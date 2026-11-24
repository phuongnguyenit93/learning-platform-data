# Keytab Rotation, Key Versions, and Handling Key Mismatches in Kerberos/SPNEGO

> **Module:** Spring Security – federation. **Group:** Kerberos Integration. This lesson explains **KVNO**, **keytab**, **service principal**, and **encryption type** when a Spring Security SPNEGO service validates tickets from a Kerberos KDC; how to rotate service keys under control on MIT Kerberos or Microsoft Active Directory; how to update multiple pods/JVMs, protect secrets, and troubleshoot key mismatch errors. The standalone Java 17 code at the end only **simulates** key-matching principles, not a real Kerberos ticket validator. Addresses, accounts, and key labels are illustrative data.

## 1. Scenario: KDC Issues New Tickets While the JVM Holds an Old Keytab

The application accessed at `https://portal.example.org` uses SPNEGO with service principal:

```text
HTTP/portal.example.org@EXAMPLE.ORG
```

The user's browser already holds a TGT and requests a **service ticket** from the KDC for this SPN. The server-targeted portion of the service ticket is encrypted by the KDC using the principal's **long-term service key**. Before rotation, the key has version **KVNO 7**. An administrator rotates the account/principal password or key, causing the KDC to begin issuing new tickets with **KVNO 8**. Meanwhile, Spring Boot JVMs on several pods still mount a keytab containing only key v7.

The browser sends:

```http
GET /dashboard HTTP/1.1
Host: portal.example.org
Authorization: Negotiate BASE64_SPNEGO_TOKEN
```

Lacking the matching secret to decrypt the AP-REQ, the acceptor may return 401 and log `KRB_AP_ERR_MODIFIED`, `Message stream modified`, or a missing key/enctype error. **Do not jump to concluding the user typed the wrong password.** Already-authenticated local sessions may keep running, and browsers holding a cached v7 service ticket may still succeed while the acceptor still holds v7.

### Learning Outcomes

After this lesson, you can:

1. Distinguish KDC, TGT, service ticket, service principal (SPN), keytab, KVNO, enctype, and application sessions.
2. Understand why a keytab with the same KVNO as the KDC but **wrong key bytes** still fails to validate tickets.
3. Inspect keytabs with `klist -k -e`, retrieve service ticket KVNOs with `kvno`, and test decryption with `kvno -k` where supported.
4. Avoid the trap where `kadmin ktadd` rotates the KDC key by default; know when to use `-norandkey` and `-keepold`.
5. Distinguish MIT principals from AD SPN–account mappings, `ktpass`, `msDS-KeyVersionNumber`, and DC replication.
6. Design a v7→v8 rotation across multiple pods, maintaining bounded old+new grace, restarting/reinitializing acceptors, and retiring old keys.
7. Configure JAAS and Spring `SunJaasKerberosTicketValidator` with secure secret paths.
8. Diagnose principal/KVNO/enctype/secret/realm/DNS/clock/proxy failures without failing open.
9. Run the Java 17 demo and verify exact stdout.

## 2. Kerberos/SPNEGO Architecture in Spring Security

```text
User/browser                  KDC or AD Domain Controller
    |                                      |
    | Holds TGT                            |
    | Request TGS for HTTP/portal.example.org |
    |------------------------------------->|
    |<-------------------------------------|
    | Receives service ticket              |
    | (encrypted by service long-term key) |
    v
Authorization: Negotiate <SPNEGO/AP-REQ>
    |
    v
Reverse proxy -> Spring Boot
    |
    v
SpnegoAuthenticationProcessingFilter
    |
    v
KerberosServiceAuthenticationProvider
    |
    v
SunJaasKerberosTicketValidator / JAAS / JGSS
    |
    +-- valid servicePrincipal
    +-- keytab entries (principal/KVNO/enctype/key bytes)
    +-- GSS acceptSecContext + protocol validation
    |
    v
Kerberos-authenticated principal
    |
    v
UserDetailsService -> Spring authorities -> local session
```

An initial 401 response can simply be a **normal HTTP Negotiate challenge**. A failure is confirmed only when the browser sends the expected token yet the server keeps challenging/denying or logs clearly report validator failure.

### 2.1. A Principal Is Not a URL

For `https://portal.example.org/dashboard`, the standard SPN is `HTTP/portal.example.org@EXAMPLE.ORG`, **not** the full URL and without paths. Browsers may canonicalize DNS aliases per OS/realm rules; the service principal keytab must match the **actual name the KDC uses to issue tickets**.

A reverse proxy forwarding to backend `http://portal-pod:8080` does not make the SPN `HTTP/portal-pod`. With a virtual hostname, all pods typically share **the same service identity/keytab** matching the public SPN, unless the Kerberos architecture deliberately splits principals.

### 2.2. Do Not Confuse Keys

| Concept | Where Held | Purpose |
| --- | --- | --- |
| `krbtgt` long-term key | KDC | Issues/verifies TGTs; separate rotation, huge blast radius |
| **Service long-term key** | KDC and acceptor **keytab** | Encrypts/decrypts the service ticket portion meant for the principal |
| Service ticket session key | Kerberos protocol | Protects authenticators/client-service exchanges |
| Spring session cookie/`SecurityContext` | Web application | Stores authentication state post-login; does not change when keytab rotates |

