# Phân biệt người dùng, ứng dụng và danh tính máy trong claims

> **Module:** SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)  
> **Chương:** Hợp đồng token  
> **Phạm vi:** Phân biệt các loại danh tính trong JWT và OAuth/OIDC ở mức giao thức, không phụ thuộc Java, Spring hay framework cụ thể.

Một access token có thể đồng thời mô tả **người dùng**, **ứng dụng đã yêu cầu token**, **dịch vụ đang hành động thay mặt người dùng** và **API được phép nhận token**. Các vai trò này có liên quan nhưng không đồng nghĩa. Nếu hệ thống coi tất cả là một danh tính, nó có thể cấp quyền cho ứng dụng như thể đó là người dùng, ghi nhận sai chủ thể trong audit hoặc cho phép một dịch vụ dùng token thay mặt một người dùng khác.

Ví dụ: người dùng Lan đăng nhập vào ứng dụng Storefront. Ứng dụng gọi API đơn hàng để đọc đơn của Lan. Token có thể mang:

- **sub:** định danh người dùng Lan — chủ thể mà quyền truy cập đang đại diện.
- **client_id:** định danh ứng dụng Storefront — OAuth client đã yêu cầu/có token.
- **aud:** định danh API đơn hàng — dịch vụ được phép nhận token.
- **scope:** quyền được cấp, chẳng hạn đọc đơn hàng.

Nếu một dịch vụ trung gian tiếp tục gọi API thay mặt Lan qua một luồng delegation/token exchange, có thể cần thêm **act** để mô tả actor. Nếu một dịch vụ gọi API bằng danh tính của chính nó theo client credentials, subject có thể là danh tính máy thay vì người dùng.

**Không có một claim duy nhất mang ý nghĩa “người gọi” cho mọi JWT.** Phải đọc từng claim theo token profile, grant type và mục đích sử dụng.

## 1. Mô hình các vai trò danh tính

### 1.1. Các câu hỏi khác nhau

| Vai trò | Câu hỏi | Claim/khái niệm thường liên quan |
|---|---|---|
| Bên phát hành | Ai tạo và ký token? | **iss** |
| Chủ thể (subject) | Token đại diện cho ai hoặc thực thể nào? | **sub** |
| OAuth client / ứng dụng | Ứng dụng OAuth nào đã yêu cầu hoặc được cấp token? | **client_id** trong các profile có quy định |
| Authorized party | Client nào là bên được ủy quyền trong ngữ cảnh OpenID Connect? | **azp** trong ID token |
| Actor | Ai đang hành động thay mặt chủ thể trong một luồng delegation? | **act** theo RFC 8693 |
| Bên nhận | Token được phát hành cho API/client nào? | **aud** |
| Quyền | Token cho phép thao tác nào? | **scope**, **roles**, **permissions** theo profile |
| Bằng chứng sở hữu | Token có bị ràng buộc với khóa/chứng thư của bên gửi không? | **cnf** và cơ chế proof-of-possession tương ứng |

Các vai trò trả lời những câu hỏi khác nhau. Ví dụ, **aud** không phải danh tính ứng dụng gọi; **scope** không phải danh tính người dùng; **client_id** không chứng minh người dùng đã xác thực.

### 1.2. Phân biệt người dùng, ứng dụng và máy

- **Người dùng (human user):** một cá nhân đăng nhập hoặc được ủy quyền truy cập tài nguyên. Trong access token đại diện người dùng, **sub** thường nhận diện người dùng trong phạm vi issuer.
- **Ứng dụng (OAuth client):** phần mềm đăng ký với authorization server, ví dụ ứng dụng web, mobile app hoặc backend client. **client_id** nhận diện client registration theo profile.
- **Danh tính máy/workload:** một dịch vụ, daemon, job hoặc workload tự động. Nó có thể dùng OAuth client credentials; khi đó token đại diện cho client/máy, không phải một người dùng cuối.
- **Actor:** một thực thể thực hiện hành động thay mặt subject trong một chuỗi delegation. Actor có thể là dịch vụ hoặc một chủ thể được ủy quyền khác.

