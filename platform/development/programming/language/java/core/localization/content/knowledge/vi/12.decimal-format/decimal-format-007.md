# DecimalFormat: RoundingMode và kiểm soát số chữ số trong Java

## 1. Mục tiêu: số vừa đúng quy tắc làm tròn, vừa đúng cách hiển thị

Khi bản địa hóa số trong Java, chỉ chọn dấu thập phân và dấu phân nhóm theo `Locale` là chưa đủ. Một ứng dụng có thể cần hiển thị `1234.5` thành `1,234.50`, làm tròn `2.345` thành hai chữ số thập phân, hoặc giữ tối đa ba chữ số sau dấu phân cách nhưng không thêm số 0 không cần thiết.

Hai nhóm cấu hình quan trọng của `java.text.DecimalFormat` là:

- **Chính sách làm tròn**, điều khiển bằng `setRoundingMode(java.math.RoundingMode)`. Nó quyết định kết quả khi không thể biểu diễn toàn bộ phần dư trong độ chính xác hiển thị được yêu cầu.
- **Số chữ số tối thiểu/tối đa**, điều khiển bằng `setMinimumFractionDigits`, `setMaximumFractionDigits`, `setMinimumIntegerDigits`, `setMaximumIntegerDigits` hoặc pattern. Chúng quyết định độ dài/độ chính xác của chuỗi kết quả.

Đó là **hai trách nhiệm khác nhau**. Cấu hình “hai chữ số thập phân” xác định *vị trí cần làm tròn*; `RoundingMode` xác định *hướng làm tròn* tại vị trí đó.

Ví dụ với `Locale.US` và hai chữ số sau dấu thập phân:

| Giá trị gốc | Mode | Chuỗi hiển thị |
|---:|---|---|
| `2.345` | `HALF_UP` | `2.35` |
| `2.345` | `HALF_EVEN` | `2.34` |
| `2.345` | `DOWN` | `2.34` |
| `-2.345` | `CEILING` | `-2.34` |
| `-2.345` | `FLOOR` | `-2.35` |

Bài này dùng **Java 17+**, phân biệt các mode làm tròn, giới hạn chữ số phần nguyên/phần thập phân, pattern, các lỗi precision và nguyên tắc xử lý số tiền. Để có kết quả thực nghiệm nhất quán, ví dụ truyền `BigDecimal` được tạo từ **chuỗi thập phân** và định dạng bằng `DecimalFormatSymbols` của `Locale.US`.

## 2. Khởi tạo DecimalFormat đúng Locale

Một cách rõ ràng:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

DecimalFormat formatter = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));
```

Đây là **mảnh code** để đặt trong một class/phương thức Java; các chương trình chạy hoàn chỉnh nằm ở những mục sau.

`#,##0.00` là **pattern không bản địa hóa**, trong đó:

- `0` là chữ số bắt buộc: thiếu chữ số ở vị trí đó thì có thể thêm số 0 khi hiển thị.
- `#` là chữ số tùy chọn: không bắt buộc thêm số 0 vào những vị trí này.
- `,` trong pattern biểu diễn **grouping separator** theo ký pháp pattern, không nhất thiết là dấu phẩy literal trên màn hình.
- `.` trong pattern biểu diễn **decimal separator** theo ký pháp pattern, không nhất thiết là dấu chấm literal trên màn hình.

`DecimalFormatSymbols.getInstance(Locale.US)` quy định những ký hiệu hiển thị tương ứng. Với `Locale.GERMANY`, ký hiệu thập phân/nhóm số khác; không nên cố định dấu `.` và `,` vào đầu ra ứng dụng rồi gọi đó là bản địa hóa.

Có thể tạo formatter bằng:

```java
DecimalFormat formatter =
        (DecimalFormat) java.text.NumberFormat.getNumberInstance(Locale.US);
```

Tuy nhiên, các formatter từ `NumberFormat.get...Instance` có thể phụ thuộc nhà cung cấp dữ liệu locale và cấu hình; cast như trên không nhất thiết được bảo đảm cho mọi implementation. Khi cần API riêng của `DecimalFormat` và pattern do ứng dụng sở hữu, tạo trực tiếp `new DecimalFormat(pattern, symbols)` là cách minh bạch trong các ví dụ.

## 3. Bốn giới hạn chữ số chính

`DecimalFormat` kế thừa bốn cặp getter/setter từ `NumberFormat`:

| Phương thức | Tác dụng |
|---|---|
| `setMinimumFractionDigits(n)` | Ít nhất `n` chữ số sau dấu thập phân; có thể thêm số 0 |
| `setMaximumFractionDigits(n)` | Nhiều nhất `n` chữ số sau dấu thập phân; có thể cần làm tròn |
| `setMinimumIntegerDigits(n)` | Ít nhất `n` chữ số phần nguyên; có thể thêm số 0 ở đầu |
| `setMaximumIntegerDigits(n)` | Giới hạn chữ số phần nguyên mà formatter được phép hiển thị; **có thể mất các chữ số bên trái** |

Các getter tương ứng là `getMinimumFractionDigits()`, `getMaximumFractionDigits()`, `getMinimumIntegerDigits()`, `getMaximumIntegerDigits()`.

### Cách hiểu minimum và maximum fraction digits

Ví dụ:

```java
DecimalFormat optional = new DecimalFormat(
        "0.##", DecimalFormatSymbols.getInstance(Locale.US));
```

Khi format `BigDecimal("12")`, `BigDecimal("12.3")` và `BigDecimal("12.345")`:

```text
12
12.3
12.34
```

- `0.##` có **tối thiểu 0** và **tối đa 2** chữ số phần thập phân.
- Nếu không có phần thập phân cần hiển thị, dấu thập phân cũng không phải xuất hiện.
- Với `12.345` và mode làm tròn mặc định `HALF_EVEN`, kết quả là `12.34` ở hai chữ số; quyết định này phụ thuộc giá trị và mode.

Ngược lại, pattern `0.00` quy định **tối thiểu 2** và **tối đa 2**, nên `12` sẽ thành `12.00`. Số 0 ở cuối là yêu cầu **hiển thị**, không chứng minh giá trị có độ chính xác đo lường đến hai chữ số.

### Các setter tự duy trì minimum không vượt maximum

Khi đặt giới hạn mới làm cặp min/max mâu thuẫn, Java có thể điều chỉnh giới hạn còn lại. Ví dụ bắt đầu từ `#,##0.00`:

- `setMinimumFractionDigits(0)` → min 0, max 2.
- `setMaximumFractionDigits(0)` → min 0, max 0.
- `setMaximumFractionDigits(3)` → min 0, max 3.
- `setMinimumFractionDigits(4)` → min 4, max cũng thành 4.

Vì vậy, **thứ tự các lời gọi setter ảnh hưởng cấu hình cuối cùng**. Không chỉ giả định formatter vẫn giữ maximum cũ sau khi tăng minimum. Sau khi thay đổi cấu hình có tính động, đọc lại getter hoặc có test để xác nhận.

## 4. Tám chế độ java.math.RoundingMode

`DecimalFormat.setRoundingMode(...)` chấp nhận enum `java.math.RoundingMode`, cùng các tên mode được dùng trong `BigDecimal`.

| Mode | Quy tắc khi phải bỏ phần dư | Với `2.345`, giữ 2 chữ số | Với `-2.345`, giữ 2 chữ số |
|---|---|---|---|
| `UP` | Ra xa số 0 | `2.35` | `-2.35` |
| `DOWN` | Về phía số 0 | `2.34` | `-2.34` |
| `CEILING` | Về phía dương vô cùng | `2.35` | `-2.34` |
| `FLOOR` | Về phía âm vô cùng | `2.34` | `-2.35` |
| `HALF_UP` | Gần nhất; đúng nửa thì ra xa 0 | `2.35` | `-2.35` |
| `HALF_DOWN` | Gần nhất; đúng nửa thì về 0 | `2.34` | `-2.34` |
| `HALF_EVEN` | Gần nhất; đúng nửa thì chọn chữ số cuối chẵn | `2.34` | `-2.34` |
| `UNNECESSARY` | Cấm làm tròn nếu phải bỏ chữ số có ý nghĩa | Ném `ArithmeticException` | Ném `ArithmeticException` |

**Điểm dễ nhầm nhất:** `CEILING`/`FLOOR` phụ thuộc **trục số**, trong khi `UP`/`DOWN` phụ thuộc **khoảng cách tới số 0**. Chúng chỉ trùng một số trường hợp. Với số âm, `CEILING` tiến về 0, nhưng `FLOOR` đi về phía âm lớn hơn về độ lớn.

