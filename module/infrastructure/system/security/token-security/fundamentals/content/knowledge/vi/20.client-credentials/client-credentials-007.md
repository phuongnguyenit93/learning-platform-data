# Token caching for service calls

Một **Billing Worker** gọi **Invoice API** hàng nghìn lần mỗi phút để đồng bộ hóa hóa đơn. Mỗi lần gọi API, worker cần một OAuth 2.0 **access token** cấp qua grant `client_credentials`. Nếu worker gọi Authorization Server (AS) xin token mới **trước mọi request** tới Invoice API, hệ thống sẽ tốn thêm một round trip, tăng độ trễ, gây tải cho AS và dễ tạo **token-issuance storm** khi nhiều worker khởi động cùng lúc. Nếu worker giữ token quá lâu, nó có thể gửi token **đã hết hạn, bị thu hồi hoặc không đúng audience/scope**.

**Token caching for service calls** là việc **tái sử dụng access token còn hợp lệ cho những lời gọi service-to-service (M2M) phù hợp với cùng client/grant/resource/scope và điều kiện bảo mật**, thay vì phát hành token mới ở mỗi request. Cache cần có **khóa phân vùng chính xác, thời hạn hiệu lực bảo thủ, đồng bộ request cấp token, cơ chế hết hạn/invalidate và chiến lược xử lý lỗi an toàn**.

Trong chương **Client credentials** thuộc module **Security Token Security Fundamentals**, bài này giải thích cách cache access token trong hệ thống Java/Spring, multi-replica và microservices; đặt nó trong mô hình tin cậy của OAuth 2.0/OIDC, JWT/opaque token, issuer, audience, scope, lưu trữ, thu hồi và nguy cơ bearer token bị đánh cắp/phát lại. Điểm then chốt: **cache là tối ưu hóa hiệu năng phía client, không phải căn cứ để Resource Server bỏ xác minh token hoặc quyền API**.

## 1. Luồng `client_credentials` và vì sao cần cache

Trong OAuth 2.0 `client_credentials`, **client dùng chính credential của mình để xin access token cho quyền được AS cho phép**. Đây là grant thường dùng cho backend/worker/service tự hoạt động, **không phải đại diện cho một người dùng vừa đăng nhập**.

Các vai trò:

| Vai trò | Trong ví dụ | Trách nhiệm |
|---|---|---|
| **OAuth client** | Billing Worker | Xác thực với AS, nhận và cache access token, gọi API |
| **Authorization Server (AS)** | `https://auth.example.test` | Xác thực client và chính sách grant, phát access token |
| **Resource Server (RS)** | Invoice API | Xác minh access token và quyền truy cập tài nguyên |
| **Secret manager / KMS** | Kho client credential | Bảo vệ client secret/khóa; **không thay thế AS** |
| **Token cache** | Bộ nhớ worker hoặc lớp cache được thiết kế | Tái sử dụng token trong phạm vi và TTL được phép |

~~~mermaid
sequenceDiagram
    autonumber
    participant W as Billing Worker
    participant Cache as Token Cache
    participant AS as Authorization Server
    participant API as Invoice API
    W->>Cache: Token cho client=billing, aud=invoice-api, scope=invoice:read?
    alt Cache miss hoặc gần hết hạn
        Cache-->>W: MISS
        W->>AS: POST /token, grant_type=client_credentials + client authentication
        AS->>AS: Kiểm client, grant, scope, resource
        AS-->>W: access_token, token_type, expires_in
        W->>Cache: Lưu token với TTL bảo thủ theo context
    else Cache còn hợp lệ
        Cache-->>W: HIT: access token theo đúng context
    end
    W->>API: Authorization: Bearer access token
    API->>API: Kiểm issuer, aud, exp, scope và quyền đối tượng
    API-->>W: Kết quả theo chính sách
~~~

**Cần phân biệt:** AS quyết định **token được cấp quyền gì**; client cache quyết định **dùng lại bản token nào khi còn thời hạn**; RS quyết định **request có được phép không**. Cache đúng không có nghĩa token sẽ luôn được RS chấp nhận nếu nó đã bị thu hồi, issuer bị thay đổi hoặc policy nghiệp vụ cập nhật.

### Ví dụ token endpoint

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <redacted-client-credential>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&scope=invoice%3Aread
~~~

Phản hồi minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<access-token-redacted>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "invoice:read"
}
~~~

Ở đây `expires_in=900` là **thời lượng token còn hiệu lực tính bằng giây** theo OAuth token response, tương đương **15 phút** tại thời điểm liên quan đến phát hành. Client vẫn cần thời gian đệm thay vì sử dụng token sát giây hết hạn.

**RFC 6749, mục 4.4.3 nêu rằng refresh token thông thường không nên được cấp với `client_credentials`.** Khi token hết hạn, confidential client có thể **xác thực lại với AS** để nhận access token khác. Không được thiết kế mặc định một vòng quay refresh token cho M2M chỉ vì hệ thống login người dùng cũng dùng refresh token.

## 2. Cache token nào, và không nên cache thứ gì?

| Dữ liệu | Tính chất | Cách quản lý gợi ý |
|---|---|---|
| **M2M access token** | Chuỗi bearer/sender-constrained, thường TTL ngắn | Cache theo client + audience + scope + binding, có expiry rõ |
| **Client secret** | Credential của confidential client, có thể dài hạn hơn access token | Secret manager / workload identity; cache có giới hạn và rotation theo chính sách |
| **Private key cho `private_key_jwt` hoặc mTLS** | Credential mật mã của client | KMS/HSM/keystore hoặc signer handle thích hợp; ưu tiên không xuất khóa |
| **Refresh token** | Thường dùng grant có người dùng, nếu AS cấp | Bảo vệ rotation/reuse detection/transaction; **không giả định tồn tại ở client_credentials** |
| **OIDC ID token** | Xác thực người dùng cho relying party/client | Không dùng như bearer access token để gọi API nghiệp vụ |
| **JWT signing key của AS** | Khóa của issuer dùng phát token | AS quản lý; M2M client không cần lấy khóa này |
| **JWKS public key** | Khóa công khai để RS kiểm JWT | RS có thể cache theo quy tắc và chính sách rotation, **khác cache access token phía client** |
| **Opaque introspection `active`** | Trạng thái token mà RS hỏi AS | Cache của **RS**, có thể gây revoke propagation lag; không phải cache token gọi API |

Token cache phía **client** chứa bản access token dùng để gọi RS. Một **opaque token** cũng cache được, dù client không đọc được các claims. Một **JWT access token** cũng cache được, nhưng **không dựa vào việc tự giải mã JWT chưa xác minh để quyết định quyền hoặc kéo dài TTL**.

### Token endpoint phản hồi gì thì client tin?

Client cần kiểm phản hồi tới từ **AS được cấu hình và xác thực qua TLS**, có đủ các trường yêu cầu và loại token được hỗ trợ. Giá trị `expires_in`/thời điểm hết hạn được thư viện OAuth tin cậy sử dụng để quyết định cache; với JWT, `exp` có thể cung cấp thêm giới hạn bảo thủ khi được đọc và xác minh đúng cách. **Không giả định mọi token đều là JWT** hoặc token nào cũng có `refresh_token`.