Một tiến trình chạy trên máy chủ không tự động là “machine identity” chỉ vì nó là phần mềm. Danh tính cần được xác lập qua cơ chế xác thực client/workload và token profile, không suy ra từ tên tiến trình, địa chỉ IP hoặc claim tùy ý.

## 2. Các claim và ý nghĩa danh tính

### 2.1. sub — chủ thể mà token đại diện

Claim **sub** (Subject) xác định chủ thể của JWT. Trong một access token đại diện cho người dùng, subject thường là người dùng; trong token client credentials theo profile JWT access token RFC 9068, subject là client.

Ví dụ token đại diện người dùng:

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-42",
  "aud": "https://api.orders.example.com"
}
~~~

Ví dụ token đại diện client/máy:

~~~json
{
  "iss": "https://id.example.com",
  "sub": "inventory-worker"
}
~~~

Không mặc định **sub** luôn là username, email hoặc ID người dùng. Nó là định danh trong không gian của issuer. Khi nhiều issuer cùng có thể phát hành token, nên định danh principal theo ngữ cảnh **iss + sub** để tránh hai subject có cùng chuỗi bị gộp nhầm.

### 2.2. client_id — ứng dụng OAuth được cấp token

**client_id** nhận diện OAuth client trong các profile quy định claim này, nổi bật là JWT access token theo RFC 9068. Nó trả lời “client OAuth nào đã yêu cầu/được cấp token?”, không tự trả lời “người dùng nào đang được đại diện?”.

Một token có thể có:

~~~json
{
  "sub": "user-42",
  "client_id": "storefront-web"
}
~~~

Ở đây:

- **sub = user-42:** chủ thể là người dùng.
- **client_id = storefront-web:** ứng dụng OAuth đang sử dụng token.

Không suy ra client được phép làm mọi việc mà user có thể làm. Quyền cần được giới hạn đồng thời theo người dùng, client, audience, scope và policy của tài nguyên.

### 2.3. azp — authorized party trong OpenID Connect

Claim **azp** (Authorized Party) thuộc ngữ cảnh OpenID Connect ID token. Nó nhận diện party mà ID token được phát hành cho hoặc party được ủy quyền trong trường hợp có nhiều audience theo quy tắc OIDC.

Điểm cần nhớ:

- **azp** là khái niệm của OIDC ID token; không phải claim tổng quát để thay thế **client_id** trong mọi access token.
- Relying party phải kiểm tra **aud** khớp client của mình và kiểm tra **azp** theo các điều kiện của OIDC Core, đặc biệt khi ID token có nhiều audience hoặc khi claim này xuất hiện.
- Không dùng **azp** để xác định người dùng; người dùng được nhận diện bởi **sub**.
- Không dùng ID token làm access token chỉ vì **azp** hoặc **aud** chứa một client ID.

### 2.4. act — actor trong luồng delegation/token exchange

RFC 8693 định nghĩa claim **act** để biểu diễn actor trong token exchange. Claim này chứa một JSON object mô tả danh tính actor; trường **sub** bên trong object thường nhận diện actor.

Ví dụ minh họa một dịch vụ đang hành động thay mặt người dùng:

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-42",
  "aud": "https://api.payments.example.com",
  "act": {
    "sub": "checkout-service"
  }
}
~~~

Diễn giải:

- Subject vẫn là **user-42** — người mà quyền đang được đại diện.
- Actor là **checkout-service** — dịch vụ hiện đang thực hiện hành động thay mặt subject.
- Audience là Payments API — nơi được phép nhận token.

