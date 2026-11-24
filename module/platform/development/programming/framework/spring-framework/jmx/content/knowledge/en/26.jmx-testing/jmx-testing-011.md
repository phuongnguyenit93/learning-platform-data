# Spring Framework JMX — Testing Access Permissions and Authentication Failures

## 1. Goal

Spring JMX security testing must verify two independent stages: authentication at the JMX connector (verifying identity) and authorization (deciding permissions to read/write attributes and invoke operations). The goal is not merely receiving an exception on denial, but also confirming that MBean state remains unchanged after unauthorized attempts.

## 2. Architecture

```text
JMX client / credentials
   -> JMXConnectorServer / JMXAuthenticator
   -> authorization policy
   -> MBeanServer
   -> Spring MBeanExporter / exported MBean
   -> getAttribute / setAttribute / invoke
```

Spring Security `@PreAuthorize` and JMX connector security are two separate mechanisms. Method security only works when the call passes through a Spring AOP proxy with a valid `Authentication`. A JMX connector does not automatically translate a JMX login into a Spring `SecurityContext`; therefore, test both the connector policy and business method security when needed.

## 3. Distinguishing Authentication and Authorization

| Scenario | Classification |
|---|---|
| Wrong username or password during connect | Authentication failure |
| No credentials supplied when required by server | Authentication failure |
| Read-only user connects but cannot write | Authorization denial |
| User with read permission is denied invoking resetJobs | Authorization denial |
| DNS fails to resolve | Transport error |
| Untrusted TLS certificate | TLS/transport error |
| MBean does not exist | Registry error |
| Wrong operation signature | Contract/invocation error |

Do not classify network, ObjectName, or MBean method errors as login failures. When `SecurityException` is thrown, identify which stage raised it.

## 4. Preparing the MBean Fixture

```java
public interface TestControlMBean {
    int getJobs();
    int getLimit();
    void setLimit(int limit);
    void resetJobs();
}

public class TestControl implements TestControlMBean {
    private int jobs = 5;
    private int limit = 10;
    public synchronized int getJobs() { return jobs; }
    public synchronized int getLimit() { return limit; }
    public synchronized void setLimit(int value) {
        if (value < 1 || value > 100) throw new IllegalArgumentException();
        limit = value;
    }
    public synchronized void resetJobs() { jobs = 0; }
}
```

Register in a dedicated test MBeanServer:

```java
MBeanServer server = MBeanServerFactory.newMBeanServer("test");
ObjectName name = new ObjectName("com.example.test:type=Control,name=fixture");
server.registerMBean(new TestControl(), name);
```

Keep test data separate from production. Use a dedicated ObjectName namespace, unregister when finished, and never invoke dangerous operations on live environments.

## 5. Designing a Permission Matrix

| Principal | Connect | Read Jobs | Write Limit | Invoke resetJobs |
|---|---|---|---|---|
| Invalid credentials | Denied | N/A | N/A | N/A |
| monitor | Allowed | Allowed | Denied | Denied |
| operator | Allowed | Allowed | Allowed | Denied |
| admin | Allowed | Allowed | Allowed | Allowed |

The matrix above is a proposed test policy, not JMX's default permissions. Authorization enforcement must be configured at the JMX connector, MBeanServer wrapper, or trusted management layer before assertions become meaningful.

## 6. Testing Invalid Credentials

```java
Map<String, Object> env = Map.of(
    JMXConnector.CREDENTIALS,
    new String[] {"monitor", "wrong-password"}
);

assertThrows(SecurityException.class, () -> {
    try (JMXConnector ignored = JMXConnectorFactory.connect(url, env)) {
        // Connection must not succeed.
    }
});
```

The exact exception type may vary by JMX provider or be wrapped. Verify the implementation's contract rather than comparing brittle exact error messages. Test blank credentials, wrong username, wrong password, revoked credentials, and newly rotated credentials. Limit retry attempts to avoid triggering account lockouts.

## 7. Testing Read, Write, and Invoke Permissions

Read attribute:

```java
int jobs = (Integer) connection.getAttribute(name, "Jobs");
```

Write attribute:

```java
connection.setAttribute(name, new Attribute("Limit", 20));
```

Invoke operation:

```java
connection.invoke(name, "resetJobs", new Object[0], new String[0]);
```

For the `monitor` user, verify that writing is rejected and the value remains unchanged:

```java
int before = (Integer) connection.getAttribute(name, "Limit");
assertThrows(SecurityException.class, () ->
    connection.setAttribute(name, new Attribute("Limit", before + 1))
);
int after = (Integer) connection.getAttribute(name, "Limit");
assertEquals(before, after);
```

If the provider wraps `SecurityException`, assert the proper cause chain instead of assuming a single top-level class. For side-effecting operations, verify that counters or fake services were never called; observing an exception alone does not prove state stayed unchanged.

## 8. Testing Spring Security Proxies

```java
@ManagedOperation
@PreAuthorize("hasAuthority('ops:reset')")
public void resetJobs() { /* ... */ }
```

For method security to take effect, the application must enable infrastructure such as `@EnableMethodSecurity`, the call must pass through an AOP proxy, and the security context must hold an appropriate identity. JMX connector threads do not carry HTTP `Authentication` by default. If `MBeanExporter` exports the raw target and invokes target methods directly, proxy advice may be bypassed.

A testable solution is a small JMX management facade injecting the business service via its Spring proxy. Integration tests must prove: an insufficiently privileged principal is blocked before side effects occur; an authorized principal executes the call once. With JDK dynamic proxies, operations invoked through the proxy must appear on the interface; self-invocation can also bypass method-security advice.

## 9. Error Classification

| Exception | Issue Category |
|---|---|
| UnknownHostException / ConnectException | DNS or network |
| SSLHandshakeException | TLS, certificate, trust |
| SecurityException on connect | Authentication or connector policy |
| SecurityException on invoke | Authorization or policy |
| InstanceNotFoundException | Wrong ObjectName or server |
| AttributeNotFoundException | Wrong attribute name or permissions |
| ReflectionException | Wrong operation signature |
| MBeanException | MBean logic threw an error |

Never automatically retry a sent operation on client timeout, because the server may have completed execution while the response was lost. Check idempotency and post-state before retrying.

## 10. Auditing and Operational Testing

Audit events should record timestamp, logical target, connector type, outcome, failure category, and authenticated principal when permitted. Never log passwords, tokens, credential maps, or secret data. Metrics can include `jmx_authentication_failures_total`, `jmx_authorization_denials_total`, and `jmx_connect_failures_total{category}` — these are illustrative application-defined names.

Test cleanup includes closing `JMXConnector` via try-with-resources, stopping `JMXConnectorServer`, unregistering the MBean fixture, releasing RMI ports, and leaving no high-privilege test accounts behind. In CI, use loopback and managed ports; avoid hardcoded ports that collide. Never test brute-force or lockouts against production accounts.

## 11. Practice Exercises

1. Create an MBean fixture with a readable attribute, a writable attribute, and a `resetJobs` operation; register it in a test MBeanServer.
2. Create a read-only `monitor` account; verify `connect` and `getAttribute` succeed while `setAttribute` and `invoke` are denied.
3. Verify `Limit` and `Jobs` remain unchanged after each denied attempt.
4. Supply wrong credentials, verify connection rejection, and verify an authentication failure audit event.
5. Test that `operator` can write `Limit` but cannot invoke `resetJobs`.
6. Test Spring `@PreAuthorize` through a JMX facade, confirming the AOP proxy participates in the invocation path.
7. Disconnect or pass an invalid URL and verify the error is classified as transport rather than login failure.

## 12. Conclusion

Testing JMX access permissions does not stop at verifying a successful connection. Test both authentication failures and authorization denials, verify attribute reads/writes and operation invocations per principal, confirm no side effects occur when denied, and keep logs safe. When relying on Spring Security, verify the actual execution path through proxies; connector security and method security are separate boundaries and do not substitute for one another.