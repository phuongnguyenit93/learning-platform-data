# Độ chính xác khi truyền và lưu dữ liệu thời gian: Instant, offset và Java

> **Module:** Java 8 — Instant và offset. **Trọng tâm:** Bảo toàn **thời điểm thực**, **phần giây**, **offset** và **ngữ nghĩa dữ liệu** khi gửi giữa dịch vụ, chuyển thành JSON/epoch, lưu bằng SQL/JDBC rồi đọc ngược. Những API `java.time` cốt lõi trong bài có từ Java 8 và vẫn còn áp dụng cho Java hiện nay.

## 1. Vấn đề thực tế: timestamp đi qua nhiều hệ thống

Xem một hệ thống ghi nhận giao dịch. Dịch vụ Java tạo:

~~~java
Instant eventTime =
        Instant.parse("2025-01-02T03:04:05.123456789Z");
~~~

Đây là **đoạn minh họa**; cần `import java.time.Instant;`. Giá trị này chứa thời điểm UTC và phần giây có **chín chữ số**, tức 123.456.789 nanosecond sau giây thứ 05.

Dữ liệu có thể đi qua:

~~~text
Java Instant
    |
    +--> JSON/API (chuỗi ISO-8601 hay số epoch)
    |
    +--> Kafka/queue/event payload
    |
    +--> JavaScript hoặc dịch vụ ngôn ngữ khác
    |
    +--> JDBC/SQL (TIMESTAMP với precision riêng)
    |
    +--> Đọc lại thành java.time object
    |
    +--> So sánh với giá trị ban đầu
~~~

Nếu một bước chỉ giữ **milliseconds**, `.123456789` có thể trở thành `.123`. Nếu một bước chuẩn hóa từ `+07:00` về `Z`, **Instant có thể không đổi** nhưng **offset gốc không còn**. Nếu một bước bỏ cả offset và lưu thành timestamp không có timezone, thông tin xác định thời điểm thực có thể bị mất.

**Không có một khái niệm “giữ nguyên timestamp” duy nhất.** Phải phân biệt ít nhất ba điều:

1. **Giữ đúng thời điểm trên timeline:** hai biểu diễn quy ra cùng `Instant`.
2. **Giữ đúng độ phân giải/phần lẻ của giây:** ví dụ từ nanosecond sang microsecond có mất sáu? **Không:** từ 9 chữ số xuống 6 chữ số sẽ bỏ **3 chữ số** thấp nhất của phần nano.
3. **Giữ đúng dữ liệu người gửi đã biểu diễn:** chuỗi `+07:00` có thể cần giữ nguyên offset, format hoặc `ZoneId` tùy hợp đồng nghiệp vụ.

Ba tiêu chí này có thể độc lập. Một dữ liệu được đọc lại đúng *thời điểm* mà vẫn không giống hệt dữ liệu đầu vào ở mức offset hoặc text.

## 2. Phân biệt độ phân giải, độ chính xác và tính toàn vẹn

Trong hệ thống thời gian, các khái niệm sau thường bị gộp làm một:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Resolution / độ phân giải** | Kiểu dữ liệu có thể biểu diễn bước nhỏ tới đâu? | `Instant` lưu phần giây tới nanosecond, 9 chữ số |
| **Actual clock resolution** | Đồng hồ hệ thống thực sự thay đổi theo bước nhỏ nào? | Có thể chỉ đến micro/millisecond tùy OS/JVM/hardware |
| **Accuracy / độ đúng so với thực tế** | Clock lệch bao nhiêu so với thời gian chuẩn? | Clock sai 200 ms dù biểu diễn 9 chữ số |
| **Precision khi truyền** | Wire format mang được bao nhiêu chữ số? | Timestamp ISO có 9 chữ số so với số epoch millis |
| **Precision khi lưu** | Column/driver/database giữ bao nhiêu chữ số? | `TIMESTAMP(6)` có thể chỉ lưu microsecond |
| **Fidelity / toàn vẹn ngữ nghĩa** | Sau một vòng ghi/đọc, dữ liệu có giữ ý nghĩa gốc không? | Giữ Instant nhưng đánh mất offset ban đầu |

Một đối tượng `Instant` có trường nanosecond **không chứng minh đồng hồ đã đo chính xác tới 1 ns**. Ví dụ, lấy `Instant.now()` rồi in chín chữ số không xác nhận độ chính xác của phần cứng hay đồng bộ NTP.

**Nguyên tắc:** xác định rõ yêu cầu thực tế về giây, mili giây, micro giây hay nano giây; cách đồng bộ đồng hồ; khả năng của mỗi endpoint; và chính sách khi một phía không hỗ trợ đủ độ hạt.

### 2.1. Một bảng đổi đơn vị cần nhớ

| Đơn vị | Số đơn vị trong một giây | Chữ số thập phân |
| --- | ---: | ---: |
| Giây | 1 | 0 |
| Millisecond (ms) | 1.000 | 3 |
| Microsecond (µs) | 1.000.000 | 6 |
| Nanosecond (ns) | 1.000.000.000 | 9 |

Ví dụ `05.123456789` gồm `123` ms + `456` µs + `789` ns. Khi chỉ giữ 3 chữ số sau dấu chấm, thông tin `456789` nanosecond nằm dưới mức millisecond sẽ không còn trong bản biểu diễn đã làm giảm độ phân giải.

Không coi số lượng chữ số sau dấu chấm **được hiển thị** là đo lường độ chính xác nguồn. Một formatter có thể in dấu chấm và nhiều số 0, nhưng số 0 không tạo thêm độ chính xác vật lý.

## 3. Instant: một thời điểm, giây epoch và nano-of-second

`java.time.Instant` biểu diễn một thời điểm trên timeline. Về mô hình giá trị, nó có:

- Một `long` số giây tính từ epoch `1970-01-01T00:00:00Z`.
- Một `int` nanosecond **trong giây**, từ `0` đến `999_999_999`.

Các phương thức chính:

~~~java
Instant instant =
        Instant.parse("2025-01-02T03:04:05.123456789Z");

long seconds = instant.getEpochSecond();
int nanos = instant.getNano();

Instant restored = Instant.ofEpochSecond(seconds, nanos);
boolean preserved = restored.equals(instant); // true
~~~

Đây là **đoạn minh họa**, sử dụng `Instant` của Java 8.

**Điểm rất quan trọng:** `getNano()` không phải “tổng số nano giây kể từ 1970”. Nó chỉ là phần dư nano **bên trong giây**. Nếu muốn giao thức chính xác và ít rủi ro tràn số, cặp `(epochSecond, nanoOfSecond)` là một biểu diễn tốt khi cả hai phía thống nhất hợp đồng.

### 3.1. Thời điểm trước epoch và phần nano dương

~~~java
Instant beforeEpoch =
        Instant.parse("1969-12-31T23:59:59.999999999Z");

System.out.println(beforeEpoch.getEpochSecond()); // -1
System.out.println(beforeEpoch.getNano());        // 999999999
~~~

Không sai khi `getEpochSecond()` âm mà `getNano()` dương. Đối với một thời điểm **một nanosecond trước epoch**:

~~~text
epochSecond = -1
nanoOfSecond = 999999999

-1 giây + 0.999999999 giây = -0.000000001 giây
~~~

Nếu tự xây quy tắc “giây = cắt phần nguyên về 0” rồi gán phần dư âm, có thể tạo lỗi ở các mốc trước năm 1970. Luôn xác định convention rõ ràng, hoặc dùng trực tiếp `Instant.ofEpochSecond`/`getEpochSecond`/`getNano`.

### 3.2. Chuyển từ epoch millis là phép **giảm độ phân giải**

~~~java
Instant original =
        Instant.parse("2025-01-02T03:04:05.123456789Z");

long millis = original.toEpochMilli();
Instant fromMillis = Instant.ofEpochMilli(millis);
// 2025-01-02T03:04:05.123Z

boolean exact = original.equals(fromMillis); // false
~~~

