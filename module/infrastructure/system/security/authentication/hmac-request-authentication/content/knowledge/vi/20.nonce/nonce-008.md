# Nonce theo client trong xác thực HTTP request bằng HMAC

> **Chương:** Nonce  
> **Đề bài:** Nonce theo client  
> **Phạm vi module:** `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION` — Xây dựng xác thực HTTP request với shared secret và canonical request ký method, URI, header và/hoặc raw body theo hợp đồng. Bài học tập trung vào **namespace nonce riêng cho từng client đã xác thực**, chống replay bằng timestamp và kho nonce nguyên tử, hành vi qua key rotation, gateway/proxy và sự khác biệt giữa authentication, authorization và idempotency.

## 1. Nonce theo client nghĩa là gì?

**Nonce** (*number used once*) là giá trị được tạo để **chỉ dùng một lần trong phạm vi chính sách đã xác định**. Khi HMAC ký HTTP request, nonce được đưa vào canonical request cùng timestamp. Receiver kiểm tra chữ ký và **ghi nhận nonce đã được sử dụng** để từ chối việc phát lại request có chữ ký hợp lệ.

Giả sử hai đối tác độc lập tích hợp cùng API thanh toán:

~~~http
POST /v1/orders?mode=commit HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: merchant-a
X-Key-Id: key-a-2026
X-Timestamp: 1795824000
X-Nonce: UHpXKkv1ZdK2MHbNSEUdvw
X-Signature: <base64url-tag-hmac-sha256>

{"orderId":"o-123","amount":150000}
~~~

Một request của client khác có thể vô tình gửi **cùng nonce**:

~~~http
POST /v1/orders?mode=preview HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: merchant-b
X-Key-Id: key-b-2026
X-Timestamp: 1795824000
X-Nonce: UHpXKkv1ZdK2MHbNSEUdvw
X-Signature: <tag-duoc-ky-bang-secret-cua-merchant-b>

{"orderId":"o-456","amount":150000}
~~~

**Theo hợp đồng minh họa trong bài, nonce duy nhất theo từng client trong một audience dịch vụ**, không duy nhất toàn cục giữa mọi client:

~~~text
(audience=orders-api-production, client=merchant-a, nonce=N) -> đã dùng
(audience=orders-api-production, client=merchant-b, nonce=N) -> có thể dùng
~~~

Điều này giải quyết một vấn đề quan trọng của hệ thống multi-tenant: **merchant A không được làm merchant B mất quyền gửi request chỉ bằng cách chọn cùng nonce**. Đồng thời, không cho phép cùng merchant A tái sử dụng nonce để gửi một request thứ hai trong cửa sổ chống replay.

**Định nghĩa chính sách của bài:**

> Mỗi nonce hợp lệ là **duy nhất trong namespace (audience, authenticatedClientId)** trong thời gian nonce store còn bảo vệ cửa sổ timestamp. Một request mới của cùng client/audience có cùng nonce bị từ chối, **bất kể key ID, path, method hoặc body khác nhau**.

Đây là **một lựa chọn thiết kế minh họa**, không phải yêu cầu rằng mọi HMAC API đều dùng đúng tuple này. Quan trọng là cả client, verifier, kho nonce và chính sách rotation phải cùng dùng một định nghĩa phạm vi.

### 1.1. Nonce khác timestamp, signature và idempotency key

| Trường | Mục đích | Có thể lặp lại khi nào? |
|---|---|---|
| **Timestamp** | Giới hạn độ tuổi request được ký | Nhiều request hợp lệ trong cùng giây |
| **Nonce** | Đánh dấu một lần sử dụng trong phạm vi client/audience | Không lặp trong replay window của cùng client |
| **HMAC signature** | Chứng minh toàn vẹn và sở hữu shared secret theo canonical bytes | Với cùng bytes và secret, tag giống nhau |
| **Idempotency key** | Ngăn một hành động nghiệp vụ thực hiện nhiều lần | Có thể cố ý lặp ở retry để trả lại cùng kết quả |
| **Request ID** | Truy vết/observability | Có thể unique cho log nhưng không tự đủ chống replay |

Một request gửi lại y nguyên có thể vẫn **đúng HMAC**, vì chữ ký đúng về toán học. Nếu timestamp vẫn nằm trong cửa sổ, chỉ nonce store mới phát hiện việc đã sử dụng trước đó. **Không dùng request ID hay HMAC string đơn thuần thay nonce store**, trừ khi một giao thức được thiết kế và chứng minh tương đương rõ ràng.

### 1.2. Mục tiêu học tập

Sau bài, người học có thể:

1. Giải thích vì sao replay protection cần namespace theo **client đã xác thực**, thay vì nonce toàn cục hoặc nonce theo IP.
2. Đánh giá các cách scope: `nonce`, `(clientId, nonce)`, `(audience, clientId, nonce)`, `(clientId, keyId, nonce)` và `(clientId, endpoint, nonce)`.
3. Định nghĩa canonical nonce: 16 byte CSPRNG, Base64URL không padding, kiểm tra strict 22 ký tự và ký cùng request.
4. Xác định thứ tự đúng: **lookup key → kiểm tra timestamp → xác minh HMAC → atomic reserve nonce → authorization/business**.
5. Tính TTL nonce đủ dài cho cửa sổ timestamp, phân biệt Redis `EX` (giây) và `PX` (mili giây).
6. Mô phỏng atomic reservation, replay liên key khi rotation và hai request đồng thời trong Java 17.
7. Kiểm thử proxy/gateway, hệ thống đa node, lỗi datastore, khả năng DoS và retry/idempotency.
8. Phân biệt client identity, credential/key identity, authenticated principal và quyền trên tài nguyên.

## 2. Phân biệt client identity với credential và HTTP source

### 2.1. Một client có thể sở hữu nhiều khóa

Ví dụ một đối tác tên `merchant-a` có hai shared secrets đang ở giai đoạn rotation:

~~~text
Authenticated client identity: merchant-a
Audience: orders-api-production

Key record #1:
  keyId = old-2026
  owner = merchant-a
  state = VERIFY_ONLY

Key record #2:
  keyId = new-2026
  owner = merchant-a
  state = ACTIVE
~~~

Cả hai key IDs là **credentials của cùng một client**, không phải hai client khác nhau. Một nonce được dùng bằng old key cần được coi là đã dùng khi client chuyển sang new key trong cửa sổ replay nếu hợp đồng yêu cầu **mỗi nonce một lần cho một client**.

Vì vậy, trong ví dụ này, namespace lưu nonce là:

~~~text
NonceKey(
    audience = "orders-api-production",
    authenticatedClientId = "merchant-a",
    canonicalNonce = "UHpXKkv1ZdK2MHbNSEUdvw"
)
~~~

**Không chứa `keyId`**. Key ID vẫn được **đưa vào canonical request và ký bằng HMAC**, chỉ là không nằm trong khóa *deduplication*.

### 2.2. Không lấy nguyên X-Client-Id chưa kiểm chứng làm danh tính an toàn

Header `X-Client-Id` ban đầu chỉ là **một claim do client khai**:

~~~http
X-Client-Id: merchant-a
X-Key-Id: new-2026
X-Nonce: ...
~~~

Một attacker có thể tự đặt `X-Client-Id: merchant-b`. Nếu server dùng claim này để tạo namespace, reserve nonce hoặc tạo principal **trước khi xác minh key ownership/HMAC**, có thể phát sinh:

- **Nonce poisoning:** attacker chiếm nonce của một client khác bằng request có MAC giả.
- **Cross-tenant confusion:** key ID của tenant A bị diễn giải trong tenant B.
- **Key enumeration:** timing/error message có thể tiết lộ key ID tồn tại.
- **Cross-client DoS:** một request sai chữ ký làm đầy hoặc chiếm nonce namespace của người khác.

Luồng đúng:

1. Đọc các **header duy nhất, hợp lệ về cú pháp** từ HTTP parser.
2. Tra key record đáng tin theo cặp client ID/key ID và **audience**.
3. Xác nhận key record thuộc client, state cho phép verify.
4. Tính và xác minh HMAC trên chính các metadata đã ký.
5. Chỉ sau MAC đúng, lấy `authenticatedClientId` từ key record/principal đáng tin.
6. Tạo nonce scope theo `(audience, authenticatedClientId, nonce)` rồi reserve nguyên tử.

Việc kiểm tra timestamp *format* và giới hạn size có thể diễn ra sớm trước HMAC; nhưng **không được ghi nonce khi MAC chưa đúng**.

### 2.3. Vì sao không scope theo IP, session hoặc connection?

| Nguồn nhận diện | Vấn đề khi dùng làm nonce namespace |
|---|---|
| Remote IP | Nhiều client chia NAT/proxy; một client có thể đổi IP |
| `X-Forwarded-For` | Có thể bị giả nếu không do proxy đáng tin quản lý; không là danh tính HMAC |
| TLS connection | Client mở connection mới, HTTP/2 multiplexing và retry; replay qua connection khác |
| HTTP session ID | Không nhất thiết gắn với HMAC client, có thể rotate hoặc vắng mặt |
| Hostname client | Có thể trùng hoặc bị spoof |
| Key ID đơn độc | Key ID có thể trùng giữa tenant hoặc đổi trong rotation |
| Client ID raw chưa verify | Do attacker chọn trước xác thực |
| **Authenticated client ID + audience** | **Phù hợp** khi principal đã được xác nhận bằng key/HMAC và namespace thống nhất |

