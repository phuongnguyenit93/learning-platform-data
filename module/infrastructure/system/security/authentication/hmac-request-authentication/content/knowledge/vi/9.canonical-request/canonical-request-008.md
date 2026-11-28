# Canonical timestamp trong xác thực HTTP request bằng HMAC

Một HTTP request được ký bằng HMAC có thể bị chụp lại và gửi lần nữa mà không cần biết **shared secret**. Nếu server chỉ xác minh HMAC trên method, URI, header và body, chữ ký của bản sao vẫn hợp lệ. **Timestamp** giúp server giới hạn khoảng thời gian mà một request đã ký được chấp nhận; khi đưa timestamp vào **canonical request**, kẻ tấn công không thể tự đổi thời điểm gửi mà vẫn giữ chữ ký hợp lệ.

Bài **Canonical timestamp** thuộc chương **Canonical request**, module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Module thiết kế xác thực HTTP request bằng HMAC với shared secret và canonical request bao gồm phương thức, URI, header hoặc body theo hợp đồng ký. Nội dung dưới đây tập trung vào **định dạng timestamp chính xác ở cấp byte**, kiểm tra đồng hồ và thời gian hiệu lực, phối hợp timestamp với nonce để chống replay, quản lý key rotation, kiểm thử khi đi qua proxy/gateway và phân biệt xác thực với phân quyền.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Chọn một định dạng thời gian duy nhất cho hợp đồng ký và giải thích tại sao thời gian dạng text phải được canonical hóa cẩn thận.
2. Xây dựng canonical request có trường timestamp cùng method, raw URI, các signed header và body digest.
3. Kiểm tra timestamp hợp lệ, quá cũ hoặc đến từ tương lai bằng **đồng hồ server**, với cửa sổ thời gian rõ ràng.
4. Giải thích tại sao timestamp **không tự chống replay** nếu thiếu nonce store dùng chung và thao tác claim nguyên tử.
5. Viết Java 17 ký và xác minh timestamp bằng `Instant`, `Clock`, `Mac` và test với đồng hồ cố định.
6. Nhận diện lỗi do timezone, seconds/milliseconds, header trùng, proxy rewrite, key rotation và retry.

## 2. Timestamp trong HMAC request authentication là gì?

Timestamp là một giá trị thể hiện **thời điểm client tạo chữ ký** hoặc một mốc thời gian được hợp đồng ký quy định. Nó không phải bằng chứng rằng request đã được gửi qua mạng đúng vào thời điểm đó: client có thể gửi trễ, request có thể chờ trong hàng đợi, hoặc proxy có thể giữ bản sao rồi phát lại.

Ví dụ:

~~~http
POST /v1/payments?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-42
X-Key-Id: key-2026-11
X-Timestamp: {epoch-seconds}
X-Nonce: {32-lowercase-hex-characters}
X-Content-SHA256: {sha256-body-hex}
X-Signature: {base64-hmac-tag}

{"orderId":"ord-123","amount":50000}
~~~

Các giá trị trong ngoặc nhọn là **placeholder**, không phải chữ ký hoặc timestamp để dùng nguyên văn. Giá trị thật của `X-Timestamp` được tạo lúc client ký request. HMAC bảo vệ **chính chuỗi timestamp** khi chuỗi đó được đưa vào canonical request.

| Dữ liệu | Chức năng | Có tự đủ chống replay không? |
| --- | --- | --- |
| Timestamp đã ký | Giới hạn thời gian server cho phép nhận request | **Không**: kẻ tấn công có thể phát lại trong cửa sổ còn hiệu lực. |
| Nonce đã ký | Phân biệt từng request được ký | **Không** nếu server không lưu những nonce đã chấp nhận. |
| Nonce store nguyên tử | Phát hiện nonce đã được dùng, kể cả hai request đồng thời | Cùng timestamp/nonce tạo lớp chống replay khi kết hợp kiểm tra HMAC. |
| Idempotency key | Nhận diện một thao tác nghiệp vụ xuyên các lần retry khác nonce | Cần thực thi riêng cho thao tác có tác dụng phụ. |
| HMAC signature | Chứng minh bên ký có khả năng sử dụng secret và bảo vệ các trường đã ký | Chữ ký đúng vẫn có thể được gửi lại nguyên văn. |

**Điểm quan trọng:** HMAC không cho phép proxy không biết secret tự sửa timestamp rồi giữ nguyên chữ ký, nhưng không ngăn proxy chuyển tiếp nguyên bản request trước khi hết hạn. Đồng hồ server, nonce store và idempotency phải được xem là các cơ chế riêng.

## 3. Chọn định dạng timestamp: phải có một biểu diễn duy nhất

Nhiều định dạng thời gian cùng mô tả một thời điểm:

~~~text
2026-11-28T09:00:00+07:00
2026-11-28T02:00:00Z
1795831200            // Giá trị ví dụ: Unix seconds
1795831200000         // Giá trị ví dụ: Unix milliseconds
~~~

Hai dòng ISO-8601 cùng chỉ một thời điểm, nhưng **byte khác nhau**. Số giây và số mili-giây lại khác nhau **1000 lần**. Nếu client ký một representation còn server dựng lại representation khác thì HMAC không khớp; nếu server tự đoán đơn vị từ độ dài chuỗi sẽ tăng nguy cơ diễn giải sai.