A keytab is not a SAML public certificate or an OAuth client secret. It stores **secret key material** for a Kerberos service principal.

## 3. What Are Keytab and KVNO?

MIT Kerberos defines a keytab as storage for long-term keys belonging to one or more principals. Each entry typically holds **principal, KVNO, encryption type, key bytes, and timestamp**.

**Simulated** output example:

```text
Keytab name: FILE:/run/secrets/kerberos/http.keytab
KVNO Principal
---- -------------------------------------------------------------
   7 HTTP/portal.example.org@EXAMPLE.ORG (aes256-cts-hmac-sha1-96)
   7 HTTP/portal.example.org@EXAMPLE.ORG (aes128-cts-hmac-sha1-96)
   8 HTTP/portal.example.org@EXAMPLE.ORG (aes256-cts-hmac-sha1-96)
   8 HTTP/portal.example.org@EXAMPLE.ORG (aes128-cts-hmac-sha1-96)
```

### 3.1. KVNO Is a Key Version, Not Cryptographic Proof

**Key Version Number (KVNO)** increments when principal/service account keys change. The KDC may issue tickets with version v8; the acceptor needs the matching v8 key.

| KDC Ticket | JVM Keytab | Typical Outcome |
| --- | --- | --- |
| v7 | v7 | Succeeds if secret bytes, enctype/principal match |
| v8 | v7 only | Cannot decrypt new tickets |
| v8 | v7 + v8 | Can accept both new tickets and cached old tickets |
| v8 | file labeled v8 yet wrong secret | Integrity/decryption failure |
| v7 cached | v8 only | Old tickets may be rejected |
| v8 AES256 | v8 AES128 only | May fail for missing key with matching enctype |

**Never manually edit the KVNO number inside a keytab to force a match.** Matching principal/KVNO/enctype still fails if the key was derived from a different password, salt, or account.

### 3.2. Encryption Type (Enctype)

Enctype specifies the algorithm/parameter suite encrypting the ticket:

- `aes256-cts-hmac-sha1-96`
- `aes128-cts-hmac-sha1-96`
- Other AES enctypes when supported by KDC/JVM/clients
- Legacy `arcfour-hmac`/RC4 and `des-cbc-*` must be avoided per security policy

If a ticket requires an enctype missing from the file, the validator reports no appropriate key found. Never downgrade to RC4/DES to cut down 401s. Inspect Kerberos config, AD supported encryption types, JDK policy, and key derivation sources.

### 3.3. Real Keys Are Secrets Requiring Protection

Keytabs contain long-term secret keys, not mere metadata. Anyone obtaining a keytab can impersonate the service or abuse tickets within that key's scope. Never place the file in Git/JARs/container images/CI logs; store via secret manager/Kubernetes Secrets with encryption at rest, ACLs, minimal runtime permissions, backup retention, and auditing.

**Never run `klist -K` to share in logs:** MIT `klist -K` prints encryption key values. Nor should you `cat`, `xxd`, or base64 a keytab into support tickets. Use `klist -k -e` to view only principals/versions/enctypes.

## 4. Four Clocks in Key Rotation

KDC key transition and application rollouts do not happen atomically:

1. **KDC active key:** when the KDC begins issuing new service tickets with v8.
2. **Keytab distribution:** when each pod/VM receives the file containing v8.
3. **JVM/JAAS runtime:** when the Subject and Kerberos acceptor actually load the new keys.
4. **Client service ticket lifetime:** browsers may keep sending cached v7 tickets.

Consequently, routine rotation often needs the **acceptor keytab to hold both v7 and v8** during a bounded grace period. The KDC switching to v8 does not automatically invalidate all cached client v7 tickets. Yet the KDC retaining old keys does not automatically put old keys into the acceptor's keytab file.

**Zero downtime is not guaranteed by default:** unlike public signature-verification certs that can be pre-published, Kerberos keytabs contain secrets; many KDCs start issuing v8 immediately upon rotation. If apps lack v8 yet, an error window occurs. Schedule a change window or use a genuinely supported staged-key mechanism rather than claiming any rollout is disruption-free.

## 5. Read-Only Checks Before Rotating Keys

### 5.1. Build an Inventory

```text
Public URL:     https://portal.example.org
Expected SPN:   HTTP/portal.example.org@EXAMPLE.ORG
Keytab path:    /run/secrets/kerberos/http.keytab
KDC type:       MIT KDC or Active Directory
Service owner:  svcPortal / principal admin
Pods:           portal-a, portal-b, portal-c
JDK:            17
Secret version:  v7
```

Illustrative names. Inspect the file **actually mounted and read by the JVM**, not just a copy outside the container.

### 5.2. List Keytab Entries on Linux/MIT

```bash
klist -k -e /run/secrets/kerberos/http.keytab
klist -k -t -e /run/secrets/kerberos/http.keytab
```

`-k` lists keytab keys, `-e` shows enctypes, `-t` shows timestamps. Never add `-K` when capturing logs.

### 5.3. Query the KDC for the Service Ticket Version

From a **test client** holding valid Kerberos credentials:

```bash
kvno HTTP/portal.example.org@EXAMPLE.ORG

# If MIT Kerberos version supports it, test decrypting ticket with file.
kvno -k /run/secrets/kerberos/http.keytab \
     HTTP/portal.example.org@EXAMPLE.ORG
```

`kvno` fetches a service ticket and prints its key version; `kvno -k` also attempts decryption against the keytab, verifying **secret bytes**, not just the KVNO label. Depending on KDC/credentials/cache and tool release, ensure you actually test a newly issued ticket rather than a stale cached one.

`kinit -k -t <keytab> <principal>` can test acquiring initial credentials with a service key, yet **it does not replace** an HTTP SPNEGO acceptor test with a browser/AP-REQ and Spring Security. Never wipe user credential caches wholesale; use a dedicated test identity.

### 5.4. Inspect the Test Client's Cache

```bash
klist -e
kvno HTTP/portal.example.org@EXAMPLE.ORG
```

A cached v7 ticket can still be sent by a browser after the KDC activates v8. During diagnostics, distinguish cached old tickets from newly issued ones; never assume one passing user test guarantees every client ticket passes.

## 6. Routine Rotation Procedure v7 → v8

### 6.1. Preparation

- Confirm principal/realm/KDC backend, account owners, and all services sharing the long-term key.
- Record current KVNO/enctypes from both KDC and keytab, and confirm SPN uniqueness.
- Measure maximum service ticket lifetime and AD/DC replication timelines if applicable.
- Back up the v7 file securely in a vault with restricted read access and zero secret exposure.
- Rehearse on a staging realm; prepare rollout automation and canary SPNEGO probes.
- Confirm how the v8 key will be obtained from KDC/AD, who is authorized, and whether a maintenance window is needed.
- Agree on grace cutoff, rollback/incident paths, version manifests, and approvals.

### 6.2. Actual Cutover

```text
T0: KDC active v7; all JVMs accept v7
        |
T1: KDC admin rotates key to v8 (KDC may issue v8 immediately)
        |
T2: Receive v8 keytab safely; combine v7+v8 for routine grace
        |
T3: Distribute/mount v7+v8 secret -> all pods
        |
T4: Reinitialize JAAS credentials or rolling restart JVMs
        |
T5: Canary new v8 SPNEGO PASSES on every pod, old cached v7 PASSES
        |
T6: Wait for bounded grace to expire, retire v7 from all runtime/vault copies
```

**T1–T4 may experience a brief disruption window.** There is no universal way for the KDC and all pods to flip atomically. If your KDC/secret tooling supports safe pre-provisioning/dual-key protocols, follow its exact documentation; otherwise, your plan must reflect the downtime risk.

### 6.3. Bounded Overlap for Routine Rotation, None for Emergency Revocation

Keeping v7+v8 lets the acceptor decrypt **v7 tickets issued before rotation** alongside new v8 tickets while valid. Never retain old v7 indefinitely because that prolongs the blast radius. If v7 is **compromised**, keep zero routine overlap: revoke the old key under incident response and accept reauthentication/disruption.

### 6.4. Rollback Is Not Just Rolling Back the Container Image

If the KDC is active on v8 and you roll back an app image to a v7-only keytab, new logins will fail. During rollback, keep a v8-compatible runtime keytab or coordinate a separate KDC change with admins, accounting for cached tickets/DC replication. Never rotate the KDC again just to patch a botched secret rollout.

## 7. MIT Kerberos: Special Caveats with ktadd

### 7.1. Default ktadd Generates a New Key and Increments KVNO

Example MIT `kadmin` command:

```text
kadmin: ktadd -k /secure/keytabs/portal-new.keytab \
  HTTP/portal.example.org@EXAMPLE.ORG
```

**WARNING: COMMAND HAS SIDE EFFECTS ON THE KDC.** MIT `ktadd` randomizes keys and bumps the version by default rather than merely "exporting a file". If two admins run it uncoordinated, Admin A creates v8 while Admin B creates v9; pods that just received v8 become stale immediately. Enforce change locks, audits, and KDC ownership.

### 7.2. ktadd -norandkey

Where KDC policy and privileges permit, use:

```text
kadmin: ktadd -norandkey \
  -k /secure/keytabs/portal-export.keytab \
  HTTP/portal.example.org@EXAMPLE.ORG
```

MIT docs: `-norandkey` does not randomize keys or change the KVNO; it exports current key material. **It is still a secret export**, not a read-only operation regarding confidentiality. Do not combine `-norandkey` with `-e`; verify version/backend/permissions.

### 7.3. KDC -keepold Does Not Automatically Put Old Keys in the App

An MIT command rotating the KDC key might be:

```text
kadmin: change_password -randkey -keepold \
  HTTP/portal.example.org@EXAMPLE.ORG
```

**This also mutates the KDC key**; never test it in production. `-keepold` retains previous KDC keys per policy, yet an acceptor wanting to decrypt cached v7 tickets still needs the **exact v7 key bytes inside its keytab**. Do not confuse the KDC retaining old keys with the JVM having them. MIT docs highlight `-keepold` especially for `krbtgt`; do not mechanically copy `krbtgt` rotation procedures to HTTP service principals.

### 7.4. Merging Keytabs When Retaining v7+v8

