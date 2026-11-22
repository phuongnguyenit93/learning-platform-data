# Cập nhật JDK an toàn

## 1. Cập nhật JDK là gì?

**Cập nhật JDK an toàn** là quá trình đưa bộ Java Development Kit đang dùng lên bản phát hành phù hợp, đồng thời xác nhận rằng môi trường phát triển, hệ thống build, ứng dụng và môi trường triển khai vẫn hoạt động đúng.

Một lần cập nhật JDK có thể bao gồm bản vá bảo mật, sửa lỗi runtime, cập nhật compiler, thư viện chuẩn hoặc công cụ đi kèm. Vì JDK ảnh hưởng trực tiếp đến quá trình biên dịch và thực thi ứng dụng, cần kiểm soát cả nguồn tải, phiên bản, cấu hình và kết quả kiểm thử.

Có hai loại thay đổi thường gặp:

- **Update trong cùng feature release:** ví dụ chuyển từ Java 21.0.4 lên 21.0.5. Thay đổi này thường nhằm nhận bản vá bảo mật và sửa lỗi trong cùng dòng Java 21.
- **Upgrade sang feature release khác:** ví dụ chuyển từ Java 17 lên Java 21. Đây là thay đổi lớn hơn, có thể liên quan đến ngôn ngữ, bytecode, API, module, công cụ build và khả năng tương thích thư viện.

Bản cập nhật cùng feature release thường có phạm vi tương thích hẹp hơn, nhưng vẫn cần kiểm thử. Không nên mặc định rằng mọi bản JDK mới đều hoàn toàn không ảnh hưởng đến ứng dụng.

## 2. Vì sao cần cập nhật JDK?

Duy trì JDK ở mức cập nhật phù hợp giúp:

- Nhận các bản vá bảo mật cho JVM, thư viện chuẩn và thành phần đi kèm.
- Sửa lỗi runtime, compiler, garbage collector và các công cụ JDK.
- Hạn chế rủi ro từ những lỗi đã được nhà cung cấp công bố.
- Tương thích với framework, thư viện và công cụ build mới hơn.
- Duy trì môi trường phát triển được hỗ trợ.
- Giảm khoảng cách giữa JDK dùng để phát triển, kiểm thử và triển khai.

JDK là thành phần nền tảng. Nếu ứng dụng dùng TLS, xử lý chứng chỉ, mã hóa, serialization, timezone hoặc networking, một bản cập nhật JDK có thể ảnh hưởng đến hành vi của các thành phần này. Cần xem release notes và advisory bảo mật của nhà cung cấp trước khi triển khai.

## 3. Phân biệt update, upgrade và thay đổi nhà cung cấp

Ba thay đổi sau có phạm vi khác nhau:

| Thay đổi | Ví dụ | Nội dung cần chú ý |
|---|---|---|
| Patch update | Java 21.0.4 lên 21.0.5 | Bản vá bảo mật, sửa lỗi và thay đổi trong cùng feature release |
| Feature upgrade | Java 17 lên Java 21 | API, cú pháp, bytecode, module, GC, công cụ và tương thích thư viện |
| Vendor change | Eclipse Temurin 21 sang Oracle JDK 21 | Chính sách hỗ trợ, giấy phép, build, nền tảng và khác biệt phân phối |

Không nên gộp cả ba thay đổi vào một lần nếu không cần thiết. Khi có thể, hãy thay đổi từng yếu tố để dễ xác định nguyên nhân nếu phát sinh lỗi.

Một tổ chức có thể chọn cùng feature release nhưng vẫn yêu cầu một nhà cung cấp cụ thể để thống nhất hỗ trợ và quy trình bảo trì. Ghi rõ cả vendor và phiên bản đầy đủ trong tài liệu môi trường.

## 4. Xác định JDK đang được sử dụng trước khi cập nhật

Trước khi thay đổi, cần biết máy và dự án đang dùng JDK nào. Một máy có thể cài nhiều JDK, trong khi terminal, IDE, Maven và Gradle lại sử dụng các đường dẫn khác nhau.

Chạy các lệnh cơ bản:

```bash
java --version
javac --version
```

Trên Windows PowerShell:

```powershell
$env:JAVA_HOME
Get-Command java -All
Get-Command javac -All
where.exe java
where.exe javac
```