Bài này chọn hợp đồng minh họa có các quy tắc:

- `X-Timestamp` là **số nguyên Unix epoch seconds**, biểu thị số giây kể từ **1970-01-01T00:00:00Z**; UTC là mốc thời gian, **không** cần cộng/trừ múi giờ thủ công.
- Sử dụng ký tự **ASCII 0–9**, không dấu `+`, không dấu trừ, không phần thập phân, không dấu cách trước/sau, không dấu phân cách hàng nghìn và không có zero thừa ở đầu. Timestamp hợp lệ phải là một số nguyên dương dạng thập phân chính tắc.
- Định nghĩa độ dài bằng **quy tắc parse số nguyên 64 bit** và khoảng thời gian cho phép, **không** mặc định timestamp luôn có 10 chữ số: độ dài epoch seconds sẽ thay đổi theo thời gian.
- Verifier phải từ chối header thiếu, trùng lặp hoặc không đúng format; **không** sửa format rồi chấp nhận như giá trị tương đương.
- Giá trị canonical là **chuỗi ASCII nguyên vẹn đã qua kiểm tra định dạng** mà server nhận ở header, không phải kết quả gọi `toString()` trên một đối tượng ngày giờ được parse tùy ý.

| Dạng `X-Timestamp` | Theo hợp đồng ví dụ | Lý do |
| --- | --- | --- |
| `1795831200` | Có thể hợp lệ về **định dạng** | Chỉ chữ số, không zero đầu; vẫn phải kiểm tra cửa sổ thời gian. |
| `01795831200` | **Từ chối** | Có zero đầu, dù parse số học ra cùng thời điểm. |
| `1795831200.0` | **Từ chối** | Có phần thập phân. |
| `+1795831200` | **Từ chối** | Có dấu `+`. |
| `1795831200000` | Có thể parse nhưng thường **hết cửa sổ** | Đơn vị milliseconds bị nhầm thành seconds. |
| `2026-11-28T02:00:00Z` | **Từ chối** | Hợp đồng chỉ cho epoch seconds, không cho ISO-8601. |
| ` 1795831200 ` | **Từ chối** | Khoảng trắng ngoài định dạng. |
| Hai header `X-Timestamp` | **Từ chối** | Tránh proxy/backend chọn các giá trị khác nhau. |

Đây là một **hợp đồng tự định nghĩa để học**, không phải quy định bắt buộc của mọi HTTP signature. Một hệ thống khác có thể chọn RFC 3339/ISO-8601 với UTC cố định, hoặc timestamp theo mili-giây, nhưng khi đó cần quy định chuẩn hóa, độ chính xác, timezone, parser và byte encoding **đúng một cách**. Không trộn hợp đồng này với giao thức khác mà không có thỏa thuận.

### 3.1. Cách tạo epoch seconds trong Java

~~~java
import java.time.Clock;
import java.time.Instant;

String timestamp = Long.toString(Instant.now().getEpochSecond());

// Khuyến khích inject Clock để viết test xác định:
static String canonicalTimestamp(Clock clock) {
    return Long.toString(clock.instant().getEpochSecond());
}
~~~

`Instant.now().getEpochSecond()` trả số giây theo mốc UTC. Không chuyển `LocalDateTime.now()` thành epoch bằng múi giờ hệ thống tùy ý, không ghép ngày/giờ thủ công, không sử dụng `System.currentTimeMillis()` mà quên chia 1000 **nếu** hợp đồng đang yêu cầu seconds.

**Lưu ý vận hành:** thời gian không nên lấy từ kết quả phản hồi của một proxy không tin cậy rồi xem là nguồn đồng bộ đã xác thực. Client cần đồng hồ hệ thống được đồng bộ bằng cơ chế thời gian đáng tin; server dùng đồng hồ của chính nó để kiểm tra freshness. Sử dụng `long` thay `int` để không bị tràn giới hạn epoch seconds kiểu 32 bit vào năm 2038.

## 4. Đưa timestamp vào canonical request như thế nào?

Giả sử hợp đồng ký bảo vệ toàn bộ các trường sau:

~~~text
HMAC-TIMESTAMP-V1
POST
/v1/payments?currency=VND
audience:payments-api
x-client-id:partner-42
x-key-id:key-2026-11
x-timestamp:<epoch-seconds>
x-nonce:<32-lowercase-hex-characters>
content-type:application/json
x-content-sha256:<64-lowercase-hex-characters>
~~~

**HMAC-TIMESTAMP-V1** là marker phiên bản, không phải một chuẩn do JDK hay HTTP tự áp đặt. Hợp đồng này quy định mỗi dòng được nối bằng **LF (byte 0A)**, **không có LF ở cuối**. Tất cả chuỗi chuyển thành byte **UTF-8** trước khi tính HMAC-SHA256.

~~~text
bodyHash  = lowerHex(SHA256(bodyBytes))
canonical = JoinWithLF(method, rawTarget, signedHeaders, bodyHash)
signature = Base64(HMAC_SHA256(secretBytes, UTF8(canonical)))
~~~

