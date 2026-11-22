# Tạo SBOM và kiểm soát nguồn gốc artifact

Một tổ chức triển khai dịch vụ Java/Spring Boot lên Azure Kubernetes Service (AKS). Ứng dụng sử dụng Maven, vài thư viện Azure SDK, một image nền Java, nhiều dependency bắc cầu và container image được đẩy lên Azure Container Registry (ACR). Một ngày, nhóm bảo mật nhận thông báo lỗ hổng trong một thư viện JSON. Nhóm phát triển kiểm tra pom.xml nhưng không thấy thư viện đó: nó có thể được kéo vào qua dependency bắc cầu, nằm trong thư viện đóng gói lại hoặc trong một thành phần của container image. Ngay cả khi tìm ra dependency, câu hỏi tiếp theo là: **image đang chạy có thực sự được tạo từ commit đã duyệt, bằng pipeline được tin cậy và chưa bị thay thế sau khi build hay không?**

Hai nhóm bằng chứng giúp giải quyết các câu hỏi này:

- **Software Bill of Materials (SBOM):** danh mục thành phần, phiên bản, quan hệ phụ thuộc và metadata của phần mềm/artifact.
- **Artifact provenance:** bằng chứng về xuất xứ của artifact: nó được tạo từ nguồn nào, bởi builder/pipeline nào, trong hoàn cảnh nào và liên kết thế nào với output có digest cụ thể.

Bài thuộc chương **CI/CD và chuỗi cung ứng phần mềm** của mô-đun **CLOUD_PROVIDERS_AZURE**. Mô-đun khám phá Microsoft Azure từ subscription, resource group và Microsoft Entra ID tới mạng ảo, compute, storage và dữ liệu, đồng thời hướng dẫn triển khai, giám sát, bảo vệ và kiểm soát chi phí ứng dụng trên Azure. Ở đây ta gắn SBOM/provenance với Git, Maven/Gradle, Azure DevOps hoặc GitHub Actions, Azure Container Registry, Microsoft Defender for Cloud, Azure Key Vault và workload trên AKS, Azure Container Apps hoặc App Service.

**Nguyên tắc trọng tâm:** SBOM trả lời “bên trong phần mềm có những gì?”, provenance trả lời “artifact này đến từ đâu, được tạo thế nào?”, còn chữ ký/attestation và policy verification giúp quyết định “ta có đủ cơ sở tin artifact này để triển khai hay không?”. **Không công cụ đơn lẻ nào bảo đảm phần mềm không chứa lỗ hổng hoặc mã độc.**

> **Phạm vi và phiên bản:** Ví dụ là minh họa cho Java, container và Azure. Cú pháp/khả năng của CycloneDX Maven plugin, Syft, Cosign, ORAS, Docker Buildx, Azure CLI, ACR, Azure DevOps, GitHub Actions, SLSA và admission controllers có thể thay đổi. Không coi tên plugin, định dạng, mức SLSA hoặc flags là bản hỗ trợ mới nhất; phải đối chiếu tài liệu của đúng phiên bản và chính sách tổ chức. Các lệnh build/push/sign trong bài có thể tạo hoặc thay đổi artifacts và phát sinh phí; chỉ thực hiện trong môi trường lab được phê duyệt. Không có lệnh nào được chạy trong quá trình biên soạn tài liệu này.

## Mục tiêu học tập

Sau bài, người học có thể:

1. Phân biệt **SBOM, dependency lockfile, vulnerability report, license report, checksum, digital signature, provenance và attestation**.
2. Hiểu **CycloneDX** và **SPDX**, các trường component identity, package URL (purl), hash, dependency relationships.
3. Tạo SBOM cho **Maven multi-module**, Gradle hoặc **OCI container image**, biết giới hạn khả năng phát hiện.
4. So sánh **source-level, build-resolved, binary-level và image-level SBOM**.
5. Giải thích **tag vs immutable digest**, OCI image manifest, image index và multi-platform builds.
6. Gắn SBOM/provenance với **đúng artifact digest** trong ACR.
7. Mô tả **SLSA provenance**, build identity, source revision, builder identity, workflow và attestation predicate.
8. Phân biệt ký artifact/attestation bằng **Cosign/Sigstore** với việc chỉ tạo file checksum.
9. Xây pipeline Azure DevOps hoặc GitHub Actions có nguyên tắc **OIDC/workload identity federation, least privilege và builder isolation**.
10. Thiết kế verify gates trong CI/CD và AKS admission phù hợp policy, kèm rollback và break-glass có kiểm toán.
11. Dùng SBOM để đánh giá **CVE, license, dependency reachability và incident response**, không nhầm vulnerability scan với provenance.
12. Xây checklist vận hành, thực hành an toàn và tình huống truy vết artifact từ AKS về Git commit.

## 1. Chuỗi cung ứng phần mềm là gì?

Một container image thường đi qua nhiều lớp:

~~~text
Developer source code
      |
      v
Git repository / reviewed commit
      |
      v
Package manager and external repositories
  Maven Central / approved internal mirror
      |
      v
CI runner / compiler / build plugins
      |
      v
Java JAR/WAR + transitive dependencies
      |
      v
Docker/OCI image + OS packages + runtime
      |
      v
Azure Container Registry
      |
      v
AKS / Container Apps / App Service
      |
      v
Production requests and data
~~~

Mỗi mắt xích có rủi ro: dependency không còn được duy trì, tài khoản publisher bị chiếm, package bị thay thế, build plugin bị xâm nhập, CI job nhận credentials rộng, image tag bị chuyển sang manifest mới, hoặc cluster triển khai từ registry không được phép.

### Tại sao chỉ review source code chưa đủ?

Repository có thể không chứa source của tất cả **dependencies, base image, compiler, plugin, operating-system libraries**. Một dòng trong pom.xml không cho biết toàn bộ bytecode/runtime classes sẽ chạy, cũng không xác nhận image cuối cùng tương ứng với code đã review.

## 2. Threat model: cần bảo vệ điều gì?

| Mục tiêu tấn công | Kịch bản | Biện pháp chính |
|---|---|---|
| **Source** | Commit malicious code hoặc sửa workflow file | Branch protection, review, signed/verified commit khi policy yêu cầu |
| **Dependencies** | Gói độc hại, dependency confusion, typosquatting | Approved repositories, pin versions, integrity verification, SBOM |
| **Build environment** | Runner bị xâm nhập, secret/token bị lấy | Ephemeral/isolated runners, workload federation, least privilege |
| **Build output** | JAR/image bị tráo sau khi build | Content digest, signed provenance, verify |
| **Registry** | Tag đổi trỏ tới digest khác | Immutable digest deploy, registry RBAC và policy |
| **Deployment** | Pull image không được phép hoặc không đúng release | Admission policies, signatures/attestations, GitOps |
| **Runtime** | Known vulnerable library hoặc container escape | Scanning, patching, policy, hardening, Defender |
| **Audit trail** | Xóa/ghi sai provenance hoặc SBOM | Evidence retention, access control, tamper-evident storage |

**SBOM là dữ liệu kê khai**, không phải cơ chế chống sửa đổi khi không được bảo vệ. Nếu kẻ tấn công kiểm soát cả artifact và SBOM không có kiểm chứng, họ có thể viết một SBOM “sạch” nhưng sai.

## 3. SBOM là gì?

**Software Bill of Materials** là bản kê các thành phần cấu thành phần mềm và quan hệ giữa chúng. Tùy công cụ/độ phủ, SBOM có thể ghi:

- Package name và version.
- Supplier/publisher hoặc source repository.
- Component type: library, application, operating-system package, container, framework.
- Package URL (**purl**) hoặc identifiers khác.
- Hashes/checksums khi tính từ artifact bytes.
- Direct/transitive dependencies và dependency graph.
- Licenses, copyrights, metadata từ package manifest.
- Build/document metadata: tool, timestamp, serial number/namespace.

~~~text
SBOM for checkout-service
    |
    +-- Java application checkout-service:1.8.0
    |     +-- azure-identity
    |     +-- azure-storage-blob
    |     +-- spring-boot-starter-web
    |            +-- transitive libraries
    |
    +-- Container runtime: JRE/JDK
    +-- Base image operating-system packages
    +-- Native libraries and utilities if detected
~~~

**SBOM không nhất thiết có toàn bộ những mục này.** Một SBOM tạo từ Maven dependency graph có thể thiếu OS packages, còn một image scanner có thể không tìm được libraries bị shaded/obfuscated hoặc tải động lúc runtime.

## 4. SBOM không phải những thứ nào?

| Đối tượng | Trả lời câu hỏi | Không chứng minh |
|---|---|---|
| **SBOM** | Artifact chứa những components nào? | Components không có lỗ hổng/mã độc |
| **Lockfile** | Dependency resolution được khóa như thế nào? | Image cuối chứa chính xác những gì |
| **Vulnerability report** | Components này khớp CVE/advisory nào? | Đường build là đáng tin |
| **License report** | Package metadata/license obligations? | Đã tuân thủ mọi điều khoản pháp lý |
| **SHA-256 digest** | Bytes có khớp một content ID không? | Ai tạo bytes hoặc build có đáng tin không |
| **Digital signature** | Chủ khóa/danh tính đã ký bytes/statement nào? | Nội dung được ký là thật/sạch nếu signer không đáng tin |
| **Provenance** | Artifact xuất xứ và quá trình tạo thế nào? | Bản thân source/dependencies không có lỗi |
| **Attestation** | Một chủ thể chứng thực statement gắn với artifact | Statement luôn chính xác nếu không kiểm soát issuer/policy |

Vì vậy cần kết hợp **thành phần + kiểm chứng danh tính/nguồn + policy + quét lỗ hổng + kiểm thử + quan sát runtime**.

## 5. CycloneDX và SPDX

**CycloneDX** và **SPDX** là hai họ chuẩn phổ biến để trao đổi thông tin thành phần phần mềm. Mỗi chuẩn có các version/specification và kiểu diễn đạt riêng.

| Tiêu chí | CycloneDX | SPDX |
|---|---|---|
| Trọng tâm phổ biến | Software/component inventory, dependencies và supply-chain metadata | Software package/licensing/provenance-related document model |
| Dạng biểu diễn | JSON/XML hoặc biểu diễn được chuẩn hỗ trợ | JSON, tag-value, RDF và các dạng theo phiên bản |
| Identity | bom-ref, purl, hashes, component metadata | SPDXID, package identifiers, externalRefs, checksums |
| Dependency links | dependencies graph | relationship statements/graph |
| License | Declared/license evidence theo spec | License identifiers/expressions theo spec |
| Ecosystem | CycloneDX Maven/Gradle tooling, Syft, scanners | SPDX generators, Syft, package/compliance tooling |

**Đừng tự khẳng định một định dạng luôn “tốt hơn” định dạng kia.** Chọn theo yêu cầu khách hàng, scanner, registry, compliance và khả năng xuất/đọc của công cụ. Có thể tạo cả hai, nhưng chuyển đổi có thể mất metadata không tương đương.

### Thông tin tối thiểu phải giữ

1. Artifact identity và digest.
2. Component identifier ổn định, name và version.
3. Quan hệ phụ thuộc khi biết.
4. Công cụ/phiên bản tạo SBOM.
5. Thời điểm và source/build reference.
6. License và hash khi có bằng chứng.
7. Signature/attestation hoặc metadata bảo vệ SBOM.

## 6. PURL và component identity

**Package URL (purl)** định danh package theo ecosystem. Ví dụ:

~~~text
pkg:maven/com.azure/azure-identity@<RESOLVED_VERSION>
pkg:maven/org.springframework.boot/spring-boot@<RESOLVED_VERSION>
pkg:deb/debian/libssl3@<RESOLVED_VERSION>?arch=amd64
~~~

PURL hữu ích để vulnerability scanners đối chiếu package, nhưng không tự là chứng cứ về bytes của package. Hai nguồn artifacts hoặc cách đóng gói có thể dùng tên/version giống nhau; hashes, repository trust, digest và provenance giúp bổ sung.

### Cần ghi thông tin nào?

- **Name/version** là thông tin cơ bản.
- **purl** hỗ trợ định danh ecosystem.
- **Hash** hỗ trợ so byte artifacts khi được đo thực sự.
- **Source/repository** cho biết nguồn phát hành dự kiến.
- **Dependency relationship** giúp tìm transitive impact.

Không tự gán package version bằng cách nhìn tên JAR nếu build dùng repackaging hoặc shaded classes; scanner phải ghi rõ mức độ chắc chắn và cách nhận diện.

## 7. Direct vs transitive dependency

~~~text
pom.xml trực tiếp:
  spring-boot-starter-web
  azure-storage-blob
  azure-identity
         |
         v
Transitive graph:
  spring-web, logging, JSON parser, HTTP clients,
  azure-core, Netty/Reactor, auth libraries, ...
~~~

Một **CVE trong thư viện JSON bắc cầu** có thể ảnh hưởng dự án dù pom.xml không khai báo trực tiếp. Maven BOM hoặc Gradle platform giúp version alignment nhưng **không phải bản kê SBOM của artifact đã build**.

### Điều tra ảnh hưởng