**act** không phải claim bắt buộc của mọi JWT hoặc mọi access token. Chỉ sử dụng khi giao thức/contract có mô hình delegation và định nghĩa rõ cách xác minh actor. Nếu có chuỗi actor lồng nhau, recipient phải xử lý theo RFC 8693 và profile đã chọn; không tự suy ra actor từ các claim tùy chỉnh không được tin cậy.

### 2.5. aud — bên nhận, không phải bên gọi

Claim **aud** xác định bên nhận dự kiến của token. Trong ví dụ trên, **aud** là Payments API. Nó không cho biết user hay service nào đã gọi API.

API phải kiểm tra audience của chính mình. Một token có **sub = user-42**, **client_id = storefront-web** nhưng **aud** dành cho Inventory API không được chấp nhận tại Payments API.

### 2.6. scope, roles và permissions — quyền, không phải danh tính

Các claim quyền mô tả những thao tác được cấp:

- **scope:** phạm vi quyền theo giao thức, ví dụ **orders:read**.
- **roles / permissions:** quyền theo mô hình của ứng dụng nếu profile định nghĩa.

Chúng không xác định ai đang thực hiện hành động. Hai người dùng có thể có cùng scope nhưng được phép truy cập các tài nguyên khác nhau. Một client có scope không có nghĩa mọi user đăng nhập qua client đó đều được quyền giống nhau.

### 2.7. cnf — ràng buộc token với khóa của bên gửi

Claim **cnf** có thể mang thông tin xác nhận khóa/chứng thư gắn với token trong các profile sender-constrained. Nó hỗ trợ kiểm tra bên gửi có chứng minh được quyền sở hữu khóa tương ứng hay không.

**cnf không phải user ID, client ID hoặc actor ID.** Nó là thông tin ràng buộc việc sử dụng token với một khóa/chứng thư. Resource server phải kiểm tra proof-of-possession theo đúng cơ chế, chẳng hạn mTLS hoặc DPoP; chỉ đọc claim cnf là chưa đủ.

## 3. Phân biệt theo OAuth grant type

Grant type ảnh hưởng đến chủ thể và cách hiểu danh tính trong access token. Không nên dùng một quy tắc **sub** cho mọi luồng.

### 3.1. Authorization Code — ứng dụng truy cập thay mặt người dùng

Trong Authorization Code flow, người dùng ủy quyền cho ứng dụng web truy cập tài nguyên. Ứng dụng nhận access token để gọi API thay mặt người dùng. Nếu cần xác thực danh tính người dùng, luồng thường kết hợp OpenID Connect; riêng OAuth Authorization Code không tự định nghĩa kết quả đăng nhập:

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-42",
  "client_id": "storefront-web",
  "aud": "https://api.orders.example.com",
  "scope": "orders:read",
  "iat": 1794800000,
  "exp": 1794800600
}
~~~

Trong profile access token phù hợp:

- **sub** đại diện user-42.
- **client_id** nhận diện Storefront OAuth client.
- **aud** xác định Orders API.
- **scope** giới hạn quyền được cấp.

API cần kiểm tra quyền của user-42 đối với đơn hàng cụ thể và policy của client nếu có. Việc client được đăng ký không có nghĩa client có thể truy cập dữ liệu của mọi user.

### 3.2. Client Credentials — dịch vụ gọi API bằng danh tính của chính nó

Một workload tự động cần đọc dữ liệu kho vận mà không đại diện người dùng:

~~~json
{
  "iss": "https://id.example.com",
  "sub": "inventory-worker",
  "client_id": "inventory-worker",
  "aud": "https://api.inventory.example.com",
  "scope": "inventory:read",
  "iat": 1794800000,
  "exp": 1794800300
}
~~~

Theo JWT access token profile RFC 9068, trong grant **client_credentials**, giá trị **sub** phải là **client_id** của client. Ví dụ dùng cùng chuỗi cho hai claim để thể hiện trường hợp đó.

Diễn giải:

- Subject là workload/client, không phải người dùng cuối.
- **client_id** nhận diện OAuth client.
- API chỉ cấp quyền workload theo scope/policy được phê duyệt.
- Không tạo audit record như thể một user đã thực hiện thao tác.

