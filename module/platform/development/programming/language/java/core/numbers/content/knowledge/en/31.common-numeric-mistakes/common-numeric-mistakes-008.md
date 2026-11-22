# Chia BigDecimal không chỉ định chính sách cho kết quả vô hạn tuần hoàn

Trong Java, `BigDecimal` biểu diễn số thập phân bằng hệ số nguyên (`unscaledValue`) và `scale`: giá trị bằng `unscaledValue × 10^(-scale)`. Nó hỗ trợ phép toán decimal chính xác nhưng **không thể chứa vô hạn chữ số thập phân trong một đối tượng hữu hạn**. Do đó phép chia exact như `1 / 3` là trường hợp cần hiểu rõ.

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

BigDecimal result = one.divide(three);
// Ném ArithmeticException: thương không có khai triển thập phân hữu hạn
```

Mặc dù `1` và `3` đều là số nguyên, thương toán học `1/3 = 0.333333…` không có biểu diễn thập phân hữu hạn. `BigDecimal.divide(BigDecimal)` **không tự chọn** số chữ số thập phân, cách làm tròn hay độ chính xác. Nếu phải làm tròn, lập trình viên cần truyền **chính sách tường minh**, phù hợp yêu cầu nghiệp vụ.

## 1. Phân biệt chia chính xác với chia có làm tròn

Hai phép chia này trả kết quả khác nhau về ý nghĩa:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

one.divide(three); // ArithmeticException: yêu cầu thương chính xác
one.divide(three, 2, RoundingMode.HALF_UP); // 0.33: thương đã làm tròn
```

Lời gọi `divide(three, 2, HALF_UP)` **không làm cho `1/3` trở thành `0.33` về mặt toán học**; đó là giá trị gần đúng được làm tròn theo scale 2 và mode `HALF_UP`. Khi tính tiếp, cần nhận biết rằng thông tin đã bị bỏ đi ở bước chia.

| Tình huống | Dùng `divide(divisor)` | Vì sao? |
|---|---|---|
| `1 / 2` | `0.5` | Thương thập phân hữu hạn |
| `1 / 8` | `0.125` | Thương thập phân hữu hạn |
| `1 / 40` | `0.025` | Thương thập phân hữu hạn |
| `3 / 6` | `0.5` | Rút gọn thành `1/2` |
| `1 / 3` | Ném `ArithmeticException` | `0.333333…` |
| `1 / 6` | Ném `ArithmeticException` | `0.166666…` |
| `1 / 7` | Ném `ArithmeticException` | `0.142857142857…` |

**Quan trọng:** `ArithmeticException` là ngoại lệ của một phép tính không thể đáp ứng yêu cầu exact, không phải bằng chứng rằng dữ liệu đầu vào “không phải số” hoặc rằng `BigDecimal` bị lỗi.

## 2. Tại sao có thương hữu hạn và thương vô hạn?

Với phân số hữu tỉ `p/q` sau khi **rút gọn tối giản** và chọn `q > 0`:

- Khai triển thập phân **kết thúc** nếu mẫu `q` chỉ có thừa số nguyên tố `2` và/hoặc `5`, tức `q = 2^a × 5^b` với `a,b ≥ 0`.
- Nếu mẫu tối giản còn thừa số khác như `3` hoặc `7`, khai triển thập phân vô hạn tuần hoàn.
- Phải xét mẫu **sau rút gọn**, không phải mẫu ban đầu: `3/6 = 1/2` nên chia exact được.

Ví dụ `1/8 = 1/(2³) = 0.125`; `1/40 = 1/(2³ × 5) = 0.025`. Trong khi đó `1/3` không thể biến thành phân số có mẫu là một lũy thừa của 10.

Một giá trị `BigDecimal` chỉ mang hệ số nguyên hữu hạn và scale nguyên; do đó nếu thương cần dãy thập phân vô hạn, yêu cầu “trả chính xác toàn bộ thương bằng một BigDecimal” là bất khả thi. Java từ chối thay vì âm thầm cắt hoặc làm tròn.

Quy tắc toán học này dành cho thương của hai số hữu tỉ. Không cần tự phân tích thừa số nguyên tố trong ứng dụng thông thường chỉ để chia: chọn API phù hợp với hợp đồng phép tính là đủ.

## 3. Năm cách chia cần phân biệt

