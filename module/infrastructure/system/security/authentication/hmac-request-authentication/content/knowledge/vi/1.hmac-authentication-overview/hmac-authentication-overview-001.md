# HMAC request authentication là gì?

> **Chương:** Tổng quan HMAC request auth  
> **Phạm vi:** Xác thực yêu cầu HTTP giữa các hệ thống bằng khóa bí mật dùng chung (shared secret), chữ ký HMAC và một hợp đồng chuẩn hóa yêu cầu (canonical request). Nội dung tập trung vào tính xác thực, tính toàn vẹn, chống phát lại, vận hành khóa và ranh giới với phân quyền.

## 1. Bài toán cần giải quyết

Giả sử hệ thống bán hàng gọi API tạo thanh toán của một dịch vụ khác:

~~~http
POST /v1/payments?currency=VND HTTP/1.1
Host: api.payment.example
Content-Type: application/json

{"orderId":"o-123","amount":150000}
~~~

Máy chủ cần trả lời ít nhất ba câu hỏi:

1. **Ai gửi yêu cầu?** Yêu cầu có thực sự đến từ đối tác đã đăng ký hay chỉ tự khai tên đối tác?
2. **Dữ liệu có bị thay đổi?** Các trường quan trọng như phương thức, đường dẫn, tham số truy vấn và số tiền có còn đúng như lúc đối tác ký?
3. **Yêu cầu có còn mới?** Một yêu cầu hợp lệ trước đây có đang bị gửi lại để gây tác động lần thứ hai không?

Gửi một `clientId` ở header không chứng minh được danh tính: bất kỳ bên nào cũng có thể sao chép chuỗi đó. Gửi một hàm băm SHA-256 của body cũng chưa đủ: kẻ tấn công có thể thay body rồi tính lại hàm băm. HMAC kết hợp **khóa bí mật chỉ hai bên biết** với **nội dung yêu cầu đã được biểu diễn nhất quán** để tạo bằng chứng xác thực và toàn vẹn cho các thành phần được ký.

Kiểu xác thực này thường xuất hiện trong API kết nối server-to-server, webhook, cổng thanh toán, hệ thống đối tác và các dịch vụ dùng shared secret. Nó phù hợp khi hai bên có thể cấp phát, lưu giữ và luân chuyển khóa an toàn.

## 2. Định nghĩa và nguyên lý mật mã

**HMAC request authentication** là cơ chế mà bên gọi (client) tạo một mã xác thực thông điệp bằng HMAC trên biểu diễn xác định của HTTP request; bên nhận (server) dùng cùng khóa bí mật để tính lại mã và đối chiếu. Khi chữ ký đúng, server có cơ sở xác nhận rằng bên gửi **nắm giữ khóa tương ứng** và **các thành phần được ký không bị sửa đổi** kể từ khi ký.

Với HMAC-SHA-256:

~~~text
canonicalRequest = Canonicalize(method, target, headers, body, metadata)
macBytes         = HMAC-SHA256(sharedSecret, UTF8(canonicalRequest))
signature        = Base64URL-NoPadding(macBytes)
~~~

HMAC chuẩn được xây dựng từ hàm băm mật mã và khóa bí mật, về khái niệm:

\[
\operatorname{HMAC}_{K}(m)
=H\big((K'\oplus opad)\,\Vert\,H((K'\oplus ipad)\,\Vert\,m)\big)
\]

Trong đó `K` là khóa dùng chung; `m` là thông điệp canonical; `H` là hàm băm (ở đây SHA-256); `ipad` và `opad` là các hằng đệm của thuật toán. **Không tự triển khai công thức này trong ứng dụng**; sử dụng thư viện HMAC tiêu chuẩn, ví dụ `javax.crypto.Mac` của Java.

Cần phân biệt:

| Thành phần | Công dụng | Có dùng khóa bí mật? |
|---|---|---|
| SHA-256(body) | Phát hiện khác biệt giữa hai chuỗi byte của body; làm đầu vào cho canonical request | Không |
| HMAC-SHA256(secret, canonicalRequest) | Chứng thực và bảo vệ tính toàn vẹn của các thành phần đã ký | Có |
| TLS/HTTPS | Mã hóa kênh truyền, kiểm tra chứng chỉ server và bảo vệ thông điệp trên đường truyền | Có cơ chế khóa riêng của TLS |
| Phân quyền (authorization) | Quyết định client đã được xác thực có quyền thực hiện thao tác trên tài nguyên cụ thể hay không | Dựa vào chính sách, quyền và ngữ cảnh |

HMAC **không mã hóa dữ liệu** và không tự chống replay. Vì cả client lẫn server đều biết shared secret, HMAC cũng **không tạo tính không thể chối bỏ** theo nghĩa chữ ký số bất đối xứng.

## 3. Một request được ký như thế nào?

Một giao thức HMAC cần **hợp đồng ký** (signing contract) được hai bên thống nhất trước. Hợp đồng phải quy định chính xác thuật toán, định dạng khóa, phiên bản, trường nào được ký, thứ tự và quy tắc canonical hóa, cách mã hóa chữ ký, dung sai thời gian, quy tắc nonce và cách phân phối/luân chuyển khóa.

Ví dụ sau là **hợp đồng minh họa `hmac-v1`**, không phải định dạng HMAC HTTP bắt buộc cho mọi sản phẩm:

| Mục | Quy tắc của `hmac-v1` |
|---|---|
| Thuật toán | `HmacSHA256`; secret ngẫu nhiên có ít nhất 32 byte |
| Phiên bản | Chuỗi cố định `hmac-v1`, là dòng đầu của canonical request |
| Method | Giữ đúng token HTTP, ví dụ `POST`; adapter chỉ chấp nhận method theo hợp đồng |
| Request target | Dùng nguyên chuỗi **encoded path + raw query** theo thứ tự truyền, ví dụ `/v1/payments?currency=VND&orderId=o-123` |
| Header `Content-Type` | Bỏ khoảng trắng ở hai đầu và chuyển thành chữ thường bằng `Locale.ROOT`; không có header thì dùng chuỗi rỗng |
| Danh tính | `X-Client-Id` và `X-Key-Id` được đưa vào nội dung ký |
| Thời điểm | `X-Timestamp`: số giây Unix dạng thập phân, không dấu và không số `0` thừa ở đầu |
| Nonce | `X-Nonce`: 16–32 byte sinh bằng bộ sinh số ngẫu nhiên mật mã, mã hóa Base64URL không padding |
| Body | SHA-256 của **đúng chuỗi byte body đã gửi**, thể hiện dưới dạng hex chữ thường; body rỗng dùng mảng byte rỗng |
| Chữ ký truyền đi | `X-Signature` = Base64URL không padding của 32 byte HMAC, dài 43 ký tự |
| Ký tự phân cách | Mỗi thành phần canonical nằm trên một dòng, nối bằng LF (`\n`), **không có LF ở cuối**; cấm CR/LF bên trong giá trị trường |

Ví dụ HTTP request:

~~~http
POST /v1/payments?currency=VND&orderId=o-123 HTTP/1.1
Host: api.payment.example
Content-Type: application/json
X-Client-Id: merchant-17
X-Key-Id: key-2026-11
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
X-Signature: <base64url-cua-hmac-sha256>

{"orderId":"o-123","amount":150000}
~~~

Với đúng request trên, chuỗi đầu vào HMAC có **chín dòng**:

~~~text
hmac-v1
POST
/v1/payments?currency=VND&orderId=o-123
application/json
merchant-17
key-2026-11
1795824000
b75sZVQmhTBcfnX-bNbGqw
<sha256-hex-cua-chinh-cac-byte-body>
~~~

Hai chuỗi trong dấu `<...>` chỉ là **ký hiệu thay thế**, không phải chữ ký hoặc digest thực tế. Trong triển khai thật, digest phải được tính từ chuỗi byte UTF-8 của body ở ví dụ, rồi thay vào dòng cuối trước khi chạy HMAC. Secret **không** được gửi trong request. Server tra secret theo cặp `(clientId, keyId)` đã được cấp trước đó; `keyId` là định danh để chọn khóa, không phải bí mật.

### 3.1. Vì sao canonical request bắt buộc phải xác định?

