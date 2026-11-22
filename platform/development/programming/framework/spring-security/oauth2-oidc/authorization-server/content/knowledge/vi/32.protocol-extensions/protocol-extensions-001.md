# Đánh giá nhu cầu custom grant và tác động đến chuẩn giao thức

## 1. Bối cảnh: không phải mọi yêu cầu cấp token đều cần một grant mới

OAuth 2.0 định nghĩa authorization grant là credential đại diện cho quyền mà Resource Owner hoặc policy của client cho phép, được client dùng để yêu cầu access token. Ngoài các grant type nền tảng, RFC 6749 cho phép mở rộng bằng **extension authorization grant**.

Trong một hệ thống Spring Security và Spring Authorization Server, nhu cầu mới thường xuất hiện khi một client phải đổi một loại assertion, mã giao dịch, bằng chứng thiết bị hoặc credential của hệ thống nội bộ lấy access token. Cách triển khai nhanh có thể là thêm một nhánh xử lý riêng vào Token Endpoint. Tuy nhiên, nếu không xác định đúng bản chất yêu cầu, extension có thể tạo ra một grant trùng chức năng với chuẩn đã có, làm giảm khả năng tương thích và mở thêm bề mặt tấn công.

Bài học thuộc chương **Mở rộng giao thức**, tập trung đánh giá khi nào nên định nghĩa custom grant, khi nào chỉ cần dùng grant hoặc extension chuẩn, và những tác động tới client, Authorization Server, Resource Server, metadata, bảo mật và vận hành.

Các ví dụ Spring sử dụng API của Spring Authorization Server 1.5.x. Khi áp dụng cho phiên bản khác, cần kiểm tra API tương ứng.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt authorization grant, grant type, client authentication và scope.
2. Xác định yêu cầu có thực sự cần một grant type mới hay không.
3. Chọn grant hoặc extension chuẩn như Authorization Code, Client Credentials, Device Authorization, JWT Bearer, Token Exchange, RAR, PAR và Resource Indicators.
4. Hiểu định dạng URI duy nhất của extension grant theo RFC 6749.
5. Đánh giá ảnh hưởng tới khả năng tương thích và metadata.
6. Thiết kế contract cho request, response, lỗi và vòng đời grant.
7. Phân tích các rủi ro replay, token substitution, over-privilege và confused deputy.
8. Triển khai điểm mở rộng bằng AuthenticationConverter và AuthenticationProvider.
9. Đăng ký grant type cho RegisteredClient và nối vào Token Endpoint.
10. Kiểm thử và vận hành extension theo yêu cầu bảo mật OAuth 2.0 hiện hành.

## 2. Phân biệt các khái niệm trước khi thiết kế

Các khái niệm sau liên quan nhưng không thể dùng thay nhau:

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Authorization grant | Credential hoặc bằng chứng nào cho phép yêu cầu token? | Authorization code, device code, JWT assertion |
| Grant type | Token Endpoint phải xử lý grant theo quy trình nào? | authorization_code, client_credentials, token-exchange |
| Client authentication | Client nào đang gọi Token Endpoint? | client_secret_basic, private_key_jwt, mTLS |
| Scope | Client xin quyền nào? | orders.read, orders.write |
| Resource indicator | Access token được dự định dùng tại resource nào? | https://api.example.com/orders |
| Authorization details | Quyền chi tiết nào được yêu cầu hoặc cấp? | Đọc số dư, khởi tạo thanh toán |
| Token format/claims | Access token mang thông tin gì và có dạng nào? | JWT, opaque token, aud, scope |

### 2.1. Grant type không phải client authentication

Client authentication chứng minh danh tính của ứng dụng gọi Token Endpoint. Grant type mô tả cách Authorization Server đánh giá căn cứ cấp token.

Một client xác thực thành công bằng mTLS hoặc private_key_jwt vẫn phải chứng minh grant hợp lệ. Ngược lại, một assertion hợp lệ cũng không mặc nhiên chứng minh client gọi request là client được phép sử dụng assertion đó.

### 2.2. Grant type không phải scope

Scope mô tả quyền được yêu cầu, không mô tả cách client nhận được quyền đó.

Ví dụ, thêm scope orders.export không đòi hỏi grant type mới nếu client vẫn dùng Authorization Code hoặc Client Credentials và chỉ cần xin thêm quyền theo policy. Tương tự, đổi danh sách scope không biến một request thành một loại grant mới.

### 2.3. OAuth grant không phải cơ chế đăng nhập ứng dụng

OAuth 2.0 chủ yếu cấp quyền truy cập protected resource. Nếu mục tiêu là xác thực người dùng và truyền danh tính cho ứng dụng, hãy dùng OpenID Connect. Không tạo custom grant để thay thế một authentication protocol hoặc để đưa mật khẩu người dùng qua client.

## 3. Quy trình đánh giá nhu cầu custom grant

Trước khi viết code, hãy mô tả yêu cầu bằng các câu hỏi:

1. Ai yêu cầu token: người dùng, ứng dụng server-side, thiết bị hay một workload?
2. Bằng chứng cấp quyền là gì: sự chấp thuận của người dùng, client identity, assertion, device code hay token khác?
3. Bằng chứng đó được phát hành bởi bên nào và được xác minh ra sao?
4. Bằng chứng có thể dùng một lần hay nhiều lần? Có thời hạn không?
5. Token cần đại diện cho ai, do client nào hành động và dành cho resource nào?
6. Quyền được quyết định bằng scope, authorization details hay policy phía server?
7. Grant chuẩn nào đã giải quyết cùng tình huống?
8. Client và Resource Server có cần hiểu một giao thức riêng hay chỉ cần nhận access token chuẩn?

Chỉ cân nhắc custom grant khi yêu cầu có **ngữ nghĩa cấp quyền riêng** và không thể mô hình hóa an toàn bằng grant/extension hiện có. Một tham số mới, một claim mới hoặc một cách xác thực client mới thường không đủ lý do để tạo grant type.

