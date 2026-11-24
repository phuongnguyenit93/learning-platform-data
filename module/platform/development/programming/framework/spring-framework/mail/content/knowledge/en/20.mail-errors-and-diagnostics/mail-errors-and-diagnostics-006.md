# DNS, Timeout, and Connection Refused Errors

## 1. Overview

When sending email through **Spring Framework Mail**, the application typically uses **`JavaMailSender`** and Jakarta Mail to connect to an **SMTP server**. Before an email is sent, the application must resolve the server's IP address, establish a TCP connection, perform TLS or STARTTLS if needed, authenticate, and exchange SMTP commands.

If any step fails, users might only see a generic message such as "Failed to send email". However, the following errors have different root natures:

- **DNS error**: the application fails to resolve the SMTP server hostname to an IP address, or receives an invalid resolution result.
- **Connection refused**: a TCP connection attempt is actively rejected, usually because no service is listening on that address/port or a network device actively sends a rejection.
- **Connect timeout**: a connection cannot be established within the allowed time, usually because packets are blocked, dropped, or the network path does not respond.
- **Read timeout**: a connection exists, yet the application waits too long for an SMTP response.
- **Write timeout**: writing data onto the socket takes longer than the configured limit.

Some errors look like network errors on the surface yet stem from **TLS**, **authentication**, **SMTP provider policy**, or **wrong port configuration**. To handle them properly, determine which step failed and separate **cannot connect** from **connected but cannot send**.

In this lesson, the goal is to diagnose each error group systematically, configure sensible timeouts, and decide when to retry without creating duplicate email risks.

## 2. The SMTP Connection Journey in a Spring Application

Simplified flow:

~~~text
Spring application
       |
       | JavaMailSender.send(...)
       v
JavaMailSenderImpl / Jakarta Mail
       |
       | 1. DNS resolution for SMTP host
       v
Hostname -> IP address
       |
       | 2. TCP connection to host:port
       v
SMTP server greeting
       |
       | 3. EHLO / HELO
       | 4. STARTTLS or TLS from start (per config)
       | 5. Authentication if required
       | 6. MAIL FROM / RCPT TO
       | 7. DATA and MIME content
       | 8. Server returns accept/reject reply
       v
SMTP queue / next relay
~~~

Example configuration:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
~~~

With this configuration, the application needs to resolve **smtp.example.com**. Then it connects directly to the server at the declared host and port; it does not look up the recipient domain's MX records during normal email submission.

**Note:** DNS and other sending steps can fail independently. Resolving a domain name does not mean the TCP port is open; succeeding at TCP connect does not mean TLS or SMTP authentication will succeed.

## 3. Distinguishing SMTP Submission from Recipient DNS MX

This is a common confusion when seeing DNS errors.

In the email-sending model using an SMTP provider:

~~~text
Spring application
      |
      | spring.mail.host config
      v
smtp.provider.example  <-- application connects to this host
      |
      | provider forwards email
      v
Recipient domain's MX
      |
      v
Receiving mail server
~~~

The Spring application resolves the hostname of the configured **SMTP relay/submission server**. Looking up MX records to route mail to the destination domain is normally the responsibility of the mail provider's MTA, not `JavaMailSender` in this submission flow.

| DNS component | Used for | When it matters |
|---|---|---|
| **A / AAAA** | Maps hostname to IPv4/IPv6 | When the application connects to the SMTP host |
| **CNAME** | Aliases hostname to another name | If the SMTP hostname is an alias |
| **MX** | Identifies mail-receiving servers for a domain | When a mail server routes mail to the destination domain |
| **TXT SPF/DKIM/DMARC** | Authentication/mail-sending policy info | Operations and deliverability, does not replace resolving the SMTP host |

If the application throws **`UnknownHostException`** for `smtp.example.com`, checking MX records for the recipient address usually will **not** address the direct cause. Start from the configured SMTP hostname.

## 4. Signs of DNS Errors

DNS errors occur when the hostname cannot be resolved or resolution fails. Java may throw **`java.net.UnknownHostException`**, which may be wrapped inside a Jakarta Mail or Spring Mail exception.

Common message example:

~~~text
java.net.UnknownHostException: smtp.example.com
~~~

Possible causes:

- Typo in hostname or using a nonexistent hostname.
- Host configured via a wrong or empty environment variable.
- DNS resolver of the machine/VM/container is unreachable.
- DNS server returns **NXDOMAIN** for a nonexistent name.
- DNS server returns **SERVFAIL** or times out.
- Internal network requires a private DNS while the application uses another resolver.
- Split-horizon DNS: the same name returns different results internally vs. on the public Internet.
- DNS cache in the JVM or OS has not updated after records changed.
- Host has an IPv6 address, but the environment's IPv6 path does not work reliably.

### Different DNS Scenarios

| Scenario | Characteristics | How to diagnose |
|---|---|---|
| **NXDOMAIN** | Domain/hostname does not exist per DNS reply | Check host name, zone, alias |
| **SERVFAIL** | DNS server could not process the query | Check resolver and DNS infrastructure |
| **DNS timeout** | No response received from resolver | Check network to DNS server, firewall, container DNS |
| **Returns old IP** | Possibly due to TTL or cache | Check TTL, DNS cache, new address |
| **Returns wrong private IP** | Possibly due to split DNS or environment config | Check active resolver and routing |
| **Only AAAA or IPv6 preferred** | Environment lacks an IPv6 route | Compare A/AAAA and actual connectivity |

A single Java exception usually does not explicitly distinguish every DNS response type. Cross-check with DNS tools and resolver logs if needed.

## 5. Check Hostname Configuration Before Checking the Network

First determine the **effective host** Spring actually uses. Do not look only at the default value in one config file:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
~~~

This value can be overridden by:

- Another profile such as `application-prod.yml`.
- Environment variable **`SPRING_MAIL_HOST`**.
- Command-line arguments or higher-precedence property sources.
- Secrets/ConfigMaps in container orchestration.
- A manually configured **`JavaMailSenderImpl`** bean that does not read the properties above.

With multiple senders, each bean may use a different host/port. Confirm which sender actually handles the failing notification.

