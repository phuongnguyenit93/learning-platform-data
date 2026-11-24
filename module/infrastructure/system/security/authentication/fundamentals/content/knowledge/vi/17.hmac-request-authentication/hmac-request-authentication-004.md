# Request signature

## 1. Request signature là gì?

**Request signature** là chữ ký mật mã gắn với một HTTP request để bên nhận kiểm tra request có được tạo bởi bên nắm giữ khóa tương ứng và nội dung được ký có bị thay đổi hay không. Với **HMAC request authentication**, client và server chia sẻ một secret key. Client tính mã xác thực thông điệp (Message Authentication Code - MAC) trên biểu diễn request đã thống nhất; server tính lại bằng secret tương ứng rồi so sánh an toàn.

Một request có chữ ký hợp lệ có thể cung cấp bằng chứng rằng bên gửi biết secret và các thành phần được ký còn nguyên vẹn. Nó **không mã hóa nội dung**, không tự ngăn replay, không chứng minh danh tính pháp lý của người vận hành và không tự cấp quyền truy cập tài nguyên.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, HMAC request authentication bổ sung góc nhìn về credential và ranh giới tin cậy: ngoài password, passkey, certificate hoặc bearer token, một service có thể xác thực từng request bằng chữ ký trên HTTP message. Người học cần biết thiết kế canonical request, bảo vệ secret, chống replay, kiểm tra đúng nội dung và ánh xạ key identity tới principal.

Sau bài học, người học có thể:

- Giải thích HMAC và vai trò của request signature.
- Mô tả vì sao phải chuẩn hóa request thành một chuỗi ký duy nhất.
- Xác định thành phần cần ký: method, authority, path, query, headers, body digest, timestamp và nonce.
- Thiết kế verifier kiểm tra chữ ký, thời hạn, replay và quyền theo đúng thứ tự.
- Quản lý key ID, cấp phát, rotation, revoke và ứng phó khi secret bị lộ.
- Nhận biết khi nào HMAC phù hợp và khi nào nên dùng mTLS hoặc chữ ký bất đối xứng.

## 2. HMAC hoạt động như thế nào?

**HMAC (Hash-based Message Authentication Code)** kết hợp một hash function mật mã với secret key để tạo mã xác thực. Với HMAC-SHA-256, hai bên sử dụng cùng secret và cùng message bytes để tính kết quả:

~~~text
mac = HMAC-SHA-256(secretKey, messageBytes)
signature = Base64url(mac)
~~~

HMAC dùng hai lớp hash với các giá trị đệm nội bộ để tránh các vấn đề khi chỉ ghép secret vào một hash thông thường. Không thay HMAC bằng SHA-256(secret || message) hoặc SHA-256(message || secret); đó không phải cách xây MAC an toàn tổng quát.

Các đặc tính chính:

- **Integrity:** nếu nội dung được ký bị thay đổi, MAC tính lại thường sẽ khác.
- **Authentication of key possession:** chữ ký hợp lệ cho thấy bên tạo MAC biết secret tương ứng, với giả định thuật toán và key an toàn.
- **Shared-key model:** cả client ký và server xác minh đều biết secret; vì vậy cả hai bên đều có khả năng tạo MAC.
- **No confidentiality:** request vẫn đọc được nếu không có TLS hoặc lớp mã hóa khác.
- **No automatic replay protection:** một request đã ký có thể bị gửi lại nếu hệ thống không ràng buộc thời gian, nonce hoặc trạng thái sử dụng.

HMAC là MAC, không phải chữ ký số bất đối xứng. Nó không cung cấp non-repudiation: server xác minh cũng giữ secret nên về mặt mật mã server có thể tạo một MAC giống client.

## 3. Khi nào dùng HMAC request authentication?

HMAC thường phù hợp khi hai hệ thống có quan hệ tin cậy và có thể quản lý secret an toàn, ví dụ:

- Service nội bộ gọi API của service khác.
- Partner server-to-server tích hợp với một API.
- Thiết bị hoặc agent được quản lý, có nơi lưu khóa riêng cho từng thiết bị.
- Webhook provider ký payload để bên nhận xác minh nguồn và tính toàn vẹn.
- API yêu cầu mỗi request được ràng buộc với method, URI, thời gian và nội dung.

HMAC thường **không phù hợp để nhúng một secret dùng chung vào browser JavaScript hoặc mobile app public**. Người dùng có thể tải mã, phân tích binary, hook runtime hoặc trích secret khỏi môi trường client. Nếu mọi bản app dùng cùng một secret, chỉ cần một bản bị trích xuất là toàn bộ client có thể bị giả mạo.

Với public client, cân nhắc Authorization Code + PKCE, passkey/WebAuthn cho người dùng, DPoP hoặc chữ ký bất đối xứng khi cần proof-of-possession, và mTLS cho workload phù hợp. Không chọn HMAC chỉ vì dễ viết vài dòng code.

## 4. Canonical request: hai bên phải ký cùng một message

