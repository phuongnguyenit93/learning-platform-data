# Testing TLS and Authentication in an Isolated Environment

When a Spring application sends emails over SMTP, correctness does not lie solely in message contents or `JavaMailSender.send(...)` returning normally. The system must also ensure that connections to the SMTP server actually use TLS when required, server certificates are validated properly, invalid credentials are rejected, and the application never silently downgrades to an unencrypted connection when security settings are missing.

These behaviors require **integration testing in an isolated environment**: the application connects to a test-controlled SMTP server, never connects to real mail accounts, does not depend on the Internet, and never sends emails to unintended recipients. This guide focuses on setting up the test environment, distinguishing **STARTTLS** from **SMTPS (implicit TLS)**, testing SMTP AUTH, verifying certificate trust and hostnames, handling negative failure cases, and designing repeatable tests.

**Core principle:** A test that "successfully sent an email" does not prove TLS or authentication was enforced. Tests must intentionally configure insecure conditions and verify that the client or server **rejects** them.

## 1. Goals of Secure SMTP Integration Testing

A unit test can mock `JavaMailSender` to verify the service invokes `send` once with the right Subject and recipient. However, mocks cannot observe TLS handshakes or protocol authentication:

~~~text
Unit test
    OrderMailService
          |
          v
    Mock JavaMailSender
          |
          v
      verify(send)

No network, SMTP greeting, TLS handshake, or AUTH.
~~~

Security integration tests must run over real transport:

~~~text
Spring service / JavaMailSenderImpl
                |
                | TCP over loopback/container network
                v
       Controlled SMTP test server
                |
          +-----+------+
          |            |
       STARTTLS       SMTP AUTH
          |            |
          v            v
     Certificate    Credentials/
     verification    auth policy
                |
                v
     Captured MIME message
~~~

A strong test suite should answer:

1. Does the client connect to the **exact test endpoint**, rather than production SMTP?
2. With STARTTLS, does the server advertise STARTTLS and does the client upgrade the connection before transmitting sensitive data?
3. If the server does not support STARTTLS yet policy requires TLS, does the operation **fail**?
4. Are certificates issued by a trusted test CA accepted?
5. Are untrusted, expired, or hostname-mismatched certificates rejected?
6. When SMTP AUTH is required, are valid credentials accepted and invalid credentials rejected?
7. If the server mandates AUTH yet the client does not configure AUTH, does sending fail?
8. When handshake or AUTH fails, does the test server receive zero messages?
9. Are failures logged without leaking passwords, tokens, or email contents?
10. Are tests stable when run repeatedly, in parallel, or when CI has no Internet access?

## 2. Three SMTP Modes to Distinguish

In mail environments, the phrase "SMTP TLS" can refer to different connection mechanisms.

| Mode | How It Is Established | Common Port | Key Jakarta Mail Properties |
| --- | --- | --- | --- |
| **Plaintext SMTP (no TLS)** | Plain TCP connection, no TLS upgrade | 25 or test port | Neither `ssl.enable` nor `starttls` enabled |
| **SMTP + STARTTLS** | Plain SMTP connection upgraded via `STARTTLS` command | 587 | `mail.smtp.starttls.enable`, `mail.smtp.starttls.required` |
| **SMTPS / implicit TLS** | TLS handshake immediately on socket open, before SMTP exchange | 465 | `mail.smtp.ssl.enable` |

The ports in the table are deployment conventions, **not security mechanisms**. A test server may use any dynamic port. Security depends on the actual negotiated protocol and client policy, not merely assigning port 465 or 587.

### STARTTLS

STARTTLS typically follows this flow:

~~~text
Client                                  SMTP server
   |                                         |
   |-- TCP connect ------------------------->|
   |<----------------------- 220 greeting ---|
   |-- EHLO client.example ----------------->|
   |<----------------------- 250-STARTTLS ---|
   |-- STARTTLS ---------------------------->|
   |<----------------------- 220 Ready ------|
   |===== TLS handshake + cert verify ======|
   |-- Re-EHLO over TLS connection --------->
   |<----------------------- 250-AUTH -------|
   |-- AUTH ... ---------------------------->|
   |<----------------------- auth result ----|
   |-- MAIL FROM / RCPT TO / DATA --------->|
~~~

SMTP commands before TLS, such as the greeting and initial EHLO, are not protected by TLS. After STARTTLS, the client typically re-issues EHLO to retrieve updated capabilities advertised over the encrypted channel.

### Enabling STARTTLS Alone Is Not Enough for Mandatory Policy

When a client configures:

~~~properties
mail.smtp.starttls.enable=true
~~~

this permits STARTTLS if the server supports it. If policy requires **never sending without TLS**, you must also add:

~~~properties
mail.smtp.starttls.required=true
~~~

A critical negative test is connecting to a server **not advertising STARTTLS** and confirming that sending fails instead of silently sending unencrypted.

### SMTPS / Implicit TLS

In SMTPS, the client initiates TLS before any SMTP greeting:

~~~text
Client                                      Server
   |                                          |
   |===== TLS handshake + cert verify =======|
   |<---------------------- 220 greeting -----|
   |-- EHLO --------------------------------->|
   |-- AUTH / MAIL FROM / DATA ... ---------->|
~~~

For Jakarta Mail SMTP transport, **mail.smtp.ssl.enable=true** requests implicit TLS. There is no need to simultaneously require STARTTLS on the same connection.

### AUTH Is Not TLS

**SMTP AUTH** proves the sender's identity to the server. **TLS** protects the transport channel and verifies the server the client connects to. A test where authentication succeeds over plaintext proves nothing about transport security; many AUTH mechanisms transmit credentials in ways unsafe over unencrypted networks.

Therefore, separate two test categories:

- **Authentication correctness:** valid/invalid/missing credentials; are allowed AUTH mechanisms enforced?
- **Transport security:** mandatory TLS, certificate trust/hostname verification, no downgrade.

Then add combined tests proving **AUTH is only performed according to TLS policy**.

## 3. JavaMailSenderImpl Properties to Test

Spring Framework provides **JavaMailSenderImpl** to configure host, port, username, password, and Jakarta Mail properties.

STARTTLS connection example:

~~~java
import java.util.Properties;
import org.springframework.mail.javamail.JavaMailSenderImpl;

JavaMailSenderImpl sender = new JavaMailSenderImpl();
sender.setHost("localhost");
sender.setPort(1587);          // Fixture port, not production
sender.setUsername("mailer");
sender.setPassword("test-password");

Properties props = sender.getJavaMailProperties();
props.put("mail.transport.protocol", "smtp");
props.put("mail.smtp.auth", "true");
props.put("mail.smtp.starttls.enable", "true");
props.put("mail.smtp.starttls.required", "true");
props.put("mail.smtp.ssl.checkserveridentity", "true");
props.put("mail.smtp.connectiontimeout", "2000");
props.put("mail.smtp.timeout", "2000");
props.put("mail.smtp.writetimeout", "2000");
~~~

This is a client configuration example. For the test connection to succeed, the fixture must genuinely advertise STARTTLS, present a certificate matching the hostname and trusted by the client, and support the configured AUTH mechanism.

### Property Meanings

| Property | Meaning | Testing Notes |
| --- | --- | --- |
| **mail.smtp.auth** | Client uses SMTP AUTH | Server must enforce AUTH for invalid-credentials tests to be meaningful |
| **mail.smtp.starttls.enable** | Allows STARTTLS upgrade | Alone does not enforce fail-closed policy |
| **mail.smtp.starttls.required** | Mandates STARTTLS when using SMTP | Servers lacking STARTTLS must be rejected |
| **mail.smtp.ssl.enable** | Uses TLS from connection start (implicit TLS) | Do not confuse with STARTTLS |
| **mail.smtp.ssl.checkserveridentity** | Verifies hostname identity in certificate | Never disable just to make tests green |
| **mail.smtp.ssl.protocols** | Restricts allowed TLS protocol versions | Match real JDK/server support; avoid obsolete protocols |
| **mail.smtp.connectiontimeout** | Timeout for opening TCP connection | Prevents tests hanging when fixture is down |
| **mail.smtp.timeout** | Socket read timeout | Unresponsive test server fails boundedly |
| **mail.smtp.writetimeout** | Socket write timeout | Useful when server/network stalls |
| **mail.debug** | Jakarta Mail protocol debug logging | Do not enable carelessly as it may leak sensitive data |

The timeouts above are in **milliseconds**. The illustrative 2000 ms value suits some CI environments; on overloaded runners you may need a configurable limit. Never set infinite timeouts when tests must fail cleanly.

### Equivalent Spring Boot Configuration

~~~yaml
spring:
  mail:
    host: localhost
    port: 1587
    username: mailer
    password: test-password
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
      mail.smtp.connectiontimeout: 2000
      mail.smtp.timeout: 2000
      mail.smtp.writetimeout: 2000
~~~

Never use these test values in production. With Spring Boot, **JavaMailSender** availability also depends on active dependencies, mail properties, and auto-configuration.

