# Network Binding, Firewalls, and Restricting Administrative Access

MySQL may serve only an application on the same host, serve a group of hosts inside a private network, or accept connections across multiple network zones. Each deployment model requires an appropriate listening scope and access policy. If the server listens on all network interfaces and the database port is widely exposed, outsiders can reach the service before MySQL ever checks an account. Conversely, configuring a firewall alone while ignoring account privileges still lets an allowed host log in with excessive rights.

This lesson focuses on restricting where MySQL accepts connections, filtering connection sources with firewalls, and reserving administrative access for the right people, hosts, and purposes. This is part of mastering MySQL from data design, queries, and transactions through security and operations.

## 1. Layers of Connection Control

A client connection to MySQL typically traverses multiple layers:

| Layer | Question to Answer | Primary Mechanism |
|---|---|---|
| Network path | Does the client have a network route to the server? | Private network, subnet, VPN, routing, bastion |
| Listening interface | Does MySQL accept connections on the destination address? | **bind_address**, **port**, **skip_networking** |
| Firewall | Which sources are allowed to reach the MySQL port? | Host firewall, security group, network ACL |
| MySQL account | Which account may log in from which source host? | **user** and **host** pair |
| Authentication & encryption | Is the identity valid and is data in transit protected? | Password, TLS, certificates |
| Authorization | After logging in, what can the account do? | Privileges, roles, principle of least privilege |

These layers complement one another. **bind_address** decides where MySQL listens; the firewall decides which network sources can reach the port; **user@host** decides whether an account matches the connection source; privileges decide what the account can do after logging in. No single layer completely replaces the others.

For example, an application host may be permitted by the firewall to reach the database server, yet the application account is still restricted to reading and writing one specific schema. An administrative workstation may be allowed access over VPN, yet the DBA account must still use strong authentication and hold only the privileges needed for its work.

## 2. Choosing the Network Address MySQL Listens On

### 2.1. bind_address and port

MySQL uses the **bind_address** server option to choose the IP address on which the service accepts TCP/IP connections. The standard MySQL protocol port is **3306**. When configured with a specific address, the server listens only on that interface; when using a wildcard address such as **0.0.0.0** or **\***, the service can listen across multiple network interfaces.

Common choices:

| Value | Meaning and Use Case |
|---|---|
| **127.0.0.1** | Accepts IPv4 connections only from the host itself. Fits when application and MySQL run on the same machine. |
| **::1** | IPv6 loopback address. Suitable only for local clients using IPv6. |
| **10.20.30.15** | Listens only on the private network address assigned to the server. Fits when applications connect over a controlled internal network. |
| **0.0.0.0** | Listens on all IPv4 interfaces. Consider only when firewall and network layers already strictly limit access sources. |
| **\*** | MySQL wildcard instructing the server to listen on available network interfaces. Evaluate both IPv4 and IPv6 in the deployment environment. |

Do not choose a wildcard simply because it makes remote connections work faster. If a server has both an internal interface and a public interface, listening on all interfaces can expose the service in an unintended network zone. Determine in advance the exact addresses actually used by applications and administrative hosts.

### 2.2. Configuration by Deployment Model

If MySQL serves only processes running on the same host, configure loopback:

~~~ini
[mysqld]
bind-address = 127.0.0.1
port = 3306
~~~

If the application runs on another host in a private network, for example with the MySQL host at **10.20.30.15**, configure:

~~~ini
[mysqld]
bind-address = 10.20.30.15
port = 3306
~~~

The configured address must actually exist on the host when MySQL starts. If there is a typo or the address is not yet assigned to a network interface, the service may fail to start. On multi-homed hosts, choose the interface belonging to the designed application or management network.

Common configuration file paths include **/etc/mysql/mysql.conf.d/mysqld.cnf** on some Debian/Ubuntu distributions, or **/etc/my.cnf** and **/etc/mysql/my.cnf** depending on OS and packaging. Place settings in the **[mysqld]** section, not mistakenly in a client program section.

If TCP/IP connections are unnecessary, disable TCP/IP networking with:

~~~ini
[mysqld]
skip-networking = ON
~~~

Local applications can still connect over a Unix socket on OSes that support sockets; other OS-specific local mechanisms may also be used. Remote TCP/IP clients will not be able to connect. Enable this option only when the architecture genuinely needs no TCP connections.

