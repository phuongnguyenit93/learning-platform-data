# Chia không hữu hạn và lựa chọn chính sách làm tròn

## 1. Vì sao dùng BigDecimal vẫn có thể không chia chính xác được?

`BigDecimal` lưu số thập phân hữu hạn với độ chính xác tùy ý trong giới hạn tài nguyên. Điều đó giúp biểu diễn chính xác các đầu vào như 0.1 hoặc 12.375, nhưng không có nghĩa mọi thương đều lưu được chính xác bằng một `BigDecimal`.

Ví dụ:

```text
6 / 15 = 0.4          → có biểu diễn thập phân hữu hạn
5 / 12 = 0.416666...  → phần thập phân không kết thúc
```

Đối với 5/12, tăng số chữ số chỉ làm kết quả gần hơn, không biến thương thành một số thập phân hữu hạn chính xác. Java cần biết phải trả về kết quả gần đúng nào, hoặc phải từ chối nếu ứng dụng yêu cầu chính xác.

Đây là lý do gọi `a.divide(b)` có thể ném `ArithmeticException`: overload đó yêu cầu thương chính xác. Nó không tự đoán số chữ số cần giữ.

Trong bài này, “chia không hữu hạn” nói về khai triển thập phân của thương không kết thúc; không phải chia cho 0 và không có nghĩa chương trình phải chạy vô hạn.

## 2. Khi nào thương có dạng thập phân hữu hạn?

Với phân số hữu tỉ đã tối giản và mẫu khác 0, thương có biểu diễn thập phân hữu hạn khi mẫu dương chỉ chứa các thừa số nguyên tố 2 và 5. Lý do là các mẫu đó có thể được nhân thành một lũy thừa của 10.

Ví dụ:

| Phép chia | Sau khi tối giản | Kết luận |
| --- | --- | --- |
| 6/15 | 2/5 | Hữu hạn: 0.4 |
| 7/40 | 7/(2³ × 5) | Hữu hạn: 0.175 |
| 5/12 | 5/(2² × 3) | Không kết thúc vì còn thừa số 3 |
| 14/21 | 2/3 | Không kết thúc |
| 0/7 | 0/1 | Hữu hạn: 0 |

Phải xét mẫu sau khi tối giản. Nhìn thấy số 15 có thừa số 3 rồi kết luận 6/15 không hữu hạn là sai, vì thừa số 3 đã được khử.

Hai đầu vào `BigDecimal` đều là các số hữu tỉ hữu hạn. Về mặt toán học, có thể quy chúng về phân số nguyên rồi áp dụng quy tắc trên; không cần chuyển sang `double` để kiểm tra. Trong mã ứng dụng thông thường, không nhất thiết tự viết thuật toán phân tích mẫu: hãy chọn phép chia chính xác hoặc phép chia có làm tròn theo yêu cầu.

Nếu cần bảo toàn một tỷ số chính xác như 5/12 xuyên suốt nhiều phép biến đổi, có thể giữ riêng tử/mẫu dưới dạng số nguyên thay vì ép thành `BigDecimal` sớm. Đó là một lựa chọn mô hình dữ liệu, không phải một chế độ làm tròn khác.

## 3. Bốn cách gọi divide cần phân biệt

| Cách gọi | Ý nghĩa chính |
| --- | --- |
| `a.divide(b)` | Trả thương chính xác; từ chối thương không có dạng thập phân hữu hạn |
| `a.divide(b, scale, mode)` | Trả thương ở scale chỉ định |
| `a.divide(b, mc)` | Áp dụng precision và roundingMode của `MathContext` |
| `a.divide(b, mode)` | Dùng scale hiện có của số bị chia `a` |

Cả bốn đều từ chối mẫu số 0. Dùng các overload nhận enum `RoundingMode` trong mã mới; không dùng hằng làm tròn kiểu `int` đã deprecated. Tham khảo hợp đồng từng overload trong [BigDecimal API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html).

### 3.1. Chính xác là một yêu cầu có thể thất bại

```java
BigDecimal result = new BigDecimal("6").divide(new BigDecimal("15"));
// Giá trị là 0.4.

BigDecimal impossible = new BigDecimal("5").divide(new BigDecimal("12"));
// Ném ArithmeticException.
```

Các đoạn mã ngắn trong bài nằm trong một phương thức và cần import các lớp được dùng từ `java.math`.

