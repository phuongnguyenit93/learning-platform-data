# Header phiên khác với token JWT hoặc OAuth access token

Spring Session có thể gửi session ID qua HTTP header thay vì cookie. Cách này thường hữu ích với ứng dụng mobile, desktop client hoặc API client tự quản lý thông tin phiên. Tuy nhiên, một header mang session ID không tự biến ID đó thành JWT hay OAuth access token. Ba giá trị này có thể đều được gửi trong HTTP request, nhưng chúng đại diện cho những cơ chế khác nhau.

Để thiết kế đúng, cần phân biệt **định danh một phiên phía máy chủ**, **định dạng token có thể mang claim**, và **credential cấp quyền truy cập tài nguyên**. Spring Session quản lý phiên; JWT định nghĩa một định dạng token; OAuth access token đại diện quyền truy cập do authorization server cấp. Một JWT có thể được dùng làm OAuth access token, nhưng không phải mọi JWT đều là access token và session ID của Spring Session không phải JWT.

## 1. Header phiên của Spring Session là gì?

Trong ứng dụng Servlet, Spring Session thường dùng cookie để trao đổi session ID. Với client không muốn dùng cookie, có thể cấu hình `HeaderHttpSessionIdResolver` để đọc ID từ một HTTP header. Factory method `xAuthToken()` sử dụng header `X-Auth-Token`.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.HeaderHttpSessionIdResolver;
import org.springframework.session.web.http.HttpSessionIdResolver;

@Configuration
class SessionHeaderConfiguration {

    @Bean
    HttpSessionIdResolver httpSessionIdResolver() {
        return HeaderHttpSessionIdResolver.xAuthToken();
    }
}
```

Sau khi cấu hình resolver, client gửi session ID trong header:

```http
GET /api/profile HTTP/1.1
Host: api.example.test
X-Auth-Token: 9f7a...opaque-session-id
```

Khi ứng dụng tạo session mới, Spring Session có thể trả session ID trong response header tương ứng. Client phải lưu giá trị này một cách an toàn và gửi lại ở request sau. ID chỉ là một khóa tra cứu; dữ liệu session vẫn được lưu phía máy chủ qua `SessionRepository`, chẳng hạn Redis hoặc JDBC.

Luồng xử lý tổng quát:

```mermaid
sequenceDiagram
    participant C as API client
    participant F as SessionRepositoryFilter
    participant I as HeaderHttpSessionIdResolver
    participant R as SessionRepository
    participant D as Redis/JDBC
    participant A as Ứng dụng
    C->>F: Request với X-Auth-Token
    F->>I: Đọc session ID từ header
    I-->>F: Session ID
    F->>R: Tìm session theo ID
    R->>D: Đọc dữ liệu phiên
    D-->>R: Session attributes
    R-->>F: Session
    F->>A: HttpSession được bọc
    A-->>F: Xử lý request
    F-->>C: Response, có thể kèm ID mới
