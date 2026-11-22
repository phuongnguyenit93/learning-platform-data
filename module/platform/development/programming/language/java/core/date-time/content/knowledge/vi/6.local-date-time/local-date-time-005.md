# LocalDateTime: Thay thành phần và cắt bớt độ chính xác

## 1. Mục tiêu và phạm vi

Bài học tập trung vào hai nhóm thao tác trên `java.time.LocalDateTime` trong Java 17+:

1. **Thay một thành phần** của ngày-giờ bằng các phương thức `withYear()`, `withMonth()`, `withDayOfMonth()`, `withHour()`, `withMinute()`, `withSecond()`, `withNano()` hoặc các dạng `with(TemporalField, long)` và `with(TemporalAdjuster)`.
2. **Cắt bớt độ chi tiết thời gian** về ngày, giờ, phút, giây, mili giây, micro giây… bằng `truncatedTo(TemporalUnit)`.

Sau bài, bạn có thể giải thích tính bất biến của `LocalDateTime`, phân biệt **đặt thành phần** với **cộng/trừ thời lượng**, hiểu các trường hợp cuối tháng/năm nhuận, chọn đơn vị cắt hợp lệ và tránh nhầm cắt bỏ với làm tròn.

**Phạm vi:** `LocalDateTime` là ngày và giờ **địa phương**, không có múi giờ hoặc độ lệch UTC. Các phép thay thành phần/cắt bớt trong bài thao tác trực tiếp trên trường ngày-giờ của giá trị địa phương. Không được coi một `LocalDateTime` tự nó đã xác định một thời điểm tuyệt đối.

## 2. LocalDateTime là giá trị bất biến

`LocalDateTime` chứa các trường ngày (năm, tháng, ngày) và giờ (giờ, phút, giây, nano giây). Đối tượng **bất biến (immutable)**: mọi thao tác `with...()` và `truncatedTo()` trả về một giá trị kết quả; giá trị gốc không bị thay đổi.

```java
LocalDateTime original = LocalDateTime.of(2024, 1, 31, 14, 27);
original.withHour(9); // Kết quả trả về bị bỏ đi

System.out.println(original); // 2024-01-31T14:27

LocalDateTime updated = original.withHour(9);
System.out.println(updated);  // 2024-01-31T09:27
System.out.println(original); // 2024-01-31T14:27
```

Đây là **đoạn mã minh họa trong một phương thức**, yêu cầu `import java.time.LocalDateTime;`.

Có thể gán lại biến `original = original.withHour(9);` nếu muốn biến trỏ tới giá trị mới; điều đó **không sửa đối tượng cũ**. API có thể tối ưu bằng cách trả cùng object khi không thay đổi, nên không dùng `==` làm phép kiểm tra hai ngày-giờ có cùng giá trị; dùng `equals()`, `isBefore()` hoặc `isAfter()` tùy nhu cầu.

### Cách tạo và độ chi tiết tới nano giây

```java
LocalDateTime moment = LocalDateTime.of(
        2024, 1, 31, 14, 27, 38, 987_654_321);
System.out.println(moment);
// 2024-01-31T14:27:38.987654321
```

Đây là đoạn mã minh họa trong một phương thức, cần `import java.time.LocalDateTime;`.

Giá trị chứa đủ:

| Trường | Giá trị | Miền thông dụng |
| --- | ---: | --- |
| Năm | 2024 | `LocalDateTime` hỗ trợ dải năm ISO mở rộng |
| Tháng | 1 | 1–12 |
| Ngày trong tháng | 31 | 1–28/29/30/31, tùy tháng/năm |
| Giờ | 14 | 0–23 |
| Phút | 27 | 0–59 |
| Giây | 38 | 0–59 |
| Nano giây trong giây | 987.654.321 | 0–999.999.999 |

`LocalDateTime` **có thể biểu diễn** phần nano giây; điều đó không đảm bảo đồng hồ, cơ sở dữ liệu hay thiết bị đo **có độ chính xác thực tế** tới 1 ns. `LocalDateTime.now()` sử dụng đồng hồ hệ thống với độ phân giải phụ thuộc nền tảng; ví dụ có giá trị cố định dùng `of(...)` để đầu ra tái lập.

## 3. Thay thành phần bằng with...()

Các phương thức có tên rõ ràng cho biết **thành phần cần đặt**:

| Phương thức | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `withYear(2025)` | Đặt năm thành 2025 | Giữ các trường khác khi có thể |
| `withMonth(2)` | Đặt tháng thành 2 | Có thể điều chỉnh ngày cuối tháng |
| `withDayOfMonth(1)` | Đặt ngày trong tháng thành 1 | Về ngày đầu tháng |
| `withDayOfYear(60)` | Đặt ngày thứ 60 trong năm | Phụ thuộc năm có nhuận hay không |
| `withHour(9)` | Đặt giờ thành 09 | Giữ phút/giây/nano |
| `withMinute(0)` | Đặt phút thành 00 | Giữ giờ/giây/nano |
| `withSecond(0)` | Đặt giây thành 00 | **Không tự đặt nano về 0** |
| `withNano(0)` | Đặt phần nano giây thành 0 | Không sửa giây |