## 4. Environment Isolation Principles

A secure SMTP integration test should have these characteristics:

1. **Runs locally/in container:** the SMTP server is a fixture started and stopped by the test or CI.
2. **No real credentials:** username/password are test values with no permission to send external mail.
3. **No Internet sending:** network ports and firewall/egress are restricted; the server only captures messages or delivers to test mailboxes.
4. **Dedicated or dynamic ports:** avoid collisions with other servers or parallel tests.
5. **Test certificates:** custom test CA/server certs; never use production private keys.
6. **State cleanup:** reset mailboxes/received messages, users, and queues between tests.
7. **Finite timeouts:** prevent CI from hanging if a server stops responding.
8. **Never disable security to pass tests:** never use trust-all or allow-any-credentials as proof of proper TLS/AUTH.
9. **Include negative tests:** wrong certificate, wrong hostname, wrong credentials, and missing STARTTLS.
10. **Observable:** tests inspect both client outcomes and server-captured messages.

### Proper Network Diagram

~~~text
Test JVM / Spring context
          |
          | TCP to localhost:dynamicPort
          v
SMTP fixture
          |
          +-- Local test users
          +-- Test TLS keypair
          +-- Message capture
          +-- Protocol capability configuration
          |
          X No relay to the Internet
~~~

Never design integration tests by sending emails to Gmail, Outlook, or a real SMTP provider and checking an Inbox. That approach is unstable, slow, bound by rate limits/networks, and risks unintended email distribution.

## 5. Choosing the Right Test Tool

SMTP test tools have distinct capabilities. Do not assume all of them can verify TLS and AUTH equally.

| Tool Type | Suitable For Testing | Caveats to Watch |
| --- | --- | --- |
| **Mock JavaMailSender** | Service send-API calls, MIME construction | No real SMTP/TLS/AUTH |
| **GreenMail** (embedded SMTP) | Sending/receiving and managing test mailboxes; some setups support SSL/auth | Verify fixture actually enforces TLS/AUTH per test goal |
| **Mailpit/MailHog** or SMTP capture server | Capturing and viewing messages, payload API checks | Default capture setups may accept mail without AUTH or TLS |
| **Dedicated containerized SMTP server** | Fine-grained control of STARTTLS, SMTPS, users, and certs | Higher setup cost, requires certificate management |
| **Provider test/sandbox API** | Verifying contract with a specific vendor | May depend on network, quotas, and sandbox features; not strictly isolated |

**GreenMail** is an easy starting point for in-JVM integration tests. For scenarios that strictly require verifying **certificate chain/hostname validation, TLS downgrade protection, or specific AUTH mechanisms**, you may need a more strictly configured SMTP fixture or a test-managed server container.

Never use an SMTP capture server that **accepts any credentials by default** to conclude the application enforces SMTP AUTH. Such a test passes even with a wrong username or password.

## 6. SMTP AUTH Test Example with GreenMail

**GreenMail** is an SMTP/IMAP/POP3 server for testing. You can embed it in JUnit 5 to send messages over sockets and inspect received mailboxes without Internet SMTP.

Assume the project uses Spring Mail, Jakarta Mail, JUnit Jupiter, and a GreenMail dependency compatible with your Spring version. Select the Jakarta-compatible GreenMail artifact to avoid mixing **javax.mail** and **jakarta.mail** in the same test.

### Starting the Test Server on a Dynamic Port

~~~java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

import static org.junit.jupiter.api.Assertions.*;

class SmtpAuthIntegrationTest {

    private GreenMail smtp;

    @BeforeEach
    void startServer() {
        smtp = new GreenMail(
                new ServerSetup(
                        0,
                        "127.0.0.1",
                        ServerSetup.PROTOCOL_SMTP
                )
        );
        smtp.start();
        smtp.setUser(
                "recipient@local.test",
                "recipient",
                "recipient-secret"
        );
        smtp.setUser(
                "mailer@local.test",
                "mailer",
                "mailer-secret"
        );
    }

    @AfterEach
    void stopServer() {
        if (smtp != null) {
            smtp.stop();
        }
    }

    private JavaMailSenderImpl sender(
            String username,
            String password
    ) {
        JavaMailSenderImpl result = new JavaMailSenderImpl();
        result.setHost("127.0.0.1");
        result.setPort(smtp.getSmtp().getPort());
        result.setUsername(username);
        result.setPassword(password);

        result.getJavaMailProperties().put(
                "mail.smtp.auth", "true"
        );
        result.getJavaMailProperties().put(
                "mail.smtp.connectiontimeout", "2000"
        );
        result.getJavaMailProperties().put(
                "mail.smtp.timeout", "2000"
        );
        result.getJavaMailProperties().put(
                "mail.smtp.writetimeout", "2000"
        );
        return result;
    }

    @Test
    void correctCredentialsCanSendMessage() throws Exception {
        JavaMailSenderImpl client =
                sender("mailer", "mailer-secret");

        MimeMessage message = client.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom("mailer@local.test");
        helper.setTo("recipient@local.test");
        helper.setSubject("SMTP AUTH test");
        helper.setText("Test-environment-only message.");

        client.send(message);

        assertTrue(smtp.waitForIncomingEmail(5000, 1));
        assertEquals(1, smtp.getReceivedMessages().length);
        assertEquals(
                "SMTP AUTH test",
                smtp.getReceivedMessages()[0].getSubject()
        );
    }

    @Test
    void wrongCredentialsAreRejected() {
        JavaMailSenderImpl client =
                sender("mailer", "wrong-password");

        assertThrows(
                MessagingException.class,
                client::testConnection
        );
        assertEquals(0, smtp.getReceivedMessages().length);
    }
}
~~~

The example above runs **unencrypted SMTP on loopback**, solely to illustrate isolated authentication testing. **Never send real credentials over plaintext SMTP** and never mistake this for a TLS test. Each test creates a fresh fixture, uses a dynamic port, provisions test accounts, and stops the server in **@AfterEach**.

**Precondition for the wrong-credentials test:** the fixture must **genuinely require SMTP AUTH and reject wrong passwords**. If your GreenMail version/configuration allows unauthenticated relay or accepts any credentials, the negative test must fail or the fixture must be reconfigured; never treat a permissive server as proof of AUTH enforcement. GreenMail APIs and behavior can vary by version, so choose dependencies and test setups matching your project's Jakarta Mail stack.

### Why Use testConnection() for Authentication?

**JavaMailSenderImpl.testConnection()** opens a transport connection and performs the handshake/authentication per client settings **without sending a MIME message**. Thus, wrong-credentials tests can verify failures without generating unintended emails.

When you need to verify the full SMTP submission flow, use **send(...)** with a test recipient and inspect the server side. Both test styles serve distinct roles.

## 7. Testing AUTH Rejection When Credentials Are Missing

Distinguish two directions:

1. **Client requests auth** and supplies username/password.
2. **Server requires auth** before allowing submission.

A test that only sets **mail.smtp.auth=true** on the client while the test server permits anonymous relay can mask a server configuration flaw.

### Basic AUTH Matrix

| Client Configuration | Server Policy | Expected Outcome |
| --- | --- | --- |
| Valid username/password, AUTH enabled | AUTH required | Connection succeeds |
| Wrong password, AUTH enabled | AUTH required | Authentication rejected |
| Non-existent username | AUTH required | Authentication rejected |
| No username/password | AUTH required | Send or connect rejected at server-enforced step |
| AUTH disabled on client | AUTH required | Mail cannot be relayed |
| Valid credentials without TLS, server requires TLS before AUTH | Protect credentials with TLS | Credentials never sent over plaintext |

The last scenario requires a fixture supporting real TLS policies; it cannot be proven with a passive SMTP capture server that accepts mail without enforcing STARTTLS.

### Do Not Assert Errors Using a Fixed Message String

Depending on the library/transport and failure stage, tests may observe **AuthenticationFailedException**, **MessagingException**, or a Spring Mail wrapper. Do not assume every auth failure surfaces with one fixed English string such as "535 Authentication failed".

A robust test should verify:

- The operation fails with the expected exception type/category.
- No message is accepted by the server.
- There is no fallback to anonymous relay.
- Credentials do not appear in test logs.

When deterministic SMTP reply codes exist, you can add code assertions in tests dedicated to that fixture.

## 8. Testing Mandatory STARTTLS and Downgrade Protection

STARTTLS is the most common case when clients connect to an SMTP submission port. A subtle pitfall: if **mail.smtp.starttls.enable=true** yet **mail.smtp.starttls.required** is omitted, the client may proceed in plaintext when the server does not advertise STARTTLS.

### Two Modes to Test

~~~text
TEST A - SMTP server with STARTTLS
  SMTP greeting -> EHLO -> 250-STARTTLS
  -> TLS handshake
  -> authenticate
  -> send
  Expected: SUCCESS if certificate/credentials are valid

TEST B - SMTP server not advertising STARTTLS
  SMTP greeting -> EHLO -> no 250-STARTTLS
  -> client configured with starttls.required=true
  Expected: FAIL, message not sent
