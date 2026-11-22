# ServerCsrfTokenRequestHandler và cơ chế che token chống BREACH

## Mục tiêu học tập

Trong **Spring Security Reactive (Spring WebFlux)**, CSRF token được sinh/lưu ở server và được đưa đến trình duyệt để bảo vệ các HTTP request thay đổi trạng thái. Tuy nhiên, nếu mỗi response HTML nén luôn phản chiếu cùng một CSRF token gốc, hệ thống có thể tạo bề mặt **BREACH**, một dạng tấn công kênh phụ dựa trên độ dài nội dung nén. Spring Security từ phiên bản 6.0 dùng **XOR masking** mặc định để thay đổi chuỗi token được xuất ra mà vẫn kiểm tra được cùng giá trị kỳ vọng.

Bài học thuộc ngữ cảnh **Bảo vệ CSRF** của module **Spring Security – reactive**. Chủ đề chính là **`ServerCsrfTokenRequestHandler` và cơ chế che token chống BREACH**.

Sau bài này, bạn có thể:

1. Giải thích khác biệt giữa CSRF và BREACH; vì sao HTTPS, SameSite, CORS và CSRF token giải quyết các vấn đề khác nhau.
2. Phân biệt **raw expected token**, **masked token**, **random mask** và **token rotation**, không cho rằng token masked khác nhau nghĩa là token phiên bị đổi.
3. Hiểu trách nhiệm của `CsrfWebFilter`, `ServerCsrfTokenRepository`, `ServerCsrfTokenRequestHandler`, `ServerCsrfTokenRequestResolver` và `CsrfToken`.
4. Nắm hành vi mặc định Spring Security 6.x: `XorServerCsrfTokenRequestAttributeHandler`; so sánh với `ServerCsrfTokenRequestAttributeHandler`.
5. Truy cập `Mono<CsrfToken>` ở `ServerWebExchange` theo reactive contract, không block hoặc tự subscribe.
6. Trình bày luồng form hidden field/header có token masked, giải XOR và so với raw expected trong WebSession.
7. Nhận diện lỗi khi SPA đọc raw CSRF token từ cookie nhưng gửi đến handler đang chờ masked token.
8. Viết ứng dụng Java 17+ Spring Boot 3.5/Spring Security 6.5 với `GET /csrf` và `POST /transfer`; kiểm thử token đúng/sai/khác phiên, 401/403, và mask thay đổi qua các request.
9. Đưa ra biện pháp bảo vệ XSS, tránh caching/logging token, cấu hình cookie/CORS, xử lý logout/timeout và các rủi ro vận hành.

Phần thực hành dùng **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring WebFlux, Gradle**. Chữ ký API và default behavior được trình bày theo nhánh 6.5; hãy kiểm tra version dependency đang chạy trước khi copy mã.

## 1. Mô hình đe dọa: CSRF là gì?

Trình duyệt thường tự gửi cookie phù hợp với domain/path/SameSite khi truy cập một website mà user đã đăng nhập. Kẻ tấn công điều khiển website khác có thể cố khiến trình duyệt của nạn nhân thực hiện POST tới endpoint nhạy cảm. Nếu server chỉ kiểm tra cookie, một request không được chủ tài khoản chủ ý vẫn có thể vượt qua authentication.

Ví dụ request tưởng tượng:

```http
POST /transfer HTTP/1.1
Host: bank.example
Cookie: SESSION=<session-id-of-victim>
Content-Type: application/x-www-form-urlencoded

recipient=attacker&amount=100
```

Đây là ví dụ để hiểu nguy cơ, không phải giao dịch thực. Việc browser gửi cookie cross-site còn phụ thuộc SameSite, request context và browser policy. Bài toán của CSRF protection là yêu cầu một token mà **client hợp lệ phải lấy từ origin/phiên đáng tin và chủ động thêm vào header hoặc form field**, không phải thứ trình duyệt tự gắn khi trang tấn công gửi form.

Mẫu phổ biến:

```text
GET /form (website hợp lệ):
  Server nạp/tạo expected CSRF token R
  Server render token cho frontend
  Browser giữ session cookie

POST /transfer:
  Cookie session + token trong _csrf field hoặc X-CSRF-TOKEN header
  CsrfWebFilter đọc expected R
  Request handler resolve actual token A từ request
  A hợp lệ và khớp R -> tiếp tục authentication/authorization/business
  Thiếu/sai -> từ chối, thường HTTP 403
```

**CSRF token không phải access token**. Nó không xác minh danh tính hay cấp quyền. Người có CSRF token hợp lệ vẫn cần authentication và authorization nếu endpoint yêu cầu.

### 1.1. Vì sao CSRF còn quan trọng với HTTP Basic và cookie-based SPA?

Một trình duyệt có thể tự gửi cookie, hoặc sử dụng credential HTTP Basic đã được browser cache, theo quy tắc của nó. Vì vậy không nên chỉ dựa vào câu “API của tôi là REST/JSON” để kết luận không có CSRF. Xác định liệu browser có tự đính credential hay không, có cookie-based login hay không, CORS/SameSite được cấu hình thế nào và có endpoint nào nhận request unsafe.

Đối với API thuần server-to-server dùng Authorization: Bearer được client chủ động thêm theo cách browser không tự cung cấp, threat model CSRF có thể khác. Quyết định bật/tắt CSRF phải dựa trên **cơ chế credential và client**, không dựa vào nhãn REST hay reactive.

### 1.2. HTTP methods và CSRF

Spring Security CSRF mặc định bảo vệ các phương thức **không an toàn**, thường là những phương thức ngoài GET/HEAD/OPTIONS/TRACE. Những phương thức “safe” phải được ứng dụng thiết kế để **không đổi trạng thái**. Nếu một GET thực hiện delete/transfer, kẻ tấn công có thể kích hoạt bằng cách tải URL, và CSRF mặc định không nhất thiết chặn vì GET được coi là safe.

Chuyển hành động thay đổi trạng thái sang POST/PUT/PATCH/DELETE và bảo vệ chúng đúng contract. Không tắt CSRF chỉ vì một POST của frontend hiện trả 403.

## 2. BREACH: rò bí mật qua độ dài response nén

BREACH là lớp tấn công liên quan **HTTP response compression**. Nếu attacker có thể điều khiển một phần dữ liệu được phản chiếu trong response cùng với secret và đo được độ dài nội dung đã nén qua nhiều lần thử, các khác biệt độ dài có thể tiết lộ thông tin về secret ngay cả khi truyền qua HTTPS.

