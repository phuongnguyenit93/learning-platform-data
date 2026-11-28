# Mac.update trong Java: cập nhật HMAC theo từng phần dữ liệu

Trong Java, `javax.crypto.Mac` là API thuộc hệ sinh thái **Java Cryptography Architecture (JCA/JCE)** để tính **Message Authentication Code (MAC)** bằng một khóa bí mật. Với thuật toán `HmacSHA256`, đối tượng `Mac` dùng SHA-256 bên trong HMAC, nhưng đầu ra là một mã xác thực **có khóa**, khác với SHA-256 không khóa của `MessageDigest`.

Phương thức **`Mac.update(...)`** đưa thêm byte vào trạng thái HMAC đang tính. Nó cho phép xử lý một thông điệp thành nhiều phần mà không cần ghép các phần thành một mảng byte lớn. Đây là kỹ năng thiết yếu khi xây dựng **HMAC request authentication**: client và verifier cần tính cùng một chữ ký từ **canonical request** gồm method, URI, các header được ký và digest của body theo hợp đồng đã thống nhất.

Bài thuộc chương **JCA Mac API** của module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Trọng tâm là cách dùng `Mac.update` đúng vòng đời và đúng byte; đồng thời đặt nó trong bài toán xác thực request, chống replay bằng timestamp/nonce, quản lý key rotation, xử lý proxy/gateway và phân biệt xác thực với phân quyền.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích sự khác nhau giữa `Mac.init`, `Mac.update`, `Mac.doFinal` và `Mac.reset`.
2. Sử dụng bốn kiểu đầu vào của `update`: một byte, cả mảng byte, một vùng của mảng và `ByteBuffer`.
3. Chứng minh các lần `update` liên tiếp tương đương một lần cấp cùng dãy byte đã nối, nếu thứ tự và ranh giới byte không thay đổi.
4. Viết Java 17 tạo HMAC-SHA256 cho canonical request theo từng dòng, so sánh chữ ký và kiểm tra bằng test vector công khai.
5. Tránh các lỗi về trạng thái, charset, delimiter, body bytes, thread safety và gateway làm sai lệch chữ ký.

## 2. Vòng đời đối tượng Mac

~~~mermaid
flowchart TD
    A["Mac.getInstance(\"HmacSHA256\")"] --> B["Mac.init(secretKey)"]
    B --> C["Mac.update(chunk 1)"]
    C --> D["Mac.update(chunk 2, ...)"]
    D --> E["Mac.doFinal(): MAC bytes"]
    E --> F{"Ký thông điệp tiếp?"}
    F -->|Có, cùng key| C
    F -->|Đổi key| B
    F -->|Không| G["Kết thúc sử dụng"]
~~~

~~~java
Mac mac = Mac.getInstance("HmacSHA256");
mac.init(new SecretKeySpec(secretBytes, "HmacSHA256"));
mac.update(part1);
mac.update(part2);
byte[] tag = mac.doFinal();
~~~

Các điểm cần nhớ:

| API | Ý nghĩa | Hệ quả lên trạng thái |
| --- | --- | --- |
| `Mac.getInstance("HmacSHA256")` | Chọn thuật toán/provider phù hợp | Tạo đối tượng **chưa được khởi tạo khóa**. |
| `mac.init(secretKey)` | Cấu hình khóa HMAC; có thể khởi tạo lại với khóa khác | Chuẩn bị trạng thái đầu cho một thông điệp. |
| `mac.update(bytes)` | Nạp thêm byte vào thông điệp đang được tính HMAC | **Chưa** trả chữ ký; có thể gọi nhiều lần. |
| `mac.doFinal()` | Hoàn tất HMAC trên toàn bộ byte đã nạp | Trả MAC bytes, sau đó đối tượng được reset về trạng thái sau lần `init` gần nhất. |
| `mac.reset()` | Bỏ phần dữ liệu đang nạp, trở về trạng thái sau `init` | **Giữ key** đã cấu hình, không xóa key khỏi bộ nhớ. |
| `mac.getMacLength()` | Độ dài kết quả MAC tính theo byte | Với HmacSHA256 thông dụng là **32 byte**. |

