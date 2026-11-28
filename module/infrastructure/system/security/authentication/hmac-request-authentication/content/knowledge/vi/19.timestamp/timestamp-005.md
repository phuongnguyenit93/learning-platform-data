# Timestamp freshness: xác định HTTP request HMAC còn hiệu lực theo thời gian

**Timestamp freshness** (độ mới của dấu thời gian) là phép kiểm tra server thực hiện để quyết định một HTTP request đã ký bằng HMAC có nằm trong **cửa sổ thời gian được chấp nhận** hay không. Chữ ký HMAC đúng không bảo đảm request còn mới: một kẻ tấn công có thể ghi lại toàn bộ request hợp lệ rồi phát lại. Timestamp được **đưa vào canonical request trước khi ký**, còn verifier dùng **đồng hồ của server** để giới hạn thời gian chấp nhận.

Bài thuộc chương **Timestamp**, module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Module thiết kế xác thực HTTP request với **shared secret**, canonical method/URI/headers/body; thực hành xác minh HMAC, chống replay bằng timestamp/nonce, key rotation, kiểm thử proxy/gateway và phân biệt **xác thực** với **phân quyền**. Trọng tâm ở đây là **kiểm tra độ mới chính xác**, tính ranh giới thời gian và giải thích vì sao timestamp **không thể thay thế nonce**.

**Ý chính:** Với hợp đồng minh họa có `pastWindow = 300 giây` và `futureTolerance = 60 giây`, request có dấu thời gian `ts` chỉ còn mới nếu:

~~~text
nowServer - 300 <= ts <= nowServer + 60
~~~

Đây là **policy của ứng dụng ví dụ**, không phải quy định mặc định của HMAC hoặc HTTP. Cả hai ranh giới được chọn **bao gồm dấu bằng**; server và client phải cùng biết quy tắc, unit, định dạng timestamp và thời điểm verifier đo đồng hồ.

## 1. Mục tiêu học tập

Hoàn thành bài, người học có thể:

1. Phân biệt **HMAC hợp lệ**, **timestamp còn mới** và **request chưa bị phát lại**: ba điều kiện liên quan nhưng không đồng nghĩa.
2. Biểu diễn timestamp thành **Unix epoch seconds UTC**, không nhầm với milliseconds, local timezone hoặc chuỗi ISO-8601 tùy biến.
3. Viết điều kiện freshness bất đối xứng: cho phép request quá khứ trong `pastWindow`, chấp nhận tương lai trong `futureTolerance`, xử lý **đúng ranh giới**.
4. Giải thích tác động của clock drift, NTP, retry, queue delay, server replicas và proxy/gateway đến cửa sổ xác thực.
5. Tính được **thời điểm nonce có thể hết hạn** theo signed timestamp, không dùng TTL ngắn khiến replay có thể lọt trở lại.
6. Thực hành Java 17 với `Clock`, `Instant`, `Mac`, `MessageDigest.isEqual`, `SecureRandom` và các ca kiểm thử sát biên.
7. Kết hợp freshness với key rotation, route/tenant authorization và idempotency trong tác vụ có side effect.

## 2. Timestamp freshness bảo vệ điều gì?

Giả sử một client hợp lệ gửi:

~~~http
POST /v1/transfers?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-42
X-Key-Id: key-2026-11
X-Timestamp: 1795831200
X-Nonce: 00112233445566778899aabbccddeeff
X-Content-SHA256: <64-hex-lowercase>
X-Signature: <base64-hmac-sha256-full-tag>

{"transferId":"t-123","amount":50000}
~~~

Các trường `<...>` là **placeholder** để mô tả định dạng. Ví dụ, timestamp `1795831200` tương ứng **2026-11-28 02:00:00 UTC**. Một request có chữ ký thật được tính bằng secret và tất cả signed fields sẽ không thể bị thay đổi timestamp tùy ý mà vẫn khớp HMAC.

Tuy nhiên, nếu attacker **sao chép nguyên vẹn** các byte request rồi gửi lại trong khi timestamp vẫn nằm trong cửa sổ cho phép, **HMAC vẫn hợp lệ**:

~~~mermaid
sequenceDiagram
    participant C as Client hợp lệ
    participant A as Attacker/replay proxy
    participant V as HMAC verifier
    participant N as Shared nonce store
    C->>V: POST + signed timestamp + nonce + HMAC
    V->>V: HMAC đúng, timestamp còn mới
    V->>N: Claim nonce
    N-->>V: Chưa từng dùng, accepted
    A->>V: Phát lại nguyên request và chữ ký
    V->>V: HMAC vẫn đúng, timestamp có thể còn mới
    V->>N: Claim cùng nonce
    N-->>V: Đã sử dụng, reject replay
~~~

**Timestamp** giới hạn **khoảng thời gian** một request có thể được chấp nhận; **nonce** ngăn **dùng lại request trong khoảng ấy**. Đối với nghiệp vụ chuyển tiền, một **idempotency key đã ký** còn cần thiết để tránh việc client tự tạo nonce mới cho cùng một ý định và gây ra side effect lặp.

| Kiểm tra | Câu hỏi trả lời | Nếu bỏ qua |
| --- | --- | --- |
| HMAC trên canonical request | Request có được tạo bởi bên biết secret, và các trường đã ký có nguyên vẹn không? | Attacker sửa method, URI, body hoặc timestamp dễ hơn. |
| Timestamp format/freshness | Thời gian được ký có nằm trong khoảng server cho phép không? | Request cũ có thể được phát lại vô thời hạn. |
| Nonce nguyên tử, dùng chung | Nonce này đã từng được xác thực cho cùng client/audience chưa? | Có thể replay nhiều lần trong freshness window. |
| Idempotency nghiệp vụ | Hai request khác nonce có cùng một ý định side effect không? | Client retry hợp lệ vẫn có thể tạo giao dịch trùng. |
| Authorization | Client có quyền thực hiện action với resource/tenant không? | Chữ ký đúng có thể bị lạm dụng để truy cập ngoài quyền. |

## 3. Định dạng timestamp phải là một phần của signing contract

### 3.1. Unix epoch seconds thay vì chuỗi thời gian tùy ý

Hợp đồng minh họa quy định:

~~~text
x-timestamp:<decimal-epoch-seconds>
~~~

Timestamp là **số giây nguyên** tính từ mốc **1970-01-01T00:00:00Z**, không phải chuỗi ngày giờ ở timezone của client, không phải milliseconds và không có fractional seconds.

