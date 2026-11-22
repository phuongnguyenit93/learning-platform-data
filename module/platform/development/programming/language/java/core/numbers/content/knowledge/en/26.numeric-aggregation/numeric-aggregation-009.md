# Tổng `BigDecimal` và chính sách `MathContext` trong Java

## 1. Tổng nhiều số thập phân cần chính sách rõ ràng

Khi cộng nhiều khoản tiền, phép đo hoặc giá trị nghiệp vụ, vấn đề không chỉ là lấy tổng mà còn là **tổng phải chính xác đến đâu**, **khi nào được làm tròn** và **quy tắc làm tròn nào được phép**.

`BigDecimal` hỗ trợ hai cách cộng quan trọng:

~~~java
BigDecimal exact = left.add(right);
BigDecimal limited = left.add(right, context);
~~~

- `add(BigDecimal)` tính tổng **chính xác về mặt giá trị thập phân**. Phép cộng không mặc định giới hạn số chữ số có nghĩa.
- `add(BigDecimal, MathContext)` áp dụng **precision** và **rounding mode** cho kết quả phép cộng. Nếu precision hữu hạn, một phần chữ số có thể bị làm tròn ngay ở bước đó.
- “Cộng chính xác tất cả phần tử rồi làm tròn một lần” **có thể khác** “làm tròn ở mỗi lần cộng”. Đó là hai chính sách tính toán riêng.

Nếu hợp đồng chỉ yêu cầu “lấy tổng rồi biểu diễn thành hai chữ số thập phân”, thường nên **cộng chính xác trước, áp scale cuối cùng**. Nếu đặc tả yêu cầu kết quả trung gian luôn giới hạn precision, hãy dùng `MathContext` ở từng phép tính và chấp nhận tác động của làm tròn tích lũy.

## 2. Kiến thức nền: giá trị, scale và precision

Giá trị của một `BigDecimal` được xác định bởi:

~~~text
value = unscaledValue × 10^(-scale)
~~~

| Chuỗi | Giá trị | Scale | Precision |
| --- | --- | ---: | ---: |
| `"1.20"` | 1.20 | 2 | 3 |
| `"2.345"` | 2.345 | 3 | 4 |
| `"0.005"` | 0.005 | 3 | 1 |
| `"1234.00"` | 1234.00 | 2 | 6 |

**Scale** quy định vị trí dấu thập phân; **precision** đếm số chữ số có nghĩa trong unscaled value. `MathContext(3, HALF_UP)` giới hạn **ba chữ số có nghĩa trên toàn bộ kết quả**, không phải ba chữ số sau dấu chấm.

Phép cộng chính xác có *preferred scale* bằng giá trị lớn hơn giữa scale hai toán hạng. Ví dụ:

~~~java
BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("2.345");
BigDecimal result = a.add(b);
System.out.println(result);         // 3.545
System.out.println(result.scale()); // 3
~~~

Cộng thêm `new BigDecimal("0.005")` được `3.550`, vẫn có scale 3. Giá trị toán học này bằng `3.55`; tuy nhiên `equals` còn xét scale nên `new BigDecimal("3.550").equals(new BigDecimal("3.55"))` là `false`, còn `compareTo` trả về 0.

Vì `BigDecimal` bất biến, mỗi phép `add` trả về một đối tượng kết quả; toán hạng không thay đổi. Cần gán kết quả cho biến tổng, không chỉ gọi `total.add(value)` rồi bỏ kết quả.

## 3. Cộng chính xác trước khi xử lý đầu ra

### 3.1. Dùng vòng lặp

Đoạn sau cần đặt trong một phương thức và import `java.math.BigDecimal`, `java.util.List`:

~~~java
List<BigDecimal> amounts = List.of(
        new BigDecimal("1.20"),
        new BigDecimal("2.345"),
        new BigDecimal("0.005"));

BigDecimal total = BigDecimal.ZERO;
for (BigDecimal amount : amounts) {
    total = total.add(amount);
}
System.out.println(total); // 3.550
~~~

