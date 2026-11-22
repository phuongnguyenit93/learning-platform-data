# Số thực IEEE 754 trong JVM: NaN, vô cực, số không có dấu và tính nhất quán

## Mục tiêu học tập

Các kiểu `float` và `double` của Java không lưu trữ mọi số thực theo nghĩa toán học. Chúng lưu một tập hữu hạn các **giá trị dấu phẩy động nhị phân** cùng những giá trị đặc biệt theo mô hình IEEE 754. Sau bài này, bạn có thể:

- Giải thích cấu trúc, độ chính xác và vùng giá trị của `float`/`double` theo IEEE 754.
- Dự đoán kết quả khi phép tính tạo **NaN**, **vô cực dương/âm** và **số không mang dấu** (`+0.0`, `-0.0`).
- Phân biệt so sánh số học `==` với `Double.equals`, `Double.compare` và so sánh bit; hiểu tác động lên collection.
- Hiểu làm tròn, overflow, underflow, tính tái lập của phép tính Java 17+ và các giới hạn thực tế của tính nhất quán.
- Viết chương trình kiểm tra dữ liệu số, chọn cách so sánh/phép toán phù hợp và tránh lỗi khi truyền dữ liệu hoặc xử lý tài chính.

## 1. Hai kiểu số thực của Java và mô hình IEEE 754

Java có hai kiểu dấu phẩy động nguyên thủy:

| Tính chất | `float` | `double` |
| --- | --- | --- |
| Định dạng IEEE 754 | binary32 | binary64 |
| Tổng số bit | 32 | 64 |
| Bit dấu | 1 | 1 |
| Bit số mũ được mã hóa | 8 | 11 |
| Bit phần trị được lưu (fraction) | 23 | 52 |
| Độ chính xác phần trị với bit ẩn của số chuẩn hóa | 24 bit | 53 bit |
| Số chữ số thập phân có nghĩa gần đúng | khoảng 6–9 tùy mục đích biểu diễn | khoảng 15–17 tùy mục đích biểu diễn |
| Giá trị dương chuẩn hóa nhỏ nhất | `Float.MIN_NORMAL` | `Double.MIN_NORMAL` |
| Giá trị dương khác 0 nhỏ nhất (subnormal) | `Float.MIN_VALUE` | `Double.MIN_VALUE` |
| Giá trị hữu hạn dương lớn nhất | `Float.MAX_VALUE` | `Double.MAX_VALUE` |

Trong Java, literal `1.25` mặc định là `double`, còn `1.25f` là `float`. Dùng `double` khi không có lý do rõ ràng cần độ chính xác/không gian lưu trữ của `float`; **không** hiểu rằng `double` tính chính xác mọi giá trị thập phân.

Với số **chuẩn hóa (normal)** và khác 0, giá trị nhị phân được diễn giải theo dạng:

~~~text
(-1)^sign × (1.fraction) × 2^(storedExponent - bias)
~~~

Trong đó `bias` là 127 đối với binary32 và 1023 đối với binary64. Bit `1` đầu của phần trị ở số chuẩn hóa được ngầm định nên không lưu trực tiếp.

Các trường hợp đặc biệt theo bit mũ/phần trị:

| Bit số mũ | Bit phần trị | Ý nghĩa |
| --- | --- | --- |
| Không toàn 0 và không toàn 1 | Bất kỳ | Số hữu hạn chuẩn hóa |
| Toàn 0 | Toàn 0 | Số không; **bit dấu** phân biệt `+0.0` và `-0.0` |
| Toàn 0 | Có bit 1 | Số **subnormal**, cho phép độ lớn tiến dần về 0 |
| Toàn 1 | Toàn 0 | Vô cực `+Infinity` hoặc `-Infinity` theo bit dấu |
| Toàn 1 | Có bit 1 | **NaN** (*Not a Number*) |

Trong cách đặt tên hằng số Java, `Double.MIN_VALUE` **không phải** số âm hữu hạn nhỏ nhất; nó là **số dương khác 0 nhỏ nhất**, thuộc vùng subnormal. Để lấy số âm có trị tuyệt đối lớn nhất có thể biểu diễn hữu hạn, dùng `-Double.MAX_VALUE`.

### Vì sao biểu diễn thập phân có thể không chính xác?

Phân số `0.1` của hệ thập phân có khai triển nhị phân vô hạn, không được mã hóa chính xác trong binary64 hữu hạn bit. Do đó:

~~~java
double result = 0.1 + 0.2;
System.out.println(result);        // 0.30000000000000004
System.out.println(result == 0.3); // false
~~~

