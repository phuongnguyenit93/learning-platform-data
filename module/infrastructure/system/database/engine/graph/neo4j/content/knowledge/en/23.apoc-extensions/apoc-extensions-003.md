# Installation, Allowlist Configuration, and Procedure Privilege Restrictions

## 1. What is APOC and Why Must Privileges Be Controlled?

**APOC** (*Awesome Procedures On Cypher*) is an extension library for Neo4j providing **procedures** and **user-defined functions** called directly from Cypher. They assist with tasks such as string processing, data transformation, reading external sources, and certain graph operations tasks. APOC complements the built-in capabilities of **Cypher** rather than replacing the **property graph** model consisting of nodes, relationships, properties, indexes, and constraints.

In the **DATABASE_ENGINE_GRAPH_NEO4J** module, systems may invoke APOC from Neo4j Browser, the **Java Driver**, or **Spring Data Neo4j**. Precisely because it can be called across multiple application layers, installing the library must accompany a policy of **loading only needed features, granting only needed execution privileges, and enabling external resource access only when genuinely required**.

This lesson belongs to the **APOC and Extensions** chapter and focuses on three questions:

1. How to install APOC Core/Extended appropriately for the environment and **Neo4j version**?
2. How do **dbms.security.procedures.allowlist** and **dbms.security.procedures.unrestricted** differ?
3. How to restrict **EXECUTE PROCEDURE/FUNCTION privileges per role**, while controlling impact on files, network, and data?

**Principle:** having a procedure present in a JAR does not mean it is loaded; being loaded does not mean a user is allowed to execute it; being allowed to execute it does not mean the user is permitted to read/write arbitrary data.

## 2. Distinguishing APOC Core, APOC Extended, and Plain Cypher

Since Neo4j 5, APOC has been clearly split into two parts:

| Option | Nature | When to Use | Operations |
|---|---|---|---|
| **Built-in Cypher** | Neo4j's query language, requiring no APOC JAR | Queries with an equivalent Cypher feature | Fewer dependencies; prefer whenever it meets requirements |
| **APOC Core** | The portion of APOC officially supported by Neo4j since Neo4j 5 | Data transformations, utility functions, certain graph procedures | Packaged for the matching Neo4j release; often bundled in the distribution but requires enabling |
| **APOC Extended** | Community-maintained additions, including external integrations/dependencies | Only when Core/Cypher cannot fulfill the need | Download separate JAR, verify versions/dependencies, and assess risks more thoroughly |

Do not assume that **Core + Extended** is always a single JAR, or that every procedure shown in old APOC docs still lives in current Core. Several APOC features now have Cypher equivalents and may be **deprecated** or removed across releases. During upgrades, inspect the procedure catalog, migration guide, and change notices for the exact version.

### 2.1. Matching Neo4j and APOC versions

APOC uses internal Neo4j APIs, so **incompatible versions can prevent the plugin from loading** or cause startup failures:

- For traditional **Neo4j 5.x** branches, match Neo4j and APOC **major.minor** versions per the published compatibility matrix.
- For modern **year.month** Neo4j branches (e.g., 2025.06 or 2026.10), pick APOC with the same **year and month**; patch numbers may differ if compatibility documentation permits.
- **Core** and **Extended** must each match the proper release; never install two mismatched JARs merely because both filenames contain APOC.
- When upgrading Neo4j, upgrade/re-verify APOC **before** putting the instance into service.

Do not treat a JAR filename from documentation examples as a universal version across all systems. Verify the actual server version, compatibility docs, and published artifacts before deployment.

## 3. Installing APOC by Environment

### 3.1. Self-managed Neo4j Server

For Neo4j distributions bundling **APOC Core** in the **labs** directory, the typical process is:

1. Identify the Neo4j server version and select the matching APOC version.
2. Copy the APOC Core JAR from **$NEO4J_HOME/labs** to **$NEO4J_HOME/plugins**; or download the matching JAR from the official release source if required by your environment.
3. If **APOC Extended** is needed, place the compatible Extended JAR and required dependencies from the publisher into **plugins**; do not treat Extended as a replacement for Core.
4. Configure the allowlist, execution privileges, and APOC options per Sections 4–6 below.
5. Restart Neo4j via your environment's service manager, then verify the procedure/function listing.

In a **cluster**, ensure all servers that may receive queries have the same set of JARs and compatible configuration. One server having the plugin while another lacks it causes intermittent failures when routing directs connections.

**Note:** only administrators should be allowed to modify the plugins/config directories or restart the service. Never download JARs from untrusted origins or allow application OS accounts to write to **plugins**.

### 3.2. Neo4j Desktop

In **Neo4j Desktop**, open the managed DBMS, go to the **Plugins** tab, choose to install **APOC**, and restart when prompted. The APOC entry in this UI normally installs **APOC Core**. To use **Extended**, follow manual JAR installation instructions for your Desktop/DBMS version, then verify loading.

Desktop is convenient for learning, but **default development permissions are not a production security configuration**. Whether invoked from Browser or a Java application, procedures execute on the Neo4j server with whatever privileges the server permits.

### 3.3. Neo4j Docker

The Neo4j Docker image provides the **NEO4J_PLUGINS** variable accepting a JSON list, such as **["apoc"]** for Core. Minimal Docker Compose example for a **development environment**:

~~~yaml
services:
  neo4j:
    image: neo4j:2026.10.2
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      NEO4J_AUTH: "neo4j/${NEO4J_PASSWORD}"
      NEO4J_PLUGINS: '["apoc"]'
      NEO4J_dbms_security_procedures_allowlist: "apoc.version,apoc.text.clean,apoc.help"
    volumes:
      - neo4j_data:/data
volumes:
  neo4j_data:
~~~

**Before running**, set the **NEO4J_PASSWORD** environment variable to a sufficiently strong test password; do not commit passwords to Git. Version **2026.10.2** is illustrative; replace it with your project's tag and check compatibility.

The **NEO4J_PLUGINS** mechanism downloads/configures plugins on container startup and is intended by Neo4j docs for **development**. For production, pin plugin versions, verify JAR origins, and provide **/plugins** via an image or managed volume rather than relying on dynamic downloads at every container start.

If using **Extended**, Docker supports the corresponding **apoc-extended** value, though you must check the release and dependencies. Do not automatically enable both parts just because they are available.

### 3.4. Neo4j Aura

**Aura** pre-installs **a managed subset of APOC Core**. Users cannot copy JARs into **plugins**, edit **neo4j.conf**, or install arbitrary APOC Extended builds as on a self-managed server.

Before choosing a procedure for Aura, consult Aura's official **APOC support** list and check via **SHOW PROCEDURES/SHOW FUNCTIONS** on the live instance. Do not assume every APOC Core function is available across all Aura products/tiers.

## 4. Three Control Layers: Loading, Unrestricting, and Execute Privileges

The control layers can be visualized as follows:

~~~mermaid
flowchart TD
  A["JAR present on server with matching version"] --> B["allowlist: loaded into DBMS?"]
  B --> C["unrestricted: allowed to use restricted internal APIs?"]
  C --> D["Role-based EXECUTE PROCEDURE/FUNCTION privileges"]
  D --> E["Graph access and external resource privileges"]
  E --> F["Cypher query executes within granted scope"]
~~~

