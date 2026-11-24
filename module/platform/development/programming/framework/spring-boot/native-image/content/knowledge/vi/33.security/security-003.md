# Binary native vẫn cần quản lý lỗ hổng và kiểm tra dependency

## 1. Vì sao native executable vẫn có rủi ro dependency?

GraalVM Native Image tạo executable độc lập với JVM runtime truyền thống, nhưng điều đó không có nghĩa ứng dụng đã loại bỏ mọi dependency hoặc miễn nhiễm với lỗ hổng bảo mật. Binary vẫn chứa mã từ thư viện Java, framework, runtime support và có thể liên kết với thư viện hệ điều hành. Container image còn có base image, CA certificates, native libraries và các file hệ thống khác.

Một lỗ hổng trong Jackson, Spring Framework, HTTP client, database driver hoặc thư viện xử lý ảnh vẫn có thể ảnh hưởng tới native executable nếu phần code dễ bị khai thác được đưa vào binary và có thể truy cập. Tương tự, CVE trong glibc, OpenSSL hoặc thư viện native khác có thể ảnh hưởng nếu executable hoặc image sử dụng thành phần đó.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, cần duy trì quy trình quản lý dependency xuyên suốt từ source, build, native binary đến container image. Bài học này giải thích cách tạo và đọc SBOM, quét dependency Java và thư viện hệ thống, hiểu giới hạn scanner đối với binary native, phân loại CVE, cập nhật/rebuild và đưa kiểm tra vào CI/CD.

## 2. Native Image thay đổi cách đóng gói, không xóa nguồn gốc lỗ hổng

Native compilation có thể loại bỏ một số class không reachable khỏi executable, nhưng không tự động chứng minh dependency còn lại an toàn. Các rủi ro gồm:

- Code dễ bị khai thác vẫn nằm trong reachability graph.
- Lỗ hổng nằm trong một method chỉ được gọi ở payload/branch hiếm.
- Native library được liên kết tĩnh hoặc động có CVE.
- Base image chứa package hệ điều hành dễ bị khai thác.
- Dependency có phiên bản cũ dù JAR đã được chuyển thành binary.
- Metadata hoặc resource bị đóng gói chứa dữ liệu không nên phát hành.
- Build toolchain hoặc builder image có lỗ hổng trong supply chain.

Không thể dùng kích thước binary nhỏ hơn để suy ra bề mặt tấn công đã được loại bỏ tương ứng. Reachability là thuộc tính của build; khả năng khai thác còn phụ thuộc code path, dữ liệu đầu vào, cấu hình và môi trường runtime.

## 3. Phân loại dependency cần theo dõi

Một native service có nhiều lớp dependency:

| Lớp | Ví dụ | Nguồn kiểm tra |
|---|---|---|
| Application dependencies | Jackson, Apache HttpClient, SDK đối tác | Maven/Gradle dependency graph |
| Spring ecosystem | Spring Boot, Spring Framework, Spring Data | BOM/plugin và dependency report |
| Native Image toolchain | GraalVM, Native Build Tools | Builder image/toolchain inventory |
| Native libraries | OpenSSL, zlib, database client library | ELF linkage, package inventory, SBOM |
| OS/runtime packages | glibc, CA certificates, timezone data | Base image package database |
| Build plugins/actions | Maven/Gradle plugins, CI actions | Plugin graph và CI supply chain |
| Generated artifacts | AOT output, metadata, generated source | Build manifest và artifact provenance |

Không chỉ quét file JAR. Nếu final image chứa thư viện native hoặc OS packages, cần scanner có khả năng nhận diện các thành phần đó. Nếu build stage và runtime stage khác nhau, theo dõi cả hai vì chúng có rủi ro và mục đích khác nhau.

## 4. Dependency graph của Maven và Gradle

Trước khi native compile, lưu dependency graph ở dạng có thể kiểm tra.

Với Maven:

```bash
./mvnw dependency:tree
```

Có thể xuất danh sách dependency ở định dạng phù hợp với plugin/reporting tool của dự án. Ghi cả dependency trực tiếp và transitive; nhiều CVE nằm trong thư viện bắc cầu mà source code không khai báo trực tiếp.

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Để xem dependency cụ thể được kéo vào bởi đường nào:

```bash
./gradlew dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
```

Các lệnh này giúp xác định version được resolve, nhưng chưa phải kết quả vulnerability scan. Lưu dependency lock/BOM và report theo commit để so sánh khi nâng cấp.

