# Connecting to a Remote JVM with `jconsole`

`jconsole` is a graphical tool in the JDK for monitoring and managing a Java Virtual Machine (JVM) via Java Management Extensions (JMX). When connecting remotely, JConsole runs on the operator workstation and reads data from a JMX management agent running on the application host.

Basic connection command:

~~~text
jconsole app-server.example.internal:9010
~~~

On the target JVM, enable the remote management agent with the following system properties:

~~~text
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9011
~~~

These two ports serve the two parts of the RMI connection. The client connects to the registry on port `9010`, receives the RMI stub, and then connects to the RMI connector on port `9011`. Firewall rules and hostnames must be configured for both connection paths.

Remote JMX can read runtime information and invoke management operations through MBeans. Therefore, the connection requires authentication, authorization, and TLS. The JDK enables password authentication and SSL/TLS for remote management by default; for production, Oracle recommends authenticating clients with certificates and authorizing users with passwords or a login module.

The toolchain verified for this guide is Zulu/OpenJDK 24.0.2. The hands-on example uses Java 17+ and a JMX endpoint bound only to loopback.

## 1. JConsole, JMX, and remote management

JMX is Java's standard mechanism for exposing management data and operations through MBeans (Managed Beans). The JVM includes built-in platform MXBeans for components such as:

- Runtime: VM version, uptime, and arguments.
- Memory: heap, non-heap, and memory pools.
- Garbage Collector: collection counts and GC time.
- Threading: thread count, thread states, stack traces, and deadlock detection.
- Class Loading: counts of loaded and unloaded classes.
- Operating System: process and OS metrics depending on the runtime.

Applications can also register custom MBeans to expose their own metrics or management operations.

Remote connection flow:

~~~text
JConsole on operator workstation
             |
             | JMX over RMI
             v
      RMI Registry on target
             |
             | returns connector stub
             v
      RMI Connector on target
             |
             v
      MBeanServer in target JVM
             |
       +-----+------+
       |            |
       v            v
  Platform MBeans  Application MBeans
~~~

JConsole is a JMX client. It does not automatically enable remote management on a JVM running on another host. The target JVM must already have a remote JMX agent listening, or be configured to start the agent through an appropriate administrative workflow.

## 2. Local vs. remote connections

### Local connection

When you run:

~~~text
jconsole
~~~

JConsole lists the local Java processes that the current user has permission to attach to. Select a process and click Connect.

You can also specify a PID:

~~~text
jconsole 18240
~~~

Local connections use the Attach API and OS-level permissions. JConsole and the JVM typically must run under the same user. In modern Java, local monitoring can be enabled dynamically when JConsole attaches; passing `-Dcom.sun.management.jmxremote.port` at startup is not required.

### Remote connection

A remote connection requires:

1. The target JVM has the remote JMX agent enabled.
2. The client knows the hostname and registry port.
3. Both the registry port and the RMI connector port are reachable over the network.
4. The RMI stub advertises a hostname or IP address that the client can reach.
5. The client has the credentials and trust material required by the security configuration.

A remote connection does not depend on any process PID on the client machine. Do not enter the target machine's PID in place of the hostname and JMX port.

## 3. `jconsole` syntax

JDK 24 syntax:

~~~text
jconsole [-interval=n] [-notile] [-pluginpath path] [-version] [connection] [-Jinput_arguments]
~~~

`connection` can be:

| Form | Meaning |
|---|---|
| `pid` | PID of a local JVM; requires appropriate attach permissions |
| `host:port` | Hostname and `com.sun.management.jmxremote.port` on the target host |
| `jmxURL` | Full JMX service URL |

Commonly used options:

- `-interval=n`: chart update interval in seconds; defaults to 4 seconds.
- `-notile`: disables automatic window tiling when connected to multiple JVMs.
- `-pluginpath`: path to JConsole plugins.
- `-version`: prints the program version.
- `-help` or `--help`: displays help information.
- `-J...`: passes a JVM option to the JConsole process itself, such as a client-side truststore or keystore.

Example of a remote connection with a 10-second update interval:

~~~text
jconsole -interval=10 app-server.example.internal:9010
~~~

If no host and port are provided, JConsole opens the connection dialog where you can enter remote process details or a JMX service URL.

## 4. Configuring the remote JMX agent on the target JVM

The remote management agent is enabled at JVM startup via `com.sun.management.jmxremote.port`.

Example port configuration:

~~~text
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9011
~~~

Property roles:

- `com.sun.management.jmxremote.port`: the RMI Registry port that JConsole contacts first. The registry publishes the connector under the name `jmxrmi`.
- `com.sun.management.jmxremote.rmi.port`: fixed port for the RMI connector server.
- `com.sun.management.jmxremote.host`: IP interface on the target host that the JMX RMI agent binds to.
- `java.rmi.server.hostname`: hostname or IP address embedded in the RMI stub for the client to use on the follow-up connection.
- `com.sun.management.jmxremote.local.port`: local JMX connector port if you want to pin it explicitly.

If `com.sun.management.jmxremote.rmi.port` is not fixed, RMI may choose a dynamic port. In that case, a firewall that only opens the registry port will block the connector port; the client can reach the registry and still time out.

`jmxremote.host` and `java.rmi.server.hostname` serve different roles: one selects the bind interface on the server, while the other determines the address advertised in the stub. On hosts with multiple NICs, NAT, or a dedicated management subnet, configure both to match the network path the client actually uses.

## 5. Preparing the firewall and network

Example configuration:

~~~text
JMX registry:       TCP 9010
RMI connector:      TCP 9011
Server bind address: 10.20.30.40
Advertised host:    jmx-app-01.example.internal
Client command:     jconsole jmx-app-01.example.internal:9010
~~~

For the connection to succeed:

1. The hostname resolves to the target host's management interface.
2. TCP registry port `9010` is allowed from the operator workstation.
3. TCP connector port `9011` is allowed from the operator workstation.
4. The RMI stub advertises a hostname or IP address that the client can resolve and reach.
5. Firewalls, NAT, security groups, and network policies do not block either connection.
6. Neither port is already in use by another process.

Do not open only the registry port and assume JMX is ready. The RMI client must connect to the endpoint returned in the stub. If the stub contains a private or loopback address unreachable from the client, the connection will still fail.

In production, allow JMX access only from the management subnet or jump hosts. Never expose JMX ports to the public Internet.

## 6. Enabling remote JMX with startup options

Example startup command with two fixed ports and a management interface:

~~~text
java -Dcom.sun.management.jmxremote.port=9010 -Dcom.sun.management.jmxremote.rmi.port=9011 -Dcom.sun.management.jmxremote.host=10.20.30.40 -Djava.rmi.server.hostname=jmx-app-01.example.internal -jar application.jar
~~~

This covers the network configuration. Before deploying to production, you must add authentication, authorization, and TLS according to your security policy. Do not use this example alone as a release configuration without securing remote JMX.

System properties can also be placed in a `management.properties` file, with its path passed via:

~~~text
-Dcom.sun.management.config.file=/etc/myapp/management.properties
~~~

Properties passed directly on the command line override the corresponding values in the configuration file.

## 7. Authentication and access control

The remote JMX agent uses password authentication by default. There are two main files:

- `jmxremote.password`: maps roles/users to passwords.
- `jmxremote.access`: defines the permissions for each role.

Example password file:

~~~text
# Replace the sample values with your own strong passwords.
monitorRole <monitor-password>
controlRole <control-password>
~~~

Example access file:

~~~text
# Read-only access to metrics and MBean attributes.
monitorRole readonly

# Write access to attributes and permission to invoke operations.
controlRole readwrite
~~~

`readonly` allows reading MBean attributes and receiving notifications. `readwrite` allows writing attributes, invoking operations, and, depending on configuration, creating or unregistering MBeans. Grant `readwrite` only to operators who genuinely need administrative actions.

Specify custom files at startup:

~~~text
-Dcom.sun.management.jmxremote.authenticate=true
-Dcom.sun.management.jmxremote.password.file=/etc/myapp/jmxremote.password
-Dcom.sun.management.jmxremote.access.file=/etc/myapp/jmxremote.access
~~~

The default mechanism's password file stores passwords in clear text. On Linux/macOS, restrict permissions:

~~~sh
chmod 600 /etc/myapp/jmxremote.password
~~~

On Windows, use NTFS ACLs so that only the account running the JVM can read the file. If the file has broader read permissions, the JMX agent may refuse to start. Do not reuse everyday personal login accounts as JMX roles; create dedicated credentials with separate permissions.

Do not set `com.sun.management.jmxremote.authenticate=false` in production. When authentication is disabled, any user who can reach the endpoint is granted full management access, and the password/access files are ignored.

## 8. TLS and securing the RMI Registry

When remote JMX is enabled, SSL/TLS is enabled by default, but the JVM needs an appropriate certificate configuration. The server needs a keystore containing its private key and certificate. The client needs a truststore that trusts the server certificate.

