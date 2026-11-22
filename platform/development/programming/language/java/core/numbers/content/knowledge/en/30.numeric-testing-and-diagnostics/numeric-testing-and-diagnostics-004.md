# NaN, vô cực, signed zero và subnormal trong Java

## 1. Vì sao phải hiểu các giá trị đặc biệt?

`float` và `double` của Java biểu diễn số dấu phẩy động nhị phân theo các quy tắc IEEE 754. Ngoài những số hữu hạn thông thường, chúng có **NaN** (*Not a Number*), **vô cực dương/âm**, **số 0 có dấu** (+0.0 và -0.0), và **số subnormal** (số hữu hạn khác 0 có độ lớn nhỏ hơn số normal dương nhỏ nhất).

Những giá trị này ảnh hưởng trực tiếp tới phép chia, so sánh, sắp xếp, thống kê, kiểm thử, định dạng, lưu trữ và xử lý dữ liệu từ API. Có thể gặp kết quả trông “hợp lệ” theo kiểu `double` nhưng không phù hợp với ràng buộc nghiệp vụ.

Các điểm phân biệt ngay từ đầu:

| Trường hợp | Ví dụ | Tính chất |
| --- | --- | --- |
| NaN | `0.0 / 0.0` | Không phải một giá trị số có thứ tự thông thường |
| Vô cực dương | `1.0 / 0.0` | Lớn hơn mọi số hữu hạn khi so sánh dấu phẩy động |
| Vô cực âm | `-1.0 / 0.0` | Nhỏ hơn mọi số hữu hạn khi so sánh dấu phẩy động |
| Dương không | `+0.0` | Số 0 có bit dấu dương |
| Âm không | `-0.0` | Số 0 có bit dấu âm; có thể cho kết quả khác trong vài phép toán |
| Subnormal dương nhỏ nhất | `Double.MIN_VALUE` | Số dương hữu hạn nhỏ nhất khác 0 của `double` |

**Cảnh báo tên hằng:** `Double.MIN_VALUE` **không** phải số âm hữu hạn nhỏ nhất. Nó là `4.9E-324`, một số dương subnormal. Giá trị hữu hạn âm lớn về độ lớn gần đáy miền biểu diễn là `-Double.MAX_VALUE`. Ngưỡng số *normal* dương nhỏ nhất là `Double.MIN_NORMAL`.

## 2. Nền tảng biểu diễn double và float

Một giá trị `double` có 64 bit, thường được mô tả thành 1 bit dấu, 11 bit exponent và 52 bit fraction. `float` có 32 bit với 1 bit dấu, 8 bit exponent và 23 bit fraction. Số normal sử dụng significand với một bit dẫn ngầm, tạo độ chính xác tương ứng khoảng 53 và 24 bit nhị phân.

Mô hình ý tưởng:

```text
double = sign (1 bit) | exponent (11 bit) | fraction (52 bit)

Exponent thông thường + fraction → số normal hữu hạn
Exponent toàn bit 1, fraction = 0 → +Infinity hoặc -Infinity
Exponent toàn bit 1, fraction ≠ 0 → NaN
Exponent toàn bit 0, fraction = 0 → +0.0 hoặc -0.0
Exponent toàn bit 0, fraction ≠ 0 → số subnormal
```

`float` cũng dùng những nhóm biểu diễn tương tự, nhưng số bit khác nhau. Đây là cơ chế của **kiểu dấu phẩy động nhị phân**, không phải của `BigDecimal`. Không suy diễn bit layout này cho `BigInteger` hoặc kiểu nguyên.

Từ Java 17, ngữ nghĩa dấu phẩy động luôn nghiêm ngặt theo đặc tả Java; khai báo `strictfp` không còn cần thiết để có cùng ngữ nghĩa như trước. Dù vậy, các hàm thư viện toán học có hợp đồng độ chính xác riêng; không nên tự hứa hẹn rằng mọi phép tính đều đúng tuyệt đối như phép toán trên số thực.

## 3. NaN — kết quả của phép toán không xác định

NaN có nghĩa *Not a Number*. Ví dụ:

```java
double a = 0.0 / 0.0;
double b = Math.sqrt(-1.0);
double c = Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY;
double d = Double.POSITIVE_INFINITY * 0.0;
```

