# Bảo vệ Token Endpoint bằng giới hạn tốc độ, timeout và chống lạm dụng

## 1. Bối cảnh: Token Endpoint là điểm nóng bảo mật và hiệu năng

Trong một **OAuth 2.0/OpenID Connect (OIDC) Authorization Server** xây dựng bằng **Spring Security**, **Spring Authorization Server** và Spring Boot, **Token Endpoint** thường được đặt tại `POST /oauth2/token`. Đây là nơi các OAuth client yêu cầu phát hành access token, đổi authorization code, dùng refresh token hoặc gọi những grant khác được hỗ trợ.

Khác với trang đăng nhập người dùng, Token Endpoint phục vụ **các request giao thức** từ client, thường là backend service hoặc ứng dụng dùng OAuth client library. Nó phải xác minh dữ liệu nhạy cảm như client secret, JWT client assertion, authorization code, refresh token và các điều kiện grant. Vì vậy, Token Endpoint có thể bị khai thác theo hai hướng cùng lúc:

- **Bảo mật:** đoán credential, thử lại authorization code, dò refresh token, lạm dụng grant, xin token với scope không được phép.
- **Khả dụng:** dồn request khiến authentication provider, cơ sở dữ liệu authorization, cache, KMS/HSM ký JWT và thread pool cạn tài nguyên.

Ví dụ, hệ thống đặt phòng có `booking-bff` dùng Authorization Code + PKCE, `billing-service` dùng Client Credentials và `partner-service` dùng refresh token. Nếu một client lỗi cứ xin token mới cho mỗi API call, Token Endpoint có thể quá tải ngay cả khi không có kẻ tấn công. Ngược lại, kẻ tấn công có thể dùng hàng nghìn request `invalid_client` để cố dò secret hoặc tiêu hao tài nguyên xác thực.

**Mục tiêu không phải chặn càng nhiều càng tốt.** Thiết kế cần bảo vệ Token Endpoint nhưng vẫn duy trì khả năng sử dụng của client hợp lệ, hạn chế false positive, giữ chuẩn OAuth/OIDC và cung cấp tín hiệu vận hành đủ để xử lý sự cố.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện các kiểu lạm dụng và điểm tiêu hao tài nguyên của Token Endpoint.
2. Thiết kế **rate limiting nhiều tầng**, với các khóa giới hạn có ranh giới tin cậy rõ.
3. Phân biệt **rate limit**, **concurrency limit**, **request timeout**, **dependency timeout** và **circuit breaker**.
4. Cấu hình `SecurityFilterChain` và thêm filter HTTP có phạm vi hạn chế mà không thay thế xác thực OAuth.
5. Chọn phản hồi `429 Too Many Requests`, `Retry-After` và OAuth error phù hợp.
6. Bảo vệ từng nhóm grant: Authorization Code + PKCE, Refresh Token, Client Credentials và các extension grant.
7. Xây dựng chiến lược chống credential stuffing, replay, token acquisition storm và lạm dụng client authentication.
8. Kiểm thử giới hạn, timeout, concurrency, nhiều instance và khả năng phục hồi.
9. Vận hành bằng metrics, tracing, alert và audit không làm lộ credential.

## 2. Ranh giới chức năng của Token Endpoint

Token Endpoint có thể nhận một request điển hình:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_OF_CLIENT_ID_AND_SECRET
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=inventory.read
```

Đây là ví dụ một confidential client. Các grant khác có thể dùng body như:

```text
authorization_code:
  grant_type=authorization_code
  code=...
  redirect_uri=...
  code_verifier=...

refresh_token:
  grant_type=refresh_token
  refresh_token=...

client_credentials:
  grant_type=client_credentials
  scope=...

token_exchange:
  grant_type=urn:ietf:params:oauth:grant-type:token-exchange
  subject_token=...
  subject_token_type=...
```

**Các tham số chỉ là minh họa**; yêu cầu chính xác phụ thuộc loại client, grant, token/subject type và phiên bản Spring Authorization Server.

### 2.1. Những lớp cùng tham gia xử lý

```mermaid
flowchart TB
    OUT["OAuth Client / Internet"]
    EDGE["Gateway / WAF / Load Balancer<br/>TLS, body cap, rate limit, connection limit"]
    IP["Ứng dụng Spring Security<br/>Pre-auth ingress limiter"]
    CA["OAuth2 Client Authentication<br/>Xác minh client credential"]
    POLICY["Authenticated-client policy<br/>grant/tenant/quota"]
    ENDPOINT["OAuth2 Token Endpoint<br/>converter + provider"]
    BACK["Repositories, DB, Cache, HSM/KMS<br/>dependency timeout / bulkhead"]
    TOKEN["Token generation + persistence"]
    RESPONSE["OAuth response hoặc 429/5xx có kiểm soát"]

    OUT --> EDGE --> IP --> CA --> POLICY --> ENDPOINT
    ENDPOINT --> BACK --> TOKEN --> RESPONSE
