# Xác định nguồn tin cậy của công cụ, wrapper và artifact

Một build Java không chỉ chạy mã nguồn của dự án. Nó còn tải và thực thi JDK, Gradle hoặc Maven, wrapper, plugin, annotation processor, thư viện và đôi khi cả script hay công cụ bên ngoài. Mỗi thành phần đó có thể ảnh hưởng trực tiếp đến kết quả build và có thể thực thi mã trên runner CI. Nếu một thành phần bị thay thế, tải từ nguồn không đáng tin hoặc bị giả mạo, kẻ tấn công có thể thay đổi artifact đầu ra, lấy secret của CI hoặc chèn mã độc vào phần mềm được phát hành.

Vì vậy, câu hỏi quan trọng không chỉ là “file này có tải được không?” mà là **“file này đến từ đâu, ai chịu trách nhiệm phát hành, làm sao xác minh nó đúng là file đã được phát hành và build có thể chứng minh đã dùng file đó?”**

Bài học này trình bày cách xác định nguồn tin cậy của JDK, Gradle/Maven, wrapper, plugin và dependency; cách dùng HTTPS, checksum và chữ ký; cách khóa và xác minh artifact; cùng các biện pháp bảo vệ chuỗi cung ứng build trong CI.

## 1. Trust source là gì?

Nguồn tin cậy (trusted source) là nơi hoặc danh tính mà tổ chức chấp nhận làm căn cứ để lấy một công cụ hay artifact. Nguồn đó cần có:

- Danh tính nhà phát hành hoặc tổ chức sở hữu rõ ràng.
- Kênh phân phối được kiểm soát.
- Cơ chế xác thực kết nối và/hoặc xác minh nội dung.
- Chính sách phát hành và xử lý sự cố.
- Khả năng truy vết phiên bản, checksum, chữ ký hoặc provenance.

Ví dụ nguồn có thể được tổ chức chấp nhận:

- Trang phát hành chính thức của nhà cung cấp JDK.
- Gradle distribution service hoặc Maven distribution service chính thức.
- Plugin Portal hoặc repository nội bộ được quản trị.
- Maven Central hoặc registry package chính thức.
- Artifact repository nội bộ proxy các nguồn upstream đã được phê duyệt.
- Kho lưu trữ release bất biến do tổ chức vận hành.

Một website có HTTPS không tự động trở thành nguồn tin cậy. HTTPS giúp xác thực kết nối đến domain và bảo vệ dữ liệu trên đường truyền; nó không chứng minh domain đó là nhà phát hành đúng hoặc artifact trên đó không bị phát hành độc hại.

## 2. Chuỗi tin cậy của một build

Một build có thể phụ thuộc vào nhiều lớp:

```text
Máy/runner và hệ điều hành
          |
          v
JDK / Java runtime
          |
          v
Gradle hoặc Maven distribution
          |
          v
Wrapper scripts và wrapper JAR
          |
          v
Build logic và plugin
          |
          v
Dependency trực tiếp và bắc cầu
          |
          v
Compiler / test / packaging tools
          |
          v
Artifact đầu ra
          |
          v
Repository phát hành / deploy
```

Mỗi lớp có thể tải hoặc thực thi thành phần từ lớp khác. Ví dụ:

- Wrapper JAR tải Gradle distribution.
- Gradle tải plugin và dependency.
- Maven tải plugin goal và thư viện.
- Annotation processor chạy trong quá trình compile.
- Test plugin khởi chạy test worker và external process.
- Packaging plugin tạo JAR, WAR hoặc container image.

Nếu chỉ xác minh dependency ứng dụng nhưng không xác minh wrapper hoặc plugin, chuỗi tin cậy vẫn có lỗ hổng. Một plugin độc hại có thể đọc secret hoặc sửa artifact trước khi dependency ứng dụng được đóng gói.

## 3. Xác định nguồn chính thức trước khi tải

Khi chọn công cụ hoặc artifact, hãy xác định:

1. Tên chính xác của sản phẩm và nhà phát hành.
2. Domain phát hành chính thức.
3. Repository hoặc endpoint phân phối được nhà phát hành công bố.
4. Phiên bản cụ thể cần dùng.
5. Trang checksum hoặc chữ ký của đúng phiên bản.
6. Fingerprint khóa ký nếu có chữ ký.
7. Chính sách hỗ trợ, release và bảo mật của nhà phát hành.

Không nên tìm file thực thi bằng cách chọn kết quả đầu tiên của công cụ tìm kiếm hoặc tải từ trang mirror không rõ chủ sở hữu.

### Phân biệt nguồn gốc và bản sao

Một artifact có thể xuất hiện ở nhiều nơi:

- Trang chính thức của nhà phát hành.
- Repository công cộng.
- Mirror do trường học hoặc tổ chức vận hành.
- Cache/proxy repository nội bộ.
- File được đính kèm trong issue hoặc chat.

Các bản sao có thể hợp lệ, nhưng cần có đường xác minh ngược về nhà phát hành. Repository nội bộ nên ghi rõ nguồn upstream, cơ chế đồng bộ và cách xác minh artifact.

### Nguồn nội bộ cũng cần được quản trị

Không nên mặc định mọi file trong artifact repository nội bộ đều đáng tin. Cần xác định:

- Ai có quyền publish?
- Có tách quyền upload snapshot và release không?
- Có cho ghi đè release artifact không?
- Có audit log không?
- Có scan hoặc verify artifact trước khi promote không?
- Repository có proxy các upstream đã được allowlist không?
- Có kiểm soát dependency namespace để tránh dependency confusion không?

## 4. HTTPS bảo vệ điều gì?

HTTPS/TLS giúp:

- Xác thực certificate của server theo trust store của client.
- Mã hóa dữ liệu truyền qua mạng.
- Phát hiện thay đổi dữ liệu trong quá trình truyền.
- Giảm nguy cơ bị nghe lén hoặc sửa dữ liệu trên đường truyền.

