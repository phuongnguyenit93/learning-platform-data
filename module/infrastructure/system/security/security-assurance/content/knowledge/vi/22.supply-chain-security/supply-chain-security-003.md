# SBOM

**SBOM (Software Bill of Materials)** là danh mục có cấu trúc mô tả **các thành phần phần mềm** tạo nên một sản phẩm hoặc artifact, cùng thông tin định danh, phiên bản, quan hệ phụ thuộc và metadata liên quan. Có thể hình dung SBOM như “bảng kê nguyên vật liệu” cho phần mềm: muốn đánh giá một ứng dụng chịu ảnh hưởng thế nào khi xuất hiện lỗ hổng trong một thư viện, trước hết cần biết **thư viện nào thực sự có mặt**, đến từ đâu, nằm trong bản phát hành nào và được dùng trong phạm vi nào.

Ví dụ, hệ thống học trực tuyến viết bằng Java/Spring có Maven dependencies, thư viện transitively pulled, JAR đã đóng gói, container base image, Java Runtime, native libraries và một worker xử lý báo cáo. Một tập tin build mô tả dependencies **không chắc chứa đủ** mọi thành phần có trong image chạy production; một image scan phát hiện thư viện **không chắc phản ánh** mọi code path đang có thể bị khai thác. SBOM giúp tạo một **inventory có thể kiểm chứng**, nhưng phải được liên kết với build, deployment và bằng chứng đánh giá khác.

Trong chương **Supply chain security** của module **SECURITY_SECURITY_ASSURANCE**, mục tiêu không chỉ biết SBOM là gì mà còn **chứng minh bằng evidence** rằng danh mục thành phần đáng tin và đủ cho phạm vi đã tuyên bố. Tư duy xuyên suốt:

**Asset/risk → SBOM requirement → generation/validation control → artifact/version binding → vulnerability/exposure analysis → test/evidence → findings/remediation → continuous reassessment.**

Một SBOM tốt là nền tảng của quản trị rủi ro chuỗi cung ứng, vulnerability response, license governance và incident scoping. **SBOM không phải chứng chỉ an toàn, không thay SCA, không thay provenance/attestation và không chứng minh không có mã độc.**

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích SBOM, component, dependency, transitive dependency, artifact, supplier, namespace, identifier và relationship.
2. Phân biệt SBOM với package manifest, lockfile, SCA report, vulnerability report, VEX, build provenance và source attestation.
3. Xác định **scope** cho SBOM của source, build artifact, container, deployed workload, một sản phẩm đa service và một nhà cung cấp.
4. Hiểu vai trò của các trường như name, version, supplier, identifiers, hashes, licenses, dependencies, creation metadata và tool provenance.
5. Nhận diện hai hệ sinh thái tiêu biểu là **SPDX** và **CycloneDX**, cũng như nhu cầu interoperability và phiên bản schema.
6. Đọc một SBOM nhỏ, kiểm tra quan hệ direct/transitive dependencies và phát hiện bản ghi thiếu định danh.
7. Hiểu cách tạo SBOM từ Maven/Gradle, JAR, container, OS package manager, binary scanner và build pipeline.
8. Thiết kế cơ chế gắn SBOM vào đúng source revision, build digest, image digest, deploy environment và release.
9. Đánh giá completeness, accuracy, freshness, authenticity, integrity và reproducibility của SBOM.
10. Kết hợp SBOM với advisory/SCA/VEX, khả năng khai thác, exposure, ownership và residual risk.
11. Thiết kế requirements và test matrix để đánh giá cả pipeline tạo SBOM lẫn người dùng SBOM.
12. Xây Claim–Argument–Evidence, phân biệt design, implementation và operating effectiveness.
13. Quản lý findings, exceptions, missing components, vendor gaps và trigger cập nhật.
14. Vận hành continuous SBOM assurance trong SDLC và incident response.

## 2. SBOM là gì và không phải là gì?

### 2.1. Cấu trúc tư duy

Một sản phẩm phần mềm có thể gồm:

- **Component:** một library, package, framework, module, OS package, executable hoặc phần mềm con được xác định theo mô hình SBOM.
- **Identity:** tên, supplier/author khi biết, loại, package URL hoặc định danh tương đương, version và metadata.
- **Relationship:** sản phẩm **depends on**, **contains**, **generated from** hoặc quan hệ khác, tùy format và loại SBOM.
- **Provenance của SBOM:** ai/công cụ nào tạo, lúc nào, trên dữ liệu nguồn nào, với config/version nào.
- **Artifact binding:** SBOM nói về **bản nào**: source tree, resolved build, JAR, container image, firmware hoặc deployed service.

SBOM không nhất thiết công bố source code và không bắt buộc tiết lộ mọi bí mật của sản phẩm. Nó là một biểu diễn có cấu trúc về **thành phần phần mềm trong phạm vi cụ thể**.

### 2.2. Minh họa dependency graph

~~~mermaid
flowchart TD
    P["Learning Platform — release R"] --> API["learning-api"]
    P --> WK["report-worker"]
    API --> S["Spring-based service"]
    API --> L1["Logging library"]
    API --> J["JSON parser"]
    WK --> J2["JSON parser"]
    WK --> PDF["Document converter"]
    API --> IM["Container image A"]
    WK --> IM2["Container image B"]
    IM --> RT["Java Runtime"]
    IM --> OS["OS packages"]
    IM2 --> RT2["Java Runtime"]
~~~

Mô hình cần cho thấy cả:
- **Trùng component nhưng khác phiên bản:** parser trong API có thể không giống parser trong worker.
- **Transitive dependencies:** API không khai báo trực tiếp nhưng vẫn chứa package được framework kéo vào.
- **Runtime layering:** application library khác runtime/base OS packages.
- **Nhiều artifact:** release R có thể gồm các image và workload riêng; một SBOM duy nhất không đủ nếu chỉ phản ánh một module.

### 2.3. SBOM không trả lời tất cả câu hỏi

| Câu hỏi | SBOM có hỗ trợ? | Bằng chứng bổ sung |
|---|---|---|
| Sản phẩm có thành phần X phiên bản Y? | Có, nếu scope/completeness đủ | Binary inventory, artifact inspection |
| Thành phần X có advisory/CVE? | Là input cho đối chiếu | SCA/advisory feed, version mapping |
| Lỗ hổng X có exploitable trong môi trường này? | Không tự kết luận | VEX, reachability, config, runtime, threat model |
| SBOM được tạo từ đúng build đã phát hành? | Không tự động | Provenance, digest binding, CI/deploy records |
| Library bị cài vào image nhưng không chạy? | Có thể thấy có mặt | Runtime/use analysis |
| Mã nguồn có backdoor chưa công bố? | Không | Review, testing, provenance, threat intelligence |
| Có license obligations? | Có thể cung cấp license metadata | Legal/license analysis, policy |
| Nhà cung cấp thật sự kiểm soát dependency chain? | Không đầy đủ | Supplier attestation, contracts, build evidence |
| Ứng dụng đang được bảo vệ bởi runtime controls? | Không | Config, IAM, runtime tests, monitoring |

### 2.4. Những nhầm lẫn thường gặp

- **Không phải lockfile:** lockfile mô tả resolution của một package manager/build context; SBOM có thể bao phủ runtime, image và embedded binaries ngoài lockfile.
- **Không phải SCA report:** SCA đối chiếu inventory với vulnerability/license intelligence và policies; SBOM là dữ liệu inventory có thể dùng làm đầu vào.
- **Không phải CVE list:** một component chưa có CVE được biết đến vẫn có thể có risk.
- **Không phải VEX:** VEX nêu trạng thái ảnh hưởng của vulnerability đối với sản phẩm có scope cụ thể, thường dùng cùng SBOM.
- **Không phải provenance:** SBOM nói *có những gì*; provenance/attestation hỗ trợ trả lời *được tạo ra như thế nào, từ nguồn nào, bởi ai/hệ thống nào*.
- **Không phải “SBOM file tồn tại = đủ”:** còn cần kiểm tra độ phủ, cập nhật, schema, định danh, integrity và gắn đúng artifact.

## 3. Vì sao SBOM quan trọng với security assurance?

### 3.1. Incident: một thư viện có lỗ hổng mới

Giả sử xuất hiện advisory về parser JSON phiên bản bị ảnh hưởng. Tổ chức cần trả lời nhanh:

1. Những products/services/artifacts nào chứa parser này?
2. Phiên bản chính xác là gì? Có bị shade/repackage/rename không?
3. Có nằm trong runtime đang triển khai, image cũ, job batch hoặc plugin không?
4. Component là dependency trực tiếp hay transitive?
5. Các images/releases bị ảnh hưởng đang chạy ở môi trường/tenant nào?
6. Có sử dụng tính năng/vulnerable code path hay config bị ảnh hưởng không?
7. Ai sở hữu service, ai phê duyệt remediation hoặc risk acceptance?
8. Cần cập nhật dependency nào và retest những workflow nào?
9. Sau fix, bằng chứng nào chứng minh deployment đã chuyển sang artifact khác?

SBOM có độ bao phủ tốt biến câu hỏi “chúng ta có dùng thư viện đó không?” từ kiểm tra thủ công mọi repo thành **query inventory có truy vết**. Nhưng quyết định impact/priority vẫn cần analysis bên ngoài SBOM.

### 3.2. Security assurance program sử dụng SBOM

~~~mermaid
flowchart LR
    A["Threats / supply-chain risks"] --> R["SBOM requirements"]
    R --> G["Generation from build/artifact"]
    G --> V["Schema + completeness verification"]
    V --> B["Bind to signed / hashed artifact"]
    B --> I["Inventory & vulnerability intelligence"]
    I --> E["Exposure/VEX assessment"]
    E --> F["Finding / remediation / decision"]
    F --> T["Retest + release evidence"]
    T --> M["Continuous monitoring"]
    M --> R
~~~

Trong claim an toàn, SBOM là **một phần bằng chứng**, không phải bằng chứng độc lập chứng minh mọi control hiệu quả.

### 3.3. Mục tiêu bảo mật liên quan

| Mục tiêu | Ứng dụng SBOM | Giới hạn |
|---|---|---|
| **Confidentiality** | Tìm thành phần mã hóa/truyền dữ liệu có lỗi | Không tự chứng minh ACL/authz đúng |
| **Integrity** | Tìm package có rủi ro tampering/supply chain | Không thay artifact signature/provenance |
| **Availability** | Xác định service dùng package dễ gây DoS | Không tự kiểm tra resilience |
| **Accountability** | Gắn component với supplier/owner/release | Không chứng minh actor đã thực hiện build |
| **Maintainability** | Đánh giá outdated/EOL components | Không xác định toàn bộ chi phí fix |
| **Compliance/license** | Cung cấp license metadata và inventory | Không tự giải quyết nghĩa vụ license |
| **Incident response** | Truy vấn blast radius các bản phát hành | Cần deploy/runtime source of truth |

### 3.4. Điều kiện để SBOM có giá trị

Một bảng kê tạo hôm nay nhưng không rõ version/source/image digest có thể làm tăng **niềm tin sai lệch**. Những điều tối thiểu:
- Scope, target artifact và lifecycle stage rõ.
- Định danh thành phần đủ phân giải.
- Có direct/transitive relationships khi format/tool hỗ trợ.
- Có timestamp, generator/tool version và provenance phù hợp.
- Có cấu trúc parse được, schema version và validity.
- Có độ phủ được đo và ghi exclusions.
- Gắn được vào build/release/deployed asset.
- Có quy trình cập nhật và xử lý discrepancies.

## 4. Thành phần và quan hệ phụ thuộc

### 4.1. Direct dependency

Component được project khai báo trực tiếp để sử dụng. Ví dụ một Gradle/Maven project khai báo thư viện JSON hoặc HTTP client. Nó có thể tồn tại trong **compile**, **test** hoặc **runtime** scopes khác nhau.

### 4.2. Transitive dependency

Component được kéo vào vì một dependency khác yêu cầu. Project không khai báo trực tiếp nhưng binary/packaging vẫn có thể chứa nó. Các lỗ hổng chuỗi cung ứng thường liên quan transitive dependencies bị bỏ qua bởi review thủ công chỉ nhìn manifest.

### 4.3. Dependency graph khác danh sách phẳng

Một danh sách:
- learning-api;
- library A v1;
- library B v2;
- library C v3;

không cho biết A kéo B hay C được dùng trực tiếp. Graph giúp trả lời **đường giới thiệu** và thứ tự remediation.

Ví dụ:

~~~mermaid
flowchart TD
    A["learning-api"] --> B["framework A"]
    A --> C["HTTP client"]
    B --> D["JSON library vX"]
    C --> D
    D --> E["utility vY"]
~~~

Graph có thể có một component được tham chiếu bởi nhiều parents; tránh đếm thành phần trùng như nhiều vulnerability instances nếu mục tiêu là xác định artifact affected. Nhưng nếu cùng package có **nhiều bản phiên bản** trong các classloaders/modules khác nhau thì cần biểu diễn đầy đủ.

### 4.4. Dependency scope và optionality

Trong Java:
- **Compile:** được dùng khi biên dịch và có thể được đóng gói/runtime tùy build.
- **Runtime:** cần khi chạy; có thể không cần tại compile.
- **Test:** dùng trong test; thường không nằm trong production artifact, trừ lỗi packaging.
- **Provided:** kỳ vọng môi trường cung cấp; vẫn có thể xuất hiện trong runtime container/platform.
- **Optional:** có thể không kéo vào dependency graph mặc định.
- **Plugin/build-time:** tham gia quá trình build dù không được đưa vào artifact.

Không được coi **test-only** luôn là hoàn toàn vô hại: build pipeline/test runner vẫn có threat model riêng. Đối với **production runtime SBOM**, phải chỉ rõ build-time/test components có nằm trong scope hay được theo dõi bằng một SBOM/build inventory riêng.

### 4.5. “Component” không luôn là một package registry entry

Trong thực tế có:
- Shaded/repackaged Java JAR.
- Native shared libraries và JNI/JNA.
- Generated binaries và vendored source.
- OS packages, libc/openssl, Java Runtime.
- Embedded third-party code không có package metadata.
- JavaScript assets trong cùng backend artifact.
- Plugin tải động hoặc runtime classpath ngoài container.
- Base image layers và sidecar agents.
- SaaS dependencies mà nhà cung cấp không tiết lộ ở mức package.
- Proprietary internal libraries.

Vì vậy **không thấy trên Maven dependency tree** không có nghĩa thành phần không có trong artifact.

## 5. Metadata và định danh quan trọng

### 5.1. Các trường cốt lõi

Một danh mục SBOM thường cần, tùy format, profile và requirement:

| Trường | Vai trò | Câu hỏi kiểm tra |
|---|---|---|
| Document/BOM ID | Định danh tài liệu | Có unique/versioned và link tới artifact? |
| Format/spec version | Parser hiểu cấu trúc nào? | Có được hỗ trợ bởi consumers? |
| Component name | Tên component | Có ambiguous/confusable không? |
| Component version | Phiên bản hiện diện | Là declared/resolved/observed version? |
| Supplier/author | Bên cung cấp hoặc tác giả khi biết | Có được xác minh hay chỉ suy đoán? |
| Component type | Library, application, OS package, file, container, ... | Có đúng thực tế? |
| Unique identifier | purl, SPDXID, bom-ref, CPE khi thích hợp | Có canonical và tương thích ecosystem? |
| Hash/digest | Liên kết bytes của artifact/component khi có | Algorithm, scope, bytes và method rõ? |
| License data | Declared/concluded/license expression theo model | Có “unknown” được xử lý không? |
| Dependencies/relationships | Component nào phụ thuộc/chứa component nào? | Có direct, transitive và completeness? |
| Creation time | Thời điểm BOM được sinh | Có phản ánh rebuild/update không? |
| Tool/creator metadata | Generator/provenance của BOM | Version/config/source known? |
| Scope/lifecycle | Source/build/runtime/deployed artifact | Không đánh đồng các stages? |
| External references | Registry, repository, advisories, websites | Links có đáng tin và còn giá trị? |