| API | Ý nghĩa | Thương tuần hoàn |
|---|---|---|
| `a.divide(b)` | Chia chính xác, không cho phép mất thông tin | `ArithmeticException` |
| `a.divide(b, scale, mode)` | Làm tròn thương theo **scale đích** chỉ định | Trả kết quả đã làm tròn |
| `a.divide(b, mode)` | Dùng **scale của `a`** làm scale kết quả | Trả kết quả đã làm tròn tại scale đó |
| `a.divide(b, mathContext)` | Điều khiển **precision (chữ số có nghĩa)** và mode | Có thể trả kết quả làm tròn với precision dương |
| `a.divide(b, MathContext.UNLIMITED)` | Không giới hạn precision, yêu cầu exact | `ArithmeticException` |

Tất cả đều có thể ném `ArithmeticException` khi **divisor bằng 0**. Khi `RoundingMode.UNNECESSARY` được dùng và không thể biểu diễn thương tại giới hạn đã chọn mà giữ nguyên giá trị, phép chia cũng ném ngoại lệ.

### 3.1. Exact: `divide(divisor)`

```java
BigDecimal a = new BigDecimal("1.00");
BigDecimal b = new BigDecimal("8");

BigDecimal exact = a.divide(b); // 0.125
```

Thương có thể mang scale **khác** scale của dividend. `1.00` có scale 2, nhưng kết quả chính xác `0.125` có scale 3. Scale đầu vào **không** tự trở thành giới hạn làm tròn của `divide(divisor)`.

### 3.2. Chia theo scale đích và mode: `divide(divisor, scale, roundingMode)`

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

BigDecimal third = one.divide(
        three, 2, RoundingMode.HALF_UP); // 0.33

BigDecimal twoThirds = new BigDecimal("2").divide(
        three, 2, RoundingMode.HALF_UP); // 0.67

BigDecimal oneEighth = one.divide(
        new BigDecimal("8"), 2, RoundingMode.HALF_UP); // 0.13
```

Ở đây `scale=2` yêu cầu kết quả có đúng hai vị trí thập phân. Ngay cả `1/8 = 0.125`, vốn có thương decimal exact, cũng phải làm tròn thành `0.13` vì **scale đích** không đủ biểu diễn chính xác 0.125.

Chú ý phương thức `setScale(2, HALF_UP)` sau khi có thương exact có thể là một lựa chọn khi thương exact kết thúc, nhưng **không** sửa được tình huống `one.divide(three)` đã ném ngoại lệ trước khi đến bước `setScale`. Chỉ định chính sách **ngay tại phép chia** nếu biết thương có thể tuần hoàn.

### 3.3. Chia chỉ với RoundingMode: scale đầu vào có thể gây bất ngờ

```java
BigDecimal three = new BigDecimal("3");

System.out.println(
        new BigDecimal("1").divide(three, RoundingMode.HALF_UP)
); // 0

System.out.println(
        new BigDecimal("1.00").divide(three, RoundingMode.HALF_UP)
); // 0.33
```

Hai dividend có **cùng giá trị toán học**, nhưng scale lần lượt là 0 và 2. Overload `divide(divisor, roundingMode)` trả thương với scale bằng **scale của dividend**. Nếu data layer cung cấp `1` thay vì `1.00`, kết quả có thể thay đổi không mong đợi.

Đối với quy tắc nghiệp vụ cần scale cố định, **truyền scale rõ ràng** thay vì phụ thuộc biểu diễn đầu vào.

### 3.4. Chia với MathContext: precision không phải scale

```java
MathContext context =
        new MathContext(5, RoundingMode.HALF_UP);

BigDecimal third = BigDecimal.ONE.divide(
        new BigDecimal("3"), context); // 0.33333

BigDecimal tenSixths = new BigDecimal("10").divide(
        new BigDecimal("6"),
        new MathContext(3, RoundingMode.HALF_UP)); // 1.67
```

`MathContext(5, HALF_UP)` yêu cầu tối đa năm **chữ số có nghĩa** trong kết quả, không phải năm chữ số sau dấu trong mọi trường hợp. Precision kiểm soát một khía cạnh khác scale. Khi độ lớn thay đổi, số chữ số sau dấu cần để đạt precision nhất định cũng thay đổi.

`MathContext` có ích trong những thuật toán kiểm soát precision theo chữ số có nghĩa. Nếu ứng dụng cần kết quả ở đơn vị thập phân cụ thể, ví dụ chính xác hai vị trí để kết toán theo chính sách đã duyệt, overload có scale tường minh thường trực tiếp hơn.

### 3.5. MathContext.UNLIMITED và mode UNNECESSARY

```java
BigDecimal.ONE.divide(
        new BigDecimal("3"), MathContext.UNLIMITED);