Do not print the entire mail configuration for debugging as it can expose username, password, or tokens. Only log permitted info such as hostname, port, environment name, and logical sender ID.

### Checking Environment Variables

Example configuration:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
~~~

If `SMTP_HOST` is assigned wrongly, one environment may work while another reports DNS failure. Check the actual host value inside **the exact process/container experiencing the failure**.

## 6. DNS Diagnostic Tools

On Windows with PowerShell:

~~~powershell
Resolve-DnsName smtp.example.com -Type A
Resolve-DnsName smtp.example.com -Type AAAA
Resolve-DnsName smtp.example.com -Type CNAME
~~~

You can also use `nslookup`:

~~~text
nslookup smtp.example.com
~~~

On Linux or environments with corresponding tools:

~~~bash
getent hosts smtp.example.com
dig smtp.example.com A
dig smtp.example.com AAAA
nslookup smtp.example.com
~~~

Not every container image has `dig`/`nslookup` installed. If the application runs in Kubernetes or Docker, test DNS **from the same network namespace or a debug environment with identical DNS configuration**, rather than only testing from a laptop.

### Reading Results Correctly

- DNS query succeeds and returns an IP: grounds to proceed with TCP testing, though it does not yet prove the application can connect.
- DNS query fails: inspect resolver, hostname, zone, search suffix, and network policies.
- DNS query succeeds on laptop yet fails in container: focus on container DNS/network configuration.
- A and AAAA results differ: test the corresponding IPv4/IPv6 paths.
- Fails in only one environment: compare profiles, resolvers, VPNs, proxies, and outbound policies.

Do not change production DNS or flush caches widely before identifying the cause and blast radius.

## 7. DNS Caching and Differences Between the JVM and OS Tools

Java applications cache hostname resolution results. Cache duration depends on the JVM, security/network properties, and environment.

Typical scenario:

1. The SMTP provider changes its IP address or DNS alias.
2. `dig`/`nslookup` on the machine returns the new IP.
3. A long-running Java process keeps using the old result for some time.
4. Connections from the application continue to fail.

This does not prove the JVM is definitely caching wrongly; verify the timing of the DNS change, DNS TTL, JVM configuration, and where lookups happen.

Related Java properties:

~~~text
networkaddress.cache.ttl
networkaddress.cache.negative.ttl
~~~

Effective duration and configuration depend on the runtime; do not set TTL to 0 for every environment or disable caching as a "universal fix". Too low a TTL can increase DNS load and latency.

If temporary recovery is needed, restarting an instance may refresh DNS results, but fixing the hostname, resolver, or network path addresses the root cause.

## 8. What Is Connection Refused?

**Connection refused** is commonly represented in Java by **`java.net.ConnectException`**:

~~~text
java.net.ConnectException: Connection refused
~~~

At the TCP level, this error usually indicates one side actively rejected the connection attempt, e.g., the OS returning an RST when no service is listening on the target port.

Common causes:

- Hostname resolves properly, but the **configured port is wrong**.
- SMTP server is not running or has not bound to the required interface.
- Server listens only on localhost/internal interfaces, not the IP the application accesses.
- Firewall, load balancer, or gateway actively rejects connections.
- Connected to the wrong server due to DNS or routing.
- Provider does not support the chosen port.
- NAT, proxy, or service mesh routes to an endpoint with no listener.

**Connection refused differs from connect timeout:** refused usually indicates a fast explicit rejection, whereas timeout usually means no connection establishment result arrived within the time limit.

## 9. Distinguishing Connection Refused, Connect Timeout, and Network Unreachable

| Symptom | Indicator | Causes to consider |
|---|---|---|
| **Connection refused** | Connection rejected quickly | Wrong port, no listener, firewall reject |
| **Connect timeout** | Waited full configured duration then failed | Packets dropped, network path unresponsive |
| **Network is unreachable** | OS has no route to destination | Routing, interface, or VPN |
| **No route to host** | No suitable route or blocked by policy | Route, ACL, firewall, network segment |
| **UnknownHostException** | No usable IP address obtained | DNS/host configuration |
| **Read timed out** | Connection established, but reply not received in time | Slow server, network, SMTP/TLS phase |

Error messages depend on OS, JDK, and implementation; the same infrastructure cause can surface as different exceptions. The table is a diagnostic guide, not an absolute rule.

### Wrong Port Example

Suppose the SMTP provider supports submission on port 587, while the application uses port 2526. If no service listens there and the firewall does not drop packets, the client can immediately receive connection refused.

If a firewall blocks outbound traffic to port 587 without sending a reject, the connection attempt may time out instead of refusing.

What to inspect is **the actual `host:port` and network path**, not just increasing timeouts.

## 10. Checking TCP Ports with Network Tools

On Windows PowerShell:

~~~powershell
Test-NetConnection smtp.example.com -Port 587
~~~

On Linux with netcat:

~~~bash
nc -vz -w 5 smtp.example.com 587
~~~

If `telnet` is available, it can be used to observe a TCP connection to the SMTP server:

~~~text
telnet smtp.example.com 587
~~~

With plaintext SMTP before STARTTLS, the server typically sends a greeting like:

~~~text
220 smtp.example.com ESMTP ready
~~~

**Do not use `telnet` to enter SMTP credentials** because this session is not guaranteed to be TLS-protected. Telnet is only suitable when checking listener/greeting in permitted environments.

If TCP connect succeeds, next check TLS, authentication, and SMTP responses. A successful TCP probe **is not enough to conclude the application can send email**.

### Why Is Ping Not a Decisive Test?

Ping uses ICMP. A server may block ICMP while still allowing TCP to the SMTP port. Conversely, a successful ping does not prove port 587 is open.

Therefore:

- Use DNS lookup to verify name resolution.
- Use a TCP port probe to verify network reachability to `host:port`.
- Use controlled TLS/SMTP tests to verify the protocol.
- Use ping only as a secondary signal if network policy allows it.

## 11. Choosing the Right Port and TLS Mode

Common SMTP connection patterns:

| Port | Common usage | Security mechanism |
|---|---|---|
| **587** | Mail submission | TCP connect, then STARTTLS upgrade |
| **465** | Submission with implicit TLS | TLS starts immediately upon connect |
| **25** | SMTP relay/MTA transfer; occasionally supported by special policy | May support STARTTLS; often blocked outbound in clouds |
| **2525** | Alternative port supported by some providers | Provider-dependent |

These are common conventions; not all providers support every port. Always rely on the documentation or service configuration of your SMTP system.

### STARTTLS on Port 587

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
~~~

With STARTTLS, the SMTP connection starts unencrypted and upgrades to TLS after the server advertises support. Setting **required: true** requires STARTTLS to succeed rather than continuing unencrypted if the server lacks support.

### Implicit TLS on Port 465

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 465
    properties:
      mail:
        smtp:
          auth: true
          ssl:
            enable: true
~~~

Do not configure **ssl.enable: true** on a port supporting only STARTTLS in a way that triggers an immediate TLS handshake at the start. Combining the wrong port and TLS mode can cause the client to wait on greeting/handshake until timeout or get SSL errors, not necessarily connection refused.

In all configurations, validate certificates, hostnames, and the provider's actual security requirements; never disable certificate validation just to bypass errors.

## 12. Checking TLS with OpenSSL

In environments with OpenSSL, test STARTTLS:

~~~bash
openssl s_client -starttls smtp -connect smtp.example.com:587 -servername smtp.example.com
~~~

For SMTPS/implicit TLS:

~~~bash
openssl s_client -connect smtp.example.com:465 -servername smtp.example.com
~~~

These commands let you observe certificates and TLS negotiation when connecting to the server. They do not verify SMTP username/password or sending permissions.

When reading the output, check:

- Did the TCP connection open?
- Did the TLS handshake complete?
- Was the certificate validly verified?
- Does the certificate name match the hostname?
- Does the server require or support a compatible TLS protocol?

**Do not conclude an email sending channel is secure merely because the TLS command did not report an obvious error.** Verify the verification result, trust configuration, and appropriate SMTP policies.

## 13. Connect Timeout, Read Timeout, and Write Timeout in Jakarta Mail

In Spring Boot, JavaMail properties can be passed through **spring.mail.properties**:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
~~~

The three timeout values above are in **milliseconds**.

| Property | Typically controls | Example |
|---|---|---|
| **mail.smtp.connectiontimeout** | Wait time to establish TCP connection | 5,000 ms |
| **mail.smtp.timeout** | Socket read timeout, waiting for data/replies | 10,000 ms |
| **mail.smtp.writetimeout** | Socket write timeout for writing data | 10,000 ms |

Configure **all three** to prevent a request from hanging indefinitely on the network. These are illustrative values; appropriate bounds depend on actual latency, attachment size, network path, and SLA.

### Why Is Setting Only `connectiontimeout` Insufficient?

Suppose TCP connect succeeds and the server sends its greeting. When the application sends DATA, the server or network path may be slow, making reading the final reply take a long time. Connect timeout does not guard that phase.

Conversely, setting only read timeout does not guard the initial phase when TCP cannot connect.

### Timeouts Do Not Guarantee Safety on Retry

Setting read timeout = 10 seconds does not mean that after failing at 10 seconds, the SMTP server definitely did not receive the email. If the server received DATA yet the reply was lost, the application can still hit a timeout without knowing the outcome.

Thus, timeouts are a tool to **bound wait duration**, not a mechanism proving an email was not sent.

## 14. When Are Timeouts Too Low or Too High?

A timeout that is too low can treat healthy yet slightly slow connections as failures; a timeout that is too high can hold threads and delay incident detection.

| Configuration | Possible consequence |
|---|---|
| Connect timeout too low | Fails under normal DNS/TCP/network latency |
| Read timeout too low | Fails while server processes SMTP commands or DATA |
| Write timeout too low | Prone to failing on large messages or slow networks |
| Timeout too high | Threads held long, reduced throughput, delayed retries |
| No finite timeout | Risk of hanging too long depending on network/runtime |

When setting values:

1. Measure normal SMTP connection and reply latency.
2. Account for email sizes, attachments, and concurrent send volume.
3. Check application request/worker/queue limits.
4. Align timeouts reasonably with SLAs and retry schedules.
5. Monitor p95/p99 and timeout rates after configuration changes.

Never raise timeouts indefinitely to "fix" bad DNS, firewall blocks, or refused ports. Those errors require fixing network paths or configuration.

## 15. One Error May Be Wrapped Across Multiple Exception Layers

A Spring application might catch only **MailException**, while the root cause is a DNS or Java networking error.

Conceptual chain example:

~~~text
org.springframework.mail.MailSendException
    caused by jakarta.mail.MessagingException
        caused by java.net.UnknownHostException
~~~

Or:

~~~text
MailSendException
    -> MessagingException
        -> java.net.ConnectException: Connection refused
~~~

Do not classify solely by the outermost exception. Inspect the cause chain and, when using Jakarta Mail, check **`MessagingException.getNextException()`** because this API supports linking exceptions alongside `Throwable.getCause()`.

Common groups:

| Exception | Initial interpretation |
|---|---|
| **UnknownHostException** | DNS/hostname cannot be resolved |
| **ConnectException** | TCP connection refused or connection failure |
| **SocketTimeoutException** | Timeout on a socket operation; need send phase |
| **NoRouteToHostException** | Routing or network policy issue |
| **SSLHandshakeException** | TLS negotiation/certificate failure |
| **MailAuthenticationException** | SMTP authentication error |
| **MailSendException** | Spring-layer send error; inspect detailed causes |
| **MessagingException** | Jakarta Mail error; inspect cause and next exception |

Do not lump everything into **"SMTP is down"**. Clear classification tells operations whether to fix DNS, TCP, TLS, credentials, or message content.

## 16. Reading the Cause Chain of Spring Mail Errors

A service can record a normalized error kind without dumping all SMTP details into logs. To do so, locate the underlying exception instead of relying only on message strings.

Example walking **`getCause()`**:

~~~java
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import org.springframework.mail.MailException;

