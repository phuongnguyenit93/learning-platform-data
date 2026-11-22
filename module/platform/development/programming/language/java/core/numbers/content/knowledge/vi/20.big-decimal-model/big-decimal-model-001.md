# Số thập phân độ chính xác tùy ý và tính bất biến của BigDecimal trong Java

## 1. BigDecimal giải quyết vấn đề gì?

Các kiểu **float** và **double** lưu số theo hệ dấu phẩy động **nhị phân**. Không phải mọi phân số thập phân đều biểu diễn chính xác trong hệ nhị phân hữu hạn. Kết quả ví dụ quen thuộc:

~~~java
double a = 0.1;
double b = 0.2;
System.out.println(a + b); // 0.30000000000000004
~~~

Đây là hành vi đúng của kiểu double, không phải lỗi JVM. Khi ứng dụng yêu cầu tính **thập phân chính xác theo những quy tắc đã định**, Java cung cấp lớp **java.math.BigDecimal**.

~~~java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");

System.out.println(a.add(b)); // 0.3
~~~

BigDecimal có đặc tính:

- **Biểu diễn thập phân dựa trên một số nguyên tùy ý độ dài và scale**, thay vì significand nhị phân 53 bit.
- **Immutable**: sau khi tạo, đối tượng không đổi qua các phép toán. Phép tính trả về giá trị kết quả mới.
- **Các phép toán chính xác** khi có thể biểu diễn kết quả thập phân hữu hạn trong giới hạn tài nguyên và scale.
- **Có kiểm soát rounding** qua RoundingMode, MathContext, hoặc setScale.
- **Có nhiều cách so sánh** tùy cần bằng nhau về giá trị số hay cả về scale.

BigDecimal hữu ích trong tài chính, thuế, giá cả, tính tỷ lệ thập phân, nhập liệu chữ số do người dùng cung cấp và các giao thức yêu cầu giữ chữ số thập phân.

**Arbitrary precision không có nghĩa chính xác vô hạn cho mọi số thực**: phép chia 1/3 không có biểu diễn thập phân hữu hạn; BigDecimal phải làm tròn theo chính sách được cung cấp hoặc ném exception. Nó cũng không có tài nguyên vô hạn: scale là int, còn độ dài số nguyên và phép toán chịu giới hạn triển khai, CPU và bộ nhớ.

## 2. Cấu trúc: unscaled value và scale

Một BigDecimal biểu diễn giá trị toán học qua công thức:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

- **unscaledValue**: số nguyên có dấu; phương thức unscaledValue() trả BigInteger.
- **scale**: số nguyên kiểu int, có thể dương, bằng 0 hoặc âm.
- **precision**: số chữ số thập phân của unscaled value khi bỏ dấu; zero có precision bằng 1.

Ví dụ:

~~~java
BigDecimal n = new BigDecimal("123.4500");

System.out.println(n.unscaledValue()); // 1234500
System.out.println(n.scale());         // 4
System.out.println(n.precision());     // 7
System.out.println(n.toPlainString()); // 123.4500
~~~

Giá trị chính xác là 1234500 × 10^−4 = 123.4500.

| Chuỗi khởi tạo | Unscaled value | Scale | Giá trị số |
| --- | ---: | ---: | --- |
| "123.4500" | 1234500 | 4 | 123.45 |
| "12.34" | 1234 | 2 | 12.34 |
| "12" | 12 | 0 | 12 |
| "1E+3" | 1 | −3 | 1000 |
| "0.001" | 1 | 3 | 0.001 |

**Scale và precision là hai khái niệm khác nhau.** Với 123.4500, scale=4, precision=7; với 1E+3, scale=−3, precision=1. BigDecimal không giới hạn scale chỉ là số chữ số phía phải dấu thập phân; scale **âm** là hợp lệ.

### Scale âm trong thực tế

~~~java
BigDecimal x = new BigDecimal("1E+3");
System.out.println(x.scale());         // -3
System.out.println(x.toString());      // 1E+3
System.out.println(x.toPlainString()); // 1000
~~~

Mẫu số mũ thập phân này vẫn là giá trị **1000** chính xác. Nhưng khi parse chuỗi plain "1000" trở lại, đối tượng mới có thể có scale 0, khác scale −3 của giá trị ban đầu. Do đó không mặc định toPlainString duy trì đầy đủ cách biểu diễn khi round-trip.

