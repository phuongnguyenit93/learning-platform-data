# MathContext trong Java: precision và RoundingMode

## 1. Bài toán mà MathContext giải quyết

Khi tính toán với `BigDecimal`, có hai câu hỏi độc lập:

- **Được giữ bao nhiêu chữ số có nghĩa?** Ví dụ kết quả phép chia `1 / 3` không thể biểu diễn hết bằng một số thập phân hữu hạn, nên cần quyết định mức chính xác.
- **Nếu phải bỏ chữ số, làm tròn theo quy tắc nào?** Với `2.5`, có thể làm tròn thành `2` hoặc `3`, tùy quy tắc.

`java.math.MathContext` gói hai quyết định này vào một đối tượng bất biến:

```java
MathContext context = new MathContext(5, RoundingMode.HALF_EVEN);
```

Ở đây `precision = 5` là **tối đa năm chữ số có nghĩa của kết quả**; `RoundingMode.HALF_EVEN` quyết định cách xử lý phần chữ số bị loại bỏ. `MathContext` được truyền vào các phép toán `BigDecimal` hoặc phương thức `round` để giới hạn độ chính xác của kết quả. `MathContext` không mô tả số chữ số sau dấu thập phân và cũng không tự động áp dụng cho mọi phép toán.

Ví dụ:

| Số ban đầu | `MathContext(3, HALF_UP)` | Giải thích |
|---|---|---|
| `12345.67` | `1.23E+4` (giá trị `12300`) | Giữ ba chữ số có nghĩa: 1, 2, 3; chữ số kế là 4 |
| `12.345` | `12.3` | Giữ ba chữ số 1, 2, 3; chữ số kế là 4 |
| `0.0012345` | `0.00123` | Các số 0 đứng trước 1 không chiếm chữ số có nghĩa |
| `9.999` | `10.0` | Làm tròn gây nhớ sang hàng cao hơn nhưng vẫn có ba chữ số có nghĩa |

Để hiểu đúng kết quả, cần phân biệt **giá trị**, **precision** và **scale**.

## 2. Precision của BigDecimal khác scale như thế nào?

`BigDecimal` mô tả số thập phân thông qua *unscaled value* và *scale*: về mặt toán học,

```text
giá trị = unscaledValue × 10^(-scale)
```

- `BigDecimal.precision()`: số chữ số của giá trị không chia tỷ lệ (*unscaled value*), không tính dấu âm; các số 0 ở cuối biểu diễn có thể vẫn được tính.
- `BigDecimal.scale()`: số chữ số được dời sang phải dấu thập phân theo biểu diễn của đối tượng; scale có thể bằng 0 hoặc âm.
- `MathContext.getPrecision()`: số chữ số có nghĩa **tối đa** dùng khi một phép toán có context tạo ra kết quả; đây không phải thuộc tính cố định của mọi `BigDecimal` liên quan.

| Giá trị tạo từ chuỗi | `precision()` | `scale()` | Ý nghĩa |
|---|---:|---:|---|
| `"123.4500"` | 7 | 4 | Bốn chữ số sau dấu chấm, gồm hai số 0 cuối |
| `"0.00123"` | 3 | 5 | Ba chữ số có nghĩa, năm chữ số sau dấu chấm |
| `"100.00"` | 5 | 2 | Biểu diễn vẫn giữ hai số 0 cuối |
| `"1E+3"` | 1 | -3 | Giá trị bằng `1000`, scale âm |

Ví dụ hai thao tác hoàn toàn khác nhau:

```java
BigDecimal x = new BigDecimal("12.345");

BigDecimal byPrecision = x.round(
    new MathContext(4, RoundingMode.HALF_UP)
); // 12.35: tối đa 4 chữ số có nghĩa

BigDecimal byScale = x.setScale(4, RoundingMode.HALF_UP);
// 12.3450: đúng 4 chữ số sau dấu chấm
```

