# Canonical request

Trong xác thực request bằng HMAC, **canonical request** là biểu diễn chuẩn hóa của một HTTP request theo quy tắc đã thống nhất giữa client và server. Client tạo chuỗi canonical từ method, đường dẫn, query, header và nội dung request; sau đó dùng khóa bí mật tính HMAC trên chuỗi này. Server tự xây dựng lại canonical request từ request nhận được, tính HMAC và so sánh với chữ ký client gửi.

Mục đích của canonical request là làm cho hai bên ký và xác minh **cùng một thông điệp logic**, kể cả khi HTTP có những khác biệt biểu diễn như chữ hoa/chữ thường ở tên header, khoảng trắng hoặc thứ tự tham số query. Nếu hai bên chuẩn hóa khác nhau, request hợp lệ có thể bị từ chối; nguy hiểm hơn, nếu chuẩn hóa mơ hồ hoặc bỏ sót thành phần quan trọng, attacker có thể thay đổi request mà chữ ký vẫn được chấp nhận.

Bài này thuộc chương **HMAC request authentication** trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Người học sẽ biết cách xây dựng canonical request ổn định, chọn thành phần cần ký, xử lý URI/query/header/body, tránh lỗi parser và request smuggling, thiết kế chữ ký có timestamp/nonce để chống replay, cùng cách kiểm thử tương thích client-server.

## 1. Vì sao cần canonical request?

HTTP request có nhiều thành phần:

- Method như `GET`, `POST`, `PATCH`.
- Request target gồm path và query.
- Header như `Host`, `Content-Type`, `Content-Encoding`.
- Body có thể là JSON, form, binary hoặc rỗng.
- Ngữ cảnh xác thực như key ID, timestamp, nonce và tên thuật toán.

Một số khác biệt biểu diễn không làm thay đổi ý nghĩa theo quy tắc giao thức, nhưng một số khác biệt lại làm thay đổi cách server định tuyến hoặc xử lý. Ví dụ, tên header không phân biệt chữ hoa/chữ thường theo HTTP, trong khi path, query parameter trùng lặp và cách percent-decode có thể ảnh hưởng ý nghĩa endpoint.

Nếu client ký trực tiếp chuỗi request tùy ý, server có thể không tái tạo được đúng byte sequence để xác minh. Canonicalization tạo ra một **serialization xác định (deterministic)**: cùng một request logic theo giao thức phải tạo ra cùng chuỗi canonical ở cả hai phía.

### 1.1. Ví dụ đơn giản

Giả sử client gửi:

```http
POST /v1/certificates?course=java&tenant=org-7 HTTP/1.1
Host: api.example.org
Content-Type: application/json
X-Client-Date: 2026-11-22T05:00:00Z

{"learnerId":"usr-57","courseId":"java"}
```

Client và server có thể thống nhất canonical request gồm:

1. HTTP method viết hoa.
2. Path theo quy tắc encoding và normalization được quy định.
3. Query được parse, encode và sắp xếp theo quy tắc.
4. Header được chọn, đổi tên thành chữ thường, chuẩn hóa giá trị và sắp xếp.
5. Danh sách header đã ký.
6. Hash của body theo byte sequence đã nhận.

Ví dụ này chỉ minh họa cấu trúc. **Không có một định dạng canonical request phổ quát cho mọi hệ thống HMAC.** AWS Signature Version 4, HTTP Message Signatures và giao thức nội bộ có quy tắc khác nhau. Client và server phải triển khai đúng cùng một profile; không tự pha trộn quy tắc của nhiều giao thức.

### 1.2. Canonicalization không phải mã hóa

Canonical request không che giấu dữ liệu. Nó tạo biểu diễn chuẩn để ký. HMAC cung cấp kiểm tra toàn vẹn và xác thực bên nắm giữ khóa bí mật; nó không mã hóa body, không che URL/header và không thay thế TLS.

## 2. Cấu trúc canonical request

Một profile đơn giản có thể định nghĩa canonical request gồm các trường theo đúng thứ tự và phân cách bằng newline:

```text
HTTP_METHOD
CANONICAL_PATH
CANONICAL_QUERY
CANONICAL_HEADERS
SIGNED_HEADERS
PAYLOAD_HASH
```

Ví dụ:

```text
POST
/v1/certificates
course=java&tenant=org-7
content-type:application/json
host:api.example.org
x-client-date:2026-11-22T05:00:00Z
content-type;host;x-client-date
<hex-sha256-of-body>
```

Các dòng trên chỉ là **profile minh họa**. Trong triển khai thật, cần quy định rõ:

- Dùng LF (`\\n`) hay CRLF (`\\r\\n`) làm separator trong chuỗi canonical.
- Có newline cuối hay không.
- Encoding của chuỗi canonical, thường là UTF-8.
- Quy tắc xử lý byte ngoài ASCII, Unicode và percent-encoding.
- Cách biểu diễn body rỗng.
- Cách xử lý header trùng lặp, query parameter trùng lặp và giá trị trống.
- Những header bắt buộc phải ký và những header không được phép ảnh hưởng quyết định nghiệp vụ.

**Thứ tự trường, separator và encoding là một phần của giao thức.** Không thể để mỗi ngôn ngữ lập trình tự chọn cách serialize rồi hy vọng HMAC khớp.

## 3. Canonicalize HTTP method

Method xác định hành động HTTP và phải được đưa vào chữ ký. Ví dụ `GET`, `POST`, `PUT`, `DELETE` không thể hoán đổi mà giữ nguyên chữ ký.

Một profile có thể yêu cầu method được chuyển thành chữ hoa ASCII:

```text
get  -> GET
post -> POST
PATCH -> PATCH
```

HTTP method token có quy tắc chữ hoa/chữ thường theo cách triển khai và server; không nên tự ý thay đổi method ở proxy hoặc middleware sau khi đã xác minh chữ ký.

Các nguyên tắc:

- Lấy method từ request đã được HTTP server parse, không lấy từ một header client tự khai.
- Canonicalize theo quy tắc cố định, ví dụ uppercase ASCII nếu profile yêu cầu.
- Ký method thực sự được router sử dụng.
- Không cho middleware xác minh `GET` nhưng handler cuối cùng xử lý một method khác do rewrite.
- Nếu hỗ trợ method mở rộng, định nghĩa chính xác cách giữ hoặc chuẩn hóa token đó.

Nếu method bị bỏ khỏi canonical request, attacker có thể thử thay đổi loại thao tác trong khi những phần khác giữ nguyên. Nếu hai lớp trong server diễn giải method khác nhau, cần sửa parser/routing thay vì chỉ thêm một phép biến đổi chuỗi.

## 4. Canonicalize path và request target

Path thường là phần dễ gây sai khác vì URL có percent-encoding, dấu gạch chéo, Unicode, dấu chấm và các proxy có thể rewrite.

### 4.1. Không tự chuẩn hóa theo trực giác

Các dạng sau có thể được một số thư viện diễn giải khác nhau:

```text
/v1/users/alice
/v1/users/%61lice
/v1/a/../users/alice
/v1//users/alice
/v1/files/a%2Fb
/v1/files/a/b
```

Không được mặc định tất cả dạng trên tương đương. Đặc biệt, encoded slash (`%2F`), dot-segment (`.`, `..`) và double slash có thể ảnh hưởng định tuyến hoặc kiểm soát quyền.

Một hệ thống an toàn cần thống nhất **cùng một parser và cùng một representation** giữa bước xác minh chữ ký, router và middleware authorization. Nếu reverse proxy decode path rồi backend decode lần nữa, request có thể được xác minh theo một path nhưng xử lý theo path khác.

### 4.2. Quy tắc path cần định nghĩa

Một profile canonical path nên trả lời:

1. Dùng raw request target hay path đã được HTTP framework parse?
2. Percent-encoding có được giữ nguyên, chuẩn hóa hex digits hay decode những ký tự nào?
3. Có loại bỏ dot-segment không? Nếu có, tại lớp nào và theo chuẩn nào?
4. Có giữ dấu slash cuối, double slash và encoded slash không?
5. Unicode được biểu diễn bằng UTF-8 percent-encoding hay một dạng chuẩn hóa khác?
6. Proxy/gateway có thể rewrite path trước hoặc sau xác minh không?

Thông thường nên tránh những phép decode/normalize tùy tiện. Một lựa chọn an toàn là định nghĩa rõ canonicalization theo chuẩn URI/profile đã chọn, từ chối request có representation mơ hồ hoặc không hợp lệ, và đảm bảo router dùng cùng kết quả đã xác minh.

