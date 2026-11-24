# Configuring protocol debug and its impact on logs

When integrating **Spring Framework Mail** in a **Spring Boot** application, an "unable to send email" error can come from many layers: address data, MIME content, Spring configuration, TCP connection, TLS, SMTP login, mail-sending commands, or the provider's policy. Ordinary application logs sometimes show only a single line such as **MailSendException: Mail server connection failed**. To observe the actual exchanges between the SMTP client and the mail server, Jakarta Mail provides **protocol debug** mode.

This mode is very useful when diagnosing, but it significantly changes the **volume and kind of data appearing in logs**. A trace can show the server in use, STARTTLS capability, AUTH responses, sender/recipient addresses, and details from the sending process. Enabling debug too broadly or for too long can leak information, clutter operational logs, and increase storage costs.

This lesson explains how to enable protocol debug through Spring Boot configuration, how to read SMTP signals, the difference between framework logs and protocol traces, and how to use traces safely when troubleshooting incidents.

## 1. First, distinguish three kinds of observability information

A Spring Boot application can simultaneously produce:

1. **Application business logs**: for example, a mail job was created, a template was selected, notification sending started, or the job was moved to retry state.
2. **Spring and mail-library logs**: for example, exception classes, error causes, or component/transport activity.
3. **SMTP protocol debug**: detailed information about the conversation between the SMTP client and the mail server during a sending phase.

These three layers serve different questions:

| Observability layer | Main question | Example information |
| --- | --- | --- |
| Business logs | "Which send job failed and how was the business affected?" | **mailJobId**, email type, attempt, status |
| Spring Mail/transport logs | "Which component and operation raised the exception?" | **MailAuthenticationException**, **MailSendException**, cause |
| Protocol debug | "Which command did the SMTP server receive and how did it respond?" | **EHLO**, **STARTTLS**, **AUTH**, **MAIL FROM**, **RCPT TO**, **DATA**, and **2xx/4xx/5xx** codes |

**Enabling DEBUG logging for Spring is not automatically equivalent to enabling Jakarta Mail's protocol debug.** Conversely, enabling **mail.debug** also does not create business tracking, job IDs, or delivery statuses if the application has not designed that data.

### Sending flow with observable points

~~~text
HTTP request / scheduled job
      |
      | [APPLICATION LOG] mailJobId, status, attempt
      v
Spring service -> JavaMailSender.send(...)
      |
      | [SPRING LOG / EXCEPTION] prepare, parse, send
      v
Jakarta Mail SMTP transport
      |
      | [PROTOCOL DEBUG]
      | DNS/TCP -> greeting -> EHLO -> STARTTLS
      | -> AUTH -> MAIL FROM -> RCPT TO -> DATA
      v
SMTP server accepts or rejects
      |
      | [PROVIDER EVENT if any]
      v
Subsequent delivery steps
      |
      v
Destination mailbox / bounce / delay / filtering
~~~

An SMTP trace line only proves what the transport **observed at that moment**. For example, **250** after the server accepts the message content is a signal that the submission step completed, not proof that the mail has appeared in the Inbox or that the recipient has read it.

## 2. Enabling protocol debug via Spring Boot's application.yml

Spring Boot allows passing Jakarta Mail properties through **spring.mail.properties**. The key property is **mail.debug**.

Example configuration for a diagnostic environment:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: demo-smtp-user
    password: "set-using-a-secret-provider"
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 3000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000
      "[mail.debug]": true
      "[mail.debug.auth]": false
~~~

The domains, account, and timeout values are only illustrative. A real application needs to use the SMTP details, TLS method, and timeout limits suitable for the provider. The password must be obtained from a secure secret configuration; do not store real passwords in source code or documentation.

Meaning of the related settings:

| Property | Purpose |
| --- | --- |
| **spring.mail.host** | The SMTP server the application intends to connect to |
| **spring.mail.port** | The SMTP port, for example 587 when using STARTTLS per provider configuration |
| **mail.smtp.auth** | Requires performing SMTP AUTH per configuration |
| **mail.smtp.starttls.enable** | Allows the transport to upgrade the connection with STARTTLS |
| **mail.smtp.starttls.required** | Requires STARTTLS to succeed before continuing in this configuration |
| **mail.smtp.connectiontimeout** | TCP connection timeout, usually in milliseconds |
| **mail.smtp.timeout** | Timeout for reading responses/data from the socket |
| **mail.smtp.writetimeout** | Timeout when writing over the socket |
| **mail.debug** | Enables Jakarta Mail session/transport debug output |
| **mail.debug.auth** | Adjusts whether AUTH information can appear in debug on supporting implementations; should be kept **false** |

