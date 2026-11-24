# 7.6 Authentication, TLS, and read vs. control authorization on the management channel

**JMX (Java Management Extensions)** supports reading and managing JVM and application state through **MBeans**. You can inspect heap, GC, class loading, thread counts, health, and business metrics—yet you may also encounter MBeans that modify configuration or invoke operations that alter runtime behavior. An improperly secured JMX Remote port can turn a diagnostic interface into a sensitive control channel.

To protect the **JMX management channel**, separate three independent questions:

- **Authentication — Who is connecting?** For example, username/password identity, JAAS, or TLS client certificates.
- **TLS — Is the connection encrypted and did the client verify the right server?** Covers encryption, certificate chains, hostnames, and sometimes mutual TLS (mTLS).
- **Authorization — Once authenticated, what is that identity allowed to do?** For example, **readonly** for monitors vs. **readwrite** for authorized operators.

This lesson focuses on the **JDK 21 / HotSpot ready-to-use management agent** using JMX Remote with the **RMI connector**. The **com.sun.management.jmxremote.*** properties are specific to JDK/HotSpot configuration, not a guarantee that every Java SE 21 JVM implements the exact same mechanism. Network addresses, file paths, and PIDs are for learning, not production system details.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish **MBeanServer**, **JMX connector**, **RMI registry**, local Attach API, and remote management.
2. Explain the differences between **TLS server authentication**, **mTLS client authentication**, JMX accounts, and MBean permissions.
3. Design a **jmxremote.access** file for `readonly` monitors and `readwrite` operators following **least privilege**.
4. Understand the **jmxremote.password** mechanism, file permission requirements, and why plaintext password files should not be used casually in production.
5. Understand the consequences of **authenticate=false**, **ssl=false**, and an unprotected registry lacking TLS.
6. Configure **jmxremote.port**, **jmxremote.rmi.port**, **java.rmi.server.hostname**, and recognize RMI limitations inside Docker/Kubernetes.
7. Verify in practice that **getAttribute** reads succeed while **setAttribute** writes or **invoke** calls are rejected for a `readonly` role.
8. Prepare keystores/truststores and validate certificates without embedding secrets in source code or arguments.
9. Distinguish network, TLS handshake, authentication, and authorization errors when troubleshooting JMX connections.
10. Enforce boundaries across remote JMX, local attach, Kubernetes RBAC, and existing active sessions.

## 2. Security layers overview

~~~text
Operator / JConsole / monitoring service
          |
          |  (A) Network controls: firewall, VPN, allowlist, tunnel
          v
RMI registry / JMX connector
          |
          |  (B) TLS: encryption, server trust, client cert required?
          |  (C) Authentication: which principal logged in?
          v
Authorization / MBeanServerForwarder
          |
          |  (D) readonly or readwrite? which operations?
          v
Platform MBeans and Application MBeans
~~~

| Layer | Controls | Does not replace |
| --- | --- | --- |
| **Network** | Which client sources can reach registry/connector ports. | Does not verify user identity or which operations are invoked. |
| **TLS** | Encrypts transport and authenticates peers via certificates. | Does not grant or restrict MBean permissions. |
| **Authentication** | Verifies user or client identity. | Does not guarantee the user is read-only. |
| **Authorization** | Allows/blocks `getAttribute`, `setAttribute`, and `invoke`. | Does not encrypt traffic or open/close network ports. |
| **Audit** | Tracks who accessed, what changed, and when. | Does not prevent unauthorized connections on its own. |

**Being able to connect does not mean trusted. Having TLS does not mean readonly. Having a username/password does not mean traffic is encrypted.** These three misconceptions cause many remote management incidents.

## 3. Distinguishing local JMX from remote JMX

On HotSpot JDK 21, **local JMX / Attach API** can let tools like JConsole attach to a JVM on the same host governed by **OS user and file permissions**. JDK documentation describes the private local connector and states that **the remote agent's password/access files are not checked for requests arriving via the local connector**.

Therefore:

- Having **monitorRole readonly** in **jmxremote.access** does not prove every process running under the same OS user on that machine is **read-only**.
- Anyone permitted to exec into the same container, read secrets, attach, or run code inside the process has a **separate** control path from the remote connector.
- Running **jcmd PID ...** uses the diagnostic/attach mechanism, not a JMX Remote login with `monitorRole`.
- You must govern **OS permissions, PID/namespaces, exec/attach rights, and container isolation** alongside remote JMX authentication.

For **remote management**, configure the JMX agent/connector to listen on an appropriate port. On the ready-to-use agent, **com.sun.management.jmxremote.port** enables the RMI remote endpoint. Those ports enforce configured authentication, TLS, and access files; never assume they share the exact same behavior as the local connector.

### 3.1. An example of testing the wrong path

You run JConsole on the same node under the Java process's OS account and notice you can modify an MBean attribute. Seeing **monitorRole readonly** in your access file, you assume the policy is being ignored.