Không phải mọi trường đều là **bắt buộc trong mọi schema/version**. Chúng là điểm cần xem khi viết acceptance criteria và assurance.

### 5.2. Minimum elements và yêu cầu nâng cao

Các sáng kiến về SBOM thường nhắc đến các minimum data elements như supplier name, component name, version, unique identifiers, dependency relationship, author và timestamp, bên cạnh các quy trình và thực hành chia sẻ. Tuy nhiên một chương trình thực tế phải quyết định **profile/format/version và các thuộc tính bổ sung cần thiết cho use case**, không coi bất kỳ danh sách tối thiểu nào là đủ để quản lý rủi ro trên mọi hệ thống.

Ví dụ một tổ chức cần query CVEs theo container digest sẽ phải thu **build/image identity, component identifiers và deployed workload mapping** ngoài các field nhận diện đơn giản.

### 5.3. Package URL (purl)

**purl** là định danh package có cấu trúc, hữu ích cho ecosystem-aware matching. Ví dụ minh họa:

~~~text
pkg:maven/org.example/learning-core@1.4.2
pkg:maven/org.springframework/spring-core@6.x
pkg:npm/example-ui@2.3.0
pkg:deb/debian/openssl@3.x?arch=amd64
~~~

Các giá trị phiên bản có chữ x và package ví dụ **không phải** những artifact cụ thể được xác minh. Với bài toán thật, phải dùng **resolved exact version**, namespace, qualifiers đúng và canonical encoding theo purl specification.

### 5.4. CPE

**CPE (Common Platform Enumeration)** là một cách định danh tên sản phẩm/platform thường dùng trong vulnerability data. Một package trong Maven không nhất thiết có CPE tương ứng chính xác. Mapping purl→CPE không nên coi là bằng chứng tuyệt đối; có thể tạo false positive hoặc false negative do naming/version/edition khác nhau.

### 5.5. bom-ref và SPDXID

Các format có cách tham chiếu component nội bộ của tài liệu như **bom-ref** (CycloneDX) hoặc **SPDXID** (một số biểu diễn SPDX). Chúng giúp tạo graph relationships **trong phạm vi BOM**; không nên tự coi một internal ID là global persistent identity của package.

### 5.6. Hash, checksum và chữ ký

- **Digest/hash** giúp xác định bytes (theo thuật toán và phạm vi) và hỗ trợ so khớp.
- **Signature** giúp xác minh nguồn ký và integrity theo trust model.
- **SBOM artifact digest** xác nhận file SBOM không đổi kể từ thời điểm được hash/ký.
- **Component digest** hỗ trợ đối chiếu một JAR/package cụ thể.
- **Image digest** giúp gắn deployed container với một image immutable reference.

Dùng **hash không chứng minh nguồn đáng tin hoặc code không độc hại**. Ký một SBOM tạo từ dữ liệu thiếu sẽ chỉ xác nhận **tài liệu thiếu đó** do signer phát hành; không làm nội dung đầy đủ hơn.

## 6. SPDX và CycloneDX

### 6.1. Hai định dạng phổ biến

**SPDX** và **CycloneDX** là những tiêu chuẩn/mô hình máy đọc được dùng để biểu diễn SBOM và những thông tin liên quan. Cả hai có nhiều phiên bản với khả năng khác nhau; lựa chọn cần dựa vào **interoperability, yêu cầu tổ chức/khách hàng, đối tượng BOM, khả năng generator/validator và pipeline sử dụng**.

| Khía cạnh | SPDX | CycloneDX |
|---|---|---|
| Điểm mạnh thường dùng | Component relationships, package metadata, license/compliance, supply-chain data | Component inventory, dependency graph, security-oriented extensions và tích hợp toolchain |
| Định dạng | Các serialization được hỗ trợ tùy phiên bản | JSON/XML và dạng được schema hỗ trợ tùy phiên bản |
| Identifiers | SPDX document IDs, package IDs, external refs | bom-ref, purl, CPE/external references |
| Relationships | Relationship model theo version | Dependency graph cùng metadata/components |
| License | License expressions và metadata theo model | License identifiers/expressions theo version/profile |
| Vulnerability-related | Khả năng tùy version/model | Có cấu trúc hỗ trợ vulnerability/VEX-related data tùy phiên bản |
| Validation | Schema/spec/profile phù hợp | Schema/spec/profile phù hợp |
| Lưu ý | Không suy schema mới từ ví dụ version cũ | Không giả định consumer hỗ trợ field mới nhất |

Không nên khẳng định một format “an toàn hơn” format kia chỉ vì tên hoặc popularity. **Coverage và integrity của dữ liệu thực** quan trọng hơn extension của file.

### 6.2. Format version là một phần của contract

Một parser hỗ trợ CycloneDX 1.4 không nhất thiết xử lý chính xác mọi field trong bản mới hơn; tương tự SPDX 2.x và 3.x có sự khác biệt mô hình. Requirement phải nêu:
- Accepted standards/versions.
- Required/optional profile fields.
- Validation tool/version.
- Cách xử lý unknown extensions.
- Backward compatibility/migration.
- Cách báo lỗi nếu consumer không đọc được schema.

### 6.3. Chuyển đổi giữa formats

Chuyển từ CycloneDX sang SPDX hoặc ngược lại có thể:
- Mất một số trường chỉ có ở nguồn.
- Gộp/đổi relationship semantics.
- Không có mapping hoàn hảo cho supplier, license, pedigree hoặc annotations.
- Thay đổi IDs nội bộ.
- Làm giảm độ chính xác vulnerability/asset binding nếu không có metadata kèm theo.

**File sau chuyển đổi parse được không đồng nghĩa bảo toàn tất cả ý nghĩa**. Test interoperability cần so sánh scope, component count/identity, relationships, required fields và evidence of information loss.

## 7. SBOM có nhiều “thời điểm nhìn”

### 7.1. Source SBOM

Inventory dựa trên source manifests/lockfiles và vendored code. Tốt cho planning, PR review, early vulnerability detection. Hạn chế là build resolution có thể đổi theo profiles, platform/architecture, dynamic versions hoặc plugins.

### 7.2. Build SBOM

Inventory từ resolved dependency graph và build process. Có thể phản ánh dependencies thực tế hơn source declaration. Nhưng vẫn có thể thiếu OS/runtime/native components, hoặc khác artifact sau repackaging.

### 7.3. Artifact SBOM

BOM sinh hoặc kiểm chứng từ JAR/WAR, container image hoặc binary đã đóng gói. Hữu ích cho đối chiếu **bytes sắp release**. Có thể khó định danh component được shade, compile/static link hoặc không còn manifest; cần công bố unknowns.

### 7.4. Deployment/runtime SBOM

BOM mô tả những thành phần có trong deployed workloads hoặc quan sát runtime. Có thể bổ sung dynamic plugins, JRE/base image, injected agents, sidecars và environment differences. Runtime inventory **không nhất thiết** nhận diện đầy đủ các thành phần chỉ nằm dormant/offline.

### 7.5. Product/system SBOM

Một nền tảng có nhiều services cần **aggregation với boundaries**:
- learning-api image digest A;
- report-worker image digest B;
- frontend static bundle digest C;
- identity service/version D;
- database extensions/runtime E;
- service mesh and monitoring agents trong scope.

Nếu gộp mọi component vào danh sách phẳng mà bỏ links tới artifact/service, sẽ khó xác định **component nằm ở đâu** và release nào bị ảnh hưởng.

### 7.6. Build vs deployed reconciliation

Một nguyên tắc quan trọng cho assurance:

> Không kết luận production đang dùng component X dựa duy nhất vào dependency manifest của main branch; cần nối **deployed workload → image/artifact digest → build provenance → SBOM revision** và kiểm tra các thành phần runtime ngoài phạm vi build.

## 8. Threat model của chính quy trình tạo và phân phối SBOM

### 8.1. Chuỗi tin cậy

~~~mermaid
flowchart LR
    S["Source / dependency inputs"] --> B["Build / resolve"]
    B --> A["Artifact / image digest"]
    B --> G["SBOM generator"]
    A --> V["BOM completeness verification"]
    G --> V
    V --> K["Sign / attest + publish"]
    K --> R["SBOM registry / evidence store"]
    R --> C["Consumers: SCA, SOC, customer"]
    A --> D["Deploy"]
    D --> X["Runtime inventory reconciliation"]
    X --> C
~~~

Mỗi bước có trust boundary: repo/dependency registry, CI runner, generator, signer, SBOM storage, consumer, deployed platform.

### 8.2. Các kịch bản rủi ro

| Threat | Ví dụ | Controls |
|---|---|---|
| **Tampering** | Attacker sửa BOM để xóa package bị ảnh hưởng | Build-linked digest/signature, protected registry |
| **Incomplete inventory** | Generator bỏ OS/native dependencies | Artifact scanning, multi-source coverage, reconciliation |
| **Wrong binding** | SBOM của image A gắn nhầm image B | Digest binding, release metadata, negative tests |
| **Stale BOM** | Deploy bản mới nhưng dùng SBOM cũ | CI gate và deployment mapping |
| **Generator compromise** | Tool/plugin tự bỏ component hoặc chèn false data | Pinned/verified tool, isolated CI, independent spot-checks |
| **Registry substitution** | BOM bị thay ở nơi phân phối | Immutable refs, signatures/verification, access controls |
| **Identity confusion** | purl/CPE mapping sai hoặc trùng tên | Canonicalization, reviewed matching, uncertainty flags |
| **SBOM leakage** | BOM công khai tiết lộ technology stack/versions/internal paths | Classification, audience-scoped distribution |
| **Dependency confusion** | Package resolve nhầm nguồn public thay private | Registry priority/policies, provenance, reproducible builds |
| **Opaque vendor gap** | Vendor không cung cấp danh mục thành phần | Contract/evidence, risk treatment, explicit exclusions |
| **False assurance** | Dashboard báo 100% SBOM nhưng chỉ scan manifests | Coverage definition, artifact tests, limitations |

### 8.3. Tamper-proof tuyệt đối là tuyên bố quá rộng

Dùng signatures, immutable storage, transparency logs hoặc access separation giúp hạn chế rủi ro. Nhưng nếu builder hoặc generator đầu vào đã bị chiếm, BOM có thể sai ngay từ lúc sinh. Assurance cần xem **data source reliability** và dùng independent verification phù hợp với mức quan trọng.

## 9. Sinh SBOM cho dự án Java

### 9.1. Nguồn dữ liệu ở Maven

Maven project có thể sử dụng:
- **pom.xml**: khai báo dependencies, plugins, profiles, repositories và management.
- **Resolved dependency tree**: dependency thực tế với scopes, conflict resolution và transitive graph.
- **Effective POM**: kết quả kết hợp inherited configuration, properties/profiles.
- **Build outputs**: JAR/WAR và thư viện kèm theo.
- **Repository metadata**: package group, artifact, version, checksums, license metadata.
- **JDK/JRE**: môi trường runtime, đôi khi nằm ngoài application dependency graph.

Để tạo SBOM phục vụ assurance, phải xác định **profiles, settings, repositories, platform, build options và artifacts** được dùng khi phát hành. Nếu CI build với một profile riêng mà developer tạo BOM bằng profile mặc định, kết quả có thể khác.

### 9.2. Ví dụ Maven command (minh họa)

~~~bash
# Quan sát dependency graph đã resolve của module hiện tại.
mvn dependency:tree

# Ví dụ goal của CycloneDX Maven plugin.
# Plugin/version/config và output cần được pin và xác minh theo CI thực tế.
mvn org.cyclonedx:cyclonedx-maven-plugin:makeAggregateBom

# Không dùng output của lệnh ví dụ như chứng cứ production
# khi chưa gắn với commit, Maven/JDK/config và artifact digest.
~~~

Đây là câu lệnh gợi ý để hình dung workflow, **không phải yêu cầu đã được thực thi** và không ngầm tuyên bố một plugin version cụ thể. Một dự án multi-module cần xác định **module aggregation, optional dependencies, plugins, excluded scopes** và xử lý duplicate components.

### 9.3. Các yếu tố gây khác biệt trong Maven

- dependencyManagement có thể chỉ định version nhưng **không đồng nghĩa package thực sự xuất hiện**.
- Profiles thay dependency tree theo môi trường/flag.
- Dependency exclusions làm mất hoặc thay transitive packages.
- BOM import trong Maven (dependency version management) **khác SBOM**; cùng từ “BOM” nhưng vai trò khác.
- Classifier/packaging có thể thay bytes và runtime dependencies.
- System-scope local JAR và private repository dependencies có thể thiếu metadata nguồn.
- Shading/relocation có thể giấu package identity.
- Build plugins/code generators có supply-chain exposure dù không vào runtime artifact.
- JDK version và native libraries thay đổi theo runtime image.

### 9.4. Scope cho một project Spring

Một Spring-based Learning API có thể bao gồm:
- Spring Web/Security/Data.
- JSON serialization.
- Database driver.
- HTTP client.
- Logging dependencies.
- Validation library.
- Observability/telemetry agent.
- Embedded servlet container.
- JRE, OS packages trong image.
- Internal shared libraries.
- Additional plugins/assets nếu có.

BOM từ Maven có thể **đúng** đối với resolved application dependencies nhưng **chưa đầy đủ** đối với toàn container/runtime. Cần ghi rõ claim: *Maven build dependency SBOM* hay *deployed image SBOM*.

## 10. Gradle, lockfiles và multi-project builds

### 10.1. Gradle dependency resolution

Gradle có configurations (ví dụ compileClasspath, runtimeClasspath, testRuntimeClasspath) và có thể dùng version catalogs, platforms/BOMs, constraints, variant selection và dependency locking.

SBOM cho runtime nên xét:
- Configuration nào được resolve.
- Modules/subprojects nào thuộc release.
- Composite builds và included builds.
- Resolved versions vs dynamic/range declarations.
- Platform/architecture và toolchain.
- Gradle plugin/build-time dependencies có được inventoried riêng không.
- Dependency graph có file/local/project dependencies được định danh không.

### 10.2. Ví dụ lệnh (minh họa)

~~~bash
# Inspect resolved runtime dependencies.
./gradlew dependencies --configuration runtimeClasspath

# Ví dụ task của CycloneDX Gradle plugin khi đã cấu hình.
./gradlew cyclonedxBom
~~~

Tên task/configuration và output có thể khác theo phiên bản plugin, Gradle và cấu trúc multi-project. CI phải pin tool versions và kiểm tra file đầu ra/metadata thực tế; không nên copy một lệnh rồi cho rằng BOM đạt completeness.

### 10.3. Lockfile là input, không phải kết luận

Locking giúp reproducible resolution, nhưng:
- Lockfile có thể không bao gồm base OS/image.
- Một artifact có thể chứa thư viện vendored/shaded không xuất hiện trong lockfile.
- Lockfile có thể khác theo configuration/platform.
- Runtime có thể tải plugin hoặc code ngoài artifact build.
- Một dependency khóa phiên bản cũ vẫn có thể vulnerable.
- Lockfile không tự chứng minh artifacts được tải từ registry đúng nguồn.

Cần kết hợp resolved dependencies, artifact inspection và provenance.

### 10.4. Multi-module graph

Ví dụ:
- learning-api phụ thuộc learning-domain;
- learning-domain phụ thuộc permission-library;
- report-worker phụ thuộc document-converter;
- cả hai sử dụng shared-client.

Một aggregate SBOM có thể hữu ích cho toàn release, nhưng security response cần biết **thành phần nào nằm trong artifact/service nào**. Hãy giữ mối liên hệ giữa module → build artifact → image → deployment, thay vì chỉ tạo một file tổng rồi mất containment boundaries.

## 11. Fat JAR, shading, native libraries và hidden components

### 11.1. Khi manifest không khớp bytes