1. Xác định thư viện bị ảnh hưởng bằng purl/name/version.
2. Tìm nó trong SBOM của các releases.
3. Dùng dependency graph tìm đường từ application tới package.
4. Xác minh package có trong binary/image thực.
5. Kiểm tra advisory, fix version, exploitability/context và runtime path.
6. Ưu tiên nâng parent dependency/BOM, không force override bừa bãi.

## 8. Source SBOM, build SBOM và image SBOM

| Lúc tạo | Nguồn | Thấy tốt | Có thể bỏ sót |
|---|---|---|---|
| **Source scan** | Manifests/pom.xml/lockfiles | Declared dependencies | Runtime-resolved graph, downloaded deps |
| **Build-resolved scan** | Maven/Gradle graph | Direct/transitive versions được resolve | Base OS packages, native tools, dynamic downloads |
| **Binary/JAR scan** | JAR/WAR và bundled classes | Những thành phần đóng gói thực, tùy scanner | Shaded/repackaged/obfuscated libs |
| **Image scan** | OCI image layers/filesystem | OS packages + JAR + runtime thường gặp | Dynamic components, undiscoverable native libs |
| **Runtime inventory** | Workload observations | Modules/load thực tế ở một số trường hợp | Chưa-executed paths, full dependency set |

### Chiến lược kết hợp

Nên tạo **build-resolved SBOM** và **final-image SBOM** ở giai đoạn thích hợp, rồi liên kết cả hai với **cùng release**. Không gộp chúng thành một bản mà không giải thích scope/deduplication.

### Vì sao thời điểm scan quan trọng?

Sau khi Maven build xong, Dockerfile có thể copy thêm shell tools, APM agent hoặc native libraries. SBOM chỉ từ Maven không thấy các thành phần đó. Ngược lại, công cụ quét image có thể không diễn giải đầy đủ metadata license/dependency graph từ Maven.

## 9. Container image chứa những lớp gì?

~~~text
OCI image: registry.example/checkout:1.8.0
    |
    +-- Manifest / image index
    |     +-- Config digest
    |     +-- Layer digests
    |
    +-- Base OS files/packages
    +-- JRE/JDK and native libraries
    +-- Spring Boot fat JAR
    +-- APM agent / init scripts
    +-- Application configuration defaults
~~~

Một final image là **artifact độc lập** với source tree. Quét nó cung cấp góc nhìn thực tế hơn về những bytes được phân phối, nhưng vẫn không hoàn hảo.

### Fat JAR và shaded JAR

Spring Boot có thể repack dependencies vào **BOOT-INF/lib**. Shading còn có thể đổi package/class names. Một scanner không thấy Maven metadata hoặc không nhận dạng shaded classes có thể không liệt kê đúng package.

**Tránh tuyên bố “SBOM complete 100%”** khi chưa có cơ sở đánh giá coverage. Đặt tiêu chí tối thiểu, thực hiện kiểm tra đa nguồn và ghi known gaps.

## 10. Chuẩn hóa SBOM identity và bản phát hành

Mỗi lần tạo SBOM cần metadata có thể đối chiếu:

~~~text
Application: checkout-api
Release:     1.8.0
Git commit:  <FULL_GIT_SHA>
Build run:   <CI_RUN_ID>
Container:   registry.example/checkout-api@sha256:<DIGEST>
SBOM format: CycloneDX JSON (approved spec version)
Generator:   pinned tool name/version
Timestamp:   UTC
~~~

Nếu không gắn SBOM với **output digest**, rất khó biết file sbom.json là của image đang chạy hay bản build thử trước đó.

**Release version/tag không đủ làm identity**, vì tag có thể bị thay nếu registry/policy cho phép.

## 11. Maven: tạo SBOM bằng CycloneDX plugin

Một Maven project Java có thể dùng **CycloneDX Maven Plugin**. Ví dụ cấu hình trong **pom.xml** (phiên bản plugin phải thay bằng bản đã duyệt; đoạn này là template):

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.cyclonedx</groupId>
      <artifactId>cyclonedx-maven-plugin</artifactId>
      <version>REPLACE_WITH_APPROVED_PLUGIN_VERSION</version>
      <executions>
        <execution>
          <phase>verify</phase>
          <goals>
            <goal>makeAggregateBom</goal>
          </goals>
        </execution>
      </executions>
      <configuration>
        <outputFormat>json</outputFormat>
        <outputName>bom</outputName>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

### Lưu ý trước khi dùng

1. **REPLACE_WITH_APPROVED_PLUGIN_VERSION** không phải version chạy được; phải thay đúng số phiên bản công bố.
2. Cấu hình plugin và output path có thể khác theo plugin/version; đọc tài liệu chính thức.
3. **makeAggregateBom** phù hợp hướng tổng hợp nhiều modules; với project một module có thể chọn goal tương ứng.
4. Plugin có thể tạo file tại **target/bom.json** theo cấu hình, nhưng đừng suy ra mọi version/goal có cùng output path.
5. Quá trình build/resolve dependency có thể tải JAR/metadata từ repository; chỉ chạy với mirror và network policy được phê duyệt.

### Command minh họa

~~~bash
# Chỉ chạy trong dự án Java lab; không chạy ở workflow worker.
mvn -B -ntp verify

# Hoặc gọi goal trực tiếp, pin plugin version:
mvn -B -ntp \
  org.cyclonedx:cyclonedx-maven-plugin:REPLACE_WITH_APPROVED_PLUGIN_VERSION:makeAggregateBom
~~~

**BOM chỉ mô tả những thành phần mà plugin nhận diện theo dependency resolution ở thời điểm chạy.** Nếu build profile, module, classifier hoặc build tool behavior khác production, SBOM có thể khác artifact release.

## 12. Maven multi-module: làm sao tránh mất module?

Ví dụ:

~~~text
checkout-service/
    pom.xml (parent)
    api/pom.xml
    domain/pom.xml
    storage-adapter/pom.xml
    messaging-adapter/pom.xml
~~~

### Quy trình

1. Chạy build từ **root reactor** với những Maven profiles giống release.
2. Sử dụng aggregate SBOM goal/phương thức tương ứng với plugin version.
3. Xác minh SBOM chứa modules chính và runtime dependencies.
4. Kiểm tra Maven dependency tree nếu một dependency vắng mặt.
5. Đối chiếu output JAR thật với SBOM.
6. Ghi Maven/JDK/plugin versions, active profiles và build run ID.

**Không chạy Maven từ mỗi module riêng rồi mặc định tổng các file SBOM đã đại diện cho release**; có thể thiếu modules hoặc tạo trùng dependencies.

## 13. Gradle: SBOM và resolved configurations

Với Gradle, có các plugin hỗ trợ CycloneDX và các công cụ quét output artifacts. Vì API/task names của plugin thay đổi, cần **pin plugin version** và xác nhận output path trong documentation hiện hành.

~~~text
Gradle project
     |
     +-- compileClasspath
     +-- runtimeClasspath
     +-- testRuntimeClasspath
     |
     v
CycloneDX Gradle plugin / approved SBOM generator
     |
     v
SBOM for selected project/configuration(s)
~~~

### Không trộn scopes

Một SBOM phát hành production nên ưu tiên **runtime dependencies**. Test frameworks (JUnit, testcontainers) có thể cần SBOM riêng cho build environment nhưng không phải mọi test JAR nằm trong image đang chạy.

### Kiểm tra graph

~~~bash
# Đọc dependency graph Gradle (khi học viên tự thực hiện):
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency azure-core \
  --configuration runtimeClasspath
~~~

Đây là lệnh hướng dẫn; **không thực thi Gradle trong công việc worker**. Dùng Gradle wrapper đã được pin/kiểm soát và repository tin cậy.

## 14. Quét final container image với Syft

**Syft** là một công cụ phổ biến tạo software package inventories/SBOM từ image, filesystem hoặc các nguồn được hỗ trợ.

Ví dụ hướng dùng:

~~~bash
# Chỉ chạy khi đã chọn image digest và có quyền pull.
# Thay image reference/digest bằng artifact lab thật.
IMAGE="registry.example/checkout-api@sha256:<REAL_DIGEST>"

syft "$IMAGE" -o cyclonedx-json=sbom-image.cdx.json

# Có thể tạo SPDX JSON theo format mà Syft version hỗ trợ:
syft "$IMAGE" -o spdx-json=sbom-image.spdx.json
~~~

### Chú ý

- **<REAL_DIGEST>** là placeholder; phải thay bằng chuỗi digest hợp lệ.
- Syft có thể truy cập registry hoặc container runtime; credential chỉ cấp read-only cho registry cần thiết.
- Output file có thể chứa thông tin nội bộ về dependencies, paths và base image; phân quyền/retention phù hợp.
- Scanner cần phiên bản đã kiểm thử; package detection có false positives/negatives.
- Quét local image tag không bảo đảm đó là digest cuối cùng đã push, đặc biệt khi multi-platform build.

## 15. Source scan và final image scan có thể khác nhau

Giả sử build-resolved SBOM có:

~~~text
pkg:maven/org.springframework.boot/spring-boot@<VERSION>
pkg:maven/com.azure/azure-identity@<VERSION>
~~~

Image-level scan còn phát hiện:

~~~text
pkg:deb/debian/openssl@<VERSION>
pkg:deb/debian/zlib1g@<VERSION>
JRE files/native libraries
~~~

### Hai chiều kiểm tra

- **Từ Maven tới image:** mỗi runtime dependency mong đợi có thật trong final app artifact không?
- **Từ image về source:** component nào do base image, Dockerfile, APM agent hoặc build step thêm vào?

Nếu một dependency chỉ xuất hiện trong source SBOM nhưng không ở image SBOM, có thể do scope khác, scanner không thấy, packaging khác hoặc dependency không được ship. Không tự xóa nó khỏi risk register nếu chưa xác minh.

## 16. Kiểm tra tính đúng của SBOM

Một SBOM “có file JSON và parse được” chưa đủ.

### Tiêu chí cấu trúc

- JSON/XML theo schema chuẩn và spec version được duyệt.
- Có metadata component của application/output.
- Có tool name/version và timestamp thích hợp.
- Identifiers không trùng sai hoặc mất bom-ref/SPDXID.
- Dependency relationships hợp lệ.
- Không có fields vô nghĩa do pipeline gán placeholder.

### Tiêu chí nội dung

- Phiên bản của một số direct dependencies khớp Maven/Gradle resolved graph.
- Có expected critical runtime libraries.
- Base image packages được liệt kê khi SBOM scope là final image.
- Phân biệt dev/test-only với runtime.
- Không vô tình kê khai tất cả dependencies trên laptop/CI host.
- Tránh thiếu components vì plugin bỏ qua modules/build profiles.

### Tiêu chí gắn với release

SBOM được sinh và lưu cho **chính build artifact/image digest** phát hành, không dùng lại SBOM của bản trước khi code/deps thay.

## 17. SBOM được dùng ở những giai đoạn nào?

~~~text
PR / dependency review
    -> source/build SBOM and initial risk scan
             |
             v
Merge to protected branch
    -> clean build, final-artifact SBOM
             |
             v
Push image to ACR, record digest
    -> attach/publish SBOM + provenance
             |
             v
Staging admission / policy
    -> verify signer, subject, SBOM and approved registry
             |
             v
Production deployment
    -> digest pinning, monitor and rescan as advisories evolve
~~~

**SBOM không chỉ được tạo một lần rồi quên.** Cơ sở dữ liệu CVE/tiêu chuẩn license thay đổi theo thời gian, nên một SBOM cũ vẫn có thể được quét lại khi có advisory mới.

## 18. SBOM và vulnerability scanning khác nhau

~~~text
SBOM:
  Package A v1.2
  Package B v4.5
  Package C v2.1
        |
        v
Advisory database (CVE, OSV, GHSA, vendor advisories)
        |
        v
Vulnerability matches + severity + affected ranges
        |
        v
Triage exploitability, reachability, context
        |
        v
Fix/mitigate + regenerate/reverify SBOM
~~~

### Vì sao kết quả scanner khác nhau?

- Advisory feed và freshness.
- Package identity mapping (purl/CPE/vendor).
- OS package backports làm version number khác upstream.
- Java shaded libraries hoặc incomplete component metadata.
- False positives/false negatives.
- Policy severity thresholds và exclusions.

**Không coi “0 CVE từ một scanner” là bảo đảm an toàn.** Thiếu dữ liệu/coverage hoặc advisory chưa được công bố vẫn là rủi ro.

## 19. Quy trình xử lý CVE dựa trên SBOM

Khi một advisory được công bố:

1. Xác minh advisory chính thức và các version ranges bị ảnh hưởng.
2. Tìm package purl/version trong SBOM tất cả active releases.
3. Xác định component nằm trong JAR/runtime image hay chỉ test dependency.
4. Xem dependency path và remediation options (BOM/parent upgrade, patch, rebuild).
5. Đánh giá exposure của workload: API reachable, permissions, sandbox, config, exploit prerequisites.
6. Chọn remediation theo severity, exploitability và SLO.
7. Tạo artifact mới từ source đã sửa, sinh SBOM/provenance mới.
8. Test, ký, xác minh và deploy theo release gate.
9. Theo dõi production digest và chứng minh vulnerable digest không còn chạy.
10. Ghi exception/temporary mitigation với owner và expiration nếu chưa thể fix.