Ba mode `HALF_*` chỉ khác nhau khi giá trị cần làm tròn nằm đúng **điểm giữa** hai kết quả có thể biểu diễn. Nếu gần kết quả nào hơn, cả ba chọn kết quả gần đó.

### HALF_EVEN: làm tròn về chữ số chẵn ở vị trí giữ lại

Giữ hai chữ số sau dấu thập phân:

- `2.345` nằm đúng giữa `2.34` và `2.35`: `HALF_EVEN` chọn `2.34`, vì chữ số cuối được giữ là **4** (chẵn).
- `2.355` nằm đúng giữa `2.35` và `2.36`: `HALF_EVEN` chọn `2.36`, vì chữ số cuối được giữ là **6** (chẵn).
- `HALF_UP` chọn `2.35` và `2.36` tương ứng.

`HALF_EVEN` thường còn gọi là *banker's rounding*, có thể giảm thiên lệch thống kê qua nhiều lần làm tròn. Nhưng quy tắc tiền tệ cụ thể phải được xác định theo sản phẩm/quy định, không mặc định rằng ngân hàng hoặc tất cả quốc gia đều dùng một mode duy nhất.

## 5. Chương trình Java 17+: kiểm chứng mọi RoundingMode

Lưu vào `RoundingModesDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class RoundingModesDemo {
    public static void main(String[] args) {
        DecimalFormat formatter = new DecimalFormat(
                "0.00",
                DecimalFormatSymbols.getInstance(Locale.US));

        BigDecimal positive = new BigDecimal("2.345");
        BigDecimal negative = new BigDecimal("-2.345");

        for (RoundingMode mode : RoundingMode.values()) {
            formatter.setRoundingMode(mode);
            try {
                System.out.printf(
                        "%s: %s | %s%n",
                        mode,
                        formatter.format(positive),
                        formatter.format(negative));
            } catch (ArithmeticException exception) {
                System.out.println(mode + ": ArithmeticException");
            }
        }
    }
}
```

Biên dịch/chạy:

```bash
javac RoundingModesDemo.java
java RoundingModesDemo
```

Đầu ra đã kiểm tra trên JDK:

```text
UP: 2.35 | -2.35
DOWN: 2.34 | -2.34
CEILING: 2.35 | -2.34
FLOOR: 2.34 | -2.35
HALF_UP: 2.35 | -2.35
HALF_DOWN: 2.34 | -2.34
HALF_EVEN: 2.34 | -2.34
UNNECESSARY: ArithmeticException
```

Ở đây `new BigDecimal("2.345")` biểu diễn chính xác giá trị decimal cần thử, nên các trường hợp đúng nửa được tái hiện rõ ràng. Nếu truyền trực tiếp giá trị `double` tạo bởi phép tính hoặc literal, kết quả có thể khác do **biểu diễn nhị phân**; xem mục 9.

`UNNECESSARY` không có nghĩa “đừng in số sau dấu thập phân”. Nó có nghĩa **không được thực hiện thao tác làm tròn làm mất thông tin**. Ví dụ nếu format `2.340` theo hai chữ số thập phân, việc bỏ số 0 tận cùng không làm đổi giá trị số và có thể được chấp nhận; với `2.345` thì không thể bỏ chữ số 5 mà vẫn giữ nguyên giá trị, nên ném lỗi.

## 6. Chương trình Java 17+: min/max fraction và zero padding

Lưu vào `DigitLimitsDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class DigitLimitsDemo {
    public static void main(String[] args) {
        DecimalFormat formatter = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US));
        BigDecimal value = new BigDecimal("1234.5");

        System.out.printf(
                "initial min=%d max=%d text=%s%n",
                formatter.getMinimumFractionDigits(),
                formatter.getMaximumFractionDigits(),
                formatter.format(value));

        formatter.setMinimumFractionDigits(0);
        System.out.printf(
                "min0 min=%d max=%d text=%s%n",
                formatter.getMinimumFractionDigits(),
                formatter.getMaximumFractionDigits(),
                formatter.format(value));

        formatter.setMaximumFractionDigits(0);
        System.out.printf(
                "max0 min=%d max=%d text=%s%n",
                formatter.getMinimumFractionDigits(),
                formatter.getMaximumFractionDigits(),
                formatter.format(value));

        formatter.setMaximumFractionDigits(3);
        System.out.printf(
                "max3 min=%d max=%d text=%s%n",
                formatter.getMinimumFractionDigits(),
                formatter.getMaximumFractionDigits(),
                formatter.format(value));

        formatter.setMinimumFractionDigits(4);
        System.out.printf(
                "min4 min=%d max=%d text=%s%n",
                formatter.getMinimumFractionDigits(),
                formatter.getMaximumFractionDigits(),
                formatter.format(value));
    }
}
```

