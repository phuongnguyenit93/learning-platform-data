# Package integrity – Xác minh tính toàn vẹn gói phần mềm trong chuỗi cung ứng

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **package integrity (tính toàn vẹn của gói phần mềm)** trong software supply chain và phân biệt với authenticity, provenance, vulnerability assessment, license compliance và reproducible build.
- Mô hình hóa các đường gói phần mềm đi qua **registry, repository mirror, resolver, cache, build runner, artifact repository, deployment và runtime**; xác định trust boundaries và tác nhân có thể thay đổi nội dung.
- Sử dụng đúng vai trò của **cryptographic digest/checksum, chữ ký số, keyless signing, provenance attestation, dependency lock/verification metadata và SBOM**.
- Xác định các yếu tố làm suy yếu kiểm chứng: tải digest từ cùng nguồn bị chiếm, bỏ qua lỗi xác minh, cập nhật baseline tự động không review, khóa ký bị lộ, package mutable, dependency confusion và transitive dependency bị thay thế.
- Thiết kế cơ chế kiểm chứng phụ thuộc cho **Maven/Gradle** và kiểm soát package của chính tổ chức từ build tới production.
- Viết security requirements và acceptance criteria có thể kiểm chứng cho dependency/artifact integrity, kể cả khi registry, mirror, signing service hoặc CI cache gặp lỗi.
- Xây dựng tests, audit evidence và quy trình xử lý finding từ **risk → requirement → control → verification → evidence → remediation/retest**.
- Tổ chức continuous assurance cho package integrity, thay vì chỉ scan một lần khi release.

## 1. Package integrity là gì?

**Package integrity** là thuộc tính cho biết nội dung của một gói phần mềm, cùng các hiện vật cần thiết để xác định đúng gói đó, **không bị thay đổi trái phép hoặc ngoài ý muốn so với nội dung đã được tin cậy/phê duyệt** tại các điểm trong chuỗi cung ứng.

“Package” có thể là:
- Dependency trực tiếp hoặc bắc cầu của ứng dụng: JAR, POM, Gradle module metadata, thư viện JavaScript/Python và package archives.
- Plugin cho build/test/deploy, compiler toolchain hoặc script thực thi trong pipeline.
- Artifact do tổ chức tự tạo: JAR, WAR, ZIP, container image, Helm chart hoặc release bundle.
- Metadata liên quan đến danh tính và phân giải package: tên, group/namespace, version, repository, dependency graph, manifest và digest.

Một package có cùng tên/version nhưng **bytes khác nhau** có thể làm đổi hành vi build hoặc runtime. Việc thay đổi có thể đến từ attacker, lỗi vận hành, registry/mirror bị chiếm, cache bị nhiễm độc, artifact bị republish, dependency thay đổi do version range hoặc cấu hình resolver sai.

**Security assurance** không chỉ hỏi “đã có checksum chưa?” mà hỏi:

1. Chúng ta đang tin **đúng package nào** và vì sao?
2. Nội dung **ở mỗi lần tải/dùng/deploy** có khớp nội dung đã được phê duyệt không?
3. Phê duyệt đó đến từ **nguồn tin nào** và ai có thể sửa nó?
4. Có bằng chứng kiểm chứng trên **đúng build/deployment/environment** không?
5. Nếu xác minh thất bại, hệ thống **dừng hay vô tình tiếp tục**?
6. Nếu package đã bị sử dụng trước khi phát hiện, có thể tìm và khắc phục phạm vi ảnh hưởng không?

### Ví dụ đầu tiên

Ứng dụng dùng `com.example:report-utils:2.3.1` từ một Maven repository. Ngày đầu, artifact có SHA-256 là `H1`. Vài ngày sau, một mirror bị xâm nhập trả về bytes khác có SHA-256 `H2` nhưng vẫn mang cùng tọa độ `group:artifact:version`.

- Chỉ pin version `2.3.1` **không đảm bảo** bytes không thay đổi.
- Tính SHA-256 của file nhận được chỉ cho biết digest `H2`, **chưa cho biết H2 đúng hay sai**.
- Nếu có expected digest `H1` đã được thiết lập qua quy trình đáng tin và bảo vệ khỏi thay đổi, hệ thống có thể phát hiện `H2 ≠ H1`.
- Nếu expected digest được tải cùng thời điểm từ chính mirror bị chiếm và attacker sửa cả artifact lẫn checksum, phép so sánh có thể vẫn “PASS” giả.
- Nếu có chữ ký đáng tin và policy xác minh signer/identity phù hợp, có thêm bằng chứng về nguồn ký; nhưng khóa/identity có thể bị chiếm, và package được ký vẫn có thể chứa mã độc.

**Điểm cốt lõi:** package integrity là vấn đề **xây dựng chuỗi tin cậy từ quyết định chấp nhận một gói đến thời điểm thực thi nó**, không đơn thuần là bài toán tính hàm băm.

## 2. Ranh giới của package integrity và các khái niệm liên quan

| Khái niệm | Câu hỏi chính | Điều không tự chứng minh |
| --- | --- | --- |
| **Integrity** | Bytes/metadata đang dùng có đúng với nội dung được chấp nhận? | Package an toàn, signer có đáng tin hay không |
| **Authenticity** | Gói/chữ ký có đến từ nguồn hoặc identity được xác minh? | Code không có lỗ hổng hoặc hành vi độc hại |
| **Provenance** | Gói được tạo bởi ai/quy trình nào, từ source/materials nào? | Không có lỗi trong source/build nếu builder/source bị chiếm |
| **Cryptographic hash** | Nội dung này có digest nào? | Digest là expected value đáng tin nếu không có trusted baseline |
| **Digital signature** | Ai nắm signing key/identity đã ký thông điệp? | Signer thực sự không bị compromise và nội dung an toàn |
| **SBOM** | Phần mềm được khai báo gồm những component nào? | Mọi bytes đã được xác minh hoặc component đều hợp lệ |
| **Vulnerability scanning** | Có vulnerability được biết và có khả năng liên quan không? | Package không chứa mã độc hoặc package không bị thay thế |
| **Reproducible build** | Hai môi trường build có tạo kết quả giống nhau khi điều kiện tương đương? | Đầu vào/toolchain đáng tin hoặc source code không độc hại |
| **License compliance** | Việc dùng package có phù hợp điều khoản license không? | Package toàn vẹn và an toàn |
| **Availability** | Có thể tải package đúng lúc không? | Bytes được tải là đáng tin |

Các kiểm soát hỗ trợ lẫn nhau. Không được dùng một kết quả SCA “không có CVE” để thay integrity verification, hoặc dùng chữ ký hợp lệ để tuyên bố đã kiểm tra vulnerability.

## 3. Package đi qua những đâu?

### 3.1. Luồng dependency từ upstream đến runtime

~~~mermaid
flowchart LR
    AUTHOR["Upstream maintainer / publisher"] --> REG["Public registry"]
    REG --> MIRROR["Organization proxy / mirror"]
    MIRROR --> RES["Maven/Gradle resolver"]
    RES --> CACHE["Developer/CI cache"]
    CACHE --> BUILD["Build / tests / packaging"]
    BUILD --> REPO["Internal artifact repository"]
    REPO --> DEPLOY["Deploy / image pull"]
    DEPLOY --> RUN["Runtime"]
    AUTH["Trusted policy / baseline / signer roots"] -. "Verify package and metadata" .-> RES
    AUTH -. "Verify build provenance" .-> BUILD
    AUTH -. "Verify release digest/identity" .-> DEPLOY
    RUN --> EVID["Telemetry / evidence / inventory"]
~~~

Từng mũi tên có thể là một **trust boundary**. Ví dụ:
- Public registry có thể phục vụ package có tên gần giống package nội bộ.
- Corporate mirror có thể lưu trữ bản cũ, bản republish hoặc bị attacker thay.
- CI cache có thể chứa bytes khác source.
- Build runner có thể chạy plugin với quyền truy cập secret và repository.
- Artifact repository nội bộ có thể bị overwrite nếu không có immutable release policy.
- Deployment có thể kéo lại image bằng tag mutable thay vì digest được duyệt.
- Runtime có thể chạy một digest khác digest vừa kiểm tra ở CI.

### 3.2. Dependency có thể thực thi code ngay trong build

Không phải package chỉ “nằm yên” cho tới khi ứng dụng chạy. Một dependency hoặc plugin có thể:
- Tác động đến code generation, annotation processing hoặc test runners.
- Chạy build script/task/plugin có quyền đọc filesystem, biến môi trường và credentials của CI.
- Thay đổi cấu hình, dependency graph hoặc output.
- Được đưa vào ứng dụng và thực thi ở runtime.

Vì vậy, security review phải xét **build-time privileges** lẫn runtime privileges. Artifact độc hại có thể lấy secret CI ngay khi build, không cần chờ deployment.

