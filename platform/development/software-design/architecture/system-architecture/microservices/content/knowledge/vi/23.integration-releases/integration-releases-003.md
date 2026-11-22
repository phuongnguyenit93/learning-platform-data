# Xây dựng gói bất biến và ghi nhận nguồn gốc bản dựng

## 1. Vì sao microservices cần artifact bất biến?

Một microservice thường được build nhiều lần mỗi ngày, chạy trên nhiều môi trường và được triển khai bởi các pipeline độc lập. Khi có sự cố ở production, câu hỏi đầu tiên không chỉ là “đang chạy phiên bản nào?” mà là:

- **Chính xác những byte nào** đã được đưa vào môi trường?
- Artifact đó được tạo từ commit nào, bởi pipeline và builder nào?
- Những dependency, base image và công cụ build nào đã tham gia?
- Có bằng chứng cho thấy artifact được kiểm thử, kiểm tra bảo mật và phê duyệt trước khi deploy?
- Có thể chạy lại bản ổn định trước đó bằng đúng artifact đã lưu hay không?

Nếu một image tag như `catalog-service:latest` được ghi đè, hai lần triển khai cùng tên có thể nhận nội dung khác nhau. Nếu staging và production tự build lại từ cùng nhánh Git, hai môi trường có thể sử dụng các byte khác nhau vì dependency thay đổi, công cụ build khác phiên bản hoặc input bên ngoài thay đổi.

**Artifact bất biến (immutable artifact)** là gói đầu ra của quá trình build mà nội dung được xác định bằng một định danh không phụ thuộc vào tên có thể sửa, thường là **cryptographic digest**. **Build provenance** là bản ghi có cấu trúc mô tả artifact được tạo *bởi ai/cái gì, từ nguồn nào, với các đầu vào và quy trình nào*. Hai khái niệm bổ sung cho nhau: digest xác định **cái gì**; provenance cung cấp chứng cứ về **quá trình tạo ra nó**.

Mục tiêu của bài:
1. Phân biệt tag, version, digest, checksum, chữ ký, SBOM và provenance.
2. Xây dựng pipeline tạo artifact một lần và promote đúng artifact qua các môi trường.
3. Ghi nhận liên kết từ source commit tới build, artifact, test và deployment.
4. Đặt chính sách verify provenance và chữ ký tại các điểm phát hành.
5. Nhận biết giới hạn của tính bất biến, khả năng tái lập build và các phương thức tấn công chuỗi cung ứng phần mềm.

## 2. Các khái niệm nền tảng

| Khái niệm | Trả lời câu hỏi | Ý nghĩa trong release |
| --- | --- | --- |
| Source revision | Mã nguồn ở trạng thái nào? | Commit SHA xác định snapshot đã build; branch name có thể dịch chuyển |
| Version | Người dùng gọi bản này là gì? | Ví dụ `1.8.3`; thuận tiện cho phát hành và tương thích |
| Artifact | Thứ gì được triển khai? | JAR, OCI image, package hoặc bundle được build |
| Tag | Tên dễ nhớ đang trỏ đến đâu? | Ví dụ `catalog:1.8.3`, `catalog:stable`; nhiều registry cho phép chuyển tag |
| Digest | Nội dung hoặc manifest có hash nào? | Ví dụ `sha256:...`; tham chiếu artifact theo nội dung |
| Checksum | Byte có thay đổi khi truyền/lưu không? | Phát hiện sai khác nhưng một checksum không có nguồn tin cậy riêng vẫn có thể bị thay |
| Digital signature | Ai hoặc danh tính workload nào đã ký? | Xác minh tính toàn vẹn và nguồn ký theo chính sách tin cậy |
| Build provenance | Artifact được tạo bằng quá trình nào? | Liên kết subject digest với source, builder, invocation, dependencies |
| SBOM | Artifact chứa thành phần nào? | Danh sách package/dependency để quản lý lỗ hổng, license và ảnh hưởng |
| Attestation | Ai xác nhận một phát biểu có cấu trúc về artifact? | Có thể mang provenance, kết quả test hoặc nội dung kiểm tra khác |
| Release record | Vì sao và khi nào được triển khai? | Liên kết digest, môi trường, quyết định promote, kết quả rollout |

**Bất biến khác với tái lập được (reproducible).** Một artifact đã lưu theo digest là một đối tượng nội dung được xác định duy nhất. Tuy nhiên cùng commit có thể build thành hai artifact có digest khác nhau nếu chứa timestamp, thứ tự file không ổn định hay dependency động. Build reproducible là khả năng tạo lại đúng byte từ cùng nguồn và đầu vào đã định nghĩa; đó là thuộc tính bổ sung, có giá trị cao nhưng không phải tiền đề bắt buộc để dùng artifact bất biến.