Với một tổ chức có nhiều API credentials nhưng muốn giới hạn nonce **theo từng credential độc lập**, có thể lựa chọn scope theo credential. Tuy nhiên, phải cân nhắc **phát lại qua rotation** và đảm bảo policy của chính API, không mặc nhiên cho `keyId` vào mọi nonce key.

## 3. Chọn namespace nonce theo client

### 3.1. So sánh các phương án

| Nonce store key | Hành vi | Đánh giá |
|---|---|---|
| `nonce` | Nonce trùng giữa hai client bị coi replay | Quá rộng, gây chặn chéo tenant |
| `(clientId, nonce)` | Phân biệt client, nhưng không phân biệt audience/dịch vụ | Có thể xung đột khi nhiều API chia một store |
| **`(audience, authenticatedClientId, nonce)`** | Cùng nonce được dùng bởi hai client khác nhau; một client không tái sử dụng | **Lựa chọn của bài** |
| `(audience, clientId, keyId, nonce)` | Nonce của cùng client có thể tái sử dụng qua key ID mới | Không phù hợp với chính sách uniqueness xuyên rotation |
| `(clientId, endpoint, nonce)` | Nonce tái sử dụng được ở endpoint khác | Chỉ dùng nếu định nghĩa uniqueness theo endpoint là chủ đích |
| `(clientId, timestamp, nonce)` | Cùng nonce có thể tái sử dụng bằng timestamp mới | Làm suy yếu chính sách “nonce không lặp trong cửa sổ” |
| `(sourceIp, nonce)` | Phụ thuộc topology mạng, không phải principal | Tránh dùng |

**Audience** ở đây là một định danh dịch vụ có chính sách bảo mật riêng, ví dụ `orders-api-production`. Không lấy audience tùy ý từ một `Host` hoặc `X-Audience` do client gửi mà không kiểm chứng. Nó phải gắn với service configuration và/hoặc key record đáng tin và được ràng buộc vào canonical request/key policy.

### 3.2. Cùng nonce, hai client: hợp lệ về replay policy

~~~text
Request R1:
  principal = merchant-a
  nonce     = N
  valid MAC = yes
  reserve   = SUCCESS

Request R2:
  principal = merchant-b
  nonce     = N
  valid MAC = yes, dùng secret của merchant-b
  reserve   = SUCCESS
~~~

Đây là kết quả có chủ ý: R2 **không phát lại R1 dưới cùng principal**. Chỉ giống chuỗi nonce không chứng minh có replay. Mỗi request vẫn cần HMAC hợp lệ và quyền riêng của principal.

### 3.3. Cùng client, hai key IDs: nonce phải bị từ chối ở lần thứ hai

~~~text
Request R1:
  principal = merchant-a
  keyId = old-2026
  nonce = N
  MAC = valid
  reserve(audience, merchant-a, N) -> SUCCESS

Request R2:
  principal = merchant-a
  keyId = new-2026
  nonce = N
  MAC = valid với new secret
  reserve(audience, merchant-a, N) -> REPLAY
~~~

Dù R2 được ký đúng với key mới, **nó vẫn tái sử dụng nonce của client**. Không cho phép key rotation vô tình thay namespace chống replay. Cũng không dùng “HMAC tag” làm nonce key; hai key khác nhau tạo hai tags khác nhau ngay cả khi nonce giống nhau.

**Caveat:** nếu một hệ thống cố ý quy định nonce duy nhất **theo key credential**, thì có thể cho scope chứa key ID. Phải nói thẳng rằng nó cho phép cùng client sử dụng nonce giống nhau trên hai keys và đánh giá tác động. Hợp đồng của bài chọn uniqueness **xuyên key IDs đang được verify**.

### 3.4. Cùng client, hai endpoint: không scope theo endpoint

~~~text
POST /v1/orders?mode=preview  nonce=N -> SUCCESS
POST /v1/orders?mode=commit   nonce=N -> REPLAY
~~~

Các request có method/target/body khác nhau sẽ có MAC khác nhau, nhưng nonce policy của bài áp **toàn client trong một audience**. Không đưa path vào nonce key nếu muốn ngăn reuse xuyên endpoints. Với microservices có audience khác nhau, nonce có thể độc lập theo audience, nhưng từng service phải có key/audience binding thật.

## 4. Nonce phải sinh như thế nào?

### 4.1. Nonce không nhất thiết bí mật, nhưng phải khó đoán và tránh trùng

Nonce thường đi trong HTTP header và được đưa vào HMAC; nó **không phải secret**. Tuy nhiên, một nonce predictable hoặc dễ trùng có thể gây lỗi nghiệp vụ, tự chặn client hoặc tạo cơ hội gây tranh chấp (đặc biệt khi một ứng dụng dùng nhiều SDK instances).

Chọn nonce từ **cryptographically secure pseudorandom number generator (CSPRNG)**. Với Java 17:

~~~java
SecureRandom rng = new SecureRandom();
byte[] nonceBytes = new byte[16]; // 128 bit
rng.nextBytes(nonceBytes);

String nonce = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(nonceBytes);
// 16 byte => 22 ký tự Base64URL không padding.
~~~

**Không dùng** `java.util.Random`, timestamp hiện tại, `System.nanoTime()`, số đếm cục bộ không đồng bộ, tên client hay thứ tự request để thay thế một nonce ngẫu nhiên. `UUID.randomUUID()` có thể cung cấp UUID v4 được tạo bằng nguồn an toàn trên JDK, nhưng **khác định dạng và dung lượng bit ngẫu nhiên** so với contract 16 raw bytes/Base64URL; không tự hoán đổi formats.

### 4.2. Xác suất đụng nonce ngẫu nhiên

Với `b` bit ngẫu nhiên độc lập và `q` lần sinh trong cùng namespace, xấp xỉ xác suất có ít nhất một cặp trùng theo *birthday bound*:

\[
P_{\mathrm{collision}}\;\approx\;\frac{q(q-1)}{2^{b+1}}
\quad\text{khi }q\ll 2^{b/2}.
\]

Nếu nonce 128 bit và một client sinh khoảng một tỷ nonce (`q = 10^9`) trong cùng phạm vi, xác suất xấp xỉ **1,47 × 10⁻²¹**. Đây là giá trị **xác suất của nguồn ngẫu nhiên tốt**, không phải bằng chứng không bao giờ va chạm. Nếu server nhận nonce đã dùng, phải reject; client cần tạo nonce khác và ký lại khi retry.

Vì scope tách client, hai client vô tình tạo cùng 128-bit nonce **không tự xung đột trong store**. Đừng giảm nonce xuống 32 bit chỉ vì đã scope theo client; traffic tăng sẽ khiến birthday collision đáng kể và dễ gây chặn request.

### 4.3. Một biểu diễn canonical duy nhất

Hợp đồng minh họa:

~~~text
Nonce raw bytes:   16 bytes (128 random bits)
Header:            X-Nonce
Encoding:          Base64URL without padding
Text length:       exactly 22 ASCII characters
Alphabet:          A-Z a-z 0-9 - _
Validation:        decode 16 bytes then encode lại và so text
~~~

Với 16 bytes, Base64URL no-pad có 22 chars: ký tự cuối chứa **4 pad bits** không có dữ liệu nên phải bằng 0 trong encoding canonical. Decoder có thể lỏng lẻo khi xử lý pad bits; **decode rồi encode lại** để đảm bảo một nonce chỉ có một biểu diễn text được nhận.

Không cho phép:

~~~text
X-Nonce: "abc..."          # Quotes không thuộc format
X-Nonce: abc...=           # Padding ngoài contract
X-Nonce: abc...            # Thiếu ký tự
X-Nonce: one,two           # Comma-list / header bị gộp
X-Nonce: hello world       # Space giữa value
X-Nonce: same-value        # Không đủ 22 ký tự và có thể không CSPRNG
~~~

HTTP adapter cần từ chối **duplicate `X-Nonce` headers** và ký tự điều khiển. Server chỉ có thể kiểm tra **hình thức và uniqueness đã quan sát**, chứ không thể chứng minh một giá trị client gửi thực sự được sinh bởi `SecureRandom`. Hợp đồng yêu cầu phía client sinh CSPRNG; server reject nếu từng dùng trong namespace của client.

## 5. Timestamp giới hạn thời gian; nonce chặn replay trong cửa sổ

Giả sử dùng Unix epoch **seconds** với cửa sổ độ lệch `W = 300` giây:

\[
t_{\mathrm{server}}-300 \le t_{\mathrm{signed}}
  \le t_{\mathrm{server}}+300.
\]

Timestamp được đưa vào canonical request để attacker không thể kéo dài thời gian bằng cách sửa một trường chưa ký. Nhưng một request được sao chép nguyên cả timestamp, nonce và signature vẫn có **HMAC hợp lệ** trong cửa sổ.

### 5.1. Vì sao TTL nonce phải đủ dài?

Với một timestamp đã ký `t`:

- Server có thể chấp nhận request **sớm nhất** tại thời điểm `t - 300`.
- Server còn có thể chấp nhận nó tới **`t + 300`**.
- Từ lúc sớm nhất đến lúc muộn nhất là **600 giây**.

