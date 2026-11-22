# Thang thời gian Java và giới hạn biểu diễn giây nhuận

Khi lưu timestamp bằng `Instant`, Java cung cấp một trục thời gian thuận tiện để ghi log, sắp xếp sự kiện và tính khoảng cách giữa hai thời điểm. Tuy nhiên, **một giây trên trục thời gian Java không đồng nghĩa tuyệt đối với một giây SI trong mọi tình huống**, đặc biệt vào thời điểm có **giây nhuận (leap second)**. Hiểu giới hạn này giúp tránh các giả định sai trong hệ thống cần độ chính xác rất cao.

Bài học tập trung vào khái niệm Java Time-Scale, mối quan hệ với UTC, cách API `java.time` biểu diễn và parse dữ liệu chứa giây thứ 60, cũng như cách thiết kế chương trình khi dữ liệu đầu vào có thể chứa leap second.

## 1. Vì sao tồn tại nhiều thang thời gian?

Một **thang thời gian (time scale)** quy định cách đánh số và đo các thời điểm liên tiếp. Các khái niệm thường gặp:

| Khái niệm | Vai trò | Lưu ý |
| --- | --- | --- |
| **Giây SI** | Đơn vị vật lý được xác định theo chuẩn nguyên tử | Là cơ sở cho đo thời gian vật lý chính xác |
| **TAI** (International Atomic Time) | Thang thời gian nguyên tử quốc tế, không chèn giây nhuận như UTC | Phù hợp với bài toán cần đếm giây nguyên tử liên tục, khi có dữ liệu và quy tắc chuyển đổi thích hợp |
| **UT1** | Thang thời gian bám theo chuyển động quay thực tế của Trái Đất | Không đều theo chuẩn SI; được xác định bằng quan trắc |
| **UTC** (Coordinated Universal Time) | Chuẩn thời gian dân dụng phối hợp với chuyển động Trái Đất | Có cơ chế giây nhuận để giữ quan hệ với UT1 |
| **Java Time-Scale** | Mô hình thời gian được `java.time` định nghĩa | Mỗi ngày lịch được chia thành đúng **86.400 giây Java danh nghĩa** |

**UTC và múi giờ không phải một khái niệm.** UTC là chuẩn thời gian; `+07:00` là độ lệch (offset) của biểu diễn giờ địa phương so với UTC. Quy tắc daylight saving time (DST) thay đổi giờ hiển thị ở vùng địa lý; leap second điều chỉnh sự khác biệt giữa đồng hồ nguyên tử và sự quay của Trái Đất. Cần xử lý hai vấn đề riêng.

### 1.1. Giây nhuận là gì?

Theo cách đánh số giờ–phút–giây của UTC, một ngày bình thường có các giây từ `00:00:00` đến `23:59:59`, tức 86.400 giây. Khi cơ quan quản lý thời gian quyết định **chèn một giây nhuận dương**, cuối ngày UTC có thêm nhãn `23:59:60` trước khi sang `00:00:00` hôm sau. Về mặt vật lý, ngày ấy gồm **86.401 giây SI**.

Ví dụ thực tế, cuối ngày **2016-12-31 UTC** có một giây nhuận dương:

```text
UTC (có giây nhuận dương)
2016-12-31T23:59:58Z
2016-12-31T23:59:59Z
2016-12-31T23:59:60Z   <- giây nhuận
2017-01-01T00:00:00Z
```

Về nguyên tắc UTC cũng cho phép giây nhuận âm, tức bỏ qua một nhãn giây để một ngày có 86.399 giây SI. Điều này là **khả năng của mô hình UTC**, không có nghĩa cứ mỗi năm lại có giây nhuận hoặc cứ cuối tháng 6/12 sẽ chèn một giây. Việc một ngày cụ thể có leap second phải dựa trên thông báo/dữ liệu chính thức; không suy ra chỉ bằng công thức lịch.

**Đừng nhầm giây nhuận với ngày nhuận:** ngày 29/2 trong lịch Gregory được xử lý bởi `LocalDate`, hoàn toàn khác sự kiện UTC thêm/bớt một giây.

## 2. Java Time-Scale: ngày luôn có 86.400 giây danh nghĩa