HMAC nhận **byte**, không hiểu ý nghĩa HTTP hay JSON. Các cách diễn đạt có thể tương đương về nghiệp vụ nhưng khác về byte:

~~~text
/v1/items?a=1&b=2      != /v1/items?b=2&a=1
/v1/a%2Fb               != /v1/a/b
{"a":1,"b":2}            != {"b":2,"a":1}
Content-Type: application/json
                            != Content-Type: application/json; charset=utf-8
~~~

Trong `hmac-v1`, thứ tự query, dạng percent-encoding, thứ tự khóa JSON, khoảng trắng body và các tham số của `Content-Type` đều có thể làm chữ ký khác đi. **Không tự parse rồi sắp xếp lại query, không deserialize rồi serialize lại JSON** nếu hợp đồng chỉ ký raw target và raw body. Client phải ký **chính các byte sẽ gửi**; server phải kiểm tra **các byte đã thực sự nhận** tại điểm xác thực.

Một hệ thống khác có thể chọn quy tắc sắp xếp query, chuẩn hóa percent-encoding, chọn tập header khác hoặc ký nội dung `Digest`; tất cả đều hợp lệ nếu được đặc tả chính xác và thực hiện đồng nhất. Không được lặng lẽ chuyển giữa hai hợp đồng.

### 3.2. Nên ký những gì?

Nên bảo vệ tối thiểu **method, đường dẫn, query quan trọng, body/digest, danh tính client, phiên bản, timestamp, nonce**. Ký thêm `Content-Type` để tránh thay đổi cách hiểu body. Nếu cùng khóa có khả năng được dùng cho nhiều host hoặc dịch vụ, nên ràng buộc thêm **audience/host đích hoặc định danh dịch vụ** được định nghĩa ổn định trong hợp đồng; tốt hơn là dùng khóa riêng cho từng môi trường và dịch vụ.

Tránh ký các trường dễ biến đổi khi đi qua hạ tầng như `Content-Length`, `Transfer-Encoding`, `Connection` hay header thêm vào bởi proxy, trừ khi mọi bên đã chuẩn hóa và kiểm soát chúng. Với các header có trong hợp đồng, phải quy định cách xử lý khoảng trắng, chữ hoa/thường, giá trị trùng lặp; phương án an toàn, dễ kiểm thử là **từ chối header chữ ký xuất hiện nhiều lần hoặc không đúng định dạng**.

## 4. Luồng xác thực ở máy chủ

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Proxy / Gateway
    participant A as API verifier
    participant K as Key store
    participant N as Nonce store
    C->>C: Canonicalize request + HMAC(secret)
    C->>P: HTTPS request + signature/timestamp/nonce
    P->>A: Chuyển request theo hợp đồng
    A->>K: Tìm khóa theo clientId, keyId
    K-->>A: Khóa hợp lệ cho bước verify
    A->>A: Kiểm tra cấu trúc, timestamp, chữ ký
    A->>N: Reserve nonce nguyên tử, có TTL
    N-->>A: Thành công / đã tồn tại
    A->>A: Tạo identity đã xác thực
    A->>A: Kiểm tra quyền với tài nguyên
    A-->>C: Kết quả HTTP qua proxy
~~~

Quy trình triển khai nên gồm các bước:

1. **Tiếp nhận và kiểm tra cấu trúc:** giới hạn kích thước request/header/body; yêu cầu đủ các header đã ký; không chấp nhận header trùng, chữ ký sai encoding, timestamp không hợp lệ, CR/LF chèn vào dữ liệu. Bắt đầu từ raw target và body tại đúng lớp thực hiện kiểm tra HMAC.
2. **Xác định khóa:** lấy `clientId` và `keyId` chỉ để tra cứu bản ghi khóa được quản lý ở server; kiểm tra khóa thuộc client, đúng dịch vụ/môi trường, có trạng thái cho phép **verify**. Không tin bất kỳ secret nào do request gửi kèm.
3. **Kiểm tra thời gian:** so sánh timestamp đã ký với đồng hồ server; ví dụ chấp nhận `|now - timestamp| ≤ 300 giây`. Đồng hồ server cần đồng bộ thời gian. Giới hạn này chỉ giảm phạm vi replay.
4. **Tái tạo canonical request và HMAC:** áp dụng đúng hợp đồng và khóa đã tra; giải mã chữ ký; so sánh byte bằng hàm so sánh an toàn theo thời gian như `MessageDigest.isEqual`. Không so sánh HMAC qua `String.equals` như một lựa chọn mặc định.
5. **Chống replay:** sau khi xác minh MAC, ghi nhận nonce theo phạm vi client/khóa bằng thao tác **insert-if-absent nguyên tử**; nếu nonce đã tồn tại, từ chối. Kho nonce phải dùng chung giữa các instance xác thực.
6. **Thiết lập principal và phân quyền:** gắn identity client đã xác thực vào security context; kiểm tra quyền với thao tác và tài nguyên (ví dụ merchant đó có được tạo thanh toán cho `orderId` này không?).
7. **Trả kết quả có kiểm soát:** thường dùng `400` cho request sai định dạng, `401` cho thông tin xác thực sai/thiếu/hết hạn, `403` cho client hợp lệ nhưng không đủ quyền. Phản hồi ngoài không tiết lộ secret, chữ ký kỳ vọng hoặc trạng thái chi tiết của khóa.

Kiểm tra chữ ký đúng chỉ chứng minh quyền nắm giữ secret tại thời điểm ký, **không chứng minh client được phép thực hiện mọi API**. Bỏ bước 6 có thể tạo lỗ hổng phân quyền dù mật mã hoàn toàn chính xác.

## 5. Chống replay bằng timestamp và nonce

Nếu chỉ kiểm tra HMAC, một bản sao byte-for-byte của request hợp lệ vẫn cho chữ ký đúng. Với API tạo giao dịch, retry hoặc phát lại không kiểm soát có thể gây yêu cầu lặp.

**Timestamp** giới hạn khoảng thời gian chấp nhận; **nonce** (number used once) giúp server phân biệt một lần gửi với bản sao của lần đó. Client phải sinh nonce bằng `SecureRandom` (hoặc CSPRNG tương đương), **không** dùng biến đếm cục bộ dễ reset, thời gian hiện tại làm nonce, hay `java.util.Random`.

Ví dụ chính sách cửa sổ ±5 phút:

~~~text
timestamp hợp lệ nếu: serverNow - 300 <= signedTimestamp <= serverNow + 300
nonce key:             namespace(clientId, keyId) + nonce
lưu nonce:             chỉ sau khi MAC hợp lệ; insert-if-absent nguyên tử
TTL ví dụ:             600 giây tính từ lúc ghi nhận (2 × cửa sổ 300 giây)
~~~

Lý do TTL có thể cần **gấp đôi** dung sai: ở thời điểm nhận, một timestamp hợp lệ có thể đang đi trước đồng hồ server gần 5 phút; chữ ký mang timestamp đó còn nằm trong cửa sổ chấp nhận thêm gần 10 phút tính từ lần nhận đầu. Chính sách chính xác có thể đặt hạn hết hiệu lực của nonce bằng `signedTimestamp + window` cộng sai số an toàn.

Trong hệ thống nhiều node, có thể dùng một Redis dùng chung với thao tác tương đương:

~~~text
SET hmac:nonce:<scope-and-nonce> 1 NX EX 600
~~~

Chỉ kết quả **SET thành công** mới cho phép đi tiếp. Không dùng mẫu “GET rồi SET” vì hai request chạy song song có thể cùng vượt qua. Nếu nonce store lỗi, verifier phải **fail closed** theo chính sách vận hành (ví dụ trả lỗi tạm thời), không bỏ qua replay check để tiếp tục giao dịch.

**Nonce khác idempotency key.** Request có chữ ký hợp lệ đã được server nhận nhưng client mất response: khi retry, client cần timestamp/nonce mới và chữ ký mới. Để tránh tạo giao dịch trùng, API vẫn cần cơ chế **idempotency** ở tầng nghiệp vụ, ví dụ khóa nghiệp vụ `Idempotency-Key` được gắn với principal và nội dung yêu cầu. Nếu giá trị này chi phối hành vi nghiệp vụ, nên đưa nó vào hợp đồng ký.

