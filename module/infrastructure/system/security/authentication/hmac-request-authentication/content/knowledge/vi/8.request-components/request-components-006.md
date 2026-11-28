# Body trong HMAC request authentication: bảo vệ chính xác nội dung HTTP request

**HTTP request body** là phần nội dung mà client gửi cùng request, chẳng hạn JSON tạo đơn hàng, dữ liệu form, tệp tải lên hoặc một chuỗi byte nhị phân. Khi xây dựng xác thực HTTP request bằng **HMAC (Hash-based Message Authentication Code)**, chỉ ký method, URI và header là chưa đủ nếu body chứa những giá trị có thể thay đổi kết quả nghiệp vụ. Kẻ tấn công có khả năng sửa body có thể đổi số tiền, người nhận hoặc quyền được yêu cầu mà không cần thay đổi URL.

Bài **Body** thuộc chương **Request components**, nằm trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Module này thiết kế xác thực HTTP request bằng **shared secret** và **canonical request** gồm method, URI, header và/hoặc body theo hợp đồng ký. Bài tập trung vào cách biến **đúng các byte body** thành dữ liệu được HMAC bảo vệ, cách kiểm tra tại server, tác động của proxy/gateway, timestamp/nonce, key rotation và khác biệt giữa xác thực và phân quyền.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt body bytes, nội dung đã parse, HTTP header, content encoding và transfer framing.
2. Tạo **SHA-256 digest của body bytes** và ràng buộc digest đó vào canonical request được HMAC-SHA256 ký bằng shared secret.
3. Giải thích vì sao body hash không khóa **không phải** bằng chứng xác thực client.
4. Viết client Java 17 tạo body một lần, hash và ký request, rồi mô phỏng verifier kiểm tra trên body bytes đã nhận.
5. Thiết kế cách xử lý body rỗng, JSON, multipart, dữ liệu lớn, compression, retry và proxy rewrite theo một hợp đồng rõ ràng.
6. Kiểm thử thay đổi body, timestamp/nonce, key rotation, đường đi qua gateway và phân quyền sau xác thực.

## 2. HTTP body là dữ liệu gì?

Ví dụ request tạo thanh toán:

~~~http
POST /v1/payments?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json

{"orderId":"ord-123","amount":50000}
~~~

Body ở đây là các byte UTF-8 tương ứng với chuỗi JSON:

~~~text
{"orderId":"ord-123","amount":50000}
~~~

Phân biệt các lớp dữ liệu:

| Thành phần | Ví dụ | Có phải body bytes cần băm? |
| --- | --- | --- |
| HTTP method | `POST` | Không; cần ký **riêng** trong canonical request. |
| Request target | `/v1/payments?currency=VND` | Không; cần ký **riêng** nếu nó quyết định xử lý. |
| Header | `Content-Type: application/json` | Không; là metadata nên cần quy định header nào được ký. |
| HTTP message content | Byte của JSON | **Có**, theo hợp đồng minh họa của bài. |
| HTTP/1.1 chunk framing | Kích thước chunk, CRLF phân cách chunk | **Không** nếu hợp đồng ký trên message content sau khi lớp HTTP loại bỏ transfer framing. |
| HTTP/2 DATA frame boundaries | Ranh giới frame trong HTTP/2 | **Không**; ranh giới frame là chi tiết vận chuyển. |
| Content coding | Body được gzip nếu `Content-Encoding: gzip` | Phải quy định rõ ký **encoded bytes** hay **decoded bytes**. |

Trong bài này, hợp đồng mẫu chỉ chấp nhận **body không nén**; client **không gửi** `Content-Encoding` và canonical có trường logic `content-encoding:identity` (nghĩa là không áp dụng content coding). `identity` trong canonical là giá trị **do hợp đồng tự định nghĩa**, không bắt buộc phải gửi như một HTTP header. Verifier từ chối request có Content-Encoding khác quy định.

Phần được hash là **HTTP message content bytes**, tức byte body sau khi HTTP stack xử lý transfer framing, nhưng **trước bước parse JSON** và trước bất kỳ bước biến đổi nội dung nào khác. Tự động giải nén, thay charset hoặc serialize lại JSON trước khi tính digest sẽ khiến hai bên không còn băm cùng dữ liệu. Với API thực sự cho phép gzip, phải bổ sung một chính sách riêng về encoded/decoded content và vị trí xác minh.

Không phải mọi request đều có body. GET thường không có body theo thiết kế API, còn POST có thể mang body rỗng. **Không có body** cần được định nghĩa thống nhất thành **0 byte** khi tính SHA-256, thay vì bỏ trường digest một cách tùy ý.

## 3. Điều gì xảy ra khi body không được ký?

Hãy xem một request chuyển tiền:

~~~http
POST /v1/transfers HTTP/1.1
Content-Type: application/json

