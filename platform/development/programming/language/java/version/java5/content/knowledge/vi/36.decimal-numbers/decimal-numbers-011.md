# MathContext.UNLIMITED, DECIMAL32, DECIMAL64 và DECIMAL128

## 1. Bốn cấu hình có sẵn để diễn đạt chính sách tính toán

`MathContext` mô tả giới hạn chữ số có nghĩa và cách làm tròn cho các phép toán `BigDecimal` nhận tham số này. Bốn hằng số dưới đây là các đối tượng bất biến được Java cung cấp sẵn, có thể dùng lại trực tiếp.

| Hằng số | precision | roundingMode | Ý nghĩa thực tế |
| --- | ---: | --- | --- |
| `UNLIMITED` | 0 | `HALF_UP` | Yêu cầu tính chính xác, không cắt theo giới hạn precision |
| `DECIMAL32` | 7 | `HALF_EVEN` | Tối đa 7 chữ số có nghĩa khi cần làm tròn |
| `DECIMAL64` | 16 | `HALF_EVEN` | Tối đa 16 chữ số có nghĩa khi cần làm tròn |
| `DECIMAL128` | 34 | `HALF_EVEN` | Tối đa 34 chữ số có nghĩa khi cần làm tròn |

Số 32, 64, 128 trong tên liên quan đến các định dạng thập phân IEEE 754 có cùng mức precision tương ứng. **Chúng không phải số chữ số thập phân và không quy định kích thước bộ nhớ của một đối tượng BigDecimal.**

Ví dụ `DECIMAL64` không có nghĩa là 64 chữ số, cũng không có nghĩa là 16 chữ số sau dấu thập phân. Một kết quả `123.45` có thể giữ nguyên khi áp dụng cấu hình này vì nó chỉ có năm chữ số có nghĩa.

## 2. UNLIMITED: chính xác khi kết quả biểu diễn được

Precision bằng 0 là ký hiệu “không giới hạn precision”, không phải yêu cầu trả về 0 chữ số hoặc trả về số 0.

Ví dụ minh họa trong một phương thức:

```java
BigDecimal value = new BigDecimal("123456789.123456789");
BigDecimal result = value.multiply(
        BigDecimal.TEN, MathContext.UNLIMITED);
// Gia tri chinh xac: 1234567891.234567890
```

Cấu hình `UNLIMITED` có thuộc tính `HALF_UP`, nhưng thuộc tính đó không được dùng để cắt chữ số khi precision bằng 0. Không có giới hạn hữu hạn để phép toán làm tròn về.

Điều này dẫn tới giới hạn quan trọng của phép chia:

- `1 / 8` có biểu diễn hữu hạn `0.125`, nên tính được chính xác.
- `1 / 7` có khai triển thập phân lặp vô hạn, nên `divide(..., UNLIMITED)` ném `ArithmeticException`.
- Chia cho 0 vẫn không hợp lệ, bất kể dùng cấu hình nào.

`UNLIMITED` không tạo được một đối tượng chứa vô hạn chữ số. Nó cũng không hứa bộ nhớ hoặc thời gian xử lý vô hạn; phép tính lớn vẫn chịu tài nguyên thực tế và giới hạn biểu diễn của `BigDecimal`, trong đó scale là số nguyên 32 bit.

Nếu cần thương xấp xỉ của `1 / 7`, phải chọn precision dương hoặc một scale cùng rounding mode phù hợp.

## 3. DECIMAL32, DECIMAL64 và DECIMAL128: ba mức precision hữu hạn

Cùng một phép chia có thể cho ba xấp xỉ khác nhau:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal seven = BigDecimal.valueOf(7);