Đặc tả của `java.time.Instant` định nghĩa **Java Time-Scale** riêng để ứng dụng có biểu diễn nhất quán. Trên thang này, mỗi ngày lịch có đúng **86.400 phân đoạn được gọi là giây**, dù một ngày UTC có giây nhuận. Giây danh nghĩa của Java vì thế **có thể khác giây SI** ở vùng quanh sự kiện leap second.

Đặc tả chia trục thời gian thành các giai đoạn:

1. **Trước mốc chuyển tiếp năm 1972:** áp dụng mô hình dựa trên **UT1** một cách kéo dài về quá khứ (*proleptic*).
2. **Từ giai đoạn bắt đầu quanh 1972-11-03:** áp dụng **UTC-SLS** (*UTC Smoothed Leap Seconds*) làm định nghĩa quan hệ với UTC. Điểm ranh giới chính xác được mô tả bằng thời điểm UT1 = UTC trong khoảng 1972-11-03 đến 1972-11-04, thay vì đơn giản xem 00:00 ngày 03/11 là mốc tuyệt đối.

### 2.1. UTC-SLS xử lý giây nhuận như thế nào?

Trên **ngày không có giây nhuận**, Java Time-Scale và UTC trùng nhau. Trên ngày UTC có leap second, UTC-SLS phân bố ảnh hưởng của giây chèn/bớt **đều trong 1.000 giây cuối ngày**, thay vì thể hiện nhãn giây `60` riêng biệt. Cách “làm mượt” này giữ hình thức **86.400 giây Java mỗi ngày**.

Hình dung:

```text
Ngày UTC bình thường:  86.400 giây SI
Ngày UTC leap dương:   86.401 giây SI (có 23:59:60)
Java Time-Scale:       luôn 86.400 giây Java danh nghĩa/ngày
UTC-SLS:               làm mượt khác biệt ở 1.000 giây cuối ngày leap
```

**Phạm vi bảo đảm rất quan trọng:** tài liệu `Instant` mô tả UTC-SLS ở mức **mô hình/đặc tả**, nhưng **không yêu cầu mọi đồng hồ hệ thống của Java thực sự triển khai bước làm mượt UTC-SLS**, không bắt buộc có độ chính xác dưới giây, cũng không bảo đảm đồng hồ chạy đơn điệu hoặc trơn tru. Vì vậy:

- Có thể dựa vào cấu trúc và phép toán của các kiểu `java.time`, nhưng **không suy ra** `Instant.now()` luôn báo thời điểm thực với độ chính xác nano giây.
- Không giả định JVM hoặc hệ điều hành của bạn sẽ tự thực hiện “smear” đúng 1.000 giây, hoặc nhận biết lịch leap second.
- Nếu phải đối chiếu dấu thời gian gần giây nhuận ở mức milli/micro/nano giây, cần biết chính sách và nguồn đồng bộ đồng hồ thực tế (hệ điều hành, NTP, nguồn thời gian, hạ tầng đo).

Nói cách khác, **đặc tả thang thời gian** và **chất lượng nguồn đồng hồ đang dùng** là hai lớp bảo đảm khác nhau.

## 3. `Instant`, `LocalTime` và giới hạn biểu diễn giây thứ 60

### 3.1. `Instant` chứa gì?

Một `Instant` chứa:

- `epochSecond` kiểu `long`: số giây trên trục Java kể từ epoch `1970-01-01T00:00:00Z`;
- `nano` kiểu `int`: phần nano giây của giây hiện tại, trong khoảng **0 đến 999.999.999**.

`Instant` hỗ trợ độ phân giải biểu diễn đến nano giây, nhưng đó **không phải cam kết độ chính xác nano giây của đồng hồ máy**. Nó không có trường `leapSecond` và không cho lưu hai giá trị `23:59:59Z` và `23:59:60Z` như hai nhãn UTC riêng biệt.

`LocalTime` có `SECOND_OF_MINUTE` từ **0 đến 59**, `LocalTime.MAX` là `23:59:59.999999999`. Vì vậy `LocalTime.of(23, 59, 60)` thất bại; tương tự, đừng mong `LocalDateTime` tự cho phép giây thứ 60.

### 3.2. Điều gì xảy ra quanh ranh giới 2016–2017?

Với biểu diễn và phép tính `Instant` thông thường:

```java
Instant before = Instant.parse("2016-12-31T23:59:59Z");
Instant after  = Instant.parse("2017-01-01T00:00:00Z");
Duration d = Duration.between(before, after);
System.out.println(d); // PT1S
```

