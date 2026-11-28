# Nonce length trong HMAC Request Authentication

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **nonce** (*number used once*) trong request được ký HMAC và phân biệt **độ dài của bytes**, **số bit ngẫu nhiên thực tế**, **độ dài chuỗi sau encoding** và **tính duy nhất trong phạm vi sử dụng**.
- Lựa chọn một profile rõ ràng: **16 byte ngẫu nhiên sinh bằng CSPRNG = 128 bit**, mã hóa **Base64URL không padding = 22 ký tự ASCII**; không nhầm 22 ký tự với 22 byte ngẫu nhiên.
- Ước lượng xác suất **collision** theo *birthday bound*, hiểu giới hạn của nonce quá ngắn ở hệ thống lưu lượng lớn và những điều xác suất này **không** chứng minh.
- Viết client Java dùng `SecureRandom.nextBytes`, format validator yêu cầu đúng 16 byte sau decode, re-encode để loại Base64URL **không canonical**.
- Ràng buộc **chính nonce text** vào canonical HTTP request và xác minh HMAC-SHA256 với key đúng client/môi trường.
- Thiết kế kho nonce chia sẻ giữa các verifier, thao tác **atomic insert-if-absent**, phạm vi khóa chống replay và TTL đủ che phủ cửa sổ timestamp.
- Phân biệt replay protection, retry/idempotency nghiệp vụ, key rotation và **authorization**; kiểm thử duplicate nonce cả tuần tự lẫn cạnh tranh nhiều replica.

**Ngữ cảnh:** Bài thuộc chương **Nonce** của module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Module thiết kế xác thực HTTP request bằng **shared secret** và **canonical request** gồm method, URI, header hoặc body theo hợp đồng ký, đồng thời xác minh HMAC, chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt xác thực với phân quyền. Chủ đề trung tâm của bài là **Nonce length**: chọn, phát hành, mã hóa và kiểm tra **kích thước nonce** như một phần của giao thức HTTP bảo mật.

> Các header `X-*` và tên profile `hmac-nonce-v1` là **hợp đồng tự định nghĩa để thực hành**. Không có một độ dài nonce duy nhất bắt buộc cho mọi cơ chế HMAC; độ dài phải được đánh giá dựa trên threat model, số request, thời gian sống và thiết kế nonce store.

## 1. Nonce là gì và độ dài liên quan tới bảo mật như thế nào?

Nonce là giá trị mà client gắn vào **mỗi lần ký request mới** để server có thể phát hiện việc dùng lại. Trong mô hình HMAC server-to-server, client sinh nonce, **đưa nó vào thông điệp HMAC**, rồi gửi cho verifier cùng chữ ký.

Ví dụ:

```http
POST /v1/orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-17
X-Key-Id: k2
X-Timestamp: <unix-seconds>
X-Nonce: <22-char-base64url>
X-Signature: <43-char-hmac-tag>

{"orderId":"O-42","amount":120000}
```

Các chuỗi `<...>` là **placeholder**, cần thay bằng giá trị thực. Nonce **không phải secret**: nó xuất hiện trên wire, có thể được log ở mức metadata có kiểm soát và có thể bị người quan sát biết. Bảo vệ quan trọng nằm ở việc nonce **được ký** và verifier **ghi nhớ nonce đã dùng**.

### Ba thuộc tính cần tách biệt

| Thuộc tính | Câu hỏi | Ý nghĩa |
|---|---|---|
| **Unpredictability** | Người ngoài có dự đoán được nonce tiếp theo không? | Liên quan chất lượng CSPRNG, **không chỉ** số ký tự |
| **Collision resistance ở mức xác suất** | Hai request mới vô tình sinh cùng nonce không? | Phụ thuộc số bit entropy và số lần sinh trong cùng scope/window |
| **Replay detection** | Server có nhớ nonce đã được chấp nhận không? | Phụ thuộc **shared atomic nonce store + TTL**, không được giải quyết chỉ bằng nonce dài |

Nếu một client luôn gửi `nonce="AAAAAAAAAAAAAAAAAAAAAA"` thì header **đúng 22 ký tự** và có thể decode thành 16 byte `0x00`, nhưng giá trị ấy **không hề ngẫu nhiên**. Format đúng **không chứng minh entropy**. Khi client dùng lại nonce, server phải reject request thứ hai theo replay policy, ngay cả khi cả hai đều được ký bằng secret hợp lệ.

### Nonce khác timestamp

- **Timestamp** giới hạn thời gian request được xem xét.
- **Nonce** phân biệt các lần request trong cửa sổ ấy.
- **Signature HMAC** bảo vệ nội dung nonce và timestamp, tránh attacker đổi một trong hai mà vẫn dùng tag cũ.
- **Nonce store** khiến cùng nonce không được chấp nhận lần hai trong scope đã định nghĩa.

Một timestamp giống nhau có thể xuất hiện ở hàng nghìn request cùng một giây; đó là bình thường. Các request này vẫn cần **nonce riêng**, không được lấy timestamp làm nonce.

## 2. Nonce length: 16 byte, 128 bit hay 22 ký tự?

Độ dài nên được đặc tả trước tiên bằng **số byte ngẫu nhiên gốc**, vì đây là dữ liệu quyết định không gian giá trị và xác suất collision. Phần text chỉ là cách vận chuyển.

Profile `hmac-nonce-v1`:

```text
nonceBytes    = 16 byte từ CSPRNG
nonceEntropy  ≈ 128 bit nếu mỗi byte uniform và độc lập
nonceText     = Base64URL_NoPadding(nonceBytes)
nonceTextLen  = 22 ký tự ASCII
nonceHeader   = X-Nonce: <nonceText>
```

Vì sao 22 ký tự?

- 16 byte = **128 bit**.
- Base64 mã hóa mỗi nhóm 3 byte thành 4 ký tự; 16 byte gồm 5 nhóm đủ 3 byte và dư 1 byte.
- 5 nhóm đủ → 20 ký tự; 1 byte dư → 2 ký tự có dữ liệu.
- Dạng Base64URL **không padding** có **20 + 2 = 22 ký tự**.
- Base64URL **có padding** sẽ dài **24 ký tự**, kết thúc bằng `==`; profile này **không chấp nhận** padding.

```text
16 raw bytes  --->  22 Base64URL chars (không padding)
             --->  24 Base64URL chars (có "==")
             --->  32 lowercase hex chars nếu chọn hex
```

**22 ký tự Base64URL không có 132 bit entropy.** 22 ký tự có 132 vị trí bit mã hóa, nhưng do chỉ có 128 bit dữ liệu gốc, **4 pad bits ở ký tự cuối phải bằng 0**. Đây là lý do cần re-encode khi xác minh format.

### Bảng quy đổi những độ dài hay được nhắc tới

