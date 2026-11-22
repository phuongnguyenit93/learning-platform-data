# Vì sao chữ ký hợp lệ không ngăn token bị sử dụng lại

## 1. Chữ ký hợp lệ chứng minh điều gì?

Một JWT được ký bằng JWS có thể mang chữ ký số hoặc MAC. Khi bên nhận xác minh thành công, kết quả cho biết dữ liệu được bảo vệ khớp với chữ ký được tạo bằng khóa tương ứng và chưa bị sửa đổi theo cách làm phép xác minh thất bại. Nếu khóa được liên kết đúng với issuer đáng tin cậy, bên nhận có thêm cơ sở xác định nguồn phát hành của token.

Tuy nhiên, chữ ký **không chứng minh token đang được gửi lần đầu tiên**. Nó cũng không chứng minh người gửi request hiện tại chính là chủ thể đã nhận token ban đầu.

Kẻ tấn công có thể sao chép nguyên vẹn một bearer token hợp lệ rồi gửi lại nhiều lần. Mỗi bản sao vẫn có cùng header, payload và signature. Chữ ký tiếp tục hợp lệ vì dữ liệu không hề bị thay đổi.

Mã hóa JWE cũng không tự giải quyết vấn đề này. JWE bảo vệ tính bí mật và tính toàn vẹn của nội dung mã hóa; nếu một JWE hợp lệ bị sao chép, bên nhận vẫn có thể giải mã và xác thực tag thành công mỗi lần nhận bản sao đó. Cả chữ ký lẫn authentication tag đều không lưu trạng thái rằng thông điệp đã được dùng trước đây.

Đây là **replay attack (tấn công phát lại)**: một thông điệp, token hoặc bằng chứng xác thực đã hợp lệ trước đó bị ghi lại và gửi lại để thực hiện lại hành động hoặc sử dụng lại quyền đã được cấp.

**Nguyên tắc:** chữ ký bảo vệ tính toàn vẹn và xác thực nguồn phát hành theo khóa; chống replay cần cơ chế kiểm tra tính mới, trạng thái sử dụng hoặc ràng buộc token với người sở hữu.

## 2. Vì sao bearer JWT có thể bị phát lại?

Access token dạng bearer hoạt động theo nguyên tắc: bất kỳ bên nào đang nắm giữ token đều có thể trình token đó để yêu cầu tài nguyên, miễn token còn được chấp nhận. Resource Server không nhất thiết biết ai đang cầm token.

Ví dụ:

~~~http
GET /api/orders HTTP/1.1
Host: api.example
Authorization: Bearer eyJ...signed-token...
~~~

Nếu người dùng hợp lệ gửi request và kẻ tấn công lấy được token, kẻ tấn công có thể gửi lại cùng giá trị:

~~~http
GET /api/orders HTTP/1.1
Host: api.example
Authorization: Bearer eyJ...signed-token...
~~~

Nếu token còn hiệu lực và các điều kiện xác minh đều đúng, cả hai request có thể được chấp nhận. Chữ ký không phân biệt request đầu tiên với request thứ hai.

Token có thể bị lộ qua nhiều con đường:

- Malware hoặc phần mềm độc hại trên thiết bị người dùng.
- XSS hoặc mã chạy trong ngữ cảnh ứng dụng có thể đọc nơi lưu token.
- Log, trace, crash dump hoặc công cụ giám sát ghi lại header nhạy cảm.
- Proxy, gateway hoặc hệ thống debug được cấu hình sai.
- Máy chủ hoặc hệ thống lưu trữ credential bị xâm nhập.
- Token bị sao chép từ clipboard, file cấu hình, backup hoặc công cụ hỗ trợ.
- Kênh truyền không được bảo vệ đúng cách.

TLS/HTTPS bảo vệ dữ liệu trên đường truyền giữa các điểm kết thúc TLS, nhưng không bảo vệ token sau khi nó đã tới endpoint bị xâm nhập hoặc bị ghi vào log. TLS là lớp bảo vệ cần thiết, nhưng không tự biến bearer token thành credential chống phát lại.

## 3. Vì sao các claim thông thường không tự chống replay?

JWT có một số registered claims thường được dùng khi xác minh token. Chúng quan trọng, nhưng từng claim không tự tạo ra cơ chế dùng một lần.

