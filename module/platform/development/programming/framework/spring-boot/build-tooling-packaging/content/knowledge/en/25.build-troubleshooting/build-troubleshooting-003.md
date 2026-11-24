# Diagnosing Proxy, TLS, Certificate, and Offline Mode Errors in Spring Boot Builds

## 1. Identify the Exact Layer Causing the Error

When Maven fails to download a dependency or plugin, the final message is often `Could not transfer artifact`, `Non-resolvable parent POM`, or `PluginResolutionException`. That is the failed operation; the root cause usually lies in DNS, TCP, proxy, HTTP authentication, TLS certificate validation, or the local repository.

There are four layers to distinguish:

1. **Network:** can the machine running Maven resolve DNS, open TCP, and reach the right host/port?
2. **Proxy/repository routing:** is Maven using the right proxy, bypass list, mirror, and repository endpoint?
3. **TLS/authentication:** can the JVM verify the certificate chain and hostname? Does the proxy/repository require credentials or a client certificate?
4. **Offline/cache:** does Maven have all dependencies, parent POMs, plugins, and plugin dependencies in the local repository?

```text
Developer / CI runner
       |
       v
Maven process + JDK
       |
       +--> settings.xml: proxy / mirror / credentials
       |
       v
Corporate proxy (if present)
       |
       +--> CONNECT tunnel for HTTPS
       |
       v
Maven repository / repository manager
       |
       v
Local repository (~/.m2/repository)
       |
       v
Compile -> Test -> Package -> Verify
```

Maven uses the JDK to perform TLS. A browser being able to open a URL does not prove Maven's JDK trusts that certificate. A laptop build can pass while CI fails because the runner uses a different JDK, truststore, proxy, or local cache.

Examples in this guide use Java 17, Spring Boot 3.5.0, and Maven 3.9.x to keep configurations consistent. This is a training version set; real projects should pin versions compatible with organizational support policies.

## 2. Confirm Which JDK Maven Is Running On

Before modifying certificates or proxies, check which JDK Maven actually uses:

```bash
mvn -version
java -version
where java
where mvn
```

On Linux/macOS:

```bash
which java
which mvn
echo "$JAVA_HOME"
```

`mvn -version` reports the Maven version, Java version, Java home, and OS. `java` on PATH may differ from the JDK used by Maven, the IDE, or the CI runner.

Check:
- `JAVA_HOME` points to the expected JDK.
- `mvn -version` shows a Java major version matching the project.
- Whether the IDE has its own Maven runner JDK.
- Whether the CI runner executes Maven inside a different container/toolchain.
- Whether the Maven Wrapper downloads a separate Maven distribution; inspect `distributionUrl` in `.mvn/wrapper/maven-wrapper.properties`.
- Whether `MAVEN_OPTS` adds a truststore or JVM properties to Maven.

**Do not import a certificate into an arbitrary JDK and assume Maven will use it.** Get Java home directly from `mvn -version`, then locate the corresponding truststore.

## 3. Distinguishing Proxy, Mirror, and Repository

### 3.1. A Proxy Is a Network Path

A proxy is an intermediary machine receiving requests from Maven and forwarding them to the repository. In a corporate network, a proxy can:
- Control which domains may be accessed.
- Require authentication.
- Log and rate-limit traffic.
- Use TLS inspection to inspect HTTPS traffic.
- Block direct Internet connections from developers/CI runners.

Maven configures proxies in `settings.xml`, usually at `~/.m2/settings.xml`. This is Maven runtime environment configuration, not dependency configuration in `pom.xml`.

### 3.2. A Mirror Is a Replacement Repository

A mirror is a URL Maven uses in place of a remote repository. For example, an organization runs a Nexus/Artifactory repository group acting as a proxy/cache for Maven Central. When configured with `mirrorOf=*`, Maven can route most remote repositories through that internal endpoint.

| Component | Question It Answers | Configuration |
| --- | --- | --- |
| Proxy | Which network path does Maven take outbound? | `<proxies>` in `settings.xml` |
| Mirror | Which repository endpoint does Maven fetch dependencies from? | `<mirrors>` in `settings.xml` |
| Repository | Where are artifacts stored/served? | `<repositories>` or `<pluginRepositories>` |
| Server credentials | Which account authenticates against the repository? | `<servers>` in `settings.xml` |
| TLS truststore | Which CAs does the JVM trust when verifying HTTPS? | JSSE truststore / JDK security configuration |

A single request can go through both a mirror and a proxy: Maven selects the mirror URL, then connects to that URL through the proxy if the proxy is active and the host is not listed in `nonProxyHosts`.

### 3.3. Request Flow

```text
pom.xml repository
      |
      v
Maven mirror selection
      |
      v
https://repo.corp.example/repository/maven-public/
      |
      v
Proxy selection (if host not bypassed)
      |
      v
TLS + HTTP authentication
      |
      v
Artifact download
```

If the mirror points to the wrong URL, adding a proxy will not fix the error. If the proxy is right but the JVM does not trust the CA, changing the mirror will not fix the TLS handshake. If an artifact has never been cached, enabling offline mode cannot conjure that dependency either.

## 4. Configuring Maven Proxy in settings.xml

### 4.1. Example settings.xml

The following example illustrates an internal HTTP proxy and a Maven mirror. Replace the hostname, port, repository path, and secret references with values provided by IT/DevOps.

