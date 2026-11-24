# 7.5 — Remote connections via JMX connector, RMI registry, and port configuration

## 1. Objectives and core problem

When a Java 17 application runs on another host, JConsole, JDK Mission Control, or a Java program on an operator workstation can read **platform MXBeans** and application MBeans through the **JMX Remote API**. With HotSpot's ready-to-use management agent, JMX typically uses the **RMI connector**.

Common failure cause: a JMX/RMI session takes **two TCP hops**. The client first locates the RMI connector in the **RMI registry**, then uses the returned **remote stub** to reach the actual connector port. Opening only the registry port allows lookup to succeed while every subsequent JMX call times out.

After this lesson, you will be able to:

1. Explain the roles of `MBeanServer`, JMX connector server, RMI registry, `RMIServer` stub, and client.
2. Distinguish `jmxremote.port`, `jmxremote.rmi.port`, bind interface, and advertised hostname.
3. Read a `JMXServiceURL` and identify which port is the registry and which is the connector.
4. Run a **two-Java-process** demo over RMI/JMX reading both a custom MXBean and the platform `RuntimeMXBean`.
5. Diagnose DNS, firewall, NAT/container, SSL, authentication, and authorization issues.
6. Maintain security principles when exposing a remote management endpoint.

> **Warning:** Remote JMX is a **JVM administration surface**, not merely a metrics endpoint. The `authenticate=false` and `ssl=false` demo below **must only be run on an isolated test machine bound to 127.0.0.1**. Never copy that configuration to any server whose ports are reachable from untrusted networks.

## 2. Connection flow through RMI registry and JMX connector

```text
JMX client / JConsole / JMC
        |
        | (1) RMI lookup for "jmxrmi" at HOST:9010
        v
Management agent's RMI registry
        |
        | returns RMIServer remote stub
        v
Client extracts advertised HOST:PORT from stub
        |
        | (2) RMI call to HOST:9011 (example)
        v
JMX RMI connector server inside target JVM
        |
        | forwards MBeanServerConnection requests
        v
Platform MBeanServer
        +-- java.lang:type=Runtime
        +-- java.lang:type=Memory
        +-- demo:type=Status
```

| Component | Role | Is not |
| --- | --- | --- |
| **Platform MBeanServer** | Manages MBeans, attributes, and operations by `ObjectName` | An RMI registry over TCP |
| **JMX connector server** | Exposes the management interface over the RMI network transport | A Web/REST server |
| **RMI registry** | Looks up binding `jmxrmi` to obtain the stub | Where MBean `getAttribute` executes |
| **RMIServer stub** | Remote reference to the connector object containing the endpoint to contact | Proof of authentication |
| **JMXConnector client** | Opens a session, obtains `MBeanServerConnection`, calls APIs, and closes resources | The monitored JVM itself |

**Hop 1:** The client contacts `HOST:9010` and asks for the name `jmxrmi`. The ready-to-use management agent creates a dedicated registry and registers that binding.

**Hop 2:** The RMI registry returns the stub. The client reads the address and port embedded in the remote reference to call the connector. The connector creates an `RMIConnection` session and serves `MBeanServerConnection` operations.

The phrase "private read-only RMI registry" refers only to permissions for modifying registry bindings—it says **nothing** about which MBeans a client can read or write. JMX permissions are controlled by the management agent's authentication and authorization.

## 3. Port and address map

| Property / concept | Example | Meaning |
| --- | --- | --- |
| `-Dcom.sun.management.jmxremote.port=9010` | 9010 | Enables the remote agent and RMI registry for remote JMX |
| `-Dcom.sun.management.jmxremote.rmi.port=9011` | 9011 | Pins the RMI connector port so firewalls know it in advance |
| `-Djava.rmi.server.hostname=HOST` | `jvm-node.internal.example` | Host/IP **embedded into the RMI stub** for the client's second hop |
| `-Dcom.sun.management.jmxremote.host=IP` | `127.0.0.1` in demo | Interface the remote JMX agent binds on HotSpot |
| `com.sun.management.jmxremote.local.port` | Unused in demo | A separate port for the local management connector |
| Registry binding | `jmxrmi` | Name looked up inside the registry |

