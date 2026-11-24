# Configuring JAAS, krb5.conf, and Secret Paths for Kerberos Integration

> **Module:** Spring Security – federation. **Group:** Kerberos Integration. **Focus:** configuring Kerberos V5 for Java 17 and Spring Security applications using SPNEGO, properly distinguishing **acceptor/initiator** roles, managing `krb5.conf`, **JAAS login configuration**, **keytabs**, ticket caches, and secret mount paths. This lesson uses illustrative domains/principals `EXAMPLE.ORG` and `portal.example.org`, with no real credentials. Application configuration must be tested against your actual JDK, Spring Security Kerberos extension, KDC/Active Directory, and runtime platform.

## 1. Learning Objectives

After this lesson, you can:

1. Explain the distinct responsibilities of `krb5.conf` (locating realms/KDCs), **JAAS** (how Java acquires/holds Kerberos credentials), and **keytab/ticket caches** (sensitive authentication material).
2. Distinguish an **acceptor principal** for HTTP/SPNEGO services from an **initiator principal** for a Java client calling another Kerberos-protected service.
3. Configure `com.sun.security.auth.module.Krb5LoginModule` with `useKeyTab`, `keyTab`, `principal`, `storeKey`, `isInitiator`, `doNotPrompt`, `useTicketCache`, and `ticketCache` appropriately for each role.
4. Identify Java system properties `java.security.krb5.conf`, `java.security.auth.login.config`, and `javax.security.auth.useSubjectCredsOnly`, knowing how they differ from MIT Kerberos environment variables.
5. Place keytabs in a **secret volume/read-only path**, lock down file mode/UID/GID, and forbid credentials in Git, Docker images, logs, and user-controlled paths.
6. Explain the flow **HTTP 401 WWW-Authenticate: Negotiate** → Kerberos service ticket → `Authorization: Negotiate ...` → Java GSS/JAAS → Spring authentication → application authorization.
7. Author sample `krb5.conf` and `jaas.conf` files alongside Java 17 launch commands, separating standalone runnable code from code requiring a real KDC/keytab.
8. Establish a test workflow for **KDC, DNS, SPN, key version number (KVNO), encryption types, time skew, and TLS**, verifying zero secret printing and safe debugging.
9. Handle multi-realm, reverse proxy, container/Kubernetes, keytab restart/rotation, and permission failures.
10. Build a positive/negative QA matrix before promoting SPNEGO/Kerberos to production.

**Prerequisites:** HTTP, DNS and hostnames/FQDNs, Linux file permissions, Java 17, Spring Security `SecurityFilterChain`, Active Directory or MIT Kerberos, and the principle of least privilege. If new to Kerberos, familiarize yourself first with **KDC**, **AS/TGS**, **TGT**, **service ticket**, **realm**, and **SPN**.

## 2. Context: Java Portal Authenticating via Kerberos/SPNEGO

Suppose a user in corporate realm `EXAMPLE.ORG` visits:

~~~text
https://portal.example.org/private
~~~

Kerberos involves these entities:

| Component | Example | Responsibility |
| --- | --- | --- |
| Kerberos realm | `EXAMPLE.ORG` | Logical domain managing principals and keys |
| KDC/AD Domain Controller | `kdc1.example.org:88`, `kdc2.example.org:88` | Issues TGTs and service tickets, validates principals |
| User principal | `lan@EXAMPLE.ORG` | KDC-authenticated user identity |
| HTTP service principal/SPN | `HTTP/portal.example.org@EXAMPLE.ORG` | Identity of the server accepting Kerberos service tickets |
| Java/Spring server | Portal on VM or Pod | Receives SPNEGO token, decrypts/verifies service ticket via keytab |
| Keytab | `/run/secrets/kerberos/http-portal.keytab` | Holds long-term keys of the service principal, **a secret** |
| JAAS config | `/etc/kerberos/jaas.conf` | Selects login module and keytab/principal/path/flags |
| krb5.conf | `/etc/kerberos/krb5.conf` | Realm/KDC/domain mapping and Kerberos settings |
| Ticket cache | `/run/kerberos/ccache/svc-reader.ccache` | May hold TGT/credentials used by an initiator, **a secret** |

Browser SSO flow:

~~~text
User/browser                         KDC/AD                 Portal Java
    |                                  |                         |
    |-- accesses HTTPS /private -------------------------------->|
    |<--------- 401 WWW-Authenticate: Negotiate ----------------|
    |                                  |                         |
    |-- gets service ticket for HTTP/portal.example.org -------->|
    |<--------- Kerberos ticket --------------------------------|
    |-- Authorization: Negotiate [SPNEGO token] ---------------->|
    |                                  |                   JAAS/JGSS
    |                                  |                 acceptor keytab
    |                                  |                   validate ticket
    |<-------------------- 200 /private (if authorized) --------|
~~~

The browser usually holds a TGT because the user logged into the domain. The server **neither needs nor should possess** each user's password/TGT just to accept SPNEGO. The server needs the **service key** for the matching SPN, typically inside a keytab. Kerberos authentication reveals the principal to the app; **role/tenant/resource permissions are still governed by Spring Security and business logic**.

### 2.1. Do Not Confuse Kerberos with Other Technologies

- A Kerberos service ticket is a credential bound to a KDC and SPN, not a SAML Assertion, OIDC ID Token, or OAuth Access Token.
- JAAS is not a KDC and does not issue tickets; it is an API/configuration layer for Java authentication modules to acquire or load credentials into a `Subject`.
- `krb5.conf` does not contain the service's private key; it describes realms, KDCs, and Kerberos discovery policy. Still, it discloses internal topology, so govern read/write access per policy.
- A keytab holds **keys** proving service identity that can be copied and abused. Putting a keytab on a filesystem with encryption at rest does not automatically protect it once the app or host is compromised.
- A ticket cache holds time-bounded credentials; it is **not** harmless config metadata and needs protection comparable to a keytab.

## 3. Three Configuration Layers That Must Align

~~~text
Layer 1 — Kerberos topology
  /etc/kerberos/krb5.conf
  -> default_realm, KDC, domain_realm

Layer 2 — Java authentication behavior
  /etc/kerberos/jaas.conf
  -> Krb5LoginModule
  -> principal, keyTab, isInitiator, useTicketCache, storeKey

Layer 3 — Secret material/runtime
  /run/secrets/kerberos/http-portal.keytab
  /run/secrets/kerberos/svc-reader.keytab
  /run/kerberos/ccache/svc-reader.ccache
  -> UID/GID, read/write permissions, secret manager, rotation

Java process (JDK 17):
  -Djava.security.krb5.conf=/etc/kerberos/krb5.conf
  -Djava.security.auth.login.config=/etc/kerberos/jaas.conf
  Spring Security Kerberos acceptor / JGSS / LoginContext
~~~

**Why not bundle them together?** Changing KDC/realm routing usually requires no service key change; changing a principal or keytab may require updating AD/SPN and key versions; changing a mount location is purely a path/runtime update. Hardcoding everything in Java source makes key rotation, auditing, and rollouts brittle.

### 3.1. File Comparison Table

| File | Contains | Is It a Secret? | Who Provisions & Updates? | Recommended Permissions |
| --- | --- | --- | --- | --- |
| `krb5.conf` | Realm/KDC/DNS mapping | Usually not a credential, though topology-sensitive | Platform/Identity team | Admin-owned, app-readable, admin-writable only |
| `jaas.conf` | Module/options/principal/keytab path | Usually no secrets **if no inline passwords**, though exposes paths/IDs | App/Platform Security | App-readable, trusted deploy/admin writable only |
| `http-portal.keytab` | Keys for the HTTP SPN | **Yes, highly sensitive** | Identity team / secret provisioning | Acceptor workload read-only |
| `svc-reader.keytab` | Key for client/service principal | **Yes** | Identity team / secret provisioning | Necessary client workload read-only |
| `svc-reader.ccache` | TGT/credentials (if used) | **Yes** | Kerberos client/JAAS runtime | Exact UID read/write only, TTL/cleanup |
| JKS/PKCS12 TLS keystore | TLS private key/cert, distinct from Kerberos | **Yes** if holding private key | PKI/secret provisioning | Restricted per server TLS policy |

