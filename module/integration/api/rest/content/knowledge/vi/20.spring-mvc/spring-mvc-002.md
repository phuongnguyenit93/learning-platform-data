# Chọn Java, Spring Boot và thư viện tương thích

## 1. Chọn nền tảng trước khi viết REST controller

Một REST API có thể chạy tốt trên máy phát triển nhưng lỗi khi lên production chỉ vì các thành phần không tương thích: Java compiler dùng phiên bản mới hơn JVM triển khai, Spring Boot và Spring Framework bị ép về hai dòng khác nhau, thư viện dùng namespace javax.servlet cũ trong ứng dụng Jakarta, hoặc OpenAPI UI không hỗ trợ phiên bản Spring mới.

Trong module **INTEGRATION_API_REST**, mục tiêu là xây dựng API theo resource, URI, phương thức và status HTTP; sau đó triển khai phân trang, cache, idempotency, OpenAPI, authentication/authorization, lỗi và kiểm thử bằng Java/Spring. **Chọn phiên bản đúng** giúp các tính năng này vận hành nhất quán, nhận được bản vá bảo mật và có lộ trình nâng cấp.

Bài học tập trung vào **cách lựa chọn và kiểm chứng tương thích**, không quảng cáo một phiên bản là mới nhất cho mọi thời điểm. Các bản phát hành, yêu cầu JDK và thời hạn hỗ trợ thay đổi; trước khi tạo dự án thực tế cần đối chiếu tài liệu chính thức và ma trận hỗ trợ của **đúng bản patch** đã chọn.

Sau bài học, người học có thể:

1. Phân biệt **Java language level, JDK build, JVM runtime, Spring Boot, Spring Framework, Jakarta APIs, Servlet container và thư viện bổ sung**.
2. Lập ma trận chọn Java LTS, Spring Boot và starter phù hợp với nhu cầu REST API.
3. Dùng **dependency management/BOM** để tránh trộn các phiên bản transitive tùy tiện.
4. Nhận biết rủi ro khi nâng cấp Boot major, đặc biệt chuyển từ javax sang jakarta và thay đổi API bảo mật.
5. Dùng Java/Spring, HTTP, OpenAPI, kiểm thử và bảo mật để chứng minh lựa chọn thực sự chạy đúng.
6. Thiết lập checklist nâng cấp, phát hiện CVE, kiểm tra runtime và chuẩn bị rollback.

> **Nguyên tắc cốt lõi:** Đừng “chọn từng JAR mới nhất” rồi hy vọng chúng hoạt động cùng nhau. Hãy chọn **một platform được hỗ trợ**, để BOM của platform quản lý các thư viện liên quan, chỉ override khi có lý do và bằng chứng kiểm thử.

## 2. Bản đồ tương thích: những lớp khác nhau trong một ứng dụng Spring

~~~mermaid
flowchart TD
    A[REST contract: URI, HTTP, JSON, security] --> B[Ứng dụng Java và Spring MVC]
    B --> C[Spring Boot: starters, auto-configuration, BOM]
    C --> D[Spring Framework và Spring Security]
    D --> E[Jakarta Servlet / Validation / Persistence APIs]
    E --> F[Servlet container, JSON mapper, ORM, database driver]
    F --> G[JDK để build và JVM chạy ứng dụng]
    G --> H[OS/container image, CPU architecture, TLS]
~~~

Sơ đồ trên biểu diễn các lớp phụ thuộc **logic**; thực tế mỗi thư viện có dependency graph riêng và không phải tất cả nằm trên một đường thẳng. Khi một lớp đổi major, những lớp liên quan có thể cần đổi theo.

