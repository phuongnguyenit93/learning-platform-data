# Creating the Initial Account, Changing Passwords, and Verifying Connections

## 1. Objectives and Context

Neo4j is a graph database management system using the **property graph** model. Data consists of **nodes**, directed **relationships**, and **properties**; the **Cypher** language helps match relationship patterns, query paths, and update data. Before diving into indexes, constraints, query tuning, data import, or integrating Java Driver and Spring Data Neo4j, you must be able to access the **right Neo4j DBMS** with a **valid account**.

This lesson belongs to the **Environment Setup** chapter and focuses on the credential lifecycle: **setting up the initial account → first login → changing password → verifying connectivity and queries → safeguarding credentials**.

After this lesson, you will be able to:

1. Distinguish the default `neo4j` account, the initial password, and a changed password.
2. Create initial credentials for Neo4j Desktop, self-hosted server, Docker Compose, and Neo4j AuraDB.
3. Change a known password via the UI or Cypher `ALTER CURRENT USER SET PASSWORD`.
4. Verify identity and access rights using Neo4j Browser, Cypher Shell, and Java Driver.
5. Diagnose authentication, URI, port, TLS, or database name errors without losing data.

> **Scope:** Examples use internal authentication (**native authentication**) on a standalone Neo4j DBMS, primarily for learning. Multi-user management, roles/privileges, SSO/OIDC, LDAP, and admin recovery workflows vary by **edition**, version, and environment. Documentation describes current Neo4j, illustrated with the `neo4j:2026.10.2` image; always check the guide for your exact version.

## 2. Understanding Neo4j Accounts and Password States

### 2.1. Authentication differs from authorization

- **Authentication** answers: *who is connecting?* For example, username `neo4j` and the password you set.
- **Authorization** answers: *what is that user allowed to do?* For example, reading data, writing nodes/relationships, creating indexes/constraints, or managing users.
- **Database** is where graph queries execute. One DBMS can manage one or more databases depending on edition and configuration; passwords belong to **DBMS users**, and are not set separately by running commands on individual nodes.

In typical local setups with native authentication, **the initial admin account name is `neo4j`**. This login name is **distinct** from the `neo4j` database name, even though in many labs both carry the string `neo4j`.

| Concept | Illustrative example | Notes |
| --- | --- | --- |
| Username | `neo4j` | Initial administrative account |
| Password | Password you create | Never commit real passwords in Git, logs, or reports |
| Database | `neo4j` | Default database commonly available in labs; verify the actual name |
| Browser URL | `http://localhost:7474/browser/` | Loads the web UI, not a Driver URI |
| Bolt URI | `bolt://localhost:7687` | Address for Java Driver/Cypher Shell connecting to local DBMS |
| AuraDB URI | `neo4j+s://<instance-id>.databases.neo4j.io` | Copy the exact URI from Aura Console; uses TLS |

### 2.2. Initial password lifecycle

~~~mermaid
flowchart TD
    A["Install fresh DBMS, no user data yet"] --> B{"Initial password set?"}
    B -- "Yes" --> C["Neo4j initializes native user with that credential"]
    B -- "No" --> D["Local server uses neo4j / neo4j<br/>and requires change on first login"]
    C --> E["First login"]
    D --> E
    E --> F{"Password change required?"}
    F -- "Yes" --> G["Change to personal password"]
    F -- "No" --> H["Run queries and verify connection"]
    G --> H
    H --> I["When later changes are needed: use ALTER CURRENT USER"]
    I --> J["Applications update secrets and recreate connections"]
~~~

**Core principle:** "Setting the initial password" is an **account initialization action on a new DBMS**, whereas "changing a password" modifies an **existing account**. The two operations do not substitute for each other.

- For a self-installed server, `neo4j-admin dbms set-initial-password` is only used **before the DBMS starts for the first time**.
- For Docker, `NEO4J_AUTH` or `NEO4J_AUTH_FILE` only initializes the user when the **`/data` volume has no existing auth state**.
- Once a database already exists, changing environment variables, secret files, or recreating the container **does not overwrite** the stored user password.
- On a self-installed Neo4j server, if not pre-configured, the default password is `neo4j` and the user must change it on first login. **Never leave default credentials** on an endpoint reachable from another network.

