# Số chữ số phần nguyên, phần lẻ và tác động làm tròn trong Java

Khi định dạng một số theo `Locale`, ta không chỉ chọn dấu phẩy hoặc dấu chấm. Ta còn quyết định **phần nguyên phải có ít nhất/tối đa bao nhiêu chữ số**, **phần thập phân được phép có bao nhiêu chữ số** và **làm tròn theo quy tắc nào**. Trong Java, `java.text.NumberFormat` cung cấp bốn cặp thuộc tính số chữ số; `java.text.DecimalFormat` bổ sung pattern, ký hiệu và cách điều khiển chi tiết.

Điều dễ nhầm nhất:

- **Số chữ số tối thiểu** thường **thêm số 0 để hiển thị đủ độ rộng**; nó không nhân/chia giá trị.
- **Số chữ số thập phân tối đa** có thể **làm tròn phần lẻ**.
- **Số chữ số phần nguyên tối đa**, đặc biệt với `DecimalFormat`, có thể **bỏ các chữ số hàng cao** khi hiển thị, chứ **không** làm tròn thành một số có ít chữ số hơn.
- **Chuỗi được format không phải số gốc**: việc thay đổi số chữ số hiển thị không làm thay đổi một `BigDecimal` hoặc `double` truyền vào; nhưng nếu lấy chuỗi đã định dạng làm dữ liệu tính toán, bạn có thể mất thông tin.

Bài học sử dụng **Java 17+**, `NumberFormat`, `DecimalFormat`, `BigDecimal` và `RoundingMode`, có ví dụ chạy độc lập, đầu ra kiểm chứng được và cảnh báo cho dữ liệu tài chính.

## 1. Phần nguyên và phần lẻ trong một con số

Với số thập phân biểu diễn theo quy ước tiếng Anh:

```text
               12345.6789
               ----- ----
               phần  phần
               nguyên lẻ

Sau định dạng theo en-US: 12,345.68
Sau định dạng theo de-DE: 12.345,68
```

Trong hai kết quả, **giá trị nguồn** có thể vẫn là `12345.6789`; dấu phân cách phần nghìn và dấu thập phân là **quy tắc trình bày** của locale, còn hai chữ số phần lẻ là do cấu hình giới hạn chữ số. Không nhầm ký tự dấu chấm trong một chuỗi giao diện với dấu thập phân của `BigDecimal` hoặc literal số Java.

Các API quan trọng:

| Thuộc tính | Getter | Setter | Tác động khi định dạng |
| --- | --- | --- | --- |
| Số chữ số phần nguyên **tối thiểu** | `getMinimumIntegerDigits()` | `setMinimumIntegerDigits(int)` | Thêm số 0 ở bên trái khi thiếu chữ số |
| Số chữ số phần nguyên **tối đa** | `getMaximumIntegerDigits()` | `setMaximumIntegerDigits(int)` | `DecimalFormat` có thể bỏ các chữ số nguyên ở bên trái nếu vượt giới hạn |
| Số chữ số phần lẻ **tối thiểu** | `getMinimumFractionDigits()` | `setMinimumFractionDigits(int)` | Thêm số 0 bên phải dấu thập phân nếu cần |
| Số chữ số phần lẻ **tối đa** | `getMaximumFractionDigits()` | `setMaximumFractionDigits(int)` | Làm tròn phần thập phân đến giới hạn này |

Hai cặp **minimum/maximum** là ràng buộc về **cách viết đầu ra**, không phải kiểu dữ liệu hay độ chính xác được lưu trong biến. Những phương thức này thuộc `NumberFormat`; `DecimalFormat` là một lớp con phổ biến hiện thực chúng.

## 2. Cấu hình một NumberFormat: ví dụ hoàn chỉnh

Tạo file **`DigitBoundsDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.util.Locale;

public class DigitBoundsDemo {
    public static void main(String[] args) {
        NumberFormat number =
                NumberFormat.getNumberInstance(Locale.US);

        number.setGroupingUsed(false);
        number.setMinimumIntegerDigits(5);
        number.setMinimumFractionDigits(2);
        number.setMaximumFractionDigits(3);
        number.setRoundingMode(RoundingMode.HALF_UP);

        System.out.println(number.format(new BigDecimal("12")));
        System.out.println(number.format(new BigDecimal("12.5")));
        System.out.println(number.format(new BigDecimal("12.3456")));
        System.out.println(number.format(new BigDecimal("0")));
        System.out.println("minInteger="
                + number.getMinimumIntegerDigits());
        System.out.println("minFraction="
                + number.getMinimumFractionDigits());
        System.out.println("maxFraction="
                + number.getMaximumFractionDigits());
    }
}
```

Biên dịch và chạy trong thư mục chứa file:

```bash
javac -encoding UTF-8 DigitBoundsDemo.java
java DigitBoundsDemo
```

**Stdout với JDK cung cấp bộ định dạng số thông thường cho `Locale.US`:**

