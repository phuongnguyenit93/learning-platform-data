# BigDecimal.divide chính xác và số thập phân vô hạn tuần hoàn trong Java

## 1. Mục tiêu và hiện tượng quan trọng

**java.math.BigDecimal** lưu giá trị thập phân theo mô hình một **unscaled value** nguyên và một **scale**. Với cộng, trừ và nhân không có MathContext, ta có thể nhận kết quả thập phân **chính xác** trong giới hạn tài nguyên. Nhưng **phép chia** có một trở ngại toán học: thương của hai số thập phân hữu hạn có thể có **vô hạn chữ số thập phân tuần hoàn**.

Ví dụ:

- **1/8 = 0.125**: biểu diễn hữu hạn, BigDecimal có thể trả chính xác.
- **1/3 = 0.333333…**: thập phân vô hạn tuần hoàn; không thể lưu thành một BigDecimal hữu hạn mà vẫn giữ giá trị 1/3 chính xác.
- **1/6 = 0.166666…**: vô hạn tuần hoàn, dù 6 có chứa thừa số 2.
- **3/6 = 1/2 = 0.5**: phải **rút gọn phân số** trước khi kết luận có thập phân vô hạn hay không.

Trong Java:

~~~java
import java.math.BigDecimal;

BigDecimal exact = BigDecimal.ONE.divide(new BigDecimal("8"));
// exact = 0.125

// Lệnh dưới ném ArithmeticException khi thực thi:
// BigDecimal recurring = BigDecimal.ONE.divide(new BigDecimal("3"));
~~~

Đây là hành vi **đúng theo hợp đồng API**. BigDecimal không cố đoán số chữ số người dùng muốn giữ, cũng không tự chuyển kết quả không hữu hạn sang một số xấp xỉ khi gọi overload chia chính xác.

Bài học sẽ giải thích **khi nào chia chính xác được**, cơ chế lặp vô hạn, cách lựa chọn các overload **divide**, ý nghĩa **scale**, **precision**, **MathContext**, **RoundingMode**, các ngoại lệ và cách kiểm tra bằng Java 17+.

## 2. Ôn lại mô hình BigDecimal

Giá trị một BigDecimal có thể viết:

\[
x = u \times 10^{-s}
\]

Trong đó **u** là unscaled integer (BigInteger) và **s** là scale (int). Ví dụ:

~~~java
BigDecimal n = new BigDecimal("10.00");

System.out.println(n.unscaledValue()); // 1000
System.out.println(n.scale());         // 2
~~~

Ta có **1000 × 10^−2 = 10.00**.

BigDecimal **immutable**: phương thức divide trả về một BigDecimal mới, không thay đổi toán hạng gốc. Kết quả có thể có **scale khác** so với kết quả của một overload khác dù cùng giá trị số học.

~~~java
BigDecimal a = new BigDecimal("10.00");
BigDecimal b = new BigDecimal("4");
BigDecimal q = a.divide(b);

System.out.println(q); // 2.50
System.out.println(a); // 10.00
~~~

Không được nhầm **giá trị số**, **scale** và **độ chính xác** (*precision*):

- **Giá trị số**: 2.5.
- **Scale** trong ví dụ: 2, nên chuỗi đại diện 2.50.
- **Precision** của 2.50: 3 chữ số có nghĩa.

Một giá trị BigDecimal với scale âm vẫn hợp lệ; có thể được hiển thị bằng dạng khoa học như **1E+3**. Điều này cũng ảnh hưởng cách xác định scale của kết quả phép chia.

## 3. Thế nào là phép chia chính xác?

**Chia chính xác (exact division)** nghĩa là giá trị trả về phải bằng **đúng thương toán học** của hai số đầu vào, **không bỏ chữ số có nghĩa** do làm tròn.

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal eight = new BigDecimal("8");

BigDecimal quotient = one.divide(eight); // 0.125
~~~

Vì 0.125 kết thúc sau ba chữ số thập phân, một BigDecimal hữu hạn có thể biểu diễn nó chính xác.

Với một số như **1/3**, không tồn tại số chữ số thập phân hữu hạn nào biểu diễn chính xác thương. Dù cho phép 10, 100 hoặc một triệu chữ số, mọi biểu diễn hữu hạn dạng 0.333… đều khác 1/3 một lượng nhỏ.

Do đó:

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

// one.divide(three) -> ArithmeticException
~~~

Đừng diễn giải exception thành **overflow của kiểu số 64 bit** hay lỗi precision mặc định quá thấp. Đây là việc yêu cầu một **kết quả exact nhưng không tồn tại dưới dạng thập phân hữu hạn**.

### Hai loại ArithmeticException cần phân biệt

Phép chia BigDecimal có thể ném ArithmeticException khi:

1. **Số chia bằng 0**: ví dụ 1/0; phép toán không xác định và BigDecimal không trả infinity/NaN.
2. **Thương thập phân không kết thúc khi bắt buộc exact**: ví dụ 1/3 với divide(divisor) hoặc precision=0.

Một số overload còn có ngoại lệ khi **RoundingMode.UNNECESSARY** yêu cầu kết quả không được làm tròn nhưng scale/precision được chỉ định không đủ.

Do đó chỉ bắt ArithmeticException rồi luôn in “số vô hạn tuần hoàn” là sai: có thể nguyên nhân là chia cho zero hoặc làm tròn bị cấm.

## 4. Điều kiện toán học: mẫu số sau rút gọn chỉ có 2 và 5

Xét phân số hữu tỉ **a/b**, với b ≠ 0. Rút gọn thành **p/q**, sao cho q > 0 và gcd(|p|, q) = 1.

Phân số có biểu diễn thập phân **hữu hạn** khi và chỉ khi q có dạng:

\[
q = 2^m5^n,\qquad m,n \ge 0
\]

Tức là **mẫu số sau rút gọn không có thừa số nguyên tố nào ngoài 2 và 5**.

Lý do: một số thập phân hữu hạn d chữ số sau dấu chấm có mẫu số **10^d = 2^d × 5^d**. Sau rút gọn, mọi thừa số nguyên tố của mẫu phải đến từ 2 và 5. Ngược lại, nếu q chỉ gồm 2 và 5, có thể nhân tử và mẫu để đưa mẫu thành một lũy thừa của 10.

| Phân số | Sau rút gọn | Phân tích mẫu | Dạng thập phân |
| --- | --- | --- | --- |
| 1/2 | 1/2 | 2 | 0.5 — hữu hạn |
| 1/8 | 1/8 | 2³ | 0.125 — hữu hạn |
| 1/40 | 1/40 | 2³ × 5 | 0.025 — hữu hạn |
| 3/6 | 1/2 | 2 | 0.5 — hữu hạn |
| 1/3 | 1/3 | 3 | 0.(3) — tuần hoàn |
| 1/6 | 1/6 | 2 × 3 | 0.1(6) — tuần hoàn |
| 1/7 | 1/7 | 7 | 0.(142857) — tuần hoàn |
| 22/7 | 22/7 | 7 | 3.(142857) — tuần hoàn |

Ký hiệu **0.(3)** nghĩa là chữ số 3 lặp lại mãi; **0.1(6)** là 0.16666… và **0.(142857)** là chu kỳ sáu chữ số.

**Quan trọng:** xét **mẫu sau rút gọn**, không xét mẫu ban đầu. Trường hợp **3/6** có mẫu ban đầu chứa thừa số 3 nhưng khi rút gọn mẫu còn 2, nên phép chia exact hoàn toàn thành công.

### Mở rộng sang hai BigDecimal có scale bất kỳ

Với:

\[
x=u_x \times 10^{-s_x}, \qquad y=u_y \times 10^{-s_y}
\]

thì:

\[
\frac{x}{y} = \frac{u_x}{u_y} \times 10^{s_y-s_x}
\]

Nhân với một lũy thừa của 10 (chỉ mang các thừa số 2 và 5) **không thể khử những thừa số nguyên tố khác 2/5 trong mẫu sau rút gọn**. Vì vậy việc kiểm tra mẫu số của tỷ số hai **unscaled integer** cũng cho biết thương có khai triển thập phân hữu hạn hay không, miễn số chia khác 0.

Đây là tính chất toán học hữu ích để giải thích, không phải lúc nào cũng cần tự cài kiểm tra: nếu chỉ muốn lấy thương exact, cứ gọi **divide(divisor)** và xử lý điều kiện lỗi theo hợp đồng.

## 5. Chữ ký divide và cách chọn overload

Các overload phổ biến của BigDecimal trong Java 17:

| Cách gọi | Kết quả mong muốn | Cần lưu ý |
| --- | --- | --- |
| **a.divide(b)** | Thương chính xác, nếu biểu diễn hữu hạn | Ném ArithmeticException với thương thập phân không kết thúc |
| **a.divide(b, scale, mode)** | Thương có **scale được chỉ định** | Làm tròn theo mode nếu cần |
| **a.divide(b, mode)** | Thương có **scale bằng a.scale()** | Dễ làm tròn ngoài ý muốn nếu a.scale() nhỏ |
| **a.divide(b, mc)** | Thương làm tròn theo **precision và mode** trong MathContext | precision=0 yêu cầu exact |
| **a.divide(b, scale, intMode)** | Overload dùng hằng integer rounding cũ | Deprecated, nên dùng enum RoundingMode |

Không có một overload nào được xem là tốt nhất cho mọi bài toán. Chọn theo **yêu cầu kết quả**:

- Nếu đòi **exact** và chỉ chấp nhận số thập phân hữu hạn: **divide(b)**.
- Nếu cần **đúng N vị trí sau dấu thập phân**: **divide(b, scale, roundingMode)**.
- Nếu cần **N chữ số có nghĩa** trên nhiều bậc độ lớn: **divide(b, MathContext)**.
- Nếu ứng dụng muốn scale kết quả giống chính số bị chia: **divide(b, roundingMode)**, nhưng phải hiểu đây là một chính sách rất cụ thể.

**RoundingMode** là enum thuộc **java.math**; nên dùng **RoundingMode.HALF_UP**, **HALF_EVEN**, **DOWN**, **UNNECESSARY**, v.v. thay cho các hằng BigDecimal.ROUND_* đã deprecated.

## 6. divide(BigDecimal) — chọn khi cần exact

Ví dụ chia hữu hạn:

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal eight = new BigDecimal("8");
BigDecimal forty = new BigDecimal("40");

System.out.println(one.divide(eight)); // 0.125
System.out.println(one.divide(forty)); // 0.025
~~~

Ví dụ chia vô hạn tuần hoàn:

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

try {
    System.out.println(one.divide(three));
} catch (ArithmeticException e) {
    System.out.println("Exact decimal quotient is unavailable");
}
~~~

**Đừng viết code xử lý ngoại lệ như trên để mặc nhiên tiếp tục với một số gần đúng** khi hệ thống thực sự yêu cầu phân số chính xác. Khi bài toán phải lưu thương 1/3 mà không được phép làm tròn, cần **biểu diễn phân số** (tử và mẫu BigInteger đã rút gọn), chứ BigDecimal không thể lưu toàn bộ khai triển vô hạn.

### Preferred scale của phép chia exact

Trong đặc tả BigDecimal, **preferred scale của phép chia** là:

\[
s_{\text{preferred}} = s_{\text{dividend}} - s_{\text{divisor}}
\]

Nhưng **scale thực tế có thể lớn hơn** nếu cần thêm chữ số để biểu diễn thương chính xác.

Ví dụ:

~~~java
BigDecimal q = new BigDecimal("10.00")
        .divide(new BigDecimal("4"));

System.out.println(q);         // 2.50
System.out.println(q.scale()); // 2
~~~

Số bị chia 10.00 có scale 2; số chia 4 có scale 0; preferred scale=2 và thương 2.50 vừa đúng yêu cầu. Với **1/8**, preferred scale là 0 nhưng để biểu diễn chính xác 0.125 phải tăng đến scale 3.

Không suy rằng **divide exact luôn bỏ toàn bộ số 0 cuối** hoặc luôn trả lại đúng scale của dividend: quy tắc về preferred scale và biểu diễn exact quyết định điều đó.

## 7. divide(divisor, scale, RoundingMode) — số chữ số sau dấu thập phân

Ví dụ làm tròn thương không kết thúc:

~~~java
import java.math.RoundingMode;

BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

BigDecimal rounded = one.divide(three, 4, RoundingMode.HALF_UP);
// 0.3333
~~~

Overload này tạo kết quả **scale=4**, tức có 4 vị trí sau dấu chấm thập phân với cách hiểu thông thường của scale dương. Với hai chữ số:

~~~java
BigDecimal two = new BigDecimal("2");
BigDecimal result = two.divide(three, 2, RoundingMode.HALF_UP);
// 0.67
~~~

**Scale không phải precision.** Chia 12345/3 ở scale=2 sẽ tạo số ở hai chữ số phần lẻ (ví dụ 4115.00), còn chia với MathContext precision=3 sẽ cho ba chữ số có nghĩa gần 4.12E+3.

### Không dùng số chữ số theo thói quen

Nếu đầu ra là tiền và cần 2 chữ số sau dấu thập phân, scale=2 có thể phù hợp, **sau khi** xác định quy tắc tính tiền và thời điểm làm tròn. Nhưng nếu đầu ra là tỷ lệ đo khoa học biến thiên từ 10^−12 tới 10^12, scale=2 thường không phù hợp. Phải lựa chọn chính sách trước khi gọi API.

## 8. divide(divisor, RoundingMode) — bẫy scale ẩn

Có một overload không có tham số scale:

~~~java
BigDecimal result = BigDecimal.ONE.divide(
        new BigDecimal("8"), RoundingMode.HALF_UP);
~~~

**Kết quả là 0**, không phải 0.13. Vì **BigDecimal.ONE.scale() = 0**, overload này tạo thương với **scale=0**, rồi làm tròn 0.125 thành số nguyên gần nhất theo HALF_UP (là 0).

So sánh:

~~~java
BigDecimal a = BigDecimal.ONE;           // scale 0
BigDecimal b = new BigDecimal("1.00");   // scale 2
BigDecimal eight = new BigDecimal("8");

System.out.println(a.divide(eight, RoundingMode.HALF_UP)); // 0
System.out.println(b.divide(eight, RoundingMode.HALF_UP)); // 0.13
~~~

