# Azure Pipelines cho quy trình build ứng dụng Java

Một dịch vụ Spring Boot chạy trên Azure App Service thường được đóng gói từ mã Java bằng Maven hoặc Gradle. Nếu từng lập trình viên tự build trên máy, rồi gửi JAR qua chat hoặc tải lên máy chủ, rất khó trả lời: **JAR này được tạo từ commit nào? Dùng JDK bao nhiêu? Các bài kiểm thử có chạy không? Dependency có được tải từ nguồn tin cậy không? Ai đã duyệt code trước khi build? Có thể tạo lại cùng artifact và truy vết lỗi không?**

**Azure Pipelines** là dịch vụ CI/CD thuộc Azure DevOps, cho phép mô tả quy trình bằng YAML và thực thi trên agents. Đối với Java, một pipeline tốt không chỉ gọi **mvn package** hoặc **gradle build**: nó chuẩn hóa JDK/toolchain, xác minh source, chạy kiểm thử và quality gates, xuất báo cáo, tạo **build artifact bất biến** và giữ bằng chứng cho các bước triển khai/kiểm toán sau này.

Bài thuộc chương **CI/CD và chuỗi cung ứng phần mềm**, module **CLOUD_PROVIDERS_AZURE**. Trong lộ trình tìm hiểu Microsoft Azure từ subscription, resource group, Microsoft Entra ID đến network, compute, storage và data, Azure Pipelines là mắt xích tự động hóa quá trình **build, xác minh, chuẩn bị triển khai, giám sát và kiểm soát rủi ro/chi phí** của ứng dụng Java trên Azure.

> **Phạm vi:** Tập trung vào **quy trình build Java bằng Azure Pipelines**: source → checkout → JDK → Maven/Gradle → test/quality → JAR → publish artifact. Đẩy image lên Azure Container Registry hoặc triển khai App Service/AKS là các bước có thể nối tiếp trong CI/CD, nhưng **không đồng nhất build thành deploy** và không cần triển khai tài nguyên Azure thật để thực hành bài này.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích Azure DevOps organization/project, repository, pipeline, run, agent, pool, job, step, task, stage và artifact.
2. Phân biệt **CI build** với **CD release/deployment** và tại sao build artifact nên được tạo một lần rồi tái sử dụng.
3. Tạo file **azure-pipelines.yml** cho Maven Java 17/21 trên Microsoft-hosted Ubuntu agent.
4. Sử dụng **JavaToolInstaller@0**, Maven Wrapper và **Maven@4** đúng mục đích.
5. Chạy **mvn verify** để kiểm thử rồi package, xuất JUnit XML và publish artifact.
6. Viết pipeline tương tự cho **Gradle Wrapper** và biết các điều kiện của **Gradle@3/@4**.
7. Phân biệt pipeline **trigger** sau push và **PR build validation** trên Azure Repos so với GitHub.
8. Thiết lập **cache dependency** bằng Cache@2 và biết khi nào không nên cache.
9. Quản lý biến môi trường, secret variables, variable groups, Azure Key Vault, service connections và quyền của token pipeline.
10. Thiết kế unit tests, integration tests, code coverage, quality gates và tránh che dấu test failures.
11. Bảo vệ software supply chain: nguồn dependencies, wrapper, lockfiles, SBOM, provenance, scans và least privilege.
12. Tách artifacts tạm thời của job khỏi **Pipeline Artifacts**; truy xuất artifact theo commit/build ID.
13. Chẩn đoán lỗi JDK/Maven/Gradle, failed tests, 401/403 private feeds, cache, disk quota và agent outage.
14. Đặt build-time SLO, phân tích thời gian/cost của agents, retention và chiến lược tối ưu.
15. Thực hành một vòng build và đánh giá checklist trước khi bật CI bắt buộc trên nhánh chính.

## 2. Tình huống xuyên suốt: Orders API bằng Spring Boot

Nhóm phát triển dịch vụ **orders-api** trên Java 21, Spring Boot và Maven. Ứng dụng sẽ chạy trên Azure App Service hoặc trong container ở một giai đoạn khác.

Yêu cầu từ nhóm:

- Mọi push vào nhánh **main** hoặc **develop** phải được build bằng JDK đã chọn.
- Mọi PR vào **main** phải trải qua build validation và unit tests.
- Không cho các unit tests bị bỏ qua chỉ vì muốn JAR build nhanh.
- Pipeline tạo JAR có tên/version rõ ràng từ cùng source commit đã được kiểm tra.
- Có báo cáo test/coverage để reviewer và SRE xem được.
- Dependency cache giúp rút thời gian nhưng không làm mất khả năng reproducibility.
- Pipeline của PR không được đọc production credentials hay thực hiện deployment.
- Nhóm phát hành có thể lấy artifact của run đã được phê duyệt; không rebuild tùy tiện trên server đích.
- Log không chứa passwords, PAT, access token hoặc secrets.

Sơ đồ CI cơ bản:

~~~mermaid
flowchart LR
    DEV["Developer commit / PR"] --> GIT["Azure Repos / GitHub"]
    GIT --> TRIGGER["Azure Pipelines<br/>CI / PR validation"]
    TRIGGER --> AGENT["Build agent<br/>JDK + Maven/Gradle"]
    AGENT --> TEST["Compile + unit/integration tests"]
    TEST --> QA["Coverage, dependencies,<br/>quality/security checks"]
    QA --> PKG["Package JAR / WAR"]
    PKG --> ART["Publish Pipeline Artifact<br/>run + commit provenance"]
    ART -. "later approved CD" .-> DEPLOY["App Service / AKS / VM"]
~~~

**Kết quả CI:** một run có trạng thái, logs, JUnit/test reports và artifact. **Kết quả CD:** triển khai artifact đã kiểm tra lên một environment, thường có approvals và credentials riêng.

## 3. Azure Pipelines trong hệ sinh thái Azure DevOps

| Khái niệm | Chức năng | Ví dụ |
|---|---|---|
| **Organization** | Biên quản trị Azure DevOps | Organization của công ty |
| **Project** | Nhóm repos, boards, pipelines, permissions | Commerce Platform |
| **Repository** | Lưu mã nguồn và pipeline YAML | orders-api |
| **Pipeline** | Định nghĩa tự động hóa build/release | orders-api-ci |
| **Run** | Một lần pipeline thực thi trên commit/context | Build #1428 |
| **Agent** | Máy/process thực hiện công việc | Microsoft-hosted Ubuntu |
| **Agent pool** | Nguồn agents có thể được chọn cho jobs | Azure Pipelines pool / custom pool |
| **Job** | Một nhóm steps trên một agent hoặc server context | BuildAndTest |
| **Step** | Script/task/checkout trong một job | Maven@4 |
| **Task** | Tác vụ đóng gói sẵn của Azure Pipelines | Cache@2 |
| **Stage** | Nhóm jobs có điều kiện/phụ thuộc | Build, Scan, Package |
| **Variable** | Giá trị cấu hình pipeline | JDK_VERSION, MAVEN_CACHE |
| **Service connection** | Danh tính/ủy quyền để gọi tài nguyên ngoài | Azure Resource Manager connection |
| **Pipeline Artifact** | Output được lưu/phân phối từ run | orders-api JAR |
| **Environment** | Đích deployment có thể có checks/approvals | staging/prod |

### 3.1. Pipeline YAML vs classic pipeline

Với YAML, cấu hình **sống trong repository**, review qua Pull Request, có lịch sử thay đổi cùng source code. Classic UI vẫn tồn tại trong một số dự án; YAML dễ chuẩn hóa templates, kiểm thử và áp quy trình GitOps.

### 3.2. Agent và agent pools

**Microsoft-hosted agent** do Azure DevOps cung cấp cho mỗi job; image như **ubuntu-latest** có nhiều tool preinstalled nhưng version có thể thay đổi khi image cập nhật. Job mới không nên phụ thuộc dữ liệu/trạng thái của job cũ.

**Self-hosted agent** do tổ chức vận hành, phù hợp nếu cần mạng nội bộ, công cụ đặc thù, build rất nặng hoặc kiểm soát phần cứng. Đổi lại phải tự cập nhật OS/JDK/tools, bảo vệ token/working directory, quản lý quotas và tránh độc hại từ PR không tin cậy.

Không dùng một self-hosted agent có production credentials mạnh để tự động chạy code của mọi PR từ fork.

### 3.3. Microsoft-hosted image không phải environment bất biến

Tên **ubuntu-latest** có thể trỏ đến một image OS/tool set mới theo thời gian. Với yêu cầu reproducibility mạnh:

- Chọn **vmImage** cụ thể khi phù hợp và được hỗ trợ.
- Chỉ định **JDK version** rõ ràng.
- Dùng Maven/Gradle Wrapper được pin version, kiểm tra checksum.
- Pin dependencies/plugins, kiểm tra resolved tree.
- Lưu provenance của agent image/toolchain.
- Có thể dùng container job image được pin bằng digest, với điều kiện image/run capabilities phù hợp.

## 4. CI khác CD và “build once, deploy many”

### 4.1. Continuous Integration

CI kiểm chứng code trên mỗi push/PR theo policy:

~~~text
Checkout source
→ Configure JDK
→ Resolve dependencies
→ Compile
→ Unit tests
→ Integration tests (nếu có)
→ Static checks + coverage
→ Package
→ Publish artifact
~~~

Nếu các quality gates bắt buộc không đạt, **không publish artifact như một bản phát hành hợp lệ**.

### 4.2. Continuous Delivery/Deployment

CD có thể:

~~~text
Download approved artifact
→ Verify checksum/signature and metadata
→ Apply environment-specific non-secret config
→ Deploy to staging
→ Smoke test
→ Approval / checks
→ Deploy to production
→ Monitor / rollback
~~~

CD có thể dùng Azure Resource Manager service connection, managed identity/federated credential, Azure App Service deploy, AKS manifests hoặc ACR. **Các quyền đó không cần cho job chỉ build Java từ public dependencies**.

### 4.3. Tại sao không rebuild ở production?

Nếu mỗi environment tự chạy Maven, dependency repository hoặc plugin version có thể đổi giữa những lần build, khiến artifact chạy ở production **không giống** cái đã test ở staging. Một artifact được build và kiểm tra một lần có **run ID, source commit, checksum, SBOM, provenance**, giúp điều tra và rollback.

Một artifact tốt cần mang đủ evidence nhưng **không chứa secret** hoặc credentials từ build environment.

## 5. Maven và Gradle: Java build lifecycle

### 5.1. Maven

Maven sử dụng **pom.xml** và lifecycle; các phases thường gặp:

| Phase | Vai trò | Kiểm thử? |
|---|---|---|
| validate | Kiểm tra project/POM | Tùy plugins |
| compile | Compile main sources | Không tự chạy test |
| test | Chạy unit tests với Surefire mặc định khi được cấu hình | Có |
| package | Đóng gói jar/war | Các phases trước được chạy |
| verify | Chạy kiểm tra sau package, có thể bao gồm integration-test/Failsafe/JaCoCo check | Tùy POM |
| install | Đưa artifact vào local Maven repository | Không cần cho CI đơn module |
| deploy | Publish vào remote Maven repository (khác deploy ứng dụng) | Có side effect lên artifact feed |

**Khuyến nghị cơ sở:** dùng **mvn -B -ntp clean verify**, không chỉ **package -DskipTests**. **verify** chỉ chạy quality gates mà **POM đã cấu hình**; nó không tự sinh integration tests/coverage/security scanning nếu POM không có plugins tương ứng.

### 5.2. Maven Wrapper

Dự án nên commit **mvnw**, **mvnw.cmd**, **.mvn/wrapper/maven-wrapper.properties** cùng files cần thiết để cài một Maven version được chọn. Wrapper vẫn tải Maven distribution nếu agent chưa cache; kiểm tra **distributionUrl/checksum/provenance** theo policy.

~~~bash
# Local baseline, trước khi đưa vào Azure Pipelines:
java -version
./mvnw -B -ntp clean verify
~~~

Trong Windows, dùng **mvnw.cmd** hoặc môi trường shell phù hợp. Trên Linux, file **mvnw** cần có executable permission, hoặc có thể gọi **bash ./mvnw** khi script tương thích.

### 5.3. Gradle

Gradle sử dụng **settings.gradle(.kts)**, **build.gradle(.kts)** và Wrapper:

~~~bash
./gradlew --no-daemon clean check
./gradlew --no-daemon bootJar
~~~

- **test** chạy unit tests.
- **check** thường phụ thuộc test/verification tasks.
- **build** thường gồm assemble + check.
- **bootJar** đóng executable Spring Boot JAR khi plugin Spring Boot được cấu hình.
- **integrationTest** không phải task mặc định trong mọi Gradle project; cần khai báo/test suites.
- **Gradle Wrapper** dùng distribution/version được pin.
- Không chạy **gradle** từ agent system nếu muốn wrapper-controlled version.

### 5.4. JDK version

