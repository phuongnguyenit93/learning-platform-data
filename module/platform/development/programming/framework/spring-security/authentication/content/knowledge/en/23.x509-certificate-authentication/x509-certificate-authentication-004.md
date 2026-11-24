# Extracting the Principal from an X.509 Certificate Subject

When using an **X.509 client certificate** for authentication in Spring Security, the browser, client machine, or service presents the certificate during the TLS handshake. After the TLS layer validates the certificate against system policy, the application needs to identify the **application entity** corresponding to that certificate. A common approach is taking the `CN` (Common Name) value from the **Subject** field and using it as the principal name to look up the account and permissions.

Key point: **principal extraction** is merely reading and interpreting an identity attribute. It does **not** verify the CA, digital signature, validity period, certificate revocation, or access permissions on its own. Clearly distinguish the identifier inside the certificate, the extraction result, and the `Authentication` used by Spring Security.

This lesson explains Subject Distinguished Name (DN) syntax, safe extraction in Java 17+, Spring Security's default mechanism, cases where CN is missing/duplicated/escaped, its relationship to SAN, and integration testing.

## 1. What Does Subject DN Contain?

An X.509 certificate contains fields such as **Subject**, **Issuer**, validity period, public key, serial number, extensions, and signature. The Subject is typically an **X.500 Distinguished Name (DN)** describing the entity to which the certificate was issued.

Example Subject:

~~~text
CN=svc-orders,OU=Backend,O=Example Corp,C=VN
~~~

| Attribute | Meaning | How It Is Used |
| --- | --- | --- |
| `CN` | Common Name: common name of the subject | Can be configured as username/principal |
| `OU` | Organizational Unit | Provides organizational info; does not automatically grant roles |
| `O` | Organization | Organization name in the Subject |
| `C` | Country | Country code |
| `UID` | User identifier, if used by the CA profile | Potential identifier candidate depending on organizational convention |
| `emailAddress` or corresponding OID | Email address that may appear in DN | Not inherently trustworthy or unique |

With the example DN, if the policy relies on CN, the expected principal is:

~~~text
svc-orders
~~~

The DN is **different** from the extracted principal. The string `CN=svc-orders,OU=Backend,O=Example Corp,C=VN` is the full Subject name; `svc-orders` is only one attribute value chosen according to application rules.

Further distinctions:

- **Subject** describes who the certificate is issued to; **Issuer** describes the organization/CA that issued the certificate. Taking CN from Issuer yields the wrong identity.
- **Subject DN** resides in the Subject field; **Subject Alternative Name (SAN)** is a separate extension that can contain DNS names, emails, URIs, IPs, or other identifiers. Modern certificates may use SAN as the primary identifier.
- **Spring Security Principal** is the application object after looking up the account. It can be `UserDetails` or a domain object depending on the provider; it does not have to be just the CN String.

Never interpret `OU=Admins` as administrative privileges. Subject attributes are identifying data issued by the CA under a certificate profile, whereas roles/authorities are decided by application policy.

## 2. Processing Flow: TLS → Subject → Principal → Authentication

In a Spring Security Servlet application supporting client certificates, the high-level flow is:

~~~text
Client sends certificate in TLS handshake
                 │
                 ▼
TLS endpoint verifies certificate against trust policy
  (CA/trust anchor, chain, validity, usage constraints...)
                 │
                 ▼
Servlet container supplies X509Certificate[] on request
                 │
                 ▼
Spring Security X509AuthenticationFilter
                 │
                 ▼
X509PrincipalExtractor reads Subject and selects principal value
                 │
                 ▼
PreAuthenticatedAuthenticationToken
                 │
                 ▼
PreAuthenticatedAuthenticationProvider
  looks up account/roles via UserDetailsService or equivalent
                 │
                 ▼
Authentication placed in SecurityContext
                 │
                 ▼
Authorization: endpoint, method, resource
~~~

In the modern Servlet API (Jakarta), the container-verified client certificate can be provided via the `jakarta.servlet.request.X509Certificate` request attribute. Whether this attribute is actually populated depends on TLS/container/proxy configuration; `X509AuthenticationFilter` cannot infer a trusted certificate from an arbitrary client-supplied header.