HTTP request có nhiều cách biểu diễn tương đương hoặc gần tương đương: header có thể khác chữ hoa/thường, query parameter có thể đổi thứ tự, whitespace có thể thay đổi, proxy có thể chuẩn hóa path hoặc giải nén body. Nếu client và server tự diễn giải khác nhau, chữ ký sẽ thất bại hoặc nguy hiểm hơn là hai bên ký/xác minh những nội dung khác nhau.

**Canonical request** là biểu diễn byte/string duy nhất được hai bên thống nhất để ký và xác minh. Một profile minh họa có thể gồm:

1. HTTP method ở dạng chữ hoa.
2. Authority/host đã chuẩn hóa theo quy tắc cố định.
3. Path theo đúng quy tắc percent-encoding và normalization.
4. Query parameters được encode và sắp xếp theo quy tắc xác định.
5. Danh sách headers cần ký, tên header chuẩn hóa và giá trị đã xử lý whitespace.
6. Digest của body chính xác theo byte sequence được định nghĩa.
7. Timestamp, nonce, key ID và metadata bảo mật khác.

Ví dụ chuỗi ký minh họa:

~~~text
HMAC-REQUEST-V1
POST
api.example.test
/v1/transfers
amount=250000&currency=VND
content-type:application/json
content-digest:sha-256=:BASE64_DIGEST:
x-request-timestamp:2026-11-22T05:00:00Z
x-request-nonce:random-unique-value
~~~

Đây là **format ví dụ do ứng dụng định nghĩa**, không phải cú pháp chuẩn HTTP Signature. Điều quan trọng là hai phía phải dùng cùng một phiên bản profile, cùng encoding và cùng quy tắc chuẩn hóa. Nếu cần tương tác với nhiều nhà cung cấp hoặc triển khai quy mô lớn, ưu tiên chuẩn đã được định nghĩa và thư viện tương ứng như HTTP Message Signatures thay vì tự tạo format mới.

### 4.1. Method và authority

Method cần được chuẩn hóa rõ ràng, thường là chữ hoa như GET, POST, PUT, DELETE. Không để một bên ký chuỗi post trong khi bên kia xác minh POST mà không có quy tắc chung.

Authority gồm host và port theo profile. Cần quy định rõ:

- Hostname có chuyển thành lowercase không.
- Port mặc định của HTTPS có được lược bỏ không.
- IPv6 literal được biểu diễn thế nào.
- IDN hostname được chuyển đổi theo quy tắc nào.
- Proxy có thay đổi authority hay không.

Không lấy một header Host tùy ý từ client làm danh tính đáng tin; server cần xác định authority thực tế theo cấu hình ingress/proxy và profile đã thống nhất.

### 4.2. Path và percent-encoding

Path là nơi dễ xảy ra khác biệt giữa proxy, framework và ứng dụng. Các dạng percent-encoding, dấu gạch chéo lặp, dot segment hoặc ký tự Unicode có thể được chuẩn hóa ở một tầng nhưng giữ nguyên ở tầng khác.

Một số nguyên tắc:

- Định nghĩa rõ path được ký trước hay sau bước normalization.
- Tránh tự decode rồi encode lại bằng các thư viện khác nhau ở hai phía.
- Xử lý nhất quán dấu slash cuối, duplicate slash và dot segment.
- Không để proxy xác minh một path nhưng backend thực thi một path khác.
- Nếu path được rewrite, ký/verify tại cùng ranh giới hoặc truyền một representation được bảo vệ và xác định rõ.

Một chữ ký hợp lệ trên đường dẫn /users/a không nên vô tình được chấp nhận cho /users/b chỉ vì một tầng đã chuẩn hóa sai.

### 4.3. Query parameters

Query có thể có nhiều tham số cùng tên, giá trị rỗng, ký tự được encode hoặc thứ tự khác nhau. Profile cần định nghĩa:

- Có giữ tham số trùng hay không; nếu giữ, thứ tự của chúng được xử lý thế nào.
- Quy tắc encode tên và giá trị.
- Có phân biệt tham số a với tham số a có giá trị rỗng không.
- Có sắp xếp theo byte, tên rồi giá trị hay giữ nguyên thứ tự ban đầu.
- Dấu cộng biểu diễn space hay ký tự cộng theo parser nào.

Không nên loại bỏ duplicate parameter ở một tầng nhưng backend lại dùng giá trị cuối cùng ở tầng khác. Điều đó có thể tạo chênh lệch ngữ nghĩa: verifier thấy một request, ứng dụng thực thi một request khác.

### 4.4. Headers

Chỉ ký các header cần thiết, nhưng phải ký đủ để bảo vệ ý nghĩa request. Thường cân nhắc:

- Host hoặc authority.
- Content-Type.
- Content-Digest hoặc trường digest tương đương.
- Timestamp và nonce.
- Header tenant/resource/action nếu chúng ảnh hưởng cách backend diễn giải request.
- Header idempotency nếu chính sách giao dịch phụ thuộc vào nó.

