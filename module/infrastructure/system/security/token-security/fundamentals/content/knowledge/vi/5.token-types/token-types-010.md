# API key khác token xác thực như thế nào?

## 1. Câu hỏi cốt lõi: hai loại credential giải quyết điều gì?

Trong chương **Token types** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, chúng ta cần phân biệt **API key** với những credential thường được gọi là **token xác thực**, đặc biệt là **OAuth 2.0 access token**, **OpenID Connect (OIDC) ID token** và **refresh token**. Cả API key lẫn token đều có thể xuất hiện trong request tới API, nhưng **chúng thường thể hiện các quan hệ tin cậy và vòng đời khác nhau**.

Giả sử một hệ thống có hai tình huống:

- **Dịch vụ đồng bộ dữ liệu** gọi API của nhà cung cấp để lấy số liệu hằng đêm. Nhà cung cấp cấp một API key gắn với dự án `project-analytics`. Key cho biết request được phép dùng dịch vụ trong phạm vi dự án và hạn mức đã đăng ký.
- **Người dùng Alice** đăng nhập vào ứng dụng quản lý đơn hàng. Ứng dụng lấy access token được Authorization Server cấp theo một luồng OAuth 2.0, rồi gửi token tới Orders API để đọc đơn hàng Alice được phép xem.

Cả hai request đều cần được xác thực. Tuy nhiên, ở tình huống thứ nhất, nhà cung cấp thường cần nhận diện **ứng dụng, tài khoản kỹ thuật hoặc dự án sở hữu key**. Ở tình huống thứ hai, Orders API còn cần biết **token được cấp cho client nào, theo quyền của subject/actor nào, cho resource server nào, với scope gì**.

**Điểm quan trọng:** trong nghĩa rộng, API key cũng là **một loại secret/credential dùng để xác thực lời gọi API** và đôi khi được gọi là token. Vì vậy, "API key" và "token xác thực" **không phải hai tập hợp tách biệt tuyệt đối**. Cách phân biệt có ích nhất là theo **mục đích, chủ thể, giao thức cấp phát, đặc tính bảo mật và cách API kiểm tra quyền**.

Sau bài này, bạn nên có khả năng:

1. Giải thích một API key xác định ai và một access token OAuth 2.0 đại diện cho ai/điều gì.
2. Phân biệt API key với access token, ID token và refresh token; phân biệt **mục đích token** với **định dạng JWT/opaque**.
3. Chọn cơ chế phù hợp cho máy chủ gọi máy chủ, ứng dụng có người dùng, frontend công khai và các tác vụ tự động.
4. Thiết kế lưu trữ, phát hành, kiểm tra quyền, thu hồi, rotation và giám sát đối với từng credential.
5. Nhận diện lỗi phổ biến như đưa API key vào frontend, bỏ qua audience, dùng ID token để gọi API hoặc coi API key là quyền truy cập mọi dữ liệu của một tenant.

## 2. API key là gì?

**API key** thường là một chuỗi bí mật được dịch vụ/API provider cấp và liên kết với một bản ghi phía nhà cung cấp. Khi client gửi key, provider dùng nó để **nhận diện và xác thực caller theo chính sách của sản phẩm**, rồi quyết định client được dùng endpoint, tính năng, dự án, hạn mức hoặc dữ liệu nào.

Ví dụ minh họa:

~~~http
GET /v1/weather/current?city=Hanoi HTTP/1.1
Host: data.example.com
X-API-Key: <API_KEY>
~~~

`X-API-Key` ở đây là **một cách truyền key theo hợp đồng của API ví dụ**; tên header không phải chuẩn bắt buộc cho mọi nhà cung cấp. Một API khác có thể dùng `Authorization: ApiKey ...` hoặc cơ chế khác. Không tự giả định mọi API hỗ trợ cùng cách truyền.

Trong một thiết kế thường gặp, provider lưu thông tin như:

~~~json
{
  "key_id": "ak_41b7",
  "project_id": "project-analytics",
  "principal_type": "application",
  "allowed_actions": ["weather:read"],
  "allowed_resources": ["weather-public"],
  "expires_at": "2027-02-01T00:00:00Z",
  "revoked": false
}
~~~

Đây là **bản ghi metadata minh họa**, **không phải nội dung API key** và không phải schema tiêu chuẩn. Giá trị secret thực phải được bảo vệ riêng, không lưu hoặc ghi log cùng metadata ở dạng nguyên văn. Chính sách thực tế có thể có giới hạn tenant, IP, môi trường, quota, người quản lý key và thời điểm sử dụng gần nhất.

### 2.1. API key thường xác định client, dự án hoặc tài khoản kỹ thuật

Nhà cung cấp có thể trả lời: "Request này mang key được cấp cho dự án `project-analytics` và được phép đọc dữ liệu thời tiết." Nhưng từ đó **không thể tự suy ra một người dùng cuối đã đăng nhập**.

Một số API provider cấp key **cho từng người dùng**, gắn key với **service account**, hoặc thiết kế **API key có scope và thời hạn ngắn**. Do đó, không có quy luật tuyệt đối rằng "API key luôn gắn với ứng dụng, không bao giờ gắn với người dùng". Điều đúng là **ý nghĩa của key do provider và hợp đồng API quyết định**.

### 2.2. API key thường mang tính bearer

Nếu chỉ cần biết chuỗi secret là gọi được API, key có tính chất **bearer credential**: ai chiếm hữu nó có thể sử dụng quyền đã được cấp cho key trong giới hạn còn hiệu lực.

Điều đó tạo ra rủi ro:

- Key lộ trong repository, log, URL, ảnh chụp màn hình hoặc cấu hình frontend.
- Bên lấy được key dùng lại từ một thiết bị khác.
- Một key dùng chung cho nhiều ứng dụng khiến khó xác định nguồn lạm dụng.
- Key được cấp quyền rộng, không hết hạn hoặc không được rotation.

Một số hệ thống bổ sung **mTLS, IP allowlist, ràng buộc workload hoặc xác thực request có chữ ký**. Những kiểm soát đó có thể hạn chế việc dùng key bị lộ, nhưng **không phải đặc tính mặc định của mọi API key**.

## 3. OAuth 2.0 access token là gì?

**Access token** là credential client dùng để truy cập **resource server** theo quyền được Authorization Server cấp trong một luồng OAuth 2.0. Resource server xác minh token và áp dụng chính sách để quyết định request được phép hay không.

Ví dụ:

~~~http
GET /api/orders/order-721 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <ACCESS_TOKEN>
~~~

Với access token theo dạng JWT, payload có thể giống:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "alice-123",
  "aud": "https://orders.example.com",
  "client_id": "shop-web",
  "scope": "orders:read",
  "iat": 1790000000,
  "nbf": 1790000000,
  "exp": 1790000900,
  "jti": "at-2871"
}
~~~

Đây là **JSON minh họa đã giải mã**, chưa có header/chữ ký JWT hoàn chỉnh và không dùng làm token thật. Trường cụ thể phụ thuộc profile/token contract của issuer; không phải mọi access token đều chứa tất cả các claim trên.

| Claim | Ý nghĩa trong ví dụ | Resource server cần làm gì? |
|---|---|---|
| `iss` | Issuer đã phát hành token | Chỉ chấp nhận issuer đã được cấu hình tin cậy |
| `sub` | Subject/principal mà token mô tả | Hiểu trong phạm vi issuer và loại grant; không tự suy ra quyền mọi đơn hàng |
| `aud` | Orders API là bên nhận dự kiến | So khớp audience với API hiện tại |
| `client_id` | Client nhận token là `shop-web` | Diễn giải theo profile; không đồng nhất với subject |
| `scope` | Token được cấp phạm vi `orders:read` | Kiểm tra action và quyền trên từng đơn hàng |
| `iat`, `nbf`, `exp` | Thời điểm phát hành, hiệu lực, hết hạn | Kiểm tra giới hạn thời gian |
| `jti` | Định danh token khi issuer cung cấp | Có thể hỗ trợ audit/chặn token, không tự ngăn replay |

**Access token không nhất thiết là JWT.** Một Authorization Server có thể cấp **opaque access token**, là chuỗi mà resource server không cần giải mã để lấy claims. Resource server khi đó thường dùng **token introspection** hoặc cơ chế kiểm tra trạng thái đáng tin cậy theo hợp đồng.

### 3.1. OAuth 2.0 có thể đại diện người dùng hoặc ứng dụng

OAuth 2.0 không giới hạn ở đăng nhập người dùng. Hai trường hợp phổ biến:

- **Authorization Code + PKCE:** client có thể xin quyền thay mặt người dùng sau quá trình xác thực/ủy quyền. Access token cho phép client gọi API trong phạm vi được cấp.
- **Client Credentials:** backend/service xin access token theo quyền của **chính client** cho tác vụ máy chủ gọi máy chủ. Không bắt buộc có người dùng cuối hay consent tại thời điểm request.

Vì vậy, so sánh "API key là máy với máy còn OAuth token luôn là người dùng" là **sai**. OAuth access token cũng thường được sử dụng cho machine-to-machine, nhưng có giao thức phát hành và cơ chế xác minh/giới hạn quyền khác tùy triển khai.

## 4. So sánh trực tiếp API key và các loại token

| Khía cạnh | API key thông dụng | OAuth 2.0 access token | OIDC ID token | OAuth 2.0 refresh token |
|---|---|---|---|---|
| **Mục đích chính** | Xác định/xác thực caller của một API, quản lý quyền dùng dịch vụ | Gọi resource server trong phạm vi được cấp | Client xác minh thông tin đăng nhập người dùng | Client xin access token mới tại token endpoint |
| **Ai cấp?** | API provider, hệ thống quản lý key | Authorization Server | OpenID Provider | Authorization Server |
| **Ai dùng/nhận?** | Client gửi tới API theo hợp đồng | Client gửi tới resource server | Client nhận và kiểm tra | Client gửi tới Authorization Server |
| **Chủ thể hay gặp** | Project, app, account kỹ thuật, đôi khi người dùng | Người dùng hoặc client/service principal tùy grant | Người dùng được xác thực | Gắn với grant/client và chính sách phiên |
| **Biểu diễn** | Thường là secret opaque | JWT hoặc opaque | JWT theo OIDC | Thường là chuỗi opaque, không bắt buộc |
| **Thời hạn** | Do provider quy định; có thể dài hoặc ngắn | Thường được cấu hình thời hạn tương đối ngắn | Hạn dùng để xác minh authentication event | Vòng đời thường dài hơn access token, phụ thuộc chính sách |
| **Scope/audience** | Có thể có giới hạn riêng, không có cấu trúc OAuth bắt buộc | Scope, audience/resource và policy của issuer/resource server | Audience hướng tới client; không dùng làm API access token | Gắn với grant/quyền được cấp; không gửi cho resource server |
| **Xác minh** | Tra metadata/secret/key hash hoặc cơ chế provider | JWT validation hoặc opaque introspection | OIDC ID token validation ở client | Token endpoint xác minh theo chính sách grant/client |
| **Thu hồi/rotation** | Provider quản lý key, có thể hỗ trợ revoke/rotate | Token lifetime, revocation, introspection/chặn token tùy thiết kế | Hết hạn; quản lý phiên theo quy tắc OIDC | Revoke, rotate, phát hiện reuse khi triển khai |

