# User và client trong ranh giới tin cậy

> **Chương:** Trust boundary  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** tìm hiểu xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này làm rõ sự khác nhau giữa **người dùng (user)** và **ứng dụng khách (client)**, từ đó xác định ai đang yêu cầu, ai gửi request, ai được xác thực và thành phần nào phải kiểm tra quyền.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt user, client application, user agent, device, service account và principal trong một request.
2. Giải thích vì sao client ID hoặc client authentication không chứng minh người dùng cuối là ai.
3. Mô hình hóa ranh giới tin cậy giữa trình duyệt/ứng dụng di động, backend, API gateway, identity provider và resource server.
4. Nhận diện dữ liệu do client kiểm soát, bao gồm URL, body, header, cookie, local storage và các giá trị nhận diện người dùng.
5. Chọn cách truyền danh tính và token phù hợp với public client, confidential client, BFF và service-to-service.
6. Thiết kế kiểm tra authentication, authorization, CSRF, CORS, session và token theo đúng trách nhiệm của từng thành phần.
7. Kiểm thử các tình huống giả mạo user ID, client ID, tenant, role, header và truy cập trực tiếp API.

## 2. User và client trả lời hai câu hỏi khác nhau

**User (người dùng)** là con người hoặc chủ thể sử dụng hệ thống. User có thể sở hữu một tài khoản, đăng nhập bằng mật khẩu/passkey/MFA, được cấp principal và được phân quyền theo vai trò, quan hệ, tenant hoặc chính sách.

**Client (ứng dụng khách)** là phần mềm thay mặt người dùng hoặc một hệ thống khác để gửi yêu cầu tới dịch vụ. Client có thể là ứng dụng web chạy trong trình duyệt, ứng dụng di động, desktop app, backend server, script tích hợp hoặc một dịch vụ tự động.

Trong một request, hai câu hỏi cần tách biệt:

- **User:** ai là người hoặc chủ thể mà thao tác đang được thực hiện cho/nhân danh?
- **Client:** thành phần phần mềm nào đang gửi request và theo cơ chế nào?

Ví dụ, An dùng trình duyệt để mở ứng dụng ngân hàng. Trình duyệt là user agent/client ở phía giao diện; ứng dụng ngân hàng có backend riêng; API thanh toán nhận request từ backend. Người dùng An, ứng dụng web, backend và dịch vụ thanh toán là những thực thể khác nhau, có thể có danh tính và quyền riêng.

| Thành phần | Ví dụ | Ý nghĩa bảo mật |
|---|---|---|
| **User** | An, tài khoản A-104 | Chủ thể nghiệp vụ cần được xác thực và phân quyền |
| **User account** | Bản ghi A-104 | Hồ sơ và trạng thái tài khoản do hệ thống quản lý |
| **Client application** | Ứng dụng mobile com.example.bank | Phần mềm gửi yêu cầu; có thể có client ID riêng |
| **User agent** | Chrome, Safari, ứng dụng nhúng WebView | Môi trường thực thi và gửi request của người dùng |
| **Device** | Điện thoại của An | Thiết bị có trạng thái, khóa, chứng chỉ và mức độ tin cậy riêng |
| **Backend service** | bank-web-backend | Thành phần server có thể xác thực client/service và xử lý thay người dùng |
| **Resource server** | API tài khoản/thanh toán | Kiểm tra token và quyền trên tài nguyên mà nó quản lý |
| **Principal** | Principal đại diện An hoặc service | Danh tính được framework bảo mật dùng trong ngữ cảnh request |

**Một người có thể dùng nhiều client; một client có thể phục vụ nhiều người; một request có thể đi qua nhiều dịch vụ.** Vì vậy không nên dùng một giá trị như clientId, userId hay địa chỉ IP để đại diện cho tất cả các thực thể này.

## 3. Bản đồ ranh giới tin cậy

Ranh giới tin cậy xuất hiện ở nơi dữ liệu hoặc quyền đi từ một miền kiểm soát sang miền khác. Với ứng dụng web điển hình:

~~~mermaid
flowchart LR
    U["User<br/>Người dùng"] -->|"Tương tác"| B["Browser / Mobile<br/>Client không đáng tin hoàn toàn"]
    B -->|"HTTPS: request, cookie, token"| E["Ingress / API Gateway<br/>Biên mạng"]
    E -->|"Forward request + context đã chuẩn hóa"| S["Backend / BFF<br/>Miền server"]
    S -->|"Token hoặc service identity"| R["Resource API"]
    S <-->|"OIDC / OAuth"| I["Identity Provider"]
    R --> D[("Database / Resource")]
    S --> P["Authorization Policy"]
    P --> R
~~~

Sơ đồ khái niệm này có một số ranh giới cần chú ý:

1. **User → client:** người dùng nhập dữ liệu, chọn tenant, bấm nút và có thể thao tác ngoài ý muốn. Client có thể bị sửa đổi hoặc bị chiếm quyền.
2. **Client → ingress:** request đến từ mạng không đáng tin; ingress phải xử lý TLS, giới hạn kích thước, rate limit và chuẩn hóa proxy headers.
3. **Ingress → backend:** backend chỉ tin các metadata được ingress thiết lập theo cấu hình xác thực; không tin header cùng tên do client tự gửi.
4. **Backend → IdP:** luồng liên kết danh tính phải dùng đúng issuer, redirect URI, state, nonce, PKCE và client authentication khi cần.
5. **Backend → resource API:** service identity, user identity và quyền được ủy quyền phải được phân biệt.
6. **Backend/API → database:** truy vấn phải áp dụng tenant, ownership và chính sách dữ liệu; không mặc định client đã lọc đúng.

Không có nghĩa mọi browser hay mobile app đều phải bị xem là độc hại. Ý nghĩa của “không đáng tin hoàn toàn” là server **không thể dựa vào client để tự xác nhận các thuộc tính bảo mật quan trọng**. Client hỗ trợ trải nghiệm, nhưng quyết định bảo mật phải được thực thi ở thành phần có quyền kiểm soát và nguồn dữ liệu phù hợp.

## 4. Client ID không phải user ID

Trong OAuth 2.0/OIDC, một ứng dụng thường được đăng ký với **client identifier (client_id)**. Giá trị này giúp authorization server nhận diện ứng dụng đang tham gia giao thức. Nó thường không phải bí mật.

Một người dùng có thể đăng nhập vào client web-portal, ios-app hoặc partner-console. Nhiều người dùng cùng sử dụng một client ID. Client ID vì thế không thể trả lời “người nào đang dùng ứng dụng?”.

Ngược lại, sub hoặc user ID có thể nhận diện chủ thể trong một miền định danh cụ thể, nhưng nếu client tự gửi một giá trị user ID thì server chưa có bằng chứng rằng request thực sự thuộc về người đó.

| Giá trị | Nhận diện điều gì? | Có tự xác thực user không? |
|---|---|---|
| client_id | Ứng dụng khách được đăng ký | **Không** |
| client_secret | Bí mật của confidential client, nếu được dùng đúng cách | **Không**; chứng minh client nắm bí mật, không chứng minh user |
| sub trong token đã xác minh | Subject theo issuer và ngữ cảnh token | Có thể là định danh user hoặc subject khác theo profile; phải hiểu issuer và loại token |
| userId trong URL/body | Giá trị client yêu cầu server xử lý | **Không**; phải đối chiếu với principal và policy |
| Session cookie | Tham chiếu/bằng chứng bearer liên kết request với phiên | Chỉ khi server xác minh phiên và trạng thái; bị đánh cắp có thể bị lạm dụng |
| Access token | Token cấp quyền truy cập cho resource server theo ngữ cảnh | Không mặc nhiên là “user đã đăng nhập”; cần kiểm tra token type, audience, subject/client và quyền |

### Client authentication khác user authentication

**Client authentication** chứng minh ứng dụng khách được phép tham gia hoặc gọi một endpoint theo cấu hình. **User authentication** chứng minh chủ thể người dùng đã đáp ứng phương thức xác thực. Hai việc có thể cùng diễn ra trong một luồng, nhưng không thay thế nhau.

Ví dụ, backend server có client_id và client_secret hợp lệ để đổi authorization code tại token endpoint. Điều này xác thực backend là confidential client theo cấu hình; nó không có nghĩa mọi người gọi backend đều là quản trị viên. Backend vẫn cần xác thực user và giới hạn quyền của user.

