# Ánh xạ scope thành quyền SCOPE_ và tùy chỉnh JwtGrantedAuthoritiesConverter

**Module:** Spring Security – reactive (WebFlux)  
**Phần:** Resource Server JWT  
**Trọng tâm:** Spring Security chuyển các scope từ JWT access token thành `GrantedAuthority` có tiền tố `SCOPE_` như thế nào; cách chỉnh claim nguồn, prefix, delimiter bằng `JwtGrantedAuthoritiesConverter`; cách nối converter đồng bộ vào luồng reactive bằng `ReactiveJwtAuthenticationConverterAdapter`; test đúng sự khác nhau giữa xác thực Bearer và phân quyền 401/403.

**Kết luận:** Trong Spring Security Resource Server JWT, claim `scope` (thường là chuỗi cách nhau bằng khoảng trắng) hoặc `scp` (thường là mảng các chuỗi) được chuyển thành authorities dạng `SCOPE_xxx`. Ví dụ `scope="reports.read reports.write"` tạo `SCOPE_reports.read` và `SCOPE_reports.write`. Rule `hasAuthority("SCOPE_reports.read")` cho phép khi JWT hợp lệ **và** chứa đúng scope. `JwtGrantedAuthoritiesConverter` cho phép đổi claim được đọc, tiền tố và biểu thức phân tách. Với WebFlux, nếu bọc converter dạng `JwtAuthenticationConverter` (đồng bộ, không blocking) bằng `ReactiveJwtAuthenticationConverterAdapter` rồi gắn vào `oauth2ResourceServer().jwt()`, kết quả `Authentication` reactive sẽ mang những authorities đó.

Quan trọng: **Ánh xạ quyền không xác minh chữ ký JWT.** `ReactiveJwtDecoder` phải kiểm token (signature, issuer, expiry/not-before và audience nếu API yêu cầu) trước khi converter đọc claims; `SecurityWebFilterChain` sau đó mới kiểm authority. Không lấy một JWT chưa được xác minh rồi tin `scope`/`roles` trong payload.

## 1. Tổng quan pipeline từ Authorization header tới quyết định quyền

```text
HTTP GET /api/reports
Authorization: Bearer <signed-access-token>
             |
             v
Spring Security WebFlux / bearer-token authentication
             |
             v
ReactiveJwtDecoder
  - xác minh JWS signature/key/allowed algorithm
  - kiểm iss, exp, nbf; aud theo validation của API
  - từ chối nếu JWT invalid
             |
             v
Jwt đã được xác minh
    claims: sub="alice"
            scope="reports.read reports.write"
            permissions="catalog.read,catalog.write"
             |
             v
JwtGrantedAuthoritiesConverter mặc định
   scope -> SCOPE_reports.read
            SCOPE_reports.write
             |
             +-- converter tùy chỉnh (nếu được cấu hình)
             |   permissions -> PERM_catalog.read
             |                  PERM_catalog.write
             v
JwtAuthenticationConverter
  -> JwtAuthenticationToken với Principal là Jwt
  -> Authentication.getAuthorities()
             |
             v
ReactiveJwtAuthenticationConverterAdapter
  -> Mono<AbstractAuthenticationToken>
             |
             v
ServerHttpSecurity.authorizeExchange()
   hasAuthority("SCOPE_reports.read")
          |
          +-- token thiếu/hỏng -> 401
          +-- token tốt nhưng không có quyền -> 403
          +-- token tốt và đủ quyền -> controller Mono/Flux
```

Sơ đồ chỉ mô tả trách nhiệm logic; các reactive publishers có thể phát tín hiệu ở thời điểm subscription. Việc chuyển authority là thao tác trong memory, không có lý do gọi database blocking ở converter. Nếu quyền cần tra cứu bất đồng bộ, phải dùng thiết kế authorization reactive riêng và đưa truy vấn theo principal/tenant tới nơi phù hợp.

### 1.1. Bốn tầng không nên trộn

| Tầng | Câu hỏi | API/phương thức tiêu biểu |
| --- | --- | --- |
| Bearer extraction | Request có `Authorization: Bearer ...` không? | Spring Security Bearer authentication filter/converter |
| JWT validation | Token có chữ ký và claims tin cậy không? | `ReactiveJwtDecoder` + `OAuth2TokenValidator<Jwt>` |
| Authority mapping | Claims được chuyển thành quyền Spring ra sao? | `JwtGrantedAuthoritiesConverter`, `JwtAuthenticationConverter` |
| Authorization | Request hiện tại có quyền đúng route/resource không? | `authorizeExchange`, `hasAuthority`, `@PreAuthorize` với reactive method security |

**401 Unauthorized:** Không có Bearer hợp lệ hoặc token bị từ chối trong authentication. Với Resource Server chuẩn, response thường có `WWW-Authenticate: Bearer` hoặc chi tiết lỗi phù hợp RFC 6750.

**403 Forbidden:** JWT hợp lệ đã được xác thực nhưng thiếu authority hoặc không thỏa policy. Không tự đổi `403` thành `401` hay bỏ kiểm quyền chỉ vì test thất bại.

### 1.2. Mặc định scope và scp

Spring Security nhận những tên claim phổ biến, mặc định là `scope` và `scp`. Dữ liệu đầu vào:

```json
{
  "iss": "https://idp.example.invalid",
  "sub": "alice",
  "aud": ["reports-api"],
  "scope": "reports.read reports.write"
}
```

Sau mapping mặc định, `Authentication.getAuthorities()` có:

```text
SCOPE_reports.read
SCOPE_reports.write
```

Nếu provider phát:

```json
{
  "scp": ["reports.read", "reports.write"]
}
```

thì mặc định cũng có thể ánh xạ hai scope trên. `JwtGrantedAuthoritiesConverter` thường ưu tiên claim đầu tiên trong danh sách tên đã biết có mặt, **không có nghĩa luôn hợp nhất `scope` và `scp`** khi cả hai cùng tồn tại. Tránh AS phát hai claim mâu thuẫn; chọn hợp đồng claim ổn định và test trường hợp có cả hai.

### 1.3. Quy tắc đối chiếu authority phải khớp chính xác

| JWT scope / dữ liệu đầu vào | Authority sau mapping | Rule hợp lệ |
| --- | --- | --- |
| `scope="messages.read"` | `SCOPE_messages.read` | `hasAuthority("SCOPE_messages.read")` |
| `scope="reports.read reports.write"` | `SCOPE_reports.read`, `SCOPE_reports.write` | `hasAuthority("SCOPE_reports.write")` |
| `scp=["catalog.read"]` | `SCOPE_catalog.read` | `hasAuthority("SCOPE_catalog.read")` |
| Không có scope/scp | Thường rỗng với converter mặc định | Không được tự coi là authenticated có mọi quyền |
| `scope="admin"` | `SCOPE_admin` | **Không** tự thỏa `hasRole("ADMIN")` |
| `permissions="catalog.read,catalog.write"` | Mặc định **không đọc** claim này | Cần `setAuthoritiesClaimName("permissions")` |

`hasRole("ADMIN")` theo convention Spring Security tìm authority `ROLE_ADMIN`, **khác** `SCOPE_admin` hoặc `SCOPE_ADMIN`. Scope là sự ủy quyền từ AS cho API, role có thể là mô hình quyền domain/ứng dụng; không coi chúng đồng nghĩa.