## 3. Preparing Before Creating an Account

Identify the environment you are using:

| Environment | Who creates the initial password? | Where to connect |
| --- | --- | --- |
| **Neo4j Desktop** | User when creating the DBMS via UI | Local DBMS managed by Desktop |
| **Native server (ZIP/TAR/DEB/RPM)** | `neo4j-admin` command **before first start**, or changed from default on first login | `bolt://localhost:7687` under default setup |
| **Docker/Compose** | `NEO4J_AUTH` or file referenced by `NEO4J_AUTH_FILE` | Host: `bolt://localhost:7687` if published; same Compose network: `bolt://neo4j:7687` |
| **AuraDB** | Service supplies initial credentials in Aura Console | Instance's `neo4j+s://...` URI |

In addition to the environment, prepare a **strong, unique password**, a controlled secret store, the URI/port, username, and database name. Neo4j enforces a minimum password policy; current documentation specifies a default of **at least 8 characters**, though in real use you should generate a longer random string and never reuse passwords from other accounts.

**Protect sensitive information from the start:**

- Never put real passwords into `compose.yaml`, `application.properties` in Git, doc examples, screenshots, or support tickets.
- Consider the risk of passing passwords via command-line arguments: they can end up in **shell history**, process listings, or logs.
- `.env` and Compose secret files on a dev machine **are not automatically encrypted vaults**; restrict file permissions and use a proper secret manager for production.
- When configuring remote connections, evaluate **TLS and firewalls** alongside username/password.

## 4. Setting the Initial Password for a Self-Hosted Neo4j Server

### 4.1. Initializing with `neo4j-admin`

This applies to a **brand-new DBMS that has never been started**. After installing the Neo4j package and before starting the server:

~~~text
neo4j-admin dbms set-initial-password --require-password-change "<TEMPORARY_PASSWORD>"
~~~

Replace `<TEMPORARY_PASSWORD>` with a sufficiently strong temporary password. This is **illustrative syntax**—do not paste the literal placeholder for real use. Depending on installation, `neo4j-admin` lives in `bin` or is already in `PATH`.

The `--require-password-change` option forces the account to change its password on first login, which fits when an administrator creates temporary credentials and hands them off to a user. If you **omit** that flag, setting the initial password does not require an immediate change by default; this differs from a server falling back to the default `neo4j` password.

On Linux installed from a package managed by `systemd`, you may need to run the command as the `neo4j` service user. Example invocation before starting the service:

~~~bash
# Example for Linux package; use a temporary password per your security process
sudo -u neo4j neo4j-admin dbms set-initial-password --require-password-change "<TEMPORARY_PASSWORD>"
sudo systemctl start neo4j
sudo systemctl status neo4j
~~~