// ArithmeticException

BigDecimal.ONE.divide(
        new BigDecimal("3"), 2, RoundingMode.UNNECESSARY);
// ArithmeticException
```

`MathContext.UNLIMITED` có precision 0, nghĩa là **không giới hạn số chữ số có nghĩa**, nhưng không đồng nghĩa “tự sinh vô hạn chữ số cho phép chia tuần hoàn”. Phép chia vẫn đòi kết quả decimal exact và ném ngoại lệ nếu bất khả thi.

`RoundingMode.UNNECESSARY` biểu thị **không được làm tròn mất thông tin**. Khi cần bỏ một chữ số khác 0 để đạt giới hạn mong muốn, phương thức từ chối. Đây là cách kiểm tra một ràng buộc exact, không phải một mode làm tròn mặc định.

## 4. Chọn chính sách theo yêu cầu, không theo mẹo tránh lỗi

Trước một phép chia `BigDecimal`, hãy xác định:

1. **Có yêu cầu exact không?** Nếu có, `divide(divisor)` phù hợp và phải xử lý trường hợp thương không thể biểu diễn hữu hạn.
2. **Nếu cho phép gần đúng, cần bao nhiêu chữ số?** Phân biệt scale (vị trí thập phân) với precision (chữ số có nghĩa).
3. **Làm tròn theo mode nào?** `HALF_UP`, `HALF_EVEN`, `FLOOR`, `CEILING`, `DOWN`... khác nhau về hướng, đặc biệt với số âm và giá trị đúng điểm giữa.
4. **Làm tròn ở bước nào?** Ngay khi chia, sau khi nhân, trên từng dòng, sau khi cộng tổng, hay lúc kết toán cuối cùng?
5. **Chia với mục đích gì?** Tính tỷ lệ thống kê, tính số lượng, lãi suất, phân bổ tài chính hoặc hiển thị có thể đòi chính sách khác nhau.
6. **Phần dư xử lý ra sao?** Đặc biệt khi phân chia một tổng thành nhiều phần cần bảo toàn tổng cuối.

Ví dụ, dùng `divide(3, 2, HALF_UP)` để chia `1.00` thành ba khoản:

```text
1.00 / 3 ≈ 0.33333…
Kết quả từng khoản (scale 2, HALF_UP): 0.33