### 3.3. Các package object cần kiểm kê

| Object | Ví dụ | Vì sao liên quan integrity? |
| --- | --- | --- |
| Binary artifact | `report-utils-2.3.1.jar` | Bytes thực thi được đưa vào classpath |
| Descriptor | `pom.xml` đã publish, module metadata | Quyết định transitive dependencies và variant |
| Build plugin | Maven/Gradle plugin | Có thể thực thi trong CI với quyền mạnh |
| Source archive | Source JAR, tarball | Dùng review/debug/rebuild, cần biết provenance |
| Container image | OCI manifest/layers | Tag có thể trỏ tới digest khác |
| Release metadata | Version, checksums, signatures | Dẫn resolver tới bytes và trust material |
| SBOM/attestation | Component list, build statement | Phục vụ điều tra, nguồn gốc và assurance claims |
| Lock/verification metadata | Dependency versions, expected hashes | Baseline để phát hiện thay đổi ngoài phê duyệt |

## 4. Threat model cho package integrity

### 4.1. Tài sản và các mục tiêu

- **Assets:** source code, dependency graph, release artifact, signing key, CI credentials, registry namespace, cache, build logs, SBOM và production deployment.
- **Objectives:** chỉ dùng package được phê duyệt; phát hiện thay đổi bytes/metadata; xác minh origin và build provenance theo risk; tránh build/deploy artifact sai; giữ bằng chứng; giới hạn blast radius.
- **Entry points:** public registry, repository URL, mirror, dependency resolver, plugin portal, build cache, CI runner, artifact repository, deployment manifest, mutable tag.
- **Trust boundaries:** upstream → registry, registry → proxy, proxy → build, build → artifact store, artifact store → deployment và deployment → runtime.

### 4.2. Risk scenarios tiêu biểu

| Risk ID | Attack/failure scenario | Hậu quả |
| --- | --- | --- |
| **PI-R01** | Attacker republish bytes khác dưới cùng version ở registry/mirror | Thay đổi hành vi dependency âm thầm |
| **PI-R02** | Tên package nội bộ bị resolve từ public registry (dependency confusion) | Tải package attacker thay package nội bộ |
| **PI-R03** | Typo-squatting hoặc namespace impersonation | Developer chọn nhầm package độc hại |
| **PI-R04** | Transitive dependency bị thay nhưng top-level dependency vẫn giữ nguyên | Mã không mong muốn vào build |
| **PI-R05** | Build cache bị nhiễm hoặc CI runner bị chiếm | Artifact khác với source/inputs được tin |
| **PI-R06** | Attacker sửa cả package và checksum ở cùng mirror | Kiểm tra checksum cùng nguồn PASS giả |
| **PI-R07** | Signing key hoặc issuer/workflow identity bị compromise | Chữ ký hợp lệ nhưng nguồn không đáng tin |
| **PI-R08** | Pipeline dùng version dynamic/range hoặc snapshot mutable | Một commit build ra các dependency khác nhau |
| **PI-R09** | Artifact release bị overwrite sau khi kiểm thử | Production chạy binary chưa được đánh giá |
| **PI-R10** | Deployment dùng image tag thay digest được phê duyệt | Tag trỏ đến image khác |
| **PI-R11** | Lỗi xác minh checksum/signature bị ignore hoặc downgrade | Build/deploy tiếp tục với package không được xác minh |
| **PI-R12** | Registry/verification service unavailable, pipeline bật bypass | Trust boundary bị vô hiệu khi outage |
| **PI-R13** | Dependency vulnerability mới xuất hiện nhưng bytes vẫn khớp | Package toàn vẹn nhưng vẫn có nguy cơ khai thác |
| **PI-R14** | SBOM thiếu plugin/transitive component hoặc sai digest | Inventory/evidence không đầy đủ |
| **PI-R15** | Package manager chạy install/build script độc hại | Exfiltrate credential hoặc sửa artifact |
| **PI-R16** | Phê duyệt hash baseline bị cập nhật bởi chính compromised pipeline | Tấn công “hợp thức hóa” bytes bị thay |

### 4.3. Attack path mẫu: mirror bị chiếm

~~~mermaid
flowchart TD
    A["Attacker thay bytes package ở mirror"] --> B["Resolver tải package theo name/version"]
    B --> C{"Có expected digest độc lập, đã review?"}
    C -- "Không" --> D["Lấy checksum cùng mirror hoặc không kiểm tra"]
    D --> E["Build có thể PASS giả"]
    E --> F["Artifact độc hại vào release"]
    C -- "Có" --> G["Tính digest trên bytes nhận"]
    G --> H{"Khớp trusted baseline?"}
    H -- "Không" --> I["BLOCK / quarantine / finding"]
    H -- "Có" --> J["Kiểm tra origin/policy + các gates khác"]
    J --> K["Dùng package trong scope được duyệt"]
~~~

Đường kiểm tra digest giúp phát hiện **bytes khác baseline**; nó không đảm bảo baseline ban đầu được lựa chọn đúng. Quy trình phê duyệt dependency và bảo vệ metadata là phần thiết yếu của kiến trúc.

## 5. Checksum và cryptographic digest

### 5.1. Hash kiểm tra điều gì?

Một hàm băm mật mã như SHA-256 ánh xạ nội dung bất kỳ thành một digest có độ dài cố định. Với giả định thuật toán phù hợp và implementation đúng, việc thay đổi bytes có xác suất rất cao làm digest thay đổi.

Ký hiệu:
- `A`: bytes artifact thực tế.
- `H(A)`: SHA-256 của artifact.
- `D_expected`: digest được chấp nhận theo trusted baseline.

Điều kiện kiểm tra cơ bản:

`H(A) == D_expected`

Dù biểu thức đúng, ta vẫn phải hỏi: **ai xác lập D_expected, từ đâu, vào thời điểm nào, dựa trên kiểm chứng gì và ai có quyền sửa?**

### 5.2. Ví dụ trên Linux/macOS

~~~bash
sha256sum report-utils-2.3.1.jar

# Ví dụ kiểm tra với file chứa expected digest đã được phê duyệt.
sha256sum -c approved-checksums.sha256
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash -LiteralPath '.\report-utils-2.3.1.jar' -Algorithm SHA256
~~~

**Quan trọng:** các lệnh chỉ tính hoặc so sánh digest. Phải quản trị file `approved-checksums.sha256` sao cho attacker không thể thay đồng thời baseline và artifact. Có thể dùng approved manifest trong source repository được review, policy store có kiểm soát hoặc attestation/signature được xác minh với trust root độc lập.

### 5.3. Những điều checksum không làm

- Không xác minh maintainer, repository hoặc signer.
- Không xác minh package an toàn về code hoặc không có lỗ hổng.
- Không chứng minh ai đã build.
- Không chống việc attacker sửa cả expected hash.
- Không bảo đảm transitive dependencies đều đúng nếu chỉ hash một JAR.
- Không chứng minh runtime đang chạy chính bytes đã kiểm tra.

Không dùng MD5/SHA-1 làm biện pháp bảo mật hiện đại cho integrity decision nếu baseline yêu cầu collision resistance; ưu tiên thuật toán mật mã hiện hành như SHA-256 theo standard được tổ chức duyệt.

### 5.4. Hash đúng phải gắn với identity và phạm vi

Một record tốt không chỉ là digest rời rạc mà có:
- Ecosystem/repository.
- Namespace/group/name.
- Version hoặc immutable identifier.
- Artifact classifier/extension/platform nếu liên quan.
- Digest algorithm và value.
- Source/approval reference.
- Thời điểm và người phê duyệt.
- Kênh tiêu thụ: compile/runtime/test/build plugin.
- Scope/environment/target architecture.

Một JAR và POM của cùng tọa độ là **hai objects khác nhau**, có digest riêng và ảnh hưởng khác nhau.

## 6. Chữ ký số và package authenticity

### 6.1. Chữ ký giải quyết gì?

Chữ ký số có thể giúp xác minh rằng một thông điệp/digest được ký bởi khóa phù hợp với public key hoặc identity mà verifier tin cậy. Với package:
1. Publisher/build system ký digest/artifact/attestation.
2. Consumer nhận package và signature/bundle.
3. Verifier kiểm tra cryptographic validity.
4. Verifier đối chiếu signer identity, issuer, key fingerprint, certificate constraints và policy.
5. Verifier kiểm tra digest được ký thực sự khớp bytes đang sử dụng.

**Chữ ký hợp lệ không tự đồng nghĩa package hợp lệ cho dự án.** Nếu attacker có được signing key hoặc chiếm workflow của publisher, package độc hại vẫn có thể được ký. Trust policy phải xét **ai được phép ký package nào** và tình trạng thu hồi/rotation.

### 6.2. Ví dụ detached signature với GPG