Quy tắc bảo vệ của từng thành phần:

| Thành phần | Nguồn lấy giá trị | Tác dụng |
| --- | --- | --- |
| Method | Method thực nhận và được thực thi | Phát hiện đổi POST thành DELETE hoặc GET. |
| Raw request target | Raw path + raw query của request theo contract | Phát hiện sửa endpoint, account ID hoặc query. |
| Audience | Cấu hình dịch vụ phải xử lý request | Ngăn dùng một chữ ký ở dịch vụ ngoài phạm vi key. |
| Client ID và key ID | Header đã kiểm tra, ràng buộc key store | Chọn secret đúng client, đúng key rotation. |
| **Timestamp** | **Giá trị X-Timestamp chính tắc từ request** | Ngăn sửa thời điểm ký mà vẫn giữ tag HMAC hợp lệ. |
| Nonce | Giá trị từ header đã kiểm tra format | Cho server phát hiện replay. |
| Content-Type và body hash | Header thực nhận và SHA-256 của body bytes thực nhận | Bảo vệ cách diễn giải body và nội dung body. |

Ví dụ một proxy thay `X-Timestamp: 1795831200` thành `X-Timestamp: 1795831300`. Nếu verifier tự dựng canonical từ header thực nhận, **HMAC khác** và request bị từ chối. Nếu client chỉ ký body hash mà bỏ timestamp khỏi canonical, proxy có thể tự đẩy thời điểm về sau để gia hạn tuổi thọ request.

Không nên “chữa” signature mismatch bằng cách bỏ timestamp ra khỏi chữ ký, chuẩn hóa mọi kiểu timestamp về một số rồi thử nhiều canonical thay thế hoặc tin một header `X-Verified: true` từ proxy. Các cách đó mở thêm bề mặt cho bên ngoài điều khiển.

### 4.1. Signed timestamp và HTTP Date header

Header `Date` trong HTTP hoặc đồng hồ gateway **không tự thay thế** `X-Timestamp` đã được ký. Nếu dùng `Date` làm trường được ký thì phải định nghĩa chính xác định dạng HTTP-date và cách chuẩn hóa, cũng như cách xử lý các hop có thể sửa header. Trong hợp đồng minh họa, `X-Timestamp` là trường duy nhất dùng cho freshness; không suy luận từ một header khác chưa được HMAC bảo vệ.

### 4.2. Các chi tiết byte vẫn phải thống nhất

- Tên header canonical viết chữ thường `x-timestamp`; giá trị là chuỗi số thập phân chính tắc, không tự trim hoặc thêm khoảng trắng.
- Giá trị header thực tế `X-Timestamp` được gửi **chỉ một lần**; HTTP header names vốn không phân biệt hoa/thường, nhưng giao thức phải từ chối hai tên khác nhau về case mà cùng biểu thị một trường.
- Không cho phép CR/LF trong giá trị header nhằm tránh nhập nhằng ranh giới dòng.
- Raw path, percent-encoding, thứ tự query và body encoding có quy tắc riêng. Timestamp ký đúng không cứu được lỗi bỏ query hay body ra khỏi canonical.
- Trường `X-Signature` mang tag **không** được đưa vào chính dữ liệu nó ký. Với HMAC-SHA256 full tag 32 byte, Base64 chuẩn có padding thường có 44 ký tự.

## 5. Kiểm tra thời gian: “quá cũ” và “quá sớm”

Verifier phải có **chính sách freshness**. Một ví dụ minh họa có hai ngưỡng khác nhau:

~~~text
pastWindow   = 300 giây
futureWindow =  60 giây

accepted nếu:
    serverNow - 300 <= signedTimestamp <= serverNow + 60
~~~

Diễn giải: một request có timestamp cũ hơn đồng hồ server tối đa **5 phút** hoặc đi trước tối đa **1 phút** có thể vượt bước kiểm tra thời gian. Các ngưỡng chỉ là **ví dụ cấu hình ứng dụng**, không phải thông số mặc định bắt buộc của HMAC.

| So với thời điểm server là T | Kết quả freshness |
| --- | --- |
| T − 301 giây | Từ chối: quá cũ |
| T − 300 giây | Chấp nhận về thời gian, còn phải kiểm tra HMAC/nonce/quyền |
| T | Chấp nhận về thời gian |
| T + 60 giây | Chấp nhận về thời gian |
| T + 61 giây | Từ chối: quá xa trong tương lai |

Không được dùng đồng hồ client để quyết định giá trị `serverNow`, vì client là phía không tin cậy. Server so sánh thời điểm hiện tại do nó quan sát với timestamp đã ký và đã kiểm tra format. Nếu nhiều node verifier có đồng hồ lệch nhau, request có thể được node này chấp nhận nhưng node khác từ chối; cần đồng bộ thời gian và giám sát sai lệch tại toàn bộ cụm.

**Cửa sổ càng rộng**, request đã ký càng có thể được phát lại trong thời gian dài nếu thiếu nonce store. **Cửa sổ quá hẹp** dễ khiến yêu cầu hợp lệ bị từ chối khi mạng chậm hoặc đồng hồ lệch. Cần chọn cân bằng theo độ trễ thực tế, cấu hình retry, số tầng gateway, độ ổn định đồng hồ và tính nhạy cảm của nghiệp vụ.

