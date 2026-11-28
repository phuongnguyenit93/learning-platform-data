# Request receiver trong mô hình xác thực HMAC

> **Chương:** Mô hình client server  
> **Phạm vi bài học:** Vai trò, thiết kế và triển khai **request receiver** (bên nhận HTTP request) trong mô hình xác thực yêu cầu bằng HMAC, shared secret và canonical request. Receiver kiểm tra chữ ký, timestamp/nonce, trạng thái khóa, tương tác với proxy/gateway và chuyển danh tính đã xác thực sang bước phân quyền.

## 1. Request receiver là gì?

Trong một giao thức HMAC request authentication, **request sender** là bên tạo request và chữ ký; **request receiver** là điểm nhận yêu cầu, tái tạo dữ liệu đã ký và quyết định có chấp nhận danh tính được khai báo hay không. Receiver có thể nằm tại API gateway, một service riêng, hoặc lớp filter/middleware trước business controller.

Giả sử một đối tác gửi lệnh tạo thanh toán:

~~~http
POST /v1/payments?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: merchant-17
X-Key-Id: key-2026-11
X-Timestamp: 1795824000
X-Nonce: xzTWlHvMPAj9xQlDQTxcDw
X-Signature: <base64url-cua-hmac>

{"orderId":"order-123","amount":150000}
~~~

Receiver không thể chỉ tin `X-Client-Id: merchant-17`: attacker cũng có thể tự điền header này. Thay vào đó, receiver tìm khóa bí mật đã cấp cho merchant và key ID, tái tạo **canonical request** từ request nhận được, tính HMAC theo hợp đồng và đối chiếu với chữ ký. Sau bước đó, receiver xác thực được **quyền nắm giữ khóa** gắn với client; controller hoặc tầng policy mới quyết định client có **quyền** tạo thanh toán cho đơn hàng cụ thể hay không.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Chỉ ra nhiệm vụ của receiver so với sender, proxy, key store, nonce store và authorization service.
2. Thiết kế luồng kiểm tra một request có ký HMAC từ lúc nhận byte HTTP đến khi tạo authenticated principal.
3. Xác định chính xác đâu là dữ liệu **raw** và đâu là dữ liệu được phép chuẩn hóa theo hợp đồng ký.
4. Thiết kế kiểm tra khóa, chữ ký, timestamp, nonce, key rotation và xử lý lỗi an toàn.
5. Viết lõi verifier bằng Java và kết nối đúng với HTTP framework qua một adapter tin cậy.
6. Thiết kế kiểm thử integration qua gateway/proxy, nhiều instance và các trường hợp header/URI/body mơ hồ.

## 2. Receiver đứng ở đâu trong kiến trúc?

~~~mermaid
sequenceDiagram
    participant C as HTTP client / Sender
    participant G as Gateway / Reverse proxy
    participant R as Request receiver
    participant K as Key store
    participant N as Shared nonce store
    participant A as Authorization / Business API
    C->>C: Tạo body, timestamp, nonce, canonical request
    C->>C: HMAC-SHA-256(secret, canonical request)
    C->>G: HTTPS request + signature headers
    G->>R: Chuyển request theo hợp đồng ký
    R->>R: Kiểm tra framing, header, size, raw bytes
    R->>K: Tra clientId + keyId + audience
    K-->>R: Khóa hợp lệ để verify
    R->>R: Canonicalize + kiểm tra timestamp + HMAC
    R->>N: Đánh dấu nonce atomically với TTL
    N-->>R: Nonce mới / trùng
    alt Xác thực thành công
        R->>A: Authenticated principal + request
        A->>A: Kiểm tra action/resource/tenant
        A-->>C: Business response qua gateway
    else Bất kỳ kiểm tra bắt buộc nào thất bại
        R-->>C: Từ chối có kiểm soát
    end
~~~

**Ranh giới tin cậy** rất quan trọng:

- **Mạng ngoài và HTTP header do client gửi đều chưa đáng tin.** Receiver cần kiểm tra giá trị, độ dài và số lượng header, bất kể client tự nhận là ai.
- **Gateway chỉ đáng tin trong phần được kiểm soát:** nếu proxy xác thực nội bộ, xóa header giả mạo từ bên ngoài và chuyển đúng raw target/body theo hợp đồng, receiver có thể sử dụng metadata của proxy. Nếu không có sự bảo đảm này, `X-Original-URI` hoặc `X-Forwarded-*` phải coi như dữ liệu do client kiểm soát.
- **Key store có thẩm quyền về danh tính:** request không được chỉ định secret và không được tự quyết định trạng thái khóa của mình.
- **Nonce store quyết định tính mới:** tất cả receiver instance phải thống nhất trạng thái nonce, không giữ cache riêng dẫn đến replay qua node khác.
- **Authorization có trách nhiệm độc lập:** HMAC hợp lệ không đồng nghĩa client có quyền đối với mọi tài nguyên.

Receiver có thể verify ở **edge** trước khi gateway rewrite URI/body, hoặc sau gateway nếu contract xác định rõ dữ liệu nào được bảo vệ và cách truyền dữ liệu gốc qua kênh tin cậy. Việc chọn vị trí phải rõ từ đầu; không được để gateway và service tự suy diễn hai chuỗi canonical khác nhau.

## 3. Hợp đồng giữa sender và receiver

