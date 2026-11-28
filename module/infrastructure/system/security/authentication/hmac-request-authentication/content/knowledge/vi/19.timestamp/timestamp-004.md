# Timestamp format trong HMAC Request Authentication

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **timestamp** trong một HTTP request được ký HMAC là gì, tại sao nó cần có **đơn vị thời gian và định dạng wire cố định**, và vì sao timestamp không tự chống được replay.
- Phân biệt **Unix epoch seconds**, Unix epoch milliseconds và chuỗi thời gian ISO 8601/RFC 3339; không nhầm múi giờ UTC với múi giờ của máy chạy ứng dụng.
- Xây dựng hợp đồng `X-Timestamp` gồm ký tự ASCII thập phân, không leading zero, không dấu `+`/`-`, whitespace, dấu thập phân hoặc các kiểu số do thư viện tự chuyển đổi.
- Ràng buộc **chính chuỗi timestamp nhận được** vào canonical request trước khi tính HMAC-SHA256, tránh làm mất dữ liệu qua trim/parse/format tùy tiện.
- Dùng `java.time.Instant`, `Clock` và `Long.parseLong` để tạo/đọc timestamp có kiểm tra giới hạn, kiểm thử chính xác ranh giới thời gian chấp nhận.
- Thiết kế cửa sổ lệch đồng hồ (*clock skew window*), kho nonce dùng chung với thao tác nguyên tử và TTL bao phủ cả request đến sớm.
- Kiểm thử timestamp bị sửa, quá hạn, quá xa tương lai, nhầm đơn vị, duplicate header, proxy rewrite, key rotation và sự tách biệt giữa xác thực và phân quyền.

**Bối cảnh:** Bài thuộc chương **Timestamp** của module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Module thiết kế xác thực HTTP request bằng **HMAC với shared secret**, một **canonical request** chứa method, URI, header hoặc body theo hợp đồng ký, kết hợp kiểm tra chữ ký, chống replay bằng timestamp/nonce, key rotation, kiểm thử proxy/gateway và phân biệt authentication với authorization. Trọng tâm bài này là **Timestamp format**: biến một khái niệm “thời điểm” thành **giá trị byte-level thống nhất giữa client và server**.

> Những tên header `X-*` và hợp đồng `hmac-ts-v1` sau đây là ví dụ học tập do chúng ta tự định nghĩa, không phải định dạng mặc định của mọi dịch vụ HMAC.

## 1. Timestamp trong HTTP request đã ký là gì?

Timestamp là thông tin về **mốc thời gian** do client đưa vào request, thường đại diện thời điểm client tạo hoặc chuẩn bị ký request. Nó giúp verifier giới hạn khoảng thời gian một chữ ký có thể được xem xét.

Ví dụ:

```http
POST /v1/orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-17
X-Key-Id: k2
X-Timestamp: 1760000000
X-Nonce: <nonce-ngau-nhien>
X-Signature: <hmac-sha256-tag>

{"orderId":"O-42","amount":120000}
```

`1760000000` chỉ là **ví dụ về cú pháp epoch seconds**, không phải timestamp hợp lệ cho một request gửi tại mọi thời điểm; verifier kiểm tra nó theo **đồng hồ server thực tế**. Các chuỗi `<...>` là placeholder.

Thông tin thời gian chỉ có ý nghĩa bảo mật khi nó **được đưa vào dữ liệu có HMAC bảo vệ**. Nếu timestamp là header ngoài hợp đồng ký, bên trung gian có thể sửa nó từ “quá hạn” thành “hiện tại” mà không làm tag thay đổi.

### Timestamp giải quyết bài toán nào?

Một request được ký HMAC có thể bị ghi lại và gửi lại nguyên vẹn. Chữ ký vẫn đúng vì secret và canonical bytes không thay đổi. Timestamp giới hạn **tuổi request**, nhưng không phân biệt **lần gửi đầu tiên** và **lần phát lại** trong cửa sổ chấp nhận.

| Cơ chế | Mục tiêu chính | Giới hạn |
|---|---|---|
| HMAC trên canonical request | Xác thực việc sử dụng shared secret và toàn vẹn của signed fields | Không tự chứng minh request mới |
| **Timestamp được ký** | Giới hạn khoảng thời gian chấp nhận | Trong cửa sổ vẫn có thể replay |
| **Nonce được ký + shared nonce store** | Chặn sử dụng lại nonce theo scope đã định nghĩa | Không ngăn kẻ đã biết secret tạo request/nonce mới |
| Key rotation/revocation | Giới hạn hiệu lực của secret | Không thay thế kiểm soát thời gian |
| Authorization | Xác định principal có quyền với thao tác/tài nguyên | Không suy ra trực tiếp từ timestamp/HMAC |

**Kết luận:** timestamp là **một thành phần** của replay protection, không phải một cơ chế độc lập đầy đủ.

## 2. Unix epoch seconds, milliseconds và ISO 8601 khác nhau thế nào?

**Unix epoch** là mốc `1970-01-01T00:00:00Z`. Trong nhiều giao thức HTTP signing, timestamp có thể được truyền dưới dạng số giây hoặc số mili giây đã trôi qua từ mốc đó.

| Định dạng | Ví dụ cùng nhóm cú pháp | Đơn vị/đặc tính | Rủi ro |
|---|---|---|---|
| **Unix epoch seconds** | `1700000000` | Giây kể từ Unix epoch | Cần thống nhất có nhận phần lẻ hay không |
| Unix epoch milliseconds | `1700000000000` | Mili giây kể từ epoch | Nhầm với seconds làm thời điểm lệch rất xa |
| Unix epoch microseconds | `1700000000000000` | Microseconds | Nhầm đơn vị và overflow ở parser hạn chế |
| RFC 3339/ISO 8601 | `2023-11-14T22:13:20Z` | Chuỗi ngày giờ có timezone/offset | Nhiều cách viết của cùng thời điểm |
| HTTP-date | `Tue, 14 Nov 2023 22:13:20 GMT` | Chuỗi ngày theo cú pháp HTTP-date | Dấu phẩy, whitespace, format khác với epoch |

Trong ví dụ đầu của bảng, `1700000000` giây và `1700000000000` mili giây cùng biểu diễn mốc `2023-11-14T22:13:20Z`. Đây là ví dụ về **đơn vị**, không phải giá trị còn hợp lệ trong cửa sổ timestamp tại ngày hiện tại.

