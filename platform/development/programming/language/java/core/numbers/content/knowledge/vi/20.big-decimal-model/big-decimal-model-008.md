# Giữ dấu 0 cuối trong biểu diễn có ý nghĩa với BigDecimal (Java)

## 1. Vì sao “1.20” không đơn giản là “1.2”?

Trong toán học, **1,20 và 1,2 bằng nhau về giá trị**. Nhưng trong nhiều hệ thống, chuỗi thập phân `"1.20"` còn mang một thông tin khác: người nhập đã cung cấp giá trị tới **hai chữ số sau dấu thập phân**, thay vì một. Điều này có thể có ý nghĩa đối với tiền tệ, giá niêm yết, dữ liệu đo đạc, file báo cáo hoặc yêu cầu lưu trữ.

`java.math.BigDecimal` lưu không chỉ giá trị số học mà còn một thành phần **scale**. Nhờ đó:

~~~java
BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("1.2");

System.out.println(a);         // 1.20
System.out.println(b);         // 1.2
System.out.println(a.scale()); // 2
System.out.println(b.scale()); // 1
~~~

Đây là đoạn mã đặt trong một phương thức và cần `import java.math.BigDecimal;`. Cả hai đại diện cùng một số toán học nhưng giữ **hai biểu diễn thập phân khác nhau**.

Mục tiêu của bài:

- Hiểu `unscaledValue`, `scale` và `precision` của `BigDecimal`.
- Biết cách **giữ số 0 cuối** khi đọc, tính toán, lưu trữ và xuất chuỗi.
- Không dùng `stripTrailingZeros()` khi các chữ số 0 cuối có ý nghĩa.
- Phân biệt `equals()` với `compareTo()` và tác động lên `HashMap`/`TreeSet`.
- Hiểu `setScale()` khi thêm/bớt chữ số 0, quy tắc làm tròn và các thay đổi biểu diễn do phép toán.
- Tránh làm mất thông tin khi đi qua `double`, JSON, JDBC hoặc bộ định dạng.
- Nhận biết giới hạn: scale có thể biểu thị **độ phân giải đã ghi**, nhưng không tự chứng minh độ chính xác vật lý của phép đo.

Các ví dụ dùng **Java 17+**, ưu tiên xây dựng BigDecimal từ **chuỗi thập phân gốc**.

## 2. Mô hình unscaled value × 10^(-scale)

Giá trị toán học của một `BigDecimal` được biểu diễn bởi:

\[
\text{value}=\text{unscaledValue}\times10^{-\text{scale}}
\]

- **Unscaled value** là một số nguyên `BigInteger` chứa các chữ số có nghĩa trong biểu diễn hiện tại.
- **Scale** là số chữ số bên phải dấu thập phân, khi scale dương; scale cũng có thể là 0 hoặc âm.
- **Precision** là số chữ số của giá trị unscaled (theo định nghĩa API), với quy tắc đặc biệt khi giá trị bằng 0.

| Chuỗi tạo BigDecimal | Unscaled value | Scale | Precision | Giá trị toán học |
| --- | ---: | ---: | ---: | --- |
| `"1.2"` | 12 | 1 | 2 | 1,2 |
| `"1.20"` | 120 | 2 | 3 | 1,2 |
| `"1.200"` | 1200 | 3 | 4 | 1,2 |
| `"0.00"` | 0 | 2 | 1 | 0 |
| `"1200"` | 1200 | 0 | 4 | 1200 |
| `"1E+3"` | 1 | −3 | 1 | 1000 |

Ví dụ kiểm tra:

~~~java
BigDecimal amount = new BigDecimal("1.20");

System.out.println(amount.unscaledValue()); // 120
System.out.println(amount.scale());         // 2
System.out.println(amount.precision());     // 3
~~~

**Điểm cốt lõi:** các số 0 cuối của `1.20` không chỉ là chi tiết của `println`. Chúng gắn với `scale=2` và `unscaledValue=120` trong mô hình dữ liệu của đối tượng.

Không nhầm `precision` với `scale`. `1.20` có precision 3, scale 2; `1200` có precision 4, scale 0. Một giá trị có thể có nhiều biểu diễn hợp lệ với precision và scale khác nhau.

## 3. “Có ý nghĩa” là yêu cầu của hợp đồng dữ liệu

Có ít nhất ba tình huống cần phân biệt.

### 3.1. Số tiền có hai chữ số thập phân

Một hóa đơn biểu diễn `"12.30"` có thể bắt buộc thể hiện **hai chữ số sau dấu chấm** vì đơn vị tiền tệ và tiêu chuẩn xuất chứng từ. Dù giá trị số của `12.30` bằng `12.3`, định dạng không hoàn toàn có thể thay thế trong bản in hoặc API.

### 3.2. Số đo được ghi với độ phân giải

Một phép đo chiều dài `"1.20 m"` có thể được báo cáo đến 0,01 m. Việc biến thành `"1.2 m"` có thể làm mất **thông tin về mức chi tiết đã được ghi**.

Tuy nhiên, một chuỗi có hai chữ số thập phân **không tự chứng minh cảm biến chính xác ±0,01 m**. Nếu cần bất định đo lường, độ chính xác thiết bị, sai số chuẩn hoặc đơn vị, phải lưu chúng bằng metadata/hợp đồng riêng.