Changing startup options such as **bind_address**, **port**, or **skip_networking** typically requires restarting the service to take effect. On systemd systems, the service name may be **mysql** or **mysqld**:

~~~bash
sudo systemctl restart mysql
~~~

Use your installation's exact service name and check status after restarting:

~~~bash
sudo systemctl status mysql
sudo ss -lntp | grep ':3306'
~~~

You can check the values MySQL is currently using via SQL:

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN ('bind_address', 'port', 'skip_networking');
~~~

The SQL output shows the server's active configuration; **ss** shows which address the actual TCP socket is listening on. Check both because a valid entry in a config file might not have been loaded by MySQL—for example, if the wrong file or section was edited.

## 3. Restricting Connection Sources with Firewalls

Firewalls filter traffic by source address, destination address, protocol, and port. For MySQL, rules typically allow TCP to port **3306** from identified application or administrative hosts. Firewalls may live on the host itself, in the cloud network layer, or in both places.

For example, the MySQL server is **10.20.30.15** and only application host **10.20.1.25** is permitted to connect. With UFW on Linux, create the rule:

~~~bash
sudo ufw allow from 10.20.1.25 to any port 3306 proto tcp
sudo ufw status numbered
~~~

This rule limits the source to a specific IP address. If there are multiple application servers, create individual rules or use a small approved network range. Before changing default firewall policies remotely, verify that administrative paths such as SSH remain allowed so you do not lock yourself out of the server.

In cloud environments, configure security groups or equivalent firewalls to accept TCP **3306** only from the application tier's security group or required private IP ranges. For example, source **10.20.1.25/32** represents a single IPv4 address. Never open the MySQL port to the entire Internet with **0.0.0.0/0**. If the environment has IPv6, inspect IPv6 rules as well; a strict IPv4 rule does not automatically protect IPv6 paths.

Apply restrictions across appropriate layers:

1. Place MySQL in a private subnet without a public IP unless explicitly justified and approved.
2. Allow only application subnets or security groups to reach the MySQL port.
3. On the host itself, maintain firewall rules allowing only the right sources and ports.
4. Provide a separate administrative path via VPN or bastion; never expose administrative ports to an entire user network.
5. Audit legacy rules, especially any-source rules, after adding new restrictive rules.

Firewalls usually operate at the network layer and do not know which MySQL account is logging in. Conversely, MySQL account rules cannot stop an unauthorized host from probing ports or sending traffic to the server. Therefore, combine firewalls with MySQL configuration and account privilege design.

## 4. Restricting Accounts and Administrative Access

### 4.1. Host-Bound MySQL Accounts

In MySQL, an account is defined by both username and host in the form **'user'@'host'**. The host portion specifies which source machines may use that account. Example:

~~~sql
CREATE USER 'app_runtime'@'10.20.1.25'
  IDENTIFIED BY 'ReplaceWithSecretFromSecretManager';
~~~

That account is only for connections matching the specified source address. Use **localhost** for accounts that log in locally only, or a specific IP address for an application or admin host. Remember that **'report'@'localhost'** and **'report'@'10.20.1.25'** are two separate accounts that can have different passwords and privileges.

Wildcard characters in the host portion, especially **%**, widen the range of machines allowed to log in. An account like **'root'@'%'** creates a very wide administrative access surface and is generally unsuitable for production. Prefer IP addresses or narrow, stable network ranges. If **skip_name_resolve** is enabled, MySQL does not resolve client hostnames; in that case, declare hosts using appropriate IP addresses rather than relying on hostnames.

The account's host portion is an additional authentication layer. It does not replace a firewall, since the firewall still must block traffic from unauthorized sources before it ever reaches MySQL.

### 4.2. Separating Application Accounts and DBA Accounts

Never share an administrative account with an application. The application should hold only the privileges needed on its own schema. Database operators use separate accounts restricted to administrative hosts or VPN networks and granted only task-appropriate privileges.

For example, creating a read-only operational monitoring account from a specific admin host:

~~~sql
CREATE ROLE 'ops_observer';
GRANT PROCESS ON *.* TO 'ops_observer';
GRANT SELECT ON performance_schema.* TO 'ops_observer';

CREATE USER 'ops_readonly'@'10.20.5.10'
  IDENTIFIED BY 'ReplaceWithSecretFromSecretManager'
  REQUIRE SSL;