| Lớp | Quyết định cụ thể | Ví dụ rủi ro |
|---|---|---|
| **JDK / language level** | Java 17, 21, 25 LTS hoặc bản được tổ chức hỗ trợ | Dùng cú pháp Java 21 nhưng compiler cấu hình release 17 |
| **Runtime JVM** | JDK/JRE image và vendor, cùng nền tảng CPU/OS | Build class Java 21, deploy JVM 17 → UnsupportedClassVersionError |
| **Spring Boot** | Dòng major/minor/patch và thời hạn hỗ trợ | Auto-configuration/starter thay đổi giữa major |
| **Spring Framework** | Dòng được Boot quản lý | Override thủ công gây NoSuchMethodError |
| **Servlet stack** | Spring MVC + embedded Tomcat/Jetty được hỗ trợ | Thư viện filter dùng javax.servlet trong stack Jakarta |
| **Validation/JPA** | jakarta.validation, jakarta.persistence và provider | Annotation cũ không được nhận hoặc provider lệch API |
| **Security** | Spring Security + OAuth2 Resource Server nếu cần | DSL/filter chain khác, token được parse nhưng không kiểm quyền |
| **OpenAPI** | Bộ sinh tài liệu/UI hỗ trợ Boot/Framework thực tế | App khởi động nhưng /v3/api-docs lỗi runtime |
| **Driver/migration** | JDBC driver, Flyway/Liquibase theo DB thực | Driver không hỗ trợ DB hoặc schema migration mới |
| **Build/deploy** | Gradle/Maven, plugin, container image và TLS | Build plugin không chạy với JDK/Gradle đã chọn |

**API hoạt động ở tầng HTTP** không chỉ phụ thuộc phiên bản Spring MVC. Hợp đồng HTTP còn phụ thuộc message converters, JSON mapping, security filters, proxy và persistence.

### 2.1. Java source, bytecode và JVM runtime

**JDK build** biên dịch và chạy test; **--release 21** giới hạn Java API và bytecode ở mức Java 21; **JVM production** phải đọc được bytecode ấy (JVM 17 không chạy được class Java 21). Dù JVM load được class, vẫn phải kiểm chứng thư viện, driver, agent và Spring Boot hỗ trợ Java đích.

### 2.2. Chọn Java LTS như thế nào?

Java 17, 21 và 25 là các mốc LTS cần cân nhắc theo **support policy tại ngày chọn**. Xem minimum Java của Boot, chọn LTS được vendor/tổ chức hỗ trợ, kiểm thư viện/driver/agent/build tool và pin image runtime; CI phải test trên **Java major của production**. Java mới hơn chưa chắc là lựa chọn tốt khi một thành phần quan trọng chưa tương thích.

## 3. Spring Boot, Spring Framework và Jakarta: chọn theo một dòng hỗ trợ

### 3.1. Boot không chỉ là một thư viện web

Spring Boot cung cấp **starter dependencies**, auto-configuration, dependency management, cơ chế externalized configuration, server tích hợp, Actuator và tích hợp kiểm thử. Spring MVC là phần của Spring Framework cho request mapping, binding, validation, exception handling, message conversion và HTTP response.

Chẳng hạn:

~~~text
Spring Boot starter web
    -> Spring MVC
    -> Spring Framework core/context/web
    -> JSON serializer
    -> Servlet container tích hợp
~~~

**Không tự chọn riêng Spring Framework 6.x/7.x theo trực giác** khi đang dùng một Spring Boot đã quản lý nó. Phiên bản Framework, Security, Jackson, servlet engine và các starter có quan hệ tương thích cần được Boot BOM khóa lại.

### 3.2. Các ranh giới major cần hiểu

| Hệ sinh thái | Nhận diện | Hậu quả khi chọn hoặc nâng cấp |
|---|---|---|
| **Spring Boot 2.x / Spring Framework 5.x** | Thường gắn với các API Java EE cũ dùng javax.servlet / javax.validation | Không copy nguyên dependency cũ sang dự án Jakarta mới |
| **Spring Boot 3.x / Spring Framework 6.x** | Java 17 trở lên làm nền; dùng namespace Jakarta EE ở các phần chuyển đổi | Cần jakarta.servlet.*, jakarta.validation.*, jakarta.persistence.* |
| **Spring Boot 4.x / Spring Framework 7.x** | Thế hệ major tiếp theo, có thay đổi về module/starter/auto-configuration | Đọc migration guide và ma trận tương thích **của đúng bản** trước khi áp dụng |

