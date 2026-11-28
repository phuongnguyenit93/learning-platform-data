# Giới hạn exposure, quyền truy cập và CSRF cho từng endpoint quản trị

Spring Cloud Config Server và các Config Client có nhiều endpoint phục vụ vận hành: đọc cấu hình, mã hóa/giải mã secret, refresh Environment, phát tán sự kiện qua Bus và nhận webhook từ Git. Các endpoint này có mức độ nhạy cảm khác nhau. Nếu chỉ bật toàn bộ endpoint rồi yêu cầu mọi người dùng chung một tài khoản quản trị, một lỗi cấu hình hoặc một credential bị lộ có thể cho phép người gọi đọc secret, giải mã dữ liệu hoặc refresh toàn bộ hệ thống.

Bảo vệ đúng cần tách ba lớp. **Exposure** xác định endpoint nào được publish qua HTTP. **Authentication và authorization** xác định ai được gọi endpoint nào, bằng method nào và trong phạm vi nào. **CSRF** bảo vệ các request thay đổi trạng thái khi trình duyệt tự động gửi thông tin xác thực như session cookie. Ba lớp này bổ sung cho nhau; bật exposure không đồng nghĩa endpoint được phép truy cập, còn xác thực thành công không tự động chứng minh request POST an toàn trước CSRF.

Bài học này hướng dẫn thiết kế allowlist endpoint, phân quyền theo đường dẫn và HTTP method, tách SecurityFilterChain cho API quản trị, áp dụng CSRF phù hợp với loại credential, bảo vệ webhook và kiểm thử ma trận truy cập.

Sau bài học, bạn có thể:

- Phân biệt endpoint exposure với authentication và authorization.
- Chỉ expose endpoint quản trị thật sự cần thiết.
- Tạo quyền riêng cho đọc cấu hình, mã hóa, giải mã, refresh và webhook.
- Giới hạn quyền theo HTTP method và destination path.
- Tổ chức SecurityFilterChain riêng cho API quản trị và giao diện trình duyệt.
- Hiểu khi nào cần giữ CSRF và khi nào có thể miễn CSRF cho API dùng bearer token.
- Bảo vệ endpoint trên management port, mạng nội bộ và broker.
- Kiểm thử các trường hợp 401, 403, CSRF failure và truy cập vượt quyền.

## 1. Ba lớp bảo vệ endpoint

Một endpoint chỉ nên được truy cập khi cả chính sách publish và chính sách bảo vệ đều cho phép.

| Lớp | Câu hỏi | Cơ chế điển hình |
|---|---|---|
| Exposure | Endpoint có được publish qua HTTP không? | Actuator web exposure, route và network binding |
| Authentication | Người gọi là ai? | OAuth2/JWT, session login, mTLS hoặc service identity |
| Authorization | Danh tính đó được phép làm gì? | Role, authority, scope, method/path matcher |
| CSRF | Request có thể bị trình duyệt gửi ngoài ý muốn không? | CSRF token, cookie policy, API credential design |

Ví dụ, việc expose <code>refresh</code> trong Actuator chỉ khiến route có thể được phục vụ qua HTTP. Nó không có nghĩa mọi người đều được phép gọi <code>POST /actuator/refresh</code>. Tương tự, một tài khoản đã đăng nhập vẫn có thể bị từ chối nếu không có quyền refresh.

CSRF là một vấn đề khác: trình duyệt có thể tự gửi cookie phiên đăng nhập kèm request do một trang web độc hại kích hoạt. Kẻ tấn công không nhất thiết biết cookie hoặc đọc được response để khiến trình duyệt gửi request. Vì vậy, một endpoint POST có xác thực cookie cần kiểm tra CSRF token.

## 2. Phân loại endpoint trước khi mở quyền

Không phải mọi endpoint của Config Server đều có cùng mức độ rủi ro.

