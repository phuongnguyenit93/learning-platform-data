# Ngữ nghĩa Bearer: quyền sử dụng gắn với việc nắm giữ token

Trong OAuth 2.0 Resource Server, **bearer token** là một cách dùng access token dựa trên nguyên tắc: **bên nào nắm giữ token hợp lệ đều có thể xuất trình token để yêu cầu quyền truy cập mà token đại diện**. Resource Server cần kiểm tra token và điều kiện phân quyền, nhưng với bearer token thuần túy, nó **không yêu cầu bên gửi chứng minh đang giữ một khóa mật mã riêng được ràng buộc với token**.

Đây là điểm cốt lõi để hiểu cả sự thuận tiện lẫn rủi ro của bearer token. Token hoạt động gần giống một **chìa khóa truy cập tạm thời**: có chìa khóa chưa chắc được mở mọi cửa; nhưng ai nhặt được chìa khóa có thể thử mở những cửa mà chìa khóa ấy được phép mở.

Theo [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750), tính chất của bearer token là người nắm giữ token có thể sử dụng token mà không cần đưa ra bằng chứng sở hữu một khóa mật mã (proof of possession). Điều này đúng cho **cả JWT access token lẫn opaque access token** nếu chúng được dùng theo ngữ nghĩa bearer.

## 1. “Bearer” nghĩa là gì?

Từ **bearer** chỉ **người/bên đang mang hoặc nắm giữ** một giá trị chứng thực. Giả sử Authorization Server cấp access token `T` cho client A:

1. Client A gửi `T` tới `orders-api` bằng header `Authorization: Bearer T`.
2. Resource Server kiểm tra `T` và cho phép những thao tác nằm trong phạm vi token.
3. Nếu một bên B không được ủy quyền sao chép được toàn bộ `T`, B cũng có thể gửi `Authorization: Bearer T`.
4. Nếu `T` vẫn hợp lệ và request của B đáp ứng các điều kiện phân quyền, **bearer token tự nó không giúp Resource Server phân biệt A với B**.

Điểm cần giữ chính xác: **nắm giữ token cho phép yêu cầu truy cập theo quyền của token**, chứ không có nghĩa mọi request kèm token đều phải được chấp nhận. Server vẫn có thể từ chối token hết hạn, token không đúng audience, token thiếu scope hoặc hành động vượt quyền sở hữu dữ liệu.

~~~text
               Authorization Server
                       |
            cấp access token T
                       |
                       v
                Client hợp lệ A
                       |
     GET /api/orders   | Authorization: Bearer T
                       v
                Resource Server
                kiểm tra T + quyền
                       |
                 trả kết quả


 Nếu T bị lộ:
                Bên không được ủy quyền B
                       |
     GET /api/orders   | Authorization: Bearer T
                       v
                Resource Server
                kiểm tra T + quyền
                       |
     T vẫn hợp lệ? B có thể sử dụng quyền mà T cho phép.
~~~

Resource Server có thể áp dụng thêm bảo vệ như phân quyền theo dữ liệu, giới hạn hành vi hoặc token bị ràng buộc với sender. Nhưng các biện pháp đó **không làm thay đổi định nghĩa cơ bản** của bearer token thuần túy.

### “Nắm giữ” token không đồng nghĩa “là chủ sở hữu hợp pháp”

Ba khái niệm thường dễ bị nhầm:

| Khái niệm | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| **Possession** — đang nắm token | Request có mang theo một giá trị token không? | Header chứa `Bearer T` |
| **Token validation** — token hợp lệ | Token có được phát hành bởi nguồn tin cậy, còn hiệu lực và dành cho API này không? | Chữ ký JWT hợp lệ; `exp` còn hạn; `iss` và `aud` đúng |
| **Authorization** — được phép thao tác | Quyền trong token và chính sách của hệ thống có cho phép hành động này không? | `orders.read` và đơn hàng thuộc khách hàng tương ứng |

Với bearer token, việc có `T` thường đủ để **trình bày bằng chứng ủy quyền ở tầng token**. Nó không tự chứng minh người thực hiện request là người dùng đã đăng nhập ban đầu, là ứng dụng ban đầu hoặc là thiết bị ban đầu.

## 2. Bearer là ngữ nghĩa sử dụng, không phải định dạng token

Một nhầm lẫn phổ biến là đồng nhất “bearer” với “JWT”. Thực tế có hai trục độc lập:

- **Định dạng token**: JWT có chữ ký, opaque string hoặc biểu diễn khác theo hợp đồng của Authorization Server.
- **Cách chứng minh quyền sử dụng token**: bearer thuần túy hoặc token ràng buộc với bên gửi (sender-constrained), chẳng hạn mTLS/DPoP.

