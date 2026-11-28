# Tính HMAC

**Tính HMAC** là bước cốt lõi của quy trình **ký HTTP request bằng shared secret**: client tạo một dãy byte **canonical request** theo hợp đồng chung, sử dụng khóa bí mật và thuật toán HMAC để tạo **message authentication code (MAC tag)**, sau đó encode tag thành chữ ký gửi kèm HTTP request. Server tái tạo **cùng dãy byte**, lấy đúng secret và tự tính lại HMAC để xác minh.

Nếu client/server bất đồng chỉ một byte trong canonical request — dấu xuống dòng, path, cách escape query, header value hay JSON body — hai tag sẽ khác nhau dù cả hai đều dùng đúng `HmacSHA256` và đúng secret. Vì vậy cần xem phép tính HMAC **cùng với** việc chọn khóa, chuẩn hóa thông điệp và vòng đời request.

Bài học thuộc chương **Ký request** trong mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Mô-đun hướng tới thiết kế xác thực HTTP request bằng HMAC với shared secret và canonical request có thể bao gồm phương thức, URI, header hoặc body theo hợp đồng ký; người học thực hành xác minh chữ ký, chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt xác thực với phân quyền.

> **Nguyên tắc:** HMAC nhận **byte secret** và **byte thông điệp**, không nhận khái niệm trừu tượng như “một object JSON” hay “URL đã được người dùng nhìn thấy”. Mọi bước từ HTTP request đến canonical bytes phải được định nghĩa và kiểm thử có thể tái tạo.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả HMAC khác SHA-256 thông thường, encryption, digital signature bất đối xứng và checksum như thế nào.
2. Giải thích công thức HMAC, vai trò khóa, hash nền và độ dài tag.
3. Thiết kế pipeline **request → canonical bytes → HMAC bytes → encoded signature**.
4. Sử dụng Java 17 `Mac.getInstance("HmacSHA256")` và `SecretKeySpec` để tính một tag đầy đủ.
5. Kiểm thử HMAC primitive bằng vector RFC 4231 trước khi ghép vào HTTP.
6. Viết client signer và server verifier theo một hợp đồng canonical request cố định.
7. Phát hiện nguyên nhân chữ ký sai từ path/query/header/body/encoding/proxy, không nhầm với lỗi HMAC.
8. Áp dụng timestamp/nonce, key rotation, audience binding và authorization sau khi xác minh.

## 2. Bốn khái niệm phải tách biệt

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| **Shared secret** | 32 byte được cấp an toàn cho client và verifier | Khóa chỉ những bên có thẩm quyền mới biết |
| **Canonical request** | UTF-8 bytes của method, path, query, signed headers, body digest... | Dữ liệu cụ thể được HMAC bảo vệ |
| **HMAC tag** | 32 byte đầu ra của HMAC-SHA256 | Mã xác thực thông điệp dưới khóa chung |
| **Signature encoding** | Base64URL hoặc hex của tag bytes | Đưa tag vào header HTTP dạng văn bản |

Ví dụ tổng quát:

~~~text
K_mac  : byte[] bí mật
M      : canonical request byte[]
T      : HMAC-SHA256(K_mac, M)              // 32 byte
S      : Base64URL_NoPadding(T)             // 43 ký tự
Header : X-Signature: S
~~~

Đường xác minh tương ứng:

~~~text
keyId -> server-side key record -> K_mac
request đã nhận -> canonical request byte[] M'
expectedTag = HMAC-SHA256(K_mac, M')
suppliedTag = Base64URL_Decode(X-Signature)

validMac = constant-time comparison(expectedTag, suppliedTag)
~~~

**Điểm quan trọng:** Server **không** giải mã tag ra request, không dùng tag để giải mã payload. HMAC là kiểm tra **toàn vẹn và xác thực nguồn theo shared secret**, không phải encryption và không tạo tính bí mật nội dung.

### 2.1. HMAC, hash, encryption và chữ ký số

| Cơ chế | Có khóa bí mật? | Mục tiêu chính | Điểm khác với HMAC request signing |
| --- | --- | --- | --- |
| SHA-256 | Không | Digest kiểm tra byte thay đổi khi có bản gốc đáng tin | Attacker có thể tự tính hash mới cho dữ liệu đã sửa |
| **HMAC-SHA256** | Có shared secret | Message authentication và integrity | Hai bên biết cùng secret có khả năng tạo tag |
| AES-GCM | Có symmetric key | Confidentiality + authenticated encryption | Mã hóa payload; khác với HMAC trên canonical HTTP request |
| RSA/ECDSA/EdDSA | Private/public key | Chữ ký số bất đối xứng | Verifier có thể xác minh bằng public key mà không sở hữu signing private key |
| CRC32 | Không | Phát hiện lỗi truyền dữ liệu ngẫu nhiên | Không an toàn trước attacker chủ động sửa dữ liệu |

Trong ngữ cảnh API HMAC, cách gọi “signature” là thông dụng, nhưng về mặt mật mã tag HMAC **không cung cấp tính không thể chối bỏ (non-repudiation)** như một số ứng dụng chữ ký bất đối xứng: cả client và server cùng biết shared secret và có thể tính tag.

## 3. HMAC hoạt động ở cấp mật mã

HMAC được chuẩn hóa trong RFC 2104 và NIST FIPS 198-1. Với một hash `H` có kích thước block `B` và độ dài digest `L`:

\[
\operatorname{HMAC}(K,m) =
H\big((K'\oplus opad)\,\|\,H((K'\oplus ipad)\,\|\,m)\big)
\]

Trong đó:

- `K` là shared secret.
- `m` là **dãy byte thông điệp** cần ký.
- `K'` là khóa được xử lý để có đúng `B` byte: khóa dài hơn `B` được hash trước, sau đó được pad bằng zero; khóa ngắn hơn được pad zero.
- `ipad` là byte `0x36` lặp lại cho đủ một block.
- `opad` là byte `0x5c` lặp lại cho đủ một block.
- `⊕` là XOR theo bit; `||` là nối byte.
- Digest kết quả của phép hash ngoài cùng là **tag HMAC đầy đủ**.

Không cần tự triển khai công thức này trong mã ứng dụng. Java JCA đã cung cấp `Mac` để sử dụng HMAC. Công thức giúp giải thích vì sao **HMAC không đơn giản là `SHA256(key || message)`**, và vì sao thay canonical bytes làm thay đổi tag.

### 3.1. Kích thước block và tag

| Thuật toán | Java JCA name | Block size của hash nền | Tag đầy đủ | Hex tag | Base64URL không padding |
| --- | --- | --- | --- | --- | --- |
| HMAC-SHA256 | `HmacSHA256` | 64 byte | 32 byte | 64 ký tự | 43 ký tự |
| HMAC-SHA384 | `HmacSHA384` | 128 byte | 48 byte | 96 ký tự | 64 ký tự |
| HMAC-SHA512 | `HmacSHA512` | 128 byte | 64 byte | 128 ký tự | 86 ký tự |

Kích thước HMAC tag phụ thuộc thuật toán **không phụ thuộc kích thước HTTP body**. Một request 0 byte body và request 5 MB body khi dùng full HMAC-SHA256 đều có **32-byte tag**.

**Không chọn thuật toán bằng độ dài tag do client khai.** Server phải xác định thuật toán từ contract version và key record được phép, sau đó kiểm tra tag đúng độ dài/encoding của thuật toán đã chọn.

### 3.2. HMAC tag không phải entropy của secret

Không thể suy từ “32-byte output” rằng secret chứa 256 bit entropy. Một secret rất yếu như `password123` vẫn tạo ra HMAC-SHA256 32 byte, nhưng có nguy cơ bị brute-force/dictionary attack nếu attacker có message và tag.

Thực hành tốt:

- Sinh secret bằng **CSPRNG**, ví dụ 32 byte ngẫu nhiên cho HMAC-SHA256.
- Không lấy secret trực tiếp từ mật khẩu người dùng, số điện thoại, UUID tuần tự hoặc chuỗi đoán được.
- Nếu cần derive subkeys từ master key, dùng KDF phù hợp với context rõ ràng; không tự “chế” bằng nối chuỗi.
- Bảo vệ secret trong secret manager, phân quyền truy cập, audit và kế hoạch rotation/revocation.
- Chỉ truyền **key ID và tag**, không truyền secret trong HTTP request.