**Lựa chọn của bài:** `hmac-ts-v1` dùng **Unix epoch seconds, số nguyên không âm, viết bằng chữ số ASCII hệ 10**. Không tự chấp nhận milliseconds, ISO 8601 hay HTTP-date như các dạng thay thế.

### Vì sao không dùng giờ địa phương?

Unix epoch seconds đại diện một **thời điểm tuyệt đối**. `Instant.now(clock).getEpochSecond()` không phụ thuộc server đặt tại Việt Nam, Nhật Bản hay Mỹ. Việc chuyển sang `LocalDateTime` hoặc format theo `ZoneId.systemDefault()` rồi ký là một nguồn lỗi do timezone và daylight-saving.

```text
Thời điểm tuyệt đối -> Instant -> epoch seconds -> ASCII decimal
Không cần bước:   Instant -> LocalDateTime -> timezone text -> parse lại
```

Đồng hồ client và server vẫn có thể **khác nhau về thời gian thực**; loại bỏ lỗi timezone **không** đồng nghĩa đồng hồ đã được đồng bộ.

## 3. Đặc tả `X-Timestamp` theo một grammar duy nhất

Trong `hmac-ts-v1`, format timestamp được quy định như sau:

```text
timestamp = "0" / (nonzero-digit *11DIGIT)
nonzero-digit = "1"..."9"
DIGIT = "0"..."9"

Ví dụ hợp lệ về cú pháp:
0
1
1700000000
1760000000

Ví dụ KHÔNG hợp lệ:
""
"01700000000"
"+1700000000"
"-1"
"1700000000.0"
"1700000000000"  (13 chữ số milliseconds)
"1.7e9"
"2023-11-14T22:13:20Z"
" 1700000000"
"1700000000 "
```

Đây là grammar **1–12 chữ số**, trong đó số 0 chỉ được biểu diễn bằng đúng `"0"`. Cách viết tương đương trong Java regex:

```java
private static final Pattern UNIX_SECONDS =
        Pattern.compile("(?:0|[1-9][0-9]{0,11})");
```

**Lưu ý phạm vi:** grammar 12 chữ số là lựa chọn có giới hạn cho profile này, không phải mệnh đề “Unix timestamps luôn dài tối đa 12 chữ số”. Ta cũng giới hạn năm lịch hỗ trợ ở phía verifier, thay vì mặc nhiên nhận mọi số mà kiểu `long` chứa được.

| Trường hợp | Chấp nhận về format? | Lý do |
|---|---|---|
| `X-Timestamp: 1700000000` | Có | Decimal seconds chuẩn, không leading zero |
| `X-Timestamp: 0` | Có | Cách biểu diễn chuẩn của mốc epoch; thường bị **time-window** từ chối |
| `X-Timestamp: 01700000000` | Không | Leading zero, nhiều biểu diễn cùng giá trị |
| `X-Timestamp: 1700000000.000` | Không | Phần lẻ không thuộc version này |
| `X-Timestamp: 1700000000000` | Không | 13 chữ số, thường là milliseconds |
| `X-Timestamp: +1700000000` | Không | Dấu `+` ngoài grammar |
| `X-Timestamp: ١٧٠٠٠٠٠٠٠٠` | Không | Unicode digits không phải ASCII `0-9` |
| `X-Timestamp: 1e9` | Không | Scientific notation ngoài grammar |
| `X-Timestamp: 1700000000, 1700000001` | Không | Nhiều giá trị/gộp header |
| Hai header `X-Timestamp` | Không | Duplicate header gây bất đồng parser |

**Cảnh báo về HTTP whitespace:** trên wire, HTTP có quy tắc OWS (*optional whitespace*) quanh field value. Đối với profile này, HTTP adapter phải công bố cách lấy **giá trị trường đã parse** và cấm giá trị chứa whitespace không thuộc contract. Không đọc raw header theo một quy tắc ở client nhưng verifier lại tự `trim()` theo quy tắc khác. Nếu cần cho phép OWS hợp lệ của HTTP, hãy xử lý duy nhất tại parser/ingress rồi đưa **giá trị đã chuẩn hóa theo contract** vào HMAC.

### Timestamp có được thiếu không?

Trong profile này, **không**: `X-Timestamp` là header bắt buộc, **xuất hiện đúng một lần**. Không gán mặc định `now()` nếu client quên gửi timestamp — làm vậy phá ràng buộc chữ ký giữa yêu cầu client tạo và thời điểm server xử lý.

## 4. Parse timestamp không có nghĩa là tin timestamp

Một server có thể làm ba kiểm tra khác nhau:

1. **Syntactic validation:** chuỗi khớp grammar ASCII decimal seconds?
2. **Temporal validation:** số giây đó có nằm trong cửa sổ lệch đồng hồ so với **`Clock` của server**?
3. **Authenticity validation:** giá trị timestamp ấy có nằm trong canonical bytes của request đã vượt qua **HMAC verification**?

Ba câu hỏi **không giống nhau**.

Ví dụ attacker gửi `X-Timestamp: 1760000000` với đúng 10 chữ số. Đây có thể là **cú pháp hợp lệ**, nhưng chưa chứng minh request được ký bằng secret hợp lệ hay timestamp còn trong cửa sổ chấp nhận. Ngược lại, một client có secret đúng vẫn có thể ký một request với timestamp quá cũ; chữ ký đúng **không tự bỏ qua time window**.

### Giữ nguyên chuỗi đã parse khi ký

Sai lầm:

```text
Client ký: x-timestamp:01700000000
Server parse thành long 1700000000
Server format lại: x-timestamp:1700000000
```

Nếu hợp đồng không chủ động định nghĩa normalize như vậy, hai bên đã đưa **bytes khác nhau** vào HMAC. Ví dụ `hmac-ts-v1` chọn cách dễ kiểm thử hơn:

- Reject `01700000000` ngay từ format.
- Giữ nguyên chuỗi ASCII đã hợp lệ, ví dụ `1700000000`.
- Dùng `Long.parseLong(text)` **chỉ để kiểm tra thời gian**, không dùng số parse để tự tạo một representation ký khác.
- Đưa `"x-timestamp:" + text` vào canonical request.

**Không chấp nhận cú pháp sai bằng cách “parse được thì format lại”.** Các thư viện JSON/JavaScript có thể mất chính xác khi chuyển các số rất lớn, còn một số ngôn ngữ có parsing nhạy với locale, leading zero hoặc overflow. Dạng text **một nghĩa duy nhất** giúp cross-language interoperability.