| Token | Resource Server kiểm tra như thế nào? | Nếu kẻ khác lấy được chính token đó thì sao? |
|---|---|---|
| JWT access token dùng như bearer | Xác minh chữ ký, thời gian, issuer, audience và claim | Có thể phát lại token còn hợp lệ trong phạm vi quyền được cấp |
| Opaque access token dùng như bearer | Thường gọi introspection endpoint để kiểm tra trạng thái/quyền | Có thể phát lại token còn `active` trong phạm vi quyền được cấp |
| Access token được ràng buộc với sender | Kiểm tra tính hợp lệ của token **và** bằng chứng về sender | Chỉ lấy được chuỗi token thường chưa đủ; cần cả bằng chứng/khóa thích hợp |

Điều quan trọng là **JWT được ký không đồng nghĩa token đã được ràng buộc với người gửi request**. Chữ ký JWT thường chứng minh token không bị sửa và được ký bởi một issuer tin cậy, **không chứng minh client hiện tại là nơi AS đã cấp token**.

### Ví dụ một JWT bearer

Giả sử nội dung claim hợp lệ được AS phát hành là:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "customer-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1794703600
}
~~~

Nếu token đã có chữ ký hợp lệ, Resource Server có thể xác định token đại diện cho subject `customer-42`, chỉ dành cho `orders-api` và có scope `orders.read`. Nhưng nếu bị sao chép, **bên đang gửi token không nhất thiết là chính khách hàng 42**. Claim `sub` là thông tin về chủ thể mà AS ghi trong token; nó không phải bằng chứng sống rằng chủ thể ấy đang trực tiếp thao tác.

## 3. Luồng Bearer Token qua HTTP

OAuth 2.0 quy định cách phổ biến, được khuyến nghị để trình bày bearer token là header HTTP:

~~~http
GET /api/orders/1001 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
Accept: application/json
~~~

Giá trị sau `Bearer` là **access token** mà client có quyền sử dụng. Request không cần gửi password, refresh token hay client secret cùng lúc. Resource Server xác thực token theo cách được cấu hình.

~~~text
  Client                   Resource Server               Authorization Server
    |                            |                                 |
    |-- Authorization: Bearer T ->|                                 |
    |                            |                                 |
    |                            |-- [JWT] xác minh bằng public key |
    |                            |            đã tin cậy            |
    |                            |                                 |
    |                            |-- [opaque] introspection T ----->|
    |                            |<--- active, scope, sub, ... -----|
    |                            |                                 |
    |                            |-- kiểm tra scope, đối tượng,     |
    |                            |   chính sách của endpoint       |
    |<--------- 200/401/403 ------|                                 |
~~~

Hai nhánh trong sơ đồ là **những phương án xác minh thay thế**, không phải bắt buộc phải thực hiện cả hai với mỗi request.

### Bearer token không phải lệnh “bỏ qua authentication”

Trong Spring Security, việc dùng bearer token vẫn đi qua quy trình xác thực đầy đủ:

1. Lấy token từ request.
2. Đưa token vào cơ chế `Authentication`.
3. Xác minh bằng JWT decoder hoặc opaque token introspector đã cấu hình.
4. Tạo principal và authorities nếu token hợp lệ.
5. Kiểm tra authorization rule của API.

“Không phải chứng minh thêm khóa riêng” không có nghĩa là “không kiểm tra token”.

## 4. Vì sao token bị lộ dẫn tới nguy cơ replay?

**Token replay** là tình huống một giá trị token hợp lệ bị thu thập rồi được gửi lại từ một nguồn khác. Với bearer token thuần túy, việc gửi lại chính chuỗi token không bị chặn chỉ bởi cơ chế bearer.

Ví dụ:

- Token `T` cấp cho `shop-web` có quyền `orders.read` trên `orders-api`, hết hạn sau 10 phút.
- Trong 10 phút đó, token vô tình xuất hiện trong application log hoặc một công cụ debug.
- Người không được phép có quyền đọc log lấy được `T` và gửi request từ thiết bị khác.
- Nếu Resource Server chỉ yêu cầu bearer token, token còn hợp lệ, đúng audience và request không vi phạm quyền dữ liệu bổ sung, request đó có thể được chấp nhận.

Ở đây **TLS không cứu được token đã bị lộ từ log**. TLS bảo vệ đường truyền; nó không thể tự ngăn người khác sử dụng một bí mật đã bị sao chép từ nơi khác.

### Những đường rò rỉ bearer token thường gặp