JDK dùng biên dịch phải tương thích **pom.xml maven-compiler-plugin release** hoặc **Gradle Java toolchain**. Đừng mặc định JDK 21 dùng để chạy Java 8 bytecode với cùng semantics/library dependency mà không kiểm tra. Phân biệt:

- **Build JDK:** JDK agent thực thi Maven/Gradle.
- **Target bytecode release:** version của class files và API có thể dùng.
- **Runtime JRE/JDK:** environment chạy ứng dụng sau deployment.
- **Multi-module toolchains:** có thể có modules dùng version khác.

Một project Spring Boot 3.x thường đòi hỏi Java 17 trở lên; tuy nhiên hãy kiểm tra version matrix của framework/plugin thực tế.

## 6. Cấu trúc repository gợi ý

~~~text
orders-api/
├── azure-pipelines.yml
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/
│   └── wrapper/
│       └── maven-wrapper.properties
├── src/
│   ├── main/
│   │   ├── java/com/example/orders/
│   │   └── resources/application.yml
│   └── test/
│       └── java/com/example/orders/
├── docs/
│   └── build-and-release.md
└── .gitignore
~~~

Không commit **target/**, **build/**, **.gradle/**, **.m2/** hoặc credentials. Những files generated như SBOM/test reports có thể publish từ pipeline thay vì commit vào Git.

### 6.1. POM tối thiểu về mặt tư duy

Một Spring Boot Maven project cần plugin/dependencies để tạo executable JAR và kiểm thử. Java version, Spring Boot plugin, surefire/failsafe, JaCoCo và checks phải được định nghĩa theo framework/BOM. Pipeline **không thay thế** POM.

### 6.2. Maven Wrapper là executable code

Trước khi cho phép pipeline thực thi **./mvnw** trong PR từ nguồn ngoài, kiểm tra wrapper scripts/JAR/distribution URL. Một PR có thể sửa pipeline YAML, wrapper hoặc POM để thực thi bất kỳ code nào trong job. Vì vậy không gắn secrets quyền cao vào PR job.

## 7. Tạo pipeline trong Azure DevOps

Một quy trình thao tác trên UI:

1. Đăng nhập Azure DevOps organization có quyền phù hợp.
2. Mở **Project → Pipelines → New pipeline**.
3. Chọn source repo (**Azure Repos Git**, GitHub hoặc provider được hỗ trợ).
4. Cấp quyền kết nối repository khi cần; không mở rộng quyền ngoài yêu cầu.
5. Chọn **Existing Azure Pipelines YAML file** nếu đã commit **azure-pipelines.yml**, hoặc tạo mới theo policy.
6. Review file YAML trong PR/nhánh làm việc.
7. Chọn agent pool, kiểm tra hosted parallelism entitlement/quota.
8. Run lần đầu trên commit tin cậy, theo dõi các bước.
9. Sau khi kiểm thử, bật branch policy/PR validation cho main.
10. Ghi ownership, notification và artifact retention policy.

**Không có pipeline hay tài nguyên Azure thật được tạo khi biên soạn bài.** Những bước trên là hướng dẫn cho môi trường lab hoặc dự án được phê duyệt.

## 8. YAML pipeline Maven: build, test và publish JAR

Ví dụ dưới đây dành cho repository Java 21 dùng **Maven Wrapper**. Yêu cầu: có **pom.xml**, script **mvnw** tương thích Linux và POM được cấu hình tạo JAR. Tên artifact là **orders-api-java**.

~~~yaml
# azure-pipelines.yml
trigger:
  branches:
    include:
      - main
      - develop

# pr: được Azure Pipelines dùng cho GitHub/Bitbucket Cloud.
# Với Azure Repos Git, PR validation do Branch Policies cấu hình.
pr:
  branches:
    include:
      - main

pool:
  vmImage: 'ubuntu-latest'

variables:
  MAVEN_CACHE_FOLDER: '$(Pipeline.Workspace)/.m2/repository'

steps:
  - checkout: self
    clean: true
    fetchDepth: 1
    persistCredentials: false

  - task: JavaToolInstaller@0
    displayName: 'Select JDK 21'
    inputs:
      versionSpec: '21'
      jdkArchitectureOption: 'x64'
      jdkSourceOption: 'PreInstalled'

  - task: Cache@2
    displayName: 'Cache Maven dependencies'
    inputs:
      key: 'maven | "$(Agent.OS)" | **/pom.xml'
      restoreKeys: |
        maven | "$(Agent.OS)"
      path: '$(MAVEN_CACHE_FOLDER)'

  - bash: |
      set -euo pipefail
      java -version
      bash ./mvnw --version
      bash ./mvnw -B -ntp \
        -Dmaven.repo.local="$(MAVEN_CACHE_FOLDER)" \
        clean verify
    displayName: 'Maven compile, test and verify'

  - task: PublishTestResults@2
    displayName: 'Publish JUnit XML results'
    condition: succeededOrFailed()
    inputs:
      testResultsFormat: 'JUnit'
      testResultsFiles: '**/surefire-reports/TEST-*.xml'
      searchFolder: '$(System.DefaultWorkingDirectory)'
      failTaskOnFailedTests: true
      failTaskOnMissingResultsFile: true

  - task: CopyFiles@2
    displayName: 'Stage JAR artifact'
    condition: succeeded()
    inputs:
      SourceFolder: '$(Build.SourcesDirectory)/target'
      Contents: '*.jar'
      TargetFolder: '$(Build.ArtifactStagingDirectory)/app'
      flattenFolders: true

  - task: PublishPipelineArtifact@1
    displayName: 'Publish immutable build output'
    condition: succeeded()
    inputs:
      targetPath: '$(Build.ArtifactStagingDirectory)/app'
      artifact: 'orders-api-java'
      publishLocation: 'pipeline'
~~~

### 8.1. Điều kiện để ví dụ chạy được

- Repo là **Maven project có wrapper**; Maven wrapper scripts phải có mặt trong checkout và distribution phải tải được theo network policy.
- **JavaToolInstaller@0** ở mode **PreInstalled** yêu cầu agent image có JDK 21 hỗ trợ. Nếu image thay đổi hoặc self-hosted agent không có, dùng phương án cài JDK đáng tin khác và pin version.
- POM có unit tests và Maven Surefire xuất XML.
- **CopyFiles@2** lấy JAR trực tiếp trong **target/** của **single-module project**. Với multi-module, phải sửa paths/selector.
- **PublishPipelineArtifact@1** phù hợp Azure DevOps Services; những môi trường Azure DevOps Server hoặc pipeline type khác có thể cần task artifact tương thích.
- Trường **failTaskOnMissingResultsFile** giúp không im lặng khi project kỳ vọng tests; một số task versions/conditions có semantics riêng, cần xác minh trên agent/task version.
- Nếu build không tạo file JAR, nên bổ sung bước kiểm tra file tồn tại trước Publish; không tin CopyFiles mặc định sẽ fail khi không tìm thấy artifact.

### 8.2. Vì sao verify thay package?

**clean verify** đi qua compile, test và package; nếu POM cấu hình JaCoCo/Failsafe/SBOM checks đúng, các goals tương ứng có thể được chạy theo lifecycle. **Không** tự động bảo đảm dependency scanning/coverage khi POM thiếu plugins.

### 8.3. Vì sao PublishTestResults chạy cả khi build fail?

**condition: succeededOrFailed()** cho phép xuất XML ngay cả khi Maven tests fail. Điều này giúp reviewer xem test nào lỗi. Nó **không** biến pipeline đỏ thành xanh; task cần bảo toàn failure status và artifacts chỉ publish khi các gates đạt.

### 8.4. Bước kiểm tra JAR

CopyFiles không phải quality gate đủ mạnh nếu không tìm thấy file. Với Java project thực tế, thêm bước sau Maven verify và trước CopyFiles:

~~~yaml
  - bash: |
      set -euo pipefail
      test "$(find target -maxdepth 1 -type f -name '*.jar' | wc -l)" -eq 1
      test -s "$(find target -maxdepth 1 -type f -name '*.jar' | head -n 1)"
      sha256sum target/*.jar
    displayName: 'Validate artifact count and checksum'
    condition: succeeded()
~~~

**Lưu ý:** Nếu nhiều module hoặc có **sources.jar, javadoc.jar**, phải điều chỉnh selector chọn đúng deployable JAR. Checksum cho artifact có thể ghi trong log/build evidence nhưng không được nhầm với digital signature.

## 9. Maven@4: task sẵn có hay Maven Wrapper?

Azure Pipelines có task **Maven@4** để gọi Maven, tích hợp JDK selection và publish JUnit test results. Nó hữu ích khi tổ chức muốn thống nhất build theo task version; Maven Wrapper hữu ích khi dự án muốn giữ Maven distribution version cùng repository.

### 9.1. Task Maven@4 cơ bản

Với Maven đã có trên agent và **pom.xml** ở thư mục gốc:

~~~yaml
steps:
  - task: Maven@4
    displayName: 'Maven clean verify'
    inputs:
      mavenPOMFile: 'pom.xml'
      goals: 'clean verify'
      options: '-B -ntp'
      publishJUnitResults: true
      testResultsFiles: '**/surefire-reports/TEST-*.xml'
      javaHomeOption: 'JDKVersion'
      jdkVersionOption: '1.21'
      jdkArchitectureOption: 'x64'
      mavenVersionOption: 'Default'
~~~

Đây là **phương án thay thế** cho bước Bash chạy Maven Wrapper và PublishTestResults trong mục 8, không phải phần chèn nguyên vào pipeline để chạy Maven hai lần. Hãy kiểm tra task schema/agent Java version trên Azure DevOps đang sử dụng.

### 9.2. So sánh

| Tiêu chí | Bash + Maven Wrapper | Maven@4 task |
|---|---|---|
| Maven version | Pin trong wrapper properties | Chọn bản đã cài trên agent hoặc cấu hình custom |
| Lệnh thực thi | Rõ toàn bộ command line | Dùng task inputs |
| Publish test XML | PublishTestResults@2 riêng | Có hỗ trợ tích hợp |
| Portability | Chạy giống local/CI khi wrapper đáng tin | Gắn với Azure Pipelines |
| Kiểm soát toolchain | JDK task + wrapper | JDK/Maven task inputs |
| Cập nhật Maven | PR thay wrapper version/checksum | Agent/task hoặc custom install |
| Security | Wrapper/script là executable code cần review | Task và agent version cũng cần review |

Không chọn Maven@4 chỉ vì “không cần kiểm tra POM”. Cả hai đều chạy mã từ build plugins/dependencies; trust boundary của source và credentials vẫn quan trọng.

### 9.3. Không chạy test hai lần ngoài ý muốn

Nếu dùng Maven@4 **goals=clean verify** rồi lại chạy **./mvnw verify**, tests bị chạy lại, artifacts có thể bị thay đổi và logs dễ nhầm lẫn. Thiết kế một **build authority** rõ cho mỗi job. Nếu muốn tách stages cho integration tests hoặc security scans, phải xác định cách chia workload và quyền truy cập artifacts.

## 10. Pipeline YAML Gradle: Gradle Wrapper + Java 21