Hai số bị chia **1** và **1.00** có cùng giá trị số học; **chỉ khác scale**, nhưng overload này cho kết quả đã làm tròn khác nhau.

Đây là lý do khi cần một số chữ số phần thập phân rõ ràng, nên dùng **divide(divisor, scale, roundingMode)** thay vì phụ thuộc vào scale của đầu vào.

## 9. divide(divisor, MathContext) — số chữ số có nghĩa

**MathContext** mang hai thông số:

- **precision**: số chữ số có nghĩa cho kết quả.
- **roundingMode**: quy tắc làm tròn nếu phải bỏ chữ số.

~~~java
import java.math.MathContext;
import java.math.RoundingMode;

MathContext mc = new MathContext(5, RoundingMode.HALF_UP);
BigDecimal q = BigDecimal.ONE.divide(new BigDecimal("3"), mc);
// 0.33333
~~~

**MathContext(5)** ở đây giữ 5 chữ số có nghĩa, không phải 5 chữ số sau dấu chấm cho mọi thương.

Ví dụ khác:

~~~java
BigDecimal q = new BigDecimal("12345")
        .divide(new BigDecimal("3"),
                new MathContext(3, RoundingMode.HALF_UP));
// 4.12E+3 (giá trị 4120)
~~~

Kết quả chính xác của 12345/3 là 4115; chỉ giữ ba chữ số có nghĩa và HALF_UP thì làm tròn thành 4120, biểu diễn khoa học **4.12E+3**.

### MathContext.UNLIMITED không giải quyết khai triển vô hạn

~~~java
// Vẫn ném ArithmeticException:
BigDecimal.ONE.divide(
        new BigDecimal("3"), MathContext.UNLIMITED);
~~~

**MathContext.UNLIMITED** có **precision=0**, nghĩa là yêu cầu tính exact cho các phương thức tương ứng. Nó **không** có nghĩa BigDecimal được phép sinh vô hạn chữ số rồi chạy mãi. Với 1/3 không kết thúc, Java ném ArithmeticException.

Ngược lại, **MathContext.DECIMAL32**, **DECIMAL64**, **DECIMAL128** đặt precision hữu hạn theo các cấu hình có sẵn; chúng là quy tắc tính toán thập phân, không tự biến BigDecimal thành một kiểu primitive cố định.

## 10. RoundingMode: chọn quy tắc khi phải làm tròn

Các lựa chọn quan trọng:

| RoundingMode | Ý nghĩa ngắn |
| --- | --- |
| **HALF_UP** | Trung điểm làm tròn xa 0 |
| **HALF_EVEN** | Trung điểm chọn chữ số cuối được giữ là chẵn |
| **HALF_DOWN** | Trung điểm làm tròn về 0 |
| **DOWN** | Khi cần bỏ phần dư, làm tròn về 0 |
| **UP** | Nếu có phần dư, làm tròn xa 0 |
| **FLOOR** | Về âm vô cùng |
| **CEILING** | Về dương vô cùng |
| **UNNECESSARY** | Không cho phép làm tròn; nếu cần sẽ ném ArithmeticException |

Sự khác biệt giữa HALF_UP và HALF_EVEN ở **đúng trung điểm**:

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal eight = new BigDecimal("8");

BigDecimal halfEven = one.divide(
        eight, 2, RoundingMode.HALF_EVEN); // 0.12
BigDecimal halfUp = one.divide(
        eight, 2, RoundingMode.HALF_UP);   // 0.13
~~~

Thương chính xác 0.125 nằm chính giữa 0.12 và 0.13. HALF_EVEN chọn kết quả có chữ số cuối **2 (chẵn)**; HALF_UP chọn kết quả **xa 0**, tức 0.13. Với giá trị âm, quy tắc hướng về zero/xa zero phải được hiểu theo dấu, không bằng cách cắt chuỗi.

### UNNECESSARY là ràng buộc chất lượng dữ liệu

~~~java
BigDecimal exactAtScale = BigDecimal.ONE.divide(
        new BigDecimal("8"), 3, RoundingMode.UNNECESSARY);
// 0.125, không phải làm tròn

// Ném ArithmeticException vì cần làm tròn:
BigDecimal.ONE.divide(
        new BigDecimal("3"), 2, RoundingMode.UNNECESSARY);
~~~

Dùng UNNECESSARY khi nghiệp vụ **không chấp nhận mất chữ số** và muốn phát hiện trường hợp không đáp ứng được scale/precision đã định, thay vì vô tình làm tròn.

## 11. Chia cho zero, zero bị chia và các ngoại lệ

