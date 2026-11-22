# Chọn mức bảo mật cho Java toolchain

## 1. Mức bảo mật của toolchain là gì?

Trong thiết kế toolchain, **mức bảo mật** mô tả độ chặt của các biện pháp bảo vệ toàn bộ quá trình lấy JDK, chạy build tool, tải dependency/plugin, thực thi build script, tạo artifact và phát hành phần mềm.

Toolchain không chỉ gồm JDK. Nó còn có Maven hoặc Gradle, Wrapper, plugin, thư viện bắc cầu, repository, cache, IDE, CI runner, secret và hệ thống ký artifact. Một thành phần bị thay thế hoặc chạy mã độc có thể làm thay đổi kết quả build và đưa mã không mong muốn vào sản phẩm.

Bài này dùng bốn profile thực hành: Cơ bản, Tiêu chuẩn, Cao và Rất cao. Đây là cách phân loại để chọn biện pháp theo rủi ro, **không phải bốn cấp bảo mật chính thức của Java SE, Oracle hay SLSA**. Một tổ chức có thể đổi tên hoặc ánh xạ chúng vào chính sách nội bộ.

## 2. Bảo vệ những gì?

Một build Java có nhiều ranh giới tin cậy:

| Thành phần | Rủi ro nếu bị kiểm soát |
|---|---|
| JDK/compiler | Biên dịch mã bị sửa, chèn hành vi ngoài dự kiến |
| Maven/Gradle và Wrapper | Thực thi mã trước hoặc trong build |
| Plugin, annotation processor | Chạy mã với quyền của tiến trình build |
| Dependency và repository | Đưa thư viện giả mạo hoặc có lỗ hổng vào ứng dụng |
| Build script | Đọc file, truy cập mạng, sửa artifact và lấy secret |
| CI runner và cache | Rò rỉ credential hoặc làm nhiễm các build sau |
| Signing key và release credential | Phát hành artifact giả mạo dưới danh nghĩa tổ chức |

Maven plugin, Gradle plugin, build script và annotation processor đều là mã có thể thực thi. Hãy xem thay đổi plugin hoặc Wrapper như thay đổi mã chương trình có ảnh hưởng bảo mật.

## 3. Đánh giá rủi ro trước khi chọn mức

Xem xét ba yếu tố:

- **Mức độ ảnh hưởng:** toolchain chỉ build bài lab, ứng dụng nội bộ hay sản phẩm chạy production có dữ liệu quan trọng?
- **Mức độ phơi nhiễm:** repository riêng với nhóm tin cậy, repository công khai, hay nhận pull request từ contributor bên ngoài?
- **Quyền mà build nắm giữ:** chỉ đọc source hay có quyền ghi package, deploy production, truy cập cloud hoặc ký artifact?

Chọn profile theo rủi ro cao nhất trong ba yếu tố, không lấy trung bình. Một project ít người dùng nhưng build job có quyền ký và phát hành production vẫn cần kiểm soát ở mức cao.

## 4. Bốn profile bảo mật thực hành

| Profile | Trường hợp phù hợp | Biện pháp chính |
|---|---|---|
| Cơ bản | Học tập, thử nghiệm, máy cá nhân, không có secret production | JDK và build tool có nguồn rõ ràng, dùng Wrapper, HTTPS, pin version, không chạy file không tin cậy |
| Tiêu chuẩn | Nhóm phát triển, CI nội bộ, ứng dụng thông thường | Kiểm tra checksum Wrapper, xác minh dependency, pin plugin, quét lỗ hổng, quyền CI tối thiểu |
| Cao | Sản phẩm production, repository công khai hoặc nhận đóng góp bên ngoài | Runner tách biệt, action được pin, dependency và release có xác minh, OIDC, ký artifact, provenance |
| Rất cao | Hệ thống trọng yếu, tài chính, dữ liệu nhạy cảm hoặc yêu cầu kiểm toán | Builder cô lập và được làm cứng, kiểm soát egress, phê duyệt phát hành, signing key được bảo vệ, provenance có xác minh độc lập |

