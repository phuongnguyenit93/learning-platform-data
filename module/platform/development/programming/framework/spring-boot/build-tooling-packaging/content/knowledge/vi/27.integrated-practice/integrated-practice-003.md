# Tạo JAR thực thi và kiểm chứng chạy trên máy chỉ có JRE phù hợp

## 1. Mục tiêu và ranh giới giữa build machine với runtime machine

Một ứng dụng Spring Boot có thể được đóng gói thành **executable JAR** để triển khai trên máy chỉ cài Java Runtime Environment (JRE) hoặc một runtime image tương đương. Máy chạy ứng dụng không cần source code, Maven, Gradle hay Java compiler. Nó cần runtime Java tương thích, file JAR thực thi và những tài nguyên bên ngoài mà ứng dụng thực sự sử dụng.

Cần phân biệt hai máy:

| Máy | Thành phần cần có | Công việc |
|---|---|---|
| **Build machine** | JDK phù hợp, Maven hoặc Gradle, source code và dependency repositories | Biên dịch, chạy test, đóng gói executable JAR, kiểm tra manifest và archive |
| **Runtime machine** | JRE/runtime Java phù hợp, executable JAR, cấu hình và kết nối cần thiết | Chạy ứng dụng bằng java -jar, theo dõi log và kiểm tra endpoint |

**Executable JAR không đồng nghĩa với JAR chứa cả JVM.** Spring Boot đóng gói application classes, Spring Boot Loader và các dependency Java cần thiết vào archive. JVM/JRE vẫn được cung cấp bởi máy đích. Vì vậy, JAR chạy được trên JDK ở máy phát triển chưa đủ chứng minh nó chạy được trên runtime máy đích; phải kiểm tra đúng phiên bản Java và hệ điều hành triển khai.

Trong bài thực hành, ta dùng Java 17 và Spring Boot 3.5.16. Theo tài liệu hệ thống của Spring Boot 3.5.16, Java 17 là mức tối thiểu; Maven cần từ 3.6.3 và Gradle cần 7.6.4 trở lên trong nhánh 7.x hoặc 8.4 trở lên trong nhánh 8.x. Hãy kiểm tra yêu cầu của đúng Spring Boot release mà dự án đang dùng: [Spring Boot 3.5.16 System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html).

## 2. JDK, JRE và executable JAR khác nhau ở đâu?

### 2.1. JDK và JRE

- **JDK (Java Development Kit)** có compiler javac, công cụ đóng gói jar, javadoc, jdeps, jcmd, jstack và runtime để chạy Java.
- **JRE/runtime image** cung cấp JVM và các module Java cần thiết để chạy ứng dụng. Nó không nhất thiết có compiler hay các công cụ phát triển.
- **Executable Spring Boot JAR** chứa ứng dụng, loader và thư viện ứng dụng được đóng gói. Nó không tự mang theo JRE.

Một số nhà cung cấp Java hiện phân phối runtime dưới dạng runtime-only package hoặc custom runtime image thay vì một bộ cài đặt riêng mang tên JRE. Trong bài này, “máy chỉ có JRE” có nghĩa là máy có Java runtime tương thích nhưng không có bộ công cụ phát triển JDK.

### 2.2. Những gì nằm trong executable JAR?

Executable JAR Spring Boot thường có cấu trúc:

```text
runtime-jar-demo-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   └── com/example/runtimejardemo/...
    └── lib/
        ├── spring-boot-*.jar
        ├── spring-core-*.jar
        ├── spring-web-*.jar
        └── ... các dependency runtime khác
```

| Thành phần | Có trong executable JAR? | Nguồn |
|---|---|---|
| Application classes/resources | Có | Project build output |
| Spring Boot Loader | Có | Spring Boot packaging plugin |
| Dependency Java runtime được đóng gói | Có, nếu nằm trong packaging classpath | Maven/Gradle dependency configuration |
| JVM/JRE | Không | Runtime machine |
| OS packages, native libraries của hệ điều hành | Không mặc nhiên có | Runtime machine hoặc môi trường triển khai |
| Database, message broker, file cấu hình ngoài | Không mặc nhiên có | Hạ tầng bên ngoài |

