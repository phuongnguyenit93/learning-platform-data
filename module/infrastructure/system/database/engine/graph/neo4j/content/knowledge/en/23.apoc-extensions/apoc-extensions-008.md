# Assessing Risks of Unrestricted Procedures and System Access

## 1. Why Is APOC Both Useful and Requiring Strict Control?

In Neo4j, Cypher operates on a **property graph** comprising nodes, relationships, labels, types, and properties. APOC (*Awesome Procedures on Cypher*) adds numerous procedures and functions to transform data, import/export files, fetch remote sources, execute dynamic queries, run batch jobs, and assist operations. For example, parsing JSON from an API can be very convenient when ingesting connected data into a graph.

However, several APOC features interact with **server files**, **network addresses**, **Cypher execution pipelines**, or Neo4j internal APIs. Enabling too many procedures, configuring `unrestricted` too broadly, or granting elevated execution privileges to the wrong account can expose business-unnecessary capabilities to an ordinary application account. Potential consequences include data leaks, reaching internal network resources via the server, unintended writes/deletions, resource exhaustion, and loss of auditability.

This lesson belongs to the **APOC and Extensions** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. Its goal is to **assess risks of unrestricted procedures and system access**, and then design layered defenses for applications using Cypher, the Neo4j Java Driver, or Spring Data Neo4j.

After this lesson, you will be able to:

1. Distinguish APOC Core/Extended, procedures/functions, and user execution privileges.
2. Accurately interpret `allowlist`, `unrestricted`, `EXECUTE PROCEDURE`, and `EXECUTE BOOSTED PROCEDURE` layers.
3. Analyze the risk surface from files, networks, dynamic Cypher, background tasks, and plugins.
4. Use **read-only** commands to inventory loaded procedures and associated privileges.
5. Build a risk assessment table, propose controls, and test in an isolated environment.

> **Scope:** Examples target Neo4j 5 and current releases, checked against documentation as of **25/11/2026**. Procedure names, Cypher 5/Cypher 25 support, editions, RBAC privileges, and APOC settings may vary by version. This lesson uses only safe verification examples and does not require calling unknown URLs, reading sensitive files, or modifying live server configs.

## 2. Distinguishing APOC Core, APOC Extended, and Custom Procedures

APOC is neither a single privilege nor a separate process running outside Neo4j. Its procedures and functions are packaged as Java libraries, loaded by Neo4j, and callable from Cypher according to server configuration and user privileges.

| Component | Role | Control Points |
|---|---|---|
| **APOC Core** | Procedure/function library officially supported by Neo4j since Neo4j 5; commonly used for conversions, import/export, and graph tasks | Enable only what the application needs; track Neo4j/APOC compatibility |
| **APOC Extended** | Community-maintained additions; may include external integrations or experimental features | Scrutinize dependencies, privileges, and security patches closely; support differs from Core |
| **Organization-authored procedures/functions** | Java code running inside Neo4j via extension APIs | Review source code, dependencies, read/write rights, and system access scope |
| **Plain Cypher** | Statements governed by Neo4j's parser, planner, and privileges | Prefer whenever sufficient; minimize unnecessary extension dependencies |

A name starting with `apoc.` does not imply all procedures carry equal risk. A string-formatting function is completely different from a procedure opening outbound connections or running dynamic queries. You must inspect **actual behavior**, accepted inputs, and granted privileges.

Since Neo4j 5, APOC Core and Extended are two separate libraries. APOC must match your Neo4j version; newer Neo4j versions bring equivalent features into Cypher, deprecating or altering availability of older APOC procedures. When upgrading, check **version-accurate documentation** before exposing system access.

## 3. Four Control Layers to Keep Distinct

A procedure appearing in the catalog does not mean every user can invoke it with unrestricted authority.

~~~mermaid
flowchart TD
    A["Plugin/JAR deployed"] --> B{"Is procedure in allowlist to be loaded?"}
    B -->|No| C["Does not appear as a callable procedure"]
    B -->|Yes| D{"Does procedure require unrestricted?"}
    D -->|Yes, explicitly permitted| E["Can use sandbox-restricted APIs"]
    D -->|No| F["Runs under standard sandbox constraints"]
    E --> G{"Does user have EXECUTE and appropriate data privileges?"}
    F --> G
    G -->|No| H["Denied or sees only permitted data"]
    G -->|Yes| I["Runs within user's privilege scope"]
    G -->|Has BOOSTED| J["Elevated privileges during procedure execution"]
    I --> K["Still bound by file, network, OS, and container limits"]
    J --> K