| Nguồn rò rỉ | Cách xảy ra | Tác động |
|---|---|---|
| HTTP thay vì HTTPS | Bên thứ ba có thể quan sát hoặc thay đổi lưu lượng | Đánh cắp token trên đường truyền |
| Log tại API gateway, reverse proxy, app | Ghi toàn bộ request headers, trace, exception | Người đọc log có thể sao chép `Authorization` |
| URL query | Token xuất hiện trong access log, lịch sử trình duyệt, link được chia sẻ hoặc referrer | Rất khó kiểm soát nơi token lan truyền |
| JavaScript bị chèn (XSS) | Script độc hại có quyền truy cập token trong môi trường browser | Đọc hoặc dùng token trong phiên người dùng |
| Tiện ích trình duyệt, công cụ debug, telemetry | Chụp request/response, lưu lại header | Token lan tới hệ thống ngoài dự kiến |
| Lưu trữ trên máy khách không an toàn | File cấu hình, local storage, bộ nhớ hoặc backup bị truy cập trái phép | Token bị dùng lại |
| Chia sẻ token qua chat, ticket, ảnh chụp màn hình | Người xử lý sự cố dán nhầm token thật | Nhiều bên cùng nắm bí mật truy cập |

Các ví dụ trên nêu **bề mặt rủi ro**, không mặc định mọi hệ thống hay phương tiện lưu trữ đều có mức độ nguy hiểm như nhau. Tính nhạy cảm còn phụ thuộc vòng đời token, quyền của token và khả năng truy cập của kẻ tấn công.

### Token replay bị giới hạn bởi những gì?

Một bearer token bị lộ không nhất thiết còn dùng được nếu:

- Token đã hết hạn (`exp`) hoặc đã bị vô hiệu qua hệ thống xác minh đang dùng.
- Token không dành cho API bị gọi (`aud` khác).
- Token không có scope/authority cần thiết.
- Chính sách tài nguyên từ chối truy cập dù scope đúng.
- Resource Server có yêu cầu bổ sung mà bên dùng token không đáp ứng, chẳng hạn sender-constrained proof.

**Nguyên tắc giảm thiểu thiệt hại:** token càng sống ngắn, quyền càng hẹp, audience càng cụ thể thì tác động của một lần rò rỉ thường càng nhỏ.

## 5. Những thông tin gì thực sự được chứng minh khi RS nhận Bearer T?

Giả sử một API nhận token và giải mã ra:

~~~json
{
  "sub": "alice",
  "client_id": "shop-web",
  "scope": "profile.read",
  "aud": ["profile-api"]
}
~~~

Resource Server có thể dựa vào claim đã xác minh để xử lý yêu cầu **như một request được token cho phép thay mặt subject `alice`**. Nhưng chính token không chứng minh:

- Người đang cầm điện thoại hoặc máy tính là Alice.
- Request xuất phát từ đúng ứng dụng `shop-web` nguyên gốc.
- Request đến từ đúng IP hay thiết bị từng nhận token.
- Alice vẫn đang đăng nhập tương tác ở trình duyệt.
- Mọi hồ sơ hay bản ghi trong hệ thống đều thuộc về Alice.

Hệ thống vẫn cần các lớp kiểm soát tương ứng. Ví dụ, đọc `GET /api/profiles/alice` có thể hợp lệ với claim `sub=alice`, còn đọc `/api/profiles/bob` phải bị chặn nếu Alice không có quyền truy cập Bob.

**Không dùng email, `sub` hay `client_id` trong token như “bằng chứng bên gửi là chính chủ”**. Chúng là thuộc tính/claim được tin sau xác minh token, không phải bằng chứng sender possession.

## 6. Spring Security xử lý bearer token ở đâu?

Trong một Spring MVC Resource Server, cơ chế mặc định được thiết kế xoay quanh HTTP `Authorization: Bearer ...`:

~~~text
HTTP request
    |
    v
Spring Security FilterChain
    |
    v
BearerTokenAuthenticationFilter
    |
    +-- BearerTokenResolver lấy token từ request
    |
    +-- AuthenticationManager / AuthenticationProvider
    |       |
    |       +-- JWT: JwtDecoder và validators
    |       |
    |       +-- Opaque: OpaqueTokenIntrospector
    |
    +-- xác thực thành công -> SecurityContext có Authentication
    |
    v
AuthorizationFilter / method security
    |
    +-- scope, role, chính sách truy cập dữ liệu
    |
    v
Controller / business logic
~~~

Đây là mô tả khái niệm; thứ tự thành phần có thể chịu ảnh hưởng cấu hình nhiều `SecurityFilterChain` và các filter ứng dụng riêng.

Một số thành phần quan trọng:

| Thành phần | Trách nhiệm |
|---|---|
| `BearerTokenAuthenticationFilter` | Nhận diện bearer token và khởi động việc xác thực |
| `BearerTokenResolver` | Quyết định đọc token ở đâu trong HTTP request |
| `DefaultBearerTokenResolver` | Mặc định đọc từ header `Authorization` |
| `JwtDecoder` | Giải mã, xác minh chữ ký và claim JWT theo cấu hình |
| `OpaqueTokenIntrospector` | Kiểm tra token qua introspection và tạo principal từ thuộc tính trả về |
| `Authentication` / `SecurityContext` | Biểu diễn principal và authorities đã được xác thực trong request |
| Rule phân quyền | Quyết định endpoint/method/tài nguyên nào được truy cập |