Chạy:

```bash
javac DigitLimitsDemo.java
java DigitLimitsDemo
```

Đầu ra:

```text
initial min=2 max=2 text=1,234.50
min0 min=0 max=2 text=1,234.5
max0 min=0 max=0 text=1,234
max3 min=0 max=3 text=1,234.5
min4 min=4 max=4 text=1,234.5000
```

Các thay đổi có ý nghĩa:

1. **Ban đầu:** pattern `#,##0.00` buộc hiện hai chữ số: `1,234.50`.
2. **Min = 0:** không cần đệm `0` cuối; giá trị `1234.5` trở thành `1,234.5`, dù max vẫn cho phép 2 chữ số.
3. **Max = 0:** bỏ phần thập phân; mode mặc định ở ví dụ là `HALF_EVEN`. Giá trị 1234.5 đúng nửa giữa 1234 và 1235, nên chọn **1234** (chẵn).
4. **Max = 3:** formatter được phép hiện tới 3 chữ số thập phân nhưng không bắt buộc thêm 0.
5. **Min = 4:** Java nâng max lên 4 để không còn mâu thuẫn; chuỗi được đệm thành `1,234.5000`.

Không nên xem số lượng chữ số sau dấu thập phân được in ra là độ chính xác của **giá trị trong bộ nhớ**; đó là lựa chọn cách trình bày. Điều này đặc biệt cần lưu ý khi làm tròn số tiền hoặc số đo.

## 7. Kiểm soát phần nguyên: minimum và maximum có ý nghĩa khác

Với phần nguyên, `setMinimumIntegerDigits(n)` thường được dùng để **thêm zero padding**:

```java
DecimalFormat code = new DecimalFormat(
        "0000", DecimalFormatSymbols.getInstance(Locale.US));
System.out.println(code.format(42));
```

Kết quả là `0042`. Đây là kiểu hiển thị hợp lệ cho một mã số hoặc số thứ tự, nhưng **không nên dùng DecimalFormat thay cho định dạng mã định danh tổng quát** nếu mã chứa chữ cái, dấu gạch hoặc cần giữ nguyên chuỗi đầu vào.

`setMaximumIntegerDigits(n)` khác biệt và nguy hiểm hơn: với `DecimalFormat`, nó có thể **cắt bỏ các chữ số bên trái** khi phần nguyên quá dài.

Ví dụ mảnh code:

```java
DecimalFormat limited = new DecimalFormat(
        "0000", DecimalFormatSymbols.getInstance(Locale.US));
limited.setMaximumIntegerDigits(3);

System.out.println(limited.format(12345));
```

Với cấu hình này, kết quả kiểm chứng là:

```text
345
```

Vì `setMaximumIntegerDigits(3)` làm maximum thành 3 và có thể điều chỉnh minimum xuống 3, `12345` mất hai chữ số quan trọng bên trái. Đừng sử dụng maximum integer digits để **validate độ lớn số** hoặc để che bớt số mà vẫn mong kết quả giữ nguyên giá trị. Nếu miền dữ liệu yêu cầu tối đa ba chữ số, hãy kiểm tra giá trị trước khi format và báo lỗi nếu vượt phạm vi.

Khi muốn kiểm soát **tổng số chữ số có nghĩa** thay vì số chữ số nguyên/thập phân, cần thiết kế quy tắc khác (chẳng hạn thao tác với `BigDecimal` theo `MathContext`), không giả định `setMaximumIntegerDigits` là một “significant digits limit”.

## 8. Pattern và setters: cái nào có quyền quyết định?

`DecimalFormat` lấy min/max chữ số ban đầu từ pattern. Ví dụ:

| Pattern | Minimum fraction | Maximum fraction | Ví dụ giá trị `12` |
|---|---:|---:|---|
| `0` | 0 | 0 | `12` |
| `0.0` | 1 | 1 | `12.0` |
| `0.00` | 2 | 2 | `12.00` |
| `0.##` | 0 | 2 | `12` |
| `#,##0.000` | 3 | 3 | `12.000` |