**Digest khác với chữ ký.** Hash khẳng định hai bản có cùng nội dung theo thuật toán hash. Chữ ký dùng danh tính và quan hệ tin cậy để trả lời liệu artifact hoặc attestation có được phát hành bởi builder/đơn vị được phép hay không. Không nên xem một tag “đã ký” là đủ nếu chữ ký không ràng buộc với digest cụ thể.

## 3. Mô hình chuỗi chứng cứ từ commit đến production

~~~mermaid
flowchart TD
    A[Source repository<br/>Commit SHA] --> B[CI runner có danh tính]
    C[Toolchain và dependency<br/>được khóa] --> B
    B --> D[Build và kiểm thử]
    D --> E[Artifact bất biến<br/>OCI digest hoặc JAR checksum]
    D --> F[Provenance attestation]
    D --> G[SBOM và kết quả scan]
    E --> H[Registry/artifact repository]
    F --> H
    G --> H
    H --> I{Verify release policy}
    I -- Không đạt --> X[Chặn promote hoặc deploy]
    I -- Đạt --> J[Staging theo digest]
    J --> K[Production theo cùng digest]
    K --> L[Release record + telemetry]
~~~

Chuỗi liên kết cần giữ nguyên:

`repository@commit → build-run/builder → artifact digest → chứng cứ kiểm thử → quyết định promote → deployment digest`

Một bản ghi chỉ có “version 1.8.3” không đủ để truy nguyên. Tên version có thể được gán sai, tag có thể bị ghi đè, artifact có thể bị rebuild. Release record cần giữ cả **định danh nội dung** và **ngữ cảnh quyết định phát hành**.

Ví dụ: khi `catalog-service` gặp lỗi, hệ thống lưu:

- Source: `git.example/team/catalog`, commit `8fa12cd...`.
- CI workflow/run: `build-catalog`, run `#1842`, builder identity của CI.
- Artifact: `registry.example/catalog@sha256:<digest>`.
- Evidence: test report, provenance attestation, SBOM, kết quả scan.
- Deploy: staging lúc 09:00, production lúc 11:00, đều cùng digest.
- Rollout: người hoặc chính sách phê duyệt, tỷ lệ canary, metric và kết luận.

Digest giả định ở trên là **chỗ điền giá trị minh họa**, không phải digest thực. Không bao giờ dùng chuỗi placeholder làm tham chiếu deploy thật.

## 4. Bốn nguyên tắc thiết kế

### Nguyên tắc 1: Build một lần, promote nhiều lần

CI tạo artifact từ một revision đã chốt. CD sử dụng chính artifact đó ở integration, staging và production. Môi trường có thể khác URL, credential hoặc resource limit, nhưng **không thay đổi byte của artifact**. Việc thay cấu hình cần có nguồn kiểm soát và release record riêng.

Dùng:

`registry.example/catalog-service@sha256:<verified-digest>`

Thận trọng với:

`registry.example/catalog-service:latest`

Câu lệnh triển khai theo tag có thể tham chiếu đến nội dung khác ở lần chạy sau. Có thể gắn tag cho khả năng đọc của con người, nhưng rollout nên khóa theo digest.

### Nguyên tắc 2: Đầu vào build phải được xác định

Lưu rõ source revision, dependency lockfile hoặc resolved graph, base image digest, toolchain/JDK/Gradle version, compiler flags và build arguments ảnh hưởng đầu ra. Tránh những đầu vào tự thay đổi như `latest`, version range không khóa, `SNAPSHOT` hoặc `curl | bash` lấy script tùy thời điểm.

### Nguyên tắc 3: Chứng cứ phải được tạo ở nơi có danh tính tin cậy

Provenance do CI runner được quản lý tạo và ký có giá trị hơn một tệp JSON do developer tự viết. Danh tính builder, quyền workflow, nguồn repository và branch protection phải được kiểm soát. Chữ ký chỉ có ý nghĩa khi phía verify xác nhận **đúng danh tính và đúng đối tượng**.

### Nguyên tắc 4: Verify trước khi cho phép triển khai

Không chỉ sinh chứng cứ rồi lưu. Chính sách CD hoặc admission controller cần kiểm tra digest, chữ ký, provenance subject, builder identity, nguồn repository, revision cho phép và kết quả kiểm tra bắt buộc. Thất bại phải chặn phát hành hoặc đi qua quy trình ngoại lệ có thẩm quyền, được ghi lại.

