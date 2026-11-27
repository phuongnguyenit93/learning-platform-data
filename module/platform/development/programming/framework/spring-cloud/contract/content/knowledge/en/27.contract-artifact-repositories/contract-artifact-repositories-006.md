# Authentication, Proxies, and Repository Access in CI

In microservices architectures, **Spring Cloud Contract** delivers value when the producer not only generates tests from Groovy/YAML DSLs but also **publishes stub artifacts** for consumers to test independently. However, a pipeline can fail even when all contracts are valid: CI cannot authenticate against the Maven repository, a proxy blocks dependency downloads, the repository certificate is untrusted by Java, or Stub Runner fetches the wrong artifact due to an incorrect version/classifier.

This lesson belongs to the **Contract and Artifact Repositories** chapter of the **SPRING_CLOUD_CONTRACT** module. The module focuses on contracts between producer and consumer over HTTP or messaging, generating producer tests, publishing stubs, running Stub Runner, and integrating with CI to catch incompatible API changes. Here, we learn how to **design repository permissions**, supply **credentials via CI secret managers**, route through **proxies**, verify **TLS**, and diagnose artifact retrieval errors without leaking sensitive data.

Running example throughout: **Order Service** (producer) builds and publishes `com.acme:order-service:1.0.0:stubs` to a private Maven repository; **Billing Service** (consumer) uses `Stub Runner` to download that version and test its HTTP client code. All domains, accounts, and versions in this lesson are **illustrative values** and must be replaced with authorized internal project details.

## 1. Identify Three Storage Locations and One Running Server Correctly

Before configuring authentication, identify **which service is being accessed**:

| Component | Example | What does it hold? | Who needs access? |
| --- | --- | --- | --- |
| **Contract source repository** | Internal Git repository | Groovy/YAML DSL, producer code, base tests. | Developers and CI with read access to source; contract editors need write rights via review workflow. |
| **Maven artifact repository** | `https://repo.example.org/repository/releases` | Application JARs, `stubs` classifier JARs, POMs, and metadata. | Producer CI needs publish permission; consumer CI needs read permission. |
| **Maven dependency/plugin repositories** | Maven Central or internal mirror | Spring Boot/Spring Cloud libraries and Maven plugins. | Both producer and consumer CI need resolve permission. |
| **Running HTTP stub server** | `http://localhost:12543` | Loaded WireMock mappings returning sample responses in tests. | Consumer test's HTTP client; not where artifacts are published. |

**A Maven repository URL is not the producer API's base URL.** When using `Stub Runner REMOTE`, the consumer may download the `stubs` JAR from `https://repo.example.org/...`, then start WireMock on `localhost` with a **dynamic port**. `OrderClient` must call **the assigned WireMock URL**, not the Maven repository address.

~~~mermaid
flowchart TD
    A["Git repo: contracts + producer code"] --> B["Producer CI"]
    B --> C["Contract Verifier generates/runs producer tests"]
    C --> D{"Tests pass?"}
    D -->|No| E["Block publish"]
    D -->|Yes| F["Package order-service-1.0.0-stubs.jar"]
    F -->|Write credential| G["Maven artifact repository"]
    G -->|Read-only credential| H["Billing consumer CI + Stub Runner"]
    H --> I["WireMock HTTP stub started"]
    I --> J["OrderClient sends HTTP to dynamic stub URL"]
    J --> K["Assert response + actual requests"]
~~~

If using **contracts outside the producer repository**, there is an extra fetch path for source contracts (Git, SCM, or Maven contract artifact depending on workflow). In that setup, access to **contract sources** and access to **published stub artifacts** can require two distinct sets of credentials. Never treat them as identical just because both are called “contract repository.”

## 2. Which Artifact Coordinates Are Published and Fetched?

Suppose Order Service has Maven coordinates:

~~~text
groupId    = com.acme
artifactId = order-service
version    = 1.0.0
classifier = stubs
extension  = jar
~~~

For Stub Runner, the common shorthand is:

~~~text
com.acme:order-service:1.0.0:stubs
~~~

A release may be stored by the repository as:

~~~text
com/acme/order-service/1.0.0/
    order-service-1.0.0.pom
    order-service-1.0.0.jar
    order-service-1.0.0-stubs.jar
~~~