~~~bash
# Minh họa cú pháp, không tự coi key bất kỳ trong keyring là trusted.
gpg --verify report-utils-2.3.1.jar.asc report-utils-2.3.1.jar
~~~

Verifier còn phải xác thực fingerprint của public key qua **kênh được tin cậy**, xem chữ ký có dành cho package/release mong đợi không và theo dõi rotation/revocation theo policy. Nếu chỉ import một key từ cùng trang đã bị chiếm và thấy output “Good signature”, không có assurance mạnh về nguồn phát hành.

### 6.3. Keyless signing và transparency log

Các mô hình ký dựa trên identity ngắn hạn (ví dụ hệ sinh thái Sigstore) có thể liên kết chữ ký với workflow/identity, issuer, chứng chỉ và transparency log. Khi áp dụng, verifier cần chính sách rõ về:
- Identity/repository/workflow/ref được phép ký.
- OIDC issuer và certificate constraints.
- Subject digest trùng bytes đã tải.
- Thời điểm ký, điều kiện xác minh timestamp và chứng cứ transparency log theo trust model.
- Trust roots/keys được cập nhật có kiểm soát.
- Khả năng hoạt động khi verification service/offline/outage.
- Cách xử lý khi identity hoặc build workflow bị compromise.

Không chấp nhận **chữ ký bất kỳ** như đủ. Cũng không suy ra attestation là đáng tin chỉ vì nó được phát hành bởi công cụ quen thuộc.

## 7. Provenance, attestation và khả năng xây dựng lại

### 7.1. Provenance là gì?

**Build provenance** là bằng chứng có cấu trúc liên kết artifact với thông tin về quá trình tạo ra nó: source reference, builder/build platform, workflow, input/materials, invocation và output digest trong phạm vi mô hình provenance được áp dụng.

Mục tiêu là trả lời: “Artifact này thực sự được tạo ở đâu, bằng quy trình nào, từ input nào?”. Chuỗi có thể gồm:

~~~mermaid
flowchart LR
    SOURCE["Reviewed source commit"] --> CI["Approved build workflow"]
    MATERIALS["Pinned dependencies / toolchain"] --> CI
    CI --> OUTPUT["Artifact digest"]
    OUTPUT --> ATTEST["Signed provenance attestation"]
    ATTEST --> VERIFY["Verify subject + builder/identity policy"]
    VERIFY --> DEPLOY["Release admission"]
~~~

### 7.2. Điều phải xác minh trong attestation

- **Subject:** attestation nói về đúng digest của artifact được deploy?
- **Signer/identity:** attestation được ký/phát hành bởi identity được policy cho phép?
- **Builder:** build platform/workflow có nằm trong allowlist?
- **Source:** repository, commit/tag và trigger có được kiểm soát?
- **Materials:** dependencies/toolchain/inputs có phù hợp và được ghi lại?
- **Build parameters:** các tham số ảnh hưởng output có được giới hạn?
- **Freshness:** attestation có khớp release/change và time window?
- **Tamper resistance:** attestation không thể bị sửa sau phát hành mà không bị phát hiện?

Nếu attestation mô tả một output khác digest đang chạy, kết luận phải **FAIL** hoặc không đạt theo chính sách. Nếu provenance thiếu thông tin cần thiết hoặc verifier mất trust roots, kết luận có thể **INCONCLUSIVE/FAIL** tùy gate.

### 7.3. Reproducible builds: bổ sung, không thay thế

Reproducibility giúp so sánh output của hai build từ source/inputs và environment được kiểm soát. Tuy nhiên:
- Compiler/toolchain hoặc dependency độc hại vẫn có thể tạo output giống nhau.
- Build script bị compromise có thể vẫn tái tạo được một payload độc hại.
- Timestamp, ordering, environment hoặc archive metadata có thể làm output khác nhau mà không phải tấn công.
- Reproducibility cần có quy trình xác minh đáng tin, không chỉ một cờ trong build.

Reproducibility là **một nguồn assurance bổ sung**, không phải điều kiện đủ cho integrity/authenticity.

## 8. Version pinning, lockfiles và transitive dependencies

### 8.1. Pinning version chưa đủ

Ví dụ:

~~~text
com.example.training:report-utils:2.3.1
~~~

Một version cố định hạn chế tự động đổi version, nhưng chưa đảm bảo artifact với tọa độ đó **không bị republish**. Nếu resolver dùng mirror khác hoặc package metadata bị đổi, build vẫn có thể nhận bytes khác.

### 8.2. Dynamic versions và snapshots

Các biểu thức ví dụ:
- `1.+`
- `latest.release`
- Version range.
- Snapshot/changing module.
- Mutable tag.

Những cách này có thể hữu ích trong quy trình khám phá, nhưng khó đảm bảo cùng source commit luôn nhận **cùng package set và bytes**. Trong release production, nên có dependency constraints/locks và artifact verification phù hợp, quy trình update có review.

### 8.3. Transitive dependencies

Nếu `app` phụ thuộc `library-A`, `library-A` lại phụ thuộc `library-B`, kiểm tra một mình `library-A.jar` là chưa đủ. Cần xem:
- Dependency graph thực tế sau resolution (bao gồm conflict resolution, exclusions, variants).
- Transitive packages và metadata.
- Build plugins và annotation processors.
- Test/runtime classpath khác nhau.
- Package có tải runtime (plugin loader, remote extension) nếu tồn tại.
- Platform-specific/native artifacts.

### 8.4. Lockfile là một lớp, không phải bằng chứng tuyệt đối

Lockfile/verification metadata có thể lưu version, resolved dependency và expected integrity values. Nhưng phải:
- Được commit/review theo quy trình.
- Có ownership và change history.
- Không tự cập nhật trong bước build đang verification rồi coi như thành công.
- Bao phủ các configuration/classpath cần thiết.
- Có quy trình review khi dependency mới xuất hiện.
- Được kiểm tra với artifact bytes, không chỉ với tên/version.

Một lockfile do compromised CI tự sửa và commit có thể biến bytes độc hại thành “approved baseline”; cần **trust boundary độc lập**.

## 9. Gradle: dependency verification cho ứng dụng Java

Gradle có cơ chế dependency verification metadata để ghi expected checksums hoặc signature-related metadata theo khả năng/phiên bản phù hợp. Ví dụ dưới đây minh họa **cách hình thành baseline và kiểm tra**, không áp đặt một Gradle release cụ thể.

### 9.1. Tạo baseline trong môi trường được kiểm soát

~~~bash
# Minh họa workflow ban đầu: tải và ghi verification metadata.
./gradlew --write-verification-metadata sha256 help

# Sau khi review và phê duyệt metadata:
./gradlew --dependency-verification=strict build
~~~

**Không chạy bước tạo baseline một cách mù quáng rồi coi đã bảo mật.** Lúc generate, resolver có thể tải artifact từ nguồn bị chiếm. Reviewer cần kiểm tra package, repository, version, SHA-256 và nguồn phê duyệt; sau đó commit metadata qua PR được kiểm soát.

Nếu build không resolve mọi configuration, metadata sinh ra có thể **chưa bao phủ** test/runtime/plugin artifacts. Cần xác định các tasks/configurations hoặc pipeline thực tế sẽ resolve những gì.

### 9.2. Ví dụ verification metadata minh họa

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<verification-metadata xmlns="https://schema.gradle.org/dependency-verification">
  <configuration>
    <verify-metadata>true</verify-metadata>
    <verify-signatures>false</verify-signatures>
  </configuration>
  <components>
    <component group="com.example.training"
               name="report-utils"
               version="2.3.1">
      <artifact name="report-utils-2.3.1.jar">
        <sha256 value="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"/>
      </artifact>
    </component>
  </components>
</verification-metadata>
~~~

**Đây là giá trị digest giả chỉ để minh họa cấu trúc, không phải digest thực của package.** Tệp thật phải được tạo/xác minh theo Gradle version, dependency graph và artifact set đang sử dụng. Với metadata, POM, module metadata hoặc plugin artifacts, cần kiểm tra quy tắc bao phủ và hành vi strict verification của version đang chạy. Cấu hình `verify-signatures=false` trong ví dụ chỉ minh họa mô hình **hash-based verification**, không có nghĩa mọi dự án nên bỏ chữ ký.

### 9.3. Điều kiện nghiệm thu cho Gradle

- Chạy build release ở chế độ integrity verification được phê duyệt.
- Artifact mới hoặc digest thay đổi ngoài approved baseline làm build **fail**.
- Metadata verification được review như security-sensitive code.
- Plugin và transitive dependencies thuộc scope, không chỉ dependency khai báo trực tiếp.
- Không dùng verification bypass/lenient/off để làm xanh release gate.
- Verification failures và quyết định cập nhật baseline có evidence.
- CI environment không tự sửa trusted metadata trong quá trình verify.
- Provenance của **artifact do chính build tạo** được kiểm tra ở gate tiếp theo.

