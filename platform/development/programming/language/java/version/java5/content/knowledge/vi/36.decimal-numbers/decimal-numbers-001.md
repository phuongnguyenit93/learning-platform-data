# MathContext và tính toán theo độ chính xác chỉ định

## 1. Từ số thập phân chính xác đến phép tính có giới hạn chữ số

`BigDecimal` biểu diễn số thập phân, nhưng nhiều phép tính không thể trả về một số thập phân hữu hạn chính xác. Ví dụ, 1 chia 3 có vô hạn chữ số 3 sau dấu chấm. Ngoài ra, ứng dụng có thể chủ động chỉ giữ một số lượng chữ số có nghĩa nhất định cho từng phép tính.

`MathContext` là đối tượng mô tả hai lựa chọn:

- `precision`: số chữ số có nghĩa tối đa được giữ khi phép tính cần làm tròn.
- `roundingMode`: cách chọn kết quả khi phải bỏ bớt chữ số.

Có thể hình dung `BigDecimal` là số đang tính, còn `MathContext` là chính sách được truyền cho một phép tính. Chính sách không tự gắn vĩnh viễn vào số và không thay đổi toàn bộ chương trình.

Ví dụ, với precision bằng 4, `123.456` được làm tròn thành `123.5`; `0.00123456` thành `0.001235`. Hai kết quả có số chữ số sau dấu chấm khác nhau, nhưng đều giữ bốn chữ số có nghĩa.

Bài này dùng API còn áp dụng trong Java hiện đại và ví dụ tương thích Java 17+. Dùng `RoundingMode`, không dùng các hằng số làm tròn kiểu `int` đã bị đánh dấu deprecated của `BigDecimal`.

## 2. Precision khác scale như thế nào?

Trong `BigDecimal`, precision của một giá trị là số chữ số trong phần số nguyên không kèm dấu được dùng để biểu diễn giá trị đó. Scale cho biết vị trí dấu chấm thập phân:

```text
giá trị = unscaledValue × 10^(-scale)
```

Các ví dụ sau được tạo từ chuỗi:

| Giá trị khởi tạo | precision() | scale() | Giải thích |
| --- | ---: | ---: | --- |
| "123.450" | 6 | 3 | Số 0 cuối vẫn thuộc biểu diễn đã nhập |
| "0.0012345" | 5 | 7 | Các số 0 trước chữ số 1 không làm tăng precision |
| "1000" | 4 | 0 | Cả bốn chữ số thuộc biểu diễn |
| "1E+3" | 1 | -3 | Giá trị bằng 1000 nhưng biểu diễn khác |

Precision của một `MathContext` là giới hạn cho phép tính, còn `precision()` của một `BigDecimal` mô tả giá trị kết quả hiện có. Precision bằng 4 không bắt buộc kết quả phải có đúng bốn chữ số: phép chia 1 cho 2 vẫn có thể cho `0.5`.

Đừng dùng `new MathContext(2)` để yêu cầu hai chữ số sau dấu chấm. Với `123.456`:

```java
BigDecimal value = new BigDecimal("123.456");

BigDecimal significant = value.round(new MathContext(2, RoundingMode.HALF_UP));
BigDecimal fractional = value.setScale(2, RoundingMode.HALF_UP);
```

`significant.toPlainString()` là `120`, còn `fractional.toPlainString()` là `123.46`. Giá trị thứ nhất đã mất thông tin hàng đơn vị để đáp ứng giới hạn hai chữ số có nghĩa; giá trị thứ hai giữ hai chữ số sau dấu chấm.

Scale có thể âm sau khi làm tròn. Đó là biểu diễn hợp lệ, không phải lỗi. `toPlainString()` giúp hiển thị không dùng ký hiệu số mũ, nhưng không thay đổi precision hay scale của đối tượng.

## 3. Tạo và truyền MathContext

Đoạn sau minh họa cấu hình thường dùng:

```java
MathContext calculation = new MathContext(8, RoundingMode.HALF_EVEN);

BigDecimal left = new BigDecimal("12.3456789");
BigDecimal right = new BigDecimal("0.125");
BigDecimal sum = left.add(right, calculation);
BigDecimal product = left.multiply(right, calculation);
BigDecimal quotient = left.divide(right, calculation);
```

Các lệnh trên là một đoạn mã trong phương thức, cần import `java.math.BigDecimal`, `java.math.MathContext` và `java.math.RoundingMode`.