In YAML, the **"[mail.debug]"** form is a key of the **spring.mail.properties** map. The square brackets are placed in quotes to avoid confusion in how Spring Boot binds keys containing dots. The desired result is a Jakarta Mail property named literally **mail.debug**.

**There is no Spring Boot property named spring.mail.debug with the same guaranteed meaning in every configuration.** The explicit way to pass the property to Jakarta Mail is using **spring.mail.properties["mail.debug"]**.

### Why set mail.debug.auth: false?

AUTH traces can contain sensitive information, especially if someone enables a more detailed trace level or uses an implementation that permits printing login information. **mail.debug.auth** is used by some Jakarta Mail SMTP implementations to control debugging of the authentication process; **false** is the cautious choice and should not be switched to **true** on systems holding real credentials.

Even when **mail.debug.auth=false**, do not treat the trace as harmless: it can still contain addresses, hostnames, server responses, internal identifiers, and at some trace levels/implementations may include parts of the mail data. Log protection policies must apply to **the entire trace**, not just the AUTH lines.

## 3. Enable debug only in a diagnostic profile

During development, you can create a separate profile, for example **mail-debug**, to enable protocol debug intentionally.

**application.yml** holds the normal configuration:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: demo-smtp-user
    password: "set-using-a-secret-provider"
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 3000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000
      "[mail.debug]": false
~~~

**application-mail-debug.yml** holds only the parts that need overriding when investigating:

~~~yaml
spring:
  mail:
    properties:
      "[mail.debug]": true
      "[mail.debug.auth]": false

logging:
  level:
    org.springframework.mail: DEBUG
~~~

When running the application with the **mail-debug** profile active, Spring Boot loads the corresponding profile configuration. Example startup argument:

~~~text
--spring.profiles.active=mail-debug
~~~

Having a separate profile makes it clear which environment has tracing enabled and avoids accidentally leaving protocol debug in the default production configuration.

If the application uses multiple profiles at once, you need to understand Spring Boot's configuration precedence and rules. A property overridden in a higher-precedence source can change the value of **mail.debug**. When a configuration "has no effect", check the application's **effective configuration**, active profiles, and whether the Session configuration is supplied by another source.

### When the JavaMail Session is configured externally

Some applications use **Spring Boot spring.mail.jndi-name** to obtain the **Jakarta Mail Session** from JNDI/the application server, or declare the **JavaMailSender** bean themselves. In those cases, the actual configuration source of the Session may lie outside the commonly used **spring.mail.properties**.

If you enable **mail.debug** in YAML and see no trace, you need to identify **which Session JavaMailSender is using**, and who creates and manages it, instead of continuing to add **logging.level** settings at random.

## 4. logging.level and mail.debug are two different switches

Spring Boot has an application logging system, usually via SLF4J and a backend like Logback. You can adjust the log level by logger name:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.mail: DEBUG
~~~

The configuration above increases the detail level for loggers under **org.springframework.mail** when matching log calls occur. It **does not necessarily** cause Jakarta Mail to print a transcript of SMTP commands.

Meanwhile:

~~~yaml
spring:
  mail:
    properties:
      "[mail.debug]": true
~~~

tells the Jakarta Mail **Session** to turn on debug mode. Depending on the version and implementation (for example JavaMail/Jakarta Mail or Angus Mail), debug data may go through the Session's debug stream and/or the library's own logger infrastructure.

| Configuration | Target | Guaranteed to show SMTP commands? |
| --- | --- | --- |
| **logging.level.root=DEBUG** | Increases logs for many application loggers | **No**; still depends on the mail library and logger |
| **logging.level.org.springframework.mail=DEBUG** | Increases logs for the Spring Mail package if emitted | **No**; does not automatically enable Jakarta Mail protocol debug |
| **spring.mail.properties["mail.debug"]=true** | Enables Jakarta Mail Session/transport debug | **Usually provides appropriate transport traces**, depending on implementation |
| Provider debug logging via **java.util.logging** or implementation logger | Observes the internals of the transport library | Depends on logger name, level, handler/bridge, and version |

Do not treat **logging.level.root=DEBUG** as a general cure-all for mail errors. It can produce huge log volume from the entire application while still missing the desired SMTP details.

### Why are there traces without Spring's log formatting?

