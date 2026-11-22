# Chọn cơ chế xác thực bằng matcher và tránh xử lý trùng yêu cầu

> **Ngữ cảnh:** Spring Security **Reactive/WebFlux**, Java 17+, Spring Boot 3.3.x / Spring Security 6.3.x. Trọng tâm là chọn đúng authentication mechanism theo **URL, HTTP method, loại credential và hợp đồng API**, sử dụng `ServerWebExchangeMatcher`, `SecurityWebFilterChain.securityMatcher` và `AuthenticationWebFilter.setRequiresAuthenticationMatcher`; không để một request bị nhiều filter cùng xác thực, không vô tình nâng quyền hoặc chấp nhận credential ngoài ý muốn. Các ví dụ 3.3.x minh họa cú pháp, không phải khuyến nghị triển khai production bằng phiên bản đã hết hỗ trợ.

## 1. Bài toán thực tế

Một WebFlux service phục vụ ba kiểu client:

1. Một hệ thống đối tác nội bộ gọi `GET /internal/jobs` bằng header `X-API-Key`; dịch vụ cấp cho nó authority hạn chế `SCOPE_jobs.read`.
2. Một API quản trị/tương tác cũ gọi `GET /api/me` bằng HTTP Basic; user được xác thực qua `ReactiveUserDetailsService`.
3. Nhân viên mở `GET /web/me` trên trình duyệt, đăng nhập qua form và `WebSession`.

Nếu đặt **Basic, API key và form login trên mọi request**, có thể xảy ra:

- Basic filter và API-key filter đều được thử trên cùng một request có nhiều header.
- Một credential lỗi bị handler này bỏ qua rồi handler khác cấp quyền từ credential còn lại.
- API request nhận redirect đến trang login HTML thay vì HTTP 401.
- Filter tùy chỉnh không có matcher vẫn chạy trên `/health`, `/login` hoặc `/oauth2/**`, tiêu thụ credential sai loại.
- Developer vừa thêm custom `WebFilter` thành Spring bean vừa chèn đúng object đó vào `SecurityWebFilterChain`, dẫn đến khả năng chạy **hai lần** qua global WebFilter và security chain.
- Duplicate token decode/lookup, ghi session lặp, log/audit/tracing lặp hoặc side effect của authentication manager bị thực hiện nhiều lần.

Giải pháp là **định nghĩa ranh giới rõ ràng** giữa việc chọn chain, chọn filter, phân tích credential và kiểm quyền.

### Quy tắc một câu

**Mỗi request chỉ nên đi vào một `SecurityWebFilterChain` đã chọn, mỗi credential có một chủ thể xử lý rõ ràng, và mỗi xác thực thành công/thất bại phải có ý nghĩa nhất quán.** Điều này không ngăn các bước bảo mật khác (CSRF, CORS, authorization, logging) chạy trong chain; nó tránh xác thực ngoài chủ đích hoặc xác thực lặp.

## 2. Ba lớp matcher bắt buộc phân biệt

| Lớp | API Spring Security Reactive | Mục đích | Hệ quả nếu không match |
|---|---|---|---|
| **Chọn security chain** | `ServerHttpSecurity.securityMatcher(ServerWebExchangeMatcher)` | Chọn cấu hình bảo mật áp dụng cho request | Thử chain khác theo thứ tự; nếu không chain nào match, request có thể không được Spring Security bảo vệ |
| **Chọn lần xác thực của một filter** | `AuthenticationWebFilter.setRequiresAuthenticationMatcher(ServerWebExchangeMatcher)` | Quyết định filter đó có thử tạo `Authentication` | Filter bỏ qua, tiếp tục chain |
| **Chọn luật authorization** | `authorizeExchange(exchanges -> exchanges.pathMatchers(...).hasRole(...))` | Quyết định quyền đã có đủ hay chưa | Xét luật kế tiếp; `anyExchange()` làm fallback trong chain |

Sơ đồ:

```text
Request
  |
  v
WebFilterChainProxy
  |
  +-- securityMatcher của @Order(0) /internal/** ?
  |          | có
  |          +--> Internal chain
  |                     |
  |                     +--> AuthenticationWebFilter matcher?
  |                     |             |
  |                     |             +-- không -> bỏ qua filter
  |                     |             +-- có -> converter -> manager
  |                     |
  |                     +--> authorizeExchange pathMatchers/anyExchange
  |
  +-- nếu không, @Order(1) /api/** ?
  |          +--> Basic/API chain
  |
  +-- nếu không, @Order(2) fallback
             +--> Form login / web chain
```

**Quan trọng:** Spring Security WebFlux chọn **một** `SecurityWebFilterChain` khớp đầu tiên, không “ghép” tất cả chain. Nhưng **bên trong chain đã chọn**, nếu developer bật nhiều authentication filters có matcher giao nhau, chúng vẫn có thể cùng tham gia. Tách chain giải quyết nhóm route; cấu hình matcher/converter giải quyết việc chọn cơ chế **bên trong** chain.

## 3. ServerWebExchangeMatcher: điều kiện cho request reactive

`ServerWebExchangeMatcher` là interface của Spring Security Reactive. Nó nhận `ServerWebExchange` và trả publisher kết quả match/no match:

```java
Mono<ServerWebExchangeMatcher.MatchResult> matches(
    ServerWebExchange exchange);
```

Đây là chữ ký diễn giải, không cần tự định nghĩa lại interface. Spring có những matcher hữu ích:

- `PathPatternParserServerWebExchangeMatcher`: match URL theo Spring WebFlux path patterns, có thể ràng buộc HTTP method.
- `ServerWebExchangeMatchers.pathMatchers("/internal/**")`.
- `ServerWebExchangeMatchers.pathMatchers(HttpMethod.GET, "/internal/jobs")`.
- `ServerWebExchangeMatchers.matchers(matcherA, matcherB)`: ghép điều kiện OR khi API phiên bản hỗ trợ.
- `AndServerWebExchangeMatcher` và `OrServerWebExchangeMatcher` để kết hợp nhiều điều kiện.
- `NegatedServerWebExchangeMatcher` để phủ định một điều kiện khi cần.

**Lưu ý:** các matcher kiểu path không phải cấu trúc boolean từ ngữ `permitAll`. Một route `permitAll()` **vẫn nằm trong Security chain**, nên những filter trước authorization như CSRF hoặc custom authentication filter vẫn có thể tác động. Muốn bỏ qua một filter cụ thể, cấu hình matcher/converter của **filter đó** hoặc thay ranh giới chain phù hợp.

### 3.1 Path và HTTP method

```java
ServerWebExchangeMatcher internal =
    ServerWebExchangeMatchers.pathMatchers("/internal/**");

ServerWebExchangeMatcher onlyGetJob =
    ServerWebExchangeMatchers.pathMatchers(
        HttpMethod.GET, "/internal/jobs");
```

Các ví dụ trên cần imports `ServerWebExchangeMatcher`, `ServerWebExchangeMatchers`, `HttpMethod`. `/internal/**` có phạm vi rộng; `GET /internal/jobs` hẹp hơn và không match POST cùng path.

Một chiến lược tốt là chain match theo nhóm route, còn filter custom chỉ match route cần cơ chế đó, ví dụ:

```java
http.securityMatcher(
    ServerWebExchangeMatchers.pathMatchers("/internal/**"));

apiKeyFilter.setRequiresAuthenticationMatcher(
    ServerWebExchangeMatchers.pathMatchers(
        HttpMethod.GET, "/internal/jobs"));
```

Nếu thêm `POST /internal/jobs` sau này, phải **chủ động quyết định** có bật API-key filter và policy CSRF cho POST không. Không tự hiểu matcher GET sẽ bảo vệ mọi method.

### 3.2 Match theo header: có nên không?