```text
00012.00
00012.50
00012.346
00000.00
minInteger=5
minFraction=2
maxFraction=3
```

Phân tích:

1. `12` có hai chữ số nguyên nên được đệm thành `00012`; không có phần lẻ nhưng **minimum fraction = 2** buộc in `.00`.
2. `12.5` thành `00012.50`: thêm một số 0 ở cuối phần lẻ, **không** đổi số thành `1250`.
3. `12.3456` có bốn chữ số lẻ và **maximum fraction = 3** nên được làm tròn thành `12.346` theo `HALF_UP`; phần nguyên sau đó vẫn được đệm thành năm chữ số.
4. `0` có phần nguyên dài một chữ số nên được đệm thành `00000`; phần lẻ tối thiểu hiển thị `.00`.
5. `setGroupingUsed(false)` tắt dấu phân nhóm hàng nghìn để dễ quan sát các số 0 bên trái; nó **không** liên quan cơ chế làm tròn.

Ví dụ dùng `new BigDecimal("12.3456")` để biểu diễn chính xác giá trị thập phân ở đầu vào, tránh nhiễu từ số thực nhị phân `double` khi học quy tắc làm tròn.

## 3. Số chữ số phần nguyên tối thiểu: đệm 0, không làm tròn

Khi gọi `setMinimumIntegerDigits(4)`, một số nguyên như `7` có thể hiển thị `0007`. Cách này hữu ích cho **mã hiển thị có độ rộng cố định**, ví dụ số thứ tự `0007`, nhưng mã định danh quan trọng thường nên được lưu bằng **String** nếu cần giữ nguyên các số 0 đầu.

Với `DecimalFormat`, có thể đạt tác dụng tương tự bằng pattern:

```java
DecimalFormat format = new DecimalFormat(
        "0000", DecimalFormatSymbols.getInstance(Locale.US));
System.out.println(format.format(7));    // 0007
System.out.println(format.format(1234)); // 1234
```

Đây là **fragment** cần `import java.text.DecimalFormat;`, `DecimalFormatSymbols;` và `java.util.Locale;`. Mỗi ký tự `0` ở phần nguyên của pattern biểu thị một chữ số **bắt buộc** phải hiển thị. `setMinimumIntegerDigits(4)` có hiệu ứng về số chữ số tối thiểu tương tự, nhưng pattern còn điều khiển cấu trúc ký hiệu, grouping và chữ số lẻ.

**Không nhầm với chuẩn hóa giá trị:** `format.format(7)` trả về chuỗi `"0007"`; đối số `7` vẫn là số bảy. Chuỗi `"0007"` nếu chuyển lại thành số có thể mất các số 0 dẫn đầu. Vì vậy không dùng định dạng số để lưu **mã bưu điện, mã khách hàng, mã sản phẩm** có số 0 đầu.

## 4. Số chữ số phần nguyên tối đa: nguy cơ bỏ các chữ số hàng cao

Đây là chỗ **dễ gây mất dữ liệu nhất ở lớp trình bày**. Với `DecimalFormat`, nếu giới hạn số chữ số nguyên tối đa thấp hơn thực tế, formatter **bỏ bớt các chữ số bên trái** để đạt giới hạn; nó không tự chuyển sang ký pháp khoa học và cũng không làm tròn số thành một giá trị có ít chữ số.

