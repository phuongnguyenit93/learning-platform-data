# kid không biết, JWKS lỗi và thay đổi khóa trong lúc có yêu cầu

## 1. Vì sao cần kiểm thử vòng đời khóa khi xác minh JWT?

Một resource server xác minh chữ ký JWT bằng khóa công khai do issuer công bố, thường thông qua JSON Web Key Set (JWKS). Trong token JWS, protected header có thể chứa kid (Key ID) để verifier chọn khóa tương ứng trong tập khóa của issuer.

Trong vận hành, tập khóa không cố định:

- Issuer thêm khóa mới khi chuẩn bị rotation.
- Issuer ngừng ký bằng khóa cũ nhưng vẫn giữ public key để xác minh token cũ.
- JWKS endpoint có thể timeout, trả lỗi HTTP, dữ liệu sai định dạng hoặc bị gián đoạn mạng.
- Verifier có thể đang giữ cache cũ khi token được ký bằng khóa mới.
- Nhiều request có thể cùng phát hiện kid lạ và đồng thời kích hoạt tải JWKS.
- Một khóa có thể bị lộ và cần vô hiệu hóa khẩn cấp trong khi request đang được xác minh.

Nếu xử lý sai, hệ thống có thể từ chối token hợp lệ trong lúc rotation, chấp nhận token đã ký bằng khóa bị thu hồi, tạo request storm tới JWKS endpoint hoặc vô tình tin một khóa do nguồn không đáng tin cung cấp.

Bài này tập trung vào ba nhóm tình huống: **không tìm thấy kid, không lấy/đọc được JWKS và thay đổi khóa trong lúc request đang chạy**. Mục tiêu là kiểm thử cả tính đúng đắn của quyết định xác minh lẫn khả năng chịu lỗi và khả năng chống DoS.

Bài thuộc chương **Kiểm thử bảo mật** của module **Security - JSON Web Token (JWT)**. Nội dung áp dụng chung cho JOSE/JWT và mọi nền tảng triển khai, không phụ thuộc Java hay framework.

## 2. Mô hình xác minh JWT bằng JWKS

### 2.1. JWKS là gì?

JWKS là một JSON Web Key Set, chứa một mảng các JWK. Mỗi JWK mô tả một khóa và các thuộc tính cần thiết để sử dụng khóa đó. Với JWT ký bất đối xứng, issuer thường công bố public key để resource server xác minh chữ ký.

Ví dụ JWKS rút gọn:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "rsa-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "<public-modulus>",
      "e": "AQAB"
    },
    {
      "kty": "EC",
      "kid": "ec-2026-02",
      "use": "sig",
      "alg": "ES256",
      "crv": "P-256",
      "x": "<public-x>",
      "y": "<public-y>"
    }
  ]
}
~~~

Đây là ví dụ cấu trúc minh họa. Giá trị khóa được lược bỏ; một JWKS công khai không được chứa private key material.

### 2.2. kid là gợi ý chọn khóa

kid nằm trong protected header của JWS và giúp verifier tìm JWK tương ứng. Nó là dữ liệu do token cung cấp, nên phải được xem là **untrusted input cho tới khi chữ ký được xác minh**.

Verifier không được tin kid như bằng chứng token do issuer phát hành, dùng kid để chọn thuật toán ngoài allowlist, ghép kid vào URL hoặc filesystem path, tải khóa từ URL do token tự khai báo hoặc chọn tùy tiện một khóa khác khi không tìm thấy kid.

kid chỉ giúp chọn ứng viên khóa. Verifier vẫn phải kiểm tra thuật toán, loại khóa, issuer, audience, thời hạn và chữ ký theo token profile.

### 2.3. Luồng xác minh cơ bản

~~~mermaid
flowchart TD
    A[Nhận JWT] --> B[Parse protected header có giới hạn]
    B --> C[Chọn issuer từ trust configuration]
    C --> D[Đọc JWKS cache của issuer]
    D --> E{Tìm được đúng một key phù hợp?}
    E -->|Có| F[Kiểm tra alg, kty, use, key_ops]
    E -->|Không| G[Refresh JWKS có kiểm soát]
    G --> H{Refresh thành công và key xuất hiện?}
    H -->|Có| F
    H -->|Không| I[Reject hoặc báo dependency unavailable]
    F --> J[Xác minh chữ ký]
    J --> K[Kiểm tra iss, aud, exp, nbf và token profile]
    K --> L[Authorization decision]
~~~

Thứ tự thực tế có thể khác tùy thư viện, nhưng không được đưa token vào bước authorization trước khi xác minh chữ ký và các điều kiện bắt buộc.

### 2.4. Trust configuration quyết định JWKS endpoint

Verifier phải biết issuer nào được tin cậy và JWKS URI nào thuộc issuer đó. URI có thể đến từ cấu hình tin cậy hoặc metadata discovery đã được xác minh theo issuer allowlist.

Không dùng iss chưa xác minh để tự động truy vấn metadata tùy ý. Không dùng jku hoặc x5u do token cung cấp làm nguồn khóa mặc định. Cách làm này có thể tạo SSRF hoặc khiến verifier tin khóa do attacker kiểm soát.

## 3. Chọn khóa an toàn từ JWKS

### 3.1. Không chỉ so sánh kid

Sau khi tìm JWK theo kid, verifier cần kiểm tra các thuộc tính phù hợp:

| Thuộc tính | Điều cần kiểm tra |
| --- | --- |
| kid | Khớp chính xác với key identifier theo policy |
| kty | Loại khóa được hỗ trợ cho thuật toán |
| use | Nếu có, phải phù hợp với chữ ký, thường là sig |
| key_ops | Nếu có, phải cho phép thao tác verify |
| alg | Nếu có, phải khớp thuật toán được cấu hình cho issuer/token profile |
| Curve/key size | Thuộc danh sách thuật toán và tham số được chấp nhận |
| Key material | Có đầy đủ tham số public hợp lệ; không chứa hoặc sử dụng private material |

Không phải mọi JWK đều phải có tất cả thuộc tính tùy chọn. Verifier cần áp dụng quy tắc rõ ràng cho thuộc tính vắng mặt, không suy đoán rộng hơn profile cho phép.

### 3.2. Một kid phải ánh xạ rõ ràng tới một khóa

Nếu cùng một JWKS có nhiều JWK cùng kid và đều có thể được chọn, kết quả trở nên mơ hồ. Không chọn khóa đầu tiên hoặc khóa cuối cùng theo thứ tự mảng.