| Claim | Mục đích | Vì sao chưa đủ chống replay? |
| --- | --- | --- |
| `exp` | Giới hạn thời điểm hết hạn | Token vẫn có thể bị dùng lại nhiều lần trước khi hết hạn |
| `nbf` | Xác định thời điểm bắt đầu hiệu lực | Chỉ giới hạn thời điểm; không ghi nhận token đã được dùng |
| `iat` | Ghi nhận thời điểm phát hành | Timestamp không chứng minh request hiện tại là request đầu tiên |
| `aud` | Giới hạn bên nhận dự kiến | Token vẫn có thể bị phát lại nhiều lần tại đúng audience |
| `iss` | Xác định issuer | Xác định nguồn phát hành không ghi nhận lịch sử sử dụng |
| `jti` | Định danh duy nhất của JWT | Chỉ là định danh; cần lưu trạng thái và từ chối lần dùng lại |

### exp chỉ thu hẹp cửa sổ phát lại

Ví dụ access token có thời hạn 10 phút. Nếu kẻ tấn công đánh cắp token ở phút thứ hai, họ vẫn có thể phát lại token trong khoảng thời gian còn lại nếu không có biện pháp bổ sung.

Thời hạn ngắn giúp giảm thời gian token bị lạm dụng, nhưng không bảo đảm token chỉ được sử dụng một lần.

### iat không phải nonce

`iat` cho biết thời điểm token được phát hành. Nhiều request hợp lệ có thể dùng cùng một token và cùng giá trị `iat`. Nếu chỉ từ chối token có `iat` cũ, hệ thống đang áp dụng giới hạn tuổi token chứ chưa phát hiện token đã được dùng trước đó.

### aud ngăn dùng sai nơi, không ngăn dùng lại đúng nơi

Audience giúp ngăn token được cấp cho một API bị sử dụng tại API khác. Nhưng khi token được gửi tới đúng API trong `aud`, nó vẫn có thể được phát lại nhiều lần trong thời hạn cho phép.

### jti chỉ có ý nghĩa chống replay khi có trạng thái

`jti` là định danh JWT được thiết kế để cung cấp một định danh duy nhất trong phạm vi issuer. RFC 7519 cho phép dùng claim này để ngăn JWT bị phát lại. Tuy nhiên, nếu verifier chỉ đọc `jti` rồi bỏ qua, không có gì ngăn lần gửi thứ hai.

Muốn dùng `jti` để chống replay, hệ thống phải ghi nhận nó và kiểm tra mọi lần sử dụng theo một chính sách nhất quán.

## 4. Replay token khác replay request như thế nào?

Hai dạng tấn công có liên quan nhưng cần được phân biệt.

| Dạng | Đối tượng bị phát lại | Hậu quả điển hình |
| --- | --- | --- |
| **Token replay** | Cùng một JWT hoặc bearer credential | Kẻ tấn công sử dụng lại quyền truy cập trong thời gian token còn được chấp nhận |
| **Request replay** | Cùng một HTTP request hoặc thông điệp nghiệp vụ | Một thao tác có thể bị thực hiện nhiều lần, ví dụ tạo đơn hàng hoặc chuyển tiền lặp |
| **Assertion replay** | JWT assertion dùng tại token endpoint | Một grant hoặc client authentication assertion bị gửi lại |
| **Proof replay** | Bằng chứng sở hữu khóa hoặc request signature | Bằng chứng đã tạo trước đó bị gửi lại trong ngữ cảnh còn được chấp nhận |

Một request có thể chứa token hợp lệ nhưng vẫn là bản sao của một request trước đó. Ngược lại, một token có thể được dùng cho nhiều request khác nhau mà mỗi request đều là hành động hợp lệ theo quyền của token.

Chống token replay không tự động bảo đảm thao tác nghiệp vụ chỉ thực hiện một lần. Nếu API thực hiện thao tác có tác động như thanh toán, tạo đơn hoặc gửi lệnh, cần thêm cơ chế idempotency hoặc chống lặp ở tầng nghiệp vụ.

## 5. Chống phát lại bằng jti và replay cache

Với loại JWT assertion hoặc token được thiết kế để dùng một lần, bên nhận có thể yêu cầu `jti` duy nhất và ghi nhận trạng thái sử dụng.

Quy trình cơ bản:

1. Xác minh chữ ký hoặc MAC bằng khóa tin cậy.
2. Kiểm tra issuer, audience, thời hạn và các claim bắt buộc.
3. Lấy `iss` và `jti` từ payload đã xác minh.
4. Tạo khóa tra cứu duy nhất, ví dụ kết hợp issuer và jti.
5. Thực hiện thao tác kiểm tra-và-ghi nguyên tử.
6. Nếu định danh đã tồn tại, từ chối assertion/token như một lần phát lại.
7. Giữ bản ghi đến ít nhất thời điểm token hết hạn cộng dung sai đồng hồ.

Ví dụ logic:

~~~text
replayKey = issuer + ":" + jti
expiresAt = exp + allowedClockSkew

if atomic_insert_if_absent(replayKey, expiresAt):
    accept_first_use
else:
    reject_replay
~~~

Tên hàm chỉ mô tả thao tác cần có. Hệ thống thực tế phải dùng kho lưu trữ hỗ trợ thao tác nguyên tử hoặc transaction tương đương.

### Vì sao cần thao tác nguyên tử?

Giả sử hai request giống nhau đến cùng lúc ở hai instance:

~~~text
Request A: kiểm tra jti chưa tồn tại -> chưa thấy
Request B: kiểm tra jti chưa tồn tại -> chưa thấy
Request A: ghi jti
Request B: ghi jti
~~~

Nếu kiểm tra và ghi là hai thao tác độc lập, cả hai request có thể vượt qua bước kiểm tra trước khi một bản ghi được tạo. Đây là race condition.

Cần một thao tác kiểu compare-and-set, unique insert hoặc transaction bảo đảm chỉ một request đầu tiên có thể ghi thành công. Request còn lại phải nhận kết quả đã tồn tại và bị từ chối.

### Replay cache cần dùng chung giữa các instance

Nếu hệ thống có nhiều node hoặc nhiều vùng, replay state phải được chia sẻ hoặc đồng bộ đủ chặt để hai instance không cùng chấp nhận một `jti`.

Một cache cục bộ riêng cho từng instance chỉ ngăn replay quay lại đúng instance đó. Kẻ tấn công có thể gửi bản sao đến instance khác.

### Thời gian lưu bản ghi

Bản ghi replay cần tồn tại ít nhất cho đến khi assertion/token không còn được chấp nhận:

~~~text
replayRecordTTL >= exp - currentTime + allowedClockSkew
~~~

Có thể thêm khoảng dự phòng vận hành nếu request có thời gian xử lý dài hoặc hệ thống có độ trễ đồng bộ. Không xóa bản ghi ngay sau khi request hoàn tất nếu token vẫn có thể được gửi lại và chính sách yêu cầu dùng một lần.

## 6. Khi nào nên dùng jti replay protection?

Replay cache phù hợp khi một JWT có ngữ nghĩa **mỗi token chỉ được chấp nhận một lần**, ví dụ:

- JWT bearer authorization grant dùng tại token endpoint nếu profile yêu cầu dùng một lần.
- JWT client assertion cần phát hiện việc sử dụng lại.
- Link hoặc mã xác nhận một lần được biểu diễn bằng JWT.
- Một hành động đặc biệt cần assertion riêng và không được gửi lại.
- Một giao thức nội bộ dùng JWT làm bằng chứng cho một giao dịch duy nhất.

Nó thường không phù hợp nếu áp dụng trực tiếp cho mọi access token bearer thông thường mà không thay đổi mô hình sử dụng. Một access token thường được thiết kế để dùng nhiều lần trong suốt thời hạn, trên nhiều request tới Resource Server. Nếu replay cache đánh dấu token đã dùng ngay lần đầu, các request tiếp theo của người dùng hợp lệ cũng bị từ chối.

Với access token thông thường, các lựa chọn thường là:

- Chấp nhận rằng bearer token có thể được dùng lại trong thời hạn, đồng thời giảm lifetime và bảo vệ nơi lưu trữ.
- Dùng cơ chế thu hồi hoặc denylist khi cần vô hiệu hóa token trước exp.
- Chuyển sang sender-constrained token để token chỉ dùng được cùng khóa hoặc chứng thư của client.
- Dùng session/reference token nếu cần trạng thái tập trung và thu hồi nhanh.

Chính sách phải phù hợp với mục đích token. Không thể áp dụng cùng một quy tắc replay cho access token nhiều lần và assertion dùng một lần.

## 7. Chống replay request bằng nonce và timestamp

Với giao thức ký request hoặc thông điệp cần tính mới, bên gửi có thể tạo bằng chứng gắn với từng request thay vì chỉ gửi một token tĩnh.