## 5. Vì sao phải quét cả dependency bắc cầu?

Ứng dụng có thể chỉ khai báo Spring Boot starter, nhưng starter kéo theo nhiều thư viện khác. Một lỗ hổng có thể nằm trong parser, compression library, logging implementation hoặc HTTP client ở tầng transitive.

Khi scanner báo CVE:
1. Xác định artifact coordinates và version thực tế.
2. Xem dependency được kéo vào từ thư viện nào.
3. Kiểm tra version đã resolve trong runtimeClasspath.
4. Xác định artifact có nằm trong native binary hoặc final image không.
5. Kiểm tra feature/code path sử dụng dependency.
6. Đánh giá exploitability và mức độ ảnh hưởng.
7. Nâng dependency/BOM hoặc áp dụng biện pháp giảm thiểu có thời hạn.

Không bỏ qua CVE chỉ vì dependency không được khai báo trực tiếp. Cũng không tự động nâng một transitive library bằng cách override version nếu version đó không tương thích với Spring Boot BOM hoặc dependency sử dụng.

## 6. SBOM là danh mục thành phần của artifact

Software Bill of Materials (SBOM) mô tả các thành phần phần mềm có trong một artifact hoặc tập hợp artifact. SBOM có thể chứa:

- Tên component và version.
- Package URL (PURL) hoặc định danh tương đương.
- Supplier/publisher.
- License.
- Quan hệ dependency.
- Hash hoặc thông tin định danh.
- Metadata về công cụ và thời điểm tạo.

Các định dạng phổ biến gồm SPDX và CycloneDX. Chọn format theo scanner, registry và chính sách tổ chức; bảo đảm consumer có thể đọc và liên kết SBOM với đúng artifact.

SBOM không tự chứng minh artifact an toàn. Nó là inventory đầu vào cho vulnerability analysis, license review và supply-chain tracking. SBOM thiếu component hoặc không gắn với đúng image digest sẽ làm giảm giá trị kiểm soát.

## 7. Tạo SBOM cho dependency Java

Có thể tạo SBOM từ Maven/Gradle project bằng plugin hoặc công cụ chuyên dụng. Ví dụ Maven CycloneDX plugin:

```bash
./mvnw org.cyclonedx:cyclonedx-maven-plugin:makeAggregateBom
```

Ví dụ Gradle CycloneDX plugin:

```bash
./gradlew cyclonedxBom
```

Tên goal/task, version plugin và vị trí output phụ thuộc cấu hình. Pin plugin version trong build và xác nhận file SBOM được tạo đúng. Không dùng phiên bản plugin không được kiểm soát trong CI production.

SBOM từ project dependency graph thường mô tả các package Java đã resolve. Nó có thể không phản ánh đầy đủ thư viện hệ thống được copy vào container, native libraries được link hoặc toolchain trong builder image. Cần bổ sung SBOM/image scan cho container và build environment.

## 8. SBOM của native binary và container image

Native executable là file binary, không còn giữ cấu trúc JAR/dependency graph theo cách scanner Java thông thường có thể đọc đầy đủ. Vì vậy, quy trình nên tạo inventory ở nhiều điểm:

- SBOM từ Maven/Gradle project để nhận diện Java components.
- SBOM của builder image/toolchain để quản lý build environment.
- SBOM hoặc package inventory của final container image.
- Metadata liên kết binary với source revision và dependency lock.
- Native library linkage report để bổ sung thông tin khi scanner không phát hiện đầy đủ.

Không coi SBOM từ JAR là SBOM hoàn chỉnh cho final native container. Native compile có thể thay đổi cách đóng gói, loại bỏ một số code, nhưng OS libraries và runtime files vẫn cần được theo dõi.

## 9. Scanner có thể bỏ sót dependency trong binary

Các scanner thường có cách nhận diện khác nhau:
- Quét Maven/Gradle manifests và lockfiles.
- Phân tích JAR/package metadata.
- Quét package database của OS image.
- Nhận diện file binary bằng signature hoặc version strings.
- Phân tích ELF dependency và shared libraries.
- So sánh SBOM với vulnerability database.

Một scanner chỉ đọc manifest Maven có thể không nhận diện glibc hoặc thư viện native trong final image. Một scanner image có thể phát hiện package OS nhưng không khôi phục chính xác mọi Java component đã được compile vào binary.

