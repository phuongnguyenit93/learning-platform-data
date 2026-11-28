# Mô hình đe dọa: Proxy không tin cậy trong HMAC request authentication

HMAC request authentication cho phép client và server dùng một **shared secret** để tạo và xác minh chữ ký trên **canonical request**. Khi chữ ký được kiểm tra đúng, server có cơ sở tin rằng những thành phần đã ký không bị sửa và request được tạo bởi bên có khả năng sử dụng secret. Nhưng request thường đi qua forward proxy, reverse proxy, load balancer hoặc API gateway. Một proxy không tin cậy có thể sửa request, thêm header, thay cách biểu diễn đường dẫn, chặn hoặc phát lại request đã có chữ ký hợp lệ.

Bài này thuộc chương **Mô hình đe dọa** và tập trung vào **Proxy không tin cậy**: xác định khả năng của kẻ tấn công tại điểm trung gian, đặt ranh giới tin cậy, bảo vệ method/URI/header/body theo hợp đồng ký, kiểm thử đường đi qua proxy/gateway, chống replay bằng timestamp/nonce, quản lý key rotation và phân biệt xác thực với phân quyền.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Phân biệt proxy chuyển tiếp kết nối TLS, proxy chấm dứt TLS và ingress/gateway thuộc hạ tầng tin cậy.
2. Mô tả rõ những gì HMAC bảo vệ, những gì HMAC **không** thể ngăn khi proxy bị kiểm soát.
3. Phân tích tấn công sửa URI, query, header, body; header spoofing; request replay; parser disagreement và request smuggling.
4. Xác định vị trí xác minh chữ ký và xử lý rewrite sao cho thông tin **đã xác minh** chính là thông tin được ứng dụng sử dụng.
5. Thiết kế bộ kiểm thử bảo mật cho cả HTTP/1.1, HTTP/2, TLS termination và nhiều replica.

## 2. Kiến trúc mẫu và ranh giới tin cậy

~~~mermaid
flowchart LR
    C["Client giữ shared secret"] -->|Request + HMAC| P["Proxy trung gian không tin cậy"]
    P -->|Có thể sửa hoặc replay| G["Ingress / gateway thuộc hệ thống"]
    G --> B["Backend xử lý nghiệp vụ"]
    S[("Secret store và nonce store")] --- G
    S --- B
~~~

**Ranh giới tin cậy (trust boundary)** là nơi lưu lượng từ thành phần do người khác kiểm soát chuyển vào hệ thống được xác thực và quản trị. Tên gọi proxy, gateway, mạng nội bộ hay địa chỉ IP private **không tự chứng minh** thành phần đó đáng tin; phải biết ai kiểm soát cấu hình, ai có thể gọi trực tiếp backend, TLS kết thúc ở đâu và identity được truyền giữa các hop bằng gì.

| Mô hình trung gian | Proxy làm được gì? | Ý nghĩa bảo vệ |
| --- | --- | --- |
| HTTPS được tunnel qua proxy bằng CONNECT, client xác minh chứng chỉ server thực | Proxy quan sát metadata kết nối, kích thước, thời gian; có thể trì hoãn/ngắt nhưng không đọc/sửa plaintext HTTP | TLS bảo vệ request; HMAC là tầng xác thực thêm ở ứng dụng. |
| Proxy chấm dứt TLS rồi kết nối lại | Proxy có thể đọc/sửa plaintext HTTP và tạo response; nếu bên trung gian nắm quyền TLS termination, có thể xem dữ liệu nhạy cảm | HMAC phát hiện sửa **những thành phần đã ký** nếu secret không lộ và verifier dùng cùng contract; không khôi phục bí mật hay xác thực response. |
| Gateway do tổ chức quản trị, được xác thực giữa các hop | Có thể rewrite path, normalize header, thay body theo chính sách | Có thể làm điểm xác minh đáng tin, nhưng phải đặt verify và rewrite theo một thiết kế thống nhất. |

Một proxy không tin cậy có thể làm sai lệch hoặc hủy request, nhưng nếu không biết secret, nó **không thể tự tạo chữ ký HMAC hợp lệ cho dữ liệu canonical đã bị thay đổi**, với giả định thuật toán và quản lý secret an toàn. Tuy vậy, nó vẫn có thể phát lại nguyên văn một request hợp lệ, đổi **phần không được ký**, thay route ở một tầng xử lý có lỗi, khai thác khác biệt parser hoặc từ chối phục vụ.