Commonly used system properties:

| Property | Purpose |
|---|---|
| `javax.net.ssl.keyStore` | Path to the JVM keystore |
| `javax.net.ssl.keyStoreType` | Keystore type, e.g., `PKCS12` |
| `javax.net.ssl.keyStorePassword` | Password to open the keystore |
| `javax.net.ssl.trustStore` | Path to the truststore |
| `javax.net.ssl.trustStoreType` | Truststore type |
| `javax.net.ssl.trustStorePassword` | Password to open the truststore |
| `com.sun.management.jmxremote.ssl` | Enables/disables TLS on the connector; defaults to `true` |
| `com.sun.management.jmxremote.ssl.need.client.auth` | Requires a client certificate when TLS is enabled |
| `com.sun.management.jmxremote.registry.ssl` | Secures the RMI Registry with TLS |

A production configuration template in `management.properties`:

~~~properties
com.sun.management.jmxremote.port=9010
com.sun.management.jmxremote.rmi.port=9011
com.sun.management.jmxremote.host=10.20.30.40
com.sun.management.jmxremote.authenticate=true
com.sun.management.jmxremote.password.file=/etc/myapp/jmxremote.password
com.sun.management.jmxremote.access.file=/etc/myapp/jmxremote.access
com.sun.management.jmxremote.ssl=true
com.sun.management.jmxremote.registry.ssl=true
com.sun.management.jmxremote.ssl.need.client.auth=true
~~~

Start the JVM with the management file and provisioned keystore/truststore:

~~~text
java -Dcom.sun.management.config.file=/etc/myapp/management.properties -Djava.rmi.server.hostname=jmx-app-01.example.internal -Djavax.net.ssl.keyStore=/etc/myapp/jmx-server.p12 -Djavax.net.ssl.keyStoreType=PKCS12 -Djavax.net.ssl.trustStore=/etc/myapp/jmx-truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12 -jar application.jar
~~~

Keystore/truststore passwords must be supplied through your deployment environment's secret-management mechanism. Never commit real passwords to source control, store them in world-readable configuration files, or leave them in command history.

When using mutual TLS, the two-way configuration must include:

- Server keystore containing the server certificate and private key.
- Server truststore trusting the client certificate or the CA that issued it.
- Client keystore containing the client certificate and private key.
- Client truststore trusting the server certificate or the CA that issued it.

You can use `keytool` to generate key pairs, export public certificates, and import them into truststores. In production, prefer certificates issued by an internal CA or an organization-approved CA, and manage private keys and passwords with secret management.

An important security note: Oracle highlights the risk of RMI Registry spoofing when a connector stub is retrieved from an unsecured registry. Enabling TLS only on the connector is not enough to eliminate this risk. For production, enable `com.sun.management.jmxremote.registry.ssl=true` and client certificate authentication, along with password/login authentication for user authorization.

## 9. Connecting from JConsole

Once the remote JMX agent is running, run on the operator workstation:

~~~text
jconsole jmx-app-01.example.internal:9010
~~~

Or launch JConsole with no arguments, select Remote Process, and enter:

- Host name: `jmx-app-01.example.internal`
- Port: `9010`
- User name: a role defined in the password file
- Password: the corresponding password for that role

If using a JMX service URL, the default address of the JMX RMI agent has the form:

~~~text
service:jmx:rmi:///jndi/rmi://jmx-app-01.example.internal:9010/jmxrmi
~~~

Enter the URL in JConsole's Remote Process field. The URL specifies the registry port, not the RMI connector port.

If the server certificate is not in JConsole's default truststore, pass a truststore to the JVM running JConsole using `-J`:

~~~text
jconsole -J-Djavax.net.ssl.trustStore=/etc/jmx/client-truststore.p12 -J-Djavax.net.ssl.trustStoreType=PKCS12 jmx-app-01.example.internal:9010
~~~

When using mutual TLS, also configure a client keystore for JConsole:

~~~text
jconsole -J-Djavax.net.ssl.keyStore=/etc/jmx/jconsole-client.p12 -J-Djavax.net.ssl.keyStoreType=PKCS12 -J-Djavax.net.ssl.trustStore=/etc/jmx/jconsole-truststore.p12 -J-Djavax.net.ssl.trustStoreType=PKCS12 jmx-app-01.example.internal:9010
~~~

Do not hardcode real keystore passwords directly in scripts or recorded command lines; process arguments can be read by other users on the same host. Use an environment-appropriate secret and certificate management mechanism.