Cả bốn biến đều mang NaN trong Java. Đây là các đoạn lệnh minh họa, đặt trong phương thức mới chạy được.

**Phép chia hai số dấu phẩy động bằng 0.0 / 0.0 trả NaN**, chứ không ném `ArithmeticException` như phép chia số nguyên cho 0. Ví dụ `int x = 1 / 0;` có thể biên dịch, nhưng khi chạy ném `ArithmeticException`; với mẫu số là biến nguyên có giá trị 0, phép chia cũng ném ngoại lệ này. Với `double`, chia số hữu hạn khác 0 cho ±0.0 thường cho vô cực có dấu.

### 3.1. So sánh primitive với NaN

NaN không có quan hệ thứ tự thông thường với số khác — kể cả chính nó:

```java
double x = Double.NaN;

System.out.println(x == x);  // false
System.out.println(x != x);  // true
System.out.println(x < 1.0); // false
System.out.println(x > 1.0); // false
System.out.println(x <= 1.0);// false
System.out.println(x >= 1.0);// false
```

Đừng dùng điều kiện `value == Double.NaN` để phát hiện NaN: nó **luôn false**. Hãy dùng:

```java
boolean isNan = Double.isNaN(value);
boolean isNanFloat = Float.isNaN(floatValue);
```

Hai dòng này giả định `value` có kiểu `double`, `floatValue` có kiểu `float` và nằm trong một phương thức.

### 3.2. Vì sao Double.equals khác toán tử ==?

`Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` trả **true** theo hợp đồng lớp wrapper, dù phép `doubleNaN == doubleNaN` trả false. `Double.compare` xây dựng một thứ tự tổng để các API collection có thể sắp xếp; theo thứ tự này, NaN được xem là bằng nhau trong comparator và **lớn hơn `Double.POSITIVE_INFINITY`**.

Vì vậy, hãy phân biệt:

- `==` và `<`, `>`: quan hệ so sánh primitive, NaN không bằng số nào.
- `Double.isNaN`: phát hiện NaN đúng ý nghĩa.
- `Double.equals`, `Double.hashCode`: hợp đồng object/hash, trong đó mọi biểu diễn NaN được đối xử tương đương để kiểm tra bằng nhau.
- `Double.compare`: thứ tự dùng được cho sắp xếp, có quy tắc đặc biệt cho NaN và signed zero.

NaN có thể có nhiều payload bit bên trong. `Double.doubleToLongBits` chuẩn hóa NaN về một dạng canonical; `Double.doubleToRawLongBits` giữ raw bits của đầu vào. Không dựa vào payload cụ thể của kết quả phép toán để xác định nguyên nhân NaN theo business logic.

## 4. Vô cực dương và âm

Java có `Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY`, tương ứng với `Float.POSITIVE_INFINITY` và `Float.NEGATIVE_INFINITY`.

```java
double positive = 1.0 / 0.0;   // Infinity
double negative = -1.0 / 0.0;  // -Infinity
double overflow = Double.MAX_VALUE * 2.0; // Infinity
```

Một số kết quả quan trọng:

| Phép toán | Kết quả |
| --- | --- |
| `1.0 / +0.0` | `Infinity` |
| `1.0 / -0.0` | `-Infinity` |
| `-1.0 / +0.0` | `-Infinity` |
| `1.0 / Double.POSITIVE_INFINITY` | `0.0` |
| `Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY` | `NaN` |
| `0.0 * Double.POSITIVE_INFINITY` | `NaN` |
| `Double.MAX_VALUE * 2.0` | `Infinity` |

Vô cực **khác NaN**: `Double.isInfinite(positive)` là true, `Double.isNaN(positive)` là false. Vô cực cũng **không hữu hạn**. Các phép toán có thể lan truyền vô cực, biến hai vô cực đối dấu thành NaN, hoặc trả số không.

Đừng coi vô cực là “một số rất lớn nhưng bình thường” khi domain yêu cầu kích thước, thời gian, giá tiền hoặc tỷ lệ hữu hạn. Phép toán có thể tràn từ một input hoàn toàn hữu hạn thành vô cực; do đó validation chỉ kiểm tra input là chưa đủ.

## 5. Signed zero: +0.0 và -0.0 bằng nhau trong == nhưng vẫn khác bit

IEEE 754 có hai biểu diễn cho số 0: `+0.0` và `-0.0`. Với phép so sánh primitive:

```java
double positiveZero = 0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero); // true
System.out.println(1.0 / positiveZero); // Infinity
System.out.println(1.0 / negativeZero); // -Infinity
```

Như vậy, phép `==` coi hai số bằng nhau về giá trị, nhưng một số phép toán vẫn phân biệt được bit dấu. Âm không có thể phát sinh từ phép tính âm quá nhỏ rồi underflow, từ literal `-0.0` hoặc từ việc chuyển đổi và giữ dấu.

**Ba cách nhận biết khác nhau:**

- `negativeZero == 0.0` là true, không đủ phát hiện dấu.
- `Double.compare(-0.0, +0.0) < 0` là true theo thứ tự tổng của wrapper.
- `Double.doubleToRawLongBits(-0.0) == Long.MIN_VALUE` là true: bit dấu cao nhất được bật, các bit còn lại bằng 0.

Theo `Double.equals`, `Double.valueOf(-0.0).equals(Double.valueOf(+0.0))` là **false**. Đó là điểm khác với primitive `==`. `Double.hashCode` cũng phải bảo toàn hợp đồng `equals`, nên kết quả hash tương ứng có thể khác.

### 5.1. Tác động khi dùng HashSet và sắp xếp

Khi dùng `HashSet<Double>`, hai phần tử `+0.0` và `-0.0` là **hai giá trị khác nhau theo equals**. Với NaN, hai giá trị NaN có payload raw bit khác nhau vẫn được wrapper coi bằng nhau.

Một tập chứa `+0.0`, `-0.0`, NaN thứ nhất và NaN thứ hai có thể có kích thước **3**, không phải 2 hoặc 4. Tương tự, `TreeSet<Double>` dùng `Double.compare` nên tách signed zero và gom NaN. Hành vi này khác với cách primitive `==` đối xử với chúng; đừng thay thế các quy tắc đó một cách vô thức.

Các phép toán thư viện như `Math.min(+0.0, -0.0)` trả `-0.0`, còn `Math.max(+0.0, -0.0)` trả `+0.0`; nếu có tham số NaN, `Math.min` và `Math.max` trả NaN. Đây là các ngoại lệ hữu ích khi test logic min/max.

## 6. Subnormal: vùng rất gần 0 và gradual underflow

Số **normal** sử dụng significand với bit dẫn ngầm; số **subnormal** có exponent field bằng 0 và fraction field khác 0. Subnormal cho phép biểu diễn các số gần 0 nhỏ hơn ngưỡng normal nhỏ nhất bằng độ chính xác giảm dần (*gradual underflow*).

Với `double`:

- `Double.MIN_NORMAL` = `2.2250738585072014E-308`, số normal dương nhỏ nhất.
- `Double.MIN_VALUE` = `4.9E-324`, số subnormal dương nhỏ nhất khác 0.
- Một số hữu hạn `x` là subnormal khi `0 < Math.abs(x) && Math.abs(x) < Double.MIN_NORMAL`.
- `Double.MIN_VALUE / 2.0` làm tròn thành `+0.0`, vì kết quả toán học quá nhỏ để biểu diễn là một số khác 0 của `double`.
- `Math.nextUp(0.0)` là `Double.MIN_VALUE`; `Math.nextDown(0.0)` là `-Double.MIN_VALUE`.

`Float.MIN_NORMAL` và `Float.MIN_VALUE` có vai trò tương ứng cho kiểu `float`. Đừng dùng `Double.MIN_VALUE` để mô tả miền âm nhỏ nhất; tên viết tắt này chỉ số **dương nhỏ nhất**.

### 6.1. Không nhầm subnormal với zero, NaN hay Infinity

Subnormal vẫn là một số hữu hạn, khác 0. Nó có thể tham gia cộng/trừ/nhân/chia và `Double.isFinite` trả true. Tuy nhiên, khoảng cách giữa những giá trị biểu diễn được ở vùng subnormal khiến **độ chính xác tương đối suy giảm**.

Một phép tính rất nhỏ có thể:

1. Cho kết quả subnormal khác 0.
2. Tiếp tục nhỏ xuống, rồi làm tròn thành signed zero.
3. Khi kết quả bị mất hoàn toàn vì underflow, điều kiện `value == 0.0` có thể đúng dù kết quả toán học chưa phải 0.

