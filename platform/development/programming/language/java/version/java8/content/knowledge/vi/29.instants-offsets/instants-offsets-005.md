# Chuyển giữa Instant với thời gian có offset trong Java

## 1. Mục tiêu và bức tranh tổng quan

Trong `java.time`, nhiều kiểu có thể cùng mô tả một sự kiện xảy ra lúc 12 giờ 30 phút UTC, nhưng cách hiển thị khác nhau theo UTC offset. Khi làm API, ghi nhật ký, trao đổi sự kiện giữa hệ thống và xây giao diện người dùng, điều quan trọng là hiểu **chuyển đổi giữ nguyên thời điểm** và **gán lại một giờ địa phương** không phải một việc.

Ba khái niệm cần phân biệt:

- **`Instant`:** một **thời điểm tuyệt đối** trên timeline của Java, tính theo epoch bắt đầu `1970-01-01T00:00:00Z`, có độ phân giải nanosecond. Nó **không lưu timezone, UTC offset hay lịch hiển thị địa phương**.
- **`ZoneOffset`:** độ lệch cố định so với UTC, ví dụ `Z`/`+00:00`, `+07:00` hoặc `-04:00`. Nó không chứa lịch sử thay đổi giờ của một vùng địa lý.
- **`OffsetDateTime`:** **ngày + giờ địa phương + offset**. Từ ba thành phần đó, ta xác định được **một Instant duy nhất** khi giá trị hợp lệ.

Một thời điểm được biểu diễn qua nhiều offset:

```text
Instant:          2024-06-01T12:30:45Z
                          |
         +----------------+------------------+
         |                                   |
  Offset +07:00                         Offset -04:00
         |                                   |
2024-06-01T19:30:45+07:00         2024-06-01T08:30:45-04:00
         |                                   |
         +---------------+-------------------+
                         |
               Cùng một Instant
               2024-06-01T12:30:45Z
```

Hai cách hiển thị bên dưới **khác local clock** nhưng cùng **mốc thời gian thật**.

Bài học trình bày những API hiện hành:

- `instant.atOffset(offset)` hoặc `OffsetDateTime.ofInstant(instant, offsetOrZone)`: từ `Instant` sang thời gian có offset.
- `offsetDateTime.toInstant()`: từ `OffsetDateTime` trở về `Instant`.
- `localDateTime.atOffset(offset)` và `localDateTime.toInstant(offset)`: khi đầu vào chỉ có giờ địa phương, phải **cấp thêm offset có căn cứ**.
- `withOffsetSameInstant` và `withOffsetSameLocal`: hai phép biến đổi **khác hẳn nhau**.
- Chuyển theo `ZoneId` địa lý, DST, parsing, kiểm tra cùng thời điểm, độ chính xác và giới hạn dữ liệu.

Những API này có từ Java 8 và **vẫn phù hợp trong Java hiện đại**. Các chương trình hoàn chỉnh dùng JDK 17+ và không yêu cầu kỹ thuật legacy. Bài không dùng `java.util.Date`/`Calendar` để thay thế cách biểu diễn mới.

## 2. Kiểu dữ liệu nào mang thông tin gì?

| Kiểu | Giữ giá trị gì? | Có thể chuyển trực tiếp sang Instant? | Khi nào dùng? |
| --- | --- | --- | --- |
| `Instant` | Mốc thời gian trên timeline | Chính nó đã là Instant | Lưu timestamp sự kiện, truyền mốc thời gian giữa hệ thống |
| `ZoneOffset` | Độ lệch cố định so với UTC | Không phải ngày giờ | Mô tả offset cụ thể |
| `LocalDateTime` | Ngày + giờ, **không có offset/zone** | Không nếu thiếu offset/zone | Giờ địa phương chưa có cách xác định mốc UTC |
| `OffsetDateTime` | Ngày + giờ địa phương + offset | **Có**, bằng `toInstant()` | API hoặc dữ liệu giữ offset đã được xác định |
| `ZonedDateTime` | Ngày giờ + `ZoneId` và offset được resolve | **Có**, bằng `toInstant()` | Lịch hẹn theo vùng, quy tắc DST và múi giờ lịch sử |
| `OffsetTime` | Giờ địa phương + offset, **không có ngày** | Không biểu diễn một Instant độc lập | Giờ trong ngày có offset, khi thông tin ngày chưa biết |

Điểm then chốt là **OffsetDateTime không lưu ZoneId địa lý**. Ví dụ `2024-07-15T14:00+02:00` cho biết offset tại thời điểm đó, nhưng không cho biết nó đến từ Paris, một vùng khác đang dùng `+02:00`, hay do người dùng nhập trực tiếp.

`ZoneOffset` là một subclass của `ZoneId` theo API Java, nên có thể truyền `ZoneOffset` vào một số phương thức yêu cầu `ZoneId`. Nhưng nếu ứng dụng cần **quy tắc thay đổi offset theo ngày**, phải sử dụng một `ZoneId` vùng như `"Europe/Paris"` hoặc `"Asia/Ho_Chi_Minh"`, không dùng offset cố định làm đại diện toàn diện.

### 2.1. Epoch, ký hiệu Z và offset

- `Instant.EPOCH` biểu diễn `1970-01-01T00:00:00Z`.
- `Z` trong chuỗi ISO nghĩa là offset zero: `+00:00`.
- `+07:00` nói rằng giờ địa phương **nhanh hơn UTC bảy giờ**: khi muốn tính UTC, **trừ** 7 giờ.
- `-04:00` nói rằng giờ địa phương **chậm hơn UTC bốn giờ**: khi muốn tính UTC, **cộng** 4 giờ.

Ví dụ:

```text
2024-06-01 19:30:45 +07:00
-                  07:00
--------------------------------
2024-06-01 12:30:45 UTC
```

**Không nhầm “+07:00” với việc cộng 7 giờ khi chuyển từ local về UTC**. Dấu offset có ý nghĩa tương đối giữa **local time** và **UTC**, không phải một phép cộng tự do.

## 3. API chính để chuyển hai chiều

### 3.1. Instant → OffsetDateTime

Cách viết trực tiếp:

```java
// Đoạn minh họa; import java.time.*.
Instant instant = Instant.parse("2024-06-01T12:30:45Z");
ZoneOffset offset = ZoneOffset.ofHours(7);

OffsetDateTime displayed = instant.atOffset(offset);
// 2024-06-01T19:30:45+07:00
```

Cách tương đương khi truyền một `ZoneOffset`:

```java
// Đoạn minh họa.
OffsetDateTime displayed =
    OffsetDateTime.ofInstant(instant, offset);
```

Có thể dùng `OffsetDateTime.ofInstant(instant, ZoneId.of("Europe/Paris"))` để **tra cứu offset có hiệu lực tại thời điểm đó** theo timezone rules. Kết quả vẫn là `OffsetDateTime`, nên **không giữ ZoneId Paris** sau chuyển đổi.