**HTTPS vẫn cần thiết.** HMAC không mã hóa body hoặc header, không xác thực response và không bảo đảm request được chuyển tiếp. Nếu proxy chấm dứt TLS và client tin cậy chứng chỉ của nó, proxy có thể đọc plaintext dù request đã ký. Nếu yêu cầu bí mật dữ liệu xuyên suốt đến backend, phải thiết kế kết nối TLS phù hợp với điểm tin cậy thực tế, không chỉ thêm HMAC.

## 3. Tài sản, kẻ tấn công và giả định

### Tài sản cần bảo vệ

- **Shared secret và key ID:** secret phải không lộ và được ràng buộc với client, dịch vụ/audience, phiên bản khóa và thời gian hiệu lực.
- **Dữ liệu có ý nghĩa bảo mật:** HTTP method, request target, query, header identity/tenant/audience, content type/encoding và body của thao tác.
- **Tính đúng đắn của nghiệp vụ:** đúng endpoint, đối tượng, số tiền, tài khoản, phạm vi phân quyền và số lần thực thi.
- **Danh tính sau xác thực:** backend phải phân biệt identity được gateway đáng tin xác minh với chuỗi do người gọi tự khai báo.
- **Trạng thái chống replay:** timestamp/nonce cùng kho lưu nonce dùng chung giữa replica; idempotency nếu có tác dụng phụ.

### Khả năng của kẻ tấn công

Giả sử đối thủ **không biết shared secret**, nhưng kiểm soát một proxy ở giữa client và verifier, có thể quan sát plaintext nếu proxy có khả năng terminate TLS. Đối thủ có thể:

- Thêm, xóa, sửa và nhân đôi HTTP header; sửa method, raw path, query hoặc body.
- Rewrite URL, thay dấu percent-encoding, thay thứ tự tham số, đổi HTTP/2 sang HTTP/1.1 hoặc làm khác biểu diễn framing.
- Chèn các header như X-Forwarded-For, X-Forwarded-Host, X-Forwarded-Proto, X-Original-URI và X-Authenticated-User.
- Lưu bản sao request đã ký rồi phát lại, gửi đồng thời đến nhiều backend, trì hoãn request tới khi hết hạn.
- Chặn request, trả về response giả nếu chiếm quyền điểm TLS termination, hoặc gửi lưu lượng gây quá tải.

Ngoài phạm vi giả định này là trường hợp secret bị lộ hoặc gateway/verifier bị chiếm quyền. Khi ấy kẻ tấn công có thể ký request mới hoặc giả mạo kết quả xác minh; HMAC tự nó không giải quyết sự cố lộ key. Cần thu hồi khóa, rotate, cách ly thành phần bị xâm nhập và điều tra hệ thống.

## 4. HMAC bảo vệ chính xác những gì?

Giả sử client gửi lệnh chuyển tiền:

~~~http
POST /v1/transfers?dryRun=false HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-42
X-Key-Id: key-2026-11
X-Timestamp: {epoch-seconds}
X-Nonce: {128-bit-random-hex}
X-Content-SHA256: {sha256-of-body}
X-Signature: {base64-hmac-signature}

{"from":"A","to":"B","amount":250000}
~~~

Các giá trị trong ngoặc nhọn chỉ là **placeholder**, không phải digest hay chữ ký tính sẵn.

Nếu client chỉ ký **body**, proxy có thể đổi query từ dryRun=false thành dryRun=true hoặc chuyển route; chữ ký body vẫn đúng. Nếu chỉ ký method và URI, proxy có thể đổi amount. Nếu ký body hash nhưng không đưa body hash vào canonical request được **HMAC** bảo vệ, đối thủ có thể sửa cả body và hash. Nếu không bảo vệ audience/dịch vụ đích, cùng chữ ký có nguy cơ bị sử dụng nhầm ở dịch vụ khác nếu các bên dùng chung secret.

