# Checking Maintainers, BOMs, and Current Compatibility

## 1. Why Check Before Choosing Dependencies?

A Spring Boot application needs to use Nacos Discovery for service registration and OSS to store invoice files. The development team finds a starter on GitHub, adds the dependency, and builds the project. However, the application is running Spring Boot 4, while the starter was released years ago and has not published a corresponding compatibility matrix. The build may resolve dependencies successfully, yet runtime failures still occur due to Spring API changes, the Jakarta namespace, transitive SDKs, or outdated auto-configuration classes.

Before choosing a library, four questions must be answered:

1. **Who is responsible for maintaining it?** Which organization owns the repository, which group reviews pull requests, are there active maintainers, and what support channels exist?
2. **Which release line is actively maintained?** Are there GA releases, changelogs, security fixes, and upgrade guides?
3. **Which BOM manages the dependencies?** Spring Boot, Spring Cloud, Spring Cloud Alibaba, Aliyun service starters, and product SDKs may each use different BOMs.
4. **Is the entire stack compatible?** You must evaluate JDK, Spring Boot, Spring Cloud, Spring Cloud Alibaba, Nacos/Sentinel/Seata/RocketMQ clients, service starters, and the Alibaba Cloud runtime together.

This lesson belongs to the **Alibaba Cloud** chapter in the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module teaches how to integrate Spring Boot with managed services from AWS, Azure, Google Cloud, and Alibaba Cloud through their respective libraries, covering identity/permission configuration, storage, messaging, data, secret protection, integration testing, and evaluating differences across providers.

After completing this lesson, you will be able to:

- Assess the maintainer organization and health of a library using public evidence.
- Distinguish Spring Cloud Alibaba's maintenance status from upstream Spring Cloud's support status.
- Select the appropriate BOM and versions based on official matrices.
- Read the dependency tree to identify conflicts and overridden dependencies.
- Plan upgrades, testing, version pinning, and rollbacks.
- Recognize the risks of adopting Aliyun Spring Boot Starters that show low maintenance activity.

## 2. Three Maintenance Layers to Verify

In the Alibaba Cloud ecosystem, not every dependency is developed by the same team. Identify the exact project before evaluating it.

| Component | Scope | Where to Check |
| --- | --- | --- |
| **Spring Cloud Alibaba (SCA)** | Spring Cloud-based microservice integration: Nacos, Sentinel, Seata, RocketMQ, and related components | **alibaba/spring-cloud-alibaba** repository, **sca.aliyun.com** docs, release notes, FAQ, and pull requests |
| **Aliyun Spring Boot Starters** | Auto-configuration for specific services such as OSS, SMS, Redis, RDS, or SchedulerX | **alibaba/aliyun-spring-boot** repository, BOM, starter modules, samples, and issues |
| **Alibaba Cloud Java SDK** | Product-specific client APIs, such as OSS SDK or OpenAPI SDK | Product SDK repositories, SDK docs, Maven Central, and security advisories |
| **Spring Boot / Spring Cloud** | Underlying Spring platform that integrations depend on | Official Spring compatibility/support documentation |
| **Managed service runtime** | Nacos/MSE, OSS, SMS, RDS, RocketMQ, or specific cloud services | Product documentation, supported protocols/versions, regions, and Alibaba Cloud operational notices |

A **maintainer entity** can be an organization, a product team, an open-source community, or a group of committers. The repository owner only indicates where the source code is hosted and who holds organizational governance; it does not by itself prove there is a 24/7 support team or an SLA-backed patching commitment.

Three responsibilities must be separated:

- **Library maintainers:** review source code, publish artifacts, fix integration bugs, and update compatibility.
- **Managed service provider:** operate the cloud service, endpoints, SLA, quotas, and server-side changes.
- **Application team:** select versions, manage credentials, run compatibility tests, and upgrade dependencies.

For example, SCA may be maintained by the Alibaba community while an enterprise's Nacos cluster is operated by Alibaba Cloud MSE. An issue with Nacos client compatibility in Spring differs from an MSE endpoint issue; you must identify the right owner to handle it.

