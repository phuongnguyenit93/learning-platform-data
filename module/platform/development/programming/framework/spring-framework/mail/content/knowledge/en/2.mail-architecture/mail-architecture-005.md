# DNS MX and How Receiving Mail Domains Are Found

When an application sends an email to `linh@example.org`, it knows the recipient address, but does not yet know which server accepts email for the domain `example.org`. The recipient address does not contain the IP address or network port of the receiving mail server. A mechanism is needed to publish routing information so the sending server can find the right place to transfer the message.

**DNS MX (Mail Exchanger) records** solve the part about finding where a domain receives mail: they specify the **hostnames published by that domain to accept email** and the priority order for attempting delivery. MX is a critical piece of transferring mail between SMTP servers, but by itself it does not verify that a mailbox exists, does not guarantee delivery, and does not decide whether the message is marked as spam.

In the context of **Spring Framework Mail**, distinguish clearly between the email's path inside the application and its path across the Internet. The application typically connects to a configured SMTP server via `JavaMailSender`. It is that relaying SMTP server or the infrastructure behind it that performs the recipient domain's MX lookup to forward the message onward.

## 1. Why Are DNS MX Records Needed?

An email address typically has the form:

~~~text
linh@example.org
│    └── Receiving mail domain: example.org
└─────── Mailbox identifier within domain: linh
~~~

From the part after `@`, the sending system identifies the **receiving domain**. However, a domain's website and its email receiving system can live in completely different places:

- `example.org` might serve its website from one web server.
- Email sent to `@example.org` might be accepted by a different email provider.
- A domain might declare multiple mail servers for redundancy or traffic distribution.

Therefore, resolving `example.org` only to the website's IP address is not enough to find where to send email. DNS allows a domain to publish dedicated **MX records** for receiving mail.

| Component | Purpose | Illustrative Example |
| --- | --- | --- |
| `A` | Maps a hostname to an IPv4 address | `mx1.mail.example.net → 192.0.2.10` |
| `AAAA` | Maps a hostname to an IPv6 address | `mx1.mail.example.net → 2001:db8::10` |
| `MX` | Specifies the mail-receiving hostname for a domain along with priority | `example.org → 10 mx1.mail.example.net` |
| `TXT` | Stores text data, such as SPF policies or domain verification info | `v=spf1 ...` |

The addresses `192.0.2.10` and `2001:db8::10` above are documentation-reserved addresses, not real mail servers. **MX points to a hostname**, and that hostname is then resolved to an IP address via `A` or `AAAA`.

## 2. How Does an Email Travel from Spring to the Receiving Domain?

Suppose a Spring system sends a notification to `linh@example.org` and uses a provider's SMTP relay. The path typically looks like:

~~~mermaid
flowchart TD
    A["Spring Application"] -->|"JavaMailSender.send()"| B["Configured SMTP relay"]
    B --> C["Look up DNS MX for example.org"]
    C --> D["Receive list of hostnames and priorities"]
    D --> E["Look up A/AAAA for MX host"]
    E --> F["Connect via SMTP to receiving server"]
    F --> G["Receiving server checks recipient/policy"]
    G --> H["Mailbox or downstream processing"]
~~~

The flow can be explained step by step:

1. **Application constructs the message.** Java code prepares the sender, recipient, subject, and body. `JavaMailSender` sends the message to the SMTP server configured for the application.
2. **Sending server identifies the destination domain.** When relaying externally, the sending system reads the domain from the recipient address in the **SMTP envelope**, such as `example.org` from `RCPT TO:<linh@example.org>`.
3. **Sending server queries DNS.** It requests `MX` records for `example.org`, typically through a DNS recursive resolver. The resolver may answer from cache or query authoritative DNS servers.
4. **Receive MX list.** The result includes the receiving mail server hostnames and each server's priority number. **Lower** numbers have higher priority.
5. **Resolve network addresses.** The sending server looks up `A`/`AAAA` for the selected MX hostname to get a reachable IP address.
6. **Run the SMTP session.** The sending server connects to the receiving server, usually over TCP **port 25** for server-to-server mail transfer, then exchanges SMTP commands and transmits the message if accepted.
7. **Receiving server processes it.** Destination infrastructure decides whether to accept the recipient, applies anti-abuse policies, stores the message in the mailbox, or forwards it internally.