Do đó, nếu nonce được reserve tại `t - 300` và bị xóa chỉ sau **300 giây**, attacker có thể gửi lại request trong nửa sau của cửa sổ. **HMAC và timestamp vẫn đúng, nhưng store quên nonce**.

Chính sách minh họa:

~~~text
window: ±300 seconds inclusive
TTL nonce: 660 seconds tính từ lần reserve đầu
nonce scope: (audience, authenticatedClientId, canonicalNonce)
store operation: atomic insert-if-absent with expiration
failed duplicate: KHÔNG gia hạn TTL chỉ vì request replay
~~~

Giá trị `660` gồm 600 giây bao phủ cửa sổ và 60 giây margin cho sai lệch vận hành minh họa. Không có con số TTL đúng cho mọi hệ thống; phải tính từ **max effective timestamp acceptance interval**, clock skew giữa các verifier, datastore behavior và yêu cầu retention.

### 5.2. Đơn vị TTL không được nhầm với đơn vị timestamp

Redis có thể dùng:

~~~redis
SET nonce:... 1 NX EX 660
~~~

`EX 660` nghĩa là 660 **giây**. Nếu dùng `PX`:

~~~redis
SET nonce:... 1 NX PX 660000
~~~

`PX 660000` nghĩa là 660.000 **mili giây**, tương đương 660 giây. `PX 660` chỉ giữ khoảng 0,66 giây và có thể làm replay lọt.

Nếu SDK cache dùng `Duration`, phải kiểm tra nó chuyển thành giây/mili giây thế nào. Nếu timeout/TTL bị làm tròn xuống 0, một nonce có thể không được bảo vệ trong phần cửa sổ còn lại.

### 5.3. Nonce không phải idempotency key

Giả sử client gửi yêu cầu thanh toán và bị timeout:

~~~text
R1: timestamp=t1, nonce=N1, signature=S1
R2: timestamp=t2, nonce=N2, signature=S2
~~~

R2 có nonce mới nên **không phải replay nonce**, nhưng có thể là **giao dịch trùng** với R1 nếu server đã xử lý R1 rồi response bị mất. Chính sách xử lý thường cần thêm:

~~~text
X-Idempotency-Key: payment-order-123
~~~

Idempotency key có chức năng tạo **cùng kết quả/không thực thi lặp** cho một thao tác logic, khác nonce dùng một lần cho mỗi HTTP request. Nếu idempotency key ảnh hưởng xử lý nghiệp vụ, **đưa nó vào hợp đồng ký**. Retry cần nonce mới và MAC mới, nhưng có thể giữ cùng idempotency key để lấy lại kết quả an toàn.

## 6. Atomic reserve nonce theo client

### 6.1. Thứ tự an toàn

~~~mermaid
sequenceDiagram
    participant C as Client A
    participant G as Gateway
    participant V as HMAC Verifier
    participant K as Key Store
    participant N as Shared Nonce Store
    participant B as Business
    C->>C: Tạo random nonce, timestamp, canonical request, HMAC
    C->>G: Request có clientId/keyId/nonce/signature
    G->>V: Raw target, headers, body tại trust boundary
    V->>V: Parse header, giới hạn size, check timestamp
    V->>K: Lookup secret theo clientId/keyId/audience
    K-->>V: Key record thuộc authenticated client
    V->>V: Validate key state và full HMAC tag
    V->>N: Atomic reserve (audience, authenticated client, nonce)
    N-->>V: SUCCESS hoặc ALREADY_USED
    V->>B: Chỉ khi SUCCESS, chuyển principal và typed request
    B->>B: Authorization và idempotency
~~~

Một trình tự có thể thay đổi bước validate timestamp/lookup để giảm chi phí hoặc hạn chế oracle, nhưng **nonce không được bị reserve trước khi MAC đúng**. Nếu không, attacker gửi request giả chữ ký với nonce của một client sẽ có thể “đốt” nonce đó và chặn request thật.

### 6.2. Vì sao GET rồi SET sai?

Cách sai với hai verifier node:

~~~text
Verifier A: GET nonceKey -> không tồn tại
Verifier B: GET nonceKey -> không tồn tại
Verifier A: SET nonceKey
Verifier B: SET nonceKey
Cả A và B: ACCEPT  <-- replay race
~~~

Cách đúng cần **một lệnh atomic insert-if-absent**:

~~~text
reserve(nonceKey) -> created? true/false
  A: true
  B: false
~~~

Với Redis:

~~~redis
SET nonce:... 1 NX EX 660
~~~

`NX` chỉ tạo khi khóa chưa tồn tại; `EX` đặt TTL trong **cùng một thao tác**. Không dùng `SETNX` rồi `EXPIRE` tách rời, vì process chết giữa hai lệnh có thể để lại key không có TTL hoặc gây quản lý sai. Ở datastore khác, cần primitive transactional compare-and-insert với expiration tương đương.

### 6.3. Thiết kế nonce store key

Một encoding logic an toàn:

~~~text
NonceKey {
  version: 1
  audience: "orders-api-production"
  authenticatedClientId: "merchant-a"
  nonce: "UHpXKkv1ZdK2MHbNSEUdvw"
}
~~~

Trong Java có thể dùng một `record` với các thành phần typed, tránh nối string nhập nhằng. Với Redis, cần tạo key có delimiter không thể nhầm hoặc **length-prefix encoding** và hash cố định:

~~~text
storageKey = "nonce:v1:" + SHA-256(
    lengthPrefixed(audience)
    || lengthPrefixed(authenticatedClientId)
    || lengthPrefixed(canonicalNonce)
)
~~~

Dấu `||` ở đây nghĩa là nối byte. Hash chỉ dùng để **định danh khóa lưu trữ**, không phải thay HMAC. Có thể dùng HMAC với một storage key nội bộ nếu cần giảm khả năng lộ tên principal/nonce trong logs hoặc key scans. Nếu tên client bị giới hạn alphabet (ví dụ `[A-Za-z0-9_-]+`), vẫn phải phân biệt namespace rõ ràng và tránh sử dụng raw field do attacker gửi trước khi verify.

**Không nên chứa `keyId` trong key lưu trữ của ví dụ**: khi rotate, namespace của cùng một client phải ổn định. **Không đưa timestamp vào key**: nếu cùng nonce được ký lại ở timestamp mới, nó vẫn phải bị coi là reused trong cửa sổ.

### 6.4. Failure mode của store

| Sự cố | Hậu quả tiềm ẩn | Chính sách |
|---|---|---|
| Redis / DB timeout | Không biết nonce đã được dùng chưa | **Fail closed** khi replay protection bắt buộc |
| Hai verifier dùng store tách biệt | Cùng nonce có thể pass mỗi node | Shared atomic store hoặc partition routing được chứng minh |
| TTL quá ngắn | Nonce bị quên khi timestamp còn hợp lệ | Tính TTL theo full window + margin |
| Eviction khi áp lực bộ nhớ | Dữ liệu nonce biến mất sớm | Store/cấu hình có no-eviction thích hợp, capacity planning |
| Nonce key thiếu client | Hai tenant vô tình chặn nhau | Scope bằng authenticatedClientId |
| Nonce key chứa keyId | Replay policy bị reset qua rotation | Scope ổn định theo client/audience |
| Store trả “exists” nhưng app vẫn accept | Replay vượt qua policy | Bắt buộc kiểm kết quả atomic insert |
| HTTP gateway tự retry | Bị reject replay dù client không cố ý | Xử lý retry có nonce mới, ký lại, idempotency |
| Key record bị REVOKED | MAC có thể đúng nhưng credential không còn dùng được | Reject trước khi reserve |
| Attacker có key hợp lệ spam nonce mới | Tăng dung lượng store/CPU | Quota, rate limiting theo client, bounded TTL |

Khi thực hiện nhiều request song song, **mỗi request của cùng client phải có nonce riêng**. Không tạo nonce một lần khi khởi tạo HTTP client singleton rồi dùng lại cho cả pool request.

### 6.5. Mức phân tán và vùng địa lý

Nếu một client có thể gọi cùng API ở nhiều availability zones/regions, chính sách nonce per-client phải đúng **ở mọi nơi có thể xác thực cùng client/audience**.

- Một Redis chỉ tồn tại trong node A còn node B có cache riêng là không đủ.
- Eventual replication có thể cho phép hai bản sao cùng accept trước khi thấy dữ liệu nhau.
- Có thể dùng global strongly consistent reservation hoặc route một client/nonce đến một vùng authoritative có atomicity.
- Nếu failover làm mất lịch sử nonce còn hiệu lực, cần đánh giá replay risk và chọn fail closed cho đến khi trạng thái chống replay được khôi phục.
- Clock các node cần được đồng bộ; timestamp window không thay thế tính nhất quán nonce store.

Không tuyên bố “đã chống replay toàn cụm” chỉ vì unit test của một `ConcurrentHashMap` trong một JVM chạy xanh.

## 7. Canonical HMAC request có client ID, nonce và key ID

Một nonce sẽ không thể bảo vệ tính nguyên vẹn nếu nó không được **ký cùng request**. Hợp đồng minh họa `hmac-client-nonce-v1` có canonical request **10 dòng**:

| Dòng | Thành phần ký | Ví dụ/quy tắc |
|---|---|---|
| 1 | Version | `hmac-client-nonce-v1` |
| 2 | Audience | `orders-api-production` |
| 3 | Method | `POST` theo method thật |
| 4 | Raw target | `/v1/orders?mode=commit` tại verifier, theo route grammar |
| 5 | Content-Type | `application/json` đã chuẩn hóa |
| 6 | Client ID | `merchant-a`, được ràng buộc với key record |
| 7 | Key ID | `old-2026` hoặc `new-2026`, được ký |
| 8 | Timestamp | Unix epoch seconds ASCII canonical |
| 9 | Nonce | Base64URL không padding của 16 byte |
| 10 | Body digest | Lowercase hex của SHA-256 **raw request body bytes** |

Nối 10 dòng bằng LF (`\n`), **không có LF cuối**, mã hóa UTF-8. Tag HMAC-SHA-256 32 byte được chuyển thành Base64URL không padding trong `X-Signature`. Signature **không** nằm trong canonical string để tránh tự tham chiếu.

Ví dụ:

~~~http
POST /v1/orders?mode=commit HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: merchant-a
X-Key-Id: old-2026
X-Timestamp: 1795824000
X-Nonce: UHpXKkv1ZdK2MHbNSEUdvw
X-Signature: <43-char-base64url-hmac-tag>

{"orderId":"o-123","amount":150000}
~~~

Canonical text:

~~~text
hmac-client-nonce-v1
orders-api-production
POST
/v1/orders?mode=commit
application/json
merchant-a
old-2026
1795824000
UHpXKkv1ZdK2MHbNSEUdvw
<sha256-hex-of-raw-body>
~~~

Dòng cuối và chữ ký trong dấu ngoặc nhọn là **placeholder**, không copy nguyên vào phép HMAC. `1795824000` chỉ minh họa cú pháp; tính hợp lệ về thời gian phụ thuộc **server clock** thực tế. Với body rỗng, SHA-256 là:

~~~text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

**Lưu ý:** JSON bytes được ký không tự bảo đảm business parser hiểu đúng duplicate keys, số hoặc Unicode; nếu parser/controller hiểu khác verifier, cần policy nội dung rõ ràng. Client/key ID, audience và nonce phải được **ký**, còn quyền sử dụng client/key ID phải tra từ kho khóa tin cậy.

### 7.1. Vì sao ký cả key ID nhưng không đưa key ID vào nonce key?

Đây là hai câu hỏi khác nhau:

- **Cryptographic binding:** `X-Key-Id` phải được ký để không thay đổi key selection và danh tính request mà MAC vẫn khớp.
- **Replay identity:** nonce đã dùng thuộc về **principal/audience**, không reset khi thay credential.

Ví dụ:

~~~text
R1 dùng old-2026 và nonce N:
  HMAC hợp lệ -> store (audience, merchant-a, N) = used

R2 dùng new-2026 và cùng nonce N:
  HMAC theo secret mới có thể hợp lệ
  nhưng store (audience, merchant-a, N) vẫn = used
  => REPLAY
~~~

Điều này bảo vệ chính sách “một nonce cho một request của client” ngay cả trong thời gian có hai key hợp lệ. Nếu một hệ thống cần “nonce duy nhất theo credential”, phải thiết kế và công bố một hợp đồng khác.

### 7.2. Danh tính được xác thực và authorization

Sau khi HMAC, timestamp và nonce đều hợp lệ:

~~~text
authenticatedPrincipal:
    clientId = merchant-a
    audience = orders-api-production
    credentialKeyId = new-2026
    verifiedNonce = UHpXKkv1ZdK2MHbNSEUdvw
~~~

Server **vẫn phải** áp authorization: client có được phép tạo đơn, sửa đơn của tenant khác, gọi `mode=commit` hoặc đọc dữ liệu nhạy cảm không? Chữ ký đúng không trao mọi quyền; kho nonce chỉ giải quyết reuse/replay trong phạm vi đã chọn.


## 8. Java 17: HMAC verifier và nonce store scope theo authenticated client

Ví dụ Java 17 dưới đây minh họa **một hợp đồng rõ ràng**, không phụ thuộc Spring/Servlet hay thư viện ngoài JDK:

- Sinh nonce 128-bit bằng `SecureRandom`, encode Base64URL không padding (22 ký tự).
- Ký canonical request với method, raw target, content type, client ID, key ID, timestamp, nonce và body hash.
- Xác minh tag HMAC-SHA-256 đủ 32 byte sau strict Base64URL decoding.
- Kiểm tra key record có đúng client/audience và trạng thái `ACTIVE` hoặc `VERIFY_ONLY` trong deadline.
- Dùng nonce key `(audience, authenticatedClientId, nonce)`, **không chứa key ID**.
- Chỉ reserve nonce **sau khi MAC đúng**, TTL 660 giây; demo store dùng `ConcurrentHashMap.compute` cho atomicity trong một JVM.
- Test cạnh tranh đồng thời: cùng client/audience/nonce chỉ **một** lời gọi được nhận.
- Test same nonce qua **hai client** được nhận riêng; same nonce qua **hai key IDs của cùng client** bị coi replay.

**Giới hạn:** đây là ví dụ **lõi xác thực và nonce**, chưa phải HTTP server, key vault, distributed Redis, authorization hay idempotency production. Bài không chạy Gradle và không yêu cầu framework.