```

Resolver chỉ quyết định **đọc và gửi session ID ở đâu**. Nó không xác thực người dùng, không kiểm tra chữ ký token và không quyết định quyền truy cập API. Việc tìm dữ liệu phiên thuộc repository; xác thực và phân quyền thuộc lớp bảo mật của ứng dụng.

## 2. Session ID là định danh tham chiếu phía máy chủ

Session ID của Spring Session thường là một chuỗi opaque (không mang ý nghĩa nghiệp vụ có thể đọc trực tiếp). Khi client gửi ID, ứng dụng dùng ID đó để tìm session trong repository. Các attributes, thời điểm truy cập gần nhất và thời hạn không hoạt động nằm trong dữ liệu session phía máy chủ.

Đặc điểm của session ID:

- **Tham chiếu tới trạng thái phía máy chủ:** nếu repository không có session tương ứng, ID không khôi phục được trạng thái.
- **Không tự mô tả danh tính hoặc quyền:** ID không chứa claim như user ID, role, scope hay audience để client hoặc resource server tự diễn giải.
- **Có thể bị thu hồi phía máy chủ:** vô hiệu hóa session hoặc xóa session trong repository làm ID cũ không còn khôi phục được phiên.
- **Phụ thuộc kho lưu trữ:** nhiều instance có thể dùng cùng ID nếu cùng truy cập repository và namespace tương thích.
- **Là bí mật dạng bearer:** người khác lấy được ID còn hiệu lực có thể sử dụng phiên tương ứng, nên phải bảo vệ như credential.

Không đưa thông tin người dùng, vai trò hay dữ liệu nhạy cảm vào session ID. Cũng không tự tạo ID bằng cách ghép username, timestamp hoặc số thứ tự. Hãy để Spring Session tạo ID ngẫu nhiên theo cơ chế của framework.

## 3. JWT là định dạng token, không phải tên khác của session ID

JWT (JSON Web Token) là một định dạng biểu diễn claim dưới dạng JSON, thường được ký số hoặc bảo vệ bằng cơ chế mật mã phù hợp. Một JWT dạng compact thường có ba phần ngăn cách bởi dấu chấm:

```text
header.payload.signature
```

Header mô tả loại token và thuật toán; payload chứa claims; signature cho phép bên nhận kiểm tra tính toàn vẹn và nguồn phát hành theo khóa được tin cậy. Payload JWT ký số thường chỉ được mã hóa Base64URL, không phải tự động được mã hóa bí mật. Người có token có thể đọc nội dung payload, vì vậy không đặt mật khẩu hay dữ liệu nhạy cảm vào claim.

Một JWT có thể chứa các claim tiêu chuẩn như:

| Claim | Ý nghĩa |
|---|---|
| `iss` | Issuer — bên phát hành token |
| `sub` | Subject — chủ thể mà token nói đến |
| `aud` | Audience — đối tượng nhận token |
| `exp` | Thời điểm token hết hạn |
| `nbf` | Thời điểm trước đó token chưa được chấp nhận |
| `iat` | Thời điểm token được phát hành |
| `jti` | Định danh riêng của token |

Khi xác minh JWT, resource server cần kiểm tra chữ ký bằng khóa tin cậy và xác nhận các điều kiện như issuer, audience, thời hạn và thuật toán được cho phép. Chỉ giải mã payload hoặc đọc `sub` không chứng minh token hợp lệ.

JWT có thể được xác minh cục bộ mà không cần tra một session record cho mỗi request, nếu hệ thống dùng mô hình token tự chứa và resource server đã có khóa cũng như chính sách xác minh. Đây là điểm khác với session ID: session ID cần được tra trong repository để khôi phục trạng thái phiên; JWT tự chứa các claim đã được issuer phát hành và ký, nhưng vẫn cần xác minh trước khi tin cậy.

## 4. OAuth access token đại diện quyền truy cập

OAuth 2.0 là framework ủy quyền. Access token là credential mà client gửi tới resource server để yêu cầu truy cập tài nguyên theo quyền đã được cấp. Authorization server phát hành token sau một quy trình cấp quyền phù hợp; resource server kiểm tra token theo định dạng và chính sách của hệ thống.

Access token có thể là:

- **Opaque token:** một chuỗi không chứa claim có thể đọc trực tiếp. Resource server thường cần gọi introspection endpoint hoặc cơ chế tra cứu tương ứng để biết token có hợp lệ và được cấp quyền gì.
- **JWT access token:** token có định dạng JWT, mang claims về issuer, subject, audience, scope hoặc quyền, cùng thời hạn. Resource server xác minh chữ ký và claims theo profile mà hệ thống áp dụng.

Vì vậy, OAuth access token là vai trò/ý nghĩa của credential trong giao thức ủy quyền; JWT là một định dạng có thể được dùng để biểu diễn credential đó. Hai khái niệm không đồng nghĩa.

Một request OAuth Bearer thông thường có dạng:

```http
GET /api/orders HTTP/1.1
Host: resource.example.test
Authorization: Bearer eyJhbGciOi...access-token
```

Resource server xử lý access token theo cấu hình bảo mật OAuth2 Resource Server. Nó kiểm tra tính hợp lệ và quyền cần thiết, ví dụ scope `orders.read`. Việc Spring Session có tồn tại trong ứng dụng không tự động khiến resource server chấp nhận hoặc xác minh access token.

Refresh token có vai trò khác access token. Client dùng refresh token với authorization server để xin access token mới theo điều kiện cấp quyền; không gửi refresh token đến resource API như thể nó là access token.

## 5. So sánh ba loại giá trị

| Tiêu chí | Spring Session ID trong header | JWT | OAuth access token |
|---|---|---|---|
| Bản chất | Định danh phiên phía máy chủ | Định dạng token chứa claims | Credential cấp quyền truy cập tài nguyên |
| Ví dụ nơi gửi | `X-Auth-Token: <session-id>` | Thường `Authorization: Bearer <jwt>` nếu được dùng làm credential | Thường `Authorization: Bearer <access-token>` |
| Dữ liệu quyền/danh tính | Thường nằm trong session phía máy chủ | Có thể có claims về chủ thể/quyền | Quyền được cấp cho client/resource; token có thể opaque hoặc JWT |
| Cách kiểm tra | Tra session qua `SessionRepository` | Xác minh chữ ký và claims theo chính sách | Xác minh JWT hoặc introspect opaque token theo cấu hình OAuth |
| Thu hồi | Vô hiệu hóa/xóa session phía máy chủ | Thường khó thu hồi tức thời nếu chỉ xác minh offline; cần denylist, introspection hoặc cơ chế tương đương | Theo cơ chế authorization server: introspection, revocation, thời hạn ngắn hoặc chính sách khác |
| Trạng thái phía máy chủ | Có session state | Có thể không cần session state cho mỗi request | Tùy loại token và triển khai |
| Thành phần quản lý | Spring Session và repository | Issuer, hệ thống khóa và bên xác minh | Authorization server và resource server |

Không phân loại token chỉ dựa trên việc nó là một chuỗi dài hay được gửi trong header. Cần xem ai phát hành, nó đại diện cho điều gì, ai xác minh và cơ chế thu hồi là gì.

## 6. Header X-Auth-Token không đồng nghĩa Authorization: Bearer

Spring Session `HeaderHttpSessionIdResolver.xAuthToken()` mặc định đọc header `X-Auth-Token`. OAuth access token thường được gửi trong header `Authorization` với scheme `Bearer`. Hai header này có ngữ nghĩa khác nhau.

```http
# Session ID do Spring Session quản lý
X-Auth-Token: 9f7a...opaque-session-id

