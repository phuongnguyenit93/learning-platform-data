# `BigDecimal.stripTrailingZeros()` có thể tạo `scale` âm

## 1. Vấn đề cần hiểu

Trong Java, `BigDecimal.stripTrailingZeros()` loại bỏ các chữ số `0` không cần thiết ở **cuối phần số nguyên không có dấu thập phân (unscaled value)** của biểu diễn `BigDecimal`, đồng thời điều chỉnh `scale` để **giá trị số học không đổi**. Vì thế, kết quả có thể có `scale < 0`, ngay cả khi đối tượng ban đầu có `scale = 0` hoặc `scale > 0`.

Ví dụ:

~~~java
BigDecimal original = new BigDecimal("600.00");
BigDecimal normalized = original.stripTrailingZeros();

System.out.println(normalized);         // 6E+2
System.out.println(normalized.scale()); // -2
~~~

`6E+2` vẫn là **600**. `scale = -2` không biểu thị số âm, lỗi tràn số hoặc mất độ chính xác. Đây là cách biểu diễn hợp lệ của cùng một giá trị `BigDecimal`.

Sau bài này, bạn cần giải thích được phép biến đổi `unscaledValue/scale`, phân biệt so sánh giá trị với so sánh biểu diễn, và chọn cách định dạng hoặc chuẩn hóa phù hợp.

## 2. `BigDecimal` lưu số như thế nào?

Về mặt khái niệm, một giá trị hữu hạn của `BigDecimal` được xác định bởi:

\[
\text{value}=\text{unscaledValue}\times 10^{-\text{scale}}
\]

Trong đó:

- `unscaledValue()` trả về một `BigInteger` chứa các chữ số có nghĩa kèm dấu, trước khi đặt dấu thập phân.
- `scale()` là số chữ số ở bên phải dấu thập phân theo công thức trên. `scale` có thể **dương, bằng 0 hoặc âm**.
- `precision()` là số chữ số trong `unscaledValue` ở biểu diễn thập phân (không tính dấu; số `0` có precision bằng 1).
- Hai đối tượng có thể cùng giá trị toán học nhưng khác `unscaledValue`, `scale`, `precision`.

Ví dụ:

| Biểu diễn | `unscaledValue` | `scale` | Giá trị |
| --- | ---: | ---: | ---: |
| `600.00` | `60000` | `2` | `600` |
| `600` | `600` | `0` | `600` |
| `6E+2` | `6` | `-2` | `600` |
| `0.001000` | `1000` | `6` | `0.001` |

Với `6E+2`, công thức cho `6 × 10^(-(-2)) = 6 × 10² = 600`. Do đó **scale âm nghĩa là vị trí dấu thập phân được dịch về phía phải của unscaled value**, tương đương nhân với một lũy thừa dương của 10.

Lưu ý: `scale` không phải số chữ số có nghĩa; để xem số chữ số có nghĩa, dùng `precision()`. Cũng không nên xem `scale` là quy định định dạng hiển thị cố định cho mọi phép toán.

## 3. Vì sao `stripTrailingZeros()` làm `scale` âm?

Phương thức trả về một đối tượng `BigDecimal` tương đương về giá trị, bỏ các thừa số 10 cuối `unscaledValue`. Mỗi lần bỏ một chữ số 0 ở cuối `unscaledValue`, `scale` giảm 1 để giữ nguyên kết quả phép nhân.

Với `new BigDecimal("600.00")`:

| Bước | `unscaledValue` | `scale` | Giá trị |
| --- | ---: | ---: | ---: |
| Ban đầu | `60000` | `2` | `600.00` |
| Bỏ một `0` | `6000` | `1` | `600.0` |
| Bỏ một `0` nữa | `600` | `0` | `600` |
| Bỏ tiếp `0` | `60` | `-1` | `600` |
| Bỏ `0` cuối | `6` | `-2` | `600` |

Kết quả có `unscaledValue = 6` và `scale = -2`. `toString()` biểu diễn nó là `6E+2`.

Điểm dễ nhầm là phương thức không chỉ xóa các số 0 **sau dấu thập phân trong chuỗi hiển thị**. Nó còn có thể loại bỏ số 0 **ở cuối số nguyên** khi biểu diễn dạng unscaled có đủ thừa số 10.

Một số kết quả tiêu biểu:

| Đầu vào `new BigDecimal("...")` | Sau `stripTrailingZeros()` (dạng `toString()`) | `scale` kết quả |
| --- | --- | ---: |
| `"125.000"` | `125` | `0` |
| `"120.3000"` | `120.3` | `1` |
| `"1000"` | `1E+3` | `-3` |
| `"600.00"` | `6E+2` | `-2` |
| `"0.001000"` | `0.001` | `3` |
| `"0.000"` | `0` | `0` |

**Trường hợp đặc biệt là số 0:** `stripTrailingZeros()` trả về biểu diễn `BigDecimal.ZERO` với `scale = 0`, bất kể số 0 ban đầu có bao nhiêu chữ số sau dấu thập phân. Không thể suy ra `scale` của kết quả chỉ bằng cách đếm chữ số `0` trong chuỗi đầu vào.

`stripTrailingZeros()` là phép biến đổi **chính xác**, không làm tròn, không dùng `MathContext` và không thay đổi đối tượng nguồn (vì `BigDecimal` bất biến). Độ chính xác của giá trị số học vẫn được giữ nguyên; `precision()` của biểu diễn có thể thay đổi.

## 4. Ví dụ Java 17+ chạy độc lập

Lưu tệp dưới tên `BigDecimalNegativeScaleDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class BigDecimalNegativeScaleDemo {
    public static void main(String[] args) {
        BigDecimal original = new BigDecimal("600.00");
        BigDecimal normalized = original.stripTrailingZeros();

        System.out.printf(
                "original: %s, unscaled=%s, scale=%d%n",
                original, original.unscaledValue(), original.scale()
        );
        System.out.printf(
                "normalized: %s, unscaled=%s, scale=%d%n",
                normalized, normalized.unscaledValue(), normalized.scale()
        );

        System.out.println("plain: " + normalized.toPlainString());
        System.out.println("equals: " + original.equals(normalized));
        System.out.println("compareTo: " + original.compareTo(normalized));
        System.out.println(
                "fixed scale 2: "
                        + normalized.setScale(2, RoundingMode.UNNECESSARY)
        );

        BigDecimal zero = new BigDecimal("0.000").stripTrailingZeros();
        System.out.printf("zero: %s, scale=%d%n", zero, zero.scale());
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac BigDecimalNegativeScaleDemo.java
java BigDecimalNegativeScaleDemo
~~~

Kết quả stdout:

~~~text
original: 600.00, unscaled=60000, scale=2
normalized: 6E+2, unscaled=6, scale=-2
plain: 600
equals: false
compareTo: 0
fixed scale 2: 600.00
zero: 0, scale=0
~~~

Giải thích:

1. Giá trị gốc `600.00` có `unscaledValue = 60000`, `scale = 2`; đối tượng chuẩn hóa có `unscaledValue = 6`, `scale = -2`.
2. `toString()` có thể dùng ký pháp mũ (`6E+2`), còn `toPlainString()` trả về biểu diễn thập phân thông thường (`600`).
3. `equals()` trả về `false` vì hai đối tượng khác `scale` dù giá trị số học giống nhau.
4. `compareTo()` trả về `0` vì so sánh **giá trị số học**.
5. `setScale(2, RoundingMode.UNNECESSARY)` tạo một đối tượng mới có `scale = 2` và giá trị `600.00`; trường hợp này chỉ thêm các chữ số 0, không cần làm tròn.
6. Số 0 sau khi bỏ các số 0 tận cùng có `scale = 0`.

## 5. Hệ quả quan trọng với `equals()`, `compareTo()` và hash

`BigDecimal.equals(Object)` kiểm tra cả **giá trị** và **scale**. `BigDecimal.compareTo(BigDecimal)` so sánh giá trị số học, bỏ qua khác biệt chỉ do scale.

~~~java
BigDecimal a = new BigDecimal("1000");
BigDecimal b = a.stripTrailingZeros(); // 1E+3; scale = -3

System.out.println(a.equals(b));    // false
System.out.println(a.compareTo(b)); // 0
~~~

Trong `HashSet<BigDecimal>` và khóa `HashMap<BigDecimal, ...>`, `equals()` và `hashCode()` quyết định trùng khóa. Vì thế, `1000` và `1E+3` có thể là **hai khóa khác nhau**. Trong `TreeSet<BigDecimal>` sử dụng thứ tự tự nhiên `compareTo()`, chúng lại được coi là tương đương theo phép so sánh thứ tự.

Điều này không phải do `scale` âm riêng lẻ; sự khác biệt `equals`/`compareTo` đã tồn tại cả với `1.0` và `1.00`. Việc gọi `stripTrailingZeros()` có thể làm khác biệt biểu diễn lộ rõ hơn.

Nếu nghiệp vụ yêu cầu so sánh **giá trị tiền hoặc số đo**, thông thường dùng `compareTo() == 0`. Nếu yêu cầu so khớp chính xác biểu diễn, bao gồm scale, dùng `equals()`. Với collection dựa trên hash, hãy quyết định và áp dụng một quy tắc chuẩn hóa đầu vào thống nhất, đồng thời xét nhu cầu giữ scale gốc.

## 6. Phân biệt giá trị, scale và cách hiển thị

Một số API nhìn tương tự nhưng giải quyết vấn đề khác nhau:

| API | Mục đích | Điều cần chú ý |
| --- | --- | --- |
| `stripTrailingZeros()` | Bỏ các thừa số 10 dư trong biểu diễn | Có thể tạo scale âm và không giữ số chữ số thập phân ban đầu |
| `scale()` | Đọc scale hiện tại | Scale âm là hợp lệ |
| `toString()` | In biểu diễn chuẩn; có thể dùng ký pháp mũ | `new BigDecimal("600.00").stripTrailingZeros().toString()` là `6E+2` |
| `toPlainString()` | In dạng số thập phân thông thường, không ký pháp mũ | Chỉ đổi **chuỗi hiển thị**, không đổi đối tượng hay scale |
| `setScale(n, mode)` | Tạo đối tượng mới có scale xác định | Có thể cần làm tròn, hoặc ném lỗi nếu `UNNECESSARY` và phải làm tròn |
| `compareTo()` | So sánh giá trị số học | Không yêu cầu scale giống nhau |
| `equals()` | So sánh giá trị và scale | Có thể trả `false` cho hai số cùng giá trị |

Ví dụ, khi chỉ muốn chuỗi `"600"` thay cho `"6E+2"`:

~~~java
BigDecimal x = new BigDecimal("600.00").stripTrailingZeros();
String plain = x.toPlainString(); // "600"; x.scale() vẫn là -2
~~~

Đừng nhầm `toPlainString()` với việc chuẩn hóa dữ liệu nội bộ: đọc lại chuỗi `"600"` bằng `new BigDecimal(plain)` sẽ tạo đối tượng có `scale = 0`, khác `scale = -2` ban đầu. Nếu trao đổi dữ liệu yêu cầu giữ cả biểu diễn lẫn giá trị, cần định nghĩa rõ format truyền tải.

Nếu giao diện phải luôn hiển thị hai chữ số thập phân, hãy định rõ quy tắc format hoặc scale ở ranh giới hiển thị; `stripTrailingZeros()` không phục vụ yêu cầu này:

~~~java
BigDecimal amount = new BigDecimal("600.00");
BigDecimal fixed = amount.stripTrailingZeros()
                         .setScale(2, RoundingMode.UNNECESSARY);
// fixed.toPlainString() -> "600.00"
~~~

Khi cần đổi `scale` của số có phần thập phân không phù hợp (ví dụ `12.345` thành scale 2), `RoundingMode.UNNECESSARY` sẽ ném `ArithmeticException`, vì phải bỏ chữ số khác 0. Hãy chọn quy tắc làm tròn theo yêu cầu nghiệp vụ thay vì tùy tiện bỏ phần dư.

## 7. Cách sử dụng phù hợp trong thực tế

**Trường hợp A — chỉ muốn hiển thị không có ký pháp mũ.** Dùng `toPlainString()` sau khi chuẩn hóa. Đừng tự giả định `scale >= 0`:

~~~java
BigDecimal value = new BigDecimal("1000").stripTrailingZeros();
System.out.println(value.toString());      // 1E+3
System.out.println(value.toPlainString()); // 1000
~~~

**Trường hợp B — cần một scale cố định theo hợp đồng dữ liệu.** Dùng `setScale(targetScale, roundingMode)` với chính sách làm tròn được quyết định rõ. Ví dụ số tiền VND không có phần lẻ có thể đặt scale 0; tiền có hai chữ số thập phân có thể đặt scale 2 nếu ứng dụng thực sự dùng quy tắc đó. Không áp dụng `stripTrailingZeros()` sau bước đặt scale nếu cần giữ biểu diễn cố định.

**Trường hợp C — kiểm tra số có phải số nguyên về mặt giá trị.** Cách kiểm tra sau là sai với một số nguyên lớn có scale âm:

~~~java
BigDecimal value = new BigDecimal("1000").stripTrailingZeros();
boolean wrong = value.scale() == 0; // false dù giá trị là số nguyên
~~~

Với `BigDecimal` hữu hạn, sau `stripTrailingZeros()`, điều kiện `scale() <= 0` nhận diện giá trị nguyên. Khi thực sự cần lấy một `BigInteger` và kiểm tra chính xác không có phần lẻ, có thể dùng `toBigIntegerExact()`: phương thức này ném `ArithmeticException` nếu có phần lẻ khác 0.

**Trường hợp D — chuẩn hóa số để so sánh hoặc dùng làm khóa.** Thống nhất quy tắc từ lúc tiếp nhận giá trị. `stripTrailingZeros()` có thể hữu ích khi bạn chấp nhận loại bỏ scale để hợp nhất các biểu diễn cùng giá trị (ví dụ `1.0` và `1.00` cùng về `1`). Tuy nhiên việc này sẽ đánh mất thông tin scale ban đầu, nên không thích hợp nếu scale mang ý nghĩa nghiệp vụ.

## 8. Những lỗi phổ biến và cách tránh

1. **Giả định kết quả của `stripTrailingZeros()` luôn có `scale >= 0`.** Một số tròn như `1000` trở thành `1E+3` với `scale = -3`. Viết code chấp nhận cả ba trường hợp scale dương, 0, âm.
2. **Cho rằng `scale` âm nghĩa là số âm hoặc giá trị bị thay đổi.** Scale là số mũ trong công thức biểu diễn; kiểm tra giá trị bằng `compareTo()`.
3. **Dùng `equals()` khi chỉ muốn so sánh giá trị.** `600.00` không `equals` với `6E+2` dù `compareTo() == 0`.
4. **Dùng `stripTrailingZeros()` để cố giữ hai chữ số thập phân cho số tiền.** Phương thức thực hiện điều ngược lại: loại bỏ thông tin scale không cần để giữ giá trị toán học. Quy định scale hoặc format riêng.
5. **Tưởng `toPlainString()` đổi scale của đối tượng.** Nó chỉ sinh chuỗi; `x.scale()` không đổi.
6. **Dùng `new BigDecimal(0.1)` để thử nghiệm thập phân và rồi đổ lỗi cho `stripTrailingZeros()`.** `double` nhị phân thường không biểu diễn chính xác `0.1`. Khi muốn đúng literal thập phân, dùng `new BigDecimal("0.1")`; khi nhận sẵn `double`, cân nhắc `BigDecimal.valueOf(double)` theo hợp đồng đầu vào.

## 9. Tự kiểm tra

Xét đoạn mã:

~~~java
BigDecimal x = new BigDecimal("1200.00");
BigDecimal y = x.stripTrailingZeros();
~~~

Bạn hãy trả lời:

1. `x.unscaledValue()` và `x.scale()` bằng bao nhiêu?
2. `y.unscaledValue()`, `y.scale()`, `y.toString()` và `y.toPlainString()` là gì?
3. `x.equals(y)` và `x.compareTo(y)` cho kết quả gì?
4. Nếu một API yêu cầu đúng hai chữ số sau dấu thập phân, bạn nên xử lý `y` thế nào?

**Đáp án:** `x` có `unscaledValue = 120000` và `scale = 2`; `y` có `unscaledValue = 12`, `scale = -2`, `toString() = "1.2E+3"` và `toPlainString() = "1200"`. `equals` là `false`, `compareTo` là `0`. Để biểu diễn hai chữ số thập phân, dùng `y.setScale(2, RoundingMode.UNNECESSARY)` và `toPlainString()` khi xuất chuỗi, cho `"1200.00"`.

Điểm cốt lõi: `stripTrailingZeros()` giữ nguyên **giá trị** nhưng có thể thay đổi **biểu diễn**. Khi biểu diễn tối giản của một số chứa lũy thừa 10 ở phần nguyên, `scale` âm là kết quả chính xác và được hỗ trợ đầy đủ bởi `BigDecimal`.