**`~/.m2/settings.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
                              https://maven.apache.org/xsd/settings-1.2.0.xsd">

    <proxies>
        <proxy>
            <id>company-http-proxy</id>
            <active>true</active>
            <protocol>http</protocol>
            <host>proxy.corp.example</host>
            <port>8080</port>
            <username>${env.MAVEN_PROXY_USER}</username>
            <password>${env.MAVEN_PROXY_PASSWORD}</password>
            <nonProxyHosts>localhost|127.0.0.1|repo.corp.example|*.corp.example</nonProxyHosts>
        </proxy>
    </proxies>

    <mirrors>
        <mirror>
            <id>company-maven-mirror</id>
            <name>Company Maven repository group</name>
            <url>https://repo.corp.example/repository/maven-public/</url>
            <mirrorOf>*</mirrorOf>
        </mirror>
    </mirrors>

    <servers>
        <server>
            <id>company-maven-mirror</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
```

Maven settings support environment variable interpolation, so `MAVEN_PROXY_USER`, `MAVEN_PROXY_PASSWORD`, `MAVEN_REPO_USER`, and `MAVEN_REPO_TOKEN` can be supplied from a secret manager/CI variables. Never commit tokens or passwords to Git. Settings files containing credentials should have read permissions restricted to the build-runner account.

### 4.2. Why Is `<protocol>` `http` While the Repository URL Is `https`?

In proxy configuration, `<protocol>` describes the connection protocol **from Maven to the proxy**. It does not have to match the scheme of the repository URL.

Many corporate proxies accept HTTP connections on port 8080, then support HTTPS tunneling via HTTP `CONNECT`. Therefore, a common setup has:
- Proxy endpoint: `http://proxy.corp.example:8080`
- Repository endpoint: `https://repo.maven.apache.org/maven2/`

After the `CONNECT` command, the TLS handshake to the repository runs inside the tunnel. If the proxy performs TLS inspection, the certificate seen by the JVM may be issued by the corporate proxy; in that case, the appropriate CA must be in the truststore.

If the proxy endpoint itself uses HTTPS, verify the protocol/port per the proxy admin team's guidance and Maven transport version.

### 4.3. nonProxyHosts

`nonProxyHosts` lists hosts Maven connects to directly, bypassing the proxy. Maven uses `|` to separate patterns and supports wildcards.

```xml
<nonProxyHosts>localhost|127.0.0.1|*.svc.cluster.local|*.corp.example</nonProxyHosts>
```

An incorrect `nonProxyHosts` can cause:
- An internal repository that needs direct access to be routed through the Internet proxy.
- An internal host to fail resolution from the proxy.
- The proxy to reject private domains.
- Requests to take the wrong route even though internal DNS works.

Do not add `*` arbitrarily, as it can make all hosts bypass the proxy. List the exact internal domains required by your organization.

### 4.4. Unauthenticated Proxy

If the proxy does not require a username/password, omit those two elements:

```xml
<proxy>
    <id>company-http-proxy</id>
    <active>true</active>
    <protocol>http</protocol>
    <host>proxy.corp.example</host>
    <port>8080</port>
    <nonProxyHosts>localhost|127.0.0.1|*.corp.example</nonProxyHosts>
</proxy>
```

Some enterprise proxies use SSO/NTLM/Kerberos or an OS agent instead of Basic authentication. Verify the mechanism supported by the proxy and Maven transport; do not move passwords into URLs or enable insecure authentication options.

### 4.5. Check Mirror ID and Server ID

When Maven uses a mirror, `<server><id>` must match the ID of the repository/mirror Maven actually connects to. In the example, the ID is `company-maven-mirror` in both `<mirror>` and `<server>`.

If credentials are declared only for `central` yet Maven routes through a mirror with ID `company-maven-mirror`, Maven may not use the credentials you expect.

If the organization uses `mirrorOf=*`, verify that the mirror URL is a repository group granted access to both dependencies and plugins. A repository holding only a team's release packages may lack plugins/parent POMs needed for the build.

### 4.6. Using a Dedicated Settings File

```bash
mvn -s .mvn/company-settings.xml -B -ntp clean verify
```

When using `-s`, ensure that file includes all required proxies, mirrors, credentials, and profiles. Do not assume it inherits everything from other user settings. Maven has global settings and user settings; user settings take precedence when the two files are merged.

## 5. Check the Network Before Changing Maven

### 5.1. Check DNS and TCP

On Windows PowerShell:

```powershell
Resolve-DnsName proxy.corp.example
Test-NetConnection proxy.corp.example -Port 8080
Resolve-DnsName repo.maven.apache.org
Test-NetConnection repo.maven.apache.org -Port 443
```

In networks requiring a proxy, direct connections to repositories may be intentionally blocked. In that case, testing TCP to the proxy matters more; do not conclude the Internet is down just because a direct connection fails.

On Linux:

```bash
getent hosts proxy.corp.example
nc -vz proxy.corp.example 8080
getent hosts repo.maven.apache.org
```

`nc` only tests TCP to a host/port; it does not verify proxy authentication, HTTP responses, or TLS trust.

### 5.2. Check HTTPS with curl

If the proxy supports HTTP CONNECT:

```bash
curl -I -v \
  --proxy http://proxy.corp.example:8080 \
  https://repo.maven.apache.org/maven2/
```

If the proxy requires authentication, use an approved credentials mechanism; avoid placing passwords directly on the command line because process lists, shell history, or CI logs may record them.

On Windows, invoke `curl.exe` to avoid PowerShell's alias:

```powershell
curl.exe -I -v --proxy http://proxy.corp.example:8080 https://repo.maven.apache.org/maven2/
```

`curl` and Maven can use different trust stores. On Windows, curl may use the Windows certificate store while Maven uses the JDK truststore. Thus, curl succeeding only proves connectivity and curl's trust, not that Java TLS will succeed.

### 5.3. Inspect the TLS Chain