## 6. Ví dụ triển khai Java: tạo và xác minh chữ ký

Đoạn sau dùng Java 17+ và thư viện chuẩn của JDK; nó minh họa **cùng một định dạng canonical cho client và server**. Bộ chuyển đổi từ HTTP framework sang `Request`, tra cứu secret theo `(clientId, keyId)`, quản lý vòng đời khóa và kho nonce thực tế thuộc lớp tích hợp.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Locale;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacV1 {
    private static final long WINDOW_SECONDS = 300;

    private HmacV1() {}

    public record Request(
            String method, String rawTarget, String contentType,
            String clientId, String keyId, String timestamp,
            String nonce, byte[] body) {}

    // reserve trả true đúng một lần; triển khai bằng Redis SET ... NX EX
    // hoặc kho khác hỗ trợ insert-if-absent nguyên tử và TTL.
    public interface NonceStore {
        boolean reserve(String namespace, String nonce, Duration ttl);
    }

    public static String sign(Request r, byte[] secret)
            throws GeneralSecurityException {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(mac(r, secret));
    }

    public static boolean verify(Request r, String signature, byte[] secret,
                                 long nowSeconds, NonceStore nonces)
            throws GeneralSecurityException {
        if (r == null || r.body() == null || signature == null
                || nonces == null || signature.length() != 43) {
            return false;
        }
        try {
            // Chuỗi thập phân canonical, từ chối dấu, khoảng trắng, leading zero.
            if (!line(r.timestamp()).matches("[1-9][0-9]{0,18}")) {
                return false;
            }
            long sentAt = Long.parseLong(r.timestamp());
            if (sentAt < nowSeconds - WINDOW_SECONDS
                    || sentAt > nowSeconds + WINDOW_SECONDS) {
                return false;
            }
            if (!validNonce(line(r.nonce()))) {
                return false;
            }

            byte[] received = Base64.getUrlDecoder().decode(signature);
            if (received.length != 32
                    || !Base64.getUrlEncoder().withoutPadding()
                              .encodeToString(received).equals(signature)) {
                return false;
            }

            byte[] expected = mac(r, secret);
            if (!MessageDigest.isEqual(expected, received)) {
                return false;
            }

            // Chỉ reserve nonce sau khi MAC đã được xác thực.
            String namespace = r.clientId().length() + ":" 
                    + r.clientId() + ":" + r.keyId();
            return nonces.reserve(namespace, r.nonce(),
                    Duration.ofSeconds(2 * WINDOW_SECONDS));
        } catch (IllegalArgumentException ex) {
            return false; // Trường đầu vào không hợp lệ, fail closed.
        }
    }

    private static boolean validNonce(String value) {
        if (value.length() < 22 || value.length() > 43) return false;
        byte[] bytes = Base64.getUrlDecoder().decode(value);
        return bytes.length >= 16 && bytes.length <= 32
                && Base64.getUrlEncoder().withoutPadding()
                         .encodeToString(bytes).equals(value);
    }

    private static byte[] mac(Request r, byte[] secret)
            throws GeneralSecurityException {
        if (secret == null || secret.length < 32) {
            throw new IllegalArgumentException("Secret phải có >= 32 byte");
        }
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(canonical(r).getBytes(StandardCharsets.UTF_8));
    }

    private static String canonical(Request r)
            throws GeneralSecurityException {
        byte[] bodyHash = MessageDigest.getInstance("SHA-256")
                .digest(r.body());
        String bodyHex = HexFormat.of().formatHex(bodyHash);
        return String.join("\n",
                "hmac-v1",
                line(r.method()),
                line(r.rawTarget()),
                line(r.contentType()).trim().toLowerCase(Locale.ROOT),
                line(r.clientId()),
                line(r.keyId()),
                line(r.timestamp()),
                line(r.nonce()),
                bodyHex);
    }

    private static String line(String value) {
        if (value == null || value.indexOf('\r') >= 0
                || value.indexOf('\n') >= 0) {
            throw new IllegalArgumentException("Giá trị canonical không hợp lệ");
        }
        return value;
    }
}
~~~

