# Distinguishing APOC Packages, Supportability, and Version Compatibility in Neo4j

## 1. What is APOC and Why Is Understanding the Packages Essential?

**APOC (Awesome Procedures on Cypher)** extends Neo4j with **procedures** and **functions** written in Java that can be called from Cypher. In systems built on a property graph, APOC commonly helps process JSON data, manipulate lists/maps, traverse paths conditionally, import/export data, and automate certain graph processing steps.

A common deployment issue is that documentation or online examples use an `apoc.*` name, yet your machine reports `There is no procedure with the name ...`. The cause may **not be a Cypher syntax error**: the procedure belongs to a different package, has not been installed, lacks execution privileges, no longer exists in the running version, or has been superseded by native Cypher syntax.

In the **APOC and Extensions** chapter, four questions must be answered:

1. How do **APOC Core** and **APOC Extended** differ in packaging, capabilities, maintainers, and support?
2. What rules govern choosing a **compatible APOC version** for a given Neo4j version?
3. How do you verify that a specific procedure/function is **actually available in your environment**?
4. When upgrading Neo4j/Cypher, what must be checked so Java Driver or Spring Data Neo4j applications do not break?

> Scope: this article targets Neo4j 5.x and Neo4j releases following the `2025.MM`/`2026.MM` calendar schedule. Some legacy Neo4j 4.x naming is mentioned solely to explain migration.

## 2. APOC Core and APOC Extended: Two Complementary Libraries

Starting with **Neo4j 5**, APOC was split into two separate projects/library groups. The old **APOC Full** "all-in-one" bundle no longer applies to Neo4j 5+.

| Criterion | APOC Core | APOC Extended |
| --- | --- | --- |
| Maintainer | Neo4j product/engineering | Community and contributors |
| Official Support | **Yes**, within Neo4j's APOC Core support scope | **No** official Neo4j product support; best-effort maintenance |
| Purpose | Common procedures/functions for graphs, strings, maps, JSON, paths, import/export, and batch processing | More specialized capabilities, external integrations, niche formats/technologies, and optional dependencies |
| How to Obtain | Usually bundled in the server distribution's `labs` directory; toggleable via Neo4j Desktop/Docker; allowed subset on Aura | Installed separately from compatible releases; primarily for environments allowing server plugin installation |
| JAR File | `apoc-<version>-core.jar` or distribution-specific JAR name | `apoc-<version>-extended.jar` or distribution-specific JAR name |
| Relationship Between Packages | Does not require Extended to run Core features | **Does not bundle all of Core**; to use Core features, ensure Core is also present |
| Troubleshooting Process | Consult APOC Core docs and product support channels | Consult Extended docs, releases, and community issues; proactively assess operational risk |

**Do not infer the package from the `apoc.` prefix alone.** Both libraries register names starting with `apoc.`. Always look up a procedure in the **catalog for the exact package and version**.

### 2.1. Examples of Core Features

The following examples are documented in **APOC Core** (availability may still be constrained by privileges, edition, environment, or version):

| Category | Function/Procedure | Purpose |
| --- | --- | --- |
| Conversion | `apoc.convert.toJson(value)` | Converts Cypher data into a JSON string |
| Graph Querying | `apoc.path.expandConfig(startNode, config)` | Traverses relationships/paths with filters and uniqueness rules |
| JSON Import | `apoc.load.json(...)` | Reads JSON from permitted sources |
| CSV Export | `apoc.export.csv.all(...)` | Exports graph data in CSV format |
| Batch Processing | `apoc.periodic.iterate(...)` | Splits operations into batches; note deprecation status in newer Cypher |
| Inspection | `apoc.help(...)` and `apoc.version()` | Looks up API listings and library version |

**Specific note:** `apoc.export.csv.all` and `apoc.load.json` are **not automatically Extended** simply because they involve import/export. The Core catalog actually includes these procedures.

### 2.2. Examples of Extended Features