Đây là **một giây theo giá trị thang thời gian Java**. Không nên lấy kết quả `PT1S` rồi khẳng định chắc chắn rằng giữa hai nhãn UTC trên đã trôi qua đúng một giây SI vật lý: lịch UTC thực tế có nhãn `23:59:60` ở giữa. `Duration` đo chênh lệch theo thang thời gian mà `java.time` dùng; tài liệu cũng lưu ý giây trong `Duration` không nhất thiết luôn đồng nhất với giây SI gần leap second.

`Instant.ofEpochSecond(...)`, `toEpochMilli()` và timestamp dạng epoch được thiết kế để dùng trục Java này; **không coi epoch second là số đếm đầy đủ tất cả các giây nhuận đã xảy ra**. Muốn chuyển chính xác sang TAI/GPS hoặc giây SI vật lý trong tình huống đặc biệt, phải có quy tắc chuyển đổi và dữ liệu leap second phù hợp.

## 4. Java có parse được chuỗi `23:59:60Z` không?

Câu trả lời phụ thuộc **API và formatter**.

- Tạo `LocalTime`/`LocalDateTime` với `second=60` → **không hợp lệ**.
- Parser instant của `DateTimeFormatter`, cụ thể luồng được xây dựng bằng `DateTimeFormatterBuilder.appendInstant()` (bao gồm `DateTimeFormatter.ISO_INSTANT`), **có xử lý đặc biệt** chuỗi UTC `23:59:60`.
- Khi thấy `23:59:60`, parser **thay 60 bằng 59** cho giá trị `Instant` được phân giải và lưu dấu hiệu `parsedLeapSecond() == true`. Điều này **không tạo ra một `Instant` độc lập cho giây 60**.
- `DateTimeFormatter.parsedLeapSecond()` là query trả `Boolean`, đọc được từ kết quả parse; đây là tín hiệu rằng parser đã gặp cú pháp leap second. **Parser không tự chứng minh** ngày đang xét đã thực sự được cơ quan thời gian công bố có leap second.
- Nếu ứng dụng cần bảo toàn ý nghĩa leap second hoặc áp dụng smoothing đúng chuẩn, chính ứng dụng phải xác minh sự kiện và xử lý theo chính sách đã chọn.

Ví dụ (đoạn mã minh họa trong phương thức Java có đầy đủ `import` tương ứng):

```java
String raw = "2016-12-31T23:59:60Z";
TemporalAccessor parsed = DateTimeFormatter.ISO_INSTANT.parse(raw);
Instant normalized = Instant.from(parsed);
boolean leapSeen = parsed.query(DateTimeFormatter.parsedLeapSecond());

System.out.println(normalized); // 2016-12-31T23:59:59Z
System.out.println(leapSeen);    // true
```

Không được dùng `normalized` một mình rồi xóa chuỗi gốc nếu mục tiêu là lưu trữ không mất thông tin sự kiện: `2016-12-31T23:59:59Z` và input leap `2016-12-31T23:59:60Z` có thể dẫn đến **cùng giá trị `Instant` sau parse**, mặc dù đó là hai nhãn UTC khác nhau.

### 4.1. `parsedLeapSecond()` khác `isSupported(SECOND_OF_MINUTE)`

Truy vấn `parsedLeapSecond()` là một **cờ thông tin từ quá trình parse**, không phải một trường độc lập có thể khai thác từ `Instant` thông thường. Sau khi chuyển thành `Instant` rồi chỉ lưu mỗi `Instant`, thông tin chuỗi đã ghi `60` **không còn nguyên vẹn**.

Trong dữ liệu liên hệ với định danh giao dịch hay chứng cứ đo đạc, cần cân nhắc giữ đồng thời:

1. Chuỗi UTC gốc và nguồn dữ liệu.
2. Cờ đã gặp cú pháp `60`.
3. Giá trị đã chuẩn hóa để dùng chung với `java.time`.
4. Quy tắc/phiên bản dữ liệu leap-second dùng để xác minh và chuyển đổi.

Chỉ kiểm tra cờ có giá trị `true` chưa đủ để kết luận leap second đó hợp lệ theo lịch thực tế.

## 5. Chương trình Java 17+ chạy độc lập

Tạo tệp **`JavaTimeScaleDemo.java`**:

```java
import java.time.DateTimeException;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.TemporalAccessor;

public class JavaTimeScaleDemo {
    public static void main(String[] args) {
        Instant before = Instant.parse("2016-12-31T23:59:59Z");
        Instant after = Instant.parse("2017-01-01T00:00:00Z");

        System.out.println("before = " + before);
        System.out.println("after = " + after);
        System.out.println("Java duration = " + Duration.between(before, after));
        System.out.println("epoch delta = "
                + (after.getEpochSecond() - before.getEpochSecond()));

        boolean localTimeRejected = false;
        try {
            LocalTime.of(23, 59, 60);
        } catch (DateTimeException e) {
            localTimeRejected = true;
        }
        System.out.println("LocalTime rejects 60 = " + localTimeRejected);

        String input = "2016-12-31T23:59:60Z";
        TemporalAccessor parsed = DateTimeFormatter.ISO_INSTANT.parse(input);
        Instant normalized = Instant.from(parsed);
        boolean leapSecondSeen =
                parsed.query(DateTimeFormatter.parsedLeapSecond());

        System.out.println("parsed normalized = " + normalized);
        System.out.println("leap second flag = " + leapSecondSeen);
        System.out.println("same normalized Instant = "
                + before.equals(normalized));

        Instant preciseValue = Instant.ofEpochSecond(
                before.getEpochSecond(), 123_456_789);
        System.out.println("nanosecond value = " + preciseValue);
    }
}
```

Chạy trong thư mục chứa tệp, với JDK 17 trở lên:

```bash
javac JavaTimeScaleDemo.java
java JavaTimeScaleDemo
```

Kết quả:

```text
before = 2016-12-31T23:59:59Z
after = 2017-01-01T00:00:00Z
Java duration = PT1S
epoch delta = 1
LocalTime rejects 60 = true
parsed normalized = 2016-12-31T23:59:59Z
leap second flag = true
same normalized Instant = true
nanosecond value = 2016-12-31T23:59:59.123456789Z
```

**Giải thích:** `LocalTime` chặn `60`; parser `ISO_INSTANT` nhận chuỗi leap second, trả giá trị đã chuẩn hóa và cờ phát hiện; hai timestamp biên có `epochSecond` hơn kém đúng 1 theo Java Time-Scale. Trường nano chỉ minh họa **khả năng lưu**, không nói đồng hồ đã đo được độ chính xác đến 1 nano giây. Mã không dùng giờ hiện tại hoặc múi giờ mặc định nên output có tính xác định.

## 6. Đồng hồ hệ thống: độ phân giải, độ chính xác và tính đơn điệu

Ba khái niệm dễ bị nhầm:

- **Độ phân giải biểu diễn:** `Instant` có thể lưu phần nano giây; đó là kích thước đơn vị biểu diễn nhỏ nhất của kiểu.
- **Độ chính xác của nguồn:** `Instant.now()`, `Clock.systemUTC()` phụ thuộc đồng hồ, hệ điều hành và cơ chế đồng bộ. Một giá trị có chín chữ số sau dấu thập phân không chứng minh phép đo đúng đến nano giây.
- **Tính đơn điệu (monotonicity):** đồng hồ hệ thống dùng để lấy thời gian thực có thể bị chỉnh tiến/lùi; đặc tả Java không yêu cầu `Instant.now()` phải tăng sau mọi lần gọi.

Ví dụ khi đo thời gian xử lý trong **cùng một JVM**, thường dùng `System.nanoTime()` để lấy **chênh lệch thời gian tương đối**:

```java
long started = System.nanoTime();
doWork();
long elapsedNanos = System.nanoTime() - started;
```

Đây là ví dụ minh họa; `doWork()` là hàm nghiệp vụ cần định nghĩa riêng. `System.nanoTime()` không cho mốc UTC và không được phép dùng như `Instant` để lưu timestamp hoặc gửi mốc thời gian giữa máy. Độ phân giải trả về đơn vị nano giây không đảm bảo độ chính xác phần cứng nano giây; đo thời gian cũng phải tính tới overhead và hành vi của nền tảng.

Với nghiệp vụ hỏi “bây giờ là lúc nào?”, sử dụng `Clock`/`Instant.now(clock)` để có mốc dân dụng; truyền `Clock` vào thành phần cần thời gian hiện tại để dễ kiểm thử. Với nghiệp vụ đo latency hoặc timeout tương đối trong quá trình chạy, sử dụng nguồn elapsed-time thích hợp.

