# Xác định đầu vào cần ghim và dữ liệu cần ghi nhận

## 1. Build tái lập là gì và vì sao cần quan tâm?

Một lần build nhận mã nguồn, dependency, công cụ, cấu hình và môi trường thực thi rồi tạo ra artifact. Nếu cùng một commit được build vào hai thời điểm khác nhau nhưng đầu ra thay đổi vì phiên bản thư viện, compiler, image nền hoặc một giá trị môi trường không được kiểm soát, nhóm khó giải thích chính xác artifact được tạo ra từ những gì.

Build tái lập (reproducible build) hướng đến khả năng tạo lại cùng một artifact từ cùng mã nguồn và cùng tập đầu vào đã xác định. Với định nghĩa nghiêm ngặt, hai lần build độc lập tạo ra đầu ra giống nhau từng byte, có thể so sánh bằng checksum như SHA-256. Trong một số hệ thống, người ta dùng “repeatable build” theo nghĩa rộng hơn: cùng đầu vào tạo ra kết quả chức năng tương đương, dù file đầu ra có thể khác metadata hoặc timestamp. Khi nói về reproducible build ở mức byte, cần loại bỏ cả những khác biệt tưởng như vô hại trong gói build.

Khả năng tái lập có giá trị trực tiếp với CI/CD:

- **Truy vết:** xác định artifact đến từ commit, dependency và toolchain nào.
- **Điều tra sự cố:** build lại một revision cũ để kiểm tra lỗi hoặc xác minh bản vá.
- **Tin cậy chuỗi cung ứng:** phát hiện đầu ra bị thay đổi ngoài dự kiến hoặc build bị can thiệp.
- **Kiểm toán:** cung cấp bằng chứng về nguồn gốc và quy trình tạo artifact.
- **Phát hành nhất quán:** kiểm thử một artifact rồi promote chính artifact đó qua các môi trường.
- **Giảm phụ thuộc môi trường cá nhân:** tránh tình trạng máy lập trình viên build được nhưng runner CI tạo đầu ra khác.

Ghim đầu vào (pinning) và ghi nhận metadata (provenance) là hai phần bổ trợ nhau. Ghim đầu vào giúp lần build sử dụng đúng phiên bản đã chọn. Ghi nhận metadata cho biết thực tế lần build đã dùng gì và tạo ra đầu ra nào. Chỉ ghi “JDK 21” mà không biết bản phân phối, bản vá và image chứa JDK đó có thể chưa đủ để tái hiện chính xác.

## 2. Phân biệt đầu vào được ghim và dữ liệu provenance

Hai khái niệm thường bị gộp làm một nhưng phục vụ mục đích khác nhau:

| Khái niệm | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| Đầu vào được ghim (pinned inputs) | Lần build được phép sử dụng chính xác những thành phần nào? | Commit SHA, lockfile, JDK version, compiler version, image digest |
| Dữ liệu provenance | Lần build thực tế đã chạy với những đầu vào và điều kiện nào? | Run ID, commit thực tế, builder image digest, lệnh build, artifact SHA-256 |
| Kết quả xác minh | Có bằng chứng nào cho thấy đầu ra đáp ứng yêu cầu? | Test report, checksum so sánh giữa hai lần build, chữ ký/attestation |

Ví dụ, file cấu hình khai báo image `builder:21` chưa chắc đã pin được môi trường vì tag đó có thể được cập nhật. Provenance ghi lại digest thực tế của image giúp biết lần build đã chạy trên image nào. Tương tự, lockfile thể hiện dependency được khóa; build metadata nên ghi lại các dependency thực tế đã được phân giải và nguồn lấy chúng nếu công cụ hỗ trợ.

Không phải mọi giá trị quan sát được đều cần trở thành đầu vào cố định. Run ID và thời điểm chạy thay đổi theo từng lần build, nhưng vẫn cần được ghi nhận. Ngược lại, phiên bản compiler có thể ảnh hưởng trực tiếp đến bytecode và phải được ghim. Hãy phân biệt giá trị cần cố định để tái lập với giá trị cần lưu để truy vết.