### 8.1. Mã nguồn `ClientScopedNonceHmacDemo.java`

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class ClientScopedNonceHmacDemo {
    private static final String VERSION = "hmac-client-nonce-v1";
    private static final String AUDIENCE = "orders-api-production";
    private static final String HMAC = "HmacSHA256";
    private static final long WINDOW_SECONDS = 300L;
    private static final long NONCE_TTL_SECONDS = 660L;

    private ClientScopedNonceHmacDemo() {}

    public record Request(
            String method, String rawTarget, String contentType,
            String clientId, String keyId, String timestamp,
            String nonce, byte[] rawBody) {
        public Request {
            if (rawBody == null) {
                throw new IllegalArgumentException("Missing raw body");
            }
            rawBody = rawBody.clone();
        }
        @Override
        public byte[] rawBody() {
            return rawBody.clone();
        }
    }

    public enum KeyState { ACTIVE, VERIFY_ONLY, REVOKED }

    // Server-owned record: được lookup từ key store đáng tin.
    public record KeyRecord(
            String clientId, String keyId, String audience,
            KeyState state, long verifyUntilEpochSeconds,
            byte[] secret) {
        public KeyRecord {
            if (secret == null || secret.length != 32) {
                throw new IllegalArgumentException(
                        "Expected 32-byte demo shared secret");
            }
            secret = secret.clone();
        }
        @Override
        public byte[] secret() {
            return secret.clone();
        }
    }

    // Namespace không chứa keyId, path, method hoặc timestamp.
    public record NonceKey(
            String audience, String authenticatedClientId,
            String canonicalNonce) {}

    public interface NonceStore {
        boolean reserve(NonceKey key, long now, long ttlSeconds);
    }

    // DEMO: atomic trong 1 JVM, KHÔNG chia sẻ giữa server nodes.
    // Không có background eviction; production dùng store có TTL thật.
    public static final class LocalNonceStore
            implements NonceStore {
        private final ConcurrentHashMap<NonceKey, Long> expiries =
                new ConcurrentHashMap<>();

        @Override
        public boolean reserve(
                NonceKey key, long now, long ttlSeconds) {
            if (key == null || ttlSeconds <= 0) {
                throw new IllegalArgumentException("Invalid nonce TTL");
            }
            AtomicBoolean inserted = new AtomicBoolean(false);
            expiries.compute(key, (id, oldExpiry) -> {
                if (oldExpiry != null && oldExpiry > now) {
                    return oldExpiry; // Replay: giữ nguyên TTL.
                }
                inserted.set(true);
                return Math.addExact(now, ttlSeconds);
            });
            return inserted.get();
        }
    }

    public static String newNonce(SecureRandom random) {
        byte[] bytes = new byte[16];
        random.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(bytes);
    }

    // Input nonce đã đi qua HTTP parsing; phải là đúng 1 field.
    private static String canonicalNonce(String text) {
        if (text == null
                || !text.matches("[A-Za-z0-9_-]{22}")) {
            throw new IllegalArgumentException(
                    "Invalid nonce alphabet/length");
        }
        final byte[] raw;
        try {
            raw = Base64.getUrlDecoder().decode(text);
        } catch (IllegalArgumentException invalid) {
            throw new IllegalArgumentException("Bad nonce", invalid);
        }
        if (raw.length != 16
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(raw).equals(text)) {
            throw new IllegalArgumentException(
                    "Non-canonical nonce encoding");
        }
        return text;
    }

    private static long parseEpochSeconds(String text) {
        if (text == null
                || !text.matches("[1-9][0-9]{0,18}")) {
            throw new IllegalArgumentException(
                    "Epoch timestamp must be seconds");
        }
        try {
            return Long.parseLong(text);
        } catch (NumberFormatException overflow) {
            throw new IllegalArgumentException(
                    "Timestamp out of long range", overflow);
        }
    }

    private static boolean inTimeWindow(
            String signedTimestamp, long now) {
        try {
            long signed = parseEpochSeconds(signedTimestamp);
            long delta = Math.subtractExact(signed, now);
            return delta >= -WINDOW_SECONDS
                    && delta <= WINDOW_SECONDS;
        } catch (IllegalArgumentException | ArithmeticException ex) {
            return false;
        }
    }

    private static String asciiToken(String input, int max) {
        if (input == null || input.isEmpty()
                || input.length() > max
                || input.chars().anyMatch(c -> c < 0x21 || c > 0x7E)) {
            throw new IllegalArgumentException("Bad signed token");
        }
        return input;
    }

    private static String canonicalContentType(String value) {
        if (value == null || value.length() > 128
                || value.chars().anyMatch(
                        c -> (c < 0x20 && c != '\t') || c > 0x7E)) {
            throw new IllegalArgumentException("Bad Content-Type");
        }
        String contentType = value.trim().toLowerCase(Locale.ROOT);
        if (!"application/json".equals(contentType)) {
            throw new IllegalArgumentException(
                    "Unsupported Content-Type");
        }
        return contentType;
    }

    public static byte[] canonicalBytes(Request r)
            throws GeneralSecurityException {
        if (r == null || !"POST".equals(r.method())) {
            throw new IllegalArgumentException("Only POST supported");
        }
        String target = asciiToken(r.rawTarget(), 2048);
        if (!target.matches(
                "/v1/orders\\?mode=(?:preview|commit)")) {
            throw new IllegalArgumentException("Invalid raw target");
        }
        String client = asciiToken(r.clientId(), 64);
        String keyId = asciiToken(r.keyId(), 64);
        if (!client.matches("[A-Za-z0-9_-]+")
                || !keyId.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid identity");
        }
        String timestamp = asciiToken(r.timestamp(), 19);
        parseEpochSeconds(timestamp); // Không chuyển unit/text.
        String nonce = canonicalNonce(r.nonce());

        byte[] body = r.rawBody();
        if (body.length > 64 * 1024) {
            throw new IllegalArgumentException("Body too large");
        }
        String bodyHash = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(body));
        String canonical = String.join("\n",
                VERSION,
                AUDIENCE,
                r.method(),
                target,
                canonicalContentType(r.contentType()),
                client,
                keyId,
                timestamp,
                nonce,
                bodyHash);
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] calculateMac(
            byte[] secret, byte[] canonical)
            throws GeneralSecurityException {
        if (secret == null || secret.length != 32) {
            throw new IllegalArgumentException("Bad shared secret");
        }
        Mac engine = Mac.getInstance(HMAC);
        engine.init(new SecretKeySpec(secret, HMAC));
        return engine.doFinal(canonical);
    }

    public static String sign(Request request, byte[] secret)
            throws GeneralSecurityException {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(
                        calculateMac(secret, canonicalBytes(request)));
    }

    private static byte[] decodeTagStrict(String text) {
        if (text == null || !text.matches("[A-Za-z0-9_-]{43}")) {
            throw new IllegalArgumentException("Invalid signature form");
        }
        final byte[] bytes;
        try {
            bytes = Base64.getUrlDecoder().decode(text);
        } catch (IllegalArgumentException invalid) {
            throw new IllegalArgumentException("Bad signature", invalid);
        }
        if (bytes.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(bytes).equals(text)) {
            throw new IllegalArgumentException(
                    "Non-canonical/truncated signature");
        }
        return bytes;
    }

    private static boolean keyCanVerify(
            Request r, KeyRecord key, long now) {
        if (r.clientId() == null || r.keyId() == null
                || !r.clientId().equals(key.clientId())
                || !r.keyId().equals(key.keyId())
                || !AUDIENCE.equals(key.audience())) {
            return false;
        }
        if (key.state() == KeyState.REVOKED) return false;
        return key.state() == KeyState.ACTIVE
                || (key.state() == KeyState.VERIFY_ONLY
                    && now <= key.verifyUntilEpochSeconds());
    }

    // Server đã tra KeyRecord bằng (clientId,keyId,audience).
    // Chỉ khi MAC hợp lệ mới reserve scope theo verified client.
    public static boolean authenticate(
            Request request, String signature,
            KeyRecord key, Clock clock, NonceStore nonceStore)
            throws GeneralSecurityException {
        if (request == null || key == null
                || clock == null || nonceStore == null) {
            return false;
        }
        long now = clock.instant().getEpochSecond();
        if (!inTimeWindow(request.timestamp(), now)
                || !keyCanVerify(request, key, now)) {
            return false;
        }
        final byte[] actual;
        final byte[] expected;
        try {
            actual = decodeTagStrict(signature);
            expected = calculateMac(
                    key.secret(), canonicalBytes(request));
        } catch (IllegalArgumentException invalid) {
            return false;
        }
        if (!MessageDigest.isEqual(expected, actual)) {
            return false;
        }
        // Không chứa keyId: tránh reset replay namespace khi rotate.
        NonceKey nonceKey = new NonceKey(
                key.audience(), key.clientId(), request.nonce());
        return nonceStore.reserve(
                nonceKey, now, NONCE_TTL_SECONDS);
    }

    private static void require(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    private static Request request(
            String client, String keyId, String nonce, long now) {
        return new Request(
                "POST", "/v1/orders?mode=commit",
                "application/json", client, keyId,
                Long.toString(now), nonce,
                "{\"orderId\":\"o-123\",\"amount\":150000}"
                        .getBytes(StandardCharsets.UTF_8));
    }

    // Không đo timing: dùng latch để ép nhiều request cạnh tranh.
    private static void concurrentReplayTest(
            Request request, String signature, KeyRecord key,
            Clock clock) throws Exception {
        final int workers = 12;
        LocalNonceStore store = new LocalNonceStore();
        ExecutorService executor =
                Executors.newFixedThreadPool(workers);
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Boolean>> results = new ArrayList<>();
        try {
            for (int i = 0; i < workers; i++) {
                results.add(executor.submit(() -> {
                    ready.countDown();
                    start.await();
                    return authenticate(
                            request, signature, key, clock, store);
                }));
            }
            require(ready.await(10, TimeUnit.SECONDS),
                    "Threads must reach start latch");
            start.countDown();
            int accepted = 0;
            for (Future<Boolean> result : results) {
                if (result.get()) accepted++;
            }
            require(accepted == 1,
                    "Exactly one of concurrent duplicates can pass");
        } finally {
            start.countDown();
            executor.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-28T00:00:00Z"),
                ZoneOffset.UTC);
        long now = clock.instant().getEpochSecond();

        byte[] secretOld = new byte[32];
        byte[] secretNew = new byte[32];
        byte[] secretB = new byte[32];
        random.nextBytes(secretOld);
        random.nextBytes(secretNew);
        random.nextBytes(secretB);

        KeyRecord aOld = new KeyRecord(
                "merchant-a", "old-2026", AUDIENCE,
                KeyState.VERIFY_ONLY, now + 120L, secretOld);
        KeyRecord aNew = new KeyRecord(
                "merchant-a", "new-2026", AUDIENCE,
                KeyState.ACTIVE, 0L, secretNew);
        KeyRecord bKey = new KeyRecord(
                "merchant-b", "key-b", AUDIENCE,
                KeyState.ACTIVE, 0L, secretB);

        String nonce = newNonce(random);
        require(nonce.length() == 22, "16 byte nonce -> 22 chars");
        Request a1 = request(
                "merchant-a", "old-2026", nonce, now);
        String sigOld = sign(a1, secretOld);
        LocalNonceStore shared = new LocalNonceStore();

        require(authenticate(a1, sigOld, aOld, clock, shared),
                "Client A accepts first nonce");
        require(!authenticate(a1, sigOld, aOld, clock, shared),
                "Identical replay is rejected");

        // Cùng client, đổi keyId và ký bằng secret hợp lệ mới:
        // vẫn REPLAY vì nonce scope không chứa keyId.
        Request aNewKeySameNonce = request(
                "merchant-a", "new-2026", nonce, now);
        String sigNew = sign(aNewKeySameNonce, secretNew);
        require(!authenticate(
                aNewKeySameNonce, sigNew, aNew, clock, shared),
                "Cross-key replay for same client is rejected");

        // Client B dùng nonce giống client A nhưng một secret khác.
        Request b = request(
                "merchant-b", "key-b", nonce, now);
        require(authenticate(
                b, sign(b, secretB), bKey, clock, shared),
                "Another authenticated client has own namespace");
        require(!authenticate(
                b, sign(b, secretB), bKey, clock, shared),
                "Client B replay is rejected separately");

        // Client A dùng nonce mới được chấp nhận.
        Request aFresh = request(
                "merchant-a", "new-2026", newNonce(random), now);
        require(authenticate(
                aFresh, sign(aFresh, secretNew), aNew,
                clock, shared), "New nonce can pass");

        // MAC sai không được chiếm nonce.
        Request toProtect = request(
                "merchant-a", "new-2026", newNonce(random), now);
        String good = sign(toProtect, secretNew);
        byte[] badTag = decodeTagStrict(good);
        badTag[0] ^= 1;
        String forged = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(badTag);
        require(!authenticate(
                toProtect, forged, aNew, clock, shared),
                "Forged MAC must be rejected");
        require(authenticate(
                toProtect, good, aNew, clock, shared),
                "Forged MAC must not poison nonce");

        // State REVOKED không được accept hoặc reserve.
        KeyRecord revoked = new KeyRecord(
                "merchant-a", "new-2026", AUDIENCE,
                KeyState.REVOKED, 0L, secretNew);
        Request revokedRequest = request(
                "merchant-a", "new-2026", newNonce(random), now);
        String revokedSig = sign(revokedRequest, secretNew);
        require(!authenticate(
                revokedRequest, revokedSig, revoked,
                clock, shared), "Revoked credential must fail");

        // Timestamp cũ, dù MAC đúng, phải bị từ chối.
        Request stale = request(
                "merchant-a", "new-2026",
                newNonce(random), now - 301L);
        require(!authenticate(
                stale, sign(stale, secretNew), aNew,
                clock, shared), "Stale request must fail");

        // Kiểm tra TTL demo: fail khi chưa hết, có thể reserve lại
        // khi TTL hết (timestamp cũ sẽ không còn valid lúc đó).
        LocalNonceStore ttlStore = new LocalNonceStore();
        NonceKey ttlKey = new NonceKey(
                AUDIENCE, "merchant-a", newNonce(random));
        require(ttlStore.reserve(
                ttlKey, now, NONCE_TTL_SECONDS), "Reserve once");
        require(!ttlStore.reserve(
                ttlKey, now + 659, NONCE_TTL_SECONDS),
                "Nonce still reserved at 659 sec");
        require(ttlStore.reserve(
                ttlKey, now + 661, NONCE_TTL_SECONDS),
                "Nonce can expire after full TTL");

        // Hai request đồng thời đúng cùng nonce: đúng 1 accept.
        Request racing = request(
                "merchant-a", "new-2026", newNonce(random), now);
        concurrentReplayTest(
                racing, sign(racing, secretNew), aNew, clock);
        System.out.println("PASS client-scoped nonce HMAC/replay tests");
    }
}
~~~