**Jakarta Mail Session** supports its own debug output, which usually writes to **System.out** by default (or is configured differently by the provider/application). Therefore, you may see lines starting with **DEBUG:** or **DEBUG SMTP:** in the console **without timestamp, thread, MDC/correlation ID, and Logback formatting** like Spring logs.

For example, the two lines below belong to two mechanisms:

~~~text
2026-11-12 10:00:00.001 INFO  [mail-worker-1] MailJobService -
  Submitting mailJobId=MAIL-782 attempt=1

DEBUG SMTP: trying to connect to host "smtp.example.test", port 587
~~~

The first line is written by the application logger using its own pattern; the second line may come from the mail library's debug output. Both appearing in the terminal **does not mean they use the same logging pipeline**.

### Where does System.out appear when running Spring Boot?

Depending on deployment, debug output may appear in:

- The IDE console when running the application locally.
- Standard output of the Java process.
- Logs collected from stdout by the Docker or Kubernetes container runtime.
- Logs forwarded by a process manager, runtime platform, or cloud logging collector.
- Test/CI logs if running integration tests with mail debug enabled.

Consequently, a debug configuration that seems intended only for developers can send protocol information into a **centralized logging system** with wider retention and access permissions than expected.

If you want to route debug output through SLF4J/Logback, you need a bridge mechanism or corresponding Session/provider output configuration. **Do not assume that adjusting logging.level will automatically turn a Jakarta Mail PrintStream into logs with MDC.** In particular, forwarding protocol lines into a logger yourself must come with access control, sensitivity classification, and data-masking mechanisms.

## 5. How is an SMTP debug session interpreted?

After enabling **mail.debug**, depending on the implementation and trace level, an output snippet might show a sequence like the following. This is a **shortened example with sensitive data hidden**, not the exact transcript of every server or every Jakarta Mail version:

~~~text
DEBUG SMTP: trying to connect to host "smtp.example.test", port 587
S: 220 smtp.example.test ESMTP ready
C: EHLO app.example.test
S: 250-smtp.example.test
S: 250-STARTTLS
S: 250 AUTH PLAIN LOGIN
C: STARTTLS
S: 220 Ready to start TLS
[TLS handshake completed]
C: EHLO app.example.test
S: 250-smtp.example.test
S: 250 AUTH PLAIN LOGIN
[SMTP AUTH performed; authentication details hidden]
S: 235 2.7.0 Authentication successful
C: MAIL FROM:<sender@example.test>
S: 250 Sender accepted
C: RCPT TO:<recipient@example.test>
S: 250 Recipient accepted
C: DATA
S: 354 End data with <CRLF>.<CRLF>
[email headers and content hidden]
C: .
S: 250 2.0.0 Queued as Q12345
~~~

The **C:** and **S:** labels are added to explain client/server in the example. Actual debug output may differ in format, line count, and level of detail.

### Reading the key milestones

| Milestone | What is happening? | What to check on error |
| --- | --- | --- |
| Connect to host:port | SMTP client opens a path to the server | Host, DNS, port, firewall, timeout |
| **220 greeting** | Server greets at the start of the session | Whether the server is ready or refuses the connection |
| **EHLO** | Client introduces itself and queries server capabilities | Extensions such as STARTTLS, AUTH, SIZE |
| **STARTTLS** | Requests upgrading the connection to TLS | Certificate, trust, hostname, and TLS requirement |
| **AUTH** | Authenticates using an allowed mechanism | Credentials, account permissions, supported mechanisms |
| **MAIL FROM** | Declares the envelope sender | Domain/sending permission, provider policy |
| **RCPT TO** | Proposes delivering the mail to a recipient | Rejected address, limits, policy |
| **DATA** then **354** | Server allows sending the message content | Size, structure, connection limits |
| **250** after DATA | Server accepts the content at the submission step | Cross-check queue/message ID if provided by the server |

A server can produce multiple **RCPT TO** results in the same email: accepting one recipient while rejecting another. Those responses should not be collapsed into a single conclusion of "all addresses valid" or "all failed".

If the server reports **Queued as Q12345**, that code can be used to correlate with the provider's logs. It is not a global identifier preserved by every SMTP server, nor does it by itself prove the mail was delivered to the final Inbox.

### What protocol debug does not tell you

Even a full transcript of the SMTP submission step **does not guarantee** providing:

- The final status of the message in the recipient's mailbox.
- Whether the message is put into Spam or blocked later by the receiving system.
- Whether the recipient opens or reads the email.
- Any alias/forwarding steps at intermediate servers.
- The final outcome if the connection is lost before the client receives the response.