**Ví dụ quan trọng:** nếu `mac.update(A)`, `mac.update(B)`, rồi `mac.doFinal()`, kết quả là HMAC của **A nối B**. Nếu bạn gọi `doFinal()` ngay sau A, sau đó tiếp tục `update(B)` và `doFinal()`, đó là **hai thông điệp độc lập**, không còn là HMAC(A || B). `doFinal` cũng không đồng nghĩa mã hóa; đầu ra có thể biểu diễn thành Base64 hoặc hex để truyền qua header.

Thực tế, nên tạo **một Mac riêng cho mỗi phép ký** hoặc có cơ chế quản lý instance rõ ràng. `Mac` là đối tượng có trạng thái; không giả định cùng một instance an toàn khi nhiều thread cùng gọi `update`. Chia sẻ instance giữa các request đồng thời dễ làm byte của nhiều request bị trộn lẫn, tạo chữ ký sai hoặc lỗi khó tái hiện.

## 3. Bốn overload của Mac.update

Java cung cấp những cách cấp byte sau:

| Phương thức | Dữ liệu được đưa vào HMAC | Khi nào dùng? |
| --- | --- | --- |
| `update(byte input)` | Đúng một byte | Thêm delimiter chính xác như LF (0x0A). |
| `update(byte[] input)` | Toàn bộ byte của mảng | Message nhỏ đã có sẵn trong byte array. |
| `update(byte[] input, int offset, int len)` | `len` byte bắt đầu từ chỉ số `offset` | Dùng một chunk thực nhận từ buffer, tránh ký cả vùng đệm còn trống. |
| `update(ByteBuffer input)` | Các byte từ `position()` đến trước `limit()` | Dữ liệu trong NIO/direct buffer; position được tiến đến limit. |

### 3.1. Nạp một byte

~~~java
mac.update("POST".getBytes(StandardCharsets.UTF_8));
mac.update((byte) '\n');  // Chính xác một byte LF
mac.update("/v1/payments".getBytes(StandardCharsets.UTF_8));
~~~

Điều này tạo dãy byte tương đương với `UTF8("POST\n/v1/payments")`. Nếu hợp đồng ký yêu cầu LF, đừng thay bằng `System.lineSeparator()`: trên Windows, ký tự xuống dòng thông thường là CRLF (hai byte 0D 0A), khác LF (0A). Một byte khác cũng đủ làm chữ ký khác.

### 3.2. Nạp cả mảng

~~~java
byte[] canonicalBytes =
    "POST\n/v1/payments".getBytes(StandardCharsets.UTF_8);
mac.update(canonicalBytes);
byte[] tag = mac.doFinal();
~~~

Đừng gọi `String.getBytes()` mà không chỉ rõ charset. Hợp đồng ký HTTP phải công bố cách chuyển text thành byte, thường là UTF-8. Những chuỗi nhìn giống nhau có thể mang byte khác nếu normalize Unicode hoặc encode khác nhau ở mỗi phía.

### 3.3. Nạp một phần mảng: offset và len

~~~java
byte[] buffer = "XXPOSTYY".getBytes(StandardCharsets.UTF_8);
mac.update(buffer, 2, 4); // Chỉ nạp bốn byte "POST"
~~~

**`offset` là vị trí bắt đầu, `len` là số lượng byte** chứ không phải chỉ số kết thúc. Ví dụ `update(buffer, 2, 4)` chọn các chỉ số 2, 3, 4, 5. Với buffer tái sử dụng để đọc stream, phải đưa vào **số byte thực sự vừa đọc**, tránh vô tình ký cả byte còn sót của lần đọc trước.

~~~java
byte[] chunk = new byte[8192];
int n;
while ((n = inputStream.read(chunk)) != -1) {
    if (n > 0) {
        mac.update(chunk, 0, n);
    }
}
byte[] tag = mac.doFinal();
~~~

Đoạn đọc stream mô tả một giao thức **HMAC trực tiếp toàn bộ stream bytes**. Trong hợp đồng ký HTTP mà body được biểu diễn bằng `SHA-256(body)` trong canonical request, bước đọc body nên sử dụng **`MessageDigest.update(chunk, 0, n)`**, kết thúc bằng `digest()` rồi đưa **chuỗi body hash** vào `Mac.update` cùng các trường canonical. Không vô tình vừa HMAC raw body vừa HMAC body hash nếu hợp đồng không yêu cầu cả hai.