Đây là lý do không nên dùng phép kiểm tra `x == 0.0` như một khẳng định rằng một thuật toán số không hề có underflow. Nếu ứng dụng xử lý xác suất cực nhỏ, chuẩn hóa log-likelihood, ma trận với hệ số rất bé hay phép chia tỷ lệ, cần cân nhắc miền giá trị và thuật toán ổn định số.

## 7. Chương trình Java 17+ thực thi các trường hợp đặc biệt

Lưu toàn bộ chương trình sau vào `FloatingDiagnosticsDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;
import java.util.stream.DoubleStream;

public class FloatingDiagnosticsDemo {
    public static void main(String[] args) {
        double nan = 0.0 / 0.0;
        double positiveInfinity = 1.0 / 0.0;
        double negativeInfinity = -1.0 / 0.0;
        double positiveZero = 0.0;
        double negativeZero = -0.0;
        double subnormal = Double.MIN_VALUE;

        System.out.println("NaN detected: " + Double.isNaN(nan));
        System.out.println("NaN == NaN: " + (nan == nan));
        System.out.println("NaN != NaN: " + (nan != nan));
        System.out.println("Infinity positive: "
                + (positiveInfinity == Double.POSITIVE_INFINITY));
        System.out.println("Infinity negative: "
                + (negativeInfinity == Double.NEGATIVE_INFINITY));
        System.out.println("Infinity finite: "
                + Double.isFinite(positiveInfinity));
        System.out.println("Signed zeros primitive equal: "
                + (positiveZero == negativeZero));
        System.out.println("Signed zeros boxed equal: "
                + Double.valueOf(positiveZero).equals(Double.valueOf(negativeZero)));
        System.out.println("Negative zero reciprocal: " + (1.0 / negativeZero));
        System.out.println("Signed zero ordering: "
                + (Double.compare(negativeZero, positiveZero) < 0));
        System.out.println("Subnormal positive: " + (subnormal > 0.0));
        System.out.println("Subnormal below normal: "
                + (subnormal < Double.MIN_NORMAL));
        System.out.println("Subnormal half underflow: "
                + (subnormal / 2.0 == 0.0));
        System.out.println("Next after zero: "
                + (Math.nextUp(0.0) == subnormal));
        System.out.println("Negative zero raw sign: "
                + (Double.doubleToRawLongBits(negativeZero) == Long.MIN_VALUE));
        System.out.println("Nonempty average can be NaN: "
                + Double.isNaN(DoubleStream.of(1.0, Double.NaN)
                        .average().orElseThrow()));

        Set<Double> samples = new HashSet<>();
        samples.add(positiveZero);
        samples.add(negativeZero);
        samples.add(Double.NaN);
        samples.add(Double.longBitsToDouble(0x7ff8000000000001L));
        System.out.println("HashSet size: " + samples.size());
        System.out.println("HashSet contains NaN: "
                + samples.contains(Double.NaN));
        System.out.println("Boxed NaN equals NaN: "
                + Double.valueOf(Double.NaN).equals(Double.valueOf(nan)));
    }
}
```

Biên dịch và chạy:

```bash
javac FloatingDiagnosticsDemo.java
java FloatingDiagnosticsDemo
```

Stdout đã kiểm chứng:

```text
NaN detected: true
NaN == NaN: false
NaN != NaN: true
Infinity positive: true
Infinity negative: true
Infinity finite: false
Signed zeros primitive equal: true
Signed zeros boxed equal: false
Negative zero reciprocal: -Infinity
Signed zero ordering: true
Subnormal positive: true
Subnormal below normal: true
Subnormal half underflow: true
Next after zero: true
Negative zero raw sign: true
Nonempty average can be NaN: true
HashSet size: 3
HashSet contains NaN: true
Boxed NaN equals NaN: true
```

Đầu ra chỉ dùng các thuộc tính có hợp đồng xác định; không phụ thuộc vào thuật toán sinh số ngẫu nhiên hay thứ tự duyệt của HashSet. Cặp NaN thêm vào Set có raw bit payload khác nhau nhưng `Double.equals` vẫn xem chúng cùng một khóa.

## 8. Double.isFinite: kiểm tra đầu vào và cả kết quả

Đối với nhiều nghiệp vụ, điều kiện tối thiểu là **giá trị phải hữu hạn**. Java cung cấp:

```java
Double.isNaN(x);       // Chỉ NaN
Double.isInfinite(x);  // Chỉ +Infinity hoặc -Infinity
Double.isFinite(x);    // Không phải NaN, cũng không phải vô cực
```

Ba dòng này minh họa API với biến `x` kiểu `double` trong một phương thức. `Double.isFinite` trả true cho cả +0.0, -0.0 và các số subnormal. Nó **không** kiểm tra rằng giá trị nằm trong miền nghiệp vụ, có đúng độ chính xác hay không.

Khi một phép tính chia yêu cầu kết quả hữu hạn và mẫu số khác 0, nên kiểm tra cả input lẫn output. Ví dụ lưu trong `FiniteValueDemo.java`:

```java
public class FiniteValueDemo {
    static double divideFinite(double numerator, double denominator) {
        if (!Double.isFinite(numerator) || !Double.isFinite(denominator)) {
            throw new IllegalArgumentException("Inputs must be finite");
        }
        if (denominator == 0.0) {
            throw new IllegalArgumentException("Denominator must be nonzero");
        }
        double result = numerator / denominator;
        if (!Double.isFinite(result)) {
            throw new ArithmeticException("Result is not finite");
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println("4 / 2 = " + divideFinite(4.0, 2.0));
        try {
            divideFinite(1.0, -0.0);
        } catch (IllegalArgumentException e) {
            System.out.println("Negative zero rejected");
        }
        try {
            divideFinite(Double.MAX_VALUE, 0.5);
        } catch (ArithmeticException e) {
            System.out.println("Overflow rejected");
        }
        try {
            divideFinite(Double.NaN, 1.0);
        } catch (IllegalArgumentException e) {
            System.out.println("NaN rejected");
        }
    }
}
```

Chạy:

```bash
javac FiniteValueDemo.java
java FiniteValueDemo
```

Stdout đã kiểm chứng:

```text
4 / 2 = 2.0
Negative zero rejected
Overflow rejected
NaN rejected
```

Hàm cố ý từ chối cả hai dạng zero làm mẫu số bằng điều kiện `denominator == 0.0`; điều kiện này bắt được cả +0.0 lẫn -0.0. Nó cũng kiểm tra kết quả sau phép chia, vì `Double.MAX_VALUE / 0.5` có input hữu hạn, mẫu số khác 0 nhưng **kết quả tràn thành Infinity**.

Đây là hợp đồng ví dụ khi kết quả *phải hữu hạn*. Có ứng dụng khoa học chủ động dùng Infinity hoặc NaN và cần chính sách khác. Không bắt mọi trường hợp thành một lỗi chung mà không xét ý nghĩa nghiệp vụ.

## 9. So sánh, sort, min/max và collection

Các toán tử quan hệ primitive, `Double.compare`, `Double.equals` và `HashSet/HashMap` có những quy tắc khác nhau. Phân biệt chúng trước khi viết điều kiện lọc hoặc khóa số.

| Cặp giá trị | `primitive ==` | `Double.equals` | `Double.compare` |
| --- | --- | --- | --- |
| `+0.0` và `-0.0` | true | false | `compare(-0.0, +0.0) < 0` |
| `NaN` và `NaN` | false | true | 0 |
| `+Infinity` và `+Infinity` | true | true | 0 |
| `1.0` và `1.0` | true | true | 0 |

`Double.compare` dùng một thứ tự tổng hữu dụng cho sort: `-Infinity` nhỏ hơn số hữu hạn, các số hữu hạn được xếp theo giá trị với `-0.0 < +0.0`, tiếp theo là `+Infinity` rồi NaN. Đừng biến quy tắc sort này thành một nhận định rằng NaN là “giá trị số lớn nhất” về mặt toán học.

`Math.min` và `Math.max` dùng quy tắc khác với `Double.compare` ở chỗ NaN **lan truyền**: nếu có một tham số NaN thì kết quả NaN. Với signed zero, `Math.min(+0.0, -0.0)` trả -0.0 và `Math.max(+0.0, -0.0)` trả +0.0.

Nếu cần tìm cực trị nhưng muốn **bỏ qua NaN**, hãy xây dựng chính sách lọc trước; nếu muốn từ chối dữ liệu bất thường, hãy xác thực bằng `Double.isFinite`. Không dựa vào `min`/`max` để “tự chữa” đầu vào.