`Instant.toEpochMilli()` trả số millisecond tính từ epoch. Nếu giá trị có chi tiết nhỏ hơn millisecond, phép đổi **loại bỏ thông tin** đó. `Instant.ofEpochMilli(...)` không thể khôi phục các chữ số đã mất.

Trong ví dụ, chênh lệch giữa thời điểm gốc và bản millisecond là **456.789 ns**. Sau một vòng encode/decode bằng millis, so sánh `equals` không còn true.

### 3.3. Tràn số ở timestamp cực xa

`Instant` có miền giá trị rất rộng, nhưng không phải mọi `Instant` đều đổi được thành **một long milliseconds**, và càng không thể gói mọi timestamp thành **một long nanoseconds** kể từ epoch. `toEpochMilli()` có thể ném `ArithmeticException` nếu số milli vượt giới hạn `long`.

Không xây API giả định “`long epochNanos` luôn đủ cho mọi ngày có thể biểu diễn bằng Instant”. Một long nanoseconds kể từ epoch chỉ có miền thời gian hữu hạn quanh năm 1970, nhỏ hơn miền của `Instant`.

## 4. Instant và OffsetDateTime: bảo toàn thời điểm khác bảo toàn offset

`OffsetDateTime` lưu **ngày/giờ local + UTC offset**, ví dụ:

~~~text
2025-01-02T10:04:05.123456789+07:00
2025-01-02T03:04:05.123456789Z
~~~

Hai chuỗi trên biểu diễn **cùng một thời điểm**, nhưng khác mặt đồng hồ và offset.

~~~java
Instant instant =
        Instant.parse("2025-01-02T03:04:05.123456789Z");

OffsetDateTime inPlusSeven =
        instant.atOffset(ZoneOffset.ofHours(7));

OffsetDateTime inUtc =
        inPlusSeven.withOffsetSameInstant(ZoneOffset.UTC);

System.out.println(inPlusSeven.toInstant().equals(inUtc.toInstant()));
// true
~~~

Đây là **đoạn minh họa**, cần import `Instant`, `OffsetDateTime`, `ZoneOffset`.

Khi truyền dữ liệu:

- Nếu chỉ cần biết **sự kiện diễn ra lúc nào**, truyền/lưu dạng chuẩn UTC `Instant` thường đơn giản.
- Nếu cần thể hiện **offset mà nguồn đã khai báo**, phải giữ `OffsetDateTime` hoặc gửi thêm trường offset gốc.
- Nếu cần lịch tương lai theo **múi giờ địa phương có quy tắc DST**, `ZoneId` (ví dụ `Europe/Paris`) khác một `ZoneOffset` cố định. Cần thiết kế thêm thông tin vùng khi lịch nghiệp vụ đòi hỏi.

### 4.1. equals() và isEqual() không giống nhau

~~~java
OffsetDateTime a =
        OffsetDateTime.parse("2025-01-02T10:04:05+07:00");

OffsetDateTime b =
        OffsetDateTime.parse("2025-01-02T03:04:05Z");

boolean sameInstant = a.isEqual(b); // true
boolean sameRepresentation = a.equals(b); // false
~~~

Đây là **đoạn minh họa**. `OffsetDateTime.isEqual` hỏi **cùng instant không**. `OffsetDateTime.equals` còn so cùng ngày giờ local và offset. Khi kiểm tra round-trip, phải xác định mục tiêu **ngữ nghĩa** trước khi chọn phép assertion.

### 4.2. withOffsetSameInstant và withOffsetSameLocal

Đừng nhầm:

~~~java
OffsetDateTime localView =
        OffsetDateTime.parse("2025-01-02T10:04:05+07:00");

OffsetDateTime sameInstant =
        localView.withOffsetSameInstant(ZoneOffset.UTC);
// 2025-01-02T03:04:05Z

OffsetDateTime sameWallClock =
        localView.withOffsetSameLocal(ZoneOffset.UTC);
// 2025-01-02T10:04:05Z
~~~

`withOffsetSameInstant` giữ thời điểm thực, đổi đồng hồ local phù hợp offset mới. `withOffsetSameLocal` giữ các trường local, đổi offset nên **đổi thời điểm thực**. Nếu máy chủ đang chuẩn hóa dữ liệu vào UTC, thường muốn **same instant**, không phải same local.

### 4.3. Offset không phải ZoneId

Một giá trị `+07:00` nói offset cụ thể. `Asia/Ho_Chi_Minh` là ID vùng với các quy tắc được quản lý qua dữ liệu thời gian và có thể khác nhau theo thời điểm lịch sử. Một offset **không có đủ thông tin** để lên lịch nhắc việc địa phương dài hạn khi vùng có DST/thay đổi quy tắc.

Không tự mặc định `+07:00` luôn tương đương mọi thời điểm ở một vùng cụ thể; khi cần định nghĩa lịch hẹn theo vùng, phải lưu **region ZoneId** ngoài giá trị local hoặc lưu representation phù hợp.

## 5. Chọn wire format để truyền dữ liệu

### 5.1. Chuỗi ISO-8601/RFC 3339 rõ ràng về UTC/offset

Thường nên chọn một format văn bản có offset tường minh:

~~~json
{
  "eventId": "evt-42",
  "occurredAt": "2025-01-02T03:04:05.123456789Z"
}
~~~

Khi người gửi cần giữ offset gốc:

~~~json
{
  "eventId": "evt-42",
  "occurredAt": "2025-01-02T10:04:05.123456789+07:00"
}
~~~

Đây là **JSON minh họa**. Hai payload có thể chỉ cùng instant. Bên nhận phải parse theo đúng kiểu:

~~~java
Instant eventTime =
        Instant.parse("2025-01-02T03:04:05.123456789Z");

OffsetDateTime sourceTime =
        OffsetDateTime.parse(
                "2025-01-02T10:04:05.123456789+07:00");

Instant normalized = sourceTime.toInstant();
~~~

Đây là **đoạn minh họa**. Bên phát không nên tự loại bỏ `Z` hay `+07:00` rồi giả định phần còn lại là UTC. Chuỗi `2025-01-02T10:04:05.123456789` **không offset** không đủ để xác định instant.

**Về đặc tả:** ISO-8601 có nhiều biểu diễn; RFC 3339 là profile thường dùng cho trao đổi timestamp trên API. Hợp đồng cần ghi rõ format chấp nhận, timezone/offset bắt buộc hay không, tối đa mấy chữ số thập phân và cách xử lý lỗi.

### 5.2. ISO_INSTANT và ISO_OFFSET_DATE_TIME

Java 8 có các formatter phù hợp:

~~~java
Instant instant =
        Instant.parse("2025-01-02T03:04:05.123456789Z");

String utcText =
        DateTimeFormatter.ISO_INSTANT.format(instant);

OffsetDateTime offset =
        instant.atOffset(ZoneOffset.ofHours(7));

String offsetText =
        DateTimeFormatter.ISO_OFFSET_DATE_TIME.format(offset);
~~~

Đây là **đoạn minh họa**, cần `DateTimeFormatter` và các class liên quan. Với dữ liệu trên:

~~~text
utcText    = 2025-01-02T03:04:05.123456789Z
offsetText = 2025-01-02T10:04:05.123456789+07:00
~~~

Khi sử dụng các formatter ISO chuẩn, đối tượng có thông tin phù hợp có thể round-trip cả giá trị nano. Tuy nhiên, nếu API bên kia **chỉ hỗ trợ 3 hoặc 6 chữ số**, hãy định nghĩa chính sách làm giảm độ phân giải thay vì âm thầm cắt dữ liệu.

### 5.3. toString() không hứa luôn đúng 9 chữ số

~~~java
Instant a = Instant.parse("2025-01-02T03:04:05Z");
Instant b = Instant.parse("2025-01-02T03:04:05.123Z");
Instant c = Instant.parse("2025-01-02T03:04:05.123456Z");
Instant d = Instant.parse("2025-01-02T03:04:05.123456789Z");
~~~