### 4.3. Path và authorization phải cùng một ngữ nghĩa

Giả sử HMAC được xác minh trên `/v1/users/%2e%2e/admin`, nhưng router decode và rút gọn thành `/admin`. Nếu authorization dựa trên path đã chuẩn hóa khác với path đã ký, chữ ký không bảo vệ đúng hành động.

**Quy tắc:** thành phần dùng để xác minh HMAC, định tuyến và quyết định quyền phải có cùng một cách diễn giải request target. Nếu không thể đảm bảo, từ chối request thay vì đoán.

## 5. Canonicalize query string

Query string có thể có thứ tự khác nhau, key lặp, value rỗng, dấu `+`, ký tự percent-encoded và ký tự Unicode. Client/server phải thống nhất chính xác cách chuyển query thành canonical form.

### 5.1. Sắp xếp và encoding

Một profile thường có thể:

1. Parse query thành danh sách cặp key-value, giữ cả các key trùng.
2. Percent-decode theo quy tắc URL đã chọn.
3. Percent-encode key và value theo một bộ ký tự cho phép cố định.
4. Sắp xếp theo byte/chuỗi đã encode, có quy tắc tie-break cho key trùng.
5. Nối mỗi cặp bằng `=` và các cặp bằng `&`.

Ví dụ, với profile giả định:

```text
Raw query:
z=last&course=java&tag=b&tag=a&empty=&flag

Canonical query:
course=java&empty=&flag=&tag=a&tag=b&z=last
```

Ví dụ trên chọn quy tắc rằng tham số không có dấu `=` được biểu diễn thành value rỗng và duplicate `tag` được sắp xếp theo value. Một giao thức khác có thể giữ thứ tự duplicate hoặc phân biệt các trường hợp khác. **Không được áp dụng ví dụ này nếu profile thực tế quy định khác.**

### 5.2. Các trường hợp phải kiểm thử

| Input | Câu hỏi canonicalization |
| --- | --- |
| `a=1&a=2` | Giữ cả hai giá trị? Thứ tự có ý nghĩa không? |
| `a=` và `a` | Có được xem là tương đương hay không? |
| `q=a+b` và `q=a%20b` | Dấu cộng có nghĩa dấu cách theo form encoding hay là ký tự cộng? |
| `x=%2f` và `x=%2F` | Hex digits trong percent-encoding được chuẩn hóa thế nào? |
| `name=%C3%A1` | Byte UTF-8 được giữ/encode theo quy tắc nào? |
| `a=1&b=2` và `b=2&a=1` | Thứ tự tham số có bị bỏ qua theo profile không? |
| `a=1&&b=2` | Thành phần rỗng ở giữa có bị từ chối hay bỏ qua? |

Không dùng một hàm parse query chung rồi mặc định kết quả phù hợp với mọi framework. Nhiều thư viện có quy tắc riêng cho `+`, duplicate key, empty value và Unicode.

### 5.3. Duplicate parameter là nguồn gây mơ hồ

Nếu signature middleware đọc giá trị đầu tiên của `role=reader&role=admin`, còn business handler đọc giá trị cuối cùng, hai lớp có thể đưa ra quyết định khác nhau. HMAC vẫn hợp lệ trên canonical form của middleware, nhưng handler sử dụng giá trị khác.

Cách xử lý:

- Chọn một quy tắc duplicate parameter và áp dụng ở mọi lớp.
- Với tham số không được phép lặp, từ chối khi xuất hiện nhiều lần.
- Nếu duplicate được phép, ký đầy đủ danh sách và bảo đảm handler sử dụng chính danh sách đó theo cùng thứ tự/quy tắc.
- Không âm thầm chuyển query thành map nếu map làm mất giá trị lặp.
- Kiểm thử proxy, gateway, framework và application parser cùng một bộ test vector.

## 6. Canonicalize headers

HTTP header names không phân biệt chữ hoa/chữ thường. Header values lại có thể có whitespace, danh sách giá trị, duplicate field và quy tắc riêng theo từng header.

Một canonical header profile thường:

- Chọn một tập header bắt buộc phải ký.
- Chuyển tên header thành lowercase ASCII.
- Chuẩn hóa khoảng trắng theo quy tắc được định nghĩa.
- Sắp xếp header theo tên.
- Biểu diễn duplicate header theo quy tắc của profile.
- Ghi danh sách signed header names để server biết những header nào đã được bảo vệ.

Ví dụ:

```http
Host: api.example.org
Content-Type: application/json
X-Request-Date: 2026-11-22T05:00:00Z
X-Tenant-ID: org-7
```

Có thể tạo canonical headers:

```text
content-type:application/json
host:api.example.org
x-request-date:2026-11-22T05:00:00Z
x-tenant-id:org-7
```

Danh sách:

```text
content-type;host;x-request-date;x-tenant-id
```

Đây là profile minh họa. Một giao thức có thể yêu cầu header cụ thể, chẳng hạn `host`, `date`, `content-digest`, hoặc có quy tắc chuẩn hóa khác.

### 6.1. Header nào nên được ký?

Các header ảnh hưởng đến định tuyến, body parsing, tenant, nội dung và ngữ cảnh bảo mật thường cần được xem xét. Ví dụ:

- `host` hoặc authority: ràng buộc request với dịch vụ đích.
- `content-type`: ràng buộc cách diễn giải body.
- `content-encoding`: ràng buộc việc giải nén body.
- `content-digest` hoặc payload hash: ràng buộc nội dung.
- Timestamp/date và nonce: ràng buộc thời gian/giao dịch.
- Header tenant hoặc idempotency nếu chúng ảnh hưởng tới quyết định nghiệp vụ.

Không cần ký mọi header một cách máy móc. Các header hop-by-hop như `Connection`, `Transfer-Encoding` hoặc metadata do proxy tự thêm có thể thay đổi trên đường truyền; cần xử lý theo giao thức và topology. Điều quan trọng là **mọi header ảnh hưởng đến hành động hoặc diễn giải request phải được bảo vệ hoặc được kiểm soát độc lập**.

### 6.2. Duplicate header và whitespace

Ví dụ:

```http
X-Tenant-ID: org-7
x-tenant-id: org-9
```

Nếu proxy gộp hai header thành một chuỗi còn application lấy header đầu tiên, hai bên có thể hiểu tenant khác nhau. Không nên chỉ lowercase rồi nối chuỗi một cách tùy tiện.

Hãy quy định:

- Header nào chỉ được xuất hiện một lần.
- Header nào có thể lặp và cách kết hợp giá trị.
- OWS (optional whitespace) được loại bỏ ở đâu.
- Dấu phẩy trong giá trị là separator theo ngữ nghĩa header hay ký tự dữ liệu.
- Có từ chối header trùng lặp hoặc mơ hồ không.

Với header định danh, tenant, content length, host và các header bảo mật, từ chối duplicate/ambiguous representation thường an toàn hơn là tự đoán.

## 7. Canonicalize body và payload hash

HMAC cần ràng buộc với nội dung body nếu body ảnh hưởng đến thao tác. Một cách phổ biến là tính hash của **byte sequence body** rồi đưa giá trị hash vào canonical request.

Ví dụ:

```text
payload_hash = SHA-256(raw_body_bytes)
payload_hash_hex = lowercase_hex(payload_hash)
```

Canonical request có thể chứa `payload_hash_hex`, sau đó HMAC được tính trên toàn bộ canonical string.

### 7.1. Hash byte, không hash JSON đã parse rồi serialize tùy ý

Hai JSON document sau có thể có cùng ý nghĩa ở cấp dữ liệu nhưng byte sequence khác nhau:

```json
{"name":"Mai","active":true}
```

```json
{
  "active": true,
  "name": "Mai"
}
```

Nếu giao thức yêu cầu hash raw body, hai body này có hash khác nhau. Client và server phải hash cùng byte sequence thực tế được truyền. Không để client ký JSON compact còn server parse rồi serialize lại với thứ tự field khác.

Nếu muốn ký một biểu diễn JSON canonical, phải chọn chuẩn canonical JSON rõ ràng, áp dụng đúng chuẩn đó ở cả hai phía và tránh các khác biệt như số, Unicode, duplicate property name hoặc escaping. Đối với HTTP request signing, hash raw body bytes thường dễ xác định hơn nếu transport và middleware giữ nguyên byte sequence.

