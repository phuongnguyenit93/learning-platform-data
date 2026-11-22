# Bộ nhớ đệm khóa công khai và độ mới của JWKS

> **Chương:** Hiệu năng và vận hành  
> **Phạm vi:** Security – JSON Web Token (JWT), thuộc module SECURITY_TOKEN_SECURITY_JWT. Bài viết tập trung vào phân phối, lưu đệm, làm mới và thu hồi khóa xác minh JWT trong hệ thống có một hoặc nhiều issuer; không phụ thuộc ngôn ngữ lập trình hoặc framework.

## 1. Vì sao JWKS cache vừa là bài toán hiệu năng vừa là bài toán bảo mật?

Resource server thường xác minh chữ ký JWT bằng public key do issuer công bố qua một JSON Web Key Set (JWKS). Nếu tải JWKS từ xa cho mọi request, hệ thống sẽ tạo thêm latency, phụ thuộc mạng và tải không cần thiết lên authorization server. Vì vậy, resource server thường lưu đệm JWKS và tái sử dụng các public key đã tải.

Nhưng cache khóa có một đặc tính khác cache dữ liệu thông thường: **độ mới của cache ảnh hưởng trực tiếp đến việc token nào được tin cậy**.

- Cache quá ngắn có thể gây nhiều request đến JWKS endpoint, tăng latency và làm hệ thống dễ bị ảnh hưởng khi issuer tạm thời không khả dụng.
- Cache quá dài có thể làm chậm việc nhận biết key mới khi issuer xoay khóa.
- Cache giữ public key đã bị thu hồi có thể tiếp tục xác minh token giả mạo được ký bằng private key đã bị lộ.
- Làm mới JWKS mỗi khi gặp kid lạ mà không giới hạn có thể tạo thành đường DoS vào chính resource server hoặc issuer.
- Cache dùng chung giữa nhiều issuer có thể khiến một key của issuer này bị dùng nhầm để xác minh token của issuer khác.

Do đó, thiết kế JWKS cache cần cân bằng ba mục tiêu:

1. **Hiệu năng:** giảm network round-trip và chi phí parse/validate key.
2. **Tính sẵn sàng:** tiếp tục xử lý token hợp lệ khi mạng hoặc JWKS endpoint gặp lỗi trong giới hạn rủi ro đã chấp nhận.
3. **Tính cập nhật của trust state:** nhận biết key mới, key bị loại bỏ và key bị compromise trong thời gian có thể kiểm soát.

Không có một TTL duy nhất phù hợp cho mọi hệ thống. TTL, chính sách stale cache, refresh trigger và quy trình emergency invalidation phải xuất phát từ token lifetime, tốc độ xoay khóa, threat model và yêu cầu availability.

## 2. JWKS và vai trò của kid

### 2.1. Cấu trúc JWK Set

RFC 7517 định nghĩa JSON Web Key (JWK) và JSON Web Key Set (JWKS). JWKS là một JSON object có member keys, chứa một mảng các JWK.

Ví dụ JWKS chứa hai public key RSA dùng để xác minh chữ ký:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "signing-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-modulus>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "signing-2026-02",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

Các member đáng chú ý:

| Member | Ý nghĩa | Điều cần kiểm tra |
|---|---|---|
| keys | Danh sách JWK | Phải là mảng có cấu trúc hợp lệ. |
| kty | Loại khóa, ví dụ RSA hoặc EC | Phải phù hợp thuật toán và profile. |
| kid | Key ID, dùng để chọn key tương ứng | Chỉ là định danh trong phạm vi trust context, không phải bằng chứng key đáng tin. |
| use | Mục đích sử dụng, ví dụ sig hoặc enc | Key xác minh chữ ký phải phù hợp mục đích ký. |
| key_ops | Các thao tác được phép với key | Nếu có, phải tương thích với thao tác verify. |
| alg | Thuật toán gắn với key nếu được khai báo | Không được vượt qua thuật toán allowlist của validator. |
| n, e | Thành phần public key RSA | Phải được parse và kiểm tra theo yêu cầu thuật toán. |
| crv, x, y | Curve và tọa độ public key EC | Phải khớp curve/algorithm được cho phép. |
| x5c | Chuỗi chứng thư X.509 nếu được dùng | Phải áp dụng trust/validation policy tương ứng; sự hiện diện không tự làm chứng thư đáng tin. |

JWKS phục vụ xác minh thường chỉ công bố public key. Private signing key không được đưa vào JWKS công khai. Đặc biệt, JWK có kty là oct chứa khóa đối xứng trong member k; không được công bố giá trị secret đó tại một JWKS public endpoint. Với RSA/EC, không đưa các private parameter như d, p, q hoặc private scalar vào public set.

### 2.2. kid trong JWT header

Một JWS có thể chứa kid trong JOSE header:

~~~json
{
  "alg": "RS256",
  "kid": "signing-2026-02",
  "typ": "at+jwt"
}
~~~

kid là gợi ý để bên xác minh chọn key phù hợp trong tập key đã tin cậy. Nó không phải secret và không tự chứng minh chữ ký hợp lệ. Giá trị kid là chuỗi phân biệt chữ hoa/thường; lookup phải so khớp chính xác theo trust context, không tự lowercase, trim hoặc dùng prefix/substring.

Khi nhận JWT:

1. Chọn issuer và trust configuration theo cấu hình tin cậy của resource server.
2. Đọc kid như dữ liệu chưa xác minh để tìm candidate key trong JWKS của issuer đó.
3. Kiểm tra candidate key phù hợp với thuật toán/profile.
4. Xác minh chữ ký.
5. Chỉ sau khi chữ ký và các điều kiện profile đạt mới tin claims.

Không tìm key chỉ theo kid toàn cục. Hai issuer khác nhau có thể dùng cùng một chuỗi kid. Cache và key lookup phải được cô lập theo issuer hoặc trust domain.

### 2.3. kid có thể thiếu hoặc không tìm thấy

RFC 7517 mô tả kid là member tùy chọn của JWK; việc sử dụng nó phụ thuộc ứng dụng. JOSE header của JWS cũng không bắt buộc mọi token phải có kid. Không nên tự kết luận mọi JWT đều bắt buộc có kid.

Profile có thể yêu cầu kid. Nếu profile yêu cầu mà header thiếu kid, từ chối token. Nếu profile không yêu cầu:

- Có thể chọn key khi chỉ có đúng một candidate tương thích trong tập key tin cậy.
- Nếu có nhiều candidate và không thể chọn an toàn, từ chối hoặc áp dụng một chiến lược thử hữu hạn đã được profile quy định.
- Không thử mọi key không giới hạn trên mỗi request.