```

Sơ đồ là kiến trúc tham khảo. Trong framework, authentication filter, provider, authorization service và token generator có thứ tự thực thi cụ thể theo cấu hình. **Giới hạn trước xác thực** có thể chạy từ gateway hoặc một servlet filter; **chính sách theo client đã được xác thực** phải dùng danh tính tin cậy của client, không chỉ tên client do request tự khai.

### 2.2. Phân biệt bốn lớp kiểm soát

| Kiểm soát | Trả lời câu hỏi | Thực hiện ở đâu? |
|---|---|---|
| **Rate limit** | Một nguồn được gửi bao nhiêu request trong một khoảng thời gian? | Gateway, limiter ở AS, quota theo client |
| **Concurrency limit / bulkhead** | Một thời điểm tối đa bao nhiêu request hoặc tác vụ nặng được xử lý? | Gateway, thread pool, semaphore/queue có giới hạn, dependency |
| **Timeout / deadline** | Một request hoặc lời gọi phụ thuộc được chờ tối đa bao lâu? | Gateway, servlet infrastructure, HTTP/DB/KMS client |
| **Circuit breaker / overload shedding** | Khi dependency hỏng/quá tải, có tiếp tục gửi mọi yêu cầu tới nó không? | Service integration, dependency client, gateway |

Chỉ có rate limit **không đủ** khi một số request rất chậm. Chỉ đặt timeout cũng không đủ khi hàng nghìn request ngắn liên tiếp làm cạn tài nguyên xác thực.

## 3. Mô hình đe dọa và hành vi lạm dụng

| Dạng lạm dụng | Ví dụ | Rủi ro | Phòng vệ trọng tâm |
|---|---|---|---|
| Credential stuffing | Liên tục thử `client_id`/`client_secret` khác nhau | Chiếm confidential client | Rate limit trước và sau xác thực, phát hiện thất bại, credential hygiene |
| JWT client assertion flooding | Gửi JWT sai chữ ký hoặc `kid` không tồn tại | Tiêu hao CPU, JWKS/network cache | Giới hạn đầu vào, trust store, negative caching có kiểm soát |
| Authorization code guessing/replay | Đổi code sai hoặc dùng lại code đã đổi | Phát token trái phép nếu thiếu validation | Code ngẫu nhiên, TTL ngắn, single-use, PKCE, rate limit |
| Refresh token brute force | Gửi refresh token giả hoặc đã bị thu hồi | Đoán credential, token replay | State validation, rotation/reuse detection, rate limiting |
| Token acquisition storm | Client Credentials xin token ở mỗi API request | Quá tải AS | Cache token phía client, quota, jitter và backoff |
| Grant spraying | Thử nhiều `grant_type` trên cùng endpoint | Dò khả năng cấu hình/client | Registered grant policy, error ổn định, anomaly detection |
| Scope probing | Lặp request với scope hoặc audience nhạy cảm | Thu thập policy/thử nâng quyền | Client registration, audience policy, không trả chi tiết nhạy cảm |
| Request body exhaustion | Body form quá lớn, nhiều tham số lặp | Tốn bộ nhớ/CPU parser | Body size limit, parameter count cap, timeout |
| Connection/slow request exhaustion | Mở nhiều kết nối hoặc gửi rất chậm | Cạn connection/thread | TLS termination, read/idle timeout, connection limit |
| Expensive backend amplification | Request kích hoạt database/KMS/remote JWK liên tục | Cạn pool và quota phía sau | Timeout, bulkhead, cache, per-operation quota |
| Distributed abuse | Nhiều IP/region đánh vào cùng client | Vượt giới hạn theo IP đơn lẻ | Phát hiện theo client và tín hiệu rủi ro kết hợp |

Không phải mọi lỗi `invalid_client` đều là tấn công. Secret rotation chưa hoàn tất hoặc cấu hình sai cũng tạo lượng lớn request lỗi; hệ thống nên có cảnh báo và điều tra thay vì khóa vĩnh viễn client ngay lần đầu.

### 3.1. Threat model theo từng lớp

**Ở edge:** nguồn gửi có thể giả mạo hoặc thay đổi IP, tự khai header và tạo request sai chuẩn. Đừng giả định mọi request đã có client identity đáng tin.

**Ở client authentication:** secret/JWT assertion/mTLS phải được xác minh độc lập. Dùng client ID do request tự khai làm căn cứ **duy nhất** cho quota có thể bị lợi dụng để làm cạn quota của client khác.

**Ở grant validation:** cần giữ các bảo đảm sẵn có của Spring Authorization Server, đặc biệt PKCE, redirect URI, ownership của authorization code, single-use, refresh token state và scope.

**Ở storage/token generation:** database connection, cache I/O và ký JWT/HSM đều là tài nguyên có giới hạn. Một request từ nguồn ít tốn network có thể gây nhiều công việc backend nếu kiểm soát đặt sai tầng.

## 4. Nguyên tắc thiết kế phòng vệ nhiều tầng

Một thiết kế nên áp dụng **defense in depth**:

1. **Trước ứng dụng:** TLS, giới hạn kết nối, kích thước request, tốc độ theo nguồn đã chuẩn hóa, chặn request rõ ràng bất thường.
2. **Trước OAuth client authentication:** chặn đợt request dày từ mạng/nguồn chưa xác thực để giảm công việc xác minh credential.
3. **Sau khi xác thực client:** quota theo client identity đáng tin, grant type và policy tenant/môi trường.
4. **Trước công việc đắt đỏ:** giới hạn đồng thời/timeout cho database, introspection, signer, khóa và các external services.
5. **Phản hồi:** giữ OAuth error semantics khi validation thất bại, trả tình trạng quá tải rõ ràng và hướng dẫn retry có giới hạn khi thích hợp.
6. **Quan sát:** ghi lượng request được cấp/từ chối, latency, hàng đợi, retry và lỗi credential mà không log bí mật.
7. **Ứng cứu:** có cơ chế hạ quota, vô hiệu hóa credential, giảm tải hoặc cô lập một client đang bị lạm dụng.

**Không có một bộ giới hạn chung hoàn hảo cho mọi deployment.** Chính sách cần được xây từ dữ liệu baseline, threat model, mô hình client và mức độ quan trọng của hệ thống.

### 4.1. Vì sao rate limit chỉ theo IP là chưa đủ?

Một IP có thể là:

- NAT chia sẻ cho hàng nghìn người dùng hợp lệ.
- Egress gateway của nhiều microservice.
- Proxy/load balancer mà mọi request đi qua.
- IP luân chuyển của client hợp lệ hoặc botnet.
- Địa chỉ IPv6 với chiến lược privacy rotation.

Giới hạn chỉ theo IP có thể khóa nhầm nhiều client hợp lệ hoặc bị vượt qua khi attacker thay nguồn. Nhưng giới hạn chỉ theo `client_id` do người gửi tự khai cũng nguy hiểm, vì attacker có thể dùng ID của client nạn nhân để làm cạn quota (*quota exhaustion attack*).

**Giải pháp:** Dùng một lớp pre-auth theo network/request fingerprint đã được kiểm soát, rồi thêm lớp post-auth dựa trên **client identity đã xác thực**, kết hợp quota phù hợp grant/resource. Không nhầm hai lớp này.

## 5. Chọn rate-limit key mà không cho kẻ tấn công tự quyết định

| Giai đoạn | Key có thể sử dụng | Mức tin cậy | Cảnh báo |
|---|---|---|---|
| Gateway/edge | IP thực được proxy tin cậy suy ra, network range, TLS identity | Phụ thuộc cấu hình gateway | Tránh dùng raw `X-Forwarded-For` không được bảo vệ |
| Pre-auth ở AS | Source IP đã chuẩn hóa, gateway-issued request identity | Chưa chứng minh OAuth client | Cần công bằng với NAT/proxy |
| Sau client authentication | Registered client ID/internal ID đã được xác minh | Cao hơn | Không dùng client ID lấy thẳng từ body làm bằng chứng |
| Theo grant | Authenticated client + grant type đã parse | Phụ thuộc parsing/validation | Tránh tách quá nhiều key làm tăng cardinality |
| Theo tenant/workload | Authenticated client + tenant đáng tin | Cao nếu tenant binding hợp lệ | Không lấy tenant ID tự khai rồi tin ngay |
| Theo credential failure | Nguồn + loại lỗi/credential identifier an toàn | Cần privacy review | Không lưu raw secret/JWT assertion như cache key |

Ví dụ chính sách minh họa:

```text
Layer A: ingress source -> giới hạn tổng request trước authentication
Layer B: authenticated client -> quota token requests
Layer C: authenticated client + grant -> quota theo loại grant
Layer D: signing/DB dependency -> max concurrency và deadline
```

Các giới hạn cần phối hợp. Nếu chỉ Layer B được triển khai, request dùng secret sai **không đạt tới trạng thái authenticated client** vẫn có thể tiêu hao CPU xác minh không bị giới hạn theo client.

### 5.1. Không tạo metric/cardinality không kiểm soát

Đừng đưa raw IP, `client_secret`, refresh token hoặc toàn bộ client-generated identifier vào nhãn metric. Các hệ thống Prometheus/metrics thường khó chịu tải khi hàng triệu giá trị khác nhau xuất hiện.

Với security audit chi tiết, có thể lưu source identifier đã chuẩn hóa theo retention và quyền truy cập; metric tổng hợp nên phân nhóm theo grant, outcome, endpoint hoặc nhóm client với cardinality được giới hạn.

## 6. Thuật toán rate limiting thường dùng

### 6.1. Token bucket

Token bucket có:

- `capacity = B`: số request có thể xử lý trong một đợt ngắn.
- `refillRate = r`: số token được bổ sung mỗi giây.
- Một request hợp lệ tiêu thụ một lượng token; nếu không đủ thì bị từ chối.

```mermaid
flowchart LR
    IN["Token Request"] --> BUCKET{"Bucket còn token?"}
    BUCKET -->|"Có"| TAKE["Trừ token nguyên tử"] --> PROCESS["Tiếp tục pipeline"]
    BUCKET -->|"Không"| LIMIT["429 + Retry-After"]
    REFILL["Refill theo thời gian"] --> BUCKET