`Instant.toString()` dùng dạng ISO, nhưng **số chữ số phần giây có thể khác** tùy giá trị. Các chuỗi không bắt buộc phải có độ dài cố định. Vì vậy, **đừng kiểm tra timestamp bằng số ký tự hoặc cắt chuỗi ở vị trí cố định**. Dùng parser/formatter có hợp đồng rõ ràng.

Tương tự, một giá trị có nano giây bằng 0 không trở nên “kém chính xác hơn” theo nghĩa độ tin cậy vật lý chỉ vì formatter không in `.000000000`. Giá trị số 0 ở phần lẻ có thể biểu diễn chính xác theo mọi độ phân giải.

### 5.4. Mẫu tùy biến có thể làm mất phần giây

Ví dụ:

~~~java
DateTimeFormatter millisOnly =
        DateTimeFormatter.ofPattern(
                "uuuu-MM-dd'T'HH:mm:ss.SSSXXX");

String text = OffsetDateTime.parse(
        "2025-01-02T10:04:05.123456789+07:00")
        .format(millisOnly);
// 2025-01-02T10:04:05.123+07:00
~~~

Đây là **đoạn minh họa**, dùng `OffsetDateTime` và `DateTimeFormatter`. Pattern `SSS` chỉ in **3 chữ số phần giây**. Nếu parse lại từ `text`, không thể suy lại `456789` nanosecond đã bỏ.

Không “bổ sung số 0” rồi gọi đó là độ chính xác gốc. Nếu cần làm tròn ở mức millisecond, hãy thực hiện bằng một quy tắc có kiểm thử; một formatter chỉ là lớp hiển thị.

## 6. Dùng epoch time: làm rõ đơn vị và miền giá trị

Các field API như `timestamp`, `createdAt` hay `time` thường bị gửi dưới dạng số mà **không nói đơn vị**. Đây là nguyên nhân phổ biến khiến mốc thực bị lệch từ vài thập kỷ đến hàng chục nghìn năm.

### 6.1. Epoch seconds và epoch milliseconds

~~~java
Instant instant =
        Instant.parse("2025-01-02T03:04:05.123456789Z");

long seconds = instant.getEpochSecond();
long millis = instant.toEpochMilli();
int nanos = instant.getNano();
~~~

- `seconds` là **giây nguyên** từ epoch, bỏ phần fractional nếu đứng một mình.
- `millis` là **millisecond** từ epoch; không giữ độ phân giải nano.
- `nanos` là **phần nano giây trong giây**, phải ghép với seconds nếu cần toàn giá trị.

API số nên đặt tên rõ:

~~~json
{
  "epochSecond": 0,
  "nanoOfSecond": 123456789
}
~~~

Đây là một **timestamp ví dụ** biểu diễn `1970-01-01T00:00:00.123456789Z`. Cặp số này dễ round-trip khi client dùng integer chính xác và thực hiện đúng phép tạo `Instant.ofEpochSecond(epochSecond, nanoOfSecond)`.

### 6.2. Nếu dùng một field numeric, ghi rõ suffix

Ví dụ các tên tự mô tả:

- `occurredAtEpochSeconds` — giây từ 1970 UTC.
- `occurredAtEpochMillis` — millisecond từ 1970 UTC.
- `occurredAtEpochMicros` — microsecond từ 1970 UTC nếu giao thức thực sự hỗ trợ.
- `occurredAtEpochNanos` — nanosecond từ 1970 UTC nếu kiểu số và miền thời gian được định nghĩa có kiểm soát.

**Không tự đổi tên field mà không versioning contract.** Một client đọc số millisecond như giây có thể nhận timestamp vô lý hoặc vượt miền thời gian.

### 6.3. JavaScript và độ chính xác số nguyên

JavaScript `Number` là IEEE-754 double, **không biểu diễn chính xác mọi số nguyên** lớn hơn `Number.MAX_SAFE_INTEGER = 2^53 - 1`. Một epoch timestamp tính bằng **nanosecond** quanh thời điểm hiện đại có độ lớn xấp xỉ `10^18`, vượt vùng integer an toàn đó.

Vì vậy, nếu truyền epoch nanoseconds sang JavaScript:

- Không mặc định một JSON numeric literal sẽ round-trip toàn bộ bit giá trị nanosecond.
- Cân nhắc chuỗi timestamp ISO-8601 có offset; hoặc gửi cặp giây + nano với quy ước kiểu số, hoặc decimal string.
- Nếu dùng `BigInt` ở client, cần chú ý JSON serialization mặc định không hỗ trợ trực tiếp BigInt như một Number. Cần schema và encode/decode rõ ràng.
- Các epoch **milliseconds** ở thời điểm thông thường gần hiện tại vẫn nằm dưới giới hạn số nguyên an toàn của JavaScript, nhưng điều này **không khôi phục nano giây** đã mất.

### 6.4. Số giây thập phân và floating-point

Tránh kiểu:

~~~java
double timestamp = instant.getEpochSecond()
        + instant.getNano() / 1_000_000_000.0;
~~~

Đây là **đoạn minh họa phản ví dụ** nếu yêu cầu bảo toàn nano tuyệt đối: `double` có số bit hữu hạn, nên cộng một epoch seconds lớn với phần nano bé có thể làm tròn, không giữ đủ 9 chữ số sau dấu chấm.

Nếu giao thức yêu cầu số giây thập phân với 9 chữ số cố định, cân nhắc biểu diễn dưới dạng **string decimal** và dùng `BigDecimal` ở hai phía để thao tác chính xác, kèm quy tắc cho giá trị âm và giới hạn. Thường đơn giản hơn là dùng ISO text hoặc cặp seconds + nanos.

### 6.5. Trường hợp trước epoch dễ sai dấu

Xem:

~~~java
Instant negative =
        Instant.parse("1969-12-31T23:59:59.999999999Z");

long ms = negative.toEpochMilli(); // -1
~~~

Giá trị chỉ trước epoch **1 ns** có timestamp milli là `-1` theo biểu diễn millisecond mà Java sử dụng, chứ không phải `0`. Những phép làm tròn tự viết theo kiểu truncate-towards-zero có thể tạo sự khác biệt quanh mốc âm. Bài kiểm thử round-trip nên có **ít nhất một timestamp trước epoch**, không chỉ thời gian hiện đại dương.

## 7. Lưu vào SQL: precision và timezone không thống nhất giữa các hệ quản trị

Không có quy tắc “cột TIMESTAMP ở mọi database giữ chính xác 9 chữ số nano giây”. Một số database/column type chỉ giữ millisecond hoặc microsecond; một số có precision khai báo; thao tác gán có thể **round** hoặc **truncate** tùy hệ quản trị, driver và kiểu cột.

Ví dụ minh họa cách mô tả precision trong schema:

~~~sql
-- CHỈ LÀ MẪU KHÁI NIỆM: phải kiểm tra cú pháp/hợp đồng DB đang dùng.
CREATE TABLE events (
    id BIGINT PRIMARY KEY,
    occurred_at TIMESTAMP(6) NOT NULL
);
~~~

`TIMESTAMP(6)` thông thường thể hiện mục tiêu **6 chữ số phần giây (microsecond)** trong hệ thống có hỗ trợ tham số precision này. Nhưng **ngữ nghĩa timezone** của `TIMESTAMP`, precision thực tế và cách database xử lý phần nano phải được xác nhận trên công nghệ cụ thể.

### 7.1. TIMESTAMP WITHOUT TIME ZONE và TIMESTAMP WITH TIME ZONE

Hai cụm tên xuất hiện trong nhiều hệ quản trị:

| Cách lưu/kiểu dữ liệu | Có thể biểu diễn | Cần kiểm tra |
| --- | --- | --- |
| SQL timestamp **không timezone** | Ngày giờ local, không có thông tin zone/offset | Ứng dụng/driver có tự quy đổi timezone không? |
| SQL timestamp **with timezone** | Thường dùng cho thời điểm có offset/timeline | Database có giữ nguyên offset gốc hay chuẩn hóa? |
| Epoch millis dưới kiểu `BIGINT` | Một số milli nguyên từ epoch | Mất phần dưới milli; cách dùng số âm; miền long |
| Epoch seconds + nanos ở hai cột | Một cặp biểu diễn `Instant` tới nano nếu kiểu/cột đủ | Constraint nano 0–999999999, quy tắc âm |
| ISO timestamp dạng text | Có thể giữ chính xác chuỗi đã nhận nếu đủ độ dài | Validation, canonical format, index/query/timezone |