Nếu có kid nhưng không tìm thấy key, validator có thể kích hoạt một lần làm mới JWKS theo chính sách. Sau khi refresh vẫn không có key phù hợp, token phải bị từ chối.

## 3. Mô hình JWKS cache

Một triển khai thường lưu cache theo issuer hoặc JWKS URI đã được cấu hình tin cậy.

~~~mermaid
flowchart TD
    A["JWT request"] --> B["Resolve trusted issuer"]
    B --> C["Read JWKS snapshot for issuer"]
    C --> D{"Matching kid and compatible key?"}
    D -->|Yes| E["Verify signature"]
    D -->|No| F["Bounded JWKS refresh"]
    F --> G["Validate and atomically replace snapshot"]
    G --> H{"Key now available?"}
    H -->|Yes| E
    H -->|No| I["Reject invalid token"]
~~~

Một cache entry có thể lưu:

| Trường | Mục đích |
|---|---|
| Trusted issuer ID | Phân biệt trust context. |
| JWKS URI đã cấu hình | Nguồn key được phép truy cập. |
| JWK Set snapshot | Tập public key đã parse và kiểm tra. |
| fetched_at | Thời điểm tải thành công gần nhất. |
| fresh_until | Thời điểm hết freshness theo policy/cache metadata. |
| ETag | Validator dùng cho conditional request. |
| Last-Modified | Validator thời gian nếu server cung cấp. |
| last_success_at | Thời điểm refresh thành công gần nhất. |
| last_error | Trạng thái lỗi gần nhất để monitoring. |
| generation | Version nội bộ để quan sát và đồng bộ cache. |
| revoked_kids hoặc deny state | Trạng thái key bị chặn khẩn cấp nếu hệ thống có cơ chế riêng. |

Cache nên lưu một snapshot nhất quán. Khi nhận JWKS mới, parse và validate toàn bộ response trước; chỉ thay snapshot khi response đạt. Không cập nhật từng key một cách dở dang khiến request đồng thời nhìn thấy tập key nửa cũ nửa mới.

Việc thay snapshot nên có tính atomic: request đang chạy có thể hoàn tất với snapshot hợp lệ đã đọc; request tiếp theo dùng snapshot mới. Với key bị compromise, cần một cơ chế deny/invalidation có ưu tiên cao hơn cache snapshot thông thường.

## 4. Cache theo issuer, không theo kid đơn lẻ

kid không phải định danh toàn cục. Ví dụ:

- Issuer A có key current.
- Issuer B cũng có key current.
- Cả hai có thể dùng cùng thuật toán nhưng public key khác nhau.

Nếu cache chỉ có key current, public key của issuer A có thể bị sử dụng nhầm khi xác minh token issuer B.

Cache identity nên gắn với ít nhất:

- Trust configuration/issuer.
- JWKS endpoint đã được cấu hình cho issuer.
- kid.
- Các ràng buộc key/profile cần thiết như kty, alg, use hoặc key_ops.

Ví dụ key cache nội bộ:

~~~text
cache_key = (
    trusted_issuer_id,
    kid,
    expected_algorithm,
    key_usage
)
~~~

Đây là mô hình minh họa; có thể cache toàn bộ JWK Set theo issuer rồi lookup kid bên trong snapshot. Dù chọn cách nào, không để key lookup bỏ qua issuer boundary.

Không dùng iss chưa xác minh để tự động tải JWKS từ URL bất kỳ. Với nhiều issuer, ánh xạ issuer đến metadata/JWKS URI phải đến từ allowlist hoặc trust configuration được quản lý. Việc đọc iss từ token có thể hỗ trợ chọn candidate trong danh sách đã tin cậy, nhưng không được tạo trust mới.

## 5. HTTP caching và freshness của JWKS

JWKS thường được phân phối qua HTTP(S), do đó cache có thể tận dụng các cơ chế HTTP caching.

### 5.1. Cache-Control và max-age

Issuer có thể trả response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/jwk-set+json
Cache-Control: public, max-age=300
ETag: "jwks-v42"

{ "keys": [ ... ] }
~~~

max-age=300 cho biết response có freshness lifetime 300 giây theo HTTP caching semantics. Đây là ví dụ minh họa, không phải TTL khuyến nghị cho mọi JWKS.

Một số directive cần hiểu:

| Directive | Ý nghĩa thực tế đối với JWKS cache |
|---|---|
| max-age=N | Response có thể được dùng như fresh trong khoảng thời gian N giây, tùy các điều kiện cache HTTP. |
| s-maxage=N | Freshness cho shared cache; có thể ghi đè max-age trong ngữ cảnh shared cache. |
| no-cache | Có thể lưu response nhưng phải revalidate trước khi tái sử dụng theo HTTP semantics. |
| no-store | Không lưu response vào cache HTTP. |
| must-revalidate | Khi response stale, cache phải revalidate trước khi reuse theo quy tắc HTTP caching. |
| private | Shared cache không được lưu response theo directive này; private cache vẫn có thể lưu nếu các điều kiện khác cho phép. |

Không diễn giải no-cache thành “không được lưu”. Cũng không diễn giải no-store thành “được lưu vô hạn trong cache ứng dụng riêng”. Nếu ứng dụng xây dựng cache riêng bên ngoài HTTP cache, phải có policy riêng và tôn trọng hợp đồng phân phối key của issuer.

### 5.2. ETag và conditional request

Khi đã lưu JWKS cùng ETag, resource server có thể revalidate:

~~~http
GET /.well-known/jwks.json HTTP/1.1
Host: identity.example.test
If-None-Match: "jwks-v42"
~~~

Nếu JWKS không thay đổi, server có thể trả:

~~~http
HTTP/1.1 304 Not Modified
Cache-Control: public, max-age=300
ETag: "jwks-v42"
~~~

304 Not Modified không mang một JWKS body mới. Cache giữ body đã lưu và cập nhật metadata freshness theo response. Nếu nội dung đã thay đổi, server trả 200 OK với JWK Set mới và validator mới.

ETag giúp giảm băng thông và chi phí truyền dữ liệu. Nó không làm cho key cache được cập nhật tức thời: resource server chỉ biết có thay đổi khi thực hiện revalidation hoặc nhận một tín hiệu invalidation khác.

### 5.3. Last-Modified và If-Modified-Since

Nếu endpoint không cung cấp ETag, cache có thể sử dụng:

~~~http
If-Modified-Since: Mon, 16 Nov 2026 10:00:00 GMT
~~~

