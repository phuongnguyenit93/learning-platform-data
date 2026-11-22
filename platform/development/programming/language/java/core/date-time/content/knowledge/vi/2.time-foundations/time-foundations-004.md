# Mốc epoch và dấu thời gian trước, sau epoch trong Java

Trong lập trình ngày giờ, một *timestamp* dùng để chỉ một thời điểm trên trục thời gian. Để hai hệ thống có thể trao đổi và so sánh thời điểm mà không phụ thuộc cách hiển thị ngày giờ, chúng thường đếm thời gian từ một mốc quy ước: **epoch**.

## 1. Epoch là mốc gì?

**Unix epoch / Java epoch** là thời điểm **1970-01-01T00:00:00Z**, tức 00:00:00 ngày 01/01/1970 theo UTC. Chữ `Z` trong ISO 8601 chỉ UTC, tương đương độ lệch `+00:00`.

- **Đúng epoch**: timestamp bằng `0`.
- **Sau epoch**: timestamp dương.
- **Trước epoch**: timestamp âm. Giá trị âm là hợp lệ, không mặc nhiên có nghĩa là dữ liệu sai.
- **Đơn vị là một phần của hợp đồng dữ liệu**: `-1` giây, `-1` mili giây và `-1` micro giây đại diện ba thời điểm khác nhau.

~~~text
                        mốc epoch
 ... 1969-12-31           1970-01-01             1970-01-02 ...
         trước <-------------|-------------> sau
     epoch second âm          0          epoch second dương
~~~

Mốc epoch **không phải ngày Java ra đời**, không phải giờ địa phương và không tự thay đổi theo múi giờ máy tính. Chỉ có cách biểu diễn hoặc diễn giải ngày giờ tại một múi giờ là thay đổi.

**Phân biệt:** *epoch* là mốc gốc; *epoch second* là số giây tính từ mốc; *epoch millisecond* là số mili giây tính từ mốc; *timestamp* là giá trị biểu diễn một thời điểm, có thể ở dạng số hoặc chuỗi ngày giờ kèm thông tin múi giờ.

## 2. Một vài thời điểm ngay sát epoch

| Thời điểm UTC | Epoch seconds (phần nguyên) | Epoch milliseconds |
|---|---:|---:|
| `1969-12-31T23:59:59Z` | `-1` | `-1000` |
| `1969-12-31T23:59:59.999Z` | `-1` | `-1` |
| `1970-01-01T00:00:00Z` | `0` | `0` |
| `1970-01-01T00:00:00.001Z` | `0` | `1` |
| `1970-01-01T00:00:01Z` | `1` | `1000` |

Với thời điểm `1969-12-31T23:59:59.999Z`, khoảng cách đến epoch chỉ là **1 mili giây**, nên epoch milliseconds bằng `-1`. Trong khi đó, cách Java tách thời điểm thành *epoch seconds* và *nano-of-second* cho giá trị `-1` giây kèm `999_000_000` nano giây: `-1 + 0,999 = -0,001` giây. Phần nguyên giây dùng quy tắc làm tròn xuống theo trục thời gian, không phải cắt phần thập phân về 0.

### Các đơn vị thường gặp

| Đơn vị | Ký hiệu thường gặp | Một giây tương ứng |
|---|---|---:|
| Giây | `epochSeconds`, Unix time | `1` |
| Mili giây | `epochMillis` | `1_000` |
| Micro giây | `epochMicros` | `1_000_000` |
| Nano giây | `epochNanos` | `1_000_000_000` |

Tên trường như `timestamp` **không cho biết đơn vị**. Phải xác nhận từ hợp đồng API, tài liệu DB, định dạng lưu trữ hoặc kiểu dữ liệu. Không đoán đơn vị bằng cách chỉ nhìn số chữ số, đặc biệt với thời điểm trước epoch hoặc rất xa epoch.

## 3. Biểu diễn thời điểm bằng `java.time.Instant`

Trong Java 17+, `Instant` đại diện cho **một điểm trên trục thời gian**, không gắn trực tiếp với giờ địa phương. Đây là kiểu phù hợp cho thời điểm tạo bản ghi, xảy ra sự kiện, audit log và so sánh thời gian.

Các API chính:

| Nhu cầu | API | Ý nghĩa |
|---|---|---|
| Lấy mốc chuẩn | `Instant.EPOCH` | `1970-01-01T00:00:00Z` |
| Từ số giây | `Instant.ofEpochSecond(seconds)` | Xây dựng `Instant` theo giây |
| Từ giây và nano | `Instant.ofEpochSecond(seconds, nanoAdjustment)` | Thêm độ chính xác dưới giây, tự chuẩn hóa |
| Từ mili giây | `Instant.ofEpochMilli(millis)` | Nhận giá trị trước/sau epoch, kể cả âm |
| Lấy giây | `instant.getEpochSecond()` | Số giây của khoảng một giây chứa `instant` |
| Lấy nano trong giây | `instant.getNano()` | Luôn trong `0..999_999_999` |
| Lấy mili giây | `instant.toEpochMilli()` | Giá trị epoch milliseconds; mất độ chính xác nhỏ hơn 1 ms |
| Đọc ISO 8601 | `Instant.parse("1969-12-31T23:59:59Z")` | Chuỗi cần độ lệch/UTC phù hợp |
| So sánh | `isBefore`, `isAfter`, `compareTo` | So theo thời điểm thực |
| Tính khoảng cách | `Duration.between(a, b)` | Khoảng thời gian từ `a` đến `b` |

`Instant` có cấu trúc khái niệm gồm `long epochSecond` và `int nanoOfSecond`. Chẳng hạn:

~~~text
Instant: 1969-12-31T23:59:59.500Z
epochSecond = -1
nanoOfSecond = 500_000_000
tổng số giây tương đối với epoch = -0,5 s
~~~

Điều này giải thích vì sao không thể dùng phép chia nguyên thông thường `-1 / 1000` rồi coi đó là epoch second: phép chia nguyên của Java làm tròn **về 0**, cho `0`, trong khi giây chứa `-1 ms` phải là `-1`.

`Instant.ofEpochSecond` có thể nhận cả `nanoAdjustment` âm hoặc vượt một tỷ rồi **chuẩn hóa** về `getNano()` nằm trong `0..999_999_999`. Ví dụ, `Instant.ofEpochSecond(0, -1_000_000)` chính là `Instant.ofEpochMilli(-1)`.

## 4. Ví dụ Java 17 chạy độc lập

Tạo tệp **`EpochDemo.java`**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;