HTTPS không tự xác nhận:

- Artifact do đúng dự án phát hành.
- Người có quyền publish không bị xâm nhập.
- Repository không bị compromise.
- Artifact không chứa mã độc.
- Version được chọn là version mà tổ chức đã review.

Vì vậy, HTTPS là lớp bảo vệ cơ bản cần có, nhưng nên kết hợp checksum, chữ ký, dependency verification, repository policy và provenance khi mức độ rủi ro yêu cầu.

Không tắt TLS certificate validation để “sửa nhanh” lỗi certificate. Nếu runner dùng certificate nội bộ, hãy cài trust chain đúng vào hệ điều hành hoặc JDK theo hướng dẫn của quản trị viên.

## 5. Checksum là gì?

Checksum là giá trị hash tính từ nội dung file. Khi tải một distribution hoặc artifact, có thể tính SHA-256 trên file và so sánh với giá trị được nhà phát hành công bố qua kênh tin cậy.

Ví dụ Linux:

```bash
sha256sum gradle-8.10.2-bin.zip
```

Ví dụ macOS:

```bash
shasum -a 256 gradle-8.10.2-bin.zip
```

Ví dụ PowerShell:

```powershell
Get-FileHash .\gradle-8.10.2-bin.zip -Algorithm SHA256
```

Nếu hash tính được khác hash chính thức, không sử dụng file đó. Hãy kiểm tra lại file tải, URL, proxy/cache và hướng dẫn phát hành.

### Checksum chứng minh điều gì?

Checksum giúp xác nhận nội dung file đang kiểm tra khớp với nội dung tương ứng của giá trị hash tham chiếu.

Nhưng checksum chỉ hữu ích khi giá trị tham chiếu đến từ nguồn đáng tin cậy. Nếu tải file ZIP và file SHA256 từ cùng một server đã bị xâm nhập, kẻ tấn công có thể thay cả hai. Khi đó, hai giá trị vẫn khớp nhưng artifact không đáng tin.

Vì vậy, cần phân biệt:

- Hash được tính cục bộ để so sánh.
- Hash do nhà phát hành công bố.
- Hash được truyền qua một kênh độc lập hoặc được ký.
- Hash đã được tổ chức review và lưu trong repository.

## 6. Chữ ký số và xác minh nhà phát hành

Chữ ký số cho phép xác minh nội dung được ký bởi người nắm private key tương ứng. Người xác minh dùng public key để kiểm tra chữ ký và bảo đảm nội dung không thay đổi kể từ khi được ký.

Một chữ ký chỉ đáng tin khi public key được gắn với danh tính nhà phát hành qua một quy trình tin cậy.

Quy trình thường gồm:

1. Lấy public key hoặc certificate từ kênh chính thức.
2. Kiểm tra fingerprint qua kênh độc lập hoặc tài liệu tin cậy.
3. Lưu public key vào trust store/keyring được quản lý.
4. Tải artifact và signature.
5. Xác minh signature.
6. Kiểm tra key còn hợp lệ, chưa bị thu hồi và đúng mục đích.
7. Ghi nhận phiên bản, fingerprint và kết quả xác minh.

### Fingerprint quan trọng hơn tên hiển thị

Tên người ký hoặc email trong metadata có thể được tự khai báo. Fingerprint là định danh của public key và cần được đối chiếu với nguồn đáng tin cậy.

Không nên chỉ import bất kỳ key nào đi kèm artifact rồi coi chữ ký là hợp lệ. Nếu attacker thay cả artifact và key, chữ ký vẫn có thể verify về mặt toán học nhưng danh tính người ký không được xác thực.

### Checksum và chữ ký khác nhau

| Cơ chế | Xác nhận | Giới hạn |
|---|---|---|
| SHA-256 checksum | Nội dung khớp giá trị hash tham chiếu | Không tự xác nhận ai tạo hash |
| Digital signature | Nội dung được ký bởi private key tương ứng | Cần xác minh public key và danh tính |
| HTTPS/TLS | Kết nối tới server có certificate hợp lệ | Không tự chứng minh artifact là release đúng |
| Provenance attestation | Thông tin về cách, nơi và workflow tạo artifact | Cần xác minh issuer, subject và policy |
| SBOM | Danh sách thành phần trong artifact | Không chứng minh artifact an toàn hoặc không bị sửa |

Các cơ chế này bổ sung cho nhau.

## 7. Xác định nguồn tin cậy của JDK

JDK là nền tảng thực thi compiler, build tool, plugin và test. JDK không đáng tin có thể thay đổi bytecode, can thiệp process hoặc đọc dữ liệu trong CI.

Khi chọn JDK:

- Xác định vendor và distribution được tổ chức chấp nhận.
- Tải từ trang hoặc repository chính thức của vendor.
- Pin phiên bản JDK và, nếu cần, patch release cụ thể.
- Xác minh checksum/chữ ký theo hướng dẫn của vendor.
- Dùng toolchain để build không phụ thuộc JDK ngẫu nhiên trên máy runner.
- Ghi nhận vendor, version và build number trong build metadata.
- Cập nhật JDK theo lịch và xử lý security update kịp thời.

### Không chỉ kiểm tra java -version

Lệnh:

```bash
java -version
javac -version
```

cho biết version mà PATH hiện tại đang chọn, nhưng không chứng minh distribution đó đến từ đâu hoặc đã được xác minh thế nào.

Có thể có nhiều JDK trên runner. JAVA_HOME, PATH, Gradle toolchain và Maven toolchains có thể trỏ đến các bản khác nhau. Hãy xác định JDK thực sự dùng để chạy build và JDK dùng để compile/test.

### Gradle Java Toolchains

