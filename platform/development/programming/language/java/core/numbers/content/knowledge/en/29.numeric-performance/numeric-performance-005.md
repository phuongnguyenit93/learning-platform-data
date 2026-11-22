# Tránh tăng precision hoặc scale không cần thiết với BigDecimal

## 1. Vấn đề và mục tiêu học tập

`BigDecimal` là lựa chọn quan trọng khi Java phải xử lý số thập phân chính xác, chẳng hạn tiền tệ, tỷ lệ hoặc giá trị đo có yêu cầu làm tròn cụ thể. Nhưng “chính xác” không đồng nghĩa với việc luôn giữ **càng nhiều chữ số càng tốt**. Một pipeline cứ kéo dài phần thập phân, nhân nhiều giá trị có scale lớn, hoặc chuyển sang chuỗi thập phân quá dài có thể tăng chi phí bộ nhớ, CPU, lưu trữ và truyền dữ liệu.

Cần phân biệt hai điều:

- **Không đánh mất độ chính xác cần thiết:** không làm tròn tùy tiện, không âm thầm chuyển qua `double`, không xóa scale nếu scale mang ý nghĩa nghiệp vụ.
- **Không tạo độ lớn biểu diễn không cần thiết:** không tự thêm hàng nghìn chữ số 0, không để scale tăng qua nhiều phép nhân mà không có kế hoạch, không yêu cầu precision hoặc cách hiển thị quá mức.

Mục tiêu của bài học là hiểu quan hệ giữa `precision`, `scale` và kích thước biểu diễn; nhận ra những phép toán có thể làm tăng chúng; thiết kế giới hạn hợp lý tại ranh giới tính toán, lưu trữ và hiển thị; kiểm chứng tính đúng đắn trước khi tối ưu.

Điều kiện tiên quyết: **hiệu năng không được đánh đổi âm thầm bằng kết quả sai**. Một phép chuẩn hóa, làm tròn hay cắt precision chỉ hợp lệ khi hợp đồng dữ liệu cho phép.

## 2. Precision và scale không phải một thứ

Một giá trị `BigDecimal` được mô hình hóa như sau:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

Trong đó:

- `unscaledValue()` trả số nguyên không giới hạn kiểu `BigInteger` biểu diễn các chữ số.
- `scale()` chỉ vị trí dấu thập phân theo cơ số 10; có thể dương, bằng 0 hoặc âm.
- `precision()` là số chữ số thập phân trong unscaled value của biểu diễn hiện tại, không tính dấu. Số 0 có precision bằng 1.

Ví dụ:

| Giá trị được tạo | `unscaledValue` | `precision` | `scale` | Giá trị số học |
| --- | ---: | ---: | ---: | --- |
| `new BigDecimal("1.2300")` | `12300` | `5` | `4` | `1.23` |
| `new BigDecimal("1.23")` | `123` | `3` | `2` | `1.23` |
| `new BigDecimal("1000")` | `1000` | `4` | `0` | `1000` |
| `new BigDecimal("1E+3")` | `1` | `1` | `-3` | `1000` |
| `new BigDecimal("1E-100000")` | `1` | `1` | `100000` | `10^-100000` |

Hai số có cùng giá trị theo `compareTo` vẫn có thể khác `equals` vì `equals` xét thêm `scale`. Chẳng hạn `1.2300` và `1.23` có cùng giá trị nhưng khác scale.

Ví dụ cuối trong bảng là một bẫy quan trọng: `1E-100000` có **precision bằng 1** nhưng **scale bằng 100000**. Scale lớn không tự chứng minh rằng đối tượng đang chứa 100000 chữ số của unscaled value; ngược lại, tạo chuỗi plain hoặc ép về scale khác có thể khiến bộ nhớ tăng mạnh.

## 3. Vì sao precision hoặc scale có thể ảnh hưởng hiệu năng?

