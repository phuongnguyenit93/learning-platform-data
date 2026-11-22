# BigDecimal.ulp() trong Java: đơn vị tại chữ số cuối cùng

## 1. ulp là gì?

`BigDecimal` biểu diễn số thập phân với độ chính xác tùy ý, nhưng mỗi đối tượng có một **scale** cụ thể. Khi cần biết giá trị của một đơn vị tại *hàng thập phân cuối cùng trong biểu diễn hiện tại*, dùng phương thức:

```java
public BigDecimal ulp()
```

**ULP** viết tắt của *unit in the last place* (đơn vị tại chữ số cuối). Với `BigDecimal`, kết quả là một `BigDecimal` dương, có cùng `scale` với đối tượng gốc. Giá trị số học luôn bằng:

\[
\operatorname{ulp}(x)=10^{-x.\operatorname{scale}()}
\]

Ví dụ, `123.45` có `scale = 2` nên `ulp() = 0.01`; `123.4500` có `scale = 4` nên `ulp() = 0.0001`. Chúng bằng nhau về **giá trị số học**, nhưng chữ số cuối của hai biểu diễn nằm ở hai hàng thập phân khác nhau.

**Phân biệt ngay từ đầu:** `ulp()` cho biết đơn vị ở vị trí chữ số cuối **đang được lưu**. Nó không tự đo sai số tính toán, không làm tròn, và không xác định độ chính xác mà nghiệp vụ cần.

## 2. Vì sao scale quyết định ulp?

Mỗi `BigDecimal` có các thành phần:
- `unscaledValue()` là phần nguyên chưa đặt dấu thập phân (kiểu `BigInteger`).
- `scale()` là số nguyên mô tả vị trí dấu thập phân.
- `precision()` là số chữ số của phần nguyên chưa đặt dấu thập phân; precision của số 0 bằng 1.

Công thức biểu diễn:

\[
x = \operatorname{unscaledValue}(x) \times 10^{-\operatorname{scale}(x)}
\]

Ví dụ, `new BigDecimal("123.4500")` có phần không scale `1234500`, `scale = 4`, `precision = 7`. Nếu tăng phần không scale từ 1234500 lên 1234501 mà giữ scale, giá trị tăng 0.0001, đúng bằng `ulp()`.

Đừng nhầm **scale** (vị trí dấu thập phân) và **precision** (số chữ số có nghĩa của phần không scale). `ulp()` phụ thuộc **scale**, không trực tiếp phụ thuộc precision:

| Chuỗi tạo `BigDecimal` | `scale()` | `precision()` | `ulp()` |
| --- | ---: | ---: | ---: |
| `"123.45"` | 2 | 5 | `0.01` |
| `"123.4500"` | 4 | 7 | `0.0001` |
| `"1"` | 0 | 1 | `1` |
| `"0.00"` | 2 | 1 | `0.01` |
| `"-7.20"` | 2 | 3 | `0.01` |
| `"6E+2"` | -2 | 1 | `1E+2` |

Scale có thể **âm**: `6E+2` biểu thị 600 với phần không scale là 6, `scale = -2`, nên ulp bằng 100. Vì thế, `ulp()` không nhất thiết nhỏ hơn 1.

## 3. Hành vi được Java quy định

- Phương thức trả về **`BigDecimal`**, không phải `double`, và kết quả luôn dương.
- Kết quả giữ **đúng scale** của giá trị nhận lời gọi. Giá trị tương đương `BigDecimal.valueOf(1L, x.scale())` về cả số học lẫn scale.
- Với số 0, ulp vẫn là 1 ở scale của chính số 0 đó; không có ngoại lệ `ulp() = 0`.
- `ulp()` **không nhận `MathContext`**, không thay đổi giá trị gốc và không phải thao tác làm tròn. `BigDecimal` là bất biến.

Các số 0 dưới đây bằng nhau về mặt số học nhưng trả kết quả khác:

```java
new BigDecimal("0").ulp();      // 1, scale = 0
new BigDecimal("0.00").ulp();   // 0.01, scale = 2
new BigDecimal("0E+2").ulp();   // 1E+2, scale = -2
```