**Bảng mô tả các mẫu thường gặp, không phải giới hạn tuyệt đối.** Provider có thể triển khai key theo từng user, key có scopes và expiry, hoặc cơ chế ngắn hạn giống token. Cũng có hệ thống dùng một giá trị được gọi là "API token" nhưng về mặt chức năng thực chất là API key dài hạn. **Tên gọi do sản phẩm đặt không đủ xác định mô hình bảo mật**.

### 4.1. Hai trục phân loại không được trộn

**Trục 1 — mục đích/quy trình cấp quyền**

- API key: credential có ngữ nghĩa do API provider tự định nghĩa.
- OAuth access token: credential cho resource server theo quyền và chính sách OAuth.
- OIDC ID token: thông tin kết quả xác thực cho client.
- Refresh token: credential làm mới quyền truy cập tại Authorization Server.

**Trục 2 — định dạng và cách kiểm tra**

- **JWT:** có cấu trúc header.payload.signature (đối với JWT được ký), bên nhận xác minh chữ ký, issuer, audience và claims; JWT được ký **không tự mã hóa** payload.
- **Opaque:** chuỗi không yêu cầu bên nhận hiểu cấu trúc; cần tra cứu/kiểm tra bằng nguồn tin cậy nếu phải biết trạng thái/quyền.

Một OAuth access token có thể là JWT hoặc opaque. Một API key thông thường là chuỗi opaque. Không được kết luận "API key là opaque, token là JWT" hay "JWT luôn là access token".

## 5. Hai luồng gọi API để thấy rõ sự khác biệt

### 5.1. Dịch vụ backend sử dụng API key

Giả sử một công ty có job `analytics-worker` gọi API dữ liệu:

~~~mermaid
sequenceDiagram
    participant W as analytics-worker
    participant V as Secret store
    participant API as Provider API
    participant K as API key registry
    W->>V: Lấy API key theo identity của workload
    V-->>W: Secret được bảo vệ
    W->>API: GET /v1/metrics + X-API-Key
    API->>K: Tra key/secret, trạng thái, project, phạm vi
    K-->>API: Project-analytics, metrics:read, active
    API->>API: Kiểm tra policy, quota và resource
    API-->>W: Dữ liệu được phép hoặc lỗi
~~~

Giả định key nằm trong kho bí mật của backend. Provider xác thực key, xác định dự án và quyền. Nếu key bị đưa vào ứng dụng JavaScript trong trình duyệt, người dùng cuối có thể đọc key và gọi API với quyền của toàn dự án.

### 5.2. Người dùng đăng nhập và client sử dụng access token

~~~mermaid
sequenceDiagram
    actor U as Alice
    participant C as Client: shop-web
    participant AS as Authorization Server / OIDC Provider
    participant RS as Orders API
    U->>C: Yêu cầu xem đơn hàng
    C->>AS: Authorization Code + PKCE
    AS->>U: Xác thực và xử lý consent/policy khi cần
    AS-->>C: Authorization code qua redirect URI hợp lệ
    C->>AS: Đổi code kèm code_verifier
    AS-->>C: Access token (ID/refresh token nếu được cấp)
    C->>RS: GET /orders/order-721 + Bearer access token
    RS->>RS: Xác minh issuer, aud, expiry, scope
    RS->>RS: Kiểm tra Alice được đọc order-721
    RS-->>C: Đơn hàng hoặc 403/404 theo policy
~~~

**Một khác biệt kiến trúc:** trong OAuth, Authorization Server là thành phần chuyên cấp token; Orders API là resource server chấp nhận token cho đúng audience và đánh giá quyền tài nguyên. Với API key, cùng provider thường cấp key, kiểm tra key và áp quota thông qua cơ sở dữ liệu quản lý key; không có quy tắc buộc phải có authorization server OAuth riêng.

### 5.3. Machine-to-machine không có người dùng

Nếu `analytics-worker` gọi API nội bộ có OAuth 2.0, nó có thể dùng **Client Credentials Grant**:

~~~text
analytics-worker --(client authentication + grant_type=client_credentials)-->
Authorization Server
    --(access token có aud=metrics-api, scope=metrics:read)-->
analytics-worker
    --(Bearer access token)-->
Metrics API
~~~

Điều này giúp dùng access token có audience/scope/expiry được cấp cho API đích. **Client secret** hoặc private key để xác thực client tại token endpoint là credential dùng để **xin access token**; nó không được nhầm với **access token** gửi đến resource server.

## 6. API key có phải là bằng chứng một người dùng đã đăng nhập?

**Thông thường là không.** Một API key gắn với công ty hoặc dự án chứng minh request biết một credential của dự án; nó không cho biết người dùng cuối nào đã thực hiện thao tác.

Ví dụ, backend dùng API key có quyền `invoices:read` gọi Billing API để tạo báo cáo cho Alice. Alice có quyền xem hóa đơn `A-100` nhưng không có quyền xem `B-900`. Nếu backend dùng key quyền rộng để lấy `B-900` vì Alice nhập ID đó, backend có thể trở thành **confused deputy**: dịch vụ có đặc quyền bị điều khiển để thực hiện yêu cầu ngoài quyền người dùng.

API key và access token **đều không thay thế authorization trên resource cụ thể**. Ngay cả JWT access token có `scope=invoices:read`, `sub=alice` cũng không đủ để cho phép đọc mọi hóa đơn.

Một mô hình phân quyền phù hợp:

~~~text
ALLOW = credential hợp lệ cho API hiện tại
    AND action được credential/policy cho phép
    AND caller/delegation hợp lệ cho hành động này
    AND principal có quyền trên resource cụ thể
    AND tenant, trạng thái và giới hạn nghiệp vụ được thỏa mãn
~~~

Nếu API cho phép cả API key lẫn access token, việc chuẩn hóa chúng thành một đối tượng principal nội bộ cần giữ nguyên **credential type, client/project, issuer hoặc nguồn xác thực, loại principal, scopes và provenance**. Không được tự gán một API key ứng dụng thành một `sub` người dùng hay tin header `X-User-Id` do caller tự gửi.

## 7. Cấp phát, lưu trữ và truyền credential

### 7.1. Quy trình cấp API key an toàn

1. **Xác định chủ sở hữu và mục đích:** mỗi ứng dụng, môi trường và workload nên có identity/key riêng khi khả thi; gắn key với account/project/tenant cụ thể.
2. **Sinh secret đủ ngẫu nhiên:** dùng bộ sinh ngẫu nhiên mật mã (CSPRNG), key có entropy cao và khó đoán; không dùng email, timestamp hoặc ID tuần tự làm secret.
3. **Chỉ hiển thị key hoàn chỉnh khi tạo nếu chính sách cho phép:** người quản trị lưu vào secret manager; sau đó UI chỉ hiển thị prefix/suffix để nhận diện, không hiển thị secret lại.
4. **Lưu metadata và verifier phù hợp:** với key ngẫu nhiên đủ entropy, provider có thể lưu hash/HMAC tra cứu an toàn và tách phần secret khỏi dữ liệu hiển thị. Bảo vệ key dùng để HMAC trong KMS/secret manager khi thiết kế áp dụng.
5. **Giới hạn quyền mặc định:** scope/action, project, resource, tenant, hạn dùng, quota; tránh key "mọi quyền" cho tích hợp đơn giản.
6. **Chuẩn bị rotation và revocation:** key mới có thể dùng song song ngắn hạn với key cũ để chuyển đổi không gián đoạn; sau đó thu hồi key cũ.
7. **Audit:** lưu người tạo, ứng dụng được cấp, thời điểm dùng và các thay đổi quyền, nhưng không ghi lại secret thô.

Nếu cần kiểm tra key trong cơ sở dữ liệu, nên dùng một **key ID/prefix không bí mật** để tìm bản ghi, rồi kiểm tra verifier của secret bằng cách so sánh an toàn. Với key có entropy đủ cao, hash mật mã/HMAC có thể phù hợp; không nên bê nguyên cách lưu mật khẩu người dùng hoặc mã hóa hai chiều không cần thiết mà không xét threat model.

### 7.2. Nơi nào được giữ API key?

| Nơi sử dụng | Khuyến nghị |
|---|---|
| **Backend server / worker** | Secret manager hoặc cơ chế secrets của hạ tầng, quyền đọc tối thiểu theo workload |
| **CI/CD** | Secret store của pipeline, giới hạn môi trường và quyền; không in ra log build |
| **Mobile app hoặc SPA JavaScript** | Không nhúng **API key bí mật có quyền cao** vào bundle hoặc app phát cho người dùng vì có thể bị trích xuất |
| **Repository/config mẫu** | Chỉ dùng placeholder, không commit key thật |
| **Log, telemetry, exception, URL** | Che hoặc loại bỏ key thô, đặc biệt trong query string và header được log |

Nếu một dịch vụ dùng key **công khai** để nhận diện project và áp quota đơn giản (ví dụ các hệ thống thiết kế riêng cho client công khai), key đó cần được xem là **public identifier**, không phải secret xác thực mạnh. Provider phải dựa vào giới hạn bổ sung và không cấp quyền nhạy cảm chỉ từ việc biết giá trị công khai.

### 7.3. Nơi giữ OAuth token

- **Access token:** cấp đúng audience, giới hạn scope/thời gian sống; truyền qua HTTPS. Nơi lưu trữ tùy kiến trúc client; frontend có rủi ro XSS, backend/BFF có thể giảm phạm vi lộ credential nếu thiết kế session/cookie đúng.
- **Refresh token:** nhạy cảm vì có thể xin access token mới; cấp theo chính sách, bảo vệ lưu trữ, giới hạn vòng đời, sử dụng rotation/phát hiện reuse khi thích hợp. Không gửi refresh token tới resource server.
- **ID token:** client kiểm tra theo OIDC (issuer, audience, expiry, nonce và các điều kiện liên quan); không dùng để gọi API nghiệp vụ.
- **Client credential tại token endpoint:** client secret hoặc khóa riêng phải được giữ ở bên thực sự bảo vệ được bí mật; public client dùng flow phù hợp như Authorization Code + PKCE thay vì nhúng client secret.

**Cùng một nguyên tắc bảo vệ secret áp dụng cho cả API key và bearer access token:** không đặt vào URL, không ghi nguyên văn vào log, không gửi qua HTTP không mã hóa, không dùng cho đối tượng nhận ngoài phạm vi cấp phép.

## 8. API xác minh credential như thế nào?

### 8.1. Xác minh API key

Một request API key có thể được kiểm tra theo trình tự:

1. Chỉ cho phép key ở vị trí/giao thức đã công bố, ví dụ header `X-API-Key`; loại bỏ giá trị mơ hồ như nhiều key trong một request.
2. Tìm key record bằng ID/prefix rồi xác minh secret với verifier được bảo vệ.
3. Kiểm tra key còn active, chưa hết hạn/thu hồi, đúng môi trường và chủ sở hữu đã cấu hình.
4. Xác định principal dạng ứng dụng/project/tenant và phạm vi quyền được cấp.
5. Đánh giá **action và resource** thực tế, sau đó áp quota/rate limit riêng.
6. Ghi audit metadata an toàn; không log secret.