Vì vậy, dùng nhiều nguồn inventory phù hợp và ghi rõ coverage. Không diễn giải “zero vulnerabilities” thành “không có lỗ hổng” nếu scanner không nhận diện được một số lớp dependency.

## 10. Quét final container image

Final image là artifact được triển khai nên cần được scan sau khi build. Công cụ có thể là scanner trong registry, CI hoặc security platform của tổ chức.

Một workflow tổng quát:

```text
Build native executable
        |
        v
Create final container image
        |
        v
Generate image SBOM
        |
        v
Scan OS + application components
        |
        v
Review vulnerabilities and policy
        |
        v
Sign/attest and promote image digest
```

Ví dụ lệnh scan phụ thuộc công cụ đang dùng; không có một cú pháp chung cho mọi scanner. Cấu hình scanner để kiểm tra OS packages, language packages khi có thể, native libraries và image configuration.

Quét đúng image digest sẽ được phát hành. Nếu rebuild image sau khi scan, digest có thể đổi và kết quả scan trước đó không còn đại diện cho artifact mới.

## 11. CVE trong Java dependency vẫn áp dụng cho native binary

Một CVE trong thư viện Java không biến mất chỉ vì bytecode được biên dịch thành machine code. Nếu phần code có lỗ hổng còn được đưa vào executable và đường khai thác vẫn tồn tại, native application vẫn có thể bị ảnh hưởng.

Ví dụ, một parser xử lý dữ liệu không tin cậy có thể có lỗi denial of service hoặc memory exhaustion. Native Image không tự sửa logic parser. Tương tự, lỗ hổng authorization trong code Spring vẫn là lỗi ứng dụng dù executable không chứa JAR riêng.

Khi nhận CVE:
- Xác định package/version trong dependency graph.
- Kiểm tra advisory và phiên bản đã vá.
- Xác định API/feature ứng dụng sử dụng.
- Kiểm tra reachability nếu có dữ liệu phù hợp, nhưng không dùng “unreachable” làm lý do bỏ qua mà không có bằng chứng.
- Nâng version và chạy regression/native tests.
- Rebuild, scan lại và phát hành artifact mới.

## 12. CVE trong OS và native libraries

Binary có thể phụ thuộc vào shared libraries như libc, libstdc++, OpenSSL hoặc thư viện vendor. Final image cũng chứa package OS như CA bundle và timezone database.

Cần xác định binary liên kết động hay tĩnh:

```bash
file orders-service
readelf -l orders-service
readelf -d orders-service
ldd orders-service
```

Dùng `ldd` với binary đáng tin cậy và trong môi trường tương thích. Với binary không tin cậy, ưu tiên phân tích ELF tĩnh. Nếu static linking, scanner package của final image có thể không thấy thư viện đã được nhúng vào binary; cần SBOM/build provenance và tool hỗ trợ binary analysis.

Cập nhật base image không nhất thiết cập nhật thư viện đã link tĩnh vào executable. Trong trường hợp đó, cần rebuild binary bằng toolchain chứa thư viện đã vá, rồi tạo image mới.

## 13. Builder image cũng nằm trong supply chain

Multi-stage build thường loại bỏ compiler và package build khỏi final image, nhưng builder vẫn có thể:
- Chạy script hoặc plugin độc hại.
- Resolve dependency từ repository không tin cậy.
- Chứa GraalVM/JDK version có lỗ hổng.
- Sử dụng CI action hoặc build plugin bị xâm phạm.
- Rò rỉ credentials qua build logs/cache/artifacts.

Quản lý builder:
- Pin builder image theo digest.
- Quét image và OS packages.
- Pin Maven/Gradle plugins và CI actions theo policy.
- Dùng repository mirror/allowlist.
- Cấp credentials tối thiểu và chỉ trong thời gian cần thiết.
- Tách cache theo trust boundary.
- Lưu provenance cho native binary và image.

Không chỉ scan runtime image rồi kết luận pipeline an toàn. Build environment có quyền tạo artifact nên là một phần quan trọng của supply-chain threat model.

## 14. Reachability không thay thế vulnerability management

Native Image có thể loại bỏ class không reachable khỏi executable. Điều này có thể giảm code được đóng gói, nhưng không thay thế cập nhật dependency.

Có các lý do:
- Reachability có thể thay đổi khi code/config/profile thay đổi.
- Một class tưởng như ít dùng có thể reachable qua reflection hoặc framework.
- Scanner có thể không xác định được code cụ thể đã bị loại.
- Lỗ hổng có thể nằm trong code còn reachable.
- CVE có thể ảnh hưởng tới shared library hoặc OS package ngoài Java reachability.

