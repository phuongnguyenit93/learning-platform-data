# Xác nhận logout và xử lý yêu cầu không đủ thông tin

## 1. Bối cảnh và mục tiêu

Trong hệ thống **OAuth 2.0/OpenID Connect Authorization Server** dùng **Spring Security**, **Spring Authorization Server** và **Spring Boot**, một người dùng có thể đăng nhập vào nhiều ứng dụng (Relying Party — RP) thông qua cùng một OpenID Provider (OP). Khi người dùng bấm Logout tại một ứng dụng, RP có thể chuyển trình duyệt tới Logout Endpoint của OP để yêu cầu kết thúc phiên đăng nhập trung tâm. Cơ chế này được gọi là **RP-Initiated Logout**.

Yêu cầu logout thường mang theo `id_token_hint`, `post_logout_redirect_uri`, `client_id` và `state`. Nhưng không phải request nào cũng có đủ các tham số đó. Một số RP cũ không gửi ID Token; một số người dùng mở trực tiếp URL logout; một số request có redirect URI không được đăng ký; cũng có trường hợp ID Token thuộc phiên khác hoặc không xác định được người dùng đang đăng nhập ở OP.

Ví dụ xuyên suốt: người dùng đăng nhập vào `customer-portal` và `billing-console` qua `https://auth.example.com`. Khi bấm Logout tại portal, ứng dụng gửi `id_token_hint` cùng `post_logout_redirect_uri`. Một thiết bị kiosk lại mở trực tiếp `/connect/logout` mà không có `id_token_hint`. OP phải phân biệt hai tình huống, tránh kết thúc phiên của người dùng khác chỉ vì một URL được gọi, đồng thời vẫn cho người dùng lựa chọn logout trung tâm khi request thiếu thông tin.

Sau bài học, bạn có thể:

1. Giải thích luồng RP-Initiated Logout và vai trò của Logout Endpoint.
2. Phân biệt tham số bắt buộc, được khuyến nghị và tùy chọn trong OIDC RP-Initiated Logout 1.0.
3. Xác định khi nào OP phải yêu cầu người dùng xác nhận logout.
4. Xử lý request thiếu `id_token_hint`, `client_id`, `post_logout_redirect_uri` hoặc `state`.
5. Kiểm tra issuer, audience, client binding, session ID và trạng thái phiên của ID Token.
6. Xác minh `post_logout_redirect_uri` bằng exact match với URI đã đăng ký.
7. Thiết kế confirmation page, luồng đồng ý/từ chối và ticket một lần an toàn.
8. Tùy chỉnh `OidcLogoutEndpointConfigurer`, `OidcLogoutAuthenticationProvider`, validator và success/error handler trong Spring Authorization Server.
9. Phân biệt logout OP session với revoke access token/refresh token.
10. Kiểm thử các trường hợp thiếu dữ liệu, redirect sai, phiên không khớp và request lặp.

**Phạm vi phiên bản:** Ví dụ dùng Spring Authorization Server 1.5.x (tham chiếu API 1.5.8), Spring Security 6.x và Servlet stack. `OidcLogoutAuthenticationProvider.setAuthenticationValidator(...)` có từ Spring Authorization Server 1.4. Nếu dùng version cũ hơn, kiểm tra API tương ứng hoặc nâng cấp trước khi áp dụng ví dụ custom validator.

## 2. RP-Initiated Logout là gì?

### 2.1. Ai yêu cầu logout?

RP là ứng dụng mà người dùng đang sử dụng, ví dụ `customer-portal`. OP là Authorization Server đã xác thực người dùng, ví dụ `https://auth.example.com`. RP-Initiated Logout cho phép RP điều hướng User Agent tới Logout Endpoint của OP để yêu cầu OP kết thúc phiên đăng nhập trung tâm.

Logout Endpoint thường được RP lấy từ OpenID Provider Discovery metadata qua trường `end_session_endpoint`. Nếu OP hỗ trợ RP-Initiated Logout và Discovery, metadata phải công bố endpoint này bằng HTTPS.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as End-User
    participant RP as customer-portal
    participant OP as OpenID Provider
    participant S as SessionRegistry
    U->>RP: Bấm Logout
    RP->>RP: Kết thúc hoặc đánh dấu phiên local
    RP-->>U: Redirect tới end_session_endpoint
    U->>OP: Logout request + id_token_hint
    OP->>OP: Xác minh hint, client và session
    OP->>U: Có cần xác nhận logout OP không?
    U->>OP: Đồng ý
    OP->>S: Tìm phiên và kết thúc phiên OP
    OP-->>RP: Logout notification nếu cơ chế đã đăng ký
    OP-->>U: Trang hoàn tất hoặc redirect hợp lệ về RP
~~~

RP có thể logout local trước khi chuyển sang OP hoặc chờ logout notification từ OP. Mỗi lựa chọn có trade-off: nếu RP logout local trước, người dùng đã thoát khỏi RP ngay cả khi họ từ chối logout OP; nếu RP chờ notification, cơ chế notification không đáng tin cậy có thể khiến RP vẫn còn phiên local. Thiết kế phải thể hiện rõ cho người dùng trạng thái logout nào đã hoàn tất.

### 2.2. Logout không đồng nghĩa revoke mọi token

RP-Initiated Logout chủ yếu kết thúc phiên đăng nhập OP và phối hợp thông báo logout cho các RP có đăng ký cơ chế tương ứng. Việc logout không tự động bảo đảm mọi access token hoặc refresh token đã phát hành đều bị revoke ngay.

Nếu hệ thống cần thu hồi token, phải dùng chính sách revoke/authorization riêng, ví dụ:

- Revoke refresh token hoặc authorization tương ứng.
- Đánh dấu session/authorization đã kết thúc để introspection trả `active=false`.
- Dùng back-channel logout để RP nhận thông báo và kết thúc phiên local.
- Áp dụng TTL ngắn, token family revocation hoặc policy kiểm tra session tại Resource Server.

Không trình bày một trang “Bạn đã logout” nếu chỉ cookie OP bị xóa nhưng refresh token hoặc session ở một hệ thống khác vẫn còn hiệu lực theo thiết kế.

## 3. Các tham số logout request

OIDC RP-Initiated Logout 1.0 định nghĩa các tham số sau:

| Tham số | Mức độ | Vai trò | Cách xử lý |
| --- | --- | --- | --- |
| `id_token_hint` | RECOMMENDED | ID Token trước đó OP đã phát hành cho RP; gợi ý người dùng và phiên RP cần logout. | Xác minh OP là issuer, client/audience và liên hệ với phiên hiện tại hoặc phiên gần đây. |
| `client_id` | OPTIONAL | Client Identifier đã đăng ký tại OP. | Nếu cùng xuất hiện với `id_token_hint`, bắt buộc khớp client được dùng khi phát hành ID Token. |
| `post_logout_redirect_uri` | OPTIONAL | URI RP muốn trình duyệt quay về sau logout. | Phải khớp chính xác URI đã đăng ký hoặc được OP cho phép bằng cơ chế tương đương. |
| `state` | OPTIONAL | Giá trị opaque để RP tương quan callback logout. | Chỉ trả lại khi thực hiện redirect hợp lệ về RP. Không dùng làm bằng chứng danh tính. |
| `logout_hint` | OPTIONAL | Gợi ý về người dùng, ví dụ username hoặc session identifier. | Chỉ là hint theo policy OP; không thay thế `id_token_hint` hoặc xác thực người dùng. |
| `ui_locales` | OPTIONAL | Ngôn ngữ UI ưu tiên theo BCP 47. | Có thể bỏ qua locale không hỗ trợ mà không báo lỗi. |