### 3.2. OffsetDateTime → Instant

```java
// Đoạn minh họa.
Instant restored = displayed.toInstant();
// 2024-06-01T12:30:45Z
```

Phép chuyển này **không cần hỏi timezone hệ thống**, vì `OffsetDateTime` đã có ngày giờ và offset đầy đủ. Nó không dựa vào `ZoneId.systemDefault()`.

### 3.3. Công thức khái niệm

```text
Instant (UTC) + ZoneOffset -> local date-time + ZoneOffset
OffsetDateTime            -> Instant tương đương trên timeline
```

Có thể viết bằng ký hiệu toán học đơn giản:

```text
local clock = UTC instant + offset
UTC instant = local clock - offset
```

Phép toán thực tế còn phải tính đúng ngày, tháng, năm khi qua nửa đêm, kể cả qua ranh giới tháng/năm. Không tự triển khai phép cộng/trừ chuỗi giờ rồi quên thay đổi ngày: **dùng API java.time**.

### 3.4. Không phải mọi Instant đều chuyển được sang OffsetDateTime

`Instant` hỗ trợ khoảng thời gian rộng hơn phạm vi local date-time tối đa của `OffsetDateTime`. Với một `Instant` rất xa ở biên, `instant.atOffset(offset)` có thể ném `DateTimeException` khi ngày địa phương cần tạo vượt giới hạn biểu diễn. Đây là exception hợp lệ theo Javadoc, **không phải một lỗi của phép tính UTC/offset**.

## 4. Ví dụ 1 — chuyển hai chiều và giữ nguyên thời điểm

Tạo file **InstantOffsetBasicsDemo.java**:

```java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

public class InstantOffsetBasicsDemo {
    public static void main(String[] args) {
        Instant point =
            Instant.parse("2024-06-01T12:30:45Z");

        OffsetDateTime hcm =
            point.atOffset(ZoneOffset.ofHours(7));

        OffsetDateTime west =
            OffsetDateTime.ofInstant(
                point,
                ZoneOffset.ofHours(-4)
            );

        System.out.println("instant=" + point);
        System.out.println("hcm=" + hcm);
        System.out.println("west=" + west);

        System.out.println("roundTrip=" +
            point.equals(hcm.toInstant()));

        System.out.println("equalInstant=" +
            hcm.isEqual(west));
    }
}
```

Biên dịch và chạy:

```bash
javac InstantOffsetBasicsDemo.java
java InstantOffsetBasicsDemo
```

Stdout đã kiểm thử:

```text
instant=2024-06-01T12:30:45Z
hcm=2024-06-01T19:30:45+07:00
west=2024-06-01T08:30:45-04:00
roundTrip=true
equalInstant=true
```

**Diễn giải:**

1. `Instant.parse(...)` tạo một thời điểm UTC rõ ràng, không phụ thuộc ngày giờ máy đang chạy.
2. `atOffset(+07:00)` tạo local clock 19:30:45 cùng offset +07:00.
3. `ofInstant(..., -04:00)` tạo local clock 08:30:45 cùng offset -04:00.
4. `hcm.toInstant()` bằng `point`: chuyển ngược về timeline không làm thay đổi sự kiện.
5. `hcm.isEqual(west)` trả `true` vì hai giá trị mô tả **cùng một thời điểm** dù local date-time và offset khác.

**Không hiểu nhầm tên biến `hcm`:** Nó đặt theo ví dụ hiển thị ở offset +07:00, **không có nghĩa** đối tượng giữ định danh timezone `Asia/Ho_Chi_Minh`. Offset không phải danh tính vùng.

## 5. Hai phép đổi offset khác nhau: SameInstant và SameLocal

Đây là một trong những sai lầm nghiêm trọng nhất khi chuyển đổi timestamp có offset.

`OffsetDateTime` cung cấp:

```java
// Các chữ ký minh họa trong API.
OffsetDateTime withOffsetSameInstant(ZoneOffset offset);

OffsetDateTime withOffsetSameLocal(ZoneOffset offset);
```

### 5.1. withOffsetSameInstant: giữ nguyên Instant

Giả sử:

```text
2024-03-10T10:30+07:00
               |
        cùng Instant
               |
2024-03-09T22:30-05:00
```

Vì offset mới nhỏ hơn offset cũ **12 giờ**, local clock phải giảm **12 giờ** để cùng chỉ một Instant.

`withOffsetSameInstant(newOffset)` giữ nguyên vị trí trên timeline, điều chỉnh local date-time tương ứng. Đây thường là **lựa chọn đúng khi hiển thị cùng một sự kiện theo offset khác**.

### 5.2. withOffsetSameLocal: giữ nguyên giờ trên đồng hồ

```text
2024-03-10T10:30+07:00 = 2024-03-10T03:30Z

withOffsetSameLocal(-05:00)

2024-03-10T10:30-05:00 = 2024-03-10T15:30Z
```

`withOffsetSameLocal(newOffset)` giữ **các trường ngày/giờ** giống cũ, chỉ thay offset. Vì vậy nó thường tạo **một thời điểm tuyệt đối khác**.

Nó chỉ đúng khi yêu cầu nghiệp vụ là **diễn giải lại** cùng local clock bằng một offset mới, không phải chuyển cách hiển thị của một sự kiện đã xảy ra.

| Nhu cầu | Phương thức |
| --- | --- |
| Xem timestamp của sự kiện tại offset khác | `withOffsetSameInstant` |
| Giữ local clock 10:30, gán một offset khác để mô tả thời điểm mới | `withOffsetSameLocal` |
| Không biết offset hiện tại nhưng có ngày giờ địa phương | Xác định zone/offset trước khi tạo OffsetDateTime |
| Không muốn thay đổi timestamp sự kiện | Tránh `withOffsetSameLocal` |

### Ví dụ 2 — SameInstantVsSameLocalDemo.java

Tạo file **SameInstantVsSameLocalDemo.java**:

```java
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

public class SameInstantVsSameLocalDemo {
    public static void main(String[] args) {
        OffsetDateTime base =
            OffsetDateTime.parse("2024-03-10T10:30+07:00");

        ZoneOffset west = ZoneOffset.ofHours(-5);

        OffsetDateTime sameInstant =
            base.withOffsetSameInstant(west);

        OffsetDateTime sameLocal =
            base.withOffsetSameLocal(west);

        System.out.println("base=" + base);
        System.out.println("sameInstant=" + sameInstant);
        System.out.println("sameLocal=" + sameLocal);

        System.out.println("baseInstant=" +
            base.toInstant());

        System.out.println("sameInstantUTC=" +
            sameInstant.toInstant());

        System.out.println("sameLocalUTC=" +
            sameLocal.toInstant());

        System.out.println("sameInstantEqual=" +
            base.toInstant().equals(sameInstant.toInstant()));

        System.out.println("sameLocalEqual=" +
            base.toInstant().equals(sameLocal.toInstant()));
    }
}
```

