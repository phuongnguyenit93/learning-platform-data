# Khả năng dùng firewall Reactive từ các phiên bản hỗ trợ

> **Chương:** Cấu hình và phiên bản  
> **Module:** `SPRING_SECURITY_HTTP_PROTECTION`  
> **Trọng tâm:** Xác định **từ phiên bản Spring Security nào** có thể dùng HTTP firewall cho Spring WebFlux, cấu hình đúng `ServerWebExchangeFirewall`/`StrictServerWebExchangeFirewall`, kiểm thử request nguy hiểm và bảo đảm các lớp CSRF, CORS, security headers/CSP/HSTS, authorization và session không bị hiểu lẫn với firewall.  
> **Mốc đối chiếu:** 26/11/2026. Javadoc của Spring Security ghi `Since: 6.4` đối với `ServerWebExchangeFirewall`, `StrictServerWebExchangeFirewall` và `WebFilterChainProxy.setFirewall(...)`. Những khác biệt phát sinh ở dòng 7.x cần được kiểm tra với **đúng phiên bản runtime**.

## 1. Vấn đề mà HTTP firewall Reactive giải quyết

Giả sử một ứng dụng WebFlux phục vụ endpoint `GET /admin/reports` và yêu cầu quyền `ADMIN`. Người dùng thường không được truy cập đường dẫn này. Tuy nhiên, một client có thể thử các biến thể URL:

```text
/admin/reports
/admin//reports
/admin/../public
/admin%2Freports
/admin;mode=x/reports
/admin%5Creports
```

Nếu reverse proxy, HTTP server, Spring Security matcher và WebFlux router **không hiểu đường dẫn giống nhau**, một request có thể được bảo vệ theo URL này nhưng lại được route tới handler khác. HTTP firewall giúp giảm kiểu bất đồng đó: **từ chối request có cấu trúc nguy hiểm hoặc không được phép trước khi chúng đi qua các security filters và URL authorization rules**.

Vấn đề tương tự còn xuất hiện với HTTP method (`TRACE`, method lạ), header name/value và query-parameter name/value có ký tự bất thường. Firewall **không xác thực người dùng** và **không ra quyết định ADMIN/USER**. Nó bảo vệ *ranh giới diễn giải HTTP request*, làm nền cho các lớp phòng vệ tiếp theo.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Chỉ đúng mốc **Spring Security 6.4** và phân biệt WebFlux đời trước với đời có firewall API chính thức.
2. Giải thích mối quan hệ giữa `ServerWebExchangeFirewall`, `WebFilterChainProxy`, `SecurityWebFilterChain` và `ServerHttpSecurity`.
3. Biết default `StrictServerWebExchangeFirewall` chặn những nhóm request nào và trả mã lỗi theo cơ chế nào.
4. Tạo bean firewall có allowlist HTTP methods đúng kiểu `HttpMethod`; tránh những công tắc vô hiệu hóa bảo vệ.
5. Phân biệt HTTP 400 do firewall, HTTP 401 do authentication, HTTP 403 do CSRF/authorization và HTTP 404/405 do routing.
6. Kiểm thử firewall độc lập và qua `WebTestClient`/HTTP proxy thực, không dựa riêng vào status.
7. Duy trì CSRF, CORS, CSP/HSTS, session và method security trên cả Reactive/Servlet theo đúng web stack.

## 2. Ma trận hỗ trợ: từ 6.4 trở đi

| Dòng Spring Security | Tình trạng Reactive HTTP firewall | Cần làm gì khi triển khai |
| --- | --- | --- |
| **5.x** | WebFlux Security có `WebFilterChainProxy`, authentication/authorization filters, nhưng **chưa có API `ServerWebExchangeFirewall` mới của 6.4** | Không copy import/class mới; bảo vệ bằng normalization ở server/ingress, route và authorization; lập kế hoạch nâng tương thích |
| **6.0–6.3** | Chưa có `ServerWebExchangeFirewall`/`StrictServerWebExchangeFirewall` theo mốc Javadoc `Since 6.4` | Không thêm bean mà phiên bản không hỗ trợ; xác minh jar thực tế |
| **6.4** | **Có** `ServerWebExchangeFirewall`, `StrictServerWebExchangeFirewall`, `ServerExchangeRejectedException`/handler và `WebFilterChainProxy.setFirewall(...)` | Có thể cấu hình firewall Reactive; các API đánh dấu `Since 6.4` |
| **6.5** | Duy trì tính năng firewall Reactive; reference guide mô tả mặc định Strict và bean tùy chỉnh | Thử request bất thường, thêm `ServerExchangeRejectedHandler` khi có yêu cầu rõ ràng |
| **7.0–7.1** | Tiếp tục hỗ trợ firewall Reactive với API tương ứng | Đối chiếu cấu hình WebFlux/security chain và tương thích Spring Framework/Boot |
| **7.2** | Tiếp tục firewall; *What's New* ghi nhận thay đổi xử lý HTTP method **không chuẩn chữ hoa/thường** | Không giữ test giả định mọi request method `get` viết thường đều bị Strict firewall từ chối; xác minh framework đã chuẩn hóa method |

