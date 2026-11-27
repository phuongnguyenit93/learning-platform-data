# Network Segmentation, Firewalls, and Administrative Access Control

PostgreSQL often stores critical application data, so network paths to the database server must be strictly limited. Only components with a legitimate need should be allowed to reach the PostgreSQL port; administrative connections must travel over a dedicated path with strong authentication, logging, and revocation capability.

Protecting PostgreSQL does not rely on a single setting. Network segmentation limits where the server can be reached from; firewalls control packet flows; listen settings and `pg_hba.conf` restrict connections at the PostgreSQL layer; TLS protects data in transit; and roles and privileges determine what connected users can do. These layers complement one another and must be tested as a unified system.

## 1. Design Objectives and Principles

A secure deployment design should meet the following goals:

- The PostgreSQL server has no public IP address unless the application has a specific approved requirement.
- Only designated application subnets or server groups may connect to the database port.
- Administrative access passes through a VPN, bastion host, or remote access platform with MFA and session logging.
- Connections among applications, admin hosts, replicas, and backup services are restricted strictly to required paths.
- Network connections use TLS with server identity verification.
- `pg_hba.conf` allows only defined sources, databases, roles, and authentication methods.
- Application roles hold no OS admin privileges, `SUPERUSER`, or `BYPASSRLS`.
- Logs, alerts, and revocation procedures exist when servers, accounts, or connection sources change.

Changing the default port 5432 should not be considered a primary defense. Attackers can scan ports; what matters is that the database port is reachable only from authorized sources and PostgreSQL continues authenticating every connection.

## 2. Network Segmentation for PostgreSQL

Network segmentation divides infrastructure into zones with distinct trust levels and functions. Database servers should reside in private subnets or dedicated data zones. Application servers reach the database over internal networks; administrators pass through management zones; replication and backups use separately scoped paths.

A reference model:

~~~mermaid
flowchart TB
    U["Users / Internet"] --> W["Load balancer / Web tier"]
    W --> A["Application subnet"]
    A -->|TCP 5432| D["Private database subnet"]
    O["Administrators"] --> V["VPN / Bastion / MFA"]
    V -->|Authorized admin path| D
    D -->|Replication| R["Replica subnet"]
    D -->|Controlled backup| B["Backup storage"]
    M["Monitoring subnet"] -->|Metrics / Logs| D
~~~

Zones in this diagram can be implemented via VPC/VNet subnets, VLANs, security groups, firewall zones, or Kubernetes network policies. You do not necessarily need a separate subnet for every function, but the source and destination of every flow must be clearly defined.

### 2.1. Application Subnet

Contains backend services requiring database access. Firewalls allow only identified application workload groups to connect to PostgreSQL's private address on TCP 5432.

Do not open the database port to the entire internal network simply because servers share a VPC. A build box, development host, test runner, or compromised workload can become a lateral-movement pivot if every internal source is allowed access.

### 2.2. Database Subnet

Contains the primary and replicas if replication is used. This zone receives no direct traffic from the Internet. Open only required flows:

- Application to PostgreSQL: the PostgreSQL TCP port, typically 5432.
- Bastion or management system to PostgreSQL: only from verified administrative sources.
- Primary to replica or replica to primary: replication flows matching the actual topology.
- Monitoring to exporter or metrics endpoints: only from monitoring hosts.
- Database to backup endpoints: only required protocols and storage targets.

When running multiple PostgreSQL instances, grant network permissions per group separately. Never open an entire port range or whole subnet just to avoid updating firewall rules when adding replicas.

### 2.3. Management Subnet

Contains bastion hosts, VPN gateways, or remote administration systems. Administrators authenticate to this tier first, and only then access database servers within granted permissions.

A bastion should not become a general-purpose shared server. Restrict installed software, login accounts, `sudo` rights, Internet access, and forwarding to unrelated networks. Monitor administrative sessions and revoke access when personnel change responsibilities.

### 2.4. Replication and Backup Subnets

Replication and backups are separate service flows. Allow only the corresponding primary, replica, or backup worker addresses to connect in the exact direction and protocol required.

Physical streaming replication typically connects to PostgreSQL using the special `replication` database and a role with the `REPLICATION` attribute. Logical replication connects to a specific database using privileges suited for publications/subscriptions. Do not grant `REPLICATION` or full-data read rights to application roles just to reuse an account.

Backup workers need read access or permission to invoke backup tools as designed. Restrict delete and administrative privileges on backup repositories; backups must be protected from simultaneous deletion if a database host is compromised.