Sau khi áp dụng pattern, có thể thay đổi các giới hạn bằng setter. Nhưng gọi `applyPattern(...)` **sau đó** có thể đặt lại các giới hạn phù hợp với pattern mới.

Ví dụ:

```java
DecimalFormat df = new DecimalFormat(
        "0.00", DecimalFormatSymbols.getInstance(Locale.US));
df.setMaximumFractionDigits(0);
df.applyPattern("0.000");

System.out.println(df.getMinimumFractionDigits());
System.out.println(df.getMaximumFractionDigits());
```

Kết quả:

```text
3
3
```

Vì `applyPattern("0.000")` đã cập nhật min/max theo pattern mới. Nếu cần vừa dùng pattern vừa cấu hình bằng setters, **áp dụng pattern trước rồi mới đặt min/max và rounding mode**. Kiểm tra getter trong tests để phát hiện thứ tự sai khi refactor.

Các pattern có phần dấu phần trăm (`%`), phần tiền tệ (`¤`), khoa học (`E`) hoặc các mẫu số có nghĩa đặc biệt có thể thay đổi cách hiểu số chữ số. Bài này tập trung vào pattern thập phân thông thường như `#,##0.00`; không nên suy ra toàn bộ logic của định dạng khoa học chỉ từ ví dụ decimal cơ bản.

## 9. double, BigDecimal và hiện tượng “làm tròn bất ngờ”

`double` dùng biểu diễn nhị phân, không lưu chính xác mọi phân số thập phân. Trong một số trường hợp, giá trị gần `2.675` nhưng **nhỏ hơn** điểm giữa thực sự; với hai chữ số thập phân, kết quả có thể là `2.67` thay vì `2.68`.

Ví dụ Java 17+ độc lập, lưu `DecimalPrecisionDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class DecimalPrecisionDemo {
    public static void main(String[] args) {
        DecimalFormat formatter = new DecimalFormat(
                "0.00",
                DecimalFormatSymbols.getInstance(Locale.US));
        formatter.setRoundingMode(RoundingMode.HALF_EVEN);

        double primitive = 2.675;
        BigDecimal exact = new BigDecimal("2.675");
        BigDecimal fromDouble = new BigDecimal(primitive);

        System.out.println("double=" + formatter.format(primitive));
        System.out.println("stringBD=" + formatter.format(exact));
        System.out.println("newBDdouble=" + formatter.format(fromDouble));
    }
}
```

Chạy:

```bash
javac DecimalPrecisionDemo.java
java DecimalPrecisionDemo
```

Kết quả kiểm chứng:

```text
double=2.67
stringBD=2.68
newBDdouble=2.67
```

Giải thích:

- `double` không biểu diễn chính xác decimal `2.675`; kết quả làm tròn phụ thuộc giá trị binary thực sự được nhận.
- `new BigDecimal("2.675")` biểu diễn decimal đúng như văn bản.
- `new BigDecimal(primitive)` phản ánh chi tiết giá trị `double` đã bị xấp xỉ, không tự sửa thành decimal mong muốn.
- `BigDecimal.valueOf(primitive)` lại sử dụng dạng thập phân từ `Double.toString` làm căn cứ, nên có thể phù hợp hơn `new BigDecimal(double)` khi muốn chuyển giá trị `double` hiện hữu sang decimal có cách biểu diễn dễ hiểu. Tuy nhiên, nếu độ chính xác ban đầu đã bị mất trong những phép tính trước đó, `valueOf` không thể khôi phục dữ liệu không còn tồn tại.

Nếu dữ liệu nghiệp vụ vốn xuất phát từ một chuỗi decimal như số tiền từ input hoặc database, hãy phân tích/lưu thành `BigDecimal` ngay từ đầu thay vì đi vòng qua `double`. Không nên viết tests làm tròn tie-case bằng các literal `double` rồi kết luận phương thức format làm sai quy tắc HALF_EVEN.

## 10. Làm tròn khi định dạng khác với thay đổi giá trị

`DecimalFormat.format(number)` tạo **chuỗi hiển thị**. Nó không sửa nội dung `BigDecimal` hoặc `double` đã truyền vào.

```java
BigDecimal value = new BigDecimal("12.345");
DecimalFormat formatter = new DecimalFormat(
        "0.00", DecimalFormatSymbols.getInstance(Locale.US));
formatter.setRoundingMode(RoundingMode.HALF_UP);

String text = formatter.format(value);
// text = "12.35"
// value vẫn bằng 12.345
```

