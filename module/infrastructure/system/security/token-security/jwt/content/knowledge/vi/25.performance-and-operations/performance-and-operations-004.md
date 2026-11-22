# Giới hạn độ dài, tốc độ yêu cầu và số lần thử xác minh

JWT có thể được ký đúng nhưng vẫn trở thành nguồn gây quá tải nếu verifier phải parse một token quá lớn, xử lý JSON lồng sâu, thử nhiều khóa, gọi JWKS liên tục hoặc thực hiện quá nhiều phép xác minh mật mã cho một request. Ngược lại, giới hạn quá thấp hoặc áp dụng không nhất quán giữa load balancer, gateway và resource server có thể làm token hợp lệ bị từ chối, gây lỗi khó chẩn đoán và tạo ra hành vi bảo mật khác nhau giữa các tầng.

Bài này thuộc chương **Hiệu năng và vận hành** của module **Security - JSON Web Token (JWT)**. Nội dung áp dụng cho mọi hệ thống xác minh JWT, độc lập ngôn ngữ lập trình, runtime và framework.

## 1. Mục tiêu và nguyên tắc thiết kế

Sau bài học, người đọc có thể:

1. Xác định giới hạn kích thước cho HTTP request, JWT compact serialization, từng segment và dữ liệu sau giải mã.
2. Giới hạn độ phức tạp của header, claims, JSON parser và nested token.
3. Thiết kế rate limit, concurrency limit và work budget cho request xác minh.
4. Giới hạn số candidate key, số lần thử chữ ký và số lần refresh JWKS.
5. Tránh CPU, memory, I/O và network exhaustion do token hoặc request độc hại.
6. Phối hợp giới hạn giữa proxy, gateway, authorization server và resource server.
7. Đo lường, kiểm thử tải và điều chỉnh giới hạn dựa trên năng lực thực tế.

**Nguyên tắc cốt lõi:** giới hạn phải được áp dụng trước khi thực hiện công việc tốn tài nguyên, phải nhất quán trên toàn đường đi của request và phải dựa trên token profile cùng năng lực đã đo của hệ thống. Không có một giá trị byte, request/second hoặc timeout chuẩn áp dụng cho mọi triển khai JWT.

## 2. Vì sao JWT cần resource limits?

JWT thường được gửi trong mỗi request API. Một request có thể kích hoạt nhiều thao tác:

- Nhận và lưu trữ HTTP headers.
- Parse compact serialization và Base64url-decode các segment.
- Parse JSON header và claims.
- Tra cứu key trong JWKS/cache/database/KMS.
- Xác minh chữ ký hoặc giải mã JWE.
- Kiểm tra claims, scope, tenant và authorization policy.
- Ghi log, metrics, trace và audit event.

Attacker có thể khai thác từng bước bằng token quá lớn, JSON phức tạp, key ID ngẫu nhiên, thuật toán tốn CPU hoặc request rate cao. Một token không hợp lệ vẫn có thể tiêu tốn tài nguyên trước khi bị từ chối.

### 2.1. Ba loại giới hạn cần phối hợp

| Nhóm giới hạn | Kiểm soát | Ví dụ |
| --- | --- | --- |
| **Size limit** | Kích thước đầu vào và dữ liệu trung gian | Request header, JWT bytes, decoded payload, JSON depth |
| **Rate limit** | Số request trong một khoảng thời gian | Request/second theo IP, client, tenant hoặc route |
| **Work/attempt limit** | Công việc tối đa cho một request | Candidate keys, chữ ký được thử, JWKS refresh, nested depth |

Rate limit không thay thế size limit. Một request/second vẫn có thể làm cạn memory nếu mỗi token có kích thước rất lớn. Tương tự, token nhỏ vẫn có thể gây CPU exhaustion nếu verifier thử nhiều thuật toán hoặc khóa.

## 3. Xác định ranh giới xử lý và thứ tự áp dụng giới hạn

Giới hạn hiệu quả cần đặt tại đúng tầng:

1. **Network/load balancer:** giới hạn connection, request header tổng, body, timeout và tốc độ kết nối.
2. **HTTP server/API gateway:** giới hạn header field, số lượng header, request rate, concurrency và route.
3. **JWT admission/parser:** giới hạn tổng bytes, số segment, decoded size, JSON depth và cấu trúc.
4. **Key resolver:** giới hạn candidate key, cache lookup, database query và JWKS refresh.
5. **Crypto verifier/decryptor:** giới hạn thuật toán, key strength, số lần xác minh và thời gian xử lý.
6. **Authorization/business layer:** giới hạn quyền, tenant, truy vấn và side effect.

Không đợi đến sau khi parse toàn bộ payload mới kiểm tra kích thước. Không đợi đến sau khi thử nhiều khóa mới áp dụng attempt limit. Kiểm tra rẻ và có thể thực hiện an toàn nên diễn ra trước công việc tốn tài nguyên.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Ingress size, timeout, connection limits"]
    B --> C["Rate and concurrency admission"]
    C --> D["JWT byte and segment limits"]
    D --> E["Bounded Base64url and JSON parsing"]
    E --> F["Trusted issuer and bounded key lookup"]
    F --> G["Allowlisted algorithm and bounded crypto work"]
    G --> H["Claims and token-profile validation"]
    H --> I["Authorization and business operation"]
    B --> X["Reject / shed load"]
    C --> X
    D --> X
    E --> X
    F --> X
    G --> X
    H --> X
~~~

