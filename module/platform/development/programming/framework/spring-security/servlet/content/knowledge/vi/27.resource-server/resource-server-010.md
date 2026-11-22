# STATELESS, SecurityContextRepository và kiểm soát CSRF theo cách gửi token

> **Phạm vi:** Spring Security **Servlet** (Spring Boot 3, Spring Security 6, Java 17+), tập trung vào OAuth2 Resource Server nhận access token. Điều quan trọng nhất: **không tạo session** và **không cần chống CSRF** là hai nhận định *khác nhau*. Quyết định có cần CSRF hay không phải dựa vào **cách trình duyệt gửi thông tin xác thực** và các cơ chế authentication còn hoạt động, không chỉ dựa vào từ khóa `STATELESS` hoặc việc token có định dạng JWT.

## 1. Ba câu hỏi phải tách biệt

Khi bảo vệ một API, hãy lần lượt trả lời:

1. **Nguồn credential:** Access token được client chủ động gửi qua `Authorization: Bearer ...`, hay được trình duyệt tự đính kèm trong cookie/HTTP Basic/chứng chỉ client? API có chấp nhận nhiều cơ chế authentication cùng lúc không?
2. **Vòng đời SecurityContext:** Sau khi xác thực request hiện tại, `Authentication` được giữ ở đâu để authorization đọc? Có cần lưu lại để request **tiếp theo** kế thừa danh tính không?
3. **Khả năng CSRF:** Trang web ở origin khác có thể khiến trình duyệt của nạn nhân tự gửi **credential đang hợp lệ** đến endpoint gây thay đổi dữ liệu, dù attacker không biết credential không?

Ví dụ hai hệ thống đều có thể nói “dùng JWT”, nhưng khác nhau về CSRF:

| Kiến trúc | Cách credential đi theo request | Session/SecurityContext | Rủi ro CSRF đối với browser |
| --- | --- | --- | --- |
| Mobile hoặc API client gửi bearer | Header `Authorization: Bearer TOKEN` do client gắn riêng | Xác thực từng request, không cần HTTP session | Không dựa vào credential tự động từ browser; thường không cần CSRF token cho chain API thuần này |
| SPA gửi bearer thủ công | JavaScript thêm header `Authorization` từ token có sẵn | Thường stateless phía server | Tương tự trên *nếu* API thật sự chỉ chấp nhận bearer header; vẫn cần phòng XSS, CORS, lộ token |
| Browser giữ JWT trong cookie và backend đọc cookie | `Cookie: access_token=...` được browser tự đính kèm | Có thể stateless dù không có `HttpSession` | **Cần đánh giá và xử lý CSRF**; JWT không tự ngăn CSRF |
| BFF giữ OAuth token ở server, browser có cookie session | Cookie phiên đi tự động; BFF gọi Resource Server bằng Bearer | BFF thường dùng session, Resource Server có thể stateless | BFF cần cơ chế CSRF phù hợp; Resource Server thuần bearer thường không |
| Ứng dụng kết hợp login web và Resource Server | Có thể nhận cả `JSESSIONID` và bearer | Phụ thuộc chain/filters | Không được tắt CSRF toàn cục chỉ vì một phần API dùng bearer |
| Browser tự gửi HTTP Basic đã cache hoặc client certificate | Credential được browser gửi tự động theo ngữ cảnh | Có thể không dùng HttpSession | Có thể tồn tại CSRF dù phía server stateless |

**Kết luận ban đầu:** `SessionCreationPolicy.STATELESS` điều chỉnh **cách Spring Security sử dụng HttpSession** cho SecurityContext; `SecurityContextRepository` điều chỉnh **nơi nạp/lưu context**; `CsrfFilter` điều chỉnh **chống giả mạo request**. Ba công cụ giải quyết ba bài toán riêng.

## 2. Phân biệt JWT, session và SecurityContext

### 2.1. JWT hoặc opaque token không đồng nghĩa với SecurityContext

