# Pack200 và chuyển sang cơ chế phân phối artifact khác

Trong một đợt nâng cấp Java từ JDK 8 lên các phiên bản hiện đại, lỗi không chỉ xuất hiện khi biên dịch mã nguồn. Một pipeline vẫn có thể build thành công nhưng thất bại ở bước tạo gói phát hành, tải thư viện xuống máy khách hoặc giải nén artifact. Nguyên nhân thường gặp ở những hệ thống lâu năm là sự phụ thuộc vào **Pack200**: một cơ chế nén JAR chuyên biệt từng có trong JDK nhưng đã bị loại bỏ.

Các lệnh `pack200` và `unpack200`, cùng API `java.util.jar.Pack200`, từng được sử dụng để nén nhiều class file trong JAR thành định dạng nhỏ hơn, đặc biệt trong một số kịch bản phân phối Java qua mạng. Từ JDK 14, các thành phần Pack200 của JDK không còn tồn tại. Vì vậy, thay một bản JDK cũ bằng JDK 17, 21 hoặc 25 có thể khiến một script packaging hoặc trình tải artifact cũ ngừng hoạt động, ngay cả khi ứng dụng không hề import `Pack200` trong mã nghiệp vụ.

Bài học này hướng dẫn cách nhận diện dependency Pack200, phân biệt định dạng nén với định dạng phân phối, đánh giá những lựa chọn thay thế phù hợp, chuyển pipeline sang JAR và artifact repository hoặc mô hình triển khai khác, cũng như kiểm tra tính toàn vẹn và khả năng tương thích sau migration.

## 1. Pack200 là gì?

### 1.1. Mục đích ban đầu

Pack200 là một định dạng nén được thiết kế riêng cho nội dung JAR chứa Java class file. Không giống việc chỉ áp dụng một thuật toán nén tổng quát lên một chuỗi byte, Pack200 khai thác cấu trúc class file và các đặc điểm lặp lại giữa những class trong cùng archive để giảm kích thước truyền tải.

Pack200 đặc biệt có ý nghĩa ở thời kỳ băng thông hạn chế, khi ứng dụng Java hoặc một tập JAR lớn phải được tải xuống qua mạng. Nó từng được gắn với những cơ chế triển khai như Java Web Start và các pipeline tối ưu kích thước thư viện phân phối.

Một luồng xử lý cũ có thể được hình dung như sau:

```text
Mã nguồn Java
    |
    v
Biên dịch và đóng gói thành application.jar
    |
    v
pack200 tạo application.pack.gz
    |
    v
Tải lên server hoặc kho phát hành
    |
    v
Máy khách tải application.pack.gz
    |
    v
unpack200 tái tạo application.jar
    |
    v
JVM nạp class từ application.jar
```

Định dạng `.pack` hoặc `.pack.gz` không phải là JAR bình thường và không thể được đưa trực tiếp vào classpath với kỳ vọng JVM đọc như archive ZIP/JAR. Máy nhận phải có công cụ hoặc thư viện phù hợp để chuyển nó về JAR trước khi sử dụng.

### 1.2. Pack200 khác JAR ở điểm nào?

JAR vốn là một archive dựa trên ZIP và thường có khả năng nén từng entry bằng DEFLATE. Pack200 không thay thế JAR như định dạng classpath lâu dài; nó là một biểu diễn tối ưu dành cho đóng gói/truyền tải rồi được giải nén trở lại thành JAR.

| Khía cạnh | JAR thông thường | Pack200 |
|---|---|---|
| Mục đích | Archive ứng dụng/thư viện có thể sử dụng trực tiếp | Biểu diễn nén chuyên biệt cho nội dung JAR |
| Cấu trúc | ZIP entries, manifest, class/resource | Định dạng packed stream riêng |
| JVM dùng làm classpath trực tiếp | Có | Không; cần unpack về JAR |
| Công cụ JDK hiện đại | `jar` vẫn được hỗ trợ | `pack200` và `unpack200` bị loại bỏ từ JDK 14 |
| Mức độ phụ thuộc runtime | Chủ yếu theo class file và API sử dụng | Phụ thuộc khả năng có packer/unpacker tương thích |
| Phân phối phổ biến hiện nay | Maven/Gradle repository, JAR download, container image | Legacy pipeline cần migration |

Sự khác biệt này rất quan trọng: khi Pack200 biến mất, **khả năng chạy JAR không biến mất**. Chỉ có công đoạn nén/giải nén chuyên biệt bằng Pack200 không còn được JDK cung cấp.

### 1.3. Các tên file thường gặp

Những hệ thống cũ có thể sử dụng:

- `library.pack`: packed stream không có lớp gzip bên ngoài.
- `library.pack.gz`: packed stream có thêm lớp nén gzip.
- `library.jar.pack.gz`: quy ước tên giúp nhận biết JAR gốc.
- `application.jar`: JAR thông thường trước khi pack hoặc sau khi unpack.

Tên file chỉ là gợi ý; cần nhận diện định dạng thực tế và quy trình tạo artifact. Một file có đuôi `.gz` có thể là gzip của JAR thuần hoặc gzip của Pack200 stream, và hai trường hợp này **không giống nhau**.

Ví dụ:

```text
gzip(application.jar)
    -> application.jar.gz
    -> gunzip trả về application.jar

gzip(pack200(application.jar))
    -> application.pack.gz
    -> gunzip + unpack200 mới trả về application.jar
```

Chỉ thay đuôi `.pack.gz` thành `.jar.gz` không chuyển đổi được nội dung.

## 2. Lịch sử hỗ trợ Pack200 qua các bản JDK

Để lập kế hoạch migration, cần xác định chính xác thay đổi xảy ra ở bước nào.

| Phiên bản | Trạng thái liên quan Pack200 | Tác động |
|---|---|---|
| JDK 8 và nhiều JDK cũ hơn | Các công cụ và API Pack200 còn sẵn | Legacy build hoặc client có thể đang phụ thuộc |
| JDK 11 | JEP 336 deprecate Pack200 tools và API, đánh dấu for removal | Cần kiểm kê và lên kế hoạch thay thế |
| JDK 14 | JEP 367 loại bỏ Pack200 tools và API | `pack200`, `unpack200` và `java.util.jar.Pack200` không còn trong JDK |
| JDK 17, 21, 25 | Không khôi phục Pack200 trong JDK | Pipeline phải dùng cơ chế khác hoặc công cụ bên ngoài có hỗ trợ rõ ràng |

Không nên suy luận rằng JDK 9 hoặc JDK 11 đã xóa toàn bộ Pack200. Điểm loại bỏ thực tế là **JDK 14**, theo JEP 367. Việc đánh dấu deprecated trước đó cho phép các hệ thống chuẩn bị chuyển đổi.

Pack200 là một ví dụ về vòng đời API:

```text
API/tool từng được hỗ trợ
       |
       v
Deprecated for removal (JDK 11)
       |
       v
Removed (JDK 14)
       |
       v
Ứng dụng phải đổi packaging/distribution
```

Một mã nguồn không dùng Pack200 trực tiếp vẫn có thể bị ảnh hưởng bởi Maven/Gradle plugin, Ant task, script phát hành, CI image, thư viện thứ ba hoặc chương trình phía máy khách gọi công cụ cũ.