## 4. Bản đồ lựa chọn: grant và extension chuẩn

Trước khi định nghĩa grant mới, hãy so sánh với các lựa chọn sau:

| Nhu cầu | Lựa chọn chuẩn cần đánh giá | Vì sao có thể không cần custom grant |
|---|---|---|
| Ứng dụng web/mobile cần quyền do người dùng cấp | Authorization Code + PKCE | Authorization Server đã có luồng người dùng và consent |
| Dịch vụ gọi API bằng danh tính của chính nó | Client Credentials | Client authentication và policy có thể xác định quyền |
| Thiết bị không có browser hoặc khó nhập liệu | Device Authorization Grant (RFC 8628) | Đã có device code, user code và polling protocol |
| Đổi JWT assertion lấy access token | JWT Bearer Grant (RFC 7523) | Đã có profile xác minh assertion và quy tắc token request |
| Đổi token để delegation hoặc impersonation | Token Exchange (RFC 8693) | Đã có subject token, actor token và semantics delegation |
| Quyền chi tiết vượt quá scope dạng chuỗi | Rich Authorization Requests (RFC 9396) | Dùng authorization_details để mô tả quyền |
| Chỉ định API/resource đích | Resource Indicators (RFC 8707) | Dùng resource để giới hạn nơi access token được sử dụng |
| Gửi authorization request trực tiếp tới OP | Pushed Authorization Requests (RFC 9126) | Thay đổi cách gửi request, không cần grant mới |
| Xác thực client bằng khóa bất đối xứng | private_key_jwt hoặc mTLS | Đây là client authentication method |
| Chống replay token bị đánh cắp | DPoP hoặc mTLS sender-constrained token | Đây là cơ chế ràng buộc token với sender |
| Thêm dữ liệu vào access token | OAuth2TokenCustomizer hoặc token claims policy | Không thay đổi cách client nhận token |

### 4.1. Authorization Code + PKCE

Khi người dùng tương tác và cấp quyền cho một ứng dụng, Authorization Code với PKCE thường là lựa chọn phù hợp. Client nhận authorization code qua redirect và đổi code tại Token Endpoint.

Không tạo custom grant chỉ để bỏ qua trang đăng nhập, consent hoặc PKCE. Nếu yêu cầu cần một trải nghiệm xác thực khác, hãy xem xét OIDC hoặc một authentication flow phù hợp.

### 4.2. Client Credentials

Khi workload gọi API bằng quyền của chính nó, Client Credentials thường phù hợp. Quyền có thể được quyết định bởi RegisteredClient, scope được phép, resource và policy vận hành.

Không tạo grant riêng chỉ vì client cần thêm một tham số xác định môi trường, tenant hoặc loại công việc nếu tham số đó có thể được xử lý an toàn bằng policy và token customization.

### 4.3. Device Authorization Grant

RFC 8628 dành cho thiết bị có kết nối Internet nhưng thiếu browser phù hợp hoặc có giới hạn nhập liệu. Thiết bị xin device code, hiển thị user code và URI; người dùng hoàn tất xác thực trên thiết bị thứ hai.

Nếu yêu cầu thực chất là “thiết bị TV cần user đăng nhập bằng điện thoại”, hãy dùng Device Authorization Grant hoặc implementation tương thích. Một grant tự thiết kế lại device code/polling sẽ tạo ra một giao thức thứ hai khó tương thích.

### 4.4. JWT Bearer Grant

RFC 7523 định nghĩa JWT Bearer assertion có thể được dùng làm authorization grant để xin access token. Nếu hệ thống đã phát hành JWT assertion với issuer, audience, thời hạn và chữ ký có thể kiểm tra, hãy đánh giá profile chuẩn này trước khi thiết kế grant riêng.

Lưu ý: JWT Bearer Grant và private_key_jwt là hai cách dùng JWT khác nhau. JWT Bearer Grant dùng assertion làm authorization grant; private_key_jwt dùng JWT để xác thực client tại Token Endpoint.

### 4.5. Token Exchange

RFC 8693 định nghĩa Token Exchange cho các tình huống Security Token Service, bao gồm delegation và impersonation. Client gửi subject token và có thể gửi actor token, đồng thời chỉ định token type, resource hoặc scope theo contract.

Nếu service A cần token để gọi service B thay mặt người dùng, hãy đánh giá Token Exchange trước khi thiết kế grant “service delegation” riêng. Cần phân biệt rõ impersonation với delegation vì hai mô hình có trách nhiệm và dấu vết audit khác nhau.

### 4.6. RAR, Resource Indicators và PAR không phải grant type

- **RAR** thêm authorization_details để mô tả quyền chi tiết; nó không định nghĩa một cách đổi credential lấy token hoàn toàn mới.
- **Resource Indicators** dùng resource parameter để chỉ định resource server đích.
- **PAR** chuyển authorization request tới endpoint riêng bằng POST, sau đó browser sử dụng request_uri để tiếp tục authorization flow.

Những extension này có thể giải quyết phần lớn yêu cầu tưởng như cần custom grant. Chúng mở rộng dữ liệu hoặc cách vận chuyển request trong giao thức đang có.

## 5. Khi nào custom grant là hợp lý?

Custom grant có thể phù hợp khi tất cả các điều kiện sau được xác định rõ:

- Có một loại authorization credential hoặc quy trình xác minh riêng.
- Credential đó có semantics cấp quyền độc lập, không chỉ là một scope hay claim.
- Không có grant/extension chuẩn phù hợp hoặc việc dùng chuẩn sẽ làm sai semantics.
- Client và Authorization Server có thể phối hợp triển khai giao thức mới.
- Có thể xác định issuer, audience, subject, client binding và thời hạn của grant.
- Có quy tắc chống replay, thu hồi và audit.
- Resource Server hiểu chính xác token được phát hành đại diện cho quyền gì.
- Có tài liệu giao thức, versioning và kế hoạch tương thích.

