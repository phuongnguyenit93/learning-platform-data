# Access token, refresh token và vòng đời sử dụng

Trong một hệ thống sử dụng OAuth 2.0, ứng dụng thường cần gọi API thay mặt người dùng hoặc thay mặt chính ứng dụng. Thay vì liên tục gửi mật khẩu của người dùng tới từng API, hệ thống có thể cấp **access token** để truy cập tài nguyên và, nếu chính sách cho phép, **refresh token** để xin access token mới khi access token cũ hết hạn.

Hai loại token này có nhiệm vụ khác nhau:

- **Access token**: credential mà client trình cho **resource server** (API) để yêu cầu truy cập tài nguyên được cấp quyền.
- **Refresh token**: credential mà client trình cho **authorization server** (máy chủ cấp quyền) tại **token endpoint** để nhận access token mới; refresh token **không được gửi đến API tài nguyên**.
- Việc có refresh token là **tùy chính sách** của authorization server; không phải mọi luồng OAuth đều cấp refresh token.

Bài học giải thích từ khái niệm, cơ chế cấp và làm mới, thời hạn, thu hồi, đến cách Spring Security xử lý token. Các giá trị token trong ví dụ đều là chuỗi giả lập, không thể dùng để đăng nhập hệ thống thật.

## 1. Token nằm ở đâu trong hệ thống?

Các vai trò phổ biến trong OAuth 2.0:

| Vai trò | Trách nhiệm |
|---|---|
| **Resource owner** | Chủ thể sở hữu/quyết định cấp quyền truy cập tài nguyên, thường là người dùng |
| **Client** | Ứng dụng cần truy cập API, ví dụ web app, mobile app, backend service |
| **Authorization server** | Xác thực/cấp quyền theo luồng phù hợp, phát hành và quản lý token |
| **Resource server** | API nhận access token và quyết định có chấp nhận request hay không |

Ví dụ luồng đơn giản:

```text
    Người dùng
        |
        | đăng nhập / cấp quyền theo luồng phù hợp
        v
  Client (web/mobile/backend) <----> Authorization Server
        |                            cấp access token
        |                            và có thể cấp refresh token
        |
        | Authorization: Bearer <access_token>
        v
  Resource Server (API) ----> kiểm tra token + quyền ---> tài nguyên

  Khi access token không còn dùng được:
  Client -- refresh_token --> Authorization Server
  Client <-- access_token mới và có thể refresh_token mới --
```

**Resource server không cần biết refresh token của client.** Client chỉ gửi access token đến API tương ứng. Trong luồng dùng authorization code, authorization server thường chỉ phát hành token sau khi client đã thực hiện trao đổi authorization code; với ứng dụng công khai như SPA/native, cần dùng PKCE và các biện pháp phù hợp. Không phải cứ đăng nhập bằng mật khẩu là tự động sinh hai token.

**OAuth 2.0 chủ yếu là khung ủy quyền**, không tự định nghĩa đầy đủ danh tính người dùng để đăng nhập ứng dụng. Nếu cần xác thực danh tính theo chuẩn OpenID Connect (OIDC), luồng có thể cấp thêm **ID token**; ID token có mục đích khác với access token và không được dùng thay access token để gọi API.

## 2. So sánh access token và refresh token

| Đặc điểm | Access token | Refresh token |
|---|---|---|
| Mục đích | Chứng minh quyền truy cập API trong phạm vi được cấp | Lấy access token mới từ authorization server |
| Nơi sử dụng | Resource server được token cho phép | Token endpoint của authorization server |
| Cách gửi thường gặp | Header `Authorization: Bearer ...` | Body request với `grant_type=refresh_token` qua TLS và xác thực client khi áp dụng |
| Thời hạn | Thường ngắn để giảm tác hại khi bị lộ | Thường dài hơn access token nhưng vẫn phải có chính sách hết hạn/thu hồi |
| Nội dung/định dạng | Có thể là JWT, opaque string hoặc định dạng khác | Thường là chuỗi opaque, nhưng định dạng là quyết định triển khai |
| Scope / audience | Phải phù hợp tài nguyên và hành động được phép | Bị ràng buộc với grant, client và phạm vi/resource đã được cấp |
| Khi bị lộ | Kẻ tấn công có thể truy cập API cho đến khi token bị vô hiệu/hết hiệu lực, trừ khi sender-constrained | Kẻ tấn công có thể xin access token mới nếu vượt qua các ràng buộc; hậu quả thường kéo dài hơn |
| Có bắt buộc? | Có khi API yêu cầu OAuth access token | Không, authorization server có thể từ chối cấp |