| Giá trị gửi | Ý nghĩa hoặc lỗi | Theo contract minh họa |
| --- | --- | --- |
| `1795831200` | Epoch seconds dạng thập phân, UTF-8/ASCII | Có thể hợp lệ sau freshness/HMAC. |
| `1795831200000` | Epoch milliseconds bị gửi nhầm | Reject vì quá xa tương lai. |
| `01795831200` | Có leading zero; số học có thể giống nhưng byte ký khác | **Reject format**. |
| `+1795831200` | Có dấu cộng | **Reject format**. |
| `1795831200.000` | Có phần thập phân | **Reject format**. |
| `2026-11-28T02:00:00Z` | ISO-8601, không đúng kiểu field của contract này | **Reject format**. |
| `1795831200 ` | SP cuối | **Reject format**, không trim ngầm. |
| `-1` hoặc `0` | Không khớp policy ví dụ về số dương không leading zero | **Reject format**. |
| Chuỗi số vượt `long` | Có thể gây overflow khi parse | **Reject an toàn**, không wrap. |

Định dạng minh họa là regex `[1-9][0-9]{0,18}` rồi `Long.parseLong`; regex chỉ kiểm tra cú pháp, bước parse vẫn phải bắt `NumberFormatException` vì có thể có số 19 chữ số lớn hơn `Long.MAX_VALUE`.

**Tại sao strict?** Hai chuỗi `1795831200` và `01795831200` có thể biểu diễn cùng giá trị số, nhưng HMAC ký **byte của canonical request**. Nếu một bên chuẩn hóa leading zero còn bên kia ký nguyên văn, hệ thống có sai lệch. Hợp đồng xác định **một representation** khiến signer/verifier có thể tạo byte giống nhau và reject input mơ hồ.

### 3.2. UTC, timezone và leap seconds

Epoch seconds biểu diễn một thời điểm độc lập timezone. Trong Java, sử dụng `Instant.now()` hoặc `Clock.instant()`; không tự chuyển `LocalDateTime` cộng với timezone không rõ ràng để ký. **Timezone hiển thị** ở Việt Nam (UTC+07:00) không thay đổi số epoch seconds của cùng thời điểm.

Timestamps theo epoch và đồng hồ hệ điều hành còn chịu ảnh hưởng chính sách đồng bộ thời gian và cách hệ thống xử lý leap seconds. Tài liệu học tập này **không** thiết kế một chuẩn time-scale mới; client/server phải dùng **cùng time scale/Unix time convention** và có cấu hình đồng bộ clock đáng tin cậy.

### 3.3. Timestamp phải nằm trong phần được HMAC ký

Nếu verifier kiểm tra `X-Timestamp` nhưng canonical **không có timestamp**, attacker có thể thay timestamp cũ thành mới mà không cần biết key.

~~~text
SAI:
  HMAC(secret, method + path + bodyHash)
  Kiểm tra X-Timestamp không được ký

ĐÚNG:
  HMAC(secret, method + path + x-timestamp + x-nonce + bodyHash + ...)
  Verifier kiểm tra timestamp vừa dùng để dựng canonical
~~~

Đồng thời phải ký key ID, client ID, raw URI/query, method, các signed headers và body hash theo policy. Không để gateway đọc timestamp từ một header còn verifier dựng canonical từ header khác; **giá trị được kiểm tra freshness phải chính là giá trị đã được ký**.

## 4. Công thức freshness và ranh giới thời gian

Đặt:

- `ts`: epoch seconds do client ghi trong signed request.
- `now`: epoch seconds **verifier đo từ server clock** tại thời điểm kiểm tra.
- `P` = `pastWindowSeconds`: tối đa bao nhiêu giây trong quá khứ vẫn nhận.
- `F` = `futureToleranceSeconds`: tối đa bao nhiêu giây ở tương lai vẫn nhận.

Contract minh họa chọn `P = 300` và `F = 60`:

\[
\operatorname{fresh}(ts,now)\iff now-P\le ts\le now+F
\]

**Hai biên được tính inclusive.** Nếu muốn exclusive ở một API khác, phải thay đổi đồng bộ policy và test vectors. Không nên để mỗi replica tự chọn `<` hoặc `<=` theo suy đoán.

<text color="secondary" size="sm">Trục thời gian minh họa với server now = 1795831200 (2026-11-28 02:00:00 UTC).</text>

~~~text
Quá cũ                      Chấp nhận                    Quá xa tương lai
   |----------------------------|------------------------------|
 ts < now - 300         now - 300 <= ts <= now + 60       ts > now + 60
                       [----------------------]
 1795830899          1795830900   1795831200   1795831260  1795831261
   REJECT               ACCEPT        ACCEPT       ACCEPT       REJECT
~~~

| Signed timestamp | Lệch so với server now | Freshness khi `P=300,F=60` |
| ---: | ---: | --- |
| `1795830899` | -301 s | Reject, quá cũ 1 giây. |
| `1795830900` | **-300 s** | Accept, đúng biên dưới. |
| `1795830901` | -299 s | Accept. |
| `1795831200` | 0 s | Accept. |
| `1795831259` | +59 s | Accept. |
| `1795831260` | **+60 s** | Accept, đúng biên trên. |
| `1795831261` | +61 s | Reject, quá xa tương lai 1 giây. |

### 4.1. Vì sao cho phép timestamp ở tương lai?

Client và server có thể không hoàn toàn đồng bộ đồng hồ. Nếu client nhanh hơn server 10 giây, request hợp lệ có `ts > now`. Một khoảng **future tolerance** nhỏ cho phép độ lệch clock dự kiến. Tuy nhiên, **cho phép tương lai làm tăng thời gian sống tiềm năng của request**, nên `F` không nên quá lớn.

Nếu phát hiện clock lệch vượt policy, giải pháp tốt là **sửa đồng bộ thời gian**, không mở rộng window vô hạn để “hết lỗi HMAC”. Các dịch vụ cần bảo vệ mạnh hoặc môi trường nhạy cảm có thể chọn tolerance nhỏ hơn tùy threat model và năng lực đồng bộ.

### 4.2. Vì sao không chỉ dùng `Math.abs(now - ts) <= 300`?

Điều kiện đối xứng:

~~~java
// Không diễn đạt đúng policy cho phép quá khứ 300s, tương lai 60s.
boolean symmetric = Math.abs(now - timestamp) <= 300;
~~~

nó cho phép timestamp **ở tương lai tới 300 giây**, không phải 60 giây. Hơn nữa, phép trừ hai `long` hoặc `Math.abs(Long.MIN_VALUE)` có thể overflow. Hãy kiểm tra bằng **hai ngưỡng rõ ràng**, kết hợp kiểm tra kiểu số chính tắc và xử lý overflow.

~~~java
static boolean fresh(long ts, long now, long past, long future) {
    if (past < 0 || future < 0) {
        throw new IllegalArgumentException("Window âm");
    }
    try {
        long oldest = Math.subtractExact(now, past);
        long newest = Math.addExact(now, future);
        return ts >= oldest && ts <= newest;
    } catch (ArithmeticException overflow) {
        return false; // Fail closed nếu phép tính bất thường.
    }
}
~~~