| Phép toán | Hành vi |
| --- | --- |
| **0 / 3** | Kết quả exact bằng 0 |
| **1 / 0** | ArithmeticException (division by zero) |
| **0 / 0** | ArithmeticException (undefined division) |
| **1 / 3** qua divide exact | ArithmeticException vì khai triển không kết thúc |
| **1 / 3** qua MathContext.UNLIMITED | ArithmeticException vì vẫn yêu cầu exact |
| **1 / 3** qua divide(scale=2, UNNECESSARY) | ArithmeticException vì cần làm tròn |
| **1 / 3** qua divide(scale=2, HALF_UP) | 0.33 |

BigDecimal **không có NaN và Infinity** như double. Phép chia zero không trả Double.POSITIVE_INFINITY hoặc NaN mà **ném ngoại lệ**.

Đối với mã production, đừng gom mọi ArithmeticException từ divide thành cùng thông báo. Thường nên kiểm tra **divisor.signum() == 0** trước để phân biệt đầu vào không hợp lệ. Những chính sách lỗi và làm tròn cần được thể hiện rõ với người gọi.

## 12. Ví dụ kiểm tra trước khả năng kết thúc thập phân

Khi không cần thử chia rồi bắt exception, ta có thể dựa trên tiêu chí mẫu số sau rút gọn chỉ gồm 2, 5.

Với hai BigDecimal hữu hạn:

1. Lấy **unscaledValue()** của số bị chia và số chia.
2. Với số chia bằng 0, từ chối.
3. Với tử bằng 0 và mẫu khác 0, thương là 0 và hữu hạn.
4. Rút gọn tỷ số hai unscaled integer bằng gcd.
5. Từ mẫu rút gọn, loại toàn bộ thừa số 2 và 5; nếu còn 1, thương có dạng thập phân hữu hạn.

Sự khác nhau về scale giữa hai BigDecimal chỉ tương ứng việc nhân với lũy thừa của 10, nên không đưa thêm thừa số nguyên tố ngoài 2 và 5.

Phương thức sau chỉ minh họa **tính kết thúc thập phân**, không tính thương:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;

static boolean hasTerminatingDecimal(BigDecimal a, BigDecimal b) {
    if (b.signum() == 0) {
        throw new ArithmeticException("Division by zero");
    }
    if (a.signum() == 0) {
        return true;
    }

    BigInteger numerator = a.unscaledValue().abs();
    BigInteger denominator = b.unscaledValue().abs();

    denominator = denominator.divide(denominator.gcd(numerator));

    BigInteger two = BigInteger.valueOf(2);
    BigInteger five = BigInteger.valueOf(5);

    while (denominator.mod(two).signum() == 0) {
        denominator = denominator.divide(two);
    }
    while (denominator.mod(five).signum() == 0) {
        denominator = denominator.divide(five);
    }
    return denominator.equals(BigInteger.ONE);
}
~~~

Đây là **phương thức phải đặt bên trong class** và cần import java.math.BigDecimal/BigInteger. Nó trả:

- **true** với 1/40, 3/6, 0/3.
- **false** với 1/6 hoặc 1/3.
- **ArithmeticException** với số chia 0.

**Giới hạn thực tế:** kết luận toán học về khai triển hữu hạn **không bảo đảm** phép chia thực tế luôn hoàn tất với bộ nhớ và scale hữu hạn của Java nếu đầu vào quá lớn, scale cực trị hoặc vượt giới hạn triển khai. Với ứng dụng thông thường, việc gọi **divide** trực tiếp vẫn đơn giản hơn; tự triển khai bộ phân tích mẫu chỉ cần thiết khi tiêu chí là một phần nghiệp vụ hoặc muốn giải thích lý do làm tròn.

## 13. Phân biệt làm tròn để tính và làm tròn để hiển thị

Một mẫu dữ liệu có thể có nhiều giá trị cần giữ khác nhau:

- **Số gốc**: tỷ lệ, giá, số đo hoặc số tiền chưa làm tròn.
- **Kết quả tính toán**: giá trị sau chia theo một chính sách scale/precision.
- **Chuỗi hiển thị**: qua NumberFormat theo Locale, có thể thêm dấu nhóm và làm tròn để người dùng đọc.

Ví dụ một phép tính phí cần chính sách chia và làm tròn theo nghiệp vụ:

~~~java
BigDecimal total = new BigDecimal("10.00");
BigDecimal people = new BigDecimal("3");

BigDecimal perPerson = total.divide(
        people, 2, RoundingMode.HALF_UP);
// 3.33
~~~

**3.33 × 3 = 9.99**, không bằng 10.00; còn dư 0.01. Đó là hệ quả của chia không kết thúc và làm tròn theo đơn vị nhỏ nhất, không phải lỗi BigDecimal. Nếu cần **phân bổ chính xác 10.00**, phải có quy tắc phân phối số dư (ví dụ một người nhận thêm 0.01) và kiểm tra tổng cuối cùng.

Không tự động đổi sang double để tránh exception hoặc để dễ hiển thị. Double có thể mang thêm sai số nhị phân và không tự giải quyết quy tắc phân bổ/làm tròn.