### Độ chính xác tùy ý vẫn có giới hạn

BigDecimal có thể xử lý hàng nghìn chữ số mà double không thể lưu chính xác, nhưng:

1. Scale thuộc miền int (không thể là mọi số nguyên không giới hạn).
2. Unscaled integer cần heap và có giới hạn thực tế/triển khai.
3. Nhân, chia và nâng lũy thừa số rất lớn tiêu tốn thời gian và tài nguyên.
4. Một MathContext có precision hữu hạn **cho phép làm tròn có chủ đích**.

Nếu dữ liệu từ người dùng có thể cực dài, hãy kiểm tra số chữ số, scale, độ phức tạp phép toán và giới hạn tài nguyên trước khi xử lý.

## 3. Cách tạo BigDecimal không bị mất chữ số

Để biểu diễn một **giá trị thập phân mà bạn chủ ý nhập**, ưu tiên chuỗi thập phân:

~~~java
BigDecimal price = new BigDecimal("19.99");
BigDecimal taxRate = new BigDecimal("0.075");
BigDecimal quantity = BigDecimal.valueOf(3);
~~~

Constructor String chuyển văn bản thành BigDecimal mà không đi qua double.

### Bẫy của new BigDecimal(double)

~~~java
BigDecimal fromBinaryDouble = new BigDecimal(0.1);
BigDecimal expected = new BigDecimal("0.1");

System.out.println(fromBinaryDouble.equals(expected)); // false
~~~

Nguyên nhân: literal double **0.1** không phải chính xác 1/10 về mặt biểu diễn nhị phân. **new BigDecimal(double)** mô tả chính xác giá trị nhị phân xấp xỉ mà double chứa, dẫn đến nhiều chữ số thập phân.

**BigDecimal.valueOf(0.1)** sử dụng văn bản thập phân tương ứng với Double.toString của double:

~~~java
BigDecimal fromValueOf = BigDecimal.valueOf(0.1);
System.out.println(fromValueOf.toPlainString()); // 0.1
~~~

Phương thức valueOf(double) thường phù hợp hơn constructor double nếu phải nhận giá trị double đã có và muốn chuyển theo biểu diễn thập phân ngắn tương ứng. Nhưng **nó không chữa được sai số đã phát sinh trước đó**:

~~~java
double alreadyRounded = 0.1 + 0.2;
BigDecimal converted = BigDecimal.valueOf(alreadyRounded);
// converted = 0.30000000000000004, không trở lại 0.3.
~~~

Đối với input thập phân có yêu cầu chính xác, chuyển **String → BigDecimal ngay từ đầu**. Đối với số nguyên long, BigDecimal.valueOf(long) giữ chính xác giá trị.

### Các hằng và hàm tiện dụng

- **BigDecimal.ZERO**, **BigDecimal.ONE**, **BigDecimal.TEN** là hằng sẵn có ở Java 17.
- **BigDecimal.valueOf(2)** tạo giá trị 2.
- **BigDecimal.TWO** không phải hằng trong API Java 17.
- **BigDecimal.valueOf(long, int scale)** hữu ích khi giá trị ban đầu là một số nguyên không chia tỷ lệ đã xác định scale.

Không nhầm BigDecimal với BigInteger: BigInteger dành cho số nguyên, còn BigDecimal hỗ trợ lũy thừa của 10 để biểu diễn thập phân.

## 4. Tính bất biến: không sửa đối tượng trong phép toán

BigDecimal là **immutable object**: các phương thức add, subtract, multiply, divide, negate, abs, setScale, round và stripTrailingZeros không sửa nội dung toán hạng; chúng trả về BigDecimal kết quả.

~~~java
BigDecimal first = new BigDecimal("1.20");
BigDecimal second = new BigDecimal("2.30");

BigDecimal sum = first.add(second);

System.out.println(first.toPlainString()); // 1.20
System.out.println(sum.toPlainString());   // 3.50
~~~

**Nếu bỏ qua kết quả trả về, dữ liệu của biến không đổi:**

