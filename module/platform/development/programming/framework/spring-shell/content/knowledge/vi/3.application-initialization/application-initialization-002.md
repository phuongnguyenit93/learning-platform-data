# Khai báo phụ thuộc bằng Maven hoặc Gradle

Để xây dựng ứng dụng dòng lệnh bằng Spring Shell, dự án Java cần có các thư viện Spring Boot và Spring Shell trên classpath. Maven và Gradle đều quản lý việc khai báo, tải xuống, chọn phiên bản và đưa các thư viện này vào quá trình biên dịch cũng như chạy ứng dụng.

Bài học thuộc chương **Khởi tạo ứng dụng** của Spring Shell. Nội dung hướng dẫn chọn starter phù hợp, quản lý phiên bản bằng BOM, khai báo dependency trong Maven hoặc Gradle và xác minh ứng dụng sau khi thêm thư viện.

Sau bài học, bạn có thể:

- Xác định dependency chính cần có để khởi tạo ứng dụng Spring Shell 3.x.
- Khai báo `spring-shell-starter` trong `pom.xml` hoặc file build Gradle.
- Quản lý phiên bản các module Spring Shell bằng `spring-shell-dependencies` BOM.
- Kiểm tra dependency tree, build và chạy ứng dụng để phát hiện lỗi cấu hình.
- Nhận biết thay đổi về chế độ tương tác trong các phiên bản Spring Shell 3.x.

## Thành phần cần thêm vào dự án

Spring Shell tích hợp với Spring Boot để khởi tạo application context, nạp cấu hình và cung cấp các thành phần cần thiết cho command line. Với một ứng dụng Spring Boot thông thường, dependency cơ bản gồm:

| Dependency | Vai trò |
| --- | --- |
| `org.springframework.boot:spring-boot-starter` | Cung cấp nền tảng Spring Boot và các thành phần cơ bản để khởi tạo ứng dụng. |
| `org.springframework.shell:spring-shell-starter` | Tập hợp các module Spring Shell cần thiết để xây dựng ứng dụng shell. |
| `org.springframework.boot:spring-boot-starter-test` | Cung cấp thư viện kiểm thử cho mã ứng dụng và integration test. Dependency này thuộc cấu hình kiểm thử. |

Nếu dự án đã được tạo từ Spring Initializr với Spring Boot, `spring-boot-starter` thường đã có trong cấu hình. Khi đó, công việc chính là thêm `spring-shell-starter` và quản lý phiên bản tương ứng.

Không nên thêm riêng từng module nội bộ của Spring Shell khi chưa có nhu cầu rõ ràng. Starter là điểm bắt đầu phù hợp vì nó tập hợp các thành phần cơ bản và giúp giảm nguy cơ bỏ sót dependency cần thiết.

## Quản lý phiên bản Spring Shell

Spring Shell 3.x được phát triển trên nền tảng Spring Boot 3.x và yêu cầu JDK 17 theo baseline của dòng phiên bản này. Phiên bản Spring Shell cụ thể còn gắn với các phiên bản Spring Boot và Spring Framework tương ứng. Vì vậy, cần chọn một bộ phiên bản tương thích thay vì nâng riêng lẻ từng thư viện Spring.

Spring Shell cung cấp BOM có tọa độ:

```text
org.springframework.shell:spring-shell-dependencies:<spring-shell-version>
```

BOM (Bill of Materials) tập trung thông tin phiên bản của các dependency thuộc Spring Shell. Khi import BOM, các dependency do BOM quản lý có thể được khai báo mà không phải lặp lại version ở từng dòng. Cách này giúp các module Spring Shell sử dụng những phiên bản đã được kiểm tra cùng nhau.

Trong các ví dụ bên dưới, `3.x.y` là ký hiệu giữ chỗ cho một phiên bản Spring Shell 3.x đã phát hành. Hãy thay nó bằng phiên bản thực tế tương thích với Spring Boot và JDK của dự án. Không đưa nguyên văn `3.x.y` vào build file vì đây không phải một phiên bản artifact cụ thể.