Một cách chọn thời hạn thường thấy là **access token vài phút**, **refresh token lâu hơn**. Đây là **ví dụ chiến lược**, không phải giá trị mặc định được chuẩn OAuth quy định; thời hạn thực tế tùy mức rủi ro, loại client, chính sách tổ chức và cơ chế bảo vệ/thu hồi.

**Access token không phải mật khẩu tài khoản**, nhưng một **bearer token** có giá trị gần giống chìa khóa tạm thời: ai sở hữu token còn hiệu lực thường có thể dùng nó trong phạm vi token cho phép. Vì vậy token cũng là bí mật cần bảo vệ.

## 3. Vòng đời đầy đủ từ lúc cấp đến khi hết hiệu lực

Có thể chia vòng đời thành các trạng thái sau:

1. **Chưa cấp quyền**: client chưa có token phù hợp cho API.
2. **Cấp quyền và phát hành**: authorization server xác nhận grant hợp lệ, phát hành access token và có thể phát hành refresh token.
3. **Đang sử dụng**: client gắn access token vào request API; resource server kiểm tra tính hợp lệ, audience, scope/quyền và chính sách áp dụng.
4. **Gần hết hạn hoặc đã hết hạn**: client quyết định xin token mới; nếu có refresh token hợp lệ thì gửi nó đến token endpoint.
5. **Làm mới (refresh)**: authorization server kiểm tra refresh token và ràng buộc client/grant; nếu được phép sẽ cấp access token mới, có thể đồng thời **rotate** refresh token.
6. **Hết hạn/thu hồi/không hợp lệ**: khi không thể refresh, client cần thực hiện lại luồng ủy quyền hoặc đăng nhập thích hợp; không được dùng token lỗi vô hạn.
7. **Đăng xuất/ngắt cấp quyền**: client xóa credential cục bộ, phối hợp thu hồi token/grant ở authorization server theo chính sách hệ thống; cần xem tác động tới access token đang tồn tại.

Hai đồng hồ quan trọng thường độc lập: **thời gian sống của access token** và **thời gian sống/không hoạt động của refresh token**. Đừng coi việc access token hết hạn là người dùng đã bị đăng xuất; refresh token vẫn có thể xin quyền truy cập mới mà không cần bắt người dùng nhập lại thông tin.

## 4. Nhận token: đọc đúng response

Ví dụ response thành công từ token endpoint sau một luồng ủy quyền hợp lệ:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 300,
  "refresh_token": "EXAMPLE_REFRESH_TOKEN",
  "scope": "orders.read"
}
```

Các giá trị `EXAMPLE_...` chỉ là nhãn minh họa, không phải token có thể sử dụng. `expires_in: 300` nghĩa là access token có thời gian tồn tại **300 giây kể từ thời điểm phát hành response theo cách server quy định**. Trong hệ thống thực, client nên lưu thời điểm hết hạn thích hợp và xử lý sai lệch đồng hồ/network delay thay vì chỉ so sánh máy móc một con số.

Ý nghĩa các trường:

- `access_token`: giá trị credential dùng để gọi API.
- `token_type`: cách sử dụng token; giá trị phổ biến là `Bearer`.
- `expires_in`: số giây token còn hiệu lực theo thông tin authorization server cấp.
- `refresh_token`: tùy chọn, chỉ xuất hiện khi authorization server cấp.
- `scope`: phạm vi quyền được cấp; có thể bị giới hạn hơn quyền client đề nghị.

**Lưu ý:** Không phải mọi response đều có `refresh_token`, và access token không nhất thiết là JWT. Nếu một hệ thống có nhiều API, token được cấp riêng cho audience/resource nào thì chỉ được gửi tới tài nguyên được phép tương ứng.

## 5. Gọi API bằng access token

Ví dụ request của client:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
```