# OAuth access token
Authorization: Bearer eyJhbGciOi...access-token
```

Nếu gửi một session ID trong `Authorization: Bearer`, các thành phần OAuth2 Resource Server có thể hiểu nó là access token và cố gắng xác minh theo JWT decoder hoặc introspection. Ngược lại, gửi JWT access token vào `X-Auth-Token` không khiến Spring Session tự động xác minh chữ ký JWT; framework sẽ xem giá trị đó là session ID và tìm trong repository.

Có thể tự cấu hình `HeaderHttpSessionIdResolver` với tên header khác, nhưng nên chọn tên biểu thị rõ mục đích, ví dụ `X-Session-Id` hoặc `X-Auth-Token`, và ghi lại hợp đồng API. Tránh dùng `Authorization` cho session ID nếu ứng dụng còn sử dụng OAuth Bearer authentication.

## 7. Spring Security và session header phối hợp như thế nào?

Spring Session quản lý nơi lưu session và cách khôi phục session ID. Spring Security thực hiện xác thực và phân quyền. Trong một ứng dụng Servlet dùng session-based authentication, Spring Security có thể lưu `SecurityContext` trong `HttpSession`. Khi `SessionRepositoryFilter` khôi phục session, các thành phần bảo mật có thể lấy context từ session theo cấu hình của Spring Security.

Với header resolver, client gửi session ID trong header; filter của Spring Session khôi phục `HttpSession`; sau đó Spring Security sử dụng cơ chế bảo mật của ứng dụng để xác định principal và quyền. Header resolver tự nó không chứng minh người dùng đã đăng nhập.

```mermaid
flowchart TD
    C[Client gửi X-Auth-Token] --> F[SessionRepositoryFilter]
    F --> R[SessionRepository: khôi phục HttpSession]
    R --> S[HttpSession / SecurityContext]
    S --> A[Spring Security xác thực context]
    A --> P{Được phép truy cập?}
    P -- Có --> E[Controller / API]
    P -- Không --> D[401 hoặc 403 theo tình huống]