The password in the argument above may be saved in command history. In shared environments, use an organization-approved silent secret input method or interactive prompt per the [Set an initial password guide](https://neo4j.com/docs/operations-manual/current/configuration/set-initial-password/). Never paste a real password into lesson content or committed shell scripts.

With ZIP/TAR, inside the Neo4j directory you can invoke tools from `bin` and start `bin/neo4j console`; on Windows the corresponding launcher is in the installation's `bin` folder. Exact paths and file extensions depend on package and OS.

### 4.2. What if the server has already started for the first time?

**Do not** reuse `set-initial-password` to change the password of an existing database. Once logged in, use the method in Section 7. If the password is lost, follow the **password recovery** procedure supported by Neo4j for your DBMS version/edition; never delete the `data` directory or create a new volume just to "reset a password."

**Case with no initial configuration:** on a completely fresh self-installed server, the default account is `neo4j` with password `neo4j` and must be changed immediately on first login. Never test default credentials on a system you do not administer.

## 5. Creating an Account When Using Neo4j Desktop

Neo4j Desktop lets you create and operate local DBMSs through a UI. General flow:

1. Install Desktop compatible with your OS, create a **local DBMS instance**, and choose the DBMS version.
2. When Desktop prompts, set a password for **user `neo4j`**. Store the password in a personal secret manager.
3. **Start** the DBMS and monitor status and logs until the service is ready.
4. Open **Query/Neo4j Browser** from Desktop and connect to the right DBMS.
5. Run `SHOW CURRENT USER;` and `RETURN 1 AS ok;` to verify the authenticated session and query execution.

Button labels may vary between Desktop versions; look for the **DBMS/connection** management section. **Desktop version** does not equal the internal **Neo4j Server** version, and each local DBMS has its own credentials. If you have multiple local DBMSs, verify the exact instance name/port before suspecting a wrong password.

When changing the password of an authenticated account, use Cypher in Section 7. Never delete a DBMS or database directory just because you forgot a password.

## 6. Initializing a User with Docker Compose and Secrets

### 6.1. Compose configuration using a persistent data volume

The official Neo4j Docker image supports `NEO4J_AUTH` and **`NEO4J_AUTH_FILE`**. The example below uses a **Compose secret** to avoid placing passwords directly in the YAML file.

Create a lab directory containing:

~~~text
neo4j-auth-lab/
├── compose.yaml
├── .gitignore
└── secrets/
    └── neo4j_auth.txt
~~~

Contents of `compose.yaml`:

~~~yaml
services:
  neo4j:
    image: neo4j:2026.10.2
    ports:
      - "127.0.0.1:7474:7474"
      - "127.0.0.1:7687:7687"
    environment:
      NEO4J_AUTH_FILE: /run/secrets/neo4j_auth
    secrets:
      - neo4j_auth
    volumes:
      - neo4j_data:/data
    restart: unless-stopped

secrets:
  neo4j_auth:
    file: ./secrets/neo4j_auth.txt

volumes:
  neo4j_data:
~~~

File `secrets/neo4j_auth.txt` contains **one line**:

~~~text
neo4j/REPLACE_WITH_A_UNIQUE_STRONG_PASSWORD
~~~

Replace the placeholder with your own password before starting. Neo4j reads the secret file inside the container at `/run/secrets/neo4j_auth`. `neo4j` is the **initial username**; everything after `/` is the password. If using special characters or non-ASCII characters, ensure the file is UTF-8 encoded and check the secret format docs for your Neo4j version.

Add `secrets/` to `.gitignore`:

~~~gitignore
secrets/
.env
.env.*
!.env.example
~~~

**Note:** Local Docker Compose mounts secrets as files. File contents remain visible to users with appropriate read permissions on the host; this is a mechanism for passing secrets into a container, **not a replacement for a vault/secret manager**.

### 6.2. Starting and logging in for the first time

In the `neo4j-auth-lab` directory:

~~~bash
docker compose config --quiet
docker compose up -d
docker compose ps
docker compose logs --tail=100 neo4j
~~~

Wait for Neo4j to become ready, then open `http://localhost:7474/browser/` using:

- **Bolt URI:** `bolt://localhost:7687`.
- **Username:** `neo4j`.
- **Password:** the string after `neo4j/` in the created secret.

Host ports are restricted to `127.0.0.1` for local lab purposes. If a Java application runs **in another service on the same Compose network**, the internal network URI is `bolt://neo4j:7687`.

### 6.3. Why changing the secret file does not change the stored password

The `NEO4J_AUTH_FILE` file only sets **initial authentication** when Neo4j has no database users yet. In the example above, authentication state and data reside in the volume mounted at `/data`.

Example scenario:

1. First startup with secret password A: Neo4j creates credential A.
2. You create nodes/relationships and stop via `docker compose down`: **the volume still exists**.
3. You edit the secret to password B and run `docker compose up -d`.
4. Neo4j reuses the auth already stored in the volume: **B does not replace A**. You must log in with the currently valid password and change it as shown in Section 7.

**Do not use** `docker compose down -v` as a way to "reset a password": the `-v` flag removes named volumes holding graph data, users, and metadata. To preserve data, keep the same project name and volume, and use proper password change/recovery procedures.

## 7. Changing the Password of the Currently Logged-in Account

### 7.1. Changing when Neo4j prompts on first login

If the system reports **password change required**, follow the password-change screen in the tool you are using; enter the current temporary password, choose a new password, and log back in.

After changing it successfully, update the password in your secret store and dependent applications. A Java application still holding old credentials will continue reporting `Authentication failed` for new connections until its config and Driver are recreated.

### 7.2. Changing password with Cypher

An **authenticated user** can change their own password without privileges to manage other users:

~~~cypher
ALTER CURRENT USER
SET PASSWORD FROM '<CURRENT_PASSWORD>' TO '<NEW_STRONG_PASSWORD>';
~~~

`<CURRENT_PASSWORD>` and `<NEW_STRONG_PASSWORD>` are **placeholders**, not values for real environments. The command requires the exact old password and a new password meeting policy requirements. The new password must differ from the previous one. This **updates the current user's credentials**; it does not create a new account.

In applications with parameterized Cypher APIs, use **string parameters** instead of embedding real passwords directly in the query string:

~~~cypher
ALTER CURRENT USER
SET PASSWORD FROM $currentPassword TO $newPassword;
~~~

The `$currentPassword` and `$newPassword` values are supplied securely by the client according to the tool used; this query **cannot run unless parameters are provided**. In Browser or Cypher Shell, parameter-passing syntax may vary across versions. Avoid pasting real passwords into queries saved in browser history, screenshots, or logs.

To verify the user and password-change-required status:

~~~cypher
SHOW CURRENT USER;
~~~

The result typically includes `user` and `passwordChangeRequired` columns; additional columns such as `roles` or `suspended` may vary by edition. After changing, **disconnect and log back in with the new password**. A previously authenticated session may remain open; verification must rely on a **fresh login session**, not merely on the password-change statement returning success.

### 7.3. Changing another user's password and admin privileges

In environments supporting user management and appropriate admin privileges, an administrator can reset a managed account's password with `ALTER USER`. Syntax example:

~~~cypher
ALTER USER someUser SET PASSWORD '<NEW_TEMPORARY_PASSWORD>' CHANGE REQUIRED;
~~~

This is an **administrative operation**: execution rights depend on edition, auth configuration, and DBMS privileges. Do not use it in place of `ALTER CURRENT USER` when a user knows their old password and simply wants to change their own password. When handing off a temporary password to someone else, require a change on next login and use an approved credential-delivery channel.

### 7.4. What if the password is completely forgotten?

You cannot self-change via `ALTER CURRENT USER` if you cannot log in. Appropriate sequence:

1. Confirm the exact **instance, URI, port, and username**, since hitting the wrong machine is often mistaken for a forgotten password.
2. Check your secret vault or internal handoff records; do not repeatedly guess passwords and trigger lockout/rate limits.
3. If another authorized administrator exists, ask them to perform the appropriate reset operation.
4. If no admin access remains, follow the **[Recover admin user and password](https://neo4j.com/docs/operations-manual/current/authentication-authorization/password-and-user-recovery/)** procedure for your **exact version and edition**, on a system you own/administer.

The recovery procedure may require maintenance downtime and network isolation; follow Neo4j docs carefully to avoid exposing an unauthenticated database externally. **Do not** delete the `/data` volume, permanently disable authentication, or edit the initial password expecting it to overwrite existing auth.

## 8. AuraDB: Service-Provisioned Credentials

**Neo4j AuraDB** runs on managed infrastructure. You **do not run `neo4j-admin dbms set-initial-password` on AuraDB**, because you do not have direct access to the service's filesystem or process.

Initial flow:

1. Open **[Aura Console](https://console.neo4j.io/)**, create or select an AuraDB instance.
2. Receive/download the service-provided connection details: **Connection URI**, **username**, **password**, and database name if needed.
3. Save the password/credentials in an approved secret vault. Some credentials are shown for download **only at creation time**, so store them safely right away.
4. Use the **Query** tool in Aura Console or the Java Driver to connect with the provided URI, typically formatted as:

~~~text
neo4j+s://example123.databases.neo4j.io
~~~

`example123` is only a placeholder; **do not guess hostnames**, and do not change `neo4j+s://` to `bolt://` to bypass TLS. When needing to reset/rotate credentials without being able to log in, use the official Aura Console functionality or service support per your tier. When already logged in with native auth, current-user password change commands may apply depending on service capabilities and terms.

## 9. Verifying Connectivity Step by Step

Verification should separate **network → protocol → authentication → database → Cypher**. Loading the Browser page alone does not prove an account can log in.

### 9.1. Level 1: Are the DBMS and ports ready?

With Docker Compose:

~~~bash
docker compose ps
docker compose logs --tail=100 neo4j
~~~

With Desktop, check the active instance's status and logs. With a native Linux server, inspect `systemctl status neo4j` and `journalctl -u neo4j` if using systemd.

Two common endpoints:

| Port / URI | Role | What to verify |
| --- | --- | --- |
| `http://localhost:7474/browser/` | Neo4j Browser web UI | Browser page loads |
| `bolt://localhost:7687` | Bolt query endpoint | Driver/Cypher Shell reaches the right DBMS |
| `neo4j+s://<id>.databases.neo4j.io` | AuraDB over Bolt TLS | DNS, network, TLS, and credentials |

If Java runs in **another container** on the same Compose network, `localhost` points to the **Java container**, not the Neo4j service. In that case use `bolt://neo4j:7687`, where `neo4j` is the service DNS name.

### 9.2. Level 2: Logging in via Neo4j Browser

With local Neo4j, open `http://localhost:7474/browser/`:

1. Select the Bolt address of the **instance** to log into, e.g., `bolt://localhost:7687`.
2. Enter username `neo4j` and the password **changed/initialized for that instance**.
3. If the tool requires an initial password change, complete it and log back in.
4. Run:

~~~cypher
SHOW CURRENT USER;
~~~

If it returns user details, authentication succeeded. Continue by running:

~~~cypher
RETURN 1 AS ok, datetime() AS serverTime;
~~~

A row with `ok = 1` proves you can execute Cypher on the selected database. To confirm version/edition:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

Do not infer server version solely from the image name, Browser UI version, or application code.

### 9.3. Level 3: Testing with Cypher Shell

On a host with `cypher-shell` installed:

~~~bash
cypher-shell -a bolt://localhost:7687 -u neo4j -d neo4j
~~~

With Docker Compose, run the tool inside the Neo4j container:

~~~bash
docker compose exec neo4j cypher-shell -a bolt://localhost:7687 -u neo4j -d neo4j
~~~

If no password is passed via CLI flags, `cypher-shell` prompts interactively depending on version/config. Never pass `-p YOUR_REAL_PASSWORD` in shared commands to avoid leaking it in shell history or process lists.

After logging in, run:

~~~cypher
RETURN 'authenticated' AS status;
~~~

If Cypher Shell logs in successfully while Browser fails, focus on Browser config, WebSocket, and Bolt/TLS settings in the browser. If both fail, inspect DBMS state, URI, and credentials.

### 9.4. Level 4: Neo4j Java Driver

The **Neo4j Java Driver** connects over Bolt and does not use the Browser HTTP URL. Example verification from a Java app declaring a compatible Driver dependency:

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;

public class Neo4jLoginCheck {
    public static void main(String[] args) {
        String uri = requireEnv("NEO4J_URI");
        String user = requireEnv("NEO4J_USERNAME");
        String password = requireEnv("NEO4J_PASSWORD");

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(user, password))) {
            // Creating a Driver does not guarantee connectivity; this line verifies the server.
            driver.verifyConnectivity();

            try (Session session = driver.session()) {
                long value = session.run("RETURN 1 AS ok")
                                    .single().get("ok").asLong();
                System.out.println("Neo4j connection OK: " + value);
            }
        }
    }

    private static String requireEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing environment variable: " + key);
        }
        return value;
    }
}
~~~

