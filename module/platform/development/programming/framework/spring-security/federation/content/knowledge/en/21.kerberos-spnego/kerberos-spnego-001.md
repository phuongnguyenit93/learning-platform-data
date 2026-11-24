# Kerberos in Intranet Login and Its Relationship with SSO

## 1. The Problem and Expected Outcomes

An employee has signed in to a corporate domain-joined machine, opens **https://intranet.example.org**, and is recognized by the application without having to re-enter a password. This is a **Single Sign-On (SSO)** experience. A common mechanism used to achieve this is **Kerberos V5** in an **Active Directory Domain Services (AD DS)** or **MIT Kerberos** infrastructure, combined with **HTTP Negotiate/SPNEGO** in the browser and web application.

**Key takeaway:** the user's machine holds a **Ticket-Granting Ticket (TGT)** in the operating system's secure credential store. When it needs to access a web service, the client obtains a **service ticket** for the exact **Service Principal Name (SPN)**, for example **HTTP/intranet.example.org@EXAMPLE.ORG**. The browser sends a GSS/SPNEGO token, the server verifies it using the service's secret key (usually loaded from a **keytab**), and Spring Security creates an Authentication only after verification succeeds.

The browser does not send the user's domain password to each intranet app to achieve SSO. However, **Kerberos identity authentication does not automatically grant business permissions**, nor does it create a shared HttpSession across all apps.

### Learning Objectives

- State the roles of **KDC, AS, TGS, realm, principal, SPN, TGT, service ticket, keytab, and credential cache**.
- Correctly interpret **AS-REQ/AS-REP, TGS-REQ/TGS-REP, and AP-REQ/AP-REP**.
- Trace the **HTTP 401 WWW-Authenticate: Negotiate → Authorization: Negotiate** flow.
- Distinguish **Kerberos** from **SPNEGO negotiation** and NTLM fallback cases.
- Understand why DNS aliases, duplicate SPNs, wrong keytab/kvno, clock skew, and browser policies cause silent SSO to fail.
- Configure **Spring Security Kerberos 2.x** with **Spring Boot 3.3.5 / Security 6.x / Java 17** and persist sessions properly.
- Distinguish internal Kerberos from **SAML2, CAS, OIDC**, and other SSO models.
- Perform positive/negative testing and handle errors without disabling HTTPS or ticket validation.

The domain EXAMPLE.ORG and user alice are lesson sample data only. A real Kerberos login requires a managed KDC/AD, SPN, keytab, and client machine.

## 2. Terminology: Do Not Confuse a KDC Ticket with a Browser Session

| Concept | Definition | Example |
| --- | --- | --- |
| **Realm** | A Kerberos administrative domain with a KDC and principal namespace, usually written in uppercase. | EXAMPLE.ORG |
| **KDC** | Key Distribution Center, providing **Authentication Service (AS)** and **Ticket-Granting Service (TGS)** functions. | AD domain controller or MIT KDC |
| **User principal** | The Kerberos identity of a user. | alice@EXAMPLE.ORG |
| **Service principal** | The identity of a service that receives tickets. | HTTP/intranet.example.org@EXAMPLE.ORG |
| **SPN** | Service Principal Name requested by a client for a service, especially important in AD. | HTTP/intranet.example.org |
| **TGT** | A ticket allowing the client to request further service tickets from the TGS, not a login ticket for every web app. | krbtgt/EXAMPLE.ORG@EXAMPLE.ORG |
| **Service ticket** | A ticket encrypted/protected for a specific service principal. | HTTP/intranet.example.org |
| **Session key** | A session key used in Kerberos exchanges between client and service. | Secret value, never logged |
| **Keytab** | A file containing long-term keys of a server/service principal, potentially with kvno and enctype. | /etc/security/keytabs/http.keytab |
| **Credential cache** | Client-side storage for credentials/TGT/service tickets. | Windows LSA, MIT ccache |
| **GSS-API** | An abstract API for establishing an authenticated security context. | org.ietf.jgss in JDK 17 |
| **SPNEGO** | A negotiation mechanism for selecting a GSS mechanism, which may be Kerberos. | HTTP Negotiate |
| **Local HTTP session** | Spring application state after authentication when deployed statefully. | JSESSIONID or SESSION |

**A TGT is not a Spring session cookie.** A browser does not send the TGT directly to an intranet application; it uses the Kerberos/GSS-API stack to obtain a token appropriate for the service. Likewise, **a keytab is not an X.509 public certificate**: a keytab contains the service's long-term secret key and must be protected like a credential.

### Three Types of Identities That Often Differ

~~~text
Kerberos principal:       alice@EXAMPLE.ORG
Kerberos service SPN:     HTTP/intranet.example.org@EXAMPLE.ORG
Local application user:   employee-0041
Email:                    alice@example.org
~~~

Only after Kerberos has successfully verified the principal and a policy links that identity to a local account does the app know the corresponding internal user. **Do not automatically strip the realm or use email as a global key** if multiple realms/tenants can issue the same name.

## 3. Kerberos V5 Flow: From Workstation Login to App

~~~text
(1) Workstation/user logon
     Client ------------------ AS-REQ -------------------> KDC / AS
     Client <----------------- AS-REP -------------------- KDC / AS
          TGT is cached on the client

(2) User opens https://intranet.example.org
     Client -- TGS-REQ + TGT for HTTP/intranet --> KDC / TGS
     Client <-- TGS-REP + service ticket ------- KDC / TGS

(3) Browser calls intranet application
     Browser ---- HTTP Negotiate (AP-REQ) -------------> Web service
     Browser <--- optional GSS final token (AP-REP) --- Web service

(4) Server has accepted the GSS context
     Verified Kerberos identity -> local UserDetails -> Spring Authentication
     -> SecurityContext/session -> check authorization by resource/tenant
~~~

### 3.1. Authentication Service: Issuing the TGT

During domain/Kerberos login, the client sends an **AS-REQ** and receives an **AS-REP** after satisfying pre-auth/credential policy requirements. The client obtains a TGT to present when requesting service tickets.

- The user does not have to re-enter a password at each web service.
- The TGT has lifetime/renewable flags governed by KDC policy and does not live forever.
- The operating system or MIT Kerberos manages the cache; never place a TGT in a browser cookie or URL query.
- If the user does not have a TGT yet, the OS/browser may not complete silent authentication or may require login via the device's mechanism.
- A client in another realm requires managed **cross-realm trust/referral**; do not trust arbitrary realms by default.

### 3.2. Ticket-Granting Service: Issuing a Ticket per SPN