Some names appearing in **APOC Extended** documentation:

- `apoc.export.parquet.all` and `apoc.export.parquet.*` variants: export in Parquet format.
- `apoc.mongodb.get.byObjectId`: MongoDB integration.
- `apoc.bolt.execute`: interacts over the Bolt protocol with another database in compatible scenarios.
- Various `apoc.nlp.aws.*`, `apoc.nlp.azure.*`, `apoc.nlp.gcp.*` procedures: NLP provider integrations.

These are **examples for package identification**, not a guarantee that every name exists in every Extended release. Each external integration also requires its own dependencies, endpoints, configuration, permissions, and credentials. Extended documentation is published per branch/version; check the catalog directly for your deployed release.

### 2.3. Neither Core nor Extended Equals GDS

**Neo4j Graph Data Science (GDS)** is a separate product/plugin providing graph algorithms and specialized analytics. Having path traversal/search utilities in APOC does not make APOC equivalent to GDS. Similarly, the **Java Driver** and **Spring Data Neo4j** are tools for connecting, mapping, and executing Cypher from applications; they do not install APOC onto the server.

## 3. Version Compatibility: Checking Neo4j, APOC, and Cypher Together

### 3.1. Version Matching Rules

APOC relies on internal Neo4j APIs, so pairing an incompatible JAR version can cause startup warnings or prevent procedures from loading.

| Neo4j Line | APOC Verification Rule | Illustration |
| --- | --- | --- |
| Neo4j 5.x | Pick an APOC line on the same `5.x` branch and the **exact version pair listed in the compatibility matrix** | Neo4j `5.26.x` needs an APOC release published as compatible with `5.26.x` |
| Calendar-versioned Neo4j `YYYY.MM` | Match the **release year and month**; APOC's patch number does not have to equal Neo4j's patch number | Neo4j `2026.10.x` uses APOC released for `2026.10`, e.g., `2026.10.2` |
| Neo4j 4.4 | Use documentation and artifacts specifically for 4.4 | Do not copy a 4.4 JAR directly into Neo4j 5/2026 |

**Do not apply a naive "same major version works" rule:** `5.15` and `5.26` share major version 5 yet cannot be assumed compatible. Conversely, Neo4j patch and APOC patch numbers do not have to match if the compatibility matrix confirms they belong to the same release line.

Minimum verification steps:

1. Identify the Neo4j version running on the **actual server**, not just the client Java library version.
2. Choose **Core** or **Extended** according to the list of procedures your application uses.
3. Read the compatibility matrix for **both packages** and release notes, including special Extended dependencies.
4. Check the active Cypher syntax (`Cypher 5` or `Cypher 25`), as an API may exist at runtime yet be deprecated or unavailable in the default language version.
5. Load the library, restart Neo4j, and verify with `SHOW PROCEDURES`, `SHOW FUNCTIONS`, a read smoke test, and startup logs.

### 3.2. Difference Between Library Version and Language Version

In newer Neo4j releases, a DBMS can support choosing **Cypher 5** or **Cypher 25**. This is a **distinct** concern from whether the APOC JAR matches the Neo4j version.

Several previously useful Core APIs now have Cypher equivalents and have been marked **deprecated**. For example:

| Former APOC API | Status / Guidance in Newer Cypher |
| --- | --- |
| `apoc.coll.toSet(list)` | Deprecated in Cypher 25; prefer `coll.distinct(list)` |
| `apoc.periodic.iterate(...)` | Deprecated as of Neo4j 2026.04/Cypher 25; consider `CALL { ... } IN CONCURRENT TRANSACTIONS` |
| `apoc.when(...)` | Deprecated in Cypher 25; review corresponding Cypher conditional query syntax |

Example illustrating the difference between **legacy syntax** and **Cypher 25 syntax**:

```cypher
// Way APOC used to deduplicate values:
RETURN apoc.coll.toSet([1, 1, 2, 3, 2]) AS ids;
```