`MathContext` bất biến. Có thể dùng một hằng `static final` cho chính sách chung hoặc truyền nó qua tham số nếu mỗi nghiệp vụ có yêu cầu khác nhau. `BigDecimal` cũng bất biến: cần nhận giá trị trả về của `round`, `add`, `multiply` và các phép tính khác.

```java
BigDecimal value = new BigDecimal("12.3456");
value.round(new MathContext(4, RoundingMode.HALF_UP)); // Bỏ mất kết quả.
System.out.println(value);                           // Vẫn là 12.3456.
```

Constructor `new MathContext(precision)` mặc định dùng `HALF_UP`. Viết rõ cả hai đối số giúp người đọc không phải nhớ mặc định. Precision âm gây `IllegalArgumentException`; precision bằng 0 có ý nghĩa riêng, được giải thích bên dưới. Các quy tắc cấu hình và tính bất biến được mô tả trong [MathContext API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/MathContext.html).

### Truyền context ở đâu thì tác động ở đó

```java
MathContext mc = new MathContext(4, RoundingMode.HALF_UP);
BigDecimal input = new BigDecimal("123.456");
BigDecimal roundedInput = new BigDecimal("123.456", mc);
BigDecimal roundedLater = input.round(mc);
```

`input` giữ giá trị nhập chính xác; hai biến sau có giá trị `123.5`. Constructor có context làm tròn ngay khi nhập. Điều này có thể làm mất dữ liệu trước khi phép tính chính bắt đầu.

Tương tự, sau `a.divide(b, mc)`, gọi `result.multiply(c)` mà không truyền context sẽ không tự kế thừa `mc`. Cần chọn rõ vị trí làm tròn trong toàn bộ chuỗi phép tính.

Nên khởi tạo số thập phân từ chuỗi khi muốn giữ đúng giá trị thập phân do người dùng hoặc đặc tả cung cấp. `new BigDecimal(0.1)` nhận giá trị nhị phân của `double`; thêm `MathContext` không biến nó trở lại thành bản gốc thập phân đã bị mất. `BigDecimal.valueOf(double)` dùng biểu diễn chuỗi của `double`, nhưng cũng không khôi phục được thông tin đã mất trong những phép tính `double` trước đó.

## 4. Hiểu cách làm tròn thông qua ví dụ

Để chọn `roundingMode`, cần xác định cách xử lý phần bị bỏ, đặc biệt là số âm và trường hợp nằm chính giữa hai kết quả.

| Chế độ | Ý nghĩa |
| --- | --- |
| `UP` | Ra xa 0 khi có phần bị bỏ khác 0 |
| `DOWN` | Về phía 0 |
| `CEILING` | Về phía dương vô cùng |
| `FLOOR` | Về phía âm vô cùng |
| `HALF_UP` | Chọn gần nhất; nếu chính giữa thì ra xa 0 |
| `HALF_DOWN` | Chọn gần nhất; nếu chính giữa thì về phía 0 |
| `HALF_EVEN` | Chọn gần nhất; nếu chính giữa thì giữ chữ số cuối chẵn |
| `UNNECESSARY` | Yêu cầu không phải bỏ thông tin; ném ngoại lệ nếu cần làm tròn |

Với precision bằng 3:

- `1.245` thành `1.25` dưới `HALF_UP`, nhưng thành `1.24` dưới `HALF_EVEN`.
- `1.255` thành `1.26` dưới `HALF_EVEN`, vì chữ số cuối giữ lại phải là số chẵn.
- `-1.231` thành `-1.23` dưới `CEILING`, nhưng thành `-1.24` dưới `FLOOR`.

`HALF_EVEN` không có nghĩa là luôn làm tròn xuống hay luôn tạo ra kết quả nhỏ hơn. Nó chỉ dùng quy tắc chẵn khi đúng điểm giữa; một giá trị lớn hơn điểm giữa vẫn làm tròn về số gần hơn.

Tham khảo định nghĩa và ví dụ dấu âm trong [RoundingMode API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/RoundingMode.html).

## 5. Precision bằng 0: chính xác, không phải giữ 0 chữ số

`MathContext.UNLIMITED` có precision bằng 0. Trong các phép toán số học với context này, Java yêu cầu kết quả chính xác; chế độ làm tròn không được dùng để cắt bớt chữ số.

Điều đó không cho phép lưu một số thập phân dài vô hạn:

```java
BigDecimal exact = BigDecimal.ONE.divide(new BigDecimal("8"), MathContext.UNLIMITED);
// exact = 0.125

BigDecimal impossible = BigDecimal.ONE.divide(new BigDecimal("3"), MathContext.UNLIMITED);
// Ném ArithmeticException: không có biểu diễn thập phân hữu hạn chính xác.
```

Ngược lại, `BigDecimal.ONE.divide(new BigDecimal("3"), new MathContext(6, RoundingMode.HALF_UP))` cho `0.333333`.

Cũng cần phân biệt các overload:

```java
one.divide(three, new MathContext(4, RoundingMode.HALF_UP));
one.divide(three, 4, RoundingMode.HALF_UP);
```

Dòng đầu yêu cầu bốn chữ số có nghĩa, dòng sau yêu cầu scale bằng 4. Với 1/3, hình thức kết quả tình cờ giống nhau. Với 100/3, kết quả lần lượt là `33.33` và `33.3333`. Đừng dựa vào một ví dụ nhỏ để coi hai overload là tương đương.

Ngữ nghĩa phép tính chính xác, làm tròn và overload được quy định trong [BigDecimal API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html).

## 6. Làm tròn từng bước có thể đổi kết quả cuối

Phép tính có precision hữu hạn mất một phần các tính chất của số thực chính xác. Xét biểu thức `(1 / 3) × 3` với precision bằng 3:

```text
1 / 3 → 0.333
0.333 × 3 → 0.999
```

Kết quả không trở về 1 vì chữ số đã bị bỏ ở bước chia không được khôi phục khi nhân. Tăng precision ở bước nhân sau đó cũng không lấy lại thông tin đó.

Ví dụ dễ thấy hơn với phép cộng:

```text
a = 1000, b = 1, c = -1000, precision = 3, HALF_UP

(a + b) + c:
1000 + 1 → 1000
1000 + (-1000) → 0

a + (b + c):
1 + (-1000) → -999
1000 + (-999) → 1
```

Như vậy đổi cách nhóm phép cộng có thể đổi kết quả. Với một thuật toán có nhiều bước:

1. Xác định dữ liệu đầu vào có được làm tròn ngay hay phải giữ nguyên.
2. Xác định những bước nào bắt buộc làm tròn theo yêu cầu nghiệp vụ hoặc thuật toán.
3. Nếu cần gần đúng ở bước trung gian, có thể dùng precision lớn hơn kết quả cuối để giữ thêm chữ số dự phòng.
4. Kiểm tra sai số của kết quả cuối với các dữ liệu đại diện, nhất là khi cộng các số chênh lệch độ lớn hoặc trừ các số gần nhau.

Không có một số chữ số dự phòng cố định bảo đảm đúng cho mọi công thức. Precision cao hơn thường giảm mất mát do làm tròn, nhưng không thay thế phân tích sai số.

Nếu biểu thức chỉ có cộng, trừ, nhân và kích thước dữ liệu cho phép, có thể tính chính xác rồi làm tròn ở ranh giới đã chọn. Với phép chia vô hạn như 1/3, vẫn phải chọn một biểu diễn gần đúng nếu cần giữ thương trung gian.

Cũng không nên làm tròn hai lần tùy tiện. Chẳng hạn `1.2451` làm tròn trực tiếp về ba chữ số dưới `HALF_EVEN` cho `1.25`. Nếu làm tròn về bốn chữ số trước, được `1.245`; làm tròn tiếp về ba chữ số lại thành `1.24`. Bước trung gian đã tạo ra một điểm giữa vốn không có trong giá trị ban đầu.

## 7. Những context dựng sẵn và giới hạn của chúng

Java cung cấp các hằng sau:

| Context | Precision | RoundingMode |
| --- | ---: | --- |
| `MathContext.DECIMAL32` | 7 | `HALF_EVEN` |
| `MathContext.DECIMAL64` | 16 | `HALF_EVEN` |
| `MathContext.DECIMAL128` | 34 | `HALF_EVEN` |
| `MathContext.UNLIMITED` | 0 | `HALF_UP`, không tham gia làm tròn khi tính chính xác |

Các tên DECIMAL32/64/128 không có nghĩa `BigDecimal` bị chuyển thành kiểu số chiếm 32/64/128 bit. Chúng cung cấp precision và chế độ làm tròn; không áp đặt dải số mũ tương ứng của định dạng IEEE 754. Vì vậy không nên dùng tên context để suy ra toàn bộ hành vi của một kiểu số phần cứng.