`id_token_hint` được **khuyến nghị**, không phải tham số bắt buộc của mọi logout request. Vì vậy, thiếu hint không tự động đồng nghĩa request sai cú pháp. Tuy nhiên, thiếu hint làm OP khó xác định RP/người dùng/phiên mà request muốn kết thúc; chuẩn yêu cầu OP hỏi người dùng trước khi logout OP trong trường hợp này.

### 3.1. GET và POST

Logout Endpoint của OP phải hỗ trợ cả HTTP GET và POST:

- GET dùng URI Query String Serialization.
- POST dùng Form Serialization.

Ví dụ GET:

~~~http
GET /connect/logout?id_token_hint=<id-token>&post_logout_redirect_uri=https%3A%2F%2Fportal.example.com%2Flogged-out&state=abc123 HTTP/1.1
Host: auth.example.com
~~~

Ví dụ POST:

~~~http
POST /connect/logout HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

id_token_hint=<id-token>&post_logout_redirect_uri=https%3A%2F%2Fportal.example.com%2Flogged-out&state=abc123
~~~

Request POST từ RP vẫn là **logout request**, không phải bằng chứng người dùng đã bấm nút “Đồng ý” trên confirmation page của OP. OP không được coi việc RP gửi POST là xác nhận tương tác của người dùng.

## 4. Khi nào cần yêu cầu xác nhận?

### 4.1. Quy tắc từ OIDC RP-Initiated Logout 1.0

Tại Logout Endpoint, OP SHOULD hỏi người dùng có muốn logout khỏi OP hay không. Trong hai trường hợp sau, OP **MUST** hỏi:

1. Request không cung cấp `id_token_hint`.
2. ID Token được cung cấp không thuộc phiên OP hiện tại với RP và/hoặc người dùng hiện đang đăng nhập.

Nếu người dùng trả lời đồng ý, OP MUST logout End-User. Nếu người dùng từ chối, OP không được kết thúc phiên OP chỉ dựa trên request đó.

Nếu ID Token có `sid` không khớp phiên RP hiện tại hoặc một phiên gần đây tại OP, OP SHOULD coi request là đáng ngờ và MAY từ chối xử lý. Nếu ID Token đã hết `exp` nhưng RP được nhận diện qua `aud` và/hoặc `sid` vẫn có phiên hiện tại hoặc gần đây, OP SHOULD chấp nhận ID Token đó làm hint logout. Vì vậy, không nên áp dụng máy móc quy tắc “ID Token hết hạn thì không thể dùng để logout”.

### 4.2. Bảng quyết định

| Tình huống | Xác nhận người dùng | Logout OP | Redirect về RP |
| --- | --- | --- | --- |
| ID Token hợp lệ, đúng issuer/client và gắn với phiên hiện tại | Nên hỏi; chuẩn yêu cầu hỏi nếu chính sách OP áp dụng xác nhận cho mọi logout. | Khi người dùng đồng ý. | Nếu URI hợp lệ và đã đăng ký. |
| Không có `id_token_hint`, có phiên OP đang đăng nhập | **Bắt buộc hỏi.** | Chỉ khi người dùng đồng ý. | Chỉ khi OP có cách khác xác nhận tính hợp lệ của đích redirect. |
| Không có `id_token_hint`, không có phiên OP | Không có phiên để logout; có thể hiển thị trạng thái đã đăng xuất. | Không có thao tác phiên; xử lý idempotent. | Không redirect nếu chưa xác minh được RP và URI. |
| ID Token hint hợp lệ về chữ ký nhưng không khớp người dùng/phiên hiện tại | **Bắt buộc hỏi.** | Chỉ khi người dùng hiện tại đồng ý; không logout người dùng được nêu bởi hint một cách âm thầm. | Chỉ khi đích redirect đã được xác minh độc lập. |
| `client_id` và hint mismatch | Request đáng ngờ; từ chối thao tác phụ thuộc dữ liệu sai. | Không logout theo request sai. | Không redirect. |
| `post_logout_redirect_uri` không đăng ký hoặc không exact-match | Có thể hiển thị lỗi hoặc hỏi người dùng có muốn logout OP mà không quay lại RP không. | Có thể tiếp tục nếu người dùng xác nhận và policy cho phép. | **Không redirect** tới URI sai. |
| Chỉ có `logout_hint` | Không coi hint là bằng chứng danh tính; hỏi người dùng hiện tại nếu có phiên. | Chỉ khi người dùng hiện tại đồng ý. | Không redirect nếu chưa xác minh client/URI. |
| Chỉ có `state` | State không xác thực client hay người dùng. | Không tự logout dựa trên state. | Không echo state khi không redirect hợp lệ. |

### 4.3. Thiết kế confirmation page

Confirmation page nên nói rõ người dùng đang xác nhận điều gì:

- “Bạn có muốn đăng xuất khỏi tài khoản trên tất cả ứng dụng đang dùng phiên đăng nhập này không?”
- Nêu ứng dụng khởi tạo nếu OP xác định được client đáng tin cậy.
- Cho hai lựa chọn rõ ràng: “Đăng xuất” và “Ở lại”.
- Không hiển thị thông tin định danh nhạy cảm chỉ dựa trên `logout_hint`.
- Nếu request có redirect URI không hợp lệ, giải thích OP sẽ không chuyển trình duyệt tới địa chỉ đó.

Không hiển thị một nút “Tiếp tục” mơ hồ rồi tự động logout. Người dùng phải hiểu họ đang kết thúc phiên OP trung tâm, có thể ảnh hưởng nhiều RP.

## 5. Phân loại yêu cầu đủ và thiếu thông tin

### 5.1. Có id_token_hint và không có post_logout_redirect_uri

Đây là request có thể xác định RP/người dùng từ ID Token. OP xác minh token và ánh xạ phiên. Sau khi logout, OP hiển thị trang hoàn tất tại OP. Không cần redirect về RP.

### 5.2. Có id_token_hint và có post_logout_redirect_uri

OP phải:

1. Xác minh ID Token do chính OP phát hành.
2. Xác định client từ audience/session.
3. Nếu request đồng thời có `client_id`, xác nhận client ID khớp client đã dùng khi phát hành ID Token.
4. Xác minh `post_logout_redirect_uri` khớp chính xác URI đã đăng ký cho client.
5. Xác minh session/user context và quyết định có cần confirmation hay không.
6. Chỉ redirect sau khi logout đã hoàn tất và các logout notification cần thiết đã được xử lý.

### 5.3. Thiếu id_token_hint nhưng có client_id

`client_id` có thể giúp OP tìm `RegisteredClient` và kiểm tra URI đã đăng ký. Tuy nhiên, client ID không chứng minh rằng người gửi request là người dùng đang đăng nhập của client đó. Theo chuẩn, OP vẫn phải hỏi người dùng trước khi logout OP vì không có `id_token_hint`.

Nếu có `post_logout_redirect_uri`, OP chỉ được redirect khi có cách khác xác nhận tính hợp lệ của đích. Một chính sách an toàn có thể yêu cầu đồng thời:

- `client_id` tồn tại và được phép.
- URI exact-match với `RegisteredClient.postLogoutRedirectUris`.
- Trình duyệt đang có phiên OP hợp lệ gắn với ngữ cảnh RP hoặc có bằng chứng khác do OP quản lý.
- Người dùng đã xác nhận logout.

Không mặc định rằng chỉ một `client_id` trong query string là đủ để cho phép redirect.

### 5.4. Thiếu cả id_token_hint và client_id

Nếu người dùng đang đăng nhập tại OP, OP có thể hiển thị confirmation page để người dùng chủ động logout phiên hiện tại. Không có cơ sở để xác định RP khởi tạo, do đó không nên redirect về một URI do request tự cung cấp.

Nếu không có phiên OP, thao tác logout có thể được xử lý như một thao tác idempotent: hiển thị trạng thái đã đăng xuất hoặc yêu cầu đăng nhập lại nếu người dùng muốn quản lý phiên. Không được tìm người dùng theo một `logout_hint` tùy ý rồi kết thúc phiên của tài khoản đó.

### 5.5. Có post_logout_redirect_uri nhưng thiếu id_token_hint

OIDC RP-Initiated Logout 1.0 quy định OP MUST NOT thực hiện post-logout redirect nếu không có `id_token_hint`, trừ khi OP có phương thức khác để xác nhận tính hợp lệ của redirect target. Dù URI đã nằm trong danh sách đăng ký, OP vẫn phải đánh giá client và ngữ cảnh request theo policy của mình.

Nếu không xác minh được, lựa chọn an toàn là:

- Hoàn tất logout OP sau khi người dùng xác nhận, rồi hiển thị trang OP.
- Không chuyển tới URI được yêu cầu.
- Không trả lại `state` vì callback không diễn ra.

### 5.6. logout_hint không thay thế ID Token

`logout_hint` là một gợi ý có ngữ nghĩa do OP định nghĩa, có thể là username, email, số điện thoại hoặc session identifier. Nó không phải credential và không chứng minh người gửi được quyền logout tài khoản đó.

Không dùng `logout_hint` làm khóa duy nhất để:

- Tìm user rồi xóa session ngay lập tức.
- Chọn tài khoản khi trình duyệt đang đăng nhập một user khác mà không xác nhận.
- Bỏ qua xác minh `id_token_hint`, `client_id` hoặc session binding.

## 6. Xác minh ID Token hint và session binding

### 6.1. Kiểm tra issuer

Khi có `id_token_hint`, OP MUST xác minh chính OP là issuer của ID Token. Không chỉ decode payload rồi đọc `sub`. Tùy cách lưu trữ và kiến trúc, OP có thể đối chiếu token với authorization/ID Token đã phát hành hoặc xác minh JWS theo key nội bộ.

Các điểm cần kiểm tra:

- Issuer `iss` đúng OP hiện tại.
- Chữ ký hợp lệ nếu token được xác minh theo JWS.
- `aud` chứa client identifier tương ứng.
- Nếu request có `client_id`, giá trị đó khớp client đã dùng khi phát hành ID Token.
- `sid` nếu có phải được liên kết với phiên OP tương ứng.
- Principal/session được tìm thấy không mâu thuẫn với người dùng đang đăng nhập ở trình duyệt.

### 6.2. aud có thể chứa nhiều giá trị

Không giả định `aud` luôn là một chuỗi đơn. OIDC ID Token có thể có một audience hoặc nhiều audience. Khi kiểm tra `client_id`, cần xác minh client ID nằm trong tập audience được chấp nhận theo policy token, đồng thời xử lý `azp` khi cần theo OIDC Core.

Ví dụ minh họa:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-123",
  "aud": [
    "customer-portal",
    "shared-client"
  ],
  "azp": "customer-portal",
  "sid": "session-9c82",
  "iat": 1794800000,
  "exp": 1794803600
}
~~~

Đây là payload ví dụ. Khi có nhiều audience, OP phải áp dụng đúng quy tắc OIDC cho authorized party và client đã đăng ký; không chọn tùy tiện phần tử đầu tiên.

### 6.3. ID Token hết hạn không phải lúc nào cũng vô dụng cho logout

ID Token thường có thời hạn ngắn để xác thực tại RP. Nhưng RP có thể giữ ID Token đã nhận để gửi `id_token_hint` khi người dùng logout sau đó. RP-Initiated Logout 1.0 nói OP SHOULD chấp nhận ID Token nếu RP xác định bởi `aud` và/hoặc `sid` có phiên hiện tại hoặc phiên gần đây tại OP, ngay cả khi `exp` đã qua.

Điều này không có nghĩa bỏ qua mọi kiểm tra token:

- Vẫn xác minh token do OP phát hành.
- Vẫn kiểm tra chữ ký/nguồn phát và client binding theo policy.
- Vẫn cần session hiện tại/gần đây để liên hệ hint với ngữ cảnh logout.
- Không chấp nhận một token hết hạn rất lâu hoặc không còn session chỉ vì chữ ký đúng.

Không tái sử dụng một JWT validator chỉ kiểm tra `exp` như cách duy nhất để xác thực logout hint. Hãy tách policy xác minh token logout khỏi policy chấp nhận ID Token cho login thông thường, có xét current/recent session.

### 6.4. Kiểm tra sid và người dùng hiện tại

Nếu ID Token chứa `sid`, OP nên đối chiếu nó với session registry/session store. Nếu `sid` không tương ứng với phiên RP hiện tại hoặc phiên gần đây tại OP, request có thể đáng ngờ và OP có thể từ chối.

Ngoài ra, so sánh principal trong `id_token_hint` với principal đang có trong `SecurityContext`/OP session:

- Cùng user và cùng phiên: request có thể tiếp tục theo policy xác nhận.
- Cùng user nhưng khác phiên: cần xác nhận rõ phạm vi logout và không vô tình kết thúc mọi phiên nếu policy chỉ định một phiên.
- Khác user: không logout user hiện tại theo hint; yêu cầu xác nhận hoặc từ chối theo policy.
- Không có phiên hiện tại: không suy ra người dùng đang hoạt động chỉ từ token hint cũ.

## 7. Kiểm tra post_logout_redirect_uri và state

### 7.1. Exact match với URI đã đăng ký

RP-Initiated Logout 1.0 yêu cầu OP không redirect nếu URI được gửi không khớp chính xác một URI đã đăng ký trong `post_logout_redirect_uris` hoặc cơ chế đăng ký tương đương.

Ví dụ client đã đăng ký:

~~~text
https://portal.example.com/logout/callback
~~~

Các giá trị sau không được tự động coi là tương đương:

~~~text
https://portal.example.com/logout/callback/
https://portal.example.com/logout/callback?next=/home
http://portal.example.com/logout/callback
https://portal.example.com:8443/logout/callback
https://evil.example.net/logout/callback
~~~

Không dùng prefix matching, suffix matching, wildcard host hoặc tự normalize URI để cho phép các giá trị gần giống. Với native app custom scheme, chỉ chấp nhận scheme/URI đã đăng ký theo chính sách client type.

### 7.2. client_id khi không có ID Token

Nếu không có `id_token_hint`, `client_id` là cách phổ biến để OP xác định client khi có `post_logout_redirect_uri`. OP có thể tra RegisteredClient và kiểm tra URI. Nhưng chỉ tìm thấy client không đồng nghĩa đã xác minh người dùng hoặc request đến từ RP hợp lệ.