## 2. JwtGrantedAuthoritiesConverter: ba điểm tùy chỉnh quan trọng

Class:

```java
import org.springframework.security.oauth2.server.resource.authentication
    .JwtGrantedAuthoritiesConverter;
```

Dòng import trên được ngắt dòng cho dễ đọc trong tài liệu; khi đưa vào source Java thật hãy viết **một dòng**:

```java
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
```

`JwtGrantedAuthoritiesConverter` là một `Converter<Jwt, Collection<GrantedAuthority>>`, đồng bộ, không có I/O. Các setter quan trọng:

| API | Mặc định | Khi dùng |
| --- | --- | --- |
| `setAuthoritiesClaimName(String)` | Tìm claim phổ biến `scope` hoặc `scp` | Provider dùng `permissions`, `authorities` hay claim cố định khác |
| `setAuthorityPrefix(String)` | `SCOPE_` | Muốn namespace như `PERM_`; cẩn thận `ROLE_` |
| `setAuthoritiesClaimDelimiter(String)` | Regex phân tách whitespace cho string claim | Provider phát chuỗi phân tách bằng comma/semicolon; có từ Spring Security 6.1 |
| `convert(Jwt)` | Trích các scope/authorities từ claim | Test logic mapping trực tiếp không cần network |

### 2.1. Tùy chỉnh tên claim

Provider của tổ chức phát `permissions` thay vì `scope`:

```json
{
  "sub": "alice",
  "permissions": ["report.read", "report.export"]
}
```

Cấu hình:

```java
JwtGrantedAuthoritiesConverter converter =
    new JwtGrantedAuthoritiesConverter();

converter.setAuthoritiesClaimName("permissions");
// Nếu không đổi prefix:
// ["SCOPE_report.read", "SCOPE_report.export"]
```

Đây là **fragment**, không phải chương trình Java độc lập. Thay claim trong converter **không sửa JWT**, chỉ thay claim được đọc. **Khi gọi setter trên converter duy nhất, mapping mặc định từ `scope`/`scp` sẽ không tự được gộp vào**; nếu cần giữ cả hai loại, phải kết hợp hai converter theo phần 3.

### 2.2. Đổi tiền tố: SCOPE_, PERM_ và ROLE_

```java
JwtGrantedAuthoritiesConverter custom =
    new JwtGrantedAuthoritiesConverter();

custom.setAuthoritiesClaimName("permissions");
custom.setAuthorityPrefix("PERM_");
```

Với `permissions=["catalog.read"]`, authority là `PERM_catalog.read`, phải dùng `hasAuthority("PERM_catalog.read")`. Không quên sửa matcher/tests khi đổi prefix.

Có thể dùng `setAuthorityPrefix("")` để không thêm tiền tố, nhưng cần đánh giá xung đột namespace. Có thể dùng `ROLE_` nếu claim **thực sự đại diện role đáng tin cậy**, đã validate issuer, audience, tenant và role values; **không** map mọi `scope` thành role admin một cách tự động.

Ví dụ sai về semantics:

```java
JwtGrantedAuthoritiesConverter danger =
    new JwtGrantedAuthoritiesConverter();
danger.setAuthorityPrefix("ROLE_");
// Bây giờ scope "ADMIN" có thể thành ROLE_ADMIN.
// Đây không phải phép ánh xạ an toàn mặc định.
```

Muốn ánh xạ role từ custom claim, thiết kế allowlist và authorization policy tường minh, không chỉ ghép chuỗi. Phải phân biệt claims do AS đáng tin ký với header hoặc input người dùng.

### 2.3. Chuỗi claim có dấu phẩy

Nếu token mang:

```json
{
  "permissions": "catalog.read, catalog.write,report.export"
}
```

thì cần delimiter khác whitespace:

```java
JwtGrantedAuthoritiesConverter custom =
    new JwtGrantedAuthoritiesConverter();

custom.setAuthoritiesClaimName("permissions");
custom.setAuthorityPrefix("PERM_");
custom.setAuthoritiesClaimDelimiter("\\s*,\\s*");
```

`setAuthoritiesClaimDelimiter` nhận **regex**. Trong Java literal, `"\\s*,\\s*"` tạo regex khớp dấu phẩy có hoặc không có whitespace. Không dùng một ký tự dấu phẩy đơn nếu provider có spaces sau comma và bạn không trim; authority có thể thành `PERM_ catalog.write` (thừa dấu cách), rồi matcher fail dù người đọc nghĩ nó đúng.

Nếu claim là **mảng JSON các strings**, converter xử lý trực tiếp collection, không cần split bằng regex. Không cho converter nhận tùy tiện object lồng nhau hoặc string JSON serialized rồi kỳ vọng tự parse sâu; kiểu claim từ issuer phải được thống nhất và test.

## 3. Giữ scope mặc định và thêm quyền tùy chỉnh cùng lúc

Đây là trường hợp sản phẩm hay gặp: upstream Authorization Server phát `scope` dành cho OAuth2 protocol và một claim `permissions` dành cho quyền chi tiết.

Muốn:

```json
{
  "scope": "reports.read reports.write",
  "permissions": "catalog.read,catalog.write"
}
```

thành:

```text
SCOPE_reports.read
SCOPE_reports.write
PERM_catalog.read
PERM_catalog.write
```

thì **không thể** chỉ tạo một converter rồi `setAuthoritiesClaimName("permissions")`, vì như vậy sẽ không lấy hai scope mặc định. Hãy dùng **hai `JwtGrantedAuthoritiesConverter`** và gộp kết quả:

```java
JwtGrantedAuthoritiesConverter scopes =
    new JwtGrantedAuthoritiesConverter();

JwtGrantedAuthoritiesConverter permissions =
    new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("PERM_");
permissions.setAuthoritiesClaimDelimiter("\\s*,\\s*");

JwtAuthenticationConverter jwtAuthenticationConverter =
    new JwtAuthenticationConverter();

jwtAuthenticationConverter.setJwtGrantedAuthoritiesConverter(jwt -> {
    Set<GrantedAuthority> merged = new LinkedHashSet<>();
    merged.addAll(scopes.convert(jwt));       // SCOPE_...
    merged.addAll(permissions.convert(jwt));  // PERM_...
    return merged;
});
```

Đây là **fragment** cần imports; trong `SecurityConfig.java` hoàn chỉnh ở phần 6 có đủ code. `LinkedHashSet` loại duplicate authorities mà không tự thay nghĩa quyền; không thực hiện I/O blocking. `setJwtGrantedAuthoritiesConverter` **thay thế** converter mặc định của `JwtAuthenticationConverter`, nên việc gộp trong lambda phải explicit.

### 3.1. Vì sao không gom tất cả thành ROLE_?

`ROLE_ADMIN` thường đại diện role trong ứng dụng, còn `SCOPE_reports.read` biểu diễn phạm vi OAuth2 access token. Nếu AS phát `scope=admin`, việc map thành ROLE_ADMIN có thể vô tình cho token quyền tương đương user admin của hệ thống nội bộ. Ngay cả khi AS tin cậy, authorization phải xét **audience**, identity/tenant, claims và business policy.

