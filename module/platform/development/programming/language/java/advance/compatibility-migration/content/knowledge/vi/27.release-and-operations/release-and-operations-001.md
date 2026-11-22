
# Lưu artifact, cấu hình và kết quả kiểm thử của từng bước chuyển đổi

Nâng cấp Java không chỉ là thay dòng `sourceCompatibility` hoặc đổi Docker base image. Trong một hệ thống đang vận hành, quá trình có thể gồm nhiều bước: nâng JDK biên dịch, giữ hoặc đổi `--release`, cập nhật Gradle/Maven, thay dependency, loại API nội bộ, chuyển framework và Jakarta EE, điều chỉnh JVM flags, kiểm thử tương thích nhiều phiên bản, rồi triển khai canary. Mỗi bước có thể tạo **binary mới, cấu hình mới và kết quả kiểm thử mới**.

Nếu chỉ ghi “CI xanh” hoặc “đã nâng lên Java 21”, vài tuần sau nhóm phát triển rất khó trả lời: artifact nào được kiểm thử, artifact nào đã phát hành, JDK update chính xác là gì, server đã sử dụng GC nào, những test nào bị skip, bộ dependency nào tạo ra lỗi, và liệu rollback có khả thi hay không.

Vì thế, trong *Java Advance Compatibility Migration*, phần *Phát hành và vận hành*, **lưu artifact, cấu hình và kết quả kiểm thử theo từng bước chuyển đổi** là một phần của chiến lược tương thích: tạo chuỗi bằng chứng có thể tái hiện, đối chiếu, kiểm chứng tính toàn vẹn và hỗ trợ điều tra lỗi/rollback.

Mục tiêu không phải thu thập mọi file vô hạn, mà là lưu **đúng đối tượng, đúng phiên bản, có quan hệ truy xuất rõ và có kiểm soát bảo mật**.

## 1. Vì sao mỗi bước migration phải có bằng chứng?

Giả sử ứng dụng đi qua các trạng thái:

~~~text
S0: Java 11, framework cũ, dependency cũ
S1: compiler JDK 21, vẫn build --release 11
S2: thay dependency dùng JDK internal APIs
S3: nâng framework, sửa javax -> jakarta
S4: chuyển runtime và bytecode baseline
S5: tối ưu GC và tài nguyên container
S6: canary và production rollout
~~~

Nếu chỉ lưu artifact cuối S6, một regression ở production có thể do S1, S2, S3, S4 hoặc S5. Không có bằng chứng trung gian, nhóm phải tái tạo lại những điều kiện đã qua và có thể không còn build được bản cũ.

Việc lưu theo từng bước giúp:

- **Khoanh vùng thay đổi gây lỗi:** so sánh last-known-good với bước đầu tiên thất bại.
- **Tái hiện:** chạy đúng JAR, runtime và cấu hình từng dùng.
- **Ra quyết định:** release gate dựa vào báo cáo và số liệu thay vì cảm giác.
- **Rollback:** truy xuất ngay binary, container image, config và schema phù hợp.
- **Kiểm tra bảo mật:** xác định dependency/runtime nào cần vá.
- **Audit và phối hợp:** biết ai tạo, ai duyệt, khi nào và dựa trên bằng chứng nào.
- **Không mất kết quả thất bại:** lưu cả những lần test failed để hiểu nguyên nhân.

### 1.1. Một bước chuyển đổi là gì?

Một *migration step* cần có phạm vi và tiêu chí kiểm thử rõ. Ví dụ:

~~~text
ID: JAVA-MIG-04
Mục tiêu: nâng JDK chạy runtime từ 17 sang 21
Không đổi: public HTTP API, database schema, business features
Phải xác minh: startup, integration, API contract, p99, CPU, RSS
Kết quả: artifact + manifest + test reports + quyết định
~~~

Bước chuyển đổi không nhất thiết tương ứng một release production. Nó có thể là một giai đoạn nghiên cứu, staging, nâng toolchain hoặc sửa tương thích.

### 1.2. “Build thành công” chứng minh được gì?

Nó chứng minh quy trình build cụ thể đạt điều kiện exit của nó. Nó **không tự chứng minh**:

- Tất cả tests đều đã chạy.
- Artifact đang deploy giống artifact đã test.
- Runtime JDK tương thích.
- API/event/database contract không đổi.
- Các dependency native/JNI có mặt trong image.
- SLO hiệu năng được giữ.
- Có đường rollback sau schema migration.

Vì vậy, **build record là một phần của release evidence**, không phải toàn bộ.

## 2. Phân biệt artifact, cấu hình và kết quả kiểm thử

| Nhóm | Ví dụ | Câu hỏi được trả lời |
|---|---|---|
| Artifact phát hành | JAR, WAR, container image, desktop installer | Đã xây dựng binary nào? |
| Artifact phụ trợ | SBOM, generated source, migration SQL, runtime image | Binary được tạo từ thành phần nào? |
| Build configuration | JDK toolchain, build plugin, dependency lock | Đã build như thế nào? |
| Runtime configuration | JVM flags, heap/GC, feature flags, server/container | Binary chạy trong điều kiện nào? |
| Test evidence | JUnit XML, contract report, benchmark raw data | Đã kiểm chứng điều gì? |
| Deployment evidence | Image digest, rollout records, canary observations | Bản nào đang chạy ở đâu? |
| Decision evidence | Approval, exception, rollback decision | Vì sao được promote hoặc bị chặn? |

**Artifact** có thể được hiểu rộng là mọi đầu ra có giá trị từ pipeline. Nhưng khi thiết kế kho lưu trữ nên phân biệt **binary để chạy** với **bằng chứng dùng để giải thích binary**.

### 2.1. Mối quan hệ giữa các đối tượng

~~~mermaid
flowchart TD
    A["Migration step ID"] --> B["Source commit"]
    B --> C["Build toolchain + dependencies"]
    C --> D["Build ID"]
    D --> E["Binary artifact + SHA-256"]
    E --> F["Test runs + reports"]
    E --> G["Deployment + configuration"]
    F --> H["Release gate"]
    G --> H
    H --> I["Promote / Hold / Rollback"]
    I --> J["Runtime observations"]
~~~

Một test report chỉ chứa `PASS` mà không trỏ tới binary, JDK và môi trường không đủ để chứng minh một release an toàn.

## 3. Định danh: version không thay thế checksum

Trong một lần chuyển đổi có nhiều khái niệm phiên bản.

| Trường | Giá trị mẫu | Ý nghĩa |
|---|---|---|
| Git commit | `abcdef123...` | Mã nguồn/cấu hình tại một commit |
| App version | `2.7.0` | Phiên bản sản phẩm |
| Build ID | `ci-18421` | Một lần thực thi build |
| Migration ID | `JAVA-MIG-04` | Một bước trong kế hoạch |
| JAR SHA-256 | `sha256:...` | Nội dung byte của JAR |
| Image digest | `registry.example/app@sha256:...` | Manifest/container image cụ thể |
| Test run ID | `test-18421-jdk21` | Một lần chạy tests |
| Deployment ID | `prod-492` | Một lần triển khai |
| DB revision | `V034__expand_order.sql` | Mốc migration schema |

### 3.1. Tại sao chỉ lưu app version là nguy hiểm?

Hai pipeline có thể đều tạo `orders-2.7.0.jar` nhưng nội dung khác vì:

- Dependency snapshot/dynamic version đổi.
- JDK vendor/update hoặc compiler plugin đổi.
- Build có generated timestamp.
- Source tree có thay đổi chưa commit.
- Cấu hình build khác nhau.
- Một artifact được rebuild sau kiểm thử.
- Nhiều architecture được đóng gói bằng công cụ native khác nhau.

Vì vậy, **không dùng filename hoặc version label làm định danh duy nhất của một artifact**.

### 3.2. Quy tắc truy xuất

Một release record nên trả lời:

1. Build nào tạo artifact?
2. Source commit và dependency lock nào được dùng?
3. Checksum/digest của artifact là gì?
4. Test run nào đã kiểm thử checksum đó?
5. Configuration snapshot nào đã dùng trong test?
6. Deployment nào đã chạy chính artifact này?
7. Metrics và quyết định promote thuộc deployment nào?

Nếu thiếu một liên kết, hồ sơ mất một phần khả năng tái hiện.

## 4. Cấu trúc thư mục bằng chứng tham khảo

Một cấu trúc phù hợp cho CI/artifact storage:

~~~text
java-migration/
└── orders-service/
    └── JAVA-MIG-04/
        └── ci-18421/
            ├── manifest.yaml
            ├── artifacts/
            │   ├── orders.jar
            │   ├── orders.jar.sha256
            │   ├── sbom.json
            │   └── schema-migrations/
            ├── build/
            │   ├── toolchain.json
            │   ├── dependency-tree.txt
            │   ├── build-summary.txt
            │   └── source-revision.txt
            ├── config/
            │   ├── runtime-effective.redacted.yaml
            │   ├── jvm-flags.redacted.txt
            │   └── environment-metadata.json
            ├── tests/
            │   ├── unit/
            │   ├── integration/
            │   ├── contract/
            │   ├── runtime-matrix/
            │   └── performance/
            ├── deployment/
            │   ├── staging.yaml
            │   ├── canary.json
            │   └── promotion-decision.yaml
            └── checksums.sha256
~~~

Đây là cấu trúc minh họa. Trong hệ thống thực, các file có thể được lưu trong object storage, artifact repository, CI test reporting service và hệ quản lý release. Cần một **manifest trung tâm** chứa references để truy xuất.

### 4.1. Git, CI và artifact repository có trách nhiệm khác nhau

**Git** phù hợp với source, build scripts, config templates, lockfiles, migration SQL, manifest template và release policy.

**CI system** chạy build/test, tạo log và reports. Tuy nhiên CI logs có thể hết hạn theo retention hoặc bị xóa.

**Artifact repository/object storage** giữ binary và evidence cần truy xuất lâu dài, có quyền truy cập và version/retention policy.

Đừng nhồi những heap dumps, JFR recordings và hàng chục GB binary vào Git repository chỉ để “không mất lịch sử”.

### 4.2. Không ghi đè bằng đường dẫn latest

Các tên:

~~~text
artifacts/latest/app.jar
reports/latest/test.xml
~~~

có thể hữu ích làm pointer nhưng không đủ làm lưu trữ bất biến. Nên dùng path theo **migration step + build ID + artifact hash**; alias `stable` hoặc `last-known-good` chỉ trỏ tới những đối tượng này.

## 5. Manifest: một điểm vào của toàn bộ evidence

Ví dụ hồ sơ:

~~~yaml
schema_version: 1

application: orders-service

migration:
  id: "JAVA-MIG-04"
  title: "Chuyển runtime sang JDK 21"
  predecessor: "JAVA-MIG-03"
  stage: "STAGING"
  outcome: "PENDING"

source:
  commit: "EXACT_GIT_COMMIT"
  tag: "release/java-migration"

build:
  id: "ci-18421"
  tool: "Gradle Wrapper"
  tool_version: "EXACT_GRADLE_VERSION"
  compiler:
    vendor: "APPROVED_JDK_VENDOR"
    version: "EXACT_JDK_BUILD"
    release_target: 17
  runner_image: "EXACT_CI_IMAGE_DIGEST"

artifacts:
  jar:
    path: "artifacts/orders.jar"
    sha256: "EXACT_SHA256"
  container:
    image: "registry.example/orders@sha256:EXACT_DIGEST"
  sbom: "artifacts/sbom.json"

config:
  snapshot: "config/runtime-effective.redacted.yaml"
  jvm_flags: "config/jvm-flags.redacted.txt"
  secret_policy: "SECRET_VERSION_REFERENCES_ONLY"

tests:
  unit: "tests/unit/summary.yaml"
  integration: "tests/integration/summary.yaml"
  contract: "tests/contract/summary.yaml"
  runtime_matrix: "tests/runtime-matrix/results.yaml"
  performance: "tests/performance/summary.yaml"

deployment:
  record: "deployment/staging.yaml"
  promotion: "deployment/promotion-decision.yaml"
~~~

Mọi giá trị `EXACT_*` chỉ là placeholder; không công bố manifest này như bằng chứng thực nếu chưa được pipeline điền và kiểm chứng.

### 5.1. Manifest phải là ảnh chụp sự thật

Ví dụ compiler dùng JDK 21 với `--release 17`, staging dùng JDK 21, còn production dùng JDK 17 trong giai đoạn mixed-version. Đây là những trục khác nhau, phải ghi riêng.

Không dùng một trường `javaVersion: 21` nếu nó che mất khác biệt giữa **build JDK**, **target bytecode/API** và **runtime JDK**.

### 5.2. Đừng nhầm trạng thái test

Các trạng thái sau không giống nhau:

- `PASS`: chạy và đạt.
- `FAIL`: chạy và không đạt.
- `SKIPPED`: bị bỏ qua theo test runner.
- `NOT_RUN`: không chạy.
- `BLOCKED`: không thể chạy vì dependency/môi trường.
- `FLAKY`: có biến động hoặc retry.
- `TIMED_OUT`: quá hạn thời gian.

Một gate không được âm thầm chuyển `SKIPPED` thành `PASS` chỉ vì pipeline exit code là 0.

## 6. Lưu artifact nhị phân nguyên vẹn

Các artifact thường cần lưu:

- Main JAR/WAR/EAR hoặc plugin package.
- Native desktop installer.
- Custom JDK runtime image nếu ứng dụng phân phối cùng.
- Container image digest.
- SQL migration bundle.
- Generated classes khi chúng là phần của release.
- Dependency manifest/SBOM.
- Checksum hoặc chữ ký tương ứng.

### 6.1. Tính checksum

Trên shell có `sha256sum`:

~~~bash
sha256sum build/libs/orders.jar
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath "build\libs\orders.jar"
~~~

SHA-256 giúp kiểm tra hai byte streams có giống nhau. Nhưng **hash không tự chứng minh builder đáng tin, source đúng hay artifact đã qua kiểm thử**. Những bằng chứng đó phải đến từ CI provenance, test reports và verification policy.

### 6.2. Build một lần, promote cùng artifact

Cách rủi ro:

~~~text
Build A → Test A → Rebuild B → Deploy B
~~~

Dù A và B cùng Git commit, vẫn có thể khác binary.

Cách bền vững:

~~~text
Build Artifact A
       ├── Unit/Integration/Contract tests trên A
       ├── Security scan A
       ├── Staging deploy A
       └── Production promote A theo checksum/digest
~~~

