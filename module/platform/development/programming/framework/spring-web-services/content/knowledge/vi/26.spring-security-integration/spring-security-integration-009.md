# CSRF, yêu cầu SOAP POST và thiết kế ngoại lệ có phạm vi phù hợp

Khi tích hợp **Spring Security** với **Spring Web Services (Spring-WS)**, một hiện tượng rất thường gặp là client Java/đối tác gửi SOAP qua HTTP `POST` nhưng nhận `403 Forbidden` trước khi method `@Endpoint` được gọi. Một nguyên nhân có thể là **CSRF protection** của Spring Security: request làm thay đổi trạng thái qua HTTP POST không có CSRF token hợp lệ. Cách sửa nhanh `http.csrf(csrf -> csrf.disable())` thường làm SOAP client hoạt động, nhưng cũng có thể vô tình **loại bỏ bảo vệ CSRF của giao diện web và các endpoint dùng cookie session** trên cùng ứng dụng.

Bài **“CSRF, yêu cầu SOAP POST và thiết kế ngoại lệ có phạm vi phù hợp”** thuộc chương **Tích hợp Spring Security** của module `SPRING_WEB_SERVICES`. Bối cảnh module là phát triển SOAP **contract-first** với XSD/WSDL, JAXB, `@Endpoint`, `WebServiceTemplate`, SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích trong hệ thống doanh nghiệp. Bài tập trung vào **mô hình đe dọa CSRF ở tầng HTTP**, phân biệt **SOAP client máy–máy** với **người dùng trình duyệt**, cách giới hạn ngoại lệ theo **HTTP method, servlet URL và cơ chế xác thực**, và cách kiểm chứng rằng việc sửa HTTP 403 **không làm suy yếu các endpoint khác**.

Các ví dụ nhắm tới **Spring Security Servlet stack 6.x** và cú pháp `SecurityFilterChain`/lambda DSL, trên JDK 17+ và Spring-WS phù hợp. Spring Security 7.x vẫn có các cơ chế tương ứng nhưng có thể thay đổi API/matcher defaults; **kiểm tra phiên bản dependency chính xác** trước khi copy code. Tên đường dẫn, operation, authority, URL và certificate trong bài là giả định; không phải cấu hình production sẵn dùng.

> **Quy tắc chính:** Không nên hỏi “SOAP có cần tắt CSRF không?” rồi trả lời theo công nghệ. Cần hỏi **ai có thể phát request, trình duyệt có tự đính kèm thông tin xác thực hay không, request có side effect không và cơ chế nào buộc bên gửi chứng minh ý định**. Nếu client máy–máy tự cung cấp credential không được trình duyệt gửi tự động, có thể cân nhắc một **ngoại lệ CSRF thật hẹp**; nếu endpoint dùng cookie session hoặc browser HTTP Basic auto credentials, cần đánh giá CSRF nghiêm túc.

## 1. CSRF là gì và tại sao Spring Security quan tâm tới HTTP POST?

**Cross-Site Request Forgery (CSRF)** là tình huống một website/trang do attacker kiểm soát khiến trình duyệt của người dùng đang đăng nhập **gửi request đến hệ thống đích**; trình duyệt có thể tự đính kèm thông tin xác thực như session cookie, hoặc một số cơ chế credential ambient khác. Nếu hệ thống chỉ kiểm tra “người dùng đã được xác thực” mà không kiểm tra **request có thực sự xuất phát từ ý định của người dùng hay không**, hành động cập nhật dữ liệu có thể bị thực thi.

### 1.1. Minh họa luồng tấn công CSRF

~~~mermaid
sequenceDiagram
    participant U as Người dùng đã đăng nhập
    participant B as Trình duyệt
    participant A as Trang attacker
    participant S as Ứng dụng có cookie session

    U->>S: Đăng nhập và nhận session cookie
    S-->>B: Set-Cookie: SESSION=...
    B->>A: Người dùng mở trang không tin cậy
    A->>B: HTML form/script kích hoạt request tới S
    B->>S: POST /account/change với cookie nếu browser policy cho phép
    S->>S: Xác thực cookie đúng
    Note over S: Nếu thiếu CSRF protection và request được chấp nhận
    S-->>B: Hành động được thực hiện trái ý người dùng
~~~

Đây là **mô hình khái niệm**. Việc cookie có được gửi thật không còn phụ thuộc thuộc tính `SameSite`, browser policy, top-level navigation, loại request và deployment; khả năng attacker tạo một request có đúng `Content-Type`/SOAP XML cũng cần đánh giá cụ thể. **Không kết luận mọi SOAP endpoint mặc nhiên bị tấn công bằng một HTML form bất kỳ**, nhưng cũng không coi XML/SOAP là bằng chứng chống CSRF đầy đủ.

### 1.2. CSRF khác XSS, SSRF và CORS

| Vấn đề | Mục tiêu | Tại sao cần phân biệt khi xử lý SOAP? |
| --- | --- | --- |
| **CSRF** | Lạm dụng credential mà trình duyệt tự mang sang request không do người dùng chủ động. | Filter có thể chặn SOAP POST khi thiếu token. |
| **XSS** | Chạy script không tin cậy trong origin của ứng dụng. | Có thể làm mất hiệu quả một số bảo vệ CSRF nếu attacker đã kiểm soát same-origin script. |
| **SSRF** | Khiến server mở kết nối tới URI do attacker chi phối. | Liên quan WS-Addressing `ReplyTo`, XML resolver, service URL; không được sửa bằng CSRF token. |
| **CORS** | Chính sách trình duyệt về JavaScript cross-origin access và một số loại request. | Không tự thay thế CSRF; form POST có thể được gửi không cần đọc response. |
| **WS-Security** | Bảo vệ SOAP message bằng token, chữ ký, timestamp, encryption theo policy. | Không phải Spring Security `CsrfFilter`; HTTP POST vẫn có thể bị chặn trước khi WSS4J chạy. |

**Authentication** xác định “ai đang gọi”; **authorization** xác định “người gọi được làm gì”; **CSRF protection** bảo vệ một lớp rủi ro khác: request dùng **quyền ambient của trình duyệt** mà không phản ánh ý định người dùng. Không lấy một biện pháp tự động thay thế toàn bộ biện pháp còn lại.

### 1.3. Mặc định của CsrfFilter trên HTTP methods

Trong Servlet stack, Spring Security mặc định áp dụng CSRF protection cho **các HTTP methods không an toàn**, thông thường loại trừ:

~~~text
GET
HEAD
TRACE
OPTIONS
~~~

và yêu cầu token với các method khác như:

~~~text
POST
PUT
PATCH
DELETE
~~~

Điều này dựa vào semantics HTTP safe/unsafe methods, không dựa vào **SOAP Body QName** hay operation name. Một SOAP request thông dụng là:

~~~http
POST /ws HTTP/1.1
Host: orders.example.test
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:v1/CreateOrder"
Authorization: Bearer <access-token>
~~~

Vì method là **POST**, request có thể bị `CsrfFilter` kiểm tra, cho dù Body chứa XML hợp lệ theo WSDL và có header SOAPAction đúng.

**Đừng nhầm mặc định CSRF với mặc định SOAP:** Spring Security chưa parse `<soap:Body>` để quyết định CSRF; nó hoạt động ở tầng **Servlet Filter**, trước các bước endpoint mapping/JAXB thông thường của Spring-WS.

## 2. Vị trí chặn 403 trong pipeline Spring-WS

Một Spring-WS service nhận HTTP request qua `MessageDispatcherServlet`, nhưng `springSecurityFilterChain` có thể xử lý request **trước khi Servlet được gọi**.

~~~mermaid
flowchart TD
    A["HTTP POST /ws: SOAP Envelope"] --> B["Reverse proxy / TLS / gateway"]
    B --> C["Servlet container + Spring Security FilterChainProxy"]
    C --> D{"CSRF requirement và token hợp lệ?"}
    D -- "Không" --> E["HTTP 403; chưa vào SOAP dispatcher"]
    D -- "Có hoặc được loại trừ có phạm vi" --> F["Authentication + Authorization filters"]
    F --> G{"Có quyền gọi operation/endpoint?"}
    G -- "Không" --> H["HTTP 401/403 theo security entry point/policy"]
    G -- "Có" --> I["MessageDispatcherServlet"]
    I --> J["SOAP MessageFactory, EndpointMapping, Interceptors"]
    J --> K["WSS4J / XML validation / JAXB / @Endpoint"]
    K --> L["SOAP response hoặc SOAP Fault"]
~~~

Sơ đồ **đơn giản hóa**: thứ tự thực tế của các filters phụ thuộc security configuration và version. `CsrfFilter` thường chạy sớm trong filter chain; không nên giả định mỗi HTTP 403 đều do CSRF. Gateway, method security, authentication/authorization, rate limit hoặc custom filter cũng có thể trả 403.

### 2.1. HTTP 403 không nhất thiết là SOAP Fault

| Hiện tượng | Tầng gây lỗi thường gặp | Client quan sát |
| --- | --- | --- |
| CSRF token thiếu/sai | `CsrfFilter` ở HTTP servlet filter chain. | `403` và có thể HTML/JSON/empty body; **không có SOAP Fault chuẩn**. |
| Token bearer không hợp lệ | Authentication filter/resource server. | `401 Unauthorized` hoặc entry point policy; không có SOAP Fault. |
| Người gọi xác thực nhưng thiếu authority | HTTP authorization hoặc method security. | `403`; có thể chưa vào `@Endpoint`. |
| WS-Security Signature sai | WSS4J SOAP interceptor sau khi parse Envelope. | SOAP Fault bảo mật khi pipeline tạo được SOAP response. |
| XSD payload sai | Spring-WS validation/endpoint adapter. | SOAP Fault hoặc response theo contract/policy. |
| SOAPAction/Body QName sai | SOAP endpoint mapping. | SOAP Fault/server mapping error hoặc transport-specific status. |
| HTTPS trust/certificate sai | TLS/JSSE/gateway. | Lỗi handshake **không nhất thiết có HTTP response**. |

Nếu client Java nhận HTTP 403, hãy **kiểm tra Content-Type và response thực tế**, không tự chuyển nó thành `SoapFaultClientException`. Lỗi bị chặn bởi `CsrfFilter` có thể xảy ra trước khi `Wss4jSecurityInterceptor` hoặc `@Endpoint` được gọi.

### 2.2. Vì sao WSDL GET thường hoạt động còn SOAP POST lại lỗi?

Một WSDL có thể được công bố:

~~~text
GET  /ws/orders.wsdl  → 200 OK
POST /ws              → 403 Forbidden
~~~

`GET` thuộc nhóm method được bỏ qua CSRF mặc định. `POST` cần token nếu chain bảo vệ CSRF và không có ngoại lệ. **WSDL tải được không chứng minh SOAP endpoint đã có cấu hình authentication/authorization/CSRF đúng**.