**Không “sửa SBOM” bằng cách xóa package name/version để scanner không báo lỗi.** Việc cần sửa là thành phần và build output thực.

## 20. SBOM cũng hỗ trợ quản lý license

Dependency có thể sử dụng license như Apache-2.0, MIT, BSD-3-Clause hoặc những điều khoản khác. SBOM cung cấp **inventory ban đầu** để nhóm pháp lý/compliance phân tích.

### Cần kiểm tra

- Package có khai báo license SPDX identifier/expression không?
- License được **declared**, **concluded** hay tool chỉ suy từ metadata?
- Có nhiều licenses hoặc dual-license không?
- Có notice/source distribution obligations không?
- Có third-party code được copy thủ công nhưng không được scanner nhận dạng?
- Container base image và command-line tools có license riêng không?

### Không đồng nhất license scanner với ý kiến pháp lý

Một SBOM có thể ghi **NOASSERTION/UNKNOWN** khi thiếu license metadata. Điều đó không có nghĩa package vô bản quyền hoặc chắc chắn được dùng thương mại. Quy trình cần policy review, owner và bằng chứng hợp lệ, đặc biệt khi distribute phần mềm cho khách hàng.

## 21. Chọn định danh của artifact: tag và digest

Một container image có thể được tham chiếu:

~~~text
myregistry.azurecr.io/checkout-api:1.8.0
myregistry.azurecr.io/checkout-api:stable
myregistry.azurecr.io/checkout-api@sha256:<64_HEX_CHARACTERS>
~~~

**Tag** là nhãn trỏ tới một manifest/index; nó có thể được chuyển sang content khác nếu registry và permissions cho phép. **Digest** là content address của manifest/index và không thay đổi cho cùng bytes.

~~~text
Tag 1.8.0  ------> Manifest digest A
Tag stable ------> Manifest digest A

Later:
Tag stable ------> Manifest digest B
Tag 1.8.0  ------> Manifest digest A
~~~

### Tại sao digest quan trọng?

- Có thể xác định chính xác artifact được ký/đính SBOM.
- Tránh deploy một tag đã bị thay.
- Hỗ trợ rollback về image manifest đã kiểm thử.
- Giúp chứng minh release production chứa thành phần nào.

**Digest không chứng minh provenance.** Attacker có thể build một image độc hại rồi biết digest của nó. Cần kiểm tra ai/build nào đã tạo digest đó và policy có chấp nhận hay không.

## 22. OCI manifest, image index và multi-platform

Một image tag có thể trỏ tới **OCI image index** bao gồm nhiều platform manifests:

~~~text
checkout-api:1.8.0
      |
      v
OCI image index @sha256:INDEX_DIGEST
      |
      +-- linux/amd64 manifest @sha256:AMD64_DIGEST
      |      +-- config + layers
      |
      +-- linux/arm64 manifest @sha256:ARM64_DIGEST
             +-- config + layers
~~~

### Hệ quả với SBOM/provenance

- Đính một SBOM vào **index digest** có thể mang ý nghĩa khác một SBOM cho **amd64 manifest**.
- Hệ điều hành/packages giữa platforms có thể khác.
- Công cụ build có thể phát hành provenance/SBOM ở cấp từng platform hoặc cấp index, tùy tính năng.
- Admission controller và scanner phải biết đang xác minh **index hay platform-specific manifest**.

**Không lấy SBOM của linux/amd64 rồi tuyên bố nó bao phủ đầy đủ linux/arm64** khi chưa xác minh.

## 23. Azure Container Registry trong chuỗi bằng chứng

**Azure Container Registry (ACR)** thường giữ container images và OCI artifacts trong hệ thống Azure. Cần quản lý:

1. Registry identity, region, replication và network access.
2. Repositories, tags, manifests và immutable digest references.
3. Push/pull access tách biệt.
4. Registry retention/cleanup và artifact retention policy.
5. Tích hợp vulnerability scanning/Defender theo khả năng hiện hành.
6. SBOM/provenance/signatures, nơi lưu và cách tìm theo digest.

~~~text
Azure DevOps / GitHub Actions trusted build
        |
        v
Push final image
        |
        v
Azure Container Registry
   checkout-api@sha256:IMAGE_DIGEST
        |
        +--> SBOM linked to subject digest
        +--> Provenance attestation linked to digest
        +--> Signature / verification material
        |
        v
AKS pulls approved digest
~~~

### ACR không tự biến mọi push thành trusted release

Một người có quyền push vào repo có thể đưa artifact chưa được duyệt vào registry. Cần **publisher identity, protected CI flow, verification gate và cluster admission**. Việc ACR đặt trong private network/Private Link là lớp bảo vệ đường truyền, không phải chứng nhận nguồn gốc.

## 24. Truy vấn ACR metadata chỉ đọc

Khi có quyền đọc một **registry lab**:

~~~bash
az account show \
  --query "{subscription:id, tenant:tenantId}" \
  --output json

az acr repository list \
  --name "<LAB_ACR_NAME>" \
  --output table

az acr repository show-tags \
  --name "<LAB_ACR_NAME>" \
  --repository "checkout-api" \
  --output table
~~~

Các lệnh đọc trên giúp nhận biết repository/tags, **chưa chứng minh tag tương ứng digest nào hoặc artifact được ký**. Để lấy manifest digest, dùng API/CLI/OCI tooling tương ứng với ACR version và permissions, sau đó ghi immutable digest vào release record.

**Không suy ra mọi Azure CLI command cũ vẫn tồn tại nguyên**. Kiểm tra help/reference theo CLI version. Khi có nhiều registries/subscriptions, yêu cầu lệnh chỉ rõ registry thật và scope.

## 25. Artifact provenance là gì?

Provenance là metadata xác định **output artifact được tạo bằng quy trình nào và từ những đầu vào nào**.

~~~text
Source repository + commit
       |
       +-- Build workflow definition
       +-- Dependency/cache sources
       +-- Builder/runtime identity
       |
       v
Trusted CI builder / execution
       |
       v
Output artifact digest
       |
       v
Provenance statement
    subject: image digest
    source: repo + commit
    builder: workflow/service identity
    build parameters / materials
~~~

Một provenance statement có thể được lưu dưới dạng **attestation**, thường ký và liên kết với content digest. Đây không phải “tác giả viết chú thích rằng image tốt”; cần kiểm tra **subject, builder identity, signature và trusted workflow**.

## 26. Provenance tối thiểu phải chứa gì?

| Nhóm thông tin | Ví dụ | Cần xem |
|---|---|---|
| **Subject** | OCI image @sha256:... | Digest khớp artifact được deploy |
| **Source** | Repository URI | Nguồn có được allowlist không |
| **Revision** | Full Git commit SHA | Commit có trong protected branch/release |
| **Builder ID** | Build service/workflow | Builder được tổ chức tin cậy |
| **Invocation** | Workflow ID/run ID/parameters | Run có theo chính sách không |
| **Materials** | Source, dependencies/base image khi được ghi | Các nguồn đầu vào đã xác định |
| **Timestamp** | Start/finish UTC | Có hợp lý và đủ audit |
| **Build type** | Kind of build process | Khớp workflow/template cho phép |
| **Signer/issuer** | Signing identity/authority | Certificate/key/issuer được verify |

Thông tin thực tế phụ thuộc **SLSA/in-toto predicate spec version** và công cụ tạo provenance. Các tên ở bảng là khái niệm, không phải schema JSON bắt buộc tương ứng một-một cho mọi phiên bản.

## 27. SLSA và provenance attestations

**Supply-chain Levels for Software Artifacts (SLSA)** là một khung tiêu chuẩn về bảo đảm nguồn gốc/tính toàn vẹn của artifacts. Provenance mô tả build process, source revisions và output. Các cấp độ/yêu cầu cụ thể **thay đổi theo phiên bản specification**.

### Phân biệt

- **SLSA specification:** định nghĩa các khái niệm/yêu cầu.
- **SLSA provenance predicate:** schema diễn đạt nguồn gốc build.
- **Builder/attestor:** dịch vụ thực sự tạo statement.
- **Verifier/policy:** bên dùng bằng chứng để chấp nhận hoặc từ chối artifact.

**Một file JSON tự gắn nhãn SLSA không chứng minh đạt bất kỳ mức SLSA nào.** Cần evidence về builder isolation, identity, immutable source, tamper resistance và verification.

### Ví dụ minh họa nguồn gốc (không phải schema SLSA hợp lệ)

~~~json
{
  "note": "Conceptual example, NOT a compliant attestation",
  "subjectDigest": "sha256:<IMAGE_DIGEST>",
  "sourceCommit": "<FULL_COMMIT_SHA>",
  "sourceRepository": "https://example.org/org/checkout-api",
  "builderIdentity": "<TRUSTED_WORKFLOW_ID>",
  "runId": "<CI_RUN_ID>"
}
~~~

Khi phát hành thực, **dùng generator chính thức** theo schema SLSA/in-toto hiện hành, không ký JSON tự chế rồi tuyên bố có SLSA provenance.

## 28. In-toto statement và attestation

Một **attestation** là một statement về artifact, có thể mang predicate như:

- Provenance: artifact được tạo từ nguồn/workflow nào.
- SBOM: artifact gồm những components gì.
- Test results: assertions về quá trình kiểm thử, khi có trusted generator.
- Vulnerability scan results: scanner nào chạy lúc nào, với version nào.

~~~text
             Subject: image@sha256:D
                       |
           +-----------+------------+
           |                        |
           v                        v
      SBOM attestation        Provenance attestation
       predicate: ...           predicate: ...
           |                        |
           +-----------+------------+
                       |
                 Signature/bundle
                       |
                       v
               Policy verification
~~~

**Attestation không đồng nghĩa có chữ ký hợp lệ**. Một statement có thể chưa được ký hoặc được ký bởi identity không nằm trong danh sách tin cậy. Policy phải kiểm chứng cả nội dung và signer.

## 29. Ký artifact và ký attestation

Có hai mục tiêu liên quan nhưng khác nhau:

1. **Artifact signature:** xác nhận signer ký content digest của image/artifact.
2. **Attestation signature:** xác nhận signer ký một statement (SBOM/provenance...) gắn với subject digest.

### Chữ ký giúp gì?

- Phát hiện việc statement hoặc digest bị sửa sau ký.
- Liên kết bằng chứng với một identity/khóa được tin cậy.
- Cho phép admission gate kiểm tra đúng release.

### Chữ ký không giúp gì nếu?

- Signing key bị lộ hoặc CI signer bị chiếm.
- Kẻ tấn công khiến trusted signer ký một output độc hại.
- Verifier không kiểm tra signer identity, chỉ kiểm “có signature”.
- Provenance statement khai báo source sai và được tạo bởi một tool không đáng tin.

**Cần xây dựng trust policy** thay vì chấp nhận tất cả signatures từ bất kỳ issuer nào.

## 30. Sigstore/Cosign và keyless signing

**Cosign** là một công cụ trong hệ sinh thái **Sigstore**, có thể ký và xác minh container images và attestations qua các hình thức supported. Một mô hình là **keyless signing** dựa trên danh tính OIDC của workload và các dịch vụ chứng thực.

~~~text
Trusted CI workflow
       |
       | OIDC identity claims
       v
Keyless signing authority / certificate workflow
       |
       v
Sign image digest / attestation
       |
       v
OCI registry + transparency/evidence mechanisms
       |
       v
Verifier checks signer identity/issuer and subject
~~~

### Không tự dùng keyless ở mọi CI mà không kiểm tra

- CI phải hỗ trợ **OIDC** và policy credentials/issuer phù hợp.
- Cần kiểm tra Sigstore/Cosign version, trust root, certificate identity fields, transparency log/bundle và mạng.
- Keyless identities của PR từ nhánh không tin cậy có thể khác protected release workflow.
- Không chỉ so issuer domain; phải so **repository/workflow/ref/build identity** được phê duyệt.
- Có thể có yêu cầu private Sigstore instance/trust root riêng; không mặc định mọi tổ chức dùng public Sigstore.

### Với signing key do tổ chức quản lý

Có thể dùng khóa được quản lý phù hợp như Azure Key Vault/KMS qua integration được hỗ trợ. Cần key permissions, rotation, audit và verifier trust anchor. Không upload khóa cá nhân vào CI variables hoặc commit vào repository.

## 31. Dấu vết minh bạch và offline verification

Các hệ sinh thái signing/attestation có thể sử dụng transparency log và **verification bundles** để cung cấp bằng chứng có thể kiểm tra về sau.

### Ba điều cần phân biệt

- **Chữ ký hợp lệ:** statement/digest không bị sửa với private key tương ứng public key/cert.
- **Danh tính signer đáng tin:** certificate/identity phù hợp allowlist của tổ chức.
- **Provenance đáng tin:** statement do workflow/builder được bảo vệ tạo ra, source và subject đúng.

Một transparency log giúp hỗ trợ audit/tamper evidence theo thiết kế nhưng **không chứng minh bản thân code không độc hại**.