The client uses **TGS-REQ + TGT** to request a ticket for **HTTP/intranet.example.org@EXAMPLE.ORG**. The TGS uses the **service's long-term key** to protect the portion of the ticket received by the target server. The client also receives the appropriate session key material.

- **A ticket for HTTP/intranet.example.org cannot automatically be used for HTTP/payroll.example.org**.
- If the client already has a valid service ticket in its cache, it may not need to ask the KDC again for every HTTP request.
- If the SPN does not exist, the client/KDC cannot map the service account properly and ticket acquisition can fail.
- Cross-realm relies on separate trust paths; realm configuration, DNS, and krb5.conf/AD referrals all affect it.
- A TGT can be used to request multiple service tickets, creating an SSO experience across multiple applications, **yet each application still validates its own ticket**.

### 3.3. Application Exchange: AP-REQ/AP-REP

The client sends a GSS token, usually containing a Kerberos **AP-REQ**, to the service. The server uses its keytab/service key to:

1. Verify that the ticket is intended for the correct service principal.
2. Process the authenticated session key and authenticator.
3. Check validity time, clock skew, replay cache, and policy.
4. Establish the GSS context; if mutual authentication is required, it may return an AP-REP.
5. Return the verified principal so the application layer can map it to a local user.

**Never trust a user identity taken solely from a principal string in an HTTP header**. The Kerberos credential must be successfully validated by the GSS acceptor/server validator; a KerberosPrincipal constructor or a JSON payload containing the name alice does not prove the sender is alice.

## 4. HTTP Negotiate / SPNEGO: How Browsers "Use Kerberos"

**RFC 4559** defines the **Negotiate** HTTP authentication scheme, which typically uses GSS-API/SPNEGO. On an intranet:

~~~http
GET /private HTTP/1.1
Host: intranet.example.org
~~~

The server does not yet have a valid Authentication:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

A browser permitted by policy obtains a token from the GSS/Kerberos stack:

~~~http
GET /private HTTP/1.1
Host: intranet.example.org
Authorization: Negotiate BASE64_GSS_TOKEN
~~~

The server verifies the context and may return:

~~~http
HTTP/1.1 200 OK
WWW-Authenticate: Negotiate OPTIONAL_FINAL_TOKEN
Content-Type: text/plain

Welcome to intranet
~~~

**The tokens above are illustrative placeholders only**, not real credentials. Some GSS negotiations require multiple rounds of **401 and continuation tokens**; RFC 4559 allows a 2xx response to carry a final GSS token to complete mutual authentication on the client. Do not assume that HTTP 200 alone proves mutual authentication succeeded under every policy.

### Why Do Internal Machines Not Show a Login Page?

A typical scenario:

- The user has performed a domain logon and holds a TGT in the OS credential cache.
- The browser recognizes intranet.example.org as a site allowed to use integrated authentication.
- The browser requests the exact service ticket for the URL's hostname.
- The browser sends HTTP Authorization: Negotiate.
- The server has the keytab for HTTP/intranet.example.org, verifies the ticket, and creates an Authentication.
- The app grants the user access according to the local account/role policy.

**There is no password form on the website** because the browser/OS performs the ticket exchange, not because the website skipped authentication.

### Negotiate Does Not Guarantee Kerberos

SPNEGO is a **negotiation mechanism**. On Windows/HTTP, the selected mechanism can involve **Kerberos or NTLM** depending on the browser, policy, and environment. Simply seeing **Authorization: Negotiate** does not by itself prove that Kerberos was actually chosen. If the system requires **Kerberos-only**, check the actual GSS mechanism and configure rejection of unwanted fallbacks to prevent unapproved downgrades.

**A Kerberos token does not automatically encrypt the entire HTTP body/cookies.** RFC 4559 recommends appropriate channel protection; production must use HTTPS/TLS. Never post real Authorization tokens to an issue tracker or public logs.

## 5. Relationship to SSO and Other Federation Protocols

| Property | Kerberos + HTTP Negotiate | SAML2 Web Browser SSO | OIDC Authorization Code | CAS native |
| --- | --- | --- | --- | --- |
| Authentication center | KDC/realm, service keys, and tickets. | SAML IdP signs Response/Assertion. | OIDC Provider issues tokens. | CAS server issues ST for a service. |
| Browser flow | HTTP 401 + WWW-Authenticate: Negotiate. | Redirect to IdP, SAMLResponse back to ACS. | Redirect to auth endpoint, callback with authorization code. | CAS /login?service, callback with ST. |
| Data verified by app | GSS Kerberos service ticket/context. | XML signature/issuer/audience/time. | ID Token/issuer/audience/nonce and code/token exchange. | CAS ticket via /serviceValidate. |
| SSO experience | TGT allows requesting tickets for multiple SPNs. | IdP session lets multiple SPs avoid re-login. | OP session lets multiple clients avoid re-login. | CAS TGC/TGT session allows issuing new STs. |
| Devices outside intranet | Needs credential cache/KDC reachability/browser support or a bridge. | Usually more convenient for Internet SaaS. | Well-suited for web/mobile/API ecosystems. | Suited for CAS-integrated web applications. |
| Local app session | Optional, independent of TGT. | Optional. | Optional. | Optional. |

**One Windows login → multiple intranet apps** is SSO based on **TGT + service tickets**, **not all applications sharing a single JSESSIONID**. Each app can create its own session, with its own session timeout and logout policy.

### Kerberos as the Foundation for SAML2/OIDC SSO

There is a common enterprise pattern:

~~~text
Employee login domain workstation
    |
    +--> Intranet Spring app:
    |      Browser --Kerberos/SPNEGO--> Web app
    |
    +--> Enterprise IdP:
           Browser --Kerberos/SPNEGO--> IdP
           IdP --SAMLResponse or OIDC tokens--> SaaS SP/RP
~~~

A SaaS app does not receive a raw Kerberos service ticket when the actual integration is SAML2/OIDC. **The IdP uses Kerberos as its inbound authentication method**, and then federates outward using the appropriate protocol. Do not confuse **spring-security-saml2-service-provider** with **spring-security-kerberos**.

## 6. SPN, DNS, Keytab, kvno, and Time: Infrastructure Factors

### 6.1. SPN and the Key-Owning Account

~~~text
Browser URL:
  https://intranet.example.org

Service principal used in Kerberos:
  HTTP/intranet.example.org@EXAMPLE.ORG

SPN on the AD service account:
  HTTP/intranet.example.org

Service account (simulated):
  EXAMPLE\svc_intranet

Keytab located on the server:
  /etc/security/keytabs/http-intranet.keytab
~~~