Nếu một bước ký, đóng gói lại hoặc tạo native installer làm thay đổi bytes, đầu ra mới cũng cần **checksum và record** riêng.

### 6.3. Lưu cả failed build evidence

Nếu compile JDK mới làm fail do `IllegalAccessError`, vẫn cần lưu:

- Build ID và Git commit.
- JDK/compiler version.
- Error log đã loại dữ liệu nhạy cảm.
- Dependency versions.
- Cấu hình compiler/annotation processor.
- Failure classification và liên kết issue.

Không nên chỉ lưu các lần build thành công.

## 7. Container: tag không phải digest

Một container có thể được tham chiếu:

~~~text
registry.example/orders:2.7.0
~~~

Nhưng tag có thể bị thay đổi nếu registry/policy cho phép. Một tham chiếu theo digest rõ ràng hơn:

~~~text
registry.example/orders@sha256:IMAGE_MANIFEST_DIGEST
~~~

Ghi cả:

- Tag phát hành.
- Digest đang chạy.
- Application JAR checksum trong image.
- Base image digest.
- JDK vendor/update bên trong image.
- OS/architecture.
- Build ID và source commit.

### 7.1. Container image chứa nhiều hơn JAR

Hai image cùng JAR có thể khác:

- CA certificates.
- JDK runtime.
- OS shared libraries.
- Locale/timezone data.
- Entrypoint/JVM options.
- User permissions.
- Native drivers.

Vì vậy, khi tái hiện lỗi, **chỉ lưu JAR chưa đủ** nếu hệ thống chạy dưới container.

### 7.2. Đa kiến trúc

Một multi-arch image reference có thể trỏ tới image manifests riêng cho Linux amd64/arm64. Khi vấn đề chỉ xuất hiện trên một kiến trúc, cần ghi platform thực tế và digest phù hợp, không chỉ tag chung.

## 8. Lưu toolchain và build inputs

Để tái hiện một build Java, ghi:

- Git commit và submodule revisions.
- Maven/Gradle Wrapper version.
- Compiler JDK vendor, update, architecture.
- `--release`, `source`/`target`.
- Build plugins, annotation processors.
- Dependency graph và lockfiles.
- BOM/version catalogs.
- Native compilation tools nếu dùng JNI.
- Build runner image/OS.
- Relevant environment values đã redaction.
- Compiler flags, JPMS options.
- Generated source inputs.

### 8.1. Các lệnh thu thập minh họa

~~~bash
java -version
javac -version
git rev-parse HEAD
git status --porcelain
./gradlew --version
~~~

Hoặc với Maven:

~~~bash
mvn -version
mvn dependency:tree
~~~

Chạy các lệnh trong pipeline phù hợp, không coi chúng là phép kiểm chứng duy nhất. Một Gradle daemon có thể dùng JDK khác với `java` của shell; Java toolchain có thể chỉ định compiler JDK riêng.

### 8.2. Working tree bẩn

Nếu build từ file chưa commit, Git SHA không xác định đầy đủ source. Đối với release, nên dùng checkout sạch/immutable commit hoặc ghi rõ các thay đổi ngoài Git và quản lý quyền lưu trữ phù hợp.

### 8.3. Dependency động làm khó tái hiện

Dynamic ranges/SNAPSHOT có thể resolve khác theo thời điểm. Nên lưu versions đã resolve, lockfiles hoặc metadata xác thực dependency, không chỉ dòng cấu hình khai báo.

## 9. Maven: dependency và effective configuration

Một Maven build có thể thay đổi theo profiles, properties, plugins và dependency mediation.

Ví dụ thu thập báo cáo:

~~~bash
mvn -version
mvn dependency:tree
mvn help:effective-pom
~~~

`effective-pom` giúp thấy cấu hình đã tính toán nhưng có thể chứa dữ liệu nhạy cảm từ settings/profiles. **Không upload raw output công khai** nếu chưa redaction.

### 9.1. Cần lưu scope

Một dependency `provided` có thể có lúc compile nhưng không đi vào runtime JAR/WAR. Một dependency `test` không chứng minh production có provider tương ứng.

Lưu các thông tin:

- Compile/runtime/test dependency scopes.
- BOM versions.
- Dependency exclusions.
- Plugin versions.
- Profiles.
- Transitive dependency selection.

### 9.2. External server không nằm hoàn toàn trong dependency tree

Nếu deploy WAR lên application server, một số API/provider do server cấp. Maven dependency tree không thể mô tả toàn bộ runtime khi không biết server modules. Cần snapshot platform profile và version của server.

## 10. Gradle: configuration, toolchain và dependency resolution

Một số báo cáo:

~~~bash
./gradlew --version
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency example-library \
  --configuration runtimeClasspath
~~~

Các configuration thực tế phụ thuộc plugins/source sets. Nếu app có test fixtures hoặc custom annotation processors, thu thập thêm các reports tương ứng.

### 10.1. Lưu lockfiles và version catalogs

Version catalogs mô tả versions mong muốn; dependency resolution thực tế còn phụ thuộc constraints, platforms và transitive deps. Lưu:

- Resolved graph.
- Lockfiles khi bật dependency locking.
- Dependency verification metadata nếu dùng.
- Gradle Wrapper version.
- JVM chạy Gradle daemon.
- Java toolchain compiler version.
- Build cache policy nếu liên quan.

### 10.2. Build cache không phải kho release

Một cache entry có thể bị xóa hoặc có retention khác. Nó không nhất thiết chứa manifest, approval hay test evidence. Dùng artifact repository chuyên dụng để lưu release-critical outputs.

## 11. Cấu hình nguồn khác cấu hình hiệu lực

Ứng dụng thường nhận cấu hình qua nhiều lớp:

~~~text
application.yaml
  + profile-specific properties
  + environment variables
  + JVM -D options
  + command-line arguments
  + Kubernetes ConfigMaps / secrets
  + Helm/Kustomize overlays
  + remote feature flags
  + server/platform defaults
  = effective runtime configuration
~~~

Chỉ lưu `application.yaml` từ Git chưa đủ để biết production chạy với cài đặt nào.

### 11.1. Danh mục cấu hình

| Nhóm | Ví dụ | Cần lưu |
|---|---|---|
| Source config | Git-tracked templates | Commit và file reference |
| Deployment config | Rendered manifests | Snapshot đã redaction |
| Runtime config | Effective properties | Những giá trị ảnh hưởng migration |
| JVM config | GC/heap/module flags | Effective flags và origin |
| Feature flags | New API/serialization enabled | State tại thời điểm test/deploy |
| Server config | Servlet/JPA/TLS module versions | Platform/version/profile |
| External resources | Database/broker/cache | Engine version, schema revision |

### 11.2. Không dump secrets

Không lưu nguyên văn:

- Database password.
- API key.
- Access token.
- Signing key.
- Private TLS key.
- JWT signing secret.
- Full connection string có credentials.
- Command line có token.
- Heap dump chứa dữ liệu người dùng nếu không có kiểm soát riêng.

Ví dụ snapshot:

~~~yaml
database:
  endpoint: "INTERNAL_ENDPOINT_REFERENCE"
  schema_version: "V034"
  username: "REDACTED"
  password:
    secret_ref: "secret-manager/orders-db"
    version_ref: "APPROVED_SECRET_VERSION"

tls:
  truststore_ref: "approved-truststore-version"
  private_key: "NOT_EXPORTED"
~~~

