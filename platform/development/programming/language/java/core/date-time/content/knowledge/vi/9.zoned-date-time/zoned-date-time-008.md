# Đổi múi giờ giữ nguyên thời điểm với ZonedDateTime.withZoneSameInstant()

Trong Java, `ZonedDateTime` biểu diễn **ngày, giờ địa phương kèm một `ZoneId` và offset đã được phân giải**. Khi muốn xem **cùng một sự kiện** theo giờ của quốc gia, thành phố hoặc hệ thống khác, dùng:

```java
ZonedDateTime converted = original.withZoneSameInstant(targetZone);
```

Phương thức `withZoneSameInstant(ZoneId zone)` trả một `ZonedDateTime` mới ở vùng đích, **bảo toàn tuyệt đối cùng một `Instant`** (*thời điểm trên trục thời gian*). Vì vậy, giờ, ngày lịch và offset hiển thị có thể thay đổi, nhưng sự kiện không “di chuyển” sớm hoặc muộn hơn trong thực tế.

Điểm cần phân biệt ngay từ đầu:

- **`withZoneSameInstant(zone)`:** giữ **thời điểm thực**, đổi **ngày giờ hiển thị** theo vùng.
- **`withZoneSameLocal(zone)`:** cố giữ **ngày giờ trên đồng hồ** khi thay vùng; **thời điểm thực thường đổi**.
- **`withFixedOffsetZone()`:** giữ giá trị ngày giờ và offset hiện có, nhưng thay zone vùng thành một zone offset cố định; không phải công cụ để đổi múi giờ hiển thị sang một vùng khác.

Bài học tập trung vào `withZoneSameInstant()`, cơ chế, ví dụ Java 17+ chạy được, xử lý DST, sự khác biệt với thao tác đổi local, và cách áp dụng trong ứng dụng.

## 1. Ba lớp ý nghĩa của ZonedDateTime

`ZonedDateTime` liên kết ba thông tin:

1. **Ngày giờ địa phương (`LocalDateTime`):** chẳng hạn `2024-03-10T03:30`.
2. **Zone ID (`ZoneId`):** chẳng hạn `America/New_York` hoặc `Asia/Ho_Chi_Minh`. Với ID vùng, các quy tắc của nó xác định offset theo từng thời điểm.
3. **Offset (`ZoneOffset`):** ví dụ `-04:00` hoặc `+07:00`, cho biết chênh lệch với UTC tại thời điểm đó.

Khi đã phân giải các thành phần phù hợp với quy tắc vùng, `ZonedDateTime` xác định một **`Instant` duy nhất**. Có thể lấy nó bằng `toInstant()`.

Ví dụ:

```java
import java.time.*;

Instant moment = Instant.parse("2024-03-10T07:30:00Z");

ZonedDateTime newYork = moment.atZone(
        ZoneId.of("America/New_York"));
ZonedDateTime vietnam = moment.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(newYork);
// 2024-03-10T03:30-04:00[America/New_York]
System.out.println(vietnam);
// 2024-03-10T14:30+07:00[Asia/Ho_Chi_Minh]
```

Hai biểu diễn có giờ đồng hồ chênh nhau **11 giờ** tại thời điểm này nhưng cùng chỉ đến `2024-03-10T07:30:00Z`. New York đã chuyển sang offset mùa hè `-04:00` vào ngày 10/03/2024. Vì thế, không thể mặc định chênh lệch giữa hai vùng là một số giờ không đổi suốt năm.

## 2. withZoneSameInstant() thực sự làm gì?

Cú pháp:

```java
ZonedDateTime result = source.withZoneSameInstant(destination);
```

- `source` là một `ZonedDateTime` đã xác định thời điểm thực.
- `destination` là `ZoneId` đích, có thể là ID vùng IANA (như `Europe/Paris`), `ZoneOffset` hoặc `ZoneId.of("UTC")`.
- Kết quả là một **đối tượng mới**. `ZonedDateTime` là kiểu **immutable**; `source` không bị sửa.
- Bất biến quan trọng: **`source.toInstant().equals(result.toInstant())` luôn là `true` khi phép chuyển thành công**.
- Offset đích được tra theo **quy tắc vùng đích tại chính `Instant` đó**, không sao chép offset nguồn.