**HTTP/** is the service class, while the hostname typically follows the website's FQDN. **An SPN is not a URL**: it does not contain https://, a /private path, or a query string.

With Active Directory, an authorized administrator can run:

~~~powershell
setspn -Q HTTP/intranet.example.org
setspn -L EXAMPLE\svc_intranet

# Command that modifies AD configuration: only run with change approval
setspn -S HTTP/intranet.example.org EXAMPLE\svc_intranet

# Check for duplicate SPNs
setspn -X
~~~

**setspn -S** checks for duplicates before adding; do not arbitrarily register the same SPN on two accounts. Duplicate SPNs or assigning an SPN to the wrong account can prevent the service from decrypting tickets issued by the KDC.

### 6.2. DNS Aliases, CNAMEs, Load Balancers, and Containers

If a browser accesses **https://portal.example.org** while the server keytab only supports **HTTP/intranet.example.org**, it can fail if the client requests an SPN based on portal.example.org. Similarly, a browser using an IP address or localhost will not automatically obtain a ticket for the FQDN's SPN.

- CNAME/hostname canonicalization depends on the Kerberos/GSS/browser stack; **do not assume every client resolves an alias to the canonical host identically**.
- If there are multiple instances behind an LB, the same logical service **HTTP/intranet.example.org** needs a consistent service identity model, the correct keytab on all acceptors, or an approved reverse proxy acting as the acceptor.
- Do not create two separate AD accounts with the same SPN to "load balance"; service accounts, keytabs, and kvnos must be managed accurately.
- If HTTPS termination occurs at ingress, determine **who actually verifies the SPNEGO token**. If a reverse proxy verifies Kerberos and passes identity to the backend, the backend must trust that identity assertion only over a protected channel, never an arbitrary client-supplied X-User header.
- Proxy host rewriting, forwarding, and DNS affect the SPN; inspect the path visible to the browser, not just internal cluster DNS.

### 6.3. Keytabs Contain Secrets and Are Versioned

A keytab can contain keys for specific **kvno (key version number)** and **enctype (encryption type)** values. If the AD service account's key has changed while the keytab has not been updated, the KDC issues tickets with the new key while the server only has the old key:

- The service may report **KRB_AP_ERR_MODIFIED**, an integrity failure, or a GSSException.
- Check the SPN owner, keytab principal/kvno/enctype, file permissions, and rotation timestamp.
- Coordinate key rotation between the KDC and all nodes, with overlap/rollback according to policy.
- Avoid enabling DES/RC4/weak crypto just to make an error disappear; prefer AES and approved policies.

A keytab **is not a public certificate**; do not put it in Git, logs, or artifacts, or send it over chat/email. Use secret management, least-privilege permissions, and auditing.

### 6.4. Clock Skew, Ticket Expiry, and Replay

Kerberos uses lifetimes and timestamps to limit replay attacks. Client, KDC, and server must stay synchronized via NTP/Windows Time. A common policy allows a small clock skew (often around 5 minutes), though **the actual value is determined by realm/service policy**.

- Expired/non-renewable TGT → the client may have to re-authenticate to obtain a new TGT.
- Expired service ticket → must acquire a new ticket if credentials allow.
- Authenticator replay or clock drift → the server must reject it.
- Do not relax expiry or disable replay protection indefinitely to mask NTP drift.
- The ticket cache avoids sending a TGS-REQ on every request, but does not allow tickets to be used forever.

## 7. Browser Integrated Authentication and Client Devices

### Microsoft Edge / Chromium

Microsoft Edge has the **AuthServerAllowlist** policy, which specifies hosts to which the browser may send integrated authentication. When unconfigured, Edge may only automatically use IWA for sites classified as intranet. For Internet websites not on the allowlist, the browser may not send a token even if Windows is domain-joined.

Allowlist only organization-approved hostnames such as **intranet.example.org**; do not open wildcards covering the Internet. Proxy/PAC, browser profiles, and the OS can affect intranet zone classification.

### Firefox, Linux, macOS

Firefox has settings such as **network.negotiate-auth.trusted-uris**. Linux/macOS may require **kinit** and a GSSAPI credential cache, or enterprise SSO integration. Do not assume every browser has access to a TGT on every machine.

### Off-Domain / Mobile / Internet

Personal devices without Kerberos credentials or without reachability to the KDC cannot perform silent login. Instead of forcing Kerberos on every client, the application should offer **federated OIDC/SAML2 via the enterprise IdP** or a controlled fallback, along with MFA/device policy when needed. **Do not accept NTLM/HTTP Basic automatically just because Kerberos does not work.**

The KDC does not necessarily need to be online for every request if the client already has a valid cached service ticket; however, network/KDC reachability is still required to request new tickets, renew tickets, or perform cross-realm referrals.

## 8. Spring Security Kerberos 2.x: Relevant Classes

**Spring Security Kerberos** is an extension, not a feature that appears merely by adding spring-boot-starter-security. For the **Spring Security 6.x** family, you can use **Spring Security Kerberos 2.x**, under the **org.springframework.security.kerberos** packages.

| Component | Role |
| --- | --- |
| **SpnegoEntryPoint** | Sends HTTP **401 WWW-Authenticate: Negotiate** when the user is not yet authenticated. |
| **SpnegoAuthenticationProcessingFilter** | Reads Authorization: Negotiate; creates a KerberosServiceRequestToken and invokes AuthenticationManager. |
| **KerberosServiceAuthenticationProvider** | Delegates to a validator to verify the service ticket/SPNEGO token, then loads UserDetails. |
| **SunJaasKerberosTicketValidator** | Uses JDK/JAAS to accept the ticket with the service principal and keytab. |
| **ProviderManager** | Dispatches the authentication token to the matching provider. |
| **UserDetailsService** | Maps the verified Kerberos principal to a local account and GrantedAuthorities. |
| **SecurityContextRepository** | Persists Authentication across subsequent requests if the app uses HttpSession. |
| **SessionAuthenticationStrategy** | Handles session fixation / session ID rotation after login. |

**KerberosAuthenticationProvider** supports a different authentication flow that can use a password/JAAS client and is not required for accepting a **SPNEGO service ticket** on a web server. This lesson uses **KerberosServiceAuthenticationProvider**.

### Pitfall with a Custom Filter in Spring Security 6.x

When instantiating **SpnegoAuthenticationProcessingFilter** with `new`, the filter **does not automatically save the SecurityContext for subsequent requests** unless a SecurityContextRepository is attached. If you want a stateful SP session, you must configure the repository **on both the filter and HttpSecurity**, along with a session fixation strategy and cookies. Otherwise, the ticket may pass on the first request while the user gets 401 on the next request.

In the **Spring Security Kerberos 7.x** generation, the coordinates/APIs belong to the Spring Security 7 family and differ from 2.x; do not copy 7.x dependencies and imports into Spring Boot 3.3.5.

## 9. Standalone Java 17: Identifying the Principal and Local Authorization

The **KerberosSsoPolicyDemo.java** example runs on JDK 17 without needing a KDC/AD/keytab. It illustrates **policy enforcement after the GSS context has been verified**. The **VerifiedContext** object in main is simulated; **it must never be constructed from a client-supplied header/JSON or the KerberosPrincipal constructor to bypass GSS validation in production**.

~~~java
import java.util.Set;
import javax.security.auth.kerberos.KerberosPrincipal;

public class KerberosSsoPolicyDemo {
    static final String SERVICE =
            "HTTP/intranet.example.org@EXAMPLE.ORG";
    static final Set<String> MEMBERS = Set.of("alice@EXAMPLE.ORG");
    static final Set<String> RESOURCES = Set.of("/intranet/report");

    record VerifiedContext(String client, String service,
                           String mechanism, boolean established) {}

    static String authorize(VerifiedContext c, String resource) {
        if (c == null || !c.established()) {
            return "DENY CONTEXT_NOT_ESTABLISHED";
        }
        if (!"KERBEROS".equals(c.mechanism())) {
            return "DENY MECHANISM_NOT_ALLOWED";
        }
        if (!SERVICE.equals(c.service())) {
            return "DENY WRONG_SERVICE";
        }
        if (!c.client().endsWith("@EXAMPLE.ORG")) {
            return "DENY REALM_NOT_ALLOWED";
        }
        if (!MEMBERS.contains(c.client())) {
            return "DENY NO_MEMBERSHIP";
        }
        if (!RESOURCES.contains(resource)) {
            return "DENY RESOURCE_NOT_ALLOWED";
        }
        return "ALLOW";
    }

    static void check(String label, VerifiedContext c, String resource) {
        System.out.println(label + ": " + authorize(c, resource));
    }

    public static void main(String[] args) {
        KerberosPrincipal principal =
                new KerberosPrincipal("alice@EXAMPLE.ORG");
        System.out.println("principal: " + principal.getName());

        VerifiedContext good = new VerifiedContext(
                principal.getName(), SERVICE, "KERBEROS", true);

        check("valid", good, "/intranet/report");
        check("wrong service", new VerifiedContext(
                principal.getName(), "HTTP/other.example.org@EXAMPLE.ORG",
                "KERBEROS", true), "/intranet/report");
        check("wrong mechanism", new VerifiedContext(
                principal.getName(), SERVICE, "NTLM", true), "/intranet/report");
        check("wrong realm", new VerifiedContext(
                "bob@OTHER.ORG", SERVICE, "KERBEROS", true), "/intranet/report");
        check("not provisioned", new VerifiedContext(
                "mallory@EXAMPLE.ORG", SERVICE, "KERBEROS", true),
                "/intranet/report");
        check("wrong resource", good, "/admin");
        check("not established", new VerifiedContext(
                principal.getName(), SERVICE, "KERBEROS", false),
                "/intranet/report");
        check("no context", null, "/intranet/report");
    }
}
~~~

Run:

~~~bash
javac KerberosSsoPolicyDemo.java
java KerberosSsoPolicyDemo
~~~

**Exact stdout:**

~~~text
principal: alice@EXAMPLE.ORG
valid: ALLOW
wrong service: DENY WRONG_SERVICE
wrong mechanism: DENY MECHANISM_NOT_ALLOWED
wrong realm: DENY REALM_NOT_ALLOWED
not provisioned: DENY NO_MEMBERSHIP
wrong resource: DENY RESOURCE_NOT_ALLOWED
not established: DENY CONTEXT_NOT_ESTABLISHED
no context: DENY CONTEXT_NOT_ESTABLISHED
~~~

**KerberosPrincipal** only represents a principal name and does not log in to a KDC. **VerifiedContext** is used to represent "GSS validation has occurred", not an object supplied by the browser. In a real application, the identity and mechanism must come strictly from a trusted Kerberos acceptor/provider before checking local account/tenant/resource access.

## 10. Spring Boot 3.3.5 + Spring Security Kerberos 2.1.0

This is a **Servlet intranet SPNEGO acceptor** sample on Java 17 that only completes end-to-end authentication when you have:

- A real EXAMPLE.ORG realm and user alice@EXAMPLE.ORG.
- The SPN HTTP/intranet.example.org bound to the proper service account.
- A server keytab with the right principal/kvno/enctype, readable by the process.
- DNS/LB/HTTPS for https://intranet.example.org.
- A domain/trusted intranet browser allowlist and a TGT in the client credential cache.
- Strong realm/service policies that disallow unapproved fallbacks.

### 10.1. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>kerberos-intranet-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.security.kerberos</groupId>
            <artifactId>spring-security-kerberos-core</artifactId>
            <version>2.1.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.security.kerberos</groupId>
            <artifactId>spring-security-kerberos-web</artifactId>
            <version>2.1.0</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Version warning:** Maven coordinates for Kerberos **2.1.0** differ from Kerberos 7.x. This is an example suited for the Spring Security 6.x family; transitive dependencies must be checked via dependency:tree, security advisories, and integration tests in enterprise environments.

### 10.2. application.yml

**src/main/resources/application.yml**

~~~yaml
server:
  port: 8080
  forward-headers-strategy: framework

app:
  kerberos:
    service-principal: "HTTP/intranet.example.org@EXAMPLE.ORG"
    keytab-location: "/etc/security/keytabs/http-intranet.keytab"
~~~

The keytab path is illustrative for Linux/containers and requires a real file with proper permissions at runtime. Never commit keytabs; never let the application take the keytab location or service principal from a user request. The public URL remains the HTTPS intranet hostname, not localhost:8080.

### 10.3. Main class

**src/main/java/com/example/krbdemo/KerberosApplication.java**

~~~java
package com.example.krbdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class KerberosApplication {
    public static void main(String[] args) {
        SpringApplication.run(KerberosApplication.class, args);
    }
}
~~~

### 10.4. SecurityConfig.java

**src/main/java/com/example/krbdemo/SecurityConfig.java**

~~~java
package com.example.krbdemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class SecurityConfig {
    @Bean
    UserDetailsService localUsers() {
        return username -> {
            // The demo only grants access to a single provisioned account.
            if (!"alice@EXAMPLE.ORG".equals(username)) {
                throw new UsernameNotFoundException("Unknown local account");
            }
            return User.withUsername(username)
                    .password("{noop}unused-by-kerberos")
                    .authorities("ROLE_EMPLOYEE")
                    .build();
        };
    }

    @Bean
    SunJaasKerberosTicketValidator ticketValidator(
            @Value("${app.kerberos.service-principal}") String principal,
            @Value("${app.kerberos.keytab-location}") String keytabPath) {
        SunJaasKerberosTicketValidator validator =
                new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(principal);
        validator.setKeyTabLocation(new FileSystemResource(keytabPath));
        return validator;
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosProvider(
            SunJaasKerberosTicketValidator validator,
            UserDetailsService localUsers) {
        KerberosServiceAuthenticationProvider provider =
                new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(localUsers);
        return provider;
    }

    @Bean
    SecurityFilterChain chain(
            HttpSecurity http,
            KerberosServiceAuthenticationProvider kerberosProvider)
            throws Exception {

        SecurityContextRepository repository =
                new DelegatingSecurityContextRepository(
                    new RequestAttributeSecurityContextRepository(),
                    new HttpSessionSecurityContextRepository());

        SpnegoAuthenticationProcessingFilter spnego =
                new SpnegoAuthenticationProcessingFilter();
        spnego.setAuthenticationManager(
                new ProviderManager(kerberosProvider));
        spnego.setSecurityContextRepository(repository);
        spnego.setSessionAuthenticationStrategy(
                new ChangeSessionIdAuthenticationStrategy());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new SpnegoEntryPoint()))
            .securityContext(sc -> sc
                .securityContextRepository(repository))
            .authenticationProvider(kerberosProvider)
            .addFilterBefore(spnego, BasicAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**What this example gets right:**

1. **SpnegoEntryPoint()** sends a 401 Negotiate challenge, not a CAS redirect or SAML2 redirect.
2. **SpnegoAuthenticationProcessingFilter** reads the GSS token and calls ProviderManager.
3. **KerberosServiceAuthenticationProvider** uses the ticket validator and local user details; it does not grant every user ROLE_ADMIN.
4. **SunJaasKerberosTicketValidator** uses a servicePrincipal + keytab configured outside HTTP input.
5. **The shared SecurityContextRepository** is wired into both the filter and HttpSecurity; a stateful SecurityContext can survive after the first request.
6. **ChangeSessionIdAuthenticationStrategy** provides session fixation protection.
7. The filter is created **inside SecurityFilterChain**, not as a standalone servlet Filter bean, avoiding double registration by Spring Boot outside the chain.
8. **anyRequest().authenticated()** is not sufficient to protect individual roles/tenants/resources; explicit authorization is still required.
9. Basic/formLogin fallback is not enabled by default, nor is CSRF disabled just for the demo.
10. The Spring app depends on **real KDC/keytab/browser integration**; code cannot fabricate an authenticated Kerberos principal from a username string.

**Note:** the password value in UserDetailsService is a local UserDetails placeholder, **not a domain password and not used to validate Kerberos**. In production, replace localUsers with managed DB/LDAP/IGA and check disabled/locked/revoked status.

### 10.5. Controller

**src/main/java/com/example/krbdemo/IntranetController.java**

~~~java
package com.example.krbdemo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IntranetController {
    @GetMapping("/")
    public String home() {
        return "Kerberos intranet SSO ready";
    }

    @GetMapping("/private")
    public String privatePage(Authentication authentication) {
        return "Authenticated: " + authentication.getName();
    }
}
~~~

Run in the pom.xml directory:

~~~bash
mvn spring-boot:run
~~~

**Conditional output:**

- **GET http://localhost:8080/** returns **Kerberos intranet SSO ready** if the app starts and the keytab config causes no initialization error.
- **GET /private** while unauthenticated returns **401 + WWW-Authenticate: Negotiate** if the request hits the proper SecurityFilterChain.
- An allowlisted browser can send **Authorization: Negotiate** after receiving 401.
- When KDC/SPN/keytab/validator succeed and localUsers finds **alice@EXAMPLE.ORG**, **/private** returns **Authenticated: alice@EXAMPLE.ORG**.
- If the principal returned by the KDC has a different format, it must be mapped properly by policy rather than defaulting to email or stripping the realm to force login.
- **http://localhost:8080** does not match the SPN HTTP/intranet.example.org; testing real SSO requires accessing **https://intranet.example.org** with real DNS/HTTPS ingress and keytab.