Ví dụ: một nền tảng có dịch vụ thiết bị phát hành assertion đã ký, gắn với một thiết bị đã được đăng ký, một client cụ thể, một resource và một nhiệm vụ có thời hạn rất ngắn. Authorization Server cần xác minh assertion, kiểm tra thiết bị chưa bị thu hồi, tiêu thụ bằng chứng một lần và phát access token giới hạn theo nhiệm vụ. Nếu profile assertion này không tương thích JWT Bearer Grant hoặc một chuẩn khác, extension grant riêng có thể hợp lý.

Đây là ví dụ kiến trúc. Nó không có nghĩa cứ có một assertion nội bộ là cần grant mới.

## 6. Khi nào không nên tạo custom grant?

| Yêu cầu | Cách tiếp cận nên đánh giá |
|---|---|
| Thêm scope hoặc quyền mới | Cấu hình scope và policy |
| Thêm claim vào JWT access token | OAuth2TokenCustomizer và claim policy |
| Xác thực client bằng certificate | mTLS client authentication |
| Xác thực client bằng JWT ký | private_key_jwt |
| Chọn resource đích | RFC 8707 Resource Indicators |
| Gửi authorization request có payload lớn | RFC 9126 PAR |
| Quyền chi tiết theo giao dịch | RFC 9396 RAR |
| Đổi access token để gọi service khác | RFC 8693 Token Exchange |
| Thiết bị nhập liệu hạn chế | RFC 8628 Device Authorization |
| Dùng mật khẩu người dùng để xin token | Không thiết kế grant kiểu Resource Owner Password Credentials |

RFC 9700, OAuth 2.0 Security Best Current Practice, quy định Resource Owner Password Credentials Grant **MUST NOT** được sử dụng. Không tạo một custom grant chỉ đổi tên password grant hoặc chuyển username/password qua một tham số riêng. Cách đó vẫn phơi bày credential người dùng cho client và không giải quyết được rủi ro gốc.

## 7. Đánh giá tác động tới chuẩn giao thức

Một custom grant làm thay đổi contract tại Token Endpoint. Tác động không chỉ nằm ở Authorization Server.

| Thành phần | Thay đổi cần đánh giá |
|---|---|
| Client | Biết grant_type, tham số, credential, error và retry semantics |
| Authorization Server | Parse request, xác thực client, kiểm tra grant, phát token và lưu authorization |
| RegisteredClient | Cho phép đúng client dùng grant mới |
| Resource Server | Hiểu audience, subject, actor, scope và claim của token |
| Authorization metadata | Công bố grant type nếu server hỗ trợ metadata |
| SDK/API gateway | Có thể cần cập nhật allowlist, parser và observability |
| Audit/operations | Theo dõi grant issue, reject, replay, revoke và abuse |
| Tổ chức tích hợp | Cần tài liệu, versioning, conformance tests và quy trình thay đổi |

### 7.1. Khả năng tương thích với client chuẩn

Một OAuth client tổng quát có thể gửi POST tới Token Endpoint và xử lý token response chuẩn. Tuy nhiên, nó không tự biết cách tạo credential riêng hoặc các tham số của custom grant.

Vì vậy, việc Token Endpoint vẫn trả access_token/token_type/expires_in theo OAuth không làm cho toàn bộ custom grant trở nên interoperable. Client phải triển khai đúng extension contract.

### 7.2. Resource Server cũng chịu ảnh hưởng

Nếu custom grant phát token với semantics mới, Resource Server phải biết cách đánh giá token. Ví dụ, token đại diện cho thiết bị và người dùng cùng lúc cần có quy tắc rõ về subject, actor và audience.

Không chỉ thêm một claim tùy ý rồi giả định các API sẽ tự hiểu. Cần định nghĩa claim, quyền, resource và cách Resource Server xác minh.

### 7.3. Metadata và discovery

RFC 8414 định nghĩa metadata Authorization Server, trong đó trường tùy chọn `grant_types_supported` liệt kê các grant type mà server hỗ trợ.

Nếu server công bố metadata, hãy đảm bảo danh sách phản ánh chính xác grant mới. Đừng công bố một grant mà server chưa bật hoặc chưa hoàn tất validation. Đồng thời, kiểm tra metadata của Spring Authorization Server có được tùy biến để công bố extension hay không; không mặc định rằng việc thêm provider tự động cập nhật metadata.

## 8. Định danh grant type và quy tắc mở rộng tham số

RFC 6749 `4.5` yêu cầu client chỉ định extension grant bằng một URI tuyệt đối trong tham số `grant_type` của Token Endpoint.

RFC 6749 `8.3` cũng yêu cầu mỗi grant type mới có một URI tuyệt đối duy nhất. Nếu extension cần thêm token endpoint request parameters, các tham số đó phải được đăng ký trong OAuth Parameters registry theo `8.2` và `11.2`.

Ví dụ URI do tổ chức sở hữu:

~~~text
https://auth.example.com/grants/device-attestation
~~~

Đây là URI minh họa cho domain dành riêng trong tài liệu. Trong hệ thống thực, chọn namespace thuộc quyền kiểm soát của tổ chức và giữ ổn định qua các phiên bản.

### 8.1. Không dùng tên ngắn dễ xung đột

Không đặt grant type mới là `device`, `assertion` hoặc `custom`. Tên ngắn có thể trùng với extension của nhà cung cấp khác hoặc khiến client hiểu sai semantics.

URI giúp định danh rõ extension và chủ thể chịu trách nhiệm về đặc tả.

### 8.2. Định nghĩa parameter contract

Với mỗi tham số bổ sung, cần mô tả:

- Tên, kiểu dữ liệu và encoding.
- Bắt buộc hay tùy chọn.
- Có được lặp lại hay không.
- Giới hạn kích thước.
- Thời hạn và cách xác minh.
- Quan hệ với client_id, grant type, scope và resource.
- Error code tương ứng.
- Cách xử lý tham số không được hỗ trợ.