Chances are you connected via **local Attach**. Test through the **actual remote JMX service URL** using `monitorRole` and proper TLS/certificates. Testing locally to prove remote authorization leads to false conclusions. Conversely, if local attach is overly broad, fix **permissions at the OS/deployment layer**, not merely the remote role file.

## 4. Authentication with a password file

### 4.1. Two files with distinct purposes

The agent uses two separate files:

- **jmxremote.password**: principal/role mapped to a password, or replaced by a supported login mechanism.
- **jmxremote.access**: principal/role mapped to **readonly** or **readwrite**, optionally with extra clauses.

An identity using file-based login must be validly declared in both. The names **monitorRole** and **controlRole** in documentation are common examples, not pre-enabled default accounts with passwords.

Illustrative configuration paths:

~~~properties
com.sun.management.jmxremote.authenticate=true
com.sun.management.jmxremote.password.file=/run/secrets/jmxremote.password
com.sun.management.jmxremote.access.file=/etc/jmx/jmxremote.access
~~~

These lines are **part of a configuration**, not a complete remote agent setup. By default these files often reside in **$JAVA_HOME/conf/management** on standard JDKs; use dedicated paths managed per application and secret policy.

### 4.2. Password files have strict security constraints

Per JDK 21 documentation, file-based JMX passwords are stored in Java properties format with **clear-text password values** and are regarded as better suited for development or tightly controlled scenarios. Production environments should pair client certificates and/or JAAS/login modules per approved identity policy.

On Linux/macOS, the password file must restrict read/write permissions solely to the owner, typically **0600**. The JDK checks file permissions to prevent secrets from being readable by other users; if permissions are too permissive, the agent can refuse startup.

~~~bash
# View metadata only; never print passwords
ls -l /run/secrets/jmxremote.password
stat /run/secrets/jmxremote.password
~~~

**Never use `cat`/`echo` to print real secrets into shared terminals or CI logs.** Restrict permissions on parent directories, secret volumes, and container root/exec access. The file must exist inside the **JVM's filesystem/mount namespace** and be readable by the JVM user. Having the right filename on the host does not guarantee a containerized JVM sees it.

### 4.3. authenticate=false is a dangerous permission change

The following option **is not a recommended production setting**:

~~~properties
com.sun.management.jmxremote.authenticate=false
~~~

With the ready-to-use JMX agent, this **disables both the password and access files**. Clients allowed to connect gain full agent access—even if the access file still lists **monitorRole readonly**. **Being on an internal network does not fix this authorization hole.**

Combining **authenticate=false** with **ssl=false** is especially dangerous: there is neither password-based authentication/role enforcement nor connector encryption. Never use it as a temporary workaround when JConsole cannot connect.

If a design relies solely on mTLS client certificates without passwords, it requires a **verified authentication/authorization architecture**. Never assume presenting a client certificate automatically restricts a principal to `readonly`.

### 4.4. JAAS, LDAP, and alternative authentication

With the ready-to-use agent, **JAAS** can be selected via **com.sun.management.jmxremote.login.config** alongside a matching login configuration. The JMX API also offers **JMXAuthenticator** for custom connectors.

~~~properties
com.sun.management.jmxremote.login.config=EnterpriseJmxLogin
~~~

**EnterpriseJmxLogin** is an illustrative login entry name; it works only when declared and loaded by the JVM via an actual JAAS config. The authenticated identity must still be **mapped to the right role/policy**. A successful LDAP login does not automatically grant `readwrite`; operators must still verify access mapping, auditing, and session lifecycles.

## 5. Authorization: readonly and readwrite

Example **jmxremote.access** file:

~~~properties
monitorRole readonly
controlRole readwrite
~~~

| Permission | Example | Recommendation |
| --- | --- | --- |
| **readonly** | Read MBean attributes, inspect metadata, receive notifications. | Monitoring/dashboard accounts needing read access. |
| **readwrite** | Read/modify writable attributes, invoke MBean operations. | Only trusted operators under approval workflows. |
| **create/unregister** (policy-dependent) | Create or unregister MBeans. | Grant only with clear need, restricting classes and privileges. |

**readonly** restricts state-mutating operations over an **access-controller-protected remote connector**. However, an application-written getter can still be **slow, trigger side effects, or leak sensitive data** if implemented unsafely. "Read-only" does not mean "safe for everyone to read."

**readwrite** can permit broader system changes than expected. It is not scoped to editing one specific attribute. If an organization needs **Team A to toggle only feature flag X** and **Team B to view only MBean Y**, simple `readonly`/`readwrite` roles are too coarse.

### 5.1. Access files are not fine-grained per-method RBAC

Java JMX supports richer security configurations, such as **MBeanServerForwarder** or application-level security. Implemented properly, these can enforce checks per ObjectName, operation, and identity.

Ready-to-use access files generally provide **coarse-grained** roles. Never assume they support application-domain operation wildcards without proof. Build a **management gateway** or controller enforcing granular policies when control operations are highly sensitive.

### 5.2. Notes on create and unregister