### Offline verification

Nếu production cluster không truy cập được verification services trên Internet, cần thiết kế **bundle/trust root đã pin và vòng đời cập nhật** phù hợp. Không bỏ verify hoàn toàn chỉ vì một dịch vụ hỗ trợ bên ngoài tạm không kết nối được.

## 32. Gắn SBOM/provenance vào artifact digest

Một chiến lược là publish SBOM/provenance dưới dạng **OCI artifacts/referrers** liên kết với subject image digest nếu registry và công cụ hỗ trợ.

~~~text
ACR:
  checkout-api@sha256:D
       |
       +-- OCI SBOM artifact (subject = D)
       +-- OCI provenance attestation (subject = D)
       +-- Cosign signature / verification material
~~~

### Vấn đề cần giải quyết

1. Registry/OCI tooling có hỗ trợ artifact/referrers theo API/version không?
2. Metadata được lưu ở repository nào, có quyền push/read không?
3. Artifact retention/cleanup có xóa SBOM/attestation độc lập với image không?
4. Nếu image được copy qua registry/region, attestations có được copy theo không?
5. Scanner/validator/admission controller có lấy đúng subject digest không?

**Đính một file sbom.json vào release pipeline artifact khác không tự làm ACR lưu nó cạnh image.** Phải thiết kế explicit publication/storage/linkage và kiểm chứng.

## 33. ORAS và OCI artifacts

**ORAS** là một nhóm công cụ/thư viện giúp push/pull/copy OCI artifacts, phục vụ việc lưu SBOM và metadata nếu registry hỗ trợ.

### Luồng khái niệm

~~~text
Generate SBOM JSON
        |
        v
Validate SBOM format
        |
        v
Use OCI tooling to attach/push as artifact
   subject: checkout-api@sha256:IMAGE_DIGEST
        |
        v
ACR registry
        |
        v
Pull/read/verify by policy tool
~~~

**Không hard-code một câu lệnh oras attach cho mọi version**: ORAS CLI syntax, artifact types, subject support và registry compatibility thay đổi. Đọc docs của ORAS/ACR hiện hành và test bằng image digest lab trước.

### MIME/artifact type cần thống nhất

CycloneDX JSON, SPDX JSON, SLSA provenance hoặc DSSE envelope có media types khác nhau theo specification. Chọn artifact type/predicate type có chuẩn; tránh đăng ký mọi JSON là **application/json** không có metadata phân biệt.

## 34. Kết hợp OCI referrers với registry cleanup

Khi xóa image digest, có thể ảnh hưởng tới referrer artifacts tùy registry, implementation và cleanup policy. Khi xóa SBOM/attestation cũ, tổ chức mất khả năng điều tra release lịch sử.

### Retention policy hai lớp

- **Deployable images:** giữ những digests production, rollback và các release được policy yêu cầu.
- **Evidence artifacts:** giữ SBOM/provenance/signature/test reports theo thời hạn audit và incident response.

Nếu image cũ không còn được pull cho production, có thể vẫn cần SBOM/provenance để chứng minh đã xử lý CVE trong quá khứ.

### Lưu cả bên ngoài registry?

Có thể lưu bản chứng cứ ở immutable blob storage/artifact archive với access control, integrity và retention nếu quy định audit yêu cầu. **Một bản copy không gắn đúng digest/không có verification metadata vẫn khó tin cậy.**

## 35. Azure Key Vault và signing key

Nếu tổ chức sử dụng chữ ký dựa trên khóa dài hạn thay vì keyless:

~~~text
Release signing workflow
       |
       | Entra workload federation / managed identity
       v
Azure Key Vault / supported signing integration
       |
       | Cryptographic signing operation
       v
Signature over artifact digest or attestation
       |
       v
Published signature and verification metadata
~~~

### Least privilege

- Signing identity chỉ có quyền **sign** với key tương ứng, không cần Key Vault Administrator.
- Build/PR pipeline không tự sở hữu production release-signing key.
- Phân tách keys dev/staging/prod theo risk policy.
- Audit signing events và bất thường.
- Có key rotation/revocation/trust anchor rollover plan.
- Quản lý Key Vault network/private endpoint khi workflow cần.

**Azure Key Vault không tự làm Cosign tương thích mọi key type/algorithm**. Xác minh plugin/provider/KMS URI và thuật toán hỗ trợ trước, không đưa một đoạn lệnh Azure KMS chưa kiểm thử vào CI production.

## 36. Trust policy phải kiểm tra điều gì?

Trước khi cho image chạy production:

1. **Subject digest:** artifact cần deploy chính là image được ký.
2. **Trusted signer identity:** thuộc release pipeline được phê duyệt.
3. **Trusted issuer/trust root:** không chấp nhận certificate/CA bất kỳ.
4. **Source repo:** từ allowlisted organization/repository.
5. **Commit SHA/ref:** commit trên protected branch hoặc release tag đã duyệt.
6. **Builder identity:** workflow/build service có isolation và quyền được kiểm soát.
7. **Provenance schema:** predicate type/format hợp lệ.
8. **SBOM link:** SBOM gắn với cùng subject digest và được kiểm chứng.
9. **Vulnerability/license policy:** không có những rủi ro bị chặn theo policy hiện hành.
10. **Exception handling:** break-glass có owner, expiration, audit và review.

**Chỉ kiểm tra signature existence chưa phải một release policy.**

## 37. Threat: ký đúng bytes nhưng từ nguồn không đáng tin

~~~text
Attacker PR branch
      |
      v
CI workflow tự động ký mọi PR build
      |
      v
Image độc hại có signature hợp lệ
      |
      v
Cluster chỉ kiểm "signature exists"
      |
      v
Image độc hại được chấp nhận
~~~

### Cách khắc phục

- Không trao release-signing privileges cho untrusted PR jobs.
- Không cho PR từ fork tự đọc secrets/OIDC identity đủ quyền production nếu không có kiểm soát.
- Verify **workflow identity + source repository + protected ref**.
- Chỉ publish production provenance từ trusted release builder.
- Yêu cầu approval/policy checks trước khi đưa image vào production allowlist.

**Signer identity đáng tin phải gắn với một quy trình phát hành đáng tin**, không chỉ là bất kỳ job nào chạy dưới tên tổ chức.

## 38. Git repository là đầu vào, không phải bằng chứng đầy đủ

Một build thường ghi **repository URL** và **full commit SHA**. Nhưng còn phải trả lời:

- Commit được merge qua pull request có review không?
- Branch/release tag có được bảo vệ khỏi force push không?
- Workflow definition đến từ commit nào?
- Build runner có isolation với PR chưa tin cậy không?
- Dependencies và base images lấy từ nguồn nào?
- Có step tải script qua curl rồi chạy mà không kiểm tra không?
- Build result có thực sự khớp output digest ghi trong provenance không?

### Commit signature khác artifact signature

**Signed Git commit** giúp xác minh một tuyên bố về commit/author theo policy, nhưng không xác minh container image có được tạo từ commit ấy. **Signed image** xác nhận identity đã ký digest, nhưng không chứng minh source commit nếu không có provenance đáng tin. Cả hai giải quyết lớp khác nhau.

## 39. Workflow definition cũng phải được tin cậy

Một GitHub Actions hoặc Azure DevOps pipeline thường gồm:

~~~text
Source code commit
     |
     +-- Workflow YAML / pipeline templates
     +-- External actions/tasks/plugins
     +-- Build scripts
     +-- Container builder/runtime
     +-- Secrets/identity permissions
     |
     v
Release builder
~~~

### Các biện pháp

1. Review và bảo vệ pipeline config như source code.
2. Với third-party actions, pin immutable commit SHA khi nền tảng hỗ trợ và duy trì update policy.
3. Với build tasks/plugins, pin versions và kiểm tra nguồn publisher.
4. Không chạy arbitrary untrusted PR code trong một job có production credentials.
5. Hạn chế scripting remote fetch không xác minh hash/signature.
6. Cấp permissions theo job thay vì dùng token toàn quyền mặc định.
7. Ghi source revision của cả reusable workflow/template khi provenance format hỗ trợ.

**Một pipeline chạy thành công không đồng nghĩa runner và scripts đáng tin.**

## 40. Azure DevOps Pipelines và OIDC federation

Trong Azure DevOps, có thể sử dụng **service connections** với **workload identity federation** theo tính năng/authorization mode được hỗ trợ, thay vì lưu client secret dài hạn trong pipeline.

~~~text
Protected Azure DevOps pipeline
       |
       v
Azure service connection (federated identity)
       |
       | Token exchange with Microsoft Entra ID
       v
Scoped Azure principal
       |
       +--> ACR push on approved registry/repository
       +--> Read approved Key Vault resources if essential
       +--> Deployment rights on staging/prod with approvals
~~~

### Nguyên tắc quyền

- **Build job** cần source/dependency/build cache; không nhất thiết cần quyền deploy.
- **Publish job** chỉ push tới ACR repo/registry cần thiết.
- **Signing job** chỉ sử dụng signer/identity được release policy cho phép.
- **Deploy job** chỉ thay workload trong environment cụ thể.
- **PR jobs** không cần production push/sign permissions.

Việc federation thành công không có nghĩa Azure principal có quyền ACR/AKS tự động. Cần RBAC/registry repository permissions tương ứng, network path và phê duyệt môi trường.

## 41. Azure DevOps YAML: skeleton build và SBOM

Đây là **khung pipeline minh họa**, cố ý không push hoặc ký; cần điều chỉnh theo agent, Maven version, cache/mirror, branch security và plugin version thực trước khi dùng:

~~~yaml
trigger:
  branches:
    include:
      - main

pool:
  vmImage: ubuntu-latest

stages:
  - stage: BuildAndInventory
    displayName: Build Java and generate SBOM
    jobs:
      - job: Build
        steps:
          - checkout: self
            persistCredentials: false

          - script: |
              java -version
              mvn -version
              mvn -B -ntp verify
              test -s target/bom.json
            displayName: Build and verify SBOM presence

          - publish: target/bom.json
            artifact: sbom-java
            displayName: Publish build SBOM
~~~

### Các điều kiện để skeleton chạy

- Maven plugin đã được **cấu hình trong pom.xml** như mục 11, tạo file target/bom.json.
- Với multi-module, đường dẫn SBOM có thể khác; không dùng đường dẫn ví dụ nếu không tồn tại.
- Runner phải có đúng JDK/Maven/permissions và approved artifact repositories.
- CI cần thêm step **schema validation**, **image build**, **image-level SBOM**, **provenance, signing, verification** và **deployment** trước khi đủ production.
- Published pipeline artifact là bản sao file; **chưa gắn với OCI subject digest**.

**Không dùng ví dụ này để khẳng định đã đạt SLSA hoặc đã bảo vệ supply chain đầy đủ.**

## 42. GitHub Actions và Azure: tách build khỏi release

Một workflow có thể phân quyền:

~~~text
Pull Request Workflow
  -> compile/test
  -> dependency/SBOM check
  -> no production signing/push credentials

Protected Main/Release Workflow
  -> isolated trusted build
  -> final image to ACR
  -> provenance/SBOM attestation and signature
  -> verify gate
  -> controlled deployment
~~~

### OIDC khi dùng GitHub Actions

Workload federation yêu cầu **trust relationship** giữa Microsoft Entra ID và OIDC claims GitHub workflow. Khi cấp Azure permissions, cần giới hạn đúng repository/environment/ref theo mô hình hỗ trợ.

**GitHub OIDC dùng để lấy Azure token không tự tạo Cosign keyless signing certificate.** Azure resource login và Sigstore signer identity là các luồng liên quan nhưng không đồng nhất; cần cấu hình từng luồng theo tài liệu.

### Không trao quyền cho mọi pull request

Một PR chứa code do người ngoài đóng góp có thể sửa build script để cố đọc token/secrets. Với runners và credentials, dùng separation, event restrictions và branch/environment protections; không dựa vào một điều kiện tên branch được khai báo trong YAML nếu workflow itself có thể bị sửa bởi PR không đáng tin.

## 43. Docker Buildx: tạo image và attestation metadata

Ở những phiên bản **Docker Buildx/BuildKit** hỗ trợ, có thể tạo SBOM/provenance attestations trong quá trình build.

~~~bash
# Lệnh minh họa có PUSH image; chỉ chạy với lab registry và quyền phù hợp.
# Phải thay registry/repo/tag bằng giá trị lab thật.
docker buildx build \
  --platform linux/amd64 \
  --tag "registry.example/checkout-api:lab-release-001" \
  --sbom=true \
  --provenance=mode=min \
  --metadata-file build-metadata.json \
  --push \
  .
~~~

### Giải thích

- **--sbom=true:** yêu cầu BuildKit tạo SBOM attestation khi hỗ trợ.
- **--provenance=mode=min:** yêu cầu provenance ở mức thông tin tối thiểu theo BuildKit; không đồng nghĩa tự đạt một cấp SLSA.
- **--metadata-file:** lưu metadata để tìm digest/build output theo version.
- **--push:** ghi image vào registry; có thể phát sinh chi phí và đòi quyền.
- **--platform:** ở đây chỉ amd64 để tránh phức tạp đa nền tảng.