```java
Clock fixed = Clock.fixed(
        Instant.parse("2026-10-24T12:00:00Z"),
        java.time.ZoneOffset.UTC);
Instant a = Instant.now(fixed);
Instant b = Instant.now(fixed);
System.out.println(a.equals(b)); // true
```

`Clock.fixed` dành cho kiểm thử/giả lập, không phải nguồn giờ thực đang trôi.

## 7. Thực hành xử lý dữ liệu có leap second

### Trường hợp A — Ứng dụng thông thường

Đối với log ứng dụng, CRUD, lịch sử thanh toán, sự kiện dịch vụ, phân trang theo timestamp: `Instant` thường là lựa chọn phù hợp để biểu diễn thời điểm toàn cục. Lưu dữ liệu ở dạng UTC/epoch nhất quán; xác định rõ độ chính xác hệ thống và cách đồng bộ giữa các máy. Không viết logic “thêm giây `60`” thủ công vào `Instant` hoặc `LocalTime`.

### Trường hợp B — Nhận dữ liệu UTC từ thiết bị có thể báo `23:59:60Z`

Sơ đồ quyết định:

```text
Chuỗi timestamp đầu vào
    |
    v
Parse theo formatter instant phù hợp
    |
    +-- Cú pháp không hợp lệ --> từ chối / báo lỗi dữ liệu
    |
    v
Đọc parsedLeapSecond()
    |
    +-- false --> xử lý Instant theo chính sách thông thường
    |
    +-- true
          |
          v
    Giữ raw input, xác minh ngày UTC với bảng leap-second chính thức
          |
          +-- Không khớp --> từ chối / đưa vào vùng cần kiểm tra
          |
          +-- Hợp lệ --> chuyển đổi bằng chính sách timescale đã quy định
                           + lưu metadata để bảo toàn sự kiện
```

Đừng mặc định `Instant.from(parsed)` là kết quả cuối cùng đã xử lý đúng leap second. Parser giúp nhận biết ký hiệu đầu vào, còn việc xác thực sự kiện leap và biến đổi thang thời gian do ứng dụng chịu trách nhiệm nếu bài toán yêu cầu chính xác đến giây vật lý.

### Trường hợp C — Thiết bị đo đạc, giao dịch cần thứ tự tuyệt đối sát leap second

Nếu định danh hai sự kiện xảy ra ở UTC `23:59:59` và `23:59:60` là thiết yếu, dùng `Instant` đơn thuần có thể **làm mất khả năng phân biệt** sau parse. Hệ thống cần chốt rõ:

- Thang thời gian của đầu vào và đầu ra (UTC, TAI, GPS hoặc thang khác);
- nguồn và phiên bản bảng lịch leap-second có thẩm quyền;
- cách chuyển đổi/smoothing; liệu các thành phần hạ tầng có dùng cùng chính sách hay không;
- cơ chế bảo toàn timestamp gốc và metadata;
- cách kiểm thử những thời điểm liền trước, trong và sau sự kiện leap second.

Đây là phần trách nhiệm của **thiết kế hệ thống và nguồn đồng hồ**; `java.time` không thay thế phần mềm metrology/time-service chuyên dụng.

## 8. Các lỗi nhận thức thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Một ngày UTC luôn có 86.400 giây SI.” | UTC có thể có giây nhuận; Java Time-Scale duy trì 86.400 **giây danh nghĩa Java** trên mỗi ngày. |
| “Java đã định nghĩa UTC-SLS nên mọi `Instant.now()` đều smear đúng quy tắc.” | API không yêu cầu mọi clock thực hiện UTC-SLS hay nhận biết leap second. |
| “`LocalTime.of(23,59,60)` sẽ tạo được giây nhuận.” | `SECOND_OF_MINUTE` có phạm vi 0–59. |
| “`Instant.parse` nhận giây 60 nghĩa là giữ nguyên giây 60.” | Parser instant đặc biệt chuẩn hóa 60 về 59; muốn biết input có 60 phải giữ cờ và/hoặc raw input. |
| “Parser chấp nhận `23:59:60` nên ngày đó chắc chắn là ngày có leap second.” | Cần xác minh ngày sự kiện từ dữ liệu lịch leap-second chính thức. |
| “`Instant` lưu nano giây nên đồng hồ hệ thống chính xác nano giây.” | Độ phân giải biểu diễn khác độ chính xác nguồn đo. |
| “Lấy `Duration.between` gần leap second luôn cho đúng thời gian SI đã trôi qua.” | Phép toán dùng Java Time-Scale; không mặc định đại diện đầy đủ cho giây SI vật lý quanh leap second. |
| “`System.nanoTime()` là timestamp UTC chính xác.” | Đây là nguồn đo khoảng thời gian tương đối; không có gốc epoch UTC. |
| “Giây nhuận là DST hoặc ngày 29/2.” | Leap second, giờ mùa hè và ngày nhuận là ba hiện tượng khác nhau. |

