# Configuring HTTPS for the Management Port and Its Relationship With Application HTTPS

## 1. Identify Where TLS Terminates

HTTPS is HTTP transmitted over a TLS-protected connection. Before choosing properties, determine whether the TLS connection is handled directly at the Spring Boot application or at an intermediary server (proxy).

If the JVM serves HTTPS directly, the listening endpoint must have TLS configuration and suitable cryptographic material. Merely changing the port from 8080 to 8443 or 9443 does not turn HTTP into HTTPS.

In this article, **Spring Boot 3.3.x**, referencing 3.3.13, has two configuration groups:

| Group | Scope |
| --- | --- |
| `server.ssl.*` | TLS for the main application server |
| `management.server.ssl.*` | Dedicated TLS for the management server when management uses a different port from the application |

Spring Boot allows the two ports to have different SSL configurations, including the case where the application uses HTTPS while management uses HTTP. [Configuring management-specific SSL](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.configuring-management-specific-ssl).

The property names still use the word `ssl`, but the purpose is configuring server HTTPS/TLS. Do not use the property name as a reason to enable legacy SSL protocol versions.

## 2. Sharing a Port vs. Using a Separate Management Port

### 2.1. When Sharing a Port

If `management.server.port` is not set, Actuator shares the application's server/port. TLS is then determined by `server.ssl.*`.

Example with a test keystore that will be created in section 4:

```yaml
server:
  port: 8443
  address: 127.0.0.1
  ssl:
    enabled: true
    key-store: file:./tls/app-local.p12
    key-store-type: PKCS12
    key-store-password: ${APP_TLS_STORE_PASSWORD}
    key-alias: app-local

management:
  endpoints:
    web:
      exposure:
        include: health
```

In this standalone configuration, the health address is:

```text
https://localhost:8443/actuator/health
```

Management endpoints and business HTTP go through the same TLS server. Do not use `management.server.ssl.*` to request a separate certificate per `/actuator` path on the same listener. TLS is established before the server reads the HTTP path to select an endpoint.

Management-specific SSL properties require a separate management port. [Management server property scope](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator).

### 2.2. When Management Uses a Different Port

With `server.port=8443` and `management.server.port=9443`, you can choose independent management TLS.

In the default embedded server mechanism of 3.3.13, the management server is customized according to the application-side configuration first; if a separate management SSL object is present, that object is set on the management server instead. This leads to two interpretations:

- **No separate management SSL block declared:** under this default mechanism, the management server keeps the SSL configuration inherited from the application side.
- **Separate management SSL block declared:** provide complete suitable configuration for it; do not assume missing fields will be merged field-by-field with `server.ssl.*`.

This is inferred from [`ManagementWebServerFactoryCustomizer` in 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/web/server/ManagementWebServerFactoryCustomizer.java). If the project customizes the server via code, check that customization as well.

For example, setting only `management.server.ssl.enabled=true` is not a clear way to select "the application's certificate plus a few small tweaks." When separate management TLS is needed, declare the full key/certificate source or select an SSL bundle that already contains complete material.

## 3. What Does a Server Need to Serve HTTPS?

| Component | Purpose |
| --- | --- |
| Private key | Proves the server owns the key matching the certificate |
| Server certificate, with needed chain | Presents the server's identity for the client to verify |
| Keystore | Holds the private key and certificate, e.g., PKCS12 format |
| Key alias | Selects the right private key entry in the store |
| Client trust source | Allows the calling tool to verify the server certificate |
| Domain/IP in SAN | Allows matching certificate identity with the URL called |

Do not confuse a **server-side serving keystore** with a **truststore used to verify the peer**. In the one-way HTTPS of this lab, the server needs a private key and certificate; curl needs to trust the server certificate.

If mutual TLS (mTLS) is used later, the server also checks client certificates and requires corresponding trust configuration. Enabling ordinary HTTPS does not mean every client must present a certificate. [Role of keystore and truststore in Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html).

Common properties when choosing PKCS12:

| Relative Property Under SSL Group | Value in Example |
| --- | --- |
| `enabled` | `true` |
| `key-store` | `file:./tls/management-local.p12` |
| `key-store-type` | `PKCS12` |
| `key-store-password` | Value read from environment variable |
| `key-alias` | `management-local` |