Không nên bắt ngoại lệ của phép chia không hữu hạn rồi trả về 0. Số 0 không biểu thị thương của 5/12 và sẽ che mất lỗi chính sách. Nếu ứng dụng cho phép kết quả gần đúng, hãy cấu hình phép chia đó rõ ràng.

### 3.2. Scale: giữ vị trí thập phân cố định

```java
BigDecimal result = new BigDecimal("5")
        .divide(new BigDecimal("12"), 4, RoundingMode.HALF_UP);
// result.toPlainString() là "0.4167".
```

Scale bằng 4 yêu cầu bốn chữ số sau dấu chấm. Với thương 100/6, cùng chính sách cho `16.6667`: vẫn là bốn chữ số sau dấu chấm, nhưng tổng số chữ số có nghĩa khác.

Khi thương có thể biểu diễn chính xác ở scale đó, việc chọn mode không làm thay đổi giá trị số. Ví dụ 6/15 ở scale 2 cho `0.40`.

### 3.3. MathContext: giữ số chữ số có nghĩa

```java
MathContext mc = new MathContext(4, RoundingMode.HALF_UP);
BigDecimal result = new BigDecimal("100").divide(new BigDecimal("6"), mc);
// result.toPlainString() là "16.67".
```

Precision bằng 4 giới hạn tổng chữ số có nghĩa, không phải chữ số sau dấu chấm. Cần chọn theo độ lớn và yêu cầu độ chính xác của phép tính.

Precision bằng 0, chẳng hạn `MathContext.UNLIMITED`, yêu cầu phép tính chính xác; nó không cho phép giữ vô hạn chữ số của một thương tuần hoàn. 5/12 với context đó vẫn thất bại.

### 3.4. Overload chỉ có mode có thể làm tròn nhiều hơn dự định

```java
BigDecimal first = new BigDecimal("5")
        .divide(new BigDecimal("12"), RoundingMode.HALF_UP);

BigDecimal second = new BigDecimal("5.00")
        .divide(new BigDecimal("12"), RoundingMode.HALF_UP);
```

`first` là `0`, vì scale của `"5"` bằng 0. `second` là `0.42`, vì scale của `"5.00"` bằng 2.

Hai số bị chia bằng nhau về giá trị số, nhưng overload này phụ thuộc biểu diễn của số bị chia. Khi ứng dụng yêu cầu scale cụ thể, truyền scale một cách tường minh để tránh kết quả phụ thuộc vào cách đầu vào được viết.

## 4. Chính sách làm tròn gồm nhiều quyết định

Chỉ chọn `HALF_UP` hoặc `HALF_EVEN` là chưa đủ để xác định toàn bộ phép tính.

### 4.1. Có cho phép xấp xỉ không?

Nếu không cho phép mất thông tin, dùng phép chia chính xác hoặc `UNNECESSARY` với giới hạn đầu ra cần kiểm tra. Khi thất bại, ứng dụng phải báo rằng điều kiện không được đáp ứng.

Nếu được phép xấp xỉ, cần công bố độ chính xác và cách làm tròn. Đừng dựa vào một scale tình cờ của biến đầu vào.

### 4.2. Giữ vị trí thập phân hay chữ số có nghĩa?

- Scale phù hợp khi hợp đồng yêu cầu đơn vị nhỏ nhất cố định, chẳng hạn bốn chữ số sau dấu chấm.
- Precision phù hợp khi yêu cầu số chữ số có nghĩa được giữ qua các giá trị có độ lớn khác nhau.
- Định dạng chuỗi đầu ra là việc tiếp theo; nó không khôi phục phần thông tin đã bị làm tròn.

Ví dụ 100/6 với scale 4 cho 16.6667; precision 4 cho 16.67. Cả hai đều đúng với chính sách riêng.

### 4.3. Chọn hướng hoặc quy tắc phá hòa

| Chế độ | Khi cần bỏ thông tin |
| --- | --- |
| `HALF_UP` | Gần nhất, chính giữa thì xa 0 |
| `HALF_DOWN` | Gần nhất, chính giữa thì về 0 |
| `HALF_EVEN` | Gần nhất, chính giữa thì chọn chữ số cuối được giữ là chẵn |
| `DOWN` | Về phía 0 |
| `UP` | Ra xa 0 |
| `FLOOR` | Về phía âm vô cùng |
| `CEILING` | Về phía dương vô cùng |
| `UNNECESSARY` | Từ chối nếu phải làm tròn |

