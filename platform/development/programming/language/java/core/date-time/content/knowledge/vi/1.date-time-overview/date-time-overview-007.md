# Tính bất biến, an toàn luồng và so sánh theo giá trị trong `java.time`

Khi xử lý ngày giờ trong Java, ba câu hỏi thường đi cùng nhau: đối tượng có bị sửa đổi sau khi tạo không, có thể chia sẻ giữa các luồng không, và hai đối tượng biểu diễn “cùng một thời điểm” hay “cùng một giá trị” theo nghĩa nào? Các kiểu chuẩn của `java.time` (Java 8+, dùng tốt trên Java 17+) được thiết kế để giải quyết phần lớn vấn đề từng gặp với `Date`, `Calendar` và `SimpleDateFormat`. Tuy nhiên, tính bất biến của một giá trị **không tự động làm cho toàn bộ nghiệp vụ dùng giá trị đó trở nên an toàn luồng**, và “bằng nhau” cần được hiểu theo đúng kiểu dữ liệu.

## 1. Tính bất biến (immutability) là gì?

Một đối tượng **bất biến** giữ nguyên trạng thái quan sát được sau khi được tạo. Với các implementation ngày giờ chuẩn như `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`, `OffsetDateTime`, `ZonedDateTime`, `Duration` và `Period`, các thao tác thay đổi ngày giờ trả về **giá trị kết quả** mà không sửa đối tượng nhận lời gọi.

```java
LocalDate issuedAt = LocalDate.of(2026, 10, 24);
LocalDate expiresAt = issuedAt.plusDays(30);

// issuedAt vẫn là 2026-10-24; expiresAt là 2026-11-23.
issuedAt.plusYears(1); // Bỏ qua kết quả: issuedAt KHÔNG thay đổi.
```

Hệ quả thực hành:

- `plusDays`, `minusHours`, `withYear`, `atStartOfDay` và nhiều thao tác tương tự **trả về giá trị**; nếu cần dùng trạng thái mới, phải giữ giá trị trả về (`date = date.plusDays(1)`).
- Việc gán lại biến tham chiếu không sửa đối tượng cũ. Nếu `LocalDate next = original.plusDays(1)`, các nơi vẫn giữ `original` sẽ tiếp tục thấy ngày cũ.
- Không nên giả định mỗi phép toán luôn cấp phát đối tượng mới: implementation có thể trả về chính đối tượng cũ khi giá trị kết quả không đổi. Vì vậy **không dùng `==` để kiểm tra ngày giờ bằng nhau**.
- Bất biến là tính chất của **đối tượng**, không phải của biến. Một biến `LocalDate` vẫn có thể được gán tham chiếu khác; `final LocalDate d` ngăn gán lại biến `d` trong phạm vi tương ứng nhưng không phải nguyên nhân làm `LocalDate` bất biến.
- `DateTimeFormatter` chuẩn cũng bất biến và an toàn để dùng chung. Ngược lại, `DateTimeFormatterBuilder` là builder có trạng thái thay đổi trong quá trình cấu hình.

Tính bất biến làm mã dễ suy luận: không có luồng hay hàm nào “lén” chỉnh sửa giá trị ngày giờ mà một hàm khác đang sử dụng. Tuy nhiên, không phải **mọi** lớp triển khai các interface `Temporal`, `TemporalAccessor` hay `Clock` đều có bảo đảm giống nhau. Khi nói `java.time` bất biến, cần dựa vào hợp đồng của **kiểu cụ thể**; với kiểu tự triển khai và các đối tượng bao ngoài, phải đánh giá riêng.

## 2. Chọn đúng kiểu: giá trị nào đang được so sánh?

| Kiểu | Giá trị biểu diễn | Có xác định duy nhất một instant? | Ý nghĩa khi so sánh |
| --- | --- | --- | --- |
| `LocalDate` | Ngày lịch, ví dụ `2026-10-24` | Không | So sánh ngày trong lịch, không xét giờ/múi giờ |
| `LocalTime` | Giờ trong một ngày | Không | So sánh giờ địa phương |
| `LocalDateTime` | Ngày và giờ địa phương | Không | So sánh các trường ngày/giờ; chưa biết offset/zone |
| `Instant` | Điểm trên trục thời gian UTC | Có | So sánh sự kiện theo thời gian tuyệt đối |
| `OffsetDateTime` | Ngày giờ địa phương + UTC offset | Có | Giá trị gồm cả offset, nhưng có thể quy về `Instant` |
| `ZonedDateTime` | Ngày giờ + `ZoneId` + offset theo quy tắc vùng | Có | Giá trị giữ thông tin vùng; có thể quy về `Instant` |
| `Duration` | Khoảng thời gian theo giây và nano giây | Không áp dụng | Độ dài thời gian theo đơn vị thời gian |
| `Period` | Số năm, tháng, ngày theo lịch | Không áp dụng | Lượng thời gian theo đơn vị lịch |