Java executable fat JAR/WAR thường bao gồm nhiều nested JAR hoặc bytecode được repackage. Công cụ dựa trên dependency graph có thể:
- Liệt kê package không thực sự đóng gói.
- Bỏ sót một JAR copy thủ công.
- Gộp những component có cùng metadata nhưng bytes khác.
- Không nhận ra shaded/relocated classes.
- Không nhận dạng binary native libs.
- Không phát hiện plugin/runtime agent được thêm sau build.

### 11.2. Shaded JAR

Shading có thể trộn nhiều dependencies vào một artifact và đổi package names. Khi gặp advisory ảnh hưởng bản gốc, tên class trong JAR có thể không còn map trực tiếp tới Maven coordinates. Cần:
1. Lưu build dependency graph và shading rules.
2. Theo dõi source packages và versions.
3. Inspect artifact khi cần bằng công cụ phù hợp.
4. Ghi uncertainties nếu không map được component.
5. Đánh giá impact theo vulnerable code/config, không chỉ tên tệp.
6. Nêu provenance của shaded artifact.
7. Test detection bằng fixture có shaded dependency đại diện.

Không dựa vào absence of a package name trong archive để kết luận source code đó hoàn toàn không xuất hiện.

### 11.3. Native binaries và JRE

Java service có thể dùng:
- JNI/JNA library.
- OpenSSL hoặc system TLS library qua tool/sidecar.
- OS packages và libc.
- Database/native drivers.
- JDK/JRE modules.
- Chromium/headless browser hoặc PDF converter cho report worker.
- Third-party command-line tools.

Để có inventory **runtime image**, cần nhìn thêm binary/OS package layers và cách deployment cấu hình các công cụ ngoài JVM.

### 11.4. Test cho completeness

Tạo một controlled fixture:
- Một direct dependency.
- Một transitive dependency.
- Một vendored JAR.
- Một shaded library.
- Một native library.
- Một OS package trong image.
- Một runtime-injected agent.

So sánh SBOM generated theo từng source với expected test inventory. Các trường hợp không nhận dạng được phải được **báo Unknown/Unidentified**, không tự lờ đi để đạt coverage 100%.

## 12. SBOM cho container và hệ điều hành

### 12.1. Vì sao image SBOM bổ sung cho Java SBOM?

Một container image chứa:
- Base image layers.
- OS packages.
- Java runtime.
- Application JAR/WAR.
- Native dependencies hoặc tools.
- Config/assets.
- Agents và binaries bổ sung.

Công cụ quét image có thể tìm packages không xuất hiện trong pom.xml, nhưng đôi khi không thể nhận diện **nguồn và version chính xác** của compiled/static/shaded code. Kết hợp **build-generated BOM và image-scanned BOM** giúp bù đắp blind spots.

### 12.2. Image digest vs mutable tag

**Tag** như learning-api:latest hoặc learning-api:prod có thể thay đổi theo thời gian. **Digest** định danh nội dung image trong mô hình registry. Để assurance:
- Gắn SBOM với **immutable image digest** thay vì chỉ tag.
- Lưu image architecture/platform (amd64, arm64...) khi multi-platform.
- Theo dõi registry/repository/source.
- Tách SBOM theo từng platform-specific image khi bytes/components khác.
- Xác nhận deployed runtime image digest đúng digest đã scan.
- Không coi rebuild cùng version/tag tạo cùng bytes.
- Định nghĩa cách xử lý image đã bị xóa khỏi registry nhưng còn chạy.

### 12.3. Ví dụ minh họa quy trình

~~~bash
# Pseudocode workflow — thay bằng công cụ/version đã được phê duyệt.
# 1) Build image và nhận digest immutable.
# 2) Generate SBOM từ image digest, không chỉ tag.
# 3) Validate schema và required component metadata.
# 4) Bind BOM digest, image digest, commit và CI build ID.
# 5) Sign/attest rồi lưu vào protected artifact registry.
# 6) Chỉ deploy digests có attestation hợp lệ theo policy.
# 7) Reconcile runtime image digest với release mapping.
~~~

Công cụ như **Syft** hoặc image scanners hỗ trợ tạo inventory từ filesystem/image; công cụ như **Trivy** có khả năng inventory/scan theo chế độ và phiên bản. Mỗi tool có **coverage model và blind spots** riêng, phải ghi version/config và kiểm tra thực tế. Không coi một câu lệnh generic là bằng chứng mọi embedded component đều được phát hiện.

### 12.4. Container layers, multi-stage builds và distroless

- Multi-stage build có tool/dependency trong build stage không nằm trong final runtime image. Build supply-chain risk và runtime inventory là **hai phạm vi khác nhau**.
- Distroless/minimal images giảm attack surface nhưng có thể gây khó định danh OS packages; không phải “0 package”.
- Copy binary thủ công có thể không còn package manager metadata.
- Multi-architecture manifests có thể trỏ tới images khác nhau.
- Sidecars/init containers không thuộc application image nhưng có trong deployed system.
- Runtime-installed packages hoặc writable layer changes có thể khiến deployed state khác image gốc.

### 12.5. Base image inheritance

Nếu image của API dùng base image B và B có vulnerable library, sản phẩm có thể chịu ảnh hưởng. Cần lưu relationship/image ancestry khi phù hợp, nhưng tránh **đếm trùng** component từ layers và final filesystem. Hãy phân biệt component present in final image với package trong removed build stage.

## 13. Một ví dụ CycloneDX JSON

Ví dụ này **cố ý nhỏ và có dữ liệu hư cấu** để học cách đọc graph, không phải SBOM production, không khẳng định hoàn toàn conformant với mọi organizational profile. Các giá trị có thể cần cập nhật theo schema/tool version khi triển khai thật.

~~~json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.6",
  "serialNumber": "urn:uuid:123e4567-e89b-42d3-a456-426614174000",
  "version": 1,
  "metadata": {
    "timestamp": "2026-11-28T00:00:00Z",
    "tools": {
      "components": [
        {
          "type": "application",
          "name": "example-sbom-generator",
          "version": "1.0.0"
        }
      ]
    },
    "component": {
      "type": "application",
      "bom-ref": "app:learning-api",
      "name": "learning-api",
      "version": "1.4.2"
    }
  },
  "components": [
    {
      "type": "library",
      "bom-ref": "pkg:maven/org.example/json-helper@2.1.0",
      "group": "org.example",
      "name": "json-helper",
      "version": "2.1.0",
      "purl": "pkg:maven/org.example/json-helper@2.1.0"
    },
    {
      "type": "library",
      "bom-ref": "pkg:maven/org.example/core-util@3.0.0",
      "group": "org.example",
      "name": "core-util",
      "version": "3.0.0",
      "purl": "pkg:maven/org.example/core-util@3.0.0"
    }
  ],
  "dependencies": [
    {
      "ref": "app:learning-api",
      "dependsOn": [
        "pkg:maven/org.example/json-helper@2.1.0"
      ]
    },
    {
      "ref": "pkg:maven/org.example/json-helper@2.1.0",
      "dependsOn": [
        "pkg:maven/org.example/core-util@3.0.0"
      ]
    },
    {
      "ref": "pkg:maven/org.example/core-util@3.0.0",
      "dependsOn": []
    }
  ]
}
~~~

**Cách đọc:**
- BOM metadata mô tả sản phẩm **learning-api 1.4.2**.
- Hai thư viện được liệt kê trong components.
- Dependency graph nói **learning-api → json-helper → core-util**.
- Trong ví dụ này purl được dùng làm bom-ref, nhưng **bom-ref chỉ cần unique trong BOM theo rules của format**, không bắt buộc luôn là purl.
- Timestamp là thời điểm minh họa; không nói lên release nào đã deploy.
- Chưa có license, supplier, hash, dependency scope, provenance và actual image digest. Những thông tin đó phải được bổ sung theo **profile và mục đích đánh giá**, không kết luận file đã đầy đủ.
- Không có vulnerability entry không có nghĩa package không có CVE.

### 13.1. Các phép kiểm tra cho ví dụ

1. BOM parse được với schema/version đã chọn.
2. Component name/version có kiểu và giá trị hợp lệ.
3. Mỗi relationship ref trỏ tới bom-ref hợp lệ (kể cả root metadata component theo spec).
4. bom-ref unique trong tài liệu.
5. Dependency graph không vô cớ bỏ relationship dự kiến.
6. purl phù hợp ecosystem và version cụ thể.
7. Không có credentials/private URLs.
8. Timestamp/creator metadata tồn tại.
9. Target artifact binding được bổ sung ở release package/attestation.
10. Nếu một tool chuyển format, graph semantics không bị mất.

## 14. Một ví dụ SPDX JSON

Ví dụ **SPDX 2.3** sau thể hiện document, package entries và relationships ở mức rút gọn. Đây là dữ liệu hư cấu; khi cần đáp ứng kiểm thử conformant thực tế, phải dùng generator/validator chính thức với schema/profile đã phê duyệt.

~~~json
{
  "spdxVersion": "SPDX-2.3",
  "dataLicense": "CC0-1.0",
  "SPDXID": "SPDXRef-DOCUMENT",
  "name": "learning-api-example-sbom",
  "documentNamespace": "https://example.invalid/spdx/learning-api/1.4.2/demo",
  "creationInfo": {
    "creators": ["Tool: example-sbom-generator-1.0.0"],
    "created": "2026-11-28T00:00:00Z"
  },
  "packages": [
    {
      "name": "learning-api",
      "SPDXID": "SPDXRef-App",
      "versionInfo": "1.4.2",
      "downloadLocation": "NOASSERTION",
      "filesAnalyzed": false,
      "licenseConcluded": "NOASSERTION",
      "licenseDeclared": "NOASSERTION",
      "copyrightText": "NOASSERTION"
    },
    {
      "name": "json-helper",
      "SPDXID": "SPDXRef-JsonHelper",
      "versionInfo": "2.1.0",
      "downloadLocation": "NOASSERTION",
      "filesAnalyzed": false,
      "licenseConcluded": "NOASSERTION",
      "licenseDeclared": "NOASSERTION",
      "copyrightText": "NOASSERTION"
    }
  ],
  "relationships": [
    {
      "spdxElementId": "SPDXRef-DOCUMENT",
      "relatedSpdxElement": "SPDXRef-App",
      "relationshipType": "DESCRIBES"
    },
    {
      "spdxElementId": "SPDXRef-App",
      "relatedSpdxElement": "SPDXRef-JsonHelper",
      "relationshipType": "DEPENDS_ON"
    }
  ]
}
~~~

**Cách đọc:** document mô tả **learning-api** và quan hệ phụ thuộc tới **json-helper**. “NOASSERTION” không có nghĩa “không có license”; nó thể hiện **chưa có assertion** cho trường tương ứng. Nếu license/legal review cần thông tin chính xác, đây là **gap phải xử lý**, không phải Pass.

### 14.1. Không ghép nhầm phiên bản SPDX

SPDX 2.x và SPDX 3.x có cách mô hình hóa/serialization khác nhau. Không dùng ví dụ trường JSON của SPDX 2.3 để khẳng định đó là cấu trúc đúng của mọi SPDX 3.x document. Consumer contract phải nêu accepted versions và test conversion/migration.

## 15. SBOM requirements: biến inventory thành đối tượng kiểm thử

### 15.1. Requirement tốt cần rõ

Một câu mơ hồ: “Mọi ứng dụng phải có SBOM”.

Một yêu cầu có thể kiểm chứng:

> Với mọi containerized production release của các critical services trong inventory, CI phải tạo SBOM máy đọc được ở format/version được phê duyệt từ resolved build và/hoặc immutable final image; SBOM phải liên kết đúng source revision, artifact digest, build ID và release identity, có component/dependency identifiers theo required profile. Pipeline phải validate schema và completeness checks, publish SBOM với integrity/access controls và báo lỗi nếu generator/validation không chạy. Mọi exclusions hoặc unknown components được ghi rõ và xử lý theo risk policy.

Requirement có:
- **Population:** production releases của critical services.
- **Trigger:** build/release.
- **Source:** resolved build/final image.
- **Format:** accepted machine-readable schema/version.
- **Identity/binding:** revision/digest/build.
- **Fields/coverage:** component metadata/graph.
- **Failure behavior:** reject/quarantine/exception.
- **Evidence:** CI reports, artifact, signatures, comparisons.
- **Owner:** Build/Platform/Product Security.
- **Risk:** dependency transparency và response.

### 15.2. Functional vs nonfunctional requirements

| Nhóm | Ví dụ | Verification |
|---|---|---|
| **Generation** | Sinh BOM mỗi production release | CI run và output |
| **Inventory depth** | Direct/transitive/native/OS coverage theo scope | Seeded fixtures, artifact comparison |
| **Identity quality** | Exact versions, purl/hash khi có | Field validation, resolution tests |
| **Relationships** | Dependency graph đủ cho profile | Referential integrity, known graph tests |
| **Freshness** | Mỗi release gắn BOM hiện hành | Commit/build/image digest match |
| **Integrity/authenticity** | BOM được ký/attest và lưu có kiểm soát | Signature/auth policy tests |
| **Availability** | SOC/SCA có thể lấy BOM đúng digest | Registry/query/API tests |
| **Timeliness** | Query impacted assets trong response window | Drill với advisory giả định |
| **Privacy/access** | External consumers chỉ nhận BOM đã phê duyệt | ACL, classification, redaction tests |
| **Lifecycle** | BOM giữ/retire theo retention và release policy | Archive/deletion/restore tests |
| **Exception handling** | Missing/failed generation không biến thành Pass | CI gate negative tests |

### 15.3. Định nghĩa “complete” theo phạm vi

Có thể đo những lớp:
- Application declared/resolved packages.
- Transitive dependencies.
- Vendored/bundled libraries.
- Native binaries.
- OS packages.
- Runtime (JDK/JRE).
- Container image and sidecars.
- Runtime-loaded plugins.
- SaaS/vendor-managed components.

Một SBOM generation control có thể đạt hoàn toàn **trong scope Maven resolved dependencies**, nhưng **không đạt yêu cầu toàn deployed system**. Báo cáo cần chỉ rõ scope được kiểm tra và phần chưa được bao phủ.

## 16. Gắn SBOM với artifact và build provenance

### 16.1. Chuỗi bằng chứng

~~~mermaid
flowchart TD
    C["Source revision C"] --> B["Build run B"]
    B --> D["Artifact/image digest D"]
    B --> S["SBOM digest S"]
    D --> A["Attestation: subject=D, SBOM=S"]
    S --> A
    A --> R["Protected registry + verification"]
    R --> DEP["Deployment references D"]
    DEP --> V["Runtime reconciliation"]
    V --> Q["Assurance / vulnerability impact"]
~~~

**Artifact digest là khóa đối chiếu chính** vì tag/version label có thể trùng hoặc mutable. Build provenance giúp biết source, builder, dependencies, process và subject theo mô hình được chọn. SBOM có thể được đóng gói cùng artifact hoặc publish như **related artifact/referrer/attestation** tùy registry/toolchain.

### 16.2. Không nhầm generator identity với component supplier

- “SBOM generated by CI scanner” chỉ nói **ai tạo danh mục**.
- “Package supplied by organization X” là một metadata của component.
- “Artifact built by CI builder Y” thuộc provenance.
- “Signed by key Z” nói ai/khóa nào ký.
- “Deployed by platform P” nói về deployment.

Đây là **các trust statements khác nhau**, cần bằng chứng và policies riêng.

### 16.3. In-toto/SLSA và SBOM

Khái niệm **attestation** có thể dùng để gắn statement về build/artifact với evidence và chữ ký. SLSA đề cập những thực hành/mức độ bảo đảm cho supply-chain/build provenance; in-toto cung cấp mô hình liên kết/signed statements cho chuỗi tạo artifact. SBOM là inventory và **không tự tương đương** một provenance statement hoặc điểm SLSA.

Không khẳng định “có SBOM = đạt SLSA” hoặc “provenance hợp lệ = không có vulnerability”. Kết hợp chúng để tăng khả năng truy vết và xác minh.

### 16.4. Verify trước release và sau deploy

