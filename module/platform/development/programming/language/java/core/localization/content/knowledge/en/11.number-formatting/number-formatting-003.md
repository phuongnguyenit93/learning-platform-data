# CompactNumberFormat với dạng ngắn hoặc dài trong Java

## 1. Khi nào cần định dạng số rút gọn?

Trong giao diện có diện tích hạn chế như thẻ thống kê, dashboard, biểu đồ, ứng dụng di động hoặc danh sách lượt xem, hiển thị toàn bộ số lớn đôi khi gây khó đọc. Thay vì hiển thị `1,000` hoặc `1,000,000`, người dùng tiếng Anh ở Hoa Kỳ thường dễ nhận ra dạng `1K` hoặc `1M`. Với văn bản có nhiều chỗ trống hơn, dạng đầy đủ như `1 thousand` hoặc `1 million` có thể tự nhiên hơn.

Java cung cấp cơ chế **compact number formatting** qua `java.text.CompactNumberFormat`, một lớp con cụ thể của `NumberFormat` được đưa vào từ **Java 12** và sử dụng được trong **Java 17+**.

Khác với việc tự viết `if (value >= 1000) value / 1000 + "K"`, compact formatter dùng **các pattern đặc thù cho locale**. Cùng một độ lớn, ngôn ngữ và khu vực khác nhau có thể có từ ngữ, đơn vị viết tắt, ngưỡng và quy tắc số nhiều khác nhau.

Bài này tập trung vào:

- Phân biệt hai kiểu `NumberFormat.Style.SHORT` và `NumberFormat.Style.LONG`.
- Tạo formatter đúng bằng `NumberFormat.getCompactNumberInstance(locale, style)`.
- Hiểu ngưỡng rút gọn, chữ số thập phân, rounding, dấu và khả năng phụ thuộc locale.
- Phân biệt **chuỗi trình bày** với **giá trị số gốc**; lưu ý khi parse compact text.
- Chọn cách dùng phù hợp trong UI, xác định các lỗi thường gặp và cách kiểm thử.

## 2. SHORT và LONG khác nhau thế nào?

Java hỗ trợ hai style trong `NumberFormat.Style`:

| Style | Mục tiêu | Ví dụ theo `Locale.US` | Phù hợp |
| --- | --- | --- | --- |
| `SHORT` | Ký hiệu ngắn, chiếm ít không gian | `10000 → 10K` | KPI, nhãn biểu đồ, badge, card |
| `LONG` | Cụm từ ngắn gọn bằng chữ | `10000 → 10 thousand` | Mô tả thống kê, báo cáo, văn bản |
| `NumberFormat.getNumberInstance(locale)` | Không phải compact: số thông thường | `10000 → 10,000` với `Locale.US` | Bảng số liệu chi tiết, dữ liệu cần độ chính xác hiển thị |

Dạng dài (`LONG`) **không** có nghĩa là in từng chữ số hoặc viết toàn bộ số bằng từ (“ten thousand”); nó là *compact long form* theo mẫu của locale. Tại Hoa Kỳ, `10 thousand` vẫn có phần số `10`, chỉ có phần đơn vị được viết dài hơn `10K`.

Dạng ngắn (`SHORT`) cũng **không nhất thiết** chỉ có ký tự K/M/B; mỗi locale có các ký hiệu và cách viết riêng. Hậu tố, tiền tố, dấu cách, chữ viết và dạng số nhiều đều do dữ liệu bản địa hóa quyết định. `1K` là ví dụ tiếng Anh tại Hoa Kỳ, không phải một quy tắc bắt buộc cho tiếng Việt, tiếng Hindi hay mọi ngôn ngữ khác.

### Hai thứ cần phân biệt

1. **Style**: người dùng muốn bản rút gọn dạng ký hiệu ngắn hay cụm từ dài?
2. **Locale**: dạng ký hiệu và cấu trúc của đơn vị sẽ theo ngôn ngữ/khu vực nào?

Hai tham số này độc lập. Muốn hiển thị cho người dùng `vi-VN`, truyền `Locale.forLanguageTag("vi-VN")`, không tự gắn `K` hoặc `M` vào số. Khi định dạng cho `en-US`, sử dụng `Locale.US`.

## 3. API Java 17 cơ bản

Phương thức factory chuẩn:

```java
NumberFormat shortFormat = NumberFormat.getCompactNumberInstance(
        Locale.US, NumberFormat.Style.SHORT);

NumberFormat longFormat = NumberFormat.getCompactNumberInstance(
        Locale.US, NumberFormat.Style.LONG);
```

Hai biến có kiểu `NumberFormat` (API factory trả về kiểu này). Với triển khai chuẩn, formatter compact thuộc lớp `CompactNumberFormat`, nhưng code chỉ dùng `format` và các option cơ bản thì có thể giữ kiểu `NumberFormat` để hạn chế phụ thuộc triển khai.

Có thêm overload:

```java
NumberFormat defaultShort = NumberFormat.getCompactNumberInstance();
```

Overload không tham số dùng **locale mặc định của category `Locale.Category.FORMAT`** và style `SHORT`. Trong ứng dụng server phục vụ nhiều người dùng, thường nên dùng overload **có locale và style tường minh**; nếu không, kết quả có thể phụ thuộc cấu hình JVM của máy triển khai.

`Locale` không tự chọn múi giờ, loại tiền hoặc đơn vị đo; `CompactNumberFormat` chỉ format một giá trị số. Nếu đầu vào là 1.000.000 lượt xem, ký hiệu M mang ý nghĩa **một triệu theo pattern**; đây không phải cơ chế quy đổi tiền, độ dài hay tỷ giá.

### Ví dụ độc lập 1 — cùng số, hai style

Lưu vào tệp `CompactStylesDemo.java`:

```java
import java.text.NumberFormat;
import java.util.Locale;

public class CompactStylesDemo {
    public static void main(String[] args) {
        long count = 10_000L;

        NumberFormat shortFormat = NumberFormat.getCompactNumberInstance(
                Locale.US, NumberFormat.Style.SHORT);

        NumberFormat longFormat = NumberFormat.getCompactNumberInstance(
                Locale.US, NumberFormat.Style.LONG);

        System.out.println("original=" + count);
        System.out.println("short=" + shortFormat.format(count));
        System.out.println("long=" + longFormat.format(count));
    }
}
```

Dùng JDK 17 trở lên, lưu tệp UTF-8 và chạy:

```bash
javac -encoding UTF-8 CompactStylesDemo.java
java CompactStylesDemo
```

Với dữ liệu compact chuẩn cho `Locale.US`, stdout:

```text
original=10000
short=10K
long=10 thousand
```

Điểm cần quan sát: biến `count` giữ nguyên 10.000. Cả `10K` và `10 thousand` chỉ là **hai chuỗi biểu diễn** do formatter tạo ra, không phải hai giá trị nghiệp vụ khác nhau. Ví dụ `10K` và `10 thousand` là các ví dụ cụ thể trong tài liệu `CompactNumberFormat` của Java 17; khi kiểm thử nhiều locale/provider khác, không nên giả định mọi chuỗi compact giống `Locale.US`.

## 4. Ngưỡng rút gọn đến từ compact number patterns

`CompactNumberFormat` dùng dãy **compact number patterns** theo dữ liệu locale, dựa trên chuẩn Unicode LDML (Locale Data Markup Language).

Với `Locale.US` và style `SHORT`, ví dụ các pattern có thể bao gồm:

```text
0       → dạng số thường khi chưa có mẫu compact
0K      → 1K (ví dụ 1000)
00K     → 10K (ví dụ 10000)
000K    → 100K (ví dụ 100000)
0M      → 1M (ví dụ 1000000)
...
```

Các chữ số `0` trong pattern biểu diễn số lượng chữ số tối thiểu của phần số ở độ lớn tương ứng. `K`, `M` ở đây là **hậu tố của mẫu**, không phải ký tự được thêm bằng phép nối chuỗi ngẫu nhiên.

Một số điểm quan trọng:

- Mỗi locale có thể có **một hệ ngưỡng/đơn vị khác nhau**. Không viết thuật toán riêng chia cho 1.000 ở mọi locale.
- Không phải giá trị nào cũng phải rút gọn. Nhiều locale dùng pattern số thông thường cho các bậc nhỏ hơn một ngưỡng nhất định, ví dụ `42` vẫn hiển thị là `42`.
- Nếu một bậc không có compact pattern thì formatter có thể dùng **dạng số thông thường** được bản địa hóa, thay vì tự chọn hậu tố của ngôn ngữ khác.
- Số âm dùng pattern âm nếu locale cung cấp, hoặc áp dụng quy tắc dấu âm mặc định. Đừng tự thêm ký tự `-` khi UI đã dùng formatter.
- Dạng dài có thể chứa **quy tắc số nhiều**: cùng một đơn vị có dạng singular/plural khác nhau tùy số lượng và ngôn ngữ.

