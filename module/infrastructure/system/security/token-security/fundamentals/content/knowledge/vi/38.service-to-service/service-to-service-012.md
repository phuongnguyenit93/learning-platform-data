# Không dùng user token làm service secret tùy tiện

## 1. Bối cảnh và mục tiêu

Trong một hệ thống microservices, service A thường gọi service B bằng HTTP, gRPC hoặc qua message queue. Nếu A đang xử lý yêu cầu của người dùng, lập trình viên dễ nhìn thấy một access token trong request và cho rằng có thể tận dụng token này làm credential cho mọi lời gọi nội bộ. Một biến thể nguy hiểm hơn là lấy token của một tài khoản quản trị, gắn vào cấu hình của service hoặc lưu vào bộ nhớ đệm để dùng cho cron job. Các cách làm này trộn lẫn **quyền được cấp cho người dùng** với **danh tính của một workload**, khiến việc phân quyền, thu hồi và điều tra sự cố trở nên không đáng tin cậy.

Trong chương **Service to service** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, bài học này giải thích tại sao **không dùng user token làm service secret tùy tiện**. Nội dung liên hệ mô hình tin cậy, vòng đời token, JWT và opaque token, access token và refresh token, OAuth 2.0/OIDC, audience, scope, phát hành, xác minh, lưu trữ, thu hồi và phòng chống token bị đánh cắp hoặc phát lại.

Sau bài học, bạn có thể:

1. Phân biệt **user access token**, **service access token**, **client credential** và **workload identity**.
2. Giải thích vì sao user token không phải một secret ổn định để service dùng lâu dài hoặc chia sẻ cho nhiều service.
3. Chọn giữa **client credentials**, **token relay có kiểm soát**, **token exchange/on-behalf-of** và cơ chế ủy quyền riêng cho tác vụ bất đồng bộ.
4. Thiết kế xác thực và phân quyền theo **issuer, audience, scope, chủ thể, actor** và dữ liệu nghiệp vụ.
5. Nhận diện lỗi bảo mật, xử lý vòng đời credential, quản lý log/cache và kiểm thử lời gọi service-to-service.

## 2. Hiểu đúng các loại credential

Không phải token nào cũng có cùng mục đích. Cần phân biệt **ai là bên được xác thực**, **token được cấp cho resource server nào** và **quyền được sử dụng trong ngữ cảnh nào**.

| Thành phần | Đại diện cho điều gì? | Nơi sử dụng hợp lệ | Điều cần nhớ |
| --- | --- | --- | --- |
| **User access token** | Quyền truy cập tài nguyên được cấp trong ngữ cảnh một người dùng và client | Resource server có **audience** phù hợp, trong phạm vi scope/quyền đã cấp | Có hạn dùng; có thể bị thu hồi; không đồng nghĩa với danh tính workload. |
| **Service access token** | Quyền truy cập tài nguyên được cấp cho OAuth client/workload, thường qua client credentials | API có audience phù hợp và chấp nhận quyền của service | Không mặc nhiên đại diện cho người dùng cuối. |
| **Client credential** | Bằng chứng để OAuth client xác thực với authorization server: client secret, private key, chứng chỉ... | Token endpoint hoặc kênh xác thực client được cho phép | Phải bảo vệ và xoay vòng; không được lấy user access token thay thế một cách tùy tiện. |
| **ID token (OIDC)** | Thông tin về lần xác thực người dùng dành cho OIDC client | Client phù hợp, theo đúng luồng OIDC | Không phải credential để gọi API nghiệp vụ. |
| **Refresh token** | Credential dùng để xin access token mới theo quyền và cơ chế được cấp | OAuth client được phép giữ và dùng refresh token | Không chuyển tới downstream như access token hoặc service secret. |
| **Workload identity** | Danh tính của tiến trình, pod, VM hoặc service trên hạ tầng | Xác thực giữa workloads hoặc xin credential phù hợp từ STS | Có thể dựa trên mTLS, federation, SPIFFE/SVID, managed identity, v.v.; phải ràng buộc đúng workload. |

Access token có thể là **JWT** tự chứa claims được ký hoặc **opaque token** cần introspection với authorization server. Định dạng không làm thay đổi mục đích: JWT của người dùng vẫn là user token, còn opaque token cấp cho workload vẫn có thể là service token. Đọc được payload JWT **không đồng nghĩa** đã xác minh chữ ký, audience hoặc quyền.

### 2.1. Access token là credential có phạm vi, không phải password chung

Một access token được phát hành dựa trên quyết định của authorization server: cho client nào, truy cập resource nào, với scope nào và thời hạn nào. Với bearer token, bên có được chuỗi token có thể thử sử dụng nó trong khi còn hiệu lực. Vì vậy token **là dữ liệu bí mật cần bảo vệ**, nhưng điều đó **không làm nó trở thành service secret thích hợp**.

Service secret thường được hiểu là credential được cấp riêng cho một ứng dụng để xác thực chính ứng dụng đó. User token được cấp trong một phiên hoặc ngữ cảnh ủy quyền của người dùng và thường gắn với một tập quyền, resource và thời hạn khác. Dùng user token như service secret làm sai lệch ít nhất hai câu hỏi: **ai thực sự đang gọi?** và **quyền này dựa trên sự ủy quyền nào?**

### 2.2. Phân biệt chủ thể, client, actor và audience