`BigDecimal.ZERO` là phần tử trung hòa cho phép cộng về **giá trị**: bắt đầu với zero và lần lượt cộng các giá trị là cách đơn giản, minh bạch. Với danh sách rỗng, kết quả ở cách này là `BigDecimal.ZERO` (scale 0). Nếu đầu ra yêu cầu scale 2, có thể chuẩn hóa zero đó bằng `setScale(2)`.

### 3.2. Dùng `Stream.reduce`

~~~java
BigDecimal total = amounts.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

Khi không truyền `MathContext`, cách này giữ nguyên chính sách **cộng chính xác**. Với stream rỗng, `reduce(identity, accumulator)` trả `BigDecimal.ZERO`. Nếu “không có bản ghi” phải khác với “tổng bằng 0”, có thể dùng overload:

~~~java
Optional<BigDecimal> optionalTotal = amounts.stream()
        .reduce(BigDecimal::add);
~~~

Overload này trả `Optional.empty()` khi không có phần tử. Đây là **đoạn mã minh họa**, cần import `java.util.Optional`.

Không có phương thức tĩnh `BigDecimal.sum(List)` chuẩn giống `IntStream.sum()`. `reduce` hoặc vòng lặp là lựa chọn phổ biến.

### 3.3. Chất lượng dữ liệu đầu vào

Hãy xây dựng các số thập phân từ chuỗi khi muốn bảo toàn số thập phân nguồn: `new BigDecimal("0.1")` có đúng giá trị 0.1, còn `new BigDecimal(0.1)` nhận giá trị `double` nhị phân đã làm tròn. Nếu dữ liệu đến từ `double`, `BigDecimal.valueOf(value)` thường phù hợp hơn constructor nhận `double`, nhưng không thể tự khôi phục văn bản thập phân gốc chưa biết.

Danh sách chứa `null` không thể cộng trực tiếp; `BigDecimal.add(null)` sẽ gây lỗi. Phải có hợp đồng đầu vào: từ chối, loại bỏ bản ghi thiếu hoặc xem thiếu là 0 **chỉ khi nghiệp vụ cho phép**. Đừng âm thầm loại dữ liệu sai.

## 4. `MathContext`: precision và rounding mode

Một `MathContext` gồm hai thành phần:

- `precision`: giới hạn số chữ số có nghĩa của kết quả. Giá trị 0 nghĩa là không giới hạn.
- `roundingMode`: chính sách làm tròn khi số chữ số của kết quả vượt giới hạn, ví dụ `HALF_UP`, `HALF_EVEN`, `DOWN`, `UNNECESSARY`.

~~~java
MathContext mc = new MathContext(3, RoundingMode.HALF_UP);

System.out.println(new BigDecimal("1.234").round(mc)); // 1.23
System.out.println(new BigDecimal("12345").round(mc)); // 1.23E+4
~~~

Đoạn mã trên cần import `java.math.MathContext`, `java.math.BigDecimal`, `java.math.RoundingMode`. Khi precision hữu hạn, `BigDecimal.add(other, mc)` có thể làm tròn **mỗi tổng trung gian**.

`MathContext.UNLIMITED` có precision 0. Dùng `add(other, MathContext.UNLIMITED)` cho tổng chính xác về giá trị như overload không có context, miễn thao tác không gặp vấn đề tài nguyên. Rounding mode không tạo khác biệt khi precision không giới hạn và không có chữ số nào cần bỏ.

## 5. Cộng rồi làm tròn một lần và làm tròn từng lần

Giả sử ta có `1.234`, `0.004`, `0.004` với precision 3 và `HALF_UP`.

**Chính sách A — Cộng chính xác rồi làm tròn cuối:**

~~~java
BigDecimal exact = BigDecimal.ZERO;
for (BigDecimal x : values) {
    exact = exact.add(x);
}
BigDecimal roundedOnce = exact.round(mc);
~~~