| Layer | Control | Meaning | Substitutes Another Layer? |
|---|---|---|---|
| **Plugin install** | JAR and dependencies in plugins | Implementation code available for Neo4j to load | **No** |
| **Load allowlist** | **dbms.security.procedures.allowlist** | Loads only matching procedure/function names | **Does not** grant role privileges |
| **Internal unrestriction** | **dbms.security.procedures.unrestricted** | Allows certain procedures/functions to use internal APIs with elevated access | **Does not** make non-allowlisted names appear |
| **Execute authorization** | **EXECUTE PROCEDURE / EXECUTE FUNCTION** | Who may invoke a loaded procedure/function | **Does not** automatically grant data read/write privileges |
| **Data/resource authorization** | Cypher, file, network, and APOC config permissions | Which operations are permitted while the procedure runs | Must be reviewed separately, especially with boosted execution |

**Important:** both **allowlist** and **unrestricted** are DBMS-level settings applied at server startup/extension loading. They are **not** per-user permission lists. Restricting which users can call individual procedures belongs to **role privileges**, supported in detail in **Neo4j Enterprise Edition**.

## 5. dbms.security.procedures.allowlist: Load Only What Is Needed

### 5.1. Configuration in neo4j.conf

**$NEO4J_HOME/conf/neo4j.conf** is where this is declared:

~~~properties
# Load only the 2 functions and 1 APOC procedure needed for the lab.
dbms.security.procedures.allowlist=apoc.version,apoc.text.clean,apoc.help
~~~

Comma-separated list; full names or the wildcard **\*** are supported. For instance, if an application genuinely needs multiple string-processing functions:

~~~properties
dbms.security.procedures.allowlist=apoc.version,apoc.text.*,apoc.help
~~~

The pattern **apoc.text.\*** loads **the entire group**, which has a broader scope than listing individual names. If you only use **apoc.text.clean**, specifying the exact name is easier to govern.

Key rules:

- Default **allowlist = \***: procedures/functions discovered in plugins can load unless blocked by another restriction.
- Setting an **empty allowlist** prevents extensions from loading; do not mistake it for "keep default."
- The allowlist affects **all extension libraries**, not just APOC. If the system also uses Graph Data Science or other plugins, include their approved entries as well.
- If a name is not allowlisted, **GRANT EXECUTE** on that name cannot make it appear: update the load configuration first.
- Do not casually allow **apoc.\*** or **\*** in production simply to silence "unknown procedure" errors.

**Distinguish the asterisk:** here **\*** is a wildcard matching function/procedure names in the configuration file, not Cypher's variable-length path syntax.

### 5.2. Verifying loaded names

After restarting Neo4j and logging in with an account allowed to inspect procedure/function listings:

~~~cypher
SHOW PROCEDURES
YIELD name, signature
WHERE name STARTS WITH 'apoc.'
RETURN name, signature
ORDER BY name;
~~~

~~~cypher
SHOW FUNCTIONS
YIELD name, signature
WHERE name STARTS WITH 'apoc.'
RETURN name, signature
ORDER BY name;
~~~

**apoc.help** is a **procedure**, whereas **apoc.version** and **apoc.text.clean** are **functions**. Thus, running only **SHOW PROCEDURES** will not show all loaded APOC capabilities.

Simple test without mutating the graph:

~~~cypher
RETURN apoc.version() AS apocVersion,
       apoc.text.clean('Hello World!') AS cleanedText;
~~~

Expected **cleanedText = 'helloworld'**. If the function is unrecognized, inspect JAR loading, versions, allowlist, restart state, and startup errors before widening permissions.

## 6. dbms.security.procedures.unrestricted: Special Privilege for Internal APIs

Some extensions use internal Neo4j APIs that are disallowed under default sandboxing. The **dbms.security.procedures.unrestricted** setting specifies names **exempted** from this restriction:

~~~properties
# Example from Neo4j docs: only when an approved workload genuinely needs it.
dbms.security.procedures.unrestricted=apoc.cypher.runFirstColumn
~~~

This is a **syntax example**, not a general recommendation for lab setups. By default **unrestricted** is empty, and it should **remain empty** whenever the features in use do not require it.

Principles:

1. **Never default to unrestricted=apoc.\***. That grants a very wide set of procedures/functions access to internal APIs, increasing risk compared to least privilege.
2. For a procedure to work, it must be **loaded**, **unrestricted if genuinely needed**, and the caller must possess **EXECUTE** plus appropriate data privileges.
3. **unrestricted is not a cure-all for permission errors**. If the failure is due to missing EXECUTE or graph WRITE privileges, enabling unrestricted fails to fix the root cause while widening risk.
4. Before using a procedure accessing internal APIs, read **that procedure's dedicated documentation page**, assess security implications, and check role impacts.

In the configuration examples of Section 5, **apoc.version**, **apoc.text.clean**, and **apoc.help** do not require **unrestricted** to teach basic loading and function calls. Leaving unrestricted unset is appropriate for this practice exercise.

### 6.1. When both allowlist and unrestricted are present

Suppose the configuration is:

~~~properties
dbms.security.procedures.allowlist=apoc.text.clean,apoc.version,apoc.help
dbms.security.procedures.unrestricted=apoc.cypher.runFirstColumn
~~~

**apoc.cypher.runFirstColumn** is still **not** loaded because it is absent from the allowlist. Making it usable requires both loading and unrestricting, followed by user execution privileges. Do not mistake the two settings for a logical "OR."

## 7. Role-Based Privileges: EXECUTE, Data Privileges, and BOOSTED

In **Neo4j Enterprise Edition**, administrative statements can specify **which role may invoke which procedure/function**. For example, a service needing only string normalization and help lookup:

~~~cypher
// Run in the system database using an administrator account.
CREATE ROLE apoc_text_reader IF NOT EXISTS;

GRANT EXECUTE FUNCTION apoc.text.clean
ON DBMS TO apoc_text_reader;

GRANT EXECUTE FUNCTION apoc.version
ON DBMS TO apoc_text_reader;

GRANT EXECUTE PROCEDURE apoc.help
ON DBMS TO apoc_text_reader;
~~~

These statements perform **role administration**; they do not create graph data or assign the role to users automatically. After verifying the real application user, an administrator assigns that role to the appropriate account per organizational policy.

**Notes for accurate interpretation:**

- **EXECUTE PROCEDURE** grants permission to call procedures; **EXECUTE FUNCTION** grants permission to call user-defined functions. The two privileges are not interchangeable.
- A graph-reading procedure remains subject to appropriate **TRAVERSE/READ** privileges; a graph-writing procedure requires corresponding write privileges unless **BOOSTED** is explicitly granted.
- The **GRANT** example does not "revoke" broader privileges a user may already hold via other roles. Always inspect **effective privileges** across all roles and existing **DENY** rules.
- **GRANT EXECUTE BOOSTED PROCEDURE** is a **distinct** elevated privilege that can allow operations inside a procedure to bypass a user's normal data privileges; grant it only with explicit design and approval.
- Per modern Neo4j docs, for **BOOSTED** to actually take effect, the user needs both the corresponding **EXECUTE PROCEDURE** privilege and **EXECUTE BOOSTED PROCEDURE** privilege. Never use BOOSTED as a quick "permission fix."
- Granular role/privilege management is an **Enterprise** capability; do not copy these commands verbatim to Community Edition or Aura assuming identical behavior. Review the security model and limits of your environment.

### 7.1. Checking execution privileges under the application account

Log in with the **actual application account** or an account authorized to inspect it:

~~~cypher
SHOW PROCEDURES EXECUTABLE BY CURRENT USER
YIELD name, signature
WHERE name STARTS WITH 'apoc.'
RETURN name, signature
ORDER BY name;
~~~

~~~cypher
SHOW FUNCTIONS EXECUTABLE BY CURRENT USER
YIELD name, signature
WHERE name STARTS WITH 'apoc.'
RETURN name, signature
ORDER BY name;
~~~

These two queries distinguish between **loaded functions/procedures** and **functions/procedures the current user is allowed to execute**. An administrator account will often see more entries than an API account.

