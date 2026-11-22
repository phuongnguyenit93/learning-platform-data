# Lựa chọn JAR thường, JAR thực thi, WAR hoặc image OCI trong Spring Boot

## 1. Cần chọn theo cách ứng dụng được sử dụng và triển khai

Trong Spring Boot, “đóng gói” có hai câu hỏi khác nhau: **bên trong artifact chứa gì** (class, tài nguyên, thư viện, launcher) và **môi trường nào sẽ chạy artifact đó** (classpath Java, JVM độc lập, servlet container bên ngoài, hay container runtime). Đuôi `.jar` hoặc `.war` không đủ để kết luận artifact có thể tự chạy. OCI image cũng không đơn thuần là một loại JAR khác: image thường **chứa** ứng dụng Java đã đóng gói cùng Java runtime và các thành phần hệ điều hành cần thiết.

Bốn lựa chọn cần phân biệt:

1. **JAR thường (plain/regular JAR):** chủ yếu chứa class và resource của module; các dependency thường phải được cung cấp riêng. Phù hợp khi module được **module khác dùng làm thư viện** hoặc khi hệ thống chủ động quản lý classpath.
2. **JAR thực thi (Spring Boot executable JAR):** chứa class/resource, dependency lồng bên trong và Spring Boot launcher; thích hợp chạy dịch vụ độc lập bằng `java -jar` trên JVM.
3. **WAR:** phục vụ mô hình **triển khai ứng dụng web lên servlet container** như Tomcat bên ngoài. WAR do Spring Boot plugin tạo có thể đồng thời là **executable WAR** chạy bằng `java -jar` nếu cấu hình phù hợp.
4. **OCI image:** đơn vị triển khai theo chuẩn container image; phù hợp Docker, Kubernetes và nền tảng container. Có thể được tạo từ executable JAR/WAR bằng Cloud Native Buildpacks hoặc Dockerfile.

| Tiêu chí | JAR thường | Spring Boot executable JAR | WAR triển khai được | OCI image |
| --- | --- | --- | --- | --- |
| Mục đích chính | Phân phối thư viện/class | Chạy ứng dụng độc lập | Chạy web app trong servlet container | Phân phối và chạy ứng dụng dạng container |
| Có dependency đi kèm? | Thông thường không | Có, thường trong `BOOT-INF/lib` | Có trong `WEB-INF/lib`; dependency container dạng provided được tách riêng khi Boot repackage | Có các lớp runtime/dependency/app theo cách dựng image |
| Cách chạy thường gặp | Module khác thêm làm dependency hoặc tự dựng classpath | `java -jar app.jar` | Deploy lên Tomcat tương thích; executable WAR còn có thể `java -jar app.war` | `docker run ... image:tag` hoặc Kubernetes |
| Cần gì ở môi trường đích? | JVM, dependency và cơ chế khởi chạy | JVM tương thích | Servlet container/JVM tương thích; hoặc JVM nếu WAR thực thi | Container runtime/nền tảng OCI; Java runtime thường đã ở trong image |
| Khi nên chọn | Shared library, SDK, module dùng lại | Dịch vụ độc lập, VM, hệ thống chạy JAR | Hạ tầng bắt buộc quản lý WAR trên app server | Hệ thống CI/CD, orchestration, container platform |
| Điều dễ nhầm | Có đuôi `.jar` không có nghĩa là `java -jar` được | Không nên dùng làm thư viện thông thường | WAR không mặc nhiên thích hợp với mọi Spring app | Image có thể chứa JAR/WAR; hai khái niệm không loại trừ nhau |

## 2. Bên trong từng gói có gì?

### 2.1. JAR thường

JAR là một ZIP archive có cấu trúc Java chuẩn, thường gồm các `.class`, resource và thư mục `META-INF/`. Ví dụ:

```text
com/example/library/Formatter.class
application.properties
META-INF/MANIFEST.MF
```

Một JAR thường **không tự mang toàn bộ dependency**. Nếu dùng nó như thư viện, Maven/Gradle sẽ giải quyết dependency từ metadata khi project khác khai báo dependency. Nếu muốn chạy trực tiếp, phải có lớp `main`, manifest/classpath phù hợp và mọi dependency lúc runtime. Không nên coi việc có một phương thức `main` là đủ để bảo đảm `java -jar` hoạt động.