Chính sách an toàn:

- Từ chối tập khóa có kid trùng gây mơ hồ.
- Không cập nhật cache từ JWKS không vượt qua validation.
- Ghi nhận sự kiện và cảnh báo issuer/operator.
- Không fallback sang khóa khác chỉ vì chữ ký với khóa đầu tiên thất bại.

Một kid có thể được dùng trong các issuer khác nhau nếu namespace được phân tách theo issuer, nhưng trong một issuer/key set, identifier phải đủ để lựa chọn rõ ràng.

### 3.3. Trường hợp token không có kid

kid không phải lúc nào cũng bắt buộc theo mọi dạng JWS. Cách xử lý phải theo token profile:

- Nếu profile yêu cầu kid, token thiếu kid phải bị từ chối.
- Nếu issuer chỉ có đúng một khóa tương thích và profile cho phép bỏ kid, verifier có thể chọn khóa duy nhất một cách không mơ hồ.
- Nếu có nhiều khóa phù hợp mà không có kid, không thử hàng loạt khóa tùy tiện trừ khi profile xác định rõ cách xử lý.

Không biến việc thiếu kid thành lý do để bỏ qua allowlist thuật toán hoặc các kiểm tra khác.

### 3.4. kid không quyết định thuật toán

Verifier phải có allowlist thuật toán độc lập với header token. Ví dụ, một issuer có thể chỉ được phép ký bằng RS256. Nếu token tự khai alg=HS256, việc kid tồn tại trong JWKS không làm thuật toán đó hợp lệ.

Không cho phép alg=none, không để xảy ra confusion giữa thuật toán đối xứng và bất đối xứng, và không tự động chấp nhận thuật toán chỉ vì JWK có trường alg tương ứng.

## 4. Khi nào kid được xem là không biết?

### 4.1. Unknown kid trong cache

Verifier đã có JWKS hợp lệ trong cache nhưng không tìm thấy kid của token. Có một số khả năng:

- Token giả mạo dùng kid ngẫu nhiên.
- Issuer vừa rotation và verifier chưa cập nhật JWKS.
- Token đến từ issuer khác với cấu hình verifier.
- Issuer phát hành token sai cấu hình hoặc dùng nhầm key ID.
- Cache chưa đồng bộ hoặc đang giữ một phiên bản cũ.

Không thể kết luận ngay rằng mọi unknown kid đều là tấn công hoặc mọi unknown kid đều do rotation. Cần refresh có kiểm soát rồi đưa ra quyết định.

### 4.2. Refresh một lần có giới hạn

Một luồng xử lý thường dùng:

1. Tìm kid trong JWKS cache hiện tại.
2. Nếu không thấy, yêu cầu refresh JWKS theo issuer đã tin cậy.
3. Chống nhiều request đồng thời bằng single-flight/coalescing.
4. Nếu refresh thành công, validate toàn bộ JWKS mới và thay cache nguyên tử.
5. Tìm lại kid trong snapshot mới.
6. Nếu vẫn không có khóa phù hợp, từ chối token.

Không lặp refresh vô hạn trong cùng một request. Một request chỉ nên có số lần tải lại hữu hạn, thường là một lần thử refresh do unknown kid, rồi kết thúc.

### 4.3. Unknown kid sau refresh thành công

Nếu JWKS endpoint trả dữ liệu hợp lệ, verifier cập nhật cache thành công nhưng kid vẫn không tồn tại, token không thể được xác minh bằng key set đáng tin cậy.

Kết quả là từ chối xác thực. Với API dùng Bearer token, response có thể biểu diễn lỗi invalid_token theo hợp đồng OAuth/resource server, thường là HTTP 401.

Không dùng khóa bất kỳ trong JWKS, chấp nhận chữ ký không xác minh được, bỏ qua chữ ký để tiếp tục kiểm tra claims hoặc tự tải khóa từ URL nằm trong token.

### 4.4. Không tìm thấy kid và không lấy được JWKS là hai trạng thái khác nhau

Nếu JWKS fetch thất bại, verifier chưa có bằng chứng rằng kid không tồn tại trong key set hiện hành. Đây là lỗi dependency hoặc trạng thái chưa xác định.

Nếu không có cached key phù hợp, hệ thống vẫn phải **fail closed**: không cấp quyền. Tuy nhiên, về vận hành có thể phân biệt:

- Token sai hoặc kid không tồn tại sau lần refresh thành công: lỗi xác thực, thường là 401.
- Không thể lấy JWKS và không có cached key phù hợp: dependency unavailable, có thể trả 503 hoặc lỗi tạm thời theo API contract.

Không trả 200 hoặc tiếp tục request khi chưa xác minh được chữ ký. Cũng không nên báo mọi lỗi JWKS thành 401 nếu điều đó che giấu sự cố hạ tầng và khiến client hiểu nhầm credential của họ chắc chắn sai.

## 5. Chống DoS qua unknown kid

### 5.1. Tấn công tạo request refresh liên tục

Attacker có thể gửi nhiều JWT với kid ngẫu nhiên. Nếu mỗi request khiến verifier tải JWKS, attacker có thể tạo request storm tới authorization server, làm cạn connection pool, tăng độ trễ xác minh token hợp lệ, tăng chi phí outbound network hoặc khiến dịch vụ phụ thuộc JWKS bị quá tải.

Đây là một dạng resource exhaustion thông qua key discovery.

### 5.2. Single-flight refresh

Nếu nhiều request cùng phát hiện cache thiếu key cho một issuer, chỉ nên có một lần refresh đang chạy; các request còn lại chờ kết quả hoặc dùng snapshot đã được cập nhật.

~~~text
Request A: unknown kid ----\
Request B: unknown kid -----+--> one JWKS refresh per issuer
Request C: unknown kid ----/             |
                                         v
                                  atomic cache update
                                         |
                       +-----------------+----------------+
                       v                 v                v
                  retry lookup      retry lookup     retry lookup
~~~

Single-flight cần có phạm vi phù hợp với cache/issuer. Một mutex trong một process không bảo vệ được nhiều instance nếu mỗi instance có refresh coordinator riêng.

### 5.3. Cooldown và rate limit

Kết hợp các biện pháp:

- Cooldown refresh theo issuer/JWKS endpoint.
- Rate limit request xác minh từ nguồn không tin cậy.
- Backoff có jitter khi JWKS endpoint lỗi.
- Giới hạn số lần refresh trong một khoảng thời gian.
- Timeout kết nối và timeout đọc ngắn, có giới hạn.
- Giới hạn kích thước response và số JWK được xử lý.
- Giới hạn độ dài/định dạng kid.
- Theo dõi số unknown kid và số refresh thực tế.