~~~java
BigDecimal total = BigDecimal.ZERO;
total.add(new BigDecimal("10.00"));
System.out.println(total); // 0

total = total.add(new BigDecimal("10.00"));
System.out.println(total); // 10.00
~~~

Câu lệnh gán **total = ...** chỉ cập nhật tham chiếu trong biến; nó không thay đổi đối tượng ZERO ban đầu.

### Lợi ích của tính bất biến

- Có thể tái sử dụng các hằng BigDecimal.ZERO/ONE/TEN trong nhiều nơi.
- Giảm nguy cơ một hàm khác thay đổi một đối tượng đã truyền qua tham số.
- Dễ kiểm thử vì đối tượng đầu vào giữ nguyên sau tính toán.
- Có thể chia sẻ đối tượng BigDecimal đã tạo để **đọc** trên nhiều luồng mà không có tình trạng mutate nội dung nó.

Tuy nhiên tính bất biến **không biến thao tác cập nhật một biến chia sẻ thành atomic**. Hai thread cùng đọc một biến balance, cùng tính giá trị cộng rồi cùng gán lại có thể mất một cập nhật. Phải dùng synchronization, transaction hoặc cấu trúc atomic phù hợp khi cập nhật trạng thái chung.

### Immutability là thuộc tính của đối tượng, không phải biến

~~~java
BigDecimal a = new BigDecimal("100");
BigDecimal alias = a;

a = a.add(BigDecimal.ONE);

// a chứa 101; alias vẫn trỏ tới đối tượng cũ có giá trị 100.
~~~

Nếu một DTO có setter cho trường BigDecimal, chính DTO vẫn có thể **mutable**, dù từng BigDecimal trong trường là immutable.

## 5. Phép cộng/trừ/nhân chính xác và scale của kết quả

Các phép cộng, trừ và nhân **không nhận MathContext** cố gắng tạo kết quả thập phân chính xác trong giới hạn triển khai.

~~~java
BigDecimal a = new BigDecimal("12.30");
BigDecimal b = new BigDecimal("0.045");

BigDecimal sum = a.add(b);       // 12.345
BigDecimal diff = a.subtract(b); // 12.255
~~~

Đối với cộng/trừ exact, **preferred scale** thường là max(scale của các toán hạng). Với nhân exact, preferred scale là tổng scale:

~~~java
BigDecimal a = new BigDecimal("1.20"); // scale 2
BigDecimal b = new BigDecimal("3.00"); // scale 2
BigDecimal product = a.multiply(b);   // 3.6000, scale 4
~~~

Chuỗi kết quả có thể mang số zero tận cùng. Đó không phải sai số: nó phản ánh cách biểu diễn BigDecimal và quy tắc scale. Nếu nghiệp vụ cần đúng 2 chữ số phần thập phân, hãy dùng setScale hoặc bước làm tròn đã quy định; đừng giả định multiply tự động xuất đúng hai chữ số.

## 6. Vì sao phép chia khác cộng/trừ/nhân?

Một phân số có thể không có khai triển thập phân hữu hạn. Với BigDecimal:

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal eight = new BigDecimal("8");
BigDecimal exact = one.divide(eight); // 0.125
~~~

Ngược lại:

~~~java
// BigDecimal.ONE.divide(new BigDecimal("3"));
// Ném ArithmeticException khi thực thi vì 1/3 không kết thúc.
~~~

BigDecimal.divide(BigDecimal) không có thông tin giới hạn chữ số/làm tròn thì chỉ chấp nhận thương thập phân **chính xác hữu hạn**. Nếu số chia bằng zero, cũng ném ArithmeticException.

Một phân số a/b sau khi rút gọn thành mẫu số dương b có dạng thập phân hữu hạn khi các thừa số nguyên tố của b chỉ gồm **2 và 5**. Vì vậy 1/8 và 1/40 kết thúc, còn 1/3 và 1/7 không kết thúc.

### Chia theo scale và rounding

~~~java
import java.math.RoundingMode;

BigDecimal result = BigDecimal.ONE.divide(
        new BigDecimal("3"), 4, RoundingMode.HALF_UP);
// 0.3333, scale 4
~~~

Overload này yêu cầu **4 chữ số sau dấu thập phân**, không phải 4 chữ số có nghĩa.