**SHOW PROCEDURES** does not replace checking **graph privileges**. A procedure may show up as executable while a query still fails when attempting to modify nodes, read files, or open network connections disallowed to the user/instance.

### 7.2. Illustrating the principle of least privilege

| Account | Need | Privilege Direction |
|---|---|---|
| **api_reader** | Query graph and call a few string helpers | Appropriate graph TRAVERSE/READ + EXECUTE FUNCTION on specific names |
| **import_worker** | Ingest validated data | Scoped WRITE privileges; only approved import procedures if truly required |
| **db_maintainer** | Update config, plugins, inspect errors | Operational privileges; do not reuse as an API account |
| **auditor** | Review feature inventory and privileges | Read access to configuration/roles as appropriate; no default WRITE |

Never embed a full-privilege admin account in Java Driver or Spring Data Neo4j code just to avoid granting narrow permissions. Each application should connect with its own minimally scoped account.

## 8. apoc.conf: File Limits, Exports, and Out-of-Database Features

Since **APOC 5**, settings starting with **apoc.** belong in **$NEO4J_HOME/conf/apoc.conf** or corresponding environment variables. **Do not place apoc.* in neo4j.conf** as in older APOC docs; with strict validation, misplacement can prevent Neo4j from starting or cause settings to be ignored.

Safe **apoc.conf** example for an environment that **does not need local file read/write via APOC**:

~~~properties
apoc.import.file.enabled=false
apoc.export.file.enabled=false
~~~

These controls are **separate** from the **allowlist**:

| Control | File | Purpose |
|---|---|---|
| **dbms.security.procedures.allowlist** | **neo4j.conf** | Which procedures/functions are loaded |
| **dbms.security.procedures.unrestricted** | **neo4j.conf** | Which procedures/functions bypass internal API sandboxing |
| **apoc.import.file.enabled** | **apoc.conf** | Allows APOC features to read local files |
| **apoc.export.file.enabled** | **apoc.conf** | Allows APOC features to write data to local files |
| **apoc.import.file.use_neo4j_config** | **apoc.conf** | When enabled, file access adheres to Neo4j's import directory/file-read configuration |

Per current documentation, **apoc.import.file.enabled** and **apoc.export.file.enabled** default to **false**. If a file import/export task must be enabled:

1. Identify the exact procedure to run, source or target file, executing user, and data privileges.
2. Allowlist only the required procedure; do not open the entire APOC namespace unnecessarily.
3. Consider enabling strictly **one** of import or export in **apoc.conf**.
4. Keep path restrictions aligned with **server.directories.import** and related settings where appropriate.
5. Grant execute/graph-write privileges to the proper role; monitor requests, OS permissions, and the target directory.

**Do not interpret apoc.import.file.enabled=false as "all network access is blocked."** It governs **local file reading** by the relevant APOC features. HTTP/HTTPS calls, cloud storage, or external URI reads require procedure policies, authentication, network permissions, egress/firewall rules, and separate settings. Likewise, enabling file import in **apoc.conf** does not automatically grant OS-level file access outside what the Neo4j process itself possesses.

### 8.1. Principles for protecting external sources

Procedures capable of loading URLs or running dynamic Cypher require stricter scrutiny than pure string functions. For any client-specified source:

- Allow only trusted origins, enforcing permitted domains/addresses at both application and infrastructure layers.
- Never pass arbitrary user-supplied URLs, credentials, or query fragments into sensitive procedures without validation.
- Never enable unrestricted privileges broadly just to bypass file or HTTP errors.
- Ensure the container/server cannot read sensitive files outside its granted working directories.
- Avoid enabling **export** features if no account genuinely needs data export.

**APOC does not replace Neo4j data authorization**; when powerful internal procedures or BOOSTED privileges are present, security boundaries should be verified with negative tests (confirming forbidden requests actually fail).

## 9. Verifiable Configuration Rollout Process