**Trust boundary:** X.509 authentication in Spring Security is a form of **pre-authentication**. Spring Security assumes the TLS/container layer has already completed certificate verification. If the layer ahead of Spring Security fails to verify the certificate chain, clientAuth, or trust store properly, perfect Subject parsing still does not make the system secure.

For example, a client certificate with Subject `CN=svc-orders` signed by an untrusted CA: must **not** receive principal `svc-orders` to log in. The decision to accept the certificate must occur before identity mapping.

## 3. Extraction in Java: Prefer X500Principal

Java provides an API to retrieve the Subject as a standard object:

~~~java
X500Principal subject = certificate.getSubjectX500Principal();
String subjectDn = subject.getName(X500Principal.RFC2253);
~~~

This is an **illustrative code snippet**, where `certificate` is a `java.security.cert.X509Certificate` obtained from a trusted source. You must import `javax.security.auth.x500.X500Principal`.

Points to remember:

- `getSubjectX500Principal()` returns the X.500 Subject structure; the certificate is **not** verified just because you can call this method.
- `getName(X500Principal.RFC2253)` returns a string formatted per RFC 2253 DN rules, suitable for parsing by DN-aware libraries.
- `X509Certificate.getSubjectDN()` is a legacy API returning `Principal`; string formatting may vary between providers. Avoid building new parsers by calling `getSubjectDN().getName()` and splitting on commas.
- `X500Principal.CANONICAL` is useful in certain comparisons/normalizations, but does **not** turn a CN or DN into a stable organizational account identifier.

A DN has structure with escaping and sometimes multi-valued Relative Distinguished Names (RDNs). Do not treat it as an ordinary CSV string.

### Why Can Naive Splitting or Regex Fail?

Two valid Subjects:

~~~text
CN=Lan Tran,OU=Platform,O=Example,C=VN
CN=Nguyen\, Lan,OU=Platform,O=Example,C=VN
~~~

