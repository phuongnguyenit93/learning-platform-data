# Hex signature

**Hex signature** là cách biểu diễn **chữ ký HMAC dạng byte** thành một chuỗi ký tự hệ cơ số 16 (*hexadecimal*, hay **Base16**) để truyền qua HTTP header, ghi vào test vector hoặc so sánh giữa các hệ thống. Ví dụ, HMAC-SHA256 tạo ra **32 byte tag**; khi encode đầy đủ sang hex, tag đó có **64 ký tự**.

Hex **không phải thuật toán ký**, không làm tăng sức mạnh mật mã và không thay thế bước xác minh HMAC. Nó chỉ là một **định dạng biểu diễn**. Hai phía phải thống nhất chính xác cách encode, decode và kiểm tra chuỗi chữ ký; nếu client dùng hex chữ hoa hoặc thêm tiền tố `0x` trong khi server chỉ cho hex chữ thường, một tag đúng về mặt byte vẫn có thể bị từ chối theo hợp đồng giao thức.

Bài học thuộc chương **Encoding chữ ký** của mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Trong mô-đun này, HTTP client và verifier dùng shared secret để tính HMAC trên **canonical request** gồm phương thức, URI, header và/hoặc body theo hợp đồng ký. Bên cạnh việc thống nhất encoding chữ ký, hệ thống còn phải chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và thực hiện authorization riêng sau authentication.

> **Điểm cần nhớ:** `HMAC(secret, canonicalBytes)` trả về **một dãy byte**. `HexEncode(tagBytes)` chỉ đổi cách trình bày. Khi xác minh, kiểm tra format hex, **decode về đúng byte tag** rồi so sánh với HMAC do server tự tính. Không thay một phép so sánh mật mã bằng việc so chuỗi hex tùy tiện.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích hex encoding ở mức byte, bit và ký tự ASCII; phân biệt tag HMAC với chuỗi hex đại diện cho tag.
2. Tính đúng độ dài hex cho HMAC-SHA256, HMAC-SHA384 và HMAC-SHA512.
3. Giải thích các lựa chọn hợp đồng: hex chữ thường/chữ hoa, có/không tiền tố, có/không dấu cách, độ dài cố định, vị trí chữ ký và cú pháp header.
4. Tránh lỗi mất số `0` đầu, xử lý hex như số nguyên, nhầm bytes với UTF-8, dùng sai thuật toán hoặc chấp nhận tag bị cắt.
5. Viết Java 17 tạo và xác minh HMAC-SHA256 dạng **hex chữ thường** bằng JCA và `HexFormat`.
6. Xây dựng verifier chống malformed signature và tích hợp nó với key ID, canonical request, timestamp/nonce, key rotation.
7. Kiểm thử với vector HMAC chuẩn, test cases sai encoding và luồng client–gateway–server.
8. Phân biệt chữ ký hợp lệ với quyền được phép thao tác trên resource cụ thể.

## 2. Hex là phép mã hóa, không phải phép băm hay MAC

### 2.1. Một byte thành hai chữ số hex

Mỗi byte có 8 bit, mang giá trị từ `0` tới `255`, hay từ `0x00` tới `0xFF`. Hex dùng 16 ký tự:

~~~text
0123456789abcdef
~~~

Một ký tự hex biểu diễn **4 bit** (*nibble*). Vì một byte có 8 bit, mỗi byte được encode bằng **hai ký tự hex**.

~~~text
Byte gốc (hex notation) : 00   0f   a0   ff
Nibble cao/thấp         : 0 0  0 f  a 0  f f
Chuỗi hex chữ thường    : 000fa0ff
~~~

Ví dụ cụ thể:

| Byte | Dạng nhị phân | Hai ký tự hex |
| --- | --- | --- |
| `0x00` | `00000000` | `00` |
| `0x07` | `00000111` | `07` |
| `0x0f` | `00001111` | `0f` |
| `0x10` | `00010000` | `10` |
| `0xa0` | `10100000` | `a0` |
| `0xff` | `11111111` | `ff` |

Công thức:

\[
\text{hexLength} = 2 \times \text{numberOfBytes}
\]

Trong Java, `byte` có thể được xem như giá trị signed từ -128 tới 127. Đó **không làm thay đổi bit gốc**. Một bộ mã hóa hex chuẩn sẽ biểu diễn đúng hai chữ số cho mỗi byte bất kể dấu của kiểu `byte`.

### 2.2. Hex encoding không sử dụng secret

~~~text
messageBytes = UTF8("Hello")
digestBytes  = SHA-256(messageBytes)
digestHex    = HexEncode(digestBytes)

canonicalBytes = UTF8(canonicalRequest)
tagBytes       = HMAC-SHA256(sharedSecret, canonicalBytes)
signatureHex   = HexEncode(tagBytes)
~~~

`digestHex` của SHA-256 và `signatureHex` của HMAC-SHA256 đều có thể dài 64 ký tự, nhưng **không có cùng ý nghĩa bảo mật**:

- `SHA-256(message)` là digest không có khóa; bất kỳ ai biết message đều tính được.
- `HMAC-SHA256(secret, message)` là tag có khóa; verifier có thể dùng nó để kiểm tra thông điệp đã ký bởi bên sở hữu secret.
- `HexEncode(...)` chỉ biểu diễn kết quả; ai cũng có thể decode hex sang byte.

Không dùng `SHA256(secret + message)` thay HMAC hoặc xem một chuỗi hex dài là bằng chứng đã được xác thực.

## 3. Độ dài hex signature của các thuật toán HMAC

Độ dài **tag HMAC đầy đủ** được quyết định bởi hash nền, không phải bởi độ dài secret hay kích thước HTTP body.

| Thuật toán MAC | Độ dài tag byte | Hex đầy đủ | Base64URL không padding | Java JCA |
| --- | ---: | ---: | ---: | --- |
| **HMAC-SHA256** | 32 byte | **64 ký tự** | 43 ký tự | `HmacSHA256` |
| **HMAC-SHA384** | 48 byte | **96 ký tự** | 64 ký tự | `HmacSHA384` |
| **HMAC-SHA512** | 64 byte | **128 ký tự** | 86 ký tự | `HmacSHA512` |

Một request dùng `HmacSHA256` và hợp đồng **full-tag lowercase hex** phải gửi **đúng 64 ký tự `[0-9a-f]`**. Một request gửi 32 ký tự không phải “chữ ký HMAC-SHA256 32 byte”: đó chỉ là **16 byte sau hex decode**, tức tag đã bị cắt.

### 3.1. Vì sao kích thước tag không phải độ dài khóa?

Một shared secret dài 32 byte có thể được dùng để tạo:

~~~text
HMAC-SHA256(secret32Bytes, message) -> 32-byte tag -> 64 hex
HMAC-SHA384(secret32Bytes, message) -> 48-byte tag -> 96 hex
HMAC-SHA512(secret32Bytes, message) -> 64-byte tag -> 128 hex
~~~

HMAC xử lý secret theo cấu trúc nội bộ của thuật toán. Không thể suy ra thuật toán hoặc chất lượng secret chỉ từ chiều dài chuỗi hex. Độ dài tag không thay thế việc cấp secret ngẫu nhiên, bảo vệ secret, ràng buộc key ID và chọn thuật toán theo chính sách server.

### 3.2. Hex có làm HMAC “mạnh hơn” không?

**Không.** Hex biểu diễn cùng một tập bit bằng nhiều ký tự ASCII hơn. Với HMAC-SHA256, 32 byte tag nhị phân có cùng thông tin mật mã như 64 ký tự hex của nó.