Bảng là **bản đồ xu hướng major**, không phải danh sách patch hiện hành hoặc cam kết rằng mọi thư viện hỗ trợ mọi JVM mới. Khi chọn bản cụ thể, kiểm chứng tại **System Requirements, Dependency Versions, release notes, migration guide và security support policy** của bản ấy.

### 3.3. Bẫy javax → jakarta

Trong ứng dụng Spring Boot 3.x/Jakarta:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.persistence.Entity;
~~~

Các import cũ tương ứng:

~~~java
import javax.servlet.http.HttpServletRequest;
import javax.validation.Valid;
import javax.persistence.Entity;
~~~

không tương thích trực tiếp với API Jakarta mà Spring Framework hiện đại sử dụng. **Không đổi toàn bộ chuỗi javax thành jakarta một cách máy móc**: javax.crypto, javax.net, javax.sql và nhiều package Java SE vẫn giữ tên javax. Phải phân biệt API đã chuyển namespace theo Jakarta EE với API thuộc Java SE.

Rủi ro còn ở **thư viện transitively kéo API cũ**, annotation từ plugin code generation, Servlet filter, JPA entity listener và converter của đối tác. Khi nâng Boot major, kiểm tra imports trong **mã nguồn lẫn dependencies**.

### 3.4. Quyết định một baseline thay vì “phiên bản mới nhất”

Chốt baseline theo **một bảng quyết định có bằng chứng**: Java LTS được Boot hỗ trợ; Boot minor/patch còn vòng đời; MVC/Servlet stack; Security/Jakarta/ORM từ BOM; driver đúng DB; công cụ OpenAPI theo compatibility matrix; wrapper và container image được pin. Ghi **ngày đánh giá, owner, phiên bản được duyệt và ngày rà soát lại**; bản đang hỗ trợ hôm nay có thể hết vòng đời trước khi hệ thống kết thúc vận hành.

## 4. Chọn Spring starters theo những năng lực API cần thật sự

| Nhu cầu | Starter hoặc thành phần nên cân nhắc | Ghi chú |
|---|---|---|
| REST API đồng bộ dùng Servlet | spring-boot-starter-web hoặc starter MVC tương ứng theo dòng Boot | Request mapping, JSON, embedded servlet engine |
| Bean Validation | spring-boot-starter-validation | Jakarta Validation cho DTO, cần thêm invariant nghiệp vụ |
| Authentication/authorization | spring-boot-starter-security | Khởi tạo security chain; phải cấu hình policy thực |
| JWT Bearer Resource Server | spring-boot-starter-oauth2-resource-server | Kiểm token, issuer/audience/scope và phân quyền resource |
| Monitoring/health | spring-boot-starter-actuator | Giới hạn actuator endpoints và quyền |
| JPA/ORM | spring-boot-starter-data-jpa | Phù hợp entity/transaction, cảnh giác N+1 |
| JDBC | spring-boot-starter-jdbc | SQL trực tiếp, phù hợp các query/transaction tùy biến |
| Schema migration | Flyway hoặc Liquibase tương thích | Không chạy thay đổi schema tùy tiện lúc bootstrap |
| Cache | spring-boot-starter-cache + provider được hỗ trợ | Cache HTTP khác application cache |
| Testing | spring-boot-starter-test, spring-security-test | JUnit, MockMvc, security tests |
| PostgreSQL | org.postgresql:postgresql | Driver phải phù hợp Java và DB đang dùng |
| OpenAPI docs | springdoc-openapi hoặc công cụ khác đúng major | Kiểm compatibility với Boot/Spring Framework |

**Tên starter và cách tách module có thể thay đổi khi lên major Boot mới**: coi bảng là bản đồ chức năng và tra danh sách starter của dòng đã chọn, không copy nguyên dependencies từ một tutorial dùng bản khác.

### 4.1. Spring MVC hay WebFlux?