{"from":"A","to":"B","amount":100000}
~~~

Nếu HMAC chỉ ký:

~~~text
POST
/v1/transfers
x-client-id:partner-42
~~~

thì kẻ tấn công tại proxy có thể đổi `"amount":100000` thành `"amount":900000`, hoặc thay tài khoản nhận. Khi method, URI và client ID vẫn giữ nguyên, **canonical không đổi** và chữ ký cũ vẫn hợp lệ. Đây là lỗi thiết kế **phạm vi được ký**, không phải điểm yếu của HMAC-SHA256.

Ngược lại, nếu client chỉ gửi header:

~~~http
X-Content-SHA256: {sha256-cua-body}
~~~

mà **không đưa giá trị đó vào HMAC**, kẻ tấn công có thể sửa body **và tính lại hash**. SHA-256 không dùng khóa; ai thấy body đều có thể tính digest của body mới.

Hợp đồng an toàn cần **ràng buộc body với chữ ký có khóa**. Hai cách phổ biến là:

1. Đưa chính body bytes vào dữ liệu HMAC theo một format định nghĩa rõ ràng.
2. Tính `SHA-256(bodyBytes)`, đưa body digest vào canonical request, sau đó HMAC toàn bộ canonical.

Bài này dùng **cách 2**, vì phù hợp với request có body lớn và giúp canonical có kích thước tương đối gọn. Cách này chỉ an toàn nếu cả digest **và các thành phần quan trọng khác** đều nằm trong phạm vi HMAC; verifier bắt buộc tính digest từ **body bytes thực nhận**.

## 4. Hợp đồng ký minh họa: body digest được HMAC bảo vệ

Xét dịch vụ thanh toán chỉ nhận JSON UTF-8 **không nén**, có quy định:

| Trường | Quy tắc của hợp đồng minh họa | Lý do |
| --- | --- | --- |
| Contract version | `HMAC-BODY-V1` | Ràng buộc phiên bản canonicalization. |
| Method | `POST`, chữ hoa ASCII | Ngăn chuyển sang method khác. |
| Request target | Raw path + raw query đúng request thực gửi | Ràng buộc route, resource và query. |
| Audience | `payments-api` lấy từ policy dịch vụ | Ngăn dùng request ở sai dịch vụ. |
| Client ID | `partner-42` | Xác định bên được cấp secret. |
| Key ID | ID phiên bản secret | Chọn đúng khóa cho xác minh/rotation. |
| Timestamp | Unix epoch seconds dạng số thập phân | Giới hạn cửa sổ replay ở server. |
| Nonce | 16 byte ngẫu nhiên, biểu diễn 32 ký tự hex chữ thường | Giúp phát hiện request đã phát lại. |
| Content-Type | **Chính xác** `application/json` | Ràng buộc cách backend diễn giải body. |
| Content-Encoding logic | `identity` khi HTTP request không có Content-Encoding | Chặn nhập nhằng encoded/decoded body. |
| X-Content-SHA256 | 64 ký tự hex chữ thường của SHA-256 trên raw body bytes | Ràng buộc toàn bộ body vào HMAC. |

Canonical request được nối bằng **LF (byte 0x0A)** giữa các dòng, **không có LF cuối**; tất cả text trong canonical được mã hóa **UTF-8**:

~~~text
HMAC-BODY-V1
POST
/v1/payments?currency=VND
audience:payments-api
x-client-id:partner-42
x-key-id:<key-id>
x-timestamp:<unix-seconds>
x-nonce:<32-lowercase-hex-characters>
content-type:application/json
content-encoding:identity
x-content-sha256:<64-lowercase-hex-characters>
~~~

Các placeholder nằm trong dấu `<...>` mô tả **vị trí giá trị**, không phải ký tự được gửi nguyên văn.

Phép tính:

~~~text
bodyHashHex    = lowercaseHex(SHA256(bodyBytes))
canonicalBytes = UTF8(JoinWithLF(canonicalFields))
fullTagBytes   = HMAC_SHA256(sharedSecretBytes, canonicalBytes)
signatureB64   = Base64_standard_with_padding(fullTagBytes)
~~~

**Quy tắc chữ ký:** HMAC-SHA256 trả 32 byte tag; header `X-Signature` chứa Base64 chuẩn **44 ký tự có padding theo quy tắc Base64**, không phải Base64URL. `X-Signature` **không** nằm trong canonical vì nếu ký chính chữ ký sẽ tạo vòng tự tham chiếu. Client không gửi secret; `X-Key-Id` chỉ là định danh để server tìm đúng khóa.

**Quy tắc header:** những header được ký phải có một giá trị duy nhất, không chứa CR/LF, không có khoảng trắng thừa ngoài contract. Request có duplicate `X-Content-SHA256`, `Content-Type` hoặc `X-Signature` phải bị từ chối theo chính sách parse chặt chẽ, thay vì để proxy và backend chọn giá trị khác nhau.