**Quan trọng:** tên cột chứa chữ “with time zone” **không tự bảo đảm giữ nguyên offset văn bản mà người gửi đã truyền**. Một số hệ quản trị chuẩn hóa dữ liệu về mốc UTC/timeline và không lưu lại offset ban đầu; đọc ngược có thể nhận `Z` dù đầu vào là `+07:00`.

Nếu ứng dụng cần biết offset gốc để hiển thị chứng từ như lúc gửi, hãy **lưu offset/zone metadata ở field riêng** hoặc chọn schema phù hợp và xác minh bằng thử nghiệm thực tế.

### 7.2. Ví dụ tình huống microsecond

Một Java Instant:

~~~text
2025-01-02T03:04:05.123456789Z
~~~

Một hệ thống lưu tối đa 6 chữ số có thể trả một trong những dạng tùy quy tắc:

~~~text
2025-01-02T03:04:05.123456Z  (truncate xuống microsecond)
2025-01-02T03:04:05.123457Z  (round sang microsecond gần nhất)
~~~

**Đừng khẳng định database nào cũng làm giống nhau.** Cần kiểm tra cách lưu và đọc ngược trên chính môi trường triển khai, đặc biệt khi transaction có precision nhỏ hơn API Java.

Nếu business yêu cầu so timestamp không sai lệch nanosecond, một cột chỉ giữ microsecond **không đáp ứng được**. Nếu business cho phép microsecond, cần **chuẩn hóa ngay tại boundary** theo quy tắc thống nhất hoặc ghi rõ mất mát cho bên gọi.

### 7.3. JDBC 4.2 và java.time

JDBC 4.2 (trong hệ sinh thái Java 8) giới thiệu mapping cho nhiều kiểu `java.time`, nhưng **khả năng hỗ trợ cụ thể vẫn phụ thuộc driver/database**. Thường gặp:

- `LocalDateTime` tương ứng dữ liệu timestamp **không có offset**.
- `OffsetDateTime` tương ứng dữ liệu timestamp **có timezone/offset** ở những driver hỗ trợ.
- `Instant` có thể cần mapping rõ ràng; **không mặc định driver nào cũng nhận `setObject(..., Instant)`**.
- `java.sql.Timestamp` có trường nano trong Java, nhưng đi qua driver/cột vẫn có thể bị giới hạn precision hoặc thay đổi ngữ nghĩa timezone.

Đoạn minh họa dưới đây giả định connection và column hỗ trợ mapping `OffsetDateTime` của JDBC:

~~~java
// Minh họa, giả định đã có Connection conn,
// bảng events có cột occurred_at tương thích với offset timestamp.
OffsetDateTime utcValue = instant.atOffset(ZoneOffset.UTC);

try (PreparedStatement ps = conn.prepareStatement(
        "INSERT INTO events(id, occurred_at) VALUES (?, ?)")) {
    ps.setLong(1, eventId);
    ps.setObject(2, utcValue);
    ps.executeUpdate();
}
~~~

Đây **không phải chương trình độc lập**: cần `conn`, `eventId`, `instant`, import JDBC và schema hợp lệ. Phần quan trọng không phải mẫu INSERT, mà là chọn **kiểu Java + kiểu SQL + quy tắc chuyển đổi** nhất quán và kiểm tra kết quả thực tế.

Khi đọc, nếu driver hỗ trợ:

~~~java
OffsetDateTime read =
        resultSet.getObject("occurred_at", OffsetDateTime.class);
Instant stored = read.toInstant();
~~~

Đây là đoạn minh họa, giả định `resultSet` hợp lệ. `stored` chỉ bảo đảm bằng giá trị ban đầu nếu **đường truyền và lưu** thực sự không làm mất precision hay diễn giải sai timezone.

### 7.4. Ví dụ thực tế về driver PostgreSQL

Tài liệu pgJDBC mô tả mapping thường dùng: SQL `TIMESTAMP WITHOUT TIME ZONE` ↔ `LocalDateTime` và `TIMESTAMP WITH TIME ZONE` ↔ `OffsetDateTime`. Tài liệu cũng nói driver trả `OffsetDateTime` của loại có timezone theo **UTC offset 0**, do phía database lưu mốc UTC; **không giữ offset đầu vào như metadata**. pgJDBC không hỗ trợ trực tiếp `Instant` qua các mapping `getObject/setObject` java.time được liệt kê ở đó.

Điều này là **ví dụ của một driver cụ thể**, không suy rộng máy móc sang Oracle Database, SQL Server, MySQL, SQLite hay tất cả bản JDBC. Khi dùng hệ khác, phải đọc tài liệu cho driver/kiểu cột đang chạy.

### 7.5. Khi cần bảo toàn đầy đủ 9 chữ số

Cân nhắc các chiến lược có hợp đồng rõ:

1. Chọn **kiểu cột hỗ trợ nanosecond** nếu database/driver có chứng cứ round-trip.
2. Lưu **epochSecond** ở `BIGINT` và **nanoOfSecond** ở integer có ràng buộc `0..999999999`; dựng lại bằng `Instant.ofEpochSecond`.
3. Lưu **chuỗi ISO timestamp** nếu cần giữ cả format/offset ban đầu, và bảo đảm validation/index/query hợp lý.
4. Nếu chỉ cần precision nhỏ hơn, **chủ động hạ độ phân giải** theo đơn vị và quy tắc làm tròn/cắt đã thống nhất; không gọi đó là “lossless”.

Mọi chiến lược đều có trade-off: truy vấn thời gian, index, range, storage, tương thích API, và cách nâng cấp dữ liệu cũ. Không chọn hai cột seconds+nanos chỉ vì số 9 xuất hiện trong source code; làm vậy khi yêu cầu nghiệp vụ thật sự cần fidelity đến nano.

## 8. Chính sách hạ precision: truncate hay round?

### 8.1. truncateTo theo ChronoUnit

Java 8 cung cấp `Instant.truncatedTo(TemporalUnit)`:

~~~java
Instant value =
        Instant.parse("2025-01-02T03:04:05.123456789Z");

Instant micros = value.truncatedTo(ChronoUnit.MICROS);
Instant millis = value.truncatedTo(ChronoUnit.MILLIS);
Instant seconds = value.truncatedTo(ChronoUnit.SECONDS);
~~~

Đây là **đoạn minh họa**, cần `java.time.temporal.ChronoUnit`. Kết quả:

~~~text
micros  = 2025-01-02T03:04:05.123456Z
millis  = 2025-01-02T03:04:05.123Z
seconds = 2025-01-02T03:04:05Z
~~~

Phương thức `truncatedTo` loại bỏ phần nhỏ hơn đơn vị chỉ định, không phải một API làm tròn theo quy tắc `HALF_UP` hoặc `HALF_EVEN`. Nếu một DB **làm tròn** khi lưu còn ứng dụng **cắt** trước khi lưu, round-trip kỳ vọng có thể vẫn khác nếu hợp đồng không nhất quán.

### 8.2. Thời điểm âm cần kiểm thử riêng

~~~java
Instant negative =
        Instant.parse("1969-12-31T23:59:59.999999999Z");

Instant byMillis = Instant.ofEpochMilli(negative.toEpochMilli());
// 1969-12-31T23:59:59.999Z
~~~

Đoạn minh họa cho thấy phần trước epoch 1 ns trở thành mốc **trước epoch 1 ms** khi quy về milliseconds. Đừng nhầm với Java integer division cắt về 0 ở một công thức tự viết trên tổng nano âm. Test cả trước/sau epoch nếu dữ liệu lịch sử được hỗ trợ.