~~~

This diagram is a conceptual model: exact behavior still depends on each procedure's privileges and implementation. **Unrestricted** here configures API/sandbox access for extension code, whereas **boosted** is a Neo4j privilege granted to a **role** when invoking procedures. They are different mechanisms.

### 3.1. `dbms.security.procedures.allowlist` — what gets loaded?

This is a Neo4j setting in `neo4j.conf`. It defines which procedures/functions are allowed **to be loaded**. The list accepts full names or `*` wildcards. Per current docs, the default is `*`: allowing all procedures discovered in plugins to load, **without granting elevated execution privileges to all users**.

Illustrative example of a policy permitting only needed functional groups:

~~~properties
# SAMPLE FOR REVIEW — do not apply verbatim to every deployment.
dbms.security.procedures.allowlist=apoc.text.*,apoc.map.*
~~~

Verify actual dependencies: an application may need procedures omitted from the sample, while overly broad globs can load unexpected features after an upgrade.

### 3.2. `dbms.security.procedures.unrestricted` — what bypasses sandbox limits?

Also configured in `neo4j.conf`, this setting grants listed procedures/functions broader access to Neo4j internal APIs normally restricted by the sandbox. Per current docs, the default is **empty**. Setting `unrestricted` too broadly creates paths around safety guardrails extensions are meant to obey.

**Risky configuration example to avoid**, shown solely for spotting in reviews:

~~~properties
# ANTI-PATTERN — DO NOT put in configuration.
# dbms.security.procedures.unrestricted=apoc.*
~~~

Setting `unrestricted=apoc.*` does **not** let a user log in, nor is it identical to `EXECUTE BOOSTED`. It expands capabilities inside extension code while callers still need procedure privileges and other controls. Still, combining broad unrestricted access with high-privilege roles sharply increases risk.

### 3.3. `EXECUTE PROCEDURE` / `EXECUTE FUNCTION` privileges

In Neo4j Enterprise, RBAC determines which roles may call which procedures/functions. Under standard execution privileges, a procedure reading or writing graph data remains bound by **the calling user's own read/write privileges**. For instance, a read-only role cannot turn itself into a writer merely by calling a procedure.

An account with `EXECUTE PROCEDURE` also does **not automatically** possess `LOAD` privileges to fetch URLs or graph write rights. Inspect all effective privileges, including defaults/inherited grants via the `PUBLIC` role.

### 3.4. `EXECUTE BOOSTED PROCEDURE` privilege

`EXECUTE BOOSTED PROCEDURE` can allow a procedure to execute internally with privileges elevated above the caller's normal privileges. Neo4j docs emphasize that a user needs **both EXECUTE and BOOSTED privileges** to run a procedure in boosted mode.

This privilege is especially dangerous on dynamic-Cypher families like `apoc.cypher.*`, `apoc.do.*`, `apoc.periodic.*`, or triggers capable of executing statements built from inputs. If users hold overly broad boosted privileges and can influence dynamic query text, data-authorization boundaries collapse. Boosted privileges can also bypass procedure `LOAD` restrictions.

**Never use `BOOSTED` to patch a "permission denied" error before understanding why the action was blocked.** Designing properly scoped roles or moving administrative tasks into a separately authenticated workflow is usually appropriate.

## 4. Matrix: Which Mechanism Controls Which Risk?

| Question | Primary Control | What Not to Infer |
|---|---|---|
| Is the procedure loaded into the DBMS? | `dbms.security.procedures.allowlist` | Loaded ≠ any user can call it |
| May the extension use restricted Neo4j APIs? | `dbms.security.procedures.unrestricted` | Unrestricted ≠ boosted role |
| Which account may invoke the procedure? | `EXECUTE PROCEDURE` / `EXECUTE FUNCTION` | Having EXECUTE ≠ having write rights beyond role |
| Does the procedure run with elevated privileges? | `EXECUTE BOOSTED PROCEDURE` | Granting BOOSTED alone ≠ automatically granting EXECUTE |
| Which files may the procedure read/write? | `apoc.conf` + import directory config + OS permissions | `apoc.load.*` loaded ≠ able to read any file |
| Which URLs may the procedure call? | `LOAD` privileges/CIDR, egress firewall, IP blocklist, and input checks | Valid HTTPS URL ≠ trusted endpoint |
| What can extension code read on the host? | Neo4j OS process user, container/VM, filesystem mounts | DBMS privileges do not replace OS privileges |
| Who changes config and installs JARs? | Server admin access, deployment pipeline, review, and audit | Blocking one Cypher query does not replace plugin review |

