# Thời gian sống phiên, token và quy trình thu hồi truy cập

## 1. Bài toán triển khai: đăng xuất hoặc hết hạn có thực sự cắt quyền?

Một hệ thống Spring Security có thể cho người dùng đăng nhập qua trình duyệt và đồng thời cho dịch vụ khác gọi API bằng access token. Người dùng bấm **Đăng xuất**, quản trị viên khóa tài khoản, hoặc phát hiện token bị lộ. Câu hỏi quan trọng không chỉ là giao diện hiện dòng “Đã đăng xuất” mà là:

> **Từ thời điểm thu hồi được yêu cầu, những thông tin xác thực đã cấp trước đó còn cho phép gọi API hay không, trong bao lâu và ở những thành phần nào?**

Nếu trình duyệt xóa cookie nhưng server vẫn chấp nhận `JSESSIONID` cũ, logout chưa đạt mục tiêu. Nếu Authorization Server thu hồi refresh token nhưng một JWT access token còn hạn vẫn được Resource Server chấp nhận, người dùng có thể tiếp tục gọi API trong một khoảng thời gian. Nếu microservice giữ cache quyết định quyền quá lâu, thay đổi role trong database chưa chắc có hiệu lực ngay.

Bài này thuộc phần **Triển khai** của **Spring Security – fundamentals**. Trọng tâm là thiết kế và vận hành **thời gian sống của phiên, token và quy trình thu hồi truy cập** trên Java 17+, Spring Boot 3.x, Spring Security 6.x Servlet; đồng thời phân biệt các tình huống OAuth2/OIDC và hệ thống nhiều node.

Học xong, bạn cần có khả năng:

1. Phân biệt cookie, HTTP session, access token, refresh token, remember-me và phiên SSO ở Identity Provider.
2. Xác định **idle timeout**, **absolute lifetime**, token `exp`, refresh token TTL và khoảng thời gian quyền cũ còn hiệu lực.
3. Giải thích vì sao **logout một session không tự thu hồi tất cả JWT**, và **revoke refresh token không tự thu hồi access token đã phát hành**.
4. Chọn cơ chế thu hồi: session invalidation, token introspection, denylist, token version, short-lived token, refresh token rotation và family revocation.
5. Cấu hình session trên Spring Boot/Spring Security phù hợp và viết test để kiểm chứng logout/CSRF/phiên.
6. Thiết lập quy trình ứng phó khi tài khoản, token hoặc service credential bị xâm phạm.

Không có một số TTL “đúng cho mọi hệ thống”. Chính sách phải dựa trên rủi ro, loại client, dữ liệu, quyền, trải nghiệm người dùng, yêu cầu pháp lý và khả năng thu hồi thực tế.

## 2. Phân biệt chính xác các loại trạng thái và credential

| Thành phần | Ai cấp và lưu trạng thái? | Cách sử dụng | Hết hạn/thu hồi |
| --- | --- | --- | --- |
| **HTTP session** | Servlet container hoặc Spring Session lưu trạng thái phiên trên server/repository. | Browser gửi session ID, thường bằng `JSESSIONID` cookie. | Invalidate session hoặc hết hạn ở session store; ID cũ không được nhận. |
| **Session cookie** | Server gửi `Set-Cookie`; browser giữ chuỗi session ID. | Tự động gửi qua `Cookie` khi khớp domain/path/SameSite/Secure. | Browser xóa/hết hạn cookie; **không thay thế** invalidate ở server. |
| **OAuth2 access token** | Authorization Server cấp; Resource Server xác thực. | Thường gửi `Authorization: Bearer ...`. | `exp`, introspection hoặc cơ chế thu hồi mà Resource Server hỗ trợ. |
| **Refresh token** | Authorization Server cấp và quản lý grant/token family. | Client dùng với token endpoint để xin access token mới. | Hết hạn, rotation/reuse detection, revoke grant hoặc token family. |
| **ID token OIDC** | OpenID Provider cấp cho client để cung cấp thông tin về sự kiện xác thực. | Client xác minh danh tính trong giao thức OIDC. | Có `exp` nhưng **không dùng mặc định như access token** gọi Resource Server. |
| **Remember-me token** | Ứng dụng cấp cookie/record cho chức năng ghi nhớ đăng nhập. | Có thể phục hồi xác thực sau khi session hết hạn. | Thu hồi cookie và bản ghi phía server theo loại remember-me. |
| **CSRF token** | Spring Security hoặc ứng dụng tạo để chống request giả mạo. | Form/header kèm request thay đổi trạng thái dùng credential trình duyệt. | Có vòng đời gắn session/repository; **không cấp quyền đăng nhập**. |
| **API key / client secret** | Đơn vị quản lý tích hợp/Identity Provider cấp. | Dùng để xác thực client hoặc một dịch vụ theo giao thức. | Rotate, disable/revoke tại hệ thống cấp; không nhầm với JWT TTL. |
| **Phiên IdP/SSO** | Identity Provider lưu riêng trạng thái đăng nhập liên kết. | Có thể cấp phiên mới cho ứng dụng mà không bắt người dùng nhập lại mật khẩu. | Logout local không nhất thiết logout IdP; cần thiết kế SSO/logout riêng. |

### 2.1. Session cookie không phải session phía server

Ví dụ:

```http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=DEMO_SESSION_ID; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
```

Cookie chứa **mã tham chiếu phiên**, không chứa toàn bộ trạng thái phiên do Servlet container quản lý. Khi người dùng gửi cookie:

```http
GET /private/home HTTP/1.1
Cookie: JSESSIONID=DEMO_SESSION_ID
```

container tra cứu session tương ứng. Nếu session đã hết hạn hoặc bị xóa, cookie cũ không còn mang quyền xác thực. Vì vậy, “xóa cookie khỏi browser” và “hủy phiên phía server” là **hai công việc khác nhau**. Bài kiểm thử an toàn cần cố tình gửi lại cookie cũ sau logout.

### 2.2. Một người có thể đồng thời sở hữu nhiều loại credential

Người dùng truy cập ứng dụng qua OIDC có thể có:

- Session IdP còn hiệu lực.
- Session nội bộ của ứng dụng (cookie `JSESSIONID`).
- Access token của API.
- Refresh token ở phía client/BFF hoặc authorization server.
- Token remember-me, nếu ứng dụng triển khai tính năng đó.

Đăng xuất ứng dụng có thể chỉ vô hiệu hóa session nội bộ. Nếu IdP vẫn có phiên SSO, lần điều hướng tiếp theo có thể đăng nhập lại rất nhanh. Nếu resource server vẫn chấp nhận JWT chưa hết hạn, API có thể vẫn đọc được dữ liệu với token đó. **Không được tuyên bố “đăng xuất khỏi mọi nơi” nếu chưa chứng minh thu hồi trên mọi loại credential liên quan.**

## 3. Các khái niệm thời gian: idle, absolute, rolling và token expiry

### 3.1. Idle timeout — thời gian không hoạt động

**Idle timeout** là khoảng thời gian tối đa session không có hoạt động được tính là sử dụng phiên. Ví dụ, session có `maxInactiveInterval = 20 phút`:

```text
09:00  Login -> session S được tạo
09:10  Request hợp lệ với S -> cập nhật last-access
09:25  Request hợp lệ với S -> còn session vì chưa idle quá 20 phút
09:46  Request tiếp theo với S -> có thể bị từ chối vì idle >20 phút
```

Mỗi request sử dụng session có thể cập nhật thời điểm truy cập cuối. Vì vậy, polling/heartbeat chạy nền có thể kéo dài phiên lâu hơn dự định. Cần thống nhất **hoạt động nào được tính là activity** thay vì dựa vào cảm nhận “người dùng không chạm bàn phím”.