### 8.2. Chạy ví dụ

Lưu khối Java vào `ClientScopedNonceHmacDemo.java`, biên dịch/chạy bằng JDK 17+:

~~~bash
javac ClientScopedNonceHmacDemo.java
java ClientScopedNonceHmacDemo
~~~

Kết quả kỳ vọng:

~~~text
PASS client-scoped nonce HMAC/replay tests
~~~

### 8.3. Những ca test quan trọng nhất

| Tình huống | Kết quả kỳ vọng |
|---|---|
| Client A gửi nonce N với key cũ `VERIFY_ONLY` hợp lệ | **ACCEPT** lần đầu |
| Cùng A phát lại request cũ | **REJECT** |
| Cùng A ký lại N bằng key mới `ACTIVE` | **REJECT** theo chính sách per-client |
| Client B ký N bằng secret riêng | **ACCEPT** lần đầu |
| Cùng B phát lại N | **REJECT** độc lập |
| Client A tạo nonce mới | **ACCEPT** |
| MAC giả dùng nonce chưa có | **REJECT**, không reserve |
| Request thật sau MAC giả với cùng nonce | **ACCEPT**, không bị nonce poisoning |
| Key `REVOKED` có HMAC đúng | **REJECT**, không dựa vào nonce |
| Timestamp cũ 301 giây | **REJECT** dù MAC hợp lệ |
| 12 request đồng thời cùng client/nonce | **Chính xác một** request được accept |

Test đồng thời sử dụng `CountDownLatch`, `ConcurrentHashMap.compute` và `Future`. Nó chứng minh **quy tắc atomicity trong cùng một JVM trên dữ liệu demo**; không chứng minh multi-node safety. Khi triển khai thật, thay `LocalNonceStore` bằng kho phân tán có atomic insert-if-absent và expiration.

### 8.4. Giới hạn của mã Java

Mã có chủ ý **không** thực hiện các thành phần production sau:

- HTTP server/parser thật; kiểm tra **duplicate `X-Client-Id`, `X-Key-Id`, `X-Timestamp`, `X-Nonce`, `X-Signature`** cần làm ở HTTP adapter/edge, trước khi biến headers thành single Strings.
- Key lookup từ KMS/secret manager và policy tenant/audience thực; `KeyRecord` được tạo trong test để minh họa.
- Backend distributed nonce store có transaction/TTL/eviction policy, metric và fail closed. `ConcurrentHashMap` sẽ giữ các record đã hết hạn trong bộ nhớ cho đến lần truy cập lại.
- Authentication principal ở gateway và signed identity metadata bảo vệ qua mTLS/kênh nội bộ.
- Authorization theo action, resource, tenant và idempotency cho nghiệp vụ.
- Kiểm thử tích hợp raw target/body thực qua HTTP/1.1/2/3, decompression, proxy rewrites.
- Chính sách **quota/rate limiting** để ngăn client đã có secret dùng nhiều nonce hợp lệ làm đầy kho.
- Phân tích side-channel của key lookup và error responses, xử lý exceptions đồng nhất trước khi gửi HTTP status.

Cấu trúc `Request` sao chép raw body khi tạo/accessor để tránh bị sửa ngoài ý muốn; adapter thật vẫn phải giới hạn body bytes, HTTP framing và content coding theo hợp đồng. Ví dụ trả boolean đơn giản để không cung cấp oracle chi tiết ra mạng.

## 9. Ma trận kiểm thử nonce per-client

### 9.1. Golden fixtures về namespace

Giả sử audience `orders-api-production`, hai authenticated principals `merchant-a`, `merchant-b` và hai key IDs của merchant A là `old-2026` / `new-2026`. Bộ fixtures cần có expected **tạo độc lập**, không dựa toàn bộ vào chính hàm đang được test.

| Case | Client đã xác thực | Key ID | Nonce | HMAC | Kết quả / lý do |
|---|---|---|---|---|---|
| A1 | merchant-a | old-2026 | N1 | Đúng | **ACCEPT** lần đầu |
| A2 | merchant-a | old-2026 | N1 | Đúng | **REPLAY** |
| A3 | merchant-a | new-2026 | N1 | Đúng với key mới | **REPLAY** dù key ID đổi |
| A4 | merchant-a | new-2026 | N2 | Đúng | **ACCEPT** nếu thời gian/key hợp lệ |
| B1 | merchant-b | key-b | N1 | Đúng với secret B | **ACCEPT** dù A đã dùng N1 |
| B2 | merchant-b | key-b | N1 | Đúng | **REPLAY** của chính B |
| A5 | merchant-a | new-2026 | N3 | Sai | **REJECT**, **không reserve** |
| A6 | merchant-a | new-2026 | N3 | Đúng | **ACCEPT** sau A5 |
| A7 | merchant-a | revoked-key | N4 | Đúng toán học | **REJECT** vì key revoked |
| A8 | merchant-a | new-2026 | N5 | Đúng nhưng timestamp quá cũ | **REJECT**, không reserve |
| A9 | merchant-a | new-2026 | N6 | Đúng nhưng resource ngoài quyền | Authentication có thể pass; **authorization DENY** |
| C1 | merchant-a | new-2026 | N7 | Đúng | Hai request đồng thời: **chính xác 1 accept** |

Mỗi một chữ cái `N1`, `N2` ở bảng là **một nonce canonical 128 bit cụ thể** trong fixture, không phải literal 2 ký tự gửi vào HTTP. Bảng mô tả kết quả replay policy khi mọi trường format khác hợp lệ.

### 9.2. Test input nonce theo format

| Đầu vào | Kỳ vọng |
|---|---|
| 16 random bytes encode Base64URL no-pad (22 ký tự) | **Accept về định dạng** |
| 15 byte encode no-pad (20 ký tự) | Reject |
| 17 byte encode no-pad (23 ký tự) | Reject |
| Nonce dài 22 ký tự đúng alphabet nhưng pad bits không chuẩn | Reject qua round-trip |
| Nonce chứa `+` hoặc `/` | Reject: không phải Base64URL |
| Nonce kết thúc bằng `=` | Reject: cấm padding |
| Nonce chứa `%2F`, `%3D` dưới dạng header text | Reject: URL-encoding không thuộc grammar |
| Nonce có khoảng trắng ở giữa | Reject |
| Có CR/LF/NUL hoặc Unicode ngoài ASCII | Reject ở HTTP parser/format |
| Hai header `X-Nonce` | Reject, không chọn first/last |
| Header nối bằng comma-list | Reject |
| Không có `X-Nonce` | Reject |
| Nonce hợp lệ nhưng chưa được đưa vào canonical request | Thiết kế sai; phải ký nonce |
| Nonce có chữ ký đúng nhưng đã dùng | Replay reject |

**Lưu ý:** không có cách kiểm tra “ngẫu nhiên đủ 128 bit” chỉ từ một nonce riêng lẻ. Validation chỉ kiểm tra byte length/encoding; đánh giá entropy cần kiểm tra API sinh nonce, quy trình seeding, tests collision và cách dùng CSPRNG.

### 9.3. Test timestamp và TTL

Dùng `Clock.fixed` tại `n` và timestamp policy ±300 giây:

| Timestamp theo `n` | Freshness | Nonce behavior |
|---|---|---|
| `n-301` | Reject | Không reserve |
| `n-300` | Accept về thời gian | Reserve nếu MAC hợp lệ |
| `n` | Accept | Reserve nếu MAC hợp lệ |
| `n+300` | Accept về thời gian | Reserve nếu MAC hợp lệ |
| `n+301` | Reject | Không reserve |
| `n` với nonce đã reserve | Accept về thời gian | **Replay reject** |
| `n+1` cùng nonce, MAC mới | Accept về thời gian | **Replay reject**, vì timestamp không thuộc scope |
| `n` cùng nonce nhưng key ID mới | Accept về thời gian/key | **Replay reject** theo per-client |
| Store xóa nonce trước khi timestamp hết hạn | Sai bảo mật | Test phải phát hiện replay có thể lọt |