**Nguồn xác minh mốc 6.4:** Javadoc chính thức của [`ServerWebExchangeFirewall`](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/firewall/ServerWebExchangeFirewall.html), [`StrictServerWebExchangeFirewall`](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/firewall/StrictServerWebExchangeFirewall.html) và [`WebFilterChainProxy` 6.4](https://docs.spring.io/spring-security/site/docs/6.4.5/api/org/springframework/security/web/server/WebFilterChainProxy.html). Tất cả đều ghi phần API liên quan có mốc `Since: 6.4`.

**Phân biệt hai phát biểu:** “Spring Security WebFlux đã tồn tại từ 5.x” là đúng, nhưng **không** có nghĩa là public API `StrictServerWebExchangeFirewall` đã có từ 5.x. Nhiệm vụ của bài này là tính khả dụng của **firewall Reactive chính thức từ 6.4**, không phủ nhận các cơ chế bảo vệ HTTP khác đã có trước đó.

### 2.1. Đừng đoán phiên bản từ BOM hoặc bài hướng dẫn

Để xác nhận một dự án có API mới hay chưa, kiểm tra **dependency đã resolve**:

```text
spring-security-web
spring-security-config
spring-webflux / spring-web
spring-boot dependencies/BOM
JDK và container thực sự sử dụng
```

Nếu IDE báo không tìm thấy `org.springframework.security.web.server.firewall.StrictServerWebExchangeFirewall`, có thể dự án vẫn dùng `spring-security-web` trước 6.4. Không thay riêng jar Security 7 vào một Spring Boot/Spring Framework cũ chỉ để import được class. Hãy dùng tổ hợp phiên bản được Boot quản lý hoặc đã được xác minh tương thích và nâng cấp theo lộ trình.

Với những tài liệu URL “6.2.x” được mirror/redirect bất thường, đừng suy mốc ra mắt từ đường dẫn; **Javadoc `Since`, API artifact đã resolve và release notes** mới là căn cứ xác định tính khả dụng.

## 3. Firewall nằm ở đâu trong pipeline WebFlux?

```text
HTTP client
     |
     v
CDN / reverse proxy / ingress
   (có thể rewrite hoặc normalize URI)
     |
     v
Reactor Netty / HTTP server / WebFlux
     |
     v
WebFilterChainProxy của Spring Security
     |
     +--> ServerWebExchangeFirewall
     |      mặc định: StrictServerWebExchangeFirewall
     |         |
     |         +--> request đáng ngờ -> REJECT
     |         |                         |
     |         |              ServerExchangeRejectedHandler
     |         |              mặc định HTTP 400
     |         |
     |         +--> request hợp lệ -> ServerWebExchange đã kiểm tra
     |
     v
Chọn SecurityWebFilterChain đầu tiên match:
   @Order(1) /api/**   hoặc   @Order(2) fallback
     |
     v
CSRF / CORS / authentication / authorization / headers ...
     |
     v
Handler / RouterFunction / controller
```

Các tên API có ý nghĩa riêng:

| Tên | Package | Vai trò |
| --- | --- | --- |
| `ServerWebExchangeFirewall` | `org.springframework.security.web.server.firewall` | Giao diện kiểm tra/wrap `ServerWebExchange` |
| `StrictServerWebExchangeFirewall` | Cùng package | Triển khai mặc định từ chối nhiều request đáng ngờ |
| `ServerExchangeRejectedException` | Cùng package | Lỗi khi request vi phạm firewall |
| `ServerExchangeRejectedHandler` | Cùng package | Chuyển request bị từ chối thành phản hồi HTTP |
| `HttpStatusExchangeRejectedHandler` | Cùng package | Handler trả HTTP status, mặc định 400 |
| `WebFilterChainProxy` | `org.springframework.security.web.server` | Tích hợp firewall và điều phối các `SecurityWebFilterChain` |
| `SecurityWebFilterChain` | `org.springframework.security.web.server` | Tập WebFilter và matcher của một chain |
| `ServerHttpSecurity` | `org.springframework.security.config.web.server` | DSL xây dựng `SecurityWebFilterChain` |

Từ Spring Security 6.4, `WebFilterChainProxy.setFirewall(ServerWebExchangeFirewall)` là điểm tích hợp và tài liệu hiện đại cho phép **công bố một bean** `ServerWebExchangeFirewall`/`StrictServerWebExchangeFirewall` để Spring Security sử dụng.

### 3.1. Firewall không phải `pathMatchers`

`authorizeExchange(a -> a.pathMatchers("/admin/**").hasRole("ADMIN"))` yêu cầu role; nó chỉ xét quyền **khi request đã vào chain và không bị firewall từ chối**. Firewall không biết `ROLE_ADMIN`, không có logic bảo vệ theo từng handler và không tự bảo đảm mọi endpoint có authorization rule phù hợp.

Tương tự, nếu `securityMatcher("/api/**")` chỉ chọn một chain hẹp mà ứng dụng không có fallback, một URL nằm ngoài tất cả chain có thể không được Spring Security bảo vệ. Để có coverage đáng tin cậy, phải tạo fallback chain và kiểm thử đường đi qua reverse proxy.

### 3.2. Một firewall, nhiều security chain

`WebFilterChainProxy` thường quản lý danh sách `SecurityWebFilterChain` và áp firewall ở cấp proxy, **trước khi lựa chọn chain**. Việc tạo hai chain không có nghĩa hai firewall khác nhau sẽ tự chạy tùy route. Đừng thiết kế một firewall “nhẹ” cho `/public/**` và “chặt” cho `/admin/**` bằng cách đăng ký hai bean cùng kiểu rồi kỳ vọng Spring tự chọn theo URL.

Nếu thật sự cần ngoại lệ dựa trên URL, thiết kế request normalization/policy có kiểm soát tại gateway/server và custom firewall được review kỹ, nhưng **không** tùy ý bỏ kiểm tra đường dẫn nguy hiểm ở public endpoint: URL công khai cũng có thể chạm vào router, static resources hoặc handler dùng chung.

## 4. Strict firewall mặc định chặn những gì?

Spring Security liệt kê các nhóm rủi ro trong Javadoc và reference guide. Trạng thái cuối cùng có thể phụ thuộc proxy và HTTP server **đã từ chối/giải mã request trước khi nó tới firewall chưa**.

| Nhóm dữ liệu | Ví dụ | Nguy cơ |
| --- | --- | --- |
| Path không normalized | `/admin/../public`, `/admin//report` | Router và matcher hiểu đường dẫn khác nhau |
| Dấu chấm phẩy/matrix segment | `/admin;role=x/report` | Path parameters làm thay đổi segment được nhìn thấy |
| Encoded slash | `/admin%2Freport` | Một tầng thấy 1 segment, tầng khác thấy 2 segment |
| Backslash | `/admin%5Creport` | Một số thành phần hiểu `\` như separator |
| Encoded percent | `/admin%25report` | Double decoding / không nhất quán URL encoding |
| Null hoặc điều khiển | `%00`, CR/LF encoded | Parser/header injection và normalization ambiguity |
| HTTP method không được phép | `TRACE` hoặc method ngoài allowlist | Cross-Site Tracing, verb tampering |
| Header name/value không hợp lệ | Ký tự control hoặc Unicode code point không xác định | Parser inconsistency, spoofing |
| Parameter name/value bất thường | Tên/giá trị chứa ký tự bị policy cấm | Ambiguous parsing và xử lý đầu vào không mong đợi |
| Hostname không được phép (nếu cấu hình) | Host sai theo allowlist tùy chỉnh | Mismatch với routing/redirect logic |

`StrictServerWebExchangeFirewall` mặc định không cho phép semicolon; có setter `setAllowSemicolon(true)` nhưng đây là **nới bảo vệ**, không phải sửa lỗi 404/403 thông thường. Chỉ bật sau khi chứng minh ứng dụng cần matrix variables và mọi tầng proxy/server/matcher đều diễn giải chúng một cách thống nhất.

### 4.1. HTTP methods mặc định

Allowlist mặc định trong reference guide:

```text
DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT
```

Vì `OPTIONS` được phép mặc định, **đừng vô tình loại bỏ nó** khi tối giản allowlist, nếu SPA cần CORS preflight. Chỉ cho GET/POST có thể là hợp lý cho một hệ thống nhất định nhưng sẽ loại PUT/PATCH/DELETE và có thể làm preflight thất bại nếu quên OPTIONS.

Đối với **Spring Security 7.2**, tài liệu *What's New* mô tả một thay đổi: Spring Framework `HttpMethod.valueOf` chuẩn hóa chữ hoa/thường, do đó một request có method non-canonical `get` có thể được xem như `GET` và **không còn bị Strict firewall từ chối chỉ do case**. Người viết test và custom `ServerExchangeRejectedHandler` không nên mặc định mọi phiên bản trả cùng status cho request này. Không đánh đồng thay đổi chuẩn hóa đó với việc mặc nhiên cho phép các method nguy hiểm.

### 4.2. Đừng nhầm “normalize” và “reject”

Firewall nghiêm ngặt **từ chối** các URL không normalized nhằm ngăn các thành phần diễn giải khác nhau. Không nên chuyển sang chiến lược “nhận mọi URI rồi tự sửa” mà chưa có hợp đồng nhất quán với ingress, router và authorization.

Khi một HTTP server đã từ chối encoded slash trước Spring Security, kết quả có thể là 400 của server; nếu proxy đã rewrite/giải mã URL, firewall có thể chỉ thấy bản đã thay đổi. Vì vậy **một status 400 đơn lẻ không chứng minh tầng nào đã chặn**; phải quan sát response, logs và cả request mà application thực sự thấy.

## 5. Cấu hình Reactive trong ứng dụng WebFlux từ Security 6.4+

Một ứng dụng Spring WebFlux thường tạo bean `SecurityWebFilterChain` qua `ServerHttpSecurity`. Khi không có yêu cầu thay đổi policy firewall, **không cần tạo bean `StrictServerWebExchangeFirewall` thủ công**: mặc định của phiên bản hỗ trợ đã sử dụng firewall nghiêm ngặt.

### 5.1. Giữ firewall mặc định, cấu hình các lớp HTTP protection bình thường

```java
package com.example.protection.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain defaultChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(a -> a
                .pathMatchers(HttpMethod.GET, "/public/**").permitAll()
                .pathMatchers("/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
                    )
                )
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
```

Ví dụ dùng form login/cookie-session để minh họa **CSRF còn bật**; nếu ứng dụng là Bearer-only API, nên thiết kế chain và authentication khác theo threat model, không sao chép form login. `CSP` cần kiểm tra tài nguyên frontend thực tế; Spring Security không tự thêm CSP mặc định. HSTS được xử lý theo cấu hình header và HTTPS request; phải kiểm tra qua public TLS nếu có proxy.

Những điều **không** được suy từ đoạn code:

- Không có lệnh `.httpFirewall(...)` trong `ServerHttpSecurity` không chứng minh firewall chưa bật.
- `anyExchange().authenticated()` không thay thế firewall và không tự đảm bảo endpoint quản trị có vai trò ADMIN.
- `permitAll()` cho public GET vẫn đi qua các HTTP security filters; POST vào public path còn có thể cần CSRF token.
- `@EnableWebFluxSecurity` và `SecurityWebFilterChain` khác với `@EnableWebSecurity`/`SecurityFilterChain` của Servlet.

### 5.2. Tùy chỉnh bằng bean firewall đúng package

Nếu chính sách ứng dụng thật sự chỉ cho phép GET/HEAD/POST và CORS preflight OPTIONS, có thể **thu hẹp allowlist HTTP methods**:

```java
package com.example.protection.reactive;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.web.server.firewall.StrictServerWebExchangeFirewall;

@Configuration
public class ReactiveFirewallConfiguration {

    @Bean
    StrictServerWebExchangeFirewall reactiveHttpFirewall() {
        StrictServerWebExchangeFirewall firewall =
            new StrictServerWebExchangeFirewall();

        firewall.setAllowedHttpMethods(List.of(
            HttpMethod.GET,
            HttpMethod.HEAD,
            HttpMethod.POST,
            HttpMethod.OPTIONS
        ));

        // Giữ mặc định nghiêm ngặt với path encoding/semicolon.
        return firewall;
    }
}
```

Điểm cần lưu ý:

1. Code yêu cầu **Spring Security 6.4+**, vì `StrictServerWebExchangeFirewall` được khai báo từ mốc đó.
2. Tham số `setAllowedHttpMethods` là `Collection<HttpMethod>` trong Javadoc, do đó dùng `HttpMethod.GET`, không đưa các string tùy tiện vào API mới.
3. Đây là ví dụ **hạn chế method**: PUT/PATCH/DELETE sẽ bị firewall từ chối, dù controller có mapping cho chúng. Nếu REST API cần các method này, **không dùng chính cấu hình này**; giữ allowlist mặc định hoặc khai báo đầy đủ theo nhu cầu.
4. Giữ `OPTIONS` nếu frontend cần CORS preflight. Đừng quên `HEAD` khi hệ thống/proxy/monitoring sử dụng nó.
5. Bean phải được đăng ký trong **Reactive application context** do Spring Security quản lý. Nếu class không nằm trong phạm vi component scan hoặc ứng dụng đang chạy Servlet mode, bean không có hiệu lực như mong đợi.
6. Đăng ký **một bean** được lựa chọn rõ ràng; đừng có nhiều `ServerWebExchangeFirewall` gây xung đột dependency injection.

Từ phiên bản hỗ trợ, tài liệu Spring Security nói rằng có thể tùy chỉnh firewall bằng cách **expose một bean**; Spring sẽ tích hợp với `WebFilterChainProxy`. Trong một dự án tự tạo `WebFilterChainProxy` hoặc can thiệp vào security infrastructure, cần xác minh bean có thực sự được sử dụng. Không tự tạo thêm một proxy song song chỉ để bật firewall.

### 5.3. Khi không muốn hạn chế HTTP method, giữ default là tốt nhất

Nếu chỉ muốn “bật strict firewall” mà không đổi gì, việc thêm bean chỉ để trả `new StrictServerWebExchangeFirewall()` là không cần thiết trong cấu hình WebFlux chuẩn ở dòng hỗ trợ. Có thể giữ bean cho mục đích kiểm thử hoặc khẳng định kiến trúc, nhưng tránh lặp cấu hình mà về sau dễ bị một module khác ghi đè.

Nếu Security 6.4+ đang chạy nhưng request bất thường vẫn lọt qua, trước tiên kiểm tra:

- Ứng dụng có thật sự dùng Spring WebFlux + Security, có `WebFilterChainProxy` trong request pipeline không?
- Request đã bị ingress/server chuẩn hóa hay bị chuyển đến service khác?
- Có cấu hình tự viết thay `WebFilterChainProxy`, `WebFilter` hoặc bỏ qua Spring Security không?
- Bean `StrictServerWebExchangeFirewall` có được dùng hay có bean khác ghi đè?
- Test đang gọi controller trực tiếp hay đã tích hợp security WebFilter?

## 6. Tùy chỉnh rejection: lỗi firewall khác lỗi quyền

Mặc định, khi firewall từ chối một `ServerWebExchange`, Spring Security dùng `ServerExchangeRejectedHandler` để trả phản hồi, thường là **HTTP 400 Bad Request**.

### 6.1. Chuỗi xử lý lỗi

```text
GET /admin//reports
       |
       v
StrictServerWebExchangeFirewall
       |
       +-- Vi phạm normalization/policy
       |
       v
ServerExchangeRejectedException
       |
       v
ServerExchangeRejectedHandler
       |
       +-- Mặc định: HttpStatusExchangeRejectedHandler -> 400
       +-- Tùy chỉnh đã duyệt: có thể trả 404 hoặc format response phù hợp
```

Đừng nhầm `ServerExchangeRejectedException` với `AccessDeniedException` hoặc `MissingCsrfTokenException`. Chúng xuất phát từ các tầng khác nhau; thay `ServerExchangeRejectedHandler` không sửa quyền ADMIN hay CSRF token.

### 6.2. Tùy chỉnh status khi tổ chức có lý do rõ

Reference guide cho phép công bố một bean handler:

```java
package com.example.protection.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.web.server.firewall.HttpStatusExchangeRejectedHandler;
import org.springframework.security.web.server.firewall.ServerExchangeRejectedHandler;

@Configuration
class ReactiveRejectedResponseConfiguration {

    @Bean
    ServerExchangeRejectedHandler rejectedExchangeHandler() {
        // Chỉ dùng nếu API contract yêu cầu 404 cho request bị firewall reject.
        return new HttpStatusExchangeRejectedHandler(HttpStatus.NOT_FOUND);
    }
}
```

Khi không có lý do cụ thể, nên giữ **mặc định HTTP 400** để dễ phân biệt request invalid với 404 của router. Nếu tổ chức chủ động dùng 404, ghi lại quyết định trong test/monitoring; response 404 giờ có thể xuất phát từ cả firewall lẫn handler routing.

**Cảnh báo vận hành:** Đổi status có thể ảnh hưởng cảnh báo WAF, API gateway, rate limit, caching hoặc client retry. Nó **không làm các request đáng ngờ hợp lệ**, không điều chỉnh allowlist và không nên dùng để che một lỗ hổng URL authorization.

### 6.3. Mẫu phân loại HTTP status

| Status thường gặp | Tầng có thể sinh | Cách phân biệt |
| --- | --- | --- |
| 400 | Firewall, HTTP server parser, validation | Xem `ServerExchangeRejectedException` và log server/proxy |
| 401 | Authentication entry point | Thiếu/không hợp lệ credential ở chain |
| 403 | Authorization hoặc CSRF/CORS | Kiểm tra role/authority, CSRF token, Origin và exception |
| 404 | Handler routing, custom rejected handler hoặc proxy | Truy theo nguồn response, không suy là “không có firewall” |
| 405 | Handler không hỗ trợ method | Method qua firewall nhưng không có controller tương ứng |
| 5xx | Lỗi ứng dụng, filter tùy chỉnh hoặc hạ tầng | Điều tra riêng, không đổi firewall để “giấu lỗi” |

Ngay cả khi status trùng, request có thể được xử lý khác nhau. Để điều tra an toàn, ghi nhận loại exception, request ID và **đường dẫn đã được làm sạch phù hợp**, không log giá trị Authorization/session/cookie hay raw payload nhạy cảm.

## 7. Những API tùy chỉnh nguy hiểm cần nhận diện

### 7.1. `setAllowSemicolon(true)`: ngoại lệ cho matrix variables

Javadoc có API:

```java
StrictServerWebExchangeFirewall firewall =
    new StrictServerWebExchangeFirewall();

// CẦN ĐÁNH GIÁ RỦI RO TRƯỚC KHI DÙNG:
firewall.setAllowSemicolon(true);
```

Khi cho phép semicolon, URL `/secure;mode=x/reports` phải được mọi thành phần xử lý thống nhất: ingress, Reactor Netty, WebFlux path parser, matcher và handler. Matrix variables chỉ nên dùng khi thật sự cần; một phương án thường rõ ràng hơn là chuyển tham số thành `?mode=x` trong query **và tiếp tục validate tham số**.

**Không mặc định rằng việc cho phép semicolon là an toàn chỉ vì handler vẫn trả 404**: request có thể được route khác sau rewrite/normalization.

### 7.2. `setAllowUrlEncodedSlash(true)` và double decoding

`%2F` là slash được URL encode. Nếu một tầng coi nó là ký tự trong một segment, nhưng tầng khác giải mã thành dấu phân cách `/`, các matcher/path variables có thể sai lệch.

```java
// KHÔNG DÙNG như mẹo sửa lỗi URL:
firewall.setAllowUrlEncodedSlash(true);
```

Thay vào đó, xác định vì sao client gửi encoded slash: path ID có chứa `/` hay proxy double-encode? Có thể dùng URL-safe identifier, UUID hoặc đặt dữ liệu có slash vào body/parameter được validate theo contract. Nếu buộc hỗ trợ, phải có test end-to-end cho **mọi** tầng xử lý URL.

### 7.3. `setUnsafeAllowAnyHttpMethod(true)` là mở rộng bề mặt tấn công

```java
// KHÔNG KHUYẾN NGHỊ:
firewall.setUnsafeAllowAnyHttpMethod(true);
```

Tùy chọn này bỏ kiểm soát allowed HTTP methods; có thể mở nguy cơ HTTP Verb Tampering và Cross-Site Tracing. Không bật chỉ vì một client gửi method không được hỗ trợ. Cân nhắc sửa client/contract, hoặc mở **đúng method cần thiết** nếu thực sự có nhu cầu được kiểm soát.

### 7.4. `ServerWebExchangeFirewall.INSECURE_NOOP`

API có hằng `INSECURE_NOOP` biểu thị firewall **không kiểm tra**. Javadoc gọi rõ đây là triển khai **không an toàn**. Không sử dụng để “giải quyết” test fail, không đưa vào production và không dùng như cách thay thế default Strict trong một dự án cũ.

### 7.5. Nới predicate header/parameter

`StrictServerWebExchangeFirewall` cho phép tùy chỉnh:

```java
firewall.setAllowedHeaderNames(...);
firewall.setAllowedHeaderValues(...);
firewall.setAllowedParameterNames(...);
firewall.setAllowedParameterValues(...);
firewall.setAllowedHostnames(...);
```

Đây là nhóm **chính sách đầu vào cấp transport**. Đừng thay tất cả predicate thành `value -> true` chỉ vì có một User-Agent hoặc header sai encoding. Nên xác định chính xác dữ liệu hợp lệ, giới hạn nguồn và điều chỉnh ngoại lệ hẹp, kèm unit tests. Đặc biệt không nhầm `setAllowedHostnames` với CORS allow-origin: Host của request và Origin của browser là các khái niệm khác nhau.

## 8. Test đơn vị: kiểm tra firewall mà không phụ thuộc controller

Khi mục tiêu là chứng minh **firewall thực sự từ chối dữ liệu bất thường**, cách đáng tin cậy nhất là gọi trực tiếp `ServerWebExchangeFirewall.getFirewalledExchange(exchange)`. Phương thức trả `Mono<ServerWebExchange>`, nên sử dụng `StepVerifier` của Reactor Test. Thử nghiệm này không cần login, authorization rule, CSRF token hay router.

### 8.1. Unit test với `MockServerWebExchange`

Ví dụ JUnit 5, `spring-test` và `reactor-test`:

```java
package com.example.protection.reactive;

import java.net.URI;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.firewall.ServerExchangeRejectedException;
import org.springframework.security.web.server.firewall.StrictServerWebExchangeFirewall;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveFirewallUnitTest {

    private final StrictServerWebExchangeFirewall firewall =
        new StrictServerWebExchangeFirewall();

    @Test
    void allowsNormalGetRequest() {
        MockServerWebExchange exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/public/ping")
        );

        StepVerifier.create(
            Mono.defer(() -> firewall.getFirewalledExchange(exchange))
        )
            .expectNextCount(1)
            .verifyComplete();
    }

    @Test
    void rejectsTraceMethod() {
        MockServerWebExchange exchange = MockServerWebExchange.from(
            MockServerHttpRequest.method(
                HttpMethod.TRACE, URI.create("http://localhost/public/ping")
            )
        );

        StepVerifier.create(
            Mono.defer(() -> firewall.getFirewalledExchange(exchange))
        )
            .expectError(ServerExchangeRejectedException.class)
            .verify();
    }

    @Test
    void rejectsSemicolonInPathByDefault() {
        MockServerWebExchange exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/admin;mode=1/report")
        );

        StepVerifier.create(
            Mono.defer(() -> firewall.getFirewalledExchange(exchange))
        )
            .expectError(ServerExchangeRejectedException.class)
            .verify();
    }
}
```

Sử dụng `Mono.defer` để chụp được cả trường hợp implementation kiểm tra request ngay khi gọi phương thức và trường hợp nó phát lỗi khi subscribe. **Các phép thử không dùng mạng thật** và chưa kiểm tra Reactor Netty/proxy normalize URI như thế nào. Đây là lý do cần thêm kiểm thử integration.

### 8.2. Test một allowlist method tùy chỉnh

Giả sử policy chỉ cho GET, HEAD, POST, OPTIONS như ở mục 5.2:

```java
@Test
void customizedFirewallRejectsPutButAllowsOptions() {
    StrictServerWebExchangeFirewall strict =
        new StrictServerWebExchangeFirewall();
    strict.setAllowedHttpMethods(
        java.util.List.of(
            HttpMethod.GET,
            HttpMethod.HEAD,
            HttpMethod.POST,
            HttpMethod.OPTIONS
        )
    );

    var put = MockServerWebExchange.from(
        MockServerHttpRequest.put("/orders")
    );
    var options = MockServerWebExchange.from(
        MockServerHttpRequest.options("/orders")
    );

    StepVerifier.create(
        Mono.defer(() -> strict.getFirewalledExchange(put))
    )
        .expectError(ServerExchangeRejectedException.class)
        .verify();

    StepVerifier.create(
        Mono.defer(() -> strict.getFirewalledExchange(options))
    )
        .expectNextCount(1)
        .verifyComplete();
}
```

Đây là test về **firewall method allowlist**, không phải test CSRF: PUT bị chặn ở firewall trước khi CSRF quyết định token; OPTIONS được firewall nhận nhưng CORS/authentication vẫn có thể từ chối vì policy riêng.

### 8.3. Unit test không phải bằng chứng đầy đủ

| Unit test firewall chứng minh | Điều nó chưa chứng minh |
| --- | --- |
| Bean Strict nhận GET thông thường | HTTP server/proxy giữ nguyên URL từ client |
| Bean Strict từ chối TRACE | Router/WebFilterChainProxy đang dùng đúng bean |
| Bean Strict từ chối semicolon | URI semicolon có tới được firewall trên production không |
| Bean Strict xử lý custom method list | API Controller và CORS cho OPTIONS hoạt động |
| Exception loại `ServerExchangeRejectedException` | Status cuối cùng sau rejection handler/proxy |

Một test có thể gọi đúng instance `new StrictServerWebExchangeFirewall()` trong khi app runtime lại sử dụng instance khác hoặc một bean/configuration không được load. Hãy kiểm tra cả wiring trong application context.

## 9. Test tích hợp qua WebTestClient và security WebFilter

WebFlux có thể kiểm thử security với `WebTestClient` đã bind vào `ApplicationContext` và áp dụng `springSecurity()`. Nếu dùng client được Spring Boot auto-configure, phải xác nhận Security filters hiện diện.

### 9.1. Tạo client tích hợp security

```java
import org.springframework.test.web.reactive.server.WebTestClient;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .configureClient()
    .build();
