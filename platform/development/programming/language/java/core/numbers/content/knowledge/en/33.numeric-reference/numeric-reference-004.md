# Bảng tra cứu: NaN, signed zero, equals và compare trong Java

## 1. Mục tiêu: phân biệt bốn khái niệm “bằng nhau”

Trong Java, các kiểu dấu phẩy động `float` và `double` tuân theo ngữ nghĩa IEEE 754 được Java quy định. Một số giá trị đặc biệt có cách so sánh khác trực giác số học thông thường:

- **NaN (Not a Number)**: giá trị đặc biệt biểu thị kết quả không xác định theo phép toán floating-point, ví dụ `0.0 / 0.0`.
- **Signed zero**: có cả `+0.0` và `-0.0`. Hai giá trị bằng nhau qua toán tử số học `==`, nhưng không giống nhau ở mọi thao tác, ví dụ `1.0 / +0.0` và `1.0 / -0.0`.
- **`==`, `!=`, `<`, `>`, `<=`, `>=` trên primitive**: áp dụng quy tắc **so sánh số học**, trong đó NaN không được xem là bằng bất kỳ số nào, kể cả chính nó.
- **`Double.equals` / `Float.equals` và `Double.compare` / `Float.compare`**: sử dụng **quy tắc bình đẳng và thứ tự dành cho wrapper**, được thiết kế nhất quán để dùng làm khóa trong collection và sắp xếp.

Vì vậy, cùng nhìn vào hai giá trị `double` mà lựa chọn API khác nhau có thể cho kết quả khác nhau. Đây không phải lỗi của Java; đó là những **hợp đồng so sánh khác nhau**.

Bài này là bảng tra cứu cho Java 17+, kèm ví dụ chạy độc lập, các trường hợp NaN với payload khác nhau, signed zero, hash/sorted collections và cách chọn phép so sánh theo bài toán.

## 2. Bảng nhanh: toán tử primitive và wrapper

Giả sử:

~~~java
double nan = Double.NaN;
double positiveZero = 0.0;
double negativeZero = -0.0;
~~~

Đây là các khai báo **trong thân một phương thức**; chương trình hoàn chỉnh nằm ở phần 8.

| Phép kiểm tra | Kết quả Java | Lý do |
|---|---|---|
| `Double.NaN == Double.NaN` | `false` | NaN không bằng bất kỳ giá trị nào bằng primitive `==` |
| `Double.NaN != Double.NaN` | `true` | Phép `!=` có kết quả true nếu có NaN |
| `Double.NaN < 1.0` | `false` | Quan hệ thứ tự primitive với NaN là unordered |
| `Double.NaN > 1.0` | `false` | Tương tự |
| `Double.NaN <= 1.0` | `false` | Tương tự |
| `Double.NaN >= 1.0` | `false` | Tương tự |
| `Double.NaN == Double.POSITIVE_INFINITY` | `false` | Infinity là giá trị riêng, không phải NaN |
| `0.0 == -0.0` | `true` | Hai zero bằng nhau theo so sánh số học |
| `0.0 < -0.0` | `false` | Không có chênh lệch giá trị số học |
| `0.0 > -0.0` | `false` | Tương tự |
| `Double.valueOf(nan).equals(Double.valueOf(nan))` | `true` | Wrapper xem các NaN là bằng nhau |
| `Double.valueOf(-0.0).equals(Double.valueOf(0.0))` | `false` | Wrapper phân biệt bit dấu của zero |
| `Double.compare(nan, nan)` | `0` | Hai NaN cùng vị trí trong thứ tự wrapper |
| `Double.compare(nan, Double.POSITIVE_INFINITY)` | Số dương (`1` ở JDK 17) | NaN xếp **sau** mọi giá trị số, kể cả +Infinity |
| `Double.compare(-0.0, +0.0)` | Số âm (`-1` ở JDK 17) | `-0.0` xếp trước `+0.0` |
| `Double.compare(+0.0, -0.0)` | Số dương (`1` ở JDK 17) | `+0.0` xếp sau `-0.0` |

**Mẹo nhớ:** nếu cần so sánh giá trị dấu phẩy động theo toán tử số học, `==` và `<` có quy tắc về NaN/zero riêng. Nếu cần một **thứ tự toàn phần để sắp xếp**, `Double.compare` và `Float.compare` là API phù hợp.

Các ví dụ trong bảng dùng `Double.NaN` kiểu primitive `double`, không phải đối tượng `Double`. Sự khác nhau giữa primitive và wrapper trở nên rõ trong những đoạn tiếp theo.

## 3. NaN và toán tử primitive

NaN có thể hình thành từ phép toán dấu phẩy động không xác định:

~~~java
double undefined = 0.0 / 0.0;
double infinity = 1.0 / 0.0;

System.out.println(undefined); // NaN
System.out.println(infinity);  // Infinity
~~~

Không nên suy luận NaN như một số lớn hoặc nhỏ. Khi ít nhất một toán hạng là NaN:

- `==` trả `false`, kể cả khi biểu thức so sánh NaN với chính NaN.
- `!=` trả `true`.
- Các phép `<`, `<=`, `>`, `>=` đều trả `false`.
- Do đó hai điều kiện `!(a < b)` và `a >= b` **không tương đương** khi có NaN: với `a = NaN`, `!(a < b)` là true trong khi `a >= b` false.

Ví dụ:

~~~java
double a = Double.NaN;
double b = 10.0;

System.out.println(a == a);  // false
System.out.println(a != a);  // true
System.out.println(a < b);   // false
System.out.println(a >= b);  // false
System.out.println(!(a < b)); // true
~~~

**Không phát hiện NaN bằng `x == Double.NaN`.** Điều kiện đó luôn false cho mọi giá trị x, kể cả NaN. Dùng:

~~~java
boolean invalid = Double.isNaN(a);
~~~

Với `float`, dùng `Float.isNaN(value)`. Nếu cần loại bỏ mọi giá trị không hữu hạn (cả NaN lẫn ±Infinity), dùng `Double.isFinite(value)` hoặc `Float.isFinite(value)` (có trong Java 17).

### Infinity không phải NaN

`Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY` là các giá trị có thứ tự số học:

~~~java
System.out.println(Double.NEGATIVE_INFINITY < -1e300); // true
System.out.println(Double.POSITIVE_INFINITY > 1e300);  // true
System.out.println(Double.isNaN(Double.POSITIVE_INFINITY)); // false
System.out.println(Double.isInfinite(Double.POSITIVE_INFINITY)); // true
~~~

Với kiểu `double`, phép chia `1.0 / 0.0` trả +Infinity và `-1.0 / 0.0` trả -Infinity theo quy tắc floating-point. Nhưng phép chia **số nguyên** `1 / 0` hoặc `int x / intZero` ném `ArithmeticException`; đừng gom hai trường hợp làm một.

Nếu dữ liệu nhập phải là số hữu hạn, việc kiểm tra `!Double.isNaN(x)` **chưa đủ**: Infinity không phải NaN. Quy tắc hữu ích:

~~~java
if (!Double.isFinite(x)) {
    throw new IllegalArgumentException("Value must be finite");
}
~~~

Đây là đoạn trong một method có biến `x` kiểu double.

## 4. Signed zero: vì sao 0.0 bằng -0.0 nhưng không hoàn toàn giống nhau?

IEEE 754 có hai biểu diễn zero:

- `+0.0`: bit dấu bằng 0.
- `-0.0`: bit dấu bằng 1.

Toán tử `==` trên primitive coi chúng **bằng nhau**, vì cùng giá trị zero theo phép so sánh số học:

~~~java
System.out.println(0.0 == -0.0); // true
System.out.println(-0.0 < +0.0);  // false
~~~

Nhưng trong một số phép toán, dấu zero ảnh hưởng kết quả:

~~~java
System.out.println(1.0 / +0.0); // Infinity
System.out.println(1.0 / -0.0); // -Infinity

System.out.println(Math.min(-0.0, +0.0)); // -0.0
System.out.println(Math.max(-0.0, +0.0)); // 0.0
~~~

`Math.min` và `Math.max` cho `double` có quy tắc dấu zero: `-0.0` được xem là nhỏ hơn `+0.0` khi hai đối số đều là zero khác dấu. Nếu một toán hạng là NaN, kết quả của hai hàm này là NaN theo API Java. Vì vậy đừng sử dụng min/max như một cách để **loại NaN** khỏi dữ liệu.

Biểu diễn chuỗi cũng có thể giữ dấu:

~~~java
System.out.println(Double.toString(-0.0)); // -0.0
System.out.println(Double.toString(+0.0)); // 0.0
~~~

Nếu bài toán chỉ cần biết hai giá trị số học có bằng nhau không, so sánh `+0.0 == -0.0` là true. Nếu bài toán có ý nghĩa phân biệt dấu zero (ví dụ kết quả tính 1/x, serialization theo bit, kiểm tra chính xác đầu ra), không được mặc định hai biểu diễn hoàn toàn thay thế cho nhau.

### Bit pattern của hai zero

~~~java
long positiveBits = Double.doubleToRawLongBits(+0.0);
long negativeBits = Double.doubleToRawLongBits(-0.0);
System.out.println(positiveBits == negativeBits); // false
~~~

Trên dạng IEEE 754 binary64 của Java, bit sign khác nhau. `Double.doubleToLongBits` cũng giữ sự khác nhau này cho ±0.0.

**Chú ý:** chữ “signed zero” không có nghĩa rằng `-0.0 < 0.0` trong mọi API. Toán tử primitive `<` trả false, nhưng `Double.compare(-0.0, +0.0) < 0` là true theo thứ tự wrapper được định nghĩa riêng.

## 5. Double.equals và Double.compare: khác toán tử == ra sao?

### 5.1. Double.equals

