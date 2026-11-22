# Phân biệt precision và scale của BigDecimal

## 1. Hai câu hỏi khác nhau về cùng một số

Khi yêu cầu “giữ hai chữ số sau dấu thập phân”, ta đang nói đến **scale**. Khi yêu cầu “giữ tổng cộng bốn chữ số có nghĩa”, ta đang nói đến **precision**. Hai yêu cầu này có thể tạo ra hai kết quả khác nhau từ cùng một giá trị.

Ví dụ, từ `123.456` với cách làm tròn `HALF_UP`:

- Giữ scale bằng 2 → `123.46`.
- Giữ precision tối đa bằng 4 → `123.5`.

`BigDecimal` lưu số thập phân bằng một số nguyên chưa đặt dấu thập phân (`unscaledValue`) và một số nguyên `scale`. Giá trị được xác định bằng:

```text
giá trị = unscaledValue × 10^(-scale)
```

`precision()` là số chữ số thập phân của trị tuyệt đối `unscaledValue`; riêng số 0 có precision bằng 1. `scale()` xác định vị trí dấu thập phân so với số nguyên đó.

Đây là thông tin của **biểu diễn hiện tại**, không phải phép đo độ chính xác của dữ liệu ngoài đời. Đọc `"1.2300"` vào `BigDecimal` không tự chứng minh rằng một thiết bị đo đã đo chính xác đến bốn chữ số sau dấu thập phân.

## 2. Cách đếm bằng ví dụ

Các hàng sau giả sử tạo đối tượng bằng `new BigDecimal(chuỗi)`:

| Chuỗi đầu vào | unscaledValue | precision | scale | Cách hiểu |
| --- | ---: | ---: | ---: | --- |
| `"123.45"` | 12345 | 5 | 2 | Năm chữ số được lưu, dấu thập phân lùi hai vị trí |
| `"123.4500"` | 1234500 | 7 | 4 | Các số 0 cuối được giữ trong biểu diễn |
| `"0.00120"` | 120 | 3 | 5 | Các số 0 đầu không làm tăng precision |
| `"-12.30"` | -1230 | 4 | 2 | Dấu âm không phải chữ số |
| `"0"` | 0 | 1 | 0 | Quy tắc riêng: precision của số 0 là 1 |
| `"0.000"` | 0 | 1 | 3 | Giá trị 0 vẫn có thể có scale khác nhau |
| `"1000"` | 1000 | 4 | 0 | Biểu diễn thông thường của một số nguyên |
| `"1E+3"` | 1 | 1 | -3 | `1 × 10^3 = 1000` |
| `"1.23E+4"` | 123 | 3 | -2 | `123 × 10^2 = 12300` |

Với scale không âm, có thể hình dung scale là số vị trí sau dấu thập phân, kể cả các vị trí có giá trị 0. Tuy nhiên, **scale có thể âm**, nên định nghĩa “scale luôn là số chữ số sau dấu chấm” chưa đầy đủ.

Đừng dùng công thức `precision - scale` một cách máy móc để đếm số chữ số phần nguyên trên mọi đầu vào. Với `0.00120`, phép trừ là `3 - 5 = -2`; đây không phải “âm hai chữ số phần nguyên”. Hãy quay về công thức biểu diễn để giải thích trường hợp nhỏ hơn 1 hoặc số 0.

## 3. Precision của đối tượng và giới hạn precision của MathContext

`value.precision()` chỉ **đọc số chữ số đang được lưu**. Nó không cấu hình cho phép tính tiếp theo.

`new MathContext(4, RoundingMode.HALF_UP)` tạo chính sách tính toán giữ tối đa bốn chữ số có nghĩa khi cần làm tròn. Muốn chính sách có tác dụng, phải truyền nó vào phép toán hoặc gọi `round(mc)`.

Ví dụ minh họa trong một phương thức:

```java
BigDecimal value = new BigDecimal("123.456");

BigDecimal fixedFraction =
        value.setScale(2, RoundingMode.HALF_UP); // 123.46

BigDecimal limitedDigits =
        value.round(new MathContext(4, RoundingMode.HALF_UP)); // 123.5
```

`fixedFraction` có precision bằng 5, dù scale bằng 2. `limitedDigits` có scale bằng 1, dù giới hạn precision bằng 4.

