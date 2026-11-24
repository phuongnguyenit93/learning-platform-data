# 18.6. Kerberos, KDC, Service Principal, Ticket, Keytab, and Relationship to Krb5LoginModule

## 1. Objectives and Context

After this lesson, you should be able to explain:

- How Kerberos V5 proves **who is requesting which service** using tickets and symmetric keys, rather than sending the user's password to every service.
- How KDC, realm, client principal, service principal, TGT, service ticket, session key, and keytab each have distinct responsibilities.
- The AS → TGS → application service flow, including the step proving the client possesses the session key.
- When a Java application uses a ticket cache, when a service needs a keytab, and how JAAS Krb5LoginModule populates a Subject.
- Why a successful JAAS login does not automatically mean HTTP/SASL/GSS-API authentication with the target service has succeeded.

The scope is **Kerberos in Java**, focusing on the relationship between Kerberos infrastructure and Krb5LoginModule. Sample hostnames, realms, and file paths below are illustrative only; they do not represent a live KDC.

## 2. The big picture: identity, realm, and KDC

A **Principal** is an identity name in a Kerberos system. Typical forms:

~~~text
alice@EXAMPLE.COM                         # user (client principal)
HTTP/api.example.com@EXAMPLE.COM          # HTTP service (service principal)
host/server.example.com@EXAMPLE.COM       # host service
krbtgt/EXAMPLE.COM@EXAMPLE.COM            # realm ticket-granting service
~~~

- **Realm**: administrative domain for Kerberos identities and keys; conventionally uppercase, e.g., EXAMPLE.COM. A realm is not automatically synonymous with a DNS domain, though many deployments intentionally match them.
- **Client principal**: identity wishing to use a service, e.g., alice@EXAMPLE.COM.
- **Service principal**: server identity the client asks to authenticate to, typically of the form service/hostname@REALM. HTTP Negotiate commonly uses HTTP/hostname@REALM.
- **KDC (Key Distribution Center)**: trusted ticket-issuing service comprising the Authentication Service (AS) and Ticket-Granting Service (TGS). The KDC knows principals and their keys; in Active Directory, domain controllers usually serve as the KDC.
- **Application server/acceptor**: service receiving the ticket sent by the client and validating it with the service principal's own key.

Not every step contacts the KDC. Once a client holds a valid TGT and service ticket, it can reuse tickets; the server does not need to contact the KDC for each routine authentication request.

## 3. Kerberos V5 flow from login to calling a service

Suppose Alice wants to call HTTP/api.example.com@EXAMPLE.COM:

~~~text
Alice / Java client                    KDC (AS + TGS)              HTTP service
       |                                      |                          |
       |--- AS-REQ (request TGT) ------------>|                          |
       |<-- AS-REP (TGT + session key) -------|                          |
       |                                      |                          |
       |--- TGS-REQ (TGT, ask HTTP ticket) -->|                          |
       |<-- TGS-REP (service ticket + key) ---|                          |
       |                                      |                          |
       |--- AP-REQ (service ticket + authenticator) -------------------->|
       |<-- AP-REP (if mutual authentication requested) -----------------|
       |<================= protected application protocol ==============>|
~~~

**Step 1 — AS exchange:** the client proves its identity to the AS, typically via pre-authentication involving the principal's key or another KDC-supported method. The KDC returns a **TGT** (Ticket-Granting Ticket) along with session key material for the client. The TGT contains a portion encrypted for the TGS, so the client cannot tamper with it.

**Step 2 — TGS exchange:** the client presents the TGT to request a **service ticket** specifically for HTTP/api.example.com@EXAMPLE.COM. The TGS issues a service ticket containing a portion encrypted with the service principal's long-term key and delivers the corresponding session key securely to the client.

**Step 3 — AP exchange:** the client sends the service ticket **together with a fresh authenticator** to the HTTP server. The server uses the service principal's own key (typically from a keytab) to decrypt the server portion of the ticket, then uses the session key to verify the authenticator, timestamps, and other checks. A ticket alone does not prove the sender possesses the session key.