Given two safely provisioned keytab files, MIT `ktutil` supports:

```text
$ ktutil
ktutil: read_kt /secure/keytabs/portal-v7.keytab
ktutil: read_kt /secure/keytabs/portal-v8.keytab
ktutil: list -e
ktutil: write_kt /secure/keytabs/portal-v7-v8.keytab
ktutil: quit
```

`ktutil` manipulates entries on the filesystem without altering the KDC. **These are sensitive operational commands**; never run without authorization and backups. Never run `list -k`, which can print key bytes. After merging:

```bash
klist -k -e /secure/keytabs/portal-v7-v8.keytab
```

Run an **actual** `kvno -k` or fresh Java GSS authentication check. Seeing v7/v8 entries in the file does not prove the secret bytes are valid, nor that a running JVM has reloaded the file.

## 8. Microsoft AD: SPN, ktpass, Key Version, and Replication

### 8.1. The SPN Must Belong to the Right Account

AD's KDC encrypts service tickets with the key of the **AD account owning the SPN**. If `HTTP/portal.example.org` is bound to the wrong account or duplicated, a keytab generated from another account cannot decrypt tickets. A telltale sign is `KRB_AP_ERR_MODIFIED` even when the KVNO looks right.

Read-only commands:

```powershell
setspn -Q HTTP/portal.example.org
setspn -L EXAMPLE\svcPortal
```

Never add the same SPN to multiple accounts for "load balancing". All pods for a public SPN must share a clean single-account/key strategy.

### 8.2. msDS-KeyVersionNumber

Microsoft exposes `msDS-KeyVersionNumber` indicating the current Kerberos key version for an account. With the ActiveDirectory module:

```powershell
Get-ADUser -Identity svcPortal -Properties "msDS-KeyVersionNumber","msDS-SupportedEncryptionTypes" | Select-Object SamAccountName,"msDS-KeyVersionNumber","msDS-SupportedEncryptionTypes"
```

This is a **read-only** command for user service accounts. Computer/gMSA accounts use their respective cmdlets. This attribute is **constructed**; DC replication lag can cause different DCs to issue different keys/versions during rotation. Check the actual DC/KDC serving clients and replication health before drawing conclusions.

### 8.3. ktpass Can Modify the Account/Password

Microsoft `ktpass` does not merely "inspect a keytab"; it supports `/princ`, `/mapuser`, `/pass`, `/crypto`, `/kvno`, `/out` and can alter mappings/secrets. Example **command structure for reading only**, never execute without admin approval:

```text
ktpass /out C:\secure\portal-next.keytab
       /princ HTTP/portal.example.org@EXAMPLE.ORG
       /mapuser EXAMPLE\svcPortal
       /crypto AES256-SHA1
       /ptype KRB5_NT_PRINCIPAL
       /pass *
```

`/pass *` prompts interactively; never put plaintext passwords on the command line/history/CI logs. Microsoft docs state `/kvno` defaults to 1 if omitted, so **never assume a file's KVNO label matches AD's current KVNO**. Never force a guessed KVNO: matching versions with wrong bytes still fail, and `ktpass` can reset/remap keys impacting multiple services.

### 8.4. AD Causes to Inspect

- SPN ownership/duplicate SPNs and the actual service account.
- Password recently rotated while the keytab was generated from the old password.
- AES salt/key derivation/casing/principal mismatch.
- Account `msDS-SupportedEncryptionTypes` differs from what Java/KDC issues.
- Incomplete DC replication.
- Browser requesting a ticket for a different DNS alias SPN.
- Cached Java Subject/keytab or wrong runtime path.
- gMSA managed rotation has its own lifecycle; never overwrite it manually with `ktpass`.

**Never downgrade Kerberos security to RC4/DES to bypass AES errors.** Fix the account, salt, enctype, secret source, and runtime keytab.

## 9. Java JAAS and Spring Security Kerberos

### 9.1. Java Acceptor Login Configuration

A JAAS config for a service acceptor:

```properties
KerberosServiceAcceptor {
  com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    keyTab="/run/secrets/kerberos/http.keytab"
    principal="HTTP/portal.example.org@EXAMPLE.ORG"
    storeKey=true
    doNotPrompt=true
    isInitiator=false
    debug=false;
};
```

`useKeyTab` and `keyTab` point to the file; `principal` names the service acceptor principal; `storeKey` lets the Subject retain service credentials; `isInitiator=false` suits a server acceptor; `doNotPrompt=true` prevents interactive password prompts. This is **JAAS syntax**, not a Java program. Never use `principal="*"` to mask a wrong SPN without reviewing the trust scope.

### 9.2. Spring Security Kerberos Components

| Component | Responsibility |
| --- | --- |
| `SpnegoEntryPoint` | Sends HTTP Negotiate challenge |
| `SpnegoAuthenticationProcessingFilter` | Accepts `Authorization: Negotiate` |
| `KerberosServiceAuthenticationProvider` | Validates service ticket and builds Authentication |
| `SunJaasKerberosTicketValidator` | Uses JAAS/JGSS + keytab to verify |
| `UserDetailsService` | Maps principal to app authorities |
| `KerberosAuthenticationProvider` | Separate Kerberos client/username-password branch, does not replace acceptor |