- **Subject**: danh tính mà token phản ánh, ví dụ một user; cách diễn giải claim `sub` phụ thuộc issuer và profile token.
- **OAuth client**: ứng dụng được authorization server nhận diện. Claim như `client_id` hoặc `azp` có thể dùng theo profile, nhưng không tự mang nghĩa “service nào hiện cầm token”.
- **Actor**: thành phần hành động thay subject, ví dụ Orders Service gọi Inventory theo ủy quyền; một profile delegation có thể thể hiện thông tin actor trong claim `act`.
- **Audience**: resource server mà token được phát hành để sử dụng, thường thể hiện qua `aud`. Token cấp cho Orders API không tự hợp lệ cho Payments API.
- **Scope**: phạm vi quyền được cấp ở mức API, ví dụ `orders:read`; không thay thế kiểm tra quyền trên từng bản ghi hoặc tenant.

Không dùng các header do client tự đặt như `X-User-Id` hoặc `X-Roles` để thay cho claims đã xác minh. Nếu API nội bộ nhận danh tính từ header, hệ thống cần kiểm soát nơi tạo header, xóa giá trị từ nguồn không tin cậy và xác thực chặng truyền nội bộ.

## 3. Anti-pattern: biến token của người dùng thành khóa dùng chung

Giả sử hệ thống có một tài khoản quản trị viên quản lý đơn hàng. Người triển khai đăng nhập bằng tài khoản đó, sao chép access token rồi đặt trong cấu hình của `orders-worker`:

~~~yaml
# SAI: Ví dụ phản diện, tuyệt đối không áp dụng trong hệ thống thật
inventory:
  base-url: https://inventory.internal.example
  authorization-header: "Bearer <copied-admin-user-token>"
~~~

Một batch job chạy hằng đêm đọc header cấu hình này và dùng nó để gọi Inventory API. Kể cả khi request lúc đầu thành công, thiết kế có nhiều lỗi nền tảng:

1. **Sai danh tính:** Inventory thấy hoạt động gắn với người quản trị, không phải batch worker thực sự phát sinh công việc.
2. **Sai vòng đời:** user token hết hạn, người dùng đăng xuất hoặc bị thu hồi quyền; job có thể hỏng bất ngờ hoặc tiếp tục chạy với quyền cũ tùy cơ chế thu hồi.
3. **Quyền quá rộng:** token quản trị có thể chứa quyền không cần cho đồng bộ tồn kho; nếu lộ token, kẻ tấn công có nhiều quyền hơn mức công việc yêu cầu.
4. **Rò rỉ và nhân bản:** cùng token bị sao chép sang cấu hình, container, pipeline, nhiều service, trace hoặc log; phạm vi bị ảnh hưởng tăng theo số nơi lưu.
5. **Không có giới hạn resource:** token dành cho resource khác có thể bị API không cấu hình đúng audience chấp nhận.
6. **Khó audit:** không phân biệt được thao tác thực hiện trực tiếp bởi quản trị viên với thao tác tự động của worker.
7. **Phụ thuộc cá nhân:** tài khoản bị khóa, đổi vai trò, nghỉ việc hay reset credential làm ngừng dịch vụ; việc “giữ token mãi mãi” còn nguy hiểm hơn.

Không thể sửa thiết kế này bằng cách kéo dài thời hạn user token lên nhiều tháng hoặc xin scope `admin:*`. Điều đó làm tăng nguy cơ sử dụng trái phép. Batch worker phải sử dụng **danh tính và quyền riêng của workload**, còn tác vụ cần thực sự đại diện người dùng phải có **cơ chế delegation có kiểm soát**.

### 3.1. Những biến thể khó nhận ra

| Anti-pattern | Vì sao sai | Phương án thay thế |
| --- | --- | --- |
| Ghi user token vào `.env`/ConfigMap rồi cho mọi pod sử dụng | Token gắn với phiên/người dùng; cấu hình bị sao chép và khó thu hồi | Workload identity hoặc OAuth client credentials cho mỗi service. |
| A gửi nguyên user token sang B, C, D chỉ vì “cùng mạng nội bộ” | Token không nhất thiết đúng audience; mở rộng bề mặt lộ credential | Relay chỉ khi được cấp đúng đích; cần khác đích thì token exchange. |
| Dùng refresh token người dùng để worker tự xin token mỗi đêm | Tạo một phiên người dùng lâu dài trong service; quyền refresh và lưu giữ có rủi ro cao | Dùng service account, workload federation hoặc quy trình ủy quyền cho job riêng. |
| Gửi token qua URL: `?access_token=...` | Token có thể rơi vào proxy log, history, referer, analytics | Dùng cơ chế truyền credential đã chuẩn hóa, thường header Authorization trên TLS. |
| Lấy token user A từ cache để xử lý request user B | Cross-user/cross-tenant privilege leakage | Khóa cache theo ngữ cảnh đầy đủ hoặc không cache credential người dùng. |
| Dùng ID token làm bearer token gọi service | Nhầm chứng cứ xác thực client với access token cho API | Chỉ chấp nhận access token đúng loại/profile và audience. |
| Dùng service token rồi tự gửi `X-User-Id: admin` để “thay mặt user” | Không có chứng cứ ủy quyền từ subject, dễ impersonation | Delegation/actor model qua STS, kiểm policy ở downstream. |
| Lấy JWT Kubernetes service account mặc định làm token cho mọi API | JWT đó thường được cấp cho một audience xác định; không tự hợp lệ cho API ứng dụng | Dùng workload federation để xin access token có audience phù hợp; xác minh token theo profile. |

## 4. Mô hình ranh giới tin cậy giữa các service

Ví dụ người dùng truy vấn đơn hàng, Orders Service cần hỏi Inventory Service:

~~~mermaid
flowchart LR
    U[Client / Người dùng] -->|user access token; aud=orders-api| O[Orders Service]
    O -->|xác minh token và quyền truy cập order| P{Mục đích gọi Inventory?}
    P -->|Nhiệm vụ nội bộ độc lập user| M[Workload identity / client credentials]
    P -->|Cần quyền user| D[Token exchange / delegation]
    M -->|service token; aud=inventory-api| I[Inventory Service]
    D -->|delegated token; aud=inventory-api| I
    I -->|kiểm token và quyền trên dữ liệu| R[Response]