### 3.4. Nạp ByteBuffer

~~~java
byte[] data = "POST\n/v1/payments"
    .getBytes(StandardCharsets.UTF_8);
ByteBuffer buffer = ByteBuffer.wrap(data);

mac.update(buffer);
// Sau update: buffer.position() == buffer.limit().
byte[] tag = mac.doFinal();
~~~

`Mac.update(ByteBuffer)` lấy **các byte còn lại** (`remaining()`), bắt đầu tại `position()` hiện tại và kết thúc trước `limit()`. Nó làm thay đổi **position** của buffer, vì vậy không thể giả định một lần `update(buffer)` thứ hai sẽ nạp lại cùng dữ liệu; nếu position đã bằng limit thì không còn byte nào.

Nếu một thành phần khác vẫn cần đọc từ vị trí cũ, dùng một view với position độc lập:

~~~java
ByteBuffer source = ByteBuffer.wrap(data); // Vị trí ban đầu bằng 0.
ByteBuffer forMac = source.asReadOnlyBuffer();
mac.update(forMac); // Tiêu thụ position của forMac.
// Position của source vẫn bằng 0, không bị lần update này thay đổi.
~~~

`ByteBuffer` có thể là heap buffer hoặc direct buffer. Mối quan tâm chính là **position/limit**, chứ không phải nơi lưu bộ nhớ. Khi buffer vừa được ghi vào, thường phải `flip()` trước khi chuyển từ chế độ ghi sang đọc. Không gọi `update` trên buffer đang ở position sai rồi kết luận HMAC không ổn định.

## 4. Tính chất phân mảnh: một thông điệp, nhiều lần update

Giả sử byte thông điệp là `m = A || B || C`:

~~~text
mac.init(key)
mac.update(A)
mac.update(B)
mac.update(C)
tag1 = mac.doFinal()

mac.init(key)
mac.update(A || B || C)
tag2 = mac.doFinal()

tag1 == tag2
~~~

Tính chất này rất hữu ích: canonical request có thể được ký theo từng dòng; body có thể được băm theo từng chunk; không cần sao chép toàn bộ dữ liệu vào một buffer lớn chỉ để gọi API. Nhưng **`update` không tự ghi nhớ ranh giới các phần**. Ví dụ, các trường:

~~~text
["ab", "c"]  -> các byte abc
["a", "bc"]  -> các byte abc
~~~

Nếu chỉ nạp liên tiếp byte mỗi trường, hai danh sách trên có **cùng MAC** vì byte message giống nhau. Muốn ràng buộc cấu trúc, hợp đồng ký phải định nghĩa delimiter không mơ hồ (và cách escape/validate nó), hoặc cấu trúc có prefix độ dài/encoding duy nhất.

Với canonical request dùng LF giữa các dòng, cách thực thi an toàn là:

~~~java
for (int i = 0; i < fields.length; i++) {
    if (i != 0) {
        mac.update((byte) '\n');
    }
    mac.update(fields[i].getBytes(StandardCharsets.UTF_8));
}
byte[] tag = mac.doFinal();
~~~

Khi đó `String.join("\n", fields).getBytes(UTF_8)` và chuỗi các lời gọi `update` ở trên tạo ra **cùng một dãy byte** nếu tất cả trường hợp lệ và không chứa LF nội bộ. Cần kiểm tra và từ chối CR/LF trong các giá trị header được ký để tránh nhập nhằng ranh giới.

## 5. Ví dụ HMAC HTTP request: cập nhật từng dòng canonical

Xét request gửi tới dịch vụ thanh toán:

~~~http
POST /v1/payments?currency=VND&dryRun=true HTTP/1.1
Host: api.example.test
Content-Type: application/json

{"orderId":"ord-123","amount":50000}
~~~

Ví dụ dưới đây dùng **hợp đồng ký HMAC-V1 riêng cho mục đích học**, không mặc định tương thích với hợp đồng của một nhà cung cấp API thực tế. Hai bên bắt buộc thống nhất:

| Field canonical | Quy tắc trong ví dụ | Mục đích |
| --- | --- | --- |
| HMAC-V1 | Marker phiên bản đầu tiên | Tránh nhầm định dạng khi hệ thống nâng cấp contract. |
| Method | POST, chữ hoa ASCII | Không cho đổi method mà giữ chữ ký. |
| Request target | Raw path + raw query theo đúng request truyền đi | Ràng buộc URI, thứ tự query, tham số nghiệp vụ. |
| audience | payments-api | Ràng buộc nơi chấp nhận request, ngăn replay xuyên dịch vụ khi verifier kiểm tra đúng audience. |
| x-client-id | partner-42 | Nhận diện client để tìm khóa và áp dụng policy. |
| x-key-id | ID phiên bản khóa được cấp | Verifier chọn đúng secret và kiểm tra key rotation. |
| x-timestamp | Unix epoch seconds | Giới hạn tuổi thọ request ở server. |
| x-nonce | 16 byte random biểu diễn hex | Phát hiện replay nếu verifier ghi nhận nonce. |
| content-type | application/json | Ràng buộc cách diễn giải body. |
| x-content-sha256 | Lowercase hex của SHA-256 trên body bytes | Ràng buộc nội dung body vào HMAC. |

Canonical request là một chuỗi các dòng **LF (0A)**, **không** có LF cuối:

~~~text
HMAC-V1
POST
/v1/payments?currency=VND&dryRun=true
audience:payments-api
x-client-id:partner-42
x-key-id:<key-id>
x-timestamp:<epoch-seconds>
x-nonce:<32-lowercase-hex-characters>
content-type:application/json
x-content-sha256:<64-lowercase-hex-characters>
~~~

Chữ ký gửi qua `X-Signature` chứa **Base64 của HMAC-SHA256 trên UTF-8 của canonical request**. Không có `X-Signature` trong dữ liệu được ký vì tự ký chính chữ ký sẽ tạo vòng phụ thuộc. Secret được cấp riêng bằng kênh bảo mật và **không** gửi trong HTTP request.

### 5.1. Ví dụ đầy đủ với Java 17

Đây là chương trình tự chứa tạo request đã ký, minh họa `Mac.update(byte)` và `Mac.update(byte[])`. Chương trình **không gửi request thật**; nó yêu cầu hai biến môi trường: `HMAC_SHARED_SECRET_B64` (Base64 của secret ngẫu nhiên từ secret manager, nên có ít nhất 32 byte) và `HMAC_KEY_ID` (key ID mà server đã cấp).

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

public final class MacUpdateRequestExample {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String CONTENT_TYPE = "application/json";

    public static void main(String[] args) throws Exception {
        URI uri = URI.create(
            "https://api.example.test/v1/payments?currency=VND&dryRun=true"
        );
        byte[] body = "{\"orderId\":\"ord-123\",\"amount\":50000}"
            .getBytes(StandardCharsets.UTF_8);

        String clientId = "partner-42";
        String keyId = requiredEnv("HMAC_KEY_ID");
        byte[] secret = Base64.getDecoder().decode(
            requiredEnv("HMAC_SHARED_SECRET_B64")
        );
        if (secret.length < 32) {
            throw new IllegalArgumentException(
                "Secret nên là ít nhất 32 byte ngẫu nhiên"
            );
        }

        String timestamp = Long.toString(Instant.now().getEpochSecond());
        String nonce = randomNonce();
        String bodyHash = sha256Hex(body);

        String[] fields = {
            "HMAC-V1",
            "POST",
            rawRequestTarget(uri),
            "audience:payments-api",
            "x-client-id:" + clientId,
            "x-key-id:" + keyId,
            "x-timestamp:" + timestamp,
            "x-nonce:" + nonce,
            "content-type:" + CONTENT_TYPE,
            "x-content-sha256:" + bodyHash
        };

        byte[] tag = signFields(secret, fields);
        String signature = Base64.getEncoder().encodeToString(tag);

        HttpRequest request = HttpRequest.newBuilder(uri)
            .header("Content-Type", CONTENT_TYPE)
            .header("X-Client-Id", clientId)
            .header("X-Key-Id", keyId)
            .header("X-Timestamp", timestamp)
            .header("X-Nonce", nonce)
            .header("X-Content-SHA256", bodyHash)
            .header("X-Signature", signature)
            .POST(HttpRequest.BodyPublishers.ofByteArray(body))
            .build();

        System.out.println("Đã tạo request ký HMAC: " + request.method());
        // Không log secret hoặc chữ ký trong ứng dụng thật.
        // Gửi request bằng HttpClient khi đã có server test phù hợp.
    }