`LocalDateTime.of(2026, 10, 24, 9, 0)` chưa phải một thời điểm tuyệt đối: 09:00 ở Việt Nam và 09:00 ở Tokyo là hai instant khác nhau. Nếu phải lưu hoặc đối chiếu thời điểm phát sinh một sự kiện giữa nhiều vùng, hãy dùng `Instant` làm đại diện chung; giữ thêm `ZoneId` khi cần biết vùng hiển thị/ngữ cảnh lịch.

Đừng đồng nhất `Period.ofDays(1)` và `Duration.ofHours(24)` trong mọi phép tính trên `ZonedDateTime`: cộng một **ngày theo lịch địa phương** có thể khác cộng đúng **24 giờ** khi đi qua ngày chuyển giờ mùa hè (DST).

## 3. Vì sao các giá trị bất biến dễ chia sẻ giữa nhiều luồng?

Một instance `LocalDate`, `Instant` hoặc `DateTimeFormatter` chuẩn không có trạng thái nội bộ để các luồng cùng sửa. Nhiều luồng có thể đồng thời đọc, format, parse hoặc tính toán từ cùng một instance mà không cần khóa đối tượng đó. Mỗi phép tính trả ra kết quả riêng.

```java
private static final DateTimeFormatter DISPLAY =
        DateTimeFormatter.ofPattern("dd/MM/uuuu");

// Các luồng có thể gọi DISPLAY.format(date) đồng thời.
String text = DISPLAY.format(LocalDate.of(2026, 10, 24));
```

Cần phân biệt ba lớp vấn đề:

1. **An toàn của một giá trị bất biến:** đọc và gọi phương thức trên instance chuẩn không làm thay đổi giá trị mà luồng khác đang đọc.
2. **Công bố tham chiếu (publication):** nếu một luồng tạo hoặc thay tham chiếu được chia sẻ, hãy dùng cơ chế công bố phù hợp (`static final`, đồng bộ hóa, `volatile`, `AtomicReference`, cấu trúc đồng thời…). Điều này giúp các luồng khác nhận được tham chiếu đúng thời điểm và có các bảo đảm về khả kiến của Java Memory Model. Các trường `final` của đối tượng bất biến hỗ trợ bảo đảm khởi tạo, nhưng **không biến mọi cách truyền/cập nhật tham chiếu thành một giao thức đồng thời đúng**.
3. **An toàn của thao tác nghiệp vụ:** hai luồng cùng đọc một ngày hết hạn rồi cùng cập nhật “thêm một ngày” có thể đánh mất một lần cập nhật, dù mỗi `LocalDate` riêng lẻ đều bất biến.

Ví dụ một lỗi cập nhật mất dữ liệu (mã *minh họa*, không phải chương trình độc lập):

```java
private LocalDate deadline = LocalDate.of(2026, 10, 24);

void extendOneDay() {
    deadline = deadline.plusDays(1);
}
```

Nếu hai luồng đều đọc `2026-10-24` trước khi ghi, cả hai có thể cùng gán `2026-10-25`; kết quả chỉ tăng **một ngày**, không phải hai. Việc gán và tính `plusDays` là thao tác đọc–tính–ghi gồm nhiều bước; `volatile` trên `deadline` chỉ hỗ trợ khả kiến của tham chiếu, **không** khiến toàn bộ các bước trở thành một cập nhật nguyên tử.

Khi thực sự cần một trạng thái ngày giờ dùng chung và phải cập nhật nguyên tử, có thể sử dụng:

```java
private final AtomicReference<LocalDate> deadline =
        new AtomicReference<>(LocalDate.of(2026, 10, 24));

void extendOneDay() {
    deadline.updateAndGet(day -> day.plusDays(1));
}
```

(Cần `import java.time.LocalDate;` và `import java.util.concurrent.atomic.AtomicReference;` trong lớp chứa đoạn mã.) `updateAndGet` thực hiện cập nhật theo cơ chế compare-and-set; hàm tính giá trị mới có thể được gọi lại khi tranh chấp, nên biểu thức lambda phải **không có tác dụng phụ**. `day -> day.plusDays(1)` phù hợp vì chỉ tạo giá trị kết quả. Nếu nghiệp vụ cập nhật đồng thời cả ngày hết hạn và các trường khác, phải phối hợp **toàn bộ trạng thái liên quan** bằng một cơ chế đồng bộ/transaction thích hợp; riêng `AtomicReference<LocalDate>` không đủ.