Header name không phân biệt hoa/thường theo HTTP; profile cần lowercase tên header và quy định whitespace. Với header trùng lặp, phải có quy tắc kết hợp hoặc từ chối. Tránh ký một header nhưng lại cho phép backend lấy giá trị khác từ duplicate header.

Không ký các header hop-by-hop hoặc header do proxy tự thay đổi nếu profile không xử lý rõ. Cần xác định chính xác header nào được tạo bởi client, gateway hay backend.

## 5. Body digest: bảo vệ nội dung request

Nếu chỉ ký method, path và timestamp nhưng không ký body, kẻ tấn công có thể thay đổi dữ liệu nghiệp vụ mà chữ ký vẫn hợp lệ. Vì vậy, với request có body, thường tính digest của body rồi đưa digest đó vào canonical request.

~~~text
bodyDigest = SHA-256(exactBodyBytes)
contentDigest = Base64(bodyDigest)
canonicalRequest includes contentDigest
signature = HMAC-SHA-256(secretKey, canonicalRequest)
~~~

Điểm quan trọng là **exactBodyBytes** phải được định nghĩa: byte nào được gửi, byte nào được verifier hash, và proxy có thể biến đổi gì.

### 5.1. JSON và thứ tự thuộc tính

Hai JSON document có thể mang ý nghĩa tương đương nhưng có byte khác nhau:

~~~json
{"amount":100,"currency":"VND"}
~~~

~~~json
{
  "currency": "VND",
  "amount": 100
}
~~~

Nếu ký raw body, hai biểu diễn này có digest khác nhau. Điều đó không sai: client ký chính xác bytes nó gửi. Server phải tính digest trên cùng bytes nhận được trước khi parser biến đổi nội dung.

Nếu muốn ký theo ngữ nghĩa JSON thay vì raw bytes, cần một chuẩn canonical JSON được thống nhất, xử lý rõ Unicode, number representation, duplicate keys và thứ tự thuộc tính. Không tự parse rồi stringify bằng hai thư viện JSON khác nhau và giả định kết quả giống nhau.

### 5.2. Content-Encoding và proxy

Gzip, Brotli hoặc middleware có thể nén/giải nén body. Nếu client ký compressed bytes nhưng verifier hash decompressed bytes, digest không khớp. Nếu gateway thay đổi body rồi backend xác minh, cần xác định chữ ký áp dụng trước hay sau biến đổi.

Các lựa chọn kiến trúc:

- Xác minh tại ingress trước khi middleware biến đổi body.
- Ký một digest được định nghĩa trên representation cụ thể và bảo toàn representation đó tới verifier.
- Dùng chuẩn message signature/digest có quy tắc rõ về content và intermediary.

Không bỏ body khỏi chữ ký chỉ để né lỗi khác biệt encoding; hãy sửa ranh giới canonicalization.

## 6. Timestamp và nonce: chống replay

HMAC tự nó không ngăn replay. Nếu đối thủ lấy được một request hợp lệ, họ có thể gửi lại đúng bytes và MAC trong khi secret vẫn an toàn.

Để hạn chế replay, request thường mang:

- **Timestamp:** thời điểm ký, được đưa vào canonical request.
- **Nonce:** giá trị ngẫu nhiên duy nhất cho mỗi request, cũng được ký.
- **Replay store:** server lưu nonce đã chấp nhận trong khoảng thời gian cho phép và từ chối lần dùng lại.
- **Idempotency key:** với thao tác có side effect, khóa logic để xử lý retry mà không thực hiện giao dịch nhiều lần.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as API Server
    participant R as Replay Store
    C->>C: Tạo timestamp + nonce + canonical request
    C->>C: Tính HMAC
    C->>S: Request + keyId + timestamp + nonce + signature
    S->>S: Tìm key và xác minh HMAC
    S->>S: Kiểm tra timestamp trong cửa sổ cho phép
    S->>R: Consume nonce atomically
    R-->>S: Nonce mới hoặc đã tồn tại
    S->>S: Authorization và xử lý request
    S-->>C: Response
~~~

### 6.1. Timestamp không đủ nếu đứng một mình

Timestamp giới hạn cửa sổ replay nhưng không ngăn gửi lại request nhiều lần trong cửa sổ đó. Nếu cửa sổ chấp nhận là vài phút, một request bị bắt có thể được phát lại trong khoảng thời gian đó.

Nonce cần được lưu theo phạm vi thích hợp, ví dụ key ID + nonce, với thao tác **check-and-insert nguyên tử**. Nếu hai bản sao tới đồng thời, chỉ một request được tiêu thụ nonce thành công. TTL của replay store phải bao phủ toàn bộ cửa sổ timestamp và clock skew cho phép.

### 6.2. Clock skew và đồng hồ

Client và server có thể lệch giờ. Policy cần quy định cửa sổ chấp nhận trước/sau thời điểm hiện tại và đồng bộ đồng hồ đáng tin. Cửa sổ quá rộng tăng cơ hội replay; quá hẹp làm client hợp lệ thất bại khi mạng chậm hoặc đồng hồ lệch.