Ví dụ:

```java
LocalDateTime source = LocalDateTime.of(
        2024, 8, 23, 14, 27, 38, 987_654_321);

LocalDateTime meeting = source.withHour(9).withMinute(0);
LocalDateTime exactSecond = source.withNano(0);
LocalDateTime startOfMinute = source.withSecond(0).withNano(0);
```

Đây là đoạn minh họa trong một phương thức, cần `import java.time.LocalDateTime;`.

Kết quả:

- `meeting` = `2024-08-23T09:00:38.987654321`: giờ/phút đã đổi, phần giây giữ nguyên.
- `exactSecond` = `2024-08-23T14:27:38`: chỉ phần nano về 0.
- `startOfMinute` = `2024-08-23T14:27`: cả giây và nano về 0.

**Điểm dễ nhầm:** `withSecond(0)` **không phải** phương thức “cắt về đầu phút”, vì nano giây có thể vẫn khác 0. Dùng `truncatedTo(ChronoUnit.MINUTES)` hoặc đặt đồng thời `withSecond(0).withNano(0)`.

### 3.1. Phân biệt with...(), plus...() và minus...()

```java
LocalDateTime source = LocalDateTime.of(2024, 5, 10, 14, 27);

LocalDateTime setHour = source.withHour(9);  // 2024-05-10T09:27
LocalDateTime addHour = source.plusHours(9); // 2024-05-10T23:27
LocalDateTime minusHour = source.minusHours(9); // 2024-05-10T05:27
```

Đây là đoạn minh họa trong một phương thức, cần `import java.time.LocalDateTime;`.

- `withHour(9)` nghĩa là “**đặt giờ bằng 9**”.
- `plusHours(9)` nghĩa là “**cộng thêm 9 giờ**”.
- `minusHours(9)` nghĩa là “**trừ đi 9 giờ**”.

Thao tác `with...()` thường gắn với nhu cầu **chọn một giá trị trường cụ thể** như giờ bắt đầu làm việc, phút 00 hay ngày đầu tháng. Dùng `plus/minus` khi bài toán nói đến **dịch chuyển** theo một lượng.

## 4. Quy tắc cuối tháng, năm nhuận và giá trị không hợp lệ

Khi đặt tháng hoặc năm, ngày hiện tại có thể **không tồn tại trong tháng/năm mới**. Một số phương thức `with...()` điều chỉnh ngày về ngày cuối hợp lệ:

```java
LocalDateTime jan31 = LocalDateTime.of(2024, 1, 31, 14, 27);
LocalDateTime feb2024 = jan31.withMonth(2);
LocalDateTime leapDay = LocalDateTime.of(2024, 2, 29, 14, 27);
LocalDateTime nextYear = leapDay.withYear(2025);

System.out.println(feb2024); // 2024-02-29T14:27
System.out.println(nextYear); // 2025-02-28T14:27
```

Đây là đoạn minh họa trong một phương thức, cần `import java.time.LocalDateTime;`. Với `withMonth(2)`, 31/1 điều chỉnh về ngày cuối tháng 2; với `withYear(2025)`, 29/2 của năm nhuận trở thành 28/2 năm không nhuận.

Tuy nhiên **đặt trực tiếp một ngày không tồn tại** bằng `withDayOfMonth()` sẽ ném `DateTimeException`. Ví dụ:

```java
LocalDateTime feb29 = LocalDateTime.of(2024, 2, 29, 14, 27);
// feb29.withDayOfMonth(30); // DateTimeException: tháng 2/2024 không có ngày 30
```

Đây là đoạn minh họa trong một phương thức. Quy tắc cần nhớ: **một số thay đổi tháng/năm có cơ chế điều chỉnh ngày**; không suy rộng rằng mọi `with...()` đều tự sửa mọi ngày sai.

Các giới hạn khác: `withHour(24)`, `withMinute(60)`, `withSecond(60)`, `withNano(1_000_000_000)` đều không hợp lệ theo miền của `LocalDateTime`. Khi dữ liệu đến từ form/API, hãy kiểm tra hoặc xử lý `DateTimeException` phù hợp.

### Thứ tự thực thi trong chuỗi thay thành phần

```java
LocalDateTime start = LocalDateTime.of(2024, 1, 31, 14, 27);

LocalDateTime a = start.withMonth(2).withDayOfMonth(28);
LocalDateTime b = start.withDayOfMonth(28).withMonth(2);
```