JDK 21 allows **readwrite** entries with **create** and/or **unregister** clauses. These permit actions even more powerful than reading/writing attributes. Sample access files bundled with the JDK may grant a control role extra privileges. **Always inspect the exact file your JVM loads.**

Never grant **create** for arbitrary classes. MBean creation can expand the process's code execution surface; restrict it strictly to trusted classes and approved use cases. For observation, **monitorRole readonly** is almost always the right choice.

## 6. TLS: encryption and peer verification

When **com.sun.management.jmxremote.ssl=true**, the JMX connector uses SSL/TLS per agent settings. JDK 21 docs note SSL is enabled by default for remote management, yet you **still must provision certificates, keystores, and truststores properly**. Without a configured trust chain, `ssl=true` will not make connections succeed automatically.

**One-way TLS**:

1. The server holds its private key/certificate in a **keystore**.
2. The client holds trust anchors in a **truststore** and verifies the server.
3. The client validates the certificate chain, hostname/SAN, expiry, and trusted algorithms.
4. Connector traffic is encrypted under the TLS session.

**Mutual TLS (mTLS)**:

1. The server proves its identity to the client.
2. The client also presents a certificate; the server verifies it against the client truststore.
3. Certificate identity serves as an authentication layer; MBean actions still require authorization.

Related JSSE properties example:

~~~properties
javax.net.ssl.keyStore=/run/secrets/jmx-server.p12
javax.net.ssl.keyStoreType=PKCS12
javax.net.ssl.trustStore=/run/secrets/jmx-client-trust.p12
javax.net.ssl.trustStoreType=PKCS12
~~~

This is only a **file-location layout**, not sufficient to launch: you need real keystores/truststores, certificate chains, secret injection for passwords, SANs matching the connection address, and certificate lifecycle policies. Never commit private keys to git or place store passwords in shared scripts.

### 6.1. Key JDK 21 parameters to remember

| Property | Meaning |
| --- | --- |
| **com.sun.management.jmxremote.ssl=true** | Enables TLS on the remote connector. |
| **com.sun.management.jmxremote.ssl.need.client.auth=true** | Requires client certificate authentication during connector TLS. |
| **com.sun.management.jmxremote.registry.ssl=true** | Enables TLS for the **RMI registry**, a separate component. |
| **com.sun.management.jmxremote.ssl.enabled.protocols** | Selects allowed TLS protocol versions. |
| **com.sun.management.jmxremote.ssl.enabled.cipher.suites** | Selects allowed cipher suites. |
| **javax.net.ssl.keyStore** | Peer's key/cert store. |
| **javax.net.ssl.trustStore** | Trust anchors to verify the peer's certificate. |

Never copy TLS ciphers/protocols from legacy JDK configs into production. Follow your Java 21 vendor, algorithms disabled in **java.security**, PKI standards, and actual clients. Never disable certificate validation or skip hostname verification to "fix" `SSLHandshakeException`.

## 7. RMI registry and connector: two separate boundaries

An RMI-based remote JMX client typically passes through two stages:

~~~text
JMX client
    |
    +--- RMI registry: jmxremote.port
    |           |
    |           +-- Looks up jmxrmi, receives connector stub
    |
    +--- RMI connector: jmxremote.rmi.port
                |
                +-- TLS -> authentication -> JMX operations
~~~

HotSpot JDK 21 includes **com.sun.management.jmxremote.registry.ssl**, which **defaults to false** even when connector SSL is enabled. This matters because an unprotected registry can expose risks of returning a **spoofed connector stub** in certain scenarios; Oracle documentation warns of potential password disclosure if clients trust an insecure registry.

To protect the registry with TLS:

~~~properties
com.sun.management.jmxremote.registry.ssl=true
com.sun.management.jmxremote.ssl.need.client.auth=true
com.sun.management.jmxremote.ssl=true
~~~

Documentation recommends enabling **TLS client certificate** authentication alongside **registry.ssl=true** for full security. Clients must support **SSL-protected registry lookup**, not just TLS on the connector; otherwise, connections can still fail even with valid usernames/passwords.

**Do not assume connector SSL covers every RMI hop.** Registry, connector, trust/certificates, authentication, and access policy must each be evaluated independently.

### 7.1. Two ports and the advertised hostname

Loopback example for a lab with JVM and client on the same host environment:

~~~properties
com.sun.management.jmxremote.port=7091
com.sun.management.jmxremote.rmi.port=7092
com.sun.management.jmxremote.host=127.0.0.1
java.rmi.server.hostname=127.0.0.1
~~~

- **7091** is the registry port.
- **7092** is the pinned connector port.
- **com.sun.management.jmxremote.host** affects the agent's bind address per JDK capabilities.
- **java.rmi.server.hostname** determines the hostname/IP embedded into the RMI stub for the client to follow to the connector.

**`127.0.0.1` above is strictly for loopback labs.** If the client is on another machine, a loopback stub causes the client to connect to itself. Inside containers, the JVM's loopback is not the Docker host's or laptop's loopback. Never open all interfaces to the Internet to compensate for a bad stub; configure DNS/certificate SANs, network topology, and ports properly.