HMAC hoạt động trên chuỗi byte. Hai phía phải thống nhất một **signing contract**: chọn thành phần request để ký, quy tắc mã hóa, chuẩn hóa, tên header và chính sách thời gian. Nếu không, hai phía có thể nhận cùng một HTTP request về mặt nghiệp vụ nhưng tính ra hai tag khác nhau.

### 3.1. Hợp đồng minh họa `hmac-v1`

Trong bài này, ta sử dụng hợp đồng cụ thể sau để lập trình và kiểm thử. **Đây là ví dụ ứng dụng, không phải định dạng bắt buộc của HMAC HTTP hay triển khai RFC 9421.**

| Thành phần | Quy tắc receiver phải áp dụng |
|---|---|
| Phiên bản | Dòng đầu literal `hmac-v1`; không tự downgrade sang phiên bản cũ |
| Thuật toán | HMAC-SHA-256 với shared secret là **32 byte ngẫu nhiên** được cấp trước |
| Method | HTTP method ở dạng token viết hoa đúng như request gửi, ví dụ `POST` |
| Raw request target | **Encoded path + raw query** theo thứ tự và byte được kiểm tra; ví dụ `/v1/payments?currency=VND`, không chứa scheme/fragment |
| `Content-Type` | Một header duy nhất nếu có; trim hai đầu và lower-case bằng `Locale.ROOT`; thiếu header được biểu diễn bằng chuỗi rỗng |
| `X-Client-Id` | Định danh client, một giá trị duy nhất, được ký |
| `X-Key-Id` | Định danh phiên bản khóa thuộc client, một giá trị duy nhất, được ký |
| `X-Timestamp` | Unix epoch **seconds** dạng số nguyên thập phân canonical, được ký |
| `X-Nonce` | Base64URL không padding của **16–32 byte CSPRNG**, được ký |
| Body | Băm **đúng raw body bytes đã nhận** bằng SHA-256; đưa lowercase hexadecimal digest vào canonical request |
| `X-Signature` | Base64URL không padding của toàn bộ HMAC-SHA-256 (32 byte, 43 ký tự); không đưa chính signature vào chuỗi ký |
| Ngăn cách | Mỗi thành phần là một dòng, nối bằng LF (`\n`); không có LF sau dòng cuối, không cho phép CR/LF trong giá trị |

Receiver cần thêm ràng buộc **audience/dịch vụ/môi trường** vào bản ghi khóa. Nếu cùng một secret được chia sẻ giữa nhiều host/dịch vụ, hợp đồng nên ký cả audience hoặc authority tin cậy, hoặc tốt hơn dùng secret riêng cho mỗi audience. Ví dụ chỉ ký các trường trong bảng với giả định secret đã được phân tách theo dịch vụ và môi trường.

Đối với request ví dụ ở đầu bài, receiver tái tạo:

~~~text
hmac-v1
POST
/v1/payments?currency=VND
application/json
merchant-17
key-2026-11
1795824000
xzTWlHvMPAj9xQlDQTxcDw
<sha256-hex-cua-raw-body>
~~~

Dòng cuối là chuỗi 64 ký tự hex tính từ byte UTF-8 của JSON đã nhận. Biểu thức `<sha256-hex-cua-raw-body>` trong ví dụ là chỗ giữ chỗ; receiver thực tế tính digest và thay bằng kết quả thật trước khi chạy HMAC. Header `X-Signature` cũng chứa tag Base64URL thật, không phải văn bản `<...>`.

### 3.2. Raw bytes và biểu diễn được chuẩn hóa

Một số biểu diễn có vẻ tương đương nhưng **khác nhau khi ký HMAC**:

~~~text
/v1/items?a=1&b=2   != /v1/items?b=2&a=1
/v1/a%2Fb            != /v1/a/b
{"x":1,"y":2}         != {"y":2,"x":1}
{"amount":150000}    != { "amount": 150000 }
~~~

Trong contract của bài, receiver **không parse rồi sắp xếp lại query**, không giải mã và mã hóa lại path, cũng không parse/serialize lại JSON trước khi hash. Nếu JSON được gzip, chuyển charset hoặc biến đổi tại proxy, cần định nghĩa chính xác receiver xác minh **byte nào** và kiểm thử với cấu hình thực tế; việc hai phía cùng gọi dữ liệu là “JSON” không bảo đảm cùng byte.

HTTP header có tên không phân biệt chữ hoa/thường, nhưng điều đó không có nghĩa tự động biến đổi mọi **giá trị** header là an toàn. Chỉ trường được contract quy định rõ (ví dụ `Content-Type` trong hợp đồng này) mới được chuẩn hóa tương ứng. Receiver cần từ chối header ký trùng, giá trị mơ hồ hoặc các giá trị có ký tự điều khiển; không âm thầm chọn “giá trị đầu tiên” hay nối hai giá trị theo một quy tắc framework tự đặt.

## 4. Receiver phải thu nhận những dữ liệu nào?

Một receiver thường cần một **request envelope** bất biến (immutable về mặt logic) tại ranh giới xác thực, bao gồm:

~~~text
RequestEnvelope
  method              HTTP method trong hợp đồng ký
  rawTarget           encoded path + raw query, chưa tái cấu trúc
  contentType         header có đúng một giá trị hoặc absent
  clientId            định danh từ X-Client-Id
  keyId               phiên bản khóa từ X-Key-Id
  timestamp           chuỗi timestamp gốc
  nonce               chuỗi nonce gốc
  signature           chuỗi Base64URL gốc
  body                byte[]/buffer của body nhận được
  resolvedAudience    định danh API nội bộ từ cấu hình/trusted routing