Hàm ví dụ dùng cửa sổ dương nhỏ, `now` từ đồng hồ server và `ts` đã parse thành công. Với hệ thống cần bao quát toàn miền thời gian `long` bất thường, có thể sử dụng `Instant`/`BigInteger` theo contract; không cố chấp nhận giá trị vượt giới hạn bằng số bị wrap.

### 4.3. “Fresh” tại thời điểm nào?

Verifier phải đọc **server clock gần lúc xác minh**, thay vì dùng timestamp do một proxy ngoài hoặc header client cấp để quyết định `now`. Nếu request được xếp hàng 10 phút trước khi xử lý, freshness tại lúc thực thi có thể khác lúc được gateway nhận. Cần chỉ rõ **trust boundary** và thời điểm kiểm tra cuối trước khi cấp quyền.

Với gateway xác minh rồi backend xử lý bất đồng bộ, **đừng để backend dựa vào một header `X-Verified` vô danh** hoặc sử dụng kết quả xác minh đã hết hạn cho hành động mới. Hợp đồng nội bộ phải ràng buộc danh tính, request, thời hạn hoặc thời điểm gateway đã xác minh, có kênh xác thực gateway→backend và chính sách chống replay/retry ở tầng nghiệp vụ.

## 5. Timestamp freshness không tự chống replay

Tại thời điểm `now`, một request có `ts = now` có thể được phát lại rất nhiều lần trong khoảng **300 giây tiếp theo** nếu không kiểm soát nonce; HMAC trên cùng byte vẫn đúng.

~~~mermaid
flowchart TD
    R["HTTP request với signed timestamp + nonce + HMAC"] --> P["Strict parse và kiểm tra signed fields"]
    P --> T{"Timestamp còn mới theo server clock?"}
    T -->|Không| X["Reject"]
    T -->|Có| H["Dựng canonical và tính expected HMAC"]
    H --> E{"Full tag HMAC khớp?"}
    E -->|Không| X
    E -->|Có| N{"Atomic claim(client, audience, nonce)?"}
    N -->|Đã có| X
    N -->|Nonce mới| A["Authorization + idempotency + business action"]
~~~

**Không** claim nonce trước khi HMAC hợp lệ: attacker có thể gửi request giả mạo với nonce lấy từ request hợp lệ để **đốt nonce** trong store và khiến client thật bị từ chối. Hãy kiểm tra format/giới hạn và freshness sớm nếu cần giảm tải, nhưng chỉ ghi nhận nonce sau khi đã xác thực tag.

### 5.1. Nonce đủ ngẫu nhiên và có phạm vi kiểm tra

Ví dụ nonce 16 byte do `SecureRandom` sinh ra, mã hóa thành **32 ký tự hex chữ thường**. Với mỗi request mới phải có nonce mới. Khóa nonce lưu trữ nên có phạm vi gắn với **client identity và audience**, ví dụ:

~~~text
nonceStorageKey = (audience, authenticatedClientId, nonce)
~~~

**Không** thêm key ID vào storage key chỉ để dễ key rotation nếu điều đó cho phép một client dùng **cùng nonce trên key cũ và key mới** và vẫn vượt qua replay detector. Cần có policy nhất quán cho tất cả key hiện đang được chấp nhận của cùng client/audience. Mỗi hệ thống có thể đặt nonce scope khác (global per client, per audience), nhưng phải **nhất quán giữa các replica** và giữa các phiên bản khóa có thể ký cùng hành động.

### 5.2. TTL nonce phải dựa trên thời điểm request có thể hết hạn

Với hai bất đẳng thức:

~~~text
ts <= now + F    -> request có thể được nhận sớm nhất khi now = ts - F
ts >= now - P    -> request có thể được nhận muộn nhất khi now = ts + P
~~~

Do đó **toàn bộ khoảng thời gian lý thuyết một timestamp có thể còn mới** trải từ `ts-F` tới `ts+P`, dài tối đa **`F+P` giây**.

<text strong>Với `P=300,F=60`, tổng cửa sổ có thể là **360 giây**, không phải chỉ 60 hoặc 300 giây.</text>

Nếu server nhận request sớm nhất khi `now = ts-F` và claim nonce ngay, còn store đặt TTL **300 giây kể từ lúc claim**, nonce có thể biến mất ở `now=ts+240`, trong khi request cùng chữ ký vẫn còn **60 giây freshness**. Kẻ tấn công khi ấy có thể phát lại thành công **sau khi nonce bị xóa nhưng trước khi timestamp hết hạn**.

**Giải pháp:** tính expiration theo **signed timestamp đã xác thực**:

~~~text
nonceExpiresAt >= signedTimestamp + pastWindowSeconds + safetyMargin
~~~

Khi chèn nonce lần đầu, có thể đặt TTL bằng `expiresAt - trustedStoreNow`; store phải dùng đồng hồ đáng tin và **atomic put-if-absent với expiration**. Tránh đặt TTL theo “300 giây từ lúc request đến” khi tương lai được cho phép. Nếu chỉ có TTL cố định, cần ít nhất `P + F + margin` từ lúc claim trong các điều kiện clock assumptions của policy.

**Cảnh báo vận hành:** Clock của replica và store có thể lệch, mạng có trễ, thời điểm ghi expiration có thể bị làm tròn, hoặc server clock bị điều chỉnh lùi. Cần margin an toàn, NTP monitoring và fail-closed/giảm khả năng nhận request khi đồng hồ không đáng tin. Trong các hệ thống yêu cầu chống replay mạnh, đừng cho phép xóa nonce sớm chỉ vì một node suy đoán timestamp đã hết hạn.

### 5.3. Retry nghiệp vụ và idempotency

Nonce giúp chặn **cùng một request đã ký** được gửi lại. Nhưng client có thể retry với `nonce` mới, `timestamp` mới và HMAC mới — đây là request khác về mặt bảo vệ replay. Một lệnh chuyển tiền cần **idempotency key** được bảo vệ bởi HMAC và xử lý nguyên tử ở tầng business, không chỉ một nonce.

## 6. Clock skew, đồng bộ thời gian và độ tin cậy vận hành

### 6.1. Có bao nhiêu nguồn tạo độ lệch?