**File `MaximumIntegerDigitsDemo.java`:**

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class MaximumIntegerDigitsDemo {
    public static void main(String[] args) {
        DecimalFormat number = new DecimalFormat(
                "0", DecimalFormatSymbols.getInstance(Locale.US));

        number.setGroupingUsed(false);
        System.out.println("Default: " + number.format(12345));

        number.setMaximumIntegerDigits(3);
        System.out.println("Max 3: " + number.format(12345));
        System.out.println("Short: " + number.format(99));
        System.out.println("Max digits: "
                + number.getMaximumIntegerDigits());
    }
}
```

```bash
javac -encoding UTF-8 MaximumIntegerDigitsDemo.java
java MaximumIntegerDigitsDemo
```

Stdout:

```text
Default: 12345
Max 3: 345
Short: 99
Max digits: 3
```

**Cực kỳ quan trọng:** `345` ở dòng thứ hai **không phải** kết quả làm tròn `12345`. Các chữ số `12` ở hàng cao đã bị **lược khỏi chuỗi hiển thị**. Số nguồn vẫn là `12345`, nhưng một người chỉ nhìn thấy nhãn `345` sẽ hiểu sai hoàn toàn.

Vì vậy:

- Không đặt giới hạn tối đa phần nguyên quá nhỏ đối với **số tiền, số lượng, đo lường** có thể lớn hơn giới hạn.
- Nếu muốn **hiển thị gọn** một lượng lớn, chọn quy ước sản phẩm minh bạch như `"12.3K"`, định dạng khoa học có kiểm soát hoặc thông báo lỗi giá trị vượt giới hạn, chứ không cắt các chữ số hàng cao.
- Nếu muốn hạn chế **đầu vào** đến tối đa N chữ số, hãy **validate giá trị đầu vào**, không dùng `setMaximumIntegerDigits(N)` làm validator. Formatter chỉ quyết định chuỗi đầu ra.
- Hành vi cắt chữ số ở phần nguyên được trình bày cụ thể cho `DecimalFormat`; đừng khái quát mọi subclass tương lai của `NumberFormat` có quy tắc y hệt mà không kiểm tra tài liệu.

## 5. Phần lẻ tối thiểu và tối đa: thêm 0 hoặc làm tròn

Hai phương thức này thường được dùng cùng nhau:

```java
number.setMinimumFractionDigits(2);
number.setMaximumFractionDigits(2);
```

Đây là **fragment** trong ngữ cảnh đã có `NumberFormat number`. Tác dụng khi in:

| Giá trị đầu vào chính xác | Min fraction = 2, max = 2, HALF_UP, en-US | Lý do |
| --- | --- | --- |
| `12` | `12.00` | Thêm hai chữ số 0 |
| `12.5` | `12.50` | Thêm một chữ số 0 |
| `12.34` | `12.34` | Giữ nguyên |
| `12.345` | `12.35` | Chữ số lẻ thứ ba làm tròn lên |
| `12.344` | `12.34` | Chữ số dư không đủ để tăng |
| `12.999` | `13.00` | Làm tròn có thể tạo **carry** sang phần nguyên |

Dòng cuối đáng chú ý: giới hạn phần lẻ có thể thay đổi **cả phần nguyên của kết quả trình bày** khi làm tròn sang một đơn vị tiếp theo. Nó hoàn toàn khác thao tác bỏ chữ số hàng cao do `setMaximumIntegerDigits`.

### Tại sao cần đặt cả min và max?

- Chỉ đặt `maxFractionDigits = 2`: kết quả có thể là `12`, `12.5` hoặc `12.35` tùy giá trị. Mục tiêu là **không quá hai** chữ số lẻ.
- Chỉ đặt `minFractionDigits = 2`: kết quả ít nhất hai chữ số lẻ nhưng có thể nhiều hơn, tùy max mặc định của formatter.
- Đặt **cả min = max = 2**: kết quả có **đúng hai chữ số lẻ** trong các trường hợp số hữu hạn bình thường, thuận tiện cho bảng giá/thông số cần độ rộng thống nhất.

`setMinimumFractionDigits(0)` cùng `setMaximumFractionDigits(0)` có nghĩa không hiển thị chữ số sau dấu thập phân; **số đầu vào vẫn được làm tròn** theo `RoundingMode` hiện hành trước khi in. Đừng suy luận `0 chữ số lẻ` tương đương cắt bỏ tất cả phần lẻ không làm tròn.

## 6. Quy tắc làm tròn: RoundingMode là một quyết định độc lập

`NumberFormat.setRoundingMode(RoundingMode)` chỉ định cách làm tròn khi giới hạn số chữ số khiến biểu diễn phải ngắn hơn. Các chế độ thường gặp:

| Mode | Ý nghĩa khi phải bỏ chữ số | Ví dụ số dương `2.5` về 0 chữ số lẻ |
| --- | --- | --- |
| `UP` | Ra xa 0 khi có phần bị bỏ | `3` |
| `DOWN` | Về phía 0 (bỏ phần dư) | `2` |
| `CEILING` | Về phía dương vô cùng | `3` |
| `FLOOR` | Về phía âm vô cùng | `2` |
| `HALF_UP` | Điểm giữa thì ra xa 0 | `3` |
| `HALF_DOWN` | Điểm giữa thì về phía 0 | `2` |
| `HALF_EVEN` | Điểm giữa chọn chữ số cuối chẵn | `2` |
| `UNNECESSARY` | Không được phép phải làm tròn | Ném `ArithmeticException` nếu không thể biểu diễn chính xác dưới ràng buộc |

**Số âm giúp nhận ra khác biệt:** `-2.5` làm tròn về 0 chữ số cho ra `-2` với `CEILING` nhưng `-3` với `FLOOR`. `HALF_UP` cho `-3`, trong khi `HALF_EVEN` chọn `-2` vì chữ số giữ lại là chẵn. Đừng diễn giải `UP` là “tăng số” trong mọi trường hợp: với số âm, `UP` là **ra xa số 0**.

`DecimalFormat` thông thường mặc định dùng `RoundingMode.HALF_EVEN`. Tuy nhiên, với code nghiệp vụ, **thiết lập mode tường minh** luôn tốt hơn phụ thuộc ngầm vào mặc định của một formatter cụ thể hoặc nguồn tạo formatter khác.

### Ví dụ so sánh điểm giữa — Java 17+

Tạo file **`FractionRoundingDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class FractionRoundingDemo {
    public static void main(String[] args) {
        DecimalFormat f = new DecimalFormat(
                "0.00", DecimalFormatSymbols.getInstance(Locale.US));

        BigDecimal a = new BigDecimal("2.345");
        BigDecimal b = new BigDecimal("2.355");

        f.setRoundingMode(RoundingMode.HALF_EVEN);
        System.out.println("Even A: " + f.format(a));
        System.out.println("Even B: " + f.format(b));

        f.setRoundingMode(RoundingMode.HALF_UP);
        System.out.println("Up A: " + f.format(a));
        System.out.println("Up B: " + f.format(b));
        System.out.println("Up negative: "
                + f.format(new BigDecimal("-2.345")));

        f.setMaximumFractionDigits(0);
        f.setMinimumFractionDigits(0);
        System.out.println("Whole: "
                + f.format(new BigDecimal("2.5")));
    }
}
```

```bash
javac -encoding UTF-8 FractionRoundingDemo.java
java FractionRoundingDemo
```

Stdout:

```text
Even A: 2.34
Even B: 2.36
Up A: 2.35
Up B: 2.36
Up negative: -2.35
Whole: 3
```

**Giải thích:**

- Với `HALF_EVEN`, `2.345` đứng đúng giữa `2.34` và `2.35`; `2.34` có chữ số cuối 4 chẵn nên được chọn. `2.355` nằm giữa `2.35` và `2.36` nên chọn `2.36` (6 chẵn).
- Với `HALF_UP`, điểm giữa được chọn **xa số 0**, vì vậy `2.345 → 2.35` và `-2.345 → -2.35`.
- Khi `maxFraction = minFraction = 0`, `2.5` theo `HALF_UP` thành `3`. Nó **không** được in thành `2` theo phép cắt.
- Mẫu `"0.00"` đảm bảo hai chữ số sau dấu chấm cho các dòng đầu; dòng cuối thay các giới hạn bằng setter.

Tất cả giá trị thập phân cần chính xác trong ví dụ được tạo từ **`String`**, tránh bất định do một literal kiểu `double` như `2.345` không luôn biểu diễn chính xác trong hệ nhị phân.

## 7. BigDecimal, double và sai khác giữa biểu diễn số với làm tròn

### BigDecimal dạng String

`new BigDecimal("2.345")` giữ chính xác giá trị thập phân `2.345`. `BigDecimal.valueOf(2.345)` sử dụng biểu diễn thập phân của `Double.toString(...)` khi chuyển từ `double`, thường thuận tiện hơn `new BigDecimal(2.345)` trong nghiệp vụ; tuy nhiên giá trị double đã được tính từ phép toán nhị phân có thể tích lũy sai số từ trước.

`new BigDecimal(2.345)` trực tiếp từ số thực nhị phân **không phải** cách đáng tin để nói “chính xác 2.345”. Kết quả nhị phân gần đúng có thể dẫn đến kết quả làm tròn gây ngạc nhiên. Đối với các khoản tiền hoặc định lượng theo thang thập phân cố định, hãy nhận đầu vào dưới dạng **chuỗi decimal có kiểm soát** hoặc dùng `BigDecimal` xuyên suốt chuỗi tính toán.

### Làm tròn để tính hay chỉ làm tròn lúc hiển thị?

Xem hai thao tác:

```java
BigDecimal raw = new BigDecimal("12.345");
BigDecimal calculated =
        raw.setScale(2, RoundingMode.HALF_UP);

