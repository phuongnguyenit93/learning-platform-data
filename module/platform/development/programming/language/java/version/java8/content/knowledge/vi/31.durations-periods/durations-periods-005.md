# Khoảng âm, giá trị bằng không và normalized trong Java

> **Chủ đề:** Java 8 — Khoảng thời gian. Bài giải thích **Duration âm**, **Period có các trường âm**, cách nhận biết **giá trị zero**, và ý nghĩa chính xác của **normalization**. Các API `java.time` được dùng đều xuất hiện từ Java 8 và vẫn hữu ích trong những phiên bản JDK hiện hành.

## 1. Vì sao cần hiểu dấu âm, zero và chuẩn hóa?

Một ứng dụng có thể cần xử lý những tình huống sau:

- Thời điểm kết thúc sớm hơn thời điểm bắt đầu: khoảng chênh lệch có hướng **âm**, chứ không phải luôn là lỗi.
- Hai mốc trùng nhau: khoảng thời gian thực sự bằng **zero**.
- Người dùng nhập **15 tháng**: hệ thống muốn hiển thị thành **1 năm 3 tháng**.
- Một dữ liệu nhận từ bên ngoài chứa **1 năm và -12 tháng**: xét các trường riêng rẽ thì không phải zero, nhưng nếu quy đổi thành tổng tháng sẽ triệt tiêu.
- Một bộ đếm có **-1 nanosecond**: khi chuyển sang `long milliseconds` có thể thành `0`, mặc dù giá trị gốc âm.

Để tránh xử lý sai, cần phân biệt **hai kiểu thời lượng**:

| Tiêu chí | `Duration` | `Period` |
| --- | --- | --- |
| Đơn vị | Giây và nanosecond | Năm, tháng, ngày lịch |
| Cách dùng thường thấy | Timeout, elapsed time, khoảng giữa `Instant` | Gia hạn tháng, tính kỳ lịch, cộng ngày/tháng/năm |
| Có thể âm? | Có, tổng thời gian nhỏ hơn 0 | Có, từng trường có thể âm |
| Giá trị zero | Tổng thời gian đúng 0 giây | Cả 3 trường năm/tháng/ngày bằng 0 |
| Normalization | Giây/nano được chuẩn hóa **ngay trong factory và phép tính** | Gọi `Period.normalized()` để chuẩn hóa **năm/tháng** |
| `normalized()` | **Không có** | **Có** |
| Một ngày | `ofDays(1)` nghĩa 24 giờ tiêu chuẩn | `ofDays(1)` nghĩa một ngày lịch |
| Có natural ordering? | `Duration` là `Comparable` | Không có thứ tự độ dài tổng quát giữa các Period |

Cả `Duration` và `Period` đều là **immutable value-based classes**. Dùng `equals` để so giá trị, không dùng `==` để suy ra hai giá trị cùng hoặc khác nhau.

### 1.1. Khoảng thời gian có hướng

Khoảng chênh lệch giữa hai mốc phải đi kèm **hướng tính**:

~~~java
Instant start = Instant.parse("2025-07-02T10:00:00Z");
Instant end = Instant.parse("2025-07-02T09:58:30Z");

Duration delta = Duration.between(start, end);
System.out.println(delta.getSeconds()); // -90
~~~

Đây là **đoạn mã minh họa**, cần import `java.time.Instant` và `java.time.Duration`. Giá trị `end` đứng trước `start` 90 giây nên chênh lệch âm.

Không nên tự gọi `abs()` nếu dấu âm đang mang thông tin như “quá hạn”, “xảy ra trước mốc” hoặc “sai thứ tự dữ liệu”.

## 2. Duration âm được biểu diễn thế nào?

### 2.1. Cặp seconds và nano-of-second

`Duration` lưu thời lượng dưới dạng:

~~~text
totalSeconds = getSeconds() + getNano() / 1_000_000_000.0

getSeconds(): long
getNano()   : int, từ 0 tới 999_999_999
~~~

Sơ đồ trên giúp giải thích số học; trong code yêu cầu độ chính xác nanosecond, **không nên tự chuyển thành double** vì có thể bị làm tròn. Điều cần nhớ: **`getNano()` không bao giờ âm**.

Ví dụ `-0,5 giây`:

~~~java
Duration minusHalf = Duration.ofMillis(-500);

System.out.println(minusHalf.getSeconds()); // -1
System.out.println(minusHalf.getNano());    // 500000000
System.out.println(minusHalf.isNegative()); // true
~~~

Giá trị tổng là `-1 giây + 500.000.000 nanosecond = -0,5 giây`. Đây là biểu diễn **đúng theo hợp đồng**, không phải dấu hiệu lỗi.

### 2.2. Trường hợp đặc biệt: âm một nanosecond

~~~java
Duration oneNanoBack = Duration.ofNanos(-1);

System.out.println(oneNanoBack.getSeconds()); // -1
System.out.println(oneNanoBack.getNano());    // 999999999
System.out.println(oneNanoBack.toNanos());    // -1
~~~

Java lưu `-1 ns` thành `-1 giây + 999.999.999 ns`. Nếu một giao thức truyền riêng cặp `seconds/nanos`, **không được suy ra rằng phần nano mang cùng dấu với tổng Duration**.

### 2.3. Factory ofSeconds tự chuẩn hóa nanoAdjustment

`Duration.ofSeconds(seconds, nanoAdjustment)` nhận `nanoAdjustment` có thể âm hoặc lớn hơn một tỷ; factory đưa kết quả về cặp seconds/nanos hợp lệ:

~~~java
Duration a = Duration.ofSeconds(1, -1_000_000_000L);
Duration b = Duration.ZERO;

System.out.println(a.equals(b)); // true
System.out.println(a.getSeconds()); // 0
System.out.println(a.getNano()); // 0
~~~

Thêm ví dụ:

~~~java
Duration almostOneSecond =
        Duration.ofSeconds(1, -1L);

// Gần một giây, thiếu đúng 1 nanosecond.
// getSeconds() == 0, getNano() == 999999999.
~~~

Hai đoạn này là **minh họa Java 8**. Không cần tự viết phép chia lấy dư với giá trị âm khi API đã xử lý normalization nội tại.

### 2.4. Duration không có normalized()

**Không có phương thức `Duration.normalized()` trong Java 8.** Khác với Period, Duration duy trì cặp seconds/nanos được chuẩn hóa từ khi tạo.

