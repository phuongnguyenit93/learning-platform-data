# Cân bằng bảo mật, độ trễ và tính sẵn sàng của quy trình xác minh

## 1. Xác minh JWT là một pipeline, không chỉ là phép kiểm tra chữ ký

Khi một resource server nhận JSON Web Token (JWT), nó phải thực hiện nhiều bước trước khi quyết định chấp nhận request:

1. Giới hạn kích thước và phân tích cấu trúc token.
2. Xác định token profile và chính sách issuer được phép.
3. Chọn khóa tin cậy và thuật toán được phép.
4. Xác minh chữ ký hoặc giải mã theo loại JOSE.
5. Kiểm tra issuer, audience, thời gian và claims bắt buộc.
6. Kiểm tra trạng thái bổ sung như revocation, session, replay hoặc delegation nếu policy yêu cầu.
7. Đưa ra quyết định authorization cho hành động và tài nguyên cụ thể.

Mỗi bước có chi phí và đặc tính lỗi khác nhau. Parsing và chữ ký thường tiêu tốn CPU; tải JWKS, introspection hoặc replay store có thể tạo độ trễ mạng; kiểm tra trạng thái tập trung làm tăng phụ thuộc availability; cache giúp giảm chi phí nhưng có thể làm trạng thái cũ tồn tại lâu hơn.

Vì vậy, tối ưu xác minh không có nghĩa là bỏ bớt kiểm tra bảo mật. Mục tiêu là **đáp ứng threat model với chi phí và độ trễ có thể dự đoán, đồng thời xác định rõ hành vi khi một dependency không khả dụng**.

## 2. Ba chiều cần cân bằng

### 2.1. Security

Mức bảo vệ phụ thuộc vào các câu hỏi:

- Token có được xác minh bằng thuật toán và khóa tin cậy không?
- Issuer, audience, thời gian và token profile có được kiểm tra không?
- Khóa hoặc token bị thu hồi có bị từ chối trong thời gian yêu cầu không?
- Replay, session state hoặc delegation có cần kiểm tra trực tuyến không?
- Khi không thể xác minh trạng thái, hệ thống có vô tình chấp nhận token không?

### 2.2. Latency

Độ trễ gồm thời gian xử lý cục bộ và thời gian chờ dependency:

- Parse/validate cấu trúc và claims.
- Tính toán chữ ký/MAC hoặc giải mã.
- Đọc khóa từ cache hoặc JWKS endpoint.
- Gọi introspection, replay store, session store hoặc policy service.
- Chờ retry, queue, connection pool hoặc circuit breaker.

Một bước crypto có thể tốn CPU nhưng ổn định và chạy cục bộ. Một lần gọi mạng có thể có chi phí CPU thấp nhưng latency biến động theo tải, DNS, TLS, routing và trạng thái vùng.

### 2.3. Availability

Resource server có thể phụ thuộc vào:

- Issuer/JWKS endpoint để lấy public key.
- Authorization server để introspect token hoặc đổi token.
- Replay store để bảo đảm one-time-use.
- Session/revocation store để kiểm tra trạng thái.
- Policy service để quyết định quyền động.
- KMS/HSM hoặc dịch vụ ký/giải mã trong một số mô hình.

Thêm dependency có thể tăng khả năng thu hồi tức thời hoặc kiểm tra policy mới nhất, nhưng cũng thêm một điểm có thể làm request thất bại.

## 3. Xây dựng ngân sách độ trễ cho pipeline

Không nên đo riêng thời gian xác minh chữ ký rồi coi đó là latency của xác minh JWT. Cần đo từng thành phần và tổng thời gian ở các percentile.

Một mô hình đơn giản:

~~~text
T_verify =
    T_parse
  + T_key_lookup
  + T_signature
  + T_claim_validation
  + T_state_checks
  + T_authorization
~~~

Trong đó:

- T_key_lookup gần như chỉ là cache lookup khi key đã có sẵn; khi cache miss có thể bao gồm network round trip tới JWKS.
- T_state_checks có thể gồm introspection, replay, session hoặc revocation lookup.
- Một số bước có thể chạy song song nếu không phụ thuộc kết quả nhau, nhưng không được cho phép side effect trước khi tất cả kiểm tra bắt buộc hoàn tất.