Spring Security **không tự suy luận rằng token do cùng thiết bị đã nhận token gửi tới**. Nếu sử dụng token ràng buộc sender, hệ thống phải có hỗ trợ và cấu hình để xác minh bằng chứng ràng buộc đó.

### Cấu hình Resource Server dùng JWT bearer

Ví dụ cho ứng dụng servlet Spring MVC dùng Spring Security hiện đại:

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
~~~

Cấu hình `issuer-uri` là nguồn phát hành tin cậy; `audiences` ràng buộc token với `orders-api`. Thuộc tính `audiences` có ở các phiên bản Spring Boot hiện đại; nếu dùng phiên bản không hỗ trợ, bổ sung audience validator trong Java thay vì bỏ kiểm tra này.

`SecurityConfig.java`:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**Giả định bảo mật của ví dụ:** `/api/**` là API chỉ nhận access token trong `Authorization`, không dựa vào browser cookie/session để xác thực. Nếu cùng endpoint chấp nhận cookie tự động đính kèm hoặc ứng dụng phục vụ form đăng nhập, phải thiết kế lại CSRF thay vì sao chép `csrf(...disable)`.

Token có claim `scope: "orders.read"` thường được Spring Security ánh xạ thành authority `SCOPE_orders.read`. Nó cho phép **GET** theo rule bên trên, nhưng vẫn không được **POST** nếu thiếu `SCOPE_orders.write`. Code này kiểm tra quyền ở mức endpoint; controller/service còn phải kiểm tra quyền sở hữu từng đơn hàng.

### Thử request với curl

Ví dụ dùng token kiểm thử nhận được từ Authorization Server:

~~~bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.example.com/api/orders/1001
~~~

Không đưa access token thật vào tài liệu, shell history chia sẻ công khai, ảnh chụp màn hình hay hệ thống log. Biến môi trường cục bộ cũng cần được quản lý theo chính sách bí mật của môi trường chạy.

Một request có thể:

- Trả `200 OK` nếu token hợp lệ, có scope và được phép đọc đơn hàng.
- Trả `401 Unauthorized` nếu không có token, token sai hoặc token hết hạn.
- Trả `403 Forbidden` nếu token hợp lệ nhưng thiếu quyền, hoặc luật truy cập dữ liệu từ chối.

Số trạng thái chính xác và nội dung lỗi phụ thuộc cấu hình ứng dụng, exception handler và cơ chế xác thực/phân quyền bổ sung.

## 7. Lựa chọn vị trí mang bearer token

RFC 6750 mô tả các phương thức vận chuyển bearer token trong HTTP. Với API hiện đại, **header `Authorization` là cách được ưu tiên**:

~~~http
Authorization: Bearer <access_token>
~~~

Một số dạng truyền khác tồn tại trong đặc tả hoặc hệ thống cũ, nhưng mang nhiều rủi ro hơn.

| Nơi đặt token | Đánh giá | Lý do |
|---|---|---|
| Header `Authorization` | Lựa chọn mặc định khuyến nghị | Tách credential khỏi URL, có cơ chế HTTP authentication chuẩn |
| Form body `application/x-www-form-urlencoded` | Ngoại lệ có điều kiện trong RFC 6750 | Bất tiện, có điều kiện chặt và dễ bị ghi trong payload log |
| URL query `?access_token=...` | Tránh sử dụng | Dễ lộ qua URL logs, browser history, referrer, link chia sẻ |
| Cookie | Không phải vị trí bearer mặc định của Resource Server | Browser tự gửi cookie; cần xét CSRF, SameSite, cookie scope và kiến trúc phiên |

Theo `DefaultBearerTokenResolver`, Spring Security mặc định **không chấp nhận** bearer token từ URI query parameter hoặc form body. Chỉ bật các nguồn đó nếu có yêu cầu đặc biệt, hiểu rõ hệ quả bảo mật và hạn chế bề mặt lộ token.

Không nên tạo “tiện ích” như:

~~~http
GET /api/orders?access_token=<token>
~~~

vì token trong URL có thể đi qua nhiều tầng ghi lại metadata request. Kể cả khi một API chưa ghi URL ra log, proxy, APM, trình duyệt hoặc hạ tầng bên ngoài vẫn có thể lưu thông tin.

### HTTP header không bảo đảm token không bị log

Các ứng dụng thường có filter log hoặc API gateway ghi request headers. Do đó phải chủ động **redact `Authorization`**, `Proxy-Authorization` và các header bí mật tương tự trước khi đẩy dữ liệu ra log, tracing, crash report hay công cụ phân tích.

