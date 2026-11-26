# Chọn dòng Spring Security phù hợp với Spring Framework và Spring Boot

> **Chương:** Cấu hình và phiên bản  
> **Phạm vi:** SPRING_SECURITY_HTTP_PROTECTION — các lớp phòng vệ HTTP và trình duyệt trong Spring Security cho Servlet và Reactive, gồm CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và session.  
> **Mốc đối chiếu phiên bản:** 26/11/2026. Các số phiên bản và vòng đời hỗ trợ có thể thay đổi; khi tạo hoặc nâng cấp dự án, luôn kiểm tra lại tài liệu của phiên bản Spring Boot cụ thể.

## 1. Vì sao chọn đúng bộ phiên bản là một quyết định bảo mật?

Spring Security không vận hành độc lập với phần còn lại của ứng dụng web. Một yêu cầu HTTP đi qua nhiều lớp:

```text
Trình duyệt / client
    |
    v
Reverse proxy / TLS / forwarded headers
    |
    v
Servlet container (Tomcat, Jetty) hoặc Reactive server (Reactor Netty)
    |
    v
Spring Framework (Web MVC / WebFlux)
    |
    v
Spring Security (filter chain / web filter chain)
    |-- CSRF, CORS
    |-- Security headers, CSP, HSTS
    |-- HTTP firewall / request matching
    |-- Authentication, authorization, session
    v
Controller / handler / nghiệp vụ
```

Một cấu hình CSRF hoặc HTTP firewall đúng về cú pháp vẫn có thể không đạt mục tiêu nếu các thư viện Spring không tương thích. Ví dụ, khác biệt trong cách đối sánh URL giữa các dòng Spring Security có thể khiến một quy tắc bảo vệ không áp dụng cho request mà lập trình viên tưởng đã được bảo vệ. Việc nâng cấp cũng có thể thay đổi API cấu hình, yêu cầu Java, Jakarta Servlet và cơ chế quản lý phiên.

**Nguyên tắc quan trọng nhất:** nếu ứng dụng dùng **Spring Boot**, hãy **chọn dòng Spring Boot trước**, để dependency management của Boot chọn các dòng Spring Framework và Spring Security tương ứng. Chỉ ghi đè phiên bản Spring Security sau khi có lý do cụ thể và đã kiểm chứng tổ hợp thu được.

### Phân biệt ba thành phần

| Thành phần | Vai trò khi bảo vệ HTTP | Ai thường quản lý phiên bản? |
| --- | --- | --- |
| **Spring Boot** | Cung cấp starter, auto-configuration, phiên bản thư viện được kiểm thử cùng nhau và cấu hình máy chủ web | `spring-boot-starter-parent`, `spring-boot-dependencies` BOM hoặc Spring Boot Gradle plugin |
| **Spring Framework** | Cung cấp Servlet/MVC hoặc WebFlux, request mapping, HTTP API, hạ tầng bean và web server integration | Thường do Spring Boot quản lý |
| **Spring Security** | Cung cấp chuỗi filter bảo mật, chống CSRF, tích hợp CORS, headers, firewall, xác thực, phân quyền và session | Thường do Spring Boot quản lý; nếu không có Boot thì dùng Spring Security BOM |

Một phiên bản có dạng `MAJOR.MINOR.PATCH`. **Major** có thể thay đổi API/hành vi; **minor** bổ sung tính năng; **patch** là nơi có các bản sửa lỗi và bản vá bảo mật. Không coi việc chạy được hoặc biên dịch thành công là bằng chứng rằng mọi lớp phòng vệ hoạt động đúng.

## 2. Ma trận phiên bản nên dùng để ra quyết định

Bảng sau ghi **dòng phiên bản được Spring Boot quản lý theo từng thế hệ**, không phải tuyên bố mọi tổ hợp bất kỳ cùng hàng đều có thể thay đổi độc lập:

| Spring Boot | Spring Framework | Spring Security | Java tối thiểu | Cách hiểu |
| --- | --- | --- | --- | --- |
| **2.7.x** | 5.3.x | 5.7.x mặc định (có thể dùng 5.8.x để chuẩn bị di chuyển) | 8 | Hệ `javax.servlet` cũ; dành cho bảo trì/chuyển đổi |
| **3.0.x** | 6.0.x | 6.0.x | 17 | Bước chuyển sang `jakarta.servlet` |
| **3.1.x** | 6.0.x | 6.1.x | 17 | Thế hệ Boot 3 đầu |
| **3.2.x** | 6.1.x | 6.2.x | 17 | Dòng Boot 3 và Framework 6.1 |
| **3.3.x** | 6.1.x | 6.3.x | 17 | Dòng Boot 3 trước Framework 6.2 |
| **3.4.x** | 6.2.x | 6.4.x | 17 | Dòng Boot 3 cũ |
| **3.5.x** | 6.2.x | 6.5.x | 17 | Dòng cuối của Security 6.x, là bước đệm lên 7.x |
| **4.0.x** | 7.0.x | 7.0.x | 17 | Bước chuyển lên Framework 7/Security 7 |
| **4.1.x** | 7.0.x | 7.1.x | 17 | Tiếp tục thế hệ Boot 4 |
| **4.2.x** | 7.1.x | 7.2.x | 17 | Dòng mới phát hành ngày 19/11/2026 |

Trong bảng, chữ `x` chỉ bản vá cùng dòng; **không** có nghĩa nên dùng patch đầu tiên. Lấy patch mới nhất mà nhà cung cấp còn hỗ trợ và kiểm tra bản BOM thực sự được quản lý bởi **phiên bản Boot đang chạy**.

Ví dụ đã được công bố:

- **Spring Boot 4.2.0** đi kèm **Spring Framework 7.1.0** và **Spring Security 7.2.0**. Spring Boot 4.2 yêu cầu **Java 17 trở lên**.
- **Spring Boot 4.1.0** đi kèm Framework **7.0.8** và Security **7.1.0** khi phát hành.
- **Spring Boot 4.0** chuyển sang Framework **7.0** và Security **7.0**.
- **Spring Boot 3.5** thuộc thế hệ Framework **6.2** và Security **6.5**; **Spring Security 6.5 là dòng cuối của thế hệ 6.x**.
- **Spring Boot 2.7.18** quản lý Spring Security **5.7.11**; Security **5.8** là bước hỗ trợ chuẩn bị di chuyển lên Security 6, không phải phiên bản do Boot 2.7.18 mặc định chọn.

