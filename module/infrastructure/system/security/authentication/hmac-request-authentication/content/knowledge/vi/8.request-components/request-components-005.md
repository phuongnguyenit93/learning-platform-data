# Headers

## 1. Vai trò của HTTP headers trong HMAC request authentication

Một HTTP request gồm **phương thức**, **URI**, **headers** và có thể có **body**. Trong cơ chế xác thực bằng HMAC, client dùng **shared secret** để ký một biểu diễn thống nhất của những thành phần mà hai phía đã thỏa thuận, gọi là **canonical request**. Server dựng lại chính biểu diễn đó rồi so sánh HMAC để phát hiện thay đổi và xác thực bên nắm giữ secret.

Headers đặc biệt quan trọng vì chúng có thể mang cả **tham số bảo mật** lẫn **thông tin điều khiển cách xử lý request**. Ví dụ:

```http
POST /v1/payments?merchantId=m-42 HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: client-42
X-Key-Id: key-2026-11
X-Timestamp: 1795856400
X-Nonce: Xo0hNWXh3NgFhNz71xtsqQ
X-Signature: <base64-hmac-sha256>

{"orderId":"O-42","amount":250000,"currency":"VND"}
```

Giá trị trong dấu `<...>` là **placeholder**; timestamp và nonce là dữ liệu minh họa. Trên thực tế, sender phải dùng timestamp hiện tại và nonce mới cho mỗi lần ký.

Trong mô-đun **`SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`**, ta thiết kế xác thực HTTP request bằng HMAC với shared secret, canonical request gồm method, URI, header hoặc body theo hợp đồng ký, đồng thời xem xét chống replay bằng timestamp/nonce, key rotation, proxy/gateway và sự khác biệt giữa xác thực với phân quyền. Bài **Headers** thuộc chương **Request components** sẽ làm rõ **header nào phải được ký**, **cách biến header thành byte canonical**, và **cách tránh sai lệch giữa client–gateway–server**.

Một điểm cần giữ rõ từ đầu: **không phải cứ header có mặt trong HTTP request thì mặc nhiên được HMAC bảo vệ**. Nếu header ảnh hưởng đến cách hiểu hoặc thực thi nghiệp vụ nhưng bị loại khỏi hợp đồng ký, bên ngoài có thể sửa giá trị ấy mà không khiến HMAC thay đổi.

## 2. Phân loại headers theo trách nhiệm bảo mật

| Header hoặc nhóm header | Vai trò | Có nên nằm trong dữ liệu ký? |
| --- | --- | --- |
| `X-Client-Id` | Xác định client để tra cấu hình khóa | **Có** trong hợp đồng minh họa; còn phải ràng buộc với key tương ứng |
| `X-Key-Id` | Chọn phiên bản shared secret | **Có** để ràng buộc phiên bản khóa với request |
| `X-Timestamp` | Thời điểm ký, hỗ trợ giới hạn replay | **Có** nếu dùng để chống replay |
| `X-Nonce` | Giá trị mới cho một lần ký | **Có** nếu dùng để chống replay |
| `Content-Type` | Xác định cách server diễn giải body | **Có** khi ảnh hưởng cách parse/kiểm tra nội dung |
| `Idempotency-Key` | Nhận diện một ý định nghiệp vụ | **Có hoặc bảo vệ tương đương** khi ảnh hưởng hành động |
| `X-Merchant-Id`, `X-Tenant-Id` nếu có | Chọn tài nguyên/tenant | **Có** nếu được dùng để định tuyến hoặc phân quyền |
| `Host` / HTTP/2 `:authority` | Xác định authority/đích công khai | Bảo vệ khi có ý nghĩa đối với tenant/routing; cần hợp đồng xử lý proxy |
| `Content-Encoding` | Chỉ cách mã hóa nội dung body | Bảo vệ hoặc khóa chính sách; quan trọng khi body được nén |
| `X-Signature` | Mang HMAC tag đã tạo | **Không đưa trực tiếp vào chính thông điệp cần ký** vì tạo vòng phụ thuộc |
| `Connection`, `Transfer-Encoding`, `Via` | Framing hoặc thông tin theo từng chặng mạng | Thường không ký trực tiếp trong hợp đồng ứng dụng; vẫn phải kiểm tra tính hợp lệ tại HTTP stack |
| `X-Forwarded-For`, `X-Forwarded-Host` | Metadata có thể do proxy thiết lập | Không tin dữ liệu tự khai báo từ Internet; chỉ dùng theo ranh giới tin cậy đã xác định |
| `User-Agent`, `Accept-Encoding` | Thông tin client/thương lượng nội dung | Chỉ ký khi thực sự cần và có quy tắc ổn định |

Bảng này là **hướng thiết kế**, không phải chuẩn chung bắt mọi HMAC API phải dùng các tên header trên. Tên `X-*` chỉ để minh họa. Một giao thức thực tế có thể dùng `Authorization` hoặc một schema khác; quan trọng là **hai phía sử dụng cùng hợp đồng và cùng độ dài/encoding chữ ký**.