If OpenSSL is available, check HTTPS through the HTTP proxy:

```bash
openssl s_client \
  -proxy proxy.corp.example:8080 \
  -connect repo.maven.apache.org:443 \
  -servername repo.maven.apache.org \
  -showcerts
```

Observe:
- Whether the certificate subject/SAN matches the hostname.
- Whether the issuer is a public CA or a corporate inspection CA.
- Whether the certificate is still valid or expired.
- Whether the server sends required intermediate certificates.
- What verify return code OpenSSL reports.

You can inspect the certificate returned directly by a server with:

```bash
keytool -printcert -sslserver repo.maven.apache.org:443 -rfc
```

`keytool -sslserver` connects directly and does not replace testing through a proxy. If the network only allows CONNECT via a proxy, use OpenSSL or a TLS tool provided by your organization to test the exact route.

## 6. Distinguishing Proxy Errors from Repository Errors

| HTTP/Status or Exception | Common Meaning | Next Check |
| --- | --- | --- |
| `407 Proxy Authentication Required` | Proxy needs credentials or credentials are wrong | Proxy username/password, auth mechanism, proxy ID |
| `401 Unauthorized` | Repository/server requires authentication | `<servers>` ID matches mirror/repository ID, token |
| `403 Forbidden` | Reached server, but policy denies access | Repository permissions, group membership, artifact policy |
| `404 Not Found` | Artifact/path does not exist at selected endpoint | Mirror URL, repository path, GAV/plugin coordinates |
| `429 Too Many Requests` | Rate limit | Repository manager throttling, CI concurrency |
| `502` / `503` / `504` | Proxy/gateway/upstream unavailable or timed out | Proxy logs, repository manager health, remote status |
| `UnknownHostException` | DNS failed to resolve host | Which host is being resolved: proxy or repository |
| `ConnectException: Connection refused` | Host reachable, but port not accepting connections | Proxy host/port, service listener, firewall |
| `SocketTimeoutException` | Connection or response timed out | Route, proxy load, repository latency, firewall |
| `SSLHandshakeException` | TLS handshake failed | Certificate chain, hostname, truststore, protocol, mTLS |

**Do not confuse 407 with 401.** 407 is proxy authentication; 401 is usually repository/server authentication. If Maven uses a mirror, verify the actual mirror ID in settings before rotating tokens.

A `Could not transfer artifact` message can wrap the underlying exception. Use `-e` to view stack traces and `-X` when more detail is needed:

```bash
mvn -B -ntp -U -e validate
mvn -B -ntp -U -X validate
```

`-X` creates very verbose logs. Before sending logs externally, strip credentials, tokens, authorization headers, private repository URLs, usernames, and internal details. Never post the full `settings.xml` to public tickets.

## 7. TLS Certificates and Truststores in Java

### 7.1. Truststore and Keystore Are Different

- **Truststore:** contains CAs/certificates Java trusts when verifying a server's certificate.
- **Keystore:** contains the client/server's own private key and certificate, typically used when mutual TLS (mTLS) is required.

When Maven accesses `https://repository.example`, the JVM verifies the repository's certificate chain using the truststore. When a repository requires a client certificate, Maven may need a keystore holding the private key and corresponding client certificate.

`PKIX path building failed` usually indicates the JVM cannot build a certificate chain back to a trust anchor it trusts. Do not try to fix this error by adding a client private key when the real issue is a missing trusted CA.

### 7.2. Which Truststore Does the JVM Choose?

According to JDK JSSE, if `javax.net.ssl.trustStore` is specified, the JVM uses that file. If the property points to a non-existent file, JSSE may initialize a trust manager with an empty truststore. If unspecified, the JVM looks for `jssecacerts`, then `cacerts` in Java home.

Check:
- `mvn -version` to determine Java home.
- The value of `javax.net.ssl.trustStore` in JVM options.
- Whether the truststore file exists and is readable.
- Whether the truststore type is accurately `JKS` or `PKCS12`.
- Whether the certificate is an organization-approved CA.
- Whether the server sends all intermediate certificates.

### 7.3. Inspecting JDK cacerts

Use the `keytool` shipped with the JDK that Maven uses:

```bash
keytool -list -cacerts
keytool -list -v -cacerts -alias company-root-ca
```

Do not assume every JDK installed on a machine shares the same `cacerts`. The IDE, Maven CLI, Maven Wrapper, CI containers, and runtime containers may each use different Java homes.

### 7.4. Creating a Dedicated Truststore and Importing a Corporate CA

In enterprises, HTTPS inspection can cause a proxy to replace a public server's certificate with one signed by a corporate CA. The JDK must trust the verified corporate root CA.

Safe workflow:

1. Obtain the CA certificate file from a verified internal source (IT/security PKI).
2. Verify the SHA-256 fingerprint via an independent, trusted channel.
3. Inspect the certificate's subject/issuer/validity.
4. Create a dedicated truststore for Maven or the build runner.
5. Import the CA into that truststore.
6. Point the JVM running Maven to that truststore.
7. Re-run the build and confirm the TLS error is resolved.

Inspect the certificate file before importing:

```bash
keytool -printcert -file corp-root-ca.cer
```

Create a PKCS12 truststore and import:

```bash
keytool -importcert \
  -alias corp-proxy-root \
  -file corp-root-ca.cer \
  -keystore "$HOME/.m2/corp-truststore.p12" \
  -storetype PKCS12
```

After importing, verify the entry:

```bash
keytool -list -v \
  -keystore "$HOME/.m2/corp-truststore.p12" \
  -storetype PKCS12 \
  -alias corp-proxy-root
```