~~~java
// Sai vì method không tồn tại:
// Duration.ofNanos(-1).normalized();

// Đúng: tạo qua factory.
Duration result = Duration.ofSeconds(0, -1);
~~~

Dòng sai được **comment** rõ ràng để không ảnh hưởng ví dụ. `result` biểu diễn `-1 ns` theo cùng quy tắc chuẩn ở trên.

## 3. Duration.ZERO và phép kiểm tra isZero/isNegative

### 3.1. Zero là giá trị chính xác

`Duration.ZERO` là 0 giây và 0 nano:

~~~java
Duration zero = Duration.ZERO;

System.out.println(zero.isZero());         // true
System.out.println(zero.isNegative());     // false
System.out.println(zero.equals(
        Duration.ofSeconds(1, -1_000_000_000L))); // true
~~~

Có thể dùng `Duration.ofSeconds(0)` hoặc `Duration.parse("PT0S")` để tạo giá trị bằng zero. `Duration.ZERO` là constant tiện dụng nhưng **không dùng `==` để kiểm tra equality** giữa các object value-based.

### 3.2. isNegative khác isZero

~~~java
Duration earlier = Duration.ofSeconds(-2);
Duration exactlyZero = Duration.ZERO;
Duration later = Duration.ofSeconds(2);

System.out.println(earlier.isNegative());   // true
System.out.println(exactlyZero.isNegative()); // false
System.out.println(exactlyZero.isZero());    // true
System.out.println(later.isNegative());     // false
~~~

`Duration.isNegative()` hỏi **tổng khoảng có nhỏ hơn 0 không**, không đơn thuần nhìn một trường bất kỳ như Period. Nếu cần ba trạng thái, dùng `compareTo(Duration.ZERO)`:

~~~java
int compare = d.compareTo(Duration.ZERO);

if (compare < 0) {
    // Khoảng âm.
} else if (compare == 0) {
    // Khoảng bằng không.
} else {
    // Khoảng dương.
}
~~~

Đây là **đoạn minh họa**, với `d` là Duration đã có. Không giả định `compareTo` luôn trả đúng `-1` hoặc `1`; chỉ dấu của kết quả được dùng.

### 3.3. Sai lầm khi nhìn toMillis()

`Duration.toMillis()` chuyển Duration thành số mili giây `long`, loại bỏ phần nhỏ hơn một mili giây. Nếu Duration có độ lớn dưới một mili giây, số trả về có thể bằng 0:

~~~java
Duration tiny = Duration.ofNanos(-1);

System.out.println(tiny.isNegative()); // true
System.out.println(tiny.isZero());     // false
System.out.println(tiny.toMillis());   // 0
~~~

`toMillis()==0` **không tương đương** `isZero()==true`. Điều này rất quan trọng trong logic timeout, TTL, số liệu latency và thời hạn chính xác đến micro/nano.

Nếu ứng dụng chủ động vận hành ở độ phân giải millisecond, nó cần **chính sách làm tròn/cắt và xử lý khoảng dưới một ms** rõ ràng, không được ngầm coi mọi giá trị đó là zero thực sự.

### 3.4. toNanos và overflow

`Duration.toNanos()` tính tổng số nanosecond dưới dạng một `long`. Không phải mọi `Duration` hợp lệ đều biểu diễn được bằng một `long` nanosecond vì miền của Duration rất rộng. API có thể ném `ArithmeticException` khi tràn.

Tương tự `toMillis()` cũng có thể tràn với Duration cực dài. Nếu cần serialize thời lượng lớn mà vẫn giữ nanosecond, dùng cặp `(getSeconds(),getNano())` hoặc chuỗi Duration theo hợp đồng, có validation ở bên nhận.

## 4. abs, negated, cộng/trừ và overflow

### 4.1. abs lấy độ lớn không âm

~~~java
Duration d = Duration.ofSeconds(-90);
Duration positiveMagnitude = d.abs();

System.out.println(positiveMagnitude.getSeconds()); // 90
~~~

`abs()` phù hợp nếu nghiệp vụ cần **độ lệch tuyệt đối**, chẳng hạn độ lớn chênh lệch so với mục tiêu. Nhưng với `remainingUntilDeadline`, đổi âm thành dương có thể giấu mất thông tin quá hạn.

### 4.2. negated đổi hướng

~~~java
Duration d = Duration.ofMinutes(-2);
Duration reversed = d.negated();

// reversed biểu diễn +2 phút, không sửa d.
~~~

`negated()` khác `abs()`: khi đầu vào dương, `negated()` chuyển thành âm còn `abs()` vẫn dương.

### 4.3. Các lượng trái dấu có thể triệt tiêu

~~~java
Duration a = Duration.ofMinutes(-3);
Duration b = Duration.ofMinutes(3);

Duration combined = a.plus(b);
System.out.println(combined.isZero()); // true
~~~

Duration immutable nên `a` và `b` không đổi. Kết quả zero được lưu dưới dạng chuẩn, không còn dấu của các lượng ban đầu.

### 4.4. Miền số hữu hạn

`Duration` lưu giây bằng `long`. Một số phép tính như `negated`, `abs`, cộng hoặc nhân có thể ném `ArithmeticException` khi vượt miền biểu diễn.

~~~java
Duration smallestWholeSeconds =
        Duration.ofSeconds(Long.MIN_VALUE);

// Lời gọi sau nếu thực thi sẽ ném ArithmeticException:
// smallestWholeSeconds.negated();
~~~

Đây là **đoạn minh họa không thực thi lời gọi gây lỗi**. Trường hợp `Long.MIN_VALUE` không có số đối dương biểu diễn được trong `long`. Đừng "khắc phục" bằng cách gọi `Math.abs(Long.MIN_VALUE)`: phép này cũng không biến được thành số dương.

## 5. Period âm có ý nghĩa khác Duration âm

`Period` là lượng thời gian lịch với ba trường:

~~~java
int years = period.getYears();
int months = period.getMonths();
int days = period.getDays();
~~~

Đây là **đoạn minh họa**, giả định `period` là một Period đã có.

### 5.1. Các trường có thể khác dấu

`Period.of(years,months,days)` nhận các trường riêng biệt. Một giá trị có thể chứa **năm dương và tháng âm**:

~~~java
Period mixed = Period.of(1, -1, 0);
~~~

Nó có `1 năm`, `-1 tháng`, `0 ngày`. Period **không tự chuẩn hóa thành 11 tháng** khi tạo.

### 5.2. Period.isNegative là phép kiểm tra *bất kỳ trường nào âm*

Đây là khác biệt then chốt so với Duration:

~~~java
Period mixed = Period.of(1, -1, 0);

System.out.println(mixed.isNegative());              // true
System.out.println(mixed.normalized());              // P11M
System.out.println(mixed.normalized().isNegative()); // false
~~~

Bản gốc có tháng âm nên `isNegative` trả true dù tổng năm/tháng tương đương +11 tháng. Bản chuẩn hóa chỉ còn 11 tháng dương nên trả false.

**Không diễn giải `Period.isNegative()` là "giá trị tổng thể nhỏ hơn 0 ngày/giây"**, nhất là khi Period có dấu hỗn hợp ở năm, tháng và ngày. Độ dài một tháng thay đổi theo ngày mốc.

### 5.3. Period.between có thể trả giá trị âm

~~~java
LocalDate start = LocalDate.of(2025, 4, 10);
LocalDate end = LocalDate.of(2025, 4, 7);

Period backwards = Period.between(start, end);
// P-3D
~~~

Đây là **đoạn minh họa**. Ngày kết thúc sớm hơn ngày bắt đầu ba ngày lịch. Nếu đổi thứ tự tham số, kết quả thành dương ba ngày.

### 5.4. Không có độ dài chung cho mọi Period

Một tháng không luôn bằng 30 ngày:

~~~java
LocalDate jan10 = LocalDate.of(2025, 1, 10);

System.out.println(jan10.plus(Period.ofMonths(1)));
// 2025-02-10

System.out.println(jan10.plus(Period.ofDays(30)));
// 2025-02-09
~~~

Period không cung cấp `Comparable<Period>` với thứ tự toàn phần giống Duration. Muốn so hai kỳ lịch, cần **định nghĩa ngày tham chiếu và tiêu chí** hoặc giới hạn so sánh vào những đơn vị tương thích của nghiệp vụ.

## 6. Period.normalized chuẩn hóa tháng thành năm

### 6.1. Quy tắc 12 tháng/năm

`Period.normalized()` trả **một Period mới** với **năm và tháng** được chuẩn hóa theo tổng số tháng. **Ngày giữ nguyên**.

Mô hình:

~~~text
totalMonths = years * 12 + months

normalizedYears  = totalMonths / 12
normalizedMonths = totalMonths % 12
normalizedDays   = days
~~~

Phép chia số nguyên và phần dư phải hiểu theo quy tắc Java; kết quả các trường phải nằm trong miền dữ liệu hỗ trợ. API có thể báo `ArithmeticException` nếu không biểu diễn được năm sau normalization.

Không tự quy đổi ngày thành tháng vì tháng có độ dài khác nhau. `P30D` không tự thành `P1M`.

### 6.2. Ví dụ 15 tháng

~~~java
Period raw = Period.of(0, 15, 2);
Period normalized = raw.normalized();

System.out.println(raw);        // P15M2D
System.out.println(normalized); // P1Y3M2D
~~~

Năm chuyển từ 0 thành 1, tháng từ 15 thành 3, và ngày **vẫn bằng 2**. Vì Period immutable, `raw` không thay đổi.

### 6.3. Ví dụ tháng âm

~~~java
Period raw = Period.ofMonths(-13);

System.out.println(raw.normalized()); // P-1Y-1M
~~~

`-13 tháng` trở thành `-1 năm và -1 tháng`. Đây vẫn là một giá trị lịch, không có quy tắc mặc định đổi sang số giây cố định.

### 6.4. Năm và tháng trái dấu

~~~java
Period p = Period.of(1, -25, 4);

System.out.println(p.normalized()); // P-1Y-1M4D
~~~

Tổng tháng là `12 - 25 = -13`. Sau chuẩn hóa thành -1 năm -1 tháng, còn **4 ngày dương** vì `normalized` không động đến trường ngày.

Không thể suy ra mọi thành phần sau `normalized()` phải cùng dấu. Dữ liệu dấu hỗn hợp vẫn có thể tồn tại khi ngày khác hướng với năm/tháng.

### 6.5. Period có thể thành zero sau chuẩn hóa

~~~java
Period cancellation = Period.of(1, -12, 0);

System.out.println(cancellation.isZero());              // false
System.out.println(cancellation.normalized().isZero()); // true
System.out.println(cancellation.normalized());          // P0D
~~~

Trước khi normalized, trường năm là `1` và tháng `-12`, nên `Period.isZero()` trả false. Sau chuẩn hóa, tổng tháng bằng 0 và ngày cũng 0, vì thế `P0D` là zero.

Đây là lý do logic “không tạo ra thay đổi lịch khi tổng năm/tháng triệt tiêu” có thể chọn `period.normalized().isZero()`, chứ không chỉ `period.isZero()`. Nhưng chỉ làm vậy nếu đó thật sự là ý nghĩa nghiệp vụ.

### 6.6. Normalization không phải tự động ở equals

~~~java
Period months = Period.ofMonths(12);
Period years = Period.ofYears(1);

System.out.println(months.equals(years));              // false
System.out.println(months.normalized().equals(years)); // true
~~~

`Period.equals` so sánh **ba trường năm, tháng, ngày**; nó không quy đổi trước khi so. Hai Period tương đương về tổng tháng nhưng có biểu diễn khác nhau vẫn có thể khác nhau theo `equals` và `hashCode`.

Nếu hệ thống muốn `P12M` và `P1Y` là cùng một khóa nghiệp vụ, cần chuẩn hóa theo chính sách của ứng dụng trước khi đưa vào Set/Map. Nhưng nếu hợp đồng cần giữ nguyên cách người dùng nhập ("12 tháng" so với "1 năm"), không nên xóa biểu diễn gốc mà không có chủ đích.

### 6.7. toTotalMonths không tính ngày

~~~java
Period a = Period.of(1, 3, 2);
Period b = Period.of(1, 3, 40);

System.out.println(a.toTotalMonths()); // 15
System.out.println(b.toTotalMonths()); // 15
~~~

Hai Period có cùng totalMonths nhưng khác **days**. Không dùng `toTotalMonths()==0` như phép kiểm tra toàn bộ Period bằng zero; còn phải xét ngày.

