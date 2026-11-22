# Khi nào dùng `BigDecimal` thay `float` hoặc `double` trong Java?

Chọn kiểu số là một quyết định về **ngữ nghĩa dữ liệu và sai số được phép**, không chỉ về dung lượng bộ nhớ. `float` và `double` lưu số dấu phẩy động **nhị phân, độ chính xác hữu hạn**; `BigDecimal` lưu số thập phân theo mô hình một số nguyên không chia tỷ lệ (*unscaled value*) và một `scale`. Những con số trông giống nhau khi in ra có thể có cách biểu diễn và kết quả tính toán khác nhau.

Quy tắc thực hành quan trọng nhất:

- **Dùng `BigDecimal`** khi cần giữ chính xác các giá trị thập phân được nhập vào (giá, tiền, thuế, số lượng tính theo đơn vị thập phân, tỷ lệ hợp đồng), hoặc phải thực hiện chính sách làm tròn thập phân tường minh và kiểm tra được.
- **Dùng `double`** khi đang giải quyết bài toán số học xấp xỉ như khoa học, mô phỏng, đồ họa, thống kê hoặc học máy, nơi sai số dấu phẩy động đã được chấp nhận và hiệu năng/API số học là ưu tiên. `float` phù hợp khi ưu tiên bộ nhớ, băng thông, GPU hoặc API yêu cầu 32 bit và độ chính xác thấp hơn là đủ.
- **Không có kiểu nào tự làm phép tính của bạn đúng theo nghiệp vụ.** `BigDecimal` có phép chia phải làm tròn khi kết quả không thể biểu diễn hữu hạn ở hệ thập phân; `double` cần phân tích sai số và điều kiện biên.

## 1. Khác nhau ở cách biểu diễn

| Đặc tính | `float` | `double` | `BigDecimal` |
|---|---|---|---|
| Mô hình | IEEE 754 nhị phân 32 bit | IEEE 754 nhị phân 64 bit | `unscaledValue × 10^-scale` |
| Độ chính xác | 24 bit có nghĩa (khoảng 6–9 chữ số thập phân hữu ích) | 53 bit có nghĩa (khoảng 15–17 chữ số thập phân hữu ích) | Do biểu diễn nguyên/scale và tài nguyên cho phép |
| `0.1` thập phân | Không biểu diễn nhị phân chính xác | Không biểu diễn nhị phân chính xác | `new BigDecimal("0.1")` biểu diễn chính xác |
| Giá trị đặc biệt | `NaN`, `±Infinity`, số 0 có dấu | `NaN`, `±Infinity`, số 0 có dấu | Không có giá trị `NaN` hoặc vô cực |
| Phép toán | Toán tử `+ - * /` | Toán tử `+ - * /` | `add`, `subtract`, `multiply`, `divide`... |
| Chi phí thường gặp | Thấp, dùng phần cứng | Thấp, dùng phần cứng | Cao hơn, nhiều đối tượng/bộ nhớ |
| Ngữ cảnh điển hình | Đồ họa, dữ liệu số lượng lớn | Tính toán khoa học, số liệu gần đúng | Thập phân chính xác và làm tròn theo hợp đồng |

`BigDecimal` không có một giới hạn cố định về số chữ số như `double`, nhưng **không phải số thực vô hạn độ chính xác**: biểu diễn thập phân là hữu hạn, kích thước và scale bị giới hạn bởi tài nguyên và API; phép chia như `1/3` vẫn cần chọn quy tắc làm tròn để biểu diễn kết quả hữu hạn.

### Vì sao `0.1` không chính xác trong `double`?

Một số phân số thập phân hữu hạn lại là phân số nhị phân vô hạn. Ví dụ `0.5 = 1/2` biểu diễn chính xác bằng nhị phân, còn `0.1 = 1/10` có khai triển nhị phân lặp vô hạn. `double` chỉ giữ một số bit hữu hạn nên lưu giá trị **gần** 0.1 nhất trong lưới số nhị phân.

```java
double approximate = 0.1 + 0.2;
System.out.println(approximate); // 0.30000000000000004

BigDecimal exact = new BigDecimal("0.1").add(new BigDecimal("0.2"));
System.out.println(exact);       // 0.3
```

