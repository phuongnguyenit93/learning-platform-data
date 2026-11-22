# Thiết kế phép tính thập phân với MathContext và RoundingMode trong Java

Một hệ thống báo giá, tính thuế, chiết khấu hoặc chia tỷ lệ thường dùng `BigDecimal` để giữ đúng giá trị thập phân. Tuy nhiên, **dùng BigDecimal không tự động làm cho mọi kết quả và quy tắc làm tròn đều đúng nghiệp vụ**: phép chia có thể không có biểu diễn thập phân hữu hạn; phép toán có thể tạo nhiều chữ số hơn mong muốn; cùng một bộ dữ liệu có thể cho tổng khác nhau nếu làm tròn tại các bước khác nhau.

Bài thực hành này hướng dẫn thiết kế một chính sách tính toán rõ ràng qua ba thành phần:

- **Giá trị và cách biểu diễn:** `BigDecimal` giữ một số nguyên không chia tỷ lệ (`unscaledValue`) và `scale`.
- **Độ chính xác khi tính:** `MathContext` định nghĩa `precision` (số chữ số có nghĩa) và `RoundingMode` dùng khi phải bỏ chữ số.
- **Làm tròn kết quả theo đơn vị:** `setScale(...)` và một chính sách `RoundingMode` quy định số chữ số sau dấu thập phân khi chốt giá trị.

Mục tiêu không phải chọn một “rounding mode tốt nhất cho mọi hệ thống”. Mục tiêu là **tạo quy tắc cụ thể, dễ kiểm thử và nhất quán với hợp đồng nghiệp vụ**.

## 1. Mô hình số thập phân của BigDecimal

Giá trị được biểu diễn theo công thức:

~~~text
numericValue = unscaledValue × 10^(-scale)
~~~

Ví dụ:

| Chuỗi đưa vào constructor | `unscaledValue()` | `scale()` | `precision()` |
|---|---:|---:|---:|
| `"12"` | 12 | 0 | 2 |
| `"12.00"` | 1200 | 2 | 4 |
| `"0.00123"` | 123 | 5 | 3 |
| `"123.456"` | 123456 | 3 | 6 |
| `"1E+3"` | 1 | -3 | 1 |

**`scale`** đếm vị trí dấu thập phân trong biểu diễn; có thể âm. **`precision`** đếm tổng số chữ số trong phần nguyên `unscaledValue`, bỏ dấu âm và số 0 đầu không thuộc biểu diễn. Vì vậy `precision = 4` không có nghĩa “bốn chữ số sau dấu phẩy”, và `scale = 2` cũng không có nghĩa số được tính với chính xác hai chữ số có nghĩa.

`BigDecimal` là immutable: phép toán trả đối tượng kết quả; việc gọi `setScale` không thay đổi đối tượng ban đầu. Luôn gán hoặc trả về kết quả nếu muốn dùng nó trong bước sau.

Khởi tạo bằng chuỗi decimal:

~~~java
BigDecimal rate = new BigDecimal("0.075");
BigDecimal amount = new BigDecimal("123.45");
~~~

Tránh `new BigDecimal(0.1)` khi ý muốn là số thập phân chính xác 0.1, vì constructor nhận `double` lấy **giá trị nhị phân** đang được biểu diễn, có thể khác chuỗi decimal người viết kỳ vọng. Sử dụng `new BigDecimal("0.1")` hoặc `BigDecimal.valueOf(0.1)` nếu nguồn dữ liệu phù hợp.

## 2. MathContext là gì?

`java.math.MathContext` là một đối tượng bất biến chứa hai quyết định:

1. `precision` — tối đa bao nhiêu **chữ số có nghĩa** cho kết quả của một phép toán sử dụng context, nếu precision lớn hơn 0;
2. `roundingMode` — phải xử lý các chữ số bị loại như thế nào khi kết quả không thể giữ nguyên trong precision đó.

Tạo context:

~~~java
import java.math.MathContext;
import java.math.RoundingMode;

MathContext work = new MathContext(4, RoundingMode.HALF_EVEN);
~~~

`precision = 4` nói rằng kết quả làm tròn của phép toán dùng context sẽ có tối đa bốn chữ số có nghĩa. Nó **không** nói kết quả luôn có bốn chữ số sau dấu thập phân.

`MathContext` chỉ tác động khi **được truyền vào thao tác có overload tương ứng**, ví dụ `a.add(b, work)`, `a.multiply(b, work)`, `a.divide(b, work)`, `a.round(work)`. Tạo biến `MathContext work` rồi gọi `a.add(b)` không tự động áp dụng context cho phép cộng đó.

Ví dụ:

~~~java
BigDecimal a = new BigDecimal("123.456");
BigDecimal b = new BigDecimal("0.789");
MathContext work = new MathContext(4, RoundingMode.HALF_EVEN);