### 8.3. Rounding có quy tắc business

Nếu yêu cầu là **round to nearest microsecond**, trước hết xác định:

- Nếu đúng nửa đơn vị thì làm tròn lên, xuống, về chẵn hay ra xa 0?
- Với thời điểm âm, quy tắc được áp trên timeline như thế nào?
- Giá trị sát ranh giới giây có được carry sang giây tiếp theo không?
- Các API và database có dùng đúng cùng chính sách?
- Có ảnh hưởng đến sắp xếp log, sự kiện sát nhau, phân trang cursor hay khóa uniqueness không?

Không tùy ý viết `+500_000 nanos` rồi truncate mà bỏ qua overflow/biên thời gian/giá trị âm nếu phần mềm yêu cầu nghiêm ngặt. Dùng phép tính integer hoặc `BigDecimal` với chính sách rõ và test các mốc biên; hoặc dựa vào quy tắc hạ precision mà hệ thống chủ đích chấp nhận.

## 9. Timestamp trong JSON, message bus và hệ thống nhiều ngôn ngữ

### 9.1. Quy ước contract nên có từ đầu

Một schema tốt cần định nghĩa:

1. **Loại ngữ nghĩa:** thời điểm tuyệt đối hay ngày giờ theo lịch?
2. **Kiểu truyền:** chuỗi offset timestamp, epoch milliseconds, hay cặp seconds+nanos?
3. **Đơn vị:** seconds/millis/micros/nanos — đừng để người đọc đoán bằng độ dài số.
4. **Precision:** hỗ trợ tối đa bao nhiêu chữ số, có bắt buộc giữ phần lẻ không?
5. **Normalization:** có bắt buộc gửi UTC `Z` không, hay nhận offset tùy ý?
6. **Offset/Zone:** cần giữ offset gốc? cần cả region ZoneId?
7. **Validation:** xử lý chuỗi thiếu offset, timestamp ngoài range, số thập phân sai định dạng thế nào?
8. **Compatibility:** client cũ đọc bản payload mới có sai đơn vị hay không?

Nếu chỉ cần timestamp của sự kiện, một trường chuỗi UTC chuẩn thường dễ tương tác:

~~~json
{
  "eventType": "PAYMENT_ACCEPTED",
  "occurredAt": "2025-01-02T03:04:05.123456789Z"
}
~~~

Với dữ liệu cần giữ thêm cách nhìn địa phương, nên tách:

~~~json
{
  "occurredAt": "2025-01-02T03:04:05.123456789Z",
  "sourceOffset": "+07:00",
  "sourceZoneId": "Asia/Ho_Chi_Minh"
}
~~~

Đây là **JSON minh họa**: dữ liệu `sourceZoneId` chỉ đúng nếu hệ thống thực sự biết vùng gốc, không nên suy đoán region ZoneId chỉ từ `+07:00`.

### 9.2. Protobuf, Avro, Kafka và serialization framework

Một message framework không tự bảo đảm precision chỉ vì Java sử dụng `Instant`. Wire schema mới là thứ quyết định lượng thông tin có thể mang:

- Schema có **seconds + nanos** có thể giữ subsecond precision nếu serializer và các consumer thực thi đúng.
- Schema chỉ có **epoch millis** mất phần nhỏ hơn 1 ms.
- Schema dùng **double seconds** có thể làm tròn dưới mức nanosecond do giới hạn binary floating point.
- Schema dùng **ISO string** có thể giữ đủ chữ số nếu không bị formatter/adapter cắt bớt.
- Trên cùng một queue, hai phiên bản client có thể áp serializer khác nhau: cần compatibility test và versioned contract.

Không suy ra hành vi của mọi serializer từ tên công nghệ. Với JSON library, ORM, Avro/protobuf adapter và message schema, hãy xác minh cấu hình **phiên bản đang dùng** và kết quả encode/decode chính xác trên môi trường thật.

### 9.3. Timezone mặc định không được quyết định ngầm

Khi server nhận `"2025-01-02T03:04:05"` **không offset**, không tự coi đó là UTC chỉ vì JVM chạy ở UTC; cũng không tự coi là giờ Việt Nam chỉ vì user hiện đang ở Việt Nam. Cần nghiệp vụ chỉ rõ timezone hoặc từ chối payload không đủ thông tin.

Tương tự, nếu cột DB lưu local timestamp, việc đọc ra rồi gọi `atZone(ZoneId.systemDefault())` có thể làm thay đổi ý nghĩa khi triển khai sang container ở vùng khác.

## 10. Kiểm tra round-trip: biết chính xác cái gì được bảo toàn

**Round-trip** là hành trình encode → gửi/lưu → decode. Test không nên chỉ kiểm tra “parser không ném lỗi”; phải kiểm tra bất biến của dữ liệu theo hợp đồng.

### 10.1. Trường hợp yêu cầu không mất nanosecond

~~~java
Instant before =
        Instant.parse("2025-01-02T03:04:05.123456789Z");

String text = DateTimeFormatter.ISO_INSTANT.format(before);
Instant after = Instant.parse(text);

boolean lossless = before.equals(after); // true
~~~

Đây là **đoạn minh họa**. Với cùng API ISO trong Java, không có bước hạ precision nên kết quả giữ nguyên. Trong thử nghiệm API/DB thực, phải kiểm tra ngay kết quả **sau bước thực tế** chứ không chỉ tự round-trip trong JVM.

### 10.2. Trường hợp chủ đích chỉ giữ microsecond

~~~java
Instant before =
        Instant.parse("2025-01-02T03:04:05.123456789Z");

Instant normalized =
        before.truncatedTo(ChronoUnit.MICROS);

// Giả sử một kênh truyền đã được chứng minh là giữ đúng microsecond.
// Thì so sánh đầu ra với normalized, không phải tùy tiện so với before.
~~~

Đây là **đoạn minh họa**, không giả định mọi database/driver sẽ tự truncate. Nếu database round thay vì truncate, bản expected phải theo **quy tắc thực tế đã xác nhận**. Nhất thiết không chấp nhận một độ lệch lớn rồi gọi là "vẫn đủ chính xác" nếu yêu cầu nghiệp vụ là thứ tự giao dịch nanosecond.

### 10.3. Trường hợp giữ instant nhưng offset bị chuẩn hóa

~~~java
OffsetDateTime before =
        OffsetDateTime.parse(
                "2025-01-02T10:04:05.123456789+07:00");

OffsetDateTime normalized =
        before.withOffsetSameInstant(ZoneOffset.UTC);

boolean sameEvent = before.isEqual(normalized); // true
boolean sameValue = before.equals(normalized);  // false
~~~

Nếu contract chỉ giữ **mốc thực**, test `before.toInstant().equals(normalized.toInstant())` hoặc `isEqual` là phù hợp. Nếu contract yêu cầu **offset nguyên bản**, test như vậy **chưa đủ**; phải kiểm tra trường offset được giữ.

### 10.4. Bộ test cases tối thiểu

| Test case | Mục đích |
| --- | --- |
| Không có phần giây: `...:05Z` | Trường có zero nanos |
| `.100Z` | Giữ zero ở phần thập phân/biểu diễn đúng |
| `.123Z` | Millisecond |
| `.123456Z` | Microsecond |
| `.123456789Z` | Nanosecond |
| `.999999999Z` | Ranh giới đổi giây |
| `1969-12-31T23:59:59.999999999Z` | Epoch âm, phép chia/round |
| `+07:00` và `Z` cùng instant | Offset preservation |
| Local string không offset | Reject hoặc có quy tắc nhận rõ ràng |
| Timestamp nằm ngoài miền DB | Báo lỗi, không silent wrap |
| DB column precision nhỏ hơn input | Chính sách truncate/round được xác nhận |
| Ghi/đọc qua **driver thật** | Phát hiện hành vi mapping khác in-memory |

Nên chạy cùng bộ dữ liệu trên đường **Java → API → service khác → DB → Java** và kiểm tra quy tắc ở từng boundary.

## 11. Chương trình Java 8 hoàn chỉnh: bảo toàn và mất precision