Read the fingerprint carefully before confirming the import. Do not import a certificate merely because a browser displays it; verify the certificate comes from official PKI/IT.

### 7.5. Configuring Maven to Use a Dedicated Truststore

On Linux/macOS:

```bash
export MAVEN_OPTS="-Djavax.net.ssl.trustStore=$HOME/.m2/corp-truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12"
mvn -B -ntp -U clean verify
```

On Windows PowerShell:

```powershell
$env:MAVEN_OPTS = "-Djavax.net.ssl.trustStore=$env:USERPROFILE\.m2\corp-truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12"
mvn -B -ntp -U clean verify
Remove-Item Env:MAVEN_OPTS
```

If the truststore requires a password, supply it via a secret mechanism appropriate for the CI/JVM process and restrict read permissions. Avoid writing passwords into shell history, source code, or logs. Truststores hold only public CA certificates, yet the file still needs governance to prevent unauthorized modification.

You can configure the truststore in `MAVEN_OPTS` for a single run; do not leave an old truststore path lingering silently in the environment to affect other builds.

### 7.6. Why Avoid Overwriting Global cacerts?

Importing a CA directly into the JDK's `cacerts` can work, but:
- It requires write permissions to the JDK installation.
- A JDK upgrade may replace the truststore file.
- Multiple projects sharing one JDK broaden the blast radius.
- It is hard to audit who added the CA and when.
- Ephemeral CI runners require re-provisioning.

A dedicated truststore is generally easier to version, mount, and manage per environment. If the organization requires a system truststore, follow their standard certificate management workflow.

### 7.7. Certificate Chain Missing an Intermediate

A server typically sends a leaf certificate and the intermediate certificates needed to chain to a root CA. The root CA might already be trusted by the truststore, yet if the server fails to send an intermediate, some clients cannot build the chain.

In that situation:
- Ask the repository/proxy administrator to configure the full certificate chain properly.
- Inspect the output of `openssl s_client -showcerts`.
- Compare issuer/subject across the certificates.
- Check whether the root CA is already trusted by the truststore.

Do not arbitrarily import every host's leaf certificate into the truststore as a default workaround. Fixing the server chain or installing the verified corporate root CA is generally more durable.

## 8. Analyzing Common TLS Errors

| Error | Meaning | What to Check |
| --- | --- | --- |
| `PKIX path building failed` | Cannot build a trust chain to a trusted CA | Truststore, corporate CA, missing intermediate |
| `unable to find valid certification path` | JVM cannot find a valid certificate path | Active JDK truststore, root CA |
| `No subject alternative DNS name matching ...` | Hostname does not match certificate SAN | URL hostname, reverse proxy, certificate SAN |
| `CertificateExpiredException` | Certificate is expired or not yet valid | Certificate validity and system clock |
| `handshake_failure` | TLS negotiation or authentication failed | Protocol/cipher compatibility, mTLS requirement |
| `protocol_version` | Both sides share no common TLS version | JDK policy, server TLS configuration |
| `certificate_required` | Server requires a client certificate | Client keystore and mTLS configuration |
| `bad_certificate` | Peer rejected the sent certificate | Client cert chain, EKU, expiry, issuer |
| `Connection reset` during handshake | Connection closed mid-handshake | Proxy inspection, firewall, server logs |

### 8.1. PKIX path building failed

Common causes:
- A corporate proxy re-signs certificates, but the JDK does not trust the corporate CA yet.
- An older JDK has an outdated root CA store.
- Maven uses a different JDK than the one into which you imported the certificate.
- Custom truststore path is wrong or the file does not exist.
- Server sends an incomplete certificate chain.
- A security property points to an empty truststore.

How to check:
1. Run `mvn -version`.
2. Identify Java home.
3. Check `MAVEN_OPTS` and `javax.net.ssl.trustStore`.
4. Check the certificate chain through the exact proxy route.
5. Verify the corporate CA fingerprint.
6. Import the verified CA into the right truststore.
7. Re-run dependency/plugin resolution.

### 8.2. Hostname Mismatch

If a certificate has a SAN for `repo.company.example` yet Maven calls `repo-alias.company.example`, Java can reject the connection even if the certificate is trusted by a CA.

Do:
- Use the canonical hostname provided by the repository administrator.
- Check DNS aliases/load balancers.
- Issue a certificate with matching SANs.
- Avoid disabling hostname verification.

A truststore only resolves trust chains; it does not make a certificate with the wrong hostname valid.

### 8.3. Expired Certificate or Wrong Clock

A certificate has `Not Before` and `Not After` timestamps. A runner machine with the wrong date/time can evaluate a valid certificate as not yet valid or expired.

Check the OS clock/NTP, leaf/intermediate certificates, proxy/load balancer/repository certificates, and JVM system time. Do not roll back the system clock to bypass expiry; fix time synchronization or renew the certificate at the issuing authority.

### 8.4. TLS Protocol/Cipher Mismatch

If the server only permits a TLS version/cipher that the JDK does not support or that security policy has disabled, the handshake can fail. Check JDK version, security policy, server-supported TLS versions, proxy CONNECT/TLS passthrough, and JSSE handshake logs.

Do not enable TLS 1.0/1.1 or weak ciphers as a permanent fix. Update the server/proxy or JDK to achieve a supported TLS configuration.

### 8.5. Mutual TLS (mTLS)

Some internal repositories require a client certificate:
- The truststore verifies the server's certificate.
- The keystore holds the client private key and client certificate.
- The certificate must be unexpired and trusted by the server.
- The client certificate needs the proper key usage/extended key usage per policy.