```

Token bucket cho phép một **burst** nhỏ nhưng bảo đảm tốc độ trung bình theo cấu hình. Ví dụ `B=20` và `r=2 request/giây` cho phép tối đa khoảng 20 request ngay lúc bucket đầy, sau đó bổ sung 2 token/giây.

Đây là **mô hình minh họa**, không phải quota khuyến nghị cho production. Chọn `B` và `r` từ baseline thực và mức tải backend chấp nhận được.

### 6.2. Sliding window và fixed window

| Cơ chế | Ưu điểm | Hạn chế |
|---|---|---|
| **Fixed window** | Đơn giản, dễ tính | Có thể có burst lớn ngay sát ranh giới hai cửa sổ |
| **Sliding window** | Giảm hiệu ứng ranh giới, công bằng hơn | Cần lưu trạng thái/thời gian phức tạp hơn |
| **Token bucket** | Hỗ trợ burst và tốc độ trung bình có kiểm soát | Cần thao tác cập nhật state nguyên tử |
| **Leaky bucket / queue** | Làm mượt lưu lượng ở một số hệ thống | Queue dài có thể tăng latency và tiêu tốn memory |
| **Concurrency semaphore** | Chặn quá nhiều tác vụ nặng cùng lúc | Không tự giới hạn tổng số request trên thời gian |

Không nên dùng hàng đợi không giới hạn trước một endpoint nhạy cảm. Một request chờ quá lâu vẫn giữ tài nguyên và có thể khiến client retry tạo ra nhiều request trùng lặp.

### 6.3. Weighted cost cho các thao tác khác nhau

Một lần kiểm tra client secret cục bộ có chi phí khác với việc:

- Xác minh client assertion bằng khóa công khai và tải JWKS.
- Tra refresh token trong database.
- Gọi remote introspection của một subject token.
- Ký token qua HSM/KMS.
- Ghi authorization với transaction.

Có thể áp dụng **weighted cost** theo grant hoặc đường xử lý sau khi parsing và xác thực các thuộc tính cần thiết. Ví dụ một thao tác remote signing tiêu tốn nhiều quota hơn một kiểm tra sớm bị từ chối.

Điều này đòi hỏi kiểm thử kỹ, vì attacker có thể cố gửi một loại grant tốn kém để đốt quota của client khác. Phân loại chi phí phải dựa trên tín hiệu đáng tin và chính sách chống quota poisoning.

## 7. Rate limit trong môi trường nhiều instance

Nếu Token Endpoint chạy trên 5 pod mà mỗi pod có bucket riêng giới hạn 100 request/phút, tổng lưu lượng có thể vượt xa 100 request/phút khi load balancer phân phối request.

### 7.1. Hai mô hình vận hành

**Mô hình A — Local per-node limiter:**

- Nhanh, không phụ thuộc network.
- Phù hợp giới hạn bảo vệ CPU/thread cục bộ.
- **Không bảo đảm quota toàn cụm**, nhất là khi autoscale.

**Mô hình B — Shared/distributed limiter:**

- State/quota được chia sẻ giữa các node, ví dụ gateway hỗ trợ distributed rate limiting hoặc Redis với thao tác nguyên tử.
- Phù hợp quota thực sự theo client trên toàn cụm.
- Cần xử lý Redis outage, replication lag, key cardinality và tính nhất quán giữa region.

Đối với Redis, thao tác “đọc counter → tăng → ghi lại” không nguyên tử có thể vượt quota khi nhiều node gọi đồng thời. Ưu tiên cơ chế atomic script/transaction hoặc rate-limiter đã được kiểm thử.

### 7.2. Fail-open hay fail-closed khi limiter store lỗi?

Không có câu trả lời chung:

| Chế độ | Kết quả khi limiter unavailable | Rủi ro |
|---|---|---|
| **Fail-open** | Cho request tiếp tục | Có thể tăng tải/tạo cửa sổ abuse, đặc biệt khi AS đang bị tấn công |
| **Fail-closed** | Từ chối/giảm request | Có thể gây outage cho toàn bộ client dù AS còn hoạt động |
| **Fallback quota cục bộ** | Chuyển sang hạn chế tại node | Quota toàn cụm bị lệch, cần đánh giá capacity và alert |

Nên phân biệt **ingress limiter không phải điều kiện xác thực bắt buộc** với **client authorization policy**. Lỗi của service xác thực client/validation không được biến thành “cho qua” chỉ vì muốn tăng availability.

### 7.3. Các vùng và region

Rate limiting trên nhiều region có thể có trạng thái **eventual consistency**; quota hiển thị như toàn cục nhưng thực tế sai lệch trong thời gian network partition. Với hệ thống cần hạn cứng, cần thiết kế consistency/cost phù hợp, không hứa quota tuyệt đối dựa trên cache replication bất đồng bộ.

## 8. Chính sách quota theo grant và loại client

Một hệ thống có thể xác định chính sách tham khảo như:

| Nhóm request | Ví dụ nhu cầu hợp lệ | Định hướng kiểm soát |
|---|---|---|
| **Client Credentials** | Dịch vụ nền xin token định kỳ | Khuyến khích cache access token; phát hiện token storm |
| **Authorization Code** | Callback sau login | Burst ngắn hợp lệ, bảo vệ code/PKCE; tránh rate limit khiến login bị gián đoạn hàng loạt |
| **Refresh Token** | Client gia hạn access token | Kiểm soát tốc độ/replay và rotation state |
| **Token Exchange** | Dịch vụ xin token cho downstream API | Kiểm tra target/subject policy, cost của validation |
| **JWT private_key authentication** | Client ký assertion khi xin token | Giới hạn CPU/JWKS lookup, cache trusted keys |
| **Extensions grant** | Luồng grant tự định nghĩa | Quota riêng theo chi phí và threat model |

Ví dụ chính sách ban đầu **chỉ để minh họa**:

```yaml
token-endpoint:
  limits:
    ingress-per-source:
      burst: 100
      refill-per-second: 10
    authenticated-client:
      burst: 60
      refill-per-second: 3
    expensive-grant:
      max-concurrent: 8
```

**Đây là YAML nghiệp vụ giả định**, không phải property được Spring Authorization Server hoặc Spring Boot tự nhận diện. Muốn áp dụng phải triển khai limiter/gateway tương ứng và điều chỉnh bằng load test.

### 8.1. Không ưu tiên client quan trọng bằng cách tắt mọi giới hạn

Một service quan trọng có thể cần quota cao hơn hoặc capacity được dành riêng. Nhưng “unlimited” trên Token Endpoint có thể cho một client lỗi chiếm toàn bộ HSM, database pool hoặc thread pool.

Có thể dùng **fair scheduling**, quota theo nhóm client và bulkhead; khi quá tải, hệ thống vẫn phải dành năng lực cho những request có mức ưu tiên cao theo policy mà không đánh đổi xác thực đúng.

### 8.2. Đếm request thành công hay tất cả request?

Nếu chỉ đếm **request phát token thành công**, credential stuffing bằng secret sai có thể bỏ qua quota. Nếu chỉ dùng một quota chung cho mọi request, attacker có thể gây khóa client hợp lệ bằng request giả mang `client_id` của client đó.

Nên có:

- Pre-auth quota đếm **mọi request đến** theo nguồn mạng đáng tin.
- Post-auth quota đếm request theo **client đã xác thực**.
- Counter/anomaly riêng cho **authentication failures** và lỗi grant, không biến dữ liệu chưa xác thực thành quyền khóa vĩnh viễn client khác.

## 9. HTTP 429, `Retry-After` và lỗi OAuth

HTTP `429 Too Many Requests` báo client đã vượt giới hạn lưu lượng. Header `Retry-After` có thể chỉ thời gian khuyến nghị chờ trước khi thử lại.

Ví dụ:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 15
Cache-Control: no-store
Content-Type: application/json

{
  "error": "rate_limited"
}
```

**Quan trọng về tương thích:** `rate_limited` ở ví dụ là **mã lỗi mở rộng**, không thuộc bộ mã lỗi chuẩn của OAuth 2.0 Token Endpoint theo RFC 6749. Nếu API/gateway dùng nó, client phải được thiết kế để hiểu response đó. Một số OAuth client libraries mong đợi phản hồi lỗi có dạng OAuth khi HTTP khác 2xx; cần kiểm thử khả năng tương thích và contract công khai.

### 9.1. Đừng trộn lỗi bảo mật với lỗi quá tải

| Tình huống | Phản hồi phù hợp | Lưu ý |
|---|---|---|
| Client credential sai | `invalid_client` theo OAuth; thường HTTP 401 khi yêu cầu client authentication tương ứng | Không trả “secret sai ký tự thứ 3” |
| Authorization code sai/hết hạn/đã dùng | `invalid_grant` | Không cấp token; giữ single-use |
| Client không được dùng grant | `unauthorized_client` | Không sửa thành rate-limit error |
| Scope không được phép | `invalid_scope` | Không tự nâng quyền |
| Request thiếu/sai tham số | `invalid_request` | Không tiết lộ nội bộ |
| Hết quota request | `429` + `Retry-After` nếu có thể | Client cần retry có giới hạn |
| AS/dependency tạm quá tải | `503 Service Unavailable` hoặc lỗi hạ tầng phù hợp | Bảo vệ capacity, tránh retry storm |
| Một request xử lý quá thời hạn | Timeout/`504` ở proxy hoặc lỗi phù hợp | Không chắc token đã được cấp hay chưa |