Đây là **đoạn minh họa đặt trong một phương thức Java**. Hai phép biểu diễn làm tròn khác nhau: tổng của số gần `0.1` và số gần `0.2` không trùng mẫu bit của literal `0.3`. Đối với dữ liệu số thực, những sai số biểu diễn rất nhỏ có thể tích lũy qua nhiều phép tính; không nên dùng `==` để hỏi liệu hai kết quả xấp xỉ có “đủ gần” nhau theo yêu cầu nghiệp vụ.

## 2. NaN: kết quả không biểu diễn được như một số

**NaN** viết tắt của *Not a Number*. Nó có thể xuất hiện trong những phép toán không có giá trị số thực/vô cực xác định, chẳng hạn:

~~~java
double a = 0.0 / 0.0;                         // NaN
double b = Double.POSITIVE_INFINITY
         - Double.POSITIVE_INFINITY;         // NaN
double c = 0.0 * Double.POSITIVE_INFINITY;   // NaN
double d = Math.sqrt(-1.0);                   // NaN
~~~

Đó là một **đoạn minh họa**, không phải một class độc lập. Không có `ArithmeticException` chỉ vì một phép toán `double` chia cho 0. Điểm này khác với chia nguyên, ví dụ `int x = 1 / 0;` gây lỗi do phép chia cho 0 (với biểu thức hằng như thế compiler có thể chấp nhận rồi ném khi đánh giá).

### NaN lan truyền như thế nào?

Với phần lớn phép toán số thực thông thường, nếu một toán hạng là NaN, kết quả cũng là NaN, ví dụ `Double.NaN + 1.0`, `Double.NaN * 2.0` và `Double.NaN / 3.0`. Những API cụ thể có thể quy định xử lý NaN riêng, vì vậy cần đọc contract của phương thức thay vì suy diễn mọi hàm trong thư viện đều giống các toán tử số học.

**NaN là “unordered” khi so sánh bằng toán tử:** `NaN == NaN` trả `false`, ngay cả cùng một biến; `NaN != NaN` trả `true`. Bất cứ phép so sánh thứ tự nào bằng `<`, `<=`, `>`, `>=` với ít nhất một NaN đều trả `false`.

| Biểu thức | Kết quả |
| --- | --- |
| `Double.NaN == Double.NaN` | `false` |
| `Double.NaN != Double.NaN` | `true` |
| `Double.NaN < 1.0` | `false` |
| `Double.NaN >= 1.0` | `false` |
| `Double.isNaN(Double.NaN)` | `true` |
| `Double.isFinite(Double.NaN)` | `false` |

Một bẫy logic: với NaN, điều kiện `!(x >= y)` **không tương đương** `x < y`. Nếu `x` là NaN, `x >= y` là `false`, nên phủ định thành `true`, nhưng `x < y` vẫn là `false`. Đừng viết validate khoảng số bằng hai nhánh `x < min` và `x > max` mà quên NaN: cả hai sẽ `false`, khiến NaN lọt qua. Kiểm tra tính hữu hạn trước.

**Dùng API thay vì so sánh với NaN:**

~~~java
if (Double.isNaN(value)) {
    // Xử lý phép đo không xác định.
}

if (!Double.isFinite(value)) {
    // Loại cả NaN và hai vô cực khi nghiệp vụ yêu cầu số hữu hạn.
}
~~~

Hai đoạn trên minh họa điều kiện kiểm tra, không phải chương trình độc lập.

## 3. Vô cực dương/âm và overflow

IEEE 754 có hai giá trị vô cực: `Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY` (tương tự với `Float`).

Một số tình huống:

| Phép tính số thực | Kết quả |
| --- | --- |
| `1.0 / 0.0` | `Infinity` |
| `-1.0 / 0.0` | `-Infinity` |
| `Double.MAX_VALUE * 2.0` | `Infinity` (overflow) |
| `1.0 / Double.POSITIVE_INFINITY` | `0.0` |
| `Double.POSITIVE_INFINITY + 3.0` | `Infinity` |
| `Double.POSITIVE_INFINITY / Double.POSITIVE_INFINITY` | `NaN` |
| `Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY` | `NaN` |
| `0.0 * Double.POSITIVE_INFINITY` | `NaN` |

**Overflow** khi kết quả hữu hạn về mặt toán học vượt ngưỡng định dạng có thể tạo vô cực (phụ thuộc dấu và quy tắc làm tròn). **Vô cực không giống giá trị hữu hạn lớn nhất**: `Double.MAX_VALUE` vẫn là hữu hạn; `Double.isFinite(Double.POSITIVE_INFINITY)` là `false`.

`Infinity` và `-Infinity` tham gia quan hệ thứ tự số học: `Double.POSITIVE_INFINITY > Double.MAX_VALUE` là `true`; `Double.NEGATIVE_INFINITY < -Double.MAX_VALUE` là `true`. Mọi biểu thức so sánh như vậy vẫn phải xét khả năng NaN xuất hiện, vì NaN không có vị trí trong thứ tự của các toán tử `<` và `>`.