```bash
javac SameInstantVsSameLocalDemo.java
java SameInstantVsSameLocalDemo
```

Stdout:

```text
base=2024-03-10T10:30+07:00
sameInstant=2024-03-09T22:30-05:00
sameLocal=2024-03-10T10:30-05:00
baseInstant=2024-03-10T03:30:00Z
sameInstantUTC=2024-03-10T03:30:00Z
sameLocalUTC=2024-03-10T15:30:00Z
sameInstantEqual=true
sameLocalEqual=false
```

**Tại sao khác biệt quan trọng?**

- `sameInstant` giữ timestamp 03:30Z, nhưng local clock ở offset -05:00 là **22:30 ngày hôm trước**.
- `sameLocal` giữ số `10:30`, khiến timestamp thành 15:30Z, **muộn hơn 12 giờ** so với sự kiện ban đầu.
- Thay đổi offset có thể làm **đổi cả ngày**, không chỉ đổi số giờ.

Nếu ứng dụng hiển thị thời gian thanh toán, giao dịch, hoặc sự kiện audit, việc dùng `withOffsetSameLocal` nhầm chỗ có thể làm bản ghi chuyển sang một thời điểm sai. Khi muốn **giữ nguyên sự kiện**, hãy ưu tiên `withOffsetSameInstant` hoặc chuyển qua `Instant`.

## 6. LocalDateTime cần offset để thành Instant

`LocalDateTime` chỉ mang các trường năm-tháng-ngày-giờ-phút-giây-nanosecond. Nó **không chứa timezone hoặc offset**.

Ví dụ:

```text
LocalDateTime: 2024-01-02T09:15

Nếu offset +07:00 -> Instant 2024-01-02T02:15Z
Nếu offset -05:00 -> Instant 2024-01-02T14:15Z
```

Cùng một local clock có thể tương ứng nhiều điểm trên timeline. Vì vậy **không thể suy ra Instant duy nhất từ LocalDateTime khi thiếu thông tin offset/zone**.

### 6.1. Các phương thức hợp lệ

```java
// Đoạn minh họa: local và offset đã tồn tại.
OffsetDateTime withOffset = local.atOffset(offset);
Instant timestamp = local.toInstant(offset);
Instant timestampViaOffset = withOffset.toInstant();
```

Hai đường tính Instant trên tương đương với cùng local và offset hợp lệ.

**Quan trọng:** `local.atOffset(offset)` chỉ **gắn offset** được chỉ định với local time; nó không xác minh offset ấy là offset **đúng theo vùng địa lý** tại ngày đó. Nếu chỉ có tên vùng như `Europe/Paris`, cần dùng `ZoneId` và quy tắc DST, không tự chọn offset dựa trên ngày hiện tại.

### Ví dụ 3 — LocalDateTimeConversionDemo.java

Tạo file **LocalDateTimeConversionDemo.java**:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

public class LocalDateTimeConversionDemo {
    public static void main(String[] args) {
        LocalDateTime local =
            LocalDateTime.of(2024, 1, 2, 9, 15);

        OffsetDateTime east =
            local.atOffset(ZoneOffset.ofHours(7));

        OffsetDateTime west =
            local.atOffset(ZoneOffset.ofHours(-5));

        System.out.println("local=" + local);
        System.out.println("east=" + east.toInstant());
        System.out.println("west=" + west.toInstant());

        System.out.println("different=" +
            !east.toInstant().equals(west.toInstant()));

        System.out.println("explicit=" +
            local.toInstant(ZoneOffset.ofHours(7)));
    }
}
```

```bash
javac LocalDateTimeConversionDemo.java
java LocalDateTimeConversionDemo
```

Stdout:

```text
local=2024-01-02T09:15
east=2024-01-02T02:15:00Z
west=2024-01-02T14:15:00Z
different=true
explicit=2024-01-02T02:15:00Z
```

**Kết luận từ ví dụ:** Không tồn tại một kết quả `local.toInstant()` không tham số trên `LocalDateTime` để “tự đoán offset”; method cần một `ZoneOffset` phù hợp. Nếu input là thời gian một sự kiện đã diễn ra nhưng thiếu offset/zone, **chưa đủ dữ liệu để phục hồi chính xác timestamp**.

### 6.2. LocalDateTime không tương đương OffsetDateTime

`LocalDateTime.parse("2024-01-02T09:15")` hợp lệ, nhưng `OffsetDateTime.parse("2024-01-02T09:15")` không hợp lệ khi parser ISO offset đòi có offset. Đừng im lặng điền timezone máy chủ để “chữa” thiếu offset nếu API contract yêu cầu timestamp có offset.

## 7. ZoneId địa lý, UTC offset và DST

### 7.1. Instant → OffsetDateTime từ vùng timezone

`OffsetDateTime.ofInstant(instant, ZoneId)` chấp nhận một `ZoneId` vùng như `Europe/Paris`. Java đọc quy tắc timezone **ở chính Instant đang chuyển** để chọn offset đúng thời gian đó.

Ví dụ:

```text
2024-01-15T12:00:00Z tại Europe/Paris -> 13:00+01:00
2024-07-15T12:00:00Z tại Europe/Paris -> 14:00+02:00
```

Cả hai đều bắt đầu từ 12:00 UTC nhưng giờ Paris khác vì DST. Không được chọn offset của Paris **một lần cho mọi ngày trong năm**.

### 7.2. OffsetDateTime không giữ định danh vùng

Sau phép:

```java
// Đoạn minh họa.
OffsetDateTime result =
    OffsetDateTime.ofInstant(instant, ZoneId.of("Europe/Paris"));
```

`result` có giá trị local date-time và offset, **không còn `"Europe/Paris"`**. Nếu cần giữ vùng địa lý để giải thích lịch hẹn tương lai, sử dụng:

```java
// Đoạn minh họa.
ZonedDateTime zoned =
    instant.atZone(ZoneId.of("Europe/Paris"));