Resource server không được tin chỉ vì header có từ `Bearer`. Nó phải xác định token đúng issuer/nguồn tin cậy, còn hiệu lực, dành cho API này, thỏa các quyền cần thiết và chưa bị thu hồi nếu hệ thống có cơ chế kiểm tra thu hồi.

Phản hồi có thể là:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Khi request thiếu token hoặc token không hợp lệ/hết hạn, API thường trả **401**. Nếu token hợp lệ nhưng thiếu quyền cần cho tài nguyên, API thường trả **403**; tùy triển khai có thể kèm `WWW-Authenticate: Bearer error="insufficient_scope"`. Các ví dụ lỗi này chỉ diễn tả trường hợp phổ biến, không đảm bảo mọi framework luôn trả cùng response body.

**Không gửi access token trong URL query** khi có thể dùng header; query dễ lọt vào log, browser history, proxy và analytics. Dùng HTTPS với xác minh chứng chỉ đúng cách và không để lộ Authorization header trong telemetry.

### Token còn hiệu lực có đồng nghĩa đủ quyền?

Không. Cần tách hai bước:

1. **Authentication/token validation**: token là credential được chấp nhận theo quy tắc hệ thống.
2. **Authorization**: token và chủ thể liên quan có quyền thực hiện thao tác cụ thể không.

Ví dụ access token chỉ có `orders.read` có thể gọi `GET /api/orders` nhưng không mặc nhiên được gọi `DELETE /api/orders/42`. Resource server cần kiểm tra quyền và kiểm soát truy cập ở cấp tài nguyên, không chỉ xem token có chữ ký hợp lệ.

## 6. JWT và opaque token: định dạng khác nhiệm vụ

**JWT access token** thường gồm ba phần `header.payload.signature` được mã hóa dạng Base64URL. Khi dùng dạng JWT ký số (JWS), resource server có thể xác minh chữ ký và các claim như:

- `iss` (issuer): đơn vị phát hành.
- `sub` (subject): chủ thể mà token nói tới; không mặc nhiên đồng nhất với quyền ở mọi API.
- `aud` (audience): tài nguyên/người nhận mà token hướng tới.
- `exp` (expiration): thời điểm hết hiệu lực.
- `nbf` (not before): thời điểm bắt đầu có hiệu lực nếu có.
- `scope` / `scp`: quyền được cấp theo quy ước authorization server.

JWT có chữ ký **không phải JWT đã mã hóa bí mật**: phần payload của JWT ký số thông thường có thể được decode bởi bất kỳ ai nhận được token. Do đó không đưa mật khẩu hoặc dữ liệu nhạy cảm không cần thiết vào claim, và không chỉ `decode` rồi tin vào nội dung. Phải **xác minh chữ ký, thuật toán phù hợp, issuer/audience, thời gian và quyền**.

**Opaque access token** là chuỗi không mang cấu trúc công khai hữu ích cho API. Resource server thường cần cơ chế tra cứu/introspection hoặc tích hợp dịch vụ kiểm tra phù hợp để xác định token có hiệu lực và phạm vi quyền. Không suy ra rằng token opaque an toàn hơn JWT chỉ vì không đọc được nội dung; cả hai đều là credentials phải được bảo vệ.

**Refresh token có thể có định dạng bất kỳ**, nhưng client không nên đọc/giải mã để tự suy ra quyền hoặc thời hạn. Hãy xem nó là chuỗi bí mật và tuân thủ response/chính sách từ authorization server.

## 7. Refresh token hoạt động thế nào?