```cypher
CYPHER 25
RETURN coll.distinct([1, 1, 2, 3, 2]) AS ids;
```

Both illustrate list deduplication; pick syntax according to your Cypher version and deprecation status. **Deprecated does not mean "already deleted."** Some APIs absent from Cypher 25 may still work via `CYPHER 5` on supporting releases; check compatibility notes rather than assuming a single fallback mechanism applies to every procedure.

### 3.3. Upgrade Version Checklist

Before every upgrade, record a matrix:

| Component | Record |
| --- | --- |
| Neo4j Server | Version, edition, deployment type (server/Desktop/Docker/Aura), cluster or standalone |
| APOC Core | Present or not, JAR version, list of functions/procedures in use |
| APOC Extended | Present or not, JAR version, external dependencies, and features in use |
| Cypher | Default version and queries explicitly declaring `CYPHER 5`/`CYPHER 25` |
| Security | `allowlist`, `unrestricted`, role execution privileges, and I/O policies |
| Application | Java Driver, Spring Data Neo4j, queries, and tests using APOC |

You cannot conclude "the plugin is compatible" merely because Neo4j starts up; you must still verify that business procedures are invoked with the **exact signature and execution privileges**.

## 4. How to Confirm APOC Is Actually Present in the Database

Run the following read-only statements via Neo4j Browser, cypher-shell, or the Java Driver, using an account permitted to view the required metadata.

### 4.1. Check the Neo4j version

```cypher
CALL dbms.components()
YIELD name, versions
RETURN name, versions;
```

The output reveals the DBMS components and versions. Never use a client library version to infer the server version.

### 4.2. Check the APOC version

```cypher
RETURN apoc.version() AS apocVersion;
```

If this reports an unknown function, check first whether **Core is loaded and permitted**; this statement is not evidence of whether Extended is installed.

### 4.3. List registered procedures and functions

```cypher
SHOW PROCEDURES
YIELD name
WHERE name STARTS WITH 'apoc.'
RETURN name
ORDER BY name;
```

```cypher
SHOW FUNCTIONS
YIELD name
WHERE name STARTS WITH 'apoc.'
RETURN name
ORDER BY name;
```

These two lists differ because a **procedure** is invoked with `CALL` whereas a **function** is used inside an expression. Check both; sometimes the API an application needs is a function rather than a procedure.

### 4.4. Look up signatures and usage examples

```cypher
CALL apoc.help('path');
```

```cypher
CALL apoc.help('convert');
```

`apoc.help` lets you inspect available APOC entries and signatures when permitted. An example in newer docs may have different input parameters than older docs; always verify the **actual signature** against your server version.

> Seeing a procedure name in documentation does not prove it is installed or that the current role has permission to run it. Conversely, a name missing from `SHOW PROCEDURES` could be due to an unloaded JAR, a restrictive allowlist, or permission-scoped visibility; cross-check logs and configuration.

## 5. Installing APOC Across Environments

### 5.1. Self-managed Neo4j Server (binary/tar/zip/package)

For Neo4j distributions shipping with APOC Core, the JAR is typically located in `$NEO4J_HOME/labs`. Conceptual workflow:

1. Identify the Neo4j version and corresponding Core release.
2. Copy the **compatible Core JAR** from `labs` to `plugins`. Do not copy unrelated JARs.
3. If Extended is genuinely needed, download the **matching release line's Extended JAR** from the designated release; check dependencies for specialized features.
4. Configure procedure execution and file I/O permissions according to business requirements.
5. Restart Neo4j, inspect logs, and run the verification queries from Section 4.

Example **reference directory structure** (filenames vary by release):

```text
NEO4J_HOME/
├── conf/
│   ├── neo4j.conf
│   └── apoc.conf        # create only when APOC configuration is needed
├── labs/
│   └── apoc-<compatible-version>-core.jar
└── plugins/
    ├── apoc-<compatible-version>-core.jar
    └── apoc-<compatible-version>-extended.jar  # only when needed
```