~~~

Trước khi chọn credential, cần trả lời:

1. **Service B có cần quyền của người dùng không?** Nếu không, dùng danh tính riêng của service A.
2. **Nếu có, người dùng đã ủy quyền cho A gọi B trong phạm vi nào?** Chuyển tiếp token chỉ hợp lệ khi token đã dành cho B; nếu cần token khác, yêu cầu STS exchange/on-behalf-of theo policy.
3. **B cần xác minh điều gì?** Dù nội bộ, B phải kiểm issuer, audience, thời hạn, scope/quyền, tenant, actor và quyền trên dữ liệu.
4. **Ai chịu trách nhiệm cho tác vụ tương lai?** Nếu công việc kéo dài sau khi HTTP request kết thúc, cần quyền và danh tính được thiết kế cho job, không giữ token ngắn hạn để dùng vô thời hạn.

**Authorization server** xác minh và cấp token; **Service A** xác thực người gọi và quyết định tác vụ; **Service B** là resource server cuối, chịu trách nhiệm kiểm quyền trên tài nguyên của mình. mTLS hoặc private network bảo vệ kênh và danh tính workload, nhưng không tự quyết định user có quyền sửa đơn hàng hay không.

## 5. Chọn phương án credential theo bản chất công việc

| Tình huống | Phương án đề xuất | Chủ thể/quyền mà B đánh giá |
| --- | --- | --- |
| Service đọc thông số cấu hình, health hoặc metadata nội bộ | **Client credentials** hoặc workload identity được STS chuyển thành token có audience B | Danh tính service; scope tối thiểu cho B. |
| Worker đồng bộ tồn kho theo chính sách hệ thống | **Service token** dành riêng cho worker | Danh tính worker, chính sách workload, giới hạn dữ liệu cần xử lý. |
| A gọi B **thay user** đang thực hiện request | **Token exchange/on-behalf-of** khi STS hỗ trợ, hoặc cơ chế delegation được duyệt | Subject người dùng + actor A (nếu profile hỗ trợ), audience B, scope hẹp. |
| A chuyển tiếp token mà client đã được cấp **cho chính B** | **Token relay** có kiểm soát, nếu policy và sender constraint cho phép | Chính access token dành cho B; B kiểm lại mọi điều kiện. |
| Batch job chạy sau nhiều giờ, user token đã hết hạn | **Job authorization** đã ghi nhận tại thời điểm tạo + danh tính worker, hoặc cơ chế delegated grant có vòng đời rõ ràng | Workload identity và quyền thực thi job; nếu cần user delegation, phải kiểm lại theo chính sách. |
| C gọi D trong chuỗi dài A → B → C → D | **Per-hop token** hoặc exchange từng chặng theo policy | Token chỉ có audience/quyền cần cho D; actor chain được STS kiểm soát. |

**Không có một lựa chọn đúng cho mọi dịch vụ.** Chọn client credentials khi hành động thuộc quyền của chính service; chọn delegation khi hành động phải được ủy quyền bởi người dùng. Việc “trong request có sẵn token” chỉ là một chi tiết kỹ thuật, không phải căn cứ quyết định mô hình ủy quyền.

### 5.1. Service token bằng client credentials

Với OAuth 2.0 client credentials, một OAuth client đại diện Orders Worker xác thực với authorization server và xin access token cho Inventory API:

~~~mermaid
sequenceDiagram
    autonumber
    participant W as Orders Worker
    participant AS as Authorization Server
    participant I as Inventory API
    W->>AS: Client authentication + client_credentials; resource=inventory-api
    AS->>AS: Kiểm danh tính workload và scope được cấp
    AS-->>W: Service access token; aud=inventory-api
    W->>I: GET /inventory/summary + Bearer service token
    I->>I: Kiểm issuer, audience, scope và quyền workload
    I-->>W: Thông tin được phép
~~~

Request minh họa:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <workload-client-authentication>

grant_type=client_credentials&scope=inventory%3Aread&resource=https%3A%2F%2Finventory.example.internal%2F
~~~

Đây là ví dụ phụ thuộc authorization server: tham số `resource` theo RFC 8707 chỉ hoạt động khi server hỗ trợ; nhiều hệ thống dùng `audience` hoặc ánh xạ client/scope qua cấu hình riêng. Việc xác thực client có thể dùng mTLS hoặc `private_key_jwt` thay vì Basic, tùy năng lực STS. Chỉ sử dụng HTTPS, không log body/header chứa credential. Service token đầu ra có audience và scope theo chính sách của STS, không được tự chọn bằng cách sửa JWT.

Tại Inventory API, actor là workload/client đã được cấp quyền. Nếu nghiệp vụ thực sự cần biết **người dùng nào cho phép thao tác**, client credentials đơn thuần chưa đủ; phải có cơ chế delegation hoặc record ủy quyền riêng đã được thẩm định.

### 5.2. Token exchange cho lời gọi thay người dùng

Giả sử client có user access token cho `orders-api` và Orders cần gọi Inventory để trả thông tin người dùng có quyền xem. STS hỗ trợ **OAuth 2.0 Token Exchange (RFC 8693)**:

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User Client
    participant O as Orders API (OAuth Client tại chặng sau)
    participant AS as STS
    participant I as Inventory API
    U->>O: Bearer user-token; aud=orders-api
    O->>O: Xác minh token, scope orders:read, quyền trên order
    O->>AS: Xác thực Orders + subject_token=user-token
    Note over O,AS: audience=inventory-api; scope=inventory:read
    AS->>AS: Kiểm subject, actor/client, policy và target
    AS-->>O: delegated-token; aud=inventory-api
    O->>I: Bearer delegated-token
    I->>I: Xác minh token mới, actor nếu có, quyền dữ liệu
    I-->>O: Kết quả được phép
    O-->>U: Response