Set environment variables where the application runs; **never** hardcode credentials in Java. Example URI `bolt://localhost:7687` when the app runs on the host against local Neo4j; inside the same Compose network use `bolt://neo4j:7687`; with AuraDB use the exact `neo4j+s://...`.

**After changing a password:** update `NEO4J_PASSWORD` in the application environment and **recreate the Driver/connections**; a Driver initialized with `AuthTokens.basic(user, oldPassword)` does not automatically learn the new password. When using a connection pool, Spring Boot, or a secrets manager, reload/restart components as designed so new connections use the new credentials.

### 9.5. Level 5: Spring Data Neo4j

When using Spring Boot with Spring Data Neo4j, configure `application.properties`:

~~~properties
spring.neo4j.uri=${NEO4J_URI}
spring.neo4j.authentication.username=${NEO4J_USERNAME}
spring.neo4j.authentication.password=${NEO4J_PASSWORD}
~~~

These parameters configure the Driver connection. Verify compatibility across Spring Boot, Spring Data Neo4j, Driver, and application JDK; the **Neo4j server** JVM may run in a separate environment. If the application uses a specific database, configure the database name according to your Spring Data Neo4j version's capabilities.

## 10. Verifying Access Rights with a Small Property Graph

`RETURN 1` proves connectivity and basic Cypher execution; to verify **read/write data permissions**, create a small graph in a **test** database:

~~~cypher
MERGE (student:Student {studentId: 'neo4j-auth-lab'})
  ON CREATE SET student.name = 'An'
MERGE (course:Course {courseId: 'neo4j-connect'})
  ON CREATE SET course.title = 'Connecting to Neo4j'
MERGE (student)-[:ENROLLED_IN]->(course)
RETURN student.name AS studentName, course.title AS courseTitle;
~~~

Read back the relationship:

~~~cypher
MATCH p =
  (:Student {studentId: 'neo4j-auth-lab'})
  -[:ENROLLED_IN]->
  (:Course {courseId: 'neo4j-connect'})
RETURN p;
~~~

If the result returns a path with both nodes and the `ENROLLED_IN` relationship, you have verified **writing and reading** property graph data. `MERGE` works well for repeatable labs; applications with concurrent transactions still require designing **uniqueness constraints**.

If `RETURN 1` succeeds while `MERGE` is rejected for lack of privileges, the connection **authenticated successfully**, but the **user lacks write privileges**. That is an **authorization** error, not a password error.

## 11. Common Error Scenarios

| Symptom | Possible cause | Verification and resolution |
| --- | --- | --- |
| `Authentication failed` immediately at login | Wrong username, wrong password, wrong instance/port | Verify URI, instance name, and active password; test Browser/Cypher Shell |
| Changed `NEO4J_AUTH`/secret but password didn't change | `/data` volume holds user created on an earlier startup | Log in with still-valid old credentials and run `ALTER CURRENT USER`; do not delete volume |
| `Password change required` | Using default password or temporary password forced to change | Complete password change flow, reconnect with new password |
| `Too many failed authentication attempts` or temporary login lockout | Repeated failed credential attempts exceeded threshold | Stop guessing, wait per policy, and verify the correct credentials |
| `Connection refused` | Server not ready, wrong port/hostname, or Bolt not listening | Check service/logs, test exact `bolt://...:7687` from where the app runs |
| Browser loads page but cannot log in | HTTP `7474` works but Bolt `7687`/WebSocket is blocked or auth failed | Check Bolt URI, network/TLS, password; test with Cypher Shell |
| Docker Java app using `localhost:7687` fails to connect | `localhost` points to the Java container | On the same Compose network use `bolt://neo4j:7687` |
| AuraDB reports TLS/certificate error | Wrong scheme, CA, DNS, endpoint, or network filtering | Keep exact `neo4j+s://` from Aura, verify TLS and instance status |
| `Database not found` | Wrong database name or database does not exist | Confirm database in the instance; do not assume every DB is named `neo4j` |
| Read queries work but `CREATE`/`MERGE` is rejected | Account lacks write privileges | Check current privileges; admin grants appropriate role per edition |
| Password changed successfully, yet Spring Boot still reports wrong password | App still holds old credentials or pool/Driver not reloaded | Update app secrets and reinitialize necessary connections |
| Forgot admin password and nobody can log in | No valid credentials remaining | Follow official recovery guide, isolate network, preserve data |