Các bước phải fail closed khi token vượt giới hạn của profile. Request bị từ chối ở admission hoặc parser không được gây side effect nghiệp vụ.

## 4. Giới hạn kích thước HTTP request

JWT thường nằm trong HTTP Authorization header, cookie hoặc một vị trí khác do ứng dụng quy định. Giới hạn ở HTTP layer có thể chặn request trước khi JWT parser được gọi.

Các kích thước cần quản lý:

- Tổng kích thước request headers.
- Kích thước từng header field, đặc biệt Authorization và Cookie.
- Số lượng header fields.
- Kích thước request body nếu token được gửi trong body theo một protocol cụ thể.
- Kích thước URL/query nếu hệ thống có endpoint nhận token qua URL.

HTTP/2 hoặc HTTP/3 có cơ chế nén header, nhưng giới hạn của ứng dụng thường cần tính trên giá trị header sau khi giải nén và trước khi xử lý. Không coi header compression là biện pháp chống oversized header.

### 4.1. Chọn nơi đặt giới hạn

Nếu load balancer cho phép header lớn hơn gateway, còn gateway cho phép lớn hơn backend, một request có thể đi qua nhiều tầng rồi bị từ chối ở tầng sau. Ngược lại, nếu tầng ngoài từ chối sớm hơn nhiều so với policy backend, client có thể gặp lỗi khác nhau tùy đường đi.

Thiết kế nên:

- Định nghĩa một profile giới hạn được quản trị tập trung.
- Đồng bộ cấu hình trên ingress, gateway và service.
- Để tầng ngoài chặn sớm với giới hạn tương thích với tầng trong.
- Chừa headroom cho các header hợp lệ khác như tracing, correlation và cookie.
- Kiểm tra thực tế sau TLS termination và qua mọi proxy.

### 4.2. HTTP status và thông báo lỗi

Có thể dùng:

- **413 Content Too Large** khi request content/body vượt giới hạn áp dụng.
- **431 Request Header Fields Too Large** khi request headers hoặc một header field quá lớn.
- **400 Bad Request** khi token/header sai định dạng theo contract của endpoint.
- **429 Too Many Requests** khi rate limit được kích hoạt.
- **503 Service Unavailable** khi hệ thống chủ động shed load do quá tải tạm thời.

Không tiết lộ giới hạn nội bộ, key store path hoặc chi tiết parser trong response. Client cần nhận được lỗi có thể xử lý và correlation ID để hỗ trợ điều tra.

## 5. Giới hạn kích thước JWT compact serialization

Với compact JWS, token có ba segment phân tách bằng hai dấu chấm. Với compact JWE, token có năm segment phân tách bằng bốn dấu chấm. Nếu endpoint chỉ hỗ trợ một dạng serialization, phải kiểm tra đúng số segment trước khi parse sâu.

Các giới hạn nên xác định riêng:

| Thành phần | Vì sao cần giới hạn |
| --- | --- |
| Tổng token bytes | Chặn input lớn trước khi copy, decode hoặc parse |
| Protected header segment | Header thường nhỏ; hạn chế metadata và JSON bất thường |
| Payload segment | Claims lớn làm tăng memory và parser cost |
| Signature segment | Giới hạn theo thuật toán và key size được hỗ trợ |
| JWE encrypted-key/IV/tag | Ngăn segment sai kích thước hoặc dữ liệu dư thừa |
| Decoded header/payload | Base64url text có kích thước khác dữ liệu sau decode |

JWT compact serialization dùng ký tự ASCII trong các segment Base64url và dấu phân cách. Đo kích thước theo bytes ở ranh giới HTTP và token parser, không dựa vào số ký tự của chuỗi Unicode đã được decode từ nơi khác.

### 5.1. Không có một giới hạn JWT phổ quát

RFC JWT/JOSE định nghĩa cấu trúc và thuật toán nhưng không đưa ra một giới hạn kích thước duy nhất cho mọi deployment. Giới hạn phải xét:

- Claims bắt buộc và custom claims thực sự cần thiết.
- Số lượng role/scope/group.
- Kích thước key/certificate hoặc header metadata.
- Giới hạn của proxy, server, SDK và client.
- Chi phí parse/verify và memory budget.
- Khả năng tương thích với các hệ thống nhận token.

Ví dụ, một API có thể đặt ngưỡng compact token vài kilobyte, trong khi token profile có certificate chain hoặc dữ liệu đặc thù có thể cần khác. Mọi con số phải được đo và kiểm thử xuyên suốt đường đi.

### 5.2. Đo trước khi decode

Trình tự an toàn:

1. Kiểm tra tổng bytes của token.
2. Kiểm tra số lượng segment và độ dài từng segment.
3. Tính giới hạn decoded size dự kiến trước khi cấp phát buffer lớn.
4. Base64url-decode bằng parser có giới hạn.
5. Kiểm tra kích thước decoded bytes.
6. Chỉ sau đó mới parse JSON với depth/member limits.

Không decode một payload không giới hạn vào memory rồi mới kiểm tra rằng nó quá lớn.

## 6. Giới hạn cấu trúc JSON và claims

Một payload nhỏ vẫn có thể có cấu trúc gây tốn tài nguyên hoặc tạo khác biệt giữa parser:

- JSON nesting quá sâu.
- Object có rất nhiều members.
- Array có quá nhiều phần tử.
- String rất dài.
- Số có biểu diễn cực lớn hoặc vượt kiểu dữ liệu của implementation.
- Duplicate member names.
- Unicode escape hoặc invalid UTF-8 theo cách parser xử lý không nhất quán.