Một form HTML có thể phản chiếu CSRF token:

```html
<form method="post" action="/transfer">
  <input type="hidden" name="_csrf" value="TOKEN_VALUE">
</form>
```

Nếu `TOKEN_VALUE` là cùng raw secret cố định lặp lại trên nhiều response nén, nó có thể tạo ra tín hiệu cho một số tình huống BREACH. Không phải mọi response nén đều mặc nhiên khai thác được: còn cần khả năng tạo/reflection chosen plaintext, quan sát độ dài và các điều kiện triển khai khác.

Từ Spring Security 6.0, WebFlux mặc định **mask token được phơi bày vào response**, nhằm tránh lặp một chuỗi raw token ổn định. Điều này **không thay thế** việc đánh giá compression khi các bí mật khác cũng được phản chiếu.

### 2.1. CSRF và BREACH không thay thế nhau

| Cơ chế | Mục tiêu | Không tự giải quyết |
|---|---|---|
| CSRF synchronizer token | Chặn request unsafe không được origin/user chủ ý | XSS, toàn bộ kênh phụ nén, lộ token qua logs |
| XOR masking | Thay representation token xuất ra để giảm rủi ro BREACH | Không thay CSRF validation hoặc mã hóa token |
| HTTPS | Bảo vệ nội dung trên đường truyền | Không chặn CSRF; không mặc nhiên xóa tín hiệu kích thước response nén |
| SameSite | Giới hạn một số trường hợp browser tự gửi cookie cross-site | Không thay token trong mọi flow |
| CORS | Kiểm soát JS cross-origin đọc response/gửi một số loại request | Không phải giải pháp tổng quát chống CSRF |
| CSP/XSS prevention | Giảm nguy cơ script xấu cùng origin | Không tự thay request handler hay repository |

## 3. Raw token, masked token và token rotation

### 3.1. Raw expected token R

`ServerCsrfTokenRepository` quyết định **tạo, lưu và nạp giá trị CSRF kỳ vọng**. Với WebFlux mặc định, `WebSessionServerCsrfTokenRepository` giữ raw token trong `WebSession`. Raw token phải ngẫu nhiên/khó đoán, không suy ra từ username hay một giá trị cố định.

Ví dụ ký hiệu:

```text
Raw expected token phía server: R
  - được repository lưu/nạp
  - gắn với WebSession hoặc storage strategy
  - là đích đối chiếu khi filter xác minh request
```

Không cần hiển thị R nguyên văn trong mỗi response. Với session còn hiệu lực, repository có thể tiếp tục sử dụng R qua nhiều request.

### 3.2. Masked representation V

`XorServerCsrfTokenRequestAttributeHandler` dùng random mask để tạo representation mới cho token ở mỗi lần expose thích hợp.

Mô hình trực giác:

```text
Cùng một phiên có raw R:

GET /csrf lần 1:
  ngẫu nhiên M1
  masked representation V1 = Encode(M1, M1 XOR R)

GET /csrf lần 2:
  ngẫu nhiên M2
  masked representation V2 = Encode(M2, M2 XOR R)

V1 và V2 thường khác nhau
nhưng đều có thể được handler giải thành R
```

Đây là **mô hình giải thích**, không phải lời hứa về định dạng byte/Base64 cụ thể để tự lập trình lại. Framework chịu trách nhiệm xử lý encoding/decoding, kích thước, random và malformed input.

### 3.3. Masked khác nhau không có nghĩa raw đã rotate

- **Masking** làm thay đổi cách hiển thị của cùng expected token.
- **Rotation** là thay token thật trong repository.
- **Invalidation** xóa token expected, thường liên quan logout/session timeout hoặc custom lifecycle.
- **Expiry** có thể làm cookie/session cũ không còn ánh xạ đến expected token.
- Khi đã rotate, masked token cũ không khớp expected mới; khi chỉ mask mới, masked token trước vẫn có thể hợp lệ với cùng raw R và session.

Đừng viết unit test kiểu `assertEquals(csrf1.token(), csrf2.token())` cho hai GET độc lập và coi việc khác nhau là bug. Tương tự, đừng tin rằng token mới có nghĩa đã đổi phiên đăng nhập.

### 3.4. XOR masking không phải encryption

XOR representation gồm dữ liệu để handler khôi phục raw token; nó không phải ciphertext chỉ người có khóa bí mật mới giải được. Masking chỉ nhằm làm representation ngẫu nhiên theo từng lần xuất, giảm tín hiệu độ dài khi phản chiếu secret. Không gửi masked token cho origin xấu, không log nó và không coi masked token đã “an toàn để công khai”.

## 4. Các thành phần chính của Spring Security WebFlux CSRF

| Thành phần | Trách nhiệm |
|---|---|
| `CsrfWebFilter` | Kích hoạt CSRF protection, expose token và kiểm tra unsafe requests |
| `CsrfToken` | Có `getToken()`, `getHeaderName()`, `getParameterName()` |
| `DefaultCsrfToken` | Implementation cụ thể, hữu ích trong unit test |
| `ServerCsrfTokenRepository` | Tạo/lưu/nạp expected raw token cho exchange |
| `WebSessionServerCsrfTokenRepository` | Repository mặc định, gắn token với WebSession |
| `CookieServerCsrfTokenRepository` | Dùng cookie `XSRF-TOKEN` làm nguồn lưu raw token |
| `ServerCsrfTokenRequestHandler` | Làm token sẵn có qua exchange attributes và hỗ trợ resolve token từ request |
| `ServerCsrfTokenRequestResolver` | Giải actual token mà client gửi từ header/form data |
| `ServerCsrfTokenRequestAttributeHandler` | Plain request handler, không có XOR masking |
| `XorServerCsrfTokenRequestAttributeHandler` | Request handler mặc định 6+, masking + unmasking |
| `ServerHttpSecurity.CsrfSpec` | DSL chọn token repository, handler và những điều kiện CSRF |

**Đúng package:** WebFlux dùng `org.springframework.security.web.server.csrf`; Servlet dùng `org.springframework.security.web.csrf`. Đừng import `XorCsrfTokenRequestAttributeHandler` của Servlet khi cấu hình `ServerHttpSecurity`.

### 4.1. Contract của ServerCsrfTokenRequestHandler

Giao diện WebFlux có method quan trọng:

```java
// Chỉ là mô hình chữ ký, KHÔNG định nghĩa lại interface.
void handle(ServerWebExchange exchange, Mono<CsrfToken> csrfToken);

Mono<String> resolveCsrfTokenValue(
    ServerWebExchange exchange,
    CsrfToken csrfToken
);
```

`handle` đưa token vào `ServerWebExchange` cho view/controller sử dụng và có thể biến đổi representation. `resolveCsrfTokenValue` lấy actual token do request gửi. Các method thuộc `ServerCsrfTokenRequestHandler` và parent `ServerCsrfTokenRequestResolver`; xem Javadoc đúng version để biết default method và chi tiết.

Một custom handler không được tự tạo subscription tùy tiện để đẩy token vào response. Nếu cần materialize token lazy, compose publisher với response lifecycle. Thông thường dùng handler chuẩn thay vì tự triển khai.

### 4.2. Attribute chứa Mono<CsrfToken>, không phải CsrfToken trực tiếp

`CsrfWebFilter` exposes `Mono<CsrfToken>` trong attribute có key:

```java
CsrfToken.class.getName()
```

Giá trị key thường là `org.springframework.security.web.server.csrf.CsrfToken`. Đọc trong controller WebFlux:

```java
Mono<CsrfToken> csrfMono =
    exchange.getAttribute(CsrfToken.class.getName());

return csrfMono.map(csrf -> csrf.getToken());
```

Đây là snippet, cần context method, imports và null handling. Không cast trực tiếp attribute thành `CsrfToken`, không `.block()` trên Netty event loop và không `.subscribe()` riêng. View/controller nên return/compose publisher để WebFlux subscribe.

### 4.3. Repository và handler là hai chiến lược riêng

```text
ServerCsrfTokenRepository:
  expected raw R
      |
      v
CsrfWebFilter / Mono<CsrfToken>
      |
      v
ServerCsrfTokenRequestHandler.handle(exchange, tokenMono)
      |
      +-- expose: Xor...handler tạo masked V
      |             view/JSON/form gửi V cho frontend
      |
      +-- POST unsafe:
            Browser gửi Cookie phiên và V (header hoặc _csrf)
            |
            v
            handler.resolveCsrfTokenValue(...)
            |
            v
            giải V thành raw actual A
            |
            v
            filter so A với expected raw R
            |
            +-- match: tiếp tục request
            +-- mismatch/missing: deny, thường 403
```

Thay repository không tự đổi cách mask. Thay request handler không tự đổi nơi lưu token. Sự khác nhau này đặc biệt quan trọng với frontend JavaScript đọc raw cookie.

## 5. Hành trình GET và POST với token được che

### 5.1. GET trang hoặc GET /csrf

Một GET bình thường không cần CSRF validation nếu đúng safe method, và token có thể được **deferred/lazy** để giảm việc nạp session vô ích. Nhưng khi controller hoặc view **subscribe `Mono<CsrfToken>`** để xuất token, repository có thể nạp hoặc tạo raw expected token và lưu vào WebSession/cookie theo cấu hình.

```text
GET /csrf
  -> CsrfWebFilter chuẩn bị Mono<CsrfToken>
  -> request handler đặt publisher vào exchange attribute
  -> controller map publisher thành JSON/header/view model
  -> subscription thực sự đòi token
  -> repository lấy/tạo R
  -> XOR handler expose V = masked(R)
  -> response trả V
  -> session cookie được gửi khi session có state cần lưu
```

Việc GET /csrf công khai có thể tạo WebSession dù user **chưa đăng nhập**; session/cookie không đồng nghĩa user đã authenticated. Ngược lại, một GET public không đọc token không nhất thiết tạo CSRF state.

### 5.2. POST cùng session, masked token trong header

```http
POST /transfer HTTP/1.1
Host: app.example
Cookie: SESSION=<current-session-id>
Authorization: Basic <credentials>
X-CSRF-TOKEN: <masked-token-from-same-session>
Content-Type: application/json

{}
```

Đây là mẫu request, không phải credential/token thật. `CsrfWebFilter` đọc expected raw R từ repository, handler giải masked actual A, rồi filter so A với R. Token đúng **chỉ** cho POST đi tiếp; authentication/authorization vẫn có thể từ chối.

### 5.3. HTML form

Mẫu form:

```html
<form method="post" action="/transfer">
  <input type="hidden" name="_csrf" value="MASKED_FROM_SERVER">
  <button type="submit">Confirm</button>
</form>
```

`MASKED_FROM_SERVER` chỉ để minh họa. Form thật phải render giá trị từ CSRF token mà Spring Security expose cho **đúng phiên**. Thymeleaf tích hợp với `CsrfRequestDataValueProcessor` có thể tự chèn field vào form unsafe method khi được cấu hình đúng. Nếu tự render, hãy đọc `Mono<CsrfToken>` và HTML-escape thuộc tính.

Không đưa token vào URL, vì URL có thể vào log, browser history, analytics và referrer.

### 5.4. Mất cookie hay khác session vẫn là token sai

```text
GET /csrf với cookie session A -> masked V_A

POST /transfer:
  cookie session B
  token V_A
  -> unmask thành raw R_A
  -> expected repository ở B là R_B
  -> R_A != R_B -> deny
```

Không sửa bằng cách cho server chấp nhận mọi token được che hợp lệ về mặt định dạng; phải đối chiếu với expected raw của context đang nhận request.

## 6. ServerCsrfTokenRequestAttributeHandler và XorServerCsrfTokenRequestAttributeHandler

Spring Security 5.8 dùng `ServerCsrfTokenRequestAttributeHandler` làm default; từ **6.0**, WebFlux đổi sang `XorServerCsrfTokenRequestAttributeHandler` để giảm nguy cơ BREACH.

| Đặc điểm | Plain handler | XOR handler |
|---|---|---|
| Class | `ServerCsrfTokenRequestAttributeHandler` | `XorServerCsrfTokenRequestAttributeHandler` |
| Token expose | Raw token representation | Masked representation |
| Token resolve | Plain header/form value | Unmask header/form value |
| Chống phản chiếu raw token ổn định qua compression | Không có masking | Có random masking |
| Default 5.8 | Có | Không |
| Default 6.0+ | Không | **Có** |
| Khi dùng với SPA raw cookie header | Có thể tương thích theo cấu hình | Cần chú ý raw/masked mismatch |
| Đối với HTML form server-rendered | Hoạt động nhưng thiếu mitigation | Ưu tiên giữ default |