**Filenames inside the repository depend on Maven layout and how the publisher attaches artifacts.** What matters is that group/artifact/version/**classifier** coordinates match. If the producer only publishes `order-service-1.0.0.jar` while the consumer requests `...:stubs`, an `artifact not found` error is expected even though the regular application artifact exists in the repository.

Before checking authentication/proxies, confirm:

1. The producer ran **generated producer tests** and passed.
2. The `stubs` classifier JAR was actually created and attached to the publication.
3. The artifact was **published to the right repository and exact version**.
4. The consumer requests **those exact coordinates**, without mixing up SNAPSHOT/release, classifier, or `groupId`.
5. The repository URL is a **Maven layout endpoint**, not an admin web UI, login page, or directory browser not meant for Maven resolvers.

**Never fix an “artifact does not exist” error by granting broader write permissions.** Separate **coordinate/path errors** from **authentication or authorization errors**.

## 3. Permission Model: Who Reads and Who Writes?

At minimum, there are two CI identities:

| Identity | Task | Minimum permissions to grant |
| --- | --- | --- |
| **Producer publish identity** | Push `stubs.jar`, POM/metadata to an allowed repo. | **Write/deploy** permission to Order Service's repository or namespace; read if tools check existence. |
| **Consumer read identity** | Stub Runner downloads artifacts by coordinates. | **Read** permission on the stubs/repositories used. |
| Local developer | Run tests or trial publishes in personal environments. | Read permission; write only where authorized and audited. |
| Release automation | Publish verified releases. | Publish rights gated by approval workflow and designated environment. |

**Never share a single repository admin account across all CI jobs.** A leaked read-only consumer token causes far less damage than a token able to write/overwrite the entire release repository. In repository managers like Nexus/Artifactory or equivalent artifact services, create dedicated roles/service principals with narrow scope instead of granting broad permissions to every project.

Useful policies:

- **Short-lived credentials** or workload identity/OIDC when supported by the repository and CI platform; if long-lived tokens are used, enforce an explicit rotation policy.
- **Separate snapshot and release environments**; production consumers should pin approved releases/versions.
- **Immutable release artifacts** when supported by repository policy, preventing silent test shifts from overwriting the same coordinates.
- **Never place tokens in POMs, `build.gradle`, contract DSLs, or Git history**.
- **Never expose publish secrets** to untrusted pull requests from forks or unapproved code.
- **Never put real tokens inside WireMock stub headers/bodies**: stub artifacts are distributed more broadly than typical test logs.

## 4. Maven: Repository Locations Live in the POM, Secrets Live in Settings

In a Maven producer, the publish endpoint is usually declared via `distributionManagement`:

~~~xml
<distributionManagement>
    <repository>
        <id>releases</id>
        <url>https://repo.example.org/repository/releases</url>
    </repository>
    <snapshotRepository>
        <id>snapshots</id>
        <url>https://repo.example.org/repository/snapshots</url>
    </snapshotRepository>
</distributionManagement>
~~~

This is the **deploy target configuration**, containing no passwords. `<id>releases</id>` and `<id>snapshots</id>` are **logical keys** for Maven to match credentials in `settings.xml`.

Example `settings.xml` generated by CI from a secure template, illustrating Maven settings interpolation from environment variables:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>releases</id>
            <username>${env.MAVEN_PUBLISH_USER}</username>
            <password>${env.MAVEN_PUBLISH_TOKEN}</password>
        </server>
        <server>
            <id>snapshots</id>
            <username>${env.MAVEN_PUBLISH_USER}</username>
            <password>${env.MAVEN_PUBLISH_TOKEN}</password>
        </server>
    </servers>
</settings>
~~~

**Attention:** accounts often use repository-issued passwords or tokens; some providers expect tokens in `username`, `password`, or custom headers. This example only applies when **the repository supports Basic authentication/tokens via username/password** and Maven/plugins support that setup.

Key points to remember:

1. `settings.xml` is **user/CI configuration**, not something that must be committed to the repository.
2. `${env.MAVEN_PUBLISH_TOKEN}` is resolved by Maven from the **Maven process environment**, when Maven settings interpolation applies.
3. The ID in `settings.xml` must match **the repository ID used by the deploy command**. A mismatched ID can cause requests to be sent **without credentials**.
4. If the project uses an internal mirror or alternate deployment repository, **the actual repository ID Maven sends requests to** may differ from the ID seen in a single POM snippet. Inspect effective settings, CI profiles, and Maven deploy configuration.
5. Never put raw passwords/tokens into `pom.xml` or pass `-Dpassword=...` on the command line where they can appear in process lists/logs.

### 4.1. Maven commands in CI

Once CI sets the environment and provides settings at a controlled path:

~~~shell
./mvnw -s "$MAVEN_SETTINGS_FILE" clean verify
./mvnw -s "$MAVEN_SETTINGS_FILE" deploy
~~~

These are **two illustrative invocations**; `deploy` also executes earlier phases and may re-run tests. A pipeline can separate the build/verify job from the publish job to avoid rebuilding, provided the published artifact is **the exact bytes produced by the verified job**.

**`mvn deploy` does not prove producer verification ran** if the pipeline passes `-DskipTests`, generated tests were not discovered, or publish runs as an isolated goal. Check reports and CI conditions rather than merely reading exit code 0.

## 5. Maven: Which Repositories Does the Consumer Fetch Dependencies From?

Unlike `distributionManagement` (used for publishing), a consumer can configure **repositories for downloading dependencies/artifacts**:

~~~xml
<repositories>
    <repository>
        <id>contract-releases</id>
        <url>https://repo.example.org/repository/releases</url>
        <releases>
            <enabled>true</enabled>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </repository>
</repositories>
~~~

Consumer CI only needs **read** credentials for that repository:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>contract-releases</id>
            <username>${env.MAVEN_READ_USER}</username>
            <password>${env.MAVEN_READ_TOKEN}</password>
        </server>
    </servers>
</settings>
~~~

**Distinction:** ID `contract-releases` for the **read repository** and ID `releases` for the **write repository** can differ even when both URLs point to the same server. When using Maven settings for authentication, the ID must match **the repository the resolver actually selects**, never automatically the JAR filename.

In enterprise environments, an authorized **mirror/repository group** may let Maven pull dependencies from multiple sources. Still, **never assume Stub Runner automatically uses the exact same resolver, effective settings, and mirror rules as the `mvn` CLI**; verify the behavior of the Stub Runner version running inside the consumer process.

### 5.1. A mirror is not an upload repository

Maven `mirrors` in `settings.xml` redirect **artifact/plugin resolution** to a proxy repository or mirror:

~~~xml
<mirrors>
    <mirror>
        <id>company-mirror</id>
        <mirrorOf>external:*</mirrorOf>
        <url>https://repo.example.org/repository/maven-group</url>
    </mirror>
</mirrors>
~~~

For example, `external:*` routes downloads from matching external repositories to an internal mirror under Maven's rules; check company policy and repository IDs. Mirrors help cache Maven Central and keep CI from needing open internet access.

**Do not treat a mirror configuration as a deploy target.** Publishing to a specific repository still requires `distributionManagement`/deploy configuration and write access on that destination. A read-only repository group can download dependencies fine yet **reject uploads**.

## 6. Stub Runner REMOTE: Downloading the JAR and Finding the Server Address Are Two Steps

Billing Service configures Stub Runner for a specific artifact:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.org/repository/releases"
)
class BillingContractTest {
    // Inject StubFinder, call real OrderClient, and assert responses.
}
~~~

`repositoryRoot` in this example is **the Maven repository URL for downloading the `stubs` JAR**. It is **not the base URL** for `GET /api/orders/42`. After loading the artifact, Stub Runner starts WireMock locally on an available port.

A test can look up the running HTTP stub address:

~~~java
import java.net.URL;
import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cloud.contract.stubrunner.StubFinder;

@Autowired StubFinder stubFinder;

@Test
void resolvesOrderStub() {
    URL url = Objects.requireNonNull(
        stubFinder.findStubUrl("com.acme", "order-service"),
        "Order Service stub not started"
    );

    OrderClient client = new OrderClient(url.toExternalForm());
    OrderClient.OrderDto order = client.getOrder(42L);

    assertThat(order.id()).isEqualTo(42L);
    assertThat(order.status()).isEqualTo("PAID");
}
~~~

This is an **illustrative test snippet**, assuming Billing already has `OrderClient`, its DTO, and AssertJ; it is not a complete Java class. The goal is to distinguish:

- **Repository URL:** `https://repo.example.org/repository/releases`, using **read credentials**.
- **Stub HTTP URL:** e.g., `http://localhost:12543`, used to call the **simulated API** in consumer tests.

### 6.1. Supplying credentials to Stub Runner

Spring Cloud Contract Stub Runner can use its built-in resolver/transport to download artifacts. **Never assume every version reads `settings.xml` and credentials identically to the Maven CLI.** Depending on the release train and initialization mode, it may support Stub Runner properties, Aether/Maven settings, or a custom repository resolver.

Proper process:

1. Confirm **which authentication scheme** the repository actually requires: Basic/token, cloud identity, bearer token, mTLS, or another mechanism.
2. Check documentation/APIs for **the exact Spring Cloud Contract Stub Runner version** used by the consumer on how to configure authentication.
3. Pass secrets from the **CI secret manager** into the supported mechanism; never hardcode them in annotations or committed `application-test.yml`.
4. Run consumer tests in a CI environment **without the artifact pre-cached in Maven local** to prove real remote downloads work.
5. Inspect resolver logs at a diagnostic level without **printing usernames/passwords/tokens**.

If the repository uses Basic auth and your Stub Runner version supports username/password properties, wire them to **environment/secret injection** per project conventions. If the repository requires OIDC/mTLS/custom headers, **do not try to cram that token into a Basic password** if the transport does not support it; use a resolver/proxy capable of proper authentication.

**Never embed tokens inside URLs** like `https://user:token@repo.example.org/...`. URLs can be logged in exceptions, CI artifacts, test reports, shell history, and proxy logs. Prefer separate, masked credentials.

### 6.2. LOCAL is not a workaround for REMOTE authentication

~~~java
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
~~~

`LOCAL` uses artifacts already in the running environment's **Maven local repository**. It is suitable when the producer ran `mvn install` into the same local repo or a CI step prepared the artifact properly.

`LOCAL` **does not prove** the consumer can download releases from the remote repository. A CI test that happens to have the artifact cached can PASS even though **repository read credentials have expired**. Dedicated checks for remote downloads should therefore run from a clean cache or isolated runner.

## 7. CI Secrets: Provisioning, Passing, and Revoking

A secure pipeline never stores secrets in Git, POMs, or Markdown. Instead, the CI platform stores secrets and supplies them at runtime only to **authorized jobs**.

| Illustrative environment variable | Using job | Permission |
| --- | --- | --- |
| `MAVEN_PUBLISH_USER` | Producer publish job | Service identity permitted to upload. |
| `MAVEN_PUBLISH_TOKEN` | Producer publish job | **Write/deploy** to producer namespace. |
| `MAVEN_READ_USER` | Consumer contract test job | Read-only service identity. |
| `MAVEN_READ_TOKEN` | Consumer contract test job | **Read** required artifacts. |
| `MAVEN_SETTINGS_FILE` | Job running Maven | Path to runner-generated or provisioned settings. |
| `ARTIFACT_REPO_URL` | Build/test job | Approved repository URL without credentials. |

These variables are **illustrative names only**, not mandatory variables required by Spring Cloud Contract.

A solid pipeline enforces:

- Publish secrets appear only in the **publish job** after producer verification passes, not in every unit-test job.
- Read secrets appear only in **consumer CI** needing to download artifacts.
- Pull requests from untrusted sources **never receive publish secrets**; workflow execution on external branches must be gated.
- Mask secret values in logs; avoid excessive trace/debug logging or dumping the full process environment.
- Never archive credential-bearing `settings.xml` into CI artifacts/caches, and never print `help:effective-settings` verbatim unless sensitive fields are verified masked.
- Bind permissions to **machine accounts/service principals** with auditing and rotation; revoke immediately if a token leaks.
- Separate read access for public dependency mirrors from read/write access for private release repositories if policy demands.

### 7.1. Example CI workflow generating settings

CI can generate a temporary settings file inside a protected workspace, referencing credentials from environment variables:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>releases</id>
            <username>${env.MAVEN_PUBLISH_USER}</username>
            <password>${env.MAVEN_PUBLISH_TOKEN}</password>
        </server>
    </servers>
</settings>
~~~

Then pass this file to Maven when running the publish job. **Never reuse a file holding write rights inside a read-only consumer job.** If the runner renders secrets literally into a file instead of environment expressions, restrict permissions to owner-read-only, avoid printing the file, and delete it on job completion.

**Masked secrets can still leak.** Tokens can slip into URLs, HTTP proxy logs, heap dumps, crash reports, or build-tool output. Choose secret-passing methods less likely to appear on command lines and verify plugin logging per environment.

## 8. HTTP Proxies: CI Network Paths Can Differ from Laptops

In enterprises, CI runners often traverse a proxy to reach Maven Central, Gradle Plugin Portal, or internal repos. Sometimes internal repos must go **direct**, bypassing the proxy. Therefore you must know:

1. Proxy host/port and accepted protocol.
2. Host list configured to **bypass the proxy**.
3. Whether the proxy requires a **username/password**.
4. Whether HTTPS traffic uses a **CONNECT tunnel** or undergoes TLS inspection.
5. Whether the runner container/VM has DNS and routing to the **repository host**.

**Do not confuse a proxy with a repository.** A proxy forwards network traffic; a Maven repository stores artifacts. A request to `repo.example.org` may travel through a proxy, yet Maven/artifact coordinates stay the same.

### 8.1. Declaring proxies in Maven settings

Example `settings.xml`:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <proxies>
        <proxy>
            <id>corporate-proxy</id>
            <active>true</active>
            <protocol>http</protocol>
            <host>proxy.example.internal</host>
            <port>3128</port>
            <nonProxyHosts>
                localhost|127.0.0.1|*.corp.internal|repo.example.org
            </nonProxyHosts>
        </proxy>
    </proxies>
</settings>
~~~

Hostnames above are **samples**. `nonProxyHosts` uses `|` as a separator in common Maven/Java syntax; it **differs** from comma-separated `NO_PROXY` used by many HTTP clients. If an internal repository must be reached directly, put it in the bypass list; if the repository is only reachable via proxy, do not bypass it blindly.

Authenticated proxies can use `<username>`/`<password>` inside `<proxy>`, populated from CI secrets via settings interpolation or a protected runtime file. **Never place real proxy passwords** in committed files.

**`<protocol>http</protocol>` describes the proxy**, not that the repository URL must be HTTP; an HTTPS repository typically uses an HTTP proxy via CONNECT when infrastructure permits. Never assume every HTTPS/mTLS repository works with every proxy: check SSL rules and corporate configuration.

### 8.2. Be careful with HTTP_PROXY, HTTPS_PROXY, and NO_PROXY

Some tools read variables:

~~~text
HTTP_PROXY=http://proxy.example.internal:3128
HTTPS_PROXY=http://proxy.example.internal:3128
NO_PROXY=localhost,127.0.0.1,.corp.internal
~~~

However, **Java/Maven, Gradle, curl, Git, and Stub Runner can read different variables/settings**. `curl` downloading a JAR **does not prove** Maven or Stub Runner used the same proxy. When debugging, inspect the **actual process making the request** and the proxy mechanisms it supports.

In containerized CI, verify environment variables were **passed into the container running Maven/tests**, not merely present on the host runner.

## 9. Gradle: Dependency Repositories, Publication, and Credentials

For producers/consumers using **Gradle**, the principle remains **separating read and write credentials**, though syntax differs from Maven. Groovy DSL example:

~~~groovy
repositories {
    mavenCentral()
    maven {
        name = 'contractReleases'
        url = uri('https://repo.example.org/repository/releases')
        credentials {
            username = providers.environmentVariable(
                'MAVEN_READ_USER'
            ).orNull
            password = providers.environmentVariable(
                'MAVEN_READ_TOKEN'
            ).orNull
        }
    }
}
~~~

This is **configuration to resolve dependencies** in a Gradle build. With compatible Gradle versions, `providers.environmentVariable(...)` reads CI-injected environment variables; no tokens need to be written in source. In projects with an internal repository group/mirror, replace `mavenCentral()` with the approved repository.

A Gradle producer needs a dedicated publication to publish the `stubs` classifier JAR (created by the Contract Gradle Plugin) and a publish repository with **write** credentials:

~~~groovy
publishing {
    repositories {
        maven {
            name = 'companyReleases'
            url = uri(
                'https://repo.example.org/repository/releases'
            )
            credentials {
                username = providers.environmentVariable(
                    'MAVEN_PUBLISH_USER'
                ).orNull
                password = providers.environmentVariable(
                    'MAVEN_PUBLISH_TOKEN'
                ).orNull
            }
        }
    }
}
~~~

**The `publishing.repositories` block only declares the publish target**; it does not attach the `stubs` JAR automatically. You need `maven-publish`, a Maven publication containing the `stubs` classifier artifact, and the stub packaging task for your plugin version. When publishing, check both **coordinates and contents** of the JAR, not just an upload success status code.

### 9.1. Proxies for Gradle use JVM/network settings

Gradle runs on the JVM, so in many cases it uses system properties such as:

~~~properties
systemProp.http.proxyHost=proxy.example.internal
systemProp.http.proxyPort=3128
systemProp.https.proxyHost=proxy.example.internal
systemProp.https.proxyPort=3128
systemProp.http.nonProxyHosts=localhost|127.0.0.1|*.corp.internal
~~~

This is an **example configuration** without passwords and may not apply to every HTTP client/plugin invoked by Gradle. Never put real proxy credentials into `gradle.properties` in source control. Identify which `gradle.properties` file the runner reads, check Gradle daemon settings, and exclude internal repos from proxying per policy.

**Another note:** Maven `settings.xml` does not automatically govern all Gradle dependency resolution; if the producer uses Gradle while the consumer uses Maven, **each build tool needs its own repository and credentials configuration**.

## 10. HTTPS/TLS: Handling Certificate Errors Properly

Private repositories require **valid HTTPS**. Common errors:

~~~text
PKIX path building failed
unable to find valid certification path
SSLHandshakeException
hostname verification failed
~~~

Common causes:

| Cause | Symptom | Proper resolution |
| --- | --- | --- |
| Repository uses an internal CA | JVM does not trust certificate chain. | Install **organization-approved CA** into the truststore of the JDK/JVM running the build. |
| TLS inspection proxy re-signs certificates | Browser/curl works yet JVM rejects proxy CA. | Verify with security team and trust the proper corporate CA. |
| Hostname does not match certificate | `hostname verification failed`. | Fix DNS/repository URL or certificate SAN; never disable verification. |
| Expired certificate | Handshake fails after expiry date. | Renew certificate on repository/proxy; check runner system clock. |
| Old JDK missing trust roots/algorithms | Passes on laptop, fails on old runner. | Upgrade JDK/truststore per policy; pin CI toolchain. |
| Unexpected proxy/SSL MITM | Chain differs from approved environment. | Investigate network with security team; never blindly accept unknown certificates. |

**Never work around this by disabling SSL verification** or passing `insecure/allowall` flags in Maven/Gradle to get CI green. Doing so lets attackers substitute stub/dependency JARs or intercept credentials.

### 10.1. Which JVM process's truststore is used?

In a pipeline involving Maven, Gradle, Java test processes, and Stub Runner, there can be **multiple JVMs**:

- Maven launcher uses JDK A.
- Gradle daemon uses JDK B.
- Forked test/Surefire runs JDK C.
- A standalone Stub Runner app runs JDK D.

Updating only a laptop truststore or a JDK unused by the runner leaves SSL errors intact. Inspect **`java -version`, `mvn -version`, Gradle Java home/toolchain, and test processes**, then install the approved CA into the exact environment needed.

### 10.2. For mTLS or repositories not using Basic auth

Some repositories require **client certificates**, IAM/OIDC, or a short-lived token gateway. In those cases, username/password settings in Maven settings may **not suffice**. You must:

1. Confirm which auth method the repository/gateway supports.
2. Configure client certificates/truststores/identities via supported Maven, Gradle, Stub Runner, or proxy resolver mechanisms.
3. Ensure secret keys/certificates exist only in authorized jobs, never stored in artifacts or source control.
4. Handle expiration/rotation and failed authentication safely.

Do not claim “the repo just needs `<server><password>`” when the actual system uses another mechanism.

## 11. Distinguishing 401, 403, 404, 407, 429, and SSL Errors

When consumer CI fails to download stubs, HTTP status codes narrow the search, yet **no single status proves every root cause**. Some repositories intentionally return 404 instead of 403 to avoid leaking private artifact existence.

| Error | Common meaning | What to check first? |
| --- | --- | --- |
| **401 Unauthorized** | Missing/invalid credentials, expired token. | Are credentials present? Right repo/server ID? Token still valid? |
| **403 Forbidden** | Authenticated yet insufficient permissions or blocked by policy. | Role, namespace, repository, branch/env policy, IP allowlist. |
| **404 Not Found** | Artifact/URL missing, wrong classifier/version, or repo hides resource. | Maven coordinates, repository layout, metadata, read permission. |
| **407 Proxy Authentication Required** | Proxy demands separate authentication. | Proxy username/password and whether client really routes via proxy. |
| **429 Too Many Requests** | Repository/gateway rate limit. | Quota, backoff retries, and policy-compliant concurrency/caching. |
| **5xx** | Repository/proxy/gateway instability. | Infrastructure health, timeouts, retry counts, service incident. |
| **PKIX/SSLHandshakeException** | Invalid certificate chain, hostname, TLS, or truststore. | JDK/truststore, valid cert, TLS inspection proxy. |
| **Connection refused / timeout** | Wrong host/port, DNS, routing, firewall, or proxy. | Exact URL, DNS, CI network namespace, TCP reachability. |

**Never assume** 401 means “artifact doesn't exist” or 404 means “missing password.” To debug effectively, record the **credential-free URL host**, status code, Maven coordinates, repository ID, and failing pipeline step.

### 11.1. Ordered diagnostic workflow

1. Cross-check **group/artifact/version/classifier/extension** against producer publication.
2. Confirm **repository URL** points to a Maven endpoint, not a UI login or admin page.
3. Check that the CI job **holds the right identity** and the secret has not expired; never print the secret.
4. Confirm **server ID/repository ID** matches in Maven, or credential configs are actually read by Gradle/Stub Runner.
5. Check **proxy and non-proxy hosts** for the process making the request.
6. Check the **TLS chain/truststore** of the exact JDK/process.
7. Inspect repository/gateway logs under controlled access if your team owns the repo; match request IDs and policies.
8. From a clean runner, test fetching **the exact stub version** with CI tooling, then execute the Stub Runner consumer test.

**Never debug by putting real tokens into exception messages or cranking logging to unlimited verbosity.** If logs must be shared for investigation, redact all Authorization headers, cookies, query credentials, and repository user info.

## 12. Separating Artifact Download Errors from HTTP Stub Matching Errors

Once authentication is solved, tests can still fail at another layer:

| Situation | Symptom | Investigation path |
| --- | --- | --- |
| **Cannot download JAR** | Stub Runner fails to resolve artifact; HTTP 401/403/404 from repo. | Repository/credentials/proxy/TLS/Maven coordinates. |
| **JAR downloads yet lacks HTTP mappings** | WireMock starts yet serves no endpoints. | Inspect `stubs.jar` contents, Contract Verifier output, exact artifact version. |
| **WireMock fails to start** | No URL in `StubFinder`, port bind/config error. | Stub Runner startup, classpath, port, mapping parser. |
| **WireMock runs yet request doesn't match** | Consumer gets 404 no-match. | Compare method/path/query/headers/body against mappings and journal. |
| **WireMock returns business 404** | A 404 error mapping matched, with error body/code. | Assert error payload and consumer handling. |
| **Client code uses wrong base URL** | Connects to Maven repo or another server. | Query `StubFinder.findStubUrl(...)` and pass that URL to the real client. |
| **Consumer fails to parse response** | Jackson/schema error. | Inspect contract body, DTO, Content-Type header, and version. |

In particular, **WireMock's HTTP 404** is unrelated to **HTTP 404 when downloading a JAR from a Maven repository**. The two requests go to **two different hosts/ports and two different services**. Use the right logs and tools for each layer.

## 13. Internal Repositories, Snapshots, Releases, and Metadata

Many organizations separate repositories:

~~~text
https://repo.example.org/repository/snapshots
https://repo.example.org/repository/releases
https://repo.example.org/repository/maven-group
~~~

| Repository type | Purpose | Notes |
| --- | --- | --- |
| **Snapshots** | Unstable development artifacts. | A snapshot version can change; requires clear update/metadata/cache policies. |
| **Releases** | Approved releases. | Prefer immutability, pin versions, and restrict overwrites. |
| **Group/proxy** | Resolves across multiple upstream repos. | Often read-only; never use as a publish target. |
| **Staging** | Awaits QA/approval before promotion to release. | Consumers should not treat unapproved staging artifacts as releases. |

For example, the consumer tests `1.0.0` while the producer publishes `1.0.1`. CI should not automatically accept the new version via a dynamic version like `+`/`LATEST`. **Select explicit versions via a compatibility matrix** with reviewed upgrades.

With `-SNAPSHOT`, Maven metadata points to timestamped artifacts. If a repository/mirror/cache holds stale metadata, the consumer may fetch an unexpected snapshot. When analyzing, compare **version, checksum, timestamp, and metadata** in the repo and local cache, not just the `...-SNAPSHOT` name.

### 13.1. Caching speeds things up yet can mask authentication errors

CI caches typically store downloaded libraries and stubs:

- Caching avoids re-downloading dependencies, cutting runtime and network reliance.
- Caching can **hide repository errors** if the artifact is already present.
- Caches must never contain `settings.xml` with credentials, private keys, or tokens.
- Cache keys must match OS/JDK/build tool/policy to avoid stale or untrusted artifacts.
- Include a dedicated **cold-cache remote download** check in the pipeline to guard auth/repository access.
- On `Could not find artifact` after an earlier failed fetch, Maven may cache negative resolution per update policy; check `-U`/metadata refresh properly instead of wiping caches blindly when coordinates are actually wrong.

**Never treat a cache hit as proof** that CI's identity still has permission to read the remote repository. To verify auth, force the repository to serve a download in an isolated environment.

## 14. Preventing Data Leaks via Artifacts and Logs

Contracts and stubs may be shared with more consumers than producer source code. Never assume artifacts only hold “test data” and need no review:

| Risk | Bad example | Prevention |
| --- | --- | --- |
| Token in WireMock mapping | Authorization header contains a real bearer token. | Use inert/placeholder tokens and scan contracts for secrets. |
| Private data in sample response | Real emails, account numbers, or personal data. | Use synthetic fixtures and govern artifact read access. |
| Credential in repository URL | `https://user:token@repo...` | Configure credentials separately; never embed in URLs. |
| Secret exposed in build logs | `echo $TOKEN`, command tracing, debug exceptions. | Never print env/secrets; enable masking, redaction, and limit debug output. |
| Artifact uploaded to wrong namespace | Producer holds write access across entire repo. | Least privilege by repository/namespace/service. |
| Overwriting an older release | Publishing same group/artifact/version with altered content. | Immutable releases, reviews, and metadata/checksum checks. |
| Tampered artifact | Downloading from unauthenticated HTTP or untrusted mirrors. | HTTPS/TLS, repository allowlists, checksums/signatures/policy. |

In CI, verify artifacts are published from **commits and pipelines that passed producer verification**. Depending on the organization, add SBOMs, checksums/signatures, provenance, or dependency policies; these strengthen origin protection but **do not replace verifying contract accuracy**.

## 15. Producer CI: From Verification to Authorized Publication

A trustworthy producer pipeline:

~~~mermaid
flowchart TD
    A["Producer PR/commit"] --> B["Read-only CI: resolve dependencies"]
    B --> C["Contract Verifier generates producer tests"]
    C --> D["Run tests + inspect reports"]
    D --> E{"Verification passes?"}
    E -->|No| F["Fail; no publish credentials granted"]
    E -->|Yes| G["Package stubs classifier"]
    G --> H["Verify JAR, version, metadata, and secret scan"]
    H --> I["Publish job receives write credentials"]
    I --> J["Upload to releases/snapshots as appropriate"]
    J --> K["Verify artifact resolves and audit"]
~~~

Recommended steps:

1. **Resolve plugins/dependencies** via approved repositories/mirrors; CI holds minimal read rights.
2. **Run generated producer tests** from Groovy/YAML contracts; confirm test count > 0 and none skipped.
3. **Run necessary integration/security tests**, especially when contracts rely on DBs, auth, or messaging.
4. **Package the stubs JAR** after verification; check `stubs` classifier and mappings/contracts contents.
5. **Block publish if verification fails**; never provision write secrets to unapproved jobs.
6. **Publish versioned artifacts** to the right snapshot or release repository using a scoped write account.
7. **Check artifact metadata/provenance** and verify consumers have needed read access.

There is no reason to pass publish credentials into consumer test steps. Conversely, consumers should never be able to alter the stubs they test against.

### 15.1. Controlled CI pipeline pseudocode

~~~yaml
# Pseudocode: adapt to real GitHub Actions/GitLab CI/Jenkins syntax.
jobs:
  verify-producer:
    permissions: read-only
    steps:
      - checkout-source
      - configure-java-and-maven-settings-readonly
      - run: ./mvnw clean verify
      - inspect: generated-tests-and-surefire-reports
      - archive: verified-stubs-artifact

  publish-stubs:
    needs: verify-producer
    if: verification-and-release-policy-pass
    secrets:
      - MAVEN_PUBLISH_USER
      - MAVEN_PUBLISH_TOKEN
    steps:
      - download: verified-stubs-artifact
      - check: version-checksum-and-publish-target
      - publish: exact-verified-artifact
~~~

**This is pseudocode, not valid YAML for a specific CI platform.** It illustrates the core pattern: **read-only permissions in the verify job**, injecting **write secrets** only in the publish job after passing the gate. If the publish job rebuilds with Maven, verify the rebuild cannot alter unverified artifacts; a cleaner approach is publishing **the exact artifact produced in the verify job** via an approved repository mechanism.

## 16. Consumer CI: Cold-Cache Download and Stub Runner Execution

The consumer can configure Stub Runner:

~~~java
@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.org/repository/releases"
)
class BillingConsumerContractTest {
    @Autowired
    private StubFinder stubFinder;

    @Test
    void readsOrderFromPublishedStub() {
        URL url = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service")
        );
        OrderClient client = new OrderClient(url.toExternalForm());
        assertThat(client.getOrder(42L).status()).isEqualTo("PAID");
    }
}
~~~

This is an **illustrative test snippet**, assuming imports, `OrderClient`, and dependencies exist. For private repos, add **read credentials** via the mechanism supported by your project's Stub Runner version. Before running, CI needs network reachability to the repo, working proxy/TLS, and a published artifact.

A consumer test flow should:

1. Receive **read credentials** from the CI secret store, with no write credentials.
2. Verify the repository URL and proxy/TLS connect from the exact runner/container.
3. Download the **specific stubs artifact** using Stub Runner `REMOTE`.
4. Start WireMock from mappings inside the artifact or messaging adapters per contract.
5. Look up the dynamic HTTP base URL with `StubFinder` when using HTTP.
6. Call **real client code** and assert responses/statuses/headers/bodies rather than merely confirming stub download succeeded.
7. When needed, inspect the **request journal** to catch wrong client paths/headers or duplicate calls.
8. Record the **artifact version** in test reports for reproducibility, never recording credentials.

If CI runs multiple consumer jobs in parallel, use dynamic ports and isolated Stub Runner contexts to avoid colliding on `8089`. An `Address already in use` error **is not a Maven credentials error**.

## 17. Manual Verification from a CI Runner Without Leaking Secrets

When artifact downloads fail, a logical check sequence:

~~~text
1. Identify repository host and Maven coordinates.
2. Verify DNS/routing from the actual container or runner.
3. Verify proxy settings used by the Maven/Stub Runner process.
4. Verify TLS certificate chain against the right truststore/JDK.
5. Verify read identity permissions on the repository/namespace.
6. Attempt artifact resolution in a clean environment.
7. Confirm returned JAR has the right stubs classifier and version.
8. Run consumer contract tests—do not stop at download success.
~~~

Maven can test resolution of a specific artifact on a runner already configured with safe credentials in `settings.xml`:

~~~shell
./mvnw -s "$MAVEN_SETTINGS_FILE" \
  org.apache.maven.plugins:maven-dependency-plugin:get \
  -Dartifact=com.acme:order-service:1.0.0:jar:stubs \
  -DremoteRepositories=contract-releases::default::https://repo.example.org/repository/releases
~~~

This command uses a **Maven Dependency Plugin** goal to diagnose Maven artifact resolution; **it does not guarantee Stub Runner uses that exact resolver configuration**. When adopting in CI, check plugin syntax/version, permissions, and repository policy, avoiding credential printing or arbitrary runs against production environments.

If `mvn dependency:get` succeeds while Stub Runner still fails to download, inspect **differences in resolver, settings, proxy, credentials, or classpath** inside the test process. Conversely, if Maven CLI cannot resolve due to 401/403, fix authentication before investigating WireMock mappings.

**Syntax note:** Maven Dependency Plugin coordinates can be written `groupId:artifactId:version:type:classifier`; Stub Runner uses `groupId:artifactId:version:classifier[:port]` in many configs. **The two strings are not always directly interchangeable.**

## 18. Special Cases: Git Contract Sources, Private Proxies, and Cloud CI

### 18.1. Contracts in a separate Git repository

A team may keep **consumer-driven contracts** in a separate SCM repository. Producer CI fetches contract sources at a specific version/tag/commit, while consumer Stub Runner still fetches **stub artifacts** from a Maven repository.

Rules:

- **Git tokens** only need SCM read rights in contract-consuming pipelines; contract edits go through PRs/reviews.
- **Maven read/write tokens** serve the separate artifact repository; never put a Git token into a Maven repository URL.
- Pin the **Git commit/tag** or contract source version so builds are reproducible.
- Verify contract sources and stub artifacts match the **same logical version**; never pull contracts from an unapproved branch and publish stubs as stable releases.

If you do not know whether the project uses Git or artifact-based external contracts, never configure “one repository URL” across every component.

### 18.2. Containers and internal proxies

CI runners may live in Kubernetes with `service DNS`; the Maven process and Stub Runner test process may run in two separate containers:

| Issue | Symptom | Prevention |
| --- | --- | --- |
| Internal DNS fails to resolve | `UnknownHostException`. | Test DNS from the actual container, not only the host. |
| Misunderstood `localhost` | HTTP client calls consumer's own container instead of stub. | Use `StubFinder` URL or proper service DNS/port mapping. |
| Wrong proxy for internal repo | Request blocked by proxy, 407, or timeout. | Configure bypass for right hosts; distinguish JVM `nonProxyHosts` from `NO_PROXY`. |
| TLS CA only on host | Java inside container throws PKIX. | Provision approved CA into container JDK/truststore. |
| Secret scoped to another job | Consumer gets 401 even though producer published fine. | Separate secret scopes properly and pass to needed steps/processes. |
| Fixed WireMock port | Parallel tests collide on port. | Dynamic Stub Runner ports, per-process isolation. |

### 18.3. Repositories allowing anonymous reads yet authenticated publishes

Some internal repositories allow **unauthenticated consumer reads** inside a trusted network while uploads require auth. That is **repository policy**, not Spring Cloud Contract behavior. When choosing that model, still restrict network access, TLS, auditing, and artifact exposure risks.

Do not invent dummy credentials to “fix” a repo that does not expect Basic auth; that can trigger 401s or leak unnecessary metadata. Always check the actual access policy.

## 19. Quick Investigation Matrix for Developers and CI

| Symptom | Most likely fault area | Action to take |
| --- | --- | --- |
| Producer `mvn deploy` gets 401 | Publish credentials or server ID. | Check `distributionManagement.id`, `settings.xml`, token expiry, and auth method. |
| Producer upload gets 403 | Missing write/deploy rights or namespace/release policy. | Check role/repository policy; never escalate system-wide privileges. |
| Consumer Stub Runner REMOTE gets 401 | Read credentials not used by resolver. | Check how your Stub Runner version loads credentials; test cold cache. |
| Consumer REMOTE gets 404 | Wrong coordinates/classifier/version, URL, or hidden permissions. | Compare Maven layout/metadata; verify read ACLs. |
| Maven/Gradle reports 407 | Proxy auth failure. | Check proxy username/password and client proxy config. |
| Maven CLI downloads yet Stub Runner fails | Different resolver, settings, cache, proxy, or process TLS. | Compare actual test JVM config against Maven CLI. |
| `PKIX path building failed` | JVM does not trust corporate CA/chain. | Inspect JDK/truststore and TLS proxy; never disable SSL checks. |
| `Connection timed out` | Routing/DNS/proxy/firewall or overloaded repo. | Test from CI network namespace and check server health. |
| Fails only in CI, passes on laptop | Secret scopes, proxy, CA, cache, JDK/Gradle/Maven versions differ. | Compare environments selectively without printing secrets. |
| Stub JAR downloads yet consumer gets 404 | WireMock mapping mismatch or business error. | Inspect request journal/mappings instead of continuing Maven auth debugging. |
| Consumer tests pass yet producer broke API | Producer verifier skipped or stale stub artifact. | Inspect producer test report and artifact version/commit. |
| Passes with warm cache, fails on cold cache | Remote repo/mirror permissions or stale metadata. | Run a cold-cache test with controlled credentials. |
| Publish succeeds yet others cannot download | Different repo/group permissions, unpromoted staging, wrong classifier. | Inspect publication and consumer read path. |
| New content invisible despite same version | Immutable release or snapshot metadata/cache. | Publish a new version; never overwrite releases to “force” changes. |

Classify before fixing: **source retrieval**, **dependency resolution**, **stub artifact publishing**, **artifact download**, **HTTP stub runtime**, or **contract mismatch**. Each category has its own logs, permissions, and fixes.

## 20. Practice Lab: Producer Publishes, Consumer Fetches via Private Repository

Set up a sandbox environment with a **private Maven repository** for learning—never use production admin accounts:

1. **Define an HTTP contract** for Order Service: `GET /api/orders/42` returns 200 JSON `{"id":42,"status":"PAID"}` using Groovy or YAML DSL.
2. **Configure Contract Verifier** on the producer; generate tests, verify they actually execute, and confirm an intentional breaking change fails.
3. **Build/publish the `stubs` classifier JAR** using coordinates `com.acme:order-service:1.0.0:stubs`. Inspect artifact contents after building.
4. **Create two service identities** in the test repo: one with publish rights in the producer namespace, one with read-only rights.
5. **In the Maven producer**, configure `distributionManagement` pointing to the release repository; supply publish credentials via `settings.xml` generated from CI secrets without committing tokens.
6. **Run producer verification first** before letting the publish job receive write credentials. Confirm the artifact appears at the right Maven path.
7. **In Billing consumer**, configure `@AutoConfigureStubRunner` with `REMOTE`, `repositoryRoot`, and the published version; supply read credentials via the mechanism supported by your Stub Runner version.
8. **Run from a clean CI runner/cache**: confirm Stub Runner downloads the artifact, starts WireMock, `StubFinder` returns the URL, and `OrderClient` reads `PAID`.
9. **Test controlled credential failure**: use an expired read token or omit credentials in sandbox; observe 401/403 and identify root cause without printing tokens.
10. **Test coordinate failure**: change classifier/version to a non-existent one; explain why 404 is not necessarily an authentication failure.
11. **Test proxy**: configure a test proxy and bypass list for the internal repository; confirm both Maven and test JVM take the expected network path.
12. **Test truststore** in an environment with an approved internal CA; confirm the CI JDK trusts the valid certificate. Never disable TLS verification.
13. **Test caching**: compare a warm-cache run with a cold-cache run to verify the pipeline does not rely on leftover artifacts.
14. **Assemble a CI gate**: producer verification PASS → publish versioned stubs → consumer REMOTE test → record artifact version and compatibility result.

**Completion criteria:** both producer and consumer run across two independent jobs/runners, **write/read permissions are separated**, no credentials appear in source/logs, Stub Runner **downloads real artifacts from the private repo**, and you can distinguish repository/proxy/TLS errors from WireMock request matching errors.

## 21. Self-Check Questions

1. How do a Git repo holding contract sources, a Maven repo holding `stubs` JARs, and a WireMock HTTP server differ?
2. Why is Stub Runner's `repositoryRoot` not the base URL for `OrderClient`?
3. What does `groupId:artifactId:version:stubs` represent, and why can omitting the classifier cause an artifact 404?
4. What permission type does producer CI need to publish, and what does consumer CI need to download?
5. Why should you avoid using one shared admin token across all CI jobs?
6. How does `distributionManagement` differ from `repositories` and `mirrors`?
7. Why must `<id>` in Maven server credentials match the repository ID Maven actually uses?
8. How does `StubsMode.LOCAL` differ from `REMOTE` in artifact source? Do both run WireMock HTTP locally?
9. Why might Maven CLI download an artifact cleanly while the Stub Runner test JVM fails?
10. In Maven proxy config, how does `nonProxyHosts` differ syntactically from `NO_PROXY`?
11. On encountering 407, should you check repository credentials or proxy credentials first?
12. On `PKIX path building failed`, why is disabling TLS verification a dangerous fix?
13. Why can a CI runner with a warm cache mask expired read credentials?
14. When a repository returns 404, can you conclude with certainty the artifact does not exist?
15. Why do immutable release artifacts make consumer contract tests reproducible?
16. When a consumer gets WireMock 404 from `GET /api/orders/43`, why is that not automatically a Maven repository 404?
17. In CI, when should publish secrets be granted and when should they be revoked?
18. Why must contracts and sample data inside a stubs JAR also be scanned for information leaks?

## 22. Production Readiness Checklist

| Check | Expectation |
| --- | --- |
| Separate producer/consumer permissions | Publisher has **minimal write**, consumer has **minimal read**. |
| Repository URLs and identities | Valid host, valid Maven layout, matching server IDs, sound release/snapshot policy. |
| Secret delivery | Only via secret manager/workload identity or equivalent secure channel; never committed. |
| Proxy/DNS/network | Configured on the right CI process; internal hosts properly bypassed. |
| TLS | Valid certificates, trusted CA in the right JDK/truststore; never disable SSL verify. |
| Maven/Gradle build | Dependencies/plugins resolve cleanly via approved mirrors/repos. |
| Producer verification | Generated tests actually execute and report PASS before publish. |
| Artifact classifier/version | `stubs` JAR has exact coordinates; no stale cached artifacts. |
| Consumer Stub Runner | `REMOTE` performs real downloads when needed; uses dynamic stub URL to call client. |
| CI reproducibility | Pinned versions, redacted audit logs, intentional cold-cache tests. |
| Compatibility | Consumer exercises real client/listener per contract; API bugs separated from infra issues. |

**Takeaway:** **Repository authentication, proxy configuration, and TLS trust are operational prerequisites for distributing contracts—not API contract content themselves.** The producer must verify Groovy/YAML contracts with generated tests before publishing the `stubs` classifier artifact; the consumer needs proper read access so Stub Runner downloads **the exact version**, then calls **the running HTTP stub URL**, never the Maven repository. Separating read/write permissions, injecting CI secrets securely, checking server IDs/proxies/truststores, and diagnosing at the right layer enable pipelines to catch incompatible API changes without sacrificing security or reproducibility.