~~~

`resolvedAudience` phải xuất phát từ tuyến dịch vụ đáng tin, **không** chỉ từ một header tùy ý do bên ngoài gửi. Những trường client khai như `clientId`, `keyId` chỉ trở thành danh tính tin cậy sau khi tag hợp lệ và khóa được ràng buộc đúng client/audience.

### 4.1. Thời điểm đọc body

Framework thường cung cấp body như stream chỉ đọc **một lần**. Nếu filter đọc hết stream để tính hash, controller phía sau có thể không còn body để parse; ngược lại, nếu controller parse JSON trước, byte đã chuẩn hóa có thể khác byte ban đầu. Vì vậy:

1. Nhận **raw body bytes trước khi request binder/JSON serializer can thiệp**.
2. Đặt giới hạn kích thước trước hoặc trong khi buffer, chẳng hạn 1 MiB cho endpoint nghiệp vụ có body nhỏ; không đọc vô hạn vào RAM.
3. Dùng cùng một buffer/stream digest được xác minh để cung cấp lại cho controller, hoặc đặt verifier ở nơi có thể replay body an toàn.
4. Đối với upload lớn, thiết kế dạng streaming digest và replay/forwarding có giới hạn; không mặc định copy toàn bộ file vào heap.
5. Từ chối trường hợp `Content-Length`/`Transfer-Encoding` mơ hồ bằng cách dựa vào HTTP parser/gateway tuân thủ giao thức, tránh bất đồng framing giữa proxy và backend.

**Ví dụ về hậu quả của đọc sai thời điểm:** sender ký raw body `{"a":1,"b":2}`; receiver dùng một DTO rồi serialize lại thành `{"b":2,"a":1}`. Hai payload có thể tương đương ở tầng JSON, nhưng SHA-256 khác nhau nên MAC sẽ không khớp. Receiver cần kiểm tra byte đã thực sự truyền theo hợp đồng.

### 4.2. Giới hạn và kiểm tra dữ liệu đầu vào

Một receiver nên kiểm tra trước phép tính HMAC đắt hơn và trước truy vấn kho khóa:

| Đầu vào | Ví dụ quy tắc kiểm tra |
|---|---|
| Method | Chỉ các method endpoint hỗ trợ; ký đúng token theo contract |
| Raw target | Phải có encoded path hợp lệ; giới hạn chiều dài; loại CR/LF/control/fragment và encoding sai |
| Body | Giới hạn số byte; reject request framing mơ hồ; body null được quy về mảng rỗng nếu contract cho phép |
| Header ký | Mỗi header yêu cầu đúng một giá trị, đúng ASCII/UTF-8 theo contract, không CR/LF |
| `clientId/keyId` | Không rỗng, giới hạn độ dài, tập ký tự cho phép |
| Timestamp | Kiểm tra dạng thập phân canonical; không chấp nhận overflow/giá trị âm khi contract cấm |
| Nonce | Kiểm tra Base64URL không padding, độ dài byte 16–32; giá trị do sender sinh CSPRNG |
| Signature | Base64URL không padding, đúng 32 byte; tránh nhận encoding khác rồi tự “sửa” |

Các giới hạn cụ thể phụ thuộc API, gateway và SLA. Bên nhận không thể chứng minh nonce là ngẫu nhiên chỉ bằng nhìn vào một request; receiver chỉ kiểm tra **định dạng, độ dài và tính duy nhất**; trách nhiệm sinh CSPRNG thuộc sender.

## 5. Pipeline xác thực: từ untrusted request tới principal

~~~mermaid
flowchart TD
    A["HTTP request tới receiver"] --> B["Kiểm tra framing, kích thước, header, raw target/body"]
    B --> C{"Đầu vào hợp lệ?"}
    C -- Không --> R400["400 Bad Request"]
    C -- Có --> D["Tra khóa theo clientId + keyId + audience"]
    D --> E{"Khóa được phép verify?"}
    E -- Không --> R401["401 Unauthorized"]
    E -- Có --> F["Kiểm tra timestamp trong cửa sổ"]
    F --> G{"Thời gian hợp lệ?"}
    G -- Không --> R401
    G -- Có --> H["Rebuild canonical request, tính HMAC, so sánh tag"]
    H --> I{"MAC khớp?"}
    I -- Không --> R401
    I -- Có --> J["Reserve nonce nguyên tử, có TTL"]
    J --> K{"Nonce mới?"}
    K -- Không --> R401
    K -- Có --> L["Tạo principal đã xác thực"]
    L --> M["Authorization theo action + resource + tenant"]
    M --> N{"Đủ quyền?"}
    N -- Không --> R403["403 Forbidden"]
    N -- Có --> O["Xử lý nghiệp vụ, có idempotency khi cần"]
    J -. "Kho nonce lỗi" .-> R503["503: từ chối tạm thời; fail closed"]
~~~

Thứ tự có thể điều chỉnh để phù hợp hiệu năng hoặc tránh lộ thông tin, nhưng các điều kiện kiểm tra bắt buộc phải cùng được thỏa mãn. **Không ghi nhận nonce trước khi xác minh chữ ký**: attacker có thể gửi MAC sai với nonce lấy từ một request hợp lệ để chiếm chỗ, gây từ chối dịch vụ cho request thật.

