# UNLIMITED, DECIMAL32, DECIMAL64 và DECIMAL128 trong Java

## 1. Vấn đề cần giải quyết

Khi tính toán với `BigDecimal`, kết quả có thể cần rất nhiều chữ số. Phép chia `1 / 3` có vô hạn chữ số thập phân; ngay cả phép nhân hai số thập phân hữu hạn cũng có thể tạo ra kết quả dài hơn mức độ chính xác cần dùng. `MathContext` trong gói `java.math` cho phép chỉ định **độ chính xác của kết quả (precision)** và **quy tắc làm tròn (rounding mode)** cho từng phép toán.

Java cung cấp bốn hằng `MathContext` thường dùng:

- `MathContext.UNLIMITED`: tính chính xác, không chủ động làm tròn vì giới hạn chữ số.
- `MathContext.DECIMAL32`: tối đa 7 chữ số có nghĩa, làm tròn `HALF_EVEN`.
- `MathContext.DECIMAL64`: tối đa 16 chữ số có nghĩa, làm tròn `HALF_EVEN`.
- `MathContext.DECIMAL128`: tối đa 34 chữ số có nghĩa, làm tròn `HALF_EVEN`.

Các tên `DECIMAL32`/`DECIMAL64`/`DECIMAL128` gợi đến độ chính xác của các định dạng số thập phân IEEE 754. Trong Java, chúng là **các cấu hình tính toán cho `BigDecimal`**, không phải các kiểu dữ liệu 32/64/128 bit và không áp đặt toàn bộ giới hạn số mũ, biểu diễn hoặc lưu trữ của định dạng IEEE 754 tương ứng.

## 2. Phân biệt precision, scale và MathContext

Một `BigDecimal` gồm giá trị nguyên không chia tỷ lệ (`unscaledValue`) và `scale`; giá trị toán học là `unscaledValue × 10^(-scale)`.

- **Precision**: số chữ số có nghĩa trong biểu diễn thập phân của `BigDecimal`. Ví dụ, `123.4500` có precision 7 vì cả hai chữ số `0` cuối đang được giữ trong biểu diễn.
- **Scale**: số chữ số bên phải dấu thập phân theo cách lưu trữ thông thường; `123.4500` có scale 4. Scale có thể âm; ví dụ `1.23E+4` có scale -2.
- **MathContext precision**: giới hạn chữ số có nghĩa của **kết quả khi phép toán được gọi với context đó**. Không đồng nghĩa với số chữ số sau dấu phẩy.
- **Rounding mode**: quyết định làm gì với các chữ số bị loại khi kết quả vượt precision.

Ví dụ: `12345.6789` có 9 chữ số có nghĩa. Làm tròn với `DECIMAL32` (7 chữ số) tạo `12345.68`: giữ tổng cộng 7 chữ số có nghĩa, chứ không phải giữ 7 chữ số sau dấu phẩy. Với số `0.000123456789`, các chữ số `0` đứng đầu không làm tăng số chữ số có nghĩa.

`MathContext` là đối tượng bất biến. Chỉ việc khai báo context **không tự thay đổi** các `BigDecimal` sẵn có và Java không có MathContext mặc định toàn cục áp lên mọi phép toán. Phải truyền context cho phép toán, gọi `round(context)`, hoặc dùng constructor nhận context.

## 3. Bảng so sánh bốn hằng có sẵn

| MathContext | `getPrecision()` | `getRoundingMode()` | Ý nghĩa |
| --- | ---: | --- | --- |
| `UNLIMITED` | 0 | `HALF_UP` | Precision bằng 0 nghĩa là **không giới hạn số chữ số**, không có nghĩa chỉ giữ 0 chữ số. Chế độ `HALF_UP` được lưu trong object nhưng không được dùng để làm tròn theo precision khi giới hạn là 0. |
| `DECIMAL32` | 7 | `HALF_EVEN` | Giữ tối đa 7 chữ số có nghĩa của kết quả. |
| `DECIMAL64` | 16 | `HALF_EVEN` | Giữ tối đa 16 chữ số có nghĩa của kết quả. |
| `DECIMAL128` | 34 | `HALF_EVEN` | Giữ tối đa 34 chữ số có nghĩa của kết quả. |