Đặt giới hạn cho:

| Thành phần | Policy nên có |
| --- | --- |
| JSON nesting depth | Độ sâu tối đa được hỗ trợ |
| Object members | Số member tối đa ở mỗi object hoặc toàn document |
| Array elements | Số phần tử tối đa |
| String length | Độ dài tối đa cho claim theo profile |
| Numeric claims | Miền giá trị và kiểu dữ liệu được chấp nhận |
| Duplicate names | Từ chối hoặc quy tắc xử lý duy nhất, nhất quán |
| Total decoded bytes | Giới hạn payload/header sau decode |

Không cần cho phép mọi kiểu JSON ở mọi claim. Ví dụ, iss, sub, jti, typ và kid thường cần string; exp, iat, nbf cần NumericDate theo profile. Kiểm tra kiểu và độ dài theo schema/token profile sau khi parser đã được giới hạn.

## 7. Giới hạn số lượng claims và kích thước từng claim

JWT không phải nơi lưu toàn bộ hồ sơ người dùng hoặc danh sách dữ liệu nghiệp vụ lớn. Claims càng nhiều thì token càng lớn, request càng nặng và càng nhiều dịch vụ có thể đọc dữ liệu đó.

Thiết kế:

- Chỉ đưa claims cần cho audience và mục đích cụ thể.
- Dùng scope/role gọn, tránh nhúng toàn bộ permission graph.
- Không nhúng danh sách hàng nghìn resource ID vào access token.
- Giới hạn custom claim theo schema và owner.
- Tránh lặp lại cùng một dữ liệu ở nhiều claim.
- Dùng API hoặc datastore để truy xuất dữ liệu lớn thay vì nhúng vào token.
- Có versioning khi thay đổi schema claims.

Nếu một token vượt giới hạn do claims phình to, cần sửa token profile hoặc cách lấy dữ liệu. Tăng giới hạn vô hạn chỉ chuyển chi phí sang mọi request và mọi service nhận token.

## 8. Giới hạn JWE, nested JWT và giải nén

JWE thêm encrypted key, IV, ciphertext và authentication tag. Kích thước token có thể lớn hơn đáng kể so với plaintext, đặc biệt khi dùng key wrapping hoặc nhiều recipient trong JSON serialization.

Nếu hỗ trợ JWE, cần giới hạn:

- Tổng compact JWE bytes.
- Kích thước từng segment.
- Recipient/key management operations theo profile.
- Plaintext bytes sau authenticated decryption.
- Số lớp nested JWT và tổng kích thước sau giải mã.
- Số lần decrypt/key unwrap tối đa.

### 8.1. Nested token depth

Không parse lặp không giới hạn khi một token chứa một token khác. Đặt maximum nesting depth theo profile. Nếu endpoint chỉ chấp nhận một cấu trúc cụ thể, từ chối token lồng sâu hơn.

### 8.2. Compression và decompression bombs

JWE có thể sử dụng compression header parameter zip trong một số profile/triển khai. Nén có thể giảm wire size nhưng dữ liệu sau giải nén có thể lớn hơn nhiều.

Nếu không có nhu cầu rõ ràng, tránh bật compression. Nếu hỗ trợ:

- Chỉ cho phép thuật toán compression được profile định nghĩa.
- Xác thực integrity/authentication của JWE trước khi giải nén plaintext.
- Giới hạn decompressed bytes và expansion ratio.
- Giới hạn CPU/time của decompressor.
- Từ chối output vượt ngưỡng trước khi chuyển cho JSON parser hoặc business logic.

Không để một token nhỏ sau truyền tải tạo ra payload rất lớn trong memory.

## 9. Rate limit cho request xác minh JWT

Rate limit giới hạn số request có thể đi vào một route hoặc nhóm tài nguyên trong một khoảng thời gian. Với JWT, cần tách rate limit trước và sau khi xác minh.

### 9.1. Pre-authentication rate limit

Trước khi xác minh token, không được tin sub, client_id, tenant hoặc role lấy từ JWT chưa xác minh. Có thể dùng các tín hiệu ở lớp network/ingress:

- IP hoặc network prefix, nếu kiến trúc cho phép và đã xử lý NAT.
- Connection identity đã được xác thực ở tầng trước.
- API key/client identifier độc lập với JWT nếu có.
- Route, method và loại request.
- Global service budget.

Không dùng claim chưa xác minh để cấp quota cao hơn hoặc miễn rate limit.

### 9.2. Post-authentication rate limit

Sau khi JWT và profile đã được xác minh, có thể áp dụng quota theo:

- Issuer/client identity đã xác minh.
- Cặp (iss, sub) nếu quota theo người dùng là cần thiết.
- Tenant đã xác minh và được ánh xạ từ claim đáng tin.
- Scope/operation class hoặc nhóm API.
- Chi phí nghiệp vụ và mức độ nhạy cảm.

Không dùng sub đơn lẻ làm key toàn cục khi có nhiều issuer.

### 9.3. Nhiều tầng rate limit

Một thiết kế thực tế có thể có:

1. Global rate limit để bảo vệ toàn service.
2. Per-route limit để bảo vệ endpoint tốn tài nguyên.
3. Per-client/tenant limit để phân bổ công bằng.
4. Per-user limit cho nghiệp vụ cần kiểm soát theo tài khoản.
5. Verification-specific limit để bảo vệ CPU crypto và key resolver.