Ví dụ, tham số `assertion` có thể bắt buộc đúng một giá trị. Nếu client gửi hai assertion, server phải từ chối thay vì âm thầm chọn giá trị đầu tiên.

### 8.3. Error contract

Ưu tiên OAuth error code hiện có:

| Error | Ý nghĩa điển hình |
|---|---|
| `invalid_request` | Thiếu tham số bắt buộc, tham số trùng hoặc request sai định dạng |
| `invalid_client` | Client authentication thất bại |
| `unauthorized_client` | Client không được phép dùng grant type |
| `unsupported_grant_type` | Server không hỗ trợ grant type được yêu cầu |
| `invalid_grant` | Assertion/code/credential không hợp lệ, hết hạn, đã dùng hoặc không khớp |
| `invalid_scope` | Scope yêu cầu không được phép |
| `server_error` | Lỗi nội bộ khi phát token hoặc lưu authorization |

Nếu cần error code riêng cho extension được đăng ký, hãy tuân thủ quy tắc extension error trong RFC 6749 `8.5`. Không trả thông tin chi tiết về khóa, token, user hoặc lý do nội bộ có thể giúp attacker dò đoán.

## 9. Thiết kế protocol contract trước khi viết code

Một đặc tả custom grant tối thiểu cần các phần:

1. **Purpose:** tình huống cấp token được giải quyết.
2. **Grant type URI:** định danh duy nhất.
3. **Client authentication:** phương thức client được phép dùng.
4. **Request parameters:** tên, kiểu, cardinality, encoding và giới hạn.
5. **Grant validation:** issuer, audience, signature, time, subject, client binding.
6. **Authorization policy:** scope, resource, tenant, consent và quyền.
7. **Token issuance:** loại token, TTL, audience, claims, refresh policy.
8. **Persistence:** authorization ID, grant type, subject, token metadata và trạng thái.
9. **Errors:** error code, HTTP status và quy tắc không tiết lộ dữ liệu.
10. **Replay/revocation:** one-time use, jti, nonce, revocation và retry.
11. **Metadata:** grant_types_supported và tài liệu cho client.
12. **Versioning:** cách nâng cấp request và xử lý client cũ.

Không bắt đầu từ một AuthenticationProvider rồi để semantics được quyết định dần trong code. Contract cần được review bởi chủ sở hữu client, Authorization Server và Resource Server trước.

## 10. Ranh giới bảo mật của custom grant

Một custom grant thường nhận credential do client gửi lên. Credential có thể là assertion ký số, mã dùng một lần, proof từ thiết bị hoặc token của một hệ thống khác. Mỗi loại có rủi ro riêng.

### 10.1. Xác thực client độc lập với xác minh grant

Thực hiện cả hai bước:

1. Xác thực client theo phương thức đã đăng ký.
2. Xác minh authorization grant và ràng buộc nó với client đã xác thực.

Không cấp token chỉ vì assertion có chữ ký hợp lệ. Assertion có thể được phát hành cho client khác, resource khác hoặc môi trường khác.

### 10.2. Kiểm tra assertion/JWT

Nếu grant mang JWT hoặc assertion đã ký, kiểm tra tối thiểu:

- Chữ ký bằng khóa thuộc issuer tin cậy.
- Thuật toán nằm trong allowlist.
- `iss` đúng issuer được cấu hình.
- `aud` đúng Authorization Server hoặc recipient theo profile.
- `exp` chưa hết hạn và `nbf` đã có hiệu lực.
- `iat` nằm trong khoảng thời gian hợp lý.
- `jti` hoặc nonce được kiểm tra replay khi profile yêu cầu.
- Subject, actor, tenant và client binding đúng policy.

Không chỉ decode JWT rồi tin payload. Không nhận khóa hoặc issuer tùy ý từ chính assertion mà chưa có trust configuration.

### 10.3. Chống replay và sử dụng một lần

Nếu grant là code dùng một lần:

- Sinh giá trị khó đoán với entropy đủ cao.
- Lưu hash của code nếu có thể.
- Gắn code với client, subject, resource và scope.
- Có thời hạn ngắn.
- Tiêu thụ code bằng thao tác nguyên tử để hai request đồng thời không cùng thành công.
- Ghi nhận replay mà không ghi raw code vào log.

Kiểm tra “đã dùng chưa” rồi mới đánh dấu trong hai thao tác database riêng có thể tạo race condition. Dùng transaction, compare-and-set hoặc unique constraint phù hợp.

### 10.4. Giới hạn quyền của access token

RFC 9700 khuyến nghị access token có quyền tối thiểu và audience giới hạn vào một Resource Server hoặc một nhóm nhỏ resource. Grant mới không được trở thành đường vòng để cấp token rộng hơn policy hiện có.

Xác định rõ:

- Token đại diện cho ai.
- Client nào hành động.
- Resource nào được phép nhận token.
- Scope/authorization details nào được cấp.
- Token sống bao lâu.
- Có cần refresh token không.

### 10.5. Sender-constrained token

Khi rủi ro token bị đánh cắp cao, cân nhắc sender-constrained token bằng mTLS hoặc DPoP. RFC 9700 khuyến nghị Authorization Server và Resource Server dùng cơ chế này để giảm replay access token.

Đây là lớp bảo vệ token sau khi phát hành. Nó không thay thế việc xác minh custom grant trước khi cấp token.

## 11. Vòng đời của một custom grant

Một luồng điển hình:

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant AS as Spring Authorization Server
    participant V as Grant Verifier
    participant DB as Authorization Store
    participant RS as Resource Server

    C->>AS: POST /oauth2/token + client authentication + custom grant
    AS->>AS: Authenticate client
    AS->>AS: AuthenticationConverter parses request
    AS->>AS: Check RegisteredClient allows grant
    AS->>V: Verify grant credential and policy
    V->>V: Validate signature, time, audience and replay
    V-->>AS: Verified subject, client binding, resource and scopes
    AS->>AS: Build OAuth2TokenContext
    AS->>AS: OAuth2TokenGenerator creates access token
    AS->>DB: Save OAuth2Authorization
    DB-->>AS: Authorization persisted
    AS-->>C: Standard OAuth token response
    C->>RS: API request with access token
    RS->>RS: Validate token, audience and authorization