Thứ tự các lớp kiểm tra ảnh hưởng kết quả: request bị chặn tại ingress limiter **trước client authentication** có thể trả 429 ngay cả khi credential cũng sai. Đó là trade-off có chủ đích của bảo vệ quá tải; không có nghĩa validator được bỏ qua cho request tiếp tục vào pipeline.

### 9.2. `slow_down` không phải mã rate limit chung

OAuth Device Authorization Grant có lỗi `slow_down` dành cho cơ chế polling theo RFC 8628. Không nên dùng `slow_down` như một mã rate limiting chung cho **mọi** `grant_type` tại Token Endpoint.

### 9.3. `Retry-After` có giới hạn gì?

`Retry-After` có thể biểu diễn **số giây** hoặc **HTTP-date** theo HTTP. Client nên tôn trọng giá trị hợp lệ và áp dụng backoff/jitter, nhưng không retry vô hạn hoặc chia sẻ một deadline vô hạn trên nhiều worker.

Nếu quota theo client/tenant, cần tránh trả chi tiết revealing về danh sách client hay trạng thái quota của người khác.

### 9.4. Không gửi token trong lỗi

Response 429/5xx không được chứa `access_token`, `refresh_token`, `authorization_code`, client secret hoặc stack trace. Không thêm response header debug chứa raw credential.

## 10. Timeout: đặt deadline cho từng lớp, không chỉ một property

Một request/token issuance có thể đi qua gateway → servlet container → Spring Security → authentication provider → database/cache → signer KMS/HSM → response.

```mermaid
flowchart LR
    G["Gateway deadline"]
    S["Servlet request budget"]
    D["DB/Redis operation timeout"]
    K["KMS/HSM/remote JWT/JWKS timeout"]
    O["Outcome / cancellation / monitoring"]

    G --> S --> D --> K --> O
```

Sơ đồ không có nghĩa tất cả lời gọi phụ thuộc chạy tuần tự; hệ thống thật có thể gọi các dependency song song.

### 10.1. Các timeout dễ nhầm

| Loại timeout | Nó bảo vệ gì? | Không bảo đảm |
|---|---|---|
| **TLS handshake/connection timeout** | Không để kết nối tạo mới chờ vô hạn | Không giới hạn thời gian xử lý business logic đã vào endpoint |
| **Idle/read timeout tại proxy** | Chống client gửi dữ liệu quá chậm hoặc kết nối treo | Không tự hủy mọi tác vụ DB sau khi proxy bỏ request |
| **Gateway upstream response timeout** | Hạn chờ phản hồi từ AS | Không chắc DB/HSM phía AS đã ngừng làm việc |
| **Servlet async request timeout** | Request xử lý bất đồng bộ theo cơ chế servlet | Không áp dụng như một deadline tổng quát cho mọi filter/controller đồng bộ |
| **DB statement/query timeout** | Câu lệnh DB chạy quá lâu | Không tự đặt timeout cho remote KMS hoặc toàn bộ request |
| **Connection-pool acquire timeout** | Thời gian chờ lấy connection | Không thay thế query timeout sau khi đã lấy connection |
| **HTTP client connect/read timeout** | Remote introspection/JWKS/IdP/KMS HTTP calls | Không bảo đảm request ngoài có tính idempotent |
| **Concurrency/bulkhead timeout** | Thời gian chờ slot xử lý | Không thay thế OAuth validation |

Đặc biệt, cấu hình `server.tomcat.connection-timeout` thường liên quan thời gian chờ kết nối/đọc request ở servlet container. **Không được coi đây là “Token Endpoint sẽ xử lý xong trong đúng N giây”.**

### 10.2. Thiết kế một time budget

Giả sử gateway có giới hạn phản hồi 4 giây. Có thể đặt ngân sách minh họa:

| Thành phần | Mục tiêu giới hạn tham khảo |
|---|---|
| Tổng thời gian tới client | 4 giây |
| Xử lý ở AS trước dependency nặng | Ngân sách nhỏ, có capacity guard |
| DB connection acquire | Tối đa 300 ms |
| Một DB query quan trọng | Tối đa 800 ms |
| Remote signer/KMS | Tối đa 1 giây |
| Remote trust lookup nếu có | Tối đa 500 ms |
| Dự phòng serialization/network | Đủ để không sát deadline tổng |

**Các số chỉ để minh họa**, không phải Spring defaults. Tổng timeout không thể tính đơn giản bằng phép cộng khi có thao tác song song, retry hoặc transaction. Cần đặt deadline end-to-end dựa trên SLO, đo phân phối latency (p95/p99) và giới hạn queue.

Một nguyên tắc: **dependency timeout phải phù hợp với tổng deadline còn lại**, không phải mỗi lớp độc lập chờ thêm 30 giây. Nếu gateway cắt sau 4 giây nhưng truy vấn database vẫn chạy 30 giây, công việc “mồ côi” có thể tiếp tục chiếm tài nguyên.

### 10.3. `@Transactional(timeout=...)` có phải toàn bộ request timeout?

Không. Timeout transaction có phạm vi nghiệp vụ/persistence nhất định và phụ thuộc transaction manager/driver. Nó không tự bao trùm toàn bộ HTTP processing, client credential verification, KMS signing hoặc servlet thread.

Phải cấu hình timeout đúng tại từng dependency, kết hợp capacity protection và cancellation khi có thể. Khi không thể hủy tác vụ đang chạy, hệ thống cần hạn chế concurrent work để không làm cạn tài nguyên.

## 11. Cấu hình `SecurityFilterChain` trong Spring Authorization Server

Một Authorization Server có thể có:

- **AS chain** xử lý các endpoint OAuth/OIDC.
- **Login chain** xử lý xác thực End-User khi cần Authorization Code.
- **Admin API chain** nếu quản trị client có giao diện riêng.

Với Token Endpoint, bảo vệ HTTP có thể được gắn vào **AS chain** mà không thay thế `OAuth2TokenEndpointFilter` hay `OAuth2ClientAuthenticationFilter`.

Ví dụ cấu trúc dùng configurer API hiện đại:

```java
@Configuration
@EnableWebSecurity
class AuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(
            HttpSecurity http,
            TokenEndpointRateLimitFilter tokenRateLimitFilter)
            throws Exception {

        OAuth2AuthorizationServerConfigurer as =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(as.getEndpointsMatcher())
            .with(as, Customizer.withDefaults())
            .addFilterAfter(
                tokenRateLimitFilter,
                SecurityContextHolderFilter.class);

        return http.build();
    }
}
```

**Đây là mẫu tích hợp filter**, không phải cấu hình Authorization Server hoàn chỉnh. Phải cung cấp registered clients, authentication service, authorization/consent services, issuer, khóa ký/JWK, chain đăng nhập và các chức năng OIDC theo nhu cầu.

Đặt filter sau `SecurityContextHolderFilter` chỉ nhằm neo vào một vị trí có thứ tự công khai của Spring Security; **cần test thứ tự thực tế** trên phiên bản dependency, đặc biệt để xác nhận limiter chạy trước công việc client authentication nặng như dự kiến. Một giải pháp ingress mạnh nhất thường nằm ở gateway/proxy, trước khi request chạm servlet container.

### 11.1. Không sửa filter giao thức để thêm rate limit

Việc thay `OAuth2TokenEndpointFilter` để chèn counter có thể vô tình bỏ qua:

- Client authentication.
- Grant validation và scope policy.
- PKCE/authorization code replay validation.
- Refresh token rotation/reuse detection.
- Token persistence/issuance semantics.
- OAuth error response và headers.

**Ưu tiên:** gateway, filter HTTP cross-cutting có phạm vi hẹp, hook authentication/policy được framework công bố hoặc quota service riêng. Khi cần limit theo authenticated client, chỉ dựa trên identity đã được xác minh.

## 12. Ví dụ filter rate limiting trước xác thực client

Ví dụ sau minh họa một **pre-auth limiter**. Nó chỉ áp dụng cho `POST /oauth2/token`, dùng địa chỉ nguồn được xác định từ hạ tầng tin cậy và từ chối sớm khi vượt quota.