**Chọn JAR thường khi** đang xây dựng module domain, utility, SDK hoặc API dùng lại giữa các ứng dụng. Nếu lấy executable Boot JAR làm dependency, class ứng dụng được đặt dưới `BOOT-INF/classes` nên consumer thông thường không tìm thấy theo bố cục classpath JAR chuẩn. Với module thư viện, giữ plain JAR là artifact chính; nếu cũng cần chạy ứng dụng, tạo thêm executable JAR có classifier riêng.

### 2.2. Spring Boot executable JAR

Spring Boot Maven `repackage` hoặc Gradle `bootJar` biến artifact ứng dụng thành gói thực thi. Bố cục điển hình:

```text
META-INF/MANIFEST.MF
org/springframework/boot/loader/...
BOOT-INF/classes/com/example/packaging/PackagingApplication.class
BOOT-INF/classes/application.properties
BOOT-INF/lib/<dependency-1>.jar
BOOT-INF/lib/<dependency-2>.jar
```

Launcher của Spring Boot thiết lập classpath cho thư viện lồng trong `BOOT-INF/lib` rồi khởi chạy class ứng dụng. Manifest do plugin quản lý: `Main-Class` thường hướng tới launcher, còn `Start-Class` là class ứng dụng. Không nên tự sửa `Main-Class` trong Maven JAR plugin rồi hy vọng nó thay thế được cơ chế `repackage`.

Với ứng dụng Spring MVC dùng embedded servlet server, executable JAR thường khởi động cả HTTP server trong cùng tiến trình JVM; ta có thể chạy `java -jar app.jar --server.port=9090`. Đây là lựa chọn mặc định hợp lý cho một service Spring Boot chạy trực tiếp trên máy chủ hoặc VM.

**Giới hạn:** image/JVM nơi chạy vẫn cần Java runtime tương thích; JAR cũng không tự cung cấp cấu hình môi trường, secret, database hay hệ thống log/giám sát.

### 2.3. WAR và executable WAR

WAR là định dạng cho web application trên nền servlet. Bố cục tiêu biểu:

```text
WEB-INF/classes/com/example/packaging/PackagingApplication.class
WEB-INF/lib/<application-dependency>.jar
WEB-INF/lib-provided/<embedded-container-dependency>.jar
META-INF/MANIFEST.MF
```

`WEB-INF/lib-provided` là đặc điểm của **executable WAR được Spring Boot repackaged** khi dependency servlet container được đánh dấu `provided`. Servlet container bên ngoài cung cấp thư viện container khi deploy WAR; launcher của Spring Boot vẫn có thể dùng các thư viện `lib-provided` khi chạy `java -jar`. WAR thông thường do công cụ Java tạo chưa chắc là executable WAR.

Để deploy từ Spring Boot MVC lên servlet container bên ngoài, ứng dụng thường cần:
- đóng gói `war`, có `SpringBootServletInitializer` và override `configure`;
- đánh dấu embedded servlet container là `provided` / `providedRuntime`;
- bảo đảm container hỗ trợ đúng phiên bản Jakarta Servlet, Java và Spring Boot đang dùng;
- kiểm tra context path của WAR trên máy chủ ứng dụng.

WAR truyền thống **không phải lựa chọn cho ứng dụng Spring WebFlux dùng Reactor Netty** theo mô hình mặc định. Chỉ chọn WAR nếu nền tảng triển khai thật sự yêu cầu servlet container bên ngoài, hoặc có ràng buộc tích hợp/hạ tầng cụ thể.

### 2.4. OCI image

OCI image là tập các layer và manifest theo chuẩn container. Một image ứng dụng Spring Boot thường gồm runtime Java, thành phần Linux tối thiểu và mã ứng dụng/dependency. Khi chạy, container runtime tạo container từ image; ứng dụng thường vẫn là JVM process khởi chạy mã trong executable JAR/WAR.

