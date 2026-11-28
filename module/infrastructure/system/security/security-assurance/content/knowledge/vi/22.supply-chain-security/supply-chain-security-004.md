# Dependency pinning: Cố định phụ thuộc để kiểm soát chuỗi cung ứng phần mềm

## 1. Dependency pinning là gì?

**Dependency pinning** là thực hành **ràng buộc phiên bản hoặc định danh nội dung của một dependency vào giá trị đã xác định**, thay vì để quá trình build tự chọn một phiên bản mới theo điều kiện thay đổi theo thời gian.

Dependency có thể là:

- Thư viện Java, JavaScript, Python, Go hoặc ngôn ngữ khác.
- Dependency bắc cầu (transitive dependency) do thư viện khác kéo vào.
- Plugin build, compiler extension, code generator, annotation processor.
- Base image của container và các package hệ điều hành được cài trong image.
- GitHub Actions, reusable CI workflow hoặc công cụ được tải trong pipeline.
- SDK, CLI, binary, artifact hoặc mã nguồn lấy từ repository bên ngoài.
- Toolchain hoặc runtime ảnh hưởng kết quả build.

Ví dụ, cấu hình yêu cầu một thư viện ở phiên bản **1.2.3** cụ thể hơn cấu hình “chấp nhận mọi bản 1.x”. Tương tự, tham chiếu container bằng **content digest** xác định nội dung rõ hơn tham chiếu bằng tag có thể thay đổi.

Mục tiêu quan trọng nhất của pinning là **kiểm soát sự thay đổi không được xét duyệt trong dependency graph**, làm cho build có thể tái hiện và giải thích được các thành phần đã sử dụng.

Trong module **SECURITY_SECURITY_ASSURANCE**, pinning là một security control cần được đánh giá bằng chứng:

**Threat/risk → Security requirement → Pinning and resolution policy → Build verification → Artifact evidence → Finding → Remediation/retest.**

> **Pinning không có nghĩa dependency đã an toàn.** Một phiên bản đã cố định vẫn có thể chứa CVE, code độc hại hoặc một dependency không đáng tin. Pinning giúp xác định *chính xác ta đang dùng gì*, còn việc xác minh integrity, provenance, vulnerability, maintainer risk và cập nhật là các control bổ sung.

### 1.1. Vì sao pinning quan trọng?

Một build hôm nay có thể khác build ngày mai dù source code không đổi nếu:

- Khai báo version range cho phép lấy bản mới.
- Một transitive dependency thay đổi theo version resolution.
- Image tag trỏ sang một image digest mới.
- CI action dùng branch/tag có thể được cập nhật.
- Script build tải “latest” binary từ Internet.
- Package mirror hoặc repository trả metadata/artifact khác.
- Plugin build bị thay đổi dù application dependency giữ nguyên.

Những thay đổi này có thể tạo lỗi tương thích, lỗ hổng, mã độc, hành vi bảo mật khác, hoặc khiến investigation khó xác định thời điểm dependency đã thay đổi.

**Dependency pinning** giúp bảo vệ các thuộc tính:

1. **Integrity of dependency selection:** build không tự chuyển sang phiên bản ngoài quyết định.
2. **Change control:** sự thay đổi dependency được ghi nhận và review.
3. **Reproducibility of dependency graph:** có thể tái dựng cùng graph trong điều kiện đã xác định.
4. **Incident traceability:** biết artifact nào chứa phiên bản bị ảnh hưởng.
5. **Verification repeatability:** kết quả SCA, test và audit gắn được với thành phần cụ thể.
6. **Blast-radius analysis:** xác định service, pipeline và image sử dụng một dependency rủi ro.

Pinning **không tự đảm bảo reproducible build bit-for-bit**, vì compiler version, timestamp, environment, locale, external download, plugin behavior hoặc các yếu tố không xác định khác vẫn có thể làm artifact khác nhau.

## 2. Thuật ngữ cốt lõi

| Thuật ngữ | Định nghĩa | Ví dụ |
| --- | --- | --- |
| **Direct dependency** | Dependency được dự án khai báo trực tiếp | Orders API khai báo thư viện JSON |
| **Transitive dependency** | Dependency được kéo theo bởi dependency khác | Thư viện JSON kéo một thư viện utility |
| **Dependency graph** | Toàn bộ package/version/relationship mà resolver chọn | Web starter → HTTP library → codec |
| **Version range** | Biểu thức cho phép một nhóm phiên bản | Lớn hơn/bằng 1.2, nhỏ hơn 2.0 |
| **Dynamic version** | Resolver tự chọn phiên bản tại thời điểm build | 1.+, latest.release, latest |
| **Exact version pin** | Chỉ rõ một version identifier | 1.2.3 |
| **Lockfile** | Bản ghi kết quả resolution cụ thể, gồm các dependency gián tiếp trong scope | package-lock.json, gradle.lockfile |
| **Integrity hash/checksum** | Giá trị để kiểm tra bytes artifact khi tải | SHA-256 được xác minh từ nguồn đáng tin |
| **Content digest** | Định danh nội dung theo hash, thường dùng cho image | Image reference theo sha256 digest |
| **Provenance** | Bằng chứng nguồn và quá trình tạo artifact | Builder, source, build invocation |
| **SBOM** | Danh mục thành phần phần mềm trong artifact/product | Component, version, relationship |
| **Vulnerability management** | Phát hiện, đánh giá và xử lý lỗi đã biết | SCA/advisory/reachability/patch |
| **Artifact immutability** | Không thay đổi bytes của một artifact với một định danh được cam kết | Content-addressable artifact |
| **Vendoring** | Đưa bản sao phụ thuộc vào source hoặc artifact nội bộ được quản lý | Vendored library directory |

### 2.1. “Version” không giống “content”

Tên package + version giúp chỉ rõ phiên bản được yêu cầu, nhưng **không tự chứng minh bytes tải về bất biến hoặc đến từ nguồn đáng tin**.

Có thể có tình huống:

- Repository cho phép thay artifact cùng version.
- Mirror bị cấu hình sai hoặc bị compromise.
- Một registry dùng tag có thể đổi.
- Dependency được resolve từ một nguồn khác.
- Build script download file trực tiếp không đi qua dependency lock.

Vì vậy phải phân biệt hai câu:

- **Chúng ta yêu cầu phiên bản nào?** → version pinning.
- **Chúng ta thực sự lấy đúng bytes và nguồn đã phê duyệt?** → integrity/provenance verification.

### 2.2. “Reproducible” không giống “repeatable”

Một build có thể lặp lại được trong cùng máy nhưng không tái dựng được ở nơi khác do cache local hoặc toolchain khác.

Các mức kết luận:

- **Version stable:** direct version không đổi.
- **Graph stable:** direct và transitive versions được khóa theo resolver/scope.
- **Artifact integrity verified:** bytes dependency khớp giá trị đã được tin cậy phê duyệt.
- **Environment controlled:** toolchain, base image, plugin và external inputs được quản lý.
- **Reproducible output:** artifact đầu ra tương đương theo tiêu chí đã định, có thể là bit-for-bit nếu hệ thống đủ điều kiện.

Không dùng một lockfile để tự kết luận đã đạt mọi mức trên.

## 3. Threat modeling cho dependency resolution

### 3.1. Threat scenarios

| ID | Threat scenario | Tác động | Control cần xem |
| --- | --- | --- | --- |
| **DP-01** | Direct dependency dùng dynamic version | Build lấy bản chưa review | Exact version/lock và gate |
| **DP-02** | Transitive dependency đổi dù direct giữ nguyên | Binary đổi mà code không đổi | Dependency lock/graph review |
| **DP-03** | Package registry phát hành bản độc hại | Mã độc vào build/runtime | Version governance, provenance, integrity, review |
| **DP-04** | Package mirror trả artifact khác | Artifact substitution | Verified checksum/signature, trusted repositories |
| **DP-05** | Internal package bị dependency confusion | Tải package cùng tên từ public registry | Repository routing/namespace và source verification |
| **DP-06** | Developer tải package gần giống tên thật | Typosquatting | Allowlist, review publisher/name, source controls |
| **DP-07** | Container dùng mutable tag | Deployment thay base image ngoài review | Pin image digest và policy |
| **DP-08** | CI action dùng mutable branch/tag | Pipeline chạy mã mới không được review | Pin commit SHA, workflow review |
| **DP-09** | Version bị pin lâu không cập nhật | Tiếp tục dùng dependency có lỗ hổng | SCA, patch cadence, exception |
| **DP-10** | Build tải binary từ script bên ngoài | Input không có trong lock graph | Inventory external fetch, digest/signature |
| **DP-11** | Lockfile bị thay trái phép cùng source change | Resolver chấp nhận dependency không mong đợi | Review diff, approval, CI lock consistency |
| **DP-12** | CI runner cache chứa artifact không đúng | Kết quả lệch hoặc rủi ro substitution | Cache controls, integrity verification, clean build |
| **DP-13** | Build plugin/annotation processor bị compromise | Chạy mã trong build, lấy secret | Build-time identity/secret isolation, pin/integrity |
| **DP-14** | Package có install script gây side effect | Rò CI token hoặc sửa build | Script governance, runner isolation, source review |
| **DP-15** | Artifact deploy khác artifact đã test | Evidence security test không đúng production | Digest identity, provenance, deployment verification |

### 3.2. Attacker capability cần mô tả

Một risk assessment tốt không chỉ nói “supply-chain attack”. Cần ghi:

- **Attacker kiểm soát gì?** Package mới, registry, mirror, build script, Git repository hay CI runner?
- **Precondition:** Có quyền publish, thay lockfile, tạo package public trùng tên hay compromise maintainer?
- **Trust boundary:** Developer → package registry, CI → artifact mirror, registry → deploy.
- **Impact:** Remote code trong build, rò secret, dữ liệu bị sửa, artifact bị tráo, outage?
- **Time window:** Build nào đã nhận dependency mới, artifact nào đã deploy?
- **Existing controls:** Review, policy, checksum, signature, SBOM, network isolation?
- **Residual risk:** Pinning có ngăn được threat không hay chỉ giúp truy vết?