The sending system may use multiple relay hops and intermediate queues. The diagram illustrates cross-domain routing principles, not that every email passes through exactly one server.

### The Domain in the SMTP Envelope Is the Routing Input

An email may have display headers:

~~~text
From: Notifications <notify@example.com>
To: Linh <linh@example.org>
Subject: Registration confirmation
~~~

Yet the SMTP session has separate *envelope* information, for example:

~~~text
MAIL FROM:<bounce@example.com>
RCPT TO:<linh@example.org>
~~~

The address in `RCPT TO` is where the sending server must transfer the message; MX is looked up based on this recipient address's domain. The `From` and `To` fields in the headers serve message presentation and can differ from envelope information, such as with forwarding, mailing lists, or bounce handling. Therefore, you should not assume the system finds MX solely by reading the `To` field in the email body/headers.

## 3. Structure and Reading of MX Records

Suppose an administrator publishes the following illustrative DNS records:

~~~dns
example.org.  3600  IN  MX  10 mx1.mail.example.net.
example.org.  3600  IN  MX  20 mx2.mail.example.net.

mx1.mail.example.net.  3600  IN  A     192.0.2.10
mx2.mail.example.net.  3600  IN  A     192.0.2.20
~~~

This is a **hypothetical record set for learning**, not the live DNS query output of `example.org` or `example.net`.

| Record Part | Meaning |
| --- | --- |
| `example.org.` | Receiving mail domain the MX record applies to. The trailing dot denotes a fully qualified domain name (FQDN). |
| `3600` | TTL, how long resolvers may cache the result, in seconds. |
| `IN` | Internet DNS record class. |
| `MX` | Mail Exchanger record type. |
| `10` or `20` | `preference` value: a lower number has higher priority. |
| `mx1.mail.example.net.` | Hostname designated to receive mail; must resolve to an IP address. |

With this data, the sending system **prefers trying** `mx1.mail.example.net` first because 10 is lower than 20. If it cannot transfer mail via the preferred server according to SMTP rules and retry policy, it may try `mx2.mail.example.net`.

### Preference Is Not a Load-Splitting Percentage

The values 10 and 20 do not mean 10% and 20%, nor are they port numbers. They only express **priority order**.

- `MX 10 mail-a.example.net` and `MX 20 mail-b.example.net`: prefer `mail-a`.
- `MX 10 mail-a.example.net` and `MX 10 mail-b.example.net`: two servers with equal priority. The sending system should distribute/randomize the attempt order in accordance with SMTP rather than always hitting one fixed host.
- Having multiple MX records **does not by itself guarantee high availability**: the backup server must also be configured to accept mail for the domain, be authorized to accept, and handle messages properly.

TTL values do not force every server worldwide to see changes immediately. Resolvers may keep using cached records while valid. When migrating email providers, changing MX must account for cache delay and the possibility that mail continues arriving at the old system for some time.

## 4. Rules for Finding Target Servers When MX Exists, Is Missing, or Fails

SMTP's general principle when transferring mail to a domain is to look up MX and identify connectable hosts, though several distinct cases must be separated.

### Case A — Domain Has One or More Valid MX Records

The sending system selects servers by priority, resolves MX hostnames into `A` and/or `AAAA` addresses, and attempts SMTP connections. If one connection fails, it may try another address or MX host. Temporary errors may also cause the message to be queued for later retry.

**Note:** if a domain publishes MX but that MX host has no usable IP address, that is an MX configuration or availability issue. You cannot arbitrarily ignore MX and switch to the website's IP address at the apex domain.

### Case B — No MX Record, Yet the Domain Exists

Under traditional SMTP rules, when lookup succeeds but the domain **has no MX**, the sending system may apply the **implicit MX** rule: look up `A`/`AAAA` of the **recipient domain itself** and attempt SMTP to the resulting address.

