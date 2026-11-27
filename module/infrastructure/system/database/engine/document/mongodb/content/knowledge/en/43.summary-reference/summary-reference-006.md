# How to Find Official MongoDB Documentation, Release Notes, and Compatibility Matrices

When a MongoDB command works on a developer laptop yet fails in production, the cause is not always syntax. Two environments may differ in **MongoDB Server version**, **featureCompatibilityVersion (FCV)**, deployment type (**Atlas vs self-managed**), **driver** version, **Java/Node.js/Python** runtime version, **Spring Data** integration layer, topology (**standalone/replica set/sharded cluster**), or simply a patch release containing a behavioral change. A blog post may have been accurate when written yet no longer hold for the software version currently running.

For example, a project using the MongoDB Java Sync Driver to connect to MongoDB Server must know more than the `MongoCollection.updateOne()` API. It must also check whether that driver version is compatible with the **running server**, which **JDK** it requires, which driver version Spring Data manages via its BOM, whether the needed feature has shipped on this server or Atlas tier, and whether release notes warn of any breaking changes or security advisories.

This is a summary and reference lesson in the **Database Engine Document MongoDB** module, focusing on **how to locate and verify official documentation**, **read release notes/changelogs**, and **build an evidence-backed compatibility matrix** for learning, debugging, and upgrade planning. Versions cited here serve as **lookup examples as of 2026-11-14**, not a claim that those versions will always remain the newest later. Compatibility tables and software lifecycles evolve over time; **always reopen the official documentation on the day you make a deployment decision**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish official product documentation from blogs, snippets, community posts, and legacy docs.
2. Navigate to the right documentation branch for Server, Atlas, Compass, `mongosh`, drivers, and Spring Data.
3. Pin the documentation version before copying a command or adopting a feature.
4. Locate release notes for a **major/minor/patch** release and interpret their core sections.
5. Distinguish release notes, changelogs, migration/upgrade guides, compatibility tables, API references, and issue trackers.
6. Verify compatibility across **MongoDB Server ↔ driver ↔ language runtime ↔ framework**.
7. Interpret "fully compatible," "partially compatible," "not compatible," and "untested" markers accurately.
8. Distinguish **supported**, **tested**, **works in a lab**, and **available in Atlas/self-managed**.
9. Look up EOL lifecycles, security bulletins, critical advisories, and support eligibility.
10. Retrieve Server, FCV, `mongosh`, driver, JDK/Node.js, and Spring Data versions from live environments.
11. Understand that upgrading binaries and bumping FCV are two separate decisions.
12. Evaluate Stable API, FCV, feature flags, and deployment limits when adopting a feature.
13. Build a compatibility table with URLs, verification dates, evidence, and GO/NO-GO status.
14. Plan testing, rollbacks, and audits prior to upgrading production.
15. Look up information rapidly without mistaking `current` branch docs for your running version.

## 2. Foundational Rule: Always Pin Five Facts First

Before searching for MongoDB guidance, fill in:

| Question | Example |
|---|---|
| **Which product?** | MongoDB Server, Atlas, Java Driver, `mongosh`, Compass |
| **Which version?** | Server 8.0.x, Java driver 5.x, Spring Data 4.x |
| **Where deployed?** | Atlas dedicated, Atlas auto-upgrade, Enterprise/Community self-managed |
| **How is it running?** | Standalone, replica set, sharded cluster; JDK 17 |
| **What is the goal?** | Debug connection error, use transactions, upgrade driver, check CVE |

A more concrete example:

~~~text
Product: MongoDB Server Community
Deployment: self-managed replica set, Linux x86_64
Server binaries: 8.0.x (record exact patch)
FCV: 8.0
Application: Java 17 + Spring Data MongoDB
Driver: mongodb-driver-sync 5.x (record exact patch)
Question: Can we upgrade server/driver while continuing to use transactions?
~~~

Never answer "Does MongoDB support it?" without knowing **which MongoDB product, which version, and on which topology**.

## 3. Map of Documentation Sources to Open

~~~mermaid
flowchart TD
    Q["Need to look up MongoDB information"] --> Product{"Which component is involved?"}
    Product -->|"Server command/behavior"| Manual["MongoDB Server Manual"]
    Product -->|"Managed cluster/API"| Atlas["Atlas Documentation"]
    Product -->|"Java/Node/Python driver"| Drivers["Official Driver Docs"]
    Product -->|"Spring Data"| Spring["Spring Data MongoDB Reference"]
    Product -->|"mongosh/GUI"| Tools["mongosh / Compass Docs"]
    Manual --> Version{"Select the exact version"}
    Atlas --> Version
    Drivers --> Version
    Spring --> Version
    Tools --> Version
    Version --> Evidence["Reference + Release Notes + Compatibility + Tests"]
~~~

### 3.1. Directory of Official Entry Points