In the second line, `\,` is a comma **inside the CN value**, so the real principal is **Nguyen, Lan**. If you write `subjectDn.split(",")[0]` or use a regex stopping at the first comma, you may truncate the name to `Nguyen\` and produce the wrong identity.

Additional tricky cases:

- CN appears at the end of the DN, not the beginning.
- Attribute names may vary in casing, and RDN order may differ depending on representation.
- Subject may have no CN, multiple CNs, or multi-valued RDNs joined by `+`.
- DN values may contain escaped commas, equals signs, plus signs, or backslashes.
- Some Subject information may be represented as OIDs instead of human-readable aliases.
- Unicode character strings must be handled consistently; arbitrary accent stripping or case-folding can create identity collisions.

Therefore, for general Subject data, **parsing by RDN** or using an X.500-aware extractor is more reliable than running a regex directly on the DN string.

## 4. Java 17+: Complete Program Extracting Exactly One CN

The following example uses APIs built into JDK 17 (no Spring needed). It constructs `X500Principal` instances to simulate Subject fields, parses the DN using `LdapName`/`Rdn`, and intentionally **rejects** certificates that do not have exactly one non-blank CN.

Create file **SubjectPrincipalDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.ldap.LdapName;
import javax.naming.ldap.Rdn;
import javax.security.auth.x500.X500Principal;

public class SubjectPrincipalDemo {

    static String singleCn(X500Principal subject) throws NamingException {
        LdapName dn = new LdapName(
                subject.getName(X500Principal.RFC2253));

        List<String> names = new ArrayList<>();
        for (Rdn rdn : dn.getRdns()) {
            Attribute cn = rdn.toAttributes().get("CN");
            if (cn == null) {
                continue;
            }

            for (int index = 0; index < cn.size(); index++) {
                Object raw = cn.get(index);
                if (!(raw instanceof String text)) {
                    throw new IllegalArgumentException("CN must be text");
                }
                names.add(text);
            }
        }

        if (names.size() != 1 || names.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Subject must contain exactly one non-blank CN");
        }
        return names.get(0);
    }

    public static void main(String[] args) throws NamingException {
        X500Principal first = new X500Principal(
                "CN=Lan Tran,OU=Platform,O=Example,C=VN");
        X500Principal escaped = new X500Principal(
                "CN=Nguyen\\, Lan,OU=Platform,O=Example,C=VN");

        System.out.println("Simple CN: " + singleCn(first));
        System.out.println("Escaped CN: " + singleCn(escaped));

        try {
            singleCn(new X500Principal("OU=Platform,O=Example,C=VN"));
        } catch (IllegalArgumentException expected) {
            System.out.println("Missing CN rejected");
        }

        try {
            singleCn(new X500Principal(
                    "CN=Lan,CN=Other,O=Example,C=VN"));
        } catch (IllegalArgumentException expected) {
            System.out.println("Multiple CN rejected");
        }
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac SubjectPrincipalDemo.java
java SubjectPrincipalDemo
~~~

Exact expected stdout:

~~~text
Simple CN: Lan Tran
Escaped CN: Nguyen, Lan
Missing CN rejected
Multiple CN rejected
~~~

**Why does the program handle escaped commas?** `X500Principal` and `LdapName` understand DN structure; `Rdn.toAttributes()` returns the unescaped CN attribute value, so `Nguyen\, Lan` becomes `Nguyen, Lan` instead of being split in the middle. Counting CNs before returning prevents the program from arbitrarily picking one of two CNs.

Limitations of the example:

- The `X500Principal` instances are **constructed from strings**, solely to test extraction logic. They are **not** real certificates and do not prove CA/certificate chain validity.
- This method implements a **single-CN policy**. Some CA profiles use Subjects without a CN or put identifiers in SAN; in those cases, choose a different extraction rule instead of ignoring errors.
- Organizational identification rules must be applied after parsing (e.g., exact match against a list of services issued certificates). Do not accept any arbitrary CN as a privileged account.
- Do not automatically `trim()` or alter casing unless the system defines normalization and collision checks. Such transformations can merge two distinct identities into one.

## 5. Regex for Extracting CN in Spring Security

Traditional Spring Security versions use `SubjectDnX509PrincipalExtractor`, which takes the Subject DN from the certificate and finds the principal via a regular expression. The pattern commonly documented is:

~~~regex
CN=(.*?)(?:,|$)
~~~

There is only **one capturing group**: `(.*?)`. With a simple subject `CN=svc-orders,OU=Backend,O=Example,C=VN`, the result is `svc-orders`. `(?:,|$)` is a non-capturing group, terminating the match at a comma or end of string. Spring Security handles matching case-insensitively in the legacy extractor.

When using the Spring Security 6.x Servlet DSL, you can set the extraction pattern:

~~~java
@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        UserDetailsService users) throws Exception {

    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/internal/**")
                    .hasAuthority("INTERNAL_ACCESS")
                    .anyRequest().authenticated())
            .x509(x509 -> x509
                    .subjectPrincipalRegex("CN=(.*?)(?:,|$)")
                    .userDetailsService(users))
            .build();
}
~~~

This is a **Spring configuration snippet** requiring imports for `org.springframework.context.annotation.Bean`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.security.web.SecurityFilterChain`, and `org.springframework.security.core.userdetails.UserDetailsService`. It requires a Servlet app with Spring Security, proper TLS client certificate configuration, and a real `UserDetailsService` returning the `INTERNAL_ACCESS` authority for allowed accounts. The snippet **does not start an HTTPS server itself**, nor does it create a user service.

If you do not need to override the default extraction, `.x509(Customizer.withDefaults())` is usually enough to enable the X.509 mechanism, provided TLS and the account lookup service are already configured.

### Limitations of the Default Regex

The regex above is useful for certificate profiles with simple CNs, but has limitations:

1. **Escaped comma:** `CN=Nguyen\, Lan,...` may stop in the middle of the value.
2. **Multiple CNs:** the regex picks one match without verifying CN uniqueness across the entire DN.
3. **Missing CN:** no match; the extractor cannot produce a valid username. Never convert the error into an anonymous admin or default principal.
4. **CN inside unusual attribute strings:** regex operates on text without full understanding of X.500 boundaries/escaping.
5. **CN is not a policy identity:** even if extracted accurately, it may still lack a valid account mapping.