Đây là đoạn minh họa trong một phương thức. Với đầu vào này, cả `a` và `b` đều là `2024-02-28T14:27`. Nhưng quy tắc tổng quát vẫn là **các thao tác chạy từ trái qua phải**: `start.withMonth(2).withDayOfMonth(31)` sẽ lỗi ở bước sau, còn `start.withDayOfMonth(31).withMonth(2)` điều chỉnh về `2024-02-29T14:27`. Không được hoán đổi thứ tự tùy ý trong một quy trình có phụ thuộc giá trị trung gian.

## 5. Dạng tổng quát with(TemporalField, long)

Nếu trường ngày/giờ được chọn động (ví dụ từ bảng cấu hình), dùng dạng:

```java
LocalDateTime updated = source.with(
        ChronoField.MINUTE_OF_HOUR, 5);
```

Đây là đoạn minh họa trong một phương thức, cần `source` là `LocalDateTime` và `import java.time.temporal.ChronoField;`.

Một số `ChronoField` phù hợp với `LocalDateTime`:

- `YEAR`, `MONTH_OF_YEAR`, `DAY_OF_MONTH`, `DAY_OF_YEAR`;
- `HOUR_OF_DAY`, `MINUTE_OF_HOUR`, `SECOND_OF_MINUTE`;
- `MILLI_OF_SECOND`, `MICRO_OF_SECOND`, `NANO_OF_SECOND`.

Lưu ý `NANO_OF_SECOND` là phần nano trong một giây, không phải timestamp nano kể từ Unix epoch. `LocalDateTime` không có múi giờ hoặc offset, nên các trường như `INSTANT_SECONDS` không phải trường có thể tự truy xuất từ nó.

Kiểm tra khả năng hỗ trợ khi field đến từ bên ngoài:

```java
boolean supported = source.isSupported(ChronoField.MINUTE_OF_HOUR);
// true

boolean instantSupported = source.isSupported(ChronoField.INSTANT_SECONDS);
// false
```

Đây là đoạn minh họa trong phương thức với `source` là `LocalDateTime`. Gọi `with(...)` với field không hỗ trợ có thể ném `UnsupportedTemporalTypeException`, là lớp con của `DateTimeException`.

Trong mã thông thường, `withMinute(5)` dễ đọc hơn `with(ChronoField.MINUTE_OF_HOUR, 5)`; dạng tổng quát phù hợp khi chọn trường động.

## 6. Dạng with(TemporalAdjuster): điều chỉnh theo quy tắc lịch

`with(TemporalAdjuster)` cho phép áp dụng điều chỉnh có ngữ nghĩa lịch như “ngày đầu tháng”, “ngày cuối tháng” hoặc “thứ Hai kế tiếp”. `TemporalAdjusters` cung cấp nhiều adjuster dùng sẵn.

```java
LocalDateTime source = LocalDateTime.of(2024, 8, 23, 14, 27);

LocalDateTime firstDay =
        source.with(TemporalAdjusters.firstDayOfMonth());
LocalDateTime lastDay =
        source.with(TemporalAdjusters.lastDayOfMonth());
LocalDateTime nextMonday =
        source.with(TemporalAdjusters.next(DayOfWeek.MONDAY));
```

Đây là đoạn minh họa trong một phương thức, cần:

```java
import java.time.DayOfWeek;
import java.time.LocalDateTime;
import java.time.temporal.TemporalAdjusters;
```

Kết quả:

- `firstDay` = `2024-08-01T14:27`;
- `lastDay` = `2024-08-31T14:27`;
- `nextMonday` = `2024-08-26T14:27`.

Các adjuster lịch thay **phần ngày** nhưng giữ nguyên thời gian trong ngày nếu quy tắc không yêu cầu thay. Muốn cả ngày đầu tháng **và giờ 00:00**, cần thêm thao tác cắt về ngày:

```java
LocalDateTime monthStart = source
        .with(TemporalAdjusters.firstDayOfMonth())
        .truncatedTo(ChronoUnit.DAYS);
// 2024-08-01T00:00
```

Đây là đoạn minh họa có `import java.time.temporal.ChronoUnit;` và các import trước đó. Hai thao tác thực hiện hai việc khác nhau: điều chỉnh **ngày** và xóa **thành phần thời gian trong ngày**.

Có thể thay phần ngày hoặc giờ bằng `with(LocalDate)` / `with(LocalTime)` vì các kiểu đó triển khai `TemporalAdjuster`, nhưng `with(TemporalAdjusters....)` thể hiện tốt hơn ý nghĩa quy tắc lịch.

## 7. truncatedTo(TemporalUnit): cắt phần nhỏ hơn đơn vị