Ví dụ:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}
```

Cấu hình này yêu cầu toolchain Java 21 từ vendor phù hợp. Nó giúp build không phụ thuộc JDK mặc định trong PATH, nhưng việc tải và chọn distribution vẫn cần chính sách nguồn tin cậy. Cấu hình toolchain không tự xác minh mọi JDK download source.

Trong CI, có thể cài JDK từ image hoặc setup action đã được pin và xác minh. Nếu dùng container, pin image theo digest khi cần tính tái lập và xác minh nguồn image.

## 8. Xác định nguồn tin cậy của Gradle distribution

Gradle Wrapper giúp mọi người trong dự án dùng cùng phiên bản Gradle. File cấu hình quan trọng thường là:

```text
gradle/wrapper/gradle-wrapper.properties
```

Ví dụ:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.10.2-bin.zip
distributionSha256Sum=<sha256 đã xác minh>
```

distributionUrl chỉ định distribution cần tải. distributionSha256Sum cho phép wrapper kiểm tra SHA-256 của distribution đã tải.

Giá trị checksum trong ví dụ là placeholder. Trong dự án thật, hãy lấy checksum chính xác từ kênh phát hành chính thức của đúng version và xác minh trước khi commit.

### Vì sao phải pin version?

Nếu URL trỏ đến một version cố định, build có thể tải lại cùng phiên bản Gradle theo cấu hình. Không nên dùng URL động, nightly hoặc distribution không rõ nguồn cho release build.

Ví dụ pin:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.10.2-bin.zip
```

Nếu cần đổi version, thay đổi wrapper nên được review như một dependency/toolchain update: đọc release notes, kiểm tra compatibility, xác minh checksum và chạy build trên CI.

### -bin và -all

Gradle cung cấp các distribution khác nhau, ví dụ:

- -bin: runtime distribution gọn hơn, thường phù hợp cho CI và người dùng build.
- -all: bao gồm thêm source/documentation, hữu ích cho IDE hoặc phát triển Gradle plugin.

Dùng đúng loại cần thiết giúp giảm download. Dù chọn loại nào, vẫn cần pin version và xác minh checksum.

## 9. Gradle Wrapper gồm những thành phần nào?

Trong repository thường có:

```text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
```

- gradlew: script khởi chạy trên Unix-like.
- gradlew.bat: script khởi chạy trên Windows.
- gradle-wrapper.jar: mã Java thực thi wrapper.
- gradle-wrapper.properties: cấu hình distribution và checksum.

Wrapper script và wrapper JAR được commit vào source repository. Vì chúng được chạy trước Gradle distribution, cần xem chúng là code quan trọng trong chuỗi tin cậy.

### Kiểm tra wrapper JAR

Gradle cung cấp checksum chính thức cho wrapper JAR theo version. Khi nâng wrapper, nên xác minh wrapper JAR đã commit khớp bản được Gradle phát hành. Có thể dùng quy trình hoặc action validation wrapper được tổ chức chấp thuận, nhưng phải pin action theo commit SHA và xác minh nguồn action.

Không chỉ xác minh distribution ZIP rồi bỏ qua wrapper JAR. Một wrapper JAR bị sửa có thể chạy mã tùy ý trước khi tải distribution.

### Kiểm tra wrapper scripts

Review thay đổi trong gradlew và gradlew.bat. Các script không nên có đoạn tải thêm binary từ URL không liên quan, gửi environment ra ngoài hoặc bỏ qua checksum.

Khi cập nhật wrapper, hãy kiểm tra cả bốn file liên quan và diff trước khi merge.

## 10. Cập nhật Gradle Wrapper an toàn

Có thể dùng:

```bash
./gradlew wrapper --gradle-version 8.10.2
```

Sau khi chạy, kiểm tra:

- gradle-wrapper.properties trỏ đúng distribution URL.
- distributionSha256Sum được thiết lập với checksum chính thức.
- gradle-wrapper.jar đúng bản phát hành.
- gradlew và gradlew.bat không có thay đổi bất thường.
- CI chạy được trên JDK được hỗ trợ.
- Plugin và build logic tương thích version Gradle mới.

Có thể chạy wrapper task lần nữa theo hướng dẫn Gradle để cập nhật các wrapper files lên phiên bản implementation mới nhất phù hợp. Đừng giả định một lần chạy task đã cập nhật mọi thành phần theo cách mong muốn; hãy xem diff thực tế.

## 11. Xác định nguồn tin cậy của Maven distribution và Maven Wrapper

Maven Wrapper cho phép dự án cố định Maven version. Các file thường gặp:

```text
mvnw
mvnw.cmd
.mvn/wrapper/maven-wrapper.properties
.mvn/wrapper/maven-wrapper.jar
```

Tùy kiểu wrapper được tạo, file wrapper JAR hoặc script downloader có thể khác nhau. Hãy kiểm tra các file được commit và loại wrapper mà dự án sử dụng.

Trong maven-wrapper.properties, distributionUrl xác định Maven distribution. Có thể cấu hình checksum distribution nếu wrapper version hỗ trợ, ví dụ thuộc tính distributionSha256Sum. Hãy xác nhận cú pháp với version wrapper thực tế của dự án.

Ví dụ minh họa:

```properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
distributionSha256Sum=<sha256 đã xác minh>
```

Không dùng placeholder checksum trong dự án. Lấy checksum đúng từ nguồn Maven chính thức, xác minh và commit cùng thay đổi wrapper.

### Kiểm tra wrapper files

- Xác minh URL trỏ đúng Maven distribution và version đã chọn.
- Xác minh checksum nếu wrapper hỗ trợ.
- Review mvnw, mvnw.cmd và wrapper JAR/script.
- Không cho wrapper tải script hoặc binary phụ từ nguồn không rõ.
- Pin wrapper version và kiểm tra CI.
- Không commit credential repository vào wrapper properties.

## 12. Wrapper không thay thế xác minh build tool

Wrapper đảm bảo người dùng khởi chạy phiên bản được cấu hình trong repository, nhưng chỉ khi wrapper files và distribution source đáng tin.

Nếu attacker sửa gradlew, mvnw hoặc wrapper JAR, họ có thể thực thi mã trước khi build tool chính thức khởi chạy. Nếu distribution URL bị thay đổi, wrapper có thể tải binary từ nguồn khác.

Vì vậy, review wrapper files là một phần của code review bảo mật. Branch protection và CODEOWNERS có thể yêu cầu người có trách nhiệm review thay đổi ở:

- gradlew, gradlew.bat.
- gradle/wrapper/**.
- mvnw, mvnw.cmd.
- .mvn/wrapper/**.
- Root build files và settings.
- Plugin management và repository definitions.

## 13. Xác định nguồn tin cậy của Gradle plugin

Plugin Gradle là mã được thực thi trong build. Nó có thể đọc source, environment, file hệ thống và network tùy quyền của process.

Ví dụ:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
}
```