~~~

Các bước cần có:

1. Token Endpoint nhận request.
2. Client authentication filter xác thực ứng dụng.
3. Converter nhận diện grant type và parse request.
4. Provider kiểm tra client được phép dùng grant.
5. Provider xác minh credential và authorization policy.
6. Token context được tạo với grant type, principal, scope và resource.
7. Token generator phát access token.
8. Authorization được lưu để phục vụ tra cứu, revoke, introspection hoặc audit theo kiến trúc.
9. Token response tuân theo OAuth response contract.

## 12. Spring Authorization Server: các điểm mở rộng

Spring Authorization Server cung cấp extension point cho custom authorization grant tại OAuth2 Token Endpoint. Theo hướng dẫn 1.5.8, cần ba phần:

- **AuthenticationConverter:** nhận diện grant type và chuyển HTTP request thành Authentication object.
- **AuthenticationProvider:** xác minh grant, kiểm tra client/policy và phát token.
- **Token Endpoint configuration:** đăng ký converter/provider để endpoint sử dụng.

Ngoài ra, cần đăng ký grant type trong `RegisteredClient` và dùng `OAuth2TokenGenerator` cùng `OAuth2AuthorizationService` của ứng dụng.

### 12.1. AuthenticationConverter

Converter chỉ xử lý grant type mà nó sở hữu. Nếu request thuộc grant khác, trả `null` để converter tiếp theo trong chain xử lý.

Converter không nên phát token hoặc thực hiện logic cấp quyền. Nhiệm vụ của nó là parse và kiểm tra cấu trúc request:

- Có đúng grant_type không?
- Có đủ parameter bắt buộc không?
- Parameter có bị lặp ngoài contract không?
- Kiểu/độ dài có hợp lệ không?
- Client principal hiện tại là ai?

### 12.2. AuthenticationProvider

Provider chịu trách nhiệm xác minh credential và quyết định có được cấp token hay không. Provider cần:

- Lấy authenticated client principal.
- Kiểm tra grant type nằm trong danh sách của RegisteredClient.
- Xác minh authorization grant.
- Xác định subject/actor, resource và authorized scopes.
- Tạo OAuth2TokenContext.
- Gọi OAuth2TokenGenerator.
- Tạo và lưu OAuth2Authorization.
- Trả OAuth2AccessTokenAuthenticationToken hoặc lỗi OAuth2 phù hợp.

Không đưa logic kiểm tra assertion quan trọng vào converter rồi giả định mọi request đã được xác thực chỉ vì converter tạo được Authentication object.

## 13. Định nghĩa AuthorizationGrantType và Authentication token

Ví dụ minh họa một grant nhận device attestation đã ký:

~~~java
public final class DeviceAttestationGrant {

    public static final AuthorizationGrantType GRANT_TYPE =
        new AuthorizationGrantType(
            "https://auth.example.com/grants/device-attestation");

    public static final String ASSERTION_PARAMETER = "assertion";

    private DeviceAttestationGrant() {
    }
}
~~~

Authentication token giữ assertion và client principal:

~~~java
public final class DeviceAttestationGrantAuthenticationToken
        extends OAuth2AuthorizationGrantAuthenticationToken {

    private final String assertion;

    public DeviceAttestationGrantAuthenticationToken(
            Authentication clientPrincipal, String assertion) {

        super(DeviceAttestationGrant.GRANT_TYPE,
            clientPrincipal, Collections.emptyMap());

        this.assertion = assertion;
    }

    public String getAssertion() {
        return this.assertion;
    }
}
~~~

Đây là khung minh họa cho grant riêng. Trong ứng dụng thực, có thể giữ thêm parameter đã được parse nhưng không lưu raw secret không cần thiết vào object hoặc log.

## 14. Viết AuthenticationConverter

Converter nhận đúng grant type, kiểm tra assertion chỉ xuất hiện một lần và tạo Authentication token:

~~~java
public final class DeviceAttestationGrantAuthenticationConverter
        implements AuthenticationConverter {

    @Override
    public Authentication convert(HttpServletRequest request) {
        String grantType =
            request.getParameter(OAuth2ParameterNames.GRANT_TYPE);

        if (!DeviceAttestationGrant.GRANT_TYPE.getValue()
                .equals(grantType)) {
            return null;
        }

        String[] assertions =
            request.getParameterValues(
                DeviceAttestationGrant.ASSERTION_PARAMETER);

        if (assertions == null
                || assertions.length != 1
                || !StringUtils.hasText(assertions[0])) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_REQUEST);
        }

        Authentication clientPrincipal =
            SecurityContextHolder.getContext().getAuthentication();

        return new DeviceAttestationGrantAuthenticationToken(
            clientPrincipal, assertions[0]);
    }
}
~~~

Đoạn code tập trung vào cấu trúc converter. Production còn cần giới hạn kích thước request, content type, parameter allowlist và kiểm soát việc log request. Nếu grant có thêm parameter, hãy định nghĩa cardinality và validation cho từng trường.

## 15. Viết AuthenticationProvider và phát token

Provider nên ủy quyền phần xác minh credential cho một service có contract riêng. Ví dụ:

~~~java
VerifiedDeviceGrant verifiedGrant =
    deviceAttestationVerifier.verifyAndConsume(
        grantAuthentication.getAssertion(),
        registeredClient,
        authorizationServerIssuer);
~~~

Service trên phải xác minh chữ ký/issuer/audience/thời gian, ràng buộc assertion với client và resource, đồng thời tiêu thụ grant một cách nguyên tử nếu nó dùng một lần.