public String classifyMailFailure(MailException exception) {
    for (Throwable current = exception;
         current != null;
         current = current.getCause()) {

        if (current instanceof UnknownHostException) {
            return "SMTP_DNS_FAILURE";
        }
        if (current instanceof ConnectException) {
            return "SMTP_CONNECTION_FAILURE";
        }
        if (current instanceof SocketTimeoutException) {
            return "SMTP_SOCKET_TIMEOUT";
        }
    }
    return "SMTP_OTHER_FAILURE";
}
~~~

This is a **minimal** example illustrating cause extraction. In production, handle cyclic exception chains and **`MessagingException.getNextException()`** chains when present. Also, **`SMTP_SOCKET_TIMEOUT`** is only a diagnostic code; it is **insufficient to decide retries**, since you must know whether the timeout happened at CONNECT, waiting for an SMTP reply, or after transmitting DATA.

### More Complete Traversal for Jakarta Mail

~~~java
import jakarta.mail.MessagingException;
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public static Set<Throwable> collectRelatedErrors(Throwable root) {
    Set<Throwable> seen = Collections.newSetFromMap(
            new IdentityHashMap<>()
    );
    ArrayDeque<Throwable> pending = new ArrayDeque<>();
    pending.add(root);

    while (!pending.isEmpty()) {
        Throwable current = pending.removeFirst();
        if (!seen.add(current)) {
            continue;
        }
        if (current.getCause() != null) {
            pending.addLast(current.getCause());
        }
        if (current instanceof MessagingException mailError) {
            Exception next = mailError.getNextException();
            if (next != null) {
                pending.addLast(next);
            }
        }
    }

    return seen;
}
~~~

This example assumes **root is non-null**. **`IdentityHashMap`** detects duplicate exception instances even when chains contain cycles. Use the output for internal analysis; do not automatically log every exception's message as it may contain internal hostnames, email addresses, or sensitive details.

## 17. `MailSendException` and Failures Sending Multiple Messages

If an application calls **`JavaMailSender.send(...)`** with multiple messages, one call can fail on some messages while others were already submitted.

Spring's **MailSendException** provides APIs to read messages recorded as failed, such as:

~~~java
try {
    mailSender.send(messages);
} catch (MailSendException exception) {
    Map<Object, Exception> failed =
            exception.getFailedMessages();

    for (Map.Entry<Object, Exception> entry : failed.entrySet()) {
        Object failedMessage = entry.getKey();
        Exception cause = entry.getValue();

        // Map failedMessage back to the application's notification ID.
        // Classify the error based on cause and send context.
    }
}
~~~

Here, **messages** is an array of `MimeMessage` objects created and tied to stable notification IDs. The method illustrates looking up failure info; it is not complete production code for a batch sender.

If sending a batch A, B, C where A was accepted and B rejected, **do not retry the entire batch**. Doing so may send A a second time.

In applications needing high accuracy, design **one notification/outbox record per message or per recipient** to track each submission's status easily. Per-recipient outcomes within a single multi-recipient `MimeMessage` can be more complex and require analyzing **`SendFailedException`** per Jakarta Mail.

## 18. Layer-by-Layer Diagnostic Workflow

A practical runbook moves from simple, low-cost checks to complex ones.

**Step 1 — Determine Scope**

- Are all emails failing or only one notification type?
- Does the failure occur on all instances or one instance?
- Only in production or also in staging?
- Did it start after a deploy, secret change, DNS change, or firewall change?
- Is it continuous or intermittent?

**Step 2 — Read the Actual Exception**

- Record the outermost Spring exception and cause chain.
- Look for `UnknownHostException`, `ConnectException`, `SocketTimeoutException`, `SSLHandshakeException`.
- If an SMTP reply is present, record the code and associated command.
- Determine which phase the timeout occurred in if evidence exists.

**Step 3 — Confirm Effective Configuration**

- Active SMTP host, port, and sender bean.
- Active profile and environment variables.
- STARTTLS vs. implicit TLS.
- Whether timeouts are configured.
- Outbound network policy of the current environment.

**Step 4 — Check DNS**

- Look up A/AAAA from the exact environment where the app runs.
- Compare against another resolver if needed.
- Inspect IP, TTL, split DNS, or DNS cache.

**Step 5 — Check TCP**

- TCP probe to the exact `host:port`.
- Distinguish refused, timeout, and no route.
- Inspect firewall/egress rules, NAT, proxies, and service meshes.

**Step 6 — Check TLS and SMTP**

- Can the SMTP greeting be reached?
- Is STARTTLS advertised/supported?
- Are the TLS certificate and hostname valid?
- Is authentication accepted by the server?
- Are there explicit SMTP `4xx`/`5xx` replies?

**Step 7 — Cross-Check Application Logs and Metrics**

- Connection latency / total send duration.
- Timeout rates and errors per instance.
- Timing of configuration/deploy events.
- Pending/retry/unknown counts in the outbox.

**Do not jump straight to increasing timeouts before verifying the right host and port.** A nonexistent hostname or port without a listener will not be fixed by waiting longer.

## 19. Diagnosing in Docker and Kubernetes

An error occurring only inside a container usually relates to the runtime environment, not necessarily Spring Mail.

Items to check:

| Layer | Example issue |
|---|---|
| **Container DNS** | Misconfigured resolver, CoreDNS failure, wrong DNS policy |
| **Network namespace** | Container has a different network path than the host |
| **Egress policy** | NetworkPolicy or firewall blocks outbound SMTP |
| **NAT/route** | No path to the Internet or to private SMTP |
| **Service mesh** | Sidecar/proxy restricts ports or TLS |
| **Environment variables** | Secret or ConfigMap not updated |
| **IPv6** | Container gets AAAA DNS records, but IPv6 routing does not work |

### Do Not Test Only on a Development Machine

If a developer's laptop reaches the SMTP host fine while a production pod times out, test from the pod or a debug container sharing the same namespace and network policy.

Example command in an authorized Kubernetes environment:

~~~bash
kubectl exec -n app-namespace deploy/mail-worker -- printenv SPRING_MAIL_HOST
~~~

This command prints only the permitted hostname. **Never print `SPRING_MAIL_PASSWORD` or secrets.** For containers without a shell or network tools, use a debug container per approved operational procedures; never modify production pods just to test networking.