Cooldown nên dựa trên issuer/key set, không tạo một lịch refresh riêng cho từng kid tùy ý. Nếu lưu negative cache cho từng kid, phải giới hạn kích thước và thời gian lưu để tránh attacker tạo vô hạn entry.

### 5.4. Negative caching

Sau khi refresh thành công mà kid vẫn không tồn tại, verifier có thể cache kết quả “không có key” trong một khoảng ngắn để tránh refresh lại ngay lập tức.

Negative cache cần TTL ngắn và có giới hạn, gắn với issuer và phiên bản JWKS cụ thể, được vô hiệu hóa khi JWKS thay đổi, có giới hạn dung lượng/eviction và không lưu chuỗi kid tùy ý vô hạn.

Nếu issuer vừa thêm key mới, negative cache cũ không được ngăn verifier nhìn thấy key sau khi JWKS đã được cập nhật.

### 5.5. Không biến kid thành URL hoặc path

kid là selector trong key set. Không ghép nó vào URL để tải khóa, file path, tên bảng hoặc câu truy vấn không parameterize, hay cache key không có namespace/giới hạn.

Việc ghép dữ liệu header vào URL có thể tạo SSRF; ghép vào path có thể tạo path traversal; dùng làm cache key không giới hạn có thể tạo memory exhaustion.

### 5.6. Giới hạn tải và validate JWKS response

Khi tải JWKS:

- Chỉ kết nối tới URI thuộc trust configuration.
- Dùng TLS và xác minh chứng thư.
- Giới hạn redirect theo policy; không cho redirect sang host không được phép.
- Giới hạn thời gian và kích thước response.
- Parse JSON an toàn và từ chối cấu trúc không hợp lệ.
- Kiểm tra keys là mảng và từng JWK phù hợp policy.
- Không thay cache tốt bằng response rỗng, sai định dạng hoặc mơ hồ.

Một response lỗi không được làm mất cached key set hợp lệ chỉ vì refresh thất bại.

## 6. JWKS cache và xử lý khi endpoint lỗi

### 6.1. Vì sao cần cache?

Nếu mỗi request đều gọi JWKS endpoint, hệ thống phụ thuộc mạng vào authorization server cho mọi lần xác minh. Cache giúp giảm latency, giảm tải cho issuer, tăng khả năng hoạt động khi JWKS endpoint tạm thời gián đoạn và giảm tác động của lỗi mạng ngắn hạn.

Nhưng cache tạo ra độ trễ giữa lúc issuer thay đổi key set và lúc verifier nhìn thấy thay đổi.

### 6.2. Cache theo issuer và JWKS URI

Cache phải được namespace theo issuer/trust configuration. Không dùng chung key set giữa hai issuer chỉ vì kid trùng nhau.

Cache entry có thể chứa issuer đã xác minh, JWKS URI từ trust configuration, JWK set đã validate, thời điểm fetch và hết hạn cache, ETag/Last-Modified nếu hỗ trợ HTTP conditional request, phiên bản/generation của snapshot và thời điểm refresh gần nhất.

Không lưu raw JWT trong cache JWKS.

### 6.3. Tôn trọng cache header nhưng phải có giới hạn policy

JWKS endpoint có thể trả Cache-Control, max-age, ETag hoặc Last-Modified. Verifier có thể dùng các header này để tối ưu cache và conditional request.

Local security policy nên đặt TTL tối đa, TTL tối thiểu hợp lý, thời gian stale tối đa khi endpoint lỗi, backoff/retry policy và cách xử lý 304 Not Modified.

Không để response header do upstream cấu hình khiến verifier giữ key vô thời hạn.

### 6.4. JWKS timeout hoặc network failure

Các lỗi có thể gặp: DNS resolution thất bại, TCP/TLS handshake timeout, read timeout, connection reset hoặc network partition.

Nếu cache có key phù hợp và key vẫn nằm trong giới hạn stale được policy cho phép, verifier có thể tiếp tục xác minh bằng cached key. Nếu không có key phù hợp, không thể xác minh và phải từ chối request mà không cấp quyền.

### 6.5. JWKS trả 5xx, 429 hoặc lỗi HTTP khác

| Kết quả | Cách xử lý gợi ý |
| --- | --- |
| 5xx | Giữ last-known-good cache trong giới hạn policy; backoff |
| 429 | Tôn trọng Retry-After nếu hợp lệ; không tạo retry storm |
| 401/403 | Kiểm tra cấu hình client/network; không coi response là JWKS hợp lệ |
| 404 | Kiểm tra issuer/JWKS URI và cấu hình discovery |
| Redirect | Chỉ theo redirect nếu policy cho phép và đích vẫn nằm trong trust boundary |
| 200 nhưng JSON sai | Không thay cache tốt; ghi nhận lỗi dữ liệu và cảnh báo |
| 200 nhưng key set rỗng/bất thường | Xem là thay đổi nguy hiểm hoặc lỗi cấu hình theo policy; không xóa key tốt một cách mù quáng |

Không mặc định rằng mọi mã 4xx/5xx đều có cùng ý nghĩa. Cần quan sát status, endpoint, thời điểm và trạng thái cache.

### 6.6. Stale-if-error có giới hạn

Last-known-good key set có thể giúp hệ thống tiếp tục hoạt động khi JWKS endpoint tạm lỗi. Nhưng dùng key quá cũ có rủi ro nếu issuer đã thu hồi một key vì compromise.

Policy cần xác định stale key được dùng tối đa bao lâu, chỉ dùng cho key đã biết hay cả kid mới, có dùng khi endpoint lỗi nhưng cache key còn hạn không, có emergency denylist/push invalidation không và stale-if-error có bị tắt ngay khi key compromise không.

Không dùng stale cache để xác minh một kid chưa từng có trong cache. Không dùng stale-if-error vô thời hạn.

## 7. Cập nhật JWKS an toàn

### 7.1. Không cập nhật cache từng phần

Giả sử JWKS mới có nhiều key. Nếu verifier cập nhật cache từng JWK, request đồng thời có thể nhìn thấy một key set nửa cũ nửa mới.

Quy trình an toàn hơn:

1. Tải toàn bộ response.
2. Parse và validate toàn bộ key set.
3. Kiểm tra duplicate kid, loại khóa, thuật toán và policy.
4. Tạo một snapshot bất biến mới.
5. Thay con trỏ cache bằng snapshot mới trong một thao tác atomic.
6. Request đang chạy dùng snapshot nhất quán mà nó đã lấy; request mới dùng snapshot mới.

