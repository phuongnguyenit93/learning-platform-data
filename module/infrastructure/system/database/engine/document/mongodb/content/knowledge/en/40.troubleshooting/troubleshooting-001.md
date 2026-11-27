# Diagnosing Connection, DNS, TLS, and Server Selection Timeout Errors in MongoDB

## 1. Understanding Connection Failures Layer by Layer

A Java/Spring Data MongoDB application may report:

```text
com.mongodb.MongoTimeoutException:
Timed out after 30000 ms while waiting for a server
that matches ReadPreferenceServerSelector{readPreference=primary}
```

This **does not mean that MongoDB Server is shut down**. The message only states that the MongoDB Java Driver **could not select an eligible server within the server-selection timeout**. The root cause may belong to several layers:

- The URI has an incorrect hostname, port, database, `replicaSet`, or options.
- DNS cannot find the SRV/TXT/A/AAAA records, or the application host uses a different resolver than your laptop.
- A firewall, route, VPN, security group, or MongoDB Atlas IP access list is blocking TCP.
- TCP reaches the server, but the TLS handshake fails due to CA, hostname, expired certificate, SNI, TLS version, or mTLS.
- TCP/TLS works, but the replica set has no **primary** suitable for the operation, the server is undergoing an election, or advertised member hostnames are unreachable.
- A server was found, but authentication failed due to an incorrect user/password/`authSource`.
- The connection pool is exhausted and checkout waits too long; this is a different failure layer from server selection, even though it can also surface as a timeout.
- The application creates too many `MongoClient` instances, triggers a retry storm, or is blocked by a proxy/sidecar.

### 1.1. Stage Diagram

```text
Java / Spring Data Application
        |
        v
[1] Parse MongoDB URI
        |
        v
[2] DNS
    mongodb+srv: SRV -> target names -> A/AAAA; TXT options
    mongodb:     A/AAAA for hosts in the seed list
        |
        v
[3] TCP network / routing / firewall / Atlas allow-list
        |
        v
[4] TLS handshake
    TLS version, chain of trust, hostname/SAN, SNI, mTLS
        |
        v
[5] MongoDB hello / SDAM topology discovery
    standalone / replica set / mongos; roles, read preference
        |
        v
[6] Authentication + authorization
    SCRAM, X.509, authSource, roles
        |
        v
[7] Pool checkout and command execution
        |
        v
[8] Query result / error
```

**Rule:** check the **earliest broken layer** first. Increasing `serverSelectionTimeoutMS` will not fix wrong DNS; adding an index will not fix TLS; changing the password will not make a TCP route passable.

### 1.2. Learning Outcomes

After this lesson, you will be able to:

1. Read an error chain and distinguish between DNS, TCP, TLS, authentication, server discovery, and pool timeouts.
2. Validate `mongodb://` and `mongodb+srv://` connection strings properly.
3. Use `Resolve-DnsName`/`nslookup`, `dig`, `Test-NetConnection`, `nc`, and `openssl` depending on the operating system.
4. Read TLS errors and verify SAN/CA/truststore certificates without disabling hostname verification as a "fix".
5. Read `MongoTimeoutException` and the Java Driver's **cluster description**.
6. Distinguish `serverSelectionTimeoutMS`, `connectTimeoutMS`, `socketTimeoutMS`, pool wait, and CSOT.
7. Investigate Atlas IP access lists, egress IPs, Private Endpoints, and split-horizon DNS.
8. Analyze replica set primary/secondary roles, read preference, `directConnection`, and advertised member hostnames.
9. Verify real connectivity with a `ping` command rather than relying on `MongoClient` creation succeeding.
10. Create a runbook with evidence, timestamps, incident scope, owner, and recovery steps.

---

## 2. Reading Error Messages: Outermost Exception vs. Deepest Cause

A Java stack trace can contain **multiple wrapper layers**:

```text
org.springframework.dao.DataAccessResourceFailureException
  caused by: com.mongodb.MongoTimeoutException:
    Timed out after 30000 ms while waiting for a server
    ...
    caused by: com.mongodb.MongoSocketOpenException:
      Exception opening socket
      caused by: java.net.ConnectException:
        Connection refused
```

How to read it:

1. Note the outermost exception type to understand how the framework reacts.
2. Read the **MongoDB exception**: `MongoTimeoutException`, `MongoSecurityException`, `MongoSocketException`, etc.
3. Read the **root cause**: `UnknownHostException`, `ConnectException`, `SocketTimeoutException`, `SSLHandshakeException`.
4. Read the **cluster description** to see how many nodes the driver sees and what roles they have.
5. Correlate the timestamp with logs/metrics from MongoDB, DNS, network, and deployments.
6. Do not strip details like `type=...`, `state=...`, `exception=...` when sending technical reports; however, **redact credentials and sensitive content**.

### 2.1. Quick Identification Table

| Clue in error/log | First layer to check | Do not jump to conclusions |
| --- | --- | --- |
| `UnknownHostException`, `ENOTFOUND`, `NXDOMAIN` | DNS/hostname | The DB is definitely shut down |
| `querySrv ECONNREFUSED` | DNS SRV resolver/port 53 | MongoDB TCP port 27017 is definitely blocked |
| `No SRV records`, DNS `SERVFAIL` | Resolver, DNS forwarding, SRV service | Wrong password |
| `Connection refused` | TCP, process listener, firewall reject | Wrong TLS cert |
| `Connection timed out` | Route/firewall drop/port/network | There is definitely no primary |
| `No route to host` | IP route/security network | Changing the MongoDB user will help |
| `SSLHandshakeException` | TLS protocol/cert chain/hostname | Just increasing timeout will fix it |
| `PKIX path building failed` | Java truststore/CA chain | Server is not running |
| `No subject alternative names matching` | Certificate SAN/hostname | Just need to change the password |
| `Authentication failed`, code 18 | User/password/authSource/mechanism | DNS is always broken |
| `Timed out ... ReadPreferenceServerSelector` | SDAM and any underlying errors | Immediately conclude server is offline |
| `state=CONNECTING`, `type=UNKNOWN` | Opening socket/hello/heartbeat | Server has already been selected |
| `REPLICA_SET_SECONDARY` while waiting for `primary` | Role/primary/election/read preference | Secondary network error |
| `Timed out waiting for a connection from the pool` | Pool checkout, concurrency, server load | Wrong SRV records |
| `Too many connections` | Limits/pool/client churn | Increase `maxPoolSize` indefinitely |

This is a **hypothesis table**, not a substitute for reading the root exception and actual conditions.

---

## 3. First Five-Step Incident Runbook

When receiving an "application cannot connect to MongoDB" incident, follow this sequence:

1. **Scope:** one pod, all pods, one AZ/region, production only, or laptop only? Start time in UTC? Any recent rollout, network policy, or certificate rotation?
2. **URI and topology:** which URI format is used; are the cluster, seed host, port, TLS, replicaSet, and authSource correct? **Redact** all usernames/passwords/tokens before sharing.
3. **DNS and TCP from the exact runtime:** test from the **exact failing machine/pod/container**, not just from a working laptop.
4. **TLS and authentication:** if TCP succeeds but Java cannot connect, inspect the handshake/cert/truststore or auth error.
5. **SDAM, server selection, and pool:** read the cluster description, member roles, timeouts, and checkout waits; run `ping` using the driver in the same environment.

### 3.1. Incident Recording Template

```text
Incident ID:                 ...
First seen (UTC):            ...
Last known good (UTC):       ...
App version + JDK:           ...
MongoDB driver version:      ...
MongoDB deployment/tier:     ...
Pod/container/host:          ...
Egress IP / network path:    ...
URI scheme:                  mongodb:// or mongodb+srv://
URI host (redacted):         ...
Read preference:             primary / secondary / ...
Exception type and cause:    ...
Driver cluster description:  ...
DNS SRV/TXT/A/AAAA result:   ...
TCP port test:               ...
TLS verification result:     ...
Replica set roles:           ...
Pool checkout metrics:       ...
Change before incident:      ...
Recovery/action owner:       ...
```

**Security:** do not paste raw connection strings containing passwords into tickets. You can keep host/port, scheme, safe options, and URI options after removing secrets.

---

## 4. Two Connection String Formats and Fundamental Differences

### 4.1. Standard `mongodb://`

Self-managed replica set example:

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/app?replicaSet=rs0&tls=true
```

- The seed list contains `host:port`.
- For a replica set, the driver uses the seed list to discover the entire topology.
- `tls=true` must be specified when a self-managed deployment requires TLS; **standard URIs do not enable TLS by default** unless configured otherwise.
- `replicaSet=rs0` helps identify the exact replica set.
- `db1`, `db2`, `db3` must be reachable from the application environment, not just from other MongoDB servers.

### 4.2. DNS Seedlist `mongodb+srv://`

Hypothetical Atlas example:

```text
mongodb+srv://cluster0.example.mongodb.net/app?retryWrites=true&w=majority
```

- Only **one hostname** after the scheme.
- Do not append `:27017` directly to an SRV URI.
- The driver queries DNS SRV `_mongodb._tcp.<hostname>` to find node targets/ports.
- The driver can read the TXT record for allowed connection options.
- `mongodb+srv://` **enables TLS by default** unless overridden appropriately; you should not override TLS to false to work around errors.
- DNS SRV changes with topology, so do not manually hardcode node IPs.