Các profile tích lũy biện pháp. Khi chuyển từ Tiêu chuẩn lên Cao, vẫn duy trì pin version, checksum và dependency verification đã có. Chỉ tăng mức khi rủi ro yêu cầu; không cần dựng một hệ thống kiểm soát phức tạp cho bài lab không có quyền truy cập nhạy cảm.

## 5. Những kiểm soát nền tảng ở mọi mức

Dù chọn profile nào, hãy giữ các nguyên tắc sau:

1. Tải JDK và build tool từ nhà phân phối hoặc nguồn chính thức, qua HTTPS.
2. Chốt version cụ thể cho JDK, Maven/Gradle, plugin và dependency quan trọng.
3. Dùng Wrapper được commit cùng repository và kiểm tra tính toàn vẹn của nó.
4. Không chạy build script từ checkout chưa tin cậy trên máy đang giữ credential.
5. Không đặt password, token, private key hoặc certificate trong source, build file hay cache.
6. Dùng tài khoản và quyền hệ điều hành tối thiểu cần thiết.
7. Cập nhật bản vá bảo mật và xử lý cảnh báo dependency có mức độ nghiêm trọng phù hợp.
8. Có cách truy lại source, toolchain và dependency đã tạo ra artifact phát hành.

Các biện pháp này tạo baseline để tăng cường theo từng profile.

## 6. Chọn và cố định JDK

Chọn JDK từ nhà phân phối có chính sách cập nhật, nguồn tải chính thức, chữ ký hoặc checksum công bố và lịch hỗ trợ phù hợp với vòng đời sản phẩm.

Ghi rõ:

- Nhà phân phối và tên bản build.
- Java feature release và patch/update version.
- Hệ điều hành, kiến trúc và loại package.
- Nguồn tải và cách xác minh checksum/chữ ký.
- Lịch cập nhật khi có bản vá bảo mật.

Không dùng tên phiên bản trôi nổi như `latest` trong build production. Cùng một feature release có thể có nhiều patch level và vendor build. Pin đúng bản cần dùng để build có thể tái lập và điều tra được.

Kiểm tra JDK thực tế:

~~~bash
java --version
javac --version
java -XshowSettings:properties -version
~~~

Trên CI, log lại phiên bản và đường dẫn JDK được chọn. Cấu hình Java Toolchain cho compile/test task để IDE, máy developer và runner dùng cùng baseline.

## 7. Bảo vệ Maven Wrapper

Maven Wrapper giúp mọi máy dùng đúng Maven distribution của project. Wrapper cũng tải và chạy binary, vì vậy cần xác minh cả Wrapper JAR và Maven distribution.

Trong `.mvn/wrapper/maven-wrapper.properties`, dùng hai thuộc tính:

- `wrapperSha256Sum` để xác minh file `maven-wrapper.jar`.
- `distributionSha256Sum` để xác minh Maven distribution được tải.

Lấy SHA-256 từ nguồn Apache Maven chính thức hoặc repository mirror đã được tổ chức xác minh. Không lấy checksum từ chính file vừa tải rồi coi đó là nguồn độc lập đáng tin.

Các bước kiểm tra:

1. Review `mvnw`, `mvnw.cmd` và `maven-wrapper.jar` trong pull request.
2. Pin URL distribution tới phiên bản Maven cụ thể và HTTPS.
3. Ghi checksum của Wrapper JAR và distribution.
4. Khi nâng Maven, xác minh binary và checksum mới trước khi cập nhật.
5. Dùng repository manager nội bộ nếu tổ chức cần kiểm soát nguồn artifact.

Không chạy Wrapper từ repository lạ trước khi review các file này. Một Wrapper đã bị thay thế có thể thực thi mã trước khi Maven bắt đầu build.

## 8. Bảo vệ Gradle Wrapper