String presented = format.format(raw);
```

Đây là **fragment** với `import java.math.BigDecimal` và `RoundingMode`, còn biến `format` là một formatter đã khai báo. `calculated` là **một giá trị BigDecimal mới** bằng `12.35`, trong khi `raw` vẫn là `12.345`; `presented` chỉ là chuỗi hiển thị, có thể là `"12.35"` nếu formatter dùng hai chữ số lẻ và HALF_UP.

**Ranh giới thiết kế:** nếu quy tắc nghiệp vụ bắt buộc số được chốt ở hai chữ số (ví dụ tổng tiền thanh toán đã được làm tròn), hãy thực hiện nghiệp vụ bằng `BigDecimal.setScale(...)` hoặc phép tính có `MathContext`/chính sách rõ ràng, **rồi** định dạng để hiển thị. Đừng định dạng thành chuỗi và parse ngược để thực hiện bước làm tròn nghiệp vụ: dấu phân cách, locale và rounding có thể làm mất thông tin.

### Kiểu double vẫn phù hợp cho điều gì?

`double` phù hợp nhiều tính toán khoa học/kỹ thuật chấp nhận sai số floating-point được kiểm soát. Khi sử dụng NumberFormat, phải hiểu formatter chỉ làm tròn **giá trị nhị phân đã tính được** theo quy tắc của nó, chứ không tạo ra độ chính xác thập phân vốn không tồn tại trong đầu vào.

## 8. Tương tác giữa các setter min/max

Bốn giới hạn đều không âm. `NumberFormat` đảm bảo các cặp giới hạn hợp lệ: **minimum không được vượt maximum** ở trạng thái cuối. Nếu setter mới đòi một minimum lớn hơn maximum hiện có, implementation điều chỉnh giới hạn còn lại để thỏa điều kiện; nếu setter maximum thấp hơn minimum, minimum có thể được hạ theo.

Vì vậy **thứ tự gọi setter có ý nghĩa** khi giá trị cuối của một cặp bị xung đột. Hãy thiết lập có chủ đích, rồi kiểm tra lại getters nếu điều kiện quan trọng.

**Ví dụ chạy độc lập — `DigitLimitsOrderDemo.java`:**

```java
import java.text.NumberFormat;
import java.util.Locale;