Timestamp cần nằm trong phần được ký. Nếu server kiểm tra một timestamp ở header nhưng header đó không nằm trong canonical request, kẻ tấn công có thể thay timestamp mà MAC vẫn hợp lệ.

### 6.3. Nonce và idempotency key không giống nhau

Nonce chống việc **cùng một signed request** được chấp nhận nhiều lần. Idempotency key giúp xử lý retry của cùng một thao tác nghiệp vụ một cách nhất quán.

Ví dụ, client gửi POST tạo thanh toán nhưng không nhận được response vì mạng đứt. Nếu gửi lại với nonce mới, server có thể xác minh request mới nhưng vẫn cần biết đó là cùng một ý định thanh toán. Idempotency key được ký và lưu theo principal/operation để trả lại kết quả trước hoặc ngăn tạo giao dịch trùng.

Không dùng một idempotency key tĩnh thay nonce chống replay; cũng không xem nonce mới là đủ để ngăn duplicate business operation.

## 7. Key ID và ánh xạ danh tính

Request thường mang một **key ID** để server biết cần dùng secret nào. Key ID là định danh tra cứu, không phải bí mật và cũng không phải bằng chứng đã xác thực.

Một request minh họa:

~~~http
POST /v1/transfers?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: partner-042
X-Request-Timestamp: 2026-11-22T05:00:00Z
X-Request-Nonce: 7F2b9Kq8mX4p
Content-Digest: SHA-256=:BASE64_DIGEST:
Authorization: HMAC-SHA256 Signature=:BASE64_SIGNATURE:

{"amount":250000,"destination":"acct-1008"}
~~~

Đây là **header profile minh họa**, không phải chuẩn wire format. Server dùng key ID để tìm secret đang hoạt động, rồi mới xác minh MAC. Sau khi MAC hợp lệ, key ID được ánh xạ tới principal hoặc partner identity đã đăng ký.

Cần kiểm soát:

- Key ID có tồn tại, đang hoạt động và được phép gọi endpoint này không?
- Secret gắn với principal/tenant nào?
- Key được phép dùng cho scope, resource và môi trường nào?
- Key đã hết hạn, bị revoke hoặc đang trong giai đoạn rotation không?
- Có giới hạn IP/network hoặc yêu cầu mTLS bổ sung theo policy không?

Không dùng key ID để lấy principal trước rồi cấp quyền mà bỏ qua kiểm tra MAC. Principal chỉ được coi là đã xác thực sau khi chữ ký hợp lệ và các điều kiện request khác đạt.

## 8. Quy trình verify phía server

Một verifier nên có thứ tự kiểm tra rõ ràng để tránh side effect trước khi request được xác thực.

1. Parse request theo một HTTP parser và ingress policy nhất quán; từ chối request mơ hồ hoặc header trùng không được phép.
2. Kiểm tra kích thước, method, endpoint và giới hạn lưu lượng sơ bộ.
3. Đọc key ID; tra cứu key record trong kho quản lý secret, kiểm tra trạng thái và scope dự kiến.
4. Kiểm tra thuật toán theo allowlist phía server. Không để client tự chọn thuật toán yếu hoặc đổi algorithm.
5. Tạo canonical request theo đúng phiên bản profile và bytes thực tế đã nhận.
6. Tính HMAC với secret tương ứng.
7. Decode signature theo encoding quy định, kiểm tra độ dài và so sánh bằng hàm constant-time.
8. Kiểm tra timestamp và cửa sổ clock skew.
9. Tiêu thụ nonce nguyên tử để chống replay.
10. Ánh xạ key sang principal đã xác thực.
11. Chạy authorization cho principal, resource, action, tenant và business rules.
12. Chỉ sau khi mọi kiểm tra đạt mới thực hiện side effect; ghi audit không chứa secret/MAC nhạy cảm.

~~~mermaid
flowchart TD
    A[Nhận HTTP request] --> B[Parse nghiêm ngặt và giới hạn kích thước]
    B --> C[Lookup keyId và trạng thái key]
    C --> D[Build canonical request]
    D --> E[Compute expected HMAC]
    E --> F{MAC hợp lệ?}
    F -- Không --> X[Reject và audit an toàn]
    F -- Có --> G[Check timestamp]
    G --> H{Trong cửa sổ?}
    H -- Không --> X
    H -- Có --> I[Consume nonce atomically]
    I --> J{Nonce mới?}
    J -- Không --> X
    J -- Có --> K[Resolve principal]
    K --> L[Authorization]
    L --> M{Được phép?}
    M -- Không --> N[Deny]
    M -- Có --> O[Thực hiện request]
~~~

Thứ tự cụ thể có thể điều chỉnh để giảm DoS hoặc bảo vệ tài nguyên, nhưng **không thực hiện side effect trước khi MAC, freshness, replay và authorization được kiểm tra**. Một số metadata như timestamp có thể được kiểm tra sơ bộ trước HMAC để loại request rõ ràng hết hạn, nhưng chỉ tin giá trị đó sau khi nó đã được xác minh là thành phần được ký.

### 8.1. Constant-time comparison

