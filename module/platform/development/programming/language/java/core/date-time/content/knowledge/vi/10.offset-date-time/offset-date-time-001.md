# OffsetDateTime: Biểu diễn ngày giờ kèm độ lệch UTC trong Java

## 1. OffsetDateTime giải quyết bài toán gì?

Một nhãn thời gian như **2024-07-15 09:30** chưa xác định một thời điểm tuyệt đối: đó có thể là 09:30 ở Việt Nam, Paris, New York hoặc nơi khác. `java.time.OffsetDateTime` bổ sung **độ lệch so với UTC (UTC offset)** để giá trị có thể ánh xạ tới một thời điểm cụ thể.

Ví dụ:

- `2024-07-15T09:30+02:00` có nghĩa đồng hồ địa phương nhanh hơn UTC hai giờ; thời điểm tương ứng là `2024-07-15T07:30:00Z`.
- `2024-07-15T09:30Z` dùng offset UTC bằng không; thời điểm tương ứng là `2024-07-15T09:30:00Z`.
- Hai giá trị có **cùng giờ hiển thị nhưng khác offset** thường là hai thời điểm khác nhau.
- Hai giá trị có **giờ hiển thị khác nhau nhưng cùng instant** có thể chỉ là hai cách biểu diễn cùng một thời điểm.

Trong Java 17+, `OffsetDateTime` là giá trị bất biến, thread-safe khi dùng như một giá trị và có độ phân giải biểu diễn đến nano giây. Nó không chứa ID vùng địa lý hay toàn bộ lịch sử quy tắc DST.

Mục tiêu bài học: tạo/đọc `OffsetDateTime`, phân biệt nó với `LocalDateTime`, `Instant` và `ZonedDateTime`, hiểu các phép đổi offset, tính toán/chuyển đổi, so sánh, parse/format và các lỗi thiết kế phổ biến.

## 2. Ba thành phần quan trọng

Một `OffsetDateTime` chứa:

1. **Phần ngày-giờ địa phương** (`LocalDateTime`): năm, tháng, ngày, giờ, phút, giây, nano giây.
2. **Độ lệch UTC** (`ZoneOffset`): từ UTC tới đồng hồ địa phương, ví dụ `+07:00`.
3. **Mối liên hệ với instant**: khi đã biết ngày-giờ và offset, ta tính được mốc tuyệt đối trên timeline.

Có thể hình dung:

```text
OffsetDateTime = LocalDateTime + ZoneOffset

2024-07-15T09:30+02:00
      |           |
      |           +-- nhanh hơn UTC hai giờ
      +-------------- ngày và giờ được hiển thị tại offset ấy

UTC instant = local date-time - offset
            = 2024-07-15T07:30:00Z
```

`ZoneOffset` quy định dấu theo chuẩn ISO-8601: `+02:00` nghĩa là giờ tại offset đó **đi trước UTC hai giờ**, nên muốn đổi về UTC phải trừ hai giờ; `-05:00` nghĩa là giờ địa phương **chậm hơn UTC năm giờ**.

### So sánh với các kiểu java.time liên quan

| Kiểu | Có ngày/giờ hiển thị? | Có offset? | Có ZoneId vùng? | Có xác định instant? |
| --- | --- | --- | --- | --- |
| `LocalDateTime` | Có | Không | Không | Không |
| `OffsetDateTime` | Có | Có | Không | Có |
| `ZonedDateTime` | Có | Có | Có | Có |
| `Instant` | Mốc trên timeline UTC | Hiển thị theo UTC | Không | Có |
| `ZoneOffset` | Không | Chính nó là offset | Không | Không, nếu thiếu ngày-giờ |

**Chọn `OffsetDateTime`** khi cần trao đổi hoặc lưu một ngày-giờ cụ thể **kèm offset được ghi nhận**. Chọn `ZonedDateTime` khi cần giữ **quy tắc vùng** như `Europe/Paris` cho lịch hẹn tương lai. Chọn `Instant` khi trọng tâm là mốc thời gian tuyệt đối, không cần mang theo biểu diễn local.