### 2.1. Header được ký và header không được ký

**Signed headers** là tập header có tên và giá trị đi vào canonical request. Header không nằm trong tập ấy có thể vẫn được server xử lý, nhưng sự thay đổi của nó **không làm HMAC sai**.

Ví dụ, nếu server chọn tenant bằng `X-Tenant-Id` mà client chỉ ký method, path, body, kẻ tấn công có thể đổi `X-Tenant-Id` trong request đã ký. Khi đó chữ ký vẫn hợp lệ, nhưng đối tượng chịu tác động có thể đã khác. Cách khắc phục là bảo vệ trường tenant bằng chữ ký hoặc xác định tenant chỉ từ **principal đã xác thực** và từ chối mọi mâu thuẫn.

Một header chưa ký cũng có thể bị sửa **hợp pháp** bởi proxy, chẳng hạn `Via`. Không nên ký mọi header “cho chắc”, vì những giá trị thay đổi theo chặng mạng thường làm request hợp lệ bị từ chối khi qua gateway. Cần phân loại dựa trên **mô hình đe dọa và đường đi của request**.

### 2.2. Header chứa signature có được ký chính nó không?

Giả sử client muốn đặt `X-Signature` vào canonical request nhưng chưa biết chữ ký là gì: chữ ký lại phụ thuộc vào canonical request. Đây là vòng phụ thuộc không có quy trình tạo rõ ràng.

Thực tế, hợp đồng ký thường **loại trừ chính header chứa signature** khỏi dữ liệu ký, nhưng có thể bảo vệ những tham số liên quan khác như `keyId`, phiên bản thuật toán, danh sách signed headers và timestamp. Server **không** tin một tên thuật toán hoặc độ dài tag do client tùy ý yêu cầu rồi hạ cấp kiểm tra chữ ký.

## 3. Vấn đề canonicalization: tên header và giá trị header

HTTP field names không phân biệt chữ hoa/chữ thường. Với nhiều header, giá trị có thể chứa khoảng trắng tùy chọn ở hai đầu; các framework có thể trình bày field theo cách khác nhau. Trong khi đó, HMAC tính trên **byte chính xác**. Do đó, client và verifier cần quy tắc canonicalization đủ chi tiết để tạo cùng kết quả.

### 3.1. Chuẩn hóa tên header

Hai dòng sau biểu diễn cùng tên field theo HTTP:

```http
Content-Type: application/json
content-type: application/json
```

Một lựa chọn phổ biến cho hợp đồng ký là chuyển **tên header về ASCII lowercase**:

```text
Content-Type       -> content-type
X-Client-Id        -> x-client-id
X-Key-Id           -> x-key-id
X-Timestamp        -> x-timestamp
X-Nonce            -> x-nonce
```

Tên header là HTTP token, không được chứa dấu cách, ký tự xuống dòng hoặc ký tự phân cách trái phép. **Chuẩn hóa tên** không đồng nghĩa với việc cũng được chuyển **giá trị** về chữ thường.

### 3.2. Chuẩn hóa giá trị header

`Content-Type: application/json` và `Content-Type: APPLICATION/JSON` có thể được phần mềm hiểu theo các quy tắc của media type, nhưng hai giá trị ấy có byte khác nhau. Một HMAC contract chỉ có thể chấp nhận chúng cùng chữ ký nếu đã **đặc tả chính xác** một bước chuẩn hóa giá trị tương ứng.

Các quyết định phải viết rõ:

- Có bỏ khoảng trắng `SP`, `HTAB` ở đầu/cuối giá trị không? Bỏ như thế nào?
- Có gộp nhiều dấu cách liên tiếp ở giữa giá trị không? Với header nào?
- Giá trị chứa dấu phẩy có phải một danh sách hay một chuỗi đơn? Có được sắp xếp không?
- Các giá trị nào phân biệt chữ hoa/thường? Có được đổi encoding Unicode không?
- Với nhiều dòng cùng tên field, xử lý như danh sách, từ chối hay chọn một giá trị?
- Header không xuất hiện được biểu diễn khác thế nào với header có giá trị rỗng?

**Quy tắc của bài này:** để hạn chế độ phức tạp, hợp đồng mẫu chỉ ký **năm header bắt buộc**, mỗi header **xuất hiện đúng một lần**, giá trị chỉ dùng ASCII có thể in, chỉ bỏ khoảng trắng ASCII `SP` ở đầu/cuối, **không gộp dấu cách bên trong**, từ chối `CR`, `LF`, `HTAB` và các ký tự điều khiển. Đây là **quy tắc của ví dụ**, không nên áp dụng máy móc cho mọi giá trị HTTP header hợp lệ.

Chỉ chuẩn hóa các giá trị đã được hợp đồng chọn. Một thư viện tự động dùng `String.trim()`, `strip()` hoặc đổi giá trị về lowercase mà không theo hợp đồng có thể làm chữ ký không tương thích.

## 4. Duplicate headers, list values và nguy cơ diễn giải khác nhau