Trong Servlet, `HttpSession#setMaxInactiveInterval(int seconds)` là API đặt giới hạn không hoạt động cho một session. Cơ chế và thời điểm dọn dữ liệu có thể phụ thuộc container/session repository, nhưng request với session đã hết hạn **không được dùng trạng thái xác thực của phiên đó**.

### 3.2. Absolute lifetime — giới hạn sống tuyệt đối

**Absolute lifetime** tính từ khi phiên bắt đầu hoặc lần xác thực đủ mạnh gần nhất, không bị kéo dài vô hạn bởi request liên tục.

Ví dụ chính sách ứng dụng:

- Idle timeout: 20 phút.
- Absolute lifetime: 8 giờ kể từ khi login.
- Sensitive operation reauthentication: yêu cầu đăng nhập/MFA lại nếu quá 15 phút từ lần xác thực mạnh gần nhất.

Các con số chỉ là **ví dụ để thiết kế**, không phải mặc định hoặc khuyến nghị cố định của Spring Security. `server.servlet.session.timeout` xử lý chính sách idle của Servlet; **không tự tạo absolute lifetime**. Muốn giới hạn tuyệt đối hoặc step-up, hệ thống cần lưu thời điểm gốc ở nơi đáng tin cậy, kiểm tra tại request/operation và thu hồi hoặc yêu cầu xác thực lại khi chạm ngưỡng.

### 3.3. Sliding/rolling expiry

Một session có idle timeout thường mang tính **sliding**: khi hoạt động được tính hợp lệ, mốc hết hạn do idle dịch ra sau. Refresh token cũng có thể có sliding lifetime nếu Authorization Server cho phép, nhưng một hệ thống an toàn thường cân nhắc thêm **absolute expiry** cho refresh token family để không kéo dài vô hạn chỉ vì liên tục làm mới.

**Không nhầm rolling expiry với token đang được sửa `exp`.** JWT access token đã ký thông thường có `exp` cố định trong token đó; một request sử dụng token không tự thay `exp`. Client phải nhận token mới từ quy trình được cấp phép.

### 3.4. Các mốc thời gian trên JWT

JWT có thể chứa:

- `iat` (issued at): thời điểm cấp.
- `nbf` (not before): chưa được chấp nhận trước mốc này.
- `exp` (expiration time): không còn được chấp nhận ở hoặc sau mốc này, tùy **clock skew/leeway** mà validator cho phép.
- `jti`: định danh token duy nhất nếu nhà phát hành sử dụng, hữu ích cho một số mô hình chống replay/thu hồi.

Trong JWT, các giá trị thời gian dạng NumericDate thường đo bằng **giây từ Unix epoch**. Khi so sánh, phải tính đúng timezone/đơn vị và đồng bộ đồng hồ máy chủ. Ví dụ sau dùng thời gian UTC cố định:

```text
issuedAt  = 2026-01-01T00:00:00Z
expiresAt = 2026-01-01T00:05:00Z
current   = 2026-01-01T00:04:59Z -> chưa chạm exp
current   = 2026-01-01T00:05:00Z -> đến exp
```

Validator Spring Security có thể dùng độ lệch đồng hồ (clock skew) để chịu sai lệch giữa các máy. Cần xác nhận mức leeway thực tế khi test boundary: một token “đúng giây exp” có thể chưa bị từ chối nếu có tolerance cấu hình. **Không đặt clock skew lớn tùy tiện** vì nó kéo dài thời gian token được chấp nhận sau expiry danh nghĩa.

## 4. Ranh giới trách nhiệm của Spring Security, Servlet container và Identity Provider

### 4.1. Session do ai hết hạn?

Spring Security quản lý xác thực/ủy quyền và liên kết `SecurityContext` với request/session theo cấu hình. **Servlet container hoặc Spring Session repository** quyết định sự tồn tại và idle expiry của HTTP session. Spring Security có thể phản ứng khi client gửi session ID đã hết hạn, nhưng không biến cấu hình session timeout thành “hàm logout chạy tự động mọi nơi”.

Các thuộc tính thường gặp trong Spring Boot:

```yaml
# application-prod.yml: ví dụ cấu hình, không phải mặc định chung
server:
  servlet:
    session:
      timeout: 20m
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

Giải thích:

- `timeout: 20m` đặt idle timeout phiên Servlet; tùy container, giá trị quá nhỏ hoặc độ phân giải thời gian có thể được làm tròn.
- `secure: true` yêu cầu cookie được sử dụng trên kết nối bảo mật, phù hợp production qua HTTPS.
- `http-only: true` giúp hạn chế JavaScript đọc cookie; không bảo vệ khỏi mọi XSS hoặc CSRF.
- `same-site: lax` là lựa chọn ví dụ; ứng dụng có SSO/cross-site iframe/callback đặc biệt cần đánh giá `SameSite` và `Secure` riêng.
- Đây **không phải** giới hạn sống tuyệt đối của phiên, TTL của OAuth token hay tuổi thọ phiên IdP.

Trong môi trường dev/test chạy HTTP tại localhost, nếu bật `Secure` trên cookie mà mong browser gửi qua HTTP, kết quả có thể thay đổi theo browser và chính sách loopback. Nên test production-like qua HTTPS thay vì âm thầm tắt bảo vệ cookie trên production.

### 4.2. Logout Servlet làm gì?

Khi bật Spring Security logout, `POST /logout` với CSRF hợp lệ (khi CSRF đang bật) thường thực hiện:

- Invalidate `HttpSession` hiện tại.
- Clear `SecurityContextHolder` và repository phù hợp.
- Xóa CSRF token hiện hành.
- Dọn cơ chế remember-me được tích hợp, nếu ứng dụng bật.
- Gửi redirect hoặc response thành công theo `LogoutSuccessHandler` đã cấu hình.

`GET /logout` trong cấu hình CSRF mặc định thường hiển thị trang xác nhận, **không thực hiện hủy session**. Nếu đổi sang logout bằng GET để “cho tiện”, hệ thống có nguy cơ bị một website khác kích hoạt logout ngoài ý muốn.

**Không nên chỉ kiểm tra trang đã chuyển về `/login`.** Một phép thử có giá trị là giữ bản sao cookie trước logout và gửi lại nó tới endpoint bảo vệ; server phải từ chối.

### 4.3. Access token được kiểm tra ở đâu?

Spring Security OAuth2 Resource Server nhận bearer token, kiểm tra chữ ký và những claim cần thiết theo loại token và cấu hình (issuer, thời hạn, audience nếu ứng dụng yêu cầu), sau đó quyết định quyền từ authorities/scopes. Nhưng **Resource Server không mặc định tự biết refresh token vừa bị thu hồi tại Authorization Server**.

Nếu dùng JWT tự chứa (self-contained) và chỉ kiểm tra chữ ký/`exp`, token đã cấp có thể tiếp tục hoạt động đến expiry. Nếu yêu cầu “thu hồi ngay”, phải bổ sung cơ chế kiểm tra trạng thái thu hồi thực sự ở các Resource Server, hoặc dùng opaque token với introspection phù hợp.

## 5. Ma trận thời gian sống cần tài liệu hóa

Một hệ thống nên có **sơ đồ thời hạn** thay vì chỉ một giá trị “session timeout”.

| Thành phần | TTL cần quyết định | Có kéo dài khi sử dụng không? | Cách thu hồi |
| --- | --- | --- | --- |
| Browser session | Idle timeout và (nếu có) absolute lifetime | Idle có thể trượt; absolute thường không. | Invalidate session, xóa record trong store, khóa account, buộc login lại. |
| Session cookie | Session cookie hoặc `Max-Age`/`Expires` | Browser xử lý theo thuộc tính cookie. | Gửi cookie hết hạn; **phải thu hồi session server**. |
| Access token | `exp - iat`, có thể vài phút tùy rủi ro | Token cũ không đổi `exp`; xin token mới. | Hết hạn, introspection, denylist, token version hoặc biện pháp tương đương. |
| Refresh token | Idle, absolute, family lifetime theo Authorization Server | Có thể rotation/sliding có giới hạn. | Revoke token/family/grant, phát hiện reuse. |
| API key/client secret | Hạn sử dụng, rotation và quyền theo workload | Không mặc định hết hạn theo request. | Disable, rotate, thay credential ở dịch vụ liên quan. |
| Role cache | TTL cache và phiên bản quyền | Có thể refresh theo yêu cầu. | Invalidate cache, token/session version, token expiry hoặc reauthentication. |
| IdP SSO session | Chính sách session của Identity Provider | Có thể sliding hoặc absolute theo IdP. | Back-channel/front-channel logout phù hợp; không đồng nhất với local logout. |

**Ví dụ chính sách để thảo luận, không áp đặt:**

```text
Ứng dụng nội bộ:
- HttpSession idle: 20 phút
- HttpSession absolute: 8 giờ nếu được triển khai
- Access JWT: 5 phút
- Refresh token: dùng rotation, có absolute lifetime
- Quyền đặc biệt: step-up nếu xác thực mạnh đã quá 15 phút
- Thu hồi khi khóa tài khoản: yêu cầu hiệu lực gần như tức thời
```

Nếu nghiệp vụ chấp nhận **tối đa 5 phút** quyền cũ còn hiệu lực, JWT TTL 5 phút cộng mức clock skew, cache và thời gian truyền có thể vẫn cần đánh giá. Nếu nghiệp vụ bắt buộc thu hồi **trong vài giây**, chỉ thiết lập `exp` ngắn thường không đủ, nhất là khi token còn hiệu lực được Resource Server xác minh offline.

### 5.1. Định nghĩa “độ trễ thu hồi” (revocation latency)

**Revocation latency** là khoảng giữa thời điểm hệ thống ghi nhận một sự kiện thu hồi và thời điểm **mọi điểm thực thi quyền trong phạm vi cam kết** bắt đầu từ chối credential bị thu hồi.

Các nguồn độ trễ:

- Event chưa tới các Resource Server.
- Cache introspection/authorization còn dữ liệu cũ.
- Database/Redis replication chưa nhất quán.
- Token kiểm tra offline chỉ dựa vào `exp`.
- API gateway, service mesh và ứng dụng kiểm tra quyền ở các tầng khác nhau.
- Request đã được chấp nhận và đang xử lý trước thời điểm thu hồi.

Tài liệu vận hành cần phân biệt “thu hồi được ghi vào database” với “mọi request mới bị từ chối”. Với tác vụ nhạy cảm, cần đánh giá cả các request đang chạy và side effect đã được cho phép từ trước.

## 6. Chiến lược thu hồi theo từng loại credential

### 6.1. Session phía server

Khi logout:

1. Invalidate session của thiết bị hiện tại.
2. Dọn security context/CSRF/remember-me theo cấu hình.
3. Yêu cầu browser xóa session cookie.
4. Kiểm thử gửi lại **cookie cũ** bị từ chối.
5. Nếu có nhiều node, bảo đảm session store dùng chung ghi nhận trạng thái xóa trên mọi node.

Nếu quản trị viên muốn **đăng xuất tất cả thiết bị**, cần theo dõi session thuộc cùng user và xóa/đánh dấu vô hiệu từng session. `HttpSession.invalidate()` của một request **không mặc định thu hồi toàn bộ session ở mọi nơi**.

Nếu dùng Spring Session/Redis/JDBC, theo dõi repository/namespace, TTL, replication và độ trễ xóa. Khi hệ thống có sticky session, test qua nhiều node để tránh một node giữ bản sao session đã bị thu hồi ở node khác.

### 6.2. Opaque access token và introspection

Một Resource Server nhận opaque bearer token có thể hỏi Authorization Server qua **token introspection** xem token còn `active` hay không. Nếu token bị thu hồi và introspection trả inactive, API từ chối. Đánh đổi là thêm độ trễ và phụ thuộc tính sẵn sàng của dịch vụ introspection; caching phải tương thích với cam kết thu hồi.

**Không mặc định** rằng cứ dùng opaque token là “thu hồi tức thời”, nếu Resource Server hoặc gateway cache kết quả `active=true` trong một khoảng quá dài. Mốc đáp ứng revocation SLO phải tính cả TTL cache.

### 6.3. JWT access token tự chứa

Một JWT có chữ ký hợp lệ và `exp` chưa tới có thể được Resource Server chấp nhận **offline**. Authorization Server xóa record refresh token **không đổi chữ ký hay `exp` của JWT đã cấp**.

Các hướng thiết kế:

- **Access token sống ngắn:** giảm khoảng cửa sổ lộ token nhưng không đảm bảo thu hồi ngay.
- **Denylist theo `jti`/token digest:** tại mỗi request quan trọng, Resource Server kiểm tra token có bị thu hồi chưa; record thu hồi được giữ ít nhất đến khi token chắc chắn hết hiệu lực, có tính clock skew/cache.
- **Token version / user security epoch:** lưu phiên bản/“tokens valid after” ở server; JWT chứa giá trị ràng buộc. Khi khóa hoặc đổi quyền, tăng version. Resource Server phải **truy vấn/đồng bộ đáng tin cậy** phiên bản tại thời điểm phù hợp.
- **Opaque token introspection:** dịch chuyển việc kiểm tra trạng thái sang máy chủ có thể từ chối ngay.
- **Mô hình quyền nhạy cảm:** kiểm tra trạng thái account/tenant tại service ngay trước thao tác, hoặc yêu cầu reauthentication/step-up.

**Không coi JWT tự chứa là có thể “xóa” khỏi client.** Xóa bản local không thu hồi bản sao bị đánh cắp. Thay khóa ký là một biện pháp cực mạnh làm mất hiệu lực nhiều token, có thể cần trong sự cố nhưng không phải thao tác logout bình thường.

### 6.4. Refresh token và token family

Refresh token thường cho phép client xin access token mới, vì vậy mất refresh token có thể duy trì truy cập lâu hơn mất access token. Các biện pháp:

- Chỉ phát cho client/flow có nhu cầu và được policy cho phép.
- Bảo vệ lưu trữ; không đưa vào URL, localStorage hoặc log nếu chưa đánh giá rủi ro.
- Áp dụng **refresh token rotation** hoặc sender-constrained refresh token theo yêu cầu bảo mật và loại client.
- Ràng buộc token với client, grant, thiết bị/phiên hoặc token family phù hợp.
- Hạn idle và absolute, revoke khi logout/đổi mật khẩu/phát hiện compromise theo chính sách.
- Phát hiện token cũ bị dùng lại (**reuse detection**) và thu hồi family/grant khi xác định có replay trái phép.

**Thu hồi refresh token không mặc định làm access token cũ biến mất.** Nếu cam kết cắt quyền ngay, cần kết hợp với cơ chế thu hồi access token tại Resource Server.

### 6.5. Service account và client credentials

Một worker dùng OAuth `client_credentials` thường **không có browser session của con người**. Khi service secret bị lộ:

1. Disable/rotate credential tại Identity Provider.
2. Thu hồi grant/token nếu nhà cung cấp hỗ trợ và đánh giá access token còn hạn.
3. Phát hành credential mới, cập nhật secret manager/workload identity.
4. Deploy an toàn, kiểm tra client cũ bị từ chối và client mới hoạt động.
5. Kiểm toán các API đã được gọi trong khoảng nghi ngờ.

Không “logout browser” để giải quyết lộ client secret. Không dùng tài khoản người thật làm service account chỉ để dùng chung session/password.

## 7. Refresh token rotation và phát hiện reuse theo mô hình giao dịch

Giả sử client sở hữu refresh token `R1`:

```text
Lần refresh hợp lệ:
Client -> POST /token với R1
Authorization Server:
  - Xác thực client và R1
  - Đánh dấu R1 đã dùng
  - Sinh access token A2 và refresh token R2