Nếu validation thất bại, giữ nguyên last-known-good snapshot và ghi nhận lỗi.

### 7.2. Không xóa cache tốt trước khi có cache mới hợp lệ

Trình tự nguy hiểm:

~~~text
delete old JWKS cache
fetch new JWKS
parse response
~~~

Nếu fetch hoặc parse thất bại, verifier mất cả key set cũ vốn còn có thể dùng để xác minh token hợp lệ.

Trình tự an toàn hơn:

~~~text
fetch new JWKS
validate complete response
build immutable snapshot
atomic replace old snapshot
~~~

### 7.3. Cache generation

Có thể gắn generation/version cho mỗi snapshot:

~~~text
JWKS snapshot generation 41:
  keys = [K1]

JWKS snapshot generation 42:
  keys = [K1, K2]

JWKS snapshot generation 43:
  keys = [K2]
~~~

Generation giúp log và kiểm thử xác định request đã dùng snapshot nào. Đây là metadata nội bộ; không thay thế kid, chữ ký hoặc trust validation.

### 7.4. Nhiều instance và cache phân tán

Nếu mỗi instance giữ cache riêng, rotation có thể lan truyền không đồng đều. Một instance đã nhận K2, instance khác vẫn chỉ có K1.

Có thể dùng TTL có giới hạn và refresh-on-unknown-kid, shared cache hoặc key distribution nội bộ đã xác thực, pub/sub invalidation khi key set đổi, version/generation để quan sát độ trễ cập nhật, health check và metric cho cache age.

Shared cache cũng là một trust boundary. Phải bảo vệ nguồn ghi, tính toàn vẹn, namespace theo issuer và chống cache poisoning.

## 8. Planned key rotation

### 8.1. Vì sao cần overlap?

Khi issuer thay khóa ký, token đã phát hành bằng khóa cũ có thể vẫn còn hiệu lực. Nếu xóa public key cũ ngay khi bắt đầu ký bằng key mới, verifier chưa cập nhật JWKS sẽ từ chối token mới; verifier đã cập nhật cũng sẽ từ chối token cũ còn hạn.

Vì vậy, planned rotation thường có một giai đoạn overlap: JWKS công bố cả public key cũ và mới trong khi issuer chuyển việc ký sang key mới.

### 8.2. Trình tự rotation tham khảo

~~~mermaid
flowchart LR
    A[Generate K2] --> B[Publish K1 + K2]
    B --> C[Wait for cache propagation]
    C --> D[Start signing with K2]
    D --> E[Stop signing with K1]
    E --> F[Wait until K1 tokens expire + skew]
    F --> G[Remove K1 from JWKS]
~~~

Trình tự:

1. Tạo key pair mới trong hệ thống quản lý khóa/HSM phù hợp.
2. Công bố public key K2 trong JWKS cùng với K1.
3. Chờ thời gian đủ để verifier/CDN/cache nhìn thấy K2.
4. Bắt đầu ký token mới bằng K2 và kid mới.
5. Ngừng phát hành token mới bằng K1.
6. Giữ K1 trong JWKS tới khi token cuối cùng ký bằng K1 hết hạn, cộng clock skew và biên an toàn vận hành.
7. Gỡ K1 khỏi JWKS sau khi không còn token hợp lệ cần nó.

Thời gian chờ cần tính đến cache TTL, propagation delay, CDN và các verifier ít hoạt động chỉ refresh khi gặp kid lạ.

### 8.3. Không tái sử dụng kid cho key material khác

Không dùng lại kid cũ cho public key mới. Nếu cùng kid nhưng key material thay đổi, verifier có thể giữ cache cũ và không biết cần refresh; log/audit cũng khó phân biệt hai khóa.

Tạo kid mới cho mỗi key material mới. kid nên ổn định trong vòng đời của key và duy nhất trong phạm vi issuer/key set theo policy.

### 8.4. Cả hai key phải đúng policy

Trong giai đoạn overlap, verifier vẫn phải kiểm tra từng key theo kty và tham số public, use/key_ops nếu có, alg và allowlist của issuer, key size/curve được phê duyệt và kid không mơ hồ.

Overlap không phải lý do để nới lỏng kiểm tra chữ ký.

## 9. Thay đổi khóa trong lúc request đang chạy

### 9.1. Tình huống race

Một request có thể bắt đầu xác minh trong khi background refresh đang thay snapshot JWKS:

~~~text
Request A                  JWKS Cache                 Refresher
   |                           |                          |
   |-- read snapshot G41 ----->|                          |
   |                           |<-- fetch JWKS G42 -------|
   |                           |<-- validate G42 ---------|
   |                           |<-- atomic replace -------|
   |-- verify using G41 ------>|                          |
   |                           |                          |
Request B                     |                          |
   |-- read snapshot G42 ----->|                          |
   |-- verify using G42 ------>|                          |
~~~

Request A và B có thể dùng snapshot khác nhau. Điều đó không tự động là lỗi nếu G41 vẫn hợp lệ theo rotation policy. Điều quan trọng là mỗi request dùng một snapshot nhất quán, không đọc một nửa key set cũ và một nửa key set mới.

### 9.2. Snapshot bất biến cho mỗi request

Khi bắt đầu xác minh, request nên lấy một tham chiếu tới snapshot JWKS hiện tại. Snapshot không bị mutate tại chỗ. Nếu cache được thay, request đang chạy vẫn nhìn thấy snapshot cũ hoàn chỉnh; request tiếp theo thấy snapshot mới.

Điều này tránh collection thay đổi trong lúc đang duyệt, key bị xóa giữa bước lookup và verify, request thấy duplicate/thiếu key tạm thời do cập nhật từng phần và kết quả phụ thuộc thứ tự thread.

### 9.3. Unknown kid trong lúc refresh đang chạy

Nếu request không tìm thấy kid trong G41 và một refresh khác đang tải G42:

1. Request tham gia/chờ cùng refresh operation nếu còn trong thời gian chờ hợp lý.
2. Sau khi refresh hoàn tất, đọc snapshot G42.
3. Tìm lại kid đúng một lần.
4. Nếu có đúng một key phù hợp, tiếp tục verify.
5. Nếu không có hoặc refresh lỗi, từ chối theo trạng thái xác minh.

Không để mỗi request tạo một fetch riêng. Không lặp vòng refresh nếu G42 vẫn không có key.