## 5. Bảo toàn tính bất biến trong artifact registry

Với OCI image, digest thường là hash của một **manifest hoặc image index**. Digest của image index đa kiến trúc có thể khác digest manifest cho `linux/amd64` hay `linux/arm64`. Chính sách deploy và verification phải thống nhất loại subject đang kiểm tra. Với JAR hoặc ZIP, checksum thường tính trực tiếp trên byte của file.

Tính bất biến cần được giữ ở cả lưu trữ và cách sử dụng:

1. Bật chính sách không ghi đè tag release khi registry hỗ trợ.
2. Chặn thao tác xóa hoặc thay artifact trái phép; phân quyền upload, promote, delete riêng.
3. Sử dụng digest cho deployment manifest, Helm values hoặc GitOps revision.
4. Lưu lịch sử mapping version ↔ tag ↔ digest. Tag giúp tìm, digest mới là định danh nội dung.
5. Có chính sách retention và garbage collection để artifact cần rollback không bị xóa khỏi registry.
6. Phân tách bản build thử nghiệm với artifact được duyệt để phát hành production.

**Lưu ý:** Digest chứng minh nội dung tham chiếu không đổi, nhưng không bảo đảm artifact sẽ còn tồn tại mãi mãi. Registry có thể xóa đối tượng do retention, lỗi vận hành hoặc mất quyền truy cập. Vì vậy kiểm tra khả năng lấy lại artifact là một phần của kế hoạch rollback.

## 6. Chuẩn bị môi trường build cho dịch vụ Java

Ví dụ dịch vụ Spring Boot `catalog-service` tạo executable JAR và đóng gói OCI image. Cấu trúc đường dẫn và task Gradle dưới đây là minh họa; điều chỉnh theo module thực tế.

~~~text
catalog-service/
├── src/
├── build.gradle
├── gradle.lockfile
├── Dockerfile
└── deployment/
    ├── staging/
    └── production/
~~~

Ở mức dependency và toolchain:

- Khóa Gradle Wrapper, JDK toolchain và phiên bản plugin; xác nhận chúng đến từ nguồn tin cậy.
- Bật dependency locking cho cấu hình thực sự dùng trong build; lưu lockfile trong source control.
- Dùng dependency verification/checksum khi phù hợp để phát hiện artifact dependency bị thay.
- Không để `version = "+"` hoặc các version động trong đường release chính.
- Cố định base image theo digest được kiểm chứng; chủ động cập nhật digest theo lịch thay vì âm thầm kéo “mới nhất”.
- Làm rõ khác biệt giữa source dependency của build và runtime dependency đóng vào image.

Ví dụ dòng CI tạo JAR:

~~~bash
./gradlew --no-daemon clean test bootJar
sha256sum build/libs/catalog-service.jar
~~~

Lệnh này **chỉ minh họa**: tên JAR và task có thể khác trong thực tế. Nếu JAR chứa tên phiên bản hoặc classifiers, hãy lấy output từ metadata build thay vì tự đoán tên file. Hash JAR chỉ mô tả JAR; artifact production có thể là OCI image bao gồm cả base image, runtime và cấu hình filesystem, nên cần ghi thêm digest image.

Dockerfile minh họa dùng JAR đã được tạo:

~~~dockerfile
# Dùng base image đã được lựa chọn và pin theo digest trong pipeline thật.
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY build/libs/catalog-service.jar /app/app.jar
USER 10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Dòng `FROM` đang dùng tag để người học dễ đọc; với release production cần thay bằng image `@sha256:<approved-base-digest>` và lưu chính digest base đó trong provenance. Không đưa secret, access token hoặc file `.env` vào build context. Nên có `.dockerignore` và quyền runtime tối thiểu. Nếu dùng multi-stage build, vẫn cần ghi nhận builder image/toolchain và đầu vào của từng stage.

## 7. Một pipeline tham chiếu

Giả sử CI có quyền build từ protected branch. Các bước độc lập về ý nghĩa:

~~~yaml
pipeline: catalog-build
source:
  repository: git.example/team/catalog-service
  revision: exact_git_commit_sha
stages:
  - name: verify-source
    checks: [protected-branch, code-review, pinned-toolchain]
  - name: test
    checks: [unit-test, integration-test, contract-test]
  - name: build
    outputs: [jar, oci-image]
  - name: inspect
    outputs: [sbom, dependency-scan, image-scan]
  - name: publish
    outputs: [oci-digest, immutable-release-record]
  - name: attest
    outputs: [signed-provenance]
  - name: promote
    requires: [all-mandatory-checks-pass, verify-provenance]
    target: staging
~~~