## 3. Lập danh mục đầu vào ảnh hưởng đến build

Trước khi ghim, cần liệt kê những gì có thể làm thay đổi đầu ra. Một danh mục thực tế có thể chia thành các nhóm sau:

| Nhóm đầu vào | Những giá trị cần xem xét | Cách ghim hoặc kiểm soát |
|---|---|---|
| Mã nguồn | Commit, submodule, Git LFS object, generated source | Commit SHA; ghi nhận revision của submodule và object ID |
| Dependency | Thư viện trực tiếp/gián tiếp, package, plugin | Lockfile, phiên bản cụ thể, checksum/signature, repository tin cậy |
| Toolchain | Compiler, JDK, runtime, linker, package manager, build tool | Phiên bản cụ thể, wrapper có checksum, image hoặc package bất biến |
| Builder image | Base image, OS package, công cụ cài thêm | Image digest, snapshot repository hoặc image được quản lý phiên bản |
| Nền tảng thực thi | OS, kiến trúc CPU, libc, kernel hoặc runner | Ghi nhận phiên bản; cố định các thuộc tính có ảnh hưởng đến đầu ra |
| Cấu hình build | Build flags, profile, feature flags, tham số, biến môi trường | Lưu trong version control hoặc ghi rõ trong invocation metadata |
| Dữ liệu sinh mã | Schema, API definition, compiler/plugin sinh mã, asset | Ghim revision và phiên bản công cụ sinh mã |
| Tài nguyên bên ngoài | Package repository, URL tải binary, dữ liệu từ mạng | Mirror/snapshot, checksum, nguồn được allowlist hoặc chế độ offline |
| Thời gian và tính ngẫu nhiên | Timestamp, timezone, random seed, thứ tự file | Chuẩn hóa thời gian, seed và thuật toán sắp xếp khi phù hợp |
| Đóng gói | Phiên bản archiver, thứ tự entry, metadata file | Pin công cụ, chuẩn hóa metadata và cấu trúc gói |

Không phải dự án nào cũng cần ghim mọi thuộc tính ở mức hệ điều hành hoặc phần cứng. Hãy xác định thuộc tính nào thực sự ảnh hưởng đến đầu ra và mức độ tái lập mong muốn. Ví dụ, một ứng dụng Java thuần có thể không cần cố định từng chi tiết kernel để tái tạo JAR, nhưng một dự án native compile có thể phụ thuộc mạnh vào compiler, linker, libc và kiến trúc CPU.

## 4. Ghim mã nguồn bằng revision bất biến

Không nên dùng tên nhánh như `main`, `develop` hoặc tên tag có thể bị di chuyển làm định danh duy nhất của mã nguồn đã build. Nhánh thay đổi theo thời gian. Một tag có thể bị xóa hoặc tạo lại nếu kho không bảo vệ tính bất biến.

Các thực hành nên dùng:

- Ghi commit SHA đầy đủ của revision đã checkout.
- Lưu repository URL hoặc định danh repository, cùng trạng thái checkout.
- Ghi nhận submodule commit cho từng đường dẫn nếu dự án sử dụng Git submodule.
- Ghi object ID của Git LFS hoặc dữ liệu nguồn ngoài được tải về.
- Với source archive, lưu checksum của archive và nguồn phát hành.
- Tránh sửa mã nguồn sau checkout bằng thao tác thủ công không được ghi nhận.
- Nếu build cần patch được áp dụng trong pipeline, lưu patch trong version control hoặc ghi checksum và nội dung tham chiếu có thể truy xuất.

Ví dụ metadata:

```yaml
source:
  repository: https://example.com/platform/order-service.git
  revision: 8d3f2a1c...full-commit-sha
  submodules:
    shared-contracts: 4b71e9...
```

Đây là YAML minh họa; các giá trị SHA và địa chỉ cần được thay bằng dữ liệu thật. Với pull request, cần xác định rõ build đang kiểm tra commit của nhánh nguồn, merge commit tạm hay revision đã được hợp nhất. Ghi nhận revision thực tế mà runner checkout, không chỉ ghi mã pull request.