**Cách đặt tên an toàn:** Giữ `SCOPE_` cho OAuth2 scopes; chọn `PERM_` cho claim quyền nghiệp vụ đã có hợp đồng với issuer; chỉ thêm `ROLE_` từ claim role đã review/allowlist và có ranh giới tenant rõ. Tránh map role từ email, query parameter hay custom HTTP header người dùng tự viết.

### 3.2. Scope thường không tự lọc tài nguyên theo owner

`hasAuthority("SCOPE_reports.read")` kiểm token được cấp quyền *loại thao tác*. Nó **không** chứng minh Alice được xem report của Bob hoặc tenant khác. Repository và service vẫn cần object-level/tenant checks, có thể đọc principal từ `ReactiveSecurityContextHolder` và truy vấn theo user/tenant từ token đã validate.

## 4. ReactiveJwtAuthenticationConverterAdapter và converter native reactive

**Điểm khác của WebFlux:** `ServerHttpSecurity.OAuth2ResourceServerSpec.JwtSpec.jwtAuthenticationConverter(...)` muốn một `Converter<Jwt, Mono<AbstractAuthenticationToken>>`. Trong khi `JwtAuthenticationConverter` truyền thống là converter **đồng bộ** từ Jwt thành Authentication. Spring cung cấp:

```java
new ReactiveJwtAuthenticationConverterAdapter(
    jwtAuthenticationConverter);
```

Adapter chuyển logic non-blocking thuần memory sang reactive return type; **không có nghĩa đưa blocking database call vào executor**. Không nhét lookup JDBC, `block()` hay HTTP I/O blocking vào converter. Nếu quyền thực sự cần API/bộ dữ liệu reactive, cân nhắc `ReactiveAuthorizationManager` ở lớp authorization tương ứng, hoặc thiết kế converter reactive có hợp đồng rõ.

### 4.1. Chữ ký WebFlux

```java
Converter<Jwt, Mono<AbstractAuthenticationToken>> converter =
    new ReactiveJwtAuthenticationConverterAdapter(
        jwtAuthenticationConverter);
```

Trong cấu hình:

```java
return http
    .authorizeExchange(ex -> ex
        .pathMatchers("/api/reports")
            .hasAuthority("SCOPE_reports.read")
        .anyExchange().authenticated())
    .oauth2ResourceServer(oauth -> oauth
        .jwt(jwt -> jwt.jwtAuthenticationConverter(converter)))
    .build();
```

Đây là fragment; security config đầy đủ bên dưới còn cấu hình GET/POST khác quyền, decoder, Bearer-only và CSRF scope. Không đưa trực tiếp một `JwtGrantedAuthoritiesConverter` (nó trả `Collection<GrantedAuthority>`) vào API yêu cầu converter trả `Mono<AbstractAuthenticationToken>`; cần **JwtAuthenticationConverter + adapter** hoặc `ReactiveJwtAuthenticationConverter` phù hợp.

### 4.2. Cách khác: ReactiveJwtAuthenticationConverter

`ReactiveJwtAuthenticationConverter` nhận `Converter<Jwt, Flux<GrantedAuthority>>` và trả `Mono<AbstractAuthenticationToken>`. Có thể chuyển collection converter bằng `Flux.fromIterable`:

```java
ReactiveJwtAuthenticationConverter reactive =
    new ReactiveJwtAuthenticationConverter();

reactive.setJwtGrantedAuthoritiesConverter(
    jwt -> Flux.fromIterable(scopes.convert(jwt)));
```

Đây là fragment, `scopes` là một `JwtGrantedAuthoritiesConverter` đã khai báo. Đừng nhầm API setter này với `JwtAuthenticationConverter`, vốn nhận `Converter<Jwt, Collection<GrantedAuthority>>`. Ở các ví dụ có nhiều converters kiểu synchronous, adapter giúp tái sử dụng cấu hình một cách đơn giản và đúng hợp đồng của WebFlux.

### 4.3. Đổi Authentication.getName khác đổi authorities

Mặc định principal name của `JwtAuthenticationToken` thường là claim `sub`. `JwtAuthenticationConverter.setPrincipalClaimName("preferred_username")` có thể đổi tên được trả về từ `Authentication.getName()` khi claim đó tồn tại:

```java
JwtAuthenticationConverter c = new JwtAuthenticationConverter();
c.setPrincipalClaimName("preferred_username");
```

Đây là thay đổi **tên principal**, **không** thêm scope hay role. Nếu dùng username/email để hiển thị, phải hiểu claim nào ổn định và có thể thay đổi; với multi-issuer nên dùng `iss + sub` làm khóa định danh đáng tin cậy. Đừng đổi subject key chỉ vì UX muốn hiển thị name.

## 5. Java 17 độc lập: nhìn thấy prefix với stdout cố định

Để người mới học tách logic **mapping dạng văn bản** khỏi JWT cryptography, có thể chạy một chương trình Java thuần. Nó **không phải implementation thật của Spring Security JwtGrantedAuthoritiesConverter**: không verify JWT, không xử lý `scp` array hoặc authorities trống/claim khác; nó chỉ minh họa tiền tố.

Lưu `ScopePrefixDemo.java`:

```java
import java.util.Arrays;
import java.util.List;

public class ScopePrefixDemo {

    static List<String> authorities(String scopeClaim) {
        return Arrays.stream(scopeClaim.trim().split("\\s+"))
            .filter(s -> !s.isEmpty())
            .map(s -> "SCOPE_" + s)
            .sorted()
            .toList();
    }

    public static void main(String[] args) {
        System.out.println(authorities(
            "reports.write reports.read"));
        System.out.println(authorities("catalog.read"));
        System.out.println(
            authorities("reports.read").contains("ROLE_ADMIN"));
    }
}
```

Chạy trên JDK 17+:

```bash
javac ScopePrefixDemo.java
java ScopePrefixDemo
```

**Stdout chính xác:**

```text
[SCOPE_reports.read, SCOPE_reports.write]
[SCOPE_catalog.read]
false
```

Giải thích: Prefix là một phần của authority string; `SCOPE_reports.read` không phải `ROLE_ADMIN`. Trong ứng dụng thật, chỉ chạy mapper **sau khi decoder đã xác minh JWT**.

## 6. Project Spring Boot WebFlux có JWT đã ký thật để kiểm tra scope mapping

Ta tạo một Resource Server **Bearer-only** làm bài thực hành:

| Route | HTTP method | Authority cần có | Kết quả |
| --- | --- | --- | --- |
| `/public` | GET | Public | `200 public` |
| `/api/reports` | GET | `SCOPE_reports.read` | `200 report-visible` nếu token đúng |
| `/api/reports` | POST | `SCOPE_reports.write` | `200 report-created` nếu đủ scope |
| `/api/catalog` | GET | `PERM_catalog.read` | `200 catalog-visible` nếu custom claim đủ |
| `/api/admin` | GET | `ROLE_ADMIN` | `403` nếu chỉ có scope `admin` |
| `/api/inspect` | GET | Authenticated | JSON tên principal và danh sách authority, không chứa token |