## 11. JAAS / Java GSS-API in JDK 17

Beneath the Spring extension lie JDK **JAAS** and **GSS-API**. JDK 17 provides **Krb5LoginModule**, **LoginContext**, **KerberosPrincipal**, and the **org.ietf.jgss** package.

**Example JAAS acceptor configuration (jaas.conf):**

~~~text
KerberosAcceptor {
    com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    keyTab="/etc/security/keytabs/http-intranet.keytab"
    storeKey=true
    doNotPrompt=true
    isInitiator=false
    principal="HTTP/intranet.example.org@EXAMPLE.ORG";
};
~~~

Explanation:

- **useKeyTab=true** uses the keytab file.
- **storeKey=true** makes acceptor credentials/keys available in the Subject when appropriate.
- **isInitiator=false** configures the service to accept GSS contexts, rather than acting as an initiator client.
- **doNotPrompt=true** disables interactive password prompting.
- **principal** must match the exact service principal for which the browser requests a ticket.
- The JAAS config and keytab are stored outside the webroot and never exposed over APIs.

**Java GSS-API snippet after obtaining Subject/JAAS acceptor** — this is an API-illustrative snippet, **not a standalone compilable program** without imports, request handler, GSS credentials, JAAS, and a KDC:

~~~java
GSSManager manager = GSSManager.getInstance();
GSSContext context = manager.createContext((GSSCredential) null);