Đây là **đoạn minh họa trong phương thức**, không phải toàn bộ lớp Java độc lập. Đừng suy ra mọi phép cộng `double` đều sai, hoặc cứ thấy chuỗi dài là một lỗi JVM: kết quả tuân theo độ chính xác hữu hạn và quy tắc làm tròn của dấu phẩy động nhị phân.

## 2. Những tình huống nên chọn `BigDecimal`

### 2.1. Giá, thuế, lãi suất, chiết khấu và số tiền theo quy tắc thập phân

Khi đầu vào là các chữ số thập phân có ý nghĩa hợp đồng (ví dụ giá đơn vị `"19.99"`), việc biểu diễn chính xác giúp tránh đưa sai số nhị phân vào phép tính. Ví dụ:

```java
BigDecimal price = new BigDecimal("19.99");
BigDecimal quantity = new BigDecimal("3");
BigDecimal subtotal = price.multiply(quantity); // 59.97
```

Nếu cần tính phần thuế, làm tròn theo một chính sách **được định nghĩa rõ**:

```java
import java.math.RoundingMode;

BigDecimal taxRate = new BigDecimal("0.075");
BigDecimal tax = subtotal.multiply(taxRate)
                         .setScale(2, RoundingMode.HALF_UP);
// tax = 4.50
```

Đoạn mã minh họa giả định đã có các biến và import. `HALF_UP` ở đây chỉ là **ví dụ chính sách**, không phải quy định bắt buộc cho mọi quốc gia hoặc giao dịch. Độ chính xác phần nhỏ nhất của tiền tệ, điểm làm tròn (từng dòng hay tổng hóa đơn), cách xử lý số âm, khấu trừ và quy định làm tròn có thể khác nhau. Kiểu `BigDecimal` chỉ cho công cụ để thực hiện một quy tắc đã chọn.

Nếu dữ liệu toàn là số đơn vị nhỏ nhất (ví dụ số xu nguyên) và **không cần phép chia thập phân**, lưu `long` hoặc `BigInteger` dưới dạng số đơn vị nhỏ nhất cũng là thiết kế đáng cân nhắc. Chọn kiểu theo miền dữ liệu và thao tác, không mặc định rằng tất cả giá trị tiền phải luôn là `BigDecimal`.

### 2.2. Dữ liệu thập phân đi vào/đi ra có hợp đồng rõ ràng

Nếu API nhận chuỗi `"0.000001"` hoặc cơ sở dữ liệu có cột decimal chính xác, hãy giữ ý nghĩa số thập phân đó đến tận logic tính toán. `BigDecimal` có thể giúp:

- tránh mất chữ số có nghĩa khi chuyển qua `double`;
- xác thực scale hoặc số chữ số theo hợp đồng;
- làm tròn tường minh cho trường hợp quy định tối đa số chữ số;
- so sánh các giá trị thập phân mà không phụ thuộc sai số biểu diễn nhị phân.

Ví dụ kiểm tra dữ liệu phải có **tối đa hai chữ số thập phân mà không thay đổi giá trị**:

```java
BigDecimal input = new BigDecimal("12.340");
BigDecimal canonical = input.setScale(2); // 12.34, chính xác

// new BigDecimal("12.345").setScale(2)
// sẽ ném ArithmeticException nếu phải bỏ phần khác 0.
```

`setScale(2)` một tham số yêu cầu không được làm thay đổi giá trị toán học. Nếu cần **kiểm tra cả định dạng nguyên bản** (ví dụ cấm nhập quá hai ký tự sau dấu thập phân kể cả số 0), việc chuẩn hóa như trên chưa đủ: phải kiểm tra chuỗi nguồn hoặc metadata bổ sung trước khi chuẩn hóa.

### 2.3. Giá trị nguyên lớn chuyển sang phép toán thập phân

Một số `long` lớn có thể bị mất đơn vị khi ép sang `double`; độ chính xác nguyên tuyệt đối của `double` chỉ được đảm bảo cho tất cả số nguyên trong miền đến `2^53`. Khi cần tính tiếp với giá trị lớn và các hệ số thập phân chính xác, `BigDecimal.valueOf(long)` giữ nguyên số nguyên đầu vào.

```java
long idLikeNumber = 9_007_199_254_740_993L;
BigDecimal exact = BigDecimal.valueOf(idLikeNumber);
// exact = 9007199254740993
```

