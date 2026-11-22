# Phân biệt `==`, `equals` và thứ tự so sánh của số thực trong Java 17

## 1. Vì sao so sánh số thực cần được hiểu riêng?

Trong Java, `float` và `double` biểu diễn số thực bằng dạng dấu phẩy động nhị phân theo chuẩn IEEE 754. Cách biểu diễn này hiệu quả cho tính toán khoa học và kỹ thuật, nhưng **không phải mọi số thập phân đều có biểu diễn nhị phân hữu hạn, chính xác**. Vì vậy, hai phép tính có vẻ tạo cùng một kết quả theo toán học có thể cho ra hai giá trị `double` hơi khác nhau.

Ngoài ra, Java có cả kiểu primitive `double`/`float` và kiểu wrapper `Double`/`Float`. Cùng ký hiệu `==` nhưng ý nghĩa có thể là so sánh giá trị số hoặc so sánh identity của hai object. `equals()` và `compareTo()` lại có quy tắc riêng, đặc biệt với `NaN` và `+0.0`/ `-0.0`.

Mục tiêu của bài là chọn đúng phép so sánh theo câu hỏi cần trả lời:

- Hai giá trị primitive có bằng nhau theo toán tử số học của Java không?
- Hai wrapper có đại diện cho cùng một object hay có nội dung bằng nhau theo hợp đồng `equals`?
- Giá trị nào đứng trước giá trị nào trong một thứ tự sắp xếp?
- Hai kết quả tính toán có đủ gần nhau theo sai số cho phép của bài toán không?
- Dữ liệu có yêu cầu số thập phân chính xác như tiền tệ hay không?

Đây là kiến thức Java vẫn áp dụng hiện nay. Các ví dụ dùng cú pháp và API ổn định của Java 17.

## 2. Nền tảng: số thực nhị phân không lưu mọi số thập phân chính xác

### 2.1. `float` và `double`

| Kiểu | Kích thước | Định dạng | Độ chính xác thập phân xấp xỉ |
|---|---:|---|---:|
| `float` | 32 bit | IEEE 754 binary32 | Khoảng 6–7 chữ số có nghĩa |
| `double` | 64 bit | IEEE 754 binary64 | Khoảng 15–16 chữ số có nghĩa |

`double` có độ chính xác và miền biểu diễn lớn hơn `float`, nên thường là lựa chọn mặc định cho tính toán dấu phẩy động. Tuy nhiên, cả hai đều là biểu diễn **xấp xỉ** đối với nhiều phân số thập phân.

Ví dụ:

```java
double a = 0.1;
double b = 0.2;
double c = 0.3;

System.out.println(a + b);       // Thường hiển thị 0.30000000000000004
System.out.println(a + b == c);  // false
```

Về toán học, \(0.1 + 0.2 = 0.3\). Nhưng các giá trị `0.1`, `0.2`, `0.3` được làm tròn sang những số binary64 gần nhất có thể biểu diễn. Kết quả phép cộng cũng được làm tròn, nên kết quả có thể không bằng chính giá trị được lưu cho literal `0.3`.

Điều này không phải lỗi riêng của toán tử `==`. Phép tính đã diễn ra trên những giá trị nhị phân gần đúng; so sánh chính xác đang phản ánh đúng các giá trị thực sự có trong máy.

### 2.2. Không phải mọi số đều xấp xỉ

Các số nguyên trong phạm vi thích hợp và một số phân số có mẫu là lũy thừa của 2 có thể được biểu diễn chính xác. Chẳng hạn `0.5`, `0.25`, `1.75` có biểu diễn nhị phân hữu hạn. Ngược lại, `0.1` có chu kỳ nhị phân và không thể lưu chính xác trong binary32/binary64.

Không nên kết luận rằng mọi phép so sánh `double` đều sai. Nếu chương trình cần kiểm tra một giá trị sentinel, một số nguyên được biểu diễn chính xác trong miền phù hợp, hoặc kết quả được tạo và kiểm tra theo cùng một quy trình xác định, `==` vẫn có thể là phép so sánh có chủ đích. Cần hiểu dữ liệu và yêu cầu trước khi chọn.

## 3. `==` với primitive `float` và `double`

Khi hai toán hạng là primitive số thực, `==` so sánh **giá trị dấu phẩy động** theo quy tắc của Java:

```java
double x = 1.5;
double y = 1.5;

System.out.println(x == y); // true
```

Với kết quả tính toán xấp xỉ:

```java
double x = 0.1 + 0.2;
double y = 0.3;

System.out.println(x == y); // false
```