Trên Linux hoặc macOS:

```bash
echo "$JAVA_HOME"
type -a java
type -a javac
command -v java
command -v javac
```

Kiểm tra cả runtime launcher và compiler. Nếu `java` và `javac` đến từ hai thư mục khác nhau, máy có thể đang chạy một JDK nhưng biên dịch bằng JDK khác.

Kiểm tra JVM thực tế đang chạy:

```bash
java -XshowSettings:properties -version
```

Tìm thuộc tính `java.home` trong kết quả. Thuộc tính này cho biết thư mục runtime của JVM đang chạy. Nó giúp phát hiện trường hợp `JAVA_HOME` và runtime thực tế không trùng nhau.

Với Maven:

```bash
mvn -version
```

Với Gradle:

```bash
./gradlew --version
```

Trên Windows, dùng `gradlew.bat --version`. Các lệnh này cho biết JVM mà Maven hoặc Gradle đang sử dụng. Dự án còn có thể cấu hình compiler toolchain riêng, vì vậy cần kiểm tra cả cấu hình build.

## 5. Chuẩn bị trước khi cập nhật

Trước khi cài bản mới, hãy lập một mốc hiện trạng để có thể so sánh và quay lại khi cần.

### 5.1. Ghi nhận phiên bản và đường dẫn

Lưu lại:

- Tên nhà cung cấp JDK.
- Feature release và số bản cập nhật hiện tại.
- Đường dẫn cài đặt JDK.
- Giá trị hiện tại của `JAVA_HOME` và thứ tự PATH.
- Kết quả `java --version` và `javac --version`.
- Phiên bản JVM của Maven hoặc Gradle.
- JDK được chọn trong IDE.
- JDK và image đang dùng trong CI hoặc container.

Có thể lưu kết quả các lệnh kiểm tra vào một tệp ghi nhận của đợt bảo trì. Không đưa thông tin nhạy cảm hoặc mật khẩu vào tệp này.

### 5.2. Kiểm tra yêu cầu tương thích

Đọc cấu hình dự án và xác định:

- Java tối thiểu mà framework và thư viện hỗ trợ.
- Java release mà dự án dùng để biên dịch.
- Phiên bản JDK chạy build tool.
- Phiên bản runtime trong môi trường staging và production.
- Phiên bản Maven Compiler Plugin, Gradle Wrapper và các plugin khác.
- Annotation processor, agent, native library và công cụ kiểm thử có phụ thuộc JDK hay không.

Nếu nâng feature release, cần kiểm tra ma trận tương thích của Gradle, Maven plugin, framework và thư viện. Một JDK mới có thể yêu cầu nâng công cụ build trước khi dự án biên dịch được.

### 5.3. Đọc release notes và security advisory

Sử dụng tài liệu chính thức của nhà cung cấp JDK đang dùng. Tập trung vào:

- Các lỗ hổng bảo mật đã được sửa và mức độ ảnh hưởng.
- Lỗi JVM, compiler, GC, networking và TLS được khắc phục.
- Thay đổi hành vi có thể ảnh hưởng ứng dụng.
- API bị deprecated hoặc loại bỏ.
- Thay đổi mặc định về thuật toán mật mã, chứng chỉ, locale hoặc timezone.
- Lỗi đã biết và giới hạn nền tảng.

Không chỉ đọc số phiên bản. Release notes giúp xác định liệu bản cập nhật có liên quan đến tính năng mà ứng dụng đang sử dụng hay không.

## 6. Tải và xác minh bộ cài JDK

Chỉ tải JDK từ website hoặc kho phần mềm đáng tin cậy của nhà cung cấp hay tổ chức. Kiểm tra đúng:

- Nhà cung cấp đã được dự án phê duyệt.
- Feature release và bản cập nhật yêu cầu.
- Hệ điều hành và kiến trúc CPU (x64 hoặc ARM64).
- Loại gói cài đặt phù hợp (installer, archive hoặc package).
- Chính sách hỗ trợ và điều khoản sử dụng áp dụng cho môi trường đó.

### 6.1. Xác minh checksum

Nếu nhà cung cấp công bố SHA-256, hãy tính checksum của tệp tải về và so sánh chính xác với giá trị chính thức.

Windows PowerShell:

```powershell
Get-FileHash .\jdk-installer.msi -Algorithm SHA256
```

Linux:

```bash
sha256sum jdk-installer.tar.gz
```

macOS:

```bash
shasum -a 256 jdk-installer.pkg
```

Checksum giúp phát hiện tệp bị hỏng hoặc không khớp với bản phát hành dự kiến. Giá trị so sánh phải lấy từ kênh chính thức hoặc kênh phân phối nội bộ đã được xác thực.

Nếu nhà cung cấp cung cấp chữ ký số, hãy xác minh chữ ký theo hướng dẫn của họ. Không bỏ qua cảnh báo chữ ký hoặc tắt cơ chế bảo vệ của hệ điều hành chỉ để cài được bộ JDK.

## 7. Cài đặt bản mới theo cách có thể quay lại

Nếu máy cần duy trì nhiều dự án hoặc cần khả năng rollback, hãy cài bản mới vào thư mục riêng thay vì ghi đè ngay lên JDK đang hoạt động.

Ví dụ:

```text
C:\Dev\Java\jdk-21.0.4
C:\Dev\Java\jdk-21.0.5

/opt/jdks/jdk-21.0.4
/opt/jdks/jdk-21.0.5
```

Cách tổ chức này cho phép chọn lại bản trước bằng cách thay đổi cấu hình đường dẫn. Không xóa bản cũ cho tới khi bản mới đã được kiểm tra và được chấp nhận.

### 7.1. Windows

Có thể sử dụng installer chính thức của nhà cung cấp hoặc package manager được tổ chức cho phép.

Quy trình thông thường:

1. Đóng các ứng dụng đang sử dụng JDK nếu installer yêu cầu.
2. Chạy installer đã xác minh.
3. Chọn thư mục cài đặt riêng nếu cần giữ bản cũ.
4. Hoàn tất cài đặt theo hướng dẫn của nhà cung cấp.
5. Kiểm tra thư mục JDK mới có các thành phần như `bin` và `conf`.
6. Cập nhật `JAVA_HOME` và PATH cho phiên terminal hoặc cấu hình người dùng phù hợp.
7. Mở terminal mới và xác minh phiên bản.

Không giả định installer luôn giữ lại bản cũ. Hành vi nâng cấp, gỡ bản cũ và đăng ký PATH khác nhau giữa các nhà cung cấp và loại installer.

### 7.2. Linux

Có thể cài bằng package manager của bản phân phối hoặc archive chính thức. Nếu dùng package manager, kiểm tra tên package và repository trước khi cập nhật.

Với archive, giải nén vào thư mục riêng, ví dụ `/opt/jdks/jdk-21.0.5`. Sau đó chọn JDK bằng `JAVA_HOME` và PATH:

```bash
export JAVA_HOME=/opt/jdks/jdk-21.0.5
export PATH="$JAVA_HOME/bin:$PATH"

java --version
javac --version
```

Nếu hệ thống dùng `update-alternatives`, cập nhật cả lựa chọn `java` và `javac`. Kiểm tra `JAVA_HOME` riêng vì cơ chế alternatives không nhất thiết thay đổi biến này.

### 7.3. macOS

Cài package hoặc archive từ nhà cung cấp. Nhiều JDK được đặt dưới:

```text
/Library/Java/JavaVirtualMachines/
```

Liệt kê các bản đã cài:

```bash
/usr/libexec/java_home -V
```

Chọn JDK cụ thể cho phiên shell hiện tại:

```bash
export JAVA_HOME=$(/usr/libexec/java_home -v 21)
export PATH="$JAVA_HOME/bin:$PATH"

java --version
javac --version
```

Lựa chọn `-v 21` chọn feature release 21; nếu có nhiều bản phân phối cùng feature release, cần kiểm tra danh sách và chọn đúng JDK theo yêu cầu của dự án.

## 8. Cập nhật cấu hình dự án và công cụ build

Sau khi cài JDK, cần kiểm tra cấu hình mà từng công cụ sử dụng. Đổi PATH của terminal không tự động thay đổi JDK trong IDE, Maven, Gradle hoặc CI.

### 8.1. Cấu hình Maven

Kiểm tra JVM chạy Maven:

```bash
mvn -version
```