`LocalDateTime.truncatedTo(unit)` trả về ngày-giờ được **cắt bỏ các trường thời gian nhỏ hơn độ lớn của đơn vị chọn**, không đổi phần lớn hơn và không cộng thêm để làm tròn lên.

Hình dung:

```text
Giá trị gốc: 2024-01-31T14:27:38.987654321
Cắt về giờ: 2024-01-31T14:00
Cắt về phút: 2024-01-31T14:27
Cắt về giây: 2024-01-31T14:27:38
Cắt về ms: 2024-01-31T14:27:38.987
Cắt về µs: 2024-01-31T14:27:38.987654
```

Phương thức sử dụng `TemporalUnit` (thường là `ChronoUnit`):

```java
LocalDateTime source = LocalDateTime.of(
        2024, 1, 31, 14, 27, 38, 987_654_321);

LocalDateTime hour = source.truncatedTo(ChronoUnit.HOURS);
LocalDateTime minute = source.truncatedTo(ChronoUnit.MINUTES);
LocalDateTime second = source.truncatedTo(ChronoUnit.SECONDS);
LocalDateTime millis = source.truncatedTo(ChronoUnit.MILLIS);
LocalDateTime micros = source.truncatedTo(ChronoUnit.MICROS);
LocalDateTime dateStart = source.truncatedTo(ChronoUnit.DAYS);
```

Đây là đoạn minh họa trong một phương thức, cần `import java.time.LocalDateTime;` và `import java.time.temporal.ChronoUnit;`.

| Đơn vị | Giá trị sau cắt |
| --- | --- |
| `DAYS` | `2024-01-31T00:00` |
| `HOURS` | `2024-01-31T14:00` |
| `MINUTES` | `2024-01-31T14:27` |
| `SECONDS` | `2024-01-31T14:27:38` |
| `MILLIS` | `2024-01-31T14:27:38.987` |
| `MICROS` | `2024-01-31T14:27:38.987654` |
| `NANOS` | Giữ nguyên đầy đủ `2024-01-31T14:27:38.987654321` |

**Cắt về ngày** trên `LocalDateTime` nghĩa là giữ nguyên ngày và đặt giờ 00:00:00.000000000. Nó **không** quyết định “đầu ngày thực tế ở UTC” vì `LocalDateTime` chưa gắn `ZoneId`.

### Vì sao DAYS hợp lệ còn WEEKS thường không?

`LocalDateTime.truncatedTo(...)` thực hiện phần cắt dựa trên **thời gian trong một ngày**. Đơn vị cắt phải có duration dương và **chia hết một ngày chuẩn 24 giờ**, và không được dài hơn một ngày chuẩn. Do đó `NANOS`, `MICROS`, `MILLIS`, `SECONDS`, `MINUTES`, `HOURS`, `HALF_DAYS` và `DAYS` phù hợp; `WEEKS`, `MONTHS`, `YEARS` không phải cách cắt hợp lệ.

Ví dụ:

```java
LocalDateTime noon = source.truncatedTo(ChronoUnit.HALF_DAYS);
// Với source 14:27, noon là 2024-01-31T12:00

// source.truncatedTo(ChronoUnit.WEEKS);
// UnsupportedTemporalTypeException
```

Đây là đoạn minh họa trong phương thức với `source` là `LocalDateTime`. Muốn đầu tuần, hãy dùng **quy tắc lịch** với adjuster/chọn ngày đầu tuần, sau đó cắt phần giờ:

```java
LocalDateTime startOfIsoWeek = source
        .with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))
        .truncatedTo(ChronoUnit.DAYS);
```

Đây là đoạn minh họa cần `ChronoUnit`, `DayOfWeek` và `TemporalAdjusters`. Quy ước tuần bắt đầu thứ Hai ở ví dụ thuộc lịch ISO; một số nghiệp vụ/vùng địa lý dùng Chủ nhật hoặc quy tắc khác.

## 8. Code chạy được: thay thành phần và cắt độ chi tiết

Lưu file **`LocalDateTimeAdjustmentDemo.java`**:

```java
import java.time.LocalDateTime;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;

public class LocalDateTimeAdjustmentDemo {
    public static void main(String[] args) {
        LocalDateTime original = LocalDateTime.of(
                2024, 1, 31, 14, 27, 38, 987_654_321);

        LocalDateTime february = original.withMonth(2);
        LocalDateTime nineOClock = original.withHour(9)
                .withMinute(0).withSecond(0).withNano(0);
        LocalDateTime minuteFive =
                original.with(ChronoField.MINUTE_OF_HOUR, 5);

        System.out.println("original = " + original);
        System.out.println("february = " + february);
        System.out.println("nineOClock = " + nineOClock);
        System.out.println("minuteFive = " + minuteFive);
        System.out.println("truncatedHours = "
                + original.truncatedTo(ChronoUnit.HOURS));
        System.out.println("truncatedMinutes = "
                + original.truncatedTo(ChronoUnit.MINUTES));
        System.out.println("truncatedMillis = "
                + original.truncatedTo(ChronoUnit.MILLIS));
        System.out.println("truncatedMicros = "
                + original.truncatedTo(ChronoUnit.MICROS));
        System.out.println("truncatedDays = "
                + original.truncatedTo(ChronoUnit.DAYS));
        System.out.println("originalAgain = " + original);
    }
}
```