~~~

### Fail-Closed Configuration

~~~java
JavaMailSenderImpl sender = new JavaMailSenderImpl();
sender.setHost("localhost");
sender.setPort(smtpFixturePort);

sender.getJavaMailProperties().put(
        "mail.smtp.starttls.enable", "true"
);
sender.getJavaMailProperties().put(
        "mail.smtp.starttls.required", "true"
);
sender.getJavaMailProperties().put(
        "mail.smtp.ssl.checkserveridentity", "true"
);
~~~

### Integration Test Pattern Against a Fixture Contract

Assuming a test fixture exposes an API to start SMTP with or without STARTTLS support, a test can be structured as:

~~~java
@Test
void refusesServerWithoutStartTls() {
    // Custom fixture implemented by the project:
    try (SmtpFixture fixture =
                 SmtpFixture.startWithoutStartTls()) {

        JavaMailSenderImpl client = senderFor(
                "localhost",
                fixture.port(),
                true  // require STARTTLS
        );

        assertThrows(
                Exception.class,
                client::testConnection
        );
        assertEquals(0, fixture.acceptedMessageCount());
    }
}
~~~

**SmtpFixture** and **senderFor** are hypothetical project helper classes, **not built-in Spring or GreenMail APIs**. This pattern expresses the enforcement requirement: when the server lacks STARTTLS, the client must fail. Real implementations may use a dedicated SMTP container or an embedded fixture controlling EHLO capabilities.

### Why Is This a Real Security Test?

If the `required` property is omitted, the system might still transmit messages to an SMTP server despite a TLS-only policy. This negative test catches fail-open configurations prior to deployment. A test that only succeeds against a STARTTLS-enabled server cannot detect a client silently accepting plaintext elsewhere.

### Note on STARTTLS Stripping

An attacker can strip the STARTTLS capability during the unencrypted EHLO phase. With **required=true**, failing to observe STARTTLS causes the client to **fail**. Combining this with hostname/certificate verification after TLS upgrade reduces server impersonation risk.

Do not conclude all forms of MITM are prevented just because one missing-STARTTLS test passes. Overall security also depends on truststores, DNS, network controls, TLS implementation, and server configuration.

## 9. Testing Implicit TLS (SMTPS)

In implicit TLS mode, the client must open with a TLS handshake. A plaintext client connecting to an implicit TLS port or vice versa normally fails protocol negotiation.

### Client Configuration

~~~java
JavaMailSenderImpl sender = new JavaMailSenderImpl();
sender.setHost("localhost");
sender.setPort(smtpsFixturePort);
sender.setUsername("mailer");
sender.setPassword("test-password");

sender.getJavaMailProperties().put(
        "mail.smtp.ssl.enable", "true"
);
sender.getJavaMailProperties().put(
        "mail.smtp.ssl.checkserveridentity", "true"
);
sender.getJavaMailProperties().put(
        "mail.smtp.auth", "true"
);
~~~

### Cases to Test

| Case | Fixture | Client | Result |
| --- | --- | --- | --- |
| Valid implicit TLS | Valid TLS server/cert | `ssl.enable=true`, valid trust | Connection and AUTH succeed |
| Untrusted certificate | TLS server/unfamiliar cert | `ssl.enable=true`, default trust | TLS handshake rejected |
| Wrong hostname | TLS server/trusted CA but wrong name | `checkserveridentity=true` | Rejected |
| Client TLS disabled | Server requires immediate TLS | `ssl.enable=false` | Protocol mismatch; cannot send |
| Valid TLS yet wrong password | Server enforces AUTH | `ssl.enable=true`, wrong password | Authentication fails |

Do not set **mail.smtp.starttls.required=true** simultaneously as a substitute for **mail.smtp.ssl.enable=true**. They are distinct protocol flows. Select the mode matching the server under test.

## 10. Testing Certificates and Truststores

A meaningful TLS test must verify the **chain of trust** and **hostname identity**, not merely socket encryption.

### Test Certificates

A suitable fixture can provide:

- A server certificate containing a **Subject Alternative Name (SAN)** matching the test hostname, such as **localhost**.
- A private key used strictly inside the fixture.
- A client truststore containing the trusted test CA or certificate.
- Server configuration using that certificate for STARTTLS or implicit TLS.

In test environments, you can generate a **self-signed certificate** or private test CA. Self-signed is fine as long as the test client is configured to trust that specific certificate/CA; what matters is never enabling trust-all mechanisms.

### Example Generating PKCS#12 with keytool

The following commands illustrate creating a certificate for a local fixture. Run in a test environment, and **never share production private keys or certificates**.

~~~bash
keytool -genkeypair \
  -alias smtp-local \
  -keyalg RSA -keysize 3072 \
  -validity 7 \
  -storetype PKCS12 \
  -keystore smtp-server.p12 \
  -storepass changeit \
  -keypass changeit \
  -dname "CN=localhost" \
  -ext "SAN=dns:localhost"

keytool -exportcert \
  -alias smtp-local \
  -storetype PKCS12 \
  -keystore smtp-server.p12 \
  -storepass changeit \
  -rfc -file smtp-server.crt

keytool -importcert -noprompt \
  -alias smtp-local \
  -file smtp-server.crt \
  -storetype PKCS12 \
  -keystore smtp-client-trust.p12 \
  -storepass changeit
~~~

The password **changeit** is purely illustrative inside an isolated fixture. Never use hard-coded passwords or test private key files in production. Tools and Java versions vary in available key algorithms, PKCS#12 defaults, and cipher suites; adjust for your JDK.

Because the SAN contains **dns:localhost**, a client connecting via hostname **localhost** matches identity. A client connecting via IP **127.0.0.1** will not necessarily match this certificate: to support IP connections, the certificate needs an IP SAN, or you can intentionally test hostname mismatch.

### A Truststore Does Not Skip Hostname Validation

Two distinct steps:

1. **Trust validation:** does the certificate chain lead to an accepted trust anchor?
2. **Identity validation:** does the certificate represent the hostname the client intended to reach?

If a self-signed certificate is imported into the truststore, it may pass trust validation. Yet if its SAN is **localhost** while the client connects to **127.0.0.1**, hostname validation must fail when enabled.

### Never Use Trust-All to Turn Tests Green

Settings like:

~~~properties
mail.smtp.ssl.trust=*
mail.smtp.ssl.checkserveridentity=false
~~~

weaken or bypass critical TLS checks. **Never use them to prove TLS security.** In some local setups, developers use trust-all to capture messages quickly, yet that is unsuitable for certificate tests and must never be copied to production.

## 11. Configuring a Dedicated Truststore for Test Clients

A quick approach is launching the test JVM with **javax.net.ssl.trustStore**, **javax.net.ssl.trustStorePassword**, and **javax.net.ssl.trustStoreType**. However, those affect TLS for the **entire process** and can cause unwanted interference across parallel integration tests.

For tests requiring per-client isolation, build an **SSLSocketFactory** backed by the exact test truststore and pass that factory to Jakarta Mail.

### Loading a PKCS#12 Truststore with JSSE

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManagerFactory;

public final class SmtpTestTls {

    private SmtpTestTls() {
    }

    public static SSLSocketFactory socketFactory(
            Path truststorePath,
            char[] truststorePassword
    ) throws Exception {
        KeyStore trustStore = KeyStore.getInstance("PKCS12");

        try (InputStream input =
                     Files.newInputStream(truststorePath)) {
            trustStore.load(input, truststorePassword);
        }

        TrustManagerFactory trustManagerFactory =
                TrustManagerFactory.getInstance(
                        TrustManagerFactory.getDefaultAlgorithm()
                );
        trustManagerFactory.init(trustStore);

        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(
                null,
                trustManagerFactory.getTrustManagers(),
                new SecureRandom()
        );
        return sslContext.getSocketFactory();
    }
}
~~~

This function uses the Java Secure Socket Extension (JSSE) to obtain trust managers from the test-generated PKCS#12 store. It does **not** install an all-trusting trust manager. Only certificate chains valid against that truststore are accepted per the trust manager's policy.

### Attaching the Socket Factory to JavaMailSenderImpl

~~~java
import javax.net.ssl.SSLSocketFactory;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class SmtpTestSenders {

    private SmtpTestSenders() {
    }

    public static JavaMailSenderImpl startTls(
            String hostname,
            int port,
            SSLSocketFactory sslSocketFactory
    ) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(hostname);
        sender.setPort(port);
        sender.setUsername("mailer");
        sender.setPassword("test-password");

        sender.getJavaMailProperties().put(
                "mail.smtp.auth", "true"
        );
        sender.getJavaMailProperties().put(
                "mail.smtp.starttls.enable", "true"
        );
        sender.getJavaMailProperties().put(
                "mail.smtp.starttls.required", "true"
        );
        sender.getJavaMailProperties().put(
                "mail.smtp.ssl.checkserveridentity", "true"
        );
        sender.getJavaMailProperties().put(
                "mail.smtp.ssl.socketFactory",
                sslSocketFactory
        );
        sender.getJavaMailProperties().put(
                "mail.smtp.connectiontimeout", "2000"
        );
        sender.getJavaMailProperties().put(
                "mail.smtp.timeout", "2000"
        );
        sender.getJavaMailProperties().put(
                "mail.smtp.writetimeout", "2000"
        );
        return sender;
    }
}
~~~