public class EpochDemo {
    public static void main(String[] args) {
        Instant before = Instant.parse("1969-12-31T23:59:59.999Z");
        Instant epoch = Instant.EPOCH;
        Instant after = Instant.parse("1970-01-01T00:00:00.001Z");

        System.out.println("before ms = " + before.toEpochMilli());
        System.out.println("epoch ms = " + epoch.toEpochMilli());
        System.out.println("after ms = " + after.toEpochMilli());
        System.out.println("before seconds = " + before.getEpochSecond());
        System.out.println("before nanos = " + before.getNano());

        System.out.println("from -1 ms = " + Instant.ofEpochMilli(-1));
        System.out.println("from -0.5 s = "
                + Instant.ofEpochSecond(-1, 500_000_000));
        System.out.println("distance = "
                + Duration.between(before, after).toMillis() + " ms");

        System.out.println("epoch in +07:00 = "
                + epoch.atOffset(ZoneOffset.ofHours(7)));

        LocalDateTime local = LocalDateTime.of(1970, 1, 1, 0, 0);
        System.out.println("local with UTC = "
                + local.toEpochSecond(ZoneOffset.UTC));
        System.out.println("local with +07:00 = "
                + local.toEpochSecond(ZoneOffset.ofHours(7)));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac EpochDemo.java
java EpochDemo
~~~

Đầu ra đã kiểm chứng khi biên dịch với `--release 17`:

~~~text
before ms = -1
epoch ms = 0
after ms = 1
before seconds = -1
before nanos = 999000000
from -1 ms = 1969-12-31T23:59:59.999Z
from -0.5 s = 1969-12-31T23:59:59.500Z
distance = 2 ms
epoch in +07:00 = 1970-01-01T07:00+07:00
local with UTC = 0
local with +07:00 = -25200
~~~

**Giải thích:** `before` và `after` nằm hai phía của epoch, cách nhau 2 ms. `-1 ms` được Java chuẩn hóa thành `-1 epoch second` cộng `999_000_000 ns`. Chuyển epoch sang độ lệch `+07:00` chỉ đổi **cách hiển thị** thành 07:00, không đổi timestamp `0`. Ngược lại, khi *diễn giải* cùng một `LocalDateTime` 00:00 ở `+07:00`, thời điểm thực tương ứng `1969-12-31T17:00:00Z`, tức `-25_200` giây so với epoch.

## 5. Epoch và múi giờ: hai câu hỏi khác nhau

Hãy phân biệt:

1. **Thời điểm nào đã xảy ra?** Dùng `Instant` hoặc timestamp kèm đơn vị: câu trả lời có thể so sánh giữa các máy và múi giờ.
2. **Đồng hồ địa phương hiển thị bao nhiêu?** Kết hợp `Instant` với `ZoneId` (múi giờ có quy tắc lịch sử/DST) hoặc `ZoneOffset` (độ lệch cố định).

Ví dụ, **cùng một thời điểm**:

~~~text
1970-01-01T00:00:00Z       (UTC)
1970-01-01T07:00:00+07:00  (độ lệch +07:00)
epoch milliseconds = 0     (cả hai)
~~~

`LocalDateTime` chỉ có năm, tháng, ngày, giờ, phút, giây, **không lưu múi giờ hay offset**. Vì vậy không thể suy ra epoch timestamp duy nhất từ `LocalDateTime` nếu chưa biết cách diễn giải offset hoặc `ZoneId`. Tương tự, `LocalDate` chỉ biểu diễn ngày lịch; để tìm thời điểm đầu ngày phải chỉ rõ múi giờ, và ở một số vùng có thay đổi đồng hồ, đầu ngày không nhất thiết là 00:00.

Khi làm việc với một địa điểm thực, ưu tiên `ZoneId.of("Asia/Ho_Chi_Minh")` hoặc một mã vùng phù hợp vì quy tắc lịch sử có thể khác độ lệch hiện tại. Ví dụ `+07:00` ở trên là **độ lệch cố định** để tính toán dễ kiểm chứng; không nên mặc định rằng một vùng địa lý luôn có offset đó ở mọi thời điểm lịch sử.

## 6. Xử lý timestamp âm và đổi đơn vị an toàn

Với timestamp mili giây âm, dùng `Instant.ofEpochMilli(...)` là cách trực tiếp và an toàn. Nếu cần **tách** mili giây thành giây + nano, dùng `Math.floorDiv` và `Math.floorMod` để duy trì phần dư không âm.

Đoạn sau là **mã minh họa đặt bên trong một phương thức**, không phải tệp Java độc lập:

~~~java
long epochMillis = -1L;
long seconds = Math.floorDiv(epochMillis, 1_000L);    // -1
long millisInSecond = Math.floorMod(epochMillis, 1_000L); // 999
Instant restored = Instant.ofEpochSecond(
        seconds, millisInSecond * 1_000_000L);
// restored = 1969-12-31T23:59:59.999Z
~~~

Tương tự, nếu API cung cấp **micro giây**:

~~~java
long epochMicros = -1L;
long seconds = Math.floorDiv(epochMicros, 1_000_000L);
long microsInSecond = Math.floorMod(epochMicros, 1_000_000L);
Instant instant = Instant.ofEpochSecond(
        seconds, microsInSecond * 1_000L);
// instant = 1969-12-31T23:59:59.999999Z
~~~

Nếu cần từ `Instant` về micro giây, phải tính với kiểm tra tràn số, ví dụ `Math.addExact(Math.multiplyExact(instant.getEpochSecond(), 1_000_000L), instant.getNano() / 1_000)`. Biểu thức này làm tròn xuống đến micro giây theo trục thời gian; dữ liệu dưới micro giây sẽ mất. Khi chuyển sang mili giây, `toEpochMilli()` cũng giảm độ chính xác. Với timestamp rất xa, phép đổi ra `long` mili giây/micro giây có thể tràn và ném `ArithmeticException`.

**Tránh mẹo chia nhân bừa:** `-1 / 1000 == 0` trong Java và `0 * 1000` không thể khôi phục `-1 ms`; phần dư `-1 % 1000 == -1` cũng không phải nano-of-second hợp lệ cho `Instant`. Hãy dùng API sẵn có hoặc `floorDiv`/`floorMod` khi phải tách đơn vị thủ công.

## 7. Áp dụng thực tế và kiểm tra dữ liệu

### Trao đổi qua API hoặc lưu database

- Với một thời điểm xảy ra sự kiện, có thể truyền ISO 8601 có offset rõ ràng, ví dụ `"1969-12-31T23:59:59.999Z"`, rồi đọc thành `Instant`.
- Nếu truyền số nguyên, hợp đồng phải ghi **đơn vị**, ví dụ `createdAtEpochMillis: -1`; đừng đặt chung chung `createdAt: -1` nếu phía nhận không biết đơn vị.
- Kiểu `long` Java cho epoch seconds/millis thông thường. Với dữ liệu trước năm 1970, database, JSON schema và phía frontend phải chấp nhận **số âm**; không tự coi mọi timestamp âm là lỗi.
- Lưu `Instant`/UTC cho thời điểm thực khi phù hợp; áp dụng múi giờ để trình bày theo nhu cầu người dùng. Ngày thuần túy như ngày sinh hoặc ngày hết hạn theo lịch cần cân nhắc `LocalDate` thay vì ép thành timestamp.
- Dữ liệu lịch sử trước epoch có thể xuất hiện trong ngày sinh, sự kiện lưu trữ, hồ sơ nhập từ hệ thống cũ và backfill; test dữ liệu ở cả ba trường hợp **âm, bằng 0, dương**.

### Những lỗi rất dễ gặp

| Lỗi | Vì sao sai / cách sửa |
|---|---|
| Coi số âm là không hợp lệ | Timestamp âm biểu diễn thời điểm trước 01/01/1970 UTC; chỉ từ chối khi hợp đồng dữ liệu thực sự cấm |
| Trộn giây và mili giây | `Instant.ofEpochSecond(-1)` là trước epoch 1 giây, còn `ofEpochMilli(-1)` là trước epoch 1 mili giây |
| Chia nguyên khi timestamp âm | `-1 / 1000 = 0`; dùng `Instant.ofEpochMilli` hoặc `Math.floorDiv`/`floorMod` |
| Cho rằng `getNano()` âm trước epoch | `getNano()` luôn `0..999_999_999`; dấu nằm ở `getEpochSecond()` |
| Gắn múi giờ mặc định máy vào giá trị UTC | Dễ lệch giờ; parse offset rõ ràng và dùng `Instant` khi lưu thời điểm |
| Chuyển `LocalDateTime` thành epoch mà thiếu offset | Một giá trị giờ địa phương có thể ứng với các instant khác nhau; cần `ZoneId`/`ZoneOffset` |
| Dùng `int` cho epoch milliseconds | Dải `int` quá nhỏ; dùng `long` và kiểm tra hợp đồng giữa các hệ thống |
| Nghĩ `toEpochMilli()` giữ nguyên nano | Độ chính xác dưới 1 ms bị mất; giữ `Instant` nếu cần nano giây |
| Dựa vào `System.nanoTime()` làm Unix timestamp | `nanoTime()` dùng đo khoảng thời gian, có mốc tùy ý, không phải mốc 1970 |
| Nghĩ đồng hồ hệ điều hành luôn tiến đều | `Instant.now()`/`currentTimeMillis()` theo đồng hồ tường có thể điều chỉnh; để đo thời lượng chạy tác vụ, dùng `System.nanoTime()` |

## 8. Bài tự kiểm tra

1. `1969-12-31T23:59:59Z` có epoch seconds bao nhiêu? **`-1`**, vì sớm hơn epoch đúng một giây.
2. `Instant.ofEpochMilli(-1).getNano()` trả bao nhiêu? **`999_000_000`**; epoch second đi kèm là `-1`.
3. Hai chuỗi `1970-01-01T00:00:00Z` và `1970-01-01T07:00:00+07:00` có cùng timestamp không? **Có**, cùng thời điểm epoch `0`.
4. `LocalDateTime.of(1970, 1, 1, 0, 0)` có chắc là epoch `0` không? **Không**; theo UTC là `0`, theo `+07:00` là `-25_200` giây.
5. Nếu nhận số `-1` từ API, đã đủ biết thời điểm chưa? **Chưa**, cần xác nhận đơn vị (giây, mili giây, micro giây...) và ý nghĩa của trường.

**Ghi nhớ:** Mốc epoch cố định tại `1970-01-01T00:00:00Z`; trước mốc là timestamp âm, sau mốc là dương. Trong Java, hãy ưu tiên `Instant` cho thời điểm thực, luôn xác định đúng đơn vị, và xử lý phân số âm bằng quy tắc chuẩn hóa của `Instant`.

### Tài liệu tham khảo

- [Java SE 17 — `Instant`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
- [Java SE 17 — gói `java.time`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html)
- [Java SE 17 — `ZonedDateTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html)