System.out.println(a.add(b));       // 124.245
System.out.println(a.add(b, work)); // 124.2
~~~

Kết quả chính xác `124.245` có sáu chữ số có nghĩa; với context bốn chữ số, kết quả là `124.2`. Phần `0.045` đã được làm tròn **trong phép toán đang dùng context**. Nếu lưu kết quả này rồi tính tiếp, thông tin phần bị bỏ không tự xuất hiện trở lại.

## 3. Khác biệt cốt lõi: precision và scale

| Câu hỏi | API phù hợp | Ý nghĩa |
|---|---|---|
| “Kết quả phép tính giữ tối đa 6 chữ số có nghĩa?” | `new MathContext(6, roundingMode)` | Giới hạn **precision** khi tính |
| “Kết quả cuối có đúng 2 chữ số sau dấu thập phân?” | `setScale(2, roundingMode)` | Đặt **scale** của biểu diễn cuối |
| “Phải chia 1/3 và lấy 6 chữ số có nghĩa?” | `divide(divisor, mc6)` | `0.333333` |
| “Phải chia 1/3 và chốt đến 2 chữ số thập phân?” | `divide(divisor, 2, roundingMode)` | `0.33` |
| “Phải không mất bất kỳ chữ số có nghĩa nào?” | `MathContext.UNLIMITED` hoặc không dùng context nếu phép toán có kết quả hữu hạn chính xác | Kết quả cần chính xác; phép chia vô hạn có thể ném lỗi |

Một ví dụ quan trọng về độ lớn:

~~~java
BigDecimal x = new BigDecimal("12345");
System.out.println(x.round(new MathContext(3, RoundingMode.HALF_UP)));
// 1.23E+4

System.out.println(x.setScale(2));
// 12345.00
~~~

Kết quả thứ nhất làm tròn thành **ba chữ số có nghĩa** (giá trị thay đổi từ 12345 thành 12300). Kết quả thứ hai giữ nguyên **giá trị 12345** nhưng biểu diễn với hai chữ số sau dấu thập phân. Đây là hai nhiệm vụ khác nhau.

Đừng dùng `new MathContext(2)` để biểu diễn “tiền có hai chữ số lẻ”. Và đừng mặc định `setScale(2)` đủ để kiểm soát sai số của các phép chia/trị số trung gian mà không cần xét thuật toán.

## 4. Những RoundingMode cần nắm

`java.math.RoundingMode` là enum; sử dụng các hằng enum thay vì các hằng `BigDecimal.ROUND_*` kiểu `int` đã lỗi thời.

| Mode | Quy tắc khi phải bỏ chữ số khác 0 | Cách hiểu |
|---|---|---|
| `UP` | Tăng độ lớn ra xa 0 | Dù giá trị dương hay âm |
| `DOWN` | Tiến về 0 | Cắt chữ số bị bỏ theo độ lớn |
| `CEILING` | Hướng tới +∞ | Với số âm thường ít âm hơn |
| `FLOOR` | Hướng tới -∞ | Với số âm thường âm hơn |
| `HALF_UP` | Tới gần nhất; đúng điểm giữa thì ra xa 0 | Kiểu làm tròn .5 thường được dạy |
| `HALF_DOWN` | Tới gần nhất; đúng điểm giữa thì về 0 | Chỉ khác các trường hợp đúng giữa |
| `HALF_EVEN` | Tới gần nhất; đúng điểm giữa chọn chữ số giữ lại chẵn | Giảm thiên lệch trong nhiều chuỗi làm tròn |
| `UNNECESSARY` | Không được bỏ chữ số có nghĩa | Ném `ArithmeticException` nếu cần làm tròn |

Ví dụ số dương và âm:

~~~java
BigDecimal positive = new BigDecimal("2.345");
BigDecimal negative = new BigDecimal("-2.345");

System.out.println(positive.setScale(2, RoundingMode.HALF_UP));   // 2.35
System.out.println(positive.setScale(2, RoundingMode.HALF_EVEN)); // 2.34
System.out.println(negative.setScale(2, RoundingMode.HALF_UP));   // -2.35
~~~

Ở đây chữ số giữ lại thứ hai của `2.34` là 4 (chẵn); tại đúng điểm giữa `2.345`, `HALF_EVEN` chọn `2.34`, còn `HALF_UP` chọn `2.35`. Với `-2.345`, `HALF_UP` làm tròn **ra xa 0**, được `-2.35`, không phải `-2.34`.

Với giá trị `2.355` ở scale 2, `HALF_EVEN` lại chọn `2.36` vì chữ số 6 là chẵn. `HALF_EVEN` không có nghĩa “luôn làm tròn xuống khi .5”, mà là quy tắc chọn chữ số chẵn **chỉ trong trường hợp đúng giữa hai lựa chọn**.