Đây là mảnh code minh họa trong phương thức đã có import thích hợp. Nếu cần **giá trị số đã lượng hóa** thành hai chữ số để lưu hoặc tính tiếp, làm rõ quy tắc bằng:

```java
BigDecimal rounded = value.setScale(2, RoundingMode.HALF_UP);
```

Kết quả `rounded` là một `BigDecimal` mới có scale 2. `BigDecimal` là immutable; `setScale` không sửa `value` gốc.

**Không** lấy chuỗi đã định dạng theo locale rồi truyền ngay cho `new BigDecimal(text)`. Ví dụ `"1,234.50"` là cách hiển thị ở US có dấu grouping, không phải cú pháp decimal chuẩn mà constructor nhận; ở locale khác dấu phẩy có thể là decimal separator. Tách bạch:

1. **Lưu trữ/tính toán:** chọn kiểu và quy tắc làm tròn số chính xác, thường `BigDecimal` với tiền.
2. **Trình bày cho người dùng:** dùng `DecimalFormat` theo `Locale`, giới hạn chữ số và mode tương ứng.
3. **Phân tích input đã bản địa hóa:** dùng parser được cấu hình rõ ràng và kiểm tra việc parse tiêu thụ đầy đủ chuỗi; không đồng nhất parsing hiển thị với parsing định dạng máy.

Không nên lấy một giá trị đã được làm tròn để hiển thị rồi dùng ngược làm cơ sở cho tính toán tài chính, vì có thể gây sai lệch tích lũy.

## 11. Chọn số chữ số cho tiền tệ, tỉ lệ và số đo

### Tiền tệ

Một cách thực tế là lấy `NumberFormat.getCurrencyInstance(locale)` và đặt `Currency` phù hợp. Số chữ số thập phân mặc định có thể theo currency; ví dụ một số currency có 0, 2 hoặc 3 chữ số thập phân thông dụng.

Nhưng **đừng nghĩ mọi nghiệp vụ tiền tệ đều có đúng hai chữ số** hoặc các quy tắc cash rounding đều được giải quyết chỉ bởi `setRoundingMode`. Một số tiền có thể cần làm tròn theo bội số (như đơn vị nhỏ nhất được phép thu tiền mặt), chứ không đơn thuần chọn bao nhiêu decimal places. Trường hợp đó cần nghiệp vụ lượng hóa theo bước/bội số trước khi hiển thị.

Nếu phải dùng `DecimalFormat` cho số tiền, đảm bảo currency symbol, số chữ số và mode được áp dụng đúng chính sách; test với từng currency được hệ thống hỗ trợ.

### Tỉ lệ phần trăm

`NumberFormat.getPercentInstance(locale)` / `DecimalFormat` có thể nhân giá trị đầu vào với 100 khi hiển thị. Ví dụ một tỉ lệ `0.125` có thể được trình bày là `12.5%` nếu cho phép một chữ số thập phân. Vì phép nhân và chữ số hiển thị là hai ý nghĩa riêng, đừng kết luận `setMaximumFractionDigits(1)` tương đương với làm tròn tỉ lệ gốc đến 1 decimal place.

### Số đo liên tục

Với nhiệt độ, chiều dài, vận tốc hay dữ liệu sensor, số chữ số tối đa cho phần thập phân có thể phụ thuộc độ chính xác của nguồn đo. `setMinimumFractionDigits` giúp giao diện nhất quán; `setMaximumFractionDigits` và `RoundingMode` điều chỉnh rounding presentation. Không được dùng số chữ số in ra để tuyên bố độ tin cậy hoặc độ chính xác đo lường ngoài những gì nguồn dữ liệu hỗ trợ.

## 12. UNNECESSARY: phát hiện nhu cầu làm tròn không được phép

Mode `RoundingMode.UNNECESSARY` đặc biệt hữu ích nếu ứng dụng **đòi hỏi giá trị đã phù hợp với độ chính xác chỉ định** và không muốn mất chữ số có ý nghĩa.

Ví dụ:

```java
DecimalFormat strict = new DecimalFormat(
        "0.00", DecimalFormatSymbols.getInstance(Locale.US));
strict.setRoundingMode(RoundingMode.UNNECESSARY);

System.out.println(strict.format(new BigDecimal("12.30")));
// 12.30
System.out.println(strict.format(new BigDecimal("12.345")));
// Ném ArithmeticException vì cần làm tròn
```