| Nguồn | Dấu hiệu | Biện pháp |
| --- | --- | --- |
| Client clock chạy nhanh/chậm | Request bị reject dù HMAC đúng | Đồng bộ NTP; hướng dẫn client đo epoch seconds bằng clock hệ thống đúng. |
| Server replica lệch nhau | Request cùng timestamp accepted ở node A, rejected ở node B | Đồng bộ tất cả replica, theo dõi `clock_offset`, có chung window policy. |
| Load balancer/proxy trì hoãn | Timestamp cũ đi trong queue rồi hết hạn | Giới hạn queue/retry delay; không dùng timestamp do proxy ngoài khai. |
| Offline client tạo request rất sớm rồi gửi muộn | Chữ ký đúng nhưng quá hạn | Tạo timestamp **ngay trước khi gửi** và ký lại khi retry; nonce mới. |
| Đồng hồ server bị chỉnh lùi | Request cũ có thể trở lại cửa sổ hợp lệ | Đồng bộ clock, cảnh báo jump, nonce TTL đủ dài, fail closed khi clock không tin cậy. |
| Đồng hồ server nhảy tới | Nhiều request hợp lệ thành “quá cũ” | Monitoring, alert, giảm phạm vi lỗi bằng kiến trúc đồng bộ clock đáng tin. |
| Gateway ghi nhận nhận lúc A, backend xử lý lúc B | Kết quả freshness khác do queue | Nêu rõ ranh giới verify và lifecycle của kết quả đã xác thực. |
| Client gửi epoch milliseconds | Timestamp lớn hơn server hàng nghìn lần | Reject đúng unit; không tự chia `1000` để “tương thích”. |

**Clock wall-time** (`Instant.now()`/`Clock.instant()`) dùng để so sánh dấu thời gian từ các máy khác nhau. **Monotonic time** (`System.nanoTime()`) hữu ích đo khoảng thời gian cục bộ, nhưng không thể đưa giá trị `nanoTime()` vào HTTP header để so sánh với epoch seconds của hệ thống khác.

Không nên bật chế độ “accept every timestamp” khi NTP gặp lỗi. Nếu freshness không thể được bảo đảm, phải có chính sách degrade/fail-closed theo mức rủi ro: từ chối request có side effect nhạy cảm, hạn chế xử lý hoặc bảo vệ bằng cơ chế xác thực bổ sung.

### 6.2. Chọn window là một trade-off

| Lựa chọn | Lợi ích | Chi phí/rủi ro |
| --- | --- | --- |
| `P` nhỏ | Hạn chế khoảng thời gian phát lại | Dễ reject request trễ hoặc client clock chậm. |
| `P` lớn | Chịu được delay/queue lâu | Request giữ hiệu lực lâu, nonce TTL lớn, lưu trữ nhiều hơn. |
| `F = 0` | Không nhận request có timestamp ở tương lai | Client clock nhanh dù rất ít cũng bị reject. |
| `F` lớn | Dễ chấp nhận client clock nhanh | Khoảng thời gian sống của request và nonce retention tăng. |
| NTP tốt + window nhỏ | Giảm cửa sổ mà vẫn hoạt động ổn định | Cần monitoring, cấu hình clock và xử lý sự cố. |

Không có một con số `300/60` đúng cho mọi sản phẩm. Với hệ thống tài chính hoặc có side effect, chọn window dựa vào latency thực đo (p99/p999), clock skew quan sát, tốc độ nonce store, yêu cầu availability và khả năng kiểm soát retry/idempotency. **Tuyệt đối không thay tính ngẫu nhiên/atomic nonce bằng việc thu nhỏ window**.

### 6.3. Log và telemetry

Nên log có kiểm soát:

- Request ID, tenant/audience hoặc client identifier đã xác thực ở mức phù hợp.
- `timestamp-format-invalid`, `too-old`, `too-far-in-future`, `replay-nonce`, `invalid-signature` dưới dạng mã lỗi.
- Chênh lệch `now - signedTs` sau khi kiểm tra format và theo chính sách lộ thông tin; không coi timestamp chưa xác thực là dấu hiệu đáng tin.
- NTP offset/clock drift và tỉ lệ reject theo replica để phát hiện sự cố clock.

Không log secret, raw signature, token nhạy cảm hoặc body chuyển tiền; không phản hồi cho client dữ liệu phục vụ đoán key. Giảm khả năng attacker phân biệt key có tồn tại bằng thông báo lỗi public thống nhất, rate limiting và chính sách lookup.

## 7. Hợp đồng HMAC-TIMESTAMP-FRESHNESS-V1

Để có bài tập byte chính xác, định nghĩa endpoint mô phỏng:

| Thuộc tính | Policy |
| --- | --- |
| Version | `HMAC-TIMESTAMP-FRESHNESS-V1` |
| Method | `POST` viết hoa, đúng method thực thi |
| Raw target | `/v1/transfers?currency=VND` |
| Audience | `transfers-api` từ policy server |
| Signed headers | `x-client-id`, `x-key-id`, `x-timestamp`, `x-nonce`, `content-type`, `x-content-sha256` |
| Timestamp | Unix epoch **seconds**, regex `[1-9][0-9]{0,18}`, parse `long` an toàn |
| Freshness | `now-300 <= ts <= now+60`, biên **inclusive** |
| Nonce | 16 byte ngẫu nhiên, 32 ký tự lowercase hex |
| Body | SHA-256 trên byte JSON UTF-8 thực nhận, hex lowercase |
| Signature | Full HMAC-SHA256 **32 byte**, Base64 chuẩn padded (44 ASCII chars) |
| Delimiter | Nối dòng LF, UTF-8; **không** có newline cuối |
| Key lookup | `client ID + key ID`, key active, audience/scope hợp lệ |

Canonical request:

~~~text
HMAC-TIMESTAMP-FRESHNESS-V1
POST
/v1/transfers?currency=VND
audience:transfers-api
x-client-id:partner-42
x-key-id:key-2026-11
x-timestamp:1795831200
x-nonce:00112233445566778899aabbccddeeff
content-type:application/json
x-content-sha256:<lowerhex-sha256-body>
~~~

Giá trị `<lowerhex-sha256-body>` là placeholder. Hợp đồng không lấy thời gian **từ thời điểm server ký**; client ký timestamp của **chính request gửi** và server chỉ dùng server clock để đánh giá freshness.

~~~text
canonicalBytes = UTF8(canonicalLinesSeparatedByLF)
tag           = HMAC_SHA256(sharedSecretBytes, canonicalBytes)
X-Signature   = Base64_standard_padded(tag)
~~~

**Vì sao timestamp đứng trong canonical?** Client không thể tự ý nâng timestamp một request cũ đã ký để kéo dài hạn mà không tính lại HMAC. Nếu một hợp đồng khác dùng một header timestamp mới (ví dụ `X-Signed-Date`), phải version hóa canonical/headers; không để verifier tự tìm “bất kỳ timestamp nào còn mới” trong các header có thể bị proxy gộp.

## 8. Java 17: HMAC + timestamp freshness + nonce

Ví dụ dưới đây sử dụng **Java 17**. Nó mô phỏng client ký request, verifier dùng server clock và một store nonce cục bộ để minh họa. `java.net.http.HttpRequest` chỉ được **xây dựng, không gửi qua mạng**.