Test TTL theo **thời gian store thật**, không chỉ một map có trường expiry. Với `W=300`, một request `t` có thể còn hợp lệ từ `t-300` đến `t+300`. Cần retention tối thiểu đủ bao phủ khoảng đó **cộng sai lệch thực tế giữa các node**.

### 9.4. Test cạnh tranh và tính nhất quán

Các ca cần chạy trong môi trường gần production:

1. Gửi **100 request đồng thời** có cùng authenticated client/audience/nonce, nhưng HMAC hợp lệ, qua nhiều replicas. **Tối đa 1** request có thể vượt qua replay check.
2. Gửi cùng nonce ở **100 authenticated clients khác nhau**; nếu mỗi client có MAC đúng, không được block chéo chỉ vì nonce trùng.
3. Trong key rotation, đồng thời gửi request cùng nonce từ key old và key new của **cùng client**; chỉ một reserve được phép thành công.
4. Đổi HTTP method/URI/body và ký lại bằng cùng key nhưng tái sử dụng nonce: phải bị chặn theo namespace đã chọn.
5. Tắt một vùng Redis hoặc kho nonce; nếu không có khả năng xác nhận atomic write, verifier phải **fail closed**.
6. Test replication/failover khi hai requests đồng thời đến hai regions; không được cả hai accept vì eventual consistency.
7. Khi store gần đầy, kiểm tra eviction policy có thể xóa nonce chưa hết TTL hay không.
8. Trong multi-node clock skew, xác nhận TTL/boundary không tạo cửa sổ replay do store hết hạn sớm.
9. Test client SDK vô tình tái sử dụng nonce từ một singleton mutable field cho nhiều request; lỗi phải bị bắt ở môi trường thử nghiệm.
10. Quan sát retry qua gateway. Nếu gateway tự lặp lại một POST HMAC giống hệt, lớp anti-replay sẽ reject; nếu cần retry, phải có thiết kế client ký lại và **idempotency**.

### 9.5. Property-based tests

Những thuộc tính nên kiểm tra tự động:

- **Client isolation:** `reserve(A,N)` không ảnh hưởng `reserve(B,N)` khi `A != B`.
- **Nonce reuse rejection:** cùng `(audience,client,N)` không được accept hai lần trong retention window.
- **Key rotation stability:** đổi `keyId` nhưng giữ authenticated client + nonce không đổi replay decision.
- **Audience isolation:** hai dịch vụ có audiences khác nhau được namespace riêng; chữ ký/key policy vẫn phải bind audience.
- **Atomic uniqueness:** nhiều threads/nodes cạnh tranh cùng key chỉ một insert-if-absent thành công.
- **No poisoning:** signature không hợp lệ không ghi record nonce.
- **TTL soundness:** không expire record trước khi mọi request chứa timestamp đó trở nên không hợp lệ.
- **Canonical encoding:** với đúng 16 byte, nonce có đúng một Base64URL no-pad string được chấp nhận.
- **MAC binding:** sửa nonce sau khi ký làm HMAC không khớp với xác suất áp đảo.
- **Authorization separation:** replay check pass không đồng nghĩa có quyền trên resource.

## 10. Proxy/gateway, header trust và sự tách biệt tenant

HMAC có thể được xác minh ở **API gateway** hoặc trong **backend**, nhưng nonce namespace phải dựa trên danh tính đã được xác thực tại đúng ranh giới đó.

~~~text
Client merchant-a
    |
    | POST /v1/orders?mode=commit
    | X-Client-Id: merchant-a
    | X-Key-Id: old-2026
    | X-Timestamp: t
    | X-Nonce: N
    | X-Signature: tag
    v
Gateway (có thể chuyển HTTP/2 -> HTTP/1.1)
    |
    v
HMAC verifier
    1. Reject malformed headers, duplicate fields
    2. Lookup verified key owner/audience
    3. Validate timestamp, canonical request và MAC
    4. Reserve (audience, verifiedClientId, N) atomically
    |
    v
Business handler
    5. Authorization + idempotency
~~~

### 10.1. Bẫy thường gặp khi truyền client identity qua proxy

| Trường hợp | Rủi ro | Biện pháp |
|---|---|---|
| Proxy chấp nhận `X-Verified-Client: merchant-b` do internet client tự đặt | Tạo principal giả, có thể sai nonce namespace | Edge phải strip header không tin cậy, chỉ thiết lập metadata sau verify |
| Backend dùng `X-Forwarded-For` để scope nonce | NAT/proxy làm các client trùng IP hoặc đổi IP | Scope theo HMAC principal, không theo địa chỉ mạng |
| Gateway verify nhưng backend verify lại với nonce store khác | Hai tầng có thể bất đồng reject/accept | Định nghĩa duy nhất điểm reserve hoặc transaction rõ ràng |
| Gateway rewrite `X-Client-Id` trước verify | MAC client gửi không còn khớp hoặc lookup sai | Không rewrite signed identity; xác minh ở edge nếu cần |
| Gateway đổi `X-Key-Id` | Có thể chọn sai secret/key state | Ký key ID và kiểm tra ownership |
| Gateway xóa `X-Nonce` hoặc nhân đôi header | Không thể xác minh đầy đủ | Reject, không tự phát nonce thay client |
| HTTP/2 header normalization | HTTP field names case-insensitive, value có thể đổi | Test multiplicity/canonical values thật |
| Proxy auto-retry POST | Nonce bị dùng lại bởi request lặp | Không silent retry side-effecting request; idempotency |
| Gateway cache authentication decision | Có thể bypass freshness/nonce | Không cho cache đánh dấu “đã verify” cho request khác |
| Backend nhiều vùng | Nonce store eventual consistency | Atomic shared reservation hoặc định tuyến nhất quán |

Nếu gateway gửi một principal đã verify đến backend, thông tin đó phải đi qua **mTLS hoặc kênh đáng tin tương ứng**, không phải header công khai mà bất kỳ client nào cũng có thể giả. Backend vẫn phải áp resource-level authorization.

### 10.2. Đặt nơi reserve nonce

Chọn một điểm có trách nhiệm rõ:

**Phương án A — Verify và reserve ở edge:** edge kiểm tra full canonical request trước biến đổi body/URI, reserve nonce, rồi chuyển principal đã xác thực. Backend kiểm tra authorization/idempotency. Phù hợp khi edge có truy cập kho key, nonce store và kết nối đáng tin.

**Phương án B — Verify và reserve ở backend:** proxy phải bảo toàn signed method/target/headers/body, backend đọc đúng raw bytes; nonce store có tính atomic trên mọi backend node.

Không đặt một bước reserve ở edge bằng `(clientId, keyId, nonce)` và một bước ở backend bằng `(clientId, nonce)` rồi hy vọng chúng tương đương. Sự bất đồng namespace có thể dẫn đến reject khó giải thích hoặc cửa sổ replay.

## 11. Tấn công, sai lầm và cách vận hành an toàn

### 11.1. Nonce poisoning bằng request HMAC giả

**Lỗi:** server reserve nonce trước khi so MAC. Attacker biết một nonce từ traffic/logs và gửi MAC giả nhưng cùng client ID/nonce. Nếu store đánh dấu used, client thật có thể bị từ chối.

**Phòng vệ:** chỉ reserve sau khi key ownership, key state và HMAC hợp lệ. Đồng thời không log full nonce từ request không tin cậy nếu không cần thiết.

### 11.2. Rate-limit và storage exhaustion

Ngay cả khi chỉ lưu nonce sau HMAC hợp lệ, một client **có secret thật** vẫn có thể gửi hàng triệu request mới để tiêu tốn kho nonce. Server cần:

- Giới hạn số request/giây và burst theo authenticated client.
- Hạn mức concurrent requests, body size và CPU HMAC.
- Quản lý retention/TTL và capacity của store theo lưu lượng tối đa.
- Giám sát lượng nonce keys đang hoạt động theo namespace, tránh cardinality bùng nổ.
- Chính sách phản ứng với credential bị lạm dụng, bao gồm rotation/revocation.

Không xử lý storage pressure bằng cách **xóa nonce chưa hết TTL** và vẫn báo authenticated request hợp lệ; làm vậy có thể mở replay window.

### 11.3. Key bị lộ và nonce không giúp gì?

Nếu shared secret của client bị lộ, attacker có thể **tạo request mới** có nonce mới và HMAC đúng. Nonce store chỉ chặn **replay của nonce đã thấy**, không chữa được key compromise. Biện pháp là thu hồi key, phát hành secret mới, giảm quyền, giám sát bất thường và điều tra.

Nếu attacker chỉ thấy một request đã ký mà **không biết secret**, họ không thể tự tạo HMAC cho nonce mới theo kỳ vọng an toàn của HMAC-SHA-256. Nhưng họ có thể **phát lại bản sao** trong cửa sổ nếu nonce store không hoạt động hoặc chưa từng nhận bản gốc (ví dụ replay race trước khi first reserve). Atomic reservation chỉ cho **tối đa một** request trong số các bản sao được xử lý, không chứng minh request đến trước là request của người gửi thật; cần TLS và bảo vệ đường truyền.

### 11.4. Nonce đã dùng sau khi authorization fail