Có thể hiểu thuật toán về mặt khái niệm như sau:

```text
source ZonedDateTime
       |
       | source.toInstant()
       v
   một Instant duy nhất
       |
       | tra ZoneRules của destination tại Instant này
       v
new ZonedDateTime: local date-time + offset + destination ZoneId
```

Sơ đồ giải thích **ý nghĩa** chứ không phải mã nguồn nội bộ Java. Do mốc `Instant` được giữ, phép chuyển không bị “mơ hồ” ngay cả khi giờ địa phương đích rơi vào ngày chuyển DST: một `Instant` luôn tương ứng một offset áp dụng tại vùng đích, dù hai `Instant` khác nhau có thể hiển thị cùng giờ địa phương trong một *overlap*.

### Biểu thức tương đương để kiểm tra tư duy

```java
ZonedDateTime converted = source.withZoneSameInstant(destination);

Instant originalInstant = source.toInstant();
ZonedDateTime reconstructed = originalInstant.atZone(destination);
// converted và reconstructed biểu diễn cùng Instant trong cùng zone đích.
```

Đây là đoạn minh họa sử dụng `source` và `destination` đã có từ bên ngoài, cần import `java.time.*`. Dùng trực tiếp `withZoneSameInstant` trên một `ZonedDateTime` là cách diễn đạt rõ ràng nhất khi yêu cầu là **đổi vùng hiển thị cho một sự kiện đang có zone**.

## 3. Chuyển từ New York sang Việt Nam tại một thời điểm xác định

Giả sử một thông báo xảy ra lúc `2024-03-10T07:30:00Z`. Tại New York, khi ấy là 03:30 sau khi bắt đầu DST; tại Việt Nam là 14:30 cùng ngày.

```java
ZoneId newYork = ZoneId.of("America/New_York");
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime ny = Instant
        .parse("2024-03-10T07:30:00Z")
        .atZone(newYork);

ZonedDateTime vn = ny.withZoneSameInstant(vietnam);

System.out.println(ny);
// 2024-03-10T03:30-04:00[America/New_York]
System.out.println(vn);
// 2024-03-10T14:30+07:00[Asia/Ho_Chi_Minh]

System.out.println(ny.toInstant().equals(vn.toInstant()));
// true
```

Đây là đoạn minh họa cần import `java.time.*`. Nhận xét:

- **Giờ đồng hồ đổi** từ 03:30 sang 14:30 vì các vùng có offset khác nhau.
- **Offset đổi** từ `-04:00` sang `+07:00`, lấy theo quy tắc của từng vùng tại thời điểm đó.
- **Zone ID đổi** từ `America/New_York` sang `Asia/Ho_Chi_Minh`.
- **`Instant` giữ nguyên**: không có sự kiện mới và không cộng 11 giờ vào sự kiện thực.

Phép đổi này phù hợp cho hệ thống lưu một sự kiện và hiển thị cho người dùng ở nhiều nơi: trang chi tiết giao dịch, thông báo, lịch sử thao tác, bảng điều khiển hoặc nhật ký vận hành.

## 4. So với withZoneSameLocal(): hai nhu cầu khác nhau

Hai API rất dễ nhầm vì đều có tên `withZone…`, nhưng lựa chọn **thứ phải bảo toàn** trái ngược.

| Yêu cầu | Dùng phương thức | Điều được giữ |
| --- | --- | --- |
| “Hiển thị cùng giao dịch theo giờ Việt Nam” | `withZoneSameInstant(vietnam)` | `Instant` |
| “Đổi địa điểm hẹn nhưng vẫn muốn 09:00 giờ địa phương tại địa điểm mới” | `withZoneSameLocal(newZone)` hoặc tạo lịch hẹn theo giờ địa phương với chính sách phù hợp | `LocalDateTime` nếu giờ đó hợp lệ trong zone đích |
| “Cho tôi xem giờ UTC của sự kiện này” | `withZoneSameInstant(ZoneOffset.UTC)` | `Instant` |
| “Chỉ thay vùng nhưng đừng thay mặt đồng hồ” | `withZoneSameLocal(newZone)` | Giờ đồng hồ là mục tiêu, còn `Instant` thường khác |