    static byte[] signFields(byte[] secret, String[] fields)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));

        for (int i = 0; i < fields.length; i++) {
            // Hợp đồng này không cho phép CR/LF nằm trong một field.
            if (fields[i].indexOf('\r') >= 0 ||
                fields[i].indexOf('\n') >= 0) {
                throw new IllegalArgumentException(
                    "Canonical field chứa CR/LF"
                );
            }
            if (i > 0) {
                mac.update((byte) '\n');  // Delimiter là byte LF duy nhất.
            }
            mac.update(fields[i].getBytes(StandardCharsets.UTF_8));
        }
        return mac.doFinal(); // Trả 32 byte HMAC-SHA256.
    }

    static String sha256Hex(byte[] body)
            throws GeneralSecurityException {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(body);
        return HexFormat.of().formatHex(digest);
    }

    static String rawRequestTarget(URI uri) {
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

    static String randomNonce() {
        byte[] bytes = new byte[16]; // 128 bit
        RANDOM.nextBytes(bytes);
        return HexFormat.of().formatHex(bytes);
    }

    static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu biến môi trường: " + key);
        }
        return value;
    }
}
~~~

Lý do dùng `Mac.update` trong hàm `signFields`: thuật toán nhận đúng dãy byte canonical mà không cần tạo một `String` dài duy nhất. Việc ký theo từng phần không làm thay đổi HMAC so với gọi `mac.doFinal(String.join("\n", fields).getBytes(UTF_8))`, miễn là mỗi trường và dấu phân tách đều giống nhau.

**Giới hạn của ví dụ:** Chương trình xây từ một URL cố định và các giá trị đầu vào đơn giản. Trong production, client phải có cách đảm bảo **raw request target thực tế** ở HTTP stack/gateway trùng target đã ký. Header nhiều giá trị, whitespace, Unicode, Content-Encoding, authority, domain và mọi trường nghiệp vụ cần được định nghĩa chính xác trong contract. Verifier không nên tin `fields` do client khai báo sẵn; nó phải **tự xây canonical** từ request nhận tại trust boundary và kiểm tra audience của dịch vụ đang chạy.

## 6. Kiểm chứng Mac.update với test vector

Một cách kiểm tra API độc lập với HTTP là dùng test vector **HMAC-SHA256 của RFC 4231, test case 1**:

- Key: byte `0x0b` lặp lại **20 lần**.
- Message: chuỗi ASCII `Hi There`.
- HMAC-SHA256 mong đợi: `b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7`.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class MacUpdateVector {
    public static void main(String[] args) throws Exception {
        byte[] key = new byte[20];
        Arrays.fill(key, (byte) 0x0b);
        String expected =
            "b0344c61d8db38535ca8afceaf0bf12b" +
            "881dc200c9833da726e9376c2e32cff7";

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        mac.update("Hi ".getBytes(StandardCharsets.US_ASCII));
        mac.update("There".getBytes(StandardCharsets.US_ASCII));
        String actual = HexFormat.of().formatHex(mac.doFinal());

        if (!expected.equals(actual)) {
            throw new AssertionError("HMAC test vector không khớp");
        }
        System.out.println("PASS: HMAC-SHA256 qua hai lần update");
    }
}
~~~

Test này chứng minh cách phân mảnh `Hi ` + `There` không làm đổi byte message. Để kiểm tra thêm `update(byte[], offset, len)` hoặc `update(ByteBuffer)`, hãy nạp **cùng chính xác** tám byte ASCII `Hi There` theo các overload khác nhau và so sánh tag. Không nhầm test vector công khai với secret dùng trong môi trường thật.

## 7. Những vấn đề hay gặp khi ký HTTP request

### 7.1. Ký byte rồi lại gửi byte khác

Hai JSON sau có thể tương đương theo cách xử lý dữ liệu nhưng có **SHA-256 khác**:

~~~json
{"amount":50000,"currency":"VND"}
~~~

~~~json
{
  "currency": "VND",
  "amount": 50000
}
~~~

HMAC không so sánh “ý nghĩa JSON”, nó xác thực **byte của canonical request**. Nếu contract dùng `SHA-256(bodyBytes)`, client cần **serialize body một lần**, dùng cùng byte array hoặc cùng stream đã được bảo toàn để hash và gửi. Băm JSON compact rồi gửi bản có whitespace khác là nguyên nhân phổ biến của lỗi chữ ký.

Với body lớn không thể giữ trong RAM, có thể tính SHA-256 theo chunk bằng `MessageDigest.update`, rồi lưu/spool dữ liệu một cách an toàn để gửi **chính cùng byte đó**. Nếu stream không thể đọc lại, không thể giả định sau khi hash xong HTTP client sẽ tái phát được cùng nội dung; cần thiết kế body publisher/luồng dữ liệu có thể replay hoặc giao thức ký trailer/streaming được hai bên hỗ trợ.

### 7.2. Canonicalization khác nhau

| Sai lệch | Điều gì xảy ra? | Cách khắc phục |
| --- | --- | --- |
| Dùng CRLF ở một phía, LF ở phía kia | Byte canonical và HMAC khác nhau | Dùng LF (0A) cố định theo contract, không lấy newline mặc định hệ điều hành. |
| Có LF cuối ở một phía, không có ở phía kia | HMAC mismatch | Định nghĩa rõ có/không có final delimiter. |
| Client UTF-8, server charset khác | Dãy byte khác khi có ký tự ngoài ASCII | Encode UTF-8 rõ ràng ở cả hai phía. |
| Ký URL sau decode ở client, raw URL tại server | `%2F` và `/` có thể không tương đương | Thống nhất raw path/raw query và điểm capture qua HTTP stack. |
| Gateway rewrite path hoặc sắp xếp query | Server dùng target khác client đã ký | Xác minh trước rewrite tại ingress đáng tin hoặc bảo toàn metadata gốc qua kênh xác thực. |
| Header có khoảng trắng/case khác hoặc bị lặp | Hai phía dựng canonical không giống nhau | Quy định chính xác signed headers, normalization và từ chối input mơ hồ. |
| Proxy nén/giải nén body | Body bytes cần băm bị thay đổi | Thống nhất hash trên encoded hay decoded body ở điểm nào. |
| Sử dụng `X-Forwarded-Host` từ nguồn bất kỳ | Audience và route có thể bị giả mạo | Audience phải được ràng buộc với dịch vụ/verifier, không tin header từ proxy không đáng tin. |

Đối với **proxy không tin cậy**, chữ ký phải bị từ chối nếu một trường **đã ký** bị thay đổi. Một giải pháp bỏ path/header khỏi canonical chỉ để qua gateway có thể khiến kẻ tấn công thay đổi chính trường đó mà chữ ký vẫn hợp lệ. Hãy thiết kế trust boundary và hợp đồng ký có thể bảo toàn biểu diễn gốc, không nới lỏng phạm vi bảo vệ.

### 7.3. Những sai lầm về state và API