## 9. Checklist khi thiết kế

1. **Gọi đúng đối tượng cần đo:** timestamp dân dụng, elapsed duration, hay số giây SI vật lý?
2. **Biết đơn vị và time scale của đối tác:** không gọi tất cả số đếm “epoch seconds” là cùng một mô hình nếu nguồn dùng UTC/TAI/GPS khác nhau.
3. **Khi API nhận `23:59:60Z`:** giữ bản gốc và `parsedLeapSecond()` nếu sự phân biệt mang ý nghĩa nghiệp vụ.
4. **Kiểm tra ranh giới leap-second:** với dữ liệu cần chính xác cao, bổ sung test ở `23:59:59`, `23:59:60`, `00:00:00` và xác nhận lịch sự kiện thực.
5. **Không phóng đại chất lượng `Clock`:** xác nhận cơ chế đồng bộ, phương pháp smear/step và độ chính xác của hạ tầng; phân biệt `Instant.now()` với `System.nanoTime()`.
6. **Giữ rõ quy tắc chuyển đổi:** khi kết hợp nguồn UTC/TAI/GPS, sử dụng cơ chế chuyển đổi và bảng leap-second đáng tin cậy, có phiên bản.

### Câu hỏi tự kiểm tra

**1.** Vì sao `Duration.between(Instant.parse("2016-12-31T23:59:59Z"), Instant.parse("2017-01-01T00:00:00Z"))` là `PT1S` mặc dù ngày UTC đó có leap second?  
→ Vì `Duration` và `Instant` tính trên Java Time-Scale với 86.400 giây danh nghĩa mỗi ngày; không biểu diễn riêng giây UTC `23:59:60`.

**2.** `DateTimeFormatter.ISO_INSTANT.parse("2016-12-31T23:59:60Z")` cho biết thông tin bổ sung nào?  
→ `DateTimeFormatter.parsedLeapSecond()` trả `true`; instant được phân giải đã chuẩn hóa giây 60 thành 59.

**3.** Dùng `Instant.now()` có đảm bảo monotonic và làm mượt leap second không?  
→ Không có bảo đảm chung đó từ API.

**4.** Vì sao cần giữ raw timestamp của máy đo?  
→ Vì sau chuẩn hóa về `Instant`, hai nhãn UTC riêng biệt có thể trở nên không phân biệt được và không đủ dữ kiện phục hồi sự kiện gốc.

### Tài liệu đối chiếu

- [Java SE 21 — `Instant`, mục Time-scale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html): định nghĩa Java Time-Scale, hai giai đoạn UT1/UTC-SLS, ràng buộc và giới hạn của nguồn clock.
- [Java SE 21 — `DateTimeFormatter.parsedLeapSecond()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html#parsedLeapSecond()): cơ chế parse và cờ nhận biết cú pháp giây nhuận.
- [Java SE 21 — `Clock`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html): nguồn thời gian, chính sách chất lượng/smoothing không bắt buộc ở mọi implementation.
- [Java SE 21 — `Duration`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html): đơn vị giây của duration có thể khác SI giây quanh sự kiện leap second.

**Ghi nhớ:** `Instant` là biểu diễn timestamp rất hữu ích cho ứng dụng Java, nhưng việc có `epochSecond` và `nano` không đồng nghĩa Java lưu được nhãn UTC `23:59:60` hoặc cung cấp đồng hồ vật lý tuyệt đối. Những bài toán nhạy với giây nhuận phải quản lý **thang thời gian, dữ liệu leap-second, nguồn clock và chính sách chuyển đổi** một cách tường minh.
