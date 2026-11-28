# Đơn vị thời gian trong timestamp của HMAC request authentication

> **Chương:** Timestamp  
> **Chủ đề:** Đơn vị thời gian  
> **Module:** `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION` — Thiết kế xác thực HTTP request bằng HMAC với shared secret và canonical request bảo vệ phương thức, URI, header hoặc body; thực hành xác minh chữ ký, chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt xác thực với phân quyền.

## 1. Vì sao đơn vị thời gian là một chi tiết bảo mật?

Khi xác thực một HTTP request có chữ ký HMAC, server thường chỉ chấp nhận request được gửi trong **một cửa sổ thời gian ngắn**. Client gửi timestamp và đưa chính timestamp đó vào dữ liệu ký; receiver tính lại HMAC, kiểm tra thời gian và chống replay bằng nonce.

Ví dụ:

~~~http
POST /v1/payments?mode=preview HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: merchant-17
X-Key-Id: key-2026-11
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
X-Signature: <base64url-hmac-sha256>

{"orderId":"o-123","amount":150000}
~~~

Câu hỏi quan trọng: **`1795824000` là giây, mili giây, micro giây hay nano giây kể từ epoch?**

Nếu client gửi **milliseconds** nhưng server hiểu là **seconds**, request có thể bị từ chối vì timestamp nằm quá xa tương lai. Ngược lại, nếu verifier tự đoán đơn vị hoặc một tầng chia giá trị cho 1.000 trước khi ký, **cùng một chuỗi header** có thể được hiểu khác nhau giữa verifier, gateway và nghiệp vụ.

Ví dụ mốc cố định để tính toán:

~~~text
UTC instant:       2024-01-01T00:00:00Z
Unix seconds:      1704067200
Unix milliseconds: 1704067200000
Unix microseconds: 1704067200000000
Unix nanoseconds:  1704067200000000000
~~~

Các giá trị biểu diễn **cùng một thời điểm** nhưng có số lượng đơn vị khác nhau. Chúng **không thể tráo đổi trực tiếp trong một signing contract**.

**Chính sách của bài học:** `X-Timestamp` là **Unix epoch seconds nguyên, hệ thập phân ASCII canonical**; cửa sổ chấp nhận minh họa **±300 giây**, hai đầu mút được tính inclusive. Contract này **không đoán đơn vị theo số chữ số** và **không tự chuyển milliseconds sang seconds** tại receiver.

### 1.1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt seconds, milliseconds, microseconds, nanoseconds và chuyển đổi đúng bằng Java `Instant`.
2. Hiểu **Unix epoch** và vì sao time zone không làm thay đổi epoch timestamp.
3. Phân biệt **wall-clock time** dùng để kiểm tra freshness với **monotonic elapsed time** dùng để đo duration.
4. Thiết kế format `X-Timestamp` rõ ràng: đơn vị, radix, dấu, chữ số, độ chính xác, giới hạn và ký tự hợp lệ.
5. Tính cửa sổ `now - 300 <= ts <= now + 300`, phân tích clock skew và rủi ro replay.
6. Gắn timestamp **nguyên dạng canonical** vào HMAC request, phát hiện việc thay timestamp/unit sau khi ký.
7. Viết ví dụ Java 17 với `Clock` có thể tiêm vào để kiểm thử ranh giới thời gian và chống replay.
8. Kiểm thử proxy/gateway, nonce phân tán, key rotation và authorization với đơn vị thời gian nhất quán.

## 2. Các đơn vị cơ bản và hệ số chuyển đổi

Một **Unix timestamp** biểu diễn thời lượng tính từ **1970-01-01T00:00:00Z**. Đơn vị *phải được nói rõ*: “epoch time” chưa đủ để biết số nguyên có đơn vị gì.

| Đơn vị | Ký hiệu | Bằng bao nhiêu giây? | Ví dụ ở 2024-01-01T00:00:00Z |
|---|---|---:|---:|
| Giây | `s`, seconds | 1 | `1704067200` |
| Mili giây | `ms`, milliseconds | `10^-3` | `1704067200000` |
| Micro giây | `µs`, microseconds | `10^-6` | `1704067200000000` |
| Nano giây | `ns`, nanoseconds | `10^-9` | `1704067200000000000` |

Các hệ thức đúng về **đơn vị vật lý**:

\[
1\,\text{s}=1000\,\text{ms}=10^6\,\mu\text{s}=10^9\,\text{ns}.
\]

Từ Unix seconds sang milliseconds:

\[
t_{\mathrm{ms}}=1000\,t_{\mathrm{s}}
\]

khi giá trị vẫn nằm trong miền số nguyên phù hợp và không có phần lẻ. Với thời điểm có phần mili giây, chia `t_ms` cho 1.000 và lấy **phần nguyên theo quy tắc floor đối với thời gian trước epoch**.

### 2.1. Độ dài 10 hoặc 13 chữ số chỉ là dấu hiệu thường gặp

Ở thời điểm hiện đại, một số Unix seconds thường có 10 chữ số, Unix milliseconds thường có 13 chữ số. Nhưng:

- Độ dài số thay đổi theo mốc thời gian và có thể tăng trong tương lai.
- Các timestamp trước epoch có dấu âm; timestamp gần epoch có thể rất ngắn.
- Attacker có thể cố ý dùng chuỗi 10 hoặc 13 chữ số nằm ngoài thời gian thực tế.
- Một số API dùng **epoch microseconds**, **ticks**, chuỗi ISO 8601 hoặc timestamp không tính từ 1970.

**Không viết:** `if (timestamp.length() == 13) timestamp /= 1000` ở HTTP verifier. Một giao thức an toàn phải khai báo **một đơn vị duy nhất trong contract/version**, chứ không đoán từ hình thức.

### 2.2. Chuyển đổi có thể làm mất độ chính xác

Ví dụ:

~~~text
2024-01-01T00:00:00.123456789Z

epoch seconds (integer): 1704067200
epoch milliseconds:      1704067200123
microseconds:            1704067200123456
nanoseconds:             1704067200123456789
~~~

Nếu contract dùng epoch seconds nguyên, phần .123456789 **không xuất hiện trong header**. Đây là lựa chọn độ phân giải; không phải lỗi của HMAC. Nếu hệ thống cần timestamp có độ phân giải milliseconds, hãy tạo **phiên bản hợp đồng khác** với định dạng, tính cửa sổ và ký bytes phù hợp.

Không cần đơn vị nano giây để chống replay một HTTP request. Thông thường timestamp giúp giới hạn **tuổi request**, còn **nonce duy nhất** mới chặn việc phát lại nhiều lần trong cửa sổ.

### 2.3. Kiểu số nguyên có giới hạn

Java `long` là số nguyên 64-bit có dấu. Epoch seconds phù hợp cho một phạm vi thời gian rất rộng, nhưng:

- Phép nhân `seconds * 1000` có thể overflow.
- Epoch **nanoseconds** dạng `long` có phạm vi hẹp hơn rất nhiều so với seconds; không nên dùng `long` nanoseconds một cách mù quáng cho mọi thời điểm.
- `Long.parseLong` ném lỗi với giá trị vượt phạm vi; đừng catch rồi gán 0 hoặc thời gian hiện tại.
- Đối với conversion cần tránh overflow, dùng `Math.multiplyExact` hoặc `Instant` cùng API chuyển đổi có kiểm soát.

Ví dụ:

~~~java
long epochSeconds = 1704067200L;
long epochMillis = Math.multiplyExact(epochSeconds, 1000L);
// => 1704067200000L

long secondsAgain = Math.floorDiv(epochMillis, 1000L);
// => 1704067200L
~~~

## 3. Unix epoch không phải múi giờ địa phương

Một Unix epoch timestamp đại diện cho một **instant** trên trục thời gian. Múi giờ ảnh hưởng **cách trình bày lịch**, không thay đổi instant.