Không tự chọn `HALF_EVEN` chỉ vì thuật ngữ “banker's rounding”; quy tắc tính thuế, tiền, chiết khấu và báo cáo có thể quy định phương thức khác tùy hệ thống/quốc gia/hợp đồng.

## 5. Vì sao MathContext không phải cấu hình toàn cục?

Mỗi phép toán của `BigDecimal` có các overload **với hoặc không với `MathContext`**:

~~~java
BigDecimal exact = a.multiply(b);
BigDecimal rounded = a.multiply(b, work);
~~~

`exact` có kết quả phép nhân chính xác (nếu tài nguyên và biểu diễn cho phép), `rounded` có thể đã bỏ chữ số theo context. Chỉ một tham số `work` được truyền tới phép nhân; nó không gắn vĩnh viễn vào `a`, `b` hoặc vào JVM.

Khi thiết kế chuỗi phép tính, chọn nhất quán:

- **Cần tính chính xác toàn bộ trước thời điểm chốt:** ưu tiên dùng toán tử chính xác cho các phép toán có thể biểu diễn hữu hạn, chỉ dùng rounding tại ranh giới được xác định.
- **Cần giới hạn độ chính xác ở từng bước** (mô phỏng một chuẩn decimal arithmetic hoặc để kiểm soát độ phức tạp): truyền `MathContext` vào từng phép toán theo chính sách, và chấp nhận rằng intermediate rounding làm đổi giá trị.
- **Có phép chia vô hạn:** lựa chọn scale và rounding cụ thể hoặc `MathContext` với precision hữu hạn; không chờ JVM đoán policy.

Ví dụ:

~~~java
BigDecimal left = new BigDecimal("123.456");
BigDecimal right = new BigDecimal("0.789");
MathContext work = new MathContext(4, RoundingMode.HALF_EVEN);

System.out.println(left.multiply(right));       // 97.406784
System.out.println(left.multiply(right, work)); // 97.41
~~~

Khi phép nhân đã trả `97.41`, việc gọi `setScale(6)` chỉ tạo `97.410000`; nó **không** khôi phục `0.003216` đã mất trong lần rounding trước.

## 6. Phép chia: điểm cần quyết định chiến lược rõ nhất

Phép chia `1 / 3` có biểu diễn thập phân vô hạn. `BigDecimal` không mặc định âm thầm chọn số chữ số:

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

// one.divide(three); // ArithmeticException: decimal expansion vô hạn
~~~

Có các lựa chọn chính:

~~~java
// 6 chữ số có nghĩa:
BigDecimal withContext = one.divide(
        three, new MathContext(6, RoundingMode.HALF_EVEN)
); // 0.333333

// Cố định 2 chữ số sau dấu thập phân:
BigDecimal fixedScale = one.divide(
        three, 2, RoundingMode.HALF_UP
); // 0.33
~~~

| Overload | Quy tắc kết quả | Khi nào dùng |
|---|---|---|
| `divide(divisor)` | Phải chính xác; phép chia không hữu hạn sẽ lỗi | Giá trị quotient cần chính xác và biết biểu diễn hữu hạn |
| `divide(divisor, mathContext)` | Giới hạn số chữ số có nghĩa | Tính xấp xỉ với precision xác định |
| `divide(divisor, newScale, roundingMode)` | Đặt scale của kết quả | Chốt tỷ lệ/đơn vị ở đúng số chữ số sau dấu phẩy |
| `divide(divisor, roundingMode)` | Dùng scale của **số bị chia** để tạo kết quả | Dễ gây bất ngờ nếu scale đầu vào không được chuẩn hóa |

**Tránh overload chỉ có `RoundingMode` nếu scale số bị chia không phải một phần của chính sách.** Ví dụ:

~~~java
BigDecimal divisor = new BigDecimal("3");
System.out.println(new BigDecimal("2.0").divide(divisor, RoundingMode.HALF_UP));
// 0.7
System.out.println(new BigDecimal("2.00").divide(divisor, RoundingMode.HALF_UP));
// 0.67
~~~

Hai số bị chia cùng giá trị số 2 nhưng khác scale, làm hai phép chia dùng scale kết quả khác nhau. Vì vậy API thiết kế cho hệ thống cần xác định **tính chính xác, precision hoặc scale** bằng tham số nghiệp vụ thay vì dựa ngầm vào cách nhập chuỗi.

Phép chia cho 0 luôn không hợp lệ, kể cả khi có context; cần xử lý `ArithmeticException`/validate divisor theo hợp đồng.

## 7. MathContext.UNLIMITED và RoundingMode.UNNECESSARY

`MathContext.UNLIMITED` có `precision = 0`; các phép toán với precision 0 yêu cầu **kết quả chính xác**, và cấu hình `RoundingMode` không có vai trò làm tròn khi precision 0. Giá trị `MathContext.UNLIMITED` có rounding mode mặc định nhưng không làm cho `1/3` trở thành một số thập phân hữu hạn.

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

