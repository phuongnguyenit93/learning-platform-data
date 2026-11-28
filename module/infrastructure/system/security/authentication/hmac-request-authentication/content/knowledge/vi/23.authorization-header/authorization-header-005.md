# Timestamp field trong Authorization header của HTTP HMAC authentication

**Timestamp field** là tham số mang **thời điểm client ký HTTP request**. Khi giao thức đặt timestamp **ngay trong header `Authorization`**, verifier phải parse đúng trường này từ **credential HMAC**, đưa **chính giá trị đã parse** vào canonical request rồi kiểm tra độ mới theo **server clock**. Không được lấy timestamp từ một header khác, tự chia milliseconds cho 1000, sửa format mơ hồ hoặc cho phép một proxy thay timestamp mà chữ ký vẫn được coi là đúng.

Bài thuộc chương **Authorization header**, module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Module học cách xác thực request bằng HMAC với shared secret và canonical request ràng buộc method, URI, signed headers/body; thực hành xác minh signature, timestamp/nonce chống replay, quản lý key rotation, thử nghiệm proxy/gateway và phân biệt authentication với authorization. Trọng tâm ở đây là **vị trí, cú pháp, cách parse và ràng buộc mật mã của timestamp field trong Authorization header**; phép kiểm tra freshness là bước tiếp nối không thể thiếu.

**Thông điệp chính:** Không có một định dạng `Authorization: HMAC ...` với trường timestamp được mọi HTTP API sử dụng thống nhất. Bài định nghĩa **hợp đồng minh họa HMAC-V1**; hệ thống thật phải công bố tên auth scheme, tên tham số, encoding, signed components, clock policy, canonical format và lỗi xử lý **trước khi triển khai client/verifier**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của `Authorization` và `ts` (timestamp) trong một custom HMAC authentication scheme.
2. Phân biệt **timestamp nằm trong auth-param** với `Date`, `X-Timestamp` hoặc `X-Forwarded-Date`; không trộn nguồn dữ liệu đã ký với nguồn khác.
3. Thiết kế cú pháp timestamp **Unix epoch seconds, ASCII decimal, không leading zero**, parse chặt và xử lý overflow.
4. Chứng minh vì sao timestamp phải được đưa vào **canonical request bytes** để ngăn attacker “làm mới” một chữ ký cũ bằng cách sửa text trong `Authorization`.
5. Thiết kế parser chống **duplicate Authorization, duplicate auth-param, dấu phẩy trong quoted-string, whitespace, ký tự điều khiển và header smuggling**.
6. Thực hành Java 17: tạo `Authorization: HMAC-V1 ...`, parse timestamp, kiểm tra cửa sổ `now-300 <= ts <= now+60`, HMAC-SHA256 và nonce store.
7. Kiểm thử clock skew, replay, key rotation, proxy/gateway và phân quyền sau khi xác thực.

## 2. Authorization header chứa timestamp như thế nào?

Header `Authorization` mang **credentials** theo một HTTP authentication scheme. Ví dụ quen thuộc là `Authorization: Bearer ...`; với HMAC, API có thể thiết kế một **scheme riêng** chứa client ID, key ID, timestamp, nonce và signature.

Hợp đồng của bài dùng **một field line `Authorization`** theo cú pháp minh họa:

~~~http
POST /v1/payments?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
Authorization: HMAC-V1 client="partner-42", keyid="key-2026-11", ts="1795831200", nonce="00112233445566778899aabbccddeeff", sig="<base64-hmac-sha256-tag>"

{"orderId":"ord-123","amount":50000}
~~~

Giá trị `<base64-hmac-sha256-tag>` là **placeholder**; request thật thay nó bằng Base64 chuẩn padded của HMAC-SHA256 full tag 32 byte (44 ký tự). Timestamp `1795831200` tương ứng **2026-11-28 02:00:00 UTC**, dưới dạng **Unix epoch seconds**.

Trong ví dụ, `Authorization` dùng các auth-param **được đặt trong dấu ngoặc kép**:

| Tham số | Ví dụ | Vai trò |
| --- | --- | --- |
| `client` | `partner-42` | Gợi ý identity để lookup key; **chưa đáng tin** trước HMAC. |
| `keyid` | `key-2026-11` | Chọn shared secret và policy phiên bản khóa. |
| **`ts`** | **`1795831200`** | **Thời điểm client ký; được HMAC ràng buộc và kiểm tra freshness.** |
| `nonce` | `00112233445566778899aabbccddeeff` | Giá trị ngẫu nhiên cho replay guard, phải nằm trong canonical. |
| `sig` | `<base64-tag>` | Chữ ký truyền qua header; decode thành byte trước so sánh HMAC. |

**`Authorization` là tên của HTTP credential field, không phải kết luận client đã được cấp quyền.** Verifier chỉ biết credential hợp lệ sau khi kiểm tra HMAC, freshness, nonce và key policy. Backend vẫn phải thực hiện **authorization** đối với tenant, action và resource.

### 2.1. Vì sao đặt timestamp trong Authorization thay vì header riêng?

Hai cách đều có thể được thiết kế an toàn **nếu contract rõ ràng**:

~~~http
# Cách A — timestamp là auth-param của Authorization:
Authorization: HMAC-V1 client="partner-42", keyid="key-2026-11", ts="1795831200", nonce="00112233445566778899aabbccddeeff", sig="<base64-tag>"

# Cách B — một contract khác dùng header riêng:
X-Timestamp: 1795831200
X-Signature: <base64-tag>
~~~

**Không được trộn A và B tùy hứng.** Với hợp đồng A, verifier lấy timestamp **chỉ** từ `ts` của `Authorization`. Nếu client đồng thời gửi `X-Timestamp: 1795831300`, một proxy hoặc middleware không được lấy giá trị ấy thay `ts`. Nên reject các nguồn timestamp cạnh tranh không thuộc hợp đồng trên endpoint được bảo vệ, hoặc bỏ qua chúng theo policy đã công bố nhưng không dùng cho xác minh.

Ưu điểm của cách A là credential metadata nằm cùng một nơi; nhược điểm là **parser auth-param phức tạp hơn** header timestamp đơn giản và dễ gặp vấn đề dấu phẩy, dấu ngoặc kép, duplicate param hoặc proxy/framework hỗ trợ scheme không đồng nhất. Sự đơn giản/độ khó tùy hệ thống — chọn một contract và kiểm thử xuyên các hop.

### 2.2. Khung cú pháp Authorization: scheme và auth-param

HTTP authentication cho phép trường credentials có **auth-scheme** và phần dữ liệu xác thực, thường theo dạng token68 hoặc danh sách auth-param. Trong hợp đồng này:

~~~text
Authorization = "HMAC-V1" SP HMAC-parameters

HMAC-parameters (profile minh họa):
  client="...", keyid="...", ts="...", nonce="...", sig="..."
~~~

Điều đó **không** có nghĩa parser có thể lấy giá trị bằng `split(",")` trên mọi Authorization header. HTTP `quoted-string` có thể chứa dấu phẩy được escape hoặc các cú pháp khác tùy profile; parser tổng quát phải phân biệt dấu phẩy **bên trong** và **bên ngoài** quoted-string.