## 5. Cửa sổ đồng hồ: quá khứ và tương lai được phép lệch bao nhiêu?

Giả sử server quy định `W = 300` giây, tức **±5 phút**. Gọi:

- `t`: timestamp đã parse (epoch seconds);
- `now`: epoch seconds lấy từ **clock server tại thời điểm kiểm tra**.

Server chấp nhận **về thời gian** khi:

\[
now - W \leq t \leq now + W
\]

Hai biên **được chấp nhận** nếu hợp đồng chọn điều kiện `≤` như trên. Vượt biên một giây phải bị từ chối. Giá trị timestamp vẫn cần được **HMAC bảo vệ** và nonce mới.

| Trường hợp khi `W=300` | Chênh lệch `t-now` | Time-window |
|---|---:|---|
| Đúng giờ server | `0` | Pass |
| Client chậm 299 giây | `-299` | Pass |
| Client chậm đúng 300 giây | `-300` | Pass ở biên |
| Client chậm 301 giây | `-301` | Reject |
| Client nhanh đúng 300 giây | `+300` | Pass ở biên |
| Client nhanh 301 giây | `+301` | Reject |

Với clock server kiểm soát, `Instant.now(clock).getEpochSecond()` tạo thời điểm hiện tại UTC. Trong một hệ thống nhiều replica, các máy cần đồng bộ đồng hồ bằng cơ chế vận hành phù hợp, ví dụ NTP/chrony, và quan sát sai lệch clock. Nếu đồng hồ các replica khác nhau, cùng request có thể được replica A chấp nhận thời gian nhưng replica B từ chối.

### Không dùng `Math.abs` thiếu kiểm soát

Mẫu code:

```java
return Math.abs(timestamp - now) <= 300;
```

có thể gặp **integer overflow** với giá trị cực đoan hoặc runtime tạo timestamp sai. Với profile này, ta giới hạn timestamp và clock trong phạm vi epoch seconds phù hợp trước khi trừ, rồi so bằng:

```java
long delta = timestamp - now;
return delta >= -300 && delta <= 300;
```

Với `timestamp` và `now` đã được kiểm tra là nằm trong `[0, 253402300799]` (tới cuối năm 9999 UTC), phép trừ an toàn trong `long`. Không dùng `Integer.parseInt` vì số giây sẽ vượt giới hạn `int` trong năm 2038; sử dụng `long`.

### Vì sao server nên nhận thời gian từ `Clock`?

`Clock` giúp unit test **cố định thời điểm** mà không dùng `Thread.sleep` hay phụ thuộc giờ hệ điều hành, đồng thời giúp sản phẩm đặt chính sách clock injection rõ ràng.

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixed = Clock.fixed(
        Instant.parse("2026-11-28T00:00:00Z"), ZoneOffset.UTC);
long now = fixed.instant().getEpochSecond();
```

Ví dụ này chọn một thời điểm cố định **cho test**, không dùng `Clock.fixed` ở verifier production nếu không có lý do vận hành đặc biệt.

## 6. Timestamp nằm ở đâu trong canonical request HMAC?

Timestamp không phải dòng **đứng ngoài** chữ ký. Hợp đồng `hmac-ts-v1` minh họa endpoint `POST /v1/orders`:

```http
POST /v1/orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
Idempotency-Key: order-20261128-01
X-Client-Id: partner-17
X-Key-Id: k2
X-Timestamp: <unix-seconds>
X-Nonce: <base64url-nonce-128-bit>
X-Signature: <base64url-hmac-tag>

{"orderId":"O-42","amount":120000}
```

Các phần `<...>` là placeholder; client thật phải đưa giá trị timestamp, nonce và chữ ký hợp lệ. Body giả định là **đúng các byte UTF-8 hiển thị**, không có newline cuối.

| Thứ tự | Dòng canonical | Ràng buộc |
|---|---|---|
| 1 | `hmac-ts-v1` | Version và mục đích protocol cố định |
| 2 | `POST` | Method backend dự kiến thực thi |
| 3 | `/v1/orders` | Raw request-target được chấp nhận; profile không query |
| 4 | `host:api.example.test` | Public authority ingress đã kiểm tra |
| 5 | `content-type:application/json` | Media type dùng để parse body |
| 6 | `idempotency-key:order-20261128-01` | Chống sửa key nghiệp vụ khi giữ chữ ký |
| 7 | `x-client-id:partner-17` | Client claim để chọn đúng scope key |
| 8 | `x-key-id:k2` | Key version được ký |
| **9** | **`x-timestamp:<unix-seconds>`** | **Chính chuỗi ASCII đã validate** |
| 10 | `x-nonce:<nonce>` | Nonce CSPRNG được ký |
| 11 | `body-sha256:<digest>` | SHA-256 của exact raw body bytes |

Canonical string tương ứng:

```text
hmac-ts-v1
POST
/v1/orders
host:api.example.test
content-type:application/json
idempotency-key:order-20261128-01
x-client-id:partner-17
x-key-id:k2
x-timestamp:<unix-seconds>
x-nonce:<22-char-base64url>
body-sha256:<base64url-sha256-of-raw-body>
```

Quy tắc byte-level:

1. Nối các dòng bằng **LF** (`0x0A`), không LF cuối.
2. Mã hóa canonical text bằng **UTF-8 không BOM**.
3. Tên dòng header viết **lowercase cố định**, giá trị timestamp giữ nguyên sau format validation.
4. Hash **exact representation body bytes** bằng SHA-256, encode digest Base64URL không padding.
5. Dùng `HMAC-SHA256(secretKeyBytes, canonicalBytes)` trả về **32-byte tag**; encode tag Base64URL không padding thành **43 ký tự ASCII**.
6. `X-Signature` không nằm trong thông điệp cần ký để tránh tự tham chiếu.
7. `Idempotency-Key` được ký vì backend sử dụng nó để quyết định xử lý retry; nếu API không dùng header này thì phải phát hành hợp đồng khác phù hợp.

**Một hệ quả quan trọng:** đổi `X-Timestamp` sau khi ký, dù chỉ thêm số 0 ở đầu hoặc thay số giây, làm format sai hoặc canonical message khác nên chữ ký cũ không còn hợp lệ. Đồng hồ server không được tự điền timestamp thay cho client.

## 7. Timestamp, nonce và TTL: tính thời hạn lưu replay cho đúng

Một timestamp hợp lệ không đảm bảo request **chưa từng được xử lý**. Attacker có thể replay **nguyên method, URI, body, timestamp, nonce và signature** trong cửa sổ ±300 giây.

### Vì sao chỉ kiểm tra thời gian là chưa đủ?

```text
t = timestamp được client ký
now = t + 10 giây: request hợp lệ về thời gian, server xử lý
now = t + 11 giây: attacker gửi lại y hệt, vẫn hợp lệ về thời gian
```

Muốn chặn request thứ hai, phải lưu **nonce đã dùng**.

```mermaid
sequenceDiagram
    autonumber
    participant C as HMAC client
    participant V as Verifier
    participant K as Key store
    participant N as Shared nonce store
    participant B as Backend
    C->>C: Sinh Unix seconds timestamp và nonce CSPRNG
    C->>C: Ký canonical request có cả timestamp/nonce
    C->>V: HTTPS request + signature
    V->>V: Check format và cửa sổ thời gian
    V->>K: Lookup(env, clientId, keyId, audience)
    K-->>V: Secret + principal + key state
    V->>V: HMAC trên canonical bytes; so tag
    alt Tag hoặc key sai
        V-->>C: Reject authentication
    else HMAC hợp lệ
        V->>N: Atomic insert-if-absent(scope, nonce, TTL)
        alt Đã có nonce hoặc nonce store lỗi
            V-->>C: Reject replay / fail closed
        else Nonce mới
            N-->>V: Claimed
            V->>B: Authenticated principal + verified request
            B->>B: Authorization và idempotency
            B-->>C: Business response
        end
    end