Không có bước tự động áp dụng epsilon khi dùng `==`. Đây là so sánh chính xác hai giá trị binary floating-point đã được lưu.

### 3.1. Các toán tử quan hệ khác

Các toán tử `<`, `>`, `<=`, `>=` cũng so sánh giá trị số, nhưng cần chú ý những giá trị đặc biệt:

```java
double a = 2.0;
double b = 3.0;

System.out.println(a < b);  // true
System.out.println(a > b);  // false
System.out.println(a <= b); // true
System.out.println(a >= b); // false
```

Khi một toán hạng là `NaN`, **mọi phép so sánh quan hệ đều false**, kể cả so sánh bằng:

```java
double n = Double.NaN;

System.out.println(n == n);  // false
System.out.println(n != n);  // true
System.out.println(n < 1.0); // false
System.out.println(n > 1.0); // false
System.out.println(n <= 1.0); // false
System.out.println(n >= 1.0); // false
```

Vì vậy, đừng dùng `x == Double.NaN` để kiểm tra NaN. Hãy dùng:

```java
if (Double.isNaN(x)) {
    System.out.println("Gia tri khong phai so");
}
```

### 3.2. `+0.0` và `-0.0`

IEEE 754 có hai biểu diễn zero mang dấu:

```java
double positiveZero = +0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero); // true
System.out.println(positiveZero < negativeZero);  // false
System.out.println(positiveZero > negativeZero);  // false
```

Theo toán tử số học, hai giá trị so sánh bằng nhau. Tuy nhiên, dấu zero vẫn có thể ảnh hưởng đến một số phép tính:

```java
System.out.println(1.0 / positiveZero); // Infinity
System.out.println(1.0 / negativeZero); // -Infinity
```

Nếu ứng dụng quan tâm dấu của zero (ví dụ tính toán số học đặc thù, xử lý tín hiệu hoặc thuật toán số), `==` không phân biệt được hai trường hợp. `Double.compare`, `Double.equals` và `Double.compareTo` có quy tắc phân biệt chúng, sẽ trình bày ở phần sau.

### 3.3. Infinity và các giá trị đặc biệt

`double` có thể biểu diễn vô cực dương và âm:

```java
double positiveInfinity = Double.POSITIVE_INFINITY;
double negativeInfinity = Double.NEGATIVE_INFINITY;

System.out.println(positiveInfinity > 1.0); // true
System.out.println(negativeInfinity < -1.0); // true
System.out.println(positiveInfinity == Double.POSITIVE_INFINITY); // true
System.out.println(Double.isInfinite(positiveInfinity)); // true
```

Trước khi so sánh gần đúng, sắp xếp hoặc chuyển dữ liệu ra ngoài, nên xác định bài toán cho phép `NaN`/infinity hay không. `Double.isFinite(x)` trả về false cho NaN và cả hai vô cực.

## 4. `==` với wrapper `Double` và `Float`

`Double` và `Float` là **object**, mỗi object bọc một giá trị primitive. Vì vậy, khi cả hai toán hạng đều là tham chiếu wrapper, `==` kiểm tra **hai tham chiếu có trỏ đến cùng một object hay không**, không kiểm tra hai số bên trong có bằng nhau hay không.

```java
Double first = Double.valueOf(2.5);
Double sameReference = first;
Double another = Double.valueOf(2.5);

System.out.println(first == sameReference); // true: cùng object
System.out.println(first == another);      // So sánh identity, không phải giá trị số
System.out.println(first.equals(another)); // true: nội dung Double bằng nhau
```

Không dựa vào kết quả `==` giữa hai wrapper được tạo riêng để kiểm tra giá trị. Hợp đồng của `Double.valueOf` không biến `==` thành phép so sánh số.

### 4.1. Trường hợp một bên là primitive: unboxing

Nếu một toán hạng là primitive `double` và toán hạng còn lại là `Double`, Java có thể tự **unbox** wrapper thành primitive rồi thực hiện phép so sánh số:

```java
Double boxed = Double.valueOf(0.5);
double primitive = 0.5;

System.out.println(boxed == primitive); // true: boxed được unbox
```

Điều này khác hẳn trường hợp hai wrapper:

```java
Double a = Double.valueOf(0.5);
Double b = Double.valueOf(0.5);

System.out.println(a == b); // So sánh tham chiếu
```

Unboxing một wrapper `null` gây `NullPointerException`:

```java
Double missing = null;
// boolean same = (missing == 0.0); // Ném NullPointerException khi unbox
boolean sameObject = (missing == null); // true, không unbox
```

Khi wrapper có thể null, kiểm tra null trước khi dùng trong biểu thức số.