Gradle Wrapper cũng thực thi binary được lưu trong repository và tải distribution theo URL đã cấu hình. Trong `gradle/wrapper/gradle-wrapper.properties`:

- Pin `distributionUrl` tới một version chính xác, dùng HTTPS và nguồn chính thức hoặc mirror đã kiểm soát.
- Đặt `distributionSha256Sum` bằng SHA-256 công bố cho đúng distribution ZIP.
- Xác minh `gradle-wrapper.jar` bằng checksum hoặc chữ ký chính thức khi tạo và mỗi lần nâng version.

Ví dụ phần URL:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.0-bin.zip
~~~

Thêm checksum độc lập cho đúng ZIP trước khi dùng trong môi trường tin cậy. Gradle sẽ dừng build nếu checksum tải về không khớp giá trị đã pin.

Trước khi chạy Wrapper từ checkout không quen thuộc, đọc properties, kiểm tra Wrapper JAR, xem `settings.gradle(.kts)`, `build.gradle(.kts)` và `buildSrc/`. Mở project trong IDE cũng có thể kích hoạt Gradle sync và chạy build logic.

## 9. Xác minh dependency và plugin trong Gradle

Gradle hỗ trợ **dependency verification** bằng checksum và chữ ký. Khi có file `gradle/verification-metadata.xml`, Gradle tự kiểm tra artifact được dependency engine tải về, gồm thư viện, metadata và plugin.

Tạo metadata ban đầu:

~~~bash
./gradlew --write-verification-metadata sha256
~~~

Nếu artifact có chữ ký PGP đáng tin cậy, có thể tạo cả checksum và chữ ký:

~~~bash
./gradlew --write-verification-metadata sha256,pgp
~~~

Checksum xác minh nội dung không thay đổi; chữ ký giúp xác minh artifact được ký bởi key đã tin cậy. Dùng SHA-256 hoặc SHA-512 cho checksum hiện đại. Không dùng MD5 hoặc SHA-1 làm cơ chế xác minh mới.

**Cảnh báo khi bootstrap:** lệnh tạo metadata tải dependency từ repository hiện tại rồi ghi nhận checksum/key. Nếu repository đã bị xâm nhập hoặc dependency độc hại đã được đưa vào, metadata mới có thể hợp thức hóa chính artifact đó. Review diff, xác minh nguồn chính thức và key của dependency quan trọng trước khi commit file metadata.

Gradle không tự xác minh các dependency thay đổi như SNAPSHOT theo cách này. Release build nên dùng version bất biến và tránh dependency thay đổi liên tục.

## 10. Quản lý dependency và plugin trong Maven

Với Maven, kiểm soát rõ dependency, plugin và repository:

- Pin version cho Maven plugin trong `pom.xml`; tránh version mặc định không được quản lý.
- Tránh version range và SNAPSHOT trong release build.
- Dùng `dependencyManagement` để quản lý version tập trung trong multi-module project.
- Kiểm tra dependency bắc cầu bằng `mvn dependency:tree`.
- Dùng repository manager/mirror do tổ chức kiểm soát nếu cần một nguồn tải thống nhất.
- Chỉ cho phép repository HTTPS và nguồn đã được phê duyệt.
- Review thay đổi plugin, extension và annotation processor như review mã có thể thực thi.

Kiểm tra cây dependency:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dverbose
~~~

Maven 3.9.x có Plugin Validation để cảnh báo một số vấn đề trong cấu hình và plugin. Có thể tăng mức hiển thị khi điều tra:

~~~bash
mvn -Dmaven.plugin.validation=verbose verify
~~~

Plugin Validation giúp phát hiện vấn đề tương thích và cấu hình plugin; nó không phải malware scanner hay cơ chế xác minh chữ ký artifact.

## 11. Quét lỗ hổng và tạo SBOM

Xác minh nguồn gốc artifact và quét lỗ hổng là hai việc khác nhau:

- **Checksum/chữ ký:** kiểm tra tính toàn vẹn và danh tính người ký của artifact.
- **SCA:** tìm dependency có lỗ hổng đã công bố.
- **SBOM:** liệt kê thành phần phần mềm được dùng để tạo hoặc đóng gói sản phẩm.

OWASP Dependency-Check là công cụ SCA có thể nhận diện dependency và đối chiếu với lỗ hổng công khai. Kết quả có thể có false positive, false negative hoặc dữ liệu chưa cập nhật; cần review trước khi chặn release.

Đối với release production:

1. Quét dependency trực tiếp và bắc cầu.
2. Đặt chính sách xử lý theo mức nghiêm trọng, khả năng khai thác và mức phơi nhiễm.
3. Ghi ngoại lệ có người chịu trách nhiệm và thời hạn xem xét.
4. Tạo SBOM ở định dạng phù hợp như CycloneDX hoặc SPDX.
5. Lưu SBOM cùng artifact và release metadata.

Một dependency không có CVE đã biết vẫn có thể độc hại hoặc bị giả mạo. SCA không thay thế dependency verification.

## 12. Review build script và plugin như mã thực thi

Mã trong `pom.xml`, `settings.xml`, `build.gradle`, `settings.gradle`, `buildSrc`, Maven extension và plugin có thể chạy trong quá trình build.

Khi review thay đổi toolchain, tìm:

- Plugin mới hoặc plugin đổi version không có lý do.
- Task chạy shell/process, tải script hoặc binary từ URL không quen thuộc.
- Repository mới, mirror lạ hoặc URL HTTP.
- Task đọc biến môi trường, file home, SSH key hoặc credential.
- Script sửa file ngoài workspace hoặc gửi dữ liệu ra mạng.
- Dependency được thêm vào build logic nhưng không xuất hiện trong runtime dependency tree.

Với project bên ngoài tổ chức, kiểm tra trước khi chạy `./gradlew`, `mvnw` hoặc mở project trong IDE. Dùng container/VM cô lập nếu chưa thể xác minh đầy đủ.

## 13. Chia ranh giới giữa pull request và release

Một pipeline an toàn nên phân biệt build kiểm tra mã từ contributor và build phát hành:

- **Pull request không tin cậy:** chạy test/lint với quyền đọc tối thiểu; không cấp secret production, signing key hay quyền deploy.
- **Build từ nhánh được bảo vệ:** chỉ chạy sau review và chính sách branch protection.
- **Release:** dùng job riêng, environment có approval, quyền ghi đúng phạm vi và nguồn commit đã xác định.
- **Signing/deploy:** tách khỏi job chạy mã từ pull request; chỉ nhận artifact đã được kiểm tra từ trusted build.

Không dùng một runner có credential production cho mọi loại event. Không để artifact/cache từ build không tin cậy được đưa thẳng vào release mà không xác minh lại.

## 14. Giới hạn quyền CI và bảo vệ secret

Áp dụng least privilege:

- Token mặc định chỉ có quyền đọc nếu build không cần ghi.
- Cấp quyền ghi package hoặc deploy ở job thực sự cần.
- Dùng service account riêng theo môi trường thay vì credential cá nhân dài hạn.
- Không in secret ra log, command line hoặc artifact.
- Không lưu secret trong Docker layer, cache, build scan public hoặc file cấu hình được commit.
- Xoay vòng credential và thu hồi ngay khi nghi ngờ rò rỉ.

Với GitHub Actions, có thể khai báo quyền ở workflow/job:

~~~yaml
permissions:
  contents: read
~~~

Job cần lấy OIDC token để xác thực với cloud provider có thể thêm `id-token: write` ở đúng job đó. Quyền này chỉ cho phép yêu cầu token; cloud provider vẫn phải cấu hình trust policy giới hạn repository, branch, environment hoặc workflow được phép nhận credential.

Ưu tiên OIDC token ngắn hạn thay cho lưu cloud access key dài hạn trong GitHub Secrets khi nhà cung cấp cloud hỗ trợ.

## 15. Pin GitHub Actions và kiểm soát workflow