BOOT-INF/classes/ chứa class và resource của ứng dụng; BOOT-INF/lib/ chứa nested dependency JAR. Spring Boot Loader đọc cấu trúc này khi khởi chạy. Tài liệu chính thức: [Spring Boot Executable JAR](https://docs.spring.io/spring-boot/specification/executable-jar/index.html).

**Hệ quả:** không cần chép từng dependency JAR sang runtime machine nếu chúng đã được đóng đúng vào executable JAR. Tuy nhiên, dependency bị loại khỏi runtime packaging, dependency có scope provided, native library hoặc file cấu hình ngoài vẫn cần được xử lý riêng.

## 3. Chọn đúng Java runtime cho máy đích

### 3.1. Khớp Java feature version

Nếu build ứng dụng bằng Java 17, lựa chọn dễ kiểm soát nhất là chạy trên Java 17 runtime. Java runtime mới hơn có thể chạy bytecode cũ trong phần lớn trường hợp, nhưng vẫn cần kiểm tra API, dependency và hành vi thực tế.

Ví dụ lỗi khi một class được biên dịch cho Java 21 nhưng máy chỉ có Java 17:

```text
java.lang.UnsupportedClassVersionError:
... has been compiled by a more recent version of the Java Runtime
(class file version 65.0), this version of the Java Runtime
only recognizes class file versions up to 61.0
```

Một số mốc class file phổ biến:

| Java release | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Nếu runtime báo major version 65 nhưng chỉ hỗ trợ tới 61, ứng dụng hoặc một dependency được build bằng Java 21 trong khi runtime chỉ là Java 17. Nâng JRE lên version phù hợp hoặc build toàn bộ ứng dụng và dependency theo baseline mà runtime hỗ trợ.

### 3.2. Dùng compiler release để cố định baseline

Với Maven, Spring Boot parent cho phép đặt:

```xml
<properties>
    <java.version>17</java.version>
</properties>
```

Với Maven Compiler Plugin độc lập, có thể cấu hình maven.compiler.release là 17. Tùy chọn release giới hạn ngôn ngữ, bytecode và Java platform API mà source được phép sử dụng theo release đã chọn.

Với Gradle:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Toolchain giúp build chọn đúng JDK compiler. Tuy nhiên, cấu hình compiler không tự hạ bytecode của dependency bên thứ ba. Hãy xác nhận mọi thư viện runtime đều hỗ trợ Java 17.

**Khuyến nghị:** nếu production chỉ có Java 17 runtime, hãy build và test bằng JDK 17, sau đó chạy thử chính artifact đó trên runtime-only Java 17 cùng hệ điều hành/architecture mục tiêu.

### 3.3. Kiểm tra runtime trên máy đích

Linux/macOS:

```bash
java -version
java -XshowSettings:properties -version 2>&1 |
  grep -E 'java.version|java.home|os.arch'
```

Windows PowerShell:

```powershell
java -version
java -XshowSettings:properties -version 2>&1 |
  Select-String 'java.version|java.home|os.arch'
```

Kiểm tra các thông tin:

- java.version: feature/patch version đang chạy.
- java.vendor: nhà cung cấp runtime.
- java.home: thư mục runtime đang được dùng.
- os.arch: kiến trúc CPU mà JVM nhận diện.

Có thể dùng runtime từ nhiều vendor, nhưng production nên thống nhất vendor, patch level, OS và architecture để dễ tái hiện lỗi.

## 4. Tạo Spring Boot executable JAR bằng Maven

### 4.1. Cấu trúc project

Ta tạo một web application nhỏ có endpoint /runtime-check. Khi chạy thành công trên máy chỉ có JRE, endpoint trả về nội dung cố định để smoke test.

```text
runtime-jar-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/runtimejardemo/
    │   ├── RuntimeJarDemoApplication.java
    │   └── RuntimeCheckController.java
    └── test/java/com/example/runtimejardemo/
        └── RuntimeCheckControllerTest.java
```

### 4.2. POM

File pom.xml:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>runtime-jar-demo</artifactId>
    <version>1.0.0</version>
    <name>Runtime JAR Demo</name>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Vì project dùng spring-boot-starter-parent, Spring Boot Maven Plugin có execution repackage được parent cấu hình sẵn. Goal này chạy ở phase package, chuyển archive Maven tạo thành executable Boot JAR. Nếu không dùng parent, cần khai báo execution repackage phù hợp trong plugin. Xem [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html).

### 4.3. Main class

File src/main/java/com/example/runtimejardemo/RuntimeJarDemoApplication.java:

```java
package com.example.runtimejardemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuntimeJarDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RuntimeJarDemoApplication.class, args);
    }
}
```

### 4.4. Controller

File src/main/java/com/example/runtimejardemo/RuntimeCheckController.java:

```java
package com.example.runtimejardemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RuntimeCheckController {

    @GetMapping("/runtime-check")
    public String runtimeCheck() {
        return "runtime-jar-demo: OK";
    }
}
```

Endpoint trả về một chuỗi cố định để smoke test. Phiên bản Java thực tế vẫn được xác nhận riêng bằng java -version trên máy đích.

### 4.5. Integration test

File src/test/java/com/example/runtimejardemo/RuntimeCheckControllerTest.java:

```java
package com.example.runtimejardemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RuntimeCheckControllerTest {

    @Autowired
    private TestRestTemplate http;

    @Test
    void runtimeCheckEndpointReturnsOk() {
        String response = http.getForObject(
            "/runtime-check",
            String.class
        );

        assertThat(response).isEqualTo("runtime-jar-demo: OK");
    }
}
```

Test khởi động Spring Boot trên cổng ngẫu nhiên và gửi HTTP request tới controller. Nó xác nhận application context và endpoint hoạt động trong môi trường test của build machine; bước chạy trên JRE-only machine ở phần sau vẫn cần được thực hiện riêng.

### 4.6. Build executable JAR

Trên build machine có JDK 17 và Maven:

```bash
java -version
mvn -version
mvn clean verify
```

Sau khi build thành công, artifact chính là:

```text
target/runtime-jar-demo-1.0.0.jar
```

mvn verify chạy các phase trước đó, gồm compile, test và package, rồi thực hiện các kiểm tra được bind vào verify. Nếu test thất bại, không phát hành artifact của lần build đó.

## 5. Kiểm tra JAR trước khi chuyển sang máy đích

### 5.1. Xác nhận archive có cấu trúc executable

Trên build machine có JDK:

```bash
jar tf target/runtime-jar-demo-1.0.0.jar |
  grep -E '^(META-INF/MANIFEST.MF|org/springframework/boot/loader/|BOOT-INF/classes/|BOOT-INF/lib/)'
```

Một executable Boot JAR cần có manifest, Boot Loader, application classes trong BOOT-INF/classes/ và dependency JAR trong BOOT-INF/lib/.

Nếu chỉ thấy package class của ứng dụng mà không có Boot Loader/nested dependencies, có thể bạn đang xem plain JAR hoặc plugin repackage chưa chạy.

### 5.2. Kiểm tra manifest

Linux/macOS nếu có unzip:

```bash
unzip -p target/runtime-jar-demo-1.0.0.jar META-INF/MANIFEST.MF
```

Hoặc trích manifest bằng JDK:

```bash
mkdir -p target/manifest-check
cd target/manifest-check
jar xf ../runtime-jar-demo-1.0.0.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
```

Manifest executable Spring Boot thường có:

- Main-Class: lớp launcher của Spring Boot Loader.
- Start-Class: main class của ứng dụng.
- Các thuộc tính classpath/index nếu cấu hình archive sử dụng chúng.

Đối chiếu Start-Class với RuntimeJarDemoApplication. Main-Class thường trỏ tới Boot Loader, không nhất thiết là main class ứng dụng.

### 5.3. Phân biệt executable JAR với plain JAR

| Dấu hiệu | Executable Boot JAR | Plain JAR |
|---|---|---|
| Boot Loader | Có | Thường không |
| Application classes | BOOT-INF/classes/ | Thường ở root package path |
| Dependency JAR | BOOT-INF/lib/ | Không tự đóng dependencies theo layout Boot |
| Manifest launcher | Có cấu hình để chạy java -jar | Có thể không có Main-Class phù hợp |
| Cách chạy | java -jar app.jar | Phụ thuộc manifest/classpath và cách đóng gói |

Không chọn artifact chỉ dựa vào tên file hoặc kích thước. Kiểm tra manifest và archive layout.

### 5.4. Kiểm tra checksum trước khi chuyển file

Linux/macOS:

```bash
sha256sum target/runtime-jar-demo-1.0.0.jar
```

Windows PowerShell:

```powershell
Get-FileHash ./target/runtime-jar-demo-1.0.0.jar -Algorithm SHA256
```

Ghi lại SHA-256 cùng build ID/commit. Sau khi copy sang runtime machine, tính lại hash và so sánh. Nếu khác, kiểm tra quá trình upload/download, file bị cắt hoặc copy nhầm artifact.

## 6. Chuyển artifact sang máy chỉ có JRE

Chỉ chuyển executable JAR đã xác minh cùng các file cấu hình ngoài mà ứng dụng cần. Không cần chuyển source code, thư mục Maven repository, Gradle cache, compiler hoặc toàn bộ thư mục build.

Ví dụ Linux:

```bash
sudo mkdir -p /opt/runtime-jar-demo
sudo cp target/runtime-jar-demo-1.0.0.jar /opt/runtime-jar-demo/app.jar
sudo chown -R appuser:appuser /opt/runtime-jar-demo
```

Ví dụ Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force ./runtime-jar-demo
Copy-Item ./target/runtime-jar-demo-1.0.0.jar ./runtime-jar-demo/app.jar
```

Tên và đường dẫn chỉ là ví dụ. Dùng thư mục triển khai theo policy của máy đích; tài khoản chạy ứng dụng cần quyền đọc JAR và quyền cần thiết với thư mục log/data.

### 6.1. Runtime machine không cần công cụ JDK

Máy đích chỉ cần lệnh java. Những công cụ sau thuộc JDK và có thể không tồn tại:

- javac: biên dịch source.
- jar: liệt kê/trích archive.
- javap: đọc bytecode/class metadata.
- jdeps: phân tích dependency/module.
- javadoc: tạo tài liệu API.

Nếu javac hoặc jar không tìm thấy trên máy đích, đó không phải lỗi chạy executable JAR. Hãy thực hiện việc kiểm tra archive trên build machine; runtime machine chỉ cần chạy ứng dụng bằng java -jar.

### 6.2. Kiểm tra đúng Java runtime sau khi copy

Linux/macOS:

```bash
java -version
sha256sum /opt/runtime-jar-demo/app.jar
```

Windows PowerShell:

```powershell
java -version
Get-FileHash ./runtime-jar-demo/app.jar -Algorithm SHA256
```

So sánh checksum với build machine. Nếu runtime machine có nhiều Java installation, kiểm tra java đang được tìm thấy qua PATH; trên Windows dùng Get-Command java, trên Linux/macOS dùng command -v java.

## 7. Chạy ứng dụng bằng JRE

### 7.1. Chạy foreground để xem startup log

Linux/macOS:

```bash
cd /opt/runtime-jar-demo
java -jar app.jar --server.port=8080
```

Windows PowerShell:

```powershell
java -jar ./runtime-jar-demo/app.jar --server.port=8080
```

Spring Boot khởi động embedded web server và ghi log ra console. Giữ terminal mở trong lần kiểm tra đầu để xem startup failure, port binding, cấu hình và trạng thái server.

Nếu dùng Java 17 runtime, ứng dụng ví dụ cần chạy mà không yêu cầu javac, Maven hoặc Gradle.

### 7.2. Kiểm tra endpoint

Mở terminal khác trên máy đích.

Linux/macOS:

```bash
curl -fsS http://127.0.0.1:8080/runtime-check
```

Windows PowerShell:

```powershell
(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/runtime-check).Content
```

HTTP body chính xác:

```text
runtime-jar-demo: OK
```

Nếu endpoint trả về nội dung này, request đã tới được ứng dụng đang chạy trên runtime machine. Kết hợp với java -version và checksum để xác nhận đúng runtime và đúng artifact.

### 7.3. Truyền JVM options và Spring Boot arguments

Các JVM options phải đứng trước -jar; các argument của ứng dụng đứng sau tên JAR.

```bash
java -Xms256m -Xmx512m -Dspring.profiles.active=prod \
  -jar app.jar --server.port=8080
```

- -Xms256m: heap ban đầu.
- -Xmx512m: giới hạn heap tối đa.
- -Dspring.profiles.active=prod: system property của JVM.
- --server.port=8080: Spring Boot command-line property.

Giá trị heap chỉ là ví dụ; chọn theo memory limit của máy, container và tải thực tế. Đừng đặt -Xmx cao hơn bộ nhớ khả dụng của môi trường.

### 7.4. Cấu hình bên ngoài JAR

Executable JAR có thể chứa application.properties hoặc application.yml mặc định. Với môi trường triển khai, thông tin thay đổi theo máy như profile, port, URL database và secret nên được truyền qua environment variables, secret manager hoặc file cấu hình ngoài.

Ví dụ:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar app.jar
```

Có thể bổ sung thư mục cấu hình bên ngoài:

```bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:/etc/runtime-jar-demo/
```

Đảm bảo file cấu hình tồn tại, đúng quyền truy cập và không đóng gói secret vào JAR hoặc đưa secret vào log.

## 8. Kiểm chứng trên runtime-only environment

### 8.1. Kiểm tra trên đúng loại máy

Một lượt chạy bằng JDK ở laptop chỉ chứng minh ứng dụng chạy được với runtime đi kèm JDK đó. Để xác nhận yêu cầu “chỉ có JRE”, hãy chạy artifact trên:

- Máy/VM cài runtime-only package tương ứng.
- Hoặc container runtime-only image có cùng Java feature version và architecture.
- Hoặc môi trường staging được cấu hình giống runtime production.

Không cài Maven/Gradle/JDK lên runtime-only host chỉ để chạy thử JAR. Hãy xác nhận java -version, chạy java -jar và kiểm tra endpoint.

### 8.2. Container runtime-only là lựa chọn kiểm tra lặp lại được

Nếu tổ chức dùng Docker, có thể chạy JAR trên một image chỉ cung cấp Java runtime. Ví dụ minh họa với image Java 17 runtime-only đã được tổ chức phê duyệt:

```bash
docker run --rm --name runtime-jar-check \
  -p 8080:8080 \
  -v "$PWD/target/runtime-jar-demo-1.0.0.jar:/app/app.jar:ro" \
  eclipse-temurin:17-jre \
  java -jar /app/app.jar --server.port=8080
```

Sau đó kiểm tra endpoint từ máy host:

```bash
curl -fsS http://127.0.0.1:8080/runtime-check
```

Chọn đúng image tag, digest, OS và architecture theo policy của tổ chức; ví dụ tag chỉ minh họa cách kiểm tra. Một container runtime-only test giúp tái hiện runtime sạch, nhưng không thay thế kiểm tra trên OS/host thật nếu ứng dụng dùng native library, mount, certificate store hoặc tích hợp hệ thống riêng.

### 8.3. Kiểm tra ứng dụng có phụ thuộc tài nguyên ngoài không

Executable JAR không đóng gói các dịch vụ và tài nguyên sau:

- Database, Redis, Kafka, message broker hoặc HTTP service bên ngoài.
- File upload/data directory được mount từ host.
- Certificate, truststore/keystore và secret.
- Native library hoặc executable của hệ điều hành.
- Font, locale data hoặc file cấu hình ngoài nếu ứng dụng cần.

Hãy xác định các phụ thuộc này trong deployment checklist. Nếu ứng dụng khởi động nhưng endpoint nghiệp vụ lỗi do database chưa sẵn sàng, đó là lỗi cấu hình/kết nối runtime, không nhất thiết là lỗi đóng gói JAR.

## 9. Lỗi thường gặp khi chạy trên máy chỉ có JRE

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| java: command not found hoặc java is not recognized | Chưa cài runtime hoặc PATH không trỏ tới runtime | Cài runtime phù hợp, kiểm tra PATH và JAVA_HOME |
| UnsupportedClassVersionError | JRE cũ hơn bytecode của app hoặc dependency | Dùng JRE phù hợp hoặc build theo Java baseline thấp hơn |
| no main manifest attribute | Plain JAR hoặc executable repackage chưa chạy | Build lại bằng Spring Boot plugin, kiểm tra manifest |
| Invalid or corrupt jarfile | File copy thiếu, hỏng hoặc nhầm file | So SHA-256, copy lại artifact |
| ClassNotFoundException | Thiếu class/dependency trên runtime classpath | Kiểm tra đúng executable JAR và nested libraries |
| NoClassDefFoundError | Dependency runtime bị loại, scope provided hoặc exclusion | Kiểm tra dependency graph và BOOT-INF/lib |
| Address already in use | Port đã có tiến trình khác chiếm | Chọn port khác hoặc giải phóng port |
| Connection refused tới database/API | Service chưa chạy hoặc endpoint/firewall sai | Kiểm tra URL, DNS, network, credentials và service health |
| UnsatisfiedLinkError | Native library thiếu hoặc sai OS/architecture | Cài đúng native library và kiểm tra kiến trúc |
| Permission denied | User chạy app không đọc được JAR hoặc không ghi được thư mục cần thiết | Sửa owner/permission đúng phạm vi |
| App khởi động rồi thoát | Lỗi cấu hình, profile, context hoặc dependency runtime | Đọc exception đầu tiên trong startup log |
| Chạy được ở laptop nhưng lỗi trên server | Khác Java vendor/version, OS, architecture, env hoặc config | So sánh runtime properties, checksum và cấu hình triển khai |

### 9.1. Phân tích UnsupportedClassVersionError

Đây là lỗi quan trọng nhất khi triển khai lên runtime cũ.

Ví dụ Java 21 class file có major version 65; Java 17 runtime chỉ hiểu tối đa major version 61. Có hai cách xử lý:

1. Nâng runtime machine lên Java 21 nếu Spring Boot release và policy hỗ trợ.
2. Giữ Java 17 runtime, build application với release 17 và dùng dependency có bytecode/API tương thích Java 17.

Không chỉ kiểm tra class của ứng dụng. Một dependency mới nâng lên Java 21 cũng có thể gây lỗi dù application classes được compile bằng Java 17.

### 9.2. Phân tích no main manifest attribute

Nếu chạy JAR và nhận no main manifest attribute, thường bạn đang chạy plain JAR hoặc artifact chưa được Spring Boot repackage.

Với Maven, xác nhận Spring Boot Maven Plugin được khai báo và goal repackage được thực hiện ở package. Với project dùng spring-boot-starter-parent, execution thường đã được cấu hình sẵn.

Với Gradle, chọn artifact do task bootJar tạo thay vì task jar tạo plain archive. Kiểm tra đúng tên file trong target/ hoặc build/libs/.

### 9.3. Phân tích thiếu dependency

Một executable Boot JAR bình thường chứa dependency runtime trong BOOT-INF/lib/. Nếu thiếu class:

1. Xác định class nào gây ClassNotFoundException hoặc NoClassDefFoundError.
2. Kiểm tra dependency graph bằng Maven dependency:tree hoặc Gradle dependencies.
3. Xem scope/exclusion và packaging configuration.
4. Kiểm tra nested JAR trong executable archive trên build machine.
5. Build lại và kiểm tra artifact mới.

Không giải quyết bằng cách copy ngẫu nhiên các JAR vào máy đích. Làm như vậy dễ tạo version conflict và khiến artifact không còn tái lập.

## 10. Maven và Gradle: các lệnh build tương đương

### 10.1. Maven

| Mục tiêu | Lệnh |
|---|---|
| Kiểm tra môi trường | java -version, mvn -version |
| Chạy tests và đóng gói | mvn clean verify |
| Chỉ tạo package | mvn clean package |
| Xem dependency runtime | mvn dependency:tree -Dscope=runtime |
| Xem plugin repackage | mvn help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin:3.5.16 -Dgoal=repackage -Ddetail |

Nếu không dùng Spring Boot parent, khai báo execution repackage:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.5.16</version>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Goal repackage hoạt động trên JAR/WAR được tạo ở phase package; không gọi riêng goal này trên project chưa tạo source archive. Có thể gọi:

```bash
mvn package spring-boot:repackage
```

### 10.2. Gradle

Ví dụ Groovy DSL trong build.gradle:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Build và kiểm tra:

```bash
./gradlew clean test bootJar
./gradlew tasks --all
```

Executable JAR được tạo bởi task bootJar, thường nằm trong build/libs/. Spring Boot Gradle Plugin tự tạo task này khi Java plugin được áp dụng; assemble và build được cấu hình để phụ thuộc vào bootJar. Xem [Spring Boot Gradle Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html).

Nếu project tạo cả plain JAR và executable Boot JAR, hãy chọn đúng output của bootJar. Không lấy file có classifier plain để chạy như executable archive.

## 11. Checklist phát hành JAR cho máy chỉ có JRE

### 11.1. Trên build machine

- [ ] Đã xác nhận JDK/toolchain theo Java baseline mục tiêu.
- [ ] Đã pin Spring Boot plugin/dependency versions.
- [ ] Đã chạy mvn clean verify hoặc ./gradlew clean test bootJar.
- [ ] Đã xác nhận test pass.
- [ ] Đã tạo đúng executable JAR.
- [ ] Đã kiểm tra manifest và main class.
- [ ] Đã kiểm tra Boot Loader và nested dependencies.
- [ ] Đã kiểm tra các dependency runtime không bị loại ngoài ý muốn.
- [ ] Đã tính SHA-256 và lưu cùng build ID/commit.
- [ ] Đã thử chạy artifact trên runtime-only environment tương ứng.

### 11.2. Trên runtime machine

- [ ] Đã cài runtime Java đúng feature version, vendor policy và architecture.
- [ ] java -version hiển thị runtime dự kiến.
- [ ] SHA-256 của JAR khớp artifact phát hành.
- [ ] Đã copy đúng executable JAR, không phải plain JAR.
- [ ] Đã cấp quyền đọc file và quyền thư mục cần thiết cho service user.
- [ ] Đã cấu hình port, profile, environment variables, secrets và external config.
- [ ] java -jar app.jar khởi động thành công.
- [ ] Endpoint smoke test trả về nội dung mong đợi.
- [ ] Database/API/native dependencies bên ngoài đã được kiểm tra.
- [ ] Log và cách restart/stop service đã được xác định.

### 11.3. Bằng chứng nên lưu theo release

```text
release/
├── runtime-jar-demo-1.0.0.jar
├── runtime-jar-demo-1.0.0.sha256
├── build-info.txt
├── runtime-version.txt
└── deployment-config-example/
```

build-info.txt nên ghi commit SHA, build command, JDK version, Maven/Gradle Wrapper version và Spring Boot version. runtime-version.txt ghi Java vendor, feature version, OS và architecture đã dùng để kiểm chứng.

Không lưu secret hoặc credential trong release evidence. Nếu cần lưu cấu hình mẫu, chỉ giữ giá trị không nhạy cảm và hướng dẫn nơi cung cấp secret khi deploy.

## 12. Kết luận

Để chạy Spring Boot trên máy chỉ có JRE phù hợp, hãy build executable JAR bằng JDK trên build machine, đóng application classes cùng runtime dependencies và Spring Boot Loader vào archive, sau đó chuyển đúng JAR sang runtime machine. Máy đích chỉ cần Java runtime tương thích và các tài nguyên bên ngoài mà ứng dụng sử dụng; không cần Maven, Gradle, source code hay compiler.

Việc kiểm chứng cần đủ ba bằng chứng: **JAR đúng cấu trúc executable**, **runtime version phù hợp**, và **ứng dụng thực sự khởi động/đáp ứng request trên môi trường runtime-only**. Kiểm tra manifest/BOOT-INF trên build machine, so checksum sau khi chuyển file, chạy java -jar trên JRE-only host và smoke test endpoint. Cách làm này xác nhận cả artifact lẫn môi trường triển khai.

### Tài liệu chính thức

- [Spring Boot 3.5.16 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot — Executable JAR](https://docs.spring.io/spring-boot/specification/executable-jar/index.html)
- [Spring Boot Maven Plugin 3.5 — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Spring Boot Gradle Plugin 3.5 — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html)
- [Spring Boot 3.5 — Building Applications](https://docs.spring.io/spring-boot/3.5/how-to/build.html)
- [Oracle Java — The java Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [Oracle Java — JDK Tools and Utilities](https://docs.oracle.com/en/java/javase/17/docs/specs/man/index.html)