Lưu thành **TimestampPrecisionDemo.java**. Chương trình không kết nối DB hay mạng; nó mô phỏng những phép chuyển thường xảy ra khi truyền/lưu. Sử dụng dữ liệu cố định nên stdout không phụ thuộc timezone mặc định, thời điểm thực hoặc môi trường.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;

public class TimestampPrecisionDemo {
    public static void main(String[] args) {
        Instant precise =
                Instant.parse("2025-01-02T03:04:05.123456789Z");

        OffsetDateTime plusSeven =
                precise.atOffset(ZoneOffset.ofHours(7));
        OffsetDateTime utc =
                plusSeven.withOffsetSameInstant(ZoneOffset.UTC);

        System.out.println("instant = " + precise);
        System.out.println("offset = " + plusSeven);
        System.out.println("UTC offset view = " + utc);
        System.out.println("same instant = "
                + plusSeven.toInstant().equals(utc.toInstant()));
        System.out.println("OffsetDateTime.equals = "
                + plusSeven.equals(utc));
        System.out.println("OffsetDateTime.isEqual = "
                + plusSeven.isEqual(utc));
        System.out.println("nano of second = " + precise.getNano());

        Instant micros = precise.truncatedTo(ChronoUnit.MICROS);
        Instant millis = precise.truncatedTo(ChronoUnit.MILLIS);
        System.out.println("truncate micros = " + micros);
        System.out.println("truncate millis = " + millis);
        System.out.println("lost nanos to micros = "
                + (precise.getNano() - micros.getNano()));
        System.out.println("lost nanos to millis = "
                + (precise.getNano() - millis.getNano()));

        Instant epochMilliRoundTrip =
                Instant.ofEpochMilli(precise.toEpochMilli());
        System.out.println("epoch millis roundtrip = "
                + epochMilliRoundTrip);
        System.out.println("epoch millis lossless = "
                + precise.equals(epochMilliRoundTrip));

        Instant pairRoundTrip =
                Instant.ofEpochSecond(
                        precise.getEpochSecond(), precise.getNano());
        System.out.println("seconds+nanos lossless = "
                + precise.equals(pairRoundTrip));

        String isoInstantText =
                DateTimeFormatter.ISO_INSTANT.format(precise);
        System.out.println("ISO instant roundtrip = "
                + precise.equals(Instant.parse(isoInstantText)));

        String offsetWire =
                plusSeven.format(
                        DateTimeFormatter.ISO_OFFSET_DATE_TIME);
        OffsetDateTime decoded =
                OffsetDateTime.parse(offsetWire);
        System.out.println("ISO offset roundtrip = "
                + plusSeven.equals(decoded));

        OffsetDateTime wrongChange =
                plusSeven.withOffsetSameLocal(ZoneOffset.UTC);
        System.out.println("same local changes instant = "
                + !precise.equals(wrongChange.toInstant()));

        Instant negative =
                Instant.parse("1969-12-31T23:59:59.999999999Z");
        System.out.println("negative epoch second = "
                + negative.getEpochSecond());
        System.out.println("negative nanos = " + negative.getNano());
        System.out.println("negative epoch millis = "
                + negative.toEpochMilli());

        Clock fixed = Clock.fixed(precise, ZoneOffset.UTC);
        System.out.println("fixed clock matches = "
                + Instant.now(fixed).equals(precise));
    }
}
~~~

Lệnh biên dịch với JDK 17+ nhưng khóa API và ngôn ngữ ở mức **Java 8**:

~~~bash
javac --release 8 TimestampPrecisionDemo.java
java TimestampPrecisionDemo
~~~

**Stdout chính xác:**

~~~text
instant = 2025-01-02T03:04:05.123456789Z
offset = 2025-01-02T10:04:05.123456789+07:00
UTC offset view = 2025-01-02T03:04:05.123456789Z
same instant = true
OffsetDateTime.equals = false
OffsetDateTime.isEqual = true
nano of second = 123456789
truncate micros = 2025-01-02T03:04:05.123456Z
truncate millis = 2025-01-02T03:04:05.123Z
lost nanos to micros = 789
lost nanos to millis = 456789
epoch millis roundtrip = 2025-01-02T03:04:05.123Z
epoch millis lossless = false
seconds+nanos lossless = true
ISO instant roundtrip = true
ISO offset roundtrip = true
same local changes instant = true
negative epoch second = -1
negative nanos = 999999999
negative epoch millis = -1
fixed clock matches = true
~~~

### 11.1. Đối chiếu các nhóm kết quả

1. `Instant` ban đầu có `.123456789`; chuyển sang `+07:00` đổi giờ từ `03:04` thành `10:04` mà vẫn bảo toàn instant.
2. Chuẩn hóa về UTC bằng `withOffsetSameInstant` giữ `Instant` nhưng thay offset, nên `OffsetDateTime.equals` là false còn `isEqual` là true.
3. `truncatedTo(MICROS)` giữ `.123456`, bỏ `789 ns`. `truncatedTo(MILLIS)` giữ `.123`, bỏ `456789 ns`.
4. `toEpochMilli` rồi `ofEpochMilli` cũng trở về `.123`, không thể tái tạo `.123456789`. Đó là **mất precision**, không phải chỉ thay đổi định dạng.
5. Cặp `getEpochSecond` + `getNano` tái tạo đúng giá trị bằng `ofEpochSecond`, nên lossless.
6. Chuỗi ISO của Instant và OffsetDateTime bảo toàn giá trị trong vòng encode/decode của ví dụ.
7. `withOffsetSameLocal(UTC)` giữ 10:04 đồng hồ nhưng gắn offset UTC, làm mốc thực lệch 7 giờ, vì vậy dòng `same local changes instant` là true.
8. Thời điểm âm `-1 ns` được biểu diễn bằng epochSecond `-1` + nano `999999999`; quy về milliseconds trả `-1`.
9. `Clock.fixed` dùng chính Instant đầu vào, nên `Instant.now(fixed)` bằng giá trị đã định, bất kể máy đang chạy ở timezone nào.

**Lưu ý phạm vi kiểm chứng:** chương trình chứng minh API Java và những phép chuyển in-memory. Nó **không thay thế test integration** trên database thực, driver thực và JSON serializer thực. Bài học quan trọng là phải kiểm chứng fidelity ở chính boundary hệ thống.

## 12. Kiến trúc lưu trữ: khi nào dùng UTC, khi nào giữ offset?

### 12.1. Event log, audit log, thanh toán

Thông thường điều nghiệp vụ quan tâm là **sự kiện đã xảy ra ở thời điểm nào** để sắp xếp hoặc đối chiếu trên timeline. Thiết kế hữu ích:

- Dùng `Instant` làm mô hình domain hoặc timestamp chuẩn UTC.
- Chọn wire format rõ, ví dụ ISO text `Z` hoặc cặp seconds+nanos.
- Chọn cột DB và precision theo yêu cầu thực tế; bảo đảm serializer/driver không làm đổi instant ngoài chính sách.
- Nếu cần hiển thị cho user, chuyển từ Instant sang `ZonedDateTime` tại một zone được chọn.

Không cần giữ mọi offset của từng request nếu offset đó không mang ý nghĩa nghiệp vụ. Nhưng nếu audit cần chứng minh dữ liệu gốc mà hệ thống nhận, có thể cần giữ cả raw payload hoặc offset gốc như metadata riêng.

### 12.2. Lịch hẹn theo địa phương

“Thứ Hai tới lúc 09:00 tại Paris” không giống “một Instant cố định đã chốt”. Nếu lịch có thể diễn ra ở vùng có DST:

- Lưu ngày và giờ local có nghĩa nghiệp vụ.
- Lưu **ZoneId** của địa điểm.
- Quy định cách xử lý DST gap/overlap và thay đổi quy tắc timezone.
- Chỉ chuyển sang Instant khi cần tạo lệnh thực thi/nhắc lịch, theo chính sách rõ.