Một thiết kế tổng quát có thể bao gồm:

- Timestamp để giới hạn tuổi của request.
- Nonce ngẫu nhiên hoặc sequence number để phân biệt từng request.
- HTTP method và URI để ràng buộc bằng chứng với hành động/đích nhận.
- Hash của body hoặc các thành phần quan trọng để phát hiện thay đổi nội dung.
- Chữ ký/MAC trên toàn bộ dữ liệu canonical đã thống nhất.

Ví dụ dữ liệu được bảo vệ:

~~~text
proofInput =
    method
    + "\n" + canonicalUri
    + "\n" + bodyDigest
    + "\n" + issuedAt
    + "\n" + nonce
~~~

Bên nhận xác minh chữ ký, kiểm tra timestamp nằm trong cửa sổ cho phép và đảm bảo nonce chưa được dùng. Nonce phải đủ khó đoán nếu cần ngăn attacker tạo trước bằng chứng, đồng thời cần được ghi nhận theo cách nguyên tử để ngăn hai lần dùng đồng thời.

Timestamp đơn lẻ chỉ giới hạn cửa sổ replay. Nonce/sequence number cùng trạng thái đã dùng mới giúp phát hiện một bằng chứng bị gửi lại trong cửa sổ đó.

Không phải mọi giao thức đều dùng cấu trúc proof như ví dụ. Các thành phần được ký, quy tắc canonicalization, cách cấp nonce và phạm vi lưu trạng thái phải được quy định rõ giữa hai bên.

## 8. Sender-constrained token: ràng buộc token với người sở hữu

Một cách giảm rủi ro bearer-token replay là ràng buộc access token với một khóa hoặc chứng thư mà client phải chứng minh đang sở hữu. Kẻ tấn công chỉ đánh cắp được token sẽ không có đủ vật liệu để sử dụng token theo đúng giao thức.

Hai cơ chế OAuth phổ biến là:

- **Mutual TLS certificate-bound access tokens (RFC 8705):** access token được ràng buộc với chứng thư client. Resource Server kiểm tra client đang trình chứng thư tương ứng khi sử dụng token.
- **Demonstrating Proof of Possession (DPoP, RFC 9449):** client tạo proof JWT ký bằng private key; access token được ràng buộc với public key tương ứng.

Đây là các cơ chế sender-constrained, không phải thuộc tính tự động của mọi JWT. Authorization Server và Resource Server phải hỗ trợ và kiểm tra đúng profile.

### So sánh bearer token và sender-constrained token

| Đặc điểm | Bearer token | Sender-constrained token |
| --- | --- | --- |
| Điều kiện sử dụng | Nắm giữ token | Nắm token và chứng minh sở hữu khóa/chứng thư được ràng buộc |
| Token bị đánh cắp riêng lẻ | Có thể bị dùng lại trong thời hạn | Thường không đủ để tạo request hợp lệ |
| Quản lý khóa client | Không bắt buộc cho bearer semantics | Bắt buộc bảo vệ private key hoặc chứng thư |
| Replay proof/request | Token vẫn có thể bị phát lại | Cần xác minh proof và biện pháp chống replay tương ứng |
| Độ phức tạp | Thấp hơn | Cao hơn; cần quản lý khóa và hỗ trợ ở cả AS/RS |

Sender-constrained token làm giảm giá trị của token bị đánh cắp đơn lẻ, nhưng không loại bỏ mọi rủi ro. Nếu attacker chiếm được cả token lẫn private key, điều khiển endpoint hợp lệ hoặc lấy được proof hợp lệ trong thời gian còn dùng được, tấn công vẫn có thể xảy ra.

## 9. DPoP: proof-of-possession cho từng request

DPoP dùng một JWT proof được client ký bằng private key. Proof được gửi cùng access token để chứng minh client sở hữu khóa đã được liên kết với token.

Một DPoP proof thường chứa các claim/header quan trọng:

- Header `typ` có giá trị `dpop+jwt`.
- Header `alg` phải là thuật toán chữ ký bất đối xứng được cho phép.
- Header `jwk` chứa public key dùng xác minh proof.
- Claim `jti` là định danh duy nhất của proof.
- Claim `htm` ràng buộc proof với HTTP method.
- Claim `htu` ràng buộc proof với URI đích theo quy tắc DPoP.
- Claim `iat` ghi thời điểm tạo proof.
- Claim `ath` ràng buộc proof với access token khi proof được gửi tới Resource Server.
- Claim `nonce` có thể được server yêu cầu để tăng khả năng chống replay.

