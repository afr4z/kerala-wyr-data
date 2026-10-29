const fs = require("fs");
const path = require("path");

let reps = [];
let districts = [];
let types = [];
let lbs = {};

function load() {
  try {
    const p = path.join(__dirname, "..", "data", "reps.json");
    reps = JSON.parse(fs.readFileSync(p, "utf-8"));

    const dCount = {}, tCount = {}, lbSet = {};
    for (const r of reps) {
      dCount[r.d] = (dCount[r.d] || 0) + 1;
      tCount[r.t] = (tCount[r.t] || 0) + 1;
      const key = `${r.d}||${r.t}`;
      if (!lbSet[key]) lbSet[key] = new Set();
      lbSet[key].add(r.n);
    }
    districts = Object.entries(dCount).sort().map(([n, c]) => ({ name: n, count: c }));
    types = Object.entries(tCount).sort().map(([n, c]) => ({ name: n, count: c }));
    lbs = {};
    for (const [k, v] of Object.entries(lbSet)) {
      lbs[k] = [...v].sort();
    }
  } catch (e) {
    console.error("Failed to load reps.json:", e.message);
  }
}
load();

function filterReps(query) {
  let results = reps;
  if (query.district) results = results.filter(r => r.d === query.district);
  if (query.type) results = results.filter(r => r.t === query.type);
  if (query.lb) results = results.filter(r => r.n === query.lb);
  if (query.search) {
    const s = query.search.toLowerCase();
    results = results.filter(r =>
      r.m.toLowerCase().includes(s) ||
      r.n.toLowerCase().includes(s) ||
      r.w.toLowerCase().includes(s) ||
      r.p.toLowerCase().includes(s)
    );
  }
  if (query.phone) results = results.filter(r => r.ph && r.ph.includes(query.phone));
  return results;
}

function json(res, data, status = 200) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Cache-Control", "public, max-age=300, s-maxage=300");
  res.status(status).json(data);
}

module.exports = async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const parts = url.pathname.replace(/\/$/, "").split("/");
  const query = Object.fromEntries(url.searchParams);

  // parts[0]="", parts[1]="api", parts[2]="members" (or "districts", etc.)
  const resource = parts[2] || "";
  const sub = parts[3] || "";

  // /api/members - list members
  if (resource === "members" && !sub) {
    const limit = Math.min(parseInt(query.limit) || 100, 1000);
    const offset = parseInt(query.offset) || 0;
    const results = filterReps(query);
    const page = results.slice(offset, offset + limit);
    return json(res, { total: results.length, offset, limit, count: page.length, data: page });
  }

  // /api/members/:id
  if (resource === "members" && sub) {
    const byIndex = parseInt(sub);
    if (!isNaN(byIndex) && byIndex >= 0 && byIndex < reps.length) {
      return json(res, { data: reps[byIndex] });
    }
    const byPhone = reps.find(r => r.ph && r.ph.replace(/\D/g, "").includes(sub));
    if (byPhone) return json(res, { data: byPhone });
    const byName = reps.filter(r => r.m.toLowerCase().includes(sub.toLowerCase()));
    if (byName.length) return json(res, { total: byName.length, data: byName.slice(0, 100) });
    return json(res, { error: "Not found" }, 404);
  }

  // /api/districts
  if (resource === "districts") {
    return json(res, { data: districts });
  }

  // /api/types
  if (resource === "types") {
    return json(res, { data: types });
  }

  // /api/lbs
  if (resource === "lbs") {
    const district = query.district || "";
    const type = query.type || "";
    let data = [];
    if (type) {
      data = lbs[`${district}||${type}`] || [];
    } else if (district) {
      const all = new Set();
      for (const [k, v] of Object.entries(lbs)) {
        if (k.startsWith(`${district}||`)) v.forEach(n => all.add(n));
      }
      data = [...all].sort();
    } else {
      const all = new Set();
      for (const v of Object.values(lbs)) v.forEach(n => all.add(n));
      data = [...all].sort();
    }
    return json(res, { district, type, count: data.length, data });
  }

  // /api/stats
  if (resource === "stats") {
    return json(res, {
      total: reps.length,
      districts: districts.length,
      types: types.length,
      districtBreakdown: districts,
      typeBreakdown: types,
    });
  }

  json(res, { error: "Not found" }, 404);
};