## 4. Hợp đồng tính HMAC phải rõ từng byte

HMAC không có hiểu biết về HTTP semantics. Các bên cần công bố một **signing contract** xác định chính xác:

1. Thuật toán HMAC nào được dùng.
2. Secret có encoding gì khi được cấp phát (`raw bytes`, hex hay Base64).
3. Dữ liệu nào được đưa vào canonical request và thứ tự của chúng.
4. Path và query có phải dạng đã encode hay canonical URI, xử lý duplicate/empty thế nào.
5. Header nào phải ký; cách viết tên, giá trị, whitespace, header lặp.
6. Body digest được tính từ byte nào, trước/sau compression/parser.
7. Canonical string dùng UTF-8, LF hay CRLF, có LF cuối hay không.
8. Signature đặt ở header nào, encoding gì, padding thế nào.
9. Key ID/algorithm/version/audience được ràng buộc vào chữ ký ra sao.
10. Timestamp/nonce và chính sách replay/expiry/clock skew.
11. Gateway, reverse proxy và router xử lý route/authority có giống những gì đã ký không.

Nếu hợp đồng chỉ viết “ký URL + body”, hai client khác thư viện có thể tính tag khác nhau dù cùng secret.

### 4.1. Pipeline byte trong request signing

~~~mermaid
flowchart TD
    A[HTTP method + URI + headers + raw body] --> B[Validate request components]
    B --> C[Canonical path / query / signed headers]
    B --> D[SHA-256 của raw body bytes]
    C --> E[Canonical text theo contract V1]
    D --> E
    E --> F[UTF-8 canonical bytes]
    G[Key ID] --> H[Lookup secret tin cậy]
    H --> I[HMAC-SHA256]
    F --> I
    I --> J[Tag bytes 32 byte]
    J --> K[Base64URL without padding]
    K --> L[X-Signature header]
~~~

Phía client làm pipeline này **trước khi gửi request**. Server tái tạo từ HTTP request **thực nhận tại điểm xác minh**, không tin canonical text do client tự khai trong một header không được bảo vệ.

### 4.2. Tách canonical request khỏi signature value

Nếu `X-Signature` là tag được tạo từ canonical request, thông thường **không đưa chính `X-Signature` vào đầu vào tạo ra nó** (tránh phụ thuộc vòng). Ngược lại `X-Key-Id`, `X-Timestamp`, `X-Nonce` và version metadata có ảnh hưởng đến xác thực cần được ràng buộc.

Đừng nhầm “signature không được ký” với “mọi signature metadata đều không cần ký”. Thay nonce/timestamp không được làm tag cũ tiếp tục hợp lệ, nếu không lớp chống replay có thể bị lách.

## 5. Ví dụ contract HMAC-HTTP-V1: cố định thuật toán và field

Để có thể thực hành đầy đủ, bài học sử dụng một contract **minh họa**:

| Hạng mục | Quy định V1 |
| --- | --- |
| Algorithm | **HMAC-SHA256**, tag 32 byte đầy đủ |
| Header chữ ký | `X-Signature` |
| Signature encoding | Base64URL **không padding**, đúng 43 ký tự |
| Key ID header | `X-Key-Id`, trỏ đến secret/key record ở server |
| Freshness headers | `X-Timestamp`: Unix seconds; `X-Nonce`: 16 byte CSPRNG encode lowercase hex |
| Audience | `orders-api`, cố định và kiểm tra theo key registry |
| Method | Uppercase `GET`, `POST`, `PUT` hoặc `DELETE`, theo endpoint policy |
| Canonical path | Hợp đồng path riêng, bắt đầu `/`, không có URI ambiguity |
| Canonical query | Hợp đồng query riêng: parse/sort/encoding xác định |
| Signed header | `Content-Type` và các metadata `X-Key-Id`, `X-Timestamp`, `X-Nonce` |
| Body digest | SHA-256 của **raw body bytes**; encode lowercase hex 64 ký tự |
| Canonical text | UTF-8; các dòng phân tách bởi **LF**; **không có LF cuối** |
| Cơ chế replay | Server kiểm tra timestamp và nonce bằng atomic shared store |
| Kiểm soát khóa | Server định nghĩa algorithm, status, audience, principal và secretRef theo key ID |

Dùng HMAC-SHA256 trong ví dụ để các byte và API Java minh họa rõ ràng; có thể chọn HMAC-SHA384 với contract khác, nhưng **không được tự đổi một phía**.

### 5.1. Request mẫu

~~~http
POST /v1/orders?currency=VND&sku=A12 HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: partner-a-k3
X-Timestamp: 1790000000
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <43-character-base64url-tag>

{"sku":"A12","quantity":2}
~~~

Đây là **request minh họa**, không phải request hiện hành: timestamp cố định chỉ dùng để làm ví dụ. Để có một tag có thể gửi thực, thay placeholder bằng phép tính HMAC từ secret thật của credential và chính byte body thực gửi.

### 5.2. Canonical request từ ví dụ

Giả sử path/query và signed headers đã được validate/canonicalize theo contract và giữ giá trị như trên:

~~~text
HMAC-HTTP-V1
POST
/v1/orders
currency=VND&sku=A12
audience:orders-api
content-type:application/json
x-key-id:partner-a-k3
x-timestamp:1790000000
x-nonce:6bfb21974a08417199273b09ca49a3ec
body-sha256:<64-lowercase-hex-of-raw-body>
~~~

Thay dòng placeholder bằng SHA-256 thật của raw UTF-8 body:

~~~text
{"sku":"A12","quantity":2}
~~~

Chuỗi canonical có **10 dòng**, nối bởi một byte LF `0x0A` giữa mỗi hai dòng và **không thêm LF ở cuối**. Body minh họa không có newline sau dấu `}`; nếu client gửi thêm `\n` trong HTTP body, digest phải tính **có** byte newline ấy.

### 5.3. Tại sao giữ các thành phần tách theo dòng?

Định dạng dòng cố định và field labels giúp tránh ghép nhầm:

~~~text
ab + c  -> abc
a  + bc -> abc
~~~

Nếu chỉ nối chuỗi không delimiter/length, hai tập thành phần khác nhau có thể tạo cùng byte. Ở V1, mỗi trường có **vị trí và delimiter rõ ràng**, các giá trị đầu vào bắt buộc **không chứa CR/LF**. Với dữ liệu phức tạp cho phép newline, nên encode hoặc dùng length-prefix/structured canonical representation theo protocol khác.

### 5.4. Không tự sort query/header khi chưa có hợp đồng

Một hệ thống có thể chọn sorted query trong đó `a=1&b=2` và `b=2&a=1` có canonical query giống nhau **nếu query là unordered map không có duplicate keys**. Hệ thống khác coi thứ tự là dữ liệu. HMAC không tự phân xử điều này; phải đặt rule và test.

Tương tự, tên header HTTP không phân biệt hoa/thường, nhưng giá trị header có thể khác vì whitespace hoặc proxy. Tập signed headers phải được cố định hoặc kiểm tra theo policy bắt buộc; không để caller xóa body digest/method/path khỏi chữ ký bằng cách tự sửa `signedHeaders`.

## 6. Cách tính HMAC bằng tay ở cấp khái niệm

Giả sử có một dãy canonical bytes `M` và secret bytes `K`. Với `HmacSHA256`:

1. Nếu `K` dài hơn SHA-256 block size (64 byte), hash `K` thành 32 byte.
2. Zero-pad `K` tới 64 byte để được `K'`.
3. XOR `K'` với 64 byte `0x36` để tạo inner key block.
4. Tính `inner = SHA256((K' XOR ipad) || M)`.
5. XOR `K'` với 64 byte `0x5c` để tạo outer key block.
6. Tính `tag = SHA256((K' XOR opad) || inner)`.
7. Trả về tag **32 byte**, sau đó encode thành hex 64 ký tự hoặc Base64URL không padding 43 ký tự.

~~~text
HMAC-SHA256(K, M)
  = SHA256( (K' XOR 0x5c...5c)
            ||
            SHA256( (K' XOR 0x36...36) || M ) )
~~~

Những bước trên giúp hiểu HMAC, nhưng code production nên dùng JCA `Mac` hoặc một thư viện mật mã đã được kiểm chứng, không tự triển khai bitwise XOR/padding.

### 6.1. Vì sao hash thuần không đủ?

Giả sử server kiểm tra:

~~~text
X-Signature = SHA256(canonicalRequest)
~~~

Bất kỳ ai thay request đều có thể tự tính SHA-256 mới. HMAC dùng secret để attacker không sở hữu credential **không thể tự tạo tag hợp lệ** cho thông điệp đã sửa theo giả định an toàn mật mã.

Cũng không nên tự dùng:

~~~text
SHA256(secret || canonicalRequest)
SHA256(canonicalRequest || secret)
~~~

để thay HMAC: đó không phải thiết kế được chuẩn hóa/đánh giá tương đương cho chức năng này.

## 7. Java 17: primitive tính HMAC-SHA256

Trong Java, API tiêu chuẩn là `javax.crypto.Mac`:

~~~java
import java.security.GeneralSecurityException;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacSha256 {
    public static final int TAG_BYTES = 32;

    private HmacSha256() {}

    public static byte[] compute(
            byte[] secretBytes, byte[] messageBytes)
            throws GeneralSecurityException {

        if (secretBytes == null || secretBytes.length == 0
                || messageBytes == null) {
            throw new IllegalArgumentException("Invalid MAC input");
        }

        // Một instance Mac cho mỗi phép tính: Mac là stateful.
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secretBytes, "HmacSHA256"));
        byte[] tag = mac.doFinal(messageBytes);

        if (tag.length != TAG_BYTES) {
            throw new GeneralSecurityException("Unexpected HMAC length");
        }
        return tag;
    }
}
~~~

Quan trọng:

- `Mac.getInstance("HmacSHA256")` chỉ chọn **MAC algorithm**, không encode chữ ký.
- `secretBytes` là **key bytes thực**, không mặc nhiên là `secretString.getBytes(UTF_8)` khi secret được cấp phát dưới dạng hex/Base64.
- `messageBytes` là canonical request bytes đã được chuẩn hóa, không phải raw JSON object.
- `doFinal()` trả byte[] của tag; nó **không** trả hex string hoặc Base64 string.
- Không dùng chung một `Mac` instance đang được cập nhật giữa nhiều request/thread; tạo instance per computation hoặc có chiến lược thread confinement rõ.
- Không hardcode secret vào source, log hoặc URL; lấy từ quản lý secret đáng tin.
- Có thể dùng `Mac.update(...)` rồi `doFinal()` để xử lý nhiều khối input cùng một MAC, nhưng canonical bytes vẫn phải chính xác theo contract.

### 7.1. Secret encode bằng hex hoặc Base64

Nếu secret provisioning cung cấp:

~~~text
secretAsHex = "00112233445566778899aabbccddeeff..."
~~~

thì server/client phải **decode hex thành byte**:

~~~java
byte[] secretBytes =
        java.util.HexFormat.of().parseHex(secretAsHex);
~~~

Nếu secret được cấp dưới dạng Base64:

~~~java
byte[] secretBytes =
        java.util.Base64.getDecoder().decode(secretAsBase64);
~~~

Không dùng trực tiếp UTF-8 của chuỗi biểu diễn nếu hợp đồng nói rằng nó **mã hóa khóa nhị phân**:

~~~text
HexDecode("3031") -> [0x30, 0x31]
UTF8("3031")      -> [0x33, 0x30, 0x33, 0x31]
~~~

Hai byte array khác nhau sẽ cho hai HMAC tag khác nhau. Dùng một format secret được cấp phát ổn định, và test cả decoder ở client/server.

## 8. Java 17: encode tag thành chữ ký HTTP

Contract V1 yêu cầu Base64URL không padding:

~~~java
import java.util.Base64;
import java.util.HexFormat;

byte[] tagBytes = HmacSha256.compute(secretBytes, canonicalBytes);

// Format chính thức của HMAC-HTTP-V1:
String signature =
        Base64.getUrlEncoder().withoutPadding()
                .encodeToString(tagBytes);

if (signature.length() != 43) {
    throw new IllegalStateException("Unexpected signature length");
}

// Tùy chọn cho kiểm thử/debug không phải wire format V1:
String tagHex = HexFormat.of().formatHex(tagBytes);
assert tagHex.length() == 64;
~~~

`Base64URL` dùng `-`, `_` thay cho `+`, `/` và trong V1 này **không có ký tự `=` padding**. Nó thuận tiện cho header hoặc URL-safe field, nhưng điều đó không có nghĩa được đưa secret vào query string.

Hex/Base64URL chỉ là encoding của **cùng tag byte**. Nếu client gửi hex 64 ký tự còn server chờ Base64URL 43 ký tự, server phải từ chối; không tự thử nhiều encoding để tìm một kết quả khớp.

### 8.1. Chữ ký không cần bí mật nhưng không nên công khai signed request còn hạn

`X-Signature` không phải khóa lâu dài; verifier cần đọc nó để so sánh. Tuy nhiên, kẻ lấy được **toàn bộ signed request còn hạn** (method/URI/body/timestamp/nonce/signature) có thể thử replay. Vì vậy vẫn dùng HTTPS/TLS và giới hạn logging của chữ ký hoặc raw request nhạy cảm.

## 9. Golden test HMAC với RFC 4231

Trước khi nối HMAC với HTTP, hãy kiểm tra primitive tính MAC với **known-answer test (KAT)**. RFC 4231 cung cấp vector cho HMAC-SHA256, HMAC-SHA384 và HMAC-SHA512.

### 9.1. RFC 4231 test case 1: HMAC-SHA256

~~~text
Key:       20 byte, byte nào cũng bằng 0x0b
Data:      ASCII "Hi There"
Expected:  HMAC-SHA256 tag 32 byte

Hex:
b0344c61d8db38535ca8afceaf0bf12b
881dc200c9833da726e9376c2e32cff7
~~~

Hex trên được xuống dòng **chỉ để trình bày**; tag thực là 64 ký tự liên tiếp sau khi nối hai dòng.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

byte[] secret = new byte[20];
Arrays.fill(secret, (byte) 0x0b);

byte[] message = "Hi There".getBytes(StandardCharsets.US_ASCII);
byte[] actual = HmacSha256.compute(secret, message);

String expectedHex =
        "b0344c61d8db38535ca8afceaf0bf12b"
      + "881dc200c9833da726e9376c2e32cff7";

String actualHex = HexFormat.of().formatHex(actual);
if (!expectedHex.equals(actualHex)) {
    throw new AssertionError("RFC 4231 HMAC-SHA256 test failed");
}
~~~

Nếu KAT này **PASS**, JCA/HMAC/byte encoding của test đang hoạt động theo kỳ vọng. Nếu một HTTP signature tiếp tục không khớp, lỗi có thể ở canonicalization, secret provisioning, algorithm selection, Base64URL encoding, proxy hoặc metadata; không nên sửa ngẫu nhiên cách dùng `Mac`.

### 9.2. Mở rộng sang HMAC-SHA384

Với cùng key 20 byte `0x0b` và data `Hi There`, vector HMAC-SHA384 test case 1 là:

~~~text
afd03944d84895626b0825f4ab46907f
15f9dadbe4101ec682aa034c7cebc59c
faea9ea9076ede7f4af152e8b2fa9cb6
~~~

Tag là **48 byte**, có **96 ký tự hex**. Trong Java đổi thuật toán thành `HmacSHA384` ở cả `Mac.getInstance(...)` và `SecretKeySpec`; đồng thời cập nhật **contract tag length/encoding**, không chỉ đổi một dòng code ở client.

## 10. Java 17: xây canonical request bytes trước khi ký

Đoạn mã sau biểu diễn hợp đồng V1 tại mục 5. Nó nhận **các thành phần đã canonicalize** và thực hiện bước tập hợp cuối cùng cùng body SHA-256.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.regex.Pattern;

public final class HmacHttpV1Canonical {
    private static final Pattern METHOD =
            Pattern.compile("GET|POST|PUT|DELETE");
    private static final Pattern KEY_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,80}");
    private static final Pattern NONCE =
            Pattern.compile("[0-9a-f]{32}");

    private HmacHttpV1Canonical() {}

    public static byte[] bytes(
            String method,
            String canonicalPath,
            String canonicalQuery,
            String contentType,
            String keyId,
            long timestampSeconds,
            String nonce,
            byte[] rawBody) throws GeneralSecurityException {

        if (method == null || !METHOD.matcher(method).matches()
                || canonicalPath == null
                || !canonicalPath.startsWith("/")
                || canonicalQuery == null
                || !"application/json".equals(contentType)
                || keyId == null || !KEY_ID.matcher(keyId).matches()
                || timestampSeconds < 0
                || nonce == null || !NONCE.matcher(nonce).matches()
                || rawBody == null) {
            throw new IllegalArgumentException("Invalid signing fields");
        }

        // Path/query phải được validate theo contract URI riêng trước đây.
        // Chặn tối thiểu CR/LF để chúng không phá ranh giới dòng.
        if (hasLineBreak(canonicalPath) || hasLineBreak(canonicalQuery)) {
            throw new IllegalArgumentException("Invalid canonical URI");
        }

        byte[] bodyHash = MessageDigest.getInstance("SHA-256")
                .digest(rawBody);
        String bodySha256Hex = HexFormat.of().formatHex(bodyHash);

        String canonicalText = String.join("\n",
                "HMAC-HTTP-V1",
                method,
                canonicalPath,
                canonicalQuery,
                "audience:orders-api",
                "content-type:" + contentType,
                "x-key-id:" + keyId,
                "x-timestamp:" + timestampSeconds,
                "x-nonce:" + nonce,
                "body-sha256:" + bodySha256Hex);

        return canonicalText.getBytes(StandardCharsets.UTF_8);
    }

    private static boolean hasLineBreak(String s) {
        return s.indexOf('\r') >= 0 || s.indexOf('\n') >= 0;
    }
}
~~~

**Điểm cần nhìn đúng về phạm vi của helper:**

- `canonicalPath` và `canonicalQuery` phải là **kết quả validator/canonicalizer của protocol**, không phải input raw chưa kiểm soát; kiểm tra CR/LF ở đây **không đủ** để chống encoded slash, duplicate query hoặc parser differential.
- `Content-Type` được cố định `application/json` theo ví dụ. Hợp đồng khác có thể cho thêm MIME type nhưng phải chuẩn hóa và ký đúng.
- Key ID được đưa vào chuỗi ký nhưng vẫn là **giá trị do client khai** cho đến khi server tra key record và HMAC khớp.
- `timestampSeconds` phải là Unix seconds; byte ký được tạo từ biểu diễn số thập phân do Java xuất. Nếu contract muốn giữ raw timestamp lexical form thì cần parse/serialize quy định riêng.
- Bước tính body hash phải dùng **rawBody đúng byte được HTTP client thực gửi và HTTP verifier nhận** theo ranh giới đã định nghĩa.
- Hàm này chỉ tạo canonical bytes. Nó chưa tìm secret, chưa so tag, chưa chống replay hoặc authorization.

### 10.1. Dùng raw body thay vì serialize object lần hai

Hai JSON sau có thể biểu thị cùng dữ liệu nhưng byte khác nhau:

~~~json
{"sku":"A12","quantity":2}
~~~

~~~json
{"quantity":2,"sku":"A12"}
~~~

Nếu client ký `SHA256(rawBody)` nhưng gửi body sau khi một serializer khác thay đổi thứ tự field/whitespace, verifier sẽ hash **byte body đã nhận** và ra digest khác.

Cách an toàn là:

~~~text
bodyBytes = serializeExactlyOnce(payload)
digest = SHA256(bodyBytes)
signature = HMAC(secret, canonicalRequestWithDigest)
sendHttpBody(bodyBytes)  // gửi đúng mảng byte bodyBytes
~~~

Tại server, body caching/streaming phải đảm bảo verifier và handler đọc **cùng nội dung đã được HMAC xác minh**, không để middleware làm body thay đổi sau bước kiểm tra mà handler không biết.

### 10.2. Dấu LF và line ending

~~~text
LF   = 0x0A
CRLF = 0x0D 0x0A
~~~

Nếu client nối canonical lines bằng `CRLF` còn verifier dùng `LF`, HMAC sai. Không dùng `System.lineSeparator()` để tạo canonical text vì Windows/Linux có thể khác nhau. Hợp đồng ví dụ yêu cầu **`"\n"` cố định** và không có LF cuối.

### 10.3. Vắng mặt query khác query rỗng có dấu ?

Trong canonical request, dòng query có thể là chuỗi rỗng. Nhưng protocol vẫn cần quyết định liệu request `/v1/orders` và `/v1/orders?` có được coi tương đương không. Một hợp đồng nghiêm ngặt có thể từ chối query hiện diện nhưng rỗng để tránh hai biểu diễn khác nhau có chung canonical bytes.

Vì ví dụ Java chỉ nhận `canonicalQuery` đã được tạo ở lớp khác, **không được dùng nó để tự suy đoán** trạng thái raw URI.

## 11. Java 17: client signing flow hoàn chỉnh ở mức ứng dụng

Một client signer thường thực hiện:

~~~mermaid
sequenceDiagram
    participant A as Application client
    participant K as Credential store
    participant S as Signer
    participant G as API Gateway

    A->>K: Chọn keyId, secret còn hiệu lực
    K-->>A: keyId + secret bytes
    A->>A: Tạo body bytes, method và URI
    A->>A: Timestamp + random nonce
    A->>S: Canonical components + raw body
    S->>S: SHA-256 body; canonical bytes
    S->>S: HMAC-SHA256 tag bytes
    S->>S: Encode Base64URL no-padding
    S-->>A: Signature value
    A->>G: HTTP request + signed metadata + X-Signature
~~~

### 11.1. Ví dụ gọi signer

~~~java
import java.util.Base64;

byte[] rawBody = "{\"sku\":\"A12\",\"quantity\":2}"
        .getBytes(java.nio.charset.StandardCharsets.UTF_8);

byte[] canonical = HmacHttpV1Canonical.bytes(
        "POST",
        "/v1/orders",
        "currency=VND&sku=A12",
        "application/json",
        "partner-a-k3",
        1790000000L,
        "6bfb21974a08417199273b09ca49a3ec",
        rawBody);

byte[] tag = HmacSha256.compute(secretBytes, canonical);
String signature = Base64.getUrlEncoder().withoutPadding()
        .encodeToString(tag);

// Header X-Signature phải mang signature.
// HTTP client phải gửi CHÍNH rawBody cùng path/query/headers đã ký.
~~~

Đoạn mã có **timestamp và nonce cố định chỉ để minh họa / viết golden test**. Request production phải lấy timestamp từ đồng hồ hiện hành và sinh nonce mới cho mỗi request.

### 11.2. Tạo nonce từ SecureRandom

~~~java
import java.security.SecureRandom;
import java.util.HexFormat;

SecureRandom secureRandom = new SecureRandom();

byte[] nonceBytes = new byte[16];  // 128 bit
secureRandom.nextBytes(nonceBytes);

String nonce = HexFormat.of().formatHex(nonceBytes);
// Đúng 32 ký tự lowercase hex cho contract ví dụ.
~~~

Không dùng `Math.random()`, timestamp đơn lẻ, counter cục bộ dễ lặp hoặc giá trị đoán được làm nonce cho hợp đồng này. Nonce không cần bí mật lâu dài, nhưng cần đủ ngẫu nhiên/không trùng trong phạm vi key và cửa sổ chấp nhận.

### 11.3. Metadata phải đi cùng byte được ký

Một signer không được làm:

~~~text
1. HMAC trên timestamp/nonce A
2. HTTP interceptor sinh timestamp/nonce B
3. Gửi request có chữ ký A nhưng header B
~~~

HMAC sẽ không khớp. Tất cả thành phần signed cần được **chốt trước khi ký**, và HTTP client/interceptor/proxy không được thay đổi chúng sau đó nếu không có quy trình ký lại rõ ràng.

## 12. Server verification: tính lại chứ không giải mã HMAC

Server không “decrypt HMAC”. Luồng đúng:

1. Parser/gateway kiểm tra framing, size, header counts và những giá trị mơ hồ.
2. Parse metadata có format chính xác: `X-Key-Id`, `X-Timestamp`, `X-Nonce`, `X-Signature`.
3. Tra key record theo **exact key ID** trong registry.
4. Kiểm tra key record: trạng thái, thuật toán, audience, credential lifetime, principal mapping.
5. Kiểm tra timestamp về mặt cú pháp và cửa sổ chấp nhận (có thể làm trước MAC để giảm chi phí).
6. Canonicalize request **nhận được tại ranh giới verifier**.
7. Dùng secret của key record tính **expected HMAC**.
8. Decode signature và so sánh đầy đủ **expected vs supplied tag bytes**.
9. Chỉ khi MAC hợp lệ, chặn nonce replay bằng shared atomic store.
10. Tạo authenticated principal, thực hiện authorization rồi mới chạy business logic.

~~~mermaid
flowchart TD
    R[HTTP request] --> F[Parse metadata và validate framing]
    F --> K[Lookup keyId và kiểm tra policy]
    K --> C[Canonicalize request nhận được]
    C --> M[Tính expected HMAC]
    M --> D[Decode và so sánh signature]
    D --> V{HMAC hợp lệ?}
    V -- Không --> E[Từ chối xác thực]
    V -- Có --> T[Timestamp, nonce/replay gate]
    T --> A{Fresh và nonce mới?}
    A -- Không --> E
    A -- Có --> P[Principal từ key record]
    P --> Z[Authorization theo action/resource]
    Z --> B{Có quyền?}
    B -- Không --> X[Từ chối truy cập]
    B -- Có --> H[Business handler]
~~~

### 12.1. Java: strict decode và so sánh tag

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.regex.Pattern;

public final class HmacHttpV1VerifyTag {
    private static final Pattern BASE64URL_NO_PADDING =
            Pattern.compile("[A-Za-z0-9_-]{43}");

    private HmacHttpV1VerifyTag() {}

    public static boolean verifyMac(
            byte[] secretBytes,
            byte[] canonicalBytes,
            String signatureHeader)
            throws GeneralSecurityException {

        if (signatureHeader == null
                || !BASE64URL_NO_PADDING.matcher(signatureHeader)
                        .matches()) {
            return false;
        }

        final byte[] supplied;
        try {
            supplied = Base64.getUrlDecoder().decode(signatureHeader);
        } catch (IllegalArgumentException malformed) {
            return false;
        }

        // Full HMAC-SHA256 tag: đúng 32 byte, một biểu diễn canonical.
        if (supplied.length != HmacSha256.TAG_BYTES
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(supplied)
                        .equals(signatureHeader)) {
            return false;
        }

        byte[] expected = HmacSha256.compute(
                secretBytes, canonicalBytes);

        return MessageDigest.isEqual(expected, supplied);
    }
}
~~~

Điểm cần lưu ý:

- `BASE64URL_NO_PADDING` chỉ cho 43 ký tự ASCII gồm chữ/số/`-`/`_`, không cho `=` padding.
- Decode tag **không đồng nghĩa tag hợp lệ**; cần tính expected MAC và so sánh.
- So sánh toàn bộ **32 byte**. Không chấp nhận prefix 8/16 byte hoặc signature bị cắt nếu contract yêu cầu full length.
- `MessageDigest.isEqual` dùng để so byte trong ngữ cảnh mật mã thay vì so hex/Base64 string.
- Không để exception tiết lộ secret, sự tồn tại key ID hoặc policy cho attacker. API có thể trả một lỗi xác thực thống nhất, log nguyên nhân nội bộ có kiểm soát.
- Class này **không có key lookup/freshness/replay/authorization**; không được coi `verifyMac == true` là đủ cho phép nghiệp vụ.

### 12.2. Kiểm tra timestamp

Giả sử client gửi timestamp Unix seconds và server cho phép:

~~~text
maxAgeSeconds:     300
maxFutureSkew:      30
timestamp:         signed, integer Unix seconds
~~~

Cửa sổ chính sách có thể kiểm tra với `now` (Unix seconds):

~~~text
timestamp <= now + maxFutureSkew
timestamp >= now - maxAgeSeconds
~~~

Dạng thực tế nên dùng **phép trừ/so sánh tránh overflow**, và rõ hành vi tại biên. Nếu có `expires`, cần ký giá trị đó, giới hạn max lifetime và kiểm tra expires cùng key lifetime.

Một helper Java 17 cho miền Unix seconds không âm được kiểm soát có thể là:

~~~java
public static boolean isFresh(
        long created, long now, long maxAge, long futureSkew) {

    if (created < 0 || now < 0 || maxAge < 0 || futureSkew < 0) {
        return false;
    }

    if (created <= now) {
        return now - created <= maxAge;
    }

    return created - now <= futureSkew;
}
~~~

Trong production, timestamp parser cần từ chối chuỗi không đúng format (`00123`, dấu `+`, số quá dài, milliseconds gửi nhầm seconds), đồng thời ràng buộc timestamp lexical representation vào canonical contract.

### 12.3. Nonce store và thứ tự xác minh

HMAC tự nó **không ngăn replay**: một request nguyên vẹn được gửi lại có thể cho cùng expected HMAC. Sau khi verify MAC:

~~~text
replayKey = "hmac:" + audience + ":" + keyId + ":" + nonce
atomicPutIfAbsent(replayKey, expiryTime)
  -> inserted: lần đầu, tiếp tục
  -> exists:   replay, từ chối
~~~

Yêu cầu:

- Nonce được HMAC ký để attacker không thay nonce mà vẫn dùng tag cũ.
- Store dùng chung giữa verifier instances, dùng **một thao tác nguyên tử** để kiểm tra và đánh dấu.
- TTL/expiry che phủ **toàn bộ thời gian request còn có thể được chấp nhận**; không xóa nonce quá sớm.
- Không ghi nonce dựa trên request chưa xác minh MAC để tránh attacker làm bẩn store.
- Với thao tác nhạy cảm, khi replay store không khả dụng nên **fail closed** theo chính sách đã thiết kế.
- Idempotency nghiệp vụ vẫn cần đối với client tạo **request mới** có nonce mới nhưng cùng event/đơn hàng.

## 13. Phân biệt lỗi tính HMAC với lỗi canonicalization

HMAC primitive là một phép tính xác định. Nếu cùng `K` và cùng `M`, expected tag phải giống nhau. Trong các lỗi thực tế, phần lớn khác biệt xuất hiện ở **byte đầu vào**.

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| RFC 4231 KAT thất bại | Sai algorithm, secret bytes hoặc cách gọi JCA | Dùng byte test cố định, kiểm tra vector |
| KAT PASS nhưng HTTP signature sai | Canonical request bytes khác | So sánh UTF-8 hex của canonical bytes trong test |
| Chỉ Windows client sai | Dùng CRLF/System.lineSeparator | Chuẩn hóa LF đúng contract |
| Chỉ URL có `%2F` sai | Percent-decoding path khác nhau | So sánh raw/canonical path qua gateway |
| Chỉ query đảo thứ tự sai | Sorting/duplicate/query rules khác | Golden tests canonical query |
| Chỉ JSON đẹp/compact sai | Hash body sau serialize khác nhau | Hash byte thực gửi, không parse/serialize lại |
| Chỉ một proxy sai | Rewrite path/headers/body hoặc TLS termination | E2E trace canonical bytes tại từng biên |
| Client ký đúng tag byte nhưng server reject | Base64URL/hex encoding hoặc header duplication | Test strict decoder/header parser |
| Request thứ hai bị reject dù tag đúng | Nonce đã dùng | Kiểm tra replay state (không sửa HMAC) |
| Sau key rotation mọi request sai | Client key ID/secret không đồng bộ | Kiểm tra registry, key status và clock |
| HMAC đúng nhưng trả 403 | Principal thiếu quyền | Kiểm tra authorization policy và resource |

### 13.1. Debug canonical bytes, không chỉ debug string hiển thị

Hai string có thể **nhìn gần như giống nhau** nhưng byte khác:

- LF `0A` và CRLF `0D 0A`.
- Dấu cách ASCII `0x20` và non-breaking space UTF-8.
- Unicode NFC và decomposed.
- `%2F` so với `/` trong path.
- JSON có hoặc không có newline cuối.
- Header value có leading/trailing whitespace.

Trong test environment, so sánh **hex dump của canonical UTF-8 bytes** cùng byte length. Trong production, tránh log toàn bộ canonical data chứa PII/body; có thể ghi checksum nội bộ, correlation ID và mã lỗi với kiểm soát truy cập phù hợp.

### 13.2. Đừng “thử mọi cách đến khi HMAC khớp”

Một verifier không nên thử:

~~~text
HMAC(rawPath)
HMAC(decodedPath)
HMAC(pathWithoutTrailingSlash)
HMAC(sortedQuery)
HMAC(originalQuery)
HMAC(secretOld), HMAC(secretNew), ...
~~~

để chấp nhận cách đầu tiên khớp. Điều này làm mơ hồ **phạm vi xác thực**, mở rộng số biểu diễn được chấp nhận, giảm khả năng kiểm tra policy và có thể tạo sai khác với router.

Hãy quy định **một canonicalization version**, một key record theo key ID, một algorithm được phép và một signature encoding đã xác định. Khi di trú, định nghĩa version/key policy rõ và test tương thích.

## 14. HTTP proxy/gateway và byte HMAC

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant G as Gateway / WAF
    participant V as HMAC Verifier
    participant A as Application

    C->>G: HTTP request với signature
    Note over G: Có thể rewrite path, query, header, body
    G->>V: Chuyển tiếp theo hợp đồng
    V->>V: Canonical request từ dữ liệu nhận được
    V->>V: Tính HMAC và so tag
    V->>V: Freshness + nonce
    V->>A: Principal tin cậy + request hợp lệ
    A->>A: Authorization rồi nghiệp vụ
~~~

### 14.1. Ký trước hay sau proxy rewrite?

**Verifier tại gateway** có thể kiểm tra byte request từ bên ngoài trước rewrite, sau đó truyền principal đáng tin và route có kiểm soát cho backend. Backend phải ngăn bị bypass và chỉ tin context xác thực qua kênh nội bộ được bảo vệ.

**Verifier tại backend** cần một hợp đồng cho dạng request **sau những biến đổi được phép** của gateway hoặc gateway phải giữ nguyên signed components. Nếu client ký path ngoài `/public/v1/orders` nhưng backend xác minh `/v1/orders`, HMAC không khớp trừ khi client/server đã định nghĩa chính xác mapping và biên tin cậy.

Không tin header `X-Original-URI` hoặc `X-Forwarded-Host` do client Internet tự gửi. Proxy phải xóa dữ liệu tự khai, thiết lập metadata đã kiểm soát và bảo vệ kênh nội bộ nếu verifier cần metadata đó.

### 14.2. Hop-by-hop header và body bytes

Proxy có thể thay `Connection`, `Content-Length` hoặc transport framing khi chuyển HTTP/1.1 ↔ HTTP/2. Đó không nhất thiết là lỗi signature nếu contract **không ký những header này** và body content bytes không đổi.

Tuy nhiên, HTTP framing phải được parser/gateway kiểm tra nghiêm ngặt để tránh request smuggling, đồng thời verifier và business handler phải tiêu thụ **cùng byte body có ý nghĩa**. Nếu `Content-Encoding` cho phép nén/giải nén, contract cần chốt việc body digest được tính **trước hay sau** biến đổi đó.

### 14.3. Authority/audience và cross-service replay

Nếu HMAC không ký hostname mà dùng `audience:orders-api`, server phải kiểm tra key record được phép cho `orders-api` và gateway/router thực sự đang xử lý request cho service ấy. Không được cho một signed request của orders bị dùng ở billing chỉ vì cả hai cùng secret, path và method.

Tốt hơn là tách secret theo service/audience và nguyên tắc least privilege khi có thể.

## 15. Key rotation, algorithm policy và tính HMAC

Một key registry record có thể gồm:

~~~yaml
keyId: partner-a-k3
principalId: partner-a-service
audience: orders-api
macAlgorithm: HmacSHA256
signatureEncoding: base64url-no-padding
secretRef: secrets/orders/partner-a/k3
status: ACTIVE
notBefore: "2026-09-01T00:00:00Z"
acceptUntil: "2027-01-01T00:00:00Z"
~~~

Đây là ví dụ **registry phía server**, không phải thông tin để client tự quyết algorithm hoặc tạo principal.

Luồng rotation:

1. Tạo secret mới bằng CSPRNG và `keyId` mới.
2. Phân phối secret theo kênh bảo vệ; triển khai key record mới tại verifier.
3. Client bắt đầu dùng `keyId` mới và **tính HMAC bằng secret mới** cho mỗi request.
4. Server có thể cho phép key cũ và key mới trong khoảng overlap hữu hạn theo trạng thái/key lifetime.
5. Giám sát lưu lượng sử dụng key ID; sau đó thu hồi ID cũ và làm mới cache ở các node.
6. Nếu nghi lộ secret, thực hiện revocation khẩn và ứng phó sự cố, không chờ hết overlap thông thường.

### 15.1. Vì sao không thử cả secret cũ và mới?

Nếu giữ nguyên `keyId` và thử nhiều secret đến khi tag khớp, verifier khó biết credential/rotation nào đã ký request, audit bị mơ hồ, cache có thể không đồng nhất và revocation khó chắc chắn.

Cách tốt là **mỗi key ID ánh xạ rõ tới một key record/version/secret**, và key ID được đưa vào canonical bytes hoặc ràng buộc đáng tin theo contract.

### 15.2. Thuật toán là chính sách, không phải lựa chọn tự do của client

Đừng để header tự khai:

~~~http
X-Mac-Algorithm: none
~~~

làm server bỏ xác minh. Ngay cả với tên thuật toán hợp lệ, server phải kiểm tra nó khớp contract/version/key record được phép. HMAC-SHA384 hoặc Base64URL/hex là các biến thể thiết kế, cần protocol/key policy và test vector tương ứng.

## 16. HMAC authentication không thay authorization

Giả sử client A có secret thật và tính HMAC hợp lệ cho:

~~~http
DELETE /v1/tenants/tenant-B/orders/42 HTTP/1.1
X-Key-Id: partner-a-k3
X-Timestamp: 1790000000
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <valid-tag-for-this-request>
~~~

Về mặt HMAC:

- Message đúng contract.
- Secret đúng credential A.
- Tag xác minh thành công.
- Timestamp/nonce có thể mới.

Nhưng **principal của tenant A không tự động có quyền xóa đơn hàng tenant B**. Server cần tách:

| Bước | Câu hỏi |
| --- | --- |
| Format và canonicalization | Request có cấu trúc hợp đồng ký hợp lệ không? |
| HMAC verification | Ai sở hữu secret tương ứng với key record này có thể đã tạo tag? |
| Freshness/replay | Request còn trong cửa sổ và chưa bị sử dụng lại không? |
| Authentication context | Principal tin cậy của key record là ai? |
| Authorization | Principal này được phép làm action trên resource/tenant cụ thể không? |
| Business validation | Dữ liệu và giao dịch có hợp lệ/idempotent không? |

Một client có secret A có thể cố tình ký yêu cầu vượt quyền; **HMAC đúng không cấp quyền**. Header `X-Tenant-Id` hoặc `X-Role` tự khai, dù có ký, vẫn không là nguồn quyền thay cho server policy.

## 17. Các sai lầm phổ biến khi tính HMAC

### 17.1. Tính HMAC trên JSON object thay vì raw bytes

Đối tượng JSON không có một serialization byte duy nhất. Ký một bản, gửi một bản khác khiến body digest/HMAC sai. Phải dùng cùng raw body bytes hoặc một chuẩn canonical JSON được quy định rõ.

### 17.2. Nhầm secret string với secret bytes

Secret được cấp dưới dạng hex/Base64 phải **decode đúng** trước khi đưa vào `SecretKeySpec`. Chuyển luôn ký tự hex thành UTF-8 tạo key khác.

### 17.3. Hash thường thay HMAC

`SHA256(secret + message)` không phải HMAC. Chỉ dùng primitive HMAC chuẩn như JCA `Mac`.

### 17.4. Không ký method hoặc URI

Nếu chỉ ký body, attacker có thể đổi method/path/query ảnh hưởng hành động hoặc tài nguyên mà giữ tag không đổi. Signed components phải bảo vệ semantics của endpoint.

### 17.5. Dùng newline phụ thuộc nền tảng

`System.lineSeparator()` và cách nối chuỗi có LF cuối khác nhau giữa client/server. Contract V1 dùng LF cố định, UTF-8 và không có LF cuối.

### 17.6. Ký header không ổn định hoặc bỏ header có ý nghĩa

Ký toàn bộ hop-by-hop headers khiến proxy làm HMAC sai; bỏ `Content-Type`, method override hoặc idempotency key có thể để dữ liệu ảnh hưởng business bị sửa mà MAC vẫn đúng. Tập ký cần dựa trên semantics và chính sách tin cậy.

### 17.7. Chấp nhận chữ ký sai length hoặc encoding

Với HMAC-SHA256 Base64URL no padding, yêu cầu **43 ký tự** biểu diễn đủ **32 byte**; từ chối padding tùy tiện, tag bị cắt, ký tự khác format. Không dùng so prefix.

### 17.8. Dùng equals trên chuỗi tag

Nên decode signature thành bytes và dùng `MessageDigest.isEqual` để so expected/supplied tag đủ độ dài, thay vì so chuỗi có thể khác representation.

### 17.9. Tính HMAC đúng rồi bỏ qua replay

Request còn hạn có thể bị gửi lại nguyên vẹn. Timestamp/nonce phải được ký, server kiểm tra cửa sổ và nonce store dùng chung, ghi nguyên tử sau MAC.

### 17.10. Coi HMAC hợp lệ là đủ quyền

Một credential có thể ký request bất kỳ trong khả năng tạo canonical bytes. Quyền thực thi vẫn được xác định bởi principal, action, resource và tenant phía server.

## 18. Ma trận kiểm thử tính HMAC

### 18.1. Primitive tests

| Test | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| RFC 4231 SHA256 case 1 | Key 0x0b × 20, data `Hi There` | Hex tag đúng vector |
| RFC 4231 SHA384 case 1 | Cùng key/data, thuật toán SHA384 | Hex tag 96 ký tự đúng vector |
| Message rỗng | Byte array rỗng làm message | HMAC trả tag đúng độ dài; có thể so golden vector |
| Same key/same message | Tính hai lần | Tag byte giống nhau |
| Change 1 byte message | Cùng key, sửa dữ liệu | Tag cũ không còn khớp với message mới |
| Change 1 byte secret | Cùng message, sửa key | Tag cũ không còn khớp với secret mới |
| Secret hex decoding | `HexDecode` vs `UTF8(hexString)` | Hai key khác nhau tạo tag khác |
| Encoding tag | HMAC-SHA256 32 byte | Base64URL 43 hoặc hex 64 theo contract |

### 18.2. Canonical request tests

| Ca | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Exact canonical bytes | Client/server dùng cùng V1 | HMAC khớp |
| Đổi method | `POST` → `DELETE`, giữ tag | Từ chối |
| Đổi path | `/orders/42` → `/orders/43` | Từ chối |
| Trailing slash | `/orders` → `/orders/` | Từ chối hoặc canonicalize theo contract có kiểm soát |
| Encoded slash | `%2F` khác slash literal | Từ chối input mơ hồ hoặc dùng một policy thống nhất |
| Query reorder | `a=1&b=2` vs `b=2&a=1` | Theo hợp đồng sort/preserve, không đoán |
| Query duplicate | `role=user&role=admin` | Reject hoặc xử lý theo multivalue policy ký rõ ràng |
| Header case | `Content-Type` vs `content-type` | Canonical name nhất quán; duplicates phải từ chối |
| Signed header tamper | `Content-Type` đổi MIME | HMAC sai hoặc contract từ chối |
| Unsigned telemetry header | Thay `User-Agent` | Tag có thể giữ nguyên; không dùng nó cho security |
| Raw body thay | Sửa một byte JSON | HMAC sai |
| JSON serialize lại | Đổi field order/whitespace | Digest raw body đổi; HMAC cũ sai |
| Body newline cuối | Thêm LF vào body | Body digest/HMAC đổi |
| Canonical newline | LF vs CRLF hoặc LF cuối | Byte khác; HMAC sai |
| Character encoding | UTF-8 vs encoding khác | HMAC khác hoặc reject |
| Algorithm downgrade | Client tự khai `none` | Từ chối theo policy server |
| Signature hex vs Base64URL | Đổi encoding không theo V1 | Reject |
| Truncated tag | Tag 16 byte thay vì 32 | Reject |
| Duplicate signature header | Hai `X-Signature` | Reject header mơ hồ |

### 18.3. HTTP/gateway/security tests

| Ca | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Header rewrite | Gateway đổi header signed | MAC sai, trừ mapping đã contract |
| Path rewrite | Gateway strip prefix | Verify ở đúng biên hoặc từ chối |
| HTTP/1.1 ↔ HTTP/2 | Proxy đổi framing | Body bytes/semantics được ký vẫn khớp |
| Content-Encoding | Gateway nén/giải nén | Contract định nghĩa byte hashed; không xác minh nhầm |
| Timestamp quá cũ | Tag đúng, thời gian ngoài window | Từ chối freshness |
| Timestamp tương lai | Vượt clock skew | Từ chối |
| Replay nguyên request | Gửi lần hai cùng nonce | Từ chối replay |
| Concurrent replay | Gửi đồng thời hai node | Atomic store cho tối đa một lần qua |
| Replay store unavailable | Simulate timeout | Theo fail-closed policy, không silently bypass |
| Key revoked | Tag đúng với secret cũ | Từ chối key status |
| Rotation overlap | K2 và K3 cùng đang hợp lệ | Mỗi key ID tính bằng đúng secret |
| Wrong audience | Mang request orders sang billing | Từ chối |
| Authorization failure | A gọi resource B, MAC đúng | Từ chối quyền |
| Business retry | Nonce mới nhưng same event/order | Idempotency xử lý tác động trùng |

### 18.4. Golden test xuyên client/server

Một bộ fixture gồm:

~~~text
protocolVersion
keyId
secretBytes dưới dạng test-only hex (không dùng production)
method
rawPath + canonicalPath
rawQuery + canonicalQuery
signedHeaderNamesAndValues
rawBodyBytes (hoặc file byte fixture)
bodySha256Hex
canonicalText
canonicalBytesHex
expectedTagBytesHex
expectedSignatureBase64Url
~~~

Với mỗi fixture, client signer và verifier phải cho ra **cùng canonical bytes và tag bytes**. Khi lỗi, so sánh từ trên xuống: secret bytes → canonical fields → canonical bytes → HMAC bytes → signature encoding. Không “sửa” HMAC bằng cách thử ngẫu nhiên nhiều cách normalize.

## 19. Tình huống thực tế: webhook tạo đơn đi qua gateway

Một đối tác tích hợp API đặt hàng và dùng HMAC-SHA256. Khách hàng báo lỗi “signature invalid” chỉ xảy ra khi gửi JSON có nhiều field và đi qua API gateway.

**Dấu hiệu:**

- RFC 4231 KAT của cả client và server đều PASS.
- Các request có body rỗng xác minh thành công.
- Request JSON có body thay đổi whitespace khi đến backend.
- Gateway được cấu hình parse JSON rồi serialize lại trước khi forward.

**Phân tích:** HMAC primitive đúng; **raw body bytes khác** giữa lúc client hash và lúc backend hash. Khi client ký digest của body A nhưng verifier nhận body B, canonical request đổi và HMAC không còn khớp.

**Khắc phục:**

1. Chọn điểm xác minh HMAC rõ ràng, ưu tiên trước các phép biến đổi body không thuộc contract.
2. Gửi chính byte body đã dùng để tạo digest.
3. Gateway không được tự sửa signed body nếu backend xác minh theo raw bytes, hoặc phải dùng một signing trust boundary khác được thiết kế rõ.
4. Kiểm thử JSON với thứ tự field, whitespace, Unicode và newline cuối.
5. Không tắt xác minh body digest để “cho hết lỗi”, vì như vậy mất bảo vệ nội dung quan trọng.

Tình huống khác: nếu HMAC thành công nhưng webhook bị xử lý hai lần, điều cần kiểm tra là **nonce/replay store và idempotency**, chứ không phải đổi HmacSHA256 sang HmacSHA512.

## 20. Bài tập thực hành

### Bài tập 1 — Vector RFC 4231

Viết Java dùng `Mac.getInstance("HmacSHA256")` tính HMAC từ key 20 byte `0x0b` và message ASCII `Hi There`. Encode tag thành hex để kiểm tra expected test vector, rồi encode Base64URL và xác nhận chuỗi dài 43 ký tự.

### Bài tập 2 — Tính HMAC từ request mẫu

Với request `POST /v1/orders?currency=VND&sku=A12` ở mục 5:

1. Chọn một **test secret 32 byte cố định** được lưu trong mã test (không dùng production).
2. Xác nhận body UTF-8 chính xác và SHA-256 body digest.
3. Tạo canonical text 10 dòng theo hợp đồng LF không có LF cuối.
4. Tính HMAC-SHA256 tag 32 byte.
5. Encode thành Base64URL không padding 43 ký tự.
6. Đổi `sku=A12` thành `sku=A13` và chứng minh tag cũ không xác minh được.

### Bài tập 3 — Mô phỏng lỗi byte đầu vào

Tạo ba canonical texts có nội dung hiển thị giống nhau nhưng khác:

- `LF` và `CRLF`.
- Có và không có newline cuối.
- JSON body thêm một dấu cách hoặc newline.

Tính HMAC mỗi biến thể và so sánh. Hãy kết luận rằng **canonicalization contract là một phần của giao thức mật mã**, không chỉ là formatting.

### Bài tập 4 — Client–server signing round-trip

Viết một HTTP client gửi method/URI/headers/body đã ký. Viết một verifier dùng key registry giả lập và `HmacHttpV1VerifyTag.verifyMac`. Test positive và negative khi sửa body, path, header hoặc signature; tránh sử dụng nonce tĩnh ngoài test.

### Bài tập 5 — Anti-replay

Thiết kế in-memory fake replay store với một thao tác insert-if-absent có đồng bộ hóa cho unit test, rồi mô tả cách thay bằng Redis `SET key value NX EX` hoặc store nguyên tử tương đương khi chạy nhiều instance. Đảm bảo key chứa audience/key ID/nonce và TTL đủ dài.

### Bài tập 6 — Key rotation và authorization

Cấp secret k2 và k3 cho cùng principal trong cửa sổ rotation; chuyển client sang k3. Kiểm tra việc tự sửa `X-Key-Id` từ k2 thành k3 mà giữ tag cũ phải bị từ chối. Sau đó ký một request hợp lệ đến tenant khác và chứng minh authorization vẫn từ chối.

## 21. Checklist triển khai tính HMAC

- [ ] HMAC algorithm, key policy, protocol version, tag length và signature encoding được **server cố định/kiểm soát**.
- [ ] Shared secret được sinh bằng CSPRNG, lưu/phân phối qua secret management và tách theo principal/audience khi hợp lý.
- [ ] Secret được decode đúng dạng được cấp (raw bytes/hex/Base64); không nhầm chuỗi hiển thị với byte key.
- [ ] Canonical request được định nghĩa theo byte: UTF-8, LF, thứ tự field, không có LF cuối nếu contract quy định.
- [ ] Method, canonical path/query, signed headers và raw body digest bao phủ các trường có ý nghĩa bảo mật.
- [ ] Không dùng `SHA256(secret + message)` hoặc một hash khác làm MAC tự chế.
- [ ] Java dùng `Mac.getInstance("HmacSHA256")` và `SecretKeySpec` đúng thuật toán; không chia sẻ instance `Mac` stateful giữa thread.
- [ ] Tính SHA-256 body digest từ đúng raw bytes được gửi/nhận; không serialize lại JSON sau khi ký.
- [ ] `X-Signature` là tag output, không nằm trong chính canonical text; key ID, timestamp và nonce được ký.
- [ ] Signature full 32 byte HMAC-SHA256 được encode Base64URL no padding 43 ký tự theo V1.
- [ ] Verifier parse header duy nhất, validate format/length, decode và so sánh full tag bằng `MessageDigest.isEqual`.
- [ ] Key registry chọn đúng secret/algorithm/audience và kiểm tra trạng thái/rotation/revocation.
- [ ] Timestamp window và nonce được ký; nonce store chia sẻ và atomic, TTL bao phủ cửa sổ chấp nhận.
- [ ] Không dùng chữ ký hợp lệ làm bằng chứng request chưa replay; idempotency nghiệp vụ được bảo vệ riêng.
- [ ] Gateway, proxy, router và verifier cùng hiểu URI/headers/body; không tin `X-Forwarded-*` do Internet tự khai.
- [ ] HTTPS/TLS bảo vệ request; log không làm lộ secret hoặc full signed request nhạy cảm.
- [ ] Authorization dựa trên principal/action/resource/tenant từ nguồn server tin cậy.
- [ ] Có RFC 4231 known-answer tests, golden canonical bytes, negative/tampering tests và e2e proxy tests.

## 22. Câu hỏi tự kiểm tra

1. **HMAC nhận String hay byte[]?** Thuật toán nhận **byte** của secret và thông điệp; String cần được encode theo contract.
2. **HMAC-SHA256 tag đầy đủ dài bao nhiêu?** 32 byte, tương ứng 64 hex hoặc 43 Base64URL không padding.
3. **Vì sao không dùng SHA-256(body) làm chữ ký?** Vì digest không có khóa; bất kỳ ai có body có thể tự tính lại.
4. **`Mac.doFinal(...)` trả về gì?** Mảng byte HMAC tag, chưa được encode thành hex/Base64.
5. **HMAC có mã hóa hay giữ bí mật JSON body không?** Không. Cần HTTPS/TLS cho confidentiality trên đường truyền, hoặc encryption riêng nếu có yêu cầu.
6. **Tại sao HMAC hai phía khác dù cùng secret?** Thường canonical bytes khác do URI, header, body, UTF-8 hoặc newline.
7. **Vì sao không được dùng `System.lineSeparator()`?** Vì canonical contract phải cố định byte line ending trên mọi hệ điều hành.
8. **Body JSON có thứ tự field khác nhưng dữ liệu giống nhau có MAC giống không?** Không chắc; nếu ký raw bytes thì đổi byte làm digest khác.
9. **Có thể gửi secret trong `X-Key-Id` không?** Không. Key ID chỉ là định danh tra secret trong registry.
10. **Vì sao nên ký timestamp và nonce?** Để kẻ tấn công không sửa metadata chống replay mà giữ tag cũ.
11. **HMAC hợp lệ có ngăn replay nguyên request không?** Không. Cần cửa sổ timestamp và replay store nguyên tử.
12. **Server chọn thuật toán theo độ dài chữ ký được không?** Không nên; chọn theo protocol version và key record, rồi mới validate tag length.
13. **Có nên tự thử nhiều cách normalize URI đến khi MAC khớp không?** Không. Phải có một canonicalization contract xác định.
14. **Đổi key ID lúc rotation mà giữ signature cũ có hợp lệ không?** Không. Cần dùng secret mới và ký lại đầy đủ canonical request.
15. **HMAC đúng có cho phép principal A xóa dữ liệu tenant B không?** Không. Authorization phải kiểm tra quyền theo action/resource/tenant.
16. **Vì sao kiểm thử KAT riêng với HTTP integration test?** KAT kiểm tra primitive HMAC; integration test kiểm tra canonicalization, key registry, proxy, freshness và quyền.

## 23. Tài liệu tham khảo

- **RFC 2104 — HMAC: Keyed-Hashing for Message Authentication.** Nền tảng của thuật toán HMAC.
- **RFC 4231 — Identifiers and Test Vectors for HMAC-SHA-224/256/384/512.** Known-answer tests của thuật toán.
- **NIST FIPS 198-1 — The Keyed-Hash Message Authentication Code (HMAC).** Đặc tả HMAC.
- **NIST FIPS 180-4 — Secure Hash Standard (SHS).** Cơ sở SHA-256, SHA-384 và SHA-512.
- **RFC 3986 — Uniform Resource Identifier (URI): Generic Syntax.** Nền tảng về path/query và percent-encoding.
- **Java SE 17 — `javax.crypto.Mac`, `javax.crypto.spec.SecretKeySpec`, `java.security.MessageDigest`, `java.util.Base64`, `java.util.HexFormat`.** API Java tính MAC, so sánh byte và encode tag.

**Kết luận:** **Tính HMAC trong HTTP request signing là phép toán có khóa trên một dãy canonical bytes được xác định chính xác.** Chỉ khi client và verifier thống nhất secret bytes, thuật toán, method/URI/header/body, UTF-8, delimiters và encoding signature thì HMAC mới có ý nghĩa như một cơ chế xác thực request. Ngay cả khi tag khớp, hệ thống vẫn phải kiểm tra timestamp/nonce để chống replay, key lifecycle/audience, gateway routing và authorization trước khi thực thi nghiệp vụ.