**Chú ý tính tương thích:** HTTP định nghĩa tên auth-scheme và tên auth-param **không phân biệt hoa/thường**. Vì vậy một production parser hỗ trợ cú pháp auth-param tổng quát nên chuẩn hóa **tên** tham số và reject duplicate sau chuẩn hóa. Để bài tập có test vectors cố định, Java demo ở phần sau chỉ chấp nhận **một dạng serialization hẹp**: scheme `HMAC-V1` không phân biệt hoa/thường, nhưng **tên param viết chữ thường**, một dấu cách sau scheme, thứ tự cố định, một dấu phẩy + một dấu cách giữa các cặp, không dùng escape trong value. Đó là **strict profile riêng của API minh họa**, không phải bộ parser RFC đầy đủ; nếu xây API đa client, dùng parser RFC-aware và canonicalize các giá trị đã parse.

## 3. Định dạng timestamp field: unit, ASCII và giới hạn

Hợp đồng HMAC-V1 quy định:

~~~text
ts = Unix epoch seconds
wire value = ASCII decimal string
regex = [1-9][0-9]{0,18}
Java parsing = Long.parseLong(...)
timezone = UTC instant (không có local timezone trong field)
~~~

| Giá trị `ts` | Ý nghĩa | Kết luận của contract |
| --- | --- | --- |
| `1795831200` | Epoch seconds chính tắc | Cho parse; tiếp tục HMAC/freshness. |
| `1795831200000` | Epoch milliseconds, nhầm unit | Cú pháp có thể parse, nhưng bị **freshness reject** vì quá xa tương lai. |
| `01795831200` | Leading zero | **Reject format**, không lặng lẽ chuẩn hóa. |
| `+1795831200` | Dấu cộng | **Reject format**. |
| `-1795831200` | Số âm | **Reject format** theo profile này. |
| `1795831200.0` | Decimal/fraction | **Reject format**. |
| `2026-11-28T02:00:00Z` | ISO-8601 chứ không phải epoch seconds | **Reject format**. |
| `1795831200 ` | Có space trong quoted value | **Reject format**, không `trim()`. |
| `9999999999999999999` | Vượt `Long.MAX_VALUE` | **Reject parse**, không overflow/wrap. |
| Hai tham số `ts=...` | Một Authorization có duplicate timestamp | **Reject ngay tại parser**. |

**Lý do giữ một dạng duy nhất:** Canonical HMAC ký **byte**, không ký giá trị ngày giờ trừu tượng. `"1795831200"` và `"01795831200"` có thể cùng nghĩa về số nhưng **khác byte**. Nếu client ký dạng A, server tự parse rồi in lại dạng B, kết quả HMAC có thể khác, hoặc tệ hơn dẫn đến hai parser chọn hai nguồn khác nhau.

### 3.1. Timestamp của client và thời gian kiểm tra của server

Client sinh `ts` **ngay trước khi gửi** request. Server **không tin timestamp client là thời gian thực tế hiện tại**: nó đọc `now` từ server clock đáng tin để so sánh. Đây là lý do timestamp phải **được ký** và **kiểm tra freshness** riêng.

`Clock.instant()`/`Instant.now()` trong Java là wall clock cho thời điểm UTC; `System.nanoTime()` dùng đo elapsed time cục bộ, **không** dùng làm một epoch timestamp có thể so sánh giữa hai máy. Giờ hiển thị ở Việt Nam (UTC+7) không làm thay đổi epoch seconds của cùng một `Instant`.

### 3.2. Phân biệt HTTP Date và signed timestamp

`Date` trong HTTP mô tả ngày/giờ của message theo chức năng HTTP, còn `ts` trong HMAC scheme là một **credential parameter đã ký**. Chúng không phải cùng trường, cũng không bắt buộc đồng nhất khi qua proxy/cache. Không dùng `Date` hoặc `X-Forwarded-Date` thay cho `ts` trong việc kiểm tra HMAC-V1, và không lấy HTTP header do client tự khai để “điều chỉnh” server clock.

## 4. Timestamp nằm trong canonical request thế nào?

Hợp đồng ký ví dụ **HMAC-AUTHORIZATION-TS-V1** dành cho endpoint:

~~~http
POST /v1/payments?currency=VND
Content-Type: application/json
Authorization: HMAC-V1 ...
~~~

**Canonical request** là chuỗi dòng cố định:

~~~text
HMAC-AUTHORIZATION-TS-V1
POST
/v1/payments?currency=VND
audience:payments-api
client:partner-42
keyid:key-2026-11
ts:1795831200
nonce:00112233445566778899aabbccddeeff
content-type:application/json
body-sha256:<64-hex-lowercase>
~~~

Đây là **contract học tập**, không phải chuẩn HMAC chung:

- Nối các dòng bằng **LF byte 0x0A**, **không có LF cuối**; mã hóa chuỗi thành **UTF-8**.
- Method `POST` và raw request target `/v1/payments?currency=VND` phải đúng những gì backend thực thi.
- Audience `payments-api` lấy từ policy của server, không tin header `X-Forwarded-Host` do client tự đặt.
- `client`, `keyid`, **`ts`**, `nonce` là **giá trị lấy từ Authorization credential đã parse**, giữ đúng chuỗi ký tự sau validation.
- `content-type` là giá trị đã kiểm tra từ request; `body-sha256` là lowercase hex của SHA-256 trên **body bytes thực nhận**, không hash JSON đã serialize lại.
- `sig` **không** nằm trong canonical, tránh tự tham chiếu vì signature được tính **từ** canonical.
- Timestamp và nonce được ký ở cùng transcript; verifier không được tính HMAC trên `ts` nhưng kiểm tra freshness của một timestamp khác.

~~~mermaid
flowchart TD
    A["Client: Authorization chứa client,keyid,ts,nonce"] --> P["Parse và validate các giá trị"]
    B["HTTP method, raw target, Content-Type, body bytes"] --> C["Dựng canonical UTF-8 đúng hợp đồng"]
    P --> C
    K["Shared secret ứng với client+keyid"] --> H["HMAC-SHA256"]
    C --> H
    H --> E["Base64 encode tag -> sig của Authorization"]
    E --> W["HTTP request truyền tới verifier"]
    W --> V["Parse một Authorization, tự dựng canonical thực nhận"]
    V --> M["Tính lại HMAC, so sánh full 32-byte tag"]
    M --> F["Freshness của ts đã ký + atomic nonce claim"]
~~~

### 4.1. Điều gì xảy ra nếu attacker chỉ thay `ts`?

Giả sử một request có timestamp cũ `1795831200` và tag hợp lệ. Attacker đổi:

~~~text
ts="1795831200"  ->  ts="1795831201"
sig vẫn giữ nguyên
~~~

Verifier sẽ dựng **canonical bytes khác**; HMAC tính lại không khớp chữ ký nhận được. **Một timestamp mới nhưng không được ký lại không thể làm mới request cũ.** Nếu trong code có nhánh “timestamp lấy từ header mới nhất, HMAC từ canonical cũ”, đó là **lỗ hổng logic**, không phải vấn đề thuật toán HMAC.

## 5. Parse Authorization an toàn: một field, một timestamp

Vì `Authorization` là credential field, parser và ingress phải từ chối trường hợp **nhiều giá trị bảo mật mơ hồ**:

~~~http
Authorization: HMAC-V1 client="partner-42", keyid="key-2026-11", ts="1795831200", nonce="...", sig="..."
authorization: HMAC-V1 client="partner-42", keyid="key-2026-11", ts="1795831201", nonce="...", sig="..."
~~~

Tên HTTP header **không phân biệt chữ hoa/thường**. Hai field line cùng tên **không** được cho phép đi vào verifier bằng cách gateway lấy cái đầu còn backend lấy cái cuối, hoặc gộp thành một chuỗi và parser tự chọn. **Từ chối duplicate Authorization tại trusted ingress trước khi framework làm mất dấu nguồn gốc.**

### 5.1. Duplicate auth-param trong một Authorization

~~~http
Authorization: HMAC-V1 client="partner-42", keyid="key-2026-11", ts="1795831200", ts="1795831201", nonce="...", sig="..."
~~~

Nếu client gửi hai tham số `ts`, parser nào chọn đầu, parser nào chọn cuối? Đừng sử dụng `Map.put` ghi đè giá trị cũ rồi tiếp tục. **Reject duplicate param name sau khi chuẩn hóa case**. Không cho phép hai `sig`, hai `client` hoặc hai `keyid` để tránh chọn sai credential/policy.

### 5.2. Dấu phẩy, quoted-string và whitespace

Một Authorization credential theo auth-param có thể dùng dấu phẩy để phân cách cặp tên/giá trị. Không viết parser tổng quát bằng `header.split(",")`: dấu phẩy trong quoted-string không nhất thiết là dấu phân cách, và quoted-pair escape phải được xử lý phù hợp quy tắc HTTP nếu API hỗ trợ.

Trong **profile HMAC-V1 minh họa**:

~~~text
HMAC-V1 client="...", keyid="...", ts="...", nonce="...", sig="..."
~~~

Các value được giới hạn bởi alphabet riêng, **không chứa dấu phẩy, dấu ngoặc kép bên trong, backslash escape, CR/LF, TAB hoặc Unicode**. Việc chỉ chấp nhận chuỗi serialize đúng format sẽ giúp demo dễ kiểm thử; production API đa client có thể dùng HTTP auth-param parser chuẩn, lấy parsed values và canonicalize, nhưng **không được im lặng sửa timestamp sai format bằng trim/lowercase/chuyển unit**.

### 5.3. Guard trước khi parse

- Có giới hạn kích thước tổng `Authorization` tại ingress; không thử parse một field hàng megabyte.
- Từ chối CR/LF, obs-fold và ký tự điều khiển; không cho phép proxy **unfold** một header độc hại thành giá trị hợp lệ.
- Không tự chuyển `Authorization: Bearer ...` hoặc `Basic ...` sang HMAC; chỉ scheme được policy cấu hình mới phù hợp.
- Không thử lần lượt nhiều cách parse khi một scheme thất bại; hạn chế các mode compatibility được client tự kích hoạt.
- Không log `Authorization` raw, đặc biệt signature, client credential hoặc metadata có thể hỗ trợ phát lại. Hãy dùng error code `malformed-auth`, `invalid-timestamp`, `signature-mismatch` và request ID.
- Cẩn trọng với header được gộp, reverse proxy, HTTP/2 `authorization` lowercase và frontend/backend diễn giải khác nhau.

## 6. Freshness: timestamp đã parse có còn mới không?

Đặt:

~~~text
ts  = signed epoch seconds trong Authorization
now = epoch seconds từ verifier server clock
P   = pastWindowSeconds = 300
F   = futureToleranceSeconds = 60
~~~

Chính sách minh họa:

\[
\operatorname{fresh}(ts,now) \iff now-P\le ts\le now+F
\]

**Biên inclusive:** timestamp đúng `now-300` hoặc `now+60` được chấp nhận về mặt freshness. Đây là các con số **minh họa**, cần chọn theo SLA, độ trễ thực tế, clock skew và threat model.

*Giả sử verifier clock = 2026-11-28T02:00:00Z, tức now=1795831200.*

~~~text
Quá khứ                           Hiện tại                  Tương lai
1795830899  1795830900             1795831200       1795831260  1795831261
    FAIL       PASS                     PASS             PASS         FAIL
   (-301)     (-300)                     (0)             (+60)        (+61)
                [------------- freshness window ------------]
~~~

| `ts` | Lệch `ts-now` | Kiểm tra freshness |
| ---: | ---: | --- |
| `1795830899` | -301 giây | **Reject** quá cũ. |
| `1795830900` | -300 giây | **Accept** đúng biên dưới. |
| `1795830901` | -299 giây | Accept. |
| `1795831200` | 0 | Accept. |
| `1795831259` | +59 giây | Accept. |
| `1795831260` | +60 giây | **Accept** đúng biên trên. |
| `1795831261` | +61 giây | **Reject** quá xa tương lai. |

### 6.1. Vì sao bất đối xứng?

Client có thể gửi request trước khi server nhận do network delay/queue, nên `pastWindow` thường lớn hơn `futureTolerance`. Client chạy clock nhanh hơn một ít có thể tạo timestamp **ở tương lai**, vì thế cho phép `F` nhỏ thay vì reject mọi `ts>now`. Nhưng chấp nhận tương lai cũng **kéo dài tối đa thời gian sống của một request**, khiến TTL nonce phải đủ dài.

Không dùng `Math.abs(now-ts) <= 300` cho policy `P=300,F=60`: nó cho phép request **ở tương lai tới 300 giây**. Dùng hai ngưỡng rõ ràng, kiểm tra overflow khi tính `now-P` hoặc `now+F`.

### 6.2. Timestamp đúng chưa đồng nghĩa HMAC đúng

Một attacker có thể tạo một credential chứa `ts=now`, `nonce` hợp format và Base64 signature dài 44 ký tự. Điều đó **không** có nghĩa attacker biết secret. Verifier phải tự tính full HMAC-SHA256 tag từ canonical và so sánh **32 byte** với decoded tag bằng `MessageDigest.isEqual`, đồng thời kiểm tra key active, audience/route policy và freshness.

## 7. Nonce store sau freshness: chặn phát lại nguyên credential

Với request `Authorization` hợp lệ, attacker có thể phát lại **toàn bộ header**, method, URI và body trong khi timestamp còn fresh. HMAC và freshness vẫn khớp. Do đó nonce phải được ký trong cùng canonical và được ghi vào **atomic nonce store** sau khi HMAC hợp lệ:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Proxy không tin cậy
    participant V as Verifier
    participant N as Shared nonce store
    C->>V: Credential ts=T, nonce=N, sig=S
    V->>V: HMAC + freshness PASS
    V->>N: Atomic claim(audience,client,N)
    N-->>V: CREATED
    P->>V: Replay nguyên Authorization ts=T, nonce=N, sig=S
    V->>V: HMAC + freshness vẫn PASS
    V->>N: Atomic claim(audience,client,N)
    N-->>V: ALREADY_EXISTS -> Reject replay
~~~

**Không claim nonce trước HMAC** vì attacker có thể burn nonce của request hợp lệ bằng một chữ ký giả. Storage key nên scope theo **audience + authenticated client ID + nonce**, **không mặc định theo key ID** để một nonce không được claim lại qua key rotation. Store phải hỗ trợ **atomic claim-if-absent** trên các replica (ví dụ Redis `SET key 1 NX PX ttl` hoặc SQL unique constraint), xử lý lỗi **fail closed**.