Do đó, không thể biến mọi locale thành một bảng toàn cục như “từ 1.000 là K; từ 1.000.000 là M”. Chuỗi output phụ thuộc dữ liệu locale cung cấp bởi runtime/`NumberFormatProvider`.

### Điều gì xảy ra ở gần ngưỡng?

Ví dụ một số gần một triệu có thể được làm tròn khi chỉ hiện 0 chữ số thập phân. Formatter phải phối hợp **chọn pattern** và **làm tròn**; kết quả có thể đổi ký hiệu compact khi giá trị ở sát bậc tiếp theo. Không cố tự đoán kết quả bằng cách so sánh `number >= 1_000_000` rồi nối `M`, nhất là khi có precision khác 0.

Khi sản phẩm cần một chính sách ngưỡng rút gọn được cố định tuyệt đối giữa các nền tảng, hãy định nghĩa/kiểm thử contract hiển thị riêng. Compact number formatting theo locale là **cơ chế hiển thị**, không phải luật tính toán hoặc phân loại nghiệp vụ.

## 5. Hiển thị chữ số thập phân và làm tròn

Theo mặc định, `CompactNumberFormat` thường **không hiển thị phần thập phân**. Ví dụ `1000` trong `Locale.US` với style `SHORT` hiển thị `1K`, không phải `1.00K`.

Một giá trị như 1.200 có thể chỉ được hiển thị là `1K` ở mặc định; đó là biểu diễn đã được rút gọn và làm tròn. Nếu người dùng cần phân biệt 1.200 với 1.000, có thể tăng số chữ số thập phân:

```java
NumberFormat shortFormat = NumberFormat.getCompactNumberInstance(
        Locale.US, NumberFormat.Style.SHORT);

shortFormat.setMinimumFractionDigits(1);
shortFormat.setMaximumFractionDigits(1);
```

Với cấu hình trên, ví dụ điển hình `1200 → 1.2K`. Một số tùy chọn:

| API | Mục đích |
| --- | --- |
| `setMinimumFractionDigits(n)` | Số chữ số thập phân hiển thị tối thiểu |
| `setMaximumFractionDigits(n)` | Số chữ số thập phân tối đa; có thể làm tròn |
| `setRoundingMode(RoundingMode)` | Chính sách làm tròn |
| `setGroupingUsed(boolean)` | Cho phép hoặc không dùng dấu nhóm số trong biểu diễn |
| `setMinimumIntegerDigits(n)` / `setMaximumIntegerDigits(n)` | Điều chỉnh phần nguyên theo tính năng formatter |

Khi đặt `minimumFractionDigits` lớn hơn `maximumFractionDigits` hiện tại (hoặc ngược lại), `NumberFormat` có quy tắc điều chỉnh giá trị liên quan để bảo đảm `minimum <= maximum`. Để tránh bất ngờ, sau khi cấu hình có thể kiểm tra `getMinimumFractionDigits()` và `getMaximumFractionDigits()`.

### Ví dụ độc lập 2 — thay độ chính xác hiển thị

Tệp `CompactPrecisionDemo.java`:

```java
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.util.Locale;

public class CompactPrecisionDemo {
    public static void main(String[] args) {
        NumberFormat compact = NumberFormat.getCompactNumberInstance(
                Locale.US, NumberFormat.Style.SHORT);

        long value = 1_200L;
        System.out.println("original=" + value);
        System.out.println("default=" + compact.format(value));

        compact.setMinimumFractionDigits(1);
        compact.setMaximumFractionDigits(1);
        compact.setRoundingMode(RoundingMode.HALF_UP);

        System.out.println("one-decimal=" + compact.format(value));
        System.out.println("still-original=" + value);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 CompactPrecisionDemo.java
java CompactPrecisionDemo
```

Với pattern `Locale.US` chuẩn, stdout:

```text
original=1200
default=1K
one-decimal=1.2K
still-original=1200
```

`setMinimumFractionDigits(1)` yêu cầu phần thập phân hiển thị có ít nhất một chữ số; `setMaximumFractionDigits(1)` giới hạn ở một chữ số. `RoundingMode.HALF_UP` chỉ thay đổi **cách làm tròn để hiển thị**; nó không chỉnh giá trị gốc trong biến `value`.