## 5. Public client và confidential client

OAuth 2.0 phân biệt client dựa trên khả năng giữ bí mật thông tin xác thực client:

| Loại client | Ví dụ | Có giữ client secret an toàn lâu dài không? | Hướng triển khai |
|---|---|---|---|
| **Public client** | SPA chạy trong trình duyệt, ứng dụng mobile/desktop phân phối tới thiết bị người dùng | Thông thường **không**; secret có thể bị trích xuất từ mã hoặc thiết bị | Authorization Code Flow + PKCE; không nhúng secret dùng chung vào ứng dụng |
| **Confidential client** | Backend server, ứng dụng chạy trên hạ tầng được quản lý | Có thể giữ bí mật ở môi trường server có kiểm soát | Client authentication phù hợp, bảo vệ secret/key, hạn chế quyền và xoay vòng |

Một ứng dụng mobile có thể dùng khóa riêng trong secure hardware hoặc cơ chế attestation cho một số mục đích, nhưng không vì vậy mà mọi chuỗi bí mật được nhúng trong binary trở thành client secret dùng chung an toàn. Thiết kế phải xét khả năng trích xuất, clone, kiểm soát thiết bị và profile giao thức.

**Không đặt client secret trong JavaScript frontend, source map, file cấu hình tải xuống, APK/IPA hoặc biến môi trường được bundle vào client.** Người dùng có thể kiểm tra nội dung client hoặc trích xuất giá trị. Nếu một SPA cần gọi API, hãy dùng mô hình public client phù hợp và token có scope/audience giới hạn.

## 6. OAuth/OIDC: client đại diện user như thế nào?

Trong Authorization Code Flow, client có thể khởi tạo một giao dịch để người dùng đăng nhập tại IdP. Sau khi người dùng xác thực và cấp quyền theo luồng, client nhận authorization code rồi đổi lấy token. Bảo vệ phổ biến gồm:

- **Authorization Code Flow:** dùng code thay vì đưa token trực tiếp qua URL của browser.
- **PKCE:** tạo code verifier/challenge để ràng buộc việc đổi code với client đã khởi tạo.
- **state:** liên kết callback với giao dịch do client tạo, hỗ trợ phòng chống CSRF/login response injection theo profile.
- **nonce:** trong OIDC, ràng buộc ID token với yêu cầu xác thực tương ứng.
- **Redirect URI chính xác:** chỉ chuyển kết quả về địa chỉ đã đăng ký, không cho tham số bên ngoài tùy ý quyết định callback.
- **Client authentication:** áp dụng cho confidential client ở endpoint tương ứng; public client không dựa vào secret nhúng để chứng minh danh tính.

~~~mermaid
sequenceDiagram
    autonumber
    actor User as User
    participant Client as Browser / App Client
    participant IdP as Authorization Server / IdP
    participant API as Resource API

    User->>Client: Chọn đăng nhập
    Client->>Client: Tạo state, nonce, PKCE verifier
    Client-->>User: Redirect tới IdP với challenge
    User->>IdP: Xác thực user bằng passkey/MFA/credential
    IdP-->>Client: Callback với authorization code + state
    Client->>Client: So khớp state và giao dịch
    Client->>IdP: Đổi code + PKCE verifier
    IdP-->>Client: Token theo giao thức
    Client->>Client: Xác minh ID token nếu là OIDC client
    Client->>API: Gửi access token cho API
    API->>API: Xác minh token, audience, expiry và policy
    API-->>Client: Chỉ trả dữ liệu được phép
~~~

Trong mô hình backend, một số bước diễn ra giữa server và IdP thay vì trực tiếp trong browser. Điều đó giảm việc token phải nằm trong JavaScript, nhưng không loại bỏ yêu cầu kiểm tra user, client, token và quyền.

### Đừng nhầm ID token và access token

- **ID token** là phát biểu OIDC về sự kiện xác thực và subject dành cho client/RP.
- **Access token** dành cho resource server/API; API phải xác minh đúng issuer, audience, thời hạn, quyền và loại token.
- **Refresh token** có thể cấp lại token theo chính sách, nên cần bảo vệ nghiêm ngặt và chỉ lưu ở nơi phù hợp với loại client.

