# Chọn độ lệch sớm hoặc muộn bằng `withEarlierOffsetAtOverlap()` và `withLaterOffsetAtOverlap()`

Một lịch hẹn được nhập là **01:30 ngày 03/11/2024 tại New York**. Thoạt nhìn, ngày, giờ và tên vùng đã đầy đủ. Tuy nhiên, hôm đó New York kết thúc giờ mùa hè (DST): đồng hồ quay từ 02:00 về 01:00, khiến **01:30 xuất hiện hai lần**. Hai lần đó lần lượt tương ứng với UTC offset `-04:00` và `-05:00`.

Java `ZonedDateTime` cho phép chọn một trong hai lần bằng:

- `withEarlierOffsetAtOverlap()`: chọn **offset của lần xuất hiện sớm hơn** trên dòng thời gian.
- `withLaterOffsetAtOverlap()`: chọn **offset của lần xuất hiện muộn hơn** trên dòng thời gian.

Ví dụ:

```java
ZoneId zone = ZoneId.of("America/New_York");
LocalDateTime local = LocalDateTime.of(2024, 11, 3, 1, 30);

ZonedDateTime earlier = local.atZone(zone)
        .withEarlierOffsetAtOverlap();
ZonedDateTime later = local.atZone(zone)
        .withLaterOffsetAtOverlap();
```

Đoạn minh họa đặt trong một phương thức có `import java.time.*;`. `earlier` là `2024-11-03T01:30-04:00[America/New_York]`, tức `2024-11-03T05:30:00Z`. `later` là `2024-11-03T01:30-05:00[America/New_York]`, tức `2024-11-03T06:30:00Z`. Chữ số **ngày/giờ địa phương giống hệt nhau**, nhưng hai sự kiện cách nhau đúng một giờ thực.

## 1. Vì sao có hiện tượng *overlap*?

`ZoneId` như `America/New_York` không chỉ lưu một offset cố định. Nó dựa trên các quy tắc múi giờ, bao gồm quy tắc chuyển đổi DST theo từng giai đoạn. Vào một thời điểm chuyển từ giờ mùa hè sang giờ chuẩn, đồng hồ địa phương được chỉnh **lùi**, tạo ra một khoảng giờ bị lặp (*overlap*).

Trong ví dụ ngày 03/11/2024 tại New York:

```text
Trục thời gian UTC      Giờ địa phương New York       Offset
2024-11-03T05:00Z      2024-11-03 01:00             -04:00
2024-11-03T05:30Z      2024-11-03 01:30  (lần 1)    -04:00
2024-11-03T06:00Z      2024-11-03 01:00  (lần 2)    -05:00
2024-11-03T06:30Z      2024-11-03 01:30  (lần 2)    -05:00
2024-11-03T07:00Z      2024-11-03 02:00             -05:00
```

Khi người dùng chỉ nhập `2024-11-03T01:30`, đó là một `LocalDateTime`: **chưa đủ thông tin để xác định lần 1 hay lần 2**. Khi thêm vùng `America/New_York`, quy tắc vùng phát hiện có **hai offset hợp lệ**.

Trong `ZoneRules`, số offset hợp lệ đối với một `LocalDateTime` có thể là:

| Số offset hợp lệ | Tình huống | Ý nghĩa |
| --- | --- | --- |
| 1 | Giờ địa phương bình thường | Chỉ có một thời điểm ứng với ngày/giờ đã nhập. |
| 2 | *Overlap* (giờ lặp) | Có hai thời điểm thực, cần chọn cách giải quyết mơ hồ. |
| 0 | *Gap* (giờ bị khuyết) | Ngày/giờ địa phương này không tồn tại theo quy tắc vùng. |

Hầu hết các lần tạo `ZonedDateTime` từ `LocalDateTime` và vùng đều không có vấn đề. Hai phương thức của bài **chỉ có tác dụng lựa chọn khác biệt khi giá trị nằm trong overlap**.