**Không dùng vô cực làm giá trị sentinel một cách tùy tiện.** Trong một số thuật toán, vô cực có ý nghĩa rõ ràng, chẳng hạn khoảng cách ban đầu chưa biết; nhưng đưa vô cực vào tổng, trung bình hoặc phép chuẩn hóa có thể sinh ra NaN. Phải ghi rõ quy tắc xử lý “không có dữ liệu” thay vì đồng nhất NaN, vô cực và `null`.

## 4. Số không mang dấu: `+0.0` và `-0.0`

Với `float`/`double`, **hai dạng số không** có giá trị số học bằng nhau khi dùng toán tử `==`:

~~~java
System.out.println(0.0 == -0.0);  // true
System.out.println(0.0 < -0.0);   // false
System.out.println(1.0 / 0.0);    // Infinity
System.out.println(1.0 / -0.0);   // -Infinity
~~~

Đây là đoạn minh họa ở trong phương thức; chương trình chạy đầy đủ xuất hiện bên dưới.

IEEE 754 duy trì bit dấu ở số không để thông tin về hướng của giá trị được giữ lại trong những phép toán như chia, nhân và một số hàm số. Ví dụ, `-0.0` có thể phát sinh từ số âm quá nhỏ bị làm tròn về 0; kết quả `1.0 / -0.0` vẫn mang dấu âm.

Một số quy tắc hữu ích:

- Nhân hoặc chia với số không có thể truyền dấu theo quy tắc dấu của phép tính; `-1.0 * 0.0` cho `-0.0`.
- Kết quả của cộng/trừ số không còn phụ thuộc quy tắc làm tròn; không thể khẳng định “cứ có toán hạng âm 0 thì kết quả luôn âm 0”. Ví dụ `-0.0 + 0.0` cho `+0.0` trong chế độ làm tròn chuẩn.
- `Math.min(-0.0, +0.0)` trả `-0.0` và `Math.max(-0.0, +0.0)` trả `+0.0`.
- Hai số không có mẫu bit khác nhau; `Double.doubleToRawLongBits(-0.0)` mang bit dấu bật, còn `Double.doubleToRawLongBits(+0.0)` không.
- Với nhiều bài toán, phân biệt dấu số không không cần thiết; với tính toán số học, quy tắc thứ tự, kiểm thử bit hoặc serialization, khác biệt có thể rất quan trọng.

**Đừng dùng `x == 0.0` để kiểm tra dấu của số không.** Hãy kiểm tra bit nếu cần phân biệt chính xác `-0.0` và `+0.0`:

~~~java
boolean isNegativeZero = Double.doubleToRawLongBits(x)
        == Double.doubleToRawLongBits(-0.0d);
~~~

Đây là đoạn minh họa dùng biến `x` kiểu `double`. Lưu ý phép thử này chỉ trả `true` cho **chính xác âm 0**, không cho mọi số âm; cũng không thay thế kiểm tra NaN.

## 5. Ba quan hệ khác nhau: toán tử, wrapper và bit pattern

Một nhầm lẫn gây lỗi collection: **`double` nguyên thủy dùng `==` có quy tắc khác `Double.equals` và `Double.compare`**.

### A. So sánh số học bằng toán tử `==` và `<`

- `+0.0 == -0.0` là `true`.
- `NaN == NaN` là `false`.
- NaN không nhỏ, không lớn, cũng không bằng bất cứ giá trị nào, kể cả NaN.
- Vì NaN phá tính phản xạ của `==`, toán tử này **không tạo quan hệ tương đương** trên toàn bộ tập `double`.

Phù hợp với phép so sánh số học, nhưng thường **không phù hợp** để trực tiếp mô phỏng contract của `equals` trong kiểu đối tượng/collection.

### B. `Double.equals` và `Double.compare`

Wrapper `Double` định nghĩa ngữ nghĩa khác để `equals` có tính phản xạ và `compare` tạo thứ tự toàn phần:

| So sánh | Kết quả |
| --- | --- |
| `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` | `true` |
| `Double.valueOf(-0.0).equals(Double.valueOf(+0.0))` | `false` |
| `Double.compare(-0.0, +0.0) < 0` | `true` |
| `Double.compare(Double.NaN, Double.NaN) == 0` | `true` |
| `Double.compare(Double.NaN, Double.POSITIVE_INFINITY) > 0` | `true` |

Thứ tự do `Double.compare` xác lập có dạng:

~~~text
-Infinity < các số âm hữu hạn < -0.0 < +0.0
          < các số dương hữu hạn < +Infinity < NaN