**Vòng đời hỗ trợ là một tiêu chí riêng với khả năng chạy.** Theo thông báo Spring, Boot **3.5.16 (25/06/2026)** là bản OSS cuối cùng của dòng 3.5.x. Vì vậy, một hệ thống đang ở 3.5 có thể dùng dòng này làm **bước trung gian khi di chuyển**, nhưng dự án mới cần bản vá cộng đồng nên ưu tiên dòng Boot 4 còn được hỗ trợ. Khi vận hành lâu dài, đối chiếu [Spring Support Policy](https://spring.io/support-policy) và thông báo kết thúc hỗ trợ của **đúng dòng**; nếu dùng hỗ trợ thương mại, kế hoạch vá lỗi có thể khác.

### Những tổ hợp không nên tự ghép

| Tổ hợp | Vấn đề |
| --- | --- |
| Boot 2.7 + Security 6.x/7.x | Thế hệ Java EE `javax.*` so với Jakarta `jakarta.*` và thay đổi framework lớn |
| Boot 3.x + Security 7.x | Security 7 thuộc thế hệ Framework 7 và có thay đổi tương thích; không được coi là cách nâng cấp “chỉ một dependency” an toàn |
| Boot 4.0 + Framework 6.2 | Không đáp ứng nền tảng Framework 7 mà Boot 4 yêu cầu |
| Spring Security modules 6.5.x và 7.2.x trộn trong cùng ứng dụng | Nguy cơ `NoSuchMethodError`, `NoClassDefFoundError` hoặc lỗi runtime tinh vi |
| Boot 4.2 + JDK 11 | Boot 4.2 yêu cầu tối thiểu Java 17 |

Nếu đang dùng `spring-security-web` phiên bản 7.2 mà `spring-security-config` vẫn là 7.1, hãy sửa **quy tắc quản lý dependency**, không chữa bằng cách thêm từng JAR rời rạc.

## 3. Quy trình chọn phiên bản cho dự án mới và dự án đang chạy

### Dự án mới

1. **Chọn một Spring Boot GA còn được hỗ trợ**; tại thời điểm bài viết, Boot 4.2.0 là ví dụ phù hợp.
2. **Kiểm tra JDK, build tool, servlet container và các starter ngoài Spring**. Với Boot 4.2, tài liệu yêu cầu tối thiểu Java 17, Spring Framework 7.1, Servlet 6.1 cho triển khai Servlet; kiểm tra các thư viện phụ trợ như Spring Cloud, Spring Session, SDK và driver.
3. **Dùng starter phù hợp với mô hình HTTP**: Spring MVC/Servlet dùng `spring-boot-starter-webmvc`; WebFlux/Reactive dùng `spring-boot-starter-webflux`. Cả hai có thể sử dụng `spring-boot-starter-security` nhưng mã cấu hình bảo mật khác nhau.
4. **Để Boot quản lý phiên bản** của các thư viện Spring, chỉ bổ sung module Security thực sự cần: OAuth2 Client, Resource Server, SAML2, v.v.
5. **Thử request và chính sách bảo mật thực tế** trước khi triển khai: request không xác thực, CSRF, preflight CORS, headers, firewall, session và proxy HTTPS.

### Dự án hiện hữu

Đầu tiên ghi lại:

- Phiên bản Boot đang chạy, Java tại lúc biên dịch và chạy, hình thức đóng gói JAR/WAR.
- Phiên bản **đã được resolve** của `spring-core`, `spring-web`, `spring-security-config`, `spring-security-web` và `spring-security-test`.
- Ứng dụng dùng **Servlet** (`SecurityFilterChain`) hay **Reactive** (`SecurityWebFilterChain`), có nhiều filter chain không, có OAuth2/SAML/LDAP/session tập trung không.
- Sự khác nhau giữa đường dẫn gốc ứng dụng, forwarded headers, servlet path và path matcher; danh sách URL được phép truy cập công khai.
- Các lớp bảo vệ cần giữ: CSRF cho thao tác có cookie, CORS allowlist, CSP/header, HSTS trên HTTPS, kiểm soát session và HTTP firewall.

Sau đó mới chọn tuyến di chuyển tương ứng. Không thể kết luận cấu hình được bảo toàn chỉ vì các số major khớp nhau.

## 4. Thiết lập dependency đúng cách với Spring Boot

### 4.1. Maven: để Spring Boot chọn cả bộ thư viện

Ví dụ dự án Servlet Spring MVC dùng **Spring Boot 4.2.0**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.2.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>http-protection-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc-test</artifactId>
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
```

Không ghi thêm `<version>7.2.0</version>` vào từng `spring-security-*`: BOM của Boot 4.2.0 đã quản lý phiên bản đó. Từ Boot 4, starter `spring-boot-starter-webmvc` là lựa chọn dành cho Spring MVC; starter cũ `spring-boot-starter-web` vẫn tồn tại ở 4.2 nhưng đã được đánh dấu deprecated.

### 4.2. Gradle: vẫn áp dụng cùng nguyên tắc

Với dự án đã cấu hình Spring Boot Gradle plugin và cơ chế dependency management, phần `dependencies` tương ứng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-webmvc-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-security-test'
}
```

Nếu dùng Gradle với native BOM platform thay cho dependency-management plugin, import `org.springframework.boot:spring-boot-dependencies` đúng phiên bản Boot rồi mới khai báo dependency không có version. Không thêm hai cơ chế quản lý cạnh tranh mà chưa kiểm tra kết quả resolve.

### 4.3. Khi nào có thể ghi đè một bản patch của Spring Security?

Một tình huống hợp lý là **bản vá lỗi bảo mật đã phát hành trong cùng major/minor nhưng bản Spring Boot dự án đang dùng chưa kịp quản lý bản vá đó**. Trong Maven dựa trên `spring-boot-starter-parent`, Spring Security cho phép dùng property:

```xml
<properties>
    <!-- Minh họa: chỉ đổi sau khi kiểm tra compatibility và dependency tree -->
    <spring-security.version>7.1.3</spring-security.version>
</properties>
```

Ví dụ trên minh họa cách cấu hình property, **không** phải khuyến nghị pin `7.1.3` cho Boot 4.2. Khi dùng Gradle Spring dependency-management plugin, property tương tự có thể khai báo:

```groovy
ext['spring-security.version'] = '7.1.3'
```

Quy tắc khi ghi đè:

1. Chỉ chọn phiên bản được Spring phát hành cho **dòng tương thích**, ưu tiên cập nhật patch Boot trước khi override.
2. Đảm bảo tất cả `org.springframework.security` modules thuộc cùng dòng và bản vá; kiểm tra sự tương thích với Framework mà BOM quản lý.
3. Kiểm tra bản vá CVE có liên quan tới cấu hình đang dùng (SAML, OAuth2, request cache, v.v.).
4. Ghi lý do và ngày bỏ override sau khi Boot BOM đã cập nhật, tránh tích lũy các bản pin lâu ngày.

**Không nâng Boot 3.5 từ Security 6.5 lên 7.2 bằng property override**: đó là thay đổi thế hệ tương thích, cần nâng cả Boot/Framework theo lộ trình chính thức.

## 5. Không dùng Spring Boot: tự quản lý BOM nhất quán

Nếu triển khai một ứng dụng Spring Framework thủ công (không dùng Boot), cần tự quản lý các dòng tương thích. Ví dụ cho Maven với **Security 7.2.0 / Framework 7.1.0**:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-framework-bom</artifactId>
            <version>7.1.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-bom</artifactId>
            <version>7.2.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-config</artifactId>
    </dependency>
</dependencies>
```

`spring-security-bom` giữ phiên bản các module Spring Security đồng bộ; `spring-framework-bom` giữ các module Spring Framework đồng bộ. Cấu hình này **chưa** thay thế các phụ thuộc MVC/WebFlux, runtime server, logging và test mà ứng dụng thực tế cần; bản thân việc import BOM cũng không bật bảo vệ web.

## 6. Chọn đúng API cấu hình cho Servlet và Reactive

**Version compatible** chưa có nghĩa **API đúng stack**. Spring MVC sử dụng servlet filters; WebFlux sử dụng reactive web filters. Hai cách cấu hình dưới đây dành cho các dòng Spring Security hiện đại (Security 6.5/7.x), minh họa nguyên tắc giữ các lớp phòng vệ cần thiết.

### 6.1. Servlet / Spring MVC: `SecurityFilterChain`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .csrf(Customizer.withDefaults())
            .cors(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
                    )
                )
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

- `authorizeHttpRequests` chọn quy tắc cho từng endpoint; đường dẫn công khai phải được rà soát, nhất là khi có nhiều `SecurityFilterChain` hoặc servlet path.
- `csrf(Customizer.withDefaults())` giữ chính sách mặc định; nếu ứng dụng dùng session/cookie và gửi POST/PUT/PATCH/DELETE từ trình duyệt, request cần CSRF token. Không tắt CSRF chỉ để một bài kiểm thử POST trả về 200.
- `cors(Customizer.withDefaults())` kích hoạt tích hợp CORS với nguồn cấu hình được cung cấp (chẳng hạn `CorsConfigurationSource`). Nó **không tự tạo danh sách origin được phép**; cần cấu hình policy phù hợp.
- `headers(...contentSecurityPolicy(...))` minh họa việc thêm CSP. Spring Security không tự phát sinh CSP đủ dùng cho mọi ứng dụng. Policy minh họa có thể cần nới có kiểm soát cho script, CSS, CDN và ứng dụng thực.

### 6.2. Reactive / WebFlux: `SecurityWebFilterChain`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .csrf(Customizer.withDefaults())
            .cors(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives("default-src 'self'; object-src 'none'")
                )
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Đây là ví dụ **riêng** cho ứng dụng WebFlux, không thêm song song hai bean cấu hình Servlet và Reactive vào một ứng dụng rồi kỳ vọng cả hai sẽ kiểm soát mọi request. Nếu có cả Spring MVC và WebFlux trên classpath, cần kiểm tra **web application type** mà Spring Boot thực sự chọn.

| Nhu cầu | Servlet / MVC | Reactive / WebFlux |
| --- | --- | --- |
| Filter bảo mật | `SecurityFilterChain` / `HttpSecurity` | `SecurityWebFilterChain` / `ServerHttpSecurity` |
| Quy tắc URL | `authorizeHttpRequests` và `requestMatchers` | `authorizeExchange` và `pathMatchers` |
| Cấu hình CSRF/CORS/headers | Servlet security DSL | Reactive security DSL |
| Kiểm thử request | `MockMvc` + `spring-security-test` | `WebTestClient` + reactive security test |
| Thành phần phòng vệ request | Servlet `HttpFirewall` | Reactive `ServerWebExchangeFirewall` |

Khi đổi dòng Security, đọc migration guide **đúng hệ Servlet hoặc Reactive**. Không suy ra rằng một thay đổi của Servlet `RequestMatcher` cũng áp dụng y nguyên cho WebFlux.

## 7. Những thay đổi cần kiểm tra khi nâng từ Security 5 lên 6 và từ 6 lên 7

### 7.1. Từ Boot 2.7 / Security 5.x lên Boot 3.x / Security 6.x

- **Java:** Boot 3 yêu cầu Java 17 trở lên, không còn tương thích runtime Java 8/11.
- **Namespace:** chuyển từ `javax.servlet.*` sang `jakarta.servlet.*`, kể cả filter tự viết và các thư viện có liên quan.
- **Security configuration:** chuyển sang bean `SecurityFilterChain` và Lambda DSL; loại bỏ dần cách dựa trên `WebSecurityConfigurerAdapter` đã bị xóa trong Security 6.
- **Request matching:** kiểm tra API matcher và đường dẫn servlet, thứ tự filter chains, static resources, endpoint cho phép truy cập công khai.
- **Kiểm thử trình duyệt:** xác minh CSRF, redirect đăng nhập/đăng xuất, cookie, session và response headers sau khi đổi Jakarta stack.

Lộ trình tài liệu Spring khuyến nghị: đưa ứng dụng về **Boot 2.7 mới nhất**, có thể chuẩn bị bằng **Security 5.8**, sau đó nâng lên **Boot 3 / Security 6**; nâng các thư viện phụ trợ theo Java/Jakarta trước khi kiểm thử.

### 7.2. Từ Boot 3.5 / Security 6.5 lên Boot 4 / Security 7

Spring Security khuyên dùng **Security 6.5** để chuẩn bị các breaking changes trước khi chuyển sang 7.0. Những điểm đáng chú ý:

- **Bắt buộc Lambda DSL ở Security 7**; kiểu gọi `http.authorizeHttpRequests().and().formLogin()` cũ không còn là cú pháp tương thích.
- **Request matching / HTTP firewall:** xem lại cách đối sánh đường dẫn và hành vi khi request có URL bất thường; kiểm thử đường dẫn có encoding, servlet path và nhiều filter chain.
- **Hệ sinh thái Jakarta và web server:** Boot 4 dùng Framework 7, Servlet 6.1/Jakarta EE 11 ở cấu hình Servlet hiện hành; cần kiểm tra container deploy, filter và thư viện liên quan.
- **Jackson 3:** Boot 4 và Security 7 dùng hệ sinh thái Jackson 3; đặc biệt kiểm tra session/remember-me/OAuth2 và các phần có serialize đối tượng Security. Hướng dẫn di chuyển Security 7 nêu thay đổi từ `SecurityJackson2Modules` sang `SecurityJacksonModules`.
- **Spring Security module:** Spring Authorization Server được tích hợp vào Spring Security 7; rà soát dependency và cấu hình nếu dự án từng dùng module độc lập.
- **HTTP protection không được bỏ qua khi refactor:** xác minh lại CSP, CORS, HSTS, CSRF, mặc định header, logout, session và firewall. Một lần xóa API deprecated có thể thay đổi cả hành vi security chain.

Với ứng dụng lớn, một tuyến di chuyển có kiểm soát thường là:

```text
Boot 2.7 / Security 5.7
       |
       v
Security 5.8 (chuẩn bị tương thích, nếu cần)
       |
       v
Boot 3.x / Security 6.x
       |
       v
Boot 3.5 / Security 6.5 (bước chuẩn bị 7.0)
       |
       v
Boot 4.0 / Security 7.0
       |
       v
Boot 4.2 / Security 7.2 (đích ví dụ, cập nhật bản vá mới nhất)
```

Đây là **các điểm kiểm tra migration**, không yêu cầu phát hành production qua từng bản trung gian. Boot 3.5 đã hết hỗ trợ OSS nên nếu dùng trong quá trình nâng cấp phải tính đến thời gian chuyển đổi, bản vá và chính sách hỗ trợ.

## 8. Kiểm tra phiên bản thực tế: đọc dependency graph, không đoán từ `pom.xml`

Một dự án có thể khai báo Boot 4.2 nhưng chạy với thư viện cũ vì parent, BOM khác, `dependencyManagement`, Gradle resolution strategy hoặc dependency có version tường minh.

**Maven:**

```bash
./mvnw dependency:tree -Dincludes=org.springframework,org.springframework.security
./mvnw help:effective-pom
```

**Gradle:**

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
```

Trên Windows, có thể gọi wrapper bằng `mvnw.cmd` và `gradlew.bat`. Nếu không có wrapper thì dùng `mvn` hoặc `gradle` đã cài.

Khi đọc kết quả, đối chiếu ít nhất:

| Artifact | Điều cần xác minh |
| --- | --- |
| `org.springframework.boot:spring-boot` | Có đúng dòng Boot được chọn? |
| `org.springframework:spring-core`, `spring-web`, `spring-webflux` | Có cùng thế hệ/dòng Framework mà Boot quản lý? |
| `org.springframework.security:spring-security-config` | Có cùng dòng với các Security module khác? |
| `org.springframework.security:spring-security-web`, `spring-security-core` | Có bị pin về patch cũ hoặc lẫn major? |
| `org.springframework.security:spring-security-test` | Có tương thích với runtime Security để test đúng hành vi? |
| `org.springframework.security:spring-security-oauth2-*` (nếu dùng) | Có đi cùng BOM và đúng stack không? |

Kiểm tra cả `runtimeClasspath` và `testRuntimeClasspath`, vì code có thể compile nhưng khi chạy test mới xuất hiện lỗi do phiên bản không đồng bộ.

## 9. Bảo vệ HTTP phải được kiểm thử lại sau khi đổi dòng

Ma trận dưới đây dùng để xác định việc nâng cấp có duy trì **mục tiêu bảo vệ** hay không:

| Kịch bản | Kiểm thử | Dấu hiệu cần điều tra |
| --- | --- | --- |
| URL riêng tư không xác thực | GET `/account` khi chưa đăng nhập | Trả 200 và lộ dữ liệu thay vì chuyển tới đăng nhập/401 |
| Quyền truy cập | USER gọi URL ADMIN | Trả 200 thay vì 403; matcher không chạy như dự kiến |
| CSRF | POST bằng cookie session nhưng không có CSRF token, sau đó gửi token hợp lệ | Cả hai cùng thành công hoặc token hợp lệ luôn 403 |
| CORS | Gửi preflight `OPTIONS` với origin/headers được phép và không được phép | Origin lạ được cho phép hoặc preflight hợp lệ bị chặn |
| CSP / security headers | Xem header trên trang HTML | Thiếu policy bắt buộc hoặc policy chặn script hợp lệ |
| HSTS | Xem `Strict-Transport-Security` trên response **HTTPS** | Không có header vì proxy/TLS hoặc kỳ vọng sai khi test HTTP |
| HTTP firewall | Request với URL mã hóa bất thường, path traversal, delimiter | Request nguy hiểm đi qua hoặc bị từ chối ngoài dự kiến |
| Session | Đăng nhập, đổi user, logout, hết hạn phiên | Session fixation, cookie thiếu thuộc tính hoặc logout không vô hiệu hóa phiên |

**Ví dụ kiểm thử Servlet CSRF với MockMvc:**

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Với endpoint /submit yêu cầu CSRF và user đã được xác thực:
mockMvc.perform(post("/submit"))
       .andExpect(status().isForbidden());

mockMvc.perform(post("/submit").with(csrf()))
       .andExpect(status().is2xxSuccessful());
```

Trạng thái mong đợi của ví dụ phụ thuộc việc endpoint tồn tại và user đã được cấp quyền; trong một ứng dụng thật cần cung cấp fixture xác thực và handler phù hợp. Khi một request chưa xác thực, có thể nhận redirect tới trang login hoặc 401 thay vì 403, tùy cấu hình entry point. Với WebFlux, dùng `WebTestClient` và `SecurityMockServerConfigurers.csrf()` để kiểm tra tương tự.

Đừng đánh đồng **CORS** với **CSRF**: CORS quyết định JavaScript từ origin nào được đọc/tương tác theo chính sách trình duyệt; CSRF ngăn việc website khác lợi dụng cookie/session của người dùng để gửi yêu cầu thay đổi trạng thái. Cũng đừng đánh đồng **CSP** với các header mặc định: Spring Security **không thiết lập CSP mặc định** phù hợp cho từng ứng dụng, vì vậy chính sách phải do nhóm phát triển xác định.

### Khi có reverse proxy hoặc load balancer

Trong production, proxy có thể kết thúc TLS và chuyển tiếp HTTP vào ứng dụng. Điều này ảnh hưởng việc Spring xác định request có an toàn (HTTPS) hay không, phát sinh redirect, thuộc tính cookie và HSTS. Khi nâng Boot/Framework, xác minh chiến lược xử lý `Forwarded`/`X-Forwarded-*`, danh sách proxy được tin cậy và kết quả response **qua cổng public**. Không dựa chỉ vào response khi gọi cổng backend nội bộ.

## 10. Sự cố thường gặp và cách chẩn đoán

### Trường hợp A — `NoSuchMethodError` sau khi nâng một dependency Security

**Hiện tượng:** ứng dụng compile nhưng khởi động hoặc xử lý request lỗi tại lớp Spring.

**Nghi vấn:** `spring-security-web`, `spring-security-config` và `spring-core` đang thuộc các dòng khác nhau.

**Cách xử lý:** kiểm tra `dependency:tree` hoặc `dependencyInsight`; xóa pin phiên bản không cần thiết; để Boot BOM quản lý trở lại; chỉ chọn version override có kiểm chứng rồi test smoke.

### Trường hợp B — POST trả 403 sau khi bật Security

**Hiện tượng:** GET vẫn chạy nhưng POST bị từ chối dù user có quyền.

**Nghi vấn:** CSRF token không được gửi, hết hạn session, request đi qua proxy sai origin, hoặc chính sách authorization.

**Cách xử lý:** phân biệt lỗi `InvalidCsrfTokenException`/`MissingCsrfTokenException` với lỗi phân quyền; thử POST có token bằng `spring-security-test`; rà soát cookie và session. Không vô hiệu hóa CSRF toàn cục chỉ để xóa 403.

### Trường hợp C — Preflight CORS trả 401/403

**Hiện tượng:** trình duyệt báo lỗi CORS trước khi gửi request thật.

**Nghi vấn:** cấu hình `CorsConfigurationSource` không khớp origin/method/header, hoặc xử lý CORS chưa được tích hợp vào security chain.

**Cách xử lý:** thử `OPTIONS` có `Origin` và `Access-Control-Request-Method`, kiểm tra response headers và thứ tự filter; chỉ cho phép origin/credentials phù hợp với client.

### Trường hợp D — URL nhạy cảm bất ngờ truy cập được sau migration

**Hiện tượng:** một URL có dấu slash, encoded path hoặc servlet path khác thường vượt qua quy tắc dự kiến.

**Nghi vấn:** thay đổi cách tạo `RequestMatcher`, nhiều chain có thứ tự ưu tiên khác nhau, firewall customization hoặc proxy rewrite.

**Cách xử lý:** ghi các URL phải từ chối thành test, kiểm tra `securityMatcher` và `requestMatchers`, danh sách `SecurityFilterChain`, URL khi đi qua proxy; không nới rộng firewall chỉ để vượt lỗi mà chưa hiểu nguyên nhân.

### Trường hợp E — Thiếu HSTS/CSP sau nâng cấp

**Hiện tượng:** kiểm tra header production thấy thiếu `Strict-Transport-Security` hoặc `Content-Security-Policy`.

**Nghi vấn:** HSTS chỉ được gửi trên HTTPS hợp lệ; proxy không truyền trạng thái HTTPS; CSP chưa được cấu hình hoặc policy không nằm trong security chain đang match.

**Cách xử lý:** kiểm tra response tại HTTPS endpoint public, cấu hình trusted forwarded headers và header writer; test riêng cho mỗi chain. Với CSP, có thể triển khai `Content-Security-Policy-Report-Only` trước khi enforce để phát hiện tài nguyên cần thiết.

## 11. Checklist chọn phiên bản trước khi merge hoặc triển khai

- [ ] Chọn Boot GA còn được hỗ trợ và xác định **dòng Framework/Security do BOM quản lý**.
- [ ] JDK, build tool, container Servlet hoặc Reactive server đáp ứng yêu cầu.
- [ ] Không trộn các phiên bản Spring Security khác major/minor; các module Security và Framework resolve nhất quán.
- [ ] Dùng đúng starter cùng API `SecurityFilterChain` hoặc `SecurityWebFilterChain`.
- [ ] Nếu override bản vá, có CVE/lý do cụ thể, kiểm chứng dependency graph và kế hoạch bỏ override.
- [ ] Migration guide đúng tuyến 5→6 hoặc 6→7 đã được áp dụng; API cũ và namespace cũ đã được xử lý.
- [ ] Kiểm thử anonymous/authorized, CSRF, CORS, headers/CSP, HTTPS/HSTS, firewall, session/logout với request thực hoặc integration test.
- [ ] Kiểm tra cấu hình proxy và policy trên response production, không chỉ kiểm tra máy local.

## 12. Bài tập tình huống

**Tình huống 1.** Ứng dụng đang dùng Boot 3.5, Security 6.5, Java 17; nhóm muốn dùng Security 7.2 vì có chức năng mới. Có nên chỉ thêm `<spring-security.version>7.2.0</spring-security.version>`?

**Gợi ý:** Không. Security 7.2 là thế hệ Framework 7; hãy chuẩn bị thay đổi ở Security 6.5, lên dòng Boot 4 phù hợp (Boot 4.2 quản lý Security 7.2), rồi kiểm tra API, Jackson, servlet stack và các lớp phòng vệ HTTP.

**Tình huống 2.** Dự án mới dùng Spring Boot 4.2.0 và có ba dependency `spring-security-core`, `spring-security-web`, `spring-security-config` gắn trực tiếp version 7.0.0.

**Gợi ý:** Bỏ những version gắn tay nếu không có lý do đặc biệt; dùng `spring-boot-starter-security` để Boot quản lý Security 7.2.0 tại thời điểm Boot 4.2.0 phát hành. Xem dependency graph sau khi thay.

**Tình huống 3.** Sau khi nâng Spring Security, endpoint POST trên WebFlux trả 403; dự án đang kiểm thử bằng `MockMvc` và tìm class `HttpSecurity`.

**Gợi ý:** Xác định lại web stack; WebFlux dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và `WebTestClient`. Kiểm tra CSRF token/authorization bằng reactive test support; không suy từ kết quả của cấu hình Servlet.

## Tài liệu chính thức để đối chiếu

1. [Spring Boot 4.2.0 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.2.0-Release-Notes) — cặp Framework 7.1.0 / Security 7.2.0.
2. [Spring Boot 4.1 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.1-Release-Notes) và [Spring Boot 4.0 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Release-Notes) — bước chuyển thế hệ Boot 4.
3. [Spring Boot System Requirements](https://docs.spring.io/spring-boot/reference/system-requirements.html) — Java, Spring Framework, công cụ build và Servlet container cho bản hiện hành.
4. [Spring Boot Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html) và [Managed Dependency Coordinates](https://docs.spring.io/spring-boot/reference/appendix/dependency-versions/coordinates.html) — BOM và phiên bản dependency cụ thể.
5. [Getting Spring Security](https://docs.spring.io/spring-security/reference/getting-spring-security.html) — starter, BOM, versioning và override.
6. [Migrating to Spring Security 7.0](https://docs.spring.io/spring-security/reference/migration/) và [Preparing for 7.0 từ Security 6.5](https://docs.spring.io/spring-security/reference/6.5/migration-7/index.html) — hướng dẫn nâng cấp.
7. [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide) — tuyến Java 17/Jakarta/Security 5.8→6.
8. [Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html), [Servlet Security Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html), [Reactive WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — hành vi bảo vệ và API cho từng stack.
9. [Spring Boot 3.5.16 — End of OSS Support](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/) và [Spring Support Policy](https://spring.io/support-policy) — vòng đời hỗ trợ.

**Điểm tự kiểm tra:** người học phải giải thích được vì sao **Boot 4.2 / Framework 7.1 / Security 7.2** là một bộ phù hợp, cách kiểm tra phiên bản đã được resolve, lý do không ghép Security 7 vào Boot 3 và cách chứng minh CSRF/CORS/CSP/HSTS/firewall/session vẫn hoạt động sau khi nâng cấp.