HTTP cho phép một số field có dạng danh sách, nên các bên trung gian đôi khi **gộp nhiều dòng cùng tên** thành một giá trị có dấu phẩy. Tuy vậy, **không phải header nào cũng được phép gộp**; với các header nhạy cảm như timestamp, nonce, key ID, signature và Content-Type, chấp nhận nhiều giá trị không có hợp đồng rõ có thể tạo mâu thuẫn giữa verifier, gateway và tầng nghiệp vụ.

Ví dụ request đáng ngờ:

```http
X-Client-Id: client-A
x-client-id: client-B
X-Timestamp: 1795856400
X-Timestamp: 1795856500
```

Nếu verifier chọn giá trị đầu còn ứng dụng nghiệp vụ hoặc gateway chọn giá trị cuối, các tầng sẽ **xác thực những dữ liệu khác nhau**. Không nên viết logic “lấy header đầu tiên” cho các trường nhạy cảm rồi hy vọng framework khác cũng làm giống thế.

Với hợp đồng minh họa:

1. Sau khi so tên theo ASCII lowercase, **mỗi signed header phải xuất hiện đúng một lần**.
2. Nếu một header bắt buộc thiếu, rỗng trái quy định hoặc có nhiều giá trị, **từ chối request**.
3. Nếu HTTP framework đã gộp các giá trị trước khi code kiểm tra, phải xác định xem nó còn cung cấp đủ thông tin để phát hiện duplicate không. Khi không thể phát hiện an toàn, cấu hình **gateway/HTTP server từ chối duplicate ở ranh giới đầu tiên**.
4. Không tự split dấu phẩy của một header được đặc tả là một giá trị đơn; với header dạng danh sách, cần **thuật toán riêng** nếu quyết định ký nó.

Ngoài duplicate, parser phải chặn **CR/LF injection** và dạng gấp dòng header cũ (*obs-fold*) nếu hợp đồng không hỗ trợ. Một dấu xuống dòng bất hợp pháp có thể khiến dãy canonical bị chèn thành “header mới”, phá ranh giới giữa các trường đã ký.

## 5. Hợp đồng ký minh họa với tập signed headers cố định

Xét API:

```http
POST /v1/payments?merchantId=m-42 HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: client-42
X-Key-Id: key-2026-11
X-Timestamp: 1795856400
X-Nonce: Xo0hNWXh3NgFhNz71xtsqQ
X-Signature: <base64-hmac-sha256>

{"orderId":"O-42","amount":250000,"currency":"VND"}
```

Đặt hợp đồng **`HMAC-SHA256-V1`** với các quy tắc:

1. Body là **byte JSON UTF-8 thực gửi**; `bodyHash` là hex chữ thường của `SHA-256(bodyBytes)`.
2. Method là `POST`. Path và query trong ví dụ là **raw public request target** đã thống nhất: `/v1/payments` và `merchantId=m-42`. Gateway không thay đổi chúng trước điểm xác minh. Với ký tự percent-encoded hoặc query phức tạp, giao thức cần thêm quy tắc rõ hơn.
3. Các header bắt buộc, xếp **theo thứ tự từ điển ASCII** của tên lowercase: `content-type`, `x-client-id`, `x-key-id`, `x-nonce`, `x-timestamp`.
4. Mỗi header đúng một giá trị; bỏ dấu cách SP đầu/cuối, không thay đổi khoảng trắng bên trong. `Content-Type` phải bằng chính xác `application/json`.
5. Danh sách signed headers được ghép bằng dấu chấm phẩy, đúng thứ tự như trên.
6. Canonical request gồm **11 dòng**, mỗi dòng nối bằng byte `LF`, **không thêm LF ở cuối**.
7. Ký bằng `HMAC-SHA-256(sharedSecret, UTF8(canonicalRequest))`; gửi **32 byte tag đầy đủ** qua Base64 chuẩn có padding trong `X-Signature`.

Canonical request:

```text
HMAC-SHA256-V1
POST
/v1/payments
merchantId=m-42
content-type:application/json
x-client-id:client-42
x-key-id:key-2026-11
x-nonce:Xo0hNWXh3NgFhNz71xtsqQ
x-timestamp:1795856400
content-type;x-client-id;x-key-id;x-nonce;x-timestamp
<sha256-hex-cua-bodyBytes>
```

**Lưu ý:** placeholder ở dòng cuối phải được thay bằng digest thật. Không dùng dữ liệu mô phỏng này như một request đang còn hiệu lực. Trong hợp đồng trên, `Content-Type` và năm header đều đi vào chữ ký, nhưng `X-Signature` **không đi vào** chính thông điệp dùng tạo signature.

### 5.1. Vì sao có dòng `signedHeaders`?

Dòng danh sách tên header thể hiện chính xác tập field mà hai bên dự định ký. Khi hợp đồng sử dụng một tập cố định, server có thể tự biết tập này từ phiên bản `HMAC-SHA256-V1`, nhưng ghi nó trong canonical request giúp test vector rõ ràng.