Action bên thứ ba là một dependency thực thi trong CI. GitHub khuyến nghị dùng workflow dependency lockfile khi tính năng đó được hỗ trợ; nếu chưa dùng lockfile, pin action tới full-length commit SHA đã xác minh từ repository gốc.

Không coi tag như `@v4` là một version bất biến: tag có thể được di chuyển. Khi nâng action, kiểm tra release, commit, changelog và quyền mà action yêu cầu.

Ngoài ra:

- Đặt `permissions` tối thiểu ở workflow và job.
- Giới hạn environment secret theo branch/tag và approval.
- Không checkout rồi thực thi code không tin cậy trong workflow có quyền ghi.
- Review reusable workflow và composite action như dependency.
- Giữ runner cập nhật và hạn chế người có quyền sửa workflow.

Một runner bị chiếm quyền có thể đọc secret mà job được cấp, sửa artifact và ảnh hưởng các job tiếp theo nếu môi trường dùng chung.

## 16. Cô lập runner, workspace và cache

Runner thực thi build script và test, vì vậy nên giới hạn blast radius:

- Dùng runner ephemeral cho build có rủi ro cao; hủy môi trường sau job.
- Tách runner PR, runner build tin cậy và runner ký/release.
- Chạy bằng user không có quyền quản trị.
- Giới hạn network egress và chỉ mở repository/service cần thiết.
- Không mount thư mục home, Docker socket hoặc credential host nếu không cần.
- Dùng cache riêng theo trust boundary; không cho PR không tin cậy ghi cache mà release job tin cậy sẽ khôi phục.
- Không tái sử dụng workspace chứa file thực thi hoặc secret giữa các project không liên quan.

Cache chỉ là tối ưu hiệu năng. Khi có nghi ngờ cache bị nhiễm, bỏ cache liên quan và build lại từ dependency đã xác minh. Không xem việc cache hit là bằng chứng artifact an toàn.

## 17. Ký artifact và chứng minh nguồn gốc build

Với release quan trọng, ký artifact sau khi build đã được kiểm tra. Giữ signing key trong dịch vụ quản lý khóa hoặc HSM/KMS; không đặt private key trong source, runner image hoặc cache.

Lưu kèm:

- Hash của artifact phát hành.
- Commit/tag source và trạng thái review.
- JDK, Maven/Gradle, plugin và dependency version.
- SBOM và kết quả scan.
- Danh tính workflow/runner và thời điểm build.
- Chữ ký và build provenance/attestation nếu có.

GitHub Actions hỗ trợ artifact attestations để ghi nhận provenance. SLSA định nghĩa các mức bảo đảm cho build supply chain. Provenance cho phép bên nhận xem artifact được tạo từ source, builder và quy trình nào; chữ ký giúp phát hiện provenance bị sửa sau khi tạo.

## 18. Dùng SLSA làm tham chiếu trưởng thành

SLSA Build Track v1.2 mô tả các mức:

| Mức | Ý nghĩa |
|---|---|
| Build L0 | Không có bảo đảm theo track |
| Build L1 | Có provenance mô tả cách package được tạo |
| Build L2 | Provenance được ký và tạo bởi hosted build platform |
| Build L3 | Build platform được harden để chống can thiệp trong quá trình build |

SLSA là khung tham chiếu cho supply chain; bốn profile thực hành trong bài này không tương đương trực tiếp với các mức SLSA. Có thể dùng SLSA để đặt mục tiêu cho quy trình build/release và đo khoảng cách kiểm soát.

Không tuyên bố đạt một mức SLSA chỉ vì đã tạo file provenance hoặc bật một tính năng CI. Cần đáp ứng toàn bộ yêu cầu của track và phiên bản đặc tả áp dụng.

## 19. Đừng nhầm mức bảo mật toolchain với Java Security Manager