### 3.3. Pinning giải quyết những gì và không giải quyết những gì?

| Threat | Pinning giúp gì? | Control bổ sung cần thiết |
| --- | --- | --- |
| Resolver tự chọn bản mới | Chặn drift nếu scope được khóa đúng | CI consistency checks |
| Registry có bản mới độc hại | Không tự cập nhật sang bản đó | Risk-based updates, package/source review |
| Phiên bản hiện tại đã bị compromise | Không chữa được | Incident response, revoke/remove, provenance review |
| Registry thay bytes cho cùng version | Exact version có thể chưa đủ | Integrity digest/signature, trusted artifact source |
| CI action tag bị retarget | SHA pin hạn chế tag drift | Commit review, action trust, permissions |
| Dependency có CVE đã biết | Pin giữ ổn định nhưng vẫn vulnerable | SCA, remediation, patch SLA |
| Dependency confusion | Pin tên/version chưa đủ xác nhận nguồn | Repository routing, publisher/namespace policies |
| Malicious postinstall | Pin khóa version đã chọn nhưng script vẫn chạy | Runner isolation, permission policy và review |
| Toolchain thay đổi | Library lock không kiểm soát | Toolchain pinning và build environment controls |

**Pinning là một thành phần trong defense-in-depth**, không phải chứng nhận an toàn của package.

## 4. Security objectives có thể kiểm chứng

Một chương trình dependency pinning nên có mục tiêu như:

- **DP-OBJ-01:** Các dependency được tải trong build/release thuộc phạm vi đều có nguồn và version/artifact identity xác định.
- **DP-OBJ-02:** Resolution của direct và transitive dependencies không drift ngoài change đã được review.
- **DP-OBJ-03:** Các artifact quan trọng được kiểm tra integrity với dữ liệu tin cậy.
- **DP-OBJ-04:** Container images và CI actions dùng tham chiếu đủ ổn định theo baseline.
- **DP-OBJ-05:** Việc thêm hoặc nâng version dependency phải qua review theo mức rủi ro.
- **DP-OBJ-06:** Dependency có vulnerability, maintainer compromise hoặc nguồn không tin cậy được phát hiện và xử lý.
- **DP-OBJ-07:** Artifact được phát hành có thể truy vết tới source, dependency graph, build và security results.
- **DP-OBJ-08:** Lockfile hoặc pin update trái phép/ngoài phạm vi phải bị phát hiện.
- **DP-OBJ-09:** Exception được phê duyệt, có thời hạn và compensating controls.
- **DP-OBJ-10:** Có thể cung cấp evidence về cả thiết kế, triển khai và vận hành pinning.

Mục tiêu phải được chuyển thành security requirements, acceptance criteria và test cases, không dừng ở khẩu hiệu “luôn dùng version cố định”.

### 4.1. Security requirements mẫu

**DP-REQ-01 — Khóa dependency graph**

> Với các bản build phát hành thuộc scope, dependency resolver phải sử dụng phiên bản của direct và transitive packages được xác định bởi manifest và lock state đã review; nếu resolution đòi thay lock state ngoài change được phê duyệt, CI không được báo PASS.

**DP-REQ-02 — Artifact integrity**

> Các artifact thuộc danh mục bắt buộc phải được xác minh bằng checksum/signature hoặc cơ chế integrity được phê duyệt trước khi sử dụng; mismatch phải dừng build hoặc chuyển trạng thái lỗi, không tự fallback qua nguồn không tin cậy.

**DP-REQ-03 — Trusted dependency source**

> Tên package thuộc namespace nội bộ chỉ được resolve từ repository/registry được phép theo policy, không bị ghi đè bằng package trùng tên ở nguồn public.

**DP-REQ-04 — Controlled updates**

> Mọi thay đổi dependency pin/lock ở release branch phải có change record liên kết package, old/new version, rationale, security assessment, test results và reviewer theo risk tier.

**DP-REQ-05 — Vulnerability refresh**

> Các pinned dependencies phải được kiểm tra định kỳ và khi có advisory/security event; những finding thuộc risk tier đã định phải có remediation hoặc time-bound risk decision theo policy.

**DP-REQ-06 — Artifact traceability**

> Mỗi released/deployed artifact phải có định danh bất biến hoặc tương đương, cùng record liên kết commit, build, dependency inventory và security evidence đã sử dụng để phê duyệt release.

Các từ “định kỳ”, “risk tier” và “cơ chế được phê duyệt” cần được ràng buộc bằng policy/version của tổ chức trước khi triển khai; bài học không tự đặt SLA phổ quát.

## 5. Cơ chế pinning: version, lockfile, digest, vendoring

### 5.1. Exact direct version

Ví dụ khai báo **version 1.2.3** thay vì “1.x”.

**Ưu điểm:** đơn giản, reviewer dễ thấy sự thay đổi direct dependency.

**Giới hạn:** một direct dependency có thể kéo transitive packages; các phiên bản này vẫn thay đổi tùy resolver, metadata hoặc configuration nếu không được khóa.

### 5.2. Lockfile cho resolved dependency graph

Một lockfile thường ghi các version đã được chọn khi resolver chạy.

**Ưu điểm:**

- Ổn định cả transitive versions trong scope.
- Review sự thay đổi graph qua source control.
- CI có thể kiểm tra manifest và lock state nhất quán.
- Dễ liên kết build và SBOM.

**Giới hạn:**

- Lockfile thường không kiểm soát dependency ngoài hệ thống quản lý package tương ứng.
- Một số ecosystem có resolver đặc thù; semantics của lock khác nhau.
- Lock có thể không bao gồm build plugins, toolchain hoặc container base image.
- Lock không mặc nhiên xác minh publisher hoặc nội dung artifact.
- Lock được commit nhưng pipeline không dùng chế độ frozen/locked vẫn có thể drift.

### 5.3. Content-addressable pinning

Một OCI image reference theo **sha256 digest** xác định content descriptor; một GitHub Action tham chiếu **full commit SHA** xác định Git object commit trong hệ thống Git thích hợp.

**Ưu điểm:** tránh rủi ro mutable tag/branch chuyển sang nội dung khác.

**Giới hạn:**

- Digest/SHA không chứng minh nội dung đó là đáng tin hoặc không chứa lỗ hổng.
- Digest sai được copy vào policy vẫn trỏ tới artifact sai.
- Registry có thể xóa content dẫn đến không còn tải được, dù digest không đổi.
- Cần quản lý các biến thể multi-platform manifest, source/provenance và update process.

### 5.4. Vendoring và internal artifact repository

Vendoring có thể giảm phụ thuộc tải mới từ Internet trong mỗi build, còn internal registry có thể áp policy và cache artifact.

Nhưng chúng có nhược điểm:

- Tăng công việc cập nhật bản vá và license.
- Tạo bản sao các component trong nhiều repo.
- Có thể giữ mã độc/vulnerability lâu nếu không kiểm kê.
- Cần xác minh nguồn, checksum/provenance và quyền thay artifact nội bộ.
- Artifact mirror không tự là nguồn tin cậy chỉ vì nằm trong mạng nội bộ.

### 5.5. Chiến lược kết hợp

Một chính sách thường cần nhiều lớp:

| Layer | Ví dụ control |
| --- | --- |
| **Direct dependency** | Exact version hoặc constraints được phê duyệt |
| **Transitive dependency** | Lock state/pinned resolution |
| **Artifact bytes** | Hash/signature/verification metadata |
| **Registry/source** | Allowlist, namespace routing, restricted publish |
| **Build toolchain** | Pin wrapper, JDK/runtime, build plugins |
| **Container** | Digest pin, image provenance, scanning |
| **CI pipeline** | Commit SHA pin cho actions, minimal permissions |
| **Release artifact** | Digest + SBOM/provenance + deployment verification |
| **Operations** | SCA monitoring, patch updates, exception expiry |

## 6. Semantic versioning và các version ranges

### 6.1. Semantic Versioning (SemVer)

Khi thư viện tuân thủ SemVer, version thường có dạng MAJOR.MINOR.PATCH. Tuy vậy, **nhãn SemVer chỉ là cam kết của publisher**, không đảm bảo mọi thay đổi thực tế tương thích hoặc an toàn.

Các biểu thức cho phép resolver chọn version mới tạo ra trade-off giữa cập nhật tự động và stability.

Ví dụ:

| Version expression | Ý nghĩa khái quát | Rủi ro |
| --- | --- | --- |
| **1.2.3** | Chọn một version cụ thể | Stable version selection nhưng vẫn cần integrity |
| **1.2.+** | Cho phép bản mới trong nhóm theo resolver | Tự chọn bản mới chưa review |
| **latest.release** | Chọn bản phát hành mới nhất theo resolver | Rất dễ drift theo thời gian |
| **^1.2.3** | Trong hệ sinh thái npm, cho phép khoảng tương thích theo quy tắc caret | Có thể cập nhật nếu lockfile thay đổi |
| **~1.2.3** | Trong hệ sinh thái npm, cho phép patch-level tương ứng | Vẫn có biến động khi resolve lại |
| **Tag “latest”** | Tag có thể được publisher di chuyển | Không định danh nội dung bất biến |
| **Git branch “main”** | Con trỏ tới commit hiện tại | Build chạy code thay đổi theo thời gian |

Ý nghĩa chính xác của range phụ thuộc **package manager và phiên bản**, không nên suy diễn cú pháp từ npm sang Maven hay Gradle.

### 6.2. Ranges có luôn bị cấm?

Không nhất thiết. Một thư viện có thể chủ đích cho phép range ở development hoặc ở consumer dependency metadata. Nhưng nếu mục tiêu của **release artifact** là xác định dependency graph, CI phải có cơ chế lock và review selection.

Có thể chấp nhận:

- Manifest dùng range theo quy ước ecosystem.
- Lockfile xác định version được cài.
- CI dùng lệnh không tự cập nhật lockfile.
- Update chỉ tạo PR có review và test.

Điểm đánh giá là **sự ổn định thực tế của resolved graph trong pipeline**, không chỉ nhìn một ký tự trên manifest.

## 7. Direct và transitive dependencies: vì sao phải khóa cả graph?