Đo p50, p95, p99 và tỷ lệ lỗi cho từng bước. Trung bình thấp có thể che giấu tail latency rất cao khi JWKS endpoint hoặc replay store chậm.

### 3.1. Phân loại chi phí

| Thành phần | Loại chi phí chính | Cách giảm chi phí có kiểm soát |
| --- | --- | --- |
| Parse JWT/JSON | CPU và allocation | Giới hạn kích thước, parser hiệu quả, tránh parse lặp |
| Signature verification | CPU | Chọn thuật toán phù hợp profile, benchmark trên phần cứng thực |
| JWK lookup | Memory/CPU | Cache theo issuer và kid |
| JWKS refresh | Network và TLS | Refresh theo TTL, single-flight, backoff |
| Claim validation | CPU thấp đến vừa | Policy rõ, tránh truy vấn dữ liệu không cần thiết |
| Introspection | Network và authorization server capacity | Chỉ dùng khi cần trạng thái trực tuyến, cache theo policy |
| Replay/session lookup | Network và storage I/O | Atomic operation, partitioning, connection pooling |
| Policy evaluation | CPU hoặc network | Cache policy version có giới hạn, tối ưu dữ liệu đầu vào |

Không tối ưu một thành phần bằng cách làm yếu thành phần khác. Ví dụ không được bỏ qua audience validation để giảm CPU hoặc bỏ verify khi key service chậm.

## 4. Xác minh JWT cục bộ và introspection trực tuyến

Hai mô hình có đặc tính vận hành khác nhau:

| Tiêu chí | JWT tự chứa, xác minh cục bộ | Introspection |
| --- | --- | --- |
| Cần gọi mạng mỗi request | Thường không, nếu khóa đã cache và không cần state check | Thường có, trừ khi kết quả được cache |
| Latency | Thường ổn định hơn | Phụ thuộc authorization server/network |
| Khả năng thu hồi tức thời | Hạn chế nếu không có denylist/state check | Có thể phản ánh trạng thái hiện tại theo server |
| Availability | Ít phụ thuộc issuer trong đường request | Phụ thuộc introspection service |
| Tải phía issuer | Thấp hơn khi nhiều resource server tự verify | Tăng theo số lần introspection |
| Trạng thái động | Cần cơ chế bổ sung | Có thể kiểm tra tập trung |

JWT cục bộ phù hợp khi token ngắn hạn, claims ổn định và hệ thống chấp nhận cửa sổ thu hồi tương ứng. Introspection phù hợp khi cần trạng thái token hiện tại, token opaque hoặc quyết định tập trung.

Có thể kết hợp: xác minh chữ ký và claims cục bộ, sau đó gọi introspection hoặc trạng thái tập trung chỉ cho loại token, endpoint hoặc hành động có rủi ro cao. Quy tắc kết hợp phải rõ; không được xem introspection là thay thế mọi kiểm tra chữ ký/audience khi profile yêu cầu các bước đó.

## 5. Cache khóa xác minh và JWKS

Cache public key là một trong những cách giảm latency hiệu quả nhất cho JWT ký bất đối xứng. Sau khi lấy JWKS từ endpoint tin cậy, verifier có thể dùng khóa trong cache để xác minh nhiều token mà không gọi mạng cho từng request.

### 5.1. Cache theo issuer và kid

Key cache cần gắn với issuer/trust domain, không chỉ kid. Hai issuer độc lập có thể dùng cùng một chuỗi kid nhưng khóa khác nhau.

Một entry thường cần liên kết:

- Issuer đã được cấu hình tin cậy.
- kid.
- Key type và các tham số public key.
- Algorithm/key use phù hợp.
- Thời điểm tải và thời hạn cache.
- Trạng thái/phiên bản trust configuration.

Không lấy URL JWKS từ token rồi tự tải. Endpoint phải đến từ cấu hình hoặc metadata tin cậy của issuer.

### 5.2. Refresh khi hết TTL

Khi cache hết TTL, verifier có thể tải JWKS mới theo chính sách. Nên có:

- TTL rõ ràng và phù hợp với lịch rotation.
- Timeout riêng cho JWKS fetch.
- Giới hạn retry và exponential backoff có jitter.
- Single-flight/request coalescing để nhiều request cùng cache miss chỉ tạo một lần refresh.
- Giới hạn số request refresh đồng thời.
- Quan sát số lần refresh, lỗi, latency và tuổi của key cache.