Contract của service cần trả về dữ liệu đã được xác minh, không chỉ một boolean:

~~~java
public interface DeviceAttestationVerifier {

    VerifiedDeviceGrant verifyAndConsume(
            String assertion,
            RegisteredClient registeredClient,
            String authorizationServerIssuer);
}

public record VerifiedDeviceGrant(
        String subject,
        String resource,
        Set<String> allowedScopes) {
}
~~~

Đây là kiểu dữ liệu minh họa. Assertion phải được kiểm tra trước khi tạo object này; không lấy subject, resource hoặc scope trực tiếp từ request chưa xác minh.

Sau khi xác minh, provider xác định scope được phép và tạo token context:

~~~java
OAuth2TokenContext tokenContext =
    DefaultOAuth2TokenContext.builder()
        .registeredClient(registeredClient)
        .principal(clientPrincipal)
        .authorizationServerContext(
            AuthorizationServerContextHolder.getContext())
        .tokenType(OAuth2TokenType.ACCESS_TOKEN)
        .authorizedScopes(authorizedScopes)
        .authorizationGrantType(
            DeviceAttestationGrant.GRANT_TYPE)
        .authorizationGrant(grantAuthentication)
        .build();

OAuth2Token generatedToken =
    tokenGenerator.generate(tokenContext);

if (generatedToken == null) {
    throw new OAuth2AuthenticationException(
        new OAuth2Error(
            OAuth2ErrorCodes.SERVER_ERROR,
            "The token generator failed to generate an access token.",
            null));
}
~~~

Sau đó provider tạo access token và lưu authorization:

~~~java
OAuth2AccessToken accessToken = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    generatedToken.getTokenValue(),
    generatedToken.getIssuedAt(),
    generatedToken.getExpiresAt(),
    authorizedScopes);

OAuth2Authorization.Builder authorizationBuilder =
    OAuth2Authorization.withRegisteredClient(registeredClient)
        .principalName(verifiedGrant.subject())
        .authorizationGrantType(
            DeviceAttestationGrant.GRANT_TYPE)
        .authorizedScopes(authorizedScopes);

if (generatedToken instanceof ClaimAccessor claimAccessor) {
    authorizationBuilder.token(accessToken, metadata ->
            metadata.put(
                OAuth2Authorization.Token.CLAIMS_METADATA_NAME,
                claimAccessor.getClaims()));
} else {
    authorizationBuilder.accessToken(accessToken);
}

OAuth2Authorization authorization = authorizationBuilder.build();
authorizationService.save(authorization);

return new OAuth2AccessTokenAuthenticationToken(
    registeredClient, clientPrincipal, accessToken);
~~~

Trong ví dụ này, client principal trong token context xác định ứng dụng đã xác thực; subject lấy từ assertion đã xác minh được lưu riêng trong authorization. Nếu grant đại diện cho client mà không có End-User hoặc device subject riêng, dùng client identity làm principal theo semantics của grant. Khi phát JWT, cần bảo đảm claim `sub` phản ánh đúng subject của grant; vì token context ở ví dụ dùng client principal, token customizer phải lấy subject từ grant đã xác minh thay vì mặc định dùng tên client. Không lấy claim `sub` trực tiếp từ assertion chưa xác minh. Khi generated token là JWT, lưu cả claims metadata để các thành phần persistence có thể đọc lại claims.

Không phát refresh token theo mặc định chỉ vì token generator có hỗ trợ refresh token. Nếu cấp refresh token cho public client, RFC 9700 yêu cầu sender-constrain hoặc rotation; với confidential client vẫn cần ràng buộc refresh token với client đã cấp.

## 16. Đăng ký grant type cho RegisteredClient

Authorization Server chỉ nên cho những client được cấu hình rõ ràng sử dụng custom grant.

~~~java
RegisteredClient deviceClient = RegisteredClient
    .withId(UUID.randomUUID().toString())
    .clientId("device-agent")
    .clientSecret(passwordEncoder.encode(secretFromSecretManager))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        DeviceAttestationGrant.GRANT_TYPE)
    .scope("device.status")
    .scope("device.command")
    .build();
~~~

Đây là ví dụ client confidential. Production cần lưu secret trong secret manager và dùng repository bền vững. Client chỉ được xin scope nằm trong policy đã cấu hình và quyền của assertion.

Không thêm custom grant vào mọi RegisteredClient chỉ để tránh lỗi cấu hình. Allowlist grant type là một lớp kiểm soát quan trọng.

## 17. Gắn converter và provider vào Token Endpoint

Ví dụ cấu hình Spring Authorization Server 1.5.x:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        OAuth2AuthorizationService authorizationService,
        OAuth2TokenGenerator<?> tokenGenerator,
        DeviceAttestationVerifier verifier) throws Exception {

    OAuth2AuthorizationServerConfigurer configurer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    DeviceAttestationGrantAuthenticationConverter converter =
        new DeviceAttestationGrantAuthenticationConverter();

    DeviceAttestationGrantAuthenticationProvider provider =
        new DeviceAttestationGrantAuthenticationProvider(
            authorizationService, tokenGenerator, verifier);

    http
        .securityMatcher(configurer.getEndpointsMatcher())
        .with(configurer, authorizationServer ->
            authorizationServer.tokenEndpoint(tokenEndpoint ->
                tokenEndpoint
                    .accessTokenRequestConverter(converter)
                    .authenticationProvider(provider)
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated()
        );

    return http.build();
}
~~~

Tên constructor và dependency của provider phụ thuộc implementation ứng dụng. Cấu hình minh họa cho thấy hai điểm nối: converter parse request, provider xử lý grant. Không thay toàn bộ Token Endpoint hoặc bỏ client authentication filter.

## 18. Client gọi Token Endpoint

Request mẫu dùng client authentication bằng HTTP Basic:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_DEVICE_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=https%3A%2F%2Fauth.example.com%2Fgrants%2Fdevice-attestation&assertion=SIGNED_DEVICE_ASSERTION&scope=device.status
~~~

Nếu client dùng private_key_jwt hoặc mTLS, phần client authentication thay đổi theo registration. Assertion trong body là authorization grant của ví dụ; nó không thay client authentication.

Response vẫn dùng cấu trúc OAuth token response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "device.status"
}
~~~

