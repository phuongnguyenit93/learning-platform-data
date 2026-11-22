# Cộng, trừ, nhân, chia với MathContext

## 1. MathContext là chính sách cho một phép tính

`BigDecimal` hỗ trợ tính toán thập phân với số chữ số tùy nhu cầu. Khi muốn giới hạn số chữ số có nghĩa của kết quả, ta truyền một `MathContext` vào phép toán.

`MathContext` có hai thành phần:

- **precision:** số chữ số có nghĩa tối đa dùng cho kết quả khi precision lớn hơn 0.
- **roundingMode:** quy tắc chọn kết quả nếu phải bỏ bớt chữ số.

Ví dụ:

```java
MathContext mc = new MathContext(5, RoundingMode.HALF_UP);
```

Đây là yêu cầu tối đa năm chữ số có nghĩa, không phải năm chữ số sau dấu thập phân. Kết quả `131.35` có năm chữ số có nghĩa và scale 2; kết quả `15.647` cũng có năm chữ số có nghĩa nhưng scale 3.

`MathContext` là đối tượng bất biến và có thể dùng lại. Nó không thay đổi toàn cục cách `BigDecimal` tính toán, không tự gắn vĩnh viễn vào toán hạng và không tự áp dụng cho một phép toán mà ta quên truyền nó vào.

## 2. Bốn phép toán có cùng cách truyền chính sách

Với hai đối tượng `a`, `b` và một `MathContext mc`:

| Phép toán | Lời gọi |
| --- | --- |
| Cộng | `a.add(b, mc)` |
| Trừ | `a.subtract(b, mc)` |
| Nhân | `a.multiply(b, mc)` |
| Chia | `a.divide(b, mc)` |

Hãy hiểu kết quả của mỗi lời gọi theo hai bước về mặt hợp đồng: tính kết quả toán học chính xác của phép toán trên các toán hạng, rồi làm tròn kết quả đó theo `mc` nếu cần. Đây là cách mô tả ngữ nghĩa; không đòi hỏi thư viện phải thực sự tạo một giá trị trung gian có vô hạn chữ số.

Ví dụ với `a = 123.456`, `b = 7.89`, precision 5 và `HALF_UP`:

| Phép toán | Kết quả chính xác hoặc dạng khai triển | Kết quả với mc |
| --- | --- | --- |
| Cộng | `131.346` | `131.35` |
| Trừ | `115.566` | `115.57` |
| Nhân | `974.06784` | `974.07` |
| Chia | `123.456 / 7.89` | `15.647` |

Các toán hạng không bị làm tròn trước chỉ vì chúng có nhiều chữ số hơn precision của `mc`. Chẳng hạn `a` vẫn giữ `123.456` sau lời gọi.

`BigDecimal` cũng bất biến, nên phải dùng giá trị trả về:

```java
BigDecimal total = a.add(b, mc);
```

Chỉ gọi `a.add(b, mc)` rồi bỏ kết quả không cập nhật biến `a`.

## 3. Precision không phải số vị trí thập phân

`MathContext(5, ...)` đếm từ chữ số khác 0 đầu tiên của số, không tính dấu âm, dấu chấm hoặc các số 0 đứng trước.

Ví dụ `0.0005` chỉ cần một chữ số có nghĩa. Tính `1 / 2000` với precision 3 vẫn có thể trả `0.0005`, precision 1; thư viện không bắt buộc thêm số 0 để “đủ ba chữ số”.

Nếu yêu cầu kết quả phải có đúng hai vị trí thập phân, API trực tiếp là `setScale(2, roundingMode)` hoặc overload `divide(divisor, 2, roundingMode)` khi chia. Cần phân biệt:

```java
BigDecimal a = new BigDecimal("1000");
BigDecimal b = new BigDecimal("3");

BigDecimal significantDigits =
        a.divide(b, new MathContext(2, RoundingMode.HALF_UP));
// Gia tri so 330, bieu dien mac dinh 3.3E+2

BigDecimal fractionalDigits =
        a.divide(b, 2, RoundingMode.HALF_UP);
// 333.33
```

Đây là các đoạn minh họa trong một phương thức. Hai kết quả đáp ứng hai yêu cầu khác nhau; không thể hoán đổi overload chỉ vì cả hai cùng có số 2.

Scale kết quả còn phụ thuộc phép toán và biểu diễn toán hạng. Khi tính chính xác không giới hạn, cộng/trừ thường dùng scale lớn hơn của hai toán hạng, nhân dùng tổng scale. Khi có giới hạn precision và phải làm tròn, scale có thể giảm, kể cả trở thành số âm. Vì vậy không suy rằng scale của kết quả luôn bằng scale của đầu vào.