public class DigitLimitsOrderDemo {
    public static void main(String[] args) {
        NumberFormat f = NumberFormat.getNumberInstance(Locale.US);

        f.setMinimumFractionDigits(4);
        f.setMaximumFractionDigits(2);
        System.out.println("Case A min="
                + f.getMinimumFractionDigits()
                + ", max=" + f.getMaximumFractionDigits());

        f.setMaximumFractionDigits(2);
        f.setMinimumFractionDigits(4);
        System.out.println("Case B min="
                + f.getMinimumFractionDigits()
                + ", max=" + f.getMaximumFractionDigits());
    }
}
```

```bash
javac -encoding UTF-8 DigitLimitsOrderDemo.java
java DigitLimitsOrderDemo
```

Stdout với implementation `DecimalFormat` chuẩn dùng cho `Locale.US`:

```text
Case A min=2, max=2
Case B min=4, max=4
```

Nếu mục tiêu chính xác là hai chữ số lẻ, gọi `setMinimumFractionDigits(2)` và `setMaximumFractionDigits(2)`; nếu gọi lần lượt với giá trị khác nhau và kỳ vọng implementation tự bỏ qua giá trị mâu thuẫn, bạn có thể nhận độ rộng ngoài ý định.

### Có thể đặt maximumIntegerDigits(0) hay không?

Các giới hạn chữ số nhận giá trị không âm nhưng một số bộ định dạng/pattern có quy tắc biểu diễn chữ số tối thiểu đặc biệt (ví dụ trước dấu thập phân). Không nên thiết kế giao diện dựa vào giả định mọi giá trị biên `0` cho phần nguyên có hành vi đồng nhất với mọi formatter/provider. Với số thực tế, giữ tối thiểu một chữ số nguyên là lựa chọn dễ hiểu; nếu yêu cầu biểu diễn đặc biệt như `.75`, cần kiểm tra pattern và đầu ra rõ ràng.

## 9. Pattern DecimalFormat: ký tự 0, # và dấu thập phân

`DecimalFormat` cho phép mô tả giới hạn bằng pattern:

| Pattern (kiểu `en-US`) | Giá trị `12.5` | Ý nghĩa |
| --- | --- | --- |
| `"0"` | `12` (với `HALF_EVEN`; `HALF_UP` cho `13`) | Làm tròn điểm giữa theo mode đã chọn |
| `"0.00"` | `12.50` | Đúng hai chữ số lẻ |
| `"0000.00"` | `0012.50` | Tối thiểu bốn chữ số nguyên, hai chữ số lẻ |
| `"#,##0.##"` | `12.5` | Có grouping với số đủ lớn; tối đa hai chữ số lẻ |
| `"0.000"` | `12.500` | Đúng ba chữ số lẻ |

**Lưu ý chính xác về dòng đầu:** khi `RoundingMode.HALF_EVEN` được dùng, `12.5` format với `"0"` ra `12` (12 là số nguyên chẵn). Nếu dùng `HALF_UP`, kết quả là `13`. Để tránh hiểu sai, **không phụ thuộc pattern quyết định rounding mode**; pattern chỉ quyết định vị trí/độ rộng chữ số, còn mode phải được đặt theo chính sách. Các ví dụ khác của bảng không rơi vào điểm giữa cần làm tròn.

- `0` trong phần nguyên/phần lẻ là chữ số **bắt buộc**.
- `#` là vị trí chữ số **tùy chọn**; số 0 ở vị trí không cần thiết có thể bị lược.
- `.` và `,` trong pattern không nhất thiết là dấu sẽ hiển thị đúng như ký tự mẫu: `DecimalFormatSymbols`/locale xác định dấu thập phân và dấu grouping.
- Pattern có thể có ký hiệu tiền tệ, phần trăm, số mũ khoa học và prefix/suffix. Đừng coi mọi token `0` hay `#` nằm trong một chuỗi nghiệp vụ bất kỳ đều là pattern hợp lệ của `DecimalFormat`.

Với ví dụ cần stdout cố định, truyền `DecimalFormatSymbols.getInstance(Locale.US)` hoặc thiết lập locale định dạng tường minh để tránh máy khác tạo chuỗi dấu phân cách khác.

## 10. Đổi Locale: khác dấu phân cách nhưng cùng giới hạn chữ số