Therefore, use regex only when the **certificate profile is controlled** and edge cases are thoroughly tested. When high assurance is required, use a custom `X509PrincipalExtractor` built on an X.500 parser and identity policy.

### Replacing the Extractor in an Application

A design option (illustrative snippet, depends on Spring Security version):

~~~java
X509PrincipalExtractor extractor = certificate -> {
    try {
        return SubjectIdentityRules.singleCn(
                certificate.getSubjectX500Principal());
    } catch (NamingException ex) {
        throw new IllegalArgumentException(
                "Invalid certificate subject", ex);
    }
};
~~~

`SubjectIdentityRules.singleCn(...)` here is a **custom-implemented method**, which can adapt the logic from Section 4 into an application class. When configuring x509, attach the extractor to the DSL via `x509PrincipalExtractor(...)` if supported by your Spring Security version; or configure `X509AuthenticationFilter` according to the active version's API. Do not treat the snippet above as a complete standalone configuration.

**Version note:** In Spring Security 7.x, `SubjectDnX509PrincipalExtractor` and the `subjectPrincipalRegex(...)` DSL are marked deprecated in current API docs; `SubjectX500PrincipalExtractor` is available to extract CN or email address from the X.500 principal in a more structured way. For applications on Spring Security 6.x, check the corresponding API and pick an extractor supported in that version; do not import a 7.x class into a 6.x project and expect it to compile.

## 6. SubjectX500PrincipalExtractor in Spring Security 7.x

In Spring Security 7.x, `SubjectX500PrincipalExtractor` is introduced in API docs to extract from `X509Certificate.getSubjectX500Principal()`; by default it extracts the **CN** value, and can be configured to select the Subject's emailAddress attribute:

~~~java
SubjectX500PrincipalExtractor extractor =
        new SubjectX500PrincipalExtractor();

extractor.setExtractPrincipalNameFromEmail(true);
~~~

This is a **snippet for Spring Security 7.x**, requiring `import org.springframework.security.web.authentication.preauth.x509.SubjectX500PrincipalExtractor`. When the option is `true`, the extractor reads the `emailAddress` attribute **in the Subject DN**, and **does not automatically read `rfc822Name` from SAN**. This distinction matters when a certificate only carries the email in SAN.

Do not blindly switch all systems from CN to emailAddress, because email names can change, may be recycled, and certificate issuance processes might not guarantee email uniqueness. CA policy, lookup, and permission tests must be updated together.

## 7. Accurate Extraction Does Not Mean Proper Authentication/Authorization

Suppose Subject DN contains `CN=svc-orders` and the extractor returns the String `svc-orders`. Distinguish:

| Step | Output Data | Question to Answer |
| --- | --- | --- |
| TLS validation | Certificate accepted under TLS policy | Is the certificate from a trusted source and permitted for use as a client certificate? |
| Principal extraction | `svc-orders` | Which certificate field is designated as the identifier? |
| Identity lookup | Service account in application | Is there exactly one active account mapped to this principal? |
| Authority loading | E.g., `INTERNAL_ACCESS` | Which permissions does the account hold at authentication time? |
| Authorization | Allow/deny for specific request | Are those permissions sufficient for the accessed endpoint and resource? |

Spring Security X.509 pre-authentication can use `UserDetailsService` to look up the user from the extracted principal. If no matching user exists, the application must treat it as an invalid authentication according to configuration. If the username is found, permissions are granted from the user store/provider, **never derived automatically from CN or OU**.

For instance, a certificate issued by a trusted CA carrying CN `visitor` must not automatically receive `INTERNAL_ACCESS`, unless the application explicitly maps `visitor` to a granted account. Likewise, never automatically allow CN `admin` just because that word appears in the Subject.

When designing mapping, prioritize:

1. Defining the trust domain/issuer and certificate profiles the application accepts.
2. Defining the identity attribute to read (CN, Subject UID, SAN URI, or another name).
3. Applying rules to check **uniqueness and stability** of the identity within the CA/tenant scope.
4. Looking up accounts by controlled keys and policies; failing closed when not found or non-unique.
5. Loading authorities from the user store and applying fine-grained resource policies.