Dùng **Spring Boot 3.5.7 / Java 17+** làm mốc nhất quán cho ví dụ. Test sẽ dùng một **khóa HMAC demo** để ký JWT trong test và decoder xác minh chữ ký thật khi request vào WebFlux. Không cần IdP online. **Khóa hard-code chỉ để giáo trình localhost**: production nên dùng IdP/JWK Set qua HTTPS, asymmetric signature, quản lý audience/issuer, key rotation và bảo vệ secret.

### 6.1. Cấu trúc thư mục

```text
webflux-jwt-authorities/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/jwtauth/
    │   │   ├── JwtAuthoritiesApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── DemoController.java
    │   └── resources/application.properties
    └── test/java/demo/jwtauth/
        └── JwtAuthoritiesTests.java
```

Không trộn Servlet `spring-boot-starter-web` vào WebFlux. `spring-boot-starter-oauth2-resource-server` cung cấp các lớp resource server JWT/Jose cần thiết.

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>webflux-jwt-authorities</artifactId>
    <version>1.0.0</version>
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
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
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

`src/main/resources/application.properties`:

```properties
spring.application.name=webflux-jwt-authorities
server.port=8080
```

Vì demo khai `@Bean ReactiveJwtDecoder` để dùng khóa HMAC local, nó **không cần** issuer-uri trong properties; decoder/validator được khai trong Java. Production không bê nguyên signing key trong code này lên server thật.

### 6.2. Application class

`src/main/java/demo/jwtauth/JwtAuthoritiesApplication.java`:

```java
package demo.jwtauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JwtAuthoritiesApplication {
    public static void main(String[] args) {
        SpringApplication.run(JwtAuthoritiesApplication.class, args);
    }
}
```

### 6.3. SecurityConfig: decoder, converter ghép và route policy

`src/main/java/demo/jwtauth/SecurityConfig.java`:

```java
package demo.jwtauth;

import java.nio.charset.StandardCharsets;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverterAdapter;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {
    static final String ISSUER = "https://idp.example.invalid";
    static final String AUDIENCE = "reports-api";

    // CHỈ DÙNG TRONG DEMO/TEST. Không hard-code khóa trên production.
    static SecretKey demoKey() {
        String value =
            "only-local-demo-hs256-key-keep-out-of-production";
        return new SecretKeySpec(
            value.getBytes(StandardCharsets.UTF_8), "HmacSHA256");
    }

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withSecretKey(demoKey())
                .macAlgorithm(MacAlgorithm.HS256)
                .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Missing required audience", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audienceValidator));
        return decoder;
    }

    static JwtGrantedAuthoritiesConverter scopeAuthorities() {
        // Mặc định: scope/scp -> SCOPE_...
        return new JwtGrantedAuthoritiesConverter();
    }

    static JwtGrantedAuthoritiesConverter permissionAuthorities() {
        JwtGrantedAuthoritiesConverter permissions =
            new JwtGrantedAuthoritiesConverter();
        permissions.setAuthoritiesClaimName("permissions");
        permissions.setAuthorityPrefix("PERM_");
        permissions.setAuthoritiesClaimDelimiter("\\s*,\\s*");
        return permissions;
    }

    static Converter<Jwt, Mono<AbstractAuthenticationToken>>
            jwtAuthenticationConverter() {

        JwtGrantedAuthoritiesConverter scopes =
            scopeAuthorities();
        JwtGrantedAuthoritiesConverter permissions =
            permissionAuthorities();

        JwtAuthenticationConverter imperative =
            new JwtAuthenticationConverter();

        imperative.setJwtGrantedAuthoritiesConverter(jwt -> {
            Set<GrantedAuthority> merged = new LinkedHashSet<>();
            merged.addAll(scopes.convert(jwt));
            merged.addAll(permissions.convert(jwt));
            return merged;
        });

        // Adapter là bridge sang Mono<AbstractAuthenticationToken>
        return new ReactiveJwtAuthenticationConverterAdapter(
            imperative);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/public")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers(HttpMethod.POST, "/api/reports")
                    .hasAuthority("SCOPE_reports.write")
                .pathMatchers(HttpMethod.GET, "/api/catalog")
                    .hasAuthority("PERM_catalog.read")
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/inspect")
                    .authenticated()
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(jwt -> jwt.jwtAuthenticationConverter(
                    jwtAuthenticationConverter())))
            // Chỉ có Bearer JWT làm credential, không cookie/form/Basic.
            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            .csrf(csrf -> csrf.disable())
            .build();
    }
}
```

**Giải thích chi tiết:**

1. `ReactiveJwtDecoder` thực hiện kiểm JWT; token được ký HMAC HS256 bằng khóa demo. Validator kết hợp issuer, expiry/not-before mặc định và **audience reports-api**. Nếu thiếu/sai audience, token bị từ chối trước khi lấy scope. Trong production, token nên được kiểm theo issuer/JWKS/algorithm và audience do API định nghĩa, không dùng private secret demo.
2. `scopeAuthorities()` giữ mapping chuẩn `scope`/`scp` → `SCOPE_...`.
3. `permissionAuthorities()` đọc `permissions` với delimiter regex comma và prefix `PERM_`. Claim dạng mảng JSON cũng được hỗ trợ.
4. `LinkedHashSet` gộp hai nguồn authorities, không tự trộn `PERM_` với `SCOPE_` hoặc `ROLE_`. Token chỉ có scope vẫn hoạt động với rule `SCOPE_...`; token chỉ có permissions vẫn dùng được endpoint catalog.
5. `JwtAuthenticationConverter` tạo `JwtAuthenticationToken` với danh sách authorities; `ReactiveJwtAuthenticationConverterAdapter` đưa kết quả về contract reactive cho WebFlux.
6. Các matcher cụ thể đứng trước `anyExchange().denyAll()`. GET reports và POST reports có scope khác nhau; không nhầm `POST` với GET.
7. `/api/admin` dùng `hasRole("ADMIN")` để minh họa `scope="admin"` **không** thành `ROLE_ADMIN`. Nếu sản phẩm cần role, phải có nguồn role tin cậy và mapping riêng.
8. `NoOpServerSecurityContextRepository` tránh lưu/nạp Authentication từ WebSession vào Resource Server demo. `formLogin`/`httpBasic` bị tắt; chỉ Bearer token hợp lệ được API chấp nhận.
9. `csrf.disable()` chỉ được dùng ở demo **Bearer-header-only** không chấp nhận cookie/session/Basic làm credentials. Nếu API sau này chấp nhận JWT trong cookie hoặc browser login fallback, phải đánh giá/bật CSRF lại cho mutations.

**Không lấy `setAuthorityPrefix("ROLE_")` áp lên claim scope chỉ để test admin xanh.** Hãy chứng minh mô hình quyền domain/tenant của bạn thực sự hỗ trợ cấp role và ID token/JWT đã được validate trước khi mapping.

### 6.4. Controller: API có thể quan sát authorities nhưng không lộ token

`src/main/java/demo/jwtauth/DemoController.java`:

```java
package demo.jwtauth;

import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    public record AuthView(
        String name, List<String> authorities) {}

    @GetMapping(value = "/public",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping(value = "/api/reports",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> reports() {
        return Mono.just("report-visible");
    }

    @PostMapping(value = "/api/reports",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> createReport() {
        // Mô phỏng, không ghi database hay thực hiện side effect thật.
        return Mono.just("report-created");
    }

    @GetMapping(value = "/api/catalog",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> catalog() {
        return Mono.just("catalog-visible");
    }

    @GetMapping(value = "/api/admin",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> admin() {
        return Mono.just("admin-visible");
    }

    @GetMapping(value = "/api/inspect",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<AuthView> inspect() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> {
                Authentication auth = context.getAuthentication();
                List<String> values = auth.getAuthorities()
                    .stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList();
                return new AuthView(auth.getName(), values);
            });
    }
}
```

`/api/inspect` chỉ dùng cho **học tập/kiểm thử**. Nó cố ý **không** gửi raw token, JWT claims đầy đủ, client secret hoặc Authorization header; ngay cả authorities và principal name có thể là dữ liệu nhạy cảm trong sản phẩm nên không để endpoint debug này public ở production.

Không gọi `block()` trong controller. `ReactiveSecurityContextHolder` lấy Authentication theo Reactor Context của request, không dựa `ThreadLocal`. Handler trả `Mono` để WebFlux tự subscribe; converter ở `SecurityConfig` không cần tự `subscribe()`.

## 7. Test JWT có chữ ký thật qua HTTP với WebTestClient

Đây là điểm cần làm kỹ: `mockJwt()` của `spring-security-test` rất hữu ích để **test authorization policy**, nhưng nó có thể tạo `Authentication` mock trực tiếp, vì thế **không chứng minh** rằng `ReactiveJwtDecoder`/converter production đã chạy với Bearer JWT thật. Bài dùng **JWT ký HS256 thật bằng khóa demo** trong test, gửi header `Authorization: Bearer ...` qua server WebFlux để đi qua:

1. Bearer authentication filter;
2. `NimbusReactiveJwtDecoder` + issuer/audience/expiry/signature validators;
3. `JwtAuthenticationConverter` và `JwtGrantedAuthoritiesConverter`;
4. `ReactiveJwtAuthenticationConverterAdapter`;
5. `authorizeExchange` và controller.

Không cần kết nối IdP hoặc JWK Set URL bên ngoài. Đừng đưa HMAC secret vào frontend; fixture ở đây chỉ dành cho môi trường test.

### 7.1. File test đầy đủ

`src/test/java/demo/jwtauth/JwtAuthoritiesTests.java`:

```java
package demo.jwtauth;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

import com.nimbusds.jose.jwk.source.ImmutableSecret;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class JwtAuthoritiesTests {

    @Autowired
    WebTestClient client;

    private static String signed(Map<String, Object> claims) {
        return signed(
            claims, false, SecurityConfig.ISSUER,
            List.of(SecurityConfig.AUDIENCE),
            SecurityConfig.demoKey());
    }

    private static String signed(
            Map<String, Object> extras, boolean expired,
            String issuer, List<String> audience, SecretKey key) {

        Instant now = Instant.now();

        JwtClaimsSet.Builder claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject("alice")
            .audience(audience)
            .issuedAt(expired ? now.minusSeconds(3600) : now)
            .notBefore(expired
                ? now.minusSeconds(3500) : now.minusSeconds(5))
            .expiresAt(expired
                ? now.minusSeconds(600) : now.plusSeconds(900));

        extras.forEach(claims::claim);

        NimbusJwtEncoder encoder =
            new NimbusJwtEncoder(new ImmutableSecret<>(key));

        return encoder.encode(
            JwtEncoderParameters.from(
                JwsHeader.with(MacAlgorithm.HS256).build(),
                claims.build()))
            .getTokenValue();
    }

    private static SecretKey otherKey() {
        return new SecretKeySpec(
            "other-key-only-for-testing-32-bytes-long"
                .getBytes(StandardCharsets.UTF_8),
            "HmacSHA256");
    }

    @Test
    void publicRouteNeedsNoToken() {
        client.get().uri("/public")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void missingBearerGets401AndChallenge() {
        client.get().uri("/api/reports")
            .exchange().expectStatus().isUnauthorized()
            .expectHeader().value(HttpHeaders.WWW_AUTHENTICATE,
                s -> assertTrue(s.startsWith("Bearer")));
    }

    @Test
    void scopeStringGrantsReportRead() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth(
                signed(Map.of("scope", "reports.read"))))
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report-visible");
    }

    @Test
    void scpArrayAlsoGrantsReportRead() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth(
                signed(Map.of("scp", List.of("reports.read")))))
            .exchange().expectStatus().isOk();
    }

    @Test
    void wrongScopeReturns403Not401() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth(
                signed(Map.of("scope", "reports.write"))))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void reportWriteAcceptsWriteScopeWithoutCsrfToken() {
        client.post().uri("/api/reports")
            .headers(h -> h.setBearerAuth(
                signed(Map.of("scope", "reports.write"))))
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report-created");
    }

    @Test
    void reportWriteRejectsReadOnlyScope() {
        client.post().uri("/api/reports")
            .headers(h -> h.setBearerAuth(
                signed(Map.of("scope", "reports.read"))))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void customPermissionsClaimGrantsCatalogRead() {
        client.get().uri("/api/catalog")
            .headers(h -> h.setBearerAuth(
                signed(Map.of(
                    "permissions", "catalog.read, catalog.write"))))
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("catalog-visible");
    }

    @Test
    void customPermissionsClaimAbsentReturns403() {
        client.get().uri("/api/catalog")
            .headers(h -> h.setBearerAuth(
                signed(Map.of("scope", "reports.read"))))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void listPermissionsClaimIsAlsoSupported() {
        client.get().uri("/api/catalog")
            .headers(h -> h.setBearerAuth(
                signed(Map.of(
                    "permissions", List.of("catalog.read")))))
            .exchange().expectStatus().isOk();
    }

    @Test
    void scopeAndPermissionsAreMergedWithoutDroppingDefault() {
        client.get().uri("/api/inspect")
            .headers(h -> h.setBearerAuth(
                signed(Map.of(
                    "scope", "reports.read",
                    "permissions", "catalog.read"))))
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.name").isEqualTo("alice")
            .jsonPath("$.authorities[0]")
                .isEqualTo("PERM_catalog.read")
            .jsonPath("$.authorities[1]")
                .isEqualTo("SCOPE_reports.read");
    }

    @Test
    void missingAllAuthoritiesStillAllowsAuthenticatedInspect() {
        client.get().uri("/api/inspect")
            .headers(h -> h.setBearerAuth(signed(Map.of())))
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.authorities").isArray()
            .jsonPath("$.authorities.length()").isEqualTo(0);
    }

    @Test
    void scopeAdminIsNotAutomaticallyRoleAdmin() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBearerAuth(
                signed(Map.of("scope", "ADMIN"))))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void expiredTokenIsRejectedBeforeAuthorityMapping() {
        String token = signed(
            Map.of("scope", "reports.read"),
            true,
            SecurityConfig.ISSUER,
            List.of(SecurityConfig.AUDIENCE),
            SecurityConfig.demoKey());

        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth(token))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void wrongIssuerIsRejected() {
        String token = signed(
            Map.of("scope", "reports.read"),
            false,
            "https://untrusted-issuer.example.invalid",
            List.of(SecurityConfig.AUDIENCE),
            SecurityConfig.demoKey());

        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth(token))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void wrongAudienceIsRejected() {
        String token = signed(
            Map.of("scope", "reports.read"),
            false,
            SecurityConfig.ISSUER,
            List.of("another-api"),
            SecurityConfig.demoKey());

        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth(token))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void wrongSignatureIsRejected() {
        String token = signed(
            Map.of("scope", "reports.read"),
            false,
            SecurityConfig.ISSUER,
            List.of(SecurityConfig.AUDIENCE),
            otherKey());

        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth(token))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void malformedBearerIsRejected() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth("not-a-jwt"))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void httpBasicCannotReplaceBearerJwt() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBasicAuth("alice", "anything"))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void jwtCookieCannotReplaceAuthorizationHeader() {
        client.get().uri("/api/reports")
            .cookie("access_token",
                signed(Map.of("scope", "reports.read")))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void unitDefaultConverterMapsWhitespaceSeparatedScope() {
        Jwt jwt = Jwt.withTokenValue("unsigned-unit-fixture")
            .header("alg", "none")
            .claim("sub", "alice")
            .claim("scope", "reports.read reports.write")
            .build();

        var values = SecurityConfig.scopeAuthorities()
            .convert(jwt)
            .stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        assertEquals(
            List.of("SCOPE_reports.read", "SCOPE_reports.write"),
            values);
    }

    @Test
    void unitCustomConverterSplitsCommasAndPrefixesPermissions() {
        Jwt jwt = Jwt.withTokenValue("unsigned-unit-fixture")
            .header("alg", "none")
            .claim("sub", "alice")
            .claim("permissions",
                "catalog.read, catalog.write")
            .build();

        var values = SecurityConfig.permissionAuthorities()
            .convert(jwt)
            .stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        assertEquals(
            List.of("PERM_catalog.read", "PERM_catalog.write"),
            values);
    }
}
```