| Need | Starting Page |
|---|---|
| MongoDB Server Manual | [MongoDB Database Manual](https://www.mongodb.com/docs/manual/) |
| Server release notes | [Server Release Notes](https://www.mongodb.com/docs/manual/release-notes/) |
| Versioning and upgrade paths | [MongoDB Versions and Upgrade Paths](https://www.mongodb.com/docs/mongodb-versions/) |
| FCV command | [setFeatureCompatibilityVersion](https://www.mongodb.com/docs/manual/reference/command/setfeaturecompatibilityversion/) |
| Client library compatibility | [Client Library Compatibility Tables](https://www.mongodb.com/docs/drivers/compatibility/) |
| MongoDB Java Sync Driver | [Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) |
| Java driver release notes | [Java Sync Driver Release Notes](https://www.mongodb.com/docs/drivers/java/sync/current/reference/release-notes/) |
| Java driver migration/breaking changes | [Upgrade Driver Versions](https://www.mongodb.com/docs/drivers/java/sync/current/reference/upgrade/) |
| PyMongo documentation | [PyMongo Driver](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/) |
| Spring Data MongoDB requirements | [Spring Data MongoDB Requirements](https://docs.spring.io/spring-data/mongodb/reference/preface.html) |
| Atlas docs | [MongoDB Atlas](https://www.mongodb.com/docs/atlas/) |
| Atlas changelogs | [Atlas Release Notes](https://www.mongodb.com/docs/atlas/release-notes/) |
| Atlas version policy | [MongoDB Versions in Atlas](https://www.mongodb.com/docs/atlas/atlas-versions/) |
| Compass release notes | [Compass Release Notes](https://www.mongodb.com/docs/compass/release-notes/) |
| Software lifecycle | [MongoDB Software Lifecycle Schedules](https://www.mongodb.com/legal/support-policy/lifecycles) |
| Support policy | [MongoDB Software Support Policy](https://www.mongodb.com/legal/support-policy/software) |

Documentation sites can reorganize menus, URLs, or layouts. The links above are **lookup starting points**; always inspect breadcrumbs, the version selector, and the resolved URL. For Spring Data, the authoritative reference comes from Spring—examples on MongoDB blogs never supersede Spring's reference documentation.

### 3.2. API Docs vs Behavioral Docs

The Server Manual documents server commands, stages, options, and semantics. Driver docs describe how to **invoke them from a language library**. API/Javadoc pages list classes, signatures, and exceptions. Release notes describe **changes between versions**; compatibility tables capture **relationships across versions**. Combine them—never try to extract every answer from one page.

### 3.3. Official Sources in Priority Order

1. Official reference / versioned manual or compatibility page for the exact product.
2. Corresponding release notes, migration guides, and upgrade/downgrade procedures.
3. Exact-version API docs, Javadoc, or SDK reference.
4. Official issue trackers, changelogs, and security advisories when verifying patches.
5. Official blogs/tutorials for context, cross-checked against reference docs.
6. Community / Stack Overflow / GitHub discussions for clues—**never as the sole authority** for production decisions.

## 4. Do Not Confuse MongoDB Products

"MongoDB" can refer to:

- **MongoDB Server:** the `mongod` process and underlying database engine.
- **mongos:** the query router in a sharded deployment.
- **MongoDB Atlas:** the managed database service including control plane, tiers, rollouts, and companion products.
- **MongoDB Shell (`mongosh`):** interactive/scripting client, versioned independently from Server.
- **MongoDB Compass:** GUI client with its own release cycle.
- **MongoDB Database Tools:** utilities like `mongodump`, `mongorestore`, and `mongoimport` (never assume they match Server version).
- **Language drivers:** Java, Node.js, Python, Go, C#, etc., each on its own release cadence.
- **Spring Data MongoDB:** mapping/repository framework bundling a MongoDB driver dependency.
- **Atlas Search / Vector Search / Stream Processing:** components or products with distinct capabilities, versions, and availability from core Server.
- **Ops Manager / Kubernetes Operators / Connectors:** require separate compatibility and lifecycle checks.

### 4.1. Example Mistake: "Client Is New, So Server Must Be New"

`mongosh --version` prints the `mongosh` version, **not** the server version. Having the latest Compass release does not prove your cluster supports a new aggregation stage. Query the Server directly and verify feature availability.

### 4.2. Atlas Does Not Mean Every Server Feature Is Available

Atlas enforces deployment tiers, managed settings, rollout schedules, optional services, permissions, and regional availability. A MongoDB Server feature may require a specific configuration, plan, or Atlas capability, or still be in preview on a given deployment type. Read both Server reference **and** relevant Atlas docs.

## 5. Distinguish `current` Pages From Versioned Pages

Many driver docs use URLs like:

~~~text
https://www.mongodb.com/docs/drivers/java/sync/current/
~~~

`current` points to whatever version that site treats as current. It is great for exploring newer APIs yet **may not describe the driver pinned in your repository**.

### 5.1. Safe Lookup Procedure

1. Identify the exact version from build files, lockfiles, or runtime.
2. Open the corresponding documentation portal.
3. Use the **version selector** when available and note the version branch.
4. On `current` URLs, inspect headers, breadcrumbs, and release annotations.
5. Read release notes spanning the entire version range you are upgrading across—not just the latest page.
6. Record the URL, access date, and commit/dependency lock in your decision record.

### 5.2. Legacy Pages May No Longer Be Maintained

Docs for EOL versions may move to a legacy archive; content may be frozen and omit newer advisories. Never infer from a legacy page that a version remains supported.

### 5.3. Never Guess Version URL Segments

If a URL contains `/current/`, do not assume replacing it with `/5.0/` yields a valid URL. Use the official version selector, navigation menu, or site search.

## 6. Searching Systematically

Use precise search terms instead of overly broad questions:

~~~text
MongoDB change streams resume token Server 8.0 manual
MongoDB Java driver 5.x server compatibility
Spring Data MongoDB 4.5 minimum driver compatibility
MongoDB 8.0 upgrade featureCompatibilityVersion procedure
MongoDB mongodump mongorestore compatibility tools
MongoDB Atlas search index availability tier
MongoDB partial unique index sharded restrictions
~~~

On search engines, use site filters:

~~~text
site:mongodb.com/docs/manual/ "featureCompatibilityVersion"
site:mongodb.com/docs/manual/release-notes/ "Important"
site:mongodb.com/docs/drivers/compatibility/ "Java"
site:docs.spring.io/spring-data/mongodb/reference/ "Compatibility Matrix"
site:mongodb.com/legal/support-policy/lifecycles "MongoDB 8.0"
~~~

### 6.1. Search by Exact Command Name

For `$lookup`, `updateOne`, `createIndex`, or `setFeatureCompatibilityVersion`, open the operator/command reference page first; read Syntax, Behavior, Restrictions, Compatibility, Examples, and "Changed in version."

### 6.2. Search Errors by Code and Component

When logs show `MongoCommandException`, code `11000`, `WriteConflict`, or `SERVER-xxxxx`, capture the full message/code while **stripping secrets and PII** before sharing. Search official docs/advisories/issues, then cross-check server version, topology, and driver version; the same error code can have multiple causes.

### 6.3. Looking Up Features Not Yet Released

Never treat a blog post date as a feature's GA release date. Check release notes and reference pages marked `New in version`, `Changed in version`, `Preview`, `Atlas only`, or `Deprecated`.

## 7. Distinguishing Documentation Types

| Type | What Question Does It Answer? | When to Open It? |
|---|---|---|
| Manual / reference | How does a command work, and what are its limits? | When writing code or queries |
| Tutorial / get started | How do I get started? | Learning and prototyping |
| Release notes | What was added, changed, or removed? | Before every upgrade |
| Changelog | Which exact issues/commits were fixed? | Tracing a specific bug |
| Upgrade guide | What steps and breaking changes apply? | Building a runbook |
| Downgrade guide | Can we revert to the prior version? | Rollback planning |
| Compatibility table | Is a version combination supported/tested? | Selecting dependencies |
| Lifecycle / support | Is it still maintained and patched? | Risk governance |
| Security bulletin | Which versions are affected by a CVE/advisory? | Patch prioritization |
| API / Javadoc | Which methods, classes, and signatures exist? | Compilation / implementation |

### 7.1. Release Notes Are Not Compatibility Matrices

Release notes might state "driver supports Server 9.0 feature X" without listing every JDK/driver/server matrix cell. Always check the compatibility table. Even a ✓ in a compatibility table does not guarantee your application code has **zero breaking changes** when upgrading a library.

### 7.2. A Changelog Is Not a Rollout Plan

Changelogs list fixed issues useful for bug hunting, whereas an upgrade runbook must account for topology, FCV, app drivers, platform support, backups, rollback, and tests.

## 8. Checking Live Versions on MongoDB Server

In `mongosh` connected to the target instance:

~~~javascript
// Print the Server binary version of the connected instance.
db.version()

// View build/version metadata; requires appropriate privileges.
db.runCommand({ buildInfo: 1 })
~~~

On recent MongoDB Server versions, `buildInfo` may require authentication or specific privileges. In a sharded cluster, pay attention to whether a command hits a `mongos` or a specific `mongod`; one response from one endpoint does not prove all shards and routers are on the same version during a rolling upgrade.

### 8.1. Inspecting FCV Separately

~~~javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
})
~~~

Run this against an appropriate `mongod` endpoint with required privileges. In a sharded cluster with access control, inspecting FCV on shards/config servers follows topology/privilege rules—never expect identical behavior directly on `mongos`. **Read only**—do not invoke set-FCV commands in practice labs.

### 8.2. Inspecting Topology

~~~javascript
// Within a replica set context with proper privileges:
rs.status()

// General deployment metadata:
db.hello()
~~~

`rs.status()` applies to replica set members, not standalone nodes or `mongos`. `hello` reports useful topology and wire-protocol info; exact fields vary by server and topology.

### 8.3. Checking `mongosh` Version

In your OS shell:

~~~bash
mongosh --version
~~~

Never mistake the `mongosh` version for the server version.

## 9. Checking Versions in Java / Spring Data

Dependency lockfiles are far more reliable than saying "I think the driver is 5.x."

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency mongodb-driver-sync --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-mongodb --configuration runtimeClasspath
~~~

On Windows PowerShell when using the Gradle wrapper:

~~~powershell
.\gradlew.bat dependencyInsight --dependency mongodb-driver-sync --configuration runtimeClasspath
~~~

These commands are **for learner reference**, not meant to be run against production in this lesson. Configuration names vary across Java/Kotlin/Android projects depending on dependency setup.

### 9.1. BOM / Dependency Management May Pick Versions for You

Spring Boot dependency management / BOMs pin Spring Data and MongoDB driver versions even when `build.gradle` omits explicit versions. Therefore:

- Inspect `gradle.lockfile` or resolved dependency trees.
- Check the `spring-boot-dependencies` version and Spring Data release train.
- Cross-check the minimum driver version and tested database generations.
- Never override the driver to a newer release just because "Maven Central has it" without verifying framework compatibility.

### 9.2. Maven

~~~bash
mvn dependency:tree -Dincludes=org.mongodb
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-mongodb
~~~

Inspect the BOM / `dependencyManagement` section if versions are omitted from direct dependency declarations.

### 9.3. Java Runtime

~~~bash
java -version
~~~

Driver–server compatibility is insufficient if the newer driver requires a newer JDK than your runtime, or if an older framework fails against the newer driver API.

## 10. Checking Node.js / Python and Tools

Node.js:

~~~bash
node --version
npm ls mongodb --all
~~~

With npm/yarn/pnpm, inspect the **resolved/lockfile dependency tree**, not just `package.json` semver ranges. An ORM/ODM such as Mongoose may pull a different transitive driver version than expected.

Python:

~~~bash
python --version
python -m pip show pymongo
~~~

When multiple virtual environments exist, run against the deployment interpreter; `pip show` in another shell may not reflect the active package.

Tools:

~~~bash
mongodump --version
mongorestore --version
mongoimport --version
~~~

### 10.1. Do Not Confuse Build-Time With Runtime

Container images, base OSes, JDKs, and deployed driver JARs may differ from a developer laptop. Record image hashes/tags, SBOMs, or artifact metadata to verify what actually runs in production.

### 10.2. Separate the Version Layers

~~~text
App code + Spring Boot/Spring Data
  → MongoDB Java driver + BSON codecs
    → MongoDB wire protocol/auth/TLS
      → MongoDB Server binary + FCV + topology
        → Atlas/self-managed platform capabilities
~~~

Every arrow carries **a distinct compatibility constraint**.

## 11. MongoDB Server Release Notes: Reading by Version Layer

Start at [Server Release Notes](https://www.mongodb.com/docs/manual/release-notes/). Pick the exact release series, then note both your installed patch and target patch.

A version `X.Y.Z` generally indicates:

- **X — major release:** substantial capability and compatibility changes, potentially needing dedicated upgrade paths.
- **Y — minor release:** lifecycle and availability depend on release-time policy. Starting with MongoDB 8.2, "minor" releases and distribution differ from earlier rapid releases; consult [Versions and Upgrade Paths](https://www.mongodb.com/docs/mongodb-versions/) rather than assuming all `8.x` releases share identical policies.
- **Z — patch release:** contains bug fixes, security/reliability/performance updates, and occasional notable behavioral fixes.

### 11.1. Point-in-Time Example, Not a Permanent Fact

As of **2026-11-14**, the Server Release Notes page listed the **9.0-series** under current stable alongside **8.3/8.0/7.0** under earlier series. Seeing a new release in the docs **does not** prove every cluster type, region, or edition can immediately upgrade to it. Verify availability separately for Atlas tiers or self-managed packages in [MongoDB Versions and Upgrade Paths](https://www.mongodb.com/docs/mongodb-versions/) and [MongoDB Versions in Atlas](https://www.mongodb.com/docs/atlas/atlas-versions/).

### 11.2. How to Read Patch Notes

When upgrading from `8.0.a` to `8.0.b`, do not read only the "latest patch" line. Review **every intervening patch release**, checking:

1. Critical Advisories / Important / Warning sections.
2. Security fixes / CVEs.
3. Data correctness, replication, sharding, and storage fixes.
4. Authentication / TLS / driver interaction changes.
5. Query optimizer / aggregation / index behavior changes.
6. Backward incompatibilities and new restrictions.
7. Issue IDs and full changelogs.

Dig into specific details whenever an issue touches a feature you use; never judge urgency solely by the count of fixed issues.

### 11.3. Main Release Notes vs Full Changelog

Release notes highlight major items, warnings, and patch summaries. Full changelogs list individual JIRA issues grouped by Server, Replication, Storage, Sharding, and Security. When investigating a `SERVER-xxxxx` issue, inspect both:

~~~text
Release notes (version/patch)
    → Changelog (issue ID)
        → Official issue details/advisory
            → Affected version range + verification test
~~~

Never assume "issue fixed in version X" means your branch is unaffected without checking backport branches and running patch versions.

## 12. Server Release Notes: Page-Reading Checklist

| Section on the Page | Decision-Making Significance |
|---|---|
| `New in version` | Release milestone when a feature debuted |
| `Changed in version` | Potential semantic or default changes |
| `Deprecated` | Must plan replacement |
| `Removed` | Legacy code/scripts may break |
| `Important/Warning` | Prerequisites to resolve before rollout |
| `Critical Advisory` | Potential data or security impact |
| `Upgrade Restrictions` | May forbid skipping versions directly |
| `Downgrade Limitations` | Rollback may become restricted or blocked |
| `Patch Fixes` | Identifies required security or bug patches |

### 12.1. A Single "Fixed Issue" Line Is Not Enough

Check the affected version range, reproduction conditions, workarounds, fixed release versions, and deployment type. Some issues trigger only under sharding, specific index types, or feature flags. Picking a patch solely for "lots of fixes" is not engineering rigor.

### 12.2. Do Not Confuse Preview With GA

Preview/experimental features can change APIs, support policies, and stability. For Atlas offerings, verify tier, region, and rollout status separately. Never ship a preview feature to production as GA unless official docs confirm GA status.

### 12.3. Major Upgrades May Require Intermediate Hops

Read **upgrade paths** instead of blindly swapping binaries. Mixed-version replica set/sharded upgrades, FCV transitions, downgrade constraints, and backups follow dedicated official procedures.

## 13. How to Read Driver Release Notes

Driver release notes are separate from Server release notes. For the MongoDB Java Sync Driver:

- [Java Driver Release Notes](https://www.mongodb.com/docs/drivers/java/sync/current/reference/release-notes/)
- [Java Driver Upgrade Guide](https://www.mongodb.com/docs/drivers/java/sync/current/reference/upgrade/)
- [Client Library Compatibility Tables](https://www.mongodb.com/docs/drivers/compatibility/)

### 13.1. Look for Four Categories of Changes

1. **New functionality:** new builders/APIs, integrations, support for new server features.
2. **Breaking changes:** renamed/removed classes, packages, method signatures, or changed dependency layouts.
3. **Behavioral changes:** altered defaults for retries, timeouts, authentication, serialization, or monitoring.
4. **Security/deprecation fixes:** patches affecting credentials, logging, TLS, codecs, or transitive dependencies.

### 13.2. Practical Detail Worth Reading Carefully

The Upgrade Driver Versions page includes dedicated sections on **dropped server support** across driver lines. Upgrading a driver to a newer major/minor version **does not automatically preserve connectivity to EOL servers**. Never assume "a newer driver is always backward-compatible with every older server."

### 13.3. Release Notes Do Not Guarantee Your Code Compiles

If a major Java driver release alters method signatures, your app may fail to compile even when the driver–server compatibility table shows ✓. Run build/compile and integration tests and verify dependency compatibility across Spring Data, BSON codecs, and the Java runtime.

## 14. Atlas, Compass, and Tools Maintain Separate Release Notes

A stack combining Atlas + Compass + `mongosh` + Database Tools spans **multiple independent release cycles**.

| Component | Source to Check | Types of Changes |
|---|---|---|
| Atlas control plane / cluster features | [Atlas Release Notes](https://www.mongodb.com/docs/atlas/release-notes/) | Regions, tiers, UI, backups, upgrades, managed features |
| Atlas version policy | [MongoDB Versions in Atlas](https://www.mongodb.com/docs/atlas/atlas-versions/) | Auto-upgrades, major version choices, FCV policies |
| Compass | [Compass Release Notes](https://www.mongodb.com/docs/compass/release-notes/) | GUI, connectivity, embedded shell, security |
| Java driver | [Java Driver Release Notes](https://www.mongodb.com/docs/drivers/java/sync/current/reference/release-notes/) | APIs, behavior, server support |
| Database Tools | Product-specific docs/release notes | Dump, restore, import, export behavior |
| Spring Data MongoDB | Spring release/upgrade docs | Mapping, repositories, query behavior |

### 14.1. Atlas Example

When the Atlas changelog marks a feature "GA," verify **supported cluster types, regions, tiers, and activation prerequisites**. Never infer from an Atlas changelog that self-managed MongoDB Community shares the same API.

### 14.2. Compass Example

A UI rendering bug may be fixed in a Compass patch unrelated to the Server. If Compass displays an index strangely, inspect Compass version and release notes before touching production MongoDB Server settings.

### 14.3. Backup/Restore Tools

`mongodump` and `mongorestore` have their own release cycle and compatibility rules. When planning recovery, verify **tool version ↔ source/target server version ↔ BSON/metadata/index compatibility**, rather than checking `mongod --version` alone.

## 15. Which Versions Are Currently Supported?

The [MongoDB Software Lifecycle Schedules](https://www.mongodb.com/legal/support-policy/lifecycles) page lists **release dates** and **End of Life (EOL)** dates across covered products and deployment types.

### 15.1. Sample Lifecycle Columns

| Column | Meaning |
|---|---|
| Product | Server EA, Atlas, Ops Manager, Search, etc. |
| Release version | Maintained release series |
| General availability / release date | Start milestone |
| End of Life date | End of standard support per policy |
| Optional extended support | Availability and contract/eligibility conditions |
| Source URL + verified date | Freshness proof |

**Never** apply Atlas Auto-Upgrade EOL dates to Community/Enterprise Advanced, or Server EOL dates to Compass. Read exact table headings carefully.

### 15.2. EOL Does Not Mean the Binary Stops Running Immediately

An EOL server still boots and serves traffic. Yet it stops receiving fixes and security patches, newer drivers drop compatibility, and OS/package support fades. "Still running" does not mean "supported and secure."

### 15.3. Never Copy an EOL Date Into Docs and Forget It

Vendors update lifecycles per policy. In ADRs and upgrade tickets, record the official URL and **verification date**, and add a pre-rollout re-check gate.

## 16. Security Advisories and Critical Warnings

Security patching decisions require concrete details, not rumors:

1. CVE / advisory ID.
2. Affected product and component: Server, driver, Compass, tools, or Atlas feature.
3. Affected version ranges and editions.
4. Fixed releases/patches and backports.
5. Exploitation preconditions and stated severity.
6. Official mitigation or workaround.
7. Feasibility of deploying the fix in your current topology and version.

### 16.1. Never Jump to Conclusions From an Unverified CVE

A Compass CVE does not prove the Server is vulnerable. A driver bug leaking credentials to logs is not fixed by upgrading the server. Pinpoint the exact affected component, version, and exposure path before acting.

### 16.2. Check Multiple Patch Branches

A bug may be backported to two release series under different patch numbers. Check release notes and changelogs for the **series running in production**, not solely the latest branch.

### 16.3. Record Evidence in the Ticket

~~~text
Advisory: CVE-XXXX-YYYY
Affected component: MongoDB Java driver (example)
Our resolved version: x.y.z
Fixed version available in our line: a.b.c
Official source + accessed date: ...
Mitigation until rollout: ...
Regression tests: ...
Rollback policy: ...
~~~

Placeholders avoid asserting unverified versions or CVEs. Never paste secret URIs or customer data into security tickets or chats.

## 17. What Is a Compatibility Matrix?

A **compatibility matrix** tabulates verified version/product pairs (or multi-dimensional combinations) using defined semantics: full support, partial support, incompatible, untested, minimum runtime requirements, or feature restrictions.

A Java Spring Data application must evaluate at least:

~~~mermaid
flowchart TD
    App["Application + Spring Boot"] --> Spring["Spring Data MongoDB version"]
    Spring --> Driver["MongoDB Java Driver version"]
    Driver --> Jdk["JDK runtime version"]
    Driver --> Server["MongoDB Server version"]
    Server --> FCV["Feature Compatibility Version"]
    Server --> Deploy["Replica set / sharding / Atlas tier"]
    Deploy --> Feature["Feature availability"]
~~~

Each arrow requires independent evidence. **A single ✓ between driver and Server does not certify all remaining layers.**

### 17.1. Multiple Tables, One Decision

- Driver ↔ Server.
- Driver ↔ language runtime / JDK.
- Framework / Spring Data ↔ minimum driver / tested Server versions.
- Server version ↔ OS / architecture / cloud deployment.
- Server binary ↔ FCV / upgrade path.
- Feature ↔ Server release / topology / Atlas tier / edition.
- Tools ↔ Server, metadata/backup formats, and upgrade paths.

### 17.2. Finding the Official Compatibility Table

Visit [Client Library Compatibility Tables](https://www.mongodb.com/docs/drivers/compatibility/) and select your **Language** and **Driver or Framework**. Do not read the Java driver table for a Node.js app, or read the general Node driver table for Mongoose while ignoring Mongoose's own driver dependency.

## 18. Interpreting Each Symbol in Client Compatibility Tables

Per the legend on MongoDB Client Libraries compatibility tables at reference time:

| Symbol | Meaning | Ready for Production? |
|---|---|---|
| **✓** | Combination marked **fully compatible** in the table | Strong candidate; still run app and feature tests |
| **⊛** | **Partially compatible**: connectivity works, yet full support for newer features is missing | Understand exact limits and test thoroughly |
| **✗** | Incompatible per the table | Do not choose this combination |
| **Blank cell** | Untested / unmarked per table legend | Never assume compatibility |

### 18.1. Partially Compatible Does Not Mean Everything Works

It may allow existing features while newer server APIs lack driver support. If the app needs new server features or behaviors, upgrade the driver or revise the design before proceeding.

### 18.2. A Blank Cell Is Not a ✓

If the matrix has not tested a combination, never label it "supported" simply because a quick local connection succeeded. Seek release/upgrade docs, vendor support statements, or formal verification.

### 18.3. Compatible Differs From Supported in Lifecycle

A pair may connect cleanly yet include an EOL server or unsupported runtime missing security patches. Deployment gates must clear **both compatibility checks and support/security lifecycle checks**.

## 19. Example Reading the Java Driver ↔ Server Table

Historical snapshot from **2026-11-14** on the [official compatibility table](https://www.mongodb.com/docs/drivers/compatibility/?driver-language=java&java-driver-framework=java-sync):

| Java Sync Driver | MongoDB Server 9.0 | MongoDB Server 8.0 | How to Read |
|---|---|---|---|
| 5.12–5.13 | ✓ | ✓ | Marked fully compatible across both series |
| 5.9–5.11 | ⊛ | ✓ | Missing full support for certain Server 9.0 features |
| 5.2–5.7 | Blank cell | ✓ | Never infer 9.0 compatibility from the 8.0 column |

**Note:** this is an **illustrative snapshot showing how to read the table on that date**—never pick future production versions without reopening the live source. Rows for drivers, servers, and versions may have changed since.

### 19.1. Read Every Footnote

Some combinations hit authentication caveats or runtime constraints even when a driver looks "compatible with older servers." Table footnotes call out key exceptions; **never skip footnotes**.

### 19.2. Read Both Directions

Do not ask only "Does Server 9.0 work with driver 5.10?" Also ask: "Does driver 5.10 support my JDK?", "Does my Spring Data version support that driver?", and "Are all features my app uses fully supported?"

### 19.3. Server 9.0 May Not Be Available on Your Tier Yet

Documentation listing a release does not mean your Atlas cluster tier or self-managed package repository offers that exact series/patch today. Check version availability for your **exact deployment**.

## 20. Driver ↔ Runtime: The Frequently Forgotten Axis

Java examples:

| Current Runtime | What to Check |
|---|---|
| Java 8 | Which driver versions still support it? |
| Java 11 | Which Spring Data releases support it? |
| Java 17 | Driver APIs, TLS, Spring Framework requirements |
| Java 21 | Driver and runtime feature compatibility |
| Container JRE vs local JDK | Actual resolved production runtime/JRE |

MongoDB Client Library Compatibility Tables include a dedicated **Java Compatibility** section. Read it the same way: ✓ records tested/supported pairs per the table, without replacing framework and runtime integration tests.

### 20.1. Node.js and Python

Node.js driver tables add a **Node.js versions** dimension; PyMongo tables track Python/PyPy runtimes. Before upgrading any driver:

1. Check minimum runtime version.
2. Check framework/ODM version.
3. Check driver ↔ Server compatibility.
4. Run tests inside the exact runtime/container image used in production.

### 20.2. Newer Runtimes Can Still Surprise You

Upgrading JDK, Node.js, or Python can alter TLS ciphers, native dependency binaries, codecs, threading, and logging even if MongoDB Server stays unchanged. Treat runtime upgrades as separately tested changes.

## 21. Spring Data MongoDB: Both Matrices Must Align

The [Spring Data MongoDB Requirements](https://docs.spring.io/spring-data/mongodb/reference/preface.html) page publishes:

- Spring Data release train and MongoDB module version.
- **Minimum MongoDB Java driver version**.
- MongoDB Server versions **tested** by Spring Data.
- Required JDK and Spring Framework versions.

### 21.1. Snapshot Example at Reference Time

In the published Spring Data MongoDB table at reference time, release train **2026.0** mapped to Spring Data MongoDB **5.1.x**, minimum driver **5.6.x**, and tested databases **6.x–8.x**. That indicates **framework minimum driver and tested scope**—it does **not** mean any arbitrary driver ≥ 5.6 works blindly, nor does it declare MongoDB Server 9.0 incompatible.

### 21.2. Intersect Conditions Logically

~~~text
Spring Data version requirement
  ∩ Driver compatibility with Server
  ∩ Driver compatibility with JDK
  ∩ Spring Framework/Boot compatibility
  ∩ Feature/topology availability
  = candidate deployment combination
~~~

If Spring Data requires at least driver 5.6 while the project pins 5.4, **NO-GO**. If driver 5.10 shows ⊛ with Server 9.0 while the app relies on an unsupported 9.0 feature, upgrade the driver or adjust the design before GO.

### 21.3. Tested Database Versions ≠ Absolute Maximum

Spring Data may list "tested 6.x–8.x" even after the official driver matrix supports a newer Server. That means **dedicated framework integration testing and vendor support evaluation are required**, rather than assuming "definitely works" or "definitely breaks."

### 21.4. Boot BOMs May Resolve Differently Than Expected

Inspect the resolved dependency tree. Spring Data 5.x may transitively pull a different MongoDB Java Driver than a direct declaration or override; avoid incompatible mixes across `mongodb-driver-sync`, `mongodb-driver-core`, and `bson`.

## 22. Building a Project Compatibility Matrix

Instead of one line reading "MongoDB compatible," use an explicit table:

| Component | Current | Proposed | Official Source | Result |
|---|---|---|---|---|
| MongoDB Server | x.y.z | a.b.c | Server release notes, lifecycle | TBD |
| FCV | x.y | target FCV | Versions & FCV docs | TBD |
| Topology / edition | Replica set / Atlas tier | ... | Deployment docs | TBD |
| MongoDB Java driver | x.y.z | a.b.c | Driver–Server matrix | TBD |
| Java runtime | JDK x | JDK y | Driver Java compatibility | TBD |
| Spring Data MongoDB | x.y.z | ... | Spring requirements | TBD |
| Spring Boot / Framework | x.y.z | ... | Spring support docs | TBD |
| `mongosh` / Compass | x.y.z | ... | Tool release notes | TBD |
| Database Tools | x.y.z | ... | Tool compatibility | TBD |
| Features used | Change streams, transactions | ... | Server/Atlas feature docs | TBD |
| Platform | OS / container architecture | ... | Supported platforms | TBD |

**TBD** is not PASS. Populate every cell only after verification—never extrapolate from a passing localhost connection.

### 22.1. Attach Source and Timestamp

Each critical row should capture:

~~~text
Evidence URL:
Source title:
Source product/version:
Verified at (UTC):
Owner:
Notes/footnotes:
Decision (PASS / CONDITIONAL / NO-GO / UNKNOWN):
~~~

### 22.2. Automate What Can Be Automated

Dependency versions can be extracted from lockfiles and SBOMs; Server/FCV versions from read-only diagnostic scripts; yet human review remains necessary for support policies, footnotes, and feature availability.

## 23. What Is Feature Compatibility Version (FCV)?

MongoDB Server binary version and **featureCompatibilityVersion** are two separate properties. FCV gates features that persist data in formats or semantics unreadable or unusable by an older server version.

~~~text
MongoDB binaries newly upgraded
    ↓
Cluster runs temporarily on prior FCV per upgrade path
    ↓
Observe / stabilize
    ↓
Only after full confidence and understanding downgrade impact
    ↓
Bump FCV per official procedure
~~~

Per [MongoDB Versions and Upgrade Paths](https://www.mongodb.com/docs/mongodb-versions/), upgrading binaries and enabling new FCV-gated features are separated into two steps on supported upgrade paths. Exact rules vary by version and Atlas rollouts; always consult the exact release guide.

### 23.1. FCV Is Not the Driver Version

A newer driver does not change FCV. Running newer server binaries with an older FCV does not unlock persisted features tied to the newer FCV.

### 23.2. FCV Is a Critical Downgrade Gate

Once incompatible persisted formats or features are enabled, downgrading binaries to the previous version becomes difficult or forbidden until handled. Before raising FCV, review **downgrade documentation, rollback windows, and backups**.

### 23.3. FCV Does Not Replace Compatibility Testing

A matching FCV does not prove driver, server, and framework compatibility; it is only one dimension of deployment state.

## 24. Inspecting FCV and Handling Change Commands Carefully

**Reading status**:

~~~javascript
// Connect to an appropriate mongod with required privileges.
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
})
~~~

**Never** run this command casually in a lab to bump/downgrade FCV:

~~~text
setFeatureCompatibilityVersion
~~~

Setting FCV alters persisted feature compatibility and downgrade paths; required flags such as `confirm`, `writeConcern`, and preflight checks vary by server release. Check the exact-version [command reference](https://www.mongodb.com/docs/manual/reference/command/setfeaturecompatibilityversion/)—never paste a command from an old blog post onto a production cluster.

### 24.1. Atlas Differences

Atlas Auto-Upgrades manage rollouts and FCV under different policies than self-managed clusters; users may not control FCV directly as on a standalone/self-managed `mongod`. Read [MongoDB Versions in Atlas](https://www.mongodb.com/docs/atlas/atlas-versions/).

### 24.2. Do Not Bump FCV Immediately Inside the Upgrade Window Unless Needed

When an upgrade guide allows a burn-in period on the prior FCV, that window lets you verify compatibility and catch regressions before enabling irreversible persisted features. Equally, do not leave FCV pinned forever without tracking support policies and operational requirements.

### 24.3. Never Treat FCV as a Casual Toggle

Downgrading FCV can carry strict preconditions requiring cleanup of persisted data, indexes, or features. Some downgrade paths are unsupported or lossy. Always require a dedicated runbook and formal approval.

## 25. What Problem Does Stable API Solve?

MongoDB Stable API (also called Versioned API in some docs) lets applications request stable behavior for **commands covered by that API version**, reducing upgrade friction across driver and server updates.

Reference: [Stable API — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/stable-api/).

### 25.1. What Stable API Does Not Promise

- Does not cover every MongoDB command or aggregation stage.
- Does not replace the driver ↔ server compatibility matrix.
- Does not guarantee Atlas preview or edition-specific features exist.
- Does not shield against breaking changes in Java app APIs, Spring Data, or the JDK.
- Does not automatically align backup formats, index rules, or query performance.

### 25.2. How to Check Whether a Command Is in Stable API

1. Verify which Server versions support Stable API.
2. Open the Stable API reference and its **list of covered commands**.
3. Check every command and option your application uses.
4. Review `apiStrict` and `apiDeprecationErrors` behavior when enabled.
5. Run full integration tests under strict mode if adopted by your project.

### 25.3. Java Driver Skeleton

~~~java
import com.mongodb.MongoClientSettings;
import com.mongodb.ServerApi;
import com.mongodb.ServerApiVersion;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

ServerApi serverApi = ServerApi.builder()
    .version(ServerApiVersion.V1)
    .strict(true)
    .deprecationErrors(true)
    .build();

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(
        new com.mongodb.ConnectionString(
            System.getenv("MONGODB_TEST_URI")
        )
    )
    .serverApi(serverApi)
    .build();

try (MongoClient client = MongoClients.create(settings)) {
    // Integration tests against an isolated compatible deployment.
}
~~~

This is a **configuration example** for Java Sync Driver versions supporting `ServerApi`, not meant to be run standalone here. Under strict mode, calling any command or option outside the Stable API subset gets rejected; fix the code rather than disabling checks and claiming everything is stable.

## 26. Feature Matrices Differ From Version Matrices

Even when Java driver 5.x and Server 8.x are marked compatible, specific features may still be constrained:

| Feature | Where to Verify? | What Can Block It |
|---|---|---|
| Multi-document transactions | Server transaction docs, topology | Standalone vs replica set/sharded, limits |
| Change streams | Server docs, deployment topology | Supported deployment, oplog history |
| `$lookup` on foreign sharded collection | Aggregation reference + release notes | Server version / feature restrictions |
| Atlas Search | Atlas Search docs + tier | Product availability, index limits |
| Vector search | Atlas/Server docs + release notes | GA vs preview, engine/tier |
| Stable API option | Server Stable API reference | API version / command coverage |
| Queryable Encryption | Encryption docs + driver compatibility | Driver, server, KMS, query types |
| CSFLE | Driver and server docs | Crypt library, KMS, BSON/feature limits |
| Resharding | Sharding / upgrade reference | Topology, FCV, restrictions |
| Time-series collections | Server manual + release notes | Version-specific query/write limits |

### 26.1. Version-Conditional Example

Features like transactions and `$lookup` on sharded collections gained capabilities gradually across releases. When researching, inspect `New in version` and Limitations sections on reference pages—never assume a syntax accepted by `mongosh` executes every variant on your server.

### 26.2. Server Feature ≠ Driver Helper

A Server may support a command before an older Java Driver adds a typed builder method. While raw commands may work under matching privileges and semantics, **never** treat raw commands as a way to bypass compatibility or security policies.

### 26.3. Atlas Feature ≠ Community Feature

Mark PASS only when official docs explicitly confirm support for your deployment type and preconditions. For managed Search or Vector Search capabilities, never assume self-managed `mongod` provides identical features.

## 27. Platform Compatibility Is an Independent Axis

A MongoDB Server release supports specific OS distributions, CPU architectures, CPU instruction requirements, and packages.

### 27.1. What to Check?

1. Supported Platforms for your **Server major/minor version**.
2. OS distribution/release: Ubuntu, Debian, RHEL, Windows, or macOS where supported.
3. CPU architecture (`x86_64` / `ARM64`) and CPU feature requirements.
4. Container image tag/digest, base OS, and shared libraries.
5. TLS/SSL/OpenSSL, FIPS, and authentication mechanisms.
6. Filesystem, kernel, and storage requirements for self-managed hosts.
7. Docker, Kubernetes Operator, or Ops Manager versions if used.

### 27.2. A Container Booting Does Not Mean It Is Supported

A container may start on an unsupported OS or kernel. For production, verify official supportability and security independently of passing smoke tests.

### 27.3. Atlas Abstracts Platform Details Without Removing Client Axes

Atlas manages server/OS details, yet clients still must satisfy driver, runtime, TLS, and network compatibility while following Atlas upgrade policies.

## 28. Mixed-Version Deployments During Upgrades

Rolling upgrades of replica sets or sharded clusters pass through phases running **multiple binary versions concurrently** under supported procedures. That does not mean arbitrary patch or minor combinations are allowed.

### 28.1. Read the Exact Upgrade Procedure

Scenarios to consult individually:

- Upgrading standalone instances.
- Upgrading replica sets.
- Upgrading sharded clusters (including `mongos`, config servers, and shards).
- Atlas managed rolling upgrades.
- Downgrading or restoring mid-upgrade.

### 28.2. Do Not Enable New Features Too Early

During mixed-version operation, an updated app sending commands or options understood only by the new server version will fail against older nodes or routers. Follow the official upgrade order, FCV steps, and rollout guidance before using new features.

### 28.3. Compatibility Matrices Are Necessary, Not Sufficient

A driver may support both old and new servers while an app feature works only on the new binary. Test transitional topologies per the upgrade guide.

## 29. What Levels of "Supported" Exist?

| Term | How to Interpret |
|---|---|
| **Can connect** | Client established a connection in one test |
| **Works for tested use case** | A few selected operations succeeded |
| **Compatible** | Meets vendor compatibility chart definition |
| **Fully compatible** | Chart indicates full support within documented scope |
| **Partially compatible** | Subset of features supported; read limitations |
| **Tested by framework** | Covered by the framework's test matrix |
| **Supported release** | Within active vendor maintenance/support lifecycle |
| **GA available** | Generally Available in the stated product/deployment |
| **Preview / experimental** | Do not expect GA guarantees |
| **EOL / legacy** | May still run, yet support and security fixes are limited/ended |

### 29.1. Do Not Over-Interpret ✓

A ✓ in the driver ↔ Server chart does not guarantee throughput, hardware headroom, topology health, user permissions, tier features, or application correctness.

### 29.2. Do Not Treat a Blank Cell as a Guaranteed Failure

It may simply mean untested or unmarked; look for other sources. Only an explicit ✗ or clear official statement establishes incompatibility within that scope.

## 30. Status Taxonomy for Internal Tracking Tables

Use a consistent status set:

| Status | Meaning | Action |
|---|---|---|
| `PASS` | Support/feature evidence and tests pass | Cleared for rollout |
| `PASS_WITH_CONDITIONS` | Compatible with documented caveats or mitigations | GO only once conditions are met |
| `UNKNOWN` | Insufficient data or blank matrix cell | Verify with vendor docs or tests |
| `NO_GO` | Incompatible or violates a hard gate | Change version or architecture |
| `EOL_RISK` | Out of support or security exposure | Schedule replacement roadmap |
| `NEEDS_TEST` | Matrix shows compatible, app untested | Run integration/load/fault tests |

Never mark `PASS_WITH_CONDITIONS` as plain `PASS` and forget the footnotes. Assign an owner, due date, and verification evidence.

## 31. Multi-Dimensional Verification Matrix Template

**Hypothetical** template example (not vendor certification):

| Server | Java Driver | Java Runtime | Spring Data | Feature | Vendor Matrix | Internal Test | Decision |
|---|---|---|---|---|---|---|---|
| A | B | JDK-X | SD-Y | CRUD | URL needed | TBD | UNKNOWN |
| A | B | JDK-X | SD-Y | Transactions | URL + topology | TBD | NEEDS_TEST |
| C | D | JDK-Z | SD-W | Change streams | URL + oplog policy | TBD | UNKNOWN |
| C | D | JDK-Z | SD-W | New feature | Release note + API ref | TBD | UNKNOWN |

For real migration decisions, add columns for `OS/platform`, `FCV`, `Atlas tier`, `security advisory`, and `support EOL`. A wiki table cannot replace real evidence, yet it quickly **exposes missing cells**.

### 31.1. Same Versions, Different Topologies

Transactions run on a replica set yet fail on standalone; connecting to Atlas Search introduces rules beyond CRUD. Create dedicated test rows per feature your app actually uses.

### 31.2. Managing "Unknown" Entries

Never fill in optimistic values without a source. Assign an owner and task to gather evidence, and block GO if an unknown covers a hard business requirement.

## 32. Planning Upgrades From Official Sources

~~~mermaid
flowchart TD
    Inventory["Inventory versions + workload"] --> Lifecycle["Check EOL and advisories"]
    Lifecycle --> Compat["Compatibility intersection"]
    Compat --> Release["Release notes + upgrade restrictions"]
    Release --> Staging["Stage on production-like topology"]
    Staging --> Tests["Functional + concurrency + load + fault tests"]
    Tests --> Gate{"GO/NO-GO"}
    Gate -->|"NO-GO"| Fix["Change plan/version, retest"]
    Fix --> Compat
    Gate -->|"GO"| Rollout["Backup + controlled rollout"]
    Rollout --> Monitor["Monitor + burn-in + FCV decision"]
    Monitor --> ADR["Record result, update matrix"]
~~~

These steps form a decision framework. Actual node, router, and FCV upgrade sequences must strictly follow **the version- and topology-specific upgrade guide**, not a generic flowchart.

### 32.1. Pre-Upgrade

- Record baseline server binaries, FCV, driver, runtime, framework, and topology.
- Check support lifecycles, EOL dates, and security advisories.
- Pick target versions matching availability and official upgrade paths.
- Read all breaking changes, deprecations, and behavior changes across the span.
- Choose a driver version compatible throughout the **transition window**.
- Confirm backup/restore readiness, rollback windows, and approvers.

### 32.2. Staging

- Clone schemas/indexes and anonymized data or representative distributions.
- Test auth/TLS, CRUD, aggregations, transactions, and change streams.
- Test hot tenants, timeouts, retryable writes, and failovers.
- Compare query plans/`explain`, p95/p99 latency, throughput, and resource usage.
- Test application builds, dependency locks, and new JDK/OS images.

### 32.3. Post-Upgrade

- Verify all nodes and routers run expected binary versions and report healthy.
- Monitor app connection pools, server-selection errors, retries, and slow queries.
- Hold a burn-in window before bumping FCV if the guide permits.
- Bump FCV only after approval and reviewing downgrade limitations.
- Update compatibility evidence, runbooks, inventories, and alerts.

## 33. Avoid Upgrading Every Layer Simultaneously Unless Required

Suppose you upgrade Server, driver, Spring Data, and JDK in one deployment. If something breaks, the regression could originate in any layer.

### 33.1. Reducing Variables

Where compatibility and support rules permit, stage upgrades in phases:

~~~text
Current Server + Current driver/framework/runtime
    ↓ driver/framework compatibility preparation
Current Server + New compatible driver
    ↓ Server binary upgrade per official procedure
New Server + New driver, previous FCV during burn-in if allowed
    ↓ FCV upgrade after validation
New Server + New FCV + New driver
    ↓ Optional framework/runtime upgrade in independent rollout
Target state
~~~

**Never** treat this diagram as a mandatory universal order. Some newer drivers or frameworks drop older servers, requiring intermediate versions or an adjusted sequence per the matrix.

### 33.2. Benefits of Staged Rollouts

Fewer moving variables simplify troubleshooting, application layers roll back cleanly, and regressions surface per step. The trade-off is managing compatibility across intermediate states.

### 33.3. When Are Simultaneous Upgrades Mandatory?

If a new driver drops support for the old Server or a new framework requires a newer JDK, coordinate their deployment together. Never force phased steps into unsupported combinations.

## 34. Downgrading Is Not Simply "Swapping Binaries Back"

A rollback plan must evaluate:

1. Is there an officially supported downgrade path from the target version?
2. Has FCV already been bumped, and were backward-incompatible data/features persisted?
3. Did sharded topology or cluster metadata change?
4. Do the newer driver and framework still connect to the older Server?
5. Were writes acknowledged after the pre-upgrade backup point?
6. Can restore/PITR meet business RPO?
7. What external side effects (payments/events) need reconciliation?

### 34.1. Application Rollback Differs From Database Downgrade

Rolling an app back to a prior JAR can be fast if driver/server compatibility holds. Downgrading Server binaries/FCV or restoring a database carries strict preconditions; **never lump** both into one "rollback" button.

### 34.2. Persisted Features Can Block Downgrades

If a new feature writes formats unreadable by the old version, downgrading may be rejected or require data cleanup. Review `Downgrade Limitations` for your exact release and prepare a forward-fix option.

### 34.3. Never Assume "Old FCV Means 100% Guaranteed Downgrade"

Keeping an older FCV preserves certain compatibility conditions, yet binary behaviors, index/data changes, support paths, and operational steps still apply. Test rollback steps per the official guide.

## 35. Building a Matrix Across Dev, Staging, and Production

| Environment | Server Binary | FCV | Resolved Driver | Spring Data | Runtime | Notes |
|---|---|---|---|---|---|---|
| Dev | Record exact version | Record exact value | Lockfile / dependency tree | Actual artifact | JDK/Node | Local / containers |
| Staging | Record exact version | Record exact value | Deployed artifact | Actual artifact | Runtime image | Representative topology |
| Production | Record exact version | Record exact value | Deployed artifact | Actual artifact | Runtime image | Security / region / tier |

### 35.1. Why Does Dev Pass While Prod Fails?

Dev runs a newer standalone MongoDB; prod runs an older sharded cluster; dev pulled a newer driver via a loose dependency range; staging runs JDK 21 while prod runs JDK 17; prod reads from secondaries or uses an Atlas tier lacking a feature. This table isolates mismatches fast.

### 35.2. Patch-Level Inventory

Do not just write "Server 8.0"; record `8.0.x` down to the exact patch per member/cluster. Security fixes ship in patch releases.

### 35.3. Mixed Binary Versions Are Temporary

During rolling upgrades, document the transition window and next steps. Never leave mixed versions sitting indefinitely in an inventory dashboard without an owner.

## 36. Finding "Feature Introduced in Version" Properly

Suppose a developer asks: "Can we use aggregation stage X on this cluster?"

1. Open the operator/stage reference in the Server Manual.
2. Read `Definition`, `Compatibility`, `New in version`, and `Changed in version`.
3. Check the release notes for the introducing version.
4. Read restrictions: sharding, transactions, Atlas vs self-managed, runtime, indexes.
5. Check Java driver builder or raw command API support; if absent, follow compatibility policy.
6. Confirm live Server binary, FCV, and deployment type.
7. Run a minimal query in a **test deployment** and integration suite.

### 36.1. Never Treat IDE Autocomplete as Proof

A newer `mongosh`, Compass, or IDE driver jar may autocomplete a stage unsupported by an older server. The Server decides what actually runs.

### 36.2. Raw Commands Do Not Bypass Feature Gates

When a driver lacks a helper method, sending a raw BSON command will not teach an older Server new syntax. Even when the Server supports a feature absent from driver helpers, raw commands must still comply with security, support, and testing policies.

## 37. When Release Notes Say a Feature Is "New"

Ask further:

- New on the **Server** or new in a **driver helper**?
- New for **Atlas Search** or core Server?
- **GA** or **Preview**?
- Requires a specific **FCV, edition, tier, or index type**?
- Included in **self-managed Community**?
- Deprecated or changed semantically in a later release?

For instance, "driver added a builder for an aggregation stage" **does not** make an older Server understand that stage.

## 38. Finding the Right Pages for Backup / Database Tools

When changing Server versions while still running older `mongodump`/`mongorestore`:

1. Check Database Tools release notes and compatibility for the installed tool version.
2. Verify both source and target server versions.
3. Check dump format, metadata/index restoration, and auth/TLS behavior.
4. Test restoring into a test cluster and validate data and invariants.
5. Verify backups meet RPO/RTO—not just exit code 0.

### 38.1. Do Not Confuse JSON/CSV Exports With Full Backups

`mongoexport` and `mongoimport` serve application data interchange without preserving all BSON types, indexes, metadata, or snapshot consistency like backup tools. Read the docs for each tool's intended purpose.

### 38.2. Distinguish Tool Binaries From Server Binaries

`mongodump --version` often differs from `db.version()`; that is normal. What matters is that the combination is officially supported/tested for your restore requirements.

## 39. Checking Spring Boot / Spring Data When Changing Drivers

For Spring applications:

1. Identify the Spring Boot version and dependency BOM.
2. Identify the resolved Spring Data MongoDB artifact version.
3. Open [Spring Data MongoDB Requirements](https://docs.spring.io/spring-data/mongodb/reference/preface.html).
4. Record the minimum Java driver version and tested Server versions.
5. Check the MongoDB Java driver Server and JDK matrices.
6. Read Spring Data release notes/migration guides alongside the driver upgrade guide.
7. Run tests covering repositories, transactions, `@Version` optimistic locking, custom converters, aggregations, and bulk operations.

### 39.1. Do Not Overlook Codecs

Upgrading across major Java driver and BSON codec versions can alter behavior for custom codecs/converters, UUID representations, `Decimal128`, `ZonedDateTime` serialization, or legacy APIs. Check release notes and test against real data types.

### 39.2. Reactive and Synchronous Drivers Are Distinct Integrations

MongoDB Java Sync Driver and Reactive Streams Driver have separate APIs and artifacts; Spring Data MongoDB's reactive stack requires the matching reactive driver and Spring integration. Never rely on Java Sync docs to prove reactive stack behavior.

## 40. Investigating Bugs: Building an Evidence Chain

Suppose an application hits authentication errors after a Server upgrade:

~~~text
Observed:
  MongoDB Server old -> new
  Java driver old (unchanged)
  Error: handshake/authentication failure
~~~

Investigation steps:

1. Record exact versions/patches, auth mechanism, OS/JDK, and deployment type.
2. Open the driver–Server matrix and check authentication footnotes.
3. Read driver Upgrade Versions/release notes and Server release notes.
4. Check issue advisories and changelogs if needed.
5. Reproduce in a test deployment matching the driver/server matrix.
6. Upgrade the driver along a supported path or adjust auth configuration per official docs.
7. Document root cause and add a regression test.

### 40.1. Never Guess From a Stack Trace Alone

A connection exception can stem from TLS certificates, DNS/SRV records, network ACLs, auth mechanisms, expired credentials, or driver–server mismatches. Combine symptoms, environment inventory, and vendor docs.

### 40.2. Never Share Connection Strings With Passwords

In tickets and logs, redact usernames, passwords, tokens, internal hostnames per policy, customer IDs, and PII while keeping sanitized topology/port/driver metadata.

## 41. Scenario A: Upgrading Server While Keeping an Older Java Driver

Suppose an application currently runs:

~~~text
Server: 8.0.x
Java Sync Driver: 5.10.x
Java runtime: JDK 17
Framework: with or without Spring Data
Goal: evaluate upgrading to Server 9.0.x
~~~

From the compatibility table snapshot at reference time, Java Driver 5.10 with Server 9.0 showed **⊛** (partially compatible), whereas 5.12–5.13 showed ✓ under 9.0. That is not a blind command to "upgrade to 5.13"; it signals checking which new 9.0 features driver 5.10 lacks and verifying live availability of both driver and Server versions.

### 41.1. Follow-Up Questions

- Does the app only use existing CRUD or require new Server 9.0 features?
- Is Server 9.0 available on our current tier/edition yet?
- Does the newer driver support JDK 17 and our Spring Data/BOM?
- Are there auth/TLS changes, deprecations, or security advisories?
- Are Server/FCV rollbacks permitted once new features are used?

### 41.2. Sample Conclusion

~~~text
Status: PASS_WITH_CONDITIONS or NEEDS_TEST
Reason: driver/server partially compatible for some features
Actions: inventory commands, read driver notes, test targeted features,
         validate deployment availability, create upgrade rollback plan
~~~

Never mark `PASS` simply because `db.runCommand({ping:1})` succeeded.

## 42. Scenario B: Spring Data Test Matrix Does Not List the Newer Server Yet

Suppose your Spring Data MongoDB version lists tested database generations `6.x–8.x`, while your target Server is 9.0.

### 42.1. Proper Interpretation

"Tested `6.x–8.x`" does not mean "9.0 definitely fails." It means **you cannot cite that table row as proof that Spring Data tested 9.0**. Review Spring Data release/upgrade docs, the driver matrix, and run application integration tests.

### 42.2. Do Not Ignore Framework-Generated Behavior

Frameworks issue commands, register codecs, and manage change streams, transactions, and indexes on your behalf. Test every path:

- `MongoRepository` / `MongoTemplate` CRUD.
- `@Version` and `@Id` mapping/migrations.
- Custom conversions and BSON types.
- Aggregation pipelines, sorting, and pagination.
- Reactive repositories if used.
- Transactions, sessions, retries, and idempotency.

### 42.3. Decision

Never put a ✓ on Spring Data–Server without official proof or tests. Mark `NEEDS_TEST` or `UNKNOWN` with an owner and target date; if vendor support policy forbids it under business rules, mark `NO_GO`.

## 43. Scenario C: New Code Uses an Unavailable Server Feature

Suppose a developer reads a tutorial on a new aggregation stage and adds it to a production pipeline while production runs an older Server version.

### 43.1. Lookup Sequence

1. Get the **exact stage/operator name**.
2. Open the Server Manual for your exact running version.
3. Check `New in version` and `Compatibility`.
4. Verify Atlas/self-managed availability and FCV prerequisites.
5. Check Java driver builder or raw command API support.
6. Test in staging matching the production server/driver pair.

### 43.2. Never Treat IDE Autocomplete as Authority

Newer drivers or Compass may recognize syntax unsupported by older servers. Autocomplete reflects client definitions, not Server deployment capabilities.

### 43.3. If Prerequisites Are Missing

Upgrade the deployment per official procedures, implement an approach compatible with the current server, or defer the feature. Never try sending raw BSON commands to work around a version restriction.

## 44. Scenario D: Release Notes Carry a Security Advisory

Suppose release notes include an `Important` section citing a CVE affecting a range of driver versions.

### 44.1. Response Sequence

1. Identify the exact component (Java Driver, Server, Compass, `mongosh`, tools).
2. Check the exact resolved version in production—not a loose range in a build script.
3. Read affected version ranges and fixed releases.
4. Check for backports onto your active release line.
5. Assess real exposure: which auth features are enabled, and what appears in logs.
6. Choose a supported patch; review compatibility matrices and upgrade guides.
7. Test authentication, TLS, connection pools, codecs, and critical workflows.
8. Roll out per security change control, monitor, and archive remediation evidence.

### 44.2. Do Not "Upgrade the Server" for Every CVE

If the flaw lives in driver logging code, upgrading the Server fixes nothing. Conversely, a Server storage bug is not resolved by updating Compass. Match the component before acting.

## 45. Scenario E: Production Runs 8.0 While `current` Docs Show 9.0

A developer finds a snippet on the latest docs page and adds an option that does not exist in 8.0.

### 45.1. Prevention

- Record exact Server version and FCV.
- Use the Manual version selector or open exact release notes.
- Check `Changed in version` for any option you plan to use.
- Verify on a test deployment matching production version and topology.
- Add versioned reference URLs in ADRs/PR comments whenever behavior depends on release version.

### 45.2. Never Treat Dynamic URLs as Immutable Truth

A `current` URL shifts to newer releases months later. For durable records, log **source title, section, access date, and version selector**—and use versioned permalinks where the official site provides them.

## 46. Scenario F: Atlas Auto-Upgrade

An Atlas cluster under an auto-upgrade policy receives server binaries and features according to Atlas rollout schedules. Regions and tiers may roll out at different times.

### 46.1. What to Monitor

1. [MongoDB Versions in Atlas](https://www.mongodb.com/docs/atlas/atlas-versions/).
2. [Atlas Changelog](https://www.mongodb.com/docs/atlas/release-notes/changelog/).
3. Release notes of the Server series being rolled out.
4. Driver compatibility and application dependency inventories.
5. Maintenance windows, notifications, and corresponding FCV policies.
6. Application canaries/tests on a representative cluster type.

### 46.2. Do Not Assume Self-Managed Control

Self-managed guides may instruct running FCV commands or restarting `mongod` manually—actions Atlas restricts or manages automatically. Read Atlas-specific procedures before drafting runbooks.

## 47. Compatibility Evidence Record Template

A **manually populated** YAML template—not a runnable config:

~~~yaml
compatibilityReview:
  reviewId: "mongo-upgrade-2026-11-sample"
  asOf: "2026-11-14"
  owner: "<team-or-person>"
  purpose: "MongoDB Server upgrade"
  current:
    server: "<exact-version>"
    fcv: "<actual-fcv>"
    deployment: "<Atlas or self-managed, topology and tier>"
    driver: "<resolved-version>"
    framework: "<resolved-spring-data-version>"
    runtime: "<jdk-or-node-version>"
  proposed:
    server: "<target-version>"
    driver: "<target-version>"
    fcv: "<planned-fcv-if-any>"
  evidence:
    serverReleaseNotes: "https://www.mongodb.com/docs/manual/release-notes/"
    driverCompatibility: "https://www.mongodb.com/docs/drivers/compatibility/"
    springRequirements: "https://docs.spring.io/spring-data/mongodb/reference/preface.html"
    lifecycle: "https://www.mongodb.com/legal/support-policy/lifecycles"
  checks:
    driverServer: "UNKNOWN"
    runtimeDriver: "UNKNOWN"
    frameworkDriver: "UNKNOWN"
    featureAvailability: "UNKNOWN"
    securitySupport: "UNKNOWN"
    rollbackReadiness: "UNKNOWN"
  tests:
    connectivity: "NOT_RUN"
    crud: "NOT_RUN"
    transactions: "NOT_RUN"
    aggregation: "NOT_RUN"
    failover: "NOT_RUN"
    backupRestore: "NOT_RUN"
  decision: "NO_GO_UNTIL_VERIFIED"
~~~

### 47.1. Why Not Pre-Fill PASS?

A template knows nothing about a real deployment yet, so every field starts as `UNKNOWN`/`NOT_RUN`. A sound review record highlights gaps openly so nobody mistakes a template for certification.

### 47.2. Link Deeply to Exact Sections and Versions

In real projects, replace landing-page URLs with deep links to the exact version and section supporting the claim, along with access dates and interpreted footnotes. If source pages later update, reviewers can trace the historical decision.

### 47.3. Evidence Matrices Do Not Require Production Credentials

Matrices can be built from repository lockfiles and existing asset inventories without giving doc authors production DB credentials. When runtime verification is needed, use least-privilege read-only access and keep secrets out of artifacts.

## 48. Markdown Table Template for Pull Requests

| Check | Current | Proposed | Official Source | Evidence Date | Test | Decision |
|---|---|---|---|---|---|---|
| Server EOL | TBD | TBD | Lifecycle | TBD | N/A | UNKNOWN |
| Server release | TBD | TBD | Server notes | TBD | Staging | NEEDS_TEST |
| Driver–Server | TBD | TBD | Client matrix | TBD | Connection+CRUD | UNKNOWN |
| Driver–JDK | TBD | TBD | Java compatibility | TBD | Build/smoke | UNKNOWN |
| Spring Data–driver | TBD | TBD | Spring requirements | TBD | Repository tests | UNKNOWN |
| FCV/rollback | TBD | TBD | FCV/upgrade guide | TBD | Drill | UNKNOWN |
| Atlas availability | TBD | TBD | Atlas versions | TBD | Tier check | UNKNOWN |
| Business features | TBD | TBD | Feature reference | TBD | Integration | UNKNOWN |

Reviewers can comment inline on individual rows, flagging missing evidence and owners. Pair the table with release-note deltas, test plans, rollback criteria, and approval records.

## 49. First-15-Minutes Documentation Lookup Workflow During an Incident

~~~text
0–3 min:
  Identify component, error, exact versions, deployment.
3–6 min:
  Open official reference and select exact version.
6–9 min:
  Check compatibility matrix + footnotes + lifecycle.
9–12 min:
  Check release notes / changelog / known issues.
12–15 min:
  Write 2–3 hypotheses and run minimal safe tests on staging.
~~~

This is a **suggested workflow**, not a rigid SLA. Severe production incidents demand immediate incident response and impact triage rather than passively reading docs on a fixed timer.

### 49.1. Question Sequence

1. Does the Server support the command?
2. Does the driver construct and send it properly?
3. Does framework mapping alter semantics?
4. Are runtime, TLS, and authentication compatible?
5. Have FCV and feature availability gates been met?
6. Does the topology impose constraints?
7. Is this a known bug already documented in a patch or advisory?

## 50. Using Official Documentation Safely Alongside AI

AI assistants and search snippets help orient searches, yet they can mix versions, drop footnotes, or cite stale URLs.

### 50.1. Ask Contextualized Questions

Instead of:

~~~text
Which MongoDB version supports transactions?
~~~

Ask:

~~~text
MongoDB Server 8.0.x Community replica set, FCV 8.0,
Java driver 5.x, JDK 17: what constraints apply to multi-document
transactions, and which official docs and compatibility links verify this?
~~~

### 50.2. Demand Sources and Scope

A trustworthy answer names **the document title, version, deployment type, caveats, and verification date**. Whenever AI cites compatibility cells without official sources, open the original table yourself.

### 50.3. Verify URLs Before Relying on Them

Suggested URLs may 404 or point to `current` for the wrong version. Validate via official site navigation or search; never run destructive admin commands merely because they came "with a citation."

## 51. Common Lookup Pitfalls

| Pitfall | Why It Is Wrong | How to Fix |
|---|---|---|
| Using top Google hit without checking date | Outdated article | Locate official versioned docs |
| Reading `current` docs for older prod | Options/behaviors may not exist | Use version selector |
| Confusing `mongosh` version with Server | Two independent products | Use `db.version()` or `buildInfo` |
| Checking only driver–Server | Ignores JDK/ODM/Framework | Verify remaining axes |
| Treating ⊛ as ✓ | Some features unsupported | Read legend and footnotes |
| Treating blank cell as ✗ | Simply untested/unmarked | Check additional official sources |
| Treating successful connect as certified | CRUD works, features untested | Run integration/load/fault tests |
| Omitting patch version | Misses security fixes | Track exact patch inventory |
| Omitting FCV | New features stay disabled | Read-only FCV check |
| Ignoring deployment type | Atlas and self-managed differ | Check Atlas/platform docs |
| Ignoring EOL | Running unpatched software | Track lifecycle schedules |
| Reading only release headlines | Misses breaking changes/advisories | Read changelog and upgrade guide |
| Copying `setFeatureCompatibilityVersion` from blogs | Downgrade/data risk | Follow versioned official procedure |
| Omitting sources and dates | Decisions cannot be audited | Maintain an evidence ledger |
| Upgrading driver and server untested together | Hard to isolate regressions | Use supported intermediate states |
| Testing standalone for sharded prod | Unrepresentative topology | Use production-like staging |
| Assuming "has backups" means recoverable | Restore never tested | Run restore drills against RPO/RTO |

## 52. Practice A — Finding the Exact-Version Reference Page

An application on Server 8.0.x needs to inspect `$lookup`. Locate:

1. The `$lookup` reference in the exact-version Server Manual.
2. The `Compatibility` and `Behavior` sections.
3. Restrictions when the foreign collection is sharded.
4. Release notes detailing major historical changes.
5. Write a conclusion citing URL and version instead of just "supported."

## 53. Practice B — Server and `mongosh` Versions Differ

In a terminal, `mongosh --version` prints 2.x while `db.version()` prints 8.0.x. Explain why there is no contradiction, which component's docs govern whether a server command runs, and which release notes to open for a shell UI bug.

## 54. Practice C — Interpreting Compatibility Markers

One driver ↔ Server cell shows ⊛; another cell is blank. Explain:

- What is confirmed?
- What is **not** confirmed?
- Should you GO to production if the app needs a new feature in the ⊛ column?
- Which evidence and tests are missing?

## 55. Practice D — Spring Data BOM

A project declares `spring-boot-starter-data-mongodb` without pinning `mongodb-driver-sync`. Show how to inspect the Spring Boot BOM, Spring Data module, and resolved MongoDB driver versions, then look up Spring Data's minimum driver version and tested MongoDB generations.

## 56. Practice E — Server Version vs FCV

A cluster runs upgraded binaries while FCV stays on the prior version per the upgrade path. Why are these two separate facts? Why not bump FCV before burn-in and downgrade review? Provide the **read-only** command to check FCV.

## 57. Practice F — Major/Patch Release Notes

Suppose you plan to upgrade Server from `A.B.3` to `A.B.8`. Design a table covering every patch in that range with columns for CVE/advisory, affected features, fixed issues, operational actions, and regression tests.

## 58. Practice G — Atlas vs Self-Managed

An Atlas tutorial showcases a new feature on a specific tier. Your app runs self-managed MongoDB Community. Can you apply the exact same API? List the sources to verify, deployment constraints, and alternatives if unavailable.

## 59. Practice H — Three-Way Driver Compatibility

A Java project has Server version `S`, driver `D`, and JDK 17. Build a three-way table linking Java driver Server compatibility, Java runtime compatibility, and Spring Data requirements if used. Define an `UNKNOWN` condition that must halt rollout.

## 60. Practice I — EOL Risk

A server runs smoothly yet has passed EOL. An engineer argues "no bugs, so no need to upgrade." Explain technical compatibility vs support lifecycle; list evidence needed to plan replacement and remediation timelines.

## 61. Practice J — Login/TLS Failure After Upgrade

After a Server upgrade, an older driver app fails to connect with authentication handshake errors. Build a lookup sequence across matrix footnotes, driver upgrade guides, release notes, and auth/TLS docs, plus a regression test.

## 62. Practice K — Stable API

A team believes enabling Stable API v1 makes every aggregation stage and every driver version backward-compatible forever. Identify what is wrong with that claim and which docs verify covered commands and options.

## 63. Practice L — Upgrade Matrix

Build a table with rows for Server, FCV, driver, JDK, Spring Data, topology, Atlas tier, Database Tools, `mongosh`, and critical features. Populate columns for current, proposed, official URL, verified date, vendor support, test result, status, and reviewer.

## 64. Practice M — Rollback Checkpoint

An app upgraded Server and enabled a new persisted feature via FCV, then wants to downgrade Server. Why is "swapping binaries back" insufficient? Design a rollback/forward-fix decision accounting for compatibility, data formats, backups, and RPO/RTO.

## 65. Practice N — Tracing a Bug From a Changelog

You find issue ID `SERVER-XXXXX` or `JAVA-YYYYY` in logs or a changelog. Fill out a case sheet:

~~~text
Issue ID:
Product/component:
Affected versions:
Fixed versions/backports:
Our exact version:
Prerequisites to reproduce:
Workaround:
Official release notes link:
Integration test:
Owner + decision:
~~~

Never assign a fabricated issue ID to a real bug; this is a practice template.

## 66. Practice O — Preparing a Production Upgrade

Design a GO/NO-GO review covering:

- Exact version inventory.
- Compatibility intersection + footnotes.
- Security/EOL review.
- Upgrade/downgrade procedures.
- Production-like staging tests.
- Query/transaction/change-stream regressions.
- Backup/restore and RPO/RTO.
- Canary/monitoring/rollback owner.

May a team lacking a restore drill and Spring Data/driver verification GO?

## 67. Practice Answer Guidelines

**A — Exact-version reference:** open the MongoDB Server Manual for your exact Server series, navigate to `$lookup`, read behavior/compatibility/sharding restrictions, and check release notes for noted changes. Conclude with source URL and version instead of quoting `current` snippets blindly.

**B — `mongosh` differs from Server:** they are independently versioned components. `mongosh --version` reports the shell; `db.version()` reports the connected server. Server command support depends on Server/FCV/deployment; shell UI bugs belong in `mongosh`/Compass release notes.

**C — Symbols:** ⊛ indicates partial compatibility per vendor scope; a blank cell is neither certification nor automatic incompatibility. For new features, inspect limitations and plan upgrades/tests—never GO on a passing ping alone.

**D — Dependency resolution:** use `gradle dependencies`/`dependencyInsight` or Maven `dependency:tree`, inspecting the Spring Boot BOM and Spring Data artifacts. Cross-check Spring Data Requirements, Driver–Server, and Driver–JDK matrices instead of trusting memory.

**E — FCV:** binary version defines running server code; FCV controls whether backward-incompatible persisted features are enabled. Inspect with `db.adminCommand({getParameter:1,featureCompatibilityVersion:1})` on a suitable endpoint; never run set-FCV without a runbook.

**F — Patch range:** dedicate one row per patch: number/date, CVE/advisory, affected versions, fixed issues, impacted commands, action, and regression test. Read the official series changelog and upgrade notes, not solely the final patch.

**G — Atlas vs self-managed:** never infer availability from an Atlas tutorial. Check Atlas product/tier docs alongside Server manual/release notes; if Community lacks the feature, choose a managed tier or an alternative design matching business needs.

**H — Three-way check:** driver–server, driver–JDK, and Spring Data–driver/framework all require evidence. `UNKNOWN` arises when a critical feature pair lacks vendor support/tests, runtime version is unknown, or unexplained footnotes remain.

**I — EOL:** binaries keep running without fixes or security patches. Document lifecycle URL/date, exposure, upgrade path, support contracts, backups/rollback, and deadlines; "no visible bugs" is never sufficient justification.

**J — Auth failure:** capture exact server/driver versions, auth mechanism, TLS/JDK, and topology. Check matrix footnotes, driver upgrade guides, and Server changelogs; reproduce in staging and adopt a verified supported driver/Server pair.

**K — Stable API:** protects only the command/option subset defined by that API version. Does not prevent breaking changes in drivers/runtimes/frameworks or guarantee out-of-scope features; verify official Stable API references and driver config.

**L — Matrix:** every component records current/proposed/exact patch, URL, verified date, compatibility statement, test status, and decision. Missing evidence on a hard gate yields `NO_GO` or `NEEDS_TEST`—never an assumed `PASS`.

**M — Rollback:** newer FCVs/features can persist formats incompatible with older binaries; read supported downgrade paths, inspect data/index changes, and verify backups/RPO. When safe downgrade is blocked, evaluate forward-fixes or approved recovery.

**N — Issue:** capture issue ID/component, affected/fixed versions, reproduction prerequisites, official notes link, workaround, and owner. Never assume a patch is applied if the fix landed on another release line.

**O — Production GO:** without verified critical compatibility, a restore drill, and validated rollback against RPO/RTO, the proper status is **NO_GO / CONDITIONAL** per policy and business rules; complete all evidence before deploying.

## 68. Review Questions

**1. Why is a blog post insufficient for upgrade decisions?** — It may reference outdated versions, omit restrictions, and ignore current support policies.

**2. Why track Server and driver versions separately?** — They follow independent release cycles and compatibility constraints.

**3. Does `mongosh` version reflect Server version?** — No.

**4. What does `current` in a doc URL mean?** — Typically the product's current release docs branch, not necessarily what your app runs.

**5. Where do you start for MongoDB Server release notes?** — https://www.mongodb.com/docs/manual/release-notes/

**6. Where do you start for Client Library Compatibility Tables?** — https://www.mongodb.com/docs/drivers/compatibility/

**7. How do changelogs differ from release notes?** — Changelogs detail individual issues; release notes summarize changes, patches, and warnings per release.

**8. Does ✓ in a compatibility table guarantee your app runs cleanly?** — No; topology, feature usage, frameworks, runtimes, and integration tests still matter.

**9. How is ⊛ interpreted?** — Partially compatible per vendor legend.

**10. Does a blank cell automatically mean incompatible?** — No; it may simply be untested or unmarked.

**11. Can an EOL version still connect?** — Yes, yet technical connectivity differs from support/security lifecycles.

**12. Is FCV identical to the Server binary version?** — No.

**13. Can changing FCV affect downgrades?** — Yes, especially once backward-incompatible persisted features are enabled.

**14. Can a Java driver require a minimum JDK runtime?** — Yes; check the Java compatibility chart.

**15. Does meeting Spring Data's minimum driver guarantee every new Server works?** — No; inspect tested versions and the driver–Server matrix.

**16. Does Stable API cover every new command?** — No, only the defined subset.

**17. Can Atlas release notes replace the Server Manual?** — No, their scopes differ.

**18. Can a newer Compass always connect to older Servers?** — Check tool compatibility docs; GUI version is separate from Server.

**19. When must you inspect exact patches rather than major versions alone?** — Security fixes, bug fixes, advisories, regressions, and upgrade planning.

**20. Does a passing `ping` prove transactions are supported?** — No; topology, feature, driver compatibility, and transaction tests are still required.

**21. Can you upgrade any driver to the latest version to fix an old Server?** — No; newer drivers may drop support for EOL Servers.

**22. Does "Tested by Spring Data" differ from "Supported by MongoDB driver"?** — Yes, they represent distinct verification scopes.

**23. Why must compatibility table footnotes always be read?** — They often list critical exceptions and limiting conditions.

**24. Can a new patch release introduce breaking or behavioral changes?** — It can alter behavior or add restrictions/advisories; always read patch notes.

**25. What belongs in an upgrade ticket?** — Exact versions, evidence URLs/dates, compatibility status, test results, runbooks, owners, and rollback plans.

**26. Why is production-like staging essential?** — To exercise realistic topology, traffic, TLS, FCV, data distribution, and framework integrations.

**27. Does having backups guarantee recovery within RTO?** — No; restore drills are required.

**28. Should you test-run set-FCV commands directly in production?** — No; follow official procedures, preflights, approvals, and backup/rollback plans.

**29. Why monitor EOL schedules periodically?** — Support and security policies evolve; running versions eventually lose support.

**30. What does a strong compatibility decision answer?** — Which exact combination, backed by which evidence, verified when, covering which features, and with which open risks.

## 69. Quick Question-to-Source Lookup Table

| What You Need to Know... | Primary Source to Open |
|---|---|
| What is an operator/command's syntax? | Exact-version Server Manual |
| Which release introduced a feature? | Reference `New in version` + Server notes |
| Did a patch fix a bug or CVE? | Server/driver release notes + changelog |
| Which Servers can the Java driver connect to? | Client Library Compatibility Tables |
| Which JDKs does the Java driver run on? | Driver Java Compatibility |
| Which driver does Spring Data require? | Spring Data MongoDB Requirements |
| Which Servers has Spring Data tested? | Spring Data Compatibility Matrix |
| Does an Atlas tier support a feature? | Atlas Docs + Atlas Versions / Changelog |
| What is the current FCV? | Read-only `getParameter` on `mongod` |
| Can we downgrade after upgrading? | Upgrade/Downgrade docs + FCV reference |
| Is a version still supported or EOL? | Software Lifecycle Schedules |
| Was a Compass bug fixed? | Compass Release Notes |
| Are `mongodump`/`mongorestore` compatible? | Database Tools docs / release notes |
| Why does the app still fail despite ✓? | Release notes, framework/runtime, topology + tests |
| Should we enable Stable API? | Stable API reference and driver docs |

## 70. Pre-Guidance Checklist for Learners and Engineers

- [ ] Identified exact product: Server/Atlas/driver/Spring Data/`mongosh`/tools?
- [ ] Recorded exact running versions and patches?
- [ ] Identified self-managed/Atlas tier and topology?
- [ ] Checked version selector/breadcrumb instead of assuming `current`?
- [ ] Verified source is official Manual/driver/framework docs?
- [ ] Read Syntax/Behavior/Restrictions/Compatibility for the command?
- [ ] Checked `New in version` / `Changed in version`?
- [ ] Opened release notes and changelogs for target upgrade versions?
- [ ] Read Important/Warning/Critical Advisory sections and footnotes?
- [ ] Verified the right Driver–Server table?
- [ ] Verified Driver–Runtime/JDK compatibility?
- [ ] Verified resolved Spring Data/Spring Boot dependencies and requirements?
- [ ] Identified current FCV and matching upgrade path?
- [ ] Verified feature availability in your Atlas tier/edition?
- [ ] Checked Server/driver EOL dates and security advisories?
- [ ] Distinguished ✓, ⊛, ✗, and blank cells?
- [ ] Backed every hard compatibility gate with clear evidence?
- [ ] Assigned owners and closure plans to every `UNKNOWN`/`NEEDS_TEST`?
- [ ] Ran integration tests in a representative environment?
- [ ] Tested concurrency, retries, failovers, and transactions if used?
- [ ] Measured query plans/latency when upgrades impact performance?
- [ ] Prepared backups, restore drills, and rollback/FCV decisions?
- [ ] Recorded URLs, check dates, results, and reviewers in PR/ADR?

## 71. Operations Checklist Before a Major Upgrade

1. **Inventory:** Server binaries on every node/router, FCV, driver patches, runtimes, frameworks, and tools.
2. **Policy:** lifecycles, support contracts, security advisories, platform support.
3. **Compatibility:** driver–Server, runtime, framework, features, topology, Atlas tier.
4. **Release delta:** all breaking changes, deprecations, default changes, bug/CVE fixes.
5. **Procedures:** supported upgrade order, prerequisites, FCV and downgrade constraints.
6. **Backups:** recoverability and external data reconciliation aligned with RPO/RTO.
7. **Tests:** unit/integration, queries/aggregations, transactions, change streams, load, failover.
8. **Rollout:** maintenance windows, staged clusters, canary, owners, and monitoring.
9. **Gates:** GO/NO-GO criteria, auto-pause triggers, support escalation.
10. **Postflight:** verify health/versions/FCV, metrics, business invariants, ADR, and inventory updates.

### 71.1. When to Halt

- A mandatory combination shows ✗.
- Resolved framework/driver versions in production are unknown.
- A critical feature lacks support or availability evidence.
- An unaddressed severe security advisory exists.
- Rollback/restore cannot meet RPO/RTO.
- Staging does not reflect topology, or test suites fail.

If constraints are permitted to change, complete business/security/operations review and update plans **before** declaring GO—never silently turn `NO_GO` into `PASS`.

## 72. Principles for Maintaining a Long-Lived Knowledge Base

An internal reference record should contain:

~~~text
Title: MongoDB Compatibility Decision — Project X
Last verified: YYYY-MM-DD
Products: Server / Java Driver / Spring Data / Atlas
Current versions:
Proposed versions:
Deployment topology and FCV:
Features tested:
Official references:
Exceptions/footnotes:
Lifecycle/EOL:
Test evidence:
Decision and approver:
Next review date:
~~~

### 72.1. Separate Durable Principles From Volatile Facts

**Durable:** how to read compatibility matrices, layered thinking, evidence workflows. **Volatile:** latest versions, EOL dates, driver compatibility cells, Server features, Atlas tier availability. Place dynamic data in tables stamped with `last verified` and source links.

### 72.2. Never Keep Old Screenshots as the Sole Source

Old screenshots can fail to reflect current support policies. Whenever making an upgrade decision, reopen the official links to re-verify.

### 72.3. Prioritize Reproducibility

Archive lockfiles, container image digests, redacted MongoDB `buildInfo`/FCV read-only outputs, smoke test scripts, and official links. When regressions hit, the team knows **which exact version combination** was verified.

## 73. Official References Used

These links form a **lookup map**, not a static certification snapshot for every version. Before production decisions, re-check version selectors, footnotes, release dates, and update timestamps.

1. [MongoDB Server Manual](https://www.mongodb.com/docs/manual/) — commands, operators, aggregation, sharding, replication, and transactions.
2. [MongoDB Server Release Notes](https://www.mongodb.com/docs/manual/release-notes/) — release series, patch releases, critical advisories.
3. [MongoDB Versions and Upgrade Paths](https://www.mongodb.com/docs/mongodb-versions/) — version cadence, deployment modes, FCV, and upgrade paths.
4. [setFeatureCompatibilityVersion](https://www.mongodb.com/docs/manual/reference/command/setfeaturecompatibilityversion/) — FCV semantics, preconditions, syntax per Server release.
5. [Client Library Compatibility Tables](https://www.mongodb.com/docs/drivers/compatibility/) — driver–Server and driver–runtime matrices.
6. [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — Java APIs and navigation.
7. [Java Driver Release Notes](https://www.mongodb.com/docs/drivers/java/sync/current/reference/release-notes/) — per-release driver changes.
8. [Upgrade Java Driver Versions](https://www.mongodb.com/docs/drivers/java/sync/current/reference/upgrade/) — breaking changes and dropped server support.
9. [Stable API for Java](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/stable-api/) — scoped versioned API behavior.
10. [Spring Data MongoDB Requirements](https://docs.spring.io/spring-data/mongodb/reference/preface.html) — JDK/framework/driver requirements and tested Server versions.
11. [MongoDB Atlas Docs](https://www.mongodb.com/docs/atlas/) — managed deployments.
12. [MongoDB Versions in Atlas](https://www.mongodb.com/docs/atlas/atlas-versions/) — Atlas release choices and auto-upgrade semantics.
13. [Atlas Release Notes](https://www.mongodb.com/docs/atlas/release-notes/) — Atlas/cloud features and changelogs.
14. [Compass Release Notes](https://www.mongodb.com/docs/compass/release-notes/) — GUI changes and patches.
15. [MongoDB Software Lifecycle Schedules](https://www.mongodb.com/legal/support-policy/lifecycles) — EOL and support tables.
16. [MongoDB Software Support Policy](https://www.mongodb.com/legal/support-policy/software) — support policy definitions.

## 74. Conclusion

Effective MongoDB lookup is a **repeatable engineering skill**, not hunting for a copy-paste snippet that happens to run. Always identify **product, exact version, FCV, deployment topology, driver/runtime/framework, and business goal** before opening documentation. Read the version-matched reference for semantics, release notes/changelogs for what changed, upgrade/downgrade guides for procedures, and compatibility matrices to verify version pairs.

Above all, never confuse **✓ compatibility** with **feature availability**, **framework test coverage**, **active support lifecycle**, or **production correctness**. Upgrade decisions demand concrete evidence across Driver–Server, Driver–Runtime, Framework–Driver, Server–FCV, deployment availability, and lifecycle/security—followed by staging verification, integration/fault tests, and restore/rollback rehearsals.

When every decision carries an **official URL, exact versions, verification date, test results, owner, and GO/NO-GO criteria**, teams avoid bugs from stale docs, skipped upgrade steps, or misread compatibility charts. That forms the foundation for evolving and operating MongoDB applications safely across software releases.