### Checking NetworkPolicy

A NetworkPolicy may allow the application to access the database yet block outbound traffic to the SMTP provider. If egress is dropped, connect timeout is a common symptom.

If only one namespace fails, compare policies, DNS configuration, and network routes with a working namespace. If only one node fails, inspect node-specific issues, DNS, or network agents.

## 20. Cloud Providers and Outbound SMTP Restrictions

Some cloud environments restrict or filter outbound SMTP ports, especially port 25. This depends on provider, account, region, and network policy.

When connecting to public SMTP fails:

1. Check whether the provider allows outbound traffic to the required port.
2. Check security groups/firewalls/route tables.
3. Verify the target is supported by the provider on port 587 or 465.
4. Check private vs. public SMTP endpoints matching the active network.
5. Check source IP allowlists if the SMTP server restricts them.

Do not arbitrarily switch from port 587 to 25 or vice versa without checking the SMTP provider's documentation. Changing ports can also alter TLS and authentication requirements.

### Cases That Appear Only Under Scale

When many instances send concurrently:

- The SMTP provider may limit concurrent connections.
- NAT or proxies may exhaust resources.
- DNS resolvers may become overloaded.
- Connection setup times increase.
- Rate limits can trigger SMTP `4xx` in later phases after connecting.

A "timeout" under high load is not necessarily due to too low a timeout setting. You may need **concurrency limits, sensible connection pooling, queuing, and backoff**, rather than raising thread counts indefinitely.

## 21. When DNS Succeeds Yet TCP Still Fails

This is a common situation:

~~~text
DNS:
  smtp.example.com -> 203.0.113.10
  Resolution: SUCCESS

TCP:
  203.0.113.10:587
  Connection: FAILED
~~~

The address **203.0.113.10** in this example is a documentation IP, not a real SMTP address.

Steps to distinguish:

- If **Connection refused**: check listener, port, load balancer, and firewall reject.
- If **Connect timeout**: check firewall drop, routing, NAT, provider egress policy, or unresponsive server.
- If **No route to host**: check routes/interfaces/VPN/network segmentation.
- If only **IPv6** fails: inspect A/AAAA results and connectivity for each address family in a permitted environment.
- If only one IP in a DNS round-robin set fails: one backend or network path to that endpoint may be degraded.

Do not conclude the SMTP provider is healthy based on a successful DNS lookup. DNS, TCP, and SMTP are distinct layers.

## 22. When TCP Opens Without an SMTP Greeting

A TCP connection may succeed while the application still hits a **read timeout** waiting for the initial response.

Possible causes:

- A listener exists, but the SMTP service is overloaded or hung.
- Connection passes through a proxy that does not speak SMTP.
- Routed by mistake to a different service.
- Port expects implicit TLS while the client waits for a plaintext greeting.
- Network appliance accepts TCP then blocks or stalls the data stream.

Wrong TLS mode example:

~~~text
Client connects to port 465
Client waits for plaintext SMTP greeting
Server waits for TLS ClientHello

=> Both sides wait on each other, likely causing a timeout.
~~~

The solution is using **implicit TLS** properly if the server requires it, not raising read timeout endlessly.

Similarly, if the client starts TLS immediately on a port expecting plaintext SMTP before STARTTLS, the handshake may fail or the connection may drop. Verify compatibility between **port, protocol, and TLS mode**.

## 23. When the Server Responds Slowly After Connecting

A **read timeout** can happen in different phases:

- Waiting for SMTP greeting.
- Waiting for EHLO response.
- Waiting for STARTTLS negotiation.
- Waiting for AUTH response.
- Waiting for `MAIL FROM`/`RCPT TO`.
- Waiting for the final reply after DATA.

Each phase has different operational implications. A greeting timeout may indicate an overloaded server; an AUTH timeout may point to the authentication backend; a timeout after DATA creates special difficulty for retries.

### Example After DATA

~~~text
Application                      SMTP server
    |                                 |
    | ---- MAIL FROM / RCPT TO ----> |
    | <--- success reply ----------- |
    | ---- DATA -------------------> |
    | ---- MIME content -----------> |
    | ---- end of DATA ------------> |
    |                                 | may already be queued
    |       250 reply lost            X
    v
SocketTimeoutException
~~~

If the SMTP server already queued the mail yet the reply was lost, retrying the entire message can create a duplicate. Therefore, you cannot see `SocketTimeoutException` and immediately conclude you must resend.

## 24. Retry Policies for DNS, Refused, and Timeouts

For these three error groups, consider the following matrix:

| Failure evidence | Suggested classification | Action |
|---|---|---|
| Wrong/consistently nonexistent hostname | Configuration / permanent | Stop, fix host |
| Temporary DNS resolver timeout | Transient | Retry with backoff |
| Brief DNS SERVFAIL | Transient | Bounded retry and check DNS |
| Stale DNS cache after infra change | Configuration/operational | Check TTL/cache and fix root cause |
| TCP refused due to wrong port | Configuration / permanent | Fix port or listener |
| TCP refused due to brief service restart | Transient | Retry after delay |
| TCP connect timeout before any SMTP bytes sent | Transient | Bounded retry |
| TCP timeout due to permanent firewall drop | Configuration/network policy | Fix egress/routing |
| Read timeout at greeting | Usually transient, needs context | Bounded retry if not submitted |
| Read timeout waiting for final DATA reply | Ambiguous / `UNKNOWN` | Reconcile before retrying |
| Write timeout after DATA began | Potentially ambiguous | Assess bytes sent and replies received |
| TLS handshake failed due to bad certificate | Configuration/security | Fix TLS, do not bypass validation |

**The same `ConnectException` can lead to different policies** once environmental context is known. A refusal from a server restart may self-recover, whereas a refusal from a misconfigured port will repeat forever.

### What Should a Retry Policy Include?

- Delay before trying again.
- Exponential backoff or a clearly defined wait schedule.
- Jitter to prevent many workers from retrying together.
- Max attempts and max age.
- Circuit breaker or worker pause on widespread server failures when appropriate.
- **`UNKNOWN`** status for cases that may have been accepted.
- Notification/event tracing data to prevent application-level duplicates.