`cluster0.example.mongodb.net` is only an **example hostname**, not an existing live cluster.

### 4.3. URI Validation

| Component | Check |
| --- | --- |
| Scheme | `mongodb` or `mongodb+srv` |
| Host | Correct spelling, correct domain, DNS exists |
| Port | Used on standard URI; SRV does not add it manually |
| Replica set | Option name matches server config if declared |
| `authSource` | Database containing the user used for authentication |
| Database path | Distinguish default database from auth database |
| TLS | Matches server/Atlas, certificate verification enabled |
| Read preference | Are there members satisfying read/write semantics |
| Credentials | Properly percent-encoded when placed in the URI |
| Timeout options | Do not use a single timeout to explain everything |
| Hidden secrets | URI is not logged verbatim |

### 4.4. Special Characters in Passwords

If a password contains characters such as `@`, `:`, `/`, `?`, `#`, `%`, it must be **properly percent-encoded** per URI syntax. For example, an illustrative string `p@ss:w` needs the appropriate URI representation such as `p%40ss%3Aw`.

Do not encode the password this way when **entering it directly at a tool's password prompt**. Avoid double encoding: `%40` already encodes `@`, so you do not always convert `%` to `%25` again.

**Recommendation:** use a secrets manager or environment variables to supply the URI; never commit a real URI containing credentials.

---

## 5. DNS SRV, TXT, A/AAAA: Checking in the Right Order

For `mongodb+srv://cluster0.example.mongodb.net/`, the driver typically needs:

```text
Step A: SRV _mongodb._tcp.cluster0.example.mongodb.net
        |
        v
      target0.mongodb.net:27017
      target1.mongodb.net:27017
      target2.mongodb.net:27017
        |
        v
Step B: A/AAAA for each target host
        |
        v
Step C: TXT record on cluster0.example.mongodb.net
        |
        v
Step D: TCP to the exact target:port
```

The hostnames above are **illustrative**; actual Atlas results must be obtained via DNS lookup or the Atlas Connect modal.

### 5.1. Linux/macOS with dig

```bash
# Use the real SRV hostname from the URI, replacing the example hostname.
dig +short SRV _mongodb._tcp.cluster0.example.mongodb.net

dig +short TXT cluster0.example.mongodb.net

# Use each hostname returned by the SRV lookup.
dig +short A node0.example.mongodb.net
dig +short AAAA node0.example.mongodb.net
```

An SRV response contains fields like:

```text
priority weight port target
0        0      27017 node0.example.mongodb.net.
```

**The port and hostname must come from the actual record**; do not assume every network path uses only 27017.

### 5.2. Windows PowerShell

```powershell
Resolve-DnsName -Name "_mongodb._tcp.cluster0.example.mongodb.net" -Type SRV
Resolve-DnsName -Name "cluster0.example.mongodb.net" -Type TXT

Resolve-DnsName -Name "node0.example.mongodb.net" -Type A
Resolve-DnsName -Name "node0.example.mongodb.net" -Type AAAA
```

Depending on the Windows/DNS environment, you can use `nslookup`:

```powershell
nslookup -type=SRV _mongodb._tcp.cluster0.example.mongodb.net
nslookup -type=TXT cluster0.example.mongodb.net
nslookup node0.example.mongodb.net
```

### 5.3. Distinguishing DNS Error Types

- **NXDOMAIN**: the queried name does not exist according to the resolver in use; possibly a wrong hostname or stale cluster URI.
- **SERVFAIL**: the resolver could not complete the lookup; possibly upstream, DNSSEC, forwarding, or network policy.
- **Timeout**: the DNS server did not respond; check UDP/TCP 53, resolver route, or DNS proxy/sidecar.
- **No SRV records**: the DNS resolver does not support SRV, the domain has no record, the cluster is paused/deleted, or the wrong hostname is used.
- **SRV has target but no A/AAAA**: the node hostname cannot be resolved, especially common with misconfigured Private Endpoint/split DNS.
- **DNS returns an address but TCP does not reach it**: DNS may be completely fine; move on to the network layer.

### 5.4. Comparing Resolvers

```bash
dig @1.1.1.1 +short SRV _mongodb._tcp.cluster0.example.mongodb.net
```

The command above is only suitable for **environments intentionally using public DNS**, not when using private DNS/Private Endpoints. For internal endpoints, a public resolver may return wrong answers or fail to see private records; **do not switch production DNS servers to public DNS** without evaluating security/network design.

### 5.5. DNS Cache and TTL

- The OS, CoreDNS, sidecar, and JVM may cache results differently.
- Negative caching can preserve failed results for a period of time.
- DNS changes after failover/cluster scaling; hardcoded IPs can become stale.
- Do not edit `/etc/hosts` to "rescue" an SRV URI and treat it as a long-term solution.
- When comparing DNS results, record the resolver, timestamp, TTL, and test environment.

**Important:** DNS returning a valid IP does not prove that TCP/TLS/the application can connect.

---

## 6. DNS in Docker, Kubernetes, and Cloud Environments

### 6.1. `localhost` Changes by Runtime

- On the host laptop: `localhost:27017` points to the laptop itself.
- Inside a Docker container: `localhost` points to **that container**, not the host machine.
- Inside a Kubernetes pod: `localhost` points to the **pod network namespace**, not a MongoDB Service in another pod.
- In Atlas: do not use `localhost` to reach an external cluster unless a tunnel is configured.

For example, an application container connecting to another MongoDB container on the same Docker network should use the appropriate DNS service/container name, such as `mongo:27017`, **not `127.0.0.1:27017`**.

### 6.2. Checking from Inside a Container

```bash
# Example container name: api
docker exec api sh -c 'getent hosts mongo || true'

docker exec api sh -c 'getent hosts node0.example.mongodb.net || true'
```

`getent` might not exist in minimal images. Do not install debug utilities into production images if policy forbids it; you can use an approved debug container.

### 6.3. Kubernetes

```bash
kubectl -n my-namespace get pods
kubectl -n my-namespace get svc

# Example only; requires shell and nslookup available in the pod.
kubectl -n my-namespace exec deploy/my-api -- \
  nslookup cluster0.example.mongodb.net
```

Use real namespace/Deployment names. With CoreDNS or VPC/private endpoints, check:

- `/etc/resolv.conf` inside the pod.
- CoreDNS health and forwarding rules.
- Kubernetes NetworkPolicy for DNS egress.
- Node/VPC routes, NAT Gateway, and private endpoint.
- Differences between pods allowed to access the internet and blocked pods.
- Split-horizon DNS for Private Endpoint hostnames.

### 6.4. Replica Set Hostnames That Only Resolve Internally

A self-managed replica set might advertise members:

```text
mongo-0.mongo-headless.database.svc.cluster.local:27017
mongo-1.mongo-headless.database.svc.cluster.local:27017
```

If the Java app **runs outside the cluster**, those internal hostnames may not be resolvable or routable. The initial seed may connect, but after `hello` returns the topology, the driver tries to reach members by their advertised names and fails.

This is a **network topology and replica-set member hostname** issue, not a reason to unconditionally enable `directConnection=true` in production.

---

## 7. Checking TCP: DNS Is Correct, Yet Connection Still Fails to Reach

Once you have the **real node hostname and port**, test TCP from the exact runtime.

### 7.1. Windows PowerShell

```powershell
Test-NetConnection `
  -ComputerName "node0.example.mongodb.net" `
  -Port 27017 `
  -InformationLevel Detailed