Precision trong `MathContext` không bắt buộc thêm số 0 cho đủ số chữ số. Chẳng hạn `new BigDecimal("1.2").round(new MathContext(4))` vẫn biểu diễn `1.2`. Precision bằng 0 trong `MathContext` mang nghĩa không giới hạn precision, không phải “giữ 0 chữ số”. Điều này khác với `BigDecimal.precision()`, vốn trả ít nhất 1.

## 4. setScale, làm tròn và tính bất biến

`setScale` trả về một `BigDecimal` theo scale được yêu cầu:

- Tăng scale có thể thêm các số 0 cuối mà không đổi giá trị số: `12.3 → 12.3000`.
- Giảm scale có thể chỉ bỏ số 0: `12.3000 → 12.30`, không cần làm tròn giá trị.
- Nếu phải bỏ chữ số khác 0, cần một chính sách làm tròn hoặc phép gọi sẽ thất bại khi yêu cầu kết quả chính xác.

```java
BigDecimal a = new BigDecimal("12.3000").setScale(2); // 12.30
BigDecimal b = new BigDecimal("12.345")
        .setScale(2, RoundingMode.HALF_UP);          // 12.35
BigDecimal c = new BigDecimal("12.345")
        .setScale(2, RoundingMode.UNNECESSARY);      // ArithmeticException
```

Đây là các biểu thức minh họa độc lập; dòng cuối chủ ý ném ngoại lệ. `UNNECESSARY` hữu ích khi hợp đồng dữ liệu đòi hỏi không được thay đổi giá trị để ép scale. Nó vẫn cho phép bỏ các số 0 dư.

`BigDecimal` bất biến. Phải sử dụng giá trị trả về:

```java
BigDecimal price = new BigDecimal("12.345");
price = price.setScale(2, RoundingMode.HALF_UP);
```

Nếu chỉ gọi `price.setScale(...)` rồi bỏ kết quả, biến `price` vẫn tham chiếu biểu diễn cũ. Chọn `HALF_UP`, `HALF_EVEN` hay cách khác theo quy tắc của bài toán; “tiền tệ” không tự xác định một cách làm tròn duy nhất. Dùng enum `RoundingMode` trong mã hiện tại.

## 5. Cùng giá trị số vẫn có thể khác scale

`2.0` và `2.00` bằng nhau về giá trị số, nhưng khác biểu diễn:

```java
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = new BigDecimal("2.00");

System.out.println(x.compareTo(y)); // 0
System.out.println(x.equals(y));    // false
```

`compareTo` so sánh giá trị số. `equals` xét cả giá trị và scale. Vì vậy, việc thay scale có thể ảnh hưởng kiểm tra bằng nhau, khóa trong `HashMap` hoặc phần tử trong `HashSet`. Cần xác định ứng dụng muốn so sánh giá trị số hay biểu diễn.

`stripTrailingZeros()` bỏ các số 0 cuối không cần thiết mà giữ nguyên giá trị số. Kết quả có thể có scale âm: `new BigDecimal("1000.00").stripTrailingZeros()` có precision bằng 1, scale bằng -3 và `toString()` là `"1E+3"`. Với mọi giá trị bằng 0, phương thức này trả biểu diễn `BigDecimal.ZERO`, scale bằng 0.

`toPlainString()` tránh ký pháp số mũ khi xuất chuỗi; nó không đổi precision hoặc scale của đối tượng. Đừng suy ngược precision chỉ từ số ký tự trong chuỗi xuất ra: biểu diễn scale -3 có thể in thành `"1000"` bằng phương thức này.

## 6. Chương trình kiểm chứng đầy đủ