BigDecimal a = one.divide(seven, MathContext.DECIMAL32);
BigDecimal b = one.divide(seven, MathContext.DECIMAL64);
BigDecimal c = one.divide(seven, MathContext.DECIMAL128);
```

Giá trị lần lượt là:

```text
DECIMAL32  -> 0.1428571
DECIMAL64  -> 0.1428571428571429
DECIMAL128 -> 0.1428571428571428571428571428571429
```

Các số 0 đứng trước chữ số khác 0 đầu tiên không được tính vào số chữ số có nghĩa. Chọn precision cao hơn giữ được nhiều chữ số hơn cho phép chia này, nhưng vẫn là xấp xỉ của `1 / 7`.

Precision là **giới hạn**, không phải lệnh đệm số 0. `new BigDecimal("1.2").round(MathContext.DECIMAL128)` vẫn là `1.2`, precision 2. Nó không tự thành một chuỗi dài đủ 34 chữ số.

### HALF_EVEN khi nằm đúng giữa

Ba cấu hình `DECIMAL*` đều dùng `HALF_EVEN`: chọn giá trị gần nhất; nếu đúng giữa hai lựa chọn, chọn sao cho chữ số cuối được giữ là chẵn.

Ở precision 7:

- `1.2345645` → `1.234564`, vì chữ số cuối được giữ là 4.
- `1.2345655` → `1.234566`, vì khi đó chữ số cuối được giữ là 6.

Không thể thay `DECIMAL32` bằng `new MathContext(7)` rồi cho rằng chúng hoàn toàn giống nhau. Constructor chỉ nhận precision mặc định dùng `HALF_UP`; trường hợp `1.2345645` sẽ cho `1.234565`.

Nếu cần một cấu hình tự tạo tương đương về thuộc tính:

```java
MathContext equivalent = new MathContext(7, RoundingMode.HALF_EVEN);
boolean sameSettings = equivalent.equals(MathContext.DECIMAL32); // true
```

Đây là so sánh cấu hình bằng `equals`, không dựa vào đồng nhất tham chiếu `==`.

## 4. Các tên DECIMAL không áp đặt toàn bộ định dạng IEEE 754

Các hằng số chỉ cung cấp precision và rounding mode. Chúng không giới hạn miền số mũ theo định dạng decimal32/64/128 tương ứng.

Chẳng hạn:

```java
BigDecimal huge = new BigDecimal("1E+1000");
BigDecimal rounded = huge.round(MathContext.DECIMAL32);
System.out.println(rounded); // 1E+1000
```

Giá trị này chỉ có một chữ số có nghĩa; áp dụng `DECIMAL32` không ép nó vào miền số mũ của một bộ mã hóa decimal32.

Tương tự, các hằng số không bổ sung `NaN`, dương vô cực, âm vô cực hoặc âm 0 cho `BigDecimal`. Nếu cần trao đổi với một định dạng mã hóa số thập phân cụ thể, còn phải xử lý quy tắc mã hóa, miền số mũ và giá trị đặc biệt của định dạng đó; chỉ truyền một `MathContext` chưa giải quyết trọn hợp đồng trao đổi.

## 5. Chương trình kiểm chứng đầy đủ

Lưu thành `StandardContextsDemo.java`. Chương trình dùng API có trên Java 17 trở lên.

```java
import java.math.BigDecimal;
import java.math.MathContext;

public class StandardContextsDemo {
    private static void settings(String name, MathContext context) {
        System.out.println(name + ": precision=" + context.getPrecision()
                + ", rounding=" + context.getRoundingMode());
    }