Một hệ thống có thể dùng tên hiển thị “inventory-worker”, nhưng định danh thực tế phải được xác thực bởi authorization server và kiểm tra qua token đã xác minh. Không tin tên service do request tự gửi.

### 3.3. Delegation / Token Exchange — dịch vụ hành động thay mặt người dùng

Giả sử user-42 đăng nhập, một dịch vụ trung gian cần gọi Payments API thay mặt người dùng. Hệ thống có thể dùng token exchange để phát hành token mới với subject và actor được biểu diễn rõ:

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-42",
  "client_id": "checkout-service",
  "aud": "https://api.payments.example.com",
  "act": {
    "sub": "checkout-service"
  },
  "scope": "payments:create",
  "iat": 1794800000,
  "exp": 1794800300
}
~~~

Đây là ví dụ mô tả ý tưởng; cách xác định **client_id**, **act** và token exchange phải theo cấu hình authorization server và RFC 8693. Không mặc định hai claim này luôn giống nhau trong mọi mô hình delegation.

API Payments nên ghi nhận:

- **Subject:** user-42 — người được đại diện.
- **Actor:** checkout-service — dịch vụ thực hiện hành động.
- **Client:** OAuth client liên quan đến yêu cầu/token theo profile.
- **Audience:** Payments API.
- **Scope:** payments:create.

API cần quyết định xem actor đó có được phép thực hiện hành động này thay mặt subject không. Chỉ kiểm tra user có quyền là chưa đủ nếu chính sách còn giới hạn dịch vụ trung gian.

### 3.4. Phân biệt client credentials với delegation

| Đặc điểm | Client credentials | Delegation / token exchange |
|---|---|---|
| Chủ thể **sub** | Client/workload theo profile RFC 9068 | Người dùng hoặc subject được đại diện |
| Actor | Thường không cần claim actor riêng khi client hành động cho chính nó | Có thể được biểu diễn bằng **act** |
| Client | OAuth client đang xin token | Client yêu cầu trao đổi/cấp token theo profile |
| Quyền | Quyền của workload/client | Quyền của subject bị giới hạn thêm bởi actor/delegation policy |
| Audit | Ghi nhận workload thực hiện | Ghi nhận cả subject và actor |
| Rủi ro chính | Cấp quá quyền cho service account | Nhầm quyền của user với quyền của dịch vụ trung gian |

Không gắn một user giả vào token client credentials chỉ để có trường **sub**. Nếu thao tác cần đại diện người dùng, phải dùng grant/delegation phù hợp và bảo toàn ngữ cảnh subject.

## 4. Danh tính trong OpenID Connect ID Token

ID token được phát hành cho OIDC client để truyền kết quả xác thực. Nó không phải access token dành cho API.

Ví dụ ID token payload rút gọn:

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-42",
  "aud": "storefront-web",
  "azp": "storefront-web",
  "iat": 1794800000,
  "exp": 1794800600,
  "nonce": "request-nonce-123"
}
~~~

Ý nghĩa:

- **sub:** người dùng đã được xác thực.
- **aud:** client mà ID token được phát hành cho.
- **azp:** authorized party theo quy tắc OIDC khi áp dụng.
- **nonce:** liên kết ID token với authentication request trong flow tương ứng.
- **iss:** OpenID Provider phát hành token.

ID token không cần mang **client_id** theo cách access token profile RFC 9068 yêu cầu. Không trộn quy tắc claim giữa hai profile. Relying party phải xác minh ID token theo OpenID Connect Core, bao gồm audience, authorized party, nonce và các điều kiện flow liên quan.

Nếu ID token được gửi đến Orders API, API phải từ chối vì token dành cho OIDC client, không phải API resource server. Việc **aud** chứa client ID không biến token thành quyền truy cập API.

## 5. Danh tính máy và workload identity