Một API không nên nhận ID token làm access token chỉ vì cả hai đều có thể là JWT. API cũng không nên tin sub hoặc role trong token trước khi xác minh chữ ký và các claim bắt buộc.

## 7. Trình duyệt và ứng dụng mobile là môi trường client có giới hạn

### 7.1. Browser

Trình duyệt chạy mã JavaScript và hiển thị giao diện. Người dùng có thể mở Developer Tools, thay request, sửa local state, gọi API trực tiếp hoặc dùng script khác. XSS có thể chạy mã trong origin của ứng dụng và đánh cắp dữ liệu mà JavaScript có quyền đọc.

Do đó:

- Không coi giá trị hidden input, React state, local storage, URL parameter hoặc nút bị disable là kiểm soát quyền.
- Không đưa bí mật client hoặc dữ liệu xác thực dài hạn vào bundle.
- Bảo vệ cookie phiên bằng Secure, HttpOnly, SameSite phù hợp và quản lý vòng đời.
- Chống XSS bằng output encoding, sanitization đúng ngữ cảnh, CSP và tránh API nguy hiểm; cookie HttpOnly giảm khả năng đọc cookie bằng JavaScript nhưng không ngăn XSS thực hiện request thay người dùng.
- Nếu dùng cookie tự động gửi theo request, đánh giá CSRF và dùng token/biện pháp chống CSRF phù hợp.
- Kiểm tra quyền tại backend trên từng endpoint, object và tenant.

### 7.2. Mobile / desktop

Ứng dụng mobile/desktop được cài trên thiết bị do người dùng kiểm soát. Binary có thể bị phân tích, instrument, sửa đổi hoặc chạy trên môi trường giả lập. Có thể dùng secure storage, OS keystore, hardware-backed key, app attestation và device posture để tăng mức bảo đảm, nhưng:

- Không nhúng một client secret chung cho mọi bản cài.
- Không coi User-Agent hoặc device ID do app gửi là danh tính được xác thực.
- Bảo vệ refresh token bằng cơ chế lưu trữ phù hợp; tránh ghi token vào log, clipboard, crash report hoặc backup không an toàn.
- Sử dụng trình duyệt hệ thống cho luồng OAuth/OIDC khi profile khuyến nghị, thay vì tự dựng form nhập mật khẩu IdP trong ứng dụng.
- Có chiến lược thu hồi phiên/thiết bị và xử lý khi điện thoại mất hoặc bị root/jailbreak.

## 8. BFF: đưa token ra khỏi JavaScript frontend

**Backend for Frontend (BFF)** là một backend dành riêng cho giao diện web. Browser giữ cookie phiên của BFF; BFF thực hiện luồng OIDC và lưu token ở phía server, sau đó gọi API thay cho browser.

~~~mermaid
flowchart LR
    U["User"] --> B["Browser<br/>Không giữ access token dài hạn"]
    B -->|"Cookie phiên"| F["BFF<br/>Server-side session + token store"]
    F <-->|"OIDC"| I["Identity Provider"]
    F -->|"Access token theo audience"| A["Resource API"]
    A --> D[("Resource data")]
~~~

Ưu điểm:

- Access/refresh token không phải nằm trong JavaScript runtime hoặc local storage.
- BFF có thể áp dụng chính sách session, đổi token và kiểm soát request tới API.
- Backend có thể gắn user context đáng tin từ session đã xác thực.

Rủi ro vẫn còn:

- Cookie phiên là bearer credential; nếu bị đánh cắp, kẻ tấn công có thể dùng phiên.
- Cookie tự động gửi theo request tạo rủi ro CSRF; BFF cần biện pháp chống CSRF và kiểm tra Origin/Referer phù hợp.
- XSS vẫn có thể khiến browser gửi request tới BFF dưới phiên của người dùng, dù không đọc được HttpOnly cookie.
- BFF cần kiểm tra authorization cho từng hành động, không chỉ xác thực cookie.
- Nếu BFF có quyền service rộng, phải tránh confused deputy: không để client yêu cầu tùy ý hành động mà BFF dùng quyền rộng của nó thực hiện.