Illustrative example:

~~~dns
example.org.  3600  IN  A  192.0.2.30
; No MX record declared for example.org.
~~~

In that case, the sending system may try connecting via SMTP to `192.0.2.30` of `example.org`. This **does not mean a website running at that IP definitely accepts mail**. The server must still run an SMTP service and be configured to accept email for that domain.

Having no MX differs from DNS failing. The fallback applies only when the query response validly concludes that the domain publishes no MX.

### Case C — Domain Actively Refuses Mail via Null MX

A domain used only for a website, documentation, or technical infrastructure may want to state explicitly that it **does not accept email**. It can publish *Null MX* per RFC 7505:

~~~dns
example.org.  3600  IN  MX  0 .
~~~

The dot `.` is a special MX target, not a hostname to connect to. A Null MX configuration means the domain declares it has no incoming email service; standards-compliant sending systems will not fall back to implicit MX and attempt delivery.

Null MX is a standalone record and should not be mixed with normal receiving MX records. If the goal is to receive mail, do not use Null MX.

### Case D — DNS Errors or Domain Not Found

Distinguish carefully:

- **`NXDOMAIN`:** the queried domain does not exist per DNS response. This is not equivalent to a valid domain without MX.
- **No MX (`NOERROR`/no MX data):** the domain is valid but has no MX-type records. Implicit MX may be considered if conditions are met.
- **`SERVFAIL`, timeout, or temporary DNS error:** the mail route cannot be reliably determined. Sending servers typically keep the message in queue and retry per policy rather than concluding the domain has no MX.
- **MX points to a hostname that does not resolve to an address:** route discovery can fail even if the root domain has an `A` record, because a declared MX must lead to a connectable host.

The final outcome also depends on SMTP responses, queue retention time, and sending server policy. Do not attribute every mail-receipt failure to a missing MX record.

### An Important Rule About MX Target Names

An MX target value must be a **hostname**, not a raw IPv4/IPv6 address. The hostname used as an MX target should also not be a `CNAME` alias; per DNS specifications, an MX target must point to a name that resolves directly to appropriate addresses rather than relying on CNAME. For instance, the following is an invalid data type:

~~~text
example.org. IN MX 10 192.0.2.10
~~~

Declare a hostname in MX, then create `A`/`AAAA` records for that hostname. This also allows the server's IP address to change independently of mail routing records.

## 5. Distinguishing DNS MX from SMTP Ports 25, 587, and 465

A common misconception is thinking MX supplies port numbers or SMTP login parameters. **MX only publishes hostnames and priority levels; it contains no port, username, password, or TLS mode.**

| Connection | Common Port | Purpose |
| --- | ---: | --- |
| SMTP between sending server and receiving server (mail transfer) | `25` | Servers transfer mail to receiving servers found via MX. |
| SMTP submission from application/mail client to provider | `587` | Application submits mail to relay, typically using authentication and STARTTLS upgrade. |
| Submission over TLS from the start (implicit TLS) | `465` | Another submission option when supported by the provider. |

Ports are common conventions; actual configuration must match the service in use. An internal SMTP service may use another port within a private network.

**Routing through a relay** is the common scenario for Spring Framework Mail:

~~~mermaid
flowchart LR
    A["JavaMailSender"] -->|"SMTP submission: 587/465"| B["SMTP relay"]
    B -->|"DNS MX + SMTP transfer: usually 25"| C["Recipient domain's MX"]
~~~

In this case, the application **does not need to look up MX for each recipient**. It only needs to connect to the configured SMTP hostname, such as `smtp.provider.example`; the relay is responsible for locating the destination domain and transferring the message. This is why seeing no MX query code inside a Spring application is completely normal.

## 6. Specific Role of Spring Framework Mail

Spring Mail provides interfaces such as `JavaMailSender` and message construction helpers. With Spring Boot, sending configuration typically looks like:

~~~properties
spring.mail.host=smtp.provider.example
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000
~~~