Client <- A2, R2

Sau đó kẻ khác dùng lại R1:
Authorization Server -> phát hiện R1 đã được rotate
                      -> áp dụng chính sách replay/compromise
                      -> có thể thu hồi token family/grant chứa R2
```

Bản ghi refresh token nên lưu **hash hoặc vật liệu xác minh token**, không nhất thiết lưu plaintext token. Cần thao tác thay token **nguyên tử**, thường dùng transaction/compare-and-swap, để hai request refresh đồng thời không cùng được chấp nhận là người sở hữu hợp lệ.

Thuật toán nghiệp vụ minh họa:

```text
refresh(client, presentedRefreshToken):
    record = lookupBySecureTokenDigest(...)
    begin atomic transaction / lock relevant token family

    if record missing, expired, revoked or client mismatch:
        reject without disclosing token details

    if record already spent:
        evaluate reuse policy for the family
        revoke affected grant/family if compromise is suspected
        commit and reject

    mark record spent
    issue new refresh token within permitted absolute lifetime
    associate replacement with same family, bind to client
    issue new access token with bounded scope/audience/exp
    commit

    return access token + replacement refresh token
```

**Không copy đoạn pseudocode thành implementation production.** Phải giải quyết mã hóa/hash và entropy, race condition, rollback, token family ownership, retry hợp lệ, lưu trữ phân tán, idempotency và phản hồi khi mạng lỗi. Ví dụ client gửi request refresh hợp lệ nhưng không nhận được response vì mất mạng: việc retry R1 có thể trông giống replay. Thiết kế cần chính sách **grace/đồng bộ request phía client/giải quyết race** tương ứng mà không đánh đổi khả năng phát hiện token bị đánh cắp.

Trong nhiều kiến trúc, **refresh token rotation + reuse detection** quan trọng hơn cố kéo dài tuổi thọ một access token đơn lẻ. Tuy nhiên nó không thay thế kiểm tra access token khi cần thu hồi quyền tức thời.

## 8. Ví dụ Java 17 độc lập: thời hạn và danh sách token đã thu hồi

Để thấy rõ hai điều kiện “chưa hết hạn” và “chưa bị thu hồi” là khác nhau, ta viết một chương trình **chạy độc lập bằng JDK 17**, không cần Spring Boot.

Tệp `TokenLifetimeDemo.java`:

```java
import java.time.Instant;
import java.util.HashSet;
import java.util.Set;

public final class TokenLifetimeDemo {

    record AccessToken(String id, Instant expiresAt) {}

    static boolean accepted(
            AccessToken token,
            Instant at,
            Set<String> revokedIds
    ) {
        boolean notExpired = at.isBefore(token.expiresAt());
        boolean notRevoked = !revokedIds.contains(token.id());
        return notExpired && notRevoked;
    }