### 9.4. Dependency lock và verification là hai mục đích

- **Dependency locking:** giúp giữ resolved versions ổn định, giảm drift giữa builds.
- **Dependency verification:** giúp phát hiện bytes/signature không khớp với trust metadata.
- **Repository controls:** giảm nguy cơ resolve nhầm nguồn.
- **Build provenance:** giải thích artifact output được tạo bởi workflow/inputs nào.

Cần phối hợp, không dùng một cơ chế để thay tất cả cơ chế còn lại.

## 10. Maven: checksum policy, repository và hạn chế của version pin

Maven có cơ chế resolution qua local repository, remote repositories và mirrors. Khi dùng Maven, cần quản lý **effective repositories, checksum behavior, plugin repositories và artifact provenance**.

### 10.1. Maven repository checksum policy minh họa

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
  <profiles>
    <profile>
      <id>secure-repositories</id>
      <repositories>
        <repository>
          <id>approved-public-proxy</id>
          <url>https://repo.example.internal/maven-public</url>
          <releases>
            <enabled>true</enabled>
            <checksumPolicy>fail</checksumPolicy>
          </releases>
          <snapshots>
            <enabled>false</enabled>
          </snapshots>
        </repository>
      </repositories>
    </profile>
  </profiles>
  <activeProfiles>
    <activeProfile>secure-repositories</activeProfile>
  </activeProfiles>
</settings>
~~~

Ví dụ này chỉ thể hiện **một cấu hình mẫu**; effective settings còn chịu ảnh hưởng bởi mirrors, settings chung, pluginRepositories, profiles và resolver. Cần đối chiếu trên toolchain/version thực tế, không suy rằng mọi đường tải đã được bảo vệ chỉ vì một repository khai báo `checksumPolicy=fail`.

**Giới hạn quan trọng:** nếu checksum được tải cùng repository bị compromise và attacker sửa cả package lẫn checksum, checksum policy có thể không phát hiện. Muốn chứng minh “khớp bản đã duyệt” cần một **trusted digest manifest/signature/provenance policy độc lập** hoặc công cụ verification phù hợp được tổ chức kiểm soát.

### 10.2. Lệnh phân tích dependency graph

~~~bash
# Phục vụ quan sát dependency graph, KHÔNG tự xác minh integrity.
mvn -B -ntp dependency:tree

# Minh họa build dùng settings được phê duyệt.
mvn -B -ntp -s settings-secure.xml verify
~~~

Lệnh `dependency:tree` có thể cần resolve plugin và artifacts, nên bản thân plugin source cũng phải nằm trong threat model. Build success không đồng nghĩa package-integrity PASS nếu cơ chế chỉ kiểm checksum do cùng remote trả về.

### 10.3. Lưu ý với Maven

- Kiểm soát effective repository/mirror và plugin repository.
- Phân biệt release immutable với `SNAPSHOT` changing.
- Gắn version/plugin versions với release.
- Xác minh transitive artifacts và descriptors, không chỉ JAR đầu tiên.
- Hạn chế direct Internet egress của CI nếu policy yêu cầu.
- Bảo vệ internal repository manager khỏi overwrite và credential lạm dụng.
- Duy trì approved digest/signature/provenance evidence cho critical packages.
- Test khi artifact/chksum bị thay và khi repository unavailable.

## 11. Package integrity ở hệ sinh thái khác

Bài học tập trung Maven/Gradle nhưng nguyên tắc vẫn áp dụng ở ecosystem khác:

| Ecosystem | Control minh họa | Điểm phải kiểm tra |
| --- | --- | --- |
| **npm** | Lockfile chứa resolved version/integrity metadata; `npm ci` trong CI | Lockfile review; install scripts và registry trust |
| **Python/pip** | Pinned dependencies và hash-checking mode khi phù hợp | Hashes cho toàn bộ resolved packages/variants trong scope |
| **OCI images** | Deploy theo immutable digest, verify signatures/attestations | Manifest digest, signer identity, policy, cluster admission |
| **Helm/chart** | Chart version/digest/signature và registry policy | Dependencies, templates, runtime configuration |
| **Maven/Gradle** | Resolution pinning, integrity metadata và approved repositories | Plugins, transitive packages, POM/module metadata |
| **OS packages** | Trusted repository metadata/signatures | Repository keys, package index và trust roots |

Một lockfile có trường `integrity` chưa tự chứng minh package là lành tính; dependency được chọn sai hoặc attacker sửa cả lockfile vẫn là rủi ro.

## 12. Repository, namespace và dependency confusion

### 12.1. Dependency confusion

Giả sử tổ chức có package nội bộ `com.company.billing:client:1.4.0`. Build của developer hoặc CI được cấu hình tìm cả internal và public repositories. Nếu namespace/resolution không được giới hạn, attacker có thể đăng một package cùng tên hoặc version hấp dẫn ở public source, khiến resolver dùng nhầm.

Điều kiện nguy hiểm:
- Dùng namespace nội bộ nhưng không khóa source.
- Public repository có thứ tự/priority hoặc rule có thể thắng internal.
- Có dynamic version hoặc tag.
- Registry credentials/permissions chưa kiểm soát.
- CI không xác minh expected digest/source.

### 12.2. Biện pháp

- **Namespace reservation/ownership** khi ecosystem hỗ trợ.
- **Repository content filtering / exclusive resolution**: group nội bộ chỉ được tải từ repository nội bộ đã duyệt.
- Không trộn namespace nội bộ với public source theo cách mơ hồ.
- Artifact immutable, quyền publish giới hạn và audit.
- Dependency verification theo approved baseline.
- Test resolution/source, không chỉ test build success.
- Tách quyền publish, approve và consume.

### 12.3. Ví dụ Gradle Kotlin DSL minh họa

~~~kotlin
repositories {
    exclusiveContent {
        forRepository {
            maven {
                url = uri("https://packages.example.internal/maven-private")
            }
        }
        filter {
            includeGroup("com.company.billing")
        }
    }
    mavenCentral()
}
~~~

Đây là minh họa việc **chỉ lấy một group từ repository nội bộ**; đối với nhiều subgroups, cần cấu hình includeGroupByRegex/filters chính xác theo cấu trúc namespace thực tế, và xem cả plugin management repositories. Không đưa credential trực tiếp vào source. Test để chứng minh artifact nội bộ không bị public repository thay thế.

## 13. Package metadata là một phần của integrity

Package không chỉ gồm binary. Metadata có thể quyết định:
- Những dependencies nào sẽ được tải.
- Version ranges hoặc BOM nào được áp dụng.
- Platform/classifier nào được chọn.
- Build/plugin behavior.
- Optional/excluded dependency.
- Native runtime package theo hệ điều hành.

Một attacker chỉ cần thay POM/module metadata để thêm dependency độc hại, dù JAR chính không đổi.

### Bảng kiểm

| Object | Nguy cơ | Verification |
| --- | --- | --- |
| JAR/ZIP | Bytes thay đổi | Approved digest/signature |
| POM | Thêm dependency/plugin sai | Descriptor integrity + graph review |
| Gradle module metadata | Variant/dependency khác | Metadata verification, graph/effective resolve |
| Registry index | Redirect sang artifact sai | Trusted repository/metadata signatures |
| Dependency lock | Version/source bị thay | PR review + policy |
| Verification metadata | Expected digest bị sửa | Independent approval & protected change |
| Build script/plugin | Chạy code trái phép | Source review, integrity/provenance, least privilege |
| OCI manifest | Image tag/digest mismatch | Immutable digest và admission verification |

Khi xảy ra integrity incident, cần kiểm kê **những object nào có thể bị sửa**, không chỉ JAR có dấu hiệu bất thường.

## 14. Bảo vệ package do chính tổ chức xuất bản

Một tổ chức vừa là consumer vừa là publisher. Cần bảo vệ supply chain của artifact nội bộ từ source tới deployment.

### 14.1. Đường phát hành được kiểm soát

~~~mermaid
flowchart LR
    PR["Reviewed PR / protected branch"] --> BUILD["Isolated build identity"]
    BUILD --> SCAN["Tests + security checks"]
    SCAN --> DIGEST["Immutable artifact digest"]
    DIGEST --> PROV["Build provenance / signature"]
    PROV --> REPO["Immutable artifact repository"]
    REPO --> ADMIT["Release/admission verification"]
    ADMIT --> PROD["Runtime by digest"]
    PROD --> VERIFY["Actual-state digest evidence"]
~~~

### 14.2. Requirements cho publisher