Với -5/12 ở scale 2, `DOWN` và `CEILING` cho -0.41; `UP` và `FLOOR` cho -0.42. Số âm làm lộ sự khác nhau giữa “về 0” và “về âm vô cùng”.

Không có một mode đúng cho mọi bài toán. Cần tuân thủ quy tắc của dữ liệu hoặc thuật toán. Định nghĩa các chế độ có tại [RoundingMode API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/RoundingMode.html).

### 4.4. Chọn thời điểm làm tròn

Kết quả trung gian có thể bị làm tròn trước khi các bước sau sử dụng. Ví dụ:

```text
2 / 7 ở scale 2, HALF_UP → 0.29
0.29 × 7                → 2.03
```

Làm tròn lại 2.03 về hai chữ số sau dấu chấm không thể lấy lại số 2 ban đầu.

Có thể giữ nhiều chữ số hơn cho bước trung gian rồi làm tròn ở đầu ra. Tuy nhiên, một số chữ số dự phòng tùy ý không bảo đảm đúng với mọi biểu thức, và làm tròn hai lần cũng có thể đổi kết quả tại các ranh giới. Cần kiểm tra các trường hợp biên hoặc phân tích sai số theo thuật toán.

Nếu đại số cho phép rút gọn phép chia trước khi tính, có thể tránh việc tạo ra thương gần đúng không cần thiết. Việc rút gọn phải giữ nguyên miền hợp lệ của biểu thức, đặc biệt điều kiện mẫu khác 0.

## 5. UNNECESSARY và các nguyên nhân ArithmeticException

`UNNECESSARY` không có nghĩa “cứ làm tròn theo một cách mặc định”. Nó khẳng định kết quả phải chính xác ở giới hạn đã yêu cầu.

```java
BigDecimal allowed = new BigDecimal("6")
        .divide(new BigDecimal("15"), 2, RoundingMode.UNNECESSARY);
// "0.40": không mất thông tin.

BigDecimal rejected = BigDecimal.ONE
        .divide(new BigDecimal("40"), 2, RoundingMode.UNNECESSARY);
// Ném ArithmeticException: 0.025 không thể biểu diễn chính xác ở scale 2.
```

Phép chia 1/40 có thương hữu hạn nhưng vẫn thất bại ở ví dụ thứ hai. Nguyên nhân là scale quá nhỏ, không phải khai triển thập phân không kết thúc.

Cần phân biệt:

| Tình huống | Ví dụ | Cách hiểu |
| --- | --- | --- |
| Mẫu bằng 0 | 5/0 | Phép toán không xác định; thêm precision không sửa được |
| Yêu cầu chính xác nhưng thương không hữu hạn | 5/12 với `divide(b)` | Cần đổi chính sách hoặc mô hình dữ liệu |
| Giới hạn quá chặt với `UNNECESSARY` | 1/40 ở scale 2 | Thương hữu hạn nhưng không vừa giới hạn |
| Kết quả chính xác vừa giới hạn | 6/15 ở scale 2 | Thành công, giá trị 0.40 |

Đừng phân loại lỗi chỉ bằng nội dung chuỗi thông báo ngoại lệ. Trong mã nghiệp vụ, có thể kiểm tra mẫu bằng 0 bằng `signum() == 0`, và xác định các điều kiện được phép dựa trên hợp đồng đầu vào. `equals(BigDecimal.ZERO)` có thể bỏ sót `new BigDecimal("0.00")` do scale khác nhau.

## 6. Chương trình hoàn chỉnh kiểm chứng các lựa chọn