**Recommended diagnostic flow:** right DBMS/URI → TCP/Bolt/TLS → username/password → password-change state → database → query privileges. Only run data-modifying statements after confirming you are in a **lab database**, avoiding accidental production changes.

## 12. Account Security When Moving from Lab to Real Applications

A single initial account gets you started quickly, but it is not a long-term administration model. When moving a graph system into a Java backend or shared environment:

- **Separate humans and applications:** where edition/permissions support it, provision dedicated service accounts with **least privilege**, avoiding using admin `neo4j` for every application request.
- **Manage secret lifecycles:** choose strong, unique passwords; store them in a vault or proper secret manager; document ownership and rotation procedures.
- **Plan password rotations:** update consumer secrets, change the password, verify new connections, and retire old credentials per operational procedure.
- **Encrypt connections across hosts:** deploy TLS with proper certificate trust; AuraDB uses `neo4j+s://` URIs. Never use `bolt+ssc://` to skip certificate verification over public networks.
- **Monitor logs without leaking secrets:** log diagnostic essentials such as error type, instance, database, and timestamp; never print passwords, tokens, or full environments.
- **Never disable authentication to "fix errors":** recovery has its own safety conditions—never turn `dbms.security.auth_enabled=false` into a routine operating config.

## 13. Hands-on Exercises and Completion Criteria