### 9.4. Key bị xóa trong lúc request đang xác minh

Trong planned rotation, request đã lấy snapshot chứa K1 có thể hoàn tất xác minh token K1 trong khi snapshot mới đã bỏ K1. Điều này có thể chấp nhận nếu K1 vẫn trong overlap window và token chưa hết hạn.

Trong emergency revocation do key compromise, việc chờ request dùng snapshot cũ hoàn tất có thể không chấp nhận được. Khi đó cần một cơ chế thu hồi khẩn cấp có thể được kiểm tra tại thời điểm quyết định authorization, ví dụ denylist theo kid hoặc key thumbprint, revocation generation/epoch, cache invalidation có xác nhận, introspection hoặc trạng thái online cho token/issuer cần kiểm soát tức thì, hoặc hủy request chưa commit khi key bị đánh dấu compromised.

Chỉ xóa key khỏi JWKS origin không bảo đảm mọi verifier đã xóa cache.

### 9.5. Chọn điểm tuyến tính hóa cho quyết định

Hệ thống cần xác định thời điểm nào được xem là điểm quyết định xác minh: lúc request lấy snapshot, lúc chữ ký được xác minh, lúc authorization được quyết định hay lúc thao tác nghiệp vụ được commit.

Với rotation thông thường, snapshot tại lúc bắt đầu verify thường đủ nếu overlap được thiết kế đúng. Với emergency revocation, policy có thể yêu cầu kiểm tra trạng thái key thêm một lần trước khi cho phép thao tác nhạy cảm commit.

Không thể bảo đảm thu hồi tức thì chỉ bằng một cache JWKS phân tán có độ trễ. Nếu yêu cầu tức thì, cần trạng thái thu hồi có consistency và propagation tương ứng.

## 10. Emergency key rotation khi private key bị lộ

### 10.1. Khác planned rotation

Planned rotation giữ key cũ để xác minh token cũ còn hạn. Emergency rotation do compromise có mục tiêu vô hiệu hóa key bị lộ càng nhanh càng tốt.

Không áp dụng overlap bình thường một cách máy móc cho key đã bị compromise. Token do attacker ký bằng private key bị lộ có thể trông hợp lệ về chữ ký.

### 10.2. Quy trình phản ứng

1. Dừng ngay việc ký token mới bằng key bị compromise.
2. Tạo key pair thay thế trong hệ thống quản lý khóa an toàn.
3. Cập nhật JWKS để công bố key mới và loại bỏ hoặc đánh dấu key bị compromise theo incident policy.
4. Phân phối invalidation tới verifier/cache/CDN.
5. Cập nhật denylist/revocation state để từ chối kid hoặc key thumbprint bị compromise.
6. Đánh giá token đã phát hành trong thời gian key có thể bị lộ.
7. Thu hồi session/refresh token hoặc yêu cầu xác thực lại nếu cần.
8. Theo dõi verifier còn dùng cache cũ và xác nhận chúng đã áp dụng trạng thái khẩn cấp.

### 10.3. Vì sao chỉ xóa key khỏi JWKS chưa đủ?

Verifier có thể đang giữ JWKS cũ trong memory cache, dùng shared cache chưa invalidated, mất kết nối với JWKS origin và dùng stale-if-error, có cache ở CDN/proxy hoặc chỉ refresh khi kid lạ nên không biết key cũ đã bị xóa.

Do đó emergency rotation cần kênh thu hồi riêng hoặc policy TTL/cache đủ ngắn để đáp ứng mục tiêu sự cố. Nếu không có trạng thái thu hồi, token được ký bằng key compromise có thể tiếp tục được chấp nhận tại verifier giữ cache cũ.

### 10.4. Không dùng stale-if-error cho key đã compromise

Khi nhận được tín hiệu đáng tin cậy rằng key bị compromise, verifier phải bỏ qua cơ chế stale-if-error đối với key đó. Availability không được phép khiến một key đã được xác định nguy hiểm tiếp tục được tin.

Nếu không thể truy cập revocation state trong khi yêu cầu cần vô hiệu hóa ngay, policy phải fail closed cho issuer/key bị ảnh hưởng.

## 11. Nhiều issuer và rủi ro chọn sai JWKS

### 11.1. Không dùng kid toàn cục

Hai issuer khác nhau có thể cùng dùng kid=key-1. Verifier phải namespace key theo issuer/trust domain:

~~~text
issuer A:
  kid key-1 -> public key A1

issuer B:
  kid key-1 -> public key B1
~~~

Không tìm khóa chỉ bằng kid trong một cache toàn cục.

### 11.2. Không tin issuer chưa xác minh để tải khóa tùy ý

Trong token chưa xác minh, iss cũng là dữ liệu chưa tin cậy. Với nhiều issuer, verifier phải ánh xạ issuer được phép vào cấu hình tin cậy đã biết trước.

Không lấy iss bất kỳ trong token rồi nối vào URL discovery để fetch metadata/JWKS. Điều này có thể biến verifier thành SSRF proxy hoặc làm nó tải khóa từ attacker.

### 11.3. Bỏ qua jku/x5u không được cấu hình

Header JWS có thể có jku hoặc x5u trong một số profile. Không tự động tải URL này chỉ vì token yêu cầu. Chỉ chấp nhận nguồn khóa được cấu hình và tin cậy theo hợp đồng issuer.

Nếu profile có dùng URL trong token, phải có allowlist và xác minh ràng buộc chặt chẽ; không cho phép token tùy ý quyết định network destination.

## 12. Xử lý response JWKS sai hoặc nguy hiểm

### 12.1. JSON không hợp lệ

Kiểm thử các trường hợp:

- Body không phải JSON.
- Thiếu trường keys.
- keys không phải array.
- JWK thiếu key material bắt buộc.
- Kiểu dữ liệu sai hoặc trường lặp bất thường.
- Response quá lớn hoặc có quá nhiều key.
- Duplicate kid gây mơ hồ.

Không thay last-known-good cache bằng response không hợp lệ.

### 12.2. JWK không phù hợp

Kiểm thử kty không tương thích với thuật toán, use không phải sig khi policy yêu cầu chữ ký, key_ops không cho phép verify, alg không khớp allowlist, RSA modulus quá yếu theo policy, EC curve không nằm trong allowlist, JWK chỉ có private material hoặc có trường private key không được phép công bố.

JWK không hợp lệ không được trở thành key ứng viên chỉ vì kid khớp.

### 12.3. HTTP response và redirect