~~~

Request minh họa (body URL encoded; các dòng ghép lại thành một body thật):

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <orders-client-authentication>

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange
&subject_token=<verified-user-access-token>
&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&requested_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&audience=inventory-api
&scope=inventory%3Aread
~~~

Các thành phần bắt buộc cần hiểu:

- `subject_token` là token của chủ thể được đưa vào phép exchange. **Không** gửi tùy ý ID token hay refresh token nếu STS không hỗ trợ đúng loại/hồ sơ.
- `subject_token_type` mô tả loại token vào; `requested_token_type` (tùy chọn) mô tả loại token mong muốn. **STS** quyết định kết quả dựa trên policy.
- `actor_token` và `actor_token_type` có thể xuất hiện trong luồng có actor rõ ràng; hai tham số này khác **client authentication** của Orders.
- `audience` hoặc `resource` chỉ định API đích; `scope` yêu cầu quyền tương ứng. STS không được nâng quyền tùy ý chỉ vì Orders yêu cầu.
- Token trả về có thể là JWT hoặc opaque access token; Inventory phải tự kiểm tra. Nếu STS phát hành claim `act` theo delegation profile, Inventory áp policy tương ứng; không tự chèn hoặc tin actor do Orders khai báo ngoài hợp đồng tin cậy.

Một phản hồi thành công có thể như sau:

~~~json
{
  "access_token": "<new-limited-access-token>",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 180,
  "scope": "inventory:read"
}
~~~

Token mới **không** phải bản sao để gửi tới mọi downstream. Nó chỉ nên dùng cho đúng Inventory API, với quyền và thời gian sống hẹp. Token exchange cũng **không mặc nhiên thu hồi** subject token; vòng đời từng token phải được thiết kế và kiểm chứng riêng.

### 5.3. Token relay: có lúc hợp lệ, nhưng phải chứng minh điều kiện

Chuyển tiếp cùng một user access token qua chặng A → B **có thể hợp lệ** nếu token ban đầu được issuer cấp cho B (đúng audience, scope, profile), hệ thống xác định rõ B là intended recipient, A được phép relay và yêu cầu về sender-constrained token được đáp ứng. Downstream B luôn xác minh lại token. Relay không cho phép A giữ token để dùng cho nhu cầu tương lai không liên quan hoặc chuyển đến host do client kiểm soát.

Không thể sửa audience/scope trong payload JWT để tạo “token mới”, vì sửa claim làm chữ ký không hợp lệ; với opaque token thì còn không thể suy ra claims từ chuỗi token. Nếu token ban đầu chỉ dành cho A, cần xin token phù hợp cho B thay vì bỏ kiểm tra audience.

## 6. Các bước xác minh trước lời gọi service-to-service

### 6.1. Tại service nhận request người dùng

Khi Orders nhận bearer access token từ client:

1. Kiểm syntax credential đúng giao thức; không nhận token mơ hồ từ URL hoặc header tùy ý.
2. Với **JWT**, kiểm chữ ký, thuật toán được allowlist, JWKS/key từ issuer tin cậy, `iss`, `exp`, `nbf` (nếu có), `aud`, token type/profile và claims bắt buộc khác.
3. Với **opaque token**, dùng introspection RFC 7662 được bảo vệ; kiểm `active` và các attributes đã được STS cung cấp. Timeout introspection không được coi là token hợp lệ.
4. Kiểm `scope` / policy cho action, cùng tenant và quyền trên đơn hàng cụ thể. Scope `orders:read` **không tự cấp quyền** xem mọi order của mọi người.
5. Chỉ sử dụng **verified principal/context** khi quyết định có gọi service B thay người dùng. Không lấy danh tính từ claims trước khi xác thực hoặc `X-User-Id` do client đưa vào.

Nếu token đến từ user nhưng nội dung xử lý là tác vụ hệ thống không thuộc quyền user, phải tách luồng đó khỏi quyền user và dùng workload identity đúng mục đích. Không dùng token của người dùng đặc quyền nhất để làm “giấy thông hành” cho toàn bộ mạng.

### 6.2. Tại STS/authorization server

Với token exchange, STS kiểm **hai phía**: tính hợp lệ và giới hạn của subject token, **và** danh tính/ủy quyền của service yêu cầu exchange. Chính sách nên xét cả issuer, subject, client/actor, tenant, resource đích, scope, token type, token binding và điều kiện delegation. Không có lý do hợp lệ để cấp `inventory:admin` chỉ vì Orders đang giữ token người dùng có `orders:read`.

Với client credentials, STS chỉ cấp các resource/scope mà workload đã được đăng ký và được phép. Nó không nên lấy user ID do client tự nhập làm chủ thể của service token.

### 6.3. Tại resource server đích

Inventory API kiểm token **được gửi đến chính nó**: issuer được tin cậy, chữ ký/introspection, audience Inventory, thời gian hiệu lực, scope, caller/client/actor theo policy và quyền trên dữ liệu. **Không tin chỉ vì lời gọi đến từ mạng nội bộ** hoặc qua API Gateway.

Với token nhiều audience hoặc quyền rộng, cần đánh giá khả năng lộ thông tin giữa các service; ưu tiên audience hẹp theo resource. Nếu request nhận service token nhưng thao tác yêu cầu sự đồng ý hoặc quyền của user, Inventory phải có chính sách chặn hoặc cơ chế ủy quyền bổ sung.