## Khai báo dependency bằng Maven

Maven đọc cấu hình dự án từ file `pom.xml`. Phần `dependencies` khai báo thư viện mà ứng dụng sử dụng; phần `dependencyManagement` quản lý phiên bản và metadata của dependency.

### Import Spring Shell BOM

Ví dụ sau giả định dự án đã khai báo parent hoặc dependency management phù hợp của Spring Boot. BOM của Spring Shell được import để quản lý phiên bản các module Spring Shell:

```xml
<properties>
    <java.version>17</java.version>
    <spring-shell.version>3.x.y</spring-shell.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.shell</groupId>
            <artifactId>spring-shell-dependencies</artifactId>
            <version>${spring-shell.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.shell</groupId>
        <artifactId>spring-shell-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Các phần chính:

1. `spring-shell.version` giữ phiên bản Spring Shell tại một vị trí để dễ nâng cấp.
2. `spring-shell-dependencies` được import với `type` là `pom` và `scope` là `import`. Đây là cách Maven nhập quy tắc quản lý dependency từ BOM.
3. `spring-shell-starter` không cần khai báo version riêng vì BOM đã quản lý phiên bản của nó.
4. `spring-boot-starter-test` có scope `test`, do đó chỉ được dùng trong quá trình biên dịch và chạy kiểm thử.

Khi dự án không import BOM, có thể khai báo version trực tiếp trên `spring-shell-starter`:

```xml
<dependency>
    <groupId>org.springframework.shell</groupId>
    <artifactId>spring-shell-starter</artifactId>
    <version>${spring-shell.version}</version>
</dependency>
```

Chọn một cách quản lý phiên bản rõ ràng. Nếu đã import BOM, không cần lặp lại cùng version ở từng dependency Spring Shell trừ khi có chủ đích ghi đè phiên bản.

### Build và kiểm tra bằng Maven

Với Maven Wrapper có sẵn trong dự án, có thể dùng các lệnh sau từ thư mục chứa `pom.xml`:

```bash
# Hiển thị các dependency thuộc Spring Shell
./mvnw dependency:tree -Dincludes=org.springframework.shell

# Biên dịch, chạy kiểm thử và đóng gói
./mvnw clean package