Một `OffsetDateTime` đơn thuần lưu offset hiện có, **không** đủ làm quy tắc cho lịch lặp mỗi tuần qua các mùa nếu offset của vùng thay đổi.

### 12.3. Lịch sử nhập khẩu dữ liệu thiếu offset

Với dữ liệu cũ kiểu `2025-01-02 10:04:05.123` không có zone, đừng tự gắn `UTC` chỉ để làm schema đẹp. Phải biết cách hệ thống cũ đã định nghĩa timestamp và timezone môi trường lúc tạo. Nếu không biết, đánh dấu là dữ liệu không đủ thông tin hoặc đặt chính sách migration có kiểm toán.

Không thể khôi phục một offset đã mất chỉ từ `LocalDateTime`. Một ngày/giờ local có thể tương ứng nhiều Instant, hoặc không có Instant hợp lệ tại một zone có DST.

## 13. Những lỗi phổ biến và cách phòng tránh

### Lỗi 1 — Thấy Instant hỗ trợ 9 chữ số và kết luận clock đo đúng 1 ns

Không. Dung lượng biểu diễn khác độ chính xác nguồn vật lý. **Sửa:** tách yêu cầu nguồn clock, đồng bộ thời gian, dữ liệu và precision lưu.

### Lỗi 2 — Đổi Instant qua epochMillis rồi đòi equals nguyên bản

`toEpochMilli` mất phần nhỏ hơn ms. **Sửa:** chọn ISO text/cặp seconds+nanos hoặc chấp nhận, chuẩn hóa precision một cách tường minh.

### Lỗi 3 — Quên đơn vị timestamp numeric

Một API gửi seconds nhưng consumer coi là millis; cả hai đều dùng `long` nên compiler không phát hiện. **Sửa:** đặt tên field có đơn vị và thêm contract/schema validation.

### Lỗi 4 — Dùng epoch nanoseconds dưới dạng JavaScript Number

Số nano hiện đại vượt vùng integer an toàn. **Sửa:** dùng ISO string, cặp giây+nano hoặc chuỗi decimal với parser có kiểm soát.

### Lỗi 5 — Dùng double để ghép giây và nano

IEEE-754 không bảo toàn mọi phần nano khi giá trị giây lớn. **Sửa:** dùng integer pair, `BigDecimal` hoặc ISO text.

### Lỗi 6 — Cho rằng TIMESTAMP(6) lưu đủ nanosecond

Sáu chữ số phần giây thường chỉ tới microsecond. **Sửa:** xác minh kiểu cột và test round-trip với `.123456789`.

### Lỗi 7 — Nghĩ TIMESTAMP WITH TIME ZONE luôn giữ offset gốc

Một số DB chuẩn hóa về UTC. **Sửa:** nếu cần offset gốc, lưu field riêng và đối chiếu trên driver đang dùng.

### Lỗi 8 — Tự parse timestamp không offset như UTC

Một chuỗi local không đủ xác định Instant. **Sửa:** yêu cầu offset/zone, hoặc có quy tắc diễn giải được định nghĩa chính thức cho kênh dữ liệu.

### Lỗi 9 — Dùng format .SSSXXX rồi tưởng round-trip giữ nano

Formatter 3 chữ số không còn giữ `.123456789`. **Sửa:** dùng formatter ISO thích hợp hoặc contract precision rõ.

### Lỗi 10 — Dùng equals để so OffsetDateTime khi chỉ cần cùng Instant

Hai timestamp mang offset khác nhau nhưng cùng thời điểm có thể `equals == false`. **Sửa:** `toInstant().equals(...)` hoặc `isEqual(...)` để so mốc timeline.

### Lỗi 11 — Dùng withOffsetSameLocal để chuẩn hóa UTC

Đổi offset mà giữ đồng hồ local sẽ **đổi instant**. **Sửa:** `withOffsetSameInstant(ZoneOffset.UTC)`.

### Lỗi 12 — Kỳ vọng JSON serialization mặc định giống nhau ở mọi service

Cùng kiểu Java nhưng serializer/config khác có thể encode dưới dạng millis, chuỗi hoặc array. **Sửa:** chốt wire schema và integration tests giữa các phiên bản thật.

### Lỗi 13 — Không test năm trước 1970

Quy tắc cắt chia số âm có thể tạo sai lệch một millisecond hoặc một giây. **Sửa:** test `1969-12-31T23:59:59.999999999Z` và các mốc biên âm.

### Lỗi 14 — Tạo ID duy nhất chỉ từ timestamp

Ngay cả Instant có nano precision, đồng hồ không bảo đảm không trùng giữa nhiều sự kiện/thread/máy. **Sửa:** dùng ID chuyên dụng (UUID/sequence) và chỉ dùng timestamp như một thuộc tính thời gian.

### Lỗi 15 — Dùng đồng hồ tường (wall clock) để đo latency

Clock hệ thống có thể bị chỉnh hoặc đồng bộ lại. **Sửa:** khi đo **khoảng thời gian trôi qua trong một tiến trình**, dùng nguồn monotonic như `System.nanoTime()` để tính hiệu số; nó **không phải epoch timestamp**.

### Lỗi 16 — Trộn trường “đã xảy ra lúc” với “giờ hẹn địa phương”

`Instant` thích hợp cho sự kiện đã xảy ra; lịch trong một vùng có thể cần `LocalDateTime + ZoneId`. **Sửa:** mô hình hóa theo semantics, không tự chuyển mọi trường thành `Instant` rồi mất ngữ nghĩa lịch.

### Lỗi 17 — Rounding/truncation không nhất quán giữa service và DB

Một bên truncate `.123456789` thành `.123456`, bên khác round thành `.123457`. **Sửa:** xác định policy tại boundary, kiểm thử cả hai chiều và ví dụ sát biên.

### Lỗi 18 — Dựa vào thứ tự chuỗi format tùy ý để so thời gian

Chuỗi có offset khác nhau có thể sắp theo text không tương ứng thứ tự Instant thực. **Sửa:** parse rồi so `Instant`; nếu cần lexicographic order, chuẩn hóa cùng một format UTC và precision trước, đồng thời xác minh contract của định dạng.

## 14. Checklist thiết kế API/database cho timestamp

Trước khi phát hành, trả lời lần lượt:

1. Timestamp là **Instant thực** hay ngày/giờ local theo lịch?
2. Có cần **offset đã gửi**, region `ZoneId`, cả hai, hay chỉ cần Instant?
3. Đơn vị thời gian khi truyền là gì?
4. Số chữ số phần giây tối đa, tối thiểu và có cho phép thiếu fraction không?
5. Hệ thống nào quyết định nguồn thời gian? Clock có được đồng bộ không?
6. Khi format ra text, có dùng ISO-8601/RFC 3339 với offset rõ không?
7. Nếu truyền numeric, client có giữ chính xác số nguyên trong miền không?
8. Database column có hỗ trợ precision yêu cầu không?
9. Driver có hỗ trợ `java.time` type/SQL mapping dự kiến không?
10. Có bước ORM/JDBC/serializer nào đổi precision hoặc timezone tự động không?
11. Nếu precision không đủ, **round hay truncate**, tại boundary nào?
12. Dữ liệu âm trước epoch và ranh giới giây có được test không?
13. Round-trip **Instant** có bằng nhau không, và **offset gốc** có cần bằng nhau không?
14. Integration tests có chạy trên phiên bản DB/driver/serializer thật không?
15. Có bảo đảm backward compatibility khi đổi đơn vị/format timestamp không?
16. Có ghi rõ timezone mặc định không được tự suy diễn nếu payload thiếu offset không?
17. Có cần quy tắc cho sự kiện gần đồng thời, ordering, deduplication hay unique ID không?
18. Việc audit dữ liệu gốc có yêu cầu giữ raw string/source offset ngoài timestamp chuẩn không?

### 14.1. Ví dụ hợp đồng API ngắn gọn, có thể triển khai

**Đề xuất cho sự kiện có timeline tuyệt đối và cần tới microsecond:**