## 3. Cache key phải biểu diễn đúng ngữ cảnh cấp token

Một lỗi nguy hiểm là cache toàn cục theo chuỗi `client_id` rồi dùng token đó ở tất cả API:

~~~text
BAD:
  tokenCache["billing-worker"] = token_for_invoice_api

Later:
  billing-worker calls payment-api
  -> mistakenly forwards invoice-api token to payment-api
~~~

**Cache hit chỉ an toàn khi request cần cùng một access-token context.** Các chiều quan trọng:

| Chiều khóa | Vì sao phân biệt? |
|---|---|
| **Issuer/AS** | Cùng client ID ở hai issuer không đại diện cùng registration/trust domain |
| **Client registration/verified client identity** | Không chia token giữa client có quyền khác nhau |
| **Grant type** | `client_credentials` khác token đại diện người dùng hoặc token exchange |
| **Resource/audience** | Token dành cho Invoice API không dùng nhầm ở Payment API |
| **Scope set** | `invoice:read` khác `invoice:approve`; không trộn quyền |
| **Tenant / policy context** | Nếu AS cấp token theo tenant/context đã được xác minh, phải phân vùng |
| **Token binding/sender key** | DPoP-bound hoặc mTLS-bound token phải khớp khóa/chứng chỉ của bên gửi |
| **Credential/policy version (nếu thích hợp)** | Khi client credential hoặc grant thay đổi, có thể cần invalidation để không dùng token cũ ngoài chính sách |

Khóa cache minh họa:

~~~text
TokenCacheKey {
  trustedIssuer:    "https://auth.example.test"
  clientRegistration:"billing-prod"
  grantType:        "client_credentials"
  resource:         "https://api.example.test/invoices"
  scopes:           ["invoice:read"]
  tenantContext:    "tenant-a"       // chỉ khi grant thực sự phân biệt tenant
  senderBindingKey: "cert-thumbprint-or-key-id-if-bound"
}
~~~

Giá trị trên chỉ minh họa mô hình; cache key không nên chứa **plaintext access token, client secret hoặc private key**. Sắp xếp/canonicalize **tập scope** nhất quán và dùng resource identifier đúng theo cấu hình AS; không biến `scope=read write` và `scope=write read` thành hai bản cấp token khác nhau nếu chúng có cùng ý nghĩa, trừ khi profile quy định khác.

**Không được dùng cache như cơ chế tự thay đổi audience.** Nếu AS cấp token với `aud=invoice-api`, một gateway đổi host/path không làm claim `aud` tự đổi. RS Payment API phải từ chối token không dành cho mình; client phải yêu cầu access token khác với resource/audience được phép.

### Khi nào cache key không cần tenant?

Nếu client credentials token được cấp **cho một service identity chung**, còn tenant/owner được xác định và phân quyền riêng tại API, không tự thêm tenant do người gọi gửi như một “yếu tố tin cậy” vào grant. Chỉ đưa tenant vào cache key khi AS **thực sự cấp token khác biệt theo tenant** và ứng dụng đã xác minh quyền chọn tenant. **Không lấy request query `tenant_id` tự khai để chọn token của tenant khác**.

## 4. TTL: sử dụng `expires_in` nhưng hết hạn sớm hơn

Một token `expires_in=900` không có nghĩa client nên gửi request vào giây thứ 899. Có nhiều nguồn độ trễ:

- Network latency từ client tới RS và thời gian RS bắt đầu kiểm token.
- Clock skew giữa AS, client và RS.
- Queue/retry/backpressure trong worker và gateway.
- Bản token được phát trước khi client nhận xong token response.
- Token có thể bị revoke trước expiry theo policy.

**Nguyên tắc:** Đừng phát một request mới bằng token đã hết hạn hoặc **quá gần** hạn. Tính hạn cache một cách **bảo thủ**.

### Công thức đơn giản

Giả sử tại thời điểm client nhận token response, AS báo thời lượng `expires_in = T`. Đặt `safety_margin = Δ` (ví dụ 60 giây; chỉ là giá trị minh họa tùy hệ thống). Cache token trong tối đa:

\[
TTL_{\text{cache}} = \max(0,\; T - \Delta)
\]

Với token sống 900 giây và margin 60 giây:

~~~text
Token response:             expires_in = 900 s
Safety margin:              60 s
Local cache usable window:  tối đa khoảng 840 s
Khi còn <= 60 s:           xin token mới trước request kế tiếp
~~~

Trong triển khai cần xét thời điểm token được phát, thời gian trôi qua trước khi response nhận được và clock behavior của thư viện. Một lựa chọn bảo thủ là tính từ **thời điểm gửi token request**, cộng `expires_in`, rồi trừ margin; cách khác dùng `expiresAt` của thư viện OAuth đáng tin với margin. Nếu token response báo TTL quá ngắn so với margin, cache có thể **không dùng được** và client cần chính sách khác, không đặt TTL âm hoặc vượt giới hạn AS.

### TTL của cache khác `exp`, `Cache-Control` và `max-age`

| Giá trị | Quy định điều gì? |
|---|---|
| OAuth `expires_in` | Thời lượng access token được AS công bố là còn hiệu lực |
| JWT `exp` | Mốc thời gian token **không được RS chấp nhận** khi đã đến hạn theo chuẩn và quy tắc clock skew |
| Local cache deadline | Khi **client dừng sử dụng token này** để khởi tạo request mới, thường sớm hơn expiry |
| HTTP `Cache-Control: no-store` ở token endpoint | Không để HTTP intermediary/client generic cache token response theo cơ chế không an toàn |
| CORS `Access-Control-Max-Age` | Cache **preflight CORS**, không liên quan thời hạn token |
| Introspection cache TTL ở RS | Khoảng thời gian RS có thể dùng lại kết quả kiểm trạng thái token; ảnh hưởng độ trễ revoke |

**Không dùng HTTP response cache của CDN để lưu access token trả về từ `/token`.** “Token cache” ở đây là **bộ nhớ credential trong OAuth client được kiểm soát**, không phải public HTTP caching.

### Refresh sớm và jitter

Nếu có 200 pod cùng được cấp token lúc 12:00, tất cả có thể hết hạn vào 12:15 và cùng refresh lúc 12:14. Để giảm herd:

- Mỗi pod có **jitter nhỏ** quanh mốc refresh (trong cửa sổ an toàn).
- Khi nhiều request trong **một process** cùng thấy token gần hết hạn, dùng **single-flight** để chỉ một request xin token.
- Khi cần đồng bộ giữa nhiều replica, dùng distributed coordination có TTL/fencing theo rủi ro; không chỉ dựa vào `synchronized` Java ở từng pod.
- Rate limit/backoff đối với token endpoint và cảnh báo khi issuance tăng bất thường.

**Jitter không được kéo token vượt expiry.** Mọi thời điểm refresh ngẫu nhiên phải nằm **trước hạn an toàn**, không làm chấp nhận token đã hết hiệu lực.

## 5. Cache hit, miss, near-expiry và invalidation

Một token cache đơn giản nhưng đúng cần mô hình trạng thái rõ:

~~~text
EMPTY        Chưa có token cho context này
VALID        Token đang dùng được với safety margin
REFRESHING   Một tác vụ đang xin token mới
STALE        Token đã hết usable window, không khởi tạo request mới
INVALIDATED  Token bị loại bỏ vì revoke, invalid_token, credential/policy change
~~~

~~~mermaid
flowchart TD
    R["Service cần gọi Resource Server"] --> K["Tra cache theo đầy đủ context"]
    K --> V{"Token có còn usable?"}
    V -- "Có" --> U["Dùng token cache; gọi API"]
    V -- "Không" --> L{"Đã có fetch đang chạy cho key này?"}
    L -- "Có" --> W["Chờ cùng kết quả single-flight"]
    L -- "Không" --> F["Một requester xin access token tại AS"]
    F --> A{"AS cấp token hợp lệ?"}
    A -- "Có" --> S["Lưu token + deadline bảo thủ"]
    S --> U
    A -- "Không" --> E["Không gọi API bằng token expired; xử lý lỗi AS"]
    W --> T{"Kết quả usable?"}
    T -- "Có" --> U
    T -- "Không" --> E
~~~

### Khi nào invalidate?

1. **Hết local cache deadline** hoặc token expired: bỏ bản cũ, xin bản mới.
2. **RS trả `401` với bearer challenge `invalid_token`**: có thể invalidate **đúng cache entry/token** và xin token mới theo giới hạn retry.
3. **Client credential/grant bị revoke hoặc rotate**: loại bỏ cache theo policy; đừng giả định token đã phát tự hết hiệu lực chỉ vì secret đã đổi.
4. **Đổi issuer, resource/audience, scope, DPoP key hoặc mTLS cert**: bản token cũ không còn phù hợp với context mới.
5. **Điều tra token leak**: ngăn dùng token bị nghi lộ phía client và phối hợp thu hồi tại AS/RS khi hỗ trợ.

**Không invalidate toàn bộ cache chỉ vì một API bất kỳ trả `403`.** `403 insufficient_scope` hoặc object-level authorization denial thông thường cho biết **token thiếu quyền**, không phải token đã hết hạn. Xin token mới với cùng grant/scope có thể chỉ gây vòng lặp, thậm chí tăng tải hoặc che lỗi phân quyền.

## 6. Những lỗi HTTP nào nên và không nên kích hoạt lấy token mới?

| Response từ RS | Khả năng nguyên nhân | Hành vi phía client |
|---|---|---|
| **`200/201/204`** | API thành công | Giữ token theo TTL và context |
| **`401` + `WWW-Authenticate: Bearer error="invalid_token"`** | Token expired/revoked/không hợp lệ | Invalidate token **đúng entry**, có thể xin token mới và retry **tối đa có kiểm soát** |
| **`401` do sai issuer/audience/token profile** | Cấu hình AS/RS/resource sai | Không lặp vô hạn; phát hiện misconfiguration và cảnh báo |
| **`403` + `insufficient_scope`** | Grant không có scope yêu cầu | Không tự nâng scope; điều chỉnh policy/registration sau khi được phép |
| **`403` object/tenant permission** | Client không được thao tác dữ liệu cụ thể | Từ chối theo nghiệp vụ; không refresh để thử vượt quyền |
| **`429`** | Quota/rate limit của RS | Xử lý `Retry-After`, backoff/jitter; không mặc định xin token mới |
| **`500/502/503/504`** | Lỗi ứng dụng/mạng/downstream | Retry request theo idempotency policy; không mặc định coi token hỏng |
| **Lỗi TLS/DNS** | Kết nối/độ tin cậy endpoint | Không bỏ kiểm TLS hay chuyển token sang host tùy ý |

**Retry không phải luôn an toàn cho mọi phương thức HTTP.** Với `GET` idempotent, retry một lần sau khi lấy token mới thường dễ bảo đảm hơn. Với `POST` tạo giao dịch hoặc thanh toán, phải biết server **đã xử lý nghiệp vụ hay chưa**, có **idempotency key** hay không và lỗi nhận ở giai đoạn nào. Không gửi lặp POST gây tác động kép chỉ vì token được refresh.

### Token endpoint trả lỗi thì sao?

| OAuth/token endpoint error | Ý nghĩa thường gặp | Phản ứng |
|---|---|---|
| `invalid_client` | Credential/client authentication không hợp lệ | Cảnh báo, kiểm secret/khóa/cert/registration; **không retry nóng** |
| `unauthorized_client` | Client không được phép grant | Sửa quyền/config, không bỏ client auth |
| `invalid_scope` | Scope không hợp lệ hoặc vượt quyền | Sửa cấu hình/consent/policy; không xin scope rộng hơn bằng thử đoán |
| `invalid_request` | Form/body/grant không đúng | Sửa giao thức; không retry giống hệt liên tục |
| **HTTP 429** | Rate limit ở AS/edge | Backoff, có jitter và tuân thủ `Retry-After` nếu có |
| **HTTP 503/timeout** | AS tạm thời không khả dụng hoặc response bị mất | Dùng token **đang còn hợp lệ** nếu policy cho phép; nếu không thì fail safely, thử lại có giới hạn |

## 7. Single-flight: tránh 100 request cùng gọi `/token`

Giả sử Billing Worker xử lý 100 request đồng thời. Cache entry hết hạn khiến 100 thread cùng thấy miss; nếu tất cả gọi AS, hệ thống bắn 100 token requests chỉ để lấy **cùng một loại access token**.

### Mô hình không an toàn

~~~text
T0: token cache key=K hết hạn
T1: thread 1..100 cùng đọc MISS
T2: tất cả POST /token
T3: AS ký 100 token, rate limit có thể bị kích hoạt
T4: thread nào trả cuối ghi đè token cache
~~~

### Mô hình single-flight

~~~text
T0: token K gần hết hạn
T1: thread 1 giành được quyền fetch K
T2: thread 2..100 chờ cùng Future/Promise theo K
T3: thread 1 nhận token mới, ghi cache với TTL bảo thủ
T4: các thread còn lại dùng cùng token mới nếu còn usable
~~~

**Single-flight phải theo cache key** chứ không khóa toàn bộ token service. Nếu worker gọi Invoice API và Payment API với resource khác nhau, hai token acquisition có thể chạy độc lập. Một mutex toàn cục làm nghẽn throughput và tạo head-of-line blocking không cần thiết.

### Khi AS cấp token khác nhau giữa các instance?

Nếu client credentials grant giống nhau, mỗi instance có thể có **token riêng** cho cùng client và resource. Điều đó không tự sai. **Không phải mọi pod phải dùng cùng chuỗi token**. Dùng per-process cache tránh điểm tập trung bí mật, đơn giản hóa ownership và thường đủ cho hệ thống có số replica vừa phải.

Trong multi-region/auto-scaling mạnh, số token issuances có thể lớn; khi đó cân nhắc distributed cache/lease hoặc startup jitter. Nhưng chia sẻ bearer token giữa nhiều workload **tăng số nơi token được biết** và có thể phá sender-binding, nên phải cân nhắc rủi ro trước khi tối ưu.