### 6.8. Period.normalized không phải phương thức sửa tại chỗ

~~~java
Period raw = Period.ofMonths(15);
raw.normalized(); // Bỏ qua kết quả: raw vẫn P15M.

Period canonical = raw.normalized(); // P1Y3M.
~~~

Đây là **đoạn minh họa**. Phương thức trả một Period mới; nếu muốn dùng bản chuẩn hóa, hãy lưu giá trị trả về.

## 7. Period.ZERO và khái niệm zero theo trường

`Period.ZERO` có ba trường năm/tháng/ngày đều bằng 0. `Period.of(0,0,0)` và `Period.parse("P0D")` cùng giá trị.

~~~java
Period z = Period.ZERO;

System.out.println(z.isZero());      // true
System.out.println(z.isNegative());  // false
System.out.println(z.getYears());    // 0
System.out.println(z.getMonths());   // 0
System.out.println(z.getDays());     // 0
~~~

### 7.1. Zero về mặt cấu trúc và zero sau normalization

| Period | `isZero()` | `normalized().isZero()` | Nhận xét |
| --- | --- | --- | --- |
| `P0D` | true | true | Ba trường đều zero |
| `P1Y-12M` | false | true | Hai thành phần triệt tiêu |
| `P12M` | false | false | Tương đương một năm, không phải zero |
| `P1Y-12M2D` | false | false | Tổng tháng zero nhưng còn hai ngày |
| `P-3D` | false | false | Ba ngày âm |

Bảng này giúp tránh lỗi khi thiết kế validation hoặc canonicalization. **Không** áp dụng `normalized` để làm hợp lệ một Period không đúng ngữ nghĩa nghiệp vụ; nó chỉ biến đổi biểu diễn năm/tháng theo quy tắc.

### 7.2. Period.negated đổi dấu từng thành phần

~~~java
Period original = Period.of(1, -2, 3);
Period reverse = original.negated();

// reverse: năm -1, tháng +2, ngày -3.
~~~

`negated()` không tự normalized. Giá trị `Integer.MIN_VALUE` tại một trong ba trường có thể gây overflow khi lấy số đối, dẫn đến `ArithmeticException`.

### 7.3. Period.isNegative không phải phép so tổng số tháng với 0

~~~java
Period mixed = Period.of(1, -1, 0);

System.out.println(mixed.isNegative()); // true
System.out.println(mixed.toTotalMonths()); // 11
~~~

Vừa có tháng âm vừa có totalMonths dương là hoàn toàn có thể. Nếu ứng dụng muốn biết **tổng tháng** âm hay dương **và không quan tâm days**, hãy diễn đạt đúng ý định bằng `toTotalMonths()`; nếu có ngày, không có một phép so “tổng dài bao nhiêu” phổ quát cho mọi ngày bắt đầu.

## 8. Chuỗi ISO-8601 và âm/zero

### 8.1. Duration.parse

Các dạng được JDK chấp nhận:

| Chuỗi | Ý nghĩa |
| --- | --- |
| `PT0S` | Zero Duration |
| `PT30S` | +30 giây |
| `-PT30S` | -30 giây |
| `PT-30S` | -30 giây theo cú pháp thành phần được Java chấp nhận |
| `PT-0.5S` | -0,5 giây |
| `PT1H30M` | +90 phút |
| `-PT1H30M` | -90 phút |

~~~java
Duration zero = Duration.parse("PT0S");
Duration negative = Duration.parse("-PT1H30M");

System.out.println(zero.isZero());       // true
System.out.println(negative.toMinutes()); // -90
~~~

Đây là **đoạn minh họa**. Java parser hỗ trợ cả dấu toàn chuỗi và, trong một số trường hợp, dấu ở thành phần. Khi trao đổi với dịch vụ ngoài Java, cần chuẩn hóa format và kiểm thử parser bên kia thay vì cho rằng mọi parser ISO đều nhận cùng biến thể.

### 8.2. Period.parse

Ví dụ:

| Chuỗi | Ý nghĩa |
| --- | --- |
| `P0D` | Zero Period |
| `P1Y2M3D` | Một năm hai tháng ba ngày |
| `P15M` | Mười lăm tháng chưa normalize |
| `P-1Y2M` | Một năm âm, hai tháng dương |
| `-P1Y2M` | Cả năm và tháng âm |
| `P-3D` | Ba ngày âm |

~~~java
Period zero = Period.parse("P0D");
Period months = Period.parse("P15M");

System.out.println(zero.isZero()); // true
System.out.println(months.normalized()); // P1Y3M
~~~

Đây là **đoạn minh họa**. Không nên tự tách dấu từ chuỗi bằng cách kiểm tra `startsWith("-")`: `P1Y-1M` có dấu âm ở tháng dù chuỗi bắt đầu bằng `P`.

### 8.3. PT0S khác P0D

`PT0S` parse thành `Duration.ZERO`; `P0D` parse thành `Period.ZERO`. Hai kiểu dữ liệu khác nhau dù đều có nội dung zero của riêng chúng.

Một API nên định nghĩa loại trường/đơn vị rõ ràng. Chuyển Period sang Duration không tự nhiên khi có năm/tháng; phải biết ngày gốc và, nếu muốn elapsed time thật, timezone/offset phù hợp.

### 8.4. Có bắt buộc dùng toString trong API?

`Duration.toString()` và `Period.toString()` trả representation có cú pháp tương thích parser của chính JDK; hữu ích cho log và serialization theo hợp đồng. Tuy nhiên, **mức độ hỗ trợ chuỗi dấu âm hỗn hợp có thể khác giữa các nền tảng**. Nếu API đa ngôn ngữ, cần versioned format và integration tests.

Không tự tính dấu của Duration bằng text; gọi `isNegative`. Không suy ra Period là “tổng âm” chỉ vì có ký tự `-` trong `toString()`.

## 9. Tính lịch và thời gian thực: khi nào một ngày không bằng 24 giờ?

### 9.1. Duration.ofDays(1) là 24 giờ tiêu chuẩn

~~~java
Duration exactDay = Duration.ofDays(1);
System.out.println(exactDay.toHours()); // 24
~~~

### 9.2. Period.ofDays(1) là một ngày lịch