**Step 4 — mutual authentication (optional):** the service can reply with AP-REP so the client verifies the server. Once authentication is established, the application protocol determines how message integrity/confidentiality is protected: GSS-API offers wrap/unwrap, while HTTP may rely on TLS. Kerberos does not automatically encrypt every byte of an HTTP payload.

**Note:** the message names above describe the protocol. Applications using GSS-API/SASL normally do not construct AS-REQ, TGS-REQ, or AP-REQ manually.

## 4. Distinguishing TGT, service ticket, session key, and keytab

| Component | Primary usage | Meaning | What not to confuse it with |
| --- | --- | --- | --- |
| TGT | Client ↔ TGS | Allows requesting tickets for other services within policy lifetimes | Not a ticket presented directly to ordinary HTTP services |
| Service ticket | Client → specific service | Proof issued by the KDC for a specific service principal | Not a password and cannot be reused arbitrarily for other services |
| Session key | Client and ticket verifier | Proves possession of the ticket, authenticates messages, and can protect the session | Not the long-term key stored in a keytab |
| Keytab | Usually on server, sometimes non-interactive client | File holding long-term keys and principal/KVNO/enctype metadata for Kerberos | Does not contain TGTs or a list of service tickets |
| Ticket cache | Client/process environment | Stores credentials such as TGTs and service tickets for reuse | Not a keytab; clearing the cache does not rotate service keys |

A **ticket** has a lifetime and attributes such as client, service, validity window, and KDC policy flags. For a service ticket, the server-bound portion is encrypted so **the service** can verify it. The client receives the matching session key, not the service's long-term key.

**KVNO (Key Version Number)** identifies the right key version when a principal's key is rotated; **enctype** specifies the encryption algorithm/key type. When the KDC issues a ticket using one key version while the server only holds an older keytab or lacks a compatible enctype, authentication fails. Never conclude "the principal is in the keytab so it must work" while ignoring KVNO and enctype.

## 5. Service principal, hostname, and keytab mapping

For the sample service, all three parties must agree on the identity:

~~~text
Name client requests:  HTTP/api.example.com@EXAMPLE.COM
Principal KDC knows:   HTTP/api.example.com@EXAMPLE.COM
Key server holds:      keytab containing keys for HTTP/api.example.com@EXAMPLE.COM
~~~

If the client requests HTTP/alias.example.com while the KDC lacks that SPN, a service ticket may not be issued. If the KDC has the principal but the server reads a keytab for a different principal or key version, the server cannot decrypt the ticket. DNS aliases, reverse DNS, hostname canonicalization, load balancers, and Active Directory SPN mappings must all be designed consistently.

A service principal can be registered on a service account in the KDC/AD. It is a **Kerberos identifier**; a service principal name is not itself a username/password, a full URL, or a TLS certificate.

**Multiple instances:** instances genuinely serving the same SPN may need access to the same appropriate key set, but copying keytabs must be managed as secret distribution. Never share one principal across unrelated services just for configuration convenience.

## 6. How does a keytab work?

A keytab stores secret keys for one or more principals, usually with KVNO and enctype. The server does not embed a password in Java source code; upon receiving AP-REQ, GSS/Kerberos uses the key from the keytab to accept the ticket.

Example administrative workflow in an environment with MIT Kerberos or equivalent tools:

~~~bash
# Run on a host configured for Kerberos; filenames are illustrative.
klist -k -e /etc/security/keytabs/http-api.keytab

# Check current tickets for the client account:
klist

# A client with rights and a valid TGT can request a service ticket:
kvno HTTP/api.example.com@EXAMPLE.COM
~~~

- `klist -k -e` displays identities, KVNOs, and enctypes inside the keytab; it does **not** verify that the live KDC currently holds the same key.
- `kvno` requires a real Kerberos environment, working realm/KDC resolution, and ticket permissions.
- Exact tools and flags depend on MIT Kerberos, Heimdal, Windows, or the KDC administration system.