**RoundingMode mặc định:** Theo tài liệu Java 17, compact formatter dùng `RoundingMode.HALF_EVEN` làm mặc định cho format. Có thể thay bằng `HALF_UP`, `DOWN` hoặc giá trị khác nếu phù hợp UI. Không dùng mode được chọn cho UI thay thế chính sách làm tròn ở tầng nghiệp vụ.

### Mất thông tin sau khi compact

`1.2K` có thể làm người xem hiểu xấp xỉ 1.200; với số chữ số thập phân hạn chế, nhiều giá trị gốc có thể cho **cùng một output**. Vì vậy không đưa chuỗi compact làm nguồn cho phép tính, xác định hạn mức hoặc lưu trữ giá trị gốc.

Đặc biệt trong sản phẩm tài chính, định lượng chính xác nên hiển thị bằng format tiền/số thích hợp khi ra quyết định; compact formatting chỉ có thể là **thống kê tóm tắt**, và cần cân nhắc nhãn/tooltip cho biết giá trị thật.

## 6. Cùng một số qua nhiều locale

Ví dụ, người dùng muốn xem số lượt theo `en-US`, `vi-VN` và `fr-FR`. Có thể tạo formatter tương ứng:

```java
Locale en = Locale.forLanguageTag("en-US");
Locale vi = Locale.forLanguageTag("vi-VN");
Locale fr = Locale.forLanguageTag("fr-FR");

NumberFormat shortEn = NumberFormat.getCompactNumberInstance(
        en, NumberFormat.Style.SHORT);
NumberFormat shortVi = NumberFormat.getCompactNumberInstance(
        vi, NumberFormat.Style.SHORT);
NumberFormat longFr = NumberFormat.getCompactNumberInstance(
        fr, NumberFormat.Style.LONG);
```

Đây là **đoạn mã minh họa trong một phương thức** với import `java.text.NumberFormat` và `java.util.Locale`. Không phải chương trình Java độc lập.

**Tại sao không liệt kê stdout tuyệt đối cho tất cả locale?** Dữ liệu ngôn ngữ (CLDR) và locale provider có thể thay đổi theo phiên bản JDK, cấu hình `java.locale.providers`, môi trường và các provider được cài đặt. Dạng tiếng Việt có thể dùng từ/cụm từ ngắn khác tiếng Anh; tiếng Pháp có thể sử dụng dấu cách không ngắt dòng (NBSP hoặc narrow NBSP). So sánh chuỗi nguyên văn giữa các runtime mà không kiểm soát môi trường dễ làm test thất bại giả.

Một chương trình runnable để quan sát:

Tệp `CompactLocalesDemo.java`:

```java
import java.text.NumberFormat;
import java.util.Locale;

public class CompactLocalesDemo {
    public static void main(String[] args) {
        long count = 1_500_000L;

        for (String tag : new String[]{"en-US", "vi-VN", "fr-FR"}) {
            Locale locale = Locale.forLanguageTag(tag);

            NumberFormat shortFormat =
                    NumberFormat.getCompactNumberInstance(
                            locale, NumberFormat.Style.SHORT);

            NumberFormat longFormat =
                    NumberFormat.getCompactNumberInstance(
                            locale, NumberFormat.Style.LONG);

            System.out.println(tag
                    + " | SHORT=" + shortFormat.format(count)
                    + " | LONG=" + longFormat.format(count));
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CompactLocalesDemo.java
java CompactLocalesDemo
```

Chương trình in **ba dòng**, theo thứ tự `en-US`, `vi-VN`, `fr-FR`, mỗi dòng có cả hai style cho cùng `count=1500000`. Nội dung hậu tố và dấu cách phụ thuộc locale data của JDK, nên hãy quan sát trên môi trường chạy thay vì giả định chuỗi duy nhất cho mọi máy.

Những kiểm tra đáng làm:

- `format(1_500_000L)` của `SHORT` và `LONG` có thể khác độ dài/ngữ nghĩa biểu thức, nhưng cả hai cùng mô tả giá trị đếm 1.500.000.
- Dấu phân cách thập phân và từ chỉ bậc thay đổi theo locale.
- Giá trị `count` không biến đổi, và ứng dụng không tự đổi locale hệ thống để format theo từng người.