Khi access token sắp hết hạn hoặc không còn được chấp nhận vì hết hạn, client có thể yêu cầu token mới nếu được cấp refresh token. Request ví dụ theo OAuth 2.0:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=EXAMPLE_REFRESH_TOKEN
```

`/oauth2/token` là đường dẫn minh họa; endpoint thật do authorization server công bố/cấu hình. **Confidential client** thường còn phải xác thực client tại token endpoint, ví dụ bằng cơ chế client authentication đã thỏa thuận; `Authorization` của client authentication nếu có **không phải** HTTP Bearer access token gửi đến API. Public client không thể giữ bí mật client secret như backend, nên phải dùng chính sách bảo vệ refresh token phù hợp.

Authorization server sẽ kiểm tra ít nhất những điều thiết yếu theo loại client và chính sách cấp quyền:

1. Refresh token được chính máy chủ phát hành, còn hiệu lực, chưa bị hủy.
2. Token thuộc đúng client/grant, thỏa ràng buộc xác thực hoặc bằng chứng sở hữu khi có.
3. Scope/resource được đề nghị không vượt quyền đã được chủ thể cấp.
4. Không có dấu hiệu replay/đáng ngờ hoặc điều kiện chính sách khác khiến phải từ chối.

Nếu hợp lệ, response có thể là:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "access_token": "EXAMPLE_ACCESS_TOKEN_2",
  "token_type": "Bearer",
  "expires_in": 300,
  "refresh_token": "EXAMPLE_REFRESH_TOKEN_2",
  "scope": "orders.read"
}
```

Khi server cấp **refresh token mới** theo chính sách rotation, client phải lưu token mới một cách an toàn và **ngừng dùng token cũ**. Response cũng có thể không chứa refresh token mới trong các hệ thống có chính sách khác; không tự giả định cứ refresh là luôn có rotation.

**Refresh token tuyệt đối không gửi vào `Authorization: Bearer` khi gọi resource server.** Access token hết hạn thì dùng refresh token với **authorization server**, không gửi cả hai token tới API để “thử token nào đúng”.

## 8. Ví dụ thời gian: hai vòng đời không giống nhau

Giả sử một ứng dụng được cấp:

- Access token `A1` có thời gian sử dụng **5 phút**.
- Refresh token `R1` có chính sách hết hạn **7 ngày**; có thể ngắn hơn do inactivity, thu hồi hoặc rủi ro.
- Authorization server bật **refresh token rotation**.

Trình tự giả định:

| Thời điểm | Sự kiện | Hệ quả |
|---|---|---|
| 10:00 | Cấp `A1` và `R1` | Client gọi API bằng `A1` |
| 10:04 | Gọi API hợp lệ, đủ quyền | `A1` còn được dùng theo thời hạn và chính sách |
| 10:05 | `A1` hết hạn | API từ chối `A1` nếu không còn hợp lệ; `R1` có thể vẫn dùng được |
| 10:06 | Client gửi `R1` đến token endpoint | Nếu hợp lệ, server cấp `A2` và `R2`, vô hiệu `R1` |
| 10:07 | Client gọi API bằng `A2` | Hoạt động nếu `A2` hợp lệ và đủ quyền |
| 10:08 | Gửi lại `R1` cũ | Bị từ chối; theo chính sách phát hiện replay, phiên/grant có thể bị thu hồi thêm |

Đây là một chính sách minh họa; TTL **không phải chuẩn bắt buộc**. Trong trường hợp rotation, việc vô hiệu `R1` **không tự động khiến `A1` bị vô hiệu** nếu access token cũ còn hiệu lực và hệ thống không có cơ chế thu hồi access token tương ứng. Việc nhận `A2` cũng không tự động tạo thêm quyền so với grant ban đầu.

Client có thể refresh **trước** khi access token hết hạn để tránh request thất bại, ví dụ khi còn vài chục giây. Không được dựa vào “đã đến phút thứ năm” mà bỏ qua clock skew, network delay, token bị thu hồi sớm, hoặc `nbf`/chính sách riêng.

## 9. Refresh token rotation và chống dùng lại token bị đánh cắp

Refresh token thường có thời hạn lâu hơn nên có giá trị lớn với kẻ tấn công. Một biện pháp quan trọng là **rotation**:

```text
Lần cấp đầu:        Access A1  + Refresh R1
Refresh bằng R1:    Access A2  + Refresh R2  (R1 hết hiệu lực)
Refresh bằng R2:    Access A3  + Refresh R3  (R2 hết hiệu lực)
Dùng lại R1/R2:     Bị phát hiện hoặc từ chối theo chính sách server
```