### 5.1. Vì sao không chỉ kiểm tra HMAC?

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Proxy giữ bản sao
    participant V as Verifier
    C->>P: POST + timestamp=T + nonce=N + HMAC hợp lệ
    P->>V: Forward request
    V-->>P: Xác minh HMAC và xử lý
    P->>V: Phát lại nguyên request trong cửa sổ
    Note over V: Chữ ký vẫn đúng, timestamp vẫn chưa hết hạn
    V-->>P: Chỉ có nonce store mới chặn lần phát lại
~~~

Nếu server chỉ kiểm tra timestamp mà không ghi lại nonce, bản sao request **vẫn có HMAC hợp lệ** ở lần thứ hai. Timestamp chỉ thu hẹp khoảng tấn công; nonce đã ký, khi kết hợp claim nguyên tử tại server, mới giúp nhận diện bản sao.

## 6. Timestamp, nonce và thời hạn lưu replay state

Nonce nên là giá trị **ngẫu nhiên mới** được client tạo cho từng lần ký, ví dụ 16 byte (128 bit) từ `SecureRandom` và encode thành 32 ký tự hex chữ thường. Bảo vệ cả `x-timestamp` lẫn `x-nonce` bằng cùng HMAC.

Luồng verifier tham khảo:

~~~mermaid
flowchart TD
    A["Nhận request tại trust boundary đáng tin"] --> B["Kiểm tra format timestamp/nonce và các signed fields"]
    B --> C{"Timestamp trong cửa sổ?"}
    C -->|Không| X["Từ chối"]
    C -->|Có| D["Chọn secret theo client ID + key ID"]
    D --> E["Dựng canonical, hash body, tính lại HMAC"]
    E --> F{"HMAC hợp lệ?"}
    F -->|Không| X
    F -->|Có| G{"Claim nonce nguyên tử?"}
    G -->|Đã tồn tại| X
    G -->|Mới| H["Authorize + idempotency + nghiệp vụ"]
~~~

**Phải claim nonce sau khi xác minh HMAC hợp lệ.** Nếu ghi nhận nonce của request giả chưa xác thực, kẻ tấn công có thể cố chiếm trước nonce của client hoặc làm cạn replay store. Các bước parse và kiểm tra freshness có thể thực hiện trước HMAC để giảm chi phí; nhưng không được tin danh tính client hoặc thực hiện side effect trước khi HMAC được kiểm tra.

### 6.1. TTL của nonce không được tính tùy tiện

Với chính sách ở mục 5, request có timestamp \(S\) còn được coi là không quá cũ khi serverNow nhỏ hơn hoặc bằng \(S + 300\) giây. Nếu request lần đầu đến lúc timestamp **đi trước đồng hồ server 60 giây**, nó có thể tiếp tục nằm trong cửa sổ **khoảng 360 giây nữa**.

Vì vậy lưu nonce một thời hạn cố định **60 giây kể từ khi nhận** là không đủ. Quy tắc dễ kiểm tra hơn là:

~~~text
nonceExpiryEpochSeconds = signedTimestamp + pastWindow + safetyMargin

Ví dụ:
pastWindow = 300 giây
futureWindow = 60 giây
safetyMargin = 30 giây

Nonce được giữ tới khi timestamp đó hết cửa sổ được chấp nhận
và thêm một biên độ vận hành theo chính sách.
~~~

Nếu store nhận TTL tương đối tính từ lúc claim, cần tính thời hạn còn lại từ **serverNow** tới `nonceExpiryEpochSeconds`, đồng thời bảo đảm TTL dương và thao tác ghi là nguyên tử. Nếu dùng expiry tuyệt đối thì phải thống nhất nguồn thời gian và ngữ nghĩa expiry của storage. Trong hệ thống phân tán, Redis với lệnh đặt giá trị **chỉ khi chưa có** và expiry phù hợp, hoặc database có unique constraint, có thể hỗ trợ claim nguyên tử. Một `HashSet` cục bộ của từng replica là **không đủ**.

Khóa nonce store cần ràng buộc với identity đã xác thực, ví dụ `(clientId, nonce)`, và chính sách phải xác định nonce có thể tái sử dụng giữa các phiên bản key hay không. Nếu lưu theo `(clientId, keyId, nonce)`, cùng nonce có thể được chấp nhận lại dưới key version khác; với giao dịch nhạy cảm nên cân nhắc namespace nonce theo client xuyên các key đang active, và **luôn** dùng idempotency key để xử lý trùng tác dụng phụ giữa các request được ký mới.

### 6.2. Timestamp không phải idempotency

Giả sử client gửi một POST thanh toán và server đã trừ tiền, nhưng kết nối bị mất trước khi response tới client. Client tạo **timestamp mới và nonce mới**, ký lại cùng nghiệp vụ. Hai chữ ký đều hợp lệ và hai nonce đều mới. Replay detector không thể biết đây là **một ý định thanh toán lặp lại** nếu thiếu một cơ chế nghiệp vụ.