## 3. Tạo OffsetDateTime với các API thông dụng

### 3.1. Ghép thành phần và ZoneOffset

```java
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

LocalDateTime local = LocalDateTime.of(2024, 7, 15, 9, 30);
ZoneOffset offset = ZoneOffset.ofHours(2);

OffsetDateTime value = OffsetDateTime.of(local, offset);
// 2024-07-15T09:30+02:00
```

Đây là **đoạn mã minh họa trong một phương thức**, chưa phải chương trình Java độc lập. `OffsetDateTime.of(...)` có overload nhận các trường năm, tháng, ngày, giờ, phút, giây, nano giây và offset:

```java
OffsetDateTime precise = OffsetDateTime.of(
        2024, 7, 15, 9, 30, 45, 123_456_789,
        ZoneOffset.of("+02:00"));
// 2024-07-15T09:30:45.123456789+02:00
```

Đây là đoạn minh họa với `OffsetDateTime` và `ZoneOffset` đã import. Giá trị chứa phần nano giây trong một giây từ 0 đến 999.999.999.

### 3.2. Tạo từ LocalDateTime

`LocalDateTime.atOffset(ZoneOffset)` tiện dụng khi đã có giờ địa phương **và offset được xác định rõ**:

```java
LocalDateTime local = LocalDateTime.of(2024, 7, 15, 9, 30);
OffsetDateTime result = local.atOffset(ZoneOffset.ofHours(2));
```

Đây là đoạn minh họa, yêu cầu import hai kiểu `LocalDateTime`, `ZoneOffset`. Việc gắn offset cho local time là **quyết định về thời điểm**: nếu offset sai, instant thu được cũng sai.

Không tự suy luận offset từ một `LocalDateTime`. Nếu chỉ biết `Europe/Paris`, phải lấy quy tắc `ZoneId` tại ngày-giờ thích hợp và xử lý DST gap/overlap; nên dùng API vùng thay vì hardcode `+01:00` hoặc `+02:00`.

### 3.3. Tạo từ một Instant và offset/zone

Nếu có instant tuyệt đối, có thể biểu diễn nó với offset hoặc vùng:

```java
Instant instant = Instant.parse("2024-07-15T07:30:00Z");
OffsetDateTime inVietnam =
        OffsetDateTime.ofInstant(instant, ZoneOffset.ofHours(7));
OffsetDateTime inParis =
        OffsetDateTime.ofInstant(instant, ZoneId.of("Europe/Paris"));
```

Đây là đoạn minh họa cần `import java.time.Instant;`, `OffsetDateTime`, `ZoneOffset` và `ZoneId`. Kết quả:

- `inVietnam` = `2024-07-15T14:30+07:00`.
- `inParis` = `2024-07-15T09:30+02:00` theo quy tắc Paris tháng 7/2024.

`ofInstant(instant, zone)` dùng **offset hiệu lực của vùng tại instant** rồi trả về `OffsetDateTime`. Kết quả **không giữ lại ID `Europe/Paris`**. Nếu cần mang theo ID vùng, sử dụng `instant.atZone(zone)` để nhận `ZonedDateTime`.

### 3.4. Thời điểm hiện tại

```java
OffsetDateTime nowAtUtc = OffsetDateTime.now(ZoneOffset.UTC);
OffsetDateTime nowInZone = OffsetDateTime.now(
        ZoneId.of("Asia/Ho_Chi_Minh"));
```

Đây là đoạn minh họa. Kết quả phụ thuộc thời điểm thực và môi trường, nên không có stdout cố định. `now()` không tham số dựa trên múi giờ mặc định của hệ thống, có thể khác giữa laptop, container và server.

Trong mã dễ kiểm thử, dùng `Clock` được cấu hình hoặc tiêm vào, ví dụ `OffsetDateTime.now(clock)`. Nếu nghiệp vụ yêu cầu offset của người dùng, hãy xác định `ZoneId` của họ rồi cung cấp rõ khi tạo thời gian.

## 4. ZoneOffset: dấu, giới hạn và offset cố định

`ZoneOffset` là một loại `ZoneId` biểu diễn **độ lệch UTC cố định**:

```java
ZoneOffset plusSeven = ZoneOffset.of("+07:00");
ZoneOffset same = ZoneOffset.ofHours(7);
ZoneOffset withMinutes = ZoneOffset.ofHoursMinutes(5, 30);
ZoneOffset utc = ZoneOffset.UTC;
```

Đây là đoạn minh họa với `import java.time.ZoneOffset;`. Cả `plusSeven` và `same` đều là offset +7 giờ, còn `withMinutes` là +05:30.

Java cho phép offset trong khoảng **-18:00 tới +18:00**, với phần giờ/phút/giây hợp lệ và nhất quán về dấu. Offset như `+19:00` hoặc `+07:60` bị từ chối bằng `DateTimeException`. Phạm vi đối tượng `ZoneOffset` lớn hơn phần lớn offset được dùng trong thực tế; không phải mọi offset có thể biểu diễn đều được một vùng địa lý sử dụng.

Cần phân biệt:

- `ZoneOffset.of("+07:00")` có offset cố định, không biết DST.
- `ZoneId.of("Asia/Ho_Chi_Minh")` là ID **vùng** có dữ liệu quy tắc thời gian theo lịch sử và khả năng thay đổi chính sách tương lai.
- Hai giá trị có thể cùng offset tại một instant, nhưng không là đại diện có thể hoán đổi cho mọi ngày.

## 5. Đọc các thành phần và chuyển về Instant

Từ một `OffsetDateTime`, lấy các thành phần:

```java
OffsetDateTime event = OffsetDateTime.parse(
        "2024-07-15T09:30:45.123456789+02:00");

LocalDateTime local = event.toLocalDateTime();
LocalDate date = event.toLocalDate();
LocalTime time = event.toLocalTime();
ZoneOffset offset = event.getOffset();
Instant instant = event.toInstant();
long epochSecond = event.toEpochSecond();
```

Đây là đoạn minh họa cần import `OffsetDateTime`, `LocalDateTime`, `LocalDate`, `LocalTime`, `ZoneOffset` và `Instant`. Giá trị:

- `local` = `2024-07-15T09:30:45.123456789`.
- `offset` = `+02:00`.
- `instant` = `2024-07-15T07:30:45.123456789Z`.
- `epochSecond` đếm **giây nguyên** từ Unix epoch, không phải mili giây.

**Quan trọng:** `toLocalDateTime()` làm mất offset; nếu chỉ lưu nó, bạn không thể tự khôi phục chính xác instant cũ. `toInstant()` giữ mốc tuyệt đối nhưng bỏ cách biểu diễn local/offset đã được chọn; muốn tái dựng cùng biểu diễn, phải lưu thêm offset.

## 6. Thay đổi offset: giữ instant hay giữ local time?

Hai phương thức dễ gây sai lệch lớn nhất khi xử lý `OffsetDateTime`:

- `withOffsetSameInstant(newOffset)`: **giữ nguyên instant** (thời điểm tuyệt đối), thay giờ hiển thị theo offset mới.
- `withOffsetSameLocal(newOffset)`: **giữ nguyên các thành phần ngày-giờ địa phương**, thay offset và do đó **thay instant**.

Đây là lựa chọn nghiệp vụ rất khác nhau.

Giả sử thời điểm gốc là `2024-07-15T09:30+02:00`:

| Cách dùng | Kết quả | Instant |
| --- | --- | --- |
| Gốc | `09:30+02:00` | `07:30Z` |
| `withOffsetSameInstant(UTC)` | `07:30Z` | Vẫn `07:30Z` |
| `withOffsetSameLocal(UTC)` | `09:30Z` | Đổi thành `09:30Z` |
| `withOffsetSameInstant(+07:00)` | `14:30+07:00` | Vẫn `07:30Z` |

Lưu chương trình **`OffsetConversionDemo.java`**:

```java
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

public class OffsetConversionDemo {
    public static void main(String[] args) {
        OffsetDateTime original = OffsetDateTime.of(
                2024, 7, 15, 9, 30, 0, 0,
                ZoneOffset.ofHours(2));

        OffsetDateTime sameInstant =
                original.withOffsetSameInstant(ZoneOffset.UTC);
        OffsetDateTime sameLocal =
                original.withOffsetSameLocal(ZoneOffset.UTC);
        OffsetDateTime vietnam =
                original.withOffsetSameInstant(ZoneOffset.ofHours(7));

        System.out.println("original = " + original);
        System.out.println("sameInstant = " + sameInstant);
        System.out.println("sameLocal = " + sameLocal);
        System.out.println("vietnam = " + vietnam);
        System.out.println("originalInstant = " + original.toInstant());
        System.out.println("sameInstantUtc = " + sameInstant.toInstant());
        System.out.println("sameLocalUtc = " + sameLocal.toInstant());
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac OffsetConversionDemo.java
java OffsetConversionDemo
```

Đầu ra xác định:

```text
original = 2024-07-15T09:30+02:00
sameInstant = 2024-07-15T07:30Z
sameLocal = 2024-07-15T09:30Z
vietnam = 2024-07-15T14:30+07:00
originalInstant = 2024-07-15T07:30:00Z
sameInstantUtc = 2024-07-15T07:30:00Z
sameLocalUtc = 2024-07-15T09:30:00Z
```

Giải thích: nếu người dùng muốn xem **cùng một sự kiện** tại nơi khác, hãy giữ instant. Nếu nghiệp vụ chủ động muốn tái gán một giờ địa phương cố định sang một offset khác, khi đó `withOffsetSameLocal()` mới phù hợp.

Cả hai phương thức đều trả về giá trị **mới** và không sửa `original`.

## 7. Chuyển từ OffsetDateTime sang vùng có quy tắc DST

`OffsetDateTime` không có `ZoneId` vùng. Khi cần hiển thị cùng thời điểm theo múi giờ của người khác:

```java
OffsetDateTime event = OffsetDateTime.parse(
        "2024-07-15T09:30+02:00");

ZonedDateTime inVietnam = event.atZoneSameInstant(
        ZoneId.of("Asia/Ho_Chi_Minh"));
// 2024-07-15T14:30+07:00[Asia/Ho_Chi_Minh]
```

Đây là đoạn minh họa có import `OffsetDateTime`, `ZonedDateTime` và `ZoneId`. Chữ **SameInstant** nêu rõ giữ nguyên thời điểm UTC.

`event.toZonedDateTime()` tạo `ZonedDateTime` dựa trên offset hiện có (dùng offset như một zone), nhưng **không tự khôi phục ID vùng ban đầu**. Ví dụ `09:30+02:00` có thể ứng với nhiều vùng khác nhau; từ riêng offset không thể kết luận nó nhất thiết thuộc Paris hay thành phố nào.

Khi nghiệp vụ nói “lịch họp lặp vào 9 giờ sáng mỗi ngày theo múi giờ Paris”, chỉ lưu `+02:00` là chưa đủ: mùa đông offset Paris có thể là `+01:00`. Hãy lưu `ZoneId.of("Europe/Paris")` cùng quy tắc lịch hẹn và xử lý DST. `OffsetDateTime` phù hợp hơn để **đóng dấu một lần theo offset tại thời điểm tạo/trao đổi**, hoặc khi hợp đồng dữ liệu thật sự là local time + fixed offset.

## 8. Phân tích chuỗi bằng parse()

`OffsetDateTime.parse(text)` mặc định đọc định dạng ISO-8601 có offset:

```java
OffsetDateTime a = OffsetDateTime.parse(
        "2024-07-15T09:30:00+02:00");

OffsetDateTime b = OffsetDateTime.parse(
        "2024-07-15T07:30:00Z");
```

Đây là đoạn minh họa cần `import java.time.OffsetDateTime;`. Cả hai là cùng một instant nhưng hai biểu diễn local khác nhau.

Một chuỗi chỉ có ngày và giờ như `2024-07-15T09:30` **không đủ** để parse trực tiếp thành `OffsetDateTime` bằng formatter ISO mặc định vì thiếu offset. Nếu muốn nhận dữ liệu kiểu đó, API phải có trường offset hoặc `ZoneId` riêng, và tạo giá trị sau khi xác định quy tắc.