Ví dụ log an toàn hơn:

~~~text
GET /api/orders/1001
Authorization: [REDACTED]
traceId: 9d5f...
status: 200
~~~

Tránh log toàn bộ giá trị token, ngay cả trong môi trường development chia sẻ hoặc khi trả về thông báo lỗi cho người dùng.

## 8. Bearer token, HTTPS và giới hạn của bảo mật đường truyền

**HTTPS/TLS là yêu cầu nền tảng** khi chuyển bearer token qua mạng. Nó bảo vệ nội dung request khỏi việc đọc trộm/sửa đổi trên đường truyền giữa các điểm kết thúc TLS.

Nhưng cần tách rõ:

- **TLS bảo vệ token trong lúc truyền** giữa các endpoint TLS tin cậy.
- **JWT signature bảo vệ tính toàn vẹn và nguồn ký token**, không ngăn token đã bị lộ bị trình bày lại.
- **Thời hạn, scope và audience** giảm khoảng thời gian cũng như phạm vi token được sử dụng.
- **Sender-constrained proof** bổ sung điều kiện để một chuỗi token bị đánh cắp không tự đủ cho request.

Nếu TLS kết thúc ở load balancer hoặc API gateway rồi chuyển tiếp nội bộ, phải bảo vệ cả đường chuyển tiếp phù hợp với ranh giới tin cậy. Không mặc định chặng “nội bộ” có thể truyền bearer token qua kênh thiếu bảo mật.

### Ngữ nghĩa bearer không gắn mặc định với IP hay User-Agent

Một số hệ thống muốn lưu IP/User-Agent lúc phát hành token rồi từ chối token xuất hiện ở IP mới. Đây là **chính sách bổ sung** và có nhược điểm: thiết bị di động, VPN, proxy, NAT và browser update có thể thay đổi các giá trị này. IP hoặc User-Agent **không phải bằng chứng mật mã về bên nắm token**. Không nên coi kiểm tra chúng là phương án thay thế hoàn chỉnh cho sender-constrained token.

## 9. Cách giảm rủi ro của bearer token

Vì possession là yếu tố quyết định, bảo vệ token phải theo toàn bộ vòng đời: **cấp phát → chuyển giao → sử dụng → lưu trữ → hết hạn/thu hồi**.

### 9.1. Giới hạn phạm vi token

Authorization Server nên phát hành access token theo nguyên tắc quyền tối thiểu:

- **Audience cụ thể**: token của `orders-api` không được tự dùng cho `billing-api`.
- **Scope tối thiểu**: ứng dụng chỉ đọc đơn hàng nhận `orders.read`, không nhận `orders.write` nếu không cần.
- **Lifetime hợp lý**: token sống ngắn giới hạn thời gian kẻ đánh cắp có thể sử dụng.
- **Phân quyền dữ liệu**: `orders.read` không có nghĩa được đọc mọi đơn hàng; API cần xét chủ sở hữu/tenant/trạng thái.

Đối với JWT, Resource Server phải xác minh chữ ký và các claim bắt buộc, nhất là `iss`, `aud`, `exp` và các yêu cầu liên quan. Đối với opaque token, Resource Server phải kiểm tra trạng thái qua cơ chế đã tin cậy như introspection, đồng thời áp dụng quyền truy cập của API.

### 9.2. Quản lý thời gian sống và thu hồi

Giả sử access token còn 5 phút hiệu lực. Nếu token bị lộ, kẻ tấn công có thể khai thác trong thời gian đó nếu không có cơ chế thu hồi/giới hạn khác.

Các lựa chọn vận hành gồm:

1. **Access token ngắn hạn:** thu hẹp cửa sổ replay.
2. **Introspection:** Resource Server hỏi trạng thái hiện tại của token tại Authorization Server; cần kiểm soát timeout và cache.
3. **Denylist/phiên bản quyền/kiểm tra trạng thái bổ sung:** phục vụ thu hồi sớm trong mô hình JWT xác minh cục bộ, nếu được thiết kế nhất quán.
4. **Sender-constrained token:** làm giảm khả năng dùng chỉ riêng token bị lộ.

“User logout” ở phía client chỉ xóa trạng thái của client và có thể kích hoạt cơ chế revoke riêng. **Nó không mặc nhiên làm mọi bản sao access token đã phát hành mất hiệu lực** ở Resource Server đang xác minh JWT cục bộ.

Nếu cache introspection response, thời gian cache có thể làm chậm hiệu lực thu hồi. Phải thiết kế TTL cache dựa vào yêu cầu bảo mật, không giả định introspection luôn luôn phản ánh tức thời trong mọi kiến trúc.

### 9.3. Giữ token tránh các bề mặt rò rỉ