**Spring MVC** hợp với REST API dùng JDBC/JPA và blocking I/O; **WebFlux** dành cho đường xử lý được thiết kế non-blocking. Đừng đổi sang reactive chỉ vì nhiều kết nối nhưng vẫn gọi JDBC trên event loop. Quyết định theo workload, driver, đội ngũ và load tests; MVC vẫn có thể dùng HTTP client để gọi dịch vụ khác.

### 4.2. Tránh kéo cả hai web stack khi không cần

Các starter MVC/WebFlux có thể cùng xuất hiện do dependency transitively. **Xem dependency graph** và chọn kiến trúc server có chủ đích, không để classpath quyết định vô tình.

### 4.3. Security là yêu cầu của nghiệp vụ, không phải một starter “xong việc”

Thêm spring-boot-starter-security **không tự cấu hình JWT/tenant authorization**. GET /api/orders/ord-741 phải xác minh bearer token và quyền đọc chính đơn ấy. Filter chain xử lý authentication/scope, còn service/repository thực thi resource-level ACL; không tin tenantId client gửi hoặc ID khó đoán.

## 5. Dependency management và BOM: khóa một tập thư viện đã được kiểm thử

### 5.1. Vì sao BOM quan trọng?

Giả sử một thành viên thêm:

~~~text
spring-boot-starter-web      -> Spring MVC, Jackson, Tomcat...
spring-boot-starter-security -> Spring Security...
spring-boot-starter-data-jpa -> Spring Data, Hibernate, JDBC...
springdoc-openapi            -> Spring MVC introspection...
~~~

Các thư viện kéo theo nhiều dependency khác nhau. Nếu tự gắn phiên bản mới nhất cho Spring Framework, Security hoặc Jackson mà không kiểm tra, bạn có thể tạo ra graph **biên dịch được nhưng lỗi runtime**, ví dụ NoSuchMethodError, ClassNotFoundException, LinkageError hoặc thay đổi serialization.

**BOM (Bill of Materials)** định nghĩa phiên bản tương thích cho một nhóm dependencies. Spring Boot cung cấp **spring-boot-dependencies**; khi dùng đúng cơ chế dependency management, phần lớn dependencies Spring và thư viện thông dụng **không cần tự khai version**. Một dependency ngoài BOM vẫn cần version rõ và kiểm tra ma trận tương thích riêng.

### 5.2. Ví dụ Gradle Kotlin DSL cho một baseline minh họa

Đoạn sau sử dụng **Java 21 và Spring Boot 3.5.0 như một ví dụ lịch sử cụ thể**, **không khẳng định đó là lựa chọn mới nhất hoặc còn được hỗ trợ tại ngày triển khai**. Trước khi dùng cho dự án thực, thay bằng **bản patch còn được hỗ trợ** đã kiểm tra với JDK, plugin và toàn bộ dependencies.

~~~kotlin
// build.gradle.kts — ví dụ baseline đã cố định version để học
plugins {
    java
    id("org.springframework.boot") version "3.5.0"
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

dependencies {
    // Native Gradle BOM; không cần tự ép version cho starter của Boot.
    implementation(platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    ))
    testImplementation(platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    ))

    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    runtimeOnly("org.postgresql:postgresql")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}

tasks.withType<Test> {
    useJUnitPlatform()
}
~~~

**Chú thích:**

- Plugin được pin; Java Toolchains chọn JDK build/test nhưng **production JVM** cũng phải phù hợp.
- BOM quản lý Spring/Jackson/Hibernate/Security; với Maven dùng **spring-boot-starter-parent** hoặc BOM qua dependencyManagement.
- Thêm OpenAPI generator, Flyway và Testcontainers theo **compatibility matrix** của bản Boot/DB đã chọn; đừng tự áp version của tutorial khác.

Để build tái lập, pin **Gradle Wrapper, dependency/plugin versions, JDK/container image** và dùng repositories đáng tin; không dùng version ranges động trong production.

### 5.3. Version override là quyết định ngoại lệ