**Không được để client tự bỏ bớt header quan trọng** bằng cách gửi một danh sách `signedHeaders` tùy ý. Nếu hỗ trợ nhiều tập signed headers, server phải dùng **allowlist cố định theo phiên bản, endpoint và client**, không cho phép hạ mức bảo vệ tùy tiện.

### 5.2. Các trường khác cần xử lý như thế nào?

Ví dụ chưa ký `Host` và `Idempotency-Key` vì hợp đồng này chỉ minh họa năm header. **Trong tích hợp thanh toán thực tế**, nếu host/public authority, idempotency key hoặc các header khác ảnh hưởng routing/đối tượng/hiệu ứng nghiệp vụ, phải **mở rộng phiên bản hợp đồng để ký chúng** hoặc chứng minh chúng được suy ra từ dữ liệu đã xác thực và không thể bị giả mạo.

Không được lặng lẽ thêm header vào canonical request của phiên bản V1 khi verifier chưa hỗ trợ; cần phát hành version và test vector tương ứng.

## 6. Java 17+: canonicalize headers theo hợp đồng

Một hàm canonicalization nên **thuần túy**: nhận các header đã parse đúng ranh giới, kiểm tra và trả về một chuỗi cố định. Nó không tự truy xuất secret, không tính HMAC trước khi biết đủ dữ liệu và không lặng lẽ sửa các giá trị ngoài hợp đồng.

Mã Java 17+ dưới đây triển khai **phần headers** của hợp đồng `HMAC-SHA256-V1` đã nêu. Đầu vào `Map<String, List<String>>` giả định **giữ được các giá trị lặp**. Ứng dụng thực tế phải kiểm tra rằng HTTP stack/gateway không gộp duplicate trước khi gọi.

```java
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Pattern;

public final class SignedHeaderCanonicalizer {
    // Thứ tự ASCII lowercase cố định trong hợp đồng V1.
    private static final List<String> SIGNED = List.of(
            "content-type",
            "x-client-id",
            "x-key-id",
            "x-nonce",
            "x-timestamp");

    private static final Pattern ID =
            Pattern.compile("[A-Za-z0-9._-]{1,80}");
    private static final Pattern NONCE =
            Pattern.compile("[A-Za-z0-9_-]{22}");
    private static final Pattern SECONDS =
            Pattern.compile("[0-9]{1,20}");

    private SignedHeaderCanonicalizer() {}

    public static String canonicalLines(
            Map<String, List<String>> inputHeaders) {

        Map<String, String> canonical = new HashMap<>();

        for (Map.Entry<String, List<String>> entry
                : inputHeaders.entrySet()) {
            String name = entry.getKey().toLowerCase(Locale.ROOT);
            if (!SIGNED.contains(name)) {
                continue;
            }

            // Không nhận lặp header (kể cả khác cách viết hoa).
            List<String> values = entry.getValue();
            if (canonical.containsKey(name)
                    || values == null || values.size() != 1
                    || values.get(0) == null) {
                throw new IllegalArgumentException(
                        "Duplicate/malformed signed header: " + name);
            }

            canonical.put(name, normalizeValue(values.get(0)));
        }

        if (canonical.size() != SIGNED.size()) {
            throw new IllegalArgumentException(
                    "Missing required signed headers");
        }

        if (!"application/json".equals(canonical.get("content-type"))
                || !ID.matcher(canonical.get("x-client-id")).matches()
                || !ID.matcher(canonical.get("x-key-id")).matches()
                || !NONCE.matcher(canonical.get("x-nonce")).matches()
                || !SECONDS.matcher(canonical.get("x-timestamp")).matches()) {
            throw new IllegalArgumentException("Invalid signed header");
        }

        StringBuilder result = new StringBuilder();
        for (int i = 0; i < SIGNED.size(); i++) {
            if (i > 0) {
                result.append('\n');
            }
            String name = SIGNED.get(i);
            result.append(name).append(':').append(canonical.get(name));
        }
        return result.toString();
    }

    public static String signedHeadersList() {
        return String.join(";", SIGNED);
    }

    private static String normalizeValue(String raw) {
        // Hợp đồng mẫu: chỉ ký printable ASCII và chỉ trim SP hai đầu.
        int start = 0;
        int end = raw.length();
        while (start < end && raw.charAt(start) == ' ') {
            start++;
        }
        while (end > start && raw.charAt(end - 1) == ' ') {
            end--;
        }
        String result = raw.substring(start, end);
        if (result.isEmpty()) {
            throw new IllegalArgumentException("Empty signed header");
        }
        for (int i = 0; i < result.length(); i++) {
            char c = result.charAt(i);
            if (c < 0x20 || c > 0x7e) {
                // Bao gồm CR, LF, HTAB và ký tự không thuộc ASCII.
                throw new IllegalArgumentException(
                        "Unsupported header character");
            }
        }
        return result;
    }
}
```

Ví dụ tạo dữ liệu header phía sender:

```java
import java.util.List;
import java.util.Map;

Map<String, List<String>> headers = Map.of(
        "Content-Type", List.of("application/json"),
        "X-Client-Id", List.of("client-42"),
        "X-Key-Id", List.of("key-2026-11"),
        "X-Timestamp", List.of("1795856400"),
        "X-Nonce", List.of("Xo0hNWXh3NgFhNz71xtsqQ"));

String headerLines =
        SignedHeaderCanonicalizer.canonicalLines(headers);
String signedHeaderNames =
        SignedHeaderCanonicalizer.signedHeadersList();
```

**Giới hạn chủ ý của ví dụ:** hàm chỉ kiểm tra năm header được ký, không thay thế HTTP parser hoặc tầng phát hiện request smuggling. Một số framework có thể gộp duplicate thành một chuỗi `a,b`; nếu vậy backend không thể suy ra chắc chắn có bao nhiêu field gốc. Tầng gateway hoặc HTTP server phải **từ chối cách biểu diễn mơ hồ trước khi mất thông tin**.

Quy tắc nonce trong mã dùng 22 ký tự Base64URL không padding từ 16 byte ngẫu nhiên, nhưng **chỉ kiểm tra cú pháp**; nó không tự đảm bảo nonce có entropy hay chưa từng được sử dụng. Hệ thống thực tế cần CSPRNG phía gửi và kho replay phía server.

### 6.1. Ghép header lines vào canonical request và HMAC

Ví dụ tiếp theo minh họa cách nối các phần đã được chuẩn bị theo đúng **11 dòng** của hợp đồng V1:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

// method/path/query lấy từ request gốc theo hợp đồng tại điểm ký.
// bodyBytes là byte thật được gửi, không serialize lại sau bước ký.
String method = "POST";
String publicPath = "/v1/payments";
String rawQuery = "merchantId=m-42";

String bodyHash = HexFormat.of().formatHex(
        MessageDigest.getInstance("SHA-256").digest(bodyBytes));

String canonical = String.join("\n",
        "HMAC-SHA256-V1",
        method,
        publicPath,
        rawQuery,
        SignedHeaderCanonicalizer.canonicalLines(headers),
        SignedHeaderCanonicalizer.signedHeadersList(),
        bodyHash);

Mac mac = Mac.getInstance("HmacSHA256");
mac.init(new SecretKeySpec(secretBytes, "HmacSHA256"));
byte[] tag = mac.doFinal(canonical.getBytes(StandardCharsets.UTF_8));
String signatureHeader =
        Base64.getEncoder().encodeToString(tag);
```

`bodyBytes` và `secretBytes` là dữ liệu do tầng gọi cung cấp; ví dụ chưa gồm key resolver và tầng kiểm tra timestamp/nonce. `String.join` nhận một phần tử `headerLines` có nhiều LF nội bộ; kết quả vẫn gồm **11 dòng vật lý**, vì năm dòng header được ghép sẵn trong phần tử đó.

Đối với verifier, cần **dựng lại các dòng từ request thực nhận**, tìm secret theo client và key ID hợp lệ, rồi so sánh byte tag đã giải mã với kết quả HMAC tính lại bằng một phép so sánh an toàn như `MessageDigest.isEqual`. Không dùng một `Mac` có trạng thái chia sẻ giữa nhiều request chạy song song.

## 7. Timestamp, nonce và key ID là signed headers có ý nghĩa an ninh

### 7.1. Timestamp phải được ký và kiểm tra khoảng thời gian

`X-Timestamp` trong ví dụ là Unix time **tính theo giây UTC**. Server có thể chấp nhận khi:

```text
abs(serverNowSeconds - signedTimestampSeconds) <= 300
```

Việc timestamp nằm trong canonical request ngăn đối phương **thay timestamp mà giữ chữ ký cũ**. Tuy nhiên, một request có chữ ký đúng vẫn có thể được phát lại nhiều lần **trong cửa sổ hợp lệ** nếu thiếu nonce store. Cần kiểm tra cả timestamp quá cũ và quá xa tương lai, sai đơn vị giây/millisecond, overflow số nguyên và tình trạng lệch đồng hồ.

### 7.2. Nonce phải được ký và lưu chống replay

Sender tạo `X-Nonce` mới, khó trùng, ví dụ 128 bit ngẫu nhiên được mã hóa Base64URL. Server sau khi xác minh HMAC phải chấp nhận nonce bằng thao tác **insert-if-absent nguyên tử** theo principal trong kho chia sẻ đủ nhất quán. Nếu nonce đã tồn tại, request là một bản phát lại trong phạm vi bảo vệ và bị từ chối.

**Không ghi nonce trước khi kiểm tra chữ ký**, tránh bị attacker không biết secret chiếm nonce hợp lệ. TTL của nonce phải kéo dài ít nhất đến khi timestamp tương ứng **không còn được server chấp nhận**, tính cả trường hợp request được nhận sớm và sai lệch đồng hồ giữa các máy.

### 7.3. Key ID giúp rotation nhưng chưa chứng minh danh tính

`X-Client-Id` và `X-Key-Id` là **đầu vào tra khóa**, chưa phải principal đã xác thực trước khi HMAC khớp. Server chỉ chấp nhận key thuộc client và còn hiệu lực. Khi xoay từ `key-A` sang `key-B`, sender phải gửi **key ID và secret cùng phiên bản**; dùng secret A nhưng header B làm chữ ký không khớp.

Những trường này được ký để ràng buộc thông tin lựa chọn khóa với request. Nếu secret đã bị lộ, đối thủ có thể tạo request hoàn toàn mới với timestamp/nonce mới; cơ chế chống replay không thay thế quy trình thu hồi và xoay khóa.

## 8. Headers qua proxy, gateway và các phiên bản HTTP

Một request thường đi từ client qua load balancer, reverse proxy, API gateway rồi mới đến backend. Mỗi chặng có thể **sửa, thêm hoặc bỏ header**. Việc này ảnh hưởng chữ ký khi field đã ký bị thay đổi.

```mermaid
sequenceDiagram
    participant C as Sender
    participant G as API gateway
    participant S as Backend verifier
    C->>C: Chuẩn bị headers và canonical request
    C->>C: Ký HMAC
    C->>G: POST + signed headers + signature
    Note over G: Có thể đổi case, Host, path hoặc header
    G->>S: Request sau định tuyến
    S->>S: Dựng canonical request từ dữ liệu được quy định
    alt Cùng canonical bytes
        S-->>C: Chữ ký có thể hợp lệ
    else Khác canonical bytes
        S-->>C: Chữ ký sai; kiểm tra điểm biến đổi
    end