Chạy với Java 17+:

```bash
javac LocalDateTimeAdjustmentDemo.java
java LocalDateTimeAdjustmentDemo
```

Kết quả xác định:

```text
original = 2024-01-31T14:27:38.987654321
february = 2024-02-29T14:27:38.987654321
nineOClock = 2024-01-31T09:00
minuteFive = 2024-01-31T14:05:38.987654321
truncatedHours = 2024-01-31T14:00
truncatedMinutes = 2024-01-31T14:27
truncatedMillis = 2024-01-31T14:27:38.987
truncatedMicros = 2024-01-31T14:27:38.987654
truncatedDays = 2024-01-31T00:00
originalAgain = 2024-01-31T14:27:38.987654321
```

Giải thích:

1. `withMonth(2)` chuyển 31/1 sang 29/2/2024 vì năm nhuận, giữ nguyên giờ và nano.
2. Chuỗi `withHour(9).withMinute(0).withSecond(0).withNano(0)` đặt đúng 09:00, tránh phần giây/nano sót lại.
3. `with(ChronoField.MINUTE_OF_HOUR, 5)` thay phút 27 thành 05; các trường khác giữ nguyên.
4. `truncatedTo(...)` loại phần thời gian nhỏ hơn đơn vị, không làm tròn số và không làm biến `original` thay đổi.

Lưu ý kết quả của `LocalDateTime.toString()` có thể **ẩn các nhóm số không cần thiết**. Ví dụ thời gian 09:00 sẽ in `2024-01-31T09:00` thay vì ép hiển thị `:00.000000000`. Các trường giây/nano vẫn có giá trị bằng 0.

## 9. Cắt bỏ khác làm tròn, khác định dạng hiển thị

Ba thao tác có mục đích khác nhau:

| Mục đích | API hoặc cách làm | Có đổi giá trị bên trong không? |
| --- | --- | --- |
| Cắt bỏ phần nhỏ hơn một phút | `truncatedTo(ChronoUnit.MINUTES)` | Có: giây/nano về 0 ở kết quả |
| Làm tròn về phút gần nhất | Xác định quy tắc và tính toán có chủ đích | Có: đôi khi phút tăng |
| Chỉ hiển thị tới phút | `DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm")` | Không: chỉ thay văn bản hiển thị |

Ví dụ cùng giá trị:

```java
LocalDateTime input = LocalDateTime.of(2024, 2, 29, 23, 59, 45);
LocalDateTime truncated = input.truncatedTo(ChronoUnit.MINUTES);
LocalDateTime roundedHalfUp = input.plusSeconds(30)
        .truncatedTo(ChronoUnit.MINUTES);

System.out.println(truncated);     // 2024-02-29T23:59
System.out.println(roundedHalfUp); // 2024-03-01T00:00
```

Đây là đoạn minh họa trong phương thức, cần import `LocalDateTime` và `ChronoUnit`. Phương pháp “cộng 30 giây trước rồi cắt về phút” minh họa một chính sách **làm tròn phút gần nhất, nửa phút trở lên làm tròn lên** trong lịch địa phương; với bài toán tổng quát cần xét tràn biên, quy tắc làm tròn và các yêu cầu âm/dương của đại lượng đang xử lý.

Để **chỉ đổi cách hiển thị** mà vẫn giữ nano:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm");
String display = input.format(formatter); // 2024-02-29 23:59
LocalDateTime stillOriginal = input;      // vẫn có giây = 45
```

Đây là đoạn minh họa trong phương thức, cần `import java.time.format.DateTimeFormatter;` và biến `input` từ ví dụ trên.

**Cảnh báo thiết kế:** Không sử dụng việc format chuỗi như cách cắt dữ liệu nội bộ trừ khi hợp đồng hệ thống thực sự yêu cầu chuyển qua chuỗi và parse trở lại. `DateTimeFormatter` chỉ quy định cách biểu diễn; `truncatedTo()` tác động trực tiếp tới giá trị ngày-giờ kết quả.

## 10. Cắt theo ms, µs và ns khi làm việc với cơ sở dữ liệu

`LocalDateTime` lưu phần giây theo **nano giây** dưới dạng số nguyên từ 0 đến 999.999.999. Các đơn vị phổ biến:

| Mức chi tiết | Nano giây trong một đơn vị | Ví dụ phần lẻ |
| --- | ---: | --- |
| Mili giây (ms) | 1.000.000 ns | `.987` |
| Micro giây (µs) | 1.000 ns | `.987654` |
| Nano giây (ns) | 1 ns | `.987654321` |

Một hệ thống lưu tới micro giây có thể yêu cầu:

```java
LocalDateTime persisted =
        original.truncatedTo(ChronoUnit.MICROS);