0.33 + 0.33 + 0.33 = 0.99
Chênh lệch với tổng gốc = 0.01
```

Nếu yêu cầu là “ba khoản sau phân bổ phải cộng **đúng bằng** 1.00”, chỉ phép chia làm tròn **không đủ**. Phải có quy tắc phân bổ một đơn vị nhỏ nhất còn dư, chẳng hạn một khoản 0.34 và hai khoản 0.33. Cách chọn khoản nhận chênh lệch phụ thuộc nghiệp vụ; `BigDecimal` không quyết định thay.

Không suy quy tắc làm tròn từ tên kiểu hoặc số chữ số của dữ liệu đầu vào: `BigDecimal` không biết yêu cầu về tỷ lệ, thuế, tiền tệ, đo lường hay phân bổ.

## 5. Ví dụ Java 17+ có thể biên dịch, chạy độc lập

Tạo tệp `BigDecimalDivisionDemo.java`:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalDivisionDemo {

    private static void exact(
            String label, BigDecimal a, BigDecimal b) {
        try {
            System.out.println(label + " = " + a.divide(b));
        } catch (ArithmeticException ex) {
            System.out.println(label + " -> ArithmeticException");
        }
    }

    public static void main(String[] args) {
        BigDecimal one = BigDecimal.ONE;
        BigDecimal three = new BigDecimal("3");

        exact("1 / 8 exact", one, new BigDecimal("8"));
        exact("1 / 40 exact", one, new BigDecimal("40"));
        exact("1 / 3 exact", one, three);
        exact("3 / 6 exact",
                new BigDecimal("3"), new BigDecimal("6"));

        System.out.println("1 / 3 scale 2 = "
                + one.divide(three, 2, RoundingMode.HALF_UP));
        System.out.println("2 / 3 scale 2 = "
                + new BigDecimal("2").divide(
                        three, 2, RoundingMode.HALF_UP));
        System.out.println("1 / 6 scale 2 HALF_EVEN = "
                + one.divide(new BigDecimal("6"),
                        2, RoundingMode.HALF_EVEN));

        System.out.println("1 / 3 precision 5 = "
                + one.divide(three,
                        new MathContext(5, RoundingMode.HALF_UP)));
        System.out.println("10 / 6 precision 3 = "
                + new BigDecimal("10").divide(
                        new BigDecimal("6"),
                        new MathContext(3, RoundingMode.HALF_UP)));

        System.out.println("dividend scale 0 = "
                + new BigDecimal("1").divide(
                        three, RoundingMode.HALF_UP));
        System.out.println("dividend scale 2 = "
                + new BigDecimal("1.00").divide(
                        three, RoundingMode.HALF_UP));

        System.out.println("1.00 / 8 exact = "
                + new BigDecimal("1.00").divide(new BigDecimal("8")));
        System.out.println("1.00 / 8 scale 2 = "
                + new BigDecimal("1.00").divide(
                        new BigDecimal("8"), 2, RoundingMode.HALF_UP));

        try {
            one.divide(three, MathContext.UNLIMITED);
        } catch (ArithmeticException ex) {
            System.out.println("UNLIMITED -> ArithmeticException");
        }
        try {
            one.divide(three, 2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            System.out.println("UNNECESSARY -> ArithmeticException");
        }
        try {
            one.divide(BigDecimal.ZERO);
        } catch (ArithmeticException ex) {
            System.out.println("division by zero -> ArithmeticException");
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac BigDecimalDivisionDemo.java
java BigDecimalDivisionDemo
```

Stdout:

```text
1 / 8 exact = 0.125
1 / 40 exact = 0.025
1 / 3 exact -> ArithmeticException
3 / 6 exact = 0.5
1 / 3 scale 2 = 0.33
2 / 3 scale 2 = 0.67
1 / 6 scale 2 HALF_EVEN = 0.17
1 / 3 precision 5 = 0.33333
10 / 6 precision 3 = 1.67
dividend scale 0 = 0
dividend scale 2 = 0.33
1.00 / 8 exact = 0.125
1.00 / 8 scale 2 = 0.13
UNLIMITED -> ArithmeticException
UNNECESSARY -> ArithmeticException
division by zero -> ArithmeticException
```

Bốn điểm cần quan sát:

- `1 / 3` exact ném ngoại lệ, còn `1 / 8` exact trả `0.125`.
- Khi dùng scale hoặc precision tường minh, kết quả của `1 / 3` đã là **giá trị gần đúng**.
- `1 / 3` với `divide(divisor, HALF_UP)` cho 0 nếu dividend mang scale 0; `1.00 / 3` với cùng overload cho `0.33`.
- Không nên bắt `ArithmeticException` rồi coi mọi trường hợp đều do thương tuần hoàn: chia cho số 0 hoặc mode cấm làm tròn cũng có thể ném cùng loại ngoại lệ.

Ví dụ in **tên loại ngoại lệ** thay vì `ex.getMessage()` bởi nội dung thông báo lỗi không nên được dùng làm hợp đồng ổn định của một ứng dụng.

## 6. Những sai lầm dễ mắc và cách tránh

### Sai lầm A: chia exact trước, rồi mới setScale

```java
BigDecimal rounded = BigDecimal.ONE
        .divide(new BigDecimal("3")) // Ném ArithmeticException trước
        .setScale(2, RoundingMode.HALF_UP);
```

Phương thức `setScale` **không bao giờ được gọi**, vì `divide` đã thất bại. Nếu chấp nhận làm tròn, hãy dùng:

```java
BigDecimal rounded = BigDecimal.ONE.divide(
        new BigDecimal("3"), 2, RoundingMode.HALF_UP);
```

### Sai lầm B: chuyển sang double để né ArithmeticException

```java
double approximate = 1.0 / 3.0;
BigDecimal back = BigDecimal.valueOf(approximate);
```