Java mô tả ulp của số khác 0 theo đơn vị ở chữ số cuối của biểu diễn và mô tả ulp của số 0 là một đơn vị với cùng scale. Đừng diễn giải `ulp()` thành khoảng cách giữa hai số `BigDecimal` gần nhau nhất một cách tuyệt đối: `BigDecimal` không bị bó vào một định dạng dấu chấm động nhị phân cố định.

## 4. Chương trình Java 17 hoàn chỉnh

Lưu tệp **`BigDecimalUlpDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalUlpDemo {
    public static void main(String[] args) {
        show("A", new BigDecimal("123.45"));
        show("B", new BigDecimal("123.4500"));
        show("C", new BigDecimal("-7.20"));
        show("D", new BigDecimal("0.00"));
        show("E", new BigDecimal("6E+2"));

        BigDecimal rounded = new BigDecimal("123.456")
                .round(new MathContext(4, RoundingMode.HALF_UP));
        show("Rounded", rounded);

        BigDecimal original = new BigDecimal("100.00");
        show("Original", original);
        show("Normalized", original.stripTrailingZeros());
    }

    private static void show(String label, BigDecimal number) {
        BigDecimal unit = number.ulp();
        System.out.println(label + ": value=" + number
                + ", scale=" + number.scale()
                + ", ulp=" + unit
                + ", ulpScale=" + unit.scale());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac BigDecimalUlpDemo.java
java BigDecimalUlpDemo
```

**Kết quả chính xác** (chương trình đã được biên dịch với `javac --release 17` và chạy kiểm chứng):

```text
A: value=123.45, scale=2, ulp=0.01, ulpScale=2
B: value=123.4500, scale=4, ulp=0.0001, ulpScale=4
C: value=-7.20, scale=2, ulp=0.01, ulpScale=2
D: value=0.00, scale=2, ulp=0.01, ulpScale=2
E: value=6E+2, scale=-2, ulp=1E+2, ulpScale=-2
Rounded: value=123.5, scale=1, ulp=0.1, ulpScale=1
Original: value=100.00, scale=2, ulp=0.01, ulpScale=2
Normalized: value=1E+2, scale=-2, ulp=1E+2, ulpScale=-2
```

Giải thích kết quả:
1. `A` và `B` cùng giá trị 123.45, nhưng `B` có thêm hai chữ số 0 ở phần thập phân nên ulp nhỏ hơn 100 lần.
2. `C` âm nhưng ulp dương. Dấu của số không quyết định ulp.
3. `D` là số 0, vẫn mang scale 2 và ulp 0.01.
4. `E` có scale âm nên ulp là 100 (in ra dạng khoa học `1E+2`).
5. `Rounded` dùng 4 chữ số có nghĩa, làm tròn thành 123.5, scale 1, ulp 0.1.
6. `Normalized` bỏ các số 0 tận cùng của 100.00, thay scale 2 bằng -2; giá trị vẫn là 100 nhưng ulp đổi từ 0.01 thành 100.

## 5. Quan hệ với làm tròn và thay đổi biểu diễn

### 5.1. setScale có thể thay đổi ulp và giá trị

`setScale(newScale, roundingMode)` trả về một biểu diễn với scale được yêu cầu. Khi giảm scale, nếu cần bỏ chữ số có nghĩa, `RoundingMode` quyết định cách làm tròn:

```java
BigDecimal original = new BigDecimal("1.236");
BigDecimal rounded = original.setScale(2, RoundingMode.HALF_UP);
// original = 1.236; original.ulp() = 0.001
// rounded  = 1.24;  rounded.ulp()  = 0.01
```

ULP tăng từ 0.001 lên 0.01 do scale giảm. **Sai số thực tế** của phép làm tròn là `|1.24 - 1.236| = 0.004`, không phải 0.01. Muốn đo sai số, cần so sánh với giá trị tham chiếu chính xác (nếu có).

Tăng scale cũng đổi ulp **dù không đổi giá trị số học**:

```java
BigDecimal x = new BigDecimal("2.5");
BigDecimal y = x.setScale(3);
// x = 2.5   -> ulp = 0.1
// y = 2.500 -> ulp = 0.001
// x.compareTo(y) == 0
```