### Chú ý tới nguồn thời gian

`LocalDate.now()`, `Instant.now()` hay `ZonedDateTime.now(zone)` tạo ra các giá trị bất biến, nhưng **kết quả của hai lời gọi khác nhau có thể khác nhau** vì đồng hồ tiếp tục chạy. Để logic kiểm thử ổn định, truyền một `Clock` thích hợp:

```java
Clock fixed = Clock.fixed(
        Instant.parse("2026-10-24T12:00:00Z"), ZoneOffset.UTC);
LocalDate today = LocalDate.now(fixed); // 2026-10-24
```

`Clock` là abstraction cho nguồn thời gian; tính an toàn luồng của một `Clock` tự triển khai phải được kiểm tra theo chính implementation đó. Các giá trị `LocalDate` nhận được vẫn bất biến.

## 4. Bằng nhau theo giá trị, theo thứ tự và theo instant

### 4.1. `==` khác `equals()`

- `a == b` với hai biến tham chiếu kiểm tra có trỏ tới **cùng một object** hay không.
- `a.equals(b)` dùng hợp đồng **bằng nhau theo giá trị** của kiểu cụ thể.
- Khi `equals()` là `true`, hai giá trị phải có cùng `hashCode()`. Đây là cơ sở dùng chúng làm khóa `HashMap` hoặc phần tử `HashSet`.
- Không giả định hai object cùng ngày được cache chung, hay object sau tính toán luôn khác object trước.

```java
LocalDate a = LocalDate.of(2026, 10, 24);
LocalDate b = LocalDate.parse("2026-10-24");

boolean sameDate = a.equals(b);                 // true
boolean sameHash = a.hashCode() == b.hashCode(); // true
```

`LocalDate` so sánh theo ngày lịch. `LocalDateTime` so sánh theo các trường ngày và giờ địa phương. Với `Instant`, hai giá trị bằng nhau khi chúng chỉ tới cùng điểm trên trục thời gian.

### 4.2. `OffsetDateTime` và `ZonedDateTime`: cùng instant chưa chắc `equals()`

Một sự kiện duy nhất có thể được biểu diễn bằng các offset hoặc vùng khác nhau. Ví dụ:

```java
OffsetDateTime inVietnam =
        OffsetDateTime.parse("2026-10-24T19:00:00+07:00");
OffsetDateTime inJapan =
        OffsetDateTime.parse("2026-10-24T21:00:00+09:00");

inVietnam.equals(inJapan);                      // false
inVietnam.isEqual(inJapan);                     // true
inVietnam.toInstant().equals(inJapan.toInstant()); // true
```

`equals()` của `OffsetDateTime` tính cả ngày giờ địa phương **và offset**. `isEqual()` kiểm tra hai giá trị có đại diện cùng instant hay không. Với `ZonedDateTime`, `equals()` còn phân biệt thông tin vùng (`ZoneId`); `isEqual()` so sánh trên trục thời gian. Hai object cùng instant nhưng thuộc `Asia/Ho_Chi_Minh` và `Asia/Tokyo` có thể `isEqual() == true` và `equals() == false`.

Hai phép đổi vùng cũng có ý nghĩa khác nhau:

- `withZoneSameInstant(otherZone)`: đổi cách biểu diễn theo vùng, **giữ nguyên instant**.
- `withZoneSameLocal(otherZone)`: cố giữ các trường ngày giờ địa phương, nên **instant có thể thay đổi** (và thời gian không tồn tại/trùng nhau khi DST cần được giải quyết theo quy tắc vùng).

Do đó, khi deduplicate log, sự kiện hoặc timestamp phát sinh từ nhiều hệ thống, chuẩn hóa qua `toInstant()` rồi dùng `Instant.equals()`/khóa `Instant`. Khi chính offset/vùng lịch được coi là một phần của thông tin nghiệp vụ (lịch đặt theo vùng, hiển thị), không được xóa bỏ tùy tiện để chỉ giữ instant.

### 4.3. Thứ tự: `compareTo`, `isBefore`, `isAfter`

- `LocalDate.isBefore(other)` và `isAfter(other)` xét thứ tự **ngày lịch**.
- `Instant.isBefore(other)` và `isAfter(other)` xét thứ tự **instant**.
- `OffsetDateTime.isBefore/isAfter/isEqual` và `ZonedDateTime.isBefore/isAfter/isEqual` xét thứ tự/cùng giá trị trên **trục thời gian**.
- `compareTo()` tạo thứ tự tự nhiên dùng cho sắp xếp. Với `OffsetDateTime` và `ZonedDateTime`, thứ tự tự nhiên có bước phân xử tiếp khi hai instant bằng nhau, để phân biệt biểu diễn địa phương/offset/vùng. Bởi vậy **`isEqual() == true` không kéo theo `compareTo() == 0`** cho các kiểu này.