In Jakarta Mail/Angus Mail versions supporting **mail.smtp.ssl.socketFactory** as an object property, that factory is used for TLS connections. When using another version, verify support and property names for your runtime implementation. **mail.smtp.ssl.checkserveridentity=true** must remain enabled so a custom truststore does not bypass hostname checks.

The advantage of this approach is that tests can construct multiple clients with distinct truststores in the same JVM without mutating JVM-wide properties and colliding.

### Do Not Arbitrarily Set a Global SSLSocketFactory

Calls like **SSLContext.setDefault(...)** or mutating truststore system properties at runtime can affect other HTTPS/SMTP connections in the application and introduce test-order dependencies. If using process-wide settings, run those integration tests in a **separate forked JVM** with fixed startup options.

## 12. Positive and Negative Certificate Tests

A TLS fixture can stand up two logical servers:

- **Server A:** certificate signed by the test CA, SAN is `localhost`.
- **Server B:** certificate signed by a different test CA, or absent from the client's truststore.

With that setup, the same client can exercise both trust validation and hostname validation.

### Valid Certificate Test

~~~text
Fixture A:
  Hostname: localhost
  Certificate SAN: dns:localhost
  Client truststore: contains test CA/certificate of A
  STARTTLS: advertised and required
  AUTH: valid credentials

Expected:
  JavaMailSenderImpl.testConnection() succeeds
~~~

### Untrusted Certificate Test

~~~text
Fixture B:
  Hostname: localhost
  Certificate SAN: dns:localhost
  Certificate CA: not in client truststore

Expected:
  TLS handshake rejected
  Neither AUTH credentials nor MIME message sent
~~~

### Wrong Hostname Test

~~~text
Fixture A:
  Bind address: 127.0.0.1
  Certificate SAN: dns:localhost (no IP SAN)
  Client host: 127.0.0.1
  Client truststore: trusts certificate A
  checkserveridentity: true

Expected:
  Certificate chain trusted,
  but identity check rejected
~~~

A key lesson of this test: **never use the same fault to simulate two different conditions**. If the truststore lacks the certificate, a hostname mismatch test will fail at the trust step without proving hostname validation. Intentionally trust the certificate and vary only the target hostname.

### Expired Certificate Test

An expired server certificate must be rejected even if its certificate chain leads to a trusted anchor. In CI, use a fixture certificate generated with intentionally past validity dates or a TLS test fixture capable of presenting an expired certificate during the handshake.

Avoid depending on a temporary certificate that "will start failing in three months"; tests must use controlled fixtures rather than randomly breaking based on calendar date.

### Testing a Different Certificate After Server Rotation

Swap the fixture certificate while keeping hostname and user credentials constant. If the client truststore only trusts the old certificate/CA, the connection must fail. This test catches configurations that silently fell back to **trust-all** during refactoring.

### Assert Pattern for TLS Failures

~~~java
JavaMailSenderImpl client = SmtpTestSenders.startTls(
        "127.0.0.1",
        tlsFixture.port(),
        trustedTestSocketFactory
);

assertThrows(Exception.class, client::testConnection);
assertEquals(0, tlsFixture.acceptedMessageCount());
~~~

In the snippet above, **tlsFixture** and **trustedTestSocketFactory** are project-supplied fixtures; Spring provides no global variables by those names. In real tests, assert the appropriate root exception category rather than bare **Exception.class**, and include a failure message stating whether trust or hostname is under test. The snippet illustrates the verification structure: TLS failures must never result in accepted messages.

## 13. Setting Appropriate TLS Protocol Versions

TLS 1.2 and TLS 1.3 are commonly used across modern JDKs and servers. You can restrict allowed protocols:

~~~java
sender.getJavaMailProperties().put(
        "mail.smtp.ssl.protocols",
        "TLSv1.2 TLSv1.3"
);
~~~

This list is illustrative; client, server, and JDK must support those versions. If production permits only TLS 1.3, the test fixture must also support and enforce the matching policy. Never force a protocol purely because an article mentioned it without checking your runtime environment.

### Anti-Downgrade Protocol Test

~~~text
Client policy: TLSv1.2/TLSv1.3 only
Fixture: only supports legacy protocol disallowed by client
Expected: handshake fails
~~~

Corresponding positive test:

~~~text
Client policy: TLSv1.2/TLSv1.3
Fixture: supports TLSv1.3, valid cert
Expected: handshake succeeds
~~~

Where the fixture exposes TLS session details, record the **negotiated protocol** and cipher suite to confirm the outcome. Never print session secrets or application data.

### Do Not Look Only for a "Padlock" Indicator

In Java integration tests, succeeding with **ssl.enable=true** or **starttls.required=true** is partial evidence. To prove which TLS version and cipher were negotiated, inspect TLS session data or fixture instrumentation. Never infer the negotiated TLS version solely from client properties.

## 14. SMTP AUTH Over a TLS Connection

An important combined test is verifying the server **only allows AUTH after TLS has been established**.

Expected scenario:

~~~text
SMTP connection
    |
    v
EHLO -> STARTTLS capability
    |
    v
Client STARTTLS + verify cert/hostname
    |
    v
Re-EHLO over encrypted channel
    |
    v
Server advertise/accept AUTH
    |
    v
Valid credentials
    |
    v
MAIL FROM / RCPT TO / DATA
~~~

### Recommended Test Cases

| Test | Fixture | Expected Result |
| --- | --- | --- |
| AUTH after TLS, valid password | Server requires TLS before AUTH | Success |
| AUTH after TLS, wrong password | Server enforces AUTH | Failure |
| No STARTTLS, username/password provided | Server permits AUTH only over TLS | Rejected; credentials never sent in plaintext |
| AUTH disabled on client | Server requires AUTH | Message not sent |
| Untrusted certificate, valid password | TLS handshake fails | Never reaches AUTH |
| Server advertises only an AUTH mechanism disallowed by client | Mechanism policy mismatch | Controlled failure |

With Jakarta Mail, you can restrict AUTH mechanisms when needed:

~~~java
sender.getJavaMailProperties().put(
        "mail.smtp.auth.mechanisms",
        "PLAIN LOGIN"
);
~~~

**PLAIN** and **LOGIN** must never be considered safe over plaintext. They are only appropriate over a properly verified TLS channel. If your provider uses OAuth 2.0/XOAUTH2 or another mechanism, tests must follow that provider's and Jakarta Mail's contract.

### Never Use Production Credentials in Tests

For SMTP usernames/passwords or OAuth tokens:

- Provision dedicated fixture accounts with zero Internet-sending privileges.
- Place test passwords in test-only configuration, never production artifacts.
- If using a provider sandbox, pull secrets from the CI secret store with minimal scope.
- Never log AUTH commands or tokens when debugging is enabled.
- Proactively revoke/rotate test credentials if leaked.

An auth test with a valid username and wrong password only proves the fixture server rejects invalid credentials. It does not prove production is using SMTP AUTH if production routes mail through a different path.

## 15. Integrating with Spring Boot via @DynamicPropertySource

When testing a service that uses a Spring Boot auto-configured **JavaMailSender**, manually instantiating `JavaMailSenderImpl` with `new` can miss property-binding bugs. A test running a Spring context verifies that **spring.mail.*** configuration actually applies to the live sender.

A test server on a dynamic port avoids hard-coding addresses on CI runners. **@DynamicPropertySource** registers the host/port known only after the fixture starts.

### Example Testing Wiring Against GreenMail

~~~java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class SpringMailWiringIntegrationTest {

    private static final GreenMail SMTP = new GreenMail(
            new ServerSetup(
                    0,
                    "127.0.0.1",
                    ServerSetup.PROTOCOL_SMTP
            )
    );

    static {
        SMTP.start();
        SMTP.setUser(
                "recipient@local.test",
                "recipient",
                "recipient-secret"
        );
        SMTP.setUser(
                "mailer@local.test",
                "mailer",
                "mailer-secret"
        );
    }

    @DynamicPropertySource
    static void smtpProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.mail.host", () -> "127.0.0.1");
        registry.add(
                "spring.mail.port",
                () -> SMTP.getSmtp().getPort()
        );
        registry.add("spring.mail.username", () -> "mailer");
        registry.add(
                "spring.mail.password",
                () -> "mailer-secret"
        );
        registry.add(
                "spring.mail.properties.mail.smtp.auth",
                () -> "true"
        );
        registry.add(
                "spring.mail.properties.mail.smtp.connectiontimeout",
                () -> "2000"
        );
        registry.add(
                "spring.mail.properties.mail.smtp.timeout",
                () -> "2000"
        );
    }

    @Autowired
    private JavaMailSender mailSender;

    @Test
    void springBeanSendsToIsolatedServer() throws Exception {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom("mailer@local.test");
        helper.setTo("recipient@local.test");
        helper.setSubject("Mail context test");
        helper.setText("Content inside isolated environment.");

        mailSender.send(message);

        assertTrue(SMTP.waitForIncomingEmail(5000, 1));
        assertEquals(1, SMTP.getReceivedMessages().length);
    }

    @AfterAll
    static void stopServer() {
        SMTP.stop();
    }
}
~~~