1. Validate SBOM schema/profile.
2. Check dependency graph và required fields.
3. Compare SBOM target with immutable artifact digest.
4. Verify signer/attestation theo trust policy (không chỉ signature cryptographic pass).
5. Link source commit, build run và artifact digest.
6. Xác nhận release tag/channel trỏ đúng digest.
7. Verify workload đang chạy digest tương ứng.
8. Kiểm tra runtime-added components/sidecars theo scope.
9. Lưu evidence với thời gian, config, tool versions và reviewer.
10. Reassess sau rebuild, patch base image, rollback hoặc plugin update.

Một release có version string không thay đổi nhưng được rebuild với base image mới **cần đánh giá BOM mới** nếu bytes/components đã thay.

## 17. SBOM và Software Composition Analysis (SCA)

### 17.1. Từ component inventory đến vulnerability intelligence

Một SCA workflow thường gồm:
1. Lấy SBOM hoặc inventory trực tiếp từ source/build/image.
2. Chuẩn hóa package identity/version.
3. Đối chiếu advisory databases, vendor bulletins và policy.
4. Xác định affected version ranges và mapping.
5. Kiểm tra package/artifact thực sự có trong deployed scope.
6. Phân tích exploitability/exposure/reachability khi có cơ sở.
7. Ưu tiên theo impact, khả năng bị khai thác, context và controls.
8. Fix/mitigate/risk accept theo quy trình.
9. Rebuild, regenerate SBOM, scan, deploy và retest.
10. Theo dõi advisory mới ngay cả khi BOM không đổi.

**SBOM không chứa trạng thái lỗ hổng hiện hành cố định**. Một BOM sinh tuần trước vẫn có thể là inventory đúng cho release đó, nhưng các advisory và đánh giá rủi ro phải được cập nhật khi có thông tin mới.

### 17.2. Matching không luôn chính xác

Tên package, namespace, vendor, version và CPE mapping có thể mơ hồ, nhất là:
- Forks và repackaged packages.
- Shaded JAR không giữ manifest nguồn.
- Proprietary backports: version nhìn cũ nhưng chứa patch.
- Version suffix/revision của OS vendor.
- Runtime có nhiều phiên bản của cùng thư viện.
- CPE product name trùng giữa sản phẩm khác.
- Package được build tùy chọn bỏ một tính năng.
- Source tarball vs binary package có khác patches.

Một finding cần ghi **matching basis, confidence và uncertainty**, không mặc định exact match chỉ vì tên giống nhau.

### 17.3. Đầu ra SCA khác SBOM

| SBOM | SCA / vulnerability analysis |
|---|---|
| Thành phần/phiên bản/quan hệ có trong phạm vi | Liên kết advisory và affected ranges |
| Thường gắn với artifact hoặc release | Có thể thay đổi khi threat intelligence mới |
| Có metadata định danh và license | Có severity, fix availability, status/rationale |
| Giúp tìm owners/systems affected | Giúp quyết định remediation và tracking |
| Cần accuracy, completeness và binding | Cần matching quality, exposure và risk prioritization |

Để audit, lưu **cả SBOM snapshot và intelligence/analysis version/time**. Re-run scanner hôm nay có thể khác scan ngày phát hành dù binary không đổi.

## 18. VEX: SBOM cho biết có gì, VEX cho biết ảnh hưởng ra sao

### 18.1. VEX là gì?

**Vulnerability Exploitability eXchange (VEX)** là cách trao đổi thông tin về **trạng thái ảnh hưởng của một lỗ hổng đối với một sản phẩm/phiên bản cụ thể**, thường kèm justification/rationale. VEX bổ sung cho SBOM khi một component có advisory nhưng product không bị ảnh hưởng trong điều kiện được đánh giá.

Các trạng thái trong những mô hình VEX phổ biến có thể gồm **affected, not_affected, fixed, under_investigation**, tùy chuẩn/version/profile được sử dụng. Không tự coi mọi tool/format có cùng tên trường và semantics.

### 18.2. Ví dụ not affected có căn cứ

Một thư viện bị ảnh hưởng chỉ trong một tùy chọn parser mà learning-api không sử dụng. Tổ chức có thể kết luận **not affected** *cho release R và cấu hình X* nếu có chứng cứ:
- Vulnerable function/code path không được đóng gói hoặc không reachable theo mô hình được kiểm tra.
- Hoặc configuration không kích hoạt vulnerable behavior.
- Hoặc platform/architecture không chịu ảnh hưởng.
- Hoặc phần code chứa vulnerability không có trong binary.
- Hoặc có vendor patch/backport đã được xác minh.

Một tuyên bố “not affected” cần **product scope, advisory ID, status, reason, evidence và reassessment trigger**. Chỉ vì unit tests không gây crash không đủ.

### 18.3. VEX status không thay remediation

| Status minh họa | Ý nghĩa thực hành | Câu hỏi assurance |
|---|---|---|
| **affected** | Sản phẩm được đánh giá chịu ảnh hưởng | Controls tạm và fix plan? |
| **not_affected** | Có căn cứ chứng minh không ảnh hưởng trong scope | Evidence, assumption, config/release binding? |
| **fixed** | Đã có fix cho product/version được nêu | Build/deploy digest, retest, remaining deployments? |
| **under_investigation** | Chưa đủ kết luận | Owner, deadline, protective measures, monitoring? |

Một VEX statement của vendor có thể đáng tham khảo nhưng vẫn cần xem **đúng product/version/config/usage scope**. Nếu tổ chức build lại, enable feature, đổi JVM hoặc dependency, status cần được đánh giá lại.

### 18.4. Ví dụ VEX-like record (không theo schema chuẩn)

~~~yaml
assessment_id: "VEX-EXAMPLE-01"
product:
  name: "learning-api"
  artifact_digest: "replace-with-real-sha256"
vulnerability: "CVE-EXAMPLE-XXXX"
component:
  purl: "pkg:maven/org.example/json-helper@2.1.0"
status: "under_investigation"
rationale: "Pending reachability and configuration assessment"
evidence:
  - "Link to SBOM and component match report"
  - "Link to vulnerability advisory"
  - "Link to code/config/runtime review"
owner: "Learning Backend / AppSec"
reassessment_triggers:
  - "New advisory details"
  - "Code or configuration changes"
  - "New deployed artifact digest"
~~~

Ví dụ chỉ nhằm minh họa **quản trị thông tin impact**, không nên nộp YAML này như CycloneDX/SPDX/OpenVEX conformant document. Nếu cần VEX interoperability, dùng schema/version và validator của format được chọn.

## 19. Reachability, exploitability và severity

### 19.1. Có component không đồng nghĩa exploitable

Một library xuất hiện trong SBOM có thể:
- Được dùng trực tiếp ở endpoint Internet-facing.
- Chỉ nằm ở công cụ build.
- Có trong binary nhưng chức năng vulnerable không được gọi.
- Chạy trong service không exposed trực tiếp.
- Bị ảnh hưởng bởi config/platform cụ thể.
- Có patch backport chưa thể hiện trong upstream version number.
- Đã được sandbox/isolated nhưng vẫn có residual risk.

Ngược lại, **không tìm thấy call graph path** không tự chứng minh không thể bị khai thác: reflection, dynamic loading, native code, serialization, runtime config và indirect calls có thể làm static reachability yếu.

### 19.2. Priority không chỉ dựa vào CVSS

Các tín hiệu hữu ích gồm:
- Severity/impact từ advisory (ví dụ CVSS trong scope).
- Khả năng bị khai thác/đang bị khai thác (threat intelligence phù hợp).
- Asset criticality và data sensitivity.
- Exposure: Internet-facing, internal, authenticated only, privileged.
- Reachability và code/config conditions.
- Privilege requirements, compensating controls và blast radius.
- Patch availability, workarounds, operational risk.
- Confidence/uncertainty và response window.

Một sản phẩm có low-rated library vulnerability nhưng nằm ở trust boundary xử lý dữ liệu nhạy cảm vẫn cần xem risk. Một advisory được đánh giá rất nghiêm trọng nhưng không nằm trong runtime có thể được triage với evidence thay vì remediation bừa.

### 19.3. Bằng chứng cần cho triage

- SBOM component ID và artifact digest.
- Advisory source/ID và affected ranges, ngày truy vấn.
- Matching logic/metadata hoặc vendor patch confirmation.
- Runtime deployment mapping.
- Code path/config/feature usage.
- Attack surface/threat model.
- Negative tests/PoC được phép khi thích hợp và an toàn.
- Control mitigations, compensating controls.
- Risk owner decision, review time và retest.

## 20. SBOM cho ứng phó zero-day và incident

### 20.1. Mục tiêu thời gian phản ứng

Khi có advisory nghiêm trọng, thời gian bị mất nhiều nếu không biết component đang ở đâu. Với SBOM inventory gắn deployed assets, SOC/PSIRT/AppSec có thể:
1. Tra cứu component identity và version ranges.
2. Truy ra affected artifacts, images và builds.
3. Xác định deployments đang hoạt động.
4. Tìm service/asset owners và data criticality.
5. Thu thập VEX/exposure analysis.
6. Thực hiện containment/mitigation khẩn cấp khi cần.
7. Lên lịch fix và chuẩn bị regression tests.
8. Verify build mới và deploy.
9. Theo dõi remaining vulnerable deployments.
10. Báo kết quả với evidence và limitations.

### 20.2. Impact query minh họa

~~~text
Advisory: CVE-EXAMPLE
Affected identity: pkg:maven/org.example/json-helper, versions < 2.2.0

Query SBOM registry by package identity and version range
  -> learning-api image digest D1
  -> report-worker image digest D2
  -> old staging image digest D3

Join with runtime inventory
  -> prod region A runs D1
  -> prod region B runs D2
  -> staging runs D3

Join with ownership/threat model
  -> learning-api: exposed JSON endpoint
  -> report-worker: internal batch parser
  -> staging: synthetic data

Create triage/remediation decisions per deployed artifact.
~~~

Đây là dữ liệu giả định, không phải khẳng định về advisory hoặc thư viện thật. **Không tự động cho rằng mọi component match chịu cùng impact**; cần context và VEX.

### 20.3. Tránh hai thất bại đối lập

- **Underreaction:** chỉ search source manifest mà bỏ image/native/sidecars; cho rằng không dùng nên không phản ứng.
- **Overreaction:** tất cả package cùng tên đều bị gắn critical mà không kiểm tra exact version, fork/backport, platform và runtime exposure; làm tắc đội phát triển.

Quy trình tốt **ưu tiên containment khi impact nghiêm trọng/uncertain**, đồng thời cập nhật evidence liên tục để điều chỉnh quyết định.

### 20.4. Giới hạn thông tin lúc đầu

Khi thiếu vendor SBOM, component ID sai hoặc artifact đã bị xóa:
- Đánh dấu **Unknown/Insufficient evidence**.
- Khai báo population chưa bao phủ.
- Dùng các nguồn thay thế: runtime scanning, deployment manifests, repository evidence, vendor inquiry.
- Không báo “not affected” từ việc query trả về zero rows nếu registry coverage chưa được chứng minh.

## 21. SBOM và license governance

### 21.1. Vì sao license xuất hiện trong SBOM?

SBOM có thể cung cấp:
- Component declared license.
- License expression hoặc multiple licenses.
- Supplier/attribution information.
- Source/download reference.
- Package-specific notices khi được cung cấp.
- Provenance của metadata license.

Với open-source governance, điều này giúp legal/product owners xác định obligations theo **cách sử dụng, phân phối, liên kết, sửa đổi và license terms**.

### 21.2. Declared vs concluded

Một package manifest có thể khai báo license nhưng artifact thật bao gồm các files theo license khác. SBOM metadata có thể phân biệt **declared** và **concluded** tùy format/version. Không coi “NOASSERTION”, “unknown” hay “unlicensed” đồng nghĩa nhau.

### 21.3. Không suy nghĩa vụ pháp lý tự động

Một parser báo license “GPL” không đủ để kết luận toàn bộ ứng dụng phải phát hành source. Cần xem license text, code usage, linking/distribution, exception, dual licensing, jurisdiction/contract và legal review. SBOM hỗ trợ **inventory**, không thay legal analysis.

### 21.4. License drift trong release

Nếu dependency được đổi transitive package, license obligations có thể đổi dù application code không đổi. Một release gate có thể yêu cầu:
- License metadata cho critical/distributed components.
- Flag incompatible/unknown license.
- Approval từ legal/open-source program office khi cần.
- Store notices/attribution evidence.
- Re-check khi supplier/version/shading thay đổi.

## 22. SBOM từ và cho nhà cung cấp (vendor/third party)

### 22.1. Supplier SBOM khác internal SBOM

Nhà cung cấp có thể cung cấp SBOM cho sản phẩm/phiên bản, còn bên mua cần kết nối với:
- Đúng release/edition/build mà mình dùng.
- Contractual support period.
- Distribution channel và update cadence.
- Fix/VEX advisory process.
- Cách xử lý vulnerability disclosures.
- Access/share conditions, confidentiality và license.
- Subcomponents/phần software supplier không trực tiếp kiểm soát.

**Vendor compliance report không tự chứng minh SBOM đủ cho build bạn đang chạy**.

### 22.2. Một SBOM request tốt

Yêu cầu có thể nêu:
1. Product/version/edition và update cycle.
2. SPDX/CycloneDX format/version chấp nhận.
3. Identifiers, dependency relationships và license metadata tối thiểu.
4. Cách gắn SBOM với artifact/release.
5. Signatures/attestations và trust verification khi cần.
6. Liệt kê known omissions/exclusions.
7. VEX/impact notification khi xuất hiện advisory mới.
8. Cơ chế tải/tiếp nhận, permissions và notification.
9. Data handling, classification và retention của BOM.
10. Contact/owner, incident handling và review cadence.

### 22.3. Không phải mọi SaaS đều cung cấp package-level SBOM

Với SaaS, bên mua có thể không có binary và vendor có thể không chia sẻ đầy đủ component list vì phạm vi, hợp đồng hoặc an ninh. Khi đó cần risk-based alternatives:
- Supplier assurance/questionnaire và independent reports đúng scope.
- Vulnerability/patch management attestation.
- Incident and disclosure commitments.
- Architecture/data-flow controls và API security.
- Contractual commitments, right-to-audit khi phù hợp.
- Resilience/exit plan.
- Record **evidence limitations** và residual risk.

Không được tự bịa một vendor SBOM hoặc đánh dấu “SBOM complete” từ bản marketing summary.

### 22.4. Phân phối SBOM cho khách hàng

SBOM có thể tiết lộ danh sách versions và architecture components. Để chia sẻ:
- Xác định classification, contractual obligations và authorized recipients.
- Có kênh phân phối được xác thực/phân quyền.
- Verify integrity, signatures và artifact version.
- Không đưa secrets, repository credentials hoặc private CI paths.
- Công bố exclusions, updates và contact.
- Tài liệu VEX riêng cho impact analysis.
- Theo dõi ai nhận và version nào nếu cần hỗ trợ update response.

Security-through-obscurity không phải thay cho patching; nhưng **data minimization và scope** của SBOM được chia sẻ vẫn cần thiết.

## 23. Đánh giá chất lượng SBOM: coverage, accuracy, freshness

### 23.1. Completeness

Câu hỏi: trong **population đã định nghĩa**, có bao nhiêu component hoặc artifacts được đại diện đúng?

Một metric có thể là:
- % critical services có SBOM cho deployed digest.
- % product release artifacts có linked SBOM.
- % known reference components được phát hiện bởi generator.
- % dependencies có unique identifiers và versions.
- % relationships hợp lệ theo dependency graph.
- % included native/OS/sidecar components theo scope.

**Không có mẫu số đáng tin thì coverage % có thể gây hiểu nhầm.**

### 23.2. Accuracy

SBOM có thể parse được nhưng có:
- Version sai do đọc declared thay resolved.
- OS package version mapping sai.
- Fork bị gán upstream identifier.
- Duplicate package đếm sai.
- Library đã bị loại khỏi final image vẫn được liệt kê.
- Shaded code không được nhận ra.
- Supplier metadata không có nguồn xác minh.