| Sai lầm | Vì sao sai? | Hành động đúng |
| --- | --- | --- |
| `update` trước `init` | Đối tượng chưa có secret | Gọi `init` bằng key phù hợp trước khi nạp dữ liệu. |
| `doFinal` sau từng trường | Mỗi lời gọi kết thúc một thông điệp | Nạp **tất cả** phần của một canonical request rồi mới `doFinal` một lần. |
| Quên delimiter | Hai cách phân tách trường có thể cùng chuỗi byte | Dùng hợp đồng ký có phân tách/độ dài trường duy nhất. |
| Gọi `reset` ở giữa request | Bỏ toàn bộ phần dữ liệu đã nạp trước đó | Chỉ `reset` khi muốn cố ý bỏ thông điệp đang ký. |
| Tái sử dụng một `Mac` cho nhiều thread | Dữ liệu các request có thể bị trộn trạng thái | Một instance cho mỗi phép ký hoặc quản lý instance riêng từng thread. |
| Đọc stream vào buffer rồi `update(buffer)` cả 8192 byte | Ký byte chưa nhận và byte còn sót | Dùng `update(buffer, 0, bytesRead)`. |
| Dùng lại `ByteBuffer` sau khi `update` | Position đã tiến đến limit, lần sau có thể nạp 0 byte | Sử dụng `duplicate`/`asReadOnlyBuffer` hoặc quản lý position rõ ràng. |
| Dùng `MessageDigest` cho chữ ký “có khóa” bằng tự nối secret | Đây không phải HMAC được chuẩn hóa; có thể dính lỗi length extension | Dùng `Mac.getInstance("HmacSHA256")` và `SecretKeySpec`. |
| Coi Base64 của secret là raw key | Chọn sai bytes khóa giữa client và verifier | Giải mã Base64 thành byte secret trước khi `init`. |
| Log canonical, signature hoặc secret không kiểm soát | Có thể rò rỉ dữ liệu nhạy cảm và material hỗ trợ tấn công | Chỉ log mã lỗi, request ID và thông tin an toàn cần thiết. |

## 8. Bước xác minh chữ ký và chống replay ở server

`Mac.update` cũng được dùng tại verifier theo **cùng thuật toán** và **cùng hợp đồng**. Một trình tự tham khảo:

1. **Nhận dữ liệu tại trust boundary tin cậy:** từ request thực tế, lấy method, raw request target, signed headers và body bytes; kiểm tra định dạng, từ chối các trường trùng/mơ hồ, giới hạn kích thước body và số header.
2. **Chọn key:** tra secret bằng client ID + key ID đã cấp, kiểm tra key còn hiệu lực, được phép với endpoint/audience và chính sách rotation; không thử mọi key tùy ý cho đến khi có một chữ ký đúng.
3. **Kiểm tra timestamp:** parse epoch seconds và giới hạn cửa sổ chấp nhận, ví dụ ±300 giây theo chính sách riêng của hệ thống. Chênh lệch đồng hồ cần được giám sát; timestamp phải nằm trong canonical.
4. **Tính lại body hash:** từ đúng body representation được contract quy định; so sánh với digest do client gửi, bảo đảm digest đó cũng được HMAC ràng buộc.
5. **Dựng lại canonical và tạo HMAC:** gọi `Mac.init`, `Mac.update` theo đúng thứ tự trường và delimiter, sau đó `doFinal`. Verifier tự dựng dữ liệu, không tin canonical string do người ngoài tự khai báo.
6. **So sánh chữ ký:** Base64 decode `X-Signature`, kiểm tra độ dài và dùng phép so sánh byte có thời gian tương đối ổn định, ví dụ `MessageDigest.isEqual(expectedTag, suppliedTag)`. Không dùng so sánh chuỗi HMAC thông thường.
7. **Chống replay:** chỉ sau khi MAC hợp lệ, ghi nhận nonce đã ký bằng thao tác **insert-if-absent nguyên tử** trong store dùng chung giữa replica; từ chối nonce đã sử dụng và đặt TTL đủ bao phủ cửa sổ hợp lệ.
8. **Phân quyền và tác dụng phụ:** identity xác thực phải có quyền với method, route, tenant và tài nguyên cụ thể. Với thao tác thanh toán/tạo giao dịch, dùng **idempotency key** được bảo vệ trong hợp đồng ký và thực thi ở tầng nghiệp vụ để xử lý retry an toàn.

Pseudocode:

~~~java
byte[] expectedTag = signFields(secretForClientAndKeyId, fieldsFromRequest);
byte[] suppliedTag = Base64.getDecoder().decode(signatureHeader);

if (!MessageDigest.isEqual(expectedTag, suppliedTag)) {
    // Từ chối chữ ký sai; không thực hiện nghiệp vụ.
}
// Sau các kiểm tra hợp lệ khác: claim nonce nguyên tử,
// rồi authorize và xử lý idempotency.
~~~

Một chữ ký HMAC **không tự chống replay**: proxy có thể gửi lại nguyên văn request hợp lệ trong thời gian cho phép, vẫn có tag đúng. Timestamp và nonce phải **được ký** và **server thực thi chính sách**. Một retry có nonce mới có thể vượt chống replay nhưng vẫn gây giao dịch lặp, vì vậy idempotency cần được xử lý riêng.