In deployment, only the OS account running the service should be able to read the keytab; apply minimal permissions (e.g., 0600 on Unix where appropriate), distribute via secret management, and never commit it to Git, logs, or chat. When rotating keys, coordinate KDC, KVNO, and all instances; plan key overlap while older tickets remain valid if supported by the KDC/keytab. If a keytab leaks, an attacker can impersonate the service for the scope of the exposed keys.

## 7. Where does Krb5LoginModule sit in Java architecture?

In Java, three layers of responsibility must stay distinct:

1. **JAAS LoginContext** invokes configured LoginModules by entry name; javax.security.auth.login.LoginContext drives login/commit/logout.
2. **com.sun.security.auth.module.Krb5LoginModule** interacts with Kerberos (ticket cache, keytab, KDC, or callbacks depending on config) and populates principals/credentials into javax.security.auth.Subject.
3. **GSS-API (org.ietf.jgss) or SASL** uses the appropriate credentials to establish an authenticated session with the actual service. For example, HTTP Negotiate/SPNEGO uses GSS at the HTTP layer; SASL GSSAPI is used in protocols supporting SASL.

Krb5LoginModule **is not a KDC, does not issue tickets, and does not implement HTTP Negotiate itself**. It is the bridge between Kerberos mechanisms and Java's JAAS framework.

When login/commit succeeds, the Subject may contain:

- **KerberosPrincipal** in the principals set.
- **KerberosTicket** in private credentials when logging in as an initiator with a TGT.
- **KeyTab or KerberosKey** in private credentials when storeKey and an appropriate key source are configured.
- Other credentials depending on login configuration and provider.

Remember that private credentials are sensitive data. Never dump Subject contents casually, and never serialize credentials into logs or API responses.

## 8. What do client (initiator) and server (acceptor) need?

| Role | Common source | isInitiator | Goal |
| --- | --- | --- | --- |
| User/client after kinit | Ticket cache holding TGT | true (default) | Hold credentials to request service tickets and initiate a GSS context |
| Non-interactive daemon client | Dedicated keytab and daemon principal | true | Use the key to obtain a TGT from the KDC, then call services |
| Server accepting Kerberos only | Service principal keytab, storeKey=true | false | Load keys for the GSS acceptor; no need to fetch a TGT merely to accept AP-REQ |

**A TGT does not replace a keytab** on a server. An HTTP acceptor generally needs the service key to unwrap service tickets; running kinit on the server does not fix a missing keytab or wrong SPN.

## 9. Key Krb5LoginModule options

| Option | Meaning and conditions |
| --- | --- |
| principal | Identity to use; acceptors should specify an exact SPN. Wildcard * is valid only with isInitiator=false and accepts across keys in the keytab, requiring careful review |
| isInitiator | true to acquire outbound initiation credentials; false for acceptor-only, skipping the AS exchange for a TGT |
| useTicketCache | true to try reading a TGT from the ticket cache (suits kinit-authenticated clients) |
| ticketCache | Optional cache path; used only when useTicketCache=true |
| useKeyTab | true to use keys from a keytab; specifying keyTab without useKeyTab=true is invalid configuration |
| keyTab | Path to keytab; specify explicitly and lock down file permissions |
| storeKey | true to store the keytab/keys in Subject private credentials, essential for acceptors |
| doNotPrompt | true to suppress interactive password prompts; fails cleanly if credentials cannot be obtained |
| renewTGT | Policy to attempt TGT renewal; valid only with useTicketCache=true, and does not replace ticket-expiry management |
| refreshKrb5Config | Reloads Kerberos configuration upon login (per operational requirements) |
| debug | LoginModule diagnostic output; enable only under control and turn off afterward |

Common configuration pitfalls: **doNotPrompt=true** with no valid cache/keytab/credential source; **storeKey=true** with only a ticket cache and no key source; **keyTab** specified without **useKeyTab=true**; **renewTGT=true** without **useTicketCache=true**. The module may attempt cache, then keytab, then other sources depending on flags; never allow interactive password prompts in production daemons.

## 10. Sample Kerberos and JAAS configurations

Sample krb5.conf: KDC host and realm must be replaced with values supplied by your administrator.