Không để mỗi request cùng phát hiện cache hết hạn đều gọi JWKS. Một đợt cache expiry đồng loạt có thể tạo request storm và làm issuer quá tải.

### 5.3. Unknown kid và negative caching

Khi token có kid chưa có trong cache, verifier có thể refresh JWKS một lần để xử lý rotation hợp lệ. Nếu vẫn không tìm thấy khóa, token phải bị từ chối.

Attacker có thể gửi nhiều token với kid ngẫu nhiên để kích hoạt refresh liên tục. Giảm rủi ro bằng:

- Single-flight cho mỗi issuer hoặc key set.
- Rate limit refresh.
- Negative cache ngắn cho kết quả kid không tồn tại.
- Giới hạn số lần refresh khi JWKS endpoint lỗi.
- Giới hạn kích thước header/token trước khi tra cứu.

Negative cache phải ngắn và có khả năng bị vô hiệu hóa khi có tín hiệu rotation đáng tin cậy; nếu giữ quá lâu, nó có thể khiến khóa mới hợp lệ không được nhận diện.

### 5.4. Stale key và sự cố JWKS

Nếu JWKS endpoint tạm thời không khả dụng, một số hệ thống có thể tiếp tục dùng last-known-good key trong một khoảng stale có giới hạn. Đây là quyết định availability/security, không phải fallback mặc định.

Chính sách cần trả lời:

- Key cache cũ được dùng thêm tối đa bao lâu?
- Điều gì xảy ra với token có kid đã biết so với kid mới?
- Emergency denylist có được kiểm tra trước khi dùng key cache không?
- Làm sao phân phối thu hồi khóa bị xâm phạm đến mọi verifier?
- Khi vượt stale limit, request bị từ chối hay chuyển sang chế độ dự phòng nào?

Stale key có thể giúp request tiếp tục khi issuer gặp outage, nhưng nếu khóa đã bị compromise thì tiếp tục tin key cũ có thể chấp nhận token giả. Cần cơ chế emergency revocation độc lập với JWKS refresh.

## 6. Cache kết quả xác minh token

Một số hệ thống cân nhắc cache kết quả verify để tránh thực hiện cùng phép xác minh nhiều lần cho một token. Việc này có thể giảm CPU nhưng cần giới hạn chặt.

Nếu cache, key phải bao gồm fingerprint của token và ngữ cảnh xác minh, chẳng hạn issuer, audience/resource server, token profile và policy version. Không dùng riêng jti làm cache key nếu uniqueness không được bảo đảm theo phạm vi đó.

TTL cache không được vượt quá:

- Thời gian còn lại đến exp.
- Giới hạn max token age hoặc thời hạn policy.
- Cửa sổ freshness của claims động.
- Thời hạn chấp nhận của trạng thái revocation/introspection nếu cache kết quả đó.

Cache kết quả verify có thể khiến verifier tiếp tục chấp nhận token sau khi signing key bị thu hồi, token bị denylist hoặc quyền đã thay đổi. Cần invalidation khi trust configuration/key status thay đổi, và không cache chung kết quả authorization động nếu policy yêu cầu kiểm tra mới.

### 6.1. Tách cache theo loại dữ liệu

Không gộp mọi trạng thái vào một cache có TTL chung:

| Dữ liệu | Cache có thể áp dụng | Rủi ro khi stale |
| --- | --- | --- |
| Public JWK | Có, theo TTL và rotation policy | Chấp nhận key đã thu hồi hoặc không nhận key mới |
| Signature verification result | Có giới hạn, gắn với context và policy version | Bỏ qua key revocation hoặc thay đổi policy |
| Introspection active result | Có thể, theo yêu cầu freshness | Tiếp tục chấp nhận token đã inactive |
| Replay marker | Có, nhưng phải giữ đủ lâu và không mất ngoài ý muốn | Cho phép credential one-time bị phát lại |
| Authorization decision | Có thể nếu policy version/freshness được quản lý | Quyền đã thu hồi vẫn được dùng |

Cache replay marker cần semantics khác cache kết quả xác minh: marker là trạng thái đã dùng và phải tồn tại qua mọi instance theo phạm vi bảo đảm; cache kết quả verify là dữ liệu có thể tính lại.