Trong OAuth2 Resource Server, một request hợp lệ thường có header:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOi...
```

`BearerTokenAuthenticationFilter` trích token, sau đó xác thực qua JWT decoder hoặc opaque token introspector. Nếu hợp lệ, Spring Security tạo `Authentication` tương ứng và đưa vào `SecurityContext` để các bước phân quyền của **request hiện tại** sử dụng.

- JWT có thể tự chứa claims và được xác thực bằng chữ ký, issuer, expiry, audience; JWT **không phải** Servlet `HttpSession`.
- Opaque token được kiểm tra qua introspection (hoặc cơ chế được cấu hình), cũng không cần dùng `HttpSession` để ghi nhớ đăng nhập.
- `Authentication` trong `SecurityContextHolder` là dữ liệu cho security filters và controller truy cập quyền của **request hiện tại**; nó không tự biến thành session bền vững.

Một request sau phải gửi token hợp lệ của riêng request đó nếu API được xây dựng stateless. Không có nghĩa access token không có “state” ở phía nhà phát hành: token có hạn dùng, có thể được thu hồi, có khóa ký và có quan hệ với quyền/người dùng.

### 2.2. SecurityContextHolder khác SecurityContextRepository

- **`SecurityContextHolder`:** API truy cập `SecurityContext` hiện hành trong quá trình xử lý; chiến lược mặc định ở ứng dụng Servlet thường liên kết với luồng xử lý. Spring Security quản lý việc đặt và dọn context trong filter lifecycle.
- **`SecurityContextRepository`:** nơi **load** và/hoặc **save** `SecurityContext` giữa các giai đoạn xử lý. Tùy implementation, repository có thể lưu ở request attributes, `HttpSession` hoặc không lưu.
- **`SessionCreationPolicy`:** chính sách của Spring Security về việc tạo/sử dụng `HttpSession`, không phải định nghĩa tổng quát rằng mọi thành phần trong ứng dụng cấm gọi `request.getSession()`.

Đừng nhầm “context có mặt khi xử lý request” với “context đã được ghi vào `HttpSession`”. Resource Server cần `Authentication` cho controller, authorization và audit của **lượt gọi đang diễn ra**; không nhất thiết lưu nó cho request tiếp theo.

## 3. SessionCreationPolicy.STATELESS thật sự làm gì?

Cấu hình quen thuộc:

```java
http.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
);
```

Các giá trị `SessionCreationPolicy` có ý nghĩa khác nhau:

| Chính sách | Ý nghĩa chính trong Spring Security |
| --- | --- |
| `ALWAYS` | Spring Security chủ động tạo `HttpSession` |
| `IF_REQUIRED` | Chỉ tạo `HttpSession` khi một cơ chế bảo mật cần |
| `NEVER` | Không chủ động tạo `HttpSession`, nhưng có thể dùng session **đã tồn tại** |
| **`STATELESS`** | Spring Security không tạo `HttpSession` và không sử dụng session để lấy `SecurityContext` |

**`NEVER` không phải `STATELESS`.** Ví dụ servlet code khác tạo session trước, chính sách `NEVER` có thể cho phép Spring Security sử dụng lại session đó; `STATELESS` hướng đến xác thực request mà không phụ thuộc session đã có.

### 3.1. STATELESS không bảo đảm “không có cookie”

Một hệ thống đánh dấu `STATELESS` nhưng browser vẫn thấy `JSESSIONID` chưa đủ để kết luận Spring Security bỏ qua policy. Session có thể do MVC, JSP, servlet khác, thư viện, custom filter, cơ chế CSRF dựa trên session hoặc application code tạo. Hãy điều tra **thành phần nào gọi session**, thay vì quy kết mọi cookie là do Resource Server.

Đồng thời, **không nên dựa vào một dòng `STATELESS` để khẳng định session authentication đã bị loại khỏi mọi filter**. Khi ứng dụng bật thêm authentication kiểu web, custom filters hoặc có nhiều filter chains, phải kiểm tra đầy đủ các cơ chế đang hoạt động.

### 3.2. STATELESS không tự tắt CSRF

Một request có thể hoàn toàn không dùng `HttpSession` nhưng browser tự đính kèm **cookie chứa JWT**, khiến attacker lợi dụng cross-site requests. Vì thế:

```text
JWT + no HttpSession + credential trong cookie
                      !=
                 miễn nhiễm CSRF
```

Ngược lại, một Resource Server yêu cầu bearer header do client gửi chủ động có thể không cần CSRF token, **dù vẫn cần** xác thực JWT, kiểm tra scope/quyền, CORS đúng, HTTPS và chống lộ token.

### 3.3. STATELESS không tự làm logout thu hồi token

Với xác thực từng request bằng bearer:
- Xóa cookie phiên hoặc hủy một `HttpSession` **không** tự thu hồi JWT đã cấp.
- Client có thể xóa access token local khi logout, nhưng token bị đánh cắp vẫn còn dùng được cho tới khi hết hạn, bị thu hồi hoặc bị chặn bởi cơ chế quản lý trạng thái token.
- Chọn TTL ngắn, refresh-token rotation, revoke/introspection, quản lý khóa, audience và scopes tùy threat model.

## 4. SecurityContextRepository: tải/lưu context ở đâu?

Một số triển khai quan trọng của Spring Security Servlet:

| Triển khai | Nơi lưu/tra cứu | Khi nào phù hợp | Giới hạn |
| --- | --- | --- | --- |
| `HttpSessionSecurityContextRepository` | `HttpSession` | Đăng nhập web cần giữ Authentication qua nhiều request | Không phù hợp làm nơi ghi nhớ token cho API bearer stateless |
| `RequestAttributeSecurityContextRepository` | Thuộc tính của **một HTTP request** | Duy trì context qua một số giai đoạn dispatch của cùng request (ví dụ error dispatch) | Không lưu danh tính cho request HTTP tiếp theo |
| `NullSecurityContextRepository` | Không lưu/trả lại context bền vững | Khi không muốn nạp/lưu Authentication từ repository | Không hỗ trợ persist context giữa các request/dispatch |
| `DelegatingSecurityContextRepository` | Kết hợp nhiều repositories | Môi trường Servlet dùng cả request attributes và session theo cấu hình | Cần hiểu repository con nào thực sự được sử dụng |

Trong những cấu hình web thông thường của Spring Security 6, repository có thể là `DelegatingSecurityContextRepository` kết hợp request attribute và session; cơ chế riêng của Resource Server có thể lưu context cho **request hiện tại**. **Đừng giả định một default repository duy nhất cho mọi filter và mọi version/config.** Xác minh thực tế trên chain đang chạy.

### 4.1. Vòng đời SecurityContext trong Resource Server stateless

```text
Request #1
Authorization: Bearer TOKEN
    |
    v