**API key không có chuẩn JWT `iss/aud/exp` bắt buộc.** Provider phải thiết kế các ràng buộc tương đương khi cần, chẳng hạn danh tính project, môi trường, tập endpoint, tenant và hạn dùng. Việc so khớp key với một bản ghi không có nghĩa mọi tài nguyên API đều được phép.

### 8.2. Xác minh OAuth access token

Đối với **JWT access token**, resource server cần:

1. Giới hạn thuật toán ký được chấp nhận; xác minh chữ ký bằng khóa của issuer đáng tin cậy.
2. So khớp `iss` với issuer được cấu hình; không tin địa chỉ lấy khóa do token chưa xác minh tự chỉ định.
3. Kiểm tra `aud` chứa resource server hiện tại, đúng loại token/profile được chấp nhận.
4. Kiểm tra `exp`, `nbf` và các điều kiện thời gian có áp dụng; xử lý clock skew ở mức kiểm soát.
5. Kiểm tra scope/action, loại principal, tenant và policy trên resource.
6. Xử lý trạng thái thu hồi/chặn token khi thiết kế có yêu cầu hiệu lực tức thời.

Đối với **opaque access token**, resource server có thể gọi introspection endpoint đáng tin cậy, kiểm tra `active`, client, audience, scope, expiry và dữ liệu được issuer trả theo contract. `active=true` chỉ cho biết trạng thái token theo định nghĩa của issuer, **chưa tự cấp quyền mọi resource**.

### 8.3. Vì sao hai đường xác minh không được nhầm lẫn?

Giả sử API nhận cả:

~~~http
X-API-Key: <APPLICATION_KEY>
~~~

và:

~~~http
Authorization: Bearer <OAUTH_ACCESS_TOKEN>
~~~

Nếu service lấy chuỗi bất kỳ rồi thử xác minh như JWT, thất bại thì tự động đối chiếu như API key, có thể hình thành **credential confusion/downgrade**: request dùng loại credential ít ràng buộc hơn để vượt qua kiểm tra dành cho loại token nhạy cảm.

Thiết kế an toàn nên:

- Cấu hình **loại credential được chấp nhận ở từng endpoint**.
- Nếu hỗ trợ cả hai, tách rõ cơ chế xác thực và cách xây dựng principal, tránh fallback mơ hồ.
- Từ chối khi caller gửi đồng thời nhiều credential trái quy tắc.
- Ánh xạ scopes/roles riêng theo nguồn xác thực; không tự cấp quyền người dùng cho application key.
- Áp policy resource/action độc lập với việc credential được gửi ở header nào.

## 9. Triển khai minh họa bằng Java/Spring

Các đoạn sau là **pseudocode** để thể hiện ranh giới trách nhiệm; `ApiKeyRegistry`, `VerifiedCaller`, `PermissionPolicy` là thành phần tự xây của ứng dụng, không phải API mặc định của Spring Security.

### 9.1. Kiểm tra API key để lấy principal ứng dụng

~~~java
VerifiedCaller authenticateApiKey(String presentedKey) {
    if (presentedKey == null || presentedKey.isBlank()) {
        throw new UnauthenticatedException();
    }

    ApiKeyRecord record = apiKeyRegistry.findAndVerify(presentedKey);
    if (record == null || record.isRevoked() || record.isExpired()) {
        throw new UnauthenticatedException();
    }

    return VerifiedCaller.application(
        record.projectId(),
        record.tenantId(),
        record.allowedActions()
    );
}
~~~

Hàm `findAndVerify` phải thực hiện kiểm tra secret an toàn với nguồn metadata tin cậy, không lưu/so sánh secret trong code và không ghi log key. Một bản triển khai production còn phải xét giới hạn cấu hình, request validation, chống brute force và cách từ chối nhất quán.

### 9.2. Xác thực JWT access token bằng resource server

Trong Spring Security, cấu hình **OAuth2 Resource Server** có thể tự xác minh JWT hoặc introspect opaque token tùy cấu hình. Khi dùng JWT, phải bảo đảm **audience validator** của API được cấu hình theo yêu cầu; không giả định chỉ đặt issuer là tự động kiểm tra mọi audience nghiệp vụ.

~~~java
// Pseudocode controller: các điều kiện token đã được tầng security kiểm tra.
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
@GetMapping("/api/orders/{orderId}")
public OrderDto readOrder(
        @PathVariable String orderId,
        Authentication authentication) {

    VerifiedCaller caller =
        principalFactory.fromVerifiedAuthentication(authentication);

    return orderService.readAuthorizedOrder(caller, orderId);
}
~~~

Với bearer access token, `SCOPE_orders:read` là authority thường được ánh xạ từ claim scope nhưng phụ thuộc cấu hình. Một annotation kiểm tra scope ở endpoint **chưa thay thế** kiểm tra Alice có quyền đọc `orderId` cụ thể.

### 9.3. Dù là loại credential nào, vẫn phải xét action/resource

~~~java
OrderDto readAuthorizedOrder(VerifiedCaller caller, String orderId) {
    Order order = orderRepository.findById(orderId)
        .orElseThrow(NotFoundException::new);

    boolean allowed = permissionPolicy.canPerform(
        caller,
        "order:read",
        order
    );
    if (!allowed) {
        throw new ForbiddenException();
    }

    return orderMapper.toDto(order);
}
~~~

`permissionPolicy` phải xét **loại principal, tenant, owner, scopes, quan hệ và chính sách** của resource. Nếu caller là API key của tác vụ đồng bộ, policy có thể cho đọc dữ liệu của dự án được cấp quyền; nếu caller là user access token, policy phải xét quyền người dùng. Không được suy rằng key `metrics:read` tương đương quyền cá nhân `orders:read`.