### 3.3. Giá trị thuần toán học

Trong một thuật toán chỉ cần so sánh giá trị số và không quan tâm biểu diễn, `1.20` và `1.2` có thể được coi là tương đương. Lúc đó loại số 0 cuối có thể chấp nhận được, thậm chí có ích khi chuẩn hóa dữ liệu.

**Nguyên tắc thiết kế:** xác định hệ thống cần **giữ đúng số gốc**, **giữ một scale chuẩn**, hay chỉ **giữ giá trị số học**. Ba mục tiêu này không hoàn toàn giống nhau.

## 4. Tạo BigDecimal từ String để bảo toàn biểu diễn thập phân

Cách đáng tin khi nhận văn bản decimal:

~~~java
BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("0.000");
BigDecimal c = new BigDecimal("125.00");

System.out.println(a.toPlainString()); // 1.20
System.out.println(b.toPlainString()); // 0.000
System.out.println(c.toPlainString()); // 125.00
~~~

`BigDecimal(String)` phân tích văn bản decimal và thiết lập unscaled value cùng scale theo biểu diễn số được cung cấp. Nó không mặc định gọi `stripTrailingZeros`.

Khi input là một trường decimal có định dạng cố định, nên lưu **chuỗi ban đầu**, hoặc ít nhất là `BigDecimal` cùng hợp đồng scale cụ thể, tùy yêu cầu tái tạo. Nếu cần giữ nguyên mọi ký tự như dấu cộng đầu, chữ `E` hoa/thường hoặc số 0 ở đầu phần nguyên, **chỉ BigDecimal không đủ**: nó lưu cấu trúc số, không lưu toàn bộ văn bản gốc.

### Không đi qua double để “giữ 1.20”

~~~java
BigDecimal text = new BigDecimal("1.20");
BigDecimal fromDouble = BigDecimal.valueOf(1.20);

System.out.println(text);       // 1.20
System.out.println(fromDouble); // 1.2
~~~

Lý do: literal `1.20` đã được Java coi là một giá trị `double`; cách viết `1.20` và `1.2` không được giữ như metadata văn bản. `BigDecimal.valueOf(double)` lấy biểu diễn decimal từ `Double.toString(double)`, nên không thể phục hồi số 0 cuối đã mất.

`new BigDecimal(1.20)` còn mang một vấn đề khác: constructor từ `double` diễn giải chính xác **giá trị nhị phân đã xấp xỉ**, có thể dẫn đến phần thập phân dài. Khi cần giữ dữ liệu decimal đã nhập, hãy đọc trực tiếp từ chuỗi hoặc kiểu decimal chuyên dụng.

## 5. equals và compareTo: bằng số chưa chắc bằng đối tượng

`BigDecimal` có hai cách so sánh quan trọng.

**`compareTo()`** so sánh **giá trị số học**:

~~~java
BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("1.2");

System.out.println(a.compareTo(b)); // 0
~~~

**`equals()`** đòi hỏi cả **giá trị số** và **scale** tương thích (cùng biểu diễn số theo định nghĩa của BigDecimal):

~~~java
System.out.println(a.equals(b)); // false
~~~

Bởi vậy, nếu nghiệp vụ chỉ muốn biết “cùng số tiền” hoặc “cùng giá trị” thì dùng `compareTo(b) == 0`. Nếu muốn nhận biết “cùng số và cùng scale” thì `equals()` đúng ý nghĩa hơn.

### HashCode và collection

`hashCode()` phải nhất quán với `equals()`, nhưng **không nhất thiết** nhất quán với `compareTo() == 0`. Vì vậy:

~~~java
java.util.Map<BigDecimal, String> map = new java.util.HashMap<>();
map.put(new BigDecimal("1.20"), "two decimal places");

System.out.println(map.get(new BigDecimal("1.20"))); // two decimal places
System.out.println(map.get(new BigDecimal("1.2")));  // null
~~~

Trong `HashMap`, hai khóa có cùng giá trị toán học nhưng khác scale **không được coi là cùng khóa** nếu `equals()` trả false.

Ngược lại, `TreeSet<BigDecimal>` dùng thứ tự tự nhiên dựa trên `compareTo()`, vì vậy có thể coi hai biểu diễn số là cùng một phần tử:

~~~java
java.util.Set<BigDecimal> sorted =
        new java.util.TreeSet<>();
sorted.add(new BigDecimal("1.20"));
sorted.add(new BigDecimal("1.2"));

System.out.println(sorted.size()); // 1
~~~

Đây là một điểm khác biệt thật sự giữa collection dựa vào `equals/hashCode` và collection có thứ tự. Nếu scale mang ý nghĩa nghiệp vụ, hãy cân nhắc rất kỹ trước khi dùng `TreeSet` như kho duy nhất của các bản ghi cần giữ biểu diễn riêng.

## 6. setScale: giữ hoặc áp đặt số chữ số sau dấu thập phân

`setScale(newScale)` trả về một `BigDecimal` có scale mới; **không thay đổi đối tượng nguồn**.

~~~java
BigDecimal original = new BigDecimal("1.2");
BigDecimal fixed = original.setScale(2);

System.out.println(original); // 1.2
System.out.println(fixed);    // 1.20
~~~

Vì chỉ thêm số 0, giá trị toán học không đổi và không cần làm tròn.