Có hai đường phổ biến:
- **Cloud Native Buildpacks:** `mvn spring-boot:build-image` hoặc `gradle bootBuildImage`; không cần tự viết Dockerfile, chọn builder/runtime image và tổ chức layer.
- **Dockerfile:** tự quyết định base image, cách sao chép JAR, entrypoint, user và filesystem.

OCI image thuận tiện cho registry, triển khai theo digest, Kubernetes và nhất quán môi trường. Tuy nhiên image phải được cập nhật khi Java/base image có bản vá; cần quản lý kiến trúc CPU, registry, quyền, scan lỗ hổng và tài nguyên container. OCI **không thay thế** quyết định module nên là plain JAR hay executable app.

## 3. Ví dụ chạy được với Spring Boot và Java 17

Ví dụ dưới đây **cố định Spring Boot 3.5.0** để dependency và lệnh minh họa nhất quán. Đây là phiên bản ví dụ, không phải khẳng định phiên bản mới nhất. Spring Boot 4.x có thay đổi trong một số starter/runtime artifact; khi nâng cấp phải đối chiếu tài liệu đúng nhánh. Cần JDK 17+, Maven và mạng để tải dependency. Đặt hai file Java như sau.

**`src/main/java/com/example/packaging/PackagingApplication.java`:**

```java
package com.example.packaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PackagingApplication {
    public static void main(String[] args) {
        SpringApplication.run(PackagingApplication.class, args);
    }
}
```

**`src/main/java/com/example/packaging/HelloController.java`:**

```java
package com.example.packaging;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/hello")
    public String hello() {
        return "Hello from Spring Boot";
    }
}
```

**`pom.xml` tối thiểu để tạo executable JAR:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>packaging-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

Vì project kế thừa `spring-boot-starter-parent` và đã khai báo Boot Maven plugin, goal `repackage` được cấu hình trong lifecycle. Chạy ở thư mục có `pom.xml`:

```bash
mvn clean package
java -jar target/packaging-demo-0.0.1-SNAPSHOT.jar
```

Mở terminal khác để kiểm tra:

```bash
curl -fsS http://localhost:8080/hello
```

**Response body đúng:** `Hello from Spring Boot` (curl có thể không tự xuống dòng). Server dùng port 8080 nếu không có cấu hình ghi đè và cổng chưa bị chiếm. Dừng tiến trình bằng Ctrl+C. Nếu dùng Maven Wrapper, thay `mvn` bằng `./mvnw` (Windows: `mvnw.cmd`).

Có thể xem cấu trúc archive bằng `jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar`; đây là lệnh liệt kê mục của JAR, không chạy ứng dụng.

## 4. Tạo từng dạng bằng Maven

### 4.1. Muốn plain JAR

Với ví dụ trên, có thể tạm bỏ bước Spring Boot repackage cho lần build:

```bash
mvn clean package -Dspring-boot.repackage.skip=true
jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar
```

JAR tạo ra là artifact Java thông thường, thiếu các dependency runtime lồng bên trong và không có Boot launcher. Không dùng `java -jar` như cách triển khai service ở mục 3; plain JAR phù hợp để publish làm thư viện hoặc làm đầu vào một quy trình có classpath riêng. Trong một project library thực sự, thường không cần khai báo Spring Boot Maven plugin.

**Nếu cần đồng thời plain JAR và executable JAR:** giữ `pom.xml` ở mục 3 nhưng cấu hình classifier `exec` cho execution `repackage`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <id>repackage</id>
                    <configuration>
                        <classifier>exec</classifier>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Đoạn `<build>` này **thay thế** khối `<build>` trong POM mẫu, không dán thành khối thứ hai. Sau `mvn clean package`, Maven tạo plain `target/packaging-demo-0.0.1-SNAPSHOT.jar` và bản chạy được `target/packaging-demo-0.0.1-SNAPSHOT-exec.jar`. Trong dự án có parent khác, phải bảo đảm goal `repackage` thực sự được bind vào phase `package`.

### 4.2. Muốn executable JAR

Dùng POM mục 3 và chạy `mvn clean package`. Nếu project không dùng `spring-boot-starter-parent`, cần cấu hình execution của `spring-boot-maven-plugin` với goal `repackage` cho lifecycle. Khi gọi thủ công, phải có JAR nguồn tạo từ `package` trước:

```bash
mvn package spring-boot:repackage
```

Không chạy riêng `mvn spring-boot:repackage` rồi kỳ vọng plugin tự biên dịch/package project từ đầu. Plugin có thể lưu JAR nguồn dưới tên đuôi `.original` khi thay thế main artifact (nếu không dùng classifier).

### 4.3. Muốn WAR deploy lên servlet container

Đối với **Spring MVC** trong POM mẫu, thay `<packaging>jar</packaging>` (mặc định) bằng `<packaging>war</packaging>` ngay dưới khai báo phiên bản, và thêm dependency servlet container với `provided`:

```xml
<packaging>war</packaging>
<!-- Thêm vào phần <dependencies> hiện có: -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
```

Sửa file `PackagingApplication.java` thành:

```java
package com.example.packaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class PackagingApplication extends SpringBootServletInitializer {
    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder builder) {
        return builder.sources(PackagingApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(PackagingApplication.class, args);
    }
}
```

Giữ nguyên `HelloController.java` và plugin Maven, sau đó:

```bash
mvn clean package
java -jar target/packaging-demo-0.0.1-SNAPSHOT.war
```

Với Spring Boot Maven plugin, đây là executable WAR. Đồng thời, artifact `.war` có thể deploy lên một Tomcat **tương thích** với phiên bản Spring Boot/Jakarta Servlet đang dùng. URL trên Tomcat bên ngoài thường phụ thuộc vào tên/context của WAR; chẳng hạn có thể có tiền tố `/packaging-demo-0.0.1-SNAPSHOT`, còn khi chạy standalone bằng `java -jar` thì endpoint mẫu là `/hello`.

**Quan trọng:** `provided` dành cho dependency container, không đánh dấu mọi dependency của ứng dụng thành provided. Kiểm tra classloader/version, Jakarta `jakarta.*` (Spring Boot 3+), cấu hình context path và tài nguyên mà server bên ngoài cung cấp. Đừng deploy WAR Spring Boot 3/4 lên servlet container đời cũ chỉ hỗ trợ namespace `javax.*`.

### 4.4. Muốn OCI image từ project Maven

Với ứng dụng JAR ở mục 3 và Docker daemon đã sẵn sàng:

```bash
mvn spring-boot:build-image -Dspring-boot.build-image.imageName=packaging-demo:0.0.1
docker run --rm -p 8080:8080 packaging-demo:0.0.1
```

Mở terminal khác và chạy `curl -fsS http://localhost:8080/hello`; response body là `Hello from Spring Boot`. Plugin sử dụng Cloud Native Buildpacks và có thể tự bảo đảm archive phù hợp trước khi tạo image. Docker daemon cần hoạt động; image builder/runtime có thể phải tải qua mạng. Lệnh này tạo image trong môi trường container local, **chưa tự push lên registry**. Việc đặt tên/tag cần thống nhất với quy tắc của đội triển khai.

## 5. Tương đương trong Gradle

Với Gradle có Java plugin và Spring Boot Gradle plugin:

| Mục tiêu | Task |
| --- | --- |
| Plain JAR | `./gradlew jar` (thường mang classifier `plain` khi Boot plugin bật) |
| Executable JAR | `./gradlew bootJar` |
| Plain WAR | `./gradlew war` (khi áp dụng plugin `war`) |
| Executable WAR | `./gradlew bootWar` (khi áp dụng plugin `war`) |
| OCI image bằng Buildpacks | `./gradlew bootBuildImage --imageName=packaging-demo:0.0.1` |

Ví dụ `build.gradle` (Groovy DSL) dùng Java code ở mục 3:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
}
```

Chạy `./gradlew clean bootJar jar` sẽ cho cả executable và plain JAR trong `build/libs/` (tên thực tế theo project/version/classifier). Để chuyển sang WAR, thêm `id 'war'` vào block `plugins`, thêm `providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'` vào block `dependencies`, áp dụng lớp `SpringBootServletInitializer` như mục 4.3 rồi chạy `./gradlew clean bootWar`. Ví dụ `providedRuntime` này dùng dependency Boot 3.5.x; với Spring Boot 4.x, đối chiếu artifact container runtime của nhánh đang dùng.