`Double.equals(Object)` so sánh hai **đối tượng Double** theo bit biểu diễn, với NaN được canonicalize. Kết quả khác so sánh primitive ở hai chỗ quan trọng:

| Cặp giá trị | Primitive `a == b` | `Double.valueOf(a).equals(Double.valueOf(b))` |
|---|---|---|
| `1.0` và `1.0` | true | true |
| `1.0` và `2.0` | false | false |
| `+0.0` và `-0.0` | **true** | **false** |
| `NaN` và `NaN` | **false** | **true** |
| `NaN` và `+Infinity` | false | false |
| `+Infinity` và `+Infinity` | true | true |
| `-Infinity` và `-Infinity` | true | true |

Định nghĩa này giúp `Double` dùng được với `equals`/`hashCode` trong `HashMap`, `HashSet` và các collection thông thường. Hai giá trị Double mà `equals` xem là bằng nhau có `hashCode` bằng nhau.

**Không dùng `==` để so sánh hai đối tượng `Double` nếu bạn cần equality giá trị.** Khi cả hai toán hạng là reference `Double`, toán tử `==` so sánh **tham chiếu**. Khi một bên bị unbox sang primitive, hành vi lại chuyển sang so sánh số học và có thể phát sinh `NullPointerException`.

~~~java
Double left = Double.valueOf(1.5);
Double right = Double.valueOf(1.5);

System.out.println(left.equals(right)); // true
// left == right: không dùng để suy ra value-equality.
~~~

Nếu hai reference `Double` có thể null, dùng `Objects.equals(left, right)` khi muốn quy tắc equality wrapper có xử lý null; nếu null không hợp lệ, kiểm tra đầu vào rồi dùng `left.equals(right)`. `Objects.equals` **không chuyển sang primitive `==`**, do đó vẫn phân biệt signed zero và coi NaN bằng NaN.

### 5.2. Double.compare và compareTo

`Double.compare(double a, double b)` và `Double.compareTo(Double other)` xây dựng **thứ tự toàn phần** để sắp xếp, cho phép đặt NaN vào một vị trí xác định:

~~~text
-Infinity < số âm hữu hạn < -0.0 < +0.0
          < số dương hữu hạn < +Infinity < NaN
~~~

Đó là thứ tự quan trọng nhất cần nhớ. Mọi NaN được đặt bằng nhau **theo compare**, dù có payload bit khác nhau. Dù có kết quả là số âm/0/số dương, không nên viết điều kiện dựa trên `compare(...) == -1` hay `== 1`; hợp đồng của các API compare nói chung chỉ yêu cầu dấu, dùng `< 0`, `== 0`, `> 0`.

Ví dụ:

~~~java
System.out.println(Double.compare(-0.0, +0.0)); // -1
System.out.println(Double.compare(+0.0, -0.0)); // 1
System.out.println(Double.compare(Double.NaN, Double.NaN)); // 0
System.out.println(Double.compare(
        Double.NaN, Double.POSITIVE_INFINITY)); // 1
~~~

**Quy tắc bao trùm:** với hai giá trị primitive double a, b (kể cả NaN, ±0.0), biểu thức `Double.compare(a,b) == 0` nhất quán với `Double.valueOf(a).equals(Double.valueOf(b))`. Nhưng chúng **không nhất quán với primitive `a == b`** tại NaN và signed zero.

### 5.3. Float có quy tắc tương ứng

`Float.equals`, `Float.compare` và `Float.compareTo` tuân theo cách xử lý NaN và signed zero tương tự, nhưng trên bit-width **binary32**, khác độ chính xác và miền giá trị `double` (binary64).

~~~java
System.out.println(Float.NaN == Float.NaN); // false
System.out.println(Float.compare(Float.NaN, Float.NaN)); // 0
System.out.println(Float.compare(-0.0f, +0.0f)); // -1
System.out.println(Float.valueOf(-0.0f).equals(+0.0f)); // false
~~~

Nếu đối tượng wrapper khác lớp, `Double.valueOf(1.0).equals(Float.valueOf(1.0f))` là **false**: `Double.equals` chỉ nhận đối tượng kiểu Double, không tự quy đổi Float sang Double để so sánh.

## 6. Bảng lựa chọn API theo mục đích