```

### Cách chọn TTL không quá ngắn

Giả sử verifier chấp nhận `t` khi `now - W ≤ t ≤ now + W`. Một request có timestamp `t` có thể **đến sớm nhất tại `now = t - W`**, rồi vẫn còn hợp lệ **tới `now = t + W`**.

Do đó khoảng tồn tại có thể lên tới **`2W` giây**, không chỉ `W`.

```text
W = 300 giây
t - 300       t            t + 300
   |----------|---------------|
   <-------- cửa sổ 600 giây ------->
```

Nếu nonce được claim khi request đến sớm `t - 300` mà store xóa sau 300 giây, attacker có thể replay cùng nonce vào nửa sau của cửa sổ **khi nonce đã hết TTL**. Đây là lỗi replay protection ngay cả khi HMAC, timestamp format và time-window code đều đúng.

Các lựa chọn:

- **TTL tính theo thời điểm hết hợp lệ của chính timestamp**, ví dụ giữ nonce ít nhất tới `t + W`, cộng biên an toàn cho clock skew giữa replica, TTL resolution và xử lý mạng.
- Hoặc đặt TTL cố định **ít nhất `2W + margin`** tính từ lúc claim; với `W=300` có thể chọn ví dụ **`605` giây** trong lab có đồng hồ đồng bộ và margin 5 giây.
- Nếu deadline theo `t + W` và clock giữa replica không được đồng bộ, phải phân tích **worst-case skew**; không sao chép nguyên con số lab vào production.
- Kho nonce phải **dùng chung mọi replica** và dùng `insert-if-absent` **nguyên tử**; `GET` rồi `SET` là race condition.
- Scope nonce nên bền vững qua **key rotation** đối với cùng principal/client, ví dụ `(environment, audience, clientId, nonce)`, thay vì chia theo key ID một cách tạo cơ hội replay.

**Khi nonce store không sẵn sàng, endpoint nhạy cảm nên fail closed**. Chấp nhận bỏ qua nonce vì “timestamp còn mới” làm giảm bảo vệ chống replay xuống chỉ còn cửa sổ thời gian.

## 8. Java 17+: tạo, parse, kiểm tra và ký timestamp đúng định dạng

Ví dụ sau kết hợp phần định dạng thời gian với canonical request, scoped key lookup, HMAC verification và vị trí dành cho nonce store. Trong production, HTTP adapter phải lấy đúng **method, request-target, public Host, headers và raw body thực nhận**, phát hiện duplicate trước khi tạo `RequestSnapshot`.

### 8.1. Mã minh họa tự chứa

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

public final class SignedTimestampV1 {
    private static final String CONTRACT = "hmac-ts-v1";
    private static final String HOST = "api.example.test";
    private static final String TARGET = "/v1/orders";
    private static final String AUDIENCE = "orders-api";
    private static final long WINDOW_SECONDS = 300L;
    private static final long NONCE_TTL_SECONDS = 605L;
    // Giới hạn thời gian hỗ trợ của ví dụ: 9999-12-31T23:59:59Z.
    private static final long MAX_EPOCH_SECONDS = 253402300799L;
    private static final int MAX_BODY_BYTES = 16384;

    private static final Pattern TS =
            Pattern.compile("(?:0|[1-9][0-9]{0,11})");
    private static final Pattern ID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");
    private static final Pattern NONCE =
            Pattern.compile("[A-Za-z0-9_-]{22}");
    private static final Pattern SIG =
            Pattern.compile("[A-Za-z0-9_-]{43}");
    private static final Base64.Encoder B64 =
            Base64.getUrlEncoder().withoutPadding();

    private SignedTimestampV1() {}

    // HTTP adapter chịu trách nhiệm header cardinality/proxy trust.
    // Defensive copy: không cho sửa body sau khi đã tạo snapshot.
    public record RequestSnapshot(
            String method, String rawTarget, String publicHost,
            String contentType, String idempotencyKey,
            String clientId, String keyId,
            String timestampText, String nonceText, byte[] rawBody) {
        public RequestSnapshot {
            if (rawBody == null) {
                throw new IllegalArgumentException("Missing body");
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
        Optional<KeyRecord> find(String environment, String clientId,
                                 String keyId, String audience);
    }

    // Production: atomic insert-if-absent có TTL, shared giữa replicas.
    public interface NonceStore {
        boolean claim(String scope, String nonce, long ttlSeconds);
    }

    // CHỈ parse cú pháp epoch seconds đã công bố, không trim/reformat.
    public static long parseUnixSeconds(String text) {
        if (text == null || !TS.matcher(text).matches()) {
            throw new IllegalArgumentException("Invalid timestamp format");
        }
        final long parsed;
        try {
            parsed = Long.parseLong(text);
        } catch (NumberFormatException badNumber) {
            throw new IllegalArgumentException("Timestamp out of range");
        }
        if (parsed < 0 || parsed > MAX_EPOCH_SECONDS) {
            throw new IllegalArgumentException("Timestamp unsupported");
        }
        return parsed;
    }

    // Clock kiểm soát giúp test biên -300, +300 chính xác.
    public static boolean isWithinWindow(String timestampText, Clock clock) {
        final long timestamp;
        try {
            timestamp = parseUnixSeconds(timestampText);
        } catch (IllegalArgumentException invalidTime) {
            return false;
        }

        long now = clock.instant().getEpochSecond();
        if (now < 0 || now > MAX_EPOCH_SECONDS) {
            return false;
        }
        // Hai toán hạng đều bị chặn trong [0, 253402300799].
        long difference = timestamp - now;
        return difference >= -WINDOW_SECONDS &&
               difference <= WINDOW_SECONDS;
    }

    private static byte[] decodeCanonical(
            String text, Pattern pattern, int expectedBytes) {
        if (text == null || !pattern.matcher(text).matches()) {
            throw new IllegalArgumentException("Invalid Base64URL grammar");
        }
        final byte[] value;
        try {
            value = Base64.getUrlDecoder().decode(text);
        } catch (IllegalArgumentException invalid) {
            throw new IllegalArgumentException("Invalid Base64URL value");
        }
        if (value.length != expectedBytes ||
                !B64.encodeToString(value).equals(text)) {
            throw new IllegalArgumentException("Noncanonical Base64URL");
        }
        return value;
    }

    private static void validate(RequestSnapshot r) {
        if (r == null || !"POST".equals(r.method()) ||
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
                r.rawBody().length > MAX_BODY_BYTES) {
            throw new IllegalArgumentException("Invalid signed request");
        }
        parseUnixSeconds(r.timestampText());
        decodeCanonical(r.nonceText(), NONCE, 16);
    }

    public static byte[] canonicalBytes(RequestSnapshot r)
            throws GeneralSecurityException {
        validate(r);
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(r.rawBody());
        String canonical = String.join("\n",
                CONTRACT,
                "POST",
                TARGET,
                "host:" + HOST,
                "content-type:application/json",
                "idempotency-key:" + r.idempotencyKey(),
                "x-client-id:" + r.clientId(),
                "x-key-id:" + r.keyId(),
                // Đưa đúng TEXT đã validate vào HMAC.
                "x-timestamp:" + r.timestampText(),
                "x-nonce:" + r.nonceText(),
                "body-sha256:" + B64.encodeToString(digest));
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] computeHmac(
            byte[] secret, RequestSnapshot r)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(canonicalBytes(r));  // 32 byte tag.
    }

    // Chỉ dùng để tạo fixture hoặc chạy demo client.
    public static String signForTest(
            byte[] secret, RequestSnapshot request)
            throws GeneralSecurityException {
        return B64.encodeToString(computeHmac(secret, request));
    }

    public static Optional<String> authenticate(
            RequestSnapshot request, String encodedSignature,
            Clock clock, String serverEnvironment,
            KeyStore keys, NonceStore nonces)
            throws GeneralSecurityException {
        final byte[] suppliedTag;
        try {
            validate(request);
            suppliedTag = decodeCanonical(encodedSignature, SIG, 32);
        } catch (IllegalArgumentException malformed) {
            return Optional.empty();
        }

        // Có thể reject timestamp quá hạn sớm, nhưng chỉ sau HMAC
        // đúng mới coi timestamp là đã được người nắm secret ký.
        if (!isWithinWindow(request.timestampText(), clock)) {
            return Optional.empty();
        }

        Optional<KeyRecord> candidate = keys.find(
                serverEnvironment, request.clientId(),
                request.keyId(), AUDIENCE);
        if (candidate.isEmpty()) return Optional.empty();

        KeyRecord key = candidate.get();
        if (!key.canVerify() ||
                !serverEnvironment.equals(key.environment()) ||
                !AUDIENCE.equals(key.audience()) ||
                !request.clientId().equals(key.clientId()) ||
                !request.keyId().equals(key.keyId()) ||
                key.principal() == null ||
                key.secret() == null || key.secret().length < 16) {
            return Optional.empty();
        }

        byte[] expected = computeHmac(key.secret(), request);
        if (!MessageDigest.isEqual(expected, suppliedTag)) {
            return Optional.empty();
        }

        // Nonce scope không chứa keyId để giữ thống nhất qua rotation.
        String scope = serverEnvironment + "|" + AUDIENCE +
                "|" + key.clientId();
        if (!nonces.claim(scope, request.nonceText(), NONCE_TTL_SECONDS)) {
            return Optional.empty();
        }

        return Optional.of(key.principal());  // Authn; chưa authz.
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        Clock fixed = Clock.fixed(
                Instant.parse("2026-11-28T00:00:00Z"), ZoneOffset.UTC);
        long now = fixed.instant().getEpochSecond();

        // Kiểm thử biên inclusive và vượt biên một giây.
        if (!isWithinWindow(Long.toString(now - 300), fixed) ||
                !isWithinWindow(Long.toString(now + 300), fixed) ||
                isWithinWindow(Long.toString(now - 301), fixed) ||
                isWithinWindow(Long.toString(now + 301), fixed)) {
            throw new AssertionError("Wrong timestamp window");
        }

        // Milliseconds/leading-zero/ISO string đều không được nhận.
        for (String wrong : new String[] {
                Long.toString(now * 1000), "0" + now,
                "+1700000000", "2026-11-28T00:00:00Z", "1.7e9"
        }) {
            try {
                parseUnixSeconds(wrong);
                throw new AssertionError("Accepted bad format: " + wrong);
            } catch (IllegalArgumentException expected) {
                // PASS.
            }
        }

        byte[] secret = new byte[32];
        new SecureRandom().nextBytes(secret);
        byte[] nonceBytes = new byte[16];
        new SecureRandom().nextBytes(nonceBytes);

        RequestSnapshot request = new RequestSnapshot(
                "POST", TARGET, HOST, "application/json",
                "order-20261128-01", "partner-17", "k2",
                Long.toString(now), B64.encodeToString(nonceBytes),
                "{\"orderId\":\"O-42\",\"amount\":120000}"
                    .getBytes(StandardCharsets.UTF_8));

        KeyStore keys = (env, client, kid, audience) ->
                "production".equals(env) &&
                "partner-17".equals(client) &&
                "k2".equals(kid) &&
                AUDIENCE.equals(audience)
                ? Optional.of(new KeyRecord(
                    env, client, kid, audience,
                    "partner-17", true, secret))
                : Optional.empty();

        // Fixture in-memory: KHÔNG có TTL và KHÔNG chia sẻ replica.
        Set<String> seen = ConcurrentHashMap.newKeySet();
        NonceStore nonces = (scope, nonce, ttl) ->
                seen.add(scope + "|" + nonce);

        String signature = signForTest(secret, request);
        if (!"partner-17".equals(authenticate(
                request, signature, fixed, "production",
                keys, nonces).orElse(null))) {
            throw new AssertionError("Valid request rejected");
        }

        // Chữ ký đúng nhưng nonce đã dùng: bị chặn.
        if (authenticate(request, signature, fixed, "production",
                keys, nonces).isPresent()) {
            throw new AssertionError("Replay accepted");
        }

        // Kẻ trung gian sửa timestamp nhưng giữ tag cũ: HMAC sai.
        RequestSnapshot changedTimestamp = new RequestSnapshot(
                request.method(), request.rawTarget(), request.publicHost(),
                request.contentType(), request.idempotencyKey(),
                request.clientId(), request.keyId(),
                Long.toString(now + 1), request.nonceText(),
                request.rawBody());
        if (authenticate(changedTimestamp, signature, fixed,
                "production", keys, nonces).isPresent()) {
            throw new AssertionError("Changed timestamp accepted");
        }

        System.out.println("Timestamp format + HMAC checks: PASS");
    }
}
```