Chạy:

```bash
mvn test
```

**Mục tiêu: 22 test** với JDK/Maven/dependencies đúng. Đây là mã giáo trình để tự chạy; **không khẳng định đã thực thi tests trong repository người học**. Những bài `unitDefaultConverter...` và `unitCustomConverter...` dùng `Jwt` **không có chữ ký đã verify** — chỉ để kiểm pure mapping function. Các bài `WebTestClient` mới gửi JWT HS256 đã ký thật qua HTTP server và kiểm đường Bearer/decoder/converter/authorization, dù issuer/key vẫn chỉ là fixture local.

### 7.2. Nhóm test và bằng chứng tương ứng

| Nhóm | Điều chứng minh |
| --- | --- |
| Missing Bearer, wrong signature, expired, invalid issuer/audience | Decoder/authentication từ chối token → 401 |
| `scope` chuỗi và `scp` mảng | Default `JwtGrantedAuthoritiesConverter` phát `SCOPE_...` |
| Scope đúng/sai trên GET/POST | `hasAuthority` phân biệt quyền read/write → 200/403 |
| Custom `permissions` chuỗi CSV/mảng | Converter riêng đọc claim và tạo `PERM_...` |
| Combined claims trong `/api/inspect` | Scope mặc định **không bị mất** khi có custom permissions |
| `scope=ADMIN` với `hasRole("ADMIN")` | Không tự nâng SCOPE_ thành ROLE_ |
| Cookie JWT và HTTP Basic | API Bearer-header-only không tự xác thực bằng ambient cookie/Basic |
| Unit converter | Logic trích claim/prefix/delimiter, **không** kiểm chữ ký |
| JWT HTTP signed tests | Validation/mapper/filter thực, **không** chỉ mock Authentication |

**Cảnh báo về `mockJwt()`:** Trong nhiều Spring Security tests, `mutateWith(mockJwt().authorities(...))` được thiết kế để bỏ qua signature validation và đặt `Authentication` mock cho test authorization. Nó phù hợp cho những unit/slice tests khác, nhưng **không thể** dùng một mình làm bằng chứng custom `jwtAuthenticationConverter()` production đang được gọi. Nếu dùng mockJwt, phải gọi converter tùy chỉnh tường minh hoặc bổ sung bài test signed-token E2E như trên.

### 7.3. Vì sao test 401 và 403 đặc biệt quan trọng?

Nếu token có đúng scope nhưng sai chữ ký, status phải **401**; không được lấy `scope` trước khi xác minh và cho phép vào route. Nếu token hợp lệ nhưng chỉ có `reports.write` và gọi GET cần `reports.read`, status là **403**. Cách tách này giúp client và vận hành phân biệt credential invalid với thiếu quyền, tránh xử lý sai như cố refresh token khi thực ra người dùng cần bổ sung scope/consent.

## 8. Kiểm tra thủ công bằng curl và token demo

Chạy:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Một số request không cần token:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/reports
curl -i -H 'Authorization: Bearer not-a-jwt' \
  http://localhost:8080/api/reports
curl -i -u alice:anything \
  http://localhost:8080/api/reports
curl -i -H 'Cookie: access_token=not-a-jwt' \
  http://localhost:8080/api/reports
```

Kỳ vọng:

- `GET /public` → 200 `public`.
- `GET /api/reports` không Bearer → 401, `WWW-Authenticate: Bearer`.
- Bearer không phải JWT hợp lệ → 401.
- HTTP Basic không được bật → 401, không cấp quyền từ Basic.
- Cookie `access_token` không được Resource Server demo dùng làm Bearer header → 401.

Để gọi route protected với token hợp lệ, dùng **signed test JWT** được tạo bởi test helper phần 7 hoặc token từ Authorization Server thực đã cấu hình theo **đúng issuer/audience/key**:

```bash
# Chuỗi trong ngoặc nhọn chỉ là placeholder, KHÔNG dán nguyên:
curl -i -H 'Authorization: Bearer <VALID_TEST_JWT>' \
  http://localhost:8080/api/reports