```

Đoạn trên cần `ApplicationContext applicationContext` và môi trường test có bean `SecurityWebFilterChain`/security infrastructure. Nếu test bind thẳng vào controller hoặc router mà không có `springSecurity()`, request có thể bỏ qua firewall và authorization; status 200 không có ý nghĩa xác nhận an toàn.

### 9.2. Test phân biệt firewall và authorization

Giả sử controller `GET /public/ping` và `GET /admin/report` tồn tại, trả 200 cho request hợp lệ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@Test
void authorizationStillProtectsAdminPath() {
    client.mutateWith(mockUser("viewer").roles("USER"))
        .get().uri("/admin/report")
        .exchange()
        .expectStatus().isForbidden();

    client.mutateWith(mockUser("admin").roles("ADMIN"))
        .get().uri("/admin/report")
        .exchange()
        .expectStatus().isOk();
}

@Test
void suspiciousPathIsRejectedOrStoppedBeforeHandler() {
    client.get().uri("/admin;mode=1/report")
        .exchange()
        .expectStatus().isBadRequest();
}
```

**Kỳ vọng `isBadRequest()` ở đây dựa trên default `HttpStatusExchangeRejectedHandler` và giả định test client chuyển nguyên URL semicolon qua security pipeline**. Nếu mock HTTP server đã normalize/parse khác, hoặc dự án cài custom rejected handler, status có thể khác. Hãy giữ unit test ở mục 8 làm oracle cho firewall riêng, sau đó điều chỉnh integration assertion theo response thực tế và chính sách đã duyệt. Không “sửa test” bằng cách tắt firewall.