Java Security Manager từng là cơ chế kiểm soát quyền của code trong JVM. Nó đã bị deprecated để loại bỏ từ JDK 17 và **bị vô hiệu hóa vĩnh viễn từ JDK 24**. Không thể bật nó khi khởi động JVM hoặc cài một Security Manager tùy chỉnh; không có cơ chế thay thế trực tiếp trong Java SE.

Vì vậy, không chọn mức bảo mật toolchain bằng cách thêm `-Djava.security.manager` hoặc file policy cũ. Để cô lập build script/plugin không tin cậy, dùng biện pháp của hệ điều hành và hạ tầng:

- Container hoặc VM với user không đặc quyền.
- Filesystem và network namespace/permission giới hạn.
- Network egress policy.
- Credential ngắn hạn và chỉ cấp theo job.
- Runner ephemeral và tách môi trường.

Cấu hình TLS, truststore, keystore và thuật toán mật mã của ứng dụng Java là chủ đề runtime/application security riêng. Chúng không thay thế bảo vệ JDK, Wrapper, plugin, dependency và CI trong toolchain.

## 20. Cách chọn profile theo tình huống

| Tình huống | Profile khởi điểm | Lý do |
|---|---|---|
| Bài lab Java trên laptop, không có secret | Cơ bản | Tác động và quyền truy cập thấp |
| Ứng dụng nội bộ, CI chỉ build/test | Tiêu chuẩn | Có dependency và runner dùng chung cần xác minh |
| Thư viện công khai nhận pull request từ cộng đồng | Cao | Build nhận mã không tin cậy và có nguy cơ supply-chain |
| Backend production có quyền deploy cloud | Cao | Credential và artifact có tác động trực tiếp tới production |
| Sản phẩm trọng yếu hoặc bị ràng buộc kiểm toán | Rất cao | Cần builder cô lập, provenance, approval và kiểm soát signing |

Nếu chưa chắc, hãy bắt đầu ở Tiêu chuẩn cho CI dùng chung. Nâng lên Cao khi build xử lý mã bên ngoài, có quyền phát hành hoặc nắm secret quan trọng. Dùng Rất cao khi hậu quả của artifact bị giả mạo hoặc runner bị chiếm quyền là rất lớn.

## 21. Lộ trình triển khai

Triển khai theo từng bước để nhóm có thể kiểm chứng tác động:

1. Ghi lại JDK, Maven/Gradle, Wrapper, plugin, repository và quyền CI hiện tại.
2. Pin version và xác minh checksum cho JDK/Wrapper.
3. Bật Gradle dependency verification hoặc kiểm soát dependency/repository trong Maven.
4. Pin plugin/action và review thay đổi build logic.
5. Bật SCA, tạo SBOM và đặt quy trình xử lý CVE.
6. Tách pull request, trusted build, signing và deploy job.
7. Giảm quyền token, dùng OIDC khi có thể và cô lập runner/cache.
8. Ký artifact, lưu provenance và đặt approval cho release quan trọng.
9. Kiểm tra định kỳ wrapper, dependency, action, runner image và signing policy.

Sau mỗi bước, đo thời gian build, số lần verification failure, số cảnh báo và công sức cập nhật. Một profile tốt phải bảo vệ đúng rủi ro mà vẫn cho phép nhóm duy trì build ổn định.

## 22. Lỗi triển khai thường gặp

### Chỉ pin version nhưng không kiểm tra checksum

Pin URL giúp chọn đúng tên/version, nhưng không xác minh nội dung ZIP đã tải. Bổ sung checksum lấy từ nguồn chính thức độc lập.

### Tạo verification metadata rồi commit ngay

Metadata bootstrap có thể ghi nhận artifact đã bị xâm nhập. Review checksum, chữ ký, key và nguồn tải trước khi tin cậy.

### Quét CVE nhưng bỏ qua plugin build

Plugin và build logic cũng là dependency thực thi. Bao gồm plugin trong kiểm soát version, review và verification.

### Dùng chung runner có quyền deploy cho pull request

Build script từ PR có thể đọc credential của runner. Tách runner và job theo trust boundary, không cấp secret release cho event không tin cậy.