Nếu không thể xác nhận đích redirect theo cách khác, không redirect. Người dùng vẫn có thể xác nhận logout OP và nhận trang hoàn tất tại OP.

### 7.3. state chỉ là correlation value

`state` là chuỗi opaque do RP tạo để liên kết request và callback. OP phải trả lại nguyên giá trị khi redirect thành công về RP. OP không được:

- Dùng state để xác thực client.
- Dùng state để quyết định người dùng nào cần logout.
- Redirect về URL được nhúng bên trong state.
- Echo state khi redirect target chưa được xác minh.

RP phải tự kiểm tra state ở callback để chống request mix-up/CSRF trong quy trình của mình. OP không cần diễn giải nội dung state.

### 7.4. Không redirect trước khi logout hoàn tất

Post-logout redirect chỉ diễn ra sau khi OP đã hoàn tất các bước logout và thông báo cho các RP liên quan theo cơ chế đã đăng ký. Không gửi redirect ngay khi nhận request, trước khi người dùng xác nhận hoặc trước khi session invalidation hoàn tất.

## 8. Confirmation flow an toàn

### 8.1. Mô hình hai bước

~~~mermaid
flowchart TD
    A["RP hoặc User Agent gọi Logout Endpoint"] --> B["Parse GET/POST parameters"]
    B --> C["Validate issuer, client, session và redirect"]
    C --> D{"Thông tin đủ tin cậy và policy cho phép?"}
    D -->|Có| E["Hiển thị xác nhận nếu policy yêu cầu"]
    D -->|Thiếu hint hoặc phiên không khớp| E
    D -->|Dữ liệu redirect/client sai| F["Không dùng dữ liệu sai; không redirect"]
    E --> G{"Người dùng xác nhận?"}
    G -->|Không| H["Giữ phiên OP; hiển thị đã hủy"]
    G -->|Có| I["Kết thúc phiên OP và xử lý logout notifications"]
    I --> J{"Có redirect target đã xác minh?"}
    J -->|Có| K["Redirect đúng URI và trả state"]
    J -->|Không| L["Hiển thị trang hoàn tất tại OP"]
    F --> M["Trang lỗi hoặc lựa chọn logout local có xác nhận"]
~~~

### 8.2. GET không được tự thực hiện logout khi cần confirmation

GET request có thể được gửi bởi browser prefetch, link scanner, crawler hoặc một trang bên thứ ba. Nếu thiếu `id_token_hint` và OP cần hỏi người dùng, GET nên hiển thị trang xác nhận, không xóa session ngay.

Ngay cả khi RP dùng POST để gửi logout request, POST đó vẫn không chứng minh người dùng đã đồng ý với OP. Confirmation action của người dùng phải là một thao tác riêng, được bảo vệ bằng CSRF.

### 8.3. POST confirmation phải được bảo vệ

Trang xác nhận cần:

- CSRF token của Spring Security cho form POST.
- Ticket ngẫu nhiên, khó đoán, một lần và có TTL ngắn nếu request cần lưu trạng thái qua redirect.
- Ticket gắn với OP session ID và principal hiện tại.
- Kiểm tra người dùng vẫn đang ở đúng phiên khi bấm “Đăng xuất”.
- Consume ticket nguyên tử để chống replay.
- Nút “Ở lại” không thực hiện logout và không redirect tới RP.
- Không cho request client tự gửi `confirmed=true` trong logout request ban đầu.

Không dùng GET như `/logout/confirm?yes=true` để thực thi hành động. Trình duyệt có thể tự tải URL đó và gây logout ngoài ý muốn.

### 8.4. Lưu pending request ở server

Không cần đưa toàn bộ `id_token_hint`, `state` hoặc redirect URI vào URL của confirmation page. Một cách triển khai là:

1. Sau khi parse/validate bước đầu, tạo một random ticket.
2. Lưu pending logout ở server-side store với ticket hash, session ID, principal, request context đã kiểm tra, thời điểm hết hạn và redirect eligibility.
3. Redirect tới URL nội bộ như `/logout/confirm?ticket=<opaque-ticket>`.
4. Confirmation page POST ticket + CSRF token.
5. Server consume ticket một lần, xác minh session/principal còn khớp.
6. Nếu đồng ý, thực thi logout; nếu từ chối, xóa pending request và giữ phiên.

Không log raw ticket hoặc ID Token hint trong access log. Nếu buộc phải lưu request trong session, chỉ lưu trong thời gian ngắn và xóa sau khi xử lý.

## 9. Xử lý lỗi và request không hợp lệ

### 9.1. Validation thất bại thì không sử dụng dữ liệu đó

OIDC RP-Initiated Logout 1.0 quy định nếu một bước validation thất bại, các thao tác phụ thuộc vào dữ liệu sai phải bị hủy và dữ liệu sai không được sử dụng. Đặc biệt, nếu request có lỗi, OP MUST NOT post-logout redirect tới RP.

OP có quyền quyết định nội dung trang sau lỗi:

- Hiển thị thông báo lỗi.
- Hỏi người dùng có muốn logout khỏi OP không.
- Cho phép kết thúc phiên OP sau xác nhận nhưng không redirect.
- Từ chối hoàn toàn nếu request đáng ngờ hoặc có nguy cơ nhắm vào user khác.

### 9.2. Phân biệt lỗi cú pháp và thiếu thông tin

| Trường hợp | Phân loại | Hướng xử lý |
| --- | --- | --- |
| Không có `id_token_hint` | Thiếu thông tin được khuyến nghị, không nhất thiết sai cú pháp. | Bắt buộc hỏi người dùng trước khi logout OP. |
| Không có `post_logout_redirect_uri` | Request hợp lệ; RP không yêu cầu quay lại. | Hiển thị trang OP sau logout. |
| Không có `state` | Request hợp lệ; không có callback correlation value. | Không tạo hoặc tự bịa state. |
| Không có `client_id` nhưng có ID Token hint | Có thể xác định client từ token/session. | Xác minh issuer, audience/session và redirect nếu có. |
| `client_id` không khớp ID Token | Dữ liệu mâu thuẫn. | Từ chối thao tác phụ thuộc request; không redirect. |
| `post_logout_redirect_uri` không đăng ký | Redirect target không hợp lệ. | Không redirect; hiển thị lỗi hoặc xác nhận logout OP không redirect. |
| ID Token không do OP phát hành | Hint không hợp lệ. | Không dùng token để chọn user/session; từ chối hoặc yêu cầu logout thủ công theo policy. |
| ID Token có `sid` không còn liên hệ với phiên hiện tại/gần đây | Request đáng ngờ. | Có thể từ chối; nếu hỏi user, chỉ logout phiên user hiện tại sau xác nhận. |
| Logout request lặp lại sau khi phiên đã kết thúc | Idempotent case. | Không coi “không còn phiên” là lỗi bắt buộc; không tạo side effect ngoài policy. |
| Chỉ có `logout_hint` | Chưa đủ bằng chứng. | Không tự chọn user và logout; hỏi người dùng đang đăng nhập. |

### 9.3. Tránh tiết lộ thông tin qua error message

Không trả thông báo chi tiết như “user X tồn tại nhưng session Y không khớp” cho một request không đáng tin cậy. Dùng lỗi tổng quát cho client, ghi chi tiết vào audit log nội bộ với dữ liệu tối thiểu.