Cùng nguồn New York `2024-03-10T03:30-04:00[America/New_York]`:

```java
ZonedDateTime sameInstant = ny.withZoneSameInstant(vietnam);
// 2024-03-10T14:30+07:00[Asia/Ho_Chi_Minh]

ZonedDateTime sameLocal = ny.withZoneSameLocal(vietnam);
// 2024-03-10T03:30+07:00[Asia/Ho_Chi_Minh]
```

Kết quả `sameInstant` vẫn là `2024-03-10T07:30Z`. Kết quả `sameLocal` là `2024-03-09T20:30Z`: cùng chữ số 03:30 tại Việt Nam tương ứng một thời điểm **khác**.

**Lưu ý quan trọng:** `withZoneSameLocal` không phải lúc nào cũng giữ được nguyên giờ địa phương. Nếu giờ đồng hồ đó thuộc **DST gap** của zone đích, API có thể tự điều chỉnh sang giờ hợp lệ; nếu ở **DST overlap**, API phân giải offset theo quy tắc. Vì vậy, đối với lịch hẹn có yêu cầu cứng “đúng 02:30”, cần chính sách kiểm tra `ZoneRules` trước khi áp dụng. Với nhu cầu **giữ thời điểm**, dùng `withZoneSameInstant` là chính xác và không cần lựa chọn offset mơ hồ.

### Đừng nhầm với withFixedOffsetZone()

`source.withFixedOffsetZone()` tạo biểu diễn có zone ID là **offset hiện tại** của `source`. Đây thường là thao tác “cố định hóa” zone, tránh việc quy tắc vùng ảnh hưởng tới các tính toán về sau; nó **không** có nghĩa “chuyển sang UTC” hay “chuyển đến một quốc gia khác”.

Ví dụ tại thời điểm New York có offset `-04:00`, `withFixedOffsetZone()` giữ offset `-04:00` thành zone cố định. Một thời điểm khác trong mùa đông ở New York có thể cần `-05:00`, nhưng đối tượng đã chuyển sang fixed-offset zone sẽ không tự đổi sang `-05:00`.

## 5. Ngày lịch có thể thay đổi khi giữ nguyên Instant

Việc đổi vùng có thể khiến thời gian hiển thị **sang ngày trước hoặc ngày sau**. Đây là hành vi đúng.

Ví dụ một sự kiện diễn ra vào 00:30 ngày 01/01/2024 tại Việt Nam:

```java
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime vietnamNewYear = ZonedDateTime.of(
        2024, 1, 1, 0, 30, 0, 0, vietnam);

ZonedDateTime utcView = vietnamNewYear
        .withZoneSameInstant(ZoneOffset.UTC);

System.out.println(vietnamNewYear);
// 2024-01-01T00:30+07:00[Asia/Ho_Chi_Minh]
System.out.println(utcView);
// 2023-12-31T17:30Z
```

Đây là đoạn minh họa cần import `java.time.*`. **Cùng một sự kiện thực**, nhưng ở Việt Nam là **01/01/2024** và theo UTC là **31/12/2023**. Nếu dùng `toLocalDate()` trước hoặc sau phép chuyển, ngày thu được có thể khác nhau:

```java
LocalDate vietnamDate = vietnamNewYear.toLocalDate(); // 2024-01-01
LocalDate utcDate = utcView.toLocalDate();             // 2023-12-31
```

Đoạn minh họa cần import `java.time.LocalDate` và có hai biến từ ví dụ trước. Khi tính **ngày kế toán**, **ngày hết hạn**, **phân nhóm báo cáo** hoặc **hạn chót cuối ngày**, phải xác định zone nghiệp vụ trước khi lấy ngày. Không nên lấy ngày UTC rồi chỉ đổi chuỗi hiển thị nếu quy tắc thực tế là “ngày tại Hà Nội”.

## 6. DST: vì sao không thể tự cộng một số giờ cố định?