The core of **defense in depth** is enforcing controls across all three layers: **application/Cypher**, **Neo4j/APOC**, and **host/network**. A flaw in one layer should never automatically expose all data.

## 5. Capability Families Requiring Risk Assessment

| Operation Family | Feature Examples | Risks to Evaluate | Mitigations |
|---|---|---|---|
| Reading data from URLs | `apoc.load.json`, `apoc.load.xml`, certain `apoc.import.*` | SSRF, probing internal networks, data exfiltration via URL | `LOAD` privileges, IP/CIDR blocks, egress rules, app-layer URL allowlists |
| Reading local files | Procedures reading from `file:///` | Reading outside permitted directories, host file disclosure | Disable when unused; enforce import directory and OS file permissions |
| Writing/exporting files | `apoc.export.*` | Unexpected file creation, disk exhaustion, sensitive data left on disk | Disable file export, restrict directory, quotas, and logging |
| Dynamic Cypher | `apoc.cypher.*`, `apoc.do.*` | Cypher injection, bypassing authorization boundaries when boosted | Parameterize, reject arbitrary fragments, forbid boosted for app roles |
| Batch execution | `apoc.periodic.*` | Massive writes, locking, heap/log pressure, and retries | Restrict roles, tune batch/concurrency, timeouts, job governance |
| Triggers/background jobs | `apoc.trigger.*`, `apoc.jobs.*` if installed | Background data mutations, hard-to-trace origins and monitoring | Enable only if needed, review triggers/jobs, audit and cap resources |
| External integrations | APOC Extended or custom plugin procedures | Credentials, dependencies, network calls, host access | Classify per module, manage secrets, apply security patches |

**Risk depends on more than the procedure name.** A URL-loading feature may be safe when fetching a fixed, vetted URL; it becomes high risk if external users freely supply arbitrary addresses, especially under a privileged role.

## 6. File Access Risks and Need-Based Configuration

APOC Core manages file read/write toggles in `apoc.conf`. In Neo4j 5+, `apoc.*` settings **do not go in `neo4j.conf`**; they belong in `apoc.conf` in the same config directory or in environment variables, where environment variables can override file settings.

| Setting | Purpose | Default per APOC Core Docs |
|---|---|---|
| `apoc.import.file.enabled` | Allows APOC to read local files | `false` |
| `apoc.export.file.enabled` | Allows APOC to write local files | `false` |
| `apoc.import.file.use_neo4j_config` | When `true`, enforces Neo4j directory restrictions for APOC file access | `true` |
| `server.directories.import` (Neo4j) | Import directory enforced when Neo4j path compliance is enabled | Typically `import` |
| `dbms.security.allow_csv_import_from_file_urls` (Neo4j) | Allows/denies `LOAD CSV` reading `file:///`; relevant when APOC honors Neo4j config | Verify effective value on running version |

**Restrictive configuration example** for a service that **does not need** file read/write:

~~~properties
# conf/apoc.conf — keep file read/write capabilities disabled.
apoc.import.file.enabled=false
apoc.export.file.enabled=false
apoc.import.file.use_neo4j_config=true
~~~

If business logic requires loading files, enable **only the specific direction** (read or write) needed and keep `apoc.import.file.use_neo4j_config=true`; review OS filesystem permissions of the Neo4j process and import directory. Never set the Neo4j path-compliance toggle to `false` merely as a quick "fix for file not found errors": that can expose paths outside the import directory.

Note that older APOC docs or examples use variant setting names. Always verify exact setting names in the **documentation for your deployed APOC release**, and distinguish **Neo4j** settings from **APOC** settings. When fetching over HTTP(S), toggling local file flags **does not replace** network access controls.

### Where does Neo4j file access run?