This is a test of **Spring context wiring and SMTP AUTH over loopback**, not yet a STARTTLS test. To test TLS, swap the fixture for an SMTP server providing certificates/STARTTLS and register the corresponding TLS properties. In production, Spring Boot mail properties must come from deployment configuration/secret stores, never from test fixtures.

### Choosing a Profile for Integration Tests

A test profile may specify:

~~~yaml
# application-it.yml
spring:
  mail:
    host: localhost
    username: mailer
    password: local-test-secret
    properties:
      mail.smtp.connectiontimeout: 2000
      mail.smtp.timeout: 2000
      mail.smtp.writetimeout: 2000
~~~

In integration tests, **@DynamicPropertySource** can still override host/port and other properties to target the exact fixture. Never let a test profile file accidentally contain a production SMTP host as a fallback value.

### Fixture Lifecycle and Parallel Execution

If each test class manages its own SMTP server:

- Create the server before the Spring context initializes `MailSender`.
- Register the port after the server has bound.
- Stop the server when the test suite/class finishes.
- Avoid sharing fixed ports across parallel tests.
- Prevent mailboxes/received messages from other tests affecting assertions.
- If using static fixtures with Spring context caching, ensure the fixture's lifecycle is no shorter than context reuse.

Another option is using a JUnit 5 extension aligned with GreenMail or Testcontainers lifecycles to reduce boilerplate. Verify version compatibility with JUnit/Spring/Jakarta Mail when choosing an extension.

## 16. Testing SSL Certificates with a Spring Context

For TLS tests, Spring Boot configuration can enable:

~~~yaml
spring:
  mail:
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
~~~

**Enabling the properties** is necessary, yet insufficient to prove TLS is enforced. Tests must also confirm:

1. The fixture actually advertises and implements STARTTLS.
2. The client receives and validates the fixture's certificate.
3. AUTH runs after TLS per policy.
4. Mismatched certificates/hostnames cause the operation to fail.
5. No plaintext fallback occurs.

### Separating Client Policy from Transport Implementation

A testable design uses a dedicated mail configuration class or Spring-managed **JavaMailSenderImpl** allowing injection of a test-specific socket factory/truststore **only under the test profile**. Never embed test truststores in main application code or auto-enable trust-all when running under a test profile.

### Notes on Properties and Placeholders

If the application uses profile-specific properties, make sure the **hostname in the certificate** matches the hostname resolved during tests. In Docker/Testcontainers, clients may connect via **localhost** (mapped port) or a Docker network hostname. The certificate SAN must match the hostname **observed by the client**, not an internal name picked for convenience.

For example, tests from the host JVM over a mapped **localhost** port should use a certificate with SAN **localhost**. If tests run inside container A connecting to a service named **smtp** on the same network, the certificate may need SAN **smtp**. Never fix a mismatch by disabling `checkserveridentity`.

## 17. Testing That the Server Does Not Leak AUTH Over Plaintext

To test an "AUTH only after TLS" policy, an ideal SMTP fixture should control:

- EHLO capabilities advertised before STARTTLS.
- Capabilities advertised after STARTTLS.
- Allowing or disallowing AUTH while the connection is unencrypted.
- Outcomes of valid and invalid AUTH attempts.

Example test flow:

~~~text
Client A:
  auth=true
  starttls.enable=true
  starttls.required=true
  certificate trusted
Expected:
  TLS established
  then AUTH success
  then message accepted

Client B:
  auth=true
  starttls.enable=false
Expected:
  No successful submission
  No authentication secret accepted in plaintext
~~~

If the fixture records a protocol transcript to verify ordering, that transcript may contain sensitive AUTH data. Configure test loggers to **redact credentials** or log only state events like "TLS_UPGRADED", "AUTH_ATTEMPTED", "AUTH_SUCCEEDED"; never print raw base64/auth payloads.

### Do Not Rely on Debug Properties as Sole Proof

Some developers turn on **mail.debug=true** to inspect EHLO/STARTTLS/AUTH. Logs help troubleshooting, yet easily capture unwanted data and can vary by Jakarta Mail implementation. Tests should assert outcomes via the server fixture and client exceptions; protocol logging is strictly an investigative aid.

### AUTH Mechanism Does Not Govern Sender Authorization

Even when AUTH succeeds, a server may enforce policies restricting which `From` addresses a mailer account may send as. If your fixture supports sender authorization, test:

- AUTH with valid user and permitted `From`: accepted.
- AUTH with valid user yet spoofed `From` belonging to another user: rejected per fixture policy.

This differs from testing **SMTP AUTH**. A server can validate username/password without verifying the `From` address, leaving spoofing risks intact. With production providers, verify both verified sender identities and `From`/envelope policies.

## 18. Never Send Real Emails When Tests Fail

Negative tests can easily cause accidental network leaks if the client falls back to default configuration or test code automatically retries via a real SMTP provider.

Key safeguards:

1. **Never leave a production host as fallback** in `application-it`/test properties.
2. **Never use production credentials** in CI or local tests.
3. **Block outbound SMTP egress** to the Internet in test environments where infrastructure allows.
4. Use test/fixture domain recipients, never real mailboxes.
5. Assert the actual host/port of the injected `JavaMailSender` bean.
6. Reset caches/sessions when switching sender configurations between tests.
7. Never design retry workers that hunt for another transport when the test fixture temporarily fails.
8. When a fixture fails to start, **fail the test** instead of running against default settings.

### Asserting JavaMailSenderImpl Host and Port

~~~java
import org.springframework.mail.javamail.JavaMailSenderImpl;

JavaMailSenderImpl implementation =
        (JavaMailSenderImpl) mailSender;

assertEquals("127.0.0.1", implementation.getHost());
assertEquals(
        SMTP.getSmtp().getPort(),
        implementation.getPort()
);
~~~

This cast only works when the Spring context genuinely injects **JavaMailSenderImpl**. If the bean is a custom decorator/proxy, inspect configuration via an interface/fixture or diagnostic adapter rather than casting blindly.

### SMTP Capture Servers Must Not Relay Externally

A misconfigured MTA container can become an open relay or forward test emails to the Internet. Expose ports only to the test network, never publish public endpoints, and explicitly disable relaying. With Docker Compose/Testcontainers, prefer isolated networks and map only required test ports.

## 19. Testing That Messages Remain Intact After TLS/AUTH

TLS and AUTH are transport conditions, yet within the same integration test you can verify message content was submitted properly. This catches encoding or multipart misconfigurations introduced when switching from plaintext SMTP to a real TLS server.

Example with **GreenMail** or a capture-enabled SMTP fixture:

~~~java
MimeMessage message = sender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("mailer@local.test");
helper.setTo("recipient@local.test");
helper.setSubject("Xác nhận đơn hàng có dấu");
helper.setText(
        "Đơn hàng đã xác nhận.",
        "<p>Đơn hàng <strong>đã xác nhận</strong>.</p>"
);

sender.send(message);

MimeMessage received = fixture.receivedMessages()[0];
assertEquals(
        "Xác nhận đơn hàng có dấu",
        received.getSubject()
);
assertTrue(received.isMimeType("multipart/*"));
~~~

**fixture.receivedMessages()** here is a test-built adapter API, not a built-in method on Spring `JavaMailSender`. With GreenMail, use **greenMail.getReceivedMessages()**.

### Why Not Compare Full Raw MIME?

Once serialized, a **MimeMessage** may include library-generated `Message-ID`, `Date`, MIME boundaries, header folding, and transfer encodings. Those details can legitimately vary. Assert meaningful properties:

- Accurate `From` and recipients.
- Subject decoded accurately with Unicode.
- Accurate `text/plain` and `text/html` contents.
- Proper `Content-Type` and `Content-Disposition` on inline images/attachments.
- No unintended recipients present.

Do not treat a changed MIME boundary or transfer encoding as a TLS error. Message submission and transport security are distinct test concerns.

### "Server Captured" Still Does Not Mean "Delivered"

When GreenMail or a fixture captures a message, the test proves SMTP submission to the test server only. It does not prove real-provider Inbox placement, DKIM/SPF/DMARC, spam filtering, or delivery webhooks. Those belong to separate testing layers.

## 20. Testing Failure Cases and Fail-Closed Behavior

A TLS/AUTH test suite needs **both happy paths and negative paths**. Negative cases are especially valuable because they catch security checks being disabled during config edits.

### Minimum Matrix