byte[] output = context.acceptSecContext(
        inputNegotiateToken, 0, inputNegotiateToken.length);

if (!context.isEstablished()) {
    // Continue HTTP 401 WWW-Authenticate: Negotiate with the output token.
    return;
}

GSSName clientName = context.getSrcName();
// Only after an established context + mechanism/service checks
// map clientName to a local account and permissions.
~~~

You must import the `org.ietf.jgss` types and execute inside an acceptor Subject holding service credentials. In production, you must handle the GSS final token, mutual auth, replay, TLS, response framing, cleanup, and standard errors; do not write a custom GSS filter to replace the library just because the snippet is short.

## 12. Inspection Tools on Client and Server

### MIT Kerberos (Linux/macOS when the toolkit is installed)

~~~bash
# Inspect credentials/TGT/service tickets in the user's cache
klist
klist -e

# Only use in an authorized lab: obtain a TGT
kinit alice@EXAMPLE.ORG

# Request a service ticket and check the version from the KDC
kvno HTTP/intranet.example.org@EXAMPLE.ORG
~~~

**klist** lists cached tickets. **kvno** requests a service ticket and reports the key version; failures here usually point to client/KDC/DNS/SPN issues before reaching the Spring backend.

### Windows

~~~powershell
klist
klist tickets
setspn -Q HTTP/intranet.example.org
~~~