Secret reference/version ID giúp truy xuất mà không nhân bản bí mật trong archive. Thậm chí endpoint cũng có thể nhạy cảm tùy policy tổ chức.

### 11.3. Không dùng hash password yếu để thay redaction

Một password ngắn bị hash vẫn có thể bị đoán. Hãy dùng secret-manager metadata phù hợp, không tự nghĩ ra cơ chế lưu secret.

## 12. JVM flags và runtime metadata

Các thông số quan trọng khi nâng JDK:

- `-Xms`, `-Xmx`, heap percentage.
- GC collector và tuning.
- `--add-opens`, `--add-exports`.
- `-Dfile.encoding`, timezone, locale.
- Java agents.
- TLS/security providers.
- Thread count, active processor count.
- Unified GC logging.
- `java.home`/runtime image reference.

### 12.1. Thu thập từ HotSpot runtime

Ví dụ lệnh (trên JVM hỗ trợ):

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
~~~

Khi chẩn đoán một JVM mới:

~~~bash
java -XX:+PrintCommandLineFlags -version
java -XX:+PrintFlagsFinal -version
java --list-modules
~~~

Không phải mọi JVM vendor dùng cùng diagnostic options. Không áp mẫu HotSpot cho OpenJ9 mà không xác minh.

### 12.2. GC thực tế có thể khác cấu hình suy đoán

Không có `UseG1GC` trong command line chưa chứng minh JVM không dùng G1. JVM có thể chọn default theo JDK/version/resources. Nên ghi collector **được chọn thực tế**, max heap/active CPU count và container limits.

### 12.3. Cần redaction trước upload

`VM.command_line` có thể chứa system properties nhạy cảm. Thu thập trong môi trường được phép, lọc secrets và không đưa toàn bộ nội dung lên log công khai.

## 13. Môi trường kiểm thử là một phần của kết quả

Cùng một JAR chạy khác nhau do:

- JDK vendor/update.
- OS distribution và CPU architecture.
- Container cgroup v1/v2, CPU/memory quotas.
- Filesystem permissions.
- Timezone, locale và charset.
- Native/JNI libraries.
- Database/driver version.
- Message broker/cache version.
- Application server/framework.
- TLS truststore/certificate.
- Feature flags.
- Background traffic/load.

Vì vậy, report test phải ghi ít nhất **environment ID** có thể giải được thành những thông số đó.

### 13.1. Không cần lưu toàn bộ máy ảo

Mục tiêu là lưu những thông tin ảnh hưởng tái hiện, không phải dump toàn bộ filesystem hoặc environment variables. Nếu cần bảo toàn một môi trường đầy đủ, immutable container/VM image digest và IaC/config version có thể phù hợp hơn.

### 13.2. Performance test phải khớp tài nguyên

Benchmark JDK 21 trên workstation 16 cores không so sánh trực tiếp với Java 17 trong pod quota 1 vCPU. Test record cần CPU limit, memory limit và workload profile.

## 14. Test reports cần có những trường nào?

Một test run có thể ghi:

~~~yaml
test_run:
  id: "test-18421-integration"
  build_id: "ci-18421"
  artifact_sha256: "EXACT_JAR_HASH"
  environment_id: "postgres-stage-2026-11"
  started_at: "ISO_8601_TIMESTAMP"
  elapsed_seconds: 172
  status: "PASS"

counts:
  passed: 248
  failed: 0
  skipped: 3
  aborted: 0

reports:
  junit_xml: "tests/integration/junit.xml"
  logs: "tests/integration/logs.redacted.txt"

notes:
  - "Ba test cases được skip theo policy, xem chi tiết"
~~~

Các con số minh họa, không phải kết quả thực tế.

### 14.1. Skipped và flaky test

Nếu test bị skip do thiếu database/HSM, không được ghi là PASS mà không có ngoại lệ rõ. Nếu một test fail ở attempt đầu rồi pass ở retry, cần lưu cả attempt thất bại và trạng thái flaky, không xóa dấu vết.

### 14.2. Đừng chỉ giữ một URL CI

CI job và logs có thể hết hạn. Với release-critical evidence, lưu bản export báo cáo và summary vào archive có retention phù hợp, liên kết tới CI job như thông tin bổ sung.

### 14.3. Test input và fixture

Một report không tái hiện được nếu dữ liệu nguồn đã thay đổi. Nên ghi dataset/fixture version và checksum nếu phù hợp; với dữ liệu production phải áp policy bảo vệ dữ liệu.

## 15. JUnit XML và raw test logs

JUnit XML thường được CI systems hỗ trợ, dù schema chi tiết phụ thuộc runner.

~~~xml
<testsuite name="OrderIntegrationTest"
           tests="3"
           failures="0"
           errors="0"
           skipped="1"
           time="1.82">
  <testcase classname="OrderIntegrationTest"
            name="createOrder" time="0.42"/>
  <testcase classname="OrderIntegrationTest"
            name="getOrder" time="0.31"/>
  <testcase classname="OrderIntegrationTest"
            name="requiresHardwareToken">
    <skipped message="Test environment unavailable"/>
  </testcase>
</testsuite>
~~~

Nên giữ:

1. Summary nhỏ để release gate đọc.
2. Raw JUnit XML/JSON để xem từng case.
3. Logs/stack traces liên quan khi thất bại.
4. Test runner/JDK version.
5. Link tới fixture và configuration.
6. Attempt/retry records.

### 15.1. HTML report và screenshot

HTML reports, UI screenshots hoặc HTTP captures có thể giúp debug nhưng cần quản lý quyền truy cập/retention. Nếu chứa dữ liệu khách hàng, cần redaction hoặc dữ liệu tổng hợp.

## 16. Các lớp kiểm thử trong Java migration

| Test class | Mục tiêu | Evidence nên lưu |
|---|---|---|
| Compile/build | JDK và compiler flags hợp lệ | Build log, toolchain report |
| Unit | Business logic | JUnit XML, coverage khi cần |
| Integration | DB/broker/framework/provider | Results, service versions |
| Contract | HTTP/event/gRPC compatibility | Contract files và verification |
| Binary/API | Public API compatibility | Bytecode/API diff |
| Runtime matrix | JDK baseline và target đều chạy | Per-JDK reports |
| Security | TLS, authentication, dependency scan | Scan summary và exception |
| Performance | Throughput/latency/heap/GC | Raw metrics, GC logs, config |
| Deployment | Startup, canary, rolling, rollback | Deployment records |
| Data migration | Schema/backfill consistency | Revision, row counts, checks |
| Soak/resilience | Long-running reliability | Metrics, logs, incident triggers |

Không thể chỉ có unit tests rồi coi tất cả những nhóm còn lại đều được kiểm chứng.

## 17. Multi-JDK test matrix

Giả sử build bằng JDK 21 với `--release 17` và sản phẩm tuyên bố chạy được trên JDK 17/21:

| Artifact | Runtime | Test | Evidence |
|---|---|---|---|
| Hash A | JDK 17 update X | Unit | Report J17 |
| Hash A | JDK 21 update Y | Unit | Report J21 |
| Hash A | JDK 17 update X | Integration | DB/HTTP J17 |
| Hash A | JDK 21 update Y | Integration | DB/HTTP J21 |
| Hash A | Production-like image | Startup/performance | Runtime report |

`--release` hạn chế API/bytecode của source được compile nhưng **không chứng minh** mọi third-party dependency và provider đều chạy trên runtime thấp nhất. Vì vậy phải test runtime thật.