### 7.2. Compression và content encoding

Nếu request có `Content-Encoding: gzip`, cần xác định hash được tính trên compressed bytes hay decoded representation. Hệ thống phải ký header content encoding và quy định chính xác lớp nào tính digest. Nếu proxy tự giải nén rồi backend hash body đã giải nén, trong khi client ký compressed bytes, chữ ký sẽ không khớp; nếu các lớp diễn giải không đồng nhất, có thể phát sinh lỗ hổng.

Một nguyên tắc là xác minh chữ ký tại lớp có quyền truy cập đúng byte representation mà giao thức quy định, sau đó đảm bảo downstream xử lý cùng nội dung đã được xác minh. Không để body bị biến đổi giữa lúc xác minh và xử lý nghiệp vụ.

### 7.3. Body rỗng và body streaming

Với body rỗng, profile cần quy định hash của chuỗi byte rỗng, không bỏ trường payload hash tùy tiện. Với body lớn/streaming, có thể cần digest header, trailer hoặc cơ chế chunk signing; phải theo giao thức hỗ trợ. Không đọc một phần body để xác minh nhưng xử lý toàn bộ body khác với phần đã ký.

## 8. Từ canonical request đến HMAC signature

Sau khi tạo canonical request, client tính HMAC với secret key theo thuật toán được cấu hình, thường là HMAC-SHA-256 trong một giao thức mới:

```text
canonical_request = serializeCanonicalRequest(request)
signature = HMAC-SHA-256(secret_key, UTF8(canonical_request))
signature_hex = lowercase_hex(signature)
```

Server tự tạo canonical request từ request nhận được và tính lại HMAC. So sánh chữ ký bằng hàm **constant-time comparison** để tránh timing side-channel; đồng thời kiểm tra key ID, trạng thái key, thuật toán và timestamp.

Một header giả định:

```http
Authorization: HMAC keyId="client-42", algorithm="hmac-sha256", headers="content-type;host;x-request-date", signature="<hex-signature>"
X-Request-Date: 2026-11-22T05:00:00Z
```

Đây là cú pháp minh họa, không phải chuẩn HTTP chung. Không tự phát minh header format trong một sản phẩm đã có giao thức tương thích; nếu xây giao thức riêng, cần versioning, test vector và review bảo mật.

### 8.1. Pseudocode phía client

```text
signRequest(request, key):
    bodyBytes = serializeBodyExactlyOnce(request.body)
    payloadHash = SHA256(bodyBytes)

    canonical = canonicalize(
        method = request.method,
        rawTarget = request.rawTarget,
        selectedHeaders = request.headers,
        payloadHash = payloadHash,
        profileVersion = "v1"
    )

    signature = HMAC_SHA256(key.secret, UTF8(canonical))

    return request.withBody(bodyBytes).withSignature(
        keyId = key.id,
        profile = "v1",
        signature = base64url(signature)
    )
```

Client phải ký chính body bytes mà nó gửi. Nếu serialize body lại sau khi ký, body có thể khác chữ ký.

### 8.2. Pseudocode phía server

```text
verifyRequest(request):
    key = lookupKeyById(request.signature.keyId)
    require key exists and key.status == "active"
    require key.algorithm == "HMAC-SHA-256"
    require key.profileVersion is accepted

    verifyTimestampAndReplayContext(request, key)

    bodyBytes = readBoundedRawBody(request)
    payloadHash = SHA256(bodyBytes)

    canonical = canonicalizeUsingTrustedProfile(
        method = request.method,
        rawTarget = request.rawTarget,
        selectedHeaders = request.headers,
        payloadHash = payloadHash,
        profileVersion = key.profileVersion
    )

    expected = HMAC_SHA256(key.secret, UTF8(canonical))
    supplied = decodeSignatureStrictly(request.signature.value)

    require constantTimeEqual(expected, supplied)
    markNonceConsumedAtomically(request.nonce, key.id)
    passVerifiedBodyToHandler(bodyBytes)
```

Pseudocode nhấn mạnh thứ tự: xác định key/profile đáng tin, kiểm tra timestamp/replay, đọc body có giới hạn, canonicalize, tính HMAC, so sánh constant-time và chỉ chuyển tiếp đúng body đã xác minh. Triển khai thật cần xử lý lỗi, giới hạn kích thước, timeout, concurrency và việc tiêu thụ nonce nguyên tử.