`./gradlew bootBuildImage --imageName=packaging-demo:0.0.1` tạo OCI image với Buildpacks và yêu cầu kết nối Docker daemon (hoặc runtime tương thích được cấu hình). Trên Windows, sử dụng `gradlew.bat`; nếu chưa có Gradle Wrapper thì cần tạo wrapper hoặc dùng `gradle` tương ứng.

**Phân biệt:** `bootJar`/`bootWar` là task của Spring Boot plugin, còn `jar`/`war` là task đóng gói Java/War thông thường. Tên `*-plain.jar` chỉ là convention thường gặp; đừng suy đoán loại artifact chỉ từ tên, hãy kiểm tra nội dung và cấu hình task.

## 6. OCI image bằng Dockerfile: khi nào cần kiểm soát thêm?

Nếu cần image tùy biến đặc biệt, sau khi tạo executable JAR có thể dùng Dockerfile tối giản:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/packaging-demo-0.0.1-SNAPSHOT.jar app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

```bash
mvn clean package
docker build -t packaging-demo:dockerfile .
docker run --rm -p 8080:8080 packaging-demo:dockerfile
```

Đây là ví dụ **Dockerfile cho JAR đã build**, không phải Dockerfile tự biên dịch Java. `EXPOSE 8080` chỉ khai báo metadata, còn `-p 8080:8080` mới publish port từ container ra máy host. Trong môi trường production, cần pin base image/digest, kiểm tra bản vá và tương thích CPU, tạo user không đặc quyền, quản lý cấu hình/secret ở runtime, quét vulnerability và cân nhắc layer để tận dụng cache. Cloud Native Buildpacks thường giúp giảm công sức duy trì Dockerfile, nhưng không loại bỏ trách nhiệm cập nhật image và kiểm tra bảo mật.

## 7. Quy tắc chọn theo tình huống

- **Module `billing-core` được ba ứng dụng khác import:** publish **plain JAR** làm dependency. Không chuyển nó thành executable Boot JAR làm artifact thư viện chính.
- **API `order-service` chạy trên VM với systemd, không có yêu cầu Docker:** dùng **executable JAR** và Java runtime phù hợp; triển khai thành một process có health check, log và restart policy.
- **Doanh nghiệp có Tomcat được vận hành tập trung, bắt buộc deploy WAR:** dùng **WAR**, `SpringBootServletInitializer` và dependency servlet container `provided`; kiểm tra mức tương thích servlet/JDK trước khi triển khai.
- **Service chạy trên Kubernetes:** ưu tiên **OCI image**; bên trong thường là executable JAR, build bằng Buildpacks hoặc Dockerfile; tag và digest được quản lý trong CI/CD.
- **Cùng service chạy cả standalone lẫn Tomcat ngoài:** **executable WAR** là lựa chọn có thể đáp ứng cả hai chế độ, nhưng phải kiểm tra hai đường khởi động riêng; không mặc nhiên chọn nếu không thật sự cần deployment kiểu WAR.
- **Có cả thư viện dùng lại và service chạy trực tiếp:** tách module thư viện và module ứng dụng, hoặc xuất cả plain JAR và executable JAR với **classifier khác nhau**; tránh để artifact thư viện trỏ nhầm vào bản Boot repackaged.

Một sơ đồ quyết định đơn giản:

```text
Artifact được project khác import như thư viện?
  Có  -> plain JAR (hoặc module library riêng).
  Không ->
    Nền tảng bắt buộc servlet container bên ngoài?
      Có  -> WAR deployable; cân nhắc executable WAR nếu cần chạy standalone.
      Không ->
        Nền tảng triển khai bằng Docker/Kubernetes?
          Có  -> OCI image, thường được build từ executable JAR.
          Không -> executable JAR chạy bằng java -jar.
```

Đừng chọn WAR chỉ vì ứng dụng có HTTP API; embedded Tomcat trong executable JAR đã phục vụ HTTP. Cũng đừng gọi OCI image là “JAR mới”: image và JAR giải quyết hai cấp đóng gói khác nhau.

## 8. Kiểm tra trước khi phát hành và lỗi thường gặp