### 4.2. Đừng dựa vào autoboxing để so sánh object

Autoboxing/unboxing làm code ngắn hơn, nhưng đôi khi che khuất việc Java đang so sánh identity hay giá trị. Khi đọc một biểu thức có `Double`, hãy xác định **kiểu tĩnh của cả hai toán hạng**:

| Kiểu toán hạng trái | Kiểu toán hạng phải | Ý nghĩa thường gặp của `==` |
|---|---|---|
| `double` | `double` | So sánh giá trị primitive |
| `Double` | `Double` | So sánh identity của object |
| `Double` | `double` | Unbox `Double`, rồi so sánh giá trị |
| `Double` | `null` | So sánh tham chiếu với null, không unbox |

Nếu mục tiêu là so sánh nội dung wrapper, dùng `equals` hoặc `Double.compare` theo đúng ngữ nghĩa cần có.

## 5. `equals()` của `Double` và `Float`

`Double.equals(Object)` so sánh giá trị theo quy tắc dành cho wrapper `Double`, không giống hoàn toàn toán tử `==` trên primitive. Cụ thể, quy tắc phân biệt:

- Hai giá trị NaN được xem là bằng nhau theo `Double.equals`.
- `+0.0` và `-0.0` được xem là **khác nhau** theo `Double.equals`.
- Những giá trị số còn lại phải tương ứng cùng giá trị dấu phẩy động.

Ví dụ:

```java
Double nan1 = Double.valueOf(Double.NaN);
Double nan2 = Double.valueOf(Double.NaN);
Double plusZero = Double.valueOf(+0.0);
Double minusZero = Double.valueOf(-0.0);

System.out.println(nan1.equals(nan2));       // true
System.out.println(plusZero.equals(minusZero)); // false
System.out.println(Double.NaN == Double.NaN);   // false
System.out.println(+0.0 == -0.0);               // true
```

`Float.equals` có nguyên tắc tương ứng với `float`.

### 5.1. Vì sao NaN khác biệt?

Theo IEEE 754, NaN có nhiều bit pattern và mọi phép so sánh primitive với NaN đều không bằng, kể cả chính nó. Đối với wrapper, Java cần một hợp đồng `equals` có tính tương đương ổn định để dùng trong collection. `Double.equals` dùng dạng bit chuẩn hóa (canonicalized) để tất cả NaN được xem là bằng nhau.

Điều này giúp các collection dựa trên `equals`/`hashCode` hoạt động nhất quán:

```java
var values = new java.util.HashSet<Double>();
values.add(Double.NaN);
values.add(Double.longBitsToDouble(0x7ff8000000000001L));

System.out.println(values.size()); // 1
```

Hai giá trị được xem là NaN; cách chuẩn hóa bit trong `Double.equals` khiến chúng tương đương trong `HashSet`.

### 5.2. Vì sao signed zero khác biệt?

`Double.equals` phân biệt hai zero mang dấu vì bit biểu diễn của chúng khác nhau. Đây là lựa chọn có chủ đích cho hợp đồng wrapper và thứ tự toàn phần của số thực:

```java
Double a = 0.0;
Double b = -0.0;

System.out.println(a.equals(b)); // false
System.out.println(a.doubleValue() == b.doubleValue()); // true
```

Do đó, không thể dùng `Double.equals` nếu ý nghĩa nghiệp vụ yêu cầu hai zero mang dấu được xem là cùng một giá trị số. Khi ấy, hãy so sánh primitive sau khi xử lý null phù hợp.

### 5.3. Wrapper khác kiểu không bằng nhau

```java
Integer one = 1;
Double onePointZero = 1.0;

System.out.println(one.equals(onePointZero)); // false
```

`equals` phải tôn trọng tính đối xứng và hợp đồng của từng lớp. `Integer` không xem một `Double` là cùng kiểu giá trị, dù hai số có thể tương đương khi chuyển sang một dạng tính toán chung.

## 6. Thứ tự so sánh: `Double.compare` và `compareTo`

So sánh bằng không đủ để sắp xếp. Khi cần xác định giá trị nào đứng trước, đứng sau hoặc cùng thứ tự, Java cung cấp:

- `Double.compare(double a, double b)`: phương thức static trả về số âm, 0 hoặc số dương.
- `Double.compareTo(Double other)`: phương thức instance thực hiện so sánh theo thứ tự tự nhiên.
- `Float.compare` và `Float.compareTo`: tương tự cho `float`.

Quy ước kết quả:

| Kết quả | Ý nghĩa |
|---:|---|
| Nhỏ hơn 0 | Giá trị thứ nhất đứng trước giá trị thứ hai |
| Bằng 0 | Hai giá trị bằng nhau theo thứ tự so sánh của wrapper |
| Lớn hơn 0 | Giá trị thứ nhất đứng sau giá trị thứ hai |

Không nên kiểm tra chính xác kết quả là `-1` hay `1`; hợp đồng chỉ yêu cầu dấu âm, zero hoặc dấu dương.

```java
System.out.println(Double.compare(1.0, 2.0) < 0); // true
System.out.println(Double.compare(2.0, 1.0) > 0); // true
System.out.println(Double.compare(2.0, 2.0) == 0); // true
```

### 6.1. Thứ tự toàn phần đối với NaN và signed zero

`Double.compare` và `Double.compareTo` cung cấp thứ tự có thể dùng cho sắp xếp, kể cả những trường hợp toán tử quan hệ primitive không phân loại được:

1. Các giá trị âm nhỏ hơn các giá trị dương theo thứ tự số thông thường.
2. `-0.0` đứng trước `+0.0`.
3. NaN được xem là lớn hơn mọi giá trị số khác, kể cả `Double.POSITIVE_INFINITY`.
4. Các NaN được xem là bằng nhau theo thứ tự so sánh.

Ví dụ:

```java
System.out.println(Double.compare(-0.0, +0.0)); // số âm
System.out.println(Double.compare(+0.0, -0.0)); // số dương
System.out.println(Double.compare(Double.NaN,
        Double.POSITIVE_INFINITY) > 0);          // true
System.out.println(Double.compare(Double.NaN,
        Double.NaN) == 0);                       // true
```

Thứ tự này nhất quán với `Double.equals`: nếu `a.equals(b)` thì `a.compareTo(b) == 0`. Vì thế `Double` có thể dùng trong collection sắp xếp theo thứ tự tự nhiên.

### 6.2. Sắp xếp danh sách `Double`

```java
var values = new java.util.ArrayList<Double>();
values.add(Double.NaN);
values.add(+0.0);
values.add(2.0);
values.add(Double.NEGATIVE_INFINITY);
values.add(-0.0);
values.add(Double.POSITIVE_INFINITY);

values.sort(null); // Thứ tự tự nhiên của Double
System.out.println(values);
```

Thứ tự theo quy tắc `Double.compareTo`:

```text
[-Infinity, -0.0, 0.0, 2.0, Infinity, NaN]
```

Đây là một điểm khác với việc tự viết comparator dùng `a < b ? -1 : a > b ? 1 : 0`: cách viết đó xử lý NaN sai vì cả `a < NaN` và `a > NaN` đều false, khiến NaN bị coi như bằng nhiều giá trị không liên quan.

### 6.3. Khi dùng `TreeSet` và `HashSet`

`HashSet<Double>` dựa vào `equals`/`hashCode`; `TreeSet<Double>` dựa vào thứ tự tự nhiên (`compareTo`) hoặc comparator:

```java
var hash = new java.util.HashSet<Double>();
hash.add(+0.0);
hash.add(-0.0);

var tree = new java.util.TreeSet<Double>();
tree.add(+0.0);
tree.add(-0.0);

System.out.println(hash.size()); // 2
System.out.println(tree.size()); // 2
System.out.println(tree.first()); // -0.0
```

Trong trường hợp `Double`, thứ tự tự nhiên và `equals` thống nhất về việc phân biệt signed zero và gộp NaN. Nếu tự viết comparator có quy tắc khác, `TreeSet` có thể xem hai object là cùng một phần tử khi comparator trả 0 dù `equals` trả false. Điều này cần được cân nhắc khi dùng comparator tùy chỉnh.

## 7. So sánh gần đúng bằng sai số cho phép

Với các kết quả tính toán dấu phẩy động, yêu cầu thường là “hai giá trị đủ gần nhau” thay vì “hai bit pattern cho cùng giá trị”. Khi đó cần định nghĩa **tolerance** (sai số cho phép).

### 7.1. Absolute tolerance

So sánh theo sai số tuyệt đối:

\[
|a-b| \leq \varepsilon
\]

Trong Java:

```java
static boolean nearlyEqualAbsolute(
        double a, double b, double epsilon) {
    return Math.abs(a - b) <= epsilon;
}
```

Cách này phù hợp khi sai số tối đa có ý nghĩa cố định trong miền bài toán. Nhưng cùng một epsilon có thể quá chặt với số rất lớn và quá rộng với số rất gần 0.

### 7.2. Relative tolerance

Sai số tương đối so sánh độ chênh lệch với độ lớn của giá trị:

\[
\frac{|a-b|}{\max(|a|,|b|)} \leq r
\]

Trong thực tế cần xử lý riêng trường hợp cả hai gần 0, vì mẫu số bằng hoặc rất gần 0. Một công thức kết hợp absolute và relative tolerance thường dễ áp dụng hơn.

### 7.3. Kết hợp absolute và relative tolerance

Một chính sách thường dùng:

\[
|a-b| \leq \max(\varepsilon_{abs},
 r \cdot \max(|a|, |b|))
\]

Ví dụ:

```java
static boolean nearlyEqual(
        double a,
        double b,
        double absoluteTolerance,
        double relativeTolerance) {

    if (absoluteTolerance < 0 || relativeTolerance < 0
            || !Double.isFinite(absoluteTolerance)
            || !Double.isFinite(relativeTolerance)) {
        throw new IllegalArgumentException("Invalid tolerance");
    }

    if (Double.isNaN(a) || Double.isNaN(b)) {
        return false;
    }

    // Bằng nhau chính xác, bao gồm cùng vô cực và hai signed zero.
    if (a == b) {
        return true;
    }

    // Hai giá trị không bằng nhau mà có vô cực thì không gần nhau.
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }

    double difference = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    double allowed = Math.max(
            absoluteTolerance,
            relativeTolerance * scale);

    return difference <= allowed;
}
```

Ví dụ sử dụng:

```java
double actual = 0.1 + 0.2;
double expected = 0.3;

System.out.println(nearlyEqual(actual, expected, 1e-12, 1e-12)); // true
```

Các tolerance trong ví dụ chỉ để minh họa. **Không có một epsilon chung đúng cho mọi chương trình.** Hãy xác định:

- Đơn vị đo và độ lớn thường gặp của dữ liệu.
- Sai số tối đa mà nghiệp vụ hoặc thuật toán chấp nhận.
- Có cần phân biệt `+0.0` và `-0.0` không.
- NaN/infinity là dữ liệu hợp lệ hay phải từ chối.
- Giá trị rất nhỏ, rất lớn hoặc subnormal có thể xuất hiện không.

Hàm trên chủ động coi hai signed zero là gần nhau vì `a == b` trả true. Nếu bài toán cần phân biệt dấu zero, phải bổ sung quy tắc riêng trước bước đó. Phép trừ hai số hữu hạn cực lớn trái dấu cũng có thể tràn thành vô cực; trong trường hợp này chênh lệch thực tế lớn hơn mọi tolerance hợp lý của ví dụ.

### 7.4. Vì sao không nên dùng một epsilon tùy ý?

Ví dụ:

```java
double epsilon = 0.000001;
```

Một hằng số như vậy có thể hợp lý trong một bài toán cụ thể, nhưng không phải quy tắc của Java. Với dữ liệu cỡ \(10^{-12}\), nó có thể coi hai giá trị rất khác nhau là bằng nhau. Với dữ liệu cỡ \(10^{12}\), nó có thể quá nhỏ so với độ chính xác của phép tính.

Tolerance phải phản ánh **độ chính xác cần có của kết quả**, không phải một con số được sao chép từ ví dụ trên mạng.

### 7.5. So sánh theo ULP

ULP (*unit in the last place*) là khoảng cách giữa các giá trị floating-point biểu diễn kề nhau ở một độ lớn nhất định. Java cung cấp:

- `Math.ulp(double)` và `Math.ulp(float)`: khoảng cách ULP tại giá trị được xét.
- `Math.nextUp(x)`: giá trị biểu diễn kế tiếp lớn hơn theo hướng dương.
- `Math.nextDown(x)`: giá trị biểu diễn kế tiếp nhỏ hơn theo hướng âm.

```java
double x = 1.0;
double next = Math.nextUp(x);

System.out.println(next > x);            // true
System.out.println(next - x == Math.ulp(x)); // true với trường hợp này
```

Kiểm tra theo số ULP có ích trong thuật toán số cần giới hạn sai khác theo các giá trị biểu diễn kề nhau. Tuy nhiên, nó khó giải thích hơn absolute/relative tolerance và phải xử lý riêng NaN, infinity, signed zero, subnormal cũng như miền giá trị. Không thay thế chính sách sai số của nghiệp vụ bằng ULP chỉ vì nó có vẻ “chính xác hơn”.

## 8. Khi nào dùng `BigDecimal`?

Nếu bài toán cần số thập phân **chính xác theo chữ số thập phân**, ví dụ tiền tệ, thuế hoặc số lượng có quy tắc làm tròn, `BigDecimal` thường phù hợp hơn `double`.

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
BigDecimal sum = a.add(b);