`file:./tls/management-local.p12` is a path relative to the Java process's working directory. It is not automatically resolved relative to `application.yml`'s location. If using `classpath:`, resources are searched on the classpath instead; these are two distinct resolution mechanisms.

## 4. Generating TLS Material for a Local Lab

This section is a hands-on exercise for a **separate test project** that already has a Spring Boot 3.3.x main class, `spring-boot-starter-web`, and `spring-boot-starter-actuator`. Uses JDK 21; commands run in PowerShell at the test project root.

The self-signed certificates in this lesson are only for local testing, with SANs for `localhost` and `127.0.0.1`. Do not use them as certificates for another deployment domain.

### 4.1. Create a New Directory and Session Passwords

Assuming the test project does not yet have a `tls` directory:

```powershell
New-Item -ItemType Directory -Path ./tls -ErrorAction Stop | Out-Null
$env:APP_TLS_STORE_PASSWORD = [Guid]::NewGuid().ToString("N")
$env:MGMT_TLS_STORE_PASSWORD = [Guid]::NewGuid().ToString("N")
```

The two variables receive different values and are kept in the PowerShell session. Do not print or copy them into notes. Run keystore generation and start the application from the session holding these variables; if running via an IDE or another tool, supply the same values to the Java process.

Do not rerun the two password-generation lines and then use keystores created with the old passwords. When opening a new session, supply the exact passwords of the existing stores or intentionally generate a fresh set of test material.

### 4.2. Generate Two Independent Keystores

Each line below is a complete command:

```powershell
keytool -genkeypair -alias app-local -keyalg RSA -keysize 2048 -validity 30 -dname "CN=localhost,O=LocalLab,C=VN" -ext "SAN=DNS:localhost,IP:127.0.0.1" -storetype PKCS12 -keystore ./tls/app-local.p12 -storepass:env APP_TLS_STORE_PASSWORD -keypass:env APP_TLS_STORE_PASSWORD
keytool -genkeypair -alias management-local -keyalg RSA -keysize 2048 -validity 30 -dname "CN=localhost,O=LocalLab,C=VN" -ext "SAN=DNS:localhost,IP:127.0.0.1" -storetype PKCS12 -keystore ./tls/management-local.p12 -storepass:env MGMT_TLS_STORE_PASSWORD -keypass:env MGMT_TLS_STORE_PASSWORD
```

`-storepass:env` and `-keypass:env` tell keytool to read values from the named environment variables. In each PKCS12 store in this lab, the key entry password is set equal to the store password.

The SAN contains the names/IPs clients will use. Setting only `CN=localhost` and omitting SAN is not reliable hostname verification for modern tools. [keytool command, password options, and certificate extensions in JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html).

### 4.3. Export Public Certificates for curl

```powershell
keytool -exportcert -rfc -alias app-local -keystore ./tls/app-local.p12 -storepass:env APP_TLS_STORE_PASSWORD -file ./tls/app-local.crt
keytool -exportcert -rfc -alias management-local -keystore ./tls/management-local.p12 -storepass:env MGMT_TLS_STORE_PASSWORD -file ./tls/management-local.crt
```

Expected files:

| File | Role |
| --- | --- |
| `tls/app-local.p12` | Private key and certificate for the application |
| `tls/management-local.p12` | Private key and certificate for management |
| `tls/app-local.crt` | Public PEM certificate for clients to trust the app server in the lab |
| `tls/management-local.crt` | Public PEM certificate for clients to trust the management server in the lab |

`.p12` files contain private keys; do not commit test keystores and passwords to Git. `.crt` files exported with this command do not contain private keys. In real deployments, manage keys, certificates, trust chains, and renewal according to the chosen infrastructure.

## 5. Two HTTPS Ports With Two Keystores

Use the following configuration in `src/main/resources/application.yml` of the test project:

```yaml
server:
  port: 8443
  address: 127.0.0.1
  ssl:
    enabled: true
    key-store: file:./tls/app-local.p12
    key-store-type: PKCS12
    key-store-password: ${APP_TLS_STORE_PASSWORD}
    key-alias: app-local

management:
  server:
    port: 9443
    address: 127.0.0.1
    ssl:
      enabled: true
      key-store: file:./tls/management-local.p12
      key-store-type: PKCS12
      key-store-password: ${MGMT_TLS_STORE_PASSWORD}
      key-alias: management-local
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: health
  endpoint:
    health:
      enabled: true
```