## 10. Vòng đời: phát hành, rotation, hết hạn và thu hồi

| Giai đoạn | API key | OAuth access token | Refresh token |
|---|---|---|---|
| **Phát hành** | Provider tạo secret/metadata sau khi xác định owner, ứng dụng và quyền | Authorization Server cấp qua luồng/grant và policy thích hợp | Authorization Server cấp khi chính sách cho phép |
| **Lưu trữ** | Client giữ trong secret manager hoặc kho bảo vệ phù hợp | Client giữ theo kiến trúc và thời gian sống; giảm tiếp xúc frontend | Bảo vệ nghiêm ngặt, thường cần rotation/reuse detection theo chính sách |
| **Kiểm tra** | Provider xác minh key record/secret và policy | Resource server xác minh JWT hoặc introspection, audience/scope/resource | Token endpoint xác minh để cấp credential mới |
| **Giới hạn thời gian** | Provider định nghĩa; có thể thiếu expiry nếu thiết kế kém | Thường có thời hạn xác định; cần thiết kế cả phương án thu hồi | Có lifetime/idle lifetime/absolute lifetime tùy chính sách |
| **Rotation** | Cấp key mới, chuyển client, thu hồi key cũ | Client lấy token mới qua flow được phép | Có thể rotation mỗi lần dùng theo policy |
| **Thu hồi** | Key registry vô hiệu key, xét cache xác minh | Offline JWT có thể tiếp tục đến hạn nếu không thêm cơ chế trạng thái; opaque introspection có thể phản ánh thu hồi sớm hơn | Revoke để ngăn xin access token mới; không tự xóa mọi access token còn hạn |

### 10.1. Quy trình rotation API key không gián đoạn

Ví dụ `analytics-worker` đang dùng key `K-old`:

1. Tạo **key mới `K-new`** đúng scope, môi trường và project.
2. Đưa key mới vào secret manager, cập nhật workload để dùng key mới.
3. Kiểm tra log metadata cho thấy request đã chuyển sang key mới và không còn tác vụ hợp lệ dùng key cũ.
4. Thu hồi `K-old` sau cửa sổ chuyển đổi đã xác định.
5. Xác nhận key cũ bị từ chối và xóa các bản sao secret không còn cần thiết.

Khi nghi ngờ **key đã lộ**, ưu tiên thu hồi/giới hạn ngay theo kế hoạch ứng cứu thay vì kéo dài cửa sổ chồng lấp bình thường. Tách key theo môi trường và workload làm giảm tác động khi phải thu hồi khẩn cấp.

### 10.2. Access token bị lộ có thu hồi ngay được không?

Không nhất thiết. Với **JWT được resource server xác minh offline**, đổi mật khẩu hoặc thu hồi refresh token không tự làm access token cũ hết hiệu lực. Nó có thể được chấp nhận tới `exp`, trừ khi resource server còn kiểm tra session, `jti` denylist hoặc cơ chế thu hồi bổ sung. Với opaque token/introspection, trạng thái có thể thay đổi nhanh hơn nhưng còn phụ thuộc cache và thiết kế provider.

Mức độ cần thu hồi tức thời phải được quyết định từ **threat model** và yêu cầu nghiệp vụ; không có một lựa chọn token nào tự giải quyết toàn bộ vấn đề.

## 11. Mối đe dọa và biện pháp phòng tránh

| Rủi ro | Ví dụ | Cách giảm thiểu |
|---|---|---|
| **Lộ API key trên frontend** | Key quản trị được nhúng vào SPA | Đưa lời gọi nhạy cảm qua backend/BFF, giữ key trong secret manager |
| **Lộ key/token qua log** | Log nguyên header Authorization hoặc `X-API-Key` | Redaction, chỉ log key ID/metadata và trace |
| **Key đặt trong query URL** | `?api_key=secret` lọt vào history/proxy/referrer | Gửi qua header/kênh được API quy định và HTTPS |
| **Key dùng chung cho nhiều ứng dụng** | Không phân biệt workload nào dùng key | Một key theo ứng dụng/môi trường, quyền tối thiểu và audit |
| **Key dài hạn, không rotation** | Secret cũ tồn tại nhiều năm | Expiry/rotation/revocation và quy trình ứng cứu |
| **Access token sai audience vẫn được chấp nhận** | Token của API A dùng gọi API B | Resource server xác minh `aud`, loại token, issuer và signature/active |
| **Đưa ID token vào API** | Backend nhận ID token như bearer access token | Phân biệt token type và đúng đối tượng nhận |
| **Token bị đánh cắp hoặc phát lại** | Bên khác dùng bearer token/key còn hiệu lực | Giảm scope/lifetime, chống lộ secret, cân nhắc sender-constrained token |
| **Key có quyền quá rộng** | Key báo cáo đọc dữ liệu mọi tenant | Resource/action policy, giới hạn tenant, least privilege |
| **Confused deputy** | Backend dùng key toàn quyền thay người dùng | Ràng buộc quyền caller trên tài nguyên, tách quyền ứng dụng và quyền được ủy quyền |
| **Quá tin scope** | Có `orders:read` nên đọc đơn hàng bất kỳ | Kiểm tra owner/tenant/share/status của từng resource |
| **Không kiểm tra lại quyền đã thu hồi** | Membership đổi nhưng JWT vẫn còn hạn | Policy dữ liệu hiện hành hoặc cơ chế cache/invalidation phù hợp |

### 11.1. DPoP và mTLS có liên quan gì?