Khi so sánh MAC, không dùng phép so sánh chuỗi thông thường có thể dừng ngay tại byte khác đầu tiên. Dùng hàm constant-time compare từ thư viện mật mã đáng tin cậy, sau khi kiểm tra encoding và độ dài phù hợp.

Constant-time comparison không sửa được mọi side channel của toàn bộ endpoint, nhưng loại bỏ một nguồn rò rỉ thời gian quan trọng trong bước so sánh MAC. Không tự viết hàm so sánh byte bằng vòng lặp nếu runtime hoặc thư viện đã cung cấp hàm an toàn.

### 8.2. Không thử nhiều thuật toán theo ý client

Server phải cấu hình allowlist thuật toán và phiên bản profile. Không nhận header algorithm tùy ý rồi chạy theo yêu cầu của client. Nếu hỗ trợ nhiều phiên bản, key record cần ràng buộc key với thuật toán/profile cụ thể và có kế hoạch ngừng phiên bản cũ.

## 9. Ví dụ pseudocode tạo chữ ký

Ví dụ khái niệm:

~~~text
function signRequest(request, keyRecord):
    timestamp = currentTime()
    nonce = secureRandomUniqueValue()

    bodyDigest = SHA256(request.exactBodyBytes)

    canonical = buildCanonicalRequest(
        version = "HMAC-REQUEST-V1",
        method = request.method,
        authority = request.authority,
        path = request.canonicalPath,
        query = request.canonicalQuery,
        signedHeaders = normalizeSignedHeaders(request.headers),
        contentDigest = base64(bodyDigest),
        timestamp = timestamp,
        nonce = nonce
    )

    mac = HMAC_SHA256(keyRecord.secret, UTF8(canonical))

    return attachSignatureHeaders(
        keyId = keyRecord.keyId,
        timestamp = timestamp,
        nonce = nonce,
        signature = base64url(mac)
    )
~~~

Pseudocode verifier:

~~~text
function verifyRequest(request):
    parsed = strictParse(request)
    keyRecord = keyStore.find(parsed.keyId)

    if keyRecord is missing or not keyRecord.active:
        reject()

    if not serverPolicy.allowsAlgorithm(keyRecord.algorithm):
        reject()

    canonical = buildCanonicalRequestFromReceivedBytes(parsed, keyRecord.profile)
    expected = HMAC_SHA256(keyRecord.secret, UTF8(canonical))
    supplied = decodeSignature(parsed.signature)

    if not constantTimeEqual(expected, supplied):
        reject()

    if not timestampWithinWindow(parsed.timestamp):
        reject()

    if not replayStore.consumeOnce(keyRecord.keyId, parsed.nonce):
        reject()

    principal = keyRecord.principal
    authorize(principal, parsed.resource, parsed.action)
    execute(parsed)
~~~

Đây là pseudocode để giải thích trách nhiệm, không phải thư viện HMAC production. Thực tế phải xử lý parser ambiguities, encoding, secret retrieval, concurrency, error mapping, body streaming, proxy rewriting, key versioning và audit.

## 10. Secret management và vòng đời key

HMAC an toàn phụ thuộc trực tiếp vào secret. Nếu secret bị lộ, kẻ tấn công có thể tạo request signature hợp lệ trong phạm vi key đó.

### 10.1. Cấp phát và lưu trữ

- Tạo secret bằng bộ sinh số ngẫu nhiên mật mã với độ dài phù hợp thuật toán và policy.
- Dùng key riêng cho từng client/partner hoặc trust domain; tránh một master secret dùng chung cho mọi tích hợp.
- Phân phối secret qua kênh bootstrap được xác thực, không gửi trong URL, ticket, chat log hoặc source control.
- Lưu secret trong secret manager/KMS/HSM hoặc kho được mã hóa và giới hạn quyền truy cập.
- Không log secret, raw Authorization header, signature base có dữ liệu nhạy cảm hoặc request body bí mật.
- Có inventory: key ID, owner, principal, scope, ngày cấp, hạn, trạng thái, phiên bản thuật toán và quy trình thu hồi.
- Tách khóa giữa development, staging và production.

HMAC verifier cần secret để tính lại MAC. Nếu nhiều verifier độc lập cùng biết secret, mỗi verifier đó đều có khả năng giả chữ ký. Với yêu cầu chỉ một bên được phép ký nhưng nhiều bên được phép xác minh, chữ ký bất đối xứng thường phù hợp hơn.

### 10.2. Rotation không gián đoạn

Một chiến lược rotation thường gồm:

1. Tạo key mới với key ID mới.
2. Cấu hình server chấp nhận key mới và key cũ trong khoảng chuyển đổi có giới hạn.
3. Cấp secret mới cho client qua kênh an toàn.
4. Chuyển client sang ký bằng key mới.
5. Theo dõi request key cũ và xác nhận client đã chuyển.
6. Ngừng chấp nhận key cũ, revoke và xóa secret theo policy.
7. Ghi audit và kiểm tra không còn client hợp lệ phụ thuộc key cũ.