### 5.1. Machine identity là principal được xác thực

Một máy hoặc workload cần có danh tính có thể xác minh, ví dụ:

- Dịch vụ backend gọi một API nội bộ.
- Worker xử lý hàng đợi.
- Batch job chạy theo lịch.
- Agent hoặc workload trong môi trường cloud/container.

Danh tính không nên chỉ dựa trên hostname, IP, tên pod hoặc header do caller gửi. Cần một cơ chế cấp danh tính và xác thực client/workload, sau đó authorization server phát hành token với subject/client phù hợp.

### 5.2. OAuth client không phải lúc nào cũng là một workload duy nhất

**client_id** thường nhận diện một OAuth client registration. Một registration có thể được sử dụng bởi nhiều instance hoặc replica. Vì vậy:

- Không mặc định một **client_id** tương ứng chính xác một máy vật lý hoặc một process.
- Nếu cần phân biệt workload instance, cần profile/claim hoặc cơ chế identity riêng có quản lý vòng đời.
- Không dùng **sub** hoặc **client_id** thay cho kiểm tra proof-of-possession khi token cần ràng buộc với một sender cụ thể.
- Không coi địa chỉ IP hoặc tên host là bằng chứng mật mã về danh tính workload.

### 5.3. Sender-constrained token

Với bearer token, bất kỳ bên nào lấy được token đều có thể thử sử dụng token tại đúng audience. Có thể giảm rủi ro bằng cách ràng buộc token với khóa/chứng thư:

- **mTLS certificate-bound access token**: resource server xác minh chứng thư client và đối chiếu thumbprint với claim **cnf** theo RFC 8705.
- **DPoP**: resource server xác minh proof JWT cho request và đối chiếu khóa với token theo RFC 9449.

Các cơ chế này chứng minh quyền sở hữu khóa theo giao thức; chúng không tự biến **cnf** thành một danh tính người dùng. Danh tính subject/client vẫn phải được xác minh riêng.

## 6. Kết hợp danh tính với authorization

### 6.1. Không cấp quyền chỉ dựa vào một claim

Một quyết định authorization có thể cần kết hợp:

\[
\text{Decision} =
f(\text{issuer}, \text{subject}, \text{client}, \text{actor},
\text{audience}, \text{scope}, \text{resource}, \text{context})
\]

Đây là mô hình khái niệm, không phải công thức chuẩn. Từng ứng dụng quyết định những yếu tố nào cần thiết.

Ví dụ, Orders API có thể yêu cầu:

- **sub** là người dùng có quyền truy cập đơn hàng.
- **client_id** thuộc nhóm ứng dụng được phép gọi API.
- **act** nếu có phải là một dịch vụ trung gian được ủy quyền.
- **aud** đúng Orders API.
- **scope** có orders:read.
- Tenant và quyền trên đơn hàng cụ thể khớp chính sách.

Với client credentials, subject là workload nên policy sẽ kiểm tra danh tính máy, scope và tài nguyên; không tìm user permission không tồn tại.

### 6.2. Audit phải ghi đúng cả subject và actor

Trong luồng delegation, chỉ ghi **sub** có thể làm mất thông tin dịch vụ thực hiện thao tác. Chỉ ghi **client_id** hoặc **act** lại làm mất người dùng được đại diện.

Audit record nên phân biệt:

| Trường audit | Giá trị nguồn | Mục đích |
|---|---|---|
| Issuer | **iss** đã xác minh | Biết nguồn danh tính |
| Subject | **sub** đã xác minh | Ai được đại diện |
| Client | **client_id** theo profile | Ứng dụng OAuth liên quan |
| Actor | **act** nếu profile có | Dịch vụ/đối tượng thực hiện thay mặt subject |
| Audience/service | API nhận token | Nơi thực hiện hành động |
| Action/resource | Request đã được kiểm tra | Thao tác và đối tượng cụ thể |
| Decision | Kết quả policy | Cho phép hay từ chối và mã lý do |