## 3. Mapping Network Flows Before Opening Firewalls

Before writing rules, inventory all connection flows. Document each flow with:

| Source | Destination | Protocol/Port | Purpose | Ownership |
|---|---|---|---|---|
| Application subnet | PostgreSQL primary | TCP 5432 | Business queries | Application team |
| Bastion / admin subnet | PostgreSQL | TCP 5432 | Database administration | DBA |
| Primary | Replica | TCP 5432 | Physical/logical replication per config | DBA |
| Monitoring host | Metrics exporter | Configured exporter port | Metrics collection | SRE |
| Backup worker | PostgreSQL | TCP 5432 or chosen backup channel | Backups | DBA / Backup |
| PostgreSQL host | DNS, NTP, logging, backup endpoint | Per approved service | Supporting infrastructure | Platform |

This table forms the basis for security groups, network ACLs, host firewalls, and orchestrator policies. Clearly distinguish:

- **Inbound:** connections entering the database server.
- **Outbound:** connections from the database to DNS, NTP, logging, backups, or other systems.
- **East-west:** connections between hosts within the internal environment.
- **Administrative:** connections initiated by humans or admin tooling.

Do not assume all outbound traffic is safe. A compromised database host can abuse broad outbound access to exfiltrate data or contact command-and-control infrastructure. Allow only necessary outbound targets while keeping DNS, NTP, logging, and backups operational.

## 4. Firewalls Across Infrastructure Layers

Firewalls can be enforced at multiple layers. Each layer governs part of the connection path.

### 4.1. Network Firewalls and Security Groups

In cloud environments, security groups are usually stateful firewalls attached to network interfaces or resources. Sources can be specified by the application server's security group rather than wide IP ranges. Subnet-level Network ACLs are often stateless, requiring rules for both inbound and outbound traffic, including ephemeral ports.

Logical policy example:

| Target Resource | Allowed Source | Target Port | Policy |
|---|---|---:|---|
| PostgreSQL primary | Application security group | TCP 5432 | Allow |
| PostgreSQL primary | Admin/bastion security group | TCP 5432 | Allow |
| PostgreSQL primary | Replica security group | TCP 5432 | Allow per topology |
| PostgreSQL primary | Internet / all other sources | TCP 5432 | Deny |
| PostgreSQL primary | Unrelated internal networks | TCP 5432 | Deny |

Group names and reference syntax depend on the cloud provider. Inspect the actual rules attached to network interfaces, route tables, and subnets; a correct security group paired with misconfigured routes or another firewall can still leave paths unexpectedly open.

### 4.2. Host Firewalls

A host firewall adds a control layer directly on the OS running PostgreSQL. It helps restrict sources even if external network rules are misconfigured.

Example with UFW on Linux, assuming the database host accepts application connections from `10.20.10.0/24` and admin connections from `10.20.30.0/24`:

~~~bash
sudo ufw default deny incoming
sudo ufw default allow outgoing

sudo ufw allow from 10.20.10.0/24 to any port 5432 proto tcp
sudo ufw allow from 10.20.30.0/24 to any port 5432 proto tcp

sudo ufw status numbered
~~~

These addresses are illustrative networks; replace them with verified real CIDRs. Before enabling a firewall on a remote host, ensure a rule exists for your current OS management channel, such as SSH from the bastion. Locking out the admin path can prevent DBAs from recovering configuration.

Do not run multiple tools concurrently to manage the same rule set without understanding their ordering and interactions. Choose one authoritative configuration source, manage it via IaC or config management, record changes, and verify status after applying.

### 4.3. Firewalls in Kubernetes

If PostgreSQL runs outside Kubernetes, NetworkPolicies can restrict which pods may connect to the database. If PostgreSQL runs inside the cluster, policies must govern both traffic to database pods and admin/replication flows.

Example NetworkPolicy allowing pods labeled `app: orders-api` in the `production` namespace to connect to database pods on TCP 5432:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-orders-to-postgres
  namespace: database
spec:
  podSelector:
    matchLabels:
      app: postgres
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: production
          podSelector:
            matchLabels:
              app: orders-api
      ports:
        - protocol: TCP
          port: 5432
~~~

This policy only takes effect if the cluster's CNI plugin enforces NetworkPolicies. Verify namespace and pod labels match reality; mismatched labels can block legitimate traffic or fail to match intended workloads. NetworkPolicies also do not replace `pg_hba.conf` or database privileges.

## 5. Restricting Addresses PostgreSQL Listens On