Chọn context theo yêu cầu của phép tính và mức sai số chấp nhận được. Không có context nào tự bảo đảm một nghiệp vụ có quy tắc làm tròn chính xác nếu chưa xác định các ranh giới và quy tắc đó.

## 8. Chương trình hoàn chỉnh để quan sát hành vi

Lưu thành `MathContextDemo.java`. Chương trình dùng `toPlainString()` để kết quả dễ đọc, đồng thời in precision và scale của một giá trị.

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class MathContextDemo {
    private static BigDecimal decimal(String value) {
        return new BigDecimal(value);
    }

    private static void show(String label, BigDecimal value) {
        System.out.println(label + "=" + value.toPlainString());
    }

    public static void main(String[] args) {
        MathContext p3 = new MathContext(3, RoundingMode.HALF_UP);
        MathContext p4 = new MathContext(4, RoundingMode.HALF_UP);
        MathContext even3 = new MathContext(3, RoundingMode.HALF_EVEN);

        BigDecimal input = decimal("123.456");
        show("precision4", input.round(p4));
        show("scale2", input.setScale(2, RoundingMode.HALF_UP));
        show("small", decimal("0.00123456").round(p4));

        BigDecimal carry = decimal("999.9").round(p3);
        show("carry", carry);
        System.out.println("carry.precision=" + carry.precision());
        System.out.println("carry.scale=" + carry.scale());

        show("halfUp", decimal("1.245").round(p3));
        show("halfEven", decimal("1.245").round(even3));
        show("halfEvenOdd", decimal("1.255").round(even3));
        show("negativeCeiling", decimal("-1.231").round(
                new MathContext(3, RoundingMode.CEILING)));
        show("negativeFloor", decimal("-1.231").round(
                new MathContext(3, RoundingMode.FLOOR)));

        BigDecimal one = BigDecimal.ONE;
        BigDecimal three = decimal("3");
        show("third", one.divide(three, p3));
        show("thirdTimes3", one.divide(three, p3).multiply(three, p3));
        show("hundredOver3.precision4", decimal("100").divide(three, p4));
        show("hundredOver3.scale4", decimal("100").divide(
                three, 4, RoundingMode.HALF_UP));

        BigDecimal a = decimal("1000");
        BigDecimal b = BigDecimal.ONE;
        BigDecimal c = decimal("-1000");
        show("leftGroup", a.add(b, p3).add(c, p3));
        show("rightGroup", a.add(b.add(c, p3), p3));

        BigDecimal doubleRounding = decimal("1.2451");
        show("direct", doubleRounding.round(even3));
        show("twoRounds", doubleRounding.round(
                new MathContext(4, RoundingMode.HALF_EVEN)).round(even3));

        show("exactEighth", one.divide(decimal("8"), MathContext.UNLIMITED));
        try {
            one.divide(three, MathContext.UNLIMITED);
        } catch (ArithmeticException exception) {
            System.out.println("exactThird=ArithmeticException");
        }

        try {
            decimal("1.234").round(
                    new MathContext(3, RoundingMode.UNNECESSARY));
        } catch (ArithmeticException exception) {
            System.out.println("unnecessary=ArithmeticException");
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 MathContextDemo.java
java MathContextDemo
```

Stdout:

```text
precision4=123.5
scale2=123.46
small=0.001235
carry=1000
carry.precision=3
carry.scale=-1
halfUp=1.25
halfEven=1.24
halfEvenOdd=1.26
negativeCeiling=-1.23
negativeFloor=-1.24
third=0.333
thirdTimes3=0.999
hundredOver3.precision4=33.33
hundredOver3.scale4=33.3333
leftGroup=0
rightGroup=1
direct=1.25
twoRounds=1.24
exactEighth=0.125
exactThird=ArithmeticException
unnecessary=ArithmeticException
```

`carry` có giá trị 1000, precision bằng 3 và scale bằng -1: nội bộ có thể hiểu là `100 × 10^1`. `toPlainString()` in bốn ký tự số, nhưng không có nghĩa precision phải bằng 4. Việc làm tròn đã đẩy `999.9` sang một bậc lớn hơn.

Hai ngoại lệ được bắt để chương trình tiếp tục chạy. Chương trình không so sánh thông báo ngoại lệ vì câu chữ thông báo không phải điều cần dùng làm hợp đồng của bài học.

## 9. Chọn API theo yêu cầu thực tế

| Yêu cầu | API phù hợp | Cần quyết định thêm |
| --- | --- | --- |
| Giữ tối đa p chữ số có nghĩa khi tính | `add/subtract/multiply/divide(..., mc)` | precision và roundingMode |
| Làm tròn một giá trị đã có | `value.round(mc)` | Có chấp nhận mất dữ liệu tại đây không? |
| Giữ s chữ số sau dấu chấm | `setScale(s, mode)` | Quy tắc làm tròn tại ranh giới đó |
| Phép chia có đúng scale s | `divide(divisor, s, mode)` | Tránh nhầm s là precision |
| Phép chia chính xác | `divide(divisor)` hoặc context precision 0 | Thương có biểu diễn hữu hạn không? |
| Cấm làm tròn âm thầm | `RoundingMode.UNNECESSARY` | Giá trị có đáp ứng giới hạn không? |

Ví dụ, yêu cầu xuất một giá trị với hai chữ số sau dấu chấm khác với yêu cầu mọi phép tính trung gian chỉ giữ hai chữ số có nghĩa. Cần tách rõ chính sách tính toán và chính sách đầu ra. `setScale(2, ...)` cũng tạo ra một giá trị mới đã được làm tròn; nó không đơn thuần trang trí chuỗi.

`UNNECESSARY` hữu ích khi muốn phát hiện dữ liệu hoặc kết quả vi phạm một cam kết. Nó không bảo đảm một phép tính luôn chạy được; ngoại lệ chính là dấu hiệu cam kết không đáp ứng được.

## 10. Lỗi thường gặp và cách tự kiểm tra

- **Nhầm precision với số chữ số sau dấu chấm:** thử cùng chính sách với `12345.67` và `0.0001234567`; sự khác biệt về độ lớn sẽ làm lộ lỗi.
- **Cho rằng context tự được ghi nhớ:** đọc từng lời gọi trong chuỗi, xác định lời gọi nào thực sự truyền `mc`.
- **Làm tròn ngay đầu vào mà không chủ ý:** so sánh constructor có context với constructor chuỗi không có context.
- **Bỏ qua giá trị trả về:** nhớ rằng các đối tượng đều bất biến.
- **Cho rằng UNLIMITED xử lý được mọi phép chia:** kiểm tra cả 1/8, 1/3 và chia cho 0; chia cho 0 vẫn ném `ArithmeticException` với mọi precision.
- **Tăng precision và coi như có thêm dữ liệu chính xác:** số đã làm tròn hoặc đã tính bằng `double` không được khôi phục chỉ nhờ context mới.
- **Làm tròn mỗi bước rồi đổi thứ tự phép tính:** kiểm tra ví dụ cộng nhóm và làm tròn hai lần ở trên.
- **Chọn chế độ theo tên mà quên số âm:** `DOWN` là về 0, còn `FLOOR` là về âm vô cùng.
- **So sánh kết quả bằng equals mà quên scale:** `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` là false; nếu chỉ kiểm tra giá trị số, dùng `compareTo(...) == 0`. Nếu biểu diễn/scale cũng là yêu cầu thì kiểm tra chúng riêng.

## 11. Thực hành

1. Với `new BigDecimal("0.009995")`, dự đoán kết quả `round(new MathContext(3, RoundingMode.HALF_UP))`, precision và scale; sau đó tự chạy để kiểm chứng.
2. Tính 1000/3 theo precision bằng 4 và theo scale bằng 4. Giải thích vì sao hai kết quả khác nhau.
3. Thay precision bằng 6 trong phép `(1 / 3) × 3`. Kết quả có bằng 1 chính xác không? Việc tăng precision giải quyết phần nào của vấn đề?
4. Viết hàm nhận hai `BigDecimal` và một `MathContext` để tính thương; không làm tròn đầu vào, trả về kết quả mới. Kiểm tra mẫu số 0 và context dùng `UNNECESSARY`.
5. Giải thích vì sao `1.2451 → 1.245 → 1.24` khác `1.2451 → 1.25` dưới `HALF_EVEN`. Chỉ ra thông tin nào bị mất ở bước trung gian.

Gợi ý đối chiếu: câu 1 cho giá trị `0.0100`, precision bằng 3, scale bằng 4; câu 2 cho `333.3` và `333.3333`; câu 3 cho `0.999999`. Khi giải thích kết quả, hãy nói rõ đang kiểm tra giá trị số, số chữ số có nghĩa hay biểu diễn sau dấu chấm.