**Avoiding confusion:** Java `keyTab=...` points to a **binary keytab**, not a `.crt`, `.pem`, TLS keystore, or `krb5.conf`. Java cannot validate an SPNEGO service ticket merely because it has a TLS certificate.

## 4. Declaring krb5.conf for Realms and KDCs

Example **`/etc/kerberos/krb5.conf`**:

~~~ini
[libdefaults]
    default_realm = EXAMPLE.ORG
    dns_lookup_realm = false
    dns_lookup_kdc = false
    forwardable = false

[realms]
    EXAMPLE.ORG = {
        kdc = kdc1.example.org:88
        kdc = kdc2.example.org:88
    }

[domain_realm]
    .example.org = EXAMPLE.ORG
    example.org = EXAMPLE.ORG
~~~

This is an **MIT-style `krb5.conf`**. The Java Kerberos runtime supports a compatible subset; minor directives can behave differently from MIT CLI tools, so never assume every MIT directive shares identical semantics in JDK 17.

**Explanation:**

- `[libdefaults] default_realm`: default realm when a principal omits the realm. In code/service configs, use **full principals with `@EXAMPLE.ORG`** to avoid ambiguity.
- `dns_lookup_realm=false`: disables DNS realm guessing; uses the managed `[domain_realm]` section.
- `dns_lookup_kdc=false`: disables DNS SRV KDC lookup; `[realms]` declares approved KDCs. Some AD setups rely on DNS SRV discovery; configure per actual policy rather than toggling blindly.
- `kdc=...:88`: KDC list for availability/failover. Verify pod/VM network access to TCP/UDP 88 per policy, KDC DNS, latency, and timeouts.
- `[domain_realm]`: maps host domain names to Kerberos realms; not a wildcard TLS certificate or access grant.
- `forwardable=false` merely illustrates a policy restricting TGT delegation; if real business logic needs Kerberos delegation/constrained delegation, design an explicit policy and inspect KDC/AD settings. Never set `forwardable=true` just to "make SPNEGO work".

**Do not force legacy `default_tkt_enctypes` or `default_tgs_enctypes`** without a specific KDC requirement. Disable weak DES/RC4 and pick encryption types supported by Java/KDC/AD policy, preferring AES per organizational standards.

### 4.1. Commonly Confused Addresses

~~~text
portal.example.org
    -> PUBLIC hostname accessed by browser
    -> HTTP/portal.example.org@EXAMPLE.ORG

kdc1.example.org
    -> ticket-issuing host (KDC)
    -> NOT Portal's SPN

portal-pod-7.internal.cluster
    -> internal Pod/backend name
    -> DOES NOT automatically replace HTTP/portal.example.org

/etc/kerberos/krb5.conf
    -> path to file describing KDC/realm, DOES NOT hold service keys
~~~

If the browser visits an alias `alias.example.org`, the ticket may be requested for `HTTP/alias.example.org` (depending on hostname canonicalization/browser), while the keytab only holds `HTTP/portal.example.org`: verification will fail. Keep the **canonical public FQDN**, SPN, and browser URL consistent; test DNS CNAME/canonicalization and reverse proxy behavior in a real environment. Never work around this by accepting arbitrary service principals with a domain-wide keytab.

### 4.2. Multi-Realm and Trust

For organizations with `EXAMPLE.ORG` and `PARTNER.ORG`:

- Every principal carries an explicit realm, with matching KDCs and cross-realm trust.
- `[domain_realm]` only maps hosts to realms; it does not grant trust.
- Portal's keytab needs the key for the SPN targeted by browsers; it does not need keys from every realm if cross-realm KDC trust is configured.
- Test referrals, clock synchronization, encryption types, and cross-realm routing with integration tests.
- Never pick a realm from user query/header input or build a keytab path from a client-supplied tenant name.

## 5. JAAS File: Where Java Selects Krb5LoginModule

JAAS login configuration (distinct from `krb5.conf`) defines **entry names** and module/option sequences. Java's `LoginContext("KrbAcceptor")` looks up the entry named `KrbAcceptor`. Java GSS/HTTP SPNEGO may use built-in default entry names like `com.sun.security.jgss.krb5.initiate`; thus entry names must **match what the client/framework invokes**, rather than guessing from filenames.

### 5.1. Acceptor: Portal Receiving SPNEGO Tokens

**`/etc/kerberos/jaas.conf`**, entry for the server:

~~~text
KrbAcceptor {
    com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    keyTab="/run/secrets/kerberos/http-portal.keytab"
    principal="HTTP/portal.example.org@EXAMPLE.ORG"
    storeKey=true
    isInitiator=false
    doNotPrompt=true
    useTicketCache=false
    debug=false;
};
~~~

**Key options:**

| JAAS Option | Acceptor Value | Meaning |
| --- | --- | --- |
| `useKeyTab=true` | Enabled | Reads key from keytab file instead of prompting for a password |
| `keyTab="/run/secrets/.../http-portal.keytab"` | Absolute, restricted mount | Independent of working directory/user home |
| `principal="HTTP/portal.example.org@EXAMPLE.ORG"` | Full service principal | Matches the SPN browsers request tickets for from the KDC |
| `storeKey=true` | Enabled | Stores the key/keytab handle in the JAAS `Subject`'s private credentials so the acceptor can use it |
| `isInitiator=false` | Crucial | Acceptor-only: does not require fetching a TGT via AS exchange at login |
| `doNotPrompt=true` | Enabled | Fails closed if keytab/principal is unusable rather than opening an interactive prompt |
| `useTicketCache=false` | Explicitly disabled | Server acceptor needs no user TGT cache solely to accept HTTP tickets |
| `debug=false` | Production | Avoids logging Kerberos/JGSS/JAAS internals |

**Do not default to `principal="*"`**: JDK 17 supports a wildcard principal on acceptors with `isInitiator=false`, yet that accepts tickets for any principal whose key resides in the keytab. If an application uses a single SPN, pin that exact principal. When multiple SPNs exist, clarify trust policy, identity/multi-tenancy, and keytab contents.

### 5.2. Acceptor Entry for JGSS Default Login Name

Some Java GSS clients/acceptors look up the standard JAAS entry name:

~~~text
com.sun.security.jgss.krb5.accept {
    com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    keyTab="/run/secrets/kerberos/http-portal.keytab"
    principal="HTTP/portal.example.org@EXAMPLE.ORG"
    storeKey=true
    isInitiator=false
    doNotPrompt=true
    debug=false;
};
~~~

When using Spring Security Kerberos `SunJaasKerberosTicketValidator` with `setServicePrincipal(...)` and `setKeyTabLocation(...)`, the implementation can build its JAAS/GSS login config internally. **Never assume** simply defining a `KrbAcceptor` entry makes Spring read it; inspect your library implementation and version. Both approaches (app-managed JAAS and validator-managed keytab) must align on **principal, path, and realm**, avoiding loading two different identities.

### 5.3. Initiator: Java Service Calling a Backend as a **Service Identity**

Another service needing Kerberos to **initiate** requests to backend `HTTP/reports.example.org@EXAMPLE.ORG`, using its own principal `svc-reader@EXAMPLE.ORG` and dedicated keytab:

~~~text
KrbInitiator {
    com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    keyTab="/run/secrets/kerberos/svc-reader.keytab"
    principal="svc-reader@EXAMPLE.ORG"
    storeKey=false
    isInitiator=true
    doNotPrompt=true
    useTicketCache=false
    debug=false;
};
~~~