## 10. Main tabs in JConsole

Once connected, JConsole provides six main tabs:

| Tab | Contents and usage |
|---|---|
| Overview | At-a-glance view of CPU, memory, thread count, and class loading on one screen |
| Memory | Heap, non-heap, memory pools, used/committed/max, and GC time |
| Threads | Thread list, states, stack traces, and deadlock detection |
| Classes | Currently loaded, total loaded, and unloaded class counts |
| VM | Uptime, process CPU time, VM arguments, class path, and runtime details |
| MBeans | Platform MXBeans and custom MBeans, including attributes, operations, and notifications |

### 10.1. Overview

Use Overview to quickly monitor CPU usage, memory usage, thread count, and loaded classes. When a metric spikes unexpectedly, switch to the corresponding specialized tab to investigate the cause.

### 10.2. Memory

The Memory tab displays heap and non-heap usage over time, memory pools, and GC details. Key metrics include:

- Used: memory currently in use.
- Committed: memory guaranteed to be available for use by the VM.
- Max: maximum limit if defined by the VM.
- GC time: total collection time and count.

Memory pools depend on the collector and JDK. Do not assume pool names are identical across G1, ZGC, and Parallel GC.

The `Perform GC` button requests that the JVM run garbage collection. This is a management operation that can cause pauses or CPU spikes; do not click it repeatedly to treat a memory leak or rely on it as the sole measure of heap health.

### 10.3. Threads

The Threads tab shows the live thread count, peak thread count, thread list, states, and stack traces. Select a thread to inspect its call stack at the latest refresh.

The `Detect Deadlock` button checks for deadlocks involving object monitors and ownable synchronizers such as `ReentrantLock`. If a deadlock is found, JConsole displays a deadlock results tab next to the Threads tab.

When investigating thread pools, lock contention, or hung requests, combine this view with a thread dump from `jcmd <PID> Thread.print -l`.

### 10.4. Classes

The Classes tab tracks total classes loaded, currently loaded classes, and unloaded classes. If the currently loaded class count grows steadily over a long period, inspect classloaders, dynamic proxies, plugins, or hot-reload mechanisms in the application.

### 10.5. VM

The VM tab displays details such as uptime, process CPU time, JIT compile time, thread counts, memory summary, VM arguments, and class path. Use this tab to confirm that JConsole is connected to the expected instance and deployment configuration.

### 10.6. MBeans

The MBeans tab displays the MBean tree grouped by ObjectName. Select an MBean to inspect:

- Attributes: attribute values and read/write permissions.
- Operations: management methods that can be invoked.
- Notifications: events that the MBean can emit.
- Metadata: MBean description and descriptors.

Platform MXBeans such as `java.lang:type=Memory`, `java.lang:type=Threading`, and `java.lang:type=Runtime` provide deeper detail than the overview charts. Applications can also register custom MBeans for business metrics or operational actions.

A writable attribute or an operation can alter JVM or application state. Only invoke them when you understand the impact and hold the appropriate role.

## 11. Saving chart data

JConsole lets you export chart data as CSV:

1. Open the tab containing the chart you want to save.
2. Right-click the chart.
3. Select `Save data as...`.
4. Choose the destination path and CSV filename.

The CSV contains timestamps and metric columns, which can be opened in a spreadsheet or correlated with other logs and metrics.

When comparing multiple time ranges, record the JDK version, timestamp, workload, and update interval. Charts represent sampled data; they do not replace GC logs, JFR, or high-resolution metrics.

## 12. Enabling remote management for a running JVM with `jcmd`

If a JVM is already running without the remote JMX agent enabled, you can check attach capability and start the agent dynamically with `jcmd`:

~~~text
jcmd <PID> ManagementAgent.status
~~~

Start the remote agent with a supported configuration:

~~~text
jcmd <PID> ManagementAgent.start jmxremote.host=10.20.30.40 jmxremote.port=9010 jmxremote.rmi.port=9011 jmxremote.authenticate=true jmxremote.ssl=true
~~~

You can pass additional options supported by the JVM, such as password/access files, registry SSL, client authentication, or a management config file. Check the exact options supported by the target JVM:

~~~text
jcmd <PID> help ManagementAgent.start
~~~

Stop the remote agent:

~~~text
jcmd <PID> ManagementAgent.stop
~~~

This command must run on the same host under a user/group with permission to attach to the JVM. If attach is disabled or the process runs in a different container namespace, the operation may fail.