Theo pipeline minh họa, nonce được reserve **sau MAC đúng nhưng trước authorization**. Vì thế một request có chữ ký hợp lệ mà thiếu quyền vẫn có thể tiêu tốn nonce; gửi lại cùng nonce sau khi policy thay đổi sẽ bị coi replay.

Đó là một quyết định thiết kế hợp lý nếu “một request đã được nhận và xác thực” là một lần sử dụng nonce. Không được tự đổi thứ tự reserve để “dễ retry” nếu điều đó mở khả năng xử lý cùng request nhiều lần. Với một API cụ thể, có thể chọn reserve trong một giao dịch gắn authorization/business, nhưng phải chứng minh atomicity, failure handling và side effects.

### 11.5. Timing/error oracle không nhất thiết phải lộ ra client

Bên trong verifier có thể log các trạng thái:

~~~text
bad_nonce_format
invalid_key_state
invalid_signature
timestamp_out_of_window
nonce_already_used
nonce_store_unavailable
permission_denied
~~~

Nhưng response công khai nên được thiết kế để **không lộ key tồn tại hay chi tiết MAC**. Thí dụ HTTP 400 cho malformed, 401 cho authentication failure, 403 cho thiếu quyền, 503 khi kho nonce bắt buộc hỏng là lựa chọn thường thấy, không phải quy tắc cố định cho mọi API.

Không trả expected HMAC, secret, stack trace hay thời gian/byte mismatch. Khi log, cẩn trọng với `X-Nonce` vì có thể tăng cardinality, tạo log injection nếu chưa validate và giúp attacker quan sát request IDs; cân nhắc hash/truncate ở logging policy.

## 12. Các bài tập thực hành

**Bài 1 — Phân loại scope:** Cho một nonce `N` và hai authenticated clients A/B. So sánh kết quả theo khóa store `N`, `(client,N)` và `(audience,client,N)`. Cách nào ngăn chặn chéo tenant?

**Bài 2 — Key rotation:** Client A dùng `oldKey` gửi nonce N, sau đó dùng `newKey` ký một request khác vẫn có N. Nếu store key là `(client,keyId,nonce)`, kết quả ra sao? Hãy sửa scope để thực thi chính sách một nonce một lần per-client.

**Bài 3 — Chữ ký giả:** Attacker gửi `X-Client-Id: A`, nonce N và MAC sai. Vì sao server không được reserve N trước khi so HMAC? Viết test cho trường hợp request A thật đến ngay sau.

**Bài 4 — Ngẫu nhiên:** Với nonce 128 bit từ CSPRNG và `q = 10^9` lần sinh trong cùng client, ước tính xác suất collision theo birthday bound. Tại sao nonce theo thời gian millisecond không tương đương 128-bit random?

**Bài 5 — TTL:** Timestamp t được chấp nhận từ `t-300` tới `t+300`. Nếu store reserve ở `t-300` và TTL 300 giây, khi nào replay có thể lọt? Vì sao chọn TTL 660 giây là một phương án minh họa?

**Bài 6 — Redis:** Viết lệnh atomic insert-if-absent cho nonce key với TTL 660 **giây**. Phân biệt `EX 660` với `PX 660` và giải thích vì sao `SETNX` rồi `EXPIRE` là kém an toàn hơn khi crash.

**Bài 7 — Race:** Hai backend cùng nhận request hợp lệ có nonce N và đều `GET` thấy không có key. Điều gì xảy ra nếu cả hai đều ghi `SET`? Làm sao dùng atomic reservation để đảm bảo chỉ một accept?

**Bài 8 — Gateway:** Một request được verify tại edge, rồi backend đọc `X-Verified-Client` từ headers. Attacker tự gửi header này. Hãy thiết kế kênh trusted metadata và quyết định nơi reserve nonce.

**Bài 9 — Multi-region:** Hai vùng có nonce stores chỉ đồng bộ eventual consistency. Cùng nonce có thể được accept ở hai vùng không? Đề xuất consistent reservation hoặc routing strategy.

**Bài 10 — Retry/idempotency:** Client gửi tạo đơn với nonce N1 nhưng timeout dù server đã tạo đơn. Client dùng nonce N2 để retry. Vì sao HMAC và nonce đúng vẫn không đảm bảo “tạo đơn đúng một lần”? Đề xuất signed idempotency key.

**Bài 11 — Authorization:** Merchant A có HMAC đúng, nonce mới nhưng muốn sửa order của Merchant B. Nêu kết quả của replay check và authorization.

**Bài 12 — Key revoked:** Key cũ bị thu hồi sau khi rotation. Một request có MAC tính đúng bằng secret cũ và nonce chưa dùng. Nó có được phép reserve nonce hay không? Vì sao?

## 13. Checklist thiết kế nonce theo client

1. **Principal rõ ràng:** xác minh ownership của client/key/audience; scope từ authenticated client ID, không từ IP hay raw header chưa verify.
2. **Namespace ổn định:** chọn `(audience, authenticatedClientId, nonce)` nếu muốn uniqueness xuyên key rotation và endpoints.
3. **Nonce đủ entropy:** tối thiểu 16 byte CSPRNG theo ví dụ, sinh **mỗi request**; không reuse ở client singleton.
4. **Biểu diễn duy nhất:** Base64URL no-padding 22 ký tự cho 16 byte; strict decode và re-encode; reject padding, invalid alphabet, duplicate headers.
5. **Ký nonce:** đưa nonce cùng method, URI, client/key IDs, timestamp và body digest vào canonical request.
6. **HMAC đúng:** lookup secret của đúng key record, kiểm key state; Base64URL tag 32 byte so bằng `MessageDigest.isEqual`.
7. **Timestamp:** định nghĩa rõ epoch seconds/cửa sổ inclusive; không tự đoán milliseconds.
8. **Atomic reservation:** chỉ sau MAC đúng, đúng một lệnh insert-if-absent với TTL, chia sẻ giữa mọi verifier được phép xác thực cùng client.
9. **TTL an toàn:** bao phủ tối đa timestamp acceptance interval và operational margin; không nhầm Redis seconds/milliseconds.
10. **Không bypass rotation:** dùng cùng nonce namespace xuyên key IDs của cùng client theo hợp đồng.
11. **Fail closed:** không chấp nhận request khi kho nonce bắt buộc không thể xác nhận uniqueness.
12. **Capacity/rate limits:** hạn mức theo client, tránh attacker có key thật làm đầy kho nonce, không xóa record sớm để giải áp lực.
13. **Gateway:** signed fields và principal metadata phải được bảo vệ, không tin `X-Verified-Client` từ internet.
14. **Idempotency:** retry có nonce mới và HMAC mới nhưng dùng idempotency key nhất quán cho cùng thao tác nghiệp vụ.
15. **Authorization:** authenticated client có quyền trên action/resource/tenant thực, không tự cấp quyền vì nonce chưa dùng.
16. **Kiểm thử:** golden fixtures liên client, liên key, concurrency, TTL, key revoke, multi-region failover và HTTP/1.1/2 gateways.

## 14. Kết luận

**Nonce theo client** trả lời câu hỏi: *“Một nonce đã được dùng bởi ai, trong phạm vi dịch vụ nào?”* Trong hợp đồng minh họa, replay key là **`(audience, authenticatedClientId, canonicalNonce)`** — không phải chỉ nonce, không phải IP, cũng không phải `(client,keyId,nonce)` nếu chính sách yêu cầu uniqueness **xuyên key rotation**.

Cơ chế an toàn cần kết hợp **nonce 128-bit CSPRNG**, canonical Base64URL, nonce được ký trong HMAC, timestamp ngắn hạn, **atomic reserve sau MAC hợp lệ**, TTL bao phủ cửa sổ timestamp và **store nhất quán trên mọi verifier**. Hai client khác nhau có thể dùng cùng chuỗi nonce mà không chặn nhau; cùng client tái sử dụng nonce phải bị chặn ngay cả khi chuyển sang key mới. Nonce không thay thế secret/key rotation, TLS, idempotency hay authorization; mỗi cơ chế bảo vệ một ranh giới khác nhau của HTTP request.

**Tài liệu tham khảo:**

- [RFC 2104 — HMAC: Keyed-Hashing for Message Authentication](https://www.rfc-editor.org/rfc/rfc2104): thuật toán HMAC và ý nghĩa tag.
- [RFC 4231 — Test Vectors for HMAC-SHA-256](https://www.rfc-editor.org/rfc/rfc4231): known-answer vectors kiểm chứng engine HMAC độc lập.
- [RFC 4648 — Base-N Encodings](https://www.rfc-editor.org/rfc/rfc4648): Base64URL, padding và canonical pad bits.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): method, URI, HTTP field và semantics.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): request framing và header parsing.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): HTTP/2 pseudo-headers, chuyển giao thức.
- [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421): một chuẩn ký HTTP để tham khảo; `hmac-client-nonce-v1` trong bài là **hợp đồng minh họa riêng**, không tự nhận tuân thủ RFC 9421.
- [Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): tạo nonce ngẫu nhiên bằng CSPRNG.
- [Java SE 17 — javax.crypto.Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): HMAC-SHA-256 từ JCA.
- [Java SE 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): `MessageDigest.isEqual` cho raw tag bytes.
- [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): atomic `compute` trong một JVM; không thay distributed datastore.
- [Redis — SET command](https://redis.io/docs/latest/commands/set/): `NX`, `EX` và `PX` cho atomic nonce reservation (cần cấu hình store production an toàn).