~~~

Mọi NaN đều được `Double.compare` xem như bằng nhau cho mục đích so sánh. Quy tắc này phù hợp với `Double.equals` và hỗ trợ các cấu trúc `HashSet<Double>`, `HashMap<Double, ...>`, `TreeSet<Double>`, `TreeMap<Double, ...>` mà không vi phạm hợp đồng equals/ordering thông thường.

Hệ quả: `HashSet<Double>` có thể chứa **cả `-0.0` lẫn `+0.0`** như hai phần tử khác nhau, nhưng thêm nhiều NaN khác nhau sẽ được coi là cùng một phần tử theo `Double.equals`.

### C. So sánh các bit chính xác

API `Double.doubleToRawLongBits(x)` trả các bit biểu diễn *raw* của `double`. API `Double.doubleToLongBits(x)` sẽ **chuẩn hóa mọi NaN về một bit pattern NaN chuẩn** trước khi trả giá trị `long`.

| Mục đích | API phù hợp |
| --- | --- |
| Hỏi giá trị có phải NaN? | `Double.isNaN(x)` |
| Hỏi giá trị có hữu hạn? | `Double.isFinite(x)` |
| So sánh/khóa theo ngữ nghĩa wrapper nhất quán | `Double.equals`, `Double.compare` |
| Phân biệt `-0.0` với `+0.0` bằng bit | `Double.doubleToRawLongBits(x)` |
| Bảo toàn/phân tích payload NaN ở mức bit khi có thể | `Double.doubleToRawLongBits(x)` |
| Coi mọi NaN là một đại diện chuẩn | `Double.doubleToLongBits(x)` |

IEEE 754 cho phép **nhiều mẫu bit NaN** với các payload khác nhau. Các phép toán Java thường xử lý chúng như một giá trị NaN chung. Không được giả định phép toán sẽ giữ nguyên payload; đặc biệt **signaling NaN** có thể bị chuyển thành quiet NaN trên một số kiến trúc, thậm chí khi được truyền qua API chuyển đổi bit. Với `float` có các API tương ứng: `Float.floatToRawIntBits` và `Float.floatToIntBits`.

## 6. Ví dụ Java 17+ chạy được và kết quả kiểm chứng

Tạo tệp **`Ieee754Demo.java`** (tên tệp phải khớp với `public class`):

~~~java
public class Ieee754Demo {
    public static void main(String[] args) {
        double nan = 0.0 / 0.0;
        double positiveInfinity = 1.0 / 0.0;
        double negativeInfinity = -1.0 / 0.0;
        double positiveZero = +0.0;
        double negativeZero = -0.0;

        System.out.println("nan=" + Double.isNaN(nan));
        System.out.println("nanSelfEquals=" + (nan == nan));
        System.out.println("nanSelfNotEquals=" + (nan != nan));
        System.out.println("positiveInfinity=" + positiveInfinity);
        System.out.println("negativeInfinity=" + negativeInfinity);
        System.out.println("infinityIsFinite=" + Double.isFinite(positiveInfinity));
        System.out.println("signedZerosEqual=" + (positiveZero == negativeZero));
        System.out.println("positiveZeroReciprocal=" + (1.0 / positiveZero));
        System.out.println("negativeZeroReciprocal=" + (1.0 / negativeZero));
        System.out.println("boxedZerosEqual=" +
                Double.valueOf(positiveZero).equals(Double.valueOf(negativeZero)));
        System.out.println("negativeZeroBeforePositiveZero=" +
                (Double.compare(negativeZero, positiveZero) < 0));
        System.out.println("boxedNaNsEqual=" +
                Double.valueOf(nan).equals(Double.valueOf(Double.NaN)));
        System.out.println("nanAfterInfinity=" +
                (Double.compare(nan, positiveInfinity) > 0));
        System.out.println("overflow=" + (Double.MAX_VALUE * 2.0));
        System.out.println("halfSmallestSubnormal=" + (Double.MIN_VALUE / 2.0));
        System.out.println("decimalSum=" + (0.1 + 0.2));
        System.out.println("decimalEqual=" + (0.1 + 0.2 == 0.3));
    }
}
~~~

Biên dịch và chạy (sử dụng JDK 17 hoặc mới hơn):

~~~bash
javac Ieee754Demo.java
java Ieee754Demo
~~~

**Stdout chính xác:**

~~~text
nan=true
nanSelfEquals=false
nanSelfNotEquals=true
positiveInfinity=Infinity
negativeInfinity=-Infinity
infinityIsFinite=false
signedZerosEqual=true
positiveZeroReciprocal=Infinity
negativeZeroReciprocal=-Infinity
boxedZerosEqual=false
negativeZeroBeforePositiveZero=true
boxedNaNsEqual=true
nanAfterInfinity=true
overflow=Infinity
halfSmallestSubnormal=0.0
decimalSum=0.30000000000000004
decimalEqual=false
~~~