### 7.1. TTL từ signed timestamp và freshness window

Với `P=300,F=60`, timestamp `ts` có thể được chấp nhận từ `now=ts-60` đến `now=ts+300`: tổng cộng **360 giây**.

Nếu nonce được claim ở đầu cửa sổ mà store xóa sau đúng **300 giây**, replay có thể vượt qua trong 60 giây cuối. Hãy giữ nonce tới sau:

~~~text
expiresAt > signedTimestamp + P
expiresAt = signedTimestamp + P + safetyMargin
~~~

Hoặc đặt **relative TTL** bảo thủ `P+F+safetyMargin` từ lần claim, ví dụ **370 giây** với margin 10 giây theo điều kiện vận hành. Đảm bảo không eviction sớm, không mất write khi failover và không có hai region cùng claim một nonce độc lập. Server clock bị lệch/lùi làm đảo lộn giả định về TTL, nên cần monitoring NTP và chính sách xử lý lỗi clock.

### 7.2. Nonce không phải idempotency key

Một retry nghiệp vụ hợp lệ sau timeout có thể dùng **timestamp mới, nonce mới, HMAC mới**, nhưng vẫn là **cùng ý định thanh toán**. Nonce store chỉ chặn **replay cùng nonce**; cần **Idempotency-Key được ký**, response outcome bền vững và unique business reference để tránh tạo hai giao dịch khi retry khác nonce.

## 8. Java 17: parse `Authorization`, kiểm tra `ts` và xác minh HMAC

Ví dụ dưới đây là **chương trình tự chứa** `AuthorizationTimestampExample.java` trên Java 17. Nó minh họa:

- Client tạo timestamp từ `Clock.instant().getEpochSecond()` và nonce 16 byte bằng `SecureRandom`.
- Tạo canonical method, raw target, parsed credential fields, Content-Type và body digest; HMAC-SHA256 full 32 byte; Base64 chuẩn padded.
- Tạo **một** `Authorization` theo strict profile minh họa; verifier parse `ts` trực tiếp từ credential, không có header `X-Timestamp` thay thế.
- Dùng `Long.parseLong` có bảo vệ syntax/overflow, freshness bất đối xứng inclusive, key lookup, `MessageDigest.isEqual` và atomic nonce claim mô phỏng.
- Kiểm thử đổi timestamp không ký lại, duplicate auth-param, thiếu padding, replay, key rotation và ranh giới thời gian.

**Phạm vi:** `Request` là record mô phỏng input đã parse; **không phải HTTP server/parser tổng quát**. Server production phải reject duplicate `Authorization` ngay tại trusted ingress, xử lý đúng auth-param grammar/profile, method/URI/body thực nhận, dùng key manager và atomic shared nonce store có TTL/durability.