## 5. Ghim dependency trực tiếp và gián tiếp

Dependency không chỉ gồm thư viện được khai báo trực tiếp. Build tool có thể tải thêm dependency bắc cầu, plugin, compiler extension hoặc package hệ thống. Nếu chỉ ghim dependency trực tiếp, một dependency gián tiếp có thể được cập nhật và làm thay đổi đầu ra.

Các nguyên tắc quan trọng:

1. Dùng lockfile hoặc cơ chế dependency locking để ghi lại phiên bản đã phân giải, bao gồm dependency bắc cầu khi công cụ hỗ trợ.
2. Tránh phiên bản động như `latest`, `1.+`, `^1.2` hoặc version range nếu mục tiêu là tạo đầu vào cố định. Một số hệ sinh thái dùng range để quản lý tương thích, nhưng cần khóa kết quả phân giải trước khi build phát hành.
3. Dùng checksum hoặc chữ ký để xác minh package tải về đúng nội dung đã được chấp nhận.
4. Kiểm soát repository/mirror được phép cung cấp dependency; tránh tải cùng một tọa độ package từ nguồn không xác định.
5. Ghim phiên bản plugin build và plugin sinh mã giống như dependency ứng dụng.
6. Lưu lockfile trong version control và review thay đổi dependency như thay đổi mã nguồn.
7. Có quy trình cập nhật lockfile, chạy test và phát hành bản cập nhật có chủ đích.

Với Gradle, dự án có thể sử dụng dependency locking và dependency verification. Ví dụ cấu hình khái niệm:

```kotlin
dependencyLocking {
    lockAllConfigurations()
}
```

Locking lưu kết quả phân giải dependency theo cấu hình của dự án; dependency verification có thể xác minh checksum hoặc chữ ký của artifact theo metadata đã tin cậy. Dự án cần tạo và review lock state/verification metadata theo hướng dẫn Gradle tương ứng. Chỉ thêm đoạn cấu hình trên không tự tạo ra đầy đủ lockfile cho mọi configuration.

Với Maven, cần khai báo phiên bản cụ thể cho dependency và plugin, tránh version range trong build phát hành và kiểm soát repository. Maven không tự cung cấp một lockfile chuẩn tương đương cho toàn bộ dependency graph trong mọi dự án; có thể cần công cụ hoặc quy trình bổ sung để lưu kết quả phân giải và xác minh checksum.

## 6. Ghim build tool và toolchain

Build tool và toolchain có thể ảnh hưởng trực tiếp đến bytecode, native binary, archive và metadata. Cần xác định rõ:

- Phiên bản JDK/runtime dùng để chạy build tool.
- Phiên bản compiler và target/release level.
- Phiên bản Gradle/Maven hoặc công cụ build tương ứng.
- Phiên bản plugin, annotation processor, code generator và linker.
- Phiên bản package manager và cách phân giải dependency.
- Các công cụ đóng gói, nén, ký hoặc tạo metadata.