Never retry synchronously inside user requests indefinitely; doing so prolongs responses, pins threads, and adds network pressure.

## 25. Exponential Backoff and Jitter

A suggested formula:

~~~text
delay = min(maxDelay, baseDelay * 2^(retryNumber - 1)) + jitter
~~~

Example with `baseDelay` = 30 seconds, `maxDelay` = 20 minutes:

| Retry # | Base delay before jitter |
|---:|---:|
| 1 | 30 seconds |
| 2 | 60 seconds |
| 3 | 120 seconds |
| 4 | 240 seconds |
| 5 | 480 seconds |
| 6 | 960 seconds |
| 7 | 1,200 seconds |

Not every retry count suits every email. For short-lived OTPs, retrying after many minutes may no longer be useful. For invoices or business notifications, persisting the send intent durably and raising operational alerts may be required.

Example delay function:

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public Duration retryDelay(int retryNumber) {
    if (retryNumber <= 0) {
        throw new IllegalArgumentException("retryNumber must be positive");
    }

    long seconds = 30L;
    for (int i = 1; i < retryNumber; i++) {
        seconds = Math.min(1_200L, seconds * 2);
    }

    long jitter = ThreadLocalRandom.current().nextLong(0L, 10L);
    return Duration.ofSeconds(seconds + jitter);
}
~~~

This is a simple example; production policies can use full jitter or decorrelated jitter depending on requirements. Persist the next retry timestamp in an outbox/queue if the application needs to recover across restarts.

## 26. Idempotency and Duplicate Send Risk

When the SMTP outcome is unclear, retrying can cause the recipient to receive two identical emails.

Example:

~~~text
Outbox record N-100
        |
        v
Worker A sends SMTP
        |
        v
SMTP accepts DATA
        |
        X worker loses connection
        |
        v
N-100 stays in PROCESSING
        |
        v
Lease expires, Worker B reprocesses
        |
        v
Recipient may receive a second copy
~~~

Risk-mitigation measures:

1. Use stable **event IDs** and notification keys so two outbox records are not created for the same event.
2. Add unique constraints on event/notification purpose/recipient when appropriate.
3. Record every attempt and SMTP/provider outcome if available.
4. Distinguish pre-submission errors from post-DATA timeouts.
5. Reconcile `UNKNOWN` cases using provider APIs or events when available.
6. Do not treat the same **`Message-ID`** as a guarantee that mailboxes will deduplicate.

An outbox prevents losing **send intent**, but does not by itself turn SMTP into an exactly-once transaction. When reconciliation is impossible, choose a policy based on notification criticality: prioritize avoiding lost notifications vs. avoiding duplicates.

## 27. Distinguishing DNS/TCP Exceptions from SMTP Reply Codes

A **Connection refused** before an SMTP session starts is not an SMTP **`550`** reply. The two mechanisms differ:

~~~text
TCP connection refused:
  Socket connect()
       |
       X  Could not establish connection

SMTP 550:
  TCP connection OK
       |
       v
  SMTP protocol exchange
       |
       v
  Server returns "550 ..."
~~~

| Group | Example | Diagnosis |
|---|---|---|
| DNS error | `UnknownHostException` | Hostname/resolver |
| TCP error | `ConnectException`, `SocketTimeoutException` at CONNECT | Port, route, firewall, listener |
| TLS error | `SSLHandshakeException` | Certificate, protocol, TLS mode |
| SMTP protocol response | `421`, `450`, `550`, `554` | Server reply to an SMTP command |
| SMTP auth error | `MailAuthenticationException` or SMTP AUTH failure | Credentials/permissions |
| Message preparation | `MailParseException`, `MessagingException` | Address, MIME, template |

Do not apply "retry per SMTP 4xx/5xx" to a TCP error that never received an SMTP reply. Conversely, do not troubleshoot DNS when the server already returned an explicit SMTP reply.

## 28. SMTP Debug Logs: Useful but Must Be Restricted

Jakarta Mail has a protocol debug mechanism. When diagnostics are needed in a controlled environment, some configurations enable verbose logging:

~~~yaml
spring:
  mail:
    properties:
      mail:
        debug: true
~~~

**Do not enable SMTP debug broadly in production**. Protocol logs can reveal addresses, hostnames, sending metadata, response content, or other sensitive details. Depending on provider/version, debug may have controls for authentication logging; never assume all secrets are masked automatically.

When debugging:

- Use a test environment and controlled recipients.
- Enable for a short time window.
- Protect logs from unnecessary access.
- Do not send real OTPs or real personal data.
- Disable once the investigation concludes.
- Prefer structured error logs and metrics before enabling protocol traces.

A useful application log usually only needs:

~~~text
notificationId=...
smtpHost=smtp.example.com
smtpPort=587
phase=CONNECT
errorCategory=TCP_CONNECT_TIMEOUT
attempt=2
nextAttemptAt=...
~~~

Do not log **`spring.mail.password`**, tokens, full MIME bodies, or attachment content.

## 29. Example Spring Mail Service Recording Connection Errors

A simple service sending HTML email with a plain-text alternative:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;

import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailService {

    private final JavaMailSender sender;
    private final MailFailureRecorder failureRecorder;

    public NotificationMailService(
            JavaMailSender sender,
            MailFailureRecorder failureRecorder
    ) {
        this.sender = sender;
        this.failureRecorder = failureRecorder;
    }

    public void send(
            String notificationId,
            String recipient,
            String subject,
            String plainText,
            String htmlText
    ) {
        MimeMessage message = sender.createMimeMessage();

        try {
            MimeMessageHelper helper = new MimeMessageHelper(
                    message,
                    true,
                    StandardCharsets.UTF_8.name()
            );
            helper.setFrom("notifications@example.com");
            helper.setTo(recipient);
            helper.setSubject(subject);
            helper.setText(plainText, htmlText);
        } catch (MessagingException ex) {
            failureRecorder.recordPreparationFailure(
                    notificationId,
                    "MIME_PREPARATION_FAILURE"
            );
            return;
        }

        try {
            sender.send(message);
        } catch (MailException ex) {
            failureRecorder.recordSubmissionFailure(
                    notificationId,
                    ex
            );
        }
    }
}
~~~