**Phạm vi demo:** Fixed method/target, các header đã parse giả lập trong `SignedRequest`, key test sinh `SecureRandom`, nonce store là một `Set` trong **một JVM không TTL**. Không đưa nguyên mô hình này vào production mà thiếu HTTP ingress kiểm soát duplicate/framing, key manager, shared atomic nonce store, authorization/idempotency và kiểm thử proxy/gateway.

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
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class TimestampFreshnessExample {
    private static final SecureRandom RNG = new SecureRandom();
    private static final String METHOD = "POST";
    private static final String RAW_TARGET =
        "/v1/transfers?currency=VND";
    private static final String AUDIENCE = "transfers-api";
    private static final String CLIENT_ID = "partner-42";
    private static final String KEY_ID = "key-2026-11";
    private static final String CONTENT_TYPE = "application/json";
    private static final long PAST_WINDOW = 300;
    private static final long FUTURE_TOLERANCE = 60;

    record SignedRequest(
        String method, String rawTarget,
        String clientId, String keyId, String timestamp,
        String nonce, String contentType, String bodyDigest,
        String signature, byte[] body
    ) {}

    record KeyRecord(
        String clientId, String keyId, byte[] secret,
        Instant activeFrom, Instant expiresAt, boolean revoked
    ) {}

    // Demo: atomic trong một JVM, KHÔNG TTL hoặc multi-node.
    static final class DemoNonceStore {
        private final Set<String> seen =
            ConcurrentHashMap.newKeySet();

        boolean claim(String audience, String clientId, String nonce) {
            return seen.add(audience + ":" + clientId + ":" + nonce);
        }
    }

    static String sha256Hex(byte[] body)
            throws GeneralSecurityException {
        return HexFormat.of().formatHex(
            MessageDigest.getInstance("SHA-256").digest(body)
        );
    }

    static byte[] hmac(byte[] secret, String canonical)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(
            canonical.getBytes(StandardCharsets.UTF_8)
        );
    }

    static String canonical(
            String method, String rawTarget, String clientId,
            String keyId, String timestamp, String nonce,
            String contentType, String bodyHash) {
        if (!METHOD.equals(method) || !RAW_TARGET.equals(rawTarget) ||
            !CLIENT_ID.equals(clientId) || !KEY_ID.equals(keyId) ||
            !CONTENT_TYPE.equals(contentType) ||
            timestamp == null ||
            !timestamp.matches("[1-9][0-9]{0,18}") ||
            nonce == null || !nonce.matches("[0-9a-f]{32}") ||
            bodyHash == null || !bodyHash.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException(
                "Signing contract hoặc canonical fields không hợp lệ"
            );
        }
        return String.join("\n",
            "HMAC-TIMESTAMP-FRESHNESS-V1",
            method,
            rawTarget,
            "audience:" + AUDIENCE,
            "x-client-id:" + clientId,
            "x-key-id:" + keyId,
            "x-timestamp:" + timestamp,
            "x-nonce:" + nonce,
            "content-type:" + contentType,
            "x-content-sha256:" + bodyHash
        );
    }

    // V1: full HMAC-SHA256 32 bytes, Base64 standard padded 44 chars.
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
        } catch (IllegalArgumentException invalidBase64) {
            return null;
        }
    }

    static Long parseTimestamp(String text) {
        if (text == null || !text.matches("[1-9][0-9]{0,18}")) {
            return null;
        }
        try {
            return Long.parseLong(text);
        } catch (NumberFormatException overflow) {
            return null;
        }
    }

    static boolean isFresh(long signedEpochSeconds,
            long serverEpochSeconds) {
        try {
            long oldest =
                Math.subtractExact(serverEpochSeconds, PAST_WINDOW);
            long newest =
                Math.addExact(serverEpochSeconds, FUTURE_TOLERANCE);
            // Ranh giới inclusive, không dùng Math.abs().
            return signedEpochSeconds >= oldest &&
                   signedEpochSeconds <= newest;
        } catch (ArithmeticException overflow) {
            return false;
        }
    }

    static SignedRequest sign(byte[] secret, Clock clientClock)
            throws GeneralSecurityException {
        byte[] body =
            "{\"transferId\":\"t-123\",\"amount\":50000}"
                .getBytes(StandardCharsets.UTF_8);
        byte[] nonceBytes = new byte[16];
        RNG.nextBytes(nonceBytes);
        String nonce = HexFormat.of().formatHex(nonceBytes);
        String timestamp = Long.toString(
            clientClock.instant().getEpochSecond()
        );
        String bodyDigest = sha256Hex(body);
        String canonical = canonical(
            METHOD, RAW_TARGET, CLIENT_ID, KEY_ID,
            timestamp, nonce, CONTENT_TYPE, bodyDigest
        );
        String signature = Base64.getEncoder().encodeToString(
            hmac(secret, canonical)
        );
        return new SignedRequest(
            METHOD, RAW_TARGET, CLIENT_ID, KEY_ID,
            timestamp, nonce, CONTENT_TYPE,
            bodyDigest, signature, body
        );
    }

    static boolean verify(
            SignedRequest req, Map<String, KeyRecord> keyring,
            Clock serverClock, DemoNonceStore nonces)
            throws GeneralSecurityException {
        if (req == null || req.body() == null ||
            req.body().length > 65536) {
            return false;
        }
        byte[] suppliedTag = decodeSignature(req.signature());
        if (suppliedTag == null) {
            return false;
        }
        Long signedSeconds = parseTimestamp(req.timestamp());
        if (signedSeconds == null) {
            return false;
        }

        final String signedCanonical;
        try {
            String actualBodyHash = sha256Hex(req.body());
            if (!actualBodyHash.equals(req.bodyDigest())) {
                return false;
            }
            signedCanonical = canonical(
                req.method(), req.rawTarget(), req.clientId(),
                req.keyId(), req.timestamp(), req.nonce(),
                req.contentType(), actualBodyHash
            );
        } catch (IllegalArgumentException invalidFields) {
            return false;
        }

        Instant serverNow = serverClock.instant();
        if (!isFresh(signedSeconds, serverNow.getEpochSecond())) {
            return false;
        }

        // Client ID/key ID chưa đáng tin; đây mới là lookup từ policy.
        KeyRecord key = keyring.get(
            req.clientId() + ":" + req.keyId()
        );
        if (key == null || key.revoked() ||
            !req.clientId().equals(key.clientId()) ||
            !req.keyId().equals(key.keyId()) ||
            key.secret() == null || key.secret().length < 32 ||
            key.activeFrom() == null || key.expiresAt() == null ||
            serverNow.isBefore(key.activeFrom()) ||
            !serverNow.isBefore(key.expiresAt())) {
            return false;
        }
        byte[] expected = hmac(key.secret(), signedCanonical);
        if (expected.length != 32 ||
            !MessageDigest.isEqual(expected, suppliedTag)) {
            return false;
        }

        // Chỉ claim nonce SAU HMAC; production yêu cầu TTL/chung replica.
        return nonces.claim(
            AUDIENCE, req.clientId(), req.nonce()
        );
    }

    static SignedRequest replaceTimestamp(
            SignedRequest source, String newTimestamp) {
        return new SignedRequest(
            source.method(), source.rawTarget(), source.clientId(),
            source.keyId(), newTimestamp, source.nonce(),
            source.contentType(), source.bodyDigest(),
            source.signature(), source.body()
        );
    }

    static void check(boolean assertion, String message) {
        if (!assertion) {
            throw new AssertionError(message);
        }
    }

    static void rfc4231Vector() throws Exception {
        byte[] vectorKey = new byte[20];
        Arrays.fill(vectorKey, (byte) 0x0b);
        byte[] tag = hmac(vectorKey, "Hi There");
        String expected =
            "b0344c61d8db38535ca8afceaf0bf12" +
            "b881dc200c9833da726e9376c2e32cff7";
        check(expected.equals(HexFormat.of().formatHex(tag)),
            "HMAC-SHA256 RFC 4231 known-answer test sai");
    }

    public static void main(String[] args) throws Exception {
        rfc4231Vector();
        byte[] secret = new byte[32]; // Test-only, không dùng production.
        RNG.nextBytes(secret);
        Clock server = Clock.fixed(
            Instant.parse("2026-11-28T02:00:00Z"), ZoneOffset.UTC
        );
        KeyRecord active = new KeyRecord(
            CLIENT_ID, KEY_ID, secret,
            Instant.parse("2026-01-01T00:00:00Z"),
            Instant.parse("2027-01-01T00:00:00Z"),
            false
        );
        String keyRef = CLIENT_ID + ":" + KEY_ID;
        Map<String, KeyRecord> keys = Map.of(keyRef, active);
        SignedRequest request = sign(secret, server);

        // Tạo request Java HTTP (không gửi ra mạng).
        HttpRequest http = HttpRequest.newBuilder(
                URI.create("https://api.example.test" +
                    request.rawTarget()))
            .header("Content-Type", request.contentType())
            .header("X-Client-Id", request.clientId())
            .header("X-Key-Id", request.keyId())
            .header("X-Timestamp", request.timestamp())
            .header("X-Nonce", request.nonce())
            .header("X-Content-SHA256", request.bodyDigest())
            .header("X-Signature", request.signature())
            .POST(HttpRequest.BodyPublishers.ofByteArray(request.body()))
            .build();
        check(METHOD.equals(http.method()), "Client method sai");
        check(verify(request, keys, server, new DemoNonceStore()),
            "Timestamp hiện tại phải được nhận");

        // Ranh giới inclusive: -300 và +60 chấp nhận.
        for (long offset : new long[] {-300L, +60L}) {
            Clock clientClock =
                Clock.offset(server, Duration.ofSeconds(offset));
            SignedRequest boundary = sign(secret, clientClock);
            check(verify(boundary, keys, server, new DemoNonceStore()),
                "Timestamp ở biên phải được nhận: " + offset);
        }
        // Quá cũ 301s hoặc quá xa tương lai 61s phải reject.
        for (long offset : new long[] {-301L, +61L}) {
            SignedRequest rejected = sign(
                secret, Clock.offset(server, Duration.ofSeconds(offset))
            );
            check(!verify(
                    rejected, keys, server, new DemoNonceStore()),
                "Timestamp ngoài window phải bị reject: " + offset);
        }

        // Future +60s chấp nhận tới now+360 (vì P=300), sau đó hết.
        SignedRequest future = sign(
            secret, Clock.offset(server, Duration.ofSeconds(+60L))
        );
        Clock atLastSecond = Clock.offset(
            server, Duration.ofSeconds(360L)
        );
        Clock afterExpiry = Clock.offset(
            server, Duration.ofSeconds(361L)
        );
        check(verify(future, keys, atLastSecond, new DemoNonceStore()),
            "Request future+60 phải còn mới ở now+360");
        check(!verify(
                future, keys, afterExpiry, new DemoNonceStore()),
            "Request future+60 phải quá hạn ở now+361");

        // Timestamp thay mà không ký lại làm MAC không còn đúng.
        SignedRequest altered = replaceTimestamp(
            request, Long.toString(
                server.instant().getEpochSecond() + 1
            )
        );
        check(!verify(altered, keys, server, new DemoNonceStore()),
            "Sửa timestamp phải bị từ chối dù vẫn trong window");
        check(parseTimestamp("01795831200") == null,
            "Leading zero phải bị từ chối");
        check(parseTimestamp("1795831200000") != null &&
              !isFresh(1795831200000L,
                       server.instant().getEpochSecond()),
            "Milliseconds phải bị từ chối vì không fresh");
        check(parseTimestamp("9999999999999999999") == null,
            "Overflow epoch seconds phải bị từ chối");

        // Cùng một request/nonce chỉ được dùng một lần.
        DemoNonceStore nonces = new DemoNonceStore();
        check(verify(request, keys, server, nonces),
            "Request lần đầu phải thành công");
        check(!verify(request, keys, server, nonces),
            "Phát lại cùng nonce phải bị từ chối");

        // Key bị revoke thì freshness/HMAC đúng vẫn không đủ.
        KeyRecord revoked = new KeyRecord(
            CLIENT_ID, KEY_ID, secret,
            active.activeFrom(), active.expiresAt(), true
        );
        check(!verify(
                request, Map.of(keyRef, revoked), server,
                new DemoNonceStore()),
            "Key revoked phải bị từ chối");
        System.out.println(
            "PASS: signed timestamp, inclusive limits, nonce and HMAC"
        );
    }
}
~~~