System.out.println(sum); // 0.3
```

Tạo `BigDecimal` từ chuỗi thập phân giúp biểu diễn chính xác con số theo chuỗi đó. Tránh:

```java
BigDecimal wrongForDecimalIntent = new BigDecimal(0.1);
```

Constructor nhận `double` sẽ phản ánh chính xác giá trị binary floating-point gần đúng đang có trong `double`, không phải ý định thập phân ban đầu `0.1`. Nếu nguồn đã là `double`, `BigDecimal.valueOf(double)` thường là cách chuyển thuận tiện hơn vì dựa trên biểu diễn thập phân chuẩn của giá trị double; nhưng nếu cần chính xác dữ liệu nhập ban đầu, hãy parse từ `String` hoặc một biểu diễn decimal đáng tin cậy.

### 8.1. `BigDecimal.equals` và `compareTo` cũng khác nhau

`BigDecimal` có một quy tắc cần nhớ: `equals` xét cả **giá trị và scale**, còn `compareTo` so sánh giá trị số, bỏ qua khác biệt scale:

```java
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = new BigDecimal("2.00");

System.out.println(x.equals(y));      // false
System.out.println(x.compareTo(y));   // 0
System.out.println(x.compareTo(y) == 0); // true
```

`2.0` có scale 1, `2.00` có scale 2. Chúng có cùng giá trị số nhưng không bằng nhau theo hợp đồng `equals`.

Hệ quả khi dùng collection:

```java
var hashSet = new java.util.HashSet<BigDecimal>();
hashSet.add(new BigDecimal("2.0"));
hashSet.add(new BigDecimal("2.00"));

var treeSet = new java.util.TreeSet<BigDecimal>();
treeSet.add(new BigDecimal("2.0"));
treeSet.add(new BigDecimal("2.00"));

System.out.println(hashSet.size()); // 2: equals phân biệt scale
System.out.println(treeSet.size()); // 1: compareTo trả 0
```

Natural ordering của `BigDecimal` **không nhất quán với equals** ở trường hợp khác scale nhưng cùng giá trị. Đây là khác biệt quan trọng khi dùng `TreeSet`/`TreeMap`.

### 8.2. Chọn phép so sánh cho BigDecimal

| Câu hỏi | Cách dùng |
|---|---|
| Hai giá trị có cùng giá trị và scale không? | `a.equals(b)` |
| Hai giá trị có bằng nhau về số học không, bất kể scale? | `a.compareTo(b) == 0` |
| `a` nhỏ hơn `b` về số học? | `a.compareTo(b) < 0` |
| Muốn chuẩn hóa cách biểu diễn trước khi lưu? | Quy định scale/rounding hoặc chính sách `stripTrailingZeros()` rõ ràng |

Không dùng `==` để so sánh nội dung của hai `BigDecimal` vì đó là hai object.

## 9. Bảng chọn cách so sánh

| Nhu cầu | Cách thường dùng | Lưu ý |
|---|---|---|
| So sánh hai primitive `double` theo giá trị chính xác đang lưu | `a == b` | NaN luôn không bằng chính nó; signed zero được xem là bằng nhau |
| Kiểm tra một primitive là NaN | `Double.isNaN(a)` | Không dùng `a == Double.NaN` |
| Kiểm tra số hữu hạn | `Double.isFinite(a)` | Loại cả NaN và hai infinity |
| So sánh hai wrapper theo hợp đồng `Double` | `a.equals(b)` | NaN bằng NaN; signed zero khác nhau; cần để ý null |
| So sánh số thực theo thứ tự | `Double.compare(a, b)` hoặc `a.compareTo(b)` | Có thứ tự cho NaN và signed zero |
| Kiểm tra hai kết quả tính toán đủ gần | Hàm tolerance theo miền bài toán | Chọn absolute/relative tolerance phù hợp |
| Sắp xếp `List<Double>` | `list.sort(null)` hoặc comparator phù hợp | Thứ tự tự nhiên dùng `Double.compareTo` |
| Tính toán decimal chính xác | `BigDecimal` | Parse từ chuỗi; quy định scale và rounding |

## 10. Ví dụ tổng hợp chạy trên Java 17

Chương trình sau thể hiện các trường hợp quan trọng trong cùng một nơi:

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

public class Main {
    static boolean nearlyEqual(double a, double b, double epsilon) {
        if (Double.isNaN(a) || Double.isNaN(b)) {
            return false;
        }
        if (a == b) {
            return true;
        }
        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            return false;
        }
        return Math.abs(a - b) <= epsilon;
    }

    public static void main(String[] args) {
        double sum = 0.1 + 0.2;
        System.out.println(sum == 0.3);                  // false
        System.out.println(nearlyEqual(sum, 0.3, 1e-12)); // true

        double nan = Double.NaN;
        System.out.println(nan == nan);                  // false
        System.out.println(Double.valueOf(nan)
                .equals(Double.valueOf(nan)));           // true

        System.out.println(+0.0 == -0.0);                 // true
        System.out.println(Double.valueOf(+0.0)
                .equals(Double.valueOf(-0.0)));          // false
        System.out.println(Double.compare(-0.0, +0.0) < 0); // true

        List<Double> values = new ArrayList<>(
                List.of(Double.NaN, +0.0, 2.0,
                        Double.NEGATIVE_INFINITY, -0.0));
        values.sort(null);
        System.out.println(values);

        BigDecimal decimalA = new BigDecimal("2.0");
        BigDecimal decimalB = new BigDecimal("2.00");
        System.out.println(decimalA.equals(decimalB)); // false
        System.out.println(decimalA.compareTo(decimalB)); // 0
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

Kết quả chính:

```text
false
true
false
true
true
false
true
[-Infinity, -0.0, 0.0, 2.0, NaN]
false
0
```

Mỗi cặp kết quả cho thấy một hợp đồng khác nhau: primitive equality, tolerance, wrapper equality, thứ tự tổng quát và decimal equality.

## 11. Những lỗi thường gặp

### 11.1. Dùng `==` giữa hai wrapper

```java
Double a = Double.valueOf(0.1);
Double b = Double.valueOf(0.1);