Spring Security Kerberos is a separate **extension**, distinct from Spring Security SAML2/OIDC/CAS. Verify version compatibility across Spring Boot, Security, JDK, and Jakarta Servlet.

### 9.3. Spring Bean Example

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.kerberos.authentication.sun
        .SunJaasKerberosTicketValidator;

@Configuration
public class KerberosAcceptorConfig {

    @Bean
    SunJaasKerberosTicketValidator ticketValidator() {
        SunJaasKerberosTicketValidator validator =
                new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(
                "HTTP/portal.example.org@EXAMPLE.ORG");
        validator.setKeyTabLocation(
                new FileSystemResource(
                    "/run/secrets/kerberos/http.keytab"));
        validator.setDebug(false);
        return validator;
    }
}
```

This is a Spring configuration class, **not runnable standalone via javac/java**. It requires a full application, the `spring-security-kerberos` dependency, and authentication filter/provider/entry point wiring. Store the keytab on an external file mount, never embedded in JAR/classpath.

### 9.4. Provider/Filter Fragment

```java
import org.springframework.security.kerberos.authentication
        .KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.web.authentication
        .SpnegoAuthenticationProcessingFilter;

// Fragment: ticketValidator, userDetailsService, authenticationManager
// are beans already configured in Spring.
KerberosServiceAuthenticationProvider provider =
        new KerberosServiceAuthenticationProvider();
provider.setTicketValidator(ticketValidator);
provider.setUserDetailsService(userDetailsService);

SpnegoAuthenticationProcessingFilter filter =
        new SpnegoAuthenticationProcessingFilter();