| Mục đích | Cách nên chọn | Ý nghĩa cần nắm |
|---|---|---|
| Kiểm tra hai primitive bằng nhau theo phép toán dấu phẩy động | `a == b` | NaN khác mọi giá trị, ±0.0 bằng nhau |
| Kiểm tra hai primitive khác nhau | `a != b` | True khi một bên NaN, kể cả hai bên NaN |
| Loại bỏ NaN | `Double.isNaN(a)` | Không dùng `a == Double.NaN` |
| Từ chối cả NaN và Infinity | `Double.isFinite(a)` | Hữu hạn mới được chấp nhận |
| Kiểm tra wrapper value-equality | `Double.valueOf(a).equals(Double.valueOf(b))` | NaN bằng NaN, ±0.0 khác nhau |
| Kiểm tra wrapper với khả năng null | `Objects.equals(left, right)` | Áp dụng equals của wrapper, null-safe |
| Sắp xếp một cột double | `Double.compare(a,b)` | Thứ tự tổng thể, NaN sau +Infinity |
| So sánh theo hợp đồng SortedSet/SortedMap dùng Double | `Double.compare` hoặc thứ tự tự nhiên | Trùng khóa khi compare == 0 |
| Phân biệt raw bit/payload của NaN | `Double.doubleToRawLongBits(x)` | Không dùng equals/compare để giữ payload |
| Kiểm tra giá trị gần bằng theo dung sai | Một predicate riêng với sai số rõ ràng | Không biến thành equals/hashCode/order |
| Sắp xếp theo “NaN trước” hoặc “NaN là missing” | Comparator/policy riêng | Phải giữ thứ tự bắc cầu và nhất quán |
| Tính toán tiền/độ chính xác thập phân | BigDecimal hoặc đơn vị nguyên | Không kỳ vọng primitive double luôn chính xác |

Đối với dữ liệu đầu vào bên ngoài, việc định nghĩa **chính sách NaN/Infinity** trước khi so sánh quan trọng hơn chọn đúng một toán tử. Ví dụ khi giá trị NaN nghĩa là “không đo được”, nghiệp vụ có thể muốn từ chối, đưa cuối danh sách hoặc xử lý thiếu dữ liệu; những chính sách này là khác nhau.

## 7. NaN payload, bit chuẩn hóa và hashCode

NaN không chỉ có một raw bit pattern duy nhất. Trong biểu diễn IEEE 754 có nhiều cách biểu diễn NaN khác nhau; Java cho phép quan sát raw bits từ một giá trị `double` bằng:

~~~java
long raw = Double.doubleToRawLongBits(value);
~~~

Một phương thức khác:

~~~java
long normalized = Double.doubleToLongBits(value);
~~~

`Double.doubleToLongBits` **canonicalize các NaN**: mọi NaN cho cùng mẫu bit NaN chuẩn khi gọi phương thức này. `Double.equals` sử dụng ngữ nghĩa tương thích với kết quả `doubleToLongBits`, nhờ vậy **hai NaN khác raw payload vẫn equal**. `Double.hashCode` cũng thống nhất với equality này.

Ví dụ hai payload khác nhau:

~~~java
double a = Double.longBitsToDouble(0x7ff8000000000001L);
double b = Double.longBitsToDouble(0x7ff8000000000002L);

System.out.println(Double.isNaN(a) && Double.isNaN(b)); // true
System.out.println(Double.doubleToRawLongBits(a)
        != Double.doubleToRawLongBits(b)); // true
System.out.println(Double.valueOf(a).equals(b)); // true
System.out.println(Double.compare(a, b));        // 0
~~~

Các raw bit pattern trên được tạo và đọc trong cùng chương trình Java 17 theo API. Tuy vậy, **đừng dùng payload NaN như kênh lưu metadata lâu dài** mà không có hợp đồng serialization và platform rõ ràng: các phép toán hay đường truyền/định dạng có thể canonicalize hoặc không bảo toàn raw payload. Nếu cần lưu **chính xác bit**, làm việc trực tiếp với raw bit integer theo format cụ thể, không dựa vào phép toán trên double.

`Double.doubleToRawLongBits` và `Double.doubleToLongBits` đều giữ được khác biệt raw signed-zero:

~~~java
System.out.println(
    Double.doubleToLongBits(-0.0)
        == Double.doubleToLongBits(+0.0)); // false
~~~

Với `Float` có cặp API tương ứng `Float.floatToRawIntBits` và `Float.floatToIntBits`. Khi số là NaN, `Float.floatToIntBits` canonicalize tương tự.

## 8. Chương trình Java 17+ hoàn chỉnh và output chính xác