Tương tự:

~~~java
BigDecimal twoPlaces = new BigDecimal("1.20");
BigDecimal threePlaces = twoPlaces.setScale(3);

System.out.println(threePlaces); // 1.200
~~~

Khi **giảm scale**, có thể phải bỏ chữ số khác 0. Nếu gọi `setScale(int)` không chỉ định rounding mode và thao tác không thể chính xác, Java ném `ArithmeticException`:

~~~java
BigDecimal value = new BigDecimal("1.234");

// value.setScale(2); // ArithmeticException: cần loại chữ số khác 0.
~~~

Nếu quy định nghiệp vụ cho phép làm tròn, hãy chỉ rõ chế độ:

~~~java
BigDecimal rounded = value.setScale(2, RoundingMode.HALF_UP);
System.out.println(rounded); // 1.23
~~~

Đoạn này cần import `java.math.RoundingMode`. `setScale` không biến kết quả thành số kiểu `double`; kết quả vẫn là BigDecimal có thể giữ đúng số 0 cuối theo scale mong muốn.

## 7. Làm tròn không đồng nghĩa chỉ thêm số 0

Cần tách hai trường hợp:

| Thao tác | Giá trị trước | Scale đích | Kết quả | Có làm tròn giá trị? |
| --- | --- | ---: | --- | --- |
| Tăng scale | `1.2` | 2 | `1.20` | Không |
| Tăng scale | `1.20` | 3 | `1.200` | Không |
| Giảm scale khi chữ số bỏ đều là 0 | `1.200` | 2 | `1.20` | Không |
| Giảm scale khi phải bỏ chữ số khác 0 | `1.235` | 2 với `HALF_UP` | `1.24` | Có |
| Giảm scale, yêu cầu chính xác | `1.235` | 2 với `UNNECESSARY` | Exception | Không chấp nhận làm tròn |

~~~java
BigDecimal a = new BigDecimal("1.200");
BigDecimal b = new BigDecimal("1.235");

System.out.println(a.setScale(2, RoundingMode.UNNECESSARY)); // 1.20
System.out.println(b.setScale(2, RoundingMode.HALF_UP));     // 1.24
~~~

**Khuyến nghị:** nếu yêu cầu đầu vào không được có hơn hai chữ số thập phân có nghĩa, dùng `setScale(2, RoundingMode.UNNECESSARY)` hoặc kiểm tra scale/grammar theo quy định. Nếu số chữ số gốc (kể cả zero) phải được giữ, không dùng `setScale(2)` một cách vô điều kiện vì như vậy có thể xóa thông tin độ phân giải.

Ví dụ, `1.200` xuống `1.20` không đổi giá trị toán học nhưng **đã thay đổi biểu diễn gốc**.

## 8. stripTrailingZeros: hữu ích khi chuẩn hóa, không phù hợp nếu phải giữ biểu diễn

`stripTrailingZeros()` tạo một biểu diễn tương đương về giá trị nhưng bỏ những số 0 cuối dư thừa trong hệ thập phân.

~~~java
BigDecimal original = new BigDecimal("1.2000");
BigDecimal stripped = original.stripTrailingZeros();

System.out.println(original); // 1.2000
System.out.println(stripped); // 1.2
~~~

Kết quả có cùng giá trị số học, nhưng scale mới có thể nhỏ hơn. Nếu các số 0 cuối thể hiện chuẩn báo cáo, **không gọi phương thức này trước khi lưu hoặc xuất dữ liệu**.

### Trường hợp 1000.00: có thể chuyển sang ký hiệu khoa học

~~~java
BigDecimal original = new BigDecimal("1000.00");
BigDecimal stripped = original.stripTrailingZeros();

System.out.println(original);                 // 1000.00
System.out.println(stripped);                 // 1E+3
System.out.println(stripped.scale());         // -3
System.out.println(stripped.toPlainString()); // 1000
~~~

Đây là kết quả quan trọng: bỏ số 0 cuối **không nhất thiết** tạo ra một chuỗi giống văn bản ban đầu nhưng ngắn hơn. `BigDecimal` cho phép scale âm, và `toString()` có thể dùng ký hiệu mũ.

### Zero cũng có thể mất scale

~~~java
BigDecimal measuredZero = new BigDecimal("0.000");
BigDecimal strippedZero = measuredZero.stripTrailingZeros();

System.out.println(measuredZero);       // 0.000
System.out.println(strippedZero);       // 0
System.out.println(strippedZero.scale()); // 0
~~~

Đối với một phép đo được ghi ở ba chữ số thập phân, `0.000` và `0` cùng giá trị toán học nhưng không cùng thông tin hiển thị. Bởi vậy không chuẩn hóa mọi BigDecimal bằng `stripTrailingZeros()` nếu nghiệp vụ dựa vào scale.

## 9. toString, toPlainString và toEngineeringString

Cùng một BigDecimal có thể được biểu diễn bằng các định dạng văn bản khác nhau.

- `toString()` tạo biểu diễn theo quy tắc chuẩn của API và có thể dùng ký hiệu khoa học tùy scale và adjusted exponent.
- `toPlainString()` xuất theo dạng thập phân không sử dụng ký hiệu mũ.
- `toEngineeringString()` khi cần ký hiệu mũ thì dùng số mũ là bội số của 3, phù hợp một số bối cảnh kỹ thuật.