### 7.2. Service URL for RMI JMX

Clients use the standard URL:

~~~text
service:jmx:rmi:///jndi/rmi://hostName:portNum/jmxrmi
~~~

**portNum** in the URL is the registry port. After lookup, the stub may advertise a different connector endpoint. If the client connects to the registry successfully yet hits **Connection refused** or timeout afterward, inspect hostname, connector port, firewalls, and TLS—do not immediately reset passwords.

JMX RMI **is not HTTP**. A standard HTTPS Ingress will not automatically proxy the RMI protocol or the handoff from registry to connector. Over VPNs/tunnels/bastions, both ports and the stub address must align.

## 8. Secure configuration skeleton for review

The block below lists **properties expected in a secure design**, not a copy-paste production file. It **intentionally omits credentials, certificates, and password values**; operators must provision those via secret managers/PKI and ensure the JVM loads them properly.

~~~properties
# RMI on loopback in a lab
com.sun.management.jmxremote.port=7091
com.sun.management.jmxremote.rmi.port=7092
com.sun.management.jmxremote.host=127.0.0.1
java.rmi.server.hostname=127.0.0.1

# Identity + authorization
com.sun.management.jmxremote.authenticate=true
com.sun.management.jmxremote.password.file=/run/secrets/jmxremote.password
com.sun.management.jmxremote.access.file=/etc/jmx/jmxremote.access

# TLS for connector and registry, client cert authentication
com.sun.management.jmxremote.ssl=true
com.sun.management.jmxremote.registry.ssl=true
com.sun.management.jmxremote.ssl.need.client.auth=true
~~~

The **com.sun.management.jmxremote** properties can be passed with **-Dkey=value** at JVM startup or placed in management config files per JDK documentation. JSSE properties such as **javax.net.ssl.keyStore** and **trustStore** must also be set through an appropriate JVM/deployment mechanism; never assume an arbitrary properties file path will be auto-loaded by the JVM.

The **monitorRole** and **controlRole** accounts in **jmxremote.access** must have matching authentication entries. Password files need valid permissions; keystore/truststore certificates need valid trust chains and key passwords. Otherwise, the JVM may refuse to start with the management agent enabled.

### 8.1. Why not put passwords in command-line examples?

**Discouraged** example:

~~~text
-Djavax.net.ssl.keyStorePassword=secret-displayed-in-process-list
~~~

That illustrates what **to avoid**, not a real password or command to run. Command-line arguments can be captured by process listings, runtime metadata, deployment manifests, crash diagnostics, and CI logs. Use approved secret-management workflows, strict file permissions, rotation, and never write secrets into lessons or code.

## 9. Runnable Java 21: safe MBean for testing reads and writes

To test authorization without touching a production JVM, create a **test MBean** in a standalone Java process. It exposes a read/write **Limit** attribute and a **Reset** operation. The Java class itself does not check remote roles; roles are enforced by the **remote JMX connector's** access controller.

**File JmxRoleLab.java:**

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.StandardMBean;

public final class JmxRoleLab {
    public interface DemoControlMBean {
        int getLimit();
        void setLimit(int newLimit);
        void reset();
    }

    public static final class DemoControl
            implements DemoControlMBean {
        private int limit = 10;

        @Override
        public synchronized int getLimit() {
            return limit;
        }

        @Override
        public synchronized void setLimit(int newLimit) {
            if (newLimit < 1 || newLimit > 100) {
                throw new IllegalArgumentException(
                        "Limit must be 1..100");
            }
            limit = newLimit;
        }

        @Override
        public synchronized void reset() {
            limit = 10;
        }
    }

    public static void main(String[] args)
            throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
                "training.jmx:type=DemoControl");

        server.registerMBean(
                new StandardMBean(
                        new DemoControl(),
                        DemoControlMBean.class),
                name);

        System.out.println("MBean=" + name);
        System.out.println("InitialLimit="
                + server.getAttribute(name, "Limit"));
        System.out.println("Window=120 seconds");

        Thread.sleep(120_000L);
        System.out.println("FinalLimit="
                + server.getAttribute(name, "Limit"));
    }
}
~~~

Compile and run with JDK 21:

~~~bash
javac --release 21 JmxRoleLab.java
java JmxRoleLab
~~~

**The first three stdout lines are always identical when startup succeeds:**

~~~text
MBean=training.jmx:type=DemoControl
InitialLimit=10
Window=120 seconds
~~~

After about 120 seconds, the program prints **FinalLimit=...**. If no client modified it, the value is **10**. If a `readwrite` client changed **Limit**, the final value will reflect that.

**Plain `java JmxRoleLab` only registers the MBean in the platform MBeanServer; it does not open remote JMX.** To test remote roles, launch the lab JVM with remote agent `-D` properties provisioned with proper TLS/certs/secrets, or use a controlled test connector.

### 9.1. A meaningful authorization test

Use a **remote JMX client configured with TLS/mTLS** connecting to the lab JVM—not a local JConsole tab:

- **monitorRole readonly**: reading **Limit** succeeds, while calling **setAttribute** on `Limit` or **invoke Reset** must be rejected.
- **controlRole readwrite**: allowed to read, write `Limit`, and invoke `Reset` if configured policy permits and the MBean exposes them.
- **Wrong password**: connection must fail during authentication.
- **Untrusted client cert** under mTLS: must be rejected during the TLS handshake.
- **Client from disallowed network**: must be unable to reach registry/connector ports.

**Never test writes against a production platform MBean** such as toggling logging, resetting subsystems, or forcing GC just to prove a role works. The lab MBean has minimal side effects and is designed for this purpose.

**Important limitation:** calling **MBeanServer.setAttribute** directly inside the same JVM bypasses remote password/access files; local code modifying `Limit` does not prove remote roles are broken. Role tests must traverse the **remote connector** actually protected by the policy.

## 10. Runnable Java 21: client reading an MBean over remote JMX

The example below only **reads the `Limit` attribute** and invokes no state-mutating operations. The password is read from **console**, not passed as a CLI argument. The program **compiles on JDK 21**, though a successful connection depends on the remote agent, TLS certificates, RMI registry socket factory, and credentials being deployed compatibly.

**File JmxReadProbe.java:**

~~~java
import java.io.Console;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public final class JmxReadProbe {
    public static void main(String[] args)
            throws Exception {
        if (args.length != 3) {
            System.out.println(
                    "Usage: java JmxReadProbe host port role");
            return;
        }

        Console console = System.console();
        if (console == null) {
            throw new IllegalStateException(
                    "A console is required to enter the password");
        }

        char[] secret = console.readPassword(
                "JMX password for %s: ", args[2]);
        if (secret == null) {
            throw new IllegalStateException(
                    "Password input cancelled");
        }

        String[] credentials =
                {args[2], new String(secret)};
        Arrays.fill(secret, '\0');

        int port = Integer.parseInt(args[1]);
        JMXServiceURL url = new JMXServiceURL(
                "service:jmx:rmi:///jndi/rmi://"
                        + args[0] + ":" + port + "/jmxrmi");

        Map<String, Object> env = new HashMap<>();
        env.put(JMXConnector.CREDENTIALS, credentials);

        try (JMXConnector connector =
                JMXConnectorFactory.connect(url, env)) {
            MBeanServerConnection server =
                    connector.getMBeanServerConnection();
            ObjectName bean = new ObjectName(
                    "training.jmx:type=DemoControl");
            Object current = server.getAttribute(
                    bean, "Limit");
            System.out.println("Limit=" + current);
        } finally {
            Arrays.fill(credentials, null);
        }
    }
}
~~~

Compile and run **once agent and client are compatibly configured**:

~~~bash
javac --release 21 JmxReadProbe.java
java JmxReadProbe localhost 7091 monitorRole
~~~

While the lab MBean is running, password/role are valid, TLS and RMI lookup succeed, and `Limit` is unchanged, the client prints:

~~~text
JMX password for monitorRole:
Limit=10
~~~

The first line is the **password prompt**; typed characters are not echoed. If an operator modified the MBean, `Limit` reflects the new value. If TLS handshake, registry lookup, or authorization fails, Java throws an exception rather than printing fixed success output.

**Explicit limitation of the sample client:** when the server enables **com.sun.management.jmxremote.registry.ssl=true**, an RMI/JNDI client may also need an **SSL socket factory** for the registry lookup. The code above **does not configure SSL-protected registry lookup or mTLS keystores/truststores itself**. Operators must use JMX/JConsole tools and configure clients to support registry TLS and proper certificates/trust; never disable `registry.ssl` just to make this sample connect. Verify library/client compatibility for your exact JDK.

**Password protection limitation:** the code clears the initial `char[]`, yet the **JMXConnector.CREDENTIALS** API uses **String[]**, and `String` passwords cannot be zeroed in memory like `char[]`. Production management tools must still manage secret lifecycles, protect process memory, and never log credentials.

## 11. Verifying TLS certificates and identity

Keystores and truststores are not merely two paths ending in **.p12**. Verify:

- **Server certificate** is trusted by the client and its **SAN** matches the DNS/IP used to connect.
- **Client certificate** is trusted by the server when mTLS is required; CA scope and client identity policies are managed.
- Certificates are neither expired nor revoked per policy, and use algorithms valid on JDK 21.
- Protocols and cipher suites are supported by both ends; never "fix" errors by disabling validation.
- Private keys are absent from Docker images, git, screenshots, and logs.
- Keystore/truststore passwords come from secret workflows, not hardcoded into startup commands readable by all users.

With JDK **keytool**, authorized operators can inspect certificates/aliases inside a keystore:

~~~bash
keytool -list -v -keystore /run/secrets/jmx-server.p12
~~~

The command may prompt for a password and prints certificate metadata. **Never share outputs containing sensitive details or private key material**, and never run it on environments where you lack authorization.

