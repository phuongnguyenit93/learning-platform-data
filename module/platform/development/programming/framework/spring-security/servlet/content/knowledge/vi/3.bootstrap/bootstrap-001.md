# Chọn phiên bản tương thích giữa Java, Spring Boot và Spring Security (Servlet)

Khi khởi tạo một ứng dụng **Spring MVC / Servlet**, chọn phiên bản không phải chỉ lấy bản mới nhất của từng thư viện rồi ghép lại. Java quyết định môi trường biên dịch và chạy; Spring Boot cung cấp một bộ dependency được kiểm thử tương thích; Spring Security phải nằm trong hệ phiên bản mà Spring Boot và Spring Framework đó hỗ trợ. Lựa chọn đúng cần kiểm tra cả **JDK, phiên bản Spring Boot, Spring Security, build tool và Servlet API**.

Bài này tập trung vào **cách chọn, thiết lập và kiểm chứng** bộ phiên bản cho ứng dụng Servlet, với Maven hoặc Gradle, cùng một dự án Spring Boot 3.x minh họa có thể chạy và kiểm thử. Số phiên bản trong ví dụ là **mốc minh họa cụ thể**, không được hiểu là phiên bản mới nhất hoặc còn thời hạn hỗ trợ tại thời điểm đọc.

## 1. Hiểu các tầng phiên bản và ai quản lý ai

```text
JDK chạy build (java/javac; Maven hoặc Gradle daemon)
        |
        +--> Java language level / bytecode target
        |
Spring Boot version (parent / plugin + dependency management)
        |
        +--> Spring Framework (Spring MVC, core, context...)
        +--> Spring Security (core, config, web...)
        +--> Servlet container / Jakarta APIs (Tomcat/Jetty/...)
        +--> các thư viện hạ tầng khác
        |
spring-boot-starter-web + spring-boot-starter-security
        |
Ứng dụng Spring MVC Servlet
        |
JRE/JDK thực tế trong máy chủ hoặc container khi chạy
```

- **Java / JDK:** dùng để biên dịch mã nguồn, chạy Maven/Gradle và chạy ứng dụng. Có ít nhất ba thông số cần phân biệt: JDK của quá trình build, mức bytecode được tạo ra và JRE/JDK của môi trường triển khai.
- **Spring Boot:** quản lý một tập phiên bản đã được kiểm thử cùng nhau bằng dependency management (Maven parent/BOM hoặc cơ chế tương đương trong Gradle). Boot tự động cấu hình Spring MVC, Servlet container và Security theo starter/bean có mặt.
- **Spring Framework:** thư viện nền tảng của ứng dụng Spring; Spring MVC dùng Servlet API. Spring Framework có yêu cầu Java và hệ Jakarta tương ứng.
- **Spring Security:** cung cấp xác thực, phân quyền, Servlet security filter chain và các tích hợp OAuth2 nếu chọn thêm starter tương ứng. Cần tương thích với Spring Framework và Boot; các module Security như `spring-security-web`, `spring-security-config`, `spring-security-core` nên được căn phiên bản với nhau.
- **Servlet container:** môi trường HTTP thực tế (thường là Tomcat nhúng trong `spring-boot-starter-web`). API `javax.servlet.*` và `jakarta.servlet.*` thuộc các thế hệ khác nhau; một bản Java đủ mới không giải quyết được sự bất tương thích package này.
- **Build tool:** Maven hoặc Gradle và plugin của Boot có yêu cầu phiên bản riêng. JDK mà IDE dùng có thể khác JDK mà Gradle daemon/Maven đang chạy.

**Nguyên tắc chọn:** chọn một *dòng Spring Boot được hỗ trợ phù hợp với mục tiêu triển khai*, kiểm tra yêu cầu Java và build tool cho bản Boot cụ thể, rồi **để Boot quản lý các phiên bản Spring Security** trừ khi có lý do được tài liệu chính thức hỗ trợ để override cả nhóm dependency.

## 2. Ma trận thế hệ: dùng để nhận diện ranh giới, không dùng thay release notes