## 10. NaN và thống kê: Optional có giá trị vẫn có thể là NaN

Với `DoubleStream.average()`, một stream rỗng trả `OptionalDouble.empty()`. Nhưng một stream **không rỗng** có NaN có thể trả `OptionalDouble` có mặt và chứa NaN:

```java
var result = java.util.stream.DoubleStream
        .of(1.0, Double.NaN)
        .average();

System.out.println(result.isPresent()); // true
System.out.println(Double.isNaN(result.orElseThrow())); // true
```

Đây là đoạn minh họa bên trong một phương thức; mã runnable trong chương trình ở mục 7 kiểm chứng tình huống này.

**“Không có mẫu”** và **“có mẫu nhưng phép tổng hợp trả NaN”** là hai trạng thái khác nhau. Nếu nghiệp vụ không cho phép NaN hoặc vô cực, kiểm tra dữ liệu đầu vào trước khi tổng hợp hoặc kiểm tra kết quả theo quy tắc đã xác định. Tránh tự động lọc NaN khỏi dữ liệu nếu việc đó thay đổi ý nghĩa sample count, nhất là ở báo cáo chất lượng dữ liệu.

Một phép tổng hợp toàn NaN không thể tự biến thành trung bình hợp lệ. Ngoài NaN, các phép cộng dồn với các giá trị hữu hạn rất lớn cũng có thể overflow thành Infinity, nên không có gì bảo đảm “mọi input hữu hạn” sẽ tạo output hữu hạn.

## 11. Underflow và thuật toán số: cách hiểu đúng

**Overflow** xảy ra khi một kết quả hữu hạn theo toán học vượt miền biểu diễn hữu hạn và có thể trở thành Infinity. **Underflow** xảy ra khi kết quả có độ lớn rất nhỏ, làm mất precision, thành subnormal hoặc làm tròn về signed zero.

Ví dụ:

```java
double tiny = Double.MIN_VALUE;
double half = tiny / 2.0;    // +0.0, underflow
double huge = Double.MAX_VALUE;
double twice = huge * 2.0;  // Infinity, overflow
```

Subnormal tạo khoảng đệm thay vì lập tức đưa mọi giá trị dưới `Double.MIN_NORMAL` về zero. Tuy vậy, vùng này có ít chữ số có nghĩa tương đối hơn; tính các sai số tương đối như `Math.abs(actual - expected) / Math.abs(expected)` với `expected` cực nhỏ có thể trở nên không ổn định, overflow, hoặc chia zero.

Một số nguyên tắc thực hành:

- Tránh trừ hai số gần bằng nhau nếu thuật toán có công thức tương đương ổn định hơn.
- Với tích của nhiều xác suất rất nhỏ, cân nhắc làm việc trong miền log khi phù hợp.
- Khi kiểm tra gần bằng zero, dùng tolerance được thiết kế theo scale của bài toán; một epsilon cố định cho mọi dữ liệu có thể gây sai.
- Đừng suy ra rằng `x == 0.0` nghĩa là không có signal; nó có thể là kết quả của underflow.
- Không tự tắt/substitute subnormal nếu chưa biết yêu cầu độ chính xác và nền tảng chạy.

Đối với tính toán tài chính cần decimal chính xác, `BigDecimal` có thể phù hợp hơn `double`, nhưng cũng phải xử lý scale, rounding, giới hạn tài nguyên và phép chia không hữu hạn thập phân.

## 12. Parse, định dạng và ranh giới API

Java có thể biểu diễn `NaN` và `Infinity` dưới dạng chuỗi khi gọi `Double.toString`:

```java
System.out.println(Double.toString(Double.NaN)); // NaN
System.out.println(Double.toString(Double.POSITIVE_INFINITY)); // Infinity
System.out.println(Double.toString(-0.0)); // -0.0
```

`Double.parseDouble("NaN")` trả NaN, `Double.parseDouble("Infinity")` trả vô cực dương. Điều này không có nghĩa mọi giao thức trao đổi dữ liệu đều cho phép chúng.