To track beyond the SMTP submission step, you may need **delivery events**, webhooks, DSNs/bounces, and the email provider's tracing tools. Protocol debug is a **local observation of one protocol session**, not a complete delivery tracking system.

## 6. Diagnosing incidents by where the trace stops

The goal of protocol debug is to **identify the last step the application and server successfully exchanged**, then cross-reference it with the Spring/Jakarta Mail exception and configuration. You should not start by turning every logger to TRACE without a specific question.

### Case A: No SMTP lines seen at all

Possible causes are:

- Business logic did not call **JavaMailSender.send(...)** due to input conditions, validation, or an earlier exception.
- The **mail-debug** profile was not activated or the **mail.debug** property was overridden to **false**.
- The application uses a manually configured/JNDI **JavaMailSender** bean or **Session**, so the property in YAML does not enter the Session being used.
- Debug output goes to a stream or logger other than the one being observed.
- The application does not connect to SMTP and instead uses another adapter/provider API.

**How to investigate:** first write a business log right before the send call with the job identifier, then verify which mail-sending component is actually active. If there is still no trace, check the active profiles, effective properties, the Session creation source, and the log output target. Avoid starting with the guess that "the SMTP server did not receive the email", because at this point there may **never have been a connection at all**.

### Case B: Error before seeing the 220 greeting

Example:

~~~text
DEBUG SMTP: trying to connect to host "smtp.example.test", port 587
java.net.ConnectException: Connection refused
~~~

No SMTP greeting yet means the error may lie in DNS, network, port, firewall, proxy, or the mail service not listening. Increasing **logging.level.org.springframework.mail** will not necessarily provide more evidence; check the hostname, connectivity, and firewall/network policy in the runtime environment.

If the log indicates **UnknownHostException**, focus on DNS/hostname. If it is **connect timeout**, focus usually on the network path or the server side not responding in time. If it is **Connection refused**, the destination host or an intermediate device may be refusing connections to that port.

### Case C: Connected, but STARTTLS fails

Hypothetical example:

~~~text
S: 220 SMTP ready
C: EHLO app.example.test
S: 250-smtp.example.test
S: 250 AUTH PLAIN LOGIN
[STARTTLS not seen in the capability list]
~~~

If the application configures **mail.smtp.starttls.required=true**, the transport may fail because the server does not advertise or does not allow STARTTLS. If the server advertises STARTTLS but the TLS handshake reports an error, check the certificate, trust chain, hostname, or related protocol version settings.

**Do not turn off TLS checks or remove the STARTTLS requirement just to make email "sendable".** Cross-check the port and security mechanism supported by the provider: **STARTTLS over an ordinary SMTP connection** differs from **implicit TLS/SMTPS**. Misconfiguring the TLS type can also lead to confusing connection or handshake errors.

Note: application/mail transport traces may show the protocol commands before and after TLS, but do not necessarily show all TLS handshake details. Use appropriate TLS signals or certificate errors when investigating further.

### Case D: AUTH fails

Part of a trace might be:

~~~text
C: EHLO app.example.test
S: 250 AUTH PLAIN LOGIN
[AUTH steps hidden]
S: 535 5.7.8 Authentication failed
~~~

At this point, check:

- Whether the username and password/token are configured correctly.
- Whether the account has permission to use SMTP AUTH.
- Whether the provider requires an app password, OAuth2, or another AUTH mechanism.
- Whether the connection satisfies the TLS policy before authenticating.
- Whether the account is restricted or locked due to policy.

You should not set **mail.debug.auth=true** to "see the password clearly" in the log. Verify credentials via the secret manager and authorized checking tools; avoid letting any authentication values enter centralized logs.

### Case E: MAIL FROM or RCPT TO is rejected

Example:

~~~text
C: MAIL FROM:<notify@example.test>
S: 250 Sender accepted
C: RCPT TO:<member@recipient.test>
S: 550 5.7.1 Recipient rejected by policy
~~~

The trace shows the server returned an error at the **RCPT TO** step, indicating you should check the recipient, policy, or sending limits. However, **code 550 does not always mean the mailbox does not exist**; the server may reject due to anti-spam rules, sending permissions, or domain rules.

If there are multiple recipients, a server may accept one and reject another. Therefore, inspect each **RCPT TO** response and the exception/transport data; do not generalize one error code into a conclusion for the whole recipient list.

### Case F: DATA fails or times out after sending

Example:

~~~text
C: DATA
S: 354 Continue
[Client transmits the message content]
C: .
[Final response not observed due to connection loss]
~~~

This is an important scenario. The server **may** have received the full content and queued the message, while the client lost the connection before receiving the response. On the Spring side, **MailSendException**/timeout may be reported, while the server-side acceptance status remains **uncertain**.

You cannot infer "not sent" just because the **250** line is missing in the client log. Immediately retrying the same email can create a duplicate. You need to cross-check provider logs, the message ID if available, job status, and the designed retry policy.

Conversely, if the server returns an explicit rejection code after DATA, read the response and provider data to identify size, content, limit, or policy errors. Do not treat every error at DATA as a recipient error.

### Case G: SMTP reports success but the recipient has not seen the mail

The trace ends with a success response after **DATA**. This usually only proves that the server at the submission hop **accepted the message for further processing**, not that delivery to the Inbox has completed.

At that point you need to switch from **SMTP submission diagnostics** to **delivery diagnostics**: check events, bounces, spam classification, sending domain configuration, SPF/DKIM/DMARC, and the receiving mailbox state. Leaving **mail.debug=true** on for many more hours usually generates no new information about a message that has already left the client.

## 7. Impact of protocol debug on data in logs

Protocol debug can record information that the application would not normally log, or record it in a less structured way. The exact extent depends on the library, version, trace level, and log output destination.

| Data type | Why might it appear? | Impact to watch out for |
| --- | --- | --- |
| SMTP host name, port, and server greeting | Connection, EHLO, SMTP responses | Reveals infrastructure and provider details |
| **MAIL FROM** / **RCPT TO** | Send commands and recipient selection | May contain personal emails, internal identifiers |
| Error codes, messages from the server | 4xx/5xx or extended status responses | May contain addresses or internal provider policies |
| Information related to **AUTH** | SMTP authentication process | Risk of leaking credentials/tokens if debug is enabled too deeply or misconfigured |
| Headers and message content | Some trace levels or transport log paths may record exchanged data | May contain names, order numbers, token links, private content |
| Encoded attachment payload | May appear when tracing outbound data at a very detailed level | Base64 **is decodable**, not data hiding |
| Queue ID, Message-ID, or diagnostic ID | Server responds when accepting a message | Useful for correlation, yet can still be sensitive |

**Do not treat Base64 as a way to secure data.** If logs contain raw MIME or Base64 attachment payloads, anyone with log read access can decode them back to the original bytes. An account verification link appearing in the body may also still be valid during the window when others can access the logs.

### Risks that do not come from the library

Even when Jakarta Mail does not print passwords under its default configuration, sensitive data can still be logged by:

- Application code logging the entire **MimeMessage**, request DTO, or SMTP configuration itself.
- AOP/interceptors logging arguments and exceptions without filtering data.
- HTTP/gateway diagnostics if the system also sends mail through a provider API in parallel.
- Automatic stdout collection pushing to a shared logging system.
- A diagnostic tool enabled by an engineer outside application.yml.

Therefore, the solution is not only setting **mail.debug.auth=false**, but also determining **what data may appear, who has permission to view it, how long it is kept, and how to redact/mask it before sharing**.

### Operational recommendations

1. **Disable protocol debug by default** in environments containing real data and credentials.
2. When diagnosing, prefer a **test mail server** and non-sensitive dummy addresses/events.
3. If an operational environment must be investigated, limit the scope and duration the trace is enabled; record clearly who is responsible for turning it off.
4. Keep **mail.debug.auth=false**; do not enable modes that expose authentication information.
5. Restrict log read permissions, retention duration, and log export/sharing.
6. **Mask addresses, tokens, content, and sensitive identifiers** before sending transcripts to others.
7. After gathering evidence, **turn debug off** and verify the running application/configuration version actually uses the disabled value.

You should not paste a transcript containing real transaction content into a public issue or discussion channel merely because it has the **DEBUG SMTP** prefix.

## 8. Impact on log volume, performance, and readability

An API handling a few mails per minute and a worker sending tens of thousands of mails per hour experience different levels of impact when protocol debug is enabled.

### Log volume grows with the number of sessions and recipients

Each session can contain many commands:

~~~text
EHLO
STARTTLS
EHLO
AUTH
MAIL FROM
RCPT TO (repeated for each recipient)
DATA
responses
QUIT
~~~

Depending on configuration, the transport may reuse a connection or open a new session per send. With a large recipient list, the number of **RCPT TO** lines and corresponding responses increases. If a trace level that also logs payloads is enabled, log size may also depend on **content and attachment size**.