Firewalls determine which packets reach the host; PostgreSQL also controls which interfaces the database process listens on.

Check current configuration:

~~~sql
SHOW listen_addresses;
SHOW port;
SHOW config_file;
SHOW hba_file;
~~~

The default `listen_addresses` is typically `localhost`. In production, specific private interface addresses can be configured:

~~~conf
listen_addresses = '127.0.0.1,10.20.0.15'
port = 5432
~~~

Here `10.20.0.15` is an illustrative private IP of the database server. Declare only addresses actually bound on the host. If listening on multiple interfaces is required, document why and ensure firewalls restrict each path.

Setting `'*'` instructs PostgreSQL to listen on all available interfaces. Use this only when required by the architecture and when firewalls, routing, and `pg_hba.conf` are tightly locked down. Listening on all interfaces does not automatically expose the database port to the Internet, but expands blast radius if firewalls or routes are misconfigured.

Changing `listen_addresses` or `port` requires restarting PostgreSQL to take effect. After restarting, verify the process listens on the expected address and port, and test connections from both an allowed source and a denied source.

## 6. Using pg_hba.conf to Restrict Connections

`pg_hba.conf` (host-based authentication) is PostgreSQL's connection access control layer. Each line specifies connection type, database, role, client address, and authentication method.

General format:

~~~conf
# TYPE  DATABASE  USER  ADDRESS  METHOD  [OPTIONS]
~~~

Common line types:

- `local`: connections over Unix-domain sockets on the host.
- `host`: TCP connections, with or without SSL.
- `hostssl`: TCP connections using TLS only.
- `hostnossl`: TCP connections without TLS only.

Example allowing only applications and DBAs to connect over TLS from two separate subnets:

~~~conf
# Application: only appdb database and app_runtime role
hostssl  appdb  app_runtime  10.20.10.0/24  scram-sha-256

# Administration: managed databases and db_admin role only
hostssl  all    db_admin    10.20.30.0/24  scram-sha-256

# Physical replication: designated replica address only
hostssl  replication  repl_user  10.20.40.10/32  scram-sha-256
~~~

This example assumes the corresponding roles exist, database privileges are granted, and TLS is configured. For logical replication, the `DATABASE` field in `pg_hba.conf` is typically the specific database name rather than the special `replication` keyword used for physical replication connections.

### 6.1. Rule Order Matters

PostgreSQL evaluates lines top-to-bottom and uses the first line matching connection type, address, database, and user. If authentication fails on that matching line, PostgreSQL does not try subsequent lines. Hence, an overly broad rule near the top can nullify specific rules below it.

Never add rules like this in production:

~~~conf
# Insecure: allows all addresses to access the database
host  all  all  0.0.0.0/0  trust
~~~

`trust` bypasses password authentication for matching connections. `0.0.0.0/0` covers all IPv4 addresses; IPv6 has the corresponding `::/0`. Never use `trust` for TCP connections from untrusted networks. Broad `host` rules can also permit non-TLS connections; prefer `hostssl` for paths requiring encryption.

### 6.2. Authentication Methods

`SCRAM-SHA-256` is the recommended password authentication method for modern PostgreSQL deployments. It is stronger than the legacy `md5` mechanism. Verify server and client versions before switching; older clients may lack SCRAM support.

Set password encryption for new/updated passwords:

~~~conf
password_encryption = 'scram-sha-256'
~~~

Changing this setting affects how passwords are stored when set or altered. To migrate existing roles to SCRAM, reset passwords for the affected roles after verifying client compatibility.

Inspect parsed HBA rules using the `pg_hba_file_rules` view:

~~~sql
SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_hba_file_rules
ORDER BY line_number;
~~~

Find lines with errors:

~~~sql
SELECT line_number, error
FROM pg_hba_file_rules
WHERE error IS NOT NULL;
~~~

After editing the file, tell PostgreSQL to reload configuration:

~~~sql
SELECT pg_reload_conf();
~~~

`pg_reload_conf()` returning `true` indicates the reload signal was sent successfully; still inspect server logs and re-verify configuration. Modifying `pg_hba.conf` normally requires only a reload, not a full PostgreSQL restart. If syntax errors exist, logs and the inspection view pinpoint the line to fix.

## 7. Encrypting and Verifying Connections with TLS

TLS protects data traveling between client and server, including credentials and query payloads. Enabling SSL on the server alone is insufficient; clients must verify the server certificate to avoid connecting to an imposter server.

Reference server configuration:

~~~conf
ssl = on
ssl_cert_file = 'server.crt'
ssl_key_file = 'server.key'
ssl_min_protocol_version = 'TLSv1.2'
~~~

Certificate paths depend on the installation layout. Private keys must be protected with strict OS permissions; on Linux, typically only the PostgreSQL service account may read the key. Never commit private keys to source control or public images.

`libpq` clients should use `sslmode=verify-full` and a trusted CA:

~~~bash
psql "host=db.internal.example port=5432 dbname=appdb user=app_runtime sslmode=verify-full sslrootcert=/etc/ssl/certs/company-db-ca.crt"
~~~

With `verify-full`, the client checks both the certificate chain and that the hostname matches the connection target. The server certificate needs an appropriate Subject Alternative Name (SAN). If connecting by IP instead of hostname, the certificate must include an IP SAN; prefer stable internal DNS names for primaries, replicas, and failover endpoints.

`require`, `verify-ca`, and `verify-full` enforce different checks. `require` encrypts traffic without fully verifying server identity; `verify-ca` checks the CA without checking the hostname; `verify-full` verifies both the certificate chain and hostname. For production connections, prefer `verify-full`.

If using client certificates, design issuance, distribution, renewal, and revocation lifecycles. Client certificates do not replace database roles: PostgreSQL still maps the connection identity to a role and enforces privileges.

## 8. Designing Administrative Access Control

Network access controls only who can reach the PostgreSQL port. After connecting, PostgreSQL checks roles and database privileges. These two layers must be designed independently.

### 8.1. Separating Application and Administrative Accounts

Do not share one `postgres` or `SUPERUSER` account across applications, migrations, backups, and administrators. Each purpose needs its own role:

| Role | Purpose | Recommended Privileges |
|---|---|---|
| `app_runtime` | Business backend processing | Only needed read/write grants on schemas and tables |
| `db_migrator` | Deploying schema changes | Required DDL privileges during migrations |
| `db_monitor` | Collecting metrics | Minimal monitoring rights; no business data reads unless needed |
| `repl_user` | Replication | `LOGIN` and `REPLICATION` as required |
| `db_admin` | Routine DBA tasks | Assigned administrative grants, audited |
| Break-glass role | Emergency recovery | `SUPERUSER` only when strictly necessary, stored and invoked per dedicated workflow |

Group roles can be created with `NOLOGIN` and granted to approved login roles. Personal accounts should have individual identities so logs trace who performed each action. Avoid sharing a single DBA password across a team.

### 8.2. DBA Access Paths

A standard administrative flow looks like:

1. Administrator authenticates to a VPN or remote access platform with MFA.
2. The platform verifies device, identity, and authorization.
3. Administrator opens a session to a bastion or approved management tool.
4. Firewalls allow only the bastion to connect to PostgreSQL on the required port.
5. PostgreSQL authenticates the DBA role via `pg_hba.conf` and strong authentication.
6. Administrative actions are logged, tied to the individual and corresponding ticket/change when required.

Do not expose port 5432 to the Internet so DBAs can connect from laptops anywhere. If remote operations are required, use a VPN, bastion, or zero-trust solution with identity, MFA, and session logging.

### 8.3. Managing High Privileges

`SUPERUSER` bypasses most controls inside PostgreSQL, including RLS. Therefore:

- Never grant `SUPERUSER` to application, routine migration, or monitoring accounts.
- Use high-privilege accounts only when truly necessary.
- Store credentials in a secrets manager or controlled password vault.
- Prefer temporary privilege elevation with revocation once work completes.
- Protect break-glass accounts with MFA, access controls, and formal audit logging.
- Periodically audit memberships and `SUPERUSER`, `CREATEROLE`, `CREATEDB`, `REPLICATION`, and `BYPASSRLS` attributes.

Inspect role attributes:

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolcreatedb,
    rolcreaterole,
    rolreplication,
    rolbypassrls
FROM pg_roles
ORDER BY rolname;
~~~

Role lists and memberships are part of security configuration. When staff leave or workloads are retired, revoke associated memberships, credentials, certificates, and network rules.

## 9. Controlling Administrative Connections via Bastion or Tunnel

A bastion is an intermediary allowing administrators to reach a private network. It does not make the database secure by itself; you must protect the bastion, authentication channel, and forwarding path.

Key principles:

- The bastion accepts admin connections only from VPN or authorized identities/devices.
- Never store database passwords in scripts or unprotected config files on the bastion.
- Use SSH keys or managed authentication; disable default accounts and weak passwords.
- Restrict who can open tunnels and which destinations tunnels can reach.
- Log sessions, timestamps, identities, and target endpoints.
- Keep the OS patched, minimize installed packages, and remove unnecessary services.

SSH local port forwarding can establish a temporary tunnel:

~~~bash
ssh -N -L 15432:db.internal.example:5432 admin@bastion.internal.example
~~~

Once the tunnel is active, the client connects to local port 15432 while preserving TLS certificate hostname verification. With `libpq`, you can set `host` to the hostname in the certificate, `hostaddr` to the tunnel loopback address, and set the local port accordingly. Exact client settings must be verified with your DNS and client library; never disable `verify-full` just to make a tunnel work.

In cloud platforms, managed session services can replace traditional SSH bastions. Whichever approach is used, the principles remain identity-based access, destination restriction, MFA, time-boxing, and auditing.

## 10. Testing Allowed and Denied Access Paths

Do not test only from the database host. Test from different network zones to verify firewalls and PostgreSQL work together as intended.

### 10.1. Testing from Authorized Clients

From the application subnet, test DNS and TCP:

~~~bash
getent hosts db.internal.example
nc -vz db.internal.example 5432
~~~

Then connect with TLS and query session context:

~~~bash
psql "host=db.internal.example port=5432 dbname=appdb user=app_runtime sslmode=verify-full sslrootcert=/path/company-ca.crt"
~~~

In the SQL session:

~~~sql
SELECT
    current_database(),
    session_user,
    current_user,
    inet_server_addr(),
    inet_server_port(),
    inet_client_addr();
~~~

This confirms the database, role, server address, and client address seen by PostgreSQL. If traffic passes through NAT or a proxy, `inet_client_addr()` may show the intermediary address; correlate with logs and actual topology.

### 10.2. Testing from Unauthorized Sources

From a host in an unauthorized subnet, probe TCP 5432. The connection should be blocked at the firewall layer or have no route to the database zone. Do not send passwords or attempt repeated logins.

When a firewall lets packets reach PostgreSQL but `pg_hba.conf` has no matching rule, clients typically receive an error like `no pg_hba.conf entry`. That indicates the connection reached PostgreSQL and was rejected at the HBA layer. If the firewall blocks first, you typically see a timeout or network connection error depending on the device.

Distinguishing these two outcomes identifies which layer needs inspection. Record source, target, timestamp, rejection layer, and relevant logs for negative tests.

### 10.3. Testing the Administrative Path Separately

Verify that:

- Users without VPN/bastion access cannot reach the management subnet.
- Users with bastion access but without DBA permissions cannot log into admin roles.
- DBAs can connect from authorized sources and are rejected from other sources.
- DBA roles are not used in place of application roles in backend configs.
- Revoking VPN, SSH, memberships, or certificates immediately disables the corresponding path.

### 10.4. Testing After Failover

When using primary/replicas or HA services, test endpoints after failover as well. Firewalls and `pg_hba.conf` must allow clients to reach the new node or endpoint. Do not open an entire subnet just to avoid updating rules during primary switchovers; instead, manage database group identities or automate rule updates alongside failover.

Also verify endpoint TLS certificates, DNS, routes, roles, and replication permissions after switchover. A reachable endpoint serving a certificate that mismatches the hostname must still be rejected by `verify-full` clients.

## 11. Monitoring and Auditing Access

Network configurations evolve over time. Record successful connections, failed connections, configuration changes, and privileged operations.

Basic logging settings:

~~~conf
log_connections = on
log_disconnections = on
log_line_prefix = '%m [%p] user=%u db=%d client=%h '
~~~

Exact options and log details vary by PostgreSQL version and logging pipeline. Inspect actual logs after config changes. Avoid logging full SQL statements or sensitive data unnecessarily; logs must have retention policies, read access controls, and expiration schedules.

Inspect current connections:

~~~sql
SELECT
    pid,
    usename,
    datname,
    client_addr,
    application_name,
    state,
    backend_start
FROM pg_stat_activity
ORDER BY backend_start DESC;
~~~

Monitor at least these signals:

- Connections from client addresses outside approved lists.
- Spikes or repeated authentication failures.
- High-privilege role usage outside expected maintenance windows.
- Changes to `pg_hba.conf`, `listen_addresses`, firewalls, or security groups.
- TLS certificates nearing expiration or no longer trusted.
- Interrupted replication or incomplete backups.
- Connections from developer subnets or personal workstations to production databases.