Khi gặp CVE, **ưu tiên bản Boot/BOM patch đã vá lỗi**. Nếu buộc override, xác minh advisory áp dụng, ghi version/owner/thời hạn, xem dependency graph và chạy regression tests; quay về BOM khi có bản vá chuẩn. Đặc biệt, không tự nâng riêng Spring Framework core và một module con mà bỏ qua tương thích với Boot/Security.

### 5.4. Điều tra dependency graph

Ví dụ với dự án Gradle (lệnh chỉ để người học tham khảo, không thực thi trong bài):

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-webmvc \
  --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
~~~

Đối với Maven, các lệnh tương tự có thể dùng **mvn dependency:tree** và **mvn help:effective-pom**. Cần xác định **version thực sự được resolve**, không chỉ version ghi ở dependency trực tiếp. Theo dõi cả dependency scope, duplicate libraries và dependency được đóng gói bên trong một vendor JAR.

## 6. Kiểm tra tính tương thích trước khi chốt một platform

Một bảng quyết định ngắn, có bằng chứng:

| Hạng mục | Câu hỏi cần chứng minh | Nguồn hoặc bài test |
|---|---|---|
| Java | JDK này có nằm trong phạm vi hỗ trợ của bản Boot chọn? | System Requirements, toolchain build và prod smoke |
| Build | Gradle/Maven wrapper chạy được với JDK và Boot plugin? | CI build sạch trên image chuẩn |
| Servlet | Web MVC và container embedded cùng dòng Jakarta API? | Dependency tree, startup + HTTP tests |
| Security | Spring Security và OAuth2/JWT đồng bộ với Boot? | Token validation, tenant authz tests |
| Persistence | Hibernate/JPA/JDBC driver hỗ trợ Java/DB server? | DB migration + transactional tests |
| OpenAPI | springdoc hoặc generator hỗ trợ đúng Boot major/Framework? | /v3/api-docs + UI + schema contract tests |
| JSON | Cấu hình object mapper hỗ trợ date/time/enum/number và error DTO? | Golden JSON/contract tests |
| Ops | Image base OS/arch, TLS, agents, metrics, tracing vận hành? | Staging smoke, profiling, security scans |
| Support | Bao lâu còn nhận bản vá? Ai chịu trách nhiệm cập nhật? | Support policy, ADR và kế hoạch patching |

**Compatibility matrix có thể thay đổi theo patch.** Tài liệu chính thức của Spring Boot, Spring Framework, Spring Security, các thư viện OpenAPI/driver và nhà phân phối JDK là nơi phải xác nhận khi ra quyết định; không suy từ ví dụ trên mạng.

### 6.1. Bẫy springdoc và OpenAPI

Một thư viện sinh OpenAPI thường tích hợp sâu với cấu trúc Spring MVC và cách phát hiện controller. Dòng springdoc phù hợp với một major Spring Boot **không nhất thiết** tương thích với major kế tiếp. Triệu chứng: app khởi động nhưng endpoint **/v3/api-docs** lỗi 500 hoặc Swagger UI không mở, dù GET /api/orders vẫn trả 200.

Quy trình chọn:

- Xác định version Boot/Spring Framework thực tế từ dependency graph.
- Đọc **compatibility matrix của phiên bản springdoc định dùng** hoặc chọn công cụ tài liệu khác tương thích.
- Pin đúng artifact starter cho **Spring MVC**, tránh vô tình dùng starter WebFlux.
- Bảo vệ endpoint tài liệu theo môi trường/quyền; **Swagger UI không phải API security**.
- Test generation và validate OpenAPI trong CI; không coi UI mở được là bằng chứng hợp đồng đúng.

Nếu nâng Boot 3 sang Boot 4, **không chỉ đổi con số version** mà bỏ qua thay đổi Spring Framework, servlet stack, security, JSON và công cụ OpenAPI. Phải lập danh sách các thành phần cần nâng đồng bộ và đọc migration guide.

### 6.2. Khi nào cần thư viện ngoài starter?

**Chỉ thêm khi có use case:**