`ZoneId.of("America/New_York")` và `ZoneId.of("Europe/Paris")` không đơn thuần là những con số như `-05:00` hoặc `+01:00`. Chúng dùng cơ sở dữ liệu quy tắc múi giờ (`ZoneRules`), có thể thay đổi theo ngày, giờ và lịch sử.

Tại New York vào năm 2024:

- Ngày `2024-01-15T12:00:00Z`: offset là `-05:00`.
- Ngày `2024-07-15T12:00:00Z`: offset là `-04:00`.

Nếu bạn viết:

```java
// Sai về mặt thiết kế khi offset cần tuân theo quy tắc New York:
ZonedDateTime newYorkLike = instant.atZone(ZoneOffset.of("-05:00"));
```

thì Java sẽ luôn dùng `-05:00` vì đây là **fixed offset**, ngay cả khi mùa hè ở New York thực tế là `-04:00`. Để xử lý giờ của **thành phố**, dùng:

```java
ZonedDateTime accurateNewYork = instant.atZone(
        ZoneId.of("America/New_York"));
```

Cả hai đoạn trên giả định biến `instant` kiểu `Instant` đã được khai báo, cần import `java.time.*`. Ngay cả khi hiện tại một quốc gia ít thay đổi offset, một `ZoneId` vùng vẫn mang ý nghĩa địa lý tốt hơn cho các quy tắc lịch/hẹn trong tương lai.

### Khi đổi vùng vào đúng ngày DST

Ngày 10/03/2024 tại New York, đồng hồ nhảy từ 01:59:59 sang 03:00:00. Giờ địa phương `2024-03-10T02:30` không tồn tại trong vùng này. Tuy nhiên, ta có thể bắt đầu từ một **`Instant` có thật**:

```java
Instant moment = Instant.parse("2024-03-10T07:30:00Z");
ZonedDateTime ny = moment.atZone(
        ZoneId.of("America/New_York"));
// 2024-03-10T03:30-04:00[America/New_York]
```

Sau đó `ny.withZoneSameInstant(ZoneId.of("Asia/Ho_Chi_Minh"))` chỉ cần tra offset tại **cùng thời điểm**, cho ra 14:30 Việt Nam. Không có bước “đoán” offset trong gap: giá trị đầu vào đã định danh một `Instant` hợp lệ.

Ở chiều ngược lại, nếu chỉ có **`LocalDateTime`** 02:30 New York vào ngày đó, phép tạo `LocalDateTime.of(2024, 3, 10, 2, 30).atZone(newYork)` sẽ **điều chỉnh** giờ không tồn tại sang 03:30 theo quy tắc mặc định của Java. Đây là vấn đề **phân giải local date-time với zone**, khác với việc đổi một `ZonedDateTime` đã có `Instant` bằng `withZoneSameInstant`.

### Overlap: hai giờ giống nhau vẫn có thể là hai thời điểm khác nhau

Vào ngày 03/11/2024 ở New York, giờ 01:30 xuất hiện hai lần, một lần với `-04:00` và một lần với `-05:00`. Hai `ZonedDateTime` đó có thể khác `Instant` dù cùng `LocalDateTime`.

```java
ZoneId newYork = ZoneId.of("America/New_York");
LocalDateTime local = LocalDateTime.of(2024, 11, 3, 1, 30);

ZonedDateTime earlier = local.atZone(newYork);
ZonedDateTime later = earlier.withLaterOffsetAtOverlap();

System.out.println(earlier.toInstant());
// 2024-11-03T05:30:00Z
System.out.println(later.toInstant());
// 2024-11-03T06:30:00Z
```

Đây là đoạn minh họa cần import `java.time.*`. Nếu chuyển hai giá trị trên sang Việt Nam bằng `withZoneSameInstant(vietnam)`, Java giữ **hai Instant khác nhau**, nên ở Việt Nam chúng cách nhau một giờ chứ không vô tình nhập lại làm một. Đây là điểm then chốt khi xử lý timestamp của giao dịch, nhật ký hoặc hệ thống phân tán.

## 7. Ví dụ Java 17+ hoàn chỉnh, có thể chạy trực tiếp

Tạo tệp **`ZoneSameInstantDemo.java`**:

```java
import java.time.*;

public class ZoneSameInstantDemo {
    public static void main(String[] args) {
        ZoneId newYork = ZoneId.of("America/New_York");
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

        Instant moment = Instant.parse("2024-03-10T07:30:00Z");
        ZonedDateTime ny = moment.atZone(newYork);
        ZonedDateTime vn = ny.withZoneSameInstant(vietnam);
        ZonedDateTime utc = ny.withZoneSameInstant(ZoneOffset.UTC);

        System.out.println("NY: " + ny);
        System.out.println("VN same instant: " + vn);
        System.out.println("UTC same instant: " + utc);
        System.out.println("Same instant? " + ny.toInstant().equals(vn.toInstant()));
        System.out.println("Same local time? "
                + ny.toLocalDateTime().equals(vn.toLocalDateTime()));

        ZonedDateTime sameLocal = ny.withZoneSameLocal(vietnam);
        System.out.println("VN same local: " + sameLocal);
        System.out.println("Same instant after sameLocal? "
                + ny.toInstant().equals(sameLocal.toInstant()));

        ZonedDateTime vnMidnight = ZonedDateTime.of(
                2024, 1, 1, 0, 30, 0, 0, vietnam);
        System.out.println("VN New Year: " + vnMidnight);
        System.out.println("UTC New Year: "
                + vnMidnight.withZoneSameInstant(ZoneOffset.UTC));

        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        ZonedDateTime adjustedNY = gap.atZone(newYork);
        System.out.println("NY gap resolved: " + adjustedNY);
        System.out.println("VN from resolved: "
                + adjustedNY.withZoneSameInstant(vietnam));
    }
}
```

Biên dịch và chạy:

```bash
javac ZoneSameInstantDemo.java
java ZoneSameInstantDemo
```

**stdout chính xác** (đã kiểm tra bằng `javac --release 17` và `java`):

```text
NY: 2024-03-10T03:30-04:00[America/New_York]
VN same instant: 2024-03-10T14:30+07:00[Asia/Ho_Chi_Minh]
UTC same instant: 2024-03-10T07:30Z
Same instant? true
Same local time? false
VN same local: 2024-03-10T03:30+07:00[Asia/Ho_Chi_Minh]
Same instant after sameLocal? false
VN New Year: 2024-01-01T00:30+07:00[Asia/Ho_Chi_Minh]
UTC New Year: 2023-12-31T17:30Z
NY gap resolved: 2024-03-10T03:30-04:00[America/New_York]
VN from resolved: 2024-03-10T14:30+07:00[Asia/Ho_Chi_Minh]
```

**Phân tích kết quả:**

1. Ba dòng đầu nhìn cùng `2024-03-10T07:30:00Z` từ New York, Việt Nam và UTC. Không có thay đổi mốc thời gian.
2. So sánh `toInstant()` là `true` dù `toLocalDateTime()` là `false`. Đây chính là ý nghĩa của `withZoneSameInstant`.
3. `withZoneSameLocal(vietnam)` trả cùng giờ 03:30 nhưng dịch `Instant` sang thời điểm khác. Không dùng nó để hiển thị cùng một sự kiện.
4. Đổi thời điểm gần nửa đêm của Việt Nam sang UTC tạo **ngày trước và năm trước**, là kết quả hợp lệ của cùng `Instant`.
5. Ngày DST gap New York: `LocalDateTime` 02:30 được giải quyết thành 03:30, rồi phép chuyển cùng `Instant` sang Việt Nam cho 14:30.

## 8. So sánh các ZonedDateTime khi đã chuyển vùng

Có ít nhất ba cách “so sánh” thường bị lẫn:

```java
ZonedDateTime a = Instant
        .parse("2024-03-10T07:30:00Z")
        .atZone(ZoneId.of("America/New_York"));
ZonedDateTime b = a.withZoneSameInstant(
        ZoneId.of("Asia/Ho_Chi_Minh"));

boolean sameInstant = a.toInstant().equals(b.toInstant()); // true
boolean equalInstant = a.isEqual(b);                       // true
boolean sameObjectValue = a.equals(b);                    // false
```

Đoạn minh họa cần import `java.time.*`.