### 9.3. Test HTTP method và preflight

Khi custom allowed methods chỉ có GET/HEAD/POST/OPTIONS:

- `GET /public/ping`: request hợp lệ đi qua firewall; handler quyết định status.
- `OPTIONS /public/ping`: đi qua firewall; CORS filter/router quyết định response.
- `PUT /public/ping`: bị firewall reject (mặc định 400) **trước** khi router trả 405.
- `TRACE /public/ping`: bị firewall reject theo allowlist mặc định/cấu hình.

Một CORS preflight điển hình:

```http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

**OPTIONS được firewall chấp nhận không có nghĩa preflight thành công.** Cần cấu hình CORS source phù hợp WebFlux, origin/method/header allowlist và thứ tự xử lý trước authentication. `permitAll()` cho OPTIONS không tự sinh `Access-Control-Allow-Origin`.

### 9.4. 7.2: kiểm thử method không chuẩn chữ hoa/thường

Nếu hệ thống từng có test “`get` viết thường phải bị `StrictServerWebExchangeFirewall` từ chối”, lưu ý ghi chú *What's New in Spring Security 7.2*: Spring Framework chuẩn hóa `HttpMethod.valueOf`, nên firewall có thể chỉ nhận `GET` đã canonicalized. Với nhánh này, test nên kiểm tra **hành vi được chấp nhận theo contract**, không suy rằng handler rejection phải chạy cho mọi request lowercase.

Đây **không phải** lý do cho phép TRACE hoặc tùy ý thêm method vào allowlist. Với reverse proxy, cách request line được parse trước khi tới Java cũng phải được kiểm tra, vì một số server có thể trả 400/405 trước Spring.

## 10. HTTP firewall khác CSRF, CORS, CSP/HSTS và session thế nào?

Điểm then chốt của module `SPRING_SECURITY_HTTP_PROTECTION` là các lớp bảo vệ **bổ sung lẫn nhau**, không thay thế được cho nhau.

| Cơ chế | Câu hỏi cần giải quyết | Một trường hợp điển hình |
| --- | --- | --- |
| **Reactive HTTP firewall** | Request HTTP có cấu trúc URL/method/header nguy hiểm không? | `/admin//report`, `TRACE` |
| **Authorization** | User/token có quyền gọi handler không? | USER truy cập `/admin/report` |
| **CSRF** | Request thay đổi trạng thái dùng cookie có token hợp lệ không? | Browser POST `/orders` thiếu token |
| **CORS** | Browser script từ origin này có được gửi/đọc request cross-origin theo policy không? | Preflight OPTIONS từ origin lạ |
| **CSP** | Trình duyệt được tải script/style/iframe/connect tới đâu? | Chặn XSS injection hoặc API ngoài allowlist |
| **HSTS** | Trình duyệt có phải tiếp tục dùng HTTPS với hostname này không? | Sau lần nhận HSTS trên HTTPS |
| **Session** | Authenticated user và CSRF token gắn với vòng đời phiên nào? | Hết session, logout, session fixation |
| **Method security** | Method service có được phép thực thi không? | `@PreAuthorize` chặn tác vụ nghiệp vụ |