Cần **idempotency key** do client dùng nhất quán cho cùng một ý định nghiệp vụ, được ràng buộc trong canonical request và server xử lý nguyên tử theo chính sách. Timestamp/nonce xác thực **mỗi lần truyền đã ký**, idempotency key ràng buộc **một thao tác nghiệp vụ**.

## 7. Java 17: ký timestamp chính tắc và xác minh theo Clock

Chương trình sau minh họa client và verifier trong **cùng một tiến trình test**, cùng một secret test được tạo bằng `SecureRandom`. Nó tạo `HttpRequest` để minh họa các header nhưng **không gửi ra mạng**. Các bước kiểm tra HTTP parsing, key store, nonce TTL và phân quyền ở production sẽ được bổ sung bên ngoài ví dụ.

Để dễ kiểm thử, chương trình inject `Clock.fixed` thay vì phụ thuộc đồng hồ thật. Nó xác minh một request hợp lệ, phát hiện replay và từ chối timestamp vượt cửa sổ.

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.HexFormat;
import java.util.concurrent.ConcurrentHashMap;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class CanonicalTimestampExample {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String CLIENT_ID = "partner-42";
    private static final String KEY_ID = "key-2026-11";
    private static final String TARGET = "/v1/payments?currency=VND";
    private static final String CONTENT_TYPE = "application/json";
    private static final long PAST_SECONDS = 300L;
    private static final long FUTURE_SECONDS = 60L;
    private static final long NONCE_MARGIN_SECONDS = 30L;

    record SignedRequest(
        String method, String target, String clientId, String keyId,
        String timestamp, String nonce, String bodyHash,
        String signature, byte[] body
    ) {}

    interface NonceStore {
        boolean claim(String clientId, String nonce, long expiresAtEpochSeconds);
    }

    // Chỉ dùng cho ví dụ một JVM: không tự dọn TTL, không chia sẻ giữa node.
    static final class DemoNonceStore implements NonceStore {
        private final ConcurrentHashMap<String, Long> claims =
            new ConcurrentHashMap<>();

        @Override
        public boolean claim(String clientId, String nonce,
                long expiresAtEpochSeconds) {
            return claims.putIfAbsent(
                clientId + ":" + nonce, expiresAtEpochSeconds
            ) == null;
        }
    }

    static SignedRequest sign(byte[] secret, Clock clientClock)
            throws GeneralSecurityException {
        byte[] body = "{\"orderId\":\"ord-123\",\"amount\":50000}"
            .getBytes(StandardCharsets.UTF_8);
        String timestamp = Long.toString(
            clientClock.instant().getEpochSecond()
        );
        byte[] nonceBytes = new byte[16]; // 128 bit
        RANDOM.nextBytes(nonceBytes);
        String nonce = HexFormat.of().formatHex(nonceBytes);
        String bodyHash = sha256Hex(body);

        String canonical = canonical(
            "POST", TARGET, CLIENT_ID, KEY_ID,
            timestamp, nonce, bodyHash
        );
        String signature = Base64.getEncoder().encodeToString(
            hmac(secret, canonical.getBytes(StandardCharsets.UTF_8))
        );
        return new SignedRequest(
            "POST", TARGET, CLIENT_ID, KEY_ID,
            timestamp, nonce, bodyHash, signature, body
        );
    }

    static String canonical(String method, String target, String clientId,
            String keyId, String timestamp, String nonce, String bodyHash) {
        return String.join("\n",
            "HMAC-TIMESTAMP-V1",
            method,
            target,
            "audience:payments-api",
            "x-client-id:" + clientId,
            "x-key-id:" + keyId,
            "x-timestamp:" + timestamp,
            "x-nonce:" + nonce,
            "content-type:" + CONTENT_TYPE,
            "x-content-sha256:" + bodyHash
        );
    }

    static String sha256Hex(byte[] body)
            throws GeneralSecurityException {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(body);
        return HexFormat.of().formatHex(digest);
    }

    static byte[] hmac(byte[] secret, byte[] message)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(message);
    }

    static boolean verify(SignedRequest req, byte[] secret,
            Clock serverClock, NonceStore nonceStore)
            throws GeneralSecurityException {
        // Production cần đọc các field từ HTTP request thực nhận, chặn
        // duplicate header/CRLF, kiểm tra raw target, Content-Type và audience.
        if (!"POST".equals(req.method()) || !TARGET.equals(req.target()) ||
            !CLIENT_ID.equals(req.clientId()) ||
            !KEY_ID.equals(req.keyId()) ||
            req.timestamp() == null ||
            !req.timestamp().matches("[1-9][0-9]{0,18}") ||
            req.nonce() == null || !req.nonce().matches("[0-9a-f]{32}") ||
            req.bodyHash() == null ||
            !req.bodyHash().matches("[0-9a-f]{64}") ||
            req.signature() == null || req.body() == null) {
            return false;
        }

        final long signedSeconds;
        try {
            signedSeconds = Long.parseLong(req.timestamp());
        } catch (NumberFormatException invalidOrOverflow) {
            return false;
        }

        long serverNow = serverClock.instant().getEpochSecond();
        if (signedSeconds < serverNow - PAST_SECONDS ||
            signedSeconds > serverNow + FUTURE_SECONDS) {
            return false;
        }

        String computedBodyHash = sha256Hex(req.body());
        if (!computedBodyHash.equals(req.bodyHash())) {
            return false;
        }

        final byte[] suppliedTag;
        try {
            suppliedTag = Base64.getDecoder().decode(req.signature());
        } catch (IllegalArgumentException invalidBase64) {
            return false;
        }
        if (suppliedTag.length != 32 ||
            !Base64.getEncoder().encodeToString(suppliedTag)
                .equals(req.signature())) {
            return false;
        }

        String canonical = canonical(
            req.method(), req.target(), req.clientId(), req.keyId(),
            req.timestamp(), req.nonce(), computedBodyHash
        );
        byte[] expectedTag = hmac(
            secret, canonical.getBytes(StandardCharsets.UTF_8)
        );
        if (!MessageDigest.isEqual(expectedTag, suppliedTag)) {
            return false;
        }

        // Việc claim này phải là atomic insert-if-absent có TTL dùng chung
        // giữa replica trong ứng dụng thật.
        long expiresAt = signedSeconds +
            PAST_SECONDS + NONCE_MARGIN_SECONDS;
        return nonceStore.claim(req.clientId(), req.nonce(), expiresAt);
    }

    public static void main(String[] args) throws Exception {
        byte[] sharedSecret = new byte[32]; // Secret test; không dùng production.
        RANDOM.nextBytes(sharedSecret);
        Clock fixed = Clock.fixed(
            Instant.parse("2026-11-28T09:00:00Z"), ZoneOffset.UTC
        );
        SignedRequest req = sign(sharedSecret, fixed);

        HttpRequest httpRequest = HttpRequest.newBuilder(
                URI.create("https://api.example.test" + req.target()))
            .header("Content-Type", CONTENT_TYPE)
            .header("X-Client-Id", req.clientId())
            .header("X-Key-Id", req.keyId())
            .header("X-Timestamp", req.timestamp())
            .header("X-Nonce", req.nonce())
            .header("X-Content-SHA256", req.bodyHash())
            .header("X-Signature", req.signature())
            .POST(HttpRequest.BodyPublishers.ofByteArray(req.body()))
            .build();

        DemoNonceStore nonceStore = new DemoNonceStore();
        if (!verify(req, sharedSecret, fixed, nonceStore)) {
            throw new AssertionError("Request mới phải được chấp nhận");
        }
        if (verify(req, sharedSecret, fixed, nonceStore)) {
            throw new AssertionError("Replay cùng nonce phải bị từ chối");
        }
        Clock late = Clock.offset(fixed, Duration.ofSeconds(301));
        if (verify(req, sharedSecret, late, new DemoNonceStore())) {
            throw new AssertionError("Timestamp quá cũ phải bị từ chối");
        }
        SignedRequest future = sign(
            sharedSecret, Clock.offset(fixed, Duration.ofSeconds(61))
        );
        if (verify(future, sharedSecret, fixed, new DemoNonceStore())) {
            throw new AssertionError("Timestamp quá xa tương lai phải bị từ chối");
        }

        System.out.println("PASS: " + httpRequest.method()
            + " / canonical timestamp, freshness, nonce");
    }
}
~~~