Lưu thành `DivisionPolicyDemo.java`. Chương trình dùng API tương thích Java 17+ và tạo số từ chuỗi để giữ đúng đầu vào thập phân.

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class DivisionPolicyDemo {
    private static BigDecimal decimal(String value) {
        return new BigDecimal(value);
    }

    private static void show(String label, BigDecimal value) {
        System.out.println(label + "=" + value.toPlainString());
    }

    private static void expectArithmetic(String label, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Expected ArithmeticException: " + label);
        } catch (ArithmeticException exception) {
            System.out.println(label + "=ArithmeticException");
        }
    }

    public static void main(String[] args) {
        BigDecimal five = decimal("5");
        BigDecimal twelve = decimal("12");

        show("exact6over15", decimal("6").divide(decimal("15")));
        expectArithmetic("exact5over12", () -> five.divide(twelve));

        show("scale4", five.divide(twelve, 4, RoundingMode.HALF_UP));
        MathContext p4 = new MathContext(4, RoundingMode.HALF_UP);
        show("precision4Large", decimal("100").divide(decimal("6"), p4));
        show("scale4Large", decimal("100").divide(
                decimal("6"), 4, RoundingMode.HALF_UP));

        show("inheritedScale0", five.divide(twelve, RoundingMode.HALF_UP));
        show("inheritedScale2", decimal("5.00").divide(
                twelve, RoundingMode.HALF_UP));

        BigDecimal negative = decimal("-5");
        show("negativeDown", negative.divide(twelve, 2, RoundingMode.DOWN));
        show("negativeCeiling", negative.divide(twelve, 2, RoundingMode.CEILING));
        show("negativeUp", negative.divide(twelve, 2, RoundingMode.UP));
        show("negativeFloor", negative.divide(twelve, 2, RoundingMode.FLOOR));

        show("exactAtScale2", decimal("6").divide(
                decimal("15"), 2, RoundingMode.UNNECESSARY));
        expectArithmetic("insufficientScale", () -> BigDecimal.ONE.divide(
                decimal("40"), 2, RoundingMode.UNNECESSARY));
        expectArithmetic("unlimitedRepeating", () ->
                five.divide(twelve, MathContext.UNLIMITED));
        expectArithmetic("zeroDivisor", () ->
                five.divide(decimal("0.00"), 4, RoundingMode.HALF_UP));

        BigDecimal seven = decimal("7");
        BigDecimal two = decimal("2");
        BigDecimal early = two.divide(seven, 2, RoundingMode.HALF_UP)
                .multiply(seven);
        BigDecimal later = two.divide(seven, 12, RoundingMode.HALF_UP)
                .multiply(seven)
                .setScale(2, RoundingMode.HALF_UP);
        show("earlyRounding", early);
        show("laterRounding", later);

        BigDecimal total = decimal("10.00");
        BigDecimal count = decimal("3");
        BigDecimal share = total.divide(count, 2, RoundingMode.DOWN);
        BigDecimal allocated = share.multiply(count);
        BigDecimal residual = total.subtract(allocated);
        show("share", share);
        show("allocated", allocated);
        show("residual", residual);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 DivisionPolicyDemo.java
java DivisionPolicyDemo
```

Stdout:

```text
exact6over15=0.4
exact5over12=ArithmeticException
scale4=0.4167
precision4Large=16.67
scale4Large=16.6667
inheritedScale0=0
inheritedScale2=0.42
negativeDown=-0.41
negativeCeiling=-0.41
negativeUp=-0.42
negativeFloor=-0.42
exactAtScale2=0.40
insufficientScale=ArithmeticException
unlimitedRepeating=ArithmeticException
zeroDivisor=ArithmeticException
earlyRounding=2.03
laterRounding=2.00
share=3.33
allocated=9.99
residual=0.01
```

Hàm `expectArithmetic` dành cho minh chứng: nếu lời gọi đáng lẽ thất bại lại thành công, nó ném `AssertionError` để ví dụ không âm thầm xác nhận sai hành vi. Trong ứng dụng, xử lý ngoại lệ theo ý nghĩa của phép tính, không theo mẫu in thông báo của chương trình này.

Kết quả `laterRounding=2.00` chỉ cho thấy precision trung gian lớn hơn đã đủ trong ví dụ cụ thể. Thương trung gian vẫn gần đúng; không nên suy ra rằng scale 12 bảo đảm đúng cho mọi dữ liệu.

## 7. Chia đều không tự bảo đảm tổng các phần bằng tổng ban đầu

Ví dụ cuối chia 10.00 thành ba phần ở scale 2 theo `DOWN`:

```text
Mỗi phần:          3.33
Tổng ba phần:     9.99
Phần chưa phân bổ: 0.01
```

Một chế độ làm tròn không thể tạo ra ba phần vừa hoàn toàn bằng nhau ở đơn vị 0.01, vừa có tổng đúng 10.00. Muốn bảo toàn tổng phải có quy tắc phân bổ phần dư.

Chẳng hạn có thể tạo các phần 3.34, 3.33, 3.33. Nhưng chọn phần nào nhận 0.01 là quyết định riêng của ứng dụng: theo thứ tự ổn định, theo trọng số, hay theo một quy tắc được thỏa thuận. Không nên ngẫu nhiên cộng phần dư vào bản ghi cuối nếu yêu cầu chưa quy định điều đó.

Cần phân biệt ba khái niệm:

- **Sai số của một thương gần đúng:** chênh lệch so với giá trị toán học.
- **Phần dư sau phân bổ:** tổng ban đầu trừ tổng những phần đã tạo.
- **Phần dư của phép chia lấy thương nguyên:** kết quả của `remainder` khi chia thành số nhóm nguyên.

Chúng không phải cùng một đại lượng. `divideToIntegralValue` và `remainder` hữu ích khi thật sự cần thương nguyên/phần dư; dùng chúng thay cho thương thập phân chỉ để tránh ngoại lệ sẽ thay đổi bài toán.

## 8. Đánh giá độ chính xác thay vì chỉ nhìn số chữ số

Với một phép chia được làm tròn trực tiếp về scale s theo một chế độ gần nhất, bước giữa hai kết quả kề nhau là `10^(-s)`; sai số tuyệt đối của lần làm tròn không vượt quá nửa bước đó. Ví dụ scale 4 cho bước 0.0001 và sai số làm tròn không quá 0.00005.

Giới hạn này nói về một lần làm tròn so với thương chính xác của đầu vào hiện có. Nó không bao gồm sai số đo đầu vào, dữ liệu đã bị làm tròn ở nơi khác, hoặc sai số bị khuếch đại bởi các bước sau.

Khi dùng precision, độ lớn của bước phụ thuộc vào độ lớn kết quả. Vì vậy precision 4 không bảo đảm cùng một sai số tuyệt đối cho 0.001666 và 166600.

Khi thiết kế phép tính:

1. Xác định tiêu chí chấp nhận theo giá trị hoặc theo đơn vị đầu ra.
2. Giữ đủ thông tin ở trung gian dựa trên thuật toán.
3. Ghi rõ ranh giới làm tròn và mode.
4. Kiểm tra dữ liệu gần điểm giữa, giá trị nhỏ/lớn, số âm và mẫu gần 0.
5. Giới hạn độ dài dữ liệu/precision theo yêu cầu vận hành nếu đầu vào không được kiểm soát; precision cực lớn không phải một giải pháp miễn phí.

Không chuyển kết quả sang `double` giữa chừng để “dễ chia” rồi đổi lại `BigDecimal`. Cách đó đưa một chính sách số dấu phẩy động nhị phân khác vào chuỗi tính toán và không giải quyết yêu cầu làm tròn thập phân.

## 9. Thực hành

1. Phân loại 9/24, 7/28, 11/18 và 18/45 thành thương hữu hạn hoặc không hữu hạn. Hãy tối giản trước khi xét mẫu.
2. Tính 25/6 theo scale 3 và theo precision 3, cùng `HALF_UP`. Giải thích số chữ số sau dấu chấm ở hai kết quả.
3. Vì sao 1/40 ở scale 2 với `UNNECESSARY` thất bại nhưng ở scale 3 lại thành công?
4. Thử `new BigDecimal("25")` và `new BigDecimal("25.000")` chia cho 6 bằng overload chỉ nhận `RoundingMode`. Tìm cách viết không phụ thuộc scale đầu vào.
5. Chia 1.00 thành sáu phần ở đơn vị 0.01 và bảo toàn tổng. Trước khi viết mã, định nghĩa quy tắc nhận phần dư.
6. Viết hàm chia nhận `BigDecimal dividend`, `BigDecimal divisor`, scale và mode; kiểm tra mẫu bằng `signum()`, không chuyển sang `double`, trả về kết quả mới. Kiểm thử thương chính xác, không hữu hạn, số âm và mẫu 0.00.

Gợi ý đối chiếu: 9/24 = 3/8, 7/28 = 1/4 và 18/45 = 2/5 đều hữu hạn; 11/18 không hữu hạn. 25/6 ở scale 3 cho 4.167, còn precision 3 cho 4.17. Với 1/40, giá trị chính xác là 0.025 nên scale 3 đủ giữ nguyên thông tin.