Các interface `TokenRateLimitStore` và `TrustedClientAddressResolver` là **abstraction do ứng dụng định nghĩa**; không phải bean built-in của Spring Authorization Server. Bản production cần triển khai Redis/gateway/local policy, quota và xử lý lỗi store.

```java
interface TokenRateLimitStore {
    RateLimitDecision consume(String key);
}

interface TrustedClientAddressResolver {
    String resolve(HttpServletRequest request);
}

record RateLimitDecision(boolean permitted, long retryAfterSeconds) {
}

public final class TokenEndpointRateLimitFilter
        extends OncePerRequestFilter {

    private final TokenRateLimitStore store;
    private final TrustedClientAddressResolver addressResolver;
    private final String tokenPath;

    public TokenEndpointRateLimitFilter(
            TokenRateLimitStore store,
            TrustedClientAddressResolver addressResolver,
            String tokenPath) {
        this.store = store;
        this.addressResolver = addressResolver;
        this.tokenPath = tokenPath;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !"POST".equals(request.getMethod())
            || !tokenPath.equals(request.getServletPath());
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String source = addressResolver.resolve(request);
        RateLimitDecision decision =
            store.consume("token:ingress:" + source);

        if (!decision.permitted()) {
            response.setStatus(429);
            response.setHeader(
                "Retry-After",
                Long.toString(Math.max(1, decision.retryAfterSeconds())));
            response.setHeader("Cache-Control", "no-store");
            response.setHeader("Pragma", "no-cache");
            response.setCharacterEncoding("UTF-8");
            response.setContentType("application/json");
            response.getWriter().write(
                "{\"error\":\"rate_limited\"}");
            return;
        }

        chain.doFilter(request, response);
    }
}
```

**Những giới hạn của ví dụ:**

1. Code dùng **Java 17+** cho `record`; import servlet/Spring đã lược bỏ.
2. Filter **không xác thực client**. Nó chỉ chặn ingress trước các bước OAuth.
3. `tokenPath` cần lấy từ cấu hình endpoint thực tế (ví dụ `AuthorizationServerSettings`) hoặc policy thống nhất; ví dụ `/oauth2/token` chỉ là mặc định thông dụng.
4. `getServletPath()` cần được kiểm thử khi ứng dụng sử dụng context path, servlet mapping, gateway path rewrite hoặc custom endpoint.
5. `addressResolver` phải áp dụng chính sách trusted proxies; tuyệt đối không tin raw `X-Forwarded-For` do caller tự đặt.
6. `store.consume(...)` phải cập nhật quota **nguyên tử**; quyết định failure mode của store phải được nêu rõ.
7. `rate_limited` là **OAuth error extension không chuẩn**, cần contract với client hoặc định dạng 429 được hệ thống thống nhất.
8. Test filter order và tình trạng filter chạy **đúng một lần**; không nên dựa vào mặc định Boot tự đăng ký.

### 12.1. Tránh double registration của servlet filter

Khi `TokenEndpointRateLimitFilter` là một Spring bean kiểu `Filter`, Spring Boot có thể tự đăng ký nó ở servlet container. Nếu đồng thời thêm filter vào `SecurityFilterChain`, nó có thể chạy bên ngoài phạm vi chain hoặc bị thực thi ngoài ý định.

Nếu filter được tạo thành bean và chỉ muốn Spring Security quản lý, có thể tắt tự đăng ký servlet:

```java
@Bean
FilterRegistrationBean<TokenEndpointRateLimitFilter>
disableServletRegistration(TokenEndpointRateLimitFilter filter) {

    FilterRegistrationBean<TokenEndpointRateLimitFilter> registration =
        new FilterRegistrationBean<>(filter);

    registration.setEnabled(false);
    return registration;
}
```

Ví dụ chỉ minh họa cơ chế đăng ký, chưa khai báo bean filter và các dependency limiter. Cần đối chiếu cơ chế auto-registration thực tế của Spring Boot version đang dùng.

### 12.2. Filter có bảo vệ được mọi kiểu quá tải không?

Không. Filter này chỉ đo số **request ingress**. Nếu kẻ tấn công phân tán qua nhiều IP, một limiter theo nguồn có thể không thấy tổng tải bất thường. Nếu client đã xác thực gửi grant gây chi phí ký token rất lớn, cần quota theo client và **concurrency guard** ngay trước công việc nặng.

Ngoài ra, nếu response 429 xảy ra ở tầng gateway **trước khi vào Java**, filter không thấy request đó; dashboard cần kết hợp metric của gateway và AS.

## 13. Tin cậy địa chỉ IP trong môi trường reverse proxy

Một lỗi nguy hiểm là lấy trực tiếp header:

```java
// KHÔNG dùng làm identity đáng tin nếu không có trusted proxy policy.
String source = request.getHeader("X-Forwarded-For");
```

Kẻ tấn công có thể tự gửi header đó và thay giá trị liên tục để vượt quota hoặc làm hỏng dữ liệu audit.

Cách đúng phụ thuộc topology:

- Chỉ nhận request từ load balancer/gateway được phép.
- Tại boundary tin cậy, **xóa hoặc chuẩn hóa** các forwarded headers do caller bên ngoài gửi.
- Chỉ tin chuỗi proxy header từ các hop đã xác minh.
- Đặt `TrustedClientAddressResolver` phù hợp với hạ tầng thực.
- Nếu không có trusted proxy, `request.getRemoteAddr()` phản ánh network peer trực tiếp; nhưng khi có gateway, nó có thể chỉ là IP của gateway.
- Với IPv6, cân nhắc policy grouping/normalization để không bị lách dễ dàng bằng địa chỉ thay đổi.

**Không nên dùng header do client tự gửi như `X-Client-Id` để xác minh OAuth client.** Danh tính OAuth client phải được xác thực bởi đúng cơ chế client authentication.

## 14. Giới hạn theo client đã xác thực

Pre-auth limiter giảm tải ban đầu, nhưng chưa bảo đảm **công bằng giữa các client hợp lệ**. Một client đã được xác thực có thể gửi nhiều request Token Endpoint hơn tất cả client khác cộng lại.

### 14.1. Phải dùng authenticated client identity

Trong Spring Authorization Server, client authentication có thể được biểu diễn bởi `OAuth2ClientAuthenticationToken` và các provider tương ứng. Chính sách quota theo client chỉ nên dựa trên thông tin client đã được xác minh, hoặc dữ liệu repository gắn với kết quả xác thực.

Ví dụ key nghiệp vụ:

```text
authenticated-client:
  registeredClientInternalId = "rc-7f9a"
  tenant = "tenant-a"  (đã được kiểm tra)
  grantType = "client_credentials"

quotaKey = "token:client:rc-7f9a:grant:client_credentials"
```

Đây là **mô hình key**, không phải Java code được Spring Authorization Server tự triển khai. Kiểm tra tenant, client registration và quota phải thuộc policy/service tin cậy.

### 14.2. Điểm chèn chính sách

Có thể cân nhắc:

- Chính sách gateway có identity được xác thực đáng tin, nếu gateway thực sự xác minh client authentication.
- Một hook `AuthenticationProvider`/Token Endpoint được Spring Authorization Server công bố, với thứ tự phù hợp và không bỏ qua provider chuẩn.
- Service domain được provider gọi sau xác thực client và trước token issuance.
- Một lớp admission control riêng trước signer/authorization persistence.

**Không chỉ thêm một provider tùy biến rồi mặc định nó chạy trước provider mặc định.** Thứ tự `AuthenticationManager` và kiểu `supports(...)` quyết định provider nào thực sự xử lý. Cần test hook/chain theo version.

### 14.3. Kiểm tra quota trước hay sau validation?

Một số kiểm tra rẻ (request format, grant type allowed) nên từ chối sớm để giảm tài nguyên. Nhưng nếu chỉ đếm **request đã xác thực và hợp lệ**, attacker vẫn có thể dồn request credential sai khiến provider tốn CPU.

Vì vậy, ưu tiên **pre-auth admission + post-auth per-client quota + dependency concurrency guard**. Thứ tự tối ưu dựa trên việc đo thực tế, không phải một quy tắc cứng cho mọi grant.

## 15. Bảo vệ từng grant và ngăn replay

### 15.1. Authorization Code + PKCE