## 7. Ví dụ thiết kế Java/Spring theo hai kiểu lời gọi

### 7.1. Batch job: danh tính riêng của service

Ví dụ cấu hình khái niệm một OAuth2 Client trong ứng dụng Java/Spring (không chứa secret thật):

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          internal-identity:
            token-uri: https://identity.example.com/oauth2/token
        registration:
          inventory-worker:
            provider: internal-identity
            client-id: orders-worker
            client-secret: <injected-from-secret-manager>
            authorization-grant-type: client_credentials
            scope:
              - inventory:read
~~~

Cấu hình trên minh họa cách phân biệt service identity. Trong hệ thống thực tế, inject client secret qua secret manager/biến môi trường được bảo vệ hoặc dùng `private_key_jwt`/mTLS/workload federation nếu hạ tầng hỗ trợ. URI token endpoint phải có TLS đáng tin; audience hoặc resource-specific access token cần được kiểm theo khả năng của authorization server. Không tự suy rằng chỉ khai báo scope là token sẽ đúng audience Inventory.

Pseudocode Java tách luồng machine-to-machine khỏi bearer token của người dùng:

~~~java
// Pseudocode: ServiceTokenProvider là abstraction được triển khai bằng
// Spring OAuth2 Authorized Client Manager hoặc workload token broker.
// InventoryClient chỉ nhận token được cấp cho inventory-api.
public final class InventorySyncJob {
    private final ServiceTokenProvider tokenProvider;
    private final InventoryClient inventoryClient;

    public InventorySyncJob(ServiceTokenProvider tokenProvider,
                            InventoryClient inventoryClient) {
        this.tokenProvider = tokenProvider;
        this.inventoryClient = inventoryClient;
    }

    public void syncInventory() {
        AccessToken token = tokenProvider.forWorkload(
            "orders-worker", "inventory-api", "inventory:read");
        inventoryClient.readSummaryWith(token); // TLS + verify audience
        // Không giữ token của user trong cấu hình hoặc job metadata.
    }
}
~~~

`AccessToken` trong ví dụ là đối tượng chứa credential được quản lý trong bộ nhớ ngắn hạn; các API trên là abstraction, **không phải lớp Spring chuẩn để sao chép và biên dịch nguyên xi**. Triển khai phải có timeout, cache TTL hợp lý, tự xin token mới khi hết hạn và không in credential trong `toString()`/log.

### 7.2. Request thay người dùng: exchange token trước khi gọi downstream

Orders Service xác thực JWT hoặc opaque token đầu vào trong **security layer**, sau đó controller nhận một context **đã được kiểm chứng**:

~~~java
// Pseudocode; tokenExchangeClient xác thực workload Orders với STS.
// Gọi sau khi đã xác thực token user và quyền xem order ở Orders API.
public Mono<InventoryView> getInventoryForOrder(
        VerifiedUserContext userContext, String sku) {

    return tokenExchangeClient.exchange(
            userContext.verifiedAccessToken(),  // chỉ trong phạm vi request
            "inventory-api",
            "inventory:read")
        .flatMap(inventoryToken ->
            inventoryWebClient.get()
                .uri("/items/{sku}", sku)
                .headers(headers -> headers.setBearerAuth(inventoryToken.value()))
                .retrieve()
                .bodyToMono(InventoryView.class));
}
~~~

Đoạn code dành cho **bearer token** đã được STS trả về; nếu token_C dùng DPoP/mTLS binding thì client phải gửi proof/chứng chỉ phù hợp. Không log body request token exchange, response STS hay header `Authorization`. STS có thể từ chối exchange dù user token hợp lệ; khi đó request **không được fallback** sang việc dùng user token sai audience trực tiếp tại Inventory.

### 7.3. Phản ví dụ cần loại bỏ

~~~java
// SAI: token từ request người dùng bị sử dụng như service secret lâu dài.
class BadInventoryClient {
    static String sharedBearer; // cố định, dùng chung giữa nhiều người dùng

    void remember(String userToken) {
        sharedBearer = userToken; // rò giữa request, user, tenant và job
    }

    void callInventory() {
        // Authorization: Bearer sharedBearer  (SAI)
    }
}
~~~

Rủi ro của biến tĩnh ở đây gồm race condition, cross-user leakage, không có TTL/ủy quyền theo từng mục đích, và khả năng đọc token ở heap dump. Đừng giải quyết bằng cách thêm khóa đồng bộ; phải **đổi mô hình credential** theo đúng đối tượng gọi và ngữ cảnh quyền.

## 8. Vòng đời, lưu trữ, cache và thu hồi

### 8.1. Sở hữu và lưu trữ token

User access token chỉ nên tồn tại ở những thành phần được thiết kế để nhận hoặc dùng nó. Nếu A cần exchange, giữ subject token trong phạm vi request và chỉ chuyển tới STS đã cấu hình tin cậy; không đưa token vào hàng đợi, cơ sở dữ liệu, URL, trace, exception, access log hoặc service metadata.

Service credential như client secret/private key phải được cấp **riêng cho workload**, đưa vào qua secret manager hoặc cơ chế runtime phù hợp, giới hạn quyền đọc và có rotation. Một dịch vụ bị xâm nhập không nên có quyền đọc credential của tất cả dịch vụ khác. Workload identity có thể giảm nhu cầu lưu secret dài hạn, nhưng vẫn đòi hỏi chính sách cấp quyền, xoay vòng và kiểm soát vòng đời chứng thực.

### 8.2. Token có thời hạn; cache không biến nó thành service secret