Tuy nhiên, với ID, khóa hoặc mã định danh **không thực hiện số học**, dùng kiểu nguyên hoặc chuỗi có ý nghĩa hơn. Chỉ chuyển sang `BigDecimal` nếu bài toán thật sự cần phép tính thập phân.

## 3. Khi nào `double` và `float` là lựa chọn đúng?

`double` thường phù hợp khi dữ liệu mang bản chất **đo lường/xấp xỉ**: vị trí, vận tốc, góc, tín hiệu, xác suất, thống kê, mô phỏng hoặc phép toán sử dụng các hàm toán học như `Math.sin`, `Math.sqrt`, `Math.log`. Trong các miền này:

1. Nguồn dữ liệu vốn có sai số đo đạc nên biểu diễn thập phân chính xác không làm nó trở thành số đo chính xác tuyệt đối.
2. Các thuật toán đã thiết kế với sai số dấu phẩy động, khoảng sai số tương đối/tuyệt đối và độ ổn định số.
3. Phần cứng, thư viện và vector hóa thường hỗ trợ `float`/`double` tốt hơn.
4. `double` có miền số mũ rất rộng và giá trị đặc biệt (`NaN`, `±Infinity`) đôi khi là một phần của mô hình tính toán.
5. Thư viện chuẩn `Math`/`StrictMath` tập trung vào kiểu nguyên thủy dấu phẩy động, không có API `BigDecimal` tương đương cho toàn bộ lượng giác, hàm mũ hay logarit.

`float` phù hợp với đồ họa, dữ liệu tensor, dữ liệu lưu trữ lớn hoặc API cần số 32 bit, **nếu sai số cho phép**. Với tính toán tổng quát trên CPU, `double` thường là mặc định hợp lý trước khi cân nhắc giảm độ chính xác xuống `float`.

Ví dụ đo một đại lượng thực nghiệm có sai số ±0.01, việc ép nó vào `BigDecimal("1.2345")` không làm số đo thực sự chính xác đến bốn chữ số sau dấu thập phân. Cần phản ánh độ bất định của phép đo trong mô hình.

### So sánh kết quả số gần đúng

Không mặc định so sánh hai kết quả tính toán `double` qua `==` nếu thuật toán chấp nhận sai số:

```java
double actual = 0.1 + 0.2;
double expected = 0.3;
double tolerance = 1e-12;

boolean close = Math.abs(actual - expected) <= tolerance;
// true trong tình huống này
```

Đây chỉ là ví dụ kiểm tra với miền giá trị nhỏ, hữu hạn. Ngưỡng sai số phải căn cứ miền dữ liệu và đặc tả thuật toán; phép kiểm tra đơn giản này không xử lý đầy đủ `NaN`, vô cực hay các giá trị có độ lớn rất khác nhau. Với dữ liệu có nhiều bậc độ lớn, có thể cần xét kết hợp sai số tuyệt đối/tương đối hoặc khoảng cách ULP.

## 4. Tạo `BigDecimal` đúng cách: nguồn thập phân rất quan trọng

Đây là lỗi ảnh hưởng trực tiếp đến lý do chọn `BigDecimal`.

| Cách tạo | Giá trị được lưu | Khi nào nên dùng |
|---|---|---|
| `new BigDecimal("0.1")` | Chính xác thập phân 0.1 | Khi nguồn là một chuỗi thập phân |
| `BigDecimal.valueOf(0.1)` | Dựa trên dạng chuỗi chuẩn của `double` (ở đây là 0.1) | Khi đầu vào hiện có kiểu `double` và muốn chuyển theo dạng thập phân mà Java thường in ra |
| `new BigDecimal(0.1)` | Chính xác giá trị **nhị phân của `double`**, hơi lớn hơn 0.1 | Chỉ khi thật sự cần giữ chính xác giá trị số nhị phân ban đầu |
| `BigDecimal.valueOf(100L)` | Chính xác số nguyên 100 | Khi nguồn là `long` |

`new BigDecimal(0.1)` không tạo chính xác số thập phân `0.1` theo ý định thông thường. Nó tạo biểu diễn thập phân chính xác của giá trị nhị phân đã được làm tròn:

```text
0.1000000000000000055511151231257827021181583404541015625
```