Không log raw ID Token hint, session cookie, session ID đầy đủ, CSRF token, ticket confirmation hoặc toàn bộ state nếu policy xem đó là dữ liệu nhạy cảm.

## 10. Spring Authorization Server xử lý logout như thế nào?

### 10.1. Bật OIDC và Logout Endpoint

Spring Authorization Server cấu hình OIDC qua `OAuth2AuthorizationServerConfigurer.oidc(...)`. Logout Endpoint có thể tùy chỉnh bằng `OidcLogoutEndpointConfigurer`:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .oidc(oidc -> oidc
                .logoutEndpoint(logout -> logout
                    .authenticationProviders(
                        configureLogoutValidation())
                )
            )
        );

    return http.build();
}
~~~

Đoạn code tập trung vào cấu hình logout; ứng dụng vẫn cần các bean khác của Authorization Server như RegisteredClientRepository, OAuth2AuthorizationService, key/JWK source, user authentication và session management.

### 10.2. Các thành phần mặc định

`OidcLogoutEndpointFilter` là filter xử lý RP-Initiated Logout. Cấu hình mặc định gồm:

| Thành phần | Lớp | Vai trò |
| --- | --- | --- |
| Request converter | `OidcLogoutAuthenticationConverter` | Đọc GET/POST request và tạo `OidcLogoutAuthenticationToken`. |
| Authentication provider | `OidcLogoutAuthenticationProvider` | Xử lý logout authentication, liên kết RegisteredClient, authorization và session. |
| Success handler | `OidcLogoutAuthenticationSuccessHandler` | Thực hiện logout khi provider xác thực thành công. |
| Failure handler | `OAuth2ErrorAuthenticationFailureHandler` nội bộ | Trả OAuth error khi xử lý thất bại. |
| Session registry | `SessionRegistry` | Tra cứu session của End-User để thực hiện logout. |

Spring Authorization Server cung cấp extension point cho converter, provider, success handler và error handler. Đây là nơi tích hợp policy bổ sung; không cần tự viết lại toàn bộ OIDC protocol endpoint.

### 10.3. Validator mặc định làm gì?

Từ Spring Authorization Server 1.4, `OidcLogoutAuthenticationProvider` có `setAuthenticationValidator(Consumer<OidcLogoutAuthenticationContext>)`. Trong Spring Authorization Server 1.5.8:

- `OidcLogoutAuthenticationValidator` là validator mặc định.
- Validator mặc định kiểm tra tham số `post_logout_redirect_uri`.
- Khi validation thất bại, validator ném `OAuth2AuthenticationException`.
- `OidcLogoutAuthenticationContext` chứa `OidcLogoutAuthenticationToken` và `RegisteredClient`.

Không nên giả định validator mặc định đã thực hiện toàn bộ confirmation policy theo OIDC. Ứng dụng cần xác nhận cách version đang dùng xử lý issuer, client binding, current/recent session và các trường hợp thiếu hint; bổ sung policy nếu cần.

### 10.4. SessionRegistry

`OidcLogoutAuthenticationProvider` sử dụng `SessionRegistry` để tra `SessionInformation` của End-User. Khi OIDC được bật, Spring Authorization Server dùng SessionRegistry để theo dõi các authenticated session.

Nếu đăng ký `SessionRegistryImpl`, cần đăng ký `HttpSessionEventPublisher` để SessionRegistry nhận sự kiện hủy HttpSession và dọn dữ liệu tương ứng:

~~~java
@Bean
SessionRegistry sessionRegistry() {
    return new SessionRegistryImpl();
}

@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}
~~~

Nếu ứng dụng dùng Spring Session hoặc session store phân tán, cần bảo đảm session registry chia sẻ trạng thái đúng giữa các node. Nếu Concurrent Session Control và OIDC Logout cùng dùng session tracking, nên dùng chung một SessionRegistry.

## 11. Custom validation cho logout request

### 11.1. Giữ validator mặc định rồi bổ sung policy

Một custom validator nên giữ các kiểm tra chuẩn của framework, sau đó bổ sung điều kiện riêng. Ví dụ dưới đây:

- Gọi validator mặc định để giữ kiểm tra `post_logout_redirect_uri`.
- Nếu `client_id` và ID Token cùng có, kiểm tra `client_id` nằm trong audience của ID Token.
- Nếu redirect URI có mặt, yêu cầu RegisteredClient và URI đã đăng ký.
- Không tự xác minh token bằng cách decode payload; việc xác minh ID Token/session phải dựa trên cơ chế token/authorization đáng tin cậy của OP.

~~~java
private Consumer<List<AuthenticationProvider>>
        configureLogoutValidation() {

    return providers -> providers.forEach(provider -> {
        if (provider instanceof OidcLogoutAuthenticationProvider logoutProvider) {
            logoutProvider.setAuthenticationValidator(context -> {
                // Giữ kiểm tra post_logout_redirect_uri mặc định.
                new OidcLogoutAuthenticationValidator().accept(context);

                OidcLogoutAuthenticationToken logout =
                    context.getAuthentication();
                RegisteredClient registeredClient =
                    context.getRegisteredClient();

                OidcIdToken idToken = logout.getIdToken();
                String clientId = logout.getClientId();

                if (idToken != null && clientId != null
                        && !idToken.getAudience().contains(clientId)) {
                    throw new OAuth2AuthenticationException(
                        new OAuth2Error("invalid_request"));
                }

                String redirectUri = logout.getPostLogoutRedirectUri();
                if (redirectUri != null
                        && (registeredClient == null
                        || !registeredClient.getPostLogoutRedirectUris()
                            .contains(redirectUri))) {
                    throw new OAuth2AuthenticationException(
                        new OAuth2Error("invalid_request"));
                }
            });
        }
    });
}
~~~

Đây là ví dụ bổ sung validation theo client/redirect, không phải một validator hoàn chỉnh cho mọi deployment. `RegisteredClient` được provider/context phân giải theo request; ứng dụng cần xác minh behavior khi `id_token_hint` có nhưng `client_id` vắng mặt. Nếu ID Token có nhiều audience, dùng phép kiểm tra membership thay vì chỉ lấy phần tử đầu.

### 11.2. Không biến thiếu hint thành validation error

`id_token_hint` là RECOMMENDED, không phải REQUIRED. Custom validator không nên từ chối mọi request chỉ vì thiếu hint. Thay vào đó, request cần đi vào confirmation policy.

~~~java
boolean requiresConfirmation(OidcLogoutAuthenticationToken logout) {
    if (logout.getIdToken() == null) {
        return true;
    }
    return !sessionBindingPolicy.belongsToCurrentOrRecentSession(logout);
}
~~~

`sessionBindingPolicy` là thành phần do ứng dụng xây dựng, phải kiểm tra session/principal/RegisteredClient theo dữ liệu tin cậy. Không suy ra “đúng phiên” chỉ từ việc ID Token có chữ ký hợp lệ.

### 11.3. Validator không phải confirmation UI

Validator chỉ quyết định request có vượt qua các điều kiện xác thực/validation hay không. Khi cần hiển thị trang xác nhận, dùng `logoutResponseHandler` hoặc một luồng UI riêng được tích hợp an toàn với endpoint. Không ném lỗi giả để ép framework hiển thị trang confirmation; error handler là đường xử lý lỗi, không phải đường đồng ý logout.