Không ghi toàn bộ bearer token hoặc secret vào audit log. Dùng định danh đã xác minh và dữ liệu tối thiểu cần cho điều tra.

### 6.3. Cẩn trọng với impersonation và delegation

**Impersonation** và **delegation** không giống nhau:

- Trong impersonation, hệ thống có thể xử lý request như thể actor chính là subject; nếu dùng, cần policy và audit rõ ràng vì ngữ cảnh actor có thể bị che khuất.
- Trong delegation, subject vẫn được giữ lại và actor được biểu diễn riêng, cho phép recipient đánh giá cả hai danh tính.

Không tự xóa **act** hoặc thay **sub** bằng actor chỉ để đơn giản hóa kiểm tra. Việc đó có thể làm mất ngữ cảnh ai được đại diện và ai thực sự thực hiện hành động.

## 7. Quy tắc thiết kế claim danh tính

### 7.1. Chọn định danh ổn định và có phạm vi

- Ưu tiên subject identifier ổn định, không tái sử dụng ngoài chính sách.
- Tránh dùng email hoặc username có thể đổi làm định danh chính nếu profile cần định danh lâu dài.
- Diễn giải **sub** trong ngữ cảnh issuer; không giả định hai issuer có cùng namespace.
- Phân biệt ID người dùng, client registration, workload principal và actor.
- Không dùng tên hiển thị để cấp quyền.

### 7.2. Chỉ phát hành claim cần thiết

Token chỉ nên mang dữ liệu danh tính cần cho resource server thực hiện policy. Không đưa thông tin cá nhân hoặc thuộc tính nhạy cảm vào token nếu API không cần. JWT ký không mã hóa payload; bearer token có thể bị đọc bởi bên nắm giữ.

### 7.3. Không tự tạo semantics từ tên claim

Các claim **user_id**, **app_id**, **service_name**, **machine_id**, **role** hoặc **actor_id** có thể là claim riêng. Chúng không tự có ý nghĩa chuẩn chỉ vì tên gọi dễ hiểu.

Nếu dùng claim riêng:

- Định nghĩa kiểu dữ liệu, issuer được phép phát hành và profile sử dụng.
- Quy định claim nào là bắt buộc và claim nào có thể bỏ qua.
- Chỉ tin claim sau khi xác minh chữ ký và issuer.
- Tránh để hai claim cùng biểu diễn một danh tính nhưng không có quy tắc ưu tiên.
- Có versioning khi thay đổi semantics.

### 7.4. Phân biệt claim danh tính và bằng chứng xác thực

**sub** hoặc **client_id** mô tả danh tính theo token. Chúng không tự chứng minh request hiện tại do đúng user/client đang nắm token gửi đến. Với bearer token, possession là điều kiện sử dụng; nếu cần ràng buộc người gửi, dùng cơ chế sender-constrained phù hợp. Với OIDC, kiểm tra kết quả đăng nhập theo ID token và flow; không suy diễn từ access token rằng người dùng vừa nhập lại thông tin xác thực.

## 8. Ví dụ tổng hợp và cách đọc token

### 8.1. Người dùng gọi API qua ứng dụng

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-42",
  "client_id": "storefront-web",
  "aud": "https://api.orders.example.com",
  "scope": "orders:read",
  "iat": 1794800000,
  "exp": 1794800600
}
~~~

Đọc: user-42 là subject; storefront-web là OAuth client; Orders API là audience; orders:read là quyền được cấp. API cần kiểm tra quyền user trên đơn hàng cụ thể.

### 8.2. Workload gọi API bằng danh tính của chính nó

~~~json
{
  "iss": "https://id.example.com",
  "sub": "reporting-worker",
  "client_id": "reporting-worker",
  "aud": "https://api.reports.example.com",
  "scope": "reports:generate",
  "iat": 1794800000,
  "exp": 1794800300
}
~~~