Nếu bài toán yêu cầu **chỉ xếp theo instant**, thể hiện ý định rõ ràng:

```java
Comparator<ZonedDateTime> timelineOrder =
        Comparator.comparing(ZonedDateTime::toInstant);
```

(Cần `import java.time.ZonedDateTime;` và `import java.util.Comparator;`.) Một `TreeSet` dùng comparator này sẽ coi hai phần tử cùng instant là tương đương **theo comparator** và có thể giữ chỉ một phần tử dù `equals()` giữa chúng là `false`; cần cân nhắc hợp đồng của collection khi dùng comparator không nhất quán với `equals()`.

### 4.4. Giá trị bằng nhau của `Duration` và `Period`

```java
Duration.ofMinutes(1).equals(Duration.ofSeconds(60)); // true
Period.ofMonths(12).equals(Period.ofYears(1));         // false
```

`Duration` biểu diễn tổng số giây/nano giây; các factory tạo cùng độ dài chuẩn hóa về cùng giá trị. `Period` giữ **các thành phần năm, tháng, ngày**: “12 tháng” và “1 năm” không có cùng cấu trúc giá trị dù trong nhiều phép tính lịch chúng cho kết quả tương đương. Không dùng phép so sánh của một kiểu để suy đoán quy tắc của kiểu khác.

## 5. Ví dụ Java 17+ chạy độc lập

Tạo tệp **`DateTimeValueDemo.java`**:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.concurrent.atomic.AtomicReference;