**Quy tắc URI:** nếu có query, dùng raw query đúng thứ tự và percent-encoding của request target. Không tự chuyển `%2F` thành `/`, đổi `+` thành khoảng trắng hay sắp xếp tham số. Verifier và router phải sử dụng thông tin nhất quán tại trust boundary.

Đây là **hợp đồng ví dụ cho mục tiêu học tập**. Khi tích hợp API khác, phải thực hiện chính xác hợp đồng của API đó; không tự thay thứ tự dòng, giá trị charset, encoding hoặc kiểu hash.

## 5. Vì sao băm body bytes thay vì đối tượng JSON?

Hàm băm nhận **byte**, không nhận khái niệm “hai object JSON giống nhau về ý nghĩa”:

~~~json
{"currency":"VND","amount":50000}
~~~

~~~json
{
  "amount": 50000,
  "currency": "VND"
}
~~~

Hai JSON có thể biểu diễn cùng cặp field sau parse nhưng **byte khác nhau**, vì thứ tự key và whitespace khác. SHA-256 vì vậy cũng khác. Một số nguồn sai khác:

| Thay đổi | Body digest có thể thay đổi? | Cách xử lý |
| --- | --- | --- |
| Đổi khoảng trắng, xuống dòng hoặc thứ tự key JSON | **Có** | Serialize **một lần** thành byte array rồi dùng chính array đó để hash và gửi. |
| Đổi UTF-8 thành UTF-16 | **Có** | Chốt charset hợp đồng; hash byte, không dựa vào charset mặc định của JVM. |
| Unicode có hai cách chuẩn hóa khác nhau | **Có** | Nếu cần normalize, phải thực hiện theo **cùng hợp đồng** trước bước serialize. |
| JSON số `50000` thành `50000.0` | **Có** | Không tự động tái định dạng số hoặc deserialize-reserialize sau ký. |
| Server đọc body rồi đổi thành object JSON khác, sau đó serialize lại | **Có** | Tính digest trên byte đã nhận **trước** bước parse/biến đổi. |
| Body nén gzip | **Có**, nếu so với bytes chưa nén | Chặn hoặc quy định chính xác content coding và điểm xác minh. |
| HTTP/1.1 chunk size/HTTP/2 DATA frames thay đổi | **Không**, nếu message content bytes không đổi | Loại bỏ framing trong HTTP stack rồi hash message content bytes. |

Chú ý trường hợp **multipart/form-data**: boundary trong `Content-Type` và các delimiter trong body là một phần của biểu diễn request. Hai lần tạo cùng các trường form có thể sinh boundary hoặc byte khác nhau. Với streaming upload, không thể tự cho rằng dữ liệu phát lại sẽ giống lần serialize đầu. Nếu API dùng multipart, phải ký cả Content-Type có boundary thực tế và đúng content bytes.

### Body rỗng, body “null” và chuỗi rỗng khác nhau

~~~text
bodyBytes = byte[0]                 // 0 byte
bodyBytes = UTF8("null")            // 4 byte
bodyBytes = UTF8("\"\"")            // 2 byte: hai ký tự dấu nháy
bodyBytes = UTF8("{}")              // 2 byte: hai ký tự ngoặc nhọn
~~~

Digest SHA-256 của **0 byte** là:

~~~text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

Nếu hợp đồng bắt buộc header hash dù body rỗng, hãy gửi giá trị hash **của 0 byte**. Không dùng chuỗi rỗng, `null` hoặc một giá trị giả định “không hash” để thay thế digest mà server đang chờ. Nếu backend quy định POST phải có JSON object thì body 0 byte vẫn có thể bị từ chối ở lớp **validation nghiệp vụ**, dù HMAC tính đúng.

## 6. Java 17: client tạo body một lần và ký bằng HMAC-SHA256

Chương trình dưới đây tự tạo một **HTTP request mẫu để kiểm thử**, không gửi traffic ra mạng. Key được đọc từ biến môi trường `HMAC_SHARED_SECRET_B64` chứa Base64 của secret thật do hệ thống quản lý khóa cấp, và `HMAC_KEY_ID` là ID của key đó. Trong hệ thống thực, **client và verifier phải được cấp cùng secret qua kênh an toàn**; không tự tạo hai secret độc lập.