Client sinh nonce và timestamp mới cho mỗi request:

~~~java
byte[] randomBytes = new byte[16];
new java.security.SecureRandom().nextBytes(randomBytes);
String nonce = Base64.getUrlEncoder().withoutPadding()
        .encodeToString(randomBytes);
String timestamp = Long.toString(java.time.Instant.now().getEpochSecond());

byte[] body = "{\"orderId\":\"o-123\",\"amount\":150000}"
        .getBytes(StandardCharsets.UTF_8);
HmacV1.Request request = new HmacV1.Request(
        "POST", "/v1/payments?currency=VND&orderId=o-123",
        "application/json", "merchant-17", "key-2026-11",
        timestamp, nonce, body);
String signature = HmacV1.sign(request, secret);
// Gửi đúng request target, header và body đã dùng khi tính chữ ký.
~~~

`secret` trong đoạn trên là mảng byte khóa đã được cấp phát và giữ an toàn **ngoài source code**. Ví dụ dùng `byte[] body` để làm rõ tính bất biến của dữ liệu ký; ứng dụng thực phải đặt giới hạn dung lượng, quản lý buffer/stream có kiểm soát và tránh việc framework đọc body rồi thay đổi nó trước khi xác minh.

Ở server, **không lấy secret trực tiếp từ request**. Server tra khóa hợp lệ từ kho khóa theo định danh client/key đã đăng ký, sau đó gọi `HmacV1.verify(...)`. Dịch vụ cung cấp `NonceStore` phân tán và ánh xạ principal sang chính sách phân quyền. Những bước tích hợp này quyết định độ an toàn thực tế; đoạn mã minh họa không phải middleware sản xuất hoàn chỉnh.

## 7. Quản lý shared secret và key rotation

Một chữ ký đúng chỉ đáng tin như quá trình bảo vệ khóa. Nên tạo **khóa ngẫu nhiên độc lập** cho mỗi client, môi trường và phạm vi dịch vụ; lưu trong secret manager/KMS hoặc kho được kiểm soát quyền, có quy trình cấp phát và thu hồi. Không đặt khóa vào source code, URL, log, tài liệu công khai, trình duyệt hoặc ứng dụng mobile không tin cậy.

Ví dụ vòng đời khóa:

| Trạng thái | Client được ký yêu cầu mới? | Server được xác minh yêu cầu cũ? |
|---|---|---|
| `ACTIVE` | Có | Có |
| `VERIFY_ONLY` | Không dùng để ký mới | Có, trong thời gian chuyển tiếp đã giới hạn |
| `REVOKED` | Không | Không |

Quy trình rotation thường là: (1) phát hành khóa mới với `keyId` mới; (2) cho server chấp nhận đồng thời khóa mới và khóa cũ khi đang chuyển tiếp; (3) chuyển client sang ký bằng khóa mới; (4) đưa khóa cũ sang `VERIFY_ONLY` trong thời gian ngắn đã định; (5) thu hồi khóa cũ; (6) kiểm tra log/metric để xác nhận client đã di chuyển. Khoảng overlap cần tính đến request đang bay, hàng đợi và sai lệch đồng hồ. Khi nghi ngờ khóa lộ, **thu hồi ngay** và phối hợp cấp lại, không duy trì overlap thông thường.

`keyId` giúp server chọn đúng bản ghi khóa; việc đưa cả `clientId` lẫn `keyId` vào dữ liệu ký ngăn tráo các định danh này mà vẫn giữ MAC hợp lệ. Khóa phải được ràng buộc với đúng principal và audience; không dùng một secret chung cho tất cả đối tác.

## 8. Khi có reverse proxy, API gateway và service mesh

Tuyến đường triển khai có thể là `Client → CDN/WAF → API Gateway → Service`. HTTP qua các lớp này có thể thay đổi mà nghiệp vụ không nhận ra:

| Biến đổi hạ tầng | Nguy cơ khi xác minh HMAC | Cách thiết kế/kiểm tra |
|---|---|---|
| Rewrite path (`/public/v1` thành `/v1`) | Raw target mà verifier nhìn thấy khác chuỗi client ký | Xác minh tại edge trước rewrite hoặc truyền **request target gốc qua kênh đáng tin** giữa các lớp |
| Decode/re-encode URI, thay thứ tự query | Byte canonical thay đổi | Chốt rõ representation và vị trí verifier; test `%2F`, `%20`, dấu `+`, query trùng khóa |
| Thêm/sửa header, chuẩn hóa `Content-Type` | Signed header thay đổi | Chỉ chọn header ổn định; chốt quy tắc trim/case và reject duplicate header |
| Giải nén/re-encode/chuyển JSON | Digest body khác | Ký đúng byte ở tầng xác minh hoặc thiết kế content digest thống nhất trước và sau biến đổi |
| TLS termination, HTTP/2 → HTTP/1.1 | Host, pseudo-header, scheme/port có thể khác | Quy định audience/authority tin cậy; kiểm tra trên cả HTTP/1.1 và HTTP/2 |
| Nhiều instance verifier | Nonce lưu cục bộ cho phép replay qua node khác | Dùng shared nonce store và phép ghi nguyên tử |

Không tin `X-Original-URI`, `X-Forwarded-*` hay header tương tự nếu client bên ngoài có thể tự gửi chúng: proxy đáng tin phải **xóa giá trị do client tự khai** và thiết lập lại khi cần. Mọi thành phần tác động tới request được ký cần được kiểm thử ở cả đường trực tiếp và đường production có gateway.

Chữ ký HMAC có thể được xác minh ở **gateway** hoặc **application**, nhưng phải có một hợp đồng thống nhất về raw target/body và một ranh giới tin cậy rõ ràng. Nếu gateway xác thực rồi chuyển identity nội bộ, application chỉ được tin identity đó từ đường kết nối hoặc cơ chế xác thực nội bộ được bảo vệ.

## 9. Kiểm thử tối thiểu cần có

| Tình huống | Kết quả kỳ vọng |
|---|---|
| Đúng secret, đúng canonical, timestamp hợp lệ, nonce chưa dùng | Xác thực thành công; tiếp tục kiểm tra phân quyền |
| Đổi amount/body sau khi ký | MAC sai, từ chối |
| Đổi `POST` thành `GET` hoặc sửa path/query sau khi ký | MAC sai, từ chối |
| Hoán đổi thứ tự query theo hợp đồng raw target | MAC sai, trừ khi client ký lại đúng thứ tự mới |
| Thay `X-Client-Id` hoặc `X-Key-Id` | Không tìm được khóa phù hợp hoặc MAC sai |
| Timestamp vượt giới hạn ±5 phút | Từ chối dù HMAC đúng |
| Gửi lại nguyên request trong cửa sổ thời gian | Chỉ request đầu tiên được reserve nonce; request sau bị từ chối |
| Gửi hai bản sao đồng thời đến hai node | Kho nonce nguyên tử cho phép tối đa một bản |
| Header chữ ký bị trùng, nonce/sig không đúng Base64URL | Từ chối do đầu vào sai |
| Khóa cũ trong giai đoạn `VERIFY_ONLY` và sau khi `REVOKED` | Được verify trong overlap; bị từ chối sau thu hồi |
| Gateway rewrite URI hoặc thay đổi body | Test phát hiện sai khác canonical; điều chỉnh vị trí xác minh/hợp đồng |
| HMAC hợp lệ nhưng client không có quyền truy cập tài nguyên | Xác thực thành công, phân quyền trả `403` |
| Replay store mất kết nối | Không cấp quyền bằng cách bỏ qua nonce check |

Đối với phần mật mã thuần túy, nên đối chiếu với **test vector HMAC-SHA-256 của RFC 4231** để phát hiện lỗi mã hóa khóa/thông điệp. Tách kiểm thử thành ba lớp: (1) tạo canonical string với các byte cố định; (2) tính MAC và so sánh byte; (3) integration test qua proxy/gateway, clock skew, rotation, concurrency và lỗi backend.

## 10. Các sai lầm thường gặp và nguyên tắc vận hành