Issuer có thể trả 304 Not Modified nếu representation không thay đổi kể từ thời điểm đó. ETag thường là validator chính xác hơn cho representation; nếu cả ETag và Last-Modified tồn tại, phải tuân theo thứ tự ưu tiên của HTTP caching semantics.

### 5.4. Fresh, stale và revalidation

Cần phân biệt ba trạng thái:

- **Fresh:** cache còn trong freshness lifetime và có thể được sử dụng theo policy.
- **Stale:** freshness lifetime đã hết; cache cần revalidate hoặc xử lý theo chính sách stale được cho phép.
- **Invalidated:** entry bị xóa hoặc đánh dấu không còn được phép dùng, ví dụ key bị compromise.

Stale không đồng nghĩa key chắc chắn sai. Nó chỉ có nghĩa cache không còn bằng chứng freshness theo metadata hiện tại. Ngược lại, fresh cũng không bảo đảm key chưa bị compromise nếu sự cố vừa xảy ra mà cache chưa được invalidated.

Độ mới của JWKS và trạng thái thu hồi key là hai khái niệm khác nhau. TTL điều khiển tần suất cập nhật bình thường; emergency invalidation xử lý sự cố cần hiệu lực nhanh.

## 6. Chọn TTL theo rủi ro và mục tiêu vận hành

Không chọn TTL chỉ để giảm số lần gọi JWKS endpoint. Cần xác định:

- Access token có lifetime bao lâu?
- Issuer xoay key theo lịch nào?
- Mức độ khẩn cấp khi signing key bị compromise?
- Có kênh push invalidation hoặc denylist kid không?
- Có bao nhiêu region/cluster cần cập nhật?
- Hệ thống có chấp nhận sử dụng stale cache khi endpoint lỗi không?
- Thời gian tối đa từ lúc thay đổi JWKS đến khi tất cả validator nhận biết là bao lâu?

### 6.1. TTL ngắn

Ưu điểm:

- Validator nhận key mới và key bị loại bỏ nhanh hơn trong điều kiện refresh thành công.
- Thời gian tồn tại của snapshot cũ được giới hạn.
- Có thể phù hợp với môi trường có yêu cầu xoay khóa thường xuyên.

Nhược điểm:

- Tăng số request đến issuer.
- Tăng phụ thuộc mạng và latency refresh.
- JWKS endpoint có thể trở thành bottleneck.
- Nhiều validator có thể refresh đồng loạt nếu không có jitter/single-flight.

### 6.2. TTL dài

Ưu điểm:

- Giảm tải JWKS endpoint.
- Tăng khả năng tiếp tục xác minh token khi endpoint tạm thời không khả dụng.
- Giảm network round-trip trong luồng request bình thường.

Nhược điểm:

- Key mới có thể chưa được biết đến khi issuer bắt đầu ký bằng key đó.
- Key bị xóa ở origin vẫn có thể còn trong cache.
- Key compromise có thể cần thời gian dài hơn để được phản ánh nếu không có invalidation riêng.

### 6.3. Tính toán freshness budget

Có thể định nghĩa một ngân sách độ mới:

~~~text
maximum_key_change_visibility =
    cache_freshness_lifetime
    + refresh_schedule_delay
    + network_retry_delay
    + propagation_delay
~~~

Công thức này là mô hình vận hành để ước lượng độ trễ trong hệ thống, không phải công thức chuẩn hóa của RFC. Với refresh đồng bộ ngay khi stale, refresh_schedule_delay có thể gần bằng 0; với refresh nền theo chu kỳ, độ trễ có thể lớn hơn.

Cần phân biệt:

- **Key addition delay:** thời gian để validator biết public key mới.
- **Key removal delay:** thời gian để validator ngừng tin key đã bị loại khỏi JWKS.
- **Emergency revocation delay:** thời gian để mọi validator ngừng chấp nhận key bị compromise.

TTL bình thường chỉ là một thành phần của các khoảng thời gian này. Emergency revocation cần cơ chế nhanh hơn nếu threat model yêu cầu.

### 6.4. Ví dụ thiết kế policy

| Môi trường | Refresh policy minh họa | Stale behavior |
|---|---|---|
| Development | TTL ngắn để kiểm tra rotation nhanh | Dễ quan sát lỗi, không dùng production key. |
| Staging | TTL gần với production để diễn tập | Có thể mô phỏng endpoint outage và invalidation. |
| Production API thông thường | Tuân theo HTTP freshness, có refresh nền và unknown-kid refresh được giới hạn | Chỉ dùng stale theo policy rõ ràng, có maximum staleness. |
| API có dữ liệu hoặc giao dịch rủi ro cao | Freshness và invalidation được giám sát chặt; có deny state cho key bị thu hồi | Fail closed khi không thể xác định trust state cần thiết. |

Các giá trị cụ thể phải được chọn theo SLO, token lifetime và khả năng của issuer. Không sao chép TTL ví dụ thành một hằng số toàn hệ thống.

## 7. Unknown kid: refresh đúng cách và chống DoS

### 7.1. Vì sao cần refresh khi gặp kid lạ?

Một issuer có thể xoay signing key và bắt đầu phát hành JWT bằng kid mới. Validator đang giữ JWKS cũ sẽ không tìm thấy key đó.

Một chiến lược phổ biến:

1. Tra cứu kid trong snapshot hiện tại.
2. Nếu không có, kiểm tra có refresh đang diễn ra cho issuer hay không.
3. Nếu không, khởi tạo một lần refresh có giới hạn.
4. Validate response và thay snapshot atomically.
5. Tra cứu lại đúng một lần.
6. Nếu vẫn không có key phù hợp, từ chối token.

Không được lặp refresh vô hạn cho đến khi tìm thấy key.

### 7.2. Rủi ro random-kid flood

Kẻ tấn công có thể gửi nhiều JWT giả, mỗi token dùng một kid ngẫu nhiên:

~~~json
{
  "alg": "RS256",
  "kid": "random-kid-7f19a2"
}
~~~

Nếu mỗi kid lạ tạo một HTTP request đến JWKS endpoint, attacker có thể:

- Làm cạn connection pool hoặc thread.
- Tăng tải DNS/TLS/HTTP.
- Tạo request storm đến issuer.
- Làm tăng latency cho request hợp lệ.
- Gây áp lực lên parser và key construction.

### 7.3. Các biện pháp chống refresh amplification