`BigDecimal` là kiểu **bất biến** (*immutable*). Mỗi phép toán tạo ra kết quả mới (dù implementation đôi khi có thể tái sử dụng object nội bộ hoặc giá trị cache). Số chữ số lớn hơn thường dẫn tới biểu diễn số nguyên lớn hơn, nhiều công việc số học và nhiều dữ liệu phải sao chép hoặc chuyển đổi.

Các tình huống dễ có chi phí không cần thiết:

1. **Scale bị cộng dồn trong phép nhân chính xác**: kết quả giữ cả chữ số 0 cuối, dù các số 0 đó không làm thay đổi giá trị toán học.
2. **`setScale` lên một giá trị quá lớn**: để tăng scale từ 0 lên hàng chục nghìn, có thể phải tạo unscaled value chứa rất nhiều chữ số 0.
3. **Ép chuỗi không có ký pháp mũ**: `toPlainString()` có thể mở rộng một số rất nhỏ hoặc rất lớn thành một chuỗi khổng lồ.
4. **Phép chia với precision/scale quá cao**: tính và giữ nhiều chữ số hơn yêu cầu có thể tốn chi phí đáng kể.
5. **Chuỗi phép toán không có ranh giới**: precision, scale và độ dài khi serialize có thể tăng theo các đầu vào hoặc lặp không được kiểm soát.

Đây là các **nguy cơ phụ thuộc dữ liệu và thuật toán**, không phải khẳng định cứ tăng một đơn vị precision hoặc scale thì hiệu năng giảm theo một tỷ lệ cố định. Cần đo đạc bằng benchmark phù hợp và theo dõi đầu vào thực tế trước khi đưa ra kết luận tối ưu.

## 4. Scale tăng tự nhiên qua phép toán nào?

### Phép cộng và phép trừ

Trong phép cộng/trừ chính xác thông thường, kết quả có scale bằng **scale lớn nhất của hai toán hạng** (trong trường hợp các phép toán hợp lệ và biểu diễn được):

~~~java
BigDecimal a = new BigDecimal("1.2");    // scale 1
BigDecimal b = new BigDecimal("3.4500"); // scale 4
BigDecimal sum = a.add(b);

System.out.println(sum.toPlainString()); // 4.6500
System.out.println(sum.scale());         // 4
~~~

Vì phải căn theo phần thập phân, một toán hạng có scale lớn có thể tác động tới scale kết quả. Nếu số chữ số 0 cuối không có ý nghĩa trong hợp đồng, chúng có thể là nguồn tăng kích thước biểu diễn qua nhiều bước.

### Phép nhân

Với `multiply(BigDecimal)` **không dùng MathContext**, scale kết quả bằng tổng scale của hai toán hạng:

\[
\text{result.scale} = \text{left.scale} + \text{right.scale}
\]

~~~java
BigDecimal x = new BigDecimal("1.2300"); // scale 4
BigDecimal y = new BigDecimal("2.00");   // scale 2
BigDecimal product = x.multiply(y);

System.out.println(product.toPlainString()); // 2.460000
System.out.println(product.scale());         // 6
System.out.println(product.precision());     // 7
~~~

Giá trị số học chỉ là `2.46`, nhưng kết quả giữ scale 6. Điều này có thể **cần thiết** để bảo toàn một chính sách biểu diễn; nếu không cần, số 0 tận cùng có thể làm tăng precision/scale ở các bước tiếp theo.

Ví dụ nhân `1.000000` năm lần, bắt đầu từ `BigDecimal.ONE`:

~~~java
BigDecimal value = BigDecimal.ONE;
BigDecimal factor = new BigDecimal("1.000000");

for (int i = 0; i < 5; i++) {
    value = value.multiply(factor);
}

System.out.println(value.toPlainString());
// 1.000000000000000000000000000000
System.out.println(value.precision()); // 31
System.out.println(value.scale());     // 30
~~~

**Giá trị luôn là 1**, nhưng precision của biểu diễn tăng lên 31, scale lên 30. Khi quy mô vòng lặp tăng và đầu vào có scale lớn, kích thước biểu diễn có thể trở thành vấn đề.

### Phép chia