Ports `9010` and `9011` are **illustrative numbers**; pick free ports on your system. With typical firewalls, inspect both traffic flows, not just port `9010`.

Omitting `jmxremote.rmi.port` lets the RMI connector export on a **dynamic port**. Registry lookup succeeding while the connector port is blocked by a firewall is a very common failure mode.

**Advertised host differs from bind address:**

- `java.rmi.server.hostname` controls the address written into the stub; it **does not open a new listening socket itself**.
- `com.sun.management.jmxremote.host` specifies the interface the remote agent listens on in HotSpot.
- The host inside `JMXServiceURL` is where the **registry lookup** happens.
- Both registry host/port and stub host/port must be **routable from the client**.

A stub advertising `127.0.0.1:9011` works for a client on the same host as the JVM; a client on another laptop will try connecting to **the laptop itself**, not the server.

## 4. Reading a JMXServiceURL accurately

For the ready-to-use management agent, the standard URL is:

```text
service:jmx:rmi:///jndi/rmi://HOST:REGISTRY_PORT/jmxrmi
```

Example in this lab:

```text
service:jmx:rmi:///jndi/rmi://127.0.0.1:9010/jmxrmi
```

Explanation:

- `service:jmx:`: JMX connector address prefix.
- First `rmi:`: connector protocol is RMI.
- `/jndi/rmi://...`: uses JNDI lookup against an RMI registry.
- `127.0.0.1:9010`: **registry endpoint**, not necessarily the port used for RMI calls.
- `/jmxrmi`: binding name registered by the ready-to-use agent.

**Why isn't `9011` written in the URL?** With the URL form above, the client receives the actual connector endpoint from the stub. Custom JMX connectors may use `service:jmx:rmi://HOST:CONNECTOR_PORT/jndi/rmi://HOST:REGISTRY_PORT/jmxrmi`; do not assume every connector type requires the same URL format.

### 4.1. Do you need to start `rmiregistry` manually?

**No**, not for the built-in management agent. When the JVM starts with `-Dcom.sun.management.jmxremote.port=9010`, the agent creates the required registry and binding. Starting a separate `rmiregistry` on the same port can prevent the JVM from starting with `Address already in use`. Only custom connector architectures manage their own registry per application design.

### 4.2. Difference between local JMX and remote JMX

Local JMX via the Attach API discovers JVMs by PID and uses local connectors/IPC and OS permissions. Remote JMX over RMI uses a registry URL, remote stub, network interfaces, and security settings. `jcmd` on a laptop cannot attach directly to a PID on a remote server. This lesson focuses on the **remote connector**, not enabling the local management agent.

## 5. Java 17 lab: RMI/JMX connection with two distinct ports

To verify the protocol while avoiding exposing an admin port to the network, the demo binds strictly to **loopback 127.0.0.1**. Two programs run in **two separate Java processes**: the target exports an MXBean, and the client reads it via the RMI registry and connector.

**Disabling authentication/TLS is unsafe** outside an isolated learning machine. Never use it on public IPs, production servers, or untrusted multi-user environments.

### 5.1. Create RemoteJmxTarget.java

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class RemoteJmxTarget {
    public interface StatusMXBean {
        String getMessage();
    }

    public static class Status implements StatusMXBean {
        @Override
        public String getMessage() {
            return "hello-over-jmx";
        }
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        server.registerMBean(new Status(), new ObjectName("demo:type=Status"));
        System.out.println("TARGET_READY");
        Thread.sleep(60_000);
    }
}
```

Class `Status` implements `StatusMXBean`, exposing the `Message` attribute. `registerMBean` registers it under ObjectName `demo:type=Status` on the target JVM's **platform MBeanServer**. `Thread.sleep(60_000)` keeps the program alive long enough for a second terminal to connect.

The remote agent can spawn its own threads; once `main` finishes sleeping, do not assume the JVM will necessarily exit immediately. When finishing the exercise, stop **the exact demo process** cleanly via Ctrl+C or an authorized OS tool.

### 5.2. Create RemoteJmxClient.java

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class RemoteJmxClient {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("registry port required");
        }

        String urlText =
            "service:jmx:rmi:///jndi/rmi://127.0.0.1:" + args[0] + "/jmxrmi";
        JMXServiceURL url = new JMXServiceURL(urlText);

        try (JMXConnector connector = JMXConnectorFactory.connect(url)) {
            MBeanServerConnection remote = connector.getMBeanServerConnection();

            String message = (String) remote.getAttribute(
                new ObjectName("demo:type=Status"), "Message");
            long uptime = (Long) remote.getAttribute(
                new ObjectName(ManagementFactory.RUNTIME_MXBEAN_NAME), "Uptime");

            System.out.println("message=" + message);
            System.out.println("uptimeNonNegative=" + (uptime >= 0));
        }
    }
}
```