| Raw nonce bytes | Không gian danh nghĩa | Base64URL không padding | Hex lowercase |
|---:|---:|---:|---:|
| 8 byte | 64 bit | 11 ký tự | 16 ký tự |
| 12 byte | 96 bit | 16 ký tự | 24 ký tự |
| **16 byte** | **128 bit** | **22 ký tự** | **32 ký tự** |
| 24 byte | 192 bit | 32 ký tự | 48 ký tự |
| 32 byte | 256 bit | 43 ký tự | 64 ký tự |

Đây là bảng **kích thước biểu diễn**, không khẳng định mỗi byte trong nonce có entropy tốt. Nếu client dùng một bộ sinh dự đoán được, **16 byte output không đồng nghĩa 128 bit entropy**. Ngược lại, một UUID phiên bản 4 có layout 16 byte nhưng chỉ **122 bit ngẫu nhiên** vì các bit version/variant cố định; không thể tuyên bố UUIDv4 là “128 bit ngẫu nhiên” chỉ vì nó chiếm 16 byte.

### So với độ dài HMAC signature

Một lỗi cấu hình dễ gặp:

```text
X-Nonce:     22 Base64URL chars  -> 16 random bytes
X-Signature: 43 Base64URL chars  -> 32 HMAC-SHA256 tag bytes
```

**Nonce và HMAC tag không phải cùng một loại dữ liệu.** Nonce được **client tự sinh** cho request mới, còn HMAC tag được **tính từ secret và canonical request bytes**. Đừng tái sử dụng `X-Signature` làm nonce, cắt chữ ký thành 16 byte hoặc lấy 22 ký tự đầu của HMAC tag làm “đủ ngẫu nhiên”.

## 3. Độ dài bao nhiêu là đủ? Birthday bound và lưu lượng request

Nếu nonce thực sự được sinh **độc lập, uniform** trên không gian `2^b` giá trị (với `b` bit ngẫu nhiên), xác suất có **ít nhất một collision** sau `n` lần sinh có thể xấp xỉ:

\[
P(\text{collision}) \approx 1-\exp\!\left(-\frac{n(n-1)}{2\cdot 2^b}\right)
\]

Khi xác suất rất nhỏ:

\[
P(\text{collision}) \approx \frac{n(n-1)}{2^{b+1}}
\]

Đây là **birthday bound**. Xác suất collision phụ thuộc vào **số nonce được sinh trong cùng không gian và khoảng lưu**; vì vậy n trong bảng là lượng nonce do các request có cùng scope sinh ra trong khoảng ta cần tránh trùng.

| Số request sinh nonce trong cùng scope | 64 bit | 96 bit | **128 bit** |
|---:|---:|---:|---:|
| 1 triệu (`10^6`) | Khoảng `2,7 × 10^-8` | Khoảng `6,3 × 10^-18` | **Khoảng `1,5 × 10^-27`** |
| 1 tỷ (`10^9`) | Khoảng **2,7%** | Khoảng `6,3 × 10^-12` | **Khoảng `1,5 × 10^-21`** |

Bảng giả định CSPRNG sinh giá trị độc lập/uniform; đây là **ước lượng toán học**, không phải số liệu đo trong hệ thống cụ thể. Với `10^9` giá trị 64 bit, dùng công thức `1-exp(-x)` cho khoảng 2,7%; không dùng gần đúng xác suất nhỏ một cách máy móc khi xác suất lớn.

### Diễn giải đúng về nguy cơ collision

- Một collision ngẫu nhiên **không làm lộ shared secret HMAC**.
- Nếu server dùng nonce store đúng, request thứ hai có nonce đã tồn tại sẽ bị **reject như replay**, gây lỗi availability đối với client hợp lệ.
- Nếu nonce store **không được dùng**, 128 bit nonce vẫn **không chặn** người khác phát lại nguyên request; timestamp và signature không thay đổi.
- Nếu một client liên tục dùng một nonce dự đoán được nhưng **không trùng trong TTL**, replay store vẫn có thể ngăn replay; tuy nhiên **CSPRNG** là lựa chọn đơn giản, ít rủi ro vận hành và giảm khả năng trùng/dự đoán.
- Khi có nhiều client, nonce store có thể scope theo client/principal, khiến collision giữa hai client độc lập không phải duplicate trong cùng scope. Nhưng thiết kế scope không được tạo khe hở cho replay xuyên key rotation hoặc qua audience khác.

Với đa số API server-to-server, **16 byte CSPRNG (128 bit)** là profile thực dụng có dư địa lớn. Một endpoint đặc biệt có lưu lượng/đời sống nonce khác cần tính `n` theo threat model, đo hiệu năng lưu trữ và chọn size như một quyết định **có phiên bản**; không tăng độ dài vô hạn để thay cho nonce store hay rate limiting.

## 4. Sinh nonce đúng cách: CSPRNG thay vì “chuỗi đủ dài”

Trong Java, dùng `java.security.SecureRandom` và `nextBytes`:

```java
import java.security.SecureRandom;
import java.util.Base64;

public final class NonceGenerator {
    private static final SecureRandom CSPRNG = new SecureRandom();

    public static String newNonce() {
        byte[] raw = new byte[16];                // 128 bit output.
        CSPRNG.nextBytes(raw);                   // CSPRNG.
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(raw);            // Đúng 22 ký tự.
    }

    public static void main(String[] args) {
        String nonce = newNonce();
        if (nonce.length() != 22) {
            throw new AssertionError("Wrong nonce length");
        }
        System.out.println("Nonce length: " + nonce.length());
        // Không in nonce của request production vào log tùy tiện.
    }
}
```

Các tiêu chí:

1. Cấp phát **16 byte** và điền bằng CSPRNG. `SecureRandom` nên được khởi tạo qua cấu hình/provider phù hợp với runtime và môi trường vận hành; không tự đặt seed cố định khi tạo nonce production.
2. Dùng `Base64.getUrlEncoder().withoutPadding()` để có **một** wire representation.
3. Sinh nonce **riêng cho từng request mới**, ngay trước bước canonicalize/ký.
4. Không lấy thời gian `System.currentTimeMillis()`, counter từng tiến trình hay `Random` làm nguồn ngẫu nhiên thay thế `SecureRandom`.
5. Không ghép `clientId`, timestamp, tên máy hoặc ID của thread rồi tuyên bố có 128 bit entropy chỉ vì chuỗi có 22 ký tự.
6. Không phụ thuộc vào khả năng các replica/client của nhiều đối tác dùng chung state CSPRNG. Mỗi bên sinh nonce từ CSPRNG của mình; phía server **không thể nhìn format mà biết** client thực sự dùng RNG an toàn.

### Những anti-pattern thường gặp

```java
// SAI/không phù hợp với nonce ngẫu nhiên 128 bit.
String fromTime = Long.toString(System.currentTimeMillis());
String fromCounter = Long.toString(sequence++);
String fromPseudoRandom = Long.toString(new java.util.Random().nextLong());

// UUIDv4 có thể dùng trong protocol KHÁC nhưng format/entropy khác:
// UUID.randomUUID().toString() là 36 ký tự có dấu '-', không phải
// Base64URL không padding của 16 byte CSPRNG tùy ý như profile ở đây.
```