Dùng seeded fixtures, independent artifact scans, dependency tree comparisons và spot-checks theo risk. Những sai lệch phải được ghi thành **finding hoặc known limitation**.

### 23.3. Freshness

Mỗi rebuild/redeploy có thể thay component set:
- Base image được rebuild.
- Dependency version thay do dynamic resolver.
- CI toolchain hoặc plugin update.
- JRE/OS patch.
- Artifact được repackaging.
- Feature-specific plugin được tải động.

Vì vậy **SBOM timestamp mới không chứng minh đúng release** nếu target digest không khớp. Hãy theo dõi SBOM **per immutable artifact** và quản lý version của bom document riêng với version ứng dụng.

### 23.4. Authenticity và integrity

- SBOM được tạo bởi approved generator/build context?
- Chữ ký có verify dưới signer trust policy?
- Hash của BOM đúng bản published?
- BOM có ràng buộc tới đúng artifact digest?
- Ai có thể rewrite/delete BOM trong registry?
- Có audit trail cho publish/replace/revoke?
- Có phát hiện BOM bị thiếu hoặc giả mạo?

### 23.5. Reproducibility

Một BOM generated từ cùng source/build config có thể khác về timestamp, serialNumber hoặc ordering dù dependency graph tương đương. Để test reproducibility cần phân biệt:
- **Byte-for-byte equal SBOM** (khó nếu có timestamps/random identifiers).
- **Semantically equivalent inventory/graph**.
- **Reproducible build artifact**.
- **Same dependency resolution**.

Không gộp các yêu cầu trên thành một phép so hash duy nhất mà không kiểm soát inputs/normalization.

### 23.6. Maturity qua từng mức

| Mức minh họa | Đặc điểm | Rủi ro còn lại |
|---|---|---|
| **Ad hoc** | Sinh thủ công khi audit yêu cầu | Stale/missing, không có ownership |
| **Build integrated** | Tạo tại CI và validate schema | Có thể thiếu runtime components |
| **Artifact bound** | Liên kết digest, source, build, signed/attested | Chưa chắc registry và runtime khớp |
| **Deployment reconciled** | Đối chiếu production digests/images | Dynamic components/hidden native libs có thể thiếu |
| **Response integrated** | SBOM→SCA/VEX/owners/findings tự động có review | Matching/reachability/quality limits |
| **Continuous assurance** | Coverage, health, drills, exceptions/retests | Không phải bảo đảm zero vulnerabilities |

Các mức này không phải “chuẩn chứng nhận”; chúng giúp tổ chức đánh giá năng lực theo evidence.

## 24. Inventory storage, distribution và access control

### 24.1. SBOM registry/data model

Một hệ thống lưu SBOM nên cho phép:
- Lookup theo artifact digest, product/version, package identity/version.
- Quản lý nhiều BOM per artifact cho source/build/image/runtime với scope riêng.
- Graph queries về dependencies.
- Truy vết SBOM generator/format/version/time.
- Lưu provenance/signature và validation results.
- Liên kết vulnerability/advisory, VEX assessment, findings/owners.
- Historical lookup cho incident và release cũ.
- Access control/retention theo classification.
- APIs hoặc exports machine-readable.
- Audit changes và exception approvals.

### 24.2. Nhiều SBOM có thể đúng cho một product

Một application có:
- Source BOM vào lúc PR.
- Build BOM tại CI.
- Image BOM từ scanner.
- Runtime bill of materials ở deployed environment.
- Vendor-supplied component BOM cho một binary/SDK.

Nếu các BOM có khác biệt, không nên tự động chọn một là đúng. Hãy làm **reconciliation**:
- Scope nào khác nhau?
- Thành phần xuất hiện thêm do OS/runtime?
- Có declared dependency không được packed?
- Có hidden/shaded/native packages chưa được nhận diện?
- Có cấu hình platform/architecture khác?
- Có scan tool/version differences?
- Có risk gap cần điều tra?

### 24.3. SBOM access và confidentiality

Dù không thường chứa secret, BOM có thể lộ:
- Internal package names và repository paths.
- Technology stack và version fingerprints.
- Topology qua module names.
- Proprietary suppliers và product roadmap details.
- File paths/URLs có credentials nếu generator thiếu sanitization.

Áp dụng classification, least-privilege read, external sharing review, retention, logging access và scrub secrets theo policy. Không hiển thị developer machine paths hoặc tokens trong file cấp cho customer.

### 24.4. Retention và historical response

Khi một thư viện bị thông báo có lỗ hổng sau nhiều tháng, có thể cần biết **release trước đã dùng gì** dù hiện tại đã vá. Retention nên gắn:
- Software support lifecycle.
- Regulatory/contractual obligations khi áp dụng.
- Incident investigation needs.
- Release/archive policy.
- Storage cost và privacy/security exposure.
- Legal hold/exception workflows.

Không dùng một số ngày chung cho mọi sản phẩm; record owner, class, retention and disposal evidence.

## 25. Pipeline CI/CD: tạo, kiểm tra, phát hành và dùng SBOM

### 25.1. Luồng gợi ý

~~~mermaid
flowchart TD
    PR["Source + dependency change"] --> B["Reproducible / controlled build"]
    B --> A["Immutable artifact D"]
    B --> SB["Generate application BOM"]
    A --> IM["Scan final image / artifact"]
    SB --> M["Merge or link inventories with scope"]
    IM --> M
    M --> V{"Schema / accuracy / policy gates"}
    V -->|"Fail / unknown requiring review"| F["Finding + owner + exception process"]
    V -->|"Pass"| AT["Attest / sign: BOM ↔ digest D"]
    AT --> REG["Protected registry"]
    REG --> DP["Deploy digest D"]
    DP --> REC["Reconcile runtime with D and BOM"]
    REC --> SCA["SCA / advisory / VEX"]
    SCA --> R["Risk triage + remediation + monitoring"]
    F --> B
    R --> PR
~~~

### 25.2. Build-time controls

- Pin generator/plugin version và kiểm soát source.
- Dùng approved registries; verify dependency download rules khi phù hợp.
- Tạo SBOM trong build environment có identity xác định.
- Record source revision, build ID, toolchain/JDK/OS/platform.
- Validate schema và required fields.
- Compare resolved dependency graph với expected sample/fixtures.
- Phát hiện BOM generation failure, output empty/invalid, missing files.
- Kiểm tra BOM không chứa secrets/private URLs.
- Store artifact and BOM digests; signer identity/attestation.
- Publish tới protected registry theo immutable refs.

### 25.3. Release/deploy controls

- Xác minh artifact digest có linked SBOM theo policy.
- Verify provenance/signatures nếu scope yêu cầu.
- Check applicable vulnerability/critical findings (theo policy và exception).
- Không cho phép một tag mutable tự thay thế artifact đã scan.
- Đối chiếu image digest sau deploy.
- Quản lý rollback: rollback về image cũ nghĩa cần dùng **SBOM của image cũ**, không dùng BOM mới nhất.
- Theo dõi multi-arch images và các workloads liên quan.
- Có audit log release approvals/exceptions.

### 25.4. Fail behavior

Nếu SBOM generator timeout hoặc schema validator crash, policy gate không được báo **“0 components, 0 vulnerabilities, Pass”**. Phải chuyển sang trạng thái:
- **Failed gate**, hoặc
- **Insufficient evidence/exception pending review**, tùy thẩm quyền và risk.

Cần phân biệt **no finding** (tool chạy, trong scope không có finding) với **tool unavailable** (không có cơ sở kết luận).

### 25.5. CI policy YAML minh họa

~~~yaml
sbom_gate:
  policy_version: "supply-chain-example-2026"
  covered_artifact_classes:
    - "production-container"
    - "release-jar"
  accepted_formats:
    - "CycloneDX-JSON-approved-version"
    - "SPDX-JSON-approved-version"
  require:
    - "artifact_digest_binding"
    - "resolved_component_versions"
    - "dependency_relationships_when_supported"
    - "generator_and_creation_metadata"
    - "schema_validation_pass"
    - "declared_scope_and_exclusions"
  failure_behavior:
    missing_sbom: "block-or-approved-exception"
    invalid_schema: "block"
    generator_failure: "block-or-approved-exception"
    missing_artifact_binding: "block"
  exceptions:
    approval: "authorized-risk-owner"
    fields:
      - "finding_id"
      - "affected_artifacts"
      - "risk_and_compensating_controls"
      - "expiry"
      - "retest_plan"
  evidence:
    - "commit"
    - "build_id"
    - "artifact_digest"
    - "sbom_digest"
    - "tool_version"
    - "validation_report"
    - "release_approval"
~~~

Đây là **policy data mẫu**, không phải YAML có thể nạp trực tiếp vào một CI server hoặc chứng cứ rằng pipeline đã có gate này. Trong triển khai thật, thay placeholder bằng version/profile/criteria cụ thể và test cả failure modes.

## 26. Catalog yêu cầu SBOM có thể kiểm chứng

Các mã **SBOM-REQ-001...SBOM-REQ-030** là ví dụ nội bộ trong bài, không phải mã control của SPDX, CycloneDX hay một standard pháp lý. Tổ chức cần đặt **scope, threshold, owner và risk decision** thật.

| ID | Yêu cầu | Acceptance criteria/evidence |
|---|---|---|
| **SBOM-REQ-001** | Mỗi release artifact thuộc population có SBOM | Release inventory và BOM registry đối chiếu theo digest |
| **SBOM-REQ-002** | Target type/lifecycle/scope được nêu rõ | Source/build/image/runtime không bị đánh đồng |
| **SBOM-REQ-003** | Format/schema version được phê duyệt | Validator thực thi với version/profile rõ |
| **SBOM-REQ-004** | BOM có unique document identity và creation metadata | ID, timestamp, creator/tool/version có provenance |
| **SBOM-REQ-005** | Components có name/version/type phù hợp | Exact resolved versions hoặc explicit unknown |
| **SBOM-REQ-006** | Components có identifiers đủ cho matching | purl/CPE/other refs được chuẩn hóa theo ecosystem |
| **SBOM-REQ-007** | Direct/transitive relationships có độ phủ theo scope | Referential integrity và fixture graph tests |
| **SBOM-REQ-008** | Maven/Gradle scopes và multi-modules được xử lý | Build graph vs BOM comparisons |
| **SBOM-REQ-009** | Vendored/shaded/native components được xem xét | Binary inspection và known exclusions |
| **SBOM-REQ-010** | Runtime OS/JRE packages có coverage theo profile | Final image scanner & independent spot-check |
| **SBOM-REQ-011** | Platform/architecture khác có BOM phù hợp | Per-platform image digest/scan evidence |
| **SBOM-REQ-012** | Generator/toolchain được pin/truy vết | Tool version/config và build logs |
| **SBOM-REQ-013** | BOM liên kết với immutable artifact digest | Digest binding verified; mismatch bị reject |
| **SBOM-REQ-014** | Source/build/artifact/deploy mapping có evidence | Commit→build→BOM→image→runtime reconciliation |
| **SBOM-REQ-015** | BOM authenticity/integrity được kiểm tra theo policy | Signature/attestation/access control tests |
| **SBOM-REQ-016** | BOM registry bảo vệ read/write/delete theo risk | Unauthorized publish/replace/read tests |
| **SBOM-REQ-017** | Không đưa secrets vào BOM | Synthetic secret/URL/path scans |
| **SBOM-REQ-018** | Unknown/missing metadata được hiển thị rõ | Không tự đổi missing thành verified “safe” |
| **SBOM-REQ-019** | SBOM generation failure không thành Pass | Forced tool failure -> failed/exception state |
| **SBOM-REQ-020** | Vulnerability matching có nguồn/version và confidence | SCA reports, advisory snapshot, mapping rationale |
| **SBOM-REQ-021** | Affected/not-affected decision có VEX/risk evidence | Product/version/config/reason/reviewer |
| **SBOM-REQ-022** | Impact query nối deployed artifacts với owners | Advisory response exercise, lookup results |
| **SBOM-REQ-023** | Critical dependencies có remediation/mitigation workflow | Findings, SLA theo risk, retest/deploy evidence |
| **SBOM-REQ-024** | License metadata/gaps được quản trị theo policy | Legal/license review và exceptions |
| **SBOM-REQ-025** | Vendor SBOM/evidence có scope và update cadence | Product/version binding, contract, sample validation |
| **SBOM-REQ-026** | SBOM sharing có authorization/classification | Reader/recipient access tests |
| **SBOM-REQ-027** | Historic SBOM lưu theo release lifecycle | Retention/restore/incident lookup evidence |
| **SBOM-REQ-028** | Coverage/quality metrics có mẫu số và nguồn dữ liệu | Inventory reconciliation và drill results |
| **SBOM-REQ-029** | Pipeline changes dẫn đến SBOM reassessment | Trigger, review records, affected artifacts |
| **SBOM-REQ-030** | Assurance report nêu scope, exclusions và findings | Claim–Argument–Evidence, signed/approved review |

### 26.1. Phân cấp requirements theo criticality

Có thể chọn:
- **Tier A:** Internet-facing services xử lý sensitive learner data: SBOM per deploy digest, image/native coverage, high-quality linkage, vulnerability response, negative gate tests.
- **Tier B:** Internal business services: tương tự với review cadence/monitoring phù hợp.
- **Tier C:** Internal tooling không phân phối: có thể build-time/dependency inventories và risk controls phù hợp thay vì mọi cơ chế ký/publish.

Tier là **mô hình nội bộ minh họa**, không là nhãn pháp lý bắt buộc; risk assessment quyết định chi tiết.

### 26.2. Ví dụ requirement đầy đủ

**SBOM-REQ-013 — Release artifact binding**

- **Risk:** SBOM cũ/nhầm bản khiến tổ chức bỏ sót vulnerable deployments.
- **Population:** tất cả production image digests thuộc services đã inventoried.
- **Trigger:** release, rebuild, rollback và image promotion.
- **Statement:** Chỉ được chấp nhận SBOM có target digest trùng image/artifact được deploy theo định nghĩa attestation đã chọn.
- **Failure behavior:** mismatch/missing binding làm release gate fail hoặc chuyển exception có approval và giới hạn.
- **Acceptance:** positive test đúng digest pass; tamper/swap SBOM giữa A/B bị reject; runtime reconciliation phát hiện image digest khác.
- **Evidence:** registry refs, signed statement, image digest, BOM digest, validation logs, release IDs và reviewer.
- **Owner:** Platform/Release Engineering, với Product Security assurance review.

**SBOM-REQ-019 — Generator failure visibility**

- **Risk:** scanner lỗi trả empty result rồi dashboard báo “0 components/0 vulnerabilities”.
- **Acceptance:** injected timeout, invalid file, missing permissions phải báo Unhealthy/Failed/Unknown; không được mark Pass; có owner/action.
- **Evidence:** simulated failure logs, CI gate decision, exception record và source heartbeat.

## 27. Ma trận kiểm thử SBOM assurance

Mỗi test có test fixture, owner, tool/version, environment và expected/actual riêng. Đây là **catalog tham khảo**, không có test nào đã được chạy trên hệ thống người học.