~~~ini
[libdefaults]
    default_realm = EXAMPLE.COM
    dns_lookup_kdc = false

[realms]
    EXAMPLE.COM = {
        kdc = kdc.example.com
    }
~~~

Sample jaas.conf with **two separate entries**, chosen according to process role:

~~~text
KrbClient {
    com.sun.security.auth.module.Krb5LoginModule required
    useTicketCache=true
    doNotPrompt=true
    isInitiator=true
    debug=false;
};

KrbAcceptor {
    com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    keyTab="/etc/security/keytabs/http-api.keytab"
    principal="HTTP/api.example.com@EXAMPLE.COM"
    storeKey=true
    doNotPrompt=true
    isInitiator=false
    debug=false;
};
~~~

**KrbClient**: expects a valid TGT already present in a cache readable by the JVM. Login fails if no suitable credential exists; the sample deliberately avoids password prompting.

**KrbAcceptor**: loads keys for HTTP/api.example.com so the application can accept GSS tokens addressed to that principal. It does not create an HTTP endpoint or parse Authorization headers; a framework/handler supporting Negotiate or a GSS-integrated protocol is still required.

Depending on the runtime, the ticket cache location used by OS tools and the path read by Java can differ. On Windows/AD, credential acquisition may follow OS and JDK mechanisms; verify empirically rather than assuming KRB5CCNAME behaves identically across all Unix systems.

**Never put passwords in jaas.conf**, never store keytabs in the source tree, and never run services under a domain administrator account.

## 11. Java 17+ example: inspecting a service principal without a KDC

Standalone file **PrincipalDemo.java**:

~~~java
import javax.security.auth.kerberos.KerberosPrincipal;

public class PrincipalDemo {
    public static void main(String[] args) {
        KerberosPrincipal principal = new KerberosPrincipal(
                "HTTP/api.example.com@EXAMPLE.COM",
                KerberosPrincipal.KRB_NT_SRV_HST);

        System.out.println(principal.getName());
        System.out.println(principal.getRealm());
    }
}
~~~

Compile and run:

~~~bash
javac PrincipalDemo.java
java PrincipalDemo
~~~

Stdout:

~~~text
HTTP/api.example.com@EXAMPLE.COM
EXAMPLE.COM
~~~

The constructor above only represents **an identity name and name type**; it does not authenticate with a KDC, open a keytab, or obtain a ticket. Constructing `KerberosPrincipal` successfully **does not prove** the SPN is registered in the KDC.

## 12. Java 17+ example: logging in with JAAS and inspecting Subject

File **JaasLoginDemo.java** (requires real krb5.conf, jaas.conf, and ticket cache to log in successfully):

~~~java
import javax.security.auth.Subject;
import javax.security.auth.login.LoginContext;
import java.security.PrivilegedAction;

public class JaasLoginDemo {
    public static void main(String[] args) throws Exception {
        LoginContext context = new LoginContext("KrbClient");
        context.login();

        try {
            Subject subject = context.getSubject();

            subject.getPrincipals().forEach(principal ->
                    System.out.println("Principal: " + principal.getName()));

            Subject.doAs(subject, (PrivilegedAction<Void>) () -> {
                System.out.println("Run using authenticated Subject");
                return null;
            });
        } finally {
            context.logout();
        }
    }
}
~~~

Compile:

~~~bash
javac JaasLoginDemo.java
~~~

Reference run command (on a machine configured for Kerberos):

~~~bash
java -Djava.security.auth.login.config=jaas.conf -Djava.security.krb5.conf=krb5.conf JaasLoginDemo
~~~

If LoginContext.login() fails, it throws LoginException (covered by throws Exception in the example); common causes are missing TGTs, unreadable caches, realm mismatches, or misconfiguration. **There is no single fixed stdout for this example**: the principal depends on environment credentials, and without a valid KDC/cache execution will not reach the print statements.

Subject.doAs executes the block under the Subject's identity; GSS integration APIs can then look up the associated credentials. This sample merely prints the principal name for illustration and **does not yet communicate or authenticate with an HTTP service**. On newer Java versions, check JDK compatibility guidance for Subject APIs and how a Subject is bound to the execution context.