Nếu dùng reachability analysis để hỗ trợ triage, lưu report và build inputs tương ứng. Không tạo exception policy tự động chỉ từ việc một dependency được cho là không được gọi trong một test run.

## 15. Đánh giá mức độ nghiêm trọng và khả năng khai thác

Không phải mọi CVE đều có mức độ rủi ro như nhau đối với service. Triage nên xem:

- Severity score và advisory của vendor.
- Có exploit công khai hoặc khai thác thực tế không.
- Dependency có nằm trong artifact được triển khai không.
- Code path có thể truy cập từ input không tin cậy không.
- Service chạy với quyền và network access nào.
- Có mitigation/configuration an toàn không.
- Có bản vá tương thích không.
- Exposure và business impact của service.

Không bỏ qua CVE chỉ vì scanner đánh dấu “low” nếu nó nằm trên đường xử lý dữ liệu nhạy cảm. Cũng không chặn mọi release vì một advisory không áp dụng tới artifact mà không có quy trình xác minh được ghi nhận.

Triage phải có người chịu trách nhiệm, lý do, thời hạn xử lý và điều kiện xem xét lại.

## 16. Chính sách build gate cho vulnerability

CI có thể đặt policy theo severity, exploitability, age và loại artifact. Ví dụ:

| Điều kiện | Hành động minh họa |
|---|---|
| Critical có exploit và ảnh hưởng runtime | Chặn promote/release |
| High có bản vá tương thích | Tạo remediation bắt buộc theo SLA |
| Medium không có exploit, có mitigation | Theo dõi và đặt deadline |
| Finding không áp dụng có bằng chứng | Exception có người phê duyệt và thời hạn |
| Scanner không nhận diện native component | Bổ sung inventory/tool hoặc ghi coverage gap |

Đây là ví dụ policy, không phải ngưỡng bắt buộc cho mọi tổ chức. Security team cần xác định SLA và exception process.

Gate nên scan:
- Dependency graph/SBOM Java.
- Builder image.
- Final container image.
- Native library inventory.
- License/policy nếu áp dụng.
- Artifact signature/provenance trước promotion.

## 17. Cập nhật dependency và rebuild native artifact

Khi có bản vá, cập nhật source/build configuration và tạo lại native executable. Không thể thay một JAR trong filesystem container để cập nhật thư viện đã compile vào binary.

Quy trình:
1. Xác định dependency trực tiếp/transitive bị ảnh hưởng.
2. Chọn phiên bản đã vá tương thích với Spring Boot BOM.
3. Cập nhật lockfile/BOM/plugin nếu cần.
4. Chạy JVM unit/integration tests.
5. Chạy Spring AOT và native build.
6. Chạy native integration tests liên quan.
7. Tạo SBOM mới.
8. Scan final image và builder image.
9. Gắn digest/provenance và phát hành.
10. Giữ rollback artifact theo chính sách.

Nếu CVE thuộc shared library được link động, cập nhật runtime image có thể đủ trong một số trường hợp nhưng phải xác minh ABI/version compatibility. Nếu thư viện được link tĩnh, cần rebuild executable với library đã vá.

## 18. Theo dõi lỗ hổng sau khi phát hành

Security scan không chỉ chạy một lần lúc build. Advisory mới có thể được công bố sau khi image đã deploy. Cần lưu SBOM, image digest và component inventory để scanner có thể đánh giá lại các artifact đang chạy.

Một quy trình liên tục:
- Registry scan khi push.
- Scheduled rescan các image còn được triển khai.
- Theo dõi advisory từ vendor/dependency maintainers.
- Liên kết CVE với service owner và image digest.
- Xác định image đang chạy trong môi trường nào.
- Tạo ticket/remediation deadline.
- Rebuild và rollout bản vá.
- Xác nhận digest cũ đã được thay thế hoặc loại khỏi môi trường.

Nếu chỉ lưu tag mutable, khó biết instance đang chạy binary nào. Dùng digest để truy vết chính xác.

## 19. SBOM, provenance và chữ ký artifact

SBOM cho biết thành phần; provenance cho biết artifact được tạo từ source/build inputs nào; chữ ký giúp xác minh artifact đến từ nguồn phát hành tin cậy.