### Luồng sử dụng khái quát

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    participant RS as Resource Server

    C->>AS: Token request + DPoP proof
    AS->>AS: Verify proof và public key
    AS->>AS: Bind access token với key thumbprint
    AS-->>C: Sender-constrained access token
    C->>RS: Access token + DPoP proof mới
    RS->>RS: Verify proof signature và key binding
    RS->>RS: Kiểm tra htm, htu, iat, ath, nonce
    RS->>RS: Kiểm tra replay jti theo policy
    RS-->>C: Trả kết quả nếu hợp lệ
~~~

Client cần tạo proof mới cho request mới. Không nên gửi lại cùng proof JWT cho nhiều request. Resource Server cần xác minh proof gắn với đúng access token và request hiện tại; chỉ xác minh chữ ký proof là chưa đủ.

### Vì sao DPoP vẫn cần replay detection?

Một proof JWT cũng có chữ ký hợp lệ. Nếu kẻ tấn công lấy được proof và gửi lại trong thời gian proof còn được chấp nhận, chữ ký vẫn hợp lệ. Các triển khai có thể theo dõi `jti` để phát hiện proof đã dùng, giới hạn cửa sổ `iat` và dùng nonce do server cấp.

DPoP ràng buộc token với khóa, còn replay detection kiểm tra proof cụ thể đã được dùng hay chưa. Hai biện pháp bổ sung cho nhau.

## 10. Mutual TLS và certificate-bound access token

Với Mutual TLS (mTLS), client và server xác thực chứng thư trong quá trình TLS handshake. Trong OAuth certificate-bound access token, Authorization Server ràng buộc token với thumbprint của chứng thư client, thường thông qua claim confirmation `cnf` và thuộc tính `x5t#S256`.

Khi Resource Server nhận access token, nó kiểm tra token và xác nhận chứng thư client ở kết nối hiện tại khớp với chứng thư đã ràng buộc. Một attacker chỉ có bearer token nhưng không có private key của chứng thư sẽ khó sử dụng token qua kết nối mTLS của chính mình.

mTLS không tự ngăn mọi replay ở cùng endpoint hoặc trên thiết bị đã bị xâm nhập. Nếu attacker điều khiển client hợp lệ hoặc private key bị lộ, ràng buộc có thể bị vượt qua. Hạ tầng TLS termination cũng phải được cấu hình để Resource Server nhận được bằng chứng chứng thư client đáng tin cậy, không chấp nhận header chứng thư do client tự khai.

## 11. Thu hồi token và denylist có vai trò gì?

Chống replay và thu hồi token là hai mục tiêu liên quan nhưng khác nhau:

- **Replay detection:** từ chối một token/assertion/proof đã được dùng trước đó theo chính sách một lần.
- **Revocation:** từ chối token vẫn còn thời hạn nhưng đã bị vô hiệu hóa do logout, compromise hoặc thay đổi quyền.

Với JWT tự chứa, Resource Server thường có thể xác minh token mà không tra cứu trạng thái trung tâm. Điều này làm việc thu hồi tức thời khó hơn nếu không có cơ chế bổ sung.

Một denylist có thể lưu `jti` hoặc hash token đã bị thu hồi cho đến khi token hết hạn. Khi nhận token, Resource Server kiểm tra chữ ký và claims, sau đó kiểm tra trạng thái thu hồi. Denylist cần được chia sẻ giữa các instance và cập nhật kịp thời.

OAuth Token Introspection (RFC 7662) cho phép Resource Server hỏi Authorization Server về trạng thái token. Cách này thêm phụ thuộc mạng và trạng thái trung tâm, nhưng có thể giúp phản ánh thu hồi nhanh hơn theo chính sách của AS.

Không nên nhầm denylist với replay cache:

| Cơ chế | Bản ghi biểu thị | Hành vi |
| --- | --- | --- |
| Replay cache | Assertion/proof/token đã được sử dụng | Từ chối lần sử dụng tiếp theo trong phạm vi chính sách |
| Revocation denylist | Token đã bị thu hồi | Từ chối mọi lần sử dụng còn lại |
| Allowlist/session store | Token/session đang được phép | Chỉ chấp nhận khi trạng thái còn hợp lệ |

## 12. Chống lặp thao tác nghiệp vụ bằng idempotency