| Endpoint hoặc nhóm | Mục đích | Rủi ro chính | Chính sách khởi điểm |
|---|---|---|---|
| <code>GET /{application}/{profile}</code> và biến thể label | Trả Environment cho client | Lộ cấu hình hoặc secret đã giải mã | Chỉ danh tính client được đọc đúng phạm vi |
| <code>POST /encrypt</code> | Mã hóa plaintext | Bị lạm dụng tài nguyên hoặc mã hóa dữ liệu tùy ý | Chỉ quyền cấu hình/secret operator |
| <code>POST /decrypt</code> | Trả plaintext từ ciphertext | Lộ trực tiếp secret | Quyền rất hạn chế, audit riêng |
| <code>POST /actuator/refresh</code> | Refresh một client | Thay đổi runtime ngoài kế hoạch | Chỉ quyền refresh instance được phép |
| <code>POST /actuator/busrefresh</code> | Phát refresh qua Bus | Tác động nhiều instance | Quyền vận hành Bus, kiểm soát phạm vi |
| <code>POST /actuator/busenv</code> | Phát thay đổi Environment | Thay đổi cấu hình runtime | Quyền cao, audit và giới hạn destination |
| <code>POST /monitor</code> | Nhận webhook repository | Kích hoạt refresh từ nguồn bên ngoài | Xác minh chữ ký và chống replay |
| <code>GET /actuator/env</code> | Xem Environment | Lộ property source và giá trị nhạy cảm | Không expose công khai; giới hạn quyền |
| <code>GET /actuator/configprops</code> | Xem cấu hình đã bind | Lộ cấu trúc và giá trị ứng dụng | Không expose công khai; giới hạn quyền |
| <code>GET /actuator/health</code> | Kiểm tra sức khỏe | Lộ chi tiết dependency nếu cấu hình quá rộng | Có thể công khai trạng thái tổng quát, ẩn details |

Bảng này là chính sách khởi điểm. Endpoint thực tế phụ thuộc dependency và phiên bản. Hãy kiểm tra route được đăng ký trong ứng dụng thay vì giả định mọi ứng dụng đều có đủ endpoint.

## 3. Exposure của Actuator: chỉ công khai endpoint cần dùng

Spring Boot Actuator có cơ chế quản lý endpoint riêng. Có thể dùng allowlist trong <code>application.yml</code>:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Đây là cấu hình tối thiểu thường phù hợp với ứng dụng cần health check và thông tin cơ bản. Nếu một Config Client cần refresh qua HTTP, chỉ thêm endpoint đó khi quy trình vận hành thực sự sử dụng:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh
~~~

Với ứng dụng tham gia Spring Cloud Bus, có thể thêm <code>busrefresh</code> hoặc <code>busenv</code> theo nhu cầu đã xác định:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,busrefresh
~~~

Không cần expose <code>env</code>, <code>configprops</code>, <code>beans</code>, <code>conditions</code>, <code>mappings</code> hoặc <code>threaddump</code> chỉ vì chúng có sẵn. Các endpoint chẩn đoán có thể tiết lộ cấu trúc nội bộ, tên tài nguyên, thông tin kết nối hoặc giá trị cấu hình.

### Tránh wildcard exposure

Không nên dùng cấu hình rộng như:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
~~~

Wildcard làm mọi endpoint web có thể expose theo cấu hình và dependency hiện tại. Khi thêm starter hoặc nâng cấp dependency, phạm vi endpoint công khai có thể mở rộng mà người vận hành không nhận ra.

Nếu buộc phải dùng wildcard trong môi trường chẩn đoán tạm thời, cần có authorization chặt, giới hạn mạng, thời gian bật cụ thể và bước xác nhận tắt lại. Production nên ưu tiên allowlist.

### Exclude khi cần chặn rõ ràng

Actuator hỗ trợ khai báo endpoint bị loại khỏi web exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh
        exclude: env,configprops
~~~