### 9.1. Define the minimal list

Before modifying configuration, inventory every **CALL apoc....** and **apoc....(...)** call in code or approved queries; document:

- Exact name and type (**procedure/function**).
- Package (**Core/Extended**), required version, extra dependencies.
- Whether **unrestricted** is truly required according to the procedure docs.
- Which roles call it, plus related READ/WRITE and external resource permissions.
- Whether plain Cypher syntax is preferable to reduce APOC coupling.

For instance, this lesson's workload only needs **apoc.text.clean**, **apoc.version**, and **apoc.help**. They should not be widened to **apoc.\***.

### 9.2. Apply changes and restart

1. Back up configuration and record current Neo4j/JAR versions per operational runbooks.
2. Place verified JARs into **plugins** and check file permissions.
3. Set the minimal **allowlist**, and set **unrestricted** only if an approved feature requires it.
4. Create **apoc.conf** with required file/network options; do not mix config file locations.
5. Roll out consistently across required servers; perform a controlled restart.
6. Run **SHOW PROCEDURES**, **SHOW FUNCTIONS**, and verification queries using both admin and application accounts.
7. Watch startup logs, query latency, and error responses; be ready to roll back config/JARs if critical functionality fails to load.

### 9.3. Test both allowed and denied cases

| Test Case | Expected Outcome |
|---|---|
| Admin calls **apoc.version()** and **apoc.text.clean(...)** | Succeeds when Core is loaded and allowlist includes both |
| User with matching EXECUTE FUNCTION calls **apoc.text.clean(...)** | Succeeds if effective privileges permit |
| An APOC function omitted from the allowlist | Absent from the loaded catalog |
| User denied EXECUTE on a sensitive procedure | Rejected even though the procedure is loaded |
| File-based procedure when **apoc.import.file.enabled=false** | Local file read via the relevant APOC feature is disallowed |
| Procedure using internal APIs without being unrestricted | Cannot automatically exercise full internal APIs |

For practice exercises, you can inspect the loaded catalog without attempting to run hazardous procedures. In a dedicated test environment, administrators can add negative privilege tests using a restricted role.

## 10. Troubleshooting Common Errors

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| **Unknown procedure/function** | Plugin not installed, wrong JAR version, missing restart, omitted from allowlist | Inspect plugins, version, startup logs, and SHOW PROCEDURES/FUNCTIONS |
| Some APOC entries work, others fail | Core vs. Extended split, partial allowlist, deprecated feature | Check package/version and actually loaded catalog |
| **Unauthorized** or **permission denied** | Role lacks EXECUTE/READ/WRITE or hits DENY | SHOW ... EXECUTABLE BY CURRENT USER; review effective privileges |
| Error referencing **restricted procedure** | Procedure needs internal APIs but is not unrestricted | Read procedure page; unrestrict only the exact approved name |
| **Import from files not enabled** error | **apoc.import.file.enabled** is disabled | Check **apoc.conf** and business need |
| Unable to read file path | File path is server-side; import directory/OS permissions differ from expectation | Verify actual path, permissions, and directory config |
| URL access failure | Missing DNS/network/egress route, authentication, or invalid source | Inspect network config and URL policy |
| Server fails to start after config edit | Misplaced **apoc.*** in neo4j.conf, incompatible JAR, missing dependency | Check logs, config files, and version compatibility matrix |
| Works in Desktop but fails on Aura | Aura exposes only a supported APOC Core subset | Consult Aura APOC support docs and switch to available features |
| Tests pass as admin but API fails | Java Driver/Spring Data Neo4j account has fewer privileges than admin | Test with the exact API account, inspect roles and data privileges |

### 10.1. Separate four error classes before fixing

**Name not found** is usually an **installation/allowlist/version** issue. **Found but denied execution** is an **execute privilege** issue. **Executable but denied graph or file access** is a **resource privilege** issue. **Plugin present but fails to start** usually requires inspecting **JARs, dependencies, or configuration**. Separating these classes prevents risky workarounds like setting **unrestricted=apoc.\*** for every error.