Khi chọn plugin, hãy kiểm tra:

- Plugin ID chính xác.
- Tổ chức/nhà phát hành.
- Repository chính thức.
- Version và release notes.
- Mức độ duy trì và lịch sử bảo mật.
- Dependencies mà plugin kéo theo.
- Source code hoặc tài liệu nếu cần đánh giá sâu.
- Plugin có tương thích Gradle/JDK của dự án không.

Không cài plugin chỉ vì tên gần giống plugin phổ biến. Typosquatting có thể lợi dụng lỗi đánh máy trong plugin ID hoặc artifact coordinates.

### Quản lý plugin repository

Trong settings:

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        maven {
            url = uri('https://repo.example.com/gradle-plugins')
            content {
                includeGroupByRegex 'com\\.example(\\..*)?'
            }
        }
    }
}
```

Chỉ thêm repository cần thiết và giới hạn namespace nếu phù hợp. Không nên thêm repository bất kỳ chỉ để giải quyết lỗi plugin not found mà chưa xác định nguồn phát hành.

### Pin plugin version

Tránh phụ thuộc vào version ngầm hoặc dynamic selector. Dùng version cụ thể và cập nhật có chủ đích. Với plugin áp dụng qua pluginManagement hoặc convention plugin, quản lý version tập trung để reviewer nhìn thấy thay đổi.

## 14. Xác định nguồn tin cậy của Maven plugin

Maven plugin cũng là code thực thi trong build. Ví dụ compiler, Surefire, Failsafe, shade, signing và deploy plugin.

Nên khai báo version rõ ràng:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
        </plugin>
    </plugins>
</build>
```

Không nên để plugin quan trọng tự dùng version không rõ hoặc phụ thuộc vào mặc định khác nhau giữa môi trường.

### Plugin repositories

Maven có thể dùng pluginRepositories để tìm plugin:

```xml
<pluginRepositories>
    <pluginRepository>
        <id>company-plugins</id>
        <url>https://repo.example.com/maven-plugins</url>
    </pluginRepository>
</pluginRepositories>
```

Repository plugin cần được quản trị giống repository dependency. Chỉ thêm nguồn đã được phê duyệt và giới hạn quyền publish.

### Quản lý plugin qua parent POM

Với multi-module Maven, có thể quản lý version plugin tập trung trong parent POM hoặc pluginManagement. Cần hiểu pluginManagement cung cấp cấu hình/version quản lý; module vẫn phải áp dụng plugin theo cấu trúc build tương ứng.

## 15. Xác định nguồn tin cậy của dependency

Dependency có thể đến trực tiếp hoặc bắc cầu. Một thư viện trực tiếp được chọn từ repository tin cậy vẫn có thể kéo theo nhiều module khác.

Khi review dependency:

- Kiểm tra group, artifact và version.
- Xác định repository được dùng.
- Kiểm tra dependency bắc cầu.
- Kiểm tra version được chọn sau conflict resolution.
- Xác minh artifact theo chính sách checksum/chữ ký.
- Xem xét maintainer, release history và advisory bảo mật.
- Tránh dependency không còn được duy trì nếu có lựa chọn phù hợp.
- Kiểm tra tên package có nguy cơ typosquatting hoặc dependency confusion.

### Dependency confusion

Một tình huống rủi ro xảy ra khi project dùng package nội bộ với namespace không được kiểm soát, trong khi build cũng tìm package từ public repository. Attacker có thể publish package cùng tên hoặc version cao hơn ở public registry để build resolve nhầm.

Giảm rủi ro:

- Dùng namespace/group nội bộ riêng.
- Dùng repository content filter hoặc exclusive content.
- Quản lý repository order và repository policy.
- Proxy upstream qua repository manager.
- Chặn package nội bộ bị resolve từ public registry.
- Review dependency graph khi thêm dependency mới.

## 16. Gradle dependency verification

Gradle hỗ trợ dependency verification để xác minh checksum hoặc chữ ký của artifact được resolve.

Metadata thường được lưu trong:

```text
gradle/verification-metadata.xml
```

Có thể tạo checksum metadata ban đầu:

```bash
./gradlew --write-verification-metadata sha256 help
```

Lệnh này resolve dependency cần cho task được gọi và ghi metadata checksum cho những artifact quan sát được. Trong thực tế, cần chạy các task/configuration phù hợp để bao phủ dependency của build rồi review file được tạo.

### Không chấp nhận checksum một cách mù quáng

Nếu checksum được tạo từ artifact vừa tải qua repository chưa được xác minh, nó chỉ ghi lại nội dung đã nhận, không tự chứng minh nội dung đó tốt hoặc đúng nhà phát hành.

Trước khi commit metadata:

1. Xác định nguồn artifact.
2. Đối chiếu checksum/chữ ký với nguồn tin cậy nếu có.
3. Review thay đổi trong verification metadata.
4. Xác nhận các artifact mới thực sự thuộc dependency update mong muốn.
5. Commit metadata cùng thay đổi dependency đã được chấp nhận.

### Chế độ xác minh

Gradle verification metadata có thể cấu hình checksum, trusted key và policy. Có thể dùng strict verification để build thất bại khi artifact không có thông tin xác minh phù hợp theo policy. Hãy đọc tài liệu Gradle của version đang dùng và tạo metadata đầy đủ trước khi bật strict mode cho toàn build.

Một file verification metadata được quản lý trong Git giúp các developer và CI áp dụng cùng chính sách.

## 17. Maven checksum và chữ ký artifact

Maven repository thường cung cấp checksum cạnh artifact. Maven Resolver có thể kiểm tra checksum theo cấu hình checksum policy của repository.

Tuy nhiên, checksum từ cùng repository không phải bằng chứng độc lập về danh tính nhà phát hành. Nó giúp phát hiện truyền tải hỏng hoặc nội dung không khớp metadata checksum, nhưng nếu repository bị compromise cả artifact và checksum đều có thể bị thay.

Với artifact được ký, có thể xác minh chữ ký bằng public key/fingerprint của nhà phát hành qua quy trình đã được tin cậy. Maven ecosystem cũng có thể dùng GPG signing plugin trong quy trình publish.

Một số điểm cần nhớ:

- Kiểm tra chữ ký phải dùng public key đã xác minh.
- Không import key chỉ vì nó đi kèm file tải.
- Xác minh fingerprint qua nguồn độc lập.
- Quản lý key rotation và key revocation.
- Không để private signing key trong source repository.
- Ưu tiên HSM/KMS hoặc signing service nếu tổ chức hỗ trợ.

## 18. Repository manager và proxy nội bộ

Một tổ chức có thể dùng Nexus, Artifactory hoặc repository manager khác để proxy dependency từ upstream và quản lý artifact nội bộ.

Lợi ích:

- Một điểm truy cập được kiểm soát cho build.
- Cache artifact để giảm phụ thuộc mạng.
- Chính sách allowlist/denylist.
- Phân tách hosted, proxy và group repository.
- Audit log và quyền publish.
- Quản lý retention và promotion.
- Có thể scan/verify artifact trước khi cho phép dùng.

Nhưng repository manager chỉ đáng tin khi được cấu hình và quản trị tốt. Cần kiểm tra:

- Upstream nào được proxy?
- Có cho người dùng publish vào proxy repository không?
- Release artifact có bị overwrite không?
- Ai có quyền quản trị?
- Credential có được bảo vệ?
- Metadata có thể bị sửa bởi ai?
- Có backup, audit và incident process không?

Không nên coi cache nội bộ là nguồn tin cậy tuyệt đối chỉ vì nó nằm trong mạng công ty.

## 19. Pin version và lock dependency graph

Pin version giúp build biết chính xác phiên bản trực tiếp cần dùng. Locking giúp ghi nhận phiên bản đã resolve, bao gồm dependency bắc cầu.

Với Gradle:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Tạo hoặc cập nhật lock state bằng task resolve phù hợp:

```bash
./gradlew build --write-locks
```

Lockfile thường là gradle.lockfile hoặc định dạng lock tương ứng với Gradle version. Commit lockfile vào version control.

Với Maven, quản lý version qua exact version, BOM và dependencyManagement. Có thể bổ sung plugin/tool để ghi nhận dependency graph hoặc kiểm tra convergence nếu cần. Maven không có cơ chế lockfile tích hợp tương đương Gradle trong mọi dự án.

Pin version và lockfile hỗ trợ tái lập nhưng không tự xác minh nội dung artifact. Kết hợp với checksum/signature verification và repository immutability khi yêu cầu.

## 20. Kiểm soát source repository và build logic

Nguồn tin cậy của công cụ còn phụ thuộc source repository chứa build logic.

Những file nhạy cảm với supply chain:

- settings.gradle, settings.gradle.kts.
- build.gradle, build.gradle.kts.
- gradle/libs.versions.toml.
- gradle/wrapper/**.
- pom.xml.
- Parent POM.
- .mvn/wrapper/**.
- mvnw, mvnw.cmd.
- CI workflow YAML.
- Dockerfile và build scripts.
- Script tải/cài tool.
- Convention plugin và buildSrc/included build.

Một thay đổi ở những file này có thể thêm repository, plugin, script hoặc credential access. Branch protection, required review và CODEOWNERS giúp đảm bảo thay đổi được người có trách nhiệm xem xét.

### Review thay đổi repository

Khi pull request thêm repository mới, hãy hỏi:

- Vì sao cần nguồn này?
- Ai sở hữu domain?
- Artifact nào sẽ được resolve từ đó?
- Có thể giới hạn content theo group không?
- Có thể dùng proxy nội bộ đã được phê duyệt không?
- Có nguy cơ dependency confusion không?
- Có cần xác minh checksum/chữ ký bổ sung không?

## 21. CI action, container image và runner cũng là công cụ

Build supply chain không chỉ có Gradle/Maven. CI thường sử dụng action, reusable workflow, container image và runner image.

### Pin CI action

Không nên chỉ tham chiếu action bằng tag có thể di chuyển nếu policy yêu cầu nguồn cố định. Pin theo commit SHA đầy đủ giúp workflow tham chiếu một revision cụ thể. Review SHA và nguồn action trước khi chấp nhận.

Ví dụ minh họa:

```yaml
- uses: actions/checkout@<reviewed-full-commit-sha>
```

Placeholder không phải giá trị dùng được. Hãy lấy SHA đã review từ repository chính thức của action và cập nhật có chủ đích.

### Pin container image

Tag như gradle:8.10.2-jdk21 vẫn có thể được registry cập nhật theo chính sách tag. Khi cần xác định chính xác image content, pin bằng digest:

```yaml
container:
  image: gradle:8.10.2-jdk21@sha256:<verified-image-digest>
```

Digest phải được lấy và xác minh từ registry tin cậy. Khi nâng image, review cả JDK, OS packages, Gradle và thành phần đi kèm.

### Runner

Runner cũng là một phần của trust boundary:

- Ưu tiên runner được quản lý và cập nhật.
- Dùng runner ephemeral cho job không tin cậy.
- Không chia sẻ workspace giữa job có mức tin cậy khác nhau.
- Giới hạn network egress và quyền truy cập nội bộ.
- Không để credential tồn tại sau job.
- Theo dõi image/OS patch level.

## 22. Kiểm tra provenance của artifact

Provenance là thông tin mô tả artifact được tạo từ source nào, bởi workflow nào, trên builder nào và với những tham số nào.

Một provenance attestation hữu ích có thể bao gồm:

- Artifact digest.
- Source repository và commit.
- Build workflow identity.
- Builder/toolchain identity.
- Build invocation hoặc parameters.
- Thời gian tạo.
- Quan hệ giữa artifact và source.

Provenance giúp người nhận đánh giá artifact có được tạo bởi pipeline mong muốn hay không. Nhưng phải xác minh chữ ký attestation và trust policy của issuer. Một file provenance không ký hoặc do nguồn không tin cậy tạo ra không tự tăng độ tin cậy.

### Liên kết artifact với digest

Khi phát hành, ghi nhận SHA-256 của artifact:

```bash
sha256sum application.jar
```

Lưu digest cùng version, commit và build ID. Khi artifact được tải về để deploy, tính lại digest và so sánh với digest đã được ghi nhận qua kênh tin cậy.

Không chỉ dựa vào tên file hoặc version string, vì tên file có thể bị thay nội dung.

## 23. SBOM cho biết artifact chứa những thành phần nào

SBOM (Software Bill of Materials) là danh sách thành phần phần mềm trong artifact hoặc sản phẩm.

SBOM có thể ghi:

- Tên package.
- Version.
- Package URL hoặc coordinates.
- Supplier/author khi có.
- License.
- Dependency relationship.
- Checksum hoặc external reference.
- Thông tin định danh component.

SBOM hữu ích để:

- Tra cứu dependency khi có CVE.
- Xác định artifact nào chứa thư viện bị ảnh hưởng.
- So sánh thành phần giữa các release.
- Hỗ trợ audit và compliance.
- Cung cấp dữ liệu cho vulnerability scanner.

SBOM không phải chứng nhận artifact an toàn. Nó có thể thiếu thành phần hoặc chứa metadata sai nếu được tạo từ đầu vào không đầy đủ. Cần tạo từ build/release process tin cậy và liên kết với digest của artifact.

## 24. Vulnerability scanning và nguồn dữ liệu

Sau khi biết dependency graph và SBOM, có thể quét lỗ hổng bằng công cụ phù hợp. Kết quả phụ thuộc database advisory và cách tool ánh xạ package/version.

Cần xem xét:

- Nguồn advisory và thời điểm cập nhật.
- Dependency trực tiếp hay bắc cầu.
- Phiên bản thực tế được resolve.
- Có bị ảnh hưởng ở code path đang dùng không.
- Có bản vá hoặc workaround không.
- False positive và phạm vi áp dụng.
- Thời hạn xử lý theo mức độ nghiêm trọng.

Không nên bỏ qua cảnh báo chỉ vì scanner không tìm thấy khai báo trực tiếp trong POM/build.gradle; dependency có thể đến bắc cầu. Ngược lại, không nên kết luận mọi package có CVE đều có thể khai thác trong mọi ứng dụng. Cần đánh giá phiên bản, cấu hình và cách sử dụng.

## 25. Promotion artifact thay vì build lại ở từng môi trường

Một quy trình phát hành đáng tin thường tạo artifact một lần từ commit đã được kiểm chứng, sau đó promote cùng artifact qua các môi trường.

```text
Source commit
     |
     v
Trusted CI build
     |
     v
Compile + test + scan
     |
     v
Create artifact + digest + provenance
     |
     v
Staging repository
     |
     v
Approval / release policy
     |
     v
Promote same artifact to release repository
     |
     v
Deploy verified digest
```

Nếu build lại riêng cho staging và production, dependency resolution, thời gian, environment hoặc toolchain có thể khác, dẫn đến artifact không giống nhau.

Promotion giữ nguyên bytes của artifact đã được kiểm chứng. Nếu cần cấu hình theo môi trường, nên inject configuration ở runtime hoặc tạo artifact theo quy trình đã xác định, không thay nội dung tùy tiện sau khi ký.

## 26. Immutable release repository

Release artifact nên bất biến sau khi publish. Nếu cùng tọa độ group:artifact:version có thể bị ghi đè, tên version không còn là định danh nội dung đáng tin.

Chính sách nên gồm:

- Cấm redeploy/overwrite release version.
- Tách snapshot và release repository.
- Chỉ release job được publish vào release repository.
- Bật audit log.
- Kiểm tra checksum/digest sau publish.
- Lưu metadata về source commit và build.
- Có quy trình thu hồi hoặc đánh dấu artifact bị compromise.
- Không dùng quyền admin repository trong build job thông thường.

Với snapshot, có thể có chính sách cập nhật khác, nhưng không nên dùng snapshot làm artifact production mà không ghi nhận timestamp/digest chính xác.

## 27. Typosquatting và dependency confusion

Attacker có thể tạo package có tên gần giống package phổ biến hoặc tên nội bộ. Ví dụ nhóm định dùng com.company:security-client nhưng gõ nhầm group hoặc artifact và resolve package public do attacker kiểm soát.

Biện pháp giảm rủi ro:

- Review coordinates khi thêm dependency.
- Dùng namespace riêng cho artifact nội bộ.
- Dùng repository content filters/exclusive content.
- Kiểm soát repository được phép.
- Dùng proxy repository và allowlist.
- Kiểm tra maintainer, release history và source.
- Dùng dependency verification.
- Scan dependency graph và SBOM.
- Theo dõi package mới có tên gần giống dependency quan trọng.

Không nên thêm public repository tùy tiện vào build chỉ để “thử xem có tải được không”.

## 28. Artifact từ cache có đáng tin không?

Cache tăng tốc nhưng không tự xác nhận nguồn gốc. Một cache có thể giữ:

- Artifact dependency tải từ upstream.
- Gradle/Maven plugin.
- Build output.
- Generated source.
- Metadata resolution.
- File từ job trước.

Cần xác định cache được tạo bởi job nào, ở trust domain nào và ai có thể ghi/đọc.

Một nguyên tắc quan trọng: không để job không tin cậy ghi vào cache được job release tin cậy khôi phục. Nếu pull request từ fork có thể đầu độc cache rồi main/release build dùng lại, attacker có thể tác động đến artifact đầu ra.

Biện pháp:

- Tách cache key và namespace theo trust level.
- Không chia sẻ writable cache giữa untrusted PR và release job.
- Dùng remote build cache có quyền ghi/đọc riêng.
- Xác minh dependency artifact bằng checksum/chữ ký.
- Dùng runner ephemeral.
- Kiểm soát cache restore path và file được lưu.
- Không cache secret/config credential.

## 29. Kiểm tra nguồn trước khi thêm dependency hoặc plugin mới

Một quy trình review có thể hỏi:

1. Package/plugin ID có đúng chính tả và namespace không?
2. Nhà phát hành là ai?
3. Repository chính thức nằm ở đâu?
4. Version có được pin không?
5. Release notes có giải thích thay đổi không?
6. Dependency bắc cầu là gì?
7. Có artifact signature hoặc checksum đáng tin cậy không?
8. Có advisory bảo mật hoặc lịch sử compromise không?
9. Plugin có quyền thực thi gì trong build?
10. Có thể thay bằng dependency/plugin đã được tổ chức phê duyệt không?
11. Có cần thêm verification metadata, allowlist hoặc policy exception không?
12. Ai chịu trách nhiệm cập nhật và theo dõi dependency này?

Đối với plugin build, mức kiểm tra nên nghiêm ngặt vì plugin chạy trong process build và có thể tiếp cận environment của CI.

## 30. Xử lý checksum hoặc chữ ký không khớp

Nếu checksum không khớp hoặc chữ ký không xác minh được:

- Dừng sử dụng artifact đó.
- Không tắt verification để tiếp tục release.
- Kiểm tra URL và version.
- Kiểm tra file có bị tải thiếu hoặc proxy cache hỏng không.
- Lấy lại checksum/chữ ký từ nguồn chính thức.
- Xác minh fingerprint và key status.
- Kiểm tra repository manager và audit log.
- Thông báo đội phụ trách nếu có dấu hiệu compromise.
- Chỉ tiếp tục sau khi có kết luận và artifact được xác minh.

Không nên cập nhật checksum metadata chỉ để build pass khi chưa xác định vì sao hash thay đổi. Làm vậy có thể biến verification thành thủ tục chấp nhận nội dung không rõ nguồn.

## 31. Khi phát hiện công cụ hoặc artifact bị compromise

Một quy trình phản ứng:

1. Dừng promotion/deploy artifact bị ảnh hưởng.
2. Xác định digest, version và build run đã dùng artifact.
3. Xác định source commit, wrapper, plugin và dependency liên quan.
4. Kiểm tra provenance, signature, repository audit log và CI logs.
5. Thu hồi credential có thể đã bị process độc hại truy cập.
6. Cô lập runner hoặc cache nghi bị đầu độc.
7. Tìm các build và release khác dùng cùng component.
8. Thay thế bằng version đã xác minh hoặc artifact sạch.
9. Rebuild từ source và môi trường tin cậy.
10. Lưu bằng chứng, cập nhật allowlist/verification policy và thông báo các bên liên quan.

Nếu plugin độc hại đã chạy trong CI, cần xem xét khả năng secret, signing key hoặc deploy credential bị lộ. Chỉ xóa dependency khỏi build file có thể chưa đủ; token và key liên quan có thể phải rotate.

## 32. Ví dụ Gradle: một bộ kiểm soát nguồn tin cậy

Một build có thể kết hợp repository được giới hạn, version rõ ràng, locking và verification metadata.

Ví dụ repository:

```groovy
repositories {
    mavenCentral()

    maven {
        name = 'companyReleases'
        url = uri('https://repo.example.com/maven/releases')
        content {
            includeGroupByRegex 'com\\.company(\\..*)?'
        }
    }
}
```

Bật dependency locking:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Tạo lock state sau khi resolve configuration cần thiết:

```bash
./gradlew build --write-locks
```

Tạo verification metadata ban đầu:

```bash
./gradlew --write-verification-metadata sha256 help
```

Sau đó review gradle.lockfile và gradle/verification-metadata.xml, đối chiếu checksum với nguồn tin cậy và commit thay đổi. Cấu hình này minh họa các lớp khác nhau; dự án cần bảo đảm mọi subproject/configuration quan trọng đều được áp dụng policy.

## 33. Ví dụ Maven: pin plugin, quản lý repository và xác minh

Parent POM có thể quản lý plugin version tập trung:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Repository và plugin repository cần được cấu hình theo nguồn đã được phê duyệt. Credential đặt trong user settings, không nằm trong parent POM.

Khi release, có thể yêu cầu signing plugin ký artifact và publish checksum/signature theo policy. Consumer hoặc pipeline downstream xác minh chữ ký bằng key đã được xác thực độc lập.

Maven plugin/version pinning, BOM và dependency management hỗ trợ tái lập resolution. Chúng cần đi cùng repository policy, artifact immutability và xác minh nguồn phát hành.

## 34. Quy trình trust review cho một thay đổi build

Khi pull request thay đổi wrapper, JDK, plugin, repository hoặc dependency:

1. Xác định chính xác thành phần nào thay đổi.
2. Xác định nguồn chính thức và nhà phát hành.
3. Kiểm tra version, release notes và support matrix.
4. Xác minh checksum hoặc chữ ký theo policy.
5. Kiểm tra repository URL và content scope.
6. Review wrapper scripts/JAR hoặc build logic.
7. Kiểm tra dependency graph và version bắc cầu.
8. Cập nhật lockfile/verification metadata nếu cần.
9. Chạy CI trên runner/toolchain được quản lý.
10. Tạo SBOM/provenance nếu quy trình release yêu cầu.
11. Ghi digest và build metadata.
12. Chỉ promote artifact sau khi kiểm tra và approval hoàn tất.

## 35. Checklist xác định nguồn tin cậy

Trước khi sử dụng công cụ hoặc artifact, hãy xác định:

- Nhà phát hành và domain chính thức là ai?
- Repository này được tổ chức phê duyệt chưa?
- Version có được pin cụ thể không?
- Có checksum/chữ ký từ kênh tin cậy không?
- Fingerprint public key đã được xác minh độc lập chưa?
- Wrapper scripts/JAR có thay đổi bất thường không?
- Distribution URL có dùng HTTPS và đúng host không?
- JDK, build tool và plugin có được quản lý version không?
- Dependency bắc cầu có được kiểm soát không?
- Có dependency verification hoặc repository checksum policy không?
- Artifact release có bất biến không?
- CI action/container image/runner có nguồn tin cậy không?
- Cache có được tách theo trust level không?
- Có provenance/SBOM và digest cho artifact phát hành không?
- Có người review thay đổi build logic và repository không?

## 36. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| HTTPS nghĩa là artifact chắc chắn an toàn | HTTPS bảo vệ kết nối; không chứng minh artifact do nhà phát hành đúng tạo ra. |
| Checksum khớp là đủ | Cần xác minh nguồn cung cấp checksum; hash từ cùng nguồn bị compromise không tạo trust độc lập. |
| Chữ ký verify được nghĩa là người ký đáng tin | Phải xác minh public key/fingerprint và trạng thái key. |
| Wrapper giúp build an toàn tự động | Wrapper cố định phiên bản; wrapper script/JAR và distribution URL vẫn phải được xác minh. |
| Chỉ cần xác minh dependency ứng dụng | JDK, build tool, wrapper, plugin, action và container image cũng nằm trong chuỗi tin cậy. |
| Repository nội bộ luôn đáng tin | Cần quản trị upstream, quyền publish, audit, immutability và verification. |
| Lockfile xác minh nội dung JAR | Lockfile cố định version; checksum/signature verification kiểm tra nội dung artifact. |
| SBOM chứng minh phần mềm an toàn | SBOM liệt kê thành phần; nó không phải chứng nhận an toàn. |
| Cache là dữ liệu vô hại | Cache có thể bị đầu độc hoặc chứa file nhạy cảm; cần tách trust domain. |
| Pin version ngăn mọi thay đổi artifact | Repository có thể overwrite release; cần artifact immutability và digest verification. |
| Chỉ review source code là đủ | Build script, wrapper, plugin và CI workflow cũng là mã thực thi cần review. |

## 37. Checklist trước khi phát hành artifact

- Source commit đã được review và bảo vệ.
- CI workflow/action được pin và tin cậy.
- Runner/image và JDK có nguồn xác định.
- Gradle/Maven wrapper và distribution đã được xác minh.
- Plugin và dependency version được quản lý.
- Repository được allowlist và dùng HTTPS.
- Checksum/chữ ký được xác minh theo policy.
- Lockfile và verification metadata đã được review.
- Build không dùng snapshot/dynamic version ngoài policy release.
- Test, scan và policy checks đã hoàn tất.
- SBOM/provenance được tạo nếu quy trình yêu cầu.
- Digest của artifact được ghi nhận.
- Artifact được publish vào repository bất biến.
- Artifact được promote/deploy theo đúng digest đã kiểm chứng.
- Signing/deploy credential chỉ được cấp cho job được bảo vệ.
- Log, cache và artifact không chứa secret.

## 38. Nguyên tắc áp dụng trong thực tế

Nguồn tin cậy của build không chỉ là repository chứa file JAR. Nó là toàn bộ chuỗi gồm runner, JDK, build tool, wrapper, plugin, dependency, repository và quy trình tạo/publish artifact.

Hãy bắt đầu từ nguồn chính thức và version cố định. Xác minh checksum hoặc chữ ký qua kênh tin cậy; pin wrapper distribution và review wrapper scripts/JAR; quản lý plugin và dependency repository bằng allowlist; bật dependency verification phù hợp; giữ release artifact bất biến; ghi nhận digest, SBOM và provenance khi cần.

CI cần tách quyền đọc dependency khỏi quyền publish/deploy, bảo vệ cache theo trust level và yêu cầu review cho thay đổi build logic. Khi phát hiện checksum, signature hoặc provenance không hợp lệ, dừng sử dụng artifact và điều tra nguồn gốc thay vì bỏ qua kiểm tra. Cách làm này giúp build có thể tái lập, truy vết được và giảm nguy cơ một thành phần không đáng tin làm ảnh hưởng phần mềm phát hành.