## 3. Evaluating Maintainers and Repository Health

### 3.1. Checking Ownership and Governance

Start from the repository linked in official documentation. Check:

- Does the organization/repository owner match the product's official documentation?
- Are there a license, Code of Conduct, CONTRIBUTING guide, or bug reporting guidelines?
- Who has merge/release permissions? Are there multiple independent maintainers, or does one person handle most changes?
- Are there official support channels, a roadmap, release notes, and a community schedule?
- Is there a dedicated process for reporting security issues, or only public issues?

SCA publishes documentation and community links at **sca.aliyun.com**, pointing to its GitHub repository and community channels. The project's FAQ lists the branches currently under maintenance. These are positive signals for governance and development activity, though you should still inspect actual commits and releases on the branch your application plans to use.

For an individual service starter library, check that starter's own repository. Do not infer the maintenance status of **aliyun-spring-boot** from the activity of **spring-cloud-alibaba**; the two projects have separate release schedules.

### 3.2. Signs of a Well-Maintained Project

| Signal | Evidence to Inspect | Evaluation Question |
| --- | --- | --- |
| Releases | GitHub Releases, Maven Central, changelog | Are there recent GA releases with clear descriptions of changes? |
| Commits | Commit history on stable branches | Are bug fixes, dependency updates, and documentation updated regularly? |
| Pull requests | Open/merged PRs, reviewers | Is there independent review and timely feedback? |
| Issues | Bugs, feature requests, stale/closed issues | Are critical bugs triaged and resolved? |
| CI | Build, test, security scan workflows | Do release branches have green pipelines running tests on the target JDK/Boot? |
| Security | Security policy, advisories, dependency bots | Is there a mechanism to receive reports and release security patches? |
| Documentation | Version matrix, migration guides, samples | Does the documentation match the published artifacts? |
| Bus factor | Number of actively participating maintainers/reviewers | If one person steps away, who can review and cut a release? |

Do not judge solely by star count, forks, or total commit count. A repository with many stars but no releases for a long time can still pose a risk. Conversely, a small library with responsive maintainers and stable releases may still meet your needs.

### 3.3. Maintenance Snapshot as of 24/11/2026

At the time of inspection, official **Spring Cloud Alibaba** documentation lists branches **2.2.x, 2021.x, 2022.x, 2023.x, 2025.0.x, and 2025.1.x** as actively maintained. The 2025.x release notes state that 2025.1.x targets Spring Boot 4.0.x/Spring Cloud 2025.1.x and 2025.0.x targets Spring Boot 3.5.x/Spring Cloud 2025.0.x. This is a statement about SCA branches; you also need to check upstream Spring Cloud's support status before concluding the entire stack remains supported. [Official FAQ](https://sca.aliyun.com/en/docs/2025.x/overview/faq/) · [SCA release notes](https://sca.aliyun.com/en/docs/2025.x/overview/version-explain/)