Nguy cơ đặc trưng:

- Thử đổi code giả hoặc code của client khác.
- Dùng lại một code đã đổi.
- Thiếu/sai `code_verifier`, cố đoán verifier.
- Dùng redirect URI không khớp authorization request.

Bảo vệ cốt lõi:

- Code ngẫu nhiên, thời hạn ngắn và **single-use**.
- PKCE S256 khi áp dụng, đặc biệt với public client.
- Client authentication với confidential client.
- Ràng buộc code với client, redirect URI và authorization gốc.
- Quota phù hợp cho token exchange; không tăng độ dài thời hạn code để chữa lỗi rate limit.

**Không được nới lỏng single-use** khi gặp retry. Nếu client đã gửi Token Request, network timeout có thể khiến client không biết request đã thành công chưa. Việc lặp lại code có thể tạo `invalid_grant` theo đúng cơ chế bảo vệ.

### 15.2. Refresh Token

Nguy cơ đặc trưng:

- Dò refresh token hoặc sử dụng token đã bị thu hồi.
- Dùng lại refresh token cũ sau rotation.
- Refresh storm do client thiếu cache.
- Replay giữa nhiều node.

Bảo vệ:

1. Lưu và kiểm tra trạng thái refresh token theo `OAuth2AuthorizationService` hoặc cơ chế tương ứng.
2. Áp dụng refresh token rotation/reuse policy phù hợp client và loại grant.
3. Rate limit cả request thành công và bất thường, không chỉ đếm access token mới.
4. Nếu phát hiện reuse, quyết định cách thu hồi token family/session theo threat model.
5. Không log refresh token; kiểm thử tranh chấp hai refresh request cùng lúc.

**Đừng tự tạo exception để cho refresh token hết hạn được dùng lại**, vì điều đó phá token lifecycle.

### 15.3. Client Credentials

Dịch vụ M2M không cần xin token mới cho mỗi API request. Sử dụng cache access token ở phía client và xin token sớm trước `expiresAt`, với jitter và backoff.

Nếu 500 instance cùng khởi động và cùng xin token, pre-auth/per-client limiter có thể chặn cả lưu lượng hợp lệ. Thiết kế client cần:

- `OAuth2AuthorizedClientManager` và provider client credentials phù hợp.
- Reuse token còn hạn, cache key theo registration/workload.
- Clock skew và jitter để giảm đồng thời.
- Single-flight để không gửi nhiều request trùng trong cùng instance.
- Retry có giới hạn khi 429/5xx; không retry vô hạn khi `invalid_client`.

### 15.4. Extension grants và Token Exchange

Các grant mở rộng có thể có bước xác minh JWT assertion, subject token hoặc external identity:

- Giới hạn kích thước token assertion và form body.
- Giới hạn các loại token/issuer/audience được hỗ trợ.
- Cache trusted JWK an toàn, chống SSRF/truy xuất URL tùy ý.
- Đặt timeout cho remote introspection/JWKS/KMS.
- Không tin token vì chỉ parse được payload.
- Áp dụng quota theo authenticated client và cost của grant, tránh token issuance amplification.

Nếu dùng Token Exchange theo RFC 8693, cần kiểm tra target `audience`/`resource`, scope attenuation và client authorization; rate limiting không thay thế kiểm soát nâng quyền.

## 16. Những biện pháp chống lạm dụng ngoài rate limit

### 16.1. Giới hạn kích thước và số tham số request

Token Endpoint thường đọc `application/x-www-form-urlencoded`. Request độc hại có thể chứa body rất lớn, nhiều tham số trùng hoặc assertion dài bất thường.

Nên giới hạn tại edge/servlet:

- Tổng kích thước request body và header.
- Số lượng form parameters và kích thước một parameter.
- Thời gian đọc request body.
- Loại content type và HTTP method được phép.
- Số lượng/độ dài các đối tượng như scope, audience, JWT assertion theo policy.

**Đừng để cơ chế rate limit chỉ chạy sau khi container đã parse body hàng chục MB**; giới hạn request size và timeouts ở proxy/connector nên chặn sớm.

### 16.2. Không tiết lộ thông tin client qua lỗi

Một hệ thống có thể vô tình tiết lộ:

- Client ID có tồn tại hay không.
- Phương thức client authentication đang dùng.
- Secret gần đúng hoặc sai một phần.
- Grant/scope bí mật của client khác.
- Tenant hay user mà refresh token thuộc về.

Giữ phản hồi lỗi công khai phù hợp OAuth; ghi chi tiết vào audit bảo mật có phân quyền. Đừng dùng response time khác biệt quá lớn để phân loại client tồn tại/không tồn tại nếu có thể giảm bằng xử lý mật mã thích hợp và baseline đồng nhất.

### 16.3. Chống credential stuffing mà không gây DoS lên nạn nhân

Không nên khóa vĩnh viễn một client chỉ vì attacker gửi hàng nghìn request thất bại khai báo `client_id` của nó. Có thể cân nhắc:

- Rate limit network nguồn chưa xác thực.
- Quota theo credential/client **sau khi xác thực**.
- Adaptive throttling dựa trên tín hiệu rủi ro kết hợp, thay vì một username/client ID tự khai.
- Cảnh báo và điều tra bất thường trong authentication failure.
- Cơ chế khôi phục/override được audit cho dịch vụ quan trọng.
- Credential mạnh, rotation và phương thức xác thực phù hợp như `private_key_jwt` hoặc mTLS khi có yêu cầu.

### 16.4. TLS, secret và token leakage

- Bắt buộc HTTPS cho Token Endpoint ngoài môi trường phát triển kiểm soát.
- Không đưa client secret/token vào URL.
- Không log header `Authorization` hoặc form body Token Request.
- Bảo vệ signing keys, JWKS/secret manager, DB credentials.
- Áp dụng chính sách cache HTTP an toàn cho token response (ví dụ `Cache-Control: no-store`).
- Không thêm middleware tự ghi lại tất cả token response để “debug hiệu năng”.

## 17. Timeout, circuit breaker và bulkhead cho dependency

### 17.1. Database/authorization store

`OAuth2AuthorizationService` có thể đọc/ghi authorization code, refresh token và token metadata. Cần:

- Connection pool có kích thước và acquire timeout hợp lý.
- Query/statement timeout phù hợp với SLO.
- Index theo schema/version hỗ trợ.
- Transaction không giữ lock quá lâu.
- Kiểm tra concurrency khi hai request cùng đổi code hoặc refresh token.
- Giới hạn request trước khi pool bị bão hòa.

**Khi DB chậm, tăng số thread HTTP có thể làm hệ thống tệ hơn.** Cần giới hạn concurrency, quan sát queue latency và giảm request không thiết yếu.

### 17.2. Signer/JWK/KMS/HSM

Nếu ký JWT qua HSM/KMS hoặc remote signer:

- Dùng timeout riêng cho signing operation.
- Có giới hạn concurrent signing requests.
- Cache **public key metadata** và kết quả khám phá nguồn tin cậy khi được phép, không cache private key tùy tiện.
- Chỉ dùng thuật toán/khóa được policy cho phép; không đổi sang khóa yếu khi signer lỗi.
- Theo dõi rate limit/quota của KMS/HSM.
- Khi signer không khả dụng, **không phát token chưa ký hoặc bỏ qua xác minh** để duy trì availability.

### 17.3. Remote identity/introspection

Nếu custom grant hoặc client authentication phụ thuộc IdP/JWKS/introspection ngoài:

- Chỉ gọi những endpoint được cấu hình tin cậy, chống SSRF.
- Có connect/read timeout và giới hạn retry.
- Phân biệt cached metadata với dữ liệu token validity có thời hạn riêng.
- Không tin một token chỉ vì remote endpoint trả timeout; lỗi kiểm tra trust **không được fail-open**.
- Cân nhắc circuit breaker để bảo vệ hệ thống khi downstream liên tục lỗi.

### 17.4. Retry có thể nhân tải lên rất lớn

Nếu mỗi lớp (gateway, AS, HTTP client của KMS) đều retry tối đa 3 lần, một request gốc có thể gây nhiều request downstream theo cấp số nhân. Hãy xác định **retry ownership** và tổng deadline, không bật retry mặc định ở mọi lớp.