Starting the agent dynamically does not replace preparing certificates, truststores, password files, access files, and firewall rules. For production, standardize the configuration in deployment/startup configs so it is auditable, reproducible, and persists across restarts.

## 13. Java 17+ example: testing remote JMX on loopback

This lab runs both the registry and connector only on `127.0.0.1`. Disabling authentication and TLS is solely to simplify the local exercise; never use these options for a remote host or production.

Create `RemoteJmxTarget.java`:

~~~java
public final class RemoteJmxTarget {
    private RemoteJmxTarget() {
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("REMOTE_JMX_READY");
        Thread.sleep(300_000);
    }
}
~~~

Create `JmxProbe.java` to verify the JMX service URL:

~~~java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public final class JmxProbe {
    private JmxProbe() {
    }

    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
                "service:jmx:rmi:///jndi/rmi://127.0.0.1:19099/jmxrmi");

        try (JMXConnector connector = JMXConnectorFactory.connect(url)) {
            MBeanServerConnection server =
                    connector.getMBeanServerConnection();

            ObjectName runtime =
                    new ObjectName("java.lang:type=Runtime");

            server.getAttribute(runtime, "VmName");
            System.out.println("JMX_CONNECT_OK");
        }
    }
}
~~~

Compile:

~~~text
javac --release 17 RemoteJmxTarget.java JmxProbe.java
~~~

Run the server in the first terminal:

~~~text
java -Dcom.sun.management.jmxremote.port=19099 -Dcom.sun.management.jmxremote.rmi.port=19100 -Dcom.sun.management.jmxremote.host=127.0.0.1 -Djava.rmi.server.hostname=127.0.0.1 -Dcom.sun.management.jmxremote.authenticate=false -Dcom.sun.management.jmxremote.ssl=false -cp . RemoteJmxTarget
~~~

Stdout:

~~~text
REMOTE_JMX_READY
~~~

In a second terminal, launch JConsole:

~~~text
jconsole 127.0.0.1:19099
~~~

JConsole connects to registry port `19099`. In the remote connection dialog, the host is `127.0.0.1` and the port is `19099`.

You can also test the endpoint with the JMX client:

~~~text
java JmxProbe
~~~

Stdout:

~~~text
JMX_CONNECT_OK
~~~

Both ports `19099` and `19100` must be free. If another process is already using them, pick two different ports and update the server command, JMX URL, and JConsole host/port accordingly. When finished, stop the test JVM with `Ctrl+C`.

This lab was verified on Zulu/OpenJDK 24.0.2: the server printed `REMOTE_JMX_READY`, the client printed `JMX_CONNECT_OK`, and both listeners bound only to `127.0.0.1`.

## 14. Troubleshooting remote connections

### `Connection refused`

**Cause:** the remote agent is not enabled, the JVM has stopped, the port is wrong, or a firewall is rejecting the connection.

**Resolution:** check startup options, the running process, and listeners on the registry port; verify the port is not occupied by another process.

### Registry connection succeeds, then times out

**Cause:** the RMI connector port is unreachable or the stub advertises a hostname/IP that is not routable from the client.

**Resolution:** pin `com.sun.management.jmxremote.rmi.port`, open both TCP ports, and set `java.rmi.server.hostname` to an address reachable by the client.

### `Unknown host` or connecting to the wrong address

**Cause:** DNS cannot resolve the hostname in the RMI stub, or the hostname points to an internal interface.

**Resolution:** check DNS from the JConsole host, `jmxremote.host`, and `java.rmi.server.hostname`. Do not check only the hostname in the JConsole command; the stub must also advertise the right address.

### `SSLHandshakeException`

**Cause:** the client does not trust the server certificate, the certificate is expired, the hostname does not match, the client certificate is missing, or the truststore is incorrect.

**Resolution:** verify keystores/truststores on both sides, the certificate chain, SAN/hostname, certificate expiration, and mutual TLS configuration.

### `Authentication failed`

**Cause:** the username does not exist in the password file, the password does not match, the role is missing from the access file, or the file format is invalid.

**Resolution:** check both files, role names, and file permissions. Use dedicated JMX credentials rather than personal passwords.

### JMX agent fails to start

**Cause:** the port is already in use, the password/access file is malformed, or the password file has overly permissive read access.

**Resolution:** inspect JVM stderr/logs, active listeners, and file permissions. Fix the configuration and restart according to your deployment procedure.

### JConsole does not list a local JVM

**Cause:** JConsole and the JVM are running under different users, the Attach API is restricted, or the process is in a different container/PID namespace.