~~~text
Field: occurredAt
Meaning: absolute instant of the event
Wire: RFC 3339/ISO-8601 string with UTC "Z"
Max fractional precision: 6 decimal digits
Normalization: truncate to microsecond at ingestion boundary
Validation: reject timestamp without zone/offset
Storage: database column/driver proven to preserve 6 digits
Round-trip assertion: decoded == original.truncatedTo(MICROS)
Original offset: not retained unless supplied separately
~~~

Đây là **một hợp đồng minh họa**, không phải quy định bắt buộc cho mọi hệ thống. Nếu cần nanosecond, thay đổi wire/storage/verification tương ứng và chứng minh tất cả thành phần đi qua giữ được 9 chữ số.

### 14.2. Khi có dữ liệu ngoài ngưỡng đã hứa

Nếu API hứa tối đa 6 chữ số nhưng nhận chuỗi 9 chữ số, có ba chính sách hợp lệ tùy sản phẩm:

- **Reject** và giải thích precision không được hỗ trợ.
- **Normalize** theo quy tắc đã công bố, rồi trả lại giá trị chuẩn hóa.
- **Giữ nguyên chính xác** nếu thực sự nâng cấp toàn bộ pipeline và version hóa contract.

Không âm thầm mất dữ liệu trong khi API mô tả “timestamp được bảo toàn chính xác”.

## 15. Bài tập tự kiểm tra và đáp án

**Câu 1.** `Instant.parse("2025-01-02T03:04:05.123456789Z")` lưu bao nhiêu chữ số phần giây?  
**Đáp án:** Chín chữ số, tương đương nanosecond của giây; không chứng minh clock vật lý đo được 1 ns.

**Câu 2.** `.123456789` khi truncate về microsecond trở thành gì?  
**Đáp án:** `.123456`; mất `789 ns`.

**Câu 3.** Cùng giá trị khi truncate về millisecond?  
**Đáp án:** `.123`; mất `456789 ns`.

**Câu 4.** Vì sao `Instant.ofEpochMilli(instant.toEpochMilli())` có thể khác `instant`?  
**Đáp án:** Vì epoch millis chỉ giữ tới 1/1000 giây, bỏ phần nano nhỏ hơn milli.

**Câu 5.** Muốn lossless tới nano, có thể dùng cặp số nào?  
**Đáp án:** `getEpochSecond()` cùng `getNano()` với schema và miền giá trị rõ; dựng lại bằng `Instant.ofEpochSecond(...)`.

**Câu 6.** Hai `OffsetDateTime` có cùng Instant nhưng khác offset thì `equals` có luôn true không?  
**Đáp án:** Không. Dùng `isEqual` hoặc so `toInstant()` nếu chỉ cần cùng mốc thời gian thực.

**Câu 7.** Một timestamp `2025-01-02T10:04:05` không offset có đủ làm timestamp UTC không?  
**Đáp án:** Không. Phải biết zone/offset hoặc có quy tắc nhận được định nghĩa chính thức.

**Câu 8.** `TIMESTAMP WITH TIME ZONE` có chắc giữ `+07:00` sau round-trip không?  
**Đáp án:** Không. Một số hệ quản trị/driver chuẩn hóa về UTC; phải xác minh và lưu metadata riêng nếu cần.

**Câu 9.** `long epochNanos` có thể biểu diễn mọi `Instant` không?  
**Đáp án:** Không, miền `long` khi đo bằng nanosecond nhỏ hơn miền mà `Instant` hỗ trợ.

**Câu 10.** Epoch timestamp tính bằng nanosecond quanh hiện tại truyền dưới dạng JavaScript Number có chắc chính xác không?  
**Đáp án:** Không. Giá trị thường vượt `2^53-1`; dùng string, cặp số hoặc cấu trúc integer có chủ đích.

**Câu 11.** Một timestamp `-1 ns` từ epoch có `getEpochSecond()` và `getNano()` là gì?  
**Đáp án:** `-1` và `999999999`, không phải `0` và `-1`.

**Câu 12.** Tại sao cần test trên database thật dù unit test ISO parser trong Java đã pass?  
**Đáp án:** Vì cột SQL, driver hoặc ORM có thể làm giảm precision, round/truncate hoặc chuẩn hóa timezone.

**Câu 13.** Mẫu `SSS` trong formatter có bảo toàn `123456789` nano không?  
**Đáp án:** Không. Mẫu đó chỉ ghi ba chữ số phần giây; để giữ đủ nano nên chọn format/schema phù hợp.

**Câu 14.** Với sự kiện audit cần cùng instant, nên lưu bằng Java `LocalDateTime` hay `Instant`?  
**Đáp án:** `Instant` thường hợp nghĩa hơn vì nó xác định một thời điểm thực, không phụ thuộc múi giờ được suy đoán ở nơi đọc.

**Câu 15.** Nếu hẹn lịch “09:00 thứ Hai tại Paris” lặp hằng tuần thì một `Instant` hoặc `+01:00` cố định đã đủ chưa?  
**Đáp án:** Không nhất thiết; cần ngày giờ local và region `ZoneId` để xét quy tắc mùa/đổi giờ ở từng tuần.

**Câu 16.** Dùng `System.nanoTime()` để tạo timestamp gửi API được không?  
**Đáp án:** Không. Nó là nguồn thời gian monotonic/relative để đo chênh lệch trong tiến trình, không biểu diễn thời điểm UTC theo epoch.

## 16. Tổng kết

- **`Instant` lưu giây epoch + nanosecond-of-second**, biểu diễn thời điểm đến độ phân giải nanosecond; đừng nhầm với độ đúng của đồng hồ thật.
- **`OffsetDateTime` lưu ngày/giờ và offset**, có thể diễn giải thành cùng Instant với một OffsetDateTime khác. Giữ Instant **không đồng nghĩa giữ offset gốc**.
- **`toEpochMilli` làm mất precision dưới millisecond.** Một `long epoch nanoseconds` không đủ cho toàn miền `Instant`; numeric JSON trên JavaScript cũng cần chú ý độ chính xác số nguyên.
- **ISO-8601 timestamp có offset** là lựa chọn wire rõ nghĩa; số chữ số phần giây cần được ghi thành hợp đồng thay vì suy đoán từ format.
- **SQL/JDBC không có precision hay timezone behavior thống nhất trên mọi database.** Kiểm tra driver, column type và round-trip tại đúng boundary.
- **Truncate và round khác nhau**; với microsecond/millisecond phải công khai và kiểm thử chính sách, nhất là trước epoch và sát ranh giới giây.
- **`OffsetDateTime.isEqual` so cùng Instant**, còn `equals` xét cả local time và offset.
- **Tách thời điểm thực khỏi lịch địa phương.** Lịch hẹn lâu dài cần `LocalDateTime` và `ZoneId`/quy tắc tương ứng khi dùng múi giờ vùng.
- **Round-trip test** phải xác định rõ bảo toàn instant, precision và offset nào, thay vì chỉ kiểm tra chuỗi parse thành công.
- Kiến thức chính trong bài dựa trên `java.time`/JDBC hiện hành, không dựa vào các API ngày giờ cũ đã lỗi thời.

### Tài liệu chính thức và hướng dẫn triển khai

- [Oracle Java SE 8 — Instant](https://docs.oracle.com/javase/8/docs/api/java/time/Instant.html)
- [Oracle Java SE 26 — Instant: epoch-second, nanos, toEpochMilli](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html)
- [Oracle Java SE 8 — OffsetDateTime](https://docs.oracle.com/javase/8/docs/api/java/time/OffsetDateTime.html)
- [Oracle Java SE 26 — OffsetDateTime: equals, isEqual, offset conversions](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/OffsetDateTime.html)
- [Oracle Java SE 8 — DateTimeFormatter](https://docs.oracle.com/javase/8/docs/api/java/time/format/DateTimeFormatter.html)
- [Oracle Java SE 26 — Clock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html)
- [pgJDBC — Java 8 date and time support and mapping](https://jdbc.postgresql.org/documentation/query/#using-java-8-date-and-time-classes)