The hostname `smtp.provider.example` is illustrative only. Deployers must substitute the submission server provided by their vendor and set appropriate environment variables. `spring.mail.host` specifies **the server the application connects to for sending mail**, not the recipient domain's MX. Resolving this hostname via DNS to open a network connection is a different operation from looking up MX for `example.org`.

Example of sending a notification:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class OrderMailService {
    private final JavaMailSender mailSender;

    public OrderMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderNotice(String recipient, String sender) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(sender);
        message.setTo(recipient);
        message.setSubject("Order has been recorded");
        message.setText("The system has received your order.");

        mailSender.send(message);
    }
}
~~~

Sending code does not need to extract the domain from `recipient` and invoke DNS MX itself. When `mailSender.send(message)` finishes, the result reflects only the handoff step to the connected SMTP infrastructure; **it does not prove the recipient has the message in their Inbox**.

If an application tries to deliver directly to each domain's MX servers instead of going through a relay, it must take on SMTP routing logic, DNS interactions, retry queues, bounce handling, security, and deliverability itself. That is normally the responsibility of a dedicated mail transfer agent (MTA), not the default goal of `JavaMailSender`.

## 7. Inspecting MX and Server Addresses Yourself with DNS Tools

Command-line tools can show which receiving mail servers a domain publishes. The examples below are **query syntax**, not claims about live DNS results at a specific moment.

### On Linux/macOS with `dig`

~~~bash
dig MX example.org
dig +short MX example.org
~~~

In the first query, the `ANSWER SECTION` (if present) shows MX records; depending on resolver and domain, additional information may appear. The `+short` option gives a more compact view of MX entries.

Example **hypothetical output**:

~~~text
10 mx1.mail.example.net.
20 mx2.mail.example.net.
~~~

Once you know the MX hostname, query its corresponding address:

~~~bash
dig A mx1.mail.example.net
dig AAAA mx1.mail.example.net
~~~

When checking authoritative DNS servers, start from the domain's `NS` records and query those servers directly; do not mistake cached resolver responses for records already updated at the source.

### On Windows with PowerShell

~~~powershell
Resolve-DnsName -Name example.org -Type MX
Resolve-DnsName -Name mx1.mail.example.net -Type A
Resolve-DnsName -Name mx1.mail.example.net -Type AAAA
~~~

Or use `nslookup` on supported systems:

~~~text
nslookup -type=mx example.org
~~~

A sensible inspection workflow is **check MX first → read hostname and priority → check A/AAAA of hostname → check SMTP and provider config if still failing**. Checking MX alone is insufficient to diagnose the entire mail path.

## 8. MX Does Not Replace SPF, DKIM, DMARC, or TLS

MX tells **where email can be transferred to**. Other records and mechanisms solve independent questions:

| Mechanism | Primary Question It Solves | Relationship to MX |
| --- | --- | --- |
| MX | Which servers are advertised to receive email for the domain? | Foundation for finding where to send mail across domains. |
| SPF | Which servers are permitted to send email with the declared envelope-domain identity? | Usually published via DNS TXT; MX is not used to infer all valid senders. |
| DKIM | Do content and certain headers carry a cryptographic signature from the signing domain? | Public key is queried via DNS; does not determine receiving servers. |
| DMARC | Do SPF/DKIM align with the displayed `From` domain and the domain's policy? | Usually uses DNS TXT; lets domains publish auth policies and reporting. |
| STARTTLS | Can the SMTP connection be encrypted during transit? | Operates in the SMTP session; MX alone does not guarantee TLS. |
| MTA-STS / DANE | Can selection/establishment of TLS connections to MX be strengthened? | Complementary mechanisms requiring separate infrastructure and configuration. |

A domain with valid MX can still have its display identity spoofed if proper protections are absent; conversely, configuring SPF/DKIM/DMARC for sending does not mean the domain has receiving mailboxes. For two-way email operations, you normally need to configure **both receiving routes and sending identity**.

## 9. Common Configuration and Operational Scenarios

### 9.1. Domain Has a Website, Yet Receives No Email

A working website proves the domain resolves for HTTP/HTTPS; it **does not confirm MX or receiving SMTP services are correct**. Check whether the domain has MX, whether the MX target has IP addresses, whether port 25 and the SMTP server are running, and whether the provider is actually configured to accept mail for the domain.