BFF là một lựa chọn kiến trúc, không phải cơ chế tự động giải quyết mọi rủi ro browser.

## 9. Header, IP và dữ liệu client gửi: đâu là nguồn đáng tin?

Client có thể gửi:

~~~http
GET /api/accounts/A-104?tenant=T1 HTTP/1.1
Host: api.example.test
X-User-Id: admin
X-Role: ADMIN
X-Tenant-Id: T1
X-Forwarded-For: 10.0.0.5
Authorization: Bearer <access-token>
~~~

Trong ví dụ này, các header X-User-Id, X-Role, X-Tenant-Id và X-Forwarded-For có thể do client tự tạo. Chúng không trở thành sự thật chỉ vì tên nghe có vẻ nội bộ. API phải:

1. Xác thực access token/session theo cấu hình tin cậy.
2. Tạo principal từ bằng chứng đã xác minh, không từ X-User-Id.
3. Tra cứu tenant membership/role từ nguồn dữ liệu đáng tin hoặc claim được phát hành đúng mục đích và còn hiệu lực.
4. Kiểm tra user có quyền trên account A-104 tại tenant T1 hay không.
5. Chỉ dùng forwarding header khi request đến từ proxy được tin cậy, proxy đó loại bỏ header client tự gửi và thiết lập giá trị chuẩn.

### Proxy và API gateway

Một gateway có thể xác thực token trước backend rồi truyền metadata đã chuẩn hóa. Để backend tin metadata này, cần ràng buộc rõ:

- Backend chỉ nhận traffic từ gateway qua mạng/kênh được kiểm soát hoặc xác thực service-to-service.
- Gateway xóa header danh tính do client cung cấp và tự tạo header mới sau xác minh.
- Không có đường truy cập trực tiếp tới backend bỏ qua gateway, hoặc backend vẫn tự kiểm tra bằng chứng.
- Quy ước về issuer, subject, tenant, audience và thời hạn được thống nhất.
- Các dịch vụ ghi log actor gốc và service trung gian để có thể truy vết.

Nếu backend cũng có thể nhận request từ Internet hoặc từ một service không tin cậy, không được mặc định header identity do gateway thường dùng là hợp lệ.

## 10. Authentication và authorization ở đúng nơi

**Authentication** thiết lập principal từ credential/session/token đã xác minh. **Authorization** quyết định principal có được làm một hành động trên tài nguyên trong ngữ cảnh hiện tại hay không.

Ví dụ:

- Browser gửi userId=A-104 để xem hóa đơn. Server bỏ qua danh tính tự khai và lấy principal từ phiên/token.
- Server ánh xạ principal tới account A-104.
- API tải hóa đơn INV-42 và kiểm tra owner, tenant, quyền invoice:read cùng trạng thái nghiệp vụ.
- Nếu user đăng nhập hợp lệ nhưng hóa đơn thuộc account khác, API từ chối.

| Lớp | Trách nhiệm | Không nên dựa vào |
|---|---|---|
| Client/UI | Hiển thị, thu thập input, điều hướng | Nút ẩn, role trong state, ID do người dùng tự chọn |
| Authentication middleware | Xác minh session/token/certificate và thiết lập principal | Header tùy ý, userId trong body |
| Authorization/service | Kiểm tra hành động, object, tenant và policy | Client đã lọc dữ liệu hoặc “đã đăng nhập là được” |
| Data access | Truy vấn trong phạm vi được phép | Truy vấn theo ID mà không giới hạn ownership/tenant |
| Audit | Ghi actor, client/service, resource, action và kết quả | Email/display name làm định danh duy nhất |

Nguyên tắc **deny by default** và **least privilege** cần được thực thi tại server. Nếu có quyền đọc nhưng không có quyền sửa, API PATCH vẫn phải bị từ chối dù UI không hiển thị nút sửa.

## 11. CSRF, CORS và XSS: ba khái niệm không thay thế nhau

Các lỗi này thường bị nhầm khi thiết kế trust boundary cho browser:

| Cơ chế | Vấn đề giải quyết | Không giải quyết được |
|---|---|---|
| **CSRF protection** | Ngăn trang/site khác lợi dụng trình duyệt gửi request có credential tự động đính kèm (thường cookie) | Không ngăn XSS cùng origin; không thay authorization |
| **CORS** | Kiểm soát browser JavaScript từ origin nào được đọc response cross-origin theo chính sách | Không phải xác thực user; không phải firewall/API authorization; request vẫn có thể tới server trong một số trường hợp |
| **XSS protection** | Ngăn mã không tin cậy chạy trong origin ứng dụng | Không thay kiểm tra quyền tại server; HttpOnly không ngăn script dùng browser thực hiện request |

**CSRF:** nếu session được mang bằng cookie, browser có thể tự gửi cookie khi request phù hợp. Cần token chống CSRF hoặc biện pháp tương đương, cấu hình SameSite, kiểm tra Origin/Referer trong ngữ cảnh phù hợp và bảo vệ endpoint thay đổi trạng thái.

**CORS:** chỉ cho phép origin cần thiết, không phản chiếu Origin tùy ý với credentials. CORS không ngăn một attacker gọi endpoint từ server riêng, curl hoặc ứng dụng khác; nó chủ yếu là chính sách của browser về việc script đọc response.

**XSS:** output encoding theo ngữ cảnh, sanitization, CSP và tránh DOM injection. Nếu script độc hại chạy cùng origin, nó có thể gọi API dưới danh tính người dùng ngay cả khi không đọc được HttpOnly cookie.

## 12. Service-to-service và “on behalf of”

Một backend có thể gọi service khác theo hai cách khác nhau:

1. **Service identity:** dịch vụ gọi bằng danh tính máy của chính nó, ví dụ report-service. Quyền phản ánh nhiệm vụ của service.
2. **Delegated user context:** dịch vụ gọi thay mặt An, với phạm vi được ủy quyền và giới hạn theo An. API nhận cần phân biệt service nào đang thực hiện và user nào là subject được đại diện.

Ví dụ:

~~~text
Actor / caller: report-service
Subject / user context: account A-104
Audience: document-api
Action: document:read
Resource: DOC-12
Delegation: report-service được phép đọc DOC-12 thay A-104
~~~

Nếu report-service có quyền đọc tất cả tài liệu, nhưng chỉ cần xử lý tài liệu của An, API cần ràng buộc quyền đại diện hoặc dùng token/ủy quyền giới hạn. Không nên nhận X-User-Id: A-104 từ frontend rồi để service sử dụng quyền rộng của mình mà không xác minh delegation.

### Confused deputy

**Confused deputy** xảy ra khi một thành phần có quyền cao bị lừa dùng quyền của nó cho yêu cầu không được phép của caller. Ví dụ, BFF có service token toàn quyền xuất báo cáo; browser gửi reportId của tenant khác và BFF xuất dữ liệu chỉ vì token service hợp lệ.

Biện pháp:

- Xác thực user và client/service riêng.
- Kiểm tra quyền user đối với tài nguyên và hành động.
- Giới hạn service token theo audience, scope và thời hạn.
- Truyền delegation đã xác minh nếu downstream cần biết user gốc.
- Ghi log cả actor thực hiện và subject được đại diện.

## 13. Ví dụ Java/Spring: không lấy principal từ client input