## 3. Triệu chứng lỗi khi nâng cấp JDK

### 3.1. Lệnh `pack200` hoặc `unpack200` không tồn tại

Một shell script legacy có thể có các lệnh minh họa:

```shell
pack200 dist/app.pack.gz dist/app.jar
unpack200 dist/app.pack.gz dist/app-restored.jar
```

Các lệnh này chỉ có ý nghĩa trong môi trường JDK cũ có công cụ tương ứng. Khi chạy trên JDK 14+, shell có thể báo không nhận diện command hoặc không tìm thấy executable.

Trên Windows, script có thể tham chiếu đường dẫn cố định như `%JAVA_HOME%\bin\pack200.exe`. Trên Linux, script có thể gọi `$JAVA_HOME/bin/pack200`. Khi đổi `JAVA_HOME` sang JDK mới, đường dẫn executable không còn tồn tại.

Không nên sửa bằng cách chỉ thêm một executable cũ ngẫu nhiên vào `PATH` mà không quản lý phiên bản, nguồn gốc và compatibility của công cụ. Phải xem xét cả pipeline tạo lẫn pipeline tiêu thụ artifact.

### 3.2. Code tham chiếu API `java.util.jar.Pack200` không biên dịch

Mã cũ có thể có dạng:

```java
// Ví dụ legacy - không biên dịch trên JDK đã loại bỏ Pack200.
import java.util.jar.Pack200;

Pack200.Packer packer = Pack200.newPacker();
```

Khi biên dịch bằng JDK 14+, compiler không tìm thấy `Pack200`. Đổi source/target level không thể làm một API đã bị loại bỏ khỏi JDK xuất hiện trở lại.

Một phần mềm sử dụng Pack200 thông qua reflection có thể không lỗi ở compile time nhưng sẽ gặp lỗi runtime khi cố tìm class bằng tên.

### 3.3. Plugin hoặc task build thất bại

Ngay cả khi mã ứng dụng hoàn toàn hợp lệ, pipeline vẫn có thể lỗi ở task cuối:

```text
compileJava     SUCCESS
test            SUCCESS
jar             SUCCESS
packDistribution FAILED
publish         NOT RUN
```

Task đó có thể gọi trực tiếp `pack200`, gọi API Pack200, hoặc phụ thuộc plugin cũ giả định công cụ luôn có trong JDK.

Cần đọc stack trace và log của **bước packaging/publish**, không chỉ xem kết quả compile. Việc đổi Gradle hoặc Maven version không tự động thay thế thuật toán Pack200; phải xác định task hoặc plugin nào đang áp dụng nó.

### 3.4. Máy khách không đọc được artifact mới

Một hệ thống có thể triển khai server mới nhưng giữ client cũ. Nếu client luôn tải `.pack.gz` rồi gọi `unpack200`, việc chuyển server sang cung cấp JAR thuần có thể khiến client báo lỗi định dạng. Tương tự, một artifact Pack200 cũ trong repository hoặc cache không tự nhiên trở thành JAR tương thích với JDK hiện đại.

Vì vậy, migration phải xem xét **cả producer và consumer**, bao gồm cache, CDN, proxy, cập nhật ứng dụng và các thiết bị ngoại tuyến.

## 4. Trước khi chọn giải pháp: xác định nhu cầu thực tế

Nhiều dự án sử dụng Pack200 chỉ vì đây là cách tối ưu truyền tải đã có sẵn trong build cũ. Khi thay thế, hãy trả lời:

1. Artifact được phân phối là **thư viện**, **ứng dụng JVM**, **ứng dụng desktop**, **service container**, hay **bản cập nhật cho client**?
2. Consumer đọc JAR trực tiếp hay cần một định dạng trung gian?
3. Yêu cầu chính là giảm kích thước, tăng tốc tải xuống, xác minh tính toàn vẹn, tự động cập nhật hay quản lý phiên bản?
4. Artifacts được tải từ Maven repository, một server HTTP, object storage, CDN, container registry hay file share?
5. Có hỗ trợ nhiều OS/architecture, native library hoặc runtime JVM đi kèm không?
6. Có yêu cầu chạy offline hoặc qua hệ thống proxy/thiết bị cấu hình hạn chế không?
7. Có ký số JAR, ký bản phát hành, kiểm tra SHA-256 hoặc cơ chế xác thực nguồn tải không?
8. Có cần truy xuất lại artifact lịch sử để tái dựng bản phát hành hoặc rollback không?

Pack200 là một công cụ nén, không phải giải pháp đầy đủ cho versioning, bảo mật hay deployment. Khi xóa nó, đây là cơ hội bỏ luôn các bước đóng gói thừa và chọn cơ chế phân phối đúng với loại sản phẩm.

## 5. Lựa chọn thay thế theo loại artifact

Không có một công cụ duy nhất thay thế tất cả nhu cầu trước đây của Pack200.

| Nhu cầu | Giải pháp phù hợp | Ghi chú |
|---|---|---|
| Phân phối thư viện Java cho ứng dụng khác | Maven repository và JAR thông thường | Maven/Gradle quản lý coordinates và dependency |
| Phân phối ứng dụng JVM tự chạy | Executable JAR hoặc bộ thư mục JAR + startup script | Cần runtime Java tương thích |
| Phân phối service trên hạ tầng container | OCI container image | Có image layers, registry và deployment tooling |
| Phân phối runtime tùy chỉnh | `jlink` | Tạo runtime image cho ứng dụng modular |
| Đóng gói ứng dụng desktop cho người dùng cuối | `jpackage` | Tạo application image/installer theo OS |
| Chỉ giảm byte truyền qua HTTP | HTTP compression, gzip hoặc định dạng nén phù hợp | Consumer phải hỗ trợ cùng encoding/format |
| Phát hành bản cập nhật/download trực tiếp | HTTPS/CDN + manifest version + checksums/signatures | Chú ý cache và atomic update |
| Lưu trữ dài hạn | JAR gốc kèm metadata, checksum và chữ ký | Không phụ thuộc vào unpacker đã bị loại bỏ |

Các lựa chọn trên giải quyết những lớp khác nhau. Chẳng hạn, `jlink` tạo runtime Java tối ưu nhưng không thay thế chức năng phân phối artifact library theo dependency coordinates; OCI image quản lý container deploy nhưng không giải quyết việc một Java client phải nạp thư viện động từ Maven repository.

## 6. Phân phối JAR thông thường: con đường đơn giản nhất

### 6.1. JAR vẫn có nén

Một số đội kỹ thuật lo rằng bỏ Pack200 thì tất cả JAR sẽ trở thành file không nén. Điều đó không đúng. JAR là ZIP archive và `jar` tool có thể tạo các entry nén theo định dạng ZIP/JAR.

Ví dụ tạo JAR từ thư mục class đã biên dịch:

```shell
jar --create --file dist/example.jar -C build/classes .
```