Giả sử Orders API dùng thư viện order-client 2.4.0. Thư viện này phụ thuộc:

- HTTP transport library 4.1.x.
- JSON parser từ BOM của một framework.
- Utility library theo version constraint.
- TLS adapter theo platform.

Nếu direct version 2.4.0 cố định nhưng resolver còn chọn transitive version theo metadata/range, build mới có thể sử dụng một JSON parser khác.

### 7.1. Ví dụ graph

~~~mermaid
flowchart TD
    A["Orders API"] --> B["order-client 2.4.0"]
    A --> C["Spring / Framework BOM"]
    B --> D["HTTP library selected version"]
    B --> E["Utility library selected version"]
    C --> F["JSON library selected version"]
    D --> G["TLS adapter selected version"]
    H["Manifest + Constraints"] --> I["Dependency resolver"]
    J["Lock state"] --> I
    I --> K["Resolved dependency graph"]
    K --> L["SBOM / Artifact evidence"]
~~~

Các version trong sơ đồ minh họa, không có nghĩa package thực tồn tại hoặc đã được đánh giá.

### 7.2. Những đường bắc cầu ít được chú ý

- Build plugins kéo libraries riêng.
- Annotation processors chạy trong build.
- Test runtime dependencies khác compile runtime.
- Integration-test tooling có dependency riêng.
- Frontend build pipeline có devDependencies và postinstall scripts.
- Gradle/Maven wrapper hoặc npm runtime khác.
- Code generator được tải qua task hoặc script.
- Container OS packages nằm ngoài Java/npm lockfiles.
- Serverless layers và platform-provided libraries.
- Native libraries được tải theo OS/architecture.

Vì vậy, dependency inventory phải gắn với **build phases, configurations, platforms và deployed artifacts**.

## 8. Gradle: Pinning và dependency locking cho Java

### 8.1. Exact version trong build.gradle.kts

Ví dụ Kotlin DSL minh họa:

~~~kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

dependencies {
    // Toa do va version vi du minh hoa; khong phai goi da duoc xac nhan.
    implementation("org.example:orders-validation:1.2.3")
    testImplementation("org.example:test-support:4.5.6")
}
~~~

Ưu điểm: reviewer thấy direct versions. Tuy nhiên, code trên **không khóa đầy đủ transitive graph** hoặc tự xác minh checksum.

Nếu dùng version catalog (ví dụ libs.versions.toml), cần nhớ version catalog thường giúp **tập trung quản lý declaration**, không phải bản lock toàn bộ transitive dependencies.

### 8.2. Dependency locking

Gradle hỗ trợ dependency locking, cho phép ghi lại phiên bản đã resolve cho các configurations thuộc phạm vi được bật locking.

Ví dụ DSL minh họa:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Một workflow điển hình:

1. Xác định configurations thuộc scope release và test.
2. Bật dependency locking theo quy định dự án.
3. Generate/update lock state qua tác vụ Gradle với chế độ write locks được hỗ trợ.
4. Commit lock state lên source control cùng manifest.
5. Build CI chạy ở chế độ tôn trọng lock state; không âm thầm rewrite lock.
6. Thay dependency qua PR, review diff và chạy test.
7. Retest và phát hành artifact gắn digest/commit.

Lệnh Gradle thường dùng trong workflow tạo lock state (phải điều chỉnh cho project/configurations):

~~~bash
./gradlew dependencies --write-locks
~~~

**Lưu ý thực hành:** command và cơ chế lock state thay đổi tùy phiên bản Gradle, plugin và configurations thực sự được resolve. Bật lockAllConfigurations không tự chứng minh mọi dependency đã được ghi vào lockfile; phải kiểm tra **graph thực sự resolved** của các configurations dùng cho release. Không dùng lệnh trên để chạy ở project hiện tại khi không thuộc phạm vi công việc.

### 8.3. Dependency verification khác dependency locking

Gradle có cơ chế **dependency verification** để kiểm tra integrity của các dependencies bằng metadata/checksum/signature theo cấu hình tương ứng.

| Control | Câu hỏi |
| --- | --- |
| Dependency locking | Version của package nào được chọn? |
| Dependency verification | Artifact được lấy có khớp identity/integrity metadata được tin cậy không? |
| Repository policy | Artifact chỉ được lấy từ nguồn nào? |
| SCA | Version/artifact đã chọn có advisory và rủi ro nào? |
| Build provenance | Ai build artifact, từ source và inputs nào? |

Cần bảo vệ verification metadata khỏi sửa trái phép và **không tự tin** vào checksum được lấy lần đầu từ cùng nguồn có thể bị compromise mà chưa review.

### 8.4. Gradle BOM, platform và constraints

BOM/platform/constraints hỗ trợ điều phối phiên bản, nhưng không đồng nghĩa mọi artifact đều được pin và verified.

Ví dụ:

- BOM chọn family version nhất quán.
- Constraint giới hạn một dependency quan trọng.
- Lock state ghi kết quả resolution cho configurations.
- Verification metadata kiểm tra bytes/trust.

Nếu một dependency bị nâng phiên bản do constraint conflict, phải review **effective resolved version**, không chỉ manifest.

### 8.5. Build plugins và Gradle Wrapper

Đừng chỉ pin application dependencies. Xem:

- Plugin versions khai báo trong plugin management hoặc plugin block.
- Plugin resolution repositories.
- Gradle Wrapper distribution và integrity verification.
- JDK/toolchain version và container dùng để build.
- Artifact downloads từ custom tasks.
- Credential permissions trong build runner.

Một plugin build bị compromise có thể thực thi code trước khi application tests chạy và có thể thấy secrets của CI. Hạn chế build runner permissions và secret exposure là control quan trọng ngoài pinning.

## 9. Maven: Phiên bản, BOM và effective dependency tree

### 9.1. Maven dependency management

Maven có cơ chế version management và BOM imports để điều phối direct/transitive versions theo model dependency resolution.

Ví dụ minh họa:

~~~xml
<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>org.example</groupId>
  <artifactId>orders-api</artifactId>
  <version>1.0.0</version>

  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>org.example</groupId>
        <artifactId>shared-policy</artifactId>
        <version>2.3.4</version>
      </dependency>
    </dependencies>
  </dependencyManagement>

  <dependencies>
    <dependency>
      <groupId>org.example</groupId>
      <artifactId>shared-policy</artifactId>
    </dependency>
  </dependencies>
</project>
~~~

Tọa độ là hư cấu nhằm minh họa. Maven BOM có thể giúp nhất quán các versions giữa modules, nhưng reviewer phải xem **effective POM và resolved dependency tree**.

### 9.2. Maven không có lockfile chung như npm theo mặc định

Trong Maven truyền thống, version khai báo trực tiếp/BOM/managed versions có thể giúp graph ổn định, nhưng không nên gọi dependencyManagement là một lockfile hoàn chỉnh giống package-lock.json.

Với các hệ thống cần pinning nghiêm ngặt:

- Tránh dynamic ranges, snapshots/mutable sources trong release nếu policy không cho.
- Quản lý dependency versions, BOM và transitive overrides có rationale.
- Pin Maven plugin versions và Maven Wrapper/toolchain.
- Kiểm tra effective dependency tree trong CI.
- Xem lựa chọn extension/tooling nếu cần khóa graph cụ thể.
- Xác minh repository/source và artifact integrity theo baseline.

### 9.3. Plugin và snapshot risk

Một project không khai báo rõ Maven plugin versions có thể có hành vi build thay đổi theo plugin defaults hoặc parent/toolchain. Dependency SNAPSHOT cũng có semantics cập nhật khác release cố định.

Reviewer cần hỏi:

- Những build plugins nào chạy code?
- Parent/BOM versions có được kiểm soát?
- Snapshot có xuất hiện trong release chain không?
- Metadata hoặc artifact có thể bị thay đổi cùng version?
- Artifact repository có cấm overwrite và có audit không?
- Build có phụ thuộc local Maven cache để PASS không?

## 10. npm và JavaScript: package-lock.json, npm ci

### 10.1. Manifest vs lockfile

Trong npm:

- **package.json** biểu diễn khai báo direct dependencies và version ranges.
- **package-lock.json** ghi resolved dependency tree và metadata cần cho installation theo npm version tương ứng.
- **npm ci** dành cho cài đặt dựa trên lockfile, yêu cầu manifest và lock state nhất quán; không có mục đích cập nhật lockfile như một lần npm install thông thường.

Ví dụ file package.json đơn giản:

~~~json
{
  "name": "orders-web-demo",
  "private": true,
  "dependencies": {
    "example-ui-package": "1.2.3"
  },
  "scripts": {
    "test": "node ./scripts/test.js"
  }
}
~~~

Đây là package minh họa, không yêu cầu package đó tồn tại. Trên project thật, cần dùng package name và version đã được phê duyệt.

### 10.2. Workflow có kiểm soát

1. Developer đề xuất thêm/nâng package qua PR.
2. package.json và package-lock.json thay đổi trong cùng PR.
3. Review names, publishers, diff, scripts, licenses và SCA.
4. CI cài với lockfile ở chế độ frozen:

~~~bash
npm ci
~~~

5. Chạy tests/security scans.
6. Liên kết artifact và SBOM tới commit/lockfile.
7. Release gate chặn khi lockfile thiếu/mismatch hoặc checks không hoàn tất.

**npm ci không chứng minh mọi package an toàn**. Nó giúp dùng dependency graph được lock. Lockfile có integrity metadata cho các packages theo format tương ứng; cần review trust của metadata, registry resolution và lifecycle scripts.

### 10.3. “Save exact” và ranges

Khi có yêu cầu exact direct versions, npm có tùy chọn cài và lưu exact version thay vì version range. Nhưng **lockfile mới là một cơ chế quan trọng để cố định transitive tree** trong CI; không đánh giá chỉ qua việc package.json chứa caret.

Không lấy package-lock.json từ PR của nguồn không tin cậy rồi tự động cấp CI runner quyền đọc production secrets.

### 10.4. Lifecycle scripts và devDependencies

Build tooling thường chạy package scripts. Cần xem:

- postinstall/prepare/prepublish scripts.
- package có native binary download không.
- Build và test dependencies có chạy trong CI không.
- Runner network egress và secret scope.
- Trust của lockfile diff và registry.
- Lockfile format, npm version và platform-specific dependencies.

Không nên bật một cấu hình tắt scripts trên production một cách máy móc nếu làm hỏng build; cần đánh giá theo risk và kiểm tra từng workflow.

### 10.5. Yarn và pnpm

Yarn/pnpm cũng có lockfiles và chế độ cài không cập nhật lock tương ứng, nhưng **tên lệnh, semantics và format phụ thuộc phiên bản**.

Principle chung:

- Commit lockfile.
- Pin package manager/runtime được dùng trong CI.
- Dùng frozen/immutable lock mode hỗ trợ bởi phiên bản đang chạy.
- Review transitive changes.
- Không bỏ qua integrity/security gates khi update.

Không sao chép command npm ci sang ecosystem khác rồi mặc định tương đương.

## 11. Python và Go: những semantics khác

### 11.1. Python requirements và hashes

Một file requirements với exact versions là bước cơ bản, nhưng có thể cần **hash-checking mode** để khóa bytes distributions theo platform và wheel/source distributions được cho phép.

Lệnh minh họa:

~~~bash
python -m pip install --require-hashes -r requirements.txt
~~~

Để dùng được, danh sách requirements phải pin và cung cấp hashes thích hợp cho packages được resolve theo quy tắc của phiên bản pip. Các dependency transitive cũng cần được bao phủ đúng. Không chỉ thêm flag vào requirements thiếu hashes rồi coi CI đã an toàn.

Cần cân nhắc:

- pip, Python runtime version và target platform.
- Wheel vs sdist và build-time dependencies.
- Private index, index order, dependency confusion.
- Build isolation và native extensions.
- Cơ chế lock của tooling đang dùng.

Một sdist có thể chạy build code, nên pin/hash chưa thay runner isolation hoặc provenance review.

### 11.2. Go modules

Trong Go, go.mod mô tả module requirements và go.sum ghi checksums dùng để xác minh module contents theo semantics của Go tooling. Resolver của Go có quy tắc lựa chọn phiên bản riêng, không giống npm/Gradle.

Cần xem:

- go.mod và go.sum có được commit và review không?
- go.sum có đủ entries cần cho build trong scope?
- Module source và checksum database/proxy policy như thế nào?
- Private module exemptions được cấu hình đúng?
- replace/exclude directives có tạo nguồn khác hay bỏ qua kiểm tra?
- Go toolchain version và cross-platform build đã được quản lý?

go.sum **không phải tuyên bố package an toàn**, và không nên gọi nó là lockfile giống một lockfile npm.

### 11.3. Các ecosystem khác

Rust, .NET, PHP và nhiều ecosystem có lock mechanisms khác nhau. Ví dụ Cargo.lock hoặc packages.lock.json có thể hỗ trợ locked resolution theo phạm vi phù hợp. Trước khi áp baseline, cần xác minh:

- Package manager/version.
- Lockfile có bao gồm transitive packages không.
- Application hay library publication semantics.
- Cách CI bật locked/frozen restore.
- Integrity và source verification có sẵn không.
- Platform/optional dependency graph có thay đổi không.

Không áp một chính sách cứng chỉ dựa trên tên file lock.

## 12. Container image pinning

### 12.1. Mutable tag

Ví dụ:

~~~dockerfile
FROM registry.example.org/team/runtime:latest
~~~

Tag **latest** có thể được retarget sang image khác. Ngay cả tag trông như một version cụ thể cũng có thể bị cập nhật trong một số registry/workflow.

### 12.2. Digest pinning

Ý tưởng tốt hơn là ghi identity theo digest, ví dụ cú pháp biểu diễn:

~~~text
FROM registry.example.org/team/runtime@sha256:<verified-content-digest>
~~~

Chuỗi trong dấu ngoặc nhọn là placeholder, **không phải Dockerfile có thể chạy trực tiếp**. Trong cấu hình thật phải điền digest đã được xác minh theo công cụ/registry.

Với multi-platform image, cần hiểu digest đang trỏ tới **image index/manifest list** hay manifest của một platform cụ thể. Cần gắn platform, base image lineage và resulting digest trong evidence.

### 12.3. Pin digest có đủ không?

Không. Image cố định vẫn có thể:

- Chứa OS packages có CVE.
- Chứa credential hoặc secret trong layers.
- Được build từ base image không đáng tin.
- Có provenance không xác minh.
- Không còn phù hợp bản vá hiện tại.
- Bị deploy sai platform hoặc có runtime config rủi ro.

Cần image scanning, provenance/signature verification theo policy, runtime hardening, regular refresh và deployment identity verification.

### 12.4. OS package managers và image build

Một Dockerfile cố định base image digest nhưng chạy lệnh “upgrade toàn bộ package từ repository hiện tại” vẫn có thể tạo kết quả khác qua thời gian.

Xem các bước:

- apt/apk/dnf downloads theo repository snapshot hay live index.
- Package version constraints và repository pinning.
- Toolchain downloaded qua shell scripts.
- Layer cache ảnh hưởng resolution thế nào.
- Base digest và output image digest có được ghi rõ?
- SBOM được tạo từ artifact cuối hay chỉ manifest đầu vào?

Reproducibility ở mức image cần kiểm soát **mọi đầu vào có thể thay đổi**, không chỉ FROM.

## 13. Pinning CI/CD actions, workflows và tools

### 13.1. CI action theo tag vs commit SHA

Một workflow có thể tham chiếu action theo branch/tag:

~~~yaml
# Minh hoa nguy co: tag co the duoc di chuyen.
steps:
  - uses: vendor/example-action@v1
~~~

Cách cố định định danh Git commit:

~~~yaml
steps:
  - uses: vendor/example-action@<full-verified-commit-sha>
~~~

Đây là **placeholder minh họa**, không phải workflow dùng được ngay. Tùy CI provider, cần tham khảo semantics hiện hành và trust policies của tổ chức.

Pin full commit SHA giúp ngăn một tag bị chuyển sang commit khác mà CI không review. Nhưng vẫn phải:

- Kiểm tra action repository, publisher và commit.
- Giới hạn workflow/job permissions.
- Không truyền production secret cho untrusted PR.
- Kiểm tra nested actions, container images và external downloads.
- Theo dõi advisory, patch và update action.
- Có chính sách approve change SHA.

### 13.2. Reusable workflows và remote scripts

Những đường còn drift:

- Reusable workflow theo branch.
- Remote installer script tải trực tiếp.
- CLI lấy latest release từ API.
- Git submodule theo branch không cố định.
- Plugin hoặc Docker image được action tải runtime.
- Third-party hosted task không xác định version.

Một kiểm kê chỉ tìm dependencies trong package manager sẽ bỏ qua các nguồn này. Build input inventory cần liệt kê cả **implicit/deferred downloads**.

### 13.3. Quyền CI runner quan trọng ngang pinning

Một pinned action vẫn thực thi code; nếu CI job có write token, signing key hoặc production cloud credential, rủi ro lớn khi action bị compromise ở pinned version hoặc khi workflow cho phép input không tin cậy.

Security controls:

- Minimal job permissions.
- Token scope/audience/TTL phù hợp.
- Separation giữa build/test và deploy/sign.
- Protected environment approvals.
- Runner isolation và network egress.
- Artifact upload/download integrity.
- Audit của workflow changes và manual overrides.

## 14. Dependency confusion, typosquatting và source trust

### 14.1. Dependency confusion

Giả sử project dùng package nội bộ tên orders-core. Nếu resolver có thể lấy một package public cùng tên hoặc ưu tiên nguồn không mong muốn, attacker có thể publish gói giả.

**Exact version pinning theo name/version chưa đủ** nếu không kiểm soát registry identity và resolution order.

Cần:

- Namespace/scope rõ cho internal packages.
- Chỉ cho phép trusted internal repository với những namespace đó.
- Không dựa vào version public cao hơn để quyết định nguồn.
- Repository content filtering/routing.
- Review package URL, publisher và provenance.
- Negative test không cho internal coordinates resolve từ public source.

### 14.2. Typosquatting

Developer vô tình thêm package có tên gần giống package thật. Lockfile có thể **khóa chính xác package sai** nên vẫn tạo cảm giác ổn định.

Kiểm tra:

- Tên package/namespace.
- Maintainer và publisher identity.
- Source repository và release provenance.
- Thay đổi install scripts và dependencies.
- Lịch sử/độ tin cậy phù hợp risk.
- Review của người khác trước khi merge.

### 14.3. Private registry không tự an toàn

Internal artifact repository cần:

- Write/publish permissions tối thiểu.
- Chính sách bất biến artifact hoặc thay đổi có audit.
- Phê duyệt/cách ly cho packages được mirror từ public.
- Retention và disaster recovery.
- Artifact integrity/signature verification.
- Phân tách môi trường, đặc biệt publishing và promotion.
- Monitor unexpected version replacement/deletion.

## 15. Integrity, signature và provenance

### 15.1. Checksum xác minh điều gì?

Hash như SHA-256 dùng để so sánh bytes nhận với giá trị đã biết.

Nếu hash mong đợi được lấy từ một **nguồn đáng tin** và được bảo vệ khỏi sửa, mismatch là bằng chứng artifact khác. Nhưng hash công bố cùng artifact trên một server đã bị compromise có thể đều bị attacker thay.

Vì vậy:

- Nguồn hash/metadata có trust model rõ.
- Verification xảy ra trước khi dùng artifact.
- Mismatch phải fail hoặc được điều tra, không auto-approve.
- Hash change cùng version cần được review như sự kiện bất thường nếu policy yêu cầu immutable artifact.
- Ghi evidence về expected/observed digest mà không ghi dữ liệu bí mật.

### 15.2. Signature xác minh điều gì?

Digital signature có thể cho biết artifact hoặc metadata được ký bởi holder của key tương ứng và không bị thay đổi sau khi ký, **nếu trust/key policy phù hợp**.

Nó không chứng minh:

- Người ký không bị compromise.
- Source code không có vulnerability.
- Build không có malicious step.
- Ký đúng artifact đã chạy production.
- Các identity/keys được quản lý tốt.

Review cần gắn signer identity, key/certificate trust, scope, revocation, transparency/attestation khi áp dụng và verification policy.

### 15.3. Provenance và build attestations

Provenance mô tả một artifact được tạo từ **source, builder, environment/process và inputs** nào. Đây là evidence quan trọng để kết nối:

- Source commit.
- Dependency manifests/lockfiles.
- Builder/workflow identity.
- Build steps và toolchain.
- Output artifact digest.
- Security scan/test results.

Không nên dùng provenance claim tự khai từ pipeline không tin cậy để tự chứng nhận. Cần đánh giá trust của builder và integrity của attestations.

### 15.4. SLSA và các framework tham khảo

Những mô hình như SLSA có thể giúp xác định maturity goals cho provenance/build integrity. Nhưng phải **map yêu cầu áp dụng và phiên bản chuẩn cụ thể** vào hệ thống. Việc ghi “SLSA compliant” mà không có scope, cấp độ và bằng chứng tương ứng là không đủ.

## 16. Pinning và SBOM/SCA/VEX

### 16.1. SBOM giải quyết câu hỏi nào?

**Software Bill of Materials** là danh sách các components/relationships của phần mềm theo format được hỗ trợ. Nó giúp biết package nào có mặt, version nào và quan hệ phụ thuộc nào.

Một lockfile có thể hỗ trợ tạo SBOM nhưng **không đồng nhất với SBOM của artifact cuối**. Một artifact có thể còn:

- Native libraries.
- OS packages.
- Bundled binaries.
- Shaded Java dependencies.
- Frontend assets.
- Runtime plugins hoặc platform libraries.

Cần tạo hoặc xác minh SBOM từ build/artifact theo mục tiêu.

### 16.2. SCA giúp gì?

SCA có thể đối chiếu dependency versions với advisories và metadata. Nhưng phải phân biệt:

1. Component/version present.
2. Advisory match.
3. Vulnerable function/reachability.
4. Exploit conditions thực tế.
5. Business impact và risk decision.
6. Upgrade/remediation và retest.

Một CVE có severity cao không luôn exploitable trong service, nhưng “not reachable” cũng cần bằng chứng phù hợp và không nên biến thành exception vô thời hạn.

### 16.3. VEX và applicability

Vulnerability Exploitability eXchange hoặc tài liệu tương đương có thể ghi một component vulnerability có ảnh hưởng/không ảnh hưởng đến product theo lý do cụ thể.

Không dùng một tuyên bố VEX chưa có căn cứ để xóa finding. Cần source, version, product scope, justification, reviewer, expiration/trigger và evidence.

### 16.4. Pinned không có nghĩa patched

Vì pinning giúp giữ phiên bản, một package có CVE có thể bị giữ lại lâu. Cần **chính sách refresh/upgrade** dựa trên risk tier và advisory.

Mục tiêu là **controlled change**, không phải **no change forever**.

## 17. Quy trình update dependency có kiểm soát

### 17.1. Quy trình chuẩn

1. **Inventory:** biết package nào, version nào, direct/transitive, source và consumer.
2. **Signal:** advisory, CVE, vendor notice, patch release, EOL hoặc roadmap.
3. **Assessment:** severity, exploit conditions, exposed path, business impact.
4. **Plan:** xác định old/new version, alternatives, compatibility, rollout.
5. **Resolve:** cập nhật manifest/lock và provenance/integrity metadata theo quy trình.
6. **Review:** xem graph diff, publisher, install scripts, license và dependencies mới.
7. **Test:** functional, security, regression, performance khi cần.
8. **Promote:** xây artifact, gắn SBOM/provenance, deploy theo release policy.
9. **Verify:** artifact digest và runtime behavior tương ứng.
10. **Monitor:** errors, incidents, advisories và khả năng rollback.
11. **Record:** change ID, approval, evidence, exceptions và affected products.

### 17.2. Dependency update PR cần có gì?

- Package name, ecosystem, old/new versions.
- Direct hay transitive; lý do update.
- Lockfile diff và changes trong dependency graph.
- Source/publisher/repository identity.
- Vulnerability/advisory và compatibility notes.
- New install scripts/build plugin behavior.
- Integrity/provenance verification.
- Tests executed; FAIL/NOT_RUN/BLOCKED rõ ràng.
- Artifact SBOM/output digest khi áp dụng.
- Owner, reviewer và release decision.

Automation có thể mở PR nhưng **không nên tự chấp nhận mọi thay đổi chỉ vì bot là người tạo**.

### 17.3. Patch khẩn cấp và risk-based SLA

Khi có advisory nghiêm trọng:

- Xác định consumer, exposure và khả năng khai thác.
- Chọn cập nhật nhanh, disable vulnerable feature, isolate, WAF/egress mitigation hoặc giải pháp khác phù hợp.
- Test tối thiểu đủ bảo vệ invariant cần thiết.
- Ghi approved emergency exception khi phải bỏ bớt steps thông thường.
- Retest và hoàn thiện evidence sau emergency rollout.
- Kiểm tra lại các sản phẩm dùng cùng package.

Không tự đặt “mọi Critical trong 24 giờ” nếu tổ chức chưa có policy/khả năng tương ứng; cần source, tier, start time và người phê duyệt.

### 17.4. Rollback có giới hạn

Rollback có thể đưa một vulnerability trở lại. Nên có:

- Previous known-good artifact digest.
- Danh sách security advisories liên quan.
- Approval cho rollback tới phiên bản có risk.
- Recovery/forward-fix plan.
- Monitoring và post-change review.

Không rollback về malicious package chỉ vì bản mới gặp lỗi chức năng; cần tạo safe replacement.

## 18. Case study: Orders API và giao diện web

### 18.1. Kiến trúc giả định

Một nền tảng SaaS gồm:

- **Orders API:** Java/Spring Boot, build bằng Gradle.
- **Orders Web:** npm và frontend build pipeline.
- **PostgreSQL/Redis:** deployed bằng containers.
- **CI:** build/test/scan/sign/deploy.
- **Artifact registry:** lưu images và build artifacts.
- **Production:** nhiều tenant, dữ liệu đơn hàng nhạy cảm.

Rủi ro được xét: một update dependency chưa review hoặc bị compromise có thể chạy code trong CI, lấy deploy credential hoặc thay đổi cách authorization được xử lý.

### 18.2. Dependency inventory mẫu

| Source | Dependency category | Control cần có |
| --- | --- | --- |
| Orders API | Direct Maven coordinates trong Gradle | Exact direct version/managed constraints |
| Orders API | Transitive Java libraries | Lock configurations và graph review |
| Gradle build | Plugins và wrapper | Pinned versions/distribution verification |
| Orders Web | npm packages | package-lock.json + npm ci |
| Frontend build | Node/npm toolchain | Runtime/package manager version control |
| Container | Base images | Digest pin + refresh + scan |
| CI workflow | Actions/reusable jobs | Commit SHA/reference verification và permissions |
| Tool scripts | Downloaded CLI/codegen | Fixed URL/content digest/source policy |
| Release image | Final artifact | Immutable digest + SBOM/provenance |

### 18.3. Risk scenarios và security claims

**THR-SC-01:** Một transitive Java dependency tự resolve lên phiên bản mới sau khi publisher bị compromise.

**Claim SC-01:** release build không thay transitive resolved versions nếu manifest/lock không được cập nhật qua change có review.

**THR-SC-02:** Một package npm bị thay bằng version mới trong frontend build.

**Claim SC-02:** CI installation từ lockfile không tự tạo một graph mới; mismatch là lỗi hoặc finding.

**THR-SC-03:** CI action tag bị chuyển tới commit độc hại.

**Claim SC-03:** pipeline code được định danh bằng commit identity được phê duyệt; workflow changes được review và chạy với minimal permissions.

**THR-SC-04:** Base image tag bị cập nhật sau khi SCA scan.

**Claim SC-04:** deploy dùng đúng content digest đã được scan/provenance review; nếu khác, release gate chặn hoặc yêu cầu approval lại.

**THR-SC-05:** Package đã pin có CVE mới.

**Claim SC-05:** vulnerability signal đi vào triage và remediation process có owner, risk decision và retest, không bị bỏ qua vì lockfile không thay đổi.

### 18.4. Minh họa Java/Gradle

~~~kotlin
plugins {
    java
}

// Scope va exact configuration can duoc xac dinh cho project that.
dependencyLocking {
    lockAllConfigurations()
}

repositories {
    // Minh hoa; trong production can trusted repository policy.
    mavenCentral()
}

dependencies {
    // Dependency hu cau de minh hoa exact direct version.
    implementation("org.example:orders-policy-client:2.4.0")
    testImplementation("org.example:orders-security-fixtures:1.3.1")
}
~~~

Reviewer cần xác minh: configurations thực sự được resolve, lock state được commit, version catalogs/BOM/plugins được quản lý, dependency verification và CI không ghi lock ngoài approved update.

### 18.5. Minh họa frontend/npm

~~~bash
# Workflow can duoc phe duyet va da co package-lock.json hop le:
npm ci

# Sau khi resolve theo lock, chay cac check cua du an:
npm test
~~~

Lệnh minh họa, không phải kết quả thực thi. Cần kiểm tra package scripts, runner permissions, SCA, audit/source policies và build artifact identity.

### 18.6. Minh họa container reference

~~~text
registry.example.org/orders-api@sha256:<verified-orders-api-image-digest>
~~~

Digest placeholder cần được thay bằng hash thật khi triển khai. Deployment evidence cần ghi image digest thực tế ở runtime, không chỉ tag release.

### 18.7. Kết quả đánh giá mẫu

Có thể có hai tình huống:

- **Design adequate, implementation unknown:** có policy pinning/lockfile process nhưng chưa có build logs, artifact integrity results và CI negative tests.
- **Implementation gap:** npm ci chạy trên frontend nhưng Gradle không dùng lock state ở release, build plugin vẫn tải script latest. Khi đó không thể kết luận dependency graph stable end-to-end.

