# Diagnosing Non-Negotiated SPNEGO and Service Principal Mismatches

> **Module:** Spring Security – federation. **Category:** Observability and debugging. **Scenario:** A Spring Security application protects §https://portal.example.org/private§ with HTTP Negotiate/Kerberos, yet the browser only shows a login page or repeatedly returns §401§. Or the browser already sent a token, yet Java/JGSS reports a wrong service principal/keytab. This lesson presents a **hop-by-hop evidence-gathering method** so you do not confuse HTTP challenge, browser policy, KDC/SPN, keytab, TLS channel binding, and application authorization errors. Examples favor **Java 17**, the Spring Security Kerberos extension, and Active Directory/MIT Kerberos; never use production secrets in tests.

## 1. Learning Objectives and Prerequisites

After this lesson, you must be able to:

1. Explain the §401 WWW-Authenticate: Negotiate§ / §Authorization: Negotiate ...§ handshake, recognizing when **the browser fails to negotiate** vs. when **it negotiated yet the ticket failed verification**.
2. Separate §401§ from the **origin server** from §407 Proxy Authentication Required§ from an explicit proxy; pinpoint blocks at CDN/ingress/WAF/reverse proxy.
3. Diagnose four distinct failures: **no challenge**, **browser does not send token**, **KDC does not issue ticket for SPN**, and **acceptor cannot decrypt ticket for SPN**.
4. Derive the exact §HTTP/portal.example.org@EXAMPLE.ORG§ from the public URL; avoid mistakenly using §HTTP/node-7.internal§ or a machine account.
5. Verify DNS canonicalization, CNAME/aliases, Kerberos realm, unique SPN in AD, keytab principal/KVNO/enctype, and file permissions inside containers.
6. Understand symptoms of §KDC_ERR_S_PRINCIPAL_UNKNOWN§, §KDC_ERR_PRINCIPAL_NOT_UNIQUE§, §KRB_AP_ERR_MODIFIED§, §KRB_AP_ERR_SKEW§, §KDC_ERR_ETYPE_NOTSUPP§, §GSSException: No valid credentials§, and possible NTLM fallback.
7. Distinguish the **client initiator** requesting a service ticket from the **server acceptor** using JAAS/keytab to validate the ticket; never grab a user's TGT on Portal to "fix login".
8. Configure and observe §SpnegoEntryPoint§, §SpnegoAuthenticationProcessingFilter§, §KerberosServiceAuthenticationProvider§, §SunJaasKerberosTicketValidator§, and Spring Security filter chains by version.
9. Use safe metadata-reading commands §curl§, §klist§, §kvno§, §setspn -Q§, §klist -k -e§, and a Java 17 demo to isolate failures; never log raw tokens/keys.
10. Design negative tests and write an investigation runbook with Expected/Actual, protecting secrets and enforcing the **fail closed** principle.

**Prerequisites:** HTTP 401/403/407, TLS/HTTPS, DNS FQDN, Kerberos KDC/AS/TGS/TGT/service ticket, realm/SPN, JAAS/JGSS, Java 17, Spring Security §SecurityFilterChain§, Active Directory or MIT KDC.

**Versioning:** Spring Security Kerberos is an **extension** requiring a compatible library; Spring Boot core has no standard switch to "enable SPNEGO". Filter/validator APIs and configuration differ across Spring Security Kerberos versions. Never copy XML from legacy Spring Security docs into Boot 3.5 without checking dependencies and integration tests.

## 2. What Should Healthy SPNEGO Look Like?

A browser already holding a domain Kerberos TGT and permitted Integrated Authentication to §portal.example.org§:

~~~text
Browser                  Portal Spring/JGSS                KDC/AD
  |                              |                            |
  | GET /private                 |                            |
  |----------------------------->|                            |
  | 401 WWW-Authenticate: Negotiate                         |
  |<-----------------------------|                            |
  |                              |                            |
  | request ticket for HTTP/portal.example.org ------------->|
  |<-------------------------------------- service ticket ----|
  |                              |                            |
  | GET /private                 |                            |
  | Authorization: Negotiate <opaque-SPNEGO-token>            |
  |----------------------------->|                            |
  |                              |  GSS accept using keytab   |
  |                              |  map user + authorities    |
  | 200 (authorized) or 403      |                            |
  |<-----------------------------|                            |
~~~

Two distinctions to keep absolute:

- **Negotiate** is an **HTTP authentication scheme**/SPNEGO negotiation. Seeing §Authorization: Negotiate§ does not guarantee the token holds Kerberos; on Windows, Negotiate can fall back to **NTLM** per client policy. A Java acceptor configured for Kerberos may reject NTLM tokens. Verify the actual mechanism using appropriate sanitized tooling/traces.
- **Authentication success** does not automatically mean HTTP 200. If Spring authenticated §lan@EXAMPLE.ORG§ yet the user lacks §ROLE_REPORT_READER§, the right result is **403**. Never edit SPN/keytab when the issue is authorization.

How to spot the difference:
1. Only §302 /login§ or §401§ **without** §WWW-Authenticate: Negotiate§: the issue is usually entry point, URL routing, filter chain, ingress, or a form-login priority policy.
2. §401 Negotiate§ is present yet the browser **never** sends §Authorization: Negotiate§: browser/OS/zone/domain/credential acquisition, or proxy stripping the header.
3. Browser sends §Authorization: Negotiate§ yet keeps getting 401: server filter/validator/GSS/keytab, KDC service ticket/SPN, NTLM fallback, TLS channel binding, or replay/clock skew.
4. GSS accept succeeds and Spring has a principal, yet returns §403§: business roles, account mapping, or tenant/resource authorization.
5. §200§ after form/Basic fallback: does not prove SPNEGO used Kerberos! Verify the authentication mechanism and accepted principal on the server from **verified** evidence.

## 3. Observability Framework: Collecting Evidence from Client to Server

Do not touch the keytab immediately. Create a **correlation ID** for the test call, use an isolated browser profile, and request a **protected endpoint** known to require Negotiate, such as §/private§.

| Hop | Diagnostic Question | Minimum Evidence |
| --- | --- | --- |
| Browser → edge | What are the public URL and scheme/host/port/path? | Normalized URL/Host, HTTP status |
| Edge → client | Does the response have §WWW-Authenticate: Negotiate§? | Header presence, never log ticket |
| Browser → edge | Does the browser return §Authorization: Negotiate§? | **Presence and scheme** only, no raw value |
| Edge → app | Does the reverse proxy forward the Authorization header intact? | Boolean presence at ingress and app |
| Browser → KDC | Does the browser have a TGT, and for which SPN did it request a service ticket? | Target service principal, KDC status, no ticket bytes |
| KDC/AD | Does the SPN exist, is it unique, and does it belong to the right service account? | §setspn -Q§/DC event IDs |
| App JVM | Which `krb5.conf`/JAAS/keytab is Java reading? | Approved config paths, runtime UID |
| Acceptor | Does the keytab have principal/KVNO/enctype matching the ticket? | §klist -k -e§ metadata and GSS outcome |
| Spring | Did the filter/provider receive the ticket and set the right principal? | Result type + error category, no raw token |
| Authorization | Does the user have permission for the protected resource? | 200 or 403 per policy, never bypass |

**Important:** Never paste raw browser HARs, §Authorization§ tokens, §WWW-Authenticate§ headers with payload tokens, TGT/service tickets, KRB5CCNAME caches, keytabs, passwords, or private keys into logs/chat. Collect redacted metadata only. §WWW-Authenticate: Negotiate§ can carry a server token during negotiation rounds; never log the full header value, only the scheme.

### 3.1. Cookie-Free Baseline Request

In a sandbox with trusted TLS:

~~~bash
# Do not use -k to skip TLS verification.
# Do not use --negotiate in the initial test checking the server challenge.
curl --head --max-redirs 0 https://portal.example.org/private