## 9. Replay protection và ràng buộc request

HMAC xác minh request được tạo bởi bên biết secret, nhưng nếu attacker lấy được một request đã ký, họ có thể gửi lại nguyên request đó. Chữ ký hợp lệ không tự chứng minh request là mới.

Để giảm replay:

- **Timestamp:** Ký timestamp/date và từ chối request ngoài cửa sổ thời gian cho phép.
- **Nonce:** Client tạo giá trị ngẫu nhiên duy nhất; server lưu hoặc cache nonce đã dùng theo key và cửa sổ hiệu lực.
- **Request ID/idempotency key:** Dùng cho thao tác nghiệp vụ cần đảm bảo xử lý một lần hoặc có thể retry an toàn.
- **Body digest:** Ràng buộc nội dung body với chữ ký.
- **Method/path/query/authority:** Ràng buộc request với đúng hành động và dịch vụ đích.
- **Key status/rotation:** Cho phép vô hiệu hóa key bị lộ.

Timestamp không đủ một mình: trong cửa sổ chấp nhận, attacker vẫn có thể phát lại. Nonce phải được kiểm tra và đánh dấu đã dùng **nguyên tử**, nếu hai request đồng thời dùng cùng nonce thì chỉ một request được chấp nhận. Nếu hệ thống nhiều node, trạng thái replay cần được chia sẻ hoặc có cơ chế phân vùng nhất quán phù hợp.

Với thao tác không idempotent như phát hành chứng chỉ hoặc trừ tiền, cần thêm idempotency ở tầng nghiệp vụ. Chống replay của chữ ký và idempotency của nghiệp vụ là hai kiểm soát khác nhau.

## 10. Request smuggling và parser differential

Một rủi ro lớn của canonical request là **client, proxy, signature middleware và application handler có thể hiểu cùng một request theo cách khác nhau**. Đây là parser differential; trong một số tình huống nó góp phần tạo HTTP request smuggling hoặc bypass authorization.

Ví dụ các điểm cần chú ý:

- Nhiều `Content-Length` hoặc xung đột giữa `Content-Length` và `Transfer-Encoding`.
- Header trùng lặp hoặc được gộp khác nhau qua proxy.
- Path percent-encoding được decode một lần ở gateway và lần thứ hai ở backend.
- Duplicate query parameters được parser đầu chọn giá trị đầu, parser sau chọn giá trị cuối.
- `Host` và authority của HTTP/2 hoặc HTTP/3 không được ánh xạ nhất quán khi chuyển sang HTTP/1.1.
- Body bị decompress, transcode hoặc thay đổi trước khi handler xử lý.

Biện pháp:

1. Dùng HTTP parser và gateway đã được cập nhật, cấu hình rõ; từ chối message framing mơ hồ.
2. Xác minh chữ ký tại ranh giới có cùng representation với handler hoặc truyền một đối tượng request đã xác minh, không parse lại theo quy tắc khác.
3. Loại bỏ header client tự khai dành riêng cho proxy; proxy thiết lập lại header tin cậy trên kết nối đã xác thực.
4. Từ chối duplicate header/query ở những trường bảo mật nếu không có quy tắc xử lý rõ.
5. Kiểm thử end-to-end qua toàn bộ proxy, load balancer, middleware và router, không chỉ unit test canonicalizer.
6. Không cho phép downstream sửa method, path, tenant hoặc body sau xác minh mà không xác minh lại chữ ký hoặc kiểm soát tương đương.

Canonicalization không thể sửa một kiến trúc mà các lớp xử lý request không thống nhất. **Một representation được xác minh phải là representation được thực thi.**

## 11. Versioning và khả năng tương thích canonicalization

Canonicalization là một phần giao thức. Nếu thay đổi cách sort query, chuẩn hóa path hoặc danh sách header, chữ ký cũ có thể không còn hợp lệ.

Nên định nghĩa:

- **Profile/version ID:** Ví dụ `canonical-v1`, được client và server hiểu giống nhau.
- **Algorithm ID:** Chẳng hạn `hmac-sha256`; không cho client tự chọn thuật toán yếu hoặc không được hỗ trợ.
- **Signed header set:** Có danh sách rõ và không cho client bỏ header bắt buộc.
- **Encoding/separator:** UTF-8, LF, thứ tự trường và quy tắc byte chính xác.
- **Key metadata:** Key ID gắn với tenant/client, profile và trạng thái.
- **Migration:** Cho phép thời gian chuyển tiếp có giới hạn, tránh fallback không an toàn.

Không thử nhiều canonicalization profiles cho đến khi một profile nào đó khớp nếu điều đó cho phép attacker lợi dụng parser ambiguity. Server nên chọn profile từ metadata key hoặc cấu hình đã tin cậy, rồi xác minh đúng một cách.

## 12. Kiểm thử canonical request

Một canonicalizer tốt cần test vector dùng chung cho nhiều ngôn ngữ client/server. Mỗi vector nên chứa raw request, các thành phần đã canonicalize, canonical string byte-for-byte, payload hash và kết quả HMAC mong đợi.

### 12.1. Nhóm test cần có

| Nhóm | Input/thay đổi | Kết quả mong đợi |
| --- | --- | --- |
| Method | Đổi `GET` thành `POST`. | Chữ ký không còn hợp lệ. |
| Path | Đổi segment, encoded slash hoặc dot-segment. | Chữ ký sai hoặc request bị từ chối theo profile. |
| Query order | Đổi thứ tự tham số không lặp. | Nếu profile quy định sort, canonical string giữ nguyên; nếu không, phải khác. |
| Duplicate query | Thêm key trùng hoặc đổi thứ tự giá trị. | Áp dụng quy tắc duplicate; không parser nào được mất dữ liệu. |
| Header case | Đổi `X-Date` thành `x-date`. | Nếu tên header canonical lowercase, chữ ký giữ nguyên. |
| Header value | Thêm whitespace hoặc duplicate header. | Theo quy tắc chuẩn hóa; trường mơ hồ có thể bị từ chối. |
| Body | Thay một byte trong JSON/binary. | Payload hash và chữ ký phải thay đổi. |
| Content encoding | Nén hoặc giải nén body. | Chỉ chấp nhận nếu profile quy định representation và digest tương ứng. |
| Timestamp | Gửi request ngoài cửa sổ. | Từ chối dù HMAC đúng. |
| Nonce | Gửi lại nonce đã tiêu thụ. | Từ chối replay; kiểm tra concurrency. |
| Audience/host | Gửi chữ ký dành cho API khác. | Từ chối do authority/host không khớp. |
| Parser chain | Gửi request qua gateway và backend. | Mọi lớp hiểu cùng method/path/header/body đã ký. |

### 12.2. Test vector minh họa

Một fixture có thể lưu dưới dạng JSON:

```json
{
  "profile": "canonical-v1",
  "method": "POST",
  "path": "/v1/certificates",
  "query": "course=java&tenant=org-7",
  "headers": {
    "content-type": "application/json",
    "host": "api.example.org"
  },
  "bodyUtf8": "{\"learnerId\":\"usr-57\"}",
  "expectedCanonicalFields": [
    "POST",
    "/v1/certificates",
    "course=java&tenant=org-7",
    "content-type:application/json\\nhost:api.example.org",
    "content-type;host",
    "<payload-sha256>"
  ]
}
```

Trong test thực, `<payload-sha256>` phải được thay bằng giá trị hash chính xác của body bytes; expected signature cũng cần được tạo bằng một test secret cố định không dùng ở production. Không dùng fixture chứa secret thật.

### 12.3. Property-based và differential tests

Ngoài ví dụ cố định, có thể sinh ngẫu nhiên các query/header/path hợp lệ để kiểm tra tính chất:

- Cùng request theo profile phải tạo canonical bytes giống nhau ở client và server.
- Thay đổi một thành phần đã ký phải làm chữ ký thất bại.
- Thành phần không được ký không được phép làm thay đổi quyết định định tuyến/quyền theo cách nguy hiểm.
- Parser từ gateway, signature middleware và handler phải đồng ý về representation.
- Duplicate/ambiguous inputs bị từ chối nhất quán.
- Việc serialize/parse không được làm mất hoặc tự thêm dữ liệu đã ký.

## 13. Checklist triển khai canonical request

