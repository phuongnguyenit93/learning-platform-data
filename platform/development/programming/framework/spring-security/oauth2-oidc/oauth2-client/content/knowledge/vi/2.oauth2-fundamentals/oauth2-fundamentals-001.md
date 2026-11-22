# 2.1. Resource Owner, Client, Authorization Server và Resource Server

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Nhận diện đúng bốn vai trò cốt lõi của OAuth 2.0 trong một hệ thống có đăng nhập và gọi API.
- Giải thích ai sở hữu tài nguyên, ai xin quyền, ai cấp token và ai kiểm tra token trước khi trả dữ liệu.
- Theo dõi một luồng Authorization Code với PKCE từ trình duyệt đến Authorization Server và Resource Server.
- Phân biệt OAuth 2.0 (ủy quyền truy cập) với OpenID Connect (OIDC, lớp định danh và xác thực).
- Xác định một ứng dụng Spring Security đang đóng vai trò OAuth2 Client, Resource Server hay Authorization Server, kể cả khi cùng một hệ thống có nhiều vai trò.

## 1. Bức tranh tổng thể: bốn vai trò là bốn trách nhiệm

Giả sử một trường học có:

- **Lan** muốn xem danh sách khóa học của mình.
- **Study Portal** là ứng dụng web Lan dùng, tích hợp đăng nhập của trường.
- **Campus Identity** là hệ thống đăng nhập tập trung, phát hành token.
- **Course API** lưu dữ liệu khóa học và cung cấp endpoint yêu cầu quyền truy cập.

Ở tương tác này, Lan là *Resource Owner*, Study Portal là *Client*, Campus Identity là *Authorization Server*, còn Course API là *Resource Server*. Những tên này mô tả **vai trò trong một giao dịch OAuth**, không nhất thiết tương ứng một máy chủ hay một sản phẩm riêng.

| Vai trò | Câu hỏi vai trò trả lời | Trong ví dụ | Trách nhiệm chính |
| --- | --- | --- | --- |
| **Resource Owner** | Ai có quyền cho phép truy cập tài nguyên? | Lan | Quyết định hoặc là chủ thể có thẩm quyền đối với quyền truy cập được ủy quyền |
| **Client** | Ứng dụng nào muốn truy cập tài nguyên? | Study Portal | Khởi tạo yêu cầu ủy quyền, nhận token theo luồng hợp lệ và dùng access token gọi API |
| **Authorization Server** | Ai xác thực và cấp quyền/token? | Campus Identity | Xác thực chủ thể khi cần, xử lý yêu cầu ủy quyền, cấp token cho client |
| **Resource Server** | Ai giữ tài nguyên được bảo vệ? | Course API | Nhận access token, kiểm tra tính hợp lệ và quyền hạn rồi quyết định có trả dữ liệu hay không |

Sơ đồ tổng quát:

~~~mermaid
flowchart LR
    RO["Resource Owner<br/>Lan"]
    C["Client<br/>Study Portal"]
    AS["Authorization Server<br/>Campus Identity"]
    RS["Resource Server<br/>Course API"]

    RO -->|"Sử dụng ứng dụng"| C
    C -->|"Chuyển hướng yêu cầu ủy quyền"| AS
    RO -->|"Xác thực / chấp thuận khi cần"| AS
    AS -->|"Authorization code, sau đó token"| C
    C -->|"Gọi API kèm access token"| RS
    RS -->|"Dữ liệu được cho phép"| C
    C -->|"Hiển thị kết quả"| RO
~~~

**Điểm mấu chốt:** Client không cần biết mật khẩu của Resource Owner để gọi API được ủy quyền. Authorization Server cấp bằng chứng ủy quyền dưới dạng access token; Resource Server kiểm tra bằng chứng đó trong phạm vi tài nguyên mà nó bảo vệ.

## 2. Resource Owner: chủ thể có thẩm quyền đối với tài nguyên

Theo mô hình OAuth 2.0, *Resource Owner* là thực thể có khả năng cấp quyền truy cập đến tài nguyên được bảo vệ. Khi là con người, ta thường gọi chủ thể này là *end user* (người dùng cuối).

Trong ví dụ, danh sách khóa học của Lan là tài nguyên được bảo vệ. Lan có thể cho phép Study Portal truy cập dữ liệu phù hợp chính sách của nhà trường. Tuy nhiên, hãy tránh suy luận rằng:

- Resource Owner luôn là người đang trực tiếp bấm nút đăng nhập. Có hệ thống nơi thẩm quyền được đại diện hoặc do tổ chức quản lý.
- Người dùng đồng ý là đủ để client xem bất kỳ dữ liệu nào. Resource Server vẫn phải kiểm tra quy tắc kinh doanh, quyền thực tế và giới hạn dữ liệu.
- Mọi luồng OAuth đều có Resource Owner là con người tham gia ở thời điểm cấp token. Với luồng **Client Credentials**, client xin quyền dựa trên chính danh tính của nó, không đại diện một người dùng tương tác.

**Resource Owner khác với chủ thể của mọi token.** Trong một luồng có người dùng, access token thường biểu thị ngữ cảnh truy cập thay mặt người dùng; trong luồng máy với máy, không nhất thiết có người dùng. Cần đọc grant type, claims và chính sách của Authorization Server thay vì tự suy đoán.

Trong OIDC, thuật ngữ **End-User** nói đến người được OpenID Provider xác thực. Với kịch bản đăng nhập thường gặp, Lan vừa là End-User theo OIDC vừa là Resource Owner trong ví dụ OAuth, nhưng đây là hai khái niệm thuộc hai lớp giao thức khác nhau.

## 3. Client: ứng dụng xin và sử dụng quyền truy cập

*Client* là ứng dụng thực hiện yêu cầu truy cập tài nguyên được bảo vệ thay mặt Resource Owner hoặc theo thẩm quyền của chính nó. Client có thể là ứng dụng web server-side, single-page application (SPA), ứng dụng di động, CLI hoặc một dịch vụ backend.

### 3.1. Một Client phải có những gì?

Authorization Server thường quản lý **client registration** với các thuộc tính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| Client ID | Mã định danh công khai của ứng dụng đã đăng ký |
| Client authentication | Cách client chứng minh danh tính với Authorization Server, khi loại client có thể làm việc đó |
| Redirect URI | Địa chỉ nhận phản hồi sau bước ủy quyền; phải được đăng ký và so khớp chặt chẽ |
| Grant type | Luồng được phép sử dụng, ví dụ Authorization Code hoặc Client Credentials |
| Scope | Nhóm quyền mà client được phép yêu cầu |
| Provider / issuer | Authorization Server mà client tin cậy, gồm các endpoint liên quan |

**Client ID không phải mật khẩu.** Đối với confidential client, client secret hoặc một phương thức xác thực mạnh khác được giữ an toàn ở backend. Không đưa client secret vào JavaScript chạy trên trình duyệt, mã nguồn công khai hay ứng dụng di động phân phối đến người dùng.

### 3.2. Confidential Client và Public Client

- **Confidential Client** có thể giữ bí mật thông tin xác thực, điển hình là backend web. Nó thường thực hiện trao đổi authorization code tại server.
- **Public Client** không thể bảo đảm bí mật của client secret, chẳng hạn SPA thuần trình duyệt hoặc ứng dụng di động. Những client này phải dùng phương án tương thích, đặc biệt **Authorization Code với PKCE**.

PKCE cũng được khuyến nghị cho confidential client khi dùng Authorization Code. PKCE liên kết authorization request với lần đổi code bằng một *code verifier* bí mật tạm thời và *code challenge* dẫn xuất từ nó.

**Trình duyệt và Client không luôn là một.** Khi Study Portal là ứng dụng server-side, trình duyệt chuyển hướng qua Authorization Server, nhưng thành phần backend Study Portal mới là OAuth2 Client đã đăng ký và giữ token. Nếu SPA tự thực hiện giao thức, SPA chính là public client. Sự khác biệt này quyết định nơi lưu token và cách bảo vệ chúng.

### 3.3. Client không tự cấp quyền cho mình

Client chỉ **yêu cầu** những scope cần thiết, ví dụ `courses.read`. Authorization Server quyết định scope nào thực sự được cấp. Resource Server mới là nơi áp dụng kiểm tra cuối cùng cho API cụ thể. Việc client tự khai báo scope hoặc hiện nút “Xem khóa học” không tạo ra quyền truy cập.

## 4. Authorization Server: xác thực, xử lý ủy quyền và cấp token

*Authorization Server* là hệ thống phát hành token sau khi xử lý yêu cầu ủy quyền theo chính sách. Đối với luồng có người dùng, nó thường xác thực người dùng và có thể yêu cầu sự đồng ý (*consent*). Đối với luồng dịch vụ, nó có thể xác thực client mà không mở màn hình đăng nhập.

Những chức năng thường gặp:

1. Quản lý client đã đăng ký, redirect URI, grant type và scope được phép.
2. Tiếp nhận yêu cầu tại **authorization endpoint**, xử lý xác thực người dùng, consent và chính sách.
3. Phát hành **authorization code** trong Authorization Code flow.
4. Tại **token endpoint**, kiểm tra code, PKCE và client authentication khi áp dụng rồi phát hành token.
5. Công bố metadata, khóa công khai (JWKS) hoặc introspection endpoint để các thành phần khác có thể xác thực token theo mô hình được cấu hình.
6. Quản lý vòng đời token, hết hạn, thu hồi và refresh token theo chính sách.

Authorization Server **không mặc nhiên là nơi lưu dữ liệu nghiệp vụ**. Campus Identity có thể cấp access token cho `courses.read`, còn Course API mới thực sự lưu và trả danh sách khóa học.

Một Authorization Server có thể cấp token cho nhiều Resource Server. Việc phát hành token không có nghĩa một token hợp lệ với mọi API; token có thể bị ràng buộc bởi **audience** (đối tượng nhận), scope và các điều kiện khác.

### Authorization endpoint và token endpoint có vai trò khác nhau

- **Authorization endpoint:** thường được truy cập thông qua trình duyệt (front channel), nhận yêu cầu ủy quyền rồi trả một kết quả chuyển hướng. Trong Authorization Code flow, kết quả thành công là *authorization code*.
- **Token endpoint:** client trao đổi code qua kết nối trực tiếp với Authorization Server (back channel) để nhận token. Token không cần đi qua URL chuyển hướng trên trình duyệt của người dùng.

Authorization code có thời hạn ngắn, dùng một lần và gắn với client/redirect URI theo quy tắc của máy chủ. Nó **không phải** access token và không được gửi trực tiếp để gọi Course API.

## 5. Resource Server: bảo vệ API và thực thi quyền truy cập

*Resource Server* là hệ thống lưu trữ hoặc cung cấp tài nguyên được bảo vệ. Course API có thể nhận yêu cầu:

~~~http
GET /api/me/courses HTTP/1.1
Host: courses.example.org
Authorization: Bearer <access-token>
~~~

Resource Server phải thực hiện cả **xác thực token** lẫn **kiểm tra quyền**:

- Token có đúng định dạng và có nguồn phát hành đáng tin cậy không?
- Với JWT, chữ ký và các thời hạn như `exp`, `nbf` có hợp lệ không? Với opaque token, có cần introspection từ Authorization Server không?
- Token có được cấp **cho API này** (audience / resource phù hợp) và có các scope cần thiết không?
- Chủ thể có được phép xem chính tài nguyên đang yêu cầu không, ví dụ chỉ các khóa học của mình?
- Có giới hạn thêm nào theo tenant, tổ chức, trạng thái tài khoản hoặc quy định nghiệp vụ không?

Các bước cuối không thể thay thế bằng việc “JWT có chữ ký đúng”. Một access token hợp lệ có scope `courses.read` chưa chắc cho phép đọc khóa học của người khác.

**Resource Server không được dùng ID token làm access token.** ID token dành cho OIDC Client xác thực thông tin đăng nhập; nó không phải chứng chỉ ủy quyền gọi Course API.

Phản hồi HTTP thường mang ý nghĩa:

- **401 Unauthorized:** thiếu hoặc không có thông tin xác thực hợp lệ; Resource Server có thể trả thử thách Bearer.
- **403 Forbidden:** đã có ngữ cảnh xác thực nhưng thiếu quyền cần thiết, ví dụ không có scope phù hợp.

Chi tiết 401/403 phụ thuộc cách cấu hình và tính chất lỗi, nhưng đây là cách phân biệt hữu ích khi đọc log và xử lý sự cố.

## 6. Theo dõi một giao dịch Authorization Code + PKCE

Dưới đây là luồng điển hình khi Lan đăng nhập Study Portal rồi xem khóa học. Vì module có OIDC, ví dụ yêu cầu cả scope `openid` để đăng nhập và `courses.read` để gọi API.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Lan (Resource Owner)
    participant B as Trình duyệt
    participant C as Study Portal (Client)
    participant AS as Campus Identity (Authorization Server / OP)
    participant RS as Course API (Resource Server)

    U->>B: Mở trang khóa học
    B->>C: GET /my-courses
    C-->>B: Redirect đến authorization endpoint
    B->>AS: client_id, redirect_uri, scope, state, code_challenge, nonce
    AS->>U: Đăng nhập, consent nếu cần
    U-->>AS: Hoàn thành bước xác thực/ủy quyền
    AS-->>B: Redirect về Client với code và state
    B->>C: GET /login/oauth2/code/campus?code=...&state=...
    C->>C: Kiểm tra state
    C->>AS: Đổi code + code_verifier (và client authentication nếu cần)
    AS-->>C: access_token, id_token, có thể refresh_token
    C->>C: Xác thực ID token; thiết lập phiên đăng nhập
    C->>RS: GET /api/me/courses + Bearer access_token
    RS->>RS: Xác thực token + kiểm tra quyền tài nguyên
    RS-->>C: Danh sách khóa học được phép xem
    C-->>B: Trang dữ liệu