- **Single-flight:** chỉ một refresh cho mỗi issuer được thực hiện tại một thời điểm; các request khác chờ kết quả hoặc nhận kết quả cache hiện tại theo policy.
- **Cooldown:** sau một lần refresh, đặt khoảng thời gian tối thiểu trước lần refresh tiếp theo do unknown kid.
- **Rate limit:** giới hạn refresh theo issuer và theo instance/cluster.
- **Negative caching:** ghi nhớ ngắn hạn kid không tồn tại sau khi đã refresh thành công; TTL phải ngắn và được xóa khi JWKS thay đổi.
- **Bounded retry:** mỗi request chỉ kích hoạt số lần refresh hữu hạn.
- **Timeout:** đặt timeout cho DNS, kết nối và response.
- **Backoff:** tăng khoảng chờ khi endpoint lỗi, có jitter để tránh đồng loạt retry.
- **Circuit breaker:** tạm ngăn request refresh khi endpoint liên tục lỗi, rồi thử lại theo lịch có kiểm soát.
- **Response size limit:** giới hạn kích thước JWKS và số key được chấp nhận.
- **Concurrency limit:** giới hạn số lần parse/build key đồng thời.
- **Metric/alert:** theo dõi unknown-kid rate và refresh rate để nhận biết tấn công hoặc lỗi rotation.

Negative cache chỉ được dùng để giảm lặp lại lookup thất bại trong một khoảng ngắn. Khi JWKS được cập nhật hoặc có invalidation, negative entry liên quan phải được xóa để key mới không bị từ chối kéo dài.

### 7.4. Không tin jku hoặc x5u tùy ý

Một JWT header có thể chứa jku hoặc x5u theo một số profile. Nếu validator tự động tải URL từ header chưa xác minh, attacker có thể khiến server truy cập endpoint không được phép, bao gồm địa chỉ nội bộ.

Đối với JWKS của issuer, dùng URI lấy từ trust configuration hoặc metadata discovery đã được xác minh. Nếu profile cho phép header tham chiếu key, phải có policy allowlist và kiểm tra chặt chẽ; không dùng URL do token tùy ý cung cấp để mở rộng trust.

## 8. Refresh nền, refresh theo request và phối hợp giữa nhiều instance

### 8.1. Refresh theo request

Validator chỉ tải JWKS khi cache hết freshness hoặc gặp kid chưa biết.

Ưu điểm:

- Ít refresh nếu traffic thấp.
- Không cần scheduler riêng.
- Có thể đơn giản với hệ thống nhỏ.

Nhược điểm:

- Request đầu tiên sau khi cache stale chịu latency.
- Nhiều request đồng thời có thể cùng phát hiện stale.
- Unknown kid flood cần được kiểm soát.

### 8.2. Refresh nền

Một tác vụ nền refresh JWKS trước khi hết freshness:

- Request bình thường chủ yếu dùng cache.
- Latency của refresh được tách khỏi request path.
- Có thể phát hiện key mới trước khi issuer bắt đầu ký bằng key đó nếu rotation được prepublish đúng cách.

Cần có cơ chế single-flight, jitter và giới hạn retry. Không để tất cả instance refresh đúng cùng một thời điểm.

### 8.3. Kết hợp hai chiến lược

Một thiết kế thường dùng:

- Refresh nền trước thời điểm hết freshness.
- Revalidate theo ETag khi phù hợp.
- Unknown kid kích hoạt refresh có cooldown.
- Nếu refresh đang chạy, request dùng kết quả sau khi hoàn tất hoặc bị từ chối theo latency budget.
- Khi endpoint lỗi, áp dụng stale policy đã định nghĩa.
- Khi nhận emergency invalidation, bỏ qua cache bình thường và chặn key ngay theo khả năng propagation.

### 8.4. Multi-instance và multi-region

Giả sử có 50 validator trên 3 region. Nếu mỗi instance tự refresh độc lập, một lần key rotation có thể tạo nhiều request giống nhau.

Có thể dùng:

- Cache local trong từng instance để lookup nhanh.
- Shared cache hoặc distribution layer để giảm duplicate fetch.
- Single-flight trong mỗi instance và phối hợp refresh ở cấp cluster.
- Event invalidation để thông báo JWKS generation mới.
- Jitter cho lịch refresh.
- Readiness/health signal để phát hiện instance chưa nhận key state mới.

Shared cache làm giảm tải nhưng thêm một trust boundary và failure mode. Nếu dùng shared cache, cần xác thực nguồn ghi, phân quyền truy cập, version hóa entry và ngăn một issuer ghi đè key của issuer khác.

Không có một cơ chế push invalidation phổ quát được JWKS tự định nghĩa. Event bus, cache purge API hoặc control plane là cơ chế triển khai riêng; phải có retry, acknowledgment và monitoring.

## 9. Quy trình xoay khóa bình thường

Một key rotation được lên kế hoạch nên tránh khoảng thời gian issuer đã ký bằng key mới nhưng validator chưa biết public key mới.

~~~mermaid
sequenceDiagram
    participant I as Issuer
    participant J as JWKS Endpoint
    participant V as Resource Server

    I->>J: Publish public key K2
    J-->>V: JWKS contains K1 and K2
    Note over V: Validators refresh and cache K2
    I->>I: Wait for propagation/freshness window
    I->>I: Start signing new tokens with K2
    I-->>V: JWT with kid=K2
    V->>V: Select K2 and verify signature
    Note over I,V: Keep K1 published while K1 tokens remain valid
    I->>J: Remove K1 after retirement window
    J-->>V: JWKS without K1 on revalidation
~~~

### 9.1. Các bước rotation

1. Tạo key pair mới trong hệ thống quản lý khóa/HSM phù hợp.
2. Bảo vệ private key và cấp một kid mới, duy nhất trong issuer.
3. Publish public JWK mới cùng public key đang hoạt động.
4. Chờ thời gian đủ để validator nhận JWKS mới theo freshness/propagation budget.
5. Bắt đầu ký token mới bằng private key mới.
6. Tiếp tục publish public key cũ trong thời gian token ký bằng key đó còn có thể hợp lệ.
7. Sau khi token cũ hết hạn và qua clock-skew/retirement margin, loại public key cũ khỏi JWKS.
8. Theo dõi các validator đã nhận snapshot mới và không còn phụ thuộc key cũ.

### 9.2. Tính thời gian giữ key cũ

Một cách tính thận trọng:

~~~text
old_public_key_retention >=
    time_from_last_old_key_issuance_to_maximum_token_expiry
    + accepted_clock_skew
    + operational_retirement_margin
~~~

Khoảng thời gian này được tính từ lần cuối issuer ký token bằng key cũ đến lúc token cuối cùng có thể hết hạn, không tính đơn giản từ ngày tạo key hoặc ngày bắt đầu rotation.