# Or use GET and capture only response headers, avoiding logging sensitive bodies:
curl -sS -D /dev/stderr -o /dev/null \
  --max-redirs 0 https://portal.example.org/private
~~~

**Expected behavior depends on routing:** An unauthenticated protected endpoint normally returns §401§ with §WWW-Authenticate: Negotiate§ if the SPNEGO entry point is active. If it returns §302 Location: /login§, inspect Spring entry point/form login priority; if §200§, the endpoint may be `permitAll`, cookies/sessions may still be attached, or ingress bypassed auth. §curl --head§ sends HEAD, which may behave differently from GET if endpoint filters differ; compare GET and HEAD before concluding.

Never run §curl -v§/§--trace§ into a terminal captured by production logs where it can print bearer headers/cookies. Never store stdout containing raw Negotiate tokens in CI artifacts.

### 3.2. HTTP 401 Differs from HTTP 407

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

This is the **origin web server** requesting authentication. If you see:

~~~http
HTTP/1.1 407 Proxy Authentication Required
Proxy-Authenticate: Negotiate
~~~

it may be an **explicit HTTP proxy**, not Portal. When a browser uses a proxy, there are two separate trust boundaries: §Proxy-Authorization§ is for the proxy and §Authorization§ is for Portal. Never send proxy credentials to the origin or vice versa. Check PAC/WPAD, proxy bypass lists, VPN/corporate egress, and where the response actually originated.

### 3.3. Correlation: One Trace per Attempt

Use a sanitized record:

~~~text
case=SPNEGO-CASE-17
browser_url=https://portal.example.org/private
response_status=401
www_authenticate_has_negotiate=true
client_sent_authorization_negotiate=false
ingress_forwarded_authorization=not_applicable
os_has_tgt=true
requested_spn=not_observed
spring_entry_point=SpnegoEntryPoint
outcome=CLIENT_TOKEN_MISSING
raw_token_logged=false
~~~

Never put raw §Authorization§/cookies into the record. Record only hostnames, principal aliases, and IDs allowlisted by security policy.

## 4. Decision Tree by Where the Failure Occurs

~~~text
GET /private (unauthenticated browser)
   |
   +-- Server does not return 401 WWW-Authenticate: Negotiate?
   |      -> Check SecurityFilterChain, SpnegoEntryPoint, ingress/CDN
   |         /login redirect, permitAll, Basic/Form priority
   |
   +-- Server returned 401 Negotiate
           |
           +-- Browser does not send Authorization: Negotiate?
           |      -> Browser allowlist/Integrated Auth, TGT, proxy, DNS,
           |         zone, KDC reachability, service ticket acquisition
           |
           +-- Browser sends Authorization: Negotiate
                   |
                   +-- Header does not reach backend?
                   |      -> Reverse proxy/WAF strips Authorization
                   |
                   +-- Header reaches backend
                           |
                           +-- SPNEGO/NTLM mechanism mismatch?
                           |      -> Verify Kerberos vs. NTLM
                           |
                           +-- KDC does not know target SPN?
                           |      -> SPN registration/realm/DNS
                           |
                           +-- Server cannot decrypt ticket?
                           |      -> keytab principal, KVNO, enctype, UID,
                           |         TLS channel binding / SPN mismatch
                           |
                           +-- GSS passes, Spring auth fails?
                           |      -> Provider/UserDetailsService/roles
                           |
                           +-- Spring auth passes, HTTP 403?
                                  -> Business authorization/tenant/resource
~~~

**Never conflate branches:** §No service ticket issued§ and §service ticket issued but acceptor cannot decrypt§ have different causes and different teams authorized to fix them. Who edits AD SPNs differs from who edits Spring Security filters, Kubernetes mounts, or client browser policies.

## 5. Branch A: Server Fails to Send Negotiate Challenge

A §401§ response without §WWW-Authenticate: Negotiate§ **is not a valid SPNEGO handshake**. Before running §setspn§ or opening a keytab, inspect the filter chain:

- Is §/private§ truly §authenticated()§, or is it §permitAll()§?
- Are there multiple §SecurityFilterChain§s with §@Order§ and §securityMatcher§? Did the request fall into a form-login/Basic chain instead of the SPNEGO chain?
- Is §SpnegoEntryPoint§ registered as the §AuthenticationEntryPoint§ for the protected URL, or is the default §LoginUrlAuthenticationEntryPoint§ redirecting to §/login§?
- Is §SpnegoAuthenticationProcessingFilter§ placed in the right filter chain before controllers? A standalone bean does not automatically insert itself into a chain.
- Is an upstream Nginx/Apache/API Gateway generating §302§/§401§ before the request reaches Spring?
- Are CORS preflight §OPTIONS§, static assets, or health endpoints being confused with protected GETs?
- With an already-authenticated session, Spring may return 200 instead of a challenge. Use a clean browser/curl **without cookies** for baseline checks.
- If the RP uses OIDC/SAML on the same URL and security config prioritizes it, §WWW-Authenticate: Negotiate§ will not appear even if the Java keytab is valid.

**Sample Spring Security Kerberos integration beans (fragment only, NOT a standalone runnable app):**

~~~java
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;

@Bean
SunJaasKerberosTicketValidator kerberosTicketValidator() {
    SunJaasKerberosTicketValidator validator =
            new SunJaasKerberosTicketValidator();
    validator.setServicePrincipal("HTTP/portal.example.org@EXAMPLE.ORG");
    validator.setKeyTabLocation(
            new FileSystemResource("/run/secrets/kerberos/http-portal.keytab"));
    validator.setDebug(false);
    return validator;
}

@Bean
KerberosServiceAuthenticationProvider kerberosProvider(
        SunJaasKerberosTicketValidator validator,
        UserDetailsService users) {
    KerberosServiceAuthenticationProvider provider =
            new KerberosServiceAuthenticationProvider();
    provider.setTicketValidator(validator);
    provider.setUserDetailsService(users);
    return provider;
}

@Bean
SpnegoEntryPoint spnegoEntryPoint() {
    return new SpnegoEntryPoint();
}

@Bean
SpnegoAuthenticationProcessingFilter spnegoFilter(
        AuthenticationManager manager) {
    SpnegoAuthenticationProcessingFilter filter =
            new SpnegoAuthenticationProcessingFilter();
    filter.setAuthenticationManager(manager);
    return filter;
}
~~~

**Limitations:** You need imports for Spring annotations, §AuthenticationManager§/§UserDetailsService§, a compatible Spring Security Kerberos dependency version, a §SecurityFilterChain§ wiring entry point/filter/provider, KDC, TLS, keytab, and account mapping. Never copy this fragment expecting SPNEGO to enable itself automatically. There is no core Spring Boot property §spring.security.kerberos.enabled=true§ that guarantees full setup.

**Conceptual wiring example** for a dedicated SPNEGO chain:

~~~java
// Configuration fragment: confirm exact API and @Order for your version.
http
    .securityMatcher("/private/**")
    .authorizeHttpRequests(a -> a.anyRequest().authenticated())
    .exceptionHandling(e -> e.authenticationEntryPoint(spnegoEntryPoint))
    .addFilterBefore(spnegoFilter, BasicAuthenticationFilter.class);
~~~