```

Khi đăng nhập, ứng dụng cần tạo hoặc cập nhật session và để cơ chế bảo mật lưu context theo cấu hình. Khi đăng xuất, cần vô hiệu hóa session để repository thu hồi trạng thái. Khi xác thực thành công, cần áp dụng cơ chế đổi session ID phù hợp để giảm nguy cơ session fixation. Những hành vi này là trách nhiệm của tích hợp Spring Security và Spring Session, không phải của riêng header resolver.

Một ứng dụng cũng có thể dùng OAuth2 Resource Server và Spring Session cho các mục đích khác nhau, nhưng phải định nghĩa rõ luồng nào xác thực bằng access token, luồng nào dùng session. Tránh để một endpoint vừa chấp nhận session ID vừa chấp nhận bearer token mà không có chính sách ưu tiên và phân quyền rõ ràng.

## 8. Vòng đời và thu hồi: khác biệt quan trọng

### Spring Session ID

Session ID tham chiếu tới bản ghi session trong repository. Khi người dùng đăng xuất và ứng dụng gọi `HttpSession.invalidate()`, Spring Session xóa hoặc vô hiệu hóa session tương ứng. Request tiếp theo gửi lại ID cũ sẽ không khôi phục được session đã bị thu hồi.

### JWT

JWT ký số thường được xác minh offline bằng khóa công khai. Nếu token chưa hết hạn và chữ ký cùng claims vẫn hợp lệ, resource server có thể tiếp tục chấp nhận nó. Muốn thu hồi trước `exp`, hệ thống cần thêm cơ chế như denylist theo `jti`, introspection, thay đổi khóa hoặc thời hạn token ngắn kết hợp quy trình cấp mới. Chỉ xóa một bản ghi session trong Redis không làm JWT đã phát hành mất hiệu lực.

### OAuth access token

Khả năng thu hồi phụ thuộc loại token và thiết kế authorization server/resource server. Opaque token có thể được introspect để kiểm tra trạng thái hiện tại. JWT access token thường được xác minh offline, nhưng hệ thống vẫn có thể áp dụng denylist, introspection hoặc chính sách thu hồi riêng. OAuth token revocation endpoint có thể cho client yêu cầu thu hồi token theo quy tắc của authorization server; resource server cần thực sự kiểm tra trạng thái hoặc dùng thời hạn phù hợp để việc thu hồi có hiệu lực.

Không dùng một hành động logout duy nhất với giả định nó tự động thu hồi mọi loại credential. Nếu ứng dụng dùng cả session và OAuth token, cần xác định logout có xóa session, thu hồi access/refresh token, xóa token phía client hay kết hợp các bước nào.

## 9. Bảo vệ session ID và token khi dùng header

Session ID gửi trong header vẫn là bí mật xác thực theo kiểu bearer. Bất kỳ bên nào lấy được giá trị còn hiệu lực đều có thể thử sử dụng phiên. Vì vậy:

- Chỉ truyền qua HTTPS; không đưa session ID vào query string hoặc URL path.
- Không ghi nguyên giá trị header vào access log, distributed trace, error report hoặc analytics.
- Lưu ID ở client trong vùng lưu trữ phù hợp với nền tảng; giới hạn quyền truy cập và thời gian lưu.
- Đặt timeout session phù hợp và thu hồi session khi logout hoặc phát hiện rủi ro.
- Giữ session ID khó đoán; không tự tạo ID từ thông tin người dùng.
- Không dùng cùng một giá trị cho session ID, access token và refresh token.

Header tùy chỉnh không tự mã hóa nội dung. HTTPS bảo vệ header trên đường truyền; nó không ngăn endpoint, proxy hoặc log nội bộ được cấu hình sai làm lộ giá trị. Cần rà soát việc ghi header ở reverse proxy, API gateway và hệ thống quan sát.

## 10. CORS và CSRF khi client gửi session ID qua header

Một ứng dụng trình duyệt gọi API ở origin khác có thể cần gửi `X-Auth-Token`. Vì đây là custom request header, trình duyệt thường gửi CORS preflight `OPTIONS`; server cần cho phép origin cụ thể và header đó trong `Access-Control-Allow-Headers`. Không nên bật `*` một cách tùy tiện cho các origin có quyền truy cập dữ liệu nhạy cảm.

Khác với cookie, custom header thường phải được JavaScript hoặc client chủ động thêm vào request. Điều này có thể thay đổi bề mặt CSRF vì trình duyệt không tự động gắn `X-Auth-Token` vào mọi request cross-site. Tuy nhiên, không nên xem custom header là biện pháp bảo vệ duy nhất. Nếu API vẫn chấp nhận cookie, hoặc có endpoint khác dựa vào credential tự động gửi, vẫn cần chính sách CSRF thích hợp. CORS là chính sách cho phép JavaScript đọc/gửi một số request cross-origin; nó không thay thế xác thực, phân quyền hoặc kiểm tra nguồn gốc cho mọi kiểu client.

Ví dụ client web gửi header:

```javascript
const response = await fetch("https://api.example.test/profile", {
  method: "GET",
  headers: {
    "X-Auth-Token": sessionId
  }
});
```

Giá trị `sessionId` phải được lấy từ nơi lưu trữ an toàn của ứng dụng. Tránh lưu nó trong các vị trí dễ bị JavaScript bên thứ ba đọc nếu threat model của ứng dụng không cho phép. Với ứng dụng web có nguy cơ XSS, mọi credential mà JavaScript có thể truy cập đều cần được bảo vệ đặc biệt.

## 11. Ví dụ kiểm thử header session

Giả sử API tạo session khi client gọi endpoint khởi tạo. Response có thể chứa `X-Auth-Token`; client lưu ID và gửi lại:

```bash
# Request đầu tiên: ứng dụng tạo session nếu endpoint yêu cầu
curl -i -X POST https://api.example.test/session/start