### Điều bắt buộc kiểm tra

1. Registry hỗ trợ lưu các attestations/manifest index theo cách builder phát hành.
2. Kết quả digest trong build metadata khớp image ở registry.
3. BuildKit-generated SBOM có coverage phù hợp với nội dung final image.
4. Generated provenance được bảo vệ/ký và bên xác minh tin builder/identity phù hợp.
5. Build process không làm lộ secrets qua build args, build logs hoặc provenance fields.
6. CI không publish image từ untrusted PR bằng production identity.

**--provenance không tự là chữ ký release tin cậy**. Build attestations cần lưu, verify và policy theo thiết kế.

## 44. Dockerfile và nguồn gốc base image

Một Dockerfile có thể dùng:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/checkout-api.jar /app/app.jar
USER 10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Đây là ví dụ tối giản, **không phải Dockerfile production hoàn chỉnh**; base image tag có thể đổi, user ID phải tương thích quyền filesystem, và JAR path phụ thuộc dự án.

### Tốt hơn khi kiểm soát supply chain

- Chọn base image từ registry/vendor được duyệt.
- **Pin base image by digest** ở release build khi policy yêu cầu.
- Kiểm tra provenance/signature của base image khi có.
- Định kỳ cập nhật JRE/OS patches thay vì ghim mãi một digest cũ.
- Tạo final-image SBOM sau khi mọi layers đã hoàn thành.
- Tránh package manager cài thêm tools từ nguồn không kiểm soát khi build.

### Một đánh đổi

Pin digest bảo vệ build khỏi tag drift, nhưng cũng có thể giữ lại một base image có CVE đã được sửa ở tag mới. Cần **dependency update cadence** và policy review; tính bất biến không thay thế việc cập nhật bảo mật.

## 45. Chống dependency confusion và package substitution

Một build có thể tải dependencies từ:

- Maven Central hoặc repository proxy được duyệt.
- Azure Artifacts feed hoặc repository nội bộ.
- Public package sources/third-party registries.
- Local build caches.

### Rủi ro

Nếu cùng package name tồn tại trong public và private repository, cấu hình resolution không phù hợp có thể lấy phiên bản độc hại. Typosquatting tên package, compromised publisher và cache poisoning cũng là rủi ro.

### Biện pháp

1. Cấu hình repository order/namespace ownership và routing rõ.
2. Dùng internal proxy/mirror có policy, không thêm repository tùy tiện trong mọi pom.xml.
3. Pin dependency/plugin versions, tránh SNAPSHOT/dynamic ranges trong release khi không được phép.
4. Dùng checksum/signature verification khi tool/repository hỗ trợ.
5. Giới hạn credentials của package feed.
6. Kiểm tra SBOM và dependency tree sau resolve.
7. Có cơ chế quarantine/disable package bị phát hiện độc hại.

**SBOM giúp phát hiện package đã vào artifact**, nhưng không ngăn package độc hại được chạy trong build nếu policy không kiểm soát dependency resolution trước.

## 46. Build secrets: không đưa vào ARG hoặc provenance

Một Dockerfile như sau là rủi ro:

~~~dockerfile
# ANTI-PATTERN: đừng dùng cho secrets.
ARG PRIVATE_REPO_PASSWORD
RUN echo "$PRIVATE_REPO_PASSWORD" > /tmp/repo-password
~~~

Build arguments/commands/logs, image history hoặc provenance metadata có thể làm lộ giá trị. Cần dùng **build secret mounts**, credentials ngắn hạn và cấu hình build environment theo tool/version được hỗ trợ.

### CI secret handling

- Không echo access tokens.
- Không để docker build context chứa **.env**, private keys hoặc vault exports.
- Tạo **.dockerignore** và kiểm tra build context.
- Không export signing key material vào workspace nếu KMS signing có thể dùng remote cryptographic operations.
- Bật masking logs nhưng không dựa hoàn toàn vào masking.
- Tách PR build khỏi release secrets.

**Provenance mode chứa nhiều thông tin hơn không luôn an toàn hơn** nếu pipeline ghi sensitive build inputs vào metadata. Phải thiết kế secret boundary trước khi tăng verbosity.

## 47. Reproducible build và provenance có tương đương?

**Reproducible build** nghĩa là có thể tái tạo output byte-for-byte khi dùng đầu vào/điều kiện đã xác định, trong phạm vi phương pháp tái lập. **Provenance** ghi quá trình tạo artifact; một build không hoàn toàn reproducible vẫn có thể có provenance hữu ích.

### Những nguồn gây không tái lập

- Timestamp ngẫu nhiên trong JAR/container layer.
- Dependency versions không khóa.
- Base image tag đổi.
- Build plugin/toolchain thay phiên bản.
- Hệ điều hành/locale/timezone khác.
- Các file/secret được tải động không có content digest.
- Build cache bị nhiễm hoặc shared state.

### Giá trị của reproducibility

Nếu một builder độc lập dùng cùng inputs tạo đúng digest, nó cung cấp thêm bằng chứng rằng output không bị thay đổi ngoài dự kiến. Nhưng **hai builders có thể cùng dùng dependency độc hại**, nên reproducibility không chứng minh source an toàn.

## 48. Tách build, sign, verify và deploy

Kiến trúc trách nhiệm rõ:

~~~text
BUILD
  Inputs: source + dependencies + pinned base
  Output: image digest + build SBOM
     |
     v
PUBLISH
  Push immutable image digest to ACR
     |
     v
ATTEST + SIGN
  Image SBOM + provenance, trusted release identity
     |
     v
VERIFY
  Signature, issuer, source, builder, subject, policy
     |
     v
DEPLOY
  AKS/Container Apps/App Service pin approved digest
     |
     v
OBSERVE
  Running digests, CVE advisories, runtime issues
~~~

### Tại sao không dùng cùng identity?

Nếu build job có thể sửa policy, xóa registry evidence, ký mọi image và deploy prod mà không cần approval, một compromise build runner có thể làm toàn bộ chuỗi bị vượt qua. Tách permissions, environments và control plane là defense in depth.

## 49. Verify trước khi deploy: kiểm đúng chữ ký

Với hệ sinh thái **Cosign keyless**, verifier cần kiểm tra identity/issuer được phê duyệt và image digest. Một hình thức ví dụ:

~~~bash
# Chỉ là command skeleton; không dùng placeholder cho production.
cosign verify \
  --certificate-identity "<APPROVED_RELEASE_WORKFLOW_IDENTITY>" \
  --certificate-oidc-issuer "<APPROVED_OIDC_ISSUER>" \
  "registry.example/checkout-api@sha256:<REAL_DIGEST>"
~~~

### Lưu ý

- Syntax/flags và certificate identity format phải kiểm tra với Cosign version.
- Một số kiểu ký/verification dùng trust root hoặc public key khác.
- Certificate identity/issuer phải là **giá trị chính xác từ trusted workflow** chứ không đặt wildcard quá rộng.
- Phải xác minh đúng **image reference by digest**, không chỉ tag.
- Verification command này chưa kiểm đầy đủ **provenance predicates/SBOM policy**.

### Attestation cũng cần verify

Để đạt policy “source phải là protected main và builder phải là workflow X”, verifier phải đọc **provenance attestation đã xác minh signature**, sau đó kiểm tra các thuộc tính source/builder theo schema. Không chỉ nhìn một đoạn JSON bất kỳ và tin ngay.

## 50. Policy-as-code cho AKS

AKS có thể dùng **Kubernetes admission controls**, Azure Policy integrations hoặc các engines được hỗ trợ như Gatekeeper/Kyverno để áp policy về images. Tính năng verify signed images/attestations cụ thể phụ thuộc engine, phiên bản và cấu hình.

~~~text
GitOps/CI submits Deployment
        |
        v
Kubernetes API admission
        |
        +-- Registry allowlist
        +-- Digest pin requirement
        +-- Signature/attestation verification (if supported)
        +-- Source/builder/predicate policy
        |
        +---- PASS ---> Accepted PodSpec
        |
        +---- FAIL ---> Rejected with audit event
~~~

### Những policy thực tế

1. Chỉ chấp nhận images từ **ACR repos được duyệt**.
2. Ưu tiên image **@sha256 digest**, không deploy mutable tag.
3. Release image phải có chữ ký từ **trusted pipeline**.
4. Provenance subject khớp digest và source repo/ref được duyệt.
5. SBOM attestation hợp lệ và đủ metadata theo policy.
6. Có exception rule cho sandbox và emergency break-glass, không áp mọi namespace như nhau khi chưa kiểm thử.

### Không gây outage vì verifier không được chuẩn bị

- Registry/attestation fetch có thể bị network timeout.
- Policy engine fail-open/fail-closed là quyết định an toàn/vận hành.
- OIDC verification/trust root cần updates.
- Cluster có workloads hệ thống không do pipeline ứng dụng ký.
- Rollout policy nên thử **audit mode** trước enforce khi engine hỗ trợ.

**Không khẳng định Azure Policy mặc định đã verify Cosign signatures của mọi image**; phải cài đặt và cấu hình capability thực tế.

## 51. Azure Container Apps và App Service dùng image digest

Ngoài AKS, Azure Container Apps và App Service for Containers có thể chạy image được lấy từ registry theo khả năng cấu hình từng dịch vụ.

### Nguyên tắc chung

- Cấp **pull permission** tối thiểu cho runtime identity.
- Dùng immutable image digest reference ở nơi platform cho phép.
- Xác minh artifact trước khi cập nhật deployment resource.
- Lưu mapping **release → digest → SBOM → provenance**.
- Kiểm tra vùng/registry connectivity và auth.
- Nếu platform không có admission verify attestations, áp policy gate trong CI/CD/deployment automation rồi giám sát drift sau triển khai.

**Không nói một image có signature thì App Service/Container Apps sẽ tự kiểm tra signer trước khi pull.** Verification cần được tích hợp vào luồng phát hành theo khả năng nền tảng.

## 52. Cảnh báo với image tag và rollout thực tế

Giả sử pipeline đã verify:

~~~text
checkout-api:stable -> digest A
~~~

Nhưng trước khi deploy, người khác đẩy tag stable trỏ tới digest B. Nếu Deployment dùng tag **stable**, kết quả có thể khác artifact đã verify.

### Cách ngăn TOCTOU

1. Resolve tag thành **digest A** sau publish.
2. Verify signature/provenance/SBOM của **digest A**.
3. Deploy **@sha256:A**, không sử dụng lại mutable tag.
4. Kiểm tra Pod image IDs/digests thực khi rollout.
5. Giám sát nếu workload drift sang digest khác.

**Time-of-check-to-time-of-use (TOCTOU)** là rủi ro khi artifact được kiểm tra ở một trạng thái nhưng dùng sau khi tham chiếu mutable đổi.

## 53. Release record: bằng chứng nào cần lưu?

Một bản ghi phát hành:

| Trường | Giá trị minh họa |
|---|---|
| Service | checkout-api |
| Environment | production |
| Application version | 1.8.0 |
| Source repo | org/checkout-api |
| Source commit | Full Git SHA |
| CI system/run | Azure DevOps run ID |
| Builder identity | Trusted pipeline identifier |
| Maven/Gradle toolchain | Approved pinned versions |
| Base image | Immutable digest reference |
| Final image | ACR repository@sha256:digest |
| SBOM | CycloneDX document digest/referrer |
| Provenance | SLSA/in-toto statement reference |
| Signer | Verified issuer/key/workflow identity |
| Scanner results | Tool/database version, timestamp, exception IDs |
| Approval | Reviewer/environment gate |
| Deployment | AKS namespace/revision/rollout ID |
| Rollback | Previously approved image digest |

**Không lưu secrets, service principal passwords hoặc signing private keys trong release record.**

## 54. Artifact provenance cho JAR ngoài container

Không phải mọi Azure Java application đều chạy từ container. Một **Spring Boot JAR** deploy lên App Service bằng package-based flow vẫn là artifact cần kiểm soát:

~~~text
Git commit
   |
   v
Maven build -> checkout-api.jar
                 |
                 +--> SHA-256 of exact JAR bytes
                 +--> Build-resolved SBOM
                 +--> Signed provenance statement
                 |
                 v
         Azure Artifacts / approved artifact store
                 |
                 v
         App Service deployment
~~~

### Điểm khác container

- Digest cần tính trên **JAR/package bytes**, không dùng OCI manifest digest nếu không có image.
- SBOM cần gắn với JAR/package fingerprint và dependencies thực sự bundled.
- Artifact store/CI release process phải hỗ trợ lưu signatures/attestations/verification evidence hoặc có ledger riêng.
- Runtime App Service có thể cung cấp thêm các system dependencies ngoài JAR; assessment phải cân nhắc host runtime.

**JAR checksum không tự xác nhận JAR đã được tạo từ đúng commit**; cần provenance và trusted signer.

## 55. SBOM khi có third-party SaaS và vendor libraries

Một tổ chức còn có commercial SDK/JAR hoặc binary chỉ phát hành qua vendor registry. Các thành phần này vẫn thuộc supply chain.