### Chia theo MathContext

~~~java
import java.math.MathContext;

MathContext mc = new MathContext(5, RoundingMode.HALF_UP);
BigDecimal result = BigDecimal.ONE.divide(
        new BigDecimal("3"), mc);
// 0.33333, precision 5
~~~

MathContext kiểm soát **độ chính xác tính bằng số chữ số có nghĩa** cùng RoundingMode. Sự khác nhau giữa **scale** và **precision** thể hiện rất rõ trong ví dụ này.

## 7. MathContext: precision không phải scale

- **scale**: số mũ thập phân được biểu diễn trong giá trị, có thể hiểu là số vị trí phần lẻ khi scale không âm.
- **precision**: số chữ số thập phân của unscaled value, không phải chỉ số chữ số bên phải dấu chấm.
- **MathContext**: tham số chính sách giới hạn precision của một **phép tính cụ thể**.

Ví dụ:

~~~java
BigDecimal x = new BigDecimal("12345.6789");
BigDecimal y = x.round(
        new MathContext(5, RoundingMode.HALF_EVEN));
// y = 12346, gồm 5 chữ số có nghĩa
~~~

Kết quả không có 5 chữ số sau dấu chấm; nó có **5 chữ số có nghĩa toàn số**.

**MathContext.UNLIMITED** có precision bằng 0 và yêu cầu kết quả chính xác đối với các phép toán thích hợp. Nó không khiến 1/3 đột nhiên có khai triển thập phân hữu hạn, nên phép chia không kết thúc vẫn cần rounding policy.

MathContext không phải một biến toàn cục tự động ảnh hưởng mọi phép toán. Bạn có thể dùng MathContext ở từng lời gọi:

~~~java
BigDecimal a = new BigDecimal("12345.6789");
BigDecimal b = new BigDecimal("2.5");

BigDecimal exact = a.multiply(b);
BigDecimal rounded = a.multiply(b,
        new MathContext(6, RoundingMode.HALF_EVEN));
~~~

Hai kết quả có thể khác nhau do **rounded** được làm tròn theo chính sách sau phép nhân.

## 8. setScale: điều khiển số chữ số sau dấu thập phân

~~~java
BigDecimal original = new BigDecimal("2.345");
BigDecimal newValue = original.setScale(2, RoundingMode.HALF_UP);
// original vẫn là 2.345; newValue là 2.35
~~~

setScale trả một BigDecimal kết quả, **không sửa original**. Nếu chỉ tăng scale từ 1.2 thành 1.20, việc thêm zero không thay đổi giá trị:

~~~java
BigDecimal price = new BigDecimal("1.2");
BigDecimal twoDigits = price.setScale(2, RoundingMode.UNNECESSARY);
// 1.20
~~~

Với RoundingMode.UNNECESSARY, nếu thay đổi scale bắt buộc phải làm tròn bỏ chữ số có nghĩa, phương thức sẽ ném ArithmeticException.

### Các lựa chọn RoundingMode

| Chế độ | Mô tả |
| --- | --- |
| HALF_EVEN | Tie → chữ số cuối giữ lại chẵn |
| HALF_UP | Tie → xa zero |
| HALF_DOWN | Tie → về zero |
| UP | Có phần dư thì xa zero |
| DOWN | Có phần dư thì về zero |
| CEILING | Về dương vô cùng |
| FLOOR | Về âm vô cùng |
| UNNECESSARY | Không được phép làm tròn |

Không có RoundingMode duy nhất đúng cho mọi ứng dụng. Với thuế, tính phí, tiền tệ hoặc dữ liệu đo, hãy lựa chọn theo **quy định nghiệp vụ và tiêu chuẩn áp dụng**.

**Vị trí làm tròn quan trọng**: làm tròn từng thành phần trước khi tổng hợp có thể khác làm tròn tổng cuối. BigDecimal cho công cụ thực hiện chính sách, nhưng không tự quyết định chính sách.

## 9. equals() khác compareTo() như thế nào?

Hai BigDecimal có cùng giá trị số nhưng scale khác:

~~~java
BigDecimal a = new BigDecimal("1.0");  // scale 1
BigDecimal b = new BigDecimal("1.00"); // scale 2