### 17.1. Multi-Release JAR

Nếu artifact chứa `META-INF/versions/*`, các runtime có thể nạp implementation khác nhau. Cần test những JDK supported thay vì chỉ thử JDK dùng để compile.

### 17.2. Mỗi artifact phải gắn với test riêng

Nếu pipeline build artifacts khác nhau cho x64/ARM64 hoặc các release channels, không trộn kết quả của Hash A sang Hash B mà không ghi rõ.

## 18. Lưu compatibility reports của API và framework

Khi nâng dependency hoặc chuyển `javax.*` sang `jakarta.*`, public method descriptors có thể đổi.

Ví dụ:

~~~java
public void register(javax.servlet.Filter filter);
~~~

sau đó:

~~~java
public void register(jakarta.servlet.Filter filter);
~~~

Đây là hai binary type names khác nhau, gây rủi ro cho consumer đã compile.

Có thể kiểm tra descriptors:

~~~bash
javap -classpath previous.jar -p -s com.example.PublicApi
javap -classpath candidate.jar -p -s com.example.PublicApi
~~~

Ngoài text diff, nên dùng công cụ API compatibility phù hợp nếu library có cam kết binary contract.

### 18.1. Lưu cả các lớp compatibility

~~~yaml
compatibility:
  source: "PASS_OR_REVIEW"
  binary_api: "PASS_OR_REVIEW"
  http_contract: "PASS_OR_REVIEW"
  event_schema: "PASS_OR_REVIEW"
  database_schema: "PASS_OR_REVIEW"
  runtime_behavior: "PASS_OR_REVIEW"
~~~

Một HTTP service có thể giữ wire contract dù dùng Java/Jakarta generation khác, nhưng trong cùng JVM classloader, binary name mismatch vẫn là vấn đề khác.

### 18.2. Consumer/provider versions

Trong rolling deployment, provider mới cần giữ contract của consumer cũ; producer mới có thể gửi dữ liệu đến consumer cũ. Lưu matrix kết quả **V1→V2 và V2→V1** khi topology cho phép.

## 19. Lưu DB schema và data migration evidence

Một schema migration có thể đi theo:

~~~mermaid
flowchart TD
    A["Schema S1, app V1"] --> B["Expand S2: bổ sung cột/bảng"]
    B --> C["V1 vẫn đọc/ghi S2"]
    C --> D["V1/V2 cùng chạy"]
    D --> E["Backfill và data verification"]
    E --> F["Rút hết consumer cũ"]
    F --> G["Contract S3: xóa cấu trúc cũ"]
~~~

Ở mỗi bước nên lưu:

- Migration scripts và checksum.
- DB engine/version.
- Revision trước/sau.
- Migration execution ID.
- Row counts, constraint checks.
- Backfill job version.
- Lock/transaction impact.
- Test V1/V2 cùng schema.
- Backup/snapshot reference.
- Rollback boundaries.

### 19.1. Không đưa dữ liệu production thô vào artifact store

Thay vì upload database dump chứa PII, lưu aggregate validation metrics, migration revision, snapshot reference và báo cáo redacted. Nếu cần giữ dump, phải dùng kho restricted có encryption, audit và retention được duyệt.

### 19.2. Rollback schema và rollback app không giống nhau

V2 có thể đã ghi dạng dữ liệu mới; V1 sau rollback có thể không hiểu. Cần test và ghi rõ trạng thái `ROLLBACK_SAFE` hoặc `ROLL_FORWARD_ONLY`, cùng lý do và phương án khôi phục.

## 20. Performance evidence phải có dữ liệu gốc

Nâng JDK có thể thay GC default, JIT, classloading, threading và memory footprint. Performance report nên ghi:

- Artifact hash và JDK update/vendor.
- GC collector, heap flags.
- CPU/memory limits, container image.
- Dataset/workload và concurrency.
- Warmup duration.
- Measurement duration/repetitions.
- Throughput.
- p50/p95/p99/max latency.
- Error/timeout rate.
- CPU, throttling, RSS/native memory.
- GC pause histogram/GC log.
- Dependencies như DB/network.

### 20.1. Không chỉ lưu PNG biểu đồ

Ảnh biểu đồ hỗ trợ trình bày, nhưng không cho phép tái tính phân vị hoặc lọc outliers. Cần giữ **raw measurements** (CSV/JSON/Parquet phù hợp), script/config tạo biểu đồ và summary.

### 20.2. Summary mẫu

~~~yaml
benchmark:
  artifact_sha256: "EXACT_HASH"
  jdk: "EXACT_JDK_BUILD"
  collector: "G1"
  workload: "orders-load-profile"
  warmup_minutes: 10
  measurement_minutes: 20
  metrics:
    throughput_rps: 2500
    p99_ms: 180
    error_rate_pct: 0.1
  raw_data: "tests/performance/requests.csv"
  gc_log: "tests/performance/gc.redacted.log"
~~~

Các số liệu chỉ mang tính minh họa.

### 20.3. So sánh đúng môi trường

Nếu baseline chạy trên CPU lớn hơn candidate, việc so sánh p99 không công bằng. Ghi đầy đủ test environment và sử dụng cùng workload, warmup, resource profile khi có thể.

## 21. Lưu JDK internals/JPMS compatibility results

Các bài toán migration có thể yêu cầu loại bỏ:

- `sun.*`/`com.sun.*` internal API usage.
- Reflection vào non-public JDK packages.
- `--add-opens`/`--add-exports` workaround.
- Modules đã bị loại khỏi JDK.
- Third-party agents/bytecode tools không hỗ trợ classfile mới.

Những bằng chứng hữu ích:

~~~bash
jdeps --jdk-internals --recursive --class-path "lib/*" app.jar
jdeps --print-module-deps --class-path "lib/*" app.jar
java --list-modules
~~~

`jdeps` phân tích tham chiếu tĩnh, không thấy mọi reflection string hoặc dynamic loading. Lưu output để xác định thay đổi, nhưng vẫn cần integration tests.

### 21.1. Theo dõi module flags theo bước

Ví dụ:

~~~text
Step A: 5 module-access workarounds
Step B: nâng thư viện => còn 3
Step C: nâng framework => còn 1
Step D: xóa workaround cuối => 0
~~~

Cần ghi **tên flag, lý do, owner và test chứng minh có thể bỏ**, không chỉ số lượng.

## 22. Lưu kết quả canary và production rollout

Khi deploy, cần record:

- Deployment ID.
- Environment/cluster/namespace.
- Artifact/image digest.
- JDK runtime image.
- Effective non-secret configuration.
- Feature flags.
- Schema migration revision.
- Canary percentage và routing rule.
- Readiness/health status.
- Error rate, latency, CPU/RSS/GC.
- Incident/alert timeline.
- Promotion/hold/rollback decision.

### 22.1. Một build có nhiều deployments

~~~text
ci-18421 => artifact Hash A
  ├── staging-231 => PASS
  ├── canary-prod-232 => HOLD
  └── canary-prod-233 => PASS sau config adjustment
~~~

Nếu config đã đổi giữa các deployments, đó là biến đầu vào cần được lưu. Không mặc định lần deploy mới là build mới.

### 22.2. Canary nhỏ vẫn tạo tác động toàn hệ thống