Therefore, impacts may include:

- **Log write and storage cost**: stdout, log collectors, storage, and indexing receive extra data.
- **I/O pressure**: emitting many debug lines can add overhead to the process.
- **Information noise**: important business errors get buried under thousands of protocol lines.
- **Correlation difficulty**: multiple workers sending mail concurrently interleave output.
- **Risk of prolonging incidents**: the log collector or disk becomes overloaded while the system is already failing mail.

Protocol debug should not be used as a **permanent metric or audit log**. Operational systems should have structured business logs and durable observability metrics; SMTP traces are an in-depth point-in-time investigative tool.

### Why can multiple SMTP sessions be hard to read?

When there are multiple mail-sending threads:

~~~text
Worker A -> EHLO
Worker B -> EHLO
Worker A -> MAIL FROM
Worker B -> AUTH
Worker A -> RCPT TO
...
~~~

If output lacks reliable thread IDs or mail job IDs, seeing adjacent lines in the same console does not guarantee they belong to **the same email**. In fact, a transport may open a connection and write traces at a different moment from the request's business log.

Therefore, before enabling debug, log application entries with **mailJobId**, start time, outcome, attempt count, and timeout details. Only use protocol traces when needed to understand a specific error layer.

## 9. How should business logs complement protocol debug?

The application can log concise, structured information around the **JavaMailSender.send(...)** call, instead of relying on the entire transcript:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.mail.javamail.MimeMessagePreparator;
import org.springframework.stereotype.Service;

@Service
public class InstrumentedMailService {
    private static final Logger log =
            LoggerFactory.getLogger(InstrumentedMailService.class);

    private final JavaMailSender mailSender;

    public InstrumentedMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(
            String mailJobId,
            int attempt,
            String recipient
    ) {
        long startedAt = System.nanoTime();

        MimeMessagePreparator preparator = mime -> {
            MimeMessageHelper helper =
                    new MimeMessageHelper(mime, false, "UTF-8");
            helper.setFrom("notifications@example.test");
            helper.setTo(recipient);
            helper.setSubject("Welcome");
            helper.setText("Your account has been created.", false);
        };

        log.info(
                "Mail submission started: jobId={} attempt={} type={}",
                mailJobId, attempt, "WELCOME"
        );

        try {
            mailSender.send(preparator);

            long elapsedMs =
                    (System.nanoTime() - startedAt) / 1_000_000;
            log.info(
                    "Mail submitted: jobId={} attempt={} elapsedMs={}",
                    mailJobId, attempt, elapsedMs
            );
        } catch (MailException ex) {
            long elapsedMs =
                    (System.nanoTime() - startedAt) / 1_000_000;
            log.warn(
                    "Mail submission failed or uncertain: "
                    + "jobId={} attempt={} elapsedMs={} exceptionType={}",
                    mailJobId,
                    attempt,
                    elapsedMs,
                    ex.getClass().getSimpleName()
            );
            throw ex;
        }
    }
}
~~~

This example illustrates several principles:

- Logs contain **mailJobId**, notification type, attempt, and execution duration.
- Do not put recipient email addresses or message content into every log line.
- Log **submitted** only when the send call completes without error; **submitted does not equal delivered**.
- On exception, record **failed or uncertain state**, because a timeout can happen after the provider has already received the data.
- Propagate the exception to the worker/controller layer to decide retry or error reporting per business rules.

In a real application, store the outcome in a mail job or outbox so it can recover after the process stops. **Logs only describe observed events, not a reliable job-processing state store.**

If a stack trace is needed for investigation, the final handling layer can log the exception according to the organization's logging and data-protection policies; avoid logging the same huge stack trace repeatedly across multiple layers.

### Correlation IDs and limits of debug output

In applications using SLF4J MDC, application logs can automatically carry **requestId** or **mailJobId**. But **Session debug** lines written directly to a PrintStream do not automatically receive the same MDC and Logback pattern.

For background sending work or **@Async**, MDC data on the request-handling thread is also not necessarily carried over intact to the worker. You need to design a mechanism to propagate correlation context appropriately, or always use a **job ID** stored with the job.

Do not conclude that two adjacent SMTP lines in logs belong to the same session based solely on timestamps. Cross-reference application logs, connection info, and provider traces if needed.

## 10. Settings easily confused when investigating SMTP

### Enabling debug does not mean enabling or fixing TLS

**mail.debug=true** only changes observability; it does not activate STARTTLS itself, change the port, or fix authentication errors.