**Chính sách B — Mỗi phép cộng áp `MathContext`:**

~~~java
BigDecimal roundedEveryStep = BigDecimal.ZERO;
for (BigDecimal x : values) {
    roundedEveryStep = roundedEveryStep.add(x, mc);
}
~~~

| Bước | A: Tổng chính xác | B: Tổng làm tròn từng bước |
| --- | ---: | ---: |
| Cộng `1.234` | 1.234 | 1.23 |
| Cộng `0.004` | 1.238 | 1.23 |
| Cộng `0.004` | 1.242 | 1.23 |
| Áp precision 3 tại cuối | **1.24** | **1.23** |

Đối với A, `1.242` làm tròn một lần thành `1.24`. Với B, `1.234` bị làm tròn thành `1.23` ngay ở bước đầu. Hai giá trị `0.004` không đủ lớn để thay đổi từng tổng đã bị làm tròn, nên kết quả cuối vẫn `1.23`.

Đây là **mất đóng góp do làm tròn trung gian**. Không thể khôi phục các chữ số đã bị loại ở một bước trước chỉ bằng việc cộng thêm những giá trị khác.

Chính sách B không phải lúc nào cũng sai: nếu một thuật toán quy định precision hữu hạn cho **từng phép tính**, đó là hành vi được chủ đích. Nhưng khi đặc tả là “tổng các khoản chính xác rồi mới làm tròn”, phải áp dụng A.

## 6. Rounding mode ảnh hưởng thế nào?

Các chính sách làm tròn có thể khác nhau ngay cả khi precision giống nhau. Ví dụ:

~~~java
BigDecimal x = new BigDecimal("2.345");

MathContext halfEven = new MathContext(3, RoundingMode.HALF_EVEN);
MathContext halfUp = new MathContext(3, RoundingMode.HALF_UP);

System.out.println(x.round(halfEven)); // 2.34
System.out.println(x.round(halfUp));   // 2.35
~~~

Ở trường hợp đúng nửa đơn vị, `HALF_EVEN` ưu tiên chữ số cuối được giữ lại là số chẵn; `HALF_UP` làm tròn theo hướng tăng độ lớn khi đúng nửa. Không có một rounding mode “đúng cho mọi nghiệp vụ”.

`RoundingMode.UNNECESSARY` yêu cầu **kết quả phải chính xác mà không cần loại chữ số khác 0**. Nếu tổng chính xác không thể biểu diễn dưới precision/scale yêu cầu mà vẫn giữ giá trị, thao tác sẽ ném `ArithmeticException`.

~~~java
MathContext strict = new MathContext(3, RoundingMode.UNNECESSARY);

new BigDecimal("3.550").round(strict); // 3.55, hợp lệ: bỏ zero dư

// Ném ArithmeticException:
// new BigDecimal("1.242").round(strict);
~~~

Chú ý: `UNNECESSARY` có thể bỏ những số 0 tận cùng; nó **không** có nghĩa là cấm thay đổi cách biểu diễn.

## 7. Thứ tự cộng và tính kết hợp

Phép cộng số học chính xác có tính kết hợp: `(a + b) + c = a + (b + c)`. Nhưng nếu làm tròn **mỗi phép cộng**, kết quả có thể phụ thuộc thứ tự.

Xét ba giá trị `1000`, `1`, `-1000`, precision 3 và `HALF_UP`:

~~~java
BigDecimal a = new BigDecimal("1000");
BigDecimal b = BigDecimal.ONE;
BigDecimal c = new BigDecimal("-1000");
MathContext mc = new MathContext(3, RoundingMode.HALF_UP);

BigDecimal first = a.add(b, mc).add(c, mc);
BigDecimal second = a.add(c, mc).add(b, mc);

System.out.println(first);  // 0
System.out.println(second); // 1
~~~