**Do not keep multiple Core JARs of different versions in `plugins`**, nor mix legacy APOC Full JARs with newer Core/Extended JARs. Doing so easily causes duplicate registration or Java classloading errors at startup. When upgrading, stop the DBMS, swap the JARs as planned, then restart and verify.

### 5.2. Neo4j Desktop

In Neo4j Desktop, the **Plugins** tab allows installing **APOC Core** for supported DBMSs/projects. Per current Extended documentation, **APOC Extended is not installed via the APOC button on the Plugins tab**; you must place the compatible JAR into the appropriate DBMS's `plugins` directory and restart.

Do not assume clicking "Install APOC" gives you all Extended features.

### 5.3. Neo4j Docker

The Docker image supports declaring plugins via the `NEO4J_PLUGINS` environment variable. Example **development environment** configuration using both packages:

```yaml
services:
  neo4j:
    image: neo4j:2026.10.2
    environment:
      NEO4J_PLUGINS: '["apoc", "apoc-extended"]'
    ports:
      - "7474:7474"
      - "7687:7687"
    volumes:
      - ./neo4j-data:/data
      - ./neo4j-plugins:/plugins
```

This is a **Compose snippet illustrating the plugin mechanism**; it lacks full authentication, backup, and network policies required for production. `NEO4J_PLUGINS` can download/install plugins at container startup and is handy for testing; for production, **pin compatible images and JARs**, verifying artifacts, checksums, and configuration rather than relying on dynamic downloads on every startup.

**Check the JARs inside the container right away**: declaring only `["apoc-extended"]` does not guarantee Core is included. Declaring only `["apoc"]` does not include Extended procedures.

### 5.4. Neo4j AuraDB

APOC Core **is available in AuraDB within the feature set permitted by the managed service**. Aura users typically cannot copy JARs into `plugins` or edit `neo4j.conf`/`apoc.conf` as on a self-managed server.

When deploying on Aura:

- Consult the list of APOC features **supported by Aura**, rather than treating the general Core or Extended catalog as guaranteed.
- Use `SHOW PROCEDURES`/`SHOW FUNCTIONS` to verify what the current deployment and account can see.
- Do not assume you can use local server filesystem import/export or manually install Extended.
- If a required procedure is unavailable, consider standard Cypher, the Java Driver, or application-side processing; do not make Extended a hard dependency when the service does not permit installing it.

## 6. Configuration: Separating `neo4j.conf` from `apoc.conf`

Since Neo4j 5, `apoc.*` settings belong in **`apoc.conf`** (in the same directory as `neo4j.conf`) or in environment variables, rather than being written directly into `neo4j.conf`.

| Purpose | Typical Location | Example |
| --- | --- | --- |
| Decide which procedures/functions are **loaded** | `neo4j.conf` | `dbms.security.procedures.allowlist` |
| Decide which procedures execute with **unrestricted privileges** | `neo4j.conf` | `dbms.security.procedures.unrestricted` |
| Control whether APOC can **read local files** | `apoc.conf` | `apoc.import.file.enabled` |
| Control whether APOC can **write local files** | `apoc.conf` | `apoc.export.file.enabled` |
| Restrict read paths to Neo4j's import directory | `apoc.conf` | `apoc.import.file.use_neo4j_config` |
| Block/filter outbound URL access | DBMS config, network policies, corresponding permissions | SSRF prevention, restricting reachable addresses/domains |

Example configuration keeping local file I/O restricted by default:

```properties
# conf/apoc.conf
apoc.import.file.enabled=false
apoc.export.file.enabled=false
apoc.import.file.use_neo4j_config=true
```

**Only enable file read/write privileges when genuinely needed.** Many JSON/CSV procedures access the filesystem of the **Neo4j server**, not the machine running the Java application. Likewise, fetching data via URLs generates outbound HTTP requests from the server and must be restricted to prevent server-side request forgery (SSRF).