- Build từ source reference được phê duyệt, có commit ID.
- Build workflow và runner identity được kiểm soát, quyền tối thiểu.
- Inputs/dependencies được pin/xác minh theo scope.
- Artifact digest được ghi và liên kết với build/job.
- Provenance/signature được phát hành bằng identity/quy trình đáng tin.
- Artifact repository không cho overwrite release tùy ý.
- Release approval đối chiếu artifact digest với test/evidence.
- Deployment dùng artifact digest đã được phê duyệt, không chỉ mutable tag.
- Actual runtime artifact được đối chiếu khi triển khai và theo trigger.

### 14.3. Kiểm soát signing key/identity

- Định danh chủ thể ký và phạm vi package/repository được phép ký.
- Signing key được bảo vệ và có quy trình rotation/revocation.
- Không để CI job không đáng tin mượn key ký release.
- Separation of duties giữa người sửa workflow và người duyệt trust policy khi cần.
- Ghi audit cho signing events và anomaly.
- Có runbook khi key/issuer bị compromise: tạm dừng trust, đánh giá releases, rotate, reissue và redeploy.

## 15. CI/CD verification gates và fail-secure behavior

### 15.1. Gate ở những điểm nào?

| Gate | Khi nào? | Điều kiện không được bỏ qua |
| --- | --- | --- |
| Dependency selection | PR/thay dependencies | Nguồn/name/version/owner được duyệt |
| Dependency fetch | Mỗi build hoặc lúc ingest vào trusted cache | Bytes/metadata khớp expected digest/trust policy |
| Build plugin execution | Trước khi chạy plugin | Plugin/source/version thuộc scope đã duyệt |
| Artifact publish | Sau build, trước push release | Output digest, identity, tests/provenance khớp |
| Artifact promotion | Test → staging → production | Dùng cùng immutable artifact, không rebuild ngầm |
| Deployment admission | Trước khi chạy | Digest/signature/attestation đáp ứng policy |
| Runtime verification | Sau deploy và theo trigger | Actual digest/version khớp release record |
| Incident response | Có alert compromise/mismatch | Quarantine, scope inventory, revoke/restore |

### 15.2. Fail-secure khi integrity validation lỗi

Khi digest/signature/provenance không khớp:
- Không auto-ignore hoặc chuyển sang lenient/off.
- Chặn build/deploy/promotion với package ngoài trust policy.
- Quarantine artifact/cache entry liên quan nếu có cơ chế.
- Ghi finding với expected/actual digest, source, version, build ID, thời điểm.
- Kiểm tra repository/caches/identity và scope của incident.
- Chỉ cập nhật baseline sau review độc lập và risk decision phù hợp.

Khi verification service hoặc registry unavailable:
- Không coi timeout là PASS.
- Có thể dùng offline cache **đã từng xác minh và có policy về freshness/revocation/scope**, nếu được duyệt.
- Không tự đổi registry/source hoặc fallback sang HTTP.
- Có thể hoãn build/deploy và duy trì phiên bản runtime đã được phê duyệt.
- Tách availability incident với integrity finding; ghi limitation nếu không có đủ evidence.

### 15.3. Không coi “build xanh” là bằng chứng duy nhất

Build có thể xanh vì:
- Chưa bật integrity gate.
- Verification metadata được tạo lại ngay trước build.
- Lỗi checksum chỉ là warning.
- Plugin hoặc configuration chưa được resolve trong test.
- CI dùng cache không được kiểm tra.
- Pipeline không verify release artifact đã publish.
- Deployment kéo tag khác digest vừa kiểm chứng.

Phải gắn kết quả với **artifact thực tế** và kiểm tra gate có đang hoạt động không.

## 16. Artifact caching: tăng tốc nhưng cũng tạo trust boundary

### 16.1. Các loại cache cần phân biệt

- Package manager local cache.
- Corporate repository proxy/mirror cache.
- CI remote build cache.
- Container registry cache.
- Build output cache.

Mỗi loại có cách tạo key, TTL, ownership và quyền sửa riêng. Không giả định cache “nội bộ” nghĩa là đáng tin.

### 16.2. Kiểm soát cache

- Content-addressable storage và immutable digest khi phù hợp.
- Kiểm tra artifact từ cache bằng trusted metadata.
- Không dùng cache key chỉ là name/version nếu bytes có thể đổi.
- Tách cache của untrusted pull requests khỏi privileged release pipelines.
- Không chia sẻ cache có thể ghi bởi actor ít tin cậy với job dùng signing/deploy credentials.
- Ghi cache hit/miss/source và kiểm tra bất thường.
- Quarantine/invalidate cache entry khi package mismatch.
- Không để cache bypass verification khi metadata đổi.

### 16.3. Cache poisoning

Một pull request từ nguồn không tin cậy ghi một build-cache entry. Release workflow dùng lại entry vì key trùng, tạo output chứa code ngoài expected source.

Package checksums cho dependencies chưa chắc phát hiện lỗi này nếu **output cache** không có provenance/integrity policy. Cần:
- Trust isolation của build cache.
- Output verification và provenance.
- Controlled workflow permissions.
- Release artifact digest được kiểm tra độc lập.
- Khi cần, rebuild từ môi trường đáng tin không dùng untrusted cache.

## 17. SBOM và inventory hỗ trợ integrity assurance

SBOM cung cấp danh sách component dùng cho:
- Biết package/version nào nằm trong artifact.
- Tìm phạm vi ảnh hưởng khi có package compromise hoặc vulnerability.
- Đối chiếu dependency graph với bản đang deploy.
- Hỗ trợ incident response và audit.

Tuy nhiên:
- SBOM **không tự xác minh** bytes của package.
- SBOM có thể thiếu transitive, native, build-time hoặc runtime-loaded components.
- SBOM có thể gắn với một build khác.
- SBOM có thể bị chỉnh sửa nếu không có integrity/trust controls.

### SBOM evidence nên gắn

- Artifact digest mà SBOM mô tả.
- Source/build/deployment identifiers.
- Component identities và digests khi có.
- Tool/source/version tạo SBOM.
- Scope và limitations.
- Signature/attestation và trust policy nếu áp dụng.
- Thời điểm review và người chịu trách nhiệm.

SBOM giúp **truy vết và phản ứng**, nhưng không thay signature/provenance verification hoặc security testing.

## 18. Threat-informed security requirements cho package integrity

Các ID dưới đây là mẫu đào tạo, không phải control IDs của một standard bên ngoài.

| ID | Security requirement có thể kiểm chứng | Evidence / kiểm tra |
| --- | --- | --- |
| **PI-REQ-01** | Dependency nằm trong release phải có identity, source và resolved version rõ | Dependency graph + repository mapping |
| **PI-REQ-02** | Critical package binary/metadata phải khớp approved digest hoặc trust policy | Strict verification results |
| **PI-REQ-03** | Thay đổi dependency và verification baseline phải qua review/approval | PR diff + approvals |
| **PI-REQ-04** | Internal namespace không được resolve từ public registry ngoài policy | Repository filtering + negative test |
| **PI-REQ-05** | Release pipeline phải fail khi checksum/signature/provenance mismatch | Tampered artifact failure-injection |
| **PI-REQ-06** | Build plugins và transitive dependencies phải nằm trong integrity scope được duyệt | Graph + plugin inventory + verification |
| **PI-REQ-07** | Release artifact phải có immutable digest và liên kết đúng source/build/test evidence | Artifact digest + provenance |
| **PI-REQ-08** | Promotion phải dùng cùng artifact đã kiểm tra; deployment phải đối chiếu digest | Promotion/admission/runtime evidence |
| **PI-REQ-09** | Signing identity/key chỉ dùng cho package/workflow được phê duyệt | Signer policy + audit/access review |
| **PI-REQ-10** | CI cache giữa untrusted và trusted workflows phải được tách hoặc xác minh theo trust model | Cache policy + poisoning test |
| **PI-REQ-11** | Verification outage không được chuyển thành integrity PASS hoặc bypass ngoài phê duyệt | Timeout/offline/deny tests |
| **PI-REQ-12** | Package integrity event/mismatch phải được ghi nhận, có owner và xử lý theo risk | Alert, finding, response record |
| **PI-REQ-13** | SBOM/inventory phải gắn đúng release digest và nêu limitations | Inventory/release cross-check |
| **PI-REQ-14** | Khi phát hiện compromised package, tổ chức phải xác định deployments phụ thuộc và xử lý | Dependency impact query + incident exercise |
| **PI-REQ-15** | Artifact release không được overwrite ngoài quy trình kiểm soát | Repository permissions + deny test |
| **PI-REQ-16** | Exception/bypass integrity gate phải có approval, scope, expiry và compensating verification | Exception register + expiry review |

Một requirement cần cụ thể hóa theo service, environment, owner, severity và acceptance. Ví dụ “mọi package đều được ký” chỉ hợp lý nếu ecosystem và tổ chức có trust policy hỗ trợ; không tự nhận “signed” nghĩa là nguồn được tin.