## 2. Phân biệt “offset sớm” và “thời điểm sớm”

Ở đây chữ **earlier**/**later** nói về vị trí của **lần xuất hiện trên dòng thời gian**, **không có nghĩa offset là số nhỏ/lớn**.

Tại New York năm 2024:

| Lựa chọn | Giờ địa phương | UTC offset | `Instant` |
| --- | --- | --- | --- |
| `withEarlierOffsetAtOverlap()` | `2024-11-03T01:30` | `-04:00` | `2024-11-03T05:30:00Z` |
| `withLaterOffsetAtOverlap()` | `2024-11-03T01:30` | `-05:00` | `2024-11-03T06:30:00Z` |

Offset `-04:00` về mặt số học **lớn hơn** `-05:00`, nhưng lại cho **thời điểm sớm hơn** khi gắn vào cùng giờ địa phương: `01:30 - (-04:00) = 05:30Z`. Vì thế đừng dùng thứ tự số học của `ZoneOffset.getTotalSeconds()` để tự chọn “earlier” nếu ý định là chọn phương thức chuẩn của API.

### Sự khác nhau giữa `ZonedDateTime` và `Instant`

`ZonedDateTime` lưu ngày giờ địa phương, `ZoneId` và offset đã xác định theo quy tắc vùng; từ đó tính được `Instant`. Hai `ZonedDateTime` có thể có cùng `toLocalDateTime()` và `getZone()` nhưng có offset khác và do đó **khác `Instant`**.

Tại overlap, khi chọn offset kia:

- `toLocalDateTime()` **không đổi**.
- `getZone()` **không đổi**.
- `getOffset()` chuyển từ offset thứ nhất sang offset thứ hai.
- `toInstant()` **thay đổi**, nên mốc thực đã thay đổi.
- Đối tượng cũ **không bị sửa** vì `ZonedDateTime` là bất biến.

Đây không phải thao tác đổi cách hiển thị cùng một thời điểm như `withZoneSameInstant(...)`. Nó là một quyết định **lần xuất hiện nào của giờ địa phương bị lặp**.

## 3. Hành vi chính xác của hai phương thức

### `withEarlierOffsetAtOverlap()`

Phương thức này trả một `ZonedDateTime` dùng **offset sớm hơn theo quy tắc của overlap** tại ngày giờ/vùng đang xét.

```java
ZonedDateTime firstOccurrence = current.withEarlierOffsetAtOverlap();
```

Nếu `current` ở overlap và đang mang offset của lần muộn, phương thức chuyển về lần sớm. Nếu đang ở lần sớm, kết quả có cùng giá trị. Nếu **không** ở overlap, nó để nguyên ngày giờ, vùng và offset.

### `withLaterOffsetAtOverlap()`

Phương thức này trả một `ZonedDateTime` dùng **offset muộn hơn theo quy tắc của overlap**:

```java
ZonedDateTime secondOccurrence = current.withLaterOffsetAtOverlap();
```

Nếu `current` đang ở lần sớm, phương thức chuyển sang lần muộn. Nếu đã ở lần muộn hoặc không nằm trong overlap, giá trị vẫn tương đương giá trị ban đầu.

**Lưu ý quan trọng:** hai phương thức hoạt động trên **một `ZonedDateTime` đã được tạo**. Chúng không yêu cầu đầu vào `LocalDateTime` hay `ZoneOffset` mới, và không tự thay đổi tên vùng. Chúng không làm “cộng một giờ” theo kiểu cộng `Duration.ofHours(1)` trong mọi trường hợp; độ chênh giữa hai lần phụ thuộc vào mức chuyển offset thực tế của vùng, có thể khác 60 phút.

### Phân biệt đổi offset và đổi zone

- `withEarlierOffsetAtOverlap()` / `withLaterOffsetAtOverlap()`: giữ cùng giờ địa phương và cùng `ZoneId`, đổi lựa chọn offset trong overlap, nên **đổi `Instant`**.
- `withZoneSameInstant(otherZone)`: giữ **cùng `Instant`**, đổi vùng hiển thị; giờ địa phương thường thay đổi.
- `withZoneSameLocal(otherZone)`: cố giữ **cùng ngày/giờ địa phương** tại vùng mới rồi giải quyết theo quy tắc vùng; `Instant` có thể thay đổi.
- `plusHours(1)`: trên `ZonedDateTime`, giờ là đơn vị theo thời lượng trên dòng thời gian; ở overlap có thể chuyển từ lần xuất hiện đầu sang lần sau. Nhưng nó không có nghĩa “chọn offset muộn” cho mọi giờ và mọi vùng; dùng đúng phương thức overlap khi nghiệp vụ cần giải quyết sự mơ hồ.

## 4. Ví dụ đầy đủ Java 17+: chọn và so sánh hai lần 01:30

Tạo tệp **`OverlapChoiceDemo.java`**:

```java
import java.time.*;
import java.util.List;

public class OverlapChoiceDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        LocalDateTime local = LocalDateTime.of(2024, 11, 3, 1, 30);

        List<ZoneOffset> offsets =
                zone.getRules().getValidOffsets(local);

        ZonedDateTime defaultChoice = local.atZone(zone);
        ZonedDateTime earlier =
                defaultChoice.withEarlierOffsetAtOverlap();
        ZonedDateTime later =
                defaultChoice.withLaterOffsetAtOverlap();

        System.out.println("Local time       : " + local);
        System.out.println("Valid offsets    : " + offsets);
        System.out.println("Default          : " + defaultChoice);
        System.out.println("Earlier          : " + earlier);
        System.out.println("Earlier instant  : " + earlier.toInstant());
        System.out.println("Later            : " + later);
        System.out.println("Later instant    : " + later.toInstant());
        System.out.println("Gap in minutes   : " +
                Duration.between(
                        earlier.toInstant(), later.toInstant()
                ).toMinutes());
        System.out.println("Same local       : " +
                earlier.toLocalDateTime()
                        .equals(later.toLocalDateTime()));
        System.out.println("Same instant     : " +
                earlier.toInstant().equals(later.toInstant()));
        System.out.println("Original intact  : " + defaultChoice);
        System.out.println("Earlier to later : " +
                earlier.withLaterOffsetAtOverlap());
        System.out.println("Later to earlier : " +
                later.withEarlierOffsetAtOverlap());
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac OverlapChoiceDemo.java
java OverlapChoiceDemo
```

Kết quả đã biên dịch/chạy và đối chiếu:

```text
Local time       : 2024-11-03T01:30
Valid offsets    : [-04:00, -05:00]
Default          : 2024-11-03T01:30-04:00[America/New_York]
Earlier          : 2024-11-03T01:30-04:00[America/New_York]
Earlier instant  : 2024-11-03T05:30:00Z
Later            : 2024-11-03T01:30-05:00[America/New_York]
Later instant    : 2024-11-03T06:30:00Z
Gap in minutes   : 60
Same local       : true
Same instant     : false
Original intact  : 2024-11-03T01:30-04:00[America/New_York]
Earlier to later : 2024-11-03T01:30-05:00[America/New_York]
Later to earlier : 2024-11-03T01:30-04:00[America/New_York]
```

**Giải thích từng điểm:**

1. `getValidOffsets(local)` trả hai giá trị: `-04:00` (khi còn DST) và `-05:00` (khi đã chuyển về giờ chuẩn).
2. `local.atZone(zone)` mặc định chọn **offset sớm hơn** trong overlap: `-04:00`. Đây là quy tắc mặc định khi chuyển từ một `LocalDateTime` chưa có offset thành `ZonedDateTime`.
3. Gọi `withEarlierOffsetAtOverlap()` trên lựa chọn mặc định không thay đổi giá trị vì đã ở lần sớm.
4. `withLaterOffsetAtOverlap()` thay offset bằng `-05:00`. Lúc 01:30 vẫn giữ nguyên, nhưng `Instant` dịch từ 05:30Z sang 06:30Z.
5. Hai phép `equals` của ngày giờ địa phương và `Instant` khẳng định chính xác điều khác biệt: **same local = true**, **same instant = false**.
6. Biến `defaultChoice` không thay đổi khi gọi hai phương thức; muốn cập nhật biến, phải gán giá trị được trả về.
7. Gọi phương thức ngược lại trên lựa chọn đã định sẽ đưa offset về lần còn lại. Vì vậy phương thức không chỉ có tác dụng tại lúc tạo mới; có thể đổi quyết định tại overlap khi nghiệp vụ cho phép.

## 5. Điều gì xảy ra ngoài overlap?

Hai phương thức **không** biến mọi `ZonedDateTime` thành một offset khác. Hãy xét ba nhóm:

- **Giờ bình thường:** có đúng một offset hợp lệ. `withEarlierOffsetAtOverlap()` và `withLaterOffsetAtOverlap()` đều trả giá trị tương đương ban đầu.
- **Giờ bị lặp:** có hai offset hợp lệ. Có thể chọn một trong hai bằng hai phương thức.
- **Giờ bị khuyết (*gap*):** một `LocalDateTime` cụ thể không tồn tại trong vùng. Việc tạo `ZonedDateTime` bằng `atZone(zone)` mặc định **điều chỉnh qua gap** đến giờ hợp lệ; sau đó hai phương thức overlap **không sửa gap**.

Ngày 10/03/2024 ở New York, giờ 02:30 không tồn tại do đồng hồ nhảy từ 01:59 sang 03:00. `LocalDateTime.of(2024, 3, 10, 2, 30).atZone(zone)` mặc định cho `2024-03-10T03:30-04:00[America/New_York]`. Gọi `withEarlierOffsetAtOverlap()` hoặc `withLaterOffsetAtOverlap()` trên giá trị đã điều chỉnh này không có ý nghĩa chọn giờ 02:30: đó **không phải overlap**.

### Ví dụ Java 17+ xác minh giờ bình thường, giờ bị khuyết và cách chọn ngay khi tạo

Tạo tệp **`OverlapBoundaryDemo.java`**:

```java
import java.time.*;

public class OverlapBoundaryDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");

        LocalDateTime ordinary = LocalDateTime.of(2024, 11, 4, 1, 30);
        ZonedDateTime normal = ordinary.atZone(zone);
        System.out.println("Ordinary offsets : " +
                zone.getRules().getValidOffsets(ordinary));
        System.out.println("Ordinary earlier : " +
                normal.withEarlierOffsetAtOverlap());
        System.out.println("Ordinary later   : " +
                normal.withLaterOffsetAtOverlap());

        LocalDateTime nonexistent = LocalDateTime.of(2024, 3, 10, 2, 30);
        System.out.println("Gap offsets      : " +
                zone.getRules().getValidOffsets(nonexistent));
        ZonedDateTime resolved = nonexistent.atZone(zone);
        System.out.println("Gap resolved     : " + resolved);
        System.out.println("Gap earlier      : " +
                resolved.withEarlierOffsetAtOverlap());
        System.out.println("Gap later        : " +
                resolved.withLaterOffsetAtOverlap());

        LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);
        ZonedDateTime explicitlyLater = ZonedDateTime.ofLocal(
                overlap, zone, ZoneOffset.ofHours(-5)
        );
        System.out.println("Preferred later  : " + explicitlyLater);
        System.out.println("Strict earlier   : " +
                ZonedDateTime.ofStrict(
                        overlap, ZoneOffset.ofHours(-4), zone
                ));
        System.out.println("Instant mapped   : " +
                Instant.parse("2024-11-03T06:30:00Z").atZone(zone));
    }
}
```

```bash
javac OverlapBoundaryDemo.java
java OverlapBoundaryDemo
```

Kết quả đã chạy thực tế:

```text
Ordinary offsets : [-05:00]
Ordinary earlier : 2024-11-04T01:30-05:00[America/New_York]
Ordinary later   : 2024-11-04T01:30-05:00[America/New_York]
Gap offsets      : []
Gap resolved     : 2024-03-10T03:30-04:00[America/New_York]
Gap earlier      : 2024-03-10T03:30-04:00[America/New_York]
Gap later        : 2024-03-10T03:30-04:00[America/New_York]
Preferred later  : 2024-11-03T01:30-05:00[America/New_York]
Strict earlier   : 2024-11-03T01:30-04:00[America/New_York]
Instant mapped   : 2024-11-03T01:30-05:00[America/New_York]
```

Các kết quả xác nhận rằng phương thức overlap **không chỉnh giá trị ở giờ bình thường hoặc sau khi đã giải quyết gap**. Ngoài ra, ta có thể yêu cầu offset mong muốn ngay lúc tạo `ZonedDateTime`, hoặc chọn từ một mốc `Instant` đã biết.

## 6. Chọn offset ngay khi tạo: `ofLocal`, `ofStrict` và `Instant.atZone`

Hai phương thức `withEarlierOffsetAtOverlap()` và `withLaterOffsetAtOverlap()` tiện khi **đã có** `ZonedDateTime`. Nhưng một số luồng dữ liệu có thêm thông tin offset hoặc `Instant` ngay từ ban đầu.

### A. `ZonedDateTime.ofLocal(local, zone, preferredOffset)`

Có thể truyền offset ưu tiên:

```java
LocalDateTime local = LocalDateTime.of(2024, 11, 3, 1, 30);
ZoneId zone = ZoneId.of("America/New_York");

ZonedDateTime second = ZonedDateTime.ofLocal(
        local, zone, ZoneOffset.ofHours(-5)
);
```

`second` là `2024-11-03T01:30-05:00[America/New_York]`. **Offset ưu tiên chỉ được dùng nếu là một offset hợp lệ** của giờ địa phương trong vùng. Nếu không hợp lệ, `ofLocal` dùng quy tắc giải quyết thông thường, nên nó không phải API để bắt buộc mọi kết hợp tùy ý. Khi cần từ chối dữ liệu không khớp vùng, xem `ofStrict`.

### B. `ZonedDateTime.ofStrict(local, offset, zone)`

Khi đầu vào đã chỉ định offset, có thể kiểm tra nghiêm ngặt:

```java
ZonedDateTime first = ZonedDateTime.ofStrict(
        local, ZoneOffset.ofHours(-4), zone
);
```

Với giờ lặp hợp lệ trong ví dụ, offset `-04:00` được chấp nhận. Nếu offset không hợp lệ cho giờ địa phương và vùng đó (hoặc giờ nằm trong gap), `ofStrict` ném `DateTimeException`. Nó giúp xử lý nguồn dữ liệu có yêu cầu **không âm thầm dịch giờ**.

### C. Nếu đã có `Instant`, không phải chọn “sớm hay muộn”

Khi đã biết một `Instant`, chuyển qua vùng có kết quả **không mơ hồ**:

```java
Instant instant = Instant.parse("2024-11-03T06:30:00Z");
ZonedDateTime local = instant.atZone(ZoneId.of("America/New_York"));
// 2024-11-03T01:30-05:00[America/New_York]
```

Đây là đoạn minh họa cần `import java.time.*;`. `Instant` xác định một mốc duy nhất; `ZoneId` quyết định offset đang có hiệu lực tại mốc đó. Sự mơ hồ xuất hiện khi **đi từ giờ địa phương sang mốc thực** trong overlap, không phải khi đi từ mốc thực sang giờ địa phương.

## 7. Khi nào ứng dụng nên cho chọn lần sớm hoặc muộn?

Một API đặt lịch thường nhận: ngày, giờ và múi giờ. Vào thời điểm DST overlap, **chỉ ba trường này chưa đủ** để phân biệt hai lần xuất hiện của một giờ.

Các chính sách hợp lý có thể gồm:

1. **Luôn chọn lần sớm**: ví dụ tác vụ nên bắt đầu ngay lần đầu đồng hồ hiển thị giờ đã chọn. Gọi `withEarlierOffsetAtOverlap()`.
2. **Luôn chọn lần muộn**: ví dụ tác vụ phải chờ tới lần thứ hai đồng hồ hiển thị giờ đó. Gọi `withLaterOffsetAtOverlap()`.
3. **Yêu cầu người dùng xác nhận**: đặc biệt cho chuyến bay, giao dịch tiền, tính công hoặc lịch nhạy cảm thời gian.
4. **Lưu offset/timestamp đã chọn**: tránh mất quyết định khi dữ liệu chuyển qua API, hệ thống khác hoặc khởi động lại.

Với một lịch hẹn xảy ra **một lần**, có thể lưu `Instant` đã giải quyết cùng `LocalDateTime` và `ZoneId` dùng để diễn giải. Với **lịch hẹn lặp lại** theo giờ địa phương, cần giữ `LocalTime`, `ZoneId`, quy tắc ngày lặp và chính sách gap/overlap, bởi mỗi lần lặp có thể có offset khác nhau. Một offset cố định như `-04:00` không thay thế thông tin vùng `America/New_York` cho lịch tương lai.

### Quy trình giải quyết có chủ đích

```text
Người dùng nhập LocalDateTime + ZoneId
                  |
                  v
  zone.getRules().getValidOffsets(local)
                  |
        +---------+---------+
        |         |         |
        0         1         2
       gap     bình thường overlap
        |         |         |
  từ chối/     tạo giờ    chọn earlier/
  điều chỉnh   với offset later hoặc hỏi
        |         |         |
        +---------+---------+
                  |
                  v
       ZonedDateTime đã xác định
                  |
                  v
             toInstant()
```

Đây là sơ đồ luồng khái niệm, không phải code Java. Với giờ bị khuyết, chính sách có thể là từ chối giá trị nhập, dịch tới giờ hợp lệ hoặc hỏi người dùng; hai phương thức chọn offset của overlap **không thay thế chính sách xử lý gap**.

### Ví dụ kiểm tra overlap trước khi áp dụng lựa chọn

Đoạn minh họa trong phương thức Java có `import java.time.*;` và `import java.util.List;`:

```java
ZoneId zone = ZoneId.of("America/New_York");
LocalDateTime local = LocalDateTime.of(2024, 11, 3, 1, 30);
List<ZoneOffset> valid = zone.getRules().getValidOffsets(local);

if (valid.isEmpty()) {
    throw new IllegalArgumentException("Giờ địa phương không tồn tại");
}
ZonedDateTime resolved = local.atZone(zone);

if (valid.size() == 2) {
    // Quy tắc nghiệp vụ đã chọn lần muộn.
    resolved = resolved.withLaterOffsetAtOverlap();
}
Instant scheduledAt = resolved.toInstant();
```

Đoạn này chỉ dành cho mô hình **giờ địa phương đã xác thực**; nếu yêu cầu là người dùng tự chọn giữa hai lần, thay chính sách cố định bằng lựa chọn được gửi từ giao diện. Tại giờ bình thường, `atZone(zone)` tạo kết quả duy nhất. Đầu vào lỗi, gap và overlap được xét riêng giúp tránh việc âm thầm áp dụng mặc định cho sự kiện nhạy cảm.

## 8. Tính bất biến, so sánh và lưu trữ

### Phương thức không sửa đối tượng ban đầu

`ZonedDateTime` bất biến:

```java
ZonedDateTime earlier = LocalDateTime.of(2024, 11, 3, 1, 30)
        .atZone(ZoneId.of("America/New_York"));

earlier.withLaterOffsetAtOverlap(); // bỏ qua kết quả
// earlier vẫn là 01:30-04:00

ZonedDateTime later = earlier.withLaterOffsetAtOverlap();
// later là 01:30-05:00
```

Phải giữ giá trị trả về nếu muốn dùng lựa chọn mới.

### Không dùng `toLocalDateTime()` để so mốc thực

Trong overlap, hai lựa chọn có cùng `toLocalDateTime()` nhưng khác `toInstant()`. Khi muốn kiểm tra **hai sự kiện có cùng thời điểm hay không**, hãy so sánh `toInstant()` hoặc dùng `ZonedDateTime.isEqual(...)`.

`ZonedDateTime.equals(...)` kiểm tra nhiều thành phần của đối tượng (ngày giờ, offset, zone), nên không thay thế một cách mù quáng phép so sánh mốc thực. `LocalDateTime.equals(...)` lại bỏ hoàn toàn thông tin vùng/offset, sẽ không phân biệt hai lần 01:30. Với lịch sử giao dịch, khóa sắp xếp theo **mốc thực** nên dùng `Instant`.

### Lưu trữ không được đánh mất lựa chọn

Giả sử hệ thống chỉ lưu chuỗi `2024-11-03T01:30` cùng zone `America/New_York`, nhưng không lưu offset hay instant đã chọn. Khi đọc lại, `local.atZone(zone)` mặc định có thể chọn lần sớm, khiến lựa chọn lần muộn của người dùng bị mất.

Nên lưu một trong các mô hình tùy nghiệp vụ:

- `Instant` đã xác định cùng zone gốc để phục vụ lịch sử và hiển thị.
- `ZonedDateTime` có đủ offset + `ZoneId`, với format/parse bảo toàn các trường cần thiết.
- `LocalDateTime` + `ZoneId` + offset đã chọn hoặc định danh chính sách, đặc biệt khi một lịch hẹn tương lai còn cần điều chỉnh theo các thay đổi quy tắc múi giờ.

Chuỗi có offset như `2024-11-03T01:30-05:00` xác định được mốc thực, nhưng **chỉ offset không lưu đầy đủ quy tắc vùng** cho những lần lặp khác. Khi truyền dữ liệu giữa hệ thống, phải thống nhất rõ trường nào là nguồn sự thật cho lịch tương lai.

## 9. Sai lầm phổ biến

1. **Tưởng `withEarlierOffsetAtOverlap()` chọn offset số học nhỏ hơn.** Trong New York, lần sớm là `-04:00`, dù `-05:00` là số nhỏ hơn.
2. **Tưởng “earlier” nghĩa là cộng/trừ giờ địa phương.** Cả hai phương thức giữ nguyên chữ số ngày giờ trong overlap; chúng chọn hai offset và vì vậy thay đổi `Instant`.
3. **Gọi phương thức rồi bỏ giá trị trả về.** `ZonedDateTime` bất biến; không sửa đối tượng gốc.
4. **Dùng hai phương thức để xử lý giờ bị khuyết.** Gap có **0 offset hợp lệ**; cần một chính sách riêng. Sau khi `atZone` tự điều chỉnh gap, gọi phương thức overlap không đưa về giờ không tồn tại.
5. **Mặc định mọi ngày ở mọi nơi đều có overlap.** DST khác nhau theo quốc gia, giai đoạn và dữ liệu vùng; nhiều vùng không có DST.
6. **Cho rằng overlap luôn lệch đúng 60 phút.** Quy tắc từng vùng có thể đổi offset theo bước khác nhau; kiểm tra offset thật bằng `ZoneRules`.
7. **Dùng một `ZoneOffset` cố định thay `ZoneId` cho lịch theo một thành phố.** Offset không mã hóa đầy đủ quy tắc chuyển giờ.
8. **Chỉ lưu `LocalDateTime` sau khi người dùng đã chọn lần muộn.** Mất offset/instant sẽ làm dữ liệu mơ hồ khi đọc lại.
9. **Cho rằng `local.atZone(zone)` luôn báo lỗi nếu có hai offset.** Trong overlap, nó có chính sách mặc định thường chọn lần sớm. Nếu nghiệp vụ không chấp nhận mặc định, phải kiểm tra và giải quyết rõ ràng.
10. **Chuyển sang vùng khác bằng `withZoneSameLocal` khi muốn giữ cùng sự kiện.** Muốn giữ `Instant`, dùng `withZoneSameInstant`.
11. **Nhầm `Instant` đã biết với giờ địa phương chưa được giải quyết.** Một `Instant` không cần chọn earlier/later khi biểu diễn theo zone; lựa chọn chỉ phát sinh khi bắt đầu từ giờ địa phương mơ hồ.
12. **Dùng giờ trên đồng hồ làm thứ tự sự kiện.** Trong đêm lùi giờ, 01:50 lần đầu **xảy ra trước** 01:10 lần sau mặc dù so sánh chuỗi địa phương có thể đưa ra kết luận ngược. Dùng `Instant` để sắp thứ tự mốc thực.

## 10. Câu hỏi luyện tập

**Câu 1.** 01:30 ngày 03/11/2024 tại New York có bao nhiêu offset hợp lệ?

**Đáp án:** Hai: `-04:00` và `-05:00`. Đây là một overlap.

**Câu 2.** Cùng ngày/giờ `2024-11-03T01:30`, offset `-04:00` và `-05:00` lần lượt ứng với `Instant` nào?

**Đáp án:** `05:30Z` và `06:30Z`. Hai mốc cách nhau 60 phút.

**Câu 3.** Gọi `withLaterOffsetAtOverlap()` trên `2024-11-03T01:30-04:00[America/New_York]` thay đổi giá trị gì?

**Đáp án:** Giữ nguyên ngày giờ địa phương và vùng, chọn offset `-05:00`, khiến `Instant` chuyển từ `05:30Z` sang `06:30Z`.

**Câu 4.** Gọi `withEarlierOffsetAtOverlap()` trên `2024-11-04T01:30-05:00[America/New_York]` có thay đổi không?

**Đáp án:** Không. Ngày 04/11/2024 lúc 01:30 là giờ bình thường trong ví dụ, chỉ có một offset hợp lệ.

**Câu 5.** `2024-03-10T02:30` tại New York là overlap hay gap? Hai phương thức overlap có tạo được thời điểm 02:30 này không?

**Đáp án:** Đó là **gap**, không có offset hợp lệ. `atZone` mặc định điều chỉnh thành 03:30; hai phương thức overlap không tạo lại một giờ không tồn tại.

**Câu 6.** Nếu đã biết `Instant.parse("2024-11-03T06:30:00Z")` và zone New York, có cần hỏi người dùng chọn earlier/later không?

**Đáp án:** Không. `instant.atZone(zone)` đã xác định chắc chắn `01:30-05:00` từ mốc thực.

**Câu 7.** Vì sao việc lưu chỉ `LocalDateTime` vào DB không thể bảo toàn lựa chọn lần muộn?

**Đáp án:** Vì `LocalDateTime` không mang zone, offset hoặc `Instant`; cùng 01:30 có hai lần xuất hiện trong overlap. Hãy lưu thêm dữ liệu phân biệt mốc hoặc chính sách đã chọn.

## Ghi nhớ

**`withEarlierOffsetAtOverlap()` và `withLaterOffsetAtOverlap()` chỉ giải quyết tình huống giờ địa phương bị lặp trong một `ZoneId`.** Chúng giữ ngày/giờ địa phương và vùng, chọn một offset hợp lệ khác, làm thay đổi `Instant` khi hai offset khác nhau. Ở giờ bình thường hoặc khi giờ gap đã được giải quyết thành giờ hợp lệ, hai phương thức không làm thay đổi kết quả. Khi quyết định này có ảnh hưởng nghiệp vụ, hãy kiểm tra `getValidOffsets(...)`, yêu cầu chính sách rõ ràng và lưu `Instant`/offset đã chọn để tránh mất ý nghĩa thời điểm.