### 6.1. Difference between `allowlist` and `unrestricted`

- `dbms.security.procedures.allowlist` specifies which procedures/functions are **allowed to be loaded/registered**. The default may allow all, but production environments should usually narrow it down.
- `dbms.security.procedures.unrestricted` allows selected procedures to access internal APIs that are otherwise sandboxed. **Not every APOC procedure needs this privilege.**
- Role/user permissions for calling procedures (such as execute privileges) form an additional control layer that cannot be replaced by the two settings above.

Example illustrating how to narrowly allow only the intended API groups:

```properties
# conf/neo4j.conf — example to be tailored per application
dbms.security.procedures.allowlist=apoc.version,apoc.help,apoc.convert.*,apoc.path.*
```

Where those APIs do not require unrestricted privileges, **do not** add `apoc.*` to `unrestricted`. If documentation for a specific procedure explicitly requires elevated access, grant **only the minimal exact name/pattern** after reviewing its behavior and risk.

> Avoid blindly copying `dbms.security.procedures.allowlist=apoc.*` and `dbms.security.procedures.unrestricted=apoc.*` into production. "Making every procedure runnable" grants a much broader privilege surface than business logic needs.

### 6.2. Gap Between "Successfully Installed" and "Permitted to Execute"

A procedure may exist in the JAR yet still:
- Fail to register due to `allowlist`.
- Fail to initialize due to missing dependencies.
- Be denied due to missing account execute privileges.
- Lack permission to read files, call network endpoints, or access required internal APIs.
- Be supported only on self-hosted servers while deployed on Aura.
- Be removed upon switching Cypher versions.

Therefore, acceptance testing must verify the **listing, signature, and an actual test query** under the real application account.

## 7. Hands-On Examples with APOC Core and Cypher

The following examples run on a test database with **APOC Core** installed and permission to invoke `apoc.convert.toJson` and `apoc.path.expandConfig`. Extended is not required.

### 7.1. Creating a small, repeatable graph

```cypher
UNWIND [
  {userId: 'u001', userName: 'An', companyId: 'c001', companyName: 'Acme'},
  {userId: 'u002', userName: 'Bình', companyId: 'c001', companyName: 'Acme'},
  {userId: 'u003', userName: 'Chi', companyId: 'c002', companyName: 'Northwind'}
] AS row
MERGE (u:User {id: row.userId})
SET u.name = row.userName
MERGE (c:Company {id: row.companyId})
SET c.name = row.companyName
MERGE (u)-[:MEMBER_OF]->(c);
```

Graph representing user membership in companies:

```text
(u001:User) ---MEMBER_OF---> (c001:Company)
(u002:User) ---MEMBER_OF---> (c001:Company)
(u003:User) ---MEMBER_OF---> (c002:Company)
```

With the sample data on a clean database, there are 3 `User` nodes, 2 `Company` nodes, and 3 `MEMBER_OF` relationships.

### 7.2. Transforming data with a Core function

```cypher
MATCH (u:User {id: 'u001'})-[:MEMBER_OF]->(c:Company)
RETURN apoc.convert.toJson({
  userId: u.id,
  userName: u.name,
  companyId: c.id
}) AS jsonText;
```

`apoc.convert.toJson` returns a **JSON string**, which differs from a Cypher map. If the Java Driver or Spring Data Neo4j only needs a key/value structure, return a **plain Cypher map**:

```cypher
MATCH (u:User {id: 'u001'})-[:MEMBER_OF]->(c:Company)
RETURN {
  userId: u.id,
  userName: u.name,
  companyId: c.id
} AS resultMap;
```

Choose the **non-APOC** option when you do not actually need a JSON string serialized on the server. That reduces plugin coupling and avoids unnecessary serialize-then-parse overhead in the Java layer.

### 7.3. Traversing relationships with a Core procedure