If the app also hosts HTML/OIDC login on other URLs, apply §securityMatcher§ and filter ordering deliberately. Do not accidentally leave a §permitAll()§ chain catching §/private/**§ ahead of the SPNEGO chain. With custom filter beans, check whether Spring Boot auto-registers the servlet filter once outside Spring Security and then your config adds it into `SecurityFilterChain` a second time.

## 6. Branch B: Challenge Sent Yet Browser Omits Authorization: Negotiate

When §401 WWW-Authenticate: Negotiate§ reached the browser yet no §Authorization: Negotiate§ follows, **there is no evidence yet that the server keytab is wrong**. The server has not received a ticket to validate. Check the client in order:

1. Is the user logged into the domain / holding a valid Kerberos TGT?
2. Is the site's FQDN in the browser/OS **Integrated Authentication allowlist/trusted zone**?
3. Is the browser allowed to use Negotiate, and does policy restrict the auth server whitelist?
4. Is the user accessing via **FQDN** rather than IP/localhost/alias/different port? HTTP Kerberos relies on FQDN.
5. Can the device reach KDC/DC (VPN, DNS SRV, time, port 88)? A browser on the public Internet off-network may be unable to fetch a service ticket.
6. Is a PAC/WPAD/HTTP proxy issuing 407, or is the ticket being sent to the proxy instead of Portal?
7. Is the browser falling back to NTLM/Basic per policy, which a Java Kerberos acceptor does not support?
8. Is there an HTTP→HTTPS redirect or hostname redirect changing the SPN the client tries to request?
9. Is a cross-site iframe, browser security restriction, or access policy blocking silent integrated authentication?
10. Does CNAME/SPN canonicalization make the browser request a ticket for a **different canonical host** than the one in the server's keytab?

### 6.1. Browser Configuration: Illustrative, Must Check Active Policy

- **Microsoft Edge/Chrome on Windows:** Integrated Authentication can depend on the OS intranet zone and enterprise browser policies. Policies like §AuthServerAllowlist§ control which hosts are permitted to Negotiate; inspect active policies via the browser enterprise policy UI. Never assume all §*.example.org§ are trusted by default.
- **Firefox:** preferences like §network.negotiate-auth.trusted-uris§ and the SSPI/GSS environment determine eligible hosts. Check the Firefox version, enterprise policy, and organizational security policy; never add all public domains.
- **Linux/macOS:** Browsers need GSS-API/OS Kerberos credentials and the right §krb5.conf§/ticket cache; §kinit§/§klist§ help check the source, yet do not guarantee the browser uses the same cache/session.
- **Incognito/private profile:** cookie isolation and auth policies can differ from normal profiles; test both modes and state your setup rather than just reporting "401".

### 6.2. Windows: Check Client Tickets Before Touching the Server

On a domain-joined Windows machine, use an approved test command prompt:

~~~powershell
# List current TGT/service tickets for the Windows logon session.
klist

# Purge ticket cache ONLY in a TEST environment if authorized:
# klist purge
# The purge command can disrupt other SSO sessions.
~~~

§klist§ shows whether a service ticket for §HTTP/portal.example.org§ was issued. Never run §klist purge§ casually on a real user's workstation or domain controller. If the client cannot obtain a ticket, inspect Event Viewer/DC events and KDC logs with AD team authorization.

### 6.3. Linux/MIT Kerberos: Testing Service-Ticket Acquisition

If the sandbox already has a valid, authorized TGT:

~~~bash
# Check only the TEST user's cache; do not read production TGTs.
klist

# Request a ticket for the expected service principal:
kvno HTTP/portal.example.org@EXAMPLE.ORG

# Check the ticket cache after the request:
klist
~~~

§kvno§ asks the KDC for a ticket for the SPN; if it reports principal not found, the fault is usually in KDC registration/realm mapping, **not** the acceptor keytab. If §kvno§ returns a KVNO/ticket, that **still does not prove** the Java acceptor can decrypt the ticket. MIT tools and the JDK can read different configs: §KRB5_CONFIG§/§KRB5CCNAME§ do not automatically override Java's §-Djava.security.krb5.conf§/JAAS.

## 7. Branch C: Browser Sends Authorization Yet Token Never Reaches Spring

A reverse proxy/WAF/CDN can strip or rewrite §Authorization§ before forwarding to the JVM. Therefore observe **presence** on both sides without logging raw tokens.

~~~text
Browser:
 Authorization: Negotiate [REDACTED]
      |
      v
Ingress:
 hasAuthorizationHeader = true
      |
      v
Spring app:
 hasAuthorizationHeader = false
      |
      +--> Authentication filter lacks token
           --> Returns 401 Negotiate again
~~~

Check:
- Does the ingress/reverse proxy forward §Authorization§ intact rather than consuming it for another auth method?
- Does the WAF treat large headers as anomalous, returning §400/431§ or truncating them? Kerberos/SPNEGO tokens can be quite large.
- Did HTTP/2→HTTP/1.1 forwarding, header size limits, or upstream proxy paths change?
- Is the backend app receiving direct traffic via a bypass route (skipping the trusted ingress)?
- If ingress **authenticates Kerberos itself** and passes a signed/protected identity header to the app, that is a different trust architecture; you cannot both expect Spring to receive raw SPNEGO tokens and tell ingress to strip them.
- Never forward §Authorization: Negotiate§ to third-party clients or log it in APM/tracing.

**Never "fix" by letting browsers supply an `X-User: lan` header.** If the gateway performs authentication and the backend trusts an identity header, you must enforce mTLS/trusted networks, strip externally injected headers, authenticate the trusted proxy, and enforce user/tenant/authorization at the app.

## 8. Branch D: Header Reaches Spring Yet GSS/JAAS Rejects It

Once the token reaches §SpnegoAuthenticationProcessingFilter§, the provider validates it using the Kerberos ticket validator. Break down any "repeated 401" by layer:

- Filter never invoked or §AuthenticationManager§ lacks §KerberosServiceAuthenticationProvider§: wiring issue.
- Token is actually NTLM under the §Negotiate§ umbrella: mechanism unsupported by a Java Kerberos-only acceptor.
- Kerberos token's target SPN mismatches the keytab: acceptor principal mismatch.
- Ticket matches SPN yet uses a different key/KVNO after rotation: §KRB_AP_ERR_MODIFIED§ or decryption failure.
- Incompatible encryption type: KDC/JDK/AD crypto policy mismatch.
- JAAS Subject lacks acceptor credentials: §LoginException§/§GSSException§; wrong app keytab path or insufficient read permissions.
- Channel binding/EPA: client sends channel binding info that mismatches server/TLS termination, or policy requires binding that the Java acceptor does not supply.
- Replay/time skew: ticket used outside time bounds or same authenticator replayed.
- Acceptor GSS verifies, yet §UserDetailsService§ cannot find user/disabled account/authority mapping fails: Spring auth/application layer.

### 8.1. What Format Does a Kerberos Target SPN Take?

~~~text
Public URL:
  https://portal.example.org/private

Host-based SPN:
  HTTP/portal.example.org@EXAMPLE.ORG

Not usually:
  HTTP/portal-pod-7.internal@EXAMPLE.ORG
  HTTP/kdc1.example.org@EXAMPLE.ORG
  https://portal.example.org/private@EXAMPLE.ORG
  HTTP/192.0.2.10@EXAMPLE.ORG
~~~

An SPN is **not a full HTTP URL**: it is normally `HTTP/FQDN`, plus realm when written as a Kerberos principal. AD §setspn§ normally manages §HTTP/portal.example.org§ **without `@REALM`** in the query string; JAAS/keytab principals may include §@EXAMPLE.ORG§. HTTP SPNs do not include ports/paths by default; certain apps/clients have exceptions requiring explicit contracts.

**CNAME note:** Clients may canonicalize hostnames via DNS/CNAME depending on OS/browser/GSS config. If the browser visits §https://alias.example.org§ while requesting a ticket for §HTTP/backend.example.org§, and the keytab only holds §HTTP/portal.example.org§, they mismatch. Evidence must come from the **actual requested SPN**, not guesses from the address bar.

### 8.2. KDC Missing SPN vs. Acceptor Cannot Decrypt Ticket

~~~text
Case 1 – KDC_ERR_S_PRINCIPAL_UNKNOWN:
  Browser asks KDC for HTTP/portal.example.org
  KDC has no such SPN
  -> Client cannot obtain Kerberos service ticket
  -> No valid Kerberos token reaches Portal

Case 2 – KRB_AP_ERR_MODIFIED:
  KDC finds SPN on account svc-web-A
  Browser obtains service ticket encrypted for svc-web-A
  Portal keytab actually has key for svc-web-B / stale KVNO
  -> Java acceptor cannot decrypt/verify ticket
~~~

With duplicate SPNs, a KDC may return §KDC_ERR_PRINCIPAL_NOT_UNIQUE§ or the client may see a related error depending on AD/realm. §KRB_AP_ERR_MODIFIED§ has **multiple causes**; never blame every occurrence on duplicate SPNs. Inspect KDC/server events, KVNO/enctype, account identity, time, TLS binding, and network.

### 8.3. AD SPN Query: Inspect Only, Never Edit Arbitrarily

Run on a machine with RSAT/AD read permissions per organizational policy:

~~~powershell
# Query a specific SPN:
setspn -Q HTTP/portal.example.org

# Query duplicate SPNs within supported/administered scope:
setspn -X
~~~

If §setspn -Q§ finds no SPN or shows it on the wrong account, **escalate to the AD/Identity team**. Only approved AD admins should consider modifying via §setspn -S§/§-D§. Never write an app playbook that auto-edits AD whenever login fails: reassigning an SPN can break other services or open service-impersonation vulnerabilities.

**The SPN and keytab must be issued from the same service account** by design. Registering §HTTP/portal.example.org§ on the wrong computer account or another app account lets the browser obtain a ticket that Portal Java cannot decrypt.

## 9. Keytab, KVNO, Enctype, and Runtime Permissions

A keytab is a **binary secret** holding keys for one or more principals, not a TLS certificate or §krb5.conf§ file. Keep it outside JARs/Git/container images, for example:

~~~text
/etc/kerberos/krb5.conf
/etc/kerberos/jaas.conf
/run/secrets/kerberos/http-portal.keytab
~~~

§krb5.conf§ defines realms/KDCs; §jaas.conf§ defines the login module/principal and keytab path; §*.keytab§ holds the keys. To check **metadata** without printing key bytes:

~~~bash
# Run inside a TEST container/VM with granted permissions.
id

# Check file mode, owner, group; symlink mounts dereferenced:
stat -L -c '%a %U %G %n' \
  /run/secrets/kerberos/http-portal.keytab

# Verify read permission for the JVM's actual UID/GID:
test -r /run/secrets/kerberos/http-portal.keytab \
  && printf 'KEYTAB_READABLE=YES\n' \
  || printf 'KEYTAB_READABLE=NO\n'

# View only KVNO, principal, enctype metadata:
klist -k -e /run/secrets/kerberos/http-portal.keytab
~~~

§klist -k -e§ (MIT Kerberos) typically shows principal, KVNO, and encryption types **without printing raw key material**. However, principal lists/topology remain sensitive and should not be pasted into broad-access tickets/logs. Never use §cat§, §xxd§, Base64-encoding the whole file, options that dump key bytes, or printing §Subject.getPrivateCredentials()§.

Check:

| Symptom | Possibility |
| --- | --- |
| Cannot read keytab | UID/GID/mode/mount/symlink mismatch |
| Keytab holds §HTTP/node.internal§ | Wrong principal/SPN for public host |
| Keytab has only old KVNO | Service account password/key rotated, pod not updated |
| Keytab enctype only RC4/DES or unsupported AES | KDC/JDK/AD encryption policy mismatch |
| One Pod has new keytab, another has old | Intermittent 401 depending on load-balancer backend |
| Keytab owned by root mode §0400§, Pod UID 10001 | App cannot read; needs proper group/owner |
| Keytab only configured as base64 env string | Not a binary file path JAAS can read |
| Relative/classpath keytab path | May point to the wrong file inside container/working dir |
| Duplicate SPN on AD service accounts | KDC ambiguity; ticket may not match expected key |

**Never use §chmod 777§** to fix permissions. Kubernetes Secret volumes can mount root-owned; consider §fsGroup§ + read-only §0440§ if supported by the CSI/volume driver. Verify inside the Pod using the **exact runtime UID**. Host root or privileged Pods can still read the keytab despite restricted file modes, so enforce RBAC, admission controls, node isolation, and encryption at rest.

### 9.1. Key Rotation and KVNO

When a service account password/key rotates, **KVNO may increment**. The KDC may start encrypting service tickets with the new key. Pods holding the old keytab fail to decrypt and return SPNEGO 401. Proper procedure:

1. Identity team confirms the service account owning the SPN, current KVNO/enctypes, and the new keytab.
2. Provision the new keytab via secret manager/secure mount.
3. Verify §klist -k -e§ metadata, path/mode, and auth integration tests in staging.
4. Check whether the library/JGSS caches credentials; swapping a mounted file does not guarantee the Java §Subject§/GSS loaded the new key.
5. Rolling restart or refresh per verified capability, monitoring 401/error rates per Pod.
6. Confirm old/new key overlap behavior from AD/KDC policy; **never assume overlap always exists** after a password rotation.
7. Retire old keys per procedure, handle as an incident if exposed, and do not assume deleting a file automatically revokes the old key.

### 9.2. Multiple Alias SPNs, Nodes, and Load Balancers

If public URLs include both §portal.example.org§ and §portal-alt.example.org§, decide whether to register **two SPNs** and how to provision keys based on browser canonicalization and IdP/AD policy. A VIP/load balancer fronting multiple nodes normally uses **one logical HTTP service identity**; every acceptor must have keys for that exact logical SPN and current KVNO. Never create SPNs per Pod name.

Never set §servicePrincipal="*"§ or accept any keytab principal just to "silence errors" in production when the service should accept one specific SPN; wildcard acceptors expand credential/trust scope whenever a keytab holds multiple entries.

## 10. JAAS and krb5.conf on the Java Acceptor Side

**Example §/etc/kerberos/krb5.conf§:**

~~~ini
[libdefaults]
    default_realm = EXAMPLE.ORG
    dns_lookup_realm = false
    dns_lookup_kdc = false

[realms]
    EXAMPLE.ORG = {
        kdc = kdc1.example.org:88
        kdc = kdc2.example.org:88
    }

[domain_realm]
    .example.org = EXAMPLE.ORG
    example.org = EXAMPLE.ORG
~~~

If your organization uses DNS SRV discovery for KDC/AD, §dns_lookup_kdc§ policy may differ. Never force this config onto every domain. §EXAMPLE.ORG§ must match the approved Kerberos/KDC realm, never derived from an HTTP `Host` header.

**Example §/etc/kerberos/jaas.conf§ for acceptor-only:**

~~~text
com.sun.security.jgss.krb5.accept {
    com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    keyTab="/run/secrets/kerberos/http-portal.keytab"
    principal="HTTP/portal.example.org@EXAMPLE.ORG"
    storeKey=true
    isInitiator=false
    useTicketCache=false
    doNotPrompt=true
    debug=false;
};
~~~

| Option | Effect |
| --- | --- |
| §useKeyTab=true§ | Load service credentials from keytab |
| §keyTab§ | Absolute path to **binary secret**, readable by app UID |
| §principal§ | Full service principal, must match KDC SPN/keytab |
| §storeKey=true§ | Retain credentials in private §Subject§ for GSS accept |
| §isInitiator=false§ | Server **accepts** service tickets; no user TGT needed to accept |
| §useTicketCache=false§ | Do not default to reading a user's TGT cache |
| §doNotPrompt=true§ | Fail if keytab is missing rather than prompting interactively for a password |
| §debug=false§ | Avoid printing Kerberos internals in production |

**Library differences:** §SunJaasKerberosTicketValidator§ can construct its own login config/JAAS Subject from §setServicePrincipal(...)§ and §setKeyTabLocation(...)§, so do not assume it always reads §com.sun.security.jgss.krb5.accept§ from an external JAAS file. Determine whether your app uses an **application-managed `LoginContext`** or **validator-managed login**; check actual version source/API before configuring both.

**Illustrative Java flags:**

~~~bash
java \
  -Djava.security.krb5.conf=/etc/kerberos/krb5.conf \
  -Djava.security.auth.login.config=/etc/kerberos/jaas.conf \
  -Djavax.security.auth.useSubjectCredsOnly=true \
  -jar portal.jar
~~~

- §java.security.krb5.conf§: **JDK** realm/KDC file, not the JAAS config.
- §java.security.auth.login.config§: login module entry file.
- §javax.security.auth.useSubjectCredsOnly§: controls JGSS credential lookup inside the JAAS Subject; §false§ lets JGSS search environment/default ticket caches. Never set §false§ blindly to mask server keytab bugs.
- MIT variables §KRB5_CONFIG§, §KRB5_KTNAME§, §KRB5CCNAME§ work for §klist§/§kinit§/§kvno§, yet **must not be assumed** to be the sole source the JDK reads. Set Java properties/JAAS explicitly to avoid cases where the shell succeeds while the JVM fails.
- §isInitiator=false§ is for the acceptor. If the Java app also calls Kerberos backends with its own service principal, configure a separate **initiator** and separate credentials. Never use a user TGT or the acceptor keytab to casually "delegate users".

## 11. Distinguishing GSS Failure, NTLM Fallback, and Channel Binding

**Negotiate does not guarantee Kerberos.** When browser/Windows fails to get a Kerberos ticket, it can fall back to NTLM depending on policies. A Java JGSS Kerberos acceptor can reject an NTLM token inside §Authorization: Negotiate§. When hitting a 401 loop, verify:
- Does the browser have a service ticket for §HTTP/portal.example.org§?
- Did the KDC issue a ticket or report §S_PRINCIPAL_UNKNOWN§?
- Do security events/SSPI show Kerberos or NTLM was used?
- Is the policy blocking NTLM/downgrade enforced properly?

**Never enable NTLM domain-wide as a workaround**, and never switch authentication mode from Kerberos to Basic just to "stop 401s" without risk approval.

### 11.1. Extended Protection / Channel Binding

Some Windows clients/servers enforce Extended Protection for Authentication (EPA) or TLS channel binding. If TLS terminates at an LB/WAF while Kerberos accept happens in the JVM, channel binding data can mismatch. §GSSException: Channel binding mismatch§ differs from a pure keytab §KRB_AP_ERR_MODIFIED§ error, even though both surface as 401.

Investigate:
1. Where does TLS terminate? Browser→LB, and does LB→Spring use mTLS/TLS?
2. Is the SPN used by the client based on the right public hostname?
3. Do server/IdP/OS policies require Channel Binding Tokens (CBT) or EPA?
4. Do your Spring Kerberos/JDK versions support the required channel binding mechanism?
5. Is a proxy altering hostname/routes or offloading TLS?
6. Can you adjust termination architecture, configure supported channel binding, or accept Kerberos at a trusted proxy with backend mTLS?

**Never recommend turning off EPA or editing the Windows registry to drop channel binding** as a default trick. It is an anti-relay protection; changes require Identity/Security review.

## 12. Common Error Codes: Do Not "Fix" the Wrong Layer

| Symptom / Error Code | What to Suspect | Verification & Action |
| --- | --- | --- |
| Missing §WWW-Authenticate: Negotiate§ | Entry point/filter chain/proxy | Check Spring Security routing, edge 302/401 |
| Challenge present, browser sends no token | Browser policy, TGT, proxy, KDC | Allowlist, `klist`, user identity, VPN/DNS |
| §407 Proxy-Authenticate§ | Explicit proxy demands auth | Check PAC/WPAD; do not change Portal keytab |
| §KDC_ERR_S_PRINCIPAL_UNKNOWN§ | Target SPN absent in KDC or wrong realm | §setspn -Q§/§kvno§/DNS |
| §KDC_ERR_PRINCIPAL_NOT_UNIQUE§ | Duplicate SPN in AD | AD admin audits registry; avoid auto-editing |
| §KRB_AP_ERR_MODIFIED§ | Wrong key/account/KVNO/SPN, sometimes other env errors | KDC events, keytab metadata, SPN owner and version |
| §KRB_AP_ERR_SKEW§ or "Clock skew too great" | Client/KDC/server clocks drifted | Sync NTP; never disable timestamp checks |
| §KDC_ERR_ETYPE_NOTSUPP§ | Encryption algorithms do not intersect | AD account enctype/JDK/KDC policy; prefer AES |
| §GSSException: No valid credentials provided§ | Missing/wrong Subject/JAAS/keytab | `LoginContext`/validator config, file permissions |
| §Cannot locate KDC§ | `krb5.conf`/realm/DNS/network | Java properties, DC lookup, port 88, VPN |
| §Server not found in Kerberos database§ | Unregistered FQDN/SPN | Exact SPN, alias/CNAME, realm |
| §No key to decrypt ticket§ | Acceptor keytab/SPN/KVNO/enctype mismatch | Approved keytab/rotation, right JVM path |
| §Channel binding mismatch§ | TLS EPA/CBT with LB/proxy | Test TLS topology; never blindly disable EPA |
| Token carries NTLM instead of Kerberos | Browser fallback due to KDC/SPN policy | Check actual auth mechanism; block downgrade |
| 401 after app restart on only 1 Pod | Secret version/file owner drift or cache | Compare pod version, UID/GID, rolling restart |
| GSS succeeds then 403 | `UserDetailsService`/roles/tenant/resource deny | Application authorization; do not touch keytab |
| §WWW-Authenticate§ lost at ingress | Gateway strips/rewrites challenge | Two-sided network trace, proxy config |
| Authorization header lost between proxy/app | Ingress strips header | Presence-only tracing, fix header forwarding |
| Login loop 302→IdP/form | Filter-chain priority, SSO fallback | Check URL chain + `AuthEntryPoint` |
| Client `klist` OK yet Java fails | Different JAAS/`krb5.conf`/cache/UID | Check process flags, runtime path, Subject |

**Never lump every 401 into "a Kerberos issue".** 401 is an HTTP status; inspect negotiation headers and server-side GSS errors to find the cause.

## 13. Controlled Observability in JVM/Spring

Only in an isolated test/staging environment can you enable:

~~~bash
java \
  -Djava.security.krb5.conf=/etc/kerberos/krb5.conf \
  -Dsun.security.krb5.debug=true \
  -Dsun.security.jgss.debug=true \
  -jar portal.jar
~~~

**Risk:** JDK/JGSS debug output can contain principals, realms, KDC hosts, ticket metadata, IPs, session hints, and sensitive values. Enable only for a short investigation window with restricted RBAC logs and short retention, then turn off. Never leave §debug=true§ on long-term in §Krb5LoginModule§/§SunJaasKerberosTicketValidator§ in production. Never paste raw logs to chat without redaction.

### 13.1. What Should Be Collected

- Exact timestamp (with timezone), correlation ID, node/pod ID.
- URL host, 401/403/407/302 responses, boolean presence of Negotiate challenge/response.
- Requested SPN from client traces **verified and cleared for disclosure**, expected SPN from approved service config.
- Java config paths (not secret file contents), runtime UID/GID, and readable boolean.
- Keytab principal alias, permitted KVNO/enctype categories, rotation version.
- GSS/JAAS **error code/category** and provider authentication outcome.
- **Pseudonymized** `SecurityContext` principal/authority to separate authentication from authorization.
- IdP/KDC event ID without storing raw service tickets.
- Receipt/forwarding of Authorization header recorded purely as **exists=true/false**, never the value.

### 13.2. What Must Never Be Collected

Never collect:
- §Authorization: Negotiate <raw-token>§;
- §Proxy-Authorization§, session cookies, unredacted browser HARs;
- keytab bytes, §kinit§ passwords, TGT caches, credentials inside §Subject.getPrivateCredentials()§;
- real user principals/emails when unnecessary, production screenshots exposing internal info;
- secrets/KDC admin credentials in READMEs or CI pipelines;
- domain-wide KDC logs beyond incident scope.

### 13.3. End-to-End Correlation from 401 to GSS

~~~text
Browser event:
   URL portal.example.org/private
   Response 401, hasNegotiateChallenge=true
   Request hasNegotiateAuthorization=true

Ingress event:
   request-id=qa-171
   hasNegotiateAuthorization=true

Spring event:
   request-id=qa-171
   SpnegoFilter invoked=true
   KerberosServiceAuthProvider invoked=true
   GSS_ACCEPT_RESULT=FAIL
   GSS_ERROR=KRB_AP_ERR_MODIFIED

Identity team event:
   requestedSPN=HTTP/portal.example.org
   AD owner=svc-portal-prod
   keyVersion=current-N

Runtime inventory:
   pod=portal-3
   keytabPrincipal=HTTP/portal.example.org
   keytabVersion=previous-N-1

=> Hypothesis: stale keytab KVNO on pod portal-3.
=> Fix: approved secret rollout, validate and retest.
~~~

This is a **sanitized simulated trace** with no real accounts or secrets. It illustrates requiring evidence across at least browser, ingress, JVM, and AD/KDC, without needing raw packet payloads.

## 14. Standalone Java 17: SPNEGO Triage Classifier

`SpnegoTriageDemo.java` below runs **without AD/KDC/keytab**. It accepts *verified observations* (booleans and SPN strings supplied by the tester) and suggests where to investigate. Do not use it as a Kerberos validator; it does not read real HTTP headers, verify signatures, extract SPNs from untrusted requests, or authenticate users.

**File `SpnegoTriageDemo.java`:**

~~~java
import java.util.Objects;

public class SpnegoTriageDemo {

    record Evidence(
        boolean hasNegotiateChallenge,
        boolean browserSentNegotiate,
        boolean headerReachedApp,
        boolean kdcIssuedServiceTicket,
        String ticketServicePrincipal,
        String acceptorPrincipal,
        boolean keytabKeyMatches,
        boolean gssAccepted) {}

    static String diagnose(Evidence e) {
        if (!e.hasNegotiateChallenge()) {
            return "CHECK_SERVER_CHALLENGE";
        }
        if (!e.browserSentNegotiate()) {
            return "CHECK_BROWSER_OR_KDC";
        }
        if (!e.headerReachedApp()) {
            return "CHECK_PROXY_HEADER_FORWARDING";
        }
        if (!e.kdcIssuedServiceTicket()) {
            return "CHECK_KDC_SPN_REGISTRATION";
        }
        if (!Objects.equals(
                e.ticketServicePrincipal(), e.acceptorPrincipal())) {
            return "CHECK_ACCEPTOR_SPN_MISMATCH";
        }
        if (!e.keytabKeyMatches()) {
            return "CHECK_KEYTAB_KVNO_ENCTYPE";
        }
        if (!e.gssAccepted()) {
            return "CHECK_GSS_MECHANISM_OR_POLICY";
        }
        return "SPNEGO_ACCEPTED_CHECK_AUTHORIZATION";
    }

    static void show(String label, Evidence e) {
        System.out.println(label + "=" + diagnose(e));
    }

    public static void main(String[] args) {
        String spn = "HTTP/portal.example.org@EXAMPLE.ORG";
        String wrong = "HTTP/node7.internal@EXAMPLE.ORG";

        show("missingChallenge", new Evidence(
            false, false, false, false, null, spn, false, false));
        show("browserNoToken", new Evidence(
            true, false, false, false, null, spn, false, false));
        show("proxyStripped", new Evidence(
            true, true, false, true, spn, spn, true, false));
        show("kdcNoSpn", new Evidence(
            true, true, true, false, spn, spn, false, false));
        show("wrongSpn", new Evidence(
            true, true, true, true, spn, wrong, true, false));
        show("staleKeytab", new Evidence(
            true, true, true, true, spn, spn, false, false));
        show("gssReject", new Evidence(
            true, true, true, true, spn, spn, true, false));
        show("accepted", new Evidence(
            true, true, true, true, spn, spn, true, true));
    }
}
~~~

**Run with JDK 17 or higher:**

~~~bash
javac SpnegoTriageDemo.java
java SpnegoTriageDemo
~~~

**Exact stdout:**

~~~text
missingChallenge=CHECK_SERVER_CHALLENGE
browserNoToken=CHECK_BROWSER_OR_KDC
proxyStripped=CHECK_PROXY_HEADER_FORWARDING
kdcNoSpn=CHECK_KDC_SPN_REGISTRATION
wrongSpn=CHECK_ACCEPTOR_SPN_MISMATCH
staleKeytab=CHECK_KEYTAB_KVNO_ENCTYPE
gssReject=CHECK_GSS_MECHANISM_OR_POLICY
accepted=SPNEGO_ACCEPTED_CHECK_AUTHORIZATION
~~~

Explanation: When there is no challenge, **do not check the keytab first**; when the browser sends no token, check client/KDC; when the proxy strips the header, the bug is in transit; when the KDC issues no ticket, check SPN/realm; when the ticket SPN differs from the keytab, fix service identity; when key material mismatches, inspect KVNO/enctype; GSS rejection despite matching SPN/key can be NTLM/CBT/time/replay/policy; once GSS accepts, proceed to check authorization.

**Safety limit:** The §Evidence§ record contains data **already gathered by a trusted tester**. In reality §browserSentNegotiate=true§ does not prove the KDC issued a Kerberos ticket (it could be NTLM). This is a *decision support demo*, never a "bypass" of SPNEGO by trusting booleans from HTTP.

## 15. Java 17 Integration Probe: Testing JAAS Acceptor with a Real Keytab

This example **compiles with JDK 17** yet only runs PASS once you have a **sandbox JAAS config + real keytab**; it checks only whether JAAS can load the acceptor principal, and **does not prove** browser handshake or service-ticket decryption.

**File `KerberosAcceptorProbe.java`:**

~~~java
import javax.security.auth.Subject;
import javax.security.auth.login.LoginContext;
import javax.security.auth.kerberos.KerberosPrincipal;

public class KerberosAcceptorProbe {
    public static void main(String[] args) throws Exception {
        LoginContext context =
            new LoginContext("com.sun.security.jgss.krb5.accept");
        context.login();
        try {
            Subject subject = context.getSubject();
            boolean match = subject
                .getPrincipals(KerberosPrincipal.class).stream()
                .anyMatch(p -> p.getName().equals(
                    "HTTP/portal.example.org@EXAMPLE.ORG"));

            if (!match) {
                throw new IllegalStateException(
                    "Approved service principal not found in JAAS Subject");
            }
            System.out.println("JAAS_ACCEPTOR_LOGIN=PASS");
            System.out.println("EXPECTED_PRINCIPAL=PASS");
            System.out.println("SECRETS_PRINTED=false");
        } finally {
            context.logout();
        }
    }
}
~~~

**Run in a sandbox provisioned with §jaas.conf§/keytab:**

~~~bash
javac KerberosAcceptorProbe.java
java \
  -Djava.security.krb5.conf=/etc/kerberos/krb5.conf \
  -Djava.security.auth.login.config=/etc/kerberos/jaas.conf \
  KerberosAcceptorProbe
~~~

**Stdout on login success:**

~~~text
JAAS_ACCEPTOR_LOGIN=PASS
EXPECTED_PRINCIPAL=PASS
SECRETS_PRINTED=false
~~~

If the file is missing or permissions/principal are wrong, §LoginContext.login()§ may throw §LoginException§. Never catch it and print a fake PASS; never print §Subject.getPrivateCredentials()§. A passing JAAS login proves only that service acceptor credentials loaded; it does not prove the client holds a valid Kerberos ticket, TLS CBT policy holds, or §SpnegoAuthenticationProcessingFilter§ is wired right.

### 15.1. Comparing Outputs of the Two Probes

| Condition | SpnegoTriageDemo | KerberosAcceptorProbe | What Else Must Be Tested? |
| --- | --- | --- | --- |
| No challenge | Suggests fixing entry point | May pass | Server `SecurityFilterChain` |
| Browser no token | Suggests client/KDC | May pass | Browser policy/TGT/network |
| Wrong SPN | Suggests mismatch | Probe usually fails if principal is wrong | Actual ticket SPN, keytab entries |
| Wrong KVNO | Suggests keytab mismatch | JAAS may still pass | GSS accept real ticket, KDC current key |
| NTLM/CBT issue | Suggests GSS/policy | May pass | Actual token mechanism/TLS binding |
| GSS accepted yet HTTP 403 | Suggests authorization | May pass | Roles/tenant/business permission |

## 16. Reverse Proxy, Kubernetes, DNS, and Multiple Backend Nodes

**Reverse proxy in front of Portal:**
- Public §https://portal.example.org§ does not mean the backend sees §https://portal.example.org§ instead of §http://portal-pod-7.internal:8080§. The SPN is the **public logical service name**, not the Pod hostname.
- When ingress terminates TLS, check client and acceptor channel binding/EPA expectations; never assume Kerberos works regardless of TLS topology.
- §WWW-Authenticate§ must reach the browser; §Authorization§ must reach the right acceptor if Spring authenticates.
- If ingress acts as Kerberos acceptor instead of Spring, backend identity trust must use mTLS/authorized identity propagation, never trusting a browser-sent §X-User§.
- Load balancers must not randomly route to a node with an old keytab, different realm config, or different role policy. Monitor error rates **per node**.

**Kubernetes keytab secret mount:**

~~~yaml
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001
  containers:
    - name: portal
      image: registry.example.org/portal:1.0
      volumeMounts:
        - name: kerberos-keytab
          mountPath: /run/secrets/kerberos
          readOnly: true
      env:
        - name: JAVA_TOOL_OPTIONS
          value: >-
            -Djava.security.krb5.conf=/etc/kerberos/krb5.conf
  volumes:
    - name: kerberos-keytab
      secret:
        secretName: portal-kerberos-keytab
        defaultMode: 0440
~~~

This is a **Pod spec snippet**, not a full §Deployment§; §krb5.conf§ and validator config must also be provided from a trusted source. App UID/GID, §fsGroup§, and volume drivers govern whether the mount is readable; CSI/projected volumes can have differing semantics. Base64 Kubernetes Secrets are encoding, not encryption; protect etcd, RBAC, and node isolation. Never store keytab bytes in YAML/Helm/Git.

**Multi-Pod signal:** If 4/5 Pods return 200 while one Pod returns 401 GSS, prioritize comparing **keytab version/KVNO/UID, JVM flags, clock, TLS certs, Pod DNS, and runtime image** before altering org-wide AD SPNs.

## 17. Negative/Positive Test Matrix

| ID | Test Condition | Expected |
| --- | --- | --- |
| T01 | Fresh browser GET `/private` with no session | 401 Negotiate challenge on right route |
| T02 | GET `/public` unauthenticated | Must not emit SPNEGO challenge |
| T03 | Server responds only 302 `/login` | Catches form entry point/matcher priority |
| T04 | 401 without Negotiate | Filter/entry point problem, do not blame keytab |
| T05 | Browser has no TGT | No Kerberos ticket; appropriate 401/flow |
| T06 | Browser does not allowlist host | Does not auto-send Negotiate token |
| T07 | Browser accesses IP instead of FQDN | SPN acquisition may fail/mismatch |
| T08 | Browser uses CNAME/alias | Measure actual SPN; keytab/SPN owner match |
| T09 | Proxy returns 407 | Distinguish proxy auth from Portal auth |
| T10 | Proxy strips Authorization | Server sees no token, fails closed |
| T11 | Ingress strips WWW-Authenticate | Browser receives no challenge, fails closed |
| T12 | Client falls back to NTLM | Java Kerberos-only must not treat as authenticated |
| T13 | KDC lacks HTTP SPN | `KDC_ERR_S_PRINCIPAL_UNKNOWN`, ticket not issued |
| T14 | Duplicate SPN in AD | KDC error/AD audit, no auto-edit |
| T15 | Keytab principal ≠ ticket SPN | GSS rejects, no principal created |
| T16 | Stale KVNO in keytab | Reject until approved rotation |
| T17 | Keytab unreadable by JVM UID | Startup/auth fails, never `chmod 777` |
| T18 | Wrong keytab enctype | GSS/KDC fails per policy; never enable weak DES/RC4 |
| T19 | Large clock skew | Kerberos rejects, sync NTP |
| T20 | KDC unavailable/VPN down | Browser gets no ticket or controlled failure |
| T21 | Wrong JAAS entry/`krb5.conf` path | Login/probe fails; identifies JVM property |
| T22 | Valid ticket yet §UserDetailsService§ rejects account | Authentication denied, no bypass |
| T23 | Principal authenticated yet lacks role | Proper 403 |
| T24 | TLS channel binding/EPA mismatch | Reject; investigate TLS topology, never disable EPA |
| T25 | Pod 1 new keytab, Pod 2 old | Node-specific drift detected |
| T26 | App SSO falls back to Basic | Test detects mechanism is not Kerberos |
| T27 | Logs with JGSS debug contain sensitive data | QA fail; redact/retention |
| T28 | Spoofed user/header from browser | Creates no trusted principal |
| T29 | Real Kerberos token for right SPN + right keytab | GSS accepts; app auth/roles enforced separately |
| T30 | Browser resends/replays token | Replay/time checks per GSS/KDC, no bypass |
| T31 | Acceptor has JAAS credentials yet browser fails to Negotiate | Passing probe does not mark E2E pass |
| T32 | Java mocks bool true while real token is invalid | Integration validator must reject |
| T33 | App has both OIDC and SPNEGO chains on same URL | Route matchers/priority explicitly defined |
| T34 | Client request traverses LB TLS offload | Verify EPA/CBT and public logical hostname SPN |

### 17.1. Avoiding Wrong-Layer Tests

- Mutating ticket bytes → GSS rejects integrity; **does not** prove the SPN validator works independently.
- Turning off browser Integrated Auth → client sends no token; **does not** prove a broken keytab.
- §setspn -Q§ returning a match → proves only that the SPN exists in the directory; **does not** prove keytab KVNO or Java filter config is right.
- §klist§ showing a ticket → client holds a credential; **does not** prove the server accepts it.
- Java §LoginContext§ passing → server can read the keytab; **does not** prove browser/endpoint negotiation.
- HTTP 200 after Basic login → app may be authenticated, yet **not** via SPNEGO Kerberos.
- HTTP 403 after GSS accept → likely app permission denial; Kerberos already succeeded.
- Testing on one Pod → **does not** prove the whole cluster is consistent.

## 18. Runbook for Repeated 401/403 Incidents

### Phase A – Isolate in the First 5 Minutes (Without Editing Credentials)

1. Identify the exact public URL and protected path, browser/OS version, network/VPN/proxy, timestamp, and 401/407/302/403.
2. Use a clean session and inspect §WWW-Authenticate§: is the Negotiate scheme present?
3. Observe **only presence** of §Authorization: Negotiate§ at browser, ingress, and JVM; never copy raw tokens.
4. Identify Kerberos vs. NTLM, whether the browser has a TGT, and which SPN was requested.
5. Capture the server-side GSS error category and node ID if the token reached the app.
6. **Pick one branch** of the decision tree before making any changes.

### Phase B – Verify the Hypothesis

**If browser sends no token:** check Integrated Auth allowlist, domain TGT, `klist`, DNS/KDC, VPN, proxy, and SPN queries. Do not touch the server keytab without evidence.

**If KDC issues no service ticket:** identity team checks §setspn -Q§, uniqueness/owner, realm, FQDN/CNAME, and permissions; modify AD only via change control.

**If acceptor fails to decrypt:** check actual ticket SPN, keytab KVNO/enctype metadata, account owner, runtime permissions, Pod drift, rotation, and channel binding.

**If Spring returns 403:** verify the authenticated principal, user enabled state, role mapping, and tenant/resource authorization; never grant extra roles indiscriminately or disable CSRF.

### Phase C – Fix and Verify

1. Apply **one change** in sandbox or canary: browser allowlist, SPN registration (AD team), keytab secret, app filter wiring, or reverse proxy.
2. Re-run baseline 401 Negotiate, client token presence, GSS success, and protected HTTP response.
3. Verify negative wrong-SPN/wrong-token tests still reject without weak fallbacks.
4. Monitor 401/403/407 and KDC errors by node, browser group, and version during the rollout window.
5. Retire stale keytabs/ticket caches per policy, turn off JGSS debug, and redact temporary logs.
6. Write the incident note: root cause, scope, fix, tests, credential impact, and follow-up owner.

**Never fix 401 by:** trusting all TLS, disabling EPA, enabling uncontrolled Basic auth, hardcoding passwords, accepting any service principal, running §chmod 777§ on keytabs, dumping raw tickets/logs, disabling Spring Security, trusting user headers, or adding §permitAll§ to protected resources.

## 19. Pre-Production Checklist

- [ ] Unauthenticated protected endpoints properly return §401 WWW-Authenticate: Negotiate§, not hijacked by Form/Basic chains.
- [ ] Browser enterprise policies allowlist only approved hosts; whether NTLM fallback is permitted is explicitly decided.
- [ ] DNS/FQDN/aliases, KDC realm, and §HTTP/FQDN§ match the public service name.
- [ ] AD SPN is unique and belongs to the right service account; no duplicates.
- [ ] Keytab principal, KVNO, and enctype match approved KDC keys; secret version is uniform across all Pods.
- [ ] JVM runs with the right §krb5.conf§/JAAS/validator config, absolute keytab path, and runtime UID/GID permissions.
- [ ] Spring filter chain has version-compatible §SpnegoEntryPoint§, filter, authentication provider, and user mapping.
- [ ] Ingress forwards Negotiate headers to the right component; reverse proxy never injects untrusted identity headers.
- [ ] TLS termination/EPA/channel binding aligns with policy; protections are never turned off to "pass login".
- [ ] Kerberos/JGSS debug is off in production; logs record sanitized metadata only.
- [ ] Authenticated Kerberos principals still pass through application authorization; disabled users/tenants/resources are tested separately.
- [ ] Negative tests cover wrong SPN, wrong keytab, client no token, NTLM, rotation, time skew, and cluster drift.
- [ ] Owners are assigned for AD SPN, keytab/secret rotation, Spring security config, ingress, browser policy, and incident response.
- [ ] No raw tickets, keytabs, TGT caches, or cookie/session secrets exist in Git, images, logs, tickets, or chat.

## 20. Hands-On Exercises

**Exercise 1 – Missing challenge.** Portal returns 302 to §/login§ instead of 401 Negotiate. Analyze §SecurityFilterChain§ matchers/§AuthenticationEntryPoint§ and write a MockMvc/WebTest verifying the exact challenge from §/private§.

**Exercise 2 – Silent browser.** Server sends 401 Negotiate yet no §Authorization§ arrives at ingress. Order checks across browser policy, OS ticket cache, domain/VPN/KDC, and proxy status, and explain why there is not yet evidence to edit the keytab.

**Exercise 3 – Nonexistent SPN.** Client runs §kvno HTTP/portal.example.org@EXAMPLE.ORG§ in sandbox and KDC returns §KDC_ERR_S_PRINCIPAL_UNKNOWN§. What should the AD team query? Explain the difference between querying §HTTP/portal.example.org§ and a JAAS principal with a realm suffix.

**Exercise 4 – Stale KVNO.** AD rotated the svc account; Pod A has the new keytab while Pod B has the old keytab. Design log metadata, canary/rollout, and consistency tests without reading key bytes.

**Exercise 5 – CNAME/LB.** Browser visits §https://alias.example.org§, client requests ticket §HTTP/backend.example.org§, and the JVM keytab only has §HTTP/portal.example.org§. Diagram the trust flow and how to identify the actual SPN via client/KDC metadata.

**Exercise 6 – Java 17.** Run §SpnegoTriageDemo.java§, verify all 8 lines of stdout, and modify evidence to get §CHECK_PROXY_HEADER_FORWARDING§ and §CHECK_ACCEPTOR_SPN_MISMATCH§. Explain why booleans cannot replace real ticket validation.

**Exercise 7 – JAAS integration.** In a sandbox with a test keytab, run §KerberosAcceptorProbe.java§. Distinguish a passing JAAS login from an end-to-end passing GSS accept/HTTP Negotiate flow.

**Exercise 8 – Kerberos or NTLM?** Browser sends §Authorization: Negotiate§ yet the Java Kerberos-only acceptor rejects it. Explain how to identify the actual authentication mechanism without decoding/printing raw tokens, and why enabling NTLM is not a safe default.

**Exercise 9 – Channel binding.** TLS terminates at ingress while the backend uses Java GSS. Prove why a channel binding mismatch must not be "solved" by blindly disabling EPA, and propose testing the TLS topology with security review.

**Exercise 10 – HTTP 403.** User authenticates via Kerberos yet lacks permission to view reports. Trace the layers, explain why this is the right outcome, and propose user-mapping/authorization regression tests.

**Exercise 11 – Log redaction.** Design a trace event containing only request ID, Negotiate header presence, target SPN alias, GSS category, node, and outcome. List fields that must never be printed.

**Exercise 12 – Error grouping.** Classify §KDC_ERR_S_PRINCIPAL_UNKNOWN§, §KRB_AP_ERR_MODIFIED§, §No valid credentials§, §407§, and §403§ into client/KDC/acceptor/proxy/app per the diagram in section 4.

**Success criterion:** For a 401 loop, the learner can answer **"Was a Negotiate challenge sent, did the client send a token, for which SPN did the KDC issue a ticket, did the ticket reach the JVM, did the acceptor keytab/KVNO match, did GSS accept, and did Spring authorization permit?"** and design an independent check for each question without weakening trust.

## 21. Official References

- Oracle JDK 17 – Part VI: HTTP/SPNEGO Authentication, 401 Negotiate, 407 Proxy, JAAS/useSubjectCredsOnly: https://docs.oracle.com/en/java/javase/17/security/part-vi-httpspnego-authentication.html
- Oracle JDK 17 – Krb5LoginModule JAAS options, acceptor, keyTab, isInitiator: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.security.auth/com/sun/security/auth/module/Krb5LoginModule.html
- Oracle JDK 17 – JAAS Reference Guide: https://docs.oracle.com/en/java/javase/17/security/java-authentication-authorization-service-jaas-reference-guide.html
- Spring Security Kerberos – SpnegoEntryPoint, ProcessingFilter, ServiceAuthenticationProvider, SunJaasKerberosTicketValidator: https://docs.spring.io/spring-security-kerberos/reference/ssk.html
- Spring Security – Kerberos extension integration: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html
- Microsoft Learn – Kerberos SPN registered on wrong account, KRB_AP_ERR_MODIFIED: https://learn.microsoft.com/en-us/troubleshoot/windows-server/windows-security/kerberos-event-4-access-denied
- Microsoft Learn – Troubleshooting Kerberos authentication failures: https://learn.microsoft.com/en-us/troubleshoot/windows-server/windows-security/kerberos-authentication-troubleshooting-guidance
- MIT Kerberos – krb5.conf realm/KDC/domain_realm: https://web.mit.edu/Kerberos/www/krb5-current/doc/admin/conf_files/krb5_conf.html
- MIT Kerberos – klist command: https://web.mit.edu/Kerberos/www/krb5-latest/doc/user/user_commands/klist.html
- MIT Kerberos – kvno command: https://web.mit.edu/Kerberos/www/krb5-latest/doc/user/user_commands/kvno.html
- Microsoft Learn – Setspn command for AD SPN queries: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/setspn
- OWASP – Secrets Management Cheat Sheet (keytab/TGT): https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