Không nên dùng cùng một key ID cho hai secret đồng thời nếu làm verifier không thể xác định chính xác phiên bản. Nếu key cũ bị compromise, không chờ hết giai đoạn chuyển đổi thông thường: revoke khẩn cấp, đánh giá request giả mạo và xoay khóa liên quan.

### 10.3. Phân vùng và dẫn xuất key

Không tái sử dụng cùng một secret cho nhiều giao thức hoặc mục đích không liên quan. Nếu có nhu cầu dẫn xuất subkey, dùng KDF được thiết kế cho việc đó (ví dụ HKDF) với context/label tách biệt. Không tự tạo subkey bằng cách nối chuỗi tùy tiện rồi hash.

## 11. HMAC không thay TLS, authentication context hay authorization

HMAC và TLS giải quyết các vấn đề khác nhau:

| Cơ chế | Bảo đảm chính | Không tự bảo đảm |
| --- | --- | --- |
| **TLS/HTTPS** | Bảo vệ kênh và xác thực server theo PKI | Request được tạo bởi client cụ thể nếu không có client authentication |
| **HMAC request signature** | Integrity và proof of shared-secret possession trên thành phần được ký | Confidentiality, chống replay nếu thiếu state, danh tính con người, quyền truy cập |
| **mTLS** | Xác thực peer bằng certificate và proof of private-key possession trong TLS | Quyền nghiệp vụ của peer |
| **OAuth access token** | Truyền quyền được cấp tới resource server theo token profile | Tính toàn vẹn của body nếu không có cơ chế ký riêng; chống đánh cắp bearer token |
| **Authorization policy** | Quyết định principal được làm gì trên resource | Bằng chứng xác thực nếu principal chưa được xác minh |

Ngay cả khi ký request bằng HMAC, vẫn dùng TLS để bảo vệ body, headers, metadata, chống quan sát và giảm nguy cơ sửa đổi trong truyền tải. HMAC không mã hóa request; người nghe lén có thể đọc thông tin không nhạy cảm và thử replay nếu server thiếu kiểm soát.

Một request có MAC hợp lệ chỉ giúp xác thực key holder theo mapping. Server vẫn phải kiểm tra principal đó được phép thực hiện hành động hay không.

## 12. HMAC với webhook và API partner

Webhook là trường hợp phổ biến: provider gửi event tới endpoint của khách hàng. Provider ký body và metadata; receiver xác minh trước khi xử lý event.

Một webhook profile có thể ký:

- HTTP method và endpoint/path.
- Event ID.
- Timestamp.
- Digest của raw request body.
- Key ID hoặc phiên bản secret theo profile.

Receiver nên:

1. Giữ nguyên raw body bytes trước khi JSON parser biến đổi.
2. Tính lại digest và canonical request đúng profile.
3. Xác minh HMAC bằng secret của provider đã đăng ký.
4. Kiểm tra timestamp và event ID/nonce để ngăn replay.
5. Lưu event ID bằng thao tác nguyên tử để chống xử lý lặp.
6. Ánh xạ provider identity tới tenant/integration cụ thể.
7. Kiểm tra event type và business authorization trước khi cập nhật dữ liệu.

Không chỉ xác minh HMAC rồi thực hiện ngay mọi event. Một provider key có thể được cấp cho nhiều loại webhook; ứng dụng cần kiểm tra event có thuộc integration và trạng thái nghiệp vụ hiện tại hay không.

### 12.1. Webhook retry

Provider có thể gửi lại event khi receiver timeout hoặc trả lỗi. Chính sách idempotency cần xác định cách xử lý retry hợp lệ. Có thể xác minh chữ ký ở mọi lần nhận nhưng chỉ xử lý business event một lần dựa trên event ID đã được xác minh.

Nếu cùng event ID nhưng body khác, không coi đó là retry bình thường; cần từ chối và ghi nhận bất thường. Không tin event ID trước khi chữ ký hợp lệ.

## 13. Canonicalization và proxy: những lỗi nguy hiểm

HMAC thường thất bại do hai phía chuẩn hóa khác nhau. Những lỗi nghiêm trọng hơn có thể khiến verifier ký một nội dung nhưng backend thực thi nội dung khác.

| Lỗi | Ví dụ | Biện pháp |
| --- | --- | --- |
| Path rewrite sau verify | Gateway xác minh /v1/a, backend nhận /admin/a | Xác minh ở ranh giới có cùng request-target thực thi hoặc ký thông tin rewrite được bảo vệ |
| Query duplicate | Verifier lấy giá trị đầu, backend lấy giá trị cuối | Từ chối duplicate hoặc quy định một cách xử lý duy nhất |
| Header duplicate | Có hai Content-Length/Host hoặc header danh tính | Parser/ingress từ chối ambiguity; chuẩn hóa nhất quán |
| Body transform | Middleware giải nén hoặc đổi JSON trước khi verify | Hash raw bytes đúng ranh giới, hoặc định nghĩa representation chuẩn |
| Header không được ký | Backend dùng tenant header chưa được ký | Ký mọi thành phần ảnh hưởng quyết định hoặc lấy từ context nội bộ đáng tin |
| Timestamp không được ký | Đối thủ thay timestamp trong khi MAC còn đúng | Đưa timestamp vào canonical request |
| Thuật toán do client chọn | Client yêu cầu verifier dùng thuật toán yếu | Allowlist algorithm và gắn profile với key record |
| So sánh MAC không constant-time | Thời gian phản hồi phụ thuộc byte sai | Dùng hàm constant-time từ thư viện |
| Nonce không atomic | Hai bản sao cùng vượt qua check rồi cùng chạy | Atomic consume-once hoặc unique constraint |
| Key dùng chung toàn hệ thống | Một partner bị lộ làm lộ mọi integration | Key riêng theo client/trust domain và scope tối thiểu |