`double` chứa một xấp xỉ nhị phân của `1/3`; chuyển ngược sang `BigDecimal` không khôi phục được giá trị hữu tỉ chính xác. Với miền nhạy cảm về decimal/đối soát, cách này dễ tạo thêm sai số và che giấu chính sách chưa xác định.

Nếu bài toán **chủ đích** dùng số thực gần đúng nhị phân, `double` là một lựa chọn kỹ thuật có thể phù hợp; nhưng không nên coi đó là “cách sửa” cho phép chia decimal cần được định nghĩa rõ.

### Sai lầm C: mặc định scale 2 cho mọi phép chia

Các bài toán đo lường, tỷ lệ hoặc tính toán khoa học có thể cần precision cao hơn hoặc quy tắc làm tròn ở bước khác. Hai chữ số thập phân không phải chính sách chung chỉ vì dùng `BigDecimal` hay dữ liệu được ghi trong một cột decimal.

### Sai lầm D: nhầm “không giới hạn precision” với “được phép vô hạn chữ số”

`MathContext.UNLIMITED` không cung cấp một cơ chế lưu dãy `0.333…` vô hạn; nó yêu cầu phép tính exact và có thể ném ngoại lệ.

### Sai lầm E: nuốt ArithmeticException rồi trả 0

```java
try {
    return amount.divide(divisor);
} catch (ArithmeticException ex) {
    return BigDecimal.ZERO; // Sai: che giấu lỗi thành kết quả 0
}
```

Đây là **phản ví dụ**, không phải một phương thức độc lập để sử dụng. Một lỗi chia cho 0, một tỷ lệ tuần hoàn và một ràng buộc exact không được phép tùy tiện biến thành giá trị 0. Cần xử lý ở ranh giới phù hợp, chọn overload đúng, hoặc nêu lỗi rõ theo hợp đồng.

### Sai lầm F: không tính phần dư sau phân bổ

Khi làm tròn từng phần của một tổng, tổng các phần đã làm tròn có thể khác số gốc. Nếu hệ thống yêu cầu bảo toàn tổng, cần một quy tắc phân bổ phần dư; phép chia làm tròn không tự làm điều này.

## 7. Thiết kế API theo chính sách nghiệp vụ

Một hàm dùng để chia theo policy có thể nhận scale và mode được xác định từ cấu hình nghiệp vụ. Ví dụ kiểu record Java 17:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public record DivisionPolicy(int scale, RoundingMode mode) {
    public DivisionPolicy {
        Objects.requireNonNull(mode, "mode");
    }

    public BigDecimal apply(BigDecimal a, BigDecimal b) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");
        return a.divide(b, scale, mode);
    }
}
```

Đây là kiểu Java `record` có thể lưu vào `DivisionPolicy.java`, **không phải lớp chạy độc lập có `main()`**. Trong ứng dụng, các quyết định như *chia tại bước nào*, *làm tròn từng khoản hay tổng*, *mode áp dụng cho số âm* và *cách phân bổ số dư* vẫn cần được xác định ở tầng nghiệp vụ.

Ví dụ minh họa khi đã có kiểu `DivisionPolicy`:

```java
DivisionPolicy policy =
        new DivisionPolicy(2, RoundingMode.HALF_UP);

BigDecimal part = policy.apply(
        new BigDecimal("10.00"), new BigDecimal("3"));
// part = 3.33; ba phần như nhau chỉ cộng thành 9.99
```

Chú ý: `new DivisionPolicy(2, HALF_UP)` chỉ là một chính sách minh họa, không phải quy định cho mọi đồng tiền hoặc đơn vị.

### Nếu thật sự cần lưu giá trị tỷ số exact

Thay vì ép tỷ số `1/3` vào một decimal hữu hạn, có thể mô hình hóa nó thành **tử số + mẫu số** dưới dạng số nguyên (`BigInteger`), chuẩn hóa phân số và chỉ chuyển sang `BigDecimal` ở bước có chính sách làm tròn:

```text
numerator = 1
denominator = 3