System.out.println(a.equals(b));   // false
System.out.println(a.compareTo(b)); // 0
~~~

- **equals()** xem cả giá trị số và scale.
- **compareTo()** so giá trị số theo thứ tự số học và có thể trả 0 dù scale khác.
- **==** so đối tượng tham chiếu, không phải phép so giá trị BigDecimal.

Khi kiểm tra hai giá trị thập phân có cùng giá trị số:

~~~java
boolean numericallyEqual = a.compareTo(b) == 0;
boolean smaller = a.compareTo(b) < 0;
boolean larger = a.compareTo(b) > 0;
~~~

### HashSet, HashMap và TreeSet

**hashCode()** của BigDecimal xét scale, nhất quán với equals. HashSet có thể chứa cả 1.0 và 1.00 như hai giá trị khác nhau theo equals. Ngược lại, TreeSet dùng natural ordering/compareTo, nên thường chỉ giữ một phần tử tương đương về giá trị số. **Natural ordering của BigDecimal không nhất quán với equals.**

Nếu dùng BigDecimal làm **khóa** hoặc đại diện cho tiền, định nghĩa chính sách rõ ràng: scale có là một phần của danh tính không, và khi nào chuẩn hóa? Tránh trộn cách dùng equals và compareTo tùy tiện khi ứng dụng yêu cầu logic nhất quán.

## 10. stripTrailingZeros và biểu diễn khoa học

~~~java
BigDecimal a = new BigDecimal("123.4500");
BigDecimal normalized = a.stripTrailingZeros();

System.out.println(normalized.toPlainString()); // 123.45
System.out.println(normalized.scale());         // 2
~~~

Không nên cho rằng stripTrailingZeros luôn tạo một số có scale không âm:

~~~java
BigDecimal large = new BigDecimal("1000").stripTrailingZeros();
System.out.println(large.toString()); // 1E+3
System.out.println(large.scale());    // -3
~~~

Đôi khi chuẩn hóa scale là phù hợp cho khóa/so sánh; nhưng với giá tiền yêu cầu đúng hai chữ số, bỏ trailing zeros có thể làm mất một phần quy ước biểu diễn. Cần định nghĩa rõ mục tiêu trước.

**Zero đặc biệt:** stripTrailingZeros có thể chuẩn hóa giá trị zero về BigDecimal.ZERO, scale 0. Điều này ảnh hưởng equals đối với một BigDecimal zero có scale khác.

## 11. toString, toPlainString và giữ biểu diễn

- **toString()**: xuất dạng chính tắc có thể dùng exponent notation.
- **toPlainString()**: xuất dạng chữ số thập phân không có ký pháp mũ.
- **toEngineeringString()**: có thể xuất dạng kỹ thuật với số mũ bội 3.

~~~java
BigDecimal n = new BigDecimal("1E+3");

System.out.println(n.toString());      // 1E+3
System.out.println(n.toPlainString()); // 1000
~~~

**toPlainString có thể không bảo toàn scale nếu chuỗi được parse lại**, như ví dụ 1E+3 scale −3 chuyển thành "1000" scale 0. Nếu hệ thống cần giữ cả giá trị lẫn scale, sử dụng biểu diễn round-trip phù hợp hoặc lưu scale riêng theo hợp đồng.

Việc format BigDecimal bằng NumberFormat dành cho hiển thị UI có thể thay dấu nhóm, dấu thập phân và giới hạn chữ số; đừng ghi lại kết quả đã format như một giá trị gốc nếu cần độ chính xác ban đầu.

## 12. Ứng dụng tiền và thuế: chính xác không đồng nghĩa không cần làm tròn

~~~java
BigDecimal unitPrice = new BigDecimal("19.99");
BigDecimal quantity = BigDecimal.valueOf(3);
BigDecimal subtotal = unitPrice.multiply(quantity); // 59.97

BigDecimal taxRate = new BigDecimal("0.075");
BigDecimal tax = subtotal.multiply(taxRate); // 4.49775
~~~

Việc tax có nhiều chữ số sau dấu thập phân không phải sai số nhị phân; đó là kết quả thập phân **chính xác của phép nhân**.

Nếu chính sách yêu cầu làm tròn ở bước này:

~~~java
BigDecimal chargedTax = tax.setScale(2, RoundingMode.HALF_UP);
// 4.50 theo quy tắc ví dụ
~~~

Không dùng RoundingMode.HALF_UP theo thói quen khi nghiệp vụ/pháp luật yêu cầu quy tắc khác. Tương tự cần xác định thứ tự làm tròn: mỗi dòng sản phẩm, từng khoản thuế hay tổng hóa đơn. Đơn vị tiền tệ và mã currency nên được lưu riêng; BigDecimal không tự biểu diễn USD/EUR/VND và không tự đổi tỷ giá.

## 13. Thread safety và mô hình lưu trữ

Immutable BigDecimal không có setter sửa unscaled value hay scale; do đó chia sẻ **đối tượng đã tạo** để đọc an toàn về nội dung đối tượng. Nhưng việc quản lý một **biến mutable chứa tham chiếu BigDecimal** trên nhiều thread vẫn đòi hỏi đồng bộ hóa thích hợp nếu có ghi.

Ví dụ một thuộc tính balance được hai request cập nhật theo quy trình đọc–cộng–gán có thể mất một cập nhật. Cần lock, transaction hoặc cấu trúc atomic phù hợp, tùy kiến trúc.

Khi truyền qua JSON, CSV, database:

1. Kiểm tra kiểu parser có giữ thập phân hay âm thầm đổi thành double.
2. Dùng **String decimal** hoặc kiểu native decimal có precision/scale phù hợp khi giao thức yêu cầu.
3. Với SQL DECIMAL/NUMERIC, kiểm tra precision/scale cột và quy tắc chuyển đổi của driver.
4. Giới hạn chiều dài chuỗi và độ lớn scale trước khi xử lý input không tin cậy.
5. Không nhầm chuỗi UI chứa grouping/currency với chuỗi chuẩn được chấp nhận bởi BigDecimal(String).

BigDecimal không giải quyết mọi vấn đề về an toàn dữ liệu, giao dịch hoặc định dạng. Nó cung cấp mô hình số thập phân để những quy tắc đó được triển khai rõ ràng.


## 14. Ví dụ Java 17+ chạy độc lập

Lưu thành tệp **BigDecimalModelDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalModelDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("123.4500");

        System.out.println("value: " + a.toPlainString());
        System.out.println("unscaled: " + a.unscaledValue());
        System.out.println("scale: " + a.scale());
        System.out.println("precision: " + a.precision());

        BigDecimal normalized = a.stripTrailingZeros();
        System.out.println("normalized: " + normalized.toPlainString()
                + " (scale=" + normalized.scale() + ")");

        BigDecimal first = new BigDecimal("1.20");
        BigDecimal second = new BigDecimal("2.30");
        BigDecimal sum = first.add(second);

        System.out.println("first stays: " + first.toPlainString());
        System.out.println("sum: " + sum.toPlainString());
        System.out.println("decimal 0.1 + 0.2: "
                + new BigDecimal("0.1").add(new BigDecimal("0.2")));
        System.out.println("valueOf(0.1): " + BigDecimal.valueOf(0.1));

        System.out.println("new BigDecimal(0.1) equals 0.1: "
                + new BigDecimal(0.1).equals(new BigDecimal("0.1")));

        BigDecimal x = new BigDecimal("1.0");
        BigDecimal y = new BigDecimal("1.00");
        System.out.println("equals 1.0 / 1.00: " + x.equals(y));
        System.out.println("compareTo 1.0 / 1.00: " + x.compareTo(y));

        System.out.println("8th: "
                + BigDecimal.ONE.divide(new BigDecimal("8")));
        try {
            BigDecimal.ONE.divide(new BigDecimal("3"));
        } catch (ArithmeticException e) {
            System.out.println("1 / 3 exact: ArithmeticException");
        }

        System.out.println("1 / 3 scale 4: "
                + BigDecimal.ONE.divide(
                        new BigDecimal("3"), 4, RoundingMode.HALF_UP));
        System.out.println("1 / 3 precision 5: "
                + BigDecimal.ONE.divide(
                        new BigDecimal("3"),
                        new MathContext(5, RoundingMode.HALF_UP)));

        BigDecimal rounded = new BigDecimal("12345.6789")
                .round(new MathContext(5, RoundingMode.HALF_EVEN));
        System.out.println("round 12345.6789 to 5 digits: "
                + rounded.toPlainString());
        System.out.println("setScale HALF_UP: "
                + new BigDecimal("2.345")
                        .setScale(2, RoundingMode.HALF_UP));

        BigDecimal scientific = new BigDecimal("1E+3");
        System.out.println("scientific scale: " + scientific.scale());
        System.out.println("scientific string: " + scientific);
        System.out.println("scientific plain: " + scientific.toPlainString());
        System.out.println("stripped 1000: "
                + new BigDecimal("1000").stripTrailingZeros());

        System.out.println("10.00 / 4: "
                + new BigDecimal("10.00").divide(new BigDecimal("4")));
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 BigDecimalModelDemo.java
java BigDecimalModelDemo
~~~