Giải thích những dòng dễ gây ngạc nhiên:

1. `0.0 / 0.0` tạo NaN, nhưng `nan == nan` vẫn là `false` vì quy tắc toán tử.
2. Chia cho `+0.0` và `-0.0` cho hai vô cực khác dấu.
3. `Double.valueOf(-0.0).equals(Double.valueOf(+0.0))` trả `false`, dù toán tử `==` trả `true`.
4. `Double.compare` đặt âm 0 trước dương 0 và NaN sau cả vô cực dương.
5. Nhân vượt miền hữu hạn tạo vô cực; chia một nửa `Double.MIN_VALUE` được làm tròn về `+0.0` vì giá trị chính xác nằm đúng giữa 0 và số subnormal dương nhỏ nhất, theo quy tắc gần nhất, chọn chữ số chẵn (*ties to even*).
6. `0.1 + 0.2` thể hiện sai số nhị phân; literal `0.3` không cùng kết quả binary64 sau làm tròn.

**Phạm vi ví dụ:** các dòng trên cố ý không có nhập liệu hay tính toán song song, nên thứ tự và stdout ổn định theo Java 17+. Đoạn mã không yêu cầu thư viện ngoài Java SE.

## 7. Làm tròn, overflow, underflow và số subnormal

**Làm tròn:** nhiều phép tính số học trên số thực cho kết quả thực có thể không nằm trong tập giá trị biểu diễn được. JVM phải làm tròn để trả một `float` hoặc `double`. Các toán tử số học Java 17+ sử dụng quy tắc gần nhất có thể, chọn chữ số chẵn khi hòa (*round to nearest, ties to even*) ở những phép toán tương ứng theo đặc tả. Điều này không có nghĩa mọi hàm thư viện đều tự động được tính chính xác vô hạn trước khi làm tròn; các hàm như `sin` hay `log` có hợp đồng độ chính xác riêng.

**Overflow:** trị tuyệt đối kết quả quá lớn so với miền hữu hạn có thể dẫn đến vô cực.

**Underflow:** trị tuyệt đối quá nhỏ có thể dẫn đến **subnormal** rồi cuối cùng về `+0.0` hoặc `-0.0`. Cơ chế *gradual underflow* giúp tránh việc mọi giá trị bé hơn `MIN_NORMAL` bị lập tức làm tròn về 0.

**Precision:** `float` có 24 bit phần trị hiệu dụng, `double` có 53 bit. Tăng độ chính xác từ `float` lên `double` có thể giúp giảm sai số nhưng **không biến phép toán thành số học thực vô hạn độ chính xác**.

Ví dụ dễ kiểm tra về khoảng cách giữa các giá trị biểu diễn được:

~~~java
System.out.println(Math.nextUp(1.0) > 1.0); // true
System.out.println(1.0 + Math.ulp(1.0) > 1.0); // true
~~~

Đây là đoạn minh họa trong phương thức Java. `Math.ulp(x)` trả độ rộng khoảng cách của đơn vị ở vị trí cuối (*unit in the last place*) theo đặc tả Java; `Math.nextUp(x)` đi đến giá trị dấu phẩy động kế tiếp theo chiều tăng. **ULP phụ thuộc độ lớn của x**, không phải một hằng số epsilon chung cho toàn miền.

### Tác động của thứ tự phép tính

Phép cộng số thực nhìn chung **không có tính kết hợp** (*associative*) như cộng số thực lý tưởng, do làm tròn ở từng bước. Ví dụ, trong `double`:

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
~~~

Ở biểu thức thứ hai, `b + c` làm mất `1.0` vì độ lớn chênh lệch quá xa; thứ tự gom nhóm khác nhau dẫn đến kết quả khác nhau. Vì vậy thay đổi thứ tự cộng, chia task song song hoặc thay cách reduction có thể đổi kết quả bit cuối dù từng phép toán đều tuân thủ IEEE 754. Không thể suy ra “tính nhất quán” đồng nghĩa với “kết quả bất biến với mọi thứ tự phép tính”.

Một số bài toán cần tính chính xác cao hơn có thể dùng thuật toán cộng bù như Kahan summation, pairwise summation, số học độ chính xác cao, hoặc cách tích lũy theo thứ tự ổn định. Lựa chọn tùy yêu cầu sai số và hiệu năng, không có một giải pháp áp dụng cho mọi ứng dụng.

## 8. Tính nhất quán giữa JVM và vai trò của `strictfp`