GRANT 'ops_observer' TO 'ops_readonly'@'10.20.5.10';
SET DEFAULT ROLE 'ops_observer'
  TO 'ops_readonly'@'10.20.5.10';
~~~

This illustrates an observer role; actual privileges must match the job and the running MySQL version. Accounts needing to alter configuration, manage users, back up, or restore require different privileges. Grant exact privileges per task and prefer roles for consistent management. Avoid granting **ALL PRIVILEGES** or **WITH GRANT OPTION** by habit, as they can allow an account to perform or delegate privileges beyond necessity.

High-privilege administrative accounts should log in from controlled admin hosts, over VPN or through a bastion. Never permit direct administration from arbitrary personal devices or the public Internet. When temporary remote access is needed, an SSH tunnel through a bastion can be used:

~~~bash
ssh -L 13306:10.20.30.15:3306 ops@bastion.example
~~~

Once the tunnel is established, the admin workstation connects to port **13306** locally; SSH forwards the connection to the MySQL host over the private network. The bastion must be hardened as critical infrastructure: restrict who can log in, enforce SSH keys, log activity, and allow forwarding only to required destination hosts.

### 4.3. Encrypting Administrative Connections

Administrative connections can carry data-modifying statements, credentials, and sensitive query results. When connections traverse a network, configure TLS and require the account to use encrypted connections:

~~~sql
ALTER USER 'ops_readonly'@'10.20.5.10' REQUIRE SSL;
~~~

The client side must configure the CA and certificate verification mode matching system policy. Modes requiring only TLS ensure transport encryption; identity verification modes also verify the certificate and server hostname. You can verify whether the current session uses TLS:

~~~sql
SHOW SESSION STATUS LIKE 'Ssl_cipher';
~~~

A non-empty **Ssl_cipher** value indicates the session uses a TLS cipher. Also verify client-side certificate and identity verification settings to ensure the connection is talking to the right server.

## 5. Ports and Access Paths to Audit

**3306/TCP** is the standard port for the classic MySQL protocol. If a deployment enables MySQL X Protocol, its default port is typically **33060/TCP**; check the actual configuration and open that port only to applications genuinely using X Protocol. Do not assume protecting 3306 alone restricts every MySQL-related service.

In container environments, check both the bind address inside the container and port-publishing rules on the host. A service listening only on a container network can still be exposed externally if a port is published broadly. In cloud or Kubernetes environments, also audit relevant security groups, network policies, Services, and load balancers.

Some MySQL deployments support a dedicated administrative interface via options such as **admin_address** and **admin_port**. This is an advanced, version-dependent configuration. Use it only after checking documentation for your exact version, identifying clearly which accounts may use that interface, and confining it to a dedicated management network. A separate interface does not replace network-source restrictions and account privileges.

## 6. Testing Connectivity After Configuration

Test from both authorized and unauthorized machines. A configuration is only verified when valid hosts connect cleanly and out-of-scope sources are blocked.

**On the MySQL server**, confirm the listening address and port:

~~~bash
sudo ss -lntp | grep ':3306'
~~~

If the output shows **127.0.0.1:3306**, MySQL accepts only IPv4 loopback connections. If it shows **10.20.30.15:3306**, the service is listening on that private network address. If it shows **0.0.0.0:3306** or a wildcard address, inspect all network interfaces and firewalls carefully.

**From an authorized application host**, test an explicit TCP connection:

~~~bash
mysql --protocol=TCP --host=10.20.30.15 --port=3306 --user=app_runtime --password
~~~

Passing **--password** without a value prompts interactively, avoiding recording the password in shell history. You can separately test port reachability with a network tool such as **nc**:

~~~bash
nc -vz 10.20.30.15 3306
~~~

**From an unauthorized machine**, run the same test. The connection must be blocked at the network layer or rejected by MySQL due to a host mismatch. Record clearly which layer blocked the connection so the test remains repeatable.

After logging in with an administrative or appropriate test account, confirm the matched account and effective privileges:

~~~sql
SELECT CURRENT_USER(), USER();
SHOW GRANTS FOR CURRENT_USER();
~~~

**CURRENT_USER()** reveals the actual MySQL account selected for privilege checks; **USER()** shows the username and host presented by the client at connection time. These two values can differ due to account-matching rules. **SHOW GRANTS** lets you review privileges granted to the active account.