Đối với repository có **gradlew**, **gradle/wrapper/**, **build.gradle(.kts)** và plugin Spring Boot phù hợp, một pipeline dùng Gradle Wrapper:

~~~yaml
# azure-pipelines-gradle.yml
trigger:
  branches:
    include:
      - main
      - develop

pool:
  vmImage: 'ubuntu-latest'

variables:
  GRADLE_USER_HOME: '$(Pipeline.Workspace)/.gradle'

steps:
  - checkout: self
    clean: true
    persistCredentials: false

  - task: JavaToolInstaller@0
    displayName: 'Select Java 21'
    inputs:
      versionSpec: '21'
      jdkArchitectureOption: 'x64'
      jdkSourceOption: 'PreInstalled'

  - task: Cache@2
    displayName: 'Cache Gradle files'
    inputs:
      key: 'gradle | "$(Agent.OS)" | **/gradle-wrapper.properties'
      restoreKeys: |
        gradle | "$(Agent.OS)"
      path: '$(GRADLE_USER_HOME)'

  - bash: |
      set -euo pipefail
      java -version
      bash ./gradlew --version
      bash ./gradlew --no-daemon clean build
    displayName: 'Compile, test, package with Gradle'

  - task: PublishTestResults@2
    displayName: 'Publish Gradle JUnit reports'
    condition: succeededOrFailed()
    inputs:
      testResultsFormat: 'JUnit'
      testResultsFiles: '**/build/test-results/test/TEST-*.xml'
      searchFolder: '$(System.DefaultWorkingDirectory)'
      failTaskOnFailedTests: true
      failTaskOnMissingResultsFile: true

  - bash: |
      set -euo pipefail
      mkdir -p "$(Build.ArtifactStagingDirectory)/app"
      find build/libs -maxdepth 1 -type f \
        -name '*.jar' ! -name '*-plain.jar' \
        ! -name '*-sources.jar' ! -name '*-javadoc.jar' \
        -exec cp {} "$(Build.ArtifactStagingDirectory)/app/" \;
      test "$(find "$(Build.ArtifactStagingDirectory)/app" \
        -type f -name '*.jar' | wc -l)" -eq 1
      sha256sum "$(Build.ArtifactStagingDirectory)"/app/*.jar
    displayName: 'Stage a single deployable JAR'
    condition: succeeded()

  - task: PublishPipelineArtifact@1
    displayName: 'Publish Gradle JAR'
    condition: succeeded()
    inputs:
      targetPath: '$(Build.ArtifactStagingDirectory)/app'
      artifact: 'orders-api-gradle'
      publishLocation: 'pipeline'
~~~

### 10.1. Điều kiện và điểm cần sửa

- Gradle Wrapper có script và distribution version đúng, **bash ./gradlew** hoạt động trên Ubuntu.
- Plugin **java** và **Spring Boot** được định nghĩa trong build.gradle(.kts) tùy loại ứng dụng.
- Task **build** của project thực sự kiểm thử và đóng gói JAR. Với Spring Boot, kiểm tra xem **bootJar** có nằm trong task graph và tạo deployable JAR không.
- Java plugin thường ghi JUnit XML trong **build/test-results/test/**; custom test tasks dùng đường dẫn khác.
- Filter loại **-plain.jar** theo convention Spring Boot có thể không phù hợp mọi project; điều chỉnh khi biết chính xác artifact name.
- Với multi-module, artifact có thể nằm ở **services/orders-api/build/libs/** thay vì root build/libs.
- Gradle user-home cache không thay thế compile/build cache hay configuration cache; cần version/permission policy riêng.

### 10.2. Tại sao dùng Wrapper?

Wrapper giải quyết khác biệt Gradle versions giữa developers và agent. Tuy nhiên **gradle-wrapper.jar**, **distributionUrl** và checksum phải được kiểm tra, vì wrapper code hoặc distribution source có thể bị thay bởi PR độc hại. Pinning version không thay dependency integrity.

### 10.3. Gradle@3/@4 task

Azure Pipelines cũng có các phiên bản **Gradle task** hỗ trợ Gradle wrapper, JDK và test reporting. Chỉ chọn task version đang được tổ chức hỗ trợ; kiểm tra inputs của version cụ thể thay vì giả định mọi version có cùng **gradleWrapperFile, tasks, publishJUnitResults, testResultsFiles**. Dùng **Gradle Wrapper bằng Bash** giúp ví dụ trên tự giải thích rõ command nhưng không làm nó tự động an toàn hơn.

## 11. Trigger: push CI, Pull Request và branch policies

### 11.1. CI trigger

Một YAML trigger:

~~~yaml
trigger:
  branches:
    include:
      - main
      - develop
  paths:
    exclude:
      - docs/**
~~~

Pipeline chạy trên những pushes phù hợp theo provider và pipeline settings. Một path filter loại docs có thể tiết kiệm build minutes nhưng rủi ro nếu docs chứa API spec, generated code hoặc build instructions ảnh hưởng artifact. Chọn filter theo threat model.

### 11.2. PR trigger khác nhau theo source provider

**Điểm quan trọng:** YAML **pr:** triggers thường áp dụng cho GitHub và Bitbucket Cloud. Với **Azure Repos Git**, cấu hình **Branch Policies → Build Validation** trên target branch để pipeline kiểm chứng PR; đừng xem pr YAML là một thay thế chính sách này.

| Repo | PR build validation thường cấu hình ở đâu? |
|---|---|
| **Azure Repos Git** | Branch Policies → Build Validation |
| **GitHub** | Azure Pipelines YAML pr trigger và GitHub branch protection/checks theo integration |
| **Bitbucket Cloud** | YAML pr trigger và provider permissions/checks theo hỗ trợ |

Pipeline chạy thành công trên một feature branch không đủ bảo đảm PR vào main đã bị chặn merge. Phải thiết lập required build validation/status checks theo nguồn repo.

### 11.3. Build validation branch policy cho Azure Repos

Một thiết lập có thể:

1. Mở **Repos → Branches**.
2. Tại **main**, chọn **Branch policies**.
3. Thêm **Build validation** và chỉ đúng pipeline.
4. Chọn policy **Required**, nếu workflow yêu cầu.
5. Chọn expiration/revalidation policy phù hợp để tránh merge dựa trên build cũ.
6. Thử một PR có failing test; xác minh merge bị chặn.
7. Thử sửa YAML build rồi tạo PR; xác minh required validation vẫn áp dụng.
8. Không dùng bypass permissions tùy tiện; audit những người có quyền bypass.

**Branch protection + code review + build validation** hỗ trợ nhau; một kiểm tra không thay mọi kiểm tra còn lại.

### 11.4. PR từ fork là untrusted source

Khi pipeline chạy source của PR từ fork, YAML, shell scripts, Maven plugins, Gradle tasks và test code đều có thể do người chưa tin cậy sửa. Không cấp production service connections, secret variables, PAT mạnh hoặc truy cập self-hosted agent có network privilege cho các runs này.

Đừng chạy một job “safe” chỉ vì job tên **UnitTest**: build step cũng có thể chạy lệnh shell/executables được commit trong PR.

### 11.5. Manual, schedule và path triggers

Có thể tổ chức:

- **CI push** cho main/develop.
- **PR validation** cho required branches.
- **Scheduled dependency scan** để phát hiện CVE mới khi code không thay đổi.
- **Manual approved build** để tạo release candidates.
- **Tag-based release** theo governance.

Không tạo cùng lúc nhiều rules khiến một commit chạy 3 pipelines giống nhau không cần thiết; đo throughput/chi phí rồi tinh chỉnh.

## 12. Variables, parameters và secrets

### 12.1. Một số nhóm biến

| Loại | Ví dụ | An toàn để commit? |
|---|---|---|
| YAML variable thường | JDK_VERSION=21, MAVEN_CACHE_FOLDER | Có nếu không nhạy cảm |
| Predefined variable | Build.SourceVersion, Build.BuildId, Agent.OS | Được Azure Pipelines cung cấp |
| Runtime variable | Build.SourceBranch | Dùng theo docs, không tin là approved deploy |
| Template parameter | Chọn JDK/goal khi compile YAML | Cần review đầu vào |
| Secret pipeline variable | Access token / credential cần thiết | Không commit value |
| Variable group | Tập config/secret có quyền riêng | Bảo vệ permissions/approvals |
| Key Vault-linked variable group | Secret data được truy xuất từ Key Vault theo integration | Cần Azure connection/Key Vault permissions |
| Service connection | Ủy quyền truy cập Azure/feed/external service | Không làm lộ secret vào script |

### 12.2. Macro syntax và runtime

~~~yaml
variables:
  JAVA_TARGET: '21'

steps:
  - bash: |
      echo "Build ID: $(Build.BuildId)"
      echo "Commit SHA: $(Build.SourceVersion)"
      echo "Java target: $(JAVA_TARGET)"
    displayName: 'Non-secret build metadata'
~~~

Các **$(...)** ở đây là Azure Pipelines variable expansion. Bên trong Bash nếu macro không được khai báo, một cú pháp **$(unknown)** không được thay có thể trở thành Bash command substitution không mong muốn. Tránh dựng shell commands bằng dữ liệu user không tin cậy; truyền các giá trị đã validate qua **env:** và dùng quotes.

### 12.3. Secret variable qua env

Ví dụ **chỉ khi job thật sự cần token**:

~~~yaml
steps:
  - bash: |
      set -euo pipefail
      test -n "$PRIVATE_FEED_TOKEN"
      echo "Token available; value not displayed"
    env:
      PRIVATE_FEED_TOKEN: $(PRIVATE_FEED_TOKEN)
~~~

**PRIVATE_FEED_TOKEN** được tạo là secret variable qua Azure DevOps Library/secure source; YAML chỉ có **tên**, không chứa value. Với private Maven feeds, **MavenAuthenticate@0** và job identity thường phù hợp hơn truyền một PAT thủ công. Secret masking không bảo đảm mọi bản biến đổi/substring của secrets được che, nên **không in/echo token** hoặc đưa vào command-line arguments nếu có cách an toàn hơn.

### 12.4. Không dùng biến để quyết định authorization

**Build.SourceBranch** có thể giúp giới hạn steps, nhưng chỉ một condition string không thay **branch policies, approvals, environment checks, resource authorization, service-connection permissions**. Cấp quyền credential ở tài nguyên riêng và đảm bảo untrusted PR không thể tham chiếu nó.

## 13. Cache dependencies và tính lặp lại

### 13.1. Cache@2 thực chất cache gì?

Cache@2 khôi phục/lưu một thư mục giữa runs theo **cache key**. Nó có thể giúp giảm thời gian Maven/Gradle tải artifacts/metadata. Nhưng nó **không thay remote artifact repository**, không bảo đảm dependencies nguyên vẹn và không biến pipeline thành reproducible build.

~~~mermaid
flowchart LR
    START["New agent"] --> KEY["Evaluate cache key"]
    KEY --> CACHE{"Cache hit?"}
    CACHE -->|Yes| RESTORE["Restore Maven/Gradle dir"]
    CACHE -->|No| FETCH["Download verified dependencies"]
    RESTORE --> BUILD["Build + tests"]
    FETCH --> BUILD
    BUILD --> SAVE["Cache post-job save policy"]
~~~

### 13.2. Key strategy

Một cache key ví dụ:

~~~yaml
- task: Cache@2
  inputs:
    key: 'maven | "$(Agent.OS)" | **/pom.xml'
    restoreKeys: |
      maven | "$(Agent.OS)"
    path: '$(Pipeline.Workspace)/.m2/repository'
~~~

**Cache keys** có thể dùng tệp hoặc glob; khi POM đổi, cache key có thể đổi. Nếu dùng Maven toolchain/Java version khác nhau, cân nhắc thêm version hoặc wrapper metadata vào key. Với Gradle, ít nhất xem xét **gradle-wrapper.properties**, lockfiles và OS.

### 13.3. Cache là bất biến theo key

Azure Pipelines caches được thiết kế immutable theo key; một khi cache được lưu, run sau cùng key không tự sửa cache đó. **restoreKeys** có thể hồi phục cache có phạm vi rộng hơn, nhưng dependencies mới vẫn có thể cần tải từ repository. Vì thế cần chiến lược key versioning và không cache output build để giả định source mới đã compile.

### 13.4. Nguy cơ poisoning và secrets