### 9.2. MX Created, Yet Mailbox Not Created

MX only locates the server. The receiving server can reject `RCPT TO` if mailbox `linh` does not exist, or route mail to another receiving policy. Create the mailbox, alias, forwarding route, or corresponding receiving configuration in the destination system.

### 9.3. Two MX Records Exist, Yet Failover Still Fails

The second MX server does not automatically become a replica of the first MX server. It may not accept the domain properly, may not know where to store/forward mail, or may be blocked by a firewall. For effective failover, prepare both sides: **appropriate DNS records and genuinely compatible receiving infrastructure**.

### 9.4. MX Just Changed, Yet Mail Still Goes to Old Provider

Resolvers may still hold records per TTL; some mail servers also have queued messages to drain. When migrating email systems, keep the old provider running during a controlled transition window, check DNS from multiple sources, and inspect logs on both old and new infrastructure if accessible.

### 9.5. Spring Reports Send Succeeded, Yet User Does Not See the Mail

Check SMTP relay delivery logs and status first, then use the provider's dashboard or delivery response codes to see if the message bounced, was rejected, delayed, or placed in spam. Checking only the destination domain's MX cannot identify where the failure occurred. `JavaMailSender` provides no mechanism to track open status or Inbox placement.

### 9.6. Spring's SMTP Relay Works, Yet Application's Own Domain Has No MX

If an application only **sends outbound mail** from an address authorized by the provider, sending can work through the SMTP relay even if that domain has not configured receiving MX records. However, if you want recipients to reply to emails or receive bounces in your mailbox, the domain needs an appropriate receiving route. Provider authentication rules and policies may also impose extra requirements on the sending domain.

## 10. A Decision Diagram to Remember

When a mail server prepares to transfer a message to `user@domain.example`, you can picture finding the receiving route like this:

~~~mermaid
flowchart TD
    A["Extract domain from RCPT TO"] --> B["Look up DNS MX"]
    B --> C{"DNS result?"}
    C -->|"Normal MX present"| D["Sort by preference"]
    D --> E["Look up A/AAAA of MX target"]
    E --> F["Attempt SMTP to receiving server"]
    C -->|"No MX, valid domain"| G["Try A/AAAA of domain itself"]
    G --> F
    C -->|"Null MX"| H["Domain declares it does not accept email"]
    C -->|"Temporary DNS error"| I["Defer and retry per policy"]
    C -->|"Domain does not exist"| J["No valid receiving route"]
~~~

This diagram focuses only on route discovery. After connecting, the receiving server can still accept, defer, or reject the message depending on recipient address and operational policies.

A short self-check exercise:

1. `example.org` has `MX 5 mx-a.example.net` and `MX 50 mx-b.example.net`. Which server is tried first? **`mx-a.example.net`**, because its preference value is smaller.
2. `example.org` has no MX, but has `A`. Is email guaranteed to be received? **No**; SMTP has an implicit MX mechanism, yet the server at that IP must actually accept mail.
3. `example.org` has `MX 0 .`. Should you try sending to the domain's web address? **No**; Null MX declares the domain does not accept email.
4. A Spring application uses `spring.mail.host=smtp.provider.example`. Which component usually looks up the recipient's MX? **The provider's SMTP relay** when transferring mail externally.

## 11. Reconnecting to Spring Framework Mail Architecture

Across the entire email-sending journey, **Spring Framework Mail** helps the application build messages and submit them to a configured SMTP server. **DNS MX** serves the routing step when a sending server needs to find where a destination domain receives email. Then **SMTP and email infrastructure** perform mail transfer, recipient checks, and delivery status handling.

Keeping the three parts distinct — **creating send requests in Spring**, **finding receiving domains via DNS MX**, and **delivering via SMTP** — prevents confusing application configuration errors, DNS errors, and receiving infrastructure errors. This also provides the foundation for exploring SMTP relays, email DNS, domain authentication, and reliable mail-sending strategies in greater depth.