- `toInstant().equals(...)` và `ZonedDateTime.isEqual(...)` kiểm tra **cùng một thời điểm**.
- `ZonedDateTime.equals(...)` yêu cầu thông tin ngày–giờ, offset và vùng giống nhau; đổi `ZoneId` khiến phép so sánh này thường là `false` dù hai giá trị xảy ra cùng lúc.
- `toLocalDateTime().equals(...)` chỉ kiểm tra **giờ lịch trông giống nhau**, không xác định cùng `Instant`.

Khi sắp xếp **sự kiện theo trình tự thực tế**, dùng `Instant` hoặc comparator của các thời điểm; không sắp xếp chỉ theo local date-time thu được từ các vùng khác nhau. Nếu muốn so sánh bản ghi dựa trên cùng thời điểm UTC, chuyển chúng sang `Instant` trước. Không dùng `equals` trên hai `ZonedDateTime` có vùng khác nhau như một phép thử duy nhất để kết luận “sự kiện khác nhau”.

## 9. Định dạng theo vùng và Locale: hai phụ thuộc độc lập

Sau khi chuyển vùng, có thể định dạng `ZonedDateTime` cho người dùng:

```java
ZonedDateTime userView = event.withZoneSameInstant(userZone);
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("dd/MM/uuuu HH:mm XXX '['VV']'", displayLocale);

String label = formatter.format(userView);
```

Đoạn này là mã **bên trong service**, giả định `event` kiểu `ZonedDateTime`, `userZone` kiểu `ZoneId`, `displayLocale` kiểu `Locale`; cần import `java.time.*`, `java.time.format.DateTimeFormatter` và `java.util.Locale`.

- **`ZoneId`** quyết định **ngày, giờ và offset nào** ở nơi người dùng muốn xem.
- **`Locale`** quyết định ngôn ngữ/quy ước định dạng khi pattern có trường phụ thuộc ngôn ngữ.
- **`DateTimeFormatter`** quyết định cách trình bày thành chuỗi; nó không nên là nơi ngầm quyết định lại giờ nghiệp vụ.

Nếu dữ liệu đến từ một `Instant`, bạn cũng có thể gọi `instant.atZone(userZone)`. Với dữ liệu đã là `ZonedDateTime`, `withZoneSameInstant(userZone)` diễn đạt chính xác “đổi cách hiển thị, giữ sự kiện”.

Không nên giả định múi giờ đích từ `Locale`. Người dùng sử dụng tiếng Việt có thể xem giờ ở New York; người dùng sử dụng tiếng Anh có thể cần giờ tại Việt Nam. Cấu hình ngôn ngữ và múi giờ phải độc lập.

## 10. Thiết kế lưu trữ, API và hệ thống phân tán

Trong hệ thống nhiều vùng, hãy xác định trường dữ liệu là **thời điểm đã xảy ra** hay **ý định lịch hẹn tương lai**.

### 10.1. Thời điểm sự kiện: lưu Instant, chuyển zone tại điểm hiển thị

Với `createdAt`, `paidAt`, `sentAt`, `completedAt` hoặc thời điểm ghi log:

```java
Instant stored = Instant.parse("2024-03-10T07:30:00Z");

ZoneId viewerZone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime displayed = stored.atZone(viewerZone);
// 2024-03-10T14:30+07:00[Asia/Ho_Chi_Minh]
```

Đây là đoạn minh họa cần import `java.time.*`. Dùng `Instant` giúp lưu một mốc độc lập với địa điểm. Nếu có sẵn `ZonedDateTime`, `withZoneSameInstant` đổi vùng hiển thị và `toInstant()` cho giá trị lưu trữ tuyệt đối.

Đối với JSON, một trường có nghĩa là timestamp tuyệt đối nên được biểu diễn rõ offset hoặc UTC:

```json
{
  "createdAt": "2024-03-10T07:30:00Z",
  "viewerZoneId": "Asia/Ho_Chi_Minh"
}
```

Có thể truyền thêm `ZoneId`/thông tin vùng khi thực sự cần. Không coi `"2024-03-10T07:30:00"` không có offset là một timestamp UTC nếu hợp đồng không nói vậy. Một `LocalDateTime` đơn độc không đủ dữ liệu để suy ra mốc `Instant`.