```

Đây là đoạn minh họa trong phương thức với `original` là `LocalDateTime` có phần nano, cần `ChronoUnit`.

Trong một ứng dụng lưu ngày-giờ, phải kiểm tra:

- **Cột dữ liệu và JDBC driver** có hỗ trợ độ chính xác phần giây nào; không tự giả định mọi DB giữ đủ 9 chữ số.
- **Quy tắc của DB** khi nhập nhiều chữ số phần giây hơn mức cột chấp nhận: có thể làm tròn hoặc cắt, tùy hệ quản trị và kiểu cột.
- Nếu cần so sánh chính xác giá trị vừa ghi và đọc lại, cân nhắc **chuẩn hóa về cùng độ chi tiết** theo hợp đồng trước khi lưu.
- **LocalDateTime không chứa timezone**: cắt về milli/micro/nano không biến giá trị này thành timestamp UTC. Muốn biểu diễn thời điểm tuyệt đối hãy dùng kiểu/chiến lược có thông tin offset/zone thích hợp.

Một `LocalDateTime` có phần nano là `987_654_321` sẽ thành `987_654_000` sau `truncatedTo(MICROS)` và `987_000_000` sau `truncatedTo(MILLIS)`. Đây là **mất thông tin có chủ đích**, không thể khôi phục phần đã cắt chỉ bằng đổi đơn vị.

## 11. Bài toán thực tế: gom bản ghi theo từng phút hoặc từng giờ

Giả sử một ứng dụng ghi các sự kiện có thời gian địa phương:

```text
2024-08-23T14:27:03
2024-08-23T14:27:51
2024-08-23T14:28:04
```

Có thể tạo khóa gom theo phút bằng `truncatedTo(ChronoUnit.MINUTES)`; hai sự kiện đầu về cùng khóa `2024-08-23T14:27`.

Lưu file **`LocalMinuteGroupingDemo.java`**:

```java
import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class LocalMinuteGroupingDemo {
    public static void main(String[] args) {
        List<LocalDateTime> events = List.of(
                LocalDateTime.of(2024, 8, 23, 14, 27, 3),
                LocalDateTime.of(2024, 8, 23, 14, 27, 51),
                LocalDateTime.of(2024, 8, 23, 14, 28, 4));

        Map<LocalDateTime, Long> counts = events.stream()
                .collect(Collectors.groupingBy(
                        time -> time.truncatedTo(ChronoUnit.MINUTES),
                        TreeMap::new,
                        Collectors.counting()));

        counts.forEach((minute, count) ->
                System.out.println(minute + " -> " + count));
    }
}
```

Chạy:

```bash
javac LocalMinuteGroupingDemo.java
java LocalMinuteGroupingDemo
```

Kết quả:

```text
2024-08-23T14:27 -> 2
2024-08-23T14:28 -> 1
```

Giải thích: `TreeMap` sắp xếp khóa `LocalDateTime` theo thứ tự tự nhiên để kết quả in có thứ tự. Các giá trị sự kiện gốc không bị biến đổi.

**Khi gom sự kiện của nhiều múi giờ hoặc theo timeline thực**, không nên gộp chỉ dựa trên `LocalDateTime`; cùng nhãn “14:27” có thể ứng với nhiều thời điểm khác nhau. Khi đó chuẩn hóa các timestamp có thông tin thời điểm (ví dụ `Instant`) và xác định cách tạo bucket theo UTC hoặc một `ZoneId` cụ thể.

## 12. Thay ngày nhưng giữ giờ; đặt giờ nhưng giữ ngày

Nhiều ứng dụng đặt lịch cần gán “ngày được chọn từ lịch” với “giờ cố định từ cấu hình”.

### Thay toàn bộ phần ngày

```java
LocalDateTime appointment =
        LocalDateTime.of(2024, 8, 23, 14, 27, 38);

LocalDateTime anotherDay =
        appointment.with(LocalDate.of(2024, 9, 2));