BearerTokenAuthenticationFilter
  -> resolver đọc token
  -> AuthenticationManager / JWT decoder xác thực
  -> SecurityContextHolder chứa Authentication
  -> authorization -> controller
  -> security filter cleanup
    |
    v
Response #1

Request #2
(không gửi Authorization)
    |
    v
Không kế thừa bearer Authentication của Request #1
    |
    v
Route cần authenticated -> thông thường HTTP 401
```

Việc authentication hoạt động trong Request #1 không đòi hỏi tạo `HttpSession`. Đối với Resource Server, mỗi request cần được kiểm tra dựa trên token đang được gửi.

### 4.2. SecurityContextHolderFilter và explicit save

Spring Security 6 ưu tiên cơ chế `SecurityContextHolderFilter`, đọc context từ `SecurityContextRepository`. Trong mô hình explicit-save, filter này **không tự động lưu** `SecurityContext` khi request kết thúc; nếu bạn tự viết luồng đăng nhập stateful, custom authentication code phải gọi `saveContext(...)` của repository khi muốn context tồn tại cho request kế tiếp.

Mã **minh họa API cho custom login stateful** (không phải cấu hình cần dùng cho API Bearer thuần):

```java
SecurityContext context =
    SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(context, request, response);
```

Ở đây `authenticated` phải là đối tượng `Authentication` đã được xác thực thật sự, và `securityContextRepository` phải là repository đã cấu hình cho filter chain. Đoạn trên là snippet đặt **bên trong authentication handler có request/response**; nó không thể chạy độc lập vì các biến phải được cung cấp. Không tự lưu context của bearer token vào session chỉ để xử lý request sau “nhanh hơn” — làm vậy thay đổi kiến trúc thành stateful và có thể tạo credential tự động từ cookie.

### 4.3. Có cần ép NullSecurityContextRepository?

Chỉ khi có yêu cầu rõ ràng và đã kiểm chứng vòng đời filter. Ví dụ biểu thức cấu hình:

```java
http.securityContext(context -> context
    .securityContextRepository(new NullSecurityContextRepository())
);
```

Đây là **snippet minh họa**, với class `org.springframework.security.web.context.NullSecurityContextRepository`. Không phải mọi ứng dụng cần khai báo nó: `STATELESS` đã diễn đạt ý định không phụ thuộc `HttpSession` cho context, và cơ chế request-attribute có thể có ích cho dispatch nội bộ mà không làm API stateful. Ép repository null có thể ảnh hưởng error dispatch hoặc custom filters. **Ưu tiên cấu hình tối thiểu có kiểm thử**, thay vì thay tất cả security context components chỉ vì muốn “stateless hơn”.

## 5. CSRF liên quan tới cách gửi token, không phải loại token

### 5.1. CSRF hoạt động như thế nào?

Nạn nhân đăng nhập ứng dụng `bank.example.test`. Một trang attacker điều khiển có thể dụ trình duyệt tạo request sang `bank.example.test`. Nếu **trình duyệt tự mang credential** (ví dụ session cookie) và endpoint chấp nhận thao tác đổi trạng thái mà không kiểm tra CSRF thích hợp, yêu cầu có thể chạy dưới danh tính nạn nhân. Attacker không nhất thiết đọc được response; chỉ cần tác động có hiệu lực.

```text
Người dùng đã login tại ứng dụng
  -> browser có cookie/chứng thực tự gửi
  -> user mở trang attacker
  -> attacker tạo cross-site POST đến ứng dụng
  -> browser có thể tự gửi credential (tùy cookie policy/SameSite)
  -> server xác thực thành nạn nhân
  -> nếu thiếu kiểm soát CSRF, thao tác có thể bị thực hiện