```

Inspect:

- `RemoteAddress`: IP returned by DNS.
- `RemotePort`: port being tested.
- `TcpTestSucceeded`: whether the TCP handshake succeeded.
- `SourceAddress`/interface: can help identify the route.

`TcpTestSucceeded=True` **does not prove that the TLS handshake or MongoDB auth succeeds**.

### 7.2. Linux/macOS

```bash
nc -vz node0.example.mongodb.net 27017
```

Some `nc` implementations use different syntax/flags; you can use:

```bash
timeout 5 bash -c '</dev/tcp/node0.example.mongodb.net/27017'
```

The `/dev/tcp` snippet depends on Bash and is not POSIX standard. Use the tool appropriate for the OS and container image rather than assuming every environment has Bash/`nc`.

### 7.3. Interpreting the Results

| TCP result | Primary hypothesis |
| --- | --- |
| Connection succeeded | DNS/route/TCP listener are open; proceed to TLS/hello |
| `Connection refused` | Host is reachable, but port is not listening or a device returned a reject |
| Timeout | Firewall drop, network ACL, route, or endpoint unreachable |
| `No route to host` | IP routing/network unreachable |
| Only one IP fails | Node-specific firewall, endpoint/subnet, or IPv4/IPv6 |
| Fails only from pod A | Security policy/route/DNS of that pod/node |
| TCP fine but driver times out | TLS, server hello, SDAM, auth, pool, or load |

### 7.4. Ping Does Not Determine TCP

`ping` uses ICMP, which can be blocked by firewalls/cloud providers. **A failed ping does not prove MongoDB TCP failed**. Use a port-level check.

### 7.5. `bindIp` and Listener in Self-Managed Deployments

On a self-managed server, verify that `mongod` is running and listening on the right address/port:

Linux:

```bash
ss -ltn | grep 27017
```

Windows:

```powershell
Get-NetTCPConnection -LocalPort 27017 -State Listen
```

`mongod` bound to `127.0.0.1` only accepts localhost traffic; an app on another host cannot connect via that public/private IP. Do not change `bindIp` to `0.0.0.0` in production without TLS, auth, and firewall/network policy protection.

---

## 8. Atlas: IP Access List and Outbound Egress IP

MongoDB Atlas only permits clients from IPs/CIDRs listed in the **project IP access list**, or via a connectivity model such as Private Endpoint with its own policy.

Common mistakes:

- A developer allow-lists their laptop IP, while the application runs in the cloud with a **different NAT egress IP**.
- The NAT Gateway changes or the deployment moves regions.
- There are multiple egress IPs across multiple AZs, pods, or proxies.
- Cloud network policy blocks outbound TCP 27017.
- The Atlas IP allow-list has the right IP, but a corporate firewall still blocks it.
- The cluster is paused/provisioning/deleted.
- ISP/proxy firewalls require special configuration.

### 8.1. Discovering the Egress IP

Making a request to an IP-check service from the **exact application runtime** can help identify the public egress IP, but you must consider security policies and source NAT. Do not take your laptop's public address and assume it is the egress IP of production pods.

In the cloud, a more reliable source of truth is your organization's network/NAT/VPC configuration.

### 8.2. Do Not Open `0.0.0.0/0` "Just for a Quick Test"

Atlas may allow adding a very wide CIDR range, but doing so increases the attack surface. In production:

- Restrict to the minimal CIDR.
- Separate IP access lists by deployment/environment.
- Use private networking when appropriate.
- Set an expiration for temporary access if policy supports it.
- Do not disable TLS/auth.
- Record a change ticket and owner.

### 8.3. One Open Port May Not Suffice for Every Topology

Atlas uses ports depending on deployment/tier/topology; documentation mentions port 27017 for many connections, while sharded scenarios may require other ports. Obtain the **exact hostname/port from the connection string or SRV result**, test every required node, and do not arbitrarily open broad port ranges without justification.

---

## 9. TLS: After TCP Comes Connection Protection and Server Authentication

When MongoDB requires TLS, the driver must establish a TLS handshake before exchanging MongoDB protocol commands.

Typical errors include:

```text
javax.net.ssl.SSLHandshakeException:
PKIX path building failed
```

```text
javax.net.ssl.SSLHandshakeException:
No subject alternative DNS name matching ...
```

```text
javax.net.ssl.SSLHandshakeException:
Received fatal alert: handshake_failure
```

```text
javax.net.ssl.SSLException:
Unrecognized SSL message, plaintext connection?
```

The outermost message is sometimes `MongoSocketOpenException` or `MongoTimeoutException`, while the TLS cause sits deeper.

### 9.1. SRV and Standard TLS Defaults

- `mongodb+srv://`: TLS is typically **enabled by default**.
- `mongodb://`: TLS is typically **disabled by default** unless specified/configured otherwise.
- Atlas requires TLS; use the appropriate TLS URI.
- Self-managed servers may or may not require TLS depending on `net.tls.mode`.

If you connect with TLS to a port running plaintext MongoDB, a handshake/EOF error can occur. If a non-TLS client connects to a server requiring TLS, it also fails. **Fix both sides to align TLS mode**; do not disable TLS when policy requires it.

### 9.2. Inspecting the Handshake with OpenSSL

On Linux/macOS with OpenSSL:

```bash
openssl s_client \
  -connect node0.example.mongodb.net:27017 \
  -servername node0.example.mongodb.net \
  -showcerts \
  -verify_return_error
```

- `-connect`: TCP hostname/port.
- `-servername`: SNI; should match the real hostname.
- `-showcerts`: displays the presented certificate chain.
- `-verify_return_error`: may fail when the chain is untrusted.

Only run this command against **hosts you administer or are authorized to test**. A successful OpenSSL handshake does not prove MongoDB authentication, read preference, or commands will succeed.

On Windows with OpenSSL installed, the syntax is similar. If OpenSSL is unavailable, use Java JSSE debug or an organization-approved certificate verification tool.

---

## 10. Reading Certificates: CA, SAN, Validity, and mTLS

A TLS certificate typically contains:

- `Subject` and `Issuer`.
- `Subject Alternative Name` (SAN) listing valid DNS names/IPs.
- `Not Before` / `Not After`.
- Public key and signature.
- Certificate chain up to the root/intermediate CA.
- Appropriate Extended Key Usage.

### 10.1. Hostname Mismatch Errors

Example connection URI:

```text
mongodb://10.10.0.15:27017/?tls=true
```

However, the server certificate only has SAN `db1.internal.example.net`.

Java TLS hostname verification may report a **hostname mismatch**. Proper fixes:

- Use a hostname present in the SAN and ensure DNS/routing reaches the right node.
- Or issue/switch to a valid certificate for the hostname/IP being used.
- Check SNI/cert rotation if the endpoint serves multiple certs.

**Do not use `tlsAllowInvalidHostnames=true` or `tlsInsecure=true` in production** to bypass the error.

### 10.2. PKIX Path Building Failed

Common causes:

- The server certificate is signed by a private CA that the JVM does not trust.
- An intermediate CA chain is missing.
- The JDK truststore differs from the OS truststore.
- The container uses a JRE/custom image with incomplete CA bundles.
- A TLS-intercepting proxy issues certificates from an untrusted internal CA.
- The certificate was replaced during rotation, but the truststore was not updated.

How to resolve:

1. Verify you are connecting to the right hostname and inspect the presented certificate.
2. Check the chain, issuer, and expiry.
3. Check the truststore that the **JVM actually uses**.
4. Add the **trusted and approved CA** into the truststore properly.
5. Restart/roll out the process if the runtime requires it to load the new truststore.
6. Verify there is no unauthorized MITM/proxy.

### 10.3. Inspecting a Certificate File

If you have a copy of the public server cert:

```bash
openssl x509 \
  -in server-cert.pem \
  -noout -subject -issuer -dates \
  -ext subjectAltName
```

Check clock/NTP skew: a machine with the wrong time may treat a certificate as "not yet valid" or expired.

### 10.4. Java Truststore and Keystore

- **Truststore:** contains CAs/certificates trusted to verify the **server**.
- **Keystore:** contains the client certificate/private key for the **client** to prove its identity when mTLS/X.509 is required.

Java can be configured with:

```text
-Djavax.net.ssl.trustStore=/secure/path/mongo-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
```

The truststore password must be passed through appropriate secrets management; **do not paste `-Djavax.net.ssl.trustStorePassword=...` containing a real password into tickets, logs, or repositories**.

Inspect a truststore using `keytool -list -v -keystore ...` with a password prompt per policy.

### 10.5. mTLS and X.509

Some self-managed deployments require a client certificate; Atlas X.509 authentication also has its own configuration. You must check:

- Does the server require a client cert?
- Was the client cert issued by a CA trusted by the server?
- Is there a matching private key in the right format?
- Does the certificate subject map to the user/auth mechanism when using X.509?
- How does the client keystore differ from the server truststore?

**TLS encryption/validation** and **MongoDB user authentication** are separate layers. Successful TLS does not guarantee SCRAM/X.509 login succeeds.

---

## 11. TLS Versions, Cipher Suites, JDK, and JSSE Logs

### 11.1. JDK and TLS Compatibility

MongoDB Atlas and many modern deployments require TLS 1.2+ by policy. Older JDKs may lack suitable protocols/ciphers or have TLS 1.3 bugs in certain patch versions.

- Record the exact JDK vendor, major version, and update/patch.
- Check MongoDB Java Driver compatibility.
- Check protocols blocked by `jdk.tls.disabledAlgorithms`.
- Update the JDK/CA bundle per policy instead of relaxing security constraints.

### 11.2. Controlled JSSE Debug Logging

Lab JVM run example:

```bash
java -Djavax.net.debug=ssl,handshake,trustmanager -jar app.jar
```

`-Djavax.net.debug=all` can be used when very detailed output is needed, but **the logs are huge** and may expose sensitive metadata. Only enable it temporarily in controlled environments, with log retention and redaction in place.

Questions to answer from the debug output:

- Which truststore is the JVM using?
- Which certificate chain did the server send?
- Was the certificate accepted or rejected due to CA/expiry/SAN?
- Which TLS version/cipher was negotiated?
- Was there a handshake alert from the client or server?

### 11.3. TLS Errors Should Not Be Treated by Increasing Timeouts

If you see `SSLHandshakeException: PKIX path building failed`, increasing `connectTimeoutMS` or `serverSelectionTimeoutMS` only makes the application **wait longer before failing**. You must fix the trust/certificate chain.

---

## 12. MongoDB Java Driver and SDAM: How Is a Server Selected?

**SDAM** = Server Discovery and Monitoring. The driver monitors the topology and tracks:

- Whether the cluster is standalone, replica set, or sharded `mongos`.
- Which servers are reachable.
- Which servers are primary/secondary/arbiter.
- Round-trip time (RTT) and heartbeat status.
- Which members satisfy the read preference and operation type.