# Request sau: gửi lại ID đã nhận từ response header
curl -i https://api.example.test/profile \
  -H "X-Auth-Token: <session-id-from-response>"
```

Đây là minh họa luồng HTTP; endpoint khởi tạo session phải được thiết kế phù hợp với cơ chế xác thực của ứng dụng. Không tạo một endpoint công khai cho phép bất kỳ client nào nhận một session đã xác thực mà không qua login.

Các kiểm thử nên bao gồm:

1. Request không có header: ứng dụng xử lý như chưa có session; endpoint có thể tạo session mới nếu logic yêu cầu.
2. Request có ID hợp lệ: Spring Session khôi phục attributes đã lưu.
3. Request có ID không tồn tại hoặc đã hết hạn: ứng dụng không được coi đó là phiên đã xác thực.
4. Request sau logout với ID cũ: repository không khôi phục lại session đã thu hồi.
5. Request tới instance khác: cùng repository cho phép khôi phục cùng session.
6. Header bị proxy loại bỏ hoặc ghi đè: quan sát lỗi và cấu hình chuyển tiếp header chính xác.
7. CORS preflight: chỉ origin và header cần thiết được cho phép.
8. Log và trace: giá trị session ID được che hoặc loại khỏi bản ghi.

## 12. Khi nào dùng session header, JWT hay OAuth access token?

| Nhu cầu | Cơ chế thường phù hợp | Lý do |
|---|---|---|
| API client cần duy trì trạng thái server-side như giỏ hàng hoặc tiến trình nhiều bước | Spring Session qua header | Session được lưu tập trung và có thể thu hồi phía máy chủ |
| Nhiều API độc lập cần xác minh credential mà không tra session cho mỗi request | JWT được phát hành và xác minh theo một trust model rõ ràng | Claims có thể được xác minh bằng chữ ký và chính sách issuer/audience/expiry |
| Client được cấp quyền truy cập tài nguyên của một resource server theo OAuth | OAuth access token | Token gắn với authorization grant, audience và scope/quyền theo hệ thống |
| Hệ thống muốn token opaque và kiểm tra trạng thái tập trung | Opaque OAuth access token với introspection | Resource server tra trạng thái qua authorization server |

Không có lựa chọn nào phù hợp cho mọi ứng dụng. Session header phù hợp khi ứng dụng cần trạng thái phiên phía máy chủ và chấp nhận tra repository. JWT có ích khi cần token tự chứa với xác minh chữ ký và claims. OAuth access token phù hợp khi cần ủy quyền giữa client, authorization server và resource server. Có thể dùng OAuth access token định dạng JWT, nhưng không vì vậy mà access token và JWT trở thành hai thuật ngữ thay thế nhau.

## 13. Các lỗi thiết kế thường gặp

- **Gửi JWT vào `X-Auth-Token` rồi mong Spring Session tự xác minh chữ ký:** resolver coi giá trị đó là session ID và tra repository; không có bước xác minh JWT tự động.
- **Gửi session ID vào `Authorization: Bearer` rồi mong OAuth Resource Server khôi phục session:** resource server sẽ xử lý theo cơ chế token đã cấu hình, không tự tra Spring Session.
- **Cho rằng session ID chứa quyền:** ID chỉ tham chiếu session; phải xác thực và phân quyền theo `SecurityContext` hoặc cơ chế bảo mật tương ứng.
- **Chỉ xóa ID phía client khi logout:** session phía server có thể còn hiệu lực; cần invalidate session trong repository.
- **Cho rằng logout session làm JWT mất hiệu lực:** JWT đã phát hành cần cơ chế thu hồi riêng hoặc hết hạn theo chính sách.
- **Ghi header vào log:** log có thể trở thành nơi rò rỉ credential; cần redact header nhạy cảm.
- **Cho phép mọi origin gửi custom header:** cấu hình CORS quá rộng có thể mở bề mặt truy cập không cần thiết.

Khi thiết kế API, hãy ghi rõ header nào mang session ID, header nào mang access token, thành phần nào xác minh credential và nơi nào quản lý trạng thái. Sự phân biệt này giúp Spring Session, Spring Security và OAuth2 Resource Server phối hợp đúng vai trò mà không nhầm một định danh phiên với một token cấp quyền.
