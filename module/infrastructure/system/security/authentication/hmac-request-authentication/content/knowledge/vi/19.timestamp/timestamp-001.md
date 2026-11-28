# Timestamp request: Ràng buộc thời gian vào chữ ký HMAC của HTTP request

Một HTTP request có **HMAC đúng** vẫn có thể không an toàn để thực thi: kẻ quan sát được request hợp lệ có thể gửi lại **nguyên method, URI, headers, body và signature**. Vì HMAC là phép tính xác định, server sẽ tính lại cùng MAC. **Timestamp request** giúp server đặt giới hạn về thời điểm một request đã ký còn được chấp nhận; khi đi cùng **nonce dùng một lần**, nó trở thành một phần thiết yếu của cơ chế chống replay.

Trong module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, chúng ta thiết kế xác thực HTTP request bằng **shared secret** và **canonical request** gồm phương thức, URI, header hoặc body theo hợp đồng ký; thực hành xác minh signature, chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt **authentication** với **authorization**. Bài này thuộc chương **Timestamp**, tập trung vào **giá trị thời gian được client gắn vào request, được HMAC bảo vệ và được server kiểm tra**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nêu mục đích của timestamp request trong xác thực HMAC; phân biệt **freshness** với bảo đảm **không phát lại**.
2. Chọn một định dạng thời gian **UTC có phiên bản** và giải thích rủi ro của timezone, mili-giây/giây, định dạng text, leap second, clock skew.
3. Đưa timestamp vào **canonical request được ký**, không tin timestamp do client khai ở ngoài chữ ký.
4. Xây policy **cửa sổ chấp nhận** có biên quá khứ/tương lai rõ ràng, dùng đồng hồ server và kiểm thử đúng các ranh giới.
5. Kết hợp timestamp với nonce ngẫu nhiên, claim nguyên tử và **nonce TTL đủ dài** trong hệ thống nhiều node.
6. Viết ví dụ Java 17 dùng `Instant`, `Clock`, `DateTimeFormatter`/`ChronoUnit`, `SecureRandom`, `Mac` và `MessageDigest.isEqual`.
7. Chẩn đoán lỗi timestamp khác lỗi HMAC, key rotation, lỗi gateway, 401 và lỗi authorization 403.

## 2. Timestamp request là gì?

**Timestamp request** là một giá trị thời gian do **bên gửi** gắn vào HTTP request tại lúc chuẩn bị/gửi, ví dụ:

```http
POST /v1/orders?channel=partner HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: partner-a-202611
X-Timestamp: 2026-11-28T02:00:00Z
X-Nonce: Zq8DxKtUokcwPGNj3d_yvQ
X-Signature: v1=<BASE64_FULL_HMAC_SHA256>

{"sku":"BK-42","quantity":2}
```

`X-Timestamp` là **một signed header** trong hợp đồng minh họa. Giá trị `2026-11-28T02:00:00Z` nghĩa là thời điểm **02:00 UTC**, tương đương **09:00 UTC+07:00** cùng ngày; chữ `Z` thể hiện UTC. Đây là thời gian do client **khai báo**, chưa tự đáng tin. Server chỉ được dùng nó để xét freshness **sau khi bảo đảm giá trị thuộc dữ liệu đã ký và MAC khớp**.

Phân biệt ba loại thời điểm:

| Giá trị | Ai cung cấp? | Mục đích | Có đáng tin để xác thực? |
| --- | --- | --- | --- |
| **Request timestamp** (`X-Timestamp`) | Client | Ràng buộc tuổi request và giới hạn replay window. | Chỉ sau khi **HMAC đúng** trên giá trị đã ký. |
| **Server receive time** (`Instant.now(clock)`) | Server/verifier | Mốc tin cậy để xét request cũ hay quá tương lai. | Phải dựa vào clock được cấu hình/đồng bộ phù hợp. |
| **Business timestamp** (`createdAt`, `paidAt`) | Backend/database hoặc hệ thống nghiệp vụ | Lưu thời điểm diễn ra sự kiện trong domain. | Không tự thay thế request timestamp hoặc nonce. |

**Không coi request timestamp là thời gian thực sự request được server nhận.** Một client có secret có thể tạo timestamp hơi ở tương lai trong giới hạn policy. Bản ghi `createdAt` của đơn hàng nên dùng thời điểm do backend tin cậy cấp, không lấy trực tiếp `X-Timestamp` làm nguồn thời gian nghiệp vụ.

## 3. Vì sao timestamp phải nằm trong dữ liệu HMAC?

Nếu server kiểm tra timestamp nhưng **không ký timestamp**, bên trung gian có thể thay giá trị thời gian mà giữ nguyên signature của method/URI/body. Khi đó một request cũ có thể được sửa `X-Timestamp` sang thời điểm mới mà MAC vẫn khớp.

Ví dụ **không an toàn**:

```text
canonical = method + "\n" + path + "\n" + SHA256(body)
# X-Timestamp không được ký
```

Kẻ phát lại có thể thay header `X-Timestamp` trên request đã ghi lại. Server tưởng request vừa được tạo vì timestamp mới, dù không ai biết secret đã ký lại MAC.

**Hợp đồng an toàn**:

```text
HMAC-SHA256-V1
orders-api-prod
POST
/v1/orders?channel=partner
content-type:application/json
x-key-id:partner-a-202611
x-timestamp:2026-11-28T02:00:00Z
x-nonce:Zq8DxKtUokcwPGNj3d_yvQ
sha256:<LOWERCASE_HEX_OF_SHA256_RAW_BODY>
```

Các chuỗi trong dấu `<...>` chỉ là **placeholder**, không phải digest dùng được. Khi bất kỳ ký tự nào trong `x-timestamp:...` thay đổi, **canonical bytes thay đổi** và HMAC tính trên chuỗi cũ không còn khớp.

HMAC phải bao gồm **timestamp và nonce cùng lúc**. Timestamp giới hạn tuổi request, nonce chống **lặp trong chính cửa sổ còn hợp lệ**. Ký timestamp mà bỏ nonce vẫn cho phép phát lại nguyên request trong vài phút.

## 4. Chọn một định dạng timestamp không nhập nhằng

Có nhiều cách biểu diễn thời gian: ISO 8601/RFC 3339, Unix epoch seconds, Unix epoch milliseconds hoặc HTTP-date. Không có một định dạng chung bắt buộc cho tất cả HMAC API; **client và server phải công bố cùng một format**, rồi ký chính xác bytes của giá trị đó.

### 4.1. V1 của bài: UTC đến độ chính xác giây

Quy ước minh họa:

```text
YYYY-MM-DDTHH:mm:ssZ
Ví dụ: 2026-11-28T02:00:00Z
```

- Luôn dùng **UTC**, ký tự `Z` viết hoa.
- Bắt buộc có hai chữ số cho tháng, ngày, giờ, phút, giây; ngày phải hợp lệ.
- **Không cho phép** fractional seconds như `.123Z` trong V1.
- Không cho phép `+00:00` hay `+07:00` dù có thể mô tả **cùng một instant**.
- Không dùng timezone tên vùng như `Asia/Ho_Chi_Minh` trong header.
- Parser phải từ chối giá trị không hợp lệ; có thể parse `Instant` rồi **format lại và so chính xác với input** để từ chối dạng không canonical.