### Quy trình

1. Yêu cầu vendor cung cấp SBOM/provenance/license/advisory feeds khi phù hợp.
2. Xác minh signature/checksum và source distribution channel.
3. Ghi những thành phần opaque vào inventory và risk acceptance nếu không thể phân tích đầy đủ.
4. Nếu vendor SBOM không khớp package thực, báo owner và xác minh trước production.
5. Không tự tuyên bố vendor binary sạch chỉ vì phần mềm do nhà cung cấp lớn phát hành.

**Bằng chứng thiếu phải được ghi là thiếu**, không tự thêm các package assumptions vào SBOM như thể đã kiểm chứng.

## 56. Quản trị nhiều môi trường dev, staging và production

Một tổ chức có thể có:

~~~text
DEV
  ACR repository checkout-dev
  unsigned or test-signed images, restricted namespace
          |
          v
STAGING
  Trusted release digest verified
  SBOM, provenance and integration tests
          |
          v
PRODUCTION
  Same digest or approved promotion artifact
  Verified signature/attestation and environment gate
~~~

### Những nguyên tắc quan trọng

- **Không rebuild image khi promote** nếu mục tiêu là chuyển đúng bytes đã thử ở staging.
- Nếu phải copy image sang registry khác, kiểm tra **digest và evidence có được preserve** theo OCI tooling.
- Các environment có thể dùng config/identity khác nhau nhưng artifact digest vẫn cùng một release.
- Mỗi environment có quyền pull/deploy và approval boundary khác.
- PR builds dùng signing identity test riêng hoặc không ký release; prod chỉ tin cậy release signer.

### Promotion không đồng nghĩa tự an toàn

Một image đã qua staging có thể bị phát hiện CVE critical sau đó. Policy cần xem thời điểm scan, trust, exceptions và advisory freshness; không chỉ tin release sticker “tested”.

## 57. SBOM diff giữa hai bản phát hành

So sánh **SBOM A** và **SBOM B** giúp thấy:

- Package mới thêm.
- Package bị xóa.
- Package đổi version.
- Base image hoặc OS component thay đổi.
- Component identifiers/relationships bị mất.
- License metadata đổi.

~~~text
Release 1.8.0                      Release 1.8.1
  azure-identity X                    azure-identity Y     UPDATED
  spring-web A                        spring-web A        UNCHANGED
  JSON library B                      JSON library C      UPDATED
  old-logging-helper                  (removed)           REMOVED
                                     new-metrics-lib      ADDED
~~~

### Không so diff chỉ bằng text lines

SBOM có thể khác thứ tự JSON fields, generated timestamps và bom-ref IDs dù component set giống nhau. Dùng công cụ so sánh có hiểu component identity/purl/dependencies; khi cần kiểm chứng byte-level, xem hashes/digests.

### Khi nào diff là tín hiệu xấu?

Một release chỉ sửa HTML nhưng SBOM bất ngờ có 50 native packages mới hoặc HTTP client đã đổi major có thể là dependency/base image drift. Cần điều tra, không tự động coi mọi thay đổi là tấn công.

## 58. CVE advisory xuất hiện sau khi release

Một kịch bản phổ biến:

~~~text
Day 0: Release 1.8.0 scan has no known critical issues
Day 14: New critical advisory published for package X
Day 15: Rescan stored SBOM shows affected versions
Day 16: Rebuild fixed release, verify provenance, deploy
~~~

### Vì sao SBOM cần lưu?

Không cần rebuild hoặc kéo mọi source để tìm xem release cũ chứa thư viện nào. Có thể đối chiếu inventory từ các artifacts đang chạy/historical releases với advisory mới.

### Nhưng không thay scanner runtime

SBOM từ build có thể bỏ sót package được tải lúc runtime hoặc binary được cài bằng script khi container start. Cần runtime visibility, image scanning và build policy để giảm khoảng trống đó.

## 59. Azure Defender for Cloud và registry scanning

**Microsoft Defender for Cloud** có những tính năng đánh giá bảo mật/vulnerability cho container registries/images/workloads tùy **gói, cấu hình, phạm vi và khả năng đang hỗ trợ**.

### Dùng đúng vai trò

- Container image scanning giúp nhận diện thành phần có CVE.
- Runtime/workload security có thể cung cấp tín hiệu bổ sung.
- Azure Policy có thể hỗ trợ các guardrails liên quan cấu hình/registries.
- Release pipeline vẫn cần quản lý artifact digest, provenance, signer và policy.

**Không tuyên bố bật Defender nghĩa là đã có SLSA provenance, chữ ký Cosign hoặc admission verify**. Các năng lực đó là những lớp khác; phải xác minh tích hợp thực đang vận hành.

### Phân loại phát hiện

| Phát hiện | Hướng xử lý |
|---|---|
| CVE trong Java JAR | Dependency graph/BOM upgrade và test |
| CVE trong OS package | Base image refresh, rebuild, scan |
| Image từ registry không duyệt | Policy/admission và source validation |
| Image digest khác release record | Registry/deployment drift investigation |
| Signature không hợp lệ | Block rollout, điều tra trust/signer |
| Provenance source lạ | Quarantine artifact, xem CI identity/workflow |
| SBOM không đủ component metadata | Cải thiện generator/coverage, không bỏ policy bừa bãi |

## 60. Builder compromise: khi nào phải mất niềm tin?

Giả sử CI runner bị xâm nhập giữa lúc build:

~~~text
Reviewed source commit -> compromised builder
                              |
                              v
                        malicious image
                              |
                              v
                      signed by release identity
~~~

Trong tình huống này, signature có thể hợp lệ nhưng nguồn gốc **builder integrity** đã bị phá. Provenance ghi tên builder nhưng không tự ngăn builder nói dối khi đã bị chiếm.

### Hành động incident

1. Đình chỉ builder/pipeline/release identity có nguy cơ.
2. Khoanh vùng danh sách run IDs, source commits và **output digests**.
3. Tìm production/staging workloads đang chạy những digests đó.
4. Tạm dừng deployments từ compromised trust root.
5. Rotate/revoke signing credentials/trust theo loại khóa/danh tính và policy.
6. Tái tạo artifacts bằng clean trusted builder, không chỉ re-sign image cũ.
7. Kiểm tra dependency caches, runner images, secrets và external actions/tasks.
8. Lập timeline/forensic evidence, thông báo theo incident response.

**Không xóa sạch logs/bundles ngay khi phát hiện compromise**; cần giữ bằng chứng theo chính sách, đồng thời bảo vệ secrets bị ảnh hưởng.

## 61. Signing key rotation và trust root rollover

Khi khóa ký hoặc identity certificate thay đổi:

~~~text
Verifier trusts signing key/identity A
       |
       v
Prepare new signer B; distribute trust policy
       |
       v
Test signed artifact with B in staging
       |
       v
Production begins accepting B under approval
       |
       v
Stop signing new releases with A
       |
       v
Retire A trust per time-bound policy
~~~

### Những điểm cần lưu ý

- Historical artifacts ký bằng A vẫn cần có thể được điều tra/verify theo retention policy.
- Nếu A bị **compromise**, không tiếp tục tin chữ ký A chỉ để thuận tiện.
- Keyless trust roots/issuer configurations cũng cần cập nhật và audit.
- Không thay issuer/trust policy và deployment tooling đồng thời nếu chưa có test.
- Có cơ chế rollback/quarantine theo sự kiện.

## 62. Policy exceptions và break-glass

Không phải mọi vulnerability được khắc phục ngay. Một package có advisory nhưng vendor chưa có patch, hoặc một image phục vụ khắc phục outage cần triển khai khẩn.

### Một exception hợp lệ cần

1. **Artifact digest cụ thể**, không bỏ qua toàn registry.
2. CVE/advisory hoặc policy rule cụ thể.
3. Owner có quyền phê duyệt và lý do kinh doanh.
4. Thời điểm bắt đầu/hết hạn.
5. Compensating controls: network isolation, feature off, WAF, RBAC.
6. Evidence và kế hoạch sửa triệt để.
7. Monitoring tăng cường trong thời gian exception.

**Không tạo exception “allow unsigned images forever”** chỉ vì một lần Cosign verify thất bại do network. Kiểm tra trust root, attestation availability và cân nhắc break-glass có audit theo thời hạn.

## 63. Lab A: tạo Maven SBOM từ ứng dụng Java lab

**Mục tiêu:** tạo SBOM và hiểu dependency graph cho một ứng dụng Java nhỏ mà chưa deploy Azure.

### Chuẩn bị

- Repository/lab project Maven được phép sử dụng.
- JDK, Maven và CycloneDX Maven plugin version được duyệt.
- Môi trường có mirror/repository tin cậy và không cần secrets production.
- Nếu dự án nhiều modules, chạy từ root Maven reactor.

### Các bước

1. Tạo hoặc chọn một Spring Boot app lab có hai direct dependencies, ví dụ **azure-identity** và **azure-storage-blob**.
2. Kiểm tra pom.xml/approved BOM versions.
3. Thêm CycloneDX Maven plugin theo mục 11, thay placeholder plugin version.
4. Chạy **mvn -B -ntp verify** trong môi trường lab.
5. Xác minh **target/bom.json** (hoặc path thực của plugin) tồn tại.
6. Validate theo schema CycloneDX version đã chọn bằng tool được duyệt.
7. Đọc components: name, version, purl và type.
8. Tìm **azure-core** trong SBOM và Maven dependency tree: đây có thể là transitive component.
9. So sánh số direct và transitive dependencies, ghi gaps nếu plugin không thấy một module.
10. Không commit file SBOM chứa dữ liệu môi trường nội bộ nếu policy cấm; lưu làm CI artifact trong phạm vi lab.

### Một cách quan sát components (cần jq được cài đặt)

~~~bash
jq -r '.components[]? | [.name, .version, .purl] | @tsv' \
  target/bom.json
~~~

### Nghiệm thu

| Kiểm tra | PASS khi |
|---|---|
| Generator | Plugin version pinned và có metadata |
| Format | CycloneDX JSON hợp lệ theo validator |
| Scope | Reactor/profiles đúng với dự án lab |
| Components | Có direct và transitive runtime components |
| Identifiers | Có tên, version và purl khi phát hiện được |
| Privacy | Không có credentials/secret trong output |
| Bằng chứng | Ghi build run và artifact digest/hash phù hợp |

## 64. Lab B: so sánh SBOM Maven và final container image

**Mục tiêu:** chứng minh container image chứa nhiều thứ hơn Java dependencies.

### Chuẩn bị

- Docker/Buildx hoặc image tooling được phép.
- Registry/image lab, tuyệt đối không dùng quyền push production.
- Syft đã được pin và cài từ nguồn tin cậy.
- Image digest hợp lệ sau build/push.

### Thực hiện

1. Sinh build-resolved SBOM bằng Maven theo Lab A.
2. Build Docker image lab từ JAR, dùng base image đã duyệt.
3. Push vào ACR lab hoặc dùng local image theo workflow được phép.
4. Ghi **final immutable digest**, không chỉ tag.
5. Dùng **Syft** tạo CycloneDX JSON cho image digest.
6. Validate schema của hai SBOM.
7. Đối chiếu Maven libraries có trong image không.
8. Liệt kê OS/base-image packages mới xuất hiện.
9. Kiểm tra JRE và các agents/scripts cài vào final image.
10. Viết rõ **coverage limitations**, không tự giải thích mọi difference là package bị sửa.

### Sản phẩm

~~~text
sbom-java.cdx.json
sbom-image.cdx.json
image-digest.txt
comparison-report.md
~~~

Các tên trên là **đầu ra lab đề xuất**, không phải yêu cầu ghi thêm file trong nhiệm vụ STEP 4 worker này.

## 65. Lab C: phát hiện SBOM không khớp artifact digest

**Mục tiêu:** hiểu kiểm tra tính toàn vẹn của evidence mà không cần signing keys production.

### Tình huống giả định

~~~text
SBOM A:
  subject = checkout-api@sha256:DIGEST_A

Image ở deployment:
  checkout-api@sha256:DIGEST_B
~~~

### Hướng giải

1. Kiểm tra digest A/B là OCI index hay platform-specific manifest.
2. Xác minh release record và tag→digest mapping.
3. Kiểm tra attestation **subject** thực, không chỉ tên file.
4. Nếu không cùng artifact, **không chấp nhận SBOM A để làm bằng chứng cho B**.
5. Tìm đúng SBOM/provenance của DIGEST_B hoặc tạo lại bằng trusted process.
6. Đảm bảo verifier policy dừng rollout nếu thiếu bằng chứng.

### Bài học

Một file SBOM đúng chuẩn vẫn **không liên quan** tới artifact đang chạy nếu subject mismatch. Chữ ký trên SBOM A cũng không làm nó trở thành SBOM cho image B.

## 66. Lab D: giả lập policy-as-code với evidence

**Mục tiêu:** suy luận quy tắc release mà không cần triển khai admission controller production.

### Policy giả định

~~~yaml
policy:
  allowedRegistry: myregistry.azurecr.io
  requireDigest: true
  requireTrustedSigner: true
  requireProvenance: true
  allowedSourceRepository: org/checkout-api
  allowedReleaseBranch: main
  requireSbomSubjectMatch: true
  maxUnapprovedCriticalVulnerabilities: 0