XOR handler từ Spring Security 6.x **không cần thêm config** nếu bạn dùng default CSRF. Nếu muốn biểu lộ cấu hình một cách rõ ràng:

```java
// Snippet trong @Bean SecurityWebFilterChain:
return http
    .csrf(csrf -> csrf
        .csrfTokenRequestHandler(
            new XorServerCsrfTokenRequestAttributeHandler()))
    .build();
```

Nếu buộc phải chuyển về plain:

```java
// Opt-out BREACH masking có chủ đích; KHÔNG phải fix 403 mặc định.
.csrf(csrf -> csrf
    .csrfTokenRequestHandler(
        new ServerCsrfTokenRequestAttributeHandler()))
```

**Không nên làm vậy chỉ vì frontend gửi token sai.** Việc tắt XOR có thể khiến raw token ổn định được phản chiếu vào các response nén. Hãy kiểm tra integration và threat model trước khi thay đổi protection.

## 7. SPA raw CSRF cookie là trường hợp dễ nhầm

### 7.1. CookieServerCsrfTokenRepository

`CookieServerCsrfTokenRepository` có thể ghi cookie `XSRF-TOKEN` và đọc giá trị client gửi từ header `X-XSRF-TOKEN` hoặc form parameter `_csrf` theo convention. `withHttpOnlyFalse()` cho phép JavaScript đọc cookie raw.

Một cấu hình mẫu:

```java
// Snippet chỉ chọn nơi lưu token; chưa hoàn chỉnh cho SPA.
.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieServerCsrfTokenRepository.withHttpOnlyFalse()))
```

Đây là lựa chọn có đánh đổi: nếu frontend **không cần** JavaScript đọc cookie, giữ HttpOnly để giảm bề mặt truy cập. Cookie token không thay authentication cookie, và `withHttpOnlyFalse()` không tự bật đúng request resolver cho mọi SPA.

### 7.2. Vì sao raw header có thể bị 403 dưới XOR default?

Một JS client đọc raw `XSRF-TOKEN` từ cookie rồi đặt vào header `X-XSRF-TOKEN`. Nếu request handler đang giả định actual value là **masked**, nó sẽ xử lý header theo con đường unmask, không phải “raw token từ repository”. Raw và masked là hai representation khác nhau; request có thể bị từ chối mặc dù browser cookie chứa raw token đúng theo repository.

Muốn hỗ trợ cả hai, cần thiết kế nhất quán:

- HTML form: XOR masked field để giảm BREACH reflection.
- SPA raw cookie header: request resolver thích hợp nhận raw header và so với raw expected.
- Nếu dùng endpoint `GET /csrf` phát masked token trong JSON, frontend có thể gửi chính **masked value** dưới header đúng tên, không cần đọc raw XSRF cookie.
- Làm mới token theo lifecycle sau login/logout, session timeout hoặc reset.
- Không tự tắt CSRF hay BREACH chỉ để POST thành công.
- CORS phải hạn chế origin và credentialed access; nếu attacker đọc được token, CSRF protection giảm hiệu quả.

**Không copy code Servlet `SpaCsrfTokenRequestHandler` nguyên văn**: Spring Servlet dùng `HttpServletRequest`/`Supplier<CsrfToken>`, còn WebFlux dùng `ServerWebExchange`/`Mono<CsrfToken>`. Với custom reactive handler, không tự `subscribe()` vào Mono deferred trong `handle`.

### 7.3. Một lựa chọn giản dị cho SPA

Với session-based backend WebFlux, endpoint same-origin `GET /csrf` có thể trả token **đã mask** trong JSON, client giữ session cookie rồi gửi giá trị đó ở header trong các request POST. Bài demo dưới đây minh họa chính luồng này.

Token endpoint phải có cache policy phù hợp (thường `no-store`), TLS và không bị cross-origin attacker đọc. Khi token/session hết hiệu lực, client cần lấy mới, nhưng **không tự retry vô hạn các POST đã có side effect**.

## 8. Demo chạy được Java 17+: Spring Boot 3.x và Security 6.x

Ứng dụng có:

- `GET /public`: public, không yêu cầu CSRF.
- `GET /csrf`: lấy masked token qua `Mono<CsrfToken>` từ request attribute, trả JSON cùng metadata header/form field.
- `POST /transfer`: cần HTTP Basic authentication và CSRF token; mô phỏng một mutation bằng in-memory counter.
- `WebSessionServerCsrfTokenRepository`: expected raw token.
- `XorServerCsrfTokenRequestAttributeHandler`: expose masked token, unmask khi nhận.
- Integration tests dùng cùng cookie để kiểm chứng masked token round-trip.

**Không có giao dịch tài chính thật.** Đây là một demo bảo mật để học request flow.

### 8.1. Tạo project và dependencies

Tạo project Gradle Groovy qua [Spring Initializr](https://start.spring.io/), chọn Java 17+, Spring Boot 3.5.x và dependencies Spring Reactive Web, Spring Security, Spring Boot Starter Test, Spring Security Test, Reactor Test.

Phần `dependencies` của `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Đây chỉ là block dependencies; giữ plugins, repositories, Java toolchain và Gradle wrapper do Initializr sinh. Không thêm `spring-boot-starter-web`: với cả MVC và WebFlux starters, Spring Boot 3.x thường chọn inbound Servlet theo default.

Bố cục:

```text
src/main/java/demo/csrfxor/
  CsrfXorApplication.java
  SecurityConfig.java
  CsrfController.java
  TransferController.java
src/test/java/demo/csrfxor/
  CsrfXorIntegrationTests.java
  XorHandlerTests.java
```

### 8.2. CsrfXorApplication.java

```java
package demo.csrfxor;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfXorApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfXorApplication.class, args);
    }
}
```

### 8.3. SecurityConfig.java

```java
package demo.csrfxor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;
import org.springframework.security.web.server.csrf.XorServerCsrfTokenRequestAttributeHandler;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public", "/csrf")
                    .permitAll()
                .pathMatchers(HttpMethod.POST, "/transfer")
                    .authenticated()
                .anyExchange().denyAll())
            .csrf(csrf -> csrf
                .csrfTokenRepository(
                    new WebSessionServerCsrfTokenRepository())
                .csrfTokenRequestHandler(
                    new XorServerCsrfTokenRequestAttributeHandler()))
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    public MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(alice);
    }
}
```

Giải thích:

1. `ServerHttpSecurity`, `SecurityWebFilterChain` và `@EnableWebFluxSecurity` thuộc WebFlux.
2. `/csrf` được `permitAll` để client same-origin lấy token trước login; không có nghĩa mọi third-party origin có thể đọc response qua CORS.
3. `WebSessionServerCsrfTokenRepository` giữ expected raw token trong phiên.
4. `XorServerCsrfTokenRequestAttributeHandler` là default Security 6 nhưng khai báo tường minh để nhìn rõ.
5. HTTP Basic cung cấp authentication cho demo; Base64 không phải encryption nên production phải chạy HTTPS.
6. `POST /transfer` vừa cần Basic credential vừa cần CSRF token. Một `403` do CSRF khác `401` do chưa xác thực.
7. CSRF **không bị tắt**. `formLogin` tắt để endpoint API không redirect tới trang HTML khi thiếu Basic.
8. Credential in-memory là dữ liệu mẫu; password trong account store được băm bởi `PasswordEncoder`, không dùng password ví dụ trong sản phẩm.

### 8.4. CsrfController.java: trả masked token

```java
package demo.csrfxor;