With `isInitiator=true`, JAAS may need to **contact the KDC for a TGT** at login if no usable ticket cache exists. The keytab here holds **svc-reader's** key, not the HTTP Portal key. This is **service-to-service authentication as svc-reader**, **not automatic Kerberos delegation on behalf of user Lan**. Constrained delegation/S4U requires separate AD/KDC policy, Java/GSS support, and downstream authorization design.

**Avoid sharing one entry for both acceptor and initiator** just to save lines. Acceptors need `storeKey=true` and `isInitiator=false`; initiators acquire credentials with `isInitiator=true`. The two keytabs carry different privileges and blast radii.

### 5.4. Initiator Using a Ticket Cache Instead of a Keytab

If a Java client runs inside a session already holding a TGT and reads from a configured cache:

~~~text
KrbCachedClient {
    com.sun.security.auth.module.Krb5LoginModule required
    useTicketCache=true
    ticketCache="/run/kerberos/ccache/svc-reader.ccache"
    useKeyTab=false
    storeKey=false
    isInitiator=true
    doNotPrompt=true
    debug=false;
};
~~~

Combinations must be valid per the JDK:
- `ticketCache` **is valid only when `useTicketCache=true`**.
- `renewTGT=true` also requires `useTicketCache=true`; do not enable without understanding renewable TGT policies and providers.
- Setting `doNotPrompt=true` **without** `useTicketCache`/`useKeyTab`/valid credential sources is misconfigured and fails.
- `keyTab=...` takes effect only when `useKeyTab=true`; specifying the path without enabling the flag does nothing.
- If both cache and keytab are enabled, `Krb5LoginModule` follows a credential lookup order (cache before keytab); define fallback and policy explicitly to avoid picking unexpected credentials.

**Ticket caches hold TGTs**: protect the file, TTL, owner, and cleanup; never place multiple users' caches at one path or make them world-readable.

## 6. Java System Properties Differ from MIT Kerberos Environment Variables

Launching the JVM with dedicated config/JAAS files:

~~~bash
java \
  -Djava.security.krb5.conf=/etc/kerberos/krb5.conf \
  -Djava.security.auth.login.config=/etc/kerberos/jaas.conf \
  -Djavax.security.auth.useSubjectCredsOnly=true \
  -cp app.jar \
  demo.KerberosAcceptorProbe
~~~

**Note:** this command merely illustrates setting properties for a Java class; for a Spring Boot executable JAR, run `java ... -jar app.jar` without `-cp app.jar demo.Class`. The testing section below has a dedicated command for `KerberosAcceptorProbe` when a real keytab is available.

| Setting | Consumer | Meaning | Interchangeable? |
| --- | --- | --- | --- |
| `-Djava.security.krb5.conf=/path/krb5.conf` | **JDK Kerberos** | Points to MIT-style realm/KDC config file | **Not** a JAAS file |
| `-Djava.security.auth.login.config=/path/jaas.conf` | **JAAS** | Points to entry/login module/options | **Not** a keytab path |
| `-Djavax.security.auth.useSubjectCredsOnly=true` | **JDK GSS-API** | Restricts GSS credentials to the JAAS `Subject` (standard model) | Does not log in by itself |
| `-Dsun.security.krb5.debug=true` | Java Kerberos debug | Traces Kerberos/KDC details for troubleshooting | Never leave on long-term in production |
| `KRB5_CONFIG` | **MIT Kerberos** libs/tools | Points to krb5.conf for MIT libraries | Do not assume it replaces the Java property |
| `KRB5_KTNAME` | MIT Kerberos/keytab-aware tools | Default MIT keytab location | Never assume it overrides Java JAAS `keyTab` |
| `KRB5CCNAME` | MIT Kerberos client tools | Default ticket cache (e.g. `FILE:/run/...`) | Java JAAS has its own `ticketCache` |
| `-Djava.security.krb5.realm` and `.kdc` | JDK Kerberos | Defines realm/KDC directly; both must be set together if used | Unnecessary when using a proper krb5.conf |

**Crucial distinction:** Running `kinit`/`klist` successfully in a shell verifies only **MIT Kerberos tools** and that environment's filesystem/network. It **does not guarantee** the Java process reads the same krb5.conf, the same ticket cache, uses the same service principal, or has the same file permissions. Use explicit Java system properties/JAAS to eliminate ambiguity.

### 6.1. Choose useSubjectCredsOnly Deliberately

JDK GSS-API normally uses a JAAS `Subject` holding credentials. When `javax.security.auth.useSubjectCredsOnly=true`, the app logs in via `LoginContext`/JAAS framework and runs GSS operations inside that subject. When set to `false`, JGSS can search for credentials **outside the Subject** (e.g., default ticket cache). That helps certain HTTP/SPNEGO client integrations, yet can expose unexpected credential sources.

**Do not treat `-Djavax.security.auth.useSubjectCredsOnly=false` as a "magic Kerberos fix" for every service.** First determine whether the app runs as an acceptor or initiator, who manages the Subject, which keytabs/ticket caches exist, and whether the framework already creates a login context. Oracle's Java 17 HTTP/SPNEGO guide shows `false` for clients using the OS ticket cache, not as a universal security default for servers using dedicated keytabs.

### 6.2. JAAS Config Single vs. Double Equals Sign

The JAAS Reference Guide distinguishes:
- `-Djava.security.auth.login.config=/etc/kerberos/jaas.conf`: specifies a URL/path that may be combined with `java.security` config sources per default provider behavior.
- Using `==` in the assignment (e.g. `-Djava.security.auth.login.config==/path`) **overrides** the set of JAAS configuration URLs instead of appending.

For new deployments, manage config sources explicitly; never swap syntax randomly without knowing whether the environment loads other JAAS configs from JVM security properties. Avoid editing `$JAVA_HOME/conf/security/java.security` globally on nodes just for one app.

## 7. Secret Paths: Never Put Keytabs in Source Code

**Recommended Linux/container layout:**

~~~text
/etc/kerberos/
    krb5.conf                 # non-secret topology config, admin-owned
    jaas.conf                 # config, contains ABSOLUTE keytab paths

/run/secrets/kerberos/
    http-portal.keytab        # secret SPNEGO ACCEPTOR
    svc-reader.keytab         # secret CLIENT INITIATOR, if needed

/run/kerberos/ccache/
    svc-reader.ccache         # short-lived ticket cache, if used
~~~

Never place keytabs in:
- `src/main/resources`, `classpath`, JAR/WARs, Docker build contexts, or container image layers;
- Git repositories (even "private repos"), Git history, or CI build artifacts;
- `application.yml` as base64, Kubernetes ConfigMaps, literal Helm values, or inline secrets;
- stdout/stderr, exception messages, debug logs, APM traces, request headers, tickets/chat, wikis, or emails;
- Public shared volumes or `/tmp` without proper permissions/cleanup;
- Paths chosen by users from HTTP queries/forms/headers.

### 7.1. Least Privilege on Linux

On a test machine/VM with a standard filesystem, once the secret provisioner creates the keytab:

~~~bash
# Example admin action in an approved environment.
sudo chown kerberos-app:kerberos-app \
    /run/secrets/kerberos/http-portal.keytab
sudo chmod 0400 \
    /run/secrets/kerberos/http-portal.keytab

# Inspect file metadata only, DO NOT inspect bytes:
stat -L -c '%a %U %G %n' \
    /run/secrets/kerberos/http-portal.keytab

# Verify under the exact JVM UID/GID:
sudo -u kerberos-app sh -c \
    'test -r /run/secrets/kerberos/http-portal.keytab && echo READABLE || echo DENIED'
~~~

**Note:** `0400` grants read access only to the owner; with projected secret volumes often owned by root while the app runs as another UID, `0400` can fail. When using a group-mounted secret, consider `0440` + matching GID in the pod, never `0644`/`0777`. Traversal/write permissions on parent directories matter; a secret file must not be replaceable via symlink from an attacker-writable directory.