`BigDecimal.valueOf(0.1)` thường là lựa chọn chuyển đổi tốt hơn `new BigDecimal(0.1)` khi nguồn chỉ còn `double`, **nhưng nó không thể phục hồi những chữ số đã bị mất bởi các phép toán trước đó**.

```java
double alreadyRounded = 0.1 + 0.2;
BigDecimal converted = BigDecimal.valueOf(alreadyRounded);
// converted = 0.30000000000000004, không phải 0.3
```

Nếu đầu vào thực tế là `"0.1"` và `"0.2"`, hãy phân tích hai chuỗi thành `BigDecimal` **trước khi cộng**. Đó mới là cách tránh cho sai số nhị phân đi vào luồng xử lý thập phân.

## 5. `BigDecimal` vẫn cần chính sách độ chính xác và làm tròn

Biểu diễn thập phân hữu hạn không thể chứa chính xác mọi phân số. `1/8 = 0.125` có biểu diễn thập phân hữu hạn, còn `1/3 = 0.333...` thì không. Vì vậy:

```java
BigDecimal one = BigDecimal.ONE;

one.divide(new BigDecimal("8")); // 0.125
// one.divide(new BigDecimal("3")); // ArithmeticException
```

Phép `divide` không kèm quy tắc làm tròn yêu cầu kết quả chính xác và có biểu diễn thập phân hữu hạn. Với kết quả thập phân vô hạn, phải quy định số chữ số hoặc độ chính xác và cách làm tròn:

```java
BigDecimal ratio = BigDecimal.ONE.divide(
        new BigDecimal("3"), 2, RoundingMode.HALF_UP);
// ratio = 0.33
```

Ngoài `setScale`, có thể dùng `MathContext` khi muốn giới hạn tổng số **chữ số có nghĩa** cho một phép tính hay nhóm phép tính, thay vì cố định chữ số sau dấu thập phân:

```java
import java.math.MathContext;

MathContext context = new MathContext(5, RoundingMode.HALF_EVEN);
BigDecimal result = BigDecimal.ONE.divide(new BigDecimal("3"), context);
// result = 0.33333
```

**Phân biệt:**

- `setScale(2, ...)`: yêu cầu hai chữ số sau dấu thập phân (scale 2).
- `MathContext(5, ...)`: yêu cầu năm chữ số có nghĩa cho phép toán được áp dụng.
- Không có tham số làm tròn khi kết quả bắt buộc cắt chữ số khác 0: có thể ném `ArithmeticException`.

Không làm tròn tùy tiện ở mọi bước trung gian rồi cho rằng tổng cuối chắc chắn đúng. Ví dụ tính thuế từng dòng hóa đơn và cộng lại có thể khác việc cộng trước rồi tính thuế trên tổng. Chọn **điểm làm tròn** theo hợp đồng nghiệp vụ rồi kiểm thử kết quả.

## 6. So sánh giá trị `BigDecimal`: `equals` khác `compareTo`

Scale là một phần của biểu diễn `BigDecimal`, nên:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