Commonly seen options:

| Connection type | Common configuration | Things to remember |
| --- | --- | --- |
| SMTP + STARTTLS | Port **587** per provider configuration; **mail.smtp.starttls.enable=true** | Connection starts as ordinary SMTP and then upgrades to TLS |
| SMTP requiring STARTTLS | Add **mail.smtp.starttls.required=true** | If STARTTLS cannot be negotiated, sending must fail per policy |
| SMTP using TLS from the start | Often port **465**; with the SMTP transport, **mail.smtp.ssl.enable=true** can be used | The implicit TLS mechanism differs from the STARTTLS command |
| Unauthenticated SMTP | **mail.smtp.auth=false** when the provider permits it | Do not use this setting to bypass a provider's AUTH requirement |

Ports are only common conventions. Providers may publish different parameters; obtain the official details of the service in use.

When a trace reports an error in the TLS handshake, fix the security configuration appropriate for the connection type. Do not resolve it by turning off TLS or disabling certificate checks.

### mail.debug is not mail.smtp.debug

The property commonly used to enable Jakarta Mail Session debug is **mail.debug**. Do not guess that adding an invented property like **mail.smtp.debug=true** will have an equivalent effect; transport properties must match the exact names supported by the implementation.

The reason lies in how Jakarta Mail uses **Session** and **Transport**:

~~~text
Spring Boot MailProperties
       |
       | spring.mail.properties
       v
Jakarta Mail Session
       |
       | mail.debug = true
       v
Provider / SMTP transport debug
       |
       v
Session/provider output
~~~

An application can set **Session.setDebug(true)** in Java code, but with Spring Boot, **configuration via profile** is usually easier to observe, reproduce, and turn off. In particular, changing the debug state of a **shared Session** across multiple workers at runtime can affect other sending threads using the same Session.

If another library or configuration calls **setDebug(true)** directly, changing YAML to **false** may not disable every source of protocol traces. Find the exact place where the Session is created and configured, and check the provider's loggers/handlers as well.

### spring.mail.test-connection only tests connectivity

Spring Boot has the **spring.mail.test-connection** option to attempt connecting to the mail server at startup in suitable configurations:

~~~yaml
spring:
  mail:
    test-connection: true
~~~

Depending on configuration, trying to connect may cause the application to fail at startup if it cannot connect. When **mail.debug** is enabled, you may see output related to the connection/initialization process.

However, **a successful test-connection does not prove a real email can be sent**, because it does not necessarily execute **MAIL FROM**, **RCPT TO**, **DATA** for a specific message. An account may connect and authenticate successfully yet still be restricted on sender, recipient, quota, or message content.

Use test-connection to check part of availability and configuration, not to replace controlled send testing or the provider's delivery data.

## 11. A controlled diagnostic process

When you need to handle a mail-sending incident, you can follow this sequence:

1. **Identify the specific symptom**: connection failure, AUTH rejected, recipient rejected, error at DATA, or the mail does not appear in the Inbox.
2. **Gather existing evidence**: job ID, send timestamp, **MailException** type, cause chain, SMTP status/provider event if available.
3. **Check effective configuration**: host, port, TLS type, credentials, timeouts, Spring Boot profile, Mail Session creation source.
4. **Enable mail.debug in a small scope**: use a diagnostic profile and test account/address when possible; keep **mail.debug.auth=false**.
5. **Perform one traceable send**: choose a small message with no secrets, knowing the test recipient and the exact operation time.
6. **Read the last point in the SMTP conversation**: inspect **EHLO**, **STARTTLS**, **AUTH**, **MAIL FROM**, **RCPT TO**, **DATA**, and server responses.
7. **Classify the issue**: fix data or configuration, do bounded retries for transient errors, or switch to delivery tracking if the server accepted it.
8. **Turn off protocol debug and handle logs safely**: confirm the configuration is off; protect, mask, or delete transcripts per retention and incident policies.

This process avoids leaving application-wide debug enabled for long periods. It also helps distinguish **errors before contacting SMTP** from **errors after the provider has received the message**, two situations with different retry consequences.

### A sufficient incident record

Instead of copying the entire console, an investigator can record filtered information:

~~~text
mailJobId:        MAIL-782
mailType:         WELCOME
attempt:          2
smtpTarget:       smtp-provider-a
transportStage:   RCPT_TO
smtpCode:         451
exceptionType:    MailSendException
submissionState:  TEMPORARY_FAILURE
nextAction:       RETRY_WITH_BACKOFF
observedAt:       [timestamp]
~~~