## 8. Cache local, shared cache hay không cache?

| Chiến lược | Ưu điểm | Hạn chế và điều kiện |
|---|---|---|
| **Không cache** | Luồng logic đơn giản, không giữ token lâu ở client | Lãng phí AS, latency cao, dễ quota/issuance storm; không nên mặc định cho API gọi nhiều |
| **Memory cache theo process** | Nhanh, ít dependency, ít vùng chia sẻ secret | Mỗi pod tự xin token, mất cache khi restart; cần single-flight |
| **Distributed cache được bảo vệ** | Có thể giảm token issuance giữa nhiều replica | Lưu bearer token ngoài process, IAM/TLS/encryption/TTL và phân vùng context phải rất chặt |
| **Token broker/sidecar nội bộ** | Tập trung phát token/credential và policy, giảm lặp code | Broker là trust boundary quan trọng, cần identity, isolation và rate limiting |
| **Token cache của OAuth framework** | Ít mã tùy biến, tận dụng refresh/expiry logic đã có | Phải hiểu cache key/principal, storage, concurrency và error semantics của framework |

**Lựa chọn mặc định hợp lý** cho service M2M không quá lớn là **cache memory trong mỗi process + safety margin + single-flight + backoff**. Chỉ mở rộng sang shared cache/broker khi nhu cầu throughput/availability thực tế và threat model biện minh.

### Shared cache có thể làm lộ token qua các tenant/pod

Nếu dùng Redis/distributed cache:

- Mọi key phải phân biệt issuer/client/resource/scope/tenant và sender binding.
- Redis/transport cần TLS/ACL, mã hóa at rest/backup khi phù hợp, chính sách retention và chặn dump/debug.
- Không dùng một Redis role có thể đọc mọi tenant token nếu workload cần cô lập tenant.
- TTL Redis phải **ngắn hơn hoặc bằng usable deadline**, không lấy TTL dài mặc định.
- Không log/copy token vào message bus hoặc metric label.
- Nếu dùng DPoP/mTLS, chỉ share token cho nơi **có thể cung cấp đúng proof cùng key/cert**; nếu không thì chia sẻ đó vô ích hoặc sai.

### Tính nhất quán khi dùng distributed lock

Lock/lease cần timeout, fencing/version và xử lý khi holder crash. Một pod chết sau khi xin token nhưng trước khi ghi cache không được khiến toàn cụm kẹt vĩnh viễn. Một lock không còn hiệu lực không được ghi đè kết quả mới nếu có versioning. Không cấp quyền sử dụng token từ một cache entry không có metadata expiry hoặc context đáng tin chỉ vì “Redis đang có giá trị”.

## 9. Java/Spring Security: dùng OAuth2 Authorized Client Manager

Với Spring Security 6.x, việc cache token cho **client credentials** không nhất thiết phải tự viết OAuth token client. Có thể sử dụng **`OAuth2AuthorizedClientManager`**, `OAuth2AuthorizedClientService` và provider `clientCredentials()`. Các thành phần này quản lý một **authorized client** theo client registration/principal và hỗ trợ lấy access token khi cần.

### 9.1. Đăng ký M2M client

Ví dụ cấu hình **minh họa** cho Billing Worker:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          billing-as:
            token-uri: "https://auth.example.test/oauth2/token"
        registration:
          invoice-m2m:
            provider: billing-as
            client-id: "billing-worker"
            client-secret: "<inject-at-runtime-from-secret-manager>"
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - invoice:read
~~~

**Đừng commit client secret thật trong YAML/Git.** Placeholder được thay bằng credential quản lý bên ngoài, workload identity/KMS/secret manager khi chạy. Nếu AS hỗ trợ phương thức mạnh hơn (ví dụ `private_key_jwt` hoặc mTLS), cấu hình và client provider có thể khác.

`token-uri` phải lấy từ **AS đáng tin**, dùng HTTPS và certificate validation. `scope` được yêu cầu phải nằm trong quyền client đã được cấp. Nếu muốn yêu cầu `resource` theo **RFC 8707**, cần bảo đảm AS hỗ trợ và **OAuth client library gửi đúng tham số**; cấu hình `scope` không tự tạo resource indicator.

### 9.2. AuthorizedClientServiceOAuth2AuthorizedClientManager

Trong một service chạy ngoài HTTP request của người dùng (scheduled job, message consumer), `AuthorizedClientServiceOAuth2AuthorizedClientManager` thường phù hợp hơn một manager gắn với request/`HttpSession`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
class ServiceOAuth2Config {
    @Bean
    OAuth2AuthorizedClientManager serviceAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        var manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Gọi manager bằng **principal ổn định** đại diện **workload** (không phải một user ngẫu nhiên cho mỗi job):

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.core.OAuth2AccessToken;

final class InvoiceAccessTokenSupplier {
    private final OAuth2AuthorizedClientManager manager;

    InvoiceAccessTokenSupplier(OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    String accessToken() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("invoice-m2m")
                .principal("billing-worker")
                .build();

        OAuth2AuthorizedClient client = manager.authorize(request);
        if (client == null || client.getAccessToken() == null) {
            throw new IllegalStateException(
                "No authorized OAuth client for invoice-m2m");
        }

        OAuth2AccessToken token = client.getAccessToken();
        return token.getTokenValue();
    }
}
~~~

**Ví dụ minh họa, không phải ứng dụng chạy độc lập:** Cần Spring OAuth2 Client dependencies, `ClientRegistrationRepository` và `OAuth2AuthorizedClientService` phù hợp. Boot có thể tự cấu hình một số bean; không tạo bean thứ hai mâu thuẫn nếu app đã có. `OAuth2AuthorizedClientService` có thể dùng **in-memory** cho mỗi process hoặc persistence riêng, và cache entry thường được xác định theo client registration + principal.

Các giới hạn quan trọng:

- Manager/provider có xử lý authorized-client lifecycle/expiration nhưng **không có nghĩa mọi request đồng thời đã single-flight trên mọi process**. Kiểm concurrency semantics của phiên bản đang dùng và bổ sung coordination khi cần.
- `principal("billing-worker")` là **khóa logic để quản lý authorized client**, không phải danh tính một user đang đăng nhập. Nếu app cần token riêng cho tenant/resource, **phải phân vùng tương ứng**, không dùng một principal chung làm các context khác nhau ghi đè nhau.
- Việc trả `String` access token có thể làm credential xuất hiện trong memory; không log/trace giá trị hoặc đẩy nó vào URL.
- Khi Resource Server yêu cầu token **audience/resource cụ thể**, phải bảo đảm AS phát token với audience đó. Default registration `scope` chưa chắc đáp ứng mọi resource policy.
- `ClientRegistration` thông thường biểu diễn một bộ client authentication; khi đổi credential/khóa, thiết kế invalidation/reload manager và token cache theo chính sách.
- Với DPoP hoặc mTLS token binding, luồng request cần cung cấp đúng proof/key/cert. **Đoạn ví dụ Bearer này không tự hỗ trợ sender-constrained token.**

### 9.3. Khi nào cần tự xây TokenProvider?

Nếu hệ thống dùng token endpoint đặc thù (resource indicator, custom client assertion, token exchange, token broker) hoặc cần single-flight chặt theo cache key, có thể đóng gói lớp adapter riêng trên SDK OAuth đáng tin.

**Không tự viết toàn bộ OAuth protocol** chỉ vì muốn có cache: tận dụng thư viện cho token request, client authentication, parser, error handling, TLS, credential rotation; chỉ bổ sung **cache policy và concurrency** còn thiếu.

## 10. Mã giả token cache có single-flight theo context

Thiết kế dưới đây tách các thao tác **chọn ngữ cảnh, lấy token, lưu với deadline và xử lý invalidation**. Nó minh họa các bất biến nhưng không thay production implementation:

~~~text
function getToken(context):
    key = trustedCacheKey(
        issuer=context.trustedIssuer,
        client=context.verifiedClientRegistration,
        grant="client_credentials",
        audience=context.permittedResource,
        scopes=sortedAndCanonicalized(context.approvedScopes),
        tenant=context.verifiedTenantIfApplicable,
        senderKey=context.actualSenderBinding
    )