When executing a command, the driver looks for a suitable server. If time runs out without finding one, it throws `MongoTimeoutException` with the cluster description.

### 12.1. Example of an Informative Real Error

```text
com.mongodb.MongoTimeoutException:
Timed out after 30000 ms while waiting for a server
that matches ReadPreferenceServerSelector{readPreference=primary}.
Client view of cluster state is {
  type=REPLICA_SET,
  servers=[
    {address=db1:27017, type=UNKNOWN, state=CONNECTING,
     exception={MongoSocketOpenException:
       caused by ConnectException: Connection refused}},
    {address=db2:27017, type=REPLICA_SET_SECONDARY, state=CONNECTED}
  ]
}
```

Analysis:

- The driver successfully contacted **db2 secondary**.
- The operation requires a **primary**.
- db1 cannot be reached.
- No server matches the selector, hence the timeout.
- This is not necessarily a cluster-wide DNS failure.

### 12.2. `type=UNKNOWN` Does Not Mean "Server Was Deleted"

`type=UNKNOWN`, `state=CONNECTING` means the driver **has not yet received enough information to classify the server** at the time the snapshot was recorded. Inspect the nested exception; it could be DNS, TLS, TCP, handshake, or discovery.

### 12.3. Server Selection vs. TCP Connect

- **Connect timeout:** a single socket connection was not established within the limit.
- **Server selection timeout:** after discovery attempts, no server matched the topology/read preference within the limit.
- A single server selection timeout may encompass **multiple repeated connect failures** underneath.

Diagnostics must examine both; avoid treating them as the same parameter.

---

## 13. Replica Set: Primary, Secondary, and Advertised Hostnames

### 13.1. No Primary Available

Scenario:

```text
db1: UNKNOWN / unreachable
db2: SECONDARY / connected
db3: SECONDARY / connected
request: write or readPreference=primary
```

Writes must go to the primary; the driver's default read preference is typically primary. If no primary can be selected, the operation may time out even though a secondary responds fine.

Check a self-managed replica set:

```javascript
db.hello();
rs.status();
rs.conf();
```

`rs.status()` and `rs.conf()` require appropriate connectivity/roles and privileges. On Atlas, check cluster status, replication metrics, and event logs.

### 13.2. Election and Failover

During an election, there may be a window without a primary. If the cluster recovers within the timeout, the request may succeed; otherwise, the driver throws an error. Do not confuse a brief failover with a broken TLS certificate.

Things to inspect:

- Primary election events.
- Member health and majority/quorum.
- Network partitions.
- Replication lag.
- Disk pressure/CPU saturation.
- Driver heartbeat/topology updates.

Do not run `rs.reconfig()` or `rs.stepDown()` in production just to test connectivity.

### 13.3. Wrong `replicaSet` Option

URI:

```text
mongodb://db1:27017,db2:27017/?replicaSet=rsWrong
```

If the server reports set name `rs0`, the driver will not treat it as a matching topology. Check `db.hello()`/`rs.conf()` to confirm the actual name.

### 13.4. Advertised Hosts Unreachable

The driver connects to seed `public-gateway.example.net` successfully; `hello` returns members:

```text
db1.internal.local:27017
db2.internal.local:27017
db3.internal.local:27017
```

An external application cannot resolve/route internal hosts, leading to a server selection timeout **after the seed connection succeeded**.

The fix is to configure **network topology/DNS/replica set member hostnames** appropriate for where the application runs, not simply adding more retries.

### 13.5. `directConnection=true` Only When Intentional

```text
mongodb://db1.example.net:27017/?directConnection=true
```

This option instructs the driver to connect **directly to a single host** instead of performing normal topology discovery. It is useful for diagnostics/labs/tunnels in certain cases, but:

- It does not provide high availability/failover.
- It does not fix real DNS/TLS issues across replica set members.
- It should not be used to mask unreachable advertised members in production.
- An operation requiring a primary must still satisfy server capabilities/roles.

---

## 14. Read Preference Is Also a Server Selection Criterion

Different read preference modes have different goals:

| Mode | Characteristics | Timeout relationship |
| --- | --- | --- |
| `primary` | Read only from primary | No primary → cannot select |
| `primaryPreferred` | Prefer primary, fall back to secondary when suitable | Can read from secondary, must accept staleness |
| `secondary` | Read only from secondary | No eligible secondary → timeout |
| `secondaryPreferred` | Prefer secondary, fall back to primary when suitable | Does not guarantee read-your-writes |
| `nearest` | Choose candidates by latency/topology rules | Does not mean most recent read |

**Do not change read preference just to "stop the error"** if the business logic requires reading recently written data or strict consistency.

### 14.1. `serverSelectionTimeoutMS` Does Not Make a Primary Appear

For example, the app increases the timeout from 30 to 120 seconds, but the replica set loses majority for several minutes. The wait time increases, yet the condition of having a primary is still not met.

### 14.2. Server Selection Also Considers Tags/Staleness

With read preference tags or `maxStalenessSeconds`, some secondaries may be excluded even when TCP/TLS works. Inspect the read preference and diagnostics; the issue may lie in the selector rather than the network.

---

## 15. Timeouts: Five Different Clocks

The defaults below reflect **current MongoDB Java Sync Driver documentation**, though you must verify your driver version and options overridden by Spring/frameworks.

| Option/concept | Clock measured | Common default | When worth adjusting |
| --- | --- | --- | --- |
| `serverSelectionTimeoutMS` | Wait to select a valid server in topology | 30000ms | SLA/troubleshooting; does not fix root cause |
| `connectTimeoutMS` | Wait to establish TCP socket connection | 10000ms | Justified route/network latency |
| `socketTimeoutMS` | Wait for socket send/receive | 0 (no limit set by option) | Hanging I/O operation; needs budget |
| Pool checkout wait | Wait to acquire an available connection | Per driver; `waitQueueTimeoutMS` legacy/deprecated | Pool saturation |
| `timeoutMS` (CSOT) | Client-side budget for an operation; includes selection/checkout/execution | Depends on version/config; feature may be experimental | End-to-end operation deadline |

### 15.1. Server Selection Timeout

```text
mongodb://db1.example.net:27017/?serverSelectionTimeoutMS=10000
```

After up to 10 seconds without selecting a server, the driver throws a timeout per version semantics. This is a **selection** deadline, not a server-side query execution limit.

### 15.2. Connect Timeout

```text
mongodb://db1.example.net:27017/?connectTimeoutMS=5000
```

A TCP connect attempt is bounded to about 5 seconds. If DNS returns a wrong route or a firewall drops packets, each attempt may fail while the driver continues discovery within the server selection budget.

### 15.3. Socket Timeout

```text
mongodb://db1.example.net:27017/?socketTimeoutMS=10000
```

Applies to socket read/write per driver semantics. Do not set 10 seconds across all analytics queries that may run for 30 seconds unless that is the business policy.

### 15.4. Pool Wait Differs from Selection

If a server is selected but the pool is full, the application may wait for checkout. Depending on the driver version, `waitQueueTimeoutMS` is documented as **deprecated** in current docs, which recommend client-level operation timeout/CSOT where appropriate. Read the docs for your exact driver release rather than copying legacy config blindly.

### 15.5. Client-Side Operation Timeout (CSOT)

Current MongoDB Java Driver docs cover `timeoutMS`/CSOT to bound **the total duration of an operation** including selection, checkout, network, and execution; the feature is noted as **experimental** in the documentation.

```text
mongodb://db1.example.net:27017/?timeoutMS=10000
```

Only use it when supported by your driver version and after verifying semantics and application policy. Do not sum all individual timeouts and claim an operation is guaranteed to finish before that total.

### 15.6. Do Not Just "Increase All Timeouts"

Increasing timeouts can:

- Reduce false timeouts during brief failovers.
- Cause request threads/virtual threads to wait longer.
- Let an HTTP gateway time out first while DB work keeps running.
- Cause retry amplification and pool saturation.
- Mask recurring DNS/TLS failures.

Design timeout budgets from **end-user SLOs**, retry windows, and observed telemetry—not just defaults.

---

## 16. Java Sync Driver: A `ping` Program for Real Verification

**Creating a `MongoClient` does not prove connectivity.** The driver can initialize the client and discover servers asynchronously; you need to **execute an operation** such as `ping`.

### 16.1. Self-Contained Java Code

```java
import com.mongodb.MongoClientSettings;
import com.mongodb.MongoException;
import com.mongodb.MongoTimeoutException;
import com.mongodb.ConnectionString;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

import org.bson.Document;

import java.util.concurrent.TimeUnit;

public final class MongoConnectivityProbe {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                "Environment variable MONGODB_URI is required"
            );
        }

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .applyToClusterSettings(builder ->
                builder.serverSelectionTimeout(
                    10, TimeUnit.SECONDS
                )
            )
            .applyToSocketSettings(builder ->
                builder.connectTimeout(
                    5, TimeUnit.SECONDS
                )
            )
            .build();

        try (MongoClient client = MongoClients.create(settings)) {
            Document response = client
                .getDatabase("admin")
                .runCommand(new Document("ping", 1));

            System.out.println(
                "MongoDB ping command completed: "
                + response.get("ok")
            );
        } catch (MongoTimeoutException e) {
            System.err.println("Server selection timed out");
            printCauseChain(e);
            throw e;
        } catch (MongoException e) {
            System.err.println("MongoDB operation failed");
            printCauseChain(e);
            throw e;
        }
    }

    static void printCauseChain(Throwable error) {
        Throwable current = error;
        int level = 0;
        while (current != null && level < 12) {
            System.err.println(
                level + ": "
                + current.getClass().getName()
                + ": " + current.getMessage()
            );
            current = current.getCause();
            level++;
        }
    }
}
```