Maven SSL configuration can use `javax.net.ssl.keyStore` and `javax.net.ssl.keyStoreType`. Never put private keys into repository source or public Docker image build contexts.

## 9. Enabling JSSE Debug When Needed

When the exception does not clearly state which certificate was rejected, JSSE debug lets you inspect the trust manager, certificate chain, and TLS handshake.

Linux/macOS:

```bash
MAVEN_OPTS="-Djavax.net.debug=ssl,handshake,trustmanager" \
  mvn -B -ntp -U validate
```

Windows PowerShell:

```powershell
$env:MAVEN_OPTS = "-Djavax.net.debug=ssl,handshake,trustmanager"
mvn -B -ntp -U validate
Remove-Item Env:MAVEN_OPTS
```

Debug options can produce huge logs. Use them in a controlled single reproduction, store logs securely, and redact before sharing.

Useful lines:
- `trustStore is: ...`: which truststore the JVM is using.
- `Reloaded ... trust certs`: number of loaded certificates.
- Certificate subject/issuer: the CA chain being seen.
- `Found trusted certificate`: the trust manager found a trust anchor.
- TLS protocol/cipher negotiation: which protocol/cipher both sides agreed on.

JSSE debug only shows the JVM's perspective. Combine proxy logs, repository logs, and network checks to pinpoint which component closed the connection.

## 10. How Does Maven Offline Mode Work?

### 10.1. The Local Repository Is a Cache on the Machine Running Maven

The Maven local repository defaults to `~/.m2/repository`; on Windows it is typically `%USERPROFILE%\.m2\repository`.

The local repository stores downloaded dependencies/plugins and locally installed artifacts. It does not automatically sync across developers or CI runners. When Maven needs an artifact absent from the local repository, Maven normally reaches out to remote repositories to download it. Offline mode prevents Maven from making those remote requests.

### 10.2. Enabling Offline via CLI

```bash
mvn -o -B -ntp clean verify
```

`-o` is `--offline`. This enables offline mode for a single run.

It can be configured permanently in `settings.xml`:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <offline>true</offline>
</settings>
```

When network connectivity returns, remove the offline configuration or set it to `false`; otherwise Maven will continue refusing to access remote repositories.

### 10.3. Offline Mode Does Not Download or Generate Missing Dependencies

An offline build succeeds only when the local repository already contains all required:
- Parent POMs and imported BOMs.
- Dependencies for the exact active profiles/scopes.
- Maven plugins invoked in the lifecycle.
- Plugin dependencies.
- Maven extensions in `.mvn/extensions.xml`.
- Metadata/artifacts required by specific plugins/tasks.
- The Maven distribution if using Maven Wrapper and the distribution has not been downloaded yet.

A project that previously ran `mvn package` may still lack plugins used in the `verify` phase, an integration test profile, or a release profile. Offline `clean verify` can fail even though offline `compile` succeeds.

### 10.4. Warming Up the Local Repository Before Going Offline

While online and with proxy/mirror configured properly, run:

```bash
mvn -B -ntp dependency:go-offline
```

Then test the build with the exact profiles and goals:

```bash
mvn -B -ntp -Pprod clean verify
```

Finally, verify offline:

```bash
mvn -o -B -ntp -Pprod clean verify
```

`dependency:go-offline` helps download project dependencies and plugins that the Maven Dependency Plugin can resolve. It does not guarantee that every custom plugin, dynamic profile, extension, or build task is cached. The definitive check remains running the exact build command in offline mode in the target environment.

### 10.5. Profiles Must Match

If the online build uses profile `prod` while the warm-up step did not activate that profile, dependencies specific to that profile may remain uncached.

```bash
mvn -B -ntp -Pprod dependency:go-offline
mvn -B -ntp -Pprod clean verify
mvn -o -B -ntp -Pprod clean verify
```

Verify active profiles with `mvn help:active-profiles`. If profiles depend on OS/JDK/properties, ensure the warm-up and offline build environments are compatible.

### 10.6. Maven Wrapper Also Needs Its Distribution

Maven Wrapper may download the Maven distribution before Maven runs. Consequently, Maven's `settings.xml` cannot fix wrapper distribution download errors if the Maven process has not even started.

Inspect `.mvn/wrapper/maven-wrapper.properties`, check `distributionUrl`, and ensure the distribution is already available or the wrapper URL is accessible through the appropriate network/proxy. Offline builds must cache/provision the Maven distribution as well, not just `~/.m2/repository`.

## 11. Diagnosing Offline and Local Repository Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `Cannot access ... in offline mode` | Artifact is not yet in the local repository | Warm up while online or use an internal repository |
| `Plugin ... could not be resolved` | Plugin or plugin dependency is not cached | Run the needed plugin/goal while online |
| `Non-resolvable parent POM` while offline | Parent POM not cached or different repository ID/path | Resolve parent online via the right mirror first |
| `compile` passes, `verify` fails | Plugin in a later phase is not cached | Warm up the `verify` lifecycle and profiles |
| Developer machine passes, offline CI fails | Local repositories differ between environments | Seed CI cache or use an internal repository |
| `mvn -o` still runs a task needing remote data | Plugin performs its own network request | Check plugin docs/config; stage local data or exclude task in offline profile |
| Snapshot does not update | Offline cannot check new remote metadata | Switch online to resolve snapshots per policy |
| Partial/corrupt artifact | Cache has incomplete files or checksum mismatch | Online, delete the specific artifact version directory, then re-download |
| `.lastUpdated` prevents re-resolution | Maven recorded a previous failed download | Online run `-U`, inspect repository and metadata |
| Wrapper fails to run offline | Maven distribution is not cached | Provision distribution before disconnecting network |

### 11.1. Do Not Delete the Entire `.m2` as a First Step

Deleting the entire local repository forces Maven to re-download all dependencies/plugins. It can make things worse when offline, when proxy/TLS is still broken, when repositories rate-limit, or when CI caches are large.

If a specific artifact version is confirmed corrupted:
1. Record the GAV/plugin coordinates and exact path.
2. Ensure repository connectivity is already working.
3. Delete only the failing version directory in the local repository.
4. Re-run with `-U` if metadata needs refreshing.
5. Verify checksums and the artifact after downloading.

Do not delete other caches without supporting evidence.

### 11.2. Check the Local Repository Path

The path can be customized via `localRepository` in `settings.xml`. If the Maven CLI, IDE, and CI use different settings, they may read from different caches.

Check the `localRepository` path, the `settings.xml` actually loaded, Maven user home, container volume mounts, and cache directory permissions. Do not copy an entire `.m2` directory arbitrarily across machines if the cache contains lock/partial files or incompatible ownership.

## 12. Proxy and TLS When Building in Docker

Maven running on the host and Maven running inside a Docker builder stage are two distinct environments.

### 12.1. Docker Build Proxy

Docker supports proxy build arguments such as `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`, and `ALL_PROXY`. Proxies can be supplied via Docker client config or command line:

```bash
docker build \
  --build-arg HTTP_PROXY=http://proxy.corp.example:8080 \
  --build-arg HTTPS_PROXY=http://proxy.corp.example:8080 \
  --build-arg NO_PROXY=localhost,127.0.0.1,.corp.example \
  .