Lệnh minh họa sử dụng cú pháp `jar` hiện đại và chỉ phù hợp nếu thư mục đầu vào tồn tại. Nếu dự án dùng Maven hoặc Gradle, nên để build tool tạo archive cùng manifest, resources và dependency metadata thay vì tự gọi `jar` bằng tay trong pipeline production.

Liệt kê nội dung archive:

```shell
jar --list --file dist/example.jar
```

JVM, các IDE, build tool và phần lớn Java library đều hiểu JAR trực tiếp. Không cần bước `unpack200`.

### 6.2. JAR “thin” và JAR “fat”

Khi phân phối ứng dụng, cần phân biệt:

- **Thin JAR:** chứa class và resource của ứng dụng; dependency được cấp riêng qua classpath/module path.
- **Fat/Uber JAR:** bao gồm nhiều dependency vào một archive lớn để thuận tiện triển khai.
- **Executable JAR:** có thông tin khởi chạy thích hợp trong manifest hoặc launcher; có thể là thin hoặc fat tùy thiết kế.
- **Application distribution:** thư mục gồm ứng dụng, thư viện phụ thuộc, tài nguyên và script khởi chạy.

Mỗi cách có trade-off. Fat JAR dễ phát hành một file nhưng có thể phát sinh xung đột resource, `META-INF/services` và chữ ký khi gộp dependency. Thin JAR thuận tiện cho việc thay thư viện theo phiên bản nhưng yêu cầu cơ chế đặt classpath rõ ràng.

Đừng coi việc chuyển từ Pack200 sang fat JAR là bắt buộc. Nếu hệ thống hiện đang phân phối một thư mục `lib/*.jar`, có thể tiếp tục giữ cấu trúc đó và chỉ xóa bước Pack200.

### 6.3. Ví dụ một bộ phân phối có thể chạy

```text
dist/
  app.jar
  lib/
    core.jar
    database-driver.jar
    logging.jar
  config/
    application.properties
  bin/
    start.sh
    start.ps1
```

Ứng dụng có thể khởi chạy bằng classpath gồm `app.jar` và `lib/*`, hoặc bằng launcher đã được build tool tạo. Đường dẫn và separator cần được kiểm tra trên từng OS mục tiêu.

Đối với thư viện, nên phát hành JAR cùng POM/module metadata thay vì đưa một thư mục riêng cho consumer tự quản lý dependency thủ công.

## 7. Maven repository thay cho việc tự phân phối pack stream

### 7.1. Vì sao repository là mô hình phù hợp?

Nếu artifact được nhiều ứng dụng Java khác sử dụng, một Maven-compatible repository thường cung cấp những khả năng mà Pack200 không có:

- Định danh bằng `groupId`, `artifactId` và `version`.
- Metadata dependency và dependency transitivity.
- Kho release và snapshot được quản lý.
- Quyền truy cập, chính sách lưu trữ và audit.
- Tích hợp với CI và công cụ dependency resolution.
- Có thể kèm checksum, chữ ký và tài liệu release.

Ví dụ dependency của consumer:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>core-api</artifactId>
    <version>2.4.0</version>
</dependency>
```

Consumer không cần biết thư viện từng được truyền dưới dạng Pack200. Build tool lấy JAR và POM theo coordinates từ repository đã cấu hình.

### 7.2. Ví dụ publish bằng Maven

Với dự án Maven, metadata cơ bản:

```xml
<groupId>com.example</groupId>
<artifactId>core-api</artifactId>
<version>2.4.0</version>
<packaging>jar</packaging>
```

Repository đích có thể được khai báo trong phần `distributionManagement`:

```xml
<distributionManagement>
    <repository>
        <id>internal-releases</id>
        <url>https://repo.example.invalid/maven/releases</url>
    </repository>
</distributionManagement>
```

Sau đó pipeline có thể dùng:

```shell
mvn --batch-mode clean verify
mvn --batch-mode deploy
```

URL là địa chỉ minh họa, không phải endpoint có thật. Credentials cần được cấu hình qua cơ chế bảo mật phù hợp của Maven/CI, không hard-code user/password vào POM.

`mvn deploy` phát hành artifact theo metadata Maven, không cần Pack200. Nếu dự án từng có một plugin “pack” chạy trước `deploy`, hãy gỡ hoặc thay plugin đó sau khi đã xác nhận consumers có thể dùng artifact mới.

### 7.3. Ví dụ publish bằng Gradle

Với Gradle Groovy DSL:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example'
version = '2.4.0'

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
    repositories {
        maven {
            url = uri('https://repo.example.invalid/maven/releases')
            credentials {
                username = providers.environmentVariable('REPO_USER').orNull
                password = providers.environmentVariable('REPO_PASSWORD').orNull
            }
        }
    }
}
```

Đây là mẫu cấu hình minh họa; Gradle version và plugin đang dùng phải được kiểm tra theo tài liệu tương ứng. CI cần cấp environment variables an toàn. Không in credentials vào build log.

Bước publish:

```shell
./gradlew build publish
```

Trên Windows, có thể dùng `gradlew.bat`. Tùy pipeline, có thể chạy test và publish trong các stage riêng để chỉ phát hành artifact đã vượt qua kiểm thử.

### 7.4. Immutable version và kiểm soát provenance

Không nên ghi đè một bản release đã được consumer tải xuống bằng nội dung khác nhưng cùng version. Hãy tăng version, lưu provenance của source commit/build và ghi checksum cho từng artifact.

Nếu có hai artifact khác nhau cùng coordinates/version, cache của Maven/Gradle có thể giữ file cũ khiến sự cố khó tái hiện. Nguyên tắc immutable release giúp xác định chính xác bản nào đã được kiểm thử và triển khai.

## 8. Đóng gói ứng dụng JVM mà không cần Pack200

### 8.1. Executable JAR

Với ứng dụng server hoặc CLI chạy bằng Java:

```shell
java -jar dist/application.jar
```

Artifact cần có manifest/launcher phù hợp. Nếu ứng dụng phụ thuộc nhiều JAR và không đóng gói dependency cùng file, phải cung cấp classpath hoặc distribution layout tương ứng. `java -jar` không tự tải dependency chỉ vì POM khai báo chúng.

Đối với bản phát hành, nên có:

- Version của artifact và commit.
- Yêu cầu JDK tối thiểu, ví dụ Java 21 hoặc 25.
- Startup script hoặc hướng dẫn lệnh khởi chạy.
- Danh sách dependency runtime.
- Checksum và tùy chọn signature.
- Hướng dẫn cấu hình và rollback.

### 8.2. `jlink` tạo runtime image tùy chỉnh

Nếu ứng dụng được tổ chức theo JPMS và cần runtime nhỏ hơn JDK đầy đủ, `jlink` có thể tạo một Java runtime image chỉ gồm những module cần thiết.

Ví dụ minh họa:

```shell
jlink --module-path mods --add-modules com.example.app --output image/runtime
```

Điều kiện tiên quyết là các module và dependency trên module path phải được phân giải theo đúng cấu hình. Lệnh không tự biến mọi JAR classpath thành named module hợp lệ.

Cần nhớ:

- `jlink` không phải một codec để thay Pack200.
- Runtime image có tính phụ thuộc OS/architecture.
- Phải cập nhật runtime khi có bản vá bảo mật JDK.
- Kích thước download có thể tăng nếu phát hành kèm runtime, nhưng tính tự chứa và khả năng vận hành có thể tốt hơn.
- Kiểm thử trên target OS/architecture, không chỉ máy build.

### 8.3. `jpackage` cho ứng dụng desktop

`jpackage` có thể tạo application image hoặc installer cho các hệ điều hành được hỗ trợ. Đây là lựa chọn phù hợp hơn Pack200 nếu người dùng cuối cần cài đặt/cập nhật ứng dụng Java như một ứng dụng desktop.

Quy trình tổng quát:

```text
Build class/JAR
    |
    v
Đóng gói dependencies
    |
    v
Xác định main class hoặc main module
    |
    v
jpackage tạo app image/installer
    |
    v
Ký gói, phát hành và kiểm thử cài đặt/gỡ cài đặt
```

Installer và native bundle không có tính di động như JAR thuần. Nếu hỗ trợ Windows, macOS và Linux, cần build và xác minh gói cho từng nền tảng. Nhiệm vụ ký installer, notarization và cập nhật tự động là những vấn đề vận hành riêng, không được giải quyết tự động bằng `jpackage`.

### 8.4. OCI container image cho dịch vụ

Đối với web service hoặc batch service chạy trong container, cách phân phối artifact có thể chuyển sang OCI image:

```text
Source -> JAR -> Container image -> Registry -> Deployment
```

Ví dụ Dockerfile tối giản:

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY build/libs/application.jar /app/application.jar
ENTRYPOINT ["java", "-jar", "/app/application.jar"]
```

Đây là ví dụ minh họa: tên và đường dẫn JAR phải khớp output thật, dependency runtime có thể cần được đóng gói riêng, và base image cần được pin theo chính sách của tổ chức. Không dùng một mutable image tag như bằng chứng duy nhất để tái lập bản phát hành; lưu image digest và provenance.

OCI image cung cấp layering, registry, cơ chế kéo image và caching. Đây là cách phân phối khác Pack200 và không yêu cầu JDK có `unpack200` ở runtime.

## 9. Nếu chỉ cần giảm kích thước tải xuống

Không phải hệ thống nào cũng cần đổi toàn bộ công cụ triển khai. Nếu Pack200 được dùng **chỉ để nén truyền tải**, có thể chọn một định dạng nén phổ biến được client và server thống nhất.

### 9.1. Gzip của JAR

Một cách đơn giản là tạo `application.jar` rồi nén thêm ở lớp transport/storage:

```text
application.jar
    |
    +-- gzip --> application.jar.gz
                         |
                         +-- gunzip --> application.jar
```

`.jar.gz` trong trường hợp này là gzip của JAR, **không phải Pack200 stream**. Consumer cần giải nén đúng một lớp gzip trước khi chạy.

Trên hệ thống Unix-like:

```shell
gzip -k application.jar
```

`gzip -k` là ví dụ của công cụ hệ điều hành, không phải command JDK và không đảm bảo hiện diện trên Windows. Có thể dùng Java library, build plugin hoặc công cụ đóng gói khác nếu phù hợp.

### 9.2. HTTP compression

Khi download qua HTTP, server có thể hỗ trợ các encoding được cả hai phía thương lượng. Cơ chế HTTP `Content-Encoding` là một lớp khác với định dạng artifact lưu ở repository.

Ví dụ:

```text
Stored artifact: application.jar
Response encoding: gzip (nếu client hỗ trợ và server cấu hình)
Client receives decoded representation: application.jar
```

Không tự giả định mọi client tự động xử lý mọi Content-Encoding. Hãy kiểm tra HTTP library, proxy, CDN, range requests, cache key và cách downloader ghi file. Một số artifact vốn đã nén nên áp dụng thêm gzip có thể đem lại lợi ích hạn chế.

### 9.3. Thuật toán nén khác

Các thuật toán hoặc định dạng như Zstandard và Brotli có thể hữu ích trong một số hạ tầng. Tuy nhiên, chúng không phải công cụ nén JAR bắt buộc của Java, và client cần có hỗ trợ tương ứng.

Trước khi chọn, đo bằng dữ liệu thực tế:

| Tiêu chí | Vì sao quan trọng |
|---|---|
| Kích thước artifact sau nén | Ảnh hưởng băng thông và thời gian tải |
| CPU khi nén | Ảnh hưởng CI và tần suất phát hành |
| CPU và RAM khi giải nén | Quan trọng trên thiết bị cấu hình thấp |
| Hỗ trợ đa nền tảng | Tránh phụ thuộc vào binary hiếm hoặc không còn bảo trì |
| Khả năng stream/range download | Ảnh hưởng client cập nhật và resume |
| Tính tái lập | Cần đối chiếu đúng checksum/artifact được phát hành |
| Độ phức tạp triển khai | Càng nhiều codec tùy chỉnh, càng nhiều thành phần có thể lỗi |

**Không có bảo đảm rằng gzip, Brotli hoặc Zstandard sẽ luôn nén JAR nhỏ hơn Pack200.** Lựa chọn tối ưu phụ thuộc đặc tính artifact và mục tiêu hệ thống; nên ưu tiên format được hỗ trợ lâu dài và quy trình phân phối dễ vận hành.

## 10. JAR signatures, checksum và tính toàn vẹn sau chuyển đổi

### 10.1. Không đánh đồng tương đương chức năng với giống hệt byte

Pack200 có thể chuyển đổi biểu diễn của các class/JAR entries khi pack và unpack. Vì thế, không nên giả định kết quả unpack có cùng toàn bộ byte với JAR gốc. Với signed JAR, khác biệt ở byte nội dung hoặc entry metadata có thể ảnh hưởng xác minh chữ ký.

Khi migration:

1. Xác định JAR đầu vào có ký số hay không.
2. Nếu đang giữ artifact Pack200 lịch sử, unpack bằng môi trường/công cụ phù hợp trước khi kiểm tra.
3. Xác minh class/resource và chạy test ứng dụng trên JAR sẽ phân phối.
4. Ký **artifact cuối cùng được phát hành** theo chính sách của dự án.
5. Xác minh chữ ký và checksum ở phía tiêu thụ hoặc trong pipeline phát hành.

Không copy nguyên chữ ký hay file checksum của `.pack.gz` rồi gắn sang `.jar` mới. Chữ ký/checksum xác nhận một artifact cụ thể chứ không chứng minh hai format khác nhau có cùng ý nghĩa.

### 10.2. Tạo checksum cho artifact đã phát hành

Ví dụ trên PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath ".\\dist\\application.jar"
```

Ví dụ trên Linux hoặc môi trường có `sha256sum`:

```shell
sha256sum dist/application.jar
```

Checksum giúp phát hiện thay đổi không mong muốn trong dữ liệu truyền hoặc lưu trữ. Nhưng checksum **không tự chứng minh ai đã phát hành artifact** nếu giá trị checksum và file cùng đến từ nguồn không được tin cậy. Nếu cần xác thực nguồn gốc, hãy dùng chữ ký artifact hoặc cơ chế provenance được quản lý phù hợp.

### 10.3. Kiểm tra signed JAR