**Điểm cần hiểu trước khi tích hợp:**

- `Clock` cho phép tạo test xác định ở cả client và server. Trong production, inject clock hệ thống được đồng bộ, không dùng `Clock.fixed` cho request thật.
- `Instant.getEpochSecond()` sinh chuỗi Unix seconds, tránh sai đơn vị milliseconds và timezone.
- Regex `[1-9][0-9]{0,18}` chặn zero đầu, dấu, phần thập phân; `Long.parseLong` phát hiện số vượt miền `long`. Sau đó **freshness check** còn từ chối giá trị không thuộc cửa sổ chấp nhận.
- Verifier tự tính SHA-256(body), dựng lại canonical và tính HMAC; `MessageDigest.isEqual` so sánh **byte tag**. HMAC-SHA256 full tag 32 byte được Base64 encode đúng quy tắc.
- `DemoNonceStore` dùng `putIfAbsent` để mô phỏng atomic claim trong **một JVM**; nó không xóa dữ liệu khi hết TTL và không bảo vệ giữa các replica. Production bắt buộc dùng storage chung có TTL/unique key phù hợp.
- `SignedRequest` là đối tượng test, chưa phải HTTP parser an toàn. Code thực tế phải lấy method, raw URI, signed header và body từ **request thực nhận**, không tin object do client chuyển trực tiếp. Cần kiểm tra Content-Type, signed-header duplication, CR/LF, body size và audience tại trust boundary.
- Ví dụ tạo `HttpRequest`, nhưng không gửi mạng; khi gửi thật cần kiểm thử đường đi qua HTTP client, proxy và gateway để bảo đảm **raw request target** giống biểu diễn được ký.

## 8. Retry, clock skew, proxy và key rotation

### 8.1. Đồng hồ và độ trễ

Client nên lấy timestamp **sát thời điểm ký và gửi**, không tái sử dụng request đã ký trong hàng đợi dài. Khi request chờ quá cửa sổ, client phải **tạo timestamp mới, nonce mới và ký lại**. Proxy không có shared secret không thể gia hạn thời gian hợp lệ bằng cách sửa mỗi timestamp.

