# Mục đích của refresh token

Một ứng dụng quản lý đơn hàng có thể cấp **access token** chỉ còn hiệu lực trong 15 phút để giới hạn thời gian kẻ tấn công sử dụng token bị đánh cắp. Nhưng nếu cứ 15 phút người dùng phải đăng nhập lại, trải nghiệm sẽ rất bất tiện. **Refresh token** giải quyết mâu thuẫn này: cho phép client **xin access token mới từ Authorization Server** khi quyền được cấp và phiên ủy quyền vẫn còn hợp lệ, mà không bắt buộc người dùng lặp lại toàn bộ quá trình xác thực ở mỗi lần access token hết hạn.

Refresh token không phải một “access token sống lâu hơn” hay chìa khóa được phép mang tới mọi API. Nó là **credential được cấp có điều kiện để làm mới quyền truy cập**. Chính vì có thể sử dụng trong thời gian dài hơn access token, refresh token thường cần được bảo vệ nghiêm ngặt, gắn với client, giới hạn quyền và có khả năng thu hồi.

Bài học thuộc chương **Refresh token** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung đặt refresh token trong mô hình tin cậy của OAuth 2.0/OpenID Connect (OIDC), phân biệt JWT, opaque token, access token và refresh token; liên hệ cách cấp phát, claims, scope, audience, lưu trữ, thu hồi và rủi ro đánh cắp hoặc phát lại.

Sau bài này, bạn sẽ giải thích được **vì sao cần refresh token**, khi nào không nên cấp, điều gì xảy ra lúc làm mới access token, tại sao refresh token phải bảo vệ khác access token và cách một client/Authorization Server xử lý tình huống token bị thu hồi, bị lấy cắp hoặc dùng lại.

## 1. Refresh token tồn tại để giải quyết bài toán gì?

Access token là credential mà **client** gửi tới **Resource Server** để gọi tài nguyên được bảo vệ. Với bearer access token, bên nào có được giá trị token thường có thể sử dụng nó theo audience, scope và thời hạn, trừ khi có biện pháp ràng buộc người gửi. Vì thế, access token thường được thiết kế **sống tương đối ngắn** theo mức rủi ro.

Nếu không có một cơ chế duy trì ủy quyền, access token hết hạn sẽ khiến client phải yêu cầu người dùng thực hiện lại flow đăng nhập/ủy quyền, hoặc một cách xin cấp token khác phù hợp.

**Refresh token** tạo ra một cơ chế riêng:

1. Client nhận access token và **có thể** nhận refresh token sau một flow cấp quyền hợp lệ.
2. Client dùng access token để gọi Resource Server trong thời gian access token còn hiệu lực.
3. Khi cần tiếp tục truy cập, client gửi refresh token đến **token endpoint của Authorization Server**.
4. Authorization Server kiểm tra refresh token, client, ủy quyền, trạng thái thu hồi và chính sách, rồi **có thể phát hành access token mới**.
5. Nếu chính sách rotation được áp dụng, Authorization Server cũng có thể phát hành **refresh token thay thế**, khiến refresh token cũ không còn được sử dụng.

Vậy refresh token giúp **tách thời gian sống ngắn của access token khỏi thời gian client được phép duy trì quyền truy cập**. Tuy nhiên, đó là quyền có điều kiện, **không phải cam kết phiên đăng nhập tồn tại mãi mãi**.

### Ba loại token dễ bị nhầm

| Khía cạnh | Access token | Refresh token | OIDC ID token |
|---|---|---|---|
| **Mục đích** | Truy cập API/tài nguyên được bảo vệ | Xin access token mới tại Authorization Server | Truyền kết quả xác thực danh tính tới client |
| **Bên nhận** | Resource Server, theo audience được cấp | Token endpoint của Authorization Server | Client/Relying Party |
| **Ai sử dụng?** | Client gọi API | Client thực hiện refresh grant | Client xác minh đăng nhập theo OIDC |
| **Thời hạn thường gặp** | Tương đối ngắn theo chính sách | Có thể dài hơn, nhưng phải được giới hạn và thu hồi được | Theo chính sách OIDC, không dùng làm access token |
| **Định dạng** | JWT hoặc opaque | Thường là chuỗi opaque đối với client; triển khai nội bộ có thể khác | Thường là JWT |
| **Khi bị lộ** | Có thể bị dùng gọi API đến khi hết hạn/thu hồi | Có thể bị dùng để **xin tiếp access token**, làm kéo dài thiệt hại | Có thể lộ claims danh tính và tạo rủi ro trong một số ngữ cảnh |

**Không gửi refresh token trong header Bearer để gọi Resource Server.** Resource Server chỉ nên nhận loại access token đúng profile và audience của chính mình. Sự khác nhau giữa *access* và *refresh* là **chức năng bảo mật**, không phải “chuỗi nào dài hơn” hoặc “chuỗi nào nhìn giống JWT”.

## 2. Refresh token nằm ở đâu trong mô hình OAuth 2.0?

Trong OAuth 2.0 có ba chủ thể chính liên quan:

- **Authorization Server (AS):** quản lý grant, xác minh client, cấp và thu hồi token; token endpoint quyết định có cấp access token mới hay không.
- **Client:** giữ refresh token khi được cấp, gửi nó đến AS qua kênh bảo mật và cập nhật trạng thái token sau khi làm mới.
- **Resource Server (RS):** bảo vệ API, xác minh access token, audience/scope và quyền trên tài nguyên; **không cần và không nên nhận refresh token**.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as Client
    participant AS as Authorization Server
    participant RS as Orders API
    U->>C: Đăng nhập / bắt đầu flow ủy quyền
    C->>AS: Authorization Code + PKCE / flow phù hợp
    AS-->>C: Access token AT1 và có thể refresh token RT1
    C->>RS: GET /orders với AT1
    RS-->>C: 200 nếu token và quyền hợp lệ
    Note over C: AT1 hết hạn hoặc sắp hết hạn
    C->>AS: grant_type=refresh_token + RT1
    AS->>AS: Kiểm RT1, client, quyền và chính sách
    AS-->>C: Access token AT2 và có thể RT2
    C->>RS: GET /orders với AT2
    RS-->>C: Kết quả theo policy
~~~

Sơ đồ dùng **Authorization Code + PKCE** làm ví dụ phổ biến cho ứng dụng có người dùng; không có nghĩa mọi flow đều có refresh token. Việc cấp refresh token phụ thuộc loại client, quyền đã được cấp, mức bảo mật, chính sách Authorization Server và profile áp dụng.

### Không phải flow nào cũng cần refresh token

Với **Client Credentials grant**, client thường có khả năng xác thực trực tiếp với AS để xin access token mới; theo OAuth 2.0, refresh token **thông thường không nên được cấp** trong flow này. Cấp thêm một credential dài hạn có thể tăng bề mặt rủi ro mà không mang lại lợi ích tương xứng.

Với ứng dụng chỉ cần truy cập trong thời gian ngắn, việc bắt đầu lại flow ủy quyền hoặc dùng phiên bảo mật phía server có thể phù hợp hơn cấp refresh token lâu dài cho client. **Không nên phát refresh token chỉ để client có đủ hai trường access_token và refresh_token.**

Trong **OpenID Connect**, scope **offline_access** là cách client yêu cầu quyền truy cập khi người dùng không còn hiện diện trực tiếp. Tuy nhiên, yêu cầu scope này **không tự bảo đảm được cấp refresh token**: OpenID Provider vẫn áp dụng điều kiện về flow, consent và chính sách cấp quyền. **Offline access** cũng không có nghĩa refresh token được phép sống vô hạn hoặc bỏ qua cơ chế thu hồi.

## 3. Vì sao access token và refresh token phải tách riêng?

Nếu cấp một access token có thể dùng trong nhiều tháng để tránh đăng nhập lại, **một lần lộ access token** có thể tạo ra quyền truy cập API liên tục trong thời gian dài. Thiết kế tách hai token thay đổi cách quản lý rủi ro:

| Mục tiêu | Access token | Refresh token |
|---|---|---|
| **Giới hạn nơi được dùng** | Audience giới hạn Resource Server; scope giới hạn quyền cấp | Chỉ dùng ở token endpoint, ràng buộc với client/grant theo chính sách |
| **Giới hạn thời gian lộ quyền API** | Hạn dùng ngắn theo rủi ro | Không trực tiếp gọi API; muốn tiếp tục phải qua kiểm tra của AS |
| **Thu hồi quyền cấp token mới** | Có thể cần denylist/introspection hoặc đợi hết hạn | AS có thể từ chối refresh ngay khi trạng thái bị thu hồi |
| **Phát hiện dùng lại credential** | Bearer access token thường dùng nhiều lần bình thường | Rotation cho phép phát hiện refresh token cũ bị dùng lại |
| **Bảo vệ vật liệu nhạy cảm** | Tránh lộ vì được gửi tới API thường xuyên | Cần bảo vệ chặt vì có thể xin token mới trong thời gian dài |

Refresh token **không xóa bỏ** nguy cơ bị đánh cắp; nó chuyển phần lớn khả năng duy trì truy cập dài hạn về **token endpoint có kiểm tra trạng thái và chính sách**. Bởi vậy, chất lượng xác minh refresh token, bảo vệ nơi lưu và cơ chế thu hồi là điều quyết định.