`divide(BigDecimal)` không có chế độ làm tròn chỉ trả kết quả thập phân **chính xác**, hoặc ném `ArithmeticException` nếu kết quả thập phân không kết thúc (ví dụ `1 / 3`).

~~~java
BigDecimal one = BigDecimal.ONE;
System.out.println(one.divide(new BigDecimal("8"))); // 0.125

// one.divide(new BigDecimal("3"))
// -> ArithmeticException: decimal expansion không kết thúc
~~~

Khi chia để lấy số gần đúng có kiểm soát, cần cung cấp **scale** hoặc **MathContext** theo yêu cầu đầu ra. Không đặt precision tùy ý quá lớn “cho chắc” nếu pipeline không có lý do sử dụng các chữ số đó.

## 5. `stripTrailingZeros()`: giảm phần biểu diễn dư thừa, nhưng có điều kiện

`stripTrailingZeros()` trả một `BigDecimal` có giá trị số học tương đương, loại bỏ các thừa số 10 cuối của unscaled value và điều chỉnh scale. Đây không phải phép làm tròn.

~~~java
BigDecimal original = new BigDecimal("1.2300");
BigDecimal compact = original.stripTrailingZeros();

System.out.println(original.precision()); // 5
System.out.println(original.scale());     // 4
System.out.println(compact.precision());  // 3
System.out.println(compact.scale());      // 2
System.out.println(compact);              // 1.23
~~~

Sau chuẩn hóa, các phép toán tiếp theo có thể giữ biểu diễn ngắn hơn:

~~~java
BigDecimal rawProduct = original.multiply(new BigDecimal("2.00"));
BigDecimal compactProduct = compact.multiply(new BigDecimal("2"));

System.out.println(rawProduct.toPlainString());     // 2.460000
System.out.println(compactProduct.toPlainString()); // 2.46
~~~

**Không dùng phương thức này một cách mù quáng.** Những khác biệt sau có thể quan trọng:

- `new BigDecimal("1.2300").equals(new BigDecimal("1.23"))` là `false` vì scale khác.
- `new BigDecimal("1000").stripTrailingZeros()` thường thành biểu diễn `1E+3` với **scale âm** (`-3`), không phải `scale = 0`.
- `new BigDecimal("0.000").stripTrailingZeros()` trả giá trị zero với `scale = 0`.
- Nếu đơn vị nghiệp vụ hoặc schema yêu cầu “giữ đúng hai chữ số thập phân”, giảm scale từ 2 về 0 có thể không phù hợp.

Phép chuẩn hóa chỉ nên được áp dụng khi **khác biệt scale không mang ý nghĩa**. Dù `stripTrailingZeros` có thể giúp giảm kích thước biểu diễn, bản thân nó cũng có chi phí xử lý, nên không tự động gọi sau **mọi phép toán** nếu chưa có lý do hoặc bằng chứng đo đạc.

## 6. `setScale`: chọn scale có chủ đích, tránh phình biểu diễn

`setScale(newScale, roundingMode)` tạo biểu diễn ở scale được yêu cầu. Tăng scale thường thêm chữ số 0 vào unscaled value, không đổi giá trị số học. Giảm scale có thể làm mất chữ số khác 0, lúc đó phải có `RoundingMode` hoặc dùng `UNNECESSARY` để yêu cầu chính xác.

~~~java
BigDecimal number = new BigDecimal("123");

System.out.println(number.setScale(6).toPlainString());
// 123.000000

BigDecimal exact = new BigDecimal("123.4500")
        .setScale(2, RoundingMode.UNNECESSARY);

System.out.println(exact.toPlainString()); // 123.45
~~~

Ở ví dụ đầu, thêm 6 chữ số 0 để biểu diễn 123 chính xác dưới scale 6; nếu định dạng đích chỉ cần số nguyên, phần biểu diễn phát sinh là không cần thiết. Ở ví dụ thứ hai, giảm scale vẫn chính xác vì phần bị bỏ toàn số 0.

Khi giảm scale của `123.456` xuống 2, phải quyết định có làm tròn hay không:

~~~java
BigDecimal x = new BigDecimal("123.456");

BigDecimal rounded = x.setScale(2, RoundingMode.HALF_EVEN);
System.out.println(rounded.toPlainString()); // 123.46

// x.setScale(2, RoundingMode.UNNECESSARY)
// -> ArithmeticException vì phải bỏ chữ số khác 0
~~~

Đối với tiền tệ hoặc đo lường, không tự chọn `HALF_EVEN`, `HALF_UP` hay mode khác chỉ để giảm kích thước. Quy tắc, vị trí và thời điểm làm tròn phải đến từ đặc tả nghiệp vụ.

Một thiết kế thực tế thường lưu giá trị ở độ chính xác nội bộ đủ cho phép toán và chỉ áp dụng format/scale đầu ra **tại ranh giới được quy định**, chẳng hạn khi ghi sổ hoặc xuất hóa đơn. Tuy nhiên, với một số hệ thống, luật định yêu cầu làm tròn **từng dòng** trước khi cộng tổng; làm tròn một lần ở cuối sẽ cho kết quả khác. Phải tuân theo ranh giới nghiệp vụ thay vì coi “round cuối” là quy tắc phổ quát.

## 7. `MathContext` giới hạn precision khi bài toán cho phép làm tròn

`MathContext` chứa precision (số chữ số có nghĩa mong muốn) và `RoundingMode`. Ví dụ:

~~~java
MathContext mc = new MathContext(8, RoundingMode.HALF_EVEN);

BigDecimal third = BigDecimal.ONE.divide(new BigDecimal("3"), mc);
System.out.println(third.toPlainString()); // 0.33333333
System.out.println(third.precision());     // 8
~~~

Có thể truyền `MathContext` cho các phép toán hỗ trợ, ví dụ `add`, `multiply`, `divide` hoặc `pow`, nhằm giới hạn **precision của kết quả phép toán đó**.

Không được nhầm:

| API | Giới hạn điều gì? | Ví dụ |
| --- | --- | --- |
| `setScale(2, HALF_EVEN)` | Hai chữ số sau dấu thập phân | `123.456 → 123.46` |
| `round(new MathContext(4, HALF_EVEN))` | Bốn chữ số có nghĩa | `123.456 → 123.5` |
| `divide(divisor, 2, HALF_EVEN)` | Scale của thương bằng 2 | `1 / 3 → 0.33` |
| `divide(divisor, new MathContext(8, HALF_EVEN))` | Precision của thương tối đa 8 | `1 / 3 → 0.33333333` |

Đặc biệt, **MathContext không đồng nghĩa với giới hạn scale tuyệt đối**:

~~~java
BigDecimal tiny = new BigDecimal("1E-100000");
MathContext mc = new MathContext(8, RoundingMode.HALF_EVEN);

System.out.println(tiny.precision()); // 1
System.out.println(tiny.scale());     // 100000
System.out.println(tiny.round(mc).scale()); // 100000
~~~

Precision đã nhỏ hơn 8 nên không cần làm tròn; scale vẫn cực lớn. Một API nhận dữ liệu từ bên ngoài phải kiểm soát **cả precision và scale**, nếu có thể gặp số mũ rất lớn.

### Không “làm tròn để tối ưu” qua từng bước khi chưa chứng minh đúng

Làm tròn ở các bước trung gian có thể làm sai kết quả so với thực hiện phép toán chính xác rồi làm tròn tại ranh giới được yêu cầu.

Ví dụ:

~~~java
BigDecimal first = new BigDecimal("0.125")
        .setScale(2, RoundingMode.HALF_UP);
BigDecimal second = new BigDecimal("0.125")
        .setScale(2, RoundingMode.HALF_UP);

System.out.println(first.add(second)); // 0.26

BigDecimal exactSum = new BigDecimal("0.125")
        .add(new BigDecimal("0.125"));
System.out.println(
        exactSum.setScale(2, RoundingMode.HALF_UP)
); // 0.25
~~~