Ví dụ dưới đây giả định API là OAuth2 Resource Server, nhận JWT access token và đã cấu hình issuer/audience cùng bộ xác minh phù hợp.

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/**").authenticated()
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

Controller lấy principal từ security context đã xác minh:

~~~java
@RestController
class InvoiceController {
    private final InvoiceService invoices;

    InvoiceController(InvoiceService invoices) {
        this.invoices = invoices;
    }

    @GetMapping("/api/invoices/{invoiceId}")
    InvoiceView read(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable UUID invoiceId,
            @RequestParam(required = false) String tenantId) {

        // Subject lấy từ token đã được resource-server xác minh.
        // tenantId từ query chỉ là yêu cầu chọn tenant, phải kiểm tra membership.
        return invoices.read(
            jwt.getIssuer().toString(),
            jwt.getSubject(),
            tenantId,
            invoiceId
        );
    }
}
~~~

Tầng service ánh xạ identity và thực thi authorization:

~~~java
InvoiceView read(
        String verifiedIssuer,
        String verifiedSubject,
        String requestedTenant,
        UUID invoiceId) {

    Account account = accounts.findByExternalIdentity(
        verifiedIssuer, verifiedSubject
    ).orElseThrow(AccessDeniedException::new);

    Tenant tenant = tenants.requireMembership(
        account.id(), requestedTenant
    );

    Invoice invoice = invoices.findByIdAndTenant(
        invoiceId, tenant.id()
    ).orElseThrow(ResourceNotFoundException::new);

    if (!policy.canReadInvoice(account, tenant, invoice)) {
        throw new AccessDeniedException("Access denied");
    }
    return InvoiceView.from(invoice);
}
~~~

Đây là ví dụ khung, các repository, policy và kiểu dữ liệu thuộc ứng dụng. Trong thực tế cần kiểm tra aud cho đúng API, trạng thái account, tenant membership, quyền ở cấp đối tượng và các claim cần thiết. Không nên chỉ dựa vào sub nếu hệ thống có nhiều issuer; dùng cặp issuer + subject đã xác minh để ánh xạ.

### Cấu hình browser dùng cookie

Nếu ứng dụng dùng session cookie, cần cân nhắc:

~~~text
Set-Cookie: __Host-session=<opaque-session-id>;
            Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Đây là minh họa thuộc tính cookie, không phải cấu hình hoàn chỉnh cho mọi kiến trúc. Prefix __Host- có các điều kiện riêng về Secure, Path và Domain; SameSite cần chọn theo luồng đăng nhập/redirect và yêu cầu ứng dụng. Endpoint thay đổi trạng thái vẫn cần đánh giá CSRF, và server phải rotate session sau khi đăng nhập để chống session fixation.

## 14. Các sai lầm phổ biến

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Xem client_id là danh tính user | Mọi người dùng cùng app bị gộp thành một principal | Tách client identity khỏi user identity |
| Đặt client_secret trong SPA/mobile | Secret bị trích xuất và dùng để giả mạo client | Dùng public client + PKCE; secret chỉ ở backend |
| Tin X-User-Id, X-Role do client gửi | User spoofing, privilege escalation | Lấy principal từ security context sau xác thực; role từ nguồn tin cậy |
| Chỉ ẩn nút trên UI để bảo vệ chức năng | Gọi API trực tiếp vẫn thực hiện được | Authorization server-side ở từng endpoint/action |
| Cho BFF dùng service token rộng mà không kiểm tra user | Confused deputy, truy cập chéo tenant | Kiểm tra user authorization và delegation |
| Dùng ID token gọi API | Nhầm mục đích token, audience và quyền | Dùng access token dành cho resource API |
| Cho CORS thay thế authorization | API có thể bị gọi ngoài browser hoặc bởi client khác | Xác thực và phân quyền ở API |
| Bỏ CSRF vì đã có CORS | Cookie tự gửi vẫn có thể bị lạm dụng | Thiết kế CSRF protection theo cách truyền credential |
| Tin IP/User-Agent để nhận diện user | Giả mạo, NAT, proxy, thiết bị dùng chung | Dùng IP/UA làm tín hiệu phụ, không làm principal |
| Không rotate session sau login | Session fixation | Tạo session ID mới sau xác thực và thay đổi mức quyền |
| Chỉ xác thực ở gateway, backend có đường gọi trực tiếp | Bypass gateway và giả mạo metadata | Bảo vệ service channel và xác minh context ở backend |

## 15. Ma trận kiểm thử ranh giới user/client

Giả sử user An thuộc tenant T1, user Bình thuộc tenant T2; client web portal là public-facing và backend BFF là confidential service.

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Client gửi X-User-Id: admin nhưng token/session là An | Principal vẫn là An; không nâng quyền |
| Client đổi tenantId=T1 thành T2 | Server kiểm tra membership; An không được tự chuyển sang T2 |
| Client thay invoice ID trong URL thành hóa đơn của Bình | Authorization từ chối hoặc ẩn sự tồn tại theo policy |
| Public client gửi client_secret giả | Không được coi secret là bằng chứng user; public client dùng PKCE |
| Token có aud dành cho API khác | Resource API từ chối |
| ID token được gửi vào API thay access token | API từ chối sai loại/audience token |
| Client tự đặt X-Forwarded-For thành IP nội bộ | Ingress bỏ/ghi đè; backend chỉ nhận metadata từ proxy tin cậy |
| Request có cookie hợp lệ nhưng thiếu CSRF token tại endpoint yêu cầu | Từ chối theo chính sách CSRF |
| CORS cho phép origin lạ với credentials | Kiểm thử cấu hình phải thất bại; không phản chiếu origin tùy ý |
| XSS chạy trong origin ứng dụng | CSP/output encoding ngăn; HttpOnly giảm đọc cookie nhưng API vẫn cần authorization |
| BFF nhận request xem dữ liệu tenant khác | BFF kiểm tra quyền user/delegation, không dùng service privilege một cách mù quáng |
| Gateway xác thực nhưng backend có đường truy cập trực tiếp | Backend vẫn được bảo vệ; không tin header nếu caller không phải gateway được xác minh |
| Đăng nhập thành công bằng IdP rồi session được tái sử dụng sau logout | Phiên bị thu hồi/hết hạn theo policy; session ID cũ không tiếp tục hợp lệ |
| Role trong local storage bị sửa thành ADMIN | Backend không thay đổi quyền theo client state |

Ngoài status code, cần kiểm tra **tác động thực tế**: database có bị đọc/sửa không, response có chứa dữ liệu ngoài tenant không, token có lọt vào log không, audit ghi đúng actor và user được đại diện không.

## 16. Quy trình thiết kế khi có user và nhiều client

Trước khi thêm một client mới hoặc endpoint mới, hãy xác định:

1. **Ai là user/subject?** Người dùng, service account, thiết bị hay tác vụ nền?
2. **Client nào gửi request?** Browser, mobile, backend hay service khác? Nó là public hay confidential?
3. **Client chứng minh danh tính bằng gì?** Client ID, secret, certificate, private key hoặc mTLS? Phương thức có phù hợp khả năng giữ bí mật không?
4. **User chứng minh danh tính bằng gì?** Session, access token, OIDC login, passkey/MFA hoặc certificate?
5. **Request đi qua những ranh giới nào?** Proxy, gateway, BFF, API và database có cùng hiểu đúng nguồn context không?
6. **Ai được quyền làm gì?** Kiểm tra action, resource, tenant, ownership và trạng thái ở server.
7. **Credential/session được lưu và thu hồi ở đâu?** Cookie, token store, device keystore, secret manager; có rotation, timeout, logout và revocation không?
8. **Có đường vòng nào?** API trực tiếp, header giả, tenant khác, job nền hoặc service token rộng có thể bỏ qua policy không?
9. **Audit có phân biệt actor và subject không?** Ghi rõ user gốc, client/service thực hiện, tài nguyên, action và kết quả.

## 17. Ghi nhớ trọng tâm

- **User và client là hai thực thể khác nhau.** User là chủ thể nghiệp vụ; client là phần mềm gửi yêu cầu. Một client có thể phục vụ nhiều user, một user có thể dùng nhiều client.
- **Client ID/client authentication không chứng minh danh tính người dùng.** Public client không thể giữ secret dùng chung an toàn; confidential client vẫn phải xác thực user và phân quyền user riêng.
- **Client là một ranh giới đầu vào cần kiểm chứng.** Không tin role, user ID, tenant, IP hoặc trạng thái UI do client tự khai.
- **Authentication tạo principal từ bằng chứng đã xác minh; authorization kiểm tra hành động và tài nguyên.** Cả hai phải được thực thi phía server.
- **Browser/mobile, BFF, gateway và backend có mức tin cậy khác nhau.** Phân biệt user identity, client identity, device identity và service identity; quản lý token, session, CSRF, CORS và XSS đúng vai trò.
- **Khi service gọi thay user, cần delegation và least privilege.** Tránh confused deputy bằng cách kiểm tra quyền user và giới hạn quyền service.

Thiết kế đúng mối quan hệ user/client giúp hệ thống không nhầm “ứng dụng hợp lệ đang gọi” với “người dùng hợp lệ có quyền”. Mỗi ranh giới cần một nguồn danh tính, một cơ chế xác minh và một quyết định quyền có thể kiểm tra được.
