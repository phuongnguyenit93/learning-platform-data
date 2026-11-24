# Distinguishing Confidentiality, Integrity, and Availability (CIA Triad)

## 1. Three Fundamental Security Goals

To design security for a Spring Boot application, you must first identify **what needs to be protected**. The three foundational goals are:

- **Confidentiality (C):** Only authorized subjects may learn or read the information.
- **Integrity (I):** Data and actions must preserve their accurate state, origin, and permitted rules; unauthorized or unintended changes must be prevented or detected.
- **Availability (A):** Authorized users and systems can access features, data, and services when needed at an acceptable level of quality.

This trio is known as the **CIA Triad**. These are **security goals**, not names of three specific technologies. Authentication, authorization, encryption, transactions, backups, or rate limiting are **means** that help achieve one or more of those goals.

Picture a banking app: if balance info leaks to an outsider, the primary failure is **confidentiality**. If a balance is altered without a valid transaction, the primary failure is **integrity**. If customers cannot transfer money because the system is crippled, the primary failure is **availability**. A system can protect two goals well yet still fail the third.

| Aspect | Confidentiality | Integrity | Availability |
| --- | --- | --- | --- |
| Question to answer | **Who may read or know?** | **Who may alter, and is the outcome valid?** | **Can authorized users use it when needed?** |
| Typical violation | Data leakage | Modifying or forging data | Loss of service |
| API example | USER A reads USER B's order | USER A approves an order or alters price without permission | Checkout repeatedly times out |
| Common controls | Access control, TLS, encryption, masking | Write permissions, validation, transactions, CSRF protection, HMAC/signatures | Load limits, redundancy, timeouts, backups, recovery |
| How to verify | Unauthorized read tests | Unauthorized write and DB state tests | Load tests, failover tests, measuring latency/uptime |

**Note:** C, I, and A are not mutually exclusive. A single attack can leak data, modify data, and take the service offline at the same time. The table above highlights the **most direct primary impact** of each goal.

## 2. Confidentiality

### 2.1. What Does Confidentiality Mean?

Data has confidentiality when it is **disclosed only to authorized identities, roles, services, or processes**. Data must be protected **in transit**, **at rest**, and **while being processed or exported**.

"Not disclosing" does not mean merely omitting data from the main API. Data can still leak via:

- Responses containing extra sensitive fields the client does not need.
- URLs, query strings, logs, stack traces, access logs, debug traces.
- Configuration files holding passwords, API keys, tokens, or private keys.
- Public caches, export files, or backups without access controls.
- Networks without TLS, allowing eavesdroppers to observe traffic.
- APIs letting logged-in users read resources that do not belong to them.

### 2.2. Example: Valid Login Yet Reading the Wrong Data

An API exposes **GET /orders/42**. User A logs in successfully with role USER, then replaces 42 in the URL with B's order ID. If the server only checks `authenticated()` without verifying the **order owner**, the response may return B's shipping address, phone number, and total amount.

This is **Broken Object Level Authorization (BOLA/IDOR)** and directly violates C. **Authentication** answers who A is. **Data-level authorization** must answer whether A has permission to read **that specific order**. Having authentication does not mean all data is kept confidential.

### 2.3. Controls for Protecting C

1. **Access control:** Authentication, roles/authorities, permissions, and per-record ownership checks before returning data.
2. **Least privilege:** Users, service accounts, database roles, and API keys receive only the minimum privileges needed for their job.
3. **Transport protection:** Use HTTPS/TLS; never send passwords and sensitive data over plain HTTP on real networks.
4. **Storage protection:** Encryption suited to data type, key management, backup protection, and restricted database access.
5. **Minimize unintended leakage:** Return only necessary fields via DTOs, mask secrets in logs, never return sensitive stack traces.
6. **Lifecycle management:** Expire and revoke sessions/tokens, rotate secrets, handle disabled accounts.

**Distinction to keep clear:** Encryption does not solve authorization on its own. A response sent over HTTPS can still leak data when the server returns B's info to A. Hiding a button or page in the frontend never replaces server-side authorization.

### 2.4. How to Test C?

Create two users A and B with separate orders. Log in as A and attempt to read B's order via URL and direct API client. Expect the response **to contain no unauthorized data**, regardless of whether the system returns 403 or 404 per resource-existence-hiding policy. Also inspect logs and responses to ensure no tokens, password hashes, or sensitive fields leak.