| Nhu cầu | HMAC giải quyết? | Kiểm soát bổ sung |
| --- | --- | --- |
| Phát hiện thay đổi method, URI, header, body **đã ký** | Có, nếu canonical hai phía nhất quán và secret an toàn | Từ chối chữ ký sai; ký đủ mọi trường chi phối nghiệp vụ. |
| Xác thực bên giữ shared secret | Có, nếu key gắn với client/audience đúng | Quản lý khóa, phân tách secret theo dịch vụ, thu hồi và rotation. |
| Ngăn phát lại nguyên văn request hợp lệ | Không tự động | Timestamp, nonce duy nhất, lưu nonce nguyên tử và TTL. |
| Giữ bí mật request trước proxy thấy plaintext | Không | TLS xuyên suốt đến điểm được tin cậy, hạn chế TLS termination. |
| Xác thực response từ server | Không | TLS có xác minh điểm cuối hoặc cơ chế xác thực response riêng khi cần. |
| Ngăn drop, trì hoãn hoặc DoS | Không | Timeout, retry có kiểm soát, rate limit, circuit breaker, giám sát. |
| Quyết định client được thao tác tài nguyên nào | Không | Authorization theo identity, scope, tenant và tài nguyên. |

Do đó không được kết luận “request có HMAC nên an toàn qua mọi proxy”. Chỉ những thành phần **có mặt trong canonical request và được verifier kiểm tra trên cùng biểu diễn** mới được HMAC ràng buộc.

## 5. Thiết kế hợp đồng canonical request

Một hợp đồng **minh họa** có thể dùng format dưới đây; không có định dạng HMAC request nào tự động thống nhất cho mọi API. Các dòng nối bằng **LF** (byte 0A), không có LF cuối cùng, rồi mã hóa UTF-8:

~~~text
HMAC-V1
POST
/v1/transfers?dryRun=false
api.example.test
x-client-id:partner-42
x-key-id:key-2026-11
x-timestamp:1795800000
x-nonce:4efc20b22d40a23d08e02c60f74e96a1
content-type:application/json
content-encoding:identity
x-content-sha256:{64-lowercase-hex-characters}
~~~

~~~text
bodyHash  = lowerHex(SHA256(bodyBytes))
canonical = joinLinesWithLF(contractFields)
signature = Base64(HMAC_SHA256(secretBytes, UTF8(canonical)))
~~~

**Hợp đồng bắt buộc ghi rõ**:

1. **Version/domain marker:** HMAC-V1 là marker minh họa để ngăn nhầm format khi giao thức thay đổi; không phải chuẩn chung.
2. **Method và URI:** method chữ hoa ASCII; request target lấy từ raw path + raw query; giữ nguyên thứ tự, percent-encoding, tham số trùng và dấu hỏi khi có query rỗng. Không tự decode rồi encode lại.
3. **Audience:** giá trị api.example.test được ràng buộc theo cấu hình/verifier và dịch vụ được phép xử lý, không tự lấy từ một X-Forwarded-Host chưa xác thực.
4. **Header:** danh sách, thứ tự, tên chữ thường, cách xử lý whitespace, giá trị lặp và ký tự đặc biệt phải thống nhất. Với ví dụ này, các header đã ký chỉ có một giá trị, không có CR/LF hoặc whitespace thừa; nếu mơ hồ thì từ chối.
5. **Body:** SHA-256 tính trên **byte đúng theo hợp đồng**, bao gồm body rỗng. Nếu dùng content encoding như gzip, cần định nghĩa hash trên encoded hay decoded representation, ở điểm nào trước/sau proxy; không để hai phía tự đoán.
6. **Secret:** key ID chỉ giúp chọn secret; secret không xuất hiện trong request và nên được cấp qua secret manager/kênh an toàn. X-Signature mang Base64 của HMAC; header chữ ký **không được ký vào chính nó**.
7. **Replay metadata:** timestamp biểu diễn epoch seconds, nonce là giá trị ngẫu nhiên đủ mạnh, ví dụ 128 bit từ SecureRandom; cả hai nằm trong canonical để proxy không thể đổi mà vẫn giữ chữ ký hợp lệ.

Trường **content-encoding:identity** ở ví dụ là *giá trị logic do contract định nghĩa* cho body không nén; HTTP request thật có thể không gửi Content-Encoding khi identity. Client và verifier phải thống nhất cách đưa giá trị này vào canonical. Nếu Content-Type, tenant, user/role, idempotency key hoặc một header khác ảnh hưởng đến nghiệp vụ thì cũng cần ràng buộc bằng chữ ký; không mặc định mọi header đều đáng tin.

### 5.1. URI có thể bị diễn giải khác nhau

Các request target sau có thể dẫn đến route hoặc tham số khác nhau:

~~~text
/v1/files/a%2Fb?role=user&role=viewer
/v1/files/a/b?role=user&role=viewer
/v1/files/a%2Fb?role=viewer&role=user
/v1/files/a%2Fb?role=viewer
~~~