Một **JWT access token tự chứa** có thể tiếp tục hợp lệ đến \`exp\` tại RS ngay cả khi refresh token đã bị thu hồi, nếu RS không có cơ chế kiểm tra trạng thái thu hồi bổ sung. Ngược lại, một **opaque access token** được introspection theo trạng thái mới có thể bị vô hiệu hóa sớm, nhưng cache introspection vẫn tạo độ trễ. Đây là sự khác nhau giữa **dừng cấp token mới** và **dừng nhận token đã cấp**.

## 4. Luồng làm mới access token từng bước

Giả sử client đã nhận được một refresh token hợp lệ sau một lần ủy quyền. Khi cần access token mới, client gửi yêu cầu \`grant_type=refresh_token\` tới token endpoint.

Ví dụ HTTP (credential chỉ là placeholder):

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<refresh-token-value>&client_id=shop-web
~~~

Ví dụ minh họa một **public client**. Với **confidential client**, token endpoint còn yêu cầu xác thực client theo phương thức đã đăng ký (ví dụ client secret trong kênh bảo mật, private_key_jwt hoặc mTLS). Giá trị \`client_id\` trong request **không tự chứng minh danh tính một public client**. Phương pháp bảo vệ refresh token phải phù hợp loại client và profile bảo mật áp dụng.

Authorization Server cần kiểm:

1. **Đúng token endpoint và grant:** request có định dạng hợp lệ; client được phép dùng refresh token grant.
2. **Credential hiện hữu:** refresh token được nhận biết, còn hiệu lực, chưa bị thu hồi, chưa vượt hạn dùng tuyệt đối hoặc giới hạn không hoạt động nếu áp dụng.
3. **Client binding:** token được cấp cho đúng client đang xin refresh; confidential client phải xác thực thành công.
4. **Trạng thái ủy quyền:** grant gốc, consent nếu cần và quyền tài khoản còn cho phép cấp token mới.
5. **Scope và audience:** không cho phép mở rộng vượt grant ban đầu và chính sách hiện hành; nếu client xin scope hẹp hơn, cấp theo điều kiện được phép.
6. **Rotation/sender-constraining:** áp dụng cơ chế ràng buộc và phát hiện reuse theo loại client và chính sách.
7. **Tính nhất quán:** cập nhật trạng thái token và tạo token mới an toàn khi có nhiều request đồng thời.

Response thành công có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<new-access-token>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders:read",
  "refresh_token": "<new-refresh-token-if-rotated>"
}
~~~

Đây là một ví dụ, **không phải mọi response đều có refresh_token mới**; khi thực hiện rotation, client phải thay refresh token cũ bằng giá trị mới. \`expires_in\` ở ví dụ là 900 giây cho access token, **không chứng minh refresh token có cùng thời hạn**.

### Thu hẹp quyền khi refresh

Giả sử grant gốc cấp \`orders:read\`, nhưng sau đó người dùng bị gỡ khỏi tenant. Authorization Server có thể từ chối refresh hoặc chỉ cấp quyền còn được phép tùy policy. **Không được dùng refresh token để xin thêm \`payments:charge\`** nếu quyền đó chưa thuộc grant và chưa được cấp hợp lệ.

Ngay cả khi AS trả access token mới với \`scope=orders:read\` và \`aud=orders-api\`, **Orders API** vẫn phải tự kiểm tra quyền đối với đơn hàng cụ thể. Refresh không biến scope thành đặc quyền truy cập mọi tài nguyên.

## 5. Refresh token rotation là gì và giúp gì?

**Refresh token rotation** là chiến lược thay refresh token sau mỗi lần refresh thành công:

1. Client giữ **RT1**.
2. Client gửi RT1 tới AS để xin access token mới.
3. AS xác minh và xử lý **RT1 hết khả năng sử dụng**, sau đó trả **AT2** và **RT2**.
4. Client lưu RT2 và ngừng dùng RT1.
5. Nếu RT1 xuất hiện lại, AS xem đây là dấu hiệu **reuse** cần xử lý theo chính sách.

~~~mermaid
flowchart TD
    A["RT1 còn hiệu lực"] --> B["Client gửi RT1 để refresh"]
    B --> C{"AS kiểm client, grant, trạng thái"}
    C -->|Không đạt| X["Từ chối"]
    C -->|Đạt| D["Atomic: RT1 không còn dùng, phát RT2 + AT2"]
    D --> E["Client lưu RT2 an toàn"]
    E --> F{"Có yêu cầu dùng lại RT1?"}
    F -->|Có| G["Phát hiện reuse, áp dụng chính sách rủi ro"]
    F -->|Không| H["Tiếp tục vòng đời hợp lệ"]
    G --> I["Có thể thu hồi token family, yêu cầu xác thực lại"]
~~~

**Rotation không khiến việc đánh cắp biến mất.** Nếu kẻ tấn công có RT1, một bên có thể refresh trước; khi bên kia sử dụng RT1 đã vô hiệu hóa, server phát hiện reuse. Hệ thống **không nhất thiết xác định được bên nào là hợp pháp chỉ từ sự kiện reuse**; thường cần coi cả chuỗi token liên quan có nguy cơ bị lộ và áp dụng chính sách như thu hồi **token family**.

Vì cùng một refresh token có thể được gửi trong hai request gần nhau do retry hoặc nhiều tab ứng dụng, hệ thống phải thiết kế rõ xử lý **concurrency, timeout và retry**. Việc thay đổi trạng thái RT1 và phát hành RT2 phải được bảo vệ nhất quán, tránh cả hai request đều được chấp nhận như lần đầu. Không tạo “grace period” cho refresh token cũ một cách tùy tiện nếu điều đó vô hiệu hóa mục tiêu phát hiện reuse.

### Một ví dụ trạng thái ở Authorization Server

| Thời điểm | Trạng thái RT1 | Trạng thái RT2 | Kết quả |
|---|---|---|---|
| Trước refresh | Active | Chưa tồn tại | Client được phép dùng RT1 |
| Sau refresh hợp lệ | Used/Invalid | Active | Client dùng RT2 từ lúc này |
| Có yêu cầu RT1 lần nữa | Used/Invalid | Có thể bị thu hồi do rủi ro | Từ chối; xử lý reuse |
| User đăng xuất/ủy quyền bị thu hồi | Invalid | Revoked | Không cấp token mới từ family bị thu hồi |

Các tên trạng thái chỉ là mô hình minh họa; cách lưu trữ và cơ chế phát hiện phụ thuộc Authorization Server. Một hệ thống cũng có thể dùng **sender-constrained refresh token** (ví dụ cơ chế chứng minh sở hữu khóa thích hợp) để giảm khả năng kẻ đánh cắp chỉ có token thô đem sử dụng.

## 6. Refresh token phải được bảo vệ như bí mật có giá trị cao

Refresh token có thể cho phép xin access token **nhiều lần** nên hậu quả lộ có thể kéo dài hơn một access token ngắn hạn. Bảo vệ ít nhất các lớp:

### 6.1. Truyền và điểm nhận

- Chỉ gửi refresh token qua **HTTPS/TLS** đến **token endpoint đúng của AS**. Không chuyển cho Resource Server, API bên thứ ba hoặc qua query string.
- Không ghi refresh token vào HTTP access log, APM/tracing, crash report, URL/history, email, ticket hỗ trợ hoặc công cụ decode token công khai.
- Token endpoint phải kiểm **client binding**; với confidential client phải xác thực client đúng phương thức.
- Chặn lạm dụng endpoint bằng giám sát, giới hạn tốc độ phù hợp và kiểm soát lỗi; không tiết lộ liệu một token tùy ý có tồn tại cho caller không được phép.

### 6.2. Lưu trữ theo loại client

| Client | Phương pháp cân nhắc | Rủi ro còn lại |
|---|---|---|
| **Backend/confidential client** | Lưu refresh token ở server, phân quyền chặt, mã hóa/secret manager khi phù hợp, tách tenant/user | Lộ server, log, backup hoặc quyền truy cập nội bộ |
| **Ứng dụng web có BFF** | BFF giữ token phía server; browser giữ session cookie với \`HttpOnly\`, \`Secure\`, \`SameSite\` phù hợp | XSS vẫn có thể gửi request; cookie cần CSRF protection theo cách sử dụng |
| **SPA/public browser client** | Giảm quyền tiếp cận token của JavaScript khi có thể; sử dụng rotation hoặc sender-constraining và chính sách ngắn hạn thích hợp | XSS hoặc script bên thứ ba có thể đọc token lưu trong JS-accessible storage |
| **Mobile/native client** | Dùng secure storage/keychain/keystore của hệ điều hành khi phù hợp, bảo vệ luồng redirect và thiết bị | Thiết bị bị chiếm quyền, backup, malware hoặc hooking |

Không có cách lưu token nào loại bỏ mọi nguy cơ. Ví dụ, **HttpOnly cookie** ngăn JavaScript đọc cookie trực tiếp nhưng không triệt tiêu tác động XSS; một script độc hại vẫn có thể gọi API trong phiên của người dùng. Nếu cookie tự động gửi lên server, cần xử lý **CSRF** và giới hạn cookie đúng domain/path.

Tại Authorization Server, opaque refresh token dạng ngẫu nhiên nên được tạo bằng **CSPRNG** và entropy đủ lớn; có thể lưu giá trị dẫn xuất một chiều để tra cứu thay cho bản rõ nếu kiến trúc cho phép. Cần bảo vệ trạng thái token, metadata, backup và quyền quản trị. **Định dạng opaque không đồng nghĩa token không cần giữ bí mật.**

## 7. Refresh token có liên quan gì đến JWT, opaque và claims?

**Access/refresh** là phân loại theo **mục đích sử dụng**; **JWT/opaque** mô tả **định dạng và cách bên nhận kiểm tra**.

| Kết hợp | Ý nghĩa và điều kiện |
|---|---|
| **JWT access token tự chứa** | Resource Server có thể xác minh chữ ký, issuer, audience, thời gian, scope tại chỗ; refresh token có thể được quản lý trạng thái riêng tại AS. |
| **Opaque access token** | Resource Server thường introspect qua AS hoặc nguồn tin cậy; trạng thái \`active\` có thể phản ánh thu hồi sớm nếu cache đủ mới. |
| **Opaque refresh token** | Client chỉ thấy một chuỗi bí mật; AS tra trạng thái, client binding, grant, expiration và revocation trước khi làm mới. |
| **Refresh token có cấu trúc nội bộ** | AS có thể dùng một định dạng khác, nhưng **client không được tự diễn giải** hoặc gửi cho API; AS vẫn phải áp dụng trạng thái thu hồi/ràng buộc. |
| **OIDC ID token** | Dùng cho client xác minh kết quả đăng nhập, không dùng làm refresh token hoặc access token tại API. |

Một payload JWT access token minh họa:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": "orders-api",
  "client_id": "shop-web",
  "scope": "orders:read",
  "iat": 1899999000,
  "exp": 1900000800,
  "jti": "sample-token-101"
}
~~~

Đây là **claims giả**, không phải JWT đã ký. Token này được dành cho **orders-api**. Khi access token hết hạn, client không được tự thay \`exp\` rồi coi token còn hợp lệ. Nó phải thực hiện **refresh grant tại AS**, nơi có quyền ra quyết định cấp token mới.

### Vì sao không nhúng refresh token vào access token?

JWT ký theo JWS thông thường **đọc được payload bằng Base64url**; chữ ký bảo vệ tính toàn vẹn chứ không mã hóa. Nếu đưa refresh token vào một claim của access token, mọi bên được chuyển access token (client, gateway, API, log) có thể thấy credential làm mới. Khi access token lộ, **refresh token cũng lộ**, phá vỡ mục tiêu tách quyền gọi API ngắn hạn khỏi credential dài hạn.

**Không nhúng refresh token trong claims của access token, ID token hoặc URL.** Giữ riêng hai loại credential và chỉ chuyển mỗi loại đến đúng bên nhận dự kiến.

## 8. Phân biệt gia hạn phiên, đăng xuất và thu hồi refresh token

Người dùng có thể nói “đăng xuất”, nhưng một hệ thống thực tế có nhiều lớp trạng thái:

1. **Phiên ứng dụng:** session cookie/BFF hoặc trạng thái đăng nhập tại client.
2. **Phiên xác thực của Authorization Server/Identity Provider:** có thể cho phép đăng nhập SSO ở ứng dụng khác.
3. **Refresh token hoặc token family:** khả năng client xin access token mới.
4. **Access token đã cấp:** credential đang được Resource Server kiểm tra.

Xóa token khỏi bộ nhớ client giúp client ngừng sử dụng chúng, **nhưng không đảm bảo bản sao refresh token đã bị đánh cắp cũng biến mất**. Khi cần chấm dứt khả năng làm mới, phải dùng cơ chế **revocation** hoặc vô hiệu hóa grant/phiên tương ứng tại AS.

**OAuth 2.0 Token Revocation (RFC 7009)** định nghĩa cách client yêu cầu thu hồi token. Ví dụ HTTP giản lược:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <encoded-client-credentials>

token=<refresh-token-value>&token_type_hint=refresh_token
~~~

\`token_type_hint\` chỉ là **gợi ý tìm loại token**, không tự chứng minh tính hợp lệ. Client authentication và quyền được revoke theo loại client/profile phải được thực thi; không để caller bất kỳ hủy credential của người khác.

Thu hồi refresh token có thể chặn xin access token tiếp theo nhưng **không mặc nhiên làm access token đã cấp hết hiệu lực ngay**. Với JWT tự chứa, RS vẫn có thể nhận token đến \`exp\` nếu không kiểm thêm trạng thái thu hồi; với opaque token/introspection có cache, độ trễ phụ thuộc TTL và invalidation.

**Đăng xuất khỏi ứng dụng, đăng xuất SSO và revoke toàn bộ token không phải lúc nào cũng là cùng một thao tác.** Thiết kế sản phẩm phải công bố rõ phạm vi đăng xuất: chỉ thiết bị hiện tại, tất cả phiên của client, hay tài khoản trên nhiều ứng dụng.

## 9. Refresh token có tự chống bị đánh cắp hoặc phát lại không?

Không. Nếu refresh token mang tính **bearer** và kẻ tấn công có nguyên chuỗi hợp lệ, họ có thể thử sử dụng nó tại token endpoint. Khác với access token, client hợp pháp thường không dùng refresh token nhiều lần liên tục theo cùng cách; vì vậy **rotation/reuse detection** có thể giúp phát hiện dấu hiệu bị sao chép.

Các cách giảm rủi ro bổ trợ:

- **Rotation + phát hiện reuse:** thay refresh token sau mỗi lần đổi, xử lý token cũ xuất hiện lại.
- **Sender-constraining:** ràng buộc refresh token với vật liệu khóa/chứng cứ mà client phải chứng minh khi sử dụng, khi hệ thống hỗ trợ.
- **Client binding và xác thực client:** refresh token chỉ được dùng theo quan hệ cấp quyền đã phát hành.
- **Expiration, inactivity timeout và revocation:** không duy trì khả năng refresh vô hạn nếu người dùng đã dừng sử dụng hoặc rút quyền.
- **Bảo vệ lưu trữ và transport:** chống lộ token qua XSS, log, storage, backup hoặc request URL.
- **Phân quyền tối thiểu:** một refresh token bị lộ không được dùng để nâng scope hoặc audience ngoài grant.

Với **public clients**, hướng dẫn bảo mật OAuth hiện đại yêu cầu cơ chế phát hiện replay phù hợp, thường bằng **refresh token rotation hoặc sender-constrained refresh tokens**. Confidential client cũng phải bảo vệ credential và đảm bảo token được gắn đúng client.

Đừng nhầm **refresh token reuse** với việc access token được dùng lại: access token bearer có thể được gửi nhiều request trong thời hạn hiệu lực; việc dùng lại access token không phải mặc nhiên bất thường. Cơ chế rotation áp dụng lên credential **làm mới**, không phải cứ mỗi request GET lại đổi access token.

## 10. Client phải phản ứng thế nào khi refresh không thành công?

Không phải mọi lỗi có thể giải quyết bằng cách thử lại liên tục. Một số nguyên nhân:

| Tình huống | Ý nghĩa | Hướng xử lý phía client |
|---|---|---|
| Access token hết hạn nhưng refresh token hợp lệ | Có thể xin token mới | Refresh một lần theo flow, sau đó gọi API với access token mới |
| Refresh token bị revoke/hết hạn/không nhận biết | AS không còn chấp nhận grant/token | Xóa credential cũ, yêu cầu xác thực/ủy quyền lại khi cần |
| Refresh token cũ bị dùng lại sau rotation | Có thể có replay hoặc lỗi đồng bộ | Không cố dùng mãi token cũ; theo quy trình tái xác thực/ứng cứu |
| Client authentication thất bại | Client hoặc credential không hợp lệ | Không bypass xác thực; kiểm cấu hình và an toàn credential |
| AS tạm lỗi mạng/5xx | Chưa biết grant có được xử lý thành công hay không | Retry có kiểm soát; tránh gửi lại token cũ bừa bãi nếu rotation đã diễn ra |
| API trả **403** vì scope/policy | Token có thể hợp lệ nhưng thiếu quyền | Không refresh vô hạn để tìm quyền rộng hơn; xử lý thiếu quyền phù hợp |

Ở token endpoint, refresh token không hợp lệ thường được báo bằng lỗi OAuth **invalid_grant** theo trường hợp áp dụng. Client không nên xem \`invalid_grant\` là tín hiệu có thể dùng refresh token khác do mình tự bịa, hoặc tiếp tục request vô hạn.

### Nhiều request đồng thời là trường hợp khó

Giả sử một SPA có ba request API cùng nhận **401 invalid_token** do access token vừa hết hạn. Nếu cả ba đồng thời gửi cùng **RT1** và AS dùng rotation, chỉ một request có thể refresh thành công; hai request còn lại có thể bị coi là reuse.

Client nên triển khai cơ chế **single-flight refresh**: các request cùng chờ **một tác vụ refresh đang diễn ra**, rồi dùng access token mới; không để mỗi request tự refresh cùng một refresh token. Với nhiều tab hoặc nhiều tiến trình, cần chiến lược đồng bộ phù hợp với nền tảng và chính sách bảo mật.

Không được mặc định retry có thể lặp vô hạn: nếu AS đã tiêu thụ RT1 và phản hồi bị mất, gửi lại RT1 có thể kích hoạt phát hiện reuse. Đây là lý do thiết kế protocol/client phải tính tới **mất phản hồi, tính nhất quán và khôi phục bằng đăng nhập lại**, không “sửa nhanh” bằng cách cho phép RT1 dùng lại không giới hạn.

### Quy trình phía client, ở mức khái niệm

~~~text
callProtectedApi():
    accessToken = currentValidAccessToken()
    response = apiRequest(accessToken)

    if response indicates expired/invalid access token:
        newToken = singleFlightRefresh()
        if refresh succeeds:
            atomicallyStoreReplacements(newToken)
            return retryOriginalRequestOnceIfSafe(newToken.accessToken)
        else:
            clearInvalidLocalCredentials()
            requireReauthorizationWhenAppropriate()
    return response
~~~

Đây là **pseudocode**, không phải thư viện triển khai trực tiếp. Cần phân biệt request có thể thử lại an toàn với request tạo side effect; không tự động gửi lại một lệnh thanh toán/hoàn tiền chỉ vì có access token mới mà không kiểm soát tính idempotent của nghiệp vụ.

## 11. Ví dụ thực tế: phiên mua sắm kéo dài, access token ngắn hạn

Giả sử hệ thống:

- **Authorization Server:** \`https://auth.example.org\`.
- **Orders API:** audience \`orders-api\`, scope \`orders:read\`.
- **Ứng dụng web:** thực hiện Authorization Code + PKCE.
- **Access token:** có hạn dùng minh họa 15 phút.
- **Refresh token:** được AS cấp **nếu client và chính sách cho phép**, có quản lý trạng thái và rotation.

Diễn biến:

| Mốc giả định | Sự kiện | Quyết định bảo mật |
|---|---|---|
| 09:00 | Người dùng xác thực và cho phép đọc đơn hàng | AS cấp AT1 và, nếu phù hợp, RT1 |
| 09:07 | Client gọi Orders API bằng AT1 | RS kiểm issuer, audience, exp, scope và quyền trên đơn hàng |
| 09:16 | AT1 đã hết hạn, client cần tiếp tục xem đơn | Client gửi RT1 cho AS; **không** gửi RT1 đến Orders API |
| 09:16 | AS xác minh RT1 và điều kiện grant | AS cấp AT2, có thể RT2 và vô hiệu hóa RT1 |
| 09:20 | Quản trị viên thu hồi phiên/refresh token | AS dừng cấp access token mới từ grant bị thu hồi |
| Sau thu hồi | AT2 còn hạn được gửi tới Orders API | RS áp dụng cơ chế revoke/introspection/TTL đã thiết kế; không suy rằng AT2 tự hết hạn tức thì |

Mốc thời gian và TTL chỉ để minh họa; không phải thông số mặc định OAuth. Client có thể chủ động refresh khi gần hết hạn thay vì chờ 401, tùy clock skew và chính sách; nhưng vẫn phải xử lý trường hợp token bị thu hồi sớm.

**Tình huống A – RT1 bị đánh cắp trước lúc refresh:** kẻ tấn công có thể cố xin token mới. Client binding, sender-constraining và rotation/reuse detection giúp giảm khả năng bị lạm dụng hoặc phát hiện bản sao.

**Tình huống B – người dùng bị gỡ quyền đọc đơn hàng:** AS cần đánh giá trạng thái grant khi refresh; RS vẫn kiểm membership/ownership hiện hành để không chấp nhận quyền cũ trên tài nguyên nhạy cảm.

**Tình huống C – client gửi RT1 trong header Authorization để gọi Orders API:** Orders API phải từ chối **sai loại token/mục đích**, kể cả token được AS tạo ra hợp lệ.

**Tình huống D – một JWT access token bị lộ nhưng refresh token vẫn được bảo vệ:** kẻ tấn công chỉ có thể dùng credential đã lộ trong thời hạn/quyền còn hiệu lực, thay vì mặc nhiên xin access token mới lâu dài. Đó là mục đích then chốt của việc tách hai credential.

## 12. Các sai lầm phổ biến

1. **Coi refresh token là access token sống lâu:** mang nó đến API hoặc gắn \`aud\`/scope như token truy cập thay vì kiểm tại token endpoint.
2. **Phát refresh token cho mọi client và mọi grant:** tạo credential dài hạn khi không thật sự cần, nhất là với client credentials.
3. **Không ràng buộc refresh token với client:** token của client A có thể bị đổi bởi client B nếu kiểm tra sai.
4. **Cho phép refresh mở rộng scope/audience:** biến credential cũ thành đường nâng quyền ngoài grant ban đầu.
5. **Lưu refresh token ở nơi JavaScript không tin cậy dễ đọc:** tăng nguy cơ XSS đánh cắp và duy trì truy cập.
6. **Ghi token nguyên văn vào log/analytics/ticket:** biến quan sát vận hành thành nguồn rò rỉ credential.
7. **Rotation nhưng không kiểm tra token đã dùng:** nhiều bản sao token cũ tiếp tục đổi được, mất khả năng phát hiện reuse.
8. **Xử lý hai lần refresh không nhất quán:** RT1 cùng lúc tạo ra nhiều RT2/RT3 hợp lệ.
9. **Thu hồi refresh token rồi khẳng định mọi access token mất hiệu lực ngay:** bỏ qua JWT tự chứa và cache introspection.
10. **Refresh vô hạn khi API trả 403:** thiếu scope/quyền không tự giải quyết bằng việc cấp lại access token.
11. **Không có chính sách hết hạn/tắt phiên:** refresh token tiếp tục dùng được dù người dùng rút quyền hoặc không hoạt động lâu.
12. **Nhầm OIDC ID token với token để gọi API:** ID token chứng minh kết quả xác thực với client; không làm credential Resource Server.

## 13. Ma trận kiểm thử vòng đời refresh token

| Trường hợp kiểm thử | Kết quả mong đợi |
|---|---|
| Client hợp lệ dùng refresh token còn hiệu lực, grant còn cho phép | Cấp access token mới trong quyền được phép |
| Client gửi refresh token của client khác | **Từ chối** |
| Refresh token bị revoke hoặc hết hạn | **Từ chối** |
| Xin scope rộng hơn grant ban đầu | **Từ chối/không cấp quyền vượt grant**, theo policy |
| Xin token cho audience chưa được phê duyệt | **Từ chối** |
| Client không được phép refresh grant | **Từ chối** |
| Confidential client không xác thực được | **Từ chối** |
| RT1 đã rotation nhưng lại được dùng | **Từ chối**, kích hoạt xử lý reuse theo policy |
| Hai request dùng RT1 đồng thời | Không phát nhiều nhánh token hợp lệ trái policy; kiểm soát atomic |
| Response refresh bị mất và client retry RT1 | Không phát RT mới trái policy; client xử lý phục hồi an toàn |
| Sau thu hồi RT, access token JWT cũ còn hạn | Hành vi RS phải khớp chính sách revoke/TTL đã công bố |
| Client cố dùng refresh token làm Bearer tại Orders API | **Từ chối sai loại token** |
| User bị gỡ khỏi tenant nhưng vẫn có RT | AS không cấp quyền vượt trạng thái còn hiệu lực; RS từ chối truy cập trái policy |
| Introspection hoặc AS tạm không hoạt động | **Không fail open**, thông báo lỗi phù hợp |

Đối với security tests, cần kiểm cả **không có token mới được cấp** trong các trường hợp thất bại, không chỉ mã HTTP; đồng thời kiểm việc lưu token an toàn và không có bearer token thật trong log. Các test dùng credential giả và môi trường được phép.

## 14. Checklist khi thiết kế chính sách refresh token

1. **Có thật sự cần refresh token không?** Không cấp chỉ vì ứng dụng có thể lưu nó.
2. **Client nào được cấp?** Public hay confidential, grant type nào, cách nhận diện/xác thực client?
3. **Grant nào được duy trì?** User/service, consent và quyền hiện hành được kiểm lại ra sao?
4. **Bảo vệ replay thế nào?** Rotation, phát hiện reuse hoặc sender-constraining nào phù hợp?
5. **Giới hạn scope/audience ra sao?** Refresh không được nâng quyền ngoài grant gốc/chính sách hiện hành.
6. **Thời hạn nào được áp dụng?** Absolute TTL, inactivity timeout, trạng thái revoke và giới hạn phiên?
7. **Lưu trữ và truyền ra sao?** Secure storage, HTTPS, không xuất token trong URL/log/backup thiếu bảo vệ?
8. **Khi đổi token có đồng thời không?** AS cập nhật state atomic; client single-flight refresh?
9. **Lỗi xử lý thế nào?** \`invalid_grant\`, mạng lỗi, response mất, 401/403 tại API, vòng lặp retry?
10. **Đăng xuất làm gì?** Xóa credential local, revoke refresh token/phiên theo chính sách, phân biệt access token cũ?
11. **Resource Server có hiểu ranh giới không?** Chỉ nhận access token, kiểm issuer, audience, scope và quyền đối tượng?
12. **Có khả năng ứng cứu không?** Thu hồi token family, theo dõi reuse, buộc xác thực lại khi lộ token?

## 15. Câu hỏi tự đánh giá

**1. Mục đích chính của refresh token là gì?** Cho phép client xin access token mới từ Authorization Server mà không phải lặp lại toàn bộ bước xác thực/ủy quyền của người dùng mỗi khi access token ngắn hạn hết hạn, **khi grant vẫn còn được phép**.

**2. Client có nên gửi refresh token tới Orders API không?** Không. Refresh token dùng tại token endpoint của Authorization Server, không phải credential truy cập Resource Server.

**3. Refresh token có luôn được cấp cùng access token không?** Không. Điều này phụ thuộc flow, loại client và chính sách. Client Credentials thường không cần refresh token.

**4. Vì sao refresh token cần bảo vệ chặt hơn access token ngắn hạn?** Vì một refresh token bị lộ có thể được dùng để xin nhiều access token mới trong thời gian dài hơn, nếu không bị ràng buộc/thu hồi.

**5. Rotation có thể giúp phát hiện điều gì?** Việc refresh token đã được dùng và vô hiệu hóa xuất hiện lại. Đây có thể là dấu hiệu sao chép token hoặc lỗi đồng bộ; cần áp dụng chính sách xử lý an toàn.

**6. Thu hồi refresh token có lập tức vô hiệu hóa mọi JWT access token cũ không?** Không mặc định. Access token đã cấp có thể còn hiệu lực tại Resource Server cho đến \`exp\` nếu không có cơ chế revoke bổ sung.

**7. Có thể dùng refresh token để đổi lấy scope lớn hơn hoặc token cho một API bất kỳ không?** Không. AS phải giới hạn scope/resource theo grant và chính sách còn hiệu lực.

**8. Nếu 3 request API cùng phát hiện access token hết hạn, client nên làm gì?** Nên đồng bộ để thực hiện **một tác vụ refresh**, tránh đồng thời dùng lại cùng refresh token đã rotation.

**9. Nếu refresh token bị từ chối do hết hạn/thu hồi thì client cần làm gì?** Ngừng dùng credential đó, xóa trạng thái không hợp lệ và khởi động lại bước xác thực/ủy quyền phù hợp, thay vì retry vô hạn.

**Ghi nhớ:** **Refresh token là cầu nối có kiểm soát giữa một access token ngắn hạn và khả năng duy trì ủy quyền lâu hơn.** Nó chỉ được dùng với Authorization Server, không trực tiếp mở quyền API. Bảo mật refresh token phụ thuộc vào **client binding, scope/audience không được nâng quyền, giới hạn thời gian, lưu trữ an toàn, rotation hoặc sender-constraining, phát hiện replay và thu hồi**. Khi AS cấp access token mới, Resource Server vẫn phải xác minh token và quyền với tài nguyên cụ thể.