Authorization server lưu hoặc suy ra quan hệ giữa các token thuộc cùng grant/family để phát hiện dùng lại token đã bị thay. Nếu `R1` bị đánh cắp, khi kẻ tấn công và client hợp pháp cùng cố sử dụng nó, ít nhất một bên có thể gửi token đã bị vô hiệu. Server có thể phát hiện khả năng rò rỉ và thu hồi refresh token đang còn hiệu lực trong family. Nó **không tự biết chắc ai là kẻ tấn công**.

Theo **RFC 9700 (OAuth 2.0 Security Best Current Practice)**, nếu cấp refresh token cho **public client**, authorization server phải dùng **refresh token rotation hoặc sender-constrained refresh token** để phát hiện replay. Sender-constrained token ràng buộc việc sử dụng với bằng chứng mật mã của client, chẳng hạn DPoP hoặc mTLS trong những mô hình được hỗ trợ.

**Đừng hiểu rotation là hết nguy cơ:** Nếu kẻ tấn công đánh cắp refresh token mới nhất và dùng trước, họ vẫn có thể lấy access token mới cho đến khi hệ thống phát hiện/thu hồi. Cần thêm HTTPS, kho lưu bí mật an toàn, giảm phạm vi, expiration/inactivity policy, phát hiện sự kiện bất thường và xử lý khi mất thiết bị/đổi mật khẩu.

### Tránh refresh đồng thời gây nhầm là replay

Nhiều tab hoặc nhiều HTTP request cùng phát hiện `A1` hết hạn có thể gửi `R1` **hai lần gần như cùng lúc**. Nếu server dùng one-time rotation, một request thành công nhận `R2`, request kia dùng lại `R1` có thể bị từ chối hoặc kích hoạt cơ chế phát hiện reuse.

Trong client, nên dùng cơ chế **single-flight/đồng bộ hóa refresh** theo phiên hoặc thiết bị: nhiều request cùng chờ kết quả của một lần refresh đang chạy, sau đó nhận chung access token mới. Khi có nhiều tab, cần giải pháp phối hợp cập nhật token an toàn theo kiến trúc; đừng vô hiệu hóa phát hiện reuse trên server chỉ để “chữa” lỗi race.

Nếu refresh thất bại với lỗi như `invalid_grant`, không lặp vô hạn cùng refresh token. Hãy xóa trạng thái token không còn hợp lệ, phân biệt lỗi mạng tạm thời với grant đã bị thu hồi, rồi yêu cầu luồng cấp quyền mới khi cần.

## 10. Hết hạn, thu hồi và đăng xuất có khác nhau không?

**Expiration**: Token vượt quá thời hạn hoặc chính sách hợp lệ. JWT có thể chứa `exp`; opaque token thường được kiểm tra dựa trên metadata server-side. Một token có thể bị từ chối **trước thời gian hết hạn** do thu hồi, thay đổi chính sách, không hợp audience hoặc ràng buộc sender không khớp.

**Revocation**: Authorization server chủ động vô hiệu hóa token/grant theo yêu cầu hoặc sự kiện bảo mật. OAuth 2.0 Token Revocation (RFC 7009) định nghĩa một endpoint để client yêu cầu thu hồi; việc thu hồi refresh token có thể ảnh hưởng token liên quan tùy chính sách và khả năng của server.

**Logout**: Ứng dụng kết thúc phiên sử dụng ở client và, khi cần, thực hiện logout/revocation tại authorization server hoặc identity provider. Xóa token khỏi bộ nhớ client chỉ ngăn **client đó** gửi token trong tương lai; không tự làm một access token đã rò rỉ mất hiệu lực ở các nơi khác.

Trường hợp **JWT access token tự xác minh (self-contained)**: Resource server chỉ kiểm chữ ký/claim tại chỗ có thể tiếp tục chấp nhận token đã phát hành cho tới lúc hết hạn nếu không có kiểm tra trạng thái thu hồi, danh sách chặn hoặc cơ chế tương đương. Do đó tuyên bố “logout là mọi access token lập tức vô hiệu” chỉ đúng khi kiến trúc thực sự hỗ trợ.