Về cấu hình, bốn hằng tương ứng với:

~~~java
MathContext.UNLIMITED;  // new MathContext(0, RoundingMode.HALF_UP)
MathContext.DECIMAL32;  // new MathContext(7, RoundingMode.HALF_EVEN)
MathContext.DECIMAL64;  // new MathContext(16, RoundingMode.HALF_EVEN)
MathContext.DECIMAL128; // new MathContext(34, RoundingMode.HALF_EVEN)
~~~

Đây là các giá trị có sẵn để tái sử dụng; comment giải thích cấu hình tương đương, không phải các lệnh gán lại hằng. `new MathContext(7)` mặc định dùng `HALF_UP`, **khác** `DECIMAL32` ở quy tắc làm tròn. Tương tự, `new MathContext(16)` và `new MathContext(34)` không mặc nhiên có `HALF_EVEN`.

## 4. Chính xác tuyệt đối và làm tròn có kiểm soát

### 4.1. UNLIMITED không có nghĩa là mọi phép chia đều trả về một giá trị

Với phép cộng, trừ và nhân các số `BigDecimal` hữu hạn, Java có thể trả về kết quả thập phân chính xác. Phép chia chỉ có kết quả thập phân hữu hạn khi phân số tối giản có mẫu số chứa các thừa số nguyên tố **chỉ gồm 2 và/hoặc 5**. Ví dụ:

- `1 / 8 = 0.125`: biểu diễn thập phân hữu hạn, `divide(8, UNLIMITED)` thành công.
- `1 / 40 = 0.025`: cũng hữu hạn.
- `1 / 3 = 0.3333…`: thập phân vô hạn tuần hoàn, không thể biểu diễn chính xác bằng một `BigDecimal` hữu hạn. Gọi `divide(3, UNLIMITED)` ném `ArithmeticException`.
- `1 / 7` cũng không có biểu diễn thập phân hữu hạn.

`UNLIMITED` không tự chọn số chữ số hay độ làm tròn khi gặp phép chia vô hạn. Để nhận giá trị gần đúng có giới hạn, truyền một context có precision dương như `DECIMAL64` hoặc chọn `scale` và `RoundingMode` bằng overload thích hợp của `divide`. Các phép toán như `sqrt` với context unlimited cũng yêu cầu kết quả chính xác có thể biểu diễn; căn không chính xác như `sqrt(2)` không thể được trả về dưới dạng hữu hạn chính xác.

### 4.2. Ba context DECIMAL làm tròn đến chữ số có nghĩa

Với `1 / 3`:

| Context | Kết quả của `BigDecimal.ONE.divide(new BigDecimal("3"), context)` |
| --- | --- |
| `UNLIMITED` | Ném `ArithmeticException` |
| `DECIMAL32` | `0.3333333` (7 chữ số 3) |
| `DECIMAL64` | `0.3333333333333333` (16 chữ số 3) |
| `DECIMAL128` | `0.3333333333333333333333333333333333` (34 chữ số 3) |

Nếu làm tròn `123456789.987654321`, `DECIMAL32` cho `1.234568E+8`, `DECIMAL64` cho `123456789.9876543` và `DECIMAL128` giữ nguyên `123456789.987654321`. Ký hiệu `E+8` là dạng hiển thị khoa học của `BigDecimal.toString()`; giá trị tương ứng là `123456800`.

### 4.3. HALF_EVEN là gì?

`RoundingMode.HALF_EVEN` thường được gọi là *banker's rounding*: nếu phần bỏ đi **đúng bằng một nửa đơn vị ở vị trí làm tròn**, chọn chữ số cuối được giữ là **chẵn**. Nếu lớn hơn một nửa thì làm tròn ra xa số 0; nếu nhỏ hơn thì giữ gần số 0 hơn (diễn giải với số dương; chế độ làm tròn được định nghĩa cho cả số âm).

Ví dụ khi chỉ giữ **1 chữ số có nghĩa**:

- `2.5 → 2`, vì chữ số giữ lại là 2 (chẵn).
- `3.5 → 4`, vì phải tăng 3 lên 4 (chẵn).
- `2.51 → 3`: phần bỏ đi lớn hơn đúng một nửa, nên không áp dụng quy tắc hòa chẵn.