### 5.1. Tra khóa và kiểm tra key rotation

Receiver sử dụng `(clientId, keyId)` để tìm bản ghi khóa đã được cấp trước đó; kiểm tra thêm:

- Khóa thuộc **đúng client**, dịch vụ/audience, môi trường và thuật toán.
- Trạng thái được phép **VERIFY** (`ACTIVE` hoặc `VERIFY_ONLY` trong giai đoạn chuyển tiếp đã giới hạn).
- Thời gian hiệu lực phù hợp với chính sách. Khóa `REVOKED` phải bị từ chối ngay kể cả khi HMAC đúng.
- Không có cơ chế “không thấy key ID thì thử khóa mặc định”, không tự động thử toàn bộ khóa của mọi client.

Để rotate, server có thể giữ hai **key ID khác nhau** trong cửa sổ overlap ngắn, cho phép verify cả hai trong phạm vi được phép; client chuyển sang khóa mới rồi khóa cũ bị thu hồi. `keyId` là selector không bí mật; secret tuyệt đối không được truyền trong HTTP request.

### 5.2. Tính lại MAC và đối chiếu

Receiver chuẩn hóa các trường **đúng hợp đồng**, tính SHA-256 của raw body, ghép canonical string và chạy HMAC-SHA-256 bằng secret đã tìm được. Sau khi giải mã `X-Signature` thành 32 byte, so sánh bằng hàm có đặc tính chống timing leak như `MessageDigest.isEqual`. Không tự viết HMAC bằng cách nối secret với body rồi hash; không so sánh tag bằng cách trả thông tin từng byte khác nhau.

Không nên tiết lộ trong response rằng “secret không đúng”, “client ID tồn tại nhưng key ID không tồn tại” hoặc tag kỳ vọng; việc phân loại nội bộ được lưu ở dạng mã lỗi an toàn để vận hành.

### 5.3. Timestamp và nonce chống replay

Giả sử contract chấp nhận độ lệch đồng hồ `±300` giây:

~~~text
nowSeconds - 300 <= signedTimestamp <= nowSeconds + 300
nonceScope = namespace(clientId, keyId) + nonce
reserve nonce atomically: SET nonceKey 1 NX EX 600
~~~

Timestamp cũ hơn hoặc đi trước quá xa bị từ chối. Dù timestamp hợp lệ, yêu cầu có cùng nonce trong cùng phạm vi không được qua lần hai. Phép ghi nonce phải **nguyên tử** và dùng chung giữa mọi verifier node. Với độ lệch ±5 phút, TTL khoảng 10 phút tính từ lần nhận đầu là ví dụ đơn giản giúp giữ nonce đến khi timestamp không còn được chấp nhận; chính sách thực tế cần xét sai lệch đồng hồ, delay hàng đợi và thời gian lưu trữ.

Nếu nonce store mất kết nối, receiver phải **fail closed** theo chính sách, có thể trả lỗi dịch vụ tạm thời `503`; không bỏ qua kiểm tra replay rồi xử lý thanh toán. Nonce chống **phát lại request đã ký**; người biết secret vẫn có thể tự tạo request mới với timestamp và nonce mới.

### 5.4. Xây dựng authenticated principal

Chỉ khi tất cả kiểm tra xác thực đều qua, receiver mới tạo security principal hoặc gán authenticated identity (ví dụ `partner-17`), kèm phạm vi/audience đáng tin, cách xác thực và metadata cần thiết. Phần tiếp theo phải kiểm tra **authorization**:

~~~text
principal = partner-17 đã xác thực bằng HMAC
action    = payments:create
resource  = order-123
tenant    = merchant-17

authorization = policy(principal, action, resource, tenant)
~~~

Nếu request ký đúng nhưng merchant cố tạo thanh toán cho đơn hàng không thuộc mình, tầng phân quyền phải từ chối. Với endpoint tạo giao dịch, idempotency key riêng còn cần thiết để tránh thực thi lặp do retry hợp lệ với nonce mới; nếu header idempotency ảnh hưởng hành vi, nên đưa nó vào thành phần ký.

## 6. Ví dụ Java 17+: lõi request receiver