Case study là giả định và không khẳng định bất cứ build nào thực sự đã chạy.

## 19. CI/CD gates và verification workflow

### 19.1. Pipeline assurance

~~~mermaid
flowchart TD
    A["Source change / Dependency update PR"] --> B["Manifest + Lockfile + Registry review"]
    B --> C["Version, publisher, scripts, policy checks"]
    C --> D{"Unapproved drift or source?"}
    D -- "Yes" --> X["Fail / Triage / Correct"]
    D -- "No" --> E["Locked and verified dependency restore"]
    E --> F["SBOM / SCA / Integrity checks"]
    F --> G{"Findings within release policy?"}
    G -- "No" --> Y["Remediate or authorized risk decision"]
    G -- "Yes" --> H["Build immutable artifact"]
    H --> I["Functional and security tests"]
    I --> J["Provenance / Artifact digest"]
    J --> K["Release approval / Deployment"]
    K --> L["Verify runtime artifact identity"]
    L --> M["Continuous advisories / Refresh / Retest"]
~~~

Không được biến một scanner timeout, cache failure hoặc step skipped thành PASS.

### 19.2. CI gate kiểm tra điều gì?

| Gate | Expected result | Failure example |
| --- | --- | --- |
| Manifest-lock consistency | Dependencies resolve theo lockfile | Lock state phải tự update |
| Allowed version forms | Không có dynamic version trái policy | 1.+ hoặc latest trong release |
| Approved registry | Internal coords chỉ từ nguồn cho phép | Dependency confusion |
| Integrity verification | Artifact hash/signature hợp lệ | Checksum mismatch |
| Source/publisher review | Publisher và source được phê duyệt | New maintainer không review |
| Lockfile diff review | Change có owner/rationale | Transitive graph thay bất ngờ |
| SCA/advisory | Findings được xử lý theo risk tier | Critical unresolved blocker |
| Build tool pin | Wrapper/plugins/toolchain đã xác định | Runner tự tải latest |
| Image/CI refs | Digest/SHA pin theo baseline | Mutable tag trong production |
| Release identity | Artifact deploy trùng artifact được test | Retag hoặc rebuilt ngoài gate |

### 19.3. Policy-as-code mẫu

Một policy record minh họa, **không phải cấu hình trực tiếp của một CI provider**:

~~~yaml
policy_id: "SEC-DP-RELEASE-DEMO"
scope:
  applications:
    - "orders-api"
    - "orders-web"
  environments:
    - "release"
    - "production"
requirements:
  direct_versions: "EXPLICIT_OR_APPROVED_RANGE_WITH_LOCK"
  transitive_resolution: "LOCKED"
  lockfile_in_source_control: true
  approved_repositories_only: true
  dependency_integrity_check: true
  image_digest_pinning: true
  ci_external_code_reference: "APPROVED_IMMUTABLE_ID"
  dependency_changes_need_review: true
  vulnerability_review: "RISK_TIER_BASED"
  prohibit_silent_lock_updates_in_ci: true
  prohibit_skip_as_pass: true
evidence:
  required:
    - "source-commit"
    - "lockfile-digest"
    - "resolved-dependency-graph"
    - "integrity-verification-result"
    - "sbom-reference"
    - "security-scan-result"
    - "output-artifact-digest"
exception:
  requires:
    - "risk-owner"
    - "reason"
    - "expiry"
    - "compensating-control"
~~~

Cần xem policy có được **enforce** hay chỉ được viết vào YAML. Design document không phải runtime evidence.

## 20. Negative tests cho dependency pinning

### 20.1. Vì sao cần test các đường thất bại?

Một pipeline luôn PASS có thể đang bỏ qua lockfile hoặc tắt integrity verification. Do đó cần chạy **các phép thử âm có kiểm soát** trong môi trường test, không phá production.

| Test ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| **DP-T01** | Manifest và lockfile nhất quán | Locked restore PASS |
| **DP-T02** | Sửa manifest version nhưng không cập nhật lockfile | Locked restore FAIL/BLOCKED |
| **DP-T03** | Đưa dynamic version trái policy | Policy gate FAIL |
| **DP-T04** | Đổi một transitive version trong lock không có approval | Review/policy gate bắt thay đổi |
| **DP-T05** | Artifact bytes khác integrity metadata | Verification FAIL |
| **DP-T06** | Internal package có bản public trùng tên | Không resolve từ public registry |
| **DP-T07** | CI action dùng mutable ref khi policy yêu cầu SHA | Static workflow policy FAIL |
| **DP-T08** | Base image dùng mutable tag không approved | Container policy FAIL |
| **DP-T09** | Dependency có advisory vượt ngưỡng đã xác định | Triage/block/exception theo policy |
| **DP-T10** | Scanner không chạy do timeout | Gate không được báo PASS |
| **DP-T11** | Released artifact digest khác deployed digest | Deployment verification FAIL |
| **DP-T12** | Build plugin tải binary latest từ script ngoài lock | Inventory/policy finding |
| **DP-T13** | Lockfile được thay không qua review cần thiết | Branch/review gate FAIL |
| **DP-T14** | Build từ clean runner không có cache | Dùng đúng trusted sources và locked graph |
| **DP-T15** | Secret scanner phát hiện credential trong dependency scripts/log | Incident/secret policy kích hoạt |
| **DP-T16** | Một dependency bị revoke/yanked khỏi registry | Fail theo resolution policy; không auto dùng bản khác |

Các test cần được **ủy quyền và thực hiện trên fixtures không chứa bí mật thật**. Chỉ mô phỏng artifact mismatch hoặc package confusion bằng nguồn test/registry được kiểm soát, không thực hiện tấn công vào registry public.

### 20.2. Kiểm tra không chỉ HTTP/status của CI

Một CI step fail chưa chắc do đúng policy. Ví dụ locked restore lỗi vì mất Internet; không thể báo kiểm soát dependency drift đang hoạt động chỉ từ exit code khác 0.

Cần chứng minh **nguyên nhân fail**, log/trace của policy decision và có positive case tương ứng.

### 20.3. Clean-room build

Có thể dùng runner/container sạch với:

- Toolchain pinned.
- Config registry và credentials đã được phê duyệt.
- Không có artifact cache chưa xác minh.
- Lockfiles được commit.
- Offline/restricted network test theo khả năng.
- Output graph và digest được ghi.
- So sánh với approved records.

Nếu chỉ build PASS trên laptop có local cache, evidence yếu hơn cho khả năng tái dựng từ sources chính thức.

## 21. Design, implementation và operating effectiveness

### 21.1. Design effectiveness

**Câu hỏi:** policy pinning có bao phủ những dependency inputs ảnh hưởng artifact và supply-chain threats không?

Evidence:

- Build/dataflow và threat model.
- Pinning/integrity/source policy.
- Inventory ecosystem, plugins, images, actions.
- Versioning/update/exception requirements.
- CI gate design và expected failure behavior.
- Risk approval và owner mapping.

### 21.2. Implementation effectiveness

**Câu hỏi:** pipeline và repository thực thi đúng policy?

Evidence:

- Manifest/lockfiles versioned.
- Gradle/Maven/npm/toolchain configuration review.
- CI logs của locked restore và dependency verification.
- SCA/SBOM/manifest resolution.
- Negative tests về drift và checksum.
- Image/action refs theo digest/SHA.
- Artifact provenance record.

### 21.3. Operating effectiveness

**Câu hỏi:** control có hoạt động qua nhiều releases và security events?

Evidence:

- Dependency update PRs, approvals và test history.
- Drift violations và remediation.
- Advisory handling, patch cadence, risk acceptance.
- Exception expiration/review.
- Incident response, recall affected artifact và retest.
- Production artifact digest verification.
- Audit của registry publish và CI permissions.

Một lần tạo lockfile không chứng minh controls vận hành liên tục nếu lockfile có thể bị bypass ở những lần build sau.

## 22. Chất lượng evidence và kết luận assurance

### 22.1. Evidence metadata

Mỗi release/update assessment nên ghi:

- Service/product ID và release/version.
- Source commit, branch và review ID.
- Build ID, builder identity và toolchain.
- Lockfile path/hash, package manager version.
- Resolved graph hoặc SBOM reference.
- Repository/source và verification policy version.
- Dependency verification result.
- SCA/advisory results cùng rule/database date khi có.
- Image/action refs đã kiểm tra.
- Output artifact digest và deployed digest.
- Test cases, actual results và reviewer.
- Exclusions, exceptions, findings và residual risk.

### 22.2. Tính toàn vẹn và bảo vệ evidence

Evidence cần:

- Có nguồn gốc/provenance được xác minh ở mức phù hợp.
- Có quyền truy cập và retention rõ.
- Không chứa raw production credentials.
- Tránh payload nhạy cảm, private registry tokens hoặc personal data không cần thiết.
- Dễ truy vết từ finding tới fixed artifact.
- Có dấu hiệu nếu record bị sửa trái phép.
- Lưu phương pháp/tool version để người khác tái kiểm tra.

### 22.3. Các trạng thái kết luận

- **Effective within assessed scope:** có bằng chứng các controls pinning/integrity/update hoạt động đúng trong phạm vi và kỳ.
- **Partially effective:** một số ecosystem/sources được khóa nhưng còn build inputs ngoài coverage.
- **Ineffective:** có bằng chứng build tự drift, integrity mismatch bị bỏ qua hoặc policy bị bypass.
- **Insufficient evidence:** không đủ kết quả test/scan/runtime để kết luận.
- **Exception approved:** rủi ro còn lại được chấp nhận có điều kiện, không đồng nghĩa control đạt.
- **Not applicable:** có lý do được review vì sao control không áp dụng.

Một báo cáo “lockfile present” chỉ là **một loại evidence**, chưa đủ kết luận.

## 23. Xử lý sự cố supply-chain liên quan pinned dependency

### 23.1. Khi pinned version bị phát hiện chứa mã độc hoặc vulnerability