**Separation of privileges:**
- Portal acceptor needs only **http-portal.keytab**.
- Java backend callers need only **svc-reader.keytab** or their own cache.
- CI builds/tests do not need production keytabs; unit tests use fake/mock paths.
- Only Identity/Security custodians may create/rotate/revoke service principal keys.
- Break-glass SRE access requires approval, MFA, TTL, and audit; never grant permanent access across all tenants/envs.
- Never share production keytabs with staging, dev, or individual users.

### 7.2. Keytab State and File Contents

A keytab is a **binary** file holding one or more principal/enctype/KVNO entries. It is a stealable credential even though it contains no plaintext password. Never run `cat`, `base64`, `xxd`, or `strings` to "debug" a keytab and paste results into chat.

Use MIT tooling in an authorized environment to **list metadata**:

~~~bash
klist -k -e /run/secrets/kerberos/http-portal.keytab
~~~

`klist -k -e` typically prints principals, KVNOs, and encryption types **without printing raw key material**, though principal lists can still be topology-sensitive and should not enter broad-access logs. Never pass key-printing flags if supported by the tool/version.

Verify:
- Exact principal: `HTTP/portal.example.org@EXAMPLE.ORG`.
- KVNO matches current KDC/AD.
- Enctypes are compatible with KDC, tickets, and JDK cryptographic policy.
- New secret version is distributed uniformly across all nodes.
- File has the right UID/GID/mode and valid binary format, not an accidentally mounted base64/text string.

### 7.3. Ticket Cache

If an initiator acquires a TGT via cache:
- Place it in a private app-owned runtime directory, mode `0600` on the file where possible.
- Set `ticketCache=...` explicitly in JAAS so Java JDK reads the exact file.
- With MIT tools, `KRB5CCNAME=FILE:/run/kerberos/ccache/svc-reader.ccache` works, yet never assume Java JAAS uses that same environment variable.
- When manually testing `kinit`, ensure credentials/TGTs are not written to a world-readable cache or shared across apps/tenants.
- Define ticket renewal/expiration, logout/cleanup, and crash/restart handling. Never "fix" an expired TGT by disabling lifetime checks.

## 8. Containers and Kubernetes: Mount Keytabs, Never Bake Them

In Kubernetes, secrets can be supplied via Kubernetes Secret volumes or CSI integration with an external secret manager. **Kubernetes Secret base64 is encoding, not encryption**, so enable **encryption at rest** for etcd and enforce RBAC/admission/network policies; with CSI, verify Secret sync mechanisms, rotation, ownership/permissions, and access by privileged pods.

### 8.1. Illustrative Pod Template (Not a Complete Deployment)

~~~yaml
spec:
  serviceAccountName: kerberos-portal
  automountServiceAccountToken: false
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001
  containers:
    - name: portal
      image: registry.example.org/portal:1.0.0
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
      env:
        - name: JAVA_TOOL_OPTIONS
          value: >-
            -Djava.security.krb5.conf=/etc/kerberos/krb5.conf
            -Djava.security.auth.login.config=/etc/kerberos/jaas.conf
      volumeMounts:
        - name: kerberos-keytab
          mountPath: /run/secrets/kerberos
          readOnly: true
        - name: kerberos-config
          mountPath: /etc/kerberos
          readOnly: true
  volumes:
    - name: kerberos-keytab
      secret:
        secretName: portal-kerberos-keytab
        defaultMode: 0440
    - name: kerberos-config
      configMap:
        name: portal-kerberos-config
        defaultMode: 0444
~~~

**Explanation:** Secret/ConfigMap names are **references**, containing no keytab bytes in this YAML. `portal-kerberos-keytab` must be provisioned via a controlled channel; `portal-kerberos-config` holds approved `krb5.conf` and `jaas.conf`. `fsGroup` can grant UID 10001 access to group-readable volumes if supported by the volume provider; different CSI drivers may not apply ownership as expected. Run `stat -L` and `test -r` **inside the Pod under the exact UID/GID**, never making files world-readable.

**Adjustments to consider:**
- When an app needs the Kubernetes API or CSI workload identity, `automountServiceAccountToken: false` may not apply; use token projection/Audience/TTL and least privilege. Never blindly toggle settings without checking the provider.
- `readOnlyRootFilesystem=true` may require separating `/tmp`, JVM caches, ticket caches, and logs into bounded writable volumes. An acceptor using only a keytab generally needs no writable ticket cache, though the Java runtime may still require temp files depending on the app.
- Every node/pod must hold the matching keytab version and public DNS/hostname mapping; the load balancer hostname is the public SPN, **never derive the SPN from the Pod name**.
- Restrict edit permissions on Helm ConfigMaps, Java options, and resource names; anyone altering JAAS/krb5.conf could redirect the process to another keytab or untrusted KDC.
- A privileged pod or node root can read mounted keytabs even when the app runs non-root. File modes help constrain exposure but do not replace cluster security, host isolation, and RBAC.

### 8.2. Why Not Mount a Keytab via Environment Variable?

A binary keytab is not a natural environment variable string. Putting a base64 keytab into an env var and decoding at startup creates extra leak vectors (shell history, command-line args, process environment, crash diagnostics, logs, tmp files). **Prefer a secret volume/read-only file** or a supported, audited Kerberos provider. JAAS `keyTab=...` expects a concrete file path.

### 8.3. Does Dynamic Secret Rotation Auto-Reload?

**Not by default.** When Secret/CSI updates the mounted file, an already-initialized Spring Kerberos validator/JAAS Subject/GSS credential may continue holding old keytab handles/keys/cached state. Java offers `refreshKrb5Config=true` to refresh **Kerberos config before JAAS login**, yet **it does not guarantee** keytabs, Subjects, or Spring authentication providers reload cleanly.

Plan rolling restarts or controlled credential refreshes per library capabilities, using overlapping keys/KVNOs when Identity/KDC policy allows. Test with real SPNEGO tickets **before and after** rotation.

## 9. SPN, Realm, DNS, and Reverse Proxy Must Align

When browsers access public URL `https://portal.example.org`, the client normally requests a service ticket for `HTTP/portal.example.org@EXAMPLE.ORG`. The Java server's Kerberos keytab must contain the key for that exact SPN.

**Failure example:**

~~~text
Browser URL = https://portal.example.org
Expected SPN = HTTP/portal.example.org@EXAMPLE.ORG
Keytab actually contains = HTTP/node-1.internal@EXAMPLE.ORG

Result: acceptor cannot decrypt/validate ticket for requested SPN.
~~~

Behind a load balancer:
- Each node can share the same logical service SPN keytab via controlled secret provisioning, or use an appropriate centralized design.
- Never register one HTTP SPN on multiple arbitrary AD accounts, causing duplicate/ambiguous SPNs and key mismatches.
- TLS termination at the LB does not make Kerberos service tickets valid automatically; the SPNEGO server still needs the right principal/key.
- If a proxy rewrites `Host`/redirects schemes, verify the principal hostname. Kerberos authentication does not protect an arbitrary forwarded-user header from a misconfigured proxy.
- If the reverse proxy terminates Kerberos itself and forwards identity to the app, that is **a separate proxy trust-delegation architecture**. The backend must authenticate the channel/mTLS, strip forged headers, and enforce explicit policy; never assume both proxy and app act as acceptors simultaneously.

### 9.1. HTTP 401 Negotiate Differs from Basic

A typical SPNEGO login:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

Once the browser obtains a ticket, it sends:

~~~http
GET /private HTTP/1.1
Host: portal.example.org
Authorization: Negotiate <opaque-token>
~~~