Read the configuration as two separate sets:

| Item | Main Application | Management |
| --- | --- | --- |
| Port | `8443` | `9443` |
| Protocol | HTTPS | HTTPS |
| Bind address | `127.0.0.1` | `127.0.0.1` |
| Keystore | `app-local.p12` | `management-local.p12` |
| Alias | `app-local` | `management-local` |
| Password source | `APP_TLS_STORE_PASSWORD` | `MGMT_TLS_STORE_PASSWORD` |

Application and management may share one keystore when design calls for it; two keystores in this lesson highlight configuration independence.

### Testing With curl With Certificate Verification

Start the test project from its root directory and the session holding the right environment variables. Assumptions:

- No Spring Security, proxies, custom paths, or controllers conflicting with the tested path.
- No other configuration source overrides it, and no additional health path is added to the application port.
- Certificates are valid; curl supports `--cacert` and the client environment can verify test certificates.
- Health status is `UP`.

In PowerShell:

```powershell
curl.exe --cacert ./tls/management-local.crt --silent --show-error --max-time 5 --output NUL --write-out "%{http_code}\n" "https://localhost:9443/actuator/health"
curl.exe --cacert ./tls/app-local.crt --silent --show-error --max-time 5 --output NUL --write-out "%{http_code}\n" "https://localhost:8443/actuator/health"
```

Expected stdout of the two commands in order:

```text
200
404
```

The first command checks health at the management server. The second uses the right application certificate to establish TLS, but health is not on the main port in the lab configuration. HTTP 404 here differs from a TLS handshake failure.

To view the health body:

```powershell
curl.exe --cacert ./tls/management-local.crt --silent --show-error --max-time 5 "https://localhost:9443/actuator/health"
```

Under the stated conditions, typical JSON:

```json
{"status":"UP"}
```