~~~text
Instant:     2024-01-01T00:00:00Z
UTC:         2024-01-01 00:00:00
UTC+07:00:   2024-01-01 07:00:00
Unix sec:    1704067200    (KHÔNG đổi)
~~~

Nếu server ở Việt Nam và client ở một múi giờ khác, cả hai vẫn có thể gửi/kiểm tra **cùng số Unix epoch seconds**. Đừng cộng 7 giờ vào timestamp vì server ở UTC+7; đó là lỗi nhân đôi offset.

### 3.1. Các API Java dễ bị dùng sai

| Java API | Đơn vị/ý nghĩa | Có phù hợp tạo `X-Timestamp` seconds? |
|---|---|---|
| `Instant.now().getEpochSecond()` | Unix epoch **seconds** | **Có** |
| `Clock.systemUTC().instant().getEpochSecond()` | Unix epoch **seconds**, clock có thể tiêm test | **Có**, tiện kiểm thử |
| `System.currentTimeMillis()` | Unix epoch **milliseconds** | Không gửi nguyên số nếu contract yêu cầu seconds |
| `Instant.now().toEpochMilli()` | Unix epoch **milliseconds** | Không gửi nguyên số |
| `System.nanoTime()` | **Monotonic-ish elapsed ticks** có origin tùy ý | **Không dùng** làm Unix timestamp |
| `LocalDateTime.now()` | Ngày giờ local **không có offset/zone** | Không tự chuyển thành epoch khi thiếu zone |
| `ZonedDateTime` / `OffsetDateTime` | Ngày giờ có time zone/offset | Chỉ dùng khi chuyển **đúng sang Instant** |
| `Duration.ofSeconds(300)` | Độ dài thời gian, không phải mốc thời gian | Dùng mô tả cửa sổ, TTL |
| `Thread.sleep(300)` | Thời lượng chờ tính theo milliseconds | Không liên quan đơn vị header; không dùng để test boundary |

### 3.2. `System.nanoTime()` không biểu diễn thời điểm Unix

Một cách viết sai:

~~~java
String timestamp = Long.toString(System.nanoTime());
// SAI: giá trị nanoTime() không phải số nano giây kể từ Unix epoch.
~~~

`System.nanoTime()` phù hợp cho **đo elapsed duration** trong một tiến trình:

~~~java
long start = System.nanoTime();
// Thực hiện công việc...
long elapsedNanos = System.nanoTime() - start;
~~~

Origin của nó tùy hệ thống và không được quy định là epoch 1970. Không đưa `nanoTime` vào header dùng để so với `Instant.now().getEpochSecond()`, dù cùng từ “time”.

### 3.3. Instant và phần thời gian trước epoch

Với ngày trước 1970, cần đặc biệt cẩn trọng phép chia số nguyên:

~~~java
long ms = -1L; // 1969-12-31T23:59:59.999Z

System.out.println(ms / 1000L);              // 0 (trunc về 0)
System.out.println(Math.floorDiv(ms, 1000L)); // -1
System.out.println(
        Instant.ofEpochMilli(ms).getEpochSecond()); // -1
~~~

Timestamp âm **không được hợp đồng minh họa chấp nhận**, nhưng ví dụ cho thấy khi viết thư viện conversion tổng quát, `/1000` không hoàn toàn tương đương `Instant.ofEpochMilli` với giá trị âm.

## 4. Thống nhất format timestamp trong một signing contract

### 4.1. Hợp đồng minh họa `hmac-timeunit-v1`

| Thuộc tính | Quy tắc |
|---|---|
| Tên HTTP header | `X-Timestamp` |
| Đơn vị | **Unix epoch seconds**, không phải milliseconds |
| Kiểu | Số nguyên thập phân dương, **ASCII** |
| Cú pháp | `[1-9][0-9]{0,18}` và phải parse được bằng `Long.parseLong` |
| Dấu `+`/`-` | Không chấp nhận |
| Leading zero | Không chấp nhận; `01704067200` khác canonical `1704067200` |
| Số thập phân/fraction | Không chấp nhận `1704067200.123` |
| Whitespace/quotes | Không chấp nhận trong giá trị đã được parser HTTP chuẩn hóa theo contract |
| Giá trị milliseconds | **Không tự chia 1.000**; reject vì ngoài cửa sổ seconds |
| Header multiplicity | **Đúng một** `X-Timestamp`, reject duplicate/comma-joined |
| Cửa sổ freshness | `-300 <= signedSeconds - nowSeconds <= +300` (inclusive) |
| Đồng hồ | `Clock.systemUTC()` hoặc nguồn thời gian UTC đồng bộ tương đương |
| Chữ ký | Ký **chính chuỗi ASCII canonical đã nhận**, không thay đổi format giữa chừng |
| Nonce | 16 byte ngẫu nhiên CSPRNG, Base64URL no-padding, được ký |
| Mô hình chống replay | Nonce store dùng chung, reserve nguyên tử sau khi MAC đúng |
| Algorithm | HMAC-SHA-256, tag 32 byte, Base64URL không padding |

**Lưu ý:** regex cho tối đa 19 chữ số chỉ là kiểm tra **hình thức**. Một chuỗi vẫn có thể vượt phạm vi `long`; vì thế phải parse bằng `Long.parseLong` với xử lý overflow. Timestamp bị giới hạn bởi cả **format** lẫn **cửa sổ thời gian**.

### 4.2. Không sửa timestamp trước khi ký

Client và server phải dùng **cùng canonical text**. Nếu sender ký:

~~~text
X-Timestamp: 1704067200
canonical line: 1704067200
~~~

nhưng receiver tự chuyển từ seconds sang milliseconds:

~~~text
canonical line: 1704067200000
~~~

thì chữ ký sẽ thất bại. Ngược lại, nếu verifier “cố giúp” bằng cách đổi định dạng mà không có hợp đồng, client có thể gửi nhiều representation của một thời điểm, khiến logging/nonce/error handling hiểu khác nhau.

Quy tắc đơn giản:

1. Kiểm tra format `X-Timestamp` **trước** khi parse.
2. Parse thành `long signedSeconds` **chỉ để kiểm tra freshness**.
3. Dùng **nguyên chuỗi đã được xác nhận canonical** làm dòng timestamp trong canonical request.
4. Đưa format, đơn vị và cửa sổ thời gian vào version/protocol documentation.
5. Nếu đổi từ seconds sang milliseconds, tạo `hmac-timeunit-v2` hoặc migration protocol rõ ràng, **không đoán ngầm**.

### 4.3. Timestamp nằm ở đâu trong canonical request?

Bài này chọn canonical request 10 dòng:

| Dòng | Giá trị | Quy tắc |
|---|---|---|
| 1 | `hmac-timeunit-v1` | Version literal |
| 2 | `payments-api-production` | Audience literal được ràng buộc |
| 3 | `POST` | Method chính xác |
| 4 | `/v1/payments?mode=preview` | Raw origin-form target theo route grammar |
| 5 | `application/json` | Content-Type đơn, canonical lowercase |
| 6 | `merchant-17` | Client ID đã ký |
| 7 | `key-2026-11` | Key ID đã ký |
| 8 | `1704067200` | **Epoch seconds** canonical; trong ví dụ thời điểm cố định |
| 9 | `b75sZVQmhTBcfnX-bNbGqw` | Nonce Base64URL |
| 10 | `<sha256-body-hex>` | SHA-256 raw body bytes, hex chữ thường |

Dùng **LF** (`\n`) giữa các dòng, **không thêm LF cuối**, mã hóa UTF-8; HMAC được tính trên các bytes này. Signature là Base64URL no-padding của đầy đủ 32-byte tag, đưa trong `X-Signature`; **không** cho signature vào chuỗi đang được ký.

Ví dụ canonical text:

~~~text
hmac-timeunit-v1
payments-api-production
POST
/v1/payments?mode=preview
application/json
merchant-17
key-2026-11
1704067200
b75sZVQmhTBcfnX-bNbGqw
<sha256-hex-of-raw-request-body>
~~~