Ví dụ có một hàm ký và một hàm mô phỏng xác minh, giúp thấy request nguyên vẹn được chấp nhận còn body đã sửa bị từ chối. **Replay store, key lookup và authorization thuộc server thực tế** và được trình bày ở mục sau.

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacBodyExample {
    private static final SecureRandom RNG = new SecureRandom();
    private static final String CONTENT_TYPE = "application/json";

    record SignedHeaders(
        String clientId,
        String keyId,
        String timestamp,
        String nonce,
        String bodyHash,
        String signature
    ) {}

    public static void main(String[] args) throws Exception {
        URI uri = URI.create(
            "https://api.example.test/v1/payments?currency=VND"
        );

        // Serialize một lần: đây là byte sẽ hash và đưa vào HTTP publisher.
        byte[] body = "{\"orderId\":\"ord-123\",\"amount\":50000}"
            .getBytes(StandardCharsets.UTF_8);

        String keyId = requiredEnv("HMAC_KEY_ID");
        byte[] secret = Base64.getDecoder().decode(
            requiredEnv("HMAC_SHARED_SECRET_B64")
        );
        if (secret.length < 32) {
            throw new IllegalArgumentException(
                "Ví dụ yêu cầu secret >= 32 byte ngẫu nhiên"
            );
        }
        String clientId = "partner-42";
        String timestamp = Long.toString(Instant.now().getEpochSecond());
        String nonce = newNonce();
        String bodyHash = sha256Hex(body);

        String canonical = canonical(
            "POST", rawTarget(uri), clientId, keyId,
            timestamp, nonce, bodyHash
        );
        String signature = Base64.getEncoder().encodeToString(
            hmacSha256(secret, canonical.getBytes(StandardCharsets.UTF_8))
        );
        SignedHeaders headers = new SignedHeaders(
            clientId, keyId, timestamp, nonce, bodyHash, signature
        );

        HttpRequest request = HttpRequest.newBuilder(uri)
            .header("Content-Type", CONTENT_TYPE)
            // Content-Encoding không xuất hiện: contract yêu cầu identity.
            .header("X-Client-Id", headers.clientId())
            .header("X-Key-Id", headers.keyId())
            .header("X-Timestamp", headers.timestamp())
            .header("X-Nonce", headers.nonce())
            .header("X-Content-SHA256", headers.bodyHash())
            .header("X-Signature", headers.signature())
            .POST(HttpRequest.BodyPublishers.ofByteArray(body))
            .build();

        // Ví dụ đơn giản kiểm tra chữ ký trên các giá trị giả lập server nhận.
        if (!verify(secret, "POST", rawTarget(uri), headers, body)) {
            throw new AssertionError("Body nguyên vẹn phải verify được");
        }
        byte[] tampered = body.clone();
        tampered[tampered.length - 2] ^= 1; // Thay đúng một byte.
        if (verify(secret, "POST", rawTarget(uri), headers, tampered)) {
            throw new AssertionError("Body đã sửa phải bị từ chối");
        }
        System.out.println("PASS: " + request.method()
            + ", body toàn vẹn, từ chối body bị sửa");
    }

    static String canonical(String method, String target, String clientId,
            String keyId, String timestamp, String nonce, String bodyHash) {
        // Ứng dụng thật cần validate mọi field trước khi gọi hàm này;
        // nhất là CR/LF, header trùng, method/URI và các giá trị client gửi.
        for (String field : new String[] {
                method, target, clientId, keyId, timestamp, nonce, bodyHash
        }) {
            if (field == null ||
                field.indexOf('\r') >= 0 || field.indexOf('\n') >= 0) {
                throw new IllegalArgumentException("Canonical field lỗi");
            }
        }
        return String.join("\n",
            "HMAC-BODY-V1",
            method,
            target,
            "audience:payments-api",
            "x-client-id:" + clientId,
            "x-key-id:" + keyId,
            "x-timestamp:" + timestamp,
            "x-nonce:" + nonce,
            "content-type:" + CONTENT_TYPE,
            "content-encoding:identity",
            "x-content-sha256:" + bodyHash
        );
    }

    static String rawTarget(URI uri) {
        if (uri.getRawFragment() != null) {
            throw new IllegalArgumentException("URI không được có fragment");
        }
        String path = uri.getRawPath();
        if (path == null || path.isEmpty()) {
            path = "/";
        }
        String query = uri.getRawQuery();
        return path + (query == null ? "" : "?" + query);
    }

    static String sha256Hex(byte[] data) throws GeneralSecurityException {
        byte[] hash = MessageDigest.getInstance("SHA-256").digest(data);
        return HexFormat.of().formatHex(hash);
    }

    static byte[] hmacSha256(byte[] key, byte[] message)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        return mac.doFinal(message);
    }

    static String newNonce() {
        byte[] random = new byte[16];
        RNG.nextBytes(random);
        return HexFormat.of().formatHex(random);
    }

    // Chỉ mô phỏng phần kiểm tra body hash/HMAC; chưa làm nonce,
    // timestamp policy, key lookup, HTTP parser hoặc authorization.
    static boolean verify(byte[] secret, String method, String target,
            SignedHeaders headers, byte[] receivedBody)
            throws GeneralSecurityException {
        if (headers.bodyHash() == null ||
            !headers.bodyHash().matches("[0-9a-f]{64}") ||
            headers.signature() == null) {
            return false;
        }

        byte[] computedDigest = MessageDigest
            .getInstance("SHA-256").digest(receivedBody);
        byte[] claimedDigest = HexFormat.of().parseHex(headers.bodyHash());
        if (!MessageDigest.isEqual(computedDigest, claimedDigest)) {
            return false;
        }

        final byte[] suppliedTag;
        try {
            suppliedTag = Base64.getDecoder().decode(headers.signature());
        } catch (IllegalArgumentException badBase64) {
            return false;
        }
        if (suppliedTag.length != 32 ||
            !Base64.getEncoder().encodeToString(suppliedTag)
                .equals(headers.signature())) {
            return false; // Full tag, Base64 chuẩn có padding.
        }

        String expectedCanonical = canonical(
            method, target, headers.clientId(), headers.keyId(),
            headers.timestamp(), headers.nonce(),
            HexFormat.of().formatHex(computedDigest)
        );
        byte[] expectedTag = hmacSha256(
            secret, expectedCanonical.getBytes(StandardCharsets.UTF_8)
        );
        return MessageDigest.isEqual(expectedTag, suppliedTag);
    }

    static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu biến môi trường: " + name);
        }
        return value;
    }
}
~~~