~~~

**Đây là YAML mô tả ý tưởng, không phải cấu hình hợp lệ của Kyverno, Gatekeeper hay Azure Policy.**

### Đánh giá các trường hợp

| Case | Kết quả mong đợi |
|---|---|
| Image từ ACR allowlist, digest pin, signature/provenance/SBOM đầy đủ | Có thể pass sau CVE/license checks |
| Image tag stable, không pin digest | Block |
| Image có chữ ký nhưng signer không được trust | Block |
| SBOM subject A, deployed digest B | Block |
| Provenance source ở untrusted fork | Block |
| Có Critical CVE chưa được approved exception | Block theo policy giả định |
| Registry/signature lookup timeout | Xử lý theo fail-closed/break-glass strategy đã duyệt |
| Image phục vụ hệ thống cluster không theo app pipeline | Policy scope/exception riêng có review |

### Nghiệm thu

Người học phải giải thích **vì sao** mỗi trường hợp được chấp nhận/từ chối, sự khác nhau giữa policy intent và verification implementation, và cách tránh chặn nhầm workloads hệ thống.

## 67. Lab E: kiểm tra provenance và chữ ký trong registry lab

**Mục tiêu:** học phân biệt signer, provenance và artifact subject trên các bằng chứng được phát hành từ pipeline thử nghiệm.

### Điều kiện

- Một image được build/push bằng trusted **lab** pipeline.
- Signatures/attestations thử nghiệm do công cụ đã được cấu hình phát hành.
- Cosign/OCI tooling version được phê duyệt.
- Identity read-only tới registry; không cần signing private key để verify.

### Quy trình

1. Xác định chính xác **image@sha256:digest**.
2. Đọc image manifest và xác nhận platform/index.
3. Tìm SBOM artifact/referrer hoặc nguồn lưu evidence tương ứng.
4. Xem SBOM subject/metadata và components.
5. Dùng Cosign verify theo **trusted identity/issuer** của lab.
6. Xem provenance predicate bằng verifier tương ứng đã xác thực chữ ký.
7. Kiểm tra **source repository, commit, builder, workflow và subject digest**.
8. So sánh với release record.
9. Chạy thử xác minh một image khác chưa được ký hoặc signer không được trust.
10. Ghi observed behavior và lý do policy fail.

**Không tự tạo chữ ký production hoặc nâng registry permissions** chỉ để hoàn thành bài. Nếu registry/tool không hỗ trợ referrers theo dự kiến, ghi giới hạn thay vì giả mạo kết quả PASS.

## 68. Case study: checkout Java trên Azure

Một doanh nghiệp có hệ thống thương mại:

- Source lưu trong Git, Java 21 và Maven multi-module.
- Pipeline release chạy trong Azure DevOps với workload identity federation.
- Spring Boot fat JAR được đóng gói vào image từ một JRE base image.
- ACR lưu image và OCI artifact metadata.
- AKS chạy checkout-api; Azure Container Apps chạy notification worker.
- Microsoft Defender for Cloud cung cấp một số findings container image.
- Quy định: production phải chạy **image digest đã được verify**, có SBOM và provenance từ approved builder.
- Cần giữ evidence để điều tra CVE/incident sau sáu tháng.

### Sự cố

Một advisory critical xuất hiện trong dependency bắc cầu. Dashboard Defender báo image digest B có vấn đề, nhưng team cho rằng release pipeline vừa nâng dependency và đã push tag **stable**. Một kỹ sư phát hiện Pod AKS vẫn dùng digest B, trong khi SBOM vừa lưu từ pipeline lại gắn digest C.

### Nhiệm vụ

1. Chỉ ra vì sao tag stable không thể dùng như identity release.
2. Xác định digest đang chạy ở AKS và notification worker.
3. Tìm SBOM/provenance của **digest B**, không dùng tài liệu digest C để thay.
4. Phân tích dependency vulnerable trong Maven graph và final image.
5. Phân biệt CVE ở Java JAR hay base OS package.
6. Kiểm tra builder/workflow/source commit của digest B.
7. Đánh giá signer identity/trust root và integrity of attestations.
8. Xem ACR tag mutation, IAM và release history.
9. Thiết kế patch/rebuild từ clean trusted builder.
10. Đề xuất cách giữ nguyên image digest khi promotion staging→prod.
11. Thiết kế AKS admission policy ngăn deploy tag mutable.
12. Thiết kế pipeline verification cho Container Apps nếu không có admission gate tương tự.
13. Lập remediation SLA theo exploitability, không chỉ CVSS.
14. Lập kế hoạch rollback khi patch gây lỗi nghiệp vụ.
15. Chỉ ra loại logs/evidence phải giữ phục vụ postmortem.

### Phân tích tham khảo

~~~text
Production AKS:
  digest B -- vulnerable dependency confirmed by SBOM B

Recent pipeline:
  digest C -- fixed dependency, SBOM C, provenance C

Mutable tag stable:
  currently points to C, but running Pods still have B
~~~

**Hành động:** không sửa SBOM B; chuẩn bị verified digest C hoặc build digest mới D nếu C chưa qua policy, thử staging, deploy đúng digest, xác nhận Pod image IDs/digests và rescan. Nếu cần rollback, chỉ về một digest đã được xác minh còn phù hợp security policy hoặc dùng approved emergency exception.

## 69. Case study: artifact bị thay trong pipeline

Một nhà cung cấp third-party build step bị xâm nhập. Workflow production được phép chạy step đó và tạo ra image mới; SBOM vẫn liệt kê dependencies bình thường, chữ ký release hợp lệ vì pipeline có signing privileges.

### Điều gì đã thất bại?

- SBOM không phát hiện mọi hành vi độc hại.
- Signing chỉ chứng minh một danh tính đã ký artifact.
- Builder/script trust boundary bị phá.
- Provenance có thể xác nhận workflow nào chạy, nhưng không ngăn workflow thực thi code độc hại.

### Biện pháp phục hồi

1. Chặn third-party action/plugin bị ảnh hưởng.
2. Rotate tokens/credentials theo mức độ compromise.
3. Xác định digests từ những CI run có nguy cơ.
4. Quarantine/rollback workloads theo incident policy.
5. Rebuild từ clean isolated runner với pinned/verified steps.
6. Kiểm thử binary diff/provenance và scan image mới.
7. Ký bằng release identity đã được đánh giá lại.
8. Tăng enforcement để PR không thể thay đổi signing workflow mà không qua protected approval.

**Cải thiện quy trình build và builder integrity là trọng tâm**, không chỉ thêm một scanner SBOM nữa.

## 70. Runbook điều tra artifact không đáng tin

Một sự cố có thể bắt đầu bằng cảnh báo **signature verification failed**, SBOM mismatch hoặc một image digest lạ trong cluster.

### Pha 1 — Xác định phạm vi

1. Ghi tên workload, namespace, environment, thời điểm UTC và source alert.
2. Lấy **running image digests** từ cluster/runtime, không chỉ tag khai báo trong Git.
3. Đối chiếu digest với release ledger, pipeline run và registry metadata.
4. Xác định digests nào bị nghi ngờ, workload/regions nào đang sử dụng.
5. Bảo toàn logs, SBOM, provenance, signatures và CI artifacts theo incident policy.

### Pha 2 — Xác minh bằng chứng

6. Kiểm tra image manifest/index và repository thực.
7. Lấy đúng SBOM có subject digest tương ứng.
8. Verify attestation signature, issuer, signer/workflow identity và trust root.
9. Kiểm tra provenance source repo, commit, builder ID, run ID và materials.
10. Đối chiếu dependency/BOM, scanner results và advisory hiện tại.

### Pha 3 — Quyết định ứng phó

11. Nếu chỉ là **missing evidence**, kiểm tra publishing/registry/network trước; không tự tạo bằng chứng giả.
12. Nếu **untrusted signer/source**, ngừng promotion, quarantine release và báo security.
13. Nếu **compromised builder/key**, khóa trust path, xoay credentials và xác định tất cả digests bị ảnh hưởng.
14. Nếu **critical CVE**, đánh giá exploitability, patch/mitigate và rebuild clean artifact.
15. Nếu **tag drift**, deploy lại immutable verified digest theo runbook.

### Pha 4 — Kiểm chứng và đóng sự cố

16. Rebuild/scan/generate SBOM/provenance/sign từ trusted pipeline.
17. Verify ở staging theo cùng policy như production.
18. Triển khai digest được duyệt và xác nhận runtime đã thực sự dùng digest đó.
19. Theo dõi lỗi ứng dụng, performance, resource consumption và security alerts.
20. Viết postmortem: root cause, detection gaps, control bypass, action owners và deadlines.

### Mẫu bằng chứng an toàn

~~~text
Incident ID:        supply-chain-incident-001
Detected at (UTC):  <TIME>
Service:            checkout-api
Namespace/env:      prod/checkout
Running digest:     sha256:<ACTUAL_DIGEST>
Expected digest:    sha256:<APPROVED_DIGEST>
Source commit:      <FULL_SHA_FROM_VERIFIED_PROVENANCE>
Trusted builder:    <BUILDER_ID>
Signature:          verified / failed / missing
SBOM subject:       matches / mismatch / missing
Open findings:      <ADVISORY_IDS>
Impact:             <KNOWN_FACTS>
Hypothesis:         <UNVERIFIED_HYPOTHESES>
Owner:              <TEAM>
Remediation:        <APPROVED_PLAN>
~~~

Không ghi private keys, credentials, raw CI tokens hoặc PII trong incident report.

## 71. Giám sát và chỉ số hiệu quả của supply-chain controls

Việc sinh SBOM không nên chỉ là một bước xanh trong CI. Các chỉ số vận hành:

| Chỉ số | Ý nghĩa |
|---|---|
| **% release artifacts có SBOM hợp lệ** | Mức bao phủ inventory |
| **% prod digests có provenance đã verify** | Mức bao phủ nguồn gốc |
| **% releases có trusted signature** | Mức bao phủ ký artifact |
| **% workloads dùng digest pinning** | Kiểm soát mutable tags |
| **% image components được nhận diện** | Chỉ báo coverage (cần định nghĩa đo) |
| **Số policy failures theo nguyên nhân** | Registry/signature/source/SBOM/CVE |
| **Thời gian từ advisory đến xác định affected digests** | Tốc độ incident triage |
| **Thời gian từ patch đến verified deploy** | Remediation lead time |
| **Số production exceptions còn hiệu lực** | Risk backlog |
| **Số expired/compromised signing credentials** | Trust management health |
| **Số artifacts thiếu retention evidence** | Audit readiness |
| **Tỉ lệ false positives của gate** | Chất lượng policy |

### Đừng biến coverage thành chỉ số dễ lách

Một SBOM chứa chỉ một component được tạo tự động vẫn làm “SBOM present” thành 100%, nhưng không đủ đánh giá. Đặt tiêu chí **schema, runtime/component coverage, subject match, generator integrity và verification**.

## 72. Chi phí và giới hạn của kiểm soát supply chain

Những chi phí có thể xuất hiện:

- CI runners và thời gian build/test/scanning.
- Storage pipeline artifacts, cache, SBOM/provenance.
- Azure Container Registry storage, traffic/replication và retention.
- Vulnerability-scanning services/Defender theo gói.
- Azure Key Vault signing operations và key/HSM tier khi dùng.
- OCI artifact referrers/metadata storage theo registry.
- Azure Monitor/Log Analytics log ingestion cho verification/admission events.
- Cluster admission controller resources và latency.
- Engineering time để xử lý false positives và dependency upgrades.

### Chi phí không chỉ là hóa đơn Azure

Kiểm soát quá yếu có thể dẫn tới incident nghiêm trọng; kiểm soát quá cứng/triển khai sai có thể chặn production rollouts và làm tăng MTTR. Thiết kế policy theo risk tier, thử trong staging, áp **audit → enforce** có kiểm chứng khi engine hỗ trợ.

### Cách tối ưu có trách nhiệm

1. Sinh SBOM ở build release và khi image digest được phát hành, tránh chạy scanner đắt trên mọi thao tác không cần.
2. Cache dependencies từ nguồn được duyệt nhưng kiểm tra integrity/expiration.
3. Lưu evidence có retention rõ và index theo digest.
4. Ưu tiên query/find affected digests qua SBOM inventory trước khi quét lại mọi image.
5. Cân bằng vulnerability re-scan và advisory updates.
6. Đo gate latency; cải thiện cache verification theo trust/time window.
7. Không giảm security gate chỉ để tiết kiệm vài giây mà không đánh giá rủi ro.

**Không ghi cứng đơn giá CI/ACR/Key Vault/Defender**, vì region, plan, số requests và bảng giá có thể thay đổi. Dùng Azure Pricing Calculator và Cost Management của tổ chức.

## 73. Các lỗi hiểu sai thường gặp