| Test ID | Condition | Required Outcome |
| --- | --- | --- |
| **TLS-01** | STARTTLS, valid certificate, matching hostname | Connection succeeds |
| **TLS-02** | Client requires STARTTLS, server does not support it | Fails, nothing sent |
| **TLS-03** | Untrusted certificate | Fails, no AUTH/send |
| **TLS-04** | Certificate with mismatched hostname | Fails |
| **TLS-05** | Only policy-disallowed TLS protocol available | Handshake fails |
| **TLS-06** | SMTPS client to SMTPS server, valid cert | Connection succeeds |
| **TLS-07** | Plain SMTP client to implicit TLS server | Fails, nothing sent |
| **AUTH-01** | Valid TLS, valid credentials | Authentication succeeds |
| **AUTH-02** | Valid TLS, wrong password | Authentication rejected |
| **AUTH-03** | Valid TLS, non-existent username | Authentication rejected |
| **AUTH-04** | Server requires AUTH, client unconfigured | Cannot send |
| **AUTH-05** | Server requires TLS before AUTH, client lacks TLS | Credentials never accepted over plaintext |
| **SEC-01** | Spring bean SMTP host differs from fixture | Test fails before emitting mail |
| **SEC-02** | Handshake/auth failure | Zero messages in capture mailbox |
| **SEC-03** | Negative tests enabled | Logs contain no passwords or tokens |

One test class does not have to run the entire matrix. You can split into:

1. **Fast SMTP integration tests:** GreenMail/capture server verifying messages and basic AUTH.
2. **Transport security integration tests:** containers/fixtures with certificates, STARTTLS, and implicit TLS.
3. **Provider contract tests:** vendor sandboxes or test environments if specific vendor requirements exist.

### A Test with Only assertThrows Is Not Enough

Example:

~~~java
assertThrows(Exception.class, client::testConnection);
~~~

The failure could happen because the fixture **never started**, the port was wrong, or DNS failed to resolve - rather than the certificate mismatch under test.

To distinguish causes, the test should confirm:

- The fixture is started and listening.
- Certificate and hostname match the test scenario.
- The client connects to the right fixture port.
- The exception chain reflects the target failure, such as `SSLHandshakeException` or certificate identity validation.
- Zero accepted messages exist on the server.

This prevents negative tests from passing falsely due to unrelated setup bugs.

### Asserting by Root Cause

In Spring Mail, network/Jakarta Mail errors may be wrapped inside **MailException**. A test helper can traverse the cause chain:

~~~java
public static boolean hasCause(
        Throwable error,
        Class<? extends Throwable> expectedType
) {
    Throwable current = error;
    while (current != null) {
        if (expectedType.isInstance(current)) {
            return true;
        }
        current = current.getCause();
    }
    return false;
}
~~~

With a fixture triggering **SSLHandshakeException**, tests can use the helper to verify the TLS error sits in the cause chain if the transport preserves that cause. However, avoid brittle assertions tied to exact error text or specific cause nesting that may change across versions/providers.

## 21. Testing Timeouts and Bounded Failure Responses

TLS handshakes and SMTP AUTH can stall if a server stops responding. A reliable CI setup must enforce timeouts in both the network client and the test runner.

### Cases to Include

~~~text
CASE A: server not listening on port
  -> fast connection refused/timeout, no infinite retries

CASE B: server accepts TCP but sends no greeting
  -> read timeout

CASE C: server advertises STARTTLS then stalls handshake
  -> handshake/read timeout

CASE D: TLS succeeds yet server does not respond to AUTH
  -> read timeout
~~~

Configuration:

~~~java
sender.getJavaMailProperties().put(
        "mail.smtp.connectiontimeout", "2000"
);
sender.getJavaMailProperties().put(
        "mail.smtp.timeout", "2000"
);
sender.getJavaMailProperties().put(
        "mail.smtp.writetimeout", "2000"
);
~~~

JUnit can also bound test execution time:

~~~java
import java.time.Duration;
import static org.junit.jupiter.api.Assertions.assertTimeoutPreemptively;

assertTimeoutPreemptively(
        Duration.ofSeconds(10),
        () -> client.testConnection()
);
~~~

**Note:** `assertTimeoutPreemptively` runs the assertion in a separate thread; if the test relies on a transaction context, Spring TestContext `ThreadLocal`, or thread-bound state, prefer **assertTimeout** or a runner deadline rather than preemptive interruption. Killing a thread is also no substitute for real socket timeouts.

### A Timeout Does Not Prove the Server Rejected the Mail

When sending real emails, a read timeout can occur after the SMTP server already accepted the message while the client missed the final response. In TLS/AUTH-focused tests, use **testConnection()** to test handshakes/auth without creating messages; in SMTP submission tests, distinguish **accepted**, **rejected**, and **unknown outcome** when testing retries.

Never automatically retry MIME submission indefinitely on network exceptions; it can generate duplicate emails if the server already accepted it.

## 22. Isolation When Using Testcontainers or Docker

For detailed certificate-policy tests, a containerized SMTP server is often easier to configure than a simple embedded server:

~~~text
Test runner / JUnit
       |
       v
Start SMTP test container
       |
       +-- Test users
       +-- Test certificate/key
       +-- STARTTLS / SMTPS policy
       +-- AUTH required policy
       +-- Local captured mailbox
       |
       v
Read mapped host/port
       |
       v
Inject Spring mail properties
       |
       v
Run tests and inspect server evidence
       |
       v
Stop/remove container
~~~

### Container Settings to Control

- **Port mapping:** dynamic or isolated ports; tests read the actual port after container readiness.
- **Wait strategy:** wait until the server genuinely accepts connections, not merely until the process starts.
- **TLS material:** mount only test certificates/private keys into the container with appropriate file permissions.
- **Network egress:** no Internet relay; traffic stays strictly between the test JVM and fixture.
- **Auth config:** test user/password; server disallows anonymous relay when testing AUTH.
- **Certificate SAN:** matches the hostname the client uses over mapped ports or the Docker network.
- **Mailbox reset:** each test or test class starts from a clean state.
- **Resource cleanup:** ensure containers stop after the suite, even on test failures.

### Do Not Rely on Floating Image Tags

For stable tests, pin image versions or digests per project policy. Using `latest` lets upstream image maintainers alter TLS defaults, AUTH behavior, or exposed ports, causing failures unrelated to your code.

No single SMTP Docker image should be assumed to support every TLS/AUTH scenario. Pick a project-controlled image/server and verify the fixture's capabilities.

### Testcontainers Does Not Automatically Make TLS Tests Secure

A container running an accept-all SMTP catcher can receive emails and inspect contents without proving certificate validation, server identity, or AUTH enforcement. Test environments must be **intentionally configured to reject invalid configurations**.

## 23. Separating TLS Tests from Email-Sending Logic Tests

A system may have a structure like:

~~~text
OrderService
    |
    v
OrderMailComposer
    |
    v
JavaMailSender
    |
    v
SMTP transport
~~~

Not every `OrderService` test needs to spin up a TLS fixture. A layered testing strategy is faster and clearer:

| Layer | Goal | Tools |
| --- | --- | --- |
| **Business unit tests** | Does it emit notifications on the right business events? | Mock mail port, JUnit/Mockito |
| **MIME composition tests** | Are headers, addresses, multiparts, encoding right? | Jakarta Mail parser, captured MIME |
| **SMTP integration tests** | Does it submit messages to a local fixture? | GreenMail/SMTP capture |
| **TLS/AUTH integration tests** | Do client and server enforce policies? | Real TLS/AUTH fixture |
| **Provider contract tests** | Does a specific vendor accept the configuration? | Controlled sandbox/API tests |
| **Delivery/operational tests** | Webhooks, bounces, reputation, routing | Dedicated test environment |

A test failing due to certificate mismatch should signal a transport security issue rather than being obscured by template logic. Conversely, a subject unit test does not need a network TLS handshake.

### Tests to Run on Every CI Build

Fast tests can include:

- Composing valid MIME messages.
- Local GreenMail SMTP AUTH and wrong-password checks.
- One STARTTLS positive/negative path with a fast fixture.

Heavier tests covering multiple protocol versions, expired certificates, and provider sandboxes can run in security pipelines or separate integration stages. Still, whenever the application modifies TLS configuration directly, make the relevant transport security tests mandatory before release.

## 24. Common Mistakes When Testing TLS/AUTH

### Mistake 1 - Checking Only That Mail Sending Succeeded

The test sees one email in **greenMail.getReceivedMessages()** and concludes "TLS and AUTH work".

**Problem:** an SMTP catcher may accept plaintext or anonymous relay. Successful delivery proves nothing about security.

**Resolution:** write dedicated tests for `STARTTLS` required, certificate identity, and wrong credentials.

### Mistake 2 - Setting starttls.enable Without starttls.required

Some servers do not advertise STARTTLS; the client can still proceed in plaintext under a configuration permitting downgrade.

**Resolution:** for mandatory TLS policies, set **mail.smtp.starttls.required=true**, test against a server lacking STARTTLS, and assert fail-closed behavior.