~~~java
Period calendarDay = Period.ofDays(1);
System.out.println(calendarDay.getDays()); // 1
~~~

Đây là các đoạn minh họa. Với vùng có DST, **một ngày lịch** có thể có 23 hoặc 25 giờ thực tế, trong khi `Duration.ofDays(1)` vẫn đúng 24 giờ.

### 9.3. Ví dụ đi qua DST

Ở vùng `America/New_York`, chuyển sang giờ mùa hè ngày 10/03/2024:

~~~java
ZonedDateTime start = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0,
        ZoneId.of("America/New_York"));

ZonedDateTime calendarTomorrow =
        start.plus(Period.ofDays(1));

ZonedDateTime after24Hours =
        start.plus(Duration.ofHours(24));
~~~

Đây là **đoạn minh họa**, cần import `ZonedDateTime` và `ZoneId`. Theo quy tắc múi giờ tại ngày nêu trên:

- `calendarTomorrow`: 12:00 ngày 10/03/2024, tức **23 giờ thực tế** sau start.
- `after24Hours`: 13:00 ngày 10/03/2024, đúng **24 giờ thực tế** sau start.

Vì vậy hãy đặt tên rõ ý định: `oneCalendarDay` hay `twentyFourHours`. Nếu deadline được mô tả bằng “ngày tiếp theo theo lịch địa phương”, Period/LocalDate có ý nghĩa hơn; nếu TTL yêu cầu đúng 24h elapsed, Duration/Instant phù hợp hơn.

### 9.4. Duration.between(LocalDateTime, LocalDateTime) không tự biết DST

`LocalDateTime` chỉ chứa ngày/giờ local, không có zone. `Duration.between(localA,localB)` tính khoảng trên các giá trị local, **không đủ để xác định elapsed time thực qua DST**.

Khi cần tính chênh lệch thực, quy các mốc có ngữ nghĩa thời điểm thành `Instant` rồi dùng `Duration.between(instantA,instantB)`. Với local date-time nằm trong gap/overlap DST, cần có chính sách chọn vùng/offset trước khi chuyển.

## 10. Ứng dụng nghiệp vụ của âm, zero và normalized

### 10.1. Deadline: còn lại, hết hạn, quá hạn

~~~java
Duration remaining =
        Duration.between(nowInstant, deadlineInstant);

if (remaining.isNegative()) {
    // Đã quá deadline.
} else if (remaining.isZero()) {
    // Đúng thời điểm deadline.
} else {
    // Chưa tới deadline.
}
~~~

Đây là **đoạn minh họa**, với `nowInstant` và `deadlineInstant` đã có. Nó giả định hai mốc đến từ hệ thống thời gian có ý nghĩa thống nhất; trong hệ phân tán, clock skew vẫn có thể ảnh hưởng kết quả.

**Đừng tự động gọi `abs()`**: quá hạn 5 phút sẽ trở thành +5 phút và bị hiểu nhầm là “còn 5 phút”.

### 10.2. Timeout: âm thường là input không hợp lệ

~~~java
void validateTimeout(Duration timeout) {
    if (timeout == null || timeout.isNegative()) {
        throw new IllegalArgumentException(
                "timeout must be non-negative");
    }
}
~~~

Đây là **đoạn phương thức minh họa**, không phải file Java độc lập. Với `Duration.ZERO`, phải quy định rõ theo API đích: zero có thể là “không đợi”, “deadline tức thì”, hoặc một ý nghĩa mặc định khác, tùy thư viện.

### 10.3. Gia hạn hợp đồng theo tháng

Một input `Period.ofMonths(15)` có thể được chuẩn hóa thành `P1Y3M` để hiển thị hoặc làm khóa canonical:

~~~java
Period input = Period.ofMonths(15);
Period canonical = input.normalized();
~~~

Nhưng không áp dụng normalization khi **cách biểu diễn nguyên thủy** (“15 tháng” thay vì “1 năm 3 tháng”) là dữ liệu pháp lý hoặc nghiệp vụ cần giữ; nếu cần, lưu cả raw input và giá trị chuẩn hóa phục vụ tính toán.

### 10.4. Period có dấu hỗn hợp nên được xử lý có chủ đích

Với `Period.of(1,-25,4)`, tổng tháng âm nhưng ngày dương. Một yêu cầu “một khoảng âm hay dương” không thể giải bằng so `getDays()` hay `isNegative()` rồi mặc định một số giờ cụ thể. Cần quyết định:

- Có cho phép Period hỗn hợp hay muốn từ chối?
- Có chuẩn hóa năm/tháng trước khi lưu?
- Đơn vị ngày có được tính riêng hay dựa vào một ngày mốc?
- Khi so kết quả, dùng cùng ngày tham chiếu và lịch nào?

Một quy tắc tốt cần được kiểm thử trên **ngày cuối tháng, năm nhuận và DST** nếu những trường hợp đó nằm trong phạm vi ứng dụng.

### 10.5. Zero không phải giá trị “thiếu dữ liệu”

`Duration.ZERO` và `Period.ZERO` là các giá trị đúng nghĩa. Nếu một API cần biểu diễn “chưa tính” hoặc “chưa được cung cấp”, dùng `Optional<Duration>`/`Optional<Period>` hoặc trạng thái riêng thay vì trả 0 rồi khiến caller không phân biệt được.

## 11. Ví dụ hoàn chỉnh chạy được bằng Java 8

Lưu đoạn mã sau thành **NegativeZeroNormalizedDemo.java**. Dữ liệu trong chương trình cố định nên stdout không phụ thuộc thời gian hiện tại, locale, hoặc timezone mặc định.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.Period;