    entry = cache.get(key)
    if entry exists and entry.usableBefore > monotonicNow():
        return entry.accessToken

    future = inFlight.computeIfAbsent(key, () => {
        // Chỉ một caller thực hiện grant request cho mỗi key
        tokenResponse = oauthClient.requestClientCredentials(
            trustedEndpointFor(key.issuer),
            credentialFor(key.client),
            key.audience,
            key.scopes
        )

        if tokenResponse.invalid or tokenResponse.expiresIn <= 0:
            fail without storing token

        deadline = conservativeDeadline(
            tokenResponse.expiresIn,
            localRequestStartTime,
            safetyMargin,
            clockAndNetworkBudget
        )

        cache.put(key, tokenResponse.accessToken, deadline)
        return tokenResponse.accessToken
    })

    try:
        return future.awaitWithinBoundedTimeout()
    finally:
        inFlight.removeIfSame(key, future)
~~~

Một implementation thực tế cần:

- Chống **double fetch** khi nhiều thread cùng miss và không để exception làm future treo.
- Dùng **monotonic clock** cho khoảng thời gian bên trong process; xử lý `expiresAt`/epoch time từ SDK đúng cách khi tính hạn.
- Giới hạn `await` timeout, có cancellation/cleanup khi AS không đáp ứng; không giữ key khóa vĩnh viễn.
- Không giữ token cache ngoài context được xác minh, không dùng token mới dù response token type/scope không đúng hợp đồng.
- Khi 401 invalidation xảy ra song song với một request cấp token mới, tránh xóa nhầm bản token **mới** chỉ vì một response lỗi từ **token cũ** đến muộn.

### Conditional invalidation theo token identity

~~~text
Cache K hiện chứa A1.
Request R1 dùng A1 và đang chờ API.

Trong lúc đó:
  thread khác refresh -> cache K chứa A2.

R1 nhận 401 invalid_token (cho A1).

SAI:   cache.delete(K)               // vô tình xóa A2
ĐÚNG: cache.deleteIfValueIs(K, A1)   // chỉ invalidate bản đã thất bại
~~~

Trong production, nên dùng **version/token ID nội bộ** hoặc compare-and-set thay vì log/so sánh plaintext token ở nơi không cần thiết. Đây là lỗi race phổ biến ngay cả khi logic refresh bình thường đã single-flight.

### Stale-while-revalidate có an toàn không?

Trong cache nội dung web, `stale-while-revalidate` có thể chấp nhận dữ liệu cũ. Với **access token**, không được hiểu “stale” là **token đã hết hạn nhưng cứ gửi API trong lúc làm mới**. Nếu còn thời hạn AS/RS chấp nhận nhưng đã vượt **mốc refresh sớm**, client có thể tạm dùng token ấy **chỉ khi chính sách cho phép**, tính đủ độ trễ request và không có cờ revoke/invalidated.

Khi token đã expired hoặc bị biết là revoked, **không** tiếp tục gửi API chỉ để giữ uptime. An toàn quan trọng hơn việc bỏ qua kiểm hiệu lực.

## 11. JWT, opaque token và revocation khi có cache

Một M2M access token có thể là **JWT**:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "billing-worker",
  "aud": "invoice-api",
  "client_id": "billing-worker",
  "scope": "invoice:read",
  "iat": 1800000000,
  "exp": 1800000900,
  "jti": "token-illustration-001"
}
~~~

Đây chỉ là **payload minh họa**, chưa có chữ ký; việc có `sub` hoặc `client_id` cụ thể phụ thuộc token profile/AS. Trong `client_credentials`, subject không nhất thiết là một user; đừng dựa vào tên claim để tự tạo ngữ cảnh người dùng không có thật.

Invoice API phải kiểm chữ ký/khóa tin cậy, issuer, audience, token type/profile, expiry và scope, rồi kiểm quyền nghiệp vụ. Nếu dùng **opaque access token**, RS có thể gọi introspection theo **RFC 7662** để biết `active` và ngữ cảnh phù hợp. **Client token cache không khiến RS mặc định tin token**.

### Revoke token khi cache còn lưu bản cũ

Giả sử Billing Worker đã cache A1 còn 5 phút. Security Team vô hiệu grant/client credential ở AS. Có ba mốc khác nhau:

~~~text
T0: AS cấp A1, client cache token đến T0+14 phút.
T1: AS revoke grant/client credential.
T2: Worker vẫn giữ bản A1 trong memory.
T3: RS có thể hoặc không chấp nhận A1 theo cách RS kiểm revoke.
~~~

**Revoke client credential hoặc xóa token khỏi cache không đồng nghĩa mọi RS ngừng chấp nhận access token đã phát hành.** Với JWT RS kiểm offline, A1 có thể còn hợp lệ đến `exp` trừ khi RS kiểm denylist/grant version/điều kiện tương đương. Với opaque token dùng introspection, khả năng thu hồi phụ thuộc cache trạng thái ở RS.

Cache phía client nên có **cơ chế invalidation** sau credential rotation/revoke hoặc sự kiện an ninh, nhưng đó là **kiểm soát bổ sung**. AS và RS phải tự thực thi revocation policy cần thiết.

### Khi JWT có `exp` ngắn hơn `expires_in`?

Client không nên chọn mốc muộn hơn. Nếu thư viện đáng tin cho biết cả `expiresAt` và `expires_in`, hệ thống có thể dùng **giới hạn sớm nhất được xác minh** cộng safety margin. Không lấy JWT payload chưa xác minh từ nguồn bất kỳ rồi tự suy TTL “chắc chắn” cho token, vì client không phải nơi xác minh quyền của RS.

## 12. Cache token với sender-constrained access token

Trong bearer mode, việc biết chuỗi access token có thể đủ để gửi API khi token còn hạn. Với token được **ràng buộc người gửi**, request còn phải có bằng chứng khóa/chứng chỉ đúng.