Một canary chỉ nhận 5% HTTP traffic có thể phát event vào shared broker hoặc cập nhật shared database cho mọi consumer. Do đó, quan sát cần có metrics theo version và cả những hệ thống dùng shared state.

## 23. Gắn quyết định release vào tiêu chí kiểm thử

Mẫu promotion decision:

~~~yaml
promotion:
  artifact_digest: "sha256:EXACT_HASH"
  build_id: "ci-18421"
  from: "staging"
  to: "production-canary"
  decision: "APPROVED"
  decided_at: "ISO_8601_TIMESTAMP"

gates:
  compile: "PASS"
  unit: "PASS"
  integration: "PASS"
  contract: "PASS"
  performance: "PASS"
  security: "PASS"

exceptions:
  - id: "WAIVER-123"
    status: "APPROVED_WITH_EXPIRY"
    owner: "Responsible team"
    reason: "Documented exception"

approval:
  role: "AUTHORIZED_RELEASE_ROLE"
  evidence_manifest: "manifest.yaml"
~~~

Không được ghi `APPROVED` nếu chưa có approval thực. Mẫu chỉ minh họa schema.

### 23.1. Waiver phải rõ ràng

Khi một test/gate chưa thể đạt:

- Ghi test cụ thể.
- Lý do.
- Rủi ro.
- Người chịu trách nhiệm.
- Điều kiện bù đắp.
- Hạn xử lý.
- Ai phê duyệt.
- Có được promote hay không.

Không bật cấu hình bỏ qua test rồi xóa dấu vết khỏi report.

## 24. Rollback cần cả binary, config và state

Một hồ sơ rollback đúng có:

1. Last-known-good artifact checksum/digest.
2. Runtime image/JDK version.
3. Effective configuration snapshot.
4. Feature flag state.
5. Database/schema compatibility.
6. Queue/session/cache format.
7. Runbook rollback.
8. Rehearsal evidence.
9. Rollback triggers/decision owner.

~~~yaml
rollback:
  from_deployment: "prod-492"
  target_artifact: "sha256:LAST_KNOWN_GOOD_HASH"
  runtime_image: "registry.example/runtime@sha256:EXACT_DIGEST"
  config_snapshot: "config/last-known-good.redacted.yaml"
  database_compatibility: "VERIFIED_WITH_CURRENT_SCHEMA"
  rehearsal: "tests/deployment/rollback-report.xml"
  operator_runbook: "APPROVED_RUNBOOK_ID"
  status: "READY_FOR_APPROVAL"
~~~

Một artifact cũ chưa chắc chạy được với schema mới. Khi rollback không an toàn, cần phương án roll-forward, adapter, backup/restore hoặc maintenance window.

### 24.1. Rollback cũng là một test

Test nên mô phỏng:

~~~text
Deploy V1
-> Apply compatible schema expand
-> Deploy V2
-> V2 writes data/events
-> Rollback to V1
-> V1 reads/writes without corrupting data
~~~

Lưu cả test run, artifact hashes và schema revision.

## 25. Bảo vệ thông tin trong kho artifact/evidence

Những hồ sơ này có thể chứa dữ liệu nhạy cảm:

- Internal endpoints và network topology.
- Dependency vulnerabilities.
- Access tokens/passwords trong log.
- PII trong HTTP captures.
- Heap/JFR recordings.
- Signing-related metadata.
- Chứng chỉ và thông tin khách hàng.

Cần áp dụng:

- Access control theo role.
- Encryption at rest/in transit.
- Audit access/mutations.
- Redaction trước upload.
- Retention phù hợp.
- Backup/restore.
- Immutable object/versioning khi có hỗ trợ.
- Tách public binaries khỏi restricted diagnostics.
- Không đặt raw dumps vào public CI artifacts.

### 25.1. Phân loại theo độ nhạy

| Loại | Ví dụ | Quản lý |
|---|---|---|
| Public release | Installer công bố, public checksum | Xuất bản sau phê duyệt |
| Internal build | Binary thử nghiệm, dependency graph | Quyền nội bộ |
| Restricted diagnostics | Logs có PII, JFR | Quyền giới hạn, retention cụ thể |
| Highly sensitive | Heap dump, key material | Tránh thu trừ khi cần; kho kiểm soát đặc biệt |

Không tự suy luận rằng một file có tên `gc.log` chắc chắn vô hại.

### 25.2. Secret references thay values

Khi cần tái hiện, ghi **secret version ID** từ secret manager thay vì ghi giá trị. Đừng dùng hash tùy tiện của password làm bản thay thế an toàn.

## 26. Retention policy: không phải lưu vô thời hạn

Các loại cần giữ lâu hơn thường là:

- Production artifact và checksum.
- Release/provenance manifest.
- Test gate summaries.
- Deployment/approval records.
- Last-known-good binaries/configs.
- Schema migration scripts và references.
- Incident evidence đang mở.

Các loại có thể có thời gian ngắn hơn:

- Experimental builds.
- Verbose compiler logs.
- Repeated performance raw captures.
- Failed temp artifacts không phục vụ điều tra.
- High-volume debug logs.

Thời hạn cụ thể tùy policy pháp lý, bảo mật, ngân sách và yêu cầu rollback. Không nên chọn một số ngày chung cho mọi dự án.

### 26.1. Cần thử khả năng khôi phục

Một policy archive tốt không chỉ nói “đã upload” mà cần kiểm tra:

- File có thể đọc lại.
- Checksum còn khớp.
- Reference trong manifest không chết.
- Người trực vận hành có quyền truy cập khi cần.
- Backup/replica còn hoạt động.
- Retention không xóa last-known-good quá sớm.

## 27. Mutable pointers và immutable evidence

Một dashboard có thể trỏ:

~~~text
stable -> ci-18421 / sha256 A
canary -> ci-18429 / sha256 B
last-known-good -> ci-18410 / sha256 Z
~~~

Các pointers có thể thay đổi khi promote, nhưng A/B/Z cần là các đối tượng có ID bất biến.

Nếu kho lưu cho phép overwrite cùng tọa độ, cần policy khóa/kiểm soát để tránh sửa lịch sử mà không audit trail.

### 27.1. Signed metadata và attestation

Build provenance/signature có thể chứng minh builder, source và artifact digest theo chính sách. Nhưng phải kiểm tra:

- Chữ ký thuộc identity nào?
- Artifact digest được ký là gì?
- Trust root/verification policy nào áp dụng?
- Provenance mô tả input/build step có đúng không?
- Deployment gate có verify hay chỉ lưu file chữ ký?

Lưu signature mà không có cách xác minh không đảm bảo chuỗi phát hành an toàn.

## 28. Reproducibility: cùng source chưa chắc cùng bytes

Artifact có thể khác do:

- ZIP/JAR timestamps.
- Thứ tự file.
- Generated source timestamps.
- Build paths.
- Dependency versions động.
- JDK/OS/toolchain.
- Locale/timezone.
- Native build tools.
- Signing timestamps.
- Đóng gói platform-specific.

### 28.1. Reproducible build và runtime khác nhau

Build tái tạo cùng bytes không có nghĩa production behavior như cũ nếu JDK, DB, config hoặc traffic khác.

Ngược lại, khi native installer bắt buộc có timestamp mới và checksum đổi, cần ghi mapping giữa signed/unsigned artifact, provenance và test evidence; không cố sửa hash để nhìn giống nhau.

## 29. Script minh họa thu thập bằng chứng