Nếu dự án dùng Maven Toolchains, kiểm tra `~/.m2/toolchains.xml` và các plugin được cấu hình để sử dụng toolchain. Cập nhật đường dẫn JDK khi bản mới được cài ở vị trí khác.

Nếu dự án đặt release mục tiêu trong `pom.xml`, xác nhận giá trị đó vẫn đúng:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

`maven.compiler.release` quy định phiên bản Java mục tiêu khi biên dịch. Nó không nhất thiết quyết định JDK dùng để chạy Maven.

### 8.2. Cấu hình Gradle

Kiểm tra JVM chạy Gradle:

```bash
./gradlew --version
```

Nếu dùng Java Toolchains, xác nhận toolchain vẫn trỏ tới JDK phù hợp:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Nếu chỉ cập nhật patch trong cùng feature release, cấu hình feature version có thể không cần thay đổi. Tuy nhiên, Gradle có thể chọn một bản JDK khác cùng feature release nếu có nhiều bản được cài. Khi yêu cầu cố định nhà cung cấp hoặc đường dẫn, hãy cấu hình theo cơ chế toolchain của Gradle và chính sách dự án.

### 8.3. Cấu hình IDE

Kiểm tra riêng:

- Project SDK hoặc Installed JDK.
- Module SDK nếu dự án nhiều module.
- JDK chạy Maven hoặc Gradle trong IDE.
- Run/Debug configuration.
- JDK mà IDE dùng để phân tích mã và chạy test.

Ví dụ, IntelliJ IDEA có thể dùng Project SDK 21 nhưng Gradle JVM vẫn là JDK 17. Khi đó, build từ terminal và build từ IDE có thể cho kết quả khác nhau.

Sau khi đổi JDK, có thể cần reload project hoặc khởi động lại IDE để các tiến trình và cấu hình được nạp lại.

## 9. Kiểm thử sau khi cập nhật

Không kết luận bản cập nhật thành công chỉ vì `java --version` hiển thị đúng số phiên bản. Cần kiểm tra từ compiler tới runtime và ứng dụng thực tế.

### 9.1. Xác minh công cụ

Chạy:

```bash
java --version
javac --version
javadoc --version
jar --version
```

Kiểm tra đường dẫn thực tế và xác nhận các lệnh đến từ bản JDK mới. Nếu dự án dùng Maven hoặc Gradle, kiểm tra thêm phiên bản JVM mà build tool báo.

### 9.2. Build sạch và chạy test

Với Maven:

```bash
mvn clean verify
```

Với Gradle:

```bash
./gradlew clean build
```

Chạy đúng hệ thống build của dự án. Đọc toàn bộ kết quả, bao gồm warning về deprecated API, module access, annotation processor hoặc plugin không tương thích.

Build thành công chỉ là một bước. Cần chạy unit test, integration test và các bài test đặc thù của hệ thống.

### 9.3. Kiểm tra ứng dụng thực tế

Tập trung vào những khu vực dễ chịu ảnh hưởng khi thay JDK:

- Khởi động ứng dụng, tải class và module.
- Kết nối TLS, chứng chỉ, truststore và keystore.
- Mã hóa, chữ ký số và các provider mật mã.
- Kết nối database, HTTP client, DNS và networking.
- Timezone, locale, định dạng ngày giờ và encoding.
- Serialization và tương thích dữ liệu giữa các phiên bản.
- Garbage collection, mức sử dụng heap và CPU.
- Agent, profiler, monitoring và thư viện native.
- Đóng gói JAR, runtime image hoặc bộ cài ứng dụng.

Chạy smoke test trên môi trường staging có cấu hình gần với production. Nếu ứng dụng có yêu cầu hiệu năng, hãy so sánh latency, throughput, CPU và bộ nhớ với baseline trước khi cập nhật.

### 9.4. Kiểm tra bytecode và API mục tiêu

Nếu dùng JDK mới để biên dịch cho runtime cũ, kiểm tra cấu hình release và chạy thử trên đúng runtime mục tiêu.

Ví dụ:

```bash
javac --release 17 -d out src/com/example/Main.java
```

`--release 17` giúp compiler dùng bộ ngôn ngữ, bytecode và API công khai của Java 17. Tuy nhiên, vẫn cần kiểm thử ứng dụng trên Java 17 thực tế để phát hiện các khác biệt runtime hoặc dependency.