// 2024-09-02T14:27:38
```

Đây là đoạn minh họa cần `import java.time.LocalDate;` và `import java.time.LocalDateTime;` trong phương thức. `LocalDate` triển khai `TemporalAdjuster` nên `with(LocalDate)` thay toàn bộ phần ngày và giữ phần giờ.

### Thay toàn bộ phần giờ

```java
LocalDateTime newTime = appointment.with(LocalTime.of(9, 0));
// 2024-08-23T09:00
```

Đây là đoạn minh họa cần `import java.time.LocalTime;` với `appointment` từ ví dụ trên. `LocalTime.of(9, 0)` có giây/nano bằng 0 nên kết quả đạt 09:00 chính xác, thay vì chỉ gọi `withHour(9)` và giữ lại các phần nhỏ của giờ cũ.

Các cách tương đương theo mục đích:

```java
LocalDateTime startOfDay = appointment
        .toLocalDate()
        .atStartOfDay();

LocalDateTime sameDayAtNine = appointment
        .toLocalDate()
        .atTime(9, 0);
```

Đây là đoạn minh họa trong một phương thức, cần `LocalDateTime`. Hai kết quả là `2024-08-23T00:00` và `2024-08-23T09:00`. Các cách `atStartOfDay()`, `atTime()` biểu đạt **tạo ngày-giờ từ ngày**, không phải chỉnh sửa đối tượng gốc.

## 13. DST, múi giờ và ranh giới của LocalDateTime

`LocalDateTime.of(2024, 3, 10, 2, 30)` hợp lệ dưới dạng **nhãn ngày-giờ địa phương**, nhưng tại `America/New_York` thời điểm 02:30 ngày 10/3/2024 rơi vào khoảng đồng hồ nhảy giờ (DST gap) nên không ánh xạ trực tiếp đến một thời điểm thực tế với múi giờ đó.

Việc:

```java
LocalDateTime t = LocalDateTime.of(2024, 3, 10, 2, 30);
LocalDateTime cut = t.truncatedTo(ChronoUnit.HOURS);
// 2024-03-10T02:00
```

không tự giải quyết khoảng thời gian không tồn tại khi gắn `ZoneId`. Đây là đoạn minh họa với `LocalDateTime`, `ChronoUnit` trong một phương thức.

Điểm phân biệt:

- `LocalDateTime` mô tả **các trường ngày/giờ** và có thể cắt các trường đó mà chưa biết múi giờ.
- `ZonedDateTime` kết hợp lịch địa phương với **quy tắc múi giờ** để xử lý overlap/gap.
- `Instant` mô tả **một mốc tuyệt đối** trên timeline UTC.

Nếu xử lý một lịch họp theo giờ địa phương, hãy xác định `ZoneId` và quy tắc xử lý DST tại biên nhập/xuất. Nếu cần chia bucket sự kiện theo số giây elapsed, nên tính từ thời điểm thực (ví dụ `Instant`), vì “đầu giờ địa phương” có thể lặp lại hoặc bị bỏ qua ở vùng DST.

## 14. Kiểm tra lỗi và các điều kiện biên

Các lỗi phổ biến:

1. **Bỏ kết quả trả về:** `value.withMinute(0);` không thay đổi biến `value`.
2. **Chỉ đặt giây mà quên nano:** `withSecond(0)` chưa tạo đúng đầu phút nếu `getNano() != 0`.
3. **Nhầm “set” với “add”:** `withHour(9)` khác `plusHours(9)`.
4. **Coi cắt bỏ là làm tròn:** `truncatedTo(MINUTES)` đưa `14:27:59.999` về `14:27`, không tự thành `14:28`.
5. **Dùng đơn vị quá lớn:** `truncatedTo(WEEKS/MONTHS/YEARS)` không hợp lệ trên `LocalDateTime`.
6. **Bỏ qua ngày cuối tháng:** `withMonth(2)` từ 31/1 có thể điều chỉnh về 28/29/2; nhưng `withDayOfMonth(31)` trên một ngày tháng 2 thì không hợp lệ.
7. **Tưởng rằng LocalDateTime là UTC:** giá trị không chứa offset/zone.
8. **Nhầm hiển thị với dữ liệu:** `format()` không cắt phần nano trong object.
9. **Giả định một độ chính xác lưu trữ cố định:** DB, bộ định dạng và đồng hồ có thể chỉ hỗ trợ ms hoặc µs.
10. **Dùng giá trị thời gian hệ thống trong bài kiểm thử cố định:** ưu tiên `LocalDateTime.of(...)` để expected output không đổi.

Lưu file **`InvalidLocalDateTimeDemo.java`**:

```java
import java.time.DateTimeException;
import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;