Bearer credential thường có rủi ro **ai cầm được là dùng được**. Với OAuth 2.0, các cơ chế như **DPoP (RFC 9449)** hoặc **mTLS certificate-bound access token (RFC 8705)** có thể ràng buộc access token với khóa/chứng chỉ của bên gửi để giảm khả năng sử dụng lại token bị đánh cắp.

**DPoP/mTLS không tự áp dụng cho API key tùy ý.** Provider có thể tự thiết kế ràng buộc tương đương cho key, nhưng cần giao thức, xác minh, quản lý khóa và chính sách riêng. Ngay cả sender-constrained token cũng không sửa lỗi một principal hợp lệ bị cấp quyền quá rộng.

## 12. Chọn API key hay OAuth token trong thực tế?

| Trường hợp | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Cron job backend lấy dữ liệu từ nhà cung cấp đơn giản | **API key theo project/workload** nếu provider hỗ trợ đủ kiểm soát | Đơn giản, phù hợp tích hợp server-to-server, cần kho secret và quyền tối thiểu |
| Backend gọi API tổ chức đã có Authorization Server OAuth | **Client Credentials + access token** | Dễ ràng buộc `aud`, scope, lifetime và chính sách AS theo workload |
| SPA/mobile có người dùng đăng nhập và gọi API thay mặt họ | **Authorization Code + PKCE**, access token đúng audience | Hạn chế lộ shared secret, bảo toàn danh tính/quyền người dùng |
| Ứng dụng web với backend/BFF và session | **Session cookie cho browser + access token tại backend** khi phù hợp | Giữ access token khỏi JavaScript nếu thiết kế BFF/session đúng |
| Người dùng cần cấp quyền truy cập có chọn lọc cho ứng dụng bên thứ ba | **OAuth 2.0 authorization/delegation** | Thể hiện phạm vi được cấp, consent/policy, thu hồi theo grant |
| Chỉ cần nhận diện client công khai để áp quota | **Public project identifier** theo hợp đồng provider | Không được xem là secret đủ để cấp quyền nhạy cảm |
| Một người dùng muốn tích hợp cá nhân qua "personal API token" | **Tùy contract provider** | Có thể là user-scoped API key hoặc access token; kiểm tra expiry, scope, revoke, quyền resource |

Không nên chọn chỉ dựa trên độ dài chuỗi, có dấu chấm JWT hay tên header. Cần hỏi **ai phát hành, xác định principal nào, cấp quyền cho API nào, token sống bao lâu, có thể thu hồi thế nào và ai giữ secret**.

### 12.1. Một API có thể yêu cầu cả API key lẫn access token không?

Có. Ví dụ provider yêu cầu **API key để xác định khách hàng/tính quota** đồng thời **OAuth access token để chứng minh quyền người dùng**. Khi đó hai credential phải có ý nghĩa rõ ràng và được kiểm tra độc lập:

~~~text
API key             -> project/application/quota principal
OAuth access token  -> user hoặc application principal theo grant
Resource policy     -> action + resource + tenant + điều kiện nghiệp vụ
~~~

Hệ thống phải định nghĩa chính sách khi hai credential thuộc khác project/tenant hoặc khi một credential thiếu. Không tự coi có cả hai là tự động tăng quyền, cũng không dùng API key để bỏ qua token validation.

## 13. Checklist thiết kế và kiểm thử

### 13.1. Các câu hỏi bắt buộc trước khi phát hành credential

1. Credential dùng để **xác thực ứng dụng, người dùng hay một grant được ủy quyền**?
2. Ai sở hữu credential, ai cấp, ai có thể thu hồi? Có phân biệt workload và môi trường không?
3. Resource server/endpoint/action/tenant nào được dùng? Chính sách dữ liệu nghiệp vụ nằm ở đâu?
4. Credential được lưu ở đâu? SPA/mobile có thể đọc được không? Có xuất hiện trong URL, repository, log không?
5. Có expiry, rotation, revoke, audit, quota và ứng cứu khi lộ không?
6. Hệ thống dùng OAuth có kiểm tra issuer, chữ ký/active, audience, token type và scope không?
7. Nếu quyền người dùng thay đổi trong lúc token còn hạn, API phản ứng thế nào?
8. Nếu nhận nhiều loại credential, có đường fallback hoặc nhầm principal giữa API key và access token không?

### 13.2. Ma trận test bảo mật

| Test | Kết quả đúng |
|---|---|
| Request thiếu API key tới endpoint bắt buộc key | Từ chối |
| Key sai/đã thu hồi/hết hạn | Từ chối, không tiết lộ secret thật |
| Key của project-A truy cập tài nguyên project-B | Từ chối nếu không có ủy quyền rõ ràng |
| Key chỉ có `metrics:read` gọi endpoint ghi dữ liệu | Từ chối |
| Access token đúng chữ ký nhưng `aud` là API khác | Từ chối |
| JWT chưa xác minh chứa `scope=admin` | Không tin claims |
| ID token dùng gọi Orders API | Từ chối |
| Refresh token dùng như bearer access token | Từ chối |
| Client Credentials token được coi là người dùng đã đăng nhập | Từ chối hoặc xử lý theo principal loại dịch vụ, không gán quyền user |
| User access token có `orders:read` đọc order của user khác | Từ chối theo resource authorization |
| Gửi đồng thời API key và bearer token với danh tính mâu thuẫn | Từ chối/áp quy tắc rõ ràng theo thiết kế endpoint |
| Khóa cũ sau rotation/revocation | Không còn được chấp nhận theo SLA thu hồi |
| Access token JWT offline bị thu hồi nhưng resource server không có cơ chế trạng thái | Kiểm thử đúng hành vi thực tế và giới hạn thời gian chấp nhận đã định |
| Log lỗi authentication/authorization | Không chứa raw API key, access token, refresh token |