public final class NegativeZeroNormalizedDemo {
    public static void main(String[] args) {
        Duration minusHalf = Duration.ofMillis(-500);

        System.out.println("negative duration = "
                + minusHalf.isNegative());
        System.out.println("duration seconds = "
                + minusHalf.getSeconds());
        System.out.println("duration nanos = "
                + minusHalf.getNano());
        System.out.println("duration text = " + minusHalf);
        System.out.println("absolute duration = "
                + minusHalf.abs());

        Duration tiny = Duration.ofNanos(-1);
        System.out.println("tiny negative = "
                + tiny.isNegative());
        System.out.println("tiny toMillis = "
                + tiny.toMillis());

        Duration cancelled =
                Duration.ofSeconds(1, -1_000_000_000L);
        System.out.println("duration zero = "
                + cancelled.isZero());
        System.out.println("Duration.ZERO text = "
                + Duration.ZERO);
        System.out.println("parse negative minutes = "
                + Duration.parse("-PT1H30M").toMinutes());

        Instant later =
                Instant.parse("2025-07-02T10:00:00Z");
        Instant earlier =
                Instant.parse("2025-07-02T09:58:30Z");
        System.out.println("backwards seconds = "
                + Duration.between(later, earlier).getSeconds());

        Period raw = Period.of(0, 15, 2);
        Period normal = raw.normalized();
        System.out.println("raw period = " + raw);
        System.out.println("normalized period = " + normal);
        System.out.println("total months = "
                + raw.toTotalMonths());
        System.out.println("days preserved = "
                + normal.getDays());

        Period mixed = Period.of(1, -1, 0);
        System.out.println("mixed isNegative = "
                + mixed.isNegative());
        System.out.println("mixed normalized = "
                + mixed.normalized());
        System.out.println("mixed normalized negative = "
                + mixed.normalized().isNegative());

        Period cancelling = Period.of(1, -12, 0);
        System.out.println("cancelling raw zero = "
                + cancelling.isZero());
        System.out.println("cancelling normalized zero = "
                + cancelling.normalized().isZero());
        System.out.println("cancelling normalized text = "
                + cancelling.normalized());

        System.out.println("negative 13 months = "
                + Period.ofMonths(-13).normalized());

        Period threeDaysBack = Period.between(
                LocalDate.of(2025, 4, 10),
                LocalDate.of(2025, 4, 7));
        System.out.println("backwards period = "
                + threeDaysBack);

        Period year = Period.ofYears(1);
        Period twelveMonths = Period.ofMonths(12);
        System.out.println("raw equality = "
                + year.equals(twelveMonths));
        System.out.println("normalized equality = "
                + year.equals(twelveMonths.normalized()));

        LocalDate jan10 = LocalDate.of(2025, 1, 10);
        System.out.println("plus one month = "
                + jan10.plus(Period.ofMonths(1)));
        System.out.println("plus thirty days = "
                + jan10.plus(Period.ofDays(30)));
        System.out.println("duration day hours = "
                + Duration.ofDays(1).toHours());

        System.out.println("parsed Duration.ZERO = "
                + Duration.parse("PT0S").equals(Duration.ZERO));
        System.out.println("parsed Period.ZERO = "
                + Period.parse("P0D").equals(Period.ZERO));
    }
}
~~~

Dùng JDK 17+ để biên dịch với mục tiêu Java 8:

~~~bash
javac --release 8 NegativeZeroNormalizedDemo.java
java NegativeZeroNormalizedDemo
~~~

**Stdout đúng với dữ liệu cố định:**

~~~text
negative duration = true
duration seconds = -1
duration nanos = 500000000
duration text = PT-0.5S
absolute duration = PT0.5S
tiny negative = true
tiny toMillis = 0
duration zero = true
Duration.ZERO text = PT0S
parse negative minutes = -90
backwards seconds = -90
raw period = P15M2D
normalized period = P1Y3M2D
total months = 15
days preserved = 2
mixed isNegative = true
mixed normalized = P11M
mixed normalized negative = false
cancelling raw zero = false
cancelling normalized zero = true
cancelling normalized text = P0D
negative 13 months = P-1Y-1M
backwards period = P-3D
raw equality = false
normalized equality = true
plus one month = 2025-02-10
plus thirty days = 2025-02-09
duration day hours = 24
parsed Duration.ZERO = true
parsed Period.ZERO = true
~~~

### 11.1. Giải thích từng nhóm output

1. `-500 milliseconds` có giây `-1` và nano `500000000` nên tổng bằng -0,5s; `abs()` trả `PT0.5S`.
2. `-1 nanosecond` thật sự âm nhưng khi chuyển sang milliseconds nguyên bị cắt thành `0`; đây là mất độ phân giải, không phải bằng zero.
3. Factory `Duration.ofSeconds(1,-1 tỷ nano)` chuẩn hóa thành Duration đúng bằng 0; chuỗi của `Duration.ZERO` là `PT0S`.
4. `Duration.parse("-PT1H30M")` cho -90 phút. `Duration.between(later,earlier)` âm 90 giây.
5. `Period.of(0,15,2)` giữ dạng `P15M2D` cho đến khi `normalized()` tạo `P1Y3M2D`. Tổng số tháng bằng 15, ngày 2 giữ nguyên.
6. `Period.of(1,-1,0)` có trường tháng âm nên `isNegative()==true`; sau chuẩn hóa thành `P11M` chỉ có tháng dương nên false.
7. `Period.of(1,-12,0)` ban đầu không zero theo từng trường; sau normalized trở thành `P0D` và `isZero()` true.
8. `Period.ofMonths(-13)` chuẩn hóa thành `P-1Y-1M`; ngày kết thúc trước ngày bắt đầu ba ngày cho `P-3D`.
9. `P1Y` khác `P12M` theo `equals` vì cấu trúc ba trường khác; khi chuẩn hóa mười hai tháng thì equality trả true.
10. Một tháng từ 10/01/2025 là 10/02/2025, còn ba mươi ngày cho 09/02/2025.
11. `Duration.ofDays(1)` là 24h, và parse zero đúng với từng loại.

## 12. Những lỗi phổ biến cần tránh

### Lỗi 1 — Nghĩ getNano() âm nếu Duration âm

Sai: `Duration.ofMillis(-500)` có `getNano()==500000000`. Đúng: nhìn cặp seconds/nanos đã chuẩn hóa hoặc dùng `isNegative()`.

### Lỗi 2 — Dùng toMillis()==0 thay cho isZero()

Sai nếu Duration có độ lớn nhỏ hơn 1 ms. `Duration.ofNanos(-1).toMillis()==0` nhưng Duration vẫn âm. Dùng `isZero` để kiểm tra zero chính xác.

### Lỗi 3 — Tự động abs khoảng âm trong logic deadline

Khoảng âm có thể là dấu quá hạn. Chỉ lấy `abs()` khi nghiệp vụ thật sự cần độ lớn, không che mất hướng thời gian.

### Lỗi 4 — Nhầm Period.isNegative với tổng số tháng âm