filter.setAuthenticationManager(authenticationManager);
```

`AuthenticationManager` and `SecurityFilterChain` must be wired per your specific release API. Do not confuse GSS accept with business authorization: Spring can authenticate a valid principal while UserDetailsService rejects disabled accounts or missing roles.

### 9.5. Does the JVM Reload Keytab Files Automatically?

Never **assume** replacing the file makes the JVM pick up v8 automatically. JAAS `LoginContext`/`Subject` or the validator may hold previously loaded credentials. A controllable process: atomic file replacement, **reinitializing acceptor credentials or rolling-restarting JVMs**, then testing with a fresh ticket. `setRefreshKrb5Config(true)` on a validator (where available) relates to refreshing Kerberos config, not guaranteed reloading of secret keytabs already held inside a Subject.

Debugging in a test environment:

```text
-Dsun.security.krb5.debug=true
-Djava.security.krb5.conf=/etc/krb5.conf
-Djava.security.auth.login.config=/etc/security/jaas.conf
```

Oracle documents `sun.security.krb5.debug`; enable temporarily, restrict log access, and redact. Never print AP-REQ tokens, keytabs, ticket ciphertexts, or passwords.

## 10. Multi-Node and Safe Deployment

### 10.1. Secret Mount vs. Effective JVM State

An updated Kubernetes Secret does not prove:

- The pod received the new volume revision (`subPath` in particular has different update semantics).
- The runtime has permission to read the new file version.
- JVM JAAS credentials reloaded.
- All pods/regions run with the **exact same KVNO/enctype/key bytes**.
- The KDC/DC switched keys and replicated uniformly.

Tag secret versions/expected KVNOs in deployment manifests and monitoring **without exposing secrets**, and use real SPNEGO canary readiness probes. Never rely solely on `/health` returning 200.

### 10.2. Rollout Checklist

1. Distribute the approved v8 keytab via secret manager/encrypted channel, never Git/images.
2. Keep v7+v8 during bounded routine grace when policy allows.
3. Swap the keytab atomically with tight read permissions.
4. Perform controlled restart/reinitialization of Spring Kerberos acceptors.
5. Test a fresh v8 ticket against **every pod/region**.
6. Test a cached v7 ticket if backward compatibility is required.
7. Drain stale pods; do not rotate the KDC key yet again.
8. Monitor 401/GSS integrity failures per pod, realm/service ID allowlist.
9. Retire v7 after ticket lifetime/grace, scrubbing vaults/backups.
10. If v7 was compromised, revoke immediately with zero overlap.

### 10.3. Existing Sessions Can Mask Failures

Users already authenticated in Spring's `HttpSession` can keep using the app even while new SPNEGO authentication is broken. Tests must use a **fresh session/new ticket** to confirm. Conversely, rotating a keytab does not automatically clear existing app sessions: in a compromise incident, revoke sessions/tokens per threat model.

## 11. Troubleshooting Matrix

| Symptom | Likely Cause | Verification Step |
| --- | --- | --- |
| `KRB_AP_ERR_MODIFIED` / "Message stream modified" | Wrong key bytes, SPN on another account, enctype/KVNO mismatch | Check KDC service ticket + keytab + AD SPN owner |
| `Cannot find key of appropriate type` | Missing enctype/principal/version | `klist -k -e`, KDC ticket enctype |
| Key version incorrect | New ticket KVNO while file is old | `kvno` and keytab entries |
| Integrity check on decrypted field failed | Wrong secret/salt/password source/realm | Account owner, key derivation, controlled decrypt test |
| `KDC_ERR_ETYPE_NOSUPP` | No common enctype | KDC/account/JDK crypto policies |
| Server not found in Kerberos database | Wrong SPN/realm | MIT principal or `setspn -Q` |
| Clock skew too great | Clock sync issue | NTP/chrony/DC time |
| Pod A passes, Pod B fails | Different keytab mount/JAAS cache | Per-pod inspection/testing |
| Fails only on DNS alias | Client requests a different alias SPN | Hostname/canonicalization/registered SPN |
| Fails only on cached old tickets | v7 retired too early | Ticket lifetime and overlap policy |
| v8 file on disk, JVM still fails | Subject/validator cached v7 | Reinitialize/restart |
| Browser sends no Negotiate token | Browser/client realm/policy or proxy stripping headers | Check presence without logging tokens |
| Kerberos authenticated yet HTTP 403 | Authorization/role/user mapping | UserDetailsService, Spring policies |
| Flaky AD failures after password change | Incomplete DC replication | DC-specific key/version tests |
| Unexpected version jump after MIT export | `ktadd` generated a new key | KDC admin audit |

Do not blame every exception on KVNO; **principal, enctype, key bytes, KDC, ticket, JVM, proxy, and authorization** must all align.

### 11.1. Procedure for Handling a 401 Incident

1. Confirm the browser actually sent `Authorization: Negotiate`, not mistaking the initial challenge.
2. Verify expected public SPN and realm.
3. Run `klist -k -e` on **each pod** to inspect effective file entries, without `-K`.
4. Run `kvno` from a test client to read ticket KVNO and, if supported, `kvno -k` to test decryption.
5. On AD, check `setspn -Q`, current `msDS-KeyVersionNumber`, and DC replication.
6. On MIT, inspect admin history for unscheduled `ktadd` without `-norandkey` or `change_password`.
7. If KVNO/enctype look right yet auth still fails, investigate wrong password/salt/key bytes/account owner/JVM cache.
8. Deploy the verified new keytab, restart/reinitialize acceptors, and run real tests.
9. Do not keep rotating the KDC key repeatedly, do not enable weak enctypes, and do not fail open to anonymous.
10. Once stable, monitor and retire old keys on the approved schedule.

## 12. Standalone Java 17: Simulating KVNO/Keytab Rollout

This example simulates only **matching principal + KVNO + enctype + secret bytes** via a `keyTag` field (placeholder symbol). Real Kerberos does not compare a `keyTag` string inside a ticket; JGSS uses cryptography, ticket checks, and replay/clock policies. The goal is showing that **the same KVNO with the wrong secret still fails** and **a pod lacking v8 still fails**.

Save `KerberosKeytabRotationDemo.java`:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

public class KerberosKeytabRotationDemo {

    record Key(String principal, int kvno, String enctype,
               String keyTag) {}

    record Ticket(String principal, int kvno, String enctype,
                  String keyTag) {}

    static final class Kdc {
        private Key activeKey;

        Kdc(Key key) {
            activeKey = key;
        }

        void rotateTo(Key next) {
            activeKey = next;
        }

        Ticket issueServiceTicket() {
            return new Ticket(activeKey.principal(),
                    activeKey.kvno(), activeKey.enctype(),
                    activeKey.keyTag());
        }
    }

    static final class Acceptor {
        private final Set<Key> keytab = new HashSet<>();

        Acceptor(Key... entries) {
            keytab.addAll(Arrays.asList(entries));
        }

        void install(Key key) {
            keytab.add(key);
        }

        void retire(Key key) {
            keytab.remove(key);
        }

        boolean accepts(Ticket ticket) {
            return keytab.stream().anyMatch(key ->
                key.principal().equals(ticket.principal())
                && key.kvno() == ticket.kvno()
                && key.enctype().equals(ticket.enctype())
                && key.keyTag().equals(ticket.keyTag()));
        }
    }

    public static void main(String[] args) {
        String principal =
                "HTTP/portal.example.org@EXAMPLE.ORG";
        String enctype = "aes256-cts-hmac-sha1-96";

        Key old = new Key(principal, 7, enctype, "secret-v7");
        Key next = new Key(principal, 8, enctype, "secret-v8");
        Kdc kdc = new Kdc(old);
        Acceptor podA = new Acceptor(old);
        Acceptor podB = new Acceptor(old);

        Ticket cachedOld = kdc.issueServiceTicket();
        System.out.println("Before rotation: "
                + (podA.accepts(cachedOld)
                && podB.accepts(cachedOld)));

        kdc.rotateTo(next);
        Ticket latest = kdc.issueServiceTicket();
        System.out.println("New ticket KVNO: " + latest.kvno());
        System.out.println("Old-only pod accepts v8: "
                + podA.accepts(latest));

        podA.install(next);
        System.out.println("Updated pod A accepts v8: "
                + podA.accepts(latest));
        System.out.println("Stale pod B accepts v8: "
                + podB.accepts(latest));

        podB.install(next);
        System.out.println("Both pods accept v8: "
                + (podA.accepts(latest) && podB.accepts(latest)));
        System.out.println("Cached v7 still accepted: "
                + (podA.accepts(cachedOld)
                && podB.accepts(cachedOld)));

        Acceptor wrongKey = new Acceptor(
                new Key(principal, 8, enctype, "different-secret"));
        System.out.println("Same KVNO, wrong key: "
                + wrongKey.accepts(latest));

        Ticket wrongEnctype = new Ticket(
                principal, 8, "arcfour-hmac", "secret-v8");
        System.out.println("Wrong enctype: "
                + podA.accepts(wrongEnctype));

        podA.retire(old);
        podB.retire(old);
        System.out.println("Old cached v7 after retire: "
                + podA.accepts(cachedOld));
        System.out.println("New v8 after retire: "
                + podA.accepts(latest));

        Ticket wrongPrincipal = new Ticket(
                "HTTP/other.example.org@EXAMPLE.ORG",
                8, enctype, "secret-v8");
        System.out.println("Wrong principal: "
                + podA.accepts(wrongPrincipal));
    }
}
```