**Quy tắc chọn:** dùng `MathContext` để kiểm soát chữ số có nghĩa trong phép toán; dùng `setScale` để kiểm soát số chữ số thập phân của đầu ra hoặc đơn vị đo/tiền tệ. Một bài toán có thể cần cả hai, ở các bước khác nhau.

## 3. Tạo MathContext và chọn precision

```java
import java.math.MathContext;
import java.math.RoundingMode;

MathContext a = new MathContext(6);
// precision = 6, chế độ mặc định là HALF_UP

MathContext b = new MathContext(6, RoundingMode.HALF_EVEN);
// precision = 6, chế độ HALF_EVEN

int digits = b.getPrecision();               // 6
RoundingMode mode = b.getRoundingMode();     // HALF_EVEN

MathContext unlimited = MathContext.UNLIMITED;
```

`MathContext` bất biến: không có thao tác đổi `precision` hoặc `roundingMode` tại chỗ. Có thể tái sử dụng cùng context ở nhiều phép toán. Precision âm không hợp lệ; precision bằng `0` mang ý nghĩa **không giới hạn chữ số có nghĩa**.

Java cung cấp một số context đặt sẵn:

| Hằng số | Precision | RoundingMode |
|---|---:|---|
| `MathContext.UNLIMITED` | 0 | `HALF_UP` (thường không được dùng vì không làm tròn theo precision) |
| `MathContext.DECIMAL32` | 7 | `HALF_EVEN` |
| `MathContext.DECIMAL64` | 16 | `HALF_EVEN` |
| `MathContext.DECIMAL128` | 34 | `HALF_EVEN` |

Các tên `DECIMAL32/64/128` gợi đến định dạng thập phân IEEE 754, nhưng việc chọn hằng số không có nghĩa `BigDecimal` biến thành kiểu dấu phẩy động nhị phân như `float`/`double`. Context chỉ quy định precision và rounding cho các phép toán được áp dụng.

**Lưu ý về `UNLIMITED`:** “không giới hạn precision” không đồng nghĩa “mọi phép chia đều thành công”. `1 / 8` có biểu diễn thập phân hữu hạn, còn `1 / 3` có khai triển vô hạn; `BigDecimal.divide(divisor)` hoặc `divide(divisor, MathContext.UNLIMITED)` sẽ ném `ArithmeticException` cho phép chia không thể biểu diễn chính xác hữu hạn. Chế độ làm tròn trong `UNLIMITED` không giải quyết vấn đề này.

## 4. Các RoundingMode và ý nghĩa với số âm

Các chế độ thuộc enum `java.math.RoundingMode`, độc lập với `MathContext` và cũng dùng được với `setScale`, `divide`.

| Chế độ | Nguyên tắc | `2.5` → số nguyên | `-2.5` → số nguyên |
|---|---|---:|---:|
| `UP` | Bỏ phần dư theo hướng **xa 0** | `3` | `-3` |
| `DOWN` | Bỏ phần dư theo hướng **về 0** | `2` | `-2` |
| `CEILING` | Hướng về **+∞** | `3` | `-2` |
| `FLOOR` | Hướng về **−∞** | `2` | `-3` |
| `HALF_UP` | Gần nhất; nếu đúng giữa hai mức thì **xa 0** | `3` | `-3` |
| `HALF_DOWN` | Gần nhất; nếu đúng giữa hai mức thì **về 0** | `2` | `-2` |
| `HALF_EVEN` | Gần nhất; nếu đúng giữa thì chữ số cuối được giữ là **chẵn** | `2` | `-2` |
| `UNNECESSARY` | Cấm làm tròn không chính xác; ném lỗi nếu buộc bỏ chữ số khác 0 | lỗi | lỗi |

Trong bảng, “→ số nguyên” tương đương `new BigDecimal("2.5").setScale(0, mode)` và phép tính tương tự với số âm.

Với ba chế độ `HALF_*`, phần lớn giá trị không nằm đúng trung điểm sẽ cho cùng kết quả gần nhất. Khác biệt rõ nhất nằm ở trường hợp *tie*:

```text
2.5 → HALF_UP: 3     HALF_DOWN: 2     HALF_EVEN: 2
3.5 → HALF_UP: 4     HALF_DOWN: 3     HALF_EVEN: 4
2.25 (1 chữ số sau dấu chấm) → HALF_EVEN: 2.2
2.35 (1 chữ số sau dấu chấm) → HALF_EVEN: 2.4
```

Với `HALF_EVEN`, “chẵn” nói đến **chữ số cuối còn lại**, không phải kiểm tra xem toàn bộ số đã làm tròn có phải số nguyên chẵn hay không. Nó giúp giảm thiên lệch tích lũy khi có nhiều lần làm tròn đối xứng, nhưng không phải quy tắc bắt buộc cho mọi nghiệp vụ. `HALF_UP` cũng không phải “luôn làm tròn lên”: `2.41` về số nguyên vẫn bằng `2`.

`UP` khác `CEILING` ở số âm; `DOWN` khác `FLOOR` ở số âm. Không suy luận chế độ theo tên tiếng Anh đơn lẻ mà bỏ qua hướng trục số.

## 5. MathContext áp dụng ở đâu trong BigDecimal?

Những cách dùng điển hình:

```java
MathContext mc = new MathContext(4, RoundingMode.HALF_EVEN);

BigDecimal value = new BigDecimal("123.456");
BigDecimal rounded = value.round(mc);

BigDecimal sum = value.add(new BigDecimal("7.89"), mc);
BigDecimal difference = value.subtract(new BigDecimal("7.89"), mc);
BigDecimal product = value.multiply(new BigDecimal("7.89"), mc);
BigDecimal quotient = value.divide(new BigDecimal("7.89"), mc);

BigDecimal constructed = new BigDecimal("123.456", mc);
```

Các phương thức này trả về `BigDecimal` mới; `BigDecimal` là bất biến. Nếu muốn giữ kết quả, phải gán biến, ví dụ `value = value.round(mc)`; gọi `value.round(mc);` riêng lẻ sẽ không đổi `value`.

Đặc biệt, **context không tự lan truyền**. Ví dụ:

```java
MathContext mc = new MathContext(3, RoundingMode.HALF_UP);
BigDecimal a = new BigDecimal("10.1234");
BigDecimal b = new BigDecimal("1.2345");

BigDecimal exactSum = a.add(b);       // 11.3579
BigDecimal roundedSum = a.add(b, mc); // 11.4
```

Việc tạo `a`, `b` hoặc gọi một phép toán có `mc` không tạo “precision toàn cục” cho các phép toán tiếp theo. Phải truyền context rõ ràng ở những bước muốn giới hạn chữ số.

### Phép chia: trường hợp đặc biệt dễ sai

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");
BigDecimal eight = new BigDecimal("8");

BigDecimal exact = one.divide(eight); // 0.125
BigDecimal approximate = one.divide(
    three, new MathContext(4, RoundingMode.HALF_UP)
); // 0.3333