## 7. Diagnosing Common Connection Errors

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Connection reports connection refused | No process listening on address/port; MySQL bound only to loopback; service not running | Check service status, **bind_address**, **port**, and **ss** output |
| Connection times out | Firewall blocking, bad routing, security group or network ACL denying | Check source/destination, TCP 3306, routes, and firewall rules at every layer |
| Reaches right host, yet reports Access denied | Wrong password, host mismatch, locked account, or unmet TLS requirement | Check user-host, account state, password, **REQUIRE SSL**, and client error |
| Local connection succeeds, yet remote connection fails | MySQL bound only to loopback, TCP disabled, or firewall not allowing source host | Check **bind_address**, **skip_networking**, and firewall |
| Application connects, yet admin host cannot connect | Firewall permits only app subnet or admin account disallows admin host | Check dedicated admin rules and **user@host** account |
| Only some IPv6 clients fail to connect | IPv6 bind address or IPv6 firewall rules not configured | Check IPv6 listener and IPv6 rules independently of IPv4 |

When troubleshooting, separate errors into three buckets. **Refused** usually means no listener matches or the connection was actively rejected immediately. **Timeout** usually points to a firewall or network routing issue. **Access denied** indicates the client reached MySQL and the failure lies in authentication, account matching, or login requirements. Distinguishing these buckets prevents unnecessary privilege changes or opening firewalls blindly.

## 8. Safe Deployment Workflow

A database network change should follow an auditable sequence:

1. Inventory application hosts, admin hosts, subnets, IP addresses, and ports genuinely required.
2. Select an appropriate specific bind address; confirm that address is already assigned to the host.
3. Create firewall rules for exact sources and ports; check IPv4, IPv6, and cloud firewalls if applicable.
4. Create or audit MySQL accounts by user-host pair; separate application accounts from administrative accounts.
5. Grant task-specific privileges, require TLS for sensitive connections, and store secrets in a secret management system.
6. Restart MySQL if the change requires a restart; check service status and listening address.
7. Test connecting from both authorized and unauthorized sources; inspect privileges with **SHOW GRANTS**.
8. Record the configuration, approver, timestamp, and test results to support operations and rollback when needed.

Never change bind addresses or firewalls on a production server without confirming a fallback management path. If a change prevents the service from starting or cuts off application connectivity, know ahead of time how to restore config files and network rules to the verified baseline.

## 9. Hands-on Scenario

A system has three components:

- MySQL host: **10.20.30.15**.
- Application host: **10.20.1.25**.
- Administrative host: **10.20.5.10**, accessible only over VPN.

Requirements: the application connects to MySQL to work with its data; the admin host can monitor and perform operational tasks; all other hosts are prohibited from opening direct connections to the MySQL port.

Propose a configuration following these steps:

1. Set **bind_address** to the private network address **10.20.30.15** assuming it is assigned to the host.
2. Create firewall rules permitting TCP 3306 from **10.20.1.25** and **10.20.5.10**; never expose the port to the entire Internet.
3. Create an application account with host **10.20.1.25** and grant privileges only on the application schema.
4. Create a separate administrative or monitoring account with host **10.20.5.10**, requiring TLS and granting exact task-specific privileges.
5. Test from both authorized hosts and a third host outside those two addresses. Confirm valid connections work, out-of-scope connections are blocked, and application account privileges do not extend beyond the required schema.

What matters is not merely that connections succeed. A sound design must also demonstrate that every source gets only the required network path, accounts hold privileges matching their roles, and changes remain auditable.

## 10. Self-Check Questions

1. How does **bind_address** differ from a firewall? Why are both needed?
2. When **bind_address = 127.0.0.1** is set, can an application on another machine connect to MySQL via TCP? Explain.
3. Why can a **'root'@'%'** account introduce severe risk in production?
4. How does a connection timeout differ from an Access denied error? Which layer would you check first?
5. If MySQL serves only applications inside a private subnet, which layers must be reviewed to ensure port 3306 is not exposed to the Internet?
6. Why should DBA accounts be separated from application runtime accounts and require TLS for remote administration?

Use these questions to test your ability to explain and operate the configuration. A secure design must clearly identify which address is listening, which sources may cross the firewall, which accounts may log in, and what operations each account can perform.