## 3. Integrity

### 3.1. What Does Integrity Mean?

Integrity means data and operations **are not altered without authorization, forged, lost, or transformed against the rules**. Data still changes normally: customers update addresses, admins approve orders, accountants record transactions. The goal is not "never change," it is **changing with the right permissions, under the right conditions, with the right outcome**.

Integrity can be viewed at three levels:

- **Action permissions:** Is the caller allowed to create, edit, delete, or approve this data?
- **Content trustworthiness:** Was the request/payload altered, forged, or violating business rules?
- **Outcome consistency:** After a transaction, is the data state accurate or corrupted by concurrent overwrites or partial updates?

### 3.2. Direct Examples

- A regular USER calls **POST /admin/orders/42/approve** and the order gets approved despite lacking the ADMIN role: **I is violated by an unauthorized operation**.
- A client sends totalPrice=100 for an order actually costing 900; the server trusts the client price and saves it to the database: **I is violated by trusting untrusted data**.
- Two requests debit the same account concurrently, yielding an incorrect balance due to missing proper transactions/locking: **I is violated by a concurrency bug**.
- An attacker modifies packet contents or signed config data: mechanisms verifying integrity and data origin are needed.

All of these scenarios can happen **without leaking confidential data**. Thus protecting C does not mean I is protected.

### 3.3. Controls for Protecting I

1. **Write authorization:** Separate read permissions from modification permissions; check owner, action permission, and business state.
2. **Validation:** Check data types, lengths, amounts, enum values, state transitions, and cross-field constraints.
3. **Business invariants:** Never trust client-supplied sensitive fields like ownerId, role, or totalPrice; recompute or look up from trusted sources.
4. **Database integrity:** Use transactions, unique/foreign-key constraints, optimistic locking, or appropriate concurrency control.
5. **Prevent tampering in transit:** Use TLS; when a protocol requires independent data verification, use HMAC or digital signatures with properly managed keys.
6. **CSRF protection when applicable:** Block state-changing requests triggered by another site inside a logged-in browser.
7. **Audit and recovery:** Record traces of critical actions for investigation, anomaly detection, and recovery when data is wrongly altered or deleted.

Never consider "checked ROLE_USER" sufficient if the API allows USER A to modify USER B's record. Service-layer rules must match the **authenticated principal** against **real ownership data**.

### 3.4. How Do Hashes, HMAC, and Digital Signatures Relate?

- A **cryptographic hash** such as SHA-256 produces a fingerprint of content. To verify integrity, the reference hash must come from a **trusted source**. A plain hash does not authenticate who created the content.
- **HMAC** uses a shared secret key to produce an authentication tag. If the key stays secret, a verifier can detect altered content and prove the creator knew the shared key. HMAC **does not encrypt** the content.
- **Digital signatures** use a private key to sign and the corresponding public key to verify. Signatures do not hide plaintext, and the verifier must trust the public key.
- **Authenticated encryption (AEAD)** can provide both confidentiality and authentication/integrity for encrypted data, yet still does not prove business-level authorization on its own.

For example, if a file and its hash are stored together where an attacker can modify both: the attacker can replace the file and recompute the hash. Two matching values do not prove the data came from a trusted source.

### 3.5. How to Test I?

Try invoking write operations with an unauthorized user, tampering with ownerId or totalPrice in payloads, replaying requests, sending two concurrent requests, and verifying the **final database state**. For an order-approval endpoint, testing matters not only for the 403 response but also for proving **the order did not transition state** after the rejected request.

## 4. Availability

### 4.1. What Does Availability Mean?

A system has availability when **authorized users** can use the service **when they need it**, with acceptable response times and quality. A service whose process is still running while every request times out still has poor availability. Likewise, an API repeatedly returning 503 or a database dependency going down is an A incident.

**Returning 403 to someone lacking permission is not an A violation.** That can be the right security outcome. We evaluate A for **authorized users and legitimate requests**, not arbitrary unauthorized requests.

### 4.2. Typical Causes

- Traffic spikes or DoS/DDoS attacks exhausting CPU, RAM, thread pools, or connection pools.
- Failures in databases, identity providers, DNS, message brokers, or network infrastructure.
- Misconfigured deployments preventing the app from starting or serving business logic.
- Unbounded retries or heavy tasks saturating shared resources.
- Corrupted records/storage without usable backups/restores.
- Overly rigid account lockout policies abused to lock out legitimate users.