### 10.2. Ý định lịch hẹn địa phương: giữ zone và quy tắc nghiệp vụ

Một lịch hẹn tương lai “09:00 ngày 15/07 tại Paris” khác với việc hiển thị một sự kiện đã xảy ra ở Paris. Ở đây, **09:00 Paris** chính là ý định nghiệp vụ; phải kết hợp `LocalDateTime` và `ZoneId.of("Europe/Paris")` để tạo hoặc lưu lịch hẹn, chứ không đổi từ một `ZonedDateTime` khác bằng `withZoneSameInstant` nếu muốn giữ nguyên chữ số 09:00.

Với lịch lặp “09:00 mỗi thứ Hai ở Paris”, cần giữ quy tắc lặp, giờ địa phương và zone. DST khiến **thời điểm UTC tương ứng** thay đổi theo mùa. Việc chốt một offset hoặc một `Instant` rồi cứ cộng 7×24 giờ có thể làm giờ địa phương lệch trong thời gian dài.

### 10.3. Không phụ thuộc zone mặc định của JVM

Tránh viết:

```java
ZonedDateTime now = ZonedDateTime.now();
// Quy tắc thời gian đang phụ thuộc múi giờ mặc định của máy chạy.
```

Thay bằng một nguồn thời gian và vùng có hợp đồng rõ ràng:

```java
Clock clock = Clock.systemUTC(); // tạo ở điểm cấu hình hệ thống
Instant now = clock.instant();

ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime businessView = now.atZone(businessZone);
```

Đây là đoạn minh họa cần import `java.time.*`. Trong một service thực tế, `Clock` và `ZoneId` thường được **inject**; test truyền `Clock.fixed(...)` để giữ kết quả ổn định. Khi một giao dịch cần nhiều cách hiển thị, lấy **một `Instant`**, rồi chuyển sang từng vùng. Không gọi nhiều lần `now()` và giả định mỗi lần đúng cùng mốc.

## 11. Sai lầm phổ biến

| Sai lầm | Vì sao sai? | Cách đúng |
| --- | --- | --- |
| Dùng `withZoneSameLocal` để hiển thị cùng giao dịch ở vùng mới | Nó cố giữ giờ đồng hồ, có thể đổi sự kiện thực | `withZoneSameInstant(targetZone)` |
| Tự cộng/trừ offset bằng `plusHours` để đổi giờ | Thao tác số học thay đổi `Instant` và bỏ qua DST | `withZoneSameInstant` với `ZoneId` vùng |
| Dùng offset hiện tại của thành phố cho mọi ngày | DST/lịch sử vùng có thể thay đổi | Dùng `ZoneId.of("Area/City")` |
| Cho rằng `withZoneSameInstant` giữ nguyên ngày lịch | Một sự kiện có thể thuộc hai ngày khác nhau tại hai vùng | Chuyển zone trước khi lấy `LocalDate` nghiệp vụ |
| So sánh `ZonedDateTime.equals` để xác định cùng thời điểm | `equals` còn xét ngày/giờ/zone | Dùng `isEqual` hoặc so sánh `Instant` |
| Coi LocalDateTime là timestamp toàn cầu | Nó không có offset hoặc ZoneId | Lưu `Instant` hoặc xác định đủ zone/offset |
| Lấy ngày trước rồi chuyển sang zone đích | Ngày UTC có thể khác ngày địa phương | Chuyển `ZonedDateTime` trước, sau đó `toLocalDate()` |
| Tự đoán zone từ `Locale` | Ngôn ngữ không xác định vị trí địa lý | Quản lý `Locale` và `ZoneId` riêng |
| Bỏ kết quả của `withZoneSameInstant` | `ZonedDateTime` bất biến, đối tượng cũ không đổi | Gán hoặc truyền kết quả trả về |
| Dùng phép chuyển giữ Instant để chuyển địa điểm lịch hẹn nhưng giữ 09:00 | Giờ địa phương ở nơi mới sẽ thay đổi | Dùng bài toán local time + vùng đích, xử lý DST |
| Không kiểm tra zone ID nhập từ bên ngoài | `ZoneId.of` có thể ném `DateTimeException` | Xác thực dữ liệu đầu vào và chỉ chấp nhận vùng được hỗ trợ |