## 11. Practice Exercises and Scenarios

### Exercise 1 — Classifying privileges

Given the configuration:

~~~properties
dbms.security.procedures.allowlist=apoc.text.clean,apoc.version,apoc.help
~~~

Explain:

1. Why does **apoc.text.clean** appear in **SHOW FUNCTIONS**, whereas **apoc.help** appears in **SHOW PROCEDURES**?
2. Is an account lacking the corresponding EXECUTE FUNCTION privilege guaranteed to be able to call **apoc.text.clean**?
3. Why is adding **apoc.load.json** to **unrestricted** without adding it to **allowlist** still insufficient to call it?

### Exercise 2 — Least-privilege role design

An application only needs to normalize product names using **apoc.text.clean**, with no file or network access through APOC. Design the minimal **neo4j.conf**, **apoc.conf**, and EXECUTE privileges. Propose verification queries for both an admin role and the API account.

### Exercise 3 — Fixing misconfiguration

An operations team uses:

~~~properties
dbms.security.procedures.allowlist=apoc.*
dbms.security.procedures.unrestricted=apoc.*
~~~

They actually only need one procedure to read JSON over HTTPS. State the risks of overly broad privileges and propose how to build a **name-based allowlist**, investigate whether **unrestricted** is needed, manage **HTTP egress**, authentication, and data read privileges. Do not enable package-wide internal API unrestriction without verification.

### Exercise 4 — Ingestion on Aura

An application written for self-managed Neo4j requires APOC Extended, but is migrating to **Aura**. Describe how to check the supported APOC list, find Cypher replacements, or redesign ETL via a Java Driver/Spring Data Neo4j application when the Extended procedure is unavailable.

### Exercise 5 — Reading error symptoms

After deployment, an admin can run **apoc.version()**, but the application user is denied **CALL apoc.help('text')**. Explain why this check does not prove the JAR is broken. List the **SHOW PROCEDURES**, **SHOW PROCEDURES EXECUTABLE BY CURRENT USER**, and privilege checks needed.

## 12. Key Takeaways

To use APOC safely in Neo4j, separate **installing the JAR**, **loading via allowlist**, **exempting internal APIs via unrestricted**, **granting role-based EXECUTE privileges**, and **graph/file/network permissions at runtime**. These are independent layers that together govern whether a procedure runs and within what boundaries.

In production, prefer **built-in Cypher or APOC Core when sufficient**, match plugin versions to the server, allowlist only approved names, and keep **unrestricted** minimal. Place **dbms.security.procedures.*** in **neo4j.conf**, place **apoc.*** options in **apoc.conf** starting in APOC 5, and verify using the **real application account**, not solely an administrator account.

### Official Documentation

- [Neo4j APOC Core – Installation](https://neo4j.com/docs/apoc/current/installation/)
- [Neo4j APOC Core – Configuration Options](https://neo4j.com/docs/apoc/current/config/)
- [Neo4j APOC Core – Security Guidelines](https://neo4j.com/docs/apoc/current/security-guidelines/)
- [Neo4j Operations Manual – Securing Extensions](https://neo4j.com/docs/operations-manual/current/security/securing-extensions/)
- [Neo4j Operations Manual – Configure Plugins](https://neo4j.com/docs/operations-manual/current/configuration/plugins/)
- [Neo4j Operations Manual – Procedure and User-Defined Function Privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-execute-permissions/)
- [Neo4j Operations Manual – Docker Plugins](https://neo4j.com/docs/operations-manual/current/docker/plugins/)
- [Neo4j APOC Extended – Installation](https://neo4j.com/labs/apoc/5/installation/)
- [Neo4j Aura – APOC Support](https://neo4j.com/docs/aura/apoc/)