Đọc: token đại diện workload theo client credentials. Không có người dùng cuối được đại diện. API cần kiểm tra workload có quyền tạo báo cáo hay không.

### 8.3. Dịch vụ trung gian hành động thay mặt user

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-42",
  "client_id": "checkout-service",
  "act": {
    "sub": "checkout-service"
  },
  "aud": "https://api.payments.example.com",
  "scope": "payments:create",
  "iat": 1794800000,
  "exp": 1794800300
}
~~~

Đọc: subject là user-42; actor là checkout-service; Payments API là audience. API cần policy cho phép dịch vụ đó thực hiện payments:create thay mặt user-42. Đây là ví dụ khái niệm; cách phát hành phải phù hợp token exchange/profile.

### 8.4. ID token dành cho client

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-42",
  "aud": "storefront-web",
  "azp": "storefront-web",
  "iat": 1794800000,
  "exp": 1794800600,
  "nonce": "request-nonce-123"
}
~~~

Đọc: ID token chứng minh kết quả xác thực của user-42 dành cho OIDC client storefront-web. Nó không cấp quyền gọi Orders API.

Các payload trên chỉ minh họa claims; chúng không phải JWT đã ký và không thể dùng làm token thực.

## 9. Quy trình xác minh theo danh tính

~~~mermaid
flowchart TD
    A[Endpoint nhận token] --> B[Chọn profile theo mục đích]
    B --> C[Xác minh chữ ký, issuer, audience và token type]
    C --> D{Token profile hợp lệ?}
    D -->|Không| X[Từ chối]
    D -->|Có| E[Đọc subject theo grant/profile]
    E --> F[Đọc client identity nếu profile có]
    F --> G[Đọc actor nếu luồng delegation có]
    G --> H[Kiểm tra scope và quyền trên tài nguyên]
    H --> I{Danh tính và quyền phù hợp?}
    I -->|Không| X
    I -->|Có| J[Ghi audit subject/client/actor]
    J --> K[Cho phép đúng thao tác]
~~~

Pseudocode khái niệm:

~~~text
authorizeRequest(profile, verifiedClaims, request):
    subject = resolveSubject(profile, verifiedClaims.iss, verifiedClaims.sub)
    client = resolveClientIfDefined(profile, verifiedClaims.client_id)
    actor = resolveActorIfDelegated(profile, verifiedClaims.act)
    audience = verifyReceiver(profile, verifiedClaims.aud)

    reject nếu subject không hợp lệ theo grant/profile
    reject nếu client không được phép tại endpoint
    reject nếu actor có mặt nhưng không được ủy quyền
    reject nếu audience không khớp
    reject nếu scope/permission không đủ
    reject nếu subject/actor không được truy cập resource

    recordAudit(subject, client, actor, audience, request, decision)
    ACCEPT
~~~

Đây là pseudocode thiết kế. Việc xác minh chữ ký, issuer, audience, thời gian và token profile phải diễn ra trước khi claim được xem là đáng tin. Không dùng hàm resolve để tự suy ra danh tính từ dữ liệu request không được xác thực.

## 10. Ma trận kiểm thử danh tính