Có thể viết custom matcher xét header `Authorization` hoặc `X-API-Key`, nhưng phải hiểu khác nhau giữa **chọn cách xử lý** và **tin một credential**:

- Có header `Authorization: Bearer ...` chỉ chứng tỏ client **gửi** chuỗi Bearer, không chứng tỏ token hợp lệ.
- Có `X-API-Key` chỉ giúp biết request muốn dùng API key, không có nghĩa key đủ quyền.
- `Accept: text/html` hoặc `User-Agent` không bao giờ được dùng như bằng chứng xác thực.
- Nếu nhiều loại credential cùng xuất hiện, cần policy **rõ ràng**: từ chối ambiguity hoặc chọn đúng một loại theo route, không âm thầm thử hết cho đến khi một cái thành công.
- Khi custom matcher đọc header, không log raw credential.

**Khuyến nghị:** nếu URL đã xác định rõ tính chất `/internal/**`, `/api/**`, `/web/**`, ưu tiên chia `SecurityWebFilterChain` theo route; chỉ matcher theo header khi thật sự cần hỗ trợ nhiều cơ chế trên cùng endpoint.

## 4. AuthenticationWebFilter: chính xác lúc nào nó thử xác thực?

`org.springframework.security.web.server.authentication.AuthenticationWebFilter` là một `WebFilter` phục vụ xác thực. Theo Javadoc Spring Security 6.x, flow tóm tắt:

1. Gọi `setRequiresAuthenticationMatcher(...)` để xác định **có phải request thuộc phạm vi filter**.
2. Nếu không match, tiếp tục `WebFilterChain` mà **không** thử authentication.
3. Nếu match, gọi `ServerAuthenticationConverter.convert(exchange)` tạo `Authentication` ban đầu từ request.
4. Converter trả `Mono.empty()` nghĩa là **không có credential thuộc cơ chế này**, filter **bỏ qua**, tiếp tục chain; không tự cấp quyền.
5. Nếu converter trả `Authentication`, filter gọi `ReactiveAuthenticationManager.authenticate(authentication)`.
6. Manager thành công → `ServerAuthenticationSuccessHandler`, đặt authentication vào reactive SecurityContext theo cơ chế filter.
7. Manager thất bại với `AuthenticationException` → `ServerAuthenticationFailureHandler` hoặc error behavior tương ứng.

```text
AuthenticationWebFilter
       |
  requires matcher?
       |
   +---+---+
   |       |
  no      yes
   |       |
continue  converter
             |
       +-----+------+
       |            |
   Mono.empty     Authentication
       |            |
    continue      manager
                    |
                +---+-----+
                |         |
             success     failure
                |         |
          SecurityContext  failure handler
                |         |
             continue   401/other policy
```

### 4.1 Hai loại “bỏ qua” cần phân biệt

- **Matcher không match:** filter không gọi converter/manager.
- **Converter trả Mono.empty():** matcher đã match, nhưng request **không chứa credential dành cho filter**, nên không tạo authentication attempt.

Với route protected, “bỏ qua filter” **không đồng nghĩa cho phép request**. Nếu không có authentication hợp lệ từ cơ chế khác, `authorizeExchange().authenticated()` sẽ dẫn đến entry point (thường 401 hoặc redirect tùy chain).

**Không** biến credential sai thành `Mono.empty()` để cơ chế khác được thử:

```java
// SAI về ý nghĩa bảo mật:
if (apiKeyIsWrong) {
    return Mono.empty(); // request có key SAI lại bị coi như không có key
}
```

Khi client gửi credential thuộc cơ chế đã chọn nhưng không hợp lệ, manager cần **báo lỗi xác thực** và handler trả thất bại nhất quán. `Mono.empty()` phù hợp khi **không có credential** thuộc cơ chế, không phù hợp làm “nuốt lỗi”.

### 4.2 Converter không nên tự kiểm quyền nghiệp vụ

`ServerAuthenticationConverter` chỉ trích xuất/định dạng credential thành `Authentication` chưa xác thực. `ReactiveAuthenticationManager` kiểm credential, xác định principal và authorities. `authorizeExchange` hoặc method/service security mới quyết định route/data access.

Không nên đọc user role từ request header `X-Role` rồi tạo `Authentication` đã authenticated mà không kiểm bằng nguồn tin cậy.

### 4.3 Default converter là HTTP Basic

Nếu tạo `new AuthenticationWebFilter(manager)` mà không đặt `setServerAuthenticationConverter(...)`, mặc định filter có thể sử dụng `ServerHttpBasicAuthenticationConverter`. Đối với API key custom, **phải gán converter của mình**, nếu không filter sẽ cố đọc Basic thay vì `X-API-Key` và tạo xung đột với Basic chain.

## 5. Authenticated ≠ authorized và việc có nhiều filter

Một `Authentication` thành công xác định danh tính/quyền nền tảng, không tự cấp phép tất cả endpoints:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.GET, "/internal/jobs")
        .hasAuthority("SCOPE_jobs.read")
    .anyExchange().denyAll())