## 10. Triển khai theo từng giai đoạn

Đối với hệ thống quan trọng, nên cập nhật theo từng giai đoạn thay vì thay đổi tất cả máy cùng lúc.

Một quy trình triển khai có kiểm soát:

1. **Developer workstation:** cập nhật một máy thử nghiệm và kiểm tra IDE, terminal, build.
2. **CI:** cập nhật một pipeline hoặc job đại diện; chạy build và test đầy đủ.
3. **Staging:** triển khai ứng dụng bằng JDK mới trong môi trường gần production.
4. **Canary hoặc nhóm nhỏ:** nếu kiến trúc cho phép, cập nhật một phần instance và theo dõi lỗi, log, metrics.
5. **Production rollout:** mở rộng sau khi các chỉ số và kiểm thử đạt tiêu chí đã thống nhất.
6. **Post-deployment review:** theo dõi cảnh báo, hiệu năng, lỗi ứng dụng và sự cố kết nối trong khoảng thời gian phù hợp.

Định nghĩa trước tiêu chí chấp nhận và điều kiện rollback. Ví dụ: build và test phải pass, không có lỗi khởi động mới, tỷ lệ lỗi không tăng đáng kể và hiệu năng nằm trong ngưỡng đã thống nhất.

## 11. Chuẩn bị phương án rollback

Một kế hoạch cập nhật an toàn luôn có cách quay lại phiên bản đã biết là hoạt động tốt.

Trước khi triển khai:

- Giữ lại bộ cài hoặc archive JDK cũ theo chính sách lưu trữ.
- Giữ nguyên thư mục JDK cũ trong thời gian xác nhận bản mới.
- Ghi lại giá trị `JAVA_HOME`, PATH và cấu hình IDE/build trước thay đổi.
- Ghi lại tag hoặc digest container image trước khi cập nhật.
- Bảo đảm CI có thể chạy lại với JDK cũ.
- Xác định người chịu trách nhiệm và điều kiện kích hoạt rollback.

Nếu phát sinh lỗi nghiêm trọng, quay lại cấu hình JDK và image đã ghi nhận. Sau đó xác minh lại `java --version`, compiler, Maven/Gradle và chạy smoke test để bảo đảm rollback thực sự có hiệu lực.

Không nên gỡ bản JDK cũ hoặc xóa cache, image và cấu hình cũ ngay sau khi cài bản mới. Giữ khả năng quay lại cho tới khi đợt cập nhật được xác nhận ổn định.

Lưu ý: rollback JDK không tự động đảo ngược thay đổi dữ liệu mà ứng dụng đã ghi. Nếu bản cập nhật đi kèm thay đổi ứng dụng hoặc schema, cần kế hoạch rollback riêng cho những thành phần đó.

## 12. Cập nhật JDK trong CI và container

Môi trường CI và container thường là nơi dễ xảy ra chênh lệch giữa máy lập trình viên và production.

Với CI:

- Dùng phiên bản JDK được khai báo rõ trong pipeline.
- Kiểm tra JDK chạy agent và JDK compiler toolchain.
- Không dựa vào alias thay đổi theo thời gian nếu cần build tái lập.
- Chạy test trên phiên bản runtime production hỗ trợ.
- Lưu kết quả build và phiên bản JDK để truy vết khi có lỗi.

Với Docker:

- Chọn base image đúng vendor, feature release và hệ điều hành.
- Khi cần tính tái lập cao, cố định image digest thay vì chỉ dùng tag trôi nổi.
- Cập nhật image theo lịch bảo trì bảo mật.
- Build lại image ứng dụng và kiểm tra các lớp native hoặc agent phụ thuộc hệ điều hành.
- Không giả định container đang chạy dùng cùng JDK với máy host.

Ví dụ kiểm tra JDK trong container đang chạy:

```bash
docker exec <container-name> java --version
```

Lệnh này chạy Java launcher bên trong container. Thay `<container-name>` bằng tên hoặc ID container thực tế.