Không phải mọi nonce đều **bắt buộc bí mật hoặc ngẫu nhiên** ở mọi giao thức mật mã. Một số giao thức dùng counter độc nhất theo thiết kế. Nhưng với HTTP HMAC dùng nhiều client và nhiều node, **16 byte CSPRNG + shared nonce store** thường đơn giản hơn việc duy trì counter toàn cục và quản lý reset/restart. Nếu chọn counter, phải có giao thức quản lý uniqueness, scope và crash recovery riêng.

## 5. Hợp đồng wire format cho nonce 16 byte

Để client và verifier không khác nhau khi parse, ta đặc tả `hmac-nonce-v1`:

| Quy tắc | Yêu cầu |
|---|---|
| Header | `X-Nonce`, **đúng một** occurrence trong HTTP request |
| Giá trị | **22 ký tự** thuộc alphabet `A-Z a-z 0-9 - _` |
| Encoding | **Base64URL không padding** |
| Dữ liệu sau decode | **Chính xác 16 byte** |
| Canonical encoding | Decode rồi encode lại phải **trùng đúng text ban đầu** |
| Case | **Phân biệt hoa/thường** trong value; không lowercase |
| Whitespace | Không có whitespace trong value theo profile sau bước HTTP parsing đã quy định |
| Trùng header | Reject `X-Nonce`/`x-nonce` trùng, kể cả giá trị giống nhau |
| Giá trị trống/missing | Reject |
| Format khác | Hex, UUID string, Base64 padded, Base64 chuẩn và percent-encoded nonce đều reject |
| Replay scope | Theo `(environment, audience, authenticated client/principal)`, không tách tùy tiện theo key ID |
| Thời điểm ghi vào store | **Sau HMAC verification**, trước side effect nghiệp vụ |

Regex:

```text
^[A-Za-z0-9_-]{22}$
```

Regex chỉ kiểm tra **alphabet và độ dài text**. Cần decode 16 byte và re-encode để kiểm tra **pad bits**.

### Vì sao re-encode quan trọng?

16 byte có một byte dư khi chia theo nhóm 3 byte Base64, nên ký tự Base64URL cuối chỉ dùng **2 bit dữ liệu cao nhất**; 4 bit thấp là padding ở mức bit và phải bằng 0. Do đó ký tự cuối hợp canonical chỉ có thể là một trong **`A`, `Q`, `g` hoặc `w`**. Điều này là hệ quả của format Base64URL cho 16 bytes, **không phải dấu hiệu RNG kém**.

```text
16 byte all-zero:
    canonical Base64URL unpadded:
    "AAAAAAAAAAAAAAAAAAAAAA"       // 22 ký tự A

Một decoder dễ dãi có thể cho:
    "AAAAAAAAAAAAAAAAAAAAAB"       // pad bits sai
decode ra cùng 16 byte.
```

Khi đó re-encode kết quả decode ra chuỗi canonical kết thúc bằng `A`, khác chuỗi nhận kết thúc bằng `B`; verifier phải từ chối. `"AAAAAAAAAAAAAAAAAAAAAA"` chỉ là **ví dụ format**, không phải nonce tốt để sử dụng lặp.

### Java decoder nghiêm ngặt

```java
import java.util.Base64;
import java.util.regex.Pattern;

public final class NonceFormat {
    private static final Pattern NONCE =
            Pattern.compile("[A-Za-z0-9_-]{22}");
    private static final Base64.Encoder ENCODER =
            Base64.getUrlEncoder().withoutPadding();

    public static byte[] parse16ByteNonce(String text) {
        if (text == null || !NONCE.matcher(text).matches()) {
            throw new IllegalArgumentException("Invalid nonce format");
        }
        final byte[] decoded;
        try {
            decoded = Base64.getUrlDecoder().decode(text);
        } catch (IllegalArgumentException malformed) {
            throw new IllegalArgumentException("Invalid Base64URL");
        }
        if (decoded.length != 16 ||
                !ENCODER.encodeToString(decoded).equals(text)) {
            throw new IllegalArgumentException("Noncanonical nonce");
        }
        return decoded;
    }
}
```

**Không** so nonce text với expected HMAC tag. Nonce là **metadata input của phép ký và của replay store**, còn signature là đầu ra 32 byte của HMAC-SHA256, được kiểm tra bằng phép so tag nhị phân.

## 6. Nonce phải nằm trong canonical request được HMAC ký

Giả sử client gửi:

```http
POST /v1/orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
Idempotency-Key: order-20261128-01
X-Client-Id: partner-17
X-Key-Id: k2
X-Timestamp: <unix-seconds-hien-tai>
X-Nonce: <nonce-22-char-base64url>
X-Signature: <signature-43-char-base64url>

{"orderId":"O-42","amount":120000}
```

Trong contract `hmac-nonce-v1`, canonical string có các dòng:

```text
hmac-nonce-v1
POST
/v1/orders
host:api.example.test
content-type:application/json
idempotency-key:order-20261128-01
x-client-id:partner-17
x-key-id:k2
x-timestamp:<unix-seconds-hien-tai>
x-nonce:<nonce-22-char-base64url>
body-sha256:<base64url-sha256-exact-raw-body>
```

**Quy tắc byte-level**:

- Dòng có thứ tự cố định, phân tách bằng **LF** (`0x0A`), không thêm newline cuối.
- Canonical text được mã hóa thành **UTF-8 không BOM**.
- Method và raw request-target được lấy từ **HTTP request thực tế**; với profile này chỉ nhận `POST /v1/orders` không query.
- Host là **authority công khai đã được ingress tin cậy kiểm tra**; không tin `X-Forwarded-Host` từ client.
- `Content-Type` và `Idempotency-Key` được ký vì chúng ảnh hưởng cách parse và xử lý retry.
- `X-Client-Id`, `X-Key-Id`, timestamp **và nonce** đều được đưa vào thông điệp ký.
- Body hash = `Base64URL_NoPadding(SHA256(exactRawBodyBytes))`.
- Signature = `Base64URL_NoPadding(HMAC-SHA256(secret, UTF8(canonicalString)))`; nó **không** tự xuất hiện trong canonical string.

### Nếu nonce không được ký thì chuyện gì xảy ra?

Mô hình sai:

```text
HMAC(K, method + path + bodyDigest + timestamp)
X-Nonce: không nằm trong dữ liệu HMAC
```

Attacker ghi lại một request hợp lệ, rồi thay `X-Nonce` bằng chuỗi **22 ký tự mới** mà giữ signature cũ. Nếu HMAC không phụ thuộc nonce, verifier có thể thấy signature vẫn đúng trong cửa sổ timestamp và nonce store có thể coi nonce mới là chưa được dùng. Đây là một **replay bypass** do **thiếu ràng buộc nonce vào MAC**.