Two certificates having the same CN text from two different CAs **does not guarantee** they belong to the same account. If the system trusts multiple CAs/tenants, looking up solely by CN can cause collisions; include issuer/trust domain context or use an identifier guaranteed unique by the CA profile.

## 8. Subject and SAN: Choosing Identifiers by Certificate Profile

Not every certificate type should take its principal from Subject CN.

| Certificate Profile | Identifier Strategy to Consider | Risk When Forcing CN |
| --- | --- | --- |
| Internal user certificate, CA enforces unique CN | Controlled CN mapped to user account | Personal names can collide or change |
| Service mTLS certificate with SAN URI workload ID | SAN URI matching allowed namespace/workload ID | CN may be generic, missing, or unstable |
| Client certificate with SAN `rfc822Name` | Email SAN if CA profile guarantees subject binding | Email in Subject may not match SAN |
| Certificate with empty Subject and SAN as primary ID | Read SAN via certificate API and verify expected SAN type | CN regex fails to match |
| Multiple CAs/tenants issuing same CN | Identifier paired with issuer/trust domain or global SAN ID | Identity collision across issuers |

In the JDK, `X509Certificate.getSubjectAlternativeNames()` exposes the SAN extension as a structured collection. SAN entries have distinct **type** and **value** pairs; for example `dNSName`, `rfc822Name`, `uniformResourceIdentifier`, `iPAddress`. Do not run a CN regex across all SANs and blindly take the first value. Define the expected type, format, namespace constraints, issuing CA, and matching policy upfront.

If a workload uses a URI identity such as `spiffe://example.org/ns/prod/sa/orders`, that is normally the **SAN URI** value in the corresponding profile, not the Subject CN. Extracting SAN URIs and matching trust domains is a dedicated identity strategy that must follow the chosen standard/infrastructure.

## 9. Parser and Identity Bugs That Become Vulnerabilities

### 9.1 Splitting Strings at Commas or Equals Signs

DNs have escaping, so `split(",")` and `split("=")` do not parse reliably. Use a parser API; if regex is unavoidable, strictly constrain input format via certificate issuance policy and test escaped cases.

### 9.2 Accepting the First CN When Multiple CNs Exist

Multiple RDNs with the same attribute type or multi-valued RDNs can occur. If policy requires a single CN, **count and reject if the count is not one**. Do not assume the first value is always right just because a string was read.

### 9.3 Using CN Directly for Authorization

Fundamentally flawed:

~~~java
// Anti-pattern: do not use CN to self-grant privileges.
boolean isAdmin = extractedCn.equalsIgnoreCase("admin");
~~~

CN is an identifying value issued in a certificate, not a business permission decision. Use the principal to look up an account in a trusted user store, then evaluate `GrantedAuthority` and resource policies.

### 9.4 Ignoring Certificates from Different CAs

CA A and CA B can issue certificates with the same CN. If both are trusted without unified policy, mapping by CN alone can cause account collisions. Scope by issuer/trust domain or use an identifier key guaranteed to be unique.

### 9.5 Using Fingerprint as Username Without Considering Lifecycle

A certificate's fingerprint changes upon renewal/replacement; issuer+serial identifies a specific certificate and also changes on renewal. If you need a durable identity across lifecycles, choose an attribute guaranteed by the CA profile (e.g., SAN workload ID) and manage certificate → account mappings in a controlled way. No single key fits every system.

### 9.6 Trusting Certificates Forwarded Over Unprotected HTTP Headers

If TLS terminates at a reverse proxy, the backend may not receive the certificate from the servlet container. A header like `X-Client-Cert` **has no authentication value** if external clients can send or spoof it themselves. To pass verified identity from a proxy to a backend, ensure the proxy strips client-supplied headers, accept only from trusted proxy–backend connections, authenticate the internal channel, and verify forwarded content under a clear contract. Never assume Spring Security x509 understands arbitrary forwarded headers.

### 9.7 Confusing Subject CN with TLS Server Name

CN/SAN used to verify the **server's name** in an HTTPS client is a different problem from **extracting a client certificate principal** on the server. Avoid mechanically applying hostname verification rules to client account mapping; TLS mechanisms and identity policies must be defined separately.

## 10. Infrastructure Setup So Subject Comes from a Real Certificate