| Test ID | Chủ đề | Scenario | Expected |
|---|---|---|---|
| **SBOM-T01** | Format | BOM hợp lệ theo accepted schema/version | Parser/validator pass |
| **SBOM-T02** | Format | Sai schema version, malformed JSON | Reject/quarantine, không publish như Pass |
| **SBOM-T03** | Identity | Name/version thiếu hoặc ambiguous | Flag missing/unknown theo policy |
| **SBOM-T04** | Identifier | purl sai type/namespace/encoding | Parser/quality gate phát hiện |
| **SBOM-T05** | Graph | Dependency ref tới component không tồn tại | Validation/quality gate flag |
| **SBOM-T06** | Graph | Direct và transitive fixture có known edges | Inventory matches fixture |
| **SBOM-T07** | Maven | BOM từ sai profile/config | Diff phát hiện disparity |
| **SBOM-T08** | Gradle | Dynamic version resolve khác lock | Resolved version được ghi đúng |
| **SBOM-T09** | Multi-module | Module/edge bị bỏ sót | Aggregate/per-module mapping checks fail |
| **SBOM-T10** | Shading | Component shaded/repackaged | Evidence ghi nhận hoặc explicit unknown |
| **SBOM-T11** | Vendored | JAR copy thủ công | Binary/artifact scan phát hiện hoặc coverage gap |
| **SBOM-T12** | Native | Runtime OS/JRE/native package fixture | Có trong image scope |
| **SBOM-T13** | Multi-arch | amd64 và arm64 khác package | BOM gắn đúng từng image digest |
| **SBOM-T14** | Build binding | BOM đúng source/build/image | Signed/digest linkage pass |
| **SBOM-T15** | Wrong binding | Gắn SBOM của image A cho image B | Reject |
| **SBOM-T16** | Tamper | Sửa một component/version trong SBOM đã ký | Integrity verification fail |
| **SBOM-T17** | Generator identity | Tool/plugin không được phê duyệt | Policy gate reject/require review |
| **SBOM-T18** | Failure | SBOM generation timeout hoặc file rỗng | Fail/Unknown, không 0 findings giả |
| **SBOM-T19** | Secrets | Synthetic token/private URL trong metadata | Không xuất trong BOM distributed sinks |
| **SBOM-T20** | Access | Actor không được phép đọc/download | Deny theo sharing policy |
| **SBOM-T21** | Registry | Actor không được phép replace/delete | Deny, audit |
| **SBOM-T22** | Retention | Historical BOM/attestation retrieval | Đúng artifact và policy window |
| **SBOM-T23** | Vulnerability | Advisory package/version fixture | Affected image/deploys được liệt kê |
| **SBOM-T24** | Mapping | purl/CPE fork/backport ambiguity | Flag uncertainty; không auto-assert affected |
| **SBOM-T25** | VEX | Vendor not-affected claim sai product/config | Không áp nhầm sang release khác |
| **SBOM-T26** | Remediation | Rebuild dependency version và redeploy | New BOM/digest, vulnerability status reassessed |
| **SBOM-T27** | Rollback | Quay lại image cũ | Historical BOM được restore/link đúng |
| **SBOM-T28** | Runtime | Deploy khác image đã scan | Drift/reconciliation alert |
| **SBOM-T29** | Vendor | Supplier BOM thiếu required metadata | Gap/risk follow-up |
| **SBOM-T30** | License | Unknown/conflicting license fixture | Legal/license review trigger |
| **SBOM-T31** | Format conversion | SPDX→CycloneDX (hoặc ngược lại) | Critical fields/relationships preserved or loss documented |
| **SBOM-T32** | Performance | SBOM lớn có graph hàng nghìn node | Bounded processing; timeout/error visibility |
| **SBOM-T33** | Registry outage | Consumer không lấy được SBOM | Unhealthy/exception, cached historical behavior theo policy |
| **SBOM-T34** | SCA outage | Advisory data source lỗi | Unknown/Last-updated rõ, không “No CVE” giả |
| **SBOM-T35** | Evidence | Test report không có target digest | Assessment đánh thiếu provenance |
| **SBOM-T36** | Unknown scope | Binary không xác định được version | Ghi unresolved component/limit |
| **SBOM-T37** | CI bypass | Release không chạy gate required | Block hoặc approval/audit theo emergency policy |
| **SBOM-T38** | Change event | Patch base image không đổi application code | New image BOM và impact reassessment |
| **SBOM-T39** | Incident drill | Giả advisory đối với transitive dependency | Tìm owners/deployed assets trong response window |
| **SBOM-T40** | Missing asset | Image đang chạy không có BOM | Coverage report phát hiện, không 100% giả |

### 27.1. Test generation khác test security response

Nếu một fixture package xuất hiện đúng trong SBOM, điều đó **không chứng minh** SCA query advisory được chính xác, cũng không chứng minh đội incident response biết owner hoặc artifact nào đang chạy. Cần **separate test oracles** cho:
1. Inventory generation.
2. Schema/identity/relationship quality.
3. Artifact binding/provenance.
4. Storage/distribution.
5. SCA/advisory matching.
6. Impact/risk decision.
7. Remediation/retest.
8. Historical lookup/continuous monitoring.

### 27.2. Không chỉ đếm số components

Ví dụ BOM A có 1.000 entries và BOM B có 700 entries. Không thể kết luận BOM A “đầy đủ hơn” nếu:
- A đếm trùng packages/layers.
- B dùng image tối giản.
- A bao gồm test/build components, B chỉ runtime.
- A đếm files thay packages.
- B đã loại legacy code.
- A chứa nhiều unknown/false identity matches.

Chất lượng phải được xem theo **scope, known expected population và correctness**, không chỉ số lượng entries.

### 27.3. Negative tests phải gắn gate behavior

Một release gate có thể validate JSON schema nhưng không reject **BOM khác image digest**. Do đó bắt buộc test cả:
- Valid SBOM cho image đúng.
- Valid SBOM nhưng image sai.
- Valid file nhưng không có dependency data.
- Duplicate bom-ref và missing relationship references.
- BOM signed by wrong/untrusted signer.
- Scanner silently skipped.
- SCA feed bị lỗi nhưng dashboard báo zero findings.
- Critical unknown component được xử lý theo exception policy.

## 28. Assurance evidence: yêu cầu chất lượng và bảo quản

### 28.1. Evidence cho một SBOM claim

| Evidence | Chứng minh gì | Không tự chứng minh |
|---|---|---|
| Source commit | Code revision nguồn | Binary deploy dùng code đó |
| Dependency manifest/lockfile | Intended/resolved declarations | Final image không có hidden packages |
| Build log/toolchain | Build context/generator chạy | Generated inventory đã đủ |
| SBOM file | Danh sách được ghi | Danh sách chính xác trên runtime |
| Schema validation report | File conformant theo validator/spec | Product/component mapping đúng |
| Image/JAR scan | Tool thấy những gì ở artifact | Tool không có false negatives |
| Known fixture comparison | Coverage đối với case test | Coverage cho tất cả real packages |
| Artifact/SBOM digest | Bằng chứng bytes được tham chiếu | Chữ ký/nguồn tốt và contents đúng |
| Signed attestation | Trust policy kiểm tra signer/statement | Không có tampering trước lúc ký |
| Deployment inventory | Workload chạy digest nào | Runtime plugins không đổi |
| SCA/advisory report | Match theo source/time/rules | Vulnerability exploitable |
| VEX/impact analysis | Rationale cho status product | Rationale luôn còn đúng sau thay đổi |
| Finding/remediation/retest | Xử lý risk và fix được xác nhận | Không có risk khác ngoài scope |
| Supplier evidence | Vendor khẳng định trong scope/kỳ | Khẳng định áp dụng đúng cấu hình khách hàng |

### 28.2. Evidence metadata

Một artifact/review record nên có:
- **Claim/control/requirement IDs**, test ID và risk link.
- **System, service, environment, asset criticality**, supplier.
- **Source revision, build ID, builder identity**, toolchain and config.
- **SBOM format/version, generator/version, output digest**.
- **Target artifact/image digest và platform/architecture**.
- **Timestamp/period**, time source, version của vulnerability intelligence.
- **Scope, exclusions và known limitations**.
- **Test method, fixtures, expected/actual, logs**.
- **Signature/provenance verification** và outcome theo trust policy.
- **Assessor/reviewer và access restrictions**.
- **Findings, exceptions, owners, remediation/retest**.
- **Storage/retention/classification**.

### 28.3. Evidence integrity và confidentiality

- Không nhét secrets, credentials hoặc private registry tokens vào metadata BOM.
- Lưu scan reports/attestations trong repository có IAM và retention.
- Không cho người tạo SBOM tự xóa evidence lịch sử nếu policy yêu cầu độc lập.
- Đối với external sharing, dùng bản phát hành được duyệt, có thể tách BOM nội bộ và BOM shareable với giải thích scope.
- Nếu evidence chứa proprietary names/version, đánh giá data classification và hợp đồng.
- Digest/signatures cần được verify khi đọc, không chỉ khi upload.
- Reconcile object version khi storage hỗ trợ mutable URLs/tags.

## 29. Claim–Argument–Evidence cho SBOM

### 29.1. Claim có phạm vi

> Trong kỳ đánh giá xác định, các image phát hành production thuộc danh sách critical Learning Platform services đều có SBOM máy đọc được theo accepted schema và required component profile, được tạo/kiểm tra trên artifact đã build, gắn với immutable image digest và lưu có kiểm soát. Các phép thử profile/negative binding và đối chiếu deployment được thực hiện cho những images trong population, với gaps được ghi nhận riêng.

Đây là **mẫu cách viết claim**; chưa có run result nên chưa được công nhận là evidence production.

### 29.2. Argument

1. Có inventory của production services, release artifacts, images và platform variants.
2. SBOM requirements được định nghĩa theo risk tier và scope.
3. CI sử dụng approved generator từ resolved build và final artifact/image, có tool/version/config.
4. Schema/profile/relationship và completeness tests được thực hiện.
5. SBOM–artifact binding và signer trust verification được kiểm tra.
6. Deployment inventory được reconcile với image/artifact digests.
7. SCA/VEX và impacted asset lookup sử dụng đúng inventories.
8. Unknown/unmapped components, vendor gaps và scanner failures không được tính Pass.
9. Findings được quản lý, sửa, retest và reported limitations.
10. Operating controls theo dõi changes, advisory updates và historical releases.

### 29.3. Evidence

- Asset/service/release/deployment inventory.
- SBOM policy và requirements.
- CI config/build history/source revision.
- SBOM files đúng target digests.
- Generator/validator versions và outputs.
- Artifact/image digest và attestation/signature verification.
- Independent fixture and artifact scan checks.
- Registry access/retention evidence.
- SCA/advisory matching và VEX decisions.
- Incident drill/impact query.
- Findings, exceptions, approvals, remediation/retests.
- Assessor report scope/period/population/exclusions.

### 29.4. Design, implementation và operating effectiveness

| Lớp | Câu hỏi | Evidence phù hợp | Không tự chứng minh |
|---|---|---|---|
| **Design effectiveness** | Policy, coverage và data model có giải quyết supply-chain risks? | Threat model, requirements, workflow design | Pipeline đã chạy đúng |
| **Implementation effectiveness** | CI/generator/validator/registry/binding thực thi theo yêu cầu? | Build/validation results, tests, ACL, signatures | Không có drift/incident trong cả kỳ |
| **Operating effectiveness** | Mỗi release/advisory/change có được xử lý và monitor không? | Release trends, inventory reconciliation, drills, findings | Component ngoài scope cũng an toàn |

Một SBOM có format hợp lệ **không tự chứng minh implementation effectiveness**, và một release được kiểm tra không thể tự đại diện toàn bộ kỳ nếu có nhiều artifact changes.

## 30. Mẫu hồ sơ SBOM assurance YAML

Tất cả giá trị là **placeholder minh họa**, phải thay bằng evidence thật trước khi kết luận.

~~~yaml
evidence_id: "EVD-SBOM-LEARNING-2026-EXAMPLE"
claim_id: "CLAIM-SBOM-DEPLOYMENT-COVERAGE"
module: "SECURITY_SECURITY_ASSURANCE"
scope:
  system: "Learning Platform"
  environment: "production-equivalent-test"
  services:
    - "learning-api"
    - "report-worker"
  platforms:
    - "linux-amd64"
  exclusions:
    - "Legacy standalone PDF processor pending inventory"
artifact:
  service: "learning-api"
  source_commit: "populate-real-commit"
  build_id: "populate-real-build-id"
  image_digest: "populate-real-sha256-digest"
  artifact_platform: "linux-amd64"
sbom:
  spec: "CycloneDX"
  spec_version: "1.6"
  generator: "populate-approved-generator-name-and-version"
  sbom_digest: "populate-real-sha256"
  creation_time: "populate-real-time"
  registry_reference: "populate-access-controlled-artifact-reference"
  validation_status: "PENDING_TEST"
provenance:
  builder_id: "populate-builder-identity"
  attestation_reference: "populate-attestation-location"
  signer_trust_validation: "PENDING_TEST"
controls:
  - "SBOM-REQ-003"
  - "SBOM-REQ-007"
  - "SBOM-REQ-010"
  - "SBOM-REQ-013"
  - "SBOM-REQ-019"
tests:
  - test_id: "SBOM-T06"
    expected: "Known dependency graph detected"
    actual: "PENDING_TEST"
  - test_id: "SBOM-T15"
    expected: "Wrong SBOM/image pairing rejected"
    actual: "PENDING_TEST"
  - test_id: "SBOM-T28"
    expected: "Runtime image digest reconciled"
    actual: "PENDING_TEST"
  - test_id: "SBOM-T34"
    expected: "Advisory source outage reported Unknown"
    actual: "PENDING_TEST"
review:
  assessor: "assign-reviewer"
  assessment_period: "populate-period"
  status: "INSUFFICIENT_EVIDENCE"
  limitations:
    - "Examples are not executed against production"
  next_review_triggers:
    - "Dependency/base image update"
    - "New service, plugin or supplier"
    - "Advisory, incident or SCA finding"
    - "Changes to generator, validator or deployment"
~~~

Lưu ý mã **SBOM-REQ** và **SBOM-T** do bài học đặt để thực hành traceability; chúng không phải API keys hay mã đã đăng ký trong hệ thống thực tế.

## 31. Case study: SBOM cho nền tảng học trực tuyến Java

### 31.1. Bối cảnh

Nền tảng có ba artifact triển khai:
- **learning-api:** Spring-based Java API, PostgreSQL driver, JSON/logging libraries.
- **report-worker:** Java worker, PDF processing/format conversion, queue client, object storage SDK.
- **learning-web:** frontend bundle được phục vụ từ CDN.

Mỗi service có image và runtime scope riêng. Ngoài ra:
- Managed database và cloud IAM/logging.
- Base OS/JRE images.
- Sidecar telemetry agent.
- CI builder và artifact registry.
- Vendor email/analytics API.

Business risk: rò điểm học viên, sửa bài trái quyền, mất availability do dependency vulnerability, dependency confusion hoặc build artifact manipulation.

### 31.2. Inventory ban đầu và những lỗ hổng quan sát

| Thành phần | Nguồn hiện có | SBOM gap cần kiểm tra |
|---|---|---|
| learning-api | pom.xml và resolved Maven tree | Runtime/JRE, shaded/optional packages |
| report-worker | Maven dependencies | Native PDF converter và container OS packages |
| learning-web | package manifest/lockfile | Transitive npm, bundled assets, CDN artifact |
| Base image | Registry image digest | OS packages, architecture, current rebuild |
| Telemetry sidecar | Kubernetes deploy | Sidecar image SBOM và version mapping |
| Cloud DB | Managed service version | Shared responsibility/vendor evidence |
| SaaS vendor | API contract | Opaque supplier inventory, incident notification |
| CI builder | Pipeline YAML | Build-time plugins, runner image and provenance |

### 31.3. Đề xuất release pipeline

1. Commit source/lockfiles trong protected repository.
2. Build mỗi service trong approved CI context; pin toolchain và dependencies theo policy.
3. Generate application/dependency BOM từ resolved build.
4. Build immutable image và generate/image-scan BOM.
5. Reconcile declared vs observed; flag unknown native/shaded components.
6. Validate accepted CycloneDX/SPDX schema/profile.
7. Bind BOM digest và image digest trong trusted attestation.
8. Publish BOM/reports tới protected registry.
9. SCA/advisory/license policy gates, exceptions có approval.
10. Deploy image digest đã được phê duyệt.
11. Reconcile runtime images, sidecars và platform variants.
12. Query impacted assets; maintain supplier/VEX/finding lifecycle.
13. Archive historical BOMs theo release support/retention policy.

### 31.4. Threat scenario A — Shaded parser bị bỏ sót