Use PostgreSQL logging, audit extensions such as `pgAudit` when stricter auditing is needed, alongside logs from firewalls, cloud control planes, bastions, and OS hosts. Synchronize clocks via NTP so events across systems correlate accurately.

## 12. Procedure for Deploying Network and Access Changes

Modifying firewalls or `pg_hba.conf` can disrupt applications or lock out administrative paths. Deploy in verifiable, rollbackable steps.

1. **Build inventory:** record primary, replicas, app subnets, admin subnets, backups, monitoring, DNS, and dependent endpoints.
2. **Verify flows:** confirm source, destination, port, protocol, owner, and business justification.
3. **Design rules:** create specific source/target rules; include return paths if using stateless firewalls.
4. **Prepare recovery access:** confirm console or out-of-band management remains usable; back up current configs.
5. **Update firewalls:** add new allow rules first, verify legitimate flows, then remove obsolete broad rules.
6. **Update PostgreSQL:** restrict `listen_addresses`, TLS, and `pg_hba.conf`; check syntax and reload/restart per change type.
7. **Test connectivity:** test from both allowed and denied sources; verify TLS, roles, and databases.
8. **Monitor:** watch application, PostgreSQL, firewall, and bastion logs after rollout.
9. **Finalize change:** archive approved config, approver, test results, and rollback plan.

Changing `listen_addresses` requires restarting PostgreSQL, so schedule maintenance and prepare HA switchovers if high availability is required. Changing `pg_hba.conf` normally requires only a reload. Firewall changes can apply immediately; keep a rollback rule or open console session ready to avoid locking yourself out.

Do not delete old rules immediately before confirming all applications, jobs, migrations, backups, and monitoring have migrated to new paths. Infrequent connections may only appear during backups or maintenance windows.

## 13. Common Deployment Mistakes

- **Placing PostgreSQL in a public subnet:** expands the attack surface and over-relies on firewall rules.
- **Opening TCP 5432 to `0.0.0.0/0` or `::/0`:** lets any source probe the database.
- **Relying solely on firewalls:** if network rules widen, PostgreSQL still needs HBA, TLS, and role privileges to protect data.
- **Relying solely on `pg_hba.conf`:** the process may still listen on unintended interfaces; HBA does not replace firewalls.
- **Using `trust` or weak passwords:** undermines identity verification.
- **Treating `sslmode=require` as server identity verification:** traffic is encrypted, but server identity is not checked as thoroughly as `verify-full`.
- **Sharing DBA accounts:** hinders attribution and individual revocation.
- **Granting `SUPERUSER` to applications:** lets applications bypass database controls, including RLS.
- **Forgetting IPv6:** strict IPv4 firewall rules do not guarantee IPv6 is also restricted.
- **Forgetting replication and backups:** applications keep working while replicas or backup workers get blocked after tightening rules.
- **Forgetting connection pools or failover:** new endpoints lack matching rules, DNS, or certificates.
- **Not auditing changes:** temporary rules linger and become uncontrolled access paths.

## 14. Operations Checklist

Before putting PostgreSQL into production or changing access paths, confirm:

- [ ] Database resides in a private network zone with no unintended public IP.
- [ ] Only identified application, admin, replication, backup, and monitoring sources are permitted.
- [ ] Security groups, network ACLs, and host firewalls are verified for both inbound and outbound flows.
- [ ] Both IPv4 and IPv6 have explicit policies.
- [ ] `listen_addresses` includes only required interfaces.
- [ ] `pg_hba.conf` contains no overly broad rules or unsafe `trust` entries.
- [ ] Production connections use TLS and clients verify hostnames with `sslmode=verify-full`.
- [ ] Applications, migrations, replication, monitoring, and DBAs use separate roles.
- [ ] `SUPERUSER` and `BYPASSRLS` are not granted to application roles.
- [ ] Administrative paths require MFA, time-bound access, auditing, and break-glass procedures.
- [ ] Authorized connections succeed and unauthorized sources are rejected.
- [ ] PostgreSQL, firewall, and bastion logs are retained, monitored, and protected.
- [ ] Rollback plans and out-of-band recovery channels exist in case changes break connectivity.

Network segmentation, firewalls, and administrative access controls should be treated as a contract among application, DBA, and platform teams. Every connection must have a defined source, destination, purpose, and owner. When a flow is no longer needed, revoke its network rules, credentials, and database privileges. This ensures PostgreSQL serves only approved workloads while keeping administrative operations traceable and controlled.