```

Docker client config can contain proxy settings in `~/.docker/config.json`:

```json
{
  "proxies": {
    "default": {
      "httpProxy": "http://proxy.corp.example:8080",
      "httpsProxy": "http://proxy.corp.example:8080",
      "noProxy": "localhost,127.0.0.1,.corp.example"
    }
  }
}
```

The Docker CLI can automatically pass proxy build args into builds. These settings apply to the build/container process; they do not necessarily configure the proxy for the Docker daemon or Docker Desktop. If `FROM` images cannot be pulled, inspect the proxy configuration of the Docker daemon/BuildKit/Docker Desktop for your environment.

### 12.2. Do Not Store Proxies in a Dockerfile Using `ENV`

Do not write:

```dockerfile
ENV HTTPS_PROXY=http://proxy.corp.example:8080
```

Proxy configuration via `ENV` can persist into image configuration/layers and be exposed in image metadata or runtime containers. Use proxy build args or Docker client config per official documentation; never bake usernames/passwords into images.

### 12.3. Maven in a Multi-Stage Docker Build

Example Dockerfile building a Spring Boot app:

```dockerfile
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY pom.xml .
COPY src ./src
RUN mvn -B -ntp -DskipTests package

FROM eclipse-temurin:17-jre AS runtime
WORKDIR /app
COPY --from=build /workspace/target/release-demo-0.1.0.jar /app/app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Here Maven runs inside the builder image. If Maven needs a corporate CA:
- The builder JDK needs a truststore containing the verified corporate root CA.
- The builder network needs the right proxy/mirror.
- `settings.xml` can be mounted or provided in the build stage using a secret mount.
- Do not copy proxy passwords, Maven tokens, or private keys into the final image.
- If the application inside the final container needs to make internal HTTPS calls, the runtime JRE of the final stage also needs the corresponding truststore.

**Builder truststore and runtime truststore are two separate environments.** A build downloading dependencies successfully does not mean the running container will trust the same CA.

### 12.4. Using BuildKit Secrets for Maven Settings

If a build requires Maven settings containing credentials, avoid `COPY settings.xml` with passwords into an image layer. You can use a BuildKit secret mount:

```dockerfile
# syntax=docker/dockerfile:1
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY pom.xml .
COPY src ./src
RUN --mount=type=secret,id=maven_settings,target=/root/.m2/settings.xml \
    mvn -s /root/.m2/settings.xml -B -ntp clean verify

FROM eclipse-temurin:17-jre AS runtime
WORKDIR /app
COPY --from=build /workspace/target/release-demo-0.1.0.jar /app/app.jar
USER 10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Build:

```bash
docker build \
  --secret id=maven_settings,src="$HOME/.m2/settings.xml" \
  -t release-demo:local .
```

BuildKit secret mounts provide the file only for that RUN step and do not commit it into an image layer the way a normal `COPY` does. Still, check build logs and scripts so secrets are never printed to output. Do not use personal developer credentials in production CI; issue least-privilege tokens from the CI secret store.

## 13. Java 17 Spring Boot Example Project for Reproduction

We use a small project to verify Maven dependency resolution and the build lifecycle. This project needs no proxy configuration in `pom.xml`; proxy/mirror/truststore are managed in the Maven environment.

### 13.1. Project Structure

```text
release-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/release/
                └── ReleaseDemoApplication.java
```

### 13.2. Complete pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>release-demo</artifactId>
    <version>0.1.0</version>
    <name>release-demo</name>
    <packaging>jar</packaging>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
```

### 13.3. Runnable Java Application

**`src/main/java/com/example/release/ReleaseDemoApplication.java`:**

```java
package com.example.release;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ReleaseDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReleaseDemoApplication.class, args);
    }

    @GetMapping("/ready")
    public String ready() {
        return "ready";
    }

    @GetMapping("/version")
    public String version() {
        return "release-demo:0.1.0";
    }
}
```

### 13.4. Build Through Proxy/Mirror

Once `settings.xml` is properly configured and the JDK truststore trusts the required CA:

```bash
mvn -B -ntp -U clean verify
```