### 13.3. HTTP 401, 403 và 429

| Mã | Tình huống điển hình |
|---|---|
| **401 Unauthorized** | Không có hoặc có credential không hợp lệ khi endpoint yêu cầu xác thực; với OAuth bearer nên có challenge/error tương ứng giao thức |
| **403 Forbidden** | Caller đã được xác thực nhưng thiếu quyền action/resource hoặc scope theo chính sách |
| **429 Too Many Requests** | Vượt hạn mức/rate limit; quota là một điều kiện vận hành riêng với việc chứng minh quyền |

Mã lỗi cụ thể phụ thuộc giao thức và contract API. Không nên để thông báo lỗi tiết lộ key secret, token nguyên văn hoặc thông tin resource ngoài quyền.

## 14. Tình huống tự kiểm tra

**Tình huống 1.** Một công ty nhúng `X-API-Key` vào JavaScript SPA vì mỗi người dùng truy cập website đều cần xem dữ liệu. Key cho phép đọc báo cáo nội bộ của cả công ty. Đã ổn chưa?

**Trả lời:** Không. Key bí mật trong SPA có thể bị trích xuất; bất kỳ ai lấy được có thể dùng quyền chung của công ty. Nên chuyển lời gọi nhạy cảm qua backend/BFF hoặc dùng cơ chế cấp quyền theo người dùng phù hợp, đồng thời giới hạn quyền tài nguyên.

**Tình huống 2.** Một hệ thống nhận OAuth access token dạng opaque. Không thấy header và payload JWT, có thể kết luận token giả không?

**Trả lời:** Không. OAuth access token không bắt buộc là JWT. Resource server cần xác minh token theo contract với issuer, ví dụ dùng token introspection.

**Tình huống 3.** Một backend sử dụng `client_credentials` và nhận access token có `sub` đại diện service account. Có thể xem đây là token của người dùng đang đăng nhập không?

**Trả lời:** Không. Đây là quyền của client/service principal theo luồng tương ứng. API phải áp dụng policy cho service account và không tự suy ra quyền của người dùng cuối.

**Tình huống 4.** Một API key có scope, expiry và được rotate mỗi ngày. Có phải vì vậy nó chính là OAuth access token?

**Trả lời:** Không nhất thiết. Những tính năng này cũng có thể được API provider tự triển khai cho API key. Cần xem cơ chế cấp phát, giao thức, principal, audience/resource, xác minh và hợp đồng quyền.

**Tình huống 5.** Một JWT có chữ ký hợp lệ, `scope=orders:read`, nhưng audience là `https://payments.example.com`. Orders API có được chấp nhận vì scope đọc đơn hàng không?

**Trả lời:** Không. Token không được phát hành cho Orders API; audience phải phù hợp trước khi đánh giá các điều kiện khác.

**Tình huống 6.** API provider thu hồi API key bị lộ. Vì sao vẫn cần kiểm tra log và phạm vi dữ liệu?

**Trả lời:** Revocation ngăn lần sử dụng tiếp theo theo hiệu lực thực tế của hệ thống, nhưng không đảo ngược dữ liệu đã bị truy cập trước đó. Cần điều tra phạm vi lạm dụng, kết quả request, các key/tài nguyên liên quan và nguyên nhân lộ credential.

**Tình huống 7.** Người dùng đã bị xóa khỏi dự án, nhưng access token còn hạn. API chỉ kiểm tra `scope=documents:read`. Cơ chế token có đủ không?

**Trả lời:** Chưa đủ. API cần kiểm tra membership/ownership/policy của tài liệu theo mức nhất quán hệ thống yêu cầu. Token còn hạn không đảm bảo quyền nghiệp vụ không thay đổi.

## 15. Ghi nhớ khi đánh giá một credential

Để quyết định một chuỗi dùng trong API là API key hay loại token nào, hãy đi theo sáu câu hỏi:

1. **Ai phát hành?** API provider, Authorization Server hay OpenID Provider?
2. **Ai được xác thực hoặc đại diện?** Project, ứng dụng, service account, người dùng hay delegated actor?
3. **Dùng ở đâu?** API provider, resource server có audience xác định, OIDC client hay token endpoint?
4. **Dùng để làm gì?** Xác định client, gọi API theo scope, chứng minh kết quả đăng nhập hay làm mới quyền truy cập?
5. **Kiểm tra bằng cách nào?** Key registry/secret verifier, JWT signature/claims, opaque introspection hay cơ chế theo contract?
6. **Vòng đời và rủi ro ra sao?** Expiry, rotation, revocation, storage, logging, replay và giới hạn quyền theo resource/action?

**API key thường là một credential gắn với client/dự án và quyền của API provider; OAuth access token là credential truy cập resource server trong phạm vi được Authorization Server cấp; ID token phục vụ client xác minh đăng nhập; refresh token dùng để xin token mới.** Tất cả đều cần được bảo vệ đúng vòng đời và **không loại nào tự thay thế quyết định authorization trên từng tài nguyên, hành động và tenant**.

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): các vai trò, access token, refresh token và client credentials.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): truyền access token qua header, lỗi bearer token.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, issuer, audience và quy tắc xác minh.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): claims và cách phân loại JWT access token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra trạng thái opaque access token.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh JWT đúng issuer/audience/algorithm.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ access token, refresh token và luồng OAuth.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained OAuth tokens.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): access token ràng buộc chứng chỉ.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): lưu trữ, phân phối, rotation và bảo vệ secrets.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): bảo vệ tài nguyên cụ thể trước request hợp lệ.