## 7. Thời hạn token là một công cụ vận hành

Access token ngắn hạn làm giảm thời gian token bị lộ có thể được sử dụng, đồng thời giới hạn thời gian claims cũ còn được chấp nhận. Nhưng TTL quá ngắn có thể tăng tải token endpoint, refresh request và nguy cơ lỗi do dependency.

Khi chọn TTL, cân nhắc:

- Mức độ nhạy cảm của resource/action.
- Thời gian phát hiện và xử lý sự cố.
- Độ trễ lan truyền revocation/key rotation.
- Tần suất request và chi phí refresh.
- Khả năng offline của client.
- Clock skew giữa issuer và verifier.
- Khả năng sender-constrain token hoặc kiểm tra trạng thái trực tuyến.

Không kéo dài token chỉ để che outage của authorization server. Cũng không đặt TTL cực ngắn mà không kiểm tra tải refresh và hành vi khi client mất kết nối.

## 8. Chi phí của kiểm tra trạng thái trực tuyến

Introspection, denylist, session lookup và replay store giúp kiểm tra trạng thái mà chữ ký JWT tự nó không thể cung cấp. Tuy nhiên, mỗi lần gọi mạng có thể thêm latency và failure mode.

### 8.1. Chỉ kiểm tra trạng thái khi cần

Có thể phân loại theo rủi ro:

- Endpoint đọc ít nhạy cảm có thể dựa vào JWT ngắn hạn và kiểm tra cục bộ nếu threat model cho phép.
- Endpoint thay đổi dữ liệu quan trọng có thể yêu cầu session/revocation check.
- One-time capability cần atomic consume.
- Giao dịch tài chính có thể cần idempotency và kiểm tra trạng thái riêng.
- Hành động quản trị có thể yêu cầu freshness hoặc re-authorization.

Phân loại không được tạo lỗ hổng do attacker chọn endpoint yếu hơn. Chính sách phải được gắn với resource/action phía server.

### 8.2. Cache introspection

Cache kết quả active giúp giảm tải và latency, nhưng tạo cửa sổ mà token đã bị thu hồi vẫn được coi là active. TTL phải xuất phát từ yêu cầu thu hồi tối đa chấp nhận được.

Không cache active vô thời hạn. Không dùng kết quả introspection của một token cho audience/client khác nếu contract không cho phép. Cần định danh token bằng cách an toàn, tránh lưu raw bearer token trong key/log của cache.

### 8.3. Replay và one-time-use

Với one-time credential, thao tác kiểm tra và consume phải nguyên tử. Cache cục bộ từng instance không đủ nếu contract yêu cầu one-time-use trên nhiều instance/region.

Nếu replay store không khả dụng, hệ thống phải áp dụng fail-closed hoặc policy dự phòng đã được phê duyệt cho loại hành động đó. Không chuyển trạng thái unknown thành unused để giữ availability.

## 9. Timeout, retry và circuit breaker

Dependency chậm có thể làm hàng đợi request tăng, chiếm connection và kéo theo outage dây chuyền.

### 9.1. Timeout theo từng dependency

Đặt timeout riêng cho:

- JWKS fetch.
- Introspection.
- Replay/session store.
- Policy service.
- KMS/HSM nếu thao tác nằm trên request path.

Timeout phải nằm trong ngân sách latency tổng. Không để một dependency giữ request vô thời hạn.

### 9.2. Retry có giới hạn

Chỉ retry lỗi transient phù hợp, với:

- Số lần retry nhỏ và có giới hạn.
- Exponential backoff và jitter.
- Tổng thời gian retry nằm trong request deadline.
- Không retry lỗi token invalid, signature invalid, issuer/audience sai.
- Không tạo request storm khi dependency đang quá tải.

Retry một thao tác consume hoặc refresh có thể có semantics đặc biệt. Nếu client không biết lần trước đã commit hay chưa, cần idempotency/request ID hoặc tra cứu trạng thái trước khi gửi lại.

### 9.3. Circuit breaker và bulkhead

Circuit breaker có thể ngừng gọi dependency đang lỗi để bảo vệ hệ thống khỏi chờ đợi và retry liên tục. Bulkhead giới hạn tài nguyên dành cho từng dependency để một dịch vụ chậm không chiếm hết connection/thread của toàn bộ API.