| Hệ ứng dụng | Java tối thiểu ở mức thế hệ | Hệ Spring Framework / Security | Servlet namespace | Ý nghĩa khi khởi tạo |
|---|---|---|---|---|
| Spring Boot **2.7.x** | Java 8 | Spring Framework 5.x / Spring Security 5.x | `javax.servlet.*` | Dòng cũ; có thể gặp khi bảo trì, không đem cấu hình Security 6/7 áp nguyên xi |
| Spring Boot **3.x** | Java 17 | Spring Framework 6.x / Spring Security 6.x | `jakarta.servlet.*` | Chọn Servlet starter và API bảo mật thế hệ Security 6 |
| Spring Boot **4.x** | Java 17 | Spring Framework 7.x / Spring Security 7.x | `jakarta.servlet.*` | Kiểm tra migration guide và tên starter/API của chính bản 4.x; không mặc định mã 3.x chạy nguyên trạng |

Bảng diễn tả **nhóm phiên bản lớn**. Nó không khẳng định mọi bản Java mới hơn đều được hỗ trợ trên mọi *minor/patch* Spring Boot. Đặc biệt khi dùng JDK mới ra đời, phiên bản JVM, Gradle/Maven, bytecode instrumentation và dependency bên thứ ba phải cùng hỗ trợ. Bảng cũng không khẳng định các dòng cũ còn được nhà phát hành bảo trì hay được cung cấp bản vá bảo mật.

Ba khác biệt cần ghi nhớ:

1. **Spring Security 6+ yêu cầu Java 17+**, dù mã nghiệp vụ của bạn chỉ dùng cú pháp Java 8.
2. **Spring Boot 3 chuyển sang Jakarta EE:** import `jakarta.servlet.*` thay cho `javax.servlet.*`; môi trường WAR/Servlet container cũng phải tương thích. JDK 21 vẫn không khiến thư viện `javax.servlet.Filter` trở thành `jakarta.servlet.Filter`.
3. **Spring Security thay đổi API qua major version:** ví dụ Security 6 dùng `SecurityFilterChain` và lambda DSL; không chép cấu hình kế thừa `WebSecurityConfigurerAdapter` từ dự án Security 5 cũ (adapter đó không còn trong Security 6).

Trong cùng một hệ Boot 3.x vẫn phải tra **bản minor/patch chính xác** để biết Spring Security được quản lý ở bản nào, yêu cầu build tool và mức hỗ trợ JDK. Không suy đoán kiểu “Boot 3.3 bất kỳ ↔ Security 6.3 bất kỳ” khi chuẩn bị một bản release.

## 3. Cách ra quyết định phiên bản cho dự án mới

### Bước 1 — Chốt JDK ở build và runtime

Xác định môi trường production được phép dùng JDK nào. Với một dự án Boot 3.x, **JDK 17 hoặc 21** là lựa chọn minh họa dễ kiểm thử; nếu muốn một Java mới hơn, xác nhận từng bản Boot và build tool có tuyên bố hỗ trợ. Đừng đồng nhất “JDK có thể chạy ứng dụng” với “thư viện, framework và plugin đã hỗ trợ chính thức”.

Kiểm tra trên máy phát triển/CI:

```bash
java -version
javac -version
mvn -version
```

Nếu dùng Gradle, kiểm tra thêm `gradle -version` hoặc `./gradlew --version` (Windows dùng `gradlew.bat --version`). Kết quả phải được đọc thực tế: các lệnh này **không có stdout cố định** vì tùy máy và bản JDK. Quan sát JDK của Maven/Gradle thay vì chỉ nhìn Java SDK đang chọn trong IDE.

### Bước 2 — Chọn phiên bản Boot có hỗ trợ phù hợp

Dùng một bản **stable đã phát hành và còn được hỗ trợ theo chính sách của dự án**. Khi chốt, xác minh tại tài liệu chính thức của **đúng bản Boot được chọn**:

- *System Requirements*: Java tối thiểu, Java được kiểm thử/hỗ trợ và yêu cầu Maven/Gradle.
- *Dependency Versions / managed dependencies*: bản Spring Framework, Spring Security, Tomcat và các module được Boot quản lý.
- *Release Notes / Migration Guide*: thay đổi API, tên starter, package, behavior, deprecation khi đổi major/minor.
- Thông tin support và bản vá bảo mật: phân biệt *community support*, support thương mại, release preview và bản stable.