**Giải thích:**

- `byte[] body` được tạo **một lần** rồi dùng cho `MessageDigest.getInstance("SHA-256").digest(body)` và `BodyPublishers.ofByteArray(body)`. Đây là cách tránh body thay đổi giữa lúc ký và lúc gửi.
- `sha256Hex` trả digest SHA-256 thành **64 ký tự hex chữ thường**; client ký chính dòng `x-content-sha256:...` bên trong canonical.
- `hmacSha256` dùng **javax.crypto.Mac** và `SecretKeySpec`, không tự ghép secret vào body rồi gọi SHA-256.
- `verify` tính hash từ body bytes phía nhận, kiểm tra body hash client khai báo, tự tạo canonical và so sánh HMAC bằng `MessageDigest.isEqual`. Nó từ chối chữ ký không đúng **32 byte** hoặc Base64 không đúng biểu diễn đã chọn.
- `canonical` dùng LF và không có LF cuối; nếu client/server khác dấu xuống dòng, thứ tự field, raw URI hoặc Content-Type, chữ ký sẽ lệch.
- Secret phải được cấp an toàn với entropy đủ mạnh; **độ dài Base64 của secret không phản ánh trực tiếp độ dài tag**. Không log secret, body nhạy cảm hoặc toàn bộ canonical trong hệ thống thực.

Ví dụ đơn giản chỉ mô phỏng verifier trên dữ liệu do chương trình chủ động truyền vào. Verifier HTTP production **không** lấy `SignedHeaders` làm bằng chứng đã chuẩn hóa: nó còn phải tự đọc request ở trust boundary, từ chối header trùng/không hợp lệ, kiểm tra Content-Encoding thực sự vắng mặt, kiểm tra method/URI, chọn secret theo key ID và áp dụng chính sách replay/phân quyền.

## 7. Body lớn và streaming: băm thế nào?

Với JSON nhỏ, body byte array là phương án dễ kiểm chứng. Với tệp lớn, có thể băm theo chunk mà không cần giữ toàn bộ nội dung trong bộ nhớ:

~~~java
import java.io.InputStream;
import java.security.MessageDigest;
import java.util.HexFormat;

static String sha256Stream(InputStream in) throws Exception {
    MessageDigest sha = MessageDigest.getInstance("SHA-256");
    byte[] buffer = new byte[8192];
    int bytesRead;
    while ((bytesRead = in.read(buffer)) != -1) {
        if (bytesRead > 0) {
            sha.update(buffer, 0, bytesRead);
        }
    }
    return HexFormat.of().formatHex(sha.digest());
}
~~~

Đoạn này tính cùng SHA-256 như băm một lần toàn bộ byte stream, **nếu thứ tự và byte đúng như nhau**. Lưu ý `bytesRead` là **số byte thực đọc**, không phải chiều dài của buffer. Dùng `sha.update(buffer)` khi chunk cuối chưa đầy có thể đưa cả dữ liệu dư vào hash.

### Vấn đề “băm trước khi gửi”

Nếu HTTP yêu cầu header `X-Signature` trước khi client gửi body, client thường phải **biết body digest trước khi gửi**. Khi body là stream **chỉ đọc một lần**, không thể vừa đọc hết để băm rồi mặc nhiên gửi lại cùng stream: nó đã bị tiêu thụ.

Giải pháp tùy mô hình:

- Với body nhỏ/vừa, serialize vào byte array trước khi ký và dùng publisher phát lại đúng mảng byte đó.
- Với body lớn, ghi dữ liệu vào file tạm bảo vệ an toàn hoặc nguồn có thể đọc lại, tính digest rồi tạo publisher đọc **đúng cùng byte** từ nguồn ổn định; cân nhắc thay đổi nội dung đồng thời, thời hạn lưu và giới hạn dung lượng.
- Nếu không thể biết trước digest, dùng **giao thức streaming/chunk signing riêng** được client và verifier thống nhất, không tự ý thay một hợp đồng ký toàn-body bằng partial hash.

Server cũng cần đọc body đúng **một representation** theo hợp đồng. Middleware logging, JSON parser hoặc filter tiêu thụ stream trước verifier có thể khiến verifier chỉ còn 0 byte. Nếu muốn đọc lại, cần cơ chế lưu trữ/buffering hoặc streaming digest được tích hợp đúng vào HTTP stack, có giới hạn kích thước và bảo vệ dữ liệu nhạy cảm.

**Bảo vệ tài nguyên:** giới hạn body bytes, thời gian đọc, số lượng phần multipart, kích thước đã giải nén và request concurrency. HMAC không ngăn đối thủ gửi body rất lớn để tiêu tốn CPU/RAM trước khi xác thực; không giải nén dữ liệu không tin cậy không giới hạn.

## 8. Proxy, gateway và các phép biến đổi body

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Proxy không tin cậy
    participant G as Gateway đáng tin
    participant V as Verifier
    participant B as Backend
    C->>P: Method + raw URI + headers + body bytes + HMAC
    P->>G: Forward, có thể sửa request
    G->>V: Dữ liệu tại trust boundary
    V->>V: Hash body và verify canonical/HMAC
    alt Hợp lệ
        V->>B: Forward request và danh tính đã xác minh
        B->>B: Authorization + idempotency
    else Hash/HMAC sai hoặc replay
        V-->>C: Từ chối
    end
~~~

Khi đi qua proxy, nhiều biến đổi có thể xảy ra:

| Trường hợp | Body bytes verifier nhìn thấy | Cách xử lý |
| --- | --- | --- |
| Proxy chỉ chuyển tiếp request mà không sửa message content | Giống client đã ký | HMAC có thể xác minh nếu URI/header cũng đúng. |
| HTTP/1.1 chunked được giải khung, HTTP/2 DATA frame đổi ranh giới | **Message content bytes có thể vẫn y hệt** | Hash **message content**, không đưa chunk/frame framing vào digest. |
| Proxy thêm whitespace hoặc serialize lại JSON | Khác byte ban đầu | Nếu không được contract cho phép, từ chối; không tự tái ký bằng secret của client. |
| Proxy nén/giải nén gzip | Encoded/decoded bytes khác nhau | Hợp đồng bài này **từ chối content coding khác identity**; hợp đồng khác phải xác định biểu diễn được ký. |
| Gateway đổi `Content-Type` hoặc charset | Body có thể không đổi nhưng ý nghĩa parse đổi | Ký header quyết định cách diễn giải và xác minh giá trị cuối. |
| Proxy thay body nhưng giữ X-Content-SHA256 và signature | Body hash sai | Verifier tính lại digest từ body nhận và từ chối. |
| Proxy thay cả body và X-Content-SHA256 | Hash client khai báo có thể trùng body mới nhưng HMAC sai | Verifier không biết shared secret sẽ không thể sinh tag mới hợp lệ. |
| Gateway kiểm tra HMAC **sau khi** sửa body | Dữ liệu được verify khác client đã ký | Chuyển verify về điểm đáng tin trước transform, hoặc thiết kế mapping/protocol mới có bảo vệ. |
| Proxy đặt `X-Verified: true` / `X-Original-URI` | Có thể giả mạo metadata | Không tin header ngoài boundary; xác thực gateway→backend và chặn đường bypass. |

**Ranh giới tin cậy:** nếu một gateway do hệ thống vận hành thực hiện verify rồi cần chuẩn hóa body trước khi backend xử lý, phải bảo đảm backend xử lý **cùng ngữ nghĩa đã được chấp nhận** và không để request hoặc identity bị thay thế sau verify. Nếu backend tự verify, gateway phải chuyển cho nó đúng body representation và request target mà client ký, hoặc có cách lưu giữ metadata gốc qua kênh đã xác thực.

Một proxy bên ngoài có thể replay nguyên văn request hợp lệ dù không tạo được chữ ký cho body đã sửa. Vì thế **ký body không đủ**; hệ thống vẫn cần kiểm tra timestamp/nonce và thực thi idempotency.

## 9. Luồng xác minh server: body trước nghiệp vụ

Một trình tự gợi ý cho verifier đáng tin:

1. **Giới hạn request trước:** reject framing mơ hồ, duplicate header an ninh, request quá lớn và Content-Encoding không được phép; xác định nơi lấy method/raw URI/header/body bytes.
2. **Chọn secret:** tra cặp `clientId + keyId` trong key store, kiểm tra key active, đúng audience/route và thuật toán cho phép (ví dụ HmacSHA256 full 32-byte tag). Không dùng key ID để đọc file tùy ý hoặc thử vô hạn mọi secret.
3. **Kiểm tra timestamp và format nonce:** ví dụ chỉ chấp nhận lệch tối đa ±300 giây theo policy, nonce là 16 byte ngẫu nhiên biểu diễn hex. Đây không phải cấu hình bắt buộc của HMAC.
4. **Hash body thực nhận:** dùng SHA-256 trên raw message content bytes theo contract; kiểm tra hex chữ thường có đúng 64 ký tự; so sánh với `X-Content-SHA256`.
5. **Tự dựng canonical request:** dùng method, raw target, header đã ký và digest được tính lại; không tin canonical string do client gửi hoặc X-Original-URI không xác thực.
6. **Tính HMAC:** dùng secret đã chọn, UTF-8 của canonical; Base64 decode chữ ký, kiểm tra full tag 32 byte, so sánh byte bằng `MessageDigest.isEqual`.
7. **Claim nonce nguyên tử:** chỉ sau khi HMAC hợp lệ, ghi nhận nonce trong store dùng chung giữa replica bằng insert-if-absent để chống replay trước khi thực hiện side effect.
8. **Authorize:** kiểm tra client identity, tenant, action, resource và idempotency key đã được bảo vệ trong chữ ký nếu endpoint có thao tác không thể lặp.
9. **Xử lý body:** mới parse/validate JSON và thực hiện nghiệp vụ trên body representation đã được xác minh, hoặc bảo đảm phép chuyển đổi sau verify không làm lệch ý nghĩa cho phép.

**Nonce store** phải có TTL đủ để mọi bản sao request còn nằm trong cửa sổ được chấp nhận đều bị nhận diện là đã sử dụng. Với chính sách chấp nhận timestamp ±`S` giây, một request có timestamp gần `now+S` có thể còn hợp lệ gần `2S` giây kể từ khi lần đầu được chấp nhận; đừng chỉ lưu nonce vài giây. Một thiết kế có thể tính hạn lưu ít nhất đến `timestamp+S` và thêm biên độ an toàn, sử dụng clock đáng tin và thao tác nguyên tử.

**Idempotency khác nonce:** client gửi lại giao dịch với **nonce mới** và HMAC mới vẫn là request hợp lệ. Nếu lần trước đã xử lý thành công nhưng response bị mất, server phải dựa vào idempotency key và trạng thái nghiệp vụ để tránh ghi tiền hai lần. Nếu sử dụng idempotency key, đưa nó vào phần được ký để proxy không thay nó.

**Authentication khác authorization:** HMAC đúng chứng minh request được tạo bởi bên có khả năng sử dụng secret và các trường đã ký không bị sửa. Nó **không** tự cấp quyền thay tài khoản khác, bỏ giới hạn số tiền hay đọc tài nguyên tenant khác. Server phải kiểm tra quyền **sau** xác thực và trước tác dụng phụ.

## 10. Bài thực hành và ma trận kiểm thử

Tạo một endpoint test nhận POST JSON, lấy body bytes tại verifier đáng tin, tính lại SHA-256 rồi HMAC theo hợp đồng ở mục 4. Chạy client thử các trường hợp bên dưới. Dùng secret **test** được tạo an toàn; không đưa secret thật, body chứa dữ liệu riêng tư hoặc canonical đầy đủ vào log.