**Hostname verification:** if using **localhost** over a tunnel while the server certificate is issued for **jmx.internal.example**, design the endpoint/address and identity verification appropriately. Never disable hostname checking just to ignore a mismatch between advertised RMI host and certificate SAN.

## 12. Docker and Kubernetes: ports, PIDs, secrets, and network policies

### 12.1. Docker

Inside Linux Docker containers, the JVM's **container PID** can differ from its **host PID**. While `jcmd` needs the right PID for local attach, remote JMX relies on **host/port/JMX service URL**. The two models have distinct namespaces and permissions; never assume a JMX role limits shell commands inside the container.

Design carefully:

1. Publish **RMI registry + connector ports** intentionally, never exposing everything.
2. Ensure the JVM's **bind address** and **java.rmi.server.hostname** match the client's real route.
3. Map Docker **bind mounts/volumes** so keystore/truststore/access/password files land at the exact JVM paths.
4. Set secret file owner/mode to match Java's **effective UID/GID**, not just root shell access.
5. Restrict network/tunnel sources, match certificate hostnames, and keep secrets out of logs.

**Docker Desktop** runs Linux containers inside a Linux VM; an RMI stub cannot advertise a VM-internal address and expect external hosts to reach it. Never work around this by removing TLS or disabling authentication.

### 12.2. Kubernetes

In Kubernetes, remote JMX must not be exposed as a generic internet-facing **LoadBalancer/Ingress**. A sound control model:

- Restrict via **NetworkPolicy** solely from monitoring/bastion sources as needed.
- Use **Secrets** and volume mounts to deliver certs/keystores/passwords with tight permissions; audit Pod Security, service accounts, and RBAC for reading secrets.
- Define both registry and connector ports; align **Pod IP, Service DNS, RMI stub hostname**, and certificate SANs.
- **kubectl port-forward** can provide an admin tunnel, though it does not supply TLS/auth or handle all RMI stubs/second ports automatically.
- When only CPU/heap observation is needed, prefer a **read-only metrics exporter** instead of handing raw JMX control endpoints to every dashboard.
- Restrict who holds **kubectl exec** or node access, since they may reach local attach or read mounted secret files.

**Kubernetes RBAC** governs the Kubernetes API, not remote JMX `getAttribute`/`setAttribute`. **jmxremote.access** governs remote JMX roles, not users able to `exec` as the Pod's OS user. The two permission systems do not replace one another.

### 12.3. Failing even when one port is port-forwarded

RMI can let a client look up the registry and then fail attempting to reach the hostname and connector port returned in the stub. Forwarding only **7091** when the connector uses **7092**—or when the stub advertises a Pod IP unroutable from a laptop—causes connection failure. Check **both ports**, stub hostname, DNS, firewalls, and certificates; do not assume the password is wrong.

## 13. Distinguishing failure types when remote JMX breaks

| Symptom | Likely cause | Proper check |
| --- | --- | --- |
| **Connection refused** to registry | Agent not listening, wrong bind, wrong port, firewall. | JVM startup config, listening sockets, network. |
| Registry reachable yet connector times out | Wrong RMI stub hostname/connector port, NAT/network policy. | `java.rmi.server.hostname`, `jmxremote.rmi.port`, routing. |
| **SSLHandshakeException** | Untrusted CA, wrong SAN/expired cert, cipher/protocol mismatch, missing client cert. | Server/client truststores, TLS properties, PKI. |
| **Authentication failed** | Password, identity, JAAS, password file, role entry. | File permissions, principal mapping, login logs (without secrets). |
| Read works yet **setAttribute** rejected | `readonly` role or non-writable attribute. | `MBeanInfo` and remote test on lab MBean. |
| **invoke** rejected for `monitorRole` | Authorization properly blocking side-effecting calls. | Confirm client traverses the remote connector. |
| Local JConsole works while remote fails | Local Attach bypasses remote file checks; remote TLS/auth differs. | Verify exact connection, port, and identity. |
| Connector TLS active yet registry SSL off | Registry is a separate hop, unencrypted by default. | `registry.ssl`, client cert, and policy. |
| Role declared yet privileges remain broad | `authenticate=false`, custom connector skipping forwarder, local path. | Real endpoint, effective properties, policy. |
| Java process fails startup with agent on | Invalid password/access file permissions or syntax, bind failure, cert error. | Startup stderr/config, owner/mode, port conflicts. |
| JMX worked before deploy, broke after restart | New JVM, different secret/mount/port/hostname. | Full Java version, Pod UID, config, and cert rotation. |

**Never "fix" connection issues by turning off authentication/TLS.** Identify the first failing stage and inspect layer by layer: route → TLS → identity → role → operation.

## 14. Management channels require secret and session lifecycles

A setup that is secure today can drift out of compliance when operators change teams, certificates expire, or workloads move environments. Enforce:

- **Separate monitoring and control accounts**, rotate passwords/certificates periodically, and revoke unneeded access.
- **Enforce file permissions** and keep secrets out of images, git, process arguments, crash dumps, and CI logs.
- **Track certificate expiry/trust chains** and JDK/cipher compatibility ahead of upgrades.
- **Verify agent reload behavior**; never assume editing a secret file on disk updates running JVMs/sessions immediately.
- **Control established sessions:** an already-authenticated session may remain open after policy/secret changes; verify disconnect, timeout, or connector restart behavior.
- **Audit operator actions**, especially configuration mutations or pause-inducing operations.
- **Decommission temporary endpoints** once a debug window ends instead of leaving `readwrite` ports open indefinitely.

Even a `readonly` dashboard can view sensitive details. Practice **data minimization** in MBeans; never expose private keys, passwords, or secrets as getters just because "monitors are read-only."

## 15. Outside-in authorization verification runbook

**Step 1 — Identify the target.** Record full JDK version, VM vendor, host/node, Pod/container UID, process start time, and connector URL. Avoid confusing local and remote connectors.

**Step 2 — Capture configuration.** Inspect effective startup flags/management properties—remote port, RMI port, bind host, `auth=true`, TLS, `registry.ssl`, access roles; **never print password contents or private keys**.

**Step 3 — Verify network boundaries.** Prove unauthorized clients **cannot route** to either registry or connector. Confirm DNS/stub hostnames resolve from legitimate client locations.

**Step 4 — Verify TLS.** Connections with untrusted CAs or invalid client certs must fail. Verify hostname SAN, certificate chain, expiry, and mTLS/registry SSL if enabled.

**Step 5 — Verify authentication.** Wrong passwords or unknown principals must fail session setup. Keep passwords out of test logs.

**Step 6 — Verify readonly.** Against the lab's **training.jmx:type=DemoControl**, `monitorRole` reads **Limit**; **setting Limit** and **invoking Reset** must be rejected.

**Step 7 — Verify readwrite.** In the lab only, `controlRole` can update **Limit** and invoke `Reset` per policy; keep this strictly in test environments.

**Step 8 — Separate local checks.** Other OS users are restricted from attach as designed; never use local tests to infer remote RBAC.

**Step 9 — Cleanup.** Close sessions, shut down any temporary debug ports, rotate/revoke test credentials, and archive notes with zero secrets.

| Test | Expected result |
| --- | --- |
| Client from disallowed network | Cannot reach endpoint. |
| Server certificate untrusted by client | TLS handshake/identity verification fails. |
| Missing client certificate when mTLS required | TLS authentication fails. |
| Wrong user/password | JMX authentication fails. |
| `monitorRole` reads `Limit` | Succeeds over a valid connection. |
| `monitorRole` sets `Limit` | Rejected due to `readonly`. |
| `monitorRole` invokes `Reset` | Rejected due to `readonly`. |
| `controlRole` sets `Limit` in lab | Permitted if MBean and policy allow. |
| Local attach by unauthorized user | Blocked by OS/Attach policy. |

## 16. Mistakes to avoid

1. **"We have TLS, so we don't need authorization."** TLS does not authorize `get`/`set`/`invoke`.
2. **"Having a password means traffic is encrypted."** Authentication and encryption are distinct.
3. **"`authenticate=false` only skips login; the access file still enforces readonly."** With the ready-to-use agent, role files are bypassed.
4. **"`readwrite` only allows editing one business MBean."** Coarse-grained roles grant broader scope.
5. **"`readonly` contains no sensitive data."** MBean getters can expose configs and metadata.
6. **"Local JConsole tests the remote access file."** Local Attach is a completely separate path.
7. **"`ssl=true` means `registry.ssl=true`."** The registry is a separate endpoint, unencrypted by default.
8. **"Only `jmxremote.port` needs to be opened."** The connector port and stub hostname must also be routable.
9. **"`127.0.0.1` always works for remote JMX."** Loopback behavior depends on client/host/container placement.
10. **"Put passwords in `-D` flags for convenience."** Secrets leak across process lists and logs.
11. **"A Docker private network is enough."** Other workloads or leaked credentials remain risks.
12. **"Kubernetes Secrets create JMX RBAC."** Secrets only deliver files/values, not MBean policies.
13. **"Port-forwarding equals TLS."** Tunnels/reachability do not replace mTLS/auth/JMX authorization.
14. **"Legacy Security Manager is required to secure JMX."** Do not rely on deprecated Security Manager as sole defense; use supported connector/authorization controls.
15. **"Editing the access file immediately terminates old sessions."** Verify session lifecycles and explicit revocation.
16. **"Read-only users can invoke non-mutating operations."** A `readonly` policy can reject `invoke` even on benign-looking operations.
17. **"Every client needs readwrite just to take thread dumps."** Choose exact methods and permissions; never over-grant out of habit.
18. **"TLS handshake fails—just turn off SSL."** Check truststores, SANs, ciphers, registry socket factories, and routing.
19. **"Reaching the registry guarantees reaching the JVM."** The RMI stub may point to a different connector host/port.
20. **"JMX TLS also secures `jcmd` inside containers."** Local attach/OS permissions are a separate boundary.