// one.divide(three) ném ArithmeticException vì 1/3 vô hạn.
```

Có hai API phổ biến, phục vụ hai nhu cầu khác nhau:

- `a.divide(b, mc)` yêu cầu kết quả theo **số chữ số có nghĩa** (`mc.precision`).
- `a.divide(b, scale, roundingMode)` yêu cầu kết quả theo **số chữ số sau dấu thập phân** (`scale`).

Ví dụ `1 / 3`: precision 4 cho `0.3333`; scale 2 cho `0.33`. Nhưng với `12345 / 7`, precision 2 và scale 2 tạo kết quả có mức chi tiết rất khác nhau.

Ngay cả khi truyền context, `RoundingMode.UNNECESSARY` vẫn có thể khiến phép tính ném `ArithmeticException` nếu kết quả chính xác cần nhiều chữ số hơn precision cho phép.

## 6. Ví dụ Java 17+ hoàn chỉnh, có thể chạy

Tạo file `MathContextDemo.java`:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class MathContextDemo {
    public static void main(String[] args) {
        MathContext mc = new MathContext(3, RoundingMode.HALF_UP);

        BigDecimal amount = new BigDecimal("12345.67");
        BigDecimal rounded = amount.round(mc);
        BigDecimal third = BigDecimal.ONE.divide(new BigDecimal("3"), mc);
        BigDecimal exact = BigDecimal.ONE.divide(new BigDecimal("8"));
        BigDecimal scaled = new BigDecimal("2.345")
                .setScale(2, RoundingMode.HALF_EVEN);

        System.out.println("precision=" + mc.getPrecision()
                + ", rounding=" + mc.getRoundingMode());
        System.out.println("rounded=" + rounded.toPlainString());
        System.out.println("1/3=" + third.toPlainString());
        System.out.println("1/8=" + exact.toPlainString());
        System.out.println("scale=" + scaled.toPlainString());

        try {
            BigDecimal.ONE.divide(new BigDecimal("3"));
        } catch (ArithmeticException ex) {
            System.out.println("1/3 exact: ArithmeticException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac MathContextDemo.java
java MathContextDemo
```

Kết quả chính xác:

```text
precision=3, rounding=HALF_UP
rounded=12300
1/3=0.333
1/8=0.125
scale=2.34
1/3 exact: ArithmeticException
```

Giải thích: `amount` được rút về ba chữ số có nghĩa nên mang giá trị `12300`; `toPlainString()` hiển thị dạng thường thay cho ký pháp mũ có thể xuất hiện trong `toString()`. `1/3` được xấp xỉ dưới context; `1/8` biểu diễn được chính xác. `2.345` làm tròn `HALF_EVEN` ở hai chữ số sau dấu chấm thành `2.34` vì chữ số hàng phần trăm đang được giữ là 4 (chẵn). Cuối cùng, phép chia `1/3` không context ném ngoại lệ như đã bắt.

## 7. Trình tự làm tròn ảnh hưởng kết quả

Sử dụng context sớm sẽ làm mất chữ số trước các bước sau. Trong chuỗi tính toán dài, điều này có thể tạo ra **double rounding** (làm tròn hai lần) và sai lệch tích lũy.

```java
BigDecimal x = new BigDecimal("1.249");
MathContext mc = new MathContext(3, RoundingMode.HALF_UP);

BigDecimal viaTwoSteps = x.round(mc)
        .setScale(1, RoundingMode.HALF_UP); // 1.3

BigDecimal direct = x.setScale(1, RoundingMode.HALF_UP); // 1.2
```

Vì sao? Bước đầu `1.249` → `1.25`; bước hai gặp đúng trung điểm nên `1.25` → `1.3`. Trong khi đó, làm tròn trực tiếp `1.249` ở một chữ số sau dấu chấm cho `1.2`.

Khi bài toán cần tổng hợp nhiều phần tử, hãy xác định **thời điểm làm tròn** theo đặc tả. Nếu không bắt buộc làm tròn từng phép, thường nên duy trì đủ chữ số ở bước trung gian rồi thực hiện một lần làm tròn tại điểm được quy định. Trường hợp cần tính gần đúng khi chia vô hạn, chọn precision đủ lớn (có thể thêm *guard digits*) và đánh giá sai số, thay vì mặc định một context rất thấp cho mọi bước.

Không có một `MathContext` đúng cho mọi miền dữ liệu. Độ chính xác tài chính, đo lường, thống kê, giao dịch và làm tròn thuế có thể có quy tắc khác nhau.

## 8. Ví dụ nghiệp vụ: làm tròn số tiền cuối bước tính

Giả sử một bài toán minh họa yêu cầu tiền thuế làm tròn đến hai chữ số thập phân bằng `HALF_UP` (đây chỉ là quy tắc giả định của ví dụ, không khẳng định quy định thuế thực tế):