A file read on the Neo4j server executes under the **OS account running the Neo4j process**, not the paths and privileges of a laptop running Neo4j Browser. Container volumes, Kubernetes mounts, and service accounts are critical parts of the attack surface.

If the process runs over-privileged or mounts directories holding backups or secrets unnecessarily, database role restrictions alone may be insufficient if an extension is abused or misconfigured. Minimize OS privileges, narrow mounts, and isolate lab data from sensitive paths.

## 7. Network Risks and SSRF: Where Do URLs Come From?

**SSRF (Server-Side Request Forgery)** occurs when a server is tricked into calling an unintended network target based on untrusted input. In APOC's case, the Neo4j server initiates the HTTP request; an application user might lack direct network reachability to an internal target, whereas the Neo4j server may have it.

~~~mermaid
flowchart LR
    U["Input URL from application"] --> A["Java/Spring API"]
    A --> N["Neo4j + APOC loads from URL"]
    N --> T["Permitted data source"]
    N -. "If controls are weak" .-> I["Out-of-scope internal resource"]
~~~

Assessment questions to ask:

- Does the URL come from external users, graph data, config files, or a trusted source?
- Does the application restrict **scheme**, host/port, redirects, and resolved DNS IP addresses?
- Can the Neo4j server reach private networks, admin consoles, metadata services, or endpoints unrelated to ingestion?
- Do `LOAD` privileges, firewall/egress policies, and boosted privileges align with restriction rules?
- Are timeouts, payload size caps, JSON/XML validation, and rate limits enforced to prevent resource exhaustion?

### Two control models by edition

**Neo4j Enterprise:** use `LOAD` privileges with appropriate `CIDR` ranges to restrict allowed ingestion addresses; audit grants inherited from `PUBLIC`. APOC docs warn that `EXECUTE BOOSTED` can bypass `LOAD` restrictions, so application roles must not hold boosted rights for external-loading procedures.

**Neo4j Community:** lacks Enterprise's granular RBAC; combine version-documented internal IP blocklists (such as `internal.dbms.cypher_ip_blocklist`), host/container egress rules, and an API gateway.

**In both editions:** never take an arbitrary URL and pass it straight to a procedure. Enforce an approved source list in the application, validate redirects and DNS resolution, cap response sizes, and never embed credentials in URLs or query logs.

> Never attempt to "prove SSRF" by calling real internal addresses or unauthorized services. To test, use a mock endpoint inside an isolated test network owned by your team, or verify **denied permissions** via configuration review without hitting sensitive resources.

## 8. Risks from Dynamic Cypher and Elevated Execution

Certain APOC procedures execute **Cypher statements passed as strings**. This helps genuinely dynamic query scenarios, yet blurs the boundary between **data values** and **statement structure**.

### 8.1. Safe parameterization example

If a Java application needs to look up a user by email, prefer fixed-structure Cypher with bound parameters:

~~~cypher
MATCH (u:User)
WHERE u.email = $email
RETURN u.userId AS userId, u.email AS email;
~~~

`$email` is strictly a **data value**. Never concatenate user-supplied emails, `WHERE` clauses, relationship type lists, or Cypher fragments into an executable string.

### 8.2. When are dynamic queries especially dangerous?

Risk escalates sharply when these align:

1. User input is concatenated into arbitrary Cypher fragments.
2. Those fragments are handed to a procedure that executes them.
3. The procedure runs with `BOOSTED`, or under an over-privileged role.
4. Code review, input validation, auditing, and query limits/timeouts are missing.

Saying "the API only accepts a filter name" is insufficient if that filter can alter Cypher syntax. Parameterizing values, selecting from fixed templates, and permitting only reviewed query branches is far safer.

In Neo4j 5/Cypher 25, parameterized labels/relationship types exist in certain positions depending on version; verify actual support and **never** assume every syntax slot accepts parameters. When a structural element cannot be parameterized, map inputs strictly against a **fixed server-side allowlist**.

## 9. Never Confuse "unrestricted" with "boosted"

Compare two scenarios:

**Scenario A:** An admin adds a procedure needing restricted internal APIs to `dbms.security.procedures.unrestricted`, while the calling user holds a read-only role. This lets the extension invoke the needed internal API; it **does not automatically grant** graph-wide write access to the caller. Still, the relaxed internal API itself can be sensitive, so the extension code must be reviewed.