### 4.3. Controls for Protecting A

1. **Load control:** User/IP-appropriate rate limiting, quotas, request size caps, request timeouts, queues, and concurrency limits.
2. **Eliminate single points of failure:** Multiple instances, load balancers, health checks, failover, and resilient infrastructure architecture.
3. **Contain cascading failures:** Timeouts, circuit breakers, bulkheads, bounded retries, and backoff so dependencies do not collapse further.
4. **Backup and recovery:** Regular restore drills; define Recovery Time Objective (**RTO**) and Recovery Point Objective (**RPO**).
5. **Serviceability monitoring:** Error rates, latency, saturation, availability SLIs/SLOs, and critical business journeys.
6. **Controlled deployments:** Rollbacks, rolling deployments, capacity planning, and incident drills.

Rate limiting is not a cure-all for every DDoS; network infrastructure, CDN/WAF, resource sizing, and scaling still matter. Conversely, an ill-considered account lockout mechanism can let an attacker repeatedly enter wrong passwords to **deny legitimate access** to a victim.

### 4.4. Availability and Spring Security's Responsibility

Spring Security provides authentication, authorization, and certain web protections, yet **does not automatically provide** load balancing, multi-region failover, backups, restores, circuit breakers, or complete distributed rate limiting. Those typically belong to application architecture, infrastructure, API gateways, and operations.

## 5. One API: Viewing All Three Angles Together

Consider an ordering system with view-order, update-order, and payment functions:

| Operation | Question for C | Question for I | Question for A |
| --- | --- | --- | --- |
| GET /orders/42 | Is the caller allowed to **read** order 42? | Is the returned data accurate to the record, un-tampered? | Do valid users receive responses on time? |
| PATCH /orders/42 | Does private data leak in responses/logs? | Is the caller allowed to edit; are new values valid? | When the DB slows down, does the API time out and recover cleanly? |
| POST /payments | Do accounts, tokens, or personal data leak? | Are transactions verified, replay-protected, and atomic? | Can it withstand load, dependency outages, and recover? |

Three sample scenarios:

**Scenario A — Order exposure:** User A reads B's address. The missing control is record-level access control: **C**.

**Scenario B — Unauthorized price change:** User A lacks permission yet sends a request causing the server's total amount to change. The missing control is write authorization and business constraints: **I**.

**Scenario C — Checkout system bottleneck:** An authenticated customer with payment permission repeatedly times out because the database connection pool is exhausted. The missing control is resource capacity, backpressure, or recovery: **A**.

Failures can compound. For instance, a stolen token breaks credential confidentiality, enabling the attacker to read or alter data; a data deletion incident breaks both integrity and service availability.

## 6. How Far Does Spring Security Support Each Goal?

Spring Security **most directly** supports authentication, authorization, and certain request, session, and browser protection layers. These clearly affect C/I but do not replace availability engineering.

| Mechanism | Value for CIA | What the Framework Does Not Solve Alone |
| --- | --- | --- |
| Authentication | Verifies principal so read/write rules apply | Being logged in does not allow reading/editing every record |
| HTTP authorization | Blocks out-of-privilege requests; protects C and I | URL matchers do not replace ownerId checks in the DB |
| Method security | Enforces permission checks on business methods | Requires proper setup and handling internal/proxy calls |
| CSRF protection | Supports I against forged state-changing requests | Does not replace transactions, permissions, or validation |
| Session/security context | Maintains principal context for policy enforcement | Requires cookie, timeout, logout, and session design |
| Security headers | Reduces certain browser-related risks | Does not auto-craft a tailored CSP for every app, nor replace TLS |
| HTTPS/TLS | Protects C and I in transit | Must be configured on servers, ingress/proxies, and clients |
| Rate limits, HA, backups, failover | Primarily serves A | Not included out of the box by adding starter-security |

**Example:** Requiring `authenticated()` on `GET /profile` is a first step for C. However, the Controller must return the caller's own profile or verify permission to read the target profile. Requiring `authenticated()` on `POST /payments` only identifies the caller; achieving I also requires owner checks, balance/limit checks, validation, transactions, replay protection, and CSRF when browser risk applies.