Cả hai phép tính đều làm tròn theo `HALF_UP`, nhưng **thời điểm làm tròn** khác nhau. Một phương án tối ưu chỉ hợp lệ nếu giữ đúng ngữ nghĩa đã thỏa thuận.

Khi cần tính toán nhiều bước ở precision hữu hạn, hãy thiết kế độ chính xác nội bộ, số chữ số bảo vệ (*guard digits*) nếu cần, và kiểm chứng sai số chấp nhận được. Không dùng một `MathContext` quá nhỏ xuyên suốt pipeline chỉ vì nó có thể làm giảm kích thước object.

## 8. Ví dụ Java 17+ chạy độc lập

Tạo tệp `BigDecimalPrecisionScaleDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalPrecisionScaleDemo {
    public static void main(String[] args) {
        BigDecimal original = new BigDecimal("1.2300");
        BigDecimal compact = original.stripTrailingZeros();

        System.out.printf(
                "original: %s, precision=%d, scale=%d%n",
                original.toPlainString(),
                original.precision(),
                original.scale()
        );
        System.out.printf(
                "compact: %s, precision=%d, scale=%d%n",
                compact.toPlainString(),
                compact.precision(),
                compact.scale()
        );

        BigDecimal rawProduct = original.multiply(new BigDecimal("2.00"));
        BigDecimal compactProduct = compact.multiply(new BigDecimal("2"));
        System.out.printf(
                "raw product: %s, precision=%d, scale=%d%n",
                rawProduct.toPlainString(),
                rawProduct.precision(),
                rawProduct.scale()
        );
        System.out.printf(
                "compact product: %s, precision=%d, scale=%d%n",
                compactProduct.toPlainString(),
                compactProduct.precision(),
                compactProduct.scale()
        );

        BigDecimal grown = BigDecimal.ONE;
        BigDecimal factor = new BigDecimal("1.000000");
        for (int i = 0; i < 5; i++) {
            grown = grown.multiply(factor);
        }
        System.out.printf(
                "repeated multiply: precision=%d, scale=%d%n",
                grown.precision(),
                grown.scale()
        );

        MathContext mc = new MathContext(8, RoundingMode.HALF_EVEN);
        BigDecimal third = BigDecimal.ONE.divide(new BigDecimal("3"), mc);
        System.out.println("third: " + third.toPlainString());

        BigDecimal exactScale = new BigDecimal("123.4500")
                .setScale(2, RoundingMode.UNNECESSARY);
        System.out.println("exact scale reduction: "
                + exactScale.toPlainString());

        BigDecimal exponent = new BigDecimal("1E+3");
        System.out.println("exponent scale: " + exponent.scale());
        System.out.println("exponent plain: " + exponent.toPlainString());
    }
}
~~~

Lệnh chạy trong thư mục chứa tệp:

~~~bash
javac BigDecimalPrecisionScaleDemo.java
java BigDecimalPrecisionScaleDemo
~~~

Stdout chính xác:

~~~text
original: 1.2300, precision=5, scale=4
compact: 1.23, precision=3, scale=2
raw product: 2.460000, precision=7, scale=6
compact product: 2.46, precision=3, scale=2
repeated multiply: precision=31, scale=30
third: 0.33333333
exact scale reduction: 123.45
exponent scale: -3
exponent plain: 1000
~~~

Điều có thể kết luận từ chương trình là **biểu diễn thực sự khác nhau** và scale/precision tăng theo các phép toán đã chỉ ra. Chương trình này không đo thời gian, số lần cấp phát hoặc thông lượng, nên **không phải một benchmark hiệu năng** và không chứng minh mức tăng tốc cụ thể của chuẩn hóa.

Lưu ý scale âm trong dòng cuối: `1E+3` có precision 1, scale -3 và `toPlainString()` hiển thị `1000`. Nếu lấy chuỗi plain đó tạo lại bằng `new BigDecimal("1000")`, đối tượng mới có scale 0. Điều này quan trọng nếu muốn vừa tối ưu vừa giữ round-trip biểu diễn.

## 9. Giới hạn tài nguyên khi nhận decimal từ bên ngoài

Một dịch vụ có thể nhận giá trị quá dài hoặc exponent cực lớn. Dù việc parse và lưu một số như `1E-100000` có thể khá gọn vì unscaled chỉ là 1, gọi `toPlainString()` sẽ phải tạo một chuỗi gồm rất nhiều ký tự 0.

Ví dụ **không nên chạy với exponent không được kiểm soát**:

~~~java
BigDecimal externallySupplied = new BigDecimal("1E-100000");
// Chuỗi plain sẽ rất dài dù precision chỉ bằng 1.
String huge = externallySupplied.toPlainString();
~~~

Thiết kế ranh giới:

1. Hạn chế độ dài chuỗi đầu vào trước khi parse, đồng thời không cho phép định dạng ngoài schema.
2. Parse trực tiếp từ `String` thành `BigDecimal`, không đi qua `double`.
3. Kiểm tra `precision()`, `scale()` và miền giá trị tùy hợp đồng; sử dụng phép chuyển sang `long` khi cần để lấy trị tuyệt đối scale an toàn, tránh `Math.abs(Integer.MIN_VALUE)` vẫn cho số âm.
4. Không tạo chuỗi plain, ép scale lớn, nhân lặp quá nhiều hay lưu database trước khi kiểm soát ranh giới.
5. Khi xuất JSON, biết rõ consumer cần chuỗi decimal hay numeric token, có chấp nhận ký pháp số mũ không, và có phải giữ scale hay không.

Ví dụ phương thức validation minh họa:

~~~java
static BigDecimal parseBounded(String raw) {
    if (raw == null || raw.length() > 128) {
        throw new IllegalArgumentException("Decimal input too long");
    }

    final BigDecimal parsed;
    try {
        parsed = new BigDecimal(raw);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException("Invalid decimal", ex);
    }

    if (parsed.precision() > 40
            || Math.abs((long) parsed.scale()) > 12) {
        throw new IllegalArgumentException("Decimal outside limits");
    }
    return parsed;
}
~~~

Đây là **phương thức minh họa** để đặt vào lớp Java, không phải một ứng dụng đầy đủ. Các giới hạn 128/40/12 chỉ là ví dụ; schema nghiệp vụ phải quyết định chúng. Trường hợp exponent khổng lồ, cách xử lý parse cũng có thể ném `NumberFormatException` vì scale vượt miền `int`, nên cần bắt lỗi hợp lý.

Một giới hạn `precision <= 40` không thay thế giới hạn scale, và giới hạn scale không thay thế giới hạn **giá trị số học**. Số `999999999999` có thể quá lớn so với miền nghiệp vụ dù precision và scale đều nằm trong ngưỡng.

## 10. Lưu trữ và truyền dữ liệu đúng độ chính xác

### Database `DECIMAL(p,s)` hoặc `NUMERIC(p,s)`

Schema database thường quy định độ rộng số có nghĩa và scale. Nếu cột yêu cầu `DECIMAL(18,2)`, không có lý do chung để thường xuyên mở rộng giá trị thành 100 chữ số thập phân trước khi ghi. Nhưng cũng không được tự làm tròn để vừa cột mà không có chính sách.

Ví dụ:

~~~java
BigDecimal amount = new BigDecimal("19.9900");
BigDecimal valueForColumn =
        amount.setScale(2, RoundingMode.UNNECESSARY);
System.out.println(valueForColumn.toPlainString()); // 19.99
~~~

`UNNECESSARY` chấp nhận vì chỉ bỏ số 0 thừa. Với `19.995`, nó ném `ArithmeticException`; cần quyết định có cho phép làm tròn và dùng mode nào. Không gọi `setScale(2)` mặc định nếu trường hợp cần làm tròn mà chưa nêu mode rõ ràng.

Khi dùng JDBC, truyền bằng `PreparedStatement.setBigDecimal` và đọc bằng `ResultSet.getBigDecimal`; tránh chuyển sang `Double` trung gian. Driver/database có thể áp đặt quy tắc về precision/scale, nên cần kiểm thử round-trip với schema thật.

### JSON và client JavaScript

Một API phải trao đổi các decimal lớn hoặc chính xác cao với JavaScript thường có thể chọn biểu diễn **JSON string**:

~~~json
{
  "amount": "9007199254740993.01"
}
~~~

Nếu dùng JSON number và một client gọi `JSON.parse` thông thường, giá trị có thể bị chuyển thành binary64 và mất chính xác. Chuỗi giữ nguyên ký tự và cho consumer lựa chọn thư viện decimal phù hợp. Khi bảo toàn **scale**, nên xác định có dùng `BigDecimal.toString()` (round-trip cả scale) hay một wire format gồm `unscaledValue + scale`. `toPlainString()` có thể gây mất scale âm khi parse lại; không tự biến mọi giá trị thành plain string nếu ràng buộc biểu diễn quan trọng.

### Log và hiển thị

Thường không cần hiển thị toàn bộ chữ số mà `BigDecimal` đang chứa nếu UI có hợp đồng số chữ số riêng. Hãy áp dụng format tại UI hoặc tầng presenter theo chính sách, không đổi dữ liệu nguồn chỉ để ghi log đẹp. Tránh ghi chuỗi plain cho giá trị có scale cực lớn khi không có giới hạn đầu vào; ký pháp số mũ có thể phù hợp hơn nếu bên nhận hỗ trợ.

## 11. Chọn chiến lược tối ưu theo bài toán

| Bài toán | Cách tiếp cận | Ràng buộc |
| --- | --- | --- |
| Phép nhân liên tiếp khiến scale tăng | Xem xét loại số 0 thừa ở đầu vào hoặc điểm kiểm soát bằng `stripTrailingZeros()` | Chỉ khi không cần giữ scale gốc |
| Kết quả cần đúng hai chữ số sau dấu thập phân | Dùng `setScale(2, mode)` ở ranh giới nghiệp vụ | Mode và thời điểm phải được quy định |
| Phép chia không kết thúc | Chỉ định scale hoặc `MathContext` vừa đủ | Có thể thay đổi kết quả do làm tròn |
| Payload có exponent không tin cậy | Giới hạn text length, precision, scale trước chuyển đổi tốn bộ nhớ | Chặn tài nguyên quá mức |
| Dữ liệu tính toán tài chính cần decimal chính xác | Giữ `BigDecimal` và decimal string/kiểu decimal chuẩn | Không đưa qua `double` |
| Tính toán khoa học cho phép sai số xác định | Chọn precision theo ngân sách sai số đã phân tích | Không cắt precision tùy tiện |
| Kết quả dùng để so sánh theo giá trị số học | `compareTo`, có thể chuẩn hóa nếu hợp đồng cho phép | `equals` và hash vẫn nhạy scale |
| Cần giữ nguyên biểu diễn/scale trên đường truyền | Dùng `toString()` hoặc cặp unscaled/scale | Không bỏ trailing zeros tùy tiện |

Không có một cấu hình `MathContext` hoặc một lời gọi `stripTrailingZeros` “nhanh nhất” cho mọi ứng dụng. Việc quyết định cần xem xét **độ lớn thực tế, số lượng phép toán, ngữ nghĩa scale, tần suất serialize, chi phí lưu trữ và mức sai số cho phép**.

## 12. Đo hiệu năng mà không làm sai kết luận

Một phép thử đơn lẻ dùng `System.nanoTime()` thường bị ảnh hưởng bởi JIT compilation, warmup, garbage collector và tối ưu hóa của JVM. Với một tối ưu quan trọng, nên dùng framework microbenchmark phù hợp như **JMH**, đo trên dữ liệu gần thực tế và kiểm soát kết quả không bị loại bỏ bởi tối ưu hóa.

Có thể thiết kế các nhóm thử:

- **Scale thấp vs scale cao**: cùng giá trị toán học nhưng khác số 0 tận cùng.
- **Phép nhân lặp**: giữ scale chính xác so với một pipeline đã được phép chuẩn hóa.
- **Serialize**: `toString()` so với `toPlainString()` trên dữ liệu có exponent khác nhau.
- **Giới hạn precision**: đúng precision nghiệp vụ so với precision cao hơn nhiều.
- **Allocation và GC**: số object, byte được cấp phát và độ trễ, ngoài throughput.

Một benchmark phải xác nhận hai bên thực hiện **cùng nhiệm vụ nghiệp vụ**. Chẳng hạn so sánh phép tính exact với phép tính bị cắt precision không phải so sánh công bằng nếu đầu ra yêu cầu exact. Đừng coi việc giảm chữ số là chiến thắng khi kết quả đã sai.

## 13. Lỗi phổ biến

1. **Nhầm scale với precision:** `1E-100000` có precision 1, scale 100000; kiểm tra một trong hai không bảo vệ toàn bộ.
2. **Tăng `setScale` “cho an toàn” ở mọi bước:** có thể chỉ thêm số 0, làm tăng kích thước biểu diễn mà không tăng thông tin.
3. **Chỉ dùng `MathContext` để bảo vệ scale:** một giá trị có precision nhỏ vẫn có scale rất lớn.
4. **Gọi `stripTrailingZeros` khi cần giữ scale:** kết quả có thể khác `equals` và thậm chí có scale âm.
5. **Làm tròn trung gian quá sớm:** nhiều lần làm tròn có thể đổi tổng cuối; thiết kế ranh giới rõ ràng.
6. **Chuyển qua `double` để “tăng tốc” số tiền:** có thể gây mất chính xác, không thể khôi phục khi chuyển lại sang `BigDecimal`.
7. **Dùng `toPlainString` với exponent cực lớn không tin cậy:** có thể tạo chuỗi rất dài và gây áp lực bộ nhớ.
8. **Benchmark thiếu warmup/kiểm tra đúng kết quả:** chênh lệch do môi trường hoặc bỏ công việc có thể làm kết luận sai.

## 14. Tự kiểm tra

Xét đoạn mã:

~~~java
BigDecimal a = new BigDecimal("2.5000");
BigDecimal b = new BigDecimal("3.00");
BigDecimal c = a.multiply(b);
BigDecimal d = a.stripTrailingZeros()
        .multiply(b.stripTrailingZeros());
~~~

Trả lời trước khi chạy:

1. `a.precision()` và `a.scale()` là bao nhiêu?
2. `c` in bằng `toPlainString()` là gì? Precision và scale của `c`?
3. `d` in bằng `toPlainString()` là gì? Precision và scale của `d`?
4. `c.compareTo(d)` và `c.equals(d)` cho kết quả nào?
5. Tại sao dùng `new MathContext(4, RoundingMode.HALF_EVEN)` **không** thay thế được kiểm soát scale trên mọi đầu vào?
6. Nếu cần lưu chính xác `"2.5000"` với scale 4, có nên thay nó bằng `stripTrailingZeros()` không?

**Đáp án:**

1. `a` có unscaled value `25000`, precision 5 và scale 4.
2. `c` là `7.500000`, precision 7, scale 6 (4 + 2).
3. `d` là `7.5`, precision 2, scale 1.
4. `compareTo` trả `0` vì cùng giá trị số học; `equals` trả `false` vì scale khác.
5. MathContext giới hạn **số chữ số có nghĩa** của kết quả phép toán, nhưng một số như `1E-100000` vẫn có precision nhỏ và scale cực lớn.
6. Không, nếu scale gốc là một phần yêu cầu trao đổi hoặc lưu trữ.

Cần ghi nhớ: muốn tối ưu số thập phân phải xác định **độ chính xác cần giữ, scale có ý nghĩa gì và khi nào được phép làm tròn**. Giảm biểu diễn dư thừa có thể hữu ích, nhưng tính đúng đắn, hợp đồng dữ liệu và phép đo thực tế luôn là điều kiện trước mọi tối ưu.