Maven downloads the parent POM, Spring Boot dependencies, and plugins, then compiles/tests/packages. If an error occurs, analyze the root exception before changing the project.

### 13.5. Run the Application After Building

```bash
java -jar target/release-demo-0.1.0.jar
```

Another terminal:

```bash
curl -fsS http://localhost:8080/ready
curl -fsS http://localhost:8080/version
```

Response bodies respectively:

```text
ready
release-demo:0.1.0
```

These curl commands only verify the local application. They do not prove Maven proxy/TLS is working; that was verified during Maven dependency resolution.

### 13.6. Run Offline Build

After an online build succeeds and the cache has been warmed up:

```bash
mvn -o -B -ntp clean verify
```

If the command fails due to a missing plugin/dependency, record the exact artifact coordinates reported missing, switch online to download via the configured mirror, and then re-run offline. Do not change versions or delete the entire local repository to hide a cache error.

## 14. Small Java 17 Program to Test HTTPS from the JVM

When suspecting a TLS error inside the application runtime rather than Maven, you can use Java 17's `HttpClient` to test the same endpoint from the exact JDK running.

**`HttpsProbe.java`:**

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class HttpsProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java HttpsProbe <https-url>");
            System.exit(2);
        }

        URI uri = URI.create(args[0]);
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(20))
                .GET()
                .build();

        HttpResponse<Void> response = client.send(
                request,
                HttpResponse.BodyHandlers.discarding()
        );

        System.out.println("HTTP status: " + response.statusCode());
    }
}
```

Compile and run:

```bash
javac HttpsProbe.java
java HttpsProbe https://repo.maven.apache.org/maven2/
```

If the JVM needs an HTTP proxy for an HTTPS target:

```bash
java \
  -Dhttps.proxyHost=proxy.corp.example \
  -Dhttps.proxyPort=8080 \
  HttpsProbe https://repo.maven.apache.org/maven2/
```

These are Java networking system properties for the sample program; they do not replace Maven `<proxies>` in `settings.xml`. Applications using custom HTTP clients, custom `ProxySelector`s, or separate proxy authentication may need different configuration. If the JVM reports `SSLHandshakeException`, check the truststore of the exact JDK running the program.

## 15. Diagnostic Workflow from Quick to Deep

1. **Record the root error:** capture the deepest exception, URL, artifact coordinates, and failing Maven phase.
2. **Verify the toolchain:** `mvn -version`, Maven Wrapper distribution, Java home, and `MAVEN_OPTS`.
3. **Check the network:** DNS and TCP to the proxy; test the direct repository only if policy allows.
4. **Check the proxy:** host/port/protocol, active flag, credentials, and `nonProxyHosts`.
5. **Check the mirror:** mirror URL, `mirrorOf`, repository group, and server ID.
6. **Check the HTTP status:** distinguish 407, 401, 403, 404, 429, and 5xx.
7. **Check TLS:** certificate chain, SAN, expiry, JDK truststore, and corporate CA.
8. **Check mTLS:** only when the server requires a client certificate; verify the client keystore.
9. **Check Maven cache:** whether the artifact exists, `.lastUpdated`, plugin dependencies, and profiles.
10. **Try offline:** only after warming up with the exact build command and Maven Wrapper distribution.
11. **Check Docker separately:** Docker daemon/BuildKit proxy, builder JDK truststore, and final runtime JRE truststore.
12. **Record evidence:** redacted settings IDs, Maven/JDK versions, root cause exception, HTTP status, and network/TLS check results.

### 15.1. Decision Tree

```text
Maven download/build fails
          |
          v
   DNS/TCP to proxy works?
      /          \
    No            Yes
     |             |
Fix DNS/route      v
/host/port     HTTP request goes through proxy?
                  /          \
                No            Yes
                 |             |
          Check proxy config   v
                       What is the HTTP status?
                       /      |       \
                    407     401/403   5xx
                     |        |        |
                Proxy auth  Repo auth  Proxy/repo
                                      health/policy
                       |
                       v
                 TLS handshake passes?
                    /       \
                  No         Yes
                   |          |
             Truststore/chain  v
             SAN/expiry/mTLS   Artifact in
                               local cache?
                                /       \
                              No         Yes
                               |          |
                         Warm up online  Check plugin/
                         with profile    project config
                               |
                               v
                         Re-run with -o
