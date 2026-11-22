# Chọn phiên bản Spring Boot, Spring Security và bộ phụ thuộc tương thích

> Phạm vi: **khởi tạo ứng dụng Spring Security trên WebFlux (reactive)**. Ví dụ phiên bản được đối chiếu với tài liệu chính thức ngày **07/11/2026**. Các bản vá có thể thay đổi sau thời điểm này; khi xây mới hoặc nâng cấp hãy tra lại danh sách phiên bản còn được hỗ trợ.

## 1. Tại sao phải chọn phiên bản như một bộ?

Một ứng dụng reactive bảo mật không chỉ gồm hai thư viện độc lập. Nó là tập hợp những tầng phải tương thích với nhau:

~~~text
Java (JDK/JVM chạy ứng dụng)
       |
Maven/Gradle + Spring Boot parent/BOM
       |
       +-- Spring Boot: auto-configuration, starters, đóng gói, chạy app
       +-- Spring Framework: Spring WebFlux, web/reactive APIs
       +-- Spring Security: xác thực, phân quyền reactive
       +-- Reactor / Reactor Netty: Mono, Flux, HTTP server bất đồng bộ
       +-- Thư viện liên quan: test, codec, JWT/OAuth2, database driver...
~~~

Các khái niệm thiết yếu:

- **Spring Boot** quản lý cách khởi tạo, cấu hình, đóng gói ứng dụng và cung cấp danh sách dependency đã được kiểm tra cùng nhau.
- **Spring Framework** cung cấp WebFlux; mỗi nhánh Spring Boot gắn với một nhánh Spring Framework tương thích.
- **Spring Security** cung cấp các API reactive như `SecurityWebFilterChain`, `ServerHttpSecurity` và `ReactiveSecurityContextHolder`. Spring Security cũng có API Servlet/MVC; phải chọn đúng stack.
- **Reactor** là thư viện Publisher phía dưới `Mono` và `Flux`; WebFlux và Security reactive cùng vận hành trên cơ chế này.
- **BOM (Bill of Materials)** là bảng ánh xạ nhóm/thư viện sang phiên bản. `spring-boot-dependencies` quản lý phần lớn thư viện Spring và nhiều thư viện bên thứ ba.

**Nguyên tắc mặc định:** trước tiên chọn **một phiên bản Spring Boot ổn định**, sau đó để `spring-boot-starter-parent` hoặc BOM Spring Boot quyết định phiên bản Spring Framework, Spring Security, Reactor và những dependency thuộc phạm vi nó quản lý. Không tự ghép bản mới nhất của từng thư viện như các mảnh độc lập.

## 2. Ma trận phiên bản minh họa tại 07/11/2026

| Bộ phiên bản nhất quán | Spring Boot | Spring Framework do Boot quản lý | Spring Security do Boot quản lý | Java tối thiểu | Khi nào cân nhắc |
| --- | --- | --- | --- | --- | --- |
| Nhánh mới | **4.1.2** | **7.0.10** | **7.1.2** | **17** | Dự án mới có thể tiếp nhận Spring Framework 7, Security 7 và hệ sinh thái tương ứng |
| Nhánh 3.x | **3.5.16** | **6.2.19** | **6.5.11** | **17** | Dự án đang theo Boot 3.x hoặc dependency chưa tương thích Boot 4 |

Những số này đến từ tài liệu `System Requirements` và `Managed Dependency Coordinates` của từng nhánh Spring Boot, không phải phép ước lượng “cùng số major là đủ”. Đặc biệt, **không suy ra Boot 4.1.2 phải dùng Spring Security 4.1.2**. Spring Boot 4.1.2 quản lý Spring Security **7.1.2**.

Lưu ý thêm:

- Tài liệu Boot **4.1.2** công bố hỗ trợ xây dựng với Maven **3.6.3+** hoặc Gradle **8.14+ thuộc nhánh 8.x / nhánh 9.x**; Java tối thiểu 17. Chọn một JDK LTS phù hợp hệ thống và kiểm tra version JVM của CI/production, không chỉ trên máy cá nhân.
- Tài liệu Boot **3.5.16** công bố Maven **3.6.3+**, Gradle **7.6.4+ thuộc nhánh 7.x / 8.4+ thuộc nhánh 8.x**; Java tối thiểu 17. Không mặc định một Gradle wrapper quá cũ vẫn chạy được sau khi đổi Boot major.
- Nhánh **4.0.x** cũng thuộc thế hệ Spring Framework 7 / Security 7; nên xem là lựa chọn cần đánh giá riêng, không thay số version trong project 3.x mà bỏ qua migration.
- “Ổn định” không đồng nghĩa “mãi mãi còn support”. Xem chính sách hỗ trợ và thông báo bảo mật của Spring trước khi chốt phiên bản cho ứng dụng có vòng đời dài.
- Không chọn bản `M` (milestone), `RC` (release candidate) hoặc `SNAPSHOT` cho production thông thường trừ khi đã chấp nhận rủi ro và có quy trình kiểm thử riêng.

**Quy tắc ra quyết định:** nếu bắt đầu một service reactive mới và các thư viện liên quan đều hỗ trợ Boot 4.1, dùng bộ 4.1.x hiện hành; nếu đang vận hành Boot 3.5 với dependency chưa sẵn sàng cho Framework 7 hoặc Security 7, tiếp tục dùng bản vá mới phù hợp của nhánh 3.5 trong thời gian chuẩn bị migration. Không ép nâng major chỉ để có số phiên bản lớn hơn.

## 3. Quy trình chọn phiên bản có thể lặp lại

### Bước 1 — Ghi lại ràng buộc thực tế

Trả lời những câu hỏi này trước khi chọn version:

1. Chương trình chạy bằng **Java 17, 21, 25 hay một runtime khác**? JDK chạy build và JVM production có khớp không?
2. Dự án **WebFlux reactive thuần** hay **Spring MVC/Servlet**? Nếu có đồng thời starter MVC và WebFlux, cần xác nhận stack được Boot kích hoạt thực tế.
3. Tính năng security nào cần dùng: session, HTTP Basic, JWT resource server, OAuth2 client/OIDC, SAML, method security?
4. Có phụ thuộc Spring Cloud, Spring Data, database driver, Spring Authorization Server hoặc thư viện thứ ba chưa hỗ trợ Boot/Security major mới không?
5. Có yêu cầu vòng đời hỗ trợ, security patch, hình thức triển khai container/native image, hoặc Gradle/Maven version bắt buộc không?

Một ràng buộc không đáp ứng được có thể làm cả bộ lựa chọn không phù hợp, dù riêng `spring-boot-starter-security` vẫn tải được từ Maven Central.

### Bước 2 — Xác minh nhánh Spring Boot

Đọc `System Requirements` của đúng nhánh, kiểm tra Java, Maven/Gradle, Spring Framework và thông tin hỗ trợ. Đừng dùng trang `latest` để kết luận về ràng buộc của project đang khóa ở 3.5.x.

### Bước 3 — Tra BOM để biết các phiên bản thực tế

Mở `Managed Dependency Coordinates` của **đúng phiên bản Boot**. Tìm `spring-security-core`, `spring-security-web`, `spring-webflux`, `reactor-core` và những module khác mà project dùng. Nếu library nằm trong BOM, **khai báo dependency không kèm `<version>`** (Maven) hoặc dùng cơ chế platform/dependency management (Gradle).

### Bước 4 — Kiểm tra hệ sinh thái mở rộng

Ví dụ, nếu dùng Spring Cloud Gateway, Spring Cloud Config hoặc Spring Cloud Stream, phải tìm **release train Spring Cloud được công bố tương thích với nhánh Boot** đang chọn. BOM Spring Boot không tự xác nhận mọi starter bên thứ ba tương thích. Làm tương tự với driver R2DBC, công cụ test, plugin build và các thư viện OAuth2/JWT tích hợp.

### Bước 5 — Chạy build và kiểm thử bảo mật

Đọc dependency tree đã resolve, chạy compile/test, khởi động web server và thử ít nhất request không có credentials, credentials hợp lệ và trường hợp không đủ quyền. **Maven tải được JAR chưa chứng minh API tương thích ở runtime**.

## 4. Chọn dependency nào cho Spring Security reactive?

Với ứng dụng HTTP WebFlux, hai starter bắt buộc thường là:

| Nhu cầu | Spring Boot starter phù hợp | Lý do |
| --- | --- | --- |
| Reactive HTTP server | `org.springframework.boot:spring-boot-starter-webflux` | WebFlux, Reactor và mặc định Reactor Netty |
| Authentication/authorization | `org.springframework.boot:spring-boot-starter-security` | Spring Security và cấu hình bảo mật của Boot |
| WebFlux test trên Boot 4.1 | `org.springframework.boot:spring-boot-starter-webflux-test` (scope `test`) | Hạ tầng test WebFlux |
| Security test trên Boot 4.1 | `org.springframework.boot:spring-boot-starter-security-test` (scope `test`) | Công cụ kiểm thử bảo mật |
| JWT/OAuth2 resource server trên Boot 4 | `org.springframework.boot:spring-boot-starter-security-oauth2-resource-server` | Kiểm tra access token theo cấu hình resource server |
| Gọi HTTP reactive ra bên ngoài trên Boot 4 | `org.springframework.boot:spring-boot-starter-webclient` | API `WebClient`, khi ứng dụng cần riêng HTTP client |

Chỉ thêm các starter tùy chọn nếu có nhu cầu thật. Một `spring-boot-starter-webflux` thường đã kéo theo `spring-webflux`, Reactor và Reactor Netty; không cần thêm `reactor-core` hoặc `spring-security-web` bằng một version thủ công chỉ để làm ví dụ hoạt động.

**Khác biệt nhánh test:** với Boot **3.5**, cách thiết lập phổ biến là `spring-boot-starter-test` và `org.springframework.security:spring-security-test`, cùng scope `test`. Boot **4.x** tổ chức starter theo module chi tiết hơn, gồm những starter `*-test` tương ứng. Khi đổi từ 3.5 sang 4.x, kiểm tra lại tên starter và đường dẫn package test thay vì chỉ đổi số trong build file.

**Cẩn thận khi thêm web stack:** `spring-boot-starter-web` (Boot 3.x) hoặc `spring-boot-starter-webmvc` (Boot 4.x) là Servlet MVC. Đối với bài thực hành reactive WebFlux, chỉ thêm khi chủ ý thiết kế kết hợp và đã hiểu quy tắc chọn web application type; không đưa vào do sao chép dependency từ mẫu MVC.

## 5. Maven: ví dụ project Boot 4.1.2 có thể chạy

Dùng [Spring Initializr](https://start.spring.io/) với Maven, Java 17+, group `com.example`, artifact `reactive-versions`, chọn **Spring Reactive Web** và **Spring Security**. File `pom.xml` hoàn chỉnh tối giản sau minh họa cách để parent Boot quản lý version:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-versions</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>reactive-versions</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-test</artifactId>
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
~~~

Lưu ý **chỉ parent có version 4.1.2**; bốn starter không có tag `<version>`. Parent Boot cung cấp dependency management và quản lý nhiều plugin Maven liên quan. Khi nâng Boot 4.1.x lên bản vá tiếp theo, thông thường cập nhật `<parent><version>...` và chạy lại QA thay vì thay từng dependency con.

Tạo file `src/main/java/com/example/reactiveversions/ReactiveVersionsApplication.java`:

~~~java
package com.example.reactiveversions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveVersionsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveVersionsApplication.class, args);
    }

    @RestController
    static class PingController {
        @GetMapping("/ping")
        public Mono<String> ping() {
            return Mono.just("pong");
        }
    }
}
~~~

Đây là **lớp Java đầy đủ** cho cấu trúc thư mục và `package` ở trên, không cần tự thêm code Security để bật chính sách mặc định. Spring Boot tự cấu hình bảo vệ các endpoint WebFlux khi có `spring-boot-starter-security`; cấu hình mặc định dành để phát triển, cần thay bằng chính sách của ứng dụng trước khi đưa vào production.

Ở thư mục chứa `pom.xml`, nếu có Maven wrapper do Spring Initializr tạo:

~~~bash
./mvnw clean verify
./mvnw spring-boot:run
~~~

Trên Windows dùng `.\mvnw.cmd clean verify` và `.\mvnw.cmd spring-boot:run`. Chạy lệnh sau ở terminal khác:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/ping
~~~

**Kết quả mong đợi:** HTTP **401 Unauthorized** khi chưa gửi thông tin đăng nhập. Cấu hình mặc định có user `user` và mật khẩu ngẫu nhiên được Spring Boot ghi trong startup log ở môi trường phát triển. Dùng đúng mật khẩu sinh ra để thử lại và nhận body `pong`; không ghi mật khẩu này vào repository và không dùng cơ chế mặc định cho production. Các header và nội dung body của phản hồi 401 có thể khác nhau theo phiên bản/cấu hình.