`HALF_EVEN` hữu ích khi nhiều giá trị thường xuyên được làm tròn vì tránh thiên lệch một chiều trong các trường hợp đúng nửa. Tuy nhiên, quy tắc nghiệp vụ có thể bắt buộc `HALF_UP`, `DOWN` hay `UNNECESSARY`; đừng tự đổi quy tắc chỉ vì tên preset nghe có vẻ phù hợp.

## 5. Ví dụ Java hoàn chỉnh (Java 17+)

Tạo file `MathContextPresetsDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class MathContextPresetsDemo {
    public static void main(String[] args) {
        BigDecimal one = new BigDecimal("1");
        BigDecimal three = new BigDecimal("3");

        System.out.println("UNLIMITED 1/8: " +
                one.divide(new BigDecimal("8"), MathContext.UNLIMITED));
        try {
            System.out.println("UNLIMITED 1/3: " +
                    one.divide(three, MathContext.UNLIMITED));
        } catch (ArithmeticException e) {
            System.out.println("UNLIMITED 1/3: ArithmeticException");
        }

        System.out.println("DECIMAL32 1/3: " +
                one.divide(three, MathContext.DECIMAL32));
        System.out.println("DECIMAL64 1/3: " +
                one.divide(three, MathContext.DECIMAL64));
        System.out.println("DECIMAL128 1/3: " +
                one.divide(three, MathContext.DECIMAL128));

        BigDecimal value = new BigDecimal("123456789.987654321");
        System.out.println("DECIMAL32 round: " + value.round(MathContext.DECIMAL32));
        System.out.println("DECIMAL64 round: " + value.round(MathContext.DECIMAL64));
        System.out.println("DECIMAL128 round: " + value.round(MathContext.DECIMAL128));

        BigDecimal a = new BigDecimal("1.234567");
        BigDecimal b = new BigDecimal("0.0000009");
        System.out.println("sum exact: " + a.add(b));
        System.out.println("sum DECIMAL32: " + a.add(b, MathContext.DECIMAL32));

        MathContext oneDigit = new MathContext(1, RoundingMode.HALF_EVEN);
        System.out.println("HALF_EVEN 2.5: " +
                new BigDecimal("2.5").round(oneDigit));
        System.out.println("HALF_EVEN 3.5: " +
                new BigDecimal("3.5").round(oneDigit));
        System.out.println("setScale(2): " +
                new BigDecimal("1.234567").setScale(2, RoundingMode.HALF_EVEN));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MathContextPresetsDemo.java
java MathContextPresetsDemo
~~~

Kết quả chuẩn:

~~~text
UNLIMITED 1/8: 0.125
UNLIMITED 1/3: ArithmeticException
DECIMAL32 1/3: 0.3333333
DECIMAL64 1/3: 0.3333333333333333
DECIMAL128 1/3: 0.3333333333333333333333333333333333
DECIMAL32 round: 1.234568E+8
DECIMAL64 round: 123456789.9876543
DECIMAL128 round: 123456789.987654321
sum exact: 1.2345679
sum DECIMAL32: 1.234568
HALF_EVEN 2.5: 2
HALF_EVEN 3.5: 4
setScale(2): 1.23
~~~

Đoạn `try/catch` chỉ bắt phép chia không thể biểu diễn chính xác với `UNLIMITED`. Các phép `round` tác động lên **kết quả trả về**; đối tượng `value` ban đầu vẫn giữ đầy đủ chữ số vì `BigDecimal` bất biến. Ví dụ tổng cho thấy `add(b)` trả giá trị chính xác còn `add(b, DECIMAL32)` trả tổng đã giới hạn 7 chữ số có nghĩa.

## 6. Dùng context đúng trong chương trình thực tế

### 6.1. Cách truyền MathContext

Các API thông dụng nhận tham số `MathContext` gồm `add`, `subtract`, `multiply`, `divide`, `pow` và `sqrt` (nếu phiên bản Java hỗ trợ), cũng như `round` và một số constructor của `BigDecimal`:

~~~java
MathContext mc = MathContext.DECIMAL64;
BigDecimal x = new BigDecimal("19.876543210987654321");
BigDecimal y = new BigDecimal("3");

BigDecimal sum = x.add(y, mc);       // làm tròn tổng theo mc
BigDecimal product = x.multiply(y, mc); // làm tròn tích theo mc
BigDecimal quotient = x.divide(y, mc); // làm tròn thương theo mc
BigDecimal rounded = x.round(mc);    // làm tròn chính x, không sửa x
BigDecimal roundedOnInput = new BigDecimal("19.876543210987654321", mc);
~~~

Đây là **đoạn mã minh họa** bên trong phương thức/khối lệnh có import `java.math.*`, không phải một chương trình `main` độc lập.

Cẩn thận với thời điểm làm tròn. `x.multiply(y, mc).add(z, mc)` có thể khác `x.multiply(y).add(z).round(mc)` vì biểu thức thứ nhất làm tròn ở mỗi bước. Sai số làm tròn trung gian có thể tích lũy; cần quyết định dựa trên yêu cầu của thuật toán, kể cả với precision 34.

### 6.2. Khi nào nên chọn hằng nào?

| Trường hợp | Hướng chọn | Lý do/cảnh báo |
| --- | --- | --- |
| Cộng, trừ, nhân cần kết quả thập phân chính xác | Không truyền context hoặc `UNLIMITED` | Không chủ động làm tròn; vẫn cần xét hiệu năng/bộ nhớ nếu số quá lớn. |
| Chia có khả năng vô hạn tuần hoàn | `DECIMAL32`/`64`/`128` hoặc context tùy chỉnh | Precision dương giúp phép chia trả về kết quả làm tròn. |
| Bài toán yêu cầu khoảng 7 chữ số có nghĩa | `DECIMAL32` | Ít chữ số hơn, nhưng không phù hợp khi cần nhiều thông tin. |
| Cần khoảng 16 chữ số có nghĩa | `DECIMAL64` | Phù hợp nếu yêu cầu số chữ số có nghĩa và `HALF_EVEN` đều được chấp nhận. |
| Cần khoảng 34 chữ số có nghĩa | `DECIMAL128` | Cung cấp precision cao hơn; không có nghĩa mọi phép tính đều chính xác tuyệt đối. |
| Tài chính có quy định 2 chữ số thập phân | `setScale(2, roundingMode)` theo quy tắc nghiệp vụ | Hai chữ số **sau dấu phẩy** không phải 2 chữ số **có nghĩa**; `DECIMAL32` không thay cho scale. |
| Cần quy tắc khác hoặc precision ấn định | `new MathContext(n, mode)` | Ví dụ `new MathContext(20, RoundingMode.HALF_UP)`. |
| Không chấp nhận mất bất kỳ chữ số nào | Context với `RoundingMode.UNNECESSARY` | Ném `ArithmeticException` nếu phép toán cần làm tròn; không tự làm tròn âm thầm. |

Ví dụ, muốn thương có **chính xác hai chữ số sau dấu phẩy**:

~~~java
BigDecimal price = new BigDecimal("10");
BigDecimal count = new BigDecimal("3");
BigDecimal amount = price.divide(count, 2, RoundingMode.HALF_UP);
// amount.toPlainString() là "3.33"
~~~

Ngược lại, `price.divide(count, MathContext.DECIMAL32)` cho `3.333333` (7 chữ số có nghĩa), không đáp ứng quy định hai chữ số thập phân.

### 6.3. Phối hợp precision và scale

Một phép tính có thể giới hạn số chữ số có nghĩa ở bước trung gian bằng `MathContext`, sau đó chuẩn hóa số chữ số thập phân bằng `setScale` ở ranh giới xuất dữ liệu. Khi làm vậy, **hai lần làm tròn có thể tạo sai lệch kép** so với tính chính xác rồi làm tròn một lần ở cuối. Nếu nghiệp vụ cần chính xác tuyệt đối đến thời điểm thanh toán, hãy giữ các phép tính chính xác ở những bước có thể, làm tròn theo quy tắc đã thiết kế tại điểm thích hợp và bổ sung test các trường hợp đúng nửa.

`setScale(2, mode)` yêu cầu scale 2, **không** hạn chế tổng số chữ số có nghĩa: `123456.78` vẫn có 8 chữ số có nghĩa. Còn `round(DECIMAL32)` có thể tạo scale âm hoặc cách hiển thị khoa học nếu phần nguyên lớn.

## 7. Những lỗi phổ biến

1. **Hiểu `UNLIMITED` là "chia được mọi số".** Nó đòi hỏi kết quả chính xác và ném ngoại lệ cho thương tuần hoàn như `1/3`. Cần cung cấp giới hạn precision hoặc scale khi chấp nhận gần đúng.
2. **Nhầm precision với scale.** `DECIMAL64` giới hạn **16 chữ số có nghĩa**, không phải 16 chữ số sau dấu phẩy.
3. **Tưởng preset luôn dùng `HALF_UP`.** Ba preset DECIMAL dùng `HALF_EVEN`; chỉ `UNLIMITED` giữ cấu hình `HALF_UP` và không dùng nó để làm tròn theo precision.
4. **Dùng `new MathContext(7)` thay cho `DECIMAL32` mà không xét mode.** Constructor một tham số dùng `HALF_UP`, nên ở điểm hòa nửa kết quả có thể khác.
5. **Cho rằng DECIMAL128 tương đương một kiểu IEEE decimal128 trọn vẹn.** Java `BigDecimal` không tự áp giới hạn exponent hay định dạng mã hóa của decimal128 chỉ vì truyền context này.
6. **Dùng `new BigDecimal(0.1)` rồi tin rằng context sửa được sai số đầu vào.** Literal `double` `0.1` đã không biểu diễn thập phân chính xác; constructor nhận `double` bảo toàn giá trị nhị phân được chuyển đổi. Dùng `new BigDecimal("0.1")` hoặc cân nhắc `BigDecimal.valueOf(0.1)` để có cách biểu diễn thập phân dự kiến.
7. **Làm tròn quá sớm qua nhiều bước.** Kết quả trung gian mất chữ số có thể ảnh hưởng kết quả cuối; context không bảo đảm số chữ số sau các bước làm tròn vẫn phản ánh phép toán chính xác ban đầu.
8. **So sánh kết quả theo chuỗi hoặc `equals` một cách tùy tiện.** `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` là `false` do scale khác, còn `compareTo(...) == 0` khi giá trị số bằng nhau. Context có thể làm thay đổi scale và dạng `toString()`; đánh giá theo giá trị hay biểu diễn phải đúng mục đích.
9. **Dùng precision cao để thay kiểm tra sai số.** Một kết quả với 34 chữ số vẫn là gần đúng nếu phép chia hoặc bước trung gian phải làm tròn; cần thiết kế ngưỡng sai số/kiểm thử phù hợp.

## 8. Câu hỏi tự kiểm tra

**1. Vì sao `MathContext.UNLIMITED.getPrecision() == 0` nhưng `1/3` lại gây ngoại lệ?** Vì precision 0 biểu thị không giới hạn, buộc phép chia có kết quả chính xác biểu diễn bằng thập phân hữu hạn. `1/3` không đáp ứng điều đó.

**2. Muốn làm tròn tiền `123.456` còn hai chữ số sau dấu phẩy, có nên dùng `DECIMAL32`?** Không. `DECIMAL32` giữ tối đa 7 chữ số có nghĩa, trong trường hợp này có thể không làm tròn gì; nên dùng `setScale(2, mode)` theo quy tắc tiền tệ.

**3. `DECIMAL64` có luôn cho kết quả đúng hơn `DECIMAL32` không?** Nó giữ nhiều chữ số có nghĩa hơn trong cùng kiểu phép tính, nhưng điều đó không tự bảo đảm đầu vào chính xác, cách làm tròn trung gian đúng yêu cầu, hay thuật toán ổn định số học.

**4. Khi nào chọn context tự tạo?** Khi yêu cầu precision hoặc rounding mode khác preset; ví dụ `new MathContext(12, RoundingMode.HALF_UP)` hoặc dùng `UNNECESSARY` để phát hiện tình huống cần làm tròn.

**Ghi nhớ:** Chọn `MathContext` theo **số chữ số có nghĩa** và **quy tắc làm tròn** của phép toán; chọn `setScale` theo **số chữ số thập phân** cần trình bày/lưu trữ. `UNLIMITED` nghĩa là tính chính xác khi có thể biểu diễn, trong khi ba preset `DECIMALxx` chấp nhận làm tròn với `HALF_EVEN`.