### Mistake 3 - Disabling Hostname Verification to Fix Certificate Errors

~~~properties
mail.smtp.ssl.checkserveridentity=false
~~~

**Problem:** the connection may be encrypted, yet the client never verifies that the server matches the intended name.

**Resolution:** issue a certificate whose SAN matches the test hostname, enable **checkserveridentity=true**, and verify wrong hostnames are rejected.

### Mistake 4 - Using Trust-All in Security Tests

~~~properties
mail.smtp.ssl.trust=*
~~~

**Problem:** tests lose all ability to detect forged or untrusted certificates.

**Resolution:** use dedicated test CAs/certs with a scoped truststore.

### Mistake 5 - Using an SMTP Server That Accepts Any Password

Tests with wrong usernames/passwords still succeed because the capture server does not enforce AUTH.

**Resolution:** pick a fixture that genuinely enforces authentication and verify the negative case before trusting it as an auth oracle.

### Mistake 6 - Generating a Certificate SAN Different from the Actual Hostname

The fixture has SAN **smtp-test**, while the test JVM connects to **localhost** over a mapped port.

**Problem:** hostname verification fails even though the certificate belongs to the test CA.

**Resolution:** issue certificates matching the hostname the client actually calls; never disable identity verification.

### Mistake 7 - Mixing STARTTLS with Implicit TLS

The client configures immediate SSL on socket open against an SMTP server supporting only STARTTLS upgrade.

**Problem:** client and server expect different protocol bytes, causing handshake failures or timeouts.

**Resolution:** choose **mail.smtp.ssl.enable** for SMTPS, or **starttls.enable + required** for STARTTLS.

### Mistake 8 - Sharing a Global Truststore Across Parallel Tests

Test A mutates **javax.net.ssl.trustStore** while Test B is opening a TLS connection.

**Problem:** tests become order-dependent and coupled through process-wide state.

**Resolution:** pass per-client `SSLSocketFactory` instances or run each test group in a forked JVM.

### Mistake 9 - Using Soon-to-Expire Certificates as Fixtures

Tests suddenly start failing later even though no code changed.

**Resolution:** generate TLS fixtures with controlled validity windows or manage intentional test certificate rotation; keep a separate expired-certificate test.

### Mistake 10 - Logging SMTP AUTH Transcripts

When tests fail, debug logs may contain usernames, Base64-encoded passwords, or tokens.

**Resolution:** avoid raw auth logs; if protocol debugging is required, redact payloads and restrict log access. Base64 is not encryption for secrets.

### Mistake 11 - Using Production Credentials in CI

A misconfiguration can cause integration tests to send real emails or leak credentials.

**Resolution:** use isolated test usernames/passwords, forbid Internet relaying on fixtures, and block egress where possible.

### Mistake 12 - Negative Tests Passing Because the Fixture Isn't Running

**assertThrows** passes on connection refused when the goal was testing an untrusted certificate.

**Resolution:** verify the fixture is ready and the TLS handshake reaches the expected phase before asserting the corresponding exception.

### Mistake 13 - Testing Wrong Passwords Only After SMTP Already Received Messages

Tests may trigger unintended deliveries or pollute results with older mailbox contents.

**Resolution:** use **testConnection()** for handshake/auth checks and isolated fixtures for submission tests.

### Mistake 14 - Hard-Coding the Same SMTP Port Across All Tests

In parallel CI runs, two fixtures bind the same port; one test may connect to another test's server.

**Resolution:** use dynamic ports, read the bound port from the fixture after startup, and stop the exact instance.

### Mistake 15 - Letting Tests Fall Back to a Production Host

The SMTP fixture fails to start, and Spring Boot falls back to the default deployment host.

**Resolution:** test profiles must configure isolated hosts, assert effective host/port, and block egress to external SMTP where possible.

### Mistake 16 - Assuming SMTP AUTH Means Any From Address Is Permitted

Valid credentials do not guarantee the server allows arbitrary `From`/envelope sender addresses.

**Resolution:** test sender identity separately when needed, using verified identities and matching provider settings.

### Mistake 17 - Using the TLS Protocol Property as Proof of What Was Negotiated

Reading **mail.smtp.ssl.protocols** and concluding the connection used TLS 1.3.

**Resolution:** when version/cipher proof is required, read the negotiated TLS session from the fixture or instrumentation rather than config alone.

### Mistake 18 - Send Succeeds Yet Test Reads Stale Mail

The fixture shares a mailbox across tests without clearing older messages.

**Resolution:** create fresh fixtures per test or clear mailboxes safely prior to sending; check unique message markers in captured MIME.

## 25. Troubleshooting Workflow for TLS Errors in Integration Tests

When `JavaMailSender` fails to connect, investigate in order instead of prematurely enabling trust-all.

~~~text
1. Has the fixture started and bound its port?
       |
       v
2. Do sender host/port point to the right fixture?
       |
       v
3. Is the server using STARTTLS or implicit TLS?
       |
       v
4. Is the client configured with the matching mode?
       |
       v
5. Was STARTTLS advertised, required, and handshake initiated?
       |
       v
6. Is the certificate chain valid against the test truststore?
       |
       v
7. Does the SAN match the hostname the client connects to?
       |
       v
8. Do client and server share compatible protocols/ciphers?
       |
       v
9. After TLS completes, does the server advertise AUTH?
       |
       v
10. Are username/password or AUTH mechanisms valid?
       |
       v
11. Are SMTP sender/recipients permitted?
       |
       v
12. MESSAGE ACCEPTED and captured properly?
~~~

### Read Error Categories as Clues, Not Absolute Truth

| Symptom | Suspects to Check |
| --- | --- |
| Connection refused | Fixture not running, wrong port, or broken network mapping |
| Read timed out before SMTP greeting | Server accepts TCP yet never responds, mode/port mismatch |
| Could not convert socket to TLS | STARTTLS handshake, certificate, protocol, or truststore |
| PKIX path building failed | Certificate chain not accepted by truststore |
| No subject alternative names matching | Hostname identity mismatch |
| AuthenticationFailedException | Credentials, AUTH mechanism, server auth policy |
| Server does not support STARTTLS | EHLO capabilities lack STARTTLS while client requires it |
| 530 Authentication required | Server forbids unauthenticated sends; check AUTH config |
| SMTP success yet empty mailbox | Recipients, fixture capture, acceptance semantics, or test state |

Error messages depend on implementation and version, so never use this table as production classification logic. Inspect the cause chain and server-side test evidence to pinpoint the failing stage.

### Bounded JSSE Handshake Debugging

During investigation, the JDK provides TLS handshake logging (such as JSSE debug flags) to inspect certificate chains, negotiated protocols, and handshake stages. Enable it only in restricted test environments; logs can be verbose and contain sensitive metadata. Never enable full TLS/network debug in production just to test a certificate.

There is no need to print SMTP AUTH payloads or passwords to diagnose a certificate error; TLS handshakes occur before credentials are sent under secure policies.

## 26. Practice Scenarios

### Scenario A - Test Sends Email Successfully, Yet TLS Is Disabled

A local SMTP catcher accepts messages even when the client connects in plaintext.

**Question:** does a green test prove TLS?

**Answer:** no. You need a fixture supporting real TLS and tests verifying the client rejects missing STARTTLS or invalid certificates.

### Scenario B - STARTTLS Enabled, Server Does Not Advertise It

Client configures `starttls.enable=true`, missing `required=true`.

**Question:** what is the risk?

**Answer:** it may fall back to sending in plaintext depending on settings and server. For mandatory TLS policies, enable `required` and test fail-closed behavior.

### Scenario C - Test Trusts a Self-Signed Certificate

The client imports the test certificate into a truststore and connects to **localhost** with certificate SAN=localhost.

**Question:** is this disabling TLS verification?

**Answer:** no, provided the truststore trusts only the designated test certificate/CA and hostname checking remains on. This is controlled trust testing, unlike trust-all.

### Scenario D - Connecting by IP When SAN Has Only DNS

The certificate is issued for `localhost`, and the client calls `127.0.0.1`.

**Question:** why does it fail even after importing the cert?

**Answer:** trust chain validation and hostname identity are separate steps. An IP does not match a DNS-only SAN; fix the hostname or issue a certificate with an IP SAN.

### Scenario E - Wrong-Password Test Still Succeeds

GreenMail/capture server in tests accepts sending despite invalid credentials.

**Question:** should we conclude `JavaMailSender` is broken?

**Answer:** not yet. Verify whether the fixture genuinely enables/enforces AUTH. A permissive SMTP catcher is not a valid authentication oracle.

### Scenario F - Valid User, Yet mail.smtp.auth Not Enabled

The server requires AUTH.

**Question:** what is the expected result?

**Answer:** it cannot submit as an authenticated user. The test must observe rejection rather than falling back to anonymous relay.

### Scenario G - Port 465 Without TLS

The client sends plaintext SMTP to an implicit TLS server.

**Question:** fix it by enabling STARTTLS?

**Answer:** not necessarily. If the server uses implicit TLS, set **mail.smtp.ssl.enable=true**; STARTTLS is a different mode.