## 19. Verification test plan: positive, negative và failure

Các test dưới đây nên chạy trong môi trường kiểm thử có gói mô phỏng, không tự đầu độc public registry hoặc chỉnh artifact production thật.

| Test ID | Tình huống | Expected result |
| --- | --- | --- |
| **PI-T01** | Package đúng name/version/digest từ nguồn duyệt | Verification PASS theo policy |
| **PI-T02** | Thay một byte JAR, giữ tọa độ cũ | Digest mismatch, build BLOCK |
| **PI-T03** | Thay POM/module metadata nhưng giữ JAR | Metadata/graph verification phát hiện |
| **PI-T04** | Tải checksum đã bị thay cùng artifact ở mirror test | Independent trusted baseline không bị đánh lừa |
| **PI-T05** | Internal package giả xuất hiện ở public repository | Resolver không chọn public source |
| **PI-T06** | Thêm transitive dependency ngoài baseline | Build fail hoặc yêu cầu approved update |
| **PI-T07** | Build plugin đổi version/digest ngoài phê duyệt | Verification gate chặn |
| **PI-T08** | Dynamic/snapshot version đổi giữa hai build | Lock/verification policy phát hiện drift |
| **PI-T09** | Signed artifact nhưng signer identity không thuộc allowlist | Verification DENY |
| **PI-T10** | Signed attestation có subject digest khác artifact | Admission DENY |
| **PI-T11** | Chữ ký không hợp lệ hoặc trust root không có | Verification DENY/INCONCLUSIVE theo gate |
| **PI-T12** | Signing key/identity bị revoke theo policy | Không chấp nhận artifact nằm ngoài điều kiện trust |
| **PI-T13** | Registry/mirror unavailable | Không silent fallback sang nguồn không duyệt |
| **PI-T14** | Verification service timeout | Không tự PASS; xử lý theo fail-secure policy |
| **PI-T15** | CI cache chứa bytes sai expected digest | Cache entry bị từ chối/quarantine |
| **PI-T16** | Untrusted PR cố ghi cache cho privileged release job | Cache isolation chặn hoặc verification phát hiện |
| **PI-T17** | Artifact release bị overwrite trong test repo | Repository policy deny hoặc alert |
| **PI-T18** | Deploy dùng mutable tag trỏ digest khác | Admission/runtime verification chặn |
| **PI-T19** | Promotion staging → prod | Same approved artifact digest, không rebuild ngầm |
| **PI-T20** | SBOM mô tả digest/version khác release | Inventory consistency test fail |
| **PI-T21** | Pipeline disable strict verification qua config flag | Policy/review gate phát hiện và chặn |
| **PI-T22** | Scanner/verification test thiếu scope hoặc không chạy | Assessment NOT_RUN/INCONCLUSIVE, không PASS |
| **PI-T23** | Package compromise alert có dependency graph/affected deployments | Incident impact query trả danh sách trong scope |
| **PI-T24** | Remediation cập nhật package và approved hashes | New artifact verified, old digest không còn deploy |
| **PI-T25** | CI release user thử sửa trusted verification metadata trực tiếp | Change-control permission deny/audit |
| **PI-T26** | Vẫn dùng vulnerable nhưng integrity-correct package | Integrity có thể PASS, vulnerability assessment vẫn có finding riêng |

### Test nào chứng minh điều gì?

- **Checksum mismatch test:** chứng minh phát hiện bytes khác baseline, không chứng minh baseline đúng.
- **Signer identity test:** chứng minh trust policy cho phép/không cho phép một signer.
- **Provenance subject test:** chứng minh attestation liên kết đúng digest.
- **Dependency confusion test:** chứng minh resolver không lấy internal namespace từ nguồn sai.
- **Promotion test:** chứng minh digest không đổi qua các môi trường.
- **Runtime verification:** chứng minh artifact đang chạy khớp release record trong phạm vi quan sát.
- **Incident drill:** chứng minh tìm/contain affected deployments, không tự chứng minh tất cả package đang an toàn.

Không dùng “có một test PASS” để suy ra toàn bộ software supply chain đã được bảo đảm.

## 20. Thiết kế evidence register

### 20.1. Chuỗi truy vết

~~~text
RISK PI-R01: Bytes package bị thay dưới cùng tọa độ
  -> OBJECTIVE: Chỉ tiêu thụ approved package bytes
  -> PI-REQ-02: Critical package phải khớp trusted digest
  -> CONTROL: Gradle verification metadata + reviewed baseline
  -> TEST: PI-T02 (tampered JAR), PI-T03 (tampered metadata)
  -> EVIDENCE: build run, expected/actual digest, source, artifact
  -> FINDING: unverified package accepted (nếu xảy ra)
  -> REMEDIATION: fix gate/baseline/trust policy, quarantine
  -> RETEST: verification fails on bad bytes, passes on approved bytes
  -> OPERATING: verify release digest và runtime deployment
~~~

### 20.2. Mẫu YAML record

Các giá trị `<...>` là placeholder, **không phải kết quả thực tế**.

~~~yaml
assessment_id: PKG-INTEGRITY-001
module: SECURITY_SECURITY_ASSURANCE
topic: Package integrity
service: report-platform
environment: production
assessment_scope:
  package_ecosystem: maven-gradle
  source_repositories: ["<REPOSITORY_IDS>"]
  artifact_groups: ["<APPROVED_GROUPS>"]
  configurations: ["compile", "runtime", "test", "build-plugins"]
  trust_boundaries: ["registry", "mirror", "ci", "artifact-repo", "deployment"]
risk_ids: [PI-R01, PI-R02, PI-R05, PI-R09]
requirement_ids: [PI-REQ-02, PI-REQ-04, PI-REQ-05, PI-REQ-08]
policy:
  version: "<TRUST_POLICY_VERSION>"
  approved_digest_baseline: "<REVIEWED_VERIFICATION_METADATA_REF>"
  allowed_signers: ["<IDENTITY_OR_KEY_POLICY_REF>"]
  provenance_rules: "<BUILD_PROVENANCE_POLICY_REF>"
build:
  source_commit: "<COMMIT>"
  workflow_run_id: "<CI_RUN>"
  builder_identity: "<TRUSTED_BUILDER>"
  resolved_dependency_graph_ref: "<RESOLUTION_REPORT>"
  verification_result_ref: "<STRICT_VERIFICATION_REPORT>"
  artifact_digest: "<SHA256_OF_RELEASE_ARTIFACT>"
release:
  artifact_repository_ref: "<IMMUTABLE_RELEASE_RECORD>"
  attestation_ref: "<VERIFIED_ATTESTATION>"
  sbom_ref: "<SBOM_BOUND_TO_ARTIFACT_DIGEST>"
  deployment_id: "<DEPLOYMENT_ID>"
  runtime_digest_ref: "<RUNTIME_OBSERVATION>"
tests:
  - id: PI-T02
    evidence_ref: "<TAMPERED_JAR_BLOCK_TEST>"
  - id: PI-T05
    evidence_ref: "<DEPENDENCY_CONFUSION_TEST>"
  - id: PI-T18
    evidence_ref: "<DEPLOYMENT_DIGEST_TEST>"
assessment:
  assessed_at: "<ISO8601_UTC>"
  reviewer: "<AUTHORIZED_REVIEWER>"
  result: "<PASS_FAIL_INCONCLUSIVE>"
  limitations: "<UNTESTED_CONFIGURATIONS_OR_DEPENDENCIES>"
findings: ["<FINDING_IDS_IF_ANY>"]
exceptions: ["<APPROVED_EXCEPTION_IDS_IF_ANY>"]
residual_risk: "<REVIEWED_RISK_RATIONALE>"
reassessment_triggers:
  - "Dependency/version/lock/verification metadata changes"
  - "Publisher key, builder, repository or CI workflow changes"
  - "Artifact republish, registry incident or compromised package alert"
  - "New deployment target, plugin or transitive dependency"
~~~

### 20.3. Evidence phải gắn đúng object và thời điểm

Một assessment cần biết:
- **What:** package coordinates, classifier/extension, metadata, digest và source.
- **Who:** publisher identity, build identity, approver/reviewer.
- **Where:** repository/mirror, CI job, artifact store, deployment.
- **When:** fetch/build/verify/deploy timestamps.
- **How:** algorithm, verification policy, trust roots, test method.
- **Result:** expected vs actual, PASS/FAIL/INCONCLUSIVE và limitation.
- **What next:** finding owner, remediation, exception và reassessment trigger.

Không lưu raw credentials, private keys hoặc registry tokens vào evidence. Với hash/signature logs, tránh chụp toàn bộ environment có secret. Evidence storage cũng cần integrity/access/retention.

## 21. Đánh giá design, implementation và operating effectiveness