```

Các tình huống quan trọng:

- **HTTP/1.1 và HTTP/2:** HTTP/2 dùng pseudoheaders như `:method`, `:path`, `:authority`; chúng không phải field header thông thường. Giao thức ký nên định nghĩa **ý nghĩa method, public target và authority** độc lập với cách HTTP/1.1 hay HTTP/2 biểu diễn trên wire.
- **Tên header đổi chữ hoa/thường:** nếu cả hai phía lowercase tên theo hợp đồng, `Content-Type` và `content-type` tạo cùng dòng canonical.
- **Giá trị header bị đổi:** gateway thêm `charset=UTF-8` vào Content-Type, bỏ khoảng trắng có ý nghĩa hoặc chỉnh header nghiệp vụ sẽ khiến HMAC sai nếu quy tắc không cho phép.
- **Host và X-Forwarded-Host:** phía ngoài có thể tự gửi header `X-Forwarded-Host`. Backend chỉ được dùng public authority do **gateway tin cậy** cung cấp sau khi đã loại bỏ/ghi đè dữ liệu giả mạo từ Internet.
- **Header trùng hoặc bị merge:** gateway và backend có thể hiểu hai giá trị khác nhau. Với header ký quan trọng, nên từ chối duplicate ở ranh giới mà còn giữ được dữ liệu gốc.
- **Content-Encoding và body:** ký `SHA-256(bodyBytes)` đòi hỏi hai phía thống nhất byte body **trước hay sau decompression**. Thay đổi encoding mà vẫn giữ `Content-Type` có thể làm body hash sai hoặc gây khác biệt cách parse.
- **Content-Length/Transfer-Encoding:** đây là thành phần quyết định framing HTTP; cần được HTTP stack/gateway xác thực chặt chẽ để tránh diễn giải khác nhau giữa các hop. Không có nghĩa cứ đưa chúng vào HMAC là tự động chống được request smuggling.
- **Redirect, retry và interceptor:** client có thể tự đổi Host, URI hoặc Content-Type sau khi ký; sender nên ký sát thời điểm gửi cuối cùng và ký lại mỗi request mới.

### 8.1. Đặt điểm xác minh ở đâu?

Có hai phương án phổ biến:

1. **Xác minh tại gateway trước khi rewrite**: gateway thấy path/authority/headers theo public contract; sau xác thực, nó chuyển principal sang backend qua kênh nội bộ được bảo vệ, không tin header danh tính do client tự đặt.
2. **Xác minh tại backend**: gateway phải bảo toàn các thành phần đã ký hoặc cung cấp **public-original metadata đáng tin cậy**; backend dùng đúng biểu diễn client đã ký và từ chối metadata mơ hồ.

Không dùng một header tùy ý như `X-Original-Host` do Internet gửi làm bằng chứng của URI gốc. Tin cậy phải đến từ cấu hình proxy, kênh nội bộ và cơ chế loại bỏ/ghi đè header không được phép.

## 9. Xác thực HMAC không đồng nghĩa với phân quyền

HMAC có thể chứng minh client biết shared secret, canonical request chưa bị sửa ở các trường được ký và request còn hợp lệ theo các kiểm tra về thời gian/nonce. Nhưng một client hợp lệ vẫn có thể **không được phép** truy cập merchant khác.

Ví dụ:

```http
POST /v1/payments?merchantId=m-99 HTTP/1.1
X-Client-Id: client-42
X-Key-Id: key-2026-11
X-Timestamp: <current-unix-seconds>
X-Nonce: <new-nonce>
X-Signature: <valid-signature>
```

Nếu `client-42` chỉ được tạo giao dịch cho `m-42`, request có chữ ký hoàn toàn hợp lệ cho `m-99` vẫn phải bị **từ chối ở tầng phân quyền**. Không suy quyền từ một header `X-Role`, `X-Tenant-Id` hay `X-Authenticated-User` do client tự khai báo. Principal được thiết lập sau khi server xác minh secret/key; quyền phải được tra từ chính sách hoặc dữ liệu tin cậy.

Thứ tự logic:

```text
Kiểm tra input/header -> tìm key ứng viên
-> kiểm tra timestamp -> dựng canonical request -> xác minh HMAC
-> ghi nonce nguyên tử -> thiết lập principal
-> kiểm tra quyền trên endpoint/merchant/tài nguyên
-> idempotency và xử lý nghiệp vụ
```

**Idempotency-Key** là ví dụ một header có thể ảnh hưởng hành vi nghiệp vụ sau xác thực. Nếu API cho phép retry tạo thanh toán, cần bảo vệ giá trị key bằng chữ ký hoặc ràng buộc tin cậy khác; chống replay bằng nonce không thay thế idempotency.

## 10. Những lỗi header thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| HMAC sai khi qua proxy | Header đã ký bị thêm/sửa/xóa | So sánh canonical header lines ở hai ranh giới trong môi trường thử nghiệm |
| `Content-Type` đổi từ `application/json` thành `application/json; charset=utf-8` | Middleware thêm tham số | Thống nhất quy tắc hoặc ký sau biến đổi |
| Chữ ký chỉ sai với chữ hoa trong tên header | Code không lowercase tên | Dùng ASCII lowercase theo hợp đồng |
| Trùng `X-Timestamp` nhưng verifier vẫn xác thực | Parser chọn giá trị khác nhau | Từ chối duplicate ở điểm tiếp nhận |
| Chữ ký sai vì whitespace | Hai phía trim/gộp khoảng trắng khác nhau | Đặc tả chính xác SP/HTAB và ký cùng byte |
| Replay trong 5 phút dù HMAC đúng | Có timestamp nhưng không có nonce store | Ký nonce và dùng replay store nguyên tử |
| Server báo timestamp hết hạn | Client gửi millisecond thay vì second | Cố định đơn vị Unix seconds trong contract |
| Lỗi ngay sau key rotation | `keyId` không đúng secret | Lấy key ID và secret thành cặp, kiểm tra hiệu lực |
| Header signature Base64 lỗi | Proxy/client đổi encoding hoặc padding | Cố định Base64/hex, kích thước tag và cú pháp |
| Signature đúng nhưng body bị sửa | Header được ký, body không được bảo vệ | Ký body hash của raw body bytes |
| Signature đúng nhưng tenant bị đổi | Header tenant ảnh hưởng nghiệp vụ nhưng không ký | Ký tenant hoặc suy tenant từ principal |
| Authorization header bị bỏ ở gateway | Bên xác minh đặt sai ranh giới | Quy định rõ thành phần xác minh, bảo vệ principal nội bộ |
| Header dài bất thường | Thiếu giới hạn kích thước/độ dài | Giới hạn ở gateway và backend trước khi HMAC |

## 11. Ma trận kiểm thử header canonicalization

Nên có **test vector độc lập** gồm raw request, tập header, byte canonical, body hash và HMAC kỳ vọng từ secret thử nghiệm. Điều này giúp các SDK Java và verifier ở ngôn ngữ khác cùng tuân theo hợp đồng. Chỉ để hàm ký tự kiểm tra chính chữ ký của nó là chưa đủ: cả hai phía có thể chia sẻ một lỗi canonicalization.

| Ca kiểm thử | Thao tác | Kết quả kỳ vọng |
| --- | --- | --- |
| Request hợp lệ | Đủ năm signed headers và chữ ký đúng | Qua xác thực; tiếp tục replay/authorization |
| Đổi case tên header | `Content-Type` → `content-type` | Cùng canonical header lines |
| Có SP đầu/cuối | `X-Client-Id:  client-42  ` | Cùng giá trị sau trim SP theo hợp đồng |
| Có HTAB, CR hoặc LF | Thêm ký tự điều khiển vào signed header | Từ chối theo chính sách ví dụ |
| Missing header | Bỏ `X-Nonce` | Từ chối trước khi xác minh |
| Duplicate field | Hai `X-Key-Id` hoặc hai `Content-Type` | Từ chối; không chọn một giá trị tùy ý |
| Đổi signed header | Sửa timestamp hoặc nonce nhưng giữ tag | HMAC sai |
| Đổi unsigned business header | Thay tenant/merchant chưa ký | Test phải phát hiện lỗ hổng thiết kế; bổ sung ràng buộc |
| Đổi `Content-Type` | Thêm `charset` hoặc đổi media type | HMAC sai theo hợp đồng V1 |
| Đảo thứ tự header trên wire | Giữ tên và giá trị, đảo vị trí các dòng | Cùng canonical request vì order do contract quy định |
| Signature sai độ dài | Gửi tag Base64 quá ngắn hoặc dài | Verifier từ chối theo số byte tag cố định |
| Timestamp cũ hoặc tương lai xa | Ký đúng HMAC nhưng vượt cửa sổ thời gian | Từ chối theo timestamp |
| Nonce trùng giữa hai request | Gửi lại bản sao đã xử lý | Chặn replay bằng kho chung |
| Concurrent duplicate nonce | Hai instance nhận cùng nonce | Tối đa một instance chấp nhận |
| Rotation | Dùng key mới, key cũ còn hiệu lực, key đã thu hồi | Chỉ key được phép mới xác thực |
| HTTP/2 qua gateway | Header đổi case, pseudoheaders được ánh xạ | Verifier tạo cùng method/path/authority theo contract |
| Gateway rewrite body/path | Gửi qua đường đi thực tế | Xác minh tại đúng ranh giới hoặc từ chối rõ ràng |
| Client đúng HMAC nhưng sai merchant | Gọi tài nguyên ngoài quyền | Tầng phân quyền từ chối |

### 11.1. Test “đúng byte” trước khi test end-to-end

Hãy cố định giá trị năm header đã ký, method, path, query, body bytes và secret giả. So sánh **từng byte** của canonical request ở sender và verifier. Sau đó mới so sánh digest và tag. Nếu chỉ so chuỗi Base64 cuối cùng khi test sai, rất khó biết lỗi là case của tên header, xử lý duplicate, khác raw path hay JSON serialization.

Khi cần log chẩn đoán, log mã lỗi, request ID và dữ liệu đã được che; tránh log shared secret, chữ ký nguyên vẹn hoặc body nhạy cảm. Một bản sao request có chữ ký hợp lệ bị lộ qua log có thể bị phát lại trong thời gian cho phép.

## 12. Bài tập thực hành

Một nhóm phát triển thiết kế API thanh toán bằng HMAC với năm signed headers của hợp đồng `HMAC-SHA256-V1`. Gateway nhận HTTP/2 và chuyển tiếp HTTP/1.1, backend viết bằng Java 17.

Hãy phân tích:

1. Client gửi `Content-Type: application/json`, gateway chuyển thành `Content-Type: application/json; charset=UTF-8`. Vì sao chữ ký có thể sai và xử lý từ đâu?
2. Request chứa hai dòng `X-Client-Id` khác nhau nhưng một framework đã gộp chúng. Verifier có nên chọn giá trị đầu tiên không?
3. `X-Timestamp` được ký nhưng `X-Nonce` không được ký. Attacker có thể sửa nonce của request cũ rồi gửi lại không?
4. API chọn merchant từ `X-Merchant-Id` không nằm trong signed headers. Chữ ký HMAC đúng có chứng minh merchant header chưa bị sửa không?
5. Khi backend nhận `X-Forwarded-Host` từ request Internet, có thể sử dụng nó trực tiếp làm public authority để dựng canonical request không?
6. Cùng request có header field name viết chữ hoa khác nhau ở client và server. Nếu hai phía lowercase tên chính xác, HMAC có bắt buộc đổi không?
7. Sau khi request HMAC được xác minh, client muốn tạo thanh toán cho merchant khác. Vì sao vẫn cần phân quyền?
8. Nếu gửi lại nguyên request sau timeout với nonce cũ, tầng nào sẽ từ chối? Làm sao retry an toàn mà tránh tạo thanh toán trùng?

**Gợi ý đáp án:** (1) Vì giá trị header trong canonical bytes đã đổi; chỉnh điểm ký/xác minh hoặc hợp đồng; (2) không, từ chối duplicate ở ranh giới còn thấy dữ liệu gốc; (3) có thể, vì nonce không được ràng buộc HMAC, nên bắt buộc ký; (4) không, phải ký hoặc suy merchant từ principal; (5) không, cần metadata do proxy tin cậy kiểm soát; (6) không, tên canonical giống nhau; (7) xác thực khác phân quyền; (8) nonce store chặn replay, retry mới cần timestamp/nonce/chữ ký mới và giữ idempotency key của cùng ý định nghiệp vụ.

## 13. Tổng kết

Trong HMAC request authentication, **headers vừa mang bằng chứng xác thực vừa chứa dữ liệu làm thay đổi ý nghĩa request**. Một hợp đồng ký đúng phải xác định chính xác tập signed headers, tên, thứ tự, cách xử lý giá trị, khoảng trắng, giá trị lặp và encoding. Method, URI và body cũng phải được bảo vệ theo cùng hợp đồng.

Sự an toàn không chỉ đến từ thuật toán HMAC: client phải ký **đúng byte sẽ gửi**, server phải dựng lại **đúng byte đã nhận**, proxy/gateway phải duy trì ranh giới tin cậy; timestamp/nonce phải được ký và kiểm tra chống replay; key rotation cần ràng buộc client với key ID; cuối cùng **authorization** và **idempotency** vẫn là các kiểm tra độc lập. Khi kiểm soát được từng chi tiết đó, headers trở thành thành phần đáng tin cậy trong chuỗi **sender → gateway → verifier → nghiệp vụ**.