Một vulnerability advisory ảnh hưởng library parser có trong report-worker nhưng đã được shade/relocate. Dependency scanner của pom.xml không nhận diện source package chính xác.

**Risks:** tool trả “not found”, đội vận hành kết luận worker không affected trong khi code vulnerable có trong binary.

**Controls:**
- Preserve dependency graph/build metadata trước shading.
- Scan final artifact/container và inspect shaded contents theo risk.
- Store source-to-shaded mapping/provenance.
- Allow unknown component record và manual triage.
- Test seeded shaded dependency fixture.
- Record limitations của binary scanner.

**Evidence:** build shading config, resolved dependency graph, artifact digest, manual/binary inspection, matching rationale, VEX/impact decision và retest.

**Assurance conclusion:** không được đánh dấu not affected chỉ vì search SBOM không có tên library gốc nếu độ phủ shaded packages chưa được kiểm chứng.

### 31.5. Threat scenario B — Base image đổi nhưng SBOM cũ

learning-api:prod được rebuild với JRE/OS patches; tag vẫn giữ nguyên, CI vô tình reuse SBOM của image cũ.

**Risks:** record sai component versions, impact queries bỏ sót deployed image.

**Controls:**
- Generate SBOM per immutable digest.
- Gate verify target digest match.
- Store attestation signed theo approved signer policy.
- Verify runtime image digest after deploy.
- Test swap A/B SBOM negative case.
- Log release/rollback mapping.

**Evidence:** image A/B digest, SBOM A/B digest, verification logs, deployment manifest/runtime inventory và review.

### 31.6. Threat scenario C — Advisory về transitive dependency

Một advisory (giả định) công bố library bị ảnh hưởng. learning-api dùng transitive version 2.1.0; report-worker dùng version 2.3.0. Chỉ service A có vulnerable version range, nhưng cần xác minh actual artifact.

**Response:**
1. Query BOM registry theo purl/version.
2. Join with deployed images and owners.
3. Confirm match/version/fork/backport.
4. Check exposed code path/config; create VEX/risk assessment.
5. Contain/mitigate nếu risk yêu cầu.
6. Update dependency; rebuild image digest mới.
7. Regenerate SBOM, SCA/negative tests.
8. Deploy/reconcile all active instances.
9. Close finding chỉ sau retest và remaining image search.
10. Report unverified legacy/export paths as separate gaps.

### 31.7. Threat scenario D — Vendor không cung cấp SBOM

Email service không cấp package-level BOM. Điều này không tự biến vendor thành “unsafe”, nhưng tạo **supply-chain evidence gap**.

Possible response:
- Record vendor functionality/data flows.
- Review supplier security/patch/incident process.
- Negotiate SBOM/VEX/notification scope nếu phù hợp.
- Verify API authentication/data minimization, exit/resilience.
- Approve residual risk bằng đúng authority/time limit.
- Reassess khi vendor releases/incidents/contract changes.

Không tự tạo BOM với những package suy đoán để “đạt chỉ tiêu 100%”.

### 31.8. Kết luận có bằng chứng, giới hạn rõ

**Claim minh họa:**

> Trong phạm vi hai Java services và frontend release đã inventoried, các immutable production artifacts được kiểm tra có linked SBOM theo định dạng chấp nhận; resolved dependencies và final image inventories đã được đối chiếu theo các test cases xác định, và deploy mappings được xác minh tới đúng image digests.

**Limitations minh họa:**

> Native PDF converter có opaque binary dependency, một legacy job chưa có coverage và managed SaaS components không có package-level data. Các trường hợp này được ghi là unknown/gap, không nằm trong coverage claim.

**Next steps:** xác định vendor/legacy scope, bổ sung fixture tests, verify production deployment/rebuild và đo response drill theo advisory mới.

Đây là **mẫu viết kết luận**, không phải đánh giá sản phẩm thật.

## 32. Findings và root-cause remediation

### 32.1. Phân loại

| Loại | Observation | Hành động |
|---|---|---|
| **Control failure** | Build artifact có dependency nhưng BOM chính thức bỏ sót | Fix generator/coverage, regenerate, retest |
| **Binding failure** | Image digest D1 nhưng attach SBOM D2 | Block release, sửa attestation/pipeline |
| **Integrity failure** | BOM bị replace trái policy | Contain, verify history/access, incident review |
| **Evidence gap** | Chưa có runtime/native verification | Investigate, giới hạn claim, risk treatment |
| **Identifier gap** | Component unknown version/purl sai | Enrichment/manual review và quality gate |
| **Stale data** | Release mới dùng BOM cũ | Regenerate theo artifact digest, verify deploy |
| **SCA matching failure** | Fork/backport mapping sai | Triage, improve matching, retest |
| **Vendor gap** | Supplier BOM không đủ scope | Contract/evidence/risk review |
| **License gap** | Package license unknown/conflicting | Legal review/exception, not automatic Pass |
| **Operating failure** | Tool timeout nhưng dashboard báo 0 CVE | Monitor scan health, fix gate/report |

### 32.2. Finding mẫu: dependency bị bỏ sót

**Finding:** report-worker image chứa thư viện PDF parser dạng native binary nhưng SBOM production chỉ có resolved Maven dependencies, không ghi exclusions.

**Risk:** advisory/incident query bỏ sót potentially affected runtime, dẫn đến delayed response.

**Evidence:** image digest, binary inventory, package inspection, BOM, generator config/version, release mapping và source trace.

**Root cause:** design scope “all production components” không được dịch thành multi-source scanning; CI chỉ gọi Maven plugin.

**Remediation:** xác định SBOM profiles per source/image, image scanning, native binary identification/unknown handling, convergence quality gate, documentation, owner và exception policy.

**Retest:** known fixture native package được phát hiện, BOM gắn đúng new image, advisory query tìm đúng owner, deployment mapping verified.

### 32.3. Finding mẫu: SCA tool fail-open

**Finding:** scanner không lấy được vulnerability feed; pipeline chuyển JSON findings thành danh sách rỗng và báo PASS.

**Impact:** mất khả năng xác nhận trạng thái risk của release; không có cơ sở khẳng định “0 vulnerable dependencies”.

**Remediation:** phân biệt SUCCESS_NO_FINDINGS với TOOL_ERROR/UNKNOWN; enforce fail/exception policy, monitoring/feed health, retry/recovery.

**Retest:** simulated advisory source outage, malformed response và stale database; gate/alerts đúng; reviewer nhận được evidence của failure.

### 32.4. Root cause hơn fix cục bộ

Thay một dòng SBOM thủ công có thể chữa triệu chứng, nhưng không bảo đảm build kế tiếp đúng. Cần xử lý:
- Pipeline generator source và version.
- Coverage model và inventory reconciliation.
- Test fixtures.
- Artifact digest binding.
- CI gate.
- Deployment/runtime verification.
- Supplier/exceptions.
- Monitoring and owner.
- Release and historical evidence.

Một finding chỉ nên đóng sau **fix + retest đúng scope + deployed artifact mapping + reviewer confirmation**, không chỉ sau khi file BOM được chỉnh tay.

## 33. Continuous SBOM assurance và thay đổi theo thời gian

### 33.1. SBOM là dữ liệu theo artifact, không là bản chụp repo vĩnh viễn

Khi source commit không thay đổi, SBOM vẫn có thể cần mới nếu:
- Base container image được cập nhật.
- Build environment/JDK/OS khác.
- Dependency resolver lấy phiên bản khác.
- Build plugins/codegen thay.
- Architecture target khác.
- Image layers/artifacts được copy từ nguồn khác.
- Runtime sidecars/agents thay.
- Một plugin động được tải/cập nhật.
- Release được rebuild theo patch/security advisory.
- Vendor software được nâng cấp.

Đối với mỗi **immutable artifact digest**, thông tin BOM nên được quản lý như artifact-linked evidence riêng. Không chỉ đặt “latest-sbom.json” và để release cũ/người tiêu dùng không biết nó ứng với phiên bản nào.

### 33.2. Trigger cần tạo hoặc đánh giá lại

- Dependency manifest hoặc lockfile thay đổi.
- Maven/Gradle plugin, JDK, build profiles hoặc repository config thay đổi.
- Container base image, build stage, OS packages, native lib thay đổi.
- Thêm microservice, worker, frontend, plugin, sidecar.
- Chuyển registry hoặc format/schema/version của BOM.
- Đổi signer/attestation/CI builder identity.
- New advisory/CVE, supplier notice hoặc discovered exploit.
- VEX statement thay do code/config/exposure.
- Audit finding, SBOM completeness gap, mapping error hoặc incident.
- Rebuild/rollback/deploy khác digest.
- Cập nhật license/supplier metadata hoặc điều khoản phân phối.
- Mất quyền truy cập SBOM registry hoặc data feed.
- Chuyển sản phẩm sang region/architecture/tenant khác làm scope đổi.

### 33.3. Lịch trình trong SDLC

| Giai đoạn | Hoạt động | Evidence |
|---|---|---|
| **Architecture/threat model** | Phân loại sản phẩm, dependency boundaries và criticality | Asset inventory, risk scenarios |
| **Development/PR** | Review new dependencies, pin/resolution policies | Manifest diff, owner review |
| **Build** | Sinh BOM from resolved graph/artifacts | Tool version, build ID, BOM |
| **Test/CI** | Validate schema, fixtures, required fields, risk gates | Validation, negative tests |
| **Release** | Bind BOM↔artifact digest và verify signer | Attestation/digests |
| **Deployment** | Reconcile actual image/workload inventory | Runtime scan, deployment digest |
| **Operations** | Re-evaluate advisories, SCA/VEX, supplier changes | Scan history, impact queries |
| **Incident response** | Query blast radius, verify affected builds | Impact record, containment |
| **Periodic assessment** | Review coverage, exceptions, metrics, provenance | Assurance report |
| **Retirement** | Revoke distribution access/retire release theo policy | Archive and retention evidence |

### 33.4. Continuous monitoring không đồng nghĩa scan vô hạn

Có thể có:
- Per-build SBOM generation.
- Per-deploy digest reconciliation.
- Scheduled/advisory-triggered SCA.
- Supplier feed updates.
- Runtime inventory drift checks.
- Periodic manual sampling.
- Incident-driven deep binary inspection.
- Quarterly/periodic control reviews theo risk.

Tần suất thực do tổ chức quyết định dựa trên **criticality, change rate, threat landscape và nguồn lực**, không lấy tần suất cao làm bằng chứng đầy đủ nếu source/coverage sai.

### 33.5. Monitoring phải kiểm tra chính monitoring

Nếu SBOM generator, registry hoặc advisory feed không hoạt động:
- Dashboard phải thể hiện **Unhealthy/Unknown**, không 0 findings.
- Có heartbeat/liveness/last-successful-scan timestamps.
- Có owner và escalation route.
- Missing releases/images được phát hiện qua registry/deployment reconciliation.
- Parse/validation errors có quarantine/triage.
- Unmapped/unknown packages có backlog và timeout.
- Scan output gắn đúng artifact/source, không dùng cache sai build.
- Retest khi recovery và khi tool/version đổi.

## 34. RACI và accountability của chương trình SBOM

### 34.1. Các vai trò cần phối hợp

| Hoạt động | Product/Asset Owner | Development | Platform/DevOps | AppSec/Assurance | Risk/Vendor/Legal |
|---|---|---|---|---|---|
| Inventory scope và criticality | A/R | C | C | C | I |
| Dependency choices và updates | C | A/R | C | C | I |
| SBOM generation trong build | C | R | A/R | C | I |
| Artifact/image scanning và runtime reconciliation | C | R | A/R | R/C | I |
| Format/profile/quality gate policy | C | R | R | A/R | C |
| SBOM signing/attestation và registry rights | I | C | A/R | C | I |
| SCA vulnerability matching/triage | C | R | C | A/R | I |
| Product impact/VEX decision | A/R về product | R kỹ thuật | C | R security review | C |
| Supplier BOM/VEX request | C | C | I | C | A/R Vendor Owner |
| Open source license review | C | R input | I | C | A/R Legal/OSPO |
| Finding remediation and retest | A về roadmap | R | R | A/R verification | C |
| Residual risk acceptance | C | C | C | C | A/R Risk Owner |
| Incident response and scope | A/R product | R technical | R infrastructure | R security | C |
| Periodic assurance and reporting | C | R evidence | R evidence | A/R | C |

Đây là **RACI minh họa**, không thay quyết định phân quyền thực tế. Cần ghi rõ một người chịu trách nhiệm cuối cho từng control/scope; người được audit không nên là reviewer độc lập duy nhất nếu policy yêu cầu segregation of duties.

### 34.2. Product Security Incident Response Team

Một chương trình có nhiều sản phẩm có thể dùng **PSIRT hoặc đội phụ trách vulnerability response** để:
- Nhận disclosure/advisory.
- Truy vấn sản phẩm/artifacts bị ảnh hưởng.
- Điều phối owners, vendor contacts và fix.
- Ban hành VEX/product notices khi phù hợp.
- Theo dõi mitigation, deadlines và release availability.
- Thu phản hồi từ khách hàng.
- Bảo đảm evidence và incident review.

SBOM hỗ trợ PSIRT giảm thời gian định vị thành phần; nó **không tự thay communication, patch QA hay risk decision**.

### 34.3. Who owns unknown components?

Nếu một binary có phiên bản/nguồn không xác định:
- App/Platform Owner sở hữu asset/artifact nơi binary xuất hiện.
- Security/Vulnerability Team hỗ trợ identification và exposure analysis.
- Supplier/Vendor Owner liên hệ bên cung cấp nếu cần.
- Risk Owner quyết định residual risk và exception.
- Release owner đảm bảo không tự bypass gate.

“Không có owner” chính là một finding governance, không phải lý do bỏ qua.

## 35. Metrics và dashboard phục vụ quản trị

### 35.1. Metrics có thể hành động

| Metric | Mục đích | Giới hạn |
|---|---|---|
| **% production artifacts có linked SBOM** | Coverage theo release | Cần population/digest đúng |
| **% deployed image digests match approved BOM** | Build-to-runtime assurance | Không bao phủ dynamic plugins nếu không scan |
| **% required components có exact version/identifier** | Identity quality | Version “unknown” không phải 0 |
| **% known seeded fixtures detected** | Generator effectiveness | Fixture không đại diện mọi code type |
| **Số unknown/unmapped components** | Technical debt/uncertainty | Số ít có thể do scanner không chạy |
| **% BOMs validate schema/profile** | Format conformance | Không chứng minh inventory đầy đủ |
| **% BOMs có verified provenance/signature** | Integrity/authenticity controls | Không chứng minh input đúng |
| **% critical releases có image+build BOM reconciliation** | Cross-source coverage | Cần exception/known gap log |
| **% high-risk advisories được impact queried** | Response readiness | Query không đồng nghĩa risk triage xong |
| **Median time to identify affected deployments** | Incident scoping speed | Cần test trên real/populated inventory |
| **Median time from advisory to affected decision** | Vulnerability triage | Phụ thuộc risk/availability of data |
| **% VEX decisions có supporting evidence** | Confidence in status | Rationale có thể stale sau code change |
| **Số high-risk vulnerable deployments chưa fix** | Residual exposure | SCA matching/versions có uncertainty |
| **% vendor products có usable BOM/evidence** | Third-party assurance | SaaS có khả năng chia sẻ khác |
| **% SBOM pipeline runs Healthy/valid** | Tooling health | Parser pass không = complete |
| **% exceptions quá hạn** | Risk governance | Exception không làm failure thành Pass |
| **% remediation đóng sau retest và digest verification** | Quality of closure | Ticket Done chưa đủ |
| **% retired releases có historic SBOM retrievable** | Incident/history support | Retention access phải đúng policy |

### 35.2. Dashboard phải phân biệt trạng thái