**MailFailureRecorder** is an application-designed abstraction. The example highlights the two phases **PREPARE** and **SUBMIT**; it does not yet include an outbox, retry worker, or full error model.

In real implementations:

- The failure recorder must classify exceptions and update status via a separate database transaction if needed.
- Do not unconditionally mark `RETRY` merely because `MailException` was caught.
- Explicitly handle success of **`sender.send(message)`** and record submission state.
- Handle exceptions thrown by renderers/attachments if present.
- Proceed with business work only after confirming the notification intent or failure was persisted per policy.
- For important notifications, use an outbox and workers to avoid losing emails on process restarts.

### Note When Errors Occur While Building MIME

**MimeMessageHelper** can throw `MessagingException` when preparing headers/content. These errors are not equivalent to DNS or TCP errors. Do not retry SMTP before fixing the data or content-preparation cause.

## 30. Example of Manual `JavaMailSender` Configuration

If not using Spring Boot auto-configuration, you can instantiate **`JavaMailSenderImpl`** in Java:

~~~java
import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MailSenderConfiguration {

    @Bean
    JavaMailSender mailSender() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("smtp.example.com");
        sender.setPort(587);
        sender.setUsername("configured-user");
        sender.setPassword("configured-secret");
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "10000");
        props.put("mail.smtp.writetimeout", "10000");

        return sender;
    }
}
~~~

In the example, **`configured-user`** and **`configured-secret`** are illustrative strings only. Never hard-code real credentials in source code. Applications should fetch them from protected configuration/secret managers.

If manually creating the bean, confirm it uses the right host, port, and JavaMail properties. **`spring.mail.properties`** may not automatically apply to a custom-configured `JavaMailSenderImpl` bean if code constructs it directly without reading those properties.

With multiple SMTP senders, identify which bean is sending the failing email via logical names or **`@Qualifier`**. Two senders may have different hostnames, ports, TLS settings, and timeouts.

## 31. Diagnostics Through Scenario Examples

### Case A — Only Production Hits `UnknownHostException`

Symptom:

~~~text
Production:
  UnknownHostException: smtp.internal.example

Developer machine:
  DNS lookup succeeded
~~~

Reasoning:

1. Verify production uses the right host and profile.
2. Query DNS from the production pod/VM.
3. Check the private DNS zone and whether the resolver can reach it.
4. Check DNS policies and VPN/private network connectivity.
5. If DNS changed recently, check TTL/cache.

Do not change SMTP username/password before resolving DNS.

### Case B — DNS Succeeds Yet Port 587 Is Refused

Symptom:

~~~text
DNS: OK
TCP smtp.example.com:587: Connection refused
~~~

Check:

- Does the provider support port 587 at that endpoint?
- Is the service running and listening on the port?
- Is there a load balancer, firewall reject, or blocking policy?
- Was a web/API server hostname mistaken for the SMTP server?

Increasing `connectiontimeout` will not make a nonexistent listener start working.

### Case C — Only Containers Report Connect Timeout

Symptom:

~~~text
Laptop: TCP to SMTP host OK
Container: TCP connect timeout
~~~

Check:

- NetworkPolicy egress.
- Cloud security groups/firewalls.
- NAT gateway/route table.
- Outbound port filtering.
- IPv4/IPv6 and the container's resolver.

Only after a clean TCP path exists should you proceed to check TLS and AUTH.

### Case D — TCP Connects Yet Read Times Out Immediately

Symptom:

~~~text
TCP connection established
No SMTP greeting before read timeout
~~~

Possible causes:

- Port speaks implicit TLS while client waits for a plaintext greeting.
- SMTP service is hung or overloaded.
- Proxy accepts the connection yet fails to forward data.
- Connected to the wrong service.

Test with appropriate TLS/SMTP tools before increasing timeouts.

### Case E — Only Emails with Large Attachments Hit Write Timeout

Symptom:

~~~text
Small email: sent fine
Email with large attachment: write timeout
~~~

Investigation path:

- MIME size after Base64 encoding.
- Send time over the actual network path.
- Message size limit of the SMTP provider.
- Upload bandwidth, proxies, and network appliances.
- Whether `mail.smtp.writetimeout` is appropriate.

Consider compressing files or sending a secure download link rather than just raising write timeout. If timeout happens after transmitting data, assess the possibility the message was already received.

### Case F — SMTP Accepted Email Yet Worker Failed to Update Database

Symptom:

~~~text
JavaMailSender.send(message): returns successfully
Update outbox SUBMITTED: database timeout
~~~

This is not an SMTP connection error. The worker needs to recover the state update or reconcile, not resend the email just because the database update failed.

### Case G — Only One Backend/IP in a DNS Group Fails

Symptom:

~~~text
smtp.example.com -> IP A, IP B

IP A: connection succeeded
IP B: connect timeout
~~~

The application may fail intermittently depending on which address gets chosen. Record the actual target IP if infrastructure allows, inspect load balancers/routes, and contact the provider. Do not pin IPs in production config if the provider requires DNS or may rotate endpoints.

## 32. Testing Network Scenarios in Test Environments

To catch errors before production, maintain integration tests or an SMTP sandbox simulating:

| Scenario | What to verify |
|---|---|
| Nonexistent host | App records DNS error and does not treat it as recipient error |
| Closed port | Connection failure occurs; error message is normalized |
| Dropped connection | Finite connect timeout, worker does not hang forever |
| Server sends no greeting | Read timeout is recorded |
| Wrong TLS mode | Configuration fails; validation is not disabled to bypass |
| Provider returns temporary 421 | Retries per policy with backoff |
| Timeout after DATA | Marked `UNKNOWN`, not unconditionally resent |
| SMTP accepted, DB update fails | Does not auto-resend due to database error |
| Only one recipient in batch fails | Already-accepted recipients are not retried |

Some mock/test SMTP servers can capture MIME without sending to the Internet. To simulate losing a connection after DATA, you need a test server capable of controlling SMTP flow or a test proxy built for that purpose.