| Loại token | Khi tái sử dụng từ cache | Khi chia sẻ sang pod khác |
|---|---|---|
| **Bearer access token** | Dùng chuỗi token đúng audience/scope/TTL | Pod khác có token string cũng có thể dùng được nếu RS chấp nhận; **tăng nguy cơ rò** |
| **DPoP-bound token** | Mỗi request cần DPoP proof ký bằng **private key** phù hợp với binding của token | Pod không có key thích hợp **không dùng được**; không nên copy key tùy tiện chỉ để share cache |
| **mTLS certificate-bound token** | Request phải dùng certificate/private key khớp binding tại RS | Pod có certificate khác có thể bị từ chối; cần xác định điểm mTLS termination và binding check |

Với **DPoP (RFC 9449)**, cache key phải gắn với **public-key thumbprint hoặc key identity** và policy của AS. Mỗi request tới RS cần proof phù hợp với method, URI và access token (các trường như `htm`, `htu`, `iat`, `jti`, `ath`), cùng cơ chế nonce/replay khi áp dụng. **Không cache một DPoP proof JWT dùng lại cho mọi request như access token**, vì proof thường gắn với request cụ thể và có cửa sổ thời gian/anti-replay.

Với **mTLS certificate-bound access token (RFC 8705)**, client/certificate binding là một phần của quyền sử dụng token. Nếu gateway kết thúc mTLS và truyền token tới backend bằng chứng chỉ khác, phải có điểm kiểm binding đúng và trust contract để tránh coi chứng chỉ hop sau là chứng chỉ caller gốc.

**PKCE không phải yêu cầu của `client_credentials` grant** vì không có authorization code qua browser cần bảo vệ; DPoP/mTLS client authentication/token binding có mục đích khác. Không thêm `code_verifier` vào token request M2M và tưởng đã làm token an toàn hơn.

## 13. Client credential rotation và phân vùng cache

Đối với M2M client, credential có thể là **client secret**, private-key JWT hoặc certificate. Khi đổi credential:

1. Tạo credential mới/đăng ký với AS theo phương thức được hỗ trợ.
2. Phân phối credential mới đến đúng workload thông qua secret manager/KMS/keystore.
3. Cập nhật token-acquisition client và kiểm AS cấp token mới đúng scope/audience.
4. Invalidate cache entries theo chính sách và bảo đảm request mới dùng credential/binding phù hợp.
5. Vô hiệu credential cũ ở AS khi cutover an toàn; kiểm các instance còn lại.
6. Xem xét **access token đã cấp trước đó**: chúng có thể vẫn còn hiệu lực tại RS nếu chưa bị revoke hoặc chưa `exp`.

### Không gắn token mặc định vào credential version một cách mù quáng

Một bearer access token đã phát hành trước khi **client secret** được rotate có thể vẫn hợp lệ trong thời hạn còn lại. Nhưng khi credential bị **nghi lộ**, policy có thể yêu cầu thu hồi các token/grant liên quan. Với DPoP/mTLS, thay private key/cert có thể khiến **token cũ ràng buộc với khóa/cert cũ** không thể dùng ở runtime mới.

Vì vậy cache cần tách:

- **Credential dùng xin token mới**: version/khóa nào được dùng xác thực với AS?
- **Token binding**: token đã được phát ràng buộc với key/cert nào?
- **Grant/issuer policy**: credential cũ có bị revoke và AS/RS có chặn token đã cấp không?

Một service restart không được fallback sang `client_secret` hardcode trong container khi secret manager lỗi. Có thể tận dụng token cache còn hiệu lực **trong giới hạn an toàn** nhưng không thể nới `exp` hoặc tắt kiểm TLS/RS chỉ để tránh gián đoạn.

## 14. Outage, backoff và graceful degradation

Trong một hệ thống microservice, cả AS, secret manager và RS đều có thể lỗi độc lập. Cache giúp giảm sự phụ thuộc trực tiếp vào AS trên **mỗi** lời gọi, nhưng không cho phép vượt giới hạn bảo mật.

| Sự cố | Cache có token đang usable | Cache trống/hết hạn |
|---|---|---|
| **AS tạm thời không khả dụng** | Có thể tiếp tục gọi RS bằng token hợp lệ, theo policy | Không gửi token cũ đã hết hạn; backoff/fail safely |
| **Secret manager outage** | Dùng token đã được cấp nếu còn hiệu lực, theo policy | Không dùng secret dự phòng hardcode; báo lỗi phụ thuộc |
| **RS trả 401 invalid_token** | Token cụ thể cần invalidate; có thể xin token mới **một lần** | Không lặp token issuance vô hạn |
| **RS trả 403 insufficient_scope** | Token không có quyền cần thiết; giữ nguyên chính sách | Không tự tăng scope hoặc thử client khác |
| **RS trả 503** | Token có thể vẫn hợp lệ; retry nghiệp vụ có giới hạn | Không coi 503 là lý do xin token mới mỗi lần |
| **Redis shared cache outage** | Có thể fallback **per-process cache hợp lệ** nếu kiến trúc cho phép và isolation đúng | Không tự chấp nhận cache entry không rõ expiry/key |
| **Lỗi xác thực client `invalid_client`** | Không tự suy token đang cache còn được RS chấp nhận mãi; kiểm chính sách sự cố | Dừng issuance nóng, cảnh báo và sửa credential |
| **Incident token leak** | Hủy cache entry nghi lộ và phối hợp AS/RS revoke | Không tự coi hành động xóa cache là hoàn tất revoke |

### Circuit breaker bảo vệ AS, không bỏ qua authorization

Một circuit breaker có thể tạm ngừng xin token mới khi AS liên tục lỗi, tránh mỗi request tiếp tục gây bão. Nhưng:

- Nếu **chưa có token hợp lệ**, request cần token phải thất bại an toàn.
- Không cấp một access token tự tạo từ client để thay AS.
- Không sử dụng token đã biết revoked/expired.
- Khi circuit mở trở lại, dùng backoff/jitter và single-flight để tránh đột ngột đẩy hàng nghìn token requests.

### Tránh cache poisoning và thừa quyền

Nếu service đọc token response từ một endpoint giả do DNS/proxy/URL injection, cache có thể giữ credential không đáng tin. Vì vậy:

- Token endpoint **cố định từ client registration tin cậy**, không lấy từ query/header do user cung cấp.
- TLS hostname/certificate verification bắt buộc; không bỏ kiểm khi gặp lỗi.
- AS trả token phải đúng loại/profile và scope/resource theo hợp đồng.
- Không dùng `client_id` tự khai từ HTTP request để chọn một client registration có quyền cao hơn.

## 15. Giám sát token cache và quyền riêng tư của log

Token cache cần có metrics để biết đang cải thiện hiệu năng hay tạo sự cố, nhưng **không bao giờ biến observability thành nơi lộ credential**.