# Chạy ứng dụng trong môi trường phát triển
./mvnw spring-boot:run
```

`dependency:tree` cho biết starter và các module Spring Shell nào được kéo vào thông qua dependency bắc cầu. Nếu dự án dùng Windows, có thể chạy `mvnw.cmd` thay cho `./mvnw`. Lệnh `spring-boot:run` yêu cầu dự án đã cấu hình Spring Boot Maven Plugin.

## Khai báo dependency bằng Gradle

Gradle khai báo thư viện trong khối `dependencies`. Với thư viện mà mã ứng dụng cần khi biên dịch và lúc chạy, cấu hình thông dụng là `implementation`. Có thể import BOM bằng `platform(...)` để quản lý phiên bản tập trung.

### Gradle Groovy DSL

Trong file `build.gradle`:

```groovy
dependencies {
    implementation platform("org.springframework.shell:spring-shell-dependencies:3.x.y")

    implementation "org.springframework.boot:spring-boot-starter"
    implementation "org.springframework.shell:spring-shell-starter"

    testImplementation "org.springframework.boot:spring-boot-starter-test"
}
```

### Gradle Kotlin DSL

Trong file `build.gradle.kts`:

```kotlin
dependencies {
    implementation(platform("org.springframework.shell:spring-shell-dependencies:3.x.y"))

    implementation("org.springframework.boot:spring-boot-starter")
    implementation("org.springframework.shell:spring-shell-starter")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Ở cả hai DSL, `platform(...)` đưa BOM vào dependency graph của Gradle. Các dependency Spring Shell được quản lý phiên bản theo BOM nên không cần thêm version riêng vào `spring-shell-starter`.

Nếu không dùng BOM, có thể chỉ định version trực tiếp:

```kotlin
dependencies {
    implementation("org.springframework.shell:spring-shell-starter:3.x.y")
}
```

Tương tự Maven, hãy thay `3.x.y` bằng một phiên bản thực tế và duy trì cùng một chiến lược quản lý phiên bản trong toàn dự án.

### Build và kiểm tra bằng Gradle

Với Gradle Wrapper có sẵn, chạy lệnh từ thư mục chứa `build.gradle` hoặc `build.gradle.kts`:

```bash
# Xem cây dependency của runtime classpath
./gradlew dependencies --configuration runtimeClasspath

# Xem lý do một phiên bản Spring Shell được chọn
./gradlew dependencyInsight --dependency spring-shell-starter --configuration runtimeClasspath

# Build và chạy kiểm thử
./gradlew clean build

# Chạy ứng dụng trong môi trường phát triển
./gradlew bootRun
```

`dependencyInsight` hữu ích khi nhiều dependency bắc cầu yêu cầu các phiên bản khác nhau. Lệnh `bootRun` cần dự án đã cấu hình Spring Boot Gradle Plugin. Trên Windows, dùng `gradlew.bat`.

## Chọn cấu hình phù hợp

| Tiêu chí | Maven | Gradle |
| --- | --- | --- |
| File cấu hình | `pom.xml` | `build.gradle` hoặc `build.gradle.kts` |
| Khai báo thư viện | Thẻ `dependency` trong `dependencies` | `implementation(...)` trong `dependencies` |
| Import BOM | `dependencyManagement` với `type=pom`, `scope=import` | `platform(...)` hoặc plugin quản lý dependency tương ứng |
| Kiểm tra dependency | `dependency:tree` | `dependencies`, `dependencyInsight` |
| Build phổ biến | `./mvnw clean package` | `./gradlew clean build` |

Hai công cụ có cùng mục tiêu là tạo classpath nhất quán cho dự án. Việc chọn Maven hay Gradle thường phụ thuộc vào công cụ mà nhóm đang dùng, cấu trúc build hiện tại và mức độ tùy biến cần thiết.

## Khởi chạy ứng dụng sau khi thêm dependency

Sau khi dependency được phân giải thành công, Spring Boot có thể tạo application context và Spring Shell đăng ký các thành phần shell. Có thể đóng gói ứng dụng thành executable JAR rồi gọi lệnh tích hợp `help` để xác minh:

```bash
# Maven: sau khi package
java -jar target/<ten-ung-dung>.jar help

# Gradle: sau khi build
java -jar build/libs/<ten-ung-dung>.jar help
```

Tên file JAR thực tế phụ thuộc vào `artifactId`, `version` và cấu hình archive của dự án. Nếu ứng dụng khởi động thành công và hiển thị danh sách lệnh tích hợp, dependency cơ bản đã được nạp. Khi chưa có command do ứng dụng tự định nghĩa, danh sách vẫn có thể chứa các lệnh tích hợp của Spring Shell.

### Chế độ tương tác trong Spring Shell 3.x

Khi khởi tạo ứng dụng, cần phân biệt chế độ chạy lệnh đơn với REPL tương tác. REPL (Read-Eval-Print Loop) đọc lệnh từ terminal, thực thi rồi hiển thị kết quả trong cùng một phiên.

Spring Shell 3.x có thay đổi mặc định giữa các nhánh nhỏ:

- Đến dòng 3.2.x, các shell runner được bật mặc định.
- Từ dòng 3.3.x, `NonInteractiveShellRunner` được bật mặc định; muốn mở REPL cần bật `InteractiveShellRunner`.

Để bật chế độ tương tác ở dòng 3.3.x, thêm cấu hình vào `application.yml`:

```yaml
spring:
  shell:
    interactive:
      enabled: true
```

Khi chạy `java -jar <file.jar>` trong terminal, ứng dụng có thể hiển thị dấu nhắc để người dùng nhập nhiều lệnh. Khi truyền tên command sau tên JAR, chẳng hạn `java -jar <file.jar> help`, ứng dụng thực thi theo chế độ không tương tác rồi kết thúc.

Trong kiểm thử tự động, không bật REPL tương tác nếu test chỉ cần khởi tạo application context hoặc gọi command theo cách không tương tác. Nếu integration test bị treo hoặc không kết thúc, hãy kiểm tra runner đang được bật và cấu hình profile test trước khi kết luận dependency bị lỗi.

## Lỗi thường gặp khi khai báo dependency

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy `spring-shell-starter` | Sai group ID, artifact ID hoặc phiên bản chưa được phát hành. | Kiểm tra tọa độ `org.springframework.shell:spring-shell-starter` và phiên bản trong BOM. |
| Maven báo thiếu version | Dependency chưa được BOM quản lý và cũng chưa có version trực tiếp. | Import `spring-shell-dependencies` hoặc khai báo version cho dependency. |
| Gradle không phân giải được version | Chưa import BOM bằng `platform(...)` hoặc thiếu version trực tiếp. | Kiểm tra khối `dependencies` và tọa độ BOM. |
| Lỗi tương thích Spring Boot hoặc Java | Chọn Spring Shell, Spring Boot hoặc JDK không cùng bộ tương thích. | Đối chiếu tài liệu và ghi chú phát hành của phiên bản Spring Shell định dùng. |
| Có nhiều phiên bản Spring Shell trong dependency tree | Dependency bắc cầu kéo vào phiên bản khác hoặc dự án ghi đè version. | Dùng `dependency:tree` hoặc `dependencyInsight` để xác định nguồn và điều chỉnh BOM/constraint. |
| Ứng dụng chạy lệnh đơn nhưng không hiện dấu nhắc | Interactive runner chưa được bật trong nhánh 3.3.x. | Kiểm tra `spring.shell.interactive.enabled` và cấu hình môi trường chạy. |
| Integration test không kết thúc | Runner tương tác được bật trong môi trường kiểm thử hoặc test khởi tạo shell không phù hợp. | Tách cấu hình test và không bật REPL nếu bài kiểm thử không cần terminal tương tác. |

## Quy trình thực hành đề xuất

Khi tạo một dự án Spring Shell mới, có thể thực hiện theo trình tự sau:

1. Xác định phiên bản JDK và phiên bản Spring Boot mà dự án sử dụng.
2. Chọn phiên bản Spring Shell 3.x tương thích với bộ nền tảng đó.
3. Thêm `spring-shell-starter` và import `spring-shell-dependencies` BOM trong Maven hoặc Gradle.
4. Đồng bộ dependency và xem dependency tree để xác nhận đúng phiên bản được chọn.
5. Build ứng dụng, sau đó chạy JAR với command `help` để kiểm tra khả năng khởi tạo.
6. Nếu cần REPL, kiểm tra cấu hình interactive runner theo nhánh Spring Shell đang sử dụng.
7. Giữ cấu hình kiểm thử không tương tác để các bài test có thể chạy tự động và kết thúc ổn định.

Việc khai báo dependency là bước đầu để Spring Shell tham gia vào application context. Khi starter và BOM được cấu hình đúng, dự án có thể sử dụng các API khai báo command, xử lý input, trợ giúp và tự hoàn thành ở những bài học tiếp theo.

## Tài liệu tham khảo

- [Spring Shell 3.3 — Getting Started](https://docs.spring.io/spring-shell/reference/3.3/getting-started.html): ví dụ khai báo dependency Maven/Gradle, BOM và cấu hình interactive runner.
- [Spring Shell Reference Documentation](https://docs.spring.io/spring-shell/reference/): tài liệu tham chiếu và hướng dẫn theo phiên bản Spring Shell.