Nếu resource server có thể tiếp tục dùng stale JWKS sau khi key bị xóa, cần xét thêm maximum stale window. Tuy nhiên, không nên dựa vào việc xóa key khỏi JWKS để thu hồi ngay token còn hạn; removal chỉ có hiệu lực khi validator cập nhật trust state.

### 9.3. Prepublish key mới

Nếu issuer bắt đầu ký bằng K2 ngay khi publish K2, validator có cache JWKS cũ vẫn không tìm được kid mới.

Cách an toàn là publish K2 trước, chờ các validator có cơ hội nhận key, rồi mới chuyển signing traffic. Thời gian chờ cần tính theo cache freshness tối đa, lịch refresh, propagation delay và retry budget thực tế.

Unknown-kid refresh là lớp dự phòng, không nên là cơ chế duy nhất cho rotation bình thường.

## 10. Thu hồi khẩn cấp khi signing key bị compromise

Đây là trường hợp JWKS freshness ảnh hưởng trực tiếp đến khả năng chấp nhận token giả mạo.

Nếu private signing key bị lộ, attacker có thể ký JWT mới bằng key đó. Resource server đang cache public key tương ứng vẫn có thể xác minh chữ ký giả cho đến khi key bị chặn trong trust state của nó.

### 10.1. Vì sao chỉ xóa key khỏi JWKS chưa đủ?

Giả sử JWKS origin đã xóa K1 nhưng validator còn cache JWKS chứa K1 với max-age chưa hết. Validator có thể tiếp tục dùng K1 mà không revalidate.

Vì vậy:

- Thay đổi tại origin không đồng nghĩa mọi cache đã thay đổi.
- Cache-Control không phải kênh push invalidation.
- ETag chỉ giúp phát hiện thay đổi khi validator revalidate.
- Giảm TTL sau khi phát hiện sự cố không làm cache cũ tự động hết hạn ngay.
- Một số cache hoặc validator có stale fallback riêng có thể giữ key lâu hơn dự kiến.

### 10.2. Emergency response

1. Xác nhận kid, issuer và key bị compromise qua quy trình incident.
2. Ngừng sử dụng private key bị ảnh hưởng để ký token mới.
3. Cô lập/disable key trong KMS/HSM hoặc hệ thống quản lý khóa.
4. Loại public key khỏi JWKS của issuer.
5. Phát tín hiệu khẩn cấp đến mọi validator để invalidate snapshot và chặn kid bị compromise.
6. Purge shared cache và local cache theo control plane nếu có.
7. Nếu có denylist key ID, cập nhật trạng thái deny trước khi tiếp tục xử lý token.
8. Xác minh từng region/cluster đã áp dụng trạng thái mới.
9. Phát hành key mới và publish public key qua trust channel.
10. Điều tra token giả mạo và hành động được thực hiện trong khoảng thời gian key có thể bị lộ.

Emergency deny state phải được kiểm tra trước khi dùng public key đã cache. Nếu chỉ dựa vào TTL thông thường, thời gian containment có thể vượt yêu cầu.

### 10.3. Phân biệt xóa key bình thường và revoke key khẩn cấp

| Tình huống | Cách xử lý |
|---|---|
| Planned rotation | Giữ key cũ trong thời gian token cũ còn hợp lệ, sau đó remove theo lịch. |
| Key hết nhiệm vụ nhưng không compromise | Retirement theo policy và thời gian lưu key. |
| Private key bị lộ | Chặn ngay kid, invalidate cache và không chấp nhận chữ ký mới bằng key đó. |
| JWKS endpoint lỗi nhưng key không có dấu hiệu compromise | Áp dụng bounded stale policy nếu threat model cho phép. |
| JWKS endpoint lỗi trong khi key compromise đang diễn ra | Fail closed đối với key/issuer state bị ảnh hưởng nếu không thể xác minh trạng thái thu hồi. |

### 10.4. Không nhầm key removal với token revocation

Loại public key khỏi JWKS có thể làm mọi token ký bằng key đó không còn xác minh được sau khi validator cập nhật. Đây là biện pháp phạm vi rộng: tất cả token được ký bằng key có thể bị từ chối, kể cả token hợp lệ không liên quan đến attacker.

Nếu chỉ một token hoặc một session bị lộ, revoke theo jti, session, grant hoặc cơ chế token status có thể phù hợp hơn. Nếu private signing key bị compromise, revoke key là cần thiết vì attacker có thể tạo token mới với bất kỳ sub hoặc scope nào mà profile cho phép.

## 11. JWKS endpoint lỗi hoặc không khả dụng

Một lỗi mạng không tự động có nghĩa public key đã cache trở nên không hợp lệ. Nhưng cũng không thể tiếp tục dùng cache stale vô thời hạn.

### 11.1. Phân loại tình huống

| Tình huống | Hướng xử lý |
|---|---|
| Cache còn fresh, key đã biết, không có emergency deny | Có thể xác minh bằng snapshot fresh theo policy. |
| Cache stale, endpoint trả 304 | Giữ body, cập nhật freshness metadata theo HTTP semantics. |
| Cache stale, endpoint trả 200 hợp lệ | Validate và thay snapshot. |
| Cache stale, endpoint timeout/5xx | Áp dụng maximum stale window nếu được policy cho phép; cảnh báo. |
| Unknown kid, endpoint lỗi | Không có public key để xác minh; từ chối token. |
| Response JWKS sai JSON hoặc key không hợp lệ | Không thay snapshot bằng response lỗi; ghi alert. |
| Key đã bị emergency deny | Từ chối key dù nó còn trong cache. |
| Cache hết maximum staleness | Không tiếp tục tin key chỉ vì trước đó từng tải thành công. |

### 11.2. Stale-if-error và rủi ro

HTTP caching có extension như stale-if-error được mô tả trong RFC 5861. Nó cho phép cache trả response stale trong một khoảng thời gian khi origin gặp lỗi nếu policy cho phép.

Với JWKS, stale-if-error là quyết định bảo mật, không chỉ là tối ưu hiệu năng:

- Giúp hệ thống tiếp tục xác minh token đã biết khi issuer tạm thời lỗi.
- Có thể kéo dài thời gian tin key đã bị loại khỏi origin.
- Không thể phát hiện key mới chỉ từ cache stale.
- Không được vượt qua emergency deny state.
- Phải có maximum staleness, monitoring và owner chịu trách nhiệm.

Nếu hệ thống không thể biết key có bị thu hồi khẩn cấp hay không trong lúc endpoint mất kết nối, cần đánh giá fail-open/fail-closed theo mức nhạy cảm của API. Không có một lựa chọn đúng cho mọi hệ thống; policy phải ghi rõ phạm vi endpoint và thời gian tối đa.

### 11.3. Fail closed với unknown key