Proxy có thể decode %2F thành slash, gộp hai dấu slash, sắp xếp query hoặc chọn một tham số khi query trùng tên; backend có thể parse theo cách khác. Khi đó verifier có thể kiểm tra chữ ký trên biểu diễn A nhưng handler xử lý biểu diễn B.

Thiết kế an toàn cần bảo đảm **cùng một nghĩa đã xác minh được dùng để route và authorize**. Có thể yêu cầu raw request target duy nhất; hoặc chuẩn hóa theo quy tắc được xác định trước tại boundary được kiểm soát, bảo đảm client và verifier cùng tạo canonical đó. Nếu dạng input không hỗ trợ hoặc gây mơ hồ, từ chối request thay vì thử nhiều phép canonicalization cho đến khi chữ ký khớp.

### 5.2. Header forwarded và header danh tính không thể tự tin cậy

~~~http
X-Forwarded-For: 127.0.0.1
X-Forwarded-Proto: https
X-Forwarded-Host: admin.internal.test
X-Original-URI: /admin
X-Authenticated-User: superuser
X-Verified: true
~~~

Những chuỗi trên **không phải bằng chứng** về IP, scheme, route gốc, danh tính hay trạng thái đã xác minh. Client hoặc proxy không tin cậy có thể tự tạo. Nếu cần dùng forwarded header, ingress đáng tin phải xóa/ghi đè những giá trị từ bên ngoài, dựng lại từ kết nối và cấu hình đã xác thực, rồi truyền qua kênh đáng tin. Backend phải từ chối đường gọi trực tiếp giả mạo các header này.

Các header vốn biến đổi theo từng hop như Connection, Transfer-Encoding hay Via thường không phù hợp để ràng buộc một chữ ký end-to-end. Nhưng các header ảnh hưởng tới cách diễn giải dữ liệu, ví dụ Content-Type, Content-Encoding, tenant hoặc idempotency key, cần được bảo vệ bằng contract cụ thể.

## 6. Các hướng tấn công cụ thể

| Tấn công | Cách proxy khai thác | Thiết kế phòng vệ |
| --- | --- | --- |
| Sửa trường chưa ký | Đổi query dryRun, role, accountId; sửa header tenant | Ký mọi trường chi phối quyết định nghiệp vụ; từ chối input không khớp hợp đồng. |
| Rewrite path | Đổi /public/transfer thành /internal/transfer hoặc decode %2F | Xác minh trước rewrite tại điểm tin cậy, hoặc dùng mapping đáng tin để backend khôi phục request gốc và kiểm tra route. |
| Header spoofing | Tự thêm X-Authenticated-User, X-Forwarded-Host, X-Original-URI | Ingress strip/overwrite; xác thực hop nội bộ; không trust metadata do người gọi cấp. |
| Header ambiguity | Gửi hai Content-Type, hai X-Timestamp, khác thứ tự/case | Parser và canonical policy duy nhất; từ chối field trùng/mơ hồ trước xác minh. |
| Body mutation | Đổi amount, whitespace JSON, Unicode, content encoding | Hash body bytes đúng contract, kiểm tra cùng representation trước khi xử lý. |
| Replay | Proxy chụp POST hợp lệ, gửi lại trong cửa sổ timestamp | Nonce store dùng chung và claim nguyên tử; idempotency cho side effect. |
| Cross-service replay | Hai API dùng cùng secret, không ràng buộc audience | Tách secret theo dịch vụ/client; ký và verify audience, key scope. |
| Request smuggling | Proxy và backend parse khác Content-Length/Transfer-Encoding | Từ chối framing mơ hồ ở ingress, đồng bộ HTTP parser và kiểm thử gateway; HMAC không thay thế lớp bảo vệ này. |
| Bypass xác minh | Gọi backend thẳng với X-Verified: true | Cô lập backend, xác thực gateway→backend, chỉ chấp nhận identity từ ingress đã xác minh. |
| Drop, delay hoặc DoS | Proxy chặn, trì hoãn, spam request sai chữ ký | Timeout, rate limit, tài nguyên hữu hạn và quan sát hệ thống; HMAC không bảo đảm availability. |