Giá trị SHA-256 cuối là **placeholder**, không được copy thẳng vào HMAC. `1704067200` là fixture mốc 2024 dùng để **minh họa format**, không phải timestamp còn hợp lệ theo cửa sổ ±300 giây ở mọi thời điểm chạy. Trong chương trình Java, sender sẽ lấy seconds từ `Clock` tại thời điểm test để có request hợp lệ.

### 4.4. Timestamp không phải dữ liệu tin cậy nếu chưa verify

Client có thể gửi bất kỳ `X-Timestamp` nào. Trước khi xác minh HMAC, timestamp chỉ là **claim của client**, không phải sự thật được server công nhận.

- **Format hợp lệ** chưa chứng minh client sở hữu secret.
- **Nằm trong cửa sổ** chưa chứng minh HMAC hợp lệ.
- **HMAC hợp lệ** chưa chứng minh request chưa bị replay.
- **Không replay** chưa chứng minh principal có quyền trên tài nguyên.
- **Content-Type/method/URI/body** phải được ký đúng hợp đồng để không đổi hành vi sau xác thực.

## 5. Kiểm tra độ lệch thời gian và chống clock skew

Gọi `t` là timestamp seconds được client ký và `n` là seconds theo đồng hồ server. Với cửa sổ ±300 seconds:

\[
n - 300 \le t \le n + 300.
\]

Hoặc tương đương:

\[
-300 \le t-n \le +300.
\]

### 5.1. Inclusive boundaries

| `t - n` (seconds) | Expected |
|---:|---|
| `-301` | Reject: quá cũ |
| `-300` | **Accept về thời gian**: đúng biên dưới |
| `-1` | Accept về thời gian |
| `0` | Accept về thời gian |
| `+1` | Accept về thời gian |
| `+300` | **Accept về thời gian**: đúng biên trên |
| `+301` | Reject: tương lai quá xa |

“Accept về thời gian” **không đồng nghĩa request được chấp nhận**: vẫn phải verify HMAC, kiểm tra nonce và authorization.

### 5.2. Tại sao cho phép timestamp ở tương lai?

Client và server có thể lệch đồng hồ vài giây do đồng bộ thời gian, thời gian gửi request hoặc chậm mạng. Một cửa sổ cho phép một ít **future skew** giảm false reject. Tuy nhiên, chấp nhận tương lai **quá xa** sẽ mở rộng khoảng thời gian mà một request hợp lệ có thể bị phát lại nếu nonce store không hoạt động.

Nếu hệ thống cần strict hơn, có thể chọn bất đối xứng, ví dụ chỉ cho tương lai +30 giây, quá khứ 300 giây. **Hợp đồng của bài dùng đối xứng ±300** để dễ tính; con số 300 là cấu hình minh họa, không phải chuẩn RFC bắt buộc cho mọi HMAC API.

### 5.3. Tính offset an toàn

Một cách viết dễ overflow:

~~~java
long difference = Math.abs(clientSeconds - serverSeconds);
if (difference <= 300) accept();
~~~

Với số `long` cực trị, phép trừ có thể overflow; `Math.abs(Long.MIN_VALUE)` vẫn âm. Một phương án minh họa là dùng `Math.subtractExact` rồi so khoảng:

~~~java
boolean inWindow(long signedSeconds, long nowSeconds) {
    try {
        long delta = Math.subtractExact(signedSeconds, nowSeconds);
        return delta >= -300L && delta <= 300L;
    } catch (ArithmeticException overflow) {
        return false;
    }
}
~~~

Trong API thật, nên parse và validate timestamp **một lần** thành kiểu có ràng buộc, dùng `Clock` nhất quán. Không “sửa” timestamp ở phía server bằng cách thay claim client bằng `nowSeconds`: điều đó phá khả năng đối chiếu đúng thông điệp đã được ký.

### 5.4. Đồng bộ hóa đồng hồ

Một request có HMAC đúng vẫn có thể bị 401 nếu đồng hồ client chậm/nhanh quá mức. Cần:

- Cấu hình NTP hoặc dịch vụ đồng bộ thời gian tin cậy ở client và server.
- Dùng UTC epoch seconds, không dùng local timezone để cộng/trừ offset.
- Cân nhắc vài giây network delay, load balancer và queueing.
- Dùng metric **clock_skew_seconds** ở môi trường có thể log an toàn, tránh log secret/body nhạy cảm.
- Nếu thấy nhiều request lệch đồng hồ, **sửa đồng hồ** thay vì mở cửa sổ từ 5 phút thành nhiều giờ mà không xem xét replay risk.
- Test tình huống server wall-clock bị điều chỉnh sau NTP step hoặc leap-second handling theo hệ thống OS/JVM thực tế.

`Clock.systemUTC()` là **wall-clock clock**; nó có thể nhảy khi OS đồng bộ lại thời gian. Dùng `System.nanoTime()` đo latency/timeout nội bộ, nhưng không chuyển nanoTime thành epoch seconds.

## 6. Timestamp và nonce: hai cơ chế khác nhau

Timestamp làm giới hạn khoảng thời gian chấp nhận một message đã ký, nhưng **không ngăn người khác gửi lại cùng message trong cửa sổ**.

~~~text
Request A:
   timestamp = t
   nonce = N
   signature = HMAC(K, canonical(A))
   
Request A (replay):
   timestamp = t
   nonce = N
   signature = HMAC(K, canonical(A))

Timestamp vẫn hợp lệ, HMAC vẫn khớp.
Chính nonce store phải phát hiện lần sử dụng lại N.
~~~

### 6.1. Nonce store và TTL tính theo đơn vị nào?

Đối với cửa sổ `t - 300 <= now <= t + 300`, một timestamp có thể được **chấp nhận sớm nhất** tại `now = t - 300` và vẫn còn hợp lệ tới `now = t + 300`: tổng cộng khoảng **600 giây**.

Nếu nonce được ghi ngay ở đầu cửa sổ với TTL chỉ **300 giây**, bản ghi có thể hết hạn khi timestamp vẫn còn được chấp nhận, dẫn đến replay qua nonce đã “quên”.

Chính sách minh họa:

~~~text
timestampUnit = SECONDS
clockSkewWindow = ±300 seconds
nonceKey = (audience, clientId, keyId, nonce)
atomic reserve only after successful MAC
nonce TTL = at least 600 seconds + operational margin
example TTL = 660 seconds
~~~

**Không nhầm đơn vị TTL của Redis hoặc cache API.** Chẳng hạn Redis `EX 660` biểu diễn **seconds**, còn `PX 660000` biểu diễn **milliseconds**. `EX 660000` sẽ giữ nonce lâu hơn rất nhiều; `PX 660` chỉ giữ khoảng 0,66 giây, quá ngắn. Các SDK có API nhập `Duration` có thể giảm nhầm đơn vị, nhưng vẫn phải đọc rõ quy ước.

Nonce store cần dùng thao tác **insert-if-absent nguyên tử** chia sẻ giữa các verifier node, ví dụ primitive Redis tương đương `SET nonceKey 1 NX EX 660`. Không dùng “GET rồi SET” vì hai request đồng thời có thể cùng vượt qua.

**Chỉ reserve nonce sau khi MAC đúng.** Nếu reserve nonce trước MAC, attacker gửi chữ ký giả cùng nonce của một request thật có thể làm server chiếm nonce và từ chối request hợp lệ. Nếu anti-replay là bắt buộc mà store unavailable, **fail closed**.

### 6.2. Timestamp không phải idempotency key

Ngay cả khi nonce mới và HMAC hợp lệ, client có thể gửi **hai request có nghiệp vụ giống nhau**:

~~~text
POST /v1/payments
Request 1: timestamp=t1, nonce=N1, HMAC=valid
Request 2: timestamp=t2, nonce=N2, HMAC=valid
~~~