Access token ngắn hạn có thể được cache để tránh gọi STS quá thường xuyên. Cache token máy cần phân biệt client/workload, issuer, resource/audience, scope, binding và policy liên quan. Cache token delegation còn cần phân biệt **subject, session, actor, tenant, audience, scope và ngữ cảnh ủy quyền** theo chính sách; tuyệt đối không cache “theo một user ID” nếu nhiều phiên/tenant hoặc actor có quyền khác nhau.

Không lưu **raw access token** trong cache key, metrics hoặc structured log. Nếu cần một định danh kỹ thuật để đối chiếu, dùng cơ chế tham chiếu/hàm bảo vệ đã được đánh giá và quản lý khóa, tránh biến fingerprint thành dữ liệu theo dõi không kiểm soát. Thời gian sống cache không vượt thời hạn token (trừ khoảng dự phòng) và phải xử lý thay đổi quyền, thu hồi theo yêu cầu rủi ro.

### 8.3. Refresh token không phải lối tắt cho job

Refresh token thuộc một OAuth client và một chính sách cấp quyền nhất định. Việc sao chép refresh token người dùng sang cron job cho phép job duy trì quyền thay user lâu dài, tạo nguy cơ cao về lưu trữ và thu hồi. Chỉ sử dụng refresh token nếu ứng dụng **được cấp phép rõ ràng** cho luồng đó, có biện pháp bảo vệ token, rotation, revocation và giới hạn quyền phù hợp. Với công việc thuần service, ưu tiên xin service access token mới theo workload identity/client credentials.

### 8.4. Thu hồi và quyền thay đổi

Token bị thu hồi ở authorization server **không có nghĩa** mọi resource server đang tự xác minh JWT offline lập tức biết token không còn hiệu lực. Với opaque token, introspection có thể phản ánh trạng thái `active` nhưng cache vẫn tạo khoảng trễ. Token được exchange cũng có thể có vòng đời riêng, không mặc nhiên hết hiệu lực cùng subject token. Thiết kế token ngắn hạn, kiểm tra trạng thái/denylist hoặc sự kiện thu hồi khi yêu cầu rủi ro đòi hỏi; tránh hứa hẹn “logout là tất cả token lập tức vô hiệu” khi hệ thống chưa có cơ chế chứng minh điều đó.

## 9. Sender-constrained token, replay và rủi ro trong mạng nội bộ

Bearer token thông thường có thể bị sử dụng lại bởi bên chiếm được chuỗi token cho đến khi hết hạn hoặc bị thu hồi. **DPoP** (RFC 9449) và **mTLS-bound access token** (RFC 8705) có thể ràng buộc token với bằng chứng sở hữu khóa hoặc chứng chỉ, giảm nguy cơ chỉ sao chép token rồi replay thành công. Nhưng token bị ràng buộc với khóa của người dùng **không thể** tùy tiện relay sang một workload khác.

Một số hệ thống cần exchange để STS cấp token_C gắn với workload B, hoặc cần thiết kế rõ ai tạo DPoP proof cho HTTP method/URI ở mỗi hop. Không được sao chép DPoP proof dành cho một URL rồi dùng cho URL khác, hoặc bỏ qua kiểm tra binding để “service nội bộ gọi cho tiện”.

Mạng nội bộ và service mesh không đảm bảo token đúng scope/audience; TLS/mTLS không bảo đảm user được phép thao tác trên tài nguyên cụ thể. Cần kết hợp **xác thực workload**, **access token đúng resource** và **kiểm tra quyền nghiệp vụ** tại downstream.

## 10. Thiết kế an toàn cho asynchronous job và event-driven flow

Một request của user có thể kích hoạt công việc kéo dài nhiều phút hoặc nhiều ngày. Sai lầm phổ biến là đẩy cả bearer access token vào queue để worker có thể “tiếp tục quyền user”:

~~~json
{
  "event_type": "RebuildInventoryReport",
  "user_access_token": "<copied-user-token>",
  "scheduled_at": "2026-11-23T08:00:00Z"
}
~~~

Thông điệp trên **không an toàn** vì queue, dead-letter queue, replay, log và backup có thể giữ token; token có thể hết hạn trước khi job chạy; worker tái phát token trong ngữ cảnh người dùng đã thay đổi quyền.

Thiết kế tốt hơn là truyền một **job ID** và các tham chiếu dữ liệu tối thiểu:

~~~json
{
  "event_type": "RebuildInventoryReport",
  "job_id": "job_7f21",
  "requested_by_ref": "subject_ref_31",
  "tenant_ref": "tenant_ref_02",
  "policy_ref": "inventory-report-v3",
  "scheduled_at": "2026-11-23T08:00:00Z"
}
~~~

Worker dùng **workload identity của chính nó** để lấy token truy cập Inventory/reporting service. Khi job cần quyền của user đang còn hiệu lực tại thời điểm thực thi, backend phải có chính sách lưu hồ sơ ủy quyền, kiểm lại quyền hoặc xin delegated token theo một cơ chế cho phép tác vụ bất đồng bộ. **Job ID và requested_by_ref không tự là bằng chứng ủy quyền**: đây chỉ là metadata, phải được xác minh và đối chiếu dữ liệu nội bộ tin cậy.

Nếu user rút quyền giữa thời điểm lên lịch và thực thi, hệ thống phải quy định rõ việc hủy, từ chối hoặc tiếp tục job theo chính sách nghiệp vụ và an ninh; không dựa vào việc user token còn tình cờ chưa hết hạn.

## 11. Các nguy cơ và biện pháp bảo vệ