JDK cung cấp `jarsigner` để ký và xác minh chữ ký JAR theo cấu hình key/certificate phù hợp. Ví dụ kiểm tra:

```shell
jarsigner -verify -verbose -certs dist/application.jar
```

Việc lệnh tồn tại và hoàn tất không tự giải quyết mọi yêu cầu trust policy. Cần kiểm tra chứng thư, chain, thời hạn, chính sách thuật toán và quy trình tin cậy của hệ thống. Đối với JAR từng trải qua Pack200, hãy xác minh chính JAR cuối cùng sau mọi bước biến đổi.

## 11. Tái lập build và tránh khác biệt khó kiểm soát

Bỏ Pack200 có thể giúp pipeline đơn giản hơn, nhưng sự khác nhau giữa các bản JAR vẫn có thể phát sinh từ:

- Timestamp bên trong ZIP entries.
- Thứ tự entry trong archive.
- Manifest attributes.
- Generated source/resource có timestamp hoặc build ID.
- File encoding và line endings.
- Phiên bản compiler, plugin và dependency.
- Số lượng resource trùng tên hoặc trật tự merge từ nhiều dependency.

Build tái lập giúp kiểm tra rằng cùng input và toolchain tạo ra artifact tương đương byte, từ đó dễ phát hiện sửa đổi không mong muốn.

Với Gradle Groovy DSL, có thể cấu hình task JAR theo nguyên tắc kiểm soát timestamp và thứ tự entry:

```groovy
tasks.withType(Jar).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
```

Các tùy chọn và hành vi thực tế phụ thuộc phiên bản Gradle; ví dụ nhằm minh họa khái niệm. Với Maven, cơ chế `project.build.outputTimestamp` và plugin/archiver hỗ trợ reproducible builds có thể được sử dụng.

Đừng nhầm tính tái lập với tính tương thích: hai JAR có SHA-256 giống nhau vẫn có thể chứa mã không chạy trên JDK đích nếu bytecode target hoặc dependency sai. Phải kiểm tra cả hai khía cạnh.

## 12. Rà soát mã nguồn, build và hạ tầng để tìm Pack200

### 12.1. Mã nguồn Java

Tìm các dấu hiệu như:

- `import java.util.jar.Pack200`.
- `Pack200.newPacker()` hoặc `Pack200.newUnpacker()`.
- Reflection theo chuỗi `java.util.jar.Pack200`.
- Các adapter/codec custom có tên `Pack200`.
- Utility Java gọi binary bên ngoài qua `ProcessBuilder`.

Một số đoạn code cũ có thể không được gọi trong test nhưng vẫn nằm trong artifact và gây lỗi khi build với JDK mới.

### 12.2. Script và build configuration

Kiểm tra:

- `build.gradle` / `build.gradle.kts` hoặc plugin/task tùy chỉnh.
- Maven `pom.xml` và plugin packaging.
- Ant `build.xml` và task tùy chỉnh.
- Shell, batch, PowerShell script.
- Dockerfile và CI image.
- Jobs phát hành trong Jenkins, GitHub Actions, GitLab CI hoặc công cụ tương tự.
- Release script chạy trên build server riêng.
- Artifact cache, object storage hoặc thư mục release cũ.

Tìm kiếm bằng `rg` nếu dự án có ripgrep:

```shell
rg -n -i "pack200|unpack200|java[.]util[.]jar[.]Pack200" .
rg -n -i "[.]pack[.]gz|[.]pack" .
rg -n -i "packDistribution|unpackDistribution|pack-jars" .
```

Từ khóa thứ ba chỉ là ví dụ tên task thường gặp, không phải tên task tiêu chuẩn trong Maven/Gradle. Nếu không tìm thấy kết quả ở source repo, cần kiểm tra script CI được quản lý bên ngoài repo và phụ thuộc nhị phân của plugin.

### 12.3. Tìm trong artifact đang phát hành

Có thể kiểm tra:

- Có file `.pack` hoặc `.pack.gz` trong thư mục phân phối không?
- HTTP endpoint đang trả MIME type, filename hoặc response header nào?
- Có manifest cập nhật trỏ tới Pack200 không?
- Repository lưu JAR thường hay chỉ lưu packed stream?
- Client có bước giải nén trước khi đưa JAR vào classpath không?
- Cache/CDN có lưu artifact cũ theo URL cố định không?

Đặc biệt, hệ thống update có thể giữ Pack200 như một “đường tắt” chỉ được kích hoạt khi client hỗ trợ. Nếu không kiểm tra end-to-end trên client thật, rất dễ bỏ sót.

## 13. Chuyển đổi artifact Pack200 cũ

### 13.1. Phân biệt việc tạo artifact mới và đọc artifact lịch sử

Hai bài toán khác nhau:

- **Artifact mới:** bỏ Pack200 khỏi pipeline, xuất bản JAR hoặc định dạng phân phối mới.
- **Artifact lịch sử:** vẫn có thể cần đọc `.pack.gz` của một release cũ để phục vụ kiểm toán, tái dựng hoặc migration dữ liệu.

Đối với artifact lịch sử, có thể cần một môi trường JDK cũ hoặc công cụ Pack200 tương thích để unpack một lần. Không nên chuyển cả production runtime về JDK cũ chỉ vì còn vài file archive.

### 13.2. Quy trình chuyển đổi một lần có kiểm soát

1. Lập danh sách packed artifacts cần giữ lại, kèm version, nguồn và checksum hiện có.
2. Xác minh nguồn artifact và quyền truy cập.
3. Chuẩn bị môi trường chuyển đổi cô lập với phiên bản công cụ đã được kiểm soát.
4. Unpack artifact sang JAR thông thường.
5. Kiểm tra nội dung, manifest và resource.
6. Chạy test hoặc smoke test tương ứng với loại artifact.
7. Ký/xác minh và phát hành JAR mới theo quy trình artifact chuẩn.
8. Lưu mapping từ packed artifact lịch sử sang JAR chuyển đổi, kèm checksum và metadata.
9. Loại bỏ dependency unpack khỏi consumer mới.

Ví dụ lệnh lịch sử trong môi trường cũ có `unpack200`:

```shell
unpack200 legacy-library.pack.gz legacy-library.jar
```

Lệnh **không tồn tại trong JDK 14+**. Nếu tổ chức sử dụng tool bên ngoài, cần kiểm tra rõ tương thích, giấy phép, nguồn gốc và quy trình bảo mật. Không lấy một binary không rõ nguồn chỉ để giải nén artifact.

### 13.3. Không giả định JAR chuyển đổi có bytecode mới

Unpack Pack200 chỉ tái tạo nội dung class/JAR, không biên dịch lại chương trình theo phiên bản Java mới. Một JAR được build cho Java 8 có thể vẫn chứa class-file version 52 sau khi chuyển đổi.

Nếu ứng dụng cần di chuyển lên JDK 21 hoặc 25, cần kiểm tra API đã loại bỏ, module encapsulation, native dependency và hành vi runtime riêng. Pack200 migration giải quyết **định dạng phân phối**, không giải quyết mọi vấn đề Java compatibility.