```java
BigDecimal subtotal = new BigDecimal("19.99");
BigDecimal rate = new BigDecimal("0.0825");

BigDecimal tax = subtotal.multiply(rate)
        .setScale(2, RoundingMode.HALF_UP);
BigDecimal total = subtotal.add(tax);

System.out.println("tax=" + tax.toPlainString());     // tax=1.65
System.out.println("total=" + total.toPlainString()); // total=21.64
```

`19.99 × 0.0825 = 1.649175` chính xác trước khi chuyển thành `1.65`. Nếu nghiệp vụ yêu cầu làm tròn số tiền theo từng dòng hàng trước khi cộng, kết quả có thể khác làm tròn sau khi cộng cả hóa đơn. Quy tắc này phải được xác định ở cấp nghiệp vụ; `MathContext` không tự lựa chọn thay.

Khi phép chia tạo tỷ lệ hoặc đơn giá cần xấp xỉ, có thể định nghĩa context cho bước trung gian:

```java
MathContext working = new MathContext(16, RoundingMode.HALF_EVEN);

BigDecimal totalAmount = new BigDecimal("100.00");
BigDecimal units = new BigDecimal("3");
BigDecimal approximateUnitPrice = totalAmount.divide(units, working);

BigDecimal displayPrice = approximateUnitPrice
        .setScale(2, RoundingMode.HALF_UP);
// approximateUnitPrice ~= 33.33333333333333; displayPrice = 33.33
```

Trong hệ thống thật, precision trung gian phải được chọn theo độ lớn đầu vào, số phép tính và yêu cầu sai số. Precision 16 ở đây chỉ là ví dụ.

## 9. Khởi tạo BigDecimal đúng để precision có ý nghĩa

`BigDecimal` có thể lưu trữ chính xác chữ số thập phân nhập dưới dạng chuỗi. Tránh đưa trực tiếp literal `double` vào constructor khi muốn số thập phân theo cách con người viết:

```java
BigDecimal recommended = new BigDecimal("0.1");
BigDecimal alternative = BigDecimal.valueOf(0.1);
BigDecimal surprising = new BigDecimal(0.1);
```

`recommended` và `alternative` có giá trị thập phân `0.1`. Đối tượng `surprising` mang giá trị chuyển đổi **chính xác từ số nhị phân `double`**, vốn không bằng đúng `0.1`; làm tròn nó bằng `MathContext` có thể che đi nguồn sai số nhưng không xóa được nguyên nhân. Với dữ liệu tiền hoặc dữ liệu đo yêu cầu biểu diễn thập phân kiểm soát được, ưu tiên chuỗi đầu vào hoặc parse chuỗi số thập phân có hợp đồng rõ ràng.

Việc hiển thị cũng cần cân nhắc: `toString()` có thể dùng ký pháp mũ; `toPlainString()` không dùng ký pháp mũ; `setScale(2, ...)` bảo đảm đúng hai chữ số thập phân trong biểu diễn số dùng để hiển thị. Không nên suy ra yêu cầu đầu ra từ riêng `MathContext.precision`.

## 10. Lỗi phổ biến và cách kiểm tra