Hai chuỗi mô tả cùng thời điểm:

```text
2026-11-28T02:00:00Z
2026-11-28T09:00:00+07:00
```

Nếu client ký chuỗi đầu nhưng server **thay value thành chuỗi thứ hai trước khi dựng canonical request**, HMAC sẽ khác. Đừng nhầm “cùng thời điểm” với “cùng bytes được ký”. V1 chọn dạng đầu và từ chối dạng sau thay vì tự normalize value.

### 4.2. Nếu chọn Unix epoch thì sao?

Một giao thức khác có thể dùng `X-Timestamp: 1795831200` dưới dạng **epoch seconds**. Với hệ thống có milliseconds, `1795831200000` là con số cùng mốc nhưng khác đơn vị và độ dài. Sai đơn vị có thể khiến request trông “ở tương lai hàng chục nghìn năm” hoặc “quá cũ”.

Nếu chọn epoch, contract cần chỉ rõ:

1. **Đơn vị**: giây hay milli-giây?
2. Dạng decimal ASCII không có dấu `+`, không có leading zeros hay dấu phẩy/space?
3. Giá trị âm có được chấp nhận không?
4. Độ rộng, khoảng năm và cách xử lý overflow.
5. Phép so cửa sổ **inclusive/exclusive** và chính sách clock skew.

Bài này chọn UTC text để học và đọc test vector dễ hơn; không trộn epoch vào cùng signature version.

### 4.3. Java time API nên dùng gì?

| API | Công dụng | Cảnh báo |
| --- | --- | --- |
| `Instant.now(clock)` | Mốc thời gian tuyệt đối, có thể inject Clock để test. | Cần clock của server được đồng bộ. |
| `Instant.parse(text)` | Parse thời điểm ISO-8601 UTC theo profile của Java. | Có thể chấp nhận nhiều dạng hơn policy V1; phải kiểm thêm **canonical form**. |
| `Instant.truncatedTo(ChronoUnit.SECONDS)` | Loại phần nhỏ hơn giây theo cách xác định. | Dùng trước khi client gửi, không được tự làm tròn timestamp đã ký tại server. |
| `Clock.fixed(instant, ZoneOffset.UTC)` | Test biên deterministic. | Chỉ dùng trong test, không hardcode clock trong production. |
| `LocalDateTime.now()` | Giờ lịch tại timezone cấu hình. | **Không** dùng làm timestamp tuyệt đối có chữ ký khi thiếu zone/offset. |
| `System.nanoTime()` | Đo thời lượng tương đối trong một JVM. | **Không phải** UTC timestamp gửi qua mạng. |

## 5. Cửa sổ freshness: request được chấp nhận đến khi nào?

Giả sử server nhận request tại `now = 2026-11-28T02:00:30Z` với policy **±300 giây**. Quy tắc V1 là:

\[
\mathrm{fresh} \iff
(\mathrm{now}-300\,s \leq \mathrm{timestamp}
\leq \mathrm{now}+300\,s)
\]

Tức là **hai biên đều inclusive** trong ví dụ. Từ chối nếu timestamp **nhỏ hơn** biên quá khứ hoặc **lớn hơn** biên tương lai.

**Ví dụ tại cùng giờ server 02:00:30Z:**

| Timestamp đã ký | Khoảng cách tới server | Freshness V1 |
| --- | ---: | --- |
| `2026-11-28T01:55:29Z` | −301 giây | **Từ chối: quá cũ**. |
| `2026-11-28T01:55:30Z` | −300 giây | **Chấp nhận về tuổi** (đúng biên). |
| `2026-11-28T02:00:00Z` | −30 giây | **Chấp nhận về tuổi**. |
| `2026-11-28T02:00:30Z` | 0 giây | **Chấp nhận về tuổi**. |
| `2026-11-28T02:05:30Z` | +300 giây | **Chấp nhận về tuổi** (đúng biên). |
| `2026-11-28T02:05:31Z` | +301 giây | **Từ chối: quá xa tương lai**. |

**“Chấp nhận về tuổi” chưa đồng nghĩa authenticated**: request vẫn cần credential ACTIVE, HMAC đúng, nonce chưa dùng, chính sách endpoint và các điều kiện xác thực khác.

### Vì sao cho phép timestamp hơi ở tương lai?

Đồng hồ client và server có thể lệch do cấu hình, NTP, độ trễ hoặc cơ chế đồng bộ thời gian. Cho phép một khoảng tương lai giảm lỗi false-negative đối với các client nhanh hơn server. Nhưng cửa sổ càng rộng, request hợp lệ có thể được phát lại càng lâu **nếu thiếu nonce**. Vì vậy lựa chọn ±5 phút chỉ là ví dụ, **không phải khuyến nghị bắt buộc** cho mọi môi trường.

Một policy có thể dùng hai độ rộng khác nhau, ví dụ chỉ cho trước 60 giây nhưng nhận quá khứ 300 giây:

```text
now - allowedPast <= timestamp <= now + allowedFuture
```

Lúc đó nonce TTL phải được tính theo **allowedPast** và thời điểm timestamp được ký, không suy ra từ allowedFuture đơn độc.

### Kiểm tra ở đâu trong pipeline?

Việc xác thực timestamp có hai phần:

- **Format check**: có thể thực hiện sớm với chi phí thấp để tránh parse request sai cấu trúc.
- **Freshness decision**: nên thực hiện trên **timestamp đã được HMAC bảo vệ** và đồng hồ server tin cậy; không claim nonce trước khi MAC đúng.

Mỗi server instance cần dùng clock đúng. Nếu đồng hồ server bị lùi hoặc nhảy tới tương lai đột ngột, quyết định freshness có thể thay đổi. Nên đồng bộ thời gian, giám sát độ lệch clock và chọn chính sách fail closed/alert cho hệ thống yêu cầu độ tin cậy cao.

## 6. Timestamp không đủ ngăn replay trong cửa sổ

Xét một request có HMAC hợp lệ:

```text
timestamp = 2026-11-28T02:00:00Z
nonce     = Zq8DxKtUokcwPGNj3d_yvQ
signature = v1=<VALID_MAC>
```

Attacker ghi lại request rồi gửi lại lúc `02:00:20Z`. Server tính HMAC đúng, timestamp vẫn nằm trong ±300 giây. Nếu chỉ có timestamp, cả **hai lần** đều có thể vượt qua lớp xác thực.

**Nonce** giải quyết phần còn lại:

1. Client tạo `nonce` ngẫu nhiên bằng **CSPRNG**, mỗi request mới dùng nonce mới.
2. HMAC ký cả `timestamp` và `nonce`, nên attacker không thể thay chúng mà giữ chữ ký.
3. Sau khi kiểm tra credential, MAC và freshness, server **claim** key `(audience, keyId, nonce)` bằng thao tác **nguyên tử**.
4. Nếu claim đầu tiên thành công, request mới được tạo kết quả authentication thành công.
5. Nếu key đã tồn tại, trả lỗi replay **dù chữ ký HMAC vẫn đúng**.