Kiểm thử redirect tới host khác, redirect loop, TLS certificate không hợp lệ, DNS trỏ tới địa chỉ nội bộ ngoài policy, response có content type/encoding bất thường, Cache-Control quá dài hoặc không hợp lệ và ETag/304 xử lý sai.

JWKS fetch là hoạt động outbound có trust boundary. Áp dụng egress policy và giới hạn redirect để tránh SSRF.

### 12.4. Không ghi private key ra log

Nếu JWKS response chứa private key material, coi đây là sự cố nghiêm trọng. Không ghi toàn bộ response vào log hoặc ticket. Bảo vệ evidence, hạn chế quyền truy cập, xác định nguồn rò rỉ và xử lý rotation theo incident policy.

## 13. Ma trận kiểm thử unknown kid

| ID | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| UK-01 | kid có trong cache, key hợp lệ | Verify thành công nếu claims khác hợp lệ |
| UK-02 | kid không có cache, JWKS mới có key | Refresh một lần, cập nhật cache, verify thành công |
| UK-03 | kid không có sau refresh thành công | Từ chối token, không fallback |
| UK-04 | N request cùng unknown kid | Một refresh operation dùng chung trong phạm vi coordinator |
| UK-05 | N request với nhiều kid ngẫu nhiên | Refresh bị giới hạn bởi cooldown/rate limit |
| UK-06 | kid quá dài hoặc ký tự bất thường | Reject an toàn, không tạo URL/path injection |
| UK-07 | kid trùng trong JWKS | Từ chối key set mơ hồ và giữ cache tốt |
| UK-08 | Token thiếu kid trong profile yêu cầu kid | Reject |
| UK-09 | Token thiếu kid nhưng chỉ có một key phù hợp và profile cho phép | Chọn duy nhất theo policy hoặc reject nếu profile yêu cầu |
| UK-10 | kid tồn tại nhưng alg sai | Reject |
| UK-11 | kid tồn tại nhưng kty/use/key_ops không phù hợp | Reject |
| UK-12 | kid tồn tại ở issuer B nhưng token issuer A | Không dùng key của issuer B |

## 14. Ma trận kiểm thử JWKS outage

| ID | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| JW-01 | JWKS timeout, cache có key phù hợp và còn trong stale policy | Có thể verify bằng last-known-good key |
| JW-02 | JWKS timeout, không có cache phù hợp | Fail closed; báo dependency unavailable theo API contract |
| JW-03 | JWKS trả 500, cache còn hạn | Không xóa cache; tiếp tục theo policy |
| JW-04 | JWKS trả 429 | Tôn trọng Retry-After hợp lệ và backoff |
| JW-05 | JWKS trả JSON sai | Không thay cache tốt; cảnh báo |
| JW-06 | JWKS trả mảng keys rỗng bất ngờ | Không xóa key tốt một cách mù quáng; xử lý theo policy |
| JW-07 | JWKS trả key set hợp lệ nhưng không có kid | Reject token sau refresh |
| JW-08 | JWKS outage kéo dài vượt stale limit | Không tiếp tục dùng stale key vô hạn |
| JW-09 | JWKS outage và key được đánh dấu compromised | Không dùng stale key bị thu hồi |
| JW-10 | Conditional request trả 304 | Giữ snapshot hiện tại và cập nhật cache metadata đúng |
| JW-11 | Redirect sang host không được phép | Từ chối fetch |
| JW-12 | TLS certificate không hợp lệ | Từ chối kết nối; không hạ cấp sang HTTP |

## 15. Ma trận kiểm thử planned rotation

| ID | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| KR-01 | JWKS công bố K1 và K2 trước khi issuer dùng K2 | Verifier có thể nhận biết cả hai key |
| KR-02 | Token mới ký K2 sau khi K2 đã được công bố | Verify thành công |
| KR-03 | Token cũ ký K1 trong overlap và chưa hết hạn | Verify thành công |
| KR-04 | Token K1 đã hết hạn | Reject dù K1 còn trong JWKS |
| KR-05 | K1 bị gỡ sau khi token K1 cuối cùng hết hạn và skew | Token K2 tiếp tục verify; token K1 bị reject |
| KR-06 | Verifier cache chưa thấy K2, token K2 đến | Refresh có kiểm soát, sau đó verify nếu JWKS có K2 |
| KR-07 | Verifier cache đã có K2, token K2 đến | Không cần fetch mỗi request |
| KR-08 | JWKS cập nhật nhưng kid cũ được tái sử dụng cho key khác | Reject hoặc cảnh báo theo policy; không coi là rotation bình thường |
| KR-09 | CDN/instance cập nhật chậm | Đo propagation; không chấp nhận token sai chữ ký |
| KR-10 | Old key bị gỡ quá sớm | Test phải phát hiện token cũ hợp lệ bị từ chối ngoài kế hoạch |

## 16. Ma trận kiểm thử race khi request đang chạy

### 16.1. Snapshot và atomic update

| ID | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| RC-01 | Request A giữ snapshot G1, cache đổi sang G2 | A dùng G1 nhất quán; request mới dùng G2 |
| RC-02 | Refresh thay key set khi request đang lookup | Không thấy collection nửa cũ nửa mới |
| RC-03 | N request unknown kid cùng lúc | Chỉ một refresh theo single-flight |
| RC-04 | Refresh thất bại trong lúc nhiều request chờ | Không cấp quyền; giữ last-known-good theo policy |
| RC-05 | Refresh thành công nhưng kid vẫn không tồn tại | Các request chờ đều reject sau một lần lookup lại |
| RC-06 | Hai refresh response đến sai thứ tự | Không để response cũ ghi đè snapshot mới hơn |
| RC-07 | Hai instance nhận generation khác nhau | Quan sát được độ lệch; quyết định theo policy nhất quán |

### 16.2. Emergency revocation

| ID | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| ER-01 | K1 bị đánh dấu compromised khi cache còn K1 | Request mới không được chấp nhận bằng K1 |
| ER-02 | Request đang verify bằng snapshot có K1 | Áp dụng điểm kiểm tra revocation đã định nghĩa trước authorization/commit |
| ER-03 | JWKS origin đã xóa K1 nhưng instance còn cache cũ | Revocation channel/denylist vẫn từ chối K1 |
| ER-04 | JWKS outage sau khi K1 bị compromise | Không stale-if-error cho K1 |
| ER-05 | Token K2 hợp lệ sau emergency rotation | Verify thành công khi K2 được tin cậy |
| ER-06 | Request dùng kid K1 nhưng chữ ký bằng key khác | Reject; không thử fallback tùy tiện |