This is an illustrative template, not a mandatory Spring Mail format. Fields like **transportStage** or **smtpCode** should only be filled in when there is evidence from the exception, trace, or provider. If the connection drops after DATA, **submissionState** may have to be **UNKNOWN**; do not arbitrarily set **TEMPORARY_FAILURE** as if you knew for sure it was not sent.

In operations, collected data may include:

- **Application**: job logs, time of send call, exception class, and elapsed time.
- **Transport**: a redacted trace snippet showing relevant commands and responses.
- **Provider**: queue ID, rejection reason, delivery/bounce events if the provider has them.
- **Business**: whether the user account was created, whether the verification token is still valid, whether there is a retry job.

Combining these sources is more useful than a long protocol log without job IDs or context.

## 12. Scenario reading exercises

### Scenario 1: logging.level.org.springframework.mail=DEBUG enabled, but no EHLO seen

**Question:** was SMTP not contacted?

**Answer:** not enough evidence. This property adjusts Spring Mail's logger and does not automatically enable **Jakarta Mail Session debug**. Check whether the application called send yet, then enable **mail.debug** on the right Session/profile and observe the corresponding output.

### Scenario 2: mail.debug enabled, but trace lines lack a Logback timestamp

**Question:** is Spring Boot's logging configuration broken?

**Answer:** not necessarily. Jakarta Mail can write debug directly to **System.out** or a separate debug stream. Those lines do not automatically use Logback's pattern, thread, and MDC, even though they are eventually collected by the console or container runtime.

### Scenario 3: Trace shows AUTH failed

**Question:** should mail.debug.auth=true be enabled to view the credentials and verify?

**Answer:** no. Investigate the credential source via the secret manager, account permissions, and AUTH/TLS configuration. Do not put authentication data into logs; keep **mail.debug.auth=false** and use only traces stripped of sensitive data.

### Scenario 4: Server returns 250 after DATA, but the customer does not see the email

**Question:** can protocol debug be used further to prove the recipient read the mail?

**Answer:** no. **250** after DATA usually shows the server accepted the message at the submission step. You need delivery/bounce/provider data and receiving-side checks; protocol traces do not track reading behavior.

### Scenario 5: Connection timed out before the server returned 220

**Question:** should the recipient address be changed?

**Answer:** not based on this symptom. Errors before receiving the greeting usually occur at DNS/TCP/network or the SMTP server, before the **RCPT TO** step. Check host, port, network path, and **mail.smtp.connectiontimeout**.

### Scenario 6: Trace shows only some RCPT TO responses succeeded

**Question:** can the entire recipient list be marked as sent?

**Answer:** no. Inspect each recipient's response, the DATA process, how the transport handles partial sends, and provider data. Accepting **RCPT TO** does not prove delivery to the final mailbox.

### Scenario 7: No response after the end-of-DATA line

**Question:** is it safe to immediately retry every email?

**Answer:** there is a risk of duplicate sending. The server may have received the data while the response was lost. Record an **unknown** submit status, cross-check the provider if available, and apply a retry policy suitable for the business.

### Scenario 8: Staging environment uses no customer data; can debug be left on continuously?

**Question:** is there no risk in doing so?

**Answer:** the risk is lower if the data is completely synthetic, yet infrastructure details, credentials, log volume, and access permissions still exist. It should be off by default, enabled only when needed, retention-limited, and prevented from being accidentally deployed to another environment.

## 13. Remember the difference between "knowing the error" and "seeing the protocol"

~~~text
MailException
    -> Shows the mail operation failed at the Spring layer
    -> Read type, cause, and job state

logging.level.org.springframework.mail=DEBUG
    -> Increases log level emitted by the Spring Mail logger
    -> Does not guarantee SMTP command traces

spring.mail.properties["mail.debug"]=true
    -> Enables Jakarta Mail Session/transport debug
    -> Observes the protocol conversation per implementation
    -> May print to stdout/debug stream and get ingested into centralized logs

Provider delivery/bounce events
    -> Evidence at steps after SMTP submission
    -> Needs a separate tracking mechanism when required by the business
~~~

**Protocol debug is a microscope for the SMTP exchange at the application, not the complete mail-delivery status.** In Spring Boot, you need to enable **mail.debug** properly on the Mail Session actually in use, understand where debug output appears, and read each response in the right stage. More importantly, treat protocol traces as data that must be protected: enable purposefully, mask sensitive information, limit scope/duration, and turn off after investigation.