## 17. Self-check

**Question 1.** The server has valid TLS; a monitoring client logs in as **monitorRole readonly**. Can it invoke the lab's **Reset**?

**Answer:** No, not through a remote connector enforcing `readonly`. TLS secures transport/peers without granting operation permissions.

**Question 2.** The access file lists `monitorRole readonly`, yet the JVM runs with **authenticate=false**. Is the policy still active?

**Answer:** You cannot rely on it. The ready-to-use agent ignores password/access files when authentication is disabled.

**Question 3.** Connector SSL is enabled, while registry SSL is left at default. What is the risk?

**Answer:** The RMI registry remains unencrypted by default on JDK 21; secure it with **registry.ssl** and configure client certs/auth per docs.

**Question 4.** Why is a remote monitor blocked from writing while local JConsole under the same OS user succeeds?

**Answer:** The local connector uses OS/Attach permissions and does not apply the remote agent's password/access files.

**Question 5.** Registry port 7091 is reachable, yet connector port 7092 times out. Does that prove the password is wrong?

**Answer:** No. Check stub hostname, connector port, firewalls, DNS, TLS handshake, and certificates.

**Question 6.** The JMX port is exposed only inside a Kubernetes cluster. Is that secure enough?

**Answer:** No. You still need network restrictions, TLS, authentication, JMX authorization, secret management, and Kubernetes RBAC.

**Question 7.** Why should a metrics collector avoid using `controlRole readwrite`?

**Answer:** It normally only reads attributes; `readwrite` enables unrelated management operations, creating excessive privilege risk.

**Question 8.** A client certificate was revoked, yet an established JMX session remains open. Is that possible?

**Answer:** Yes. Verify connector behavior, TLS session handling, and disconnect/restart/rotation mechanisms rather than assuming revocation drops live sessions instantly.

**Question 9.** A `readwrite` test plan calls `MemoryMXBean` to trigger GC in production. Should you proceed?

**Answer:** No; that causes real side effects. Use a test MBean with minimal impact and explicit rollback.

**Question 10.** A `readonly` MBean exposes system properties containing secrets. Is it safe?

**Answer:** No. `readonly` can still leak sensitive data; minimize exposed MBean data, redact values, and restrict readers.

## 18. JDK 21 production deployment checklist

- [ ] Identified exact JDK vendor/VM and JMX connector type.
- [ ] Separated local Attach from remote JMX; locked down OS/Pod local attach access.
- [ ] Registry/connector reachable only from approved networks, never public.
- [ ] **jmxremote.port** and **jmxremote.rmi.port** set properly, with a routable stub hostname.
- [ ] **authenticate=true** with secured identity store/JAAS.
- [ ] Monitoring uses **readonly**; `readwrite` operators require approval.
- [ ] Audited **create/unregister** and sensitive operations.
- [ ] TLS enabled; clients validate certificate chains, hostnames, expiry, and protocols.
- [ ] If using mTLS, server validates client certs; if `registry.ssl=true`, clients support TLS registry lookup.
- [ ] Secret/password/access/keystore/truststore files have strict owner/mode and lifecycle management.
- [ ] Tested positive and negative cases: wrong password/cert, `readonly` get vs. set/invoke.
- [ ] Verified Docker/Kubernetes networking, Secret mounts, RBAC, and port-forward behavior.
- [ ] Auditing, credential rotation, session revocation, and endpoint shutdown plans are in place.
- [ ] Avoided opening raw remote JMX solely for metrics when a suitable read-only exporter/gateway exists.

## References

- [JDK 21 — Monitoring and Management Using JMX Technology](https://docs.oracle.com/en/java/javase/21/management/monitoring-and-management-using-jmx-technology.html): ready-to-use JMX agent, file auth, TLS/registry SSL, remote properties.
- [Java SE 21 JMX Guide — Security](https://docs.oracle.com/en/java/javase/21/jmx/security.html): JMXAuthenticator, MBeanServerForwarder, simple and fine-grained security.
- [Java SE 21 — JMXConnectorFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnectorFactory.html): creating client connectors.
- [Java SE 21 — JMXConnector](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnector.html): credentials and lifecycle.
- [Java SE 21 — JMXServiceURL](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXServiceURL.html): JMX service URL.
- [Java SE 21 — StandardMBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/StandardMBean.html): test MBean.
- [Java SE 21 — MBeanServerConnection](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html): `getAttribute`, `setAttribute`, `invoke`.
- [Java SE 21 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): TLS/keystores/truststores.
- [Java SE 21 — keytool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html): certificates and keystores.
- [OpenJDK JEP 411 — Security Manager deprecation](https://openjdk.org/jeps/411): limitations of the legacy Security Manager model.

**Core principle:** with JMX, **read-only does not mean public**, **TLS does not grant control permissions**, and **authentication does not guarantee role files apply across every connector**. Always verify **network, TLS, identity, authorization, local attach, and secret/session lifecycles** together on the exact target JVM.