Đây là **mẫu mô tả**, không phải file YAML có thể thực thi trực tiếp trong GitHub Actions/GitLab/Jenkins. Chức năng publish và attest có thể được nền tảng hỗ trợ theo trình tự khác; điểm cốt lõi là attestation phải ràng buộc với **digest của artifact đã publish** và được cung cấp cùng artifact trước khi CD cho phép dùng.

Trình tự triển khai cụ thể:

1. CI checkout đúng commit, xác nhận chính sách nhánh và quyền workflow.
2. Chạy build/test trong môi trường cô lập với dependency và toolchain được kiểm soát.
3. Tạo JAR và OCI image, kiểm tra registry trả về digest sau push.
4. Sinh SBOM cho artifact hoặc các thành phần trong image, liên kết với digest.
5. Phát hành provenance attestation từ hệ thống CI có danh tính phù hợp và ràng buộc subject digest.
6. Ký artifact/attestation theo cơ chế được tổ chức tin cậy.
7. CD truy vấn chứng cứ của digest, verify chính sách, rồi triển khai bằng digest.
8. Theo dõi rollout; lưu deployment digest, kết quả kiểm chứng, người duyệt và quyết định cuối.

**Không rebuild trong CD.** Nếu một biến môi trường hoặc setting thay đổi, ghi nhận version cấu hình bên cạnh artifact digest. Một release được nhận diện tốt thường là cặp `artifact digest + deployment/config revision`, vì cùng image có thể chạy khác nhau khi cấu hình khác.

## 8. Build provenance chứa những gì?

Một attestation provenance thường có **subject** (artifact digest) và **predicate** mô tả quá trình build. Các mô hình chuẩn như in-toto attestation và SLSA provenance giúp trao đổi dữ liệu có cấu trúc; lựa chọn trường cụ thể tùy phiên bản chuẩn và khả năng của CI.

Các nhóm thông tin quan trọng:

| Nhóm | Nội dung cần lưu |
| --- | --- |
| Subject | Tên artifact và digest thực sự đã tạo |
| Source | Repository URI, commit SHA, thông tin nguồn đầu vào |
| Builder | Danh tính hệ thống build, môi trường runner, loại workflow |
| Invocation | Cách pipeline được kích hoạt, tham số build được phép tiết lộ |
| Materials/dependencies | Base image, dependency chính, toolchain, các tài nguyên đầu vào |
| Run metadata | Build ID, thời gian, kết quả, thông tin tái truy vấn |
| Signature/identity | Chứng cứ người/workload ký và chính sách xác thực |
| Link tới evidence | SBOM, test/scan reports và bản ghi phê duyệt được ràng buộc digest |

Ví dụ **đối tượng giải thích ý nghĩa**, không đại diện chính xác cho schema SLSA/in-toto có thể đưa thẳng vào bộ verify:

~~~json
{
  "subject": {
    "name": "registry.example/catalog-service",
    "digest": "sha256:<actual-artifact-digest>"
  },
  "source": {
    "repository": "git.example/team/catalog-service",
    "revision": "8fa12cd..."
  },
  "builder": {
    "identity": "ci.example/workflows/catalog-build",
    "runId": "1842",
    "toolchain": "JDK-21-and-pinned-Gradle"
  },
  "inputs": {
    "baseImageDigest": "sha256:<base-image-digest>",
    "dependencyLock": "gradle.lockfile@<git-revision>"
  },
  "evidence": {
    "sbom": "reference-to-attached-sbom",
    "tests": "reference-to-test-report"
  }
}
~~~

Không tự động cho rằng JSON như trên đáng tin. Một người có thể viết một file “provenance” bất kỳ. Giá trị chứng cứ xuất hiện khi định dạng được kiểm chứng, chữ ký/danh tính hợp lệ, dữ liệu được hệ thống build có trách nhiệm phát hành, và subject digest khớp với artifact sẽ deploy.

**Không ghi secret vào provenance.** Build arguments, environment variables, URI riêng tư và log có thể chứa dữ liệu nhạy cảm. Chỉ ghi metadata tối thiểu cần cho kiểm chứng và giữ bản nội bộ phù hợp quyền truy cập. Hash của secret cũng có thể tiết lộ thông tin khi không gian giá trị nhỏ; tránh đưa secret vào danh sách material.

## 9. Tin cậy provenance và kiểm chứng chữ ký

Quá trình verify cần phân biệt bốn câu hỏi:

1. **Integrity:** digest của artifact hoặc attestation có khớp với bản đang sử dụng?
2. **Authenticity:** chữ ký có xác nhận danh tính builder/key/workload được tin cậy?
3. **Authorization:** danh tính đó có quyền build và phát hành *dịch vụ này* từ *repository/branch/workflow này*?
4. **Policy compliance:** commit, dependency, kết quả scan và loại pipeline có đáp ứng yêu cầu môi trường?

Một chữ ký hợp lệ bởi một tài khoản không nằm trong allowlist **không đủ**. Một attestation hợp lệ cho digest A cũng không dùng để phát hành digest B. Khi dùng ký dựa trên danh tính ngắn hạn như OIDC, phải xác nhận issuer và identity claims theo chính sách; không chấp nhận mọi tài khoản thuộc cùng nhà cung cấp CI.

Các lựa chọn công nghệ thường gặp:
- **Sigstore/Cosign:** hỗ trợ ký và xác minh OCI artifact/attestation bằng key hoặc identity; cần cấu hình trust root và policy.
- **in-toto/DSSE:** bao gói attestation, giúp ràng buộc dữ liệu được ký với loại nội dung.
- **SLSA provenance:** định dạng và mô hình đánh giá độ tin cậy quá trình build, không thay thế chính sách vận hành của từng tổ chức.
- **OCI artifacts/referrers:** cách gắn các chứng cứ đi kèm image trong hệ sinh thái OCI.

Không phải mọi registry và pipeline đều hỗ trợ các cơ chế như nhau. Cần kiểm thử khả năng publish, truy vấn, duy trì và verify attestation khi image được sao chép sang registry khác. **Không nên suy ra SLSA level cụ thể chỉ từ việc có file provenance hoặc chữ ký.** Mức bảo đảm còn phụ thuộc tính cô lập và tính chống giả mạo của builder.

### Ví dụ chính sách phát hành

Một quy tắc production có thể yêu cầu:

~~~text
ALLOW DEPLOY when
  artifact_digest == verified_subject_digest
  AND provenance_signature_is_valid
  AND builder_identity IN approved_builder_identities
  AND source_repository == approved_service_repository
  AND source_revision_is_allowed
  AND required_tests_passed_for_this_digest
  AND critical_security_policy_is_satisfied
  AND deployment_target_is_authorized
ELSE DENY
~~~

Đây là **pseudocode chính sách**. Việc triển khai cần xác định cách đánh giá dữ liệu ký, nguồn test đáng tin, trạng thái của vulnerability database, ngoại lệ có thời hạn và hành vi khi hệ thống xác minh tạm thời không sẵn sàng. Ở production, mặc định nên chặn khi không kiểm chứng được, trừ khi tổ chức có cơ chế xử lý sự cố/ngoại lệ được cấp quyền và lưu vết.

## 10. SBOM, provenance và kết quả scan là ba loại chứng cứ khác nhau

**SBOM (Software Bill of Materials)** liệt kê thành phần của artifact, có thể được xuất ở dạng SPDX hoặc CycloneDX. Nó giúp trả lời: “Image catalog-service chứa thư viện nào, phiên bản nào?” SBOM không tự giải thích ai đã build hoặc có phải bản được phê duyệt.

**Provenance** trả lời: “Image này được tạo từ revision và builder nào?” Nó không tự khẳng định toàn bộ dependency đều an toàn.

**Scan report** ghi kết quả đối chiếu dependency/image với tiêu chí bảo mật hoặc chính sách; trạng thái scan có thể thay đổi khi phát hiện lỗ hổng mới. Scan thành công hôm qua không bảo đảm hôm nay artifact vẫn đáp ứng chính sách.

Một thiết kế tốt gắn cả ba với cùng digest, để:
- Truy vết dịch vụ production đang bị ảnh hưởng khi có CVE mới.
- Đối chiếu bản đã triển khai với source commit và build run.
- Tránh sử dụng kết quả scan của digest khác chỉ vì hai image có cùng tag.
- Kích hoạt rebuild/chỉnh sửa khi có lỗ hổng mới, rồi phát hành một digest mới, không ghi đè digest cũ.

Một SBOM do build tooling tạo có thể không bao phủ đầy đủ cả OS package, native binary hoặc dependency được tải động lúc runtime. Cần xác định phạm vi SBOM và kết hợp các phương pháp phát hiện phù hợp; không coi danh sách package là bảo đảm tuyệt đối.

## 11. Build xác định, tái lập và các nguồn sai khác

Một nhóm muốn kiểm chứng độc lập có thể rebuild cùng source và so sánh digest đầu ra. Để khả thi, cần kiểm soát tính xác định của build:

| Nguồn không xác định | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Timestamp trong archive/manifest | JAR khác hash dù cùng source | Cấu hình reproducible archives và chuẩn hóa timestamp hợp lệ |
| File order không ổn định | ZIP/JAR khác byte | Sắp xếp entry và ổn định thứ tự inputs |
| Dependency động | Build sau kéo thư viện mới | Lock dependency; verify checksum |
| Base image theo tag | Nội dung runtime thay đổi | Pin digest và chủ động cập nhật |
| Plugin/toolchain tự nâng cấp | Compiler/packager khác phiên bản | Pin version và nguồn phân phối |
| Locale/time zone của runner | Output sinh mã, tài liệu hoặc test khác | Cố định locale/time zone khi có ảnh hưởng |
| Random seed/build path | Kết quả chứa giá trị không ổn định | Khử dữ liệu môi trường khỏi artifact hoặc quản lý seed |
| Thời điểm tải input ngoài | Resource khác giữa hai lần build | Vendor/cache và xác định checksum đầu vào |

Với Gradle có thể cấu hình reproducible archive cho task liên quan; ví dụ Groovy DSL mang tính minh họa:

~~~groovy
tasks.withType(AbstractArchiveTask).configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Cú pháp cụ thể có thể phụ thuộc phiên bản Gradle và loại task, nên kiểm tra trong project thực tế. Ngay cả khi JAR reproducible, OCI image vẫn có thể khác hash do manifest metadata, layer ordering, builder hoặc base image. Cần xác định **đơn vị nào** đang so sánh: JAR byte, image manifest hay image index.

Một build không tái lập được vẫn có thể phát hành an toàn nếu artifact cuối được kiểm chứng và giữ bất biến. Tuy nhiên sai khác không giải thích được làm giảm khả năng đối chứng độc lập, nên nên theo dõi và khắc phục dần.

## 12. Bảo vệ chuỗi cung ứng trước các kịch bản tấn công

### Kịch bản A: Tag bị ghi đè sau khi test

CI test `catalog:release` lúc 10:00. Lúc 11:00, kẻ có quyền push thay nội dung tag. CD chạy lúc 12:00 kéo `catalog:release` và triển khai byte chưa từng test.

**Cách giảm rủi ro:** release gate ràng buộc test/attestation với digest; CD deploy theo digest; registry cấm ghi đè tag phát hành và giới hạn quyền push.

### Kịch bản B: Artifact được ký bởi builder không hợp lệ

Một pipeline trong fork build image chứa mã độc và tự ký bằng key mà hệ thống verify vô tình tin cậy. Signature hợp lệ về mặt mật mã nhưng nguồn không được phép.

**Cách giảm rủi ro:** allowlist builder identity, repository, branch/ref và workflow identity; bảo vệ quy trình CI cấp quyền; xác minh subject digest và nguồn trigger.

### Kịch bản C: Dependency đầu vào bị thay

Pipeline dùng dependency động hoặc script tải từ URL không pin. Một build chạy lại cùng commit nhận mã khác.

**Cách giảm rủi ro:** khóa dependency, verify checksum, pin external action/tooling theo commit/digest, giữ nguồn binary được tin cậy. Provenance ghi nhận dependencies thực tế được resolve để hỗ trợ điều tra.

### Kịch bản D: CD tự build lại cho production

Staging đã test image A. Production build lại từ cùng branch và nhận image B do base image mới. Team tưởng đang promote bản đã duyệt.

**Cách giảm rủi ro:** pipeline promotion chỉ đọc digest A từ registry, verify A và deploy đúng A; từ chối bước rebuild trong CD.

### Kịch bản E: Có provenance nhưng nguồn tạo provenance đã bị chiếm quyền

Nếu runner bị chiếm quyền, attacker có thể tạo artifact và attestation hợp lệ theo danh tính runner đó. Có chữ ký không đồng nghĩa xây dựng từ môi trường không thể bị xâm nhập.

**Cách giảm rủi ro:** runner cô lập, ephemeral khi có thể, quyền tối thiểu, secret ngắn hạn, kiểm soát workflow, theo dõi thay đổi CI config, chính sách phê duyệt, khả năng kiểm chứng độc lập khi cần. Mức bảo đảm provenance phụ thuộc vào bảo mật của builder.

## 13. Release manifest và kiểm soát qua GitOps

Một release record có thể được viết và review như một thay đổi GitOps:

~~~yaml
service: catalog-service
environment: production
release:
  version: "1.8.3"
  gitRevision: "8fa12cd..."
  image: "registry.example/catalog-service@sha256:<approved-digest>"
  provenance: "attestation-for-approved-digest"
  sbom: "sbom-for-approved-digest"
  buildRun: "catalog-build/1842"