- **Chỉ ký body:** attacker có thể đổi method, path hoặc query khi các trường đó ảnh hưởng nghiệp vụ. Phải ký toàn bộ những thành phần an ninh quan trọng.
- **Tính `SHA256(secret + body)` thay HMAC:** thiết kế không theo chuẩn HMAC và dễ mắc lỗi. Dùng `Mac.getInstance("HmacSHA256")`.
- **Ký JSON đã parse:** hai phía có thể serialize khác thứ tự key, whitespace hoặc encoding. Ký byte body thực tế hoặc áp dụng chuẩn canonical JSON đã được đặc tả.
- **Tin timestamp là đủ:** request có thể bị phát lại nhiều lần trong cửa sổ hợp lệ. Bổ sung nonce store và idempotency cho thao tác tạo/sửa.
- **Bỏ qua lỗi nonce store:** fail-open biến hạ tầng chống replay thành tùy chọn; phải có chính sách fail-closed và giám sát.
- **So sánh signature thiếu cẩn trọng:** dùng so sánh byte có đặc tính chống timing leak; xác thực độ dài và encoding trước khi so sánh.
- **Dùng một khóa cố định lâu dài:** khó khoanh vùng sự cố. Áp dụng key ID, rotation, thu hồi, phân tách môi trường và phân quyền truy cập secret.
- **Không kiểm thử proxy:** request target, header hoặc body có thể khác giữa môi trường dev và production.
- **Nhầm xác thực với phân quyền:** xác thực thành công không trao mọi quyền. Luôn kiểm tra quyền với action, resource và principal.

Trong vận hành, nên theo dõi tỷ lệ signature failure theo `clientId/keyId`, timestamp skew, replay rejection, lỗi tra secret, lỗi nonce store, sử dụng khóa sắp hết hạn và thay đổi đột biến theo gateway. Log chỉ nên giữ **metadata tối thiểu đã làm sạch** (request ID, client ID được phép ghi, key ID, nguyên nhân phân loại); tuyệt đối không log shared secret, MAC kỳ vọng hay payload nhạy cảm. Giới hạn tốc độ, giới hạn body và HTTPS vẫn cần thiết dù đã có HMAC.

## 11. Tổng kết kiến thức và câu hỏi tự kiểm tra

Một hệ thống HMAC request authentication an toàn được tạo từ nhiều mắt xích: **shared secret đủ mạnh → hợp đồng canonical nhất quán → HMAC xác minh đúng → timestamp/nonce chống replay → quản lý khóa → phân quyền riêng → kiểm thử xuyên gateway**. Thiếu một mắt xích có thể khiến hệ thống cho phép yêu cầu bị giả mạo, bị sửa đổi hoặc bị gửi lại mặc dù mã HMAC sử dụng đúng thuật toán.

Tự kiểm tra:

1. Vì sao `SHA-256(body)` không thể thay thế `HMAC-SHA256(secret, canonicalRequest)`?
2. Hệ thống nào sẽ chấp nhận hai JSON có cùng nội dung ngữ nghĩa nhưng khác thứ tự key, và điều đó phụ thuộc vào quy tắc nào?
3. Với dung sai timestamp ±300 giây, tại sao TTL nonce 300 giây có thể không đủ?
4. Khi gateway đổi `/external/payments` thành `/payments`, nên xác minh chữ ký ở đâu, hoặc cần thay đổi hợp đồng thế nào?
5. Khi request có chữ ký đúng nhưng client cố tạo thanh toán cho đơn hàng của merchant khác, lớp kiểm tra nào phải từ chối?

**Tài liệu tham khảo:** [RFC 2104 — HMAC: Keyed-Hashing for Message Authentication](https://www.rfc-editor.org/rfc/rfc2104), [RFC 4231 — Identifiers and Test Vectors for HMAC-SHA-224/256/384/512](https://www.rfc-editor.org/rfc/rfc4231), [RFC 3986 — URI Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986), [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421). RFC 9421 là một cách chuẩn hóa chữ ký thông điệp HTTP với thuật ngữ và lựa chọn thành phần riêng; ví dụ `hmac-v1` trong bài là hợp đồng ứng dụng minh họa, không phải triển khai RFC 9421.