Lưu file **`FloatingCompareTableDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.TreeSet;
import java.util.Set;

public class FloatingCompareTableDemo {
    public static void main(String[] args) {
        double nan = Double.NaN;
        double posZero = 0.0d;
        double negZero = -0.0d;

        System.out.println("primitive NaN == NaN: " + (nan == nan));
        System.out.println("primitive NaN != NaN: " + (nan != nan));
        System.out.println("primitive NaN < 1.0: " + (nan < 1.0));
        System.out.println("primitive NaN >= 1.0: " + (nan >= 1.0));
        System.out.println("primitive -0.0 == +0.0: "
                + (negZero == posZero));

        System.out.println("Double.equals(NaN, NaN): " +
                Double.valueOf(nan).equals(Double.valueOf(nan)));
        System.out.println("Double.compare(NaN, NaN): " +
                Double.compare(nan, nan));
        System.out.println("Double.compare(NaN, +Infinity): " +
                Double.compare(nan, Double.POSITIVE_INFINITY));
        System.out.println("Double.equals(-0.0, +0.0): " +
                Double.valueOf(negZero).equals(Double.valueOf(posZero)));
        System.out.println("Double.compare(-0.0, +0.0): " +
                Double.compare(negZero, posZero));
        System.out.println("Double.compare(+0.0, -0.0): " +
                Double.compare(posZero, negZero));

        System.out.println("1.0 / +0.0: " + (1.0 / posZero));
        System.out.println("1.0 / -0.0: " + (1.0 / negZero));
        System.out.println("Math.min(-0.0, +0.0): " +
                Math.min(negZero, posZero));
        System.out.println("Math.max(-0.0, +0.0): " +
                Math.max(negZero, posZero));

        System.out.println("isNaN(NaN): " + Double.isNaN(nan));
        System.out.println("isFinite(+Infinity): " +
                Double.isFinite(Double.POSITIVE_INFINITY));

        double nanPayloadA =
                Double.longBitsToDouble(0x7ff8000000000001L);
        double nanPayloadB =
                Double.longBitsToDouble(0x7ff8000000000002L);

        System.out.println("NaN raw bit patterns differ: " +
                (Double.doubleToRawLongBits(nanPayloadA)
                 != Double.doubleToRawLongBits(nanPayloadB)));
        System.out.println("NaN wrapper equality: " +
                Double.valueOf(nanPayloadA).equals(nanPayloadB));
        System.out.println("NaN wrapper hash codes equal: " +
                (Double.hashCode(nanPayloadA)
                 == Double.hashCode(nanPayloadB)));

        Set<Double> hashSet = new HashSet<>(Arrays.asList(
                -0.0, +0.0, Double.NaN, nanPayloadA, nanPayloadB));
        Set<Double> treeSet = new TreeSet<>(Arrays.asList(
                -0.0, +0.0, Double.NaN, nanPayloadA, nanPayloadB));

        System.out.println("HashSet size: " + hashSet.size());
        System.out.println("TreeSet size: " + treeSet.size());
        System.out.println("Sorted values: " + treeSet);

        System.out.println("Float NaN == NaN: "
                + (Float.NaN == Float.NaN));
        System.out.println("Float.compare(NaN, NaN): "
                + Float.compare(Float.NaN, Float.NaN));
        System.out.println("Float.compare(-0.0f, +0.0f): "
                + Float.compare(-0.0f, +0.0f));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FloatingCompareTableDemo.java
java FloatingCompareTableDemo
~~~

**Kết quả stdout đã kiểm chứng trên Java 17:**

~~~text
primitive NaN == NaN: false
primitive NaN != NaN: true
primitive NaN < 1.0: false
primitive NaN >= 1.0: false
primitive -0.0 == +0.0: true
Double.equals(NaN, NaN): true
Double.compare(NaN, NaN): 0
Double.compare(NaN, +Infinity): 1
Double.equals(-0.0, +0.0): false
Double.compare(-0.0, +0.0): -1
Double.compare(+0.0, -0.0): 1
1.0 / +0.0: Infinity
1.0 / -0.0: -Infinity
Math.min(-0.0, +0.0): -0.0
Math.max(-0.0, +0.0): 0.0
isNaN(NaN): true
isFinite(+Infinity): false
NaN raw bit patterns differ: true
NaN wrapper equality: true
NaN wrapper hash codes equal: true
HashSet size: 3
TreeSet size: 3
Sorted values: [-0.0, 0.0, NaN]
Float NaN == NaN: false
Float.compare(NaN, NaN): 0
Float.compare(-0.0f, +0.0f): -1
~~~

Chương trình không dùng số ngẫu nhiên, nên các kết quả không phụ thuộc lịch chạy. Các mã bit payload NaN được tạo tường minh, còn `TreeSet` in theo thứ tự tự nhiên của `Double`; `HashSet` chỉ in **size**, không dựa vào thứ tự duyệt không được bảo đảm.

## 9. Collection: HashSet, TreeSet, HashMap, TreeMap

Hai loại collection sử dụng hai hợp đồng khác nhau:

- `HashSet<Double>` / `HashMap<Double,...>` dùng `Double.equals` và `Double.hashCode` để xác định khóa trùng.
- `TreeSet<Double>` / `TreeMap<Double,...>` dùng `Double.compareTo` hoặc `Comparator` được cung cấp; với thứ tự tự nhiên, comparator trả 0 thì được xem là cùng vị trí khóa.

May mắn là `Double.compareTo` **nhất quán với `Double.equals`**, kể cả NaN và signed zero, nên với giá trị Double thuần túy, hai loại cấu trúc cùng phân biệt hai zero và gộp tất cả NaN thành một khóa theo khái niệm equality tương ứng.

| Dữ liệu thêm vào | HashSet kích thước | TreeSet kích thước tự nhiên | Giải thích |
|---|---:|---:|---|
| `+0.0`, `-0.0` | 2 | 2 | Hai zero không equal theo wrapper và compare khác 0 |
| `NaN`, `NaN` | 1 | 1 | NaN wrapper equal và compare = 0 |
| Hai NaN raw payload khác nhau | 1 | 1 | Payload bị canonicalize trong equality |
| `-0.0`, `+0.0`, ba NaN | 3 | 3 | Có ba nhóm khóa theo wrapper |
| `1.0`, `1.0` | 1 | 1 | Trùng nhau hoàn toàn |

**Không áp dụng quy tắc primitive `==` để đoán hành vi `HashSet<Double>`.** Nếu `NaN == NaN` false mà collection vẫn gộp NaN, đó là do collection dùng wrapper `equals` chứ không dùng primitive `==`.

Ví dụ tra cứu Map:

~~~java
Map<Double, String> map = new HashMap<>();
map.put(Double.NaN, "missing");
map.put(-0.0, "negative");
map.put(+0.0, "positive");

System.out.println(map.size());             // 3
System.out.println(map.get(Double.NaN));    // missing
System.out.println(map.get(-0.0));          // negative
System.out.println(map.get(+0.0));          // positive
~~~

Đây là code **trong method**, cần import `java.util.Map` và `java.util.HashMap`. Nếu dùng `TreeMap` với thứ tự tự nhiên của `Double`, cấu trúc vẫn phân biệt hai zero và coi các NaN là cùng khóa.

**Cẩn thận comparator tùy biến**: nếu thay comparator bằng một quy tắc mà `compare(a,b) == 0` trong khi `!a.equals(b)`, ý nghĩa trùng khóa của TreeSet/TreeMap khác HashSet/HashMap. Điều này có thể là lựa chọn có chủ đích, nhưng phải được tài liệu hóa và kiểm thử.

## 10. Sắp xếp dữ liệu có NaN: ba chính sách hay gặp

### Chính sách A — Giữ thứ tự tự nhiên Java

Dùng `Double.compare`, `Comparator.comparingDouble`, `Arrays.sort(double[])` hoặc `DoubleStream.sorted()` tùy cấu trúc dữ liệu. NaN đứng cuối, signed zero được phân biệt thứ tự:

~~~java
double[] values = {
    Double.NaN, 0.0, -0.0,
    Double.POSITIVE_INFINITY, -3.0, Double.NEGATIVE_INFINITY
};
java.util.Arrays.sort(values);
System.out.println(java.util.Arrays.toString(values));
// [-Infinity, -3.0, -0.0, 0.0, Infinity, NaN]
~~~

Đoạn trên nằm trong phương thức. Chính sách này tiện để sort, nhưng **không đồng nghĩa NaN là “số lớn nhất” theo toán học**; nó chỉ có vị trí quy ước trong thứ tự wrapper.

### Chính sách B — Từ chối NaN và vô cực

Nếu cột chứa dữ liệu kinh doanh bắt buộc hữu hạn, kiểm tra trước:

~~~java
static double requireFinite(double x) {
    if (!Double.isFinite(x)) {
        throw new IllegalArgumentException("Expected finite double");
    }
    return x;
}
~~~

Đây là method trong class. Khi đã từ chối NaN/Infinity, logic xử lý bớt nhiều trường hợp bất ngờ. Nhưng signed zero vẫn có thể tồn tại nếu API cho phép; quyết định có normalize ±0.0 hay không theo yêu cầu dữ liệu.

### Chính sách C — NaN là dữ liệu thiếu

Nếu NaN đại diện “không có kết quả đo”, có thể tách thành **trạng thái thiếu dữ liệu** bằng một kiểu mô hình rõ ràng, thay vì dựa vào một giá trị double có tính chất so sánh đặc biệt. Khi sắp xếp, ứng dụng phải định nghĩa “thiếu” đứng trước/sau và có được tính vào thống kê hay không.

Nếu chọn custom comparator, nó phải tuân theo hợp đồng `Comparator` (phản đối xứng về dấu, bắc cầu, nhất quán). Đừng đặt một so sánh “gần bằng theo epsilon” làm comparator rồi dùng `TreeSet`: quan hệ gần bằng có thể không bắc cầu, khiến sorted collection hoạt động không đáng tin.

## 11. So sánh “gần bằng”: khác equality và khác NaN handling

Với số thực, hai công thức toán học tương đương có thể cho kết quả hơi khác do sai số làm tròn. Nhiều bài toán cần kiểm tra dung sai:

~~~java
static boolean approximatelyEqual(double a, double b, double epsilon) {
    if (!Double.isFinite(a) || !Double.isFinite(b)
            || !Double.isFinite(epsilon) || epsilon < 0.0) {
        return false;
    }
    return Math.abs(a - b) <= epsilon;
}
~~~

Đây là **predicate minh họa** với chính sách từ chối NaN/Infinity. Nó cũng có giới hạn: phép trừ `a - b` có thể overflow thành Infinity khi a/b ở biên rất lớn, kể cả khi riêng a và b hữu hạn; điều này cần được thiết kế và kiểm thử nếu dùng cho phạm vi floating cực đoan. Dung sai tuyệt đối chỉ phù hợp khi đơn vị và quy mô dữ liệu hợp lý; đôi khi cần dung sai tương đối hoặc kết hợp hai loại.

Điểm quan trọng:

- `Double.compare(a,b) == 0` **không phải kiểm tra gần bằng**.
- `a == b` trên primitive **không phải kiểm tra gần bằng**.
- Với NaN, predicate trên trả false chủ động, thay vì trông vào một quy tắc suy diễn.
- Với ±0.0, `Math.abs(a-b) <= epsilon` trả true khi epsilon ≥ 0; đó là quyết định **nghiệp vụ của predicate**, khác wrapper equality.
- Không override `equals`/`hashCode` chỉ vì một phép tính cần sai số dung sai.

Ví dụ không bắc cầu: A = 0.00, B = 0.09, C = 0.18 và epsilon = 0.10. A gần B, B gần C, nhưng A không gần C. Vì vậy quan hệ này **không thể** thay cho equality dùng làm khóa HashMap hoặc thứ tự comparator một cách trực tiếp.

## 12. Bẫy về ép kiểu, boxing, null và BigDecimal

### 12.1. primitive và wrapper không luôn so sánh cùng cách

~~~java
Double obj = Double.valueOf(Double.NaN);
double raw = Double.NaN;

System.out.println(obj.equals(Double.valueOf(raw))); // true
System.out.println(obj.doubleValue() == raw);         // false
~~~

`obj.equals` sử dụng wrapper equality; `obj.doubleValue() == raw` dùng primitive `==`. Nếu `obj` null, `obj.doubleValue()` ném `NullPointerException`.

Trong generic collections như `List<Double>`, các phần tử thường được boxing thành Double; các thao tác `contains` và `remove(Object)` áp dụng `equals`, không phải primitive `==`. Do đó `list.contains(Double.NaN)` có thể true ngay cả khi `Double.NaN == Double.NaN` false.

### 12.2. Float và Double không equal chỉ vì số nhìn giống nhau

~~~java
Object a = Double.valueOf(1.0);
Object b = Float.valueOf(1.0f);
System.out.println(a.equals(b)); // false
~~~

Đó là hai lớp wrapper khác nhau. Nếu cần chuyển đổi kiểu để so sánh số học, phải xác định phép chuyển kiểu và vấn đề precision. Với số lớn, chuyển long sang double có thể mất chính xác; không tự ép mọi kiểu sang double rồi kết luận hai giá trị giống nhau.

### 12.3. BigDecimal có hợp đồng hoàn toàn khác

`BigDecimal` không có NaN hay ±Infinity như các primitive floating. Ngoài ra, `BigDecimal.equals` kiểm tra cả **giá trị và scale**, trong khi `BigDecimal.compareTo` so sánh theo giá trị số:

~~~java
java.math.BigDecimal x = new java.math.BigDecimal("2.0");
java.math.BigDecimal y = new java.math.BigDecimal("2.00");
System.out.println(x.equals(y));      // false
System.out.println(x.compareTo(y));   // 0
~~~

Đây chỉ là **đối chiếu để không nhầm hợp đồng**, không phải quy tắc NaN/signed zero của Double. `BigDecimal.valueOf(Double.NaN)` không tạo một giá trị BigDecimal NaN hợp lệ: nó ném `NumberFormatException`. Nếu chuyển dữ liệu floating sang BigDecimal, cần xử lý NaN/Infinity trước và cân nhắc signed zero vì biểu diễn thập phân không giữ cùng ngữ nghĩa dấu zero như double.

## 13. Checklist khi review lỗi so sánh floating-point

1. **Biến thực sự là primitive hay wrapper?** `==` giữa hai reference wrapper kiểm tra identity; `==` trên primitive hoặc có unboxing kiểm tra giá trị floating.
2. **Dữ liệu có thể chứa NaN?** Nếu có, so sánh primitive bất đẳng thức có thể đều false, còn `!=` true. Sử dụng `isNaN` khi cần phát hiện.
3. **Có thể chứa Infinity?** `isNaN` không chặn Infinity; nếu cần giá trị hữu hạn, `isFinite`.
4. **Signed zero có ý nghĩa không?** Nếu cần giữ khác biệt dấu, dùng wrapper equality, `Double.compare` hoặc bit API; nếu chỉ cần zero số học, primitive `==` xem chúng như nhau.
5. **Đang sort hay dùng SortedSet?** Chọn `Double.compare` hoặc comparator hợp đồng rõ; không đưa `(a,b) -> a < b ? -1 : (a > b ? 1 : 0)` vào TreeSet khi có NaN vì nó coi NaN bằng tất cả giá trị và có thể vi phạm tính nhất quán.
6. **Đang dùng HashMap/HashSet?** Phải suy luận từ `Double.equals/hashCode`, không phải primitive `==`.
7. **Cần nhận biết payload của NaN?** Dùng `doubleToRawLongBits` và giao thức lưu bit rõ ràng.
8. **Cần kiểm tra gần bằng?** Viết predicate cục bộ có yêu cầu dung sai; không thay đổi global equals và không dùng làm sorted comparator tùy tiện.
9. **Đang chuyển kiểu?** Có thể mất precision hoặc làm mất trạng thái không hữu hạn; không coi cast là bước trung tính.
10. **Định nghĩa nghiệp vụ khi thiếu dữ liệu?** “NaN = missing” là một chính sách, không được tự suy từ thứ tự Double.compare.

### Các câu hỏi kiểm thử tối thiểu

- `Double.NaN == Double.NaN` có false không?
- `Double.isNaN(Double.NaN)` có true không?
- `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` có true không?
- `Double.compare(Double.NaN, Double.POSITIVE_INFINITY) > 0` có true không?
- `+0.0 == -0.0` có true không?
- `Double.compare(-0.0,+0.0) < 0` có true không?
- `Double.valueOf(-0.0).equals(Double.valueOf(+0.0))` có false không?
- `1.0/-0.0` có -Infinity không?
- Một HashSet<Double> nhận 2 zero khác dấu và 3 NaN có size = 3 không?
- Một TreeSet<Double> với dữ liệu đó có đúng `[-0.0, 0.0, NaN]` theo thứ tự tự nhiên không?

## 14. Bài tập và đáp án

**Bài 1.** Dự đoán kết quả của các biểu thức sau, nêu rõ primitive hay wrapper:

~~~java
double a = Double.NaN;
System.out.println(a == a);
System.out.println(Double.compare(a, a) == 0);
System.out.println(Double.valueOf(a).equals(a));
~~~

**Bài 2.** Vì sao `0.0 == -0.0` là true nhưng `Double.valueOf(0.0).equals(-0.0)` là false? Nêu một phép toán làm lộ sự khác biệt.

**Bài 3.** Dự đoán tập sau khi sắp xếp bằng `TreeSet<Double>` với `-0.0`, `+0.0`, `Double.NaN`, `Double.POSITIVE_INFINITY`. Vì sao NaN ở cuối?

**Bài 4.** Bạn nhận số đo sensor có thể trả NaN và Infinity. Đề xuất quy tắc kiểm tra trước khi tính trung bình và trước khi lưu vào database.

**Bài 5.** Hai NaN có raw payload khác nhau. `Double.equals` và `Double.compare` trả gì? Cần API nào để giữ được sự khác nhau của raw bit?

**Bài 6.** Một comparator viết:

~~~java
Comparator<Double> bad = (x, y) -> x < y ? -1 : x > y ? 1 : 0;
~~~

Tại sao không nên dùng `bad` với giá trị có NaN trong `TreeSet`? Đề xuất thay thế.

**Đáp án:**

1. `false`, `true`, `true`. Trong biểu thức thứ ba, `Double.equals(Object)` nhận tham số `a` được boxing sang Double, nên NaN bằng NaN.
2. Primitive equality coi hai zero bằng số học; wrapper phân biệt bit dấu. `1.0 / -0.0` cho -Infinity, khác +Infinity của `1.0 / +0.0`.
3. `[-0.0, 0.0, Infinity, NaN]` theo thứ tự Double.compare; NaN được đặt sau mọi giá trị số.
4. Nếu nghiệp vụ chỉ chấp nhận số hữu hạn, dùng `Double.isFinite(x)` để từ chối cả NaN và ±Infinity; xác định riêng quy tắc thiếu dữ liệu và đảm bảo dữ liệu được kiểm tra trước khi lưu/tính.
5. `Double.equals` true và `Double.compare` trả 0; dùng `Double.doubleToRawLongBits` để phân biệt raw payload khi cần.
6. Comparator đó trả 0 giữa NaN và nhiều giá trị khác nhau, không tạo thứ tự phù hợp. Dùng `Double::compare` hoặc comparator tùy biến có xử lý NaN rõ và giữ các tính chất thứ tự.

## 15. Tài liệu Java 17

- Java SE 17 — `Double` (`equals`, `compare`, `compareTo`, `isNaN`, `doubleToLongBits`, `doubleToRawLongBits`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html
- Java SE 17 — `Float`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html
- Java SE 17 — `Math.min`/`max`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html
- Java SE 17 — `Comparator`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html
- Java Language Specification 17 — `15.20.1 Numerical Comparison Operators` và `15.21.1 Numerical Equality Operators`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html
- Java SE 17 — `TreeSet` và `HashSet`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html

**Ghi nhớ:** với primitive, **NaN không bằng NaN** và **+0.0 bằng -0.0**. Với `Double.equals` và `Double.compare`, hai quy tắc ấy **đảo lại ở hai điểm đặc biệt**: mọi NaN được xem là bằng nhau và signed zero được phân biệt. Hãy chọn API theo đúng nhu cầu: số học, hash key, sắp xếp hay bảo toàn raw bits.