| ID | Token / tình huống | Điểm tiếp nhận | Kết quả mong đợi | Lý do |
|---|---|---|---|---|
| I1 | Access token đại diện user, đúng client/audience/scope | Orders API | Có thể chấp nhận sau kiểm tra quyền tài nguyên | Subject và client được phân biệt |
| I2 | Client credentials token đại diện workload | Inventory API | Có thể chấp nhận theo quyền workload | Subject là machine/client |
| I3 | ID token có **aud** là OIDC client | Orders API | Từ chối | Sai token profile và audience |
| I4 | Access token có **aud** là API khác | Orders API | Từ chối | Sai audience |
| I5 | Token có **sub** user nhưng client_id không được phép | Orders API | Từ chối theo client policy | User hợp lệ không làm client tự động được tin |
| I6 | Client credentials token thiếu danh tính client theo profile | API đích | Từ chối | Không đủ thông tin machine principal |
| I7 | Token exchange có actor không được ủy quyền | Payments API | Từ chối | Actor policy không đạt |
| I8 | Delegated token có subject hợp lệ nhưng actor bị thiếu khi profile yêu cầu | Payments API | Từ chối | Thiếu ngữ cảnh delegation |
| I9 | Token có claim **azp** nhưng endpoint là resource API | Orders API | Từ chối nếu đó là ID token/sai profile | azp không biến ID token thành access token |
| I10 | **sub** giống nhau từ hai issuer khác nhau | Resource server | Không gộp principal | Định danh theo issuer + subject |
| I11 | Token có scope đúng nhưng subject không có quyền trên resource | Orders API | Từ chối quyền | Scope không thay thế resource authorization |
| I12 | Bearer token bị gửi bởi bên không có proof-of-possession trong profile sender-constrained | API đích | Từ chối | Thiếu bằng chứng sở hữu khóa |
| I13 | Audit chỉ ghi client, bỏ subject trong delegation | Hệ thống audit | Kiểm thử phát hiện thiếu trường audit | Mất người dùng được đại diện |
| I14 | Workload token bị ghi nhận như hành động của user | Hệ thống audit | Từ chối quy tắc audit sai | Sai loại principal |

## 11. Checklist thiết kế hợp đồng danh tính

**Mô hình principal**

- [ ] Xác định rõ **sub** là người dùng, client/workload hay chủ thể khác theo từng grant/profile.
- [ ] Định nghĩa ý nghĩa **client_id** và không coi nó là user ID.
- [ ] Chỉ dùng **azp** trong ngữ cảnh OIDC theo đúng quy tắc.
- [ ] Chỉ dùng **act** khi có mô hình delegation/token exchange rõ ràng.
- [ ] Phân biệt **aud** (bên nhận) với caller/actor.

**Xác minh và cấp quyền**

- [ ] Issuer và subject được định danh trong cùng namespace tin cậy.
- [ ] Client/workload được xác thực bằng cơ chế phù hợp trước khi phát hành token.
- [ ] Client, subject và actor được kiểm tra riêng khi policy cần.
- [ ] Scope/permission được kết hợp với quyền trên tài nguyên cụ thể.
- [ ] Token client credentials không bị coi là token người dùng.
- [ ] ID token không bị sử dụng như access token.
- [ ] Sender-constrained token có kiểm tra proof-of-possession khi profile yêu cầu.

**Audit và vận hành**

- [ ] Audit lưu subject, client, actor và audience riêng biệt khi có.
- [ ] Không ghi nguyên bearer token hoặc secret vào log.
- [ ] Claim riêng có schema, semantics và versioning.
- [ ] Có kiểm thử nhầm user/client/actor, sai issuer, sai audience và thiếu quyền.
- [ ] Có chính sách delegation/impersonation và truy vết rõ ràng.

**Điều cần nhớ:** **sub** cho biết token đại diện ai; **client_id** cho biết OAuth client nào liên quan; **act** cho biết ai đang hành động thay mặt subject trong luồng delegation; **aud** cho biết ai được nhận token. Scope và permission mô tả quyền. Chỉ khi phân biệt được các vai trò này, hệ thống mới có thể xác thực, cấp quyền và ghi audit chính xác.

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): Claims **iss**, **sub**, **aud** và cấu trúc JWT.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): **sub**, **client_id** và quy tắc theo grant type, bao gồm client credentials.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): Subject, actor và claim **act** trong delegation/token exchange.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): **sub**, **aud**, **azp** và ID token validation.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): OAuth client, client credentials và các grant.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): Bảo vệ OAuth clients và token.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): Ràng buộc access token với chứng thư client.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): Ràng buộc token với bằng chứng sở hữu khóa.