## 13. From Subject to GSS-API, HTTP Negotiate, and SASL GSSAPI

To actually use a service ticket, the application needs a token-exchange mechanism with the server:

~~~text
LoginContext("KrbClient") → Subject with credentials
        ↓
GSSManager / GSSContext (initiator)
        ↓ creates GSS token for service "HTTP@api.example.com"
HTTP client sends Authorization: Negotiate <base64-token>
        ↓
HTTP server / GSSContext (acceptor) uses service keytab
        ↓
Server authenticates principal; framework maps to application user/permissions
~~~

A host-based name like **HTTP@api.example.com** in GSS-API is a different representation from Kerberos service principal **HTTP/api.example.com@EXAMPLE.COM**. The GSS/Kerberos provider resolves the mapping using realm and config rules; avoid ad-hoc string concatenation, especially when aliases exist.

A GSS security context may require **multiple token rounds** between client and server; never assume every mechanism uses exactly one AP-REQ/token (especially with SPNEGO). After context establishment, GSS provides message-protection APIs, while whether the application uses them or relies solely on TLS is a protocol/deployment choice.

With **SASL GSSAPI**, protocols like LDAP or messaging integrate authentication into SASL negotiation. The library or protocol driver drives token exchange while Krb5LoginModule prepares credentials. Never infer from a successful JAAS setup that the LDAP/HTTP server has granted operation rights: **authentication** and **authorization** are two separate stages.

## 14. Step-by-step deployment and verification workflow

1. **Define principals and realm**: exact client principal, service principal, hostname/SPN requested by client, realm, and network path to the KDC.
2. **Prepare the KDC**: accounts/principals must exist; provision keys or keytabs through administrative workflows obeying enctype and KVNO policy.
3. **Prepare the service host**: place the keytab in a restricted path with minimal permissions; verify it holds the right SPN and current keys.
4. **Prepare the client host**: acquire a TGT via organization-approved means (e.g., kinit) and verify with klist; never copy the server's keytab onto the client.
5. **Load config into the JVM**: realm, KDC, role-appropriate JAAS login entry; make sure the ticket cache matches the OS user running the JVM.
6. **Log in with JAAS**: verify principals on Subject without logging private credentials.
7. **Run the GSS/SASL/HTTP exchange**: client fetches a service ticket and sends the token; server uses its service key to accept the token.
8. **Authorize access**: from the authenticated principal, map to application roles/ACLs per policy.
9. **Test renewal/rotation**: expired tickets require credential re-acquisition; keytabs and KVNOs must stay coordinated during key rotation.

Reference diagnostic commands, run only in an authorized Kerberos environment:

~~~bash
kinit alice@EXAMPLE.COM
klist
kvno HTTP/api.example.com@EXAMPLE.COM
klist -k -e /etc/security/keytabs/http-api.keytab
~~~

Before debugging Java code, pinpoint where it failed: **AS failed to issue a TGT**, **TGS failed to issue a service ticket**, or **the acceptor failed to decrypt/verify AP-REQ**. Those three failures require three distinct fixes.

## 15. Common errors and how to reason about them

| Symptom | Possible cause | Check first |
| --- | --- | --- |
| Cannot locate KDC / realm | Misconfigured krb5.conf or DNS/KDC routing | Realm, host, port, network reachability |
| Client has no valid credentials | Empty/expired cache or JVM reading wrong cache | klist under the exact user running the app; useTicketCache |
| Server not found in Kerberos database | SPN/realm requested by client is unknown to KDC | Exact service principal, aliases, realm, SPN registration |
| KRB_AP_ERR_MODIFIED or integrity error on accept | Server lacks the right service key, KVNO/enctype mismatch, SPN points to wrong instance | Ticket service principal, keytab, KVNO/enctype, hostname |
| Clock skew too great / ticket expired | Clock drift or expired ticket | NTP sync, KDC/client/server clocks, ticket lifetime |
| Cannot find key of appropriate type | Missing key or incompatible enctype | Keytab enctypes and KDC/JDK crypto policy |
| JAAS LoginException doNotPrompt | No credential source for chosen login mode | useTicketCache/useKeyTab settings, principal, file permissions |
| JAAS login OK yet HTTP 401 / SASL fail | GSS negotiation, SPN, server key, proxy, or authorization issue | Token exchange, service principal, acceptor, user mapping |