Ở đây `12.30` đã vừa hai chữ số decimal, còn `12.345` không thể giữ nguyên giá trị khi chỉ in hai chữ số decimal.

Cần bắt ngoại lệ đúng chỗ khi dữ liệu không đáng tin cậy hoặc khi có thể gửi đến nhiều luồng xử lý. `UNNECESSARY` không phải “cắt phần dư mà không làm tròn” — điều đó gần với `DOWN`, và `DOWN` vẫn có thể làm mất giá trị.

Trong lớp xử lý tiền hoặc validate payload, một lối thiết kế dễ kiểm soát hơn là kiểm tra scale bằng `BigDecimal.setScale(expectedScale, RoundingMode.UNNECESSARY)` để fail sớm trước khi tạo string hiển thị, nếu quy tắc nghiệp vụ thực sự yêu cầu scale cố định.

## 13. Kiểm thử các biên làm tròn quan trọng

Không chỉ test một số dương. Với hai chữ số thập phân và các mode thường dùng, test tối thiểu:

| Giá trị | HALF_UP | HALF_DOWN | HALF_EVEN |
|---|---|---|---|
| `2.344` | `2.34` | `2.34` | `2.34` |
| `2.345` | `2.35` | `2.34` | `2.34` |
| `2.355` | `2.36` | `2.35` | `2.36` |
| `-2.345` | `-2.35` | `-2.34` | `-2.34` |
| `-2.355` | `-2.36` | `-2.35` | `-2.36` |

Ở các giá trị `2.344`, tất cả mode gần nhất giống nhau vì không đúng điểm giữa. `UP`/`DOWN` và `CEILING`/`FLOOR` cần test riêng số âm để phát hiện nhầm hướng.

Ngoài ra cần test:

- `minFraction=0/maxFraction=2` với giá trị nguyên: có thêm `.00` không? (Không.)
- `minFraction=2/maxFraction=2` với giá trị nguyên: có thêm `.00` không? (Có.)
- `maxFraction=0` với tie-case `1234.5`, `1235.5` dưới `HALF_EVEN`.
- `minFraction > maxFraction` qua thứ tự setters: getter có bị tự điều chỉnh không?
- `applyPattern` sau khi gọi setter: các giới hạn có bị đặt lại không?
- `maxIntegerDigits` nhỏ hơn độ dài phần nguyên: có bị mất chữ số bên trái không?
- Format cùng giá trị ở nhiều locale: dấu nhóm, dấu thập phân và chữ số có thể khác.
- Giá trị `double` sát một decimal tie, ví dụ `2.675`, so với `BigDecimal` tạo từ chuỗi.
- `UNNECESSARY` với giá trị vừa scale và giá trị buộc phải làm tròn.
- Kiểm thử số rất lớn, số gần 0, số âm, số có độ chính xác cao và các trường hợp sử dụng scientific notation nếu ứng dụng cho phép.

## 14. Những lỗi phổ biến