## 4. Phép chia và precision bằng 0

Nếu không truyền `MathContext`, `add`, `subtract` và `multiply` tính chính xác trong phạm vi biểu diễn được. Với `divide(BigDecimal)`, thương phải biểu diễn được bằng một số thập phân hữu hạn; `1 / 3` không thỏa điều kiện đó.

`new MathContext(0, ... )` biểu thị không giới hạn precision. `MathContext.UNLIMITED` là cấu hình dựng sẵn có precision 0. Quy tắc làm tròn không được dùng khi tính theo precision 0, vì không có bước cắt về một số chữ số hữu hạn được chỉ định.

Điều đó **không** cho phép chứa một khai triển thập phân vô hạn trong bộ nhớ:

```java
BigDecimal.ONE.divide(BigDecimal.valueOf(3), MathContext.UNLIMITED);
// ArithmeticException
```

Để có một xấp xỉ hữu hạn, dùng precision dương, chẳng hạn:

```java
BigDecimal third = BigDecimal.ONE.divide(
        BigDecimal.valueOf(3),
        new MathContext(5, RoundingMode.HALF_UP));
// 0.33333
```

Precision dương vẫn không làm phép chia cho 0 trở nên hợp lệ. `divide` với mẫu bằng 0 ném `ArithmeticException`.

## 5. UNNECESSARY là một yêu cầu kiểm chứng

`RoundingMode.UNNECESSARY` yêu cầu phép toán không được mất giá trị vì làm tròn. Nếu kết quả chính xác không thể biểu diễn trong giới hạn precision đã đặt, phép toán ném `ArithmeticException`.

Ví dụ `123.456 + 7.89 = 131.346` cần sáu chữ số có nghĩa. Yêu cầu precision 5 với `UNNECESSARY` thất bại. Ngược lại, một kết quả có thể được biểu diễn chính xác trong giới hạn đó vẫn hợp lệ; các số 0 không cần thiết có thể được bỏ mà không đổi giá trị.

Đừng bắt ngoại lệ rồi âm thầm chuyển sang một rounding mode khác. Điều đó thay đổi hợp đồng tính toán; cần quyết định chính sách ngay tại nơi thiết kế phép tính.

## 6. Chương trình chạy đầy đủ