**JSON chuẩn không có token số NaN hoặc Infinity.** Một số thư viện từ chối serialize giá trị không hữu hạn, số khác có chế độ đặc biệt; phải chọn hợp đồng rõ ràng: từ chối yêu cầu, biểu diễn trạng thái lỗi, trường nullable, hoặc chuỗi đặc biệt được định nghĩa và xác thực. Không gửi token `NaN` như một JSON number và giả định client nào cũng đọc được.

**BigDecimal không có NaN hay Infinity.** Vì vậy, `BigDecimal.valueOf(Double.NaN)` và `new BigDecimal("Infinity")` không tạo giá trị decimal hợp lệ; chúng ném `NumberFormatException`. Chuyển từ `double` sang `BigDecimal` cần kiểm tra tính hữu hạn, đồng thời hiểu rằng giá trị `double` ban đầu có thể đã là xấp xỉ.

**Cơ sở dữ liệu và các hệ thống ngoài:** một số hệ quản trị có biểu diễn hay quy tắc cho giá trị dấu phẩy động không hữu hạn, một số không; thao tác sort, group, index, so sánh có thể khác Java. Hãy xác thực giá trị và schema ngay tại ranh giới, thay vì dựa trên hành vi mặc định của một hệ cụ thể.

**Signed zero khi xuất dữ liệu:** một hệ thống có thể quyết định giữ dấu âm để bảo toàn thông tin phép đo hoặc chuẩn hóa -0.0 thành 0.0 cho hiển thị. Nếu chuẩn hóa, hãy làm ở ranh giới đã định nghĩa, không áp đặt tùy tiện lên mọi thuật toán số.

## 13. Kiểm thử đúng các giá trị đặc biệt

Các test với floating point nên nêu chính xác loại kết quả mong đợi:

| Mục tiêu | Assertion phù hợp |
| --- | --- |
| Nhận biết NaN | `Double.isNaN(actual)` |
| Nhận biết vô cực dương | `actual == Double.POSITIVE_INFINITY` |
| Đảm bảo giá trị hữu hạn | `Double.isFinite(actual)` |
| Phân biệt -0.0 và +0.0 | `Double.doubleToRawLongBits(actual)` hoặc `Double.compare` |
| Xác nhận subnormal | `actual != 0.0 && Math.abs(actual) < Double.MIN_NORMAL` và hữu hạn |
| Xác nhận underflow về zero | Kiểm tra output zero và điều kiện đầu vào/hợp đồng phép tính |
| So sánh xấp xỉ hữu hạn | Tolerance phù hợp miền và giá trị, sau khi xử lý NaN/Infinity |

Đừng chỉ dùng `Math.abs(expected - actual) < tolerance` mà không kiểm tra trường hợp đặc biệt. Nếu `actual` là NaN, biểu thức so sánh trả false; nếu cả hai vô cực cùng dấu, phép trừ có thể tạo NaN, dù theo một chính sách chúng được xem tương đương. Việc định nghĩa so sánh gần bằng phải thể hiện rõ **chính sách đối với NaN, vô cực, signed zero** và cách chọn tolerance.

Một ví dụ kiểm tra finite và sai số cho các giá trị hữu hạn:

```java
static boolean closeFinite(double left, double right,
                           double absoluteTolerance) {
    if (!Double.isFinite(left) || !Double.isFinite(right)
            || !Double.isFinite(absoluteTolerance)
            || absoluteTolerance < 0.0) {
        return false;
    }
    return Math.abs(left - right) <= absoluteTolerance;
}
```

Đây là phương thức mẫu cần đặt trong class. Nếu phép trừ `left - right` overflow thành Infinity dù cả hai input hữu hạn thì kết quả trả false, phù hợp cách hiểu “không gần nhau” trong kiểm tra này. Đối với dữ liệu trải rộng nhiều bậc độ lớn, thêm tolerance tương đối với xử lý overflow cẩn thận, thay vì dùng ngưỡng tuyệt đối duy nhất.

## 14. Lỗi thường gặp