    public static void main(String[] args) {
        settings("UNLIMITED", MathContext.UNLIMITED);
        settings("DECIMAL32", MathContext.DECIMAL32);
        settings("DECIMAL64", MathContext.DECIMAL64);
        settings("DECIMAL128", MathContext.DECIMAL128);

        BigDecimal one = BigDecimal.ONE;
        BigDecimal seven = BigDecimal.valueOf(7);
        System.out.println("1/7 DECIMAL32 = " + one.divide(seven, MathContext.DECIMAL32));
        System.out.println("1/7 DECIMAL64 = " + one.divide(seven, MathContext.DECIMAL64));
        System.out.println("1/7 DECIMAL128 = " + one.divide(seven, MathContext.DECIMAL128));
        System.out.println("1/8 UNLIMITED = "
                + one.divide(BigDecimal.valueOf(8), MathContext.UNLIMITED));

        try {
            one.divide(seven, MathContext.UNLIMITED);
        } catch (ArithmeticException ex) {
            System.out.println("1/7 UNLIMITED: non-terminating decimal");
        }

        BigDecimal evenTie = new BigDecimal("1.2345645");
        BigDecimal oddTie = new BigDecimal("1.2345655");
        System.out.println("even tie DECIMAL32 = " + evenTie.round(MathContext.DECIMAL32));
        System.out.println("odd tie DECIMAL32 = " + oddTie.round(MathContext.DECIMAL32));
        System.out.println("even tie custom7 = " + evenTie.round(new MathContext(7)));

        BigDecimal largeExponent = new BigDecimal("1E+1000");
        System.out.println("large exponent = " + largeExponent.round(MathContext.DECIMAL32));
        BigDecimal shortNumber = new BigDecimal("1.2").round(MathContext.DECIMAL128);
        System.out.println("short = " + shortNumber + ", precision=" + shortNumber.precision());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 StandardContextsDemo.java
java StandardContextsDemo
```

Stdout:

```text
UNLIMITED: precision=0, rounding=HALF_UP
DECIMAL32: precision=7, rounding=HALF_EVEN
DECIMAL64: precision=16, rounding=HALF_EVEN
DECIMAL128: precision=34, rounding=HALF_EVEN
1/7 DECIMAL32 = 0.1428571
1/7 DECIMAL64 = 0.1428571428571429
1/7 DECIMAL128 = 0.1428571428571428571428571428571429
1/8 UNLIMITED = 0.125
1/7 UNLIMITED: non-terminating decimal
even tie DECIMAL32 = 1.234564
odd tie DECIMAL32 = 1.234566
even tie custom7 = 1.234565
large exponent = 1E+1000
short = 1.2, precision=2
```

Những dòng đầu đọc trực tiếp cấu hình bằng `getPrecision()` và `getRoundingMode()`. Các dòng `tie` chỉ ra sự khác biệt có thể bị bỏ sót nếu chỉ thử các số không nằm đúng giữa hai lựa chọn.

## 6. Chọn cấu hình theo yêu cầu

Không có quy tắc “DECIMAL128 luôn đúng hơn cho mọi bài toán”. Nó giữ nhiều chữ số có nghĩa hơn `DECIMAL32`/`DECIMAL64`, nhưng độ chính xác cần thiết và thời điểm làm tròn vẫn phải đến từ yêu cầu tính toán.

| Yêu cầu | Hướng lựa chọn |
| --- | --- |
| Các phép cộng, trừ, nhân cần giữ kết quả chính xác | `UNLIMITED` hoặc overload tính chính xác không nhận context |
| Quy trình quy định tối đa 7 chữ số và HALF_EVEN | `DECIMAL32` |
| Quy trình quy định tối đa 16 chữ số và HALF_EVEN | `DECIMAL64` |
| Quy trình quy định tối đa 34 chữ số và HALF_EVEN | `DECIMAL128` |
| Quy trình cần precision hoặc rounding mode khác | Tạo `MathContext` riêng |
| Đầu ra phải có đúng 2 vị trí thập phân | Xác định scale bằng API phù hợp; các hằng số này không cố định scale |

Với phép chia không hữu hạn, cần nêu rõ xấp xỉ chấp nhận được thay vì dùng `UNLIMITED` rồi bắt ngoại lệ như một cách chọn chính sách ngẫu nhiên.

Context chỉ áp dụng cho lời gọi nhận nó. Một đối tượng `BigDecimal` tạo từ kết quả `DECIMAL64` không “nhớ” chính sách ấy để tự áp dụng cho phép nhân tiếp theo. Nếu quy trình yêu cầu làm tròn từng bước theo cùng context, phải truyền context vào từng bước.

Ngược lại, không nên thêm context vào mọi phép toán nếu yêu cầu là tính chính xác các bước hữu hạn rồi mới làm tròn cuối. Làm tròn trung gian có thể thay đổi tổng hoặc kết quả sau phép trừ hai số gần nhau. Việc chọn một hằng số không tự xác định vị trí làm tròn trong thuật toán.

## 7. Những hiểu nhầm cần loại bỏ

- `UNLIMITED` không phải độ chính xác vô hạn cho mọi số thực; thương lặp vô hạn vẫn không biểu diễn được chính xác.
- `DECIMAL32` không phải 32 chữ số và `DECIMAL64` không chuyển phép toán sang kiểu `double`.
- `DECIMAL128` không làm mọi dữ liệu đầu vào trở nên chính xác. Nếu đầu vào đã mất chữ số khi qua `double`, context không phục hồi các chữ số đó.
- `HALF_EVEN` không có nghĩa là kết quả luôn là số nguyên chẵn; chỉ chữ số cuối tại mức làm tròn được xét khi hai ứng viên cách đều.
- Tăng precision không thay thế kiểm chứng sai số cho một chuỗi tính toán dài.
- Các đối tượng dựng sẵn bất biến; muốn đổi rounding mode hãy tạo context khác, không tìm cách sửa hằng số.

## 8. Tự kiểm tra

1. `DECIMAL64.getPrecision()` trả bao nhiêu? Có phải scale không?
2. `UNLIMITED.getRoundingMode()` là `HALF_UP`; vậy `1 / 7` có tự được làm tròn không?
3. `new MathContext(16)` có cùng cấu hình với `DECIMAL64` không?
4. Số `1E+1000` có tự bị loại khi gọi `round(DECIMAL32)` không?

Đáp án:

1. 16, là giới hạn chữ số có nghĩa, không phải scale.
2. Không; precision 0 yêu cầu tính chính xác, nên phép chia ấy ném ngoại lệ.
3. Không; constructor dùng `HALF_UP`, còn `DECIMAL64` dùng `HALF_EVEN`.
4. Không; context không áp đặt miền số mũ decimal32 và giá trị này chỉ có một chữ số có nghĩa.

Tham khảo hợp đồng API hiện hành: [MathContext trong Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/MathContext.html) và [BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html).