Không nên chỉ rate limit theo IP vì nhiều người dùng có thể chia sẻ NAT, còn attacker có thể phân tán qua nhiều IP. Kết hợp nhiều chiều và điều chỉnh theo threat model.

## 10. Thuật toán rate limiting và concurrency limiting

Một số cách triển khai thường dùng:

| Cơ chế | Đặc điểm | Khi phù hợp |
| --- | --- | --- |
| Fixed window | Đơn giản, đếm theo cửa sổ cố định | Quota dễ hiểu, chấp nhận burst ở ranh giới |
| Sliding window | Giảm burst tại ranh giới cửa sổ | Quota cần chính xác hơn |
| Token bucket | Cho phép burst có giới hạn, duy trì average rate | API có traffic dao động |
| Leaky bucket | Làm phẳng tốc độ xử lý | Downstream cần tốc độ ổn định |
| Concurrency limit | Giới hạn số request đang chạy cùng lúc | Công việc CPU/memory nặng |
| Work budget | Giới hạn tổng chi phí ước lượng | Request có cost khác nhau |

Rate limit và concurrency limit giải quyết hai vấn đề khác nhau. Một hệ thống có thể nhận request ở tốc độ vừa phải nhưng giữ mỗi request rất lâu, làm số tác vụ đang chạy tăng không giới hạn. Ngược lại, request ngắn có thể có rate cao nhưng concurrency thấp.

### 10.1. Token bucket

Token bucket có capacity tối đa và refill theo thời gian. Mỗi request tiêu thụ một hoặc nhiều token theo cost:

~~~text
bucket = min(capacity, bucket + elapsed_time * refill_rate)

if bucket >= request_cost:
    bucket = bucket - request_cost
    allow()
else:
    reject_with_429()
~~~

Request xác minh chữ ký có thể có cost khác request health check. Không cần biến mọi request thành một đơn vị chi phí giống nhau nếu các operation có độ nặng khác biệt.

### 10.2. Concurrency và bulkhead

Giới hạn số crypto verification đang chạy song song theo CPU budget. Tách pool hoặc semaphore cho:

- JWT signature verification.
- JWE decryption/key unwrap.
- JWKS network refresh.
- Database/key registry lookup.

Bulkhead giúp một nhóm công việc quá tải không chiếm hết tài nguyên của các nhóm còn lại. Khi hết capacity, reject hoặc shed load nhanh thay vì xếp hàng không giới hạn.

## 11. Giới hạn số lần thử xác minh chữ ký

Verifier không nên thử nhiều khóa, issuer hoặc thuật toán cho đến khi một phép xác minh tình cờ thành công. Việc thử lần lượt nhiều candidate làm tăng CPU cost và có thể tạo key confusion.

Policy đề xuất:

- Chọn issuer/key set từ trust configuration đã quản trị.
- Chỉ cho phép thuật toán trong allowlist của token profile.
- Dùng key ID để exact lookup trong đúng key set.
- Lọc key theo key type, curve, algorithm, use và key_ops phù hợp.
- Chỉ chấp nhận đúng một candidate key.
- Giới hạn số lần refresh JWKS khi key ID không tồn tại.
- Không fallback sang issuer, key hoặc algorithm khác.

Nếu profile cho phép token không có key ID, phải định nghĩa cách chọn khóa bằng metadata tin cậy và giới hạn candidate count. Nếu có nhiều candidate không thể phân biệt một cách an toàn, từ chối token thay vì thử toàn bộ key set.

### 11.1. Một request nên có verification budget rõ ràng

Với compact JWS profile đơn giản, mục tiêu thường là một key candidate và một phép verify chữ ký. Những profile hỗ trợ nhiều chữ ký hoặc nhiều recipient phải đặt giới hạn riêng và kiểm tra chúng trước khi thực hiện từng phép crypto.

Không nhầm retry request với số lần verify nội bộ. Một request bị retry qua nhiều tầng có thể lặp lại toàn bộ chi phí parse, key lookup và verify; cần kiểm soát retry ở client, gateway và service.

## 12. Giới hạn thuật toán và kích thước khóa

Thuật toán và key size ảnh hưởng trực tiếp đến CPU, memory và latency:

- RSA verification có chi phí phụ thuộc kích thước modulus và provider.
- ECDSA/EdDSA có profile key/curve và chi phí khác nhau.
- HMAC thường nhanh hơn nhưng yêu cầu bảo vệ shared secret và constant-time comparison.
- JWE key management và content decryption có chi phí khác nhau.

Biện pháp:

- Allowlist thuật toán theo issuer và token profile.
- Chỉ hỗ trợ key size/curve đáp ứng security policy.
- Không cho token tự chọn thuật toán ngoài allowlist.
- Từ chối key type/curve không phù hợp trước khi gọi crypto provider.
- Đo CPU/latency theo thuật toán và key size trên phần cứng production-like.
- Tránh fallback sang thuật toán yếu hoặc thử nhiều thuật toán.

Không chọn thuật toán chỉ vì benchmark nhanh nhất. Security strength, interoperability, key lifecycle và threat model vẫn là tiêu chí chính.

## 13. Giới hạn JWKS refresh và key lookup

Một kiểu tấn công phổ biến là gửi nhiều token có key ID ngẫu nhiên để buộc verifier liên tục tải JWKS, truy vấn database hoặc gọi key service. Nếu mỗi request unknown key kích hoạt một network fetch, chi phí của attacker có thể được nhân lên trên toàn hệ thống.