### Scenario H - Certificate Mismatch Test Passes Due to Connection Refused

The TLS fixture has not started yet, and `assertThrows` passes.

**Question:** does the test prove hostname validation?

**Answer:** no. Ensure the fixture is ready and the exception originates from certificate identity verification.

### Scenario I - Sending Test Emails via Production SMTP

CI uses real credentials and recipients belonging to internal mailboxes.

**Question:** why is this still not an isolated environment?

**Answer:** it depends on networks/providers, impacts quotas/reputation, risks secret leaks, and sends externally. Use local test fixtures and reserve provider sandboxes for separate contract tests.

### Scenario J - Tests Swap the JVM Truststore Across Two Threads

Test A uses CA1 cert, Test B uses CA2 cert, and both mutate system properties.

**Question:** can tests become flaky?

**Answer:** yes. JVM-wide truststore settings create shared mutable state. Use per-client `SSLContext`/socket factories or forked JVMs.

### Scenario K - AUTH Succeeds Over Plaintext

The SMTP server accepts username/password over an unencrypted connection.

**Question:** are security requirements met?

**Answer:** no, if policy requires protecting credentials with TLS. Verify AUTH runs only after TLS and the client rejects servers lacking STARTTLS.

### Scenario L - SMTP Server Only Supports Legacy TLS

Client policy allows only TLSv1.2/1.3.

**Question:** should we relax policy in tests to make sending succeed?

**Answer:** no, when the goal is verifying legacy protocols are blocked. Handshake failure is the right outcome; upgrade the fixture/server if you also want a happy path.

### Scenario M - Email Accepted Yet Recipient Does Not See It

The test SMTP fixture reports receipt, while a real provider routes messages to spam.

**Question:** can TLS/AUTH integration tests prove deliverability?

**Answer:** no. They prove transport to the fixture, not mail reputation, DNS authentication, spam filtering, or provider delivery events.

### Scenario N - Debug Logs Contain Credentials

A developer enables `mail.debug` in the pipeline and logs capture sensitive details.

**Question:** what should be done?

**Answer:** disable raw protocol debug by default, redact data, use test secrets, and restrict log access. When debugging is necessary, enable short-lived controlled logging in tests.

### Scenario O - Valid AUTH Test Yet Spoofed From Is Accepted

The SMTP fixture checks passwords yet ignores sender identity.

**Question:** can we conclude all sender security is sound?

**Answer:** no. AUTH and `From`/envelope sender authorization are separate policies; test against a fixture/provider verifying sender identity when business rules require it.

### Scenario P - Fixture Dynamic Port Changes

A test hard-codes port 3025 while the server starts on a different port.

**Question:** how to avoid this?

**Answer:** read the actual port from the fixture and inject it into the Spring context via `@DynamicPropertySource` or test configuration. Never fall back to another host.

## 27. Workflow for Setting Up a Test Suite in a Spring Mail Project

An implementation can follow these steps:

~~~text
1. Define the SMTP policy to protect
   |
   +-- STARTTLS or implicit TLS?
   +-- Mandatory or opportunistic TLS?
   +-- Certificate trust/hostname verification?
   +-- SMTP AUTH mechanism and sender permissions?
   |
   v
2. Choose a test fixture capable of enforcing policy
   |
   +-- GreenMail for basic SMTP/auth/capture
   '-- Container or TLS fixture for certificates/downgrade
   |
   v
3. Create test accounts and TLS material
   |
   +-- Test users/passwords
   +-- Certificate SAN matching hostname
   '-- Truststore trusting only test CA/certificate
   |
   v
4. Start fixture and read dynamic host/port
   |
   v
5. Override spring.mail.* in test context
   |
   +-- Enable auth
   +-- Enable starttls.required or ssl.enable
   +-- Enable hostname checking
   +-- Set socket timeouts
   |
   v
6. Run positive tests
   |
   +-- TLS handshake succeeds
   +-- Valid AUTH
   '-- Message captured by fixture
   |
   v
7. Run negative tests
   |
   +-- Missing STARTTLS
   +-- Untrusted certificate
   +-- Wrong hostname
   +-- Wrong password/username
   +-- Unsupported mechanism/protocol
   '-- Zero accepted messages on failure
   |
   v
8. Verify cleanup
   |
   +-- Fixture stop
   +-- No external SMTP traffic
   '-- No test state/credentials leaking across tests
   |
   v
9. Integrate into CI with clear logging/secret policies
~~~

### Suggested Test Class Breakdown

| Test Class / Group | Scope |
| --- | --- |
| **SmtpAuthIntegrationTest** | Valid/invalid username/password, mandatory AUTH |
| **StartTlsIntegrationTest** | STARTTLS positive and required negative cases |
| **SmtpsIntegrationTest** | Implicit TLS positive and mode mismatch cases |
| **SmtpCertificateIntegrationTest** | Trust chain, wrong hostname, expired certificate |
| **SpringMailWiringIntegrationTest** | Spring Boot property binding and dynamic endpoint |
| **MimeSubmissionIntegrationTest** | MIME message after passing through SMTP fixture |
| **MailIsolationIntegrationTest** | No production host/credentials and no external relay |

This grouping is illustrative; creating all seven classes is not mandatory. What matters is that a test failure clearly pinpoints **which configuration or security boundary broke**.

### Clear Acceptance Criteria

A test suite demonstrates solid TLS/AUTH policy verification when:

- The client genuinely connects to an isolated server enforcing the TLS/AUTH policy under test.
- The happy path succeeds only with valid certificate, hostname, and credentials.
- At least one test verifies fail-closed behavior if STARTTLS is missing.
- Unknown certificates are never trusted and mismatched hostnames are rejected.
- Invalid/missing AUTH is rejected when required by the server.
- Failed handshakes/auth attempts produce zero accepted messages.
- Tests use no production mail accounts, require no Internet, enforce timeouts, and clean up.

These criteria verify behavior in a controlled test environment; always ensure live deployment settings match the tested policies.

## 28. Distinguishing Integration Testing from Production Monitoring

Isolated testing catches configuration flaws in code and deployment templates. However, production environments can still change:

- Providers rotate TLS certificates or change CA chains.
- Servers alter TLS protocol/cipher policies.
- SMTP credentials expire or get revoked.
- Providers change supported AUTH mechanisms.
- DNS/network firewalls encounter incidents.
- Relay permissions or sender identities change.

Therefore, combine integration tests with **production monitoring of SMTP/TLS errors**, without flooding real mail or enabling protocol debugging that logs secrets.

Useful operational signals:

| Signal | Investigation Direction |
| --- | --- |
| Rising TLS handshake failures | Certificate/CA chain, hostname, protocol compatibility |
| Rising authentication failures | Credentials, mechanism, account lock/revocation |
| Rising connection timeouts | Network, DNS, firewall, provider outage |
| Submissions rejected for sender | Verified sender identity, envelope/From policy |
| Rising mail send latency | SMTP provider, throughput, queues, and worker pools |

**Never resolve a certificate incident by disabling verification in production.** Instead, verify the new server certificate, CA trust, and domain name, then update truststores/configuration via change control.

### Tests Do Not Replace DNS Authentication and Deliverability

Even with thorough TLS/AUTH integration tests, production still requires managing:

- SPF, DKIM, and DMARC when sending from organizational domains.
- Bounce and complaint suppression.
- Sender reputation, rate limits, and message content.
- Retry policies for temporary SMTP errors.
- Timeout scenarios where it is ambiguous whether the SMTP server accepted the message.

Those are distinct problems from whether TLS handshakes and SMTP AUTH are properly enforced.

## 29. Summary

~~~text
Mock JavaMailSender             -> Does not prove TLS/AUTH
Successful SMTP capture         -> Does not prove security alone
STARTTLS enable                 -> Not guaranteed fail-closed
STARTTLS required               -> Rejects server lacking STARTTLS
Implicit TLS                    -> mail.smtp.ssl.enable=true
Certificate trusted             -> Still needs hostname identity check
Trust-all                       -> Not valid trust testing
SMTP AUTH succeeds              -> Does not guarantee From is permitted
mail.debug                      -> May expose credentials
Spring test profile             -> Must target the right SMTP fixture
SMTP server accepted            -> Does not prove Inbox delivery
~~~

**Testing TLS and authentication in an isolated environment** requires an SMTP fixture capable of **enforcing and rejecting** the relevant security scenarios. With Spring Framework Mail, you can use **JavaMailSenderImpl** or a Spring Boot-configured **JavaMailSender** alongside GreenMail/an SMTP container, test truststores, and dynamic ports. A valuable test suite does not merely verify that sending succeeds - it proves the client **never downgrades to plaintext when TLS is mandatory**, **never trusts invalid certificates**, **never ignores hostname mismatches**, and **never sends when SMTP AUTH fails**. When fixtures are isolated from the Internet, avoid production credentials, and enforce timeouts and cleanup, these tests form a practical safeguard against security configuration regressions prior to release.