## 17. Thiết kế test harness và fault injection

### 17.1. Tạo issuer/JWKS giả lập trong môi trường test

Test harness nên có issuer test với key pair K1, K2 và K3; JWKS endpoint có thể đổi nội dung theo kịch bản; khả năng trả 200, 304, 429, 500, timeout và JSON lỗi; bộ ký token có thể chọn kid và thuật toán được phép/không được phép; verifier chạy với cache TTL, cooldown và stale policy có thể cấu hình; đồng hồ giả lập hoặc khả năng tạo token với iat/exp khác nhau; công cụ tạo request song song và trì hoãn từng bước.

Không dùng private key production trong test. Key fixture phải là key test và không được phát hành ra môi trường thật.

### 17.2. Điều khiển thời gian và thứ tự

Để tái hiện race:

1. Cho request A đọc snapshot G1 rồi pause trước verify.
2. Cập nhật JWKS từ G1 sang G2.
3. Cho refresher validate và atomic replace.
4. Tiếp tục request A.
5. Gửi request B sau update.
6. So sánh generation và kết quả xác minh.

Kiểm thử cần điều khiển thứ tự thay vì dựa vào sleep ngẫu nhiên. Có thể dùng barrier, latch hoặc fault injection tương đương trong test harness.

### 17.3. Kiểm thử tải unknown kid

Gửi nhiều request có kid khác nhau và đo số lần gọi JWKS, số request đang chờ refresh, CPU/memory của verifier, latency của token hợp lệ trong cùng thời gian, số negative-cache entries và số lần refresh bị cooldown/rate-limit.

Kết quả đạt là attacker không thể làm số outbound JWKS request tăng tuyến tính theo số token giả.

### 17.4. Kiểm thử nhiều issuer

Tạo hai issuer test cùng dùng kid=shared-id nhưng có key khác nhau. Token issuer A phải chỉ được xác minh bằng JWKS của A; token issuer B chỉ bằng JWKS của B.

Thử iss, jku và x5u giả mạo để xác nhận verifier không tải metadata/JWKS từ host không nằm trong trust configuration.

## 18. Quan sát và logging khi có lỗi JWKS

### 18.1. Metrics nên có

- JWKS fetch count và latency theo issuer.
- JWKS fetch error theo nhóm DNS/TLS/timeout/HTTP/parse.
- Cache age và cache generation.
- Unknown kid count.
- Unknown kid refresh count.
- Refresh coalescing/single-flight count.
- Negative-cache hit count.
- Signature verification failure theo nhóm nguyên nhân.
- Số key bị đánh dấu revoked/compromised.
- Propagation delay giữa issuer và verifier instances.

Không gắn metric label trực tiếp với kid tùy ý không giới hạn vì attacker có thể tạo cardinality explosion. Có thể ghi kid đã giới hạn độ dài trong log bảo mật khi cần, nhưng metric nên dùng nhóm trạng thái hoặc issuer đã chuẩn hóa.

### 18.2. Log an toàn

Có thể ghi issuer đã cấu hình, kid đã giới hạn, generation, cache age, kết quả refresh, nhóm lỗi, correlation ID và quyết định cuối cùng.

Không ghi raw JWT, Authorization header, private key material, toàn bộ response chứa dữ liệu nhạy cảm hoặc URL tùy ý do token cung cấp.

Không phản hồi cho client chi tiết nội bộ như hostname JWKS, đường dẫn mạng, key material hoặc stack trace. Dùng error code ổn định và log chi tiết ở server.

### 18.3. Cảnh báo vận hành

Nên cảnh báo khi unknown kid tăng đột biến, JWKS fetch liên tục thất bại, cache age vượt ngưỡng, JWKS có duplicate kid hoặc cấu trúc bất thường, một key bị đánh dấu compromised, các instance có generation chênh lệch lâu bất thường hoặc verifier tiếp tục dùng stale key quá giới hạn.

## 19. Quy trình xử lý lỗi theo quyết định

### 19.1. Bảng quyết định

| Trạng thái | Có key phù hợp trong cache? | Refresh | Quyết định |
| --- | --- | --- | --- |
| kid đã biết, cache trong policy | Có | Không cần | Verify bằng key phù hợp |
| kid đã biết, cache stale nhưng endpoint lỗi | Có | Đã thử hoặc đang lỗi | Chỉ dùng nếu stale policy cho phép và key chưa bị revoke |
| kid không biết, refresh thành công, key xuất hiện | Sau refresh có | Một lần | Verify bằng snapshot mới |
| kid không biết, refresh thành công, key không xuất hiện | Không | Thành công | Reject token |
| kid không biết, refresh lỗi, không có key | Không | Thất bại | Fail closed; dependency unavailable |
| key bị compromise | Có thể có trong cache cũ | Có thể lỗi | Deny theo revocation state; không stale fallback |
| JWKS response không hợp lệ | Có thể có cache tốt | Thất bại validation | Giữ cache tốt; không dùng response mới |

### 19.2. Pseudocode tham khảo

~~~text
function verifyJwt(token, trustedIssuer):
    header = parseProtectedHeaderWithLimits(token)
    require header.alg in trustedIssuer.allowedAlgorithms

    issuerConfig = trustedIssuer.configuration
    require issuerConfig is explicitly trusted

    snapshot = jwksCache.getSnapshot(issuerConfig)
    key = selectUniqueCompatibleKey(snapshot, header.kid, header.alg)

    if key is not found:
        refreshResult = refreshCoordinator.refreshOnce(issuerConfig)

        if refreshResult is unavailable:
            key = selectUniqueCompatibleKey(
                jwksCache.lastKnownGood(issuerConfig),
                header.kid,
                header.alg
            )
            if key is not found or key is stale beyond policy:
                return TEMPORARY_UNAVAILABLE
        else:
            snapshot = jwksCache.getSnapshot(issuerConfig)
            key = selectUniqueCompatibleKey(snapshot, header.kid, header.alg)

    require key is unique and compatible
    require key is not revoked or compromised
    require verifySignature(token, key, header.alg)
    require validateIssuerAudienceTimeAndTokenProfile(token)

    return AUTHENTICATED
~~~

Pseudocode minh họa luồng, không phải thư viện xác minh hoàn chỉnh. Trạng thái TEMPORARY_UNAVAILABLE không được chuyển thành allow. Khi refresh thành công nhưng kid không tồn tại, kết quả phải là invalid token; khi refresh lỗi và không có key dùng được, đó là lỗi dependency.