Thiết kế key resolver:

- JWKS URI phải đến từ issuer/trust configuration đã quản trị.
- Không fetch URL do JWT header tùy ý cung cấp.
- Chỉ refresh khi lookup đúng issuer/key set không tìm thấy key và policy cho phép.
- Dùng single-flight để các request đồng thời cùng chờ một lần refresh.
- Có cooldown theo issuer/key set, không theo từng key ID ngẫu nhiên.
- Giới hạn timeout, response bytes, số JWK và số redirect.
- Validate TLS, issuer metadata, JSON structure và key metadata trước khi cập nhật cache.
- Nếu refresh không thành công, không dùng key bất kỳ hoặc thử key của issuer khác.

### 13.1. Unknown key không được tạo fetch storm

Ví dụ, một đợt request chứa hàng nghìn key ID khác nhau không nên tạo hàng nghìn lượt tải JWKS. Refresh cần được gộp theo trusted issuer profile. Sau khi một lần refresh thành công, các request có thể tra cứu lại trong cùng key set mới.

Negative cache có thể ghi nhớ tạm thời key ID không tồn tại, nhưng phải giới hạn TTL và cardinality để attacker không tạo vô hạn entry. Sau khi key set thay đổi thành công, negative entries liên quan cần được làm mới hoặc hết hạn theo policy.

### 13.2. Giới hạn response JWKS

Không chỉ request JWT mới cần giới hạn. JWKS response từ upstream cũng là dữ liệu bên ngoài:

- Giới hạn response body bytes.
- Giới hạn số lượng JWK.
- Giới hạn độ dài kid và kích thước từng key.
- Từ chối JSON malformed, duplicate member hoặc key metadata không hợp lệ theo profile.
- Giới hạn thời gian DNS, connect, TLS và response.
- Không cho redirect dẫn đến host hoặc network ngoài trust policy.

Một JWKS quá lớn có thể làm tăng memory, parse time và chi phí lựa chọn khóa cho mọi request sau đó.

## 14. Timeout, retry và backoff

Retry có thể tăng độ tin cậy trước lỗi mạng tạm thời, nhưng retry không giới hạn làm khuếch đại tải khi dependency đang suy giảm.

Phân biệt các trường hợp:

- **Chữ ký sai:** không retry phép verify; cùng input và key sẽ tiếp tục sai.
- **Key ID không tồn tại:** có thể refresh trusted JWKS một lần theo cooldown rồi lookup lại.
- **JWKS timeout hoặc lỗi mạng:** retry giới hạn với exponential backoff và jitter, tùy ngân sách thời gian request.
- **Database/key service tạm lỗi:** dùng circuit breaker và timeout; không giữ request vô hạn.
- **Request bị rate limited:** client tuân theo Retry-After nếu có, đồng thời dùng backoff.
- **Token hết hạn hoặc claims sai:** không retry như lỗi hạ tầng.

Đặt timeout riêng cho từng dependency và tổng deadline cho request. Tổng thời gian chờ các lần retry phải nằm trong deadline còn lại của request.

### 14.1. Exponential backoff có jitter

Mô hình khái niệm:

~~~text
delay = min(max_delay, base_delay * 2^attempt)
wait = random(0, delay)
~~~

Jitter giúp các client không đồng loạt retry cùng thời điểm sau một outage. Số lần retry phải có giới hạn; khi hết budget, trả lỗi tạm thời phù hợp và cho phép caller thử lại sau.

Không retry POST hoặc thao tác nghiệp vụ không idempotent một cách tự động nếu không có idempotency strategy. Việc retry xác minh JWT và retry business operation là hai vấn đề khác nhau.

## 15. Cache key, cache lifetime và kết quả xác minh

Cache giúp giảm key lookup và công việc lặp lại, nhưng cache sai phạm vi có thể làm verifier chọn nhầm key hoặc tiếp tục tin key đã bị thu hồi.

### 15.1. Cache public key

Cache key nên gắn với trust context, ví dụ:

~~~text
environment + issuer_profile + jwks_set + kid
~~~

Không cache chỉ theo key ID vì hai issuer có thể cùng dùng một giá trị. Cache entry cần lưu metadata đủ để kiểm tra algorithm, key type, key purpose và thời gian cập nhật.

### 15.2. Cache lifetime

- Tôn trọng cache policy của JWKS endpoint trong giới hạn tối đa do verifier đặt.
- Có upper bound để key cũ không được giữ vô hạn.
- Có quy trình refresh khi unknown key xuất hiện.
- Có cách invalidation khi issuer/key bị thu hồi hoặc có incident.
- Không tiếp tục dùng stale key vô thời hạn chỉ vì JWKS endpoint đang lỗi.
- Nếu hỗ trợ bounded stale-if-error, phải xác định rõ thời gian tối đa và rủi ro chấp nhận.

### 15.3. Cache kết quả xác minh

Cache kết quả verify có thể giảm CPU nhưng cần đặc biệt thận trọng. Nếu dùng:

- Key cache phải dựa trên hash của toàn bộ compact token hoặc một định danh collision-resistant phù hợp.
- Gắn kết quả với issuer profile, audience, algorithm policy và validation context.
- TTL cache không được vượt thời hạn token còn hiệu lực.
- Xem xét revocation, denylist, session version và thay đổi policy.
- Không để kết quả đã xác minh cho một audience được tái sử dụng ở audience khác.
- Không dùng cache để bỏ qua sender-constraining proof hoặc request-specific checks như DPoP.