~~~

Các bước cần hiểu rõ:

1. **Client bắt đầu yêu cầu ủy quyền.** Nó gửi `response_type=code`, `client_id`, `redirect_uri`, scope và các giá trị bảo vệ như `state`, PKCE `code_challenge`. OIDC Client cũng có thể gửi `nonce` để ràng buộc ID token với yêu cầu.
2. **Resource Owner tương tác với Authorization Server.** Lan nhập thông tin xác thực vào giao diện đáng tin cậy của Campus Identity. Nếu chính sách yêu cầu, Lan xem và chấp thuận phạm vi chia sẻ.
3. **Authorization Server trả code qua redirect.** Trình duyệt quay về redirect URI đã đăng ký. Client kiểm tra `state` nhằm liên kết callback với giao dịch đã khởi tạo.
4. **Client đổi code lấy token.** Yêu cầu đến token endpoint chứa `code_verifier`; confidential client cũng xác thực bản thân theo cấu hình. Authorization Server kiểm tra các ràng buộc rồi cấp token.
5. **Client xử lý đăng nhập OIDC.** Nếu có `openid`, client kiểm tra ID token theo các quy tắc OIDC, gồm chữ ký, issuer, audience, thời hạn và nonce khi đã sử dụng, rồi thiết lập phiên đăng nhập của ứng dụng.
6. **Client gọi Resource Server.** Nó truyền access token bằng Bearer Authorization header. API kiểm tra token và quyền thực tế trước khi trả dữ liệu.
7. **Vòng đời tiếp theo.** Access token hết hạn có thể dẫn tới một lần ủy quyền mới hoặc dùng refresh token nếu client được cấp và chính sách cho phép. Việc người dùng đăng xuất khỏi Portal không tự động bảo đảm mọi access token đã phát hành bị thu hồi ngay.

Ví dụ các tham số của authorization request (giá trị minh họa, cần URL-encode khi tạo URL thực):

~~~text
GET https://login.example.org/oauth2/authorize
  ?response_type=code
  &client_id=study-portal
  &redirect_uri=https%3A%2F%2Fportal.example.org%2Flogin%2Foauth2%2Fcode%2Fcampus
  &scope=openid%20profile%20courses.read
  &state=<random-state>
  &code_challenge=<S256-derived-challenge>
  &code_challenge_method=S256
  &nonce=<random-nonce>
~~~

`state`, `nonce` và `code_verifier` phải được sinh mới, đủ ngẫu nhiên và quản lý phù hợp từng giao dịch. Đừng sao chép các chuỗi minh họa thành giá trị cố định.

### Các kênh và ranh giới tin cậy

- **Front channel:** trình duyệt đi qua authorization endpoint và redirect URI. Vì URL có thể lộ qua lịch sử hoặc log, Authorization Code flow chỉ đưa code tạm thời qua kênh này.
- **Back channel:** backend client trao đổi code với token endpoint và gọi Resource Server qua HTTPS; nơi đây access token cần được bảo vệ.
- **Trust boundary:** Client tin Authorization Server đã cấu hình; Resource Server chỉ tin các token được phát hành, ký hoặc introspect bởi nguồn được chấp nhận, dành cho tài nguyên tương ứng.
- **Điểm ra quyết định:** Authorization Server quyết định cấp quyền/token; Resource Server quyết định có cho truy cập endpoint và đối tượng dữ liệu hay không.

## 7. Access Token, ID Token, Refresh Token và Scope

Bốn vai trò sẽ dễ nhầm nếu gộp mọi token thành một loại.