1. Xác định package, version, artifact digest và affected products.
2. Kiểm tra build logs, SBOM, provenance và artifact inventory.
3. Phân loại liệu package được tải trong build, bundled, executed hay chỉ là development dependency.
4. Đánh giá exposure, các quyền trong CI/runtime và khả năng exfiltration.
5. Nếu có dấu hiệu compromise, kích hoạt incident response.
6. Contain: disable deployment, revoke affected tokens/secrets, isolate runner nếu cần.
7. Chọn safe version/alternative, cập nhật lock và integrity metadata.
8. Review source, dependencies, install scripts và registry.
9. Rebuild/retest bằng trusted environment.
10. Xác minh artifact digest thực tế sau deploy và theo dõi.
11. Bảo toàn evidence theo quy trình; không phát tán secret trong ticket.
12. Cập nhật root cause, source policies, controls và detection.

### 23.2. Pinning hỗ trợ điều tra như thế nào?

Với lockfiles/SBOM/provenance có chất lượng:

- Biết releases nào chứa version rủi ro.
- Biết image digest nào cần thu hồi.
- Xác định CI builds nào đã thực thi install script.
- Tìm consumers ở những tenant/environment nào.
- So sánh điểm bắt đầu xuất hiện package.
- Ưu tiên rebuild và retest.

Nếu một dependency bị thay nội dung ở registry nhưng giữ cùng version, **version string không đủ để phân biệt**; cần artifact digests và provenance.

### 23.3. Package bị yanked hoặc không còn tải được

Khi pin trỏ đến artifact không còn tồn tại, không nên tự chuyển sang latest để giữ build chạy.

Các lựa chọn có kiểm soát:

- Restore artifact từ trusted internal mirror có integrity verified.
- Chuyển sang approved patched version qua PR.
- Chọn alternative library với review.
- Tạm block release nếu không có nguồn tin cậy.
- Chấp nhận risk có điều kiện trong phạm vi được phép và có record.

Availability của supply chain cần được thiết kế nhưng không được phá integrity để lấy tính tiện lợi.

## 24. KPI/KRI về dependency pinning

| Chỉ số | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| **Pinned dependency coverage** | Tỷ lệ direct/transitive/components có identity ổn định | Population có thể bỏ sót external downloads |
| **Locked build coverage** | Tỷ lệ release pipelines enforce lock | Job PASS có thể vẫn thiếu integrity |
| **Integrity verification coverage** | Tỷ lệ artifact được kiểm tra hashes/signatures | Hash source có thể không đáng tin |
| **Immutable image/action references** | Tỷ lệ production refs dùng digest/SHA theo policy | Digest không chứng minh không có CVE |
| **Unapproved graph drift** | Số lần resolution ngoài change được review | Không có finding chưa chắc detection hoạt động |
| **Dependency update latency** | Thời gian từ triage tới verified patched release | SLA theo risk tier, không chỉ số tuyệt đối |
| **High-risk vulnerable pinned deps** | Packages còn risk chưa xử lý | Một package có blast radius lớn |
| **Unknown provenance components** | Thành phần thiếu nguồn/build evidence | SBOM thiếu có thể che gap |
| **Unreviewed lockfile changes** | Changes thiếu approval | Cần rule có khả năng enforce |
| **Dependency confusion tests pass** | Source isolation được kiểm chứng | Chỉ áp phạm vi namespace đã test |
| **Expired supply-chain exceptions** | Những rủi ro được chấp nhận quá hạn | Không được tính như compliant |
| **Released artifact traceability** | Artifact liên kết source/build/SBOM | Cần đối chiếu deployed digest |
| **CI gate completeness** | Các checks đã hoàn tất, không bị skip | Màu xanh pipeline có thể gây nhầm |

### 24.1. Ví dụ diễn giải số liệu

Giả sử release pipeline có 120 dependency artifacts trong inventory, trong đó 96 có bằng chứng version selection và integrity verification phù hợp policy.

- **Assessed coverage = 96/120 = 80%** trên population đã kiểm kê.
- 24 artifact còn lại là **gap/unknown**, không đồng nghĩa vô hại.
- Nếu 1 trong 24 là build plugin có quyền lấy production token, rủi ro có thể rất lớn.
- Không nói “supply chain an toàn 80%”.

### 24.2. Tránh KPI làm đóng băng updates

Nếu chỉ thưởng cho “không đổi lockfile”, đội có thể giữ version cũ có CVE nhiều năm. Cần cân bằng:

- Stable/controlled graph.
- Patch freshness.
- Vulnerability remediation.
- Exception lifetime.
- Artifact/source integrity.
- Detection/test effectiveness.

Mục tiêu là **controlled and timely evolution**, không phải bất động.

## 25. RACI và governance

| Vai trò | Trách nhiệm |
| --- | --- |
| **Application owner** | Chọn direct dependencies, đánh giá compatibility, cập nhật và tests |
| **Build/platform owner** | Wrapper/toolchain, lockfile enforcement, CI gates, runners |
| **AppSec/supply-chain security** | Threat model, pinning/integrity policy, vulnerability triage |
| **Artifact registry owner** | Publish controls, trusted mirrors, immutable artifacts/audit |
| **SRE/release engineering** | Artifact promotion/deployment identity, rollback |
| **Risk owner** | Quyết định residual risk/exception đúng thẩm quyền |
| **Assurance/auditor** | Review source/evidence/coverage/independence |
| **Incident response** | Triage compromise, containment, rebuild và recovery |
| **Procurement/legal/compliance** | Vendor/contract/license obligations khi áp dụng |

RACI minh họa:

| Hoạt động | App owner | Build/Platform | AppSec | Registry owner | Risk owner | Assurance |
| --- | --- | --- | --- | --- | --- | --- |
| Define pinning policy | C | R | **A/R** | C | C | C |
| Apply lockfiles | **A/R** | R | C | I | I | C |
| Source and artifact verification | R | **A/R** | C | R | I | C |
| Update and test dependencies | **A/R** | R | C | I | I | C |
| Vulnerability triage | R | C | **A/R** | C | C | C |
| Approved exceptions | C | C | C | I | **A/R** | I |
| Release artifact traceability | R | **A/R** | C | R | I | C |
| Independent assurance conclusion | C | C | C | C | I | **A/R** |

Thực tế cần phân vai theo hệ thống và mức rủi ro, bảo đảm separation of duties cho thay đổi pinning/verification policy có tác động lớn.

## 26. Mẫu hồ sơ assurance cho dependency pinning

YAML sau chỉ là **mẫu giả định**, không tuyên bố kiểm tra nào đã thực sự chạy:

~~~yaml
assessment_id: "DEPENDENCY-PINNING-DEMO-004"
service: "orders-api"
module: "SECURITY_SECURITY_ASSURANCE"
chapter: "Supply chain security"
topic: "Dependency pinning"
assessment_scope:
  environment: "integration"
  commit: "DEMO_NOT_VERIFIED"
  build_id: "DEMO_NOT_VERIFIED"
  artifacts:
    - "orders-api-image"
  ecosystems:
    - "gradle"
    - "npm"
    - "oci-image"
    - "ci-actions"
risk_owner: "Orders Product Risk Owner"
control_owner: "Build Platform Owner"
requirements:
  - "DP-REQ-01"
  - "DP-REQ-02"
  - "DP-REQ-03"
  - "DP-REQ-04"
  - "DP-REQ-05"
  - "DP-REQ-06"
security_claims:
  - "Resolved versions cannot drift without reviewed change"
  - "Artifact integrity is checked against trusted metadata"
  - "Images and CI actions use approved immutable identities"
  - "Vulnerable pinned packages are monitored and remediated"
verification_plan:
  - id: "DP-T01"
    test: "locked-install-positive"
    result: "NOT_RUN"
  - id: "DP-T02"
    test: "manifest-lock-mismatch"
    result: "NOT_RUN"
  - id: "DP-T05"
    test: "integrity-mismatch-detection"
    result: "NOT_RUN"
  - id: "DP-T07"
    test: "mutable-ci-action-rejected"
    result: "NOT_RUN"
  - id: "DP-T11"
    test: "deployed-artifact-digest-match"
    result: "NOT_RUN"
evidence_refs: []
dependency_inventory_ref: null
lockfile_digest: null
sbom_ref: null
artifact_digest: null
source_policy_version: "NOT_VERIFIED"
design_review: "PENDING"
implementation_review: "NOT_VERIFIED"
operating_review: "NOT_VERIFIED"
findings: []
approved_exceptions: []
assurance_conclusion: "INSUFFICIENT_EVIDENCE"
confidence: "LOW"
next_action: "Review scope and execute locked build and negative tests"
~~~

Để thành evidence thực, cần thay placeholder bằng dữ liệu đã kiểm chứng: tool versions, hashes, lockfiles, registry evidence, run IDs, reviewer, result, time, exclusions và risk decisions.

## 27. Những sai lầm thường gặp

### 27.1. Nghĩ exact version đã khóa toàn bộ graph

Một direct dependency có thể kéo transitive versions. **Khắc phục:** xác minh effective graph và lock state.

### 27.2. Commit lockfile nhưng CI tự rewrite

Build vẫn trôi theo thời gian. **Khắc phục:** frozen/locked install, mismatch phải fail hoặc trigger review.

### 27.3. Coi lockfile là bằng chứng integrity

Lock chỉ xác định resolution. **Khắc phục:** kiểm tra checksum/signature/provenance từ nguồn đáng tin.

### 27.4. Dùng latest tag cho image và CI actions

Tag/branch có thể đổi. **Khắc phục:** digest/full SHA theo policy và update automation có review.

### 27.5. Pin version rồi không bao giờ cập nhật

Vulnerability tồn tại lâu. **Khắc phục:** SCA monitoring, patch cadence và exception expiration.

### 27.6. Chỉ xem libraries, bỏ build plugins

Plugin có thể chạy code với CI privileges. **Khắc phục:** kiểm kê plugins, wrappers và code generators.

### 27.7. Xem private registry luôn đáng tin

Registry có thể cấu hình sai, publish over-write hoặc compromise. **Khắc phục:** RBAC, audit, immutable policy, integrity verification.

### 27.8. Tin source checksum được thay cùng artifact

Hash không còn là reference đáng tin. **Khắc phục:** trust/approval của verification metadata và independent checks.

### 27.9. Bỏ dependency confusion

Package cùng tên có thể được lấy từ public registry. **Khắc phục:** namespace routing, source allowlist, negative tests.

### 27.10. Không review install scripts

Pinned package vẫn chạy code độc hại trong build. **Khắc phục:** scripts review, runner isolation và minimal credentials.

### 27.11. Cho security scanner lỗi nhưng gate PASS

Độ bao phủ bị bỏ qua. **Khắc phục:** trạng thái FAIL/BLOCKED/NOT_RUN riêng.

### 27.12. Không kiểm tra release artifact thực sự được deploy

SCA kiểm tra image A nhưng production dùng image B. **Khắc phục:** artifact digest chain và deployment verification.

### 27.13. SBOM từ manifest được coi là SBOM đầy đủ

Có thể thiếu OS/native/bundled components. **Khắc phục:** tạo/đối chiếu SBOM từ artifact cuối theo scope.

### 27.14. Chấp nhận CVE bằng lời nói

Không có reviewer/expiry/rationale. **Khắc phục:** time-bound exception với evidence và risk owner.

### 27.15. Không quản lý multi-platform variants

Image digest/index có thể biểu diễn nhiều architecture. **Khắc phục:** kiểm tra platform artifact và runtime digest.

### 27.16. Dùng cache local làm căn cứ tái lập

Clean runner có thể tải artifact khác hoặc fail. **Khắc phục:** build sạch với trusted sources và integrity policy.

### 27.17. Xóa finding khi PR merge

Artifact chưa được rebuild/deploy/retest. **Khắc phục:** xác nhận build/version/artifact deployment và verified closure.

### 27.18. Coi signed artifact là không thể có mã độc

Signer/build có thể bị compromise. **Khắc phục:** signer trust, code/process review, isolated builders và monitoring.

## 28. Checklist triển khai và đánh giá dependency pinning

- [ ] Có dependency inventory cho direct, transitive, plugins, toolchains và external downloads.
- [ ] Đã định nghĩa release scope, risk tier, owner và approved repositories.
- [ ] Direct dependency version selections ổn định hoặc được lock theo policy.
- [ ] Transitive graph được khóa và có cách review diff.
- [ ] CI dùng frozen/locked restore, không auto-update lock state.
- [ ] Dynamic versions/tags trái policy được phát hiện và chặn.
- [ ] Build plugins, wrappers và code generators có version/source control.
- [ ] package manager/JDK/Node/Go/Python runtime được quản lý theo scope.
- [ ] Dependency integrity verification được bật và kiểm chứng bằng negative test.
- [ ] Hash/signature metadata có trust model và quyền sửa phù hợp.
- [ ] Private package namespaces không resolve trái phép từ public registry.
- [ ] Package source/publisher/install scripts được review khi update.
- [ ] Container base images được pin theo digest khi policy yêu cầu.
- [ ] OS packages và external install scripts không được bỏ ngoài inventory.
- [ ] CI actions/reusable workflows được pin theo identity ổn định phù hợp.
- [ ] CI runner có minimal permissions và secret isolation.
- [ ] SCA/advisory monitoring hoạt động kể cả khi pinned versions không đổi.
- [ ] SBOM bao phủ đúng deployed artifact, không chỉ direct dependencies.
- [ ] Release artifact có digest và provenance/identity metadata.
- [ ] Deployed artifact digest được đối chiếu với artifact đã kiểm thử.
- [ ] Dependency update PR có old/new versions, rationale, diff, tests và review.
- [ ] Mismatch giữa manifest/lock/registry bị từ chối hoặc điều tra.
- [ ] Scanner timeout/skip không được tính PASS.
- [ ] Có policy xử lý compromised/yanked/missing package.
- [ ] Có cơ chế patch và emergency response theo mức rủi ro.
- [ ] Rollback không tự quay lại malicious/vulnerable package đã biết.
- [ ] Exceptions có owner, risk decision, expiry và compensating controls.
- [ ] Evidence có commit, lockfile hash, tool version, build ID, artifact digest.
- [ ] Có negative tests cho lock drift, integrity mismatch và source confusion.
- [ ] Có periodic review khi ecosystem/package manager/registry thay đổi.
- [ ] Kết luận nêu scope, exclusions, confidence, residual risk và gaps chưa test.

Checklist hỗ trợ quản lý, **không thay thế evidence từ build và release thực tế**.

## 29. Bài tập thực hành

### Bài tập 1 — Phân biệt direct và transitive pinning

Một project pin direct library ở 2.4.0 nhưng không có lockfile. Ngày hôm sau build dùng transitive parser version mới.

Hãy:

1. Vẽ dependency graph.
2. Xác định nguyên nhân drift có thể.
3. Đề xuất lock và verification control.
4. Viết negative test cho mismatch.
5. Ghi những evidence cần để chứng minh đã fix.

### Bài tập 2 — Đánh giá pipeline npm

Một frontend commit package-lock.json nhưng CI chạy một lệnh có thể cập nhật lock, sau đó không fail dù lockfile bị sửa.

Hãy thiết kế gate:

- Frozen/locked install.
- Lockfile consistency.
- Change diff review.
- SCA và script risk.
- Integrity verification.
- Artifact digest/CI run evidence.

Giải thích tại sao lockfile presence chưa đủ.

### Bài tập 3 — Container image update

Production dùng runtime image theo tag. Scan trước release trên digest A nhưng khi deploy tag đã trỏ digest B.

Hãy viết security requirement, acceptance criteria và verification plan để chứng minh deployed digest khớp artifact đã review. Xem thêm multi-platform và vulnerability refresh.

### Bài tập 4 — Dependency confusion

Một package nội bộ có tên trùng package trong public registry. Viết risk scenario và các controls cho namespace, repository routing, publisher trust, negative tests và incident response. Không thử tấn công registry public ngoài môi trường được phép.

### Bài tập 5 — Malicious pinned package

Một package đã pin và đã dùng 6 tháng bị công bố có malicious install script.

Hãy lập danh sách:

- Các build có thể đã thực thi script.
- Artifact/version/digest bị ảnh hưởng.
- Quyền và secrets có thể đã lộ.
- Cách contain, revoke, rebuild, test và monitor.
- Evidence cần giữ và kết luận residual risk.

## 30. Câu hỏi tự kiểm tra

1. Dependency pinning là gì và mục tiêu bảo mật chính là gì?
2. Exact direct version khác lockfile ở phạm vi nào?
3. Vì sao pinning không tự bảo đảm artifact integrity?
4. Version 1.2.3 có đủ để xác minh bytes từ registry không?
5. Reproducible dependency graph khác bit-for-bit reproducible build thế nào?
6. Dynamic version và mutable tag có tạo rủi ro gì?
7. Transitive dependency có thể đổi dù direct version không đổi không?
8. Gradle version catalog có thay dependency lockfile không?
9. Dependency verification của Gradle khác dependency locking thế nào?
10. Maven dependencyManagement có phải lockfile toàn bộ graph không?
11. npm ci giúp kiểm soát điều gì và không chứng minh điều gì?
12. Vì sao cần quản lý lifecycle scripts của npm packages?
13. go.sum có vai trò gì và vì sao không nên đánh đồng với package-lock.json?
14. Cấu hình pip --require-hashes cần thỏa điều kiện gì?
15. Vì sao pin container image digest mạnh hơn dùng latest tag?
16. Digest có chứng minh container image không có vulnerability không?
17. Pin GitHub Action theo commit SHA giúp giảm rủi ro nào?
18. Một pinned CI action vẫn có thể nguy hiểm vì sao?
19. Dependency confusion khác typosquatting thế nào?
20. Registry nội bộ cần những controls nào?
21. Checksum lấy từ cùng server bị compromise có giới hạn gì?
22. Signature và provenance hỗ trợ integrity/trust ra sao?
23. SBOM khác lockfile ở những điểm nào?
24. SCA advisory match có nghĩa package đang exploitable không?
25. Vì sao phải cập nhật pinned dependencies theo security advisories?
26. Một PR update dependency nên có evidence gì?
27. Test nào chứng minh CI thực sự từ chối lockfile mismatch?
28. Vì sao CI job fail do network outage không chứng minh pinning policy hiệu quả?
29. Làm sao kiểm tra artifact deploy đúng artifact đã scan?
30. Khi package bị yanked, tại sao không tự dùng latest?
31. Rủi ro nào tồn tại ở build plugins và wrappers?
32. Vì sao local cache không đủ làm evidence reproducibility?
33. Design effectiveness khác operating effectiveness của pinning thế nào?
34. Exception approved có được tính là security control PASS không?
35. Coverage 80% có nói supply chain an toàn 80% không?
36. Khi phát hiện malicious pinned package, nên rà soát secrets và runner như thế nào?
37. Vì sao policy không nên thưởng cho việc giữ nguyên dependency mãi mãi?
38. Những thay đổi nào nên kích hoạt đánh giá lại pinning assurance?

## 31. Tổng kết

**Dependency pinning** là cơ chế cố định phiên bản hoặc định danh nội dung của những thành phần được sử dụng trong build và release, giúp giảm dependency drift, tăng khả năng tái dựng và hỗ trợ điều tra chuỗi cung ứng. Một chương trình đúng cần phối hợp **exact direct versions, transitive lockfiles, trusted repository routing, artifact integrity verification, digest/SHA pinning cho image và CI, toolchain controls, SBOM/SCA, provenance, approved updates và incident response**. Pinning không tự chứng minh package an toàn, không ngăn mọi malicious release và không thay thế patch management; việc giữ mãi một phiên bản có vulnerability cũng là rủi ro. Trong module **SECURITY_SECURITY_ASSURANCE**, cần đánh giá **risk → requirement → control → locked/verified build → artifact/deployment evidence → finding → remediation/retest**, phân biệt design, implementation và operating effectiveness. Mọi kết luận phải gắn scope, commit, lockfile, build, artifact digest, tool versions, thời điểm, test coverage và residual risk; khi dependency ecosystem hoặc build pipeline thay đổi, assurance phải được đánh giá lại.