import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class CsrfController {

    public record TokenView(
            String headerName,
            String parameterName,
            String token) {
    }

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/csrf")
    public Mono<TokenView> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> token =
            exchange.getAttribute(CsrfToken.class.getName());

        if (token == null) {
            return Mono.error(new IllegalStateException(
                "CsrfWebFilter did not expose a CSRF token"));
        }

        exchange.getResponse().getHeaders()
            .setCacheControl("no-store");

        return token.map(t -> new TokenView(
            t.getHeaderName(),
            t.getParameterName(),
            t.getToken()));
    }
}
```

**Điểm học chính:** `exchange.getAttribute(...)` trả publisher mà handler đặt vào exchange. `token.map(...)` được WebFlux subscribe và có thể khiến expected raw token được tạo/nạp, session state được lưu, XOR handler trả masked representation. Không `block()` hay tự `subscribe()` trong controller.

Một endpoint `GET /csrf` trả giá trị bảo mật dù không đòi authentication: chỉ được client hợp lệ same-origin đọc, không bị shared-cache và không nới CORS vô điều kiện. `Cache-Control: no-store` giảm nguy cơ browser/proxy cache; production còn cần bảo vệ XSS, TLS và logging.

### 8.5. TransferController.java: side effect quan sát được

```java
package demo.csrfxor;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class TransferController {

    private final AtomicInteger completed = new AtomicInteger();

    public record TransferResult(String status, int sequence) {
    }

    @PostMapping("/transfer")
    public Mono<TransferResult> transfer() {
        return Mono.fromSupplier(() ->
            new TransferResult(
                "accepted",
                completed.incrementAndGet()));
    }

    public int completedCount() {
        return completed.get();
    }

    // Dùng nội bộ trong JUnit, không expose thành HTTP endpoint.
    public void resetForTests() {
        completed.set(0);
    }
}
```

Counter tăng **chỉ khi** request vượt qua CSRF, authentication, authorization và controller được subscribe. Nó không phải transaction thật và không phù hợp sản phẩm tài chính. Test sẽ xác minh counter bằng 0 khi token thiếu/sai.

### 8.6. Chạy ứng dụng

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Kiểm tra route công khai:

```bash
curl -i http://localhost:8080/public
```

Dự kiến body:

```text
public
```

Lấy masked token và lưu cookie cho lần sau:

```bash
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/csrf
```

Response `GET /csrf` trả JSON có `headerName`, `parameterName`, `token`; server có thể phát session cookie `SESSION` nếu repository đã lưu state. Không đưa token/cookie thật vào log công khai. Để POST bằng curl, phải gửi **đúng masked value từ JSON** qua header cùng tên và cookie từ file; nếu không, CSRF trả 403. Dùng `WebTestClient` dưới đây sẽ tự xử lý những bước đó mà không phải copy token trong shell history.

## 9. Integration tests: token masked qua hai HTTP requests

Dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và `WebTestClient` kiểm tra luồng thật qua WebFlux filters. Test **không tự tạo token giả**; nó lấy token do endpoint phát, giữ session cookie và gửi lại masked token đúng cách.

Tạo `src/test/java/demo/csrfxor/CsrfXorIntegrationTests.java`:

```java
package demo.csrfxor;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CsrfXorIntegrationTests {

    @Autowired
    WebTestClient client;

    @Autowired
    TransferController transfer;

    @BeforeEach
    void reset() {
        transfer.resetForTests();
    }

    private EntityExchangeResult<CsrfController.TokenView> initial() {
        return client.get().uri("/csrf")
            .exchange()
            .expectStatus().isOk()
            .expectBody(CsrfController.TokenView.class)
            .returnResult();
    }

    private EntityExchangeResult<CsrfController.TokenView> again(
            String cookie) {
        return client.get().uri("/csrf")
            .cookie("SESSION", cookie)
            .exchange()
            .expectStatus().isOk()
            .expectBody(CsrfController.TokenView.class)
            .returnResult();
    }

    private String cookie(
            EntityExchangeResult<CsrfController.TokenView> result) {
        ResponseCookie c =
            result.getResponseCookies().getFirst("SESSION");
        assertNotNull(c);
        return c.getValue();
    }

    private CsrfController.TokenView token(
            EntityExchangeResult<CsrfController.TokenView> result) {
        CsrfController.TokenView v = result.getResponseBody();
        assertNotNull(v);
        assertNotNull(v.token());
        assertNotNull(v.headerName());
        return v;
    }

    @Test
    void publicGetWorksWithoutCsrf() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");

        assertEquals(0, transfer.completedCount());
    }

    @Test
    void csrfEndpointExposesMetadataAndSession() {
        var result = initial();
        var v = token(result);

        assertNotNull(cookie(result));
        assertEquals("X-CSRF-TOKEN", v.headerName());
        assertEquals("_csrf", v.parameterName());
    }

    @Test
    void missingTokenBlocksMutationEvenWithCredentials() {
        client.post().uri("/transfer")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isForbidden();

        assertEquals(0, transfer.completedCount());
    }

    @Test
    void maskedHeaderWithSameSessionAllowsPost() {
        var result = initial();
        var v = token(result);
        String session = cookie(result);

        client.post().uri("/transfer")
            .cookie("SESSION", session)
            .headers(h -> {
                h.setBasicAuth("alice", "alice-pass");
                h.set(v.headerName(), v.token());
            })
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("accepted")
            .jsonPath("$.sequence").isEqualTo(1);

        assertEquals(1, transfer.completedCount());
    }

    @Test
    void maskedTokenWithoutSessionIsForbidden() {
        var v = token(initial());

        client.post().uri("/transfer")
            .headers(h -> {
                h.setBasicAuth("alice", "alice-pass");
                h.set(v.headerName(), v.token());
            })
            .exchange()
            .expectStatus().isForbidden();

        assertEquals(0, transfer.completedCount());
    }

    @Test
    void tokenFromDifferentSessionIsForbidden() {
        var sessionA = initial();
        var sessionB = initial();

        var tokenA = token(sessionA);
        String cookieB = cookie(sessionB);

        client.post().uri("/transfer")
            .cookie("SESSION", cookieB)
            .headers(h -> {
                h.setBasicAuth("alice", "alice-pass");
                h.set(tokenA.headerName(), tokenA.token());
            })
            .exchange()
            .expectStatus().isForbidden();

        assertEquals(0, transfer.completedCount());
    }

    @Test
    void twoMasksInSameSessionAreBothValid() {
        var first = initial();
        String session = cookie(first);
        var v1 = token(first);
        var v2 = token(again(session));

        assertNotEquals(v1.token(), v2.token());

        client.post().uri("/transfer")
            .cookie("SESSION", session)
            .headers(h -> {
                h.setBasicAuth("alice", "alice-pass");
                h.set(v1.headerName(), v1.token());
            })
            .exchange()
            .expectStatus().isOk();

        client.post().uri("/transfer")
            .cookie("SESSION", session)
            .headers(h -> {
                h.setBasicAuth("alice", "alice-pass");
                h.set(v2.headerName(), v2.token());
            })
            .exchange()
            .expectStatus().isOk();

        assertEquals(2, transfer.completedCount());
    }

    @Test
    void validCsrfDoesNotReplaceAuthentication() {
        var result = initial();
        var v = token(result);
        String session = cookie(result);

        client.post().uri("/transfer")
            .cookie("SESSION", session)
            .header(v.headerName(), v.token())
            .exchange()
            .expectStatus().isUnauthorized();

        assertEquals(0, transfer.completedCount());
    }
}
```

**8 test cases** bao gồm GET public, GET CSRF, thiếu token, token đúng, thiếu session, khác session, hai masked values khác nhau trong cùng session và CSRF pass nhưng chưa authentication. Test xác minh cả HTTP response lẫn counter, không chỉ status.

### 9.1. Lưu ý về session cookie trong test

Trong Spring WebFlux default, cookie session thường tên `SESSION`. Nếu project thay `WebSessionIdResolver` hoặc cookie name, hãy đọc tên cookie thật từ response. Test giữ cookie sau `GET /csrf` để server tìm lại expected raw token.

Test `twoMasksInSameSessionAreBothValid` dùng `assertNotEquals` với random mask: xác suất hai masked strings trùng là cực thấp nhưng về lý thuyết không bằng 0. Không dùng fixed random yếu ngoài production chỉ để test dễ.

### 9.2. Vì sao không dùng mutateWith(csrf()) cho tất cả?

`SecurityMockServerConfigurers.csrf()` hữu ích cho test security nói chung. Nhưng trong bài này, mục tiêu là kiểm tra **real masked token từ ServerCsrfTokenRequestHandler**, cookie round-trip và resolver trên POST. Nếu chỉ tự gắn token bằng test helper, lỗi frontend dùng raw cookie value với XOR resolver có thể bị bỏ sót. Đây là lý do integration test lấy token qua endpoint thay vì tự tạo.

## 10. Unit tests cho XOR handler và plain handler

Tạo `src/test/java/demo/csrfxor/XorHandlerTests.java`:

```java
package demo.csrfxor;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.security.web.server.csrf.DefaultCsrfToken;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRequestAttributeHandler;
import org.springframework.security.web.server.csrf.XorServerCsrfTokenRequestAttributeHandler;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class XorHandlerTests {

    private final CsrfToken raw =
        new DefaultCsrfToken(
            "X-CSRF-TOKEN", "_csrf", "unit-test-raw-value");

    private String render(
            XorServerCsrfTokenRequestAttributeHandler handler) {
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/form").build());

        handler.handle(exchange, Mono.just(raw));

        Mono<CsrfToken> exposed =
            exchange.getAttribute(CsrfToken.class.getName());
        assertNotNull(exposed);

        // Chỉ ở unit test, KHÔNG gọi block() trên Netty event loop.
        CsrfToken value = exposed.block();
        assertNotNull(value);
        return value.getToken();
    }

    @Test
    void xorRepresentationChangesEachTime() {
        var handler =
            new XorServerCsrfTokenRequestAttributeHandler();

        String first = render(handler);
        String second = render(handler);

        assertNotEquals(raw.getToken(), first);
        assertNotEquals(first, second);
    }

    @Test
    void resolverRecoversRawFromMaskedHeader() {
        var handler =
            new XorServerCsrfTokenRequestAttributeHandler();
        String masked = render(handler);

        var post = MockServerWebExchange.from(
            MockServerHttpRequest.post("/transfer")
                .header("X-CSRF-TOKEN", masked)
                .build());

        StepVerifier.create(
                handler.resolveCsrfTokenValue(post, raw))
            .expectNext(raw.getToken())
            .verifyComplete();
    }

    @Test
    void plainHandlerExposesUnmaskedToken() {
        var handler =
            new ServerCsrfTokenRequestAttributeHandler();
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/form").build());

        handler.handle(exchange, Mono.just(raw));

        Mono<CsrfToken> exposed =
            exchange.getAttribute(CsrfToken.class.getName());
        assertNotNull(exposed);
        CsrfToken value = exposed.block();
        assertNotNull(value);

        assertEquals(raw.getToken(), value.getToken());
    }
}
```

Unit tests kiểm tra behavior công khai: XOR có masked value khác raw, masking có ngẫu nhiên, masked header được resolve về raw expected, còn plain handler expose raw. Không tự kiểm tra cấu trúc Base64 nội bộ vì framework có thể thay implementation. `block()` chỉ dùng trong test, không đặt trong reactive handler.

Chạy:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

Kỳ vọng **11 tests** được định nghĩa (8 integration + 3 unit) trong cấu hình project trên. Đây là kỳ vọng về nội dung code, **không phải xác nhận đã chạy Gradle**. Nếu version adapter có khác biệt, xem actual response/cookie, dependency tree, request handler và test logs rồi điều chỉnh trên cơ sở contract chứ không sửa expected status mù.

## 11. Lỗi thường gặp sau khi nâng Spring Security

| Triệu chứng | Nguyên nhân có thể | Cách giải quyết |
|---|---|---|
| GET form trả token dài hơn trước | XOR representation chứa mask/encoding | Giữ nguyên chuỗi, không cắt token |
| Token khác ở hai GET cùng session | Random masking theo mỗi exposure | Hành vi dự kiến, không coi như rotate |
| POST SPA raw XSRF header trả 403 sau upgrade | Request handler đang unmask nhưng client gửi raw | Dùng resolver tương thích hoặc gửi masked token |
| POST thiếu token trả 403 | Bị CSRF filter chặn | Đọc token đúng session, gửi header/form field |
| HTTP Basic đúng nhưng POST 403 | CSRF chưa đúng hoặc thiếu quyền | Tách debug CSRF 403 với authorization 403 |
| Token đúng nhưng thiếu auth trả 401 | CSRF không xác thực user | Gửi credential hợp lệ qua HTTPS |
| Token từ session A với cookie B bị 403 | Expected raw khác nhau | Giữ cookie/token cùng phiên |
| JSON /csrf không có token | Filter không nằm trong chain hoặc publisher không được materialize | Kiểm tra chain, exchange attribute và reactive composition |
| Cookie đọc được nhưng request sai | Header name, raw/masked, CORS, session, token expiry | Đối chiếu repository và handler |
| Tắt CSRF làm test pass | Đã bỏ cơ chế bảo vệ | Không xem đây là fix, tìm đúng token flow |
| Tắt XOR làm post thành công | Đã bỏ BREACH mitigation | Thiết kế client/server representation thay vì tắt protection |
| Lấy `CsrfToken` bằng cast trực tiếp | Attribute chứa `Mono<CsrfToken>` | Compose publisher, không cast |
| `block()` trong controller | Nguy cơ block event loop | Return `Mono` |
| Cache CDN chứa JSON CSRF token | Shared cache không phân biệt user/session | `no-store`, kiểm tra proxy |
| Logout/login xong token cũ bị 403 | Raw token đã bị xóa/rotate | Tải token mới theo lifecycle |
| Multipart request với token đặt trong body không chạy | Resolver/multipart handling mặc định khác | Đánh giá `tokenFromMultipartDataEnabled` và ưu tiên header khi có JS |
| Copy `XorCsrfTokenRequestAttributeHandler` của Servlet | Sai loại API | Dùng `XorServerCsrfTokenRequestAttributeHandler` WebFlux |

### 11.1. Những log an toàn để debug

Ghi request ID, HTTP path đã loại dữ liệu nhạy cảm, method, source của token (header/form), lý do token missing/invalid ở dạng category và status. Không log **raw token, masked token, Authorization, Cookie, session ID** hoặc toàn bộ request body. Dùng test environment và browser Developer Tools để quan sát cookie/header khi cần, không paste credential/token thật vào ticket.

### 11.2. 403 có nhiều nguyên nhân

`403` trên POST không luôn là CSRF; có thể là role/permission thiếu sau khi CSRF pass. Ngược lại, `401` có thể xuất hiện khi token CSRF hợp lệ nhưng chưa xác thực. Phải debug theo pipeline: CSRF validation, authentication, authorization và handler. Chỉ nhìn HTTP status là chưa đủ.

## 12. Cookie flags, CORS, XSS và compression

### 12.1. Cookie

Session cookie nên có `Secure` qua HTTPS, `HttpOnly` và `SameSite` phù hợp. `SameSite` hỗ trợ giảm một số luồng cross-site nhưng không thay CSRF token trong mọi trường hợp. Cookie `XSRF-TOKEN` có thể phải đọc được bằng JavaScript nếu dùng raw-cookie SPA pattern; `HttpOnly=false` là một đánh đổi có chủ đích, không bật nếu không cần.

### 12.2. CORS

CORS không tự kiểm tra CSRF và CSRF cũng không thay CORS. Nếu server cho phép origin không tin cậy đọc `GET /csrf` cùng credential, attacker có thể lấy token, làm suy yếu bảo vệ. Hạn chế allowlist origins, methods, headers và credentials; không phản chiếu bất kỳ `Origin` nào rồi cho đọc token.

### 12.3. XSS

Nếu attacker thực thi JavaScript cùng origin (XSS), script có thể gọi `GET /csrf` hợp lệ và sử dụng token. CSRF protection không chống XSS. Cần escaping, CSP, dependency hygiene, hạn chế script bên thứ ba và review cách render dữ liệu không tin cậy.

### 12.4. Session expiry và refresh

Raw expected token có thể bị xóa khi session hết hạn/logout/login lifecycle, hoặc custom repository rotate token. SPA phải lấy token mới sau các chuyển trạng thái phù hợp. Nhưng CSRF token không phải idempotency key; một request POST lỗi mạng không nên tự retry không giới hạn nếu mutation có thể đã thành công.

### 12.5. Response compression

Masking giảm phản chiếu CSRF secret ổn định trong HTML/JSON, nhưng không bảo vệ mọi secret được render. Nếu application phản chiếu API keys, PII hoặc session-specific secrets cùng attacker-controlled plaintext trong response nén, cần đánh giá BREACH threat model rộng hơn. HTTPS vẫn cần nhưng không loại bỏ toàn bộ side channel độ dài.

## 13. Bài tập có đáp án

### Bài 1. Hai masked tokens khác nhau có phải token hết hạn?

User GET /csrf hai lần trong cùng WebSession: V1 != V2. Có thể gửi V1 để POST không?

**Đáp án:** Có thể, nếu raw token kỳ vọng trong repository chưa đổi và session còn hợp lệ. XOR tạo mask mới mỗi lần expose; hai representation có thể giải về cùng raw token.

### Bài 2. Cứ đổi mask là đổi session ID?

**Đáp án:** Không. Mask chỉ thay biểu diễn CSRF token. Session ID và raw expected token có lifecycle riêng; không suy diễn từ chuỗi masked.

### Bài 3. Tại sao không gửi raw XSRF cookie vào XOR resolver?

**Đáp án:** Vì handler đang giải masked representation, không chỉ so plain raw string. Client và server phải thống nhất cách resolve; cần compatible handler cho raw header hoặc gửi masked token do server expose.

### Bài 4. Có token hợp lệ là được truy cập tài nguyên?

**Đáp án:** Không. CSRF token không thay authentication hay authorization. API vẫn có thể trả 401 hoặc 403 vì user thiếu credential/role.

### Bài 5. Vì sao GET /csrf có thể tạo SESSION cookie trước login?

**Đáp án:** Endpoint cần materialize token; WebSession repository có thể start session để lưu raw token. Session tồn tại không có nghĩa user đã được xác thực.

### Bài 6. Vì sao CSRF protection vẫn cần dù bật HTTPS?

**Đáp án:** HTTPS bảo vệ nội dung truyền, nhưng trình duyệt vẫn có thể tự gửi cookie với request do website khác kích hoạt theo policy; CSRF token giải quyết threat model này.

### Bài 7. Vì sao XOR không phải encryption?

**Đáp án:** Masking tạo nhiều biểu diễn ngẫu nhiên để giảm side channel nén; bản masked token có thể được handler giải về raw mà không dựa trên một bí mật mã hóa độc lập. Nó không làm token an toàn để phát cho attacker.

### Bài 8. GET /csrf public có thể đưa vào CDN cache không?

**Đáp án:** Không nên. Token phụ thuộc session/context; shared cache có thể phân phối token sai phiên và rò dữ liệu. Dùng no-store, kiểm soát proxy, CORS và logs.

### Bài 9. Điều gì phải được test khi có SPA cookie token?

**Đáp án:** Token raw đọc từ cookie, tên header, handler resolve tương thích, masked form vẫn hoạt động, cookie refresh sau login/logout, khác session 403, missing token 403 và Origin/CORS policy không cho attacker đọc token.

### Bài 10. Tại sao không tắt BREACH mitigation để sửa 403?

**Đáp án:** Vì thay plain handler có thể phản chiếu raw secret ổn định trong response nén. Cần sửa cách frontend gửi token hoặc thiết kế custom resolver có kiểm soát, không bỏ mitigation một cách vô thức.

### Bài 11. Lỗi 403 có nhất thiết là CSRF?

**Đáp án:** Không. Có thể là authorization thiếu role. Debug cả CSRF filter, authentication manager và authorization rules; test với CSRF token hợp lệ để cô lập permission errors.

### Bài 12. Có thể tự subscribe Mono<CsrfToken> ở handler không?

**Đáp án:** Không nên. Tạo subscription riêng có thể tách khỏi response lifecycle/error/cancellation và gây vấn đề session cookie. Compose publisher vào WebFlux handler response.

## 14. Checklist kỹ thuật trước production

- [ ] Inbound thật là Spring WebFlux; dùng `ServerHttpSecurity` và package `web.server.csrf`.
- [ ] Xác định Spring Security version, biết XOR default từ 6.0.
- [ ] CSRF áp dụng cho unsafe methods và login/logout browser flow theo threat model.
- [ ] Repository lưu/nạp expected raw token an toàn theo session/cookie strategy.
- [ ] View/form lấy masked value từ request handler, không phản chiếu raw trực tiếp.
- [ ] SPA raw cookie header có resolver tương thích hoặc client dùng masked token endpoint.
- [ ] Không tự triển khai XOR, không dùng random generator yếu/fixed seed ở production.
- [ ] Không block/tự subscribe `Mono<CsrfToken>` trong handler.
- [ ] Token endpoint, form HTML không bị shared-cache hoặc logs công khai.
- [ ] HTTPS, Secure/HttpOnly/SameSite và đúng cookie domain/path.
- [ ] CORS hạn chế origin được phép đọc token với credentials.
- [ ] XSS/CSP/HTML escaping được kiểm soát; CSRF không thay XSS defense.
- [ ] Test masked tokens khác nhau trong cùng session, nhưng POST đều hợp lệ.
- [ ] Test missing token, wrong session, expired token, login/logout refresh.
- [ ] Test xác thực/role riêng; token CSRF không tự cấp quyền.
- [ ] Với multipart, đánh giá token trong body, việc parse file sớm và ưu tiên custom header khi phù hợp.
- [ ] Không dùng query string cho CSRF token.
- [ ] Không retry mutation không idempotent một cách mù khi token hết hạn.
- [ ] Review nén response nếu còn phản chiếu các secret khác ngoài CSRF token.

## 15. Tóm tắt nhanh

```text
Repository (WebSessionServerCsrfTokenRepository):
  lưu expected RAW token R