The client has no reference to `Status`'s concrete Java class; it only uses the MBean `ObjectName` and attribute. `RuntimeMXBean.Uptime` is dynamic, so the program prints a boolean check for deterministic stdout. `try-with-resources` closes `JMXConnector` even on errors.

### 5.3. Compile

Place both files in the same directory and use JDK 17+:

```bash
javac --release 17 RemoteJmxTarget.java RemoteJmxClient.java
```

The JMX API resides in standard Java management modules, needing no external libraries. These two files have been compiled and tested successfully on OpenJDK.

### 5.4. Start the target in the first terminal

On bash (Linux/macOS/Git Bash), using **two free ports**:

```bash
java \
  -Dcom.sun.management.jmxremote.port=9010 \
  -Dcom.sun.management.jmxremote.rmi.port=9011 \
  -Dcom.sun.management.jmxremote.host=127.0.0.1 \
  -Djava.rmi.server.hostname=127.0.0.1 \
  -Dcom.sun.management.jmxremote.authenticate=false \
  -Dcom.sun.management.jmxremote.ssl=false \
  RemoteJmxTarget
```

On Windows PowerShell, pass the options **on one line**:

```powershell
java -Dcom.sun.management.jmxremote.port=9010 -Dcom.sun.management.jmxremote.rmi.port=9011 -Dcom.sun.management.jmxremote.host=127.0.0.1 -Djava.rmi.server.hostname=127.0.0.1 -Dcom.sun.management.jmxremote.authenticate=false -Dcom.sun.management.jmxremote.ssl=false RemoteJmxTarget
```

**Fixed stdout when the target starts successfully:**

```text
TARGET_READY
```

If a port is in use, a config file is invalid, or the agent fails to bind, the JVM may report errors before this line; inspect stderr and never assume the process is ready.

### 5.5. Connect from the second terminal

While the target has printed `TARGET_READY` and is still running:

```bash
java RemoteJmxClient 9010
```

**Exact demo stdout:**

```text
message=hello-over-jmx
uptimeNonNegative=true
```

Both outputs have been verified with a target JVM and test client using a **registry port distinct from the RMI connector port**. Actual ports during testing may differ from `9010` and `9011`; the Java program's output does not depend on specific port numbers.

`message=hello-over-jmx` proves a `getAttribute` call reached the **target JVM's MBeanServer** and returned data. Running both processes on the same machine for testing **does not mean** the client used the Attach API: the transport is still a remote JMX connector over RMI.

### 5.6. Verify and clean up

On Linux:

```bash
ss -ltn
```

On Windows:

```powershell
Test-NetConnection 127.0.0.1 -Port 9010
Test-NetConnection 127.0.0.1 -Port 9011
```

These are only TCP listener/reachability checks; they do not prove SSL, authentication, or MBean calls succeeded. Stop the target after testing; never leave unauthenticated JMX running long-term on a shared machine.

## 6. From JMXConnector to MBeanServerConnection

In the client, `JMXConnectorFactory.connect(url)` creates the connector; `getMBeanServerConnection()` provides remote JMX operations:

| API | Role | Notes |
| --- | --- | --- |
| `queryNames(...)` | Finds MBeans matching an ObjectName pattern | List can change at runtime |
| `getMBeanInfo(...)` | Inspects attribute/operation metadata | Does not prove caller can invoke all of them |
| `getAttribute(...)` | Reads a single attribute | Can fail due to ObjectName/attribute/permissions |
| `getAttributes(...)` | Reads multiple attributes | Does not guarantee an atomic snapshot |
| `addNotificationListener(...)` | Subscribes to notifications | Needs unsubscribe/reconnect handling |
| `invoke(...)` | Invokes an MBean operation | **Can mutate JVM/application state** |