a.equals(b);         // false (scale khác nhau)
a.compareTo(b) == 0; // true  (giá trị số bằng nhau)
```

`equals` xét cả giá trị lẫn scale; `compareTo` xét thứ tự theo giá trị số. Khi kiểm tra mức tiền bằng nhau về toán học, thường dùng `compareTo(...) == 0`; khi scale là một phần của hợp đồng dữ liệu, có thể chủ động dùng `equals`.

Hợp đồng `hashCode` đi theo `equals`. Hai giá trị thập phân bằng nhau về số nhưng khác scale có thể hoạt động như các **khóa khác nhau** trong `HashMap`/`HashSet`. Nếu dùng làm khóa, cần quy tắc chuẩn hóa rõ ràng, ví dụ scale cố định hoặc một định dạng chuẩn được thống nhất.

## 7. Ví dụ Java 17+ chạy độc lập

Lưu mã dưới tên **`BigDecimalChoiceDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class BigDecimalChoiceDemo {
    public static void main(String[] args) {
        double binarySum = 0.1 + 0.2;
        System.out.println("double sum: " + binarySum);

        BigDecimal a = new BigDecimal("0.1");
        BigDecimal b = new BigDecimal("0.2");
        System.out.println("decimal sum: " + a.add(b));
        System.out.println("new BigDecimal(0.1): " + new BigDecimal(0.1));
        System.out.println("BigDecimal.valueOf(0.1): " + BigDecimal.valueOf(0.1));
        System.out.println("valueOf(double sum): " + BigDecimal.valueOf(binarySum));

        long exactInteger = 9_007_199_254_740_993L;
        System.out.println("large as double then long: " + (long) (double) exactInteger);
        System.out.println("large as BigDecimal: " + BigDecimal.valueOf(exactInteger));

        System.out.println("1 / 8: " + BigDecimal.ONE.divide(new BigDecimal("8")));
        try {
            BigDecimal.ONE.divide(new BigDecimal("3"));
        } catch (ArithmeticException ex) {
            System.out.println("1 / 3 exact: ArithmeticException");
        }
        System.out.println("1 / 3 rounded: " +
                BigDecimal.ONE.divide(new BigDecimal("3"), 2, RoundingMode.HALF_UP));
        System.out.println("rounded amount: " +
                new BigDecimal("1.005").setScale(2, RoundingMode.HALF_UP));

        BigDecimal x = new BigDecimal("1.0");
        BigDecimal y = new BigDecimal("1.00");
        System.out.println("numeric equals: " + (x.compareTo(y) == 0));
        System.out.println("object equals: " + x.equals(y));

        System.out.println("double infinity: " + (1.0 / 0.0));
        try {
            BigDecimal.valueOf(Double.POSITIVE_INFINITY);
        } catch (NumberFormatException ex) {
            System.out.println("BigDecimal infinity: NumberFormatException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 BigDecimalChoiceDemo.java
java BigDecimalChoiceDemo
```

Kết quả stdout đã được xác minh bằng JDK:

```text
double sum: 0.30000000000000004
decimal sum: 0.3
new BigDecimal(0.1): 0.1000000000000000055511151231257827021181583404541015625
BigDecimal.valueOf(0.1): 0.1
valueOf(double sum): 0.30000000000000004
large as double then long: 9007199254740992
large as BigDecimal: 9007199254740993
1 / 8: 0.125
1 / 3 exact: ArithmeticException
1 / 3 rounded: 0.33
rounded amount: 1.01
numeric equals: true
object equals: false
double infinity: Infinity
BigDecimal infinity: NumberFormatException
```

Ý nghĩa các kết quả:

1. `double sum` và `decimal sum` cho thấy sai số biểu diễn nhị phân khác với phép cộng số thập phân chính xác.
2. `new BigDecimal(0.1)` cho biết chính xác giá trị nhị phân `double` thực sự lưu; `valueOf(0.1)` dùng chuỗi thập phân chuẩn của `double`.
3. `valueOf(double sum)` chứng minh phép chuyển kiểu **sau khi tính toán** không xóa sai số đã có.
4. Một số nguyên chỉ lớn hơn `2^53` một đơn vị không còn được giữ nguyên qua `double`, nhưng `BigDecimal.valueOf(long)` vẫn giữ đúng số nguyên.
5. `1/8` có kết quả chính xác; `1/3` không biểu diễn hữu hạn nên phải chọn phương pháp làm tròn.
6. `1.005` làm tròn tới hai chữ số với `HALF_UP` thành `1.01`, là ví dụ chính sách làm tròn thập phân tường minh.
7. `equals` khác `compareTo`; vô cực thuộc miền `double` nhưng không phải giá trị hợp lệ của `BigDecimal`.

## 8. Các đánh đổi về hiệu năng và khả năng tương tác

`BigDecimal` hữu ích khi bài toán **cần** độ chính xác thập phân, song không nên dùng cho mọi giá trị số theo thói quen.

**Hiệu năng:** `double` và `float` thường được xử lý bằng phần cứng, ít cấp phát hơn trong tính toán số quy mô lớn. `BigDecimal` là đối tượng bất biến và thực hiện số học dựa trên biểu diễn nguyên/scale nên có chi phí cấp phát, bộ nhớ và CPU đáng kể trong các vòng lặp lớn. Với yêu cầu hiệu năng, hãy đo trên workload thực thay vì đoán một tỷ lệ nhanh/chậm cố định.

**Tương tác API:** nhiều thư viện khoa học, đồ họa, xử lý tín hiệu và học máy nhận/trả `double` hoặc `float`. Đưa `BigDecimal` vào rồi liên tục chuyển ngược sang `double` có thể không tăng độ chính xác thực tế, vì khi chuyển ngược vẫn làm tròn về định dạng nhị phân.

**Miền giá trị:** `float`/`double` có `NaN`, vô cực, signed zero, số subnormal; `BigDecimal` chỉ biểu diễn số thập phân hữu hạn. `BigDecimal.valueOf(Double.NaN)` và `BigDecimal.valueOf(Double.POSITIVE_INFINITY)` không tạo được số hợp lệ, thường ném `NumberFormatException`.

**Lỗi tính toán:** `BigDecimal` không chữa được sai thuật toán, sai đơn vị đo, sai thời điểm làm tròn hoặc dữ liệu đo đạc vốn không chính xác. Nếu người dùng nhập “10,00” nhưng ứng dụng chọn nhầm đơn vị tiền tệ, `BigDecimal` vẫn tính đúng trên **giả định sai**.

**Độ lớn:** `BigDecimal` không bị khóa ở 64 bit, nhưng scale dùng kiểu `int` và khối lượng chữ số bị giới hạn thực tế. Kết quả hoặc phép dịch scale quá lớn có thể không khả thi hoặc ném ngoại lệ; không dùng nó như một kiểu đại diện vô hạn cho tất cả số thực.

## 9. Tiêu chí chọn kiểu dữ liệu trong dự án

| Câu hỏi thiết kế | Gợi ý chọn |
|---|---|
| Đầu vào là giá trị tiền tệ/số thập phân hợp đồng cần giữ đúng chữ số? | Ưu tiên `BigDecimal` từ chuỗi/decimal |
| Phép toán phải tuân theo scale và rounding cụ thể? | `BigDecimal` + `RoundingMode` |
| Giá trị thực sự là số đơn vị nhỏ nhất nguyên và đủ miền? | Cân nhắc `long`; dùng `BigInteger` nếu cần miền nguyên lớn |
| Bài toán là mô phỏng, hình học, thống kê, lượng giác, phép đo? | Thường chọn `double` với kiểm soát sai số |
| Dữ liệu lớn, GPU, băng thông hoặc API yêu cầu 32 bit? | Cân nhắc `float` nếu độ chính xác đáp ứng |
| Nguồn ban đầu đã tính bằng `double` và giờ đổi sang `BigDecimal`? | Xem lại nguồn và chuỗi phép tính; chuyển cuối không sửa sai số cũ |
| Cần biểu diễn `NaN` hay vô cực? | `float`/`double` hoặc thiết kế kiểu bao trạng thái riêng; `BigDecimal` không có các giá trị đó |

Một quy trình chọn kiểu thực tế gồm: xác định **đơn vị và miền giá trị**, độ chính xác/sai số yêu cầu, cách xử lý phép chia, khi nào phải làm tròn, kiểu dữ liệu ở ranh giới API/database, rồi mới tối ưu hiệu năng. Cần kiểm tra toàn bộ luồng dữ liệu, vì một bước ép sang `double` giữa chuỗi có thể làm mất ý nghĩa thập phân chính xác.

## 10. Lỗi phổ biến khi quyết định hoặc chuyển đổi

1. **Dùng `double` cho tiền rồi hy vọng `String.format("%.2f", ...)` sẽ sửa mọi phép tính.** Định dạng chỉ ảnh hưởng chuỗi cuối; sai số trong phép tính trước đó vẫn tồn tại.
2. **Viết `new BigDecimal(0.1)` vì tưởng nó biểu diễn đúng 0.1 thập phân.** Sử dụng `new BigDecimal("0.1")` khi nguồn là chuỗi số thập phân, hoặc `valueOf` khi chuyển một `double` sẵn có.
3. **Dùng `BigDecimal.valueOf(0.1 + 0.2)` rồi nghĩ là đã phục hồi 0.3.** Phép cộng thực hiện bằng `double` trước nên giá trị chuyển đổi vẫn mang dấu vết làm tròn.
4. **Gọi `divide` mà không thiết kế phép làm tròn.** Kết quả như 1/3 không có dạng thập phân hữu hạn; cần scale/`MathContext` và `RoundingMode` khi phù hợp.
5. **Cho rằng `BigDecimal` luôn chính xác tuyệt đối cho mọi phép số học.** Chia không kết thúc và các phép được giới hạn bởi `MathContext` đều có thể làm tròn; chính sách đó phải được công khai.
6. **Cho rằng mọi giá trị tiền tệ phải làm tròn tới hai chữ số.** Đơn vị tiền, quy định và trường hợp làm tròn có thể khác; không hard-code khi chưa có đặc tả.
7. **So sánh hai giá trị `BigDecimal` bằng `equals` khi chỉ cần bằng nhau về toán học.** Khác scale có thể khiến `equals` false; dùng `compareTo(...) == 0` nếu scale không có ý nghĩa nghiệp vụ.
8. **Dùng `BigDecimal` ở mọi thuật toán số mà không xét hiệu năng/thư viện.** Hãy đánh giá sai số cho phép, đặc trưng thư viện và khối lượng công việc.
9. **Chuyển `BigDecimal` sang `doubleValue()` rồi mặc định không mất dữ liệu.** Chuyển đổi có thể làm tròn, mất chữ số hoặc tràn sang vô cực khi ngoài miền `double`.
10. **Dùng so sánh `double` với một epsilon cố định cho mọi thang đo.** Ngưỡng đúng phải liên quan quy mô dữ liệu, số phép toán và đặc tả số học; cần xử lý riêng `NaN`/vô cực.

## 11. Bài tập và câu hỏi tự kiểm tra

1. Một API gửi `"23.45"` làm **đơn giá**, sau đó tính chiết khấu 12,5% và phải làm tròn từng dòng theo chính sách được cung cấp. Nên chọn kiểu gì? **Đáp án:** `BigDecimal` từ chuỗi, phép nhân thập phân và `setScale`/`RoundingMode` theo quy định.
2. Một cảm biến xuất nhiệt độ với sai số đo ±0,2°C và chương trình tính trung bình trên hàng triệu bản ghi. Có bắt buộc dùng `BigDecimal`? **Đáp án:** Không. `double` thường phù hợp nếu phân tích sai số/độ chính xác yêu cầu cho phép.
3. `BigDecimal.valueOf(0.1 + 0.2)` có cho `"0.3"` không? **Đáp án:** Không; kết quả là `0.30000000000000004` vì phép cộng đã thực hiện ở miền `double`.
4. `BigDecimal.ONE.divide(new BigDecimal("3"))` trả gì? **Đáp án:** Ném `ArithmeticException` do thập phân vô hạn mà không có quy tắc làm tròn.
5. Vì sao `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` false nhưng `compareTo == 0`? **Đáp án:** `equals` xét cả scale; `compareTo` chỉ xét giá trị số.
6. Một bài toán đồ họa cần hàng triệu tọa độ 32 bit cho GPU. Có nên chuyển toàn bộ sang `BigDecimal`? **Đáp án:** Thường không; `float` là kiểu phù hợp khi API và độ chính xác 32 bit đáp ứng yêu cầu.
7. Một số nguyên `9007199254740993` chuyển qua `double` rồi về `long` có bảo toàn không? **Đáp án:** Không; chương trình đã kiểm chứng nó thành `9007199254740992`. Giữ bằng `long` hoặc kiểu nguyên/decimal chính xác khi cần.

## Ghi nhớ

- `BigDecimal` giải quyết **nhu cầu biểu diễn và tính toán thập phân có kiểm soát**, đặc biệt khi chữ số thập phân và chính sách làm tròn mang ý nghĩa nghiệp vụ.
- `float`/`double` là lựa chọn hiệu quả cho **tính toán gần đúng có phân tích sai số**; không cần thay chúng bằng `BigDecimal` theo phản xạ.
- Chọn `BigDecimal` từ **nguồn số thập phân chính xác**. `new BigDecimal(double)` phản ánh giá trị nhị phân; `valueOf(double)` không sửa được sai số đã phát sinh trước khi chuyển.
- `BigDecimal` vẫn cần quy định phép chia, `MathContext`, scale và `RoundingMode`; đồng thời phải xử lý `equals`/`compareTo` đúng.
- Chất lượng kết quả đến từ **toàn bộ luồng dữ liệu và chính sách số học**, không chỉ từ tên kiểu dữ liệu.