## 14. Migration khi server và client không được cập nhật cùng lúc

### 14.1. Khả năng tương thích của downloader

Một client cũ có thể chỉ biết:

```text
GET /downloads/app.pack.gz
download()
unpack200()
startApplication()
```

Nếu server ngay lập tức trả `app.jar` ở cùng URL nhưng client vẫn gọi `unpack200`, migration thất bại. Phải cập nhật cả cách chọn định dạng và logic download.

Hướng triển khai an toàn:

- Phát hành client mới có thể nhận JAR thông thường.
- Dùng manifest/metadata để công bố artifact type và checksum.
- Nếu cần chuyển tiếp, phục vụ cả định dạng cũ và mới trong thời gian có kiểm soát.
- Theo dõi tỷ lệ client còn yêu cầu Pack200.
- Chỉ ngừng endpoint Pack200 sau khi không còn consumer được cam kết hỗ trợ.
- Có thông báo và lộ trình xử lý cho client offline lâu ngày.

Nếu Pack200 ở phía server chỉ là bước nén tĩnh, có thể loại bỏ sớm hơn. Nếu một thiết bị đầu cuối có firmware hoặc runtime cố định, việc tương thích ngược cần được đánh giá kỹ.

### 14.2. Manifest phiên bản cho cơ chế update

Một updater hiện đại nên tải metadata trước khi tải artifact. Ví dụ cấu trúc JSON minh họa:

```json
{
  "version": "3.2.0",
  "artifact": "application-3.2.0.jar",
  "format": "jar",
  "sha256": "<digest-of-published-file>",
  "minJava": 21
}
```

Giá trị `sha256` ở đây chỉ là placeholder. Manifest thực tế cần đặt digest đã tính của artifact phát hành. Hệ thống bảo mật cao hơn cần xác thực chính manifest bằng chữ ký hoặc kênh phát hành đáng tin cậy.

Updater không nên tự đoán format theo phần mở rộng nếu protocol có metadata rõ ràng. Nó cũng cần kiểm tra version, dung lượng giới hạn, checksum, tính tương thích runtime và thực hiện thay file theo cơ chế atomic/rollback phù hợp.

### 14.3. Cache và CDN

Khi thay đổi định dạng phân phối, nên thay URL artifact hoặc dùng versioned URL rõ ràng. Không ghi đè `app.pack.gz` bằng nội dung JAR trong khi proxy/CDN và client vẫn cache theo định dạng cũ.

Định danh artifact bằng nội dung hoặc phiên bản immutable giúp tránh các tình huống:

- Một client nhận file cũ từ cache nhưng metadata mới.
- Tên file cũ mang định dạng mới và bị giải mã sai.
- Checksum trong manifest không khớp cache.
- Một phần node CDN đã cập nhật, phần còn lại chưa.

## 15. Quy trình migration thực hành

### Giai đoạn 1: Ghi nhận baseline của pipeline cũ

Thu thập ít nhất:

| Thông tin | Ví dụ minh họa |
|---|---|
| JDK dùng để build | JDK 8 hoặc 11 |
| Task tạo Pack200 | `packDistribution` trong pipeline legacy |
| Đầu vào | `app.jar`, `lib/*.jar` |
| Đầu ra | `app.pack.gz` |
| Nơi lưu | HTTP server, file share hoặc repository |
| Consumer | Launcher/updater/desktop client |
| Bước giải nén | `unpack200` hoặc API Pack200 |
| Kiểm tra an toàn | Signature, SHA-256, manifest |
| Quy mô artifact | Số JAR, tổng MB và thời gian download |

Đo kích thước tải xuống và thời gian thực tế trước khi bỏ Pack200 để có cơ sở đánh giá. Không nên dùng một bản JAR nhỏ bất thường làm đại diện cho toàn bộ sản phẩm.

### Giai đoạn 2: Kiểm kê dependency Pack200

Tìm mọi lời gọi trực tiếp và gián tiếp đến tool/API. Lưu ý build plugin có thể gọi tool qua `JAVA_HOME` mà không xuất hiện chuỗi Pack200 trong source ứng dụng.

Phân loại từng kết quả:

- Bắt buộc cho chức năng runtime.
- Chỉ là tối ưu kích thước phân phối.
- Chỉ phục vụ artifact lưu trữ/lịch sử.
- Chỉ ở môi trường test hoặc build cũ.
- Không còn dùng nhưng chưa được xóa khỏi cấu hình.

Phân loại này giúp chọn hướng thay thế hợp lý, không nâng cấp quá mức.

### Giai đoạn 3: Thiết kế artifact cuối cùng

Chọn mục tiêu:

- Library: Maven coordinates và JAR.
- CLI/server: executable JAR hoặc application distribution.
- Container service: OCI image.
- Desktop: `jpackage` hoặc cơ chế installer/update được hỗ trợ.
- Modular runtime: `jlink` kết hợp kênh phân phối.
- Download trực tiếp: JAR + HTTPS + checksum/signature + versioned manifest.

Ghi rõ thông số:

```text
Artifact format     : jar / zip / OCI / installer
Build tool          : Maven / Gradle / tool khác
Java compatibility  : release target và runtime tối thiểu
Distribution target : repository / registry / HTTPS / CDN
Integrity           : SHA-256 / signature
Client support      : version và capability cần thiết
Rollback            : cách quay về artifact trước
```

### Giai đoạn 4: Bỏ bước Pack200

Không chỉ bỏ lệnh cuối của script nếu consumer vẫn trông đợi packed format. Cần thay đổi cả producer và consumer theo thiết kế ở giai đoạn trước.

Ví dụ luồng cũ:

```text
compile -> jar -> pack200 -> upload .pack.gz
                              |
                              v
                       download + unpack200
```

Luồng mới cho thư viện:

```text
compile -> test -> jar -> sign/checksum -> publish repository
                                           |
                                           v
                                   Maven/Gradle resolve
```

Luồng mới cho service:

```text
compile -> test -> jar -> build OCI image -> scan/sign -> push registry
                                                         |
                                                         v
                                                  deploy image
```

Không cần bước Pack200 ở luồng mới.

### Giai đoạn 5: Xác nhận bản phát hành trong môi trường đích

Kiểm tra:

1. Artifact được upload đúng định dạng và đúng version.
2. Consumer tải artifact và xác minh checksum.
3. Java runtime có thể đọc JAR hoặc image.
4. Manifest, resources, service providers và classpath/module path hoạt động.
5. Signed JAR vẫn xác minh hợp lệ sau mọi bước packaging.
6. Native libraries được đóng gói cho đúng OS/architecture.
7. Client cũ trong phạm vi hỗ trợ không bị phá vỡ.
8. Số liệu download và startup đáp ứng yêu cầu sản phẩm.
9. Pipeline rollback có thể khôi phục artifact trước.
10. Không còn task gọi executable/API Pack200 trên JDK đích.

### Giai đoạn 6: Theo dõi và dọn dẹp

Theo dõi log của server và updater để tìm request tới `.pack.gz`. Xóa cấu hình và documentation cũ khi có bằng chứng consumer đã chuyển xong. Có thể giữ artifact lịch sử ở vùng lưu trữ chỉ đọc với metadata phù hợp, nhưng không để một tool Pack200 cũ thành thành phần bắt buộc của pipeline phát hành hằng ngày.