Một release record nên liên kết:
- Source commit.
- Dependency lock/BOM.
- GraalVM/JDK và Native Build Tools versions.
- Builder image digest.
- Build arguments và profile.
- Native executable hash.
- Final image digest.
- SBOM.
- Test reports và scan results.
- Signature/attestation nếu pipeline hỗ trợ.

Không đặt SBOM rời rạc mà không có liên kết với image digest. Nếu image được rebuild, tạo SBOM/provenance mới; không tái sử dụng report của digest trước.

## 20. Chẩn đoán finding sai hoặc không đầy đủ

| Tình huống | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Scanner không thấy Java dependency trong native binary | Code đã compile vào executable, không còn JAR manifest | Scan dependency graph và SBOM project song song |
| Scanner không thấy glibc/OpenSSL | Static linking hoặc thiếu package metadata | Phân tích ELF, builder inventory và binary SBOM |
| CVE báo trên builder nhưng không có trong final image | Package chỉ nằm trong build stage | Ghi rõ scope; vẫn xử lý rủi ro build supply chain |
| CVE báo trên base image | OS package trong final image | Cập nhật base image và retest |
| Version scanner khác dependency lock | Scanner nhận diện sai/metadata thiếu | Đối chiếu package URL, hash và resolved graph |
| CVE được cho là unreachable | Reachability report chưa đủ coverage | Lưu bằng chứng, review code path và policy exception |
| Image đã scan nhưng digest đổi | Rebuild hoặc tag bị ghi đè | Scan lại đúng digest phát hành |
| Library static có bản vá nhưng binary cũ | Library đã nhúng vào executable | Rebuild Native Image |

Không xóa finding chỉ vì scanner không hiểu binary. Ghi coverage gap và bổ sung nguồn dữ liệu phù hợp.

## 21. Bài thực hành: tạo vulnerability workflow cho Order API native

**Bối cảnh:** Order API được build thành native executable, đóng gói trong distroless container và phát hành nhiều lần mỗi tuần.

**Bước 1 — Lưu dependency graph.** Xuất Maven/Gradle runtime dependency report và pin BOM/lockfile.

**Bước 2 — Tạo SBOM Java.** Dùng plugin CycloneDX/SPDX đã pin; lưu SBOM cùng build ID và commit.

**Bước 3 — Quét builder.** Quét GraalVM/JDK builder image, OS packages và CI tooling theo policy.

**Bước 4 — Build native.** Chạy AOT/native compilation với toolchain được pin; lưu build logs và executable hash.

**Bước 5 — Tạo final image.** Dùng runtime base image tối thiểu phù hợp, ghi image digest và tạo image SBOM.

**Bước 6 — Quét native/runtime components.** Scan final image, OS packages, shared libraries và bổ sung ELF/linkage inventory khi scanner chưa bao phủ.

**Bước 7 — Triage CVE.** Xác định component, version, exploitability, reachability evidence, mitigation và SLA.

**Bước 8 — Build gate.** Chặn promote theo policy đã phê duyệt; exception phải có owner, lý do và expiry.

**Bước 9 — Theo dõi sau phát hành.** Scheduled rescan các digest đang chạy và tạo remediation khi advisory mới xuất hiện.

**Bước 10 — Diễn tập patch.** Nâng một dependency thử nghiệm, rebuild native binary, tạo SBOM mới, scan và promote digest mới.

Tiêu chí hoàn thành: Java/native/system dependencies có inventory; SBOM gắn với artifact; builder và final image được scan; CVE được triage có owner/SLA; native rebuild và post-release rescan có thể tái lập.

## 22. Kết luận

Native Image không loại bỏ trách nhiệm quản lý lỗ hổng. Java dependencies vẫn có thể chứa code dễ bị khai thác; native executable có thể phụ thuộc thư viện hệ thống; builder image, compiler và CI plugins cũng nằm trong supply chain. Scanner chỉ đọc JAR hoặc manifest không đủ để đánh giá toàn bộ binary và final container.

Hãy duy trì dependency graph và SBOM cho Java components, scan builder/final image, kiểm tra native library linkage, gắn mọi kết quả với image digest và provenance, rồi triage CVE theo khả năng khai thác cùng mức độ ảnh hưởng. Khi cập nhật dependency hoặc thư viện hệ thống, tạo lại native artifact, chạy test và scan lại trước khi promote. Scheduled rescan sau phát hành giúp phát hiện advisory mới trong chính các image đang chạy.