```

`ZonedDateTime` giữ cả `ZoneId` và offset có hiệu lực; điều này hữu ích khi xử lý lịch hẹn hoặc sự kiện lặp lại theo quy tắc địa phương.

### 7.3. DST gap/overlap: điều gì xảy ra khi đổi chiều?

Bắt đầu từ **Instant** và một `ZoneId` hợp lệ, offset tại thời điểm đó được xác định theo rules. Chuyển `Instant -> ZonedDateTime/OffsetDateTime` không có mơ hồ về “Instant nào”.

Nhưng nếu bắt đầu từ **LocalDateTime + ZoneId**:

- *Gap:* một local time có thể **không tồn tại** tại vùng đó.
- *Overlap:* một local time có thể xảy ra **hai lần** với hai offset khác nhau.
- Khi đã có cả local time và một offset **được xác nhận phù hợp với vùng**, ta có thể chuyển duy nhất sang Instant.

Để kiểm tra local time theo vùng, dùng `zone.getRules().getValidOffsets(local)`. Nếu danh sách rỗng, đó là gap; nếu hai offset, phải có chính sách chọn trong overlap. `ZonedDateTime.ofStrict(local, offset, zone)` giúp từ chối một offset không hợp lệ cho cặp local/zone.

Không bao giờ coi `ZoneOffset` cố định là toàn bộ quy tắc DST hoặc tự cho rằng tên một nước luôn tương ứng một offset duy nhất qua mọi giai đoạn lịch sử.

### Ví dụ 4 — RegionOffsetDemo.java

Tạo file **RegionOffsetDemo.java**:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class RegionOffsetDemo {
    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");

        Instant winter =
            Instant.parse("2024-01-15T12:00:00Z");

        Instant summer =
            Instant.parse("2024-07-15T12:00:00Z");

        OffsetDateTime w =
            OffsetDateTime.ofInstant(winter, paris);

        OffsetDateTime s =
            OffsetDateTime.ofInstant(summer, paris);

        System.out.println("winter=" + w);
        System.out.println("summer=" + s);

        System.out.println("regionInOffset=" +
            w.toString().contains("[Europe/Paris]"));

        System.out.println("zoned=" +
            winter.atZone(paris));

        System.out.println("sameWinterInstant=" +
            winter.equals(w.toInstant()));

        LocalDateTime ambiguous =
            LocalDateTime.of(2024, 10, 27, 2, 30);

        System.out.println("validOffsets=" +
            paris.getRules().getValidOffsets(ambiguous));

        System.out.println("early=" +
            ambiguous.toInstant(ZoneOffset.ofHours(2)));

        System.out.println("late=" +
            ambiguous.toInstant(ZoneOffset.ofHours(1)));
    }
}
```

```bash
javac RegionOffsetDemo.java
java RegionOffsetDemo
```

Stdout đã kiểm thử với quy tắc timezone lịch sử của JDK cho năm 2024:

```text
winter=2024-01-15T13:00+01:00
summer=2024-07-15T14:00+02:00
regionInOffset=false
zoned=2024-01-15T13:00+01:00[Europe/Paris]
sameWinterInstant=true
validOffsets=[+02:00, +01:00]
early=2024-10-27T00:30:00Z
late=2024-10-27T01:30:00Z
```

**Ý nghĩa:**

1. `winter` và `summer` được đổi từ những Instant cụ thể sang offset theo rules tại từng ngày.
2. `OffsetDateTime` không giữ phần `[Europe/Paris]`, trong khi `ZonedDateTime` có định danh vùng.
3. Trong overlap ngày 27/10/2024, cùng `02:30` của Paris có hai offset `+02:00` và `+01:00`; chúng tạo **hai Instant cách nhau một giờ**.
4. `LocalDateTime.toInstant(offset)` chỉ dùng offset được truyền, không xác minh offset ấy có được vùng Paris chấp nhận. Nếu muốn kiểm tra đúng nghiệp vụ, hãy gọi `ZoneRules.getValidOffsets(...)` hoặc API strict.

**Tính tái lập:** Các kết quả vùng timezone dựa trên dữ liệu quy tắc TZDB trong JDK. Ví dụ cố định các ngày lịch sử năm 2024; khi triển khai dài hạn, quản lý phiên bản TZDB và test dữ liệu thời gian theo môi trường hỗ trợ của ứng dụng.

## 8. So sánh: equals khác với cùng một Instant

Có hai giá trị:

```text
a = 2024-06-01T19:30+07:00
b = 2024-06-01T08:30-04:00
```

Chúng là hai biểu diễn khác nhau của cùng `2024-06-01T12:30Z`.

- `a.equals(b)` kiểm tra bằng nhau của **local date-time và offset**, nên `false` trong ví dụ.
- `a.isEqual(b)` kiểm tra chúng có cùng **Instant** hay không, nên `true`.
- `a.toInstant().equals(b.toInstant())` cũng là `true`.
- `a.isBefore(b)`/`isAfter(b)` dựa trên Instant; cả hai `false` nếu đúng cùng thời điểm.

`OffsetDateTime.compareTo(...)` có logic sắp xếp để tương thích với `equals`; nó không nên được dùng thay cho `isEqual` nếu câu hỏi nghiệp vụ chỉ là “hai bản ghi có cùng timestamp không?”. Với một cặp có cùng Instant nhưng offset khác, kết quả `compareTo` không bắt buộc là `0`.

### Ví dụ 5 — ComparisonDemo.java

Tạo file **ComparisonDemo.java**:

```java
import java.time.OffsetDateTime;

public class ComparisonDemo {
    public static void main(String[] args) {
        OffsetDateTime a = OffsetDateTime.parse(
            "2024-06-01T19:30+07:00"
        );

        OffsetDateTime b = OffsetDateTime.parse(
            "2024-06-01T08:30-04:00"
        );

        System.out.println("aInstant=" + a.toInstant());
        System.out.println("bInstant=" + b.toInstant());

        System.out.println("equals=" + a.equals(b));
        System.out.println("isEqual=" + a.isEqual(b));
        System.out.println("aBeforeB=" + a.isBefore(b));

        System.out.println("instantEquals=" +
            a.toInstant().equals(b.toInstant()));
    }
}
```

```bash
javac ComparisonDemo.java
java ComparisonDemo
```

Stdout:

```text
aInstant=2024-06-01T12:30:00Z
bInstant=2024-06-01T12:30:00Z
equals=false
isEqual=true
aBeforeB=false
instantEquals=true
```

**Bài học:** Khi đối chiếu event timestamps từ nhiều vùng, hãy chuẩn hóa logic theo **Instant** nếu chỉ quan tâm thời điểm xảy ra. Nhưng nếu so sánh cả cách hiển thị/lựa chọn offset ban đầu, `equals` của `OffsetDateTime` phân biệt chúng.

Không chọn một phép so sánh chỉ vì tên gần đúng; chọn theo **ngữ nghĩa câu hỏi**.

## 9. Epoch seconds, milliseconds và độ chính xác nanosecond

`Instant` chứa epoch-second kiểu `long` cùng phần nanosecond trong khoảng `0..999,999,999`. Nó có thể biểu diễn thời điểm chính xác đến nanosecond **theo cấu trúc dữ liệu**, nhưng điều đó **không bảo đảm** đồng hồ vật lý của máy cung cấp độ chính xác nanosecond.

Các API thường dùng:

| API | Ý nghĩa |
| --- | --- |
| `Instant.ofEpochSecond(seconds)` | Tạo Instant từ số giây kể từ epoch |
| `Instant.ofEpochSecond(seconds, nanoAdjustment)` | Tạo Instant từ giây và điều chỉnh nanosecond |
| `Instant.ofEpochMilli(millis)` | Tạo Instant từ milliseconds kể từ epoch |
| `instant.getEpochSecond()` | Lấy epoch seconds |
| `instant.getNano()` | Lấy phần nanosecond trong giây |
| `instant.toEpochMilli()` | Chuyển sang milliseconds, có thể mất phần nhỏ hơn mili-giây |
| `instant.atOffset(ZoneOffset.UTC)` | Hiển thị theo offset UTC mà không đổi Instant |

**Cẩn thận với đơn vị.** Hệ thống JavaScript hoặc một API có thể gửi epoch **milliseconds**, trong khi API khác gửi epoch **seconds**. Nhầm hai đơn vị tạo ngày giờ sai rất xa.

### 9.1. Chuyển qua milliseconds có thể mất thông tin

Một timestamp `1970-01-01T00:00:00.123456789Z` chứa 123,456,789 nanosecond trong giây. Khi chuyển qua milliseconds, chỉ còn `123` milliseconds. Nếu tạo lại bằng `Instant.ofEpochMilli(123)`, kết quả là `.123Z`, không còn `456789` nanosecond phía sau.

**Không coi round-trip qua `long millis` là lossless với mọi Instant**. Nếu cần giữ độ chính xác tới nanosecond, lưu dạng `Instant`, ISO text có đủ độ chính xác, hoặc cặp seconds+nanos theo contract schema.

### Ví dụ 6 — PrecisionEpochDemo.java

Tạo file **PrecisionEpochDemo.java**:

```java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

public class PrecisionEpochDemo {
    public static void main(String[] args) {
        Instant t =
            Instant.ofEpochSecond(0, 123_456_789);

        OffsetDateTime asUtc =
            t.atOffset(ZoneOffset.UTC);

        long millis = t.toEpochMilli();
        Instant coarse = Instant.ofEpochMilli(millis);

        System.out.println("instant=" + t);
        System.out.println("offset=" + asUtc);

        System.out.println("epochSecond=" +
            t.getEpochSecond());

        System.out.println("nano=" + t.getNano());
        System.out.println("millis=" + millis);
        System.out.println("coarse=" + coarse);

        System.out.println("lostNanos=" +
            !coarse.equals(t));

        System.out.println("fullRoundTrip=" +
            asUtc.toInstant().equals(t));
    }
}
```

```bash
javac PrecisionEpochDemo.java
java PrecisionEpochDemo
```

Stdout:

```text
instant=1970-01-01T00:00:00.123456789Z
offset=1970-01-01T00:00:00.123456789Z
epochSecond=0
nano=123456789
millis=123
coarse=1970-01-01T00:00:00.123Z
lostNanos=true
fullRoundTrip=true
```

Ở đây `OffsetDateTime.toInstant()` giữ nguyên toàn bộ phần nanosecond. Việc mất dữ liệu đến từ bước **rút xuống milliseconds**, không phải từ phép đổi offset.

**Giới hạn phạm vi:** Với một số Instant rất xa trong quá khứ/tương lai, `toEpochMilli()` có thể ném `ArithmeticException` do giá trị milliseconds vượt giới hạn `long`. Đừng giả định mọi Instant đều chuyển được qua kiểu `long millis`.

## 10. Parsing: chuỗi offset phải có offset hợp lệ

`Instant.parse(...)` thường dùng chuỗi ISO instant biểu diễn mốc UTC, ví dụ:

```java
// Mã minh họa.
Instant t = Instant.parse("2024-06-01T12:30:45Z");
```

`OffsetDateTime.parse(...)` dùng định dạng ISO có **offset**:

```java
// Mã minh họa.
OffsetDateTime t =
    OffsetDateTime.parse("2024-02-29T10:15:30+07:00");
```

Một chuỗi chỉ chứa ngày giờ địa phương như `"2024-02-29T10:15"` **không có offset**, do đó không phù hợp với parse OffsetDateTime mặc định. Cũng không nên thêm `"Z"` tùy tiện nếu bạn không biết giờ đó thực sự là UTC.

`DateTimeParseException` là subclass của `DateTimeException` khi việc parse thất bại. Những đầu vào như ngày 30/02, offset sai phạm vi, chữ sai cú pháp hoặc thiếu offset cần được kiểm tra tại **boundary dữ liệu**.

### 10.1. Xử lý null và ngày không hợp lệ

- `OffsetDateTime.parse(null)` không được coi là “không có ngày”, vì tham số `null` vi phạm contract non-null.
- `ZoneOffset.ofHours(19)` không hợp lệ vì offset có phạm vi tối đa ±18 giờ.
- `Instant.MAX.atOffset(ZoneOffset.UTC)` có thể ném `DateTimeException` vì khoảng biểu diễn Instant rộng hơn khoảng local date-time có offset.
- `OffsetDateTime.parse("2024-02-30T10:15+07:00")` thất bại vì ngày không tồn tại.
- `OffsetDateTime.parse("2024-02-29T10:15")` thất bại vì không có offset.

**Không catch parse error rồi tự gán `ZoneOffset.UTC` nếu người dùng chỉ nhập local time**, trừ khi API contract nói rõ đầu vào không có offset **được hiểu là UTC**.

### Ví dụ 7 — OffsetValidationDemo.java

Tạo file **OffsetValidationDemo.java**:

```java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeParseException;

public class OffsetValidationDemo {
    static void tryParse(String input) {
        try {
            OffsetDateTime value =
                OffsetDateTime.parse(input);

            System.out.println("valid=" +
                value.toInstant());
        } catch (DateTimeParseException ex) {
            System.out.println("invalid=" + input);
        }
    }

    public static void main(String[] args) {
        tryParse("2024-02-29T10:15:30+07:00");
        tryParse("2024-02-30T10:15+07:00");
        tryParse("2024-02-29T10:15");

        try {
            ZoneOffset.ofHours(19);
        } catch (DateTimeException ex) {
            System.out.println("offset19=REJECTED");
        }

        try {
            Instant.MAX.atOffset(ZoneOffset.UTC);
        } catch (DateTimeException ex) {
            System.out.println("hugeInstant=REJECTED");
        }
    }
}
```

```bash
javac OffsetValidationDemo.java
java OffsetValidationDemo
```

Stdout:

```text
valid=2024-02-29T03:15:30Z
invalid=2024-02-30T10:15+07:00
invalid=2024-02-29T10:15
offset19=REJECTED
hugeInstant=REJECTED
```

**Lưu ý logging:** Ví dụ in trực tiếp input giả để dễ kiểm tra. Trong ứng dụng thật, không ghi toàn bộ payload người dùng hoặc dữ liệu cá nhân vào log nếu không phù hợp với chính sách bảo mật; nên trả error code như `INVALID_OFFSET_DATE_TIME` hoặc `MISSING_OFFSET` và log thông tin chẩn đoán ở mức được phép.