    public static void main(String[] args) {
        Instant issuedAt = Instant.parse("2026-01-01T00:00:00Z");
        AccessToken token = new AccessToken(
            "demo-token-id",
            issuedAt.plusSeconds(300)
        );

        Set<String> revoked = new HashSet<>();

        System.out.println(
            "before_expiry=" +
            accepted(token, issuedAt.plusSeconds(299), revoked)
        );
        System.out.println(
            "at_expiry=" +
            accepted(token, issuedAt.plusSeconds(300), revoked)
        );

        // Thu hồi trước khi hết hạn danh nghĩa.
        revoked.add(token.id());
        System.out.println(
            "after_revoke=" +
            accepted(token, issuedAt.plusSeconds(30), revoked)
        );
    }
}
```

Biên dịch và chạy:

```bash
javac TokenLifetimeDemo.java
java TokenLifetimeDemo
```

**Kết quả stdout chính xác:**

```text
before_expiry=true
at_expiry=false
after_revoke=false
```

Giải thích:

- Sau 299 giây, `at < exp` nên chưa hết hạn.
- Đúng thời điểm 300 giây, `at` không còn trước `exp` nên hết hạn theo mô hình này.
- Thu hồi `demo-token-id` khiến token bị từ chối **ngay cả khi còn trước exp**.

**Đây là mô hình quyết định thời gian, không phải hệ thống xác thực JWT.** Nó không xác minh chữ ký, issuer, audience, thuật toán, token binding hay lưu trạng thái chia sẻ. `HashSet` chỉ nằm trong bộ nhớ process; mất trạng thái khi restart và không đồng bộ nhiều instance. Trong production, danh tính token/`jti` phải được tạo đủ khó đoán, kiểm tra sau khi token đã được xác minh hợp lệ, và trạng thái revoked phải được chia sẻ giữa các điểm kiểm tra quyền. Clock skew phải được tính theo validator thực sự.

## 9. Spring Boot 3.x: một ứng dụng session cookie có logout và CSRF

Ví dụ tập trung vào **local HTTP session** của người dùng tương tác, không giả lập rằng nó tự thu hồi OAuth JWT. Dùng Java 17+, Spring Boot 3.x, Spring Security 6.x Servlet. Chính sách minh họa:

- Người dùng có thể login bằng form ở `/login`.
- `GET /private/home` chỉ cho người đã xác thực.
- `POST /private/save` yêu cầu authentication **và** CSRF token hợp lệ.
- `POST /logout` với CSRF hợp lệ invalidate session và trả 204 No Content.
- Không công khai endpoint không khai báo.
- Idle timeout được cấu hình qua Servlet container; test thực tế phải dùng container/session store để kiểm tra sau timeout.

### 9.1. Dependency

Trong `build.gradle` (Groovy DSL) của dự án Spring Boot đã có plugin, khai báo:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây là **trích đoạn dependencies**, không phải file build script đầy đủ. Tất cả Java class dưới đây dùng package `demo.lifetime`.

### 9.2. Main class

Tệp `src/main/java/demo/lifetime/LifetimeApplication.java`:

```java
package demo.lifetime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LifetimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(LifetimeApplication.class, args);
    }
}
```

### 9.3. Security configuration

Tệp `src/main/java/demo/lifetime/SecurityConfig.java`:

```java
package demo.lifetime;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/csrf", "/error").permitAll()
                .requestMatchers("/private/**").authenticated()
                .anyRequest().denyAll()
            )
            .csrf(Customizer.withDefaults())
            .formLogin(form -> form
                .defaultSuccessUrl("/private/home", true)
                .permitAll()
            )
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
                .logoutSuccessHandler((request, response, authentication) ->
                    response.setStatus(HttpServletResponse.SC_NO_CONTENT)
                )
                .permitAll()
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("operator")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }
}
```

Phân tích:

1. `.formLogin(...)` sử dụng login page/form filter của Spring Security và session. `permitAll()` của login cho phép vào đúng endpoint xác thực mà không mở `/private/**`.
2. `.csrf(Customizer.withDefaults())` giữ CSRF, trong đó `POST /logout` và `POST /private/save` phải có token hợp lệ.
3. `invalidateHttpSession(true)` hủy session hiện tại ở server; `clearAuthentication(true)` dọn ngữ cảnh; `deleteCookies("JSESSIONID")` yêu cầu client xóa cookie. **Phép thử quan trọng vẫn là phía server từ chối session ID cũ.**
4. `204` chỉ là hợp đồng thành công tùy chỉnh của bài học. Mặc định Spring Security thường redirect tới `/login?logout` sau logout. Khi tích hợp với UI thực, chọn redirect/JSON/status đúng nhu cầu.
5. `anyRequest().denyAll()` giúp tránh endpoint mới vô tình công khai. Với anonymous request bị deny, Spring Security có thể redirect đến login; phải test theo hợp đồng của form login, không mặc định đó là 403.
6. Ví dụ không bật remember-me, OAuth2 login hay JWT; nếu triển khai chúng, phải bổ sung chính sách revoke và test riêng.
7. Mật khẩu trong source chỉ để học/test. Production cần quản lý người dùng và bí mật an toàn, HTTPS, hạn chế brute-force, MFA khi có rủi ro và chính sách session riêng.

### 9.4. Controller

Tệp `src/main/java/demo/lifetime/LifetimeController.java`:

```java
package demo.lifetime;

import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class LifetimeController {

    @GetMapping("/api/public/csrf")
    public Map<String, String> csrf(CsrfToken csrfToken) {
        // Khi getToken() được gọi, deferred token được resolve.
        return Map.of(
            "headerName", csrfToken.getHeaderName(),
            "token", csrfToken.getToken()
        );
    }

    @GetMapping("/private/home")
    public Map<String, String> home(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @PostMapping("/private/save")
    public Map<String, Boolean> save() {
        return Map.of("saved", true);
    }
}
```

Endpoint `/api/public/csrf` hỗ trợ học/kiểm thử CSRF với trình duyệt/HTTP client. Sau login hoặc logout, Spring Security có thể xóa CSRF token cũ nên client cần lấy token mới trước một POST tiếp theo. Trong production, không công khai CSRF token cho origin không được tin cậy; kiểm soát CORS, cookie và phương thức đọc token theo ứng dụng thực tế.

### 9.5. Cấu hình idle timeout

Có thể đặt cho ứng dụng demo:

```yaml
# src/main/resources/application.yml
server:
  servlet:
    session:
      timeout: 20m
```

Với production, bổ sung cấu hình cookie/TLS như phần 4.1. **Không thêm `SessionCreationPolicy.STATELESS`** cho chuỗi form-login cần dùng session; điều đó không phù hợp mục tiêu minh họa.

Ứng dụng có absolute lifetime cần logic bổ sung, ví dụ lưu thời điểm xác thực gốc ở một trạng thái server đáng tin cậy và kiểm tra trước các thao tác quan trọng, không chỉ đọc cookie expiration. Những trường hợp nâng quyền cao có thể yêu cầu step-up authentication ngay cả khi session chưa hết hạn.

## 10. MockMvc kiểm thử logout, CSRF và quyền phiên

Một bộ test unit/integration ở lớp Spring Security giúp phát hiện lỗi cấu hình. Nó **chưa thay thế** test session timeout của Servlet container hoặc replay cookie HTTP thật, nhưng cho phép kiểm tra hành vi logout cơ bản.

Tệp `src/test/java/demo/lifetime/LifetimeSecurityTests.java`:

```java
package demo.lifetime;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LifetimeSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousRequestRequiresLogin() throws Exception {
        mvc.perform(get("/private/home"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void authenticatedUserCanReadPrivatePage() throws Exception {
        mvc.perform(get("/private/home")
                .with(user("operator").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("operator"));
    }

    @Test
    void validFormLoginCreatesServerSession() throws Exception {
        MvcResult result = login();

        MockHttpSession session = (MockHttpSession)
            result.getRequest().getSession(false);

        assertNotNull(session);
        assertFalse(session.isInvalid());
    }

    @Test
    void unsafeRequestWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/private/save")
                .with(user("operator").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unsafeRequestWithCsrfAndAuthenticationWorks()
            throws Exception {
        mvc.perform(post("/private/save")
                .with(user("operator").roles("USER"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.saved").value(true));
    }

    @Test
    void logoutWithoutCsrfDoesNotInvalidateSession()
            throws Exception {
        MockHttpSession session = sessionFromLogin();

        mvc.perform(post("/logout").session(session))
            .andExpect(status().isForbidden());

        assertFalse(session.isInvalid());
    }

    @Test
    void logoutWithCsrfInvalidatesSession() throws Exception {
        MockHttpSession session = sessionFromLogin();

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().isNoContent());

        assertTrue(session.isInvalid());
    }

    @Test
    void getLogoutMustNotInvalidateSession() throws Exception {
        MockHttpSession session = sessionFromLogin();

        mvc.perform(get("/logout").session(session));

        // Status có thể là trang xác nhận do Spring Security tạo.
        // GET không được kích hoạt thao tác logout.
        assertFalse(session.isInvalid());
    }

    private MvcResult login() throws Exception {
        return mvc.perform(
                formLogin()
                    .user("operator")
                    .password("demo-password")
            )
            .andExpect(status().is3xxRedirection())
            .andReturn();
    }

    private MockHttpSession sessionFromLogin() throws Exception {
        MockHttpSession session = (MockHttpSession)
            login().getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }
}
```

Chạy bằng Gradle wrapper của dự án đã cấu hình:

```bash
./gradlew test --tests demo.lifetime.LifetimeSecurityTests
```

**Kết quả kỳ vọng:** 8 test PASS khi lớp/cấu hình ở trên được sử dụng trong Spring Boot tương thích. Không khẳng định đã chạy chương trình trong tài liệu. Các assertion được viết nhằm kiểm tra:

| Test | Kết quả kỳ vọng | Điều chứng minh |
| --- | --- | --- |
| Anonymous GET private | Redirect đến login | Có rào xác thực theo form login. |
| Mock user GET private | 200, đúng username | Quy tắc truy cập private có hiệu lực. |
| Form login | 3xx, có session không invalid | Form login tạo session để duy trì trạng thái. |
| POST không CSRF | 403 | CSRF protection chặn unsafe request. |
| POST có user + CSRF | 200 | Request hợp lệ không bị chặn nhầm. |
| Logout thiếu CSRF | 403, session còn hợp lệ | Không bị logout bằng POST thiếu token. |
| Logout có CSRF | 204, session bị invalid | Logout handler hủy session phía server. |
| GET logout | Session vẫn không invalid | GET không phải thao tác hủy phiên trong cấu hình này. |

**Giới hạn của MockMvc:** `MockHttpSession` là đối tượng mô phỏng. Kiểm tra `isInvalid()` chứng minh logout handler gọi invalidate trong môi trường test, nhưng **không chứng minh** browser gửi lại cookie cũ qua mạng bị Servlet container từ chối hoặc idle timeout của session store hoạt động. Các mục đó cần HTTP integration test.

### 10.1. Cách kiểm thử replay cookie thật

Trong một `@SpringBootTest(webEnvironment = RANDOM_PORT)` hoặc môi trường staging qua HTTP client có thể lưu cookie thủ công, xây kịch bản:

1. GET endpoint trả CSRF token, ghi lại `Set-Cookie: JSESSIONID=...` của phiên anonymous.
2. POST `/login` với username/password và CSRF token hợp lệ, lưu **JSESSIONID sau login** (session ID có thể được thay đổi để chống fixation).
3. GET `/private/home` với cookie sau login: kỳ vọng 200.
4. Lấy CSRF token hợp lệ của phiên đã login, POST `/logout` với cookie đó: kỳ vọng 204.
5. **Bỏ qua header xóa cookie** và cố tình gửi lại **chính JSESSIONID trước logout**: GET `/private/home` phải bị từ chối theo hợp đồng (thường redirect login).
6. Đăng nhập lại tạo session mới: session mới truy cập được, session đã logout **không sống lại**.

Đừng chỉ xóa cookie khỏi client rồi thử truy cập; cách đó không chứng minh server đã invalidate session. Cũng đừng dùng `MockHttpSession.invalidate()` rồi gọi đó là test idle timeout.

### 10.2. Cách kiểm thử idle timeout thật

Trong môi trường test cô lập:

1. Tạo session bằng login thật qua container.
2. Đặt timeout ngắn bằng cơ chế test-only, ví dụ `session.setMaxInactiveInterval(2)` cho **session test**; không tạo endpoint công khai cho phép người ngoài điều chỉnh timeout.
3. Dừng tất cả polling/heartbeat dùng cùng session.
4. Sau khi vượt giới hạn idle với khoảng đệm cho độ phân giải container, gửi lại cookie cũ đến private endpoint.
5. Xác minh bị từ chối, session mới không bị hiểu nhầm là session cũ.
6. Lặp lại khi triển khai Spring Session/Redis và qua nhiều node nếu đó là kiến trúc thực.

Với container có độ phân giải thời gian theo phút hoặc session repository phân tán, đừng giả định `server.servlet.session.timeout: 1s` luôn tạo kết quả chính xác sau một giây. Tăng khoảng chờ hoặc dùng cơ chế test tương ứng và quan sát trạng thái chấp nhận request.

## 11. Spring Security OAuth2 Resource Server: expire không đồng nghĩa revoke

Để nhận bearer JWT thay vì form session, dự án backend cần:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
```

Cấu hình minh họa:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.invalid/realm/demo
```

và trong chain API stateless:

```java
// Trích đoạn cấu hình cho một API bearer-only, không phải thay thế
// trực tiếp cho SecurityConfig form-login ở phần 9.
http
    .securityMatcher("/api/**")
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
    )
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/private/**").authenticated()
        .anyRequest().denyAll()
    )
    .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()));
```

**Điều phải kiểm tra thêm trước production:**

- `issuer-uri` phải là issuer thật, tin cậy, đã cấu hình JWT/JWK discovery phù hợp; URL `.invalid` ở trên chỉ minh họa.
- Kiểm tra `aud` (audience) dành cho API, không chỉ chữ ký/issuer, khi profile nhà cung cấp hoặc chính sách ứng dụng yêu cầu.
- Kiểm tra exp/nbf/iat và clock skew thực tế.
- Map scopes/roles theo hợp đồng với Authorization Server; không tự tin claim người gọi gửi trong body.
- Phân biệt JWT user với service token nếu quyền/endpoint yêu cầu.
- Chọn cơ chế thu hồi nếu hợp đồng cần cắt quyền trước thời điểm exp.
- Trả 401/403 và `WWW-Authenticate` đúng, không leak giá trị token vào URL/error log.

**Quan trọng:** đoạn config trên chưa tự thêm denylist, introspection, token version hay bảo đảm revoke tức thời. Nó cũng không cấp/rotate refresh token; việc cấp token thuộc Authorization Server/OAuth2 Client, không phải tính năng tự động của Resource Server.

### 11.1. Đổi từ JWT offline sang opaque introspection khi nào?

Khi yêu cầu thu hồi rất nhanh, hệ thống có thể chọn opaque token với introspection ở Authorization Server, hoặc JWT nhưng Resource Server kiểm tra thêm trạng thái đáng tin cậy. Đánh đổi:

| Mô hình | Ưu điểm | Hạn chế |
| --- | --- | --- |
| JWT offline, access TTL ngắn | Ít phụ thuộc mạng khi kiểm tra token; throughput cao. | Khó thu hồi ngay nếu chỉ kiểm tra chữ ký/exp. |
| JWT + distributed denylist/version | Có thể thu hồi sớm trước exp. | Phụ thuộc store/synchronization; kiểm tra mỗi request tăng chi phí. |
| Opaque + introspection | Authorization Server kiểm soát trạng thái `active` tập trung. | Phụ thuộc introspection endpoint; cache làm tăng độ trễ thu hồi. |
| Session server-side | Có thể xóa record session ngay trong store. | Phụ thuộc session store và đồng bộ nhiều node. |
| Gateway kiểm tra token tập trung | Một nơi chuẩn hóa kiểm tra đầu vào. | Dịch vụ nội bộ vẫn cần threat model/authorization; tránh tin bypass gateway. |

Không có “JWT luôn kém an toàn” hoặc “opaque luôn tức thời”. Điều quyết định là **cách triển khai thời gian sống, xác thực, thu hồi và cache** có đáp ứng chính sách hay không.

## 12. Quy trình thu hồi truy cập khi có sự kiện bảo mật

Một playbook nên chỉ rõ **sự kiện kích hoạt, phạm vi, hành động, kiểm chứng và người chịu trách nhiệm**. Bốn tình huống thường gặp:

### 12.1. Người dùng chủ động logout trên một thiết bị

- Invalidate local session hiện tại.
- Clear security context/CSRF, remember-me nếu chính sách yêu cầu.
- Xóa cookie phía client và dữ liệu nhạy cảm trong state frontend.
- Nếu ứng dụng có refresh token do client nắm giữ, gửi yêu cầu revoke theo cơ chế được hỗ trợ.
- Nếu cần logout IdP, sử dụng luồng OIDC logout phù hợp, tránh khẳng định local logout đã logout mọi RP.
- Replay cookie/token cũ để xác minh phần nào thực sự bị từ chối.

### 12.2. Người dùng chọn “logout mọi thiết bị”

- Xác định danh sách session, refresh grants và thiết bị thuộc user.
- Xóa hoặc đánh dấu hết hiệu lực tất cả session liên quan trong kho session chung.
- Thu hồi refresh token family/grant tương ứng; với access JWT còn hạn, kích hoạt chính sách denylist/token version hoặc chấp nhận giới hạn TTL đã công bố.
- Không thu hồi nhầm các session/service không thuộc user.
- Kiểm thử qua nhiều thiết bị, browser và API; đo revocation latency.

### 12.3. Khóa tài khoản hoặc đổi mật khẩu vì nghi ngờ xâm phạm

- Dừng khả năng xác thực mới bằng thông tin cũ, khóa/reset credential.
- Thu hồi các session và refresh token theo policy.
- Xác định liệu access token cũ có thể gọi API đến khi exp; nếu rủi ro cao cần cơ chế từ chối ngay tại Resource Server.
- Thu hồi quyền/cập nhật role cache, đánh giá các request/tác vụ đang chạy.
- Tạo audit record và correlation ID an toàn, cảnh báo/điều tra theo quy trình.
- Yêu cầu người dùng xác thực lại bằng kênh đáng tin cậy sau khắc phục.

### 12.4. Lộ service credential hoặc token máy–máy

- Xác định client ID, secret/certificate, issuer, audience, scope và những môi trường bị ảnh hưởng.
- Disable hoặc rotate credential tại nguồn cấp.
- Thu hồi grant/token và chặn access token còn hạn theo khả năng của hạ tầng.
- Phát hành credential mới qua secret manager/workload identity, deploy an toàn không ghi log secret.
- Kiểm thử client cũ bị từ chối, client mới hoạt động; theo dõi truy cập bất thường.
- Không giải quyết bằng cách xóa cookie phiên của một nhân viên.

### 12.5. Thu hồi phải có bằng chứng và báo cáo

Ví dụ timeline sự cố:

```text
10:00:00 Phát hiện refresh token family F có dấu hiệu replay
10:00:02 Authorization Server đánh dấu F revoked
10:00:03 Clients không thể refresh từ F
10:00:07 Resource Servers nhận event/cập nhật cache denylist
10:00:08 Request mới với access token thuộc F bị từ chối
10:00:09 Kiểm tra tất cả zone/instance kết thúc
```

Các mốc trên **chỉ minh họa cách báo cáo**, không phải SLA mặc định. Để có cam kết “thu hồi trong 10 giây”, cần đo thực tế bằng request thử nghiệm qua tất cả điểm thực thi quyền, không chỉ xem log “revoke succeeded” ở Authorization Server.

## 13. Thiết kế phân tán: đừng để một node vẫn nhận quyền đã thu hồi

### 13.1. Spring Session và session store

Với nhiều instance Spring Boot:

```text
Browser -> Load Balancer
              |-> App A
              |-> App B
              |-> App C
                     |
                 Shared Session Store (Redis/JDBC...)
```

Nếu session nằm trong bộ nhớ từng node và thiếu chiến lược phù hợp, request có thể mất đăng nhập khi chuyển node. Nếu dùng session store chung, logout từ node A phải khiến request với session ID cũ tới B/C bị từ chối. Nhưng còn phải xét cache cục bộ, TTL, replication, sticky routing và việc xử lý request đang chạy.

**Test phân tán cần vượt qua load balancer hoặc ép qua từng node**. Chỉ test `HttpSession.invalidate()` trên một JVM không chứng minh toàn cụm từ chối session ID cũ.

### 13.2. Denylist hoặc token version dùng chung

Một `HashSet` trong một instance không thể bảo vệ toàn hệ thống. Nếu chọn denylist JWT:

- Dùng store chia sẻ với độ bền/tính nhất quán phù hợp (ví dụ Redis được thiết kế/giám sát cho mục đích này).
- Lưu `jti` hoặc digest định danh phù hợp, không log full token; có TTL đủ dài tính tới `exp` và clock skew.
- Định nghĩa khi store không sẵn sàng: **fail-open hay fail-closed**? Với quyền nhạy cảm, fail-open có thể vi phạm cam kết thu hồi; fail-closed tăng rủi ro gián đoạn dịch vụ.
- Theo dõi cache invalidation, event lag, region replication và khả năng phục hồi sau restart.
- Không đánh dấu “revoked” chỉ ở database quản trị nếu những Resource Server không bao giờ đọc trạng thái đó.

### 13.3. Trạng thái role và token còn hiệu lực

Nếu role mới/role cũ được nhúng vào JWT, thay role ở database **không tự sửa nội dung JWT đã ký**. Các phương án gồm access token TTL ngắn, revoke token version, kiểm tra quyền động tại service hoặc phát hành token mới sau khi thay đổi quyền. Hãy phân biệt **thu hồi xác thực** và **thu hồi một authority**: có thể người dùng vẫn được đăng nhập nhưng bị cấm một hành động mới.

## 14. Bẫy bảo mật và vận hành thường gặp

1. **Chỉ xóa cookie rồi kết luận logout an toàn.** Nếu server chưa hủy session, bản sao cookie vẫn dùng được.
2. **Chỉ invalidate session hiện tại rồi hứa “logout mọi thiết bị”.** Nhiều thiết bị có session riêng; còn refresh grants và IdP session.
3. **Nhầm `server.servlet.session.timeout` với `exp` của JWT.** Đây là hai cơ chế ở hai hệ thống khác nhau.
4. **Tin rằng JWT tự hết hạn khi người dùng logout.** `exp` không thay đổi chỉ vì local logout.
5. **Thu hồi refresh token rồi nghĩ access token bị revoke ngay.** Access token đã cấp vẫn có thể dùng nếu Resource Server chưa kiểm tra trạng thái thu hồi.
6. **Để access token sống rất lâu vì “đỡ refresh”.** Gia tăng cửa sổ sử dụng nếu token bị lộ.
7. **Cho refresh token trượt vô hạn không absolute TTL.** Nguy cơ phiên “không bao giờ kết thúc” và khó kiểm soát compromised client.
8. **Xử lý refresh rotation không nguyên tử.** Hai request có thể đồng thời dùng cùng token cũ, làm mất khả năng phát hiện replay chính xác.
9. **Tự động khóa mọi token family khi retry hợp lệ sau lỗi mạng.** Cần thiết kế transaction, retry và grace phù hợp.
10. **Dùng `HashSet` cục bộ làm denylist production.** Các node khác vẫn chấp nhận JWT.
11. **Dùng clock skew quá lớn.** Kéo dài thời gian token được chấp nhận hơn yêu cầu.
12. **Không tính cache kết quả introspection.** AS đã trả revoked nhưng gateway vẫn dùng cache active cũ.
13. **Đặt TTL bằng cookie `Max-Age` mà quên server session.** Client cookie và session store là hai vòng đời riêng.
14. **Quên CSRF khi thêm logout hoặc POST có cookie.** `POST /logout` cần CSRF theo cấu hình mặc định; không chuyển tùy tiện sang GET.
15. **Không xem remember-me hoặc SSO.** Session mới có thể được khôi phục sau khi local session hết hạn; phải phân biệt với việc session cũ sống lại.
16. **Kéo dài session nhờ polling nền mà không chủ đích.** Idle timeout mất ý nghĩa với “người dùng không hoạt động” nếu mọi request đều refresh nó.
17. **Dùng token thật để kiểm thử.** Không gửi credential production vào URL, shell history, ticket hoặc test log.
18. **In toàn bộ JWT/refresh token trong log để debug revocation.** Ghi ID/claim tối thiểu đã thẩm định, tránh raw secret.
19. **Không có fallback khi denylist/repository gặp lỗi.** Quyết định fail-open/fail-closed phải được định nghĩa, giám sát và kiểm thử.
20. **Chỉ kiểm thử request thành công.** Phải kiểm tra trạng thái cũ sau logout/timeout/role revoke, qua nhiều node và dưới tải.
21. **Tin rằng nhấn Back hiển thị trang cũ nghĩa session vẫn sống.** Đó có thể là cache/SPA state; phải thử request mới tới server.
22. **Thu hồi credential mà quên tác vụ đang chạy.** Request đã được cho phép trước revocation có thể vẫn hoàn thành; cần chính sách tại điểm side effect quan trọng.

## 15. Ma trận kiểm thử chấp nhận khi triển khai

| Tình huống | Kiểm thử thực hiện | Kết quả mong đợi |
| --- | --- | --- |
| Session login | Login đúng rồi GET private | Được phép; session ID không bị lộ trong URL/log. |
| Session không hoạt động | Không gửi request sau idle timeout, rồi replay cookie | Session cũ không được chấp nhận. |
| Session đang hoạt động | Gửi request trước khi hết idle | Chỉ được kéo dài nếu chính sách cho phép. |
| Absolute session lifetime | Giữ session hoạt động liên tục tới giới hạn tuyệt đối | Bị yêu cầu xác thực lại/thu hồi theo chính sách. |
| Logout thiếu CSRF | POST logout không token | Bị từ chối, không logout ngoài ý muốn. |
| Logout có CSRF | POST logout với session và CSRF hợp lệ | Hủy session; cookie cũ replay bị từ chối. |
| Logout mọi thiết bị | Tạo hai session rồi revoke all | Cả hai session đều bị từ chối; không chỉ browser hiện tại. |
| JWT trước exp | Token hợp lệ đúng issuer/audience/signature | Cho phép theo quyền, nếu chưa revoked. |
| JWT tại/qua exp | Gửi token sau boundary tính cả clock skew | Từ chối khi qua giới hạn validator thực tế. |
| JWT sai issuer/audience/chữ ký | Gửi token thử nghiệm không đúng | 401, không tin dữ liệu chưa xác minh. |
| JWT bị thu hồi trước exp | Revoke theo `jti`/version/introspection rồi gọi lại | Bị từ chối trong revocation SLO cam kết. |
| Refresh rotation | Dùng R1 → R2, dùng lại R1 | Reuse bị xử lý theo family policy, không tạo R3 ngoài ý muốn. |
| Refresh bị thu hồi | Client dùng refresh token cũ để xin access token mới | Không nhận token mới. |
| Quyền bị thu hồi | Bỏ role rồi gọi endpoint dùng token/session cũ | Quyền bị rút đúng thời hạn/chính sách. |
| Nhiều node | Logout/revoke ở A; gửi credential cũ tới B/C | Tất cả điểm kiểm tra từ chối trong giới hạn nhất quán. |
| SSO/remember-me | Local logout rồi truy cập lại từ browser | Hành vi tái đăng nhập phù hợp chính sách, phân biệt với session cũ. |
| Hạ tầng lỗi | Denylist/introspection/session store tạm mất kết nối | Fail-open/fail-closed đúng threat model; có cảnh báo. |
| Log và observability | Dùng sentinel `FAKE_TOKEN_TEST_ONLY` | Không lộ token/secret; có correlation ID an toàn. |

### 15.1. Kiểm thử TTL bằng đồng hồ kiểm soát được

Với logic cấp/kiểm tra thời gian thuần Java, nên inject `Clock` (hoặc nguồn thời gian có thể thay thế) và dùng `Clock.fixed(...)` trong unit test, tránh `Thread.sleep(...)` khi không cần. Điều đó giúp kiểm tra chính xác ngay trước/đúng/sau `exp`.

Với Servlet container, JWT decoder thật, Redis/Spring Session và IdP ngoài, đồng hồ giả ở một service **không nhất thiết đổi thời gian ở các thành phần khác**. Khi đó cần integration test tương ứng: token có `exp` đã cấp theo test issuer, session timeout thật, hoặc môi trường có đồng hồ/TTL kiểm soát. Không kết luận clock-fixed unit test đã chứng minh mọi node đồng ý về thời gian.

### 15.2. Tiêu chí đo revocation SLO

Trong môi trường thử nghiệm:

1. Cấp token giả/test có TTL xác định; ghi thời điểm issuance, `exp`, issuer và token ID đã làm sạch.
2. Xác minh request trước revoke được chấp nhận.
3. Gửi yêu cầu revoke và ghi nhận thời điểm hệ thống **cam kết** đã xử lý.
4. Liên tục thử request mới qua từng Resource Server/gateway; ghi thời điểm cuối còn chấp nhận và thời điểm đầu tất cả từ chối.
5. Đối chiếu kết quả với TTL cache, replication và mức clock skew.
6. Đảm bảo tài khoản/token mới hợp lệ vẫn làm việc, tránh “chặn tất cả” để có tỷ lệ revoke 100%.
7. Không ghi raw token vào báo cáo; dùng token ID/digest/correlation ID phù hợp.

## 16. Checklist triển khai và bài tập

Trước khi triển khai thay đổi session/token:

- **Tài liệu hóa** các thời hạn idle/absolute/expiry và giới hạn quyền cũ được phép tồn tại.
- **Phân loại credential**: browser session, access JWT/opaque, refresh grant, remember-me, IdP SSO, service secret.
- **Xác định điểm thực thi quyền**: app, gateway, Resource Server, service nghiệp vụ, session store, cache.
- **Chọn cơ chế thu hồi** có hiệu lực thực sự tại những điểm đó; đừng chỉ cập nhật UI/Authorization Server.
- **Bảo vệ token**: TLS, cookie thuộc tính phù hợp, `Authorization` header, tránh URL/log/analytics và secret trong source.
- **Giữ CSRF** cho request có cookie/credential tự gửi; test `POST /logout` và POST dữ liệu.
- **Thử lại thông tin cũ** sau revoke: cookie, access token, refresh token, permission cache.
- **Kiểm thử đa thiết bị và đa node**, bao gồm SSO, back button và ứng dụng dùng request polling.
- **Đo độ trễ thu hồi** thực tế, không chỉ quan sát sự kiện revoke.
- **Định nghĩa kịch bản sự cố** khi IdP, session store, introspection hoặc denylist không sẵn sàng.
- **Ghi log có kiểm soát**, không để session ID/token/secret xuất hiện trong ticket và trace.
- **Diễn tập rollback và key/secret rotation**, phân biệt thu hồi một client với thay toàn bộ khóa ký.

### Bài tập tình huống

Một hệ thống có các chính sách:

```text
Session idle timeout: 20 phút
JWT access token: 10 phút
Refresh token: rotation, absolute lifetime 30 ngày
Resource Server: chỉ xác minh chữ ký/exp, không có denylist
```

Vào **10:00**, tài khoản người dùng bị khóa và toàn bộ refresh token bị thu hồi. Một JWT phát hành lúc **09:58**, hết hạn lúc **10:08**.

**Câu hỏi A:** Có chắc request dùng JWT lúc 10:02 bị từ chối không?

**Không.** Với Resource Server chỉ kiểm tra chữ ký/`exp` và không xem trạng thái khóa, JWT đó có thể còn được chấp nhận đến khi hết hạn (tùy clock skew). Thu hồi refresh token chặn xin token mới, không tự vô hiệu JWT đã cấp.

**Câu hỏi B:** Làm gì nếu chính sách đòi cắt quyền trước 10:01?

Cần thêm một cơ chế từ chối access token gần như tức thời được mọi điểm thực thi quyền kiểm tra (introspection, denylist, token version/security epoch hoặc kiểm tra trạng thái account đáng tin cậy), bảo đảm propagation và cache đáp ứng ngưỡng. Sau đó đo bằng request thực tế ở các node.

**Câu hỏi C:** Nếu người dùng vẫn đăng nhập lại được qua SSO ngay sau local logout thì có chắc session cũ chưa bị xóa?

Không. IdP session có thể còn hiệu lực và tạo **session mới**. Phải đối chiếu session ID, grant và audit để phân biệt new login với old-session replay.

**Câu hỏi D:** Nếu worker gửi lại refresh token R1 do mất response mạng, có nên mặc định khóa toàn bộ tài khoản không?

Không thể có câu trả lời chung. Phải thiết kế **rotation, retry, race handling và reuse detection** theo policy, xác minh khả năng token bị đánh cắp và phạm vi grant/family bị ảnh hưởng. Khóa toàn bộ tài khoản trong mọi lỗi mạng có thể gây gián đoạn không cần thiết; bỏ qua mọi replay lại làm giảm an toàn.

## 17. Kết luận và tài liệu tham khảo

**Thời gian sống** là giới hạn quyền được chấp nhận theo thời gian; **thu hồi** là quyết định cắt quyền trước hoặc tại một mốc có kiểm soát. Chúng liên quan nhưng không thay thế nhau. Session store có thể hủy phiên phía server; access JWT tự chứa cần giới hạn `exp` và cơ chế trạng thái nếu muốn thu hồi sớm; refresh token cần vòng đời/rotation/replay protection; đăng xuất ứng dụng không mặc định đăng xuất mọi IdP, thiết bị hoặc service.

Một hệ thống triển khai tốt phải biết **credential nào đang tồn tại, ai có thể thu hồi, mọi server kiểm tra gì, độ trễ tối đa bao lâu và test nào chứng minh điều đó**.

Tài liệu chính thức:

- Spring Security 6.5 — [Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html).
- Spring Security 6.5 — [Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html).
- Spring Security 6.5 — [CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html).
- Spring Security 6.5 — [OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html).
- Spring Security 6.5 — [OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html).
- Spring Security 6.5 — [MockMvc Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/).
- Spring Session — [Integration with Spring Security](https://docs.spring.io/spring-session/reference/spring-security.html).
- OAuth 2.0 Token Revocation — [RFC 7009](https://www.rfc-editor.org/rfc/rfc7009).
- OAuth 2.0 Token Introspection — [RFC 7662](https://www.rfc-editor.org/rfc/rfc7662).
- OAuth 2.0 Security Best Current Practice — [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700).
- JWT claims `exp`, `nbf`, `iat`, `jti` — [RFC 7519](https://www.rfc-editor.org/rfc/rfc7519).