### Checklist xác minh

1. **Loại artifact:** kiểm tra lệnh Maven/Gradle, `pom.xml`/`build.gradle` và nội dung `jar tf` hoặc `unzip -l`. Với Boot JAR, mong đợi `BOOT-INF/classes`, `BOOT-INF/lib` và launcher; với WAR xem `WEB-INF`.
2. **Thực thi:** kiểm thử đúng cơ chế triển khai thực tế: plain JAR như dependency của module khác; executable JAR bằng `java -jar`; WAR trên app server; OCI image trong container.
3. **Chạy thật:** gọi `/hello` hoặc một endpoint nghiệp vụ, kiểm tra exit code, log và HTTP status. Chỉ xem task `BUILD SUCCESS` chưa đủ.
4. **Tương thích:** kiểm tra phiên bản Java lúc build/lúc chạy, Spring Boot, servlet container, architecture image và dependency runtime.
5. **Sẵn sàng triển khai:** externalize cấu hình/secret, công bố port, có health/readiness check phù hợp, giới hạn RAM/CPU, log stdout/stderr, vulnerability scan và kế hoạch cập nhật base image.
6. **Khả năng tái lập:** khóa dependency/plugin, tạo version/tag rõ ràng, trong môi trường container ưu tiên deploy theo image digest đã kiểm chứng thay vì chỉ dựa vào `latest`.

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra/sửa |
| --- | --- | --- |
| `no main manifest attribute` khi `java -jar` | Đang chạy plain JAR hoặc build chưa repackage | Dùng `bootJar`/`spring-boot:repackage`; xem manifest và bố cục JAR |
| `ClassNotFoundException` / `NoClassDefFoundError` | Thiếu dependency hoặc dùng Boot repackaged JAR làm thư viện theo classpath thường | Kiểm tra `BOOT-INF/lib`, dependency tree và đúng artifact/classifier |
| `UnsupportedClassVersionError` | Java runtime cũ hơn bytecode được biên dịch | Xem `java -version` và toolchain/`java.version`; nâng runtime hoặc build về target hỗ trợ |
| WAR không khởi động trên Tomcat ngoài | Thiếu initializer, sai `provided` hoặc servlet/Jakarta/Java không tương thích | Kiểm tra `SpringBootServletInitializer`, deployment logs và versions |
| WAR deploy thành công nhưng `/hello` trả 404 | Context path của WAR khác dự kiến hoặc mapping chưa được đăng ký | Kiểm tra tên/context của WAR và log mapping; thử đúng URL |
| `bootBuildImage`/`build-image` không kết nối được Docker | Docker daemon/context chưa hoạt động hoặc không thể truy cập | Kiểm tra `docker info`, Docker context và cấu hình plugin |
| Image chạy nhưng không truy cập được HTTP | Chưa publish port, ứng dụng nghe port khác, bind address hoặc probe sai | Kiểm tra `docker logs`, cấu hình `server.port` và `docker run -p` |
| Container thoát vì thiếu RAM | Memory limit quá thấp so với JVM/ứng dụng | Kiểm tra exit code, container logs, JVM memory settings và giới hạn runtime |

**Không nhầm “đóng gói thành công” với “triển khai thành công”.** Việc package chỉ chứng minh có artifact; chỉ bài test ở môi trường gần production mới xác nhận đủ Java runtime, dependency, cổng, cấu hình và khả năng khởi động.

## 9. Tài liệu chính thức để đối chiếu theo phiên bản

- Spring Boot Maven Plugin – [Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html).
- Spring Boot Gradle Plugin – [Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html).
- Spring Boot – [Traditional Deployment](https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html).
- Spring Boot Maven Plugin – [Packaging OCI Images](https://docs.spring.io/spring-boot/maven-plugin/build-image.html).
- Spring Boot Gradle Plugin – [Packaging OCI Images](https://docs.spring.io/spring-boot/gradle-plugin/packaging-oci-image.html).

**Nguyên tắc thực hành:** module để import → plain JAR; ứng dụng JVM chạy trực tiếp → executable JAR; môi trường quản lý servlet container → deployable WAR; nền tảng container → OCI image (thường đóng gói executable JAR bên trong).