Với Gradle, Gradle Wrapper giúp repository chỉ định phiên bản Gradle. File `gradle-wrapper.properties` có thể khai báo URL phân phối và checksum:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.10.2-bin.zip
distributionSha256Sum=<expected-sha256>
```

Giá trị checksum là placeholder trong ví dụ; phải lấy từ nguồn phát hành đáng tin cậy và xác minh trước khi dùng. Wrapper không tự ghim JDK chạy Gradle; cần quản lý JDK riêng bằng toolchain hoặc image runner đã pin.

Ví dụ Dockerfile minh họa ghim base image bằng digest:

```dockerfile
FROM eclipse-temurin:21-jdk@sha256:<image-digest>
WORKDIR /workspace
```

Tag `21-jdk` giúp con người đọc phiên bản dự kiến; digest xác định nội dung image. Digest cần được cập nhật có chủ đích khi vá bảo mật hoặc nâng cấp hệ thống.

## 7. Ghim môi trường builder và nền tảng thực thi

Hai lần build cùng mã nguồn có thể khác nhau nếu chạy trên image runner khác nhau. Một image mới có thể chứa phiên bản khác của shell, libc, CA certificates, package hệ thống hoặc công cụ nén.

Nên quản lý:

- Builder image theo digest hoặc bản phát hành bất biến.
- Kiến trúc CPU (ví dụ x86_64/ARM64) nếu ảnh hưởng đến binary.
- Phiên bản OS và package hệ thống cần thiết.
- Runtime và thư viện native được dùng trong quá trình build.
- Locale, timezone, encoding và cấu hình umask.
- Đường dẫn build nếu compiler đưa đường dẫn tuyệt đối vào debug information.
- Cấu hình mạng, proxy và nguồn package repository.

Ghim toàn bộ image runner bằng digest giúp môi trường ổn định, nhưng image cũng cần được cập nhật khi có bản vá bảo mật. Không nên giữ một image cũ vô thời hạn chỉ để duy trì tái lập. Hãy phát hành phiên bản image mới, kiểm thử và nâng cấp có kiểm soát; lưu digest cũ trong provenance để có thể tái tạo build lịch sử khi cần.

Với native build, nên cân nhắc cố định cả kiến trúc, compiler, linker, sysroot và phiên bản libc. Với Java, JAR có thể ít phụ thuộc kernel hơn nhưng vẫn chịu ảnh hưởng của JDK, build tool, plugin, dependency và metadata đóng gói.

## 8. Kiểm soát biến môi trường và tham số build

Build script thường đọc các biến môi trường mà không khai báo rõ trong file cấu hình. Một biến như `TZ`, `LANG`, `JAVA_TOOL_OPTIONS`, `PATH`, `HOME` hoặc feature flag có thể thay đổi kết quả.

Nên:

- Liệt kê biến môi trường có ảnh hưởng đến build.
- Đặt giá trị tường minh cho locale, timezone và encoding nếu chúng ảnh hưởng đến đầu ra.
- Ghi các tham số dòng lệnh và build profile đã dùng.
- Kiểm soát `PATH` để không vô tình gọi công cụ khác phiên bản.
- Tách biến cấu hình thông thường khỏi secret.
- Không ghi giá trị secret, token hoặc credential vào provenance, log hay file build metadata.
- Nếu build cần bí mật để tải dependency riêng tư, ghi định danh nguồn và phiên bản secret nếu hệ thống hỗ trợ, không ghi nội dung bí mật.

Ví dụ thiết lập môi trường có tính xác định hơn:

```bash
export TZ=UTC
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
export SOURCE_DATE_EPOCH="$COMMIT_TIMESTAMP"
./gradlew --no-daemon clean build
```

`SOURCE_DATE_EPOCH` là quy ước được một số công cụ hỗ trợ để chuẩn hóa timestamp đầu ra; không phải mọi build tool đều tự động sử dụng biến này. `COMMIT_TIMESTAMP` phải được lấy từ revision đã xác định và chuyển đổi theo định dạng epoch hợp lệ. Cần kiểm tra từng công cụ đóng gói và plugin để biết nó có tôn trọng biến này hay không.

Không nên ghi toàn bộ `env` ra log để điều tra. Môi trường có thể chứa token và secret. Hãy dùng allowlist các biến không nhạy cảm cần ghi nhận, đồng thời che hoặc loại bỏ giá trị nhạy cảm.

## 9. Loại bỏ nguồn không xác định: thời gian, ngẫu nhiên và thứ tự

Một build có thể thay đổi dù mã nguồn và dependency không đổi vì các nguồn không xác định (nondeterminism):

- Timestamp hiện tại được nhúng vào file JAR, ZIP hoặc manifest.
- Thứ tự file trong archive phụ thuộc filesystem hoặc thứ tự duyệt thư mục.
- Random seed thay đổi giữa các lần chạy.
- Tên thư mục tạm hoặc đường dẫn tuyệt đối được ghi vào debug symbols.
- Locale/timezone làm thay đổi định dạng ngày, số hoặc sắp xếp chuỗi.
- Build song song làm thứ tự sinh file hoặc gộp resource không ổn định.
- Công cụ lấy dữ liệu trực tiếp từ mạng hoặc API thay đổi theo thời gian.
- Chữ ký hoặc metadata đóng gói chứa timestamp và dữ liệu phiên chạy.

Các cách xử lý:

1. Dùng timestamp cố định từ source revision hoặc một giá trị được định nghĩa rõ thay vì thời gian hiện tại.
2. Sắp xếp danh sách file trước khi đóng gói và dùng chế độ archive deterministic nếu công cụ hỗ trợ.
3. Đặt random seed cố định cho bước sinh dữ liệu cần tái lập; không dùng seed cố định nếu mục tiêu nghiệp vụ cần tính ngẫu nhiên thực sự trong runtime.
4. Chuẩn hóa locale, timezone và encoding.
5. Dùng compiler flag để ánh xạ hoặc loại bỏ đường dẫn build không ổn định nếu phù hợp.
6. Tải dữ liệu ngoài qua snapshot/mirror có phiên bản và checksum.
7. Kiểm tra các plugin, annotation processor và code generator có sinh đầu ra xác định không.

Không phải mọi timestamp trong provenance cần cố định. Thời điểm pipeline chạy là thông tin quan sát và cần ghi nhận thực tế. Điều cần chuẩn hóa là timestamp bị nhúng vào artifact nếu nó làm cho hai lần build từ cùng đầu vào khác byte mà không mang ý nghĩa nội dung.

## 10. Quản lý nguồn dữ liệu bên ngoài và build offline

Một build có thể gọi Internet để tải dependency, schema, binary hoặc dữ liệu tham chiếu. Nếu nguồn bên ngoài thay đổi hoặc không còn truy cập, build cũ có thể không tái lập được.

Các biện pháp:

- Dùng package registry hoặc mirror nội bộ có chính sách lưu giữ rõ.
- Pin phiên bản và checksum của binary tải trực tiếp.
- Lưu snapshot của dữ liệu đầu vào nếu dữ liệu đó ảnh hưởng đến artifact.
- Ghi nguồn, thời điểm lấy và định danh nội dung của dữ liệu ngoài.
- Hạn chế URL trỏ tới file thay đổi liên tục hoặc endpoint trả dữ liệu theo thời điểm.
- Với build yêu cầu độ tái lập cao, tải đủ dependency trước rồi chạy bước build trong môi trường không có mạng.
- Duy trì khả năng truy cập các package đã dùng cho build lịch sử theo chính sách retention.

Build offline giúp phát hiện dependency chưa được khai báo hoặc bước build đang tải tài nguyên ngầm. Tuy nhiên, offline chỉ có ý nghĩa sau khi mọi đầu vào đã được chuẩn bị và xác minh. Nếu bước build cần một dịch vụ ngoài để tạo artifact, cần ghi nhận dịch vụ, phiên bản dữ liệu và kết quả trả về, hoặc thay nó bằng đầu vào snapshot.

## 11. Dữ liệu cần ghi nhận cho mỗi lần build

Provenance cần đủ chi tiết để trả lời artifact được tạo từ đâu, bằng cách nào và trong điều kiện nào. Một tập metadata hữu ích gồm:

| Nhóm | Trường dữ liệu nên ghi nhận | Mục đích |
|---|---|---|
| Định danh lần chạy | Pipeline run ID, job ID, thời điểm bắt đầu/kết thúc | Liên kết log và các bước trong cùng lần build |
| Nguồn mã | Repository, commit SHA, branch/tag tham chiếu, trạng thái checkout | Xác định revision đã build |
| Dependency | Lockfile checksum, dependency graph hoặc danh sách package đã phân giải | Biết thành phần bên ngoài đã tham gia build |
| Toolchain | JDK/compiler, build tool, plugin, package manager và phiên bản | Tái tạo môi trường build |
| Builder | Runner/image digest, OS, kiến trúc, runtime cần thiết | Xác định môi trường thực thi |
| Invocation | Lệnh, tham số, profile và cấu hình build không nhạy cảm | Hiểu cách tạo artifact |
| Environment | Allowlist biến ảnh hưởng, locale, timezone, seed và SOURCE_DATE_EPOCH nếu dùng | Giải thích khác biệt giữa các lần chạy |
| Kết quả | Artifact name, version, size, SHA-256/digest | Xác định chính xác đầu ra |
| Kiểm chứng | Test report, scan result, checksum comparison, quality gate | Chứng minh các điều kiện đã đạt |
| Chuỗi cung ứng | SBOM, provenance attestation, chữ ký và định danh builder | Hỗ trợ xác minh nguồn gốc và tính toàn vẹn |

Không phải mọi trường đều cần ghi trực tiếp trong một file. Có thể lưu metadata trong CI system, artifact repository hoặc attestation liên kết bằng định danh. Điều quan trọng là dữ liệu có thể truy xuất, được bảo vệ khỏi sửa đổi trái phép và có thời hạn lưu trữ phù hợp.

## 12. Ví dụ build metadata

Một file metadata đơn giản có thể có cấu trúc như sau:

```yaml
build:
  run_id: "ci-1042"
  started_at: "2026-11-18T07:00:00Z"
  source:
    repository: "https://example.com/platform/order-service.git"
    commit: "8d3f2a1c..."
  builder:
    image: "registry.example/ci/java-builder@sha256:<digest>"
    os: "linux"
    architecture: "amd64"
    jdk: "21.0.x"
    gradle: "8.10.2"
  dependencies:
    lockfile_sha256: "<sha256>"
    verification_metadata_sha256: "<sha256>"
  invocation:
    command: "./gradlew --no-daemon clean build"
    timezone: "UTC"
    locale: "C.UTF-8"
  outputs:
    - name: "order-service.jar"
      sha256: "<artifact-sha256>"