### 6.1. Illustrative Configuration in Spring MVC

This is a **SecurityFilterChain configuration snippet** used inside a Spring-managed class, with matching imports for `@Bean`, `SecurityFilterChain`, `HttpSecurity`, `HttpMethod`, and `Customizer`. It is **illustrative code depending on Spring Boot/Spring Security**, not a standalone compilable Java file:

~~~java
@Bean
SecurityFilterChain appSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/catalog").permitAll()
            .requestMatchers(HttpMethod.GET, "/profile").authenticated()
            .requestMatchers(HttpMethod.POST, "/payments").authenticated()
            .requestMatchers(HttpMethod.POST, "/admin/**").hasRole("ADMIN")
            .anyRequest().denyAll()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

This configuration lets anyone read `/catalog`, authenticated users access `/profile` and `/payments`, only ADMIN invoke POST under `/admin/**`, and denies unclassified requests. **Matchers do not guarantee** that profile info belongs to the right user, that payments have sufficient funds, or that load capacity is adequate.

Note on POST: Spring Security enables CSRF protection in Servlet by default. Using HTTP Basic in a browser may require a **valid CSRF token** to submit state-changing requests; if missing, requests may fail with 403 even with a valid role. Do not disable CSRF out of habit—evaluate how clients transmit credentials.

### 6.2. A Common Mistake When Assessing Security

Claiming "the API has a SecurityFilterChain, so CIA is guaranteed" is wrong. The filter chain can block unauthorized callers at the HTTP boundary, yet:

- C still fails if the Service returns User B's data to A.
- I still fails if a valid transaction is processed wrongly, partially updated, or saves client prices unchecked.
- A still fails if the database, network, or service collapses.

Choosing security solutions must be driven by **assets, threats, and consequences**, not annotation counts.

## 7. Java 17 Hands-On: How Integrity Differs from Confidentiality

We can use **HMAC-SHA256** to observe how altered content is detected when the verifier holds the right secret key. This program runs on **JDK 17+** with no Spring dependencies.