| Khái niệm | Ai nhận / sử dụng? | Mục đích | Có gửi đến Course API? |
| --- | --- | --- | --- |
| **Authorization code** | Client nhận qua redirect và gửi đến token endpoint | Đổi lấy token một lần | Không |
| **Access token** | Client giữ và gửi Resource Server | Chứng minh quyền truy cập được cấp cho API | **Có** |
| **ID token** (OIDC) | OIDC Client / Relying Party | Chứa thông tin về sự kiện xác thực và danh tính End-User | **Không** |
| **Refresh token** | Client gửi đến token endpoint khi đủ điều kiện | Xin access token mới theo chính sách | Không |

Access token có thể là **JWT** (API xác thực chữ ký và claims) hoặc **opaque token** (API thường hỏi introspection endpoint). Không có quy tắc OAuth 2.0 nào bắt buộc mọi access token phải là JWT.

**Scope** mô tả phạm vi quyền client xin và được cấp, ví dụ `courses.read`. Nó khác với:

- **Role:** vai trò nghiệp vụ của người dùng trong ứng dụng, ví dụ `TEACHER` hoặc `STUDENT`.
- **Audience (`aud`):** hệ thống hoặc đối tượng mà token được cấp cho.
- **Subject (`sub`):** định danh chủ thể trong ngữ cảnh token; cần hiểu theo loại token và issuer.
- **Consent:** bước thể hiện ý chí cho phép nếu được áp dụng, không thay thế kiểm tra scope hay chính sách của API.

Chẳng hạn, token có `courses.read` nhưng audience dành cho một API khác phải bị Course API từ chối. Ngay cả khi audience và scope phù hợp, câu hỏi “Lan có được đọc khóa học 123 hay không?” vẫn cần kiểm tra dữ liệu nghiệp vụ.

## 8. OIDC mở rộng mô hình OAuth như thế nào?

**OAuth 2.0** giải quyết vấn đề ủy quyền cho ứng dụng truy cập tài nguyên. **OpenID Connect (OIDC)** là lớp giao thức xây trên OAuth 2.0, bổ sung chuẩn xác thực người dùng và thông tin định danh cho client.

Cùng hệ thống Campus Identity có thể đóng đồng thời hai vai trò:

- **Authorization Server (OAuth 2.0):** xử lý yêu cầu cấp quyền và phát hành access token.
- **OpenID Provider, viết tắt OP (OIDC):** xác thực End-User và phát hành ID token có các claims theo chuẩn OIDC.

Tương tự, Study Portal là **OAuth2 Client** khi gọi Course API, và là **Relying Party (RP)** khi dùng ID token để biết ai đã đăng nhập.

| Cần giải quyết | Cơ chế thích hợp | Thành phần tiếp nhận |
| --- | --- | --- |
| “Ứng dụng được phép gọi API nào?” | OAuth 2.0 + access token / scope / audience | Resource Server |
| “Người nào vừa đăng nhập?” | OIDC + ID token được xác thực | Relying Party (Client) |
| “Lấy thông tin hồ sơ đã cho phép chia sẻ?” | OIDC UserInfo endpoint hoặc các claims được cấp theo quy tắc OP | OIDC Client |
| “Người này có được sửa khóa học số 123?” | Quy tắc ủy quyền nghiệp vụ, có thể kết hợp token claims | Course API |

Yêu cầu scope `openid` là tín hiệu client đang thực hiện OIDC. Các scope `profile` và `email` có thể xin thêm thông tin theo chính sách; chúng không tự bảo đảm mọi claim đều xuất hiện trong ID token. Giá trị `sub` ổn định trong phạm vi issuer/subject type phù hợp hơn email làm khóa định danh vì email có thể thay đổi hoặc chưa được xác minh.

**Không đánh đồng “đã đăng nhập qua OIDC” với “được truy cập mọi API”.** Ứng dụng có thể xác thực Lan thành công nhưng vẫn chưa có access token được phép gọi Course API.

## 9. Ánh xạ vào Spring Security

Spring Security cung cấp các cơ chế khác nhau tùy vai trò mà **ứng dụng Spring hiện tại** đảm nhiệm. Hai ứng dụng cùng dùng Spring không nhất thiết có cùng cấu hình.

| Nhiệm vụ của ứng dụng Spring | Khả năng / cấu hình tiêu biểu | Nó đóng vai trò gì? |
| --- | --- | --- |
| Cho người dùng đăng nhập bằng OpenID Provider | `oauth2Login()`, `ClientRegistration` | OIDC Client / Relying Party |
| Gọi API bên ngoài bằng access token | `oauth2Client()`, `OAuth2AuthorizedClient` | OAuth2 Client |
| Nhận Bearer token ở API của chính mình | `oauth2ResourceServer().jwt()` hoặc opaque token | Resource Server |
| Tự cung cấp authorization/token endpoints | Một triển khai Authorization Server riêng, ví dụ Spring Authorization Server | Authorization Server |