### Exercise 1 — Initializing and forcing a password change

On a **fresh DBMS**, choose Desktop or a native server. Set a temporary password and require changing it on first login (if supported by the deployment method). Log in, change the password, reconnect, and run `SHOW CURRENT USER`. Explain the difference between the temporary password and the active password.

### Exercise 2 — Docker volume preserving credentials

Start Docker Compose with `NEO4J_AUTH_FILE` and a `/data` volume; create the graph in Section 10. Run `docker compose down`, then `docker compose up -d`. Observe that data remains and old credentials still work. Explain why editing the secret file to a new password **does not automatically reset** the account. **Do not run `down -v`**.

### Exercise 3 — Changing password and updating backend

Change the Neo4j account password via `ALTER CURRENT USER`. Then update the Java/Spring Boot app secret, recreate the corresponding Driver/pool, and run `verifyConnectivity()` plus `RETURN 1 AS ok`. Describe what happens if the app keeps using the old credentials.

### Exercise 4 — Classifying errors

One student can open `http://localhost:7474/browser/`, yet `SHOW CURRENT USER` fails with an invalid password. Another student runs `SHOW CURRENT USER` and `RETURN 1` successfully, yet `MERGE` is rejected. Distinguish **authentication** from **authorization** errors and state the right diagnostic step for each.

### Acceptance Checklist

- [ ] Know the initial username and distinguish user from database.
- [ ] Know when to use `set-initial-password` vs. `ALTER CURRENT USER`.
- [ ] Have strong, unique credentials stored safely.
- [ ] Logged in via Browser or Cypher Shell and ran `SHOW CURRENT USER`.
- [ ] Changed the password successfully and **logged back in** with the new password.
- [ ] Verified exact URI, port, Bolt/TLS, and database name.
- [ ] Verified `RETURN 1` and a read/write graph in a test database.
- [ ] Understand that passwords in a Docker volume do not change when editing `NEO4J_AUTH_FILE`.
- [ ] Updated Java/Spring Boot credentials after rotation.
- [ ] Never committed passwords, secret files, or sensitive info to Git.

## 14. Official References

- [Neo4j Operations Manual — Set an initial password](https://neo4j.com/docs/operations-manual/current/configuration/set-initial-password/) — `neo4j-admin dbms set-initial-password` command and password change requirement.
- [Neo4j Operations Manual — Manage users](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-users/) — `SHOW CURRENT USER`, `ALTER CURRENT USER SET PASSWORD`, user management.
- [Neo4j Operations Manual — Getting started with Docker](https://neo4j.com/docs/operations-manual/current/docker/introduction/) — `NEO4J_AUTH`, authentication behavior with existing volumes.
- [Neo4j Operations Manual — Docker Compose](https://neo4j.com/docs/operations-manual/current/docker/docker-compose-standalone/) — secret files and `NEO4J_AUTH_FILE`.
- [Neo4j Operations Manual — Recover admin user and password](https://neo4j.com/docs/operations-manual/current/authentication-authorization/password-and-user-recovery/) — losing administrative access.
- [Neo4j Java Driver Manual — Connection](https://neo4j.com/docs/java-manual/current/connect/) — Driver initialization and `verifyConnectivity()`.
- [Neo4j Browser Manual](https://neo4j.com/docs/browser-manual/current/) — logging in and running Cypher via the UI.
- [Neo4j Aura documentation](https://neo4j.com/docs/aura/) — managed service connections and credentials.

**Key reminder:** Treat **initial passwords** and **passwords stored in the DBMS** as two distinct states. Credential changes must be verified with **a fresh login**, followed by a Cypher test and updating all dependent applications. Both graph data and authentication credentials must be protected across environment changes.