Cũng không thể suy rằng `64 ký tự hex = 64 byte bí mật`. Mỗi ký tự hex chỉ mang 4 bit thông tin, nên 64 ký tự hex đại diện **256 bit** dữ liệu.

Đặc biệt, an toàn của request authentication phụ thuộc vào secret entropy, canonicalization, bảo vệ endpoint, replay protection, key rotation và authorization; tăng chiều dài chuỗi biểu diễn không khắc phục các lỗi giao thức.

## 4. Hex so với Base64 và Base64URL

Hex và Base64 đều phổ biến khi đưa byte tag vào HTTP header.

| Tiêu chí | Hex/Base16 | Base64 chuẩn | Base64URL |
| --- | --- | --- | --- |
| Bảng ký tự | `0-9a-f` (hoặc `A-F` nếu protocol chọn) | Chữ/số, `+`, `/` và có thể `=` | Chữ/số, `-`, `_`, có thể `=` |
| Ký tự trên 32 byte | 64 | 44 với padding | 43 nếu bỏ padding |
| Dễ kiểm tra bằng mắt | Cao, từng byte gồm 2 ký tự | Thấp hơn | Thấp hơn |
| Tính gọn | 2 ký tự/byte | Xấp xỉ 4 ký tự/3 byte | Xấp xỉ 4 ký tự/3 byte |
| Phù hợp header | Có | Có | Có |
| Khả năng nhầm encoding | Chữ hoa/thường, prefix `0x`, dấu cách | Padding, `+`/`/` | Padding, `-`/`_` |

Vì hex dài hơn Base64URL, nó tăng một phần kích thước header và log. Tuy nhiên, với HMAC-SHA256, **64 ký tự** thường vẫn nhỏ so với giới hạn header của hệ thống. Lựa chọn encoding nên do **hợp đồng tích hợp** quyết định, không để client tùy chọn lúc gửi.

### 4.1. Không tự nhận diện encoding từ hình dạng chuỗi

Ví dụ, verifier không nên viết:

~~~text
if signature.length == 64:
    treatAsHexOrMaybeBase64(...)
else:
    treatAsBase64(...)
~~~

Dùng độ dài để **xác minh giá trị theo encoding đã quy định**, không dùng nó để **chọn encoding hoặc thuật toán mật mã**. Một protocol `v1` nên cố định `HmacSHA256 + lowercase hex + 64 characters`; các biến thể muốn tương thích cần version riêng và bộ test tương ứng.

### 4.2. Không lẫn hex của secret với hex của tag

Một secret có thể được **phân phối dưới dạng hex** rồi decode thành byte trước khi đưa vào HMAC:

~~~text
secretHex   = "0123456789abcdef..."  (secret được cấp riêng)
secretBytes = HexDecode(secretHex)
tagBytes    = HMAC-SHA256(secretBytes, canonicalRequestBytes)
signature   = HexEncode(tagBytes)
~~~

Đừng dùng `secretHex.getBytes(UTF_8)` nếu contract secret nói rằng chuỗi hex là **encoding của byte khóa**. Hai cách tạo byte này hoàn toàn khác nhau:

~~~text
HexDecode("3031")           -> bytes [0x30, 0x31]
UTF8("3031")                -> bytes [0x33, 0x30, 0x33, 0x31]
~~~

Đồng thời, **không** đưa secret vào HTTP header cùng signature. Client chỉ gửi key ID (định danh không bí mật) và tag; secret chỉ tồn tại ở bên ký và verifier có thẩm quyền.

## 5. Định dạng wire của một hex signature

Một hợp đồng HTTP minh họa đặt chữ ký ở header:

~~~http
X-Signature: b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7
~~~

Giá trị trên là một **known-answer HMAC-SHA256 test tag** (được giải thích ở mục 10), không phải signature cho một HTTP request thực.

Định nghĩa `HMAC-REQUEST-V1` cho bài này:

1. Thuật toán ký: **HMAC-SHA256**.
2. Tag dùng **đầy đủ 32 byte**, không cắt ngắn.
3. Encoding: **hex chữ thường ASCII** `0123456789abcdef`, **đúng 64 ký tự**.
4. Không có `0x`, `sha256=`, dấu `:`, dấu cách, `\t`, xuống dòng hoặc `=` padding.
5. Chỉ **một** header `X-Signature`; header trùng, kể cả khác cách viết hoa tên, phải bị từ chối.
6. Nếu một protocol khác muốn dùng tiền tố `sha256=`, tiền tố là **một phần cú pháp đã quy định**, cần parser/version riêng; không tự thêm/bỏ prefix.
7. Signature không nằm trong **canonical bytes tạo ra chính nó**; các metadata ảnh hưởng xác thực như key ID, timestamp, nonce, protocol version được ký theo hợp đồng.
8. Verifier phải kiểm tra đúng cú pháp và decode về byte, rồi so sánh **đầy đủ 32 byte** với expected HMAC.

Hợp đồng này **chọn chữ thường một cách có chủ đích**. Hex có thể tồn tại dạng chữ hoa và biểu diễn cùng byte, nhưng nếu server tự cho phép cả hai trong khi tài liệu chỉ quy định một dạng, nó tạo ra nhiều biểu diễn hợp lệ cho cùng một tag. Một quy tắc duy nhất giúp client, verifier và test vector ổn định.

### 5.1. Quy tắc chữ hoa/chữ thường

Hai chuỗi:

~~~text
abcdef0123456789
ABCDEF0123456789
~~~

mã hóa cùng các byte nếu decoder chấp nhận cả hai kiểu chữ. Nhưng theo `HMAC-REQUEST-V1` ở đây, chỉ lowercase là **định dạng hợp lệ**.

Không đánh đồng “hex chữ hoa có thể decode” với “request được chấp nhận theo contract”. Với hệ thống cần tương thích legacy uppercase, hãy ban hành quy tắc rõ ràng như **chấp nhận cả hai nhưng canonicalize theo lowercase trước khi lưu/so sánh**, sau khi đã kiểm tra ảnh hưởng của replay/cache/signature identity.

### 5.2. Không chấp nhận chữ ký thiếu số 0 ở đầu

Giả sử tag byte bắt đầu bằng:

~~~text
00 07 0f 80 ff ...
~~~

Hex phải bắt đầu:

~~~text
00070f80ff...
~~~

Nếu chuyển tag bytes thành một số nguyên rồi gọi `toString(16)`, các số `0` đầu có thể bị loại bỏ; độ dài sẽ không còn cố định. Đừng dùng `BigInteger(byteArray).toString(16)` để mã hóa tag HMAC:

- Nó có thể loại bỏ **leading zeros**.
- Byte cao có bit dấu có thể khiến `BigInteger` được hiểu là số âm nếu không chỉ rõ signum.
- Kết quả có thể không đủ **2 ký tự trên mỗi byte**.

Dùng thư viện mã hóa **byte sang hex** như `HexFormat` để giữ nguyên mọi byte.

### 5.3. Không phân tách bằng dấu hai chấm hoặc khoảng trắng

Các định dạng hiển thị như:

~~~text
b0:34:4c:61:...
b0 34 4c 61 ...
0xb0344c61...
~~~

hữu ích trong một số công cụ debug nhưng **không hợp lệ** theo hợp đồng hex chữ thường liền mạch. Không tự strip `:`, whitespace hoặc prefix theo cách không được công bố; điều này làm mơ hồ định dạng dữ liệu mà hai phía đang xác minh.

## 6. Khi nào hex signature được tạo?

Quy trình client có thể xem như:

~~~mermaid
flowchart TD
    A[Tạo method, URI, headers, body] --> B[Chọn keyId và shared secret]
    B --> C[Timestamp và nonce mới]
    C --> D[Canonicalize method, path, query, signed headers, body digest]
    D --> E[UTF-8 canonical request bytes]
    E --> F[HMAC-SHA256 secret + canonical bytes]
    F --> G[Tag gốc 32 byte]
    G --> H[HexEncode lowercase: 64 ký tự]
    H --> I[Đặt X-Signature và gửi HTTPS]
~~~

Điểm quan trọng là **hex encode sau khi tính HMAC**:

~~~text
ĐÚNG:
HMAC(secret, canonicalRequestBytes) -> tagBytes -> HexEncode(tagBytes)

SAI:
HMAC(secret, HexEncode(canonicalRequestBytes))     # nếu contract ký raw UTF-8 bytes
HexEncode(secret) + HexEncode(canonicalRequest)    # không phải HMAC
SHA256(secret || canonicalRequest)                 # không phải HMAC
~~~

Việc chuyển canonical request thành một chuỗi hex **trước khi ký** là một giao thức khác. Nó chỉ hợp lệ nếu cả hai phía công bố rõ sẽ ký byte ASCII của hex canonical request; không nên tự phát minh bước này vì HMAC đã nhận trực tiếp byte.

## 7. Đưa hex signature vào HTTP canonical request

Giả định một API đơn hàng nhận:

~~~http
POST /v1/orders?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: partner-a-k3
X-Timestamp: 1790000000
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <64-lowercase-hex-characters>

{"orderId":"order-42","amount":125000}
~~~

Trong đó `X-Signature` là placeholder. Định nghĩa canonical request như sau:

~~~text
HMAC-REQUEST-V1
POST
/v1/orders
currency=VND
audience:orders-api
content-type:application/json
x-key-id:partner-a-k3
x-timestamp:1790000000
x-nonce:6bfb21974a08417199273b09ca49a3ec
body-sha256:<64-lowercase-hex-of-raw-body>
~~~

Các quy tắc ví dụ:

- Chuỗi canonical dùng **UTF-8**, các dòng nối bằng **LF**, **không có LF cuối**.
- Method và canonical path/query phải theo **contract URI** do cả client và verifier dùng chung.
- Các signed headers được canonicalize lowercase name theo thứ tự cố định; giá trị đã được kiểm tra.
- `audience:orders-api` ràng buộc chữ ký vào service nhận request theo chính sách server.
- `X-Key-Id` dùng tra secret và principal trong key registry, không phải secret và không tự tạo quyền.
- `X-Timestamp`, `X-Nonce` được ký để hỗ trợ freshness/replay protection.
- Body digest là **SHA-256 của đúng raw body bytes** rồi encode hex; đây là **digest không khóa** nhưng được HMAC bảo vệ vì dòng digest nằm trong canonical request.
- `X-Signature` là **tag đầu ra** nên không nằm trong canonical request.

Dòng `body-sha256:...` cũng dùng hex, nhưng **khác vai trò** với `X-Signature`:

| Giá trị | Công thức | Đầu ra hex | Secret? |
| --- | --- | --- | --- |
| Body digest | `SHA256(rawBodyBytes)` | 64 ký tự | Không |
| HMAC signature | `HMAC-SHA256(K_mac, canonicalBytes)` | 64 ký tự | Có |

Dù đều 64 ký tự, **không được dùng body digest như chữ ký** hoặc dùng HMAC tag làm body digest.

### 7.1. Query, path, headers thay đổi vẫn phải bị phát hiện

Hex encoding **không quyết định những gì được ký**. Nếu contract chỉ ký body mà không ký method/URI, kẻ tấn công có thể thay method hoặc path mà chữ ký vẫn đúng. Với API nhạy cảm, cần ký những thành phần ảnh hưởng tới hành động, tài nguyên, tenant và nội dung request.

Tương tự, nếu một header ngoài signed set như `X-HTTP-Method-Override` hoặc `X-Tenant-Id` được handler tin dùng, thay đổi header đó có thể đổi nghiệp vụ mà HMAC vẫn khớp. Phải đưa header ảnh hưởng semantics vào signed set, cấm nó, hoặc lấy dữ liệu từ trusted principal thay vì header tự khai.

### 7.2. Xử lý request không có body

Một `GET` có body rỗng vẫn có thể chứa dòng:

~~~text
body-sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

Đây là SHA-256 hex của **dãy byte rỗng**. Không được thay digest này bằng chuỗi rỗng, `null` hoặc digest của JSON `{}` trừ khi contract định nghĩa rõ. Giá trị là digest thường, không phải HMAC signature.

## 8. Java 17: HexFormat và JCA HMAC

Java 17 cung cấp `java.util.HexFormat` để encode/decode byte array. JCA cung cấp `javax.crypto.Mac` với `HmacSHA256`.

### 8.1. Mã hóa và giải mã byte đơn giản

~~~java
import java.util.HexFormat;

byte[] bytes = new byte[] {
        (byte) 0x00, (byte) 0x0f, (byte) 0xa0, (byte) 0xff
};

// HexFormat.of() mặc định cho lowercase hex, không delimiter.
String hex = HexFormat.of().formatHex(bytes);
assert hex.equals("000fa0ff");

byte[] decoded = HexFormat.of().parseHex(hex);
assert java.util.Arrays.equals(bytes, decoded);
~~~

Nếu có một byte `0x00` ở đầu, chuỗi có hai ký tự `00` tương ứng. `HexFormat` không tự loại bỏ leading zeros.

### 8.2. Helper HMAC-SHA256 → lowercase hex

~~~java
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacSha256Hex {
    public static final int TAG_BYTES = 32;
    public static final int TAG_HEX_CHARS = TAG_BYTES * 2;

    private HmacSha256Hex() {}

    public static byte[] computeTag(
            byte[] secret, byte[] canonicalBytes)
            throws GeneralSecurityException {

        // Mac là stateful, không chia sẻ một instance giữa các thread.
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(canonicalBytes);
    }

    public static String signHex(
            byte[] secret, byte[] canonicalBytes)
            throws GeneralSecurityException {

        byte[] tag = computeTag(secret, canonicalBytes);
        return HexFormat.of().formatHex(tag);
    }
}
~~~

`computeTag` nhận **byte secret thật**, không phải chuỗi secret hex. Trong hệ thống production, byte secret cần được lấy từ secret manager/key registry theo credential đã được cấp phát, không hardcode trong source code.

### 8.3. Strict decoder cho chữ ký 64 ký tự

Đây là ví dụ cố định full-tag HMAC-SHA256 lowercase hex:

~~~java
import java.util.HexFormat;
import java.util.regex.Pattern;

public final class SignatureHexV1 {
    private static final Pattern FORMAT =
            Pattern.compile("[0-9a-f]{64}");

    private SignatureHexV1() {}

    public static byte[] decodeStrict(String input) {
        if (input == null || !FORMAT.matcher(input).matches()) {
            throw new IllegalArgumentException("Invalid signature format");
        }

        byte[] decoded = HexFormat.of().parseHex(input);
        if (decoded.length != HmacSha256Hex.TAG_BYTES) {
            throw new IllegalArgumentException("Invalid signature format");
        }
        return decoded;
    }
}
~~~

Regex `[0-9a-f]{64}` kiểm tra **ASCII lowercase hex** và đúng độ dài, vì thế từ chối:

- `ABCDEF...` (uppercase).
- Prefix `0x` hoặc `sha256=`.
- Dấu `:`, space, tab, newline.
- Chuỗi có chữ ngoài `0-9a-f` như `g`, `O`, `l`.
- Chuỗi lẻ ký tự hoặc độ dài 62/63/65 ký tự.
- Signature bị cắt ngắn dù prefix có vẻ đúng.
- Non-ASCII lookalike characters (ký tự Unicode trông giống chữ/số ASCII).