| Nguy cơ | Kịch bản | Biện pháp |
| --- | --- | --- |
| **Token theft / replay** | Sao chép bearer user token từ log hoặc heap rồi gọi API | TLS, không log credential, token ngắn hạn, audience hẹp; sender-constrained token khi phù hợp. |
| **Confused deputy** | Service A dùng quyền user để xin quyền cao ở B | STS kiểm subject + actor/client + target + scope; B thực thi policy. |
| **Cross-user / cross-tenant leakage** | Cache một token chung cho nhiều request | Cô lập context theo user/session/tenant/actor; không dùng shared mutable credential. |
| **Privilege escalation** | Dùng token admin cho job chỉ cần quyền đọc | Workload service token với quyền tối thiểu và credential riêng. |
| **Sai audience** | Token có `aud=orders-api` bị gửi sang `payments-api` | Bắt buộc kiểm audience ở mỗi resource; exchange nếu cần token mới. |
| **Header spoofing** | Gửi `X-User-Id: admin` cùng service token | Chỉ tin danh tính đã được xác thực; lọc header đầu vào; dùng delegation đúng chuẩn. |
| **Refresh-token exposure** | Worker giữ refresh token của user hàng tháng | Dùng service identity cho machine action; hạn chế refresh flow theo client được cấp phép. |
| **Token substitution** | ID token được dùng làm access token | Kiểm token type/profile, audience và mục đích sử dụng. |
| **SSRF / open redirect** | A gửi bearer token tới URL do client quyết định | Allowlist downstream, không forward credential khi redirect sang host lạ. |
| **Expired/revoked token** | Job dùng token lưu nhiều ngày | TTL, xin token mới theo cơ chế đúng, revocation policy và kiểm trạng thái. |
| **Actor attribution sai** | Audit ghi hành động của worker là user trực tiếp | Tách subject/actor/service identity và lưu policy version/correlation ID. |
| **STS outage fallback** | STS lỗi, A gửi token sai audience thẳng tới B | Fail closed; retry có giới hạn; không hạ thấp yêu cầu xác thực. |

### 11.1. Quan sát và audit

Để điều tra sự cố, log có thể ghi **request ID, route/service đích, client/workload ID đã xác minh, audience/scope *được yêu cầu hoặc kết quả kiểm tra*, policy version, decision và mã lỗi chuẩn hóa**. Với lời gọi thay user, lưu subject reference hoặc actor reference theo chính sách tối thiểu hóa dữ liệu; đừng ghi raw claims không cần thiết.

Không log `Authorization`, `Cookie`, `Set-Cookie`, refresh token, ID token, token exchange `subject_token`/`actor_token`, DPoP proof, client secret hoặc response access token. Dữ liệu trong trace và APM cũng phải được scrub. Log **không phải nơi lưu service credential**; việc mask trong UI log không cứu được token đã bị ghi vào kho log thô.

Audit cần phân biệt **gateway cho phép forward** với **downstream cho phép nghiệp vụ**. Một user token hợp lệ có thể được Orders chấp nhận nhưng Inventory từ chối vì tenant của item không khớp; hai quyết định phải được ghi riêng rồi liên kết bằng correlation ID đáng tin cậy.

## 12. Xử lý lỗi đúng ranh giới trách nhiệm

| Trường hợp | Hành vi cần có | Cách diễn giải |
| --- | --- | --- |
| User không có access token hợp lệ khi gọi Orders | Trả 401 theo giao thức bearer | Lỗi xác thực ở chặng client → Orders. |
| User hợp lệ nhưng thiếu quyền xem order | Trả 403 hoặc phản hồi theo policy dữ liệu | Lỗi phân quyền nghiệp vụ cho chủ thể user. |
| Orders có token dành cho Orders nhưng cần gọi Inventory | Dùng token exchange theo policy hoặc service token đúng ngữ cảnh | Không relay token sai audience. |
| STS từ chối client Orders hoặc scope/target exchange | Không gọi Inventory; ghi mã lỗi đã sanitize | Có thể là policy hoặc cấu hình credential của service. |
| STS timeout/5xx khi xin token service | Không fallback sang token người dùng | Lỗi hạ tầng/availability; xử lý timeout, backoff, circuit breaker. |
| Inventory trả 401 cho token_C | Không thử token_B để “chạy tạm” | Kiểm audience, token expiry, issuer, binding, cấu hình STS. |
| Inventory trả 403 cho token_C | Không tự xin scope cao hơn | Quyền của actor/subject hoặc dữ liệu không cho phép. |
| Async job không còn ủy quyền hợp lệ | Từ chối/hủy hoặc xin quyền mới theo policy | Job tồn tại không đồng nghĩa user còn ủy quyền. |

Đối với request tạo/sửa dữ liệu, retry sau timeout chỉ an toàn khi có quy tắc idempotency phù hợp. Không gửi lặp thao tác ghi chỉ vì token exchange đã thành công hoặc vì nghi rằng downstream chưa nhận request.

## 13. Tình huống kiểm thử nên có