## 11. Hai phép biến đổi có vẻ giống nhau nhưng khác contract

| Đoạn code | Kết quả | Giữ nguyên Instant? |
| --- | --- | --- |
| `instant.atOffset(+07:00)` | OffsetDateTime tại +07:00 | Có |
| `OffsetDateTime.ofInstant(instant, parisZone)` | OffsetDateTime với offset theo rules của Paris tại Instant | Có |
| `offsetDateTime.toInstant()` | Instant của cùng sự kiện | Có |
| `odt.withOffsetSameInstant(-04:00)` | Giờ địa phương khác, offset mới | **Có** |
| `odt.withOffsetSameLocal(-04:00)` | Giữ nguyên local clock, offset mới | **Không nhất thiết** |
| `local.atOffset(+07:00)` | Gắn offset đã chọn cho LocalDateTime | Chưa có Instant trước đó để “giữ” |
| `local.toInstant(+07:00)` | Instant suy ra từ local và offset | Không thể biết đúng nếu offset được đoán |
| `instant.atZone(parisZone)` | ZonedDateTime giữ ZoneId Paris | Có |
| `odt.toLocalDateTime()` | Bỏ offset, chỉ còn local clock | **Mất thông tin** |
| `odt.toEpochSecond()` | Epoch second của Instant | Giữ giây nhưng **không giữ nanos** trong riêng giá trị long |

**Một cách nhận diện nhanh:** Nếu chỉ **thay đổi cách biểu diễn cùng timestamp**, dùng các API mang nghĩa “same instant”. Nếu chủ ý giữ local clock nhưng gán offset mới, hãy hiểu rằng bạn đang **thay đổi timestamp**.

### 11.1. Không nên bỏ offset quá sớm

Đoạn sau làm mất thông tin:

```java
// Đoạn minh họa, odt là một OffsetDateTime.
LocalDateTime local = odt.toLocalDateTime();
```

Từ `local` không thể khôi phục chính xác Instant nếu không còn biết offset cũ. Vì vậy một schema truyền sự kiện chỉ có `"2024-06-01T19:30"` nhưng không chỉ rõ offset, timezone hay UTC convention **chưa đầy đủ** cho thời điểm tuyệt đối.

### 11.2. Không tự tạo offset theo thời gian hệ thống

Code kiểu:

```java
// Đoạn minh họa về ý định nguy hiểm:
// Dùng offset hiện tại thay cho offset ở thời điểm sự kiện quá khứ.
ZoneOffset currentOffset =
    ZoneId.of("Europe/Paris").getRules()
        .getOffset(Instant.now());
```

Nếu lấy `currentOffset` để gắn cho **một sự kiện có Instant khác**, kết quả có thể sai do DST hoặc thay đổi quy tắc địa phương. Khi đã có Instant của sự kiện, lấy offset **tại chính Instant đó**:

```java
// Mã minh họa.
ZoneId zone = ZoneId.of("Europe/Paris");

OffsetDateTime correct =
    OffsetDateTime.ofInstant(eventInstant, zone);
```

`eventInstant` ở đây là `Instant` của sự kiện, được cung cấp trong ngữ cảnh ứng dụng.

## 12. So sánh với ZonedDateTime trong hệ thống thực tế

### 12.1. Lưu mốc sự kiện đã xảy ra

Với log, transaction timestamp và sự kiện hệ thống, `Instant` là một lựa chọn tốt vì biểu diễn **một mốc không phụ thuộc vùng hiển thị**. Khi trả response cho người dùng, chuyển sang `OffsetDateTime` theo offset được yêu cầu hoặc `ZonedDateTime` theo timezone của người dùng.

Ví dụ quy trình:

```text
Event xảy ra
    |
    v
Instant (lưu timestamp)
    |
    +----> client A: OffsetDateTime tại +07:00
    |
    +----> client B: ZonedDateTime tại Europe/Paris
    |
    +----> service C: Instant UTC để so sánh/sắp xếp
```

Nếu dùng database, cần xác định kiểu cột/driver và contract timezone; một số kiểu SQL và driver có hành vi khác nhau. Không mặc định rằng cột tên `TIMESTAMP` trong mọi database đều lưu offset hoặc UTC theo cùng nghĩa.

### 12.2. Lịch hẹn trong tương lai theo giờ địa phương

Với lịch hẹn “9:00 sáng theo giờ Paris mỗi thứ Hai”, **Instant đơn lẻ không mang đủ ý nghĩa** để áp dụng các thay đổi DST trong tương lai hoặc cho một chuỗi lặp theo địa phương. Nên lưu lịch theo `LocalDateTime`/`LocalTime` cùng `ZoneId` và quy tắc lặp, rồi tính các Instant cụ thể khi cần.

`OffsetDateTime` mô tả offset đã xác định cho **một ngày giờ cụ thể**, không phải tên vùng để tái áp dụng quy tắc DST cho các lần lặp trong tương lai.

### 12.3. Khi yêu cầu phải giữ cả offset ban đầu

Một API có thể muốn bảo tồn thông tin người dùng gửi, ví dụ “giờ local và offset trong lịch sử giao dịch”. Chuyển ngay sang `Instant` rồi bỏ `OffsetDateTime` là **lossy đối với biểu diễn ban đầu** dù không mất thời điểm. Nếu cần audit đầy đủ, cân nhắc lưu **Instant** kèm **original offset** hoặc **ZoneId** và dữ liệu liên quan theo yêu cầu.

Đây là lựa chọn **schema nghiệp vụ**, không phải một hạn chế về độ chính xác của phép `toInstant()`.

## 13. Bất biến, thread-safety và thời gian hiện tại

Các kiểu `Instant`, `OffsetDateTime`, `ZoneOffset` trong `java.time` là **bất biến**. Các operation chuyển đổi tạo ra giá trị mới, không sửa giá trị cũ.

Ví dụ:

```java
// Mã minh họa.
OffsetDateTime original =
    OffsetDateTime.parse("2024-06-01T19:30+07:00");

OffsetDateTime changed =
    original.withOffsetSameInstant(ZoneOffset.UTC);

// original vẫn là 2024-06-01T19:30+07:00.
// changed là 2024-06-01T12:30Z.
```

Vì immutable, việc truyền một instance giữa nhiều method/thread không tự dẫn đến race condition do thay đổi nội tại của bản thân đối tượng. Tuy nhiên logic ứng dụng hoặc các object khác có thể vẫn có shared mutable state.

### 13.1. Clock để kiểm thử ổn định

`Instant.now()` đọc đồng hồ hệ thống và giá trị thay đổi theo mỗi lần chạy. Để test chuyển đổi, hãy dùng timestamp cố định hoặc inject `Clock`:

```java
// Đoạn minh họa.
Clock fixed = Clock.fixed(
    Instant.parse("2024-06-01T12:30:45Z"),
    ZoneOffset.UTC
);

Instant now = Instant.now(fixed);
// Kết quả tái lập: 2024-06-01T12:30:45Z
```

**Không suy từ việc `Instant` hỗ trợ nano rằng đồng hồ hệ thống có độ chính xác nano.** Độ phân giải và tính ổn định của nguồn thời gian là câu chuyện khác.

## 14. Xử lý ngoại lệ và biên dữ liệu

Những trường hợp sau đáng kiểm tra:

- `DateTimeParseException`: chuỗi không hợp định dạng ISO hoặc giá trị ngày giờ không hợp lệ.
- `DateTimeException`: offset ngoài phạm vi, ngày giờ vượt giới hạn khi chuyển biểu diễn.
- `NullPointerException`: một số API nhận tham số non-null nhưng được truyền `null`.
- `ArithmeticException`: chuyển một `Instant` quá lớn thành milliseconds hoặc phép số học tràn giới hạn `long`.
- `ZoneRulesException`: không tìm thấy quy tắc vùng hoặc dữ liệu timezone của runtime.

**Không bắt hết các exception rồi mặc định offset `UTC` cho input lỗi**. Điều đó có thể đổi thời điểm hoặc che một sai sót cấu hình.

Một chiến lược ở boundary:

1. Kiểm tra input có thiếu hoặc blank không.
2. Parse `OffsetDateTime` theo định dạng đã công bố.
3. Nếu không có offset nhưng API yêu cầu timestamp, trả lỗi `MISSING_OFFSET` thay vì đoán.
4. Chuyển về `Instant` để lưu/so sánh.
5. Nếu cần hiển thị theo vùng, dùng `Instant.atZone(zone)` hoặc `OffsetDateTime.ofInstant(instant, zone)`, có chính sách zone hợp lệ.
6. Chuyển lỗi kỹ thuật thành mã lỗi miền nghiệp vụ khi phù hợp, không dựa vào chuỗi `exception.getMessage()` như API contract.

## 15. Các lỗi phổ biến

### Lỗi 1 — nhầm Instant với local date-time

`Instant` không lưu ngày/giờ theo timezone người dùng. Muốn biểu diễn giờ địa phương, cung cấp offset hoặc zone.

### Lỗi 2 — nghĩ +07:00 phải cộng 7 giờ khi tính về UTC

Ngược lại: nếu local = UTC + 7 giờ thì UTC = local − 7 giờ. Dùng API để tránh nhầm dấu và ngày.

### Lỗi 3 — dùng withOffsetSameLocal để “đổi cách hiển thị” một sự kiện

`withOffsetSameLocal` có thể **đổi Instant**. Với timestamp sự kiện cần giữ nguyên, dùng `withOffsetSameInstant`.

### Lỗi 4 — cho rằng OffsetDateTime giữ ZoneId

Nó giữ offset, không giữ định danh vùng. Nếu cần `Europe/Paris` và DST, dùng `ZonedDateTime` hoặc lưu ZoneId riêng.

### Lỗi 5 — cố chuyển LocalDateTime thành Instant không có offset

Local clock không cho biết một thời điểm duy nhất nếu thiếu offset/zone. Không đoán timezone máy chủ.

### Lỗi 6 — dùng offset của ngày hôm nay cho sự kiện lịch sử/tương lai

Offset theo `ZoneId` có thể thay đổi do DST hoặc quy tắc địa phương. Lấy offset **tại chính Instant của sự kiện**.

### Lỗi 7 — coi hai OffsetDateTime cùng Instant thì equals phải true

`equals` xét cả local time và offset; `isEqual` hoặc so sánh `toInstant()` mới kiểm tra cùng timestamp.

### Lỗi 8 — chuyển qua milliseconds rồi cho rằng không mất nanosecond

`Instant.toEpochMilli()` chỉ giữ tới millisecond. Nếu cần độ phân giải cao hơn, giữ seconds+nanos hoặc dạng text thích hợp.

### Lỗi 9 — nhầm epoch seconds và epoch milliseconds

`Instant.ofEpochSecond(1_700_000_000)` khác hẳn `Instant.ofEpochMilli(1_700_000_000)`. Contract của hệ thống phải ghi rõ đơn vị.

### Lỗi 10 — đưa ngày giờ không có offset vào OffsetDateTime.parse

`"2024-02-29T10:15"` là local date-time, không phải chuỗi OffsetDateTime chuẩn có offset. Không tự append `Z` khi không có căn cứ.

### Lỗi 11 — dùng fixed offset cho lịch hẹn vùng có DST

Offset cố định thiếu lịch sử/quy tắc chuyển đổi. Với lịch hẹn theo vùng, cần ZoneId và chính sách xử lý gap/overlap.

### Lỗi 12 — cho rằng LocalDateTime.atOffset xác nhận offset của zone

Method này chỉ gắn offset được chọn; nó **không kiểm tra** offset đó có hợp lệ theo một zone địa lý. Dùng ZoneRules hoặc API strict nếu cần.

### Lỗi 13 — coi mọi Instant đều có thể đổi sang OffsetDateTime

`Instant` có phạm vi lớn hơn local date-time có offset; ở biên có thể ném `DateTimeException`.

### Lỗi 14 — dùng OffsetDateTime.toLocalDateTime rồi nghĩ có thể phục hồi Instant

Bỏ offset là **mất thông tin** cần cho phép chuyển ngược. Nếu cần timestamp tuyệt đối, giữ `Instant` hoặc `OffsetDateTime`.

### Lỗi 15 — ghi timezone/offset đầu vào không nhất quán vào database

Trước khi thiết kế schema, xác định cột lưu **Instant**, local date-time hay offset date-time; driver và hệ quản trị có thể khác nhau. Kiểm thử đọc/ghi round-trip, nhất là quanh DST.

### Lỗi 16 — dựa vào system default zone trong bài test

Máy developer, CI và production có thể khác timezone. Với test tái lập, dùng `Instant`/`ZoneId`/`Clock` cố định.

### Lỗi 17 — dùng compareTo thay isEqual để kiểm tra cùng thời điểm

`OffsetDateTime.compareTo` có thứ tự so sánh để nhất quán với `equals` khi hai local/offset khác nhau. Dùng `isEqual` hoặc `toInstant().equals(...)` khi chỉ quan tâm Instant.

## 16. Checklist code review