### Tấn công replay không làm thay đổi chữ ký

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Proxy độc hại
    participant V as Verifier
    participant N as Nonce store
    C->>P: POST + HMAC + timestamp + nonce=n1
    P->>V: Chuyển nguyên request đã ký
    V->>N: Claim (clientId, keyId, n1)
    N-->>V: Thành công
    V-->>P: Request hợp lệ
    P->>V: Replay lại nguyên request, nonce=n1
    V->>N: Claim (clientId, keyId, n1)
    N-->>V: Đã tồn tại
    V-->>P: Từ chối replay
~~~

Timestamp giúp giới hạn tuổi thọ request, ví dụ chỉ chấp nhận sai lệch ±300 giây theo chính sách dịch vụ; đây **không phải** hằng số bắt buộc của HMAC. Chỉ kiểm tra timestamp sẽ **không** chặn hai bản sao đến trong khoảng hợp lệ. Nonce phải được server ghi nhận bằng phép **insert-if-absent nguyên tử** giữa toàn bộ replica, với TTL đủ phủ cửa sổ thời gian chấp nhận. Trong ứng dụng có thao tác tạo giao dịch, một retry với nonce mới vẫn có thể thực thi hai lần nếu response đầu mất; do đó cần **idempotency key** được ký và thực thi ở tầng nghiệp vụ.

## 7. Đặt bộ xác minh khi có gateway rewrite

### Phương án A: Xác minh tại ingress đáng tin trước khi rewrite

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Proxy không tin cậy
    participant G as Ingress đáng tin
    participant B as Backend
    C->>P: Request + HMAC
    P->>G: Forward / sửa / replay
    G->>G: Parse + kiểm tra contract
    G->>G: HMAC, timestamp, nonce, audience
    alt Hợp lệ
        G->>G: Áp dụng route rewrite theo policy
        G->>B: Identity đã xác minh qua kênh có xác thực
        B->>B: Authorization + idempotency
        B-->>C: Kết quả qua ingress
    else Không hợp lệ
        G-->>C: Từ chối
    end
~~~

Ưu điểm là bộ xác minh nhìn thấy request tại ranh giới đầu vào trước các thay đổi nội bộ. Nếu dữ liệu đã ký bị proxy không tin cậy sửa, chữ ký sai và hệ thống **fail closed**. Sau xác minh, ingress có thể rewrite theo policy và gửi identity đã xác minh đến backend qua kênh **mTLS hoặc một kênh nội bộ đã xác thực, giới hạn quyền truy cập**. Backend cũng cần chặn yêu cầu gọi thẳng từ ngoài và không lấy danh tính từ header tự khai báo.

Điểm cần nhớ: **không thể giao nhiệm vụ xác minh cho một proxy do đối thủ kiểm soát**, rồi tin một header “đã verify” do proxy đó gửi. Gateway chỉ là boundary đáng tin nếu hệ thống thực sự kiểm soát và xác thực nó.

### Phương án B: Backend xác minh sau gateway

Backend có thể giữ secret và trực tiếp kiểm tra HMAC nếu nó nhận được **đúng dữ liệu được client ký**. Nhưng gateway có thể đổi raw path, host, một signed header hoặc body trước khi request đến backend. Khi đó backend dựng canonical khác và phải từ chối.

Nếu cần backend verify trong kiến trúc có rewrite, ingress **đáng tin** phải bảo toàn metadata request gốc một cách có xác thực và ràng buộc nó với request được gửi nội bộ. Backend phải dựa trên metadata thực sự do ingress cung cấp qua kênh tin cậy và kiểm tra mapping từ URI đã ký đến route nội bộ, không tin trực tiếp X-Original-URI từ internet. Tham chiếu request gốc phải đi cùng request thực thi để tránh nhầm body, target hoặc client.

**Quy tắc lựa chọn:** xác định node đáng tin đầu tiên có thể đọc method, raw request target, signed headers và body theo contract; verify ở đó **trước khi các biến đổi làm thay đổi nghĩa bảo mật**, hoặc thiết kế một cơ chế truyền dữ liệu gốc đáng tin tới verifier. Kết quả verify phải gắn với hành động và tài nguyên backend thực thi. Tránh “chữa” signature mismatch bằng cách bỏ bớt URI/header/body khỏi dữ liệu được ký.

## 8. Các kiểm soát bổ sung tại trust boundary