Chú ý: thêm cấu hình `oauth2Login()` **không biến Study Portal thành Authorization Server**. Nó chỉ giúp Portal đăng nhập thông qua một nhà cung cấp định danh bên ngoài. Tương tự, `oauth2ResourceServer()` chỉ giúp API bảo vệ endpoint nhận token, chứ không tự cấp token.

### 9.1. Study Portal: cấu hình OIDC Client

Ví dụ minh họa với ứng dụng Spring Boot dùng Spring Security và OIDC Provider công bố issuer metadata:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          campus:
            provider: campus
            client-id: ${CAMPUS_CLIENT_ID}
            client-secret: ${CAMPUS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
              - courses.read
        provider:
          campus:
            issuer-uri: https://login.example.org
~~~

Ví dụ trên giả định **confidential client** sử dụng client secret. Trong môi trường thực, `CAMPUS_CLIENT_ID` và `CAMPUS_CLIENT_SECRET` được cấp qua cấu hình bí mật; issuer và scope phải khớp nhà cung cấp đang tích hợp. Tên `campus` là `registrationId` cục bộ của Spring.

Spring Security dùng OIDC discovery từ `issuer-uri` để tra cứu các endpoint và khóa xác thực phù hợp khi nhà cung cấp hỗ trợ. Redirect URI cần đăng ký chính xác tại Authorization Server. Giá trị mặc định theo mẫu của Spring tạo callback như:

~~~text
https://portal.example.org/login/oauth2/code/campus
~~~

Cấu hình bảo vệ trang web:

~~~java
@Configuration
class PortalSecurityConfig {

    @Bean
    SecurityFilterChain portalSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Ví dụ chỉ thể hiện các thành phần liên quan; trong mã nguồn thực cần các import và dependency Spring Security phù hợp. Khi truy cập trang cần xác thực, Spring sẽ kích hoạt luồng đăng nhập qua provider đã cấu hình. Có thể chủ động bắt đầu tại:

~~~text
/oauth2/authorization/campus
~~~

Sau đăng nhập OIDC thành công, controller có thể truy cập danh tính đã được Spring xác thực:

~~~java
@GetMapping("/whoami")
Map<String, String> whoami(@AuthenticationPrincipal OidcUser user) {
    return Map.of(
        "subject", user.getSubject(),
        "issuer", user.getIssuer().toString()
    );
}
~~~

Ở đây `OidcUser` đại diện thông tin người dùng từ quy trình OIDC. Nó **không** phải access token để gửi sang Course API.

### 9.2. Study Portal: dùng access token gọi Resource Server

Spring lưu thông tin token gắn với một client registration và ngữ cảnh được ủy quyền trong `OAuth2AuthorizedClient`. Ví dụ controller có thể lấy đối tượng đó:

~~~java
@GetMapping("/my-token-metadata")
Map<String, String> tokenMetadata(
        @RegisteredOAuth2AuthorizedClient("campus")
        OAuth2AuthorizedClient authorizedClient) {

    return Map.of(
        "registrationId", authorizedClient.getClientRegistration().getRegistrationId(),
        "expiresAt", authorizedClient.getAccessToken().getExpiresAt().toString()
    );
}
~~~

Đây chỉ là ví dụ để quan sát metadata; **không trả giá trị access token trong response để debug**. Khi triển khai lời gọi thực, Client lấy `authorizedClient.getAccessToken().getTokenValue()` và gắn vào header `Authorization: Bearer ...` của yêu cầu HTTPS đến Course API, hoặc sử dụng HTTP client đã tích hợp OAuth2 của Spring Security. Cần bảo đảm cơ chế lấy token mới khi hết hạn tương thích loại client, authorized-client storage và grant type.

### 9.3. Course API: cấu hình Resource Server

Trong ứng dụng Spring Boot độc lập đóng vai trò Resource Server, cấu hình cho trường hợp **JWT access token** có thể bắt đầu như sau:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.org
~~~

Và quy tắc truy cập endpoint:

~~~java
@Configuration
class CourseApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/courses/**")
                .hasAuthority("SCOPE_courses.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Với JWT, Spring Security có thể xác minh chữ ký thông qua khóa tin cậy của issuer, kiểm tra các điều kiện token được hỗ trợ và chuyển scope thành authority dạng `SCOPE_...` theo cấu hình mặc định. Để bảo vệ API đúng cách, **cần cấu hình kiểm tra audience mong đợi** nếu đây là ràng buộc của hệ thống; không mặc định coi xác thực `issuer-uri` là đủ cho mọi trường hợp. API cũng phải kiểm tra quyền đến từng đối tượng dữ liệu, ví dụ khóa học thuộc người dùng nào.

Đoạn Java trên là khung minh họa; hệ thống API thuần Bearer token có thể cấu hình thêm phiên stateless, cách xử lý CSRF phù hợp loại credential và chính sách lỗi. Nếu provider phát hành opaque access token thay vì JWT, Resource Server phải dùng cơ chế introspection thích hợp, không thể mặc định parse token dưới dạng JWT.

### 9.4. Một ứng dụng có thể giữ nhiều vai trò

Vai trò gắn với **hành vi tại mỗi ranh giới giao tiếp**:

- Portal nhận ID token để đăng nhập: OIDC Client / RP.
- Portal cầm access token gọi Course API: OAuth2 Client.
- Course API xác thực Bearer token đến: Resource Server.
- Nếu Course API gọi một API khác bằng token của mình hoặc token được ủy quyền, Course API cũng là OAuth2 Client trong lời gọi đó.
- Campus Identity cấp token: Authorization Server và có thể là OpenID Provider.

Cần tách bạch các đường xử lý inbound/outbound token và mô hình xác thực phiên khi một Spring application vừa đăng nhập người dùng vừa tiếp nhận Bearer token. Việc gộp tất cả vào một `SecurityFilterChain` mà không phân định endpoint có thể tạo ra hành vi redirect sang màn hình đăng nhập ở API hoặc áp dụng sai chính sách.

## 10. Các tình huống giúp nhận diện đúng vai trò

### Tình huống A — Đăng nhập qua Google hoặc một IdP của doanh nghiệp

Người dùng mở ứng dụng Spring, được chuyển sang IdP để đăng nhập, rồi quay về ứng dụng. IdP đóng vai Authorization Server/OpenID Provider; ứng dụng Spring là OAuth2/OIDC Client. Nếu ứng dụng không có API được bảo vệ bằng Bearer token, nó **không nhất thiết** đóng vai Resource Server.

### Tình huống B — Backend xác minh JWT của người gọi

Mobile app gọi `GET /api/orders` với access token; backend Spring xác thực JWT và trả dữ liệu. Backend là Resource Server; mobile app là Client. Máy chủ phát hành JWT là Authorization Server. Backend không trở thành Authorization Server chỉ vì nó kiểm tra chữ ký JWT.

### Tình huống C — Một service gọi service khác bằng Client Credentials

Billing Service xin access token của chính nó rồi gọi Inventory API. Billing Service là Client; Identity Service là Authorization Server; Inventory API là Resource Server. Luồng này không có người dùng trực tiếp thực hiện đăng nhập hoặc consent; tránh gán nhầm một tài khoản kỹ thuật thành Resource Owner là con người.

### Tình huống D — Frontend, Backend for Frontend (BFF) và API

Browser nói chuyện với BFF qua cookie session; BFF làm confidential OAuth2 Client, giữ token phía server và gọi Resource Server. Browser là user agent trong luồng đăng nhập. Phân biệt này quan trọng khi chọn vị trí lưu token và cơ chế chống CSRF.

## 11. Những nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “OAuth 2.0 token chứng minh ai đang đăng nhập.” | Access token chủ yếu phục vụ ủy quyền API; OIDC ID token phục vụ xác thực danh tính đối với Relying Party. |
| “Client có scope trong request thì đã được quyền.” | Scope trong request chỉ là đề nghị; quyền được cấp và kiểm tra thực tế có thể hẹp hơn. |
| “Resource Server là nơi phát hành access token.” | Authorization Server phát hành; Resource Server kiểm tra và sử dụng token để bảo vệ tài nguyên. |
| “Mọi access token là JWT.” | OAuth cho phép token có định dạng khác, bao gồm opaque token. |
| “ID token có thông tin user nên dùng gọi API được.” | API phải nhận access token dành cho API; ID token có audience và mục tiêu khác. |
| “Backend giữ JWT nên chính là OAuth2 Client.” | Chỉ giữ/kiểm tra token trên request vào là hành vi Resource Server; dùng token đi gọi API mới là Client. |
| “User được cấp `courses.read` thì đọc khóa học nào cũng được.” | API vẫn phải kiểm tra quyền trên bản ghi, tổ chức và chính sách nghiệp vụ. |
| “Spring Security `oauth2Login` tự triển khai Identity Provider.” | `oauth2Login` tích hợp ứng dụng với provider ngoài; cần Authorization Server riêng để cấp token. |
| “Lấy được code trên callback là đăng nhập xong.” | Client phải kiểm tra `state`, trao đổi code hợp lệ; với OIDC cần xác thực ID token trước khi tin danh tính. |

## 12. Nguyên tắc bảo mật theo từng vai trò

**Resource Owner / End-User**

- Chỉ đăng nhập trên trang Authorization Server/OP đáng tin cậy.
- Đọc thông tin quyền được xin khi có consent và hiểu client sẽ sử dụng dữ liệu nào.

**Client**

- Ưu tiên Authorization Code + PKCE cho luồng có người dùng; tránh Implicit flow và Resource Owner Password Credentials trong thiết kế mới.
- Kiểm tra `state`, dùng redirect URI đã đăng ký chính xác, bảo vệ `nonce` khi sử dụng và kiểm tra ID token theo OIDC.
- Giữ client secret, access token và refresh token phù hợp loại client; không đưa token vào URL hoặc log; sử dụng HTTPS.
- Xin scope tối thiểu, lưu token đủ thời gian cần thiết và hỗ trợ chiến lược hết hạn/thu hồi token.

**Authorization Server / OP**

- Xác thực client đúng phương thức, kiểm tra redirect URI và ràng buộc PKCE.
- Chỉ cấp token theo grant type, scope và chính sách cho phép; đặt vòng đời token thích hợp.
- Công bố issuer/khóa và metadata chính xác, vận hành xoay khóa và thu hồi token theo nhu cầu hệ thống.

**Resource Server**

- Chỉ chấp nhận access token từ issuer tin cậy, dành cho API và còn hợp lệ.
- Xác thực chữ ký JWT hoặc dùng introspection đúng cách cho opaque token.
- Kiểm tra scope/authority cùng với phân quyền tài nguyên, tenant và nghiệp vụ.
- Không dùng ID token thay access token; tránh tiết lộ nội dung token hoặc dữ liệu nhạy cảm khi báo lỗi.

## 13. Tự kiểm tra sự hiểu bài

**Câu 1.** Người dùng đăng nhập thành công qua OIDC nhưng Course API trả HTTP 403. Vai trò nào cần kiểm tra quyền truy cập API?

> Resource Server (Course API) kiểm tra scope và chính sách truy cập; Client cũng cần kiểm tra đã xin/nhận đúng quyền. Đăng nhập thành công không đủ để đảm bảo được phép gọi API.

**Câu 2.** Một service Spring chỉ cấu hình `oauth2ResourceServer().jwt()`. Service đó có tự phát hành access token cho ứng dụng khác không?

> Không. Nó đang nhận và xác thực access token như một Resource Server; việc cấp token thuộc Authorization Server.

**Câu 3.** Trong Authorization Code flow, vì sao callback đưa code cho client thay vì access token?

> Client có thể đổi code tại token endpoint qua kênh trực tiếp, dùng PKCE và xác thực client khi cần. Cách này hạn chế rủi ro để access token xuất hiện ở trình duyệt/URL chuyển hướng.

**Câu 4.** Study Portal nhận ID token có `sub=lan123`. Nó có thể gửi ID token đó vào header Bearer để gọi Course API không?

> Không. ID token dành cho OIDC Client xác thực việc đăng nhập. API cần access token hợp lệ, có audience/scope và các quyền phù hợp.

**Câu 5.** Trong hệ thống sử dụng Client Credentials, vai trò nào vẫn xuất hiện rõ ràng và vai trò nào không có người dùng tương tác?

> Client, Authorization Server và Resource Server vẫn rõ ràng. Luồng không yêu cầu Resource Owner là người dùng tương tác để chấp thuận yêu cầu tại thời điểm cấp token.

---

## Ghi nhớ

Đọc mọi sơ đồ OAuth 2.0 theo bốn câu hỏi: **Ai có thẩm quyền đối với tài nguyên?** (Resource Owner), **ứng dụng nào xin quyền?** (Client), **ai cấp token?** (Authorization Server), và **ai kiểm tra token trước khi cho truy cập dữ liệu?** (Resource Server). Khi thêm OIDC, client còn có thể xác thực danh tính người dùng dựa trên **ID token** của OpenID Provider. Trong Spring Security, các cơ chế `oauth2Login`, `oauth2Client` và `oauth2ResourceServer` tương ứng những trách nhiệm khác nhau của các vai trò ấy.