### 8.2. Tại sao mã giữ nguyên timestamp text?

`parseUnixSeconds()` xác nhận một **dạng biểu diễn duy nhất**, còn `isWithinWindow()` dùng giá trị số để xét ranh giới thời gian. `canonicalBytes()` dùng lại **`r.timestampText()` đã kiểm tra**, không format lại timestamp sau parse.

- `1700000000` có cú pháp hợp lệ, nhưng **không bảo đảm còn mới**.
- `01700000000` bị loại trước HMAC, không được âm thầm sửa thành `1700000000`.
- Chuỗi 13 chữ số milliseconds bị loại chứ không tự chia `1000`.
- Server tạo `Clock` và `serverEnvironment` **từ cấu hình tin cậy**, không nhận các giá trị ấy từ client.
- Java `long` tránh vấn đề `int`/Year 2038 trong quá trình parse.
- Dùng `MessageDigest.isEqual` để so **tag HMAC nhị phân 32 byte** sau khi signature Base64URL đã được decode và kiểm tra format.
- `NonceStore` là interface; demo in-memory chỉ dùng minh họa một tiến trình, **không đạt yêu cầu TTL/đồng bộ nhiều replica** ở production.
- `KeyRecord`/`KeyStore` là mô hình lookup; production cần secret manager/KMS, cache invalidation và key-state enforcement.