Nonce store không chặn request 2 vì **nonce khác**. Với chuyển tiền hoặc tạo đơn, cần **idempotency** ở tầng nghiệp vụ, thường dựa trên một idempotency key do client gửi được ràng buộc vào dữ liệu ký. Timestamp/nonce/HMAC không tự bảo đảm “giao dịch chỉ thực hiện một lần”.

## 7. Java 17: ký timestamp seconds, kiểm tra freshness và replay

Ví dụ dưới đây **chạy với JDK 17+**, không cần Spring hoặc thư viện ngoài. Mã tập trung vào những điều liên quan trực tiếp đến **đơn vị thời gian**:

- Dùng `Clock.fixed` cho test để không phụ thuộc thời gian thực và không phải `Thread.sleep`.
- Chỉ nhận timestamp là **epoch seconds** ASCII canonical; reject dấu cộng/âm, leading zero, decimal, millisecond heuristic và overflow.
- Cố định canonical request gồm version, audience, method, raw target, Content-Type, client/key IDs, timestamp, nonce và SHA-256 body digest.
- Tính HMAC-SHA-256 đầy đủ 32 byte, decode Base64URL no-padding đúng 43 ký tự, so raw tag bằng `MessageDigest.isEqual`.
- Kiểm tra ±300 giây với `Math.subtractExact` trước khi chấp nhận MAC.
- Minh họa atomic nonce reservation bằng `ConcurrentHashMap.compute` **trong một JVM**; production cần kho phân tán và eviction/TTL thực sự.

### 7.1. Mã Java hoàn chỉnh

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Locale;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class TimestampUnitHmacDemo {
    private static final String ALGORITHM = "HmacSHA256";
    private static final String VERSION = "hmac-timeunit-v1";
    private static final String AUDIENCE = "payments-api-production";
    private static final long WINDOW_SECONDS = 300L;
    private static final long NONCE_TTL_SECONDS = 660L;

    private TimestampUnitHmacDemo() {}

    public record Request(
            String method, String rawTarget, String contentType,
            String clientId, String keyId, String timestamp,
            String nonce, byte[] rawBody) {
        public Request {
            if (rawBody == null) {
                throw new IllegalArgumentException("Missing raw body");
            }
            rawBody = rawBody.clone();
        }
        @Override
        public byte[] rawBody() {
            return rawBody.clone();
        }
    }

    // Không tự nhận diện milliseconds theo số chữ số.
    public static long parseEpochSeconds(String text) {
        if (text == null
                || !text.matches("[1-9][0-9]{0,18}")) {
            throw new IllegalArgumentException(
                    "Timestamp must be canonical epoch seconds");
        }
        try {
            return Long.parseLong(text);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "Timestamp overflows signed long", ex);
        }
    }

    // Tính delta mà không dùng abs(Long.MIN_VALUE).
    public static boolean timestampInWindow(
            String signedText, long nowSeconds) {
        try {
            long seconds = parseEpochSeconds(signedText);
            long delta = Math.subtractExact(seconds, nowSeconds);
            return delta >= -WINDOW_SECONDS
                    && delta <= WINDOW_SECONDS;
        } catch (IllegalArgumentException | ArithmeticException ex) {
            return false;
        }
    }

    private static String asciiField(String value, int max) {
        if (value == null || value.isEmpty()
                || value.length() > max
                || value.chars().anyMatch(c -> c < 0x21 || c > 0x7E)) {
            throw new IllegalArgumentException("Invalid signed field");
        }
        return value;
    }

    private static String canonicalContentType(String input) {
        if (input == null || input.length() > 128
                || input.chars().anyMatch(
                        c -> (c < 0x20 && c != '\t') || c > 0x7E)) {
            throw new IllegalArgumentException("Bad Content-Type");
        }
        String value = input.trim().toLowerCase(Locale.ROOT);
        if (!"application/json".equals(value)) {
            throw new IllegalArgumentException("Unsupported media type");
        }
        return value;
    }

    private static String canonicalNonce(String input) {
        // 16 random bytes => 22 ký tự Base64URL không padding.
        if (input == null || !input.matches("[A-Za-z0-9_-]{22}")) {
            throw new IllegalArgumentException("Invalid nonce encoding");
        }
        final byte[] nonceBytes;
        try {
            nonceBytes = Base64.getUrlDecoder().decode(input);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException("Invalid nonce", ex);
        }
        if (nonceBytes.length != 16
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(nonceBytes).equals(input)) {
            throw new IllegalArgumentException("Non-canonical nonce");
        }
        return input;
    }

    public static byte[] canonicalBytes(Request request)
            throws GeneralSecurityException {
        if (request == null || !"POST".equals(request.method())) {
            throw new IllegalArgumentException("Only POST is allowed");
        }
        String target = asciiField(request.rawTarget(), 2048);
        if (!target.matches(
                "/v1/payments\\?mode=(?:preview|commit)")) {
            throw new IllegalArgumentException("Invalid raw target");
        }
        String client = asciiField(request.clientId(), 64);
        String keyId = asciiField(request.keyId(), 64);
        if (!client.matches("[A-Za-z0-9_-]+")
                || !keyId.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid identity");
        }
        String timestamp = asciiField(request.timestamp(), 19);
        parseEpochSeconds(timestamp); // Không đổi original text.
        String nonce = canonicalNonce(request.nonce());

        byte[] body = request.rawBody();
        if (body.length > 64 * 1024) {
            throw new IllegalArgumentException("Body too large");
        }
        String bodyHex = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(body));
        String canonical = String.join("\n",
                VERSION,
                AUDIENCE,
                request.method(),
                target,
                canonicalContentType(request.contentType()),
                client,
                keyId,
                timestamp,
                nonce,
                bodyHex);
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] hmac(byte[] secret, byte[] data)
            throws GeneralSecurityException {
        if (secret == null || secret.length != 32 || data == null) {
            throw new IllegalArgumentException("Bad HMAC input");
        }
        Mac engine = Mac.getInstance(ALGORITHM);
        engine.init(new SecretKeySpec(secret, ALGORITHM));
        return engine.doFinal(data);
    }

    public static String sign(Request request, byte[] secret)
            throws GeneralSecurityException {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(hmac(secret, canonicalBytes(request)));
    }

    public static byte[] decodeSignatureStrict(String signature) {
        if (signature == null
                || !signature.matches("[A-Za-z0-9_-]{43}")) {
            throw new IllegalArgumentException(
                    "Expected full HMAC-SHA256 Base64URL signature");
        }
        final byte[] decoded;
        try {
            decoded = Base64.getUrlDecoder().decode(signature);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException("Bad signature", ex);
        }
        if (decoded.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(decoded).equals(signature)) {
            throw new IllegalArgumentException("Non-canonical tag");
        }
        return decoded;
    }

    public static boolean verifyMac(
            Request request, byte[] secret, String signature)
            throws GeneralSecurityException {
        final byte[] provided;
        try {
            provided = decodeSignatureStrict(signature);
        } catch (IllegalArgumentException badFormat) {
            return false;
        }
        final byte[] expected;
        try {
            expected = hmac(secret, canonicalBytes(request));
        } catch (IllegalArgumentException invalidRequest) {
            return false;
        }
        return MessageDigest.isEqual(expected, provided);
    }

    // Chỉ minh họa trong 1 JVM, KHÔNG có cleanup background.
    public static final class LocalNonceStore {
        private final ConcurrentHashMap<String, Long> expiries =
                new ConcurrentHashMap<>();

        public boolean reserve(
                String scope, long nowSeconds, long ttlSeconds) {
            AtomicBoolean added = new AtomicBoolean(false);
            expiries.compute(scope, (key, expiry) -> {
                if (expiry != null && expiry > nowSeconds) {
                    return expiry;
                }
                added.set(true);
                return Math.addExact(nowSeconds, ttlSeconds);
            });
            return added.get();
        }
    }

    // Demo: caller đã lookup và kiểm trạng thái khóa chính xác.
    // Authorization được thực hiện SAU khi xác thực hoàn tất.
    public static boolean verifyRequest(
            Request request, byte[] secret, String signature,
            Clock clock, LocalNonceStore store)
            throws GeneralSecurityException {
        if (request == null || clock == null || store == null) {
            return false;
        }
        long now = clock.instant().getEpochSecond();
        if (!timestampInWindow(request.timestamp(), now)) {
            return false;
        }
        if (!verifyMac(request, secret, signature)) {
            return false;
        }
        String scope = AUDIENCE + "|" + request.clientId()
                + "|" + request.keyId() + "|" + request.nonce();
        return store.reserve(scope, now, NONCE_TTL_SECONDS);
    }

    private static void require(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    private static void expectInvalid(Runnable check) {
        boolean rejected = false;
        try {
            check.run();
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        require(rejected, "Expected malformed timestamp rejection");
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        // Fixed clock => test không phụ thuộc thời gian hiện tại.
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-28T00:00:00Z"),
                ZoneOffset.UTC);
        long now = clock.instant().getEpochSecond();

        require(Instant.parse("2024-01-01T00:00:00Z")
                .getEpochSecond() == 1704067200L,
                "Seconds fixture");
        require(Instant.ofEpochMilli(1704067200000L)
                .getEpochSecond() == 1704067200L,
                "Millis fixture");
        require(Instant.ofEpochMilli(-1L)
                .getEpochSecond() == -1L,
                "Negative milliseconds floor semantics");

        require(timestampInWindow(
                Long.toString(now - 300), now), "Lower edge");
        require(timestampInWindow(
                Long.toString(now + 300), now), "Upper edge");
        require(timestampInWindow(
                Long.toString(now), now), "Current instant");
        require(!timestampInWindow(
                Long.toString(now - 301), now), "Too old");
        require(!timestampInWindow(
                Long.toString(now + 301), now), "Too far future");

        String millis = Long.toString(
                Math.multiplyExact(now, 1000L));
        require(!timestampInWindow(millis, now),
                "Milliseconds must not be accepted as seconds");
        expectInvalid(() -> parseEpochSeconds("0" + now));
        expectInvalid(() -> parseEpochSeconds("+" + now));
        expectInvalid(() -> parseEpochSeconds(now + ".123"));
        expectInvalid(() -> parseEpochSeconds("-1"));
        expectInvalid(() -> parseEpochSeconds("1704067200 "));
        expectInvalid(() -> parseEpochSeconds(
                "9999999999999999999"));

        byte[] secret = new byte[32];
        new SecureRandom().nextBytes(secret); // Demo only.
        byte[] nonceRaw = new byte[16];
        new SecureRandom().nextBytes(nonceRaw);
        String nonce = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(nonceRaw);

        Request request = new Request(
                "POST", "/v1/payments?mode=preview",
                "application/json", "merchant-17", "key-2026-11",
                Long.toString(now), nonce,
                "{\"orderId\":\"o-123\",\"amount\":150000}"
                        .getBytes(StandardCharsets.UTF_8));
        String signature = sign(request, secret);
        require(verifyMac(request, secret, signature), "Valid MAC");

        LocalNonceStore store = new LocalNonceStore();
        byte[] changedTag = decodeSignatureStrict(signature);
        changedTag[0] ^= 1;
        String forged = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(changedTag);
        require(!verifyRequest(
                request, secret, forged, clock, store),
                "Invalid MAC must not reserve nonce");
        require(verifyRequest(
                request, secret, signature, clock, store),
                "Valid request accepted once");
        require(!verifyRequest(
                request, secret, signature, clock, store),
                "Replay is blocked");

        Request changedTimestamp = new Request(
                request.method(), request.rawTarget(),
                request.contentType(), request.clientId(),
                request.keyId(), Long.toString(now + 1),
                request.nonce(), request.rawBody());
        require(!verifyMac(changedTimestamp, secret, signature),
                "Timestamp text must be signed");

        Request changedTarget = new Request(
                request.method(), "/v1/payments?mode=commit",
                request.contentType(), request.clientId(),
                request.keyId(), request.timestamp(),
                request.nonce(), request.rawBody());
        require(!verifyMac(changedTarget, secret, signature),
                "Target must be signed");

        Request millisRequest = new Request(
                request.method(), request.rawTarget(),
                request.contentType(), request.clientId(),
                request.keyId(), millis, request.nonce(),
                request.rawBody());
        String signedMillis = sign(millisRequest, secret);
        require(verifyMac(millisRequest, secret, signedMillis),
                "Even wrong-unit text can have a correct MAC");
        require(!verifyRequest(
                millisRequest, secret, signedMillis,
                clock, new LocalNonceStore()),
                "Wrong-unit request fails freshness");

        require(!verifyMac(request, new byte[32], signature),
                "Wrong secret fails");
        System.out.println("PASS HMAC timestamp unit/window/replay checks");
    }
}
~~~