**Lưu ý thêm:** Tên múi giờ dạng viết tắt như `CST` thường mơ hồ. Nên trao đổi ID IANA chuẩn như `America/New_York` hoặc `Asia/Ho_Chi_Minh`. Một chuỗi offset `+07:00` là độ lệch cố định, không thay cho quy tắc của cả một khu vực.

## 12. Các bài kiểm thử nên có

| Bài kiểm tra | Điều cần xác nhận |
| --- | --- |
| Đổi New York → Việt Nam bằng `withZoneSameInstant` | `toInstant()` giữ nguyên |
| Đổi cùng giá trị sang UTC | Vẫn bằng mốc sự kiện đầu |
| Đổi vùng qua nửa đêm hoặc cuối năm | Ngày có thể đổi, `Instant` không đổi |
| So sánh `withZoneSameLocal` và `withZoneSameInstant` | Với vùng khác offset, thời điểm của `withZoneSameLocal` thường khác |
| Ngày có DST gap | `Instant` chuyển sang giờ hợp lệ; không tự tạo giờ địa phương không tồn tại |
| Ngày có DST overlap | Hai sự kiện có local time giống nhau vẫn giữ `Instant` khác nhau |
| Đổi vùng và so sánh `equals` / `isEqual` | `isEqual` true với cùng `Instant`; `equals` thường false |
| Dùng `Clock.fixed` cho dữ liệu “bây giờ” | Kết quả không phụ thuộc lúc chạy test |

Ví dụ trong **phương thức kiểm thử JUnit 5** (giả định `source` là một `ZonedDateTime` hợp lệ, `targetZone` là `ZoneId` được cấp vào):

```java
ZonedDateTime converted = source.withZoneSameInstant(targetZone);

assertEquals(source.toInstant(), converted.toInstant());
assertTrue(source.isEqual(converted));
assertEquals(targetZone, converted.getZone());
```

Đoạn này cần `import java.time.*;` và static import `org.junit.jupiter.api.Assertions.*;`, đồng thời chạy bên trong một bài test JUnit; **không phải chương trình `main` độc lập**. Với yêu cầu “không sửa đối tượng gốc”, test có thể lưu `source` và kiểm tra giá trị không đổi sau phép gọi.

## 13. Quy trình chọn API theo yêu cầu

1. **Bạn đã có một thời điểm thực (Instant hoặc ZonedDateTime) và cần hiển thị ở vùng khác?** Dùng `instant.atZone(zone)` hoặc `zonedDateTime.withZoneSameInstant(zone)`.
2. **Bạn muốn giữ nguyên giờ trên lịch khi đổi địa điểm?** Làm việc với `LocalDateTime` và `ZoneId` đích; cân nhắc `withZoneSameLocal` chỉ khi đã nắm rõ quy tắc xử lý DST của nó.
3. **Bạn muốn chuyển giờ sang UTC nhưng không đổi thời điểm?** `withZoneSameInstant(ZoneOffset.UTC)` hoặc `toInstant()` nếu chỉ cần mốc tuyệt đối.
4. **Bạn muốn giữ ý định “09:00 hằng ngày tại một thành phố”?** Lưu `LocalTime` cùng quy tắc lặp và `ZoneId`, rồi phân giải từng lần hẹn.
5. **Bạn cần đo khoảng thời gian thực giữa hai sự kiện?** Lấy hai `Instant`, dùng `Duration.between(start, end)`; tránh trừ các giờ địa phương từ hai vùng.

**Ghi nhớ:** `withZoneSameInstant()` **đổi múi giờ hiển thị, không đổi thời điểm thực**. Hãy kiểm chứng bằng `source.toInstant().equals(converted.toInstant())`. Nếu bài toán muốn bảo toàn chữ số ngày–giờ địa phương thay vì bảo toàn một sự kiện, đó là bài toán khác, cần `LocalDateTime`/`withZoneSameLocal` và chính sách DST rõ ràng.