| Test case | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| Machine job hợp lệ | Worker xin service token `aud=inventory-api`, scope `inventory:read` | Inventory chấp nhận theo policy workload; không có user token trong job. |
| User token sai audience | Token `aud=orders-api` gửi trực tiếp Inventory | Inventory từ chối; không tắt audience validator. |
| Relay hợp lệ có giới hạn | Token được cấp đúng cho B, còn hiệu lực và đúng scope | B xác minh lại token và chỉ cho phép hành động phù hợp. |
| Exchange hợp lệ | Orders xác minh token user và được STS cấp token_C | C nhận token_C với audience/scope hẹp; audit phản ánh subject/actor khi có. |
| STS từ chối exchange | Orders yêu cầu target/scope không cho phép | Không có token_C; không fallback sang token_B. |
| Token hết hạn | User token hoặc service token hết hạn | 401 từ resource liên quan; không coi token expired là service secret còn dùng được. |
| JWT giả chữ ký | JWT bị sửa `sub` hoặc `scope` | B từ chối, không lấy claims chưa kiểm vào principal/audit. |
| Opaque token inactive | Introspection trả `active=false` | Từ chối xác thực, không gọi downstream. |
| Opaque introspection timeout | Authorization server không phản hồi | Fail closed; không coi token valid theo mặc định. |
| ID token bị dùng nhầm | Client gửi ID token cho API nghiệp vụ | Từ chối theo profile/type/audience. |
| Cross-user cache | User A gọi rồi user B gọi cùng URL | Không tái sử dụng user token của A cho B. |
| Cross-tenant cache | Cùng user đổi tenant | Không sử dụng delegated token có tenant khác. |
| Job chậm/đã bị thu hồi quyền | Tác vụ chạy sau khi user đổi quyền | Worker thực thi quy tắc reauthorization/delegation; không dựa vào token cũ. |
| Claim actor giả | Client gửi `X-User-Id` hoặc `act` tùy ý | Không biến dữ liệu chưa kiểm thành quyền của subject/actor. |
| Service credential bị thu hồi | Workload credential/key xoay vòng | Service xin token lại theo danh tính hiện tại; token cũ bị xử lý theo policy. |
| DPoP token relay sai chặng | Sao chép proof user cho URL/chặng khác | B từ chối vì binding/proof không hợp lệ; xử lý theo thiết kế exchange. |
| STS unavailable | Token endpoint timeout | Không bypass xác thực; ghi lỗi hạ tầng đã sanitize. |
| Token leak canary | Kiểm access log, trace, heap dump tùy môi trường test | Không xuất hiện raw bearer token/refresh token/client secret trong log và thông báo lỗi. |
| SSRF / redirect | URL upstream do client điều khiển trỏ ra host ngoài | A không forward credential đến host không tin cậy. |
| Nhiều hop A → B → C | B cần gọi C trong cùng quy trình | Mỗi chặng có audience, scope và policy tương ứng; không truyền user token tràn lan. |

Kiểm thử HTTP status thôi chưa đủ. Nên quan sát **lời gọi thực tế** đến authorization server và downstream: credential nào được gửi, tới hostname nào, có đúng audience không, có bị log/redirect không, và khi STS lỗi ứng dụng có chuyển sang phương án không an toàn hay không.

## 14. Checklist triển khai

- [ ] Phân loại từng lời gọi là **machine action** hay **delegated user action**; không chọn token chỉ vì token đang có sẵn trong request.
- [ ] Cấp **workload identity/credential riêng** và quyền tối thiểu cho các job/service chạy độc lập.
- [ ] Dùng **client credentials** khi hành động thuộc service; dùng **token exchange/delegation** theo chính sách khi hành động thuộc user.
- [ ] Chỉ relay user access token khi token đúng intended audience, scope, policy và sender constraint của downstream.
- [ ] Chặn sử dụng **ID token** và **refresh token** như access token của service.
- [ ] Xác minh JWT/opaque token, issuer, audience, hạn dùng, token type và quyền nghiệp vụ ở từng resource server.
- [ ] Không tin claims chưa xác thực, header giả danh tính hoặc IP nội bộ để thay thế kiểm tra ủy quyền.
- [ ] Không đặt user token trong config, image, secret dùng chung, queue, DB, URL, analytics, log, trace hoặc static variable.
- [ ] Đặt TTL/cache key phù hợp với subject, actor, tenant, resource, scope và token binding; có chính sách rotation/revocation.
- [ ] Bảo vệ mTLS/DPoP proof, khóa và token theo từng chặng; tránh reuse proof dành cho URL khác.
- [ ] Fail closed khi STS/PDP/introspection lỗi; không tự hạ cấp sang một token sai audience.
- [ ] Kiểm thử cross-user/cross-tenant, stale permission, token leak, replay, SSRF và job bất đồng bộ.

## 15. Điều cần ghi nhớ và tài liệu tham khảo

**User access token** chứng minh một ngữ cảnh truy cập đã được cấp cho người dùng/client đối với một hoặc vài tài nguyên xác định; nó **không phải** mật khẩu của workload và không thể thay thế service identity một cách tùy tiện. Khi service tự thực hiện nhiệm vụ, hãy để service xác thực bằng danh tính riêng và chỉ xin quyền cần thiết. Khi service hành động thay người dùng, hãy sử dụng một cơ chế delegation/on-behalf-of có policy rõ ràng, kiểm đúng audience/scope và ghi lại actor khi cần. Mỗi resource server phải kiểm tra credential dành cho chính mình; mọi token phải được bảo vệ khỏi rò rỉ, phát lại và dùng sai mục đích trong suốt vòng đời.

Các tiêu chuẩn liên quan:

- **RFC 6749 — OAuth 2.0 Authorization Framework:** roles, client credentials grant, access token và refresh token.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** cách gửi bearer token qua HTTP và xử lý lỗi.
- **RFC 7009 — OAuth 2.0 Token Revocation:** cơ chế thu hồi token của authorization server.
- **RFC 7519 — JSON Web Token (JWT):** claims như `iss`, `sub`, `aud`, `exp`.
- **RFC 7662 — OAuth 2.0 Token Introspection:** trạng thái hoạt động và thông tin của opaque token.
- **RFC 8693 — OAuth 2.0 Token Exchange:** subject token, actor, target audience/resource và delegated access.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** xác thực client và ràng buộc token với chứng chỉ.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** giới hạn tài nguyên mục tiêu khi xin access token.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** hồ sơ JWT cho access token của resource server.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** ràng buộc token với bằng chứng sở hữu khóa.
- **OWASP Cheat Sheet Series:** hướng dẫn quản lý secret, logging và bảo vệ token theo ngữ cảnh ứng dụng.