Nếu cần thu hồi gần như tức thời, có thể cân nhắc opaque token + introspection/trạng thái server-side, kiểm tra revocation, thời hạn access token ngắn hoặc giải pháp khác. Mỗi lựa chọn có chi phí độ trễ, tính sẵn sàng và quản lý trạng thái.

### Phân biệt với cookie session

Cookie phiên thường mang Session ID để server tra trạng thái phiên; refresh token là credential dùng để **xin access token mới**. Một ứng dụng web có thể dùng mô hình Backend-for-Frontend (BFF) giữ token ở server và cho browser dùng session cookie an toàn. Khi đó browser không trực tiếp giữ refresh token dù hệ thống vẫn dùng OAuth 2.0 bên dưới. Đừng đánh đồng logout session cookie với việc đã thu hồi toàn bộ token OAuth ở authorization server.

## 11. Ứng dụng Spring Security: resource server xác minh access token

Trong **Spring Security Servlet**, một API được cấu hình thành **OAuth2 Resource Server** có thể nhận Bearer access token ở header và xác minh JWT hoặc opaque token theo cơ chế đã chọn.

Ví dụ **cấu hình trong dự án Spring Boot có dependency Resource Server/JWT thích hợp**, với issuer có thật hỗ trợ metadata/JWKS:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test/issuer
```

Mã Java cấu hình endpoint cần scope `orders.read` (đoạn này thuộc **dự án Spring Boot/Spring Security**, không phải chương trình Java độc lập):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {
    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Với cấu hình JWT chuẩn, Spring Security Resource Server xác minh chữ ký và kiểm tra các claim thời gian như `exp`, `nbf`, cũng như `iss` phù hợp khi cấu hình issuer. Scope thường được chuyển thành authority có tiền tố `SCOPE_`. **Kiểm tra audience `aud` phải được bảo đảm bằng cấu hình/validator phù hợp** nếu API yêu cầu audience cụ thể; không cho rằng mọi cấu hình mặc định tự kiểm tra mọi trường theo chính sách doanh nghiệp.

Mã ví dụ có chủ đích chỉ minh họa **resource server dùng access token**. Nó **không phát hành access token hay refresh token**, không tạo token endpoint và không triển khai rotation. Những việc đó thuộc authorization server. Nếu ứng dụng Spring Security là **OAuth2 Client**, nó có thể quản lý `OAuth2AuthorizedClient` và refresh bằng cơ chế Client/AuthorizedClientManager phù hợp tùy cấu hình; không nên tự viết endpoint refresh trong resource server trừ khi kiến trúc thực sự yêu cầu và đã xác định rõ vai trò.

Nếu resource server được cấu hình kiểm tra opaque token, cơ chế thường là introspection tới authorization server thay vì xác minh JWT ký số tại chỗ. Cần lựa chọn chính xác theo **định dạng access token do issuer phát hành**.

## 12. Mô phỏng thời gian sống bằng Java 17

Ví dụ Java độc lập sau giúp quan sát vì sao một access token có thể hết hạn trong khi refresh token vẫn còn thời gian sử dụng. Nó **chỉ mô phỏng mốc thời gian và đổi tên token**, không tự tạo/định danh/xác minh credential thật; mọi token cố định trong bài đều không an toàn để dùng trong ứng dụng production.

Tạo tệp `TokenLifecycleDemo.java`:

```java
import java.time.Instant;