Error messages are clues to narrow down the layer, not proof of a single root cause. For instance, KRB_AP_ERR_MODIFIED can happen with an outdated keytab **or** when the client obtained a ticket for another instance's SPN.

To enable JVM diagnostics only when genuinely needed:

~~~bash
java -Dsun.security.krb5.debug=true -Djava.security.auth.login.config=jaas.conf -Djava.security.krb5.conf=krb5.conf JaasLoginDemo
~~~

You may enable debug=true on Krb5LoginModule in test environments. **Never leave Kerberos debugging enabled continuously in production**; protect logs because they can expose principal names, hostnames, configuration, and sensitive operational details.

## 16. Dangerous misconceptions

- **"TGT and service ticket are the same."** False. A TGT requests tickets from the TGS; a service ticket targets one specific service.
- **"Having a keytab guarantees Kerberos login will succeed."** False. Principal, KVNO, enctype, realm, file permissions, and LoginModule flags must all align. Client initiators need a credential-acquisition step, potentially involving the KDC.
- **"Krb5LoginModule automatically authenticates every HTTP request."** False. GSS/SPNEGO/HTTP integration with token exchange and server verification is still required.
- **"If a service has a TGT, it does not need a keytab."** False for an acceptor model relying on service keys to decrypt KDC-issued tickets.
- **"Kerberos success means the user has all permissions."** False. Kerberos proves identity; resources and permissions are decided by the application or authorization system.
- **"With Kerberos, TLS is unnecessary."** False. HTTPS/TLS and Kerberos address different security concerns; evaluate transport protection, channel binding, and the protocol's threat model.
- **"Ticket caches and keytabs both store passwords."** False. Caches hold session tickets/credentials; keytabs hold long-term keys, and both must be protected.

## 17. Self-check scenarios

**Scenario A:** the client holds a valid TGT, yet calling the API returns "Server not found in Kerberos database". Inspect the service principal requested by the client and the SPN/realm record in the KDC first; swapping the server's keytab will not fix a TGS failure to issue the ticket.

**Scenario B:** the client obtains a service ticket successfully, and the server returns KRB_AP_ERR_MODIFIED after a key rotation. Check KVNO/enctype and whether all instances received the updated keytab, and confirm the client sent a ticket for the right SPN.

**Scenario C:** a Java service only needs to accept HTTP Negotiate tokens. Its JAAS entry should be acceptor-only (isInitiator=false), useKeyTab=true, storeKey=true, with the exact principal; do not require kinit/TGT merely to receive tickets.

**Scenario D:** LoginContext.login() succeeds, yet the endpoint still returns 403. Separate two questions: was the GSS token authenticated and mapped to a principal? Does that principal have permission to call the endpoint under authorization policy?

You have mastered this lesson when you can sketch **AS → TGS → AP** from memory, point out which key is used at each step, explain which credentials live in **Subject** for initiators vs. acceptors, and diagnose why a client with a valid TGT might still fail to call a service.

## 18. Technical references

- Kerberos V5, RFC 4120: https://www.rfc-editor.org/rfc/rfc4120
- Java SE 21 Krb5LoginModule API (options, constraints, and examples): https://docs.oracle.com/en/java/javase/21/docs/api/jdk.security.auth/com/sun/security/auth/module/Krb5LoginModule.html
- Oracle Java SE 17 JAAS Login and Java GSS-API: https://docs.oracle.com/en/java/javase/17/security/use-jaas-login-utility-and-java-gss-api-secure-message-exchanges.html

The links above describe the standards and JDK behavior; example values like EXAMPLE.COM must be replaced with a valid Kerberos environment for live interoperability testing.