Windows `klist` differs in syntax and permissions from MIT `klist`; do not apply `-e` or `-k` options verbatim across the two OSes. **setspn -S** alters AD configuration and should only be executed by an admin with change approval.

### Server Keytab

~~~bash
klist -k -e /etc/security/keytabs/http-intranet.keytab
~~~

You should see the matching service principal and appropriate kvno/enctype, without printing key material or copying the keytab off the server. Do not use options that print secret keys into terminal logs.

### HTTP/Browser

Inspect DevTools → Network:

1. Does **/private** return 401 + **WWW-Authenticate: Negotiate**?
2. Does the browser send **Authorization: Negotiate**?
3. Does the public hostname match the registered SPN exactly?
4. Does the GSS acceptor actually verify the context and keytab?
5. If the ticket passes, does **UserDetailsService** return a local account?
6. Do subsequent requests persist the SecurityContext/session or return 401 again?
7. Does an authenticated user lacking permissions receive 403?

On a machine with a Kerberos cache and a GSS-enabled curl build:

~~~bash
curl --negotiate -u : -i https://intranet.example.org/private
~~~

This command **does not acquire a TGT by itself** and will fail if the client lacks credentials or does not trust the hostname/KDC. Avoid logging raw Authorization headers, even when using curl --verbose.

### JDK Debugging in Controlled Environments Only

~~~text
-Dsun.security.krb5.debug=true
-Djava.security.auth.login.config=/etc/security/jaas.conf
~~~

Enable debugging only in a sandbox or an approved investigation window; logs may contain principal/realm/ticket details. Use redacted reason codes and trace IDs instead of storing tokens/keytabs/credentials.

## 13. Troubleshooting: Distinguishing 401, KDC, Keytab, and Authorization

| Symptom | Likely Cause | How to Diagnose |
| --- | --- | --- |
| Missing WWW-Authenticate: Negotiate | Misconfigured entry point/filter chain/proxy response. | Check exceptionHandling and reverse proxy headers. |
| 401 returned, but browser sends no token | IWA policy, host outside intranet, client has no TGT. | AuthServerAllowlist, klist, DNS/KDC. |
| **KDC_ERR_S_PRINCIPAL_UNKNOWN** | SPN does not exist or client requested wrong hostname. | setspn -Q, kvno, DNS aliases. |
| **KRB_AP_ERR_MODIFIED** | Wrong service keytab/SPN owner/kvno/enctype; server cannot decrypt ticket. | Check AD service account, keytab, and rotation. |
| **KRB_AP_ERR_SKEW** | Clock skew exceeds realm policy. | Check NTP, ticket lifetime, and client/KDC/server clocks. |
| GSSException: Defective token | Truncated header, incompatible mechanism, corrupted token. | Check proxy/header limits and SPNEGO mechanism. |
| GSSException: No valid credentials | Acceptor failed to load keytab or wrong principal. | File permissions, jaas.conf, servicePrincipal. |
| Repeated 401 after ticket passes | SecurityContext not persisted, lost session cookie, or LB switched nodes. | SecurityContextRepository, session strategy, shared sessions. |
| 403 after ticket passes | Denied by local account/role/resource policy. | UserDetailsService, authority mapping, tenant membership. |
| SSO works only on canonical hostname, not alias | Service ticket requested under a different SPN. | FQDN, CNAME/canonicalization, SPN/keytab. |
| SSO works only on node A | Broken keytab on node B or unshared local session. | Per-node keytab/kvno, LB and session store. |
| HTTP Negotiate falls back to NTLM | Browser/KDC failed to get a Kerberos ticket or policy allowed it. | Actual GSS mechanism, Kerberos-only enforcement. |
| KDC is online yet web app still returns 401 | Possible GSS/server acceptor or role mapping issue. | Trace each layer rather than immediately blaming the network. |
| Local logout performed, yet browser still SSOs | Client still holds TGT/service ticket and auto-Negotiates. | Distinguish workstation credentials from local session. |
| App A cannot use user's Kerberos identity to call DB B | Delegation/KCD not configured. | Double-hop/KCD policy, do not trust X-User header. |

## 14. Double-Hop: SSO Does Not Imply Delegation

An employee signs in to intranet app A with Kerberos, and app A then needs to call backend B **using the employee's own identity**. A has authenticated the user, yet **does not automatically have a credential or authority to act on the user's behalf at backend B**.

~~~text
Browser alice --HTTP/intranet ticket--> Web A
Web A        --requires own ticket/delegation--> Backend B
~~~

**Kerberos Constrained Delegation (KCD)** or **Resource-Based KCD** can enable **S4U2Self/S4U2Proxy** flows under an appropriate AD policy. This is a distinct design with its own risks:

- Only allow A to delegate to approved services.
- Never enable **unconstrained delegation** just to make an app work.
- Never use a service account with domain-admin privileges.
- Verify user/tenant permissions at backend B even when Kerberos delegation succeeds.
- If A calls B using **A's own service account**, that is service-to-service auth, **not automatic impersonation of alice**.
- B must not trust an **X-User: alice** header supplied by an external client.

**SSO** reduces initial credential prompts for the user; **delegation** allows an intermediary service to exercise the user's identity at another service. The two concepts are related but not identical.

## 15. HTTPS, Sessions, and Authorization Remain Mandatory

- **TLS/HTTPS** protects the HTTP body, cookies, session IDs, and headers. HTTP Negotiate only establishes the authentication context and does not encrypt the full HTTP request/response.
- **Spring HttpSession** is independent of the Kerberos TGT. The app can issue a session so it does not need to re-Negotiate on every request; session expiry or logout does not delete the user's workstation TGT.
- **CSRF** still matters when the app uses cookie-based sessions for state-changing requests; do not disable CSRF globally because of SPNEGO.
- **Service keytab** is a server-level secret; protect it with file ACLs/secret manager, key rotation, and no logging.
- **UserDetailsService** does not automatically grant admin rights. Principal alice@EXAMPLE.ORG needs an active local account, scoped roles, and membership.
- **Cross-realm trust** does not mean users from every realm can access resources. Map realms/identities/accounts using an allowlist.
- **Ticket expiry** does not automatically terminate all existing local sessions; fast revocation requires session/authorization policies.
- **A Kerberos-only policy** must actually reject unsuitable SPNEGO fallbacks rather than passing merely because a Negotiate header is present.
- **A reverse proxy** should forward a verified identity over a trusted channel only if it is the GSS acceptor; never trust a public X-Forwarded-User header.