### 8.1. Điều gì quan trọng trong chương trình?

- `Clock.fixed` cho phép test biên xác định **không phụ thuộc vào lúc chạy**; production dùng clock hệ thống đáng tin, đồng bộ NTP và monitoring drift.
- `sign` tạo timestamp bằng `clientClock.instant().getEpochSecond()` rồi **đưa đúng chuỗi ấy vào canonical**. Không ký text ISO rồi gửi epoch seconds, hoặc ngược lại.
- `parseTimestamp` kiểm tra syntax **trước khi parse**, bắt overflow. Giá trị milliseconds có thể là số hợp lệ về cú pháp nhưng **nằm ngoài freshness window** nên bị từ chối.
- `isFresh` dùng hai ngưỡng bất đối xứng và biên inclusive; không dùng `Math.abs` và xử lý overflow phép cộng/trừ.
- `verify` không tin `bodyDigest` từ client: nó tính lại SHA-256 của **byte body thực nhận**, tạo canonical và HMAC bằng key server lookup.
- `MessageDigest.isEqual` kiểm tra **full 32-byte HMAC tag**, không so sánh Base64 string hoặc prefix. Chữ ký không đúng không được claim nonce.
- `DemoNonceStore` giữ khóa `audience:clientId:nonce`, không có key ID để tránh bỏ qua replay khi rotation; nhưng nó **không có TTL và không hoạt động qua nhiều JVM**.
- Tests ở offset -300 và +60 là **accepted**, -301 và +61 **rejected**. Một request được ký ở `now+60` vẫn có thể fresh tới `now+360`, chứng minh vì sao TTL nonce phải bao phủ hơn 300 giây trong trường hợp xấu nhất.