## 14. Phân số chính xác nếu không được phép làm tròn

Nếu yêu cầu toán học là **giữ đúng 1/3**, một BigDecimal hữu hạn không đủ. Có thể lưu tử và mẫu bằng BigInteger, rút gọn theo gcd:

~~~java
import java.math.BigInteger;

BigInteger numerator = BigInteger.ONE;
BigInteger denominator = BigInteger.valueOf(3);

BigInteger gcd = numerator.gcd(denominator);
numerator = numerator.divide(gcd);
denominator = denominator.divide(gcd);
// Giá trị hữu tỉ giữ dưới dạng 1/3
~~~

Đoạn này minh họa cách biểu diễn hai thành phần, **không định nghĩa một lớp phân số đầy đủ**. Với hệ thống thực, phải chuẩn hóa dấu mẫu (thường dương), từ chối mẫu 0, xử lý toán học phân số và giới hạn tài nguyên.

Chỉ khi cần xuất thập phân cho người xem hoặc gửi một API yêu cầu decimal hữu hạn mới áp dụng chính sách làm tròn rõ ràng. Nhờ vậy, **độ chính xác của mô hình** không bị mất sớm.

## 15. Checklist lựa chọn overload

Hãy trả lời các câu hỏi theo thứ tự:

1. **Có bắt buộc exact không?** Nếu có, divide(divisor); nếu thương không hữu hạn thì từ chối hoặc chọn biểu diễn phân số.
2. **Kết quả có độ rộng cố định theo phần thập phân không?** Nếu có, divide(divisor, scale, mode).
3. **Kết quả chỉ yêu cầu N chữ số có nghĩa?** Nếu có, divide(divisor, MathContext).
4. **Bạn có chủ đích giữ scale của dividend không?** Chỉ khi có mới chọn divide(divisor, mode).
5. **Có chính sách làm tròn nào được chấp nhận?** Xác định HALF_EVEN, HALF_UP hoặc mode khác từ hợp đồng.
6. **Chia zero hoặc số quá lớn thì sao?** Kiểm tra miền dữ liệu, scale, precision, giới hạn tài nguyên và cách báo lỗi.
7. **Có cần giữ phân số exact qua nhiều phép toán không?** Nếu có, dùng mô hình tử/mẫu, tránh làm tròn trung gian.

Sự lựa chọn tốt nhất là **phù hợp hợp đồng dữ liệu**, không phải API có chữ ký ngắn nhất.

## 16. Những sai lầm dễ mắc

| Sai lầm | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Gọi BigDecimal.ONE.divide(3) rồi nghĩ Java tự cho 0.333... | ArithmeticException | Chọn rounding hoặc biểu diễn phân số |
| Coi ArithmeticException luôn là chia cho zero | Bỏ qua lỗi khai triển không kết thúc/rounding forbidden | Phân loại điều kiện lỗi |
| Nghĩ BigDecimal có thể lưu vô hạn chữ số | Bản thân BigDecimal là biểu diễn hữu hạn | Chọn biểu diễn hữu tỉ khi cần exact 1/3 |
| Xét mẫu 6 để kết luận 3/6 tuần hoàn | Chưa rút gọn | Rút gọn bằng gcd trước |
| Cho rằng mẫu có cả 2 và 5 thì luôn hữu hạn | Mẫu có thể còn 3 hoặc 7 | Mẫu rút gọn chỉ được có thừa số 2,5 |
| Dùng divide(divisor, HALF_UP) nhưng tưởng tự giữ 2 chữ số | Overload giữ scale của dividend | Dùng divide(divisor,2,HALF_UP) |
| Nhầm MathContext(5) là 5 chữ số thập phân | Precision là 5 chữ số có nghĩa | Dùng scale cho phần lẻ |
| Chọn MathContext.UNLIMITED để tránh lỗi 1/3 | Vẫn yêu cầu exact và ném exception | Precision hữu hạn + rounding |
| Dùng RoundingMode.UNNECESSARY khi thương không vừa scale | ArithmeticException | Tăng scale hoặc cho rounding nếu hợp đồng cho phép |
| Dùng double làm trung gian trước khi chia BigDecimal | Có thể mất độ chính xác thập phân đầu vào | Khởi tạo từ String hoặc giá trị nguyên |
| Cứ làm tròn từng bước rồi cho rằng tổng bằng số gốc | Có thể lệch do số dư | Thiết kế quy tắc phân bổ số dư |
| Dùng NumberFormat làm bước tính chia | Chuỗi UI không phải số gốc | Tính bằng BigDecimal, format riêng |
| Bỏ qua độ lớn input hoặc precision | Tốn CPU/heap, có thể vượt giới hạn triển khai | Ràng buộc đầu vào và tài nguyên |


## 17. Chương trình Java 17+ chạy độc lập

Tạo tệp **DecimalDivideDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.MathContext;
import java.math.RoundingMode;