Cũng cần phân biệt URL WSDL và URL thực hiện SOAP: `/ws/orders.wsdl` là điểm tải contract, còn `/ws` là endpoint nhận SOAP POST trong ví dụ. Đừng cấu hình ngoại lệ theo cả `/ws/**` chỉ vì muốn SOAP POST hoạt động; pattern rộng có thể bao gồm các URL không liên quan hoặc được mở rộng sau này.

## 3. Quyết định CSRF theo cơ chế xác thực, không chỉ theo SOAP

Câu hỏi cốt lõi là: **browser có thể phát một request hợp lệ và tự đính kèm credential của nạn nhân hay không?**

### 3.1. Ma trận mô hình sử dụng

| Kiểu client/credential | Browser tự gửi credential khi attacker kích hoạt request? | CSRF decision |
| --- | --- | --- |
| **SOAP máy–máy** qua `Authorization: Bearer` do backend tự chèn, token không lưu dạng cookie | Thông thường **không**. Website attacker không tự lấy bearer token của backend. | Có thể ngoại lệ **hẹp** nếu endpoint chỉ chấp nhận cơ chế này, kèm authn/authz. |
| SOAP máy–máy dùng **mTLS private client key** được server kiểm tra và ủy quyền | Không phải cookie session; nhưng browser có thể có client certificate và auto-select theo policy trong một số môi trường. | Đánh giá browser reachability/client-cert UX; không coi mTLS tự miễn nhiễm CSRF trong mọi hệ thống. |
| SOAP máy–máy dùng **WS-Security Signature** bắt buộc trên Body với private key chỉ backend sở hữu | Website attacker thông thường không thể tạo chữ ký hợp lệ. | Có thể ngoại lệ hẹp nếu **mọi request** thực sự được xác minh trước side effect. |
| SOAP dùng **session cookie** của ứng dụng web | **Có thể**, tùy SameSite/browser policy. | **Giữ CSRF protection** và xác thực token. |
| SOAP dùng **HTTP Basic** từ browser (cached ambient credentials) | Browser có thể tự đính kèm Basic credentials trong một số ngữ cảnh. | Không coi HTTP Basic là lý do tự động tắt CSRF. |
| SOAP dùng Bearer token **lưu trong cookie** | Cookie có thể tự đi theo request. | **Đánh giá CSRF như cookie-auth**, dù tên token là Bearer/JWT. |
| SOAP dùng Bearer token **trong Authorization header do backend gửi**, nhưng vẫn chấp nhận session cookie như fallback | Browser có thể dùng fallback cookie. | **Không miễn CSRF** cho tới khi tách/loại bỏ ambient auth tại SOAP endpoint. |
| SOAP operation chỉ đọc dữ liệu nhưng vẫn dùng POST | POST vẫn bị CSRF protection theo method mặc định. | Không tự bỏ kiểm tra vì method nghiệp vụ chỉ đọc; cần contract và security policy rõ. |
| SOAP service không tiếp xúc trình duyệt nhưng chạy chung app có UI form login | UI có CSRF risk riêng. | Ngoại lệ chính xác cho SOAP **không được lan sang UI**. |

**Quan trọng:** `SessionCreationPolicy.STATELESS` **không tự chứng minh CSRF không cần thiết**. Nó điều chỉnh cách Spring Security dùng/tạo session cho SecurityContext, không ngăn mọi cookie hoặc mọi cơ chế ambient authentication mà ứng dụng/gateway có thể chấp nhận. Một API có JWT **trong cookie** vẫn có thể chịu rủi ro CSRF dù được gọi là “stateless”.

### 3.2. SOAP XML/Content-Type không phải bằng chứng đủ để bỏ CSRF

Một số hệ thống lập luận rằng attacker không thể gửi XML với `Content-Type: text/xml` bằng HTML form thông thường nên không có CSRF. Đây là một yếu tố giảm khả năng khai thác trong cấu hình rất cụ thể, **không phải quyết định bảo mật tổng quát**:

- Browser có các giới hạn với cross-origin JavaScript và content types yêu cầu CORS preflight, nhưng hành vi phụ thuộc endpoint, CORS/gateway và request encoding.
- SOAP endpoint hoặc reverse proxy có thể chấp nhận **nhiều Content-Type** hoặc parse payload lỏng lẻo.
- Một số action có thể được thực hiện qua method/path khác hoặc legacy adapter.
- Cấu hình browser, proxies và SOAP framework có thể thay đổi khi nâng cấp.

Do đó, **không dựa duy nhất vào “SOAP POST dùng text/xml” để tắt CSRF**. Hãy yêu cầu một cơ chế authentication không bị browser tự mang từ một origin không tin cậy, và giữ mọi kiểm tra ở tầng SOAP/business theo contract.

### 3.3. CORS không phải CSRF protection

CORS chủ yếu giới hạn khả năng JavaScript trên trang khác origin gửi/đọc một số request/response; nhiều dạng form submission vẫn có thể **phát request** dù attacker không đọc response được. `Access-Control-Allow-Origin` được cấu hình chặt chẽ là tốt, nhưng **không thay CSRF token** nếu endpoint dựa vào session cookie.

Cũng không nên tự tin rằng CORS chặn mọi request chỉ vì browser không cho `fetch()` đọc body. Trong CSRF, attacker có thể chỉ cần **hành động được thực hiện**, không cần đọc kết quả.

### 3.4. SameSite cookies cũng không thay thiết kế tổng thể

Thuộc tính cookie `SameSite=Lax/Strict/None` làm giảm một số dạng cross-site cookie attachment; tuy nhiên còn browser compatibility, cross-site vs same-site semantics, subdomain trust, redirects và các luồng login. Kết hợp cookie attributes, Origin/Referer/Sec-Fetch-* checks (khi phù hợp), CSRF token và authorization để phòng vệ nhiều lớp.

Không đổi cookie `SameSite=None`/`Secure` chỉ để SOAP browser client vượt CSRF mà không phân tích rủi ro và thử nghiệm.

## 4. Nguyên tắc thiết kế ngoại lệ CSRF có phạm vi hẹp

Khi đã chứng minh SOAP endpoint **chỉ** dành cho client máy–máy với credential không bị trình duyệt tự đính kèm, hãy dùng một quy tắc “chỉ request này được bỏ CSRF” thay vì tắt tính năng toàn ứng dụng.

### 4.1. Một chính sách ngoại lệ cần trả lời đủ năm câu hỏi

1. **Method nào?** Chỉ `POST` hay mọi HTTP methods? Đối với SOAP-over-HTTP request-response, ngoại lệ thường nhắm đúng **POST**.
2. **Servlet URL nào?** `/ws`, `/ws/`, `/services/orders`, hay `/ws/orders.wsdl`? Lấy từ **servlet mapping + endpoint URL thực tế**, không suy từ tên WSDL.
3. **Ai được gọi?** Client chỉ được xác thực bằng Bearer/mTLS/WS-Security theo policy nào? Có bị nhận session cookie như fallback không?
4. **Hành động nào được phép?** HTTP authority, SOAP operation authorization, tenant và business permission; ngoại lệ CSRF không phải ngoại lệ authorization.
5. **Những gì phải giữ nguyên?** CSRF trên UI/admin/session routes, các HTTP methods khác, security headers và đường kiểm tra request bất hợp lệ.

Một ngoại lệ an toàn có dạng:

~~~text
EXCLUDE CSRF if:
    method = POST
    AND servletPath = "/ws"
    AND pathInfo ∈ {null, "/"}
    AND request được xử lý bởi machine-to-machine SOAP chain

STILL REQUIRE:
    authentication + authorization
    valid SOAP Envelope + XSD/WSDL contract
    WS-Security signature/token nếu policy yêu cầu
    TLS/mTLS/egress controls theo thiết kế
~~~

Chỉ có **hai điều kiện method và đường dẫn** là phần trực tiếp của RequestMatcher; xác thực, phân quyền và WS-Security vẫn phải được thực hiện bởi **các thành phần riêng**. Không cố nhét toàn bộ kiểm tra credential vào CSRF ignore matcher.

### 4.2. Tại sao không dùng ignore "/ws/**" vô điều kiện?

Ví dụ dễ gây mở rộng quyền ngoài ý muốn:

~~~java
// Phạm vi quá rộng nếu ứng dụng còn nhiều URL dưới /ws.
http.csrf(csrf -> csrf.ignoringRequestMatchers("/ws/**"));
~~~

Nhược điểm:

- Không ràng buộc method cụ thể. Nếu sau này có endpoint `POST /ws/admin/reset` hoặc `POST /ws/browser/settings`, nó có thể bị bỏ CSRF.
- Pattern có thể khớp cả endpoint khác hoặc không khớp đường SOAP dự kiến, tùy servlet mapping/matcher semantics.
- Code không giải thích **tại sao** SOAP POST được ngoại lệ và các authentication mechanisms được phép.
- Một người đổi servlet mappings sau này có thể làm phạm vi ignore thay đổi mà không được test.

**Thay vào đó, viết matcher chính xác và unit/integration-test rõ từng URL.** Với ứng dụng có nhiều filter chains, phạm vi chain và phạm vi CSRF exception là **hai tầng matching khác nhau**.

### 4.3. Không dùng Header/Content-Type dễ giả mạo làm bằng chứng duy nhất

Các quy tắc sau **không đủ** làm ranh giới bảo mật:

~~~text
if (Content-Type contains "text/xml") ignore CSRF
if (SOAPAction header exists) ignore CSRF
if (User-Agent equals "Java") ignore CSRF
if (X-Requested-With equals "XMLHttpRequest") ignore CSRF
if (request body starts with "<soap:Envelope>") ignore CSRF
~~~

HTTP headers như `SOAPAction`, `User-Agent` và `X-Requested-With` có thể bị client tự gửi; sự tồn tại của chúng **không chứng minh identity**. `Content-Type` có thể là điều kiện kiểm tra protocol đầu vào nhưng không thay authentication, authorization và threat model CSRF.

Cũng không yêu cầu `CsrfFilter` parse XML Body để tìm `SOAPAction` hoặc một phần tử nghiệp vụ: làm vậy có thể tiêu thụ input stream trước Spring-WS, tăng attack surface XXE/DoS và phá streaming/MTOM.

## 5. Một thiết kế Spring Security 6.x: SOAP chain tách với UI chain

Giả sử ứng dụng Spring Boot có:

~~~text
Servlet mapping:
    MessageDispatcherServlet  →  /ws/*

SOAP endpoint:
    POST /ws
    POST /ws/

WSDL:
    GET /ws/orders.wsdl

Web UI:
    GET/POST /account/**
    GET/POST /admin/**
    GET/POST /login
~~~

**Giả định bảo mật:** SOAP POST chỉ chấp nhận JWT Bearer do một client backend lấy từ nhà phát hành đáng tin; JWT **không** được đọc từ session cookie hoặc một fallback browser credential. UI dùng form login + session cookie. Các luồng SOAP vẫn có thể yêu cầu WS-Security Signature/mTLS nếu hợp đồng quy định.

### 5.1. Code mẫu hai SecurityFilterChain

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    private static final RequestMatcher WS_SERVLET = request ->
        "/ws".equals(request.getServletPath());

    private static final RequestMatcher SOAP_POST = request ->
        WS_SERVLET.matches(request)
        && "POST".equals(request.getMethod())
        && (request.getPathInfo() == null
            || "/".equals(request.getPathInfo()));

    private static final RequestMatcher ORDERS_WSDL_GET = request ->
        WS_SERVLET.matches(request)
        && "GET".equals(request.getMethod())
        && "/orders.wsdl".equals(request.getPathInfo());

    @Bean
    @Order(1)
    SecurityFilterChain soapChain(HttpSecurity http) throws Exception {
        http
            // Chỉ các request được servlet /ws/* xử lý.
            .securityMatcher(WS_SERVLET)
            .csrf(csrf -> csrf
                // Ngoại lệ ĐÚNG SOAP POST, không tắt CSRF toàn ứng dụng.
                .ignoringRequestMatchers(SOAP_POST))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(ORDERS_WSDL_GET).permitAll()
                .requestMatchers(SOAP_POST)
                    .hasAuthority("SCOPE_soap.invoke")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain uiChain(HttpSecurity http) throws Exception {
        http
            // Chain dự phòng cho UI và các đường còn lại.
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/public/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Mẫu này chỉ là kiến trúc tham chiếu**, không thể chạy độc lập nếu chưa đăng ký `MessageDispatcherServlet`, JWT decoder/issuer/JWK config, Spring Security OAuth2 Resource Server, JAXB/WSDL, SOAP endpoint mapping và business permissions. Một số imports và API có thể khác trong Spring Security 7.x; luôn đối chiếu dependency đang chạy.

**Cực kỳ quan trọng:** `getServletPath()`/`getPathInfo()` trong ví dụ được kiểm soát theo **servlet mapping `/ws/*`**. Nếu ứng dụng dùng `/services/*`, `/ws` exact mapping, default servlet, reverse proxy path rewrite hoặc app context path khác, hai giá trị có thể khác. Trước khi áp dụng, **xác nhận bằng test trên servlet container đang chạy**; không giả định request URI tuyệt đối, servlet path, context path và path info là một.

### 5.2. Vì sao phải đặt SOAP chain ở @Order(1)?

Spring Security có thể có **nhiều `SecurityFilterChain`**, và `FilterChainProxy` chọn **chain đầu tiên khớp request** theo thứ tự. Ví dụ:

~~~text
POST /ws
  └── WS_SERVLET matches → soapChain
        ├── CSRF ignore chỉ SOAP_POST
        ├── Bearer JWT authentication
        ├── yêu cầu SCOPE_soap.invoke
        └── MessageDispatcherServlet / SOAP handler

POST /account/change-email
  └── WS_SERVLET does not match → uiChain
        ├── CSRF vẫn yêu cầu token
        ├── session authentication
        └── UI handler
~~~

Nếu UI chain có matcher mặc định khớp tất cả nhưng được ưu tiên **trước** SOAP chain, request `/ws` có thể vào sai chain và nhận CSRF 403. Nếu **không có** catch-all chain phía sau, một số URL có thể hoàn toàn **không được bảo vệ bởi Spring Security**. Vì vậy phải xem **cả chain ordering và final fallback**.

### 5.3. Phân biệt securityMatcher và requestMatchers

| API trong ví dụ | Tác dụng | Hậu quả nếu hiểu sai |
| --- | --- | --- |
| `http.securityMatcher(WS_SERVLET)` | Quyết định **toàn bộ filter chain** áp dụng cho request nào. | Nếu không khớp, authn/authz/CSRF của SOAP chain **không chạy**. |
| `csrf.ignoringRequestMatchers(SOAP_POST)` | Bỏ **chỉ kiểm tra CSRF** cho request khớp; không bypass authentication. | Nếu quá rộng, các unsafe requests khác mất CSRF protection. |
| `authorizeHttpRequests.requestMatchers(SOAP_POST)` | Quy định **authority cần có** khi SOAP POST khớp. | Nếu matcher khác với CSRF matcher, request có thể bị chặn hoặc mở nhầm. |
| `anyRequest().denyAll()` của SOAP chain | Từ chối các URL/method khác đã lọt vào WS servlet chain. | Giúp không biến `GET /ws/other` thành public route. |
| `uiChain` catch-all | Bảo vệ các request còn lại, gồm session UI. | Thiếu chain này có thể để hở đường ngoài SOAP. |

Khi đọc code review, luôn hỏi **một request cụ thể rơi vào chain nào**, sau đó mới xét nó có được bỏ CSRF hay không.

### 5.4. WSDL có nhất thiết phải public?

**Không.** Ví dụ dùng `permitAll()` với `GET /ws/orders.wsdl` để minh họa mô hình một số đối tác tải contract công khai. Trong môi trường doanh nghiệp, WSDL có thể tiết lộ operation names, schema và cấu trúc dữ liệu; có thể cần hạn chế truy cập qua authentication, IP allowlist/VPN, API gateway hoặc chỉ phân phối WSDL ngoài runtime.

Nếu WSDL phải được bảo vệ, thay `permitAll()` bằng một điều kiện phù hợp, ví dụ scope riêng dành cho contract retrieval. Việc WSDL dùng GET và mặc định không cần CSRF **không đồng nghĩa mọi người đều có quyền xem WSDL**.

### 5.5. Ngoại lệ CSRF không bỏ qua SOAP authorization

`hasAuthority("SCOPE_soap.invoke")` chỉ là **coarse-grained route permission**; một người có scope này không tự được phép gọi mọi SOAP operation/tenant trên URL `/ws`.

Các kiểm tra còn cần:

- Authentication identity: JWT signature/issuer/audience/expiry hoặc mTLS/WS-Security identity theo profile.
- Authorization theo SOAP operation và business resource: ví dụ `CreateOrder` khác `CancelOrder`.
- Quyền tenant, subject-organization mapping, idempotency và replay protection.
- XML parser security/size limits, XSD validation, WS-Security signed parts nếu yêu cầu.
- Fault mapping và logging an toàn: lỗi phân quyền không nên tiết lộ dữ liệu nhạy cảm.

**Không dùng SOAPAction hoặc Body QName làm bằng chứng có quyền**; chúng hỗ trợ định tuyến, không thay identity/authorization.

## 6. Trường hợp chỉ có một filter chain: vẫn ngoại lệ hẹp

Nếu một ứng dụng không có UI và chỉ định nghĩa **một** `SecurityFilterChain`, có thể cấu hình một `RequestMatcher` chính xác:

~~~java
import org.springframework.security.web.util.matcher.RequestMatcher;

RequestMatcher soapPost = request ->
    "POST".equals(request.getMethod())
    && "/ws".equals(request.getServletPath())
    && (request.getPathInfo() == null
        || "/".equals(request.getPathInfo()));

http.csrf(csrf ->
    csrf.ignoringRequestMatchers(soapPost));
~~~

Đây chỉ là **trích đoạn ở bên trong một method có `HttpSecurity http`**, không phải cấu hình đầy đủ. **Vẫn cần** `authorizeHttpRequests`, authentication và default deny/fallback theo threat model.

Nếu sau này tích hợp UI session login vào cùng ứng dụng, quy tắc trên chỉ bỏ CSRF cho SOAP POST có path khớp, còn POST UI vẫn được bảo vệ. Tuy nhiên hãy đánh giá lại khả năng SOAP URL **chấp nhận credential cookie từ UI**; một matcher hẹp vẫn có thể không an toàn nếu chính SOAP POST cho phép session cookie ambient. Khi đó cần **tách authentication mechanisms/chain** hoặc giữ CSRF token cho SOAP.

### 6.1. Một ngoại lệ đủ hẹp về URL nhưng sai về threat model vẫn nguy hiểm

Hãy xem:

~~~text
POST /ws là endpoint duy nhất trong whitelist CSRF
SOAP POST cho phép session-cookie-auth của UI
Browser có thể gửi cookie trên cross-origin request
SOAP endpoint thực hiện thay đổi dữ liệu
~~~

**Rủi ro vẫn có thể tồn tại ở chính endpoint được ngoại lệ**. Phạm vi URL hẹp chỉ giới hạn diện tích ảnh hưởng; nó **không loại bỏ điều kiện tấn công**. Do đó, điều kiện tiên quyết của cách này là SOAP endpoint máy–máy **không dựa vào credential browser tự đính kèm**, hoặc có các bảo vệ tương đương được thiết kế/kiểm thử khác.

## 7. Khi SOAP được gọi từ trình duyệt: giữ CSRF token thay vì miễn trừ

Không phải SOAP client nào cũng là một process backend. Có hệ thống portal nội bộ/legacy có JavaScript hoặc thành phần browser gọi SOAP gateway cùng origin và sử dụng session cookie. Khi **trình duyệt là một client thực sự**, ngoại lệ CSRF cho SOAP POST có thể mở ra đúng loại rủi ro mà Spring Security đang bảo vệ.

### 7.1. Cơ chế token nên được giữ nguyên

Một luồng browser/session phù hợp:

~~~mermaid
sequenceDiagram
    participant B as Browser cùng origin
    participant S as Spring Security + SOAP service

    B->>S: GET /ui hoặc bootstrap có session
    S-->>B: CSRF token theo repository + request handler
    B->>B: Lưu token theo cơ chế ứng dụng đã chọn
    B->>S: POST /ws với session cookie + HTTP X-CSRF-TOKEN
    S->>S: So token theo session/repository
    S->>S: Authenticate + authorize
    S->>S: Dispatch SOAP XML / WSS4J / @Endpoint
    S-->>B: SOAP response hoặc SOAP Fault
~~~

Tên header cụ thể thường gặp là `X-CSRF-TOKEN` hoặc `X-XSRF-TOKEN` tùy `CsrfTokenRepository` và cấu hình Spring Security; **không phải một SOAP Header chuẩn WS-Security**. CsrfFilter xử lý **HTTP request header/parameter** theo cơ chế của nó, trước khi SOAP Header được giải mã/parse.

Nếu client thêm:

~~~xml
<soap:Header>
  <app:CsrfToken>...</app:CsrfToken>
</soap:Header>
~~~

thì Spring Security **không tự coi** phần tử tùy chỉnh này là CSRF token, trừ khi ứng dụng xây cơ chế giải quyết token riêng và bảo vệ ranh giới một cách chính xác. Tốt nhất giữ CSRF token ở tầng HTTP/browser mà Spring Security đã cung cấp.

### 7.2. Repository và request handler phải cùng thiết kế

Spring Security Servlet CSRF support sử dụng `CsrfTokenRepository` và `CsrfTokenRequestHandler` để cung cấp, đọc và xác minh token. Hai mô hình phổ biến:

| Trường hợp | Tùy chọn thường dùng | Lưu ý |
| --- | --- | --- |
| Server-rendered form + session | `HttpSessionCsrfTokenRepository` mặc định. | Spring Security tích hợp token qua request/form; POST gửi token đúng session. |
| SPA/browser JavaScript cần đọc token | `CookieCsrfTokenRepository` với request handler phù hợp, ví dụ hướng dẫn SPA của Spring Security. | `HttpOnly=false` để JS đọc token là **một quyết định bảo mật có đánh đổi**; cần bảo vệ XSS và tuân docs theo version. |
| SOAP machine-to-machine không có cookie session | Không nhất thiết cần token CSRF nếu threat model đạt điều kiện. | Vẫn phải có authentication/authorization và ngoại lệ chính xác. |

Khi chọn `CookieCsrfTokenRepository.withHttpOnlyFalse()`, JavaScript có thể đọc cookie CSRF token, nhưng không được hiểu việc đọc cookie là “mở an toàn”. Ở Spring Security 6.5 và 7.x, các thay đổi về deferred CSRF tokens, BREACH/XOR token masking và SPA request handler khiến việc copy một đoạn cấu hình cũ đôi khi gây **403 dù header đã chứa token**. Hãy dùng mẫu SPA đúng version trong tài liệu chính thức, kiểm tra cả logout/login và session regeneration.

**Không tắt CSRF chỉ vì SPA không tìm thấy token sau login.** Nên sửa đường bootstrap/token handler, cookie flags và lifecycle theo tài liệu; test CSRF token thực trong môi trường browser.

### 7.3. Client SOAP thuần Java gửi token HTTP ra sao?

Nếu hợp đồng yêu cầu SOAP client dùng **session-cookie authentication** (ví dụ legacy), client phải thực hiện một luồng giống browser được thỏa thuận với server:

1. Có **session** hợp lệ do server phát hành.
2. Lấy CSRF token qua một endpoint/bootstrap được server chủ động cung cấp và bảo vệ, không tự suy từ WSDL.
3. Giữ token cùng session cookie đúng lifecycle.
4. Gửi SOAP POST kèm **HTTP CSRF token header** đúng repository/handler, và cookie/session tương ứng.
5. Làm mới token khi session/login/CSRF strategy đổi; phân loại HTTP 403 token failure khác SOAP Fault.

`WebServiceTemplate` không tự biết một CSRF token được Spring MVC tạo cho browser ở server. Có thể thêm HTTP headers qua transport/callback tùy sender mà dự án dùng, nhưng **cách thực hiện khác nhau giữa HttpURLConnection, Apache HttpClient và JDK HttpClient**; không viết một `SoapActionCallback` rồi nghĩ nó tự gửi HTTP `X-CSRF-TOKEN`.

Để đơn giản hóa B2B SOAP, nếu có thể hãy đổi sang **credential máy–máy riêng** (client credentials JWT, mTLS/WS-Security) và tách URL/chain, thay vì bắt toàn bộ đối tác mô phỏng browser session. Tuy vậy không ép thay kiến trúc ngay nếu hệ thống legacy chưa có lộ trình; trong thời gian đó **giữ CSRF protection**.

### 7.4. Điều kiện để giữ CSRF trên SOAP có session

Một endpoint browser-facing với `POST /ws` có thể dùng cùng CSRF policy như UI: **không ignore SOAP POST**. Thêm kiểm thử:

~~~text
Browser đã login + valid session + SOAP POST + thiếu CSRF → 403
Browser đã login + valid session + SOAP POST + sai CSRF   → 403
Browser đã login + valid session + SOAP POST + đúng CSRF  → đến authz/SOAP
Anonymous + SOAP POST + forged CSRF                    → không được cấp quyền
SOAP payload hợp XSD nhưng thiếu CSRF                    → vẫn bị chặn
~~~

**CSRF token không thay authorization**: request có token đúng vẫn phải bị từ chối nếu người dùng thiếu quyền gọi SOAP operation.

## 8. Những cách cấu hình sai thường gặp

### 8.1. Tắt CSRF toàn bộ ứng dụng chỉ vì SOAP POST bị 403

~~~java
// Không khuyến nghị khi ứng dụng có UI/session endpoints.
http.csrf(csrf -> csrf.disable());
~~~

Hậu quả: POST đổi email/đổi mật khẩu/admin actions có thể mất CSRF protection, kể cả khi chỉ một SOAP route cần ngoại lệ. Nếu ứng dụng thực sự là **API máy–máy hoàn toàn độc lập**, tắt CSRF **trong chain đó** có thể hợp lý sau threat-model review, nhưng **không** được copy cấu hình sang chain/UI khác và tuyên bố mọi endpoint đều an toàn.

### 8.2. Bỏ qua toàn bộ Spring Security filter chain

~~~java
// Nguy hiểm: KHÔNG dùng để sửa CSRF SOAP.
web.ignoring().requestMatchers("/ws/**");
~~~

`WebSecurityCustomizer#ignoring` (hoặc cơ chế bỏ qua request của FilterChainProxy) có thể khiến **mọi Spring Security filters** không bảo vệ đường dẫn đó, không chỉ `CsrfFilter`. Điều này rất khác với:

~~~java
csrf.ignoringRequestMatchers(soapPost);
~~~

Cách thứ hai giữ authentication, authorization, security filters và các controls còn lại của chain, chỉ bỏ **một kiểm tra CSRF** cho request khớp. Trong nhiều phiên bản, cú pháp đăng ký `WebSecurityCustomizer` khác nhau; đoạn trên chỉ nhằm **chỉ ra anti-pattern**, không phải một chương trình hoàn chỉnh.

### 8.3. Dùng permitAll() và tưởng đã miễn CSRF

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/ws/**").permitAll());
~~~

`permitAll()` là **quy tắc authorization**, không tắt `CsrfFilter`. Request POST được phép anonymous về mặt authorization **vẫn có thể bị CSRF 403** nếu thiếu token. Ngược lại, nếu vừa permitAll vừa bỏ CSRF cho một SOAP endpoint có side effect, ứng dụng có thể bỏ cả hai lớp kiểm soát.

**Không dùng `permitAll()` để xử lý 403** nếu 403 đến từ CSRF hoặc người gọi thiếu quyền. Hãy xác định đúng filter/exception trước.

### 8.4. Gắn ignore vào sai filter chain

Giả sử code có:

~~~text
@Order(1) uiChain:  anyRequest()
@Order(2) soapChain: securityMatcher("/ws/**")
~~~

Vì chain thứ nhất khớp mọi request, `soapChain` **không bao giờ được chọn**. Thay đổi `csrf.ignoringRequestMatchers` trong SOAP chain sẽ không có tác dụng. Xem `FilterChainProxy` và thứ tự `@Order`, rồi test request thực sự vào chain nào.

### 8.5. Bỏ CSRF theo một Header có thể tự đặt

~~~java
csrf.ignoringRequestMatchers(
    request -> "SOAP".equals(request.getHeader("X-Client-Type")));
~~~

Header `X-Client-Type` không chứng minh caller đáng tin, và có thể được gửi từ nhiều clients; nếu endpoint nhận cookie credentials hoặc CORS bị cấu hình sai, quy tắc này có thể bỏ CSRF cho request không mong muốn. Nếu muốn phân tách SOAP và UI, dùng **endpoint URL/path + method + authentication mechanism**, không dùng một header tự khai báo làm căn cứ duy nhất.

### 8.6. Chỉ dùng stateless() rồi tin rằng CSRF đã biến mất

~~~java
http.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
~~~

Thuộc tính này **không disable CsrfFilter**. Nó cũng không tự loại bỏ mọi cookie ambient mà upstream hoặc custom authentication filter chấp nhận. Một người dùng có thể vẫn được xác thực bằng HTTP Basic/cookie nếu các filter khác được bật.

### 8.7. Coi HTTP 403 là SOAP Fault và sửa sai tầng

Trong một số SOAP clients, lỗi 403 được wrapper thành transport exception. Nếu kỹ sư chỉ tìm lỗi XSD, `@PayloadRoot` hoặc WSS4J certificate, sẽ không sửa được vì request **chưa tới SOAP dispatcher**.

Giải pháp: xem HTTP status và response content, filter-chain trace có kiểm soát, CSRF logs và matched servlet path; chỉ sau khi đi qua filter chain mới kiểm tra SOAP/Security.

## 9. Tích hợp với WS-Security, mTLS và authorization theo operation

CSRF là **một lớp kiểm soát HTTP/browser**, còn SOAP B2B thường có WS-Security, TLS và permission riêng.

### 9.1. Chuỗi kiểm soát máy–máy đề xuất

~~~mermaid
flowchart TD
    A["Partner POST SOAP"] --> B["HTTPS / mTLS (nếu yêu cầu)"]
    B --> C["Spring Security FilterChain"]
    C --> D["Bearer JWT hoặc cơ chế identity máy–máy"]
    D --> E["Scope/role cho endpoint SOAP"]
    E --> F["CSRF exemption: đúng POST /ws"]
    F --> G["SOAP MessageDispatcherServlet"]
    G --> H["WSS4J Signature, Timestamp, Replay checks"]
    H --> I["XSD validation + JAXB"]
    I --> J["Authorization operation/tenant + business"]
    J --> K["Response/Fault + audit"]
~~~

Đây là mô hình trách nhiệm, không phải thứ tự filter/interceptor chính xác của mọi Spring-WS deployment. Khi WS-Security signature là **cơ chế xác thực chính**, có thể không có HTTP Bearer JWT; tuy nhiên cần một cách chắc chắn để bảo đảm mọi SOAP operation đi qua **WSS4J verification và authorization trước side effect**. Hệ thống có gateway có thể chuyển thông tin identity vào HTTP headers đã ký/được tin cậy, nhưng phải phòng chống header spoofing và kiểm tra trust boundary.

### 9.2. WS-Security token không phải CSRF token

| Security artifact | Tầng | Bảo vệ gì? |
| --- | --- | --- |
| `X-CSRF-TOKEN`/`X-XSRF-TOKEN` | HTTP Servlet/Web security. | Ý định/nguồn request khi credential do browser tự gửi. |
| `Authorization: Bearer ...` | HTTP Authentication. | Identity/scope của gọi máy–máy nếu token được validate đúng. |
| mTLS client certificate | TLS handshake. | Identity của TLS peer khi đã trust và map quyền. |
| `wsse:UsernameToken` | SOAP Header. | Một phần SOAP authentication; cần bảo vệ transport, password policy, nonce/timestamp và replay. |
| `ds:Signature` | SOAP/WS-Security. | Tính toàn vẹn + khả năng xác minh signer cho các parts đã ký. |
| `wsu:Timestamp` | SOAP/WS-Security. | Giới hạn thời gian hiệu lực, góp phần chống replay theo policy. |
| `wsa:MessageID` | WS-Addressing. | Định danh message/correlation, không phải authorization hoặc CSRF token. |

Một SOAP message có `wsse:Security` không khiến `CsrfFilter` tự động bỏ qua HTTP POST. Nếu endpoint loại trừ CSRF, phải chứng minh **một kiểm tra riêng thực sự xác thực và phân quyền** trước khi nghiệp vụ chạy. Đặc biệt, chỉ có header `wsse:Security` xuất hiện không chứng minh chữ ký/token được server xác minh.

### 9.3. Cookie/session không nên là authentication fallback của SOAP chain

Khi triển khai cùng UI, có thể vô tình cho SOAP chain chấp nhận session cookie vì chia sẻ authentication configuration hoặc custom filter:

~~~text
SOAP POST with Authorization: Bearer → expected machine identity
SOAP POST with SESSION cookie       → unexpected browser identity
SOAP POST without both              → should be unauthenticated
~~~

Một ngoại lệ CSRF chỉ hợp lý nếu cấu hình loại bỏ/khống chế những đường browser ambient credentials không chủ đích. **Test request có session cookie nhưng thiếu Bearer** phải không nhận quyền SOAP máy–máy. Tương tự nếu client dùng mTLS, xác minh TLS identity chứ không auto-fallback vào user session.

### 9.4. Authorization theo operation vẫn cần kiểm tra bên trong SOAP

Vì nhiều operations chia sẻ cùng endpoint URL, route-level `hasAuthority("SCOPE_soap.invoke")` thường quá rộng để quyết định mọi quyền.

Ví dụ:

~~~text
CreateOrderRequest → phải có quyền ORDER_CREATE của tenant X
CancelOrderRequest → phải có quyền ORDER_CANCEL của tenant X
GetOrderRequest    → phải có quyền ORDER_VIEW và sở hữu/được chia sẻ
~~~

Các kiểm tra đó có thể nằm ở service layer hoặc method security dùng `@PreAuthorize`/`@EnableMethodSecurity` khi kết nối đúng Authentication/SecurityContext. Với WSS4J identity, việc chuyển principal vào Spring SecurityContext phải được thiết kế và kiểm thử; **không tự giả định mỗi SOAP Signature sẽ sinh một Authentication đã được map quyền**.

### 9.5. CSRF exception không giảm yêu cầu XML và replay protection

Vì SOAP POST không yêu cầu CSRF token **không có nghĩa** ta bỏ:

- Secure XML parser: chặn external entities/DTD/XXE theo policy.
- XSD validation từ schema đáng tin, không tin `xsi:schemaLocation` do client cung cấp.
- WS-Security signature, timestamp, nonce/replay controls nếu yêu cầu.
- Rate limiting, request size/MTOM attachment limits và timeout.
- Idempotency cho operation có side effect (đặc biệt khi HTTP timeout).
- TLS trust/cert rotation và secret management.

**CSRF, replay và idempotency là ba vấn đề riêng**: CSRF nói về browser ambient credential; replay nói về việc gửi lại một message/credential; idempotency nói về hiệu ứng nghiệp vụ khi request được xử lý lại. Không dùng một biện pháp làm lời giải cho cả ba.

## 10. Ma trận kiểm thử bắt buộc: kiểm tra cả allow và deny

Một cấu hình bảo mật đúng không chỉ là “SOAP POST có JWT trả `200`”. Phải kiểm thử **request cần hoạt động** và **request bắt buộc bị từ chối**. Việc loại trừ CSRF mà không có negative tests rất dễ mở rộng ngoài phạm vi khi servlet mappings hoặc security chains thay đổi.

### 10.1. Trường hợp minh họa /ws/* với JWT và UI session

| Ca | HTTP request | Credential/CSRF | Kết quả mong đợi |
| --- | --- | --- | --- |
| 1 | `POST /ws` | JWT hợp lệ, `SCOPE_soap.invoke`, **không CSRF** | Vượt qua CSRF/authz để đến SOAP. |
| 2 | `POST /ws/` | JWT hợp lệ, có scope, **không CSRF** | Nếu URL đó được SOAP servlet chấp nhận, vượt qua filters. |
| 3 | `POST /ws` | **Không JWT**, không CSRF | Bị từ chối bởi authentication; **không** vì CSRF. |
| 4 | `POST /ws` | JWT hết hạn/sai chữ ký, không CSRF | Không được xử lý nghiệp vụ. |
| 5 | `POST /ws` | JWT hợp lệ nhưng **thiếu scope** | `403` authorization; không vào SOAP. |
| 6 | `POST /ws` | Chỉ có **UI session cookie**, không JWT | Không được coi là machine identity. |
| 7 | `GET /ws/orders.wsdl` | Không JWT | Theo ví dụ `permitAll`, có thể tải WSDL; cần test contract access policy. |
| 8 | `POST /ws/orders.wsdl` | JWT hợp lệ, **không CSRF** | **Không** được áp dụng ngoại lệ SOAP POST; bị chặn bởi CSRF/authz. |
| 9 | `POST /ws/admin/reset` | JWT hợp lệ, không CSRF | Không được coi là SOAP endpoint hợp lệ; bị từ chối. |
| 10 | `PUT /ws` | JWT hợp lệ, không CSRF | Không được áp dụng ngoại lệ CSRF. |
| 11 | `DELETE /ws` | JWT hợp lệ, không CSRF | Không được áp dụng ngoại lệ CSRF. |
| 12 | `POST /account/change-email` | Session user, **không CSRF** | `403` từ CSRF của UI chain. |
| 13 | `POST /account/change-email` | Session user, **CSRF đúng** | Qua CSRF; authorization/business vẫn quyết định. |
| 14 | `POST /admin/action` | Session user thiếu admin role, CSRF đúng | `403` authorization. |
| 15 | `POST /admin/action` | Có admin role nhưng CSRF sai | `403` CSRF. |
| 16 | `POST /ws` | JWT hợp lệ, SOAP Envelope XML sai | HTTP chain có thể cho qua; SOAP parser/validation từ chối theo contract. |
| 17 | `POST /ws` | JWT hợp lệ, WS-Security signature sai | HTTP auth pass, nhưng WSS4J **không** cho nghiệp vụ chạy. |
| 18 | `POST /ws` | JWT hợp lệ, payload có side effect nhưng retry | Chỉ thực thi theo idempotency policy, không tạo duplicate. |

**Lưu ý:** status HTTP cụ thể có thể khác theo `AuthenticationEntryPoint`, `AccessDeniedHandler`, gateway và Spring Security version. Với một request bị CSRF chặn, status mặc định thường là **403**. Với resource-server unauthenticated request, thường là **401**. Test phải ghi lại behavior đã thống nhất, không mã hóa mọi lỗi thành HTTP 500 hoặc SOAP Fault.

### 10.2. Unit test RequestMatcher theo servlet path và method

Đây là cách kiểm chứng phần rủi ro nhất của ngoại lệ: **đúng request nào được miễn CSRF**. Một matcher đơn giản cho servlet mapping `/ws/*`:

~~~java
import org.springframework.security.web.util.matcher.RequestMatcher;

public final class SoapMatchers {

    private SoapMatchers() {}

    public static final RequestMatcher SOAP_POST = request ->
        "POST".equals(request.getMethod())
        && "/ws".equals(request.getServletPath())
        && (request.getPathInfo() == null
            || "/".equals(request.getPathInfo()));
}
~~~

Kiểm thử matcher bằng Spring Test và JUnit 5:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SoapMatchersTest {

    private MockHttpServletRequest request(
            String method, String servletPath, String pathInfo) {

        MockHttpServletRequest req =
            new MockHttpServletRequest(method, servletPath);
        req.setServletPath(servletPath);
        req.setPathInfo(pathInfo);
        return req;
    }

    @Test
    void matchesOnlyExactSoapPost() {
        assertTrue(SoapMatchers.SOAP_POST.matches(
            request("POST", "/ws", null)));
        assertTrue(SoapMatchers.SOAP_POST.matches(
            request("POST", "/ws", "/")));

        assertFalse(SoapMatchers.SOAP_POST.matches(
            request("GET", "/ws", null)));
        assertFalse(SoapMatchers.SOAP_POST.matches(
            request("PUT", "/ws", null)));
        assertFalse(SoapMatchers.SOAP_POST.matches(
            request("POST", "/ws", "/orders.wsdl")));
        assertFalse(SoapMatchers.SOAP_POST.matches(
            request("POST", "/ws", "/admin/reset")));
        assertFalse(SoapMatchers.SOAP_POST.matches(
            request("POST", "/account", "/change-email")));
    }
}
~~~

**Giới hạn:** `MockHttpServletRequest` được tạo thủ công giúp kiểm tra boolean matcher nhưng **không chứng minh servlet container production thực sự tính `servletPath`/`pathInfo` giống fixture**. Kết hợp thêm integration test qua servlet mapping thật, app context path, reverse proxy, encoded paths/trailing slash khi có. Với Spring Boot test, kiểm tra request filters và servlet dispatch trong môi trường đại diện.

### 10.3. Security integration test phải kiểm tra toàn chain

Các công cụ:

- `spring-security-test`: `SecurityMockMvcRequestPostProcessors.csrf()`, `user()`, `jwt()` để mô phỏng điều kiện authentication/CSRF.
- `MockMvc` hoặc embedded Servlet container để kiểm tra SecurityFilterChain + SOAP servlet mapping.
- Spring-WS `MockWebServiceClient`/`MockWebServiceServer` cho SOAP Body, Fault và WSS4J client/server logic.
- Test HTTP thật qua gateway cho TLS/mTLS, CORS/Origin policy, Bearer JWT validation và đường đi end-to-end.

Ví dụ kiểm tra UI session vẫn được CSRF bảo vệ:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Trong một test đã có MockMvc và Spring Security filter chain:
mockMvc.perform(
    post("/account/change-email")
        .with(user("alice")))
    .andExpect(status().isForbidden());
~~~

Đây là test ranh giới CSRF (POST thiếu token → 403), không yêu cầu `/account/change-email` đã có controller thực sự khi filter chạy trước handler; nhưng test integration đầy đủ còn phải xác nhận **POST có CSRF đúng đi qua filter** và chịu kiểm tra quyền/logic của controller.

Đối với SOAP machine-to-machine, test có JWT và không CSRF phải chứng minh request **không bị từ chối bởi `CsrfFilter`**, đồng thời kiểm tra XML/WS-Security contract bằng test riêng. Nếu dùng helper `jwt()` của `spring-security-test`, nó có thể **bỏ qua cryptographic JWT decoder**, vì vậy phải có test HTTP integration với JWT hợp lệ/sai chữ ký/hết hạn qua cấu hình decoder thật.

### 10.4. Test với dữ liệu browser credential ambient

Một bộ test đáng có khi ứng dụng chạy chung UI và SOAP:

~~~text
1. POST /ws + only UI session cookie → không được xác thực vào SOAP
2. POST /ws + valid Bearer token      → xác thực machine identity
3. POST /ws + expired Bearer token    → từ chối
4. POST /ui/change + session no CSRF → 403
5. POST /ui/change + correct CSRF    → qua CSRF, vẫn cần quyền
6. POST /ws/orders.wsdl              → không được xem như SOAP POST
7. POST /ws/unknown                  → không được hưởng CSRF exemption
8. OPTIONS /ws                       → CORS/preflight policy, không mở auth tùy tiện
~~~

Kiểm thử ở đây không chỉ assert HTTP code: cần kiểm tra **không phát sinh side effect** ở DB/queue và không tạo response SOAP mang thông tin nhạy cảm đối với request bị từ chối. Trường hợp authentication bị bỏ qua tại test utility dễ che lấp rủi ro của deployment thật.

### 10.5. Test qua reverse proxy và context path

Một ứng dụng có context path `/orders` và servlet mapping `/ws/*` có thể nhận:

~~~text
Public URL:  https://api.example.test/orders/ws
Internal:    http://orders-service:8080/orders/ws
ServletPath: /ws
ContextPath: /orders
PathInfo:    null
~~~

Tất cả chỉ là ví dụ; reverse proxy có thể strip/rewrite prefix theo nhiều cách. Một matcher tự so:

~~~java
request.getRequestURI().equals("/ws")
~~~

có thể **không khớp** khi app có context path. Matcher dựa `servletPath/pathInfo` cũng cần test thật vì mappings có thể khác. Đặc biệt chú ý URL encoding/double slashes/trailing slashes; đừng tạo logic normalize tùy ý bỏ qua bảo vệ khi gặp path lạ.

**Hãy kiểm chứng dưới đúng container + reverse proxy**, không chỉ dựa vào unit test Java.

## 11. Kiểm thử HTTP thực tế và phân biệt 401, 403, SOAP Fault

### 11.1. SOAP 1.1 request mẫu

Trong môi trường test, giả sử WSDL công bố SOAP endpoint `https://orders.example.test/ws` và operation `CreateOrder` dùng SOAP 1.1:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
  <soap:Body>
    <ord:CreateOrderRequest>
      <ord:clientOrderId>WEB-20261127-009</ord:clientOrderId>
      <ord:amount>1200000.00</ord:amount>
    </ord:CreateOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

Lưu vào `create-order.xml`. Gửi bằng một client HTTP đã được phép dùng trong test:

~~~bash
curl --include --request POST \
  --header 'Content-Type: text/xml; charset=utf-8' \
  --header 'SOAPAction: "urn:example:orders:v1/CreateOrder"' \
  --header 'Authorization: Bearer REPLACE_WITH_VALID_TEST_TOKEN' \
  --data-binary '@create-order.xml' \
  'https://orders.example.test/ws'
~~~

Token được dùng ở đây là **placeholder**, không phải credential. Đừng ghi Bearer token thật vào shell history, log hoặc tài liệu; trong test CI dùng cơ chế secret injection được duyệt. `SOAPAction` và địa chỉ phải lấy từ WSDL thực tế. Lệnh curl này **không tự kiểm tra** CSRF token: nó giúp thử endpoint machine-to-machine giả định có ngoại lệ CSRF.

Nếu gửi request **không có Bearer**:

~~~bash
curl --include --request POST \
  --header 'Content-Type: text/xml; charset=utf-8' \
  --data-binary '@create-order.xml' \
  'https://orders.example.test/ws'
~~~

thì SOAP chain mẫu có thể trả `401` từ resource server. Ngược lại, với JWT hợp lệ và thiếu CSRF, request **được phép qua CSRF filter** nhưng vẫn có thể tạo SOAP Fault nếu XML/WSS4J/business không hợp lệ. **Không đồng nhất “không nhận 403 CSRF” với “SOAP operation thành công”.**

### 11.2. Phân biệt response theo tầng

~~~text
HTTP 401 / 403, Content-Type: application/json hoặc text/html
  → có thể là authentication/authorization/CSRF/gateway;
     chưa chắc có SOAP Envelope.

HTTP 500, Content-Type: text/xml, Body có soap:Fault
  → SOAP 1.1 Fault; đọc faultcode/faultstring/detail.

HTTP 200, Body có <CreateOrderResponse> trong SOAP Envelope
  → SOAP transport thành công; vẫn phải đọc business status.

Không có HTTP response, SSLHandshakeException
  → TLS/transport; không phải CSRF hay SOAP Fault.
~~~

Ở SOAP 1.2, media type thường là `application/soap+xml` và Fault structure dùng `Code/Reason/Detail`; đừng áp dụng máy móc quy tắc SOAP 1.1 HTTP status cho mọi binding. Cũng cần phân biệt 403 từ API gateway/WAF với 403 do Spring `CsrfFilter`: xem request ID, filter chain logs và response metadata đã được phép.

### 11.3. Khi nào không cần gọi web search hay kiểm tra docs mới?

Trong dự án đã pin version và có đủ test, chỉ cần đối chiếu **Javadoc của version đó** và dependency tree. Tài liệu `current` có thể khác `Spring Security 6.0/6.5/7.x` về matcher selection, CSRF token handler hoặc Spring MVC integration. Không copy ví dụ từ một version mới mà không xác nhận version đang chạy.

## 12. Troubleshooting: vì sao SOAP POST vẫn 403 dù đã cấu hình ignore?

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| WSDL GET 200, SOAP POST 403 | Mặc định GET không cần CSRF, POST cần token; hoặc POST thiếu quyền. | Xem `CsrfFilter`, `AuthenticationEntryPoint`, matched chain và status/body. |
| Đã có `ignoringRequestMatchers` nhưng vẫn bị CSRF 403 | Matcher không khớp `servletPath/pathInfo`, request vào chain khác hoặc path bị proxy rewrite. | Log an toàn method/servletPath/pathInfo, inspect filter chain order. |
| Bỏ CSRF rồi thấy HTTP 401 | CSRF đã không còn chặn, nhưng client thiếu/sai token Bearer. | JWT issuer/audience/signature/expiry, header, resource server configuration. |
| Bỏ CSRF rồi thấy HTTP 403 | Authorization thiếu scope/role, method security, gateway policy hoặc custom filter. | Xem `AccessDeniedHandler` và authority/principal mapping, không tắt thêm filter tùy tiện. |
| SOAP POST đến `/ws/` hoạt động, `/ws` không | Servlet mapping hoặc path normalization khác. | Test cả trailing slash, URL WSDL, container behavior và đúng endpoint contract. |
| GET `/ws/orders.wsdl` nhận 401/403 | WSDL không được `permitAll`, thuộc SOAP chain khác, gateway yêu cầu auth. | Xác định có chủ đích public WSDL hay không; authz policy. |
| Session UI POST vẫn bị 403 sau khi thêm csrf() | Browser chưa gửi token, token handler/repository mismatch, session/login vừa rotate. | Theo tài liệu SPA/session đúng version; kiểm tra token header/cookie lifecycle. |
| Browser UI POST **không** còn 403 khi thiếu token | Có thể đã disable CSRF toàn app, ngoại lệ quá rộng hoặc request vào chain khác. | Negative test UI/session; kiểm tra `csrf.disable()` và `web.ignoring()`. |
| Request với cookie UI nhưng không JWT vẫn gọi được SOAP | SOAP chain cho phép ambient auth fallback hoặc matcher/chains chồng nhau. | Tách identity mechanisms, kiểm tra SecurityContext, session filter, gateway headers. |
| SOAP WSS4J signature sai nhưng HTTP auth pass | WS-Security và Spring Security HTTP auth là hai tầng khác nhau. | SOAP security interceptor/actions/cert/trust, xác minh không vào nghiệp vụ. |
| HTTP status 403 là HTML/JSON, không phải SOAP XML | Bị chặn trước dispatcher hoặc bởi gateway. | Content-Type, response body đã lọc, request ID, Servlet filter. |
| SOAP Fault Sender/Client 500 | SOAP message đã được parse, có thể XML/WSS4J/endpoint error. | SOAP Fault code, detail, WSDL/XSD, security policy. |
| SOAP 1.2 Content-Type `application/soap+xml` nhận 415 | SOAP version/binding mismatch trước hoặc sau filters. | Message factory/WSDL, HTTP Content-Type, không nhầm với CSRF. |
| `@Endpoint` không hề được gọi | CSRF, auth, route, XML parser hoặc SOAP mapping từ chối trước endpoint. | Đi theo từng tầng từ FilterChainProxy đến MessageDispatcherServlet. |
| Backend gọi đúng nhưng browser cũng có thể POST | Endpoint mở tới browser, CORS/cookie/mTLS environment có thể tạo risk. | Threat model browser credentials, SameSite, Origin, strict content type, security chain. |
| Test MockWebServiceClient pass, HTTP integration vẫn 403 | Mock Spring-WS không nhất thiết chạy `springSecurityFilterChain` và proxy thật. | MockMvc with filters/embedded HTTP container/network tests. |
| Sau nâng cấp Spring Security, matcher hoạt động khác | RequestMatcher selection, servlet mapping hoặc URL normalization thay đổi. | Javadoc chính xác version, kiểm tra servletPath/pathInfo và negative tests. |

### 12.1. Phân biệt MissingCsrfTokenException và InvalidCsrfTokenException

Spring Security có thể dùng `MissingCsrfTokenException` khi không nhận được token cần thiết và `InvalidCsrfTokenException` khi token không hợp lệ. Cách hiển thị ra client có thể chỉ là HTTP 403.

**Không trả stack trace hoặc token value cho đối tác trong response.** Trong log được phân quyền, chỉ nên ghi metadata như:

~~~text
event=HTTP_REQUEST_DENIED
layer=SPRING_SECURITY
reason=CSRF_MISSING
method=POST
servletPath=/account
pathInfo=/change-email
requestId=req-73a
principalType=SESSION_USER
status=403
~~~

Đây là log **minh họa**, không phải output mặc định. Tránh log raw JWT, session cookie, CSRF token, SOAP Body, WS-Security UsernameToken, client private key hay đầy đủ headers chứa bí mật.

### 12.2. Khi nào dùng security tracing?

Trong môi trường test/staging, cấu hình logger cho Spring Security có thể giúp xác định filter chain được chọn và nguyên nhân từ chối. Tuy nhiên DEBUG/TRACE có thể tạo log khối lượng lớn và chứa metadata nhạy cảm; không bật vô điều kiện trên production.

Quy trình gợi ý:

1. Tái hiện bằng **request được phép và request bị từ chối** trong test.
2. Kiểm tra request method, public URI, contextPath, servletPath, pathInfo.
3. Xác định `SecurityFilterChain` được chọn và thứ tự của chúng.
4. Xác định 403 từ `CsrfFilter`, authorization, gateway hay WS-Security.
5. Kiểm tra token/credential **không log giá trị thực**.
6. Nếu ngoại lệ không khớp, sửa matcher nhỏ nhất có thể.
7. Chạy lại negative tests UI/WS endpoints và test thật qua servlet/proxy.
8. Xác nhận SOAP request đã đến dispatcher và operation đúng business authorization.

### 12.3. Sửa 403 đúng tầng

~~~mermaid
flowchart TD
    A["SOAP POST nhận lỗi"] --> B{"Có HTTP response?"}
    B -- "Không" --> C["TLS/DNS/network/sender: không phải CSRF"]
    B -- "Có" --> D{"HTTP status 403?"}
    D -- "Không" --> E["Xem status và SOAP response/Fault theo tầng"]
    D -- "Có" --> F{"CsrfFilter từ chối?"}
    F -- "Có" --> G{"Client là browser ambient-auth?"}
    G -- "Có" --> H["Giữ CSRF, cấp token đúng luồng"]
    G -- "Không; đã kiểm chứng M2M" --> I["Hẹp method + URL + chain; giữ authn/authz"]
    F -- "Không" --> J["Authorization/gateway/custom filters/WS-Security"]
    H --> K["Chạy positive + negative tests"]
    I --> K
    J --> K
~~~

**Không đặt `csrf.disable()` làm bước đầu tiên của troubleshooting.** Hãy xác định loại client và nguồn lỗi rồi mới thay cấu hình.

## 13. Tình huống thực hành có đáp án

### Tình huống A — SOAP client Java bị 403 nhưng tải WSDL bình thường

Client `WebServiceTemplate` lấy WSDL qua `GET /ws/orders.wsdl` được, nhưng gửi `POST /ws` với SOAP Body hợp lệ lại nhận 403. Backend sử dụng machine bearer JWT.

**Đáp án:** trước tiên xác minh 403 do `CsrfFilter` chứ không phải thiếu scope hoặc gateway. Nếu SOAP chain thực sự chỉ nhận Bearer do backend chủ động gửi, không dùng cookie/session fallback, có thể áp `csrf.ignoringRequestMatchers(soapPost)` cho **đúng POST endpoint**. Vẫn yêu cầu JWT và scope, test WSS4J/XSD sau khi qua HTTP filters.

### Tình huống B — Developer tắt CSRF toàn app

Ứng dụng vừa chạy SOAP service `/ws`, vừa có trang admin dùng `JSESSIONID`. Để sửa 403 SOAP, developer dùng `http.csrf(csrf -> csrf.disable())` trên chain duy nhất.

**Đáp án:** thay bằng một ngoại lệ hẹp chỉ cho SOAP POST máy–máy **sau khi xác minh SOAP không chấp nhận UI session credentials**, hoặc tách SOAP/UI chains. UI phải giữ CSRF; kiểm tra `POST /admin/action` khi có session đúng nhưng không CSRF vẫn trả 403.

### Tình huống C — Có Bearer JWT nhưng vẫn nhận session cookie

Ứng dụng quảng cáo SOAP là stateless REST/SOAP API, nhưng custom authentication filter vẫn chấp nhận `JSESSIONID` làm identity nếu thiếu Bearer header.

**Đáp án:** gọi endpoint này “stateless” **không giải quyết ambient credential**. Nếu muốn bỏ CSRF, phải tách chấp nhận credential: SOAP chỉ nhận machine credential theo policy, không tự fallback sang UI session. Nếu vẫn cho browser cookie auth, giữ CSRF token và các browser protections phù hợp.

### Tình huống D — Bỏ CSRF bằng Header SOAPAction

Để không ảnh hưởng UI, code ignore mọi request có HTTP `SOAPAction` header. Một form/client không tin cậy có thể tạo request với header đó.

**Đáp án:** không dựa vào một header có thể tự khai báo làm ranh giới bảo mật. Dùng **servlet path + HTTP method + security chain**, và không quên kiểm tra credentials/authorization. SOAPAction phục vụ routing/binding, không phải chứng minh authentication.

### Tình huống E — SOAP POST thiếu JWT nhận 401 sau khi sửa CSRF

Trước khi đổi config, request thiếu cả Bearer và CSRF nhận 403. Sau khi ngoại lệ CSRF đúng, nó nhận 401.

**Đáp án:** Đây **có thể là dấu hiệu đúng**: request đã không còn bị CSRF chặn, nhưng authentication JWT vẫn hoạt động và từ chối client vô danh. Không cần thay thành `permitAll()` chỉ để client nhận 200. Kiểm tra người gọi cung cấp JWT hợp lệ.

### Tình huống F — WSDL bị lộ

Sau khi triển khai, `GET /ws/orders.wsdl` trả công khai, trong khi công ty yêu cầu hợp đồng chỉ dành cho đối tác.

**Đáp án:** CSRF không liên quan trực tiếp vì GET thông thường không cần token. Phải dùng **authorization/network exposure policy** cho WSDL. Đổi `permitAll()` thành scope/allowlist thích hợp; có thể phân phối WSDL tĩnh qua kênh đã xác thực. Không dùng việc bật CSRF trên GET để giải quyết bài toán quyền đọc WSDL.

### Tình huống G — Browser JavaScript phải gọi SOAP dùng session

Một portal nội bộ gọi SOAP POST qua JavaScript với session cookie. Team muốn miễn CSRF vì request là XML và Browser CORS đang bật.

**Đáp án:** **Giữ CSRF** và xây luồng token đúng `CsrfTokenRepository`/`CsrfTokenRequestHandler` theo Spring Security version. SameSite/CORS có vai trò riêng nhưng không thay CSRF token. Nếu muốn chuyển thành M2M, cần tách origin/credential/endpoint theo thiết kế mới, không đổi mỗi Content-Type.

### Tình huống H — Request thiếu CSRF không vào endpoint, dev sửa WSS4J certificate

Ở production, SOAP client báo 403. Developer xoay certificate WSS4J và sửa XML signature nhưng vấn đề vẫn giữ nguyên.

**Đáp án:** kiểm tra HTTP response Content-Type và Spring Security filter chain trước. Nếu `CsrfFilter` đã từ chối, WSS4J interceptor **chưa được gọi**. Chỉ debug certificate khi đã xác định failure thuộc WS-Security hoặc TLS; việc xoay khóa không giải quyết CSRF.

### Tình huống I — Ignore matcher đúng path nhưng trên sai chain

Ứng dụng có `@Order(1) uiChain` matcher mặc định tất cả request, rồi `@Order(2) soapChain` matcher `/ws/**`. Dù `soapChain` ignore CSRF đúng, SOAP vẫn 403.

**Đáp án:** chain đầu tiên **bắt mọi request**, SOAP chain không được chọn. Đưa SOAP chain có `securityMatcher` cụ thể lên trước và giữ UI catch-all sau; kiểm tra `FilterChainProxy` thực tế rồi chạy lại toàn bộ authorization/CSRF tests.

### Tình huống J — Mở SOAP POST nhưng không có operation authorization

SOAP route yêu cầu scope `soap.invoke`, người dùng có scope này gửi `CancelOrderRequest` để hủy đơn của tenant khác. Endpoint mapping nhận Body QName nên method được gọi.

**Đáp án:** exemption CSRF chỉ liên quan HTTP browser risk; **operation/tenant authorization** vẫn bắt buộc. Service method phải kiểm tra ownership/tenant/scope cụ thể, và WS-Security signing nếu contract yêu cầu. Không cho rằng JAXB validate hoặc `@PayloadRoot` đã đảm bảo quyền hủy đơn.

### Tình huống K — Request SOAP hợp lệ sau proxy nhưng matcher không khớp

Public URL có prefix `/orders/ws`, proxy chuyển tiếp tới servlet `/ws/*`. Developer so `getRequestURI()=="/ws"` và không hiểu vì sao SOAP POST vẫn 403.

**Đáp án:** `getRequestURI()` có thể bao gồm contextPath; `getServletPath()`/`getPathInfo()` được tính theo servlet mapping tại container. Hãy quan sát và test đúng đường thực tế, tránh tự nối/trừ prefix bằng string manipulation thiếu kiểm soát.

### Tình huống L — Gửi CSRF token trong SOAP Header

Client browser thêm `<app:CsrfToken>abc...</app:CsrfToken>` vào SOAP Header, nhưng Spring Security vẫn 403.

**Đáp án:** Spring `CsrfFilter` mặc định đọc token qua cơ chế HTTP header/request parameter của `CsrfTokenRequestHandler`, không tự parse custom SOAP Header. Gửi token qua **HTTP header** mà server mong đợi, cùng session/repository phù hợp; tránh biến `CsrfFilter` thành XML parser.

## 14. Quy trình review trước khi duyệt ngoại lệ CSRF

Một thay đổi bảo mật tốt nên có **lý do**, **phạm vi** và **bằng chứng test** ghi lại được trong code review. Đề xuất kiểm tra theo thứ tự:

### 14.1. Bước 1 — Chụp hiện trạng

Ghi nhận:

~~~text
Spring Security version: 6.x (xác định patch version thực)
Spring Web Services version: 4.x (xác định bản thực)
HTTP servlet mapping: /ws/*
SOAP POST endpoint: /ws, /ws/
WSDL GET endpoint: /ws/orders.wsdl
UI endpoints: /account/**, /admin/**, /login
SOAP auth: JWT Bearer only (ví dụ)
UI auth: form login + session
WS-Security policy: Signature/Timestamp nếu áp dụng
Proxy context path: /orders hoặc theo môi trường
~~~

Đây là **mẫu checklist điền dữ liệu thực**, không phải kết quả kiểm tra repository hiện tại. Nếu SOAP chấp nhận cookie, browser Basic hoặc cơ chế ambient auth khác, **chưa đủ điều kiện** để duyệt ngoại lệ như ví dụ máy–máy.

### 14.2. Bước 2 — Chứng minh request khớp đúng matcher

Với `/ws/*`, test:

~~~text
Allowed for CSRF exclusion:
  POST /ws              yes
  POST /ws/             yes

Not excluded:
  GET  /ws              no exemption needed by default
  POST /ws/orders.wsdl  no
  POST /ws/admin/reset  no
  PUT  /ws              no
  POST /account/change  no
~~~

Không chỉ dựa vào chuỗi URL tài liệu; test giá trị **servletPath/pathInfo**, context path và proxy rewrite thật. Nếu endpoint dùng một URL khác, phải sửa code/test **cùng lúc**, không nới thành `/ws/**` để “cho dễ”.

### 14.3. Bước 3 — Chứng minh authentication và authorization vẫn hoạt động

Sau khi bỏ CSRF cho SOAP POST, thử:

- Không Bearer → từ chối.
- Bearer sai/hết hạn → từ chối.
- Bearer thiếu scope → từ chối.
- Có session cookie UI nhưng thiếu Bearer → từ chối.
- Bearer đúng scope → tới SOAP dispatcher, không bypass XSD/WSS4J.
- Có scope endpoint nhưng không có quyền operation/tenant → business authorization từ chối.
- Replay/duplicate requests → không tạo side effects ngoài idempotency policy.

Nếu SOAP chỉ xác thực bằng WS-Security ở SOAP layer, hãy chứng minh request **chưa được ký đúng** luôn bị chặn trước khi service thực hiện nghiệp vụ. Trường hợp này thường cần thêm gateway/network constraints và test kỹ, vì HTTP authorization có thể chưa biết principal cho đến khi WSS4J xử lý Envelope.

### 14.4. Bước 4 — Chứng minh ứng dụng web không bị ảnh hưởng

Tối thiểu:

~~~text
UI POST + session + missing CSRF   -> 403
UI POST + session + invalid CSRF   -> 403
UI POST + session + valid CSRF     -> qua CSRF, vẫn cần authz
Admin POST + valid CSRF + no role  -> 403
SOAP URL khác target matcher       -> không hưởng ngoại lệ
~~~

Nếu một kiểm thử trước đây phải nhận CSRF 403 nhưng giờ không còn, có thể ngoại lệ hoặc filter chain bị mở rộng ngoài ý định. **Không lấy SOAP integration test pass làm đủ bằng chứng.**

### 14.5. Bước 5 — Rollout và giám sát

Theo dõi có kiểm soát:

| Metric/log event | Mục đích |
| --- | --- |
| HTTP 401 tại SOAP endpoint | Thiếu/sai authentication, sự cố token lifecycle. |
| HTTP 403 theo lớp CSRF/authz | Xác định request/browser routes còn được bảo vệ. |
| SOAP Fault security/validation | Xem WSS4J/XSD lỗi sau khi qua HTTP filters. |
| Số yêu cầu SOAP POST không Bearer | Phát hiện clients sai cấu hình hoặc truy cập bất thường. |
| CSRF missing/invalid trên UI | Phát hiện app/browser integration lỗi hoặc hành vi đáng ngờ. |
| Endpoint match anomalies | Phát hiện đường dẫn mới không nằm trong matcher đã duyệt. |
| Certificate/JWT key rotation failures | Phân biệt lỗi TLS/identity với CSRF. |

Không ghi raw JWT, CSRF token, session ID, certificate private keys, SOAP Envelope chứa dữ liệu cá nhân hoặc WS-Security credentials. Trong rollout, luôn có đường **rollback cấu hình** và so sánh behavior với test trước khi thay đổi.

## 15. Checklist cuối bài

| Câu hỏi | Điều kiện đạt |
| --- | --- |
| Xác định đúng loại client? | Phân biệt browser dùng cookie/session với backend máy–máy. |
| Xác định credential có ambient không? | SOAP route không tự nhận cookie/Basic browser credential nếu được miễn CSRF. |
| CSRF risk đã được đánh giá? | Không dựa một mình vào XML Content-Type, CORS hay `SameSite`. |
| SOAP URL rõ? | Phân biệt `POST /ws` với `GET /ws/orders.wsdl` và các URL khác. |
| Ngoại lệ chính xác? | Matcher dùng **method POST + exact servlet path/pathInfo** và đã test. |
| Không disable toàn app? | UI/admin/session chains vẫn bật `CsrfFilter`. |
| Không bypass security filters? | Không dùng `web.ignoring()` để sửa lỗi SOAP 403. |
| SecurityFilterChain order đúng? | SOAP chain chọn trước UI catch-all, fallback bảo vệ tất cả đường còn lại. |
| Phân biệt matcher APIs? | `securityMatcher` quyết định chain; `requestMatchers` trong authz và CSRF có vai trò riêng. |
| Không dùng permitAll để sửa 403? | Authorization vẫn yêu cầu principal/scope/operation permission. |
| Stateless được hiểu đúng? | `STATELESS` không thay thế threat-model CSRF hoặc tự xóa cookie auth. |
| Browser SOAP được bảo vệ? | Nếu dùng session cookie, giữ token/repository/handler đúng version. |
| WSDL access policy rõ? | Public hay private là quyết định authorization, không phải CSRF. |
| WS-Security vẫn có hiệu lực? | WSS4J Signature/UsernameToken/Replay/Timestamp được kiểm chứng nếu contract yêu cầu. |
| TLS/mTLS và JWT đúng? | Tin cậy chain/hostname, JWT issuer/audience/expiry/scope, không log credentials. |
| Authorization theo operation? | `CreateOrder`/`CancelOrder` và tenant/resource permissions được bảo vệ. |
| Unit test matcher đạt? | Exact path, trailing slash, method, pathInfo khác đều được kiểm tra. |
| Integration HTTP đạt? | Servlet path/contextPath/proxy, authenticated SOAP request và 401/403 behavior đúng. |
| Negative UI test đạt? | POST session không có CSRF vẫn 403, kể cả sau SOAP change. |
| SOAP Fault được phân loại? | Không nhầm HTTP 403 của filter với `soap:Fault` do WSS4J/XSD. |
| Có logging/monitoring an toàn? | Có correlation ID và error category, không lộ tokens/Body. |
| Có kế hoạch versioning/rollback? | Spring Security matcher và CSRF token handler được test sau nâng cấp. |

### 15.1. Các câu hỏi ôn tập

1. Vì sao SOAP POST bị Spring Security CSRF filter chặn dù XML Body hợp XSD?
2. HTTP 403 do `CsrfFilter` khác SOAP Fault do `Wss4jSecurityInterceptor` thế nào?
3. Vì sao GET WSDL thành công không chứng minh POST SOAP được phép?
4. Hai tiêu chí tối thiểu của một CSRF ignore matcher hẹp là gì? Điều gì khác cũng phải được kiểm chứng?
5. Vì sao một SOAP endpoint chấp nhận session cookie không nên được miễn CSRF chỉ vì có `Content-Type: text/xml`?
6. `http.securityMatcher`, `csrf.ignoringRequestMatchers` và `authorizeHttpRequests.requestMatchers` khác nhau thế nào?
7. `csrf.disable()` và `web.ignoring()` có khác nhau về phạm vi filter bảo vệ không?
8. Một UI form POST có user session đúng nhưng không có CSRF token phải có kết quả gì?
9. `SessionCreationPolicy.STATELESS` tự làm CSRF protection không cần thiết chưa?
10. Khi nào có thể cân nhắc miễn CSRF cho SOAP machine-to-machine?
11. JWT được trình duyệt tự mang trong cookie khác gì JWT do backend chủ động đặt trong `Authorization`?
12. Nếu Spring-WS gửi SOAP Signature đúng mà HTTP 403 xảy ra trước servlet, sửa WSS4J có giúp được không?
13. Vì sao `permitAll()` không tự sửa lỗi CSRF 403?
14. Tại sao mọi request `/ws/**` không nên được ignore CSRF vô điều kiện?
15. Cần những negative tests nào để chứng minh UI/session routes vẫn an toàn sau khi thêm SOAP exception?
16. Một ngoại lệ đã hẹp về URL có còn nguy hiểm nếu SOAP endpoint cho browser cookie credentials không?
17. Spring Security JWT test helper có chứng minh signature/issuer/audience của JWT thật không?
18. Nếu reverse proxy đổi context path, phải kiểm tra những trường nào trước khi sửa matcher?

## 16. Nguồn tham khảo chính thức

Nên đối chiếu đúng **Spring Security/Spring-WS phiên bản đã resolve**, không lấy docs của bản mới hơn thay cho JAR đang chạy:

- **Spring Security — [CSRF protection (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)**: CSRF threat model, token repository/request handler, ignoring paths và SPA integration.
- **Spring Security 6.5 — [CsrfConfigurer Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/CsrfConfigurer.html)**: `ignoringRequestMatchers(RequestMatcher...)` và `requireCsrfProtectionMatcher`.
- **Spring Security — [Java configuration và multiple SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)**: `securityMatcher`, `requestMatchers`, `@Order`, filter chains và fallback.
- **Spring Security — [Authentication/Authorization architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)**: filter pipeline và trách nhiệm của filter chain.
- **Spring Security 6.5 — [CSRF reference](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)**: cookie/session/SPA CSRF token considerations.
- **Spring Security — [Spring Security Test, Servlet testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)**: `MockMvc`, `csrf()`, `user()` và authentication test support.
- **Spring Web Services — [Reference 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/)**: `MessageDispatcherServlet`, WSDL GET, SOAP POST, SOAP endpoints/interceptors.
- **Spring Web Services — [MessageDispatcherServlet Javadoc 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/transport/http/MessageDispatcherServlet.html)**: servlet routing và lifecycle.

Các tài liệu có thể có thay đổi giữa Spring Security 6.x và 7.x về lựa chọn matcher, token handler mặc định và API DSL. Đối với bài tập của hệ thống cụ thể, cần xem **dependency tree** và test request thực tế qua chính `SecurityFilterChain`/`MessageDispatcherServlet` đang triển khai.

### Ghi nhớ

- **SOAP POST là HTTP POST:** Spring Security `CsrfFilter` có thể yêu cầu token trước khi Spring-WS xử lý SOAP Body; đây thường là nguyên nhân khi WSDL GET thành công nhưng SOAP POST nhận 403.
- **Không tắt CSRF toàn ứng dụng chỉ để sửa SOAP 403.** Chỉ cân nhắc ngoại lệ cho endpoint **máy–máy không dùng credential ambient của trình duyệt**, và matcher **đúng method + URL/servlet mapping**.
- **Ngoại lệ CSRF không phải ngoại lệ xác thực/phân quyền.** Giữ JWT/mTLS/WS-Security, operation/tenant permissions, XML validation và replay/idempotency policies.
- **Nếu SOAP client là trình duyệt dùng session cookie, hãy giữ CSRF token** và cấu hình repository/request handler đúng phiên bản. SOAP Header tùy chỉnh không tự được Spring Security đọc làm HTTP CSRF token.
- **`securityMatcher`, `ignoringRequestMatchers`, `requestMatchers` và `web.ignoring()` khác nhau**; sai filter-chain order hoặc matcher có thể vừa gây 403 giả vừa làm hở đường không mong muốn.
- **Phải kiểm thử cả chiều thành công và chiều từ chối.** SOAP POST JWT đúng đi qua CSRF; SOAP POST không auth, thiếu quyền, UI POST thiếu token và các URL/method ngoài ngoại lệ vẫn bị chặn theo policy.
- **HTTP 401/403 và SOAP Fault thuộc các tầng khác nhau.** Kiểm tra response, filter chain, servlet path và WSS4J trước khi sửa certificate, XSD hoặc bật debug nhạy cảm.