Ở các phiên bản Java trước 17, ngữ nghĩa dấu phẩy động có lịch sử cho phép một số kết quả trung gian dùng **miền số mũ mở rộng** trong ngữ cảnh không strict. Từ **Java 17**, JEP 306 khôi phục chế độ **always-strict floating-point semantics**: phép toán số thực Java tuân thủ quy tắc strict theo đặc tả, không còn cần bật `strictfp` để đạt ngữ nghĩa này.

- Các kiểu `float`/`double` gắn với định dạng IEEE 754 binary32/binary64, kể cả giá trị đặc biệt và subnormal.
- Biểu thức dấu phẩy động Java 17+ luôn chịu các quy tắc strict, giúp giảm khác biệt kiểu “dùng số mũ trung gian rộng hơn” giữa các nền tảng/JVM.
- Từ khóa `strictfp` vẫn có thể gặp trong mã cũ, nhưng ở Java 17+ nó **không còn tác dụng làm phép toán nghiêm ngặt hơn** và có thể bị compiler cảnh báo là không cần thiết.
- Trình biên dịch và JVM có thể tối ưu theo phạm vi luật Java cho phép; không được tùy ý đổi thứ tự biểu thức nếu điều đó làm thay đổi kết quả quan sát được mà đặc tả không cho phép.

**Phân biệt hai lớp tính nhất quán:**

1. **Ngữ nghĩa toán tử cơ bản theo JLS/JVMS:** cùng chương trình, cùng dữ liệu và cùng thứ tự đánh giá thì các phép toán được đặc tả nghiêm ngặt có kết quả theo quy tắc Java, thay vì phụ thuộc vào việc JVM tùy ý giữ phần trung gian trong độ chính xác vượt mức.
2. **Tái lập toàn bộ ứng dụng:** vẫn có thể khác vì thứ tự tính toán song song, dữ liệu đầu vào, dependency, phiên bản và hợp đồng của hàm toán học. Đừng hứa tính tái lập bit-for-bit cho *mọi* hàm số và môi trường chỉ vì dùng `double`.

### `Math`, `StrictMath`, `Math.fma` và phép dư

- Nhiều phép toán `Math` có quy định độ chính xác (ví dụ trong đơn vị ULP) nhưng không phải tất cả các hàm siêu việt đều bảo đảm cùng bit trên mọi triển khai và phiên bản. Khi cần kết quả tái lập cho các hàm được đặc tả phù hợp, kiểm tra contract cụ thể của `StrictMath`.
- `Math.fma(a, b, c)` tính phép nhân-cộng **fused** với một lần làm tròn cuối theo contract FMA. `a * b + c` là biểu thức hai phép toán, thường làm tròn sau nhân rồi sau cộng; chúng **có thể khác nhau**. Không coi đây là lỗi IEEE 754.
- Toán tử `%` của Java trên `float`/`double` dùng quy tắc **phép dư kiểu truncation**, không hoàn toàn giống phép remainder của IEEE 754 chọn thương gần nhất. Khi cần phép dư IEEE 754 theo định nghĩa phương thức, dùng `Math.IEEEremainder(x, y)`.
- Phép chuyển đổi kiểu và các phương thức của thư viện phải được xét theo đặc tả của chúng. Ví dụ, ép kiểu từ `double` sang `int` chuyển NaN thành `0`, còn số quá lớn theo hướng dương/âm có thể bị giới hạn ở `Integer.MAX_VALUE`/`Integer.MIN_VALUE`; đừng giả định nó ném ngoại lệ khi dữ liệu không hợp lệ.

## 9. Chọn phép so sánh theo mục đích

### Kiểm tra dữ liệu đầu vào

Nếu miền nghiệp vụ chỉ cho phép số hữu hạn:

~~~java
static double requireFinite(double x) {
    if (!Double.isFinite(x)) {
        throw new IllegalArgumentException("Expected a finite number");
    }
    return x;
}
~~~

Đây là **phương thức minh họa**, cần đặt trong một class khi chạy. `Double.isFinite` loại cả NaN lẫn hai vô cực, nhưng **chấp nhận `-0.0` và `+0.0`**. Nếu âm 0 có ý nghĩa riêng trong hệ thống, cần xử lý riêng bằng API bit hoặc chuẩn hóa có chủ ý.

### So sánh hai kết quả xấp xỉ

Nếu phép tính có sai số và nghiệp vụ xác định ngưỡng chấp nhận, nên xác định **absolute tolerance** và/hoặc **relative tolerance** theo miền giá trị, thay vì dùng một `EPSILON` tùy ý cho mọi trường hợp:

~~~java
static boolean approximatelyEqual(
        double a, double b, double absTol, double relTol) {

    if (absTol < 0 || relTol < 0 ||
            !Double.isFinite(absTol) || !Double.isFinite(relTol)) {
        throw new IllegalArgumentException("Invalid tolerances");
    }
    if (Double.isNaN(a) || Double.isNaN(b)) {
        return false;
    }
    if (a == b) {
        return true; // Kể cả hai vô cực cùng dấu và hai số không.
    }
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }

    double distance = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return distance <= Math.max(absTol, relTol * scale);
}
~~~

Đây là **phương thức minh họa**, không phải chương trình độc lập. Công thức chỉ là điểm khởi đầu cho bài toán số học thông thường: phép trừ `a - b` có thể overflow ngay cả khi `a` và `b` đều hữu hạn; chọn tolerance và thuật toán robust theo miền bài toán. Không tự động dùng “xấp xỉ bằng nhau” để làm `equals` hoặc key của `HashMap` vì quan hệ xấp xỉ thường **không có tính bắc cầu**.

### Sắp xếp số thực

Nếu cần sắp xếp `Double`, dùng `Double.compare` hoặc `Comparator.naturalOrder()` để có thứ tự toàn phần, nắm rõ NaN cuối và phân biệt âm 0/dương 0. Nếu nghiệp vụ muốn NaN ở đầu hoặc xem hai số không như nhau, hãy định nghĩa quy tắc riêng **nhất quán với equals/ordering của cấu trúc đang dùng**; đừng thay comparator tùy tiện rồi giả định `TreeSet` và `HashSet` có cùng semantics.

### Tính toán tiền hoặc thập phân đúng kỳ vọng nghiệp vụ

Dùng `BigDecimal` (với scale và `RoundingMode` rõ ràng) cho trường hợp cần chính xác trong hệ thập phân, chẳng hạn giá tiền:

~~~java
import java.math.BigDecimal;

BigDecimal first = new BigDecimal("0.1");
BigDecimal second = new BigDecimal("0.2");
System.out.println(first.add(second)); // 0.3
~~~

Đây là đoạn minh họa bên trong phương thức Java (cần import). Tránh `new BigDecimal(0.1)` nếu muốn chính xác giá trị **thập phân 0.1**: constructor nhận `double` giữ giá trị nhị phân xấp xỉ được đưa vào. `BigDecimal.valueOf(0.1)` sử dụng dạng chuỗi của `double` và thường dễ dùng hơn nhưng khi có đầu vào thập phân nguyên bản, tạo từ **chuỗi thập phân** rõ ràng nhất.

## 10. Lỗi và tình huống thực tế

| Tình huống | Sai lầm điển hình | Hướng xử lý |
| --- | --- | --- |
| Kết quả `0.1 + 0.2` không bằng literal `0.3` | Dùng `==` cho kết quả thập phân xấp xỉ | Xác định tolerance theo domain hoặc dùng `BigDecimal` cho thập phân chính xác |
| Validate `x >= min` và `x <= max` | Không loại NaN; một số cách viết bằng phủ định dễ bỏ sót NaN | `Double.isFinite(x)` trước khi kiểm tra miền |
| Chia `double` cho 0 | Chờ `ArithmeticException` như chia `int` | Kiểm tra mẫu số/miền nghiệp vụ và xử lý NaN/vô cực |
| Số rất lớn bị thành `Infinity` | Nghĩ mọi kết quả `double` đều hữu hạn | Kiểm tra `Double.isFinite` và thiết kế kiểm soát overflow |
| Giá trị rất nhỏ bị thành `0.0` | Nghĩ mọi số khác 0 đều giữ được sau phép tính | Hiểu subnormal, underflow và giới hạn precision |
| Hai `Double` chứa `-0.0` và `+0.0` trong `HashSet` | Nghĩ wrapper `equals` tương đương toán tử `==` | Chọn kiểu dữ liệu và quy tắc chuẩn hóa rõ ràng |
| Comparator tự viết dùng `a < b ? -1 : a > b ? 1 : 0` | NaN thành “bằng” mọi số theo nhánh cuối | Dùng `Double.compare(a,b)` khi cần thứ tự đầy đủ |
| Kết quả số học giữa các task song song chênh chữ số cuối | Nghĩ phép cộng floating-point có tính kết hợp | Kiểm soát thứ tự tổng hợp hoặc thuật toán cộng ổn định |
| Truyền NaN/vô cực qua JSON hoặc database | Nghĩ mọi định dạng dữ liệu ngoài đều hỗ trợ giá trị IEEE đặc biệt | Kiểm tra schema/protocol, xác thực và encode theo contract |
| Test so raw NaN payload trên mọi kiến trúc | Nghĩ payload NaN được bảo toàn qua mọi thao tác | Chỉ yêu cầu raw bit khi API/đường truyền bảo đảm; xem NaN theo ngữ nghĩa nếu phù hợp |