Lưu thành `MathContextArithmeticDemo.java`. Ví dụ sử dụng API có trên Java 17 trở lên.

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class MathContextArithmeticDemo {
    private static void show(String label, BigDecimal value) {
        System.out.println(label + " = " + value.toPlainString()
                + " (precision=" + value.precision()
                + ", scale=" + value.scale() + ")");
    }

    public static void main(String[] args) {
        MathContext mc = new MathContext(5, RoundingMode.HALF_UP);
        BigDecimal a = new BigDecimal("123.456");
        BigDecimal b = new BigDecimal("7.89");

        show("add exact", a.add(b));
        show("add mc", a.add(b, mc));
        show("subtract mc", a.subtract(b, mc));
        show("multiply mc", a.multiply(b, mc));
        show("divide mc", a.divide(b, mc));
        show("original a", a);

        BigDecimal one = BigDecimal.ONE;
        BigDecimal three = BigDecimal.valueOf(3);
        show("one third mc", one.divide(three, mc));
        show("small result", one.divide(new BigDecimal("2000"),
                new MathContext(3, RoundingMode.HALF_UP)));

        try {
            one.divide(three, MathContext.UNLIMITED);
        } catch (ArithmeticException ex) {
            System.out.println("unlimited one third: non-terminating decimal");
        }

        try {
            a.add(b, new MathContext(5, RoundingMode.UNNECESSARY));
        } catch (ArithmeticException ex) {
            System.out.println("exact five digits: rounding required");
        }

        MathContext threeDigits = new MathContext(3, RoundingMode.HALF_UP);
        BigDecimal x = new BigDecimal("1000");
        BigDecimal y = BigDecimal.ONE;
        BigDecimal z = new BigDecimal("-1000");
        System.out.println("left grouped = "
                + x.add(y, threeDigits).add(z, threeDigits).toPlainString());
        System.out.println("right grouped = "
                + x.add(y.add(z, threeDigits), threeDigits).toPlainString());

        BigDecimal source = new BigDecimal("1.2449");
        System.out.println("rounded twice = "
                + source.round(new MathContext(4, RoundingMode.HALF_UP))
                        .setScale(2, RoundingMode.HALF_UP));
        System.out.println("rounded once = "
                + source.setScale(2, RoundingMode.HALF_UP));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 MathContextArithmeticDemo.java
java MathContextArithmeticDemo
```

Stdout:

```text
add exact = 131.346 (precision=6, scale=3)
add mc = 131.35 (precision=5, scale=2)
subtract mc = 115.57 (precision=5, scale=2)
multiply mc = 974.07 (precision=5, scale=2)
divide mc = 15.647 (precision=5, scale=3)
original a = 123.456 (precision=6, scale=3)
one third mc = 0.33333 (precision=5, scale=5)
small result = 0.0005 (precision=1, scale=4)
unlimited one third: non-terminating decimal
exact five digits: rounding required
left grouped = 0
right grouped = 1
rounded twice = 1.25
rounded once = 1.24
```

`original a` chứng minh toán hạng giữ nguyên. `small result` chứng minh precision của kết quả có thể thấp hơn giới hạn. Hai dòng nhóm phép tính và hai dòng làm tròn cuối cần được đọc như cảnh báo về thiết kế chuỗi tính toán.

## 7. Thứ tự tính và thời điểm làm tròn có thể đổi kết quả

Trong số học chính xác, cộng có tính kết hợp. Khi mỗi bước bị làm tròn theo precision hữu hạn, không được mặc định giữ tính chất đó.

Trong chương trình, precision 3 làm `1000 + 1` thành giá trị 1000; cộng tiếp `-1000` cho 0. Nếu tính `1 + (-1000)` trước, kết quả -999 biểu diễn chính xác ở ba chữ số; cộng với 1000 cho 1.

Tương tự, **làm tròn hai lần** có thể khác làm tròn trực tiếp một lần. `1.2449` về precision 4 với `HALF_UP` thành `1.245`; tiếp tục về scale 2 thành `1.25`. Đi trực tiếp từ `1.2449` về scale 2 lại cho `1.24`.

Vì vậy, trước khi viết chuỗi phép toán cần quyết định:

- Quy tắc nghiệp vụ yêu cầu làm tròn ở từng bước hay chỉ tại kết quả cuối?
- Các phép chia trung gian cần precision bao nhiêu để đáp ứng độ chính xác yêu cầu?
- Đầu ra cần giới hạn số chữ số có nghĩa hay cố định số vị trí thập phân?

Không có một precision nhỏ dùng chung đúng cho mọi bài toán. Với chuỗi cộng, trừ, nhân mà nguồn hữu hạn và quy tắc yêu cầu tính chính xác rồi mới làm tròn cuối, có thể giữ các bước đó chính xác. Với phép chia không hữu hạn, phải xác định chính sách xấp xỉ trung gian và kiểm chứng sai số phù hợp; chỉ tăng precision tùy ý không thay cho đặc tả tính toán.

## 8. Cấu hình sẵn và lỗi thường gặp

`MathContext.DECIMAL32`, `DECIMAL64`, `DECIMAL128` lần lượt có precision 7, 16, 34, dùng `HALF_EVEN`. Các tên này không biến đối tượng `BigDecimal` thành vùng lưu trữ cố định 32/64/128 bit và không áp đặt toàn bộ miền số mũ của các định dạng đó.

`new MathContext(5)` mặc định dùng `HALF_UP`. Khi chính sách làm tròn là phần quan trọng của yêu cầu, viết rõ enum giúp người đọc đánh giá phép tính dễ hơn. Precision âm bị từ chối bằng `IllegalArgumentException`.

Những lỗi cần tránh:

- Truyền `mc` vào phép đầu rồi quên truyền ở các phép sau, trong khi quy tắc đòi mỗi bước đều áp dụng cùng chính sách.
- Tạo `BigDecimal` từ các giá trị `double` đã sai lệch rồi kỳ vọng `MathContext` phục hồi chữ số gốc.
- Dùng precision 2 để diễn đạt “hai số lẻ”.
- Hiểu `UNLIMITED` là phép chia nào cũng trả kết quả.
- Bỏ qua số âm, kết quả gần 0 và phép trừ hai số gần nhau khi kiểm chứng chuỗi tính toán.

## 9. Tự kiểm tra

1. `new BigDecimal("12.34").add(new BigDecimal("0.005"), new MathContext(4, RoundingMode.HALF_UP))` cho giá trị gì?
2. Precision 10 có làm `1 / 0` hợp lệ không?
3. Tạo một `MathContext` có tự cấu hình mọi đối tượng `BigDecimal` trong chương trình không?

Đáp án:

1. `12.35`: tổng chính xác là `12.345`, làm tròn còn bốn chữ số có nghĩa.
2. Không; phép chia cho 0 vẫn ném `ArithmeticException`.
3. Không; chỉ các lời gọi nhận chính sách đó mới áp dụng nó.

Tham khảo: [MathContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/MathContext.html) và [BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html) trong Java SE 21.