## 13. Những lỗi thường gặp khi cập nhật JDK

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `java --version` vẫn hiển thị bản cũ | PATH ưu tiên thư mục JDK cũ hoặc terminal chưa được mở lại | Kiểm tra thứ tự PATH và mở terminal mới |
| `javac` không cùng phiên bản với `java` | Hai lệnh được tìm từ các thư mục khác nhau | Kiểm tra đường dẫn cả hai lệnh và đồng bộ JDK |
| Maven hoặc Gradle vẫn dùng JDK cũ | Build tool có cấu hình JVM hoặc toolchain riêng | Kiểm tra `mvn -version`, `gradlew --version` và toolchain |
| IDE không nhận JDK mới | Project SDK hoặc build runner chưa cập nhật | Chọn JDK mới và reload project |
| Installer báo lỗi hoặc không cài được | Sai kiến trúc, quyền cài đặt, package conflict hoặc tệp tải lỗi | Kiểm tra checksum, hệ điều hành, kiến trúc và hướng dẫn nhà cung cấp |
| Ứng dụng không khởi động | Dependency, agent, native library hoặc cấu hình không tương thích | Đọc stack trace, release notes và kiểm tra thành phần liên quan |
| TLS hoặc kết nối HTTPS thất bại | Truststore, chứng chỉ, thuật toán hoặc policy bảo mật thay đổi | Kiểm tra certificate chain, truststore và cấu hình TLS |
| Hiệu năng thay đổi sau cập nhật | Khác biệt GC, JIT, workload hoặc cấu hình runtime | So sánh metrics và profile với baseline |
| Rollback nhưng vẫn chạy JDK mới | PATH, IDE, daemon hoặc container vẫn dùng cấu hình cũ | Kiểm tra từng tiến trình và khởi động lại thành phần cần thiết |

Một lỗi phổ biến là chỉ kiểm tra phiên bản của terminal mà bỏ qua JVM do IDE hoặc build daemon khởi chạy. Hãy xác minh ở đúng nơi ứng dụng thực sự chạy.

## 14. Checklist cho một đợt cập nhật JDK

Có thể dùng checklist sau cho mỗi lần bảo trì:

- [ ] Xác định lý do cập nhật và phiên bản đích.
- [ ] Xác nhận vendor, feature release, bản cập nhật và kiến trúc.
- [ ] Đọc release notes và security advisory.
- [ ] Ghi nhận JDK, đường dẫn và cấu hình hiện tại.
- [ ] Kiểm tra yêu cầu tương thích của framework, thư viện và plugin.
- [ ] Tải bộ cài từ nguồn đáng tin cậy.
- [ ] Xác minh checksum hoặc chữ ký số.
- [ ] Cài bản mới theo cách có thể giữ lại bản cũ.
- [ ] Cập nhật JAVA_HOME, PATH, IDE và build toolchain.
- [ ] Kiểm tra java, javac, Maven và Gradle.
- [ ] Chạy clean build, unit test và integration test.
- [ ] Chạy smoke test và kiểm tra hiệu năng trên staging.
- [ ] Cập nhật CI và container image.
- [ ] Triển khai theo giai đoạn và theo dõi metrics.
- [ ] Xác nhận điều kiện rollback và giữ bản JDK cũ trong thời gian cần thiết.
- [ ] Ghi lại kết quả, phiên bản cuối cùng và ngày cập nhật.

## 15. Tổng kết

Cập nhật JDK an toàn không chỉ là chạy installer mới. Cần biết chính xác JDK nào đang được sử dụng, xác minh nguồn và tính toàn vẹn của bộ cài, đọc release notes, kiểm tra tương thích và xác nhận ứng dụng hoạt động trên runtime mới.

Những nguyên tắc quan trọng:

- Phân biệt patch update với feature upgrade và thay đổi nhà cung cấp.
- Ghi nhận hiện trạng trước khi thay đổi.
- Tải JDK từ nguồn đáng tin cậy và xác minh checksum hoặc chữ ký.
- Giữ bản cũ để có thể rollback trong giai đoạn xác nhận.
- Cập nhật đúng cấu hình của terminal, IDE, Maven, Gradle, CI và container.
- Chạy build, test, smoke test và kiểm tra hiệu năng.
- Triển khai theo giai đoạn, theo dõi sau triển khai và ghi lại kết quả.

Quy trình này giúp đội Java nhận bản vá và cải tiến của JDK mà vẫn kiểm soát được tính tương thích, khả năng tái lập và độ ổn định của hệ thống.