### 10.1. Không coi firewall là CSRF protection

`POST /orders` có path hoàn toàn hợp lệ nên **đi qua Strict firewall**. Nếu browser dùng cookie/session, request này vẫn phải gửi CSRF token hợp lệ. Một `HTTP 403` thiếu token được tạo **sau** firewall và có nguyên nhân khác.

Tương tự, một `GET /admin/report` có path/method hợp lệ vẫn bị 403 nếu user không có ADMIN. Firewall không quyết định roles/authorities.

### 10.2. CORS và firewall cùng liên quan OPTIONS nhưng mục tiêu khác

Firewall có thể chặn `TRACE`/method lạ và cho phép `OPTIONS`. CORS `CorsWebFilter` hoặc `ServerHttpSecurity.cors(...)` tiếp tục kiểm tra `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`. Nếu bạn bỏ `OPTIONS` khỏi allowlist firewall để “tăng bảo mật”, mọi preflight hợp lệ có thể bị 400.

Không cần cho mọi origin `*` để “đi qua firewall”. Hãy tách debug theo thứ tự: **method/URL firewall → CORS preflight → authentication → authorization → handler**.

### 10.3. CSP và HSTS không bảo vệ URL parser

Header `Content-Security-Policy` giảm khả năng trình duyệt thực thi tài nguyên không tin cậy, nhưng nó không phát hiện `/admin%2Freports`. HSTS bảo đảm browser nâng cấp HTTP tới HTTPS theo policy đã lưu nhưng không kiểm tra path normalization. Firewall cũng không tự ghi hai header này.

Nếu API response không có CSP/HSTS, kiểm tra security headers của chain và nơi phục vụ response (application, reverse proxy hoặc CDN). HSTS cần được kiểm chứng qua HTTPS public, không chỉ HTTP backend sau TLS termination.

### 10.4. Session cookie và reverse proxy

Một firewall Reactive mặc định không tự thiết lập `SameSite`, `HttpOnly`, `Secure`, không tạo session store và không quyết định WebSession lifetime. Những thứ đó thuộc cấu hình session, authentication và hạ tầng HTTP.

Ngược lại, session management đúng cũng không giúp nếu ingress giải mã đường dẫn khác với router/security matcher. Bảo vệ phải được kiểm chứng theo **cả HTTP transport và application logic**.

## 11. Servlet firewall và Reactive firewall: không dùng nhầm API

Trong một codebase có nhiều service, người học thường thấy `StrictHttpFirewall` (Servlet) và muốn copy bean này sang WebFlux. Hai class **không tương đương** dù cùng mục đích.

| Khía cạnh | Servlet / Spring MVC | Reactive / Spring WebFlux |
| --- | --- | --- |
| Firewall API | `HttpFirewall` | `ServerWebExchangeFirewall` |
| Strict implementation | `StrictHttpFirewall` | `StrictServerWebExchangeFirewall` |
| Package | `org.springframework.security.web.firewall` | `org.springframework.security.web.server.firewall` |
| Filter-chain proxy | `FilterChainProxy` | `WebFilterChainProxy` |
| Request object | `HttpServletRequest` | `ServerWebExchange` |
| Exception firewall | `RequestRejectedException` | `ServerExchangeRejectedException` |
| Rejected handler | `RequestRejectedHandler` | `ServerExchangeRejectedHandler` |
| Mốc API Reactive | Không áp dụng; Servlet firewall tồn tại từ các dòng trước | **6.4+** |
| Test HTTP stack | `MockMvc` | `WebTestClient` |
| Chain configuration | `HttpSecurity`/`SecurityFilterChain` | `ServerHttpSecurity`/`SecurityWebFilterChain` |

### 11.1. Ví dụ Servlet để so sánh, **không** dành cho WebFlux

```java
// Servlet application ONLY
import org.springframework.context.annotation.Bean;
import org.springframework.security.web.firewall.StrictHttpFirewall;

@Bean
StrictHttpFirewall servletFirewall() {
    return new StrictHttpFirewall();
}
```

Đoạn trên có kiểu **Servlet**. Đưa nó vào WebFlux không khiến `WebFilterChainProxy` dùng được `HttpFirewall`, vì interface khác. Nếu application có cả starter MVC và WebFlux, Spring Boot thường chọn web application type theo điều kiện; chỉ có thư viện WebFlux trong dependencies **không** đủ để khẳng định WebFlux security đang active.

### 11.2. Không copy snippet CORS/CSRF của Servlet vào Reactive

Để tích hợp với Reactive:

- CORS source thuộc `org.springframework.web.cors.reactive.CorsConfigurationSource`, không phải Servlet `org.springframework.web.cors.CorsConfigurationSource`.
- CSRF repository thuộc `ServerCsrfTokenRepository`/`WebSessionServerCsrfTokenRepository`, không phải `HttpSessionCsrfTokenRepository`.
- Chain có `authorizeExchange`/`pathMatchers`, không phải `authorizeHttpRequests`/`requestMatchers`.
- Session Reactive dùng `WebSession` và `ServerSecurityContextRepository`.

Giữ **chính sách chung** (origin allowlist, quyền ADMIN, yêu cầu HTTPS, URL hợp lệ) nhưng tạo **adapter khác nhau** cho Servlet và Reactive. Firewall không được xem như một bean dùng chung Java type giữa hai stack.

## 12. Proxy, gateway và URL normalization

HTTP firewall chỉ kiểm tra dữ liệu **đã đi đến nó**. Nếu ingress rewrite hoặc decode URL trước Spring, request mà firewall xét có thể khác request browser gửi.