Ví dụ dưới đây là **lõi verifier độc lập HTTP framework** để thấy ranh giới giữa raw request, key lookup, kiểm tra HMAC, anti-replay và principal. Adapter bên ngoài cần đảm bảo **header ký không bị trùng**, raw target không bị rewrite mơ hồ, body có giới hạn và nonce store thực sự atomic. Đây là mã minh họa cho `hmac-v1`, không phải middleware production hoàn chỉnh.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Optional;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacRequestReceiver {
    private static final long WINDOW_SECONDS = 300;
    private static final Duration NONCE_TTL = Duration.ofSeconds(600);

    public record Envelope(
            String method,
            String rawTarget,
            String contentType,
            String clientId,
            String keyId,
            String timestamp,
            String nonce,
            String signature,
            byte[] rawBody,
            String audience) {}

    public record Principal(String clientId, String audience, String keyId) {}

    // Secret đã lấy từ key store; adapter bảo đảm record thuộc client/audience.
    public record KeyRecord(byte[] secret, boolean verifyAllowed) {}

    public interface KeyStore {
        Optional<KeyRecord> findForVerify(
                String clientId, String keyId, String audience);
    }

    public interface NonceStore {
        // Phải là thao tác insert-if-absent có TTL, atomic giữa mọi node.
        boolean reserve(String namespace, String nonce, Duration ttl);
    }

    public static final class Unauthorized extends RuntimeException {
        public Unauthorized() { super("Invalid request authentication"); }
    }

    private final KeyStore keys;
    private final NonceStore nonces;

    public HmacRequestReceiver(KeyStore keys, NonceStore nonces) {
        this.keys = keys;
        this.nonces = nonces;
    }

    public Principal authenticate(Envelope request, long nowSeconds)
            throws GeneralSecurityException {
        validate(request);

        // clientId/keyId chưa đáng tin cho tới khi HMAC hợp lệ.
        KeyRecord key = keys.findForVerify(
                request.clientId(), request.keyId(), request.audience())
                .filter(KeyRecord::verifyAllowed)
                .orElseThrow(Unauthorized::new);
        if (key.secret() == null || key.secret().length != 32) {
            throw new Unauthorized();
        }

        final long sentAt;
        try {
            sentAt = Long.parseLong(request.timestamp());
        } catch (NumberFormatException ex) {
            throw new Unauthorized();
        }
        if (sentAt < nowSeconds - WINDOW_SECONDS
                || sentAt > nowSeconds + WINDOW_SECONDS) {
            throw new Unauthorized();
        }

        byte[] receivedTag;
        try {
            receivedTag = Base64.getUrlDecoder()
                    .decode(request.signature());
        } catch (IllegalArgumentException ex) {
            throw new Unauthorized();
        }
        if (receivedTag.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(receivedTag)
                        .equals(request.signature())) {
            throw new Unauthorized();
        }

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key.secret(), "HmacSHA256"));
        byte[] expectedTag = mac.doFinal(
                canonical(request).getBytes(StandardCharsets.UTF_8));
        if (!MessageDigest.isEqual(expectedTag, receivedTag)) {
            throw new Unauthorized();
        }

        // Chỉ ghi nonce sau khi chữ ký hợp lệ.
        // Dùng length prefix để namespace không bị nhập nhằng.
        String scope = request.clientId().length() + ":"
                + request.clientId() + ":" + request.keyId()
                + ":" + request.audience();
        if (!nonces.reserve(scope, request.nonce(), NONCE_TTL)) {
            throw new Unauthorized();
        }
        return new Principal(request.clientId(),
                request.audience(), request.keyId());
    }

    private static String canonical(Envelope r)
            throws GeneralSecurityException {
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(r.rawBody());
        return String.join("\n",
                "hmac-v1",
                r.method(),
                r.rawTarget(),
                r.contentType() == null ? ""
                        : r.contentType().trim().toLowerCase(Locale.ROOT),
                r.clientId(),
                r.keyId(),
                r.timestamp(),
                r.nonce(),
                HexFormat.of().formatHex(digest));
    }

    private static void validate(Envelope r) {
        if (r == null || r.rawBody() == null
                || r.rawBody().length > 1024 * 1024
                || !safe(r.method(), 16)
                || !r.method().matches("[A-Z]+")
                || !safe(r.rawTarget(), 8192)
                || !r.rawTarget().startsWith("/")
                || r.rawTarget().contains("#")
                || !optionalSafe(r.contentType(), 256)
                || !safe(r.clientId(), 64)
                || !r.clientId().matches("[A-Za-z0-9._-]+")
                || !safe(r.keyId(), 64)
                || !r.keyId().matches("[A-Za-z0-9._-]+")
                || !safe(r.audience(), 128)
                || !safe(r.timestamp(), 20)
                || !r.timestamp().matches("[1-9][0-9]{0,18}")
                || !safe(r.nonce(), 43)
                || !safe(r.signature(), 43)
                || r.signature().length() != 43) {
            throw new Unauthorized();
        }
        try {
            byte[] nonceBytes = Base64.getUrlDecoder().decode(r.nonce());
            if (nonceBytes.length < 16 || nonceBytes.length > 32
                    || !Base64.getUrlEncoder().withoutPadding()
                            .encodeToString(nonceBytes).equals(r.nonce())) {
                throw new Unauthorized();
            }
        } catch (IllegalArgumentException ex) {
            throw new Unauthorized();
        }
    }

    private static boolean safe(String value, int maxLen) {
        if (value == null || value.isEmpty() || value.length() > maxLen) {
            return false;
        }
        // Không cho phép ký tự điều khiển phá vỡ chuỗi canonical.
        return value.chars().noneMatch(c -> c < 0x20 || c == 0x7F);
    }

    private static boolean optionalSafe(String value, int maxLen) {
        return value == null || value.isEmpty() || safe(value, maxLen);
    }
}
~~~

**Cách đọc ví dụ:**