### 8.2. Những việc production phải làm thêm

`SignedRequest` chỉ là record test, chưa phải parser HTTP an toàn. Production phải đọc **method, raw URI/query, signed headers, body bytes và chữ ký** từ ingress đã kiểm soát framing/duplicate, có giới hạn kích thước và chống request smuggling. Timestamp phải là **một header đơn trị** trong contract; nếu hai `X-Timestamp` xuất hiện, một hop chọn đầu và hop khác chọn cuối thì freshness/HMAC có thể kiểm tra hai giá trị khác nhau.

Key lookup cần gắn identity với audience, route, thuật toán, key active/revoked và giai đoạn rotation. Nonce storage phải **dùng chung**, atomically claim một lần, có TTL theo signed timestamp và margin. Hợp đồng nghiệp vụ phải bổ sung idempotency, scopes và quyền tenant/resource. Không copy code demo này để tự động xử lý tiền thật.

## 9. Proxy/gateway và thời điểm xác minh

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Proxy hoặc CDN
    participant G as Trusted gateway
    participant V as HMAC verifier
    participant N as Shared nonce store
    participant B as Backend
    C->>P: POST + timestamp + nonce + HMAC
    P->>G: Forward, có thể chậm hoặc sửa metadata
    G->>V: Request đã parse, signed fields/body thực nhận
    V->>V: now = server clock; freshness check
    V->>V: Recompute canonical HMAC full tag
    alt HMAC hợp lệ và còn mới
        V->>N: Atomic claim nonce với expiration đúng
        alt Nonce mới
            N-->>V: Accepted
            V->>B: Verified identity/request
            B->>B: Authorization và idempotency
        else Replay
            N-->>V: Duplicate
            V-->>C: Reject
        end
    else Request quá hạn hoặc MAC sai
        V-->>C: Reject
    end
~~~

| Tình huống | Ảnh hưởng đến freshness/HMAC | Cách xử lý |
| --- | --- | --- |
| Reverse proxy giữ request trong queue lâu | Timestamp có thể hết hạn trước lúc verify | Kiểm tra tại boundary đã định, hạn chế queue delay và retry lại bằng chữ ký mới nếu cần. |
| Proxy thay `X-Timestamp` | Chuỗi canonical thay đổi | HMAC phải thất bại; cấm lấy timestamp từ header không ký. |
| Header `X-Timestamp` trùng | Các hop có thể chọn value khác nhau | Reject duplicate tại ingress trước khi framework gộp. |
| Gateway rewrite raw URI hoặc method | HMAC ký một hành động nhưng backend route hành động khác | Verifier và router phải thống nhất method/target thực thi; ký đủ ngữ nghĩa. |
| HTTP/2 ↔ HTTP/1.1 | Protocol dùng pseudo-header `:method`/`:path`, có thể reorder field | Dựng canonical method/URI cùng contract, không phụ thuộc header order. |
| Client giả `X-Forwarded-Date` hoặc `X-Verified` | Có thể làm giả thời gian/identity nếu backend tin | Không dùng forwarded header ngoài trust boundary để thay server clock hay auth. |
| Gateway verify nhưng backend có đường truy cập trực tiếp | Bypass freshness/HMAC | Chặn bypass, xác thực hop nội bộ và truyền identity an toàn. |
| Proxy replay request trong cửa sổ | HMAC và freshness vẫn PASS | Atomic nonce claim giữa tất cả nodes. |
| Clock replica lệch > tolerance | Một request có kết quả khác nhau | NTP offset monitoring, policy đồng nhất và xử lý sự cố clock. |

**Không dùng timestamp do client tự khai để “điều chỉnh now”**. Một số hệ thống nhận header `Date` hoặc response từ time service để hỗ trợ client sửa clock; đó là chức năng vận hành riêng. Server verifier vẫn phải dùng **đồng hồ đáng tin do mình kiểm soát**.

## 10. Key rotation, freshness và phạm vi của authentication

### 10.1. Key rotation không kéo dài tuổi thọ request

Client ký `x-key-id` trong canonical. Server tra secret tương ứng, kiểm tra key active, audience/scope và trạng thái revoke. Trong giai đoạn rotation có thể đồng thời chấp nhận key cũ/mới trong một khoảng overlap, nhưng **mỗi request vẫn phải thỏa freshness và nonce policy**. Không được vì HMAC khớp với key cũ mà bỏ kiểm tra timestamp hoặc thử nhiều cách parse timestamp.

Nếu một key vừa bị revoke, request ký bằng key ấy bị từ chối dù `ts` vẫn còn trong `now-300..now+60`. Tương tự, nếu một key đã hết hạn, không “hồi sinh” nó bằng cách lấy timestamp client gửi làm thời điểm kiểm tra trạng thái key. Policy có thể cân nhắc key validity tại signed time trong một thiết kế khác, nhưng phải có threat model chống backdating; ví dụ bài này kiểm tra **key có hiệu lực tại server verify time**.

### 10.2. Xác thực đúng không cấp quyền

Một request ký đúng, timestamp còn mới, nonce chưa dùng **vẫn có thể** nhắm tới transfer thuộc tenant không phải của client. Vì thế:

~~~text
HMAC valid        -> Xác minh khả năng sử dụng shared secret
Timestamp fresh   -> Hạn chế độ cũ của request đã ký
Nonce unique      -> Hạn chế replay của cùng nonce
Authorization     -> Client có quyền với action/resource/tenant?
Idempotency       -> Cùng ý định nghiệp vụ có bị thực hiện lặp?
~~~

Không cho phép side effect chỉ vì signed request còn mới. Backend phải dùng **identity đã được xác thực**, cùng method/route/resource đã ràng buộc trong canonical để kiểm tra quyền hạn và giới hạn nghiệp vụ.

## 11. Ma trận kiểm thử timestamp freshness

Sử dụng `Clock.fixed(2026-11-28T02:00:00Z)` và secret test. Mỗi test độc lập dùng nonce mới hoặc store mới; test replay dùng lại nonce. Các ca có `ts` giả ngoài window vẫn có **HMAC hợp lệ cho chính giá trị ts đó**, để chứng minh lỗi là do freshness chứ không phải do chữ ký sai.