1. **Tiền kiểm request:** giới hạn kích thước body, số lượng header, độ dài URI; từ chối header trùng/không hợp lệ và framing HTTP mơ hồ trước khi đi vào nghiệp vụ. Đồng bộ HTTP parser giữa ingress và backend để giảm request smuggling.
2. **Xác minh chính xác:** lấy secret theo (client ID, key ID) từ key store được kiểm soát; kiểm tra key đang hiệu lực, đúng audience; dựng canonical duy nhất, băm body bytes và HMAC. So sánh byte chữ ký đã giải mã Base64 bằng hàm so sánh thời gian hằng tương đối, ví dụ MessageDigest.isEqual trong Java.
3. **Replay:** kiểm tra timestamp và claim nonce nguyên tử sau khi chữ ký hợp lệ, trước tác dụng phụ. Không dùng map nonce riêng của từng process khi có nhiều replica.
4. **Phân quyền:** kiểm tra client đã xác thực có quyền thực hiện method/route cụ thể, thuộc đúng tenant và được truy cập đối tượng đang nhắm đến. Chữ ký hợp lệ của một client chỉ được đọc không cho phép xóa dữ liệu.
5. **Bảo vệ hops nội bộ:** ingress xóa các header danh tính không đáng tin, chỉ phát hành identity nội bộ sau xác minh; giới hạn network path và xác thực gateway→backend. Không cho backend chấp nhận X-Verified hoặc X-Authenticated-User từ một yêu cầu bên ngoài.
6. **Quản lý key rotation:** key ID chọn đúng secret và phạm vi dịch vụ; có giai đoạn cho phép key cũ/mới theo chính sách, sau đó thu hồi key cũ. Không thử tùy tiện mọi secret để tìm chữ ký khớp. Nếu nghi key lộ, thu hồi sớm thay vì chờ hết kỳ rotation.
7. **TLS, timeout và quan sát:** xác minh TLS đến endpoint được tin cậy, đặt timeout/rate limits và chỉ log mã lỗi, trace ID, key ID công khai khi cần; không log secret, payload nhạy cảm hoặc canonical đầy đủ nếu chứa dữ liệu bí mật.

Một lưu ý với **Java/Spring/Servlet**: các API request thường trả về URI đã qua một hoặc nhiều bước parse/normalize, và getPath khác với getRawPath. Không mặc nhiên coi URI trong controller là raw request target mà client ký. Phải kiểm chứng tại chính HTTP stack và gateway đang dùng, đặc biệt khi HTTP/2 sử dụng :method, :path, :authority và proxy dịch về HTTP/1.1 với Host. Cũng phải kiểm thử trường hợp proxy nén/giải nén body: HMAC của digest trên body bytes ở hai phía chỉ nhất quán khi hợp đồng chỉ rõ encoded hay decoded body và thứ tự xử lý.

## 9. Bộ kiểm thử proxy/gateway

Tạo môi trường thử với client ký HMAC bằng secret **dùng cho test**, một proxy có thể cố ý sửa request, một verifier và hai replica backend. Không dùng shared secret sản xuất, không dump secret vào log. Theo dõi route ID, HTTP status, lý do lỗi ở mức mã, key ID và trace ID; không ghi body nhạy cảm.

| Kịch bản | Thay đổi tại proxy | Kỳ vọng |
| --- | --- | --- |
| Happy path | Forward request không đổi | HMAC hợp lệ, nonce mới, authorize đúng scope. |
| Sửa query | dryRun=false → dryRun=true | Chữ ký sai vì query được ký. |
| Sửa method | POST → DELETE | Chữ ký sai. |
| Sửa body | Đổi amount hoặc whitespace JSON | Digest/HMAC sai vì body bytes khác. |
| Chèn header mạo danh | X-Authenticated-User: admin, X-Forwarded-Host: internal | Không thay identity, audience hoặc quyền đã xác minh. |
| Header mơ hồ | Hai X-Timestamp hoặc Content-Type | Từ chối request theo chính sách parser/contract. |
| URI mơ hồ | %2F, //, dấu slash cuối, query trùng tên, đổi thứ tự tham số, + và %20 | Đường route/authorize và dữ liệu verify nhất quán; reject dạng không hỗ trợ. |
| Proxy rewrite | Đổi /api/v1/items thành /internal/items | Chữ ký chỉ được chấp nhận nếu vị trí verify/mapping đáng tin bảo toàn đúng contract. |
| Dịch protocol | HTTP/2 ở ngoài, HTTP/1.1 ở backend | Method, path, authority, headers có cùng nghĩa theo contract, không lệch chữ ký. |
| Body transform | Gzip/identity hoặc thay transfer framing | Chỉ được chấp nhận biến đổi đã được hợp đồng ký cho phép; không âm thầm đổi representation. |
| Replay tuần tự | Gửi lại request nguyên vẹn | Request thứ hai bị từ chối theo nonce. |
| Replay đồng thời | Gửi cùng request đến hai replica | Tối đa một lần claim nonce thành công. |
| Trì hoãn | Forward sau thời gian cửa sổ timestamp | Bị từ chối vì hết hạn. |
| Key rotation | Gửi với key cũ, key mới, key đã thu hồi | Verifier chọn đúng key theo key ID và hiệu lực, từ chối key bị thu hồi. |
| Bypass verifier | Gọi thẳng backend hoặc thêm X-Verified: true | Không thể giả identity đã xác minh. |
| Client thiếu quyền | HMAC hợp lệ nhưng gọi tài nguyên tenant khác | Authentication PASS, authorization DENY. |