1. **Nhầm số chữ số tối thiểu với tối đa.** Min thêm số 0 để hiển thị; max có thể làm tròn/mất chữ số.
2. **Dùng mặc định HALF_EVEN mà nghiệp vụ cần HALF_UP.** Mode mặc định của `DecimalFormat` là `HALF_EVEN`; đặt rõ mode khi yêu cầu cụ thể.
3. **Cho rằng UP luôn là về dương vô cùng.** `UP` đi xa số 0; `CEILING` mới hướng về dương vô cùng.
4. **Cho rằng DOWN luôn là về âm vô cùng.** `DOWN` đi về 0; `FLOOR` mới hướng về âm vô cùng.
5. **Test tie-case bằng literal double và mong luôn chính xác.** Dùng `BigDecimal` từ chuỗi để kiểm soát giá trị decimal.
6. **Giả định thay min không ảnh hưởng max.** Các setter duy trì quan hệ min <= max, có thể tự điều chỉnh phía còn lại.
7. **Gọi applyPattern sau setters rồi quên giới hạn bị cập nhật.** Áp dụng pattern trước, chỉnh setters sau.
8. **Dùng maxIntegerDigits để chặn số quá lớn.** Formatter có thể cắt các chữ số có nghĩa bên trái; validation phải thực hiện riêng.
9. **Coi format làm thay đổi giá trị số.** Nó chỉ tạo chuỗi; dùng `BigDecimal.setScale` khi cần giá trị đã được làm tròn.
10. **Dùng chuỗi định dạng locale làm input của BigDecimal constructor.** Dấu nhóm và decimal separator của locale không phải cú pháp constructor.
11. **Định dạng tiền bằng đúng 2 decimals cho mọi currency.** Quy tắc số chữ số và cash rounding phụ thuộc currency/nghiệp vụ.
12. **Chia sẻ DecimalFormat mutable giữa các thread.** `DecimalFormat` không thread-safe; tạo instance phù hợp cho mỗi luồng/ngữ cảnh.
13. **Không validate số đếm, số lượng hoặc thang đo.** Formatting đẹp không đảm bảo input nằm trong miền hợp lệ.
14. **Bỏ qua kết quả UNNECESSARY.** Đây là mode yêu cầu tính chính xác, có thể ném `ArithmeticException` khi cần làm tròn.
15. **Tự đoán dấu thập phân/nhóm số từ Locale.** Dùng `DecimalFormatSymbols` và kiểm thử kết quả thật.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Muốn `12` hiển thị thành `12.00`, cần điều chỉnh gì?

**Đáp án:** Tối thiểu 2 chữ số thập phân, ví dụ pattern `0.00` hoặc `setMinimumFractionDigits(2)` với maximum đủ lớn.

**Câu 2.** Giữ 2 chữ số thập phân, `2.345` dưới HALF_UP và HALF_EVEN khác nhau thế nào?

**Đáp án:** HALF_UP → `2.35`, HALF_EVEN → `2.34` vì chữ số 4 của kết quả `2.34` là chẵn.

**Câu 3.** Với `-2.345`, mode CEILING và FLOOR trả gì khi giữ 2 chữ số?

**Đáp án:** CEILING → `-2.34`, FLOOR → `-2.35`.

**Câu 4.** Nếu từ pattern `0.00` đặt `setMaximumFractionDigits(0)`, minimum fraction là bao nhiêu?

**Đáp án:** Minimum được điều chỉnh thành 0 để không vượt maximum.

**Câu 5.** `setMaximumIntegerDigits(3)` có phải validation ngăn số nguyên 5 chữ số không?

**Đáp án:** Không. `DecimalFormat` có thể chỉ hiển thị ba chữ số cuối; phải validate giá trị trước khi format.

**Câu 6.** Vì sao `format(2.675)` và `format(new BigDecimal("2.675"))` có thể khác dưới HALF_EVEN?

**Đáp án:** `double` biểu diễn nhị phân xấp xỉ, còn `BigDecimal` tạo từ chuỗi biểu diễn chính xác decimal 2.675.

**Câu 7.** `RoundingMode.UNNECESSARY` cho phép truncate im lặng không?

**Đáp án:** Không. Nếu cần bỏ phần có ý nghĩa để đáp ứng giới hạn chữ số, nó ném `ArithmeticException`.

**Câu 8.** Format thành `1,234.50` có sửa giá trị `BigDecimal("1234.5")` thành `1234.50` không?

**Đáp án:** Không. Formatting là phép biểu diễn; muốn thay đổi scale theo quy tắc đã thống nhất, tạo `BigDecimal` mới bằng `setScale`.

## 16. Tổng kết

`DecimalFormat` kết hợp **pattern/Locale** để quyết định hình thức chữ số với **`RoundingMode`** để quyết định làm tròn. `minimumFractionDigits` điều khiển zero padding; `maximumFractionDigits` điều khiển điểm làm tròn. `minimumIntegerDigits` có thể đệm số 0 đầu, còn `maximumIntegerDigits` cần dùng thận trọng vì có thể cắt chữ số bên trái.

Đối với logic tài chính hoặc dữ liệu yêu cầu precision cao, lưu/tính bằng `BigDecimal`, đặt chính sách làm tròn và scale rõ ràng ở lớp nghiệp vụ, rồi định dạng theo locale ở bước hiển thị. Kiểm thử số dương, âm, tie-case, min/max và thứ tự setters là cách tránh lỗi số học lẫn lỗi bản địa hóa.

**Tài liệu chính thức:** [Java SE 17 — DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html) · [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html) · [Java SE 17 — RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html) · [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).