Trong nhiều hệ thống, cache public key và cache JWKS là đủ; cache kết quả xác minh chỉ nên triển khai khi benchmark chứng minh lợi ích và policy có thể được bảo toàn.

## 16. Giới hạn concurrency và hàng đợi

Rate limit kiểm soát tốc độ đến; concurrency limit kiểm soát số công việc đang chạy. Khi verifier dùng worker pool hoặc async task queue, cần giới hạn:

- Số request đang chờ.
- Số request đang parse/verify.
- Số crypto operations đồng thời.
- Số JWKS fetch đang chạy.
- Số database/key service calls đang chờ.
- Thời gian tối đa một request được giữ trong queue.

Không dùng queue không giới hạn để hấp thụ burst. Queue quá dài làm tăng latency, giữ memory và có thể khiến request hết hạn trước khi được xử lý. Khi queue đầy, reject sớm hoặc shed load có kiểm soát.

### 16.1. Bulkhead và ưu tiên

Tách tài nguyên cho các nhóm công việc có profile khác nhau. Ví dụ, JWKS refresh không nên chiếm hết worker dành cho request API thông thường. Health check cũng không nên cạnh tranh với lượng lớn crypto verification.

Ưu tiên phải dựa trên chính sách được quản trị, không dựa trên role hoặc claim chưa xác minh.

## 17. Pseudocode admission và verification budget

Ví dụ tổng quát:

~~~text
function handleProtectedRequest(request):
    if request.headerBytes > LIMITS.maxRequestHeaderBytes:
        reject(431)

    if not globalLimiter.allow(request.networkContext):
        reject(429)

    if not concurrencyGate.tryAcquire(request.route):
        reject(503)

    try:
        token = extractTokenFromConfiguredLocation(request)

        if byteLength(token) > LIMITS.maxCompactTokenBytes:
            reject(400)

        segments = splitCompactSerializationWithLimit(token)
        requireExpectedSegmentCount(segments, request.tokenProfile)
        requireSegmentLimits(segments, LIMITS)

        header = decodeAndParseHeaderWithLimits(segments.header)
        profile = resolveTrustedIssuerProfile(request, header)
        algorithm = requireAllowedAlgorithm(profile, header.alg)
        candidates = exactKeyLookup(profile, header.kid, algorithm)

        if candidates.isEmpty():
            refreshTrustedJwksAtMostOnce(profile)
            candidates = exactKeyLookup(profile, header.kid, algorithm)

        if candidates.count != 1:
            reject(401)

        if not cryptoBudget.tryConsume(estimatedCost(algorithm, candidates[0])):
            reject(503)

        if not verifySignature(token, candidates[0]):
            reject(401)

        claims = decodeAndParseClaimsWithLimits(segments.payload)
        validateClaimsAndTokenProfile(claims, profile)
        applyAuthenticatedRateLimit(profile, claims, request.route)
        authorizeAndExecute(request, claims)
    finally:
        concurrencyGate.release(request.route)
~~~

Đây là pseudocode về thứ tự và ngân sách, không phải API của một thư viện cụ thể. Triển khai thực tế phải bảo đảm mọi nhánh reject đều giải phóng semaphore/tài nguyên, không đọc claims chưa xác minh để cấp quyền và không thực hiện business side effect trước khi hoàn tất xác minh.

## 18. Ví dụ cấu hình giới hạn

Ví dụ dưới đây minh họa cách gom policy vào một cấu hình có version. Các con số chỉ là giá trị khởi đầu để thử nghiệm; cần điều chỉnh theo token profile, HTTP stack, traffic và benchmark của hệ thống.

~~~yaml
limits:
  http:
    max_request_header_bytes: 16384
    max_header_count: 64
    request_header_timeout_ms: 3000

  jwt:
    max_compact_token_bytes: 8192
    max_header_segment_bytes: 2048
    max_payload_segment_bytes: 6144
    max_signature_segment_bytes: 2048
    max_decoded_header_bytes: 1536
    max_decoded_payload_bytes: 4608
    max_json_depth: 16
    max_json_members: 128
    max_array_elements: 256
    max_nested_token_depth: 1

  verification:
    allowed_algorithms:
      - RS256
      - ES256
    max_candidate_keys: 1
    max_signature_verifications: 1
    max_jwe_decryptions: 1
    max_jwks_refresh_per_issuer_window: 1
    jwks_refresh_cooldown_seconds: 30
    crypto_deadline_ms: 100

  admission:
    global_requests_per_second: 500
    per_client_requests_per_second: 80
    max_inflight_verifications: 200
    max_queue_wait_ms: 20
~~~

Không sao chép nguyên các con số này vào production mà không đo tải và xác nhận tương thích. Ví dụ, tổng request header phải đủ chỗ cho các header hợp lệ khác; max token bytes phải phù hợp với mọi issuer/client; crypto deadline phải dựa trên phần cứng và thuật toán thực tế.

Giữ policy có version và triển khai đồng nhất ở ingress, gateway và verifier. Nếu cần khác nhau giữa các profile, khai báo profile rõ ràng thay vì để từng service tự đặt ngưỡng không kiểm soát.

## 19. Quan sát hiệu năng và giới hạn

Theo dõi cả lưu lượng, chi phí và kết quả từ chối:

**Kích thước và parser**