Ví dụ cho thấy **build dependency và web security mặc định hoạt động cùng nhau**; nó chưa phải cấu hình xác thực/phân quyền production, và không kiểm chứng mọi tùy chọn OAuth2 hay database driver.

## 6. Nếu dùng Gradle Kotlin DSL

Khi không dùng Maven, hãy để Boot plugin và BOM Gradle cùng ở nhánh 4.1.2. Đây là một ví dụ `build.gradle.kts` dùng **Gradle native platform** thay cho plugin dependency-management:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "4.1.2"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(
        platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    )
    testImplementation(
        platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    )

    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")

    testImplementation("org.springframework.boot:spring-boot-starter-webflux-test")
    testImplementation("org.springframework.boot:spring-boot-starter-security-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Giữ cùng file `ReactiveVersionsApplication.java` từ phần Maven. Dùng Gradle wrapper được tạo với phiên bản được Boot 4.1 hỗ trợ:

~~~bash
./gradlew clean test
./gradlew bootRun
~~~

Windows: `.\gradlew.bat clean test` và `.\gradlew.bat bootRun`. File `settings.gradle.kts` tối thiểu có thể đặt tên bằng `rootProject.name = "reactive-versions"`.

**Giải thích BOM Gradle:** plugin `org.springframework.boot` tự tạo task chạy/đóng gói, nhưng **không có nghĩa version của mọi dependency tự được quản lý khi chưa nhập BOM**. Ở đây `platform(SpringBootPlugin.BOM_COORDINATES)` nhập bộ version của đúng Boot plugin. Ngoài cách này có thể dùng plugin `io.spring.dependency-management`; chọn **một cách nhất quán** và kiểm tra kết quả resolve, tránh thêm nhiều BOM trùng hoặc override tùy tiện.

Gradle `platform` cung cấp các **ràng buộc version được đề xuất**. Dependency hoặc constraint khác trong graph vẫn có thể khiến một phiên bản khác được chọn. Vì vậy `dependencyInsight` là bước kiểm tra quan trọng, nhất là khi tích hợp thư viện không nằm trong BOM.

## 7. Khi đang ở Spring Boot 3.5.x

Nếu ứng dụng hiện dùng Boot 3.5, Spring Framework 6.2 và Spring Security 6.5, việc thêm security reactive cũng đơn giản: dùng `spring-boot-starter-webflux` và `spring-boot-starter-security` nhưng **để BOM Boot 3.5 quản lý các version 6.x tương ứng**.

Mẫu Maven khác ở phiên bản parent và cấu hình test:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>

<!-- Các dependency ứng dụng: spring-boot-starter-webflux,
     spring-boot-starter-security, không khai báo version riêng. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

**Đây chỉ là đoạn cấu hình cần đối chiếu trong `pom.xml` đã có**, không phải file POM độc lập; với project 3.5 cần giữ các phần `groupId`, `artifactId`, `properties`, `build` và dependency ứng dụng hiện hữu.

Đừng làm như sau:

~~~xml
<!-- Ví dụ KHÔNG nên dùng: Boot 3.5 nhưng tự ghép Security 7 -->
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-web</artifactId>
    <version>7.1.2</version>
</dependency>
~~~

Đây là ví dụ **cấu hình sai để nhận diện**, không được sao chép vào build. Boot 3.5 quản lý Spring Framework 6.2 / Security 6.5, còn Security 7 thuộc thế hệ tích hợp Spring Framework 7. Trộn major có thể gây lỗi build, `NoSuchMethodError` hoặc `ClassNotFoundException` khi chạy. Muốn nâng lên Security 7, hãy lập kế hoạch nâng **cả nhánh Boot** và các thư viện liên quan theo hướng dẫn migration.

## 8. Trường hợp phải dùng BOM nhưng không kế thừa Spring Boot parent

Trong project Maven đa module có parent riêng, có thể **import** Boot BOM trong `dependencyManagement`:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.1.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau đó starter không cần khai báo version nếu thuộc BOM. **Khác biệt quan trọng:** import BOM quản lý **dependency versions**, không thay thế toàn bộ cấu hình **plugin management**, resource filtering, compiler và packaging từ `spring-boot-starter-parent`. Với parent tự viết, bạn cần cấu hình plugin build/Java release phù hợp, kể cả version plugin cần thiết.

Nếu thêm một BOM khác (ví dụ Spring Cloud), hãy đọc tài liệu release train và quy tắc ưu tiên dependency-management tương ứng; không cho rằng thứ tự khai báo BOM hoặc thứ tự dependency luôn vô hại.

## 9. Kiểm tra phiên bản đã resolve — nguồn sự thật là dependency graph

### Maven

~~~bash
./mvnw -version
./mvnw help:effective-pom
./mvnw dependency:tree
./mvnw clean verify
~~~

Các lệnh này lần lượt xác minh Maven/JDK, cấu hình POM sau khi kế thừa, graph dependency đã resolve và kết quả build/test. Trên Windows thay `./mvnw` bằng `.\mvnw.cmd`.

Tìm trong `dependency:tree` các module thực tế như `spring-boot`, `spring-webflux`, `spring-security-core`, `spring-security-web`, `reactor-core`, `reactor-netty-http`. Với cấu hình Boot 4.1.2 không override, bạn kỳ vọng các module do BOM quản lý đi theo bộ **Spring Framework 7.0.10**, **Security 7.1.2**; Boot 3.5.16 tương ứng **Framework 6.2.19**, **Security 6.5.11**. Cần kiểm tra output thực tế thay vì giả định mọi dependency trong graph có cùng version.

### Gradle

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webflux --configuration runtimeClasspath
./gradlew clean test
~~~

Trên Windows thay `./gradlew` bằng `.\gradlew.bat`. `dependencyInsight` chỉ ra bản được chọn và lý do Gradle resolve bản đó, rất hữu ích khi một dependency trực tiếp hoặc constraint kéo version khác.

### Cách đọc nhanh kết quả

| Quan sát | Diễn giải | Xử lý |
| --- | --- | --- |
| Boot 4.1.2 + Security 7.1.2 + Framework 7.0.10 | Phù hợp bộ BOM đã tra | Chạy test và kiểm tra tính năng |
| Boot 3.5.16 + Security 6.5.11 + Framework 6.2.19 | Phù hợp bộ BOM nhánh 3.5 | Duy trì patch và kế hoạch migration |
| Xuất hiện đồng thời Security 6.x và 7.x | Có thể có thư viện hoặc override kéo nhầm major | Tìm nhánh phụ thuộc gây xung đột |
| `NoSuchMethodError`, `NoClassDefFoundError` | Có thể do API/binary không tương thích, classpath lệch | Kiểm tra dependency tree và stack trace |
| `UnsupportedClassVersionError` | Bytecode được biên dịch cho Java mới hơn runtime | Kiểm tra `java -version` và toolchain/release |
| Lỗi `javax.*` / `jakarta.*` khi nâng major | Có thể còn API cũ trong thư viện hoặc mã nguồn | Kiểm tra hướng dẫn migration và dependency |
| Build thành công nhưng request không đi qua filter reactive | Có thể cấu hình nhầm Servlet stack hoặc thiếu security chain reactive | Kiểm tra starter, web type và SecurityWebFilterChain |

Không “sửa” lỗi tương thích bằng cách nhét thêm một JAR bất kỳ cho hết `ClassNotFoundException`; trước tiên xác định bộ dependency nhất quán và nguyên nhân xung đột.

## 10. Khi nào mới override phiên bản Security hoặc Reactor?

Thông thường **không cần override**. Một số trường hợp có lý do chính đáng là bản vá bảo mật khẩn cấp hoặc cần fix đã phát hành trước bản vá Boot tương ứng. Khi đó:

1. Xác định advisory/CVE và các phiên bản thực sự bị ảnh hưởng.
2. Ưu tiên cập nhật **Spring Boot patch** đã quản lý bản vá.
3. Nếu chưa có, đọc hướng dẫn chính thức của Spring Security và bảng tương thích với Spring Framework. Override trong **cùng nhánh tương thích**, không tự nâng Security major.
4. Giữ các module Spring Security nhất quán, kiểm tra toàn bộ dependency graph; kiểm thử xác thực, phân quyền, CSRF, OAuth2/JWT nếu dùng.
5. Ghi lý do, phạm vi và thời hạn của override để quay về BOM khi Boot phát hành bản vá thích hợp.

Với Maven kế thừa Boot parent, Spring Security có thể cung cấp property `spring-security.version` dùng cho override theo hướng dẫn chính thức. Với Gradle native platform, cơ chế override không giống Maven property: sử dụng resolution strategy/constraints được kiểm soát và xem lại `dependencyInsight`. **Không ghi đồng thời nhiều version của `spring-security-*` trong từng dependency**.

Tương tự, không tự thay Reactor Netty/Reactor Core mới nhất nếu chưa kiểm chứng với Spring Framework/WebFlux và Boot hiện tại. Việc chạy được unit test chưa loại trừ lỗi tương thích giao thức hoặc event loop ở runtime.

## 11. Những sai lầm dễ gặp

**Sai lầm A — ghi version cho mỗi starter và module.**

~~~xml
<!-- Không làm theo -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
    <version>4.1.2</version>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-core</artifactId>
    <version>6.5.11</version>
</dependency>
~~~

Với Boot 4.1.2, cố ép Security 6.5.11 là trộn thế hệ không nhất quán. Cách đúng: dùng Boot parent/BOM và khai báo starter **không có version**; chỉ thêm module trực tiếp khi ứng dụng thật sự dùng API đó.

**Sai lầm B — nghĩ Security và Boot có cùng major.** Versioning của chúng khác nhau: Boot 4.1.2 tương ứng Security 7.1.2 theo BOM ở mốc bài học.

**Sai lầm C — quên Java của môi trường chạy.** `java.version` hoặc Gradle toolchain không tự cập nhật JVM trong container, CI hoặc máy triển khai. Kiểm tra cả build và runtime.

**Sai lầm D — sao chép cấu hình Servlet.** Reactive dùng `SecurityWebFilterChain` và `ServerHttpSecurity`, khác `SecurityFilterChain` và `HttpSecurity` của MVC/Servlet.

**Sai lầm E — xem Gradle plugin Boot đồng nghĩa tự nhập BOM.** Với Gradle cần cấu hình dependency management/plugin hoặc `platform` thật sự; luôn kiểm tra graph.

**Sai lầm F — bỏ qua thư viện ngoài BOM.** Starter Spring Cloud, OAuth2 tùy chỉnh, driver hoặc thư viện logging có thể cần nhánh cụ thể. Kiểm tra tài liệu tương thích và chạy integration test.

**Sai lầm G — dùng bản `RC`/`SNAPSHOT` mà không biết.** Release preview thích hợp cho thử nghiệm, không phải lựa chọn mặc định khi phát hành dịch vụ mới.

## 12. Bài tập thực hành

1. Tạo Maven project Boot **4.1.2** với `starter-webflux` và `starter-security` như phần 5, Java 17+.
2. Kiểm tra `effective-pom` và `dependency:tree`. Ghi lại **phiên bản thực tế** của Boot, Framework, Security và Reactor đã được Maven resolve.
3. Chạy `ReactiveVersionsApplication`. Thử `GET /ping` khi chưa đăng nhập, giải thích kết quả 401.
4. Trong bản sao project dành cho thực hành, đổi sang Boot **3.5.16** đồng thời thay test starters tương ứng; không tự ghi version cho từng Spring module. Chạy lại build và so sánh dependency tree.
5. Nêu lý do vì sao cách “Boot 3.5.16 + Security 7.1.2” không phải một lựa chọn phù hợp mặc định.

**Đáp án trọng tâm:** BOM của đúng Spring Boot mới là điểm xuất phát để có bộ thư viện nhất quán. Reactive stack cần WebFlux và các API security reactive; chọn Java/Gradle/Maven nằm trong phạm vi hỗ trợ; kiểm tra dependency graph, build, runtime và security behavior trước khi chốt triển khai.

## 13. Tài liệu chính thức

- [Spring Boot — System Requirements, nhánh hiện hành](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html)
- [Spring Boot 3.5 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [Spring Boot — Build Systems và Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Boot Gradle Plugin — Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
- [Spring Boot — Spring Security, WebFlux Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [Spring Security — Getting Spring Security](https://docs.spring.io/spring-security/reference/getting-spring-security.html)
- [Spring Security — Getting Started with WebFlux](https://docs.spring.io/spring-security/reference/reactive/getting-started.html)
- [Spring Security — Migrating to 7.0](https://docs.spring.io/spring-security/reference/migration/)
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