In a Spring Boot Servlet app using direct HTTPS, infrastructure typically requires:

- **Server keystore**: private key and server certificate to establish HTTPS.
- **Truststore for client certificates**: trust anchors/CAs accepted by the server for client authentication.
- **Client authentication mode**: mode requiring or requesting client certificates; if all endpoints require a cert, the configuration must enforce it.
- **Certificate policy**: chain, validity, key usage/extended key usage (when applicable), constraints, revocation, and other enterprise checks performed by TLS/infrastructure.
- **Spring Security x509 + user lookup**: receives the principal from the certificate presented to the container, looks up the account and permissions.

Example partial TLS configuration (real files and secrets must be supplied by the environment):

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    client-auth: need
    key-store: classpath:server-keystore.p12
    key-store-type: PKCS12
    trust-store: classpath:client-truststore.p12
    trust-store-type: PKCS12
~~~

This is an **illustrative configuration snippet**: keystore/truststore passwords must also be provided through appropriate secrets mechanisms alongside valid certificates/keys. Do not place passwords or private keys in documentation or source code. `client-auth: need` requires a certificate at the TLS level for the connection; `want` lets clients connect without sending a certificate depending on configuration. If only a subset of endpoints requires mTLS, you may need separate listeners/gateways or a different deployment policy; do not assume HTTP paths can alter TLS handshake rules after a connection is established.

If using Kubernetes ingress/API gateway/load balancer to terminate TLS, pinpoint where mTLS is verified and the contract for passing identity to the app. Test from outside directly toward the backend to verify no one can bypass the proxy and inject forged headers.

## 11. Inspecting Subject with System Tools

To inspect the Subject DN of a PEM certificate in a test environment:

~~~bash
openssl x509 -in client.pem -noout -subject -nameopt RFC2253
~~~

To inspect Subject Alternative Name:

~~~bash
openssl x509 -in client.pem -noout -ext subjectAltName
~~~

OpenSSL commands may display slightly different formatting across versions/flags. The output is for inspecting the **profile**, not proof that the application authenticated the client over TLS. When debugging, also inspect issuer, validity dates, EKU, and trust chain setup; `-subject` alone is not enough to conclude the certificate will be accepted.

Send an mTLS request from an environment with a test client certificate and private key:

~~~bash
curl --cert client.pem --key client-key.pem \
     --cacert server-ca.pem \
     https://localhost:8443/internal/whoami
~~~

This is a **conditional illustrative command**: URL, CA, endpoint, and credentials must exist; there is no fixed standard stdout. The endpoint should only echo username/authorities in development environments, and never dump full certificates/private keys to logs. If the server does not receive the certificate, check the handshake, truststore, and TLS termination point before debugging regexes.

In a Servlet app, you can write safe diagnostic logs by logging only the identity source name and request ID. Avoid logging full PEMs, personal identifiers, or full Subject DNs in production unless explicitly justified and protected.

## 12. Testing Principal Extraction

A test suite for a CN extractor should cover at least the following scenarios:

| Subject or Environment | Expected Result |
| --- | --- |
| `CN=svc-orders,OU=Backend,O=Example,C=VN` | `svc-orders` |
| `CN=Lan Tran,OU=Platform,O=Example,C=VN` | `Lan Tran` |
| `CN=Nguyen\, Lan,OU=Platform,O=Example,C=VN` | `Nguyen, Lan` |
| `OU=Platform,O=Example,C=VN` | Reject if policy requires CN |
| `CN=first,CN=second,O=Example,C=VN` | Reject if policy requires exactly one CN |
| Empty or whitespace-only CN | Reject |
| Identifying SAN present, but Subject has no CN | Reject under CN policy; or use controlled SAN extractor |
| Two certificates from two CAs with same CN | Do not merge identities if trust domain/tenant differs |
| Valid certificate, but no matching account | Application authentication fails |
| Untrusted certificate/chain | TLS rejects before principal extraction |
| Valid certificate, disabled account | Do not grant access just because CN matches |
| Valid certificate, missing endpoint authority | Authorization denies |
| Client-sent header containing forged DN | Not treated as a verified certificate |

Test at **two levels**:

1. **Parser unit tests:** use `X500Principal`/mock DNs to verify CN splitting, escaping, attribute counts, and error messages.
2. **TLS + Spring Security integration tests:** use a test CA, certificates, and real accounts in the test environment; observe the app receiving the certificate via the container, trust policies working, and `Authentication.getName()`/authorities matching.

MockMvc tests with mocked request certificates are useful for testing filters/lookup, but **do not replace** real TLS handshake and truststore tests. A unit test extracting `svc-orders` does not prove the transport layer verified the certificate.

## 13. Analysis of Three Practical Scenarios

### Scenario A: Username Truncated at Comma

The certificate has `CN=Nguyen\, Lan,...`, and a legacy regex returns only the string before the comma. This causes `UserDetailsService` to fail to find the account or look up a similarly named account by mistake.

**Remediation:** replace with an extractor using `X500Principal`/`LdapName` or standardize the issuance profile; write tests with escaped commas.

### Scenario B: Certificate Present Yet Still 403

The TLS client certificate is valid and the principal extracts accurately, but the user store does not grant the authority required by the endpoint. This is usually an account/permission mapping error or access policy issue, not a parser bug by default.

**Remediation:** verify which account the principal maps to, enabled/locked status, actual authorities on `Authentication`, and `hasAuthority`/`hasRole` expressions on the endpoint. Do not fix by disabling security for the entire URL.

### Scenario C: System Uses SAN URI, CN Is Wrong

The CA issues workload certificates with SAN URI as the primary identifier; the Subject may be generic or omit CN. Choosing CN produces an incorrect or empty principal.

**Remediation:** coordinate with the PKI team to finalize the certificate profile; define an extractor that reads the right SAN type, checks the trust domain, and maps accounts by organization-managed IDs. Never arbitrarily pull CN, OU, or email from a certificate without explicit rules.

## 14. Suggested Implementation Workflow

1. **Finalize certificate profile:** who issues it, trust anchors, client certificate type, which identity fields are guaranteed, whether SAN is present, and DN structure.
2. **Finalize principal rules:** single CN, another subject attribute, or a specific SAN type; define how missing/duplicate/escaped/renamed cases are handled.
3. **Configure TLS:** verify chain, client-auth, truststore, TLS termination, and paths through proxies/gateways.
4. **Install version-appropriate Spring Security extractor:** use classes/APIs matching your runtime library; prefer structured parsers for complex DNs.
5. **Map to accounts and permissions:** fail closed when missing or disabled; never grant permissions from free-form text in Subject.
6. **Multi-layer testing:** unit test extraction, integration test mTLS, certificate renewal, account revocation, authorization, and identity collisions.
7. **Operational monitoring:** log errors with correlation IDs and high-level reasons (keep private keys/sensitive certificates out of logs), tracking handshake and lookup failures independently.

### Self-Check Questions

- If `Subject=CN=Lan Tran,OU=Platform,O=Example,C=VN`, what is the difference between **DN** and **principal**?
- Why does `CN=Nguyen\, Lan` cause `split(",")` to return the wrong result?
- If a client sends a certificate from an untrusted CA whose CN matches an admin account, why must login be denied?
- Is `SubjectX500PrincipalExtractor` reading `emailAddress` in Subject the same as reading `rfc822Name` in SAN?
- If two CAs issue the same CN, what information does the application need to avoid confusing identities?
- Is a successfully extracted principal enough to decide `hasAuthority("INTERNAL_ACCESS")`?

### Technical Documentation

- Spring Security – X.509 (Servlet): https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html
- Spring Security – Pre-Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/preauth.html
- Spring Security – X509PrincipalExtractor API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/x509/X509PrincipalExtractor.html
- Spring Security – SubjectDnX509PrincipalExtractor API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/x509/SubjectDnX509PrincipalExtractor.html
- Spring Security – SubjectX500PrincipalExtractor API (7.x): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/x509/SubjectX500PrincipalExtractor.html
- Java SE – X500Principal: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/security/auth/x500/X500Principal.html
- Java SE – X509Certificate: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/X509Certificate.html
- Java SE – LdapName: https://docs.oracle.com/en/java/javase/21/docs/api/java.naming/javax/naming/ldap/LdapName.html