CsrfWebFilter:
  expose Mono<CsrfToken> qua ServerWebExchange attribute

XorServerCsrfTokenRequestAttributeHandler:
  tạo masked representation V1 = mask(R)
  request khác có thể xuất V2 != V1
  default Spring Security 6+

Browser:
  giữ session cookie
  gửi V1 hoặc V2 trong _csrf form field hoặc X-CSRF-TOKEN header

Request handler resolve:
  giải masked V -> raw actual A
  CsrfWebFilter so A với expected R
  đúng -> đi tiếp
  sai -> từ chối, thường 403

ServerCsrfTokenRequestAttributeHandler:
  plain representation, không có XOR BREACH masking

SPA raw XSRF cookie:
  không mặc định tương thích với masked resolver
  cần frontend/handler strategy thống nhất

CSRF != authentication
XOR masking != encryption
BREACH mitigation != toàn bộ response compression safety
```

**Thông điệp cốt lõi:** `ServerCsrfTokenRequestHandler` xác định cách token được **trình bày cho client** và **giải từ request gửi về**. `XorServerCsrfTokenRequestAttributeHandler` dùng randomness để làm các lần phản chiếu token khác nhau, giảm nguy cơ BREACH, trong khi server vẫn xác minh với **raw expected token** do repository quản lý.

## Tài liệu chính thức

- [Spring Security 6.5 — CSRF for WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security 6.5 — XorServerCsrfTokenRequestAttributeHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/XorServerCsrfTokenRequestAttributeHandler.html)
- [Spring Security 6.5 — ServerCsrfTokenRequestHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/ServerCsrfTokenRequestHandler.html)
- [Spring Security — ServerCsrfTokenRequestAttributeHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/ServerCsrfTokenRequestAttributeHandler.html)
- [Spring Security — CsrfWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/CsrfWebFilter.html)
- [Spring Security — WebSessionServerCsrfTokenRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/WebSessionServerCsrfTokenRepository.html)
- [Spring Security — CookieServerCsrfTokenRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/CookieServerCsrfTokenRepository.html)
- [Spring Security — WebFlux testing CSRF](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html)
- [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [BREACH background](https://breachattack.com/)