public class DecimalDivideDemo {
    static boolean hasTerminatingDecimal(BigDecimal a, BigDecimal b) {
        if (b.signum() == 0) {
            throw new ArithmeticException("Division by zero");
        }
        if (a.signum() == 0) {
            return true;
        }

        BigInteger numerator = a.unscaledValue().abs();
        BigInteger denominator = b.unscaledValue().abs();
        denominator = denominator.divide(denominator.gcd(numerator));

        BigInteger two = BigInteger.valueOf(2);
        BigInteger five = BigInteger.valueOf(5);

        while (denominator.mod(two).signum() == 0) {
            denominator = denominator.divide(two);
        }
        while (denominator.mod(five).signum() == 0) {
            denominator = denominator.divide(five);
        }
        return denominator.equals(BigInteger.ONE);
    }

    public static void main(String[] args) {
        BigDecimal one = BigDecimal.ONE;
        BigDecimal three = new BigDecimal("3");
        BigDecimal eight = new BigDecimal("8");

        System.out.println("1 / 8 exact: " + one.divide(eight));
        System.out.println("1 / 40 exact: "
                + one.divide(new BigDecimal("40")));
        System.out.println("10.00 / 4 exact: "
                + new BigDecimal("10.00")
                        .divide(new BigDecimal("4")));

        try {
            one.divide(three);
        } catch (ArithmeticException ex) {
            System.out.println("1 / 3 exact: ArithmeticException");
        }

        try {
            one.divide(three, MathContext.UNLIMITED);
        } catch (ArithmeticException ex) {
            System.out.println("1 / 3 UNLIMITED: ArithmeticException");
        }

        System.out.println("1 / 3 4dp HALF_UP: "
                + one.divide(three, 4, RoundingMode.HALF_UP));
        System.out.println("2 / 3 2dp HALF_UP: "
                + new BigDecimal("2").divide(
                        three, 2, RoundingMode.HALF_UP));
        System.out.println("1 / 3 5sig HALF_UP: "
                + one.divide(three,
                        new MathContext(5, RoundingMode.HALF_UP)));
        System.out.println("12345 / 3 3sig HALF_UP: "
                + new BigDecimal("12345").divide(
                        three, new MathContext(3, RoundingMode.HALF_UP)));

        System.out.println("1 / 8 2dp HALF_EVEN: "
                + one.divide(eight, 2, RoundingMode.HALF_EVEN));
        System.out.println("1 / 8 2dp HALF_UP: "
                + one.divide(eight, 2, RoundingMode.HALF_UP));

        System.out.println("1 / 8 HALF_UP no scale: "
                + one.divide(eight, RoundingMode.HALF_UP));
        System.out.println("1.00 / 8 HALF_UP no scale: "
                + new BigDecimal("1.00")
                        .divide(eight, RoundingMode.HALF_UP));

        try {
            one.divide(three, 2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            System.out.println("1 / 3 UNNECESSARY: ArithmeticException");
        }

        try {
            one.divide(BigDecimal.ZERO);
        } catch (ArithmeticException ex) {
            System.out.println("1 / 0: ArithmeticException");
        }

        System.out.println("0 / 3 exact: "
                + BigDecimal.ZERO.divide(three));

        System.out.println("1/40 terminates: "
                + hasTerminatingDecimal(one, new BigDecimal("40")));
        System.out.println("1/6 terminates: "
                + hasTerminatingDecimal(one, new BigDecimal("6")));
        System.out.println("3/6 terminates: "
                + hasTerminatingDecimal(three, new BigDecimal("6")));

        System.out.println("1/3 rounded input unchanged: " + one);
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac --release 17 DecimalDivideDemo.java
java DecimalDivideDemo
~~~

Stdout đã đối chiếu bằng Java:

~~~text
1 / 8 exact: 0.125
1 / 40 exact: 0.025
10.00 / 4 exact: 2.50
1 / 3 exact: ArithmeticException
1 / 3 UNLIMITED: ArithmeticException
1 / 3 4dp HALF_UP: 0.3333
2 / 3 2dp HALF_UP: 0.67
1 / 3 5sig HALF_UP: 0.33333
12345 / 3 3sig HALF_UP: 4.12E+3
1 / 8 2dp HALF_EVEN: 0.12
1 / 8 2dp HALF_UP: 0.13
1 / 8 HALF_UP no scale: 0
1.00 / 8 HALF_UP no scale: 0.13
1 / 3 UNNECESSARY: ArithmeticException
1 / 0: ArithmeticException
0 / 3 exact: 0
1/40 terminates: true
1/6 terminates: false
3/6 terminates: true
1/3 rounded input unchanged: 1
~~~

### Diễn giải kết quả

1. **1/8 và 1/40** có thương thập phân hữu hạn, nên divide exact trả đúng 0.125 và 0.025.
2. **10.00/4 = 2.50** thể hiện BigDecimal giữ scale theo quy tắc preferred scale thay vì tự bỏ zero tận cùng.
3. **1/3** không có thập phân hữu hạn, nên cả divide exact và MathContext.UNLIMITED đều ném ArithmeticException.
4. **4dp** chỉ 4 chữ số phần thập phân: 0.3333. **5sig** chỉ 5 chữ số có nghĩa: 0.33333.
5. **12345/3** chính xác là 4115, còn MathContext(3, HALF_UP) làm tròn còn 4120 và hiển thị 4.12E+3.
6. **HALF_EVEN và HALF_UP** ở 0.125 với scale=2 cho kết quả 0.12 và 0.13, dù đầu vào giống nhau.
7. **divide(divisor, RoundingMode)** không truyền scale dùng **scale của dividend**: từ 1 (scale 0) cho kết quả 0, nhưng 1.00 (scale 2) cho 0.13.
8. **UNNECESSARY** từ chối trường hợp cần bỏ chữ số; phép chia cho zero được báo lỗi riêng.
9. Hàm kiểm tra thập phân hữu hạn trả true với 1/40, false với 1/6 và true với **3/6 sau rút gọn**.
10. Toán hạng BigDecimal.ONE không bị sửa bởi những phép chia và rounding; đây là tính bất biến.

## 18. Câu hỏi và bài tập

**Bài 1.** Khi gọi BigDecimal.ONE.divide(new BigDecimal("3")), tại sao nhận ArithmeticException?

*Đáp án:* Thương 1/3 là thập phân vô hạn tuần hoàn, không thể biểu diễn chính xác bằng BigDecimal hữu hạn và overload này không có chính sách làm tròn.

**Bài 2.** Vì sao 3/6 có thể chia chính xác nhưng 1/6 thì không?

*Đáp án:* Rút gọn 3/6 thành 1/2, mẫu chỉ có thừa số 2. Mẫu 6 của 1/6 chứa 3 nên khai triển thập phân không kết thúc.

**Bài 3.** Mẫu số rút gọn 2³ × 5² có thể tạo thập phân hữu hạn không?

*Đáp án:* Có. Mẫu chỉ chứa 2 và 5, có thể nhân để thành lũy thừa của 10.

**Bài 4.** Tại sao MathContext.UNLIMITED vẫn ném exception khi chia 1/3?

*Đáp án:* Precision=0 có nghĩa yêu cầu tính exact, không phải tạo một chuỗi vô hạn chữ số.

**Bài 5.** Muốn 2/3 thành 0.67 với hai chữ số sau dấu thập phân, gọi phương thức nào?

*Đáp án:* **new BigDecimal("2").divide(new BigDecimal("3"), 2, RoundingMode.HALF_UP)**.

**Bài 6.** Muốn chia một số lớn chỉ giữ 4 chữ số có nghĩa, nên dùng scale hay MathContext?

*Đáp án:* **MathContext(4, mode)**. Scale là số vị trí phần thập phân, không phải tổng số chữ số có nghĩa.

**Bài 7.** Tại sao BigDecimal.ONE.divide(new BigDecimal("8"), RoundingMode.HALF_UP) cho 0?

*Đáp án:* Overload này giữ scale của dividend là 0, nên 0.125 được làm tròn thành số nguyên 0.

**Bài 8.** Tại 1/8, làm tròn còn hai chữ số sau dấu với HALF_EVEN và HALF_UP khác nhau thế nào?

*Đáp án:* 0.125 nằm giữa 0.12 và 0.13; HALF_EVEN chọn 0.12, HALF_UP chọn 0.13.

**Bài 9.** Cần giữ đúng phân số 1/3 cho nhiều phép toán trước khi xuất kết quả. Nên làm gì?

*Đáp án:* Biểu diễn dưới dạng tử/mẫu số nguyên (ví dụ BigInteger) đã chuẩn hóa, không làm tròn sang BigDecimal từ đầu.

**Bài 10.** Chia tổng 10.00 đều cho ba người, mỗi người giữ 2 chữ số tiền, vì sao 3.33×3 không bằng 10.00?

*Đáp án:* Do làm tròn thương không kết thúc. Nếu cần bảo toàn tổng, phải xác định chính sách phân bổ phần dư 0.01.

**Bài 11.** Có thể dùng BigDecimal.divide cho số chia 0 và mong nhận Infinity không?

*Đáp án:* Không. BigDecimal không có Infinity/NaN; phép chia zero ném ArithmeticException.

## 19. Tài liệu tham khảo chính thức

- [BigDecimal Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): các overload divide, preferred scale, exact arithmetic, ArithmeticException và biểu diễn thập phân.
- [MathContext Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html): precision, roundingMode và UNLIMITED.
- [RoundingMode Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): các quy tắc làm tròn số dương và âm.
- [BigInteger Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): gcd và biểu diễn tử/mẫu của phân số chính xác.