`setMinimumFractionDigits(2)` / `setMaximumFractionDigits(2)` xác định độ rộng phần lẻ; **locale** quyết định dấu thập phân, dấu phân nhóm và đôi khi chữ số được dùng để hiển thị.

**File `LocaleDigitsDemo.java`:**

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.util.Locale;

public class LocaleDigitsDemo {
    public static void main(String[] args) {
        BigDecimal value = new BigDecimal("1234.5");

        NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
        NumberFormat de = NumberFormat.getNumberInstance(Locale.GERMANY);

        for (NumberFormat formatter : new NumberFormat[] {us, de}) {
            formatter.setMinimumFractionDigits(2);
            formatter.setMaximumFractionDigits(2);
            formatter.setRoundingMode(RoundingMode.HALF_UP);
        }

        System.out.println("US: " + us.format(value));
        System.out.println("DE: " + de.format(value));
    }
}
```

```bash
javac -encoding UTF-8 LocaleDigitsDemo.java
java LocaleDigitsDemo
```

Đầu ra điển hình trên JDK với dữ liệu locale tương ứng:

```text
US: 1,234.50
DE: 1.234,50
```

Hai formatter giữ cùng số chữ số lẻ nhưng dùng ký hiệu địa phương khác. Đầu ra ở locale cụ thể có thể chịu ảnh hưởng nguồn dữ liệu locale và cấu hình/provider của JDK; nếu viết test so sánh chính xác, hãy kiểm soát runtime và dùng locale đủ cụ thể.

Trong server nhiều người dùng, dùng `NumberFormat.getNumberInstance(userFormatLocale)` cho từng request hay thao tác render. Đừng dùng `Locale.setDefault(...)` theo request, vì đó là thay đổi toàn JVM có thể làm các luồng ảnh hưởng lẫn nhau.

## 11. Tiền tệ, phần trăm, khoa học và các giới hạn chữ số

Không phải mọi kiểu NumberFormat đều có ngữ nghĩa “số thường”:

### Tiền tệ

`NumberFormat.getCurrencyInstance(locale)` cho một formatter được cấu hình phục vụ biểu diễn tiền theo locale. Số chữ số lẻ mặc định có thể liên quan đến quy ước tiền tệ; **đừng mặc định mọi tiền tệ có hai chữ số lẻ** (ví dụ các đơn vị tiền có quy ước 0 hoặc 3 chữ số lẻ). `Locale` là ngữ cảnh hiển thị, **không phải bằng chứng đồng tiền giao dịch**.

Khi format một khoản thanh toán, ứng dụng cần biết mã tiền tệ thực tế như `VND`, `USD`, `JPY`; lựa chọn mã đó bằng dữ liệu nghiệp vụ, quy tắc rounding riêng và chính sách phần lẻ tương ứng. `setCurrency(Currency.getInstance(...))` giúp thay đơn vị tiền trong formatter thích hợp, nhưng không thay thế kiểm soát **scale, rounding và bản chất tiền** của giao dịch.

### Phần trăm

`NumberFormat.getPercentInstance(locale)` thường **nhân giá trị với 100 khi trình bày** và thêm ký hiệu phần trăm. Ví dụ một tỷ lệ `0.125` có thể hiển thị `12.5%` nếu cấu hình phần lẻ cho phép. Giới hạn chữ số lẻ trong formatter áp dụng lên **biểu diễn phần trăm sau phép tỷ lệ**, không phải trực tiếp lượng decimal thô ban đầu. Vì thế, cắt phần lẻ trong phần trăm và cắt phần lẻ số thường có thể cho kết quả khác.

### Ký pháp khoa học và các format khác

`DecimalFormat` có các pattern hỗ trợ dạng số mũ. Giới hạn chữ số nguyên trong pattern khoa học tác động cả bố cục mantissa/exponent; không thể suy luận đơn giản nó luôn cắt chữ số như ví dụ số thập phân thông thường. Nếu cần ký pháp khoa học, định nghĩa pattern và kiểm thử riêng theo dữ liệu lớn/nhỏ, không dùng `setMaximumIntegerDigits(3)` để tự động đạt `1.23E4`.

## 12. Định dạng khác parse và khác validation

`NumberFormat` có thể vừa **format** vừa **parse**, nhưng các giới hạn chữ số chủ yếu nói về **chuỗi được xuất ra**. Đừng dùng giới hạn format để giả định chuỗi đầu vào bị kiểm tra độ dài hoặc làm tròn tương ứng.

**Ví dụ Java 17+ — `FormattingVsParsingDemo.java`:**

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParseException;
import java.util.Locale;

public class FormattingVsParsingDemo {
    public static void main(String[] args) throws ParseException {
        DecimalFormat f = new DecimalFormat(
                "0.00", DecimalFormatSymbols.getInstance(Locale.US));
        f.setRoundingMode(RoundingMode.HALF_UP);
        f.setParseBigDecimal(true);

        BigDecimal value =
                (BigDecimal) f.parse("123.456");
        String shown = f.format(value);

        System.out.println("Parsed: " + value.toPlainString());
        System.out.println("Formatted: " + shown);
        System.out.println("Still: " + value.toPlainString());
    }
}
```