**Thói quen tốt:** truyền `Locale` theo ngữ cảnh người dùng; không gọi `Locale.setDefault(...)` để điều khiển từng request vì default là trạng thái toàn JVM.

## 7. Lựa chọn giữa compact và number format thông thường

Một vài mục tiêu hiển thị khác nhau:

| Ngữ cảnh | Gợi ý | Lý do |
| --- | --- | --- |
| Card “lượt xem” nhỏ | `SHORT` | Ít ký tự, vẫn dễ quét |
| Dòng mô tả báo cáo | `LONG` | Diễn đạt đơn vị quy mô bằng chữ |
| Bảng kế toán, thanh toán | `getNumberInstance` hoặc formatter tiền có kiểm soát | Cần xem con số đầy đủ |
| API JSON gửi cho frontend | Gửi giá trị số chuẩn + metadata | Frontend format theo locale, không phụ thuộc chuỗi đã rút gọn |
| Tooltip của biểu đồ | Có thể hiện cả compact và số đầy đủ | Giảm việc người đọc nhầm số đã làm tròn |
| Số lượng nhỏ | Formatter có thể giữ dạng thường | Không cố dùng hậu tố sai ngữ cảnh |

Ví dụ số lượt xem `1_234_567` có thể hiển thị compact trên card, nhưng khi người dùng xem chi tiết nên cung cấp `1,234,567` theo `Locale.US` hoặc cách phân nhóm của locale tương ứng.

**Một điểm thường nhầm:** `CompactNumberFormat` định dạng **quy mô số**, không phải “dạng tiền ngắn”. Không gọi `getCompactNumberInstance` rồi tự suy ra loại tiền từ locale. Nếu muốn tạo chuỗi “$1.2M”, bạn phải cân nhắc loại tiền, ký hiệu, độ chính xác và policy nghiệp vụ riêng; nối ký hiệu tiền thô có thể sai vị trí/khoảng trắng ở nhiều locale. Bản compact của `1_200_000` không thay đổi đơn vị tiền và không chuyển tỷ giá.

## 8. Phân tích chuỗi compact trở lại số: có thể nhưng cần thận trọng

`CompactNumberFormat` hỗ trợ `parse(...)`, không chỉ `format(...)`. Với `Locale.US`, ví dụ `"1K"` có thể parse thành 1000, `"12K"` thành 12000. Lúc parse, formatter nhận biết hậu tố compact rồi nhân phần số với hệ số của hậu tố theo pattern locale.

Tuy nhiên, **format rồi parse không bảo đảm tái lập giá trị ban đầu**:

- `format(1234)` với 0 chữ số thập phân có thể thành `1K`, parse ngược lại cho 1000, đã mất 234.
- Một text như `1M` mang ý nghĩa phụ thuộc pattern của locale; parse theo sai locale có thể không nhận dạng đúng.
- Parser có thể **tiêu thụ một phần** chuỗi rồi dừng; không mặc nhiên xác nhận toàn bộ input hợp lệ.
- Mặc định parse có thể trả `Long` hoặc `Double`; kết quả và kiểu còn tùy giá trị và cấu hình. `CompactNumberFormat` có `setParseBigDecimal(true)` để ưu tiên `BigDecimal`, ngoại trừ các giá trị đặc biệt như NaN/vô cực.
- `isParseIntegerOnly` và `setGroupingUsed` ảnh hưởng parsing; đừng đoán parser luôn chấp nhận dấu nhóm số. Theo tài liệu `CompactNumberFormat`, parsing mặc định **không cho phép dấu nhóm số** cho đến khi bật grouping bằng `setGroupingUsed(true)`.

### Ví dụ độc lập 3 — parse và kiểm tra toàn bộ input

Tệp `CompactParseDemo.java`:

```java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class CompactParseDemo {
    public static void main(String[] args) {
        NumberFormat format = NumberFormat.getCompactNumberInstance(
                Locale.US, NumberFormat.Style.SHORT);

        String input = "12K";
        ParsePosition position = new ParsePosition(0);
        Number parsed = format.parse(input, position);

        if (parsed == null || position.getIndex() != input.length()) {
            throw new IllegalArgumentException("Invalid compact input");
        }

        System.out.println("input=" + input);
        System.out.println("value=" + parsed.longValue());
        System.out.println("consumed=" + position.getIndex());
    }
}
```

Chạy bằng Java 17+:

```bash
javac -encoding UTF-8 CompactParseDemo.java
java CompactParseDemo
```

Với `Locale.US`, stdout:

```text
input=12K
value=12000
consumed=3
```

`ParsePosition` cho biết số ký tự parser đã tiêu thụ; điều kiện `position.getIndex() == input.length()` giúp bắt trường hợp còn text thừa. **Đó chưa phải validation nghiêm ngặt hoàn chỉnh**: ngoài việc tiêu thụ hết, cần quy định locale, kiểu dữ liệu cho phép, độ lớn, phần thập phân, format input mong đợi và các giới hạn nghiệp vụ.

Trong hệ thống cần nhận số chính xác (ví dụ tiền, đơn hàng, lượng tồn kho), thông thường nên thiết kế form/API nhận **số không rút gọn** với contract rõ ràng; giữ compact text cho chiều **xuất ra giao diện**. Dùng số compact làm input chính chỉ khi sản phẩm thực sự chấp nhận cách nhập này và có test parser theo locale.

### ParseBigDecimal: khi nào cần?

`NumberFormat.getCompactNumberInstance(...)` trả về `NumberFormat`, nhưng triển khai chuẩn thường là `CompactNumberFormat`. Khi cần method riêng của lớp con, kiểm tra kiểu trước khi cast:

```java
NumberFormat formatter = NumberFormat.getCompactNumberInstance(
        Locale.US, NumberFormat.Style.SHORT);

if (formatter instanceof java.text.CompactNumberFormat compact) {
    compact.setParseBigDecimal(true);
}
```

Đây là đoạn minh họa **trong method** trên Java 17. `instanceof` pattern matching là tính năng ngôn ngữ chính thức từ Java 16. Khi cần chính xác thập phân, sau khi parse vẫn phải kiểm tra kiểu thực tế, hợp đồng và giới hạn; không ép mọi `Number` thành `longValue()` vì có thể làm mất thập phân hoặc tràn giá trị.

## 9. Khả năng làm tròn, âm, lớn và dữ liệu đặc biệt

### 9.1. Âm và dấu

Ví dụ `-1200` ở dạng compact có thể nhận dấu âm cùng hậu tố bậc. Cách viết dấu (tiền tố/hậu tố, ký tự) được quy định bởi pattern locale. Không tự cắt dấu âm, chia số rồi nối hậu tố vì dễ tạo chuỗi sai ngữ pháp hoặc sai vị trí dấu.

### 9.2. Các số rất lớn

Compact patterns có thể được khai báo theo dãy bậc. Với độ lớn vượt phạm vi mẫu được provider hỗ trợ, không nên giả định luôn có hậu tố mới như “P”, “E” theo cùng quy tắc. Chọn format thông thường hoặc biểu diễn khoa học khi nghiệp vụ cần; kiểm tra output với số thực tế có thể gặp.

### 9.3. NaN và Infinity

Khi đầu vào là `Double.NaN` hoặc `Double.POSITIVE_INFINITY`, biểu diễn có thể dùng ký hiệu bản địa hóa thay vì hậu tố compact như số thường. Nếu sản phẩm chỉ chấp nhận số hữu hạn, **validate trước khi format**. Không hiển thị NaN hay vô cực như số lượng hợp lệ.

### 9.4. Số thập phân và BigDecimal

`NumberFormat` có overload `format(long)`, `format(double)` và `format(Object)`. `BigDecimal` có thể được đưa vào API format dạng object. Nhưng độ chính xác hiển thị bị giới hạn bởi số chữ số đã chọn. Khi làm tính toán tiền, dùng `BigDecimal` và chính sách làm tròn nghiệp vụ độc lập, không parse lại string compact để lấy giá trị.

### 9.5. Dùng format làm logic so sánh

Không dùng:

```java
if (compact.format(a).equals(compact.format(b))) {
    // KHÔNG kết luận a và b bằng nhau.
}
```

Đây là **đoạn minh họa**, không phải ví dụ chạy độc lập. Vì kết quả có thể đã làm tròn, hai giá trị khác nhau có thể có chuỗi giống nhau. Hãy so sánh chính giá trị `a`, `b` ở kiểu nghiệp vụ thích hợp.

## 10. Định dạng theo locale và khả năng thay đổi giữa các JDK

Dữ liệu compact đến từ locale data và các provider theo cấu hình môi trường. Các yếu tố có thể tác động kết quả:

- Phiên bản JDK và phiên bản dữ liệu CLDR đi kèm.
- `Locale` được yêu cầu, đặc biệt language/region/script.
- `NumberFormat.Style.SHORT` hay `LONG`.
- `minimumFractionDigits`, `maximumFractionDigits`, `RoundingMode` và các cài đặt formatter khác.
- Các `NumberFormatProvider` được cài và cấu hình `java.locale.providers` (nếu áp dụng).
- Bộ pattern locale có quy tắc số nhiều hoặc khác ngưỡng.

Vì vậy, test UI theo locale cần **chọn đúng mức độ cam kết**:

1. Test logic luôn truyền locale tường minh, style tường minh và không sửa giá trị gốc.
2. Với môi trường JDK/CLDR được pin, có thể snapshot chuỗi chính xác của các locale được hỗ trợ.
3. Nếu chạy trên nhiều vendor/JDK khác nhau, test nên kiểm tra tính hợp lệ và ngữ nghĩa, hoặc cho phép biến thể được chấp nhận.
4. Đặc biệt kiểm tra dấu cách Unicode, ký tự phân cách, các giá trị âm và số gần ngưỡng.
5. Đối với screen reader/accessibility, kiểm tra thông báo dễ hiểu; một số ký hiệu siêu ngắn có thể cần nhãn mô tả đầy đủ.

**Không ép kiểu sang `CompactNumberFormat` mà không kiểm tra** nếu có khả năng dùng provider thay thế; factory khai báo trả về `NumberFormat` và nhà cung cấp dịch vụ có thể ảnh hưởng triển khai thực tế.

## 11. Thread safety và cách dùng trên server

`NumberFormat` và `CompactNumberFormat` là formatter **mutable**. Các lời gọi `setMaximumFractionDigits`, `setRoundingMode` hoặc cấu hình khác có thể thay đổi trạng thái của đối tượng. API `NumberFormat` không bảo đảm an toàn khi các luồng cùng format/parse bằng một instance mà không đồng bộ.

Một mẫu sử dụng đơn giản trong server:

```java
import java.text.NumberFormat;
import java.util.Locale;

public final class ViewCountFormatter {
    private ViewCountFormatter() {}

    public static String compactViewCount(long count, Locale locale) {
        NumberFormat fmt = NumberFormat.getCompactNumberInstance(
                locale, NumberFormat.Style.SHORT);
        fmt.setMaximumFractionDigits(1);
        return fmt.format(count);
    }
}
```

Đây là **lớp tiện ích có thể biên dịch** nhưng không có `main`, để ứng dụng khác gọi. Mỗi lời gọi tạo formatter riêng nên không chia sẻ instance mutable giữa các request; nếu sau này tối ưu cache, phải thiết kế đồng bộ, clone hoặc scope an toàn và có benchmark xác nhận.

Không gọi `Locale.setDefault(locale)` cho từng người dùng vì đó là state toàn JVM. Truyền `Locale` từ request/context vào formatter, giống ví dụ trên.

## 12. Kiểm thử và bài tập

### 12.1. Các ca kiểm thử có giá trị

| Tình huống | Kết quả mong đợi/tiêu chí |
| --- | --- |
| `10000` ở `Locale.US` | `SHORT = 10K` và `LONG = 10 thousand` theo dữ liệu chuẩn |
| `1200` mặc định so với 1 chữ số thập phân | Chuỗi compact đổi độ chi tiết; giá trị `1200` không đổi |
| Các số `99`, `999` và `1000` | Kiểm tra đúng ngưỡng dùng compact theo locale |
| `999_500` và `1_000_000` | Kiểm tra tác động của rounding và đổi bậc |
| Số âm | Dấu và hậu tố phù hợp với locale |
| `en-US`, `vi-VN`, `fr-FR` | Mỗi locale dùng pattern đúng và không phụ thuộc JVM default |
| `12K` parse ở `Locale.US` | Giá trị 12000; parser tiêu thụ toàn bộ input |
| `12Kxyz` | Phát hiện ký tự còn dư nếu cần input strict |
| Hai số khác nhau nhưng cùng chuỗi compact | Phép so sánh vẫn dựa số gốc |
| Truy cập từ nhiều request | Không chia sẻ formatter mutable sai cách |

### 12.2. Câu hỏi tự kiểm tra