```

Đây là schema minh họa, không phải định dạng provenance chuẩn bắt buộc. `started_at` thay đổi theo lần chạy nên cần ghi nhận thực tế; nó không phải đầu vào cố định để tái lập. Các placeholder cần được thay bằng dữ liệu thật. Không đưa token, mật khẩu, private key hoặc giá trị secret vào file này.

Với hệ thống cần trao đổi provenance giữa nhiều công cụ, có thể dùng định dạng attestation tiêu chuẩn và liên kết subject với digest của artifact. SBOM mô tả thành phần phần mềm có trong sản phẩm; provenance mô tả cách sản phẩm được tạo ra. Hai loại dữ liệu bổ trợ nhau nhưng không thay thế nhau.

## 13. Kiểm chứng bằng checksum và hai lần build độc lập

Ghim đầu vào là điều kiện cần nhưng chưa chứng minh đầu ra đã tái lập. Cách kiểm chứng trực tiếp là thực hiện hai lần build độc lập với cùng đầu vào đã khai báo, lý tưởng trên hai workspace hoặc runner sạch, rồi so sánh checksum artifact.

Ví dụ:

```bash
sha256sum build-a/order-service.jar
sha256sum build-b/order-service.jar
```

Nếu hai giá trị SHA-256 giống nhau, hai file có cùng nội dung byte với xác suất va chạm cực thấp theo tính chất của SHA-256. Nếu khác nhau, chưa thể kết luận ngay build sai; cần xác định khác biệt đến từ nội dung hay metadata đóng gói.

Quy trình kiểm chứng có thể thực hiện như sau:

1. Chọn commit SHA và ghi lại lockfile, toolchain, builder image digest cùng tham số build.
2. Chạy build A trên workspace sạch, upload artifact và ghi SHA-256.
3. Chạy build B trên runner/workspace độc lập với đúng tập đầu vào đã pin.
4. So sánh digest của artifact.
5. Nếu khác, giải nén hoặc dùng công cụ so sánh binary để xác định file/entry khác nhau.
6. Kiểm tra timestamp, thứ tự archive, đường dẫn, generated file, random seed, dependency hoặc toolchain.
7. Sửa nguồn nondeterminism, sau đó chạy lại hai lần độc lập.
8. Lưu kết quả so sánh cùng provenance để có thể kiểm tra lại.

Không nên so sánh hai artifact đã được ký bằng chữ ký có timestamp hoặc nonce khác nhau rồi kết luận phần mềm không tái lập. Có thể so sánh payload trước khi ký, hoặc dùng cơ chế ký deterministic nếu hệ thống hỗ trợ. Chữ ký và attestation cần được lưu riêng và vẫn phải xác minh được mối liên hệ với digest của payload.

## 14. Liên kết provenance với artifact và phát hành

Một artifact đáng tin cậy cần có liên kết rõ ràng tới nguồn mã và lần build. Tối thiểu nên lưu:

- Tên và phiên bản artifact.
- Digest bất biến của artifact.
- Commit SHA và repository nguồn.
- Pipeline run ID và định danh builder.
- Phiên bản toolchain, dependency lock state và builder image.
- Kết quả test, scan và quality gate.
- Provenance/attestation và chữ ký nếu quy trình yêu cầu.

Sau khi artifact đã được build và kiểm chứng, CD nên promote chính artifact đó qua staging và production. Không build lại từ cùng commit ở từng môi trường vì cấu hình hoặc thời điểm khác nhau có thể tạo ra nội dung khác. Cấu hình môi trường được cung cấp khi triển khai, trong khi payload ứng dụng giữ nguyên digest.

Ví dụ: `order-service.jar` có SHA-256 `abc...` được kiểm thử ở staging. Khi phát hành production, hệ thống tải đúng artifact có digest đó và ghi deployment record trỏ về cùng digest. Nếu production chạy một file được build lại, dù cùng tên và commit, nhóm cần coi đó là một artifact khác cho đến khi chứng minh được nội dung trùng khớp.

## 15. Những đánh đổi khi ghim đầu vào

Ghim mọi thứ có thể làm tăng công sức cập nhật và chi phí lưu trữ. Ghim phiên bản quá cũ có thể giữ lại lỗ hổng bảo mật hoặc lỗi compiler. Không ghim đủ lại khiến build thay đổi ngoài ý muốn.

| Quyết định | Lợi ích | Chi phí/rủi ro | Cách cân bằng |
|---|---|---|---|
| Pin mọi dependency | Kết quả phân giải ổn định | Cần cập nhật lockfile định kỳ | Tự động đề xuất cập nhật, review và test trước khi merge |
| Pin builder image theo digest | Môi trường rõ ràng | Cần nâng digest để nhận bản vá | Có lịch cập nhật image và kiểm thử tương thích |
| Build offline | Phát hiện phụ thuộc mạng ngầm | Cần mirror và chuẩn bị dependency | Tải/verify trước, sau đó chạy build trong mạng giới hạn |
| Pin compiler và plugin | Kiểm soát bytecode/đầu ra | Hạn chế tự động nhận phiên bản mới | Quản lý toolchain như dependency và nâng cấp có chủ đích |
| Chuẩn hóa timestamp | Tăng khả năng so sánh byte | Có thể mất timestamp thực trong artifact | Ghi thời gian thực trong provenance, dùng timestamp chuẩn trong payload |
| Giữ builder cũ để tái tạo lịch sử | Có thể build lại release cũ | Tăng chi phí và rủi ro vận hành | Lưu image digest, mirror package và chỉ duy trì môi trường cũ khi có nhu cầu rõ |

Một chính sách tốt phân loại đầu vào theo mức ảnh hưởng và rủi ro. Dependency và toolchain trực tiếp ảnh hưởng artifact cần ghim chặt. Các thuộc tính ít ảnh hưởng có thể chỉ cần ghi nhận. Secret không được ghim bằng cách lưu giá trị; cần quản lý bằng secret manager, định danh phiên bản hoặc cơ chế credential ngắn hạn.

## 16. Anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Dùng tag `latest` cho builder image | Image thay đổi mà pipeline không đổi | Pin digest và nâng cấp có chủ đích |
| Dùng dependency version động trong release build | Cùng commit có thể tải dependency khác | Lock dependency graph và xác minh checksum |
| Chỉ ghi commit SHA | Không biết compiler, plugin và môi trường đã dùng | Ghi provenance gồm builder, toolchain, dependency và invocation |
| Ghi toàn bộ biến môi trường vào log | Có thể làm lộ secret | Chỉ ghi allowlist biến không nhạy cảm |
| Dùng thời gian hiện tại trong archive | Checksum khác nhau dù payload giống nhau | Chuẩn hóa timestamp hoặc loại metadata biến động |
| Chỉ build một lần rồi tuyên bố tái lập | Chưa có bằng chứng hai lần build cho cùng đầu vào | Chạy hai build độc lập và so sánh digest |
| Dùng cache làm nguồn dependency duy nhất | Cache mất hoặc nhiễm bẩn khiến build không tái hiện được | Có lockfile, registry/mirror và checksum xác minh |
| Build lại ở từng môi trường | Artifact staging và production có thể khác | Promote cùng artifact bất biến qua môi trường |
| Gộp chữ ký vào phép so sánh payload | Timestamp/nonce của chữ ký tạo khác biệt giả | So sánh payload trước ký và xác minh chữ ký riêng |

## 17. Checklist xác định đầu vào và metadata

Trước khi xem một pipeline là có khả năng tái lập, hãy kiểm tra:

- [ ] Revision mã nguồn được xác định bằng commit SHA.
- [ ] Submodule, Git LFS và dữ liệu nguồn ngoài được định danh.
- [ ] Dependency trực tiếp/gián tiếp được khóa và có cơ chế xác minh nội dung.
- [ ] Build tool, plugin, compiler và runtime được ghim phiên bản.
- [ ] Builder image được pin bằng digest hoặc cơ chế bất biến tương đương.
- [ ] Hệ điều hành, kiến trúc và thư viện native ảnh hưởng đến build được ghi nhận.
- [ ] Build flags, profile và biến môi trường liên quan được khai báo rõ.
- [ ] Locale, timezone, timestamp và random seed được kiểm soát khi ảnh hưởng đầu ra.
- [ ] Nguồn dữ liệu ngoài có phiên bản/checksum hoặc snapshot có thể truy xuất.
- [ ] Không dùng secret làm dữ liệu provenance; giá trị nhạy cảm được loại khỏi log.
- [ ] Metadata ghi run ID, commit, builder, toolchain, invocation và artifact digest.
- [ ] Có hai lần build độc lập và so sánh checksum khi yêu cầu mức tái lập byte.
- [ ] Artifact đã kiểm chứng được promote qua môi trường bằng cùng digest.
- [ ] Provenance, SBOM, test report và chữ ký được lưu theo chính sách retention.

## 18. Nguyên tắc thực hành cốt lõi

1. Lập danh mục mọi đầu vào có thể ảnh hưởng đến artifact trước khi thiết kế quy tắc pinning.
2. Ghim revision, dependency, toolchain, builder image và dữ liệu sinh mã bằng định danh bất biến khi có thể.
3. Khóa dependency bắc cầu, xác minh checksum/chữ ký và kiểm soát nguồn package.
4. Chuẩn hóa biến môi trường, timestamp, locale, timezone, thứ tự file và các nguồn ngẫu nhiên.
5. Ghi provenance về nguồn mã, builder, invocation, môi trường, dependency và digest đầu ra.
6. Không ghi secret vào metadata hoặc log; chỉ ghi thông tin không nhạy cảm cần cho truy vết.
7. Kiểm chứng khả năng tái lập bằng hai lần build độc lập và so sánh digest.
8. Gắn provenance với artifact và promote cùng artifact qua các môi trường.
9. Cập nhật đầu vào đã ghim theo quy trình review, kiểm thử và xử lý bản vá bảo mật.

Build tái lập không đến từ một tùy chọn duy nhất trong pipeline. Nó là kết quả của việc xác định đầu vào, loại bỏ nguồn biến động, ghi nhận môi trường thực tế và kiểm chứng đầu ra. Khi các dữ liệu đó được quản lý cùng artifact, nhóm có thể giải thích, xác minh và tái tạo phiên bản phần mềm trong toàn bộ vòng đời CI/CD.