```bash
javac -encoding UTF-8 FormattingVsParsingDemo.java
java FormattingVsParsingDemo
```

Stdout:

```text
Parsed: 123.456
Formatted: 123.46
Still: 123.456
```

`setParseBigDecimal(true)` là phương thức cụ thể của `DecimalFormat`; nó giúp parse thành `BigDecimal` khi thích hợp thay vì nhận kết quả có khả năng là `Long`/`Double`. `setMaximumFractionDigits(2)` không có nghĩa là chuỗi `"123.456"` bị từ chối hoặc tự làm tròn trước khi đưa thành giá trị. Sau khi format, số `value` vẫn có ba chữ số lẻ.

Nếu cần **bắt buộc không quá hai chữ số lẻ ở input**, dùng logic kiểm tra cú pháp và `BigDecimal.scale()` (xét cả trường hợp trailing zeros/normalize nếu chính sách yêu cầu), hoặc validation riêng theo ngữ cảnh. Nếu cần parse toàn bộ input, dùng `ParsePosition` hoặc kiểm tra ký tự thừa; `DecimalFormat.parse` có thể chấp nhận prefix hợp lệ mà không bắt buộc tiêu thụ toàn chuỗi. Nếu cần làm tròn giá trị dùng cho nghiệp vụ, làm ở tầng tính toán bằng `BigDecimal.setScale(...)`.

## 13. RoundingMode.UNNECESSARY và kiểm soát việc mất chính xác

Đôi khi làm tròn là **không được phép**, ví dụ một bước xử lý dữ liệu phải chứng minh rằng giá trị ban đầu có thể biểu diễn chính xác đến số chữ số yêu cầu. `RoundingMode.UNNECESSARY` ném `ArithmeticException` khi cần bỏ chữ số khác 0.