- Không cache **Maven settings.xml** nếu file đó chứa credentials.
- Không cache token files, .npmrc/gradle.properties có passwords hoặc Azure CLI caches.
- Không share cache trust boundary giữa untrusted PR và privileged release job nếu policy không cho phép.
- Dependency caches có thể chứa files được tải từ mirror bị xâm nhập; verify checksums/signatures khi có thể.
- Đừng cache **target/** hoặc **build/libs/** rồi publish artifact mà không build/test lại từ source.
- Cập nhật keys/clear cache khi nghi supply chain compromise.

### 13.5. Warm cache không phải kết quả bảo mật

Một pipeline cache hit có thể build nhanh, nhưng nếu artifact nằm trong repository bị thay, compromised dependency đã được cache từ trước, hoặc plugin có mã độc, cache không tạo ra trust. **Reproducible build** cần pin versions, verify sources, chạy tests/checks và lưu provenance.

## 14. Build artifacts, naming và traceability

### 14.1. Ba thứ thường bị nhầm

- **Workspace files:** JAR trong **target/** hoặc **build/libs/** trên agent.
- **Pipeline Artifact:** files được upload/lưu theo pipeline run để tải về ở giai đoạn khác.
- **Container image:** image có layers/digest trong registry; không tự sinh chỉ bằng publish JAR.

Đừng coi một file trong **$(Build.ArtifactStagingDirectory)** đã trở thành artifact bền vững nếu chưa chạy Publish task.

### 14.2. Artifact metadata cần lưu

| Metadata | Lý do |
|---|---|
| Repo/project/pipeline ID | Nguồn xuất xứ |
| **Build.SourceVersion** | Git commit chính xác |
| **Build.BuildId** | Run ID |
| Branch/PR/merge commit | Ngữ cảnh xác thực |
| JDK/Maven/Gradle versions | Toolchain provenance |
| Dependency lock/SBOM | Thành phần phần mềm |
| Test/coverage results | Quality evidence |
| SHA-256 digest | Kiểm tra nội dung artifact |
| Agent image/runtime | Reproducibility context |
| Timestamp UTC | Điều tra/audit |
| Approval/environment later | CD trace |

### 14.3. Publish và download

Publish từ build run:

~~~yaml
- task: PublishPipelineArtifact@1
  inputs:
    targetPath: '$(Build.ArtifactStagingDirectory)/app'
    artifact: 'orders-api-java'
~~~

Một job/stage downstream trong **cùng pipeline** có thể dùng:

~~~yaml
- task: DownloadPipelineArtifact@2
  inputs:
    artifactName: 'orders-api-java'
    targetPath: '$(Pipeline.Workspace)/downloaded'
~~~

Để tải artifacts từ **một run khác** hoặc pipeline khác, cần đặt source/run identifiers theo task version. Không mặc định DownloadPipelineArtifact từ current run có thể lấy một artifact chưa được publish. **CD phải chọn approved run** chứ không tự tải artifact “latest” từ nhánh bất kỳ.

### 14.4. Artifact retention

Artifact có thể bị xóa theo retention policies, storage quotas hoặc project settings. “Build once, deploy many” không có nghĩa artifact được lưu vĩnh viễn. Với release candidates được approve, đặt retention/preservation/registry policy phù hợp và xác minh khả năng phục hồi nếu artifact hết hạn.

### 14.5. Checksum khác signature

**SHA-256** giúp phát hiện binary bị thay đổi so với digest đã lưu. Tuy nhiên nếu attacker có thể đổi **cả artifact lẫn checksum**, hash alone không xác thực publisher. Với supply chain assurance cao hơn, dùng **cryptographic signing/attestation** và provenance được bảo vệ, policy verify ở lúc deploy.

## 15. Kiểm thử: unit, integration và reports

### 15.1. Test pyramid cho Java

~~~mermaid
flowchart TB
    FAST["Many fast unit tests<br/>JUnit 5 / Mockito"]
    INTEG["Fewer integration tests<br/>Testcontainers / emulator"]
    E2E["Few end-to-end<br/>staging smoke tests"]
    FAST --> INTEG --> E2E
~~~

**Unit tests:** logic không cần Azure thật. **Integration tests:** DB/test container, HTTP contract hoặc một Azure lab resource có lifecycle rõ. **E2E tests:** service staging hoặc approved environment. Không dùng production database credentials trong PR.

### 15.2. Surefire và Failsafe

Maven convention:

- **maven-surefire-plugin** chạy unit tests trong test phase, thường tạo **target/surefire-reports/TEST-*.xml**.
- **maven-failsafe-plugin** có thể chạy integration tests trong integration-test/verify, thường tạo **target/failsafe-reports/TEST-*.xml** khi được cấu hình.
- Class naming conventions như **\*Test** và **\*IT** phụ thuộc plugin configuration.
- **mvn verify** không chạy integration tests nếu POM chưa gắn Failsafe goals.
- Nếu dùng Testcontainers, agent phải có container runtime/permissions phù hợp; một Microsoft-hosted Linux image thường hỗ trợ Docker nhưng phải kiểm tra networking/quotas của môi trường hiện hành.

### 15.3. Publish cả unit và integration reports

Nếu có cả Surefire và Failsafe:

~~~yaml
- task: PublishTestResults@2
  condition: succeededOrFailed()
  inputs:
    testResultsFormat: 'JUnit'
    testResultsFiles: |
      **/surefire-reports/TEST-*.xml
      **/failsafe-reports/TEST-*.xml
    searchFolder: '$(System.DefaultWorkingDirectory)'
    failTaskOnFailedTests: true
    failTaskOnMissingResultsFile: true
~~~

Nhớ task reports **không thay việc build/test fail** khi tests hỏng. Không dùng **continueOnError: true** trên build task hoặc **-Dmaven.test.skip=true** rồi coi pipeline xanh là chất lượng đạt.

### 15.4. Flaky tests

Một test lúc đỏ lúc xanh làm mất niềm tin vào PR validation:

- Loại yếu tố thời gian/ngẫu nhiên không kiểm soát.
- Dùng fake clock, deterministic IDs và isolated test data.
- Giảm phụ thuộc network bên ngoài cho unit tests.
- Khi bắt buộc integration với Azure lab, dùng env riêng và stable fixtures.
- Có retry test rất có điều kiện/triage nhưng **không che failure chính**.
- Quarantine và owner/timebound fix cho flaky tests, không vô hiệu hóa vô hạn.

### 15.5. Test data không chứa secrets

Không in JWT/API keys, customer PII hoặc database passwords vào test logs, HTML reports, screenshots và artifacts. Giả lập dữ liệu thông qua fixtures hoặc secret-supplied integration environment có quyền hạn tối thiểu.

## 16. Code coverage, quality gates và static analysis

### 16.1. Coverage không phải bảo đảm chất lượng tuyệt đối

**Line/branch coverage** đo phần code hoặc nhánh được thực thi khi chạy test; không chứng minh assertions đúng, integration hoạt động, mã an toàn hay không có race conditions. Nhưng coverage trends có thể cảnh báo khi nhóm bỏ quên kiểm thử.

| Gate | Công cụ Java phổ biến | Kết quả cần quan sát |
|---|---|---|
| Unit/integration tests | JUnit 5, Maven Surefire/Failsafe, Gradle Test | Pass/fail, JUnit XML |
| Coverage | JaCoCo | Line/branch coverage và threshold |
| Lint/static | Checkstyle, PMD, SpotBugs, Error Prone | Violations theo severity |
| Code quality | SonarQube/SonarCloud nếu được tổ chức chọn | Quality gate và findings |
| Dependency vulnerabilities | SCA scanner được duyệt | CVE/severity/fix evidence |
| Secret scanning | Repo scanner và pipeline controls | Token/password accidentally committed |
| Licensing | SBOM/SCA/license policy | Libraries không hợp policy |

Không cần bật tất cả công cụ cùng ngày; lựa chọn phải dựa trên rủi ro, false positives, ownership và latency budget.

### 16.2. JaCoCo plugin trong Maven

Mẫu cấu hình **POM fragment**, pin plugin version phù hợp trước khi build:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.jacoco</groupId>
      <artifactId>jacoco-maven-plugin</artifactId>
      <version>REPLACE_WITH_APPROVED_VERSION</version>
      <executions>
        <execution>
          <goals><goal>prepare-agent</goal></goals>
        </execution>
        <execution>
          <id>generate-report</id>
          <phase>verify</phase>
          <goals><goal>report</goal></goals>
        </execution>
        <execution>
          <id>quality-check</id>
          <phase>verify</phase>
          <goals><goal>check</goal></goals>
        </execution>
      </executions>
      <!-- Khai báo rules/limits cụ thể nếu muốn fail dưới ngưỡng. -->
    </plugin>
  </plugins>
</build>
~~~

**REPLACE_WITH_APPROVED_VERSION** là placeholder; không thể chạy nguyên trạng. Check goal không có nghĩa mặc định sẽ fail ở ngưỡng 80% nếu POM chưa đặt rules. Maven **verify** chỉ thực thi những plugins/goals mà dự án đã cấu hình.

### 16.3. Publish coverage report trong Azure Pipelines

Sau khi JaCoCo đã tạo XML, có thể thêm:

~~~yaml
- task: PublishCodeCoverageResults@2
  displayName: 'Publish JaCoCo coverage'
  condition: succeededOrFailed()
  inputs:
    summaryFileLocation: '$(System.DefaultWorkingDirectory)/target/site/jacoco/jacoco.xml'
    failIfCoverageEmpty: true
~~~

**Publish** không tự là **quality gate**; phải dùng **JaCoCo check**, Sonar quality gate hoặc chính sách khác có threshold và failure behavior. Multi-module reports có paths khác và có thể cần aggregate. Kiểm tra syntax task version/agent hiện có.

### 16.4. Khi nào fail build?

Một chính sách minh họa:

- Compile/test fail → **CI fail**.
- Missing required test reports → **CI fail**, không coi “0 tests” là pass.
- Critical dependency vulnerability đã xác minh → **fail release** và triage.
- Secret scan phát hiện credential thật → **fail** và kích hoạt incident process.
- Coverage giảm vượt mức được duyệt → fail hoặc có waiver ngắn hạn.
- Minor lint mới xuất hiện → có thể warn rồi nâng thành fail theo kế hoạch.

Không dùng **continueOnError: true** để làm một kiểm tra bắt buộc trông như thành công. Ngoại lệ phải có owner, thời hạn và risk approval.

## 17. Private Maven feeds và Azure Artifacts

Một project Java có thể dùng library nội bộ từ **Azure Artifacts Maven feed**:

~~~xml
<dependency>
  <groupId>com.company.shared</groupId>
  <artifactId>common-auth</artifactId>
  <version>2.1.0</version>
</dependency>
~~~

Lỗi **401/403** khi resolve dependency thường liên quan feed authentication/permission, **không phải** Key Vault hoặc thiếu role Azure Contributor.

### 17.1. MavenAuthenticate@0

Khi pipeline identity có quyền tới Azure Artifacts feed đã tồn tại:

~~~yaml
steps:
  - task: MavenAuthenticate@0
    displayName: 'Authenticate Maven feed'
    inputs:
      artifactsFeeds: 'team-maven-feed'

  - bash: |
      set -euo pipefail
      bash ./mvnw -B -ntp clean verify
    displayName: 'Build from approved feeds'
~~~

Task hỗ trợ auth vào feed theo cấu hình; **pom.xml hoặc settings.xml** vẫn phải định nghĩa repository URL và server ID đúng. Không tự giả định task tạo luôn dependency declarations. Đừng cache file settings chứa credentials vào Maven cache dùng chung.

### 17.2. Quyền job identity và feed

Feed có thể cần cấp role reader cho **Project Build Service** hoặc **Project Collection Build Service** identity tùy project/collection authorization scope. Nếu build fail:

1. Xác nhận artifact groupId/artifactId/version tồn tại.
2. Kiểm tra feed name, repository URL và server ID.
3. Kiểm tra MavenAuthenticate chạy trước Maven.
4. Kiểm tra pipeline identity có feed read permission.
5. Kiểm tra cross-project feed authorization nếu có.
6. Kiểm tra egress network tới feed.
7. Không đưa PAT dài hạn vào POM hoặc logs để “sửa nhanh”.

### 17.3. Release dependencies vs SNAPSHOT

**SNAPSHOT** có thể thay đổi bytes dù cùng version string. Với release artifact, ưu tiên immutable versions, approved BOMs và repository controls. Nếu build dùng snapshot, không tuyên bố reproducibility chỉ từ commit của app.

### 17.4. Gradle private repositories

Gradle cũng có thể dùng Maven repository với credentials lấy từ **environment variables** hoặc credential providers. Không commit passwords vào **build.gradle**, **gradle.properties**, Dockerfile hoặc CI logs. Kiểm tra plugin repositories, artifact repository URLs và dependency verification.

## 18. Azure credentials, service connections và secrets

### 18.1. Build Java thuần không cần subscription credentials

Một job compile/test/package từ public dependencies **không cần** Azure Resource Manager service connection. Càng ít credentials trong CI, blast radius của PR độc hại càng nhỏ.

### 18.2. Chỉ cấp quyền khi cần hành động thêm

| Hoạt động | Quyền thường cần |
|---|---|
| Build Maven/Gradle public project | Repo checkout và agent; không cần Azure subscription |
| Đọc private Maven feed | Azure Artifacts feed reader theo project/identity |
| Push Docker image lên ACR | Registry push permission/connection phù hợp |
| Deploy App Service hoặc AKS | Azure service connection/identity và environment approvals |
| Lấy secret cho approved integration test | Key Vault get permission trong lab theo scope |
| Ký artifact | Signer identity/key permission theo kiến trúc ký |

**Không** cho PR validation được dùng service connection production chỉ vì pipeline còn có bước deploy ở stage khác.

### 18.3. Workload identity federation

Azure Resource Manager service connections có thể sử dụng **workload identity federation** để thay client secret sống lâu, theo khả năng hỗ trợ. Phải:

- Giới hạn resource/subscription scope.
- Giới hạn pipelines được dùng service connection.
- Bật approval/checks hoặc resource authorization khi cần.
- Không bật “Grant access permission to all pipelines” vô cớ.
- Không để YAML từ untrusted PR tự kích hoạt privileged publish job.
- Theo dõi service connection và federated identity credential changes.

### 18.4. Secret variables và variable groups

Pipeline secret variables, Key Vault-linked variable groups hoặc secure files được dùng **chỉ khi nhiệm vụ thực sự đòi hỏi**. Nếu dùng secret trong Bash task:

~~~yaml
steps:
  - bash: |
      set -euo pipefail
      test -n "$LAB_TOKEN"
      echo "Lab token is present (value omitted)"
    env:
      LAB_TOKEN: $(LAB_TOKEN)
~~~

**LAB_TOKEN** là secret variable được tạo qua secure source, không phải literal hard-coded. **Không echo value, không log Authorization header, không ghi vào artifact**. Masking có giới hạn với substrings/biến đổi của secret; build script độc hại vẫn có thể gửi value ra ngoài nếu job đã nhận nó.

### 18.5. PR code là code chưa tin cậy

Một PR có thể sửa **pom.xml**, Gradle scripts, wrapper, pipeline YAML hoặc test code để chạy lệnh tùy ý trên agent. Một job tên “UnitTests” không tự trở nên safe. Tách:

1. **Untrusted PR verification**: không có production secret/service connections.
2. **Trusted post-merge build**: có branch policy, tests và quyền publish giới hạn.
3. **Approved CD**: service connection/approvals và deploy environments riêng.