Theo từng loại client, cách bảo vệ khác nhau:

| Client | Cân nhắc chính |
|---|---|
| Backend server | Lưu token/secret trong bộ nhớ hoặc kho bí mật có kiểm soát; tránh log và dump |
| Ứng dụng browser SPA | JavaScript bị XSS có thể đọc token truy cập được từ JS; ưu tiên kiến trúc và cơ chế giảm phơi nhiễm phù hợp |
| Browser với Backend for Frontend (BFF) | Backend giữ token; browser dùng session cookie bảo vệ đúng cách; phải xử lý CSRF và session security |
| Mobile/native app | Dùng API/kho lưu trữ bảo mật của nền tảng; tránh log và backup không phù hợp |
| Service-to-service | Bảo vệ token trong bộ nhớ, luồng giao tiếp và telemetry; cân nhắc mTLS/DPoP khi yêu cầu |

Không tồn tại một lựa chọn lưu token luôn đúng cho mọi ứng dụng. `localStorage` và `sessionStorage` dễ dùng nhưng script chạy cùng origin có thể truy cập; `HttpOnly` cookie ngăn JavaScript đọc cookie trực tiếp nhưng trình duyệt tự gửi cookie, kéo theo bài toán CSRF nếu cookie dùng để xác thực. Cần xét **mô hình tấn công tổng thể** thay vì kết luận chỉ từ nơi lưu.

## 10. Sender-constrained access token: khi possession chưa đủ