- **Covered and verified:** có BOM đúng artifact, quality checks và evidence trong scope.
- **Covered with limitations:** có BOM nhưng một số native/unknown/OS/runtime exclusions.
- **Missing:** artifact không có BOM theo requirement.
- **Invalid:** file không conformant hoặc binding sai.
- **Unhealthy:** generator/validator/registry/SCA feed lỗi.
- **Not assessed:** chưa kiểm tra.
- **Exception approved:** noncompliance có approval, hạn và controls bù trừ.
- **Affected / Under investigation / Not affected / Fixed:** vulnerability impact status riêng, không lẫn với chất lượng SBOM.

Một chỉ số “100% SBOM coverage” không nói lên gì nếu BOMs chỉ sinh cho các repos được biết đến trong khi shadow services/old images vẫn chạy.

### 35.3. Denominators và dữ liệu nguồn

Mỗi tỷ lệ cần:
- Population source (CMDB, deployment inventory, artifact registry).
- Time window.
- Artifact/release identifiers và platform variants.
- Exclusions/unknowns.
- Actual numerator/denominator.
- Data freshness và last successful collection.
- Reviewer hoặc automation owner.
- Sự khác nhau giữa **artifact coverage** và **component coverage**.

## 36. Những sai lầm thường gặp

**“Có pom.xml nghĩa có SBOM.”** Manifest chỉ là một nguồn; resolved, packaged và runtime components có thể khác.

**“Maven BOM và SBOM là một.”** Maven BOM thường quản lý dependency versions; SBOM là danh mục thành phần có cấu trúc phục vụ transparency/assurance.

**“Một dependency tree đủ cho container.”** Nó thường bỏ JRE, OS packages, native tools và runtime sidecars.

**“SBOM là danh sách CVE.”** SBOM là inventory; advisory/SCA/VEX là các nguồn/analysis bổ sung.

**“Không có CVE trong BOM nghĩa an toàn.”** Không có vulnerability entry không chứng minh không có vulnerabilities.

**“Có CVE match chắc chắn exploit được.”** Cần exact version, fork/backport, exposure, configuration và impact analysis.

**“Không thấy package trong scan nghĩa không tồn tại.”** Tool có blind spots với shaded/native/embedded/packed components.

**“Nhiều components hơn là BOM tốt hơn.”** Có thể do duplicates, scopes khác nhau hoặc false identifications.

**“SBOM mới nhất mô tả mọi deployment.”** Bản rollback/region/image khác cần BOM gắn đúng digest.

**“Image tag là định danh bất biến.”** Tag có thể thay; dùng image digest và release mapping.

**“BOM được ký là đầy đủ và đúng.”** Chữ ký hỗ trợ source/integrity theo trust; input/generator có thể thiếu hoặc sai.

**“Hash chứng minh không có mã độc.”** Hash chỉ cho phép so bytes theo reference, không đánh giá semantics hoặc provenance.

**“Format pass nghĩa inventory chính xác.”** Schema validation chỉ kiểm tra cấu trúc/constraints.

**“SPDX và CycloneDX chuyển đổi không mất dữ liệu.”** Một số fields/relationships có thể không map hoàn hảo; phải test.

**“SPDX 2.x JSON áp dụng y hệt SPDX 3.x.”** Khác version/schema, cần kiểm chứng.

**“Lưu SBOM ở một thư mục là đủ để phản ứng.”** Cần searchable identity, artifact binding, owners và deploy mappings.

**“Scanner 0 findings khi tool timeout vẫn là Pass.”** Không; scanner unavailable phải là gap/error.

**“VEX not_affected từ vendor áp cho mọi version/config.”** Trạng thái có scope, justification và thời hạn/reassessment.

**“CVSS tự quyết định mức ưu tiên.”** Cần exposure, impact, threat intelligence, controls và uncertainty.

**“Có SBOM nghĩa đạt SLSA.”** Build provenance/supply-chain practice khác inventory.

**“SaaS không có SBOM nên phải tự suy package list.”** Ghi evidence gap và risk-based supplier controls, không bịa.

**“LicenseDeclared = NOASSERTION nghĩa không có license.”** Không; chưa có assertion, cần review.

**“Ký SBOM là chia sẻ công khai an toàn.”** BOM có thể chứa proprietary metadata/internal paths, cần classification và access policy.

**“Một PR fix dependency là finding đã đóng.”** Cần rebuild, BOM mới, deploy đúng digest và retest.

**“Risk acceptance biến missing SBOM thành Pass.”** Không; exception là quyết định riêng, không thay kết quả kỹ thuật.

**“SBOM phải giống nhau byte-for-byte mọi lần.”** Timestamps/IDs có thể khác; test semantic inventory và artifact reproducibility là các vấn đề riêng.

## 37. Bài tập thực hành

### Bài tập A — Đọc dependency graph

Một API có:
- library A v1 trực tiếp;
- library B v2 được A kéo vào;
- library C v3 được B kéo vào;
- library D v4 trực tiếp;
- OS package E trong image.

Vẽ graph với direct/transitive/image relationships và nêu loại SBOM/source nào có thể phát hiện mỗi thành phần. Thiết kế các checks để phát hiện component C bị bỏ sót.

### Bài tập B — Maven/Gradle và resolved version

Một Gradle build khai báo version range cho thư viện JSON; developer tạo SBOM trong local environment và CI build artifact 2 ngày sau khi registry có version mới.

Xác định nguyên nhân lệch BOM, cách pin/resolve/version lock, cần lưu những metadata nào và vì sao source manifest alone không đủ.

### Bài tập C — Shaded JAR

Một library parser được shade thành namespace nội bộ. SCA từ final image không tìm upstream purl, nhưng build dependency tree có.

Viết kế hoạch đối chiếu source→shading→binary, ghi uncertainty và test fixture. Không sử dụng “not found” làm VEX not_affected khi chưa có evidence.

### Bài tập D — Image digest mismatch

CI tạo SBOM cho image A, nhưng deployment vẫn dùng tag latest trỏ tới image B. Làm thế nào để gate phát hiện? Viết positive/negative tests, attestation subject/digest binding và runtime reconciliation plan.

### Bài tập E — SPDX và CycloneDX

Từ hai JSON examples trong bài, lập bảng mapping document metadata, component IDs, versions và relationships. Xác định fields chưa có, thử chuyển đổi theo tool/version được duyệt và ghi thông tin bị mất. Không giả định mọi property có semantic tương đương.

### Bài tập F — Advisory mới

Advisory giả định ảnh hưởng một transitive dependency. Product có API và worker dùng các phiên bản khác nhau, một bản rollback vẫn chạy trên region khác.

Thiết kế response: package match, deploy query, owner, risk/exposure, VEX, mitigation, rebuild/deploy/retest, lịch sử và cách báo uncertainty.

### Bài tập G — VEX not affected

Vendor tuyên bố not affected cho library có advisory vì vulnerable function disabled. Bạn cần xác minh:
- Product/build/config có đúng scope?
- Có runtime flag hoặc plugin thay đổi không?
- Data processing paths nào có thể kích hoạt behavior?
- Bằng chứng code/config/test có đủ không?
- Khi nào phải reassess và ai phê duyệt?

Viết một VEX-like assessment record có rationale, limitations và owner.

### Bài tập H — SBOM tool failure

SBOM generator bị timeout nhưng pipeline tiếp tục; SCA nhận file rỗng, dashboard báo “0 vulnerable packages”. Phân loại risk/control failures, định nghĩa gate, alert và tests để scanner unavailable không bị tính Pass.

### Bài tập I — Supplier SaaS

Một nhà cung cấp analytics không cung cấp package-level SBOM và đang xử lý dữ liệu học viên. Thiết kế supplier assurance plan: contract, security practices, VEX/advisory notification, data minimization, exit/resilience, owner, risk acceptance và limitations.

### Bài tập J — License review

SBOM có một package với dual license, một package license unknown, một modified vendored library và một component từ closed source SDK.

Nhóm hãy xây license review queue, phân biệt declared/concluded, kiểm tra obligations theo distribution/usage và nêu lý do SBOM không thay legal analysis.

### Bài tập K — Historical incident

Sáu tháng sau release, một advisory mới xuất hiện. Một số image tag đã bị overwrite và SBOM registry chỉ lưu “latest”. Hãy phân tích vì sao không thể chứng minh scope quá khứ và thiết kế retention/immutable digest/archival controls.

### Bài tập L — Metrics audit

Báo cáo tuyên bố “100% codebases có SBOM” nhưng chỉ 40/50 production images nằm trong asset inventory, 15 image còn thiếu native scan và 6 BOM không có digest binding. Viết lại metrics theo population, nêu gaps, confidence và remediation priorities.

### Bài tập M — Supply-chain threat model

Vẽ threat boundaries từ source, dependency registries, CI runner, SBOM generator, signer, registry, deployment đến SCA/consumer. Dùng STRIDE hoặc cách phân loại risk tương đương để đề xuất controls và test evidence.

### Bài tập N — Root-cause finding

Một released report-worker chứa JAR copy thủ công ngoài Maven dependencies; SBOM scanner bỏ sót. Viết finding có observation/evidence/risk, root cause, containment, remediation, retest và residual risk decision.

### Bài tập O — Thiết kế assurance program 90 ngày

Lập kế hoạch:
1. Inventory critical services/artifacts và xác định owner.
2. Chọn accepted SBOM formats/profiles và required fields.
3. Tích hợp generation với Maven/Gradle/CI.
4. Thêm image/runtime/native checks theo risk.
5. Gắn BOM với artifact digest và provenance.
6. Thiết lập registry access và retention.
7. Tích hợp SCA/advisory/VEX và supplier processes.
8. Thử forced generation failure/mismatched digest.
9. Tổ chức mock zero-day drill theo component purl.
10. Xuất evidence quality/coverage metrics và report limitations.

Yêu cầu bài làm có risk prioritization, measurable acceptance criteria, owners, CI/release/runtime mapping, negative tests và plan khi công cụ không hoạt động.

### Bài tập P — Case study tổng hợp

Learning Platform có:
- 60 deployed images trong fleet;
- 52 image có SBOM, nhưng chỉ 43 có verified digest mapping;
- 8 image thiếu hoàn toàn;
- 7 image chứa binary native unknown version;
- một SCA rule đánh dấu vulnerability “not affected” cho mọi service chỉ dựa trên tên package;
- một vendor SaaS không cung cấp inventory và không có incident notification SLA;
- base image được rebuild nhưng release tag không đổi.

Hãy:
1. Phân loại **coverage, quality, binding, vulnerability assessment và supplier gaps**.
2. Viết claim có scope/period/limitations, không nói “100% secure”.
3. Đề xuất remediation và owners cho từng gap.
4. Chọn 5 negative tests quan trọng nhất và nêu expected results.
5. Thiết kế query tìm affected deployments khi advisory mới xuất hiện.
6. Viết VEX assessment có trạng thái under_investigation khi chưa đủ chứng cứ.
7. Nêu bằng chứng cần trước khi close findings.
8. Đề xuất dashboard có Unhealthy/Unknown và retention đối với historical BOM.

## 38. Checklist SBOM assurance

Checklist này giúp đánh giá chương trình; **đánh dấu đủ ô không tự chứng minh sản phẩm không có vulnerability**.

- [ ] Scope, sản phẩm, releases, criticality, data flows và supply-chain risks được xác định.
- [ ] Có inventory các services/images/artifacts/deployments và owners.
- [ ] Phân biệt source/build/artifact/image/runtime/product SBOM.
- [ ] Chọn accepted SPDX/CycloneDX format/version/profile theo consumers.
- [ ] BOM có document metadata, generator identity/time và target artifact.
- [ ] Direct/transitive dependencies/relationships phù hợp scope.
- [ ] Exact resolved versions và identifiers/purl được dùng khi có thể.
- [ ] BOM có treatment rõ cho package unknown/ambiguous.
- [ ] Maven/Gradle multi-module/profile/lockfile resolution được kiểm tra.
- [ ] Shaded, vendored, native, JDK/JRE, OS/image packages được xem theo scope.
- [ ] Multi-arch images/sidecars và dynamic plugins được inventoried hoặc ghi exclusions.
- [ ] Có seeded fixtures/independent scans cho completeness/accuracy.
- [ ] BOM được gắn với immutable artifact/image digest.
- [ ] Source commit, build ID, CI builder và deployment mapping có evidence.
- [ ] Authenticity/signature/attestation được verify theo trust policy khi áp dụng.
- [ ] Registry cho SBOM có access control, audit, integrity và retention.
- [ ] Không công khai secrets/private URLs/internal paths ngoài policy.
- [ ] BOM format schema validation có công cụ/version và results.
- [ ] Dependency graph references unique/hợp lệ và schema changes được test.
- [ ] Generator/plugin/toolchain được pin, review và monitor.
- [ ] Tool timeout/failure/empty output không thành “0 components, Pass”.
- [ ] Release gate có positive/negative tests cho mismatch và tampering.
- [ ] Runtime deployed digests được reconcile với BOM/release registry.
- [ ] Historical BOMs tìm lại được cho incident/rollback theo retention policy.
- [ ] SBOM được kết hợp SCA/advisory intelligence có thời gian/version rõ.
- [ ] Matching ambiguity, forks/backports, purl/CPE khác biệt được quản lý.
- [ ] VEX/product impact statuses có rationale và scope/version/config.
- [ ] Không tự coi missing package trong SBOM là “not affected”.
- [ ] Affected assets có owners, remediation/mitigation, retest và deadline theo risk.
- [ ] License/obligations và vendor/SaaS evidence được quản trị đúng scope.
- [ ] External SBOM distribution được phân quyền và kiểm tra integrity.
- [ ] Coverage/quality metrics có numerator, denominator, period và exclusions.
- [ ] Có security assurance Claim–Argument–Evidence với limits rõ.
- [ ] Phân biệt design, implementation và operating effectiveness.
- [ ] Findings/control failures khác evidence gaps và exceptions.
- [ ] Risk acceptance không tự sửa Pass/Fail hoặc bỏ yêu cầu bắt buộc.
- [ ] Dependency, builder, artifact, supplier và advisories thay đổi sẽ trigger reassessment.
- [ ] Đã thực hiện response drill tìm affected deployments từ một advisory giả định.

## 39. Ghi nhớ

1. **SBOM là danh mục máy đọc được mô tả thành phần phần mềm và quan hệ phụ thuộc trong một phạm vi cụ thể**, không phải danh sách CVE hoặc chứng nhận an toàn.
2. **Dependency manifest/lockfile, SCA, VEX, provenance và SBOM có vai trò khác nhau**; nên kết hợp, không đánh đồng.
3. Chất lượng của BOM phụ thuộc **identity, scope, graph relationships, completeness, accuracy, freshness và traceability**.
4. Một Java/Spring application còn có JAR shaded, native libraries, JDK/JRE, OS/base image, plugins và sidecars; chỉ scan Maven tree thường chưa đủ cho runtime.
5. **SPDX/CycloneDX là các format hỗ trợ interoperability**; phải chọn version/profile và validate, không áp một ví dụ schema cho mọi phiên bản.
6. **Immutable artifact/image digest binding** quan trọng hơn tag/version label; cần nối source→build→SBOM→release→deployment.
7. **Signature/attestation bảo vệ một số khía cạnh integrity/provenance**, không bảo đảm dữ liệu inventory đầu vào chính xác hay không có mã độc.
8. **SBOM + SCA/advisory giúp truy vấn ảnh hưởng của lỗ hổng mới**, nhưng exploitable/not-affected cần VEX/risk/technical evidence trong scope product/config.
9. **Scanner unavailable, unknown component hoặc vendor gap là uncertainty/gap**, không phải “no vulnerability”.
10. **License metadata trong SBOM không tự kết luận nghĩa vụ pháp lý**; cần review theo sử dụng/phân phối và điều kiện license.
11. **Security assurance là claim có bằng chứng và giới hạn**: yêu cầu → generator/validator → artifact binding → impact query → finding/remediation/retest → monitoring.
12. **Continuous SBOM assurance** phải đáp ứng mỗi thay đổi của code, dependency, build, image, runtime, supplier và threat intelligence xuyên suốt phát triển/vận hành.