## 16. When Should You Use Kerberos SSO?

| Context | Choice |
| --- | --- |
| Domain-joined employee machines, stable intranet, existing AD/KDC | **Kerberos/SPNEGO is suitable**, browser IWA can provide silent login. |
| Linux/macOS workstations with GSS cache and browser policy | Kerberos can be used, requires real testing. |
| Public website serving customers outside the domain | OIDC/SAML2 is usually better as the primary login. |
| Mobile apps lacking a Kerberos credential cache | Consider OIDC/mobile SSO agent or an enterprise bridge. |
| SaaS needing SSO from AD | IdP uses internal Kerberos and issues SAML2/OIDC to SaaS. |
| Multi-node intranet web | Consistent SPN/keytab or proxy acceptor; separate HA session handling. |
| User needs to call multiple backends on their behalf | Separate KCD/S4U or delegated auth design; not automatic. |
| Requirement for immediate permission revocation | Combine local account/role/session revocation; do not rely solely on ticket expiry. |

## 17. Positive and Negative Testing

Use an **AD/KDC sandbox**, test service accounts, and managed browser policies. **Do not create SPNs on production AD** or copy keytabs without authorization.

| # | Scenario | Expectation |
| --- | --- | --- |
| 1 | Client has TGT, SPN/keytab correct | Browser sends Negotiate, server can authenticate. |
| 2 | Client has no TGT and no fallback | SSO does not complete; no Authentication is created. |
| 3 | Browser does not allowlist intranet host | May not send Authorization Negotiate. |
| 4 | Spring is missing SpnegoEntryPoint | No proper Negotiate challenge is sent. |
| 5 | Spring is missing SpnegoAuthenticationProcessingFilter | Challenge is sent, but server does not process the token. |
| 6 | Missing KerberosServiceAuthenticationProvider | Service ticket is not verified, fails. |
| 7 | SPN not registered | KDC returns principal unknown or equivalent error. |
| 8 | Duplicate SPN across accounts | Ownership/crypto error; do not create duplicate accounts. |
| 9 | CNAME URL differs from SPN in keytab | Fails depending on client canonicalization/config. |
| 10 | Keytab has wrong principal or file permissions | GSS acceptor fails; login denied. |
| 11 | Stale keytab kvno after key rotation | Integrity/ticket decryption fails. |
| 12 | Client and KDC clock drift | Clock skew/time check fails. |
| 13 | Expired or replayed ticket | Rejected per Kerberos policy. |
| 14 | Actual mechanism is NTLM when Kerberos-only is required | Deny. |
| 15 | HTTPS cert hostname mismatch | TLS fails; do not disable cert verification. |
| 16 | Ticket passes, but local account is disabled | Access not granted. |
| 17 | User lacks ADMIN role | Admin resource returns 403. |
| 18 | User lacks tenant membership | Cross-tenant access denied. |
| 19 | Custom SPNEGO filter does not persist SecurityContext | Next request may get 401; test and fix repository. |
| 20 | Browser session expires while TGT remains valid | May re-SSO without prompting for password. |
| 21 | Node A keytab valid, node B keytab broken | LB causes intermittent failures; check per-node. |
| 22 | KDC temporarily offline, cached ticket still valid | Context may still work depending on policy/cache. |
| 23 | Client needs a new service ticket while KDC is offline | Cannot obtain ticket, fails. |
| 24 | User from untrusted realm | Deny mapping/realm trust. |
| 25 | Server A wants to call B on user's behalf without KCD | Delegation fails; no automatic impersonation. |
| 26 | CAS or SAML IdP uses internal Kerberos | SaaS receives only the corresponding CAS/SAML/OIDC artifact, not raw AP-REQ. |
| 27 | Authorization token logged into access log | Security QA fails; must redact. |
| 28 | Service accessed via http://localhost | Does not automatically match SPN HTTP/intranet.example.org. |
| 29 | Public GET / | Negotiate not required per route policy. |
| 30 | GET /private after successful Kerberos and local membership | 200 with verified principal and proper authorization. |

**A negative test succeeds when the security layer rejects properly**, not when ticket verification, TLS, RBAC, or session controls are bypassed to mask errors.

## 18. Common Mistakes

1. **Treating Kerberos as a shared cookie across all apps.** TGTs and service tickets differ from HttpSession.
2. **Assuming domain logon guarantees SSO for every browser/URL.** Requires intranet allowlist, credentials, and SPN.
3. **Equating SPNEGO Negotiate with verified Kerberos.** Negotiation may pick another mechanism.
4. **Believing Kerberos encrypts all HTTP traffic.** HTTPS is still required.
5. **Registering an SPN as a URL with https:// or /private.** An SPN is typically HTTP/hostname.
6. **Binding the same SPN to multiple AD accounts.** Causes principal ambiguity and key mismatch.
7. **Assuming DNS aliases always map to the original SPN.** Canonicalization must be tested.
8. **Treating a keytab as a public certificate.** It contains secret service keys.
9. **Sending the TGT directly to the web server.** Browsers use a service ticket/GSS context.
10. **Ignoring clock skew, kvno, and enctype.** They directly affect ticket acceptance.
11. **Thinking adding starter-security alone enables SPNEGO.** Extension, filter, and provider are required.
12. **Thinking SpnegoEntryPoint creates an Authentication.** It only issues the challenge.
13. **Failing to set SecurityContextRepository on a custom filter.** Authentication may not persist.
14. **Skipping local UserDetailsService/permissions because the KDC trusts the user.** Authentication is not authorization.
15. **Concluding that local logout must destroy the TGT.** They have separate lifecycles.
16. **Using unconstrained delegation for double-hop.** Violates least privilege.
17. **Making the service account a Domain Admin.** Unnecessary and increases risk.
18. **Disabling TLS or Kerberos checks just to make SSO "pass".** Unsafe.
19. **Logging raw Authorization Negotiate tokens or keytabs.** Leaks credentials.
20. **Confusing SAMLResponse/OIDC Token with Kerberos AP-REQ.** Different protocols.

## 19. Production Checklist

**KDC / browser / network**