Nếu server trả lỗi timestamp ngoài cửa sổ, cần kiểm tra đồng hồ client/server, độ trễ, timezone và đơn vị giây/mili-giây. Không nên “nới cửa sổ vô hạn” để hết lỗi vì như vậy kéo dài thời gian replay. Theo dõi drift bằng đồng hồ đáng tin và chỉ cho phép ngoại lệ trong chính sách có kiểm soát.

### 8.2. Proxy/gateway có thể phá tính nhất quán của canonical request

| Tình huống | Rủi ro | Biện pháp |
| --- | --- | --- |
| Gateway thêm, xóa hoặc ghi đè `X-Timestamp` | Chữ ký sai hoặc nguồn timestamp bị tráo | Bảo toàn trường đã ký; không lấy timestamp do gateway tự thay làm dữ liệu client đã ký. |
| Hai header `X-Timestamp` khác nhau | Gateway chọn giá trị đầu, backend chọn giá trị cuối | Từ chối header trùng/không duy nhất tại điểm đáng tin. |
| Proxy đổi raw path `%2F` thành `/` hoặc sắp xếp query | Canonical khác hoặc route được xử lý khác | Verify trước rewrite tại ingress đáng tin hoặc truyền metadata gốc qua kênh được xác thực. |
| HTTP/1.1 qua HTTP/2 | Header name, Host/`:authority`, `:path` có thể được tái biểu diễn | Quy định rõ canonical fields, thực nghiệm trên stack thật và từ chối trường mơ hồ. |
| Gateway tự parse ISO date hoặc trim giá trị timestamp | Client/server ký khác byte | Chỉ chấp nhận canonical format đã công bố; không tự chuẩn hóa nhiều biến thể. |
| Proxy giữ request vài phút | Timestamp hết cửa sổ | Từ chối request quá cũ; client retry bằng timestamp/nonce và HMAC mới. |
| Gateway tin `X-Verified: true` từ ngoài | Bỏ qua xác minh thực tế | Xóa header ngoài boundary; gateway→backend phải xác thực, chặn đường gọi trực tiếp. |

**Timestamp đã ký** không sửa được lỗi một thành phần khác **không được ký**. Nếu body hoặc query ảnh hưởng nghiệp vụ mà bị bỏ khỏi canonical, proxy có thể thay chúng trong khi timestamp và HMAC vẫn hợp lệ. Hợp đồng phải bảo vệ đúng những dữ liệu mà router và backend sử dụng.

### 8.3. Key rotation và timestamp

Client và server phải dùng đúng **secret tương ứng với key ID** để ký và xác minh. Key ID nên nằm trong canonical để proxy không thay key selection mà vẫn giữ chữ ký. Trong giai đoạn rotation, verifier có thể chấp nhận key cũ và mới theo policy thời hạn hiệu lực. **Timestamp không tự gia hạn hiệu lực của key đã thu hồi**: một chữ ký có timestamp còn mới nhưng dùng key đã bị revoke vẫn phải bị từ chối.

Một yêu cầu được ký trước thời điểm key hết hạn nhưng đến server **sau** thời hạn hiệu lực cần có quy tắc rõ (ví dụ kiểm tra key vẫn được phép tại thời điểm server xác minh, có grace period có kiểm soát). Không chấp nhận request tùy ý bằng khóa cũ chỉ vì client khai báo timestamp “trong quá khứ”. Rotation và thu hồi do **policy server** quyết định.

### 8.4. Xác thực khác phân quyền

HMAC và timestamp giúp verifier tin rằng request chưa bị sửa ở các trường đã ký, được tạo bởi bên có khả năng sử dụng secret và còn trong cửa sổ thời gian. Chúng **không cho phép** client thao tác mọi tài khoản, tenant hoặc endpoint. Sau authentication, backend phải kiểm tra **authorization** theo danh tính client, scope, action và tài nguyên, rồi mới xử lý nghiệp vụ.

## 9. Ma trận kiểm thử canonical timestamp

Hãy tạo một signer và verifier test có shared secret riêng. Inject clock giả lập để kiểm tra chính xác các điểm biên thay vì phụ thuộc thời gian thực. Mỗi ca độc lập dùng nonce mới; các ca replay **cố ý dùng lại cùng nonce**.