**Xác thực khác phân quyền:** `Mac.update` góp phần tạo và kiểm tra HMAC chứng minh bên gọi dùng đúng secret và request đã ký không bị sửa. Điều đó không cho phép client thao tác mọi tenant, tài khoản hay tài nguyên. Backend vẫn kiểm tra quyền theo danh tính đã xác thực và chính sách nghiệp vụ.

## 9. Bài thực hành và ma trận kiểm thử

Tạo một lớp `HmacSigner` có phương thức `signFields(secret, fields)` như ví dụ, một hàm `verify` độc lập dựng lại canonical từ request, và các unit test dùng **key test**. Không sử dụng secret production; không ghi body nhạy cảm hoặc secret vào nhật ký.

| Ca kiểm thử | Đầu vào/thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Test vector chuẩn | Key 20 byte 0x0b, message `Hi There` | HMAC-SHA256 đúng hex của RFC 4231. |
| Phân mảnh | Một lần `update(allBytes)` và nhiều lần `update(chunks)` | Cùng tag nếu các byte nối lại đúng thứ tự. |
| Offset/len | Buffer `XXPOSTYY`, `update(buffer, 2, 4)` | Tương đương ký `POST`. |
| ByteBuffer | Buffer có position/limit xác định | Chỉ byte còn lại được ký, position tiến tới limit. |
| Delimiter | LF so với CRLF, có/không final LF | Tag khác; verifier chỉ chấp nhận contract. |
| Encoding | UTF-8 so với charset khác khi có Unicode | Phát hiện canonical byte khác nhau. |
| State | Gọi `doFinal` giữa hai chunk | Thấy tag của hai thông điệp, khác tag nối cả hai chunk. |
| Reset | `update(A)` rồi `reset()`, `update(B)` | Tag chỉ của B, với cùng key. |
| Body change | Đổi một byte JSON sau khi ký | Digest/HMAC không khớp, từ chối. |
| Method/URI change | Sửa POST thành DELETE hoặc sửa query | Chữ ký không khớp vì field được ký. |
| Key rotation | Key ID cũ, mới, đã thu hồi | Chọn đúng secret và ràng buộc hiệu lực/audience. |
| Replay | Gửi lại cùng timestamp/nonce; kiểm thử đồng thời hai replica | Nonce trùng bị từ chối, tối đa một claim thành công. |
| Proxy rewrite | Rewrite path, đổi content encoding hoặc header | Không được âm thầm xác minh trên biểu diễn khác. |
| Authentication vs authorization | HMAC hợp lệ nhưng client thiếu quyền | Xác thực thành công, phân quyền từ chối. |

### Câu hỏi tự đánh giá

1. Vì sao hai lần `Mac.update` với A và B tương đương một lần với A || B, nhưng không tương đương hai lần `doFinal`?
2. `Mac.update(bytes, offset, len)` nhận độ dài hay chỉ số kết thúc? Sai lầm này ảnh hưởng chữ ký thế nào?
3. `Mac.update(ByteBuffer)` làm gì với position của buffer? Cần thao tác ra sao để giữ vị trí gốc?
4. Khi hợp đồng ký body hash, tại sao nên dùng `MessageDigest.update` để hash body stream rồi mới dùng `Mac.update` cho canonical request?
5. Nếu proxy thay URI sau khi client ký nhưng body vẫn nguyên, chữ ký sẽ có phát hiện thay đổi không? Điều kiện nào khiến câu trả lời đúng?
6. Sau khi chữ ký đúng, vì sao server vẫn phải kiểm tra nonce và quyền truy cập tài nguyên?

**Ghi nhớ:** `Mac.update` **chỉ thêm byte vào thông điệp HMAC hiện tại**, không tạo chữ ký cho từng phần. Chữ ký cuối cùng từ `doFinal` phụ thuộc vào **toàn bộ dãy byte, thứ tự và delimiter** đã được cập nhật dưới đúng secret. Khi dùng cho HTTP request authentication, an toàn còn phụ thuộc hợp đồng canonical request, body representation, vị trí xác minh, timestamp/nonce, key rotation và phân quyền.