`--cacert` provides an explicit trust source for that call. Curl still verifies the certificate and hostname; do not use `-k`/`--insecure` as criteria proving trust configuration is right. [How curl verifies server certificates](https://curl.se/docs/sslcerts.html).

The responses above are conditional expected results. Generated addresses, validity periods, and certificate contents vary per generation, so no fake fingerprint or expiration date is recorded in the documentation.

## 6. Combinations Between Application HTTPS and Management HTTPS

After understanding the full configuration in section 5, you can vary the intent per server:

| Application | Management | How to Configure |
| --- | --- | --- |
| HTTPS, sharing port with Actuator | Same HTTPS | Use `server.ssl.*`; do not create separate management SSL |
| HTTPS 8443 | HTTPS 9443 with separate store | Configure both SSL groups completely as in section 5 |
| HTTPS 8443 | HTTP 9091 | Keep app TLS, set separate management port and `management.server.ssl.enabled=false` |
| HTTP 8080 | HTTPS 9443 | Disable app-side TLS, keep full separate management TLS |
| HTTPS 8443 | Separate management port, no separate SSL set | Keeps app SSL under default mechanism; check further if customized in code |

### 6.1. HTTPS Application, HTTP Management

To modify the section 5 lab:

- Keep the entire `server` section of the application unchanged.
- Change the management port to `9091`.
- Replace the `management.server.ssl` block with a block disabling TLS; keep the local management address.

The replacement `management.server` snippet is:

```yaml
management:
  server:
    port: 9091
    address: 127.0.0.1
    ssl:
      enabled: false
```

This is the section to replace in the existing tree; keep the health enable/exposure settings under the same `management` block without creating two duplicate `management:` YAML keys.

Management URL is now:

```text
http://localhost:9091/actuator/health
```

The main application's certificate does not encrypt this HTTP connection. If the management port is later exposed onto another network, you must properly evaluate that unencrypted TLS-free hop. Spring Boot documentation explicitly notes the possibility of HTTPS application combined with HTTP management; framework support does not replace deployment decisions. [Independent management SSL example](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.configuring-management-specific-ssl).

### 6.2. HTTP Application, HTTPS Management

From the section 5 lab, change `server.port` to `8080` and replace the `server.ssl` block with `enabled: false`. Keep port 9443 and the entire management keystore/certificate.

Then:

```text
Business server:   HTTP on port 8080
Management health: https://localhost:9443/actuator/health
```

The business line describes protocol/port; concrete paths are provided by the actual application. Management HTTPS does not automatically encrypt connections to business port 8080.

Change properties per independent case and restart; do not paste all examples in this article on top of one another into a single configuration.

### 6.3. No Automatic HTTP Redirect Just From Enabling SSL

When switching the main server to HTTPS via SSL config, Spring Boot does not automatically maintain an extra HTTP 8080 port or create a redirect to HTTPS. If you want two listeners or redirects, design them explicitly at the server/proxy. [Embedded web server SSL configuration guide](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html#howto.webserver.configure-ssl).

Similarly, do not call `http://localhost:9443` to test a listener configured for HTTPS. Sending plain HTTP to a TLS port can be rejected or produce different responses depending on the server; do not assign a fixed HTTP code for every protocol-mismatch case.

## 7. When Using SSL Bundles or an Intermediary Server

### SSL Bundles Are a Way to Name TLS Material

Spring Boot 3.3 supports named sets of SSL material configured under `spring.ssl.bundle`, using keystore or PEM formats. When a project already manages them, `server.ssl.bundle` and `management.server.ssl.bundle` let you select which bundle each server uses.

The hands-on lab uses direct PKCS12 properties to make each file easy to follow. Within the same SSL group, choose one consistent way to configure material; do not mix a bundle with direct keystore/PEM source properties as if they merge automatically. [SSL bundle configuration](https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html), [server SSL configuration binding](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html#howto.webserver.configure-ssl).

### Distinguishing External HTTPS From HTTPS to the JVM

A system may have the flow:

```text
Management tool --HTTPS--> proxy --HTTP or HTTPS--> Spring Boot
```

HTTPS on the tool side only proves the hop to the proxy is protected. Whether the proxy-to-management hop is HTTP or HTTPS depends on backend connection config and the Spring Boot listener.

If the proxy connects to the JVM over HTTPS, the proxy must also trust the management listener's certificate and use an appropriate hostname. If the proxy connects over HTTP, certificate configuration on the proxy does not turn the downstream hop into HTTPS. [Spring Boot notes when running behind a proxy](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server).

## 8. Layer-by-Layer Troubleshooting

| Symptom | Check First |
| --- | --- |
| Application fails to start when reading keystore | File exists, path relative to working directory, store type, password, and alias |
| Error retrieving private key | Does the alias have a private key entry; is the key password right |
| Cannot connect to port | Process running, bind address, port, and network path |
| TLS handshake fails | Using HTTPS; does the server have matching TLS/key config |
| Client does not trust certificate | Certificate chain and client trust source |
| Hostname error | Does the URL have a name/IP covered by the certificate SAN |
| TLS succeeds but HTTP 401/403 | HTTP authentication and authorization or protective filters |
| TLS succeeds but HTTP 404 | Port, path, and endpoint enable/exposure decisions |
| Health returns unhealthy status | Check component status, not just TLS config |

Do not fix a certificate error by adding endpoints to the exposure list. Conversely, a valid certificate does not create an endpoint that is disabled or unexposed.

HTTPS protects the connection and lets the client verify server identity; authorizing management operations is a separate requirement. If mTLS is needed, you must also configure client certificate requirements and server-side trust, then test both directions.

## 9. Self-Check on the Relationship Between the Two Servers

**Question 1.** Setting only `management.server.port=9443`: does the port number prove the endpoint is HTTPS?

**Answer:** No. You must determine the effective SSL configuration and where TLS terminates.

**Question 2.** The application and Actuator share port 8443. Can you use `management.server.ssl.*` to swap only the certificate for the `/actuator/health` path?

**Answer:** Not via this separate management SSL mechanism. TLS belongs to the shared listener; to configure management independently, use a different management port.

**Question 3.** Both ports use two different self-signed certificates. Which certificate must curl trust when calling port 9443?

**Answer:** The management certificate `management-local.crt` in the lab, and the URL name/IP must match the SAN. Trusting the application certificate does not establish trust for another self-signed certificate.

**Question 4.** Management HTTPS works, but the client gets HTTP 403 when calling an operation.

**Answer:** The connection already passed TLS to receive an HTTP response; examine access permissions and relevant filters instead of merely swapping keystores.

**Question 5.** Is reaching the endpoint via `--insecure` enough to prove trust configuration and certificate naming are correct?

**Answer:** No. A valid check must verify the certificate, such as using the right `--cacert` in the described test environment.