| Lỗi | Hậu quả | Hướng khắc phục |
| --- | --- | --- |
| `x == Double.NaN` | Luôn false | `Double.isNaN(x)` |
| Nghĩ mọi phép chia cho 0 đều ném `ArithmeticException` | Sai với `double`/`float`; có Infinity/NaN | Phân biệt phép tính nguyên và floating point |
| Coi Infinity là số bình thường | Có thể lan truyền giá trị không hợp lệ | `Double.isFinite` và domain validation |
| Chỉ kiểm tra input hữu hạn | Phép toán vẫn có thể overflow thành Infinity | Kiểm tra output |
| Coi `+0.0` và `-0.0` có raw bit giống nhau | Lỗi reciprocal, serialization hoặc hashing | Kiểm tra `Double.compare`/raw bits khi cần |
| Cho rằng `Double.MIN_VALUE` là số âm nhỏ nhất | Nhầm miền subnormal | Phân biệt `MIN_VALUE`, `MIN_NORMAL`, `-MAX_VALUE` |
| Coi subnormal là zero | Đánh mất những số hữu hạn rất nhỏ | Kiểm tra `0 < abs(x) < MIN_NORMAL` |
| Coi `OptionalDouble` có mặt là một số hữu hạn | NaN/Infinity vẫn có thể được chứa | Phân biệt presence và `Double.isFinite` |
| Truyền NaN/Infinity vào JSON number không có chính sách | Dữ liệu không hợp chuẩn hoặc hành vi thư viện không đồng nhất | Chuẩn hóa/serialize theo schema đã chốt |
| Dùng `double` cho số tiền exact | Sai số biểu diễn nhị phân | Chọn `BigDecimal` với rounding phù hợp |
| Suy NaN trong hash collection sẽ có hành vi giống `primitive ==` | Sai: `Double.equals` coi các NaN bằng nhau | Dùng API kiểm tra phù hợp mục đích |

## 15. Câu hỏi tự kiểm tra

1. **`0.0 / 0.0` trả gì?** NaN; không phải ngoại lệ phép chia nguyên.
2. **`1.0 / -0.0` trả gì?** Vô cực âm.
3. **`Double.NaN == Double.NaN` là true hay false?** False; dùng `Double.isNaN` để phát hiện NaN.
4. **`Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` là gì?** True, vì lớp wrapper định nghĩa tính bằng nhau của NaN phục vụ object/collection.
5. **`0.0 == -0.0` là gì?** True với primitive, nhưng `Double.equals` phân biệt hai biểu diễn.
6. **`Double.MIN_VALUE` có phải âm vô cùng nhỏ không?** Không; đó là số **dương subnormal nhỏ nhất khác 0**.
7. **Subnormal có hữu hạn không?** Có; nó khác 0, khác NaN và vô cực, nhưng độ chính xác tương đối nhỏ hơn số normal.
8. **`Double.MIN_VALUE / 2.0` cho gì?** `+0.0` vì underflow và làm tròn.
9. **Một tập có dữ liệu và `DoubleStream.average()` có thể trả NaN không?** Có; trạng thái Optional có mặt không đảm bảo số hữu hạn.
10. **Kiểm tra đầu vào bằng `Double.isFinite` đã đủ cho kết quả chưa?** Chưa; phép nhân/chia của input hữu hạn vẫn có thể overflow thành vô cực.
11. **Tại sao nên kiểm tra NaN/Infinity trước JSON?** JSON number chuẩn không có token NaN/Infinity; giao diện trao đổi dữ liệu phải xác định cách xử lý.
12. **Tại sao không luôn chuẩn hóa -0.0 thành +0.0?** Dấu có thể mang thông tin quan trọng trong thuật toán số hoặc quy tắc kết quả; chỉ chuẩn hóa nếu domain yêu cầu.

## 16. Ghi nhớ

`float`/`double` biểu diễn nhiều hơn các số hữu hạn thông thường. **NaN** khiến so sánh primitive khác kỳ vọng; **±Infinity** xuất hiện từ phép chia cho zero và overflow; **±0.0** bằng nhau theo `==` nhưng có bit và một số hành vi khác nhau; **subnormal** giúp biểu diễn số cực nhỏ trước khi underflow về zero.

Khi triển khai, hãy xác định rõ API đang dùng **so sánh primitive**, **thứ tự wrapper**, hay **equals/hashCode**. Dùng `Double.isNaN`, `Double.isInfinite`, `Double.isFinite` để chẩn đoán; kiểm tra cả input và output nếu cần hữu hạn; giữ chính sách dữ liệu thiếu, rounding, min/max và serialization nhất quán. Các ví dụ Java 17+ minh họa rằng hiểu đúng những trường hợp biên này quan trọng hơn việc chỉ kiểm thử trên những con số thông thường.