Ngay cả khi token và request proof hợp lệ, client có thể gửi lại request vì timeout, mất kết nối hoặc retry tự động. Nếu request tạo đơn hàng hoặc thanh toán, việc thực hiện lặp có thể gây tác động ngoài ý muốn.

API có thể hỗ trợ `Idempotency-Key` hoặc một định danh giao dịch do client tạo:

~~~http
POST /payments HTTP/1.1
Authorization: Bearer <access-token>
Idempotency-Key: payment-attempt-8f2a
Content-Type: application/json

{"amount":250000,"currency":"VND"}
~~~

Server lưu kết quả gắn với định danh idempotency và chủ thể phù hợp. Khi nhận lại cùng key trong phạm vi chính sách, server trả kết quả đã lưu hoặc xử lý theo quy tắc retry, thay vì tạo một giao dịch mới.

Một thiết kế tốt cần:

- Phạm vi key gắn với client/subject và endpoint hoặc loại thao tác.
- Ghi nhận key và kết quả một cách nguyên tử cùng với thay đổi nghiệp vụ.
- Kiểm tra payload có nhất quán với request ban đầu.
- Quy định thời gian lưu key và cách xử lý retry đang chạy.
- Không dùng idempotency key như một credential thay thế xác thực.

Idempotency ngăn thao tác nghiệp vụ bị thực hiện lặp ngoài ý muốn; nó không thay thế xác minh token hoặc chống replay proof.

## 13. Kết hợp nhiều lớp bảo vệ

Không có một claim hoặc cơ chế đơn lẻ nào giải quyết mọi dạng replay. Có thể kết hợp theo mục đích:

| Rủi ro | Biện pháp phù hợp |
| --- | --- |
| Token bị đánh cắp và dùng trong thời hạn | Sender-constrained token, bảo vệ endpoint và nơi lưu token |
| Assertion dùng một lần bị gửi lại | `jti` + replay cache nguyên tử |
| Proof DPoP bị gửi lại | Kiểm tra `jti`, `iat`, nonce và key binding |
| Token bị thu hồi nhưng chưa hết hạn | Denylist, introspection hoặc session state |
| Request thanh toán bị retry | Idempotency key và transaction an toàn |
| Request bị nghe lén trên mạng | TLS/HTTPS và cấu hình kênh truyền đúng |
| Token bị sử dụng sai API | Kiểm tra `aud`, issuer và token profile |
| Token có thời hạn quá dài | Lifetime ngắn phù hợp với mục đích |

Một profile có thể yêu cầu assertion một lần tại token endpoint nhưng vẫn cấp access token có thể dùng nhiều lần trong vài phút. Trong trường hợp đó, replay cache áp dụng cho assertion; access token được bảo vệ bằng lifetime, sender constraint, revocation và policy riêng.

## 14. Ví dụ: cùng một JWT được gửi hai lần

Giả sử một client gửi JWT assertion tới token endpoint. Assertion có `iss`, `sub`, `aud`, `exp` và `jti` hợp lệ; chữ ký được xác minh bằng public key tin cậy.

### Không có replay cache

~~~text
Request 1:
  Signature valid
  iss/aud/exp valid
  jti = assertion-123
  -> Accept

Request 2:
  Signature valid
  iss/aud/exp valid
  jti = assertion-123
  -> Accept again
~~~

Mọi kiểm tra mật mã và claim vẫn thành công vì nội dung hai request giống hệt nhau. Hệ thống không có thông tin cho biết `jti` đã được chấp nhận trước đó.

### Có replay cache nguyên tử

~~~text
Request 1:
  Signature valid
  iss/aud/exp valid
  atomic insert issuer:jti -> success
  -> Accept

Request 2:
  Signature valid
  iss/aud/exp valid
  atomic insert issuer:jti -> already exists
  -> Reject as replay
~~~

Sự khác biệt nằm ở trạng thái sử dụng được lưu tại AS, không nằm trong chữ ký của JWT.