| Lớp đánh giá | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| **Design effectiveness** | Policy có bao phủ các nguồn package, trust boundaries và threat paths? | Threat model, dependency policy, architecture review |
| **Implementation** | Verification/config/code có được bật đúng trong CI và resolver? | CI definition, verification metadata, repository filters |
| **Operating effectiveness** | Build/deploy thực tế có chặn package sai và xác minh đúng digest? | Negative tests, build logs, release/admission evidence |
| **Recovery effectiveness** | Khi phát hiện package compromise có thể cô lập/khôi phục? | Incident exercise, quarantine, rebuild/redeploy, retest |

### Kết luận theo từng requirement

- **PASS:** Có evidence phù hợp cho đúng scope/version, test đạt, trust policy được áp dụng và không có finding làm vô hiệu claim.
- **FAIL:** Package sai vẫn được chấp nhận hoặc control/gate không đáp ứng acceptance.
- **INCONCLUSIVE:** Thiếu expected digest/trust root, test chưa chạy, source thiếu, metadata chưa bao phủ hoặc không quan sát được runtime.
- **NOT_RUN:** Chưa thực hiện verification phù hợp.
- **EXCEPTION:** Có risk acceptance được duyệt trong scope/thời hạn; **không** chuyển finding kỹ thuật thành PASS.

Các trạng thái nên được lưu theo **package/requirement/build/deployment**, không chỉ một nhãn “supply chain green” cho toàn dự án.

## 22. Quản trị thay đổi package và cập nhật baseline

### 22.1. Quy trình thêm hoặc nâng package

1. Xác định use case, package identity và nguồn.
2. Kiểm tra maintainer/namespace, lịch sử phát hành và trust policy.
3. Xác định resolved graph và transitive changes.
4. Đánh giá vulnerability, license, runtime privilege và các rủi ro liên quan **riêng** với integrity.
5. Thiết lập expected digest/verified signer/provenance theo security standard.
6. Cập nhật lockfile/verification metadata qua PR.
7. Review diff của dependency, metadata, build plugin và repository source.
8. Chạy positive/negative tests, security checks và build reproducibility nếu áp dụng.
9. Publish immutable artifact và ghi digest.
10. Promotion/deployment trên cùng digest, lưu evidence và monitoring.

### 22.2. Vì sao việc cập nhật checksum không nên tự động chấp nhận?

Giả sử build fail vì hash đã đổi. Nếu pipeline tự chạy `--write-verification-metadata` rồi commit baseline mới:
- Gate không còn phân biệt package được duyệt với package mới bị thay.
- Attacker cần chỉ kiểm soát artifact, không cần đánh bại verification logic.
- Evidence “build PASS” mất ý nghĩa.

**Cập nhật baseline là một trust decision**, không phải một thao tác kỹ thuật tùy tiện để sửa build.

### 22.3. Cần review khi nào?

| Trigger | Cần kiểm tra |
| --- | --- |
| Version/dependency graph đổi | New packages, transitive dependencies, compatibility và approval |
| Package cùng version nhưng digest đổi | Republish/tampering, source và incident scope |
| Signing identity/key đổi | Trust roots, ownership, revocation, authorization |
| Repository/mirror đổi | Namespace/routing, TLS, permissions, cache |
| CI workflow/runner đổi | Provenance, signing permissions, cache isolation |
| Release tag/digest khác | Wrong artifact/promote/rebuild, runtime consistency |
| SCA/incident alert | Affected packages và deployments, remediation |
| SBOM completeness thay đổi | Inventory accuracy và evidence coverage |

## 23. Xử lý package-integrity incident

### Tình huống

Một dependency `report-utils:2.3.1` đang dùng ở production xuất hiện hash mismatch giữa bản trong verified baseline và bản hiện có trên mirror.

### Quy trình xử lý

1. **Contain:** không tiếp tục ingest/deploy artifact bị nghi; cô lập mirror/cache entry trong phạm vi.
2. **Preserve:** lưu expected/actual digests, timestamps, repository URLs, build IDs và evidence không chứa secret.
3. **Classify:** là republish hợp lệ, corruption, cấu hình sai, metadata drift hay compromise?
4. **Scope:** tìm builds, artifacts, deployments và consumers đã dùng digest bị nghi thông qua SBOM/dependency inventory.
5. **Assess compromise:** nếu nghi bị khai thác/đã thực thi mã, phối hợp incident response và điều tra credentials/runner.
6. **Validate trusted source:** xác minh maintainer/publisher và approved package từ trust channel độc lập; không chỉ tin mirror hiện tại.
7. **Remediate:** thu hồi/rotate compromised credentials nếu cần; chọn package phiên bản/digest tin cậy hoặc rebuild trong môi trường sạch.
8. **Verify:** chạy strict verification, signer/provenance policy, tests và runtime digest check.
9. **Recover:** republish theo immutable release procedure, promote và redeploy, theo dõi anomaly.
10. **Review:** cập nhật root cause, controls, registry/cache policy, finding và exception; đóng sau retest.

**Không xóa chứng cứ hoặc chỉ “clear cache rồi build lại” trước khi xác định phạm vi.** Việc đó có thể làm mất dữ liệu điều tra. Nếu attack đã chạy trong CI, phải xem xét exposure của CI secrets và tokens.

### Phân biệt các kết quả

- Hash mismatch không tự chứng minh bị tấn công; có thể là corruption hoặc republish ngoài quy trình.
- Hash khớp không loại trừ vulnerability/malware đã nằm trong approved package.
- Signed artifact không loại trừ signing key compromise.
- Không có cảnh báo không chứng minh mirror/cache không bị thao túng.

## 24. Case study: ứng dụng Java dùng package nội bộ và mirror công cộng

### 24.1. Bối cảnh

Một nền tảng Java/Spring Boot dùng Gradle:
- Library nội bộ `com.company.billing:tax-core:4.2.0`.
- Một số libraries từ public Maven repository.
- Corporate mirror/proxy.
- CI runner với quyền đọc secret và publish artifact.
- Artifact repository lưu release JAR và container image.
- Kubernetes deployment từ image tag `release-stable`.
- Pipeline chạy SCA và unit tests nhưng chưa bật strict dependency verification.

### 24.2. Các vấn đề phát hiện

1. Namespace nội bộ vẫn có thể resolve từ public repository.
2. Một dependency dùng dynamic version.
3. Verification metadata chỉ có JAR top-level, bỏ transitive/plugin objects.
4. Mirror chấp nhận overwrite một số releases.
5. CI cache có thể ghi từ untrusted pull requests.
6. Pipeline tự cập nhật checksum khi build fail.
7. Release image được promote qua mutable tag.
8. SBOM chưa gắn artifact digest.
9. Không có negative test cho tampered package.
10. Log verification bị giữ quá ngắn, không đủ audit traceability.

### 24.3. Mapping finding → requirement → test

| Finding | Requirement liên quan | Biện pháp | Retest |
| --- | --- | --- | --- |
| Internal namespace resolve public | PI-REQ-04 | Exclusive repository mapping | PI-T05 |
| Dynamic dependency drift | PI-REQ-01/02 | Lock + trusted digest baseline | PI-T08 |
| Transitive/plugin không verify | PI-REQ-06 | Expand graph/config coverage | PI-T06/07 |
| Repository cho overwrite | PI-REQ-15 | Immutability, publish IAM separation | PI-T17 |
| Untrusted cache ghi release | PI-REQ-10 | Segregated cache + provenance | PI-T16 |
| Auto-refresh checksum | PI-REQ-03/05 | PR approval + strict gate | PI-T02/21 |
| Mutable release tag | PI-REQ-08 | Promote by immutable digest | PI-T18/19 |
| SBOM không gắn digest | PI-REQ-13 | Bind SBOM to artifact | PI-T20 |
| Thiếu negative test | PI-REQ-05 | Tampered fixture in test repo | PI-T02/03 |
| Log thiếu evidence | PI-REQ-12 | Retention/identity/build references | Evidence review |

### 24.4. Assurance claim có giới hạn

> Trong phạm vi các Java dependencies, Gradle plugins và artifacts đã được inventory cho release được đánh giá, pipeline chỉ chấp nhận package từ approved repository mappings; mọi artifact/metadata thuộc verification scope khớp trusted digest baseline hoặc signing policy; package sai digest bị chặn; artifact do CI tạo được gắn source/build/release digest và production deployment sử dụng đúng digest đã phê duyệt. Các dynamic runtime-loaded components, external vendor bundles hoặc configurations chưa kiểm tra được ghi riêng như limitations.

Claim này cần actual test results, runtime observation và reviewer. Không được tuyên bố mọi dependency toàn vẹn nếu chỉ một configuration hoặc một build agent được kiểm tra.

## 25. Vai trò và trách nhiệm