```cypher
MATCH (u:User {id: 'u001'})
CALL apoc.path.expandConfig(u, {
  relationshipFilter: 'MEMBER_OF>',
  minLevel: 1,
  maxLevel: 1,
  uniqueness: 'NODE_GLOBAL'
})
YIELD path
RETURN [node IN nodes(path) | node.id] AS nodeIds;
```

For a single-hop relationship example, plain Cypher is sufficient:

```cypher
MATCH (u:User {id: 'u001'})-[:MEMBER_OF]->(c:Company)
RETURN [u.id, c.id] AS nodeIds;
```

`apoc.path.expandConfig` shines when you need flexible **filtering by relationship types, directions, labels, hop counts, and traversal/uniqueness rules**. For a fixed single pattern, plain Cypher is clearer and reduces plugin coupling. This procedure also has safety restrictions in the **parallel runtime**, so do not blindly switch all queries to parallel mode for speed.

### 7.4. Which package does an operation require?

| Business Requirement | Starting Point | When to Choose APOC |
| --- | --- | --- |
| Look up a node by ID with a constraint | `MATCH (u:User {id: $id})` | Usually no APOC needed |
| Find paths along a fixed pattern | `MATCH p = (...)-[:REL*1..3]->(...)` | When special traversal/filter/uniqueness is needed and compatibility is verified |
| Return a DTO to Java | `RETURN { ... }` or multiple columns | `apoc.convert.toJson` when a server-side JSON string is genuinely needed |
| Standard CSV import | `LOAD CSV`, `CALL { ... } IN TRANSACTIONS` | APOC if another format is needed or the workflow already accepts the dependency |
| Export the whole graph to CSV | Check formatting needs and file permissions | `apoc.export.csv.all` is in Core, subject to file/stream conditions |
| Export to Parquet | Check ETL tools or external processing | Some Extended releases include `apoc.export.parquet.*`; verify release and permissions |
| Query MongoDB from Neo4j | Evaluate integration flow in app/ETL | Extended has related procedures, depending on environment and dependencies |
| Complex graph analytics | Cypher, appropriate algorithms | Distinguish APOC from GDS; they are not interchangeable |

## 8. Integrating with the Java Driver and Spring Data Neo4j