public class TokenLifecycleDemo {
    public static void main(String[] args) {
        Instant issuedAt = Instant.parse("2026-01-01T10:00:00Z");
        Instant accessExpiresAt = issuedAt.plusSeconds(5 * 60);
        Instant refreshExpiresAt = issuedAt.plusSeconds(7 * 24 * 60 * 60);
        Instant now = issuedAt.plusSeconds(6 * 60);

        String oldRefresh = "refresh-v1";
        String currentRefresh = oldRefresh;

        boolean accessExpired = !now.isBefore(accessExpiresAt);
        boolean refreshWithinTime = now.isBefore(refreshExpiresAt);

        System.out.println("Access expired: " + accessExpired);
        System.out.println("Refresh within lifetime: " + refreshWithinTime);

        if (accessExpired && refreshWithinTime
                && currentRefresh.equals(oldRefresh)) {
            String newAccess = "access-v2";
            currentRefresh = "refresh-v2";
            System.out.println("New access: " + newAccess);
            System.out.println(
                    "Old refresh still current: "
                    + currentRefresh.equals(oldRefresh));
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac TokenLifecycleDemo.java
java TokenLifecycleDemo
```

Kết quả chính xác:

```text
Access expired: true
Refresh within lifetime: true
New access: access-v2
Old refresh still current: false
```

Ở phút thứ sáu, access token được mô phỏng đã hết hạn (TTL năm phút), còn refresh token có TTL bảy ngày nên vẫn **nằm trong giới hạn thời gian**. Tuy nhiên, trong hệ thống thật **đủ thời gian chưa chứng minh refresh token hợp lệ**: authorization server còn phải kiểm tra client binding, chữ ký/ID/trạng thái, rotation, phạm vi, revocation và các chính sách bảo mật. Không dùng logic so sánh string trong ví dụ làm thuật toán xác thực thực tế.

## 13. Bảo vệ và lưu token theo từng loại client

Bảo vệ token cần xét cả nơi lưu, nơi gửi và phạm vi ảnh hưởng nếu bị đánh cắp:

| Môi trường | Cách tiếp cận phù hợp cần đánh giá | Lưu ý |
|---|---|---|
| **Backend/confidential client** | Lưu token ở hệ thống server kiểm soát, secret store/kho được bảo vệ, hạn chế quyền truy cập | Không log token, mã hóa/bảo vệ dữ liệu lưu trữ, kiểm soát secret client |
| **Web app dùng BFF** | Browser giữ cookie session `HttpOnly`, `Secure`, `SameSite` phù hợp; BFF giữ OAuth token phía server | Cookie vẫn có nguy cơ CSRF nếu browser tự gửi; triển khai biện pháp CSRF phù hợp |
| **SPA chạy hoàn toàn trên browser** | Tránh phơi token dài hạn trong JavaScript khi có thể; cân nhắc access token trong memory và thiết kế cấp lại phiên/refresh an toàn | XSS có thể đánh cắp token hoặc gọi API; `localStorage` không cung cấp rào cản khỏi script bị XSS |
| **Native/mobile app** | Dùng cơ chế lưu secret của OS khi thích hợp, authorization code + PKCE, quản lý thiết bị và thu hồi | Thiết bị bị xâm nhập vẫn có thể làm lộ credential |
| **Resource server/API** | Chỉ nhận và kiểm tra access token dành cho mình; hạn chế log và truyền token sang dịch vụ khác | Không yêu cầu refresh token của client để truy cập API |

Không có nơi lưu “an toàn tuyệt đối”. Cần chọn thiết kế phù hợp mô hình đe dọa; với token trong cookie, đặc tính `HttpOnly` chỉ ngăn JavaScript đọc cookie qua API thông thường, không ngăn script gây request được browser tự đính cookie và không thay cho bảo vệ CSRF/XSS.

Các nguyên tắc chung:

1. **HTTPS/TLS** cho mọi endpoint trao đổi token, bao gồm token endpoint, API, introspection/revocation và những đoạn mạng cần bảo vệ.
2. **Thời hạn ngắn, scope/audience tối thiểu** cho access token. Phân quyền thực tế do API kiểm tra.
3. **Refresh token rotation hoặc sender-constraining** đúng yêu cầu với public client khi được cấp refresh token; quản lý thời gian không hoạt động và thu hồi.
4. **Không log token/secret** trong URL, request/response dump, analytics, stack trace hoặc ảnh chụp lỗi. Che hoàn toàn các giá trị nhạy cảm trước khi chia sẻ.
5. **Không tự sinh token bằng chuỗi đoán được** hay tự quyết định thuật toán chữ ký. Dùng authorization server và thư viện bảo mật đã được kiểm chứng.
6. **Không dùng ID token thay access token** cho API, không gửi refresh token cho resource server.
7. **Chống race khi refresh** và xử lý đúng trường hợp lỗi, logout hoặc phiên bị vô hiệu từ xa.

## 14. Các lỗi thực tế và cách xử lý

| Biểu hiện | Nguyên nhân có thể gặp | Cách xử lý đúng hướng |
|---|---|---|
| API trả `401 invalid_token` | Access token hết hạn, sai issuer, chữ ký sai, sai audience hoặc đã bị thu hồi | Đọc thông báo lỗi, xác nhận cấu hình issuer/audience; chỉ refresh khi có điều kiện phù hợp |
| API trả `403` | Token hợp lệ nhưng thiếu scope/role hoặc quyền đối với đối tượng | Kiểm tra chính sách phân quyền; không tìm cách “bypass” bằng cách refresh liên tục |
| Token endpoint trả `invalid_grant` | Refresh token hết hạn, đã bị dùng/rotate, bị thu hồi hoặc không thuộc grant hợp lệ | Dừng dùng token lỗi, xóa trạng thái cũ, yêu cầu cấp quyền mới theo luồng chuẩn |
| Nhiều request cùng refresh | Có thể dùng lại cùng token cũ và kích hoạt phát hiện reuse | Hợp nhất request refresh, cập nhật token nguyên tử theo kiến trúc |
| Refresh thành công nhưng request tiếp tục 401 | Client vẫn gửi access token cũ, token mới sai audience/scope, hoặc server có chính sách khác | Đảm bảo cập nhật token vừa nhận, kiểm tra request và validator |
| Logout xong token cũ vẫn gọi được API | Client chỉ xóa token cục bộ, JWT cũ còn hiệu lực và API không có cơ chế revocation | Đánh giá cơ chế thu hồi, lifetime ngắn, introspection/denylist khi cần |
| Token bị lộ qua log | Gateway, tracing hoặc debug in `Authorization` | Ẩn/loại token khỏi log, thu hồi token bị ảnh hưởng và rà soát nguyên nhân |

**Lưu ý:** Refresh không phải cách chữa mọi lỗi `401`; token có thể sai issuer, audience hoặc đã bị thu hồi. Khi gặp lỗi xác thực lặp lại, client phải chặn vòng lặp tự động vô hạn và chuyển sang xử lý xác thực lại.

## 15. Câu hỏi tự kiểm tra

1. **Access token và refresh token được gửi đến cùng một API không?** Không. Access token tới resource server; refresh token chỉ tới authorization server để xin access token mới.
2. **Hết hạn access token có luôn bắt đăng nhập lại không?** Không, khi có refresh token còn hợp lệ và chính sách cho phép, client có thể xin access token mới.
3. **Refresh token có bắt buộc trong OAuth 2.0 không?** Không; authorization server quyết định cấp hoặc không.
4. **Token là JWT thì có thể tin vào payload sau khi Base64URL decode không?** Không; phải kiểm chữ ký và các claim/ràng buộc đúng.
5. **Mọi refresh response đều cấp refresh token mới?** Không. Rotation là một chính sách; với public client được cấp refresh token, RFC 9700 yêu cầu rotation hoặc sender-constraining để phát hiện replay.
6. **Logout client có thu hồi tức thì mọi JWT access token không?** Không mặc nhiên. Cần chính sách revocation và cơ chế kiểm tra phù hợp ở resource server.
7. **Access token còn hạn nhưng thiếu `orders.write` có được sửa đơn hàng không?** Không nếu API thực thi đúng phân quyền.
8. **Bị lộ refresh token nguy hiểm như thế nào?** Có thể cho phép xin access token mới, kéo dài quyền truy cập trái phép nếu không có bảo vệ và phát hiện reuse.

**Ghi nhớ:** **Access token dùng để vào API, refresh token dùng để xin access token mới, và cả hai phải được giới hạn thời gian, phạm vi và khả năng thu hồi.** Việc bảo vệ vòng đời token là phối hợp giữa authorization server, client, resource server và cơ chế vận hành bảo mật, không chỉ là kiểm tra trường `exp`.

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): vai trò, refresh token, cấp và làm mới access token.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): gửi access token dưới dạng Bearer và lỗi xác thực.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): refresh token rotation, sender-constraining, chống replay và khuyến nghị hiện đại.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): cơ chế thu hồi token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra token thông qua introspection.
- [Spring Security — OAuth2 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): cấu hình xác minh JWT access token trong Spring Security.