```mermaid
sequenceDiagram
    participant C as HMAC Client
    participant V as Gateway/Verifier
    participant N as Shared Nonce Store
    participant B as Backend
    C->>V: Signed request (timestamp T, nonce N)
    V->>V: Credential + canonical HMAC + freshness
    V->>N: Atomic claim (audience,keyId,N), expire at T+window+margin
    N-->>V: Claimed
    V->>B: Authenticated principal; authorization tiếp
    C->>V: Replay nguyên request với T và N cũ
    V->>V: HMAC đúng, T còn fresh
    V->>N: Atomic claim cùng key
    N-->>V: Already exists
    V-->>C: Reject replay, không gọi backend
```

Kho nonce phải **chia sẻ giữa các instance**: sử dụng một `HashSet` riêng cho mỗi gateway là không đủ. Cần ràng buộc key với audience/credential, xử lý phân vùng mạng, thao tác claim atomic và TTL, đồng thời tránh race giữa kiểm tra tồn tại và insert.

### Chi tiết quan trọng: TTL của nonce

Với cửa sổ ±300 giây, một request **có timestamp ở tương lai 300 giây** có thể được chấp nhận ngay thời điểm sớm nhất:

```text
Timestamp đã ký:       02:05:30Z
Server nhận lần đầu:   02:00:30Z    (T - 300 s)
Server còn chấp nhận:  02:10:30Z    (T + 300 s)
```

Nếu nonce store xóa entry chỉ sau **300 giây kể từ lần nhận đầu**, attacker có thể phát lại tại `02:05:31Z`, khi timestamp vẫn hợp lệ. Thời gian từ **lần nhận sớm nhất** đến **lần nhận muộn nhất** lên tới **600 giây**.

Vì vậy với V1:

```text
nonceExpiresAt = signedTimestamp + 300 seconds + safetyMargin
```

Tại lúc claim, bảo đảm `expiresAt` còn ở tương lai, và store giữ key **đến ít nhất thời điểm đó**. Với các hệ thống dùng TTL tương đối, tính TTL từ `expiresAt - now` và bảo đảm không bị làm tròn thành 0 quá sớm. Cần cộng biên an toàn cho độ lệch giữa node, độ trễ store và thời điểm xử lý. Nếu store không sẵn sàng, endpoint bắt buộc chống replay phải **fail closed**.

Đây là quy tắc chống replay **theo mỗi credential và mỗi cửa sổ**; nó không thay thế **idempotency nghiệp vụ** cho request mới được ký với nonce khác.

## 7. Canonical request HMAC-SHA256-V1 chứa timestamp

Hợp đồng minh họa cho dịch vụ `orders-api-prod`:

| Thành phần | Quy tắc của V1 |
| --- | --- |
| Method | `POST` đúng hoa/thường. |
| Raw request target | Chính xác `/v1/orders?channel=partner` trong ví dụ. |
| Audience | Dòng cố định `orders-api-prod` để hạn chế cross-service replay. |
| `Content-Type` | Chính xác `application/json`, chỉ một occurrence. |
| `Content-Encoding` | Không xuất hiện; chỉ nhận raw JSON body không nén. |
| `X-Key-Id` | Định danh credential, được ký, tra đúng secret ACTIVE. |
| **`X-Timestamp`** | UTC `YYYY-MM-DDTHH:mm:ssZ`, signed value phải giữ nguyên. |
| `X-Nonce` | 16 byte CSPRNG, Base64URL không padding; được ký, dùng một lần. |
| Body | SHA-256 của raw content bytes, hex lowercase 64 ký tự. |
| Dòng canonical | UTF-8, LF giữa các dòng, không LF cuối. |
| Tag | Full HMAC-SHA256 32 byte, Base64 chuẩn có padding và prefix `v1=`. |

Ví dụ canonical:

```text
HMAC-SHA256-V1
orders-api-prod
POST
/v1/orders?channel=partner
content-type:application/json
x-key-id:partner-a-202611
x-timestamp:2026-11-28T02:00:00Z
x-nonce:Zq8DxKtUokcwPGNj3d_yvQ
sha256:<LOWERCASE_HEX_OF_SHA256_RAW_BODY>
```

Trong đó `<LOWERCASE_HEX_OF_SHA256_RAW_BODY>` là placeholder. Sau khi điền digest thật:

\[
\begin{aligned}
D &= \operatorname{SHA256}(\mathrm{rawBodyBytes}),\\
C &= \operatorname{UTF8}(\mathrm{canonicalString\ containing\ hex}(D)),\\
S &= \texttt{v1=} \Vert \operatorname{Base64}\big(
  \operatorname{HMAC}_{\mathrm{SHA256}}(K,C)\big).
\end{aligned}
\]

Header `X-Signature` **không nằm trong dữ liệu ký của chính nó**. Timestamp có ký, nhưng `Date` của HTTP response, `createdAt` trong JSON hay đồng hồ server **không** thay thế giá trị `X-Timestamp` của request.

### Không tự chuẩn hóa giá trị timestamp sau khi nhận

Nếu client ký `2026-11-28T02:00:00Z`, server cần dùng **đúng giá trị đã được kiểm tra định dạng** khi dựng canonical. Đừng parse timestamp rồi format thành `2026-11-28T02:00:00.000Z` hoặc đổi sang offset khác trước khi tính MAC. V1 từ chối những biểu diễn khác format thay vì cố làm cho chữ ký khớp.

## 8. Java 17: kiểm tra thời gian request cùng chữ ký và nonce

Ví dụ sau là một chương trình Java 17 tự chứa với các phần:

- Client test tạo timestamp bằng `Clock`, làm tròn xuống giây; nonce từ `SecureRandom`.
- Lớp verifier tra credential ACTIVE và đúng audience, dựng canonical request, so full HMAC-SHA256.
- Hàm `parseTimestampStrict` dùng `Instant.parse` rồi **format lại về dạng chuẩn** để loại dạng thời gian không theo V1.
- So timestamp với `Clock` server theo **hai biên inclusive ±300 giây**.
- Kho nonce trong bộ nhớ thực hiện claim có `synchronized` và có expiry tại `timestamp + window + margin`.
- Kết quả xác thực chỉ trả principal khi MAC, freshness và nonce đều đạt.
- `Clock.fixed` kiểm tra chính xác quá khứ, tương lai, biên và replay mà không phụ thuộc đồng hồ máy.