Stdout (đã đối chiếu với API BigDecimal trên JDK):

~~~text
value: 123.4500
unscaled: 1234500
scale: 4
precision: 7
normalized: 123.45 (scale=2)
first stays: 1.20
sum: 3.50
decimal 0.1 + 0.2: 0.3
valueOf(0.1): 0.1
new BigDecimal(0.1) equals 0.1: false
equals 1.0 / 1.00: false
compareTo 1.0 / 1.00: 0
8th: 0.125
1 / 3 exact: ArithmeticException
1 / 3 scale 4: 0.3333
1 / 3 precision 5: 0.33333
round 12345.6789 to 5 digits: 12346
setScale HALF_UP: 2.35
scientific scale: -3
scientific string: 1E+3
scientific plain: 1000
stripped 1000: 1E+3
10.00 / 4: 2.50
~~~

### Đọc kết quả

- unscaled=1234500, scale=4, precision=7 phản ánh chính xác mô hình số thập phân ban đầu.
- normalized có scale=2 nhưng giá trị số không đổi.
- first vẫn là 1.20 sau add; đây là tính immutable.
- 0.1+0.2 dưới dạng chuỗi BigDecimal cho 0.3 thập phân chính xác.
- new BigDecimal(0.1) không equals giá trị thập phân "0.1" vì nhận double nhị phân.
- equals phân biệt scale, compareTo so giá trị số.
- 1/8 có kết quả thập phân hữu hạn, 1/3 không thể chia exact mà không làm tròn.
- Scale 4 khác precision 5; kết quả lần lượt 0.3333 và 0.33333.
- Round với MathContext(5) chỉ giữ 5 chữ số có nghĩa nên 12345.6789 thành 12346.
- Giá trị 1000 có thể được biểu diễn qua scale âm khi chuẩn hóa.
- 10.00/4 trả 2.50 do preferred scale của phép chia chính xác.

## 15. Các lỗi phổ biến

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng new BigDecimal(0.1) để tạo chính xác 0.1 | Nhận đúng giá trị nhị phân double gần 0.1, không phải 0.1 thập phân | Dùng new BigDecimal("0.1") |
| Chuyển kết quả double đã làm tròn sang BigDecimal và nghĩ sẽ sửa sai số | Sai số trước đó vẫn tồn tại | Parse dữ liệu thập phân trước phép tính |
| Gọi total.add(amount) mà không gán | total không đổi | total = total.add(amount) |
| Dùng == để so hai BigDecimal | So tham chiếu, không so giá trị | Dùng equals/compareTo đúng mục đích |
| Dùng equals cho 1.0 và 1.00 nhưng muốn so giá trị số | false do scale khác | Dùng compareTo == 0 |
| Dùng BigDecimal làm HashMap key mà không có quy tắc scale | Hai số cùng giá trị có thể là hai khóa | Chuẩn hóa biểu diễn theo hợp đồng |
| Nghĩ scale và precision cùng nghĩa | Sai giới hạn làm tròn | Scale là số mũ thập phân; precision là số chữ số có nghĩa |
| Nghĩ scale luôn dương | 1E+3 có scale −3 | Xử lý scale âm |
| Tin stripTrailingZeros luôn in dạng plain | Có thể xuất 1E+3 | Dùng toPlainString khi cần và hiểu round-trip |
| Gọi divide cho 1/3 không có rounding | ArithmeticException | Đặt scale/RoundingMode hoặc MathContext |
| Nghĩ MathContext(5) tương đương setScale(5) | Làm tròn khác nhau | Chọn theo chữ số có nghĩa hay phần thập phân |
| Nghĩ setScale sửa original | Bỏ qua kết quả, original không đổi | Gán đối tượng trả về |
| Tự chọn HALF_UP cho mọi loại tiền và thuế | Có thể sai nghiệp vụ | Chọn RoundingMode theo chính sách thực |
| Nghĩ BigDecimal giữ vô hạn chữ số không tốn tài nguyên | Có thể tốn nhiều heap/CPU, scale int | Đặt giới hạn tài nguyên |
| Nghĩ immutable tự làm biến chia sẻ an toàn khi nhiều luồng cùng ghi | Có thể mất cập nhật | Đồng bộ hóa hoặc dùng transaction |
| Dùng NumberFormat làm mô hình lưu giá trị | Chuỗi hiển thị có thể làm tròn/phụ thuộc Locale | Lưu số thập phân theo dữ liệu gốc |