| Ca thử | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Body JSON nguyên vẹn | Gửi đúng byte đã ký | Body hash và HMAC khớp; request đi tiếp tới bước nonce/quyền. |
| Body bị sửa một byte | Đổi ký tự amount sau ký | Bị từ chối vì digest/HMAC không khớp. |
| Body + hash cùng bị sửa | Thay body và tự tính lại X-Content-SHA256 | Vẫn bị từ chối HMAC vì không có secret để ký canonical mới. |
| JSON tương đương nhưng byte khác | Đổi whitespace hoặc thứ tự key sau ký | Digest khác, từ chối nếu contract ký raw bytes. |
| Body rỗng | Gửi 0 byte với hash `e3b0c442...` | Digest của 0 byte đúng; nghiệp vụ có thể từ chối vì thiếu JSON. |
| Body là `null` hoặc `{}` | Gửi chuỗi byte thực tế | Có digest riêng, không đồng nhất với body rỗng. |
| Content-Type bị sửa | Thay `application/json` bằng giá trị khác | HMAC sai hoặc reject theo contract. |
| Content-Encoding khác identity | Thêm `Content-Encoding: gzip` | Từ chối theo hợp đồng của bài. |
| Thay HTTP transfer framing | Thay chunk size hoặc số HTTP/2 frames nhưng giữ message content bytes | Digest phải không đổi nếu HTTP stack xuất cùng message content. |
| Dữ liệu lớn | Hash stream theo `MessageDigest.update(buffer, 0, n)` | Digest giống hash toàn bộ byte; không băm byte dư trong buffer. |
| Stream không đọc lại | Hash stream rồi cố gửi từ stream đã tiêu thụ | Phát hiện lỗi; dùng nguồn repeatable/spool hoặc giao thức streaming phù hợp. |
| Proxy sửa query hoặc path | Body không đổi, request target bị thay | Bị từ chối vì method/URI nằm trong canonical. |
| Header trùng | Gửi hai `Content-Type` hoặc `X-Content-SHA256` | Từ chối request mơ hồ trước xác minh. |
| Key rotation | Dùng key active, key overlap hợp lệ, key đã thu hồi | Chọn đúng secret theo key ID; reject key đã thu hồi. |
| Replay tuần tự | Gửi lại nguyên request và nonce | Lần tiếp theo bị từ chối dù body/HMAC đúng. |
| Replay đồng thời | Hai replica nhận cùng nonce | Chỉ một lần claim nonce thành công. |
| Retry giao dịch | Gửi body giống, nonce mới nhưng cùng idempotency key | Hệ thống xử lý nghiệp vụ theo chính sách idempotency; không ghi giao dịch trùng. |
| Client thiếu quyền | HMAC hợp lệ nhưng thao tác tài nguyên tenant khác | Authentication PASS, authorization DENY. |

### Câu hỏi tự kiểm tra

1. Vì sao gửi SHA-256(body) trong header **không đủ** để xác thực client nếu hash đó không nằm trong canonical request được HMAC ký?
2. Hai JSON parse thành object giống nhau nhưng khác whitespace có cùng digest không? Cần làm gì để client/server băm cùng byte?
3. Phân biệt HTTP/1.1 `Transfer-Encoding: chunked` với `Content-Encoding: gzip` khi xác định body bytes được ký.
4. Nếu body lớn chỉ có thể đọc một lần nhưng signature phải nằm trong header trước body, client có những lựa chọn thiết kế nào?
5. Proxy thay body nhưng không biết shared secret có thể làm gì, và điều gì vẫn nằm ngoài khả năng bảo vệ của HMAC?
6. Tại sao nonce và idempotency key đều cần thiết cho một API thanh toán có thể retry?
7. Sau khi hash/HMAC đúng, vì sao backend vẫn phải kiểm tra tenant, action và resource?

## 11. Checklist triển khai ký body

- [ ] Có hợp đồng ký xác định **body representation**, charset, Content-Type, Content-Encoding và điểm tính digest.
- [ ] Client serialize body **một lần**; tính hash và gửi đúng cùng byte, hoặc dùng nguồn stream có thể đọc lại một cách ổn định.
- [ ] Body hash dùng SHA-256 đúng raw bytes; body rỗng có digest của 0 byte; không xem hash không khóa là chữ ký.
- [ ] Đưa body hash vào canonical HMAC cùng method, raw URI, header có ý nghĩa bảo mật, audience và metadata replay.
- [ ] Canonical có thứ tự field, LF, UTF-8 và quy tắc percent-encoding/header duplication thống nhất; verifier tự dựng lại từ request thực nhận.
- [ ] Từ chối Content-Encoding/framing mơ hồ, body quá lớn và biến đổi không được contract cho phép; kiểm thử proxy/gateway và HTTP/1.1↔HTTP/2.
- [ ] Dùng `Mac.getInstance("HmacSHA256")` với shared secret được cấp an toàn; Base64 tag và kiểm tra độ dài/encoding nhất quán.
- [ ] Key ID gắn với secret, thuật toán, audience, trạng thái hiệu lực và key rotation; không chấp nhận key bị thu hồi.
- [ ] Timestamp và nonce nằm trong dữ liệu được ký; verifier dùng nonce store nguyên tử và TTL phù hợp chống replay.
- [ ] Retry nghiệp vụ có idempotency key được ký; sau xác thực vẫn có phân quyền theo tenant/tài nguyên.
- [ ] Không log secret, chữ ký, body nhạy cảm; có timeout, rate limit và giới hạn kích thước body để giảm nguy cơ DoS.

**Ghi nhớ:** Trong HMAC request authentication, **body an toàn khi verifier xác minh chính những byte mà client đã ký**. SHA-256 của body giúp ràng buộc nội dung, nhưng chỉ **HMAC trên canonical request chứa digest đó** mới cung cấp tính xác thực dựa trên shared secret. Đừng để parser, serializer, proxy hoặc gateway âm thầm đổi representation; replay protection, key rotation và authorization vẫn là các lớp kiểm soát độc lập.