Lưu mã vào `TimestampUnitHmacDemo.java` và chạy trên JDK 17+:

~~~bash
javac TimestampUnitHmacDemo.java
java TimestampUnitHmacDemo
~~~

Kết quả mong đợi:

~~~text
PASS HMAC timestamp unit/window/replay checks
~~~

### 7.2. Phân biệt MAC đúng và timestamp đúng

Trong test, `millisRequest` dùng timestamp **milliseconds** nhưng vẫn được ký bằng secret thật, nên `verifyMac` có thể trả `true`. `verifyRequest` vẫn trả `false` vì **giá trị đó nằm ngoài cửa sổ epoch seconds**.

~~~text
MAC đúng          -> canonical bytes được ký đúng secret.
Timestamp hợp lệ  -> đúng định dạng, đúng đơn vị, trong cửa sổ.
Nonce mới         -> chưa bị dùng lại theo policy.
Authorization     -> principal có quyền thực hiện hành động.
~~~

Một client sở hữu secret vẫn có thể gửi request sai thời gian. Không được bỏ kiểm tra freshness hoặc tự chia milliseconds cho 1000 chỉ vì HMAC hợp lệ.

### 7.3. Giới hạn của mã ví dụ

- Chương trình chỉ là **demo core**, chưa có HTTP server/filter, signed header multiplicity, khâu lấy raw path/body thực từ mạng hoặc phân quyền.
- `verifyRequest` nhận secret có sẵn; production phải lookup `(clientId, keyId, audience)`, kiểm tra trạng thái khóa và xử lý key rotation/revocation.
- `LocalNonceStore` chỉ có atomicity trong một JVM; **không** phân tán, không tự giải phóng entries hết hạn, không xử lý downtime. Cần store chia sẻ với TTL thật để triển khai.
- `Clock.fixed` chỉ đảm bảo test deterministic; không chứng minh đồng hồ production đã đồng bộ.
- Route grammar/Content-Type được giới hạn để tập trung vào timestamp. Hợp đồng thật phải quy định cách canonical hóa method, URI, headers và body đồng nhất với gateway.
- `MessageDigest.isEqual` chỉ bảo vệ phép so raw tags, không biến toàn bộ pipeline thành constant-time.

## 8. Tạo và chuyển đổi epoch timestamp trong SDK

### 8.1. Java sender tạo timestamp đúng đơn vị

~~~java
Clock clock = Clock.systemUTC();
String signedTimestamp = Long.toString(
        clock.instant().getEpochSecond());

// Phải ký CHÍNH chuỗi signedTimestamp này,
// rồi đưa cùng chuỗi vào X-Timestamp.
~~~

Không dùng nguyên `System.currentTimeMillis()` làm epoch seconds:

~~~java
String wrongMilliseconds =
        Long.toString(System.currentTimeMillis());
// Sai đơn vị: milliseconds, không phải seconds.

String wrongNanoTime =
        Long.toString(System.nanoTime());
// Sai gốc thời gian: nanoTime không phải Unix epoch.

String wrongLocalText =
        java.time.LocalDateTime.now().toString();
// Sai format: local wall time, không phải epoch seconds.
~~~