public class InvalidLocalDateTimeDemo {
    public static void main(String[] args) {
        LocalDateTime value = LocalDateTime.of(2024, 2, 29, 14, 27);

        try {
            value.withDayOfMonth(30);
        } catch (DateTimeException ex) {
            System.out.println("Invalid day");
        }

        try {
            value.truncatedTo(ChronoUnit.WEEKS);
        } catch (DateTimeException ex) {
            System.out.println("Unsupported truncate unit");
        }

        System.out.println("unchanged = " + value);
    }
}
```

Chạy:

```bash
javac InvalidLocalDateTimeDemo.java
java InvalidLocalDateTimeDemo
```

Đầu ra:

```text
Invalid day
Unsupported truncate unit
unchanged = 2024-02-29T14:27
```

Đối tượng `value` vẫn nguyên vẹn sau cả hai thao tác thất bại nhờ tính bất biến.

## 15. Quy tắc chọn API trong ứng dụng

| Yêu cầu | Gợi ý | Giải thích |
| --- | --- | --- |
| Thay giờ của lịch hẹn nhưng giữ ngày/phút/giây | `withHour(9)` | Chỉ đặt trường giờ |
| Hẹn đúng 09:00:00.000… | `with(LocalTime.of(9, 0))` | Thay toàn bộ phần thời gian |
| Đặt ngày đầu tháng, giữ giờ | `with(TemporalAdjusters.firstDayOfMonth())` | Điều chỉnh phần ngày |
| Đặt **đầu ngày** 00:00 | `truncatedTo(ChronoUnit.DAYS)` | Đặt các trường thời gian về 0 |
| Làm khóa nhóm theo giờ | `truncatedTo(ChronoUnit.HOURS)` | Cắt phút/giây/nano |
| Cắt phần nano về mức micro giây để đồng bộ DB | `truncatedTo(ChronoUnit.MICROS)` | Loại 0–999 ns cuối |
| Chỉ hiển thị năm-tháng-ngày và giờ-phút | `DateTimeFormatter` | Không đổi giá trị ngày giờ |
| Cộng đúng 30 phút | `plusMinutes(30)` | Dịch chuyển lượng trên local timeline |
| Cắt ngày-giờ UTC tuyệt đối | Chọn `Instant` và hợp đồng thời điểm | `LocalDateTime` thiếu múi giờ/offset |

Các thao tác có thể kết hợp với nhau, nhưng thứ tự cần diễn đạt rõ. Ví dụ `dateTime.withHour(9).truncatedTo(MINUTES)` vừa đặt giờ thành 09, vừa xóa giây/nano; nó **vẫn giữ phút ban đầu**. Muốn đúng 09:00 phải đặt phút bằng 0 hoặc dùng `with(LocalTime.of(9, 0))`.

## 16. Bài tập tự kiểm tra

**Câu 1.** Với `LocalDateTime.of(2024, 1, 31, 14, 27).withMonth(2)`, kết quả là gì?

**Đáp án:** `2024-02-29T14:27`. Năm 2024 nhuận, ngày 31 được điều chỉnh về cuối tháng 2.

**Câu 2.** `withSecond(0)` có luôn tương đương `truncatedTo(ChronoUnit.MINUTES)` không?

**Đáp án:** Không. `withSecond(0)` vẫn giữ `nanoOfSecond`; `truncatedTo(MINUTES)` đặt cả giây và nano về 0.

**Câu 3.** Cắt `2024-01-31T14:27:38.987654321` về `MILLIS` và `MICROS` được gì?

**Đáp án:** Lần lượt là `2024-01-31T14:27:38.987` và `2024-01-31T14:27:38.987654`.

**Câu 4.** Vì sao không nên gọi `truncatedTo(ChronoUnit.MONTHS)` trên `LocalDateTime`?

**Đáp án:** `truncatedTo` cắt theo một đơn vị duration chia hết một ngày chuẩn và không dài hơn ngày đó; tháng là đơn vị lịch có độ dài không cố định. Muốn đầu tháng, dùng `TemporalAdjusters.firstDayOfMonth()` kết hợp cắt về ngày.

**Câu 5.** Từ `LocalDateTime.of(2024, 8, 23, 14, 27, 38)`, làm sao tạo đúng 09:00 cùng ngày?

**Đáp án:** `value.with(LocalTime.of(9, 0))`, hoặc chuỗi `value.withHour(9).withMinute(0).withSecond(0).withNano(0)`.

**Câu 6.** Khi gọi `truncatedTo(MINUTES)` trên `LocalDateTime`, ta có tạo được timestamp UTC không?

**Đáp án:** Không. Kết quả vẫn là ngày-giờ **địa phương không có múi giờ/offset**.

**Ghi nhớ:** Họ `with...()` **đặt/thay một thành phần hoặc áp dụng một quy tắc**, còn `truncatedTo(...)` **loại bỏ các phần thời gian nhỏ hơn độ chi tiết mong muốn**. Cả hai trả về `LocalDateTime` bất biến. Chọn thao tác dựa trên quy tắc nghiệp vụ, xét ngày cuối tháng, giới hạn đơn vị và đừng nhầm độ chính xác số học với múi giờ hoặc phép làm tròn.