Đặc biệt ở Token Endpoint, request **không luôn idempotent**. Retry Authorization Code Grant sau một timeout mơ hồ có thể trả `invalid_grant` vì code đã được dùng. Refresh token rotation cũng có thể làm retry với token cũ thành replay theo chính sách.

## 18. Hướng dẫn OAuth client xử lý 429 và outage

Token Endpoint bảo vệ tốt chỉ là một nửa giải pháp. Nếu clients tiếp tục retry 100 lần/giây sau 429, AS vẫn có nguy cơ quá tải.

### 18.1. Nguyên tắc client

1. **Tái sử dụng token còn hợp lệ**, không xin token cho mỗi request API.
2. Khi nhận 429, đọc `Retry-After` nếu hợp lệ.
3. Dùng exponential backoff + jitter và giới hạn số lần retry.
4. Có **tổng thời gian chờ/deadline** cho nghiệp vụ.
5. Không retry vô hạn với `invalid_client`, `invalid_grant` hoặc `invalid_scope`.
6. Không tự động retry request không idempotent khi không biết request trước đã hoàn tất hay chưa.
7. Dùng circuit breaker khi AS không phục vụ để ngăn request storm.
8. Phát cảnh báo nếu token sắp hết hạn mà không thể xin token mới.

### 18.2. Pseudocode cho retry có giới hạn

```text
function acquireToken():
    if cachedToken has enough lifetime:
        return cachedToken

    for attempt in 1..MAX_ATTEMPTS:
        response = tokenEndpointRequest(deadlineRemaining)

        if success:
            cache token until safe expiry
            return token

        if oauthError in {invalid_client, invalid_grant,
                          unauthorized_client, invalid_scope}:
            fail without blind retry

        if response is 429 or transient 503:
            delay = retryAfter or boundedExponentialBackoffWithJitter
            if delay exceeds remaining deadline:
                fail
            wait(delay)
            continue

        fail

    fail with controlled error
```

**Đây là pseudocode**, không phải mã thư viện Spring. Với grant chứa authorization code hoặc refresh rotation, phải quyết định retry theo semantics của giao dịch; một response lỗi mơ hồ không cho phép mặc nhiên dùng lại cùng credential.

### 18.3. `Retry-After` không phải lịch trình tuyệt đối

Nhiều client có thể cùng nhận `Retry-After: 10` rồi cùng retry ở giây thứ 10. Kết hợp jitter và biên giới hạn sẽ giảm đồng bộ, nhưng vẫn phải tuân thủ thời gian tối thiểu theo contract và SLA của hệ thống.

## 19. Observability: theo dõi lạm dụng mà không lộ dữ liệu

### 19.1. Metrics đề xuất

| Metric | Mục đích |
|---|---|
| Token Endpoint RPS theo grant và outcome | Phân biệt tải hợp lệ/không hợp lệ |
| HTTP 429 rate và tổng denied requests | Đánh giá hiệu quả quota và false positive |
| HTTP 401/400/5xx rate | Phát hiện lỗi authentication, grant và outage |
| `invalid_client`/`invalid_grant` rate | Cảnh báo credential stuffing/replay và lỗi tích hợp |
| p50/p95/p99 latency | Theo dõi trải nghiệm và sức khỏe dependency |
| In-flight request count | Phát hiện concurrency exhaustion |
| Queue wait time | Dự đoán quá tải trước khi tăng 5xx |
| DB pool wait/timeout | Tìm bottleneck persistence |
| Redis limiter timeout/error | Theo dõi rate-limiter health |
| Signing/KMS latency/error | Tìm bottleneck phát token |
| Client Credentials token acquisition rate | Phát hiện client không cache hoặc stampede |
| Refresh token reuse detection | Phát hiện hành vi replay theo chính sách |

### 19.2. Audit event phù hợp

Có thể lưu:

- Event type: `TOKEN_REQUEST_LIMITED`, `CLIENT_AUTH_FAILURE`, `GRANT_REJECTED`, `TOKEN_ISSUED`, `DEPENDENCY_TIMEOUT`.
- Thời điểm, correlation ID và environment.
- Grant type, client identity nếu **đã xác thực**, source/network signal đã chuẩn hóa.
- Tên policy hoặc quota bucket, thời gian chờ được khuyến nghị.
- Latency, outcome và nhóm lỗi không nhạy cảm.
- Phiên bản cấu hình của limiter hoặc policy.

Không lưu:

- Client secret, private key, raw JWT assertion.
- Authorization code, `code_verifier`, access token hoặc refresh token.
- Header `Authorization`, cookie hoặc request body chưa che dữ liệu.
- SQL query có token value hoặc stack trace trong response.
- Các identifier tự do có cardinality không giới hạn trong metric labels.

### 19.3. Phân biệt tấn công với lỗi triển khai

Một biểu đồ có `invalid_client` tăng sau deploy có thể là:

- Secret rotation cập nhật chưa đồng bộ.
- Client config trỏ sang sai issuer/token URI.
- Clock skew làm client assertion hết hạn.
- Token cache không hoạt động khiến request rate tăng.
- Tấn công đoán credential.

Điều tra cần xem thời điểm deploy, client version, loại grant, nguồn và metrics phụ thuộc. Không khóa client quan trọng chỉ dựa trên một ngưỡng lỗi mà không có runbook hoặc policy rõ.

## 20. Kiểm thử rate limit, timeout và chống lạm dụng

### 20.1. Ma trận kiểm thử giao thức

| Kịch bản | Thiết lập | Kết quả cần chứng minh |
|---|---|---|
| Request hợp lệ dưới quota | Client credentials/authorization code hợp lệ | Token Endpoint xử lý chuẩn, không bị limiter cản |
| Vượt quota ingress | Nhiều POST từ cùng nguồn đã chuẩn hóa | `429`, `Retry-After` và không phát token |
| Dưới quota nhưng secret sai | Invalid client credential | OAuth `invalid_client` phù hợp |
| Mạo `client_id` nạn nhân | Attacker không có credential | Không chiếm quota **post-auth** của client nạn nhân |
| Mạo `X-Forwarded-For` | Gửi header giả từ Internet | Không vượt limiter nhờ header chưa tin cậy |
| Nhiều client sau NAT | Các client hợp lệ chung IP | Quota/false positive nằm trong mức chấp nhận theo policy |
| Public client và confidential client | Grant/method khác nhau | Không dùng một giả định client auth cho cả hai |
| Authorization code replay | Đổi code hai lần | Chỉ được cấp token đúng một lần |
| PKCE sai | Gửi `code_verifier` sai | Bị từ chối bất kể quota |
| Refresh token reuse | Token cũ sau rotation | Tuân thủ reuse/revocation policy |
| Scope/grant không được phép | Xin scope hoặc grant ngoài registration | OAuth error chuẩn, không âm thầm cấp quyền |
| Request form quá lớn | Body/header/params vượt giới hạn | Chặn sớm, không gây memory exhaustion |
| HTTP GET /oauth2/token | Sai method | Không phát token |
| Token Endpoint bị quá tải | Hết concurrency slot | Từ chối có kiểm soát, không queue vô hạn |

### 20.2. Ma trận kiểm thử timeout/dependency

| Kịch bản | Hành vi cần kiểm tra |
|---|---|
| DB connection pool hết slot | Không treo vô hạn; timeout/bulkhead hoạt động |
| Query authorization chậm | Có query timeout và metric; code state không bị sai |
| KMS signer timeout | Không phát JWT chưa ký/không hợp lệ |
| Remote JWKS/introspection timeout | Không tự coi token chưa xác minh là hợp lệ |
| Limiter store lỗi | Fail-open/closed/fallback đúng thiết kế, có cảnh báo |
| Gateway timeout trước AS | Theo dõi công việc backend có tiếp tục chiếm tài nguyên không |
| 100 request đồng thời | Không vượt giới hạn concurrency đã định |
| Multi-node load test | Quota toàn cụm đúng mức nhất quán đã cam kết |
| Redis failover/partition | Không làm hỏng dữ liệu quota hoặc tạo outage bất ngờ |
| Deployment rolling upgrade | Limiter config/version và token policy đồng nhất |
| Retry storm khi AS phục hồi | Client backoff/jitter; không tăng tải đột biến ngoài capacity |