Chỉ định tên endpoint ID, không phải URL đầy đủ. Quy tắc include/exclude và endpoint access có thể thay đổi theo phiên bản Spring Boot; kiểm tra tài liệu của phiên bản đang chạy.

## 4. Endpoint không thuộc Actuator cần được bảo vệ riêng

Một nhầm lẫn thường gặp là nghĩ rằng <code>management.endpoints.web.exposure</code> kiểm soát mọi route quản trị của Config Server.

Các route <code>/encrypt</code>, <code>/decrypt</code> và <code>/monitor</code> không phải Actuator endpoint thông thường. Việc include hoặc exclude endpoint Actuator không tự bảo vệ các route này.

Ví dụ:

- <code>/encrypt</code> và <code>/decrypt</code> thuộc nhóm endpoint mã hóa của Spring Cloud Config.
- <code>/monitor</code> thuộc nhóm nhận notification từ repository monitor.
- <code>/actuator/refresh</code> và <code>/actuator/busrefresh</code> là endpoint quản trị được expose qua Actuator.

Hãy lập danh sách route thực tế của ứng dụng, sau đó viết rule bảo mật cho từng nhóm. Không dùng một rule permit-all cho toàn bộ <code>/</code> hoặc <code>/actuator/**</code>.

## 5. Tách SecurityFilterChain cho API quản trị

Spring Security cho phép tạo nhiều <code>SecurityFilterChain</code> với thứ tự và matcher riêng. Cách này giúp API quản trị có chính sách rõ ràng, độc lập với giao diện web hoặc endpoint đọc cấu hình.

Ví dụ dưới đây minh họa một API quản trị chỉ nhận OAuth2 bearer JWT. Các authority được ánh xạ thành scope như <code>SCOPE_config.encrypt</code> hoặc <code>SCOPE_config.refresh</code> theo cấu hình resource server:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain configAdminApi(HttpSecurity http) throws Exception {
        http
            .securityMatcher(
                "/encrypt",
                "/decrypt",
                "/actuator/refresh",
                "/actuator/busrefresh",
                "/actuator/busrefresh/**",
                "/actuator/busenv",
                "/actuator/busenv/**"
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/encrypt")
                    .hasAuthority("SCOPE_config.encrypt")
                .requestMatchers(HttpMethod.POST, "/decrypt")
                    .hasAuthority("SCOPE_config.decrypt")
                .requestMatchers(HttpMethod.POST, "/actuator/refresh")
                    .hasAuthority("SCOPE_config.refresh")
                .requestMatchers(
                    HttpMethod.POST,
                    "/actuator/busrefresh",
                    "/actuator/busrefresh/**"
                ).hasAuthority("SCOPE_config.bus")
                .requestMatchers(
                    HttpMethod.POST,
                    "/actuator/busenv",
                    "/actuator/busenv/**"
                ).hasAuthority("SCOPE_config.environment.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth -> oauth.jwt(
                Customizer.withDefaults()
            ))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            // Chỉ an toàn khi chain này nhận bearer token tường minh,
            // không dùng session cookie, HTTP Basic hay browser credential.
            .csrf(csrf -> csrf.disable());

        return http.build();
    }
}
~~~

Đây là ví dụ cho các route dùng chung management base path mặc định. Nếu thay <code>management.endpoints.web.base-path</code>, thêm context path hoặc chạy Actuator trên cổng riêng, matcher phải được điều chỉnh cho đúng route thực tế. Có thể dùng <code>EndpointRequest</code> của Spring Boot để match Actuator endpoint theo ID thay vì hardcode path.

Các điểm cần giữ:

- <code>@Order(1)</code> đặt chain chuyên biệt trước chain tổng quát.
- <code>securityMatcher</code> giới hạn toàn bộ chain vào các route quản trị được liệt kê.
- <code>requestMatchers</code> phân quyền theo HTTP method và path.
- <code>anyRequest().denyAll()</code> chặn route ngoài ma trận đã khai báo trong chain này.
- Các scope tách riêng mã hóa, giải mã, refresh và thay đổi Environment.
- CSRF chỉ được tắt vì ví dụ này dành riêng cho API stateless nhận bearer token, không chấp nhận credential tự động gửi từ trình duyệt.

Tên authority thực tế phụ thuộc claim trong JWT và converter của resource server. Nếu hệ thống dùng role thay vì scope, hãy ánh xạ rõ ràng và không cấp chung một quyền admin cho mọi endpoint.

## 6. Quy tắc deny-by-default và thứ tự matcher

Trong authorization, rule cụ thể cần được đánh giá trước rule tổng quát. Ví dụ:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.POST, "/actuator/refresh")
        .hasAuthority("SCOPE_config.refresh")
    .requestMatchers(HttpMethod.GET, "/actuator/health")
        .permitAll()
    .anyRequest().denyAll()
)
~~~

Không đặt <code>anyRequest().permitAll()</code> trước các rule cụ thể. Rule tổng quát ở cuối giúp route mới được thêm vào ứng dụng không vô tình trở thành endpoint công khai.

Cũng cần phân biệt:

- <code>securityMatcher(...)</code>: chọn những request thuộc SecurityFilterChain nào.
- <code>requestMatchers(...)</code>: áp dụng authorization rule cho request bên trong chain đã chọn.

Nếu không có chain nào match, request có thể rơi vào chain khác hoặc cấu hình bảo mật mặc định. Vì vậy, cần có fallback chain bảo vệ các route còn lại.

Ví dụ một fallback chain cho ứng dụng có giao diện trình duyệt:

~~~java
@Bean
@Order(2)
SecurityFilterChain browserAndConfigRead(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/assets/**").permitAll()
            .requestMatchers(HttpMethod.GET, "/actuator/health")
                .permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .csrf(Customizer.withDefaults());

    return http.build();
}
~~~

Chain fallback này chỉ là minh họa. Ứng dụng Config Server cần bổ sung quyền đọc cấu hình theo danh tính client và phạm vi application/profile. Không dùng <code>authenticated()</code> như chính sách cuối cùng nếu tất cả client đã đăng nhập đều không nên đọc mọi application.

## 7. Phân quyền theo từng endpoint và HTTP method

Một danh tính có quyền đọc cấu hình không nhất thiết có quyền giải mã secret hoặc refresh toàn hệ thống.

Một ma trận quyền mẫu:

| Danh tính | Đọc Environment | Encrypt | Decrypt | Refresh client | Bus refresh | Webhook |
|---|---:|---:|---:|---:|---:|---:|
| Config Client | Có, đúng app/profile | Không | Không | Không | Không | Không |
| Config Operator | Theo phạm vi vận hành | Có | Theo phê duyệt | Có | Theo phê duyệt | Không |
| Secret Custodian | Không mặc định | Có | Có, rất hạn chế | Không | Không | Không |
| Release Automation | Theo ứng dụng triển khai | Không | Không | Có theo kế hoạch | Có theo allowlist | Không |
| Git Provider | Không | Không | Không | Không | Không | Chỉ gửi webhook hợp lệ |
| Read-only Auditor | Có thể xem metadata đã mask | Không | Không | Không | Không | Không |

### Tách encrypt và decrypt

<code>/decrypt</code> trả plaintext nên có rủi ro cao hơn <code>/encrypt</code>. Nếu mọi người có quyền encrypt cũng được quyền decrypt, một credential dùng cho pipeline có thể trở thành credential đọc secret. Hãy cấp quyền decrypt cho nhóm nhỏ, yêu cầu audit và có thể yêu cầu phê duyệt bổ sung.

### Tách refresh cục bộ và refresh qua Bus

<code>/actuator/refresh</code> tác động lên instance nhận request. <code>/actuator/busrefresh</code> phát sự kiện có thể tác động nhiều instance. Không cấp quyền Bus chỉ vì một service account cần refresh một canary.

Nếu endpoint hỗ trợ destination path, hãy giới hạn destination trong automation và ghi lại pattern được sử dụng. Quyền gọi Bus broadcast toàn hệ thống cần được kiểm soát chặt hơn quyền target một instance.

### Bảo vệ cả endpoint đọc cấu hình

Config Server trả Environment có thể chứa secret đã giải mã. Cần xác thực Config Client và giới hạn application/profile/label mà client được phép đọc. Không cho mọi client đọc mọi đường dẫn chỉ vì chúng đều nằm trong mạng nội bộ.

## 8. CSRF bảo vệ điều gì?

CSRF (Cross-Site Request Forgery) xảy ra khi trình duyệt của người dùng đã có thông tin xác thực tự động gửi kèm request tới một ứng dụng, trong khi request được kích hoạt từ một origin khác.

Ví dụ:

1. Người vận hành đăng nhập vào trang quản trị Config Server và có session cookie.
2. Người đó mở một trang web bên ngoài do kẻ tấn công kiểm soát.
3. Trang đó cố gửi POST tới endpoint refresh của Config Server.
4. Trình duyệt có thể tự đính kèm cookie phiên nếu cookie và chính sách trình duyệt cho phép.
5. Nếu server chỉ kiểm tra session mà không yêu cầu CSRF token, request có thể được thực hiện dưới quyền của người vận hành.

Kẻ tấn công không cần đọc response. Mục tiêu của CSRF là khiến trình duyệt thực hiện hành động ngoài ý muốn.

Các endpoint thay đổi trạng thái như <code>POST /encrypt</code>, <code>POST /decrypt</code>, <code>POST /actuator/refresh</code>, <code>POST /actuator/busrefresh</code> và <code>POST /actuator/busenv</code> cần được đánh giá theo cách credential được trình duyệt gửi.

## 9. Khi nào giữ CSRF và khi nào có thể miễn CSRF?

Chính sách CSRF phải dựa trên cách xác thực thực tế, không dựa vào việc endpoint được gọi là API.

| Kiểu truy cập | Credential có thể tự được trình duyệt gửi? | Chính sách |
|---|---|---|
| Form login + session cookie | Có | Giữ CSRF và yêu cầu token cho request thay đổi trạng thái |
| Cookie-based API session | Có | Giữ CSRF |
| HTTP Basic | Trình duyệt có thể tự gửi credential đã lưu | Không mặc định tắt CSRF; đánh giá như credential ambient |
| OAuth2 bearer token gửi rõ trong Authorization header | Thông thường không tự gắn nếu token chỉ được ứng dụng client giữ và thêm vào header | Có thể miễn CSRF trong chain stateless chỉ nhận bearer token |
| mTLS từ browser | Trình duyệt có thể dùng client certificate theo cấu hình | Không tự xem là miễn CSRF; đánh giá khả năng browser tự xác thực |
| Webhook chữ ký HMAC từ Git provider | Không dùng session cookie của người vận hành | Có thể miễn CSRF riêng route webhook nếu bắt buộc xác minh chữ ký và chống replay |

### API dùng bearer token

Một API chỉ chấp nhận bearer token được client gắn tường minh vào header thường không dùng credential tự động của trình duyệt. Trong chain stateless dành riêng cho API đó, có thể tắt CSRF nếu:

- Không chấp nhận session cookie hoặc form login.
- Không dùng HTTP Basic như cơ chế thay thế.
- Token không được lưu trong cookie tự động gửi.
- CORS chỉ cho phép origin cần thiết nếu browser client được hỗ trợ.
- Authorization vẫn được kiểm tra cho từng endpoint.
- Không có route browser-based dùng chung chain.

Không tắt CSRF trên toàn ứng dụng chỉ vì một số endpoint dùng bearer token.

### Giao diện quản trị dùng session cookie

Nếu operator truy cập trang web bằng form login hoặc session cookie, hãy giữ CSRF. Với Spring Security, CSRF protection được bật mặc định cho các request không an toàn như POST, PUT, PATCH và DELETE. Form hoặc JavaScript client phải gửi token theo cơ chế repository/handler đã cấu hình.

Không thêm một rule miễn CSRF toàn cục cho các route quản trị chỉ để làm lệnh curl chạy thuận tiện. Lệnh curl có thể dùng bearer token trong API chain riêng hoặc gửi CSRF token và cookie hợp lệ khi kiểm thử session flow.

## 10. Không nhầm CSRF với CORS

CORS kiểm soát việc JavaScript từ origin khác có được đọc response hoặc thực hiện một số loại request hay không. CORS không thay thế CSRF protection.

Một request đơn giản có thể được trình duyệt gửi mà không cần preflight. Kể cả khi JavaScript không đọc được response do CORS, hành động phía server vẫn có thể đã xảy ra nếu cookie xác thực được gửi kèm.

Do đó:

- CORS allowlist giới hạn origin được phép tương tác theo chính sách cross-origin.
- CSRF token chứng minh request thay đổi trạng thái được tạo từ luồng ứng dụng có quyền.
- Authorization quyết định danh tính có được phép thực hiện hành động không.
- SameSite cookie là một lớp giảm rủi ro, không nên dùng thay cho toàn bộ CSRF policy nếu ứng dụng vẫn dựa vào cookie.

Không dùng <code>Access-Control-Allow-Origin: *</code> cùng credential. Chỉ cho phép origin cụ thể cần thiết và không phản chiếu origin tùy ý.

## 11. Bảo vệ webhook /monitor bằng chữ ký riêng

Git provider có thể gọi <code>POST /monitor</code> để thông báo repository đã thay đổi. Đây là request từ hệ thống bên ngoài, không phải thao tác trình duyệt của operator.

Một webhook chain riêng có thể miễn CSRF cho route này, nhưng phải xác thực chữ ký HMAC hoặc cơ chế signature tương ứng của provider:

- Xác minh chữ ký trên raw request body trước khi tin payload.
- Dùng secret webhook được lưu ngoài repository.
- So sánh chữ ký theo cách constant-time.
- Kiểm tra timestamp hoặc delivery ID để hạn chế replay.
- Từ chối payload sai định dạng hoặc repository không nằm trong allowlist.
- Audit delivery ID, repository, kết quả xác minh và thời điểm.
- Không log secret chữ ký hoặc toàn bộ payload nếu có thông tin nhạy cảm.

Miễn CSRF không có nghĩa webhook được phép anonymous. Chữ ký webhook là cơ chế xác thực riêng cho nguồn gửi. Nếu bỏ kiểm tra chữ ký và chỉ mở <code>/monitor</code> ra Internet, bất kỳ ai có thể giả mạo thông báo và kích hoạt công việc refresh.

Nếu route webhook dùng chung một chain với session-based admin, chỉ miễn CSRF cho đúng request POST của webhook sau khi filter xác minh chữ ký là bắt buộc. Ví dụ về matcher giới hạn theo method và path:

~~~java
RequestMatcher monitorPost = request ->
    "POST".equals(request.getMethod())
        && "/monitor".equals(request.getServletPath());

http.csrf(csrf -> csrf.ignoringRequestMatchers(monitorPost));
~~~

Đoạn trên chỉ loại request webhook khỏi kiểm tra CSRF. Nó **không** xác thực webhook. Filter xác minh HMAC, timestamp/delivery ID và repository allowlist vẫn phải chạy trước khi controller xử lý payload. Nếu chưa có lớp xác minh chữ ký bắt buộc, không miễn CSRF cho route này.

Nếu webhook dùng bearer token thay vì HMAC, kiểm tra token và audience/issuer theo chính sách identity provider. Không dùng cùng credential với tài khoản operator.

## 12. Giới hạn endpoint bằng management port và mạng nội bộ

Có thể tách Actuator sang cổng quản trị:

~~~yaml
management:
  server:
    port: 9001
    address: 0.0.0.0
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info,refresh
~~~

Trong container hoặc môi trường orchestrator, địa chỉ bind cần phù hợp với cách health probe và gateway nội bộ truy cập. Không bind loopback nếu probe chạy từ một container hoặc host khác mà cần truy cập qua network interface.

Tách cổng không thay thế authentication và authorization. Nếu cổng 9001 vẫn được publish ra Internet hoặc mọi pod đều truy cập không hạn chế, endpoint vẫn có thể bị lạm dụng.

Các lớp mạng nên kết hợp:

- Chỉ publish management port trong private network.
- Firewall hoặc network policy giới hạn nguồn truy cập.
- Gateway nội bộ yêu cầu identity và TLS.
- SecurityFilterChain vẫn xác thực và phân quyền.
- Audit mọi thao tác thay đổi trạng thái.

Với Config Server, có thể cân nhắc management port riêng và route quản trị chỉ truy cập qua mạng vận hành. Endpoint đọc cấu hình cho Config Client vẫn được bảo vệ theo cơ chế riêng.

## 13. Kiểm soát thông tin mà endpoint chẩn đoán trả về

Một endpoint GET không thay đổi trạng thái vẫn có thể tiết lộ dữ liệu nhạy cảm.

<code>/actuator/env</code> có thể cho biết property source, origin và giá trị cấu hình. <code>/actuator/configprops</code> có thể tiết lộ tên bean, prefix và các giá trị đã bind. Cần kiểm soát cả exposure lẫn cách hiển thị giá trị.

Ví dụ cấu hình hiển thị giá trị theo quyền xác thực, nếu phiên bản Spring Boot hỗ trợ:

~~~yaml
management:
  endpoint:
    env:
      show-values: when-authorized
    configprops:
      show-values: when-authorized
~~~

Trong môi trường không cần xem giá trị, ưu tiên <code>never</code>. Nếu cho phép hiển thị khi đã xác thực, role cần được giới hạn cho nhóm vận hành thích hợp. Tên thuộc tính và origin cũng có thể nhạy cảm, vì vậy vẫn cần authorization ngay cả khi value đã được mask.

Đối với health endpoint:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
~~~

Chỉ công khai trạng thái tổng quát nếu cần health probe bên ngoài. Không hiển thị thông tin kết nối database, broker hoặc downstream cho mọi người gọi.

Tên thuộc tính và tùy chọn hiển thị có thể khác theo phiên bản Spring Boot. Kiểm tra metadata và tài liệu phiên bản trước khi áp dụng.

## 14. Kiểm thử ma trận quyền truy cập

Sau khi cấu hình exposure và SecurityFilterChain, hãy kiểm tra bằng danh tính đại diện cho từng vai trò.

| Request | Danh tính | Kết quả mong đợi |
|---|---|---|
| GET health tổng quát | Anonymous | 200 nếu chính sách cho phép |
| GET health details | Anonymous | Details bị ẩn hoặc bị từ chối |
| GET Environment | Config Client đúng application | 200 trong phạm vi được cấp |
| GET Environment của application khác | Config Client không có quyền | 403 hoặc bị từ chối theo policy |
| POST encrypt | Secret operator có scope encrypt | Thành công |
| POST decrypt | Chỉ encrypt scope | 403 |
| POST decrypt | Secret custodian có scope decrypt | Thành công và được audit |
| POST refresh | Release automation có scope refresh | Thành công |
| POST busrefresh broadcast | Tài khoản chỉ có scope refresh cục bộ | 403 |
| POST busrefresh destination hẹp | Bus operator được phép | Thành công theo policy |
| POST refresh bằng session cookie, thiếu CSRF token | Operator đã đăng nhập | 403 |
| POST refresh bằng session cookie, có CSRF token và quyền | Operator được cấp quyền | Thành công |
| POST webhook sai chữ ký | Git provider giả mạo | 401/403 hoặc từ chối |
| POST webhook chữ ký hợp lệ nhưng delivery bị replay | Webhook đã xử lý | Bị từ chối hoặc deduplicate |

Mã trạng thái chính xác có thể phụ thuộc authentication entry point, exception handler và gateway. Điều quan trọng là hành vi: anonymous không thực hiện được, authenticated nhưng thiếu quyền bị từ chối, request thiếu CSRF token không thay đổi trạng thái, và danh tính đúng chỉ thao tác được trong phạm vi đã cấp.

### Kiểm thử bằng curl

Ví dụ gọi API bearer token với giá trị token giả:

~~~bash
curl --request POST \
  --header "Authorization: Bearer $CONFIG_OPERATOR_TOKEN" \
  --header "Content-Type: text/plain" \
  --data-binary "dummy-value-for-encryption-test" \
  https://config-admin.internal/encrypt
~~~

Không dùng token thật trong tài liệu, shell history dùng chung hoặc log CI. Khi kiểm thử, xác nhận cả trường hợp token thiếu scope:

~~~bash
curl --request POST \
  --header "Authorization: Bearer $READ_ONLY_TOKEN" \
  --header "Content-Type: text/plain" \
  --data-binary "dummy-value" \
  https://config-admin.internal/encrypt
~~~

Request thứ hai phải bị từ chối vì danh tính chỉ có quyền đọc.

## 15. Checklist trước khi mở endpoint quản trị

- [ ] Đã lập danh sách route thực tế theo dependency và phiên bản.
- [ ] Actuator dùng allowlist exposure, không expose wildcard.
- [ ] <code>/encrypt</code>, <code>/decrypt</code> và <code>/monitor</code> có rule riêng; không nhầm chúng với Actuator exposure.
- [ ] Endpoint đọc Environment chỉ cho Config Client đúng application/profile.
- [ ] <code>/decrypt</code> có quyền riêng và audit chặt hơn <code>/encrypt</code>.
- [ ] Refresh cục bộ và Bus refresh có authority riêng.
- [ ] Authorization kiểm tra cả HTTP method và path/destination.
- [ ] Có fallback deny-by-default cho route quản trị không được khai báo.
- [ ] SecurityFilterChain có thứ tự và matcher không chồng lấn ngoài dự kiến.
- [ ] Session/cookie-based admin giữ CSRF token cho POST/PUT/PATCH/DELETE.
- [ ] CSRF chỉ được miễn trong API chain stateless không nhận credential tự động gửi từ browser.
- [ ] HTTP Basic và mTLS không bị coi mặc định là miễn CSRF.
- [ ] Webhook /monitor xác minh chữ ký, timestamp hoặc delivery ID và chống replay.
- [ ] CORS allowlist không được dùng thay cho CSRF.
- [ ] Management port nằm trong mạng phù hợp và vẫn có authentication/authorization.
- [ ] Env/configprops/health details được mask hoặc giới hạn theo quyền.
- [ ] Đã kiểm thử anonymous, sai scope, thiếu CSRF, đúng quyền và truy cập sai phạm vi.
- [ ] Log và audit không chứa password, token, plaintext hoặc key.

Exposure, authorization và CSRF giải quyết ba lớp rủi ro khác nhau. Hãy bắt đầu bằng allowlist endpoint nhỏ nhất, gắn quyền cụ thể theo method và path, giữ CSRF cho luồng xác thực dựa trên cookie, và chỉ miễn CSRF trong một API chain stateless có credential tường minh. Với Config Server, đặc biệt bảo vệ <code>/decrypt</code>, các endpoint refresh, webhook <code>/monitor</code> và endpoint đọc Environment; kiểm thử ma trận truy cập sau mỗi thay đổi để chắc chắn không có route quản trị nào được mở rộng quyền ngoài dự kiến.