**Note:** cause messages may contain hostnames, usernames, or connection metadata. In production, sanitize log output instead of printing raw stack traces to public log sinks. The code above is for diagnostic environments.

### 16.2. Running with Environment Variables

PowerShell:

```powershell
$env:MONGODB_URI = "mongodb://127.0.0.1:27017/?serverSelectionTimeoutMS=10000"
```

Linux/macOS:

```bash
export MONGODB_URI='mongodb://127.0.0.1:27017/?serverSelectionTimeoutMS=10000'
```

Replace the URI with a safe value for your test deployment. Use policy-compliant secrets injection for production. Do not run the commands above with real passwords and paste them into shell history/tickets.

### 16.3. What This Test Proves and Does Not Prove

- `MongoClients.create(...)` is **not sufficient** to prove connectivity.
- A successful `ping` proves a server was selected, a connection was established, and the command was processed under current permissions/connection.
- A successful `ping` **does not** prove the user has permission to read collections or that transaction/query workloads will run well.
- A successful `ping` to one node **does not** prove all replica set members/shards are reachable.
- If `ping` fails, read the root cause and cluster description, then revisit DNS/TCP/TLS/SDAM.

---

## 17. Spring Boot / Spring Data: When Do Errors Appear?

A Spring Boot application can instantiate `MongoTemplate`/repository beans without verifying the full connection path. The first query or a health check executing an operation exposes the error.

### 17.1. Configuring the Connection URI

Lab config example:

```properties
spring.data.mongodb.uri=mongodb://127.0.0.1:27017/appdb
```

For production, supply the URI via secret/environment injection compatible with your Spring Boot version, and do not commit passwords to `application.properties`.

### 17.2. Startup Probe Using MongoTemplate

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

public final class DbProbe {
    private final MongoTemplate mongoTemplate;