## 16. Ma trận kiểm thử producer/consumer

Một upgrade giữa nhiều dịch vụ hoặc client có thể cần thử các tổ hợp sau:

| Producer | Consumer | Mục tiêu |
|---|---|---|
| Pipeline cũ tạo Pack200 | Client cũ | Baseline trước migration |
| Pipeline mới tạo JAR | Client mới | Luồng mục tiêu phải thành công |
| Pipeline cũ tạo Pack200 | Client mới có hỗ trợ legacy | Kiểm tra giai đoạn chuyển tiếp nếu cần |
| Pipeline mới tạo JAR | Client cũ | Xác định rõ có hỗ trợ hoặc từ chối có thông báo |
| Repository mới | Build tool hiện tại | Dependency resolution và metadata |
| OCI registry | Deployment mới | Pull/start/healthcheck/rollback |

Không nên kỳ vọng mọi tổ hợp đều tương thích. Quan trọng là tài liệu rõ những tổ hợp được hỗ trợ, và test phản ánh đúng chiến lược rollout.

### 16.1. Test chức năng JAR

Bộ test cơ bản:

- `jar --list` xem entry và manifest.
- `java -jar` hoặc classpath/module-path startup test.
- Resource loading qua `getResourceAsStream`.
- `ServiceLoader` tìm provider.
- Reflection/annotation/bytecode tools đọc class.
- Library consumer biên dịch và chạy với JAR mới.
- Test native integration nếu có.

Nếu trước đây Pack200 làm thay đổi biểu diễn JAR, consumer mới có thể dựa vào chi tiết ZIP entry order hoặc signature khác. Phải kiểm tra những điểm đó thay vì chỉ so sánh kích thước file.

### 16.2. Test khả năng tải và resume

Với HTTP/CDN:

- File lớn và mạng chậm.
- Kết nối bị ngắt giữa chừng.
- Range request hoặc resume nếu được hỗ trợ.
- Cache invalidation/versioned URL.
- Checksum mismatch và file download không đủ.
- Proxy thay đổi Content-Encoding.
- Client offline và cập nhật nhiều version một lần.

Bộ test này thường quan trọng hơn việc ép kích thước artifact đạt một con số nén nhất định.

### 16.3. Test tương thích JDK

Tối thiểu cần xác nhận artifact mới trên JDK mà sản phẩm cam kết hỗ trợ. Ví dụ:

- Build bằng JDK 21 nhưng `--release 17` nếu consumer phải dùng Java 17.
- Chạy trên JDK 21 và 25 nếu cả hai là target.
- Xác minh class-file version và API dùng trong artifact.
- Kiểm tra `jdeps`, dependency framework, native access và module encapsulation.

Việc loại bỏ Pack200 không tự động nâng class-file version hoặc sửa API không còn hỗ trợ. Đây là hai nhóm vấn đề migration riêng.

## 17. Troubleshooting sau migration

### Trường hợp A: Command không tồn tại

```text
pack200: command not found
```

**Nguyên nhân khả dĩ:** JDK đích đã loại bỏ tool hoặc script trỏ nhầm `JAVA_HOME`.

**Hướng xử lý:** xác định task gọi công cụ, loại bỏ hoặc thay bằng packaging mới. Không mặc định cài lại JDK cũ cho toàn bộ production.

### Trường hợp B: Không tìm thấy `java.util.jar.Pack200`

```text
cannot find symbol: class Pack200
```

**Nguyên nhân:** source hoặc dependency biên dịch với API Pack200 cũ trên JDK 14+.

**Hướng xử lý:** xóa/viết lại nhánh code, cập nhật dependency hoặc thay codec bằng giải pháp được hỗ trợ. Không chỉ sửa tham số `--release`.

### Trường hợp C: `.pack.gz` được tải nhưng không thể giải nén

**Nguyên nhân:** consumer hiện đại không có Pack200 unpacker, hoặc file không đúng định dạng/kết thúc không đầy đủ.

**Hướng xử lý:** xác định magic bytes/format theo công cụ đáng tin cậy, kiểm tra checksum, chuyển dữ liệu lịch sử trong môi trường kiểm soát hoặc cập nhật server phân phối JAR thông thường.

### Trường hợp D: JAR mới tải về nhưng JVM không chạy

**Nguyên nhân khả dĩ:** bytecode target cao hơn runtime, thiếu dependency, sai manifest main class, hoặc lỗi module/native library.

**Hướng xử lý:** kiểm tra `java -version`, class-file version, `jar --list`, startup command và dependency runtime. Không mặc định đó là lỗi do bỏ Pack200.

### Trường hợp E: Chữ ký JAR không hợp lệ

**Nguyên nhân khả dĩ:** JAR bị biến đổi sau khi ký hoặc chữ ký còn gắn với artifact cũ.

**Hướng xử lý:** ký lại artifact cuối cùng theo chính sách, chạy `jarsigner -verify`, kiểm tra chain và metadata. Không chuyển chữ ký từ packed stream sang JAR mới một cách cơ học.

### Trường hợp F: Kích thước tải tăng

**Nguyên nhân:** Pack200 từng nén hiệu quả đối với tập class file cụ thể; JAR/ZIP hoặc gzip thông thường có thể tạo file lớn hơn.

**Hướng xử lý:** đo băng thông, caching, deduplication và CDN; thử encoding tương thích với consumer, tối ưu dependency không cần thiết, xem xét OCI layers hoặc split artifact theo module. Không chọn một codec hiếm chỉ vì kết quả nén tốt trên một benchmark nhỏ.

### Trường hợp G: Maven/Gradle không lấy được artifact

**Nguyên nhân:** tọa độ dependency, metadata, credentials, proxy hoặc versioning repository sai.

**Hướng xử lý:** xác nhận `group/artifact/version`, repository URL, quyền truy cập, POM/module metadata, checksum và cache. Không liên hệ sai với công cụ Pack200 vốn đã không còn trong luồng tải chuẩn.

### Trường hợp H: Client cũ bị lỗi sau thay đổi endpoint

**Nguyên nhân:** client vẫn cố unpack Pack200 dù endpoint trả JAR, hoặc cache lưu file cũ.

**Hướng xử lý:** có version negotiation/manifest, update client theo giai đoạn, sử dụng immutable URL và thông báo rõ thời điểm ngừng hỗ trợ định dạng cũ.

## 18. Những sai lầm cần tránh

**Cho rằng Pack200 và JAR ZIP là cùng một định dạng.** JAR dùng ZIP và JVM đọc trực tiếp; Pack200 là format riêng cần unpack trước.

**Chỉ đổi đuôi file.** Đổi `.pack.gz` sang `.jar.gz` không chuyển cấu trúc Pack200 thành gzip của JAR.

**Cho rằng `--release 8` mang Pack200 API trở lại.** Compiler target không phục hồi những tool/API đã bị xóa khỏi JDK hiện tại.

**Thay bằng `System.gc()` hay một tùy chọn JVM.** Pack200 là vấn đề định dạng phân phối, hoàn toàn không liên quan garbage collector.