**Giới hạn:** local nonce store và credential map chỉ phục vụ demo. Production cần secret manager, distributed atomic nonce store, HTTP adapter và bảo vệ parser/gateway.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.time.format.DateTimeParseException;
import java.util.Arrays;
import java.util.Base64;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.Map;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class TimestampRequestHmacV1 {
    private static final String VERSION = "HMAC-SHA256-V1";
    private static final String AUDIENCE = "orders-api-prod";
    private static final String TARGET = "/v1/orders?channel=partner";
    private static final String MEDIA_TYPE = "application/json";
    private static final String SIGNATURE_PREFIX = "v1=";
    private static final long WINDOW_SECONDS = 300;
    private static final long NONCE_MARGIN_SECONDS = 30;

    private TimestampRequestHmacV1() {}

    public enum Status {
        AUTHENTICATED, BAD_REQUEST, INVALID_CREDENTIAL,
        INVALID_SIGNATURE, EXPIRED, TOO_EARLY,
        REPLAY, UNAVAILABLE
    }

    public record Result(Status status, String clientId) {
        public static Result rejected(Status status) {
            return new Result(status, null);
        }
        public static Result accepted(String clientId) {
            return new Result(Status.AUTHENTICATED, clientId);
        }
    }

    public record Credential(
            String keyId, String clientId, String audience,
            boolean active, byte[] secret) {
        public Credential {
            secret = secret.clone();
        }
        @Override
        public byte[] secret() {
            return secret.clone();
        }
    }

    public record SignedRequest(
            String method, String rawTarget,
            String contentType, boolean contentEncodingPresent,
            String keyId, String timestamp, String nonce,
            byte[] body, String signature) {
        public SignedRequest {
            if (body != null) {
                body = body.clone();
            }
        }
        @Override
        public byte[] body() {
            return body == null ? null : body.clone();
        }
    }

    public interface NonceStore {
        boolean claim(String key, Instant expiresAt, Instant now)
                throws StoreUnavailable;
    }

    public static final class StoreUnavailable extends Exception {}

    /** Kho test: atomic trong một JVM, không dùng production. */
    public static final class InMemoryNonceStore implements NonceStore {
        private final Map<String, Instant> expiries = new HashMap<>();

        @Override
        public synchronized boolean claim(
                String key, Instant expiresAt, Instant now) {
            if (!expiresAt.isAfter(now)) {
                return false;
            }
            expiries.entrySet().removeIf(
                    e -> !e.getValue().isAfter(now));
            if (expiries.containsKey(key)) {
                return false;
            }
            expiries.put(key, expiresAt);
            return true;
        }
    }

    /** V1 chỉ nhận UTC có giây, không offset khác/fraction. */
    public static Instant parseTimestampStrict(String text) {
        if (text == null || !text.matches(
                "[0-9]{4}-[0-9]{2}-[0-9]{2}T"
                + "[0-9]{2}:[0-9]{2}:[0-9]{2}Z")) {
            throw new IllegalArgumentException("Invalid timestamp format");
        }
        try {
            Instant parsed = Instant.parse(text);
            String normalized = parsed.truncatedTo(
                    ChronoUnit.SECONDS).toString();
            if (!normalized.equals(text)) {
                throw new IllegalArgumentException(
                        "Noncanonical timestamp");
            }
            return parsed;
        } catch (DateTimeParseException ex) {
            throw new IllegalArgumentException(
                    "Invalid timestamp value", ex);
        }
    }

    private static boolean validNonce(String text) {
        if (text == null || text.length() != 22) {
            return false;
        }
        try {
            byte[] bytes = Base64.getUrlDecoder().decode(text);
            return bytes.length == 16
                    && Base64.getUrlEncoder().withoutPadding()
                            .encodeToString(bytes).equals(text);
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }

    private static boolean validShape(SignedRequest r) {
        if (r == null || !"POST".equals(r.method())
                || !TARGET.equals(r.rawTarget())
                || !MEDIA_TYPE.equals(r.contentType())
                || r.contentEncodingPresent()
                || r.keyId() == null
                || !r.keyId().matches("[A-Za-z0-9_-]{1,80}")
                || !validNonce(r.nonce())
                || r.body() == null || r.body().length > 8192) {
            return false;
        }
        try {
            parseTimestampStrict(r.timestamp());
            return true;
        } catch (IllegalArgumentException malformed) {
            return false;
        }
    }

    private static byte[] canonicalBytes(SignedRequest r)
            throws GeneralSecurityException {
        String bodyHash = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256")
                        .digest(r.body()));
        String canonical = String.join("\n",
                VERSION, AUDIENCE, r.method(), r.rawTarget(),
                "content-type:" + r.contentType(),
                "x-key-id:" + r.keyId(),
                "x-timestamp:" + r.timestamp(),
                "x-nonce:" + r.nonce(),
                "sha256:" + bodyHash);
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] hmac(byte[] secret, byte[] message)
            throws GeneralSecurityException {
        // Đây là policy provisioning của ví dụ, không phải giới hạn JCA.
        if (secret == null || secret.length < 32) {
            throw new GeneralSecurityException("Invalid credential key");
        }
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(message);
    }

    private static byte[] decodeSignature(String header) {
        if (header == null || header.length() != 47
                || !header.startsWith(SIGNATURE_PREFIX)) {
            return null;
        }
        String b64 = header.substring(SIGNATURE_PREFIX.length());
        if (!b64.matches("[A-Za-z0-9+/]{43}=")) {
            return null;
        }
        try {
            byte[] supplied = Base64.getDecoder().decode(b64);
            return supplied.length == 32
                    && Base64.getEncoder().encodeToString(supplied)
                            .equals(b64)
                    ? supplied : null;
        } catch (IllegalArgumentException ex) {
            return null;
        }
    }

    /** Lõi xác thực; HTTP parser/adapter phải chặn duplicate trước đó. */
    public static Result verify(
            SignedRequest r, Map<String, Credential> registry,
            NonceStore nonceStore, Clock clock) {
        if (!validShape(r)) {
            return Result.rejected(Status.BAD_REQUEST);
        }
        Credential credential = registry.get(r.keyId());
        if (credential == null || !credential.active()
                || !AUDIENCE.equals(credential.audience())
                || !credential.keyId().equals(r.keyId())) {
            return Result.rejected(Status.INVALID_CREDENTIAL);
        }
        byte[] supplied = decodeSignature(r.signature());
        if (supplied == null) {
            return Result.rejected(Status.INVALID_SIGNATURE);
        }

        // MAC trước freshness/replay: giá trị timestamp đã được ký.
        try {
            byte[] expected = hmac(
                    credential.secret(), canonicalBytes(r));
            if (!MessageDigest.isEqual(expected, supplied)) {
                return Result.rejected(Status.INVALID_SIGNATURE);
            }
        } catch (GeneralSecurityException providerFailure) {
            return Result.rejected(Status.UNAVAILABLE);
        }

        Instant now = clock.instant();
        Instant signedTime = parseTimestampStrict(r.timestamp());
        if (signedTime.isBefore(now.minusSeconds(WINDOW_SECONDS))) {
            return Result.rejected(Status.EXPIRED);
        }
        if (signedTime.isAfter(now.plusSeconds(WINDOW_SECONDS))) {
            return Result.rejected(Status.TOO_EARLY);
        }

        Instant expiresAt = signedTime.plusSeconds(
                WINDOW_SECONDS + NONCE_MARGIN_SECONDS);
        String nonceKey = AUDIENCE + ":" + r.keyId() + ":" + r.nonce();
        try {
            if (!nonceStore.claim(nonceKey, expiresAt, now)) {
                return Result.rejected(Status.REPLAY);
            }
        } catch (StoreUnavailable unavailable) {
            return Result.rejected(Status.UNAVAILABLE);
        }
        return Result.accepted(credential.clientId());
    }

    public static SignedRequest signForTest(
            Credential credential, String timestamp,
            String nonce, byte[] body) throws GeneralSecurityException {
        SignedRequest unsigned = new SignedRequest(
                "POST", TARGET, MEDIA_TYPE, false, credential.keyId(),
                timestamp, nonce, body, null);
        if (!validShape(unsigned)) {
            throw new IllegalArgumentException("Invalid outgoing request");
        }
        String signature = SIGNATURE_PREFIX
                + Base64.getEncoder().encodeToString(
                    hmac(credential.secret(), canonicalBytes(unsigned)));
        return new SignedRequest(
                unsigned.method(), unsigned.rawTarget(),
                unsigned.contentType(), false, unsigned.keyId(),
                timestamp, nonce, body, signature);
    }

    public static String freshTimestamp(Clock clock) {
        return clock.instant().truncatedTo(
                ChronoUnit.SECONDS).toString();
    }

    public static String freshNonce(SecureRandom random) {
        byte[] bytes = new byte[16];
        random.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(bytes);
    }

    private static void expect(Status expected, Result actual) {
        if (actual.status() != expected) {
            throw new AssertionError(
                    "Expected " + expected + ", got " + actual.status());
        }
        if (expected != Status.AUTHENTICATED
                && actual.clientId() != null) {
            throw new AssertionError("Principal leaked on failure");
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] secret = new byte[32]; // Khóa giả chỉ dùng trong test.
        Arrays.fill(secret, (byte) 0x59);
        Credential credential = new Credential(
                "partner-a-202611", "partner-a",
                AUDIENCE, true, secret);
        Map<String, Credential> registry =
                Map.of(credential.keyId(), credential);

        Clock fixed = Clock.fixed(
                Instant.parse("2026-11-28T02:00:30Z"), ZoneOffset.UTC);
        SecureRandom random = new SecureRandom();
        byte[] body = "{\"sku\":\"BK-42\",\"quantity\":2}"
                .getBytes(StandardCharsets.UTF_8);

        SignedRequest valid = signForTest(
                credential, "2026-11-28T02:00:00Z",
                freshNonce(random), body);
        InMemoryNonceStore store = new InMemoryNonceStore();
        Result accepted = verify(valid, registry, store, fixed);
        expect(Status.AUTHENTICATED, accepted);
        if (!"partner-a".equals(accepted.clientId())) {
            throw new AssertionError("Wrong authenticated principal");
        }

        // HMAC vẫn đúng nhưng nonce đã được claim.
        expect(Status.REPLAY, verify(valid, registry, store, fixed));

        // Thay timestamp nhưng giữ signature -> MAC sai, không phải refresh.
        SignedRequest changedTime = new SignedRequest(
                valid.method(), valid.rawTarget(), valid.contentType(),
                false, valid.keyId(), "2026-11-28T02:00:01Z",
                valid.nonce(), body, valid.signature());
        expect(Status.INVALID_SIGNATURE,
                verify(changedTime, registry,
                        new InMemoryNonceStore(), fixed));

        // Đúng MAC nhưng quá cũ hơn 300 giây.
        SignedRequest old = signForTest(
                credential, "2026-11-28T01:55:29Z",
                freshNonce(random), body);
        expect(Status.EXPIRED, verify(
                old, registry, new InMemoryNonceStore(), fixed));

        // Đúng MAC nhưng quá xa tương lai (> 300 giây).
        SignedRequest future = signForTest(
                credential, "2026-11-28T02:05:31Z",
                freshNonce(random), body);
        expect(Status.TOO_EARLY, verify(
                future, registry, new InMemoryNonceStore(), fixed));

        // Hai biên inclusive: chính xác +/- 300 giây được chấp nhận.
        SignedRequest pastBoundary = signForTest(
                credential, "2026-11-28T01:55:30Z",
                freshNonce(random), body);
        expect(Status.AUTHENTICATED, verify(
                pastBoundary, registry, new InMemoryNonceStore(), fixed));
        SignedRequest futureBoundary = signForTest(
                credential, "2026-11-28T02:05:30Z",
                freshNonce(random), body);
        expect(Status.AUTHENTICATED, verify(
                futureBoundary, registry, new InMemoryNonceStore(), fixed));

        NonceStore brokenStore = (key, expiresAt, now) -> {
            throw new StoreUnavailable();
        };
        SignedRequest fresh = signForTest(
                credential, freshTimestamp(fixed),
                freshNonce(random), body);
        expect(Status.UNAVAILABLE,
                verify(fresh, registry, brokenStore, fixed));

        if (!freshTimestamp(fixed)
                .equals("2026-11-28T02:00:30Z")) {
            throw new AssertionError("Unexpected UTC timestamp");
        }
        System.out.println("Signed timestamp + replay checks passed.");
    }
}
```

### Cách đọc ví dụ

- **`freshTimestamp`** tạo chuỗi UTC có độ chính xác giây; client dùng `Clock.systemUTC()` trong production và timestamp phải được tạo gần lúc gửi.
- **`parseTimestampStrict`** nhận chính xác định dạng V1 và từ chối các dạng UTC cùng instant nhưng khác biểu diễn, như `+00:00` hoặc fractional seconds. Check canonical text sau parse tránh chấp nhận một số dạng normalize âm thầm.
- **`Clock.fixed`** làm test ranh giới lặp lại được. Production không được dùng đồng hồ cố định.
- **`Status.EXPIRED` và `Status.TOO_EARLY`** tách hai loại lệch thời gian để quan sát nội bộ. Phản hồi cho Internet có thể là lỗi authentication chung để hạn chế tiết lộ thông tin.
- **`Status.UNAVAILABLE`** biểu thị lỗi không thể hoàn tất xác minh; **không** được coi là authenticated. Cần trả lỗi dịch vụ và cảnh báo vận hành.
- **`Result.clientId`** chỉ khác `null` khi `AUTHENTICATED`; không dùng `X-Key-Id` chưa xác minh làm principal.
- **`InMemoryNonceStore`** chỉ đồng bộ trong một process. Production phải dùng atomic claim, expiry và store dùng chung giữa nhiều node.
- **Timestamp/nonce đều được ký**, nhưng việc có HMAC đúng không đồng nghĩa có quyền thực hiện `POST`; authorization vẫn làm riêng.

**Giới hạn học thuật:** Chương trình minh họa chỉ triển khai lõi xác minh, không phải HTTP middleware production. Chưa có HTTP parser, phát hiện header trùng, credential registry/secret manager thực, quota/rate limit, mạng/TLS, audit, kiểm soát clock health hay authorization. Không chạy code này trực tiếp cho endpoint công khai.

## 9. Clock skew: lỗi vận hành thường gặp

Timestamp không chỉ là vấn đề code. Khi client và server có đồng hồ lệch, một request mới hoàn toàn có thể bị từ chối.

### Ba kiểu lệch thường gặp

| Tình huống | Dấu hiệu | Cách xử lý |
| --- | --- | --- |
| Client nhanh hơn server 7 phút. | `TOO_EARLY` dù client vừa ký xong. | Sửa đồng bộ UTC ở client; không tự nới toàn bộ hệ thống lên ±15 phút. |
| Client chậm hơn server 6 phút. | `EXPIRED`, phát sinh khi nhiều request hợp lệ bị từ chối. | Đồng bộ clock; ghi metric có kiểm soát về lệch thời gian. |
| Một gateway có clock lệch 2 phút so với gateway khác. | Request cùng timestamp có kết quả không nhất quán theo instance. | NTP/chrony, alert clock skew, kiểm tra time source của cụm. |
| Delay mạng/queue quá lâu. | Timestamp từng mới nhưng tới verifier khi quá hạn. | Xem thời điểm ký và queue; thiết kế thời hạn/retry phù hợp. |
| Server clock nhảy lùi sau khi đã nhận nonce. | Timestamp cũ có thể lại nằm trong cửa sổ. | Kho nonce phải giữ đầy đủ expiry; giám sát thay đổi clock bất thường. |

**Tránh tự động sửa clock bằng cách lấy timestamp do client khai làm giờ server.** Chính request timestamp là dữ liệu chưa tin và do người sở hữu secret kiểm soát trong phạm vi policy. Server cần nguồn thời gian độc lập đáng tin.

### Thời điểm nào lấy `now`?

Một gateway có thể quyết định “server receive time” ở đầu security filter hoặc tại điểm xác minh sau khi body được đọc. Chọn một **định nghĩa nhất quán** và dùng cùng giá trị `now` cho cả kiểm tra freshness lẫn tính expiry khi claim nonce. Nếu đọc stream body rất lâu, timestamp có thể hết hiệu lực trong lúc xử lý; cần chính sách giới hạn thời gian, body size và thời điểm hiệu lực được công bố. Không dùng nhiều lần `Instant.now()` không kiểm soát cho hai biên rồi tạo hành vi bất đối xứng tại ranh giới.

## 10. Retry, idempotency và ký lại timestamp

Một lỗi mạng không đồng nghĩa server **chưa xử lý** request. Với `POST` tạo đơn, timeout có thể xảy ra **sau khi server commit** nhưng **trước khi client nhận phản hồi**.

| Tình huống | Timestamp/nonce cho lần tiếp theo | Cách tránh side effect lặp |
| --- | --- | --- |
| Signature sai vì client gửi sai canonical bytes. | Sửa contract, tạo timestamp + nonce mới rồi ký lại. | Không tự thử nhiều cách normalize trên server. |
| Timestamp quá cũ. | Đồng bộ clock; tạo timestamp mới, nonce mới, chữ ký mới. | Kiểm tra request trước có được xử lý chưa nếu là mutation. |
| Request bị replay do nonce trùng. | Không dùng lại nonce; request mới phải ký lại. | Kiểm tra logic cấp nonce và idempotency. |
| Timeout sau khi gửi POST. | Nếu retry, timestamp/nonce/signature đều mới. | Dùng **idempotency key** hoặc status lookup trước retry. |
| PATCH với `If-Match` và ETag cũ. | Sau `412`, lấy phiên bản mới; tạo request và chữ ký mới. | Không áp lại thay đổi trên trạng thái mới một cách mù quáng. |
| Server báo `429`/`503` với `Retry-After`. | Theo lịch backoff tạo request mới đúng cửa sổ. | Vẫn cần idempotency cho mutation. |

**Phân biệt:** nonce phải **khác giữa hai HTTP attempts**, nhưng `Idempotency-Key` (nếu API hỗ trợ) thường phải **giống nhau cho cùng ý định nghiệp vụ** qua các lần retry. Nếu header này điều khiển deduplication, phải đưa nó vào **signed headers** và ràng buộc với principal, method, URI và fingerprint payload theo contract phiên bản phù hợp.

Với HTTP client có chức năng **automatic redirect hoặc automatic retry**, cần kiểm soát vì một HTTP request object cũ có thể bị phát lại với timestamp/nonce cũ, hoặc chuyển method/URI sau khi ký. Tốt nhất là đảm bảo mọi lần gửi lại có chủ ý dùng **cùng đối tượng nghiệp vụ nhưng một HTTP request mới được ký**, không bật cơ chế retry không quan sát được đối với mutation.

## 11. Key rotation và timestamp: hai trục kiểm tra độc lập

Trong khoảng chuyển khóa, một client có thể có hai credential hợp lệ:

| Key ID | Client | Secret | Trạng thái |
| --- | --- | --- | --- |
| `partner-a-202611` | `partner-a` | Secret A | ACTIVE trong overlap. |
| `partner-a-202702` | `partner-a` | Secret B độc lập | ACTIVE mới. |
| `partner-a-202608` | `partner-a` | Đã thu hồi | REVOKED. |

**Timestamp không giúp hồi sinh credential bị revoke.** Server phải kiểm tra key ACTIVE/audience/expiry trước khi chấp nhận MAC, dù timestamp rất mới và nonce chưa dùng. Ngược lại, key ACTIVE và chữ ký đúng vẫn bị từ chối khi timestamp quá cũ.

Trong một lần ký, client phải chọn một cặp **`(keyId, secret)` nhất quán**. Không thay `X-Key-Id` sang ID mới nhưng vẫn ký bằng secret cũ, hoặc cố tình sửa timestamp của chữ ký cũ sau rotation. Mọi thay đổi signed header đều cần tính lại HMAC.

Nếu clock của hệ thống key registry ảnh hưởng đến khoảng hiệu lực credential, hãy tách rõ **thời gian hiệu lực của credential** với **freshness window của HTTP request**. Một credential hết hạn tại thời điểm kiểm tra không tự trở nên hợp lệ vì client ký request trước giờ hết hạn, trừ khi API có chính sách đặc biệt được định nghĩa và chứng minh an toàn.

## 12. Proxy/gateway và timestamp trên đường đi

| Biến đổi hoặc lỗi tầng trung gian | Hệ quả | Giải pháp kiểm thử/phòng thủ |
| --- | --- | --- |
| Proxy thêm/sửa `X-Timestamp` sau khi client ký. | MAC không khớp vì timestamp được ký. | Giữ signed header value nguyên vẹn; kiểm tra vị trí xác minh trước rewrite. |
| HTTP/1.1 → HTTP/2 chuyển tên `X-Timestamp` thành `x-timestamp`. | Đây là cùng header field theo HTTP; không nên thay MAC. | Lowercase **tên**, không lowercase **value**, trong canonical request. |
| Header `X-Timestamp` xuất hiện hai lần khác case. | Gateway/backend có thể chọn first/last. | Từ chối duplicate ở ingress trước khi gộp. |
| Gateway rewrite URI, query hoặc method. | HMAC khác dù timestamp và secret đúng. | Xác minh tại điểm tin cậy; bảo đảm canonical target nhất quán. |
| Proxy parse/serialize JSON body. | SHA-256(body) khác; HMAC khác. | Băm raw content bytes; không normalize payload ngoài contract. |
| Mỗi gateway có giờ hệ thống khác nhau. | Cùng request có thể nhận `EXPIRED` hoặc `TOO_EARLY` khác nhau. | Giám sát NTP/clock, inject Clock khi test và có SLO clock skew. |
| Gateway và backend đều claim nonce độc lập. | Replay policy không nhất quán hoặc request hợp lệ bị đánh dấu dùng lại. | Quy định **một điểm sở hữu** replay claim hoặc hợp đồng phối hợp atomic rõ ràng. |
| Gateway xác thực rồi client tự khai `X-Authenticated-Client`. | Có thể giả danh nếu backend tin header ngoài. | Xóa header client, truyền principal bằng kênh tin cậy. |

Đừng thay `X-Timestamp` trong gateway rồi “tính lại HMAC giúp client” bằng secret của client. Gateway chỉ nên **xác minh** request từ client; nếu cần ký request mới giữa các service, đó là **credential và trust boundary khác** với audience/keys riêng, không che giấu việc rewrite của request gốc.

### Phân biệt lỗi đồng hồ với lỗi canonicalization

Chữ ký sai do proxy đổi URI hoặc header có ký: lỗi MAC **trước** bước freshness. Ngược lại, HMAC đúng trên timestamp quá cũ: lỗi freshness, **không thể sửa** bằng cách đổi chữ hoa của header hoặc Base64. Việc tách mã nguyên nhân nội bộ giúp debug đúng, nhưng phản hồi ngoài cần tránh tiết lộ secret/registry.

## 13. Authentication không thay authorization

Giả sử một request có:

- Shared secret đúng với credential `partner-a-202611`.
- Method, URI, signed headers và body digest được ký chính xác.
- Timestamp mới, nonce chưa từng xuất hiện.
- HMAC đầy đủ khớp.

Server có thể tạo **authentication result thành công** cho `clientId=partner-a`. Điều đó **không đồng nghĩa** client được gọi `POST /v1/orders` cho mọi tenant hay sửa trường `totalAmount`.

| Bước | Kết luận | Kiểm soát |
| --- | --- | --- |
| **Authentication** | Request đến từ bên sở hữu credential hợp lệ, signed data không bị sửa, còn mới và không replay. | Credential registry, HMAC, timestamp, nonce. |
| **Authorization** | Principal được phép gọi method/resource/tenant/scope này không? | Role/scope, resource ownership, field-level permissions. |
| **Business validation** | Dữ liệu và trạng thái nghiệp vụ cho phép thực hiện không? | Validation, ETag, quota, transaction. |

Một client đã xác thực nhưng chỉ có scope `orders:read` phải bị từ chối `POST` tạo đơn, thường bằng **403 Forbidden** theo API policy. Không đổi tình huống này thành “HMAC sai”, cũng không “mở lại” nonce đã claim vì phân quyền hoặc validation phía sau thất bại.

## 14. Xử lý lỗi thời gian và quan sát an toàn

| Trạng thái | Lý do | Hướng xử lý |
| --- | --- | --- |
| Timestamp sai cú pháp, không canonical hoặc ngày không hợp lệ | Format error. | Từ chối request, client sửa format. |
| MAC sai dù timestamp trông đúng | Secret/canonical bytes không khớp. | Debug bằng test vector không nhạy cảm, không tự chỉnh giờ server để cho qua. |
| `EXPIRED` sau MAC đúng | Timestamp quá cũ so với now. | Đồng bộ clock hoặc sửa pipeline gửi; không tái dùng request cũ. |
| `TOO_EARLY` sau MAC đúng | Timestamp quá xa tương lai. | Kiểm tra clock client/instance server. |
| `REPLAY` sau MAC đúng và timestamp fresh | Nonce đã claim. | Từ chối; request mới cần nonce và signature mới. |
| Nonce store/secret manager/JCA provider lỗi | Không thể hoàn tất xác thực. | **Fail closed**, lỗi dịch vụ, alert vận hành. |
| HMAC + timestamp + nonce đúng nhưng thiếu quyền | Authorization failure. | Từ chối ở lớp quyền, không nói là lỗi thời gian. |

Với HMAC API tùy biến, `401 Unauthorized` là mã lỗi authentication thường gặp, nhưng việc dùng `401` có các quy tắc challenge `WWW-Authenticate` trong HTTP; phải thiết kế response theo scheme/contract cụ thể. Lỗi hạ tầng như nonce store không sẵn sàng thường thích hợp với lỗi `5xx`; không báo “client ký sai” khi verifier không kiểm tra được.

**Log an toàn:** chỉ ghi request ID, mã lỗi nội bộ, tên policy/window, nguồn server clock, key ID đã lọc và thống kê độ lệch thời gian nếu cần. Không ghi shared secret, full signature production, canonical request chứa dữ liệu riêng tư hoặc raw body nhạy cảm. Cũng cần tránh để metric có thể giúp người ngoài phân biệt key ID nào tồn tại.

## 15. Ma trận kiểm thử timestamp request

| Test case | Kết quả mong đợi |
| --- | --- |
| Timestamp UTC đúng `YYYY-MM-DDTHH:mm:ssZ`, HMAC và nonce hợp lệ. | Vượt qua authentication timestamp. |
| Timestamp `2026-11-28T09:00:00+07:00` thay dạng Z, dù cùng instant. | V1 từ chối format; không auto-normalize. |
| Timestamp có fractional seconds `.000Z`. | V1 từ chối format. |
| Timestamp sai ngày (`2026-02-30T...`). | Parse/format validation từ chối. |
| Timestamp leap-second `...:60Z`. | Từ chối nếu parse normalize khác canonical format V1. |
| Timestamp trước biên quá khứ 301 giây. | `EXPIRED`. |
| Timestamp đúng biên quá khứ 300 giây. | Fresh về tuổi, còn phải vượt nonce check. |
| Timestamp đúng server now. | Fresh về tuổi. |
| Timestamp đúng biên tương lai 300 giây. | Fresh về tuổi, nonce TTL dựa trên signed time. |
| Timestamp ở tương lai 301 giây. | `TOO_EARLY`. |
| Giữ HMAC nhưng sửa timestamp +1 giây. | MAC mismatch, không “làm mới” request. |
| Timestamp mới nhưng dùng lại nonce và signature cũ. | Nếu thay timestamp, MAC sai; nếu phát lại nguyên request thì nonce replay. |
| Signature đúng, timestamp fresh nhưng nonce đã claim. | `REPLAY`; không thực thi lần hai. |
| Hai gateway claim cùng nonce đồng thời. | Tối đa một claim thành công trong store dùng chung. |
| Giữ nonce TTL 300 giây từ lần nhận sớm nhất trong policy ±300. | **Test âm**: TTL quá ngắn có thể mở lại replay window. |
| Nonce store không sẵn sàng. | **Fail closed**; không tạo authenticated principal. |
| Timestamp vẫn mới nhưng key bị REVOKED. | Credential policy từ chối. |
| Client ký epoch milliseconds còn server parse epoch seconds. | Từ chối sai format/đơn vị; không đoán. |
| Gateway đổi `X-Timestamp` hay raw URI sau khi ký. | MAC mismatch. |
| Authenticated nhưng thiếu quyền resource. | Authorization từ chối; không phải lỗi timestamp. |

Kiểm thử nên dùng `Clock.fixed` hoặc clock giả có thể dịch chuyển có kiểm soát, không dùng `Thread.sleep` để chờ 300 giây. Test vector liên ngôn ngữ nên lưu timestamp **đúng bytes**, canonical UTF-8 bytes, HMAC raw hex/Base64, server now, độ lệch, nonce key/expiry và trạng thái mong đợi. Có thể test clock drift, gateway HTTP/1.1 ↔ HTTP/2 và failover nonce store ở tầng tích hợp.

## 16. Bài tập thực hành

### Bài 1 — Chỉ ký timestamp có chống replay không?

Client gửi request hợp lệ với timestamp ở phút hiện tại; attacker phát lại y nguyên sau 20 giây, trong khi server cho phép cửa sổ ±300 giây. Chữ ký có sai không? Request có bị chặn không?

**Gợi ý:** MAC vẫn đúng vì dữ liệu không đổi. Timestamp vẫn fresh; **nếu không có nonce store**, request có thể bị chấp nhận lại. Cần nonce đã ký và claim nguyên tử.

### Bài 2 — Giữ timestamp ngoài chữ ký

Client ký method/URI/body nhưng không đưa `X-Timestamp` vào canonical request. Proxy thay timestamp cũ bằng thời gian mới. HMAC có phát hiện không?

**Gợi ý:** Không; HMAC chỉ bảo vệ dữ liệu được ký. Phải ký timestamp theo một contract không nhập nhằng, và server tự dựng canonical từ các trường nhận được.

### Bài 3 — TTL nonce ngắn hơn cửa sổ

Timestamp bằng `02:05:30Z` được server nhận lần đầu lúc `02:00:30Z` với cửa sổ ±5 phút. Nếu nonce store xóa entry lúc `02:05:30Z` thì sao?

**Gợi ý:** Request còn nằm trong window tới `02:10:30Z`. Việc xóa nonce sớm tạo cơ hội replay. Cần giữ đến `timestamp + allowedPastWindow + margin`.

### Bài 4 — Cùng instant nhưng khác chữ ký

Client gửi timestamp `2026-11-28T09:00:00+07:00`, còn server canonicalize thành `2026-11-28T02:00:00Z`. Chúng mô tả cùng instant; HMAC có chắc bằng nhau không?

**Gợi ý:** Không; text bytes khác nhau. Trong V1, client phải gửi đúng UTC `Z` có giây; server từ chối thay vì tự sửa value.

### Bài 5 — Client clock lệch 8 phút

Client mới ký nhưng server trả lỗi timestamp tương lai, trong khi key ID và HMAC có vẻ đúng. Nên sửa bằng cách tăng window lên ±30 phút?

**Gợi ý:** Không nên nới window chỉ để che clock drift. Kiểm tra NTP, timezone/UTC, epoch unit, nơi tạo timestamp và latency; chọn window dựa trên yêu cầu bảo mật thực tế, cùng nonce store đủ TTL.

### Bài 6 — Retry POST sau timeout

Client gửi POST tạo đơn; server đã commit nhưng response mất. Client ký lại với timestamp/nonce mới rồi gửi. Có thể tạo trùng đơn không?

**Gợi ý:** Có. Timestamp/nonce mới cho phép xác thực attempt mới; **idempotency** cần được xử lý riêng. Dùng Idempotency-Key được ký trong contract tương ứng và/hoặc status lookup.

### Bài 7 — Timestamp và quyền tài nguyên

Credential có HMAC đúng, timestamp fresh, nonce mới, nhưng principal chỉ có quyền đọc đơn. Request là `PATCH` sửa giá. Server nên trả authentication failure hay authorization failure?

**Gợi ý:** Authentication có thể thành công; **authorization phải từ chối** (thường 403). Không coi timestamp mới là cấp quyền chỉnh sửa.

## 17. Checklist triển khai và tổng kết

Trước khi đưa signed timestamp vào production:

- [ ] Contract có **một định dạng timestamp duy nhất**: UTC/epoch, đơn vị, độ chính xác, offset, leading zero và canonical representation.
- [ ] Timestamp xuất hiện đúng một lần trong header security và được **HMAC ký**, không lấy từ header client khác để “sửa” request.
- [ ] Verifier có **server clock đáng tin**, đồng bộ NTP/chrony, metric về skew và policy khi clock bất thường.
- [ ] Freshness window được công bố rõ (allowedPast/allowedFuture, inclusive/exclusive) và có test tại biên.
- [ ] Canonical string giữ đúng timestamp bytes, cùng method/raw URI, signed headers, body digest, audience, key ID và nonce.
- [ ] HMAC-SHA256 full tag được verify bằng secret đúng key ID ACTIVE; không retry hàng loạt secret, thuật toán hay URI.
- [ ] Nonce sinh bằng CSPRNG, được ký, claim nguyên tử **sau HMAC/freshness và trước side effect**.
- [ ] Nonce TTL được tính đến **signedTimestamp + allowedPast + margin**, không cố định ngắn hơn lifetime của request.
- [ ] Nonce store dùng chung nhiều node, có atomic insert-if-absent; lỗi store **fail closed**.
- [ ] Gateway không sửa signed timestamp, raw URI, header value hay body sau khi ký; các duplicate header được chặn ở ingress.
- [ ] HTTP/1.1–HTTP/2/3, reverse proxy và retry middleware được test với clock injection và signed test vectors.
- [ ] Retry mutation luôn ký mới bằng timestamp/nonce mới, đồng thời dùng idempotency để tránh business side effects lặp.
- [ ] Key rotation/revoke và audience kiểm soát độc lập với freshness; credential hết hạn không được chấp nhận chỉ vì request mới.
- [ ] Principal chỉ được tạo sau authentication; backend vẫn kiểm tra **authorization theo resource, tenant, method và scope**.
- [ ] Error handling không tiết lộ secret, full signature hoặc thông tin registry; phân biệt lỗi input, lỗi HMAC, replay và lỗi hạ tầng.

**Kết luận:** **Timestamp request là giới hạn thời gian hiệu lực của một HTTP request đã ký, không phải cơ chế chống replay hoàn chỉnh.** Hãy ký một timestamp **được format canonical**, kiểm tra với đồng hồ server trong cửa sổ rõ ràng và phối hợp **nonce claim nguyên tử với TTL đủ dài**. Khi đó HMAC bảo vệ request khỏi sửa timestamp, freshness từ chối request quá cũ/quá tương lai, còn nonce ngăn lặp trong khoảng còn hợp lệ. Dù vượt qua tất cả các bước này, request vẫn cần **authorization và business validation** trước khi gây side effect.