// Không dùng để kiểm tra hai số có cùng giá trị:
boolean same = (a == b);
```

Đây là so sánh identity vì cả hai toán hạng là wrapper. Nếu cần giá trị theo hợp đồng wrapper, dùng `a.equals(b)`; nếu muốn số học primitive, kiểm tra null rồi unbox hoặc gọi `Double.compare(a, b)`.

### 11.2. Dùng `==` để kiểm tra NaN

```java
if (value == Double.NaN) { // Không bao giờ true
    // ...
}
```

Sửa thành `Double.isNaN(value)`.

### 11.3. Nghĩ `equals` và `==` luôn có cùng ngữ nghĩa

Với wrapper `Double`, NaN và signed zero chứng minh chúng khác nhau:

| Biểu thức | Kết quả |
|---|---|
| `Double.NaN == Double.NaN` | false |
| `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` | true |
| `+0.0 == -0.0` | true |
| `Double.valueOf(+0.0).equals(Double.valueOf(-0.0))` | false |

### 11.4. Tự viết comparator bằng `<` và `>`

```java
// Không đủ để xác định thứ tự đúng khi có NaN.
static int badCompare(double a, double b) {
    if (a < b) return -1;
    if (a > b) return 1;
    return 0;
}
```

Nếu một toán hạng là NaN, cả hai phép kiểm tra đều false nên hàm trả 0, dù giá trị kia có thể là số hữu hạn. Dùng `Double.compare(a, b)` khi cần thứ tự wrapper chuẩn.

### 11.5. Cho rằng epsilon cố định đúng cho mọi đại lượng

Sai số chấp nhận cho nhiệt độ, tọa độ, tỷ lệ, mô phỏng và kết quả thuật toán có thể rất khác nhau. Chọn tolerance từ đơn vị và yêu cầu nghiệp vụ; nếu dữ liệu là decimal chính xác, xem xét `BigDecimal`.

### 11.6. Chuyển sang BigDecimal quá muộn

Nếu dữ liệu tiền tệ được đọc vào `double`, cộng trừ nhiều lần rồi mới tạo `BigDecimal`, phần sai số binary đã phát sinh không thể tự mất đi. Hãy chọn kiểu dữ liệu đúng **từ ranh giới nhập dữ liệu**:

```java
BigDecimal price = new BigDecimal("19.95");
BigDecimal quantity = new BigDecimal("3");
BigDecimal total = price.multiply(quantity);
```

### 11.7. Quên null khi wrapper được unbox

```java
Double score = null;
// if (score > 0.0) { ... } // NullPointerException do unboxing
```

Kiểm tra null trước khi dùng toán tử số học, hoặc thiết kế API không cho phép wrapper null.

## 12. Bài tập thực hành

### Bài 1 — Dự đoán `==` và `equals`

```java
double a = Double.NaN;
double b = Double.NaN;
Double x = Double.valueOf(+0.0);
Double y = Double.valueOf(-0.0);
```

Hãy dự đoán:

- `a == b`
- `Double.valueOf(a).equals(Double.valueOf(b))`
- `x.equals(y)`
- `x.doubleValue() == y.doubleValue()`

**Đáp án:** lần lượt `false`, `true`, `false`, `true`. Giải thích dựa vào quy tắc NaN và signed zero.

### Bài 2 — Sắp xếp số thực

Tạo danh sách có `NaN`, hai signed zero, số âm, số dương và infinity; dùng `sort(null)`. Giải thích vì sao thứ tự bắt đầu bằng `-Infinity`, `-0.0` và kết thúc bằng `NaN`.

Gợi ý: danh sách dùng thứ tự tự nhiên của `Double`, tức `compareTo`.

### Bài 3 — So sánh gần đúng

Viết hàm kiểm tra hai số đo nhiệt độ chênh nhau không quá 0.05 độ. Xác định cách xử lý `NaN`, infinity và giá trị null nếu đầu vào được bọc bằng `Double`.

Gợi ý: tolerance là yêu cầu miền bài toán, không phải hằng số phổ quát. Với wrapper, kiểm tra null rồi chuyển sang primitive.

### Bài 4 — BigDecimal

Tạo:

```java
BigDecimal a = new BigDecimal("10.0");
BigDecimal b = new BigDecimal("10.00");
```

Giải thích tại sao `equals` trả false nhưng `compareTo` trả 0. Thử thêm cả hai vào `HashSet` và `TreeSet`, giải thích số phần tử.

**Đáp án:** `HashSet` có hai phần tử vì equality có tính đến scale; `TreeSet` có một phần tử vì natural ordering của `BigDecimal` xem chúng cùng vị trí so sánh.

### Bài 5 — Sửa comparator sai

Sửa hàm:

```java
static int compare(double a, double b) {
    return a < b ? -1 : a > b ? 1 : 0;
}
```

**Đáp án:** dùng `return Double.compare(a, b);`. Nếu bài toán muốn bỏ qua signed zero hoặc xử lý NaN theo một chính sách riêng, phải viết comparator theo hợp đồng đó và kiểm tra tính nhất quán.

## 13. Tiêu chí hoàn thành

Người học hoàn thành bài khi có thể:

1. Giải thích vì sao `0.1 + 0.2 == 0.3` có thể là false với `double`.
2. Phân biệt `==` của primitive, `==` giữa hai wrapper và trường hợp wrapper bị unbox.
3. Giải thích chính xác hành vi của NaN và signed zero với toán tử số học.
4. Mô tả quy tắc `Double.equals`/`Float.equals`, bao gồm NaN và hai signed zero.
5. Dùng `Double.compare` hoặc `compareTo` để sắp xếp và giải thích vị trí của NaN, infinity, `-0.0`, `+0.0`.
6. Viết kiểm tra gần đúng có tolerance phù hợp, chủ động xử lý NaN/infinity và không coi epsilon là giá trị cố định cho mọi bài toán.
7. Phân biệt `BigDecimal.equals` với `compareTo`, biết tạo dữ liệu decimal từ chuỗi và quy định scale/rounding khi cần.
8. Chọn đúng phép so sánh theo yêu cầu: equality chính xác, equality theo object, thứ tự sắp xếp hoặc gần đúng theo sai số.

## 14. Tài liệu chính thức

- [Java Language Specification, Java SE 17 — Floating-Point Types, Formats, and Values (§4.2.3)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): mô hình và giá trị dấu phẩy động.
- [Java Language Specification, Java SE 17 — Equality Operators (§15.21)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21): quy tắc toán tử `==` và `!=`.
- [Java SE 17 API — `Double`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): `equals`, `compare`, `compareTo`, NaN, infinity và signed zero.
- [Java SE 17 API — `Float`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html): các quy tắc tương ứng cho binary32.
- [Java SE 17 API — `BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): giá trị decimal, scale, `equals`, `compareTo` và rounding.
- [Java SE 17 API — `Math.ulp`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#ulp(double)): khoảng cách đơn vị biểu diễn tại một giá trị floating-point.

**Ghi nhớ:** `==` của primitive trả lời câu hỏi bằng nhau theo phép so sánh số; `equals` của wrapper tuân theo hợp đồng object có xử lý riêng NaN và signed zero; `compareTo`/ `Double.compare` cung cấp thứ tự sắp xếp; còn “đủ gần” cần một tolerance được xác định theo bài toán. Chọn đúng hợp đồng giúp tránh cả lỗi so sánh lẫn lỗi thiết kế dữ liệu.