```text
Client request:
  GET https://public.example.com/portal/api/admin%2Freports
            |
            v
CDN / reverse proxy
  - accept/reject encoded slash?
  - normalize //, ..?
  - rewrite /portal/api -> /api?
  - set Forwarded/X-Forwarded-*?
            |
            v
WebFlux HTTP server (Reactor Netty)
  - parse request line, host, header
            |
            v
StrictServerWebExchangeFirewall (Spring Security 6.4+)
  - sees backend URI after processing above
            |
            v
SecurityWebFilterChain matcher /api/** ?
            |
            v
Spring WebFlux handler mapping
```

### 12.1. Chẩn đoán qua ba URL

| Tầng | Ví dụ đường dẫn | Rủi ro cần kiểm tra |
| --- | --- | --- |
| URL public | `/portal/api/admin%2Freports` | Reverse proxy có cho phép encoded slash không? |
| URI backend sau rewrite | `/api/admin%2Freports` hoặc `/api/admin/reports` | Proxy đã decode/normalize trước firewall? |
| URL dùng trong authorization rule | `/api/admin/**` | Security matcher có cùng cách hiểu với router không? |

Đặc biệt khi có `X-Forwarded-Prefix` hoặc context path, cần đối chiếu đường dẫn thực mà Spring WebFlux xử lý. Không viết pattern theo public prefix nếu proxy đã loại bỏ prefix ấy, cũng không cho phép `/**`/`permitAll()` chỉ để tránh lỗi authorization.

### 12.2. Trusted forwarding và Host header

Spring Boot/Spring Framework có cơ chế xử lý `Forwarded`/`X-Forwarded-*`. Những header này **chỉ nên được tin từ proxy được kiểm soát**; proxy phải xóa/ghi đè header do client bên ngoài tự cung cấp. Firewall có `setAllowedHostnames` nhưng **không thay thế** danh sách trusted proxy, TLS termination, DNS validation hay kiểm tra redirect host.

Nếu app nhìn thấy `http://service:8080` trong khi browser thấy `https://api.example.com`, kiểm tra forwarded headers cho:

- HSTS chỉ được phát theo nhận thức HTTPS phù hợp.
- Redirect login/logout và absolute URL không tự chuyển sang HTTP nội bộ.
- Cookie `Secure`/`SameSite`/`Domain`/`Path` chính xác.
- Authorization matcher xét path backend thực, không path tưởng tượng.

Không cấu hình `setAllowedHostnames(host -> true)` như một “giải pháp” cho lỗi Host header nếu ứng dụng thực sự cần allowlist hostname.

### 12.3. Spring Cloud Gateway và WebFlux

Một gateway dựa trên WebFlux cũng có HTTP request pipeline riêng. Không suy rằng một firewall bean trong **downstream service** bảo vệ luôn request đã bị gateway xử lý hoặc backend khác. Mỗi ranh giới cần được đánh giá riêng:

1. Gateway có Spring Security/WebFilterChainProxy và firewall đang hoạt động hay không?
2. Gateway có rewrite path, decode URI hoặc strip prefix không?
3. Downstream service có security chain/firewall đúng stack và đúng version không?
4. URL nhạy cảm có thể được gọi trực tiếp tới backend, bỏ qua gateway không?

Không chạy song song hai cấu hình mâu thuẫn — một bên cho phép encoded slash, bên kia từ chối — rồi chỉ dựa vào “request thành công” để kết luận hệ thống an toàn. Hãy ghi rõ contract về canonical URL và đường dẫn được hỗ trợ.

## 13. Kiểm thử HTTP thực tế qua HTTPS/ingress

### 13.1. Những phép thử tối thiểu

| Request | Dự kiến khi hệ thống giữ strict policy | Phần cần quan sát |
| --- | --- | --- |
| GET `/public/ping` | Đến handler nếu rule cho phép | Security headers, status, handler |
| GET `/admin/report` với USER | 403 do authorization | Không phải lỗi firewall |
| GET `/admin/report` với ADMIN | Qua authorization | Handler tồn tại, response phù hợp |
| GET `/admin//report` | Bị từ chối/normalize an toàn | Server/proxy hay firewall chặn? |
| GET `/admin;v=1/report` | Default Strict không cho semicolon | `ServerExchangeRejectedException` hoặc chặn trước |
| GET `/admin%2Freport` | Default Strict không cho encoded slash nếu thấy nó | Proxy decode/bỏ chặn trước không? |
| TRACE `/public/ping` | Bị chặn ở allowlist method | 400/405 theo tầng xử lý |
| OPTIONS `/api/orders` có preflight | Được firewall nhận; CORS quyết định | CORS allow-origin, methods, headers |
| POST `/orders` cookie/session thiếu CSRF | 403 do CSRF nếu CSRF được bật | Token repository/matcher |
| GET `/unknown` không auth | Không bypass security | Fallback chain/entry point |

Kỳ vọng “bị chặn” không đồng nghĩa **luôn HTTP 400 từ Spring Security**: proxy/container cũng có thể từ chối trước, và custom handler có thể thay status. Cần có cả **unit test cho firewall** và **end-to-end test cho HTTP public**.

### 13.2. Các lệnh kiểm thử bằng curl

Các URL bên dưới chỉ mang tính minh họa. Chỉ gửi request tới hệ thống bạn **sở hữu và có quyền kiểm thử**; tránh chạy request khác thường trên dịch vụ không thuộc phạm vi.

```bash
# Kiểm tra route bình thường và các security headers trên HTTPS public.
curl -i "https://api.example.com/public/ping"

# OPTIONS preflight: phải được xử lý theo CORS policy, không bị
# tắt nhầm bởi firewall method allowlist.
curl -i -X OPTIONS "https://api.example.com/api/orders" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"

# Không khuyến nghị dùng trên production ngoài phạm vi kiểm thử:
# giữ nguyên path đôi slash để kiểm tra upstream có normalize hay không.
curl --path-as-is -i "https://api.example.com/admin//report"

# Giữ nguyên phần ../ thay vì để curl tự normalize:
curl --path-as-is -i "https://api.example.com/admin/../report"

# Gửi URL có dấu chấm phẩy trong path:
curl --path-as-is -i "https://api.example.com/admin;v=1/report"
```

Khi dùng encoded slash, một số client/proxy tự decode hoặc từ chối; phải quan sát request line và path cuối cùng. `--path-as-is` giúp `curl` tránh một số normalization phía client nhưng **không buộc proxy/server giữ nguyên request**.

Không ghi/lưu Bearer token, session cookie hay đầy đủ URL nhạy cảm vào log công khai; có thể dùng ID của request và nhóm lý do rejection đã làm sạch.

### 13.3. So sánh local/mock và deployment thật

| Môi trường test | Có thể chứng minh | Giới hạn |
| --- | --- | --- |
| Unit `StrictServerWebExchangeFirewall` | API nhận/từ chối exchange định nghĩa sẵn | Không qua server, proxy, filter-chain bean wiring |
| `WebTestClient.bindToApplicationContext` | Spring Security WebFilters, authorization/CSRF/CORS | Không tái hiện mọi behavior Reactor Netty/TLS/ingress |
| `WebTestClient.bindToServer` hoặc HTTP client qua TCP | Server parse URI, filter/handler thực | Chưa chắc qua cùng proxy production |
| Staging qua ingress + HTTPS | Toàn đường public tương tự production | Còn khác CDN/cache/headers/traffic |
| Canary/production smoke test có kiểm soát | Chính sách đang phục vụ thật | Phải tránh request có side effect/tải bất thường |

Đảm bảo test negative không làm thay đổi dữ liệu thật. Với các endpoint admin, dùng tài khoản kiểm thử giới hạn quyền và kiểm tra response/correlation IDs thay vì chụp thông tin nhạy cảm.

## 14. Lộ trình nâng cấp từ WebFlux cũ lên dòng hỗ trợ firewall

**Mục tiêu của migration:** không chỉ để Java biên dịch với class `StrictServerWebExchangeFirewall`, mà còn để backend có **một cách hiểu HTTP URL nhất quán** với Security matcher, WebFlux route, proxy và chính sách client.

### 14.1. Trước Spring Security 6.4

Nếu service đang ở 5.x hoặc 6.0–6.3:

1. Không import `ServerWebExchangeFirewall`/`StrictServerWebExchangeFirewall` như thể chúng đã tồn tại.
2. Kiểm tra các lớp bảo vệ khác: WebFlux Security chain, authorization, CSRF, CORS và security headers.
3. Giữ chính sách reject/normalize URL nguy hiểm tại ingress/server, route canonical và method security; đây là giải pháp hạ tầng/kiến trúc, **không tương đương hoàn toàn** firewall của 6.4.
4. Nâng Spring Boot/Framework/Security theo tổ hợp tương thích trước khi bật API mới.
5. Ghi lại response baseline cho URL path có semicolon, encoded slash, duplicate slash và method TRACE.

### 14.2. Bắt đầu từ 6.4

Khi đã nâng đến 6.4+:

1. Xác minh class có trong `spring-security-web` và `WebFilterChainProxy.setFirewall` được cung cấp.
2. Giữ `StrictServerWebExchangeFirewall` mặc định trừ khi có yêu cầu được duyệt.
3. Nếu có bean tùy chỉnh, xác minh application context dùng đúng instance và cấu hình dự kiến.
4. Kiểm tra rule chọn chain và fallback; firewall không thay authorization.
5. Chạy lại unit test, WebTestClient integration và staging proxy tests.
6. Nếu request cũ bị reject, xác định client/proxy nào tạo URL bất thường trước khi nới firewall.
7. Kiểm tra CORS preflight nếu đã sửa allowlist HTTP methods.
8. Quan sát lỗi `ServerExchangeRejectedException`, nhưng không log credential/payload nhạy cảm.

### 14.3. Spring Security 6.5 và 7.x

Với 6.5 và các dòng 7.x, tiếp tục ưu tiên firewall nghiêm ngặt và Java DSL đúng web stack. Ở dòng 7.2, điều chỉnh test HTTP method lower-case theo thay đổi do Spring Framework chuẩn hóa `HttpMethod.valueOf`. Nếu hệ thống có custom rejection handler dùng để log/cảnh báo method `get` viết thường, nguồn tín hiệu này có thể không còn được gọi trong trường hợp đã chuẩn hóa; thêm quan sát ở tầng HTTP server/ingress khi có nhu cầu kiểm soát exact request line.

Không cần “nâng lên 7 mới dùng được Reactive firewall”; **mốc API chính thức là 6.4**. Ngược lại, việc đã nâng lên 7 không tự chứng minh fallback chain, CORS/CSRF hoặc header policies của ứng dụng đúng.

### 14.4. So sánh hành vi trước/sau

| Kịch bản | Trước khi nâng | Sau khi nâng lên dòng có Strict firewall | Ý nghĩa |
| --- | --- | --- | --- |
| GET bình thường | Controller nhận request | Controller vẫn nhận request | Không phá luồng hợp lệ |
| GET admin với USER | Authorization từ chối | Authorization tiếp tục từ chối | Bảo toàn rule vai trò |
| Duplicate slash | Phụ thuộc server/router | Có thêm cơ chế Strict reject nếu path bất thường tới firewall | Ngăn mismatch |
| Semicolon path | Có thể bị xử lý khác nhau | Strict mặc định không cho semicolon | Cần sửa client/route nếu trước đây phụ thuộc matrix vars |
| Encoded slash | Phụ thuộc HTTP server/proxy | Strict có policy reject nếu nhận encoded slash | Không tự nới khi endpoint 400 |
| TRACE | Có thể bị server/Security khác xử lý | Strict allowlist không cho TRACE | Hạn chế HTTP Verb Tampering |
| CORS OPTIONS | Tùy CORS config | Vẫn cần OPTIONS trong firewall allowed methods | Preflight không bị chặn nhầm |
| POST dùng browser cookie | CSRF theo config cũ | CSRF vẫn phải được kiểm tra | Firewall không thay CSRF |
| CSP/HSTS | Theo header config | Vẫn theo header config | Firewall không tự thêm header |
| Login/logout/session | Theo Security/WebSession | Vẫn cần thử đầy đủ | Không nhầm với firewall |

## 15. Những lỗi phổ biến và cách chẩn đoán

### Lỗi A — Class `StrictServerWebExchangeFirewall` không tồn tại

**Nguyên nhân thường gặp:** project dùng Spring Security trước 6.4, thiếu `spring-security-web` đúng phiên bản, hoặc classpath trộn nhiều dòng.

**Cách xử lý:** kiểm tra dependency graph/managed versions. Không lấy `StrictHttpFirewall` Servlet thay vào; nâng version tương thích rồi chạy test.

### Lỗi B — Có bean firewall nhưng request lạ vẫn vào handler

**Khả năng:** bean không được Spring Security dùng trong runtime, app không chạy đúng WebFlux Security pipeline, request đã được ingress normalize, hoặc custom WebFilterChainProxy bỏ qua cấu hình.

**Cách xử lý:** test trực tiếp bean, kiểm tra wiring `WebFilterChainProxy` và quan sát path tại các tầng. Nếu request được rewrite thành URL hợp lệ trước firewall, response thành công không tự chứng minh firewall đã bị tắt.

### Lỗi C — POST/PUT/DELETE từ client trả 400 sau khi thêm allowed methods

**Khả năng:** bean `StrictServerWebExchangeFirewall` đã thu hẹp method list nhưng không bao gồm method client sử dụng.

**Cách xử lý:** cập nhật allowlist **đúng hợp đồng API** hoặc giữ default; không dùng `setUnsafeAllowAnyHttpMethod(true)`. Đồng thời kiểm tra CSRF sau khi method đi qua firewall.

### Lỗi D — CORS preflight chuyển từ 200/204 sang 400

**Khả năng:** custom firewall loại `OPTIONS` khỏi allowlist; hoặc proxy chặn OPTIONS.

**Cách xử lý:** giữ OPTIONS nếu browser cần preflight, cấu hình Reactive CORS source và test origin/method/header. Không cố xử lý bằng `csrf.disable()`.

### Lỗi E — Request path có semicolon bị từ chối

**Nguyên nhân:** Strict firewall mặc định không cho semicolon để tránh URL ambiguity.

**Cách xử lý:** ưu tiên thay matrix variable bằng query/body parameter phù hợp. Nếu bắt buộc phải cho phép, xác minh route/matcher/parser/proxy, review và negative test trước khi cân nhắc `setAllowSemicolon(true)`.

### Lỗi F — Encoded slash bị chặn khi API truyền tên file có ký tự `/`

**Nguyên nhân:** `%2F` trong path có thể làm các tầng parse URL khác nhau; Strict firewall mặc định reject.

**Cách xử lý:** dùng ID URL-safe, encode dữ liệu trong body, tránh dùng slash trong một path segment. Không bật `setAllowUrlEncodedSlash(true)` mà chưa có security review.

### Lỗi G — 403 bị hiểu nhầm là do firewall

**Nguyên nhân:** test user thiếu ADMIN hoặc POST thiếu CSRF token.

**Cách xử lý:** test một GET thường với USER/ADMIN; thử POST với token CSRF hợp lệ. Quan sát loại exception. Firewall rejection thường đi qua `ServerExchangeRejectedHandler`, còn 403 thường từ authentication/authorization/CSRF.

### Lỗi H — WebFlux app có bean `StrictHttpFirewall` nhưng không có tác dụng

**Nguyên nhân:** dùng nhầm **Servlet** firewall type; Reactive pipeline cần `ServerWebExchangeFirewall`.

**Cách xử lý:** xác định `WebApplicationType` thực tế, đổi sang đúng package Reactive nếu phiên bản hỗ trợ, và chạy test `WebTestClient`. Không cố dùng hai web stacks trong một chain.

### Lỗi I — Test `get` viết thường thất bại khác giữa 7.1 và 7.2

**Nguyên nhân:** Spring Framework chuẩn hóa `HttpMethod.valueOf` ở nhánh tương ứng, làm Strict firewall không còn nhìn thấy method với case non-canonical như trước.

**Cách xử lý:** dùng test theo đúng version, kiểm tra method sau parser và custom rejected handler. Nếu bắt buộc ghi nhận raw lowercase method, cần quan sát ở HTTP server/proxy, không giả định Java `HttpMethod` giữ nguyên cách viết.

### Lỗi J — HTTP 400 chỉ xuất hiện sau khi triển khai ingress mới

**Nguyên nhân:** reverse proxy thay đổi URL rewrite, encoded slash policy, WAF hoặc Host/forwarded headers.

**Cách xử lý:** so sánh raw request public và path backend, correlation ID, status/source của 400. Không tắt firewall chỉ vì local mock test qua được.