Parse sai cú pháp hoặc thiếu phần bắt buộc sẽ ném `DateTimeParseException` (thuộc `DateTimeException`).

### Parse theo định dạng tự xác định

Khi hợp đồng đầu vào không dùng chữ `T`, có thể khai báo `DateTimeFormatter`:

```java
DateTimeFormatter formatter = DateTimeFormatter.ofPattern(
        "uuuu-MM-dd HH:mm XXX");

OffsetDateTime value = OffsetDateTime.parse(
        "2024-07-15 09:30 +02:00", formatter);
```

Đây là đoạn minh họa trong một phương thức, cần import `java.time.format.DateTimeFormatter` và `OffsetDateTime`. Với ký hiệu `XXX`, formatter biểu diễn offset theo dạng ISO như `+02:00` hoặc `Z` cho UTC.

Đừng để formatter “tự đoán” múi giờ khi đầu vào không có offset. Nếu API cần nhận dạng vùng như `Europe/Paris`, hãy dùng formatter/schema có trường vùng và xử lý sang `ZonedDateTime` hoặc instant theo mục đích.

## 9. Định dạng hiển thị và serializing

`OffsetDateTime.toString()` tạo văn bản ISO phù hợp độ chi tiết của giá trị:

```java
OffsetDateTime time = OffsetDateTime.of(
        2024, 7, 15, 9, 30, 0, 0,
        ZoneOffset.ofHours(2));

System.out.println(time);
// 2024-07-15T09:30+02:00
```

Đây là đoạn minh họa trong một phương thức. Vì giây và nano đều bằng 0, `toString()` có thể bỏ phần `:00` giây, nhưng **giá trị offset vẫn được giữ**.

Khi dùng `DateTimeFormatter.ISO_OFFSET_DATE_TIME`, ta có dạng ISO có offset. Nếu muốn định dạng trình bày cho người dùng:

```java
DateTimeFormatter display = DateTimeFormatter.ofPattern(
        "dd/MM/uuuu HH:mm XXX");

String rendered = time.format(display);
// "15/07/2024 09:30 +02:00"
```

Đây là đoạn minh họa, cần import `DateTimeFormatter`. Định dạng chỉ biến giá trị thành chuỗi để hiển thị, **không đổi instant hoặc offset** trong object gốc.

Khi xuất JSON hoặc gửi qua API, ghi rõ hợp đồng, ví dụ trường `occurredAt` chứa chuỗi ISO offset date-time. Tránh một chuỗi `2024-07-15 09:30` thiếu offset nếu bên nhận cần một thời điểm duy nhất. Nếu framework tự serialize `OffsetDateTime`, xác nhận cấu hình thực tế và kiểm tra round-trip (serialize → deserialize).

## 10. So sánh: equals(), isEqual(), isBefore(), compareTo()

Một sự khác biệt rất quan trọng là **bằng nhau về giá trị đầy đủ** so với **cùng thời điểm trên timeline**.

Cho:

```java
OffsetDateTime a = OffsetDateTime.parse(
        "2024-07-15T09:30+02:00");
OffsetDateTime b = OffsetDateTime.parse(
        "2024-07-15T07:30Z");
```

Hai giá trị có cùng instant. Tuy nhiên:

- `a.equals(b)` trả `false`: `equals()` xét cả **local date-time và offset**.
- `a.isEqual(b)` trả `true`: `isEqual()` so sánh **instant**.
- `a.isBefore(b)` và `a.isAfter(b)` đều trả `false`: cùng instant.
- `a.compareTo(b)` có thể **khác 0** khi offset/local khác nhau dù cùng instant, vì thứ tự tự nhiên trước hết theo instant, sau đó phân biệt local date-time để nhất quán với `equals()`.

Lưu **`OffsetComparisonDemo.java`**:

```java
import java.time.OffsetDateTime;

public class OffsetComparisonDemo {
    public static void main(String[] args) {
        OffsetDateTime a = OffsetDateTime.parse(
                "2024-07-15T09:30+02:00");
        OffsetDateTime b = OffsetDateTime.parse(
                "2024-07-15T07:30Z");

        System.out.println("equals = " + a.equals(b));
        System.out.println("isEqual = " + a.isEqual(b));
        System.out.println("isBefore = " + a.isBefore(b));
        System.out.println("compareTo = " + a.compareTo(b));
        System.out.println("sameInstant = "
                + a.toInstant().equals(b.toInstant()));
    }
}
```

Chạy:

```bash
javac OffsetComparisonDemo.java
java OffsetComparisonDemo
```

Kết quả xác định:

```text
equals = false
isEqual = true
isBefore = false
compareTo = 1
sameInstant = true
```

**Hệ quả cho collections:** Hai `OffsetDateTime` cùng instant nhưng offset khác nhau có thể là **hai khóa khác nhau** trong `HashMap` hoặc hai phần tử khác nhau trong `TreeSet` với thứ tự tự nhiên. Nếu định danh nghiệp vụ là **instant**, nên chuẩn hóa sang `Instant` làm khóa hoặc dùng comparator theo instant, đồng thời xác định rõ cách xử lý trường hợp hai biểu diễn khác nhau của cùng instant.

## 11. Cộng, trừ và thay thành phần

`OffsetDateTime` có những phương thức tương tự `LocalDateTime`:

```java
OffsetDateTime start = OffsetDateTime.parse(
        "2024-01-31T10:15+07:00");

OffsetDateTime afterOneDay = start.plusDays(1);
// 2024-02-01T10:15+07:00

OffsetDateTime afterOneMonth = start.plusMonths(1);
// 2024-02-29T10:15+07:00

OffsetDateTime newHour = start.withHour(9);
// 2024-01-31T09:15+07:00

OffsetDateTime priorMinutes = start.minusMinutes(30);
// 2024-01-31T09:45+07:00
```

Đây là đoạn minh họa trong phương thức với `OffsetDateTime` đã import. Các phương thức này không sửa giá trị gốc, giữ offset nếu thao tác không yêu cầu đổi offset.

**Phân biệt ý nghĩa:** Vì offset của `OffsetDateTime` là **cố định trong giá trị**, cộng một ngày như `plusDays(1)` không tự cập nhật quy tắc DST của một vùng. Nếu cần lịch sự kiện theo quy tắc `ZoneId`, dùng `ZonedDateTime`.

Các phép cộng/trừ theo tháng lịch xử lý tháng 28/29/30/31 ngày theo quy tắc `java.time`. `plusMonths(1)` từ 31/1/2024 dẫn tới 29/2/2024; không tương đương cộng 30 ngày.

## 12. Chuẩn hóa về UTC và giữ nguyên thời điểm

Khi cần biểu diễn cùng instant với UTC:

```java
OffsetDateTime value = OffsetDateTime.parse(
        "2024-07-15T09:30+02:00");
OffsetDateTime utcView =
        value.withOffsetSameInstant(ZoneOffset.UTC);

System.out.println(utcView);   // 2024-07-15T07:30Z
System.out.println(value.toInstant()); // 2024-07-15T07:30:00Z
```

Đây là đoạn minh họa cần `OffsetDateTime` và `ZoneOffset`. Hai giá trị có **cùng instant**, nhưng kiểu `OffsetDateTime` vẫn biểu diễn phần ngày-giờ với offset UTC, còn `Instant` là mốc tuyệt đối.

Trong cơ sở dữ liệu hoặc hệ thống phân tán:

- Nếu chỉ cần thứ tự thời điểm, phép so sánh, hoặc dấu thời gian sự kiện, **`Instant`** thường đơn giản.
- Nếu hợp đồng của API cần cả phần ngày giờ và offset cụ thể như đã ghi nhận, **`OffsetDateTime`** mang ngữ nghĩa đó.
- Nếu quy tắc hẹn lặp theo giờ địa phương ở một nơi, cần **`ZoneId`** bổ sung, thường dùng `ZonedDateTime` hoặc dữ liệu ngày/giờ địa phương + ID vùng.