Không share self-hosted agent chứa long-lived credentials giữa untrusted và privileged runs.

## 19. Các điểm tấn công trong software supply chain

~~~mermaid
flowchart TD
    SRC["Repo + PR + pipeline YAML"] --> AGENT["Agent OS/JDK + build wrapper"]
    AGENT --> DEPS["Maven/Gradle plugins + dependencies"]
    DEPS --> TEST["Compile/test/quality gates"]
    TEST --> ART["JAR artifact + SBOM + provenance"]
    ART --> CD["Trusted release/deployment"]
    REPO["Private/public repositories"] --> DEPS
    AUTH["Scoped job token/credentials"] -. "only approved jobs" .-> DEPS
~~~

### 19.1. Nguồn thực thi phải kiểm soát

- Maven/Gradle wrapper scripts và distribution URL.
- POM plugins, build.gradle tasks và test setup code.
- Maven repositories/plugin repositories, public mirrors.
- JDK/tool installers, agent image updates.
- Third-party Azure Pipelines extensions/tasks.
- Dockerfile/base image nếu quy trình sau này đóng container.
- Build scripts tải binary/installers từ mạng.
- Secret variables/service connections.
- Artifact publishing/storage path.

### 19.2. Dependency pinning

Maven:

- Dùng fixed versions/BOM và pin Maven plugins.
- Kiểm tra **mvn dependency:tree**, effective POM.
- Giảm SNAPSHOT/version ranges ở release path.
- Verify Maven Wrapper distribution checksum khi khả dụng.
- Hạn download từ repositories chưa được phê duyệt.

Gradle:

- Dùng **Gradle Wrapper** được pin version/checksum.
- Cân nhắc dependency locking và dependency verification.
- Kiểm tra plugin repositories, không tin version catalog tự khóa transitive versions nếu chưa cấu hình.
- Chạy tests và SCA trên resolved dependency graph.

### 19.3. Tránh curl pipe shell

Anti-pattern:

~~~bash
# KHÔNG chạy ví dụ này:
curl -fsSL https://unknown.example.invalid/install.sh | bash
~~~

Thay bằng binary/installer được duyệt, version pin và checksum/signature verification hoặc maintained Azure task. Không tắt TLS validation để tải dependencies.

### 19.4. Self-hosted agent isolation

- Tốt nhất dùng ephemeral workers cho untrusted source.
- Không mount production secrets, host Docker socket và shared home tùy tiện.
- Tách pools/network của PR và release jobs.
- Patch OS/JDK/agent và kiểm soát outbound network.
- Dọn workspace, credential caches và artifacts sau privileged runs.
- Theo dõi process/network abnormal behavior nếu có khả năng.
- Giữ logs phục vụ incident không chứa secrets.

Microsoft-hosted agents giảm bớt vận hành host, nhưng không thay repo permissions/secret isolation.

## 20. SBOM, provenance, checksum và signing

### 20.1. SBOM

**Software Bill of Materials (SBOM)** liệt kê package/dependency versions, giúp tìm thư viện bị ảnh hưởng khi có CVE. Các định dạng phổ biến: **CycloneDX** và **SPDX**. Một Java Maven project có thể dùng **CycloneDX Maven Plugin** được pin/duyệt để tạo SBOM:

~~~bash
# Yêu cầu plugin đã được pin và cấu hình trong pom.xml.
bash ./mvnw -B -ntp cyclonedx:makeAggregateBom
~~~

Output paths/goal names thay đổi theo plugin version và multi-module configuration. Publish SBOM cạnh JAR theo artifact policy. SBOM **không chứng minh dependency không có mã độc**.

### 20.2. Provenance metadata minh họa

~~~json
{
  "repository": "orders-api",
  "commit": "example-git-sha",
  "runId": "1428",
  "jdk": "21",
  "buildTool": "Maven Wrapper",
  "artifact": "orders-api.jar",
  "sha256": "example-checksum",
  "tests": "passed",
  "timeUtc": "2026-11-20T09:00:00Z"
}
~~~

Đây chỉ là metadata minh họa, **chưa phải attestation cryptographically signed**. Đừng gọi một JSON tự tạo là provenance trusted nếu attacker có thể thay cùng lúc metadata và binary.

### 20.3. Hash, signature và attestations

| Cơ chế | Giá trị | Giới hạn |
|---|---|---|
| SHA-256 | Kiểm tra binary có bị thay so với digest không | Không xác minh ai tạo |
| SBOM | Liệt kê thành phần/phụ thuộc | Không tự chứng minh an toàn |
| Digital signature | Xác minh signer và bytes khi trust chain đúng | Không chứng minh code không có bug |
| Build provenance | Nguồn, toolchain, builder, run metadata | Cần builder/attestation tin cậy |
| SLSA-style controls | Giảm nguy cơ source/build tampering | Không thay runtime security |

Để “build once, deploy many”, downstream CD nên tải **approved artifact từ run cụ thể**, kiểm tra digest/signature khi policy yêu cầu, thay vì build lại từ branch HEAD mới hoặc tải “latest” một cách không kiểm soát.

### 20.4. Một supply-chain attack điển hình

Attacker sửa POM thêm plugin chạy trong validate phase, thu thập CI secret variable và gửi ra ngoài. Unit tests vẫn có thể xanh. Controls:

1. Không đưa secrets vào PR job.
2. Review POM/wrapper/pipeline YAML như **executable code**.
3. Bảo vệ service connections và variable groups.
4. Giới hạn egress/agent privileges.
5. Cấp feed/artifact publish permissions tối thiểu.
6. Dùng scanner, trusted repositories và provenance.
7. Require code owners/PR validation trước trusted release.
8. Có incident response khi build logs/credentials bị lộ.

## 21. Multi-stage pipeline và ranh giới giữa jobs

Một pipeline phức tạp có thể chia **Build → VerifyArtifact → Release**. Ví dụ chỉ dùng hai stages build và kiểm tra artifact, không triển khai:

~~~yaml
trigger:
  branches:
    include:
      - main

pool:
  vmImage: 'ubuntu-latest'