Nếu token có kid chưa từng được tin cậy và JWKS endpoint không khả dụng, không thể xác minh chữ ký bằng key chưa biết. Không được bỏ qua signature verification hoặc chấp nhận token vì issuer tạm thời lỗi.

Nếu token dùng key đã biết trong snapshot fresh, có thể xử lý theo cache policy. Đây là tình huống khác với unknown key.

## 12. Kiểm tra JWK trước khi đưa vào cache

Không phải mọi JWK trong response đều được phép sử dụng để xác minh token.

Cần kiểm tra:

- JSON hợp lệ và có keys là array.
- kid đúng kiểu nếu profile yêu cầu.
- kty thuộc loại key được hỗ trợ.
- Key material có cấu trúc hợp lệ.
- Key đủ độ dài hoặc curve phù hợp.
- use nếu có phải tương thích với signing/verification.
- key_ops nếu có phải cho phép verify.
- alg nếu có phải phù hợp với algorithm allowlist.
- Không chấp nhận private key member trong JWKS public nếu profile/hệ thống không cho phép.
- Không chọn key chỉ vì kid khớp nhưng kty/alg/usage không phù hợp.
- Xử lý kid trùng lặp hoặc candidate mơ hồ theo policy; không tùy tiện chọn key đầu tiên.
- Giới hạn số lượng key, kích thước response và độ phức tạp parse.

### 12.1. Algorithm allowlist

JWT header alg là dữ liệu chưa xác minh. Validator phải áp dụng allowlist thuật toán theo trust configuration và profile.

Không lấy alg từ token làm lệnh cho phép bất kỳ thuật toán nào. Không dùng một RSA public key như HMAC secret hoặc ngược lại. Nếu JWK có alg, phải kiểm tra nó phù hợp với thuật toán được phép.

### 12.2. use và key_ops

Ví dụ một JWK có:

~~~json
{
  "kty": "RSA",
  "kid": "signing-2026-02",
  "use": "sig",
  "key_ops": ["verify"],
  "alg": "RS256",
  "n": "<base64url-modulus>",
  "e": "AQAB"
}
~~~

use: sig và key_ops: ["verify"] phù hợp với public key dùng để xác minh chữ ký. Nếu key được đánh dấu cho encryption hoặc không cho phép verify, validator không nên dùng nó để xác minh JWS. RFC 7517 khuyến nghị không dùng đồng thời use và key_ops; nếu cả hai cùng xuất hiện, thông tin chúng biểu đạt phải nhất quán.

Không phải mọi JWK đều bắt buộc có tất cả các member này. Việc thiếu member phải được xử lý theo RFC, profile và policy của hệ thống; các member được khai báo phải nhất quán với nhau.

## 13. Không trộn JWKS cache với JWT validation-result cache

Hai cache có mục đích khác nhau:

| Cache | Lưu gì? | Rủi ro chính |
|---|---|---|
| JWKS/key cache | Public key và metadata key của issuer | Key mới chưa được thấy hoặc key bị thu hồi vẫn còn được tin. |
| JWT validation-result cache | Kết quả xác minh một token cụ thể | Token đã bị revoke hoặc policy thay đổi nhưng kết quả allow cũ vẫn được dùng. |
| Authorization decision cache | Kết quả quyền trên subject/action/object | Membership, ACL, role hoặc object state thay đổi nhưng quyết định cũ chưa bị invalidated. |

Một public key vẫn hợp lệ không có nghĩa mọi token ký bằng key đó đều còn hợp lệ. Token có thể hết hạn, bị revoke theo jti hoặc session, sai audience, sai scope hoặc vi phạm policy.

Nếu cache kết quả validation:

- Không cache token chưa xác minh.
- Key cache phải được phân biệt theo issuer/profile và fingerprint an toàn của token.
- TTL không được vượt quá thời điểm token hết hạn hoặc thời điểm policy cho phép.
- Phải xét revocation state nếu hệ thống hỗ trợ revoke trước exp.
- Không dùng cache hit để bỏ qua emergency key deny state.
- Không log raw token làm cache key hoặc metric label.

JWKS cache chỉ cung cấp key material. Validator vẫn phải áp dụng đầy đủ các kiểm tra token ở mỗi request hoặc theo cơ chế validation-result cache có giới hạn rõ ràng.

## 14. Pseudocode cho JWKS cache có kiểm soát

Mã giả sau mô tả logic khái niệm, không phải API của thư viện cụ thể.

~~~text
function verify_jwt(token, trusted_issuer_config):
    parsed = parse_untrusted_jwt(token)

    issuer_config = trusted_issuer_config.lookup_candidate(parsed.untrusted_issuer)
    if issuer_config is null:
        reject("invalid_token")

    if not issuer_config.algorithm_allowlist.contains(parsed.header.alg):
        reject("invalid_token")

    kid = parsed.header.kid
    if issuer_config.profile.requires_kid and kid is missing:
        reject("invalid_token")

    if kid is present and emergency_denylist.contains(issuer_config.id, kid):
        reject("invalid_token")

    snapshot = jwks_cache.get(issuer_config.id)
    refreshed_this_request = false

    if snapshot is missing or snapshot is stale:
        refresh_if_due_single_flight(issuer_config)
        snapshot = jwks_cache.get(issuer_config.id)
        refreshed_this_request = true

    key = select_compatible_key(snapshot, kid, parsed.header.alg)

    if key is missing and not refreshed_this_request:
        refresh_once_with_rate_limit(issuer_config)
        snapshot = jwks_cache.get(issuer_config.id)

        if kid is present and emergency_denylist.contains(issuer_config.id, kid):
            reject("invalid_token")

        key = select_compatible_key(snapshot, kid, parsed.header.alg)

    if key is missing:
        reject("invalid_token")

    if kid is present and emergency_denylist.contains(issuer_config.id, kid):
        reject("invalid_token")

    verify_signature(parsed, key)
    validate_issuer_audience_type_and_claims(parsed, issuer_config.profile)

    return verified_principal(parsed.claims)


function refresh_jwks(issuer_config):
    response = conditional_get(
        uri = issuer_config.trusted_jwks_uri,
        etag = issuer_cache[issuer_config.id].etag,
        last_modified = issuer_cache[issuer_config.id].last_modified,
        timeout = issuer_config.fetch_timeout
    )

    if response.status == 304:
        update_freshness_metadata(issuer_cache[issuer_config.id], response)
        return

    if response.status != 200:
        record_refresh_failure(response.status)
        apply_bounded_stale_policy()
        return

    candidate = parse_and_validate_jwks(response.body, issuer_config)

    if candidate is invalid:
        record_invalid_jwks_response()
        keep_current_snapshot_unless_emergency_policy_requires_block()
        return

    atomic_replace_snapshot(issuer_config.id, candidate, response.cache_metadata)