1. Input thể hiện **Instant**, **OffsetDateTime**, **LocalDateTime** hay **ZonedDateTime**? Tên biến/chữ ký đã thể hiện đúng chưa?
2. Khi chuyển từ Instant, đã chọn offset/ZoneId có nguồn gốc rõ ràng?
3. Khi chuyển từ OffsetDateTime, có dùng `toInstant()` thay vì tự trừ chuỗi giờ?
4. Khi chuyển từ LocalDateTime, có offset/zone **được cung cấp theo contract**, không đoán?
5. Nếu đổi offset, business cần giữ **cùng Instant** hay **cùng local clock**?
6. Nếu dùng ZoneId vùng, offset được lấy **tại ngày/Instant cần đổi** thay vì offset hiện tại của hệ thống?
7. Có trường hợp DST gap/overlap cần từ chối hoặc hỏi người dùng?
8. Có so sánh timestamp bằng `isEqual`/`Instant` khi mục tiêu là cùng thời điểm?
9. Có lưu offset hoặc ZoneId ban đầu riêng nếu business cần khôi phục cách hiển thị gốc?
10. Có dùng đúng đơn vị epoch seconds/milliseconds và lưu phần nanosecond theo yêu cầu?
11. Có kiểm tra sai format, missing offset, offset vượt phạm vi và DateTimeException tại boundary?
12. Có test các trường hợp vượt qua nửa đêm, cuối tháng/năm và khi đổi sang offset âm/dương?
13. Các phép chuyển có độc lập với timezone mặc định của server khi cần kết quả tái lập?
14. Có test schema/database/API round-trip để không mất ý nghĩa offset và precision?
15. Có chọn `Clock.fixed` khi test logic phụ thuộc thời điểm hiện tại?

## 17. Tự kiểm tra kiến thức

**Câu 1.** `Instant.parse("2024-06-01T12:30:45Z").atOffset(ZoneOffset.ofHours(7))` trả gì?

**Đáp án:** `2024-06-01T19:30:45+07:00`.

**Câu 2.** `OffsetDateTime.parse("2024-06-01T19:30:45+07:00").toInstant()` trả gì?

**Đáp án:** `2024-06-01T12:30:45Z`.

**Câu 3.** `instant.atOffset(+07:00)` có thay đổi bản thân Instant không?

**Đáp án:** Không. Nó tạo một `OffsetDateTime` mới thể hiện cùng timestamp ở offset được yêu cầu.

**Câu 4.** `withOffsetSameInstant` và `withOffsetSameLocal` khác nhau thế nào?

**Đáp án:** Loại đầu giữ Instant, thay local clock để thích nghi offset; loại sau giữ local clock và thường đổi Instant.

**Câu 5.** Tại sao `LocalDateTime` không thể tự chuyển thành Instant duy nhất?

**Đáp án:** Vì thiếu offset/zone. Cùng local clock có thể mang nhiều offset và tương ứng nhiều Instant khác nhau.

**Câu 6.** `OffsetDateTime.ofInstant(instant, ZoneId.of("Europe/Paris"))` có giữ ZoneId Paris không?

**Đáp án:** Không. Nó resolve offset ở Instant đó rồi tạo `OffsetDateTime`. Nếu cần giữ vùng, dùng `ZonedDateTime`.

**Câu 7.** Tại Paris, vì sao timestamp 12:00 UTC trong tháng 1 và tháng 7 hiển thị giờ địa phương khác nhau?

**Đáp án:** Vì các offset có hiệu lực khác nhau theo rules timezone (`+01:00` và `+02:00` trong ví dụ lịch sử).

**Câu 8.** Hai `OffsetDateTime` có local clock khác nhưng cùng Instant có thể có `equals == false` không?

**Đáp án:** Có. `equals` xét biểu diễn local + offset; `isEqual` xét cùng Instant.

**Câu 9.** `Instant` hỗ trợ nanosecond thì `toEpochMilli` có giữ toàn bộ nanosecond không?

**Đáp án:** Không. Nó chuyển sang milliseconds và có thể mất phần nhỏ hơn 1 ms.

**Câu 10.** `OffsetDateTime.parse("2024-02-29T10:15")` có hợp lệ theo ISO offset format mặc định không?

**Đáp án:** Không. Chuỗi thiếu offset.

**Câu 11.** Chuyển `Instant.MAX` sang `OffsetDateTime` tại UTC có chắc thành công không?

**Đáp án:** Không. Có thể ném `DateTimeException` do giới hạn local date-time.

**Câu 12.** `LocalDateTime.atOffset(ZoneOffset.ofHours(2))` có kiểm tra offset +02:00 hợp lệ cho Paris trong một ngày cụ thể không?

**Đáp án:** Không. Nó gắn offset được chỉ định; phải xác thực timezone rules riêng.

**Câu 13.** Lưu một sự kiện đã xảy ra rồi hiển thị cho người dùng thuộc nhiều vùng, nên giữ giá trị nào làm mốc so sánh?

**Đáp án:** `Instant` thường thích hợp vì lưu mốc tuyệt đối độc lập vùng hiển thị.

**Câu 14.** Với lịch hẹn “9 giờ Paris thứ Hai hằng tuần”, chỉ một OffsetDateTime có đủ quy tắc cho những lần hẹn tương lai không?

**Đáp án:** Không. Cần ZoneId vùng và quy tắc lịch lặp/giải quyết DST.

## 18. Tài liệu Java chính thức đang áp dụng

- [Oracle Java SE 26 — Instant](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html): `atOffset`, `atZone`, `getEpochSecond`, `getNano`, `toEpochMilli` và phạm vi.
- [Oracle Java SE 26 — OffsetDateTime](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/OffsetDateTime.html): `ofInstant`, `toInstant`, `withOffsetSameInstant`, `withOffsetSameLocal`, `isEqual`, `equals` và `compareTo`.
- [Oracle Java SE 26 — LocalDateTime](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDateTime.html): `atOffset`, `toInstant(ZoneOffset)`.
- [Oracle Java SE 26 — ZoneOffset](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneOffset.html): ý nghĩa của offset và các giới hạn hợp lệ.
- [Oracle Java SE 26 — ZoneId](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneId.html): định danh vùng và timezone rules.
- [Oracle Java SE 26 — ZonedDateTime](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html): giữ vùng, offset và cùng Instant qua các vùng.
- [Oracle Java SE 26 — ZoneRules](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/ZoneRules.html): xác nhận offset hợp lệ ở gap/overlap.

**Kết luận:** `Instant` là **mốc thời gian tuyệt đối**; `OffsetDateTime` là **mốc đó cùng giờ địa phương và offset**. Dùng `instant.atOffset(...)` hoặc `OffsetDateTime.ofInstant(...)` để chuyển sang biểu diễn có offset, và `offsetDateTime.toInstant()` để trở về timeline. Khi đổi offset, phân biệt nghiêm ngặt `withOffsetSameInstant` (giữ sự kiện) với `withOffsetSameLocal` (giữ đồng hồ, thường đổi sự kiện). Với timezone địa lý và DST, dùng `ZoneId`/`ZonedDateTime` khi cần bảo toàn quy tắc vùng, không coi một offset cố định là toàn bộ lịch sử múi giờ.