## 12. Tích hợp confirmation qua success handler

### 12.1. Vì sao dùng success handler?

Sau khi `OidcLogoutAuthenticationProvider` xử lý request, `logoutResponseHandler` nhận `OidcLogoutAuthenticationToken` đã được provider chấp nhận. Handler mặc định `OidcLogoutAuthenticationSuccessHandler` thực hiện logout.

Ứng dụng có thể thay success handler để:

1. Kiểm tra policy có yêu cầu người dùng xác nhận không.
2. Nếu cần, tạo pending logout và hiển thị confirmation page.
3. Nếu không cần confirmation, ủy quyền cho success handler mặc định.
4. Sau khi người dùng xác nhận bằng một POST riêng, lấy pending logout một lần và thực hiện logout.

### 12.2. Handler minh họa

~~~java
final class ConfirmationAwareLogoutSuccessHandler
        implements AuthenticationSuccessHandler {

    private final OidcLogoutAuthenticationSuccessHandler delegate;
    private final LogoutConfirmationPolicy confirmationPolicy;
    private final PendingLogoutStore pendingLogoutStore;

    ConfirmationAwareLogoutSuccessHandler(
            LogoutConfirmationPolicy confirmationPolicy,
            PendingLogoutStore pendingLogoutStore) {
        this.delegate = new OidcLogoutAuthenticationSuccessHandler();
        this.confirmationPolicy = confirmationPolicy;
        this.pendingLogoutStore = pendingLogoutStore;
    }

    @Override
    public void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication)
            throws IOException, ServletException {

        OidcLogoutAuthenticationToken logout =
            (OidcLogoutAuthenticationToken) authentication;

        if (confirmationPolicy.requiresConfirmation(logout)) {
            HttpSession session = request.getSession(false);
            if (session == null) {
                response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
                return;
            }

            String ticket = pendingLogoutStore.create(
                logout,
                session.getId(),
                authentication.getName(),
                Duration.ofMinutes(2));

            response.sendRedirect(
                "/logout/confirm?ticket=" +
                URLEncoder.encode(ticket, StandardCharsets.UTF_8));
            return;
        }

        delegate.onAuthenticationSuccess(
            request, response, authentication);
    }
}
~~~

`LogoutConfirmationPolicy` và `PendingLogoutStore` là abstraction do ứng dụng triển khai. Store cần giữ pending authentication/request context ở server-side, TTL ngắn, ticket ngẫu nhiên, one-time consume và ràng buộc session/principal. Không đưa raw `id_token_hint` hoặc toàn bộ logout request vào URL.

Khi cấu hình:

~~~java
.oidc(oidc -> oidc
    .logoutEndpoint(logout -> logout
        .logoutResponseHandler(
            confirmationAwareLogoutSuccessHandler)
    )
)
~~~

Đoạn code minh họa extension point. Nếu thay success handler, phải bảo đảm handler mặc định vẫn được gọi ở nhánh không cần xác nhận và sau khi người dùng đã xác nhận. Nếu dùng custom LogoutHandler, cần giữ các hành vi cần thiết như invalidation session, clear security context, xóa cookie và notification đã cấu hình.

### 12.3. Confirmation POST

Controller xử lý confirmation nên có semantics tương tự:

~~~java
@PostMapping("/logout/confirm")
void confirmLogout(
        @RequestParam String ticket,
        @RequestParam boolean confirm,
        HttpServletRequest request,
        HttpServletResponse response,
        Authentication currentAuthentication) throws IOException, ServletException {

    HttpSession session = request.getSession(false);
    if (session == null) {
        response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
        return;
    }

    PendingLogout pending = pendingLogoutStore.consume(
        ticket,
        session.getId(),
        currentAuthentication.getName());

    if (!confirm) {
        response.sendRedirect("/logout/cancelled");
        return;
    }

    logoutCompletionService.complete(
        request, response, pending);
}
~~~

Đây là skeleton kiến trúc; `consume(...)` phải kiểm tra ticket tồn tại, chưa dùng, chưa hết hạn, session ID và principal khớp, sau đó xóa ticket nguyên tử. `LogoutCompletionService` là thành phần do ứng dụng triển khai: nó dùng success/logout handler đã cấu hình khi redirect đã được xác minh, hoặc thực hiện logout và hiển thị trang OP khi không có redirect hợp lệ. Không gọi endpoint logout lại bằng query parameter `confirm=true`.

Form POST cần CSRF protection. Không vô hiệu hóa CSRF cho route confirmation. Nếu Authorization Server security chain có matcher/CSRF policy riêng, route UI confirmation cần được cấu hình rõ trong chain phù hợp.

### 12.4. Khi không có redirect hợp lệ

Nếu request thiếu `id_token_hint` và OP không có cách khác xác minh redirect target, confirmation page vẫn có thể cho phép logout OP. Sau khi xác nhận:

- Kết thúc phiên OP.
- Thông báo các RP qua front-channel/back-channel logout nếu đã đăng ký và cấu hình.
- Hiển thị trang hoàn tất tại OP.
- Không redirect về URI trong request.
- Không trả lại `state`.

Không dùng default redirect handler để redirect về một URI chỉ vì người dùng bấm “Đăng xuất”. Việc đồng ý logout không biến một redirect target không hợp lệ thành hợp lệ.

## 13. Error response và trang UI

### 13.1. Lỗi protocol

`OidcLogoutEndpointConfigurer.errorResponseHandler(...)` cho phép thay failure handler mặc định. Handler mặc định dùng OAuth error gắn với `OAuth2AuthenticationException`.

Một ứng dụng có thể tùy chỉnh để:

- Ghi audit event với reason code nội bộ.
- Trả trang lỗi thân thiện cho browser.
- Không tiết lộ token, session ID hoặc chi tiết tài khoản.
- Không redirect tới RP khi validation thất bại.

### 13.2. Không biến mọi lỗi thành confirmation

Có các lỗi cần từ chối ngay:

- `client_id` mâu thuẫn với `id_token_hint`.
- ID Token không do OP phát hành.
- Redirect URI không được đăng ký.
- Dữ liệu request sai định dạng hoặc vượt giới hạn.
- Session/token hint chỉ tới người dùng khác và policy không cho phép.

Confirmation page phù hợp khi request thiếu bằng chứng nhưng vẫn có thể hỏi người dùng đang đăng nhập. Confirmation không sửa được dữ liệu client/redirect sai và không hợp thức hóa một open redirect.

### 13.3. Idempotency

RP-Initiated Logout được thiết kế theo hướng idempotent. Request yêu cầu logout một RP mà OP không còn phiên đăng nhập tương ứng không nhất thiết là lỗi. Điều này giúp RP retry khi không biết logout notification có được xử lý hay chưa.

Tuy vậy, idempotency không có nghĩa bỏ qua xác thực redirect hoặc session binding. Lần gọi lặp không được tạo ra side effect ngoài ý muốn hoặc redirect tới URI chưa xác minh.

## 14. Session tracking và thông báo tới RP

### 14.1. SessionRegistry phải nhất quán

Spring Authorization Server dùng `SessionRegistry` để tìm phiên End-User khi logout. Trong cluster:

- Dùng registry/store phù hợp với session architecture.
- Đảm bảo node xử lý logout có thể tra session được đăng ký bởi node login.
- Cấu hình `HttpSessionEventPublisher` khi dùng `SessionRegistryImpl`.
- Kiểm tra session expiration và destruction event.
- Tránh xóa session registry record trước khi logout notification cần thiết hoàn tất.

### 14.2. Front-channel và back-channel logout

OP có thể thông báo logout tới các RP đã đăng nhập End-User bằng cơ chế front-channel hoặc back-channel mà hai bên hỗ trợ. RP khởi tạo logout cũng phải được tính đến trước khi OP redirect về RP.

Các notification này giúp các RP kết thúc local session. Chúng không thay thế confirmation của người dùng khi chuẩn yêu cầu xác nhận và không tự làm cho redirect URI trở nên hợp lệ.

### 14.3. RP không nhận notification

Một số logout notification có thể không được nhận vì browser đóng, network lỗi hoặc RP không hoạt động. Vì vậy:

- RP nên có local logout behavior rõ ràng.
- OP cần audit notification result/retry nếu implementation hỗ trợ.
- Access token/refresh token cần policy vòng đời riêng.
- Người dùng cần được thông báo nếu chỉ logout một phần.

## 15. Bảo mật confirmation flow

### 15.1. CSRF và logout CSRF

Logout CSRF có thể khiến một trình duyệt bị logout ngoài ý muốn khi truy cập trang độc hại. Confirmation page giảm rủi ro nhưng chỉ khi action xác nhận được bảo vệ:

- Dùng CSRF token cho form POST.
- Không thực thi logout qua GET.
- Không coi POST do RP gửi tới Logout Endpoint là user confirmation.
- Không cho trang ngoài nhúng confirmation page nếu chính sách không cho phép; cân nhắc CSP `frame-ancestors`.
- Kiểm tra `Origin`/`Referer` khi phù hợp với kiến trúc và browser support, nhưng không thay CSRF token bằng header này.

### 15.2. Open redirect

Đây là rủi ro nghiêm trọng của logout flow. Không redirect theo URL tùy ý, không wildcard host và không lấy URL từ `state` hoặc `logout_hint`. Chỉ dùng URI exact-match đã đăng ký hoặc một cơ chế xác nhận độc lập đã được đánh giá.

### 15.3. Ticket replay và session swapping

Ticket confirmation phải:

- Có entropy cao, khó đoán.
- Hết hạn nhanh.
- Dùng một lần và consume nguyên tử.
- Gắn với session ID và principal.
- Không dùng được từ browser/session khác.
- Bị xóa khi người dùng hủy hoặc khi hết hạn.

Nếu người dùng đổi tài khoản trong thời gian confirmation page đang mở, ticket phải bị từ chối vì principal/session đã thay đổi.

### 15.4. Bảo vệ ID Token hint trong URL và log

`id_token_hint` có thể xuất hiện trong query string của GET logout request. Hạn chế rò rỉ:

- Không log query string đầy đủ tại ingress/application.
- Dùng `Referrer-Policy: no-referrer` trên trang liên quan.
- Không tải third-party analytics/image/script ở confirmation page.
- Không ghi token hint vào flash attribute hoặc browser storage.
- Xóa pending state sau khi xử lý.

RP có thể dùng POST để gửi logout request khi muốn tránh token xuất hiện trong URL, nhưng OP vẫn phải hỗ trợ GET theo chuẩn.

## 16. Kiểm thử RP-Initiated Logout

### 16.1. Unit test validation

Kiểm thử riêng:

- `client_id` trùng audience của ID Token.
- `client_id` không trùng audience.
- `post_logout_redirect_uri` exact-match.
- Redirect URI khác path, port, scheme hoặc trailing slash.
- Không có ID Token hint.
- ID Token có `sid` đúng, sai hoặc không còn session.
- ID Token hết `exp` nhưng session còn current/recent.
- `logout_hint` không được dùng làm bằng chứng danh tính.

### 16.2. Integration test confirmation

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Hint hợp lệ, phiên hiện tại khớp | Logout theo policy xác nhận; không logout user khác. |
| Không có `id_token_hint` | Hiển thị confirmation; chưa kết thúc session trước khi user đồng ý. |
| Hint thuộc user khác | Không logout theo hint; yêu cầu xác nhận cho phiên hiện tại hoặc từ chối. |
| Hint không do OP phát hành | Không dùng token; không redirect. |
| `client_id` và hint mismatch | Từ chối; không logout và không redirect. |
| Redirect exact-match | Chỉ redirect sau khi logout hoàn tất. |
| Redirect mismatch | Không redirect; hiển thị lỗi hoặc hoàn tất logout OP không redirect sau xác nhận. |
| Không có `state` | Logout vẫn hoạt động; không tự tạo state. |
| Có state và redirect hợp lệ | Trả nguyên state trong callback. |
| Chỉ có `logout_hint` | Không tự chọn user; confirmation theo phiên hiện tại. |
| GET logout request | Có thể hiển thị confirmation; không tự logout khi cần xác nhận. |
| POST từ RP | Không coi POST là user consent. |
| Confirmation POST thiếu CSRF | Bị từ chối. |
| Confirmation ticket hết hạn | Không logout. |
| Ticket đã dùng | Request replay bị từ chối. |
| Ticket từ session khác | Bị từ chối. |
| User chọn “Ở lại” | Session OP còn nguyên, pending request bị xóa. |
| User chọn “Đăng xuất” | Session OP bị kết thúc; redirect chỉ khi đã xác minh. |
| Session đã kết thúc trước request | Xử lý idempotent, không lỗi không cần thiết. |
| Notification tới RP lỗi | Ghi nhận và xử lý theo retry/policy; không redirect trước khi bước bắt buộc hoàn tất. |

### 16.3. Test bằng browser thật

MockMvc kiểm tra filter, validator và controller; nhưng browser integration test cần xác minh:

1. RP redirect tới `end_session_endpoint`.
2. OP đọc đúng GET/POST parameters.
3. Confirmation page không thực thi logout khi mới tải.
4. Browser có CSRF token trong form.
5. Nút hủy giữ nguyên phiên OP.
6. Nút xác nhận kết thúc phiên OP và xóa cookie.
7. Redirect chỉ tới URI đã đăng ký và state được trả đúng.
8. Mở ticket confirmation trong browser/session khác không có tác dụng.
9. Tab thứ hai hoặc request lặp không làm logout nhầm một phiên mới.

## 17. Lỗi thường gặp và cách xử lý

### Lỗi 1: Từ chối mọi request thiếu id_token_hint

**Triệu chứng:** RP cũ hoặc logout khởi tạo trực tiếp luôn nhận lỗi.

**Nguyên nhân:** Coi `id_token_hint` là REQUIRED dù OIDC chỉ RECOMMENDED.

**Cách xử lý:** Cho phép request thiếu hint đi vào confirmation flow; chỉ logout OP sau khi người dùng xác nhận.

### Lỗi 2: Logout ngay khi nhận GET

**Triệu chứng:** Người dùng bị logout khi browser prefetch hoặc mở link từ một trang khác.

**Nguyên nhân:** Xem request đến Logout Endpoint là sự đồng ý của người dùng.

**Cách xử lý:** Với request thiếu hint hoặc không khớp phiên, hiển thị confirmation; thực thi qua POST có CSRF.

### Lỗi 3: Dùng logout_hint như danh tính đã xác thực

**Triệu chứng:** Request chỉ cung cấp email/username có thể kết thúc session của tài khoản đó.