| Lỗi | Hậu quả | Cách làm đúng |
|---|---|---|
| Hiểu `precision = 2` là hai số sau dấu chấm | `123.45` có thể thành `1.2E+2` | Dùng `setScale(2, mode)` khi cần hai chữ số thập phân |
| Chia `1 / 3` không có rounding | `ArithmeticException` | Dùng `divide` với context hoặc scale và rounding phù hợp |
| Nghĩ `UNLIMITED` chia số nào cũng được | Phép chia thập phân vô hạn vẫn lỗi | Xác định sai số cho phép và đặt context hữu hạn |
| Dùng `HALF_UP` khi nghiệp vụ đòi `HALF_EVEN` | Khác kết quả ở các tie | Đưa mode vào đặc tả và test |
| Nhầm `UP` với `CEILING`, `DOWN` với `FLOOR` | Làm tròn sai với số âm | Test đồng thời số dương và âm |
| Gọi `x.round(mc)` mà không gán kết quả | `x` giữ giá trị cũ | Gán `x = x.round(mc)` nếu cần |
| Áp dụng context quá thấp ở mọi phép toán | Sai lệch qua nhiều bước, double rounding | Quy định điểm làm tròn; giữ độ chính xác trung gian đủ lớn |
| Tạo số bằng `new BigDecimal(0.1)` | Mang sai số biểu diễn nhị phân | Dùng `"0.1"` hoặc `BigDecimal.valueOf(0.1)` |
| Dùng `equals` để so sánh giá trị số thập phân khác scale | `1.0` khác `1.00` với `equals` | Dùng `compareTo(...) == 0` nếu chỉ xét giá trị số; dùng `equals` khi scale cũng quan trọng |
| Chọn rounding tùy tiện cho tiền/thuế | Có thể vi phạm yêu cầu nghiệp vụ | Ghi rõ loại phép tính, bước làm tròn, scale và rounding mode |

Để phát hiện làm tròn ngoài ý muốn trong các phép tính cần chính xác tuyệt đối, dùng `RoundingMode.UNNECESSARY` như một phép kiểm tra:

```java
new BigDecimal("12.340").setScale(2, RoundingMode.UNNECESSARY);
// Thành công: chỉ loại bỏ số 0 không làm đổi giá trị.

new BigDecimal("12.345").setScale(2, RoundingMode.UNNECESSARY);
// Ném ArithmeticException vì phải bỏ chữ số 5 khác 0.
```

Nếu hiển thị hoặc kiểm tra đầu ra bằng test, ưu tiên so sánh có chủ đích: dùng `compareTo` cho giá trị toán học, kiểm tra thêm `scale` hay chuỗi khi định dạng là một phần hợp đồng. `round(mc)` không bảo đảm tự chuẩn hóa scale: kết quả đã đủ precision có thể giữ nguyên các số 0 cuối.

## 11. Bài tập tự kiểm tra

1. `new BigDecimal("0.009876").round(new MathContext(2, HALF_UP))` nhận giá trị gì?
2. `new BigDecimal("-2.1").setScale(0, CEILING)` và cùng phép tính với `FLOOR` khác nhau thế nào?
3. Vì sao `new BigDecimal("100.00").precision()` bằng 5, còn `new BigDecimal("1E+2").precision()` bằng 1 dù cùng giá trị?
4. Một bảng báo cáo cần đúng ba chữ số sau dấu thập phân: nên chỉ dùng `MathContext(3)` hay `setScale(3, mode)`?
5. Phép chia `2 / 7` được yêu cầu bốn chữ số có nghĩa: lời gọi `BigDecimal` nào phù hợp?

Đáp án và lập luận:

1. `0.0099`: hai chữ số có nghĩa là 9 và 8; chữ số tiếp theo là 7 nên làm tròn 8 lên 9.
2. `CEILING` cho `-2` (hướng +∞), `FLOOR` cho `-3` (hướng −∞).
3. `precision()` dựa trên biểu diễn không chia tỷ lệ: `100.00` có năm chữ số, `1E+2` có một; giá trị toán học giống nhau không buộc precision/scale giống nhau.
4. Dùng `setScale(3, mode)`, bởi mục tiêu là vị trí dấu thập phân, không phải tổng chữ số có nghĩa.
5. Ví dụ `BigDecimal.valueOf(2).divide(BigDecimal.valueOf(7), new MathContext(4, RoundingMode.HALF_UP))`, kết quả `0.2857`.

**Ghi nhớ:** `MathContext = (precision, RoundingMode)` điều khiển **số chữ số có nghĩa và cách làm tròn của kết quả phép toán có sử dụng context**. `setScale` điều khiển **vị trí thập phân**. Chọn mức chính xác, chế độ làm tròn và thời điểm áp dụng theo yêu cầu của phép tính; với `BigDecimal`, mọi thao tác đều phải được gọi rõ ràng.