// Cả hai đều ném ArithmeticException:
one.divide(three);
one.divide(three, MathContext.UNLIMITED);
~~~

`UNNECESSARY` thì khác: nó là một **kiểm tra không được phép làm tròn**, có thể dùng cả với context có precision hữu hạn và `setScale`.

~~~java
BigDecimal ok = new BigDecimal("2.340");
System.out.println(ok.setScale(2, RoundingMode.UNNECESSARY)); // 2.34

// Ném ArithmeticException: mất chữ số 5:
new BigDecimal("2.345").setScale(2, RoundingMode.UNNECESSARY);

// Ném ArithmeticException: cần precision > 3 để giữ nguyên:
new BigDecimal("2.345").round(
        new MathContext(3, RoundingMode.UNNECESSARY));
~~~

Dùng `UNNECESSARY` tại biên dữ liệu khi **chính sách yêu cầu chính xác** và muốn phát hiện đầu vào không phù hợp thay vì làm tròn âm thầm. Ví dụ đầu vào tiền được quy định tối đa 2 chữ số thập phân có thể kiểm tra bằng `setScale(2, RoundingMode.UNNECESSARY)` rồi từ chối `"12.345"` nếu đúng quy tắc.

`UNNECESSARY` không đồng nghĩa với “không bao giờ có ngoại lệ” hay “chỉ ghi log”; nó **chủ động làm phép toán thất bại** nếu phải bỏ chữ số có nghĩa.

## 8. Ranh giới làm tròn: mỗi dòng hay tổng cuối?

Tính toán thập phân không chỉ phụ thuộc rounding mode mà còn **thời điểm làm tròn**. Xét ba khoản giống nhau `1.005` và chính sách `HALF_UP` về 2 chữ số:

**Cách A: làm tròn từng khoản rồi cộng**

~~~java
BigDecimal each = new BigDecimal("1.005")
        .setScale(2, RoundingMode.HALF_UP); // 1.01
BigDecimal totalA = each.multiply(new BigDecimal("3"));
// 3.03
~~~

**Cách B: cộng trước rồi làm tròn tổng**

~~~java
BigDecimal exactTotal = new BigDecimal("1.005")
        .multiply(new BigDecimal("3"));     // 3.015
BigDecimal totalB = exactTotal.setScale(2, RoundingMode.HALF_UP);
// 3.02
~~~

Hai số đều hợp lý **theo hai quy tắc chốt giá trị khác nhau**; chúng không tương đương. Chênh lệch `0.01` xuất hiện dù cùng đầu vào, cùng kiểu `BigDecimal`, cùng `RoundingMode.HALF_UP` và cùng target scale.

Điều phải làm trong thiết kế là quy định:

- Chốt làm tròn **từng dòng hóa đơn** rồi tính tổng?
- Hay giữ nguyên từng giá trị trung gian, **làm tròn một lần khi chốt tổng**?
- Thuế áp dụng trên từng dòng hay trên tổng sau chiết khấu?
- Các phần lẻ bị phân bổ thế nào nếu tổng phải bằng tổng chi tiết sau chốt?
- Khi có hoàn tiền hoặc điều chỉnh âm, mode và thứ tự thao tác có được áp dụng nhất quán không?

Đừng đổi vị trí rounding chỉ để test qua: thay đổi đó có thể làm sai số dư hoặc hợp đồng nghiệp vụ.

## 9. Chương trình Java 17 chạy độc lập và kết quả chuẩn