- [ ] Chọn một profile canonicalization có version; không tự trộn quy tắc của nhiều giao thức.
- [ ] Định nghĩa chính xác method, path, query, headers, payload hash, thứ tự trường, separator và encoding.
- [ ] Dùng cùng representation cho xác minh chữ ký, định tuyến và authorization.
- [ ] Quy định percent-encoding, Unicode, dot-segment, encoded slash, trailing slash và duplicate query.
- [ ] Quy định header được ký, header bắt buộc, lowercase, whitespace và duplicate header.
- [ ] Ký host/authority, content type/encoding, tenant hoặc metadata nếu chúng ảnh hưởng quyết định.
- [ ] Hash đúng byte sequence body; không parse/serialize JSON tùy ý giữa client và server.
- [ ] Bảo vệ message framing; từ chối Content-Length/Transfer-Encoding conflict và request mơ hồ.
- [ ] Tính HMAC bằng thư viện chuẩn và so sánh chữ ký constant-time.
- [ ] Ràng buộc key ID, thuật toán, profile, timestamp, nonce và audience theo chính sách.
- [ ] Chống replay bằng timestamp + nonce/cache dùng một lần; xử lý nguyên tử và phân tán.
- [ ] Dùng idempotency cho hành động nghiệp vụ không an toàn khi thực hiện lặp.
- [ ] Giới hạn kích thước body, timeout và rate limit; không để xác minh HMAC thành điểm DoS.
- [ ] Không ghi secret, signature material nhạy cảm hoặc credential vào log.
- [ ] Kiểm thử test vector đa ngôn ngữ và end-to-end qua proxy/gateway/router.
- [ ] Có versioning/migration rõ khi thay đổi canonicalization profile.

## 14. Câu hỏi tự kiểm tra

**1. Canonical request dùng để làm gì?**  
Nó tạo một biểu diễn request xác định để client và server tính HMAC trên cùng thông điệp logic, giảm khác biệt biểu diễn và bảo vệ các thành phần đã chọn.

**2. Có một quy tắc canonicalization áp dụng cho mọi HMAC API không?**  
Không. Phải theo profile/giao thức cụ thể và định nghĩa rõ byte sequence, trường, thứ tự, encoding và separator.

**3. Vì sao phải ký method, path và query?**  
Vì chúng quyết định hành động và tài nguyên đích. Nếu bỏ qua, request có thể bị đổi endpoint hoặc tham số mà chữ ký không ràng buộc.

**4. Tại sao body hash cần dựa trên byte sequence chính xác?**  
Vì JSON có thể được serialize theo nhiều dạng khác nhau. Nếu client và server hash hai representation khác nhau, chữ ký không khớp hoặc một lớp có thể xử lý body khác với body đã xác minh.

**5. HMAC hợp lệ có chống replay không?**  
Không tự động. Attacker có thể gửi lại request đã ký. Cần timestamp, nonce, replay cache và idempotency theo mục đích.

**6. Vì sao duplicate query/header nguy hiểm?**  
Các parser có thể chọn giá trị đầu, cuối hoặc gộp khác nhau. Signature middleware và business handler có thể xử lý request theo hai cách khác nhau.

**7. Có thể chuẩn hóa path bằng cách decode hết percent-encoding không?**  
Không tùy tiện. Encoded slash, dot-segment và Unicode có thể ảnh hưởng routing; phải theo profile thống nhất với proxy và router, hoặc từ chối representation mơ hồ.

**8. HMAC có mã hóa request hoặc cung cấp non-repudiation không?**  
Không. HMAC cung cấp kiểm tra toàn vẹn/xác thực bên giữ shared secret; request vẫn cần TLS và việc nhiều bên cùng giữ secret làm hạn chế khả năng quy kết duy nhất.

**9. Nếu đổi canonicalization profile, có cần versioning không?**  
Có. Client và server phải biết chính xác profile nào được dùng; migration cần giới hạn và không fallback mơ hồ.

**Ghi nhớ:** Canonical request là hợp đồng byte-level giữa client và server. Hãy chuẩn hóa method, path, query, headers và body theo một profile có version; bảo đảm cùng representation được ký, xác minh và thực thi; xử lý duplicate/ambiguous input; rồi kết hợp timestamp, nonce, idempotency và quản lý key để bảo vệ request trong toàn bộ vòng đời.