rollout:
  strategy: canary
  pauseOnSloRegression: true
~~~

YAML chỉ là **dữ liệu minh họa**, không phải Kubernetes Deployment manifest hợp lệ. Hệ thống GitOps chuyển cấu hình đã được review thành workload spec và cần xác nhận trên cluster rằng image đang chạy khớp digest dự kiến.

Tách rành mạch:
- **Build record:** xác nhận artifact từ đâu tới.
- **Release decision:** xác nhận ai/điều gì cho phép triển khai digest đó.
- **Deployment record:** xác nhận môi trường thực sự chạy digest nào.
- **Runtime evidence:** xác nhận release vận hành như mong đợi.

Trong Kubernetes, deployment theo image digest cùng với admission policy có thể ngăn image chưa được phê duyệt. Cũng cần xử lý sidecar, init container, admission mutation và image mirror để biết chính xác các thành phần runtime. Ghi metadata bằng annotations/labels hữu ích cho quan sát, nhưng nhãn không thay thế kiểm chứng digest và attestation.

## 14. Promote, rollback và thời hạn lưu artifact

Chiến lược promote thường vận hành như sau:
1. Dev/integration xác nhận artifact digest X cùng chứng cứ kiểm thử.
2. Staging triển khai X, chạy smoke và test nghiệp vụ.
3. Production verify lại X và provenance; canary một phần traffic.
4. Khi tín hiệu đạt điều kiện, mở rộng traffic mà vẫn dùng X.
5. Nếu cần quay lại, triển khai lại digest Y đã được lưu và phê duyệt trước đó.

Khi rollback, **không rebuild lại version cũ** bằng source cũ vì kết quả có thể khác Y. Hãy sử dụng artifact Y đã lưu, kiểm tra chữ ký/provenance và tương thích với schema dữ liệu hiện tại. Một rollback image không phục hồi tự động migration phá hủy, sự kiện đã phát hay tác động bên ngoài. Có thể cần roll forward hoặc tắt feature flag.

Chính sách retention nên bao gồm:
- Các digest đang chạy ở mọi môi trường quan trọng.
- Một tập bản ổn định gần nhất đủ cho rollback.
- Artifact/attestation dùng cho điều tra và yêu cầu kiểm toán.
- Metadata mapping từ bản phát hành sang chứng cứ.
- Quy trình thu hồi và gỡ artifact bị xác định là độc hại.

Nếu sao chép image sang registry khác, digest manifest thường có thể giữ nguyên khi các byte và cấu trúc không đổi, nhưng không nên giả định mọi công cụ copy giữ nguyên manifest, signature hoặc attestation. Hãy **verify lại** sau khi mirror/promote.

## 15. Thiết kế phân quyền và ranh giới trách nhiệm

| Vai trò | Có thể thực hiện | Không nên được cấp mặc định |
| --- | --- | --- |
| Developer | Thay đổi mã, đề xuất PR, xem build evidence | Ghi đè artifact release hoặc deploy thẳng production |
| CI build identity | Checkout nguồn được phép, build, test, push artifact, phát hành attestation | Sửa policy production hoặc xóa các release đã chốt |
| CD identity | Đọc artifact, verify policy, deploy digest đã duyệt | Chỉnh source/provenance hoặc tự build lại |
| Security/platform | Quản lý trust policy, registry, secret/identity và audit | Sửa mã nghiệp vụ âm thầm |
| Service owner | Chịu trách nhiệm chất lượng, rollout, SLO và sự cố | Bỏ qua gate bắt buộc khi không có quy trình ngoại lệ |

Các quyền cụ thể tùy nền tảng nhưng nguyên tắc chung là **tách quyền xây dựng, xác nhận và triển khai** ở mức phù hợp rủi ro. Khi dùng CI runner chung cho nhiều service, cần đảm bảo credential của catalog không có quyền publish hoặc deploy order-service.

Ghi dấu vết đầy đủ khi dùng quyền override. Một emergency release có thể cần luồng nhanh, nhưng vẫn phải xác định digest, owner, lý do, thời hạn ngoại lệ và kế hoạch kiểm chứng bổ sung.

## 16. Lộ trình triển khai từng bước

**Giai đoạn 1 — Nhìn thấy đúng artifact:** mọi build sinh commit SHA, build ID và digest; CD deploy theo digest; release history lưu digest đang chạy.

**Giai đoạn 2 — Ổn định đầu vào:** pin base image và toolchain, khóa dependency, chuẩn hóa archive, triển khai retention và rollback theo digest.