Trong thứ tự thứ nhất, `1000 + 1 = 1001` bị làm tròn về `1.00E+3`, rồi cộng `-1000` thành 0. Trong thứ tự thứ hai, `1000 + (-1000) = 0`, rồi cộng 1 thành 1. **Tổng chính xác luôn là 1.**

Điều này dẫn tới quy tắc quan trọng đối với `Stream.reduce`:

- Với `BigDecimal::add` **không truyền context**, phép cộng kết hợp về giá trị và có thể dùng trong parallel stream nếu mọi phần tử hợp lệ, không có side effect.
- Với lambda `(a, b) -> a.add(b, mc)` khi precision hữu hạn, phép toán có thể **không còn kết hợp**. Parallel reduction có thể gom nhóm khác nhau và cho kết quả khác nhau. Tránh dùng accumulator kiểu này trong `parallelStream` nếu không có thiết kế thuật toán và kiểm chứng riêng.

Mẫu an toàn hơn cho bài toán “tổng chính xác rồi làm tròn”:

~~~java
BigDecimal exact = values.parallelStream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);
BigDecimal result = exact.round(mc);
~~~

Cần bảo đảm đầu vào không chứa `null` và danh sách không bị sửa trong khi tính tổng. `BigDecimal` bất biến nên bản thân phép cộng trên các giá trị hợp lệ không có side effect.

## 8. Đừng nhầm giới hạn precision với scale đầu ra

Ví dụ với dữ liệu khoản tiền:

~~~java
BigDecimal total = new BigDecimal("1.20")
        .add(new BigDecimal("2.345"))
        .add(new BigDecimal("0.005"));

System.out.println(total); // 3.550

BigDecimal normalized = total.setScale(2, RoundingMode.HALF_EVEN);
System.out.println(normalized); // 3.55
~~~

`setScale(2, ...)` yêu cầu **2 chữ số sau dấu chấm**. `new MathContext(2, ...)` lại giới hạn **2 chữ số có nghĩa**, kể cả phần nguyên. Với số lớn, hai chính sách tạo ra kết quả rất khác nhau.

Nếu nghiệp vụ **không cho phép làm tròn** khi chuẩn hóa scale, dùng:

~~~java
BigDecimal normalized =
        total.setScale(2, RoundingMode.UNNECESSARY);
~~~

`3.550` đổi chính xác thành `3.55` vì chỉ bỏ zero dư. Nhưng `3.551` không thể biểu diễn chính xác với scale 2 nên sẽ ném `ArithmeticException`.

Nếu cần giới hạn cả scale và tổng precision, hãy ghi rõ **thứ tự kiểm tra**:

~~~java
BigDecimal scaled = total.setScale(2, RoundingMode.HALF_EVEN);
BigDecimal checked = scaled.round(
        new MathContext(12, RoundingMode.UNNECESSARY));
~~~

Chính sách ví dụ: cho phép làm tròn tổng một lần về scale 2, sau đó yêu cầu biểu diễn được trong 12 chữ số có nghĩa mà không làm tròn thêm. Kiểm tra precision không thay thế kiểm tra miền giá trị, loại tiền hoặc giới hạn dữ liệu của cơ sở dữ liệu.

## 9. Chương trình Java 17+ hoàn chỉnh

Lưu tệp **BigDecimalSumPolicyDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;
import java.util.List;

public class BigDecimalSumPolicyDemo {
    private static BigDecimal sumExactly(List<BigDecimal> values) {
        BigDecimal total = BigDecimal.ZERO;
        for (BigDecimal value : values) {
            total = total.add(value);
        }
        return total;
    }

    private static BigDecimal sumWithContext(
            List<BigDecimal> values, MathContext context) {
        BigDecimal total = BigDecimal.ZERO;
        for (BigDecimal value : values) {
            total = total.add(value, context);
        }
        return total;
    }