Không dùng `trim()` hay `toLowerCase()` để sửa input nếu contract **chỉ cho một dạng**. Việc parser HTTP tự xử lý optional whitespace (OWS) ở ranh giới wire cần được xác định rõ, và phải kiểm thử hành vi thực ở container/gateway.

### 8.4. Verify tag bằng so sánh byte

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;

public final class HmacSha256HexVerifier {
    private HmacSha256HexVerifier() {}

    public static boolean verify(
            byte[] secret,
            byte[] canonicalBytes,
            String presentedHex) throws GeneralSecurityException {

        final byte[] supplied;
        try {
            supplied = SignatureHexV1.decodeStrict(presentedHex);
        } catch (IllegalArgumentException malformed) {
            return false;
        }

        byte[] expected = HmacSha256Hex.computeTag(
                secret, canonicalBytes);

        return MessageDigest.isEqual(expected, supplied);
    }
}
~~~

**Vì sao nên so sánh byte thay vì string?** Chuỗi hex là biểu diễn văn bản của byte tag; so sánh bằng `String.equals` có thể có đặc điểm thời gian phụ thuộc vị trí khác nhau. Sau khi kiểm tra format và decode, `MessageDigest.isEqual` là API Java phù hợp để so sánh byte của kết quả mật mã.

Kiểm tra độ dài format trước khi chạy HMAC là chấp nhận được vì độ dài tag theo contract là thông tin công khai. Verifier vẫn cần bảo vệ chống lạm dụng/DoS, đồng thời không lộ tình trạng key/secret qua response khác biệt quá chi tiết.

### 8.5. Tích hợp canonical HTTP request

Đoạn dưới dùng hợp đồng dòng LF đã mô tả ở mục 7:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.HexFormat;

public final class CanonicalHttpV1 {
    private CanonicalHttpV1() {}

    public static byte[] toBytes(
            String method,
            String canonicalPath,
            String canonicalQuery,
            String contentType,
            String keyId,
            long timestampSeconds,
            String nonce,
            byte[] rawBody) throws GeneralSecurityException {

        String bodySha256 = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(rawBody));

        // Các tham số method/path/query/header đã được validate
        // theo hợp đồng riêng, không chứa CR/LF.
        String canonicalText = String.join("\n",
                "HMAC-REQUEST-V1",
                method,
                canonicalPath,
                canonicalQuery,
                "audience:orders-api",
                "content-type:" + contentType,
                "x-key-id:" + keyId,
                "x-timestamp:" + timestampSeconds,
                "x-nonce:" + nonce,
                "body-sha256:" + bodySha256);

        return canonicalText.getBytes(StandardCharsets.UTF_8);
    }
}
~~~

Client có thể ký:

~~~java
byte[] canonical = CanonicalHttpV1.toBytes(
        "POST",
        "/v1/orders",
        "currency=VND",
        "application/json",
        "partner-a-k3",
        1790000000L,
        "6bfb21974a08417199273b09ca49a3ec",
        rawBody);

String signatureHeader =
        HmacSha256Hex.signHex(secretBytes, canonical);
// Gửi X-Signature: signatureHeader bằng HTTPS.
~~~

Server có thể dùng cùng hàm tạo canonical bytes từ **request nhận được** và kiểm tra:

~~~java
boolean macValid = HmacSha256HexVerifier.verify(
        secretFromKeyRegistry,
        canonicalFromReceivedRequest,
        presentedSignatureHeader);
~~~

**Giới hạn quan trọng:** Ví dụ không tự parse HTTP wire, không tìm secret, không chống replay và không phân quyền. `method`, `canonicalPath`, `canonicalQuery`, `contentType`, `keyId`, `nonce` phải được validate độc lập. Không cho CR/LF, header lặp, query/path nhập nhằng hoặc giá trị chưa chuẩn hóa làm phá định dạng dòng. Chỉ xử lý nghiệp vụ **sau khi** HMAC, freshness, replay gate và authorization đều thành công.

## 9. Chuỗi hex là input không đáng tin

### 9.1. Kiểm tra format trước khi decode

Với tag HMAC-SHA256 hex, verifier nên yêu cầu:

~~~text
signature != null
signature.length() == 64
every character is one of: 0123456789abcdef
decoded bytes length == 32
~~~

Các bước này ngăn việc decoder “linh hoạt” vô tình chấp nhận nhiều biểu diễn hoặc tag sai độ dài. Không tự bỏ whitespace, không cho tag rỗng, không so prefix và không bỏ qua dấu phân cách không nằm trong contract.

### 9.2. Không thử nhiều thuật toán để tìm chữ ký khớp

Không nên làm:

~~~text
if length == 64:
    try HmacSHA256
else if length == 96:
    try HmacSHA384
else:
    try every secret and algorithm
~~~

Thuật toán và định dạng phải được chọn **từ protocol version và key record do server kiểm soát**. Độ dài hex được dùng để **kiểm tra request đã khớp thuật toán được chọn**, không phải để cho client điều khiển thuật toán.

Nếu cần hỗ trợ nhiều thuật toán trong một giai đoạn di trú, cấu hình rõ `keyId → algorithm, version, secretRef, status, audience`. Verifier chỉ tính expected tag bằng thuật toán cho phép của record đã chọn.

### 9.3. Không cho kiểm tra một phần tag

~~~text
BAD: expectedHex.startsWith(presentedHex)
BAD: compare only first 8 hex characters
BAD: suppliedTag.substring(0, expectedLength)
~~~

Cách này biến một full-length MAC thành một tag ngắn bất ngờ. Một số protocol chuyên biệt có thể định nghĩa **truncated HMAC** với độ dài xác định và phân tích bảo mật riêng, nhưng đó phải là **một contract mới**. Đối với API minh họa, dùng **đầy đủ 32 byte** và từ chối mọi tag bị cắt.

### 9.4. Không dùng hex signature làm ID duy nhất của request

Một chữ ký HMAC là kết quả xác thực các byte đã ký. Nếu hai request có cùng canonical bytes, timestamp và nonce, chúng sẽ có cùng tag. Nhưng:

- Một attacker có thể replay nguyên request với cùng chữ ký.
- Nhiều request có thể dùng các key/version khác nhau.
- Mỗi credential có namespace riêng và lịch rotation.
- Chỉ dựa vào tag làm idempotency key sẽ không đủ nếu business semantics cần phân biệt các giao dịch.

Do đó chống replay cần timestamp/nonce đã ký và replay store; idempotency nghiệp vụ cần event/operation ID và store tương ứng.

## 10. Kiểm thử thuật toán bằng vector tham chiếu RFC 4231

Trước khi kiểm thử HTTP canonicalization, hãy xác nhận HMAC primitive hoạt động đúng trên dãy byte cố định. **RFC 4231** cung cấp test vectors cho HMAC-SHA224/256/384/512.

**Test case 1 của HMAC-SHA256:**

~~~text
Key:          20 byte, mỗi byte = 0x0b
Data:         ASCII "Hi There"
Expected tag: 32 byte
Expected hex (64 ký tự):
b0344c61d8db38535ca8afceaf0bf12b
881dc200c9833da726e9376c2e32cff7
~~~

Hai dòng `Expected hex` phải **nối liền không có newline hoặc space**. Mẫu key lặp byte `0x0b` là **test input**, không phải khuyến nghị cấp khóa production.

### 10.1. Java known-answer test

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

byte[] key = new byte[20];
Arrays.fill(key, (byte) 0x0b);

byte[] message = "Hi There"
        .getBytes(StandardCharsets.US_ASCII);

String expected =
        "b0344c61d8db38535ca8afceaf0bf12b"
      + "881dc200c9833da726e9376c2e32cff7";

String actual = HmacSha256Hex.signHex(key, message);

if (!expected.equals(actual)) {
    throw new AssertionError("HMAC-SHA256 hex KAT failed");
}
~~~

Nếu test này PASS nhưng HTTP signature thất bại, cần kiểm tra **shared secret thực tế**, canonical request bytes, thứ tự field, dấu LF, URI/query, signed headers, body digest, timestamp và gateway; đừng mặc định lỗi nằm ở hex encoding.

### 10.2. HMAC-SHA384 cũng dùng cùng quy tắc hex

Nếu contract chọn `HmacSHA384`:

~~~text
Expected tag length: 48 byte
Full hex length:     96 ký tự
Allowed lowercase:  [0-9a-f]{96}
~~~

Vector HMAC-SHA384 RFC 4231 test case 1:

~~~text
afd03944d84895626b0825f4ab46907f
15f9dadbe4101ec682aa034c7cebc59c
faea9ea9076ede7f4af152e8b2fa9cb6
~~~

Đây là 96 ký tự sau khi nối ba dòng. Thay `HmacSHA256` bằng `HmacSHA384` đòi hỏi cập nhật đồng bộ **algorithm, tag length, regex, test vectors và key/policy metadata**. Không chỉ đổi tên thuật toán mà vẫn yêu cầu 64 ký tự hex.

### 10.3. Test leading-zero

Test riêng encoder/decoder:

~~~java
import java.util.HexFormat;
import java.util.Arrays;

byte[] bytes = { 0x00, 0x00, 0x01, (byte) 0xff };
String hex = HexFormat.of().formatHex(bytes);

assert hex.equals("000001ff");
assert Arrays.equals(
        bytes, HexFormat.of().parseHex(hex));
~~~

Nếu một implementation cho ra `1ff`, nó đã **làm mất byte thông tin** do xử lý như số nguyên, không phải encoding đúng của byte array.

## 11. Dữ liệu nào được hex encode trong HTTP protocol?

Trong một protocol HMAC, **nhiều giá trị có thể dùng hex nhưng không đồng nghĩa**:

| Giá trị | Ví dụ biểu diễn | Ai tạo? | Có bí mật? |
| --- | --- | --- | --- |
| `X-Signature` | Hex của HMAC tag | Client ký; verifier tính lại | Không phải shared secret, nhưng có thể bị replay |
| Body digest | Hex của `SHA-256(rawBody)` | Client/server tính từ body | Không |
| Nonce | Hex của 16 byte ngẫu nhiên | Client | Không bí mật nhưng phải khó đoán và không lặp |
| Key ID | Tên hoặc chuỗi định danh (có thể chứa hex) | Hệ thống cấp credential | Thông thường không |
| Shared secret được lưu dưới dạng hex | Hex của byte khóa | Secret provisioning/manager | **Có**, phải bảo vệ |
| Request ID | Có thể là hex UUID/random ID | Client/gateway | Không mặc nhiên là bằng chứng xác thực |

### 11.1. Nonce hex không phải signature hex

Ví dụ:

~~~http
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <64-lowercase-hex-hmac-tag>
~~~

`X-Nonce` có 32 ký tự hex vì nó đại diện **16 byte nonce**; `X-Signature` có 64 ký tự hex vì nó đại diện **32 byte HMAC-SHA256 tag**. Dù dùng cùng bảng ký tự, hai trường có mục đích và tiêu chí kiểm tra khác nhau.

Nonce phải được HMAC ký và server phải chống lặp bằng replay store. Hex encoding không mang thuộc tính random hoặc unique; chính **nguồn tạo nonce và quy trình kiểm soát** quyết định chất lượng nonce.

### 11.2. Không đưa secret hex vào log

Hex làm byte nhị phân dễ đọc nên cũng làm **secret dễ bị copy**. Mọi secret dù dưới dạng hex, Base64 hay byte array đều là bí mật. Không log hoặc gửi secret trong response/error. `X-Signature` không phải secret dài hạn, nhưng **signed request còn hạn có thể bị phát lại**, nên cũng không nên log toàn bộ request có đủ tag/timestamp/nonce và body nhạy cảm trong môi trường không được bảo vệ.

## 12. HTTP header parsing và proxy/gateway

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway / Reverse proxy
    participant V as HMAC verifier
    participant P as Replay store / Authorization

    C->>G: HTTPS + X-Signature hex + keyId/time/nonce
    Note over G: Có thể đổi HTTP version, header casing, whitespace hoặc URI
    G->>V: Request chuyển tiếp
    V->>V: Parse header duy nhất và validate lowercase hex
    V->>V: Tạo canonical bytes và HMAC expected
    V->>V: Decode hex thành 32 byte, so sánh
    V->>P: Timestamp/nonce mới, rồi principal/permission
    P-->>C: Chấp nhận hoặc từ chối
~~~

### 12.1. Tên header và giá trị header khác nhau

Trong HTTP, **tên trường header không phân biệt chữ hoa/chữ thường**. Các dạng:

~~~http
X-Signature: abcdef...
x-signature: abcdef...
~~~

có cùng tên header. Nhưng **giá trị hex** phải tuân theo format mà protocol quy định. Nếu contract yêu cầu lowercase hex, một proxy **không được tự ý chuyển giá trị signature sang uppercase** rồi mong verifier tự chấp nhận.

Nếu request đồng thời chứa:

~~~http
X-Signature: aaaa...
x-signature: bbbb...
~~~

cần từ chối header lặp, không lấy “giá trị đầu” ở verifier nhưng “giá trị cuối” ở middleware. HTTP adapter cần phát hiện duplicate values/case-variants tại ranh giới tin cậy.

### 12.2. Khoảng trắng, line folding và combined values

Một proxy hoặc HTTP library có thể trim optional whitespace quanh header value. Vì vậy contract cần nêu **giá trị mà verifier nhận từ HTTP parser** được kiểm tra thế nào. Ví dụ chỉ chấp nhận **64 ký tự hex không dấu cách** trong giá trị đã parse; nếu parser biến đổi OWS thì phải được kiểm thử nhất quán.

Các giá trị không hợp lệ:

~~~http
X-Signature: b034...cff7,
X-Signature: b034...cff7 extra
X-Signature: b034...cff7,deadbeef
~~~

Dấu phẩy không thuộc regex hex nên bị từ chối. Header chứa CR/LF injection hoặc obsolete folding cũng phải bị parser/gateway từ chối; verifier không được nối lại nhiều dòng thành một tag không có trong contract.

### 12.3. Khi gateway rewrite URI hoặc body

Hex signature có thể **được forward nguyên vẹn**, nhưng canonical request ở backend vẫn khác client đã ký nếu proxy:

- Thay path prefix hoặc trailing slash.
- Decode percent escapes, sort query theo quy tắc khác hoặc bỏ tham số trùng.
- Thay `Content-Type` hoặc các signed headers.
- Parse/serialize lại JSON body.
- Giải nén hoặc thay biểu diễn content.
- Dùng authority/host khác trong khi contract ký hostname bên ngoài.

Vì vậy, “header `X-Signature` vẫn có 64 ký tự hex” **không chứng minh chữ ký phải hợp lệ**. HMAC cần được xác minh trên canonical bytes đúng tại một trust boundary được định nghĩa.

### 12.4. Hai kiến trúc xác minh

**Verifier ở gateway:** Gateway kiểm tra HMAC trên request ngoài trước khi rewrite. Sau khi xác thực, gateway truyền principal/trusted context qua kết nối nội bộ được bảo vệ; backend không được tin header `X-Authenticated-User` tự khai từ Internet. Mapping từ request được ký tới handler cuối cùng phải được kiểm soát.

**Verifier ở backend:** Gateway phải giữ nguyên các signed components hoặc áp dụng một mapping hợp đồng được cả client/backend hiểu. Không tin header `X-Original-URI` hoặc `X-Forwarded-*` do client tự khai làm nguồn khôi phục request gốc.

Trong cả hai kiến trúc, phải giới hạn kích thước header và body, kiểm tra HTTP framing và tránh parser differential/request smuggling. Việc encode tag thành hex không ảnh hưởng đến các trách nhiệm đó.

## 13. Key rotation và di trú encoding

### 13.1. Key ID chọn thuật toán và secret

Một key record minh họa:

~~~yaml
keyId: partner-a-k3
principalId: partner-a-service
audience: orders-api
macAlgorithm: HmacSHA256
signatureEncoding: lowercase-hex
signatureLengthBytes: 32
secretRef: secrets/orders/partner-a/k3
status: ACTIVE
~~~

Đây là **dữ liệu registry phía server**, không phải header cho client tự khai. Verifier phải tra `keyId` chính xác rồi kiểm tra algorithm/encoding/version/audience/trạng thái trước khi dùng secret.

Đừng cho client tự gửi:

~~~http
X-Signature-Algorithm: none
X-Signature-Encoding: permissive
~~~

và server tự làm theo. Thuật toán/encoding được chọn bằng **contract và chính sách do server quản lý**, không bằng yêu cầu tuỳ ý từ caller.

### 13.2. Key rotation không bắt buộc đổi encoding

Trong rotation có thể tồn tại:

~~~text
partner-a-k2 -> secret v2, RETIRING, HmacSHA256, lowercase hex
partner-a-k3 -> secret v3, ACTIVE,   HmacSHA256, lowercase hex
~~~

Cả hai dùng một encoding, nhưng mỗi `keyId` chọn **secret khác nhau**. Khi đổi key ID, client phải tính **tag mới** bằng secret tương ứng. Không thay secret dưới cùng key ID rồi để server thử cả hai secret mù quáng.

### 13.3. Nếu di trú từ hex sang Base64URL

Nếu một nhóm client cần Base64URL, có thể ban hành:

~~~text
HMAC-REQUEST-V1 -> HmacSHA256, lowercase hex, tag 64 chars
HMAC-REQUEST-V2 -> HmacSHA256, Base64URL no padding, tag 43 chars
~~~

Hai phiên bản cần có rule version selection theo server/key record, test vectors riêng và lịch ngừng chấp nhận V1 nếu cần. Trong cả hai trường hợp, HMAC tag gốc vẫn là **32 byte**, trừ khi có thay đổi thuật toán.

Nếu protocol version là header `X-Signature-Version`, nó cần được ràng buộc vào canonical bytes hoặc vào một ngữ cảnh/key record không thể bị attacker đổi để gây nhầm lẫn. Không fallback “thử hex, nếu sai thử Base64” nếu version không quy định vậy.

### 13.4. Di trú HMAC-SHA256 sang HMAC-SHA384

Đây là thay đổi **MAC algorithm**, không chỉ encoding:

~~~text
HmacSHA256 -> 32 bytes -> 64 lowercase hex
HmacSHA384 -> 48 bytes -> 96 lowercase hex
~~~

Verifier phải chọn algorithm theo key record/contract. Một request gửi 64 ký tự hex dưới policy HmacSHA384 full-tag phải bị từ chối do tag length sai, chứ không được tự tính HmacSHA256 làm fallback.

## 14. Timestamp/nonce: hex đúng không chứng minh request mới

Một signed request chứa:

~~~http
X-Key-Id: partner-a-k3
X-Timestamp: 1790000000
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <valid-64-character-lowercase-hex-tag>
~~~

Có thể bị attacker **capture và gửi lại nguyên vẹn**. Chuỗi hex vẫn đúng, HMAC vẫn có thể khớp với cùng canonical bytes. Vì vậy verifier cần kiểm tra:

1. Timestamp đã ký nằm trong cửa sổ chấp nhận.
2. Key record đang hoạt động, đúng audience/algorithm và không bị thu hồi.
3. HMAC khớp **đầy đủ byte tag** với secret tương ứng.
4. Nonce đã ký được ghi vào **shared replay store** bằng thao tác atomic put-if-absent, **sau khi MAC hợp lệ**.
5. Nonce đã dùng bị từ chối; TTL nonce phải bao phủ toàn bộ thời gian request có thể được chấp nhận.
6. Request tạo tác động nghiệp vụ cần **idempotency** độc lập, vì client có thể retry bằng timestamp/nonce/chữ ký mới cho cùng một đơn hàng.

**Không dùng chính hex signature làm cơ chế chống replay duy nhất.** Một request có thể có những biểu diễn khác nhau nếu protocol cho phép uppercase/lowercase, hoặc có key/version rotation. Nên dùng định danh đã ký như nonce trong namespace credential/audience và policy tuổi request rõ ràng.

## 15. Authentication và authorization vẫn độc lập

Giả sử client được cấp `partner-a-k3` để thao tác tenant A. Client dùng secret thật ký:

~~~http
DELETE /v1/tenants/tenant-B/orders/42 HTTP/1.1
X-Key-Id: partner-a-k3
X-Timestamp: 1790000000
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <correct-lowercase-hex-hmac-tag>
~~~

Giá trị hex có thể đúng 64 ký tự và HMAC có thể hoàn toàn hợp lệ. Nhưng **không chứng minh client A được xóa đơn hàng của tenant B**.

- **Signature format validation**: Chuỗi có đúng hex format không?
- **HMAC authentication**: Tag có khớp secret cho canonical bytes không?
- **Freshness/replay**: Timestamp, nonce và key lifecycle có còn hợp lệ không?
- **Authorization**: Principal từ key record có quyền action `DELETE` trên order của tenant B không?

Trước khi handler thực thi, cả bốn lớp cần đạt kết quả phù hợp. Không lấy `X-Tenant-Id` hoặc `X-Role` do client tự gửi làm quyền truy cập, dù những header đó được HMAC ký. HMAC bảo vệ **lời yêu cầu** của caller, không cấp quyền cho nội dung của lời yêu cầu.

## 16. Ma trận kiểm thử hex signature

Bộ test nên tách **unit test encoder/decoder**, **HMAC known-answer test**, **signature verifier** và **HTTP end-to-end tests**.

| Nhóm | Ca kiểm thử | Kỳ vọng |
| --- | --- | --- |
| Encoding | Byte `00` | Hex `00`, không mất leading zero |
| Encoding | Byte `0f` | Hex `0f`, đủ 2 ký tự |
| Encoding | Byte `a0` hoặc `ff` | Hex `a0` hoặc `ff` |
| Encoding | `00 0f a0 ff` | Hex `000fa0ff` |
| Encoding | Decode rồi encode lại | Trùng chính xác lowercase hex ban đầu |
| KAT | RFC 4231 HMAC-SHA256 case 1 | Đúng hex 64 ký tự |
| KAT | RFC 4231 HMAC-SHA384 case 1 | Đúng hex 96 ký tự |
| Length | HMAC-SHA256 32-byte tag | 64 ký tự |
| Length | HMAC-SHA384 48-byte tag | 96 ký tự |
| Length | HMAC-SHA512 64-byte tag | 128 ký tự |
| Invalid input | Chữ ký `null` | Từ chối |
| Invalid input | Chuỗi rỗng | Từ chối |
| Invalid input | Chuỗi dài 63 ký tự | Từ chối |
| Invalid input | Chuỗi dài 65 ký tự | Từ chối |
| Invalid input | Tag bị cắt còn 32 ký tự | Từ chối |
| Invalid input | Có chữ `g` hoặc `O` | Từ chối |
| Invalid input | Uppercase `ABCDEF` | Từ chối theo lowercase-only V1 |
| Invalid input | Mixed case | Từ chối theo V1 |
| Invalid input | Có `0x` hoặc `sha256=` prefix | Từ chối theo V1 |
| Invalid input | Có `:` hoặc space giữa byte | Từ chối |
| Invalid input | Có leading/trailing whitespace | Từ chối theo parsed-header contract |
| Invalid input | Có non-ASCII lookalike | Từ chối |
| Invalid input | Header `X-Signature` lặp | Từ chối request mơ hồ |
| Correct MAC | Byte secret, canonical bytes, tag đều đúng | Tag match; tiếp tục freshness |
| Wrong secret | Tag tính bằng secret khác | Từ chối |
| Wrong algorithm | HmacSHA256 tag dưới contract HmacSHA384 | Từ chối theo key record/policy |
| Wrong body | Sửa raw body, giữ signature | HMAC sai |
| Wrong method | `POST` thành `DELETE`, giữ signature | HMAC sai |
| Wrong path/query | Sửa URI đã ký, giữ signature | HMAC sai |
| Wrong header | Sửa key ID/timestamp/nonce đã ký | HMAC sai hoặc credential không hợp lệ |
| HTTP proxy | Gateway đổi header casing của tên `X-Signature` | Chấp nhận tên header như nhau; value giữ đúng hex |
| HTTP proxy | Gateway uppercases hex value | Từ chối theo strict lowercase V1 |
| HTTP proxy | Gateway rewrite path/body | Canonical bytes phải theo contract; từ chối nếu khác |
| Replay | Gửi lại cùng signed request | Lần sau bị từ chối ở nonce store |
| Concurrent replay | Hai node nhận cùng nonce | Tối đa một request qua replay gate |
| Revocation | Tag đúng bằng secret đã thu hồi | Từ chối |
| Rotation | K2/K3 overlap hợp lệ | Mỗi key ID dùng đúng secret |
| Authorization | MAC đúng cho tenant khác | Authentication có thể đúng; authorization từ chối |
| Cross-service | Mang tag orders sang billing | Từ chối vì key audience/contract không khớp |

### 16.1. Fuzz format trước khi test nghiệp vụ

Một bộ input format có ích:

~~~text
64 chữ số lowercase hex hoàn chỉnh
63 chữ số lowercase hex
65 chữ số lowercase hex
64 chữ số uppercase hex
64 ký tự mixed-case
prefix 0x + 64 hex
sha256= + 64 hex
64 hex có một ký tự g
64 hex + newline
64 hex + dấu =
64 hex có tab hoặc space
hai header X-Signature
không có header X-Signature
~~~

Với strict V1, **chỉ nhóm đầu** có thể qua bước format; nó còn phải vượt HMAC verification và các bước khác. Không được xem “đúng 64 ký tự hex” là đủ để xác thực.

### 16.2. Negative tests ở cấp canonical bytes

Cùng secret và cùng canonical request, `signHex` phải tạo cùng chuỗi hex. Nhưng nếu thay một byte đã ký, expected HMAC phải thay đổi theo kỳ vọng mật mã. Test nên sửa từng thành phần độc lập: method, canonical path, query, Content-Type, key ID, timestamp, nonce và body hash.

Ngược lại, nếu một header như `User-Agent` được contract bỏ khỏi chữ ký, thay nó sẽ không làm HMAC đổi. Đây là một **quyết định phạm vi bảo vệ**, không phải lỗi hex. Phải đảm bảo unsigned header không ảnh hưởng semantics hoặc được bảo vệ bởi cơ chế tin cậy khác.

### 16.3. End-to-end test phải phân biệt MAC với replay rejection

Khi gửi lại request chỉ để xem việc đổi encoding có làm HMAC sai hay không, request có thể đã bị nonce store đánh dấu. Nếu test nhận `401`/`409` ở lần thứ hai, cần xác định **vì format, HMAC, timestamp hay replay**. Kiểm tra hex decoding và HMAC bằng unit test độc lập, sau đó chạy integration tests với nonce mới khi phù hợp.

## 17. Tình huống thực tế: client Java gửi webhook với hex chữ ký

Một hệ thống thanh toán gọi webhook sang API đối tác. Hợp đồng ký quy định:

~~~text
Protocol version: HMAC-REQUEST-V1
MAC:              HmacSHA256
Signature format: lowercase hex, 64 characters
Header:           X-Signature
Signed fields:    method, path, query, audience,
                  content-type, key-id, timestamp, nonce, body-sha256
Transport:        HTTPS
~~~

### 17.1. Luồng xử lý

1. Client tạo body JSON, giữ **đúng raw bytes** sẽ gửi.
2. Client chọn `keyId` và shared secret tương ứng đang hoạt động.
3. Sinh timestamp và nonce mới; gắn vào headers.
4. Canonicalize method, path, query, signed headers và body digest theo V1.
5. Tính HMAC-SHA256 thành byte tag 32 byte.
6. Encode bằng `HexFormat.of().formatHex(tag)` để được 64 ký tự lowercase.
7. Gửi `X-Signature` và body qua HTTPS.
8. Gateway giữ nguyên signed semantics hoặc xác minh trước rewrite.
9. Server validate signature format, tra đúng secret/key record, tái tạo canonical bytes, decode tag và so sánh.
10. Server kiểm tra freshness/nonce, tạo principal rồi authorize trước khi cập nhật thanh toán.

### 17.2. Phân tích bốn lỗi thường gặp

**Lỗi A — chữ ký có 63 ký tự.**  
Một client sử dụng `BigInteger.toString(16)` làm mất `0` đầu. Sửa bằng encoder byte→hex, không nới lỏng verifier để chấp nhận tag ngắn.

**Lỗi B — client gửi chữ hoa, server chỉ nhận chữ thường.**  
Byte sau decode có thể như nhau, nhưng wire format vi phạm contract. Sửa client sang lowercase hoặc thay protocol version có quy tắc chấp nhận rõ. Không tự cho phép cả hai mà thiếu kiểm thử.

**Lỗi C — chữ ký dài đúng 64 ký tự nhưng vẫn sai.**  
Cần so sánh secret, method/path/query, header canonicalization, LF/UTF-8, SHA-256 raw body và proxy rewrite. Độ dài đúng không bảo đảm HMAC đúng.

**Lỗi D — HMAC hợp lệ nhưng request bị từ chối.**  
Timestamp có thể đã quá hạn, nonce bị replay, key ID bị revoke, audience sai, hoặc principal không có quyền. Phải phân biệt **xác thực chữ ký** với **freshness, replay và authorization**.

## 18. Bài tập tự thực hành

### Bài tập 1 — Encode byte chính xác

Dùng `HexFormat` encode mảng byte:

~~~java
byte[] input = { 0x00, 0x01, 0x0f, 0x10, (byte) 0x80, (byte) 0xff };
~~~

Hãy tính hex kỳ vọng thủ công, decode lại và xác nhận mảng byte giữ nguyên. Sau đó thử một cách encode thông qua `BigInteger` để nhận ra rủi ro mất leading zeros hoặc signedness.

### Bài tập 2 — Kiểm tra format

Viết JUnit tests cho `SignatureHexV1.decodeStrict` để từ chối chữ ký độ dài 63/65, uppercase, mixed case, `0x`, whitespace, `g`, empty string và `null`. Xác nhận **64 ký tự lowercase hex** decode thành đúng 32 byte.

### Bài tập 3 — Known-answer HMAC

Dùng vector RFC 4231 với key 20 byte `0x0b` và dữ liệu ASCII `Hi There`. Kiểm tra HMAC-SHA256 kết quả hex là 64 ký tự và trùng expected. Sau đó chuyển sang `HmacSHA384` và kiểm tra độ dài 96 cùng vector tham chiếu tương ứng.

### Bài tập 4 — HTTP canonical request

Cho request `POST /v1/orders?currency=VND`, body JSON cố định, `X-Key-Id`, timestamp và nonce. Hãy tính SHA-256 hex của raw body, tạo canonical bytes theo LF rồi tính HMAC hex. Sửa một byte path hoặc body và kiểm tra tag cũ không khớp.

### Bài tập 5 — Gateway và signature normalization

Chạy client → gateway → verifier với `X-Signature` lowercase. Cố tình cấu hình middleware uppercases **giá trị** hoặc thêm whitespace. Quan sát verifier reject đúng contract và xác định nguyên nhân. Đồng thời test header `X-Signature` lặp, cả khác chữ hoa/thường của **tên header**.

### Bài tập 6 — Key rotation và replay

Cấp `keyId` mới cho client và dùng secret tương ứng tạo chữ ký mới. Kiểm tra request ký bằng secret cũ không khớp khi tự đổi sang key ID mới. Gửi lại signed request có nonce cũ và phân biệt HMAC vẫn đúng với lý do bị replay gate từ chối.

## 19. Checklist triển khai hex signature

- [ ] Chỉ rõ algorithm HMAC, protocol version, full/truncated tag policy và encoding trong tài liệu tích hợp.
- [ ] HMAC tag được tính trên **canonical request bytes**, không trên một chuỗi tùy tiện khác.
- [ ] Full HMAC-SHA256 tag = 32 byte = **64 hex**, SHA384 = 48 byte = **96 hex**, SHA512 = 64 byte = **128 hex**.
- [ ] Hex encoding giữ **hai ký tự mỗi byte**, kể cả byte `00` ở đầu.
- [ ] Dùng encoder chuẩn như Java 17 `HexFormat`; không mã hóa tag bằng `BigInteger.toString(16)`.
- [ ] Wire format quy định lowercase/uppercase, prefix, delimiters, whitespace và tên header chính xác.
- [ ] Verifier kiểm tra **exact length**, character set, one-value-only header rồi decode hex thành bytes.
- [ ] HMAC được so sánh theo **byte đầy đủ** với `MessageDigest.isEqual`, không so prefix/cắt tag.
- [ ] Thuật toán/encoding do **server contract và key record** quyết định; không fallback mù quáng theo độ dài.
- [ ] Key ID và metadata có ảnh hưởng xác thực được ký và đối chiếu với registry tin cậy.
- [ ] Body digest hex và signature hex được hiểu khác nhau; không nhầm SHA-256 body hash với MAC.
- [ ] Method, URI, signed headers, raw body, UTF-8 và LF canonicalization được xác định chặt chẽ.
- [ ] Timestamp/nonce được ký; replay store nguyên tử có TTL bao phủ cửa sổ chấp nhận.
- [ ] Key rotation có ID mới, secret an toàn, trạng thái thu hồi và lịch chuyển tiếp rõ ràng.
- [ ] Gateway không sửa signature value hoặc signed fields ngoài contract; xử lý header trùng, CR/LF, framing đúng protocol.
- [ ] HTTPS/TLS bảo vệ kết nối; log không để lộ secret hoặc full signed request nhạy cảm.
- [ ] Authentication không thay authorization: kiểm tra principal/action/resource/tenant riêng.
- [ ] Có known-answer tests RFC 4231, format fuzz tests, negative HMAC tests và integration tests qua gateway.

## 20. Câu hỏi tự kiểm tra

1. **Hex signature là một thuật toán ký riêng phải không?** Không. Hex chỉ biểu diễn byte tag đã được HMAC tạo ra.
2. **HMAC-SHA256 đầy đủ cần bao nhiêu ký tự hex?** 64 ký tự vì tag có 32 byte.
3. **HMAC-SHA384 đầy đủ cần bao nhiêu ký tự hex?** 96 ký tự vì tag có 48 byte.
4. **Vì sao `00` ở đầu tag phải giữ nguyên?** Nó biểu diễn một byte thật. Bỏ `00` làm đổi dãy byte và độ dài tag.
5. **Vì sao không nên dùng `BigInteger.toString(16)` để encode HMAC?** Vì có thể mất leading zeros và gặp khác biệt về dấu của số nguyên.
6. **Hex uppercase có thể decode thành cùng byte như lowercase không?** Có, nhưng contract lowercase-only có thể từ chối uppercase để đảm bảo một wire representation.
7. **`X-Signature` có được đưa vào chính canonical request tạo ra nó không?** Thông thường không, vì đó là tag đầu ra cần so sánh.
8. **Body SHA-256 hex và HMAC-SHA256 signature hex có cùng mục đích không?** Không. Body digest không khóa; HMAC tag có secret để xác thực canonical bytes.
9. **Chuỗi có đúng 64 ký tự lowercase hex có đủ để request được chấp nhận không?** Không. Còn phải kiểm tra HMAC, key status, timestamp/nonce và authorization.
10. **Có thể dùng chiều dài signature để tự chọn HmacSHA256 hay HmacSHA384 không?** Không nên; algorithm phải được chọn từ server contract/key record.
11. **Khi gateway giữ header hex nhưng đổi URI đã ký, HMAC có còn đúng không?** Không nhất thiết; canonical bytes thay đổi nên tag có thể không khớp.
12. **Một request có signature hex và HMAC đúng có thể bị replay không?** Có. Cần nonce store nguyên tử và timestamp đã ký.
13. **Hex signature đúng có cấp quyền truy cập tenant khác không?** Không. Authorization luôn dựa vào principal và resource policy phía server.

## 21. Tài liệu tham khảo

- **RFC 2104 — HMAC: Keyed-Hashing for Message Authentication.** Định nghĩa cơ chế HMAC với shared secret và hash nền.
- **RFC 4231 — Identifiers and Test Vectors for HMAC-SHA-224, HMAC-SHA-256, HMAC-SHA-384, and HMAC-SHA-512.** Cung cấp known-answer tests cho các HMAC phổ biến.
- **RFC 4648 — The Base16, Base32, and Base64 Data Encodings.** Mô tả Base16 (hex), Base32 và Base64 encoding.
- **NIST FIPS 198-1 — The Keyed-Hash Message Authentication Code (HMAC).** Tài liệu tham chiếu về thuật toán HMAC.
- **Java SE 17 — `java.util.HexFormat`, `javax.crypto.Mac`, `java.security.MessageDigest`.** API encode/decode hex, tính HMAC và so sánh digest.

**Kết luận:** **Hex signature là hình thức truyền tải của HMAC tag, không phải cơ chế xác thực tự thân.** Muốn tích hợp an toàn, cần xác định đúng thuật toán và kích thước tag, một wire format hex duy nhất, strict validation, byte decoding và so sánh HMAC đầy đủ. Sau đó vẫn phải bảo đảm canonical HTTP request nhất quán, shared secret/key rotation an toàn, timestamp/nonce chống replay, proxy/gateway không đổi ý nghĩa request và authorization độc lập với chữ ký.