| Ca thử | Dữ liệu/thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Timestamp hợp lệ | Unix seconds chính tắc, bằng đồng hồ server | Vượt freshness check; còn phải kiểm tra HMAC, nonce và quyền. |
| Biên quá khứ | Signed timestamp = T − 300 giây | Được chấp nhận **theo cấu hình ví dụ**. |
| Quá cũ | Signed timestamp = T − 301 giây | Từ chối. |
| Biên tương lai | Signed timestamp = T + 60 giây | Được chấp nhận **theo cấu hình ví dụ**. |
| Quá xa tương lai | Signed timestamp = T + 61 giây | Từ chối. |
| Seconds vs milliseconds | Gửi `System.currentTimeMillis()` vào trường seconds | Từ chối do không thuộc cửa sổ; không tự chia 1000 tại server. |
| ISO date thay epoch seconds | `2026-11-28T09:00:00+07:00` | Từ chối vì sai format của contract. |
| Zero đầu, khoảng trắng, dấu hoặc số thập phân | `01795831200`, `+1795831200`, `1795831200.0` | Từ chối format, không normalize rồi verify. |
| Timestamp vượt miền long | Chuỗi số cực dài | Từ chối khi kiểm tra định dạng/parse, không crash. |
| Timestamp bị sửa sau khi ký | Đổi X-Timestamp nhưng giữ tag cũ | HMAC sai, từ chối. |
| Header trùng | Hai giá trị X-Timestamp, khác chữ hoa tên header | Từ chối request mơ hồ trước xác minh. |
| Replay tuần tự | Gửi nguyên request và nonce lần hai trong cửa sổ | Lần hai bị từ chối do nonce đã claim. |
| Replay đồng thời | Cùng request tới hai replica | Chỉ tối đa một atomic claim thành công. |
| Nonce TTL ngắn | Nonce hết TTL trong khi timestamp vẫn hợp lệ | Test phải phát hiện lỗ hổng; TTL cần bao phủ toàn bộ thời gian chấp nhận. |
| Client clock drift | Đồng hồ client chậm hơn hoặc nhanh hơn ngưỡng | Từ chối có phân loại lỗi an toàn, giám sát drift và đồng bộ giờ. |
| Retry sau response bị mất | Client ký lại timestamp/nonce mới với cùng idempotency key | HMAC hợp lệ; tầng nghiệp vụ không thực thi giao dịch hai lần. |
| Key đã thu hồi | Timestamp hợp lệ nhưng key ID revoked | Từ chối theo key policy. |
| Proxy rewrite | Gateway đổi query, path hoặc Content-Type đã ký | Không được bỏ qua signature mismatch; kiểm tra tại boundary phù hợp. |
| Chữ ký hợp lệ, thiếu quyền | Client gọi tài nguyên tenant khác | Authentication PASS, authorization DENY. |

### Câu hỏi tự kiểm tra

1. Vì sao `X-Timestamp: 01795831200` có thể biểu thị cùng số giây với `1795831200` nhưng lại bị từ chối trong hợp đồng ký mẫu?
2. Tại sao verifier phải dùng **server clock** thay vì chấp nhận thời gian do client tự cung cấp để quyết định request còn mới?
3. Timestamp 5 phút có đủ chặn việc proxy phát lại cùng request hai lần trong vòng 10 giây không? Cần thêm cơ chế gì?
4. Nếu cho phép request có timestamp đi trước server 60 giây và quá khứ tối đa 300 giây, tại sao TTL nonce 60 giây lại không đủ?
5. Khi client retry một POST thanh toán bằng nonce mới, vì sao idempotency key vẫn cần thiết?
6. Server có thể sửa timestamp mà vẫn giữ chữ ký cũ để làm request qua kiểm tra thời gian không? Tại sao?
7. Một client ký hợp lệ request DELETE của tenant khác thì có được thực thi không? Kiểm tra nào quyết định?

## 10. Checklist triển khai

- [ ] Hợp đồng ký quy định **đúng một** format timestamp, đơn vị (seconds/milliseconds), charset và cách đưa giá trị vào canonical.
- [ ] Timestamp nằm trong **phần được HMAC bảo vệ** cùng method, raw URI, các signed header và body bytes/hash cần thiết.
- [ ] Parser từ chối khoảng trắng, dấu, zero đầu, số thập phân, chuỗi quá dài, overflow và header timestamp trùng theo policy.
- [ ] Client sử dụng thời gian UTC/Unix đúng đơn vị, tạo timestamp sát lúc ký/gửi và đồng bộ đồng hồ đáng tin.
- [ ] Server dùng **đồng hồ server** và kiểm tra cả **quá khứ** lẫn **tương lai** với giới hạn đã công bố.
- [ ] Timestamp và nonce đều được ký; nonce mới đủ ngẫu nhiên; server chỉ claim nonce sau khi HMAC hợp lệ.
- [ ] Nonce store dùng chung giữa replica, có atomic insert-if-absent và expiry bao phủ **đến cuối cửa sổ timestamp** cộng safety margin.
- [ ] Retry thao tác có side effect sử dụng **idempotency key được ký** và cơ chế nghiệp vụ chống trùng.
- [ ] Key ID được ký, key rotation/thu hồi được server kiểm soát; không coi timestamp còn mới là lý do chấp nhận key revoked.
- [ ] Proxy/gateway không làm thay đổi dữ liệu đã ký; xác minh ở trust boundary đáng tin và chặn forwarded/verified header giả mạo.
- [ ] HTTPS, rate limit, giám sát clock skew và phân quyền được triển khai riêng, không nhầm timestamp/HMAC với cơ chế cấp quyền.

**Ghi nhớ:** **Canonical timestamp** phải là một giá trị thời gian **có format byte duy nhất, được HMAC ký và được verifier kiểm tra bằng đồng hồ server**. Nó giới hạn tuổi thọ request, nhưng chỉ **nonce store nguyên tử** mới phát hiện replay của request còn hạn; **idempotency** ngăn tác dụng phụ lặp khi retry. Key rotation, proxy/gateway và authorization phải có chính sách độc lập phù hợp với hợp đồng ký.