Client và Resource Server không nên phải học một response envelope riêng nếu extension chỉ thay cách xác minh grant. Giữ response chuẩn giúp tận dụng OAuth client libraries và middleware hiện có.

## 19. Tác động tới token, scope và Resource Server

Custom grant xác định căn cứ phát token; nó không tự quyết định token phải chứa mọi thông tin của grant.

Cần xác định rõ:

- Subject của token là người dùng, thiết bị hay workload.
- Client nào thực hiện hành động.
- Có actor/delegation semantics hay không.
- Audience/resource đích.
- Scope hoặc authorization details được cấp.
- Token TTL và sender constraint.
- Resource Server xác minh các claim nào.

Nếu token mang subject là thiết bị nhưng Resource Server diễn giải subject như user ID, có thể xảy ra lỗi phân quyền. Claim cần có semantics, issuer và audience rõ ràng; tránh tái sử dụng claim chuẩn cho ý nghĩa khác.

### 19.1. Giới hạn scope theo grant

Không tin scope do client gửi. Provider phải kiểm tra scope yêu cầu là tập con của quyền được phép theo client, grant và policy. Nếu assertion chỉ cho phép device.status, client không thể thêm device.command bằng cách thay request parameter.

### 19.2. Audience và resource

Access token phải dành cho đúng Resource Server. Nếu client có thể chỉ định resource, Authorization Server cần allowlist resource và kiểm tra assertion có quyền cấp token cho resource đó.

Resource Server phải xác minh audience và quyền trên từng request; chỉ xác minh chữ ký JWT là chưa đủ.

## 20. Metadata, versioning và tương thích client

Nếu Authorization Server công bố RFC 8414 metadata, có thể liệt kê custom grant trong `grant_types_supported`. Đây là metadata tùy chọn nhưng hữu ích để client discovery.

Ngoài metadata, cần công bố tài liệu client:

- URI grant type.
- Token endpoint và client authentication method.
- Request parameters và ví dụ.
- Scope/resource hợp lệ.
- Error response và retry policy.
- Token claims và audience.
- Version, deprecation date và migration window.

Nếu thay semantics của assertion hoặc parameter, không âm thầm làm client cũ hiểu sai. Có thể tạo URI grant version mới hoặc định nghĩa version field với quy tắc tương thích rõ ràng. Không thay URI grant type hiện có để mang một semantics khác.

## 21. Kiểm thử custom grant

### 21.1. Test request parsing

| Test case | Kết quả mong đợi |
|---|---|
| grant_type không thuộc custom grant | Converter trả null |
| grant_type đúng và assertion hợp lệ về cấu trúc | Tạo Authentication token |
| Thiếu assertion | invalid_request |
| Assertion rỗng | invalid_request |
| Assertion lặp nhiều lần | invalid_request |
| Request có parameter không được hỗ trợ | Bị từ chối theo contract |
| Assertion vượt giới hạn kích thước | Bị từ chối trước khi xác minh |

### 21.2. Test client và grant policy

- Client authentication thất bại.
- Client chưa đăng ký custom grant.
- Client bị disable hoặc registration hết hiệu lực.
- Assertion được cấp cho client khác.
- Assertion sai issuer hoặc audience.
- Assertion hết hạn hoặc chưa có hiệu lực.
- Assertion đã bị revoke hoặc đã được sử dụng.
- Assertion có chữ ký bằng thuật toán/khóa không được tin cậy.
- Scope yêu cầu vượt quá quyền của grant.
- Resource đích không được phép.

### 21.3. Test token issuance và persistence

- Token generator trả token hợp lệ.
- Token generator không tạo được token.
- OAuth2Authorization được lưu đúng grant type.
- Authorized scopes và principal đúng.
- JWT claims có issuer, audience, subject và actor theo contract.
- Token response có cấu trúc OAuth chuẩn.
- Resource Server chấp nhận token hợp lệ và từ chối token sai audience.
- Authorization service có thể tra cứu/revoke token theo policy.

### 21.4. Test concurrency và replay

Gửi hai request đồng thời sử dụng cùng một one-time assertion. Chỉ một request được phép tiêu thụ grant thành công. Request còn lại phải nhận invalid_grant.

Test này phải chạy với persistence implementation thật hoặc test double mô phỏng đúng transaction/atomic consume semantics; chỉ mock verifier luôn trả true không kiểm chứng được replay protection.

## 22. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Tạo custom grant cho một scope mới | Tăng protocol complexity không cần thiết | Dùng scope và policy |
| Dùng grant mới để thay client authentication | Client identity và grant bị nhập làm một | Tách hai bước xác minh |
| Dùng tên grant ngắn hoặc không duy nhất | Xung đột với extension khác | Dùng unique absolute URI |
| Không kiểm tra RegisteredClient grant allowlist | Client ngoài policy vẫn có thể dùng grant | Kiểm tra grant type trong provider |
| Chỉ xác minh chữ ký assertion | Assertion có thể sai audience/client hoặc bị replay | Kiểm tra đầy đủ claims và replay state |
| Chấp nhận scope do client tự quyết định | Over-privilege | Tính authorized scopes từ policy |
| Không giới hạn audience | Token có thể dùng sai Resource Server | Audience restriction |
| Lưu grant one-time không nguyên tử | Hai request cùng nhận token | Atomic consume và concurrency test |
| Cấp refresh token không policy | Credential có thể tồn tại lâu hơn grant | TTL, rotation và sender constraint |
| Thay response token chuẩn bằng envelope riêng | Client library khó tương thích | Giữ OAuth token response |
| Không công bố metadata/tài liệu | Client không thể discovery hoặc tích hợp đúng | Cập nhật metadata và contract |
| Dùng password grant hoặc biến thể đổi tên | Phơi bày password cho client | Authorization Code + PKCE hoặc flow phù hợp |
| Bỏ lưu OAuth2Authorization | Khó revoke, introspect và audit | Persist authorization theo policy |
| Không test Resource Server | Token phát ra có thể sai audience/claims | End-to-end authorization test |