The **alibaba/aliyun-spring-boot** repository describes itself as Spring Boot Starters for Aliyun services. Its README instructs using the **aliyun-spring-boot-dependencies:1.0.0** BOM and notes support for Spring Boot 2 and above. However, public repository activity shows signs of low activity: the GitHub index records the last update on **08/03/2023**. This is **not an official announcement that the project is EOL**, but it is a risk to weigh before adopting the starters in Spring Boot 3/4 applications or critical workloads. [Repository and README](https://github.com/alibaba/aliyun-spring-boot) · [GitHub activity listing](https://github.com/topics/spring-boot-starters)

Meanwhile, the **alibaba/spring-cloud-alibaba** repository has release notes, 2025.x branches, and recent issue/PR activity. The project is working on compatibility updates for Spring Boot 4.2 and Spring Cloud 2026.0: PR **#4429** was opened on 20/11/2026, remained in **Open** status, and was awaiting at least one approving review as of 24/11/2026. Therefore, do not treat an unmerged branch or PR as proof that GA artifacts already support the new stack. [SCA PR #4429](https://github.com/alibaba/spring-cloud-alibaba/pull/4429)

A public comment in an upgrade issue also noted that many committers are not currently performing regular maintenance duties. This is a signal to monitor regarding **bus factor** and review capacity, not an official declaration that the entire project has ceased maintenance. When evaluating a library for production, document reviewers, release cadence, and escalation paths instead of relying on a single isolated remark. [Issue #4400](https://github.com/alibaba/spring-cloud-alibaba/issues/4400)

**Evaluation conclusion:** SCA has clearer branch documentation and release matrices; Aliyun Spring Boot Starters require closer scrutiny due to an outdated README/BOM and signs of low activity. Product SDKs may still be updated independently; for instance, the umbrella SDK repository **aliyun/alibabacloud-sdk** showed activity near the time of inspection. Do not infer that a SDK or starter is still supported solely from the status of a different project.

## 4. What Is a BOM and Why Must You Use the Right One?

A **Bill of Materials (BOM)** is a POM that manages dependency versions. When a BOM is imported into **dependencyManagement**, Maven can select aligned versions for artifacts within the same ecosystem. A BOM reduces repetitive version declarations, but it does not automatically guarantee that every dependency in the application is compatible.

An application may use multiple BOMs:

| BOM | What Group Does It Manage? | Example Coordinates |
| --- | --- | --- |
| Spring Boot dependencies/parent | Core Spring Boot libraries and Boot-managed dependencies | **org.springframework.boot:spring-boot-dependencies** |
| Spring Cloud BOM | Components belonging to the Spring Cloud release train | **org.springframework.cloud:spring-cloud-dependencies** |
| SCA BOM | Spring Cloud Alibaba artifacts and integrated component versions | **com.alibaba.cloud:spring-cloud-alibaba-dependencies** |
| Aliyun Spring Boot BOM | Service starters in the aliyun-spring-boot project | **com.alibaba.cloud:aliyun-spring-boot-dependencies** |
| Product SDK BOM | Modules of a product SDK if published by the provider | Product/SDK-specific |

**Do not use the SCA BOM to guess OSS/SMS starter versions**, and do not assume the Aliyun starter BOM manages every SDK added manually by the application. If a project needs both Nacos Discovery and OSS, it may require the SCA BOM alongside a separate mechanism for managing the OSS SDK/starter version. Before importing multiple BOMs, check dependency convergence and overridden versions.

### 4.1. How Maven Resolves Versions

Maven evaluates dependency management and mediation rules to determine the final version. One BOM may transitively manage versions of indirect dependencies; declaring a version directly on a dependency or importing another BOM can alter the outcome.

Example of what not to do:

~~~xml
<dependency>
    <groupId>com.alibaba.cloud</groupId>
    <artifactId>spring-cloud-starter-alibaba-nacos-discovery</artifactId>
    <!-- Do not declare the version yourself when the BOM already manages this artifact. -->
</dependency>
~~~

When SCA provides a BOM, omit the version on individual starters and let the BOM manage them. If there is a reason to override a transitive dependency, document the rationale, re-test, and track changes across subsequent upgrades.

### 4.2. Importing a BOM Does Not Replace Compatibility Testing

A dependency can resolve cleanly and still fail at runtime due to incompatibilities. For example:

- **javax.*** APIs changed to **jakarta.***.
- Spring Framework changed method signatures or auto-configuration contracts.
- Jackson major version changed.
- The Spring Cloud release train changed interfaces or behavior.
- Nacos client and server are not within the same protocol/feature compatibility range.
- A product SDK changed signing, credential providers, or endpoint resolution.

Therefore, a BOM is a **starting point for version management**, not certification that your application has passed compatibility testing.

## 5. Current SCA Compatibility Matrix

### 5.1. Version Pairs Published by SCA

According to the official 2025.x release notes, the two current lines and historical lines form the following matrix:

| Spring Cloud Alibaba | Spring Cloud | Spring Boot | Java/JDK | Notes |
| --- | --- | --- | --- | --- |
| **2025.1.0.0** | **2025.1.0** | **4.0.x** (release table lists 4.0.0) | JDK 17+ per 2025.1.x branch README | Newer SCA line in the referenced release notes |
| **2025.0.0.0** | **2025.0.0** | **3.5.x** (release table lists 3.5.0) | JDK 17+ per 2025.0.x branch README | Requires separate review of upstream Spring Cloud support status |
| **2023.x** | **2023.x** | **3.2.x** | Per corresponding branch | Legacy line; do not default to this for new projects |
| **2022.x** | **2022.x** | **3.0.x** | Per corresponding branch | Legacy line |
| **2021.x** | **2021.x** | **2.6.x** | Per corresponding branch | Legacy line |
| **2.2.x** | **Hoxton** | **2.2.x/2.3.x depending on release** | Per corresponding branch | Legacy line |

Official sources may update with new releases; re-check before every upgrade: [SCA Version Release Notes](https://sca.aliyun.com/en/docs/2025.x/overview/version-explain/) and [SCA FAQ](https://sca.aliyun.com/en/docs/2025.x/overview/faq/).

### 5.2. Component Versions Pinned by the SCA 2025.x BOM

The SCA release notes also publish integrated component versions:

| Component | SCA 2025.1.0.0 | SCA 2025.0.0.0 |
| --- | --- | --- |
| Sentinel | 1.8.9 | 1.8.9 |
| Nacos | 3.1.1 | 3.0.3 |
| RocketMQ | 5.3.1 | 5.3.1 |
| SchedulerX | 1.13.3 | 1.13.1 |
| Seata | 2.5.0 | 2.5.0 |

Do not independently bump a component to a newer version simply because that artifact exists on Maven Central. SCA may rely on specific behavior or APIs of the component; upgrading Nacos/Sentinel/Seata in isolation can break compatibility. If an upgrade is needed, inspect official issues/PRs, component release notes, and run integration tests.

### 5.3. Note on Upstream Spring Cloud Support

Two concepts must be distinguished:

- **SCA branch maintenance:** SCA's FAQ lists which branches the SCA project maintains.
- **Spring Cloud support:** the support lifecycle of the Spring Cloud release train and its upstream projects.

The Spring Cloud support table updated on **18/11/2026** marks the **2025.0** release train with a dash (outside OSS support policy), while 2025.1 remains in the active column. Thus, even though the SCA FAQ still lists **2025.0.x** as maintained, a Boot 3.5/Cloud 2025.0 stack must be evaluated against upstream policies and your organization's support requirements. Do not interpret **SCA branch active** as **every upstream component still receives security fixes**. [Spring Cloud Supported Versions](https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions)

Spring Cloud states a support policy of at least 3 years for major versions and at least 12 months for minor versions, while recommending the latest GA release. A release train comprises multiple projects; the train's support window depends on the lifecycles of its constituent projects. The support table also notes that third-party dependencies may reach end-of-support before the Spring Cloud release train ends. Consequently, inspect the lifecycles of Nacos, Sentinel, Seata, RocketMQ, and SDKs individually rather than looking only at the Spring Cloud version.

### 5.4. Spring Cloud 2026.0 and Spring Boot 4.2

Spring Cloud **2026.0.0** was released on 20/11/2026 and Spring Boot **4.2.0** has published release notes. However, as of **24/11/2026**, PR **#4429** upgrading SCA to Spring Cloud 2026.0.0/Spring Boot 4.2.0 is still open and requires at least one approving review. The SCA 2025.x release notes page does not yet list GA artifacts for this new pair.

Therefore:

1. Do not invent an SCA 2026.0.0 version just because upstream Spring Cloud released 2026.0.0.
2. Do not treat an unmerged branch or PR as a released production dependency.
3. Wait for the PR to be reviewed/merged, an SCA GA release to ship, and release notes to be updated.
4. Once the artifact appears on Maven Central, verify the BOM, changelog, JDK baseline, component versions, and integration tests.

This is a concrete example showing that compatibility is the intersection of multiple projects, not just a single version number. [Spring Cloud release](https://github.com/spring-cloud/spring-cloud-release/releases) · [SCA PR #4429](https://github.com/alibaba/spring-cloud-alibaba/pull/4429)

## 6. Maven Example: Managing the SCA BOM Properly

The example below uses the **Spring Boot 4.0.x + Spring Cloud 2025.1.x + Spring Cloud Alibaba 2025.1.0.0** line per the published matrix. Choose a Boot 4.0.x version verified in the project's release notes; do not arbitrarily substitute Boot 4.2.

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>${springBootVersion}</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
    <spring-cloud.version>${springCloudVersion}</spring-cloud.version>
    <spring-cloud-alibaba.version>${springCloudAlibabaVersion}</spring-cloud-alibaba.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${springCloudVersion}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>com.alibaba.cloud</groupId>
            <artifactId>spring-cloud-alibaba-dependencies</artifactId>
            <version>${springCloudAlibabaVersion}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.alibaba.cloud</groupId>
        <artifactId>spring-cloud-starter-alibaba-nacos-discovery</artifactId>
    </dependency>
</dependencies>
~~~

**BOOT_VERSION** must be a Boot 4.0.x GA version accepted by the project. The Spring Cloud BOM manages Spring Cloud projects; the SCA BOM manages Alibaba's integration artifacts. When upgrading versions, update the version property in one place, then inspect the effective POM and dependency tree.

Example discovery configuration:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    nacos:
      discovery:
        server-addr: ${NACOS_SERVER_ADDR}
        namespace: ${NACOS_NAMESPACE}
~~~

This is a basic property example. For Nacos Config on the SCA 2025.1 branch, the release notes state that bootstrap config support has been removed and applications must migrate to **spring.config.import** per the new branch's documentation. Do not copy **bootstrap.yml** configurations from older projects to the new branch without reading the migration guide.

## 7. Aliyun Spring Boot Starter BOM: Inspecting Separately

### 7.1. BOM and Artifacts

The **alibaba/aliyun-spring-boot** repository instructs importing its BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.alibaba.cloud</groupId>
            <artifactId>aliyun-spring-boot-dependencies</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Then add the service starter, for example:

~~~xml
<dependency>
    <groupId>com.alibaba.cloud</groupId>
    <artifactId>aliyun-oss-spring-boot-starter</artifactId>
</dependency>
~~~

BOM **1.0.0** is the version published in the repository's README. The README states support for Spring Boot 2 and above, but does not provide a detailed matrix proving every starter is compatible with Spring Boot 3.x or 4.x. A **Boot 2+** statement should not be interpreted as certification for all subsequent major versions.

### 7.2. Risk Assessment Before Adoption

Before adding a starter to production, verify:

- Does the starter artifact have recent releases on Maven Central?
- Which version of the product SDK does the starter's POM pull in?
- Is that SDK still maintained and compatible with the target JDK/Spring Boot?
- Does the auto-configuration use **javax.*** or **jakarta.***?
- Are there tests against Spring Boot 3/4?
- Are there security fixes, issue responses, and migration notes?
- Does the starter support modern RAM role/STS credential providers, or only static AccessKeys?
- Is there a way to override the default bean/client and configure timeouts/endpoints?

If compatibility evidence is missing, test it on a small branch with integration tests and inspect the source/bytecode before adopting it. For OSS, you can use the OSS Java SDK directly and configure the Spring bean yourself if the legacy starter does not meet your requirements.

### 7.3. Distinguishing Between a Starter and an Actively Maintained SDK

An infrequently updated starter does not mean the underlying product SDK has stopped receiving updates. For example, the umbrella SDK repository **aliyun/alibabacloud-sdk** showed activity near the time of inspection. However, that also does not prove a specific starter automatically works with the newer SDK. You must inspect the actual transitive versions and the APIs that the starter invokes.

When using an SDK directly, manage the client inside a Spring bean, reuse the client, configure credentials/region/endpoint per product guidance, and shut down the client when the application stops. Isolate the SDK behind an internal interface so the adapter can be replaced when the provider changes.

## 8. Inspecting the Dependency Tree and Effective POM

### 8.1. Seeing Which Versions Maven Actually Selects

Run in the project directory:

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn dependency:tree -Dverbose -DoutputFile=target/dependency-tree.txt
~~~

Inspect the output to determine:

- Resolved versions of **spring-boot**, **spring-cloud**, and **com.alibaba.cloud** artifacts.
- Actual resolved versions of Nacos client, Sentinel, Seata, RocketMQ, and SchedulerX.
- Which OSS/SMS/RDS SDKs are pulled in.
- Which dependencies are **omitted for conflict** or overridden by an explicit version.
- Whether the same library appears under multiple major versions.

For example, one module might require Nacos client 3.1.x while another dependency pulls in 2.x. The build may still succeed if Maven picks one version, but runtime can throw **NoSuchMethodError**, **NoClassDefFoundError**, or protocol errors.

### 8.2. Enforcing Dependency Convergence

You can use Maven Enforcer to block non-convergent dependency trees:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <id>enforce-dependency-convergence</id>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <dependencyConvergence/>
                    <requireUpperBoundDeps/>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

**dependencyConvergence** detects multiple versions of the same artifact in the dependency tree; **requireUpperBoundDeps** detects cases where the selected version is lower than what another dependency requests. Not every conflict can be solved by picking the highest version; follow the official BOM and verify API compatibility before overriding.

If using Gradle, check **dependencies**, **dependencyInsight**, and dependency constraints/platforms to trace where the chosen version comes from. Do not import Maven BOMs haphazardly in Gradle; use **platform(...)** or **enforcedPlatform(...)** intentionally.

### 8.3. Recording Verified Versions

Create a table in the project's technical documentation so the development team knows the exact running stack:

| Component | Pinned Version | Decision Source | Tests Executed |
| --- | --- | --- | --- |
| JDK | 17 | SCA 2025.1 baseline | Build/unit/integration |
| Spring Boot | 4.0.x | Boot parent/BOM | Context smoke test |
| Spring Cloud | 2025.1.0 | Spring Cloud BOM | Discovery test |
| Spring Cloud Alibaba | 2025.1.0.0 | SCA release notes | Nacos integration |
| Nacos client | BOM-managed | SCA component matrix | Register/config lookup |
| OSS SDK/starter | Separately chosen version | Product SDK/starter docs | Upload/download test |

This table is the application's tested baseline, not a copy of a vendor compatibility table. Update it after every dependency upgrade and retain the corresponding test results and release notes.

## 9. Safe Upgrade Process

### 9.1. Before Upgrading

1. Record the current versions from the effective POM/dependency tree.
2. Read release notes and migration guides for Spring Boot, Spring Cloud, SCA, and product SDKs.
3. Review security advisories and known issues for core dependencies.
4. Confirm the JDK baseline, Jakarta namespace, Jackson version, and deprecated APIs.
5. Select a version pair listed in the official matrix.
6. Create a dedicated upgrade branch without mixing in major business logic changes at the same time.

### 9.2. During the Upgrade

- Upgrade Spring Boot, Spring Cloud, and SCA together according to the published version pair.
- Keep BOMs as the primary version authority; avoid pinning child dependency versions directly unless necessary.
- Upgrade product SDKs/starters separately if required by their compatibility matrices.
- Run compilation, unit tests, Spring context tests, and integration tests against sandbox services.
- Inspect startup logs, the auto-configuration report, and warnings about deprecated properties.
- Verify that credentials, RAM roles, endpoints, regions, and TLS still work.
- Measure latency/error rates before and after the upgrade in staging.

### 9.3. After Upgrading

- Canary one workload before rolling out broadly.
- Monitor connection errors, timeouts, discovery/config refreshes, and service API calls.
- Check metrics and logs, not just whether the process started.
- Keep previous artifacts and configurations ready for rollback.
- Update the dependency inventory, SBOM, and tested version baseline.

Do not upgrade the entire ecosystem merely because a new BOM was published. If a project needs a security fix in a product SDK, you can upgrade that SDK independently after confirming compatibility without changing the Spring release train.

## 10. Practical Compatibility Testing

### 10.1. Minimum Tests for Spring Cloud Alibaba

| Test | Objective | Passing Signal |
| --- | --- | --- |
| Spring context startup | Auto-configuration initializes properly | ApplicationContext starts without errors |
| Nacos registration | Service registers into the right namespace/group | Instance appears with accurate metadata |
| Discovery lookup | Client resolves the service | Instance is returned and endpoint call succeeds |
| Config import/refresh | Configuration loads from Nacos per current branch rules | Properties load and refresh as designed |
| Sentinel rule | Rule is enforced | Requests exceeding threshold behave as configured |
| Seata transaction | Distributed transaction commits/rolls back | No inconsistent state left behind |
| RocketMQ messaging | Producer/consumer use the right protocol | Messages are sent, received, and handled idempotently |

Only test the components the application actually uses. There is no need to set up Seata/RocketMQ for an application that only needs Nacos Discovery.

### 10.2. Tests for Service Starters or SDKs

For OSS, test upload/download, object metadata, multipart uploads, endpoints/regions, and RAM permissions. For SMS, test approved senders/templates, test phone numbers, and quotas. For Redis/RDS, test TLS, connection pools, failover, timeouts, and driver versions.

Unit tests that mock clients only validate adapter logic. Integration tests against a sandbox account are what actually verify credentials, networking, IAM/RAM policies, and real server APIs.

### 10.3. Common Errors

| Symptom | Possible Cause | How to Investigate |
| --- | --- | --- |
| **NoSuchMethodError** | Incompatible Spring/SDK transitive version | Dependency tree, effective POM, and BOM |
| **ClassNotFoundException** | Missing dependency or javax/jakarta mismatch | Classpath, starter version, and migration notes |
| ApplicationContext failure | Auto-configuration/property changes | Startup condition report and release notes |
| Nacos registration failure | Namespace, endpoint, credentials, network, or client/server mismatch | Nacos logs, version matrix, RAM/ACL |
| OSS **AccessDenied** | Incorrect RAM/bucket policy or principal | Runtime credentials and resource ARN |
| OSS **SignatureDoesNotMatch** | AccessKey/STS token, region, endpoint, clock skew, and signing version | SDK config and system clock |
| SDK timeout | VPC/public endpoint, DNS, firewall, or overly short timeout | Network path and request ID |
| Credentials expired | STS refresh, role trust policy, OIDC token, and cache/provider lifecycle | Credentials provider and token expiry |
| Local tests pass, staging fails | Different credentials providers or regions | Non-sensitive principal/region info and config profiles |
| Build passes but runtime fails | Compilation does not cover reflection/auto-config/protocol | Spring context and integration tests |

## 11. Decision Rubric: Should You Adopt This Library?

Evaluate each criterion on a three-level scale: **Pass**, **Needs Verification**, **Fail**.

| Criterion | Pass | Needs Verification | Fail |
| --- | --- | --- | --- |
| Maintainers | Clear organization/team and active reviewers | Single primary maintainer, inconsistent responsiveness | No identifiable responsible entity |
| Releases | GA releases with proper changelogs | Old release, though with patches/PRs | No reliable artifacts/releases |
| Compatibility | Matrix covering the exact Boot/Cloud/JDK | General claims only, requires self-testing | Incompatible with target stack |
| Security | Advisories/process and patches exist | Unclear SLA or response cadence | Known critical vulnerabilities unaddressed |
| Dependencies | Clear BOM, convergent dependency tree | Overrides required and must be controlled | Unresolvable major version conflicts |
| Testing | CI and appropriate integration tests exist | Only unit tests/samples | Fails to build/test on target stack |
| Support | Documentation/escalation channels available | Community-only, unclear SLA | No path for handling incidents |

For low-activity libraries, adoption may still be acceptable if the API is stable and the organization is willing to own an adapter, fork, or patch maintenance. However, you must account for internal maintenance costs and have a replacement plan if the dependency becomes an upgrade blocker.

## 12. Hands-on Exercise

**Exercise:** Evaluate a Spring Boot application that uses Nacos Discovery and OSS before upgrading to a new stack.

1. Record the current JDK, Spring Boot, Spring Cloud, SCA, Nacos client, and OSS SDK versions.
2. Locate the official repository and maintainer entity for each dependency.
3. Read release notes, supported branches, issues/PRs, and security advisories.
4. Cross-reference the SCA matrix with the target Spring Boot/Spring Cloud versions.
5. Import the right BOMs and run **mvn help:effective-pom** and **mvn dependency:tree**.
6. Identify version conflicts and trace which dependency pulled them in.
7. Upgrade on a separate branch and run context/discovery/OSS integration tests.
8. Write a report covering version choices, risks, test results, and a rollback plan.

**Review Questions:**

1. Why does repository ownership not equate to an SLA support team?
2. What evidence indicates that a library branch is actively maintained?
3. Which artifacts do the SCA BOM and the Aliyun Spring Boot BOM manage respectively?
4. Why is a supported Spring Cloud version alone insufficient to prove that the Nacos client or OSS SDK is also supported?
5. SCA 2025.0.x is listed as active in the FAQ while Spring Cloud 2025.0 is marked outside the OSS support policy: how should this difference be explained?
6. Why shouldn't an unmerged SCA branch or PR be used as a production dependency?
7. What issues do dependency:tree and effective-pom help uncover?
8. When might you use an older service starter, and when should you wrap the product SDK directly?
9. Under what conditions can a dependency with few maintainers be accepted if the enterprise owns a fork?
10. Which integration tests should be in place before upgrading SCA?

## 13. References

- [Spring Cloud Alibaba — Release Notes](https://sca.aliyun.com/en/docs/2025.x/overview/version-explain/): SCA/Spring Cloud/Spring Boot matrix and component versions.
- [Spring Cloud Alibaba — FAQ](https://sca.aliyun.com/en/docs/2025.x/overview/faq/): actively maintained SCA branches and where to look up versions.
- [Alibaba — Spring Cloud Alibaba repository](https://github.com/alibaba/spring-cloud-alibaba): source, branches, issues, releases, and contributor activity.
- [SCA — PR #4429](https://github.com/alibaba/spring-cloud-alibaba/pull/4429): Spring Boot 4.2/Spring Cloud 2026.0 upgrade status at the time of inspection.
- [SCA — Issue #4400](https://github.com/alibaba/spring-cloud-alibaba/issues/4400): discussion on supporting the new stack and reviewer/committer status.
- [Spring Cloud — Supported Versions](https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions): upstream support policy and release train status.
- [Spring Cloud — Releases](https://github.com/spring-cloud/spring-cloud-release/releases): inspecting GA releases and changelogs.
- [Alibaba — Aliyun Spring Boot Starters](https://github.com/alibaba/aliyun-spring-boot): BOM, artifacts, starters, and support scope stated in the README.
- [Alibaba Cloud Java SDK](https://github.com/aliyun/alibabacloud-sdk): activity and product SDK documentation.
- [Alibaba Cloud SDK — Manage credentials](https://www.alibabacloud.com/help/en/sdk/developer-reference/v2-manage-access-credentials): credentials providers, RAM roles, STS, and OIDC.

**Expected Outcome:** Learners know how to verify maintainers, read BOMs and version matrices from official sources, distinguish SCA's maintenance status from upstream support lifecycles, inspect dependency trees, and upgrade Spring Boot/Spring Cloud/Alibaba Cloud integrations in a controlled manner.