```

Không có token issuance endpoint trong app demo; chủ đích là Resource Server **chỉ kiểm token**, không phát token. `mvn test` tạo JWT có chữ ký HS256 trong test để kiểm happy path mà không cần IdP. Không mang demo HMAC key lên production, không log JWT/token trong HTTP access logs, shell history, query hay client errors.

Trên Windows PowerShell, có thể phải dùng `curl.exe` thay cho alias `curl`. Với hệ thống thật, yêu cầu HTTPS, token lifetime hợp lý, issuer/JWK trust, audience và rotation; không gửi JWT thật qua HTTP plaintext ngoài localhost.

## 9. Nâng cấp từ demo sang JWT issuer/JWKS thật

Trong production, ứng dụng Resource Server nên dựa vào issuer/JWK Set URI đáng tin, không hard-code symmetric signing key. Ví dụ khi IdP hỗ trợ OIDC/OAuth2 metadata:

```properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://idp.example.org/issuer
```

Spring Security có thể tự discover JWKS và validate issuer/time dựa trên cấu hình. Khi cần tránh phụ thuộc IdP ở startup, có thể khai cả `jwk-set-uri` (sau khi xác minh giá trị trusted) và `issuer-uri` để vẫn validate `iss`:

```properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://idp.example.org/issuer
spring.security.oauth2.resourceserver.jwt.jwk-set-uri=https://idp.example.org/issuer/.well-known/jwks.json
```

Đây là **cấu hình thay thế** cho `@Bean ReactiveJwtDecoder` local, không dùng chung hai nguồn decoder một cách thiếu kiểm soát. Bổ sung `OAuth2TokenValidator<Jwt>` cho audience/token type/tenant/claims theo hợp đồng của API và chính sách bảo mật.

### 9.1. Không tự tin audience chỉ vì issuer đúng

Một issuer có thể cấp access tokens cho nhiều Resource Servers. JWT hợp lệ về chữ ký nhưng `aud=other-service` không nên được API reports chấp nhận. Ví dụ decoder phần 6 có audience validator để test token sai audience → 401. Khi chuyển sang `issuer-uri` production, phải duy trì validation tương đương trong decoder/validator chính thức được bạn cấu hình. Không vì chuyển cấu hình mà bỏ rule audience đã có.

### 9.2. Authority mapping không được tự trao quyền

Các claims `scope`/`scp`/`permissions` chỉ trở thành authorizations nếu **issuer thực sự tin cậy đã ký token**, token còn hạn, đúng audience và đúng policy. Không tin Base64 payload tự decode, header `X-Scope` hoặc raw user-supplied JSON. Khi scope phức tạp theo tenant, cần check ownership ở service/repository; converter không thay thế domain policy.

### 9.3. OIDC ID Token khác JWT access token

Nhiều người nhầm vì cả hai có hình dạng JWT. OIDC `id_token` chứng minh sự kiện authentication cho Relying Party; access token được cấp cho Resource Server. Resource Server không nên chấp nhận ID Token thay access token chỉ vì có `sub`/`email`/`scope` và JWS hợp lệ. Cần check audience, token type, issuer và cách AS phân biệt các token.

### 9.4. Token expired nhưng policy mapping đúng vẫn phải 401

Expiry/`nbf` validation xảy ra **trước** khi mapping quyền được tin cậy. Thêm `scope=reports.read` vào token đã hết hạn không biến nó thành token hợp lệ. Nếu client có refresh token, nó phải xin access token mới tại AS; Resource Server không refresh token giúp client.

## 10. Chọn scope, permission và role cho chính sách quyền

Trong API thực tế có ba tầng:

- **Scope (OAuth2):** loại hành động đã được AS ủy quyền cho client, ví dụ `reports.read`, `reports.write`. Đối chiếu `SCOPE_reports.read`.
- **Permission (domain):** quyền chi tiết theo sản phẩm/tài nguyên, ví dụ `catalog.read`. Khi AS phát trong claim `permissions` đã được thống nhất, có thể map `PERM_catalog.read`.
- **Role (organization):** nhóm quyền như `ADMIN` hoặc `SUPPORT`, thường map thành `ROLE_ADMIN` sau khi kiểm issuer, tenant, role allowlist. `hasRole("ADMIN")` tìm `ROLE_ADMIN`.

Một endpoint có thể cần **cả scope và permission**; đừng gộp tất cả vào một authority kiểu “authenticated” rồi cho phép. Ở mức reactive method security, có thể dùng `@PreAuthorize("hasAuthority('SCOPE_reports.read')")` khi bật `@EnableReactiveMethodSecurity` và return Publisher, nhưng method security không tự bật chỉ do có `@EnableWebFluxSecurity`. Với controller/service trong project demo, authorization đặt ở `authorizeExchange` là đủ để minh họa.

### 10.1. Ví dụ quy tắc quyền dạng kết hợp

Một policy domain có thể đòi:

```java
@PreAuthorize("hasAuthority('SCOPE_reports.read') and " +
              "hasAuthority('PERM_catalog.read')")