`Period.of(1,-1,0).isNegative()` là true vì tháng âm, mặc dù `toTotalMonths()==11`. Phải hiểu hợp đồng kiểm tra từng trường.

### Lỗi 5 — Nghĩ Period.of(1,-12,0).isZero() là true

Trước normalized, năm và tháng chưa bằng 0; sau normalized mới là zero. Xác định rõ bạn cần zero **theo trường** hay zero **sau quy đổi năm–tháng**.

### Lỗi 6 — Cho rằng 12 tháng tự bằng 1 năm trong equals

`Period.ofMonths(12).equals(Period.ofYears(1))` là false. Nếu nghiệp vụ muốn cùng khóa, canonicalize trước khi so/lưu.

### Lỗi 7 — Normalized biến 30 ngày thành 1 tháng

Không: `Period.normalized()` chỉ đổi năm/tháng, ngày giữ nguyên. Tháng có 28–31 ngày, không tự quy đổi ngày thành tháng.

### Lỗi 8 — Gọi Duration.normalized()

Method không tồn tại. Factory `Duration.ofSeconds(seconds,nanos)` đã duy trì cặp seconds/nano nội tại hợp lệ.

### Lỗi 9 — Dùng Period.ofDays(1) như đúng 24h elapsed

Qua DST có thể chỉ 23 hoặc tới 25 giờ thực. Lịch dùng Period, elapsed time/TTL dùng Duration.

### Lỗi 10 — Chỉ xem toTotalMonths rồi bỏ qua days

`Period.toTotalMonths()` không tính thành phần ngày. Period có total months = 0 vẫn có thể chứa số ngày khác 0.

### Lỗi 11 — Dùng Period để đo số giây khi không có ngày tham chiếu

Một tháng không có số giây cố định. Cần ngày/zone và hợp đồng nghiệp vụ cụ thể trước khi quy ra elapsed time.

### Lỗi 12 — Đảo start/end mà không để ý dấu

`Duration.between(start,end)` và `Period.between(start,end)` là phép có hướng. Viết test rõ với start sau end và start bằng end.

### Lỗi 13 — Không kiểm tra overflow

`Duration.toNanos()`, `Duration.negated()`/`abs()` và `Period.negated()` có thể ném `ArithmeticException` ở biên số. Kiểm soát miền input và xử lý lỗi phù hợp.

### Lỗi 14 — Dùng == để so value-based objects

`Duration` và `Period` là value-based. Dùng `equals`, `isZero` hoặc so trường đúng ngữ nghĩa, không dựa vào object identity.

### Lỗi 15 — Đổi Duration âm thành milliseconds nguyên quá sớm

Làm mất sub-millisecond precision có thể gây gộp âm/dương/zero thành cùng giá trị 0. Kiểm tra ý nghĩa trước khi hạ độ phân giải.

### Lỗi 16 — Đặt giá trị zero để biểu diễn “chưa có dữ liệu”

`Duration.ZERO` và `Period.ZERO` là dữ liệu hợp lệ. Dùng một trạng thái riêng hoặc `Optional` khi cần phân biệt không có phép đo.

### Lỗi 17 — Dùng dấu trong chuỗi thay cho parser

Chuỗi `P1Y-1M` có dấu âm dù không bắt đầu bằng dấu trừ. Parse bằng API và kiểm tra giá trị, không tự suy dấu từ một ký tự đầu.

### Lỗi 18 — Tin normalized() thay đổi object gốc

`Period.normalized()` trả giá trị mới. Gán/giữ kết quả nếu cần dùng dạng canonical; Period là immutable.

## 13. Checklist kiểm thử cần có

| Tình huống | Kiểm tra |
| --- | --- |
| Duration zero | `Duration.ZERO.isZero()` true, `isNegative()` false |
| Duration âm nguyên giây | `Duration.ofSeconds(-5).isNegative()` true |
| Duration -500ms | `getSeconds=-1` và `getNano=500000000` |
| Duration -1ns | `isNegative` true, `toMillis` zero |
| Factory nanos lệch dấu | `ofSeconds(1,-1e9)` ra zero |
| Duration between ngược | Hai hướng có dấu trái nhau nếu hai mốc khác nhau |
| abs/negated | Có hành vi đúng và xử lý overflow |
| Period.ZERO | Cả ba trường năm/tháng/ngày zero |
| Period âm ngày | `Period.ofDays(-3)` và `Period.between` ngược |
| Mixed sign | `Period.isNegative` true khi có một trường âm |
| Normalize 15 tháng | Thành `1Y3M`, ngày giữ nguyên |
| Normalize -13 tháng | Thành `-1Y-1M` |
| 1 năm -12 tháng | isZero trước/sau normalized khác nhau |
| Period equals | `P12M` khác `P1Y` trước normalization |
| Tổng tháng và ngày | `toTotalMonths` bỏ qua days |
| Parse text | `PT0S`, `P0D`, `-PT1H30M` |
| DST | +1 ngày lịch khác +24h thực ở một số mốc |
| Overflow | Test giới hạn long/int ở API có rủi ro |

### 13.1. Kiểm thử bất biến của Duration

Với một Duration `d` mà các phép tính không bị overflow:

~~~java
boolean reconstructed = d.equals(
        Duration.ofSeconds(d.getSeconds(), d.getNano()));

boolean zeroMatches = d.isZero()
        == (d.compareTo(Duration.ZERO) == 0);

boolean signMatches = d.isNegative()
        == (d.compareTo(Duration.ZERO) < 0);
~~~

Đây là **biểu thức kiểm thử minh họa trong một method**, không phải chương trình độc lập. Chúng kiểm chứng representation đã chuẩn hóa và tương quan giữa zero/sign/compareTo.

### 13.2. Kiểm thử bất biến của Period.normalized

~~~java
Period normalized = p.normalized();

boolean monthsPreserved =
        normalized.toTotalMonths() == p.toTotalMonths();

boolean daysPreserved =
        normalized.getDays() == p.getDays();

boolean idempotent =
        normalized.normalized().equals(normalized);
~~~

Đây là **đoạn minh họa** với `p` là Period đã có và không overflow. Những tính chất này xác nhận việc normalized **chỉ đổi cách biểu diễn năm–tháng, không làm mất ngày**.

### 13.3. Các trường hợp biên có giá trị cao