~~~

Các yêu cầu quan trọng:

- trusted_jwks_uri đến từ cấu hình tin cậy, không phải URL tùy ý trong JWT.
- select_compatible_key kiểm tra cả kid, issuer context, key type, usage và algorithm.
- Unknown kid chỉ kích hoạt refresh hữu hạn.
- Emergency denylist được kiểm tra ngay cả khi cache còn fresh.
- Response lỗi không được làm hỏng snapshot hợp lệ đang dùng.
- Không dùng stale snapshot nếu key đã bị emergency deny.
- Sau khi xác minh chữ ký vẫn phải xác minh issuer, audience, thời hạn, token type và required claims.

## 15. Monitoring và chỉ số vận hành

Không thể quản lý độ mới JWKS nếu chỉ quan sát HTTP status của endpoint. Cần theo dõi cả cache và kết quả xác minh.

| Metric | Ý nghĩa |
|---|---|
| JWKS cache hit ratio | Tỷ lệ lookup dùng snapshot hiện có. |
| JWKS cache age | Tuổi snapshot đang được sử dụng. |
| Time since last successful refresh | Thời gian từ lần refresh thành công gần nhất. |
| JWKS refresh count | Số lần refresh theo issuer. |
| JWKS refresh latency | Độ trễ fetch/parse/validate. |
| JWKS refresh failure rate | Tỷ lệ timeout, 5xx, invalid response. |
| HTTP 304 ratio | Tỷ lệ revalidation không có thay đổi nội dung. |
| Unknown kid rate | Tần suất token tham chiếu key chưa biết. |
| Refreshes per unknown kid | Khả năng refresh amplification. |
| Stale-key use count | Số lần dùng cache stale theo policy. |
| Emergency deny propagation time | Thời gian từ khi phát lệnh chặn đến khi mọi validator áp dụng. |
| Key selection failure | Không tìm được candidate key phù hợp. |
| Signature verification failure | Chữ ký không hợp lệ sau khi chọn key. |

Nên phân tách metric theo issuer đã được định danh an toàn, environment và region. Không dùng raw JWT, sub nhạy cảm hoặc giá trị token làm metric label.

### 15.1. Alert nên có

- JWKS snapshot vượt maximum age.
- Refresh liên tục thất bại.
- Unknown kid tăng đột biến.
- Một issuer phát hành key mới nhưng một số region chưa nhận.
- Cache generation khác nhau quá lâu giữa các instance.
- Emergency deny chưa được xác nhận bởi tất cả validator.
- JWKS response chứa key sai schema hoặc key không phù hợp policy.
- Một issuer có số key tăng bất thường.
- Resource server liên tục dùng stale key.

### 15.2. Log an toàn

Có thể ghi:

~~~json
{
  "event": "jwks_refresh",
  "issuer_id": "identity-primary",
  "cache_generation": 42,
  "http_status": 200,
  "key_count": 3,
  "duration_ms": 24,
  "result": "updated"
}
~~~

Có thể ghi kid nếu policy cho phép và nó không được xem là dữ liệu nhạy cảm trong hệ thống; không ghi raw JWT hoặc private key material. Với incident, lưu key fingerprint hoặc JWK thumbprint theo RFC 7638 có thể giúp đối chiếu key mà không cần lưu private key.

## 16. Ma trận kiểm thử JWKS cache và freshness

| Nhóm | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Cold start | Cache rỗng, token dùng key hiện tại | Tải JWKS từ URI tin cậy, xác minh thành công nếu key hợp lệ. |
| Warm cache | Nhiều request cùng issuer/key | Tái sử dụng snapshot, không fetch mỗi request. |
| Issuer isolation | Hai issuer cùng kid nhưng public key khác nhau | Không dùng chéo key giữa issuer. |
| Kid match | kid tồn tại và key phù hợp algorithm | Chọn đúng key và xác minh chữ ký. |
| Kid missing | Profile yêu cầu kid nhưng header thiếu | Từ chối. |
| Kid missing optional | Profile không yêu cầu kid, chỉ có một candidate hợp lệ | Xử lý theo policy đã định nghĩa. |
| Unknown kid | kid mới vừa được prepublish | Refresh có giới hạn, sau đó chọn key mới. |
| Unknown kid absent | Refresh thành công nhưng kid không có | Từ chối token; không refresh lặp vô hạn. |
| Random-kid flood | Nhiều token có kid ngẫu nhiên | Single-flight, cooldown/rate limit; không tạo request storm. |
| Freshness boundary | Cache vừa hết max-age | Revalidate/refresh theo HTTP policy. |
| ETag unchanged | Endpoint trả 304 | Giữ body, cập nhật freshness metadata. |
| ETag changed | Endpoint trả 200 với JWKS mới | Validate và atomically thay snapshot. |
| Last-Modified | Conditional request nhận 304 | Cập nhật freshness theo response. |
| JWKS timeout | Endpoint không phản hồi | Áp dụng bounded stale policy hoặc từ chối theo policy. |
| JWKS 5xx | Origin lỗi tạm thời | Backoff/circuit breaker, không retry storm. |
| Invalid JSON | Response không parse được | Không thay snapshot bằng dữ liệu lỗi; alert. |
| Invalid JWK | Key thiếu material hoặc sai type | Không đưa key vào cache. |
| Algorithm mismatch | alg của JWT không phù hợp key/profile | Từ chối. |
| Wrong key usage | JWK chỉ dùng cho encryption | Không dùng để verify chữ ký. |
| Planned rotation | K2 được publish trước khi ký | Validator nhận K2 trước khi token K2 xuất hiện. |
| Old key overlap | K1 còn token hợp lệ | K1 tiếp tục được publish đến hết retirement window. |
| Old key retirement | K1 đã hết thời gian token hợp lệ | Remove K1 và xác nhận validator revalidate. |
| Emergency compromise | K1 bị compromise khi cache còn fresh | Emergency deny/purge khiến mọi validator từ chối K1. |
| Multi-region | Region nhận update lệch thời gian | Monitoring phát hiện propagation gap. |
| Concurrent refresh | Nhiều request cùng thấy unknown kid | Một refresh cho mỗi issuer trong cửa sổ single-flight. |
| Header URL injection | JWT chứa jku trỏ đến host không tin cậy | Không truy cập URL ngoài trust configuration. |
| Duplicate/ambiguous kid | JWKS có candidate trùng hoặc không rõ | Từ chối hoặc xử lý theo quy tắc profile; không chọn tùy tiện. |
| Emergency deny precedence | Key còn trong snapshot nhưng đã bị deny | Từ chối key trước bước xác minh chữ ký. |