**APOC runs on the Neo4j Server**, while the Java Driver sends Cypher over the Bolt protocol. Adding `org.neo4j.driver` or Spring Data Neo4j dependencies to `pom.xml`/**Gradle** does **not** mean the server has APOC Core/Extended installed.

### 8.1. Java Driver: checking APOC at application startup

Suppose the application has an `org.neo4j.driver.Driver driver`:

```java
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {

    String version = session.executeRead(tx ->
        tx.run("RETURN apoc.version() AS version")
          .single()
          .get("version")
          .asString()
    );

    System.out.println("APOC Core version: " + version);
}
```

This is a **smoke test for function availability**. Do not treat the returned string as proof that every procedure is authorized. Add checks for **each procedure your application depends on**; production environments should log an error and disable dependent features if an API is missing.

Example when a service needs a map converted to JSON server-side:

```java
String cypher = """
    MATCH (u:User {id: $id})
    RETURN apoc.convert.toJson(properties(u)) AS json
    """;
```

Use **parameter `$id`**; never concatenate user data into Cypher code. With Extended—especially procedures executing dynamic Cypher or calling external endpoints—strictly control inputs and DB account privileges.

### 8.2. Spring Data Neo4j

In Spring Data Neo4j:

- `@Query` and `Neo4jClient` can invoke APOC procedures/functions **if the server supports them**; the framework does not bundle plugin JARs.
- Queries written solely in plain Cypher are usually easier to port between self-hosted Neo4j and Aura.
- If a procedure returns a `MAP`, `LIST`, `NODE`, or `score`, DTO/projection choices or mappings must match the actual return type.
- A write procedure does not automatically become "read-only" just because a Java method is named `find...`. You must determine the proper **transaction mode**, retry semantics, and execution privileges.
- Migration tests should run against the **exact Neo4j version, exact APOC JAR, and exact Cypher version** to be deployed.

A Java application may start up cleanly only to fail on the first request calling `apoc.path.expandConfig` because the plugin wasn't loaded. Hence, smoke tests should run early in the deployment pipeline.

## 9. Upgrade, Testing, and Troubleshooting Process

### 9.1. Neo4j + APOC upgrade checklist

1. **Inventory:** find every `apoc.*` reference in Java/Spring code, Cypher scripts, and jobs; record Core vs. Extended, signature, and target version.
2. **Select releases:** determine Neo4j server/edition and consult the exact Core and Extended compatibility matrices.
3. **Review Cypher:** check deprecated/removed APIs in Cypher 25; prefer migrating to plain Cypher where clear equivalents exist.
4. **Test on staging:** load compatible JARs, restart the server, inspect logs and `SHOW PROCEDURES`/`SHOW FUNCTIONS`.
5. **Verify permissions:** run under the actual application role, testing allowed read, write, and import/export operations.
6. **Business validation:** re-run node creation, traversal, import, and JSON queries on a representative dataset; compare before/after results.
7. **Deploy with rollback:** back up, retain exact artifact/version inventories, restart cleanly, and monitor procedure registration errors and post-upgrade latency.

### 9.2. Common troubleshooting matrix

| Symptom | Possible Cause | Verification Steps |
| --- | --- | --- |
| `Unknown function 'apoc.version'` | Core not loaded, invalid JAR, allowlist, or restricted permissions | Check `plugins`/`labs`, logs, `SHOW FUNCTIONS` |
| `There is no procedure with the name ...` | Wrong package, procedure renamed/removed, missing JAR, or unloaded config | Check Core/Extended for exact release; `SHOW PROCEDURES` |
| Logs report APOC/Neo4j incompatibility | JAR taken from a different release line | Check compatibility matrix, swap JAR, restart |
| Procedure listed but user cannot run it | Missing execute privilege, unrestricted setting, or system role permission | Inspect roles and procedure-specific configuration |
| `apoc.load.json(file:///...)` denied | Local file reading disabled; disallowed source path | Check `apoc.conf`, import directory, and file permissions |
| `apoc.export.parquet.*` not found | Extended not installed or missing in that Extended build | Check Extended catalog and `SHOW PROCEDURES` |
| "Install APOC" in Desktop lacks Extended features | Install button only adds Core to the DBMS | Manually install Extended if environment supports it |
| Blocked when running on Aura | Service exposes only an approved APOC subset | Check Aura supported list, adjust workflow |
| After Cypher 25 upgrade old procedure warns deprecation/removal | Cypher added standard syntax and updated APIs | Read release notes, use Cypher equivalent or appropriate language mode |
| Runtime error calling external integration | Missing dependency, endpoint, or configuration/credentials | Check logs and procedure docs for the exact release |
| Slow query using `apoc.path.expandConfig` | Overly broad traversal, suboptimal `uniqueness`/`bfs`/`limit` | Cap depth, examine fan-out, validate correctness against Cypher |

### 9.3. Misconceptions to Avoid

**"Installing Extended means you also get Core."** False under Neo4j 5+ packaging: the two JARs are complementary feature sets.

**"APOC is officially supported by Neo4j, so every Extended procedure has official support."** Official support applies to **Core**; Extended is community-maintained.

**"The procedure name appears in the latest docs, so my older Neo4j server can run it."** Always consult **version-specific docs**, signatures, and runtime listings.

**"All `apoc.*` names share the same access level."** Procedures may be read-only, write-capable, HTTP-calling, or file-touching; never grant unrestricted access wholesale.

**"If `SHOW PROCEDURES` lists the procedure, the app is guaranteed to work."** Account privileges, dependencies, network/filesystem rules, Cypher version, and query logic still apply.

**"Once APOC is installed, use APOC for every query."** Standard Cypher is usually better when it satisfies the same need with fewer dependencies; use APOC for **genuinely needed capabilities**, not merely shorter syntax.

## 10. Self-Check Exercises

1. Suppose a system runs Neo4j `2026.10.x`. Identify the APOC version line to inspect. Explain why comparing only major versions or requiring identical patch numbers are both flawed rules.
2. A legacy example uses `apoc.export.csv.all`. Does this API belong to Core or Extended in the current catalog? Contrast it with `apoc.export.parquet.all`.
3. In Neo4j Desktop, you clicked the `APOC` install button, yet `apoc.mongodb.get.byObjectId` is missing. Propose a logical troubleshooting sequence.
4. Write three queries to check the **Neo4j version**, **APOC version**, and **list of APOC procedures** in a running DBMS.
5. Compare the pros and cons of `apoc.convert.toJson(map)` versus returning a map directly from Cypher to the Java Driver.
6. An application on AuraDB wants to use an Extended procedure that depends on local files. Why can't simply adding a Maven dependency solve this?
7. Find a use case currently calling `apoc.coll.toSet` and rewrite it in Cypher 25. Describe how to verify functional equivalence.
8. Propose a minimal smoke test suite when upgrading Neo4j/APOC for a Java/Spring service containing JSON queries, path expansions, and batch processing.

## 11. Key Takeaways

- **APOC Core** is officially supported by Neo4j; **APOC Extended** is a community project adding specialized capabilities and separate dependencies.
- In Neo4j 5+, **Extended does not include Core**, and the legacy single-JAR "APOC Full" model is no longer used.
- Match JARs **compatible with your Neo4j version** via the **compatibility matrix**, especially for `5.x` lines and `YYYY.MM` calendar releases; also verify **Cypher 5/Cypher 25**.
- `SHOW PROCEDURES`, `SHOW FUNCTIONS`, `apoc.version()`, and `apoc.help(...)` confirm what is loaded, but you must still test **execution privileges and real behavior**.
- Separate **DBMS config (`neo4j.conf`)**, **APOC config (`apoc.conf`)**, role permissions, and file/network policies.
- Prefer **plain Cypher** when sufficient; adopt APOC only when it provides needed functionality and support, compatibility, security, and performance are verified.
- **Java Driver/Spring Data Neo4j do not install APOC on the server**; configure, upgrade, and smoke-test plugins on the target deployment.

### Official References

- [Neo4j APOC Core — Introduction](https://neo4j.com/docs/apoc/current/introduction/)
- [Neo4j APOC Core — Installation and Compatibility Matrix](https://neo4j.com/docs/apoc/current/installation/)
- [Neo4j APOC Core — Procedures & Functions](https://neo4j.com/docs/apoc/current/overview/)
- [Neo4j APOC Core — Migration Guide](https://neo4j.com/docs/apoc/current/migration-guide/)
- [Neo4j APOC Core — Additions, Deprecations, Removals and Compatibility](https://neo4j.com/docs/apoc/current/deprecations-and-additions/)
- [Neo4j APOC Core — Security Guidelines](https://neo4j.com/docs/apoc/current/security-guidelines/)
- [Neo4j APOC Core — Configuration Options](https://neo4j.com/docs/apoc/current/config/)
- [Neo4j APOC Extended — Introduction](https://neo4j.com/labs/apoc/2025/introduction/)
- [Neo4j APOC Extended — Installation](https://neo4j.com/labs/apoc/2025/installation/)
- [Neo4j APOC Extended — Procedures & Functions](https://neo4j.com/labs/apoc/2025/overview/)
- [Neo4j Operations Manual — Docker Plugins](https://neo4j.com/docs/operations-manual/current/docker/plugins/)
- [Neo4j Aura — APOC Availability](https://neo4j.com/docs/aura/platform/apoc/)