### Bài tập tình huống

**Tình huống A — Đã ký body nên đủ?** Một API chuyển tiền lấy số tài khoản từ path và cờ dryRun từ query; chữ ký chỉ bao gồm JSON body. Proxy đổi query và path, giữ body. Hãy chỉ rõ hai trường bị bỏ sót, cách thay hợp đồng ký và kết quả mong đợi sau khi verifier kiểm tra.

**Tình huống B — Gateway rewrite.** Client ký /api/v1/orders/42, gateway đổi thành /orders/42, backend lại lấy request URI sau rewrite để verify. Đề xuất đặt verifier ở ingress trước rewrite hoặc cách truyền metadata gốc đáng tin; giải thích tại sao X-Original-URI do người gọi tự gửi là nguy hiểm.

**Tình huống C — Replay đồng thời.** Một POST thanh toán có chữ ký đúng tới hai replica với cùng nonce. Vì sao timestamp chưa đủ? Hãy thiết kế nonce store có insert-if-absent nguyên tử, TTL và idempotency để tránh thực hiện giao dịch hai lần.

**Tình huống D — Chữ ký đúng nhưng không có quyền.** Client chỉ có quyền đọc hóa đơn nhưng ký thành công DELETE hóa đơn của người khác. Bộ xác minh HMAC và bộ phân quyền phải trả kết quả gì ở từng bước?

## 10. Checklist trước khi triển khai

- [ ] Vẽ được toàn bộ HTTP/TLS hops, quyền kiểm soát proxy và điểm đáng tin đầu tiên; chỉ rõ nơi terminate TLS, rewrite và verify.
- [ ] Hợp đồng ký có version, danh sách byte chính xác và bảo vệ method, target, audience, header/body có ý nghĩa bảo mật.
- [ ] Có quy tắc raw URI, query trùng tên, duplicate header, whitespace, content encoding và HTTP/1.1 ↔ HTTP/2; từ chối input mơ hồ.
- [ ] Verifier xác minh trên cùng biểu diễn mà route và authorization thực sự sử dụng; không thử lỏng lẻo nhiều phép chuẩn hóa để hợp thức hóa chữ ký.
- [ ] Các header forwarded và identity từ bên ngoài được xóa/ghi đè tại ingress tin cậy; backend không có đường bypass.
- [ ] Secret được bảo quản và phân tách theo client/audience; key ID gắn với vòng đời key, rotation và thu hồi.
- [ ] Timestamp/nonce được ký và kiểm tra tại server; nonce store dùng chung, claim nguyên tử; idempotency bảo vệ side effect.
- [ ] HTTPS, rate limit, timeout và giám sát được thiết kế riêng vì HMAC không bảo vệ confidentiality, response authenticity hoặc availability.
- [ ] Có test tamper, replay, path/header parser ambiguity, proxy rewrite, multi-replica và route trực tiếp vào backend.
- [ ] Dù chữ ký đúng, ứng dụng vẫn kiểm tra scope, tenant và quyền thao tác tài nguyên.

**Ghi nhớ:** Khi proxy không tin cậy nằm trên đường truyền, HMAC chỉ bảo vệ **những gì thực sự nằm trong canonical request và được xác minh nhất quán**. Từ chối thay đổi ở trường đã ký là hành vi bảo vệ đúng. Replay, key rotation, bảo mật đường truyền và phân quyền đòi hỏi các cơ chế độc lập, được đặt tại trust boundary rõ ràng.