`<opaque-token>` is illustrative data, not a real token. **Never log Authorization header values.** After Java/Spring verifies the token and loads user authorities, the application returns `200` or `403` depending on authorization. A valid SPNEGO token never implies the user holds `ROLE_ADMIN`.

### 9.2. Checking the Principal Received After Authentication

Kerberos `lan@EXAMPLE.ORG` is an authenticated principal. The application must verify:
- Is the user active/unlocked in the internal account directory?
- Does the principal belong to the expected realm/tenant? Does cross-realm trust need special mapping?
- Is the user authorized to view the resource? Are object-level/row-level ownership and group/role mappings approved?
- Does the application session have appropriate timeouts/reauthentication?
- Does app logout clear only the local session? Because the browser still holds a domain TGT, it **can auto-SSO again immediately**.

Never trust a principal self-reported by the frontend or taken from an unauthenticated HTTP header.

## 10. Spring Security Kerberos: Integrating with JAAS/Keytab in the Right Role

Spring Security **Kerberos** is an extension/integration providing components such as:

- `SpnegoAuthenticationProcessingFilter`: reads `Authorization: Negotiate ...` and constructs the authentication request.
- `SpnegoEntryPoint`: when unauthenticated, triggers SPNEGO negotiation (`WWW-Authenticate: Negotiate`), optionally forwarding to a fallback login page per configuration.
- `KerberosServiceAuthenticationProvider`: verifies service tickets/SPNEGO tokens using `KerberosTicketValidator`, then loads user/authorities via `UserDetailsService`.
- `SunJaasKerberosTicketValidator`: JDK/JAAS-based validator implementation requiring **servicePrincipal** and **keyTabLocation**.
- `AuthenticationManager`/`SecurityFilterChain`: wires providers/filters and enforces authorization.
- `KerberosAuthenticationProvider`/`SunJaasKerberosClient`: a separate branch for client Kerberos authentication, not a replacement for the service-ticket acceptor.

**Compatibility warning:** There is no simple Spring Boot core property named `spring.security.kerberos.enable=true` that sets up full Kerberos/SPNEGO. You must add a **Spring Security Kerberos** module/library version compatible with your Spring Security/Spring Boot release and configure beans, KDC/AD, and keytabs. Never assume from Spring Security 6.5 that every Spring Security Kerberos 2.x API will compile cleanly without checking the dependency tree.

### 10.1. Bean Configuring Keytab/Service Principal (Illustrative)

This is a **Spring configuration fragment**, not a complete application: you need compatible `spring-security-kerberos` dependencies, `UserDetailsService`, `AuthenticationManager`, `SecurityFilterChain`, SPNEGO filter/entry point, and full authorization.

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;

@Configuration
public class KerberosBeans {

    @Bean
    SunJaasKerberosTicketValidator kerberosTicketValidator(
            @Value("${app.kerberos.service-principal}") String principal,
            @Value("${app.kerberos.keytab-location}") String keytabPath) {

        SunJaasKerberosTicketValidator v =
                new SunJaasKerberosTicketValidator();
        v.setServicePrincipal(principal);
        v.setKeyTabLocation(new FileSystemResource(keytabPath));
        v.setDebug(false);
        return v;
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosServiceProvider(
            SunJaasKerberosTicketValidator validator,
            UserDetailsService users) {
        KerberosServiceAuthenticationProvider p =
                new KerberosServiceAuthenticationProvider();
        p.setTicketValidator(validator);
        p.setUserDetailsService(users);
        return p;
    }
}
~~~

In `application.yml`, **put only principal/path, NEVER keytab contents**:

~~~yaml
app:
  kerberos:
    service-principal: HTTP/portal.example.org@EXAMPLE.ORG
    keytab-location: /run/secrets/kerberos/http-portal.keytab
~~~

**Explanation:** `FileSystemResource` points to the provisioned binary keytab; the validator verifies browser-sent tickets. `UserDetailsService` must fetch authorities from an approved internal/AD mapping rather than handing `ROLE_ADMIN` to all Kerberos principals. These beans do not register the SPNEGO filter or entry point themselves, so **never copy just these two beans and claim the app has SSO**.

### 10.2. Relationship Between JAAS File and Spring Validator

There are two integration models:

1. **Application-managed JAAS Subject:** code/framework uses `LoginContext("KrbAcceptor")` or the matching JGSS entry, loads credentials, and runs GSS accept operations inside that `Subject`.
2. **Validator-managed JAAS:** `SunJaasKerberosTicketValidator` takes servicePrincipal and keytabLocation, performing login/validation per the Spring Kerberos library implementation.

**Never automatically assume** the Spring validator reads `KrbAcceptor` from `-Djava.security.auth.login.config`. Under model 2, the validator bean itself declares principal/keytab. Keep `krb5.conf` accurate and test the entire flow with a real SPNEGO token.

### 10.3. Preventing "Fallback Bypass" Authentication

If the app offers form login/Basic/OIDC alongside SPNEGO, design filter-chain and route policies carefully:
- Specify which endpoints use SPNEGO and which use fallback.
- Never let a `permitAll` filter chain accidentally expose `/private`.
- Never treat `Authorization: Negotiate` as merely a Base64 username; require ticket validation.
- Never "fail open" when KDC/JAAS/keytab fails; unauthenticated users must get 401/deny per policy.
- Never use a browser's Kerberos ticket as an OAuth Access Token to call another API; use proper token exchange or protocol-compliant service delegation.

## 11. Standalone Java 17: Checking Path/Role Layout Before Deployment

The following example is **a real Java 17 program compiling/running without KDC or keytab**, enforcing **configuration policy**: the service acceptor maps only to its exact principal/path, and the initiator maps only to its exact principal/path; it **does not read secret files** and **does not verify Kerberos tickets**.

**File `Krb5PathPolicyDemo.java`:**

~~~java
import java.util.Map;

public class Krb5PathPolicyDemo {
    record Policy(String principal, String keytab) {}

    static final Map<String, Policy> APPROVED = Map.of(
        "ACCEPTOR",
            new Policy("HTTP/portal.example.org@EXAMPLE.ORG",
                       "/run/secrets/kerberos/http-portal.keytab"),
        "INITIATOR",
            new Policy("svc-reader@EXAMPLE.ORG",
                       "/run/secrets/kerberos/svc-reader.keytab")
    );

    static final String JAAS =
        "/etc/kerberos/jaas.conf";
    static final String KRB5 =
        "/etc/kerberos/krb5.conf";

    static String check(String role, String principal,
                        String keytab, String jaas, String krb5) {
        Policy approved = APPROVED.get(role);
        if (approved == null) {
            return "DENY_ROLE";
        }
        if (!approved.principal().equals(principal)) {
            return "DENY_PRINCIPAL";
        }
        if (!approved.keytab().equals(keytab)) {
            return "DENY_KEYTAB";
        }
        if (!JAAS.equals(jaas) || !KRB5.equals(krb5)) {
            return "DENY_CONFIG_PATH";
        }
        return "ALLOW_LAYOUT";
    }

    static void show(String name, String role,
                     String principal, String keytab,
                     String jaas, String krb5) {
        System.out.println(name + "=" +
            check(role, principal, keytab, jaas, krb5));
    }