**Scenario B:** A role is granted `EXECUTE BOOSTED PROCEDURE` on a dynamic-query procedure, and the user supplies the query string. Inside the procedure, execution privileges can **exceed the user's normal data privileges**. This is an RBAC privilege-escalation risk distinct from sandbox relaxation.

| Aspect | `unrestricted` | `EXECUTE BOOSTED` |
|---|---|---|
| Category | DBMS configuration setting | Role privilege (Enterprise) |
| Applies to | Procedure/function names in config | Execution when a user calls a matching procedure/function |
| Technical purpose | Lets extension code call restricted internal APIs | Runs internal operations with elevated authority |
| Risk if too broad | Extension accesses sensitive internal APIs | Caller bypasses read/write/`LOAD` boundaries |
| How to audit | Inspect `neo4j.conf` and extension catalog | Inspect `SHOW ROLE ... PRIVILEGES`, `SHOW PROCEDURES`, and application call paths |
| Replaces the other layer? | No | No |

A checklist that only asks "is `unrestricted=apoc.*` set?" is **incomplete**. You must assess who can invoke the procedure, with what inputs, and what data/files/network resources it can touch at runtime.

## 10. Safe Read-Only Inventory with Cypher

The commands below are strictly for **inspection**; they do not invoke import/export procedures or trigger external side effects. Run them only with an account authorized for auditing on a team-managed system.

### 10.1. List loaded APOC procedures

~~~cypher
SHOW PROCEDURES
YIELD name, mode, admin, signature
WHERE name STARTS WITH 'apoc.'
RETURN name, mode, admin, signature
ORDER BY name;
~~~

`mode` indicates procedure classification such as `READ` or `WRITE`, which does not replace checking external side effects. A `READ`-mode procedure can still be designed to fetch URLs or read local files.

To inspect **procedures executable by the current account**:

~~~cypher
SHOW PROCEDURES EXECUTABLE BY CURRENT USER
YIELD name, mode
WHERE name STARTS WITH 'apoc.'
RETURN name, mode
ORDER BY name;
~~~

Outputs of the two queries can differ due to privileges. If the account lacks visibility into the full catalog, record your observation scope explicitly rather than concluding a procedure is not installed.

### 10.2. Inspect roles with boosted execution

On **Enterprise Edition**, using an account permitted to view roles:

~~~cypher
SHOW PROCEDURES
YIELD name, rolesExecution, rolesBoostedExecution
WHERE name STARTS WITH 'apoc.'
RETURN name, rolesExecution, rolesBoostedExecution
ORDER BY name;
~~~

Role columns may return `null` if the viewer lacks `SHOW ROLE` privilege. A `null` here **is not proof** that no roles hold boosted access.

When authorized to audit specific roles, cross-check:

~~~cypher
SHOW ROLE PUBLIC PRIVILEGES AS COMMANDS;
~~~