Compile and run with JDK 17:

```bash
javac KerberosKeytabRotationDemo.java
java KerberosKeytabRotationDemo
```

Exact stdout:

```text
Before rotation: true
New ticket KVNO: 8
Old-only pod accepts v8: false
Updated pod A accepts v8: true
Stale pod B accepts v8: false
Both pods accept v8: true
Cached v7 still accepted: true
Same KVNO, wrong key: false
Wrong enctype: false
Old cached v7 after retire: false
New v8 after retire: true
Wrong principal: false
```

### 12.1. Model Analysis

- KDC active on v7: both pods A and B hold v7 and accept cached old tickets.
- KDC switches to v8 before pods update: new tickets fail on both while v8 is missing.
- Only pod A installs v8: A passes, B fails, producing intermittent 401s.
- Both pods hold v7+v8: new tickets pass, and cached v7 tickets also pass during grace.
- File says v8 yet `keyTag` is wrong: fails. **A version number alone does not prove the secret matches.**
- Wrong enctype/SPN: fails even when KVNO matches.
- Retiring v7: cached old tickets are no longer accepted; v8 continues to pass.

**Limitations:** this program does not use a real KDC, decrypt AP-REQs, check expiry/replay/clocks/session keys, parse binary keytabs, or authorize users. Never substitute `Acceptor.accepts` for production `SunJaasKerberosTicketValidator.validateTicket`.

## 13. Negative Testing and Acceptance

| Test | Expectation |
| --- | --- |
| KDC v7, pods v7 | New Kerberos auth passes |
| KDC v8, pod v7 only | v8 ticket rejected, alerts fire |
| KDC v8, pods v7+v8 | New v8 ticket passes if crypto matches |
| Client cached v7, acceptor v7+v8 | Passes within permitted grace if ticket unexpired |
| Client cached v7, acceptor v8 only | Rejected |
| Right KVNO 8 yet wrong secret | Rejected/integrity error |
| AES256 ticket, keytab lacks AES256 | Rejected, never downgrade to RC4/DES |
| Wrong servicePrincipal/realm | Rejected |
| SPN points to another AD account | Decryption fails; fix ownership |
| Stale AD DC replication | Test detects discrepancy |
| Unplanned MIT `ktadd` re-run | Test/audit detects unexpected KVNO |
| JVM Subject keeps old key after file swap | Restart/reinitialize requirement caught |
| Missing secret path or permission denied | Fails closed, readiness fails |
| Pod A updated, B stale | Per-pod tests catch drift |
| Image rollback with v7-only keytab while KDC on v8 | QA fails |
| Keytab leaked in repo/CI/backups | Security QA fails + incident |
| Local Spring authenticated session stays alive | Never treated as proof new SPNEGO acceptor passes |
| Successful GSS yet disabled app account | App denies per policy |
| Wrong tenant principal/role mapping | No cross-tenant access granted |

### 13.1. Real HTTP Negotiate Test

In a lab with a test account holding Kerberos credentials and GSSAPI-enabled `curl`:

```bash
curl --negotiate -u : \
     --silent --show-error --output /dev/null \
     --write-out '%{http_code}\n' \
     https://portal.example.org/protected
```

Avoid `--verbose` or traces capturing raw Authorization headers or tickets/usernames. HTTP 200 does not prove Kerberos auth if the route is public/fallback; verify the mechanism via safe server telemetry. Route tests to individual pods/regions in a controlled environment.

## 14. When a Keytab Leaks: Emergency Differs from Routine Overlap

A leaked keytab secret may have been copied. Deleting the file does not revoke copies. Incident response:

1. Isolate the leak source and restrict secret store/CI/repository access.
2. Identify all SPNs/accounts and pods sharing that key.
3. KDC/AD admins revoke or rotate the long-term service key per incident procedure.
4. Distribute the new keytab and restart/reinitialize acceptors, **retaining zero grace for the compromised old key**.
5. Assess cached tickets, service sessions, delegated credentials, and unauthorized activity.
6. Audit logs safely, update IAM/ACLs, and review backups/secret history.
7. Accept temporary downtime/re-login if needed rather than failing open.

Never extend ticket lifetimes or enable weak enctypes to "reduce errors" after a compromise.

## 15. Production Checklist