Trang tra cứu thường dùng: [Spring Initializr](https://start.spring.io/), [Spring Boot Reference](https://docs.spring.io/spring-boot/reference/), [Spring Security Reference](https://docs.spring.io/spring-security/reference/). Initializr giúp tạo dự án với bộ lựa chọn hợp lệ; release notes và dependency tree mới xác định **phiên bản thực sự được chọn**.

### Bước 3 — Chọn đúng starter cho **Servlet**

Ở hệ Spring Boot 3.x, khởi tạo với:

- `spring-boot-starter-web`: Spring MVC + Servlet stack.
- `spring-boot-starter-security`: tích hợp Security vào Servlet filter chain.
- Nếu làm Resource Server nhận bearer token: thêm `spring-boot-starter-oauth2-resource-server`, vẫn để Boot quản lý phiên bản.
- Nếu làm OAuth2/OIDC Client: thêm starter OAuth2 Client phù hợp, không ghép trực tiếp các module Security khác major.

**Chú ý dòng Boot 4.x:** kiểm tra starter được tài liệu Boot 4.x khuyến nghị (ví dụ starter Web MVC có thể thay đổi tên/nhóm phụ thuộc so với Boot 3), không sao chép máy móc file build của Boot 3.x.

Không thêm `spring-boot-starter-webflux` chỉ để gọi HTTP reactive bằng `WebClient` rồi suy rằng ứng dụng bảo vệ HTTP bằng WebFlux. Khi server vẫn là MVC Servlet, cấu hình đúng là `HttpSecurity` + `SecurityFilterChain`.

### Bước 4 — Để Boot quyết định bản Spring Security

Maven parent/BOM và plugin quản lý dependency của Gradle làm nhiệm vụ *version alignment*: các module Spring/Security/Tomcat cần tương thích với nhau. Không khai báo “latest” cho riêng `spring-security-web` hoặc `spring-security-core`.

**Điểm mấu chốt:** starter là tập dependency, **không phải** một phiên bản Spring Security độc lập. Ví dụ cùng khai báo `spring-boot-starter-security`, hai bản Spring Boot khác nhau có thể kéo hai bản Spring Security khác nhau theo bảng quản lý tương ứng. Muốn biết bản thực tế hãy xem *resolved dependency tree*, không chỉ xem `pom.xml` hoặc `build.gradle`.

## 4. Maven: một nguồn quản lý phiên bản

Đây là cấu hình **minh họa có phiên bản cố định** cho Spring Boot **3.3.5 + Java 21**; dùng để học cách căn dependency của hệ Boot 3.x. Để triển khai dự án mới, thay mốc Boot minh họa bằng bản stable còn được hỗ trợ sau khi đọc yêu cầu hệ thống/migration guide, rồi kiểm thử lại.

Tạo `pom.xml` ở gốc dự án:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>servlet-security-compat</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
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

Giải thích:

- Parent Boot quản lý phiên bản của các starter và của `spring-security-test`; không viết `<version>` ở bốn dependency đó.
- `java.version` bằng 21 đòi hỏi JDK build phù hợp. Ứng dụng đã biên dịch target Java 21 không thể chạy trên Java 17.
- `spring-boot-maven-plugin` cần đúng dòng Boot; parent quản lý plugin để tránh bản plugin khác với project.
- Starter Test hỗ trợ JUnit và kiểm thử Boot; `spring-security-test` cung cấp các tiện ích giả lập principal như `@WithMockUser`.

Nếu dự án có parent nội bộ của công ty thay vì parent Boot, có thể import BOM `spring-boot-dependencies` trong `dependencyManagement`. **Import BOM dependency** chỉ quản lý dependency; không tự quản lý toàn bộ Maven plugin như starter parent, vì vậy phải tự kiểm tra plugin/compiler/test configuration. Đừng đồng thời dùng nhiều BOM có thứ tự override không rõ ràng.

### Kiểm tra bản Maven thực sự giải quyết

```bash
mvn -version
mvn dependency:tree -Dincludes=org.springframework.security
mvn dependency:tree -Dincludes=org.springframework
mvn help:effective-pom
```

Tìm những artifact như `spring-security-web`, `spring-security-config`, `spring-security-core`. Chúng phải là một tập phiên bản phù hợp do Boot quản lý (các artifact không nhất thiết đều xuất hiện nếu không được dùng); kiểm tra thêm Spring Framework và servlet container. Output tree thay đổi theo bộ phụ thuộc và repository nên không áp đặt một kết quả tĩnh.

## 5. Gradle: plugin Boot, toolchain và dependency alignment

Trong **một dự án Gradle riêng**, tương đương với ví dụ Maven phía trên, `build.gradle` theo **Groovy DSL** có thể là:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Ví dụ Gradle này minh họa cách plugin Boot và dependency-management plugin quản lý các phiên bản transitives. Chọn **Gradle Wrapper** tương thích với bản Boot/Gradle plugin và JDK dùng để chạy Gradle; không cho rằng mọi Gradle 8.x hoặc mọi Gradle 9.x đều được hỗ trợ bởi một bản Boot cố định. Với Boot 3.3.5 và JDK 21, Gradle 8.5 là một mốc minh họa phù hợp; khi nâng Boot/JDK cần kiểm tra lại release notes.

Một chiến lược khác là Gradle native BOM/platform; khi dùng, chỉ giữ **một chiến lược alignment được hiểu rõ** thay vì trộn ép version/strict constraint/BOM một cách ngẫu nhiên. Trong multi-module build, tránh mỗi module tự chọn Spring Security khác major.

Đọc dependency đã resolve:

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
```

Trên Windows, thay `./gradlew` bằng `gradlew.bat`. Những lệnh trên giả định dự án đã tạo Gradle Wrapper; nếu dùng Maven thì chỉ chạy bộ lệnh Maven ở mục 4. `dependencyInsight` cho biết **phiên bản được chọn và lý do** (constraint, platform, dependency conflict), hữu ích hơn việc nhìn vào một dòng `implementation`.

## 6. Ứng dụng kiểm chứng cụ thể trên Servlet stack

Sử dụng **một trong hai cấu hình build** ở mục 4 hoặc 5, cùng thư mục source Java dưới đây. Mục tiêu: Spring Boot khởi động với Servlet Security; request public được phép, request private bị chặn nếu chưa xác thực. Toàn bộ ví dụ dành cho Java 21 và Boot 3.3.5 đã cố định ở trên.

Tạo `src/main/java/example/compat/CompatApplication.java`:

```java
package example.compat;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class CompatApplication {

    public static void main(String[] args) {
        SpringApplication.run(CompatApplication.class, args);
    }

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/private")
    public String privateEndpoint() {
        return "private OK";
    }
}
```

Tạo `src/main/java/example/compat/ServletSecurityConfig.java`:

```java
package example.compat;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ServletSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Vì chạy Spring MVC **Servlet**, cấu hình dùng `HttpSecurity` và `SecurityFilterChain`. Không dùng `ServerHttpSecurity`/`SecurityWebFilterChain` của WebFlux.

- `/public` được cho phép khi không đăng nhập.
- `/private` yêu cầu người dùng đã xác thực; vì bật HTTP Basic nên request chưa xác thực thường trả `401 Unauthorized`.
- Với cấu hình demo và không có bean quản lý user riêng, Spring Boot có thể tạo user mặc định phục vụ phát triển và in mật khẩu ngẫu nhiên vào log. **Không dựa vào tài khoản mặc định đó khi triển khai thật**; thay bằng nhà cung cấp danh tính hoặc cấu hình xác thực phù hợp.
- Cấu hình ví dụ không tắt CSRF mặc định. Với phương thức thay đổi trạng thái, phải thiết kế CSRF phù hợp với cách client gửi credentials thay vì tắt bừa. Hai endpoint GET chỉ phục vụ smoke test phiên bản.

### Kiểm thử Spring Security ngay khi build

Tạo `src/test/java/example/compat/CompatApplicationTest.java`:

```java
package example.compat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CompatApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointWorksWithoutLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public OK"));
    }

    @Test
    void privateEndpointRequiresAuthentication() throws Exception {
        mvc.perform(get("/private"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "student")
    void privateEndpointWorksWhenAuthenticated() throws Exception {
        mvc.perform(get("/private"))
            .andExpect(status().isOk())
            .andExpect(content().string("private OK"));
    }
}
```

Chạy với **Maven**:

```bash
mvn test
mvn spring-boot:run
```

Hoặc với **Gradle** (có Wrapper):

```bash
./gradlew test
./gradlew bootRun
```

Các lệnh `test` chạy ba assertion ở trên; kỳ vọng kết quả kiểm thử **3 test PASS** nếu project, JDK, dependency và môi trường đúng. Không có stdout Maven/Gradle cố định vì quá trình tải dependency và mức log khác nhau. Khi ứng dụng đã chạy, có thể dùng terminal khác:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
```

Kết quả logic được kỳ vọng là `GET /public → HTTP 200` với body `public OK` và `GET /private → HTTP 401` khi không gửi credentials. Trong thực tế header, timestamp, cookie và logging có thể thay đổi; nếu đổi cấu hình xác thực hoặc port thì kết quả cũng thay đổi. Bộ test ổn định hơn việc chỉ nhìn thông báo “Started” trong log.

**Ý nghĩa của demo:** thấy cả Boot, MVC, Spring Security và test infrastructure làm việc trong một bộ phiên bản. Nó **không** chứng minh mọi dependency ngoài project, mọi phiên bản JVM hay mọi môi trường production đều tương thích.

## 7. Java compiler target khác với JDK dùng để chạy

Giả sử máy build dùng JDK 21 nhưng muốn tạo thư viện classfile chạy trên Java 17. Với chương trình Java độc lập `VersionProbe.java`:

```java
public class VersionProbe {
    public static void main(String[] args) {
        System.out.println("Bytecode target verified");
    }
}
```

Trên **JDK 21**, chạy:

```bash
javac --release 17 VersionProbe.java
java VersionProbe
javap -verbose VersionProbe
```

Lệnh `java VersionProbe` in chính xác:

```text
Bytecode target verified
```

Trong phần đầu output `javap -verbose`, class file có `major version: 61`, tương ứng Java 17. Điều này minh họa **bytecode target**; nó không biến một ứng dụng Boot yêu cầu Java 17 thành ứng dụng hỗ trợ Java 8. Nếu compile target Java 21 (class file major 65) rồi chạy với JRE 17, JVM sẽ từ chối vì classfile quá mới, thường là `UnsupportedClassVersionError`.

Trong Maven ví dụ, `<java.version>21</java.version>` kết hợp cấu hình parent Boot kiểm soát mức Java ứng dụng. Với Gradle, `java.toolchain` lựa chọn compiler Java 21; khi cần đặt target thấp hơn phải cấu hình `options.release` và **kiểm chứng thư viện phụ thuộc cũng hỗ trợ target**. Thay đổi `sourceCompatibility` mà vẫn biên dịch dựa vào API JDK mới không đủ thay thế `--release`.

Để xử lý các ca chạy khác JVM giữa local, CI, IDE và Docker, ghi rõ JDK build, Gradle daemon, java target và base image JRE trong build pipeline. Một ứng dụng chạy tốt trong IDE vẫn có thể lỗi khi container dùng JRE thấp hơn.

## 8. Những lỗi phiên bản thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra/sửa |
|---|---|---|
| `UnsupportedClassVersionError` | Bytecode đã build mới hơn JRE chạy thực tế | Đọc major version, kiểm tra `java -version` trong runtime/container; chọn JRE tương thích hoặc build lại đúng target |
| Maven/Gradle báo `invalid source release: 21` hoặc không tìm được toolchain | Build thực tế dùng JDK cũ hoặc thiếu JDK 21 | So `javac -version`, `mvn -version`, `gradlew --version`, toolchain/JAVA_HOME |
| `NoClassDefFoundError`, `NoSuchMethodError` cho class Spring Security | Trộn module Security không đồng bộ hoặc lệch Spring Framework | In resolved dependency tree, tìm override/exclusion/forced version; quay về BOM Boot thống nhất |
| Lỗi `javax.servlet.*` / `jakarta.servlet.*` | Thư viện hoặc servlet container thuộc thế hệ Servlet API khác | Với Boot 3+ dùng dependency Jakarta tương thích; nâng adapter/thư viện liên quan, không sửa import đơn lẻ rồi bỏ qua dependency |
| Không tìm thấy `WebSecurityConfigurerAdapter` | Mã cấu hình từ Security 5 dùng API đã bị xóa ở Security 6 | Viết lại bằng bean `SecurityFilterChain` và API hiện hành |
| `No qualifying bean of type SecurityFilterChain` hoặc cấu hình không bảo vệ route như mong đợi | Không tạo đúng Servlet chain, cấu hình sai loại WebFlux hoặc condition đã thay đổi | Kiểm tra web stack, bean thực tế, starter, matcher/order và log khởi tạo |
| `BeanCreationException` khi khởi động với dependency Security mới ép tay | Version override làm lệch API giữa Boot/Framework/Security | Bỏ override, xem effective POM hoặc Gradle dependencyInsight, đối chiếu release notes |
| Bị `401`/`403` sau khi nâng cấp dù build thành công | Mặc định cấu hình, matcher, filter order, CSRF hoặc mapping authorities đã thay đổi | Viết security integration tests, xem response và Security filter chain, đọc migration guide |
| Lỗi plugin Gradle/Maven trước khi biên dịch | Version build tool/plugin không tương thích JDK hoặc Boot | So System Requirements của Boot, Gradle compatibility matrix, Maven version |
| Build local thành công nhưng CI hoặc container thất bại | JDK/toolchain, OS, dependency cache, repository hoặc image runtime lệch nhau | In version ở mọi môi trường, dùng wrapper và phiên bản image được chốt, thử build sạch có kiểm soát |

Một số lỗi trong bảng có nhiều nguyên nhân. **Bắt đầu bằng bằng chứng**: stack trace đầu tiên có ý nghĩa, version thực tế đã resolve và cách tạo `SecurityFilterChain`, rồi mới quyết định có cần nâng hay hạ version.

## 9. Đường biên đặc thù của Spring Security Servlet

### Servlet namespace khi nâng từ Boot 2 sang Boot 3

Ở mã Servlet cũ, có thể gặp:

```java
import javax.servlet.Filter;
import javax.servlet.http.HttpServletRequest;
```

Trong ứng dụng thuộc hệ Jakarta tương ứng, cần:

```java
import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServletRequest;
```

Nhưng **đổi import không đủ**. Mọi servlet filter, thư viện phụ, security integration và servlet container phải tương thích cùng thế hệ. Với Boot 3, embedded Tomcat do starter quản lý giúp tránh nhiều lỗi thủ công; khi deploy WAR lên application server bên ngoài, tự kiểm tra server đó hỗ trợ Servlet API Jakarta phù hợp.

### Phân biệt phiên bản Security với loại security chain

**Servlet:**

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

**WebFlux là kiến trúc khác**, dùng `ServerHttpSecurity` và `SecurityWebFilterChain`. Không đổi sang cấu hình reactive chỉ vì nâng JDK hoặc Spring Security. Đoạn Servlet ở trên là **mảnh bean minh họa**, các import và `@Configuration` nằm trong mẫu runnable ở mục 6.

### Dependency OAuth2 không quyết định Java/Boot độc lập

Nếu API Servlet cần kiểm chứng bearer token, bổ sung starter Resource Server **thuộc cùng hệ Boot**. Nếu website cần đăng nhập OIDC, thêm OAuth2 Client starter tương ứng. Không dùng sự xuất hiện của OAuth2 dependency để tự nâng một module Security lên major khác; Security Core/Web/Config/OAuth2 phải cùng lớp tương thích của Boot.

## 10. Quy trình nâng cấp có kiểm soát

1. **Ghi baseline:** JDK local/CI/container, Maven/Gradle wrapper, Spring Boot, Spring Security đã resolve, servlet container, danh sách integration quan trọng và trạng thái test.
2. **Xác định đích:** chọn Boot stable theo thời gian hỗ trợ và yêu cầu Java/Jakarta/Servlet; đọc migration guide trước khi nâng major. Ưu tiên bản vá bảo mật trên dòng đang hỗ trợ trước khi chọn đổi major nếu phù hợp.
3. **Nâng đầu mối quản lý:** sửa **version Boot parent/plugin/BOM** và JDK/toolchain tương ứng. Tránh nâng một mình `spring-security-web`/`spring-security-config`/`spring-security-core`.
4. **Resolve lại toàn bộ dependency:** xem `mvn dependency:tree` hoặc `gradlew dependencies` và `dependencyInsight`. Tìm duplicate/forced version, exclusion, dependency shading, libraries vẫn dùng `javax.servlet`.
5. **Sửa những API không tương thích:** security configuration DSL, servlet namespace, filter adapter và các dependency bên thứ ba. Chỉ dùng migration guide đúng bản đích.
6. **Chạy test nhiều lớp:** build/compile, unit test, Servlet integration test bằng MockMvc, các luồng `401`/`403`/CSRF/login/logout, endpoint công khai, các chính sách phân quyền và OAuth2 nếu có.
7. **Kiểm thử môi trường phát hành:** JDK runtime trong image, TLS/cert, reverse proxy, session, servlet container, external integrations, CI/CD. Ghi nhận phiên bản và kết quả trong release notes nội bộ.

**Không lấy “build xanh” làm bằng chứng hoàn tất:** dependency hợp lệ ở mức compiler vẫn có thể thay đổi security defaults hoặc behavior ở runtime. Đối với chức năng bảo mật, đặc biệt kiểm tra cả trường hợp truy cập không được phép (*negative tests*).

### Checklist trước khi chốt lựa chọn

- [ ] Đã ghi rõ JDK build, Java target và JRE production; chúng tương thích theo cả yêu cầu của Boot lẫn bytecode.
- [ ] Đã chọn **một bản Spring Boot cụ thể** theo tài liệu chính thức và vòng đời hỗ trợ.
- [ ] Spring Framework, Spring Security, Servlet container được resolve từ BOM/parent/plugin thống nhất, không ép version không có căn cứ.
- [ ] Dự án Servlet dùng MVC starter và `HttpSecurity`/`SecurityFilterChain` đúng thế hệ.
- [ ] Đã so chiếu `javax.servlet` / `jakarta.servlet` khi nâng major hoặc tích hợp thư viện cũ.
- [ ] Maven/Gradle wrapper, plugin, CI và base image hỗ trợ JDK tương ứng.
- [ ] Integration test chứng minh public endpoint truy cập được, private endpoint bị chặn đúng và quyền nghiệp vụ không bị bỏ qua.
- [ ] Đã đọc release notes/migration guide và kiểm tra dependency tree sau khi resolve.

## 11. Tự kiểm tra kiến thức

**Câu 1.** Dự án dùng Spring Boot 3.x, Java 21; có thể tùy ý thêm `spring-security-web:5.x` vì API của lớp đó quen thuộc không?  
**Đáp án:** Không. Spring Security 5.x thuộc thế hệ tương ứng với Spring Framework/Servlet khác; cần theo các phiên bản được Boot 3.x quản lý và migrate security configuration.

**Câu 2.** `build.gradle` không ghi version ở `spring-boot-starter-security`. Làm sao biết Spring Security đang chạy bản nào?  
**Đáp án:** Xem resolved runtimeClasspath bằng `dependencies`/`dependencyInsight`; bản quản lý đến từ cấu hình Boot/dependency management, không suy đoán từ tên starter.

**Câu 3.** JDK 21 build thành công nhưng container Java 17 lỗi `UnsupportedClassVersionError`. Cần kiểm tra gì?  
**Đáp án:** Classfile target và JRE runtime. Nếu build tạo classfile Java 21 (major 65), Java 17 không chạy được; chọn runtime phù hợp hoặc build target tương thích khi toàn bộ dependency cho phép.

**Câu 4.** Đổi `javax.servlet.Filter` sang `jakarta.servlet.Filter` đã đủ để nâng ứng dụng Servlet từ Boot 2 lên Boot 3 chưa?  
**Đáp án:** Chưa. Cần kiểm tra các integration, thư viện, servlet container và API bảo mật có tương thích Jakarta/Spring mới không, rồi chạy lại tests.

**Câu 5.** Muốn nâng Spring Security vì bản vá, nên đổi ngẫu nhiên một module Security trong POM hay nâng Boot patch được hỗ trợ trước?  
**Đáp án:** Ưu tiên đánh giá bản Boot patch được hỗ trợ, xác định Security đã được quản lý và advisories tương ứng; nếu cần override có chủ đích, phải theo hướng dẫn chính thức và test toàn bộ nhóm phụ thuộc.

**Kết luận:** **JDK tương thích + một hệ Spring Boot được quản lý thống nhất + Security/Servlet đúng thế hệ + build/runtime được kiểm chứng** là điều kiện để chọn phiên bản an toàn. Câu trả lời chính xác cho một phiên bản cụ thể luôn đến từ *System Requirements*, *managed dependencies*, release notes và dependency tree của chính project, rồi được xác nhận bằng kiểm thử Servlet security.