- `Envelope` chỉ đại diện cho dữ liệu receiver cần kiểm tra; các trường `byte[]` có thể thay đổi nếu bên ngoài giữ tham chiếu, vì vậy adapter phải **sao chép hoặc đóng băng buffer** trước khi verify và trước khi chuyển cho downstream.
- `KeyStore.findForVerify` phải thực hiện kiểm tra trạng thái, hiệu lực, identity, audience, thuật toán và key rotation; `verifyAllowed` là kết quả của policy đó. Bản ghi khóa sai cấu hình cần bị từ chối hoặc báo lỗi hạ tầng, không được fallback sang secret mặc định.
- `NonceStore.reserve` phải triển khai bằng kho chia sẻ có primitive nguyên tử; nếu kho lỗi thì ném lỗi hạ tầng để caller **không tiếp tục request**. Code không có thao tác tiếp tục khi reserve thất bại.
- Adapter phải **từ chối duplicate signed headers**, percent encoding sai, raw target không hợp lệ và tình trạng body/URI đã bị biến đổi ngoài hợp đồng; lõi ở trên không thể tự suy ra liệu proxy đã rewrite URI hay framework đã gộp header hay chưa.
- `nowSeconds` phải lấy từ đồng hồ server đồng bộ, không lấy từ giá trị request ngoài chữ ký; giới hạn ±300 giây là cấu hình ví dụ.
- Ví dụ dùng một tag cố định 32 byte và secret đúng 32 byte để đơn giản hóa; một hệ thống khác có thể có chính sách riêng về thuật toán/chiều dài, nhưng **hai phía phải đồng nhất**.

### 6.1. Adapter HTTP nên thực hiện gì?

Trước khi gọi `authenticate`, adapter trong Spring MVC, Jakarta Servlet, Micronaut hoặc framework khác phải đảm nhiệm các bước ở ranh giới HTTP:

~~~text
onHttpRequest(exchange):
    enforceTrustedHTTPFraming(exchange)
    enforceBodyAndHeaderSizeLimits(exchange)
    rejectDuplicateSignedHeaders(exchange)
    rawTarget = getOriginalEncodedPathAndQueryAtVerificationPoint(exchange)
    rawBody   = captureBodyBytesOnceWithLimit(exchange)
    audience  = resolveAudienceFromTrustedRoutingConfig(exchange)

    envelope = new Envelope(
        methodFromRequest,
        rawTarget,
        singleValueOrEmpty("Content-Type"),
        singleRequiredValue("X-Client-Id"),
        singleRequiredValue("X-Key-Id"),
        singleRequiredValue("X-Timestamp"),
        singleRequiredValue("X-Nonce"),
        singleRequiredValue("X-Signature"),
        rawBody,
        audience)

    principal = receiver.authenticate(envelope, trustedClock.epochSeconds())
    securityContext.setAuthenticatedPrincipal(principal)
    forwardRequestWithSameBodyBytesToAuthorizedBusinessHandler()
~~~

**Đây là pseudocode của adapter**, không phải hàm có sẵn trong Servlet API. Với Servlet, `getRequestURI()` và `getQueryString()` là ứng viên để dựng target tại ranh giới ứng dụng, nhưng cần kiểm tra servlet container và gateway thực tế xem có preserve raw percent encoding, dấu phân cách, query order và rewrite path hay không. Với HTTP/2, đường dẫn thường xuất phát từ pseudo-header `:path` tại edge; container có thể đã quy đổi sang biểu diễn khác trước khi đưa vào app.

Nếu filter đã đọc body, cần dùng request wrapper có body cache/stream có thể đọc lại, hoặc một component ở gateway có thể verify và forward đúng byte. Với upload lớn, nên thiết kế streaming digest và body forwarding riêng thay vì cache không giới hạn.

## 7. Khả năng vận hành sau reverse proxy / API gateway

Đường đi thực tế:

~~~text
Sender
  -> TLS edge / WAF
  -> API Gateway (routing, rewrite, auth metadata)
  -> Request receiver
  -> Service authorization
  -> Business handler
~~~

Tại mỗi hop cần biết chính xác **thành phần nào trong request còn nguyên vẹn**:

| Tác động tại gateway/proxy | Nguy cơ đối với receiver | Cách xử lý có chủ đích |
|---|---|---|
| Rewrite `/public/v1/payments` thành `/v1/payments` | Raw path khác byte mà sender ký | Verify trước rewrite hoặc chuyển original target qua kênh nội bộ đáng tin |
| Normalize `%2F` thành `/`; sắp xếp query | Canonical request thay đổi | Chốt vị trí verify và representation; test encoded URI và query trùng |
| Chèn/chỉnh `Content-Type` | Signed header khác hợp đồng | Không ký header có thể bị middleware đổi hoặc kiểm soát chặt cách chuyển |
| Gzip/ungzip, JSON reserialize | Digest raw body khác | Verify trước biến đổi hoặc thiết kế quy tắc content digest thống nhất |
| TLS termination hoặc HTTP/2→HTTP/1.1 | `Host`, scheme, authority, framing có thể khác | Không mù quáng ký hop-specific fields; audience lấy từ routing đáng tin |
| Gateway tự gắn `X-Client-Id` | App có thể tin dữ liệu giả mạo từ ngoài | Strip header client tự gửi; chỉ gắn identity đã xác thực qua kênh nội bộ tin cậy |
| Load balancing tới nhiều verifier node | Hai bản request replay qua hai node cùng được nhận | Nonce store dùng chung và ghi atomically |

Không cho client tự đặt các header nội bộ mà downstream xem là identity đã xác thực; gateway phải loại bỏ hoặc ghi đè chúng. Service phía sau phải xác thực nguồn gateway, chẳng hạn mTLS hoặc một kênh nội bộ có policy mạng và authentication thích hợp. Nếu receiver verify trực tiếp tại backend, backend vẫn cần raw target/body đúng hợp đồng.