### 5.2. MathContext: precision không phải scale

`MathContext(4, RoundingMode.HALF_UP)` yêu cầu tối đa 4 chữ số có nghĩa khi thực hiện một phép toán với context. Nó không hứa rằng ulp của mọi kết quả đều là 0.0001. Ví dụ sau (đoạn minh họa được đặt trong phương thức Java có thể chạy, đã import `java.math.*` hoặc các lớp tương ứng):

```java
BigDecimal a = new BigDecimal("123.456")
        .round(new MathContext(4, RoundingMode.HALF_UP));
// a = 123.5; scale = 1; ulp = 0.1

BigDecimal b = BigDecimal.ONE.divide(
        new BigDecimal("3"),
        new MathContext(4, RoundingMode.HALF_UP));
// b = 0.3333; scale = 4; ulp = 0.0001
```

Cùng precision 4 nhưng ulp khác nhau vì **scale thực tế** của kết quả khác nhau. Một `MathContext` chỉ có hiệu lực với thao tác mà bạn truyền nó vào (hoặc khi gọi phương thức `round(mc)`); nó không tự thay đổi tất cả đối tượng `BigDecimal`.

### 5.3. stripTrailingZeros có thể làm ulp đổi mạnh

`stripTrailingZeros()` giữ nguyên giá trị số học nhưng bỏ số 0 tận cùng khỏi biểu diễn, đôi khi tạo scale âm:

```java
BigDecimal x = new BigDecimal("100.00");
BigDecimal y = x.stripTrailingZeros();
// x.compareTo(y) == 0        // true: cùng giá trị số học
// x.equals(y)                // false: khác scale
// x.ulp().equals(y.ulp())    // false: 0.01 khác 1E+2
```

Với số 0, `stripTrailingZeros()` trả `BigDecimal.ZERO` ở scale 0. Vì vậy `new BigDecimal("0.000").ulp()` là 0.001, còn ulp của kết quả sau chuẩn hóa là 1.

Nếu số chữ số thập phân mang ý nghĩa nghiệp vụ (chẳng hạn giá được công bố với 2 chữ số), cần cân nhắc trước khi gọi `stripTrailingZeros()`.

## 6. Ứng dụng thực tế

**Quan sát độ chi tiết của biểu diễn:** `new BigDecimal("19.990").ulp()` trả 0.001, thể hiện hàng thập phân cuối cùng hiện có trong đối tượng. Nó không nói đơn vị tiền tệ nhỏ nhất là bao nhiêu.

**Theo dõi pipeline xử lý dữ liệu:** ghi `value`, `scale()` và `ulp()` trước/sau `setScale()`, `round()` hoặc `stripTrailingZeros()` để phát hiện bước thay đổi mức chi tiết.

**Phân tích kết quả từ phép tính có MathContext:** `ulp()` giúp biết hàng thập phân cuối cùng còn được giữ sau thao tác. Tuy nhiên, khi muốn đánh giá độ chính xác của thuật toán, cần thêm định nghĩa lỗi và giá trị tham chiếu.

Ví dụ nghiệp vụ yêu cầu số tiền có 2 chữ số thập phân:

```java
BigDecimal amount = new BigDecimal("19.995");
BigDecimal payable = amount.setScale(2, RoundingMode.HALF_UP);
// payable = 20.00; payable.ulp() = 0.01
```

Chính `setScale(2, HALF_UP)` thực hiện quy tắc làm tròn; `ulp()` chỉ mô tả biểu diễn sau đó. ULP không tự đặt ra quy tắc tiền tệ, ngưỡng so sánh hoặc mức sai số có thể chấp nhận.

## 7. So sánh với các API liên quan