- **Resilience/retry:** nếu gọi service ngoài, cần timeout, retry budget, circuit breaker theo hợp đồng. Thư viện resilience phù hợp phải tương thích Spring/Java; không retry POST gây side effect tùy tiện.
- **Rate limiting:** có thể ở gateway/application; tránh mỗi layer tự tạo trạng thái hạn mức trái ngược.
- **Pagination/serialization:** ưu tiên khả năng có sẵn của Spring Data/Spring MVC; không thêm framework toàn diện chỉ để serialize một page.
- **API validation:** dùng Jakarta Bean Validation, bổ sung cross-field/business validation ở service.
- **Security/token:** ưu tiên thư viện chính thức trong Spring Security; hạn chế tự viết JWT parser.
- **Tracing/observability:** chọn instrumentation đồng bộ với Boot/Actuator/OpenTelemetry stack.

Đánh giá mỗi dependency theo **giá trị, độ phức tạp, tần suất vá bảo mật, chủ bảo trì, license, compatibility và khả năng thay thế**, không theo số sao GitHub hoặc độ phổ biến trong tutorial.

## 7. Kiểm chứng lựa chọn bằng một REST endpoint và Spring Security

### 7.1. Hợp đồng HTTP cần giữ ổn định dù nâng thư viện

Một API orders có thể công bố:

~~~http
GET /api/orders/ord-741 HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"id":"ord-741","status":"CONFIRMED","totalAmount":350000}
~~~

Khi nâng Java/Spring, **hợp đồng này không nên vô tình đổi** sang response XML, thiếu totalAmount, chuyển amount thành chuỗi, trả status khác hoặc bỏ kiểm tra quyền. Quyết định thư viện chỉ có giá trị khi các hành vi HTTP quan trọng được giữ vững.

### 7.2. Ví dụ Spring MVC controller

Ví dụ dùng Java records, Spring MVC và Spring Security hiện đại:

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record OrderView(String id, String status, long totalAmount) {}

interface AuthorizedOrders {
    // Query bắt buộc giới hạn tenant/owner và scope nghiệp vụ.
    OrderView findVisible(String id, String subject, String tenant);
}

@RestController
@RequestMapping("/api/orders")
class OrderReadController {
    private final AuthorizedOrders orders;

    OrderReadController(AuthorizedOrders orders) {
        this.orders = orders;
    }

    @GetMapping(path = "/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<OrderView> get(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {

        String tenant = jwt.getClaimAsString("tenant_id");
        OrderView view = orders.findVisible(
                id, jwt.getSubject(), tenant);

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(view);
    }
}
~~~

Đây là **fragment minh họa**: cần triển khai AuthorizedOrders, xử lý tenant claim thiếu/null, security policy, lỗi không tìm thấy/không có quyền và tests. **Không lấy tenant từ query string** để tin tưởng. Service không được đọc mọi order theo ID rồi chỉ kiểm tra quyền trong UI; authorization cần thực thi ở tầng service/query.

### 7.3. Cấu hình Resource Server minh họa

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        http
            // Chỉ phù hợp khi API dùng bearer token stateless,
            // không xác thực bằng cookie/session từ browser.
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt -> {}));

        return http.build();
    }
}
~~~

Lựa chọn vô hiệu CSRF trong ví dụ **chỉ có cơ sở khi xác thực API bằng Authorization bearer header và không dựa vào cookie gửi tự động**; không copy cấu hình này vào web app session/cookie. JWT decoder cần được cấu hình để xác minh chữ ký, issuer, thời hạn và **audience theo yêu cầu API**. Tên authorities SCOPE_... phụ thuộc claim/mapper đang dùng; tests phải kiểm đúng mapping chứ không suy đoán.

Ví dụ cấu hình issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/orders
~~~

**Không đưa private signing key hoặc access token thật vào cấu hình mẫu.** Issuer URI là ví dụ; production phải có TLS, trust/availability policy, cấu hình JWT validator và chiến lược rotation keys. Starter bảo mật chỉ cung cấp cơ chế, còn resource-level ACL do nghiệp vụ quyết định.