Một skeleton shell cho pipeline Linux sau build/test:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

STEP_ID="JAVA-MIG-04"
BUILD_ID="ci-18421"
ROOT="evidence/$STEP_ID/$BUILD_ID"

mkdir -p "$ROOT/artifacts" "$ROOT/build" "$ROOT/tests"

cp build/libs/orders.jar "$ROOT/artifacts/orders.jar"

git rev-parse HEAD > "$ROOT/build/source-commit.txt"
java -version 2> "$ROOT/build/java-version.txt"
javac -version 2> "$ROOT/build/javac-version.txt"
./gradlew --version > "$ROOT/build/gradle-version.txt"

sha256sum "$ROOT/artifacts/orders.jar" \
  > "$ROOT/artifacts/orders.jar.sha256"

# Sao chép JUnit output nếu test runner đã tạo.
cp -R build/test-results/test "$ROOT/tests/unit"

# Bước tiếp theo của pipeline thực:
# tạo manifest, redact dữ liệu nhạy cảm,
# xác minh required evidence và upload bất biến.
~~~

Đây **không phải script production hoàn chỉnh**. Nó dùng IDs cố định và chưa kiểm soát quyền, source cleanliness, redaction, retention hay upload/readback. Những phần đó cần tự động hóa khi áp dụng thực tế.

### 29.1. PowerShell checksum

~~~powershell
$artifact = "build\libs\orders.jar"
$hash = Get-FileHash -LiteralPath $artifact -Algorithm SHA256
$hash.Algorithm
$hash.Hash
~~~

Dù CI chạy trên Windows hay Linux, nên ghi checksum vào một manifest schema thống nhất.

### 29.2. Đừng mất evidence nếu test thất bại

Trong CI, hãy cấu hình bước upload/archiving phù hợp để giữ logs/reports ngay cả khi tests fail, nhưng tuyệt đối không để logic upload biến một bước test thất bại thành release PASS.

## 30. Pipeline có evidence gate theo từng migration step

~~~mermaid
flowchart TD
    A["Bước N: scope + acceptance criteria"] --> B["Chụp source/build inputs"]
    B --> C["Build binary bất biến"]
    C --> D["Hash + manifest"]
    D --> E["Chạy unit/integration/contract/runtime tests"]
    E --> F["Archive reports và config đã redact"]
    F --> G{"Required gates đạt?"}
    G -->|Không| H["HOLD, lưu failed evidence"]
    H --> A
    G -->|Có| I["Deploy staging/canary cùng digest"]
    I --> J["Lưu runtime telemetry"]
    J --> K{"SLO và invariants đạt?"}
    K -->|Có| L["Promote và giữ rollback artifacts"]
    K -->|Không| M["Rollback/hold và incident record"]
    L --> N["Bước N+1"]
~~~

### 30.1. Không tự tái build trước production

Artifact được test ở staging nên được promote theo checksum/digest. Nếu rebuild là bắt buộc, phải tạo release record và verify tương ứng cho binary mới.

### 30.2. Tách test gate và evidence upload

Khi test fail, archive vẫn có thể thành công. Pipeline cần phản ánh:

~~~text
TEST_STATUS=FAIL
EVIDENCE_ARCHIVE_STATUS=SUCCESS
RELEASE_GATE=BLOCKED
~~~

Đây là trạng thái hợp lệ; không báo release PASS chỉ vì bằng chứng đã lưu được.

## 31. Ví dụ migration Java 11 sang 21 nhiều giai đoạn

Giả sử ứng dụng Orders chuyển từ Java 11 lên 21.

### Step A — Nâng build tool, giữ target Java 11

~~~text
Compiler JDK: 21
Compiler --release: 11
Runtime matrix: Java 11 và Java 21
Framework: chưa đổi
~~~

Lưu:

- Gradle/Maven Wrapper và plugins.
- Compiler flags/toolchain.
- Artifact hash A.
- Unit/integration test report trên hai runtime.
- Dependency lockfiles.
- New compiler warnings.

### Step B — Nâng dependencies, loại internal API

~~~text
Compiler JDK: 21
Compiler --release: 17
Updated libraries
Giảm các --add-opens/--add-exports workarounds
~~~

Lưu:

- Dependency graph diff.
- `jdeps` report.
- Public API diff.
- Runtime flags trước/sau.
- Artifact hash B và test results.

### Step C — Nâng framework/Jakarta

~~~text
Framework: thế hệ hỗ trợ JDK mới
Servlet/JPA: jakarta.* nếu framework yêu cầu
Application server: generation phù hợp
~~~

Lưu:

- WAR/container digest.
- Provider/server version.
- HTTP/API consumer contract tests.
- DB migration compatibility.
- Annotation processor/generated source configuration.
- Mixed-version V1/V2 test results.

### Step D — Runtime Java 21 và canary

~~~text
Runtime JDK: exact approved update
GC: verified actual collector
Deployment: staged canary
~~~

Lưu:

- Runtime image digest.
- Effective JVM flags/heap.
- GC logs và benchmark.
- Canary metrics và decision.
- Rollback rehearsal.
- Production deployment record.

### 31.1. Bảng theo dõi mẫu

| Step | Artifact | Test gate | Deploy gate | Quyết định |
|---|---|---|---|---|
| A | Hash A | PASS | PASS | Tiếp tục |
| B | Hash B | PASS | PASS | Tiếp tục |
| C | Hash C | PASS | HOLD | Điều tra |
| C2 | Hash D | PASS | PASS | Tiếp tục |
| D | Hash E | PASS | PASS | Promote |

Đây là ví dụ về cấu trúc theo dõi, không phải kết quả chạy thật. Mỗi `PASS`/`HOLD` phải trỏ đến report cụ thể.

### 31.2. Giữ bước thất bại để điều tra

Nếu Step C đầu thất bại vì Hibernate/provider không cùng Jakarta generation, hồ sơ Hash C và stack traces giúp chứng minh thay đổi sửa lỗi ở C2 thay vì đoán lại từ đầu.

## 32. Bảng so sánh hai bước chuyển đổi

| Thuộc tính | Bước N | Bước N+1 | Lý do cần kiểm tra |
|---|---|---|---|
| Compiler JDK | JDK A | JDK B | Javac/plugins khác? |
| `--release` | 11 | 17 | Bytecode/API baseline đổi |
| Dependency lock | Lock A | Lock B | Thư viện nào được nâng? |
| Runtime image | Digest A | Digest B | OS/JDK/TLS khác? |
| GC | Parallel | G1 | Default/explicit behavior |
| Heap limit | 2 GiB | 2 GiB | Có cùng memory budget? |
| Unit tests | Report A | Report B | New failure/skip? |
| Integration tests | Report A | Report B | DB/framework changes |
| Contract tests | Report A | Report B | Consumer compatibility |
| p99 latency | Metric A | Metric B | So sánh cùng workload? |
| API binary | Baseline | Candidate | Method descriptors thay? |
| DB revision | V33 | V34 | Code cũ đọc được không? |

Bảng không tự chứng minh nhân quả. Nó chỉ đưa ra **những biến đã thay đổi** để điều tra có hệ thống.

## 33. Khi thiếu bằng chứng: ghi rõ thay vì suy đoán

Có thể một test cần HSM, external database hoặc multi-region setup chưa sẵn sàng. Quy trình đúng:

1. Ghi test ID.
2. Ghi trạng thái `NOT_RUN`/`BLOCKED`.
3. Ghi lý do.
4. Ghi rủi ro.
5. Ghi owner.
6. Ghi điều kiện để được promote.
7. Có waiver nếu chính sách cho phép.
8. Không gắn nhãn PASS giả.

Ví dụ:

~~~yaml
exception:
  gate: "hardware-hsm-integration"
  result: "NOT_RUN"
  reason: "Approved HSM test environment unavailable"
  risk: "Hardware signing behavior unverified"
  owner: "Security integration team"
  mitigation: "Block production promotion until this suite runs"
  decision: "HOLD"
~~~

Báo cáo trung thực với khoảng trống rõ còn giá trị hơn báo cáo toàn PASS mà không có test evidence.

## 34. Điều tra production regression từ hồ sơ lưu trữ

Giả sử một số pod sau nâng JDK phát sinh `NoSuchMethodError`.

Một hệ thống evidence tốt cho phép:

1. Lấy deployment/pod image digest.
2. Tìm JAR checksum thuộc image.
3. Mở build manifest.
4. Xem dependency graph và toolchain.
5. So sánh public API class descriptors với last-known-good.
6. Xem API/provider thực tế được nạp từ server.
7. Xem test suite đã hoặc chưa bao phủ flow đó.
8. Quyết định rollback/roll-forward.
9. Lưu incident summary và bổ sung regression test.

Nếu chỉ còn tag `latest`, việc xác định binary gây lỗi có thể không còn chắc chắn.

### 34.1. Dữ liệu chẩn đoán nhạy cảm

Heap dump, memory snapshot, thread dump và HTTP captures cần privacy/security policy riêng. Chỉ thu khi thật sự cần, có quyền hạn hẹp và retention phù hợp.

## 35. Sai lầm thường gặp

### 35.1. “Có Git commit là tái tạo được artifact”

Chưa đủ nếu JDK, dependency, plugin hoặc container base không được khóa.

### 35.2. “Version name đủ để nhận diện JAR”

Cùng version label có thể có bytecode khác nhau.

### 35.3. “Đã có CI PASS nên không cần lưu test report”

Không biết test nào thực sự chạy, bị skip hay flaky.

### 35.4. “Source configuration là effective configuration”

Có thể bị override bởi Helm, env, JVM flags và remote config.

### 35.5. “Lưu mọi environment variable là tốt nhất”

Rất dễ lộ secrets; chỉ ghi metadata cần thiết và redaction.

### 35.6. “Chỉ cần archive các build thành công”

Failure logs giúp tìm regression ở bước đầu tiên.

### 35.7. “Rebuild cùng commit rồi deploy sẽ giống bản đã test”

Không bảo đảm byte-for-byte, nhất là dynamic dependencies và native packaging.

### 35.8. “Container tag latest là bất biến”

Không phải trong mọi registry; nên dùng digest.

### 35.9. “Chỉ giữ performance chart PNG”

Cần raw data, workload và runtime config để tái tính.

### 35.10. “Rollback chỉ cần container image cũ”

Database, event/session state và config có thể không còn tương thích.

### 35.11. “Artifact upload thành công nghĩa là mãi mãi truy xuất được”

Retention, quyền truy cập và corruption vẫn cần quản lý.

### 35.12. “Càng giữ lâu càng tốt”

Không với dữ liệu nhạy cảm; cần policy theo giá trị và rủi ro.

### 35.13. “Mọi skipped test là PASS”

Không. Những khoảng trống cần quyết định rõ.

### 35.14. “Có chữ ký số là có đầy đủ provenance”

Cần verification identity, builder, artifact digest và policy.

### 35.15. “Canary chỉ cần xem tổng error rate”

Một canary nhỏ có lỗi lớn có thể bị che bởi tổng fleet; cần phân loại theo version.

## 36. Checklist cho mỗi bước migration

### Source và build

- [ ] Có migration step ID, mục tiêu, acceptance criteria.
- [ ] Có Git commit và trạng thái source sạch.
- [ ] Có build ID và timestamp.
- [ ] Ghi compiler JDK vendor/update và `--release`.
- [ ] Ghi build plugin/Wrapper versions.
- [ ] Có resolved dependencies/lockfiles/SBOM khi cần.
- [ ] Ghi artifact checksum và container digest.
- [ ] Không rebuild âm thầm giữa test và deploy.

### Cấu hình

- [ ] Ghi effective non-secret config.
- [ ] Ghi JVM flags/GC/heap/JPMS options.
- [ ] Ghi server/framework/provider versions.
- [ ] Ghi OS/CPU/memory/container limits.
- [ ] Ghi feature flags.
- [ ] Redact secrets/PII.
- [ ] Có secret references thay vì secret values.

### Kiểm thử

- [ ] Lưu unit test report.
- [ ] Lưu integration tests.
- [ ] Lưu API/event contract tests khi liên quan.
- [ ] Lưu JDK/runtime test matrix.
- [ ] Lưu binary/API diff nếu có public changes.
- [ ] Lưu performance raw data và config nếu có SLO risk.
- [ ] Ghi skipped/failed/flaky/not-run tests.
- [ ] Mọi report trỏ tới đúng artifact và environment.

### Deployment và rollback

- [ ] Lưu staging/canary deployment ID.
- [ ] Xác nhận digest thực chạy.
- [ ] Có promotion/hold/rollback decision.
- [ ] Ghi runtime metrics/alerts.
- [ ] Có last-known-good artifact/config.
- [ ] DB/schema/state compatibility đã được đánh giá.
- [ ] Có rollback rehearsal evidence khi yêu cầu.
- [ ] Kho archive có retention/access policy và readback verification.

## 37. Checklist dành cho người phê duyệt

Trước khi promote, cần trả lời được:

1. **Artifact nào sẽ được đưa vào production?** Có checksum/digest?
2. **Artifact đó được build từ source commit nào?**
3. **JDK biên dịch, target release và runtime JDK là gì?**
4. **Dependency và config khác baseline ở đâu?**
5. **Test suite nào đã chạy?** Test nào bị skip/waive?
6. **Có bằng chứng contract, database, runtime compatibility không?**
7. **Performance SLO và security gates có đạt không?**
8. **Staging/canary có sử dụng chính digest này không?**
9. **Rollback về artifact/config nào?** DB/state có cho phép?
10. **Evidence có thể truy xuất về sau theo retention policy không?**

Nếu không trả lời được những câu hỏi cốt lõi, pipeline xanh chưa đủ để tuyên bố bước chuyển đổi an toàn.

## Kết luận

**Mỗi bước nâng cấp Java phải để lại một hồ sơ truy xuất được**: source commit, toolchain, resolved dependencies, artifact bất biến và checksum, cấu hình hiệu lực đã redaction, báo cáo kiểm thử, deployment record, quyết định promote/hold/rollback và bằng chứng theo dõi runtime.

Chiến lược bền vững là **build một lần, test chính artifact đó, promote theo digest, lưu manifest liên kết mọi evidence, giữ last-known-good cùng cấu hình và đánh giá rollback của state/schema**. Kết hợp quyền truy cập, retention, signing/provenance và kiểm tra readback sẽ biến lịch sử migration thành công cụ vận hành thực tế: có thể tái hiện lỗi, đối chiếu từng bước, giải thích quyết định và khôi phục khi JDK mới gây regression.