**Câu 1.** `NumberFormat.Style.SHORT` và `LONG` có nhất thiết khác nhau bằng việc “viết tắt” và “viết toàn số thành chữ” không?

**Đáp án:** Không. `LONG` là dạng compact dài, ví dụ `10 thousand` tại `Locale.US`; phần `10` vẫn là chữ số.

**Câu 2.** Vì sao `1.2K` không nên lưu vào cơ sở dữ liệu thay cho `1200`?

**Đáp án:** Nó là chuỗi trình bày theo locale; có thể mất độ chính xác, không chắc parse được bằng locale khác và không phải contract số chính xác.

**Câu 3.** Nếu cần chính xác hơn mặc định, có thể cấu hình gì?

**Đáp án:** `setMinimumFractionDigits`, `setMaximumFractionDigits` và `setRoundingMode`. Tuy nhiên đây là chính sách **độ chính xác hiển thị**, không thay đổi số gốc.

**Câu 4.** Vì sao không viết `value / 1000 + "K"` cho tất cả người dùng?

**Đáp án:** Pattern của từng locale có thể khác tiền tố/hậu tố, bậc, dấu phân cách, cách viết và số nhiều. Cách nối tay áp đặt quy tắc tiếng Anh và có thể sai ở ngôn ngữ khác.

**Câu 5.** Parser nhận `"12K more"` và trả giá trị 12000. Có thể coi toàn bộ input hợp lệ không?

**Đáp án:** Không. Có thể parser chỉ đọc tiền tố `12K`. Phải kiểm tra `ParsePosition.getIndex()` với độ dài input và áp dụng validation thêm theo contract.

**Câu 6.** Trong ứng dụng nhiều người dùng, có nên tạo một `CompactNumberFormat` static duy nhất rồi thay locale mỗi request?

**Đáp án:** Không nên. Locale được truyền khi tạo formatter, còn formatter mutable không an toàn để sử dụng/sửa đồng thời mà không đồng bộ. Tạo formatter theo request hoặc quản lý cache/clone cẩn thận.

### 12.3. Thực hành

1. Chạy `CompactStylesDemo` với `10000`. Sau đó thử `1000`, `1000000` và `1000000000`; ghi nhận SHORT/LONG tại `Locale.US`.
2. Đổi `Locale.US` thành `Locale.forLanguageTag("vi-VN")` và thử cả hai style. Quan sát dấu, đơn vị và độ dài biểu thức; đừng mặc định hậu tố K/M giống tiếng Anh.
3. Chạy `CompactPrecisionDemo` với `1200`, rồi `1490` và `1500`. Quan sát tác động của maximum fraction digits và rounding mode ở các giá trị gần nhau.
4. Chạy `CompactParseDemo` với `"12K"` và `"12Kxyz"`. Bổ sung kiểm tra độ dài input và xác định cách thông báo lỗi rõ ràng.
5. Thiết kế thẻ KPI hiển thị compact, nhưng tooltip lấy số gốc qua `NumberFormat.getNumberInstance(locale)`; bảo đảm không có phép tính dựa vào text compact.

## 13. Ghi nhớ

- **`CompactNumberFormat` rút gọn biểu diễn của số theo locale**, hỗ trợ từ Java 12 và chạy trên Java 17+.
- **`SHORT`** ưu tiên ký hiệu ngắn như `10K`; **`LONG`** có thể dùng cụm từ như `10 thousand`.
- Dùng `NumberFormat.getCompactNumberInstance(locale, style)` và **truyền locale/style rõ ràng**.
- Mẫu, ngưỡng, dấu, số nhiều và cách viết phụ thuộc dữ liệu locale. Không tự thêm K/M cho mọi ngôn ngữ.
- Mặc định không có chữ số thập phân; cấu hình min/max fraction digits và rounding khi cần độ chi tiết khác.
- Compact formatting là **tầng hiển thị có thể làm tròn**, không phải dữ liệu chính xác để lưu, tính toán, chuyển tiền hay so sánh.
- Parse compact text cần đúng locale và kiểm tra tiêu thụ hết chuỗi; không dựa vào format–parse round trip để khôi phục số ban đầu.
- Không chia sẻ một instance `NumberFormat` mutable giữa các luồng mà thiếu cơ chế đồng bộ.

**Tài liệu chính thức Java 17:**

- [`CompactNumberFormat` — Oracle Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/CompactNumberFormat.html)
- [`NumberFormat` — Oracle Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html)