| API / khái niệm | Chức năng | Cạm bẫy |
| --- | --- | --- |
| `x.ulp()` | Đơn vị tại chữ số cuối theo scale của `x` | Không đo sai số tính toán. |
| `x.scale()` | Vị trí dấu thập phân | Có thể âm, 0 hoặc dương. |
| `x.precision()` | Số chữ số trong phần unscaled | Không đồng nghĩa số chữ số sau dấu phẩy. |
| `x.setScale(...)` | Đặt scale, có thể làm tròn | Có thể đổi giá trị số học. |
| `x.round(mc)` | Làm tròn theo số chữ số có nghĩa | Scale kết quả phụ thuộc độ lớn. |
| `x.stripTrailingZeros()` | Bỏ số 0 dư trong biểu diễn | Có thể đổi scale/ulp dù số học không đổi. |
| `Math.ulp(double)` | Bước biểu diễn số chấm động nhị phân `double` | Khác hệ cơ số và ngữ nghĩa với `BigDecimal.ulp()`. |

`Math.ulp(1.0)` với `double` xấp xỉ `2.22e-16`, nhưng `new BigDecimal("1.0").ulp()` bằng `0.1`. Không dùng kết quả của hai API thay thế trực tiếp cho nhau.

## 8. Lỗi thường gặp

1. **Coi ulp là sai số:** `ulp() = 0.01` không chứng minh phép tính sai 0.01 hoặc không quá 0.005. Hãy tính lỗi từ phép toán, quy tắc làm tròn và giá trị tham chiếu.
2. **Coi cùng giá trị thì cùng ulp:** `1.0` và `1.000` có cùng giá trị số học nhưng khác scale. Hãy kiểm tra `scale()`.
3. **Dùng precision để suy ra ulp:** `precision = 4` vẫn có thể cho ulp 0.1 hoặc 0.0001. Hãy xem scale của chính kết quả.
4. **Bỏ qua số 0 hoặc scale âm:** `0.00` có ulp 0.01; `6E+2` có ulp 100.
5. **Gọi stripTrailingZeros rồi kỳ vọng ulp giữ nguyên:** scale có thể đổi từ dương sang âm. Đừng bỏ các số 0 có ý nghĩa nghiệp vụ.
6. **Khởi tạo bằng double theo cách không mong muốn:** `new BigDecimal(0.1)` biểu diễn chính xác giá trị nhị phân của `double 0.1`, không đúng 0.1 thập phân, nên scale/ulp có thể bất ngờ. Khi có dữ liệu thập phân rõ ràng, ưu tiên `new BigDecimal("0.1")` hoặc cân nhắc `BigDecimal.valueOf(0.1)`.
7. **Dùng ulp làm epsilon toàn cục để so sánh:** scale có thể được thêm hoặc bớt số 0 mà số học không đổi. Ngưỡng dung sai phải do bài toán quy định.

## 9. Tự kiểm tra kiến thức

**Câu 1.** `new BigDecimal("0.0000").ulp()` bằng bao nhiêu?  
**Đáp án:** 0.0001 vì scale bằng 4, dù giá trị là 0.

**Câu 2.** Vì sao `new BigDecimal("5.00").ulp()` khác `new BigDecimal("5").ulp()`?  
**Đáp án:** đối tượng đầu có scale 2 nên ulp 0.01; đối tượng sau có scale 0 nên ulp 1.

**Câu 3.** `new BigDecimal("600.0").stripTrailingZeros()` có thể trở thành `6E+2`. ULP trước/sau là gì?  
**Đáp án:** trước là 0.1 (scale 1), sau là `1E+2` (scale -2); giá trị số học vẫn là 600.

**Câu 4.** Có thể suy ra từ `ulp() = 0.01` rằng lỗi của một phép chia không quá 0.005 không?  
**Đáp án:** không. ULP mô tả vị trí chữ số cuối, còn giới hạn lỗi phụ thuộc thuật toán và quy tắc làm tròn.

## 10. Ghi nhớ

- Với mọi `BigDecimal x`, **`x.ulp()` có giá trị `10^(-x.scale())` và cùng scale với `x`**.
- Scale là thuộc tính của **biểu diễn**, nên các đối tượng cùng giá trị số học có thể có ulp khác nhau.
- `ulp()` hỗ trợ giải thích dữ liệu và kết quả phép tính. Kiểm soát độ chính xác cần chính sách làm tròn và định nghĩa sai số riêng.

Tài liệu chính thức: [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html) và [Java SE 17 — MathContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html).