### 20.3. Test phân biệt 429 và OAuth errors

Với `MockMvc` hoặc HTTP integration test:

1. Cấu hình limiter test có quota xác định, tránh phụ thuộc đồng hồ thật khi có thể.
2. Gửi một request `client_credentials` hợp lệ dưới quota và xác minh response token.
3. Gửi request vượt quota, xác minh **HTTP 429**, `Retry-After` và không có token.
4. Gửi request secret sai dưới quota, xác minh **`invalid_client`** theo contract.
5. Kiểm tra request vượt quota **không gọi token generator** hoặc DB provider nặng nếu limiter được thiết kế chặn trước.
6. Kiểm tra filter chỉ chạy một lần trong đúng chain, không chạy trùng qua servlet container.
7. Thử request ở endpoint khác như `/oauth2/authorize` để bảo đảm không bị limiter Token Endpoint chặn nhầm.
8. Trên nhiều instance, kiểm tra cùng một bucket key được đồng bộ hoặc giới hạn được mô tả đúng.

Một ví dụ test khái niệm:

```java
@Test
void overQuotaTokenRequestReturns429() throws Exception {
    // Giả định test fixture khiến TokenRateLimitStore trả
    // RateLimitDecision(permitted=false, retryAfterSeconds=10).

    mockMvc.perform(post("/oauth2/token")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("grant_type", "client_credentials"))
        .andExpect(status().isTooManyRequests())
        .andExpect(header().string("Retry-After", "10"));
}
```

Test cần cấu hình security chain, mock store và beans phù hợp. Nó chỉ chứng minh **HTTP limiter response**; integration test đầy đủ còn cần kiểm tra client authentication/grant khi request không bị chặn.

### 20.4. Kiểm thử hiệu năng và công bằng

Đặt ba nhóm giả định:

- Client A: traffic bình thường, cần login và code exchange.
- Client B: M2M traffic lớn nhưng hợp lệ, có token cache.
- Attacker: request credential sai hoặc refresh token giả.

Đo xem limiter có:

- Bảo toàn thông lượng tối thiểu cho A.
- Ngăn B chiếm toàn bộ capacity dù hợp lệ.
- Chặn Attacker trước khi KMS/DB pool bị bão hòa.
- Tránh làm số lỗi 429 của A tăng đột biến do cùng NAT với Attacker.
- Duy trì p95/p99 latency và không tạo queue backlog ngoài thiết kế.

Đây mới là bằng chứng cần có trước khi cố định quota production; một unit test token bucket không chứng minh toàn bộ hệ thống chống DoS tốt.

## 21. Quy trình ứng cứu khi Token Endpoint bị tấn công hoặc quá tải

1. **Xác định triệu chứng:** RPS tăng, 429/5xx, `invalid_client`/`invalid_grant` tăng, queue/DB/HSM chậm.
2. **Xác định nguồn:** Tách ingress IP/network, authenticated client, grant type, tenant, route và deployment version.
3. **Bảo vệ capacity:** Kích hoạt hoặc điều chỉnh edge rate limit và concurrency guard có kiểm soát.
4. **Ưu tiên client quan trọng:** Dùng policy/quota theo nhóm đã định nghĩa; không tắt validation.
5. **Đánh giá credential:** Nếu có dấu hiệu lộ secret/JWT assertion, thu hồi/rotate theo quy trình; kiểm tra token đã phát hành.
6. **Giảm retry storm:** Thông báo Retry-After/backoff cho clients, phát hiện client library cấu hình sai.
7. **Kiểm tra dependency:** DB pool, Redis limiter, HSM/KMS, JWKS, remote introspection và network.
8. **Duy trì bằng chứng:** Audit/correlation ID, không thu thập raw token/secret “để debug”.
9. **Phục hồi:** Hạ mức giới hạn tạm thời một cách có giám sát, kiểm tra token issuance và OAuth compliance.
10. **Phòng ngừa lặp lại:** Bổ sung regression/load tests, tuning quota, client cache và runbook.

Nếu sự cố do chính limiter store bị outage, cần có phương án fallback đã được phê duyệt. Không tùy tiện bỏ qua client authentication, PKCE hay kiểm tra token chỉ để “khôi phục nhanh”.

## 22. Checklist triển khai production

- [ ] Token Endpoint chạy HTTPS và được nhận diện đúng trong `SecurityFilterChain`.
- [ ] Edge giới hạn connection, request body, header/parameter count và slow clients.
- [ ] Có pre-auth ingress limiter dùng source identity từ trusted proxy.
- [ ] Có quota post-auth theo **client identity đã xác minh** và grant phù hợp.
- [ ] Quota không dựa duy nhất vào `client_id` hoặc `X-Forwarded-For` tự khai.
- [ ] Bộ limiter dùng atomic update, có chiến lược multi-instance/region nhất quán.
- [ ] Giới hạn cả **rate** lẫn **concurrency** ở công việc DB/signing nặng.
- [ ] Có timeout cho DB pool/query, signer/KMS, remote introspection/JWKS, network.
- [ ] Timeout được thiết kế theo SLO/deadline, không nhầm connector timeout với request timeout.
- [ ] Không có hàng đợi vô hạn và retry dây chuyền không kiểm soát.
- [ ] OAuth `invalid_client`/`invalid_grant`/`invalid_scope` không bị thay bằng thông báo lỗi tùy ý.
- [ ] 429/`Retry-After` được client xử lý với retry/backoff/jitter có giới hạn.
- [ ] Không dùng `slow_down` của Device Authorization Grant cho mọi loại grant.
- [ ] Authorization Code vẫn single-use và có PKCE/redirect validation.
- [ ] Refresh token rotation và replay detection không bị nới lỏng để xử lý quá tải.
- [ ] Client Credentials sử dụng cache token thay vì xin token mỗi API call.
- [ ] Custom filter chỉ chạy trong chain phù hợp, không double registration.
- [ ] Không ghi client secret, JWT assertion, authorization code, refresh/access token hoặc raw HTTP body.
- [ ] Metrics/tracing/audit có phân quyền, cardinality và retention phù hợp.
- [ ] Đã load test traffic hợp lệ, attacker, nhiều client sau NAT và nhiều instance.
- [ ] Có runbook khi limiter/DB/KMS hỏng hoặc khi credential bị lộ.

### Kiến thức cốt lõi

**Token Endpoint cần được bảo vệ như một bề mặt xác thực và phát hành credential quan trọng**. Giới hạn tốc độ là tầng phòng vệ đầu tiên, nhưng cần kết hợp:

- **Pre-auth admission control** để chặn lưu lượng bất thường trước khi xử lý credential tốn kém.
- **Post-auth quota theo client đã xác minh** để bảo đảm công bằng và giới hạn client hợp lệ bị lỗi.
- **Concurrency limit + timeout/deadline** để không làm cạn DB, signer/HSM, cache hoặc servlet threads.
- **Phản hồi 429 và retry policy có giới hạn**, tránh tạo thêm tải từ client.
- **Validation OAuth/OIDC không được nới lỏng**, đặc biệt client authentication, grant, PKCE, code replay và refresh token state.
- **Observability không lộ credential**, cùng kiểm thử load/multi-instance và runbook ứng cứu.

Spring Authorization Server chịu trách nhiệm xử lý giao thức Token Endpoint; Spring Security và hạ tầng gateway cung cấp các vị trí thực thi policy bảo vệ. **Đừng thay filter giao thức hoặc bỏ qua xác thực chỉ để đạt được rate limit**. Một giải pháp production an toàn phải giữ cả tính đúng đắn của OAuth lẫn khả dụng khi bị lạm dụng.

## Tài liệu tham khảo

- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Multiple SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html#_multiple_httpsecurity_instances)
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework, Token Endpoint](https://www.rfc-editor.org/rfc/rfc6749#section-3.2)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 6585 — Additional HTTP Status Codes, 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585#section-4)
- [RFC 9110 — HTTP Semantics (Retry-After)](https://www.rfc-editor.org/rfc/rfc9110)
- [OWASP API Security Top 10 (2023)](https://owasp.org/API-Security/editions/2023/en/0x11-t10/)