**Giai đoạn 3 — Thêm chứng cứ:** tạo SBOM, scan report, provenance attestation; liên kết tất cả với subject digest; bật ký và kiểm tra chữ ký ở staging.

**Giai đoạn 4 — Chặn phát hành không hợp lệ:** đưa verify vào production deployment/admission; ràng buộc builder identity, source, workflow, test results và quyền phê duyệt.

**Giai đoạn 5 — Vận hành liên tục:** đánh giá khả năng khôi phục, kiểm tra trust root, tình huống thất lạc attestation, các image đã mirror; rà soát policy khi có chuỗi cung ứng hoặc builder mới.

Không nên triển khai policy ở production trước khi biết pipeline hiện tại xuất đầy đủ dữ liệu verify và có quy trình khắc phục trường hợp bị chặn. Việc rollout enforcement nên có môi trường thử và mức quan sát rõ ràng.

## 17. Chỉ số để xác nhận giải pháp hoạt động

Một số câu hỏi đo được:

- Bao nhiêu phần trăm deployment production tham chiếu **digest** thay vì tag?
- Bao nhiêu artifact có provenance/attestation và SBOM ràng buộc đúng digest?
- Bao nhiêu release được kiểm tra builder identity và source revision trước deploy?
- Có deployment nào chạy digest không nằm trong release record?
- Có thể truy từ pod/container production về commit, build run và kết quả test trong bao lâu?
- Một lần rollback có lấy lại chính artifact đã phê duyệt trước đó không?
- Có bao nhiêu lần policy chặn được artifact sai nguồn, thiếu chứng cứ hoặc sai digest?
- Tỷ lệ build cùng source và đầu vào cho ra digest giống nhau là bao nhiêu trong phạm vi kiểm thử tái lập?

Đừng tối ưu chỉ để tăng số lượng attestation. Chất lượng đến từ việc chứng cứ được tạo ở builder đáng tin, gắn đúng subject và được verify tại điểm có thể ngăn một deployment rủi ro.

## 18. Bài tập thực hành

Giả sử hệ thống có `catalog-service`, `checkout-service` và `payment-service`. Pipeline của catalog hiện dùng `catalog:latest` để deploy, staging build từ branch `main`, production build lại từ `main`, và báo cáo test chỉ ghi “catalog build succeeded”.

**Yêu cầu:**
1. Vẽ lại pipeline để mỗi commit tạo đúng một image bất biến và capture image digest sau khi publish.
2. Đề xuất các trường bắt buộc của build provenance, tối thiểu gồm subject digest, commit, builder identity, build run và input cơ bản.
3. Phân biệt SBOM với provenance và xác định chỗ lưu/đối chiếu từng loại.
4. Thiết kế release gate từ chối artifact có digest không khớp subject, ký sai danh tính hoặc source ngoài allowlist.
5. Viết một release manifest staging/production dùng **cùng digest** và hai bản ghi deployment riêng.
6. Mô tả phương án rollback khi image trước vẫn tồn tại nhưng cơ sở dữ liệu đã thực hiện migration không đảo ngược.

**Tình huống bổ sung:** ngày hôm sau, một build khác từ cùng commit sinh digest mới. Hãy chỉ ra những input có thể gây khác biệt và cách điều tra. Không suy luận “có mã độc” chỉ vì digest khác: cần kiểm tra toolchain, base image, dependency và metadata archive trước khi kết luận.

Một kết quả đạt yêu cầu phải cho thấy chuỗi truy vết đầy đủ `commit → build-run → digest → attestation → release decision → deployed digest` và giải thích được vì sao promotion bằng digest loại bỏ rủi ro build lại giữa staging và production.

## 19. Ghi nhớ

- **Version/tag là nhãn; digest xác định nội dung artifact.** Release phải liên kết với digest.
- **Build một lần, promote cùng artifact** để môi trường kiểm thử và production dùng đúng các byte đã chấp thuận.
- **Provenance ghi nguồn gốc và quy trình build**, còn SBOM ghi thành phần; chữ ký và verify policy khiến chứng cứ có giá trị.
- **Builder identity, source revision và subject digest** phải được đối chiếu cùng nhau. Chữ ký hợp lệ của sai builder không đủ để cho phép phát hành.
- **Tái lập được là mục tiêu bổ sung**, khác với việc giữ artifact bất biến sau khi tạo.
- **Rollback cần artifact cũ còn tồn tại và dữ liệu còn tương thích**; không xem rebuild lại tag cũ là rollback.
- Sự tự chủ của từng microservice mạnh hơn khi mỗi nhóm có pipeline riêng nhưng cùng sử dụng chuẩn supply-chain security và release evidence đáng tin.