## 16. Bài tập tự kiểm tra

**Bài 1.** Với BigDecimal từ chuỗi "12.3400", unscaledValue và scale là gì?

**Đáp án:** 123400 và 4. Giá trị số = 123400 × 10^−4 = 12.3400.

**Bài 2.** new BigDecimal("1.0").equals(new BigDecimal("1.00")) trả gì? compareTo trả gì?

**Đáp án:** equals trả false vì scale 1 và 2 khác nhau; compareTo trả 0 vì giá trị số bằng nhau.

**Bài 3.** BigDecimal a = new BigDecimal("2"); a.multiply(BigDecimal.TEN); sau đó a còn bao nhiêu?

**Đáp án:** Vẫn là 2. BigDecimal immutable, phải gán kết quả nếu muốn biến tham chiếu giá trị mới.

**Bài 4.** Tại sao phép chia exact 1/3 ném ArithmeticException?

**Đáp án:** Kết quả có khai triển thập phân vô hạn, không biểu diễn bằng một BigDecimal hữu hạn khi không có rounding policy.

**Bài 5.** Muốn 1/3 được biểu diễn thành 0.3333, phải dùng overload nào?

**Đáp án:** BigDecimal.ONE.divide(new BigDecimal("3"), 4, RoundingMode.HALF_UP).

**Bài 6.** MathContext(5) giữ 5 chữ số sau dấu thập phân hay 5 chữ số có nghĩa?

**Đáp án:** 5 chữ số có nghĩa. Nếu cần 5 chữ số phần thập phân, hãy dùng setScale(5, mode) theo chính sách.

**Bài 7.** Tại sao BigDecimal từ chuỗi "1000" sau stripTrailingZeros có thể thành "1E+3"?

**Đáp án:** Trailing zeros được bỏ khỏi unscaled value, scale có thể trở thành −3; giá trị toán học vẫn là 1000.

**Bài 8.** Cần làm tròn tiền thuế ở bước nào?

**Đáp án:** Theo hợp đồng nghiệp vụ/pháp luật của hệ thống. BigDecimal chỉ hỗ trợ thực thi cách làm tròn đã được xác định.

**Bài 9.** BigDecimal.valueOf(0.1 + 0.2) có đảm bảo thành BigDecimal chính xác 0.3 không?

**Đáp án:** Không. Phép cộng double đã tạo giá trị gần 0.30000000000000004 trước khi chuyển.

**Bài 10.** Một biến balance chứa BigDecimal dùng chung nhiều thread có an toàn khi các thread đồng thời gán balance = balance.add(delta) không?

**Đáp án:** Không mặc nhiên. Đối tượng immutable, nhưng cập nhật biến có thể mất dữ liệu nếu thiếu đồng bộ/giao dịch.

## 17. Tài liệu gốc

- [BigDecimal API Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): mô hình unscaledValue/scale, immutability, preferred scales, phép toán, equals/compareTo.
- [MathContext API Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html): precision, rounding và UNLIMITED.
- [RoundingMode API Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): các chế độ làm tròn.
- [BigInteger API Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): số nguyên độ chính xác tùy ý và unscaled value.
- [Double API Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): biểu diễn double, Double.toString.