**Tìm một executable Pack200 cũ rồi nhét vào production image.** Điều này tạo dependency legacy, rủi ro bảo trì/bảo mật và khó kiểm soát version.

**Chỉ sửa producer.** Nếu consumer vẫn yêu cầu `unpack200`, migration chưa hoàn tất.

**Giả định mọi JAR mới phải được đóng thành fat JAR.** Chọn thin JAR, fat JAR hoặc distribution theo nhu cầu, không theo thói quen.

**Quên ký hoặc xác minh artifact cuối cùng.** Chuyển định dạng có thể làm checksum/signature cũ không còn phù hợp.

**Dùng file version cố định có thể bị ghi đè.** Cache và rollback sẽ khó quản lý nếu cùng URL/coordinates chứa nhiều nội dung khác nhau.

**Đánh giá thành công chỉ bằng build.** Cần kiểm thử download, resource loading, startup và luồng cập nhật thực tế.

**Coi `jlink`, `jpackage` và OCI image là codec nén tương đương.** Chúng giải quyết đóng gói runtime, cài đặt hoặc triển khai; không có mục đích hay đầu ra giống Pack200.

## 19. Checklist hoàn tất migration khỏi Pack200

### Kiểm kê

- [ ] Đã tìm mọi lời gọi `pack200`, `unpack200` và `java.util.jar.Pack200`.
- [ ] Đã kiểm tra Maven/Gradle/Ant plugin, shell script, CI và Dockerfile.
- [ ] Đã nhận diện mọi artifact `.pack` / `.pack.gz` đang được phát hành.
- [ ] Đã xác định consumer nào phụ thuộc vào giải nén Pack200.
- [ ] Đã ghi nhận artifact lịch sử cần chuyển đổi hoặc lưu trữ.

### Thiết kế phân phối mới

- [ ] Đã chọn định dạng mục tiêu theo loại sản phẩm: JAR, repository, OCI hoặc installer.
- [ ] Đã phân biệt JAR compression và HTTP/transport compression.
- [ ] Đã công bố Java runtime tối thiểu và các dependency runtime.
- [ ] Đã thiết lập versioned artifact, provenance và cơ chế rollback.
- [ ] Đã chọn checksum/signature và quy trình kiểm tra ở phía nhận.
- [ ] Đã lập lộ trình chuyển client cũ nếu không nâng cấp đồng thời.

### Pipeline và validation

- [ ] Pipeline mới không gọi Pack200 tool/API trên JDK 14+.
- [ ] Artifact cuối cùng có thể được tải và dùng trực tiếp theo format đã công bố.
- [ ] JAR manifest, resources, services và classpath/module path đã được kiểm tra.
- [ ] Signed artifact và checksum được xác minh sau bước packaging cuối.
- [ ] Build tool và repository metadata hoạt động với consumer thực tế.
- [ ] Kiểm thử network, cache, resume và corrupted download đã chạy nếu áp dụng.
- [ ] Kích thước tải, thời gian tải và độ phức tạp vận hành được so với baseline.
- [ ] Đã thử rollback hoặc phục hồi bản phát hành trước.

### Dọn dẹp

- [ ] Đã loại bỏ mọi hướng dẫn yêu cầu `unpack200` ở môi trường mới.
- [ ] Endpoint Pack200 cũ có kế hoạch ngừng hỗ trợ rõ ràng.
- [ ] Archive lịch sử có metadata chuyển đổi và không đòi JDK cũ ở production.
- [ ] Tài liệu build/deploy và release notes phản ánh cơ chế phân phối mới.

## 20. Bài tập thực hành

### Bài tập 1: Nhận diện dependency Pack200

Cho một pipeline có các bước:

```text
gradle assemble
pack200 web/app.pack.gz build/libs/app.jar
upload web/app.pack.gz
```

Hãy xác định bước nào sẽ thất bại nếu pipeline chuyển sang JDK 21, và những thành phần nào ở máy khách cần được kiểm tra trước khi bỏ bước đó.

**Gợi ý:** chỉ có `gradle assemble` chưa chứng minh được consumer hỗ trợ JAR. Cần tìm launcher/updater và format download thực tế.

### Bài tập 2: Thiết kế phương án cho thư viện dùng chung

Một thư viện được năm service sử dụng và hiện được đóng gói thành `core.pack.gz` rồi copy vào mỗi server. Hãy thiết kế phương án dùng Maven-compatible repository:

1. Xác định `groupId`, `artifactId`, `version`.
2. Xuất bản JAR và dependency metadata.
3. Sửa khai báo dependency của từng consumer.
4. Thiết lập kiểm tra checksum và artifact immutability.
5. Đề xuất cách rollout/rollback mà không phải copy file thủ công.

### Bài tập 3: So sánh kích thước và tính đúng đắn

Với một ứng dụng có nhiều class/resource, tạo các artifact theo những phương án được hỗ trợ trong môi trường:

- JAR thường.
- Gzip của JAR.
- Application distribution hoặc OCI image nếu đúng loại sản phẩm.

Đo kích thước, CPU và thời gian tải; chạy cùng bộ smoke test trên đúng JDK mục tiêu. Đừng chỉ chọn artifact nhỏ nhất nếu nó làm consumer khó triển khai hoặc không có cơ chế cập nhật an toàn.

### Bài tập 4: Kế hoạch xử lý artifact lịch sử

Một kho lưu trữ còn các file `.pack.gz` của phiên bản năm trước, nhưng tất cả server hiện tại đã dùng JDK 21. Hãy lập quy trình chuyển đổi ngoại tuyến một lần, gồm kiểm tra nguồn, môi trường công cụ, unpack, validation, checksum, version mapping và lưu trữ artifact sau chuyển đổi.

## Kết luận

Pack200 từng là giải pháp nén JAR chuyên biệt trong một giai đoạn phát triển của Java, nhưng đã bị deprecated for removal ở JDK 11 và bị loại bỏ khỏi JDK 14 theo JEP 367. Vì vậy, ứng dụng nâng cấp lên JDK hiện đại không thể tiếp tục dựa vào `pack200`, `unpack200` hoặc `java.util.jar.Pack200` như một phần được JDK bảo đảm.

Đường migration bền vững không đơn giản là tìm một codec thay thế có tỷ lệ nén tương đương, mà là làm rõ nhu cầu phân phối: thư viện thì dùng JAR và Maven-compatible repository; service có thể dùng executable JAR hoặc OCI image; desktop có thể dùng `jpackage`; runtime modular có thể dùng `jlink`; tải trực tiếp có thể dùng HTTPS/CDN, versioned manifest và checksum/signature. Với mỗi lựa chọn, hãy sửa cả producer lẫn consumer, kiểm tra artifact cuối cùng và giữ lộ trình chuyển đổi cho dữ liệu legacy.

Khi loại bỏ Pack200 khỏi pipeline một cách có kiểm soát, hệ thống vừa tránh phụ thuộc vào API và công cụ đã ngừng hỗ trợ, vừa đơn giản hóa build, cập nhật, kiểm chứng nguồn gốc và triển khai trên các phiên bản Java mới.