### 19.3. Lưu ý về key revocation

Kiểm tra key không bị revoked phải đọc một nguồn trạng thái đủ tin cậy cho mục tiêu thu hồi. Nếu chỉ đọc một denylist cache cũng đang stale, emergency revocation vẫn có thể bị bỏ lỡ.

Đối với thao tác có yêu cầu thu hồi tức thì, xác định điểm kiểm tra cuối cùng trước authorization hoặc commit nghiệp vụ. Đối với request ít nhạy cảm hơn, TTL và propagation bound có thể là policy chấp nhận được.

## 20. Lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân | Hậu quả | Cách xử lý |
| --- | --- | --- | --- |
| Unknown kid thì chọn key đầu tiên | Fallback tùy tiện | Có thể xác minh sai key hoặc chấp nhận sai token | Refresh có kiểm soát rồi reject nếu vẫn unknown |
| Mỗi request unknown kid đều fetch JWKS | Không có coalescing/cooldown | Request storm và DoS | Single-flight, cooldown, rate limit |
| JWKS lỗi thì bỏ qua chữ ký | Ưu tiên availability sai cách | Chấp nhận token không xác minh | Fail closed |
| JWKS lỗi thì xóa cache cũ | Refresh không atomic | Từ chối token hợp lệ không cần thiết | Giữ last-known-good trong giới hạn policy |
| Dùng stale key vô thời hạn | Không có stale limit | Có thể tin key đã bị thu hồi | Max stale age và emergency invalidation |
| Gỡ key cũ ngay khi đổi signer | Không có overlap | Token cũ còn hạn bị từ chối | Planned rotation có overlap |
| Giữ key compromise để tương thích | Nhầm emergency với planned rotation | Attacker tiếp tục ký token | Thu hồi khẩn cấp, denylist và purge cache |
| Cập nhật JWKS từng phần | Mutate cache tại chỗ | Request thấy key set không nhất quán | Snapshot bất biến và atomic swap |
| kid trùng nhưng chọn tùy tiện | Không validate uniqueness | Kết quả phụ thuộc thứ tự | Reject key set mơ hồ |
| Tin jku/x5u từ token | Token quyết định nguồn khóa | SSRF/key substitution | Chỉ dùng trusted JWKS URI |
| Cache dùng chung giữa issuer | Không namespace cache | Key issuer khác bị dùng nhầm | Namespace theo issuer và trust config |
| Dùng kid để chọn alg | Không pin thuật toán | Algorithm confusion | Allowlist alg độc lập |
| Không kiểm tra generation | Thiếu quan sát cache | Khó điều tra race | Log generation/cache age |
| Log raw token/JWKS private material | Debug thiếu redaction | Rò rỉ credential/khóa | Redact và bảo vệ evidence |

## 21. Checklist kiểm thử trước khi phát hành

### 21.1. Key selection

- [ ] kid được xem là untrusted input.
- [ ] Issuer được chọn từ trust configuration.
- [ ] JWKS cache namespace theo issuer.
- [ ] Key selection kiểm tra kid, kty, use, key_ops, alg và key parameters.
- [ ] Duplicate kid gây mơ hồ bị từ chối.
- [ ] Missing kid được xử lý theo token profile.
- [ ] Thuật toán được pin bằng allowlist.
- [ ] Không tải jku/x5u tùy ý từ token.

### 21.2. Unknown kid và DoS

- [ ] Unknown kid kích hoạt tối đa số lần refresh hữu hạn.
- [ ] Concurrent requests dùng single-flight.
- [ ] Có cooldown/rate limit/backoff.
- [ ] Negative cache có TTL và giới hạn dung lượng.
- [ ] Độ dài và định dạng kid có giới hạn.
- [ ] Không ghép kid vào URL hoặc filesystem path.
- [ ] Unknown kid sau refresh thành công bị reject.

### 21.3. JWKS failure và cache

- [ ] Timeout, DNS, TLS, 429, 5xx và parse error được kiểm thử.
- [ ] Last-known-good không bị ghi đè bởi response lỗi.
- [ ] Stale-if-error có giới hạn.
- [ ] Không dùng stale key đã bị compromise.
- [ ] Cache update là atomic snapshot.
- [ ] Cache header có giới hạn local policy.
- [ ] Multi-instance propagation có metric và alert.

### 21.4. Rotation và revocation

- [ ] New public key được publish trước khi bắt đầu ký bằng key mới.
- [ ] Old key được giữ trong overlap tới khi token cũ hết hạn cộng skew/margin.
- [ ] kid mới không tái sử dụng ID của key cũ.
- [ ] Emergency rotation có đường invalidation/denylist riêng.
- [ ] Request đang chạy có semantics rõ khi key bị thu hồi.
- [ ] Có test cho cache cũ và JWKS outage trong lúc compromise.

## 22. Câu hỏi tự kiểm tra

1. kid có vai trò gì và vì sao không phải bằng chứng xác thực?
2. Vì sao verifier không được tải JWKS từ jku hoặc x5u tùy ý?
3. Sau khi refresh JWKS thành công mà kid vẫn không tồn tại, cần làm gì?
4. Phân biệt unknown kid sau refresh thành công với JWKS endpoint unavailable.
5. Vì sao verifier cần fail closed khi không có key phù hợp?
6. Single-flight và cooldown giúp chống kiểu DoS nào?
7. Vì sao negative cache phải có giới hạn dung lượng và TTL?
8. Khi JWKS endpoint lỗi, lúc nào last-known-good cache có thể được dùng?
9. Vì sao không được dùng stale-if-error vô thời hạn?
10. Vì sao planned rotation cần overlap giữa key cũ và key mới?
11. Khi nào có thể gỡ public key cũ khỏi JWKS?
12. Snapshot bất biến giúp xử lý request đang chạy như thế nào?
13. Vì sao xóa key khỏi JWKS origin chưa đủ để emergency revoke?
14. Cần kiểm thử những gì khi nhiều instance có generation JWKS khác nhau?

## 23. Tiêu chuẩn và tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515), protected header, kid và xác minh chữ ký.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517), JWK, JWKS và thuộc tính khóa.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519), cấu trúc JWT và registered claims.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638), định danh khóa bằng thumbprint.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414), metadata và jwks_uri.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725), algorithm verification, issuer/audience và các thực hành xác minh an toàn.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068), profile JWT access token.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111), semantics cache HTTP và validation.
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html), bảo vệ API và xử lý bearer credential.