### 13.1. Ranh giới xác minh và thực thi

Một câu hỏi quan trọng: **thành phần nào xác minh chữ ký và thành phần nào thực thi request?** Nếu gateway xác minh nhưng backend tự parse lại request theo quy tắc khác, có thể phát sinh chênh lệch.

Có thể chọn một trong các cách:

- Verify tại backend cuối cùng trên đúng bytes/representation mà backend sẽ xử lý.
- Gateway verify và chuyển tiếp một assertion nội bộ có chữ ký, ràng buộc method, path, body digest, principal, audience và thời hạn; backend chỉ nhận assertion từ gateway đã chứng thực.
- Dùng một chuẩn message signature và kiến trúc proxy/intermediary có quy tắc rõ về covered components.

Không để backend tin header danh tính hoặc trạng thái signature do client gửi trực tiếp.

## 14. Phản hồi lỗi và audit

Không nên tiết lộ chi tiết giúp kẻ tấn công biết key ID nào tồn tại, MAC sai ở byte nào hoặc nonce đã dùng của partner nào. Response bên ngoài có thể dùng lỗi chung như unauthorized/invalid signature, trong khi audit nội bộ ghi mã lý do cụ thể.

Sự kiện audit hữu ích:

- request_signature.accepted / request_signature.rejected.
- request_signature.key_unknown hoặc key_revoked.
- request_signature.timestamp_out_of_window.
- request_signature.replay_detected.
- request_signature.key_rotated / request_signature.key_revoked.
- request_signature.authorization_denied.

Nên ghi key ID, principal nội bộ nếu đã xác minh, endpoint, method, thời điểm, correlation ID và reason code đã được kiểm soát. Không log secret, raw signature header, full body nhạy cảm hoặc dữ liệu cá nhân không cần thiết.

Khi phát hiện replay hoặc MAC thất bại tăng đột biến, kiểm tra clock drift, deployment mismatch, key rotation, proxy rewriting, request smuggling và khả năng secret bị lộ. Không tự động tắt signature verification để khôi phục dịch vụ; dùng fallback chỉ khi đã được policy thiết kế và có giới hạn rõ.

## 15. Chọn HMAC hay chữ ký bất đối xứng?

HMAC là lựa chọn đơn giản, hiệu quả khi số bên tham gia có thể giữ secret và tin cậy lẫn nhau. Nhưng mô hình shared secret có giới hạn: mọi verifier biết secret đều có khả năng ký.

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Hai backend do cùng tổ chức vận hành | HMAC với secret riêng hoặc mTLS | Quản lý trust domain và rotation tập trung |
| Partner server-to-server | HMAC key riêng theo partner hoặc mTLS | Có thể cấp/revoke credential theo integration |
| Nhiều bên chỉ cần xác minh, một bên ký | Chữ ký bất đối xứng | Verifier chỉ cần public key, không có khả năng ký |
| Browser/mobile public client | OAuth/OIDC với PKCE, passkey hoặc proof-of-possession phù hợp | Không thể giữ một shared secret cố định trong client phân phối rộng |
| Workload identity trong mesh | mTLS hoặc workload credential ngắn hạn | Có danh tính peer và quản lý vòng đời khóa |
| Webhook provider ký event | HMAC hoặc asymmetric signature theo chuẩn của provider | Receiver xác minh event, timestamp và replay |
| Yêu cầu chống giả mạo giữa các tổ chức độc lập | Chữ ký bất đối xứng có thể phù hợp hơn | Giảm việc phải chia sẻ secret xác minh |

Nếu dùng HMAC, xác định rõ ai được giữ secret, ai có quyền ký, key gắn với principal nào và hậu quả khi một bên bị compromise. Nếu cần bằng chứng mà bên xác minh không thể tự tạo, dùng chữ ký bất đối xứng.

## 16. Ưu tiên chuẩn hóa thay vì tự tạo giao thức

Một custom HMAC profile có thể phù hợp với hệ thống đơn giản, nhưng càng nhiều client, proxy và bên tích hợp thì rủi ro canonicalization càng lớn. Khi cần interoperability, cân nhắc:

- **HTTP Message Signatures (RFC 9421):** chuẩn hóa cách tạo và xác minh signature trên các thành phần của HTTP message, gồm covered components và signature parameters.
- **Content-Digest (RFC 9530):** chuẩn hóa biểu diễn digest nội dung HTTP khi cần bảo vệ content.
- **AWS Signature Version 4:** ví dụ về một profile ký request có canonical request, credential scope, timestamp và key derivation trong hệ sinh thái AWS; chỉ dùng đúng đặc tả của dịch vụ tương ứng.
- **OAuth 2.0 DPoP:** cơ chế proof-of-possession cho token trong một số kiến trúc OAuth; không đồng nghĩa HMAC request signing tùy ý.

Không trộn các format hoặc tự lấy một phần quy tắc từ nhiều chuẩn rồi gọi là tương thích. Chọn một profile cụ thể, kiểm tra phiên bản và dùng thư viện được duy trì. Nếu custom, version hóa canonicalization và tạo bộ test vector dùng chung cho client/server.

## 17. Checklist review HMAC request authentication

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| HMAC dùng cho trust relationship nào? | Có danh sách client, principal, owner và phạm vi |
| Thuật toán có được cố định? | Allowlist phía server, không tin algorithm do request chọn |
| Secret có đủ ngẫu nhiên và riêng biệt? | Key riêng theo client/trust domain, không hard-code trong public app |
| Canonical request có đặc tả chính xác? | Method, authority, path, query, headers và encoding nhất quán |
| Body có được bảo vệ? | Digest của đúng bytes hoặc canonical representation đã định nghĩa |
| Timestamp và nonce có được ký? | Nằm trong canonical request và có TTL/window |
| Replay store có atomic? | Check-and-consume một lần, TTL bao phủ cửa sổ chấp nhận |
| Retry có idempotency? | Idempotency key riêng, được ký và ràng buộc nghiệp vụ |
| MAC được so sánh an toàn? | Decode/length check và constant-time comparison |
| Key ID ánh xạ đúng principal? | Key active, scope, tenant, expiry và revoke được kiểm tra |
| Proxy có thay đổi request? | Xác định rõ verify boundary và representation thực thi |
| Authorization có tách biệt? | MAC hợp lệ chỉ xác thực key holder; policy kiểm tra resource/action |
| TLS có còn được dùng? | HTTPS bảo vệ confidentiality và transport |
| Rotation/revoke có vận hành được? | Overlap có thời hạn, key version, emergency revoke |
| Có audit mà không lộ bí mật? | Reason code, key ID và correlation; không log secret/MAC/body nhạy cảm |
| Có test vector và negative tests? | Client/server dùng chung canonicalization vectors, test replay và tampering |

### Tình huống tự kiểm tra

**Tình huống 1:** Một request có HMAC hợp lệ nhưng timestamp không nằm trong phần được ký. Có thể tin timestamp để chống replay không?

**Trả lời:** Không. Đối thủ có thể thay timestamp mà MAC vẫn hợp lệ. Timestamp phải là thành phần của canonical request.

**Tình huống 2:** Server kiểm tra nonce bằng thao tác đọc rồi sau đó ghi riêng. Hai bản sao request tới đồng thời có thể cùng được chấp nhận không?

**Trả lời:** Có. Check-and-consume phải nguyên tử, chẳng hạn unique constraint hoặc thao tác atomic trong replay store.

**Tình huống 3:** HMAC hợp lệ cho request tạo thanh toán được gửi lại với nonce mới. Nonce có đủ ngăn thanh toán trùng không?

**Trả lời:** Không. Nonce chống replay cùng signed request; idempotency key và business state cần ngăn một ý định thanh toán bị thực hiện hai lần.

**Tình huống 4:** Browser app dùng chung một HMAC secret nhúng trong JavaScript. Có thể coi request được xác thực an toàn không?

**Trả lời:** Không. Secret có thể bị trích xuất từ client phân phối rộng. Dùng cơ chế phù hợp public client như OAuth/PKCE, passkey hoặc chữ ký khóa riêng được quản lý an toàn.

**Tình huống 5:** MAC hợp lệ và certificate/secret thuộc partner A. Có được cho partner A gọi mọi endpoint không?

**Trả lời:** Không. Key identity chỉ xác định partner; authorization vẫn kiểm tra scope, resource, action, tenant và business rules.

## 18. Ghi nhớ

**Request signature** dùng HMAC để ràng buộc một HTTP request với secret của client và bảo vệ tính toàn vẹn của những thành phần đã ký. Một thiết kế đáng tin cần canonical request nhất quán, body digest đúng bytes, timestamp và nonce được ký, replay store atomic, constant-time comparison và key management có vòng đời.

HMAC không mã hóa request, không tự chống replay và không cấp quyền. Luôn dùng TLS, ánh xạ key ID tới principal sau khi MAC hợp lệ, kiểm tra authorization riêng và bảo vệ secret khỏi client public. Khi triển khai qua nhiều proxy hoặc đối tác, ưu tiên chuẩn message signature có test vector rõ ràng; nếu dùng custom profile, version hóa và kiểm thử mọi khác biệt canonicalization trước khi đưa vào production.