public Mono<Report> readCombined(String id) {
    return reportRepository.findById(id);
}
```

**Fragment** cần lớp `Report` và repository thật, annotation bật và AOP proxy. Trường hợp owner/tenant phải tiếp tục lọc dữ liệu sau khi đủ scope/permission, không cho token của user A đọc report B chỉ vì cả hai có `SCOPE_reports.read`.

### 10.2. Khi nào quyền cần lấy từ DB?

JWT scopes/permissions là **snapshot** do issuer cấp tại thời điểm phát hành; nếu user bị thu hồi quyền sau đó, JWT tự chứa có thể vẫn mang authority cũ đến hết hạn. Với yêu cầu thu hồi tức thời, thiết kế introspection, token lifetime ngắn, revocation, hoặc reactive authorization check theo nguồn dữ liệu hiện tại. Không gọi blocking JDBC trực tiếp trong `JwtGrantedAuthoritiesConverter` trên event-loop.

## 11. Lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Token có `scope=reports.read` nhưng bị 403 | Rule đòi `ROLE_reports.read`, sai prefix/case | Dùng `hasAuthority("SCOPE_reports.read")` |
| Token có `scp` nhưng không phát quyền | Claim type/decoder hoặc custom claim override | Test `scp` array, không vô tình bỏ mapping mặc định |
| Custom claim `permissions` không có authority | Chưa `setAuthoritiesClaimName("permissions")` | Chọn claim đúng, test format |
| Authority thừa dấu cách sau comma | Delimiter chỉ là `","` | Dùng regex `"\\s*,\\s*"` |
| Thêm custom claim làm mất `SCOPE_` | Đã thay default converter bằng custom-only | Gộp hai converters vào một collection |
| `hasRole("ADMIN")` không nhận `scope=admin` | ROLE_ khác SCOPE_ | Thiết kế mapping role riêng nếu chính sách cho phép |
| Token sai chữ ký/issuer/expiry nhận 200 | Decoder bị mock/bỏ kiểm validation | Dùng decoder thật + signed-token E2E |
| Token sai audience vẫn pass | Thiếu audience validator | Thêm validator `aud`, test 401 |
| Trộn Servlet với WebFlux | Dùng converter sync ở API cần reactive type | Dùng `ReactiveJwtAuthenticationConverterAdapter` |
| `jwtGrantedAuthoritiesConverter` có DB blocking | Đồng bộ trong event loop | Dời dynamic authorization sang reactive policy |
| `mockJwt()` test pass nhưng production 403 | Test bypass converter/custom claims | Test mapper trực tiếp và JWT signed E2E |
| JWT trong cookie tự authenticate API | Filter/gateway có cookie fallback | Review CSRF và auth source, test cookie-only 401 |
| Token valid có scope nhưng sai tenant vẫn đọc dữ liệu | Scope-only policy | Kiểm owner/tenant tại repository và service |
| JSON debug lộ token/claims | Serialize `Jwt` nguyên đối tượng | Chỉ trả DTO metadata được phê duyệt |
| Map `SCOPE_` thành `ROLE_` tùy tiện | Scope bị nâng quyền | Dùng prefix rõ, role allowlist và domain policy |
| Không có `permissions` nhưng API catalog 200 | Matcher `authenticated()` quá rộng hoặc route không match | Test 403 khi thiếu quyền và default deny |
| POST Bearer API trả 403 do CSRF | Chain vẫn yêu cầu CSRF | Chỉ miễn khi thực sự bearer-header-only; không làm rộng ra browser cookie routes |

### 11.1. Chẩn đoán 401/403 có phương pháp

1. Xem HTTP status và `WWW-Authenticate`, không đoán lỗi chỉ từ response body.
2. Nếu 401, kiểm Bearer header format, signature algorithm/JWK/secret, `iss`, `aud`, `exp`, `nbf` và clock skew. Không in full token ra log.
3. Nếu 403, lấy Authentication authorities trong môi trường kiểm thử an toàn (không public), so với chính xác `hasAuthority`/`hasRole`.
4. Kiểm JWT claim thực sự là `scope`, `scp` hay `permissions`, kiểu string/list và delimiter.
5. Kiểm converter đã gắn vào `ServerHttpSecurity.oauth2ResourceServer().jwt().jwtAuthenticationConverter(...)` chưa.
6. Kiểm matcher/order/catch-all và method GET/POST để không bị rule khác chặn.
7. Test claim custom không làm mất default scope, token expired phải 401, thiếu authority phải 403.
8. Nếu dùng gateway, kiểm ingress không chuyển cookie/ID Token thành Bearer mà không có trust policy.

## 12. Checklist triển khai an toàn

1. Chọn issuer/AS đáng tin, HTTPS/JWKS/allowed algorithms, validate signature, `iss`, `exp`, `nbf` và `aud`.
2. Tài liệu hóa claim contract: `scope` dạng space-separated hoặc `scp` list, custom `permissions` string CSV/list, case sensitivity.
3. Dùng `JwtGrantedAuthoritiesConverter` mặc định cho scope; đặt prefix `SCOPE_` trong rule `hasAuthority`.
4. Nếu dùng custom claim, cấu hình `setAuthoritiesClaimName`, `setAuthoritiesClaimDelimiter` và `setAuthorityPrefix` hợp lý.
5. Nếu cần scope **và** permission, **gộp hai converters**, không thay default rồi làm mất `SCOPE_`.
6. WebFlux dùng `ReactiveJwtAuthenticationConverterAdapter` hoặc native `ReactiveJwtAuthenticationConverter`, không trộn signature Servlet.
7. Không dùng conversion logic để gọi I/O blocking; phân quyền DB/tenant ở reactive authorization/service.
8. Không tự nâng `SCOPE_admin` thành `ROLE_ADMIN`; định nghĩa role policy riêng có allowlist.
9. Route policy default deny, phân biệt read/write scope và object-level ownership/tenant.
10. Bearer-only API không tự dùng session cookie/Basic; nếu thêm cookie fallback phải xét CSRF lại.
11. Test trực tiếp `JwtGrantedAuthoritiesConverter` và test signed JWT qua WebTestClient để kiểm cả decoder/converter/authz.
12. Có negative tests: 401 missing/bad signature/wrong issuer/aud/expired, 403 thiếu scope/permission/role; không chỉ test 200.
13. Không log Authorization header/raw JWT, không trả token hay full claims ra browser; chỉ lưu metadata an toàn có redaction.
14. Khi nâng Spring Security version hoặc đổi IdP, chạy lại scope/scp/custom claim tests và verify authorities trên Resource Server thật.

## 13. Câu hỏi tự đánh giá

**Câu 1.** JWT `scope="reports.read reports.write"` mặc định thành những authorities nào?  
`SCOPE_reports.read` và `SCOPE_reports.write`.

**Câu 2.** `hasRole("ADMIN")` có chấp nhận `scope=admin` không?  
Không mặc định. Scope thường thành `SCOPE_admin`, còn `hasRole("ADMIN")` tìm `ROLE_ADMIN`.

**Câu 3.** Provider phát `permissions=["catalog.read"]`, default converter tự đọc claim không?  
Không theo mặc định scope/scp. Cần `setAuthoritiesClaimName("permissions")`.

**Câu 4.** Tại sao khi đổi claimName sang permissions thì scope bị mất?  
Một converter chỉ đọc claim đã chọn. Muốn có cả `SCOPE_` và `PERM_`, gộp hai converters.

**Câu 5.** Khi claim permissions là CSV có spaces, dùng delimiter gì?  
Có thể dùng regex `"\\s*,\\s*"` để tách comma và whitespace quanh nó.

**Câu 6.** Có thể đưa trực tiếp `JwtGrantedAuthoritiesConverter` vào `jwtAuthenticationConverter(...)` của WebFlux không?  
Không đúng contract. Cần converter từ Jwt sang reactive Authentication, ví dụ `JwtAuthenticationConverter` bọc `ReactiveJwtAuthenticationConverterAdapter`.

**Câu 7.** JWT có scope phù hợp nhưng sai chữ ký có được authorize không?  
Không. `ReactiveJwtDecoder` phải từ chối với 401 trước khi mapping quyền.

**Câu 8.** Vì sao cần test `aud`?  
Token của cùng issuer có thể cấp cho API khác. Resource Server phải từ chối token sai audience.

**Câu 9.** `mockJwt()` có đủ kiểm converter/JWT validation thực không?  
Không. Nó phù hợp test policy; phải thêm unit converter và signed-token E2E.

**Câu 10.** `setAuthorityPrefix("ROLE_")` trên mọi scope có an toàn không?  
Không mặc định. Nó có thể biến scope thành role mạnh, phải có role-specific trust/allowlist và domain policy.

**Câu 11.** `hasAuthority("SCOPE_reports.read")` có tự kiểm owner và tenant không?  
Không. Cần kiểm phân quyền trên từng resource, thường ở service/repository.

**Câu 12.** `401` và `403` khác nhau thế nào trong bài?  
401 khi chưa có JWT hợp lệ; 403 khi authentication thành công nhưng không thỏa authority/policy.

### Tài liệu chính thức

- Spring Security 6.5, *Reactive Resource Server JWT*: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security 6.5, *Reactive OAuth2 Resource Server Overview*: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
- Spring Security API, `JwtGrantedAuthoritiesConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html
- Spring Security API, `JwtAuthenticationConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html
- Spring Security API, `ReactiveJwtAuthenticationConverterAdapter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/ReactiveJwtAuthenticationConverterAdapter.html
- Spring Security API, `ReactiveJwtAuthenticationConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/ReactiveJwtAuthenticationConverter.html
- Spring Security, *Testing JWT Authentication in WebFlux*: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- RFC 6750, *OAuth 2.0 Bearer Token Usage*: https://www.rfc-editor.org/rfc/rfc6750
- RFC 9068, *JWT Profile for OAuth 2.0 Access Tokens*: https://www.rfc-editor.org/rfc/rfc9068

**Tóm lại:** JWT Resource Server trong Spring WebFlux ánh xạ `scope`/`scp` thành authorities `SCOPE_...`. Tùy chỉnh `JwtGrantedAuthoritiesConverter` để đọc claim khác, đổi prefix/delimiter, và **gộp** với default converter nếu cần giữ scope gốc. Dùng `ReactiveJwtAuthenticationConverterAdapter` để nối vào SecurityWebFilterChain, kiểm JWT trước khi trao quyền, test signed JWT thật bên cạnh unit mapping, và không tự biến scope thành role hoặc bỏ qua kiểm owner/tenant.