- [ ] Realm, client principal, server SPN, and DNS/FQDN are correct.
- [ ] AD/MIT KDC, browser allowlist, and credential cache are verified.
- [ ] Unique SPN, keytab with correct key/kvno/enctype, synchronized time.
- [ ] No weak crypto or unapproved fallback enabled.
- [ ] Cross-realm/delegation policies have owner, scope, and audit.

**Spring and app**

- [ ] Spring Kerberos extension matches the proper version family.
- [ ] SpnegoEntryPoint, filter, ProviderManager, KerberosServiceAuthenticationProvider, and SunJaasKerberosTicketValidator are wired properly.
- [ ] Custom filter has SecurityContextRepository/session fixation strategy.
- [ ] UserDetailsService maps verified principal to an active local account with scoped roles.
- [ ] HTTPS, CSRF, cookie security, LB/session persistence, and fail-closed behavior.
- [ ] Kerberos-only policy actually verifies the mechanism and does not silently downgrade.

**QA / operations**

- [ ] Test 401 challenge, Negotiate response, accepted context, and local 403.
- [ ] Test alias, duplicate SPN, kvno rotation, clock skew, ticket expiry, KDC offline.
- [ ] Test multi-node, logout/relogin, non-domain-joined browser.
- [ ] Protect keytabs/tickets/credentials from logs and unauthorized backups.
- [ ] Have an OIDC/SAML2 bridge plan for SaaS/external devices and separate KCD for backend hops.

## 20. Self-Check Questions

**1. Why can a user who logs into a domain once open multiple intranet apps without re-entering a password?**  
Because the client holds a TGT and requests a separate service ticket per SPN; the browser/GSS uses those tickets to authenticate with each app.

**2. Is HTTP Authorization: Negotiate enough to confirm the user is a Kerberos principal?**  
No. The server must verify the GSS token/context using service keys and policy, verify the actual mechanism, and only then map the account.

**3. How does a TGT differ from a service ticket?**  
A TGT allows requesting tickets from the TGS; a service ticket is scoped to a specific service principal for AP authentication.

**4. Why are both HTTPS and a keytab needed?**  
HTTPS protects the HTTP channel, while the keytab holds the Kerberos service key so the server can verify tickets. The two layers do not replace each other.

**5. Why might the HTTPS alias portal.example.org fail while intranet.example.org works?**  
The browser may request an SPN for the alias, while the account/keytab lacks that matching service principal. DNS/SPN alignment and client canonicalization must be checked.

**6. A Kerberos ticket passes, yet /admin returns 403—does that mean SSO is broken?**  
No. Local user/role/resource authorization can deny an authenticated user.

**7. Why does a custom SpnegoFilter need a SecurityContextRepository?**  
If a stateful session is desired in Spring Security 6.x, the filter must persist Authentication after successful GSS; otherwise subsequent requests can revert to anonymous.

**8. Does logging out of the app in the browser remove the Windows TGT?**  
No. The local HttpSession and client Kerberos cache are two separate scopes; the browser can silently log in again.

**9. Does Kerberos SSO automatically give Web A permission to call DB B on the user's behalf?**  
No. It requires KCD/S4U or a dedicated service-to-service/delegation mechanism.

**10. Does a SaaS using SAML2 have to deploy a keytab just because the IdP uses Kerberos internally?**  
No. The SaaS SP validates the SAML2 protocol, while the IdP uses Kerberos to authenticate the user on the IdP side.

## 21. Official References

1. [RFC 4120 — Kerberos V5](https://www.rfc-editor.org/rfc/rfc4120): AS/TGS/AP exchanges, tickets, authenticators, replay, and lifetime.
2. [RFC 4559 — SPNEGO-based Kerberos and NTLM HTTP Authentication](https://www.rfc-editor.org/rfc/rfc4559): WWW-Authenticate/Authorization Negotiate, 401 flow, and HTTP protection limits.
3. [RFC 4178 — SPNEGO](https://www.rfc-editor.org/rfc/rfc4178): mechanism negotiation.
4. [RFC 4121 — Kerberos GSS-API mechanism](https://www.rfc-editor.org/rfc/rfc4121): GSS security contexts/tokens.
5. [MIT Kerberos — Enctypes and tickets](https://web.mit.edu/kerberos/www/krb5-latest/doc/admin/enctypes.html): AS/TGS, service key, session key.
6. [MIT Kerberos — kinit](https://web.mit.edu/kerberos/www/krb5-latest/doc/user/user_commands/kinit.html), [klist](https://web.mit.edu/kerberos/www/krb5-latest/doc/user/user_commands/klist.html), [kvno](https://web.mit.edu/kerberos/www/krb5-latest/doc/user/user_commands/kvno.html): CLI diagnostics.
7. [Oracle Java 17 — Krb5LoginModule](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.security.auth/com/sun/security/auth/module/Krb5LoginModule.html): keyTab, principal, storeKey, and isInitiator.
8. [Oracle — JAAS and Java GSS-API](https://docs.oracle.com/en/java/javase/17/security/use-jaas-login-utility-and-java-gss-api-secure-message-exchanges.html): service principals, JAAS acceptor.
9. [Spring Security Kerberos Reference](https://docs.spring.io/spring-security-kerberos/reference/ssk.html): KerberosServiceAuthenticationProvider, SpnegoEntryPoint, SunJaasKerberosTicketValidator.
10. [Spring Security Kerberos 2.1.1 — SpnegoAuthenticationProcessingFilter Javadoc](https://docs.spring.io/spring-security-kerberos/docs/2.1.1/api/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html): SecurityContextRepository, session strategy, token processing.
11. [Spring Security Kerberos — Spring Project](https://spring.io/projects/spring-security-kerberos/): extension/version family.
12. [Microsoft Learn — setspn](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/setspn): SPN registration and duplicate detection.
13. [Microsoft Edge — AuthServerAllowlist](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-browser-policies/authserverallowlist): browser integrated authentication.
14. [Microsoft Entra — Kerberos constrained delegation](https://learn.microsoft.com/en-us/entra/architecture/auth-kcd): double-hop/KCD and remote access.

**Conclusion:** Kerberos delivers intranet SSO through **client TGT → SPN-based service ticket → browser SPNEGO/GSS → server acceptor using keytab**, not by sharing passwords or HttpSession. Spring Security receives the verified identity, yet **HTTPS, local account/role authorization, session security, SPN/keytab/DNS/clock, replay protection, and delegation policy** must still be managed independently. When reaching the Internet/SaaS, Kerberos is typically used on the **enterprise IdP side**, while external apps receive **SAML2/OIDC**.