Lưu thành `PrecisionScaleDemo.java`. Chương trình dùng API có trên Java 17 trở lên.

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class PrecisionScaleDemo {
    private static void show(String label, BigDecimal value) {
        System.out.printf("%s: value=%s, unscaled=%s, precision=%d, scale=%d%n",
                label, value.toPlainString(), value.unscaledValue(),
                value.precision(), value.scale());
    }

    public static void main(String[] args) {
        show("a", new BigDecimal("123.4500"));
        show("b", new BigDecimal("0.00120"));
        show("zero", new BigDecimal("0.000"));
        show("power", new BigDecimal("1E+3"));

        BigDecimal amount = new BigDecimal("123.456");
        show("scale2", amount.setScale(2, RoundingMode.HALF_UP));
        show("precision4", amount.round(new MathContext(4, RoundingMode.HALF_UP)));
        show("padded", new BigDecimal("12.3").setScale(4));
        show("stripped", new BigDecimal("1000.00").stripTrailingZeros());

        BigDecimal x = new BigDecimal("2.0");
        BigDecimal y = new BigDecimal("2.00");
        System.out.println("compareTo=" + x.compareTo(y));
        System.out.println("equals=" + x.equals(y));

        try {
            new BigDecimal("12.345").setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            System.out.println("scale2 exact: rounding required");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 PrecisionScaleDemo.java
java PrecisionScaleDemo
```

Kết quả:

```text
a: value=123.4500, unscaled=1234500, precision=7, scale=4
b: value=0.00120, unscaled=120, precision=3, scale=5
zero: value=0.000, unscaled=0, precision=1, scale=3
power: value=1000, unscaled=1, precision=1, scale=-3
scale2: value=123.46, unscaled=12346, precision=5, scale=2
precision4: value=123.5, unscaled=1235, precision=4, scale=1
padded: value=12.3000, unscaled=123000, precision=6, scale=4
stripped: value=1000, unscaled=1, precision=1, scale=-3
compareTo=0
equals=false
scale2 exact: rounding required
```

Hai dòng `power` và `stripped` đều in giá trị `1000`, nhưng precision chỉ bằng 1. Dòng `padded` cho thấy thêm số 0 làm precision tăng từ 3 lên 6 mà không tăng giá trị số.

## 7. Chọn đúng yêu cầu và tránh nhầm lẫn

| Yêu cầu | Công cụ phù hợp | Điều cần kiểm tra |
| --- | --- | --- |
| Đọc đặc điểm biểu diễn hiện tại | `precision()`, `scale()`, `unscaledValue()` | Không nhầm phương thức đọc với chính sách làm tròn |
| Chuẩn hóa hai vị trí thập phân | `setScale(2, roundingMode)` | Có cho phép đổi giá trị do làm tròn không? |
| Giới hạn tổng số chữ số có nghĩa | `MathContext` truyền vào phép toán hoặc `round` | Không cố định số vị trí thập phân |
| Kiểm tra cùng giá trị số | `compareTo(...) == 0` | `equals` có thêm yêu cầu về scale |
| Hiển thị không dùng số mũ | `toPlainString()` | Chuỗi hiển thị không thay đổi biểu diễn bên trong |

Một số lỗi thường gặp:

- **Đếm dấu âm, dấu chấm hoặc các số 0 đầu vào precision.** Hãy đếm chữ số của trị tuyệt đối `unscaledValue`; số 0 là trường hợp riêng.
- **Cho rằng precision bằng số chữ số sau dấu thập phân.** `123.4500` có precision 7 nhưng scale 4.
- **Cho rằng scale chỉ có thể không âm.** Dạng số mũ và `stripTrailingZeros` có thể tạo scale âm.
- **Dùng `new BigDecimal(0.1)` khi định nhập chính xác chuỗi thập phân `0.1`.** Giá trị `double` đã mang biểu diễn nhị phân xấp xỉ; hãy dùng `new BigDecimal("0.1")` khi nguồn dữ liệu là số thập phân dạng văn bản. `BigDecimal.valueOf(double)` có quy tắc chuyển qua chuỗi của `double`, nhưng không phục hồi được các chữ số đã mất trước đó.
- **Giả định các phép toán tự giữ hai chữ số thập phân.** Không có chính sách scale toàn cục gắn vĩnh viễn vào một `BigDecimal`; phải áp dụng yêu cầu ở những bước tính toán hoặc đầu ra mà bài toán quy định.

## 8. Tự kiểm tra

1. `new BigDecimal("0.0100")` có precision và scale bao nhiêu?
2. `new BigDecimal("999.9").round(new MathContext(3, RoundingMode.HALF_UP))` có giá trị, precision và scale thế nào?
3. `new BigDecimal("5.00").setScale(1, RoundingMode.UNNECESSARY)` có ném ngoại lệ không?

Đáp án:

1. `unscaledValue = 100`, precision = 3, scale = 4.
2. Giá trị số là 1000, biểu diễn `1.00E+3`, precision = 3, scale = -1. Làm tròn có thể phát sinh nhớ sang chữ số đầu và làm thay đổi scale.
3. Không. Kết quả là `5.0`; chỉ bỏ số 0 nên giá trị không đổi.

Tham khảo hợp đồng API: [BigDecimal trong Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html), đặc biệt `precision`, `scale`, `setScale`, `round` và `stripTrailingZeros`.