- Period có năm dương, tháng âm.
- Period có năm âm, tháng dương.
- Period có tháng âm và ngày dương.
- Tổng tháng bằng 0 dù các trường không bằng 0.
- Giá trị `Integer.MIN_VALUE` khi negated.
- Giá trị `Long.MIN_VALUE` khi negated Duration.
- Duration âm nhỏ hơn 1 ms.
- Mốc LocalDate gần cuối tháng hoặc ngày nhuận.
- ZonedDateTime tại khoảng chuyển DST.
- Dữ liệu âm đọc từ hệ thống ngoài Java với cách biểu diễn cặp seconds/nanos khác convention.

## 14. Bài tập và đáp án

**Câu 1.** `Duration.ofMillis(-500).getSeconds()` và `getNano()` bằng bao nhiêu?

**Đáp án:** `-1` và `500000000`, tổng -0,5 giây.

**Câu 2.** `Duration.ofNanos(-1).toMillis()` trả gì? Có phải Duration zero không?

**Đáp án:** Trả 0 nhưng Duration vẫn âm, không phải zero. Chênh lệch nhỏ hơn 1 ms bị mất khi đổi sang millis nguyên.

**Câu 3.** `Duration.ofSeconds(1,-1_000_000_000L).isZero()` thế nào?

**Đáp án:** True; 1 giây trừ một tỷ nanosecond bằng 0.

**Câu 4.** `Period.of(1,-12,0).isZero()` là true hay false?

**Đáp án:** False. Sau `normalized()`, kết quả là `P0D` với `isZero()==true`.

**Câu 5.** Vì sao `Period.of(1,-1,0).isNegative()` true nhưng `normalized().isNegative()` false?

**Đáp án:** Vì bản gốc có trường tháng âm. Sau normalize, 1 năm - 1 tháng thành 11 tháng dương.

**Câu 6.** `Period.ofMonths(-13).normalized()` cho gì?

**Đáp án:** `P-1Y-1M`.

**Câu 7.** `Period.of(0,15,2).normalized()` có đổi 2 ngày không?

**Đáp án:** Không, `P1Y3M2D`; chỉ năm/tháng được chuẩn hóa.

**Câu 8.** `Period.ofMonths(12).equals(Period.ofYears(1))` đúng không?

**Đáp án:** Không. Equals so các trường riêng; normalized 12 tháng mới bằng 1 năm theo equals.

**Câu 9.** Khi nào `Duration.ofDays(1)` phù hợp hơn `Period.ofDays(1)`?

**Đáp án:** Khi cần đúng 24 giờ elapsed. Với một ngày lịch theo zone, Period hoặc thao tác lịch phù hợp hơn.

**Câu 10.** `Period.toTotalMonths()==0` đủ kết luận Period zero chưa?

**Đáp án:** Chưa, vì còn trường ngày, và các trường năm/tháng chưa chắc đều zero nếu chưa normalize.

**Câu 11.** Nên dùng `Duration.ZERO == Duration.ofSeconds(0)` để so giá trị không?

**Đáp án:** Không. Dùng `equals` hoặc `isZero`; không dựa vào identity của value-based class.

**Câu 12.** Tại sao không thể luôn quy `Period.ofMonths(1)` thành một số giây cố định?

**Đáp án:** Tháng có số ngày khác nhau, lại có thể đi qua DST nếu gắn vùng. Cần ngày mốc và zone khi cần elapsed time.

**Câu 13.** `Duration.abs()` có nên tự động áp dụng khi thời hạn âm không?

**Đáp án:** Không. Âm có thể là đã quá hạn, dùng abs sẽ mất hướng thời gian.

**Câu 14.** `Duration.toNanos()` có luôn chạy thành công không?

**Đáp án:** Không. Duration rất lớn có thể vượt miền long nanoseconds và ném ArithmeticException.

**Câu 15.** Nếu cần nhận diện một Period bị trừ lùi ba ngày, dùng gì?

**Đáp án:** Có thể dùng `Period.ofDays(-3)` hoặc `Period.between(endLater,startEarlier)` với thứ tự mốc phù hợp; kiểm tra các trường/`isNegative` đúng ngữ nghĩa.

## 15. Tổng kết

- **Duration âm:** Tổng thời lượng âm, nhưng `getNano()` luôn không âm; `-0,5s` được biểu diễn bằng `-1s + 500 triệu ns`.
- **Duration zero:** `Duration.ZERO` và `isZero()` hỏi giá trị zero thật; `toMillis()==0` có thể chỉ là mất precision.
- **Duration không có normalized():** Factory và arithmetic giữ cặp giây–nano hợp lệ.
- **Period âm:** `isNegative()` trả true nếu **bất kỳ năm/tháng/ngày âm**, không phải phép so elapsed time hay tổng tháng duy nhất.
- **Period zero:** `isZero()` kiểm tra từng trường hiện tại. Một Period có thành phần năm/tháng triệt tiêu có thể chỉ thành zero **sau khi normalized()`.
- **Period.normalized():** Chuyển tháng dư thành năm theo 12 tháng/năm, giữ nguyên ngày; không đổi 30 ngày thành một tháng.
- **Equality:** `P12M` và `P1Y` khác nhau trước canonicalization theo `equals`, dù cùng totalMonths.
- **Lịch và timeline:** `Period.ofDays(1)` là một ngày lịch, `Duration.ofDays(1)` là 24h chuẩn; qua DST có thể khác.
- **Nghiệp vụ:** Xác định ý nghĩa dấu âm, zero, normalization rồi mới xử lý timeout, deadline, lịch, serialization và tests.
- Những API này **vẫn áp dụng trong Java hiện đại**; mã minh họa chính tương thích Java 8.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 8 — Duration](https://docs.oracle.com/javase/8/docs/api/java/time/Duration.html)
- [Oracle Java SE 26 — Duration](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html)
- [Oracle Java SE 8 — Period](https://docs.oracle.com/javase/8/docs/api/java/time/Period.html)
- [Oracle Java SE 26 — Period](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Period.html)
- [Oracle Java SE 8 — Instant](https://docs.oracle.com/javase/8/docs/api/java/time/Instant.html)
- [Oracle Java SE 8 — LocalDate](https://docs.oracle.com/javase/8/docs/api/java/time/LocalDate.html)
- [Oracle Java SE 8 — ZonedDateTime](https://docs.oracle.com/javase/8/docs/api/java/time/ZonedDateTime.html)