**Nguyên nhân:** Nhầm hint với credential.

**Cách xử lý:** Dùng hint chỉ để hiển thị/gợi ý; liên kết với phiên người dùng hiện tại và yêu cầu xác nhận.

### Lỗi 4: Redirect bằng prefix matching

**Triệu chứng:** URI như `https://portal.example.com.evil.test/` được chấp nhận.

**Nguyên nhân:** So sánh startsWith hoặc wildcard domain.

**Cách xử lý:** Exact-match với `post_logout_redirect_uris`.

### Lỗi 5: Trả state dù không redirect

**Triệu chứng:** RP nhận callback không hợp lệ hoặc nhầm trạng thái logout.

**Nguyên nhân:** Echo state ngay cả khi redirect target bị từ chối.

**Cách xử lý:** Chỉ trả state trong redirect hợp lệ đã hoàn tất.

### Lỗi 6: Từ chối ID Token hint chỉ vì exp đã qua

**Triệu chứng:** RP không thể logout phiên gần đây vì ID Token hết hạn.

**Nguyên nhân:** Áp dụng JWT expiration validation của login flow mà không xét logout profile.

**Cách xử lý:** Xác minh issuer/chữ ký/client/session và áp dụng current/recent session rule của RP-Initiated Logout.

### Lỗi 7: Dùng validator mặc định như thể nó thực hiện toàn bộ policy

**Triệu chứng:** Redirect được kiểm tra nhưng client/session mismatch không được xử lý theo policy của ứng dụng.

**Nguyên nhân:** Không phân biệt `OidcLogoutAuthenticationValidator` với toàn bộ logout provider.

**Cách xử lý:** Kiểm tra behavior version đang dùng; bổ sung `setAuthenticationValidator(...)` và confirmation policy.

### Lỗi 8: Confirmation ticket không gắn với session

**Triệu chứng:** Người dùng khác có thể xác nhận ticket lấy được từ URL hoặc log.

**Nguyên nhân:** Ticket chỉ là random URL parameter, không ràng buộc browser session.

**Cách xử lý:** Bind ticket với session ID/principal, TTL ngắn và one-time consume.

### Lỗi 9: Nhầm logout OP với revoke token

**Triệu chứng:** User logout nhưng access token vẫn hoạt động theo TTL hoặc refresh token vẫn còn hiệu lực.

**Nguyên nhân:** Chỉ xóa HttpSession mà không xử lý authorization/token policy.

**Cách xử lý:** Thiết kế token revocation và session logout thành các hành vi có quan hệ rõ ràng, kiểm thử riêng.

## 18. Checklist production

| Hạng mục | Điều kiện cần xác nhận |
| --- | --- |
| Discovery | `end_session_endpoint` công bố đúng URL HTTPS. |
| Protocol | Hỗ trợ GET và POST theo RP-Initiated Logout 1.0. |
| ID Token hint | Xác minh issuer, audience/client, sid và current/recent session. |
| Missing hint | Confirmation bắt buộc trước khi logout OP. |
| Session mismatch | Confirmation hoặc từ chối; không logout nhầm principal. |
| Expired hint | Có policy chấp nhận khi session current/recent theo chuẩn. |
| Client binding | `client_id` và hint khớp khi cả hai cùng có. |
| Redirect | Exact-match với URI đã đăng ký; không open redirect. |
| Redirect không hint | Có bằng chứng độc lập về legitimacy trước khi redirect. |
| State | Chỉ echo khi redirect hợp lệ; RP tự xác minh callback. |
| Confirmation | GET không side effect; POST có CSRF. |
| Ticket | Random, TTL ngắn, one-time, bind session/principal. |
| Spring provider | Custom validator giữ default redirect validation. |
| Success handler | Chỉ thực hiện logout sau xác nhận cần thiết. |
| SessionRegistry | Dùng chung và dọn session lifecycle đúng cách. |
| RP notification | Front/back-channel logout được kiểm thử theo client đã đăng ký. |
| Token lifecycle | Logout session và revoke token được phân biệt rõ. |
| Audit | Ghi kết quả/decision/reason mà không log token hoặc cookie. |
| Browser | Có kiểm thử prefetch, cross-site, nhiều tab và replay. |

## 19. Bài tập thực hành

Một OP dùng Spring Authorization Server tại `https://auth.example.com`, phục vụ `customer-portal` và `billing-console`. Cả hai RP dùng Authorization Code Flow. Portal gửi `id_token_hint`, `post_logout_redirect_uri` và `state`; billing-console phiên bản cũ chỉ gửi `client_id` và `post_logout_redirect_uri`. Ngoài ra, người dùng có thể mở trực tiếp `/connect/logout` từ bookmark.

1. Thiết kế ma trận quyết định cho ba request: portal đầy đủ, billing thiếu ID Token hint và request trực tiếp không có tham số.
2. Xác định khi nào OP MUST yêu cầu confirmation và khi nào có thể bỏ qua theo policy.
3. Viết custom validator giữ `OidcLogoutAuthenticationValidator` mặc định, kiểm tra `client_id` với audience và redirect URI exact-match.
4. Thiết kế `LogoutConfirmationPolicy` kiểm tra current/recent session.
5. Xây `PendingLogoutStore` có ticket một lần, TTL hai phút, ràng buộc session ID/principal và CSRF-protected confirmation POST.
6. Thay `logoutResponseHandler` bằng confirmation-aware handler, chỉ gọi handler mặc định sau khi user xác nhận.
7. Chứng minh request có `post_logout_redirect_uri` nhưng không có hint không thể redirect nếu OP chưa xác nhận legitimacy theo policy.
8. Kiểm thử ID Token đã hết `exp` nhưng `sid` vẫn trỏ tới phiên gần đây.
9. Kiểm thử `client_id` không khớp `aud`, redirect URI khác một ký tự, state không có và ticket replay.
10. Phân biệt kết quả logout OP session, RP local session và access/refresh token revocation.

**Tiêu chí đạt:** OP không logout người dùng chỉ dựa trên một request thiếu thông tin; mọi redirect được xác minh; khi thiếu `id_token_hint` hoặc session không khớp, người dùng phải xác nhận trước khi OP kết thúc phiên; thao tác xác nhận không thể bị replay hoặc CSRF.

## 20. Tài liệu đối chiếu

- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html): tham số logout, xác nhận người dùng, current/recent session, post-logout redirect và validation/error handling.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, iss, aud, azp, sid và xác minh token.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): end_session_endpoint metadata.
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html): thông báo logout qua User Agent.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): logout notification trực tiếp tới RP.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): OIDC Logout Endpoint, converter/provider/handler và custom validation.
- [Spring Authorization Server — OidcLogoutEndpointConfigurer Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OidcLogoutEndpointConfigurer.html): extension points của Logout Endpoint.
- [Spring Authorization Server — OidcLogoutAuthenticationProvider Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcLogoutAuthenticationProvider.html): session registry và custom validator.
- [Spring Authorization Server — OidcLogoutAuthenticationContext Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcLogoutAuthenticationContext.html): request context và RegisteredClient.
- [Spring Authorization Server — OidcLogoutAuthenticationSuccessHandler Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/web/authentication/OidcLogoutAuthenticationSuccessHandler.html): thực hiện logout và custom LogoutHandler.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): SessionRegistry và HttpSessionEventPublisher.