**Resolution:** run JConsole as the appropriate user, confirm the PID in the right environment, and check the attach mechanism.

### JConsole connects, but some operations are denied

**Cause:** the current role is `readonly`, or the MBean does not allow that operation.

**Resolution:** check the access file and MBean operation. Grant `readwrite` only if needed and approved operationally.

### Charts do not update or data appears delayed

**Cause:** a long update interval, an overloaded JVM, network latency, or slow JMX polling.

**Resolution:** check the interval, reduce the number of monitored charts, cross-check with GC logs/JFR, and avoid polling too aggressively.

## 15. Performance impact and operational limits

JConsole continuously samples MBeans to update its charts. Overhead depends on the number of threads, number of MBeans, update frequency, and JVM state.

Key guidelines:

- Run JConsole on the operator workstation to avoid UI overhead on the application host.
- Keep an appropriate update interval; the default is 4 seconds, and you can raise it to 10 seconds for general observation.
- Avoid opening multiple JConsole sessions polling the same JVM at high frequency.
- Limit invoking heavy MBean operations when the system is under heavy load.
- Do not use the `Perform GC` button as a fix for memory leaks.
- Export CSV selectively and protect operational data.
- Use GC logs, JFR, and monitoring metrics for long-term observability; JConsole is suited for interactive inspection and point-in-time investigation.

Because JMX exposes JVM management, a `readwrite` account can affect the running application. Separate monitoring and control roles, and grant control permissions only to authorized operators.

## 16. Production workflow for connecting to a remote JVM

1. Identify the exact service, host, JDK version, and management interface.
2. Choose unused, fixed registry and RMI connector ports.
3. Configure `jmxremote.host` and `java.rmi.server.hostname`.
4. Prepare the server keystore, server truststore, and client certificates if using mutual TLS.
5. Configure `jmxremote.password` or JAAS/LDAP authentication.
6. Configure the access file with separate `readonly` and `readwrite` roles.
7. Enable TLS, protect the RMI Registry with `jmxremote.registry.ssl=true`, and enable client certificate authentication.
8. Restrict firewall access to the management subnet or jump hosts only.
9. Start the JVM with the remote management options and check the agent logs.
10. Connect with JConsole using host/registry port, and verify the target JVM in the VM tab.
11. Start with a `readonly` role for observation; switch to a control role only when actions are required.
12. Record the timestamp, operator, host, port, JDK version, and purpose of the session.
13. Revoke unused credentials/certificates and close management ports when no longer needed.

## 17. Pre-connection checklist

- [ ] Verified the target host and JVM.
- [ ] Remote JMX agent is enabled.
- [ ] Registry port and RMI connector port are pinned.
- [ ] Bind interface and advertised hostname are configured.
- [ ] Both TCP ports are reachable from the JConsole host.
- [ ] Authentication is enabled and password/access files are valid.
- [ ] Password file is readable only by the account running the JVM.
- [ ] TLS certificates, keystores, and truststores are valid on both sides.
- [ ] RMI Registry is secured and client certificate auth is enabled per production policy.
- [ ] Monitoring role has `readonly` access only.
- [ ] `readwrite` role is restricted to operators who require it.
- [ ] JConsole is connected to the intended JMX endpoint.
- [ ] Inspected Overview, Memory, Threads, Classes, VM, and MBeans according to the investigation goal.
- [ ] High-impact operations are not invoked without prior assessment.
- [ ] Thread dumps, CSV exports, and MBean data are stored in access-controlled locations.
- [ ] A plan is in place to close the session, revoke access, and manage certificates/credentials.

## 18. References

- Oracle JDK 24 — Monitoring and Management Using JMX Technology: https://docs.oracle.com/en/java/javase/24/management/monitoring-and-management-using-jmx-technology.html
- Oracle JDK 24 — Using JConsole: https://docs.oracle.com/en/java/javase/24/management/using-jconsole.html
- Oracle JDK 24 — The `jconsole` Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jconsole.html
- Oracle JDK 24 — The `jcmd` Command, `ManagementAgent.start` section: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html
- Java SE 24 — `JMXServiceURL` API: https://docs.oracle.com/en/java/javase/24/docs/api/java.management/javax/management/remote/JMXServiceURL.html

Connecting to a remote JVM with JConsole relies on JMX/RMI: enable the management agent, configure the registry and connector ports, set the bind and advertised host addresses, and connect using `host:port` or a JMX service URL. Because JMX provides both read access and administrative operations, production environments require TLS, client authentication, read-only/read-write role separation, and firewalls restricted to the management network.