### 7.4. Khác biệt giữa API compatibility và library compatibility

Thư viện nâng thành công nhưng contract vẫn có thể hỏng: serializer đổi định dạng ngày/số/enum, validation trả status khác, Security đổi mapping scope hoặc ORM gây N+1. Vì vậy **kiểm thử nâng cấp phải bao gồm HTTP contract tests**, không chỉ biên dịch.

## 8. Kiểm thử stack được chọn

### 8.1. Ma trận tối thiểu

| Lớp cần test | Kiểm tra |
|---|---|
| **JDK / build** | Clean build trên toolchain và Gradle/Maven wrapper đã pin |
| **Startup** | ApplicationContext khởi động, health có trạng thái đúng |
| **HTTP** | Path, method, status, content type, JSON schema, header |
| **Validation** | Thiếu field, số lượng âm, malformed JSON, unsupported media type |
| **Authentication** | Token thiếu, sai chữ ký, hết hạn, issuer/audience sai |
| **Authorization** | Scope thiếu, caller khác tenant, object-level ACL |
| **Persistence** | Transaction/rollback, migration, query pagination, N+1 |
| **Idempotency** | POST retry sau timeout không tạo resource/charge trùng |
| **Caching** | ETag/304, private/no-store, invalidation nếu có |
| **OpenAPI** | /v3/api-docs tạo đúng, schema/lint/diff và runtime khớp |
| **Operational** | Logging không lộ PII, Actuator exposure, metrics và SLO |

### 8.2. MockMvc: kiểm tra HTTP và phân quyền

Ví dụ test fragment với MockMvc, JUnit 5 và Spring Security Test:

~~~java
// Bên trong test đã inject mockMvc và stub AuthorizedOrders.
mockMvc.perform(get("/api/orders/ord-741")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.id").value("ord-741"))
    .andExpect(jsonPath("$.totalAmount").value(350000));

mockMvc.perform(get("/api/orders/ord-741")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_other"))))
    .andExpect(status().isForbidden());
~~~

Fragment cần static imports của MockMvcRequestBuilders, Spring Security MockMvc request postprocessors, result matchers, SimpleGrantedAuthority và MediaType. Quan trọng: **jwt() của test tạo Authentication giả lập**, nên test này chứng minh logic filter/authority, **không chứng minh JWT chữ ký/issuer/audience thật được xác minh**. Bổ sung integration tests dùng JwtDecoder thực/mocked hợp lý và token không hợp lệ; kiểm tra tenant A không thấy dữ liệu B bằng DB fixtures.

### 8.3. Test HTTP contract không chỉ test happy path

Không chỉ test GET thành công: sau nâng cấp cần kiểm tra **POST 201 + Location**, retry cùng Idempotency-Key/payload không tạo đơn trùng trong DB, token thiếu quyền, content type sai, giới hạn body, pagination và error schema. Nếu dependency thay status hoặc bỏ kiểm tra quyền, đó là **API regression** dù build vẫn xanh.

## 9. Nâng cấp Java/Spring mà không phá production

Quy trình khuyến nghị:

1. **Kiểm kê:** lưu version JDK, Boot, Gradle/Maven, dependency tree, DB driver, OpenAPI generator, runtime image và agents.
2. **Chọn đích:** xác nhận support lifecycle, system requirements, migration guide, CVE và release notes của bản đích.
3. **Tạo nhánh nâng cấp:** cập nhật Boot/BOM trước, chỉ override khi có lý do; xử lý namespace Jakarta, API bị loại bỏ, auto-configuration, Security DSL và starter names.
4. **Build/test sạch:** chạy compile, lint/contract tests, integration DB/security, test tải và các tình huống lỗi HTTP.
5. **Staging giống production:** cùng Java major, OS/architecture, proxy, TLS, DB, driver và policy; đo memory, p95/p99, N+1, connection pool.
6. **Triển khai kiểm soát:** canary/rolling deployment, quan sát 4xx/5xx, latency, GC, DB waits, token failures, OpenAPI docs; có rollback plan.

**Rollback code không luôn đồng nghĩa rollback database.** Nếu migration schema phá khả năng chạy của version cũ, cần chiến lược expand–migrate–contract hoặc backward-compatible schema. Nếu nâng Java/container image, phải kiểm tra cả startup time, heap/GC, TLS negotiation và agent monitoring.

### 9.1. Checklist cho major migration

Đặc biệt kiểm tra imports **javax → jakarta**, cấu hình Security/role/scope, JSON enum/date/null, Hibernate dialect/transaction, công cụ OpenAPI, Gradle Wrapper và lỗi runtime **UnsupportedClassVersionError/NoSuchMethodError**.

Trong production, ưu tiên **nâng từng trục có thể kiểm soát** thay vì đồng thời đổi Java major, Spring Boot major, ORM, DB engine và toàn bộ HTTP client rồi khó xác định nguồn lỗi.

## 10. Bài tập thực hành

**Bài 1 — Chọn baseline.** Dự án mới dùng PostgreSQL, REST MVC, JWT, OpenAPI; công ty hỗ trợ Java 21, một thư viện APM chưa xác nhận Java 25. Bạn chọn Java nào? **Gợi ý:** Java 21 nếu dòng Boot được chọn hỗ trợ và APM/DB driver tương thích; chưa chọn Java 25 chỉ vì mới hơn. Ghi bằng chứng và ngày xem xét lại.

**Bài 2 — Lỗi namespace.** Sau khi chuyển từ Spring Boot 2 sang Boot 3, controller import javax.validation.Valid và filter import javax.servlet.Filter. **Đáp án:** Kiểm tra và chuyển các API Jakarta EE tương ứng sang jakarta.validation/jakarta.servlet; nâng các thư viện phụ thuộc, không đổi javax.sql hoặc javax.crypto.

**Bài 3 — Dependency conflict.** Một developer ép spring-webmvc mới hơn bản do Boot BOM quản lý, sau đó app lỗi NoSuchMethodError. **Gợi ý:** Xem dependencyInsight/dependency tree, bỏ override hoặc chọn Boot patch tương thích, chạy integration tests. Không vá bằng cách ép thêm các JAR ngẫu nhiên.

**Bài 4 — API drift.** Sau upgrade, endpoint tạo đơn chuyển từ 201 + Location sang 200, dù controller vẫn tạo thành công. **Đáp án:** Contract regression; kiểm tra controller/advice, phục hồi HTTP contract hoặc quản lý breaking change có chủ đích.

**Bài 5 — Security test.** MockMvc với jwt() và đúng scope trả 200. Có thể kết luận token giả mạo sẽ bị chặn ở production không? **Đáp án:** Chưa; jwt() test bypasses token decoding. Cần kiểm thử JwtDecoder/issuer/audience/signature và resource-level tenant authorization.

## 11. Checklist lựa chọn và kết luận

- [ ] Java LTS được Boot và vendor hỗ trợ; build target khớp runtime JVM?
- [ ] Spring Boot/Spring Framework/Jakarta cùng một dòng tương thích, có support lifecycle?
- [ ] Chọn MVC/WebFlux theo workload và blocking dependencies, không trộn vô ý?
- [ ] Dùng Boot BOM; biết version thực tế qua dependency graph; mọi override có lý do?
- [ ] Driver, migrations, OpenAPI, Security, Test và observability đã xác minh compatibility?
- [ ] JWT validation và quyền tenant/resource được kiểm thử, không chỉ khai báo starter?
- [ ] API giữ status/header/JSON/error/authorization sau upgrade?
- [ ] CI có build sạch, dependency/security scan, contract tests, DB tests và canary/rollback?

**Kết luận:** Chọn **platform có hỗ trợ**, không ghép các JAR mới nhất. Dùng BOM, hiểu ranh giới Spring/Jakarta và kiểm chứng bằng build, HTTP contract/security tests cùng staging. Chỉ hoàn tất nâng cấp khi API vẫn đúng hợp đồng và vận hành ổn định.