Không coi việc chuẩn hóa offset về UTC là phép biến đổi giá trị “không thay đổi” ở mức `equals()`. Nó giữ **instant**, nhưng phần local và offset thường thay đổi.

## 13. Một đoạn mã đầy đủ: tạo, parse, chuyển đổi và đọc thời điểm

Lưu file **`OffsetDateTimeOverviewDemo.java`**:

```java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

public class OffsetDateTimeOverviewDemo {
    public static void main(String[] args) {
        OffsetDateTime meeting = OffsetDateTime.of(
                2024, 7, 15, 9, 30, 0, 0,
                ZoneOffset.ofHours(2));

        Instant instant = meeting.toInstant();
        OffsetDateTime inVietnam = meeting.withOffsetSameInstant(
                ZoneOffset.ofHours(7));
        ZonedDateTime inVietnamZone = meeting.atZoneSameInstant(
                ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("meeting = " + meeting);
        System.out.println("instant = " + instant);
        System.out.println("vietnamOffset = " + inVietnam);
        System.out.println("vietnamZone = " + inVietnamZone);
        System.out.println("local = " + meeting.toLocalDateTime());
        System.out.println("offset = " + meeting.getOffset());
        System.out.println("epochSecond = " + meeting.toEpochSecond());
    }
}
```

Chạy:

```bash
javac OffsetDateTimeOverviewDemo.java
java OffsetDateTimeOverviewDemo
```

Đầu ra xác định theo bộ quy tắc múi giờ thông dụng:

```text
meeting = 2024-07-15T09:30+02:00
instant = 2024-07-15T07:30:00Z
vietnamOffset = 2024-07-15T14:30+07:00
vietnamZone = 2024-07-15T14:30+07:00[Asia/Ho_Chi_Minh]
local = 2024-07-15T09:30
offset = +02:00
epochSecond = 1721028600
```

Kết quả `epochSecond` là số giây từ mốc `1970-01-01T00:00:00Z`, không phải nano/mili giây. Nếu cần độ chính xác phần giây, giữ `Instant` hoặc dùng các API hỗ trợ phần nano.

## 14. Dữ liệu gửi qua hệ thống: mất offset và bảo toàn instant

Giả sử dịch vụ A gửi chuỗi `2024-07-15T09:30+02:00` tới B:

- Nếu B parse thành `OffsetDateTime`, B có **cả giờ địa phương và offset**.
- Nếu B gọi `toInstant()`, B giữ được **mốc tuyệt đối**, nhưng không biết người gửi đã chọn +02:00.
- Nếu B gọi `toLocalDateTime()` và chỉ lưu nó, B mất **thông tin offset** và không còn cách duy nhất để khôi phục instant.

Một lỗi thường gặp là nhận `OffsetDateTime` rồi làm:

```java
OffsetDateTime received = OffsetDateTime.parse(
        "2024-07-15T09:30+02:00");

LocalDateTime lostOffset = received.toLocalDateTime();

// Sai nếu tự giả định múi giờ của server là vùng thời gian gốc:
OffsetDateTime reinterpreted = lostOffset.atOffset(ZoneOffset.UTC);
```

Đây là đoạn minh họa, cần import `OffsetDateTime`, `LocalDateTime`, `ZoneOffset`. `reinterpreted` là `2024-07-15T09:30Z`, tức **instant 09:30Z**, lệch hai giờ so với instant gốc `07:30Z`.

Vì vậy khi thiết kế DTO, database và mapping, hãy quyết định có cần giữ **instant**, **offset**, **local time** và/hoặc **ZoneId** trước khi lựa chọn kiểu cột/kiểu dữ liệu. Đừng suy luận những thông tin không được lưu.