| Metric / audit event | Ý nghĩa | Lưu ý |
|---|---|---|
| `token_cache_hit_total` / `miss_total` | Hiệu quả cache theo registration/resource | Nhãn thấp cardinality; không đưa token string vào label |
| `token_acquisition_duration` | Độ trễ xin token từ AS | Phân biệt thành công, timeout, OAuth error |
| `token_acquisition_inflight` | Số request đang xin token | Phát hiện stampede |
| `token_cache_entry_age` / `usable_seconds_remaining` | Tuổi và thời gian còn dùng được | Đo số gần expiry quá sát |
| `token_acquisition_429_total` | AS quota đang bị ảnh hưởng | Cần backoff/jitter, hạn chế client thay vì flood |
| `api_401_invalid_token_total` | Token có thể bị revoke/hết hạn/cấu hình sai | Phân biệt theo issuer/resource, không log bearer |
| `api_403_insufficient_scope_total` | Quyền grant không đủ | Không auto refresh để né quyền |
| `cache_invalidation_total` | Tần suất invalidation do expiry, 401, rotate, incident | Tránh đặt token ID làm metric label |
| `secret_read_failure_total` | Vấn đề secret manager/IAM | Không log client secret |

### Những trường không được ghi log

~~~text
NEVER LOG:
  Authorization: Bearer <raw-token>
  Authorization: Basic <raw-client-authentication>
  access_token=<raw-token>
  client_secret=<raw-secret>
  private_key=<key-material>
  DPoP: <signed-proof-jwt>
  refresh_token=<raw-token>

SAFE(r):
  event=oauth_token_cache_miss
  client_registration=billing-prod
  target_resource=invoice-api
  scope_class=invoice-read
  result=success
  request_id=<correlation-id>
~~~

Các nhãn như `tenant_id`, `principal_id` hay tên secret cũng có thể là dữ liệu nhạy cảm/có cardinality lớn. Chỉ ghi ở audit store có phân quyền khi thật sự cần, với retention phù hợp; không dùng `jti` hoặc token hash làm metric label công khai. Việc token là JWT có chữ ký **không khiến nội dung payload an toàn để ghi log**.

### Dấu hiệu cảnh báo

- Tỷ lệ cache miss tăng từ khoảng vài lần mỗi 15 phút lên hàng nghìn lần/phút.
- Tất cả pod cùng xin token ở một mốc tròn và AS trả 429.
- 401 `invalid_token` tăng ngay sau credential/certificate rotation.
- Một cache key duy nhất được dùng ở nhiều resource/tenant dù chính sách đòi phân vùng.
- Số token đang in-flight tăng nhưng không giảm sau timeout.
- Cache TTL dài hơn `expires_in`, hoặc token bị dùng sát `exp`.

Không tự đặt một SLO “90% cache hit” cho mọi ứng dụng: với batch worker hiếm khi chạy, việc cache ít hiệu quả là bình thường. Đặt SLO dựa trên tần suất gọi API, TTL, số replica và mức rủi ro thực tế.

## 16. Tình huống thực hành: 120 pod Billing Worker

Một hệ thống có:

~~~text
Authorization Server:
  issuer = https://auth.example.test
  POST /oauth2/token
  grant = client_credentials

Billing Worker:
  120 pod
  client_id = billing-worker
  resource = invoice-api
  scope = invoice:read
  average API calls = 40 requests/s mỗi pod

Access token:
  type = Bearer
  expires_in = 900 s (15 phút)
~~~

### 16.1. Nếu xin access token trước mỗi API request

Token issuance trung bình có thể gần bằng request rate:

\[
120\ \text{pod} \times 40\ \text{requests/s}
 = 4\,800\ \text{token requests/s}
\]

Ngoài tăng độ trễ, 4.800 token requests/s có thể vượt quota/token-signing throughput của AS. Nhiều JWT phát hành liên tục cũng tạo ra lượng log/audit và áp lực HSM/KMS không cần thiết.

### 16.2. Nếu mỗi pod cache một token và tái cấp khoảng 14 phút/lần

Với 120 pod, mỗi pod trung bình xin khoảng một token mỗi **840 giây**, lưu lượng cấp token lý tưởng xấp xỉ:

\[
\frac{120}{840}\approx 0.143\ \text{token requests/s}
\]

Đây là **ước tính trung bình lý tưởng**, giả sử một token dùng chung cho tất cả request thuộc **cùng context** mỗi pod, mỗi pod vẫn hoạt động và không có lỗi. Thực tế có startup, autoscale, token rejection và nhiều resource/scope; lưu lượng tức thời có thể cao hơn nhiều.

### 16.3. Còn “thundering herd” lúc 12:14?

Nếu 120 pod đều khởi động lúc 12:00 và cùng áp dụng refresh ở giây 840, AS có thể nhận **120 request trong một vài giây**. Cần **jitter refresh trước deadline, startup jitter và single-flight trong từng pod**. Nếu AS quota rất thấp, đánh giá thêm broker/cache phân tán **được bảo vệ**; không copy bearer token giữa mọi tenant chỉ để giảm số request.

### 16.4. Một pod nhận 401 invalid_token

Pod có thể invalidate **đúng token bản cũ** và xin một token mới, sau đó thử lại request **chỉ khi retry an toàn**. Không xóa cache của 119 pod khác một cách mù quáng và không biến 401 do sai audience thành vòng lặp xin token.

Nếu 401 xảy ra trên **mọi pod** sau AS key rotation, cần kiểm RS JWKS/issuer, token audience, AS/RS configuration và cache invalidation; chỉ tăng số lần token acquisition không giải quyết được lỗi trust boundary.

### 16.5. Nếu token bị lấy cắp từ log

Token là Bearer, nên attacker có thể dùng chuỗi token trong scope/audience và thời gian hiệu lực nếu RS chấp nhận. Cache không cung cấp bằng chứng người gửi. Ứng phó cần:

1. Ngừng log token và bảo vệ nguồn rò.
2. Phân loại token/issuer/client/resource/scope và thời hạn còn lại.
3. Thu hồi token/grant/credential theo khả năng AS và RS.
4. Kiểm audit truy cập Invoice API, phát hiện hành vi bất thường.
5. Giảm TTL/scope/audience và cân nhắc DPoP/mTLS nếu cần sender-constraining.

**Không xóa cache rồi tuyên bố token đã bị thu hồi**: bản sao ở tay attacker không biến mất khi worker xóa entry.

## 17. Ma trận kiểm thử token caching cho service calls