## 17. Runbook vận hành

### 17.1. Khi phát hành key mới

1. Xác nhận key pair mới được tạo và private key được bảo vệ.
2. Đặt kid mới, không tái sử dụng định danh đang còn trong vòng đời.
3. Publish public key vào JWKS.
4. Xác minh endpoint trả key đúng và cache metadata phù hợp.
5. Theo dõi refresh generation trên tất cả region.
6. Chờ propagation/freshness budget.
7. Chuyển issuer sang ký bằng key mới.
8. Theo dõi unknown kid, signature failure và refresh rate.
9. Giữ public key cũ cho đến khi token cũ hết hạn theo policy.
10. Remove key cũ và xác nhận validator nhận snapshot mới.

### 17.2. Khi JWKS endpoint không khả dụng

1. Kiểm tra DNS, TLS, network, status code và latency.
2. Xác định cache age của từng issuer/region.
3. Xác định request đang dùng key đã biết hay unknown kid.
4. Áp dụng maximum stale policy đã được phê duyệt.
5. Không cho unknown key đi qua khi không thể xác minh.
6. Giám sát refresh retry, circuit breaker và ảnh hưởng đến API.
7. Khôi phục endpoint, revalidate cache và xác nhận generation đồng nhất.
8. Ghi nhận khoảng thời gian sử dụng stale key và các ngoại lệ.

### 17.3. Khi signing key bị compromise

1. Kích hoạt incident response và xác định issuer/kid.
2. Dừng ký bằng private key bị ảnh hưởng.
3. Disable key trong hệ thống quản lý khóa.
4. Publish JWKS không còn key bị compromise.
5. Phát emergency deny/invalidation đến tất cả validator.
6. Purge local/shared cache và xác nhận deny state đã có hiệu lực.
7. Phát hành key mới và phân phối public key.
8. Kiểm thử token giả ký bằng key cũ bị từ chối ở mọi region.
9. Điều tra token và hành động có thể bị giả mạo.
10. Đóng sự cố chỉ sau khi propagation và monitoring xác nhận trạng thái an toàn.

## 18. Checklist thiết kế và production readiness

- [ ] JWKS URI được lấy từ trust configuration hoặc metadata được tin cậy.
- [ ] Cache được partition theo issuer/trust domain.
- [ ] Không lookup public key chỉ theo kid toàn cục.
- [ ] kid được dùng như selector chưa xác minh, không phải bằng chứng trust.
- [ ] Key được kiểm tra kty, algorithm, use, key_ops và key material.
- [ ] Có algorithm allowlist độc lập với header alg.
- [ ] Snapshot được parse/validate hoàn chỉnh trước khi atomic replace.
- [ ] HTTP Cache-Control, ETag và conditional revalidation được xử lý đúng.
- [ ] Có TTL/freshness budget và maximum stale window được tài liệu hóa.
- [ ] Unknown kid chỉ gây refresh hữu hạn.
- [ ] Có single-flight, cooldown, rate limit, timeout, backoff và circuit breaker.
- [ ] Có negative cache ngắn hạn và invalidation khi JWKS thay đổi.
- [ ] Có giới hạn response size, key count và concurrency.
- [ ] Rotation prepublishes public key trước khi bắt đầu ký bằng key mới.
- [ ] Public key cũ được giữ đến khi token cũ không còn hợp lệ theo policy.
- [ ] Emergency key deny có ưu tiên cao hơn cache freshness.
- [ ] Có cơ chế purge/invalidation và xác nhận propagation đa region.
- [ ] Stale-if-error được quyết định theo threat model, có giới hạn.
- [ ] Unknown kid không được chấp nhận khi không thể lấy key tin cậy.
- [ ] Không nhầm JWKS cache với token validation cache hoặc authorization cache.
- [ ] Có metric/alert cho cache age, refresh failure, unknown kid và propagation.
- [ ] Có runbook cho planned rotation, endpoint outage và key compromise.
- [ ] Có test cho issuer isolation, random-kid flood, ETag, rotation và emergency revoke.

## 19. Câu hỏi tự kiểm tra

1. JWKS khác một JWK đơn lẻ như thế nào?
2. kid giúp chọn public key ra sao và vì sao nó không phải bằng chứng trust?
3. Vì sao cache key phải gắn với issuer thay vì chỉ dùng kid?
4. Cache-Control: no-cache khác no-store như thế nào?
5. ETag và If-None-Match giảm chi phí refresh ra sao?
6. Vì sao 304 không có nghĩa cache phải xóa JWK Set body?
7. TTL dài có thể ảnh hưởng thế nào đến key rotation và emergency revocation?
8. Vì sao unknown kid có thể trở thành vector DoS?
9. Single-flight, cooldown và negative caching phối hợp ra sao?
10. Vì sao phải prepublish public key trước khi issuer bắt đầu ký bằng key mới?
11. Khi nào public key cũ có thể được remove trong planned rotation?
12. Vì sao xóa key khỏi JWKS origin không lập tức chặn validator đang cache key?
13. Emergency deny state khác cache freshness như thế nào?
14. Khi JWKS endpoint lỗi, điều kiện nào có thể cho phép dùng stale cache?
15. Vì sao unknown kid không thể được chấp nhận khi endpoint không khả dụng?
16. JWKS cache khác token validation-result cache ở điểm nào?
17. Cần quan sát những metric nào để biết các region đã nhận key state mới?
18. Cần làm gì để xác minh key bị compromise đã bị chặn trên mọi validator?

## 20. Tài liệu tham khảo

- [RFC 7517 – JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517.html): cấu trúc JWK/JWKS, kid, use, key_ops, alg và phân phối public key.
- [RFC 7515 – JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515.html): JOSE header và việc sử dụng kid như gợi ý chọn key.
- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): JWT Claims Set và quan hệ giữa token với các cơ chế xác minh.
- [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html): quản lý khóa, algorithm verification, trust và các yêu cầu xác minh an toàn.
- [RFC 9111 – HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html): freshness lifetime, cache validation, Cache-Control, ETag và conditional request.
- [RFC 5861 – HTTP Cache-Control Extensions for Stale Content](https://www.rfc-editor.org/rfc/rfc5861.html): stale-while-revalidate và stale-if-error.
- [RFC 7638 – JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638.html): tạo thumbprint để định danh JWK theo các member được quy định.
- [RFC 8414 – OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html): metadata discovery và jwks_uri của authorization server.