    public static void main(String[] args) {
        List<BigDecimal> values = List.of(
                new BigDecimal("1.234"),
                new BigDecimal("0.004"),
                new BigDecimal("0.004"));
        MathContext mc = new MathContext(3, RoundingMode.HALF_UP);

        BigDecimal exact = sumExactly(values);
        System.out.println("exact total: " + exact);
        System.out.println("round once: " + exact.round(mc));
        System.out.println("round each: "
                + sumWithContext(values, mc));

        BigDecimal a = new BigDecimal("1000");
        BigDecimal b = BigDecimal.ONE;
        BigDecimal c = new BigDecimal("-1000");
        System.out.println("first order: "
                + a.add(b, mc).add(c, mc));
        System.out.println("second order: "
                + a.add(c, mc).add(b, mc));

        BigDecimal money = sumExactly(List.of(
                new BigDecimal("1.20"),
                new BigDecimal("2.345"),
                new BigDecimal("0.005")));
        System.out.println("money exact: " + money);
        System.out.println("money scale2: "
                + money.setScale(2, RoundingMode.HALF_EVEN));

        MathContext strict =
                new MathContext(3, RoundingMode.UNNECESSARY);
        System.out.println("strict exact: " + money.round(strict));
        try {
            System.out.println(exact.round(strict));
        } catch (ArithmeticException ex) {
            System.out.println("strict inexact: ArithmeticException");
        }

        System.out.println("empty sum: "
                + sumExactly(List.of()));
        System.out.println("parallel exact: "
                + values.parallelStream()
                        .reduce(BigDecimal.ZERO, BigDecimal::add));

        BigDecimal tie = new BigDecimal("2.345");
        System.out.println("half even: " + tie.round(
                new MathContext(3, RoundingMode.HALF_EVEN)));
        System.out.println("half up: " + tie.round(
                new MathContext(3, RoundingMode.HALF_UP)));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BigDecimalSumPolicyDemo.java
java BigDecimalSumPolicyDemo
~~~

Đầu ra chính xác:

~~~text
exact total: 1.242
round once: 1.24
round each: 1.23
first order: 0
second order: 1
money exact: 3.550
money scale2: 3.55
strict exact: 3.55
strict inexact: ArithmeticException
empty sum: 0
parallel exact: 1.242
half even: 2.34
half up: 2.35
~~~

Chương trình chứng minh sự khác biệt giữa hai chính sách tổng, sự phụ thuộc vào thứ tự khi làm tròn ở mỗi lần cộng, chuẩn hóa về scale đầu ra, `UNNECESSARY` khi bắt buộc chính xác, và phép cộng chính xác trong parallel stream.

## 10. Mẫu thiết kế tổng cho ứng dụng

### 10.1. Chính sách tổng cuối, làm tròn cuối

~~~java
public static BigDecimal sumToTwoDecimals(List<BigDecimal> values) {
    BigDecimal exact = BigDecimal.ZERO;
    for (BigDecimal value : values) {
        exact = exact.add(value);
    }
    return exact.setScale(2, RoundingMode.HALF_EVEN);
}
~~~

Đây là **phương thức để đặt trong một class**, cần import `BigDecimal`, `RoundingMode`, `List`. Hàm hợp với quy tắc “cộng tất cả giá trị chính xác rồi trả kết quả scale 2 theo `HALF_EVEN`”. Nếu bị cấm làm tròn, đổi sang `UNNECESSARY` và xử lý lỗi.

Cần quy định trước liệu danh sách rỗng có đại diện tổng bằng `0.00` hay một trạng thái không có dữ liệu. Hàm trên trả `0.00` trong trường hợp rỗng, do `setScale(2)` trên zero.

### 10.2. Khi thực sự cần `MathContext` mỗi lần cộng

~~~java
BigDecimal total = BigDecimal.ZERO;
for (BigDecimal value : values) {
    total = total.add(value, context);
}
~~~

Chỉ nên chọn cách này khi **precision trung gian** được chỉ định trong hợp đồng tính toán, ví dụ thuật toán mô phỏng số học hữu hạn, hoặc cần tái tạo kết quả của một quy trình xử lý đã có quy định làm tròn theo bước. Chú ý thứ tự duyệt phải có ý nghĩa xác định; test với số rất lớn, số rất nhỏ và các phần tử có dấu ngược nhau dễ triệt tiêu.

### 10.3. Tối ưu hiệu năng không được làm đổi hợp đồng

Các đối tượng `BigDecimal` bất biến, nên việc cộng nhiều phần tử có thể cấp phát nhiều đối tượng và tốn tài nguyên với giá trị/scale rất lớn. Tuy nhiên, giới hạn precision ở từng bước để giảm chi phí **có thể thay đổi tổng**. Đây là lựa chọn thuật toán cần kiểm chứng với sai số cho phép; không phải một tối ưu hóa bảo toàn hoàn toàn ngữ nghĩa.

Với bài toán tài chính dùng đơn vị nhỏ nhất cố định, biểu diễn bằng số nguyên cũng có thể phù hợp, nhưng cần một chính sách khác cho scale, overflow và đơn vị tiền. Không chuyển kiểu chỉ vì tốc độ trước khi xác định đúng hợp đồng.

## 11. Lỗi phổ biến và câu hỏi tự kiểm tra

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| `MathContext(2, HALF_UP)` cho ra 2 chữ số sau dấu chấm | Nó cho tối đa **2 chữ số có nghĩa**; dùng `setScale(2, ...)` cho phần thập phân |
| Cộng với `MathContext` mỗi bước tương đương cộng chính xác rồi làm tròn | Có thể mất các đóng góp nhỏ và cho tổng khác |
| Đổi thứ tự cộng không ảnh hưởng khi có context | Làm tròn trung gian có thể phá vỡ tính kết hợp |
| `parallelStream` với accumulator `add(mc)` luôn an toàn | Accumulator có thể không kết hợp, làm kết quả tùy cách nhóm |
| `BigDecimal.ZERO` đã có scale 2 | Zero mặc định có scale 0; chuẩn hóa sau theo hợp đồng |
| `UNNECESSARY` bỏ qua xử lý làm tròn | Nó **báo lỗi** nếu phải thay đổi giá trị để đạt precision/scale mong muốn |
| `equals` và `compareTo` giống nhau | `equals` còn so scale; `compareTo` xét giá trị |
| `new BigDecimal(0.1)` luôn chính xác số thập phân 0.1 | Constructor nhận giá trị `double` nhị phân đã làm tròn |

Tự kiểm tra:

1. Tổng chính xác của `1.234 + 0.004 + 0.004`? **`1.242`**.
2. Làm tròn tổng đó một lần với precision 3, `HALF_UP`? **`1.24`**.
3. Nếu làm tròn sau từng phép cộng cùng context? **`1.23`**.
4. Vì sao `1000 + 1 - 1000` có thể ra 0 với precision 3? **Làm tròn mất đơn vị 1 ở bước đầu**, trong khi tổng chính xác là 1.
5. Muốn đầu ra luôn có hai chữ số sau dấu chấm thì dùng gì? **`setScale(2, roundingMode)`** sau khi tổng đã tính theo hợp đồng.
6. Có thể dùng `BigDecimal::add` làm accumulator cho tổng chính xác trong parallel stream không? **Có**, nếu dữ liệu hợp lệ và không có tác dụng phụ.
7. `RoundingMode.UNNECESSARY` phù hợp lúc nào? **Khi ràng buộc precision hoặc scale phải được đáp ứng mà không đổi giá trị**; nếu không thể, thao tác ném `ArithmeticException`.

**Ghi nhớ:** Tách ba quyết định: **cộng chính xác bằng `add`**, **giới hạn chữ số có nghĩa bằng `MathContext`**, và **chuẩn hóa chữ số sau dấu chấm bằng `setScale`**. Thời điểm áp chính sách làm tròn ảnh hưởng trực tiếp kết quả, khả năng song song hóa và tính nhất quán nghiệp vụ.