### Gợi ý kiểm thử có ý nghĩa

Với hàm nhận `double`, bộ test nên bao gồm **số hữu hạn dương/âm**, `+0.0`, `-0.0`, `Double.MIN_VALUE`, `Double.MIN_NORMAL`, `Double.MAX_VALUE`, `Double.NaN`, `Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY`. Với thuật toán tích lũy, kiểm tra dãy số có chênh lệch độ lớn lớn và các thứ tự cộng khác nhau. Với serialization, kiểm tra contract định dạng ngoài có chấp nhận hoặc từ chối số thực đặc biệt như mong đợi.

## 11. Tự kiểm tra kiến thức

**Câu 1.** Vì sao `Double.NaN == Double.NaN` là `false` nhưng `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` là `true`?

**Đáp án:** Toán tử `==` trên primitive dùng quan hệ so sánh số học của IEEE 754, trong đó NaN unordered; wrapper `Double.equals` dùng quan hệ tương đương biểu diễn, chuẩn hóa các NaN thành cùng một lớp cho contract equals.

**Câu 2.** `+0.0 == -0.0` là `true`, vậy `1.0 / +0.0` và `1.0 / -0.0` có bằng nhau không?

**Đáp án:** Không. Kết quả là `+Infinity` và `-Infinity`. Số không có dấu khác nhau trong biểu diễn dù được `==` xem bằng nhau.

**Câu 3.** Khi nào `Double.isNaN(x)` là chưa đủ để bảo vệ hàm chỉ chấp nhận số hữu hạn?

**Đáp án:** Khi đầu vào là `Infinity` hoặc `-Infinity`; hai giá trị này không phải NaN. Dùng `Double.isFinite(x)`.

**Câu 4.** Vì sao `(a + b) + c` đôi khi khác `a + (b + c)` dù Java 17+ có ngữ nghĩa dấu phẩy động luôn strict?

**Đáp án:** Từng phép cộng có thể làm tròn về giá trị biểu diễn được. Đổi thứ tự nhóm thay đổi các bước làm tròn; strict bảo đảm quy tắc thực hiện phép toán, không biến số học dấu phẩy động thành phép toán kết hợp.

**Câu 5.** Với `Double.compare`, vị trí NaN và hai số không là gì?

**Đáp án:** `-0.0` nhỏ hơn `+0.0`, và NaN được đặt **lớn hơn mọi số khác**, kể cả vô cực dương.

**Câu 6.** `Double.MIN_VALUE` có phải giá trị âm nhỏ nhất không?

**Đáp án:** Không. Đó là giá trị **dương khác 0 nhỏ nhất** ở dạng subnormal. Giá trị âm hữu hạn xa 0 nhất theo trị tuyệt đối là `-Double.MAX_VALUE`.

**Câu 7.** Nếu cần cộng tiền `0.1` và `0.2` để nhận chính xác `0.3` theo hệ thập phân, nên dùng gì?

**Đáp án:** Dùng `BigDecimal` được tạo từ chuỗi `"0.1"` và `"0.2"` hoặc nguồn thập phân chính xác, cùng quy tắc làm tròn/scale được thiết kế cho nghiệp vụ.

## 12. Bản đồ ghi nhớ

~~~text
float   = IEEE 754 binary32  → 1 dấu + 8 số mũ + 23 fraction
double  = IEEE 754 binary64  → 1 dấu + 11 số mũ + 52 fraction

Giá trị:  hữu hạn | subnormal | +0.0 / -0.0 | ±Infinity | NaN

Toán tử == : +0.0 == -0.0       ; NaN != NaN
Double.equals/compare: phân biệt ±0.0 ; gom mọi NaN vào cùng lớp
Raw bits   : có thể quan sát dấu 0 và payload NaN
isFinite   : loại NaN và ±Infinity

Java 17+ luôn strict, nhưng thay thứ tự cộng vẫn có thể đổi kết quả.
~~~

**Điểm cốt lõi:** số thực IEEE 754 không phải số thực toán học có độ chính xác vô hạn. **NaN** biểu diễn kết quả không xác định, **vô cực** xử lý độ lớn vượt giới hạn và một số phép toán đặc biệt, **±0.0** giữ thông tin dấu; muốn tính nhất quán phải chọn đúng ngữ nghĩa so sánh, biết quy tắc làm tròn và kiểm soát thứ tự/phạm vi phép tính.

## Tài liệu chuẩn

- [Java Language Specification 21 — §4.2.3 Floating-Point Types and Values](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.2.3).
- [Java Language Specification 21 — §15.4 Floating-point Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.4).
- [Java SE 21 API — java.lang.Double](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html).
- [OpenJDK JEP 306 — Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306).