- Phân bố kích thước JWT theo profile (p50, p95, p99, max).
- Số request bị từ chối do HTTP header, token bytes, segment hoặc JSON limits.
- Parse latency và decoded bytes.
- Tỷ lệ token có claims lớn hoặc schema bất thường.

**Rate và concurrency**

- Request rate theo route và nhóm client.
- Số request đang chạy, queue depth và queue wait.
- Tỷ lệ 429/503 và số lần shed load.
- Tỷ lệ retry và timeout.

**Key lookup và crypto**

- Key cache hit/miss.
- JWKS refresh count, latency, failure và response size.
- Candidate key count và unknown key rate.
- Signature verification count/latency theo algorithm.
- JWE decrypt/key unwrap count/latency.
- CPU time, memory và crypto worker saturation.

Không dùng raw JWT, access token, key ID tùy ý, subject hoặc IP làm metric label có cardinality cao. Dùng token profile, algorithm, reason code và nhóm route đã chuẩn hóa. Log chi tiết phải được giới hạn, phân quyền và không chứa credential.

## 20. Kiểm thử tải và kiểm thử giới hạn

Kiểm thử phải chứng minh cả request hợp lệ được xử lý lẫn request vượt ngưỡng bị chặn trước khi tiêu tốn tài nguyên lớn.

### 20.1. Size boundary tests

- Token có kích thước ngay dưới giới hạn.
- Token đúng bằng giới hạn.
- Token vượt một byte.
- Header segment hoặc payload segment vượt giới hạn riêng.
- Base64url segment decode ra kích thước vượt giới hạn.
- JSON depth, member count, array count và string length ở ranh giới.
- JWE plaintext sau giải mã hoặc giải nén vượt giới hạn.

Ghi rõ boundary semantics: giới hạn thường cho phép giá trị bằng ngưỡng và từ chối khi lớn hơn, nhưng phải nhất quán giữa mọi tầng.

### 20.2. Rate và concurrency tests

- Traffic bình thường, burst ngắn và sustained overload.
- Nhiều client cùng NAT.
- Một client gửi request vượt quota.
- Attacker phân tán request qua nhiều nguồn.
- Crypto verification chậm làm tăng inflight count.
- Queue đầy và timeout xảy ra đồng thời.
- Rate limiter hoặc distributed store bị lỗi.

Đo throughput, p95/p99 latency, CPU, memory, queue depth và tỷ lệ reject. Xác nhận service vẫn phục hồi sau burst và không tiếp tục giữ queue cũ.

### 20.3. Verification-attempt tests

- Key ID hợp lệ có đúng một candidate.
- Unknown key chỉ kích hoạt số lần JWKS refresh đã định.
- Nhiều key cùng khớp gây reject thay vì thử lần lượt.
- Algorithm ngoài allowlist bị từ chối trước crypto.
- JWE có recipient hoặc nested depth vượt giới hạn bị từ chối.
- Chữ ký sai không kích hoạt retry verify.
- Một request không vượt crypto work budget.

### 20.4. Negative side-effect tests

Xác nhận request bị từ chối do size/rate/verification limit không tạo đơn hàng, không cập nhật dữ liệu, không gửi email hoặc không thực hiện thao tác nghiệp vụ. Kiểm tra cả log và downstream calls để phát hiện side effect xảy ra trước bước reject.

## 21. Triển khai và thay đổi giới hạn an toàn

Giới hạn quá chặt có thể gây outage; giới hạn quá rộng có thể không bảo vệ được hệ thống. Thay đổi policy nên được triển khai có quan sát:

1. Thu thập baseline kích thước token, request rate và verify latency.
2. Xác định client/profile hợp lệ có giá trị lớn nhất và lý do.
3. Thử policy mới ở staging với proxy và gateway giống production.
4. Chạy shadow measurement hoặc cảnh báo khi request gần ngưỡng trước khi enforce nếu kiến trúc cho phép.
5. Triển khai theo nhóm nhỏ/canary.
6. Theo dõi reject rate, latency, support errors và dependency load.
7. Có rollback về policy version trước nếu xuất hiện lỗi tương thích.
8. Thông báo cho issuer/client khi giới hạn ảnh hưởng đến contract.

Không tự động tăng giới hạn sau mỗi đợt reject. Trước hết xác định đó là client hợp lệ có nhu cầu thực hay dấu hiệu tấn công/claims phình to.

## 22. Xử lý khi hệ thống quá tải

Khi verifier hoặc dependency quá tải:

- Từ chối sớm request mới khi đã hết admission capacity.
- Giữ queue có giới hạn và deadline ngắn.
- Dùng circuit breaker cho JWKS/database/KMS khi dependency lỗi kéo dài.
- Gộp refresh đồng thời theo issuer.
- Tránh retry storm và tránh gọi dependency cho từng request lỗi.
- Ưu tiên duy trì các endpoint cần thiết theo policy vận hành.
- Trả 429 khi quota của caller bị vượt; trả 503 khi service không thể nhận thêm công việc.
- Phát cảnh báo theo saturation và error budget, không chỉ theo CPU.

### 22.1. Rate limiter phụ thuộc vào datastore

Nếu distributed rate-limit store bị lỗi, cần có policy fallback được định trước. Một số endpoint rủi ro cao có thể fail closed; endpoint ít nhạy cảm có thể dùng local conservative limit trong thời gian ngắn. Không mặc định fail open cho mọi route vì điều đó có thể biến sự cố của limiter thành cửa mở cho DoS.