### Kịch bản “chữ ký đúng ở dev, sai ở production”

Sender ký `/external/payments?x=1&y=2`. Ở dev, app nhận nguyên request target; ở production, gateway bỏ prefix `/external` và re-encode query. Backend lại tính MAC từ `/payments?x=1&y=2`, dẫn đến chữ ký sai mặc dù secret đúng và request chưa bị attacker sửa đổi.

Để khắc phục, **không tắt kiểm tra chữ ký**. Chọn một trong hai cách:

1. Đặt receiver tại edge trước bước rewrite, kiểm tra canonical request đúng target sender gửi.
2. Định nghĩa một target chuẩn theo contract có thể được khôi phục **an toàn** từ metadata do gateway được xác thực chuyển đến, rồi kiểm thử cả sender và receiver với chính target đó.

Tránh dùng `X-Original-URI` do internet client tự khai làm bằng chứng về đường dẫn gốc; nếu cần header do proxy thêm, proxy phải xóa giá trị đầu vào và chỉ backend được kết nối đến proxy đáng tin.

## 8. Lỗi, phản hồi và quan sát hệ thống

Một receiver không nên phản hồi chi tiết để attacker suy ra key ID hợp lệ, trạng thái khóa hoặc byte nào trong HMAC bị sai. Phân tách lỗi cho **nội bộ** và phản hồi được công khai:

| Tình huống | Phản hồi tham khảo | Điều cần ghi nhận an toàn |
|---|---|---|
| Header thiếu, nhiều giá trị, dữ liệu malformed, request vượt size | `400 Bad Request` hoặc `413 Content Too Large` | Lý do phân loại, request ID, giới hạn bị vượt |
| Client/key ID không hợp lệ hoặc MAC không khớp | `401 Unauthorized` | Nhóm lỗi xác thực; không log secret hay expected MAC |
| Timestamp quá cũ/quá mới, nonce trùng | Thường `401 Unauthorized` hoặc mã lỗi công khai thống nhất theo API | Clock skew, loại reject, client ID đã được sanitize |
| Principal xác thực nhưng không đủ quyền | `403 Forbidden` | Principal, action, resource đã giảm độ nhạy, policy ID |
| Key store/nonce store không sẵn sàng | `503 Service Unavailable` hoặc lỗi tạm thời tương đương | Trạng thái dependency, metric lỗi; không bỏ qua verify |
| Business handler thất bại sau xác thực | Mã lỗi nghiệp vụ thích hợp | Correlation ID, idempotency key và metadata được cho phép |

Mã HTTP cụ thể tùy contract và mô hình chống dò tìm; các lỗi xác thực cần nhất quán với chính sách, không vô tình tiết lộ sự tồn tại của client hoặc key. Với phía sender, `401` không nên dẫn đến việc “thử lại vô hạn bằng cùng nonce”. Khi cần retry một request mới, sender phải tạo timestamp/nonce và chữ ký mới, còn tầng nghiệp vụ cần idempotency để tránh giao dịch trùng.

**Metric hữu ích:** tỷ lệ signature failure theo version, timestamp skew, số replay rejection, độ trễ lookup khóa, lỗi key store/nonce store, sử dụng key ID sắp thu hồi, số request bị reject vì canonical/duplicate header, tỷ lệ lỗi theo gateway route. Log **không chứa** shared secret, tag HMAC kỳ vọng, body nhạy cảm, giá trị định danh không được phép ghi hoặc thông tin đủ để truy lại secret.

### Một lưu ý về thứ tự ghi nonce

Nonce được reserve khi tag hợp lệ và trước business handler. Một request đã qua auth nhưng bị từ chối authorization hoặc business failure vẫn có thể làm nonce bị tiêu thụ. Đây là lựa chọn an toàn và dễ giải thích: một nonce không nên dùng lại để thử nhiều hành vi khác nhau. Nếu client muốn gửi lại, phải **ký lại bằng nonce mới**, đồng thời dùng idempotency ở tầng nghiệp vụ theo chính sách.

## 9. Kiểm thử receiver theo từng ranh giới

| Ca kiểm thử | Input hoặc thao tác | Kết quả mong đợi |
|---|---|---|
| Happy path | MAC đúng, key ACTIVE, timestamp hợp lệ, nonce mới | Tạo principal; đi tiếp tới authorization |
| Sửa method | `POST` được ký, nhận `PUT` | Chữ ký sai, từ chối |
| Sửa target | Đổi path/query hoặc thứ tự query sau ký | Chữ ký sai theo contract raw target |
| Thay body | Đổi `amount` hoặc whitespace body | Digest/MAC thay đổi, từ chối |
| Duplicate signed header | Hai `X-Client-Id` hoặc `X-Signature` | Reject trước verify |
| Signature sai encoding | Base64 thường, thừa padding hoặc khác 32 byte | Reject định dạng/MAC |
| Client/key mismatch | ID của merchant A, khóa của merchant B | Không tìm khóa phù hợp hoặc MAC sai |
| Key rotation | Key `VERIFY_ONLY` rồi `REVOKED` | Verify theo cửa sổ overlap, từ chối sau revoke |
| Timestamp lệch | Ngoài cửa sổ ±300 giây | Từ chối kể cả MAC đúng |
| Replay | Gửi lại cùng signed request | Lần thứ hai bị reject |
| Replay race | Hai request cùng nonce đến hai node đồng thời | Chỉ tối đa một `reserve` thành công |
| Nonce store hỏng | Mất kết nối ở thời điểm reserve | Fail closed; không gọi business handler |
| Gateway rewrite | Proxy đổi path/percent encoding/body | Test phát hiện mismatch; sửa contract/vị trí receiver |
| Request body đọc hai lần | Filter verify và controller parse tiếp | Controller nhận lại đúng cùng body bytes |
| Authentication vs authorization | Principal hợp lệ gọi tài nguyên khác tenant | Receiver xác thực; policy từ chối `403` |
| Signed idempotency | Client retry với nonce mới, cùng idempotency key | Không thực thi giao dịch hai lần theo policy |