### Lỗi K — 404 sau khi dùng custom rejected handler

**Nguyên nhân:** `HttpStatusExchangeRejectedHandler(HttpStatus.NOT_FOUND)` đã thay mặc định 400 bằng 404. Nhìn 404 không đủ biết request có tới controller hay không.

**Cách xử lý:** ghi rõ status mapping, test direct firewall exception và HTTP integration, dùng metric/log nguồn lỗi được làm sạch.

## 16. Bài tập thực hành

### Bài 1 — Xác định mốc phiên bản

Cho ba service dùng Spring Security 6.3.x, 6.4.x và 7.x. Hãy xác định service nào có thể import `ServerWebExchangeFirewall`, `StrictServerWebExchangeFirewall` và công bố bean firewall. Dùng Javadoc `Since` làm chứng cứ. Giải thích tại sao `WebFilterChainProxy` đã có từ 5.0 **không** đồng nghĩa firewall Reactive API có từ 5.0.

### Bài 2 — Từ unit test tới integration test

Sử dụng `StrictServerWebExchangeFirewall` mặc định và `MockServerWebExchange` để kiểm thử: GET thường hợp lệ, TRACE bị từ chối, path có semicolon bị từ chối. Sau đó viết `WebTestClient` test với security pipeline thực. So sánh nguồn và status của lỗi.

### Bài 3 — Chính sách HTTP method cho CORS

Một nhóm chỉ khai báo `setAllowedHttpMethods(List.of(HttpMethod.GET, HttpMethod.POST))` rồi báo frontend SPA không gọi POST JSON được. Hãy phân tích preflight OPTIONS, điều chỉnh allowed methods và kiểm thử CORS allowlist origin/header/credentials. Phân biệt HTTP 400 của firewall với CORS 403.

### Bài 4 — URL chứa encoded slash

Ứng dụng WebFlux có endpoint `GET /files/{id}`; client dùng ID chứa slash, tự encode thành `%2F`. Hãy đề xuất hai cách thiết kế URL khác để không phải nới firewall, và tạo test `/files/a%2Fb` qua mock, HTTP server và ingress thực.

### Bài 5 — WebFlux và Servlet song song

Thiết kế hai ứng dụng **độc lập** có cùng policy `/admin/**` cần ADMIN và `/public/**` cho phép GET. Dùng `StrictHttpFirewall` cho Servlet, `StrictServerWebExchangeFirewall` cho WebFlux 6.4+. Kiểm thử bằng `MockMvc` và `WebTestClient`, đối chiếu exception/status/rejection handlers theo stack.

### Bài 6 — Phân biệt bốn lớp phòng vệ

Với browser form session:

- GET `/admin/report` bằng user thường.
- POST `/orders` có session nhưng thiếu CSRF token.
- OPTIONS `/api/orders` từ origin bị cấm.
- GET `/admin//report`.

Hãy xác định **cơ chế được kỳ vọng chặn** từng request: authorization, CSRF, CORS, firewall. Kiểm tra thêm CSP/HSTS trên response hợp lệ; giải thích vì sao các lớp phòng vệ không hoán đổi cho nhau.

### Bài 7 — Migration 6.3 → 6.5 → 7.2

Lập checklist tương thích khi nâng service WebFlux: dependency alignment, firewall bean, method allowlist, path normalization, URL rewrite, tests header/parameter, CORS/CSRF, security chain coverage. Bổ sung regression test phản ánh thay đổi case của HTTP method ở dòng 7.2 mà không nới allowlist nguy hiểm.

### Bài 8 — Proxy và custom error handler

Một gateway rewrite public `/portal/admin//report` thành backend `/admin/report`. Backend Strict firewall không reject vì chỉ thấy path đã normalize. Hãy xác định lỗi ở tầng nào, đề xuất policy canonical URL ở ingress và test âm xác nhận request bất thường bị chặn sớm. Nếu handler cấu hình trả 404 thay 400, chứng minh vẫn có rejection bằng unit test/metric.

## 17. Checklist trước khi đưa Reactive firewall vào production

- [ ] Đã xác định **Spring Security 6.4+**, Spring Boot/Framework tương thích và đúng `spring-security-web` đã resolve.
- [ ] Ứng dụng thực sự chạy **WebFlux** với `WebFilterChainProxy`, không nhầm Servlet stack.
- [ ] Giữ `StrictServerWebExchangeFirewall` mặc định, hoặc bean tùy chỉnh có lý do và test rõ ràng.
- [ ] Không dùng `ServerWebExchangeFirewall.INSECURE_NOOP`, `setUnsafeAllowAnyHttpMethod(true)` hoặc allow-all predicates.
- [ ] Không nới encoded slash/semicolon/backslash/null/percent chỉ để vượt lỗi ở staging.
- [ ] Custom `setAllowedHttpMethods` có đúng kiểu `HttpMethod`, bao gồm những method cần thiết và `OPTIONS` cho CORS preflight khi có browser.
- [ ] Firewall exception/rejected handler được phân biệt với lỗi authentication, authorization, CSRF, CORS và routing.
- [ ] Unit test `getFirewalledExchange` và integration test WebTestClient đã chạy ở đúng security context.
- [ ] Có test raw URL qua HTTP server, reverse proxy/ingress, HTTPS public và URL rewrite.
- [ ] Mọi endpoint nhạy cảm có authorization rule và fallback `SecurityWebFilterChain`, không trông cậy firewall thay quyền.
- [ ] Browser POST dùng cookie vẫn có CSRF; CORS origin/headers/credentials được kiểm thử độc lập.
- [ ] CSP được ghi trên HTML response phù hợp, HSTS trên HTTPS public, session/cookie có policy đúng.
- [ ] Đã xem xét khác biệt handling method case ở nhánh Security 7.2 khi viết regression test/custom rejection metric.
- [ ] Logs/metrics không chứa session cookie, JWT, password hay dữ liệu nhạy cảm; có correlation ID.
- [ ] Có phương án rollback phiên bản/config và kế hoạch kiểm tra false positives sau khi phát hành.

## Nguồn tham khảo chính thức

1. [Spring Security 6.5 — Reactive ServerWebExchangeFirewall](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/firewall.html) — default Strict, URL normalization, HTTP method allowlist, bean customization và rejected handler.
2. [Spring Security 6.5 API — ServerWebExchangeFirewall](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/firewall/ServerWebExchangeFirewall.html) — giao diện `Since: 6.4`.
3. [Spring Security 6.5 API — StrictServerWebExchangeFirewall](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/firewall/StrictServerWebExchangeFirewall.html) — class `Since: 6.4`, methods và các policy mặc định.
4. [Spring Security 6.4 API — WebFilterChainProxy](https://docs.spring.io/spring-security/site/docs/6.4.5/api/org/springframework/security/web/server/WebFilterChainProxy.html) — `setFirewall` `Since: 6.4` và `setExchangeRejectedHandler`.
5. [Spring Security — Reactive WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — `ServerHttpSecurity`, `SecurityWebFilterChain` và lựa chọn nhiều chain.
6. [Spring Security — Reactive Request Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html) — `pathMatchers`, `anyExchange` và role/authority.
7. [Spring Security — Servlet HTTP Firewall](https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html) — đối chiếu `StrictHttpFirewall`/`RequestRejectedException` với WebFlux.
8. [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html), [Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html) và [Reactive Security Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html) — các lớp HTTP protection độc lập với firewall.
9. [Spring Security — WebTestClient Test Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html) — gắn Spring Security vào test client.
10. [Spring Security 7.2 — What's New](https://docs.spring.io/spring-security/reference/7.2/whats-new.html) — thay đổi xử lý method lowercase trong `StrictServerWebExchangeFirewall` do `HttpMethod.valueOf` được chuẩn hóa.

**Tự đánh giá:** Javadoc ghi Reactive `ServerWebExchangeFirewall` có từ dòng nào? Vì sao WebFlux 5.x đã có `WebFilterChainProxy` mà không thể import class firewall mới? Khác biệt giữa `ServerExchangeRejectedException`, CSRF 403 và authorization 403 là gì? Tại sao khi cho phép GET/POST nhưng bỏ OPTIONS có thể làm hỏng CORS preflight? Vì sao một HTTP 400 từ proxy không chứng minh firewall Spring đã kiểm tra URL? Và tại sao cần tiếp tục bảo vệ session, CSP/HSTS, CSRF và role authorization dù Strict firewall đã bật?