Create **IntegrityDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class IntegrityDemo {

    private static byte[] tag(String message, byte[] secret)
            throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(message.getBytes(StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws Exception {
        byte[] secret = "demo-only-secret".getBytes(StandardCharsets.UTF_8);
        String original = "order=42&amount=100";
        String tampered = "order=42&amount=900";

        byte[] expectedTag = tag(original, secret);

        System.out.println("Original valid: "
                + MessageDigest.isEqual(expectedTag, tag(original, secret)));
        System.out.println("Tampered valid: "
                + MessageDigest.isEqual(expectedTag, tag(tampered, secret)));
    }
}
~~~

Compile and run:

~~~bash
javac IntegrityDemo.java
java IntegrityDemo
~~~

Deterministic stdout from the program:

~~~text
Original valid: true
Tampered valid: false
~~~

**Explanation:** HMAC generates a tag for the original message from the content and shared key. When `amount` changes from 100 to 900 while keeping the original tag, verification fails. This provides **tamper detection and key-holder origin verification**, part of **Integrity**.

The program **does not encrypt** the order/amount string; anyone reading the message still sees the amount, so **Confidentiality is not protected**. The program also makes no promise to stay operational if the machine crashes or is overloaded, so **Availability is not addressed**. HMAC alone does not check roles, ownership, transfer logic, or stop replay of a previously valid message. Hardcoded keys are for learning only; real apps must store keys securely and design complete protocols.

## 8. From CIA to Risk Analysis and Testing

A compact workflow to apply directly in your project:

1. **List assets:** Profiles, credentials, balances, orders, backups, approval functions, payment APIs.
2. **Identify authorized subjects:** Which users may read, edit, delete, or approve; which services may use the data?
3. **Write C risks:** Who could view unauthorized data via endpoints, logs, backups, or connections?
4. **Write I risks:** Who could alter data without authorization, forge payloads, replay requests, or create invalid states?
5. **Write A risks:** For how long could authorized users suffer denial of service, timeouts, or data loss?
6. **Choose controls at the right layer:** Spring Security for authn/authz and CSRF, Service/DB for data rules, TLS for transport, infrastructure for capacity and recovery.
7. **Design negative tests:** Denied cases must leak no data and cause no DB mutations.
8. **Verify operations:** Monitor latency, error rate, capacity; rehearse restores and define RTO/RPO.

Sample test table:

| Goal | Test Case | Pass Criteria |
| --- | --- | --- |
| C | User A calls GET /orders/42 when order belongs to B | Receives none of B's data |
| C | Login error generates logs | No passwords or tokens logged |
| I | USER calls admin-only approval endpoint | Record state unchanged |
| I | Client tries sending invalid totalPrice | Server rejects or recomputes per rules |
| I | Two requests update balance concurrently | DB result stays transactionally consistent |
| A | Database dependency temporarily pauses | Timeouts/alerts fire, cascading failures contained, system recovers |
| A | Sharp traffic spike | Priority services remain operational within design limits |
| A + I | Restore backup after incident | System runs and data recovers within RPO target |

### When Should Multiple Properties Be Recorded for One Risk?

State the **direct** consequence first, then related secondary impacts:

- Stolen token: C on the credential, which can lead to C/I on data depending on the token's permissions.
- Ransomware making data inaccessible: A; if data was also destroyed or modified without authorization, also I.
- Loss of database and backups: A because the system cannot serve; I because accurate data is not preserved/recoverable.
- Service enters deadlock: primarily A; if transactions remain atomic, not necessarily I.

This perspective is better than forcing every incident into one and only one label.

## 9. Misconceptions to Avoid

**"Once logged in, data is kept confidential."** False. You must verify read permissions per resource and guard other leak paths like logs, backups, and exports.

**"Once encrypted, data certainly cannot be tampered with."** False. Not every encryption scheme provides authentication/integrity. Choose appropriate mechanisms, such as AEAD when both confidentiality and integrity are required.

**"Having SHA-256 proves the sender is trustworthy."** False. Plain hashes do not authenticate origin; the reference hash must come from a trusted source, or use HMAC/digital signatures with properly managed keys.

**"Having ROLE_ADMIN guarantees every transaction is valid."** False. Action permissions do not replace validation, business preconditions, transactions, and concurrency handling.

**"CORS replaces CSRF."** False. CORS is a browser policy governing cross-origin reads; it does not replace authentication, authorization, or CSRF protection when needed.

**"Rate limiting solves all DDoS."** False. It is only one load-control layer; networks, infrastructure, dependencies, and capacity still matter.

**"403 means the API lost availability."** Not necessarily. Properly rejecting an unauthorized caller means security is working; availability is measured for **authorized users**.

**"Integrity is only broken by hackers."** False. Coding bugs, race conditions, operator mistakes, and faulty deployments can also break I or A.

## 10. Knowledge Self-Check

**Question 1.** A is logged in yet views B's shipping address. Which property is violated?  
**Answer:** **C**. Authentication is not enough; record-level authorization is missing.

**Question 2.** A user with only view permission alters an order's status. Which property is violated?  
**Answer:** **I**, because the system accepted an unauthorized write operation.

**Question 3.** Legitimate users cannot pay for 40 minutes because the database connection pool is exhausted. Which property is affected?  
**Answer:** **A**. Also check I if any transactions were partially updated or data was lost.

**Question 4.** A file's SHA-256 matches the hash stored beside it on a compromised server. Does that prove the file is trustworthy?  
**Answer:** **No**. An attacker can alter both the file and the hash; a trusted hash source or key-based verification is required.

**Question 5.** Does HTTPS guarantee full CIA for an API?  
**Answer:** **No**. TLS protects the transport channel but does not verify data permissions, transaction rules, or service availability.

**Question 6.** Do backups relate to A or I?  
**Answer:** **Both A and I**: they help restore serviceability and accurate data state per recovery objectives. Backups holding sensitive data must also protect C.

**Question 7.** Why can CSRF affect I even when the user logged in properly?  
**Answer:** The browser may attach credentials automatically when a malicious page triggers a state-changing request, causing the server to accept an action the user never intended. CSRF tokens are an appropriate defense layer for flows carrying that risk.

## 11. Further Reading

- NIST — Confidentiality: https://csrc.nist.gov/glossary/term/confidentiality
- NIST — Integrity: https://csrc.nist.gov/glossary/term/integrity
- NIST — Availability: https://csrc.nist.gov/glossary/term/availability
- Spring Security — Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/index.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