| Vai trò | Trách nhiệm | Evidence/đầu ra |
| --- | --- | --- |
| **System/Product Owner** | Criticality, use case, impact và risk appetite | Asset/risk decisions |
| **Developer/Tech Lead** | Chọn/updating packages, review dependency changes, tests | Dependency PR, lockfile, test evidence |
| **Build/Release Engineer** | Build workflow, provenance, artifact immutability và promotion | Build IDs, digest, release record |
| **Platform/Repository Admin** | Registry/mirror, namespace, publish IAM, cache và retention | Effective config, access reviews, audit |
| **AppSec/Supply Chain Security** | Threat model, integrity standards, trust policy, security requirements | Control mapping, verification policy |
| **Security Operations** | Detection, compromise alert, containment/incident response | Alerts, investigation timeline, response |
| **GRC/Assessor** | Evidence completeness, control evaluation, exceptions | Assessment, findings, reviewer trail |
| **Risk Owner** | Phê duyệt residual risk/exception trong thẩm quyền | Risk acceptance/expiry |
| **Upstream/Vendor Liaison** | Xác minh publisher, provenance và phản hồi incident | Vendor/publisher evidence |

Người tạo baseline hoặc build pipeline không nên tự có quyền sửa mọi trust policy, tắt verification và tự phê duyệt exception nếu risk yêu cầu separation of duties.

## 26. Bài tập thực hành

**Bối cảnh:** một hệ thống Java đa tenant dùng Gradle, thư viện nội bộ và public Maven dependencies. Repo có dependency lock nhưng không có trusted checksum baseline; CI dùng shared cache; registry mirror vừa thay đổi; production deploy bằng image tag mutable.

### Yêu cầu

1. Vẽ DFD cho đường `upstream → registry → mirror → resolver → cache → build → artifact repository → deployment`, đánh dấu trust boundaries.
2. Xác định ít nhất **8 risk scenarios** liên quan name/version, bytes, metadata, signer, CI cache và deployment.
3. Phân biệt integrity, authenticity, provenance, vulnerability scanning, SBOM và reproducible build bằng một ví dụ cụ thể cho từng khái niệm.
4. Viết ít nhất **10 security requirements** có ID, source, owner, scope, acceptance criteria và verification method.
5. Đề xuất repository mapping để private namespace không resolve public và kiểm chứng bằng một negative test.
6. Thiết kế quy trình tạo/duyệt trusted SHA-256 baseline; giải thích tại sao không tự regenerate khi build fail.
7. Xây **ít nhất 10 tests**, bao gồm tampered JAR, tampered POM, transitive change, signer không hợp lệ, registry outage, cache poisoning và mutable image tag.
8. Đề xuất release artifact provenance, digest promotion và runtime verification.
9. Tạo evidence register với source commit, resolved graph, trusted baseline, test run, artifact digest, SBOM và reviewer.
10. Giả sử một critical package từng bị thay trong mirror: lập scope inventory, containment, remediation và retest plan.
11. Nêu những gì còn **INCONCLUSIVE** nếu chỉ có `mvn dependency:tree` hoặc một bản SBOM.
12. Viết một assurance claim có phạm vi, evidence và limitations.

### Hướng giải gợi ý

| Đề mục | Cách tiếp cận |
| --- | --- |
| Trusted digest | Gắn expected hash với package coordinates, metadata và approval history |
| Source isolation | Map private namespace chỉ tới internal repository |
| CI cache | Tách untrusted/trusted workflows, xác minh cache content theo trust |
| Transitive/plugin | Inventory toàn bộ resolved graph và scopes/configurations |
| Signer/provenance | Enforce identity, subject digest, builder/source constraints |
| Fail-secure | Hash/signature mismatch hoặc unknown không tự thành PASS |
| Release | Immutable artifact and digest promotion |
| Runtime | Actual digest đối chiếu approved release record |
| Response | Quarantine, impact analysis, rotate nếu cần, rebuild/retest |
| Evidence | Build/deployment IDs, tool config, expected/actual digest, timestamp, reviewer |

### Câu hỏi nâng cao

Một package JAR được tải từ registry. Registry cung cấp `package.jar` và `package.jar.sha256`; hai file khớp nhau. Công ty còn có SBOM liệt kê đúng tên/version, SCA không phát hiện CVE và CI build thành công. **Đã đủ để kết luận package integrity PASS chưa?**

**Định hướng:** chưa chắc. Checksum cùng registry không phải trusted baseline độc lập; SBOM và SCA không xác minh package bytes so với phiên bản được phê duyệt; build success không chứng minh gate hoạt động. Cần xác định trust decision, expected digest/signature/provenance policy, resolution scope, negative tests và artifact/runtime binding. Nếu các thông tin đó thiếu, ghi limitation/INCONCLUSIVE.

## 27. Những sai lầm thường gặp

| Ngộ nhận | Rủi ro | Cách đúng |
| --- | --- | --- |
| “Có SHA-256 là integrity an toàn.” | Expected hash có thể cũng bị sửa | Trusted baseline và protected approval |
| “Hash tải cùng JAR luôn đáng tin.” | Attacker có thể sửa cả hai | Kênh trust độc lập hoặc signature/provenance policy |
| “Pin version là pin bytes.” | Republish/mirror khác vẫn thay bytes | Digest verification và immutable release |
| “Package có chữ ký tức code an toàn.” | Signer có thể bị compromise, code có thể độc hại | Verify identity, policy, vulnerabilities và behavior riêng |
| “Chữ ký bất kỳ đều chấp nhận.” | Không có signer identity constraints | Explicit allowlist và trust roots |
| “SBOM chứng minh package integrity.” | SBOM chỉ kê khai components theo scope | Bind SBOM to artifact và verify bytes separately |
| “SCA sạch nghĩa là package chưa bị thay.” | CVE detection khác integrity | Dependency verification + security analysis |
| “Một JAR đã verify thì transitive deps đều đúng.” | Metadata/plugin/other JAR có thể khác | Complete resolved graph verification |
| “CI tự update checksum giúp giảm lỗi.” | Hợp thức hóa tampered bytes | Review baseline changes |
| “Internal registry không có rủi ro.” | Mirror/cache/permissions có thể compromise | Harden repository, checks và monitoring |
| “Image tag đủ cố định cho release.” | Tag có thể mutable | Deploy immutable digest |
| “Build chạy ở private network là an toàn.” | Workload/plugin độc hại vẫn có quyền | Least privilege và integrity verification |
| “Offline cache có bytes cũ là đủ.” | Cache có thể stale/poisoned | Verify digest/freshness/trust policy |
| “Verifier lỗi thì chỉ cần bỏ qua để release.” | Bỏ trust boundary | Fail-secure, defer hoặc approved exception |
| “Không có mismatch thì không có vấn đề.” | Có thể chưa kiểm tra hoặc source bị mất | Scope completeness và negative test |
| “Build PASS đồng nghĩa production chạy bytes đã test.” | Promotion/rebuild/tag drift | Digest-bound release và runtime verification |
| “Reproducible build bảo đảm không có malware.” | Malware có thể reproducible | Threat model, provenance, code review/testing |
| “Chỉ ứng dụng runtime cần kiểm.” | Build plugins có thể chạy code trong CI | Include build-time dependencies/permissions |
| “Exception làm finding PASS.” | Risk acceptance không sửa control | Track technical status và residual risk separately |
| “Một lần tạo baseline đủ dùng mãi.” | Dependencies/registries/keys/CI thay đổi | Continuous reassessment, review triggers |

## Ghi nhớ

- **Package integrity** cần chứng minh bytes/metadata đang dùng khớp **trusted, approved content**, không chỉ tính một digest.
- **Checksum, signature, provenance, SBOM, SCA và reproducible build phục vụ các mục tiêu khác nhau**; chúng bổ trợ nhưng không thay thế nhau.
- Version pin và lockfile giúp ổn định resolution nhưng **không tự khóa bytes**; cần integrity verification và quản trị expected baseline.
- Trust boundary tồn tại tại **registry → mirror → resolver → cache → build → artifact store → deployment → runtime**; cả build plugins và transitive dependencies đều quan trọng.
- Maven checksum policy và Gradle verification metadata có thể hỗ trợ; giá trị assurance phụ thuộc nguồn hash/signer, scope, strict enforcement, review và negative tests.
- Package mismatch, verification timeout hoặc trust metadata thiếu **không được tự chuyển thành PASS**.
- Release phải liên kết **source commit, builder/workflow, resolved dependencies, artifact digest, attestation, SBOM, approval và actual deployed digest**.
- Package integrity được đánh giá theo **risk → requirement → control → test → evidence → finding → remediation/retest**, với owner, limitation và residual risk minh bạch.
- Khi phát hiện compromised package, cần **quarantine, xác định impacted builds/deployments, xử lý credential nếu liên quan, rebuild/redeploy tin cậy và retest**.