The `readonly` role suits monitoring. Never grant `readwrite` just so a dashboard can read JVM memory or thread metrics.

### 6.1. Client-side credential configuration

When the agent enables authentication, the JMX client passes credentials through the environment map:

```java
// Illustrative snippet, not a standalone program.
String user = System.getenv("JMX_USER");
String password = System.getenv("JMX_PASSWORD");

java.util.Map<String, ?> env = java.util.Map.of(
    JMXConnector.CREDENTIALS, new String[] { user, password });

try (JMXConnector connector = JMXConnectorFactory.connect(url, env)) {
    // Read MBeans authorized for the role.
}
```

Never hardcode passwords or put credentials in the URL. `JMX_USER`/`JMX_PASSWORD` are example variable names, not JDK-mandated properties. With TLS/mutual TLS or `registry.ssl=true`, the client also needs appropriate truststores, certificates, and socket-factory settings; a credentials map **does not complete TLS configuration on its own**.

## 7. Firewalls, DNS, NAT, and containers

Separate two distinct questions:

1. **Can the client reach the registry?** Connects to `HOST:9010` and looks up `jmxrmi`.
2. **Can the client reach the connector inside the stub?** Connects to the advertised `HOST:9011`, performs the handshake, and executes MBean calls.

Failure example when the stub hostname is wrong:

```text
client -> jvm-node:9010         SUCCESS: registry lookup
registry -> stub 127.0.0.1:9011 SUCCESS
client -> 127.0.0.1:9011       FAILED: points back to client, not jvm-node
```

Failure example when a dynamic connector port is blocked by a firewall:

```text
client -> jvm-node:9010         SUCCESS
registry -> stub jvm-node:random-port
client -> random-port           TIMEOUT
```

**Do not "fix" this by changing the URL from `9010` to `9011`**: the port inside `/jndi/rmi://...` is still used for the registry lookup.

Inside Docker/Kubernetes, a JVM may advertise a podIP/containerIP unroutable from outside clients. Port-forwarding only the registry port misses the connector port. A load balancer routing the registry lookup to JVM A and the connector call to JVM B also breaks the session. Both hops must hit the exact same JVM instance, and both the advertised host and port must be routable from the client.

`java.rmi.server.hostname` must match actual routing, though it creates no new listener. `com.sun.management.jmxremote.host` controls the bind interface; changing it alone will not fix a wrong endpoint embedded in the stub. Through tunnels/bastions, design both hops and security properly; never disable TLS/auth to cross NAT.

## 8. Securing remote JMX in production

Oracle Java 17 documentation recommends authentication, authorization, and TLS/SSL whenever exposing remote management. `jmxremote.authenticate` and `jmxremote.ssl` are typically enabled by default when the remote agent is configured, whereas `jmxremote.registry.ssl` **defaults to false**.

| Layer | Configuration / control | Purpose |
| --- | --- | --- |
| Network | VPN, firewall, Security Group, NetworkPolicy | Restricts which hosts can connect |
| Authentication | Password/JAAS/client certificates | Verifies identity |
| Authorization | Access file / `readonly` or `readwrite` roles | Restricts MBean operations |
| Connector TLS | `jmxremote.ssl=true` | Protects the RMI connector |
| Registry TLS | `jmxremote.registry.ssl=true` | Protects the stub lookup channel |
| Mutual TLS | `jmxremote.ssl.need.client.auth=true` | Authenticates client certificates |
| Secrets | Keystore, truststore, rotation, file permissions | Prevents credential/certificate leaks |

**Connector TLS does not automatically protect the registry.** An unencrypted registry can be spoofed in certain threat models, tricking clients into receiving untrusted stubs and sending credentials to the wrong party. For strong security, enable registry TLS and mutual TLS per JDK docs and verify client compatibility.