Circuit breaker mở không có nghĩa token được chấp nhận. Nó chỉ cho biết dependency hiện không thể được gọi; quyết định fail-open/closed phải được policy xác định riêng.

## 10. Fail-closed và fail-open theo loại kiểm tra

Không nên có một cờ fail-open chung cho toàn bộ JWT validation. Phải phân biệt lỗi crypto, lỗi policy và lỗi dependency.

| Tình huống | Hành vi an toàn mặc định |
| --- | --- |
| Chữ ký sai hoặc thuật toán không được phép | Fail-closed |
| Issuer, audience hoặc token type sai | Fail-closed |
| Token hết hạn hoặc chưa có hiệu lực | Fail-closed |
| Không tìm thấy khóa tin cậy cho kid | Từ chối; không decode-only |
| JWKS tạm lỗi nhưng có last-known-good key còn trong stale policy | Có thể tiếp tục theo policy giới hạn, trừ khi key bị denylist |
| JWKS lỗi và không có khóa tin cậy hợp lệ | Fail-closed |
| Introspection không khả dụng | Theo policy freshness/risk; không tự coi token active |
| Replay store không khả dụng cho one-time operation | Thường fail-closed hoặc dừng thao tác |
| Policy service không khả dụng | Theo policy của action; không mặc định cấp quyền |
| Logging/metrics không khả dụng | Không làm thay đổi quyết định xác minh; có thể dùng buffer có giới hạn |

Không bao giờ bỏ qua signature verification hoặc chấp nhận token sai issuer/audience để cải thiện availability. Có thể tiếp tục dùng cache hợp lệ theo stale policy, nhưng không thể thay một bước xác minh thất bại bằng decode.

## 11. Bảo vệ pipeline khỏi DoS

Kẻ tấn công có thể khai thác chi phí parse, crypto hoặc dependency bằng cách gửi nhiều token không hợp lệ.

Các biện pháp:

- Giới hạn kích thước Authorization header/token và số phần serialization.
- Từ chối JSON sai định dạng, nesting hoặc claims vượt giới hạn profile.
- Không tải URL do token chỉ định.
- Allowlist thuật toán và key type trước khi thực hiện phép crypto.
- Rate limit theo IP, client/network hoặc tín hiệu chưa xác minh phù hợp; không tin subject/role trước verify.
- Single-flight JWKS refresh và giới hạn unknown-kid refresh.
- Giới hạn concurrency/queue cho introspection, replay store và KMS.
- Timeout và circuit breaker cho dependency.
- Theo dõi tỷ lệ token invalid, kid lạ, refresh thất bại và cache miss.

Không để một token có kid ngẫu nhiên kích hoạt một request JWKS cho mỗi lần gửi. Không thử hàng loạt thuật toán hoặc mọi khóa của mọi issuer cho cùng token.

## 12. Chọn thuật toán và tối ưu crypto

Chi phí chữ ký phụ thuộc thuật toán, kích thước khóa, thư viện, CPU, phần cứng và cách triển khai. Không có thứ tự hiệu năng cố định đúng cho mọi môi trường.

Một số lưu ý:

- RSA verification thường có thể phù hợp cho nhiều verifier vì public key dùng để xác minh và private key chỉ ở issuer; benchmark vẫn cần dựa trên kích thước khóa và thư viện thực tế.
- ECDSA có kích thước chữ ký nhỏ hơn trong nhiều profile, nhưng hiệu năng phụ thuộc curve, implementation và phần cứng.
- EdDSA có đặc tính triển khai và hiệu năng riêng; chỉ dùng khi profile, issuer và toàn bộ consumer hỗ trợ.
- HMAC có chi phí tính toán thấp trong nhiều trường hợp, nhưng mọi verifier giữ shared secret đều có khả năng tạo MAC/token. Chi phí vận hành và blast radius phải được tính cùng hiệu năng.

Chọn thuật toán dựa trên tiêu chuẩn/profile và threat model trước; sau đó benchmark. Không chuyển sang thuật toán yếu hơn hoặc dùng chung secret rộng chỉ vì benchmark một endpoint nhanh hơn.

## 13. Đo lường và capacity planning

Theo dõi tối thiểu:

| Metric | Ý nghĩa |
| --- | --- |
| JWT validation latency p50/p95/p99 | Độ trễ tổng và tail latency |
| Signature verification time | Chi phí crypto cục bộ |
| JWKS cache hit/miss | Hiệu quả cache khóa |
| JWKS refresh count/failure/latency | Sức khỏe key distribution |
| Unknown kid rate | Rotation bất thường hoặc hoạt động dò phá |
| Introspection latency/error/active ratio | Tải và sức khỏe authorization server |
| Replay/session lookup latency/error | Chi phí kiểm tra trạng thái |
| Validation failure by reason | Phân biệt token sai với dependency lỗi |
| Stale key age | Mức độ cũ của key cache |
| Queue/connection pool saturation | Nguy cơ nghẽn dependency |
| CPU/memory per verifier instance | Năng lực xử lý cục bộ |
| Revocation propagation time | Thời gian áp dụng trạng thái thu hồi |

Capacity planning nên dựa trên lưu lượng thực, tỷ lệ cache miss, số token khác nhau, số issuer, tỷ lệ introspection và số thao tác one-time. Đừng chỉ nhân tổng request/giây với thời gian chữ ký; network dependency và cache stampede có thể chi phối tail latency.

## 14. Benchmark và load testing

Một kế hoạch benchmark nên tách các workload:

1. Token hợp lệ, khóa đã cache.
2. Token hợp lệ với nhiều issuer/kid.
3. Token có kid mới gây JWKS refresh.
4. Token không hợp lệ cần bị từ chối.
5. Introspection cache hit và cache miss.
6. Replay check với store bình thường và store có độ trễ cao.
7. Tải đồng thời khi cache hết hạn.
8. Dependency chậm, timeout, failover và partition.

Đo throughput, p50/p95/p99, CPU, memory, connection pool, error rate và số lần gọi dependency. Kiểm tra cả warm cache và cold start.

Không benchmark chỉ bằng token lặp duy nhất: nó có thể làm cache hit gần như tuyệt đối và không phản ánh workload nhiều người dùng/issuer. Cũng cần thử token invalid và unknown kid để đo khả năng chống DoS.

## 15. Vận hành key rotation và revocation

Rotation có kế hoạch thường công bố public key mới trước khi issuer bắt đầu ký bằng key đó, sau đó giữ key cũ trong overlap đến khi token cũ hết hạn theo policy.

Đối với key compromise, cần ưu tiên thu hồi:

- Đưa issuer + kid bị ảnh hưởng vào emergency denylist/trust policy.
- Ngừng ký bằng private key bị lộ.
- Phân phối invalidation đến verifier.
- Xác nhận cache và stale-key path không vượt qua denylist.
- Theo dõi thời gian từ lúc phát lệnh đến verifier cuối cùng từ chối key.

Không dựa riêng vào JWKS TTL để đáp ứng yêu cầu thu hồi khẩn cấp. JWKS refresh và emergency revocation là hai cơ chế vận hành khác nhau.

## 16. Ví dụ quyết định cho ba loại endpoint

| Endpoint | Đường xác minh tham chiếu | Đánh đổi |
| --- | --- | --- |
| Đọc danh mục công khai có kiểm soát | Verify JWT cục bộ, audience/scope/expiry, key cache | Latency thấp; chấp nhận cửa sổ token còn hạn theo policy |
| Xem dữ liệu tài khoản cá nhân | Verify cục bộ, kiểm tra session/revocation theo yêu cầu, authorization theo resource | Thêm lookup để giảm cửa sổ dùng token/phiên đã thu hồi |
| Xác nhận chuyển tiền một lần | Verify đầy đủ, authorization hiện tại, atomic consume/idempotency và trạng thái giao dịch | Latency cao hơn nhưng cần bảo đảm chống replay và side effect trùng |

Đây là ví dụ theo threat model. Một API đọc dữ liệu y tế hoặc dữ liệu nhạy cảm có thể cần kiểm tra trạng thái nghiêm ngặt tương tự endpoint giao dịch; không phân loại chỉ theo HTTP method.

## 17. Checklist vận hành