| Nhận định sai | Vì sao sai | Cách hiểu đúng |
|---|---|---|
| “Maven dependency:tree chính là SBOM đầy đủ của image” | Thiếu base image/JRE/OS, metadata/format | Build SBOM kết hợp final image SBOM |
| “SBOM có file JSON nghĩa là đáng tin” | File có thể bị sửa hoặc không thuộc artifact | Verify subject digest, signer, source |
| “CycloneDX luôn tốt hơn SPDX” | Tùy use case, version, tooling | Chọn chuẩn theo consumer/policy |
| “SBOM bảo đảm không có CVE” | SBOM là inventory | Quét advisory, triage, patch |
| “Scanner 0 Critical là không có mã độc” | Scanner không chứng minh hành vi code | Trusted source/build, tests/runtime security |
| “Mọi package được scanner phát hiện 100%” | Shaded/native/dynamic artifacts có thể bị bỏ sót | Coverage review, multi-source SBOM |
| “Tag 1.8.0 là bất biến” | Tag có thể bị đổi | Pin OCI manifest digest |
| “SHA-256 chứng minh ai tạo image” | Hash chỉ định danh content | Signed provenance/identity |
| “Signature hợp lệ nghĩa là code sạch” | Signer/builder có thể bị lộ | Source/builder policy, scanning, audits |
| “Có signed commit là đã ký JAR/image” | Git commit khác build output | Artifact digest + provenance |
| “Có SLSA JSON là đạt SLSA Level X” | Cấp độ dựa vào builder controls/evidence | Đánh giá specification và assurance thực |
| “Provenance mode=min tự động ký release” | Build metadata khác signature | Sign/verify attestation đúng trust policy |
| “Ký SBOM A dùng được cho image B” | Subject mismatch | SBOM gắn đúng digest |
| “Cosign verify không cần kiểm issuer” | Có thể tin signer không hợp lệ | Allowlist exact identity và issuer |
| “Private ACR tức là image trusted” | Private registry vẫn có malicious push | Least privilege và policy verify |
| “Defender scan tạo ra provenance SLSA” | Scanner và build provenance khác nhau | Thiết kế thêm trusted attestation |
| “App Service tự xác minh Cosign cho mọi image” | Không mặc định | Verification gate trước deploy theo capability |
| “Dùng signing secret chung cho mọi PR” | PR không đáng tin có thể ký release | Tách PR/release permissions |
| “Non-exportable KMS key luôn tương thích Cosign” | Provider/algorithm support khác nhau | Kiểm chứng integration trước |
| “Xóa image cũ thì không cần SBOM cũ” | Audit/CVE hậu kiểm cần evidence | Retention policy cho release evidence |
| “Critical CVE luôn đủ để kết luận bị khai thác” | Advisory match khác exploitability | Context/reachability/forensics |
| “Rollback tag stable là trở về bản cũ” | Tag có thể đã chuyển | Rollback digest đã kiểm chứng |
| “SBOM scan xong là không cần scan lại” | CVE mới xuất hiện sau release | Rescan stored SBOM/advisory updates |
| “Build once hoàn toàn reproducible” | Còn timestamp/cache/toolchain | Reproducibility test và pinned inputs |
| “Attestation tự sinh là bằng chứng độc lập” | Builder có thể tự ghi sai | Trust builder identity và bảo vệ pipeline |

## 74. Checklist production trước khi chấp nhận artifact

| Nhóm | Điều kiện nghiệm thu |
|---|---|
| **Ownership** | Owner của source, builder, scanner, signing, runtime rõ ràng |
| **Source control** | Protected branch/release, review và workflow permissions |
| **Toolchain** | JDK, Maven/Gradle, plugins, Buildx, scanners pin versions |
| **Dependency source** | Approved mirrors/registries, chống dependency confusion |
| **Dependency locking** | Direct/transitive versions có thể xác minh |
| **Base image** | Vendor/source được duyệt, digest pin và patch cadence |
| **Build isolation** | Trusted release runner, untrusted PR tách biệt |
| **Secrets** | Không lộ trong source, build args, logs, provenance/attestations |
| **Build SBOM** | Được sinh từ resolved graph, schema validated |
| **Image SBOM** | Bao phủ final OCI image/JRE/OS packages trong giới hạn scanner |
| **Artifact identity** | Final digest đúng, index/platform semantics rõ |
| **Provenance** | Source commit, builder ID, run ID, materials và subject |
| **Signature** | Trust root, signer identity/issuer được phê duyệt |
| **Attestation** | SBOM/provenance predicates đúng schema, subject match |
| **ACR** | Registry/repo permissions, network, retention và referrers được test |
| **CVE** | Scanner policy, advisory freshness, exceptions có owner/expiry |
| **License** | Metadata đủ để review obligations và unresolved items |
| **CI/CD** | Build, sign, verify, deploy responsibilities được tách |
| **Deployment** | Digest pinning ở AKS/Container Apps/App Service khi hỗ trợ |
| **Admission/policy** | Verify trusted source/signature/attestation theo engine thực tế |
| **Canary** | Triển khai thử, đo SLO và có rollback digest |
| **Evidence storage** | SBOM/provenance/signatures giữ được phục vụ audit/incident |
| **Runtime inventory** | Biết digests thực đang chạy và mapping tới release |
| **Monitoring** | Verification failures, unexpected images, CVE/policy alerts |
| **Incident response** | Builder/key compromise và malicious package runbook |
| **Cost** | CI, scanning, ACR, Key Vault, logging đã được dự trù |
| **Drift** | Phát hiện tag/workload digest khác desired state |

### Quy tắc nghiệm thu cuối cùng

**Chỉ phát hành digest đã được tạo, kê khai, ký và kiểm tra bởi quy trình tin cậy**, đủ evidence theo policy. Khi thiếu dữ liệu, ghi nhận rõ loại bằng chứng thiếu và áp quy tắc exception/deny, không tự ghi PASS cho đẹp dashboard.

## 75. Câu hỏi tự kiểm tra

1. Chuỗi cung ứng phần mềm gồm những mắt xích nào từ Git tới AKS?
2. Vì sao pom.xml không thể mô tả đủ mọi thành phần trong final container image?
3. SBOM là gì và khác vulnerability scan ra sao?
4. Một SBOM nên có những field/component identifiers nào?
5. CycloneDX và SPDX có luôn chuyển đổi metadata không mất mát không?
6. PURL khác SHA-256 digest ở điểm nào?
7. Dependency trực tiếp và dependency bắc cầu ảnh hưởng việc xử lý CVE thế nào?
8. Source SBOM và build-resolved SBOM khác nhau ra sao?
9. Vì sao final image SBOM còn có OS/JRE packages?
10. Shaded JAR có thể làm scanner bỏ sót dependencies như thế nào?
11. Vì sao SBOM không thể chứng minh mọi package đều được nhận diện?
12. Cần gắn SBOM với artifact digest để làm gì?
13. SBOM có chữ ký nhưng subject khác image có sử dụng được không?
14. SPDX license expression có đồng nghĩa đã tuân thủ license không?
15. Maven CycloneDX plugin và Maven BOM khác nhau thế nào?
16. Khi tạo aggregate BOM, vì sao nên chạy ở root reactor?
17. Vì sao Gradle testRuntimeClasspath không hẳn phản ánh production JAR?
18. Syft image scan và Maven plugin có thế mạnh khác nhau nào?
19. Image tag khác OCI manifest digest thế nào?
20. Multi-platform image index ảnh hưởng SBOM coverage ra sao?
21. ACR được dùng cho artifacts/evidence với vai trò gì?
22. Đưa image vào private ACR có tự chứng minh image trusted không?
23. Artifact provenance cần những thông tin nào?
24. Provenance khác signed Git commit ở đâu?
25. SLSA predicate khác SLSA assurance level thế nào?
26. In-toto attestation liên kết subject và predicate ra sao?
27. Ký image và ký SBOM/provenance attestation có khác nhau không?
28. Vì sao verifier phải kiểm cả signing identity và issuer?
29. Keyless signing cần điều kiện CI/OIDC nào?
30. Signing key trong Key Vault cần cấp quyền nào theo least privilege?
31. Transparency log có chứng minh code an toàn tuyệt đối không?
32. OCI referrers và registry cleanup ảnh hưởng retention evidence thế nào?
33. Một SLSA JSON tự viết tay có thể được coi là provenance compliant không?
34. Vì sao release CI phải tách khỏi untrusted PR?
35. Azure DevOps workload identity federation giúp giảm rủi ro gì?
36. GitHub OIDC lấy Azure token có tự là Sigstore signing identity không?
37. Docker Buildx --sbom/--provenance có tự tạo trusted signature không?
38. Vì sao không nên đưa secrets vào Docker ARG và provenance?
39. Reproducible build có tự chứng minh source không có malware không?
40. Tại sao phải verify digest rồi deploy chính digest đó để tránh TOCTOU?
41. Admission controller cần kiểm những điều gì?
42. Azure Policy mặc định có kiểm mọi chữ ký Cosign không?
43. Vì sao App Service/Container Apps cần verification gate riêng tùy capability?
44. Một bản phát hành JAR không container cần những bằng chứng nào?
45. SBOM và SBOM diff giúp triage CVE mới ra sao?
46. Vì sao phải phân biệt CVE Java package và base OS package?
47. Khi signer/builder bị compromise, chữ ký còn là bằng chứng đủ mạnh không?
48. Vì sao key rotation cần cập nhật trust policy của verifier?
49. Policy exception hợp lệ phải giới hạn bằng những thông tin gì?
50. Khi thấy Pod chạy digest B nhưng SBOM là digest C, phải xử lý thế nào?
51. Vì sao tag stable đã đổi không chứng minh Pod đã dùng bản mới?
52. Một release trong ACR có cần giữ evidence sau khi xóa image cũ không?
53. Những metrics nào đo hiệu quả của provenance verification?
54. Quản trị supply chain phát sinh những loại chi phí nào trên Azure?
55. Ba quyết định quan trọng nhất để không triển khai một artifact không rõ nguồn gốc là gì?

## Tài liệu tham khảo

- Microsoft Learn — *Azure Container Registry overview*: https://learn.microsoft.com/azure/container-registry/container-registry-intro
- Microsoft Learn — *Azure Container Registry authentication*: https://learn.microsoft.com/azure/container-registry/container-registry-authentication
- Microsoft Learn — *Azure Container Registry repository management*: https://learn.microsoft.com/azure/container-registry/container-registry-repositories
- Microsoft Learn — *Workload identity federation for Azure DevOps*: https://learn.microsoft.com/azure/devops/pipelines/library/connect-to-azure?view=azure-devops
- Microsoft Learn — *Azure DevOps pipelines overview*: https://learn.microsoft.com/azure/devops/pipelines/get-started/what-is-azure-pipelines?view=azure-devops
- Microsoft Learn — *Managed identities for Azure resources*: https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview
- Microsoft Learn — *Microsoft Defender for Cloud container security*: https://learn.microsoft.com/azure/defender-for-cloud/defender-for-containers-introduction
- Microsoft Learn — *AKS security baseline and policies*: https://learn.microsoft.com/azure/aks/security-best-practices
- Microsoft Learn — *Azure Key Vault overview*: https://learn.microsoft.com/azure/key-vault/general/overview
- Microsoft Learn — *Azure Artifacts*: https://learn.microsoft.com/azure/devops/artifacts/start-using-azure-artifacts?view=azure-devops
- OWASP — *Software Component Verification Standard*: https://owasp.org/www-project-software-component-verification-standard/
- CISA — *Software Bill of Materials*: https://www.cisa.gov/sbom
- CycloneDX — *Specification*: https://cyclonedx.org/specification/overview/
- CycloneDX — *Maven plugin*: https://github.com/CycloneDX/cyclonedx-maven-plugin
- CycloneDX — *Gradle plugin*: https://github.com/CycloneDX/cyclonedx-gradle-plugin
- SPDX — *Specification*: https://spdx.dev/specifications/
- Package URL — *PURL specification*: https://github.com/package-url/purl-spec
- Anchore — *Syft documentation*: https://github.com/anchore/syft
- Anchore — *Grype vulnerability scanner*: https://github.com/anchore/grype
- SLSA — *Specification and provenance*: https://slsa.dev/spec/
- In-toto — *Attestation framework*: https://in-toto.io/
- Sigstore — *Cosign overview*: https://docs.sigstore.dev/cosign/overview/
- Sigstore — *Signing and verifying*: https://docs.sigstore.dev/cosign/signing/overview/
- ORAS — *OCI artifact client documentation*: https://oras.land/docs/
- Open Container Initiative — *Image and Distribution specifications*: https://opencontainers.org/
- Docker — *Build attestations*: https://docs.docker.com/build/metadata/attestations/
- Docker — *Buildx build options*: https://docs.docker.com/reference/cli/docker/buildx/build/
- GitHub Docs — *OIDC with Azure*: https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-azure
- Kubernetes — *Admission controllers*: https://kubernetes.io/docs/reference/access-authn-authz/admission-controllers/
- Kyverno — *Verify Images policies*: https://kyverno.io/docs/writing-policies/verify-images/
- NIST — *Secure Software Development Framework*: https://csrc.nist.gov/Projects/ssdf
- Azure Pricing Calculator: https://azure.microsoft.com/pricing/calculator/