Tạo tệp `DecimalDesignDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class DecimalDesignDemo {
    private static final MathContext WORK =
            new MathContext(4, RoundingMode.HALF_EVEN);
    private static final int MONEY_SCALE = 2;
    private static final RoundingMode MONEY_ROUND = RoundingMode.HALF_UP;

    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("123.456");
        BigDecimal b = new BigDecimal("0.789");
        System.out.println("exact add = " + a.add(b));
        System.out.println("context add = " + a.add(b, WORK));
        System.out.println("exact multiply = " + a.multiply(b));
        System.out.println("context multiply = " + a.multiply(b, WORK));
        System.out.println("prec and scale = "
                + a.precision() + " / " + a.scale());

        BigDecimal one = BigDecimal.ONE;
        BigDecimal three = new BigDecimal("3");
        System.out.println("division context = "
                + one.divide(three,
                        new MathContext(6, RoundingMode.HALF_EVEN)));
        System.out.println("division fixed scale = "
                + one.divide(three, MONEY_SCALE, MONEY_ROUND));

        BigDecimal halfUp = new BigDecimal("2.345")
                .setScale(2, RoundingMode.HALF_UP);
        BigDecimal halfEven = new BigDecimal("2.345")
                .setScale(2, RoundingMode.HALF_EVEN);
        System.out.println("half up / even = " + halfUp + " / " + halfEven);
        System.out.println("negative half up = "
                + new BigDecimal("-2.345")
                        .setScale(2, RoundingMode.HALF_UP));
        System.out.println("round precision = "
                + new BigDecimal("999.9")
                        .round(new MathContext(3, RoundingMode.HALF_UP)));
        System.out.println("money 12345.00 = "
                + new BigDecimal("12345").setScale(2));

        BigDecimal x = new BigDecimal("1.005");
        BigDecimal each = x.setScale(2, MONEY_ROUND)
                .multiply(new BigDecimal("3"));
        BigDecimal end = x.multiply(new BigDecimal("3"))
                .setScale(2, MONEY_ROUND);
        System.out.println("round each = " + each);
        System.out.println("round at end = " + end);

        try {
            one.divide(three);
        } catch (ArithmeticException ex) {
            System.out.println("unlimited divide = ArithmeticException");
        }
        try {
            new BigDecimal("2.345")
                    .setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            System.out.println("unnecessary scale = ArithmeticException");
        }
        try {
            new BigDecimal("2.345").round(
                    new MathContext(3, RoundingMode.UNNECESSARY));
        } catch (ArithmeticException ex) {
            System.out.println("unnecessary precision = ArithmeticException");
        }
        System.out.println("exact scale = "
                + new BigDecimal("2.340")
                        .setScale(2, RoundingMode.UNNECESSARY));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 DecimalDesignDemo.java
java DecimalDesignDemo
~~~

Kết quả được kiểm chứng:

~~~text
exact add = 124.245
context add = 124.2
exact multiply = 97.406784
context multiply = 97.41
prec and scale = 6 / 3
division context = 0.333333
division fixed scale = 0.33
half up / even = 2.35 / 2.34
negative half up = -2.35
round precision = 1.00E+3
money 12345.00 = 12345.00
round each = 3.03
round at end = 3.02
unlimited divide = ArithmeticException
unnecessary scale = ArithmeticException
unnecessary precision = ArithmeticException
exact scale = 2.34
~~~

Chú ý dòng `round precision = 1.00E+3`: khi `999.9` làm tròn thành ba chữ số có nghĩa, phép làm tròn có carry sang hàng nghìn. `MathContext` không buộc kết quả in dạng `1000.00` hay giữ nguyên scale ban đầu.

Trong chương trình, `WORK` là một chính sách **minh họa** cho bài tập, không phải khuyến nghị rằng mọi hệ thống tiền tệ nên lấy 4 chữ số có nghĩa. `MONEY_SCALE = 2` cũng là giả định của bài tập, không áp dụng mặc định cho mọi đơn vị tiền trên thế giới.

## 10. Thiết kế một luồng xử lý thập phân theo nghiệp vụ

Một quy trình dễ kiểm toán tách bốn giai đoạn:

~~~text
Input decimal đã được xác thực
        |
        v
Giá trị BigDecimal nguyên bản + đơn vị + metadata
        |
        v
Phép toán có quy tắc precision/rounding công khai
        |
        v
Điểm chốt: setScale hoặc chia với scale cố định
        |
        +---> Giá trị đã chốt đem lưu/xuất machine-readable
        |
        +---> Chuỗi hiển thị theo locale và định dạng UI
~~~

**Bước 1 — Xác định đơn vị:** `12.34` là 12.34 đồng, 12.34 USD, hay tỷ lệ 12.34%? Số decimal không mang theo đơn vị; lưu đơn vị với dữ liệu hoặc trong kiểu miền nghiệp vụ.

**Bước 2 — Xác định độ chính xác đầu vào:** số được nhập tối đa mấy chữ số sau dấu thập phân, giới hạn độ lớn ra sao, có chấp nhận ký pháp mũ, số âm và số 0 không?

**Bước 3 — Xác định policy phép toán:** nếu chỉ cộng/nhân chính xác với dữ liệu hữu hạn và kích thước trong khả năng tài nguyên, có thể không cần round ở mỗi thao tác. Nếu có phép chia vô hạn, cần chọn context/scale và rounding. Với thuật toán mô phỏng precision cố định, truyền `MathContext` nhất quán qua các bước cần thiết.

**Bước 4 — Xác định thời điểm chốt:** một giao dịch có thể yêu cầu làm tròn từng dòng trước khi cộng; thuật toán khác có thể yêu cầu cộng chính xác rồi round kết quả. Phải viết điều này trong code và test.

**Bước 5 — Tách lưu trữ và hiển thị:** `toPlainString()`, `toString()`, `DecimalFormat` và `setScale()` có tác dụng khác nhau. Định dạng chuỗi có thể chọn dấu phẩy, dấu chấm và ký hiệu tiền theo locale, nhưng việc format chỉ để hiển thị **không thay giá trị BigDecimal gốc**.

Một đối tượng policy giúp tránh những phép tính dùng mode “mỗi nơi một kiểu”:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public final class DecimalPolicy {
    private final int scale;
    private final RoundingMode rounding;

    public DecimalPolicy(int scale, RoundingMode rounding) {
        this.scale = scale;
        this.rounding = java.util.Objects.requireNonNull(rounding);
    }

    public BigDecimal finish(BigDecimal value) {
        return java.util.Objects.requireNonNull(value)
                .setScale(scale, rounding);
    }
}
~~~

Đoạn này là **lớp độc lập có thể biên dịch khi lưu vào `DecimalPolicy.java`** nhưng chưa có `main`; nó thể hiện nơi đặt chính sách chốt giá trị. Đối với ứng dụng thật, cần validate `scale` phù hợp quy tắc, đơn vị và giới hạn tài nguyên, đồng thời thêm test cho số âm, tie và giá trị vượt giới hạn.

## 11. MathContext không tự áp đặt số chữ số thập phân cho tiền

`MathContext.DECIMAL32`, `DECIMAL64` và `DECIMAL128` lần lượt có precision **7, 16, 34** và `RoundingMode.HALF_EVEN`. Đây là những cấu hình precision tiện dùng, không phải quy định tiền tệ.

~~~java
MathContext a = MathContext.DECIMAL32;  // precision 7
MathContext b = MathContext.DECIMAL64;  // precision 16
MathContext c = MathContext.DECIMAL128; // precision 34
~~~

Dùng `DECIMAL64` không có nghĩa kết quả luôn là **hai chữ số sau dấu phẩy**, và cũng không tự hạn chế exponent/scale như toàn bộ một định dạng IEEE decimal64 vật lý. `BigDecimal` với context có precision tương ứng nhưng không ràng buộc tập scale/exponent giống hệt định dạng IEEE.

Với một đơn vị tiền có chính sách chốt hai chữ số, cần thao tác `setScale(2, mode)` tại ranh giới thích hợp hoặc lưu số nguyên đơn vị nhỏ nhất nếu quy trình phù hợp. Không dùng context precision 2, precision 16 hay “DECIMAL64” làm tên khác của `scale = 2`.

Nếu yêu cầu là **tỷ lệ phần trăm** có 6 chữ số có nghĩa, có thể dùng context 6 và chuyển đổi đơn vị đúng hợp đồng; đừng coi 0.075, 7.5% và 7.5 là cùng một số không cần quy tắc.

## 12. Làm tròn sớm và làm tròn kép

Làm tròn có thể không có tính phân phối hoặc kết hợp như phép toán số học chính xác. Một ví dụ đặc biệt nguy hiểm là **làm tròn một kết quả rồi lại làm tròn lần nữa theo scale khác**.

Xét `2.345` với `HALF_UP`:
- Trực tiếp `setScale(1, HALF_UP)` cho `2.3`, vì chữ số thứ hai là 4;
- Nếu `setScale(2, HALF_UP)` trước, được `2.35`, rồi `setScale(1, HALF_UP)` lần nữa, kết quả là `2.4`.

~~~java
BigDecimal x = new BigDecimal("2.345");
BigDecimal direct = x.setScale(1, RoundingMode.HALF_UP);
BigDecimal twice = x.setScale(2, RoundingMode.HALF_UP)
                    .setScale(1, RoundingMode.HALF_UP);

System.out.println(direct); // 2.3
System.out.println(twice);  // 2.4
~~~

Đây là **double rounding**: kết quả cuối có thể thay đổi khi round qua một precision/scale trung gian. Do đó, nếu ứng dụng yêu cầu chốt một lần ở scale 1, không tự ý đưa vào một bước `setScale(2)` chỉ để “chuẩn hóa định dạng”.

Điều này cũng xảy ra khi quy trình dùng `MathContext` ở các phép toán trước, rồi lại dùng `setScale` ở cuối: hai lần rounding có thể cho kết quả khác so với tính chính xác rồi chốt một lần. Không có chiến lược phổ quát — tính toán với precision giới hạn có thể là yêu cầu bắt buộc. Điều quan trọng là **biết rõ bước nào làm thay đổi giá trị** và viết test theo đúng thứ tự xử lý.

## 13. BigDecimal.equals(), compareTo() và scale sau phép tính

Hai `BigDecimal` có thể bằng nhau về giá trị số nhưng khác biểu diễn:

~~~java
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = new BigDecimal("2.00");

System.out.println(x.compareTo(y) == 0); // true
System.out.println(x.equals(y));         // false
~~~

`compareTo()` dùng thứ tự **theo giá trị số**; `equals()` còn xét `scale`. Vì vậy một bước `setScale(2)` có thể làm thay đổi kết quả `equals()` nhưng không làm thay đổi phép so sánh số học. Khi làm khóa cho `HashMap` hoặc phần tử trong `HashSet`, cần xác định rõ danh tính bao gồm scale hay không.

`stripTrailingZeros()` bỏ số 0 tận cùng mà không đổi giá trị số nhưng có thể làm scale âm:

~~~java
BigDecimal amount = new BigDecimal("1000.00");
System.out.println(amount.stripTrailingZeros()); // 1E+3
~~~

Nếu chính sách lưu trữ yêu cầu `"1000.00"`, đừng gọi `stripTrailingZeros` như một bước format bắt buộc. `MathContext`, `setScale`, `stripTrailingZeros` và `toPlainString()` phục vụ những chức năng khác nhau.

## 14. Kiểm tra ngoại lệ và giới hạn đầu vào

Một thiết kế tốt cần chủ động xử lý các lỗi thay vì chỉ bắt mọi `ArithmeticException` rồi cho 0:

| Tình huống | Phản ứng hợp lý |
|---|---|
| Chia cho 0 | Từ chối divisor 0; báo lỗi miền nghiệp vụ |
| `divide` chính xác nhưng kết quả không hữu hạn | Yêu cầu policy precision/scale + rounding, hoặc từ chối nếu nghiệp vụ bắt buộc chính xác |
| `setScale(2, UNNECESSARY)` phải bỏ chữ số khác 0 | Từ chối dữ liệu không tuân thủ scale đã thỏa thuận |
| `new MathContext(-1, mode)` | `IllegalArgumentException`, vì precision không được âm |
| Giới hạn chữ số đầu vào quá lớn | Validate độ dài/giá trị, chống tiêu thụ CPU và bộ nhớ quá mức |
| Kết quả vượt schema DECIMAL của database | Kiểm tra trước khi lưu, không trông chờ cơ sở dữ liệu tự làm tròn đúng chính sách |
| Chuyển `BigDecimal` sang `int`/`long` | Dùng `intValueExact()`/`longValueExact()` nếu không được phép mất phần lẻ hoặc tràn số |

`BigDecimal` hỗ trợ precision tùy ý về mặt khái niệm nhưng vẫn phụ thuộc tài nguyên máy, miền `scale` kiểu `int` và giới hạn thư viện. Một input số mũ cực đoan, chuỗi decimal khổng lồ hoặc yêu cầu `toPlainString()` với exponent lớn có thể gây tiêu tốn bộ nhớ đáng kể. Xác thực giới hạn dữ liệu không kém quan trọng so với chọn rounding mode.

Không bắt `ArithmeticException` rồi trả `BigDecimal.ZERO` một cách chung chung: nó che cả lỗi chia 0, sai chính sách rounding và dữ liệu không hợp lệ, làm kết quả sai mà khó kiểm toán.

## 15. Các test cần có cho chính sách thập phân

Một bộ kiểm thử nên gồm ít nhất những nhóm sau:

1. **Giữa hai giá trị (tie):** `2.345` với scale 2 cho `HALF_UP = 2.35`, `HALF_EVEN = 2.34`.
2. **Số âm:** `-2.345` với `HALF_UP` và các mode hướng tới ±∞.
3. **Chia vô hạn:** `1 / 3` phải dùng context/scale; kiểm tra ngoại lệ khi dùng overload chính xác.
4. **Chia hữu hạn:** `1 / 8 = 0.125` không cần rounding nếu để kết quả chính xác.
5. **Rounding từng dòng so với tổng:** `1.005 × 3` tạo `3.03` hoặc `3.02` tùy policy.
6. **Scale của kết quả:** `setScale(2)` cho `12345.00`, trong khi precision 3 có thể biến 12345 thành `1.23E+4`.
7. **Không mất dữ liệu bắt buộc:** `UNNECESSARY` từ chối `2.345` khi cần scale 2 nhưng cho phép `2.340` về `2.34`.
8. **Overflow khi ép kiểu và giới hạn lưu trữ:** kiểm tra `longValueExact()` khi chuyển sang đơn vị nhỏ nhất.
9. **Bất biến giá trị ban đầu:** vì `BigDecimal` immutable, tính toán/format không sửa instance gốc.
10. **Chính sách đầu vào:** từ chối định dạng/giá trị ngoài hợp đồng trước khi tính và lưu.

Ở cấp ứng dụng, nên test luôn **kết quả giá trị** và nếu cần **scale**:

~~~java
BigDecimal actual = new BigDecimal("2.340").setScale(2);
BigDecimal expected = new BigDecimal("2.34");

System.out.println(actual.equals(expected));     // true
System.out.println(actual.compareTo(expected));  // 0
~~~

Không viết một test chỉ so sánh chuỗi UI khi chức năng cần xác minh giá trị số; ngược lại, nếu hợp đồng yêu cầu giữ đúng hai chữ số sau dấu thập phân, kiểm tra cả `scale()` hoặc format đầu ra thích hợp.

## 16. Bài tập tự thực hành

### Bài 1 — precision hay scale?

Với `x = new BigDecimal("98765.4321")`, bạn muốn:
- (A) giữ bốn chữ số có nghĩa;
- (B) giữ hai chữ số sau dấu thập phân.

**Đáp án định hướng:** (A) gọi `x.round(new MathContext(4, policy))`; (B) gọi `x.setScale(2, policy)`. Đây không phải hai cách viết của cùng một kết quả. Với `HALF_UP`, (A) là `9.877E+4`, còn (B) là `98765.43`. Cần chọn chính sách trước khi triển khai.

### Bài 2 — chốt từng dòng

Ba đơn giá đều là `1.005` đơn vị tiền và phải xuất tổng hai chữ số. Hãy nêu hai kết quả hợp lệ theo hai chính sách khác nhau.

**Đáp án:** Làm tròn từng dòng theo `HALF_UP`: `1.01 × 3 = 3.03`. Cộng trước rồi làm tròn tổng: `3.015 → 3.02`. Phải ghi rõ quy tắc mà nghiệp vụ yêu cầu.

### Bài 3 — divide() báo lỗi

`new BigDecimal("1").divide(new BigDecimal("3"))` ném ngoại lệ dù không chia cho 0. Vì sao?

**Đáp án:** Vì `1/3` có khai triển decimal vô hạn, nên phép chia chính xác không thể trả một `BigDecimal` hữu hạn. Phải quy định precision/scale và rounding hoặc từ chối phép tính nếu yêu cầu chính xác tuyệt đối.

### Bài 4 — MathContext.UNLIMITED

`MathContext.UNLIMITED` có tự làm `1/3` thành một số hữu hạn không?

**Đáp án:** Không. `precision = 0` yêu cầu tính toán chính xác không làm tròn; phép chia có kết quả decimal vô hạn sẽ báo `ArithmeticException`.

### Bài 5 — ROUND_UNNECESSARY

Với `new BigDecimal("7.500")` và `new BigDecimal("7.505")`, giá trị nào có thể chuyển sang scale 2 bằng `RoundingMode.UNNECESSARY`?

**Đáp án:** `7.500 → 7.50` chính xác; `7.505` không thể giữ nguyên giá trị khi scale 2, nên ném ngoại lệ.

### Bài 6 — double rounding

Giả sử yêu cầu cuối là một chữ số thập phân, rounding `HALF_UP`. So sánh:
- `new BigDecimal("2.345").setScale(1, HALF_UP)`;
- `new BigDecimal("2.345").setScale(2, HALF_UP).setScale(1, HALF_UP)`.

**Đáp án:** Trực tiếp ra `2.3`, qua trung gian ra `2.4`. Không thêm bước làm tròn trung gian nếu hợp đồng không yêu cầu.

## 17. Checklist trước khi đưa vào sản phẩm

Trước khi áp dụng `MathContext` và `RoundingMode` trong nghiệp vụ thật, xác nhận:

- Đầu vào là số decimal chính xác từ chuỗi, số nguyên đơn vị nhỏ nhất hoặc nguồn có hợp đồng rõ, không âm thầm đi qua `double` ngoài ý muốn.
- Đơn vị, precision đầu vào, scale chốt và giới hạn độ lớn đều được định nghĩa.
- Các phép toán cần precision hữu hạn được truyền cùng `MathContext` theo đúng phương án tính toán, không nhầm với scale.
- Phép chia xác định explicit scale/precision, mode và quy tắc xử lý divisor 0.
- Biết rõ lúc nào tính chính xác, lúc nào round; không để vòng tính “round mỗi bước” xuất hiện ngẫu nhiên.
- Quy tắc `HALF_UP`, `HALF_EVEN`, `CEILING`, `FLOOR`, `UNNECESSARY` được chọn có lý do từ nghiệp vụ và có test số âm/tie.
- Dữ liệu sau chốt được lưu đúng schema và đơn vị; format UI là trách nhiệm riêng.
- Nếu cần chứng minh không mất chữ số, dùng `UNNECESSARY` và xử lý lỗi, không chỉ âm thầm làm tròn.
- Có ví dụ kiểm thử cho precision khác scale, rounding từng dòng vs tổng cuối và double rounding.
- Tất cả API public hoặc trường lưu trữ dùng policy nhất quán, tránh “mỗi chỗ một mặc định” làm lệch số liệu.

## 18. Tài liệu tham khảo

- [BigDecimal — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `precision`, `scale`, preferred scales, `add`, `multiply`, `divide`, `setScale`, `round`, `stripTrailingZeros`.
- [MathContext — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html): `precision`, `roundingMode`, `UNLIMITED`, `DECIMAL32`, `DECIMAL64`, `DECIMAL128`.
- [RoundingMode — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): tám chính sách làm tròn và ví dụ xử lý các trường hợp midpoint.