**Do not test connection failures against production SMTP by intentionally sending mail floods or arbitrarily disabling firewalls.** Testing must run in authorized environments with dummy data.

## 33. Monitoring Metrics and Alerting

Metrics should be split by error layer:

| Metric | Meaning |
|---|---|
| **`mail_dns_failure_total`** | Count of hostname resolution failures |
| **`mail_connect_refused_total`** | Count of TCP refused errors |
| **`mail_connect_timeout_total`** | Count of connect timeouts |
| **`mail_read_timeout_total`** | Count of read timeouts |
| **`mail_write_timeout_total`** | Count of write timeouts |
| **`mail_tls_failure_total`** | Count of TLS negotiation failures |
| **`mail_auth_failure_total`** | Count of SMTP authentication failures |
| **`mail_submission_success_total`** | Count of confirmed mail submissions |
| **`mail_unknown_outcome_total`** | Count of indeterminate submission outcomes |
| **`mail_outbox_oldest_pending_age`** | Age of oldest pending notification |

Do not count only total errors. If you simultaneously observe:

- DNS failures rising: inspect resolver, hostname, and DNS changes.
- Refused rising: inspect server listeners, ports, and firewall rejects.
- Connect timeouts rising: inspect egress, routes, and network capacity.
- Read timeouts rising: inspect SMTP response latency and failing phase.
- `UNKNOWN` rising: inspect networking at DATA/response stage and reconciliation workflow.

### Recommended Log Fields

~~~text
notificationId=...
senderId=transactional-mail
smtpHost=smtp.example.com
smtpPort=587
errorCategory=DNS_FAILURE
sendPhase=RESOLVE
attempt=1
elapsedMs=...
~~~

Do not log passwords, OTPs, token-bearing links, MIME bodies, attachment contents, or full customer addresses unless genuinely needed and access-controlled.

### Threshold-Based Alerting

For example, systems can alert when:

- DNS errors occur continuously across multiple instances.
- SMTP connect timeouts spike right after deployment.
- One sender has a high refused rate while others are normal.
- Outbox pending age exceeds SLA.
- Many messages enter `UNKNOWN` without reconciliation.
- Retry queue grows faster than processing throughput.

Alert thresholds must match real traffic to avoid false alarms when email volume is very small.

## 34. Misconceptions to Avoid

| Misconception | Accurate understanding |
|---|---|
| "DNS resolving an IP means SMTP works" | DNS is only address lookup; TCP/TLS/AUTH can still fail |
| "Ping failing means port 587 is blocked" | ICMP and TCP are two different protocols |
| "Connection refused means SMTP rejected the email" | Refused usually occurs at TCP, before SMTP commands |
| "Connect timeout and read timeout are the same" | One occurs establishing the connection, the other waiting for data |
| "Raising timeouts fixes a wrong host" | Wrong hostname/port requires fixing configuration |
| "DNS error means recipient's MX is wrong" | Submission apps usually look up the configured SMTP host |
| "Port 465 always uses STARTTLS" | Port 465 usually requires implicit TLS |
| "Port 587 always uses implicit TLS" | Port 587 usually uses SMTP followed by STARTTLS |
| "`MailSendException` is always retryable" | Need cause, send phase, and SMTP reply |
| "Read timeout proves the email was not sent" | After DATA, the server may have already accepted it |
| "`send()` not throwing means it reached the Inbox" | Only confirms submission succeeded at the handled hop |
| "Retrying once cannot duplicate because of `Message-ID`" | SMTP does not guarantee deduplication by `Message-ID` |

## 35. Quick Diagnostic Checklist

When encountering DNS, timeout, or refused errors, follow this sequence:

1. **Identify root exception**: `UnknownHostException`, `ConnectException`, `SocketTimeoutException`, or another TLS/SMTP error?
2. **Cross-check environment**: instance, profile, sender bean, and deployment timing.
3. **Verify effective host and port**: do not print credentials to logs.
4. **Test DNS where the app runs**: A/AAAA, resolver, and cache.
5. **Test TCP to `host:port`**: distinguish refused, timeout, and no route.
6. **Check firewall/egress**: cloud, container, network policies, NAT, proxies.
7. **Check TLS mode**: STARTTLS vs. implicit TLS, certificates, and hostname.
8. **Check timeouts**: `connectiontimeout`, `timeout`, `writetimeout`.
9. **Identify failure phase**: CONNECT, GREETING, AUTH, `RCPT TO`, DATA, or waiting for final reply.
10. **Set proper retry policy**: retry transient pre-submission errors; halt config errors; reconcile `UNKNOWN`.
11. **Monitor outbox and individual notifications**: avoid retrying whole batches or sending duplicates.
12. **Observe after fixing**: error rate, latency, pending age, and delivery outcomes.

This is a diagnostic flow for choosing actions. Not every item is needed once the cause is clearly established at an earlier step.

## 36. Key Takeaways

In Spring Framework Mail, **DNS errors**, **Connection refused**, and **timeouts** occur at different phases of the SMTP connection process:

- **DNS failure** indicates the app could not resolve the SMTP hostname or hit a resolver error.
- **Connection refused** usually indicates the TCP connection was rejected; inspect host, port, listener, and firewall rejects.
- **Connect timeout** usually indicates the TCP path did not respond in time; inspect routing, network policy, NAT, and outbound filtering.
- **Read/write timeout** occurs once a connection exists yet data exchange fails to complete within bounds, and must consider the SMTP phase.

Configure finite **`mail.smtp.connectiontimeout`**, **`mail.smtp.timeout`**, and **`mail.smtp.writetimeout`**, test DNS and TCP from the exact application runtime environment, match STARTTLS/implicit TLS to the port, and read the full Spring/Jakarta Mail exception chain.

When implementing retries, **retry only when the error is likely transient and sufficient evidence shows the mail was not accepted**. If a timeout happens after DATA may have reached the SMTP server, mark **`UNKNOWN`** and reconcile before resending. Separate submission status from delivery status, log normalized error records, and track notifications with idempotency/outbox when needed.

**Diagnosing the right error layer before changing config or retrying** keeps email systems reliable, avoids prolonged transactions, avoids futile retries, and reduces duplicate-send risks.