OAuth 2.0 Security Best Current Practice ([RFC 9700](https://www.rfc-editor.org/rfc/rfc9700)) khuyến nghị dùng các cơ chế **sender-constrained access token** khi phù hợp để hạn chế việc sử dụng lại token bị đánh cắp.

Có hai hướng chuẩn phổ biến:

### 10.1. Mutual TLS (mTLS) — RFC 8705

Authorization Server gắn access token với danh tính/chứng chỉ TLS client. Khi Resource Server nhận token, nó kiểm tra thông tin chứng chỉ mà kết nối mTLS đã xác thực và bảo đảm chứng chỉ khớp binding của token.

~~~text
Client nắm token T + private key của chứng chỉ client
           |
           | TLS handshake chứng minh sở hữu private key
           | Authorization: Bearer T
           v
Resource Server
           |
           +-- xác minh T
           +-- xác minh chứng chỉ client gắn với T
           +-- áp dụng quyền
~~~

Nếu chỉ lấy được chuỗi `T` nhưng không có khả năng dùng private key/chứng chỉ tương ứng, đối tượng tấn công thường không thể sử dụng token tại Resource Server đã thực thi binding đúng cách. Cách tổ chức trust với load balancer, proxy và TLS termination phải được thiết kế cẩn thận.

### 10.2. DPoP (Demonstrating Proof of Possession) — RFC 9449

DPoP ràng buộc token với một cặp khóa công khai/bí mật do client sử dụng. Với mỗi request, client có thể gửi **DPoP proof JWT** được ký bằng private key của mình, gắn với thông tin request.

Ví dụ cấu trúc request ở mức khái niệm:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: DPoP <access_token>
DPoP: <signed_proof_jwt>
~~~

Resource Server phải kiểm tra cả:

- Token có hợp lệ và được gắn với khóa công khai của client không.
- Chữ ký DPoP proof có hợp lệ không.
- Proof có khớp HTTP method và URI được bảo vệ không.
- Thông tin thời gian, định danh proof và ràng buộc token có đáp ứng yêu cầu chống replay không.

Cần lưu ý **Spring Security Resource Server mặc định cho `Bearer` không tự trở thành một DPoP Resource Server chỉ nhờ đổi header hoặc cấu hình `jwt()`**. Muốn hỗ trợ DPoP/mTLS đúng chuẩn phải dùng thành phần, cấu hình và triển khai kiểm tra ràng buộc tương ứng trên cả Authorization Server, client và Resource Server.

### So sánh bản chất

| Đặc điểm | Bearer thuần túy | Sender-constrained |
|---|---|---|
| Chỉ nắm chuỗi token còn hợp lệ | Có thể đủ để yêu cầu truy cập | Chưa đủ nếu thiếu proof hợp lệ |
| Bằng chứng khóa của bên gửi | Không bắt buộc | Có |
| Ngăn replay khi token bị sao chép riêng lẻ | Không, trừ biện pháp bổ sung | Có thể ngăn theo mô hình đe dọa và cơ chế binding |
| Độ phức tạp triển khai | Thấp hơn | Phải quản lý khóa/chứng chỉ, proof, kiểm tra và tích hợp |
| Nếu cả token **và** khóa của sender bị lấy | Token có thể bị lạm dụng | Ràng buộc có thể bị vượt qua; không tuyệt đối |

Việc ràng buộc sender giảm một dạng tấn công quan trọng, nhưng **không khiến phần mềm client đã bị chiếm quyền điều khiển trở nên an toàn tuyệt đối**. Nếu attacker kiểm soát cả token lẫn khóa hoặc có thể yêu cầu client ký proof, vẫn có thể xuất hiện hành vi trái phép.

## 11. Phân biệt Bearer token với ID token và refresh token

Cùng là chuỗi “token”, nhưng vai trò khác nhau:

| Loại token | Được gửi tới đâu? | Mục đích |
|---|---|---|
| **Access token** | Resource Server / API | Cho phép truy cập tài nguyên theo scope, audience và chính sách |
| **ID token (OIDC)** | OIDC Client / Relying Party | Cung cấp thông tin đã xác thực người dùng cho client |
| **Refresh token** | Authorization Server / token endpoint | Xin access token mới theo chính sách được phép |

Không tự lấy ID token rồi gửi `Authorization: Bearer <id_token>` vào API. Dù ID token cũng có thể là JWT có chữ ký, **audience và mục đích của nó thường dành cho client chứ không phải Resource Server**.

Refresh token cũng là bí mật nhạy cảm. Nó có thể cho phép nhận thêm access token và cần những biện pháp bảo vệ riêng, bao gồm chính sách rotation hoặc sender constraint theo loại client và tiêu chuẩn bảo mật áp dụng.

### Cũng đừng nhầm Bearer token với API key

API key và bearer token thường giống nhau về cảm giác sử dụng: ai biết giá trị bí mật có thể gửi request. Nhưng OAuth access token thường có các thuộc tính chuẩn hóa như issuer, audience, scope và thời hạn; API key có thể là cơ chế riêng của hệ thống. **Sự tương đồng về khả năng dùng lại bí mật không biến mọi API key thành OAuth bearer access token**.

## 12. 401, 403 và ý nghĩa của WWW-Authenticate

Khi request dùng bearer token thất bại, phân biệt lỗi xác thực và lỗi phân quyền giúp client xử lý đúng.

| Tình huống | Kết quả HTTP điển hình | Ý nghĩa |
|---|---|---|
| Không kèm token khi endpoint yêu cầu xác thực | `401 Unauthorized` | Client cần cung cấp thông tin xác thực hợp lệ |
| Bearer token hỏng, bị từ chối, hết hạn | `401 Unauthorized` | Token không thể dùng để xác thực request |
| Token hợp lệ nhưng thiếu `orders.write` cho thao tác sửa | `403 Forbidden` | Đã xác thực nhưng thiếu quyền |
| Token hợp lệ nhưng user không sở hữu đơn hàng | `403` hoặc `404` theo chính sách API | Điều kiện quyền dữ liệu không đạt |
| Request chứa nhiều cách trình bày token/malformed header | Có thể `400 Bad Request` | Request không đúng quy cách bearer token |

RFC 6750 mô tả header `WWW-Authenticate` để Resource Server giao tiếp thông tin về bearer authentication. Ví dụ minh họa:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

Hoặc khi token hợp lệ nhưng scope thiếu:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.write"
~~~

Ứng dụng có thể ẩn bớt chi tiết lỗi để tránh rò rỉ thông tin hệ thống. Không bao giờ đưa nguyên token hoặc credential của Authorization Server vào thông báo lỗi trả về client.

## 13. Một ví dụ đầy đủ: đánh cắp token đọc đơn hàng

Giả sử shop có:

- `orders-api` kiểm tra JWT bearer từ issuer `https://idp.example.com/realms/shop`.
- JWT có `sub=alice`, `aud=["orders-api"]`, `scope="orders.read"` và còn hạn 8 phút.
- Endpoint `GET /api/orders/1001` trả chi tiết đơn hàng 1001 cho Alice.
- Controller/service có kiểm tra chủ sở hữu đơn hàng.

Hãy xét bốn request:

| Người gửi và request | Kết quả mong đợi | Giải thích |
|---|---|---|
| Alice dùng token hợp lệ để xem đơn hàng 1001 của mình | Cho phép | Token hợp lệ, đúng API, có scope, đúng chủ sở hữu |
| Bob sao chép token Alice và xem đơn hàng 1001 | **Có thể được cho phép** nếu chỉ dựa vào các điều kiện đã nêu | RS nhận cùng token/claim `sub=alice`; không biết Bob là người gửi thực |
| Bob dùng token Alice để gọi `POST /api/orders` | Từ chối (thường 403) | Token thiếu `orders.write` |
| Bob dùng token Alice trên `billing-api` | Từ chối nếu billing xác minh audience đúng | Token chỉ có `aud=orders-api` |

Trường hợp thứ hai là bài học quan trọng nhất: ngay cả kiểm tra quyền sở hữu đơn hàng cũng **không phân biệt được một người đã đánh cắp token của Alice** nếu quyết định dựa trên cùng `sub` đã được xác thực. Do đó, ngoài kiểm tra quyền dữ liệu, hệ thống còn phải giảm nguy cơ lộ token và giới hạn khả năng phát lại.

Nếu chính sách kinh doanh yêu cầu xác thực mạnh cho hành động nhạy cảm như thay đổi tài khoản ngân hàng, phải thiết kế biện pháp bổ sung phù hợp (ví dụ bước xác thực mới, sender-constrained token, hay cơ chế phê duyệt giao dịch). **Bearer token có scope đúng không đồng nghĩa đủ bảo đảm người thật đang thực hiện hành động có rủi ro cao.**

## 14. Những hiểu nhầm cần tránh

**“Bearer là token không cần xác minh.”** Sai. Vẫn phải xác minh token, quyền và chính sách tài nguyên. Bearer chỉ nói về việc không yêu cầu bằng chứng sở hữu khóa mật mã riêng khi xuất trình token thuần túy.

**“JWT có chữ ký thì hacker không thể dùng token bị đánh cắp.”** Sai. Kẻ tấn công không cần sửa token; chỉ việc phát lại nguyên chuỗi token vẫn hợp lệ nếu các điều kiện khác cho phép.

**“Opaque token không bị replay.”** Sai. Opaque token dùng theo bearer semantics vẫn có thể bị sao chép và dùng lại nếu chưa bị vô hiệu.

**“Có claim `sub` là đã biết chính người đó đang gửi request.”** Sai. `sub` là danh tính được AS gắn vào token, không xác minh trực tiếp người đang cầm token tại thời điểm gọi API.

**“HTTPS là đủ, không cần chú ý tới logs/storage.”** Sai. TLS bảo vệ đường truyền nhưng không giải quyết lộ token ở endpoint, trace, trình duyệt hay kho lưu trữ.

**“Xóa token ở client là đã revoke token ở server.”** Sai. Phải có cơ chế hết hạn/thu hồi mà Resource Server thực sự áp dụng.

**“Thêm IP check là biến bearer thành proof-of-possession.”** Sai. IP không phải bằng chứng sở hữu khóa, có thể thay đổi hoặc dùng chung.

**“Bật JWT Resource Server là tự hỗ trợ DPoP.”** Sai. Sender constraint đòi hỏi cả cơ chế phát hành token lẫn kiểm tra proof tương ứng.

## 15. Câu hỏi tự kiểm tra

**Tình huống A:** Một JWT còn hạn, chữ ký đúng, scope đúng, được gửi từ máy lạ. Resource Server chỉ dùng JWT bearer thông thường. Server có tự biết đây không phải máy gốc không?

> Không. Nếu không có ràng buộc sender hoặc biện pháp bổ sung, token tự nó không chứng minh nơi gửi ban đầu.

**Tình huống B:** Opaque token được introspect và AS trả `active: true`. Điều này có bảo đảm request được truy cập mọi endpoint không?

> Không. Resource Server còn phải kiểm tra audience, scope và chính sách quyền trên tài nguyên.

**Tình huống C:** Token bị sao chép vào access log, nhưng kết nối internet của người dùng luôn dùng HTTPS. Rủi ro replay còn không?

> Có. Rò rỉ xảy ra tại hệ thống log; HTTPS không loại bỏ khả năng dùng lại bí mật đã bị lộ.

**Tình huống D:** Token được ràng buộc với khóa DPoP, attacker chỉ lấy được chuỗi access token. Rủi ro thay đổi thế nào?

> Nếu Resource Server thực thi đúng cơ chế ràng buộc, attacker không có private key/proof hợp lệ thường không thể dùng token chỉ bằng việc phát lại chuỗi access token.

## 16. Tài liệu tham khảo

- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): định nghĩa bearer token, cách trình bày qua HTTP và bảo vệ token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): hướng dẫn chống token leakage, replay, giới hạn audience/quyền và sender-constrained token.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): gắn access token với chứng chỉ mTLS.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): ràng buộc access token với cặp khóa và proof theo request.
- [Spring Security — OAuth 2.0 Bearer Tokens (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html): vị trí lấy bearer token và tùy chỉnh resolver.
- [Spring Security — JWT Resource Server (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác thực JWT và mapping scope.
- [Spring Security — Opaque Token Resource Server (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection cho access token.

Thông điệp cần giữ khi thiết kế Resource Server: **bearer token là một credential có thể sử dụng lại nếu bị lộ**. Các kiểm tra issuer, audience, scope, hạn dùng và quyền dữ liệu giúp giới hạn điều token có thể làm; các biện pháp bảo vệ bí mật và sender constraint giúp giảm khả năng người khác sử dụng token ngoài ý muốn.