The ready-to-use agent's password file stores passwords in **clear text**; strict file permissions are required, and Oracle docs recommend stronger mechanisms for production. Never leave secrets in command lines, logs, or repos; follow your organization's secret management policy.

**Never run production with:**

```text
-Dcom.sun.management.jmxremote.authenticate=false
-Dcom.sun.management.jmxremote.ssl=false
```

On any network-reachable endpoint, this configuration lets arbitrary clients read data or control the application via MBean operations. Even a read-only role can expose configuration, threads/heap, and system properties. Every JMX access path must be restricted and audited.

The agent can also cause the JVM to **fail startup** if a port is already bound or password/access files are invalid or mispermissioned. When enabling JMX in deployments, verify startup logs, readiness, and listeners—not just the presence of flags in config.

## 9. Hop-by-hop diagnosis instead of guessing ports

| Symptom | Possible causes | How to check |
| --- | --- | --- |
| JVM exits before READY | Port conflict, broken password/access file, wrong file permissions | Startup stderr/logs and listeners |
| Connection refused at registry | Wrong IP/registry port, agent disabled, bound to different interface | `jmxremote.port`, process, route |
| Registry port open yet JMX times out | Dynamic/blocked connector port, wrong stub advertised host | `jmxremote.rmi.port`, `java.rmi.server.hostname` |
| `NameNotFoundException: jmxrmi` | Registry lacks binding or connected to wrong process | URL `/jmxrmi`, JVM identity |
| `UnknownHostException` | Invalid DNS name in registry or stub | Resolve **from the client machine** |
| RMI tries connecting to `127.0.0.1` from laptop | Stub contains server loopback | Set advertised host matching network |
| SSL handshake failure | Certificate/hostname/truststore/mTLS mismatch | Check cert chain and registry/connector TLS |
| `SecurityException` | Wrong credentials or access role | Authentication/authorization, never log secrets |
| Connects yet `getAttribute` fails | Wrong ObjectName/attribute, bean vanished, or missing permission | `queryNames`, `getMBeanInfo`, role |
| Intermittent after deploy | Pod restart, LB switches JVM instance | Correlate registry–stub–process identity |
| Fails only over port-forward | Stub returns unroutable container/pod IP | Handle both hops, not just registry |

**Troubleshooting sequence:** (1) confirm exact target JVM, (2) confirm agent started, (3) identify registry port and connector port, (4) verify DNS/routing/firewall from client, (5) inspect stub advertised endpoint, (6) verify TLS/auth, (7) perform a non-destructive `getAttribute`, (8) close the connector and log timestamps/errors.

`ss`/`Test-NetConnection` are only TCP tests and do not validate the JMX handshake. When one JMX operation succeeds and another fails, check MBean permissions/contracts or JVM pauses instead of blaming firewalls for everything.

## 10. Common mistakes

| Misconception | Accurate understanding |
| --- | --- |
| "Remote JMX uses only one port." | Registry and connector can use two ports. |
| "The port in the URL handles every JMX call." | That is the registry port; the stub can advertise another port. |
| "`java.rmi.server.hostname` binds the socket." | It sets the advertised host inside the RMI reference. |
| "Opening the registry port means the endpoint works." | Hop two and MBean operations can still fail. |
| "Forwarding only 9010 in Kubernetes is enough." | You also need a path for connector 9011 and the stub. |
| "You must run `rmiregistry` separately." | The ready-to-use agent creates its own registry/binding. |
| "Read-only registry means read-only JMX role." | Those are two completely separate permission layers. |
| "Connector SSL automatically protects the registry." | `registry.ssl` is a separate setting. |
| "Disabling authentication only affects metrics." | JMX exposes management operations. |
| "`service:jmx:...` is an HTTP URL." | It is a JMX/RMI service URL. |
| "Attach API and remote connector are the same." | They differ in protocol, discovery, security, and scope. |
| "Clients don't need to close connectors." | Call `close()` to release resources. |

## 11. When is a custom JMXConnectorServer needed?

The demo uses the built-in management agent; **there is no need** to call `LocateRegistry.createRegistry(...)` or `JMXConnectorServerFactory` inside an application. If special architectural requirements demand it, a custom connector can be built via API:

```java
// Conceptual snippet, not a complete program.
javax.management.remote.JMXConnectorServer connector =
    javax.management.remote.JMXConnectorServerFactory.newJMXConnectorServer(
        serviceURL, environment, ManagementFactory.getPlatformMBeanServer());
connector.start();
```

A custom connector must handle its own registry, exported ports, SSL socket factories, authentication, lifecycle, and cleanup. Do not build one merely out of misunderstanding `jmxremote.rmi.port`; in JDK 17, that property already pins the connector port for the ready-to-use agent. Use custom solutions only when security/network requirements genuinely require them and have been thoroughly tested.

## 12. Real-world scenarios

**A. JConsole works on the server, fails from a laptop.** Check whether the RMI stub contains `127.0.0.1` or an internal hostname unreachable from the laptop. Configure advertised host, bind interface, and security properly; changing only the registry URL will not fix a bad stub.

**B. After adding a firewall, registry stays open yet JMX times out.** Hop one works; the connector is likely using a dynamic port. Configure `jmxremote.rmi.port` and allow both TCP flows instead of opening wide random port ranges.

**C. Kubernetes pod is port-forwarded yet client fails.** Registry over the tunnel works, but the stub advertises `podIP:connectorPort`. Design routing for both hops or run the client inside an admin network with proper reachability.

**D. SSL is enabled, yet registry spoofing remains possible.** `jmxremote.ssl` and `jmxremote.registry.ssl` are independent. Review registry TLS, client certs/trust, and role access before declaring the config secure.

**E. Dashboard only needs heap/thread counts.** Prefer a read-only monitoring role and restricted admin network. Never open unauthenticated JMX or grant `readwrite` just to pull metrics.

## 13. Deployment checklist

- [ ] Verified target JVM/host/container/PID/start time; not hitting the wrong replica.
- [ ] Set `jmxremote.port` for registry and `jmxremote.rmi.port` for connector behind firewalls.
- [ ] Distinguished bind interface from the hostname/port advertised in the stub.
- [ ] Understood `service:jmx:rmi:///jndi/rmi://HOST:REGISTRY_PORT/jmxrmi`.
- [ ] Verified both hops; did not open only one TCP port.
- [ ] Avoided running `rmiregistry` on the management agent's port.
- [ ] Protected JMX with authentication, authorization, TLS, and network isolation.
- [ ] Evaluated registry TLS and mutual TLS in production security design.
- [ ] Never copied security-disabling flags from demos.
- [ ] Under NAT/containers/LBs, ensured registry and stub point to the exact **single JVM instance**.
- [ ] Tested one non-destructive JMX attribute read, then closed the connector.
- [ ] Logged required errors/timestamps/endpoints without logging passwords, tokens, or private keys.

## 14. Official Java SE 17 references

- [Oracle — Monitoring and Management Using JMX Technology](https://docs.oracle.com/en/java/javase/17/management/monitoring-and-management-using-jmx-technology.html): ready-to-use JMX agent, remote ports, `jmxrmi` registry, TLS/auth.
- [Oracle — javax.management.remote](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/remote/package-summary.html): JMXServiceURL, JMXConnector, MBeanServerConnection.
- [Oracle — javax.management.remote.rmi](https://docs.oracle.com/en/java/javase/17/docs/api/java.management.rmi/javax/management/remote/rmi/package-summary.html): RMI connector, stubs, JNDI lookup.
- [Oracle — JMXConnectorFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/remote/JMXConnectorFactory.html): JMX client factory API.
- [Oracle — RMI system properties](https://docs.oracle.com/en/java/javase/17/docs/specs/rmi/properties.html): `java.rmi.server.hostname`.
- [Oracle — JMX Security](https://docs.oracle.com/en/java/javase/17/jmx/security.html): authentication, authorization, SSL/TLS.

**Key takeaway:** a remote JMX/RMI connection executes **registry lookup → receive stub → call connector → query MBeanServer**. Registry port, connector port, bind interface, and advertised hostname must align with network routing. An open TCP port does not prove JMX works, and an unauthenticated/unencrypted connection is a severe administrative risk.