**Một giới hạn quan trọng:** code không parse HTTP network bytes; phía HTTP adapter phải kiểm tra **đúng một `X-Timestamp`**, đúng một `X-Signature`, Host/`:authority`, method, request-target, các signed headers, kích thước body và HTTP framing. Nó cũng chưa thực hiện authorization của nghiệp vụ.

### 8.3. Nếu client Java phải tạo timestamp để gửi

```java
import java.time.Clock;
import java.time.Instant;

// Unix epoch seconds, ASCII decimal theo hợp đồng:
Clock clock = Clock.systemUTC();
String timestampText =
        Long.toString(Instant.now(clock).getEpochSecond());

// Không dùng:
// String.valueOf(System.currentTimeMillis())  // milliseconds!
// LocalDateTime.now().toString()                // không có mốc UTC rõ
```

**Điểm đặt timestamp:** tạo sát thời điểm thực sự ký/gửi request, sau khi đã chốt body/URI/headers. Nếu request được giữ lâu trong queue hoặc retry muộn, phải xây dựng lại timestamp **và chữ ký** khi gửi theo policy; không chỉ sửa timestamp header mà giữ tag cũ.

## 9. Đồng bộ đồng hồ, retry và phân tích lỗi thời gian

### Clock skew là một điều kiện vận hành

Đồng hồ hệ điều hành có thể chạy lệch, được chỉnh bởi NTP hoặc nhảy thời gian do cấu hình. Một verifier cần:

- Sử dụng nguồn clock đáng tin ở host và theo dõi drift, sync status.
- Cấu hình rõ `W` theo yêu cầu bảo mật và độ trễ mạng; cửa sổ lớn hơn **tăng cơ hội replay** nếu nonce store bị lỗi, cửa sổ quá nhỏ tạo false rejects.
- Không lấy `Date` HTTP header hoặc timestamp client khai làm **đồng hồ server hiện tại**.
- Dùng cùng time policy trên các replica, nhất là khi một request có thể được retry tới các vùng/cluster khác nhau.
- Giám sát tỷ lệ lỗi `timestamp_out_of_window`, nhưng **không tiết lộ chi tiết các thông tin về key hoặc server internals** qua response công khai.

**Không có con số ±300 giây đúng cho mọi hệ thống.** Đây là ví dụ thường được dùng để minh họa tradeoff; sản phẩm phải chọn window từ SLO latency, độ lệch clock thực tế và threat model.

### Phân biệt retry với replay

Giả sử một request tạo đơn được xử lý nhưng response bị mất:

- Retry **nguyên request** với timestamp/nonce/tag cũ: HMAC có thể vẫn đúng, nhưng nonce store phải chặn phát lại.
- Retry với **timestamp/nonce mới**: client phải tính **HMAC tag mới**. Replay store có thể cho qua như request mới, nhưng backend vẫn có nguy cơ tạo **đơn hàng trùng**.
- Một `Idempotency-Key` đã ký và bảng idempotency atomically gắn với principal, nội dung thao tác có thể ngăn side effect bị lặp. Đây là bài toán **khác** với timestamp/nonce.

Nếu request timeout, client cần chính sách kiểm tra kết quả/tra cứu theo idempotency key, không được tự tắt replay protection để “retry cho dễ”.

### Lỗi format không phải lúc nào cũng là lỗi clock

| Hiện tượng | Nguyên nhân điển hình | Cách xác minh |
|---|---|---|
| Thời gian lệch khoảng hàng chục năm | Client gửi milliseconds, server hiểu seconds | Kiểm tra số chữ số và đơn vị |
| Client gửi `2026-11-28T...Z` | Client dùng ISO text thay epoch seconds | Kiểm tra schema/scheme version |
| Thêm số 0 vào đầu | Serializer format số cố định chiều dài | Reject leading zero, sửa client |
| Client/server cùng timestamp nhưng HMAC sai | Timestamp value bị trim/reformat, canonical khác | So canonical bytes trong môi trường test |
| Chỉ một replica reject ngoài window | Clock skew hoặc cấu hình W không đồng nhất | Kiểm tra sync/status của replica |
| Request trước pass, sau lại fail | Timestamp hết hạn hoặc nonce đã được claim | Phân biệt error class qua metrics bảo vệ |
| Request format đúng, nhưng bị từ chối | Key revoke, MAC sai, nonce trùng, thiếu quyền | Phân tích pipeline theo tầng; không đổ hết cho clock |

## 10. Proxy/gateway và parser có thể làm hỏng timestamp thế nào?

`X-Timestamp` là một HTTP header dạng text, nên nhiều hop có thể tác động trước khi verifier dựng canonical request.

| Tình huống | Rủi ro | Cách phòng vệ |
|---|---|---|
| Hai `X-Timestamp` | Gateway dùng giá trị đầu, verifier/backend dùng giá trị cuối | Reject duplicate trước khi chuyển thành một String |
| `X-Timestamp: 1700000000, 1700000001` | Nhiều giá trị bị gộp | Reject theo grammar một timestamp |
| Header name khác case | `X-Timestamp` và `x-timestamp` bị xem như hai header ở một adapter sai | Dùng HTTP parser chuẩn, phát hiện trùng không phân biệt case |
| Whitespace ngoài contract | `1700000000 ` hoặc tab | Không canonicalize bằng trim tùy ý; chỉ dùng policy chung |
| Middleware đổi milliseconds → seconds | Server ký dạng khác client | Một định dạng duy nhất end-to-end, không đoán đơn vị |
| Gateway thêm timestamp mới | Header timestamp không còn do client ký | Không sửa signed field sau khi client ký |
| Header bị strip | Verifier không có dữ liệu gốc | Reject hoặc sửa cấu hình đường chuyển tiếp |
| Replay qua nhiều replica | Nonce chỉ nằm trong RAM mỗi máy | Shared atomic nonce store với TTL đúng |
| HTTP client retry/redirect tự động | Gửi lại signature cũ hoặc chuyển sang host khác | Tắt automatic unsafe retry/redirect; re-sign có kiểm soát |
| Host/path/body bị rewrite | HMAC mismatch dù timestamp đúng | Bảo vệ toàn bộ signed semantics, không chỉ timestamp |

Trong HTTP/1.1 và HTTP/2, tên header không phân biệt chữ hoa/chữ thường; HTTP/2 có quy tắc tên lowercase trên wire. Canonicalizer nên dùng **tên dòng cố định** `x-timestamp:` và giá trị **được parser xác nhận**, không hash nguyên dòng raw header `X-Timestamp: ` với spacing thay đổi.

**Bất biến quan trọng:** giá trị timestamp verifier đưa vào HMAC phải là **giá trị xác thực từ request thực nhận theo hợp đồng**, không phải một chuỗi do backend hoặc proxy tự chế; request mà handler thực thi phải tương ứng với method, URI, Host, header và body đã được xác minh.

## 11. Key rotation và authorization vẫn cần dù format timestamp đúng

### Key rotation

Client có thể chuyển từ khóa `k1` sang `k2`. Verifier dùng `(environment, clientId, keyId, audience)` để chọn secret, kiểm tra key state và principal. Header `X-Key-Id` phải nằm trong canonical bytes đã ký.

- Trong giai đoạn rotation, có thể tạm cho phép `k1` và `k2` theo chính sách với thời hạn cụ thể.
- Khi `k1` bị thu hồi, request dùng nó phải bị từ chối **ngay theo chính sách**, kể cả khi timestamp hợp lệ và HMAC tính ra đúng.
- Không cho rằng vì timestamp nằm trong ±5 phút thì key đã revoke có thể tiếp tục được nhận.
- Nonce scope không nên vô tình tách theo `keyId` nếu một principal có thể replay logic request qua hai version key.
- Nếu secret bị lộ, attacker có thể tạo timestamp hiện tại, nonce mới và chữ ký mới: replay store **không ngăn** việc tạo request giả với secret bị lộ; phải thu hồi và luân chuyển secret.

### Authentication khác authorization

Một request có timestamp hợp lệ và HMAC khớp với khóa của `partner-17` chỉ chứng minh đã sử dụng **khóa đúng scope** để ký dữ liệu. Backend vẫn phải kiểm tra `partner-17` có quyền trên resource/tenant/operation thực tế không.

Ví dụ: `partner-17` có thể ký request hợp lệ để sửa đơn `O-99`, nhưng nếu đơn thuộc `partner-42`, backend phải **deny**. Time window, HMAC và `MessageDigest.isEqual` không tạo “quyền admin” hoặc quyền truy cập chéo tenant.

### Thứ tự kiểm tra cần nhớ

```text
HTTP parse / signed-field format
       -> timestamp format và server time-window (prefilter)
       -> scoped key lookup + key state
       -> server-side canonicalization + HMAC comparison
       -> atomic nonce claim + TTL
       -> authenticated principal
       -> authorization / validation / idempotency / transaction
```

Có thể thay đổi vị trí prefilter theo threat model để giảm key enumeration/timing khác biệt, nhưng **không được ghi nonce hoặc tạo principal khi HMAC chưa được xác minh**.

## 12. Ma trận kiểm thử `Timestamp format`

| Kiểm thử | Input/thao tác | Kết quả kỳ vọng trong `hmac-ts-v1` |
|---|---|---|
| Decimal seconds chuẩn | Timestamp thập phân không leading zero | Pass **format**, còn phải kiểm tra window và MAC |
| Epoch 0 | `0` | Pass format; hiện tại thường fail window |
| Empty header value | `X-Timestamp:` | Reject format |
| Header thiếu | Không có `X-Timestamp` | Reject |
| Header trùng | Hai `X-Timestamp` kể cả khác case | Reject tại HTTP adapter |
| Comma-joined | `1700000000,1700000001` | Reject |
| Milliseconds | `1700000000000` | Reject 13 chữ số |
| Microseconds | `1700000000000000` | Reject |
| ISO 8601/RFC 3339 | `2023-11-14T22:13:20Z` | Reject trong version này |
| Unix số âm | `-1` | Reject |
| Dấu cộng | `+1700000000` | Reject |
| Leading zero | `01700000000` | Reject |
| Decimal/float | `1700000000.0` | Reject |
| Exponential | `1.7e9` | Reject |
| Non-ASCII digits | Unicode digit ngoài `0-9` | Reject |
| Header trailing space | `1700000000 ` ngoài contract | Reject hoặc xử lý OWS duy nhất tại adapter theo profile |
| Đồng hồ khớp | `t=now` | Pass time-window |
| Chậm 300 giây | `t=now-300` | Pass tại biên |
| Chậm 301 giây | `t=now-301` | Reject |
| Nhanh 300 giây | `t=now+300` | Pass tại biên |
| Nhanh 301 giây | `t=now+301` | Reject |
| Sửa timestamp sau ký | Giữ tag cũ, tăng `t` lên 1 giây | HMAC mismatch |
| Timestamp ngoài window nhưng HMAC đúng | Client tự ký timestamp quá cũ | Reject theo time policy |
| Replay trong window | Gửi nguyên request/tag/nonce lần hai | Reject khi nonce đã được claim |
| Replay khác replica | Hai request cùng nonce đồng thời | Tối đa một được xử lý với atomic store |
| Nonce TTL quá ngắn | Claim lúc `t-W`, replay gần `t+W` | Test phát hiện replay lọt qua; sửa TTL |
| Key bị thu hồi | Tag đúng, timestamp hiện tại, key `k1` revoke | Reject theo key policy |
| HTTP proxy sửa method/URI/Host/body | Timestamp không đổi, signed fields đổi | HMAC mismatch hoặc reject |
| HMAC đúng nhưng sai quyền | Principal A gửi tới resource B | Authn pass; authz deny |
| Retry dùng timestamp/nonce mới | Tạo lại tag mới cùng Idempotency-Key | Backend chống thực thi trùng bằng idempotency policy |

### Kiểm thử theo thời điểm cố định

Dùng `Clock.fixed` để xác nhận `-301, -300, 0, +300, +301` mà không chờ thời gian thực. Test parser **độc lập** với time window: `0` là một input hợp cú pháp nhưng không phù hợp với thời điểm server thông thường; `1700000000000` bị reject **ngay format**, không phải “đợi xem timestamp quá xa tương lai”.

Khi test hệ thống qua gateway, dùng client HTTP thật để kiểm tra duplicate header, whitespace, retries, signed header propagation và các replica có clock khác nhau. Unit test `parseUnixSeconds()` chỉ chứng minh một phần rất nhỏ.

## 13. Bài tập thực hành: chuẩn hóa Timestamp cho Orders API

Hệ thống `orders-api` nhận `POST /v1/orders` qua HTTPS và API gateway. Client và verifier chia sẻ secret HMAC-SHA256 theo `clientId/keyId`; verifier có ba replica; server chạy nhiều tenant; nonce store dùng chung.

**Yêu cầu:**

1. **Định nghĩa wire grammar:** chọn Unix epoch seconds, ASCII decimal, không leading zero, giới hạn chữ số và giá trị; giải thích vì sao không nhận milliseconds và ISO string trong cùng version.
2. **Lập canonical request:** chứa version, method, raw target, Host, Content-Type, Idempotency-Key, client/key ID, `x-timestamp`, nonce và SHA-256 raw body; chốt LF/UTF-8 không BOM.
3. **Viết Java client:** dùng `Clock.systemUTC()`/`Instant.now(clock).getEpochSecond()` tạo timestamp, nonce 16 byte CSPRNG, dựng canonical và ký bằng `javax.crypto.Mac`. Gửi đúng những bytes đã ký qua HTTPS.
4. **Viết verifier:** reject duplicate `X-Timestamp`, parse strict grammar, kiểm tra clock window ±300, scoped key lookup, tính expected MAC và so tag 32 byte với `MessageDigest.isEqual`.
5. **Dựng shared nonce store:** dùng atomic insert-if-absent + TTL đủ bao phủ timestamp đến sớm; giải thích vì sao khi `W=300` thì TTL `300` giây là không đủ trong trường hợp xấu nhất.
6. **Kiểm thử Clock.fixed:** xét `t=now±300` và `t=now±301`; kiểm tra `0` pass format nhưng không pass time-window. Thử timestamp milliseconds, leading zero, dấu cộng, dấu âm, ISO string, scientific notation.
7. **Thử replay và rotation:** gửi request tới hai replica, xoay `k1 → k2`, revoke key cũ và chứng minh không còn xác minh được request dù timestamp còn mới.
8. **Kiểm thử gateway:** header bị trùng, đổi timestamp sau khi ký, Host/path bị rewrite, body bị serialize lại, HTTP client retry/redirect tự động.
9. **Phân quyền và idempotency:** client ký thành công request nhắm resource của tenant khác thì vẫn bị deny; retry với timestamp/nonce mới không tạo đơn trùng nhờ Idempotency-Key đã ký và transaction.

**Tiêu chí hoàn thành:** chứng minh được **timestamp hợp format → timestamp trong cửa sổ server → giá trị timestamp nằm trong canonical bytes được HMAC bảo vệ → nonce chưa dùng → authorization hợp lệ**. Đồng thời giải thích được **timestamp format đúng không tự đồng nghĩa chữ ký đúng, request mới hoặc request được cấp quyền**.

---

## Ghi nhớ

Trong module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, **Timestamp format** phải là **một hợp đồng byte-level**: ví dụ **Unix epoch seconds dạng ASCII decimal không leading zero**, không nhầm milliseconds hoặc chuỗi ISO 8601. Server phải parse nghiêm ngặt, kiểm tra cửa sổ thời gian theo **clock của server**, đưa **chính timestamp text đã validate** vào canonical request HMAC và chặn replay bằng **nonce store nguyên tử với TTL đủ dài**. Định dạng đúng không thay thế xác minh MAC, key rotation, kiểm thử proxy/gateway hay **authorization theo tài nguyên**.