    public static void main(String[] args) {
        String acceptor = "HTTP/portal.example.org@EXAMPLE.ORG";
        String initiator = "svc-reader@EXAMPLE.ORG";
        String httpKey =
            "/run/secrets/kerberos/http-portal.keytab";
        String clientKey =
            "/run/secrets/kerberos/svc-reader.keytab";

        show("acceptor", "ACCEPTOR",
             acceptor, httpKey, JAAS, KRB5);
        show("initiator", "INITIATOR",
             initiator, clientKey, JAAS, KRB5);
        show("wrongPrincipal", "ACCEPTOR",
             "HTTP/evil.example.org@EXAMPLE.ORG", httpKey, JAAS, KRB5);
        show("wrongKeytab", "ACCEPTOR",
             acceptor, clientKey, JAAS, KRB5);
        show("wrongJaAs", "ACCEPTOR",
             acceptor, httpKey, "/tmp/jaas.conf", KRB5);
        show("unknownRole", "UNKNOWN",
             acceptor, httpKey, JAAS, KRB5);
    }
}
~~~

**Run with JDK 17+:**

~~~bash
javac Krb5PathPolicyDemo.java
java Krb5PathPolicyDemo
~~~

**Exact stdout:**

~~~text
acceptor=ALLOW_LAYOUT
initiator=ALLOW_LAYOUT
wrongPrincipal=DENY_PRINCIPAL
wrongKeytab=DENY_KEYTAB
wrongJaAs=DENY_CONFIG_PATH
unknownRole=DENY_ROLE
~~~

Explanation:
- `ACCEPTOR` requires `HTTP/portal.example.org@EXAMPLE.ORG` and the matching HTTP service keytab.
- `INITIATOR` is a separate principal with its own keytab and must never use the acceptor keytab.
- A wrong principal or wrong path is rejected by policy right at config review.
- String path comparison in this demo **does not prevent symlinks/TOCTOU, mount injection, or host permission flaws**. This is illustrative config checking only; production must enforce realpath/secure mounts, IAM, pod admission, and file ownership validation.
- The program does not generate keytabs, read credentials, contact a KDC, or prove SPNEGO login works. Verifying real Kerberos requires running the `LoginContext`/GSS probe in the next section.

## 12. Java 17 Integration Probe: LoginContext Acceptor

This snippet **actually invokes JAAS** and requires a valid keytab/principal/Kerberos config. It compiles on plain JDK 17, **yet passes only in an environment provisioned with the right keytab**. There is no fixed stdout when credentials are absent; errors must be logged at metadata level without printing keys.

**File `KerberosAcceptorProbe.java`:**

~~~java
import javax.security.auth.Subject;
import javax.security.auth.kerberos.KerberosPrincipal;
import javax.security.auth.login.LoginContext;

public class KerberosAcceptorProbe {
    public static void main(String[] args) throws Exception {
        LoginContext context = new LoginContext("KrbAcceptor");
        context.login();
        try {
            Subject subject = context.getSubject();
            String required =
                "HTTP/portal.example.org@EXAMPLE.ORG";
            boolean principalMatches =
                subject.getPrincipals(KerberosPrincipal.class)
                       .stream()
                       .anyMatch(p -> p.getName().equals(required));

            if (!principalMatches) {
                throw new IllegalStateException(
                    "JAAS principal does not match approved SPN");
            }

            System.out.println("ACCEPTOR_JAAS_LOGIN=PASS");
            System.out.println("SERVICE_PRINCIPAL_MATCH=PASS");
            System.out.println("PRIVATE_CREDENTIALS_PRINTED=false");
        } finally {
            context.logout();
        }
    }
}
~~~

Compile:

~~~bash
javac KerberosAcceptorProbe.java
~~~

Run **only on a test VM/container with matching JAAS/KDC/keytab files**:

~~~bash
java \
  -Djava.security.krb5.conf=/etc/kerberos/krb5.conf \
  -Djava.security.auth.login.config=/etc/kerberos/jaas.conf \
  KerberosAcceptorProbe
~~~

If acceptor login succeeds with the right principal, stdout:

~~~text
ACCEPTOR_JAAS_LOGIN=PASS
SERVICE_PRINCIPAL_MATCH=PASS
PRIVATE_CREDENTIALS_PRINTED=false
~~~

If the keytab is missing, unreadable, or lacks the matching principal, `LoginContext.login()` throws `LoginException`. **Never** hardcode passwords/tickets to fake PASS, never catch exceptions to return 200, and never print `Subject.getPrivateCredentials()`. A passing JAAS login proves the acceptor can load credentials, **not browser SPNEGO negotiation, KDC ticket issuance, or Spring Security authorization**: real HTTP integration tests are still required.

## 13. Verifying from OS and KDC Using Approved Tools

### 13.1. Checking the Filesystem Without Exposing Secrets

~~~bash
# Use the exact runtime user; never use root to infer app permissions.
id

stat -L -c '%a %u %g %n' \
  /run/secrets/kerberos/http-portal.keytab

if test -r /run/secrets/kerberos/http-portal.keytab; then
  printf '%s\n' 'KEYTAB_READABLE_BY_RUNTIME=PASS'
else
  printf '%s\n' 'KEYTAB_READABLE_BY_RUNTIME=FAIL'
fi
~~~

`test -r` checks read permission only for the current process; it does not prove valid keytab contents, a trusted source, or that the KDC can issue tickets. `stat -L` dereferences symlinks on projected volumes; inspect both mount source and path ownership.

### 13.2. Checking Keytab Metadata

~~~bash
# Run only in an authorized environment; avoid saving output to shared logs.
klist -k -e /run/secrets/kerberos/http-portal.keytab
~~~

Cross-check SPN, KVNO, and enctypes; **never run** commands that dump raw keys. For an authorized test initiator, you can run:

~~~bash
# Example for a client/sandbox principal ONLY; DO NOT use on real user accounts.
export KRB5_CONFIG=/etc/kerberos/krb5.conf
export KRB5CCNAME=FILE:/run/kerberos/ccache/svc-reader.ccache

kinit -k -t /run/secrets/kerberos/svc-reader.keytab \
  svc-reader@EXAMPLE.ORG

klist
# After testing, clean up the cache per policy:
kdestroy
~~~

**Common pitfall:** `kinit` here fetches a TGT using the service-client keytab to test the KDC; it does not replace the JAAS acceptor and does not represent user Lan. MIT tools read `KRB5_CONFIG`/`KRB5CCNAME`; JDK Java still needs explicit `java.security.krb5.conf`/`ticketCache` checks.

### 13.3. Network, DNS, and Clocks

- Verify DNS resolution of `kdc1.example.org` and `portal.example.org` from the exact Pod/VM.
- Verify connectivity to KDC TCP/UDP 88 and required AD/DNS services; never open network firewalls cluster-wide.
- Synchronize clocks across browser/client, KDC, and server via NTP/PTP or equivalent. Kerberos enforces clock skew limits; "Clock skew too great" is an authentication error, never fixed by disabling timestamp checks.
- Confirm the SPN in AD/KDC belongs to the right service account without duplicates, and keytab KVNO/enctypes are updated whenever keys rotate.
- With CNAMEs or cross-domain trust, test the exact canonical hostname browsers put in the HTTP URL.

### 13.4. End-to-End HTTP/SPNEGO Testing

In a domain-joined test environment with a browser configured to allow Integrated Authentication to Portal, opening `/private`:

1. Receives `401 WWW-Authenticate: Negotiate`.
2. Browser requests a service ticket for `HTTP/portal.example.org` from the KDC.
3. Sends `Authorization: Negotiate ...` (opaque token).
4. Spring Security Kerberos validator/JGSS uses the keytab to accept the service ticket.
5. App maps the verified token's principal to an internal user/authorities.
6. Authorized users receive 200; authenticated users lacking permissions receive 403.

Never run `curl -H 'Authorization: Negotiate blah'` and claim Kerberos ought to accept it; fake tokens must be rejected. If using curl compiled with GSS-API, try `--negotiate -u :` in an environment with a valid user ticket cache, keeping in mind **curl behavior is not equivalent** to browser SPNEGO policies and Java JAAS Subjects.

## 14. Keytab Generation and Rotation: Identity Team Responsibility

SPN keytabs must be issued through an approved Kerberos/AD workflow; applications should never self-generate keytabs/passwords from user input.

**Standard provisioning sequence:**

1. Pin the exact service principal, e.g., `HTTP/portal.example.org@EXAMPLE.ORG`, and a least-privilege service account owner.
2. Registry/AD admins verify **SPN uniqueness** and allowed cryptographic algorithms per KDC policy.
3. The identity team creates/exports the keytab for the principal using approved tooling, recording KVNO/enctypes and secret version.
4. Store the binary keytab in a secret manager/secured artifact transfer with encryption at rest/in transit and auditing; never send via email/tickets or commit to Git.
5. Provision to the target VM/Pod at the path configured in JAAS/Spring, readable only by the runtime identity.
6. Verify metadata via `klist -k -e` in a restricted environment; test `LoginContext` and HTTP/SPNEGO integration.
7. During key rotation, track the new KVNO and overlap behavior: depending on KDC/AD policy, old keys may stop working immediately on password change. Never promise old/new keytabs always run side by side.
8. Execute a controlled rollout while monitoring 401/GSS errors; retire/clean up old keytabs, backups, and pod images/caches per policy.
9. If a keytab leaks, treat it as a **service credential compromise**: rotate/revoke keys, investigate impersonated principals/targets, and perform audit and policy remediation. Deleting the file from Git does not invalidate old keys.

### 14.1. Never Change the SPN Only by Editing JAAS

Changing `principal="HTTP/new-host.example.org@EXAMPLE.ORG"` in JAAS **does not create a new SPN in the KDC** or update the keytab. Coordinate all layers: public DNS/URL, KDC SPN registration, keytab, app configs, browsers, and reverse proxies.

### 14.2. Never Assume "Secret Mount Auto-Rotated" Means the JVM Picked It Up

An application may initialize its Kerberos ticket validator once at startup. Even if a secret volume symlink points to a new keytab, the Java `Subject` or GSS credentials may be cached. Test rolling restarts/re-initialization per framework; never rely solely on disk file replacement to claim the live runtime uses the new key.

## 15. Troubleshooting by Symptom

| Error / Symptom | Likely Cause | Right Remediation |
| --- | --- | --- |
| `Cannot locate KDC` / `Cannot find KDC for realm` | Wrong `krb5.conf`, realm, DNS, or unreachable KDC | Check `-Djava.security.krb5.conf`, TCP/UDP 88 networking, realm case |
| `Server not found in Kerberos database` | Unregistered SPN, wrong FQDN, or wrong realm mapping | Check HTTP SPN, canonical URL, and AD/KDC registry |
| `KRB_AP_ERR_MODIFIED` | Keytab lacks matching key, wrong KVNO, duplicate SPN, or encryption mismatch | Cross-check SPN/KVNO/enctype/keytab version; never disable validation |
| `Clock skew too great` | Time drift across systems | NTP/time sync; never loosen time checks indiscriminately |
| `Unable to obtain password from user` | `doNotPrompt=false`/missing keytab falling back to prompt | Supply valid keytab, set `doNotPrompt=true`, check file permissions |
| `No valid credentials provided` / `Failed to find any Kerberos tgt` | Wrong initiator Subject/cache or expired TGT | Distinguish initiator/acceptor, inspect ticketCache/JAAS config and TTL |
| `No key to decrypt ticket` | Wrong acceptor keytab/SPN/KVNO/enctype | Check approved SPN, keytab entries, and runtime path |
| `Krb5LoginModule not found/config entry missing` | Wrong JAAS name/property or JDK module/config unread | Check `java.security.auth.login.config` and entry names |
| `LoginException: Unable to obtain Principal Name` | Missing principal declaration, non-interactive prompt | Declare full principal and verify JAAS syntax |
| `Permission denied` reading keytab | Wrong mount owner/mode/UID/GID | Fix secret provisioning; never run chmod 777 |
| `401 loop` in Browser | Browser omits Negotiate, wrong SPN, GSS validation fails | Check WWW-Authenticate/Authorization (without logging tokens), browser zone, SPN |
| HTTP 401 because browser skips Integrated Authentication | Browser/client lacks TGT, site policy blocks delegation | Check browser allowlist/OS login; never weaken security |
| HTTP 403 after Negotiate | Authenticated yet app authorization denies | Check user enabled/roles/tenant/resource; do not edit keytab |
| Works on host, fails in Pod | Different krb5.conf/keytab mount, DNS/KDC blocked, wrong hostname/cert/path | Verify container UID, pod DNS/network, and JVM flags |
| Fails on only one Pod | Different KVNO/secret version, stale validator/cache | Compare rollouts/secret mounts, restart plan, HA |
| MIT `kinit` OK yet Java fails | JDK reads different config/cache, wrong JAAS principal | Set explicit Java system properties, run `LoginContext` probe |
| After rotation all SPNEGO fails | New AD keytab not deployed or old key invalidated | Check KDC KVNO/keytab, synchronize rollout |
| Excessive debug logs/tokens | `debug=true` or `sun.security.krb5.debug` left enabled | Disable production debug, purge logs per incident policy |
| Cross-realm login rejected | Trust/referrals/realm config or tenant mapping | Review KDC trust, allowed realms/user authorization |

**Effective diagnostic flow:** Host URL/SPN → `krb5.conf`/realm/KDC/DNS/time → JAAS entry/name/options → keytab path+owner/mode → keytab principal/KVNO/enctype → JDK Subject/GSS behavior → Spring SPNEGO filter/provider → user/tenant authorization. Never fix role errors by disabling Kerberos validation, and never fix DNS issues by accepting arbitrary ticket issuers.

### 15.1. Where to Enable Debug?

There are two layers:
- JAAS `Krb5LoginModule debug=true`.
- JDK `-Dsun.security.krb5.debug=true` (plus version-specific GSS debug flags).

Enable only temporarily in a **sandbox**, keeping logs restricted and purged per retention policy. Kerberos debug output can expose realms/principals, ticket metadata, network addresses, and sensitive contexts. Never print raw `Authorization: Negotiate`/ticket data or keytab bytes to debug issues.

## 16. Testing and QA Criteria

| Scenario | Expected Result |
| --- | --- |
| Valid acceptor keytab SPN, readable, valid JAAS | `LoginContext("KrbAcceptor")` passes in test environment |
| Valid HTTP SPNEGO token for Portal | Spring authenticates user then enforces authorization |
| Missing/unnegotiated HTTP token | 401 + Negotiate challenge or approved fallback flow |
| Fake Base64 HTTP token | Rejected; no authenticated principal created |
| Token signed for another SPN | Rejected at GSS validation |
| Untrusted realm/issuer | Rejected or KDC referral per policy, no auto-trust |
| Wrong/missing keytab path | Fails closed, no password prompt fallback |
| World-readable keytab | Deployment security policy FAILS, even if login works |
| App UID cannot read keytab | Clear startup/auth failure, never chmod 777 |
| `isInitiator=false` on acceptor | Loads service key for accept ops, needs no user TGT |
| Initiator keytab swapped for HTTP keytab | Rejected due to principal mismatch / wrong credentials |
| `doNotPrompt=true` with no credential source | Fails without prompting |
| `ticketCache` set with `useTicketCache=false` | Invalid/failing JAAS config |
| `renewTGT=true` with `useTicketCache=false` | Invalid/failing JAAS config |
| Expired/missing initiator TGT | Fails or re-logs in per policy, never uses stale cache |
| Wrong DNS/KDC | Login fails, alerts on config/network |
| High time skew | Kerberos rejects; requires clock sync |
| Reverse proxy uses internal hostname | SPN mismatch; fix public hostname/registration |
| Pod A old keytab version, Pod B new | Drift caught pre-rollout, no random 401s |
| Post-rotation new keytab | SPNEGO passes after verified restart/refresh |
| Authenticated user lacking app permission | 403, not 200 just because Kerberos ticket passed |
| Secret in debug/CI/logs/image | QA FAILS and triggers leak incident response |
| App logout while browser still holds domain TGT | Immediate re-SSO possible; UX documents scope accurately |

### 16.1. Test Layers

1. **Static config QA:** inspect Java flags, JAAS syntax, principal/path, `krb5.conf` mappings, secret path allowlist, and file ownership. Run `Krb5PathPolicyDemo`.
2. **JAAS integration:** run `KerberosAcceptorProbe` on a sandbox Pod/VM with a keytab, verifying no private credentials print.
3. **KDC integration:** run approved tests with MIT tooling/Java GSS, checking hostname/SPN/KVNO/time.
4. **HTTP browser E2E:** test real Negotiate handshakes, authorized/unauthorized users, direct/aliased URLs, and reverse proxies.
5. **Ops/chaos:** KDC failover, unavailable secret mount, bad keytab, expired cache, rolling rotation, and version-skewed nodes.
6. **Security regression:** block arbitrary Host/tenant keytab selection, block public secret mounts, no plaintext token logging, and no fallback auth bypass.

**Test the right root cause:** Changing the service principal in JAAS without updating the keytab only tests mismatch, not DNS mapping. Flipping Kerberos token bytes only tests integrity; to test authorization, use a valid principal **lacking permission** and verify 403.

## 17. Production Checklist

- [ ] Approved list of realms/KDCs documented; `krb5.conf` matches environment and network reachability.
- [ ] Browser public hostname, Kerberos HTTP SPN, keytab, and reverse proxy align.
- [ ] JAAS acceptor: `useKeyTab=true`, `storeKey=true`, `isInitiator=false`, `doNotPrompt=true`, fixed principal.
- [ ] JAAS initiator (if any) uses its own service identity/keytab or ticket cache, never the HTTP acceptor keytab.
- [ ] Java flags explicitly set JAAS and krb5.conf files; difference from MIT environment variables understood.
- [ ] Binary keytabs absent from Git, images, ConfigMaps, application.yml, stdout, logs, and unprotected backups.
- [ ] Keytab volume is read-only with proper UID/GID/mode; Pod exec, host/root access, cluster RBAC, and etcd encryption reviewed.
- [ ] JAAS/krb5.conf cannot be modified by untrusted users to point at another keytab/KDC.
- [ ] `SunJaasKerberosTicketValidator`/SPNEGO filter/provider versions match the active Spring Security baseline.
- [ ] Fails closed on invalid keytab/KDC/tickets; never authenticates from raw usernames/headers.
- [ ] UserDetailsService/authorization enforces active accounts, realm/tenant, authorities, and resource ownership.
- [ ] NTP/DNS/KDC port 88, SPN uniqueness, KVNO/encryption types, and cross-realm policy tested.
- [ ] Rotation covers secret versioning, rollout/restart plan, KDC coordination, and incident runbook.
- [ ] Debug disabled after testing; logs/traces/APM scrub raw Authorization Negotiate headers and credentials.
- [ ] Tested 401/403, wrong keytab, wrong SPN, expired TGT, pod failover, and secret permission denial.

## 18. Exercises and Guided Answers

**Exercise A — Reading three file types.** Given `krb5.conf`, `jaas.conf`, and `http.keytab`, state which configures KDC/realm, which defines JAAS modules, and which holds the long-term service key. Why is setting `chmod 600` on `krb5.conf` while leaving the keytab `0644` unsafe?

**Exercise B — Role separation.** Portal accepts browser SPNEGO via `HTTP/portal.example.org`, while Report Client uses `svc-reader` to request tickets for `HTTP/reports.example.org`. Pick the right `isInitiator` and keytab for each role. Why must Portal's acceptor keytab not be used to "impersonate users" when calling Reports?

**Exercise C — Java 17.** Run `Krb5PathPolicyDemo.java` and verify the 6 lines of stdout. Change one keytab path to `/tmp/http.keytab`, explain why `DENY_KEYTAB` triggers, and state this unit test's limitations.

**Exercise D — JAAS integration.** In an org-provisioned sandbox with a keytab, run `KerberosAcceptorProbe.java` with `-Djava.security.krb5.conf` and `-Djava.security.auth.login.config`. Verify passing stdout and expected failure when changing the principal (in sandbox only), without printing private credentials.

**Exercise E — Kubernetes.** Pod UID 10001 mounts a keytab owned by root with mode `0400` and cannot read it. Propose proper ownership/group access, verify with `stat -L`/`test -r`, and explain why `0644` is unacceptable.

**Exercise F — KDC/AD.** After rotating the service account password, `KVNO` increments while Pods still mount the old keytab. Explain why `KRB_AP_ERR_MODIFIED` can appear and outline a coordinated rollout plan.

**Exercise G — SPNEGO 401 error.** A domain-joined browser does not send `Authorization: Negotiate`. Check browser allowlist, public Host, TLS, KDC, and SPN; distinguish a missing ticket from a Spring 403 authorization error.

**Exercise H — Sessions and delegation.** Browser user Lan logged in with Kerberos; a Java service calls an API using `svc-reader.keytab`. Is it "calling on Lan's behalf"? Not automatically: the backend Kerberos identity is the service account; impersonating Lan requires delegation/constrained delegation or token exchange plus dedicated authorization design.

**Exercise I — Security.** Propose 5 negative tests covering secret path injection, wrong realm/SPN, bad keytab mode, debug leaks, and KDC outage. State the fail-closed behavior for each.

**Exercise J — Comparing MIT and JDK.** Shell `kinit` passes using `KRB5_CONFIG`/`KRB5CCNAME`, yet Java fails with a wrong `-Djava.security.krb5.conf`. Why does Java still fail? How do you inspect JAAS `ticketCache`/keytab/Subject for the exact JVM?

**Passing criteria:** Independently explain **KDC/realm (`krb5.conf`) + JAAS login options + secret keytab/cache + SPN + Spring SPNEGO validator + application authorization**; configure secure paths, run the Java 17 demo, know when a real KDC is required, and maintain runbooks for permissions, clock skew, SPNs, KVNOs, and rotation.

## 19. Official References

- Oracle Java 17 API – `Krb5LoginModule` options, legal combinations, isInitiator, keyTab, ticketCache: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.security.auth/com/sun/security/auth/module/Krb5LoginModule.html
- Oracle Java 17 – Java Authentication and Authorization Service (JAAS) Reference Guide and login config: https://docs.oracle.com/en/java/javase/17/security/java-authentication-authorization-service-jaas-reference-guide.html
- Oracle Java 17 – HTTP/SPNEGO Authentication, krb5.conf/JAAS/useSubjectCredsOnly: https://docs.oracle.com/en/java/javase/17/security/part-vi-httpspnego-authentication.html
- Oracle Java 17 – JAAS Login Utility and Java GSS API: https://docs.oracle.com/en/java/javase/17/security/use-jaas-login-utility-and-java-gss-api-secure-message-exchanges.html
- Oracle Java 17 – javax.security.auth.kerberos and JGSS: https://docs.oracle.com/en/java/javase/17/docs/api/java.security.jgss/javax/security/auth/kerberos/package-summary.html
- MIT Kerberos – krb5.conf (realms/domain_realm/KDC): https://web.mit.edu/Kerberos/www/krb5-current/doc/admin/conf_files/krb5_conf.html
- MIT Kerberos – User configuration, KRB5_CONFIG/KRB5_KTNAME/KRB5CCNAME: https://web.mit.edu/Kerberos/krb5-latest/doc/user/user_config/kerberos.html
- Spring Security Kerberos – Spring integration, SPNEGO, KerberosServiceAuthenticationProvider, SunJaasKerberosTicketValidator: https://docs.spring.io/spring-security-kerberos/reference/ssk.html
- Spring Security – SPNEGO integration reference: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html
- Kubernetes – Secrets best practices: https://kubernetes.io/docs/concepts/security/secrets-good-practices/
- Kubernetes – Encrypting data at rest: https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/
- OWASP – Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