| Ca kiểm thử | Dữ liệu/thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Timestamp tại now | `ts=1795831200` | Freshness PASS. |
| Quá khứ đúng ranh giới | `ts=now-300` | PASS vì biên dưới inclusive. |
| Quá khứ quá 1 giây | `ts=now-301` | Reject. |
| Tương lai đúng ranh giới | `ts=now+60` | PASS vì biên trên inclusive. |
| Tương lai vượt 1 giây | `ts=now+61` | Reject. |
| Ở giữa window | `ts=now-120` | PASS. |
| Timestamp epoch milliseconds | `1795831200000` | Reject freshness; không tự chia `1000`. |
| Timestamp có leading zero | `01795831200` | Reject format, dù giá trị số có thể bằng nhau. |
| Timestamp có dấu cộng | `+1795831200` | Reject format. |
| Timestamp có decimal/fraction | `1795831200.0` | Reject format. |
| Timestamp ISO-8601 | `2026-11-28T02:00:00Z` | Reject vì sai contract. |
| Timestamp rỗng/thiếu | Không có `X-Timestamp` | Reject. |
| Duplicate timestamp header | Hai `X-Timestamp` khác case | Reject tại ingress/parser. |
| Timestamp vượt `Long.MAX_VALUE` | `9999999999999999999` | Reject parse, không overflow/wrap. |
| Signed timestamp bị chỉnh | Sửa `X-Timestamp` từ now sang now+1, giữ HMAC cũ | HMAC FAIL dù cả hai thời điểm fresh. |
| HMAC hợp lệ nhưng quá hạn | Sign ngay `now-301` với secret đúng | Reject freshness. |
| Nonce lặp trong window | Gửi hai lần cùng request có `ts=now` | Nonce store từ chối lần hai. |
| Nonce lặp song song | Hai replica claim cùng nonce | Tối đa một claim thành công. |
| Nonce TTL quá ngắn | `ts=now+60`, xóa nonce ở `now+300`, replay ở `now+350` | **Phát hiện rủi ro**; TTL phải giữ tới ít nhất `ts+300+margin`. |
| TTL theo signed timestamp | Nonce hết hạn sau `ts+300+margin` | Không có replay trong thời gian freshness còn hiệu lực. |
| Clock server lệch | Replica A lệch +120s, B đúng giờ | Test phát hiện kết quả không nhất quán; vận hành phải sửa drift. |
| Queue delay 10 phút | Client ký lúc gửi, request đến verifier quá muộn | Reject; không âm thầm bỏ freshness. |
| Key revoked | HMAC có thể khớp với secret cũ | Reject do key policy. |
| Proxy rewrite raw target | Signed method/path/query không khớp backend | Reject HMAC hoặc route policy. |
| Retry nghiệp vụ nonce mới | Cùng transferId, timestamp/nonce/tag mới | HMAC/nonce có thể PASS; idempotency phải ngăn transfer trùng. |
| Không đủ quyền | Client hợp lệ chuyển khoản ngoài tenant | Authentication có thể PASS, authorization DENY. |

### Câu hỏi tự đánh giá

1. Vì sao một request **HMAC hợp lệ** nhưng timestamp ở `now-301` vẫn phải bị từ chối khi `P=300`?
2. Với `now=1795831200`, hai timestamp `1795830900` và `1795831260` có được chấp nhận không? Tại sao?
3. Tại sao không dùng `Math.abs(now - ts) <= 300` nếu policy chỉ cho phép tương lai tối đa 60 giây?
4. Với `P=300` và `F=60`, vì sao nonce có thể phải được giữ **360 giây hoặc lâu hơn** từ lần claim sớm nhất?
5. Khi client gửi `1795831200000`, server nên chia cho 1000 để “tự chữa” hay reject? Giải thích dựa vào signing contract.
6. Vì sao kiểm tra nonce **trước khi** HMAC hợp lệ có thể tạo điểm DoS?
7. Khi gateway xác minh thành công nhưng request nằm trong queue rất lâu, backend cần chính sách gì để không dựa nhầm vào xác thực cũ?
8. Vì sao timestamp freshness không thay thế authorization hoặc business idempotency?

## 12. Checklist triển khai

- [ ] Định nghĩa timestamp **Unix epoch seconds**, định dạng thập phân ASCII chính tắc, không chấp nhận ms/ISO/leading zero nếu contract không cho phép.
- [ ] Đặt `x-timestamp` trong **canonical request được HMAC ký**, cùng method, raw URI/query, signed headers và body hash.
- [ ] Dùng **server clock** đáng tin; không dựa vào `X-Forwarded-Date` hoặc timestamp do proxy ngoài tự khai để xác định `now`.
- [ ] Kiểm tra freshness bằng **hai ngưỡng bất đối xứng** `now-P <= ts <= now+F`, ghi rõ inclusive/exclusive trong contract.
- [ ] Xử lý an toàn regex, `Long.parseLong` overflow và phép cộng/trừ ngưỡng; không tự normalize timestamp sai format.
- [ ] Giữ `P` và `F` nhỏ, có cơ sở từ latency/clock skew thực đo; giám sát NTP offset và clock jumps của từng replica.
- [ ] HTTP ingress reject duplicate/ambiguous timestamp và header bảo mật, framing sai, CR/LF injection, request smuggling.
- [ ] Recompute HMAC từ request thực nhận; decode signature strict, so sánh full tag bằng `MessageDigest.isEqual`.
- [ ] Chỉ sau MAC hợp lệ mới claim nonce **nguyên tử** trong store dùng chung nhiều replica.
- [ ] Thiết kế nonce expiration dựa trên `signedTimestamp + P + margin` hoặc TTL bảo thủ `P+F+margin`, không vô tình xóa sớm.
- [ ] Scope nonce theo audience/client nhất quán qua các key rotation; tránh tự cho phép nonce cũ trên key mới.
- [ ] Key lookup và rotation phải kiểm tra key active/revoked, algorithm, audience và quyền của client; không fallback sang key/format không được policy chấp nhận.
- [ ] Gateway/backend dùng cùng method, raw path/query, signed headers/body và có đường nội bộ xác thực, không cho phép bypass qua header tự khai.
- [ ] Authorization theo action/tenant/resource và idempotency key đã ký cho nghiệp vụ có side effect.
- [ ] Có test ranh giới -300/-301/+60/+61, tương lai sống 360 giây, clock skew, timestamp overflow, nonce replay đa replica, key revoke và proxy rewrite.

**Kết luận:** **Timestamp freshness** là một phép kiểm tra **độ mới của thời gian đã được HMAC ký** dựa trên **đồng hồ đáng tin của verifier**. Nó phải có unit, định dạng, cửa sổ quá khứ/tương lai và ranh giới rõ ràng. Nhưng một timestamp còn mới **không chứng minh request chưa bị dùng lại**: chỉ cơ chế nonce atomic, TTL đủ dài, idempotency và chính sách key/authorization mới hoàn thiện bảo vệ request có side effect.