## 23. Observability và vận hành

Theo dõi:

- Số request theo grant type và client ID.
- Số lần xác minh grant thành công/thất bại.
- Lỗi invalid_grant, unauthorized_client, invalid_scope và server_error.
- Assertion expired, bad issuer/audience, bad signature và replay.
- Thời gian xử lý verifier và token generation.
- Token issuance theo resource/scope.
- Authorization persistence failures.
- Tỷ lệ client dùng phiên bản contract cũ.
- Các đợt tăng bất thường của request hoặc invalid grant.

Không ghi raw assertion, bearer token, client secret hoặc private key vào log. Audit nên có correlation ID, client ID, grant type URI, issuer, resource, kết quả và fingerprint đã pseudonymize nếu cần điều tra.

### 23.1. Runbook khi custom grant bị từ chối hàng loạt

1. Kiểm tra client authentication và trạng thái RegisteredClient.
2. Xác nhận client còn được phép dùng grant type.
3. Kiểm tra issuer, audience, clock skew và key rotation của assertion.
4. Kiểm tra assertion có bị hết hạn hoặc replay không.
5. Kiểm tra scope/resource policy có thay đổi không.
6. Kiểm tra verifier và grant store có sẵn sàng không.
7. Kiểm tra token generator và authorization persistence.
8. Kiểm tra metadata/client configuration có cùng phiên bản contract không.

Không khắc phục bằng cách bỏ xác minh assertion, cho phép mọi client dùng grant hoặc cấp scope rộng hơn.

## 24. Checklist quyết định và triển khai

### Trước khi quyết định custom grant

- [ ] Đã xác định đúng authorization credential và semantics của yêu cầu.
- [ ] Đã so sánh Authorization Code, Client Credentials, Device, JWT Bearer và Token Exchange.
- [ ] Đã xem xét RAR, Resource Indicators, PAR và client authentication extensions.
- [ ] Không dùng custom grant để thay thế OIDC login hoặc password grant.
- [ ] Có lý do rõ ràng vì sao grant/extension chuẩn không đáp ứng được.

### Khi định nghĩa protocol

- [ ] Grant type dùng unique absolute URI.
- [ ] Parameter contract có syntax, cardinality, size và encoding.
- [ ] Error contract dùng OAuth errors phù hợp.
- [ ] Parameter/error extension tuân thủ quy tắc đăng ký khi cần.
- [ ] Metadata grant_types_supported và tài liệu client được cập nhật.
- [ ] Có versioning và migration policy.

### Khi triển khai Spring Authorization Server

- [ ] Có AuthenticationConverter riêng.
- [ ] Có AuthenticationProvider riêng.
- [ ] Provider xác thực client và kiểm tra RegisteredClient grant allowlist.
- [ ] Grant verifier kiểm tra credential và replay.
- [ ] Authorized scopes/resource được tính theo policy.
- [ ] Token context dùng đúng grant type, principal và token type.
- [ ] Token được tạo bằng OAuth2TokenGenerator.
- [ ] OAuth2Authorization được lưu đúng.
- [ ] Token response giữ cấu trúc OAuth chuẩn.

### Trước production

- [ ] Có test parsing, invalid grant, wrong client, wrong audience và replay.
- [ ] Có concurrency test cho grant one-time.
- [ ] Resource Server xác minh audience và quyền.
- [ ] Access token có TTL tối thiểu và sender constraint khi phù hợp.
- [ ] Refresh token có policy riêng và rotation/sender constraint phù hợp.
- [ ] Log/audit không chứa credential thô.
- [ ] Có metrics, alert, runbook và kế hoạch deprecation.

### Kiến thức cốt lõi

Custom grant là một **extension của quy trình cấp access token**, không phải cách viết lại client authentication, scope, token claims hoặc user login. Trước khi tạo grant mới, hãy kiểm tra các chuẩn đã có: Authorization Code + PKCE, Client Credentials, Device Authorization, JWT Bearer, Token Exchange, RAR, Resource Indicators và PAR.

Nếu thật sự cần custom grant, RFC 6749 yêu cầu một URI tuyệt đối duy nhất cho grant type; các token endpoint parameter bổ sung phải tuân theo quy tắc đăng ký tương ứng. Client phải xác thực độc lập với grant credential. Authorization Server cần xác minh issuer, audience, thời hạn, client binding, replay và quyền trước khi phát token.

Trong Spring Authorization Server, triển khai qua **AuthenticationConverter**, **AuthenticationProvider** và cấu hình **Token Endpoint**. Provider kiểm tra grant type được RegisteredClient cho phép, tạo token context, dùng OAuth2TokenGenerator và lưu OAuth2Authorization. Giữ token response chuẩn, giới hạn audience/scope, công bố metadata và kiểm thử cả Resource Server. Custom grant chỉ nên được triển khai khi semantics cấp quyền thực sự mới và có thể được quản lý như một protocol contract lâu dài.

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework, Sections 4.5 and 8.2–8.5](https://www.rfc-editor.org/rfc/rfc6749.html)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html)
- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628.html)
- [RFC 7523 — JSON Web Token Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523.html)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html)
- [RFC 9396 — OAuth 2.0 Rich Authorization Requests](https://www.rfc-editor.org/rfc/rfc9396.html)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707.html)
- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126.html)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449.html)
- [Spring Authorization Server 1.5.8 — How-to: Implement an Extension Authorization Grant Type](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-ext-grant-type.html)
- [Spring Authorization Server 1.5.8 — OAuth2 Token Endpoint](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