## 15. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ chữ ký hợp lệ đồng nghĩa token chưa từng được dùng | Bearer token bị đánh cắp vẫn dùng lại được | Bổ sung replay policy phù hợp |
| Chỉ dùng `exp` để chống replay | Token có thể bị dùng nhiều lần trước khi hết hạn | Dùng `jti`/replay cache hoặc sender constraint |
| Có `jti` nhưng không lưu trạng thái | Không phát hiện lần gửi thứ hai | Ghi nhận và kiểm tra `jti` nguyên tử |
| Dùng cache riêng từng instance | Replay có thể đi qua node khác | Dùng replay store chia sẻ hoặc cơ chế đồng bộ |
| Kiểm tra rồi ghi bằng hai thao tác riêng | Race condition cho phép hai request cùng thành công | Dùng unique insert/transaction nguyên tử |
| Áp dụng one-time jti cho mọi access token | Request thứ hai của người dùng hợp lệ bị từ chối | Phân biệt access token nhiều lần với assertion dùng một lần |
| Dùng timestamp mà không có nonce/trạng thái | Request vẫn bị phát lại trong cửa sổ thời gian | Kết hợp timestamp với nonce/sequence và replay detection |
| Tin DPoP proof chỉ vì signature hợp lệ | Proof đã ghi lại có thể bị phát lại | Kiểm tra binding, thời gian, nonce và `jti` theo policy |
| Nhầm revocation với replay detection | Không xử lý đúng token đã thu hồi hoặc đã dùng | Thiết kế hai trạng thái riêng |
| Chỉ dùng TLS | Token bị lộ tại endpoint/log vẫn có thể bị phát lại | Bảo vệ endpoint, log và dùng sender constraint |
| Không có idempotency cho thao tác quan trọng | Retry có thể tạo giao dịch trùng | Dùng idempotency key và lưu kết quả nguyên tử |

## 16. Checklist thiết kế chống replay

**Đối với JWT và assertion**

- Xác định token là bearer token dùng nhiều lần hay assertion dùng một lần.
- Không coi chữ ký hợp lệ là bằng chứng token chưa từng được sử dụng.
- Yêu cầu `exp` phù hợp và giới hạn lifetime.
- Kiểm tra `iss`, `aud`, `nbf`, `iat` theo profile.
- Yêu cầu `jti` khi cần nhận diện duy nhất token/proof.
- Dùng replay cache nguyên tử nếu token phải dùng một lần.
- Giữ replay state ít nhất đến khi token không còn được chấp nhận.
- Chia sẻ replay state giữa các instance và vùng cần thiết.
- Quy định cách retry khi assertion đã bị đánh dấu sử dụng.

**Đối với access token**

- Cân nhắc DPoP hoặc mTLS certificate-bound token cho môi trường có rủi ro đánh cắp bearer token cao.
- Bảo vệ private key của client và kiểm tra đúng key binding ở Resource Server.
- Có cơ chế thu hồi hoặc introspection khi cần vô hiệu hóa token sớm.
- Không dùng ID token hoặc assertion thay access token.
- Không ghi token vào log, trace hoặc URL.

**Đối với request nghiệp vụ**

- Dùng nonce/timestamp và request signature nếu giao thức yêu cầu freshness cho từng request.
- Dùng idempotency key cho thao tác có tác động khi client có thể retry.
- Đảm bảo thao tác ghi idempotency và thay đổi nghiệp vụ được đồng bộ nguyên tử.
- Kiểm thử request trùng, request đồng thời, retry sau timeout và replay qua nhiều node.

**Ghi nhớ:** Chữ ký JWT trả lời câu hỏi dữ liệu có bị sửa đổi và có khớp với khóa phát hành hay không; nó không trả lời token đã được dùng chưa. Bearer token có thể bị phát lại trong thời hạn hiệu lực. `exp` chỉ giới hạn cửa sổ, `jti` chỉ định danh và chỉ chống replay khi được lưu/kiểm tra nguyên tử. Với token dùng một lần, dùng replay cache; với access token dùng nhiều lần, cân nhắc sender-constrained token, thu hồi và lifetime ngắn; với thao tác nghiệp vụ, bổ sung idempotency.

### Tài liệu chuẩn để tra cứu

- **RFC 7519 — JSON Web Token (JWT):** registered claim `jti` và cách định danh JWT.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** bearer token có thể được sử dụng bởi bất kỳ bên nào nắm giữ token.
- **RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants:** JWT assertion và khả năng dùng `jti` để ngăn phát lại.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** ràng buộc access token với chứng thư client.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** proof-of-possession cho từng request và ràng buộc token với khóa.
- **RFC 7662 — OAuth 2.0 Token Introspection:** kiểm tra trạng thái token tại Authorization Server.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** khuyến nghị bảo vệ token và giảm rủi ro sử dụng credential.