And inspect application roles (using your environment's real role names):

~~~cypher
SHOW ROLE app_reader PRIVILEGES AS COMMANDS;
~~~

`SHOW ROLE ...` applies only when edition and admin privileges allow. Do not copy the sample role `app_reader` if your system has no such role.

### 10.3. Inspect effective Neo4j settings

~~~cypher
SHOW SETTINGS
YIELD name, value
WHERE name IN [
  'dbms.security.procedures.allowlist',
  'dbms.security.procedures.unrestricted',
  'dbms.security.allow_csv_import_from_file_urls',
  'server.directories.import'
]
RETURN name, value
ORDER BY name;
~~~

This requires appropriate settings-viewing privileges. Some Neo4j versions or managed services restrict this output. Settings like `apoc.import.file.enabled` and `apoc.export.file.enabled` live in **apoc.conf** or environment variables, so do not assume Neo4j's `SHOW SETTINGS` displays them. Verify them via authorized configuration/deployment tooling without printing secrets into logs.

## 11. Sample Risk Assessment Table with Hypothetical Data

Suppose a team operates three applications sharing one Neo4j instance:

- **Lookup portal:** only reads public data from the graph.
- **Sync service:** periodically ingests JSON from an authenticated internal service.
- **Maintenance job:** runs batched updates under a controlled admin account.

We use an illustrative scoring scale: **Likelihood (L)** from 1 to 3, **Impact (I)** from 1 to 3, priority score `R = L × I`. This is strictly a **triage scale**, not a replacement for your organization's security risk methodology.

| ID | Scenario | L | I | R | Assessment and Mitigation |
|---|---|---|---|---|---|
| R01 | Lookup portal granted boosted access on all `apoc.*` | 3 | 3 | **9** | Critical: revoke boosted privileges, isolate read-only role |
| R02 | Sync service accepts arbitrary URLs from external requests | 3 | 3 | **9** | Critical: accept only pre-defined sources and block out-of-scope egress |
| R03 | APOC file reading enabled without restricting import directory | 2 | 3 | **6** | High: disable if unused or enforce import path + OS limits |
| R04 | Maintenance job uses huge batches with unbounded concurrency | 2 | 2 | **4** | Medium: tune batch size, timeouts, and resource quotas |
| R05 | App uses a single string helper on validated input | 1 | 1 | **1** | Low: allowlist only the needed function and keep versions patched |

**Sample conclusion:** Prioritize R01/R02 because they risk privilege bypass or unintended outbound network calls. Address R03 next due to host filesystem exposure. Measure R04 operationally; still audit R05, though at lower urgency.

### Four questions to score a concrete case

1. **Trigger source:** who invokes the procedure? External user, service account, cron job, or DBA?
2. **Controlled inputs:** can the caller influence URLs, paths, Cypher fragments, batch sizes, or target labels?
3. **Effective privileges:** what graph, `EXECUTE`, `BOOSTED`, and `LOAD` rights does the caller hold? Is the extension `unrestricted`?
4. **Blast radius if abused:** graph leak, host file read, internal network probing, bulk writes, resource exhaustion, or hard recovery?

Each answer should be backed by **evidence from configs, roles, call sites, and logs**. Never score risk purely by gut feel or procedure name guesses.

## 12. Minimal Policy Templates for Three Workload Groups

| Group | Legitimate Need | Recommended Design |
|---|---|---|
| Lookup portal | `MATCH`, aggregations, output formatting | Read-only role; parameterized Cypher; no boosted needed |
| Sync service | Periodic API reads, `MERGE` into permitted graph areas | Dedicated service account, fixed network sources, scoped write rights, file access off unless used |
| Admin tooling | Controlled schema changes, batch maintenance | Authorized DBA/jobs only; maintenance windows, audits, batch caps, change review, and rollback plan |

Illustrative configuration **for review**:

~~~properties
# conf/neo4j.conf — example for a system using a small APOC subset.
dbms.security.procedures.allowlist=apoc.text.*,apoc.map.*

# Do not grant unrestricted to all of apoc.*.
# Add exact names only after reviewing necessity.
# dbms.security.procedures.unrestricted=
~~~

~~~properties
# conf/apoc.conf — service without local file access needs.
apoc.import.file.enabled=false
apoc.export.file.enabled=false
apoc.import.file.use_neo4j_config=true
~~~

These two snippets are **not a complete production configuration**: pair them with authentication, RBAC, TLS, OS ACLs, network policies, and version-specific settings. Do not apply the sample allowlist before verifying every APOC dependency in your workloads.

For Enterprise, one hardening guideline noted in APOC docs is denying boosted APOC execution to `PUBLIC`:

~~~cypher
// RBAC policy example only; DBA must review before applying.
DENY EXECUTE BOOSTED PROCEDURE apoc.* ON DBMS TO PUBLIC;
~~~

This prevents inheriting boosted rights via `PUBLIC`; still audit other grants/denies, admin roles, and effective privileges per version. Never grant `EXECUTE BOOSTED` to an application role merely to work around file/URL access errors.

## 13. Step-by-Step Side-Effect-Free Audit Process

A safe audit should proceed as follows:

1. **Define scope:** Neo4j/APOC versions, Core/Extended, edition, cluster nodes, databases, apps, and owners.
2. **Inventory JARs and plugins:** verify provenance, checksums or artifact records, and version compatibility; never load unvetted JARs.
3. **Extract procedure catalog:** use `SHOW PROCEDURES` and `SHOW FUNCTIONS`, recording `name`, `mode`, `signature`, and deprecation status; flag file/network/dynamic-query groups.
4. **Cross-check configuration:** `allowlist`, `unrestricted`, `apoc.conf`, env vars, import directory, OS permissions, and egress firewalls; check **all servers** in the cluster.
5. **Cross-check privileges:** use `SHOW ROLE ... PRIVILEGES` and `rolesBoostedExecution`; inspect `PUBLIC`, `LOAD` rights, admin roles, and service accounts.
6. **Trace callers:** locate every app/service invoking each procedure and which inputs vary—especially URLs, file paths, Cypher fragments, and batch sizes.
7. **Prioritize findings:** record evidence, impact hypotheses, owners, mitigations, and preserved business requirements.
8. **Verify in staging:** use an account with strictly the intended privileges, run inspection queries, and execute **negative authorization tests** against mock data.
9. **Roll out via change management:** back up configs with a rollback plan, document app impact, restart per version guidance, and re-verify privileges post-deploy.
10. **Monitor continuously:** audit logs, query logs, role/config/JAR changes, outbound connections, and resource-heavy jobs; re-audit after every upgrade.

`SHOW` commands neither call external endpoints nor read host files. If you must test a blocked mechanism, use **test accounts and mock endpoints owned by your team**; never run writes, deletes, or out-of-scope reads just to "test permissions."

## 14. Five Scenario Assessment Exercises with Answers

### Exercise 1 — Identifying hazardous privileges

A service that only displays `Article` nodes was granted:

- `EXECUTE PROCEDURE apoc.*`.
- `EXECUTE BOOSTED PROCEDURE apoc.*`.
- Read access to part of the graph.

**Question:** What should be fixed first? Should `unrestricted` be expanded to keep the service stable?

**Answer:** Revoke broad boosted rights and narrow EXECUTE scope down to exact needed procedures; verify what the role genuinely requires. Do not expand `unrestricted` without a reviewed sandbox requirement. A read service should rely on plain Cypher or low-privilege functions, avoiding dynamic Cypher and unnecessary import/export capabilities.

### Exercise 2 — Locating the SSRF source

An API reads `sourceUrl` from a request and passes it to a JSON-loading procedure on the Neo4j server. Neo4j can reach the internal network.

**Question:** Where does the risk arise, and what are the three defense layers?

**Answer:** The risk occurs when the **Neo4j server** fetches a URL derived from untrusted input. Three layers: (1) API accepts only pre-defined sources and validates redirects/DNS; (2) edition-appropriate `LOAD`/CIDR privileges with no boosted access; (3) host/container egress firewall, IP blocklists, and network segmentation.

### Exercise 3 — Choosing how to grant file access

An admin job must export data into a dedicated import directory on the Neo4j host nightly. It never needs to read files from any other directory.

**Question:** Should `apoc.import.file.use_neo4j_config=false` be set to avoid path errors?

**Answer:** No. Enable only the required export capability, **keep `true`** for path compliance, configure the import directory accurately, and lock down OS permissions on the Neo4j process. Test all changes in staging and audit the output directory. If data only needs to reach a client, consider streaming results instead of granting server filesystem writes.

### Exercise 4 — Interpreting an audit result

An admin runs:

~~~cypher
SHOW PROCEDURES
YIELD name, rolesExecution, rolesBoostedExecution
WHERE name = 'apoc.load.json'
RETURN name, rolesExecution, rolesBoostedExecution;
~~~

`rolesBoostedExecution` returns `null`. The auditor concludes "No role has boosted access."

**Answer:** The conclusion is unsubstantiated. Role columns can return `null` when the querying account **lacks `SHOW ROLE` privilege**. Verify inspection privileges and cross-check `SHOW ROLE ... PRIVILEGES AS COMMANDS` using an appropriately privileged admin account.

### Exercise 5 — Why counting procedures is insufficient

One deployment has 20 APOC procedures and another has 100. Can we conclude the second deployment is riskier?

**Answer:** Not yet. Risk depends on **procedure types**, file/network/dynamic-Cypher capabilities, caller privileges, boosted/unrestricted settings, input trust, and observability. Procedure count indicates attack surface size, not the sole security metric.

## 15. Common Hardening Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| "Setting `allowlist=apoc.*` is safe because an allowlist exists." | That wildcard is very broad; the allowlist only controls **loading**, not behavior or caller privileges. |
| "`unrestricted` equals user admin rights." | It is a sandbox setting for extension code; user role privileges are a separate mechanism. |
| "`EXECUTE PROCEDURE` bypasses all graph privileges." | Standard execution obeys caller privileges; **BOOSTED** is what can elevate privileges. |
| "Setting `apoc.import.file.enabled=false` blocks all outbound connections." | This setting governs **local files**; URLs and networking need separate controls. |
| "Not using `file:///` is enough to prevent SSRF." | SSRF usually exploits HTTP(S) requests to unintended targets. |
| "A `READ`-mode procedure cannot pose system risk." | Mode describes graph operations; network calls and file reads still require assessment. |
| "We have a firewall, so Neo4j privileges aren't needed." | Firewalls and database privileges guard different layers; both are required. |
| "APOC Core and Extended share identical support/updates." | Core is officially supported; Extended is community-maintained. |
| "`apoc.*` settings go in `neo4j.conf` like Neo4j 4.x." | Since Neo4j 5, use `apoc.conf`/environment variables per version docs. |
| "Trying an internal URL is the best security test." | Audit configs/privileges and test against authorized mock endpoints instead. |

## 16. Pre-Production Checklist for APOC

- [ ] Documented list of genuinely required procedures/functions, business owners, and justification.
- [ ] Evidence of Neo4j–APOC version compatibility and JAR provenance from trusted sources.
- [ ] `allowlist` narrowed to real needs; `unrestricted` avoids broad wildcards.
- [ ] Application roles lack `EXECUTE BOOSTED PROCEDURE apoc.*` unless explicitly approved.
- [ ] `PUBLIC` and inherited role privileges audited with a sufficiently privileged account.
- [ ] File read/write disabled when unused; if enabled, restricted to exact directories and OS account.
- [ ] Source URLs validated in the application, paired with `LOAD`/CIDR or equivalent restrictions.
- [ ] Egress firewalls, DNS/redirect checks, and response caps address SSRF risks.
- [ ] No untrusted input concatenated into Cypher fragments run under elevated privileges.
- [ ] Batch sizes, concurrency, timeouts, and resources bounded for background tasks.
- [ ] Query/audit logging and secret management in place; no tokens/credentials in URLs or logs.
- [ ] Verified in staging under the application role and re-verified after upgrades.
- [ ] Configuration rollback plan, privilege documentation, and designated owner on record.

## 17. Official References for Verification

- [APOC Core — Security Guidelines](https://neo4j.com/docs/apoc/current/security-guidelines/): least privilege, file/network/SSRF, boosted procedures, dynamic Cypher, and defense in depth.
- [APOC Core — Configuration Options](https://neo4j.com/docs/apoc/current/config/): `apoc.conf` location, environment precedence, file import/export settings.
- [APOC Core — Installation](https://neo4j.com/docs/apoc/current/installation/): installation and Neo4j version compatibility.
- [Neo4j Operations — Configuration Settings](https://neo4j.com/docs/operations-manual/current/configuration/configuration-settings/): `dbms.security.procedures.allowlist`, `dbms.security.procedures.unrestricted`, and Neo4j security settings.
- [Neo4j Operations — Procedure and User-Defined Function Privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-execute-permissions/): distinguishing `EXECUTE` and `EXECUTE BOOSTED`.
- [Neo4j Operations — SHOW PROCEDURES](https://neo4j.com/docs/operations-manual/current/procedures/show-procedures/): `mode`, `rolesExecution`, `rolesBoostedExecution`, and auditing executable scope.
- [Neo4j Operations — LOAD Privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/load-privileges/): CIDR-based data-source authorization in Enterprise.
- [Neo4j Operations — Security Checklist](https://neo4j.com/docs/operations-manual/current/security/checklist/): host, network, TLS, file permissions, and patching.
- [APOC — Core and Extended](https://neo4j.com/labs/apoc/): differences between extension branches.

**Key takeaway:** APOC risk comes not from "having the APOC library installed," but from **what a procedure can do**, **which inputs users control**, **effective privileges at call time**, and **the file/network access granted to the server**. Reviewing `allowlist`, `unrestricted`, `EXECUTE/BOOSTED`, file access, egress, and auditing together establishes a safe boundary for your graph system.