```

Điểm mấu chốt là **ambient authority**: credential tự đi cùng request. Quy tắc `SameSite`, `Origin`/`Referer`, CORS, CSRF token và cấu trúc endpoint cùng góp phần kiểm soát; không một yếu tố đơn lẻ thay thế đầy đủ cho các yêu cầu bảo mật khác.

### 5.2. Bearer header được client gắn chủ động

Trường hợp API chỉ xác thực access token từ:

```http
Authorization: Bearer ACCESS_TOKEN
```

Một trang attacker ở origin khác không tự biết access token để điền vào header; browser không tự lấy token JavaScript của ứng dụng nạn nhân để gắn vào request tùy ý. Vì vậy **CSRF kiểu cookie thường không áp dụng theo cùng cách** cho chain chỉ nhận bearer header.

Tuy nhiên cần đủ các điều kiện:
- Server **không** chấp nhận session cookie hoặc cookie JWT để xác thực **cùng endpoint**.
- Không có cơ chế khác mà browser tự gửi và server chấp nhận, chẳng hạn HTTP Basic được browser lưu hoặc client certificate.
- CORS không bị coi là hệ thống phân quyền; API vẫn phải validate bearer token, scopes, issuer/audience.
- Token trên client được bảo vệ khỏi XSS/extension rủi ro; nếu attacker lấy được token, đó là **token theft**, không cần CSRF.
- Không đưa token vào URL/query/form fallback vô tình biến credential thành thông tin dễ lộ.

**CSRF vẫn có thể được vô hiệu hóa riêng cho bearer-only API** sau khi xác minh các điều kiện, thay vì vô hiệu hóa toàn ứng dụng.

### 5.3. JWT trong cookie: vẫn có thể có CSRF

Một API có thể giải mã JWT từ `Cookie: access_token=...` và không tạo bất kỳ `HttpSession` nào. Nhưng cookie được browser gửi tự động khi điều kiện cookie phù hợp. Vì vậy attacker có thể lợi dụng browser gửi request đã mang credential. `HttpOnly` chặn JavaScript đọc cookie qua `document.cookie`, **không** chặn browser đính kèm cookie vào request. `Secure` yêu cầu HTTPS, **không** tự ngăn CSRF. `SameSite` hạn chế một số request cross-site, nhưng phụ thuộc ngữ cảnh trình duyệt và mô hình origin/site, không thay thế việc đánh giá endpoint thay đổi dữ liệu.

Nếu chọn cookie cho credential:
- Thiết kế cơ chế chống CSRF thích hợp (synchronizer token, double-submit được triển khai đúng, origin validation theo kiến trúc).
- Cấu hình `Secure`, `HttpOnly`, `SameSite` và domain/path cẩn thận.
- Không cho thao tác gây side effect qua `GET`.
- Kiểm soát XSS vì XSS có thể tạo request hợp lệ ngay trong origin dù không đọc được cookie.

### 5.4. BFF và session cookie

Với **Backend-for-Frontend**, browser gửi cookie session đến BFF; BFF giữ access token phía server và gọi downstream Resource Server bằng bearer header. Hai lớp có chính sách khác nhau:

```text
Browser --(cookie session; CSRF protection)--> BFF
BFF     --(Authorization: Bearer; token validation)--> Resource Server
```

- **BFF:** có credential tự gửi từ browser, thường giữ CSRF protection cho hành động thay đổi dữ liệu và xử lý session cookie.
- **Resource Server:** nếu chỉ xác thực bearer header từ BFF và không hỗ trợ cookie authentication, có thể dùng STATELESS và tắt CSRF **cho chain thuần bearer**.
- Điều này **không** đồng nghĩa BFF hoặc mọi API phía ngoài đều được tắt CSRF.

### 5.5. Môi trường hybrid: nhiều cơ chế trong cùng ứng dụng

Ứng dụng có login web tại `/account/**` và bearer API tại `/api/**`. Nếu có một cấu hình duy nhất `csrf(csrf -> csrf.disable())` bao trùm tất cả, form cập nhật profile dùng cookie session mất bảo vệ CSRF. Thay vào đó, tách **SecurityFilterChain theo matcher** hoặc bảo vệ CSRF có điều kiện dựa trên **chính xác endpoint và cách authentication hoạt động**.

**Nguyên tắc:** xác định mọi cơ chế authentication được chain chấp nhận; đừng dùng “endpoint là REST/JSON” hay “token là JWT” làm tiêu chí duy nhất để tắt CSRF.

## 6. Cấu hình Spring Security 6 Servlet: tách bearer API và web session

Ví dụ dùng Spring Boot 3, Java 17+, dependency `spring-boot-starter-web`, `spring-boot-starter-security` và `spring-boot-starter-oauth2-resource-server`. Các class dưới đây phải nằm trong package được ứng dụng `@SpringBootApplication` scan. Chúng **không phải** mã một file có thể biên dịch bằng `javac` thuần; Spring Boot và dependencies cung cấp container/filter chain.

**Giả định bảo mật quan trọng:** toàn bộ đường dẫn `/api/**` **chỉ nhận bearer token từ `Authorization`**, không dùng cookie/session/HTTP Basic/client certificate cho việc xác thực. Nếu thực tế API hỗ trợ credential tự gửi, **không áp dụng nguyên xi đoạn `csrf.disable()`**.

### 6.1. SecurityConfig.java

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache()))
            .csrf(csrf -> csrf.disable())
            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/css/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        // KHÔNG disable CSRF ở webChain.
        // Spring Security giữ cơ chế CSRF mặc định cho web.
        return http.build();
    }
}
```

Ý nghĩa từng quyết định:

1. `@Order(1)` + `securityMatcher("/api/**")` khiến API chain có phạm vi rõ ràng, chạy trước fallback web chain. `@Order(2)` áp dụng các request còn lại. Không bỏ sót route nhạy cảm ngoài cả hai chain.
2. `STATELESS` không dùng `HttpSession` để lấy `SecurityContext` cho API. Mỗi request API cần bearer hợp lệ hoặc thuộc route `permitAll`.
3. `NullRequestCache` không lưu “request trước đăng nhập” cho luồng API bằng cơ chế request cache thường dành cho web session; giảm khả năng tạo session ngoài ý muốn.
4. `csrf(csrf -> csrf.disable())` **chỉ xuất hiện trong API chain** với giả định bearer header duy nhất. Nó không tự suy ra từ `STATELESS`.
5. `formLogin(...disable())` và `httpBasic(...disable())` loại hai cơ chế authentication thông dụng vốn không nằm trong hợp đồng bearer-only của API. Nếu ứng dụng có custom filter, cần tiếp tục audit.
6. `oauth2ResourceServer(...jwt(...))` bật bearer token filter và JWT validation. JWT hợp lệ chưa chắc đủ quyền; các matcher dùng `SCOPE_orders.read`/`SCOPE_orders.write`.
7. `webChain` vẫn có form login và CSRF mặc định; các request POST web phải gửi CSRF token hợp lệ.
8. Quy tắc scope trong ví dụ chỉ minh họa. Spring Security Resource Server mặc định thường chuyển các giá trị `scope`/`scp` của JWT thành authority có tiền tố `SCOPE_`; nếu Authorization Server dùng mô hình claims khác, cần cấu hình converter và test.

**Không có phép màu từ stateless:** cookie được browser gửi đến `/api/**` có thể vẫn xuất hiện trong request, nhưng nếu chain API chỉ chấp nhận bearer header như giả định, cookie đó **không được dùng để xác thực**. Hãy kiểm tra điều này bằng integration test trong ứng dụng thật.

### 6.2. Cấu hình issuer và JWK của JWT

File `application.yml` (giá trị minh họa; phải thay bằng issuer/JWK thật):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
          jwk-set-uri: https://idp.example.test/realms/demo/protocol/openid-connect/certs
```

Khai báo trực tiếp `jwk-set-uri` có thể giúp Resource Server không cần truy vấn metadata issuer khi khởi động; vẫn cần xác minh token và issuer theo cấu hình. Trong sản phẩm thực phải dùng URL tin cậy, kiểm tra signature, thời gian, issuer, audience và scopes phù hợp. **Audience validation** cho API không tự phát sinh đầy đủ từ việc biết `issuer-uri`; triển khai validator riêng khi yêu cầu.

Cấu hình này không quyết định CSRF. Quyết định CSRF đã được xét từ **cơ chế credential mà mỗi chain chấp nhận**.

### 6.3. Controller minh họa để kiểm thử

File `DemoController.java`:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/orders")
    public String orders() {
        return "orders";
    }

    @PostMapping("/api/orders")
    public String createOrder() {
        return "created";
    }

    @PostMapping("/account/update")
    public String updateAccount() {
        return "updated";
    }
}
```

Các endpoint này chỉ trả text cố định để thể hiện điểm khác nhau của **chính sách bảo mật**; chúng không thay đổi dữ liệu thật. Vì `/account/update` thuộc `webChain`, POST phải được xác thực **và** có CSRF token. Vì `/api/orders` thuộc `apiChain`, POST cần bearer hợp lệ và authority `SCOPE_orders.write`, nhưng không yêu cầu CSRF token theo giả định bearer-only.

### 6.4. Nếu ứng dụng thực sự chỉ có một API bearer

Có thể dùng một `SecurityFilterChain` thay vì hai: chỉ bật `STATELESS`, bearer Resource Server, request cache phù hợp và tắt CSRF khi toàn bộ ứng dụng đúng là **bearer-header-only**. Ngược lại, nếu có HTML login hoặc session cookie, hãy giữ chain web riêng hoặc xây rule phù hợp. Không áp một cấu hình mẫu duy nhất cho mọi hệ thống.

## 7. CSRF protection trong web session chain

Trong ứng dụng dùng session cookie, Spring Security Servlet dùng `CsrfFilter` để kiểm tra token cho các HTTP methods không an toàn (thông thường POST/PUT/PATCH/DELETE). Theo mặc định, các method an toàn như GET, HEAD, TRACE, OPTIONS không bị CSRF filter chặn; **điều đó không cho phép GET tạo side effect** và không thay thế các biện pháp kiểm soát method khác.

Ví dụ form Thymeleaf dùng Spring Security CSRF support:

```html
<form action="/account/update" method="post">
  <input type="hidden"
         th:name="\${_csrf.parameterName}"
         th:value="\${_csrf.token}" />
  <button type="submit">Update</button>
</form>
```

Đây là **template Thymeleaf**, không phải HTML tĩnh đã render. Spring Security phải cung cấp CSRF token cho request và ứng dụng phải cấu hình MVC/Thymeleaf tương ứng. Template engine thay các biểu thức bằng tên/value của token; browser nộp lại qua form body. Nếu không dùng Thymeleaf, ứng dụng phải chủ động truyền token phù hợp trong hidden field hoặc header.

Spring Security 6 có cơ chế lazy CSRF token và xử lý request handler để tránh BREACH trong một số trường hợp; không giả định đơn giản rằng “đã mở trang GET thì luôn có session và token hiển thị đúng ở cookie”. Với SPA dùng cookie và gọi AJAX, xem xét `CookieCsrfTokenRepository` cùng request handler/cách cung cấp token phù hợp, đặc biệt khi dùng `X-XSRF-TOKEN`. Không tùy tiện tắt token masking/XOR hoặc `HttpOnly` để “sửa” lỗi AJAX mà không hiểu rủi ro.

### 7.1. CSRF token không phải access token

- Access token xác thực API caller và scope được cấp.
- CSRF token chứng minh request thay đổi trạng thái đến từ ngữ cảnh được chấp thuận theo cơ chế chống CSRF của ứng dụng.
- Không đưa access token vào hidden `_csrf` field hoặc URL.
- Không coi “JWT có chữ ký” là CSRF token; đây là hai nhiệm vụ bảo mật khác nhau.

Nếu browser dùng session/BFF, chống CSRF vẫn có ý nghĩa ngay cả khi BFF sử dụng OAuth access token ở phía server.

## 8. Kiểm thử bằng MockMvc và Spring Security Test

Thêm các dependency test thích hợp, ví dụ `spring-boot-starter-test` và `spring-security-test`. File `SecurityPolicyTests.java` (cùng package với Spring Boot application hoặc trong package được scan cho tests):

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityPolicyTests {
    @Autowired
    MockMvc mvc;

    @Test
    void noBearerOnProtectedApiReturns401() throws Exception {
        mvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authorizedApiPostDoesNotNeedCsrfToken() throws Exception {
        mvc.perform(post("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isOk())
            .andExpect(content().string("created"));
    }

    @Test
    void authenticatedButInsufficientScopeReturns403() throws Exception {
        mvc.perform(post("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void webSessionPostWithoutCsrfReturns403() throws Exception {
        mvc.perform(post("/account/update").with(user("alice")))
            .andExpect(status().isForbidden());
    }

    @Test
    void webSessionPostWithCsrfSucceeds() throws Exception {
        mvc.perform(post("/account/update")
                .with(user("alice"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("updated"));
    }
}
```

Ý nghĩa:
- Test 1 kiểm tra API bảo vệ không nhận request ẩn danh.
- Test 2 chứng minh **API chain** không đòi CSRF khi đã có authentication JWT giả lập với authority cần thiết.
- Test 3 chứng minh stateless không có nghĩa mọi JWT hợp lệ đều được thao tác; authorization có thể trả 403.
- Test 4–5 xác minh **web chain** không bị ảnh hưởng bởi quyết định tắt CSRF ở API: POST session cần token CSRF.

**Giới hạn quan trọng:** `jwt()` trong Spring Security Test là request post-processor giả lập JWT authentication; nó kiểm tra phân quyền và tương tác với filter chain, **không chứng minh JWT decoder đã kiểm tra chữ ký thực tế, token trong `Authorization` đã được BearerTokenResolver trích đúng, hay issuer có thể truy cập được**. Để test token thật, cần integration test với decoder/test key hoặc Authorization Server test, và kiểm tra kết quả thông qua HTTP Bearer header.

Nếu test class và config đặt trong package đúng, các endpoint của `DemoController` đều tồn tại, auth chain match đúng; năm test trên có kết quả mong đợi. Không có stdout nghiệp vụ riêng. Chạy trong project Maven/Gradle có dependencies tương ứng, ví dụ:

```bash
mvn -Dtest=SecurityPolicyTests test
# Hoặc:
./gradlew test --tests SecurityPolicyTests
```

### 8.1. Test cookie/session không được xác thực nhầm trên API

Để khẳng định `csrf.disable()` thật sự an toàn, hãy bổ sung kiểm thử end-to-end trên hệ thống thực:
1. Đăng nhập qua web chain và giữ session cookie hợp lệ.
2. Gọi `POST /api/orders` **chỉ với session cookie**, không gửi bearer token.
3. Kỳ vọng API chain **không sử dụng session cookie đó để xác thực**; request sẽ bị từ chối (trong ví dụ thường là 401).
4. Gọi tương tự với bearer token hợp lệ có scope `orders.write`, xác nhận yêu cầu được cho qua.
5. Nếu request chỉ có cookie lại thành công, giả định bearer-only đã sai: **không được tắt CSRF** cho endpoint đó khi chưa khắc phục nguồn authentication.

Tương tự, thử credential tự gửi khác như HTTP Basic được browser cache, chứng chỉ client hoặc filter authentication riêng, nếu hệ thống có hỗ trợ.

### 8.2. Test SecurityContextRepository và session thực tế

Với API stateless, hãy quan sát:
- Request A gửi token hợp lệ → authentication được thiết lập trong request A.
- Request B không gửi token → **không kế thừa** authentication từ A, kể cả browser lưu cookie do thành phần khác tạo.
- Không có session được tạo **bởi cơ chế bảo mật API** để ghi nhớ auth; dùng logging/instrumentation thích hợp ở dev để tìm thành phần tạo `HttpSession` khi bất ngờ thấy cookie `JSESSIONID`.
- Request qua error dispatch/forward được kiểm thử với repository tùy chỉnh nếu ứng dụng cần đảm bảo principal trong luồng lỗi.

Lưu ý: test có thể tạo session riêng do test post-processor hoặc cơ chế web chain, nên đừng kết luận “API stateless FAIL” chỉ từ mọi đối tượng `HttpSession` xuất hiện trong test harness. Cần xác minh đường đi và nguồn tạo session.

## 9. HTTP thủ công: phân biệt 401, 403 và lỗi CSRF

Giả sử app chạy tại `http://localhost:8080` với các mapping ở trên:

```bash
# API được bảo vệ, không có Authorization => thường 401.
curl -i http://localhost:8080/api/orders

# Token thử không hợp lệ: resolver có thể nhận chuỗi,
# nhưng JWT validator thường từ chối => 401.
curl -i http://localhost:8080/api/orders \
  -H 'Authorization: Bearer invalid-token'

# Không có credential hợp lệ: POST không thể thành công;
# API chain không yêu cầu CSRF nhưng vẫn yêu cầu authentication.
curl -i -X POST http://localhost:8080/api/orders

# Web endpoint cần session login và CSRF token.
# Chỉ gửi POST ẩn danh thường bị chặn, không chứng minh
# chính xác đó là lỗi CSRF hay authentication.
curl -i -X POST http://localhost:8080/account/update
```

Khi chạy qua test với `jwt()` hoặc token thật, có thể phân biệt rành mạch: **không token → 401**, **token hợp lệ nhưng thiếu scope → 403**, **web session POST thiếu CSRF token → 403**. Hai tình huống cuối cùng có thể đều là 403 nhưng phát sinh ở **hai cơ chế khác nhau**.

**Đừng dùng token thật trong URL hoặc shell history.** Khi test bearer token, ưu tiên secret handling của môi trường CI/test, không đưa vào log được chia sẻ và kiểm soát truy cập tới log request header.

## 10. Bảng quyết định khi thiết kế API

| Điều kiện | Session policy gợi ý | SecurityContextRepository / persistence | CSRF |
| --- | --- | --- | --- |
| Resource Server chỉ nhận bearer header, không auto-auth | `STATELESS` | Không persist context qua `HttpSession`; auth mỗi request | Có thể tắt trên **chain bearer-only** |
| Browser session form login | `IF_REQUIRED` hoặc chính sách web phù hợp | `HttpSessionSecurityContextRepository`/delegate phù hợp | **Giữ** bảo vệ CSRF cho unsafe methods |
| BFF nhận cookie phiên, downstream bearer | BFF stateful theo thiết kế, downstream thường `STATELESS` | BFF lưu auth/server-side token an toàn; downstream auth mỗi call | **BFF cần CSRF**; downstream bearer-only đánh giá riêng |
| JWT được đọc từ cookie trong API không session | Có thể `STATELESS` | Không nhất thiết dùng `HttpSession` | **Vẫn cần** giải pháp chống CSRF theo mô hình cookie |
| API chấp nhận cả cookie login và bearer | Phụ thuộc chain cụ thể | Phải kiểm tra nơi nạp/persist cả hai nguồn | Không vô hiệu hóa chung; chia chain hoặc rule CSRF chính xác |
| Service-to-service qua bearer header | Thường `STATELESS` | Không persist context giữa request | CSRF browser thường không áp dụng, nhưng cần TLS, token validation, authorization |
| Ứng dụng dùng HTTP Basic trong browser | Có thể không dùng session | Context thường không cần persist session | Vẫn phải đánh giá CSRF do browser có thể tự gửi Basic credential |

**Cách chọn:** hỏi “credential nào được server chấp nhận trên endpoint này và browser có tự đính kèm nó không?” trước khi chọn `csrf.disable()`. Sau đó hỏi “có cần lưu authentication cho request kế tiếp không?” để chọn session policy và repository.

## 11. Những lỗi phổ biến và cách sửa

1. **“Dùng JWT nên chắc chắn không có CSRF.”** Sai nếu JWT nằm trong cookie tự gửi. Đánh giá nguồn token và auto-auth của browser.
2. **“Đặt STATELESS là Spring Security tự tắt CSRF.”** Sai: session policy và CSRF filter là hai cấu hình khác nhau.
3. **“Tắt CSRF ở toàn bộ ứng dụng vì /api dùng Bearer.”** Sai khi các trang form/session vẫn tồn tại. Tách matcher/chain và giữ CSRF cho web.
4. **“NullSecurityContextRepository nghĩa là controller không thấy Authentication.”** Sai: authentication của request hiện tại vẫn có thể nằm trong `SecurityContextHolder`; repository quyết định load/save giữa các giai đoạn/request.
5. **“RequestAttributeSecurityContextRepository là session.”** Sai: request attribute thuộc phạm vi request/dispatch, không tồn tại như đăng nhập qua nhiều request độc lập.
6. **“STATELESS bảo đảm server không bao giờ gửi JSESSIONID.”** Sai nếu thư viện/app/filter khác tạo session; truy tìm nguồn thay vì đổ lỗi cho một dòng config.
7. **“Cookie HttpOnly chống CSRF.”** Sai: `HttpOnly` bảo vệ khỏi việc script đọc cookie, không ngăn browser tự gửi cookie khi điều kiện cho phép.
8. **“SameSite bảo đảm hết rủi ro.”** Sai: cần kiểm tra site boundary, browser behavior, endpoint đổi trạng thái và CSRF policy thực sự.
9. **“CORS thay được CSRF token.”** Sai: CORS quản lý khả năng đọc/truy cập response và một số cross-origin requests của browser, không phải hệ thống authorization hoặc CSRF thay thế tổng quát.
10. **“Bearer token hợp lệ thì được mọi API.”** Sai: cần scopes/authorities, audience, ownership check và business authorization.
11. **“Logout session sẽ thu hồi JWT.”** Sai: stateless bearer cần TTL, revocation/introspection và chiến lược token riêng.
12. **“MockMvc .with(jwt()) đã test verify chữ ký JWT.”** Sai: đó là test giả lập authentication; cần test JWT decoder/real token độc lập.

## 12. Checklist triển khai và đánh giá

- [ ] Ghi rõ authentication sources được mỗi `SecurityFilterChain` chấp nhận: Authorization Bearer, session cookie, cookie JWT, Basic, client certificate, custom filter.
- [ ] Chỉ dùng `STATELESS` ở nơi không cần lưu danh tính qua `HttpSession`; xác nhận request tiếp theo không kế thừa Authentication của request trước.
- [ ] Hiểu nơi nạp/lưu `SecurityContext`, không lẫn `SecurityContextHolder` với `SecurityContextRepository`.
- [ ] Nếu muốn API bearer-only, không bật vô tình form login/HTTP Basic/session authentication trong cùng chain.
- [ ] Chỉ tắt CSRF cho endpoint mà credential **không tự động được browser gửi** và các cơ chế auth khác đã được audit.
- [ ] Với web/BFF/cookie-based authentication, giữ CSRF phù hợp, cookie `Secure`/`HttpOnly`/`SameSite` và không có unsafe GET.
- [ ] Không dựa chỉ vào CORS hoặc JWT signing để giải quyết CSRF.
- [ ] Đảm bảo issuer, signature, expiry, audience và scopes/ownership được xác thực đúng.
- [ ] Dùng request cache phù hợp cho API; không dùng session để giữ saved request/login state vô tình.
- [ ] Có unit/integration tests tách bạch 401 không token, 403 thiếu quyền, 403 CSRF, CORS preflight và cookie-only request.
- [ ] Xác minh session creation, error dispatch và context persistence với các filter tùy chỉnh.
- [ ] Có chiến lược logout/revoke/rotate token; không coi stateless là tự động thu hồi credential.

**Ghi nhớ cuối cùng:** `STATELESS` là một quyết định về **sử dụng HttpSession**, `SecurityContextRepository` là quyết định về **lưu/nạp SecurityContext**, còn CSRF phụ thuộc **credential có được browser tự đính kèm vào request hay không**. Một Resource Server thuần `Authorization: Bearer` thường dùng API stateless và có thể không cần CSRF token; nhưng JWT trong cookie hoặc BFF/session cookie **vẫn phải** được bảo vệ chống CSRF phù hợp.