**File `UnnecessaryRoundingDemo.java`:**

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class UnnecessaryRoundingDemo {
    public static void main(String[] args) {
        DecimalFormat formatter = new DecimalFormat(
                "0.00", DecimalFormatSymbols.getInstance(Locale.US));
        formatter.setRoundingMode(RoundingMode.UNNECESSARY);

        System.out.println(formatter.format(
                new BigDecimal("7.500")));

        try {
            System.out.println(formatter.format(
                    new BigDecimal("7.501")));
        } catch (ArithmeticException exception) {
            System.out.println("Rounding would be required");
        }
    }
}
```

```bash
javac -encoding UTF-8 UnnecessaryRoundingDemo.java
java UnnecessaryRoundingDemo
```

Stdout:

```text
7.50
Rounding would be required
```

`7.500` có thể biểu diễn thành `7.50` mà không mất chữ số có ý nghĩa; `7.501` không thể đưa về hai chữ số lẻ một cách chính xác. Quy tắc này giúp phát hiện dữ liệu cần xử lý nghiệp vụ trước khi trình bày.

Không dùng `UNNECESSARY` như một cách thay thế validation đầy đủ: giới hạn độ dài phần nguyên, kiểu dữ liệu, phạm vi, tiền tệ và cú pháp input vẫn phải được kiểm soát độc lập. `UNNECESSARY` chủ yếu liên quan **việc có cần làm tròn số học** khi định dạng hay không.

## 14. Lỗi phổ biến và cách tránh

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Chỉ đặt minimum fraction = 2 và tin luôn có đúng hai chữ số lẻ | Maximum có thể cho phép nhiều hơn | Đặt min = max = 2 nếu cần đúng hai chữ số |
| Đặt maximum fraction = 2 và tin luôn có đúng hai chữ số lẻ | Số `12` có thể hiển thị `12` | Đặt minimum fraction = 2 |
| Nghĩ maximum fraction là cắt phần dư mà không làm tròn | Formatter dùng `RoundingMode` | Chọn mode tường minh, kiểm tra trường hợp nửa đơn vị |
| Nghĩ max integer = 3 làm `12345` thành `12300` | `DecimalFormat` có thể bỏ các chữ số cao và in `345` | Không giới hạn max integer ở số cần hiển thị đầy đủ |
| Gán `RoundingMode.UP` với nghĩa “tăng về +∞” | Với số âm, `UP` đi **ra xa 0** | Dùng `CEILING` nếu muốn về phía +∞ |
| Tin mặc định rounding luôn phù hợp nghiệp vụ | HALF_EVEN khác HALF_UP ở giá trị đúng giữa | Chọn theo quy định nghiệp vụ |
| Dùng literal `double` rồi kỳ vọng luôn chính xác theo decimal | Floating-point nhị phân có thể xấp xỉ | Dùng `BigDecimal(String)` khi yêu cầu decimal chính xác |
| Dùng chuỗi đã format để tính toán | Chuỗi có dấu phân cách và có thể mất độ chính xác | Tính bằng giá trị số; format ở lớp hiển thị |
| Tin setMaximumFractionDigits(2) là validation input | Giới hạn format không chặn parse/input quá dài | Validate scale, cú pháp, phạm vi riêng |
| Đổi minimum/maximum mâu thuẫn rồi không kiểm tra | Setter có thể điều chỉnh thuộc tính còn lại | Đặt cấu hình cuối có chủ đích, kiểm tra getters |
| Dùng formatter chung cho mọi luồng | `NumberFormat`/`DecimalFormat` mutable và không bảo đảm thread-safe | Tạo theo ngữ cảnh/request hoặc đồng bộ phù hợp |
| Lấy locale từ default của server cho từng người dùng | Dấu số/nhóm hàng có thể sai với người xem | Truyền `Locale` tường minh |
| Lẫn currency với locale | Locale hiển thị không quyết định giá trị giao dịch | Quản lý mã tiền và rounding nghiệp vụ riêng |
| Test so chuỗi cho mọi JDK/provider mà không cố định cấu hình | Locale data có thể khác | Dùng locale tường minh, kiểm soát runtime và kỳ vọng |

## 15. Bài tập thực hành

### Bài 1 — Chọn đúng giới hạn

Tạo formatter `Locale.US`, tắt grouping, đặt **minimum integer = 4**, **minimum fraction = 2**, **maximum fraction = 2**, **HALF_UP**. Dự đoán và chạy với `7`, `7.5`, `7.555`, `0.004`, `9.999` bằng `BigDecimal(String)`.

Mục tiêu: nhận biết hai kiểu padding và hiện tượng **carry** sang phần nguyên khi làm tròn. Thử đổi maxFraction thành 3 rồi so sánh.

### Bài 2 — Tránh giới hạn maximum integer nguy hiểm

Định dạng `987654` bằng `DecimalFormat("0")`, sau đó đặt `setMaximumIntegerDigits(3)`. Kiểm tra phần hiển thị còn lại; giải thích vì sao một API thanh toán **không bao giờ được phép** dựa vào định dạng như thế để biểu diễn giá trị tiền. Tìm giải pháp hiển thị đầy đủ hoặc thông báo vượt giới hạn.

### Bài 3 — HALF_EVEN và HALF_UP

Với `new BigDecimal("2.345")` và `new BigDecimal("2.355")`, định dạng đến hai chữ số lẻ. So sánh hai mode và giải thích quy tắc “điểm giữa chọn chữ số chẵn” của `HALF_EVEN`. Lặp lại với số âm để phân biệt `HALF_UP` với `CEILING`.

### Bài 4 — Parse và format không đối xứng

Dùng `DecimalFormat("0.00")` và `setParseBigDecimal(true)` parse `"123.456"`. Format giá trị nhận được rồi in `toPlainString()` của giá trị ban đầu. Giải thích vì sao chuỗi trình bày có hai chữ số lẻ nhưng bản thân `BigDecimal` vẫn có ba.

### Bài 5 — Locale và độ rộng

Với cùng `BigDecimal("1234.5")`, thử các locale `en-US`, `de-DE`, `vi-VN`, giữ min/max fraction = 2. Ghi chú sự khác nhau về dấu thập phân/phân nhóm, nhưng không suy luận rằng đổi dấu phân cách làm đổi **giá trị số**.

## 16. Tài liệu chính thức

- [Java SE 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html): `setMinimumIntegerDigits`, `setMaximumIntegerDigits`, `setMinimumFractionDigits`, `setMaximumFractionDigits`, `setRoundingMode`.
- [Java SE 21 — DecimalFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html): pattern, chữ số bắt buộc/tùy chọn, grouping, giới hạn phần nguyên và cách làm tròn.
- [Java SE 21 — RoundingMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html): ý nghĩa chính xác của các quy tắc làm tròn.
- [Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): `setScale`, phép toán decimal và quản lý precision.
- [Java SE 21 — DecimalFormatSymbols](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormatSymbols.html): các ký hiệu phụ thuộc locale.

## 17. Ghi nhớ

**Minimum integer/fraction digits** là mức hiển thị **ít nhất**, thường đệm bằng số 0. **Maximum fraction digits** là giới hạn số chữ số sau dấu thập phân và có thể kích hoạt **làm tròn** theo `RoundingMode`. **Maximum integer digits** với `DecimalFormat` không phải cơ chế rút gọn an toàn cho số lớn: nó có thể **loại bỏ chữ số bên trái**, làm nhãn hiển thị sai nghĩa.

Hãy chọn `Locale` tường minh, thiết lập min/max và `RoundingMode` theo mục đích, dùng `BigDecimal` cho các giá trị decimal cần chính xác, tách **làm tròn nghiệp vụ** khỏi **làm tròn khi hiển thị**, và kiểm thử những trường hợp sát ranh giới như `2.345`, `12.999`, số âm hoặc số nguyên nhiều chữ số.