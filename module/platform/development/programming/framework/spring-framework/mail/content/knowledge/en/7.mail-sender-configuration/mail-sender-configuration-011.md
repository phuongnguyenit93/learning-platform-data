# Development, Test, Staging, and Production Profiles

## 1. Why must mail-sending configuration differ across environments?

Applications using **Spring Framework Mail** typically connect to an SMTP server through **JavaMailSender**. During local development, automated test runs, staging deployments, and production operation, the application may use **the exact same sending API**, yet the sending purpose, SMTP server, accounts, permitted recipients, and operational requirements differ.

A mail configuration mistake easily causes real-world impact: a developer testing notifications accidentally points at production SMTP, sending test emails to real customers; or an automated test suite runs hundreds of times and sends hundreds of real emails. Conversely, if production keeps pointing at a local mock SMTP sink, customers receive no notifications even though the app logs "send succeeded."

Spring Boot supports **profiles** to select different configuration sets per environment. For Spring Mail, the goals are:

1. **Local/development**: inspect generated emails without sending them out to the Internet.
2. **Test**: verify email content and sending interactions repeatably, offline, without real credentials.
3. **Staging**: test near-production sending flows while restricting recipients and preventing accidental external delivery.
4. **Production**: use the real SMTP provider, TLS, managed secrets, logging/monitoring, timeouts, and proper operational policies.

Separation diagram:

~~~mermaid
flowchart LR
    A[Spring application code] --> B[JavaMailSender / Mail service]
    B --> C{Active Spring profile}
    C -->|local| D[SMTP sink / mock inbox]
    C -->|test| E[Mock, fake, or SMTP test server]
    C -->|staging| F[SMTP sandbox + recipient restriction]
    C -->|prod| G[Real SMTP provider]
~~~

**Profiles select configuration and wiring**, while **rules governing who may receive mail** must be enforced by the application or infrastructure. Naming a profile `staging` does not automatically stop the app from emailing real customer addresses.

## 2. How do Spring profiles select and override configuration?

Spring Boot typically loads base configuration from **application.yml**, then layers profile-specific configuration sources for active profiles, for example:

~~~text
src/main/resources/
├── application.yml
├── application-local.yml
├── application-staging.yml
└── application-prod.yml

src/test/resources/
└── application-test.yml
~~~

This layout is illustrative, not mandatory. Files under **src/test/resources** only appear on the test classpath by default; test configs can live elsewhere if required by your build. Profiles can also come from `.properties` files, external resources, environment variables, command-line arguments, or deployment platforms.

Example:

~~~yaml
# application.yml
spring:
  mail:
    default-encoding: UTF-8
    properties:
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

~~~yaml
# application-local.yml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
~~~

When the **local** profile is active, the app receives the shared settings (encoding, timeouts) combined with local host/port. Properties with the same key in higher-precedence sources override earlier values. **Spring Boot's configuration property precedence depends on source type and loading context**; do not naively assume every environment variable behaves identically to every YAML file. Understand externalized configuration rules, especially when mixing command-line args, environment variables, ConfigMaps, and secrets.

Activate a profile when running a JAR:

~~~bash
java -jar application.jar --spring.profiles.active=local
~~~

Or set an environment variable:

~~~bash
SPRING_PROFILES_ACTIVE=staging
~~~

In a deployed service, environment variables are passed to the **Java process** before startup. Never set **spring.profiles.active: prod** as the default in shared config files hoping developers always remember to override it; environment selection should be explicitly controlled by the runtime/deployment system.

### Multiple active profiles

Spring can activate multiple profiles simultaneously. When multiple config files define the same property, profile ordering and source precedence decide the final value. For example, combining **local,prod** can produce one environment's host with another environment's credentials if configuration is poorly controlled.

For mail settings, treat **local**, **test**, **staging**, and **prod** as **four mutually exclusive deployment environments** in operational policy; if feature profiles are also needed, define their ordering and boundaries clearly. Never rely on profile names as the sole security boundary.

### Names like test, staging, and prod are just conventions

Spring does not automatically know that a profile named **test** must disable sending, **staging** must restrict recipients, or **prod** must enforce TLS. Those behaviors exist only when the application configures the matching **beans, properties, and policies**.

## 3. Target matrix across the four environments