### Ví dụ kiểm thử phân biệt hai lỗi dễ nhầm

**Lỗi xác thực:**

~~~text
clientId = merchant-17
method = POST
body = {"amount":150000}
signature = HMAC(secretOfMerchant17, canonicalBodyAmount150000)

Attacker sửa body thành {"amount":900000}
=> receiver dựng canonical bytes mới; MAC không khớp; từ chối.
~~~

**Lỗi phân quyền:**

~~~text
clientId = merchant-17
body = {"orderId":"order-owned-by-merchant-42"}
signature = HMAC(secretOfMerchant17, canonicalRequest)

=> MAC hợp lệ, principal = merchant-17
=> authorization kiểm tra chủ sở hữu order
=> từ chối vì order không thuộc merchant-17.
~~~

Điểm khác nhau nằm ở **câu hỏi bảo mật**: “Yêu cầu do holder của khóa nào gửi và có bị sửa đổi không?” thuộc receiver authentication; “Holder đó có quyền làm việc này không?” thuộc authorization.

### 9.1. Kiểm thử xuyên gateway có ý nghĩa gì?

Unit test HMAC có thể đúng nhưng production sai nếu request đã bị proxy biến đổi. Vì vậy integration test phải đi qua **cùng cấu hình gateway, WAF, protocol conversion và backend** như production; đo sự nhất quán của raw target, signed headers và body digest tại sender/receiver bằng dữ liệu test không nhạy cảm.

Tối thiểu nên thử các biến thể `/a%2Fb`, `/a/b`, query đảo thứ tự, query trùng khóa, khoảng trắng và charset trong `Content-Type`, body JSON có dấu cách khác nhau, request không có body, request HTTP/2, body vượt giới hạn, duplicate header và nhiều receiver node.

## 10. Bài tập thiết kế

**Bài 1 — Phác họa pipeline receiver:** Vẽ lại luồng từ request vào đến authorization. Giải thích vì sao không nên đưa `X-Client-Id` trực tiếp vào security context trước khi so HMAC, và vì sao nonce không nên bị reserve khi MAC chưa hợp lệ.

**Bài 2 — Khác biệt ở gateway:** Sender ký `POST /api/payments?a=1&b=2` nhưng backend nhìn thấy `POST /payments?b=2&a=1`. Hãy chỉ ra các byte khác nhau, đề xuất vị trí verifier hoặc cách chuyển original target đáng tin, và viết ba integration test xác nhận giải pháp.

**Bài 3 — Rotation và replay:** Hai key ID của client cùng có hiệu lực xác minh trong 15 phút. Một request sử dụng key cũ và nonce `N` đã được chấp nhận; sender ký lại bằng key mới với nonce `N`. Hãy phân tích việc chọn phạm vi khóa nonce ảnh hưởng thế nào tới hành vi chấp nhận và quyết định chính sách nào cần mô tả rõ trong hợp đồng.

**Bài 4 — Backend có nhiều node:** Một instance ở AZ1 không kết nối được nonce store nhưng vẫn trả “authenticated” vì MAC đúng. Hãy chỉ ra lỗi bảo mật và đề xuất cách test fail-closed, alert, response retry.

**Bài 5 — HMAC và quyền:** Một đối tác ký thành công request đổi tài khoản thanh toán cho tài nguyên thuộc tenant khác. Hãy mô tả trạng thái principal ngay sau verify và policy cần áp dụng trước cập nhật dữ liệu.

## 11. Ghi nhớ

**Request receiver** là điểm biến một HTTP request chưa đáng tin thành yêu cầu có danh tính đã được xác thực. Nó phải tiếp nhận đúng byte theo signing contract, kiểm tra định dạng và giới hạn, tìm secret đúng principal/audience, tái tạo canonical request, verify HMAC, kiểm tra timestamp/nonce phân tán và trạng thái khóa. Sau đó receiver mới chuyển principal cho bước **phân quyền và xử lý nghiệp vụ**. Với hệ thống có proxy/gateway, các quy tắc raw target, header và body phải được chốt và kiểm thử tại đúng vị trí xác minh.

**Tài liệu tham khảo:** [RFC 2104 — HMAC](https://www.rfc-editor.org/rfc/rfc2104), [RFC 4231 — HMAC test vectors](https://www.rfc-editor.org/rfc/rfc4231), [RFC 3986 — URI Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986), [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110), [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421). Hợp đồng `hmac-v1` ở trên là ví dụ phục vụ học tập; nếu hệ thống dùng RFC 9421 hoặc chuẩn riêng của nhà cung cấp, receiver phải áp dụng đúng chuẩn/hợp đồng tương ứng.