stages:
  - stage: Build
    jobs:
      - job: BuildJava
        steps:
          - checkout: self
          - task: JavaToolInstaller@0
            inputs:
              versionSpec: '21'
              jdkArchitectureOption: 'x64'
              jdkSourceOption: 'PreInstalled'
          - bash: |
              set -euo pipefail
              bash ./mvnw -B -ntp clean verify
            displayName: 'Build and test'
          - task: PublishTestResults@2
            condition: succeededOrFailed()
            inputs:
              testResultsFormat: 'JUnit'
              testResultsFiles: '**/surefire-reports/TEST-*.xml'
              failTaskOnFailedTests: true
          - task: CopyFiles@2
            inputs:
              SourceFolder: '$(Build.SourcesDirectory)/target'
              Contents: '*.jar'
              TargetFolder: '$(Build.ArtifactStagingDirectory)/app'
          - task: PublishPipelineArtifact@1
            inputs:
              targetPath: '$(Build.ArtifactStagingDirectory)/app'
              artifact: 'orders-api-java'

  - stage: VerifyArtifact
    dependsOn: Build
    condition: succeeded()
    jobs:
      - job: Inspect
        steps:
          - checkout: none
          - task: DownloadPipelineArtifact@2
            inputs:
              artifactName: 'orders-api-java'
              targetPath: '$(Pipeline.Workspace)/app'
          - bash: |
              set -euo pipefail
              test "$(find "$(Pipeline.Workspace)/app" \
                -type f -name '*.jar' | wc -l)" -eq 1
              sha256sum "$(Pipeline.Workspace)"/app/*.jar
            displayName: 'Verify downloaded JAR'
~~~

### 21.1. Những điều quan trọng

- **Jobs có thể chạy trên agents khác nhau**, không có thư mục target của job trước.
- Dùng **PublishPipelineArtifact/DownloadPipelineArtifact** để trao đổi output qua stages.
- **dependsOn + condition: succeeded()** giúp chặn stage sau khi build fail.
- **Stage không tự bảo vệ credentials**: cần resource authorization, branch policies và approvals.
- Các bước Copy/Publish trong production nên có explicit conditions/validation để không phát hành artifact rỗng.
- Mỗi stage/job thêm overhead và có thể tăng agent minutes.
- Build run từ feature branch vẫn có thể tạo artifact nhưng **không tự là release được phê duyệt**.

### 21.2. Job dependencies không thay release policy

Nếu chạy manual build trên branch không tin cậy, downstream deploy phải kiểm tra source run, branch, commit, approvals, tests và provenance. Không dùng “latest artifact” không kiểm soát làm nguồn phát hành.

## 22. Multi-module Java và monorepo

### 22.1. Maven reactor

Một dự án:

~~~text
commerce/
├── pom.xml
├── common-model/
│   └── pom.xml
├── common-security/
│   └── pom.xml
├── orders-api/
│   ├── pom.xml
│   └── target/orders-api-1.0.jar
└── azure-pipelines.yml
~~~

**mvn clean verify** ở root xử lý reactor modules theo POM. Deployable JAR nằm trong **orders-api/target**, không nhất thiết có root **target/**.

~~~yaml
- task: CopyFiles@2
  inputs:
    SourceFolder: '$(Build.SourcesDirectory)/orders-api/target'
    Contents: 'orders-api-*.jar'
    TargetFolder: '$(Build.ArtifactStagingDirectory)/app'
    flattenFolders: true
~~~

Điều chỉnh selector để không vô tình copy **sources.jar**, **javadoc.jar** hoặc library modules. Có thể build một module và dependencies trong reactor:

~~~bash
bash ./mvnw -B -ntp -pl orders-api -am clean verify
~~~

**-pl** chọn module, **-am** build những module phụ thuộc trong reactor. Tuy nhiên một thay đổi ở **common-security** cần test đầy đủ; việc chỉ chạy unit tests trong orders-api có thể bỏ qua kiểm tra module dùng chung.

### 22.2. Gradle multi-project

Cấu trúc:

~~~text
settings.gradle.kts
build.gradle.kts
common-model/build.gradle.kts
orders-api/build.gradle.kts
~~~

Một task path theo Gradle multi-project:

~~~bash
bash ./gradlew --no-daemon :orders-api:build
~~~

JAR có thể nằm tại **orders-api/build/libs/**. Đảm bảo Gradle project/plugin/tasks đã được khai báo; Gradle không tự biết module nào là ứng dụng triển khai.

### 22.3. Path filters trong monorepo

~~~yaml
trigger:
  branches:
    include:
      - main
  paths:
    include:
      - services/orders-api/**
      - libraries/common/**
      - build-tools/**
      - azure-pipelines.yml
~~~

Những paths này chỉ là ví dụ. Nếu **pom.xml, settings.gradle.kts, version catalog, wrapper hoặc shared security code** nằm ngoài filter, một thay đổi có thể không kích hoạt build cần thiết. Với Azure Repos PR, còn cần **Build Validation branch policy path filter** tương ứng.

### 22.4. Matrix builds

Thư viện Java có thể cần verify với JDK 17 và JDK 21:

~~~yaml
# Fragment bên trong job, không đặt strategy dưới steps.
strategy:
  matrix:
    JDK17:
      JAVA_VERSION: '17'
    JDK21:
      JAVA_VERSION: '21'

steps:
  - task: JavaToolInstaller@0
    inputs:
      versionSpec: '$(JAVA_VERSION)'
      jdkArchitectureOption: 'x64'
      jdkSourceOption: 'PreInstalled'
  - bash: bash ./mvnw -B -ntp clean verify
~~~

Matrix làm tăng confidence với nhiều runtimes nhưng cũng tăng **parallel jobs, cache diversity và build minutes**. Với ứng dụng Java 21 duy nhất, không cần matrix rộng nếu không có compatibility requirement.

## 23. Phiên bản JAR và release candidate

### 23.1. Artifact identity gồm nhiều lớp

~~~text
Maven coordinates:
  groupId    com.example.orders
  artifactId orders-api
  version    1.8.0

Azure Pipelines:
  Build.BuildId        = 1428
  Build.SourceVersion  = abcdef123...
  Branch               = refs/heads/main

Artifact:
  orders-api-1.8.0.jar
  SHA256 <digest>
~~~

**Semantic version** của JAR khác **Build.BuildId** và Git commit hash. Với PR validation, **Build.SourceVersion** có thể là merge commit/context khác source HEAD trực tiếp; lưu chính xác giá trị do run báo.

### 23.2. Không tự sửa POM version thiếu kiểm soát

Nếu pipeline thay version trước build, đó là một input của artifact và phải được ghi vào provenance/release manifest. Ưu tiên committed version/release workflow đã review, không tự commit tăng version vào main từ PR job.

### 23.3. Phân biệt outputs

| Output | Dùng cho | Cần xác minh |
|---|---|---|
| Executable JAR | Spring Boot application | Main class, Java runtime, checksum |
| WAR | Java web/servlet runtime | Servlet container compatibility |
| Library JAR | Azure Artifacts Maven feed | Coordinates/immutable version |
| Container image | AKS/Container Apps | Base image, SBOM, scan, digest |
| Native binary | GraalVM-native project | Toolchain, architecture, tests |

Bài này tập trung build JAR. Docker build/ACR push là bước mở rộng, không tự xảy ra khi publish JAR.

### 23.4. Release manifest minh họa

~~~json
{
  "service": "orders-api",
  "artifact": "orders-api-1.8.0.jar",
  "sourceCommit": "abcdef123",
  "runId": "1428",
  "artifactSha256": "example-hash",
  "jdkVersion": "21",
  "tests": "PASSED",
  "qualityGate": "PASSED"
}
~~~

Đây là metadata mô phỏng. Một JSON không được ký/chứng thực không tự là trusted provenance.

## 24. Conditions, branch checks và quyền triển khai

### 24.1. Condition hạn theo nhánh

~~~yaml
- bash: |
    echo "Trusted main post-build metadata task"
  condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))
~~~

Điều kiện này giúp tránh bước không cần thiết trên feature branches, nhưng **không phải access-control boundary đủ mạnh** nếu PR có thể sửa YAML và dùng privileged service connections.

### 24.2. Các lớp bảo vệ

- **Condition:** logic YAML của một job/step.
- **Branch policy:** yêu cầu review/build validation trước merge.
- **Repository permissions:** ai được sửa YAML, code, tags và main.
- **Service connection authorization:** pipelines nào có thể dùng credential.
- **Environment approvals/checks:** gate trước deployment.
- **Azure RBAC:** identity có quyền gì trên Azure resources.
- **Feed permissions:** build identity có thể đọc/ghi packages nào.

Một pipeline xanh không tự vượt qua các lớp approval ở CD. Không dùng code từ untrusted PR để gọi service connections production.

### 24.3. Separation of duties

Developer tạo PR, reviewer/owners duyệt, CI job build/test với tối thiểu quyền, release operator phê duyệt và deployment job dùng identity scope staging/prod. Nên có audit khi bypass branch policy hoặc cấp service connection cho pipeline mới.

### 24.4. Nếu cần build container sau JAR

Luồng mở rộng:

~~~text
Compile/test Java
→ Package immutable JAR
→ Scan dependencies/SBOM
→ Docker build using pinned trusted base image
→ Scan/sign image
→ Push ACR with scoped identity
→ CD deploy approved digest
~~~

Không gộp các bước thành lệnh Docker push duy nhất rồi bỏ test; cũng không bắt buộc có ACR mới hoàn thành bài Java CI.

## 25. Troubleshooting Azure Pipelines cho Java

| Triệu chứng | Nguyên nhân thường gặp | Nơi kiểm tra |
|---|---|---|
| PR Azure Repos không kích hoạt | Chỉ có YAML pr, thiếu Build Validation | Branch Policies của main |
| Push không chạy CI | Branch/path filter hoặc pipeline disabled | YAML trigger, pipeline settings |
| Job mãi queued | Thiếu hosted parallelism/agent capacity | Agent pools và queue |
| Agent không có JDK 21 | Image đổi hoặc self-hosted thiếu JDK | JavaToolInstaller/agent capabilities |
| Maven “release version not supported” | Build JDK cũ hơn compiler release | java -version và Maven runtime |
| Maven Wrapper không chạy | Script/file mode/distribution download | mvnw, wrapper properties |
| Gradle Wrapper permission denied | gradlew không executable | Git executable bit hoặc bash wrapper |
| Maven dependency 401 | Feed auth/server ID không đúng | MavenAuthenticate/feed ACL |
| Maven dependency 403 | Feed permission/scope không đủ | Project/collection Build Service identity |
| Dependency checksum mismatch | Corrupt cache/mirror hoặc tampering | Repository integrity, cache policy |
| Tests không chạy | Surefire/Failsafe/Gradle task config sai | Test discovery, skip flags |
| Tests fail | Bug/flaky test hoặc environment | JUnit XML, failure logs |
| JUnit reports không tìm thấy | Paths hoặc tests không chạy | target/surefire-reports, build/test-results |
| JaCoCo XML không có | Plugin/report goal không được chạy | POM/Gradle configuration |
| JAR staging trống | Sai directory/module/packaging | target, build/libs và CopyFiles |
| Artifact là plain JAR thay vì boot JAR | Copy glob chọn sai | Boot plugin output/convention |
| PublishPipelineArtifact không hỗ trợ | Server/task compatibility | Azure DevOps Services vs Server |
| Disk full | Testcontainers, cache, Docker layers | Agent disk space |
| Maven/Gradle OOM | JVM heap/agent RAM | MAVEN_OPTS/Gradle JVM config |
| Build chậm | Cache miss, tests, network, queue | Timeline, cache logs |
| Testcontainers fail | Docker runtime/socket/privilege | Agent capabilities |
| TLS/proxy errors | Mạng hoặc trust roots | Egress/proxy/CA configuration |
| Pipeline xanh dù test fail | continueOnError hoặc skip flags | Task conditions/POM |
| Secret lộ trong logs | Script echo/wire logging | Incident triage + rotation |
| CD lấy nhầm JAR | Artifact/run selection sai | Run ID/source SHA/approval |

### 25.1. Lỗi JDK

~~~text
Fatal error compiling: error: release version 21 not supported
~~~

Điều tra:

1. **java -version** trong cùng job.
2. **bash ./mvnw --version** để biết JVM Maven thực dùng.
3. Maven compiler release/source/target và plugin.
4. JavaToolInstaller@0 inputs, agent image support.
5. Toolchains file nếu project dùng nhiều JDK.
6. Runtime compatibility sau deploy.

Không hạ compiler release chỉ để qua build nếu source cần Java 21 APIs.

### 25.2. Lỗi không có JUnit XML

- Build fail trước test phase, chưa có report.
- Tests bị tắt bởi **-DskipTests** hoặc cấu hình build.
- Surefire nhận tên class khác test convention.
- Failsafe chưa bind integration-test/verify goals.
- Gradle test task bị skip do condition hoặc cache.
- Multi-module report nằm ở module subdirectory.
- PublishTestResults tìm sai root path.

**Một pipeline không có bài test** chưa chắc quality gate đạt. Với service production nên có explicit check thay vì bỏ qua khi report rỗng.

### 25.3. Lỗi Publish artifact không có JAR

Nếu Maven project là **parent packaging=pom**, không có root target JAR. Nếu Spring Boot tạo **plain.jar** cạnh **bootJar**, một glob rộng có thể copy nhầm cả hai. Kiểm tra artifact count/path/checksum trước Publish. Không che lỗi CopyFiles bằng điều kiện always().

### 25.4. Lỗi sau khi hosted image được nâng cấp

**ubuntu-latest** có thể được Microsoft cập nhật. Trong job ghi JDK/Maven/Gradle versions và agent image metadata. Nếu regression:

- Reproduce trên version cũ và mới theo images còn hỗ trợ.
- Pin toolchain bằng wrapper và JDK version.
- Kiểm tra TLS/CA, Docker/Testcontainers, distro packages.
- Dùng container job image được kiểm soát khi cần.
- Đừng pin image đã hết hỗ trợ/vá bảo mật quá hạn để giữ CI xanh.

### 25.5. Lỗi private feed không liên quan Azure RBAC subscription

**App Service Contributor** hoặc **Key Vault Secrets User** không đồng nghĩa Azure Artifacts feed reader. Với dependency 401/403, xác minh feed URL/server ID/job identity/permissions/MavenAuthenticate, không nâng Azure subscription role.

### 25.6. Lỗi security scan

SCA/security scanner có thể lỗi vì external service timeout hoặc thiếu token chứ không phải tìm ra vulnerability. Phân biệt:

- **Scan complete, finding critical** → gate fail theo policy.
- **Scanner unavailable** → fail closed hoặc có waiver được duyệt, không tự coi scan pass.
- **False positive** → triage evidence, owner và expiry.
- **Dependency inaccessible** → kiểm tra repo/feed network, không tự đổi mirror không tin cậy.

## 26. Observability và run health

### 26.1. Những chỉ số hữu ích

| Chỉ số | Câu hỏi cần trả lời |
|---|---|
| Pipeline success rate | Main/PR runs có ổn định không? |
| Build queue time | Chậm do thiếu agent capacity? |
| Checkout time | Repo/LFS network có thành bottleneck? |
| Cache hit ratio | Cache có giảm dependency download? |
| Maven/Gradle build duration | Compiler/plugins chậm ở đâu? |
| Unit/integration test duration | Suite nào làm tăng feedback time? |
| Flaky test rate | Chất lượng validation có đáng tin? |
| Coverage/quality-gate trends | Thay đổi có giảm verification? |
| Artifact size/digest | Có bất thường artifact packaging? |
| Time to first PR feedback | Developer phải chờ bao lâu? |
| Time to approved build artifact | Chu kỳ phát hành mất bao lâu? |
| Agent minutes/parallel jobs | Compute/cost capacity như thế nào? |
| Role/connection policy changes | Có dấu hiệu quyền mở rộng không? |

Azure DevOps UI cung cấp logs, timeline, test results và nhiều thông tin run. Một số metrics/tổng hợp phải được tạo qua API, dashboard hoặc telemetry riêng.

### 26.2. Ví dụ timeline build

~~~text
09:00 Commit pushed
09:01 Run queued
09:03 Agent allocated
09:04 Checkout finished
09:05 JDK 21 configured
09:06 Dependency cache restored
09:12 Maven verify completed
09:13 JUnit/coverage published
09:14 JAR checksum and artifact publish finished

Queue time: 2 min
Execution time: 11 min
End-to-end feedback: 14 min
~~~

**Các số là giả định**, không phải SLA Azure Pipelines. Điều đáng chú ý là phân biệt queue wait với compilation/test/scan duration để tối ưu đúng chỗ.

### 26.3. Một log metadata an toàn

~~~json
{
  "event": "JAVA_CI_BUILD",
  "service": "orders-api",
  "runId": "1428",
  "sourceCommit": "abcdef123",
  "jdk": "21",
  "buildTool": "Maven Wrapper",
  "tests": "PASSED",
  "artifact": "orders-api-java",
  "durationSeconds": 640
}
~~~

Không đưa PAT, secret variables, private feed token, access token, connection string, sensitive customer fixtures hoặc raw Authorization headers vào log. Even non-secret source metadata có thể phải tuân theo data classification.

### 26.4. Khi nào cần alert?

- Main CI đỏ liên tiếp hoặc required PR validation không chạy.
- Agent queue vượt hạn feedback SLO.
- Missing test reports nhưng pipeline vẫn xanh.
- Artifact missing hoặc checksum mismatch.
- Critical dependency CVE/secret scan alert.
- Service connection/variable group authorization được mở rộng trái phép.
- Build artifact bị xóa theo retention trước khi CD sử dụng.
- Hosted image/toolchain update gây widespread regression.

Alert phải có owner/on-call và runbook; không gửi cùng một thông báo từ 5 systems gây alert fatigue.

## 27. Hiệu năng và chi phí build

### 27.1. Những thứ ảnh hưởng chi phí

| Thành phần | Yếu tố |
|---|---|
| Microsoft-hosted agents | Parallel jobs, job minutes và plan/entitlement |
| Self-hosted agents | VM/OS/disk/network, vận hành, updates, security |
| Artifact storage/retention | Kích thước JAR, reports, pipeline artifacts và policy |
| Azure Artifacts | Feed/storage limits, retention và usage |
| Security scanners | Tool license, external service, compute/time |
| Testcontainers | Docker resources và thời gian test |
| Private network | Egress/proxy/networking của self-hosted agents |
| Container image builds | Build compute, registry/storage/push operations |
| Logs/monitoring | Retention và export theo plan |
| Reviewer/developer wait time | Feedback latency, reruns, flaky tests |

Không đưa đơn giá cố định vì Azure DevOps plans, hosted parallelism và billing terms thay đổi; dùng chính sách license/cost hiện hành của organization.

### 27.2. Phép tính build minutes

Giả định:

~~~text
30 PRs/ngày
2 validation runs/PR (mỗi lần 8 phút)
4 main branch builds/ngày (mỗi lần 12 phút)

PR agent minutes = 30 × 2 × 8 = 480
Main agent minutes = 4 × 12 = 48
Total = 528 agent minutes/ngày
~~~

Nếu mỗi PR tự động chạy **matrix JDK 17 + 21** trên hai agents, tổng minutes có thể gần gấp đôi, chưa tính queue/caching variations. **Parallel jobs** có thể rút wall-clock feedback nhưng làm tiêu thụ đồng thời nhiều agent slots.

### 27.3. Tối ưu từng bottleneck

- Tăng **cache hit** mà không cache secrets/build output.
- Dùng Maven/Gradle Wrapper để giảm drift.
- Chỉ thêm matrix khi có compatibility requirement.
- Chạy unit tests nhanh trên PR; integration/nightly với risk-based policy.
- Giảm flaky tests thay vì retry mãi.
- Tối ưu test fixtures, DB startup và Testcontainers.
- Split jobs khi rút critical path rõ rệt và agent capacity cho phép.
- Dùng path filters thận trọng; không bỏ qua shared build/security files.
- Dọn artifacts không còn cần theo retention, giữ approved release artifacts.
- Pin toolchains trước, đừng dựa hosted image biến đổi bất ngờ.

### 27.4. Cache có thể làm build chậm hơn

Nếu Maven repository nhỏ và cache artifact rất lớn, thời gian restore/save có thể cao hơn tải trực tiếp. Đo **Cache@2 hit/miss/download/save duration** và dependency resolve time. Không mặc định thêm cache luôn cải thiện hiệu năng.

### 27.5. Biến động chi phí do pipeline failure

Một PR code độc hại có thể tạo script chạy vô hạn hoặc tải rất nhiều dữ liệu nếu không có timeout/egress/permissions. Giới hạn:

- Job timeout/cancel.
- Parallelism và budget.
- Resource quotas.
- Repo permissions, branch policies.
- Network and credential scoping.
- Build artifact size and retention limits.

## 28. Runbook cho một lần build Java thất bại

Một trình tự làm việc cho SRE/developer:

1. Xác định **pipeline ID/run ID/source commit/branch/PR**.
2. Mở job/stage đầu tiên báo failure; phân biệt infrastructure với code failure.
3. Xác định agent image/JDK/Maven/Gradle version.
4. Đọc error cụ thể, không chỉ xem dòng cuối “Job failed”.
5. Nếu lỗi dependency, kiểm tra repository/feed/auth/network.
6. Nếu compile fail, kiểm tra JDK/target release, source/annotation processors.
7. Nếu test fail, xem JUnit XML và related logs.
8. Nếu scan fail, phân biệt finding với scanner availability.
9. Nếu package fail, kiểm tra POM/Gradle plugin và output path.
10. Nếu Publish fail, kiểm tra artifact staging/permission/task support.
11. Giữ log/metadata cần điều tra; không paste credentials vào ticket.
12. Reproduce local bằng wrapper/JDK tương ứng nếu có thể.
13. Tạo fix PR và chạy required validation; không bypass branch policy.
14. Nếu build xanh trở lại, xem artifact/run SHA và postmortem nếu lỗi ảnh hưởng nhiều services.
15. Khi nghi compromise, containment credential/agent và preserve evidence trước khi retry.

### 28.1. Không chỉ bấm Retry

Retry có thể phù hợp với outage transient (feed 503/agent issue), nhưng nếu source code compile sai hoặc vulnerability gate fail, retry lặp lại không sửa nguyên nhân. Với lỗi từ PR độc hại, rerun trên agent có quyền cao có thể tăng phạm vi tấn công.

### 28.2. Một regression từ Maven Wrapper

Nếu wrapper distribution URL bị sửa trong PR, phải xem như thay executable supply-chain input. Không tự cho pipeline tải Maven từ domain lạ để build qua; review source, checksum và commit history.

### 28.3. Recovery khi artifact đã hết hạn

Nếu artifact của approved release bị xóa, không tùy tiện deploy JAR có cùng tên từ run khác. Kiểm tra retention/registry, provenance, signature và policy; nếu phải rebuild, tạo **run mới** có đầy đủ validation và ghi rõ đây là artifact khác, không khẳng định nó byte-identical nếu chưa verify.

## 29. Lab end-to-end: xây CI cho Orders API

Đây là hướng dẫn chạy trong **Azure DevOps project/repository lab được phê duyệt**, không phải thao tác đã được thực hiện trong lúc soạn bài.

### 29.1. Chuẩn bị

- Có Azure DevOps organization/project và quyền tạo pipeline/đọc repo.
- Có project Java 21 Maven Spring Boot với **pom.xml**, **mvnw**, **mvnw.cmd** và tests.
- Chỉ dùng sample data, không chứa production secrets.
- Có khả năng chạy Maven Wrapper local.
- Có Microsoft-hosted agent entitlement/parallel jobs hoặc self-hosted agent lab.
- Xác định loại source provider: Azure Repos Git hay GitHub.
- Có quyền tạo branch policy nếu muốn PR validation bắt buộc.
- Nếu có private feed, operator đã cấp quyền read cho pipeline identity.
- Không tạo service connection production cho bài lab.

### 29.2. Chuẩn hóa project local

Ở checkout của repo lab:

~~~bash
java -version
bash ./mvnw --version
bash ./mvnw -B -ntp clean verify
~~~

Kiểm tra:

1. JDK target khớp POM.
2. Maven Wrapper distribution hợp lệ.
3. Có ít nhất một unit test có assertions.
4. Có **target/surefire-reports/TEST-*.xml**.
5. Có deployable **target/*.jar** cho single-module project.
6. Không có credential trong source/POM/test fixtures.
7. Build không dựa vào environment của một developer cá nhân.

### 29.3. Thêm azure-pipelines.yml

Copy và tùy chỉnh ví dụ mục 8:

- Đổi JDK version cho project.
- Giữ **checkout self** và versioned source.
- Dùng Maven Wrapper hoặc Maven@4 theo policy, không chạy cả hai vô cớ.
- Cấu hình cache đúng path và key.
- Chạy **clean verify**.
- Publish test results kể cả khi test failed.
- Verify JAR tồn tại, không nhầm sources/plain JAR.
- Publish Pipeline Artifact tên **orders-api-java**.

### 29.4. Chạy build đầu tiên

1. Commit YAML trên nhánh lab.
2. Mở **Pipelines → New pipeline** và chọn repo/YAML.
3. Review pipeline YAML từ source đáng tin.
4. Chạy một run trong scope lab.
5. Mở logs của JavaToolInstaller, Cache, Maven, JUnit, Artifact Publish.
6. Xác minh run ID và source commit.
7. Download artifact, tính SHA-256 rồi so digest trong log.
8. Xem Tests tab và kết quả test.
9. Nếu test fail, đảm bảo pipeline fail và artifact không được phát hành như approved release.

### 29.5. Test PR validation

Nếu source là **Azure Repos Git**:

1. Mở **Repos → Branches → main → Branch policies**.
2. Thêm **Build validation** cho pipeline.
3. Đặt Required theo lab policy.
4. Tạo PR có một test cố ý fail trong môi trường test được phép.
5. Xem build validation đỏ và xác minh merge bị chặn.
6. Sửa test trên PR, chạy lại validation, xác minh xanh.
7. Không bypass chỉ để xem “merge có hoạt động không” trên repository shared.

Với GitHub, kiểm tra YAML **pr** trigger và required GitHub checks/branch protection theo tích hợp. Đừng áp logic Azure Repos branch policies của Azure DevOps lên GitHub như thể cùng một UI.

### 29.6. Test caching

1. Chạy pipeline lần đầu, ghi thời gian dependency download/cache miss.
2. Chạy lại cùng source/toolchain, xem cache hit/restore.
3. Đo Maven verify duration tổng cộng.
4. Đổi POM trong PR lab, quan sát cache key thay đổi.
5. Xác minh build vẫn test đầy đủ dù cache hit.
6. Kiểm tra cache không chứa settings.xml hoặc token.

### 29.7. Test JDK mismatch

Trong nhánh lab, thay JDK selector thành version không đáp ứng POM và xem compiler errors. Khôi phục JDK đúng; không hạ Java target nếu project thực sự dùng APIs mới. Đây là negative test để học cách debug toolchain.

### 29.8. Test artifact traceability

Một báo cáo lab mẫu:

| Hạng mục | Giá trị minh họa |
|---|---|
| Repo | orders-api |
| Pipeline | orders-api-ci |
| Run ID | 1428 |
| Commit SHA | abcdef123 |
| JDK | 21 |
| Maven | Wrapper pinned |
| Compile | PASS |
| Unit tests | 42 passed |
| Coverage | JaCoCo report when configured |
| Artifact | orders-api-java |
| Checksum | recorded SHA-256 |
| Secret exposure | none observed |
| PR validation | Required on main |
| Deploy production | Not attempted |

**Tất cả con số và IDs là ví dụ**. Khi làm lab thật, ghi giá trị từ run thực tế, không tự sao chép bảng này như kết quả kiểm thử.

### 29.9. Tiêu chí hoàn thành

Lab đạt khi:

- YAML được review, chạy từ repo chính xác.
- Build bằng JDK/toolchain rõ ràng.
- Maven/Gradle compile, unit tests, quality gates theo POM/Gradle.
- Tests thất bại làm build fail và có JUnit report.
- Artifact có checksum, run ID và commit provenance.
- Required PR build validation hoạt động với provider thực tế.
- Không có PAT/secret/production service connection trong job PR.
- Không publish artifact như approved release khi tests fail.
- Có logs/metadata đủ để debug và ước tính agent minutes.

## 30. Các anti-pattern cần tránh

| Anti-pattern | Hậu quả | Cách sửa |
|---|---|---|
| Build JAR trên laptop rồi gửi thủ công | Không rõ commit/toolchain/test | Azure Pipeline CI reproducible |
| Dùng JDK mặc định của ubuntu-latest không kiểm tra | Image update làm compile fail | Explicit JDK + wrapper |
| Build với -DskipTests | PR có bug vẫn xanh | clean verify, required tests |
| Chỉ chạy package và tưởng đã có integration tests | Quality gates không tồn tại | Cấu hình Surefire/Failsafe đúng |
| Publish JAR từ root target khi multi-module | Artifact rỗng/sai module | Chọn đúng module path |
| Publish mọi JAR trong repo | Copy cả library/sources/test jars | Validate artifact count/type |
| Cache target hoặc build/libs | Artifact stale | Chỉ cache dependency cache có kiểm soát |
| Cache file credentials | Secret leakage | Tách credential from cache |
| Dùng SNAPSHOT trong release không kiểm soát | Build không tái lập | Immutable versions |
| PR job có production secrets | PR script exfiltration | Separate untrusted/privileged jobs |
| Dùng PAT dài hạn cho private feed | Rotation khó/blast radius | Feed identity + MavenAuthenticate |
| Service connection dùng được bởi mọi pipeline | Permission abuse | Resource authorization |
| Có pr YAML nhưng không có Build Validation Azure Repos | PR không bị chặn merge | Branch policy Required |
| path filter bỏ qua shared build files | Security check không chạy | Bao gồm mọi build-affecting paths |
| Bấm Retry 10 lần để qua flaky test | Che test instability | Root cause, deterministic fixtures |
| continueOnError cho dependency scan | Release có CVE critical | Enforce security gate |
| In token vào logs để debug 401 | Credential exposed | Sanitized auth diagnostics |
| Dùng curl pipe bash từ nguồn lạ | Supply-chain RCE | Pin + verify trusted installer |
| Trust artifact chỉ vì có SHA-256 | Attacker thay cả hash và binary | Signing/provenance |
| Tải “latest artifact” khi deploy | Nhầm branch/run | Approved run and digest |
| Rebuild ở production | Bản được deploy khác bản đã test | Build once, deploy many |
| Gán Owner cho build job chỉ để compile Java | Excess privilege | No Azure subscription rights for pure build |
| Dùng self-hosted release agent cho fork PR | Agent/secret compromise | Isolated agents |
| Lưu artifacts mãi không chính sách | Cost/storage/compliance | Retention/approved release preservation |
| Chạy build rồi không ai xem failing status | Broken main kéo dài | Required checks + alerts |

## 31. Checklist production cho Java CI

### 31.1. Repository và triggers

- [ ] YAML pipeline ở repository, code owners review changes.
- [ ] Repo/build wrapper/POM/Gradle scripts được xem là executable inputs.
- [ ] CI trigger chạy đúng branches, paths không bỏ quên shared build files.
- [ ] Azure Repos main có **Build Validation branch policy Required** nếu dùng Azure Repos.
- [ ] GitHub required checks được cấu hình phù hợp nếu source GitHub.
- [ ] Fork PR jobs không có production credentials/privileged network.
- [ ] Repo settings cấm bypass tùy tiện hoặc ghi audit khi bypass.
- [ ] Build cancellation/timeout/retry policies rõ.

### 31.2. JDK và build tooling

- [ ] JDK version rõ và tương thích project target/runtime.
- [ ] Maven/Gradle Wrapper version/checksum được kiểm tra.
- [ ] Agent image/tool versions được ghi vào metadata.
- [ ] Build dùng **clean verify** hoặc **clean build/check** có tests.
- [ ] POM/Gradle plugins được pin, dependencies có approved BOM/lockfile.
- [ ] Build không phụ thuộc tool cài tay trên developer laptop.
- [ ] Multi-module paths được xác minh chính xác.
- [ ] Có runbook khi hosted agent image thay đổi.
- [ ] Self-hosted agents được patch/isolate nếu dùng.

### 31.3. Tests và quality gates

- [ ] Có unit tests thực sự và JUnit XML.
- [ ] Missing test results không silently pass khi suite bắt buộc.
- [ ] Integration tests được cấu hình riêng và có owner.
- [ ] Testcontainers/lab credentials không chạm production.
- [ ] Coverage reports được publish nếu đã cấu hình JaCoCo.
- [ ] Coverage thresholds là gate thực, không chỉ báo cáo.
- [ ] Static/security/dependency/license scans theo policy.
- [ ] Critical findings không bị continueOnError che giấu.
- [ ] Flaky tests có quarantine owner/timebound fix.
- [ ] CI xanh chỉ khi những gates bắt buộc đạt.

### 31.4. Artifact và supply chain

- [ ] Đã kiểm tra artifact count, name, binary type và kích thước.
- [ ] Publish Pipeline Artifact sau build/test thành công.
- [ ] Lưu run ID, commit, toolchain và SHA-256.
- [ ] Có SBOM/provenance/signature nếu release policy yêu cầu.
- [ ] Không commit hoặc publish secrets vào artifacts/logs.
- [ ] Downstream CD chọn artifact từ **approved run**, không lấy latest bất kỳ.
- [ ] Có retention cho release artifacts phù hợp rollback.
- [ ] SCA xác minh dependencies và plugin repositories được phép.
- [ ] Không dùng untrusted install scripts.
- [ ] Có quy trình điều tra compromised build credential/artifact.

### 31.5. IAM, secrets, network và FinOps

- [ ] Pure Java build không có Azure subscription privileges không cần thiết.
- [ ] Feed read permission có scope chính xác.
- [ ] Build identity được phân biệt với release/deployment identity.
- [ ] Service connections/variable groups có resource authorization và checks.
- [ ] OIDC federation được ưu tiên thay long-lived secret khi hỗ trợ.
- [ ] Không in token/PAT/Authorization headers.
- [ ] Caches không chứa credentials.
- [ ] Agents được bảo vệ outbound/permissions theo trust level.
- [ ] CI queue/build/test duration có dashboard và owner.
- [ ] Có alert failing main, blocked security gate, missing artifact.
- [ ] Đã tính agent minutes/parallelism, cache hiệu quả và artifact retention.
- [ ] Không tắt required tests/security gates chỉ để giảm phí.
- [ ] Pipeline secrets và access logs có incident response plan.

## 32. Bài tập thực hành

### Bài 1: Vẽ đường đi của artifact

Vẽ flow từ commit tới JAR và gắn **agent, JDK, Maven, JUnit, JaCoCo, artifact store, source SHA** vào mỗi bước. Giải thích vai trò của CI so với CD.

### Bài 2: Maven YAML

Dựa trên ví dụ mục 8:

1. Chọn JDK 17 thay 21 cho một project Java 17.
2. Thêm Maven Wrapper.
3. Bật Cache@2.
4. Chạy clean verify.
5. Publish JUnit reports.
6. Fail nếu không có JAR hoặc thiếu required tests.
7. Publish artifact có tên rõ.

### Bài 3: Gradle YAML

Viết pipeline tương đương cho Gradle Wrapper, gồm clean build, JUnit XML và chỉ lấy một boot JAR đúng. Giải thích điều gì xảy ra nếu project có cả plain.jar và bootJar.

### Bài 4: Azure Repos PR validation

Repo có pr YAML nhưng PR vào main không trigger. Tìm nguyên nhân, tạo **Branch Policy Build Validation Required**, thử một test fail và kiểm tra merge bị chặn.

### Bài 5: Private Maven feed 401

Pipeline không resolve được **com.company.shared:common-auth**. Lập runbook xác minh repository URL, POM server ID, MavenAuthenticate task, build identity/feed ACL và egress; không giải quyết bằng cách commit PAT.

### Bài 6: Cache poisoning

Giả sử cache key rộng và một run PR untrusted có thể lưu dependency bị thay. Đề xuất cách tách trust boundaries, version cache keys, verify dependency integrity và bảo vệ release builds.

### Bài 7: JaCoCo quality gate

Cấu hình JaCoCo report và check cho Maven, thử viết một failing test/giảm coverage, xác nhận **CI đỏ**. Giải thích vì sao chỉ chạy PublishCodeCoverageResults không đủ chặn merge.

### Bài 8: Multi-module Maven

Project có common-model, common-security và orders-api. Sửa pipeline để build reactor, kiểm thử shared modules và chỉ publish **orders-api executable JAR**. Viết explicit artifact count validation.

### Bài 9: PR có mã độc trong POM

Một PR thêm Maven plugin có thể đọc biến môi trường. Hãy xác định những controls để job này không lấy production secrets, dù reviewer chưa kịp phát hiện.

### Bài 10: Matrix JDK

Library cần hỗ trợ JDK 17/21. Thiết kế matrix jobs, đo agent minutes so pipeline chỉ có một JDK và quyết định chất lượng/chi phí có đáng không.

### Bài 11: Artifact provenance

Từ run ID, commit SHA, Maven/JDK versions, test status và JAR checksum, tạo release manifest. Giải thích vì sao hash không thay digital signature.

### Bài 12: Flaky integration tests

Một test Testcontainers thỉnh thoảng fail vì race/network. Thiết kế test isolation, fixtures, timeout, logs và policy xử lý flaky test; không sử dụng retry vô hạn.

### Bài 13: Source trust và service connection

Thiết kế tách PR build, trusted post-merge publish và approved Azure deployment. Ghi rõ identity quyền gì, secrets xuất hiện ở job nào và điều gì ngăn PR dùng credential production.

### Bài 14: Agent capacity và FinOps

Với 30 PRs/ngày, hai runs/PR, mỗi run 8 phút và 4 main builds mỗi ngày 12 phút, tính **528 agent minutes/ngày** rồi phân tích tác động khi thêm matrix JDK/parallel tests.

### Bài 15: Troubleshooting artifact missing

Maven verify pass nhưng PublishPipelineArtifact không có JAR. Kiểm tra project packaging, multi-module path, Spring Boot repackaging, CopyFiles pattern và fail-if-empty validation.

### Bài 16: Build compromise tabletop

SOC phát hiện Maven Wrapper distribution URL đổi sang domain lạ cùng lúc pipeline có secret variable. Lập response plan: cancel run, thu hồi credential, quarantine agent, preserve logs, review artifact provenance, rotate key và thêm regression controls.

## 33. Câu hỏi tự kiểm tra

1. Azure Pipelines thuộc sản phẩm Azure DevOps nào?
2. Organization khác project và pipeline ra sao?
3. Agent và agent pool là gì?
4. Job khác step/task và stage thế nào?
5. CI khác CD ở phạm vi nào?
6. Tại sao nên build once, deploy many?
7. Maven **verify** khác **package** và **deploy** ra sao?
8. Maven Wrapper giúp vấn đề gì?
9. Gradle Wrapper khác Gradle cài sẵn trên agent ở đâu?
10. Build JDK khác runtime JDK và compiler target release như thế nào?
11. **ubuntu-latest** có phải image bất biến không?
12. JavaToolInstaller@0 làm gì?
13. Maven@4 task khác Bash Maven Wrapper như thế nào?
14. Task **Cache@2** thường lưu gì?
15. Cache hit có bảo đảm dependency an toàn không?
16. Vì sao không cache Maven settings.xml có credentials?
17. Vì sao không cache **target/** rồi publish JAR?
18. Maven Surefire và Failsafe thường chạy loại tests nào?
19. JUnit XML ở Maven và Gradle thường nằm ở đâu?
20. Vì sao PublishTestResults chạy với succeededOrFailed?
21. Tại sao missing required test reports cần làm pipeline fail?
22. PublishCodeCoverageResults có tự áp threshold không?
23. JaCoCo check cần điều kiện gì để fail theo ngưỡng?
24. Task PublishPipelineArtifact làm gì mà CopyFiles không làm?
25. Trong pipeline hai stages, tại sao phải download artifact ở job sau?
26. Artifact checksum khác digital signature như thế nào?
27. **Build.SourceVersion** và **Build.BuildId** mang ý nghĩa gì?
28. Một artifact có thể được tạo từ PR run không được duyệt không?
29. Tại sao không tải latest artifact để tự động deploy production?
30. YAML **pr** trigger hoạt động thế nào với Azure Repos Git?
31. Azure Repos required build validation được cấu hình ở đâu?
32. Tại sao path filters trong monorepo có thể gây lỗ hổng?
33. Multi-module Maven cần điều chỉnh artifact path thế nào?
34. Maven **-pl** và **-am** giải quyết việc gì?
35. Gradle **bootJar** khác library jar ở đâu?
36. Vì sao pipeline YAML/POM/wrapper đều là executable code?
37. Untrusted PR job có nên đọc production secrets không?
38. Job access token khác Azure Resource Manager service connection như thế nào?
39. Azure Artifacts feed 401/403 có tự sửa bằng Azure Contributor không?
40. MavenAuthenticate@0 giúp điều gì?
41. Bí mật trong variable group có bảo vệ được nếu script độc hại thực thi không?
42. Workload identity federation giúp giảm loại credential nào?
43. SBOM là gì? Nó có bảo đảm không có mã độc không?
44. Provenance/attestation cần gì để đáng tin?
45. SLSA-style controls nhắm tới nguy cơ nào?
46. Khi nào nên dùng self-hosted agent?
47. Những rủi ro nếu chạy fork PR trên self-hosted release agent?
48. Vì sao một test flaky không nên được bỏ qua vĩnh viễn?
49. Build success rate và queue time nên được đo khác nhau thế nào?
50. Làm thế nào giảm agent minutes mà không làm mất các quality gates bắt buộc?

## 34. Tài liệu tham khảo

- [Azure Pipelines documentation — Microsoft Learn](https://learn.microsoft.com/azure/devops/pipelines/)
- [Build Java apps with Azure Pipelines](https://learn.microsoft.com/azure/devops/pipelines/ecosystems/java)
- [Build and deploy with Maven](https://learn.microsoft.com/azure/devops/pipelines/ecosystems/maven)
- [Build Java apps with Gradle](https://learn.microsoft.com/azure/devops/pipelines/ecosystems/gradle)
- [Azure Pipelines YAML schema](https://learn.microsoft.com/azure/devops/pipelines/yaml-schema/)
- [YAML pipeline triggers](https://learn.microsoft.com/azure/devops/pipelines/build/triggers)
- [Configure CI triggers](https://learn.microsoft.com/azure/devops/pipelines/repos/azure-repos-git)
- [Azure Repos branch policies](https://learn.microsoft.com/azure/devops/repos/git/branch-policies)
- [Microsoft-hosted agents](https://learn.microsoft.com/azure/devops/pipelines/agents/hosted)
- [Self-hosted agents](https://learn.microsoft.com/azure/devops/pipelines/agents/agents)
- [Azure Pipelines tasks reference](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/)
- [Maven@4 task](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/maven-v4)
- [JavaToolInstaller@0 task](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/java-tool-installer-v0)
- [Gradle task reference](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/gradle-v3)
- [Cache@2 task](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/cache-v2)
- [Pipeline caching](https://learn.microsoft.com/azure/devops/pipelines/release/caching)
- [PublishTestResults@2 task](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/publish-test-results-v2)
- [PublishCodeCoverageResults@2 task](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/publish-code-coverage-results-v2)
- [PublishPipelineArtifact@1 task](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/publish-pipeline-artifact-v1)
- [DownloadPipelineArtifact@2 task](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/download-pipeline-artifact-v2)
- [Pipeline Artifacts](https://learn.microsoft.com/azure/devops/pipelines/artifacts/pipeline-artifacts)
- [Azure Pipelines expressions and conditions](https://learn.microsoft.com/azure/devops/pipelines/process/conditions)
- [Azure Pipelines variables](https://learn.microsoft.com/azure/devops/pipelines/process/variables)
- [Azure Pipelines templates](https://learn.microsoft.com/azure/devops/pipelines/process/templates)
- [Azure Pipelines security](https://learn.microsoft.com/azure/devops/pipelines/security/overview)
- [Secure access to repositories](https://learn.microsoft.com/azure/devops/pipelines/security/secure-access-to-repos)
- [Azure service connections](https://learn.microsoft.com/azure/devops/pipelines/library/service-endpoints)
- [MavenAuthenticate@0 task](https://learn.microsoft.com/azure/devops/pipelines/tasks/reference/maven-authenticate-v0)
- [Azure Artifacts Maven packages](https://learn.microsoft.com/azure/devops/artifacts/maven/)
- [Spring Boot Maven Plugin](https://docs.spring.io/spring-boot/maven-plugin/)
- [Gradle Java plugin](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Maven build lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [JaCoCo Maven Plugin](https://www.jacoco.org/jacoco/trunk/doc/maven.html)
- [CycloneDX documentation](https://cyclonedx.org/docs/)
- [SLSA supply chain security framework](https://slsa.dev/)
- [Azure DevOps pricing](https://azure.microsoft.com/pricing/details/devops/azure-devops-services/)