- [ ] Principal, realm, service account, and public SPN accurately verified.
- [ ] Keytab matches principal/KVNO/enctype/**key bytes**, not just filename/version.
- [ ] MIT `ktadd`/AD `ktpass` controlled by KDC owners, never run as read-only commands.
- [ ] Current KDC KVNO and AD DC replication verified.
- [ ] Secret file encrypted/stored outside source code with minimal ACLs and zero raw byte logging.
- [ ] All pods receive the exact same approved keytab revision without drift.
- [ ] JAAS acceptor reload/restart verified using a fresh v8 ticket.
- [ ] Browser cached v7 tickets handled under bounded grace or revocation policy.
- [ ] Negative tests run for KVNO/enctype/SPN/key-byte mismatches.
- [ ] RC4/DES and anonymous fallbacks never enabled to mask errors.
- [ ] Local Spring Security sessions and authorization governed by dedicated policies.
- [ ] Image rollbacks do not revert to a v7-only keytab while KDC is on v8.
- [ ] v7 retired on schedule alongside backup cleanup, audit, and monitoring.
- [ ] Emergency revocation runbook ready if a keytab leaks.

## 16. Review Questions

**1. Does a matching KVNO guarantee a ticket can be decrypted?**  
No. Secret bytes, enctype, and principal must actually match.

**2. Is a keytab a public certificate?**  
No, it is a long-term secret key store for a Kerberos principal.

**3. Why can existing users still log in while new users fail after rotation?**  
Clients with cached old service tickets may still succeed if unexpired, while the KDC issues new tickets with a different KVNO.

**4. Why can MIT `ktadd` break production?**  
It randomizes keys/bumps KVNO by default; it does not merely export a file.

**5. What does `ktadd -norandkey` do?**  
Exports current key material without randomizing keys or changing KVNO when supported by version and admin policy.

**6. Does the KDC keeping old keys automatically allow the JVM to decrypt old tickets?**  
No; the acceptor must also hold the old key bytes in its keytab.

**7. Can you edit the KVNO label inside an old keytab to match the new KVNO?**  
No. Changing the number does not generate the real key material.

**8. What does AD `msDS-KeyVersionNumber` indicate?**  
The account's current key version; you must also verify DC replication and the right SPN/account.

**9. How do `klist -k -e` and `klist -K` differ?**  
The first lists entries/enctypes; `-K` can print actual secret keys.

**10. Does replacing the keytab file guarantee the JVM is using the new file?**  
No. JAAS/Subjects may cache credentials; reinitialize/restart and run E2E tests.

**11. Should old+new grace be kept after a service account compromise?**  
No. Perform an emergency revocation and accept reauthentication if required.

**12. What does Spring Security Kerberos use to validate tokens?**  
`SunJaasKerberosTicketValidator` wired into `KerberosServiceAuthenticationProvider` and `SpnegoAuthenticationProcessingFilter` per configuration.

## 17. Standards and Reference Documentation

- [MIT Kerberos — Keytab](https://web.mit.edu/kerberos/krb5-latest/doc/basic/keytab_def.html): principal, KVNO, enctype, and secret key entries.
- [MIT Kerberos — klist](https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/klist.html): `-k`, `-e`, `-t`, warning on `-K`.
- [MIT Kerberos — kvno](https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/kvno.html): KDC service ticket KVNO and `-k` decrypt check.
- [MIT Kerberos — kadmin](https://web.mit.edu/kerberos/krb5-latest/doc/admin/admin_commands/kadmin_local.html): `ktadd`, `-norandkey`, `change_password -keepold`, `purgekeys`.
- [MIT Kerberos — ktutil](https://web.mit.edu/kerberos/krb5-latest/doc/admin/admin_commands/ktutil.html): reading/writing/merging keytabs.
- [Microsoft Learn — ktpass](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/ktpass): AD keytab generation, SPN, crypto, and KVNO options.
- [Microsoft Learn — msDS-KeyVersionNumber](https://learn.microsoft.com/en-us/windows/win32/adschema/a-msds-keyversionnumber): account Kerberos key version.
- [Spring Security Kerberos Reference](https://docs.spring.io/spring-security-kerberos/reference/ssk.html): SPNEGO/Kerberos auth provider, SunJaasKerberosTicketValidator config.
- [Spring Security Kerberos Ticket Validator API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/sun/SunJaasKerberosTicketValidator.html): keyTabLocation/servicePrincipal/debug.
- [Oracle Java 17 — Krb5LoginModule](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.security.auth/com/sun/security/auth/module/Krb5LoginModule.html): JAAS acceptor login options.
- [Oracle — Troubleshooting JGSS](https://docs.oracle.com/en/java/javase/26/security/troubleshooting-jgss.html): Kerberos debug behavior.
- [OWASP Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): protecting keytabs/long-term credentials.

**Takeaway:** A Kerberos service acceptor must hold **the exact secret keytab matching the principal, KVNO, enctype, and key bytes** that the KDC uses for service tickets. A KDC rotating versions before apps receive the new keytab causes failures; cached old tickets create the need for bounded old+new acceptor overlap during routine rotation. MIT `ktadd` and AD `ktpass` can mutate the KDC/account itself, so coordinate them rather than treating them as read-only tools. Always verify the file and JVM runtime across all pods, test real SPNEGO, and retire old keys on schedule; on key compromise, revoke immediately without retaining grace or disabling validation.