public class DateTimeValueDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 24);
        LocalDate next = date.plusDays(1);

        System.out.println("date = " + date);
        System.out.println("next = " + next);
        System.out.println("value equals = "
                + date.equals(LocalDate.parse("2026-10-24")));

        Instant event = Instant.parse("2026-10-24T12:00:00Z");
        OffsetDateTime vietnam = event.atOffset(ZoneOffset.ofHours(7));
        OffsetDateTime japan = event.atOffset(ZoneOffset.ofHours(9));

        System.out.println("vietnam = " + vietnam);
        System.out.println("japan = " + japan);
        System.out.println("offset equals = " + vietnam.equals(japan));
        System.out.println("same instant = " + vietnam.isEqual(japan));

        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("dd/MM/uuuu");
        System.out.println("formatted = " + formatter.format(date));

        AtomicReference<LocalDate> sharedDate = new AtomicReference<>(date);
        sharedDate.updateAndGet(d -> d.plusDays(2));
        System.out.println("sharedDate = " + sharedDate.get());
        System.out.println("original unchanged = " + date);
    }
}
```

Biên dịch và chạy:

```bash
javac DateTimeValueDemo.java
java DateTimeValueDemo
```

Kết quả chuẩn:

```text
date = 2026-10-24
next = 2026-10-25
value equals = true
vietnam = 2026-10-24T19:00+07:00
japan = 2026-10-24T21:00+09:00
offset equals = false
same instant = true
formatted = 24/10/2026
sharedDate = 2026-10-26
original unchanged = 2026-10-24
```

Diễn giải: `plusDays` không sửa `date`; tạo độc lập một `LocalDate` cùng ngày vẫn so sánh `equals` bằng nhau; hai `OffsetDateTime` có offset khác nhau nhưng biểu diễn cùng `Instant`; `AtomicReference` giúp thay thế tham chiếu một cách nguyên tử, trong khi giá trị `date` ban đầu không thay đổi. Ví dụ chỉ minh họa một lần cập nhật; việc xác nhận an toàn khi nhiều luồng tranh chấp dựa trên hợp đồng nguyên tử của `AtomicReference.updateAndGet`, không phải số lần chạy của demo.

## 6. Sai lầm thường gặp và cách sửa

| Sai lầm | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| Gọi `date.plusDays(1)` rồi tin `date` đã đổi | Giá trị `LocalDate` bất biến | Giữ kết quả: `date = date.plusDays(1)` |
| So sánh hai ngày bằng `==` | Chỉ so sánh tham chiếu | Dùng `equals()`; dùng `isBefore/isAfter` cho thứ tự |
| Dùng `LocalDateTime` để so sánh sự kiện toàn cầu | Thiếu offset/zone nên chưa xác định instant | Chuyển dữ liệu có ngữ cảnh vùng sang `Instant` |
| Tin hai timestamp cùng instant phải `equals()` | `OffsetDateTime` và `ZonedDateTime` giữ thêm offset/zone | Dùng `isEqual()` hoặc so sánh `toInstant()` |
| Thay `SimpleDateFormat` chia sẻ bằng một biến `static` dùng chung | `SimpleDateFormat` có trạng thái thay đổi và không an toàn luồng | Dùng `static final DateTimeFormatter` cho format/parse chuẩn |
| Nghĩ `LocalDate` bất biến thì phép `shared = shared.plusDays(1)` tự nguyên tử | Hai luồng có thể mất cập nhật | Dùng `AtomicReference.updateAndGet`, lock hoặc transaction theo yêu cầu |
| Nghĩ `volatile` biến phép đọc–sửa–ghi thành nguyên tử | `volatile` không gộp nhiều bước thành một thao tác | Dùng cơ chế cập nhật nguyên tử thích hợp |
| Đồng nhất một ngày lịch với 24 giờ ở mọi vùng | DST có thể tạo ngày lịch 23 hoặc 25 giờ | Phân biệt `Period`, `Duration`, `plusDays` và `plusHours` |
| Lưu key theo `ZonedDateTime` rồi mong deduplicate theo instant | `equals/hashCode` còn xét zone và các trường giá trị | Dùng key `Instant` nếu danh tính là thời điểm phát sinh |

Khi làm việc với API cũ, cần nhớ `java.util.Date` và `Calendar` có hành vi mutable; `SimpleDateFormat` không an toàn khi dùng chung giữa các luồng mà không đồng bộ. Có thể chuyển một `Date` sang snapshot bất biến qua `date.toInstant()`, nhưng chính đối tượng `Date` gốc vẫn có thể bị sửa bởi mã khác.

## 7. Quy tắc quyết định trong ứng dụng

1. **Mô hình hóa đúng đại lượng:** ngày sinh/ngày nghỉ → `LocalDate`; giờ mở cửa địa phương → `LocalTime`; một event đã xảy ra → `Instant`; lịch gắn quy tắc vùng → `ZonedDateTime` kèm `ZoneId`; khoảng thời gian cố định → `Duration`; dịch chuyển theo lịch → `Period`.
2. **Truyền giá trị bất biến tự do, quản lý trạng thái có thể thay đổi một cách rõ ràng:** đối tượng ngày giờ và formatter chuẩn chia sẻ được; một biến/thùng chứa đang được cập nhật phải có cơ chế đồng thời riêng.
3. **Chọn phép so sánh theo ngữ nghĩa:** cùng giá trị biểu diễn → `equals`; cùng instant → `isEqual`/`toInstant`; trước/sau → `isBefore`/`isAfter`; sắp xếp → `compareTo` hoặc comparator có chủ đích.
4. **Xác định quy tắc vùng và nguồn thời gian:** cùng số giờ địa phương chưa chắc cùng instant; với nghiệp vụ nhạy cảm thời gian, nhận `Clock` để kiểm thử và nêu rõ zone/offset đầu vào.
5. **Không dùng tính bất biến để thay thế tính nguyên tử:** khi cập nhật deadline, quota, booking hoặc trạng thái đồng thời, đánh giá giao dịch gồm những bước nào, và bảo vệ cả quá trình.

### Tự kiểm tra

- Hai `LocalDate` cùng ngày nhưng được tạo theo hai cách khác nhau: so sánh bằng gì? → `equals()`.
- 19:00 tại UTC+07 và 21:00 tại UTC+09 cùng ngày: chúng có phải cùng instant? → Có, vì cả hai là 12:00 UTC; `isEqual()` là `true`, còn `OffsetDateTime.equals()` là `false`.
- Hai luồng cùng tăng ngày hết hạn trên một biến `LocalDate`: đối tượng bất biến có ngăn mất cập nhật không? → Không; cần cập nhật nguyên tử hoặc đồng bộ.
- Một formatter `DateTimeFormatter` được dùng bởi nhiều luồng: có phải tạo formatter riêng cho mỗi luồng không? → Không, với implementation chuẩn immutable và thread-safe.
- `LocalDateTime` 09:00 có đủ dữ kiện để tính thời điểm UTC không? → Không; cần quy tắc zone hoặc offset.

**Ghi nhớ:** `java.time` tách rõ **giá trị bất biến** khỏi **trạng thái có thể thay đổi**, và tách **bằng nhau về biểu diễn** khỏi **cùng một instant**. Chọn đúng kiểu, giữ kết quả của phép tính, rồi chọn cơ chế đồng thời và so sánh theo đúng ý nghĩa nghiệp vụ.