    public DbProbe(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public boolean canPing() {
        Document result = mongoTemplate
            .getDb()
            .runCommand(new Document("ping", 1));

        Object ok = result.get("ok");
        return ok instanceof Number
            && ((Number) ok).doubleValue() == 1.0;
    }
}
```

The code above illustrates an **active connectivity check**; in a real service, do not call it on every HTTP request. Distinguish liveness from readiness:

- **Liveness:** whether the service process is alive and should be restarted if unrecoverable; avoid tying every liveness check strictly to brief MongoDB outages.
- **Readiness:** whether the pod can serve traffic requiring the DB; can incorporate MongoDB health when policy fits.
- **Startup:** wait for dependency initialization within a defined budget.

### 17.3. Do Not Look Only at the Spring Wrapper Error

A Spring Data exception such as `DataAccessResourceFailureException` may wrap `MongoTimeoutException`. Inspect the nested exception/root cause rather than logging only "Cannot connect to MongoDB".

### 17.4. Spring Boot Actuator

If using the Actuator Mongo health indicator, check:
- Is the indicator/endpoint enabled?
- Does the health check execute a DB operation?
- How is readiness affected during failover?
- Does the health check timeout align with probe intervals and restart policy?
- Is the health status exposed publicly in a way that leaks metadata?

Do not assume `/actuator/health` returning `UP` means all tenant queries and indexes are healthy.

---

## 18. Compass/mongosh Succeeds While Java Fails

This is a common scenario:

```text
Compass on laptop: OK
MongoDB Java pod:  MongoTimeoutException
```

Many differences exist:

| Factor | Compass/mongosh | Java app |
| --- | --- | --- |
| Network | Laptop/VPN | Pod/container/VPC |
| DNS resolver | OS/public DNS | CoreDNS/private resolver |
| Egress IP | ISP/VPN IP | NAT gateway/service mesh |
| TLS truststore | OS/app bundle | JVM truststore |
| JDK/TLS stack | Electron/Node/OpenSSL | JSSE |
| URI options | Newly pasted Atlas URI | App using older config |
| Authentication | Saved profile/user | Different secret/env var |
| Replica set discovery | Different GUI options | Java driver SDAM |
| Connection pool | A few connections | Hundreds of app threads |
| Driver version | Bundled | Dependency BOM |
| Time | Tested at a different time | Incident/failover at a different time |

### 18.1. A Fair Comparison

Run `mongosh` **from the same machine/pod** if permitted:

```bash
mongosh 'mongodb+srv://cluster0.example.mongodb.net/app'
```

For secured deployments, provide credentials via the tool's prompt/secret mechanism. Ensure the same hosts, TLS, authSource, read preference, resolver, and network path are used.

### 18.2. mongosh OK Does Not Guarantee Java TLS OK

If `mongosh` uses a certificate trust chain from OS/OpenSSL/Node while the JVM uses an older custom truststore, the same endpoint can succeed in the shell and fail in Java. Inspect JSSE/debug/truststore and JDK patch version.

---

## 19. Distinguishing Authentication Failure from TLS/Server Selection

After TCP/TLS/hello, MongoDB authenticates the user.

### 19.1. Signs of Authentication Failure

Examples:

```text
MongoSecurityException:
Exception authenticating MongoCredential ...
```

or:

```text
MongoCommandException:
Command failed with error 18 (AuthenticationFailed)
```

Typical causes:

- Wrong username/password or un-updated secret.
- Wrong `authSource`.
- Password contains special characters in the URI without percent-encoding.
- SCRAM mechanism incompatible with the user/server.
- Wrong X.509 auth mechanism/certificate subject.
- Credential created in a different project/cluster.

### 19.2. `authSource` vs. Default Database

URI:

```text
mongodb://user@db.example.net:27017/app?authSource=admin
```

`app` is the application's default database, whereas `admin` is where the driver authenticates the user. **These two values can differ**. With Atlas SRV, TXT records may supply options like `authSource=admin`; check the final URI and actual records.

### 19.3. Do Not Lower Security to Diagnose

Do not disable auth/TLS or grant the `root` role just to probe connectivity. Use a user with `ping` privileges or a designated health operation, with proper approval and audit logging.

---

## 20. Connection Pool: TCP/TLS Works, Yet Requests Still Time Out

The MongoDB Java Driver maintains connection pools per server in the topology.

According to current Java Sync Driver documentation:

- Default `maxPoolSize` is typically **100 per server**.
- `minPoolSize` is typically 0.
- `maxConnecting` is typically 2.
- Each `MongoClient` may open additional monitoring connections per server.

### 20.1. One MongoClient for the Entire Application

**Wrong**:

```java
public Document findOrder(String uri, String id) {
    try (MongoClient client = MongoClients.create(uri)) {
        return client.getDatabase("app")
            .getCollection("orders")
            .find(new Document("_id", id))
            .first();
    }
}
```

Creating and closing a client on every request repeats discovery/pool/TLS setup, causing connection churn and high latency.

**Right:** initialize one `MongoClient` tied to the service/container lifecycle, reuse it, and close it on shutdown.

### 20.2. Distinguishing Selection from Checkout

```text
Server found and eligible
      |
      v
Connection pool checkout
      |
      +-- Connection available -> command
      |
      +-- All connections busy -> wait/queue
                               -> checkout timeout
```

If the error is a **pool timeout**, DNS/TLS for active connections may be completely healthy.

Check:

- In-use/idle/connecting connections.
- Max pool size and checkout wait time.
- App concurrency and executor/scheduler queues.
- MongoDB slow queries and long transactions.
- Number of `MongoClient` instances/pods.
- Retry storms and leaked cursors/streams.

### 20.3. Pool Size Does Not Equal Infinite Throughput

For example, four application instances, each with a max pool of 100 connections to each of three nodes: theoretically this could reach `4 × 3 × 100 = 1200` pooled sockets if all pools max out, excluding monitoring sockets/topology differences.

Increasing pool size indefinitely can make the server slower. Inspect server CPU/IOPS/latency and reduce query time before scaling the pool.

### 20.4. Tuning Timeouts with CSOT

Some current versions support client-side operation timeout `timeoutMS`/CSOT. Docs note CSOT as experimental; avoid mixing legacy `waitQueueTimeoutMS` and CSOT without reading the driver semantics.

---

## 21. `directConnection`, Tunnels, and Development Traps

### 21.1. Connecting via SSH Tunnel

Suppose an authorized tunnel maps `localhost:27018` to a replica-set member:

```text
mongodb://127.0.0.1:27018/?directConnection=true
```

This is useful for checking a single host in certain lab/tunnel scenarios. However, when the driver discovers a replica set, advertised hostnames may lie outside the tunnel; `directConnection` cannot be treated as a high availability solution.

### 21.2. Docker Published Port

If local MongoDB only publishes a port via Docker:

```bash
docker run --rm -d \
  --name mongo-connect-lab \
  -p 127.0.0.1:27018:27017 \
  mongo:8.0
```

This configuration is **for local labs only**, with authentication/TLS disabled; it is bound to the host's loopback `127.0.0.1`. With Docker Desktop, the host OS needs Docker Engine running and the image pulled per policy.

Connect:

```bash
mongosh 'mongodb://127.0.0.1:27018/?directConnection=true'
```

Inside another application container, `127.0.0.1` refers to that container itself, not the MongoDB container. Use a network alias/service name instead.

### 21.3. Do Not Arbitrarily Use `bindIp` `0.0.0.0`

Exposing an unauthenticated test MongoDB instance to a public network is dangerous. Use network isolation, `127.0.0.1` host publishing, and remove the lab after practice.

---

## 22. Private Endpoint and Split-Horizon DNS

Atlas deployments over cloud Private Endpoint/PrivateLink/Private Service Connect add another configuration layer:

- The Private Endpoint service and endpoint connection are **accepted/available**.
- Endpoint DNS names resolve to the **appropriate private IP** from the application's VPC/VNet.
- VPC/VNet routes, subnets, security groups, and NACLs permit the connection.
- The Atlas private endpoint URI matches the region/topology.
- Cross-region/private multi-region deployments may require additional endpoints.
- DNS forwarders/conditional forwarding for private zones work properly.
- Do not mistakenly use a public SRV hostname from a laptop where only private networking is reachable.

### 22.1. Investigation Must Happen Inside the Private Network

If `dig` on a laptop returns a public IP while a pod returns a private IP, that **may be completely expected** under split-horizon DNS. What you need to verify is whether the pod has a route and TCP connectivity to the **IP of the endpoint actually in use**.

### 22.2. SRV May Succeed While Target A Is Wrong

An SRV record returns a target name, yet the target's A/AAAA record resolves to a public IP in an environment without internet egress. Then the SRV lookup passes, but TCP fails.

Follow the full chain **SRV → targets → A/AAAA → TCP**, do not stop at "dig SRV returned a name".

### 22.3. Do Not Switch All Private DNS to Public

Changing the DNS resolver to `8.8.8.8` can break private zones or violate security policy. If the issue is private endpoint DNS forwarding, fix the forwarding/private DNS architecture with the network team.

---

## 23. Common Root Cause Scenarios

### 23.1. Atlas IP Access List Missing NAT IP

**Symptom:** laptop connects fine, ECS/EKS/AKS/VM fails; DNS resolves, TCP times out.

**Likelihood:** the IP in the Atlas project access list is the laptop IP, while the app egresses via a different NAT Gateway.

**Verification:** compare the NAT egress IP/source CIDR against the access list, and run a TCP test from the pod.

**Remediation:** allow-list the exact egress IP/CIDR per policy or use approved private networking; do not open `0.0.0.0/0`.

### 23.2. Stale JVM Truststore After Cert Rotation

**Symptom:** Compass OK, Java throws `SSLHandshakeException: PKIX path building failed`.

**Likelihood:** the JVM image/truststore lacks the new CA or intermediate certificate.

**Verification:** compare the cert chain in the handshake, Java truststore, and JDK version.

**Remediation:** update the trusted CA/JDK image/chain per procedure and restart pods when needed. Do not disable hostname verification.

### 23.3. SRV Lookup Fails in Corporate DNS

**Symptom:** `mongodb+srv://` fails, `dig SRV`/`Resolve-DnsName -Type SRV` returns no answer, standard node hostnames may resolve.

**Likelihood:** the resolver does not support SRV/misconfigured forwarding, or the cluster is paused.

**Remediation:** fix DNS SRV support; if appropriate, use the **standard `mongodb://` connection string provided by Atlas** per documentation. Do not guess the seed list by copying resolved IPs.

### 23.4. Replica Set Secondary Reachable, Primary Not

**Symptom:** cluster description shows secondary connected; selector requires primary; selection times out.

**Likelihood:** election, primary down, majority unavailable, or read/write role constraint.

**Remediation:** check replica set health/quorum and primary network; wait for/recover the primary per runbook. Only change read preference when the business allows stale reads; writes cannot be routed to a secondary.

### 23.5. Wrong `localhost` in Container

**Symptom:** app works on laptop, fails with `Connection refused 127.0.0.1:27017` when deployed in a container.

**Likelihood:** MongoDB is not running **inside the same container**.

**Remediation:** use service DNS or an approved database endpoint; check network/secret configuration.

### 23.6. Internal Advertised Hostnames Unreachable

**Symptom:** seed node is reachable, driver discovers internal member names and then throws `UnknownHostException`.

**Likelihood:** replica set configuration advertises addresses usable only inside another network.

**Remediation:** fix network topology/DNS/replica set advertised addresses per plan; do not just enable `directConnection` to mask a production issue.

### 23.7. Pool Exhaustion After Scale-Out

**Symptom:** fine early in the day, checkout timeouts at peak; DNS/TCP/TLS checks all pass.

**Likelihood:** excessive app concurrency, slow queries, pool size limits, or creating a `MongoClient` per request.

**Remediation:** reuse `MongoClient`, measure checkout metrics/query latency, reduce fan-out/retries, tune the pool reasonably, and perform capacity planning.

### 23.8. Password with `@` Character Misinterpreted

**Symptom:** TCP/TLS/hello succeed, yet `AuthenticationFailed` occurs; URI has `@` in the password.

**Likelihood:** unencoded password caused host/credential misparsing.

**Remediation:** inject secrets and URI-encode passwords accurately, verify `authSource`, and never print passwords to logs.

---

## 24. Investigation Workflow by Test Results

```text
Application cannot connect to MongoDB
        |
        v
Can the URI be parsed?
  | NO -> fix scheme/host/port/percent encoding
  v YES
Do DNS SRV/TXT (if +srv) and A/AAAA succeed?
  | NO -> fix hostname/resolver/private DNS
  v YES
Does TCP to target:port succeed from the runtime?
  | NO -> route/firewall/Atlas IP access list/bindIp
  v YES
Do TLS handshake and certificate validation succeed?
  | NO -> TLS mode, CA chain, SAN, expiry, SNI, JDK
  v YES
Does MongoDB hello/SDAM see an eligible topology?
  | NO -> replicaSet/advertised hostnames/primary/election
  v YES
Does authentication succeed?
  | NO -> user/password/authSource/mechanism/X.509
  v YES
Do pool checkout and commands work?
  | NO -> pool saturation, timeouts, server overload
  v YES
Ping succeeds, yet business logic fails?
  -> authorization, query indexes, read/write concern,
     schema/validation, session/transactions
```

**A flowchart does not replace reverse tracing:** the outermost error may wrap a deeper failure. For example, `MongoTimeoutException` can still have a TLS handshake error in its cause chain.

---

## 25. Lab 1 — Wrong DNS/Hostname

Goal: observe how a hostname error differs from a TCP error.

### Preparation

Use a reserved `.invalid` name, not a real system:

```bash
mongosh 'mongodb://db-does-not-exist.invalid:27017/?serverSelectionTimeoutMS=3000'
```

After the driver retries and times out, expect the message to contain a DNS failure/`ENOTFOUND`/`getaddrinfo` depending on the tool/version/OS.

### Comparing with TCP Refused

If you have a lab MongoDB on `127.0.0.1:27018`:

```bash
mongosh 'mongodb://127.0.0.1:27019/?serverSelectionTimeoutMS=3000'
```

Assuming port 27019 has no listener, the error typically contains `ECONNREFUSED`/`Connection refused`.

**Conclusion:** DNS failure happens before TCP, whereas TCP refused means the host/IP was resolved but the port is not accepting connections.

---

## 26. Lab 2 — TCP and Port on Local MongoDB

If you created the lab container in section 21:

```bash
mongosh 'mongodb://127.0.0.1:27018/?directConnection=true'
```

Windows:

```powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 27018
Test-NetConnection -ComputerName 127.0.0.1 -Port 27019
```

Linux/macOS:

```bash
nc -vz 127.0.0.1 27018
nc -vz 127.0.0.1 27019
```

Expect 27018 to be reachable and 27019 to have no listener, assuming no other service uses port 27019.

### Stopping the Lab

```bash
docker stop mongo-connect-lab
```

The container runs with `--rm`, so it will be removed upon stopping. Only operate on the container created by the lab itself; do not stop a production MongoDB instance.

---

## 27. Lab 3 — Intentional Local TLS Mismatch

The default MongoDB Docker lab in the example does not enable TLS. Try:

```bash
mongosh 'mongodb://127.0.0.1:27018/?directConnection=true&tls=true&serverSelectionTimeoutMS=3000'
```

Expect the handshake to fail because the client requires TLS while the lab server has no TLS. **Do not** perform this action in production to guess configuration.

Compare with:

```bash
mongosh 'mongodb://127.0.0.1:27018/?directConnection=true&tls=false&serverSelectionTimeoutMS=3000'
```

On the non-TLS local lab, the second case can connect.

**Lesson:** TLS mode must match on both ends. For Atlas/production, **do not downgrade `tls=false` to fix errors**; fix CA/certificate/TLS compatibility properly.

---

## 28. Lab 4 — Wrong Topology/Replica Set Name

Goal: see the network being reachable while the driver cannot select an eligible server.

If the local lab is standalone only:

```bash
mongosh 'mongodb://127.0.0.1:27018/?replicaSet=wrongSet&serverSelectionTimeoutMS=3000'
```

Because you requested a replica set named `wrongSet` while the server is standalone, the driver cannot find a server matching the topology and reports a selection timeout or corresponding topology error.

Compare:

```bash
mongosh 'mongodb://127.0.0.1:27018/?directConnection=true&serverSelectionTimeoutMS=3000'
```

The second command connects directly to the standalone lab.

**Note:** this case does not represent a production replica set losing its primary; diagnosing failover requires cluster status/`rs.status()` of a real replica set, not triggering an election in production.

---

## 29. Lab 5 — Testing Java/Spring Across Environments

Using the same Java `ping` code from section 16, test in sequence:

1. **Local:** `mongodb://127.0.0.1:27018/?directConnection=true`.
2. **Wrong hostname:** `mongodb://db-does-not-exist.invalid:27017/?serverSelectionTimeoutMS=3000`.
3. **Wrong port:** `mongodb://127.0.0.1:27019/?serverSelectionTimeoutMS=3000`.
4. **Local TLS mismatch:** local lab URI with `tls=true`.
5. **Authorized Atlas development cluster:** URI from the Atlas Connect modal, via secrets injection, without logging passwords.

Record in a table:

| Case | DNS | TCP | TLS | SDAM | Ping | Exception/cause |
| --- | --- | --- | --- | --- | --- | --- |
| Valid local | ... | ... | ... | ... | ... | ... |
| Invalid hostname | ... | ... | ... | ... | ... | ... |
| Closed port | ... | ... | ... | ... | ... | ... |
| TLS mismatch | ... | ... | ... | ... | ... | ... |
| Atlas dev | ... | ... | ... | ... | ... | ... |

**Every exception string does not need to match identically across driver versions.** What matters is distinguishing the **broken layer** using evidence.

---

## 30. Observability and Operations: Avoiding "Blind Retries"

### 30.1. Essential Metrics

| Metric | Purpose |
| --- | --- |
| Server selection latency/errors | Failure to select server/topology |
| TCP connect failures/timeouts | Network route/listener |
| TLS handshake errors | Cert/protocol/trust |
| DNS query failures | Resolver/SRV/TXT/A/AAAA |
| Connection pool checkout wait | Pool saturation |
| Current/open/checked-out connections | Client load |
| MongoDB CPU/disk/network | Server overload |
| Primary elections/replication lag | Replica set availability |
| App request p95/p99 | User-facing impact |
| Error/timeout/retry rate | Amplification and SLO |
| Egress NAT/source IP changes | Atlas access list drift |
| Certificate expiry/rotation events | TLS readiness |

### 30.2. Driver Monitoring

The MongoDB Java Driver provides listeners for:

- SDAM/cluster/server changes.
- Command started/succeeded/failed.
- Connection pool created/cleared/checkout failures.
- Heartbeat metrics/events.

Enable log levels and instrumentation appropriate for your framework/version. Do not print raw URIs with credentials or full command bodies containing PII. Only enable verbose debug logging for a limited time, with an owner and retention policy.

### 30.3. Retry Policy

- Distinguish **transient failover** from permanent misconfiguration.
- Use exponential backoff with jitter and a bounded retry budget.
- Avoid multiple layers retrying simultaneously (load balancer → API → SDK → driver).
- For writes, account for ambiguous outcomes/idempotency keys.
- If the server is unreachable due to wrong DNS, infinite retries only flood logs and complicate triage.
- Implement circuit breakers/load shedding if the application needs to protect upstream/downstream services.

### 30.4. Focus on Fixing the Actual Cause

Do not create a "fix" simply by changing 30s to 120s. If the issue is an expired TLS cert, **120s only makes users wait longer**. If the issue is a 2–5s primary election, an appropriate timeout combined with driver retries may help; still monitor election frequency.

---

## 31. Misconceptions to Avoid

| Misconception | Reality |
| --- | --- |
| "Server selection timeout means the database is shut down" | Could be DNS/TCP/TLS/selector/replica set |
| "Resolving DNS A is enough for +srv" | Requires SRV, target A/AAAA, and TXT when applicable |
| "SRV having a target means TCP is open" | The network must still connect to target:port |
| "Ping failing means the port is closed" | ICMP may be blocked |
| "Test-NetConnection OK means MongoDB authenticated" | Only tests TCP |
| "TLS OK means user/password are correct" | Authentication is a separate layer |
| "SSLHandshakeException just needs a higher timeout" | Must fix CA/hostname/protocol |
| "Disabling tlsAllowInvalidHostnames is a safe solution" | No; a valid cert SAN is needed |
| "JDK always trusts every CA the OS trusts" | The JVM has its own truststore |
| "SRV URI can include :27017" | SRV URIs do not accept a port directly |
| "MongoDB SRV defaults to TLS=false" | SRV enables TLS by default |
| "If no primary is seen, read/write to secondary as usual" | Writes require primary; reads have consistency constraints |
| "directConnection=true fixes production failover" | It restricts topology discovery |
| "Creating MongoClient means ping will definitely work" | The driver can connect lazily/discover asynchronously |
| "Pool timeout is a DNS timeout" | Pool checkout is a different layer |
| "maxPoolSize=100 means the whole cluster has only 100 sockets" | Pool is per server, per MongoClient |
| "Increasing maxPoolSize indefinitely is a fix" | Can cause saturation |
| "Compass OK on laptop means pod is OK" | Different DNS/network/egress/TLS runtime |
| "Private endpoint can use any public DNS" | May require split-horizon DNS |
| "Disabling TLS to debug Atlas is fine" | Violates security requirements |
| "AuthenticationFailed means TCP hasn't reached yet" | Usually TLS/connection passed and auth was rejected |
| "One timeout value explains every timeout" | Deadlines have different scopes |
| "Changing password without reading root cause" | Does not address DNS/TCP/TLS |
| "Every advertised node is reachable if seed is reachable" | Internal hostnames may be unreachable |
| "Java with the same URI as mongosh has identical TLS" | JVM truststore differs from OS/Node |
| "Logging the raw connection string is harmless" | Can expose username/password |

---

## 32. Practice Exercises

### Exercise 1 — Connection Chain

Order these: TLS, DNS, authentication, TCP, SDAM, pool checkout.

**Answer:** URI parse → DNS → TCP → TLS → SDAM/hello → authentication → pool checkout/command, with some monitoring/pooling activities overlapping depending on the driver.

### Exercise 2 — Server Selection

Does `MongoTimeoutException` always mean MongoDB Server is shut down?

**Answer:** No; the driver could not select an eligible server within the limit.

### Exercise 3 — Root Cause

A stack trace has `MongoTimeoutException` and a nested `UnknownHostException`. Which layer do you check first?

### Exercise 4 — DNS SRV

For `mongodb+srv://cluster0.example.mongodb.net/`, which SRV record name is queried?

**Answer:** `_mongodb._tcp.cluster0.example.mongodb.net`.

### Exercise 5 — SRV URI

Is this valid: `mongodb+srv://cluster0.example.mongodb.net:27017/`?

**Answer:** No; an SRV URI takes only a single hostname and does not specify a port directly.

### Exercise 6 — TXT

What kind of information can a TXT record supply? Why must you check both SRV and TXT on an SRV URI?

### Exercise 7 — DNS NXDOMAIN

If `Resolve-DnsName` returns NXDOMAIN, why won't increasing `connectTimeoutMS` solve it?

### Exercise 8 — DNS SERVFAIL

Name three causes originating from the resolver, forwarding, or outbound DNS policy.

### Exercise 9 — Split DNS

A laptop resolves a public IP while a pod resolves a private IP. Is that always an error?

**Answer:** No; a private endpoint may use split-horizon DNS.

### Exercise 10 — TCP Refused

Does `Connection refused` prove the username/password is wrong?

**Answer:** No; TCP was rejected before authentication.

### Exercise 11 — TCP Timeout

Distinguish a firewall drop from a firewall reject by connection behavior.

### Exercise 12 — Ping

Why is a failed ICMP `ping` insufficient to conclude TCP port 27017 is blocked?

### Exercise 13 — Windows

Write a PowerShell command to test TCP to `db1.example.net:27017`.

**Answer:** `Test-NetConnection -ComputerName db1.example.net -Port 27017`.

### Exercise 14 — Linux

Write an `nc` command to test TCP to the real hostname and port from an SRV record.

### Exercise 15 — Atlas Allow-List

Why does allow-listing a laptop IP not guarantee an app pod can connect?

### Exercise 16 — Private Endpoint

SRV returns a record, yet target A returns a public IP inside a VPC with only private routes. What do you inspect?

### Exercise 17 — TLS Defaults

Distinguish the TLS default of standard `mongodb://` vs. SRV `mongodb+srv://`.

**Answer:** Standard typically disables TLS by default; SRV enables TLS by default.

### Exercise 18 — PKIX

What does `PKIX path building failed` suggest, and what is the safe remediation path?

### Exercise 19 — SAN

The URI uses an IP, but the server certificate only has a DNS SAN. What needs to be fixed?

### Exercise 20 — mTLS

Distinguish a truststore from a keystore in Java.

### Exercise 21 — JDK

Compass connects, while Java fails TLS. Why must you check the JDK truststore and TLS versions?

### Exercise 22 — Security

Why should you not set `tlsAllowInvalidHostnames=true` to handle hostname mismatch in production?

### Exercise 23 — Server Selection vs. Connect

Explain the two options `serverSelectionTimeoutMS` and `connectTimeoutMS`.

### Exercise 24 — Pool

A pool already has 100/100 connections checked out; what must an additional request do? How do its symptoms differ from a server selection timeout?

### Exercise 25 — CSOT

Which stage's deadline is `timeoutMS`/CSOT? Why is it necessary to verify the driver version?

### Exercise 26 — Replica Set

The driver sees a connected SECONDARY, yet requires a PRIMARY. Why might it time out?

### Exercise 27 — Read Preference

Switching from `primary` to `secondaryPreferred` may help a read when no primary is present; what is the consistency risk?

### Exercise 28 — `replicaSet`

The URI specifies `replicaSet=rsWrong`, while the server reports `rs0`. What needs to be fixed?

### Exercise 29 — Advertised Hostname

The seed is reachable, yet `hello` returns internal names that the client cannot resolve. At which layer do you fix this?

### Exercise 30 — directConnection

How is `directConnection=true` useful in an SSH tunnel? Why is it not a long-term solution for high availability?

### Exercise 31 — Lazy Connection

Why does succeeding in creating a `MongoClient` not prove connectivity? Which command verifies it?

**Answer:** Execute the `ping` command and inspect the result.

### Exercise 32 — Authentication

`AuthenticationFailed`, error code 18; why is this usually not a DNS failure?

### Exercise 33 — Password URI

A password contains `@` and `:`. What encoding is needed when placing it in a URI? Is encoding needed when typing it into a password prompt?

### Exercise 34 — Spring Data

A Spring Boot app starts OK, yet only the first request times out. Why can this happen?

### Exercise 35 — Docker

Inside a container, does `localhost` refer to the host laptop or the container itself?

**Answer:** The container/pod network namespace itself.

### Exercise 36 — Kubernetes

List the checks for CoreDNS, NetworkPolicy, NAT egress, and private endpoints before concluding Atlas is broken.

### Exercise 37 — Connection Churn

Why does creating a `MongoClient` for every HTTP request easily cause a connection storm?

### Exercise 38 — Timeout Budget

The API gateway times out after 15s, while the driver has `serverSelectionTimeoutMS=120000`. What are the risks?

### Exercise 39 — Case Study

An app on EKS gets `MongoTimeoutException` after deployment; Compass on laptop is OK, DNS SRV/A pass, and TCP inside the pod fails. Create an investigation plan and fix the right layer.

### Exercise 40 — Comprehensive Case Study

After certificate rotation, Java pods fail with PKIX while `mongosh` on a bastion host is OK. Create a checklist verifying the JDK truststore/CA chain, checking clock synchronization, and executing a safe rollout.

---

## 33. Production Checklist

### URI and Credentials

- [ ] Correct `mongodb`/`mongodb+srv` scheme.
- [ ] Hostname/port taken from the official deployment/Atlas URI.
- [ ] Correct `replicaSet`, `authSource`, and read preference.
- [ ] URI password properly percent-encoded, not double-encoded.
- [ ] Secrets are not present in tickets, command history, or logs.
- [ ] User/cert rotation and rollback procedures exist.

### DNS and Network

- [ ] SRV/TXT/A/AAAA checked from the application runtime.
- [ ] Resolver/CoreDNS/VPC DNS/Private Endpoint properly verified.
- [ ] TCP reaches every required target on the right host/port.
- [ ] Atlas IP access list matches the actual egress IP.
- [ ] `ping` is not used as the sole TCP test.
- [ ] Self-managed `bindIp`/listener/firewall configured correctly.
- [ ] Replica set advertised member hostnames are reachable.
- [ ] Private DNS is not arbitrarily switched to public resolvers.

### TLS and Authentication

- [ ] TLS mode matches the server and policy.
- [ ] CA chain is trusted, SAN matches hostname, and certificate is not expired.
- [ ] JDK truststore/keystore are correct, and clock/NTP is accurate.
- [ ] Invalid hostname/certificate flags are not enabled in production.
- [ ] Client cert/X.509 is correct if mTLS is required.
- [ ] MongoDB database user, `authSource`, and SCRAM/X.509 mechanism are correct.
- [ ] TLS debug logs are protected and turned off after investigation.

### SDAM, Pool, and Timeouts

- [ ] Primary/secondary available matching the operation/read preference.
- [ ] Cluster description and nested exceptions preserved after redaction.
- [ ] Timeouts designed around SLOs.
- [ ] Not increasing all timeouts to mask errors.
- [ ] `MongoClient` singleton and reasonable pool sizing in place.
- [ ] Checkout wait, selection failures, and retries monitored.
- [ ] Health/readiness probes execute bounded operations.
- [ ] Failover and recovery incident runbook exists.

### Post-Incident

- [ ] Root cause identified by specific layer.
- [ ] Verified DNS → TCP → TLS → SDAM → auth → `ping`.
- [ ] Tested from all affected AZs/regions or runtime types.
- [ ] Checked app p95/p99, error/retry rates, and DB cluster health.
- [ ] Recorded timeline, owner, changes, rollback, and preventive actions.
- [ ] Sensitive data excluded from the postmortem.

---

## 34. Summary

MongoDB connection failures must be analyzed as a **dependency chain**, not a single error:

1. **URI** must have the right scheme, hostname, port, credentials, and options.
2. **DNS**: for `mongodb+srv`, verify SRV/TXT and A/AAAA for each target; for Private Endpoints, verify private DNS from the right runtime.
3. **TCP**: test the real port with `Test-NetConnection`/`nc`, and verify firewalls, routes, egress IPs, and the Atlas allow-list.
4. **TLS**: verify the certificate chain, Java truststore, SAN, expiry, SNI, protocol, and mTLS; never disable verification in production.
5. **SDAM/server selection**: `MongoTimeoutException` indicates the driver **could not find a server matching the selector** within budget; the root cause may be DNS/TCP/TLS or a replica set lacking an eligible primary.
6. **Authentication**: after network/TLS, verify user/password/`authSource` and authentication mechanism.
7. **Connection pool** and operation timeouts are a separate layer from server selection; async/threads/pools all have limits.
8. **Verify real connectivity with `ping`**; creating `MongoClient` alone is not enough.
9. **Production operations** must rely on error chain + cluster description + DNS/TCP/TLS evidence + Atlas/server metrics as the source of truth, rather than just increasing timeouts.

The best operational question is:

> **"At which step of DNS → TCP → TLS → SDAM → authentication → pool/command does the error appear, and which measurement proves it?"**

### Official MongoDB Documentation

- [MongoDB — Troubleshoot Server Selection Timeout](https://www.mongodb.com/docs/manual/troubleshooting/server-selection-timeout/) — DNS, network, TLS causes and troubleshooting methods.
- [MongoDB Atlas — Troubleshoot Connection Issues](https://www.mongodb.com/docs/atlas/troubleshoot-connection/) — IP access list, SRV records, TLS, ports, auth.
- [MongoDB Atlas — Troubleshoot Private Endpoint Connections](https://www.mongodb.com/docs/atlas/troubleshoot-private-endpoints/) — private DNS, endpoint status, and routing.
- [MongoDB — Connection String Formats](https://www.mongodb.com/docs/manual/reference/connection-string-formats/) — standard/SRV syntax, seedlist.
- [MongoDB — Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/) — TLS, authentication, read preference, and timeouts.
- [MongoDB Java Sync Driver — Connection Troubleshooting](https://www.mongodb.com/docs/drivers/java/sync/current/connection/connection-troubleshooting/) — MongoTimeoutException, cluster description, TLS diagnostics.
- [MongoDB Java Sync Driver — Cluster Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/cluster-settings/) — `serverSelectionTimeoutMS`, `localThresholdMS`.
- [MongoDB Java Sync Driver — Socket Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/socket-settings/) — `connectTimeoutMS`, `socketTimeoutMS`.
- [MongoDB Java Sync Driver — Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/) — maxPoolSize, maxConnecting, and pool wait.
- [MongoDB Java Sync Driver — Client-Side Operation Timeout](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/csot/) — CSOT/`timeoutMS`, experimental note.
- [MongoDB Java Sync Driver — TLS/SSL](https://www.mongodb.com/docs/drivers/java/sync/current/security/tls/) — truststore, keystore, SAN, and certificate verification.
- [MongoDB Manual — Replication](https://www.mongodb.com/docs/manual/replication/) — replica set, roles, failover.
- [MongoDB Manual — Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/) — server selector semantics.
- [MongoDB Java Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/) — command/pool events.
- [Spring Boot — MongoDB](https://docs.spring.io/spring-boot/reference/data/nosql.html) — MongoDB autoconfiguration.
- [Spring Boot Actuator — Health](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — liveness/readiness/health groups.