Ví dụ an toàn:

~~~java
BigDecimal thousand = new BigDecimal("1000.00")
        .stripTrailingZeros();

System.out.println(thousand.toString());      // 1E+3
System.out.println(thousand.toPlainString()); // 1000
~~~

**Không suy rằng `toPlainString()` khôi phục được số 0 cuối đã bỏ.** Nó chỉ đổi cách in của **BigDecimal hiện tại**. Một khi đã `stripTrailingZeros()`, chuỗi `"1000.00"` không còn được phục hồi chỉ bằng `toPlainString()`.

Ngược lại, với một BigDecimal giữ scale dương thông thường như `new BigDecimal("1.20")`, cả `toString()` và `toPlainString()` đều cho `"1.20"`.

**Cảnh báo tài nguyên:** đối với số có scale rất lớn về độ lớn tuyệt đối, `toPlainString()` có thể tạo chuỗi rất dài. Không dùng nó tùy tiện cho dữ liệu không được giới hạn kích thước.

## 10. Các phép toán ảnh hưởng scale như thế nào?

`BigDecimal` có quy tắc riêng cho scale của kết quả. Vì vậy, dù **đầu vào giữ số 0 cuối**, kết quả sau phép tính có thể có scale khác.

### Cộng/trừ: thường chọn scale lớn hơn

Với phép cộng hoặc trừ chính xác không có `MathContext` làm tròn, preferred scale là:

\[
\text{scale(result)}=\max(\text{scale}(a),\text{scale}(b)).
\]

~~~java
BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("2.30");

System.out.println(a.add(b));      // 3.50
System.out.println(a.subtract(b)); // -1.10
~~~

Số 0 cuối trong kết quả được giữ phù hợp với scale lớn nhất của hai số.

### Nhân: scale thường cộng lại

Với phép nhân chính xác:

\[
\text{scale(result)}=\text{scale}(a)+\text{scale}(b)
\]

~~~java
BigDecimal length = new BigDecimal("1.20");
BigDecimal factor = new BigDecimal("2.0");

System.out.println(length.multiply(factor)); // 2.400
~~~

Giá trị số là 2,4 nhưng scale kết quả là 3, bởi `2 + 1 = 3`. Tuy nhiên, **không tự suy scale kết quả chính là độ chính xác phép đo thực tế**. Trong đo lường, phép nhân thường có quy tắc số chữ số có nghĩa riêng và cần biết bất định đầu vào.

### Chia: có nhiều trường hợp hơn

`divide(BigDecimal divisor)` không tự động làm tròn khi kết quả decimal vô hạn. Nó trả kết quả chính xác nếu biểu diễn hữu hạn, hoặc ném `ArithmeticException` nếu không thể biểu diễn chính xác.

~~~java
BigDecimal amount = new BigDecimal("1.20");

System.out.println(amount.divide(new BigDecimal("2"))); // 0.60
// amount.divide(new BigDecimal("7")); // ArithmeticException
~~~

Với phép chia chính xác, preferred scale bắt đầu từ `scale(a) - scale(b)`, nhưng có thể cần điều chỉnh scale để biểu diễn đúng kết quả. Khi chọn overload nhận scale và `RoundingMode` hoặc `MathContext`, quy tắc scale/precision phụ thuộc overload và làm tròn.

### Không dựa vào scale tự nhiên để quyết định số chữ số đầu ra

Sau các phép toán, nếu hợp đồng yêu cầu **luôn hai chữ số thập phân**, hãy áp dụng chính sách rõ ràng tại ranh giới dữ liệu:

~~~java
BigDecimal result = new BigDecimal("1.20")
        .multiply(new BigDecimal("2.0"));

System.out.println(result); // 2.400

BigDecimal displayed = result.setScale(2, RoundingMode.UNNECESSARY);
System.out.println(displayed); // 2.40
~~~

Đây là trường hợp loại một chữ số 0, không làm tròn giá trị. Nếu kết quả có chữ số khác 0 sau hai chữ số thập phân, `UNNECESSARY` sẽ từ chối, giúp phát hiện quy tắc dữ liệu bị vi phạm.

## 11. Chương trình Java 17+ đầy đủ

Tạo file `BigDecimalTrailingZerosDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

public class BigDecimalTrailingZerosDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("1.20");
        BigDecimal b = new BigDecimal("1.2");

        System.out.println("a=" + a
                + " scale=" + a.scale()
                + " precision=" + a.precision());
        System.out.println("b=" + b
                + " scale=" + b.scale()
                + " precision=" + b.precision());
        System.out.println("unscaled=" + a.unscaledValue());
        System.out.println("numeric equal=" + (a.compareTo(b) == 0));
        System.out.println("object equal=" + a.equals(b));

        System.out.println("scale up=" + b.setScale(2));
        System.out.println("trim=" + a.stripTrailingZeros());
        System.out.println("sum=" + a.add(new BigDecimal("2.30")));
        System.out.println("product=" + a.multiply(new BigDecimal("2.0")));
        System.out.println("quotient=" + a.divide(new BigDecimal("2")));

        BigDecimal thousand = new BigDecimal("1000.00")
                .stripTrailingZeros();
        System.out.println("thousands=" + thousand
                + " scale=" + thousand.scale()
                + " plain=" + thousand.toPlainString());

        BigDecimal zero = new BigDecimal("0.000")
                .stripTrailingZeros();
        System.out.println("zero=" + zero + " scale=" + zero.scale());

        BigDecimal rounded = new BigDecimal("1.235")
                .setScale(2, RoundingMode.HALF_UP);
        System.out.println("rounded=" + rounded);

        System.out.println("from double=" + BigDecimal.valueOf(1.20));
        System.out.println("negative zero=" + new BigDecimal("-0.00"));

        Map<BigDecimal, String> map = new HashMap<>();
        map.put(a, "two places");
        System.out.println("hash map same scale=" + map.get(a));
        System.out.println("hash map different scale=" + map.get(b));

        Set<BigDecimal> set = new TreeSet<>();
        set.add(a);
        set.add(b);
        System.out.println("tree set size=" + set.size());
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 BigDecimalTrailingZerosDemo.java
java BigDecimalTrailingZerosDemo
~~~

Stdout (đã đối chiếu các phép toán với JDK):

~~~text
a=1.20 scale=2 precision=3
b=1.2 scale=1 precision=2
unscaled=120
numeric equal=true
object equal=false
scale up=1.20
trim=1.2
sum=3.50
product=2.400
quotient=0.60
thousands=1E+3 scale=-3 plain=1000
zero=0 scale=0
rounded=1.24
from double=1.2
negative zero=0.00
hash map same scale=two places
hash map different scale=null
tree set size=1
~~~

Giải thích:

1. Hai số có cùng giá trị nhưng khác `scale` và `precision`; `compareTo` cho 0, còn `equals` cho false.
2. `setScale(2)` thêm chữ số 0 mà không đổi giá trị; `stripTrailingZeros` bỏ số 0 cuối.
3. Phép cộng/nhân/chia chính xác giữ scale theo quy tắc số học BigDecimal, không theo một tiêu chuẩn hiển thị chung.
4. `1000.00` sau khi strip thành một số có scale âm, in là `1E+3` nhưng `toPlainString` là `1000`.
5. `0.000` sau khi strip thành `0` với scale 0; biểu diễn gốc không còn.
6. `HALF_UP` tại `1.235` xuống hai chữ số cho `1.24`.
7. `BigDecimal.valueOf(1.20)` không thể biết literal nguồn đã viết thêm zero.
8. `BigDecimal("-0.00")` biểu diễn zero với scale 2; dấu âm của zero **không được bảo toàn** như một thuộc tính giá trị BigDecimal.
9. `HashMap` và `TreeSet` có thể xem hai biểu diễn cùng số là khác hoặc giống nhau theo hợp đồng equality/ordering khác nhau.

## 12. Số 0 có dấu và trailing zeros là hai khái niệm khác nhau

`BigDecimal` lưu giá trị số nguyên không có dạng signed zero riêng như `double`. Vì vậy:

~~~java
BigDecimal negativeZero = new BigDecimal("-0.00");
BigDecimal positiveZero = new BigDecimal("0.00");

System.out.println(negativeZero);                    // 0.00
System.out.println(negativeZero.equals(positiveZero)); // true
~~~

**Scale vẫn được giữ**, nhưng dấu âm của số 0 trong **văn bản gốc** không còn là một thuộc tính số học của BigDecimal. Nếu một ứng dụng khoa học thật sự cần biết người dùng đã nhập `"-0.00"` thay vì `"0.00"`, hãy lưu văn bản gốc hoặc metadata riêng.

Không nhầm điều này với `-0.0` của IEEE 754 binary floating point, vốn có bit dấu. `BigDecimal` không sử dụng mô hình giá trị số thực binary64 để lưu dấu zero.

## 13. Chính sách nhập liệu: giữ nguyên scale hay chuẩn hóa?

Bạn cần xác định yêu cầu trước khi viết parser.

**Phương án A — giữ scale gốc:** sử dụng `new BigDecimal(text)` rồi giữ đối tượng không strip. Phù hợp khi số chữ số sau dấu thập phân là một phần thông tin cần lưu.

**Phương án B — chuẩn hóa tất cả về 2 chữ số:** dùng `setScale(2, mode)`, có thể chọn `RoundingMode.UNNECESSARY` để từ chối dữ liệu không thể biểu diễn chính xác với hai chữ số.

**Phương án C — chỉ giữ giá trị toán học:** dùng so sánh số học hoặc chuẩn hóa có chủ đích; không cam kết khôi phục lại chuỗi đầu vào.

Một phương thức validation theo chính sách **hai chữ số có thể thêm zero nhưng không làm tròn**:

~~~java
static BigDecimal requireTwoDecimalPlaces(String input) {
    if (input == null) {
        throw new IllegalArgumentException("Missing amount");
    }

    final BigDecimal value;
    try {
        value = new BigDecimal(input);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException("Malformed decimal amount", ex);
    }

    try {
        return value.setScale(2, RoundingMode.UNNECESSARY);
    } catch (ArithmeticException ex) {
        throw new IllegalArgumentException("More than two significant fractional digits", ex);
    }
}
~~~

Đây là phương thức đặt trong một lớp có import `BigDecimal` và `RoundingMode`. Nó nhận `"1.2"` và biến thành `1.20`, nhận `"1.200"` và trả `1.20`, nhưng từ chối `"1.234"`. Nó **không bảo toàn số lượng zero nguyên gốc**; nó chỉ bảo đảm kết quả có scale = 2.

Nếu hợp đồng đòi **đầu vào phải được viết đúng hai chữ số sau dấu chấm**, kể cả `"1.2"` cũng phải bị từ chối bằng một bước kiểm tra **grammar/scale gốc** trước khi chuẩn hóa. Đây là hai yêu cầu khác nhau.

## 14. Kiểm tra scale đầu vào khi zero cuối phải có ý nghĩa

Nếu quy định nhập liệu “phải đúng 2 chữ số thập phân”, có thể kiểm tra scale của BigDecimal nhận từ chuỗi:

~~~java
BigDecimal amount = new BigDecimal("1.20");

if (amount.scale() != 2) {
    throw new IllegalArgumentException("Expected scale 2");
}
~~~

Nhưng kiểm tra scale **không thay thế kiểm tra cú pháp gốc**:

- `new BigDecimal("1.20")` có scale 2.
- `new BigDecimal("1.2E+0")` có scale 1.
- `new BigDecimal("120E-2")` có scale 2 và cùng giá trị 1,20, nhưng cách viết khác `"1.20"`.
- `new BigDecimal("001.20")` có cùng giá trị và scale với `"1.20"` nhưng giữ zero đầu nếu cần là vấn đề **của chuỗi**, không phải của BigDecimal.

Nếu hệ thống yêu cầu **dạng chuỗi chuẩn duy nhất**, hãy xác thực raw input theo grammar định nghĩa rõ (ví dụ không có exponent, dấu thập phân là `.`, đúng hai chữ số phần lẻ), sau đó parse thành BigDecimal. Nếu cần giữ nguyên ký tự người nhập, lưu thêm raw input.

**Đừng suy rằng scale là thước đo đáng tin của bất định phép đo.** Khi cần thông tin về sai số, số chữ số có nghĩa đo lường hay độ phân giải, hãy biểu diễn chúng rõ ràng trong mô hình nghiệp vụ.

## 15. Định dạng hiển thị khác với thay đổi dữ liệu

Nếu dữ liệu nội bộ được lưu dưới dạng `BigDecimal("1.2")` mà màn hình phải hiển thị `"1.20"`, có hai hướng:

1. **Chuẩn hóa giá trị xuất:** `value.setScale(2, RoundingMode.UNNECESSARY).toPlainString()`, khi chính sách yêu cầu đúng 2 chữ số và cấm làm tròn.
2. **Định dạng bằng formatter:** dùng `NumberFormat`/`DecimalFormat` với locale và số chữ số fraction cố định nếu cần hiển thị theo khu vực.

~~~java
BigDecimal value = new BigDecimal("1.2");
String output = value.setScale(2, RoundingMode.UNNECESSARY)
        .toPlainString();

System.out.println(output); // 1.20
~~~

Không nhầm `toString()` / `toPlainString()` với formatter theo locale. Chúng dùng cú pháp số thập phân Java, không tự thay dấu thập phân thành dấu phẩy cho tiếng Việt/Đức.

Khi cần định dạng tiền theo locale, `NumberFormat.getCurrencyInstance(locale)` có thể áp dụng grouping, biểu tượng tiền và quy tắc số chữ số lẻ của đồng tiền. Việc dùng formatter có thể **khác với giữ nguyên biểu diễn đầu vào**; hãy lựa chọn theo mục tiêu.

### Đừng “giữ zero” bằng String.format trên double

~~~java
// Cách này chỉ tạo chuỗi định dạng, không bảo toàn scale gốc:
String display = String.format(java.util.Locale.US, "%.2f", 1.2);
System.out.println(display); // 1.20
~~~

Dòng code cho phép hiển thị hai chữ số sau dấu thập phân, nhưng giá trị gốc là `double` và không lưu thông tin về số chữ số đã nhập. Nếu phải bảo toàn scale qua nhiều bước nghiệp vụ, dùng BigDecimal hoặc metadata tương ứng.

## 16. JSON, database, CSV: mất số 0 cuối ở đâu?

Việc lưu BigDecimal trong RAM không đảm bảo **mỗi bước truyền dữ liệu** sẽ giữ scale.

### JSON

Một JSON number có thể được viết như:

~~~json
{"amount": 1.20}
~~~

Nhưng nhiều parser/serializer xem trường number là **giá trị số** và có thể chuyển qua kiểu floating point, chuẩn hóa hoặc xuất `1.2`. JSON không buộc mọi phần mềm phải giữ đúng biểu diễn lexical ban đầu của number.

Nếu định dạng có ý nghĩa bắt buộc, có thể thiết kế API lưu decimal như **chuỗi**:

~~~json
{"amount": "1.20"}
~~~

Cần ghi rõ trong schema/API rằng trường này là decimal string được validation, chứ không phải tùy tiện đổi number thành text trong từng hệ thống. Nếu khách hàng yêu cầu số JSON thay vì chuỗi, hãy kiểm thử serializer cụ thể với `BigDecimal` và định nghĩa rõ cam kết round-trip về scale.

### JDBC và cột DECIMAL

Khi sử dụng `DECIMAL(p, s)` hoặc `NUMERIC(p, s)` trong cơ sở dữ liệu, cột có thể có scale được cấu hình. DBMS, JDBC driver và mapping ORM có thể **chuẩn hóa giá trị về scale của cột** hoặc áp dụng quy tắc lưu khác.

- Ghi `1.2` vào cột scale 2 có thể đọc lại thành `1.20`.
- Ghi `1.200` vào cột scale 2 có thể bị chuẩn hóa/điều chỉnh theo quy tắc DBMS.
- Nếu cần giữ **scale nhập ban đầu thay đổi theo từng bản ghi**, cột decimal có scale cố định có thể không đủ; cân nhắc lưu metadata hoặc văn bản gốc.

Không khẳng định mọi database tự bảo toàn dấu 0 cuối nguyên văn. Phải kiểm tra schema, driver, dữ liệu đọc lại và yêu cầu nghiệp vụ.

### CSV và file văn bản

Với CSV, nếu writer xuất `BigDecimal.toPlainString()` từ đối tượng còn giữ scale thích hợp, chuỗi `1.20` có thể được giữ. Nhưng nếu bước nhập đã parse thành `double` rồi tạo BigDecimal từ giá trị đó, thông tin zero cuối có thể đã biến mất.

**Quy tắc round-trip:** xác nhận trạng thái scale tại từng ranh giới — input → parse → tính toán → lưu → đọc → serialize → hiển thị.

## 17. Hàm xuất giá trị chính xác với scale cố định

Một helper dễ kiểm thử cho kết quả decimal có đúng scale:

~~~java
static String toFixedScale(BigDecimal value, int scale) {
    if (value == null || scale < 0) {
        throw new IllegalArgumentException("Invalid value or scale");
    }
    return value.setScale(scale, RoundingMode.UNNECESSARY)
            .toPlainString();
}
~~~

Ví dụ:

~~~java
System.out.println(toFixedScale(new BigDecimal("10"), 2));    // 10.00
System.out.println(toFixedScale(new BigDecimal("10.50"), 2)); // 10.50
// toFixedScale(new BigDecimal("10.501"), 2); // ArithmeticException
~~~

**Giới hạn:** tham số scale và kích thước output phải nằm trong ngân sách ứng dụng. `setScale(1_000_000)` có thể tạo giá trị/chuỗi rất lớn hoặc tốn tài nguyên, dù giá trị số không đổi. Việc cố tình chỉ cho scale không âm là **chính sách của helper**, không phải giới hạn của BigDecimal, vốn cho phép scale âm.

Nếu yêu cầu làm tròn giá trị cho phép, có thể dùng overload helper nhận `RoundingMode`. Tuy nhiên phải ghi rõ chính sách, vì `HALF_EVEN`, `HALF_UP`, `DOWN` ... cho kết quả khác ở các điểm giữa.

## 18. Chuẩn hóa cho so sánh và canonicalization

Một số hệ thống muốn coi `1.20`, `1.200` và `1.2` như một giá trị duy nhất để tạo khóa hoặc so sánh. Khi **scale không thuộc khóa nghiệp vụ**, có thể dùng:

~~~java
BigDecimal canonical = new BigDecimal("1.200")
        .stripTrailingZeros();
System.out.println(canonical); // 1.2
~~~

Nhưng hãy nhớ `1000.00` sau strip có thể thành `1E+3`. Khi tạo textual canonical key, có thể cân nhắc `stripTrailingZeros().toPlainString()`, cùng ngân sách độ dài và quy tắc riêng cho zero.

Nếu hệ thống cần phân biệt mức chi tiết được ghi, canonicalization này **không đúng**. Hai bản ghi `"1.2"` và `"1.20"` phải được giữ riêng ở tầng dữ liệu thích hợp.

Với `HashMap<BigDecimal, ...>`, bạn có thể chuẩn hóa cả lúc ghi và đọc nếu thật sự cần tra cứu theo giá trị số. Với `TreeMap`/`TreeSet`, hãy hiểu `compareTo` không phân biệt scale, nên chính lựa chọn kiểu collection đã ảnh hưởng cách định danh phần tử.

## 19. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Tạo từ `new BigDecimal(1.20)` để giữ `"1.20"` | Literal đã là double; số 0 cuối bị mất, có thể thêm sai số binary | `new BigDecimal("1.20")` |
| Dùng `BigDecimal.valueOf(1.20)` để giữ độ dài fraction gốc | `Double.toString` không lưu cách viết literal | Parse từ String |
| Gọi `stripTrailingZeros` trước khi lưu mọi số | Mất scale, có thể chuyển thành `1E+3` | Chỉ strip khi mục tiêu là canonicalization |
| Tin `toPlainString` phục hồi `1000.00` sau strip | Scale đã thay đổi | Giữ đối tượng gốc hoặc metadata |
| Dùng `equals` để so **chỉ giá trị số** | `1.2` khác `1.20` | `compareTo(b) == 0` |
| Dùng `TreeSet<BigDecimal>` khi cần hai scale như hai bản ghi khác nhau | `compareTo` coi giá trị bằng nhau | Chọn key/record có scale rõ |
| Dùng `HashMap<BigDecimal,...>` nhưng truy vấn với scale khác | `equals` khác, get có thể null | Thống nhất scale hoặc canonical key |
| Chỉ kiểm tra `precision()` khi cần 2 chữ số phần lẻ | Precision khác scale | Kiểm tra `scale()` và grammar |
| Gọi `setScale(2)` với số có chữ số lẻ khác 0 bị loại | Ném `ArithmeticException` | Chọn rounding policy hoặc reject tường minh |
| Làm tròn nhiều bước mà không có chính sách | Kết quả thay đổi, sai số tích lũy | Chọn ranh giới rounding rõ ràng |
| Tin JSON number luôn giữ `1.20` | Serializer có thể chuẩn hóa | Kiểm tra round-trip hoặc dùng decimal string |
| Tin cột DECIMAL tự giữ scale nhập gốc | DB schema có thể cố định scale | Lưu thêm scale/raw input khi cần |
| Nghĩ số 0 cuối tự chứng minh sai số đo | Thiếu metadata bất định/đơn vị | Lưu độ phân giải, sai số và đơn vị riêng |
| Tin `BigDecimal("-0.00")` giữ dấu âm | BigDecimal biểu diễn số 0 không có sign âm riêng | Giữ raw text nếu cần |
| Dùng `toPlainString` với scale không giới hạn | Có thể tạo output cực lớn | Giới hạn scale và kích thước chuỗi |

## 20. Câu hỏi tự kiểm tra

**1.** `new BigDecimal("1.20").scale()` và `precision()` là bao nhiêu?

**Đáp án:** Scale 2, precision 3; unscaled value là 120.

**2.** `new BigDecimal("1.20").equals(new BigDecimal("1.2"))` có true không?

**Đáp án:** Không, vì khác scale. `compareTo()` của chúng trả 0 vì cùng giá trị toán học.

**3.** Vì sao `stripTrailingZeros()` có thể không phù hợp với dữ liệu đo được ghi là `"0.000"`?

**Đáp án:** Nó tạo BigDecimal tương đương với zero có scale 0 và khi in thành `"0"`, làm mất độ phân giải đã thể hiện trong biểu diễn gốc.

**4.** `new BigDecimal("1000.00").stripTrailingZeros().toString()` có thể hiển thị gì?

**Đáp án:** `1E+3`. Sau strip, scale là −3; `toPlainString()` là `"1000"`, không phải `"1000.00"`.

**5.** `new BigDecimal("1.20").multiply(new BigDecimal("2.0"))` in gì?

**Đáp án:** `2.400` vì scale kết quả của phép nhân chính xác là tổng scale 2+1 = 3.

**6.** Muốn xuất `1.2` thành chuỗi đúng hai chữ số sau dấu thập phân, không làm tròn giá trị, dùng gì?

**Đáp án:** `new BigDecimal("1.2").setScale(2, RoundingMode.UNNECESSARY).toPlainString()` → `"1.20"`.

**7.** Nếu yêu cầu phải lưu *chính xác từng ký tự* của `"+001.20"`, BigDecimal có đủ không?

**Đáp án:** Không. BigDecimal giữ giá trị thập phân cùng scale, không giữ mọi ký tự lexical như dấu cộng hoặc zero đầu. Cần lưu thêm text gốc.

**8.** Vì sao `new BigDecimal("1.235").setScale(2, RoundingMode.UNNECESSARY)` thất bại?

**Đáp án:** Bỏ chữ số 5 khác 0 sẽ làm thay đổi giá trị. `UNNECESSARY` yêu cầu phép thay đổi scale phải chính xác; nếu cần làm tròn, chọn một `RoundingMode` được nghiệp vụ chấp nhận.

## 21. Tóm tắt và tài liệu tham khảo

- `BigDecimal` biểu diễn số bằng **unscaled value × 10^(-scale)**. **Scale** giúp bảo toàn số 0 cuối sau dấu thập phân khi tạo trực tiếp từ chuỗi.
- **Giá trị số học bằng nhau** không có nghĩa `equals()` bằng nhau: `compareTo() == 0` chỉ so giá trị; `equals()` còn xét scale.
- `setScale()` có thể **thêm zero**, **loại zero** hoặc **làm tròn**, tùy scale đích và rounding mode.
- **`stripTrailingZeros()` chủ động bỏ thông tin biểu diễn**: `1.200 → 1.2`, `1000.00 → 1E+3` và `0.000 → 0`.
- Phép cộng, nhân, chia có quy tắc scale; **đầu ra nên có chính sách format/scale riêng** nếu yêu cầu đồng nhất.
- **Không đi qua double** để giữ số 0 cuối của dữ liệu decimal. Nếu cần giữ mọi ký tự nguyên gốc hoặc mức bất định phép đo, lưu metadata/văn bản nguồn bên cạnh BigDecimal.
- Kiểm tra round-trip qua JSON, database, CSV và formatter khi scale mang ý nghĩa nghiệp vụ.

Tài liệu chính thức (Java 17):

- [BigDecimal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `scale()`, `unscaledValue()`, `precision()`, `equals()`, `compareTo()`, `setScale()`, `stripTrailingZeros()`, `toString()` và `toPlainString()`.
- [RoundingMode API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): lựa chọn quy tắc làm tròn decimal.
- [BigDecimal — preferred scales for operations](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): quy tắc scale khi cộng, trừ, nhân và chia chính xác.
- [NumberFormat API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): hiển thị theo locale, giới hạn chữ số phần thập phân.