Fallback phải có thời hạn, metrics và cảnh báo. Khi datastore phục hồi, tránh đồng bộ lại state theo cách tạo burst hoặc deadlock.

## 23. Những anti-pattern cần tránh

| Anti-pattern | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Không giới hạn tổng token bytes | Memory/CPU tăng theo input attacker | Reject trước decode khi vượt profile limit |
| Chỉ giới hạn HTTP body, bỏ qua header | Authorization/Cookie header có thể quá lớn | Giới hạn tổng headers và từng field |
| Parse/decode rồi mới kiểm tra size | Cấp phát memory trước khi reject | Pre-check bytes và decoded-size bound |
| Nhúng toàn bộ profile/permission vào JWT | Token lớn và claims phình theo thời gian | Data minimization và claim schema |
| Rate limit chỉ theo IP | NAT false positive và distributed bypass | Kết hợp global, route, client và authenticated identity |
| Dùng sub chưa xác minh làm quota key | Attacker tự chọn quota identity | Chỉ dùng network context trước verify |
| Thử mọi key/algorithm đến khi thành công | CPU exhaustion và key confusion | Allowlist, exact lookup, một candidate |
| Unknown kid kích hoạt JWKS fetch mỗi request | Network/CPU exhaustion | Single-flight, cooldown và negative cache |
| Retry vô hạn khi dependency lỗi | Retry storm và queue tăng | Deadline, backoff, jitter và max attempts |
| Queue không giới hạn | Memory tăng và latency không kiểm soát | Bounded queue, concurrency gate và shed load |
| Cache key chỉ theo kid | Cross-issuer collision | Cache namespace theo trusted issuer/key set |
| Cache key hoặc verify result quá lâu | Key revoke/policy change không có hiệu lực | TTL bound và invalidation policy |
| Nới ngưỡng để xử lý token phình to | Mở rộng chi phí trên mọi request | Sửa issuer claims và profile |
| Ghi toàn bộ JWT khi lỗi | Credential leakage và log amplification | Log reason code, request ID và metadata an toàn |

## 24. Checklist giới hạn và vận hành

**Kích thước**

- [ ] Có giới hạn tổng request headers và từng header field.
- [ ] Có giới hạn tổng compact JWT bytes.
- [ ] Có giới hạn từng segment và decoded header/payload.
- [ ] JSON parser có depth, member, array và string limits.
- [ ] Có giới hạn JWE plaintext, decompression và nested depth nếu hỗ trợ.
- [ ] Giới hạn được đồng bộ giữa ingress, gateway và resource server.

**Rate và concurrency**

- [ ] Có global và per-route rate limit.
- [ ] Có per-client/tenant limit sau khi identity được xác minh.
- [ ] Pre-auth limit không tin claims từ JWT chưa xác minh.
- [ ] Có concurrency gate, bounded queue và shed-load policy.
- [ ] Rate limiter có fallback policy và metrics khi datastore lỗi.

**Verification attempts**

- [ ] Thuật toán nằm trong allowlist.
- [ ] Key lookup nằm trong trusted issuer/key set.
- [ ] Candidate key count được giới hạn và ambiguity bị reject.
- [ ] Không thử lần lượt mọi key hoặc algorithm.
- [ ] JWKS refresh có single-flight, cooldown, timeout và response-size limit.
- [ ] Retry có deadline, backoff, jitter và maximum attempts.
- [ ] JWE recipient/decrypt và nested processing có work budget.

**Cache và quan sát**

- [ ] Cache key bao gồm issuer/profile/key-set context.
- [ ] Cache lifetime có upper bound và revoke/invalidation strategy.
- [ ] Metrics có size, rate, concurrency, key lookup, crypto latency và reject reason.
- [ ] Không log JWT, secret hoặc dùng raw token/subject làm metric label.
- [ ] Có cảnh báo cho unknown-kid flood, JWKS refresh spike và saturation.

**Kiểm thử và thay đổi**

- [ ] Có test ngay dưới, bằng và vượt mỗi size boundary.
- [ ] Có burst, sustained load, distributed traffic và queue-full tests.
- [ ] Có test số candidate key, refresh count và crypto budget.
- [ ] Request bị reject không gây business side effect.
- [ ] Có canary, rollback và versioning cho limit policy.

## 25. Tài liệu chuẩn tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): cấu trúc JWS và xác minh chữ ký.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): JWE, authenticated decryption và các bước xử lý.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS và key selection metadata.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán JOSE và yêu cầu tham số.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT claims và serialization.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm allowlist, validation và phòng token confusion.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP status, request semantics và Content Too Large.
- [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585): 429 Too Many Requests và 431 Request Header Fields Too Large.
- [OWASP API4:2023 — Unrestricted Resource Consumption](https://owasp.org/API-Security/editions/2023/en/0xa4-unrestricted-resource-consumption/): giới hạn tài nguyên API, request và chi phí xử lý.
- [OWASP Denial of Service Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html): kiểm soát tài nguyên và giảm thiểu DoS.

**Ghi nhớ:** giới hạn kích thước chặn input lớn; rate limit kiểm soát tốc độ; concurrency và verification budget giới hạn công việc đang chạy trên mỗi request. Hãy đặt giới hạn trước bước tốn tài nguyên, ràng buộc key lookup với trust configuration, giới hạn JWKS refresh/retry, đo trên toàn đường đi và kiểm thử boundary cùng tình huống quá tải.