| Ca kiểm thử | Thiết lập/đầu vào | Kết quả kỳ vọng |
|---|---|---|
| **Cache miss lần đầu** | Chưa có token cho key K | Một token request hợp lệ; cache token theo deadline bảo thủ |
| **Cache hit** | Cùng issuer/client/resource/scope, token usable | Không gọi AS lại; gửi token phù hợp tới RS |
| **Cận expiry** | Token còn 30 giây, safety margin 60 giây | Không khởi tạo API request bằng token cũ; cấp token mới |
| **Token expired** | `exp`/`expires_in` quá hạn | Không dùng lại token cũ |
| **Hai resource** | Invoice API và Payment API cần audience khác nhau | Hai cache entries riêng, không token forwarding sai `aud` |
| **Scope khác** | `invoice:read` và `invoice:approve` | Không trộn token ngoài policy |
| **Issuer khác** | Hai AS dùng cùng chuỗi client ID | Cache phân vùng theo trusted issuer |
| **Tenant khác** | AS cấp token theo tenant riêng | Cache key theo tenant đã xác minh, không cross-tenant |
| **Client khác** | Hai client registrations cùng gọi API | Không chia token theo tên service chung |
| **100 thread miss cùng key** | Đồng thời gọi một process | Single-flight: chỉ một issuance thực tế theo key, còn lại chờ |
| **100 thread với nhiều key** | Nhiều resource/scope khác nhau | Các key có thể cấp token độc lập, không global lock quá rộng |
| **120 pod đồng loạt refresh** | Hết usable window cùng thời điểm | Jitter/rate limit; không gây issuance storm vượt chính sách |
| **Token response lỗi `invalid_client`** | Credential AS sai | Không cache token giả; không retry nóng |
| **Token response lỗi `invalid_scope`** | Scope chưa được phép | Không tự nâng quyền hoặc thử các scope rộng hơn |
| **Token endpoint 429** | AS rate limit | Backoff/jitter, tuân `Retry-After` khi có |
| **Token endpoint 503/timeout** | Có token cache còn usable | Có thể tiếp tục gọi RS với token hợp lệ theo policy |
| **AS lỗi, cache trống** | Không có credential hợp lệ | Fail safely, không bỏ token validation |
| **API trả 401 invalid_token** | Token A1 trong cache bị từ chối | Invalidate A1 đúng key, một lần acquire/retry có kiểm soát |
| **API trả 403 insufficient_scope** | Grant thiếu scope | Không refresh vô hạn, không tự tăng scope |
| **API trả 429 hoặc 503** | Quota/server issue | Không tự coi token sai; retry nghiệp vụ theo policy |
| **401 muộn của token A1** | Cache đã chuyển sang A2 | Không xóa A2; conditional invalidation |
| **Credential rotation** | Client secret/cert/key đổi | Reload/invalidate theo policy, không dùng binding cũ cho token mới |
| **DPoP-bound cache** | Pod khác không có private key | Không share token vô ích; RS kiểm proof mỗi request |
| **mTLS-bound cache** | Certificate pod khác | Không coi token ràng buộc cert A hợp lệ trên cert B |
| **JWT revoked nhưng còn `exp`** | RS offline-only vs RS kiểm denylist | Xác nhận đúng revocation propagation SLA, không giả định cache xóa là revoke |
| **Opaque introspection cache** | AS trả `active=false` sau revoke | RS xử lý theo chính sách, kiểm thời gian stale của introspection |
| **Non-idempotent POST retry** | API đã nhận request trước lỗi mạng | Không xử lý trùng giao dịch khi xin token mới/retry |
| **Token trong log/cache dump** | Kiểm APM, tracing, crash report, Redis backup | Không chứa raw token/client secret ngoài kho có policy |
| **Host/endpoint injection** | Caller thay token URL hoặc issuer trong query | Client dùng trusted registration, không gửi credential tới host lạ |

## 18. Checklist triển khai trước production

1. **Đúng grant và vai trò:** Đây là `client_credentials` cho service identity, không phải token đại diện end-user?
2. **Credential đúng chỗ:** Confidential client xác thực với AS qua secret manager/KMS/private key/mTLS; không hardcode credential trong Git/image?
3. **Token endpoint đáng tin:** HTTPS/TLS đúng hostname, issuer/registration cố định, error handling theo OAuth?
4. **Cache key đủ phân vùng:** Issuer, verified client, grant, audience/resource, scopes, tenant context (nếu có), sender-binding?
5. **TTL bảo thủ:** Dựa `expires_in`/trusted expiry, có margin cho network/clock/queue, không dùng token expired?
6. **Single-flight theo key:** Không phát 100 token requests khi 100 thread cùng miss; exception có giải phóng waiters?
7. **Multi-replica có chiến lược:** Per-process cache đủ chưa; có startup jitter, rate limiting, không share token bừa?
8. **Không nhầm token format:** JWT hay opaque đều cache được; Resource Server vẫn kiểm token, không dựa vào client cache?
9. **401/403 đúng:** `invalid_token` có invalidate token cũ và retry tối đa phù hợp; `insufficient_scope` không tự tăng quyền?
10. **Safe retries:** POST hoặc tác vụ không idempotent có cơ chế phòng xử lý trùng khi gặp timeout/401?
11. **Revocation có SLA:** AS revoke có thật sự đến RS qua introspection/denylist/grant check trước deadline cần thiết?
12. **Refresh token không mặc định:** `client_credentials` thường không cấp refresh token; client xin token mới bằng credential?
13. **Sender-bound token đúng key:** DPoP/mTLS proof được cung cấp ở mỗi API call; cache gắn với key/cert, không share sai?
14. **Không dùng stale token trái policy:** AS outage không làm kéo dài `exp`, không fail-open TLS/authentication/authorization?
15. **Credential rotation có kế hoạch:** Secret/key/cert đổi được cập nhật ở AS, workload và cache; token cũ được xử lý theo policy?
16. **Quan sát an toàn:** Hit/miss, issue latency, 401/403/429, in-flight, expiry; log không có raw token, secret hay private key?
17. **Kiểm quyền RS:** `iss`, chữ ký/introspection, `aud`, `exp`, `scope`, role/tenant/object được kiểm độc lập với cache?
18. **Thử kịch bản âm tính:** Cache nhầm audience, token bị revoke, 401 muộn, thread/pod race, secret rotation, Redis outage và stolen bearer token?

**Ghi nhớ:** **Token caching cho service calls là cách giữ access token M2M vừa đủ lâu để tái sử dụng, nhưng luôn trong giới hạn issuer, client, resource, scope, binding và expiry**. Cache tốt giúp giảm độ trễ, tải AS và nguy cơ token-issuance storm; cache sai có thể dùng nhầm token giữa API/tenant, giữ credential quá hạn hoặc làm rò bearer token tới quá nhiều process. Với grant `client_credentials`, client thường **xin access token mới bằng credential**, không dựa vào refresh token. Cuối cùng, **Authorization Server quyết định cấp token, Resource Server quyết định chấp nhận token và quyền dữ liệu, còn cache chỉ quyết định token hợp lệ nào được client tái sử dụng**.

### Chuẩn và tài liệu tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** `client_credentials`, client authentication, `expires_in`, token endpoint và việc refresh token thông thường không được cấp trong grant này.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** truyền access token qua `Authorization`, lỗi `invalid_token`/`insufficient_scope` và an toàn bearer token.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ OAuth credentials, access token, refresh token và giảm rủi ro token theft.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** request token hướng tới resource dự kiến.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** định dạng/claims và các quy tắc resource server kiểm JWT access token.
- **RFC 7519 — JSON Web Token (JWT):** `iss`, `aud`, `exp` và các JWT claims.
- **RFC 7662 — OAuth 2.0 Token Introspection:** kiểm trạng thái và ngữ cảnh opaque/reference token tại RS.
- **RFC 7009 — OAuth 2.0 Token Revocation:** AS revoke token/grant, khác việc xóa token cache ở client.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** mTLS client authentication và access token binding.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** ràng buộc access token với khóa người gửi, proof theo request.
- **Spring Security Reference — OAuth2 Client / Authorized Client Manager:** `OAuth2AuthorizedClientManager`, `AuthorizedClientServiceOAuth2AuthorizedClientManager` và provider `clientCredentials()`.