```

## 16. Common Enterprise Environment Issues

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Browser opens Maven Central, Maven fails PKIX | Browser and JDK use different truststores | Check Maven Java home and CA in truststore |
| Curl passes, Maven gets 407 | Curl uses proxy credentials from env/config; Maven lacks them | Configure proxy in Maven settings |
| Maven gets 407 despite right username | Unsupported proxy auth scheme or wrong credential scope | Verify auth mechanism with proxy admin |
| Maven gets 401 with internal mirror | Server ID mismatches mirror ID or wrong token | Check `<servers>` ID and token scope |
| Maven gets 403 | User authenticates, lacks artifact/group permission | Check repository role/policy |
| `PKIX path building failed` only on VPN | VPN/proxy alters TLS chain or route | Check certificate issuer and proxy path on VPN |
| `PKIX path building failed` after JDK upgrade | New truststore differs or corporate CA not provisioned | Import verified CA into new JDK's truststore |
| Maven CLI passes, IDE fails | IDE uses a different Maven/JDK/settings | Sync runner JDK and user settings in IDE |
| Laptop passes, CI fails | CI container lacks proxy/CA/cache | Provision proxy, CA, settings, and warm cache for runner |
| Maven passes, Docker build fails | Different BuildKit/daemon route or builder image | Check Docker proxy and builder JDK |
| Docker build passes, app container fails HTTPS | Runtime JRE does not trust internal CA | Install CA into final runtime image/truststore |
| Offline build missing plugin | Plugin not cached | Warm up the right lifecycle online |
| Wrapper fails to download Maven | Wrapper distribution URL unreachable | Cache/provision Maven distribution separately |
| Snapshot does not update | Offline or metadata update policy | Switch online and check snapshot metadata |
| Checksum error | Interrupted download, proxy/repo corruption, or inconsistent artifact | Verify repository/checksum; re-download the specific artifact |

## 17. Security When Fixing Proxy and TLS

The following shortcuts may get a build command past an error, but they weaken server verification and introduce supply-chain risk:

- Enabling SSL insecure mode or skipping hostname verification.
- Using a trust-all `TrustManager`.
- Disabling TLS certificate validation in curl/Java/Maven.
- Importing certificates from unverified sources.
- Copying private keys/client keystores into Git or Docker images.
- Placing proxy passwords/repository tokens on the command line or in logs.
- Using a single admin token for all developers/CI jobs.
- Disabling checksum policy to ignore artifact integrity errors.
- Running release builds with unverified caches.

**Never use TLS bypass as a production fix.** If you need to distinguish a truststore error from a proxy error in a controlled test, use an isolated environment with security team approval; return to normal certificate validation afterward.

Operational principles:
1. Trust only verified root CAs, not every certificate.
2. Fix hostnames/certificate chains on the server if misconfigured.
3. Use least-privilege tokens and separate proxy credentials from repository credentials.
4. Use a CI secret store or protected settings file.
5. Never copy credentials into final images.
6. Pin JDK/Maven/toolchain and record versions.
7. Keep checksum verification and artifact repository policies enabled.
8. Track certificate expiration and rotation procedures.
9. Store diagnostic logs with redaction.
10. Test offline caches on the exact profiles/goals before deploying to air-gapped environments.

## 18. Operational Checklist

### Proxy and Repository

- [ ] Verified Maven/JDK via `mvn -version`.
- [ ] Correct `settings.xml` is being used.
- [ ] Proxy host/port/protocol matches organization values.
- [ ] `nonProxyHosts` includes the right internal domains.
- [ ] Mirror URL is a repository group containing required dependencies and plugins.
- [ ] `mirrorOf` does not misroute internal repositories.
- [ ] Server ID matches mirror/repository ID.
- [ ] Proxy credentials and repository tokens are managed separately.
- [ ] HTTP status is attributed to the right rejecting party.

### TLS and Certificates

- [ ] Inspected the certificate chain over the right network route.
- [ ] Verified corporate CA fingerprint via a trusted channel.
- [ ] Truststore belongs to the exact JDK Maven uses.
- [ ] Custom truststore path/type exists and is readable.
- [ ] Hostname matches SAN.
- [ ] Certificate is unexpired and system clock is accurate.
- [ ] Server sends the full intermediate chain.
- [ ] mTLS keystore is configured only when the server actually requires it.
- [ ] Certificate/hostname validation is not disabled.

### Offline and Docker

- [ ] Warmed up dependencies, plugins, and profiles while online.
- [ ] Maven Wrapper distribution is cached/provisioned.
- [ ] Offline test runs the exact required lifecycle/profile.
- [ ] Local repository path and permissions are clear.
- [ ] Did not delete all of `.m2` without confirmed cache corruption.
- [ ] Docker daemon/BuildKit has the right proxy.
- [ ] Builder JDK truststore has required CAs.
- [ ] Final runtime JRE truststore has required CAs if the app makes internal HTTPS calls.
- [ ] No proxy credentials or Maven tokens are placed in the image.

## 19. Official Documentation

- Apache Maven – [Settings Reference](https://maven.apache.org/settings.html): user/global settings, proxies, mirrors, servers, and profiles.
- Apache Maven – [Configuring a Proxy](https://maven.apache.org/guides/mini/guide-proxies.html): proxy fields, authentication, and `nonProxyHosts`.
- Apache Maven – [Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories): local/remote repositories, internal repositories, and offline mode.
- Apache Maven – [Remote Repository Access through Authenticated HTTPS](https://maven.apache.org/guides/mini/guide-repository-ssl.html): truststore, keystore, and JSSE system properties.
- Apache Maven – [Maven Settings Reference 3.9](https://maven.apache.org/ref/3.9.0/maven-settings/settings.html): `settings.xml` structure and proxy fields.
- Oracle Java – [JSSE Reference Guide](https://docs.oracle.com/en/java/javase/24/security/java-secure-socket-extension-jsse-reference-guide.html): TLS, truststore selection, JSSE debug, and certificate validation.
- Docker – [Use a Proxy Server with the Docker CLI](https://docs.docker.com/engine/cli/proxy/): Docker client proxy configuration, build args, and securing proxy values.
- Docker – [Build Variables](https://docs.docker.com/build/building/variables/): predefined proxy/build arguments and BuildKit behavior.
- Spring Boot 3.5 – [Maven Plugin](https://docs.spring.io/spring-boot/3.5/maven-plugin/): Maven build integration for Spring Boot.
- Spring Boot 3.5 – [System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html): Java/Maven compatibility for Spring Boot 3.5.

**Remember:** When Maven fails to download a dependency, identify the failing layer first: network, proxy/mirror, HTTP authentication, TLS trust, or local cache. Proxies are configured in `settings.xml`; TLS trust is determined by the JDK truststore; offline mode works only when all required artifacts/plugins are already in the local repository. With Docker, builder and runtime are two separate environments, so proxy and CA must be verified in whichever stage makes the connection.