## 15. Lỗi phổ biến và kiểm thử

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ `+07:00` là ID vùng Việt Nam | Mất lịch sử và quy tắc vùng | Dùng `ZoneId` vùng khi cần chính sách theo địa điểm |
| Gọi `withOffsetSameLocal()` để hiển thị cùng sự kiện ở nơi khác | Thay đổi instant | Dùng `withOffsetSameInstant()` |
| Dùng `equals()` để kiểm tra hai biểu diễn có cùng instant | Kết quả có thể false | Dùng `isEqual()` hoặc so `toInstant()` |
| Bỏ offset bằng `toLocalDateTime()` rồi mặc định UTC | Sai mốc thời gian | Giữ offset hoặc chuyển thẳng sang `Instant` |
| Parse chuỗi thiếu offset thành `OffsetDateTime` | `DateTimeParseException` | Bổ sung offset/zone trong hợp đồng |
| Coi offset tại hiện tại luôn đúng cho lịch họp ở tháng khác | Sai trong vùng có DST | Lưu ZoneId và áp dụng quy tắc theo ngày |
| Dùng `now()` trong test có expected output cố định | Không tái lập được | Dùng `Clock.fixed(...)` hoặc thời điểm `of(...)` |
| Coi `toEpochSecond()` là milliseconds | Lệch hệ số 1.000 | Ghi rõ đơn vị hoặc chuyển từ `Instant` theo hợp đồng |
| Cho rằng lưu OffsetDateTime trong mọi DB luôn giữ nguyên offset | Có thể bị chuẩn hóa hoặc mất offset | Kiểm thử round-trip theo driver, kiểu cột và cấu hình cụ thể |

Các trường hợp nên kiểm thử:

1. Hai biểu diễn offset khác nhau nhưng cùng instant.
2. Cùng local date-time nhưng offset khác nhau.
3. Nửa đêm, thay ngày khi đổi offset và thời điểm trước Unix epoch.
4. Parse/format ISO với `Z`, `+07:00` và phần nano.
5. Offset ngoài phạm vi hợp lệ (ví dụ `+19:00`).
6. Chuyển theo `Europe/Paris` vào mùa đông/hè và quanh DST gap/overlap.
7. Mapping database/JSON giữ hay bỏ offset đúng theo hợp đồng.

## 16. Bài tập tự kiểm tra

**Câu 1.** `2024-07-15T09:30+02:00` tương đương instant nào?

**Đáp án:** `2024-07-15T07:30:00Z`, vì offset +02:00 nhanh hơn UTC hai giờ.

**Câu 2.** Gọi `withOffsetSameInstant(ZoneOffset.ofHours(7))` trên giá trị câu 1 cho kết quả gì?

**Đáp án:** `2024-07-15T14:30+07:00`, giữ nguyên instant `07:30Z`.

**Câu 3.** Gọi `withOffsetSameLocal(ZoneOffset.UTC)` trên giá trị câu 1 thì instant có đổi không?

**Đáp án:** Có. Giữ `09:30` và đổi offset về `Z`, nên instant chuyển từ `07:30Z` sang `09:30Z`.

**Câu 4.** Hai `OffsetDateTime` có cùng `toInstant()` nhưng offset khác nhau có `equals() == true` không?

**Đáp án:** Không nhất thiết; `equals()` còn xét local date-time và offset. `isEqual()` kiểm tra cùng instant.

**Câu 5.** Dùng `OffsetDateTime` có đủ để lập lịch lặp “09:00 mỗi ngày tại Paris” không?

**Đáp án:** Chưa đủ. Cần `ZoneId` vùng `Europe/Paris` để áp dụng quy tắc DST khi ngày thay đổi.

**Câu 6.** Có thể parse `2024-07-15T09:30` trực tiếp bằng `OffsetDateTime.parse(...)` mặc định không?

**Đáp án:** Không; chuỗi thiếu độ lệch UTC. Cần offset hoặc chính sách lấy zone/offset từ một nguồn khác được xác định rõ.

**Ghi nhớ:** `OffsetDateTime` chứa **ngày-giờ địa phương + UTC offset**, vì vậy xác định được một instant. Khi muốn thay cách hiển thị của **cùng sự kiện**, dùng `withOffsetSameInstant()`. Khi chủ ý gắn lại một giờ địa phương sang offset khác, dùng `withOffsetSameLocal()`. Offset là một con số cố định; lịch hẹn theo vùng và DST cần ID múi giờ qua `ZoneId`.