### 8.1. Chương trình đầy đủ

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
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class AuthorizationTimestampExample {
    private static final SecureRandom RNG = new SecureRandom();
    private static final String METHOD = "POST";
    private static final String TARGET = "/v1/payments?currency=VND";
    private static final String AUDIENCE = "payments-api";
    private static final String CLIENT = "partner-42";
    private static final String OLD_KEY = "key-2026-11";
    private static final String NEW_KEY = "key-2026-12";
    private static final String CONTENT_TYPE = "application/json";
    private static final long PAST = 300L;
    private static final long FUTURE = 60L;
    private static final long MARGIN = 10L;

    // Strict teaching profile: lowercase parameter names, fixed order,
    // quoted values without escapes, exactly comma+SP separators.
    // Scheme itself is matched case-insensitively per HTTP auth grammar.
    private static final Pattern AUTH = Pattern.compile(
        "^(?i:HMAC-V1) client=\"(?<client>[a-z0-9-]{1,40})\", " +
        "keyid=\"(?<key>[a-z0-9-]{1,40})\", " +
        "ts=\"(?<ts>[1-9][0-9]{0,18})\", " +
        "nonce=\"(?<nonce>[0-9a-f]{32})\", " +
        "sig=\"(?<sig>[A-Za-z0-9+/]{43}=)\"$"
    );

    record Fields(
        String client, String keyId, String ts,
        String nonce, String signature
    ) {}

    record Request(
        String method, String rawTarget, String contentType,
        String authorization, byte[] body
    ) {}

    record Key(
        String client, String keyId, byte[] secret,
        Instant activeFrom, Instant expiresAt, boolean revoked
    ) {}

    // Unit-test store ONLY. Real store must support shared atomic claim
    // and TTL + durability across nodes.
    static final class DemoNonceStore {
        private final ConcurrentHashMap<String, Long> expiry =
            new ConcurrentHashMap<>();

        boolean claim(String audience, String client, String nonce,
                long now, long expiresAt) {
            if (expiresAt <= now) {
                return false;
            }
            // Length-prefix avoids collisions between tuple components.
            String k = audience.length() + ":" + audience
                + client.length() + ":" + client
                + nonce.length() + ":" + nonce;
            AtomicBoolean created = new AtomicBoolean(false);
            expiry.compute(k, (key, previous) -> {
                if (previous != null && previous > now) {
                    return previous;
                }
                created.set(true);
                return expiresAt;
            });
            return created.get();
        }
    }

    static Fields parseAuthorization(String authorization) {
        if (authorization == null || authorization.length() > 512) {
            return null;
        }
        Matcher matcher = AUTH.matcher(authorization);
        if (!matcher.matches()) {
            return null;
        }
        return new Fields(
            matcher.group("client"), matcher.group("key"),
            matcher.group("ts"), matcher.group("nonce"),
            matcher.group("sig")
        );
    }

    static Long parseEpochSeconds(String ts) {
        if (ts == null || !ts.matches("[1-9][0-9]{0,18}")) {
            return null;
        }
        try {
            return Long.parseLong(ts);
        } catch (NumberFormatException overflow) {
            return null;
        }
    }

    static boolean fresh(long signedTs, long serverNow) {
        try {
            return signedTs >= Math.subtractExact(serverNow, PAST)
                && signedTs <= Math.addExact(serverNow, FUTURE);
        } catch (ArithmeticException overflow) {
            return false;
        }
    }

    static String bodySha256Hex(byte[] body)
            throws GeneralSecurityException {
        return HexFormat.of().formatHex(
            MessageDigest.getInstance("SHA-256").digest(body)
        );
    }

    static byte[] hmac(byte[] secret, String message)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(message.getBytes(StandardCharsets.UTF_8));
    }

    static String canonical(String method, String rawTarget,
            String contentType, Fields fields, String actualBodyHash) {
        if (!METHOD.equals(method) || !TARGET.equals(rawTarget)
            || !CONTENT_TYPE.equals(contentType)
            || fields == null || !CLIENT.equals(fields.client())
            || !(OLD_KEY.equals(fields.keyId())
                || NEW_KEY.equals(fields.keyId()))
            || parseEpochSeconds(fields.ts()) == null
            || !fields.nonce().matches("[0-9a-f]{32}")
            || actualBodyHash == null
            || !actualBodyHash.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("Invalid canonical fields");
        }
        return String.join("\n",
            "HMAC-AUTHORIZATION-TS-V1",
            method,
            rawTarget,
            "audience:" + AUDIENCE,
            "client:" + fields.client(),
            "keyid:" + fields.keyId(),
            "ts:" + fields.ts(),
            "nonce:" + fields.nonce(),
            "content-type:" + contentType,
            "body-sha256:" + actualBodyHash
        );
    }

    static byte[] decodeSignature(String encoded) {
        if (encoded == null ||
            !encoded.matches("[A-Za-z0-9+/]{43}=")) {
            return null;
        }
        try {
            byte[] tag = Base64.getDecoder().decode(encoded);
            if (tag.length != 32 ||
                !Base64.getEncoder().encodeToString(tag)
                    .equals(encoded)) {
                return null;
            }
            return tag;
        } catch (IllegalArgumentException malformed) {
            return null;
        }
    }

    static String renderAuthorization(Fields f) {
        return "HMAC-V1 client=\"" + f.client()
            + "\", keyid=\"" + f.keyId()
            + "\", ts=\"" + f.ts()
            + "\", nonce=\"" + f.nonce()
            + "\", sig=\"" + f.signature() + "\"";
    }

    static byte[] randomSecret() {
        byte[] secret = new byte[32];
        RNG.nextBytes(secret);
        return secret;
    }

    static String randomNonce() {
        byte[] nonce = new byte[16];
        RNG.nextBytes(nonce);
        return HexFormat.of().formatHex(nonce);
    }

    static Request sign(byte[] secret, String keyId,
            String timestamp, String nonce, byte[] body)
            throws GeneralSecurityException {
        String digest = bodySha256Hex(body);
        Fields unsigned = new Fields(
            CLIENT, keyId, timestamp, nonce, ""
        );
        String text = canonical(
            METHOD, TARGET, CONTENT_TYPE, unsigned, digest
        );
        String wireTag = Base64.getEncoder().encodeToString(
            hmac(secret, text)
        );
        String authorization = renderAuthorization(new Fields(
            CLIENT, keyId, timestamp, nonce, wireTag
        ));
        return new Request(
            METHOD, TARGET, CONTENT_TYPE, authorization, body.clone()
        );
    }

    static Request signNow(byte[] secret, String keyId,
            Clock clientClock, String nonce, byte[] body)
            throws GeneralSecurityException {
        return sign(
            secret, keyId,
            Long.toString(clientClock.instant().getEpochSecond()),
            nonce, body
        );
    }

    static boolean verify(Request request, Map<String, Key> keyring,
            Clock serverClock, DemoNonceStore nonces)
            throws GeneralSecurityException {
        // Real ingress: reject multiple Authorization field lines BEFORE
        // the HTTP framework coalesces or selects a field value.
        if (request == null || request.body() == null
            || request.body().length > 65536) {
            return false;
        }
        Fields fields = parseAuthorization(request.authorization());
        if (fields == null) {
            return false;
        }
        Long ts = parseEpochSeconds(fields.ts());
        byte[] supplied = decodeSignature(fields.signature());
        if (ts == null || supplied == null) {
            return false;
        }

        Instant verifiedAt = serverClock.instant();
        long now = verifiedAt.getEpochSecond();
        if (!fresh(ts, now)) {
            return false;
        }
        final String message;
        try {
            String hash = bodySha256Hex(request.body());
            message = canonical(
                request.method(), request.rawTarget(),
                request.contentType(), fields, hash
            );
        } catch (IllegalArgumentException invalid) {
            return false;
        }

        Key key = keyring.get(
            fields.client() + ":" + fields.keyId()
        );
        if (key == null || key.revoked()
            || !fields.client().equals(key.client())
            || !fields.keyId().equals(key.keyId())
            || key.secret() == null || key.secret().length < 32
            || key.activeFrom() == null || key.expiresAt() == null
            || verifiedAt.isBefore(key.activeFrom())
            || !verifiedAt.isBefore(key.expiresAt())) {
            return false;
        }

        byte[] expected = hmac(key.secret(), message);
        if (expected.length != 32 ||
            !MessageDigest.isEqual(expected, supplied)) {
            return false;
        }

        // Claim nonce AFTER successful HMAC and timestamp freshness.
        final long expiresAt;
        try {
            expiresAt = Math.addExact(
                ts, Math.addExact(PAST, MARGIN)
            );
        } catch (ArithmeticException overflow) {
            return false;
        }
        return nonces.claim(
            AUDIENCE, fields.client(), fields.nonce(), now, expiresAt
        );
    }

    static Request withAuthorization(Request src, String authorization) {
        return new Request(
            src.method(), src.rawTarget(), src.contentType(),
            authorization, src.body()
        );
    }

    static Request withBody(Request src, byte[] changed) {
        return new Request(
            src.method(), src.rawTarget(), src.contentType(),
            src.authorization(), changed
        );
    }

    static void require(boolean condition, String description) {
        if (!condition) {
            throw new AssertionError(description);
        }
    }

    static void rfc4231Vector() throws Exception {
        byte[] key = new byte[20];
        Arrays.fill(key, (byte) 0x0b);
        String actual = HexFormat.of().formatHex(
            hmac(key, "Hi There")
        );
        String expected =
            "b0344c61d8db38535ca8afceaf0bf12" +
            "b881dc200c9833da726e9376c2e32cff7";
        require(expected.equals(actual), "RFC 4231 test vector");
    }

    public static void main(String[] args) throws Exception {
        rfc4231Vector();
        byte[] oldSecret = randomSecret();
        byte[] newSecret = randomSecret();
        Instant from = Instant.parse("2026-01-01T00:00:00Z");
        Instant until = Instant.parse("2027-01-01T00:00:00Z");
        Map<String, Key> keys = Map.of(
            CLIENT + ":" + OLD_KEY,
            new Key(CLIENT, OLD_KEY, oldSecret, from, until, false),
            CLIENT + ":" + NEW_KEY,
            new Key(CLIENT, NEW_KEY, newSecret, from, until, false)
        );
        Clock server = Clock.fixed(
            Instant.parse("2026-11-28T02:00:00Z"),
            ZoneOffset.UTC
        );
        long now = server.instant().getEpochSecond();
        byte[] body =
            "{\"orderId\":\"ord-123\",\"amount\":50000}"
                .getBytes(StandardCharsets.UTF_8);

        Request signed = signNow(
            oldSecret, OLD_KEY, server, randomNonce(), body
        );
        HttpRequest sample = HttpRequest.newBuilder(
                URI.create("https://api.example.test" + TARGET))
            .header("Content-Type", CONTENT_TYPE)
            .header("Authorization", signed.authorization())
            .POST(HttpRequest.BodyPublishers.ofByteArray(signed.body()))
            .build(); // Do not send HTTP request over network.
        require(METHOD.equals(sample.method()), "HTTP method");
        require(parseAuthorization(
            signed.authorization()) != null, "Valid auth field parse");
        require(verify(signed, keys, server, new DemoNonceStore()),
            "Valid HMAC Authorization must pass");

        // Replace ts but keep sig: same fresh window, HMAC MUST fail.
        Request alteredTimestamp = withAuthorization(
            signed, signed.authorization().replace(
                "ts=\"" + now + "\"",
                "ts=\"" + (now + 1) + "\""
            )
        );
        require(!verify(
            alteredTimestamp, keys, server, new DemoNonceStore()),
            "Unsigned timestamp modification must fail HMAC");

        // Strict profile rejects duplicate params, extra chars and
        // other schemes even if a generic HTTP parser could parse them.
        require(parseAuthorization(
            signed.authorization().replace(
                ", nonce=", ", ts=\"1795831201\", nonce="
            )) == null, "Duplicate ts rejected");
        require(parseAuthorization(
            signed.authorization() + ", ts=\"1795831200\""
        ) == null, "Extra ts rejected");
        require(parseAuthorization(
            signed.authorization().replace(
                "HMAC-V1 ", "Bearer "
            )) == null, "Wrong scheme rejected");
        require(parseAuthorization(
            signed.authorization().replace(
                "ts=\"" + now + "\"",
                "ts=\"0" + now + "\""
            )) == null, "Leading zero rejected");
        require(parseAuthorization(
            signed.authorization().replace(
                "ts=\"" + now + "\"",
                "ts=\"" + now + " \""
            )) == null, "Whitespace in timestamp rejected");
        require(parseAuthorization(
            signed.authorization() + "\r\nX-Timestamp: " + now
        ) == null, "CRLF injection rejected");
        require(parseAuthorization(
            signed.authorization().replace(
                "sig=\"", "sig=\"bad-"
            )) == null, "Invalid Base64 alphabet rejected");
        require(parseEpochSeconds("9999999999999999999") == null,
            "Overflow timestamp rejected");

        // Full, correctly signed timestamp at boundaries is accepted.
        for (long offset : new long[] {-300L, +60L}) {
            Request boundary = sign(
                oldSecret, OLD_KEY, Long.toString(now + offset),
                randomNonce(), body
            );
            require(verify(
                boundary, keys, server, new DemoNonceStore()),
                "Inclusive freshness boundary " + offset);
        }
        for (long offset : new long[] {-301L, +61L}) {
            Request outside = sign(
                oldSecret, OLD_KEY, Long.toString(now + offset),
                randomNonce(), body
            );
            require(!verify(
                outside, keys, server, new DemoNonceStore()),
                "Reject time outside window " + offset);
        }

        // The same signed credential may be replayed while fresh;
        // shared nonce storage must allow only its first claim.
        DemoNonceStore replayStore = new DemoNonceStore();
        require(verify(signed, keys, server, replayStore),
            "First nonce claim");
        require(!verify(signed, keys, server, replayStore),
            "Exact credential replay must fail");

        // Rotation: same client/audience/nonce is not fresh in store
        // merely because the signature uses a new key.
        Fields oldFields = parseAuthorization(signed.authorization());
        Request rotatedSameNonce = sign(
            newSecret, NEW_KEY, Long.toString(now),
            oldFields.nonce(), body
        );
        require(!verify(
            rotatedSameNonce, keys, server, replayStore),
            "Rotation cannot reset nonce history");
        Request newNonceAndKey = sign(
            newSecret, NEW_KEY, Long.toString(now),
            randomNonce(), body
        );
        require(verify(
            newNonceAndKey, keys, server, replayStore),
            "New key with fresh nonce accepted");

        // Tampered body does not consume a valid nonce.
        DemoNonceStore bodyStore = new DemoNonceStore();
        byte[] tampered = body.clone();
        tampered[0] ^= 1;
        require(!verify(
            withBody(signed, tampered), keys, server, bodyStore),
            "Changed body must fail HMAC");
        require(verify(signed, keys, server, bodyStore),
            "Invalid HMAC must not burn nonce");

        // Revoked key fails even with a valid timestamp and signature.
        Map<String, Key> revoked = Map.of(
            CLIENT + ":" + OLD_KEY,
            new Key(CLIENT, OLD_KEY, oldSecret, from, until, true)
        );
        require(!verify(
            signed, revoked, server, new DemoNonceStore()),
            "Revoked key rejected");
        System.out.println(
            "PASS: Authorization ts parse, HMAC, freshness, replay"
        );
    }
}
~~~

### 8.2. Vì sao parser demo dùng một regex chặt?

`parseAuthorization` chỉ chấp nhận **một strict serialization** của HMAC-V1. Nó không tự đoán scheme, không bỏ dấu nháy, không thay đổi thứ tự tham số, không trim timestamp và không nhận param lặp. Điều này giúp test chính xác **byte nào được ký** và phản ứng với input ngoài contract.

Đối với production multi-client, parser cần **giải thích đầy đủ grammar HTTP Authorization/auth-param** và có thể chấp nhận thay đổi hợp lệ về case/tên tham số/OWS. Việc chọn nhận thêm biến thể là **quyết định giao thức công khai**, không thể ngầm sửa trong một middleware. Sau khi parse thành cấu trúc `Fields`, chỉ canonicalize **theo hợp đồng đã ký**, không đưa raw serialized Authorization (chứa `sig`) vào chính HMAC.

### 8.3. Vì sao field `ts` phải được xử lý một lần?

`Fields.ts()` vừa đi vào `canonical()` vừa đi vào `parseEpochSeconds()` và `fresh()`. Verifier không có đường code dùng một `ts` trong HMAC và một `X-Timestamp` khác trong freshness. Đây là nguyên tắc chống **parser differential**, nhất là khi có nhiều proxy/HTTP versions.

### 8.4. Hạn chế của mã minh họa

- `Request` không có khả năng phát hiện **hai field line Authorization**. Ingress production phải reject duplicate case-insensitive trước khi rút thành một `String`.
- Regex chỉ là **hợp đồng wire subset của ví dụ**, không phải HTTP auth-param parser hoàn chỉnh. Cần giới hạn header, xử lý quoted-string/OWS và kiểm thử thư viện HTTP thực.
- `DemoNonceStore` chỉ đồng bộ trong một JVM, không TTL cleanup/durability. Server nhiều replica phải dùng **shared atomic store** với retention không xóa sớm.
- `Map` keyring chỉ mô phỏng key manager; cần client status, audience/route scope, revoke/rotation policy, secret management và kiểm tra hiệu lực theo server verify time.
- Mã cố định method/target và Content-Type để tránh nhập nhằng. API thật phải ký đủ route/query/body representation mà backend thực sự xử lý.
- `verify` trả boolean cho mục tiêu học tập; hệ thống thật còn cần HTTP status, `WWW-Authenticate` challenge đúng hợp đồng, rate limiting, monitoring và bảo vệ dữ liệu.
- Chương trình mô phỏng **authentication/replay**; **authorization, idempotency và xử lý thanh toán thật chưa được triển khai**.

## 9. Key rotation, freshness và timestamp trong cùng credential

Khi client đổi từ `key-2026-11` sang `key-2026-12`, nó vẫn đặt `ts` và `nonce` trong Authorization credential, tạo canonical với key ID mới và HMAC bằng secret của key mới.

Server kiểm tra:

1. Scheme, client/key ID/timestamp/nonce/signature đúng contract.
2. Key lookup theo client ID + key ID từ **trusted key store**, không nhận secret hoặc algorithm tùy chọn do client tự gửi.
3. Key đang active, chưa revoked và đúng audience/route scope **tại thời điểm server xác minh** theo policy.
4. Timestamp còn fresh theo server clock; canonical và full HMAC tag khớp.
5. Atomic nonce store không cho **cùng client/audience/nonce** được dùng lại qua key ID khác.

**Không được** dùng giá trị `ts` do client chọn làm thời điểm quyết định key có còn active hay không trong ví dụ. Nếu cho phép backdate tới lúc key chưa revoked, attacker sở hữu key cũ có thể cố gia hạn quyền. Một policy cho ký offline rồi verify sau cần threat model và hợp đồng độc lập, không bật “accept any signed timestamp” để hỗ trợ rotation.

## 10. Proxy/gateway, HTTP versions và Authorization semantics

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as External proxy
    participant G as Trusted ingress
    participant V as HMAC verifier
    participant N as Shared nonce store
    participant B as Backend
    C->>P: Authorization HMAC-V1 với ts, nonce, sig
    P->>G: Có thể retry, rewrite hoặc thêm headers
    G->>G: Reject duplicate, malformed, oversized Authorization
    G->>V: Một credential đã parse và request bytes thực nhận
    V->>V: Canonical + full HMAC + signed ts freshness
    alt Valid
        V->>N: Atomic claim(audience, client, nonce)
        alt New nonce
            N-->>V: CREATED
            V->>B: Verified identity và đúng request
            B->>B: Authorization + idempotency
        else Replay
            N-->>V: ALREADY_EXISTS
            V-->>C: Reject
        end
    else Invalid signature / timestamp / key
        V-->>C: Reject authentication
    end
~~~

| Vấn đề | Ảnh hưởng | Cách bảo vệ |
| --- | --- | --- |
| Proxy thay `ts` trong Authorization | Canonical khác, HMAC phải fail | Parse một nguồn duy nhất, ký timestamp. |
| Proxy thêm `X-Timestamp` khác `ts` | Có thể làm hai tầng kiểm tra khác giá trị | Không fallback sang header ngoài contract. |
| Proxy gộp hai Authorization field line | Chọn sai credential hoặc parser ambiguity | Reject duplicate trước merge. |
| HTTP/2 lowercase tên `authorization` | Tên header hợp lệ không phân biệt case | Dùng parser tên header case-insensitive; value theo contract. |
| Reverse proxy xóa Authorization | Backend không thể verify credential | Cấu hình chuyển tiếp chính xác hoặc verify ở gateway có trust boundary rõ. |
| Gateway verify rồi backend nhận `X-Verified: true` từ client | Có thể bypass HMAC hoặc mạo identity | Xóa forwarded identity không tin, xác thực hop nội bộ, chặn backend direct access. |
| Proxy chuẩn hóa raw path/query | HMAC của action khác action backend dùng | Verify method/raw target đúng ngữ nghĩa tại boundary. |
| Thay content encoding/body | Body digest thay đổi | Dùng byte representation đã ký, không transform không quy định. |
| HTTP auth challenge/caching | Cache/proxy có thể xử lý Authorization đặc biệt | Không cho shared cache phân phối response nhạy cảm sai identity. |
| Client timestamp ở future quá xa | Freshness sai dù HMAC đúng | NTP, tolerance nhỏ và policy đồng nhất giữa replicas. |

### 10.1. Authorization header không có nghĩa là business authorization

`Authorization` mang **authentication credentials**. Một client sở hữu secret và ký request đúng vẫn không mặc nhiên có quyền chuyển tiền của tenant khác. Chỉ sau HMAC/freshness/nonce, backend mới dùng identity đã xác thực cho **RBAC/ABAC/ACL**, kiểm tra action, tenant, resource, hạn mức và idempotency key của nghiệp vụ có side effect.

### 10.2. HTTP error và WWW-Authenticate

Theo semantics HTTP, phản hồi **401 Unauthorized** liên quan authentication cần chứa ít nhất một **`WWW-Authenticate` challenge** phù hợp để client biết scheme. Một API HMAC tùy chỉnh có thể công bố challenge kiểu `WWW-Authenticate: HMAC-V1 realm="payments-api"` và mã lỗi tổng quát; không tiết lộ secret hoặc raw signature. Với identity đã được xác thực nhưng thiếu quyền, `403 Forbidden` thường phù hợp hơn.

Đừng phản hồi lỗi khác nhau tới mức client bên ngoài có thể liệt kê key tồn tại/không tồn tại hoặc đoán chi tiết key policy. Logging nội bộ có thể ghi `malformed-authorization`, `stale-timestamp`, `invalid-signature`, `duplicate-nonce` và request ID, nhưng phải che Authorization raw, canonical chứa dữ liệu nhạy cảm và body.

## 11. Những nhầm lẫn phổ biến về timestamp field

| Lỗi triển khai | Vì sao nguy hiểm | Hướng xử lý |
| --- | --- | --- |
| Kiểm tra `Date` nhưng HMAC ký `ts` | Dùng hai thời điểm khác nhau, dễ bị proxy/client thao túng | Chỉ dùng **parsed signed ts** cho freshness. |
| Đọc `X-Timestamp` nếu `ts` thiếu | Tạo downgrade/đường fallback không ký | Reject credential thiếu `ts`. |
| Tự chuyển milliseconds thành seconds | Chuẩn hóa không được ký, hai client khác contract | Reject sai unit hoặc dùng contract version riêng. |
| `trim()`, bỏ leading zero, parse floating point | Nhiều biểu diễn cho một giá trị, lệch canonical | Cố định ASCII decimal chính tắc. |
| Dùng `split(",")` trên auth-param tổng quát | Không xử lý quoted-string/escape và comma đúng | Dùng parser RFC-aware hoặc strict wire subset minh bạch. |
| Cho duplicate `ts` và lấy param cuối | Parser differential giữa các hop | Reject duplicate sau normalize tên. |
| Đưa toàn bộ `Authorization` (gồm `sig`) vào canonical | Tạo vòng tự tham chiếu | Ký các parsed parameters, trừ signature. |
| Ký `ts` nhưng freshness dùng timestamp khác | Attacker có thể “làm mới” request cũ | Reuse **một parsed field** cho canonical/freshness. |
| Chỉ kiểm tra timestamp, bỏ HMAC | Ai cũng tạo được ts mới | Bắt buộc recompute HMAC và so sánh full tag. |
| Chỉ kiểm tra HMAC, bỏ nonce | Replay request nguyên vẹn trong window | Atomic nonce claim có TTL đủ dài. |
| Chèn key ID vào namespace nonce | Cùng nonce có thể qua rotation | Scope nonce theo client + audience, không key ID. |
| Không giới hạn header size | Abuse CPU/memory, parser DoS | Limit trước parse, rate limit. |
| Log raw Authorization | Lộ credential có thể bị replay | Redact, chỉ log error code và request ID. |
| Bỏ authorization vì đã có Authorization header | Nhầm authn với authz | Kiểm tra quyền tenant/action/resource sau xác thực. |

## 12. Ma trận kiểm thử timestamp trong Authorization

Các test áp dụng cho **strict HMAC-V1 profile của bài**. Với HTTP parser/ingress thật, thêm integration tests qua reverse proxy, HTTP/1.1 ↔ HTTP/2 và library của client.

| Case | Thao tác/đầu vào | Kỳ vọng |
| --- | --- | --- |
| Happy path | Một Authorization HMAC-V1, `ts=now`, full HMAC tag đúng | Parse, HMAC, freshness, nonce PASS. |
| RFC 4231 | HMAC-SHA256 test vector key `0x0b`, message `Hi There` | Tag hex `b0344c61...2e32cff7`. |
| Thiếu Authorization | Không có credential | Reject authentication. |
| Sai scheme | `Bearer ...` hoặc `Basic ...` | Reject theo HMAC-V1 contract. |
| Sai tên param | `timestamp=...` thay `ts=...` | Reject strict profile. |
| Duplicate `ts` | Hai timestamp trong cùng Authorization | Reject, không chọn đầu/cuối. |
| Duplicate Authorization header | Hai field line cùng tên, khác case | Reject tại trusted ingress. |
| Timestamp leading zero | `ts="01795831200"` | Reject format. |
| Timestamp có dấu cộng | `ts="+1795831200"` | Reject format. |
| Timestamp ISO/milliseconds | `ts="2026-..."` hoặc `ts="1795831200000"` | Reject format hoặc freshness. |
| Timestamp overflow | 19 chữ số vượt `Long.MAX_VALUE` | Reject parse. |
| Timestamp quá khứ đúng biên | `ts=now-300` | Freshness PASS nếu HMAC đúng. |
| Timestamp quá cũ 1 giây | `ts=now-301` | Reject freshness. |
| Timestamp tương lai đúng biên | `ts=now+60` | Freshness PASS nếu HMAC đúng. |
| Timestamp quá xa tương lai 1 giây | `ts=now+61` | Reject freshness. |
| Sửa `ts` nhưng giữ signature | Đổi `ts=now` thành `now+1` không ký lại | HMAC FAIL. |
| Sửa nonce nhưng giữ signature | Đổi `nonce` | HMAC FAIL. |
| Chữ ký thiếu `=` | Base64 43 ký tự thay vì 44 | Reject strict signature encoding. |
| CR/LF injection | Thêm newline trong Authorization | Reject trước/ở parser, không tái ghép. |
| Dấu phẩy/quoted-string bất thường | Param chứa dấu phẩy hoặc backslash ngoài profile | Reject strict demo; production parser dùng grammar đúng. |
| Extra credential parameter | Thêm field lạ sau signature | Reject hoặc version/profile rõ, không âm thầm chấp nhận. |
| Body tamper | Sửa JSON sau ký | HMAC FAIL, không claim nonce. |
| Raw URI/query rewrite | Proxy sửa path/query | HMAC/route policy fail. |
| Replay cùng Authorization | Gửi lại ngay cùng ts/nonce/sig | HMAC và freshness vẫn đúng; **nonce reject**. |
| Retry nonce mới | Sign lại cùng business input với ts/nonce mới | HMAC/nonce có thể PASS; **idempotency** vẫn cần kiểm tra. |
| Key revoked | Credential ký đúng bằng key đã thu hồi | Reject theo key policy. |
| Key rotation | Key ID mới, nonce mới | Verify key mới nếu active, không miễn freshness. |
| Rotation reuse nonce | Key mới nhưng nonce đã claim dưới key cũ | Nonce store reject. |
| Proxy clock skew | Replica lệch nhiều giây | Test phát hiện lệch kết quả; cần NTP/monitoring. |
| Backend authorization denied | Credential hợp lệ của client thiếu quyền với tenant | Authentication PASS, authorization DENY. |

### Câu hỏi tự kiểm tra

1. `Authorization` mang credentials hay có nghĩa client đã được phép mọi business action?
2. Với HMAC-V1 của bài, timestamp được lấy từ `ts` hay `Date`/`X-Timestamp`? Vì sao không được fallback?
3. Nếu đổi `ts` trong Authorization nhưng không thay `sig`, điều gì phải xảy ra khi verifier tính lại HMAC?
4. Vì sao `ts="01795831200"` phải bị từ chối dù có thể parse cùng số với `1795831200`?
5. Vì sao parser phải reject hai `Authorization` hoặc hai auth-param `ts` trước khi ứng dụng chọn một giá trị?
6. Với `P=300` và `F=60`, vì sao nonce store phải lưu có thể tới **370 giây** nếu claim ở đầu cửa sổ?
7. So sánh Base64 signature dạng text có tốt bằng decode 32 bytes và `MessageDigest.isEqual` không?
8. Client có HMAC hợp lệ qua key rotation có tự động được truy cập payment của tenant khác không?

## 13. Checklist triển khai

- [ ] Công bố đúng một HMAC auth scheme/profile và cấu trúc `Authorization`, tên tham số `client`/`keyid`/`ts`/`nonce`/`sig`, cách trích giá trị đã parse.
- [ ] Dùng HTTP parser đáng tin; reject **duplicate Authorization** và duplicate auth-param, các field bị gộp, CR/LF, obs-fold, malformed quotes và header vượt size.
- [ ] Nếu dùng parser auth-param tổng quát, xử lý đúng case-insensitive names, quotes/escapes/OWS; không tự dùng `split(",")` bừa.
- [ ] Timestamp nằm trong **parsed credential**, Unix epoch **seconds** chính tắc; reject leading zero, sai unit, dấu cộng, float, overflow.
- [ ] **Ký chính `ts` đó trong canonical**, không lấy một timestamp khác từ `Date` hoặc `X-Timestamp` để freshness.
- [ ] Dựng canonical bằng method, raw URI/query, audience, client/key ID, timestamp, nonce, Content-Type và body hash thực nhận; thống nhất LF/UTF-8/encoding.
- [ ] Không đưa `sig` vào chính canonical; decode Base64 chuẩn padded thành full HMAC-SHA256 **32 byte** và dùng `MessageDigest.isEqual`.
- [ ] Chọn shared secret theo client/key ID từ trusted keyring, kiểm tra active/revoked, algorithm, audience, scope và route.
- [ ] Freshness theo **server clock**, policy `now-P <= ts <= now+F` và ranh giới inclusive/exclusive rõ ràng; kiểm tra clock skew/NTP.
- [ ] Sau HMAC hợp lệ, claim nonce **atomically** trên store dùng chung, namespace theo audience+client, TTL tới sau `signedTs+P+margin`.
- [ ] Không bỏ qua replay guard vì cache hit/idempotency hay vì credential HMAC đã được ký trước đó.
- [ ] Gateway và backend sử dụng cùng request semantics đã ký; chặn direct bypass và forwarded identity headers không tin cậy.
- [ ] Không log nguyên `Authorization` hoặc secret/body nhạy cảm; response 401/403 và `WWW-Authenticate` theo HTTP policy.
- [ ] Kiểm tra **authorization** theo client, tenant, action, resource và dùng **idempotency** cho side effect retry bằng nonce mới.
- [ ] Test timestamp -300/-301/+60/+61, đổi timestamp không ký lại, duplicate parser, key rotation, clock drift, proxy HTTP/2 và replay.

**Kết luận:** **Timestamp field trong Authorization header** là một phần của **credential HMAC**, phải được **parse không mơ hồ, biểu diễn đúng unit/format và ràng buộc trong canonical request**. Việc timestamp còn trong cửa sổ server cho phép chỉ là một điều kiện: server còn phải xác minh full HMAC tag, key policy và nonce chống replay trước khi cấp quyền. Chọn một nguồn timestamp đã ký, tránh parser differential qua proxy/gateway và không nhầm authentication với business authorization.