Khi nonce được ký, chỉ thay một ký tự trong nonce sau bước ký sẽ đổi canonical bytes và expected HMAC tag. Verifier reject trước khi ghi nonce.

### Có nên dùng nonce raw bytes hay text để ký?

Cả hai đều có thể thiết kế đúng **nếu hợp đồng byte-level rõ ràng**. Profile này chọn ký **nonce text Base64URL canonical** như nó xuất hiện trong header, vì:

1. ASCII text dễ đưa vào canonical lines.
2. Decode/re-encode bắt buộc duy nhất một biểu diễn cho 16 bytes.
3. Client và verifier có một giá trị text rõ ràng để ký/tra nonce store.

Không được để client ký text, còn server decode rồi lấy `new String(randomBytes, UTF_8)` hoặc hex hóa mới để HMAC. Không tự lowercase chuỗi nonce hay cho phép cả padded/unpadded vì đó là hai thông điệp ký khác nhau.

## 7. Chống replay: độ dài nonce chỉ hiệu quả cùng shared atomic store

Một nonce dài 128 bit có thể bị attacker phát lại **nguyên vẹn**. Nếu server không lưu nonce đã chấp nhận, nó sẽ không biết request đã được xử lý.

```mermaid
sequenceDiagram
    autonumber
    participant C as HMAC Client
    participant G as Gateway
    participant V as HMAC Verifier
    participant K as Key Store
    participant N as Shared Nonce Store
    participant B as Backend
    C->>C: Generate 16 random bytes, Base64URL 22 chars
    C->>C: Timestamp + nonce vào canonical bytes, ký HMAC
    C->>G: HTTPS request + X-Nonce + X-Signature
    G->>V: Validate HTTP headers, target, body and public Host
    V->>V: Decode nonce 16B, signature 32B; validate time-window
    V->>K: Lookup(env, clientId, keyId, audience)
    K-->>V: Active/verify-only key + principal + secret
    V->>V: Server-side canonical request + HMAC comparison
    alt Key hoặc HMAC không hợp lệ
        V-->>G: Reject authentication
    else HMAC hợp lệ
        V->>N: Atomic insert-if-absent(scope, nonce, TTL)
        alt Nonce đã tồn tại / store lỗi
            V-->>G: Reject replay / fail closed
        else Claim thành công
            N-->>V: Claimed
            V->>B: Trusted principal + signed request context
            B->>B: Authorization + idempotency + transaction
            B-->>G: Business response
        end
    end
```

### Replay scope nên chứa gì?

Một khóa nonce store có thể đại diện:

```text
(environment, audience, authenticated-client-id, nonce)
```

Khi client `partner-17` có secret `k1` và `k2` đang overlap, **không nên** tách nonce namespace theo `keyId` một cách cho phép request ký bởi cùng client lặp lại qua key khác. Nếu nonce scope theo authenticated principal thay vì client ID, cần đảm bảo việc ánh xạ principal không nhập nhằng và key ownership đã verify.

- **Environment** phân biệt sandbox/production.
- **Audience/service** ràng buộc nơi request được phép xử lý.
- **Client/principal** lấy từ key record **sau khi verify**, không tin một `X-Client-Id` tự khai làm danh tính.
- **Nonce** chính là 22 ký tự Base64URL đã validate; hoặc bản mã hóa khác của 16 bytes có nghĩa duy nhất, dùng nhất quán.

Một số hệ thống dùng **global nonce namespace** và cũng an toàn về replay nếu thực hiện đúng, nhưng có thể tốn bộ nhớ hơn hoặc khiến hai client vô tình dùng cùng nonce ảnh hưởng lẫn nhau. Scope phải được thiết kế nhất quán với cả **key rotation**, load balancing và multi-region.

### Vì sao ghi nonce phải nguyên tử?

Mẫu sai:

```text
Replica A: GET nonce -> not found
Replica B: GET nonce -> not found
Replica A: SET nonce -> accepted
Replica B: SET nonce -> accepted   // cùng request được xử lý hai lần
```

Phải dùng một thao tác **insert-if-absent có TTL nguyên tử** ở kho chia sẻ. Với Redis, ý tưởng tương ứng là `SET key value NX EX seconds`; với SQL, có thể dùng unique constraint và giao dịch phù hợp. Đây là **mô tả thiết kế**, không phải khẳng định bất kỳ Redis/SQL topology nào tự bảo đảm an toàn khi failover, phân vùng mạng hoặc mất state.

**Điểm bắt buộc:** việc claim nonce chỉ diễn ra **sau** khi HMAC hợp lệ. Nếu ghi nonce trước verify, attacker có thể gửi tag sai cùng một nonce để “chiếm” nonce mà client thực sự chuẩn bị dùng, gây denial of service.

## 8. Cửa sổ timestamp và thời gian giữ nonce (TTL)

Giả sử verifier dùng timestamp `t` (Unix epoch seconds), clock server `now` và cửa sổ đối xứng **`W = 300` giây**:

\[
now-W\leq t\leq now+W
\]

Kho nonce phải giữ dấu vết **cho tới khi request có timestamp `t` không thể còn hợp lệ nữa**. Nếu nonce được claim lúc request đến **sớm nhất** `now=t-W`, cùng timestamp vẫn còn hợp lệ tới **`now=t+W`**.

```text
Request timestamp:                    t
Server earliest valid arrival:       t-W
Server latest valid arrival:         t+W
Maximum validity span:               2W

Với W = 300s:
t-300 --------- t --------- t+300
        tổng cửa sổ 600 giây
```

### Lỗi TTL một cửa sổ

Nếu hệ thống claim nonce tại `t-300` nhưng chỉ đặt TTL `300` giây, nonce có thể biến mất ở khoảng `t`, trong khi request vẫn được chấp nhận về timestamp tới `t+300`. Attacker phát lại nguyên request vào đoạn sau và có thể được chấp nhận lần nữa.

Với **fixed TTL tính từ lúc claim**, một quy tắc an toàn hơn trong profile là:

```text
nonceTTL >= 2*W + safetyMargin
         >= 600s + safetyMargin
```

Ví dụ **605 giây** trong bài lab có policy clock/TTL nhất quán và margin 5 giây. Đó **không phải** giá trị luôn đủ cho mọi hệ thống: nếu đồng hồ replica lệch đáng kể, TTL resolution, replication/failover hoặc retry latency có thể khiến cần margin lớn hơn.

**Lựa chọn khác:** tính expiry theo deadline của timestamp, ví dụ `t + W + margin`, với store dùng clock đáng tin thống nhất; TTL phải bảo đảm dấu vết không mất trước khi request bị loại tại mọi verifier replica.

### Nonce dài có cần TTL dài hơn không?

Không trực tiếp. **Nonce length** quyết định xác suất collision; **TTL** quyết định thời gian nhớ một nonce để chặn replay. Tăng từ 16 byte lên 32 byte **không** bù đắp TTL quá ngắn hoặc nonce store không phân tán. Ngược lại, TTL tăng làm kho phải lưu nhiều nonce đồng thời; cần sizing theo:

```text
số nonce đồng thời ≈ request hợp lệ mỗi giây * TTL (giây)
```

Ví dụ một client tạo `1000` request/giây, TTL `605` giây thì kho có thể cần giữ khoảng **605.000 nonce** cho client đó ở trạng thái ổn định, chưa tính key/metadata và overhead. Điều này ảnh hưởng bộ nhớ/chi phí và kiến trúc store, **không thay đổi** cơ sở toán học của nonce 128 bit.

## 9. Java 17+: sinh, kiểm tra độ dài và xác minh nonce cùng HMAC

Ví dụ sau mô tả một profile server-to-server cho `POST /v1/orders`. Nội dung Java tập trung vào **nonce 16-byte/22-character**, **encoding canonical**, **signed nonce** và **shared nonce store interface**. Để thấy đúng thứ tự bảo mật, ví dụ có cả scoped key lookup và so HMAC tag.

### 9.1. Ví dụ Java tự chứa

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Pattern;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class NonceLengthHmacV1 {
    private static final String VERSION = "hmac-nonce-v1";
    private static final String HOST = "api.example.test";
    private static final String TARGET = "/v1/orders";
    private static final String AUDIENCE = "orders-api";
    private static final long CLOCK_WINDOW = 300L;
    private static final long NONCE_TTL_SECONDS = 605L;
    private static final long MAX_EPOCH_SECONDS = 253402300799L;

    private static final Pattern ID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");
    private static final Pattern TS =
            Pattern.compile("(?:0|[1-9][0-9]{0,11})");
    private static final Pattern NONCE =
            Pattern.compile("[A-Za-z0-9_-]{22}");
    private static final Pattern SIGNATURE =
            Pattern.compile("[A-Za-z0-9_-]{43}");
    private static final Base64.Encoder B64 =
            Base64.getUrlEncoder().withoutPadding();

    private NonceLengthHmacV1() {}

    // Tạo 16 byte CSPRNG -> 22 ký tự Base64URL không padding.
    public static String newNonce(SecureRandom rng) {
        byte[] bytes = new byte[16];
        rng.nextBytes(bytes);
        return B64.encodeToString(bytes);
    }

    // Check cả length text, 16 raw bytes và pad bits canonical.
    public static byte[] decodeNonce(String text) {
        return decodeCanonical(text, NONCE, 16);
    }

    private static byte[] decodeCanonical(
            String text, Pattern pattern, int exactBytes) {
        if (text == null || !pattern.matcher(text).matches()) {
            throw new IllegalArgumentException("Invalid Base64URL grammar");
        }
        final byte[] bytes;
        try {
            bytes = Base64.getUrlDecoder().decode(text);
        } catch (IllegalArgumentException malformed) {
            throw new IllegalArgumentException("Malformed Base64URL");
        }
        if (bytes.length != exactBytes ||
                !B64.encodeToString(bytes).equals(text)) {
            throw new IllegalArgumentException("Noncanonical Base64URL");
        }
        return bytes;
    }

    public record RequestSnapshot(
            String method, String rawTarget, String publicHost,
            String contentType, String idempotencyKey,
            String clientId, String keyId, String timestamp,
            String nonce, byte[] rawBody) {
        public RequestSnapshot {
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

    public record KeyRecord(
            String environment, String clientId, String keyId,
            String audience, String principal, boolean canVerify,
            byte[] secret) {}

    public interface KeyStore {
        Optional<KeyRecord> find(
                String env, String clientId, String keyId, String audience);
    }

    // Production: shared atomic insert-if-absent + TTL, fail closed on error.
    public interface NonceStore {
        boolean claim(String scope, String nonce, long ttlSeconds);
    }

    private static long parseTimestamp(String text) {
        if (text == null || !TS.matcher(text).matches()) {
            throw new IllegalArgumentException("Bad timestamp format");
        }
        long t = Long.parseLong(text);
        if (t > MAX_EPOCH_SECONDS) {
            throw new IllegalArgumentException("Unsupported timestamp");
        }
        return t;
    }

    private static void validate(RequestSnapshot r) {
        if (r == null ||
                !"POST".equals(r.method()) ||
                !TARGET.equals(r.rawTarget()) ||
                !HOST.equals(r.publicHost()) ||
                !"application/json".equals(r.contentType()) ||
                r.idempotencyKey() == null ||
                !ID.matcher(r.idempotencyKey()).matches() ||
                r.clientId() == null ||
                !ID.matcher(r.clientId()).matches() ||
                r.keyId() == null ||
                !ID.matcher(r.keyId()).matches() ||
                r.rawBody().length == 0 ||
                r.rawBody().length > 16 * 1024) {
            throw new IllegalArgumentException("Invalid signed fields");
        }
        parseTimestamp(r.timestamp());
        decodeNonce(r.nonce());
    }

    public static byte[] canonicalBytes(RequestSnapshot r)
            throws GeneralSecurityException {
        validate(r);
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(r.rawBody());

        String canonical = String.join("\n",
                VERSION,
                "POST",
                TARGET,
                "host:" + HOST,
                "content-type:application/json",
                "idempotency-key:" + r.idempotencyKey(),
                "x-client-id:" + r.clientId(),
                "x-key-id:" + r.keyId(),
                "x-timestamp:" + r.timestamp(),
                "x-nonce:" + r.nonce(),  // Chính text Base64URL đã validate.
                "body-sha256:" + B64.encodeToString(digest));

        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] hmac(
            byte[] secret, RequestSnapshot r)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(canonicalBytes(r));
    }

    // Dành cho client/test; server production chỉ verify.
    public static String signForTest(
            byte[] secret, RequestSnapshot r)
            throws GeneralSecurityException {
        return B64.encodeToString(hmac(secret, r));
    }

    // Trả principal chỉ khi HMAC hợp lệ và nonce chưa claim.
    public static Optional<String> authenticate(
            RequestSnapshot r, String signature, Clock clock,
            String serverEnvironment, KeyStore keys, NonceStore nonces)
            throws GeneralSecurityException {

        final byte[] receivedTag;
        try {
            validate(r);
            receivedTag = decodeCanonical(
                    signature, SIGNATURE, 32);
        } catch (IllegalArgumentException malformed) {
            return Optional.empty();
        }

        long t = parseTimestamp(r.timestamp());
        long now = clock.instant().getEpochSecond();
        if (now < 0 || now > MAX_EPOCH_SECONDS ||
                t - now < -CLOCK_WINDOW ||
                t - now > CLOCK_WINDOW) {
            return Optional.empty();
        }

        // client/key ID chưa tin cậy; chỉ dùng để lookup key ứng viên.
        Optional<KeyRecord> candidate = keys.find(
                serverEnvironment, r.clientId(), r.keyId(), AUDIENCE);
        if (candidate.isEmpty()) return Optional.empty();

        KeyRecord k = candidate.get();
        if (!k.canVerify() ||
                !serverEnvironment.equals(k.environment()) ||
                !AUDIENCE.equals(k.audience()) ||
                !r.clientId().equals(k.clientId()) ||
                !r.keyId().equals(k.keyId()) ||
                k.principal() == null ||
                k.secret() == null || k.secret().length < 32) {
            return Optional.empty();
        }

        byte[] expectedTag = hmac(k.secret(), r);
        if (!MessageDigest.isEqual(expectedTag, receivedTag)) {
            return Optional.empty();
        }

        // Không chia nonce namespace theo keyId: giữ qua rotation.
        String scope = serverEnvironment + "|" + AUDIENCE +
                "|" + k.clientId();

        final boolean fresh;
        try {
            fresh = nonces.claim(scope, r.nonce(), NONCE_TTL_SECONDS);
        } catch (RuntimeException unavailableStore) {
            return Optional.empty(); // Fail closed; log operational error.
        }
        if (!fresh) return Optional.empty();

        return Optional.of(k.principal()); // Authentication, chưa authz.
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        SecureRandom rng = new SecureRandom();
        String nonce = newNonce(rng);
        if (nonce.length() != 22 ||
                decodeNonce(nonce).length != 16) {
            throw new AssertionError("Nonce format incorrect");
        }

        byte[] secret = new byte[32];
        rng.nextBytes(secret); // Demo provisioning.
        Clock fixed = Clock.fixed(
                Instant.parse("2026-11-28T00:00:00Z"), ZoneOffset.UTC);

        RequestSnapshot r = new RequestSnapshot(
                "POST", TARGET, HOST, "application/json",
                "order-20261128-01", "partner-17", "k2",
                Long.toString(fixed.instant().getEpochSecond()),
                nonce,
                "{\"orderId\":\"O-42\",\"amount\":120000}"
                        .getBytes(StandardCharsets.UTF_8));

        KeyStore keys = (env, client, kid, audience) ->
                "production".equals(env) &&
                "partner-17".equals(client) &&
                "k2".equals(kid) &&
                AUDIENCE.equals(audience)
                ? Optional.of(new KeyRecord(
                    env, client, kid, audience, "partner-17", true, secret))
                : Optional.empty();

        // Chỉ fixture một process: không TTL, không shared giữa replica.
        Set<String> used = ConcurrentHashMap.newKeySet();
        NonceStore store = (scope, value, ttl) ->
                used.add(scope + "|" + value);

        String sig = signForTest(secret, r);
        if (!"partner-17".equals(authenticate(
                r, sig, fixed, "production", keys, store).orElse(null))) {
            throw new AssertionError("Valid request rejected");
        }

        // Tag vẫn đúng nhưng nonce đã được claim: phải reject.
        if (authenticate(r, sig, fixed, "production",
                keys, store).isPresent()) {
            throw new AssertionError("Replay accepted");
        }

        // Sửa nonce sau khi ký, giữ tag cũ: phải reject HMAC.
        RequestSnapshot changedNonce = new RequestSnapshot(
                r.method(), r.rawTarget(), r.publicHost(),
                r.contentType(), r.idempotencyKey(),
                r.clientId(), r.keyId(), r.timestamp(),
                newNonce(rng), r.rawBody());
        if (authenticate(changedNonce, sig, fixed, "production",
                keys, store).isPresent()) {
            throw new AssertionError("Nonce tampering accepted");
        }

        for (String invalid : new String[] {
                "", "AAAAAAAAAAAAAAAAAAAAA",
                "AAAAAAAAAAAAAAAAAAAAAAA",
                "AAAAAAAAAAAAAAAAAAAAAA==",
                "AAAAAAAAAAAAAAAAAAAAAB"
        }) {
            try {
                decodeNonce(invalid);
                throw new AssertionError("Accepted invalid nonce: " + invalid);
            } catch (IllegalArgumentException expected) {
                // PASS.
            }
        }
        System.out.println("Nonce length + replay checks: PASS");
    }
}
```

### 9.2. Điều mã đã mô phỏng

1. **Sinh nonce:** 16 bytes từ `SecureRandom` → Base64URL không padding 22 ký tự.
2. **Validate nonce:** regex độ dài/character set, decode đúng 16 byte, re-encode phải khớp text.
3. **Ký nonce:** `x-nonce:` + chính nonce text đã validate nằm trong canonical UTF-8 bytes và được HMAC-SHA256 bảo vệ.
4. **Signature riêng:** HMAC-SHA256 trả tag **32 byte** → Base64URL 43 ký tự, được decode canonical trước khi so bằng `MessageDigest.isEqual`.
5. **Scoped key lookup:** tra theo `environment + clientId + keyId + audience`, kiểm tra owner/state, tạo principal **chỉ sau** khi tag khớp.
6. **Timestamp window:** timestamp parse theo seconds với clock server, reject ngoài ±300 giây.
7. **Replay gate:** kiểm tra nonce store **sau HMAC**, với scope không chứa key ID để giữ xuyên key rotation.
8. **Negative tests:** nonce sai độ dài, padding, pad bits sai, nonce bị thay sau ký và nonce lặp lại.

### 9.3. Những việc HTTP adapter/production phải bổ sung

Code giả định `RequestSnapshot` do một HTTP adapter đáng tin tạo từ request **thực nhận**. Adapter phải kiểm soát:

- Đúng một `X-Nonce`, `X-Signature`, `X-Timestamp`, `X-Key-Id`, `X-Client-Id`, `Host`/`:authority` và các signed headers; reject duplicate hoặc ambiguous values.
- Method/path/query, content type, content encoding, HTTP framing và raw body bytes; không tự serialize body lại sau ký/verify.
- Public Host tin cậy qua proxy; không dùng `X-Forwarded-Host` tự khai để chọn audience.
- Body size, header count/length, CPU/timeout, rate limit và log redaction.
- Key store/KMS thực tế, key state/rotation/revocation, nonce store **chia sẻ nhiều replica** có **atomic claim + TTL** và xử lý failover.
- Backend dùng principal/context đã xác minh và thực hiện **authorization** theo resource/action/tenant. `authenticate()` ở ví dụ chưa gọi service phân quyền.

`ConcurrentHashMap.newKeySet()` trong `main` chỉ là test fixture: nó không expire nonce, không durable và không dùng chung giữa các process. Chạy ứng dụng đa replica với biến toàn cục kiểu `Set` như vậy **không** đáp ứng replay protection.

## 10. Các tình huống nonce length dễ bị hiểu sai

### 10.1. Sinh 22 ký tự từ alphabet 64 có bằng 16-byte CSPRNG không?

Nếu bạn chọn **22 ký tự** độc lập/uniform từ alphabet Base64URL 64 ký tự thì không gian danh nghĩa là `64^22 = 2^132`, khác với **`2^128` raw bytes → 22-char encoding canonical**.

Trong profile 16-byte Base64URL, **4 pad bits ở ký tự cuối cố định 0**. Do đó không phải mọi chuỗi 22 ký tự bất kỳ đều là encoding canonical của 16 byte. Một “nonce generator” tạo 22 ký tự ngẫu nhiên trực tiếp có thể cho một chuỗi hợp regex nhưng **re-encode sai canonical**; verifier cần reject.

**Cách đúng:** sinh **16 byte ngẫu nhiên trước**, rồi Base64URL-encode. Đừng đảo quy trình.

### 10.2. Timestamp có thể thay nonce để tiết kiệm bytes không?

Không, trừ khi giao thức được thiết kế với cơ chế uniqueness khác có kiểm chứng. Nhiều request có thể cùng timestamp seconds; nếu dùng timestamp làm nonce, request hợp lệ thứ hai sẽ bị chặn hoặc hệ thống phải nới replay protection. Nếu chỉ ký timestamp mà không lưu nonce, attacker có thể replay cả request trong cùng cửa sổ.

### 10.3. Độ dài dài hơn có ngăn được attacker phát lại không?

Không. Attacker có bản sao nguyên request mang nonce 256 bit vẫn có thể phát lại **đúng nonce đó**. Chỉ **nonce store** mới phát hiện lần dùng lại. Nonce dài hơn chủ yếu làm **collision tình cờ** kém xảy ra hơn nếu generation tốt; còn chữ ký HMAC ngăn việc thay nonce mà không biết secret.

### 10.4. Không có nonce store nhưng nonce rất dài thì sao?

Không có cơ sở chặn replay của cùng request. Nonce được đưa vào HMAC chỉ chứng minh giá trị nonce không bị sửa, **không chứng minh đã được dùng hay chưa**. Ghi nonce vào log không thay thế một thao tác claim nguyên tử.

### 10.5. Client khởi động lại, reset counter thì sao?

Với counter nonce không có persistent state, việc restart có thể làm lặp nonce. Với CSPRNG đúng cách, mỗi request mới tự sinh 16 byte không phụ thuộc counter; collision vẫn có xác suất nhưng cực nhỏ theo phân tích trên. Tuy nhiên, phải bảo đảm môi trường entropy/DRBG vận hành đúng, không clone trạng thái RNG cố định trên nhiều máy.

### 10.6. Có nên lưu nonce hashed trong store?

Có thể lưu hash/encoded fingerprint để giảm exposure trong log/store key, nhưng **đó không thay thế replay uniqueness**. Nếu hash bị cắt ngắn quá mức, hai nonce khác nhau có thể va chạm và gây false rejects. Khi dùng hash, phải có cách định nghĩa scope, hash length, collision policy và TTL đầy đủ; không tự lấy vài ký tự đầu của nonce làm khóa store.

## 11. Replay, retry, key rotation và authorization: bốn bài toán khác nhau

### Replay một request đã ký

- Kẻ quan sát gửi lại **toàn bộ request** gồm nonce, timestamp, signature.
- Expected HMAC có thể vẫn khớp.
- Nonce store phải từ chối vì nonce trong scope đã được claim.
- Nếu attacker gửi bản sao trước khi request hợp lệ đến nơi, **first accepted claim wins**: client hợp lệ có thể nhận lỗi trùng nonce. Nonce dài không loại bỏ khả năng race/DoS này; TLS, hạn chế quan sát traffic và thiết kế vận hành là cần thiết.

### Retry sau timeout

- Client gửi lại **y nguyên**: nonce trùng, request thường bị replay gate reject.
- Client tạo nonce mới/timestamp mới và **ký lại**: replay gate xem là request mới.
- Nếu thao tác tạo đơn/thanh toán đã được thực hiện trước khi response mất, request mới có thể gây side effect trùng.
- Giải pháp riêng: **Idempotency-Key đã ký** và kho trạng thái idempotency/giao dịch atomically gắn với principal và nội dung yêu cầu.

Nonce không phải idempotency key, dù cả hai có vẻ là chuỗi “unique”. Nonce nhằm chống **cùng signed request xuất hiện lần nữa**; idempotency nhằm chống **cùng thao tác nghiệp vụ xảy ra nhiều lần**, kể cả khi request có nonce mới.

### Key rotation

Trong quá trình client chuyển từ `k1` sang `k2`, verifier có thể tạm chấp nhận cả hai theo key lifecycle. **Nonce namespace không nên được reset theo key ID** cho cùng client/audience khi điều đó tạo khe hở cho replay xuyên phiên bản khóa.

- Lookup secret theo `(environment, clientId, keyId, audience)`.
- `keyId` nằm trong canonical request.
- Key bị thu hồi phải từ chối ngay theo chính sách dù nonce còn mới, HMAC có thể tính đúng bằng secret cũ.
- Khi secret bị lộ, attacker có thể tạo **nonce ngẫu nhiên mới và signature mới**. Nonce store không bảo vệ khỏi người có secret; cần thu hồi/rotation, hạn chế quyền và audit.

### Authentication và authorization

Một client hợp lệ có thể ký request với nonce dài 128 bit để thao tác trên đơn của tenant khác. HMAC có thể đúng và nonce còn mới, nhưng backend vẫn phải kiểm tra **authenticated principal** có quyền với **resource/action/tenant** thực tế. Không coi nonce dài hoặc signature đúng là giấy phép truy cập toàn hệ thống.

## 12. Ma trận kiểm thử độ dài nonce và toàn pipeline

| Test | Input hoặc hành vi | Kỳ vọng theo `hmac-nonce-v1` |
|---|---|---|
| CSPRNG 16 byte | `SecureRandom.nextBytes(new byte[16])` rồi Base64URL | **22 ký tự**, decode ra **16 byte** |
| Nonce 12 byte | Base64URL 16 ký tự | Reject format |
| Nonce 8 byte | Base64URL 11 ký tự | Reject format |
| Nonce 24 byte | Base64URL 32 ký tự | Reject format |
| Nonce 32 byte | Base64URL 43 ký tự | Reject format **nonce**, dù 43 chars là signature length |
| Hex của 16 byte | Hex 32 ký tự | Reject format |
| UUIDv4 text | `xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx` | Reject; profile không nhận UUID text |
| Base64URL padded | 24 ký tự, kết thúc `==` | Reject |
| Base64 thường có `+`/`/` | Alphabet không thuộc profile | Reject |
| Base64URL có whitespace | `nonce + " "` hoặc newline | Reject sau HTTP parsing theo policy |
| Nonce rỗng/missing | Không có `X-Nonce` hoặc giá trị `""` | Reject |
| Header nonce trùng | Hai `X-Nonce` dù khác header-name case | Reject tại HTTP adapter |
| Noncanonical pad bits | 21 chữ `A` và `B` cuối | Reject sau decode → re-encode |
| Canonical zero nonce | 22 chữ `A` | **Pass format**, nhưng không đạt policy generation ngẫu nhiên nếu dùng cố định |
| Sai timestamp format | Milliseconds, leading zero, ISO string | Reject theo timestamp profile |
| Nonce bị đổi sau ký | Client ký A, attacker thay `X-Nonce` thành B | **HMAC mismatch** |
| Signature bị đổi | Chỉ thay tag, giữ nonce | HMAC mismatch |
| Nonce dùng một lần | Request/tag/nonce hợp lệ lần đầu | Claim thành công; tiếp tục backend nếu authz pass |
| Replay tuần tự | Gửi lại nguyên request, cùng nonce | Reject ở replay gate |
| Replay hai replica | Hai request cùng principal/nonce đồng thời | **Tối đa một** atomic claim thành công |
| TTL quá ngắn | Claim khi `now=t-W`, replay gần `t+W` | Test phải phát hiện lỗ replay |
| Retry với nonce mới | Cùng Idempotency-Key và payload, timestamp/nonce/tag mới | Replay gate có thể pass; idempotency nghiệp vụ ngăn lặp |
| Duplicate giữa hai client | Hai client vô tình dùng cùng nonce text | Kết quả theo scope đã công bố; không vô tình gộp hai principal |
| Key thay phiên bản | Cùng client chuyển từ `k1` sang `k2` | Nonce namespace nhất quán qua rotation |
| Key revoke | HMAC tính đúng bằng secret cũ | Reject key state |
| Host/path/body rewrite | Proxy đổi signed field | Reject hoặc MAC mismatch; không thực thi sai đích |
| Backend bypass | Client giả header principal nội bộ | Không thể bỏ qua verifier |
| HMAC đúng nhưng sai tenant | Client hợp lệ gọi resource không được phép | Authn pass; **authz deny** |

### Test xác suất không chứng minh entropy

Một unit test thấy 10.000 nonce được sinh ra **khác nhau** không chứng minh CSPRNG có 128 bit entropy. Một bộ sinh counter cũng cho 10.000 chuỗi khác nhau. Test chức năng nên kiểm tra **số bytes, encoding, grammar, duplicate/replay behavior và nguồn RNG được dùng trong implementation**; kiểm chứng DRBG/provider/entropy thuộc thiết kế bảo mật và vận hành, không thể chứng minh bằng vài phép assert.

### Test ở ba cấp độ

1. **Unit:** sinh 16 byte, decode 22 ký tự, reject padded/noncanonical/31-character hex, test nonce tampering làm HMAC mismatch.
2. **Integration:** shared nonce store có unique claim atomically và TTL; chạy cạnh tranh thật qua nhiều process/replica, thử store unavailable và clock skew.
3. **End-to-end:** HTTP client → CDN/gateway → verifier → backend; header cardinality, Host/`:authority`, URI/body canonicalization, key rotation, authz/idempotency. HMAC đúng ở unit test không chứng minh request được xử lý an toàn qua proxy.

## 13. Bài tập thực hành: chọn Nonce length cho API nhiều đối tác

Một hệ thống `orders-api` có nhiều client server-to-server gọi `POST /v1/orders`. Mỗi client dùng HMAC-SHA256 với secret riêng; verifier có ba replica ở hai vùng triển khai, chạy sau API gateway. Timestamp được ký và chấp nhận cửa sổ `±300` giây; nonce store dùng chung, key rotation từ `k1` sang `k2`.

**Yêu cầu triển khai:**

1. **Chốt format:** chọn **16 byte CSPRNG → 22 ký tự Base64URL không padding**. Viết bảng phân biệt nonce 16 byte, 128 bit và tag HMAC 32 byte/43 ký tự.
2. **Lập luận xác suất:** tính approximate birthday collision khi một client sinh `10^6` rồi `10^9` nonce trong cùng phạm vi. So với 64/96/128 bit và giải thích điều đó ảnh hưởng availability chứ không tự cấp khả năng giả mạo HMAC.
3. **Viết Java generator:** dùng `SecureRandom.nextBytes` với `byte[16]`, encode Base64URL không padding; không dùng `Random`, timestamp hoặc UUID text thay thế tùy tiện.
4. **Viết strict parser:** yêu cầu đúng 22 ASCII chars, decode đúng 16 bytes, re-encode bằng Base64URL rồi so text để loại noncanonical pad bits. Test `22 chữ A` và `21 chữ A + B`.
5. **Viết canonical request:** chứa version, method, URI thực tế, Host tin cậy, signed headers, timestamp, **nonce**, SHA-256 raw body, LF/UTF-8. Chứng minh sửa nonce sau ký làm HMAC fail.
6. **Dùng scoped KeyStore:** tra đúng `(env, clientId, keyId, audience)` và key state trước khi so 32-byte HMAC tag; principal chỉ được tạo **sau verify**.
7. **Thiết kế NonceStore:** key namespace theo client/principal và environment/audience, atomic claim, TTL tối thiểu `2W + margin` nếu fixed TTL từ lúc claim; không tách theo key ID tạo lỗ qua rotation.
8. **Kiểm thử race:** cho hai verifier cùng claim đúng nonce một lúc, bảo đảm tối đa một được phép đi vào backend. Khi nonce store lỗi, policy phải **fail closed**.
9. **Kiểm thử gateway:** duplicate `X-Nonce`, header value sai size, proxy đổi method/Host/path/body hoặc forwarded header giả. Không dùng client-supplied authentication context để vượt kiểm tra.
10. **Bài toán nghiệp vụ:** gửi lại request với nonce cũ, rồi retry bằng nonce mới nhưng cùng `Idempotency-Key`; giải thích cách replay gate và idempotency service khác nhau. Thử principal ký đúng nhưng truy cập đơn của tenant khác.

**Tiêu chí hoàn thành:** có bằng chứng **nonce gốc 16 byte ngẫu nhiên → Base64URL canonical 22 ký tự → nonce được HMAC ký → server strict decode/verify → atomic claim trong TTL → authorization**. Người học phải giải thích được vì sao chỉ tăng nonce từ 16 lên 32 byte **không thay thế** việc giữ nonce đã dùng hoặc bảo vệ key bị lộ.

---

## Ghi nhớ

Trong module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, **Nonce length** phải được đo bằng **raw random bytes và entropy**, không chỉ đếm ký tự hiển thị. Một profile phổ biến, dễ kiểm thử là **16 byte từ CSPRNG = 128 bit ngẫu nhiên**, vận chuyển bằng **Base64URL không padding dài đúng 22 ký tự**. Verifier kiểm tra decode **đúng 16 byte**, encoding canonical, đưa **nonce text vào HMAC canonical request**, rồi chỉ **sau HMAC hợp lệ** mới claim nonce bằng **shared atomic store có TTL phủ toàn bộ cửa sổ timestamp**. Độ dài tốt giúp giảm collision; chống replay thực sự vẫn cần **state**, và hệ thống hoàn chỉnh vẫn cần key rotation, proxy/gateway consistency, idempotency và **authorization**.