- [ ] Có ngân sách latency cho từng bước xác minh.
- [ ] Đo p50/p95/p99 và tỷ lệ lỗi riêng cho từng dependency.
- [ ] Thuật toán và issuer được cấu hình allowlist.
- [ ] JWKS endpoint lấy từ nguồn trust configuration.
- [ ] Key cache gắn với issuer + kid, có TTL và refresh policy.
- [ ] Unknown kid không kích hoạt refresh không giới hạn.
- [ ] Có single-flight, timeout, backoff và jitter cho JWKS refresh.
- [ ] Stale key policy có giới hạn và bị emergency denylist ưu tiên.
- [ ] Không dùng decode-only khi key service lỗi.
- [ ] Cache verification/introspection có TTL, context và invalidation rõ.
- [ ] Replay marker được lưu theo phạm vi nhất quán của contract.
- [ ] Fail-open/closed được định nghĩa theo loại action/dependency.
- [ ] Retry không lặp side effect và không gây request storm.
- [ ] Có rate limit, input size limit và concurrency limit.
- [ ] Có load test cold cache, warm cache, unknown kid và dependency outage.
- [ ] Có đo thời gian lan truyền key/token revocation.

## 18. Tình huống tự kiểm tra

Một API nhận 8.000 request/giây. JWT được ký bằng RS256. Public key được cache trong từng instance; JWKS TTL là 15 phút. API cũng gọi introspection cho mọi request. Khi authorization server chậm, p99 tăng mạnh và connection pool bị bão hòa. Nhóm vận hành đề xuất bỏ signature verification và chỉ decode claims khi introspection timeout.

**Câu hỏi 1:** Đề xuất này có chấp nhận được không?

**Trả lời:** Không. Decode không xác minh chữ ký. Introspection timeout cũng không làm token trở nên đáng tin. Hệ thống phải giữ các kiểm tra bắt buộc và áp dụng policy khi dependency không khả dụng.

**Câu hỏi 2:** Có thể giảm latency mà vẫn giữ xác minh không?

**Trả lời:** Có thể đánh giá việc xác minh chữ ký cục bộ bằng key cache và chỉ gọi introspection cho token/action cần trạng thái trực tuyến, nếu threat model và freshness requirement cho phép. Có thể cache kết quả introspection trong TTL giới hạn, nhưng phải định lượng cửa sổ revocation bị kéo dài.

**Câu hỏi 3:** Nếu JWKS endpoint tạm lỗi thì API có phải từ chối mọi token ngay không?

**Trả lời:** Không nhất thiết nếu API có last-known-good key còn trong stale policy và key đó chưa bị emergency denylist. Nhưng nếu không có khóa tin cậy hợp lệ, hoặc khóa đã bị thu hồi, token phải bị từ chối. Không được bỏ qua verify.

**Câu hỏi 4:** Metric nào giúp biết tối ưu đã hiệu quả?

**Trả lời:** So sánh p95/p99 tổng và từng bước, signature time, introspection latency/error, JWKS cache hit/miss, connection saturation, throughput và revocation propagation time. Tối ưu latency phải được đánh giá cùng tỷ lệ lỗi và cửa sổ stale/revocation.

## 19. Ghi nhớ

Quy trình xác minh JWT gồm parsing, key lookup, crypto verification, claim/profile validation và có thể thêm trạng thái trực tuyến như introspection, replay hoặc session. Crypto cục bộ và network dependency có chi phí khác nhau; cache giảm latency nhưng tạo rủi ro stale state.

Hãy đo từng bước, cache public key theo issuer và kid, giới hạn refresh, đặt timeout/retry/circuit breaker, và phân loại fail-open/closed theo loại kiểm tra. Không bao giờ bỏ qua chữ ký, issuer, audience hoặc thời gian để giữ availability. Khi dùng stale key hoặc cache trạng thái, phải có giới hạn, invalidation và emergency revocation.

**Một hệ thống xác minh tốt giữ nguyên các điều kiện bảo mật bắt buộc, đồng thời làm cho chi phí, độ trễ và hành vi khi dependency lỗi trở nên đo lường và dự đoán được.**

## Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): xác minh chữ ký JWS.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS và phân phối khóa.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán JOSE.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): claims và thời hạn token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra trạng thái token trực tuyến.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): chính sách thuật toán, issuer, audience và token profile.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile access token JWT.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): proof-of-possession và replay protection.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo mật OAuth 2.0.