| Aspect | Local/development | Automated test | Staging | Production |
|---|---|---|---|---|
| SMTP endpoint | Locally running SMTP sink | Mock/fake or test SMTP server | Sandbox or dedicated relay | Real SMTP provider/relay |
| Credentials | Not needed if sink permits | No real credentials | Dedicated staging secret | Production secret |
| Recipients | Synthetic data | Fixture addresses | Internal allowlist or sandbox domain | Valid business recipients |
| Sending behavior | Capture and inspect mail for debugging | Verify, capture, or assert | End-to-end with guardrails | Real delivery per policy |
| TLS | Depends on local sink, often off on loopback | Not needed if mocked | Required when talking to network provider | Required per infrastructure, verify certificates |
| Observability | Sink web UI, sanitized logs | Assertions and test reports | Metrics, logs, test events | Metrics, queues, bounce/DSN/provider events |
| Sending real email? | No | No | Only approved test accounts | Per application rules |

Design to **fail closed**: if the application cannot identify its environment or lacks valid sending config, never fall back silently to production SMTP for "convenience." If production secrets are missing, fail clearly; if tests lack an SMTP server, never silently hit a real mail host.

## 4. Shared base configuration in application.yml

**Non-sensitive, shared** properties can reside in the base file:

~~~yaml
# src/main/resources/application.yml
spring:
  mail:
    default-encoding: UTF-8
    properties:
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

Meaning:

- **default-encoding**: default charset for email content constructed by `JavaMailSender`/`MimeMessageHelper` under this config.
- **mail.smtp.connectiontimeout**: wait limit for establishing TCP connection to the SMTP server.
- **mail.smtp.timeout**: wait limit for reading from the SMTP socket.
- **mail.smtp.writetimeout**: write wait limit per Jakarta Mail transport.

Durations are in **milliseconds**; numbers are illustrative. Omitting timeouts or setting them too high can tie up threads when the network/SMTP server stalls. Setting them too low causes spurious failures when valid servers respond slowly.

**Base configuration must not put real SMTP host/username/password.** Host and credentials belong to the deployment environment; define them per profile or inject them from external configuration.

Spring Boot normally provides **JavaMailSender auto-configuration** when required libraries are on the classpath and mail config satisfies conditions. If the `test` profile omits an SMTP host while the application injects a required `JavaMailSender` constructor dependency, startup may lack a matching bean. In that case, **provide a mock/fake bean in the test context** or design a gateway layer choosing transports by environment. Simply deleting the SMTP host property does not automatically turn `send()` into a no-op.

## 5. Local profile: capturing emails into an SMTP sink

During local development, an **SMTP sink** is a practical way to inspect email content without sending to the Internet. Tools like **Mailpit**, **MailHog**, or an equivalent test SMTP server accept emails over SMTP and let developers read them in a web UI.

Example local config:

~~~yaml
# src/main/resources/application-local.yml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
    properties:
      mail.smtp.auth: false
      mail.smtp.starttls.enable: false

app:
  mail:
    delivery-mode: CAPTURE
~~~

In this example, the SMTP sink is assumed to listen on **127.0.0.1:1025**; if running inside a container, **127.0.0.1** refers to the app container itself, not the host or SMTP sink container. Under Docker Compose, the app may need to connect via the SMTP sink's **service name** on the shared network, e.g., **mailpit:1025**. Hostname and port must match actual deployment.

The **app.mail.delivery-mode** property is **application-defined**, not a built-in Spring Boot configuration. For it to enforce policy, you must write code reading the property and acting on it—such as logging `CAPTURE`, blocking real delivery, or selecting an adapter. Adding a key to YAML alone creates no safety guard.

A flow developers can inspect:

~~~text
Local Spring Boot
    |
    | JavaMailSender.send()
    v
SMTP sink on dev machine
    |
    v
UI for captured mail
    |
    +-- Subject, To, From
    +-- Text/HTML
    +-- Attachments, MIME structure
~~~

An SMTP sink may reply **250 accepted**, making `JavaMailSender.send()` succeed; that only confirms **the sink received and stored it for viewing**, not that an email reached the recipient's domain. That is exactly the desired local behavior.

### Notes for demos and manual testing