ratio exact = 1/3
decimal view with scale=2, HALF_UP = 0.33
```

Đây là gợi ý **mô hình hóa**, không phải một lớp có sẵn tên `Rational` trong thư viện chuẩn `java.math`. Khi sử dụng phân số, cần xử lý mẫu khác 0, dấu, rút gọn và giới hạn tài nguyên.

## 8. Kiểm thử các trường hợp quan trọng

Một bộ test tốt không chỉ kiểm tra `1/3` mà còn cả các nhánh hành vi:

| Trường hợp | Kỳ vọng |
|---|---|
| `BigDecimal.ONE.divide(new BigDecimal("8"))` | `0.125` |
| `BigDecimal.ONE.divide(new BigDecimal("40"))` | `0.025` |
| `new BigDecimal("3").divide(new BigDecimal("6"))` | `0.5` |
| `BigDecimal.ONE.divide(new BigDecimal("3"))` | `ArithmeticException` |
| `BigDecimal.ONE.divide(new BigDecimal("3"), 2, HALF_UP)` | `0.33` |
| `new BigDecimal("2").divide(new BigDecimal("3"), 2, HALF_UP)` | `0.67` |
| `BigDecimal.ONE.divide(new BigDecimal("3"), MathContext.UNLIMITED)` | `ArithmeticException` |
| `BigDecimal.ONE.divide(new BigDecimal("3"), 2, UNNECESSARY)` | `ArithmeticException` |
| `BigDecimal.ONE.divide(BigDecimal.ZERO)` | `ArithmeticException` |
| `new BigDecimal("1.00").divide(new BigDecimal("8"))` | `0.125` |
| `new BigDecimal("1.00").divide(new BigDecimal("8"), 2, HALF_UP)` | `0.13` |

Ngoài ra cần kiểm tra dấu âm, điểm giữa của các mode làm tròn, scale âm khi có dữ liệu kiểu ký pháp khoa học, và quy tắc phân bổ số dư nếu nghiệp vụ có nhiều phần.

Khi so sánh kỳ vọng với kết quả `BigDecimal`:

- `equals()` kiểm tra **cả giá trị và scale**. Ví dụ `0.50` không `equals()` với `0.5`.
- `compareTo() == 0` kiểm tra **giá trị số học** bất kể scale.

Chọn cách assertion tùy hợp đồng: nếu scale đích là một phần của yêu cầu, bài test cần kiểm tra scale; nếu chỉ yêu cầu bằng nhau về giá trị số học, so sánh bằng `compareTo` sẽ phù hợp.

## 9. Câu hỏi tự kiểm tra

**1. Tại sao hai số nguyên BigDecimal có thể chia nhau mà ném ArithmeticException?**  
Vì thương exact có thể là thập phân vô hạn tuần hoàn, không thể lưu hoàn chỉnh trong một `BigDecimal` hữu hạn.

**2. Khi nào `divide(divisor)` trả kết quả chính xác?**  
Khi thương có biểu diễn thập phân hữu hạn. Với phân số tối giản, mẫu chỉ chứa thừa số nguyên tố 2 và/hoặc 5.

**3. Vì sao `3/6` chia exact được nhưng `1/6` thì không?**  
`3/6` rút gọn thành `1/2`; `1/6` đã tối giản và mẫu còn thừa số 3.

**4. `divide(divisor, 2, HALF_UP)` có phải trả thương exact cho `1/3` không?**  
Không. Nó trả `0.33`, một giá trị đã làm tròn theo chính sách.

**5. `divide(divisor, HALF_UP)` có dùng scale mặc định 2 không?**  
Không. Nó dùng **scale của dividend**, nên cùng giá trị đầu vào nhưng khác scale có thể trả kết quả khác.

**6. `MathContext.UNLIMITED` có làm thương tuần hoàn hết ném ngoại lệ không?**  
Không. Unlimited ở đây vẫn đòi exact.

**7. Ba khoản 0.33 cộng được 0.99, muốn phân bổ đủ 1.00 thì làm sao?**  
Cần quy tắc phân bổ phần dư 0.01 theo nghiệp vụ; `divide` không tự quyết định.

**8. Vì sao không nên bắt ArithmeticException rồi trả BigDecimal.ZERO?**  
Vì như vậy biến tình huống không có thương exact hoặc chia cho 0 thành kết quả 0 sai lệch, che giấu lỗi.

**Ghi nhớ:** `BigDecimal.divide(divisor)` không tự làm tròn kết quả tuần hoàn. Muốn có thương decimal hữu hạn đã lượng hóa, phải chỉ định **scale hoặc precision và RoundingMode** một cách tường minh. Nếu yêu cầu exact, xử lý ngoại lệ như một ràng buộc của phép tính, không giấu nó bằng cách chuyển sang `double` hoặc tự trả 0.