### Tin rằng checksum chứng minh nhà phát hành

Checksum chứng minh nội dung khớp fingerprint đã tin cậy; nó không tự xác minh ai phát hành. Kết hợp checksum với chữ ký và xác minh key qua nguồn độc lập.

### Dùng Security Manager làm sandbox trên JDK 24

Security Manager đã bị vô hiệu hóa. Dùng container/VM, quyền OS, network policy và credential scope để cô lập tiến trình build.

### Tăng mức bảo mật bằng cách thêm thật nhiều scanner

Nhiều công cụ không tự tạo thành bảo đảm. Xác định mỗi công cụ phát hiện loại rủi ro nào, ai xử lý kết quả và điều kiện nào chặn release.

## 23. Checklist chọn và duy trì mức bảo mật

- [ ] Đã xác định tác động nếu JDK, plugin hoặc dependency bị thay thế.
- [ ] Đã đánh giá repository có nhận mã từ bên ngoài hay không.
- [ ] Đã xác định secret, quyền deploy và signing key mà build có thể truy cập.
- [ ] Đã chọn profile theo rủi ro cao nhất.
- [ ] JDK và Maven/Gradle Wrapper dùng nguồn chính thức, version pin và checksum.
- [ ] Plugin, dependency và repository được quản lý rõ ràng.
- [ ] Gradle dependency verification hoặc cơ chế xác minh tương đương được review.
- [ ] Có SCA và SBOM cho release cần thiết.
- [ ] Pull request không tin cậy không có quyền release/signing.
- [ ] Action, workflow, runner và cache được kiểm soát theo trust boundary.
- [ ] Secret có quyền tối thiểu, ưu tiên credential ngắn hạn/OIDC.
- [ ] Artifact phát hành có hash, chữ ký và provenance phù hợp.
- [ ] Có owner, thời hạn và quy trình xử lý ngoại lệ bảo mật.
- [ ] Có lịch rà soát JDK patch, dependency, plugin, action và runner image.

## 24. Tài liệu tham khảo

- [Gradle — Securing the Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html): kiểm tra Wrapper, distribution URL, checksum và checkout không tin cậy.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): checksum, chữ ký PGP, verification metadata và giới hạn bootstrap.
- [Gradle — Best Practices for Security](https://docs.gradle.org/current/userguide/best_practices_security.html): checksum distribution và xác minh Wrapper khi nâng cấp.
- [Apache Maven — Maven Wrapper](https://maven.apache.org/tools/wrapper/): wrapperSha256Sum và distributionSha256Sum.
- [Apache Maven — Plugin Validation](https://maven.apache.org/guides/plugins/validation/): cảnh báo cấu hình và vấn đề tương thích plugin.
- [GitHub Actions — Secure Use](https://docs.github.com/en/actions/reference/security/secure-use): workflow dependency, pin action, least privilege và xử lý mã không tin cậy.
- [GitHub Actions — OIDC](https://docs.github.com/en/actions/reference/security/oidc): xác thực cloud bằng token liên kết danh tính ngắn hạn.
- [GitHub Actions — Artifact Attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations): tạo và xác minh provenance của artifact.
- [SLSA v1.2 — Build Track](https://slsa.dev/spec/v1.2/build-track-basics): các mức bảo đảm provenance và build platform.
- [OWASP Dependency-Check](https://owasp.org/projects/dependency-check): phân tích dependency để tìm lỗ hổng đã công bố.
- [Oracle — Security Manager permanently disabled](https://docs.oracle.com/en/java/javase/24/migrate/migrating-jdk-8-later-jdk-releases.html): thay đổi Security Manager trong JDK 24.

Chọn mức bảo mật theo giá trị của artifact, nguồn mã có thể đi vào build và quyền mà build nắm giữ. Khi ba yếu tố này tăng, hãy tăng xác minh toolchain/dependency, cô lập runner, giảm quyền credential và bổ sung chữ ký cùng provenance cho release.