Với `Instant` có phần nano giây, `getEpochSecond()` biểu diễn số nguyên seconds được **floor tới giây gần nhất**. Tránh tự dùng `Math.round(instant.toEpochMilli()/1000.0)`: đó là **làm tròn**, có thể chuyển timestamp sang giây tiếp theo và thay chuỗi được ký.

### 8.2. Khi tích hợp một API dùng milliseconds

Một bên thứ ba có thể thật sự quy định timestamp bằng epoch milliseconds. Khi ấy, chuyển đổi có kiểm soát ở **ranh giới giao thức**:

~~~java
long signedMillisFromAnotherProtocol = 1704067200123L;
Instant instant = Instant.ofEpochMilli(
        signedMillisFromAnotherProtocol);
long secondsForOurProtocol = instant.getEpochSecond();
// => 1704067200
~~~

Không lấy header milliseconds từ client và tự biến thành seconds **trước khi xác minh chữ ký của giao thức milliseconds**. Điều đó làm thay đổi bytes đã ký. Nếu phải nhận cả hai định dạng, dùng **contract version rõ ràng** hoặc gateway đáng tin xác minh giao thức gốc rồi mới tạo request nội bộ theo giao thức đích.

### 8.3. Một số API và đơn vị phổ biến

| Nền tảng/API | Đơn vị điển hình | Chú ý |
|---|---|---|
| Java `Instant.getEpochSecond()` | Seconds | Phù hợp `hmac-timeunit-v1` |
| Java `Instant.toEpochMilli()` | Milliseconds | Không gửi nguyên vào contract seconds |
| Java `System.currentTimeMillis()` | Milliseconds | Không cùng `System.nanoTime()` |
| Java `System.nanoTime()` | Elapsed nanoseconds, origin tùy ý | Không dùng làm epoch |
| JavaScript `Date.now()` | Epoch milliseconds | Dùng `Math.floor(Date.now()/1000)` nếu cần seconds |
| Go `time.Now().Unix()` | Epoch seconds | Đúng đơn vị hợp đồng |
| Go `time.Now().UnixMilli()` | Epoch milliseconds | Khác `Unix()` |
| Python `time.time()` | Epoch seconds dạng float | Cần chuyển thành integer theo contract |
| Python `time.time_ns()` | Epoch nanoseconds integer | Không gửi nguyên nếu cần seconds |
| Redis `EX 660` | TTL seconds | Không cùng `PX 660` |
| Redis `PX 660000` | TTL milliseconds | Tương đương EX 660 theo đơn vị |

Ví dụ JavaScript:

~~~javascript
const seconds = Math.floor(Date.now() / 1000);
const signedTimestamp = String(seconds);
// Dùng chính signedTimestamp ở header và canonical request.
~~~

Ví dụ Go:

~~~go
timestamp := strconv.FormatInt(time.Now().Unix(), 10)
~~~

Ví dụ Python:

~~~python
import time
timestamp = str(time.time_ns() // 1_000_000_000)
~~~

Đây là **minh họa API/đơn vị**, không tự giải quyết mọi sai lệch clock, thay đổi múi giờ hoặc yêu cầu atomic nonce store của hệ thống thực.

### 8.4. Header Date không phải epoch seconds

HTTP còn có những trường ngày tháng dạng văn bản:

~~~http
Date: Sat, 28 Nov 2026 00:00:00 GMT
~~~

Nó **không có cùng định dạng** với `X-Timestamp: 1795824000`. Một contract có thể chọn ký header `Date`, nhưng phải quy định parse/format RFC date và canonicalization riêng; không chuyển sang epoch seconds một cách ngầm định trong receiver.

## 9. Gateway/proxy và những bất đồng về đơn vị thời gian

~~~mermaid
sequenceDiagram
    participant S as Client SDK
    participant G as Gateway / Reverse Proxy
    participant V as HMAC Verifier
    participant K as Key Store
    participant N as Shared Nonce Store
    participant B as Business Handler
    S->>S: Lấy Unix seconds và nonce, ký canonical request
    S->>G: POST + X-Timestamp seconds + HMAC
    G->>V: Signed headers, method, target, body
    V->>V: Check timestamp format, epoch seconds và ±300s
    V->>K: Lookup clientId + keyId + audience
    K-->>V: Key hợp lệ để verify
    V->>V: HMAC-SHA-256 và so full tag 32 bytes
    V->>N: Reserve nonce atomically sau khi MAC đúng
    N-->>V: Nonce mới
    V->>B: Authenticated principal + request
    B->>B: Authorization trên action/resource/tenant
~~~

### 9.1. Các lỗi cần phát hiện qua gateway

| Thay đổi của gateway/SDK | Rủi ro | Hướng kiểm tra |
|---|---|---|
| Chuyển `1704067200000` thành `1704067200` | Thay đổi bytes header đã ký, dù cùng instant | Không tự rewrite signed header trước verify |
| Tự tạo `X-Timestamp` khi client thiếu | Client không ký claim đúng quy định | Reject hoặc dùng contract edge signer riêng |
| Bỏ dấu cộng/leading zeros cho “đẹp” | Biểu diễn canonical không còn gốc | Reject format sai ngay tại điểm được chọn |
| Gom hai `X-Timestamp` bằng comma | Verifier chọn first/last có thể khác proxy | Reject duplicate/comma-list |
| Đổi seconds thành ISO 8601 | Thay signing bytes và cú pháp | Dùng giao thức/version rõ ràng |
| Gateway queue quá lâu | Request có thể quá cũ khi đến verifier | Thiết kế timeout và monitoring skew, không bỏ kiểm tra |
| Các verifier lệch clock | Node A accept, node B reject | Đồng bộ clock và test multi-node |
| HTTP/2 `:path` → HTTP/1.1 URI | Signed target có thể thay | Test canonical bytes tại đúng verifier |
| Client retry với cùng nonce | Anti-replay reject theo contract | Tạo timestamp/nonce và ký lại; thêm idempotency |
| Gateway cached authentication result | Có thể bỏ qua freshness/nonce | Không cho cache bypass request authentication |
| Gateway tự đổi `X-Key-Id` | Dẫn tới secret khác | Bind key ID trong canonical bytes, không tin metadata giả |

Không tin `X-Original-Timestamp`, `X-Verified-Client` hoặc `X-Original-URI` do client Internet tự đặt. Nếu edge xác minh HMAC rồi chuyển principal, gateway phải xóa headers giả mạo do client gửi và bảo vệ kênh nội bộ đến backend.

### 9.2. Vị trí verify phải được định nghĩa

**Verify tại edge:** edge còn thấy headers/target/body ban đầu, kiểm tra chữ ký và freshness, reserve nonce, rồi chuyển principal đã xác thực qua kênh đáng tin. Backend **vẫn làm authorization** đối với tài nguyên.

**Verify tại backend:** proxy phải giữ các signed fields không thay đổi theo contract; clock của backend là cơ sở kiểm tra freshness. Nếu có nhiều verifier nodes, tất cả phải cùng chính sách seconds, cùng nonce store và clock được đồng bộ.

**Không được** để gateway kiểm timestamp bằng milliseconds, backend ký timestamp dưới dạng seconds mà không có bước chuyển giao thức rõ ràng.

## 10. Key rotation có deadline riêng, không lấy thời gian từ client

`X-Key-Id` chọn secret tương ứng của principal/audience. Ngoài timestamp của request, key store còn có **mốc hiệu lực, mốc chuyển tiếp, mốc revoke** do server quản lý.

| Trạng thái khóa | Ý nghĩa | Kết quả |
|---|---|---|
| `ACTIVE` | Được phép xác minh | Có thể tính HMAC |
| `VERIFY_ONLY` | Key cũ trong cửa sổ overlap đã phê duyệt | Chỉ verify trước deadline |
| `REVOKED` | Key bị thu hồi | Reject dù HMAC/time hợp lệ |
| Key không thuộc client/audience | Sai secret/principal | Reject, không thử tenant khác |
| Key không tồn tại | Không có record được cấp | Reject, không dùng fallback secret |

Phân biệt:

~~~text
requestTimestamp = client claim được ký, không phải server time.
serverNow        = wall-clock tin cậy cho freshness/expiry.
keyDeadline      = policy do server quản lý.
nonceExpiry      = TTL do server/quản lý datastore tạo ra.
~~~

Không chấp nhận key đã `REVOKED` chỉ vì client ký timestamp vào thời điểm trước khi key bị revoke. Đó là **đánh tráo nguồn sự thật**: client không được điều khiển chính sách key rotation.

### 10.1. Sai lầm khi key deadline lưu milliseconds

~~~java
long keyDeadlineMillis = 1795824000000L;
long nowSeconds = clock.instant().getEpochSecond();

// SAI: so hai con số với đơn vị khác nhau.
boolean validWrong = nowSeconds < keyDeadlineMillis;

// ĐÚNG: dùng Instant để so hai thời điểm thật.
boolean valid = clock.instant()
        .isBefore(Instant.ofEpochMilli(keyDeadlineMillis));
~~~

Đặt tên biến có hậu tố `Seconds`, `Millis`, `Duration` để tránh nhầm và ưu tiên dùng `Instant`/`Duration` ở tầng domain. Tránh việc code coi key deadline và nonce TTL là cùng một timestamp mà không có đơn vị.

## 11. Authentication khác authorization ngay cả khi timestamp đúng

Ví dụ merchant 17 có shared secret đúng, ký request mới:

~~~http
POST /v1/payments?mode=commit HTTP/1.1
X-Client-Id: merchant-17
X-Key-Id: key-2026-11
X-Timestamp: <valid-epoch-seconds>
X-Nonce: <fresh-nonce>
X-Signature: <valid-hmac>
~~~

Body yêu cầu thanh toán từ tài khoản thuộc merchant 42:

~~~text
Authentication:
  timestamp unit  = seconds, valid
  freshness       = within window
  HMAC            = valid
  nonce           = fresh
  principal       = merchant-17

Authorization:
  action          = payments:commit
  resourceOwner   = merchant-42
  principal       = merchant-17
  decision        = DENY
~~~

Chữ ký và timestamp đúng chứng minh request được ký bằng đúng secret và không cũ theo policy, nhưng **không cấp quyền** lên mọi tài nguyên. Kiểm tra action, resource, tenant và ownership phải dựa trên **tài nguyên thực sự router/handler xử lý**, tránh Broken Object Level Authorization (BOLA).

## 12. Ma trận kiểm thử đơn vị và thời gian

### 12.1. Parser, format và conversion

| Đầu vào / phép chuyển | Expected |
|---|---|
| `1704067200` trong contract seconds | Parse đúng epoch seconds cho 2024-01-01T00:00:00Z |
| `1704067200000` ở cùng clock seconds | Ngoài freshness window; không đoán đơn vị |
| `1704067200.123` | Reject: fractional không hợp lệ |
| `01704067200` | Reject: leading zero |
| `+1704067200` | Reject: dấu cộng |
| `-1` | Reject theo hợp đồng positive-only |
| `1.7040672e9` | Reject: scientific notation |
| `9999999999999999999` | Reject: vượt `Long.MAX_VALUE` |
| 20 chữ số | Reject: ngoài grammar |
| Unicode digits hoặc whitespace | Reject: không phải ASCII canonical |
| Không có `X-Timestamp` | Reject |
| Hai `X-Timestamp` | Reject tại HTTP adapter |
| Milliseconds `-1` chuyển qua `Instant.ofEpochMilli` | `getEpochSecond()==-1`; tránh chia nguyên truncate về 0 |
| `System.nanoTime()` đưa làm header | Sai epoch và bị reject khi không nằm trong window |

### 12.2. Cửa sổ ±300 giây với một fixed clock

Giả sử `now = 2000000000`:

| Giá trị `X-Timestamp` | Delta so với now | Freshness |
|---|---:|---|
| `1999999699` | -301 | Reject |
| `1999999700` | -300 | **Accept về thời gian** |
| `1999999701` | -299 | Accept về thời gian |
| `2000000000` | 0 | Accept về thời gian |
| `2000000299` | +299 | Accept về thời gian |
| `2000000300` | +300 | **Accept về thời gian** |
| `2000000301` | +301 | Reject |

Dùng `Clock.fixed` và so số nguyên, không dùng `Thread.sleep` để đợi qua biên. Test cả overflow/extreme `long`: phép trừ không được biến timestamp rất lớn thành delta nhỏ do overflow.

### 12.3. Tampering, replay và key rotation

| Trường hợp | Kỳ vọng |
|---|---|
| Client thay timestamp sau khi ký | HMAC fail |
| Client ký đúng timestamp **milliseconds** theo giá trị raw | HMAC có thể đúng, freshness theo seconds **fail** |
| Thay method `POST`, query `mode` hoặc body | HMAC fail |
| Thêm leading zero vào timestamp | Reject format |
| Thay client ID hoặc key ID | Không tạo principal khác, MAC/key lookup fail |
| Gửi request cũ với nonce cũ | Replay bị chặn |
| Hai node nhận cùng nonce đồng thời | Chỉ tối đa một reserve nguyên tử thành công |
| Nonce TTL chỉ 300 giây cho window ±300 | Test phải phát hiện nguy cơ hết TTL trước khi window kết thúc |
| Nonce store unavailable | Fail closed |
| Key đang `VERIFY_ONLY` đã quá deadline | Reject |
| Key `REVOKED` | Reject dù HMAC/time đúng |
| Principal được xác thực nhưng resource ngoài tenant | Authorization DENY |

### 12.4. Integration tests qua SDK, gateway và backend

Chạy các request qua tuyến gần với production:

~~~text
Java / JS / Go / Python client
      -> TLS endpoint
      -> CDN / API Gateway
      -> Reverse proxy
      -> HTTP verifier
      -> Shared nonce store
      -> Authorization / Business
~~~

Cần quan sát ít nhất **ba giá trị liên quan thời gian**: (1) timestamp text sender thực gửi, (2) timestamp text verifier nhận và ký lại, (3) `nowSeconds` của server. Dùng test fixture không có dữ liệu nhạy cảm để so canonical bytes, đo skew, key state và kết quả nonce.

Kiểm tra thêm HTTP/1.1↔HTTP/2, gateway rewrite, duplicate headers, queue delay, retry, nhiều backend có đồng hồ lệch khác nhau, NTP adjustment và khung giờ UTC/local khác nhau.

### 12.5. Property-based tests

- **Round-trip:** `Instant.ofEpochSecond(s).getEpochSecond()==s` với `s` hợp lệ.
- **Format:** `Long.toString(s)` là dạng canonical cho số dương hợp lệ.
- **Unit fidelity:** millis x1000 không được tự nhận như seconds.
- **Window boundaries:** -300/+300 inclusive, -301/+301 reject.
- **No overflow bypass:** số cực trị phải bị từ chối an toàn.
- **Signature binding:** đổi timestamp string dẫn đến MAC khác với xác suất áp đảo.
- **Replay uniqueness:** cùng nonce không được accept hai lần trong cùng phạm vi/window.
- **Cross-node consistency:** policy, clock, namespace/TTL nonce thống nhất.
- **Authorization:** MAC/time/nonce pass không đồng nghĩa cho phép tài nguyên.

## 13. Chẩn đoán những lỗi thường gặp

### 13.1. “Sai signature” thực ra là sai đơn vị

~~~text
Client X-Timestamp: 1704067200000
Receiver contract: epoch seconds
Result: too far in future
~~~

Kiểm tra SDK dùng `Date.now()`/`System.currentTimeMillis()` hay seconds, và so text ở edge/verifier. Không bỏ timestamp check hoặc tự thử nhiều đơn vị để “cho request chạy được”.

### 13.2. Đồng hồ client chậm hơn 6 phút

Với cửa sổ ±300 giây, request phải fail freshness dù HMAC đúng. Khắc phục bằng đồng bộ NTP, kiểm tra drift metrics và gửi lại với timestamp/nonce mới, đi kèm idempotency cho request có side effects. Không tự mở window lên nhiều giờ mà không đánh giá replay exposure.

### 13.3. Nonce store dùng sai TTL unit

`PX 660` chỉ giữ key khoảng **0,66 giây**, không phải 660 giây. Vì timestamp còn hợp lệ lâu hơn, replay có thể lọt nếu hệ thống dựa hoàn toàn vào nonce store. `EX 660` hoặc `PX 660000` mới biểu diễn khoảng **660 giây**.

### 13.4. Chuyển thời gian local thành epoch thiếu time zone

~~~java
// KHÔNG mặc định local time là UTC:
var local = java.time.LocalDateTime.now();
long wrong = local.toEpochSecond(java.time.ZoneOffset.UTC);
~~~

`LocalDateTime` không mang time zone. Gắn `UTC` vào một giờ thực sự là local có thể tạo epoch lệch nhiều giờ. Với request timestamp, dùng `Instant.now(clock).getEpochSecond()`; với lịch local cần chuyển, yêu cầu offset/`ZoneId` cụ thể và xử lý DST.

### 13.5. Server lấy timestamp của client làm “now”

Nếu hệ thống so `X-Timestamp` với chính `X-Timestamp` thay vì server clock, freshness luôn có thể pass. Nguồn `now` phải là **thời gian phía server tin cậy**.

### 13.6. Dùng nanoTime làm epoch time

`System.nanoTime() / 1_000_000_000` vẫn **không** cho Unix epoch seconds: phép chia đổi đơn vị nhưng **không đổi origin** của đồng hồ. Dùng nanoTime cho elapsed performance, không dùng để ký timestamp HTTP.

### 13.7. Nhầm duration và instant

`Duration.ofSeconds(300)` là một **khoảng dài**, còn `Instant.ofEpochSecond(300)` là một instant cụ thể ngay sau epoch 1970. Không đưa TTL/timeout duration vào `X-Timestamp`.

## 14. Bài tập

**Bài 1 — Chuyển đổi:** Viết epoch seconds, milliseconds, microseconds, nanoseconds cho `2024-01-01T00:00:00Z`. Vì sao chúng có thể mô tả cùng instant mà không cùng canonical bytes?

**Bài 2 — Phần lẻ:** Với `2024-01-01T00:00:00.123456789Z`, tính `Instant.getEpochSecond()` và `Instant.toEpochMilli()`. Phần chính xác nào bị mất theo hợp đồng seconds?

**Bài 3 — API Java:** So sánh `Instant.now().getEpochSecond()`, `System.currentTimeMillis()` và `System.nanoTime()`; API nào dùng làm timestamp và API nào phù hợp đo elapsed duration?

**Bài 4 — UTC:** Server ở UTC, client hiển thị UTC+7 cho cùng instant. Số epoch seconds có khác không? Vì sao cộng thêm 7 giờ vào header là sai?

**Bài 5 — Boundaries:** Với `now=2000000000`, window ±300, hãy tính kết quả cho `1999999699`, `1999999700`, `2000000300`, `2000000301`.

**Bài 6 — Tampering:** Client ký timestamp `1704067200`, gateway thay header thành `1704067200000`. Vì sao HMAC fail? Nếu client ký lại số milliseconds bằng secret thật, server phải làm gì?

**Bài 7 — Strict parser:** Viết test cho `01704067200`, `+1704067200`, `1704067200.0`, `9999999999999999999` và duplicate timestamp headers.

**Bài 8 — Nonce TTL:** Request có timestamp `t` được chấp nhận sớm nhất lúc `t-300`. Nếu TTL chỉ 300 giây, kẻ tấn công có thể phát lại trong window thế nào? Thiết kế TTL đúng với operational margin.

**Bài 9 — Clock skew:** Hai backend lệch giờ, cùng request có thể pass một node và fail node còn lại không? Thiết kế test bằng hai `Clock.fixed` và biện pháp vận hành.

**Bài 10 — Key rotation:** Key cũ hiện `REVOKED` nhưng timestamp do client ký thuộc thời gian key còn `ACTIVE`. Server phải dựa vào timestamp nào để quyết định?

**Bài 11 — Authorization:** Merchant A ký một request fresh có MAC đúng nhưng yêu cầu chuyển tiền từ tài khoản merchant B. Kết quả authentication và authorization khác nhau ra sao?

## 15. Checklist triển khai và kết luận

Checklist cuối bài:

1. **Đơn vị rõ ràng:** epoch seconds hay milliseconds phải nằm trong signing contract, không đoán theo số chữ số.
2. **Canonical text:** đúng integer ASCII, không dấu +/- và leading zero, reject decimal/duplicate headers/overflow.
3. **Đồng hồ đáng tin:** `Clock.systemUTC()` trên server, `Clock.fixed` cho test; không dùng `nanoTime()` làm epoch.
4. **Freshness:** giới hạn skew, kiểm tra inclusive boundaries, tránh arithmetic overflow.
5. **Canonical request:** ký nguyên văn timestamp đã validate, cùng method, URI, headers, raw body digest, audience và client/key ID.
6. **HMAC tag:** full 32 byte HMAC-SHA-256, strict Base64URL no-padding, so bằng `MessageDigest.isEqual`.
7. **Nonce:** CSPRNG, signed nonce, atomic reserve sau MAC, TTL tính đúng seconds và phủ toàn window.
8. **Key rotation:** key lookup theo client/audience, ACTIVE/VERIFY_ONLY/REVOKED, deadline theo server time tin cậy.
9. **Gateway:** không tự đổi timestamp unit/text hoặc signed fields; test HTTP/1.1/2, rewrites, time skew.
10. **Authorization:** check principal/action/resource/tenant; nonce không thay thế idempotency.
11. **Testing:** cross-language unit fixtures, boundaries, tamper/replay, multi-node clock, TTL và key revoke.
12. **Observability:** các mã lỗi `invalid_timestamp_format`, `timestamp_out_of_window`, `replayed_nonce`, `invalid_signature`; không log secret hoặc raw body nhạy cảm.

**Kết luận:** `1704067200` seconds và `1704067200000` milliseconds cùng biểu diễn **một instant**, nhưng là **hai thông điệp khác nhau trong HMAC request authentication**. Receiver an toàn phải chấp nhận **một format đơn vị rõ ràng**, kiểm tra time window theo clock server, ký đúng timestamp canonical, áp nonce TTL đủ dài theo cùng đơn vị và tiếp tục kiểm tra key state, gateway behavior cùng authorization. Chọn rõ seconds/milliseconds là một **quyết định giao thức và bảo mật**, không chỉ là lựa chọn hiển thị thời gian.

**Tài liệu tham khảo:**

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP field values, methods và date formats.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): request framing và header parsing.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): pseudo-header và chuyển giao thức.
- [RFC 2104 — HMAC](https://www.rfc-editor.org/rfc/rfc2104): keyed-hash message authentication.
- [RFC 4231 — HMAC test vectors](https://www.rfc-editor.org/rfc/rfc4231): giá trị tham chiếu cho HMAC-SHA-256.
- [RFC 4648 — Base-N Encodings](https://www.rfc-editor.org/rfc/rfc4648): Base64URL và canonical encoding.
- [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421): chuẩn tham khảo, không đồng nhất với contract minh họa `hmac-timeunit-v1`.
- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): getEpochSecond, toEpochMilli và quy tắc instant.
- [Java SE 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): systemUTC, fixed và clock injection.
- [Java SE 17 — Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): thời lượng so với absolute timestamp.
- [Java SE 17 — javax.crypto.Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): HmacSHA256 từ JCA.
- [Java SE 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): `isEqual` so sánh MAC.