```

Một API-key principal chỉ được tạo authority `SCOPE_jobs.read` nếu được kiểm qua key store/permission policy. Không tự cho `ROLE_ADMIN` dựa trên string header do client gửi. Với nhiều API keys, mapping key ID → tenant/permissions phải được lấy từ hệ thống đáng tin và kiểm trạng thái revoked/expiry.

### 5.1 Tại sao Basic + Bearer + API-key có thể va nhau?

Trên cùng một chain, các converter có thể xét:

- Basic filter: `Authorization: Basic ...`.
- Resource Server bearer filter: `Authorization: Bearer ...`.
- Custom key filter: `X-API-Key: ...`.

Một header `Authorization` chỉ chứa một chuỗi chính; client không thể gửi hai scheme trong **cùng** một giá trị hợp lệ, nhưng có thể gửi nhiều header lines hoặc đồng thời header `Authorization` và `X-API-Key`. Nếu filter key không bỏ qua Basic route, cả hai có thể đều thử xác thực. Khi một filter thành công rồi filter thứ hai thất bại, thứ tự/failure handler có thể tạo kết quả khó đoán. Không dựa vào thứ tự để có “fallback credential” an toàn.

**Thiết kế ưu tiên:**

1. **Một route = một scheme được công bố:** tách chain bằng URL, đơn giản nhất.
2. Nếu route buộc hỗ trợ nhiều scheme, dùng **một bộ phân luồng credential** để chọn đúng một manager/provider, hoặc các matcher loại trừ nhau có test.
3. Khi có hai credential không tương thích, **fail closed** (401/400 theo contract) thay vì thử credential mạnh hơn để “cứu” request.
4. Với cookie session + bearer trong cùng app, quyết định rõ tuyến nào chấp nhận cookie và tuyến nào thực sự stateless. Không tự dùng session authenticated để thay quyền của bearer token sai.
5. Khi nhiều identity sources cùng tồn tại, log correlation/credential type không nhạy cảm để audit, không log secret.

## 6. Chọn một chain bằng securityMatcher và @Order

Spring Security WebFlux chọn chain theo **thứ tự của các bean `SecurityWebFilterChain`**. Ví dụ:

```text
@Order(0): /internal/**    -> Custom X-API-Key
@Order(1): /api/**         -> HTTP Basic
@Order(2): fallback        -> Form Login / WebSession
```

- Chain đầu match `/internal/**`; những request này **không chạy** Basic/form chain tiếp theo.
- Chain thứ hai match `/api/**`; dù request có header `X-API-Key`, key filter thuộc chain đầu **không tồn tại ở chain này**.
- Chain cuối không có `securityMatcher` nên match các URL còn lại, gồm `/login`.
- Thứ tự rõ ràng giúp tránh matcher rộng `/**` “nuốt” route hẹp trước nó.

**Không** dùng ba chain có `securityMatcher("/**")` và mong mỗi request chạy qua cả ba để cộng quyền. Nếu không chain nào match một URL, Spring Security có thể không bảo vệ URL đó; fallback chain là biện pháp hữu ích.

### 6.1 securityMatcher khác authorizeExchange.pathMatchers

```java
// Chọn REQUEST thuộc chain này:
.securityMatcher(
    ServerWebExchangeMatchers.pathMatchers("/api/**"))

// Sau khi đã chọn chain, xác định ai được quyền:
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().authenticated())
```

Nếu `/api/admin/**` không match chain được chọn do chain matcher sai, `pathMatchers` phía authorization **không tự đưa request về đúng chain**.

### 6.2 CORS preflight và OPTIONS

Browser có thể gửi `OPTIONS` preflight trước request cross-origin với `Origin` và `Access-Control-Request-Method`. Đây không phải một lần gọi API cần “đăng nhập thêm”; matcher lọc riêng `GET /internal/jobs` sẽ không coi OPTIONS là xác thực API-key.

Nhưng việc không match auth filter **không tự cho preflight 200**: cần CORS policy và Security chain xử lý OPTIONS phù hợp. Không dùng `permitAll("/**")` để sửa preflight. Trên các API dựa header không tự động bởi trình duyệt, threat model CSRF khác cookie/browser-managed auth; chỉ tắt CSRF có chọn lọc sau khi đánh giá.

## 7. Tránh chạy WebFilter hai lần vì đăng ký sai nơi

Đây là bẫy lớn trong Spring Boot WebFlux:

```java
// PHẢN VÍ DỤ: vừa là Spring WebFilter bean toàn cục ...
@Bean
AuthenticationWebFilter apiKeyWebFilter(
        ReactiveAuthenticationManager manager) {
    return new AuthenticationWebFilter(manager);
}

// ... lại đưa cùng WebFilter vào SecurityWebFilterChain:
http.addFilterAt(apiKeyWebFilter, SecurityWebFiltersOrder.AUTHENTICATION);
```

Mã trên là **ví dụ về ý tưởng sai**, chưa đầy đủ class/import. Một bean triển khai `WebFilter` có thể được WebFlux/Boot đăng ký vào **global WebFilter chain**, trong khi `addFilterAt` lại chèn nó vào Spring Security chain. Vì vậy cùng custom filter có nguy cơ được gọi hai lần cho một request, hoặc chạy ngoài phạm vi chain security do matcher khác. Trường hợp thực tế phụ thuộc cách cấu hình và auto-registration nhưng phải được kiểm tra, không mặc nhiên coi Spring khử trùng lặp.

**Cách dùng an toàn của demo bên dưới:** tạo `new AuthenticationWebFilter(...)` **bên trong method cấu hình chain**, không đưa nó thành bean `WebFilter` toàn cục. Bean chỉ lưu verifier là một object thông thường, **không implement `WebFilter` hoặc `ReactiveAuthenticationManager` để tránh ảnh hưởng manager mặc định**.

```java
@Bean
@Order(0)
SecurityWebFilterChain internalChain(
        ServerHttpSecurity http, ApiKeyVerifier verifier) {

    AuthenticationWebFilter keyFilter =
        new AuthenticationWebFilter(verifier::authenticate);

    keyFilter.setRequiresAuthenticationMatcher(
        ServerWebExchangeMatchers.pathMatchers(
            HttpMethod.GET, "/internal/jobs"));

    // set converter và failure handler cụ thể ...

    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/internal/**"))
        .addFilterAt(keyFilter, SecurityWebFiltersOrder.AUTHENTICATION)
        .build();
}
```

**Đây là đoạn rút gọn**; mục 9 có code đầy đủ. Nếu viết một global `WebFilter` thật sự (ví dụ request ID tracing), nó sẽ chạy cho request từ mọi route theo ordering hệ thống; không nên đưa lại cùng object vào security chain để “bảo đảm”.

## 8. Chính sách áp dụng cho demo

### 8.1 Các route

| Route | Auth mechanism | Authentication required? | Ghi chú |
|---|---|---|---|
| `GET /internal/jobs` | `X-API-Key` | Có | Chỉ key hợp lệ được `SCOPE_jobs.read` |
| `GET /api/me` | HTTP Basic | Có | Trả principal username |
| `GET /web/me` | Form login / session | Có | Browser chưa login được redirect |
| `GET /web/public` | Không cần login | Không | Vẫn đi qua fallback security chain |
| `GET /login` | Generated login page | Không | Thuộc web chain |
| URL khác | Fallback web chain, `denyAll()` | Không tự mở | Giảm route lộ do thiếu chain |

### 8.2 Khi client gửi credential sai tuyến

| Request | Kết quả kỳ vọng | Vì sao |
|---|---|---|
| `GET /internal/jobs`, key đúng | 200 | Filter key đúng tuyến và manager chấp nhận |
| `GET /internal/jobs`, key sai | 401 JSON | Authentication thất bại, không được fallback |
| `GET /internal/jobs`, thiếu key | 401 JSON | Converter empty, authorization vẫn cần identity |
| `GET /internal/jobs` chỉ có Basic | 401 JSON | Chain internal không bật Basic |
| `GET /internal/jobs` có cả key + Authorization | 401 JSON | Demo cố ý từ chối mixed credentials |
| `GET /api/me`, Basic đúng | 200 | API chain chỉ nhận Basic |
| `GET /api/me` chỉ có X-API-Key | 401 với Basic challenge | Internal API-key filter không chạy ở đây |
| `GET /web/me` chưa login | Redirect form login | Web chain không bật API-key/Basic |
| `GET /web/public` | 200 | Route public, không có API-key attempt |
| `POST /internal/jobs` chỉ có key | Không coi là được bảo vệ bởi matcher GET | Luật khác/CSRF chặn; phải thiết kế riêng trước khi thêm write route |

Demo giữ CSRF mặc định vì chỉ công khai endpoint GET; **không tắt CSRF toàn cục** để làm ví dụ “dễ chạy”. Khi mở rộng sang POST, phải xét nguy cơ credential tự gửi từ browser, CORS, Content-Type và CSRF theo từng chain.

## 9. Ví dụ hoàn chỉnh Spring Boot 3.3.13, Java 17+

Dự án chạy được về mặt thiết kế với WebFlux + Spring Security và user store in-memory. Key `demo-local-api-key` và password `dev-only-password` chỉ phục vụ localhost; production phải có TLS, key entropy cao, secret manager/hashing/rotation và danh tính riêng cho service.

### 9.1 Cấu trúc thư mục

```text
webflux-auth-matchers/
  settings.gradle
  build.gradle
  src/main/resources/application.yml
  src/main/java/example/match/MatchApplication.java
  src/main/java/example/match/ApiKeyVerifier.java
  src/main/java/example/match/SecurityConfiguration.java
  src/main/java/example/match/DemoController.java
  src/test/java/example/match/AuthenticationMatcherTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'webflux-auth-matchers'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example.match'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Thư viện Servlet `spring-boot-starter-web` không được thêm vào project. `spring-security-test` hỗ trợ test Security WebFlux khi cần thêm các mock principals/CSRF helpers, dù ma trận dưới đây chủ yếu gửi credential thật để bắt lỗi matcher.

**src/main/resources/application.yml**

```yaml
demo:
  internal-api-key: demo-local-api-key
```

Không dùng giá trị demo này làm production credential. Với môi trường thật, cấu hình có thể chuyển sang `demo.internal-api-key: ${INTERNAL_API_KEY}` với biến môi trường do secret manager cung cấp, đồng thời dùng hash/rotation strategy. Không dùng chính credential trong ví dụ như khóa bí mật thật.

### 9.2 Application

**src/main/java/example/match/MatchApplication.java**

```java
package example.match;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MatchApplication {
    public static void main(String[] args) {
        SpringApplication.run(MatchApplication.class, args);
    }
}
```

### 9.3 ApiKeyVerifier: kiểm key đúng một lần, không tin raw header

**src/main/java/example/match/ApiKeyVerifier.java**

```java
package example.match;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import reactor.core.publisher.Mono;

public final class ApiKeyVerifier {

    // Type giúp converter ghi nhận request có nhiều/mixed headers.
    // Không để toString() in raw API key.
    public record SubmittedKey(String value, boolean malformed) {
        @Override
        public String toString() {
            return "[REDACTED]";
        }
    }

    private final byte[] expected;
    private final AtomicInteger attempts = new AtomicInteger();

    public ApiKeyVerifier(String configuredKey) {
        if (configuredKey == null || configuredKey.isBlank()) {
            throw new IllegalArgumentException("API key is required");
        }
        this.expected = configuredKey.getBytes(StandardCharsets.UTF_8);
    }

    public Mono<Authentication> authenticate(Authentication candidate) {
        return Mono.defer(() -> {
            attempts.incrementAndGet();

            Object credentials = candidate.getCredentials();
            if (!(credentials instanceof SubmittedKey submitted)
                    || submitted.malformed()
                    || !MessageDigest.isEqual(
                        expected,
                        submitted.value().getBytes(StandardCharsets.UTF_8))) {
                return Mono.error(
                    new BadCredentialsException("Invalid API key"));
            }

            return Mono.just(
                UsernamePasswordAuthenticationToken.authenticated(
                    "internal-service",
                    null,
                    List.of(new SimpleGrantedAuthority(
                        "SCOPE_jobs.read"))));
        });
    }

    // Chỉ dùng để chứng minh một request không gọi manager lặp.
    public int attemptCount() {
        return attempts.get();
    }
}
```

**Phân tích:**

- `ApiKeyVerifier` **không implement `WebFilter`**, nên không bị Spring Boot tự đăng ký như một global WebFilter.
- Nó cũng **không implement trực tiếp `ReactiveAuthenticationManager`** dưới dạng bean để tránh tình huống bean đó bị dùng làm authentication manager mặc định ở Basic/form-login chain. Khi cần, method reference `verifier::authenticate` được chuyển thành đúng functional interface ở constructor `AuthenticationWebFilter`.
- `AtomicInteger` phục vụ **test**, không phải chỉ số security production; không log secret.
- `MessageDigest.isEqual` so byte arrays để giảm rủi ro so sánh chuỗi dừng sớm. Với production, key phải đủ entropy, lưu theo hash/key identifier/rotation và có rate limit, TLS, revocation; không dựa vào duy nhất demo string.
- Sai key làm `Mono.error(BadCredentialsException)`, **không** trả `Mono.empty()` để một authentication mechanism khác thử tiếp.
- Authentication thành công chỉ được cấp authority `SCOPE_jobs.read`. Không tự cấp `ROLE_ADMIN` hoặc lấy quyền từ header do client tự khai.
- Không lấy `expected` từ HTTP request, query param, hoặc debug endpoint.

### 9.4 SecurityConfiguration: 3 chain, một custom filter trong đúng chain

**src/main/java/example/match/SecurityConfiguration.java**

```java
package example.match;

import java.nio.charset.StandardCharsets;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    private static final String API_KEY_HEADER = "X-API-Key";

    @Bean
    ApiKeyVerifier apiKeyVerifier(
            @Value("${demo.internal-api-key}") String configuredKey) {
        return new ApiKeyVerifier(configuredKey);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("dev-only-password"))
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(alice);
    }

    @Bean
    @Order(0)
    SecurityWebFilterChain internalChain(
            ServerHttpSecurity http,
            ApiKeyVerifier verifier) {

        // Không @Bean AuthenticationWebFilter để tránh global WebFilter.
        AuthenticationWebFilter keyFilter =
            new AuthenticationWebFilter(verifier::authenticate);

        // Lớp matcher thứ hai: filter chỉ quan tâm GET /internal/jobs.
        keyFilter.setRequiresAuthenticationMatcher(
            ServerWebExchangeMatchers.pathMatchers(
                HttpMethod.GET, "/internal/jobs"));

        // Khi matcher khớp nhưng không có key, không thử xác thực.
        keyFilter.setServerAuthenticationConverter(exchange -> {
            List<String> keys =
                exchange.getRequest().getHeaders().get(API_KEY_HEADER);

            if (keys == null || keys.isEmpty()) {
                return Mono.empty();
            }

            String submitted = keys.get(0) == null ? "" : keys.get(0);
            boolean malformed = keys.size() != 1
                || submitted.isBlank()
                || exchange.getRequest().getHeaders()
                    .containsKey(HttpHeaders.AUTHORIZATION);

            // Nếu client cung cấp key lỗi định dạng, vẫn gửi
            // Authentication chưa xác thực cho manager từ chối,
            // KHÔNG bỏ qua để cơ chế khác tiếp tục.
            return Mono.just(
                org.springframework.security.authentication
                    .UsernamePasswordAuthenticationToken.unauthenticated(
                        "internal-service",
                        new ApiKeyVerifier.SubmittedKey(
                            submitted, malformed)));
        });

        // Failure do key sai hoặc request có nhiều credential.
        keyFilter.setAuthenticationFailureHandler((filterExchange, ex) ->
            problem(filterExchange.getExchange(),
                HttpStatus.UNAUTHORIZED, "invalid_api_key"));

        // Key được xác thực cho request hiện tại, không tạo session.
        keyFilter.setSecurityContextRepository(
            NoOpServerSecurityContextRepository.getInstance());

        return http
            .securityMatcher(
                ServerWebExchangeMatchers.pathMatchers("/internal/**"))
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/internal/jobs")
                    .hasAuthority("SCOPE_jobs.read")
                .anyExchange().denyAll())
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint((exchange, ex) ->
                    problem(exchange, HttpStatus.UNAUTHORIZED,
                        "api_key_required"))
                .accessDeniedHandler((exchange, ex) ->
                    problem(exchange, HttpStatus.FORBIDDEN,
                        "access_denied")))
            .addFilterAt(
                keyFilter, SecurityWebFiltersOrder.AUTHENTICATION)
            // CSRF không bị tắt; demo chỉ có GET.
            .build();
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain basicApiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                ServerWebExchangeMatchers.pathMatchers("/api/**"))
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain browserChain(ServerHttpSecurity http) {
        return http
            // Không có securityMatcher -> fallback chain.
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/login", "/error").permitAll()
                .pathMatchers(HttpMethod.GET, "/web/public")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/web/me")
                    .authenticated()
                .anyExchange().denyAll())
            .httpBasic(basic -> basic.disable())
            .formLogin(Customizer.withDefaults())
            .build();
    }

    private static Mono<Void> problem(
            ServerWebExchange exchange,
            HttpStatus status,
            String code) {

        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(status);
        response.getHeaders().setContentType(
            MediaType.APPLICATION_PROBLEM_JSON);
        response.getHeaders().set(
            HttpHeaders.CACHE_CONTROL, "no-store");

        // Chỉ giá trị code nội bộ do server chỉ định.
        // Không xuất raw exception, key, password, session ID.
        String json = """
            {"type":"about:blank","title":"Unauthorized",
             "status":401,"detail":"Authentication required"}
            """;

        if (status == HttpStatus.FORBIDDEN) {
            json = """
                {"type":"about:blank","title":"Forbidden",
                 "status":403,"detail":"Access denied"}
                """;
        }

        // Không phản chiếu code từ request. Có thể dùng code này
        // trong internal metrics, không log credential.
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);

        return response.writeWith(Mono.just(
            response.bufferFactory().wrap(bytes)));
    }
}
```

**Các điểm cần kiểm tra khi đọc code:**

1. `SecurityWebFiltersOrder.AUTHENTICATION` đặt custom key filter vào pha authentication **trước** authorization. Không viết một global WebFilter tùy ý rồi kỳ vọng security context/order đúng.
2. `@Order(0)`, `@Order(1)` và `@Order(2)` làm thứ tự chain deterministic. Fallback chain bảo vệ các URL không thuộc internal/API.
3. `internalChain` bật **chỉ** API-key mechanism; Basic/form bị disable ở chain này. Request Basic vào internal không được đăng nhập nhờ Basic.
4. `keyFilter.setRequiresAuthenticationMatcher` dùng GET/đường dẫn hẹp; converter chỉ chạy khi đúng request.
5. Converter trả `Mono.empty()` chỉ cho **header key vắng mặt**. Header có key nhưng sai, trống, bị duplicate hoặc đồng thời có Authorization được chuyển thành credentials có cờ `malformed` để manager từ chối.
6. `ApiKeyVerifier.authenticate` chỉ thực thi khi converter phát authentication; test kiểm attempt count.
7. `NoOpServerSecurityContextRepository` được chỉ định cả tại filter và ở HTTP security chain để key auth không được lưu thành login session cho request sau. WebFilter vẫn chuyển reactive SecurityContext cho **request hiện tại** sau thành công.
8. `basicApiChain` dùng HTTP Basic và account in-memory riêng. Không có custom API-key filter trong chain này; header `X-API-Key` không tự giúp login.
9. `browserChain` dùng form login, không bật Basic. Browser chưa đăng nhập được redirect tới trang login mặc định.
10. `csrf` **không bị disable**. Các GET demo không cần CSRF token. Nếu muốn thêm unsafe POST cho internal/API, phải thiết kế CSRF/method matches/credential origin và test trước.
11. JSON writer không trả raw token hoặc nguyên nhân chi tiết. Có thể đưa một mã lỗi ổn định `invalid_api_key` / `api_key_required` vào body nếu hợp đồng client cần, nhưng hãy làm bằng các literal server-side, không dựa vào exception message.
12. Đoạn code trên dùng `@Bean ApiKeyVerifier` thay cho `@Bean AuthenticationWebFilter`; điều này tách logic xác minh khỏi WebFilter lifecycle/registration.

### 9.5 Controller

**src/main/java/example/match/DemoController.java**

```java
package example.match;

import java.security.Principal;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping(value = "/internal/jobs",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> jobs(Principal principal) {
        return Mono.just(
            "jobs for " + principal.getName());
    }

    @GetMapping(value = "/api/me",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> apiMe(Principal principal) {
        return Mono.just(
            "basic user " + principal.getName());
    }

    @GetMapping(value = "/web/me",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> webMe(Principal principal) {
        return Mono.just(
            "web user " + principal.getName());
    }

    @GetMapping(value = "/web/public",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> publicPage() {
        return Mono.just("public");
    }
}
```

Không đọc credential thô từ request trong controller để xác minh lại. `Principal` đến sau Security WebFilterChain, phản ánh authentication đã được cơ chế tương ứng chấp nhận. Với dữ liệu thật, còn phải kiểm quyền owner/tenant trong service/repository; route-level authority chưa đủ cho object-level authorization.

### 9.6 Chạy với Gradle, curl

```bash
gradle bootRun

# Internal API-key đúng:
curl -i -H "X-API-Key: demo-local-api-key" \
  http://localhost:8080/internal/jobs

# Internal thiếu key:
curl -i http://localhost:8080/internal/jobs

# Internal sai key:
curl -i -H "X-API-Key: wrong-key" \
  http://localhost:8080/internal/jobs

# Basic API route; curl hỏi mật khẩu, nhập dev-only-password:
curl -i -u alice http://localhost:8080/api/me

# Đưa key vào Basic route không thể thay Basic:
curl -i -H "X-API-Key: demo-local-api-key" \
  http://localhost:8080/api/me

# Browser route chưa login: xem 302, không follow:
curl -i -H "Accept: text/html" \
  http://localhost:8080/web/me

# Public:
curl -i http://localhost:8080/web/public
```

Nếu có wrapper, dùng `./gradlew bootRun`; Windows dùng `gradlew.bat bootRun`. Trong PowerShell, có thể phải dùng `curl.exe`. Không gắn password thật vào URL hoặc command line history; key và password trong bài chỉ là data local cho lab.

**Kỳ vọng:**

```text
GET /internal/jobs (valid X-API-Key) -> 200, "jobs for internal-service"
GET /internal/jobs (missing key)     -> 401
GET /internal/jobs (wrong key)       -> 401
GET /api/me (Basic alice)            -> 200, "basic user alice"
GET /api/me (only X-API-Key)         -> 401 Basic challenge
GET /web/me (anonymous HTML)         -> 302 Location: /login
GET /web/public                      -> 200 "public"
```

`curl -L` tự follow redirect; đừng dùng khi bạn đang kiểm phản hồi 302 đầu tiên.

## 10. Test WebTestClient: chứng minh không xác thực trùng

Test chạy HTTP WebFlux với Security chain thực, gửi credential hợp lệ/sai để xác định route nào gọi `ApiKeyVerifier`.

**src/test/java/example/match/AuthenticationMatcherTest.java**

```java
package example.match;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class AuthenticationMatcherTest {

    @Autowired
    WebTestClient client;

    @Autowired
    ApiKeyVerifier verifier;

    @Test
    void internalWithValidApiKeyAuthenticatesExactlyOnce() {
        int before = verifier.attemptCount();

        client.get().uri("/internal/jobs")
            .header("X-API-Key", "demo-local-api-key")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("jobs for internal-service");

        assertEquals(before + 1, verifier.attemptCount());
    }

    @Test
    void missingApiKeySkipsManagerButCannotAccess() {
        int before = verifier.attemptCount();

        client.get().uri("/internal/jobs")
            .exchange()
            .expectStatus().isUnauthorized();

        assertEquals(before, verifier.attemptCount());
    }

    @Test
    void invalidApiKeyFailsOnceWithoutBasicFallback() {
        int before = verifier.attemptCount();

        client.get().uri("/internal/jobs")
            .header("X-API-Key", "incorrect")
            .exchange()
            .expectStatus().isUnauthorized();

        assertEquals(before + 1, verifier.attemptCount());
    }

    @Test
    void mixedInternalCredentialsAreRejected() {
        int before = verifier.attemptCount();

        client.get().uri("/internal/jobs")
            .header("X-API-Key", "demo-local-api-key")
            .headers(h ->
                h.setBasicAuth("alice", "dev-only-password"))
            .exchange()
            .expectStatus().isUnauthorized();

        assertEquals(before + 1, verifier.attemptCount());
    }

    @Test
    void duplicateApiKeyHeadersAreRejected() {
        int before = verifier.attemptCount();

        client.get().uri("/internal/jobs")
            .header("X-API-Key",
                "demo-local-api-key", "incorrect")
            .exchange()
            .expectStatus().isUnauthorized();

        assertEquals(before + 1, verifier.attemptCount());
    }

    @Test
    void basicApiDoesNotInvokeApiKeyManager() {
        int before = verifier.attemptCount();

        client.get().uri("/api/me")
            .headers(h ->
                h.setBasicAuth("alice", "dev-only-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("basic user alice");

        assertEquals(before, verifier.attemptCount());
    }

    @Test
    void keyOnBasicRouteIsNotAValidCredential() {
        int before = verifier.attemptCount();

        client.get().uri("/api/me")
            .header("X-API-Key", "demo-local-api-key")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueMatches(
                HttpHeaders.WWW_AUTHENTICATE, "Basic .*");

        assertEquals(before, verifier.attemptCount());
    }

    @Test
    void basicOnInternalRouteDoesNotAuthenticate() {
        int before = verifier.attemptCount();

        client.get().uri("/internal/jobs")
            .headers(h ->
                h.setBasicAuth("alice", "dev-only-password"))
            .exchange()
            .expectStatus().isUnauthorized();

        assertEquals(before, verifier.attemptCount());
    }

    @Test
    void anonymousWebPageRedirectsInsteadOfKeyAuth() {
        int before = verifier.attemptCount();

        client.get().uri("/web/me")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isFound()
            .expectHeader().valueMatches(
                HttpHeaders.LOCATION, ".*/login");

        assertEquals(before, verifier.attemptCount());
    }

    @Test
    void publicPageDoesNotInvokeApiKeyVerifier() {
        int before = verifier.attemptCount();

        client.get().uri("/web/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");

        assertEquals(before, verifier.attemptCount());
    }

    @Test
    void defaultLoginPageIsHandledByWebChain() {
        int before = verifier.attemptCount();

        client.get().uri("/login")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isOk();

        assertEquals(before, verifier.attemptCount());
    }

    @Test
    void matcherForGetDoesNotAcceptUnsafePost() {
        int before = verifier.attemptCount();

        // POST ngoài phạm vi authentication filter GET.
        // Với CSRF bật, 403 là kết quả hợp lý cho request này.
        client.post().uri("/internal/jobs")
            .header("X-API-Key", "demo-local-api-key")
            .exchange()
            .expectStatus().isForbidden();

        assertEquals(before, verifier.attemptCount());
    }
}
```

**12 phương thức test** chủ ý kiểm ba điều:

1. **Mỗi request đúng key có đúng một authentication attempt.** Kiểm `AtomicInteger` trước/sau giúp phát hiện đăng ký filter trùng hoặc manager bị gọi hai lần.
2. **Request sai tuyến không gọi verifier.** Basic route, web route và login page không được kích hoạt manager API key.
3. **Thiếu key, sai key, hai loại credential cùng lúc hoặc duplicate header** đều không tạo 200 ngoài ý muốn.

Test `POST /internal/jobs` chỉ dùng để chứng minh matcher authentication GET không “mở rộng” sang POST; CSRF mặc định chặn unsafe POST. Một hệ thống thật phải test thêm method-specific policy/CSRF nếu có write endpoints.

Chạy:

```bash
gradle test
```

**Phạm vi QA:** code được rà soát dựa trên API Spring Security 6.x; **không có log Gradle build/test thực thi** trong bài. Kiểm tra cụ thể với dependency lockfile/version thật trước khi áp dụng. Nếu test về duplicate key header bị HTTP stack/proxy chuẩn hóa header khác với cách test gửi, cần kiểm xem chính sách HTTP header normalization của gateway chứ không vội kết luận auth filter sai.

### 10.1 Đo đếm chính xác trong test tích hợp thực tế

`attemptCount` chỉ giúp kiểm **đã gọi method authenticate của verifier bao nhiêu lần**. Nó không đo tất cả thứ khác:

- Một filter có thể chạy hai lần nhưng converter trả Mono.empty() ở một lần, khiến attemptCount không tăng; nếu cần phân biệt, thêm **filter-level instrumentation** trong test.
- WebFlux/Netty có thể retry request ở client nếu cấu hình riêng; bài dùng WebTestClient không thiết kế retry.
- AuthenticationManager có thể gọi async dependency nhiều lần bên trong một attempt; muốn kiểm không query DB/IdP lặp phải instrument chính repository/HTTP client.
- Nếu test chạy song song, counter toàn cục gây race giữa tests; cấu hình test sequential, dùng metric per-request/correlation ID hoặc mock strict invocation count.
- Các WebFilter chung như CSRF, headers, tracing vẫn có thể chạy; “một attempt” không có nghĩa chỉ một WebFilter chạy.

Với production, tránh lưu raw tokens để debug; dùng correlation ID và counter không nhạy cảm theo route/credential type.

## 11. Một chain bắt buộc hỗ trợ nhiều cơ chế thì làm sao?

Có những API hỗ trợ song song OAuth2 Bearer và HTTP Basic trong giai đoạn migrate. Trường hợp này không thể chỉ tách path nếu **cùng một path** được client gọi theo hai schemes.

### 11.1 Hai filter với matcher credential không giao nhau

- Basic filter chỉ nhận `Authorization: Basic ...`.
- Bearer filter chỉ nhận `Authorization: Bearer ...`.
- API-key filter chỉ nhận `X-API-Key`, nhưng phải phát hiện `Authorization` đi kèm để từ chối mixed credentials.
- Các matcher phải không giao nhau hoặc có policy chọn ưu tiên tường minh.
- Chỉ **một** source phải được phép tạo authoritative Authentication cho request.

**Đừng tự coi việc có hai filter mặc định cùng chain là lỗ hổng**: Spring Security có thể hỗ trợ đồng thời nhiều mechanism đúng cách. Vấn đề là custom logic có matcher quá rộng, converter tự tạo authentication sai, hoặc quy tắc fallback “cơ chế nào thành công cũng được” mà không có chính sách.

### 11.2 Một converter phân luồng

Đối với custom mechanisms, có thể dùng `DelegatingServerAuthenticationConverter` (nếu phiên bản hỗ trợ) hoặc viết một `ServerAuthenticationConverter` tự chọn:

```java
// Pseudocode cho policy phân loại credential:
convert(exchange) {
    if (hasBothApiKeyAndAuthorization(exchange)) {
        return Mono.error(
            new BadCredentialsException("Ambiguous credentials"));
    }

    if (isBearer(exchange)) {
        return bearerConverter.convert(exchange);
    }

    if (isApiKey(exchange)) {
        return apiKeyConverter.convert(exchange);
    }

    return Mono.empty();
}
```

Đây là **pseudocode**, không phải Java compile-ready. `ReactiveAuthenticationManager`/resolver tương ứng phải chấp nhận đúng token type của từng converter. Nếu dùng một `DelegatingReactiveAuthenticationManager`, chú ý semantics khi manager trả empty vs báo lỗi: **không biến một credential sai của provider A thành cơ hội để provider B nâng quyền** mà không có explicit policy.

### 11.3 AuthenticationManagerResolver cho nhiều issuer/tenant

Spring Security Reactive có constructor `AuthenticationWebFilter(ReactiveAuthenticationManagerResolver<ServerWebExchange>)`. Nó giúp quyết định **manager nào** dựa trên request trong những trường hợp hợp lệ. Nhưng đừng dựa vào `Host`, `tenant` hoặc `issuer-uri` do client tự khai mà không validation rồi gọi metadata discovery để tạo manager mới; đó là nguy cơ SSRF, mix-up IdP và cache poisoning. Cần allowlist issuer/tenant, JWT validation đúng key và authentication policy nhất quán.

### 11.4 Resource Server JWT nên tận dụng built-in

Nếu bảo vệ Bearer JWT, ưu tiên:

```java
@Bean
@Order(0)
SecurityWebFilterChain jwtApiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/jwt/**"))
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .httpBasic(basic -> basic.disable())
        .formLogin(form -> form.disable())
        .build();
}
```

Đoạn này là **mảnh config** cần `ReactiveJwtDecoder` và issuer/JWK cấu hình; không dán nguyên vào demo mục 9. Nếu thêm nó vào hệ thống có Basic chain `/api/**`, phải đặt **JWT chain trước Basic chain** để matcher hẹp không bị matcher rộng che. Cần bật chính sách scope/authority/audience đúng (không chỉ `authenticated()`), kiểm fail của token hết hạn/sai signature và 401/403 riêng.

## 12. Matchers và các vấn đề bảo mật khác

### 12.1 Security chain không match URL nào

Nếu developer chỉ khai báo:

```java
.securityMatcher(
    ServerWebExchangeMatchers.pathMatchers("/api/**"))
```

và **không** có fallback chain, những route khác có thể không được Spring Security bảo vệ. Điều này không có nghĩa framework tự biến tất cả URL ngoài `/api/**` thành 403. Giữ catch-all chain `anyExchange().denyAll()` cho các route ngoài dự kiến, và test endpoint “không nằm trong danh sách” với user nhiều role.

### 12.2 Authorization rules bị shadow

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").authenticated()
    .pathMatchers("/api/admin/**").hasRole("ADMIN"))
```

Đây là **ví dụ đặt luật sai thứ tự**: rule rộng đứng trước có thể match route admin và không bao giờ đến rule hạn chế. Đặt rule hẹp trước rộng, `anyExchange()` cuối cùng. Tương tự, thứ tự `@Order` của chain rộng/hẹp phải được kiểm tra.

### 12.3 Không dựa vào Accept hoặc User-Agent để chọn quyền

Có thể dùng `Accept: text/html` để quyết định 302 HTML hay 401 JSON **sau khi** authentication thất bại. Nhưng `Accept`/`User-Agent`/`X-Requested-With` không phải bằng chứng client là người hoặc service. Không cấp role/cho phép route vì user-agent trông giống browser nội bộ.

### 12.4 Cùng route, hai credential và session đã đăng nhập

Một browser có session hợp lệ nhưng gửi Authorization Bearer **sai** tới API: policy cần nói rõ response là gì. Không âm thầm cho session đã login làm fallback để bỏ qua token sai khi endpoint contract yêu cầu Bearer. Nên tách `/api/**` với stateless resource-server chain, vô hiệu form/session login tại API khi kiến trúc cho phép.

### 12.5 CSRF và authentication matcher

CSRF kiểm hành vi browser credential tự động gửi, thường áp cho unsafe methods. Một custom matcher không chạy ở POST **không tự giải quyết CSRF**, và `permitAll` cũng không tự vô hiệu hóa CSRF. Với Basic browser tự quản lý credential, CSRF vẫn có thể liên quan; không tắt CSRF toàn cục chỉ vì URL tên `/api`.

### 12.6 CORS preflight

`OPTIONS` từ browser có thể đến trước Bearer/API-key request. Cần cấu hình `CorsConfigurationSource` và Spring Security WebFlux CORS integration theo origin/method/headers. Không yêu cầu API key trong một preflight browser vốn không gửi credential; cũng không mở rộng permitAll cho mọi method/route chỉ để preflight hết lỗi. Bài demo chỉ GET và không thiết kế cross-origin support.

### 12.7 Đăng ký custom WebFilter ngoài Spring Security

Một `@Component WebFilter` chạy ở WebFlux global chain có thể được gọi trước, sau hoặc ngoài thứ tự mong muốn của Spring Security filter chain. Đừng tự thiết lập authenticated principal bằng attribute tự chế `exchange.getAttributes().put("user", ...)` rồi nghĩ authorization của Spring Security hiểu đó là Authentication.

Khi custom mechanism thực sự là authentication, dùng `AuthenticationWebFilter`/`ReactiveAuthenticationManager`/`ReactiveSecurityContextHolder` và proper order. Một global filter dùng cho tracing/metrics không nên chứa secret authentication logic.

### 12.8 Stateless vs session persistence

`NoOpServerSecurityContextRepository` giúp tránh lưu SecurityContext của API key/Basic giữa các requests. Nhưng **không tự làm mọi phần ứng dụng “stateless tuyệt đối”**: CSRF/request cache hoặc các feature khác có thể vẫn dùng WebSession. Nếu đòi stateless thực sự, cần đánh giá tất cả WebFilters, request cache, CSRF mechanism, cookie và business session riêng, chứ không đơn giản đặt repository NoOp.

### 12.9 Header normalization và duplicate credentials

HTTP proxies có thể gộp nhiều header lines thành một giá trị comma-separated hoặc xử lý `Authorization` đặc biệt. Bộ lọc không được giả định “một tên header xuất hiện” luôn tương đương một giá trị được xác minh. Với API keys:

- Giới hạn một credential theo contract.
- Reject whitespace/blank/duplicates, kích thước quá lớn, bất kỳ scheme không hỗ trợ.
- Nếu hệ thống đi qua proxy, kiểm tra cách proxy normalize duplicate header **trước** validation.
- Rate-limit/authenticate theo key ID/trusted identity; không log raw key.
- Token/key phải có entropy cao, rotation và revocation; API-key không nên thay user delegation khi phải kiểm quyền từng user.

## 13. Chẩn đoán khi nhận 401, 403, 302 hoặc filter chạy lặp

| Triệu chứng | Nghi vấn | Bước kiểm |
|---|---|---|
| Key hợp lệ nhưng `/internal/jobs` luôn 401 | Sai matcher; converter không phát Authentication; manager không được gọi; key config sai | Kiểm `@Order`, header name, manager attempt count |
| Request Basic vào `/internal/jobs` lại thành công | Chain internal bật Basic ngoài ý muốn hoặc matcher không đủ hẹp | Kiểm securityMatcher/HTTP Basic spec |
| `/api/me` với API key lại thành công | Custom WebFilter được đăng ký global hoặc converter Basic không chặn đúng | Kiểm @Bean WebFilter và addFilterAt |
| Một request tăng attempt count 2 | Filter bị thêm hai lần, retry/subscription lặp hoặc nhiều converters/managers | Instrument filter entry, manager subscribe và request ID |
| `/api/**` nhận HTML login | Chain web bắt request trước API hoặc Basic thất bại bị form entry point bắt | Kiểm @Order/securityMatcher/entryPoint |
| Header key sai nhưng request vẫn 200 | Manager trả Mono.empty và filter khác cấp quyền; session fallback | Fail closed credential sai, tách scheme |
| Path khớp chain nhưng 403 dù key đúng | Authorization authority sai, request method không match, CSRF chặn | Kiểm matcher filter/authorizeExchange/CSRF |
| POST key bị 403 | CSRF hoặc `anyExchange().denyAll()` | Thiết kế CSRF + method riêng; không tắt toàn bộ |
| OPTIONS preflight 401 | CORS chưa xử lý trước auth | Kiểm origin/method/headers và chain CORS policy |
| /login 404/403 | Fallback chain thiếu hoặc generated login page không được bật | Kiểm formLogin, permitAll login, chain matcher |
| Route không khai báo được truy cập | Không chain nào match, hoặc permitAll quá rộng | Thêm fallback denyAll, test URL lạ |
| Bearer sai chữ ký nhưng được phép nhờ session | Cho phép nhiều scheme trên route không có policy rõ | Tách chain Bearer/stateless, fail closed |
| Xuất hiện hai loại Authentication trong logs | Hai filters cùng xử lý, context bị ghi đè | Kiểm converter/matcher và identity precedence |
| Auth manager gọi DB/IdP nhiều lần | Side effects trong Mono được subscribe/retry; global filter trùng | Đo số lần subscribe, tránh redundant requests |
| Custom filter chạy trên /health | Global WebFilter hoặc requires matcher mặc định any request | Đặt matcher hẹp và chain-scoped filter |
| Client request đúng auth nhưng sai tenant | Chỉ route-level auth, thiếu data-level authorization | Kiểm service/repository ownership/tenant |

**Tốt hơn log credential:** dùng event/counter `auth_attempt{route,mechanism,outcome}` không kèm secret, correlation ID và log mapping exception an toàn.

## 14. Bộ test cần có khi hệ thống thật

| Nhóm | Case | Điều phải khẳng định |
|---|---|---|
| Chain selection | /internal, /api, /web, /login, URL lạ | Một chain đúng và fallback an toàn |
| Filter matching | GET đúng path, POST cùng path, OPTIONS, path gần giống | Filter custom chỉ active đúng phạm vi |
| Key conversion | Vắng key, blank, sai key, duplicated key | Không báo success; không lặng lẽ fallback |
| Mixed credentials | Basic+key, Bearer+key, Cookie+Bearer | Chính sách ambiguity rõ, không identity override |
| Basic auth | Valid/invalid credentials | 200/401 challenge đúng |
| Browser form login | Missing session, valid login/CSRF, logout | 302/login, session persistence đúng |
| Reactive context | Request có authentication, request sau không có key | Không cross-request context leak |
| Filter duplication | Mỗi request key đúng tăng manager attempt đúng 1 | Không double registration hoặc retry |
| Authorization | Authority thiếu, admin route, denyAll | 403/401 phù hợp, không lộ dữ liệu |
| Resource Server | Expired/bad sig/wrong aud JWT | Fail closed trước controller |
| HTTP error | Wrong credential vs missing credential | Failure handler và entry point khác nhau đúng policy |
| CSRF/CORS | Unsafe methods, preflight | Không tắt bảo vệ vì matcher |
| Multi-chain | Matcher hẹp trước rộng | Không bị shadow |
| Multi-instance | Key rotation, revocation, cache, counters | Không chấp nhận key đã thu hồi |
| Observability | auth attempt events, login failures | Không ghi password/API key/access token |

## 15. Checklist triển khai

1. Vẽ bảng route → credential scheme trước khi viết Security config.
2. Tạo `SecurityWebFilterChain` riêng cho nhóm route khác authentication model khi có thể.
3. Đặt `@Order` rõ cho các matcher giao nhau; matcher hẹp trước rộng.
4. Có fallback chain để URL lạ không tự thoát khỏi Spring Security.
5. Trong mỗi chain, dùng `authorizeExchange` để kiểm quyền; matcher của filter không thay authorization.
6. Với custom `AuthenticationWebFilter`, đặt `setRequiresAuthenticationMatcher` và `setServerAuthenticationConverter` tường minh.
7. Converter trả `Mono.empty()` chỉ khi credential của cơ chế vắng mặt, không khi credential sai.
8. Authentication manager chỉ chấp nhận token type đúng và trả lỗi khi credential không hợp lệ.
9. Khi request có credential mâu thuẫn, từ chối hoặc áp policy một cách minh bạch; không dùng “try until success”.
10. Tạo custom filter **trong chain**, không đăng ký đồng thời thành global `WebFilter` bean.
11. Giữ SecurityContext cho đúng scope request/session; tránh cross-request authentication leakage.
12. Khi dùng Basic/JWT, ưu tiên built-in authentication filters thay vì viết lại parsing/token validation.
13. Không dùng header `X-User`/`X-Role` như bằng chứng quyền; lấy permissions từ verified identity.
14. Bảo vệ API keys bằng TLS, high entropy, hashing, rotation, revocation, scope/tenant restrictions.
15. Giữ CSRF/CORS chính sách đúng threat model; kiểm cả OPTIONS và unsafe methods.
16. Test số lần converter/manager thực sự gọi cùng với response 200/401/403/302.
17. Theo dõi audit/trace không lộ credentials; tránh retry/auth loops và duplicated side effects.
18. Sau khi nâng Spring Security version, chạy lại ma trận matcher/filter order và HTTP behavior.

## 16. Bài tập tự luyện

1. Vẽ ba tầng matcher trong demo, chỉ rõ vì sao `/api/me` không gọi verifier API key.
2. Đổi `@Order(0)` và `@Order(2)` sao cho web catch-all đứng đầu. Kết quả sẽ thay đổi thế nào? Khôi phục ngay sau khi test.
3. Bỏ `setRequiresAuthenticationMatcher` của key filter, xem converter có bị gọi trên nhiều path trong cùng chain không; vì sao vẫn có thể là không cần thiết/không tối ưu?
4. Đổi converter sai key thành `Mono.empty()`. Giải thích nguy cơ khi sau này thêm một authentication filter khác.
5. Đưa custom `AuthenticationWebFilter` thành `@Bean` **và** `addFilterAt` để quan sát nguy cơ duplicate, sau đó sửa về chain-only.
6. Thêm `GET /internal/status` chỉ cho phép một API key có authority `SCOPE_status.read`; viết matcher và test tách role/scopes.
7. Cho `GET /internal/jobs` có cả `X-API-Key` và Basic. Vì sao demo trả 401 thay vì chấp nhận key hợp lệ?
8. Viết test nhận một header API key trống, hai header API key hoặc giá trị quá dài; định nghĩa policy fail closed.
9. Thêm JWT chain `/api/jwt/**` trước Basic chain `/api/**`, kiểm token sai audience bị 401.
10. Cho phép CORS preflight đúng Origin/Method/Header mà không đòi key ở OPTIONS. Đừng mở mọi route bằng permitAll.
11. Bổ sung POST và thử CSRF missing/valid; giải thích vì sao API-key matcher chỉ GET không tạo quyền POST.
12. So sánh `NoOpServerSecurityContextRepository` với `WebSessionServerSecurityContextRepository`. Vì sao Basic API stateless và web form login có kỳ vọng khác?
13. Đo converter calls và verifier attempts riêng bằng hai counters. Khi nào một request tăng converter mà không tăng verifier?
14. Thiết kế policy cho trường hợp Browser đã có session nhưng API request mang Bearer invalid: bạn sẽ từ chối hay fallback? Vì sao?
15. Dùng `ReactiveAuthenticationManagerResolver<ServerWebExchange>` cho multi-tenant đã allowlist; nêu cách phòng SSRF và issuer mix-up.
16. Đọc logs test, xác nhận **không** có API key, Basic password, Bearer token, cookie session dưới dạng plaintext.

## Tóm tắt

Chọn authentication mechanism trong Spring Security Reactive cần phân biệt **ba mức**: `securityMatcher` quyết định request thuộc **SecurityWebFilterChain nào**; `setRequiresAuthenticationMatcher` quyết định một `AuthenticationWebFilter` **có thử xác thực request đó không**; `ServerAuthenticationConverter` quyết định có credential phù hợp để tạo authentication attempt; còn `authorizeExchange.pathMatchers` kiểm **quyền truy cập sau xác thực**. Muốn tránh xử lý trùng, ưu tiên một chain cho mỗi nhóm route khác credential scheme, đặt thứ tự rõ ràng, không đăng ký custom WebFilter hai lần (global bean + addFilterAt), không chuyển sai credential thành Mono.empty, và giữ ranh giới authentication/authorization/session. Khi buộc hỗ trợ nhiều cơ chế trên cùng route, áp policy ambiguity/failure rõ ràng thay vì thử lần lượt đến khi thành công. Kiểm chứng bằng WebTestClient và đếm **manager attempts per request**, đồng thời giữ CSRF/CORS, JWT validation và object-level authorization.

## Tài liệu chính thức

1. Spring Security 6.5 — WebFlux Security, Multiple SecurityWebFilterChains: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
2. Spring Security 6.5 — AuthenticationWebFilter Javadoc (matcher, converter, failure/success, NoOp context): https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
3. Spring Security 6.3 — ServerAuthenticationConverter Javadoc: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html
4. Spring Security 6.5 — ServerHttpSecurity Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
5. Spring Security 6.3 — WebFlux authentication components: https://docs.spring.io/spring-security/reference/6.3/reactive/authentication/index.html
6. Spring Security 6.5 — Reactive Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
7. Spring Security 6.5 — WebFlux CSRF security: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
8. Spring Framework — WebFlux WebFilter and reactive request processing: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