- Bind SMTP/web UI to loopback or an isolated dev network; never expose test-email UIs publicly by default.
- Use synthetic or scrubbed data; sinks usually retain full bodies and attachments.
- For HTML emails, check text/plain, URLs, inline images, and attachments; sink UIs help inspect MIME, though they do not replace testing in real email clients.
- When switching sender hosts, verify the app loaded the right profile; never assume an environment variable set on the host was actually passed into the process.

## 6. Test profile: independent of real SMTP

In **unit tests** and many **integration tests**, what matters is verifying the application requests sending to the right recipient, subject, body, or MIME parts. Usually you do not need a real SMTP provider, because networks, accounts, quotas, and actual delivery make tests slow, flaky, or prone to leaking data externally.

A safe test profile can be declared as:

~~~yaml
# src/test/resources/application-test.yml
app:
  mail:
    delivery-mode: DISABLED
~~~

Again, **app.mail.delivery-mode** only works when application code interprets it. In tests that simply mock `JavaMailSender`, this setting can serve as metadata for environment policy; it does not replace mocking by itself.

### Verifying JavaMailSender interactions with a mock

With Spring Boot 3.3 and Spring Test/Mockito, you can create a test context with a mocked `JavaMailSender` and verify the service built the right `SimpleMailMessage`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class NotificationMailServiceTest {
    @Autowired
    private NotificationMailService service;

    @MockBean
    private JavaMailSender mailSender;

    @Test
    void shouldBuildWelcomeMessage() {
        service.sendWelcome("alice@example.test");

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);
        verify(mailSender).send(captor.capture());

        SimpleMailMessage message = captor.getValue();
        assertThat(message.getTo())
                .containsExactly("alice@example.test");
        assertThat(message.getSubject()).isEqualTo("Welcome");
    }
}
~~~

This example assumes **NotificationMailService** exists and its **sendWelcome** method builds a `SimpleMailMessage` and invokes `JavaMailSender`. It illustrates a test pattern, not a Spring-generated class. **@MockBean** fits Spring Boot 3.3; on newer Spring/Boot releases, check the mock-bean mechanism supported by your project's version.

If the application uses `MimeMessage`, tests can mock the sender for `send` yet still need a mechanism to create `MimeMessage` instances for inspection. A fake or local test SMTP server in integration tests is more convenient when verifying full MIME, attachments, and encoding. Never use a mock that simply returns success to "verify" STARTTLS or SMTP AUTH, since mocks execute no SMTP protocol.

### Integration tests with a test SMTP server

When testing **SMTP exchange** (reply codes, MIME, attachments, multiple recipients), you can start an embedded/local test SMTP server during tests and point **spring.mail.host/port** at it. Tests must manage server lifecycle, port, and captured data themselves; never use production credentials. Running the server on a dynamic port and passing it into the Spring test context prevents port conflicts across CI jobs.

Distinguishing test goals:

| Test type | How SMTP is replaced | What it verifies |
|---|---|---|
| Unit test | Mock `JavaMailSender` or mock `MailGateway` | Method calls and request data |
| Spring service test | `MockBean` / `TestConfiguration` | Wiring, validation, business rules |
| SMTP integration test | Local SMTP sink / test server | Real MIME packaging and submission protocol |
| Staging end-to-end | Managed SMTP sandbox/relay | Deployment config, network connectivity, TLS, credentials, events |

Pick the test matching what you want to prove. Mock tests do not prove real mail delivery; staging against a real provider does not replace offline unit tests.
## 7. Staging profile: production-like sending with guardrails

**Staging** is the pre-production deployment verification environment. For email, staging usually needs to verify more than local: the app boots with environment variables, reaches an SMTP provider over the network, negotiates TLS, authenticates, emits proper headers/MIME, and handles real replies. Yet staging **must not send emails to production users**.

Illustrative staging config:

~~~yaml
# src/main/resources/application-staging.yml
spring:
  mail:
    host: ${STAGING_SMTP_HOST}
    port: 587
    username: ${STAGING_SMTP_USERNAME}
    password: ${STAGING_SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true

app:
  mail:
    delivery-mode: SANDBOX
    allowed-recipient-domains:
      - qa.example.org
~~~

Variable names like **STAGING_SMTP_*** are examples, not Spring-provided system variables. Values come from the deployment platform's secret store or staging environment. If required values are missing, never fall back silently to production credentials.

**SANDBOX** and **allowed-recipient-domains** are custom business settings. For real protection, application code must validate recipients, and the provider may also offer sandbox/test modes at the infrastructure layer. Combine both layers:

- **In the application:** reject addresses outside the allowlist across **To, Cc, Bcc**, and all sending paths.
- **At the SMTP provider:** use a staging account with restricted sending permissions, dedicated domain, sandbox mode, or non-delivery policy per provider support.

Never rewrite only the displayed `To` header while leaving real SMTP envelope recipients unchecked. Blocking rules must run **before sending** on every destination that could receive the message; if the system uses aliases or forwarding, enforce controls on the destination infrastructure too.

### What should be tested in staging?

1. **Connectivity:** host/port, DNS, firewalls, TLS, certificates, and AUTH mechanisms.
2. **Content generation:** subject, UTF-8 charset, HTML/text alternatives, inline resources, attachments, and MIME boundaries.
3. **Sender identity:** whether `From` is authorized for the SMTP account; test domain SPF/DKIM/DMARC if testing actual delivery.
4. **Limits:** MIME size, recipient counts, rate limits, quotas, and SMTP replies.
5. **Async events:** submission accepted, deferred, bounced, and provider webhooks if supported.
6. **Data safety:** synthetic or anonymized test data; never copy real customer data into weakly protected staging mailboxes.

Staging results can show an email was **accepted by the SMTP server**, yet do not automatically prove delivery to a specific user's Inbox. Never treat staging passes as proof that every external domain delivers cleanly.

## 8. Production profile: security, reliability, and observability

Production sends real messages to real recipients. Configuration must remain isolated from staging in secrets, sending permissions, and network infrastructure. Example on **port 587 SMTP submission with STARTTLS**:

~~~yaml
# src/main/resources/application-prod.yml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000

app:
  mail:
    delivery-mode: LIVE
~~~

In Spring Boot YAML, **${SMTP_HOST}** is a placeholder resolved from the configuration environment; **${SMTP_PORT:587}** defaults to 587 when unset. Host, username, and password have no fallback to local or staging SMTP. If secrets/provider are unavailable, handle the configuration error explicitly.

JavaMail properties:

| Property | Effect |
|---|---|
| **mail.smtp.auth=true** | Enables authentication when sending via SMTP |
| **mail.smtp.starttls.enable=true** | Allows upgrading the connection via STARTTLS |
| **mail.smtp.starttls.required=true** | Requires STARTTLS to succeed; refuses unencrypted fallback |
| **mail.smtp.ssl.checkserveridentity=true** | Verifies certificate hostname identity in SMTP TLS |
| **connectiontimeout** | Bounds prolonged connection waits |
| **timeout** | Bounds socket read waits |
| **writetimeout** | Bounds socket write waits per transport |

**Port 465** typically uses **implicit TLS** (TLS handshake right on connect), so configuration differs. Example when provider requires port 465:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.ssl.enable: true
      mail.smtp.ssl.checkserveridentity: true
~~~

Never mistakenly enable implicit TLS on a port waiting for a plaintext SMTP banner, or vice versa. Follow the actual server's documentation; shared timeouts from the earlier example can be added as well.

### When production has multiple pods/instances

If the application runs multiple instances, **each instance has its own `JavaMailSender` bean**. A singleton bean only reuses one instance per application context, not one cluster-wide sender. System-wide, control:

- SMTP quotas and connection counts across **all instances combined**, not just one pod.
- Retries on network errors or SMTP `4xx`, with backoff and attempt caps.
- Uncertain states when timeouts happen after the server may already have accepted the message.
- Durable queues/outboxes for critical business notifications.
- Metrics and logs with request/message IDs, without logging passwords, access tokens, or sensitive content.

**`JavaMailSender.send()` succeeding** in SMTP submission means the transport handled the send to the server cleanly; usually the server accepted the message. Final delivery states must be tracked via MTA logs, DSNs/bounces, or provider events when available.

### Should you test the connection on application startup?

Spring Boot provides **spring.mail.test-connection** to test the sender connection at startup under matching config conditions. It can be enabled where mail connectivity is mandatory for readiness, though weigh the trade-off: a transient SMTP outage can keep the app **from starting**, even when other business APIs still work.

Choose readiness policy based on business requirements. Some systems treat email as auxiliary and rely on an outbox during SMTP outages; others must stop accepting mail-dependent work without a sending path. Startup checks only verify **connectivity at test time**, not long-term delivery or all sending permissions.

## 9. Enforcing application-level recipient guardrails

Profiles and config variables alone cannot create a safe policy if code always calls **JavaMailSender.send()** unchecked. You can place an intermediary layer (**MailGateway** or mail-sending service) to decide whether to send for real, capture into a sink, or reject based on configuration.

Example using custom configuration properties:

~~~java
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public record MailPolicy(
        DeliveryMode deliveryMode,
        Set<String> allowedRecipientDomains) {

    public enum DeliveryMode {
        DISABLED, CAPTURE, SANDBOX, LIVE
    }
}
~~~

Register binding for the properties class:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(MailPolicy.class)
public class MailPolicyConfiguration {
}
~~~

**MailPolicy** and enum names are application-defined examples. Spring Boot does not natively understand CAPTURE/SANDBOX; sending code must enforce the rules while pointing SMTP host settings appropriately for the mode.

A simple policy-checking method:

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;
import java.util.Locale;

public final class RecipientPolicy {
    private RecipientPolicy() {
    }

    public static void requireAllowed(
            String email,
            MailPolicy policy) {
        if (policy.deliveryMode() == MailPolicy.DeliveryMode.DISABLED) {
            throw new IllegalStateException("Mail delivery is disabled");
        }

        if (policy.deliveryMode() == MailPolicy.DeliveryMode.LIVE) {
            return; // Other production policies must still apply.
        }

        if (policy.deliveryMode() == MailPolicy.DeliveryMode.SANDBOX) {
            String domain = domainOf(email);
            boolean permitted = policy.allowedRecipientDomains() != null
                    && policy.allowedRecipientDomains().stream()
                        .map(d -> d.toLowerCase(Locale.ROOT))
                        .anyMatch(domain::equals);
            if (!permitted) {
                throw new IllegalArgumentException(
                        "Recipient not allowed in sandbox");
            }
        }

        // CAPTURE uses a separately configured SMTP sink;
        // never accidentally point CAPTURE at production.
    }

    private static String domainOf(String email) {
        try {
            InternetAddress address = new InternetAddress(email, true);
            address.validate();
            String mailbox = address.getAddress();
            int at = mailbox.lastIndexOf('@');
            if (at < 1 || at == mailbox.length() - 1) {
                throw new IllegalArgumentException(
                        "Invalid recipient address");
            }
            return mailbox.substring(at + 1)
                    .toLowerCase(Locale.ROOT);
        } catch (AddressException ex) {
            throw new IllegalArgumentException(
                    "Invalid recipient address", ex);
        }
    }
}
~~~

Call **requireAllowed** before building or sending to **every recipient** in To, Cc, and Bcc. The snippet checks one mailbox at a time; for MIME messages with multiple recipients, the sending layer must extract and validate all recipients, including any added by business rules. In production, LIVE passing the environment check **does not remove** validation, sending permissions, or anti-abuse controls.

**This is an additional guardrail, not proof of complete isolation.** Use scoped SMTP credentials, provider restrictions, and network egress rules where possible. If a misconfiguration points CAPTURE at production, a SANDBOX domain check will not catch it; also validate allowed host/port/account per environment or enforce policies at gateway/infrastructure level.

## 10. Protecting secrets and deployment configuration

SMTP credentials should come from **a secret manager, controlled environment variables, or organization-approved mechanisms**—never commit passwords to `application.yml` or example docs. The deployment system can inject **SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD** for production and distinct names for staging.

Example arguments passed at runtime:

~~~bash
java -jar application.jar --spring.profiles.active=prod
~~~

If environment variables are missing or placeholder names are wrong, configuration should fail clearly. **Never store real secrets in shell history, startup logs, or CLI arguments containing passwords.** On many platforms, secrets can be mounted as files or injected as environment variables; the choice depends on threat model and infrastructure.

### Avoiding naming collisions or unexpected overrides

For instance, Spring Boot reads **SPRING_MAIL_HOST** as a property bound to **spring.mail.host**. If a system has both **${SMTP_HOST}** in YAML and a leftover **SPRING_MAIL_HOST** in the environment, the effective value may surprise whoever wrote the YAML due to property source precedence.

Therefore:

- Follow **one clear convention** for variable names and secret sources per environment.
- Never reuse production secrets in staging.
- When inspecting effective config, log **profile, transport type, and publicly permitted hostnames**, avoiding usernames/passwords or tokens.
- Add policies that refuse startup when active profile, SMTP endpoint, and delivery mode conflict.
- Restrict runtime secret read permissions and scope SMTP account sending rights to the minimum needed.

The SMTP server replying **235 Authentication successful** only proves the client authenticated at that instant. Users can still miss emails if the `From` address is unauthorized, queues fail, quotas are exceeded, or destination servers reject the message.
## 11. Separating MailGateway from business logic when switching transports

In small apps, services can inject **JavaMailSender** directly and mock it in tests. When a system handles email multiple ways, consider a business-facing interface such as **MailGateway**. Business services issue send requests; the gateway decides whether to use SMTP, capture, or a fake per environment.

~~~java
public record OutboundMail(
        String recipient,
        String subject,
        String body) {
}

public interface MailGateway {
    void send(OutboundMail mail);
}
~~~

SMTP implementation:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;

@Component
@Profile({"local", "staging", "prod"})
public class SmtpMailGateway implements MailGateway {
    private final JavaMailSender sender;
    private final MailPolicy policy;

    public SmtpMailGateway(JavaMailSender sender, MailPolicy policy) {
        this.sender = sender;
        this.policy = policy;
    }

    @Override
    public void send(OutboundMail mail) {
        RecipientPolicy.requireAllowed(mail.recipient(), policy);

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("notifications@example.com");
        message.setTo(mail.recipient());
        message.setSubject(mail.subject());
        message.setText(mail.body());
        sender.send(message);
    }
}
~~~

**@Profile** is a Spring annotation determining which beans are registered in the application context when matching profiles are active. Here `SmtpMailGateway` exists when `local`, `staging`, or `prod` is active. Under **local**, the gateway still calls SMTP pointing to a sink. Under **staging**, `RecipientPolicy` checks the allowlist. Under **prod**, LIVE mode proceeds with real sending rules.

Under **test**, you can use a **recording fake** storing send requests in memory for assertions:

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("test")
public class RecordingMailGateway implements MailGateway {
    private final List<OutboundMail> captured = new ArrayList<>();

    @Override
    public synchronized void send(OutboundMail mail) {
        captured.add(mail);
    }

    public synchronized List<OutboundMail> snapshot() {
        return List.copyOf(captured);
    }

    public synchronized void clear() {
        captured.clear();
    }
}
~~~

This is a **minimal fake** to illustrate the idea. In parallel test runs or shared Spring test contexts across test cases, **reset test data at the right boundary**, narrow bean scope, or instantiate per-test fakes. Never deploy a fake storing real user data into production. Only use this wiring when the app intentionally adopts `MailGateway` as its sending boundary; it is not an automatic feature of `JavaMailSender`.

### Avoiding overlapping profiles that register two gateways

If **test** and **prod** are accidentally active together, both `RecordingMailGateway` and `SmtpMailGateway` could register, causing non-unique bean errors or picking the wrong implementation if `@Primary` or `@Qualifier` is present. Enforce **mutually exclusive** environment profiles and reject inconsistent configuration right at startup.

Never write policies like **@Profile("!prod")** on fakes assuming everything non-prod is safe: when no profile is set or multiple profiles are active, negated conditions can match more broadly than intended.

## 12. Validating environment configuration before sending mail

An application can start up even if SMTP properties point to the wrong environment. Therefore, design **consistency checks** before accepting mail-sending requests:

| Condition | Example check | Appropriate behavior |
|---|---|---|
| No environment profile | None of local/test/staging/prod active | Reject sending or fail startup per policy |
| Multiple environment profiles | local + prod both active | Halt startup to prevent mixed configs |
| Local using production host | delivery-mode CAPTURE with real SMTP host | Reject sending/startup and report mismatch |
| Test having real SMTP path | No mock/fake gateway while prod credentials exist | Reject or disable network sending path |
| Staging using prod secrets | Endpoint, account, or secret does not belong to staging | Halt deployment/startup via control check |
| Staging receives non-allowlisted recipient | Real customer email | Reject before calling `JavaMailSender` |
| Prod missing SMTP host/secret | Unresolved placeholder or blank credential | Fail config check; never fall back to staging |
| Prod missing required TLS policy | STARTTLS not required with username/password | Halt or reject unsafe configuration |

To catch profile mistakes right at startup, inspect **Environment.getActiveProfiles()** alongside `MailPolicy` properties in an initialization component. Example policy validation:

~~~java
import jakarta.annotation.PostConstruct;
import java.util.Arrays;
import java.util.Set;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class MailEnvironmentGuard {
    private static final Set<String> ENVIRONMENTS =
            Set.of("local", "test", "staging", "prod");

    private final Environment environment;
    private final MailPolicy policy;

    public MailEnvironmentGuard(
            Environment environment,
            MailPolicy policy) {
        this.environment = environment;
        this.policy = policy;
    }

    @PostConstruct
    void verify() {
        long selected = Arrays.stream(environment.getActiveProfiles())
                .filter(ENVIRONMENTS::contains)
                .count();

        if (selected != 1) {
            throw new IllegalStateException(
                    "Exactly one mail environment profile is required");
        }

        boolean prod = Arrays.asList(environment.getActiveProfiles())
                .contains("prod");
        if (prod && policy.deliveryMode() != MailPolicy.DeliveryMode.LIVE) {
            throw new IllegalStateException(
                    "Production requires LIVE mail policy");
        }
    }
}
~~~

The example checks two basic rules; real systems should also verify **exact mode per profile, allowed hosts, TLS, and security parameters**. If other business profiles exist, do not reject them; count only the four environment profiles defined as mutually exclusive.

This check depends on **MailPolicy** being registered via `@EnableConfigurationProperties` as shown earlier. If an app relies on Spring's **default** profile during development, adjust the required-profile rule accordingly. Never bolt an overly strict guard onto a multi-environment app without establishing an official profile selection scheme.

## 13. Verification workflow from local to production

A common progression:

~~~text
LOCAL
  Build valid email content
  SMTP sink captures it
  Developer inspects HTML/attachments
       |
       v
TEST / CI
  Business rules and MailGateway tested via mocks/fakes
  SMTP integration tests use isolated test server
  No access to real credentials/providers
       |
       v
STAGING
  Staging deployment config and secrets
  TLS/AUTH, MIME, size limits, provider events
  Send only to allowlisted / sandbox recipients
       |
       v
PRODUCTION
  Deployment system selects prod explicitly
  Production secrets, TLS, monitoring, and alerts
  Send to real recipients per business policy
~~~

### Locally

Start the SMTP sink, then run the app with the `local` profile. Trigger a send from UI or API and check the message in the sink UI. Test plain text, HTML, Unicode, attachments, and invalid recipient cases.

### In CI

Activate **test** via `@ActiveProfiles` or test runner configuration. Verify mocks/fakes receive the expected data and no path reaches production SMTP. When protocol tests are needed, spin up a temporary SMTP server on an isolated port with small fixtures, torn down afterward.

### In staging

Use **staging secrets** and a dedicated SMTP sandbox. Exercise the same network path as runtime, checking TLS negotiation, AUTH, and recipient policies. You may send to an approved test mailbox; never use real customer lists.

### In production

Apply production configuration through the deployment system, verifying properly scoped secrets and SMTP provider status. When a smoke test is needed, use an approved test account and an email clearly marked as an operational test. Monitor submission and delivery events rather than blasting test mails just to see "if it works."

## 14. Handling errors differently by environment

| Scenario | Local | Test | Staging | Production |
|---|---|---|---|---|
| Cannot connect to SMTP | Check sink/port/network | If mocked, should not depend on SMTP; check integration test server | Check staging provider, TLS/firewall | Track incident, queues, and bounded retries |
| SMTP AUTH failure | Sinks usually need no AUTH | Never use real credentials | Check staging secret/scope/permissions | Check rotation, account policy, secrets, and alerts |
| Wrong content/MIME | Inspect email in sink | Assert on message/serialized MIME | End-to-end test with sandbox | Fix templates through release process |
| Wrong recipient | Synthetic data still needs control | Fixtures must stay isolated with no real send path | Guard/allowlist must reject | Business rules and recipient authorization |
| Provider temporarily down | Can restart local sink | Mock tests unaffected | Reconcile events and retry | Queue/outbox, timeouts, backoff, alerts |
| Missing from Inbox | Check sink; no real Inbox | Not a unit-test goal | Check sandbox/provider event definitions | Distinguish SMTP accepted, relay, bounce, mailbox, and filters |

Some errors leave **uncertainty about whether the message was sent**, such as losing the connection right after the SMTP server received the full body yet before the success reply reached the client. Retrying then can create duplicate emails. Track an uncertain submission state and reconcile using provider capabilities where available, especially for critical notifications.

### Logs must inform without leaking data

Safe to log:

~~~text
environment=staging
mailMode=SANDBOX
smtpEndpointClass=staging-provider
mailRequestId=mail-2048
recipientCount=1
event=SMTP_SUBMISSION_ACCEPTED
~~~

Never log:

~~~text
smtpPassword=...
oauthAccessToken=...
fullMimeBody=...
authorizationHeader=...
~~~

Provider names, hosts, or usernames can also be sensitive internal details depending on environment; log only what operations need while complying with organizational policy.

## 15. Frequently asked questions

**Do I need four `JavaMailSender` beans in one application?** Usually no. If each running process activates **one environment profile**, one `JavaMailSender` bean configured for that environment suffices. When multiple SMTP accounts are needed simultaneously in one instance, configure multiple qualified beans or a routing abstraction.

**Can I set `spring.mail.host` in `application.yml` and override it per profile?** Technically yes, yet if the base host is production, forgetting or mis-specifying a profile can trigger accidental sends. For sensitive settings, keeping the base free of real hosts or defaulting to a non-sending mode is safer.

**Does `application-test.yml` automatically stop tests from sending mail?** No. That file only supplies properties when the `test` profile is active. You must mock/fake `JavaMailSender`, point at a test SMTP server, or select a matching `MailGateway`.

**Does `@ActiveProfiles("test")` block network access?** No. It only activates the `test` profile for the Spring test context; if code or tests directly open network connections to a real provider, the profile cannot stop it. Design safe sending paths and test isolation.

**Why disable STARTTLS locally yet enable it in staging/prod?** A local SMTP sink on loopback may exist purely to capture messages without TLS/AUTH; staging/prod talk to providers over networks and must protect credentials and data. When local uses a remote SMTP server, apply TLS as required by that remote server.

**Do enabling TLS and AUTH guarantee emails will be delivered?** No. TLS protects the connection; AUTH proves the client can log in; the SMTP server still checks sender/recipient policies, quotas, size limits, and downstream hops.

**Should staging and production share one SMTP account to reduce config?** No. Separating credentials limits blast radius if staging secrets leak or send unintended mail, and allows separate permissions and quotas.

**Should tests automatically send real emails to developers' inboxes?** Only in explicitly designed integration or smoke tests with controlled recipients and infrastructure. Unit tests and CI should default to fakes/mocks or an SMTP sink.

## 16. Principles for environment-based sender configuration

Every environment must clearly answer three questions: **Where will `JavaMailSender` connect? Who is allowed to receive mail? When sending fails, how does the system know and respond?**

| Profile | Desired sending target | Key guardrails |
|---|---|---|
| **local** | SMTP sink for developers to view mail | Never connect accidentally to real provider |
| **test** | Mock, recording fake, or test SMTP server | No real secrets/recipients; repeatable tests |
| **staging** | Staging SMTP sandbox/relay | Dedicated credentials, TLS, recipient allowlist, provider policy |
| **prod** | Real SMTP provider | Production secrets, TLS, sending rights, retries/queues, monitoring |

With **Spring Framework Mail**, the standard approach is **the same business code and `JavaMailSender` API**, separating configuration via **`application-{profile}.yml`**, environment variables/secrets, and matching beans or policies. Validate the selected profile at startup, forbid mixed configurations, verify sending paths across local/test/staging before production, and always distinguish **SMTP submission acceptance** from **delivery to the recipient's mailbox**.
