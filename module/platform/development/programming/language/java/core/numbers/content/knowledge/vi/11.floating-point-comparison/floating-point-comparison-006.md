# `equals()` của `Float`, `Double` với `NaN` và signed zero trong Java

## 1. Vì sao cùng là so sánh số thực mà cho kết quả khác nhau?

Trong Java, `float` và `double` là **kiểu nguyên thủy** (*primitive*), còn `Float` và `Double` là **lớp bao** (*wrapper*) tương ứng. Toán tử `==` trên các giá trị nguyên thủy tuân theo quy tắc so sánh số thực IEEE 754; phương thức `Float.equals(Object)` và `Double.equals(Object)` lại có một hợp đồng riêng, phù hợp với `Object.equals` và các collection của Java.

Hai trường hợp dễ nhầm nhất là **NaN** (*Not a Number*) và **signed zero** (số không có dấu: `+0.0`, `-0.0`):

```java
double positiveZero = +0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero); // true
System.out.println(Double.valueOf(positiveZero)
        .equals(Double.valueOf(negativeZero)));    // false

System.out.println(Double.NaN == Double.NaN); // false
System.out.println(Double.valueOf(Double.NaN)
        .equals(Double.valueOf(Double.NaN))); // true
```

**Đây không phải mâu thuẫn hay lỗi Java**. Hai cơ chế định nghĩa khái niệm “bằng nhau” phục vụ những mục đích khác nhau:

- **So sánh số học bằng `==`:** `NaN` không bằng bất kỳ giá trị nào, kể cả chính nó; `+0.0` và `-0.0` bằng nhau về mặt số học.
- **So sánh `equals` của lớp bao:** tất cả các giá trị `NaN` của cùng kiểu lớp bao được coi là bằng nhau; `+0.0` và `-0.0` **không** bằng nhau.

Các quy tắc trên áp dụng đối xứng cho `Float`/`float` và `Double`/`double` với đúng độ rộng của từng kiểu.

## 2. Hiểu `NaN` và hai mẫu bit của số không

### `NaN` là gì?

`NaN` biểu thị kết quả không phải một số thực hợp lệ trong số học dấu phẩy động, ví dụ:

```java
double invalid = 0.0 / 0.0;
float invalidFloat = 0.0f / 0.0f;

System.out.println(Double.isNaN(invalid)); // true
System.out.println(Float.isNaN(invalidFloat)); // true
```

Theo quy tắc so sánh số thực nguyên thủy, nếu một toán hạng là `NaN`:

- `x == y` cho `false`, kể cả `NaN == NaN`.
- `x != y` cho `true`.
- `x < y`, `x <= y`, `x > y`, `x >= y` đều cho `false`.

Đừng kiểm tra `NaN` bằng biểu thức `value == Double.NaN` hoặc `value == Float.NaN`; phép so sánh đó **luôn false**. Dùng `Double.isNaN(value)` hoặc `Float.isNaN(value)`.

`NaN` có nhiều mẫu bit IEEE 754 khả dĩ (*NaN payload*). Chúng không tương ứng với các giá trị số thực thông thường. Java cung cấp các hàm đổi bit cho phép phân biệt giữa **cách nhìn canonical** và **cách nhìn raw**; đó là cơ sở để wrapper `equals` cho mọi `NaN` cùng kiểu có thể bằng nhau.

### Signed zero là gì?

IEEE 754 có **hai biểu diễn zero**:

- `+0.0`: bit dấu là `0`.
- `-0.0`: bit dấu là `1`.

Chúng đều có phần trị và số mũ bằng `0`, chỉ khác bit dấu. Java coi chúng bằng nhau khi so sánh số học `==`. Tuy nhiên, dấu của zero có thể ảnh hưởng phép toán khác:

```java
System.out.println(+0.0 == -0.0); // true
System.out.println(1.0 / +0.0);    // Infinity
System.out.println(1.0 / -0.0);    // -Infinity
```

Như vậy hai mẫu zero có cùng giá trị dưới phép `==` nhưng **không phải mọi phép toán đều xử lý chúng giống hệt nhau**. Wrapper `equals` chủ đích phân biệt hai mẫu bit zero này.

## 3. Bảng đối chiếu: primitive `==` và wrapper `equals`

| Tình huống (cùng kiểu `double`/`Double`) | So sánh primitive `==` | `Double.equals` |
| --- | --- | --- |
| `1.0` với `1.0` | `true` | `true` |
| `1.0` với `2.0` | `false` | `false` |
| `+0.0` với `-0.0` | `true` | `false` |
| `Double.NaN` với `Double.NaN` | `false` | `true` |
| Hai `NaN` có payload khác nhau | `false` | `true` |
| `Double.POSITIVE_INFINITY` với chính nó | `true` | `true` |
| `Double.NEGATIVE_INFINITY` với dương vô cực | `false` | `false` |

Với `Float`, thay `Double` bằng `Float` cho các trường hợp tương ứng. Chú ý `Float.valueOf(1.0f).equals(Double.valueOf(1.0))` vẫn là **`false`**, dù chúng mô tả cùng giá trị toán học, vì `equals` của wrapper yêu cầu **đúng loại lớp bao**.

Các hành vi đặc biệt của `NaN` và signed zero cũng là lý do không nên viết một hàm so sánh số thực chung bằng cách thay `a == b` thành `Double.valueOf(a).equals(Double.valueOf(b))` mà không xem xét hợp đồng nghiệp vụ.

## 4. `Double.equals` và `Float.equals` thực sự so sánh theo gì?

Theo tài liệu JDK, `Double.equals(Object obj)` cho `true` khi đối tượng kia cũng là `Double` và kết quả từ phép **`Double.doubleToLongBits`** trên hai giá trị bằng nhau. Tương tự, `Float.equals` sử dụng **`Float.floatToIntBits`**.

Có thể hiểu khái niệm như sau (mã **minh họa cơ chế**, không sao chép toàn bộ triển khai JDK):

```java
static boolean sameDoubleWrapperValue(double a, double b) {
    return Double.doubleToLongBits(a) == Double.doubleToLongBits(b);
}

static boolean sameFloatWrapperValue(float a, float b) {
    return Float.floatToIntBits(a) == Float.floatToIntBits(b);
}
```

Hai đặc tính của phép đổi bit này giải thích các trường hợp ngoại lệ:

1. **NaN được chuẩn hóa (*canonicalized*):** `Double.doubleToLongBits` trả về cùng **mẫu bit NaN chuẩn** cho mọi giá trị `double` là `NaN`. `Float.floatToIntBits` làm tương tự trên 32 bit. Vì vậy các `NaN` cùng lớp bao có `equals == true`.
2. **Bit dấu zero được giữ:** `+0.0` và `-0.0` chuyển thành hai chuỗi bit khác nhau; vì thế wrapper `equals` trả `false`.

Ví dụ:

```java
System.out.println(Double.doubleToLongBits(+0.0)
        == Double.doubleToLongBits(-0.0)); // false

System.out.println(Float.floatToIntBits(+0.0f)
        == Float.floatToIntBits(-0.0f)); // false

System.out.println(Double.doubleToLongBits(Double.NaN)
        == Double.doubleToLongBits(0.0 / 0.0)); // true
```

**Không nhầm** `doubleToLongBits` với `doubleToRawLongBits` hoặc `floatToIntBits` với `floatToRawIntBits`:

- `doubleToLongBits` / `floatToIntBits` **canonicalize NaN**, phù hợp với `equals`.
- `doubleToRawLongBits` / `floatToRawIntBits` **không cố ý canonicalize NaN** khi trả về bit, nên có thể quan sát các payload NaN khác nhau, tùy giá trị bit còn được giữ sau các phép xử lý trước đó.

Nếu mục tiêu là kiểm tra/ghi lại chính xác payload nhị phân của dữ liệu theo một giao thức, phải chọn công cụ raw-bit có chủ đích. Nếu mục tiêu là khóa `Float`/`Double` trong collection, cần tôn trọng ngữ nghĩa canonical mà wrapper định nghĩa.

## 5. `Double.compare`, `Float.compare` và `compareTo` liên quan gì tới `equals`?

Java cần một **thứ tự tổng** (*total order*) để sắp xếp và lưu số thực trong các cấu trúc có thứ tự. Với kiểu wrapper, `Double.compare(double x, double y)` và `Float.compare(float x, float y)` định nghĩa thêm hai quy tắc đặc biệt:

- `-0.0` được xếp **nhỏ hơn** `+0.0`.
- `NaN` được xem là **lớn hơn mọi số thực**, kể cả `+Infinity`; các giá trị `NaN` được xem là bằng nhau khi so sánh qua `compare`.

`Double.compareTo(Double)` và `Float.compareTo(Float)` theo quy tắc cùng lớp bao. Khi so sánh hai giá trị đã được định kiểu, `compare(x,y) == 0` nhất quán với wrapper `equals` tương ứng.

```java
System.out.println(Double.compare(-0.0, +0.0) < 0); // true
System.out.println(Double.compare(Double.NaN,
        Double.POSITIVE_INFINITY) > 0); // true
System.out.println(Double.compare(Double.NaN, 0.0 / 0.0) == 0); // true
```

Trong khi đó, các phép toán thứ tự nguyên thủy:

```java
System.out.println(-0.0 < +0.0); // false
System.out.println(Double.NaN > Double.POSITIVE_INFINITY); // false
```

Không dùng phép `<`/`>` trên primitive để giả lập một comparator có thứ tự tổng. Với sắp xếp `List<Double>`, dùng `Double::compare` hoặc `Double::compareTo` khi chính sách mong muốn là **NaN cuối, -0.0 đứng trước +0.0**.

Cần phân biệt **thứ tự tổng phục vụ collection** với **thứ tự số học của IEEE 754 khi gặp NaN**. Các quy tắc khác nhau là cố ý và đã được mô tả trong JDK.

## 6. Vì sao các collection cần hợp đồng `equals` như vậy?

`HashSet`, `HashMap` và những collection dựa trên khóa thường sử dụng hợp đồng `equals` và `hashCode` của đối tượng, không dùng toán tử số học `==` để quyết định khóa trùng nhau.

Với `Double`:

- Hai đối tượng chứa `NaN` được xem là **bằng nhau theo `equals`**, nên chúng đại diện cho **cùng khóa**.
- `Double.valueOf(+0.0)` và `Double.valueOf(-0.0)` là **hai khóa khác nhau**.
- Quy tắc `hashCode` được thiết kế nhất quán với `equals`: hai giá trị bằng nhau phải có cùng hash code. Các NaN cùng lớp bao được chuẩn hóa tương ứng; hai zero khác dấu giữ thông tin phân biệt.

Ví dụ:

```java
import java.util.HashSet;
import java.util.Set;

Set<Double> values = new HashSet<>();
values.add(+0.0);
values.add(-0.0);
values.add(Double.NaN);
values.add(0.0 / 0.0);

System.out.println(values.size()); // 3
```

Tập chứa ba giá trị theo `Double.equals`: zero dương, zero âm và một khóa NaN. Không dựa vào thứ tự lặp của `HashSet` để minh họa vì `HashSet` **không đảm bảo thứ tự**.

Còn với `HashMap`:

```java
import java.util.HashMap;
import java.util.Map;

Map<Double, String> descriptions = new HashMap<>();
descriptions.put(+0.0, "positive zero");
descriptions.put(-0.0, "negative zero");
descriptions.put(Double.NaN, "first");
descriptions.put(0.0 / 0.0, "second");

System.out.println(descriptions.size()); // 3
System.out.println(descriptions.get(+0.0)); // positive zero
System.out.println(descriptions.get(-0.0)); // negative zero
System.out.println(descriptions.get(Double.NaN)); // second
```

Lần ghi `NaN` sau **thay thế value** của cùng khóa NaN; hai zero vẫn là hai khóa độc lập.

### Với `TreeSet`, `TreeMap` thì sao?

Cấu trúc có thứ tự như `TreeSet<Double>` thường dựa trên `Double.compareTo`. Bộ so sánh đó nhất quán với `Double.equals`, vì thế vẫn có ba giá trị riêng biệt trong ví dụ zero dương, zero âm và NaN; khi sắp xếp theo thứ tự tự nhiên, `-0.0` đứng trước `+0.0`, còn `NaN` đứng sau vô cực dương.

**Quan trọng:** Nếu bạn tự đưa một comparator khác vào `TreeSet` hoặc `TreeMap`, chính comparator đó quyết định hai khóa có được xem là tương đương về thứ tự hay không. Comparator không nhất quán với `equals` có thể làm hành vi “trùng phần tử” khác với `HashSet`. Cần thiết kế tiêu chí so sánh một cách nhất quán với mục đích nghiệp vụ.

## 7. Không nhầm `equals`, `==` đối tượng và autounboxing

### `equals` so sánh giá trị theo hợp đồng lớp bao

```java
Double a = Double.valueOf(1.0);
Double b = Double.valueOf(1.0);

System.out.println(a.equals(b)); // true
```

### `==` giữa hai tham chiếu wrapper có thể là so sánh danh tính đối tượng

Khi **cả hai toán hạng đều có kiểu tham chiếu**, phép `==` kiểm tra chúng có trỏ đến **cùng đối tượng** hay không, không dùng `Double.equals`.

```java
Double a = Double.valueOf(1.0);
Double b = Double.valueOf(1.0);

boolean sameReference = a == b; // Không dùng để so sánh giá trị.
boolean sameValue = a.equals(b); // true.
```

Không dự đoán `sameReference` luôn `true` hoặc `false`: cách tạo/tái sử dụng đối tượng có thể thay đổi, và không phải hợp đồng so sánh số thực.

### Khi một toán hạng primitive, phép so sánh có thể unbox wrapper

```java
Double boxed = Double.valueOf(Double.NaN);
double primitive = Double.NaN;

System.out.println(boxed == primitive); // false
```

Ở đây `boxed` được unbox thành `double` để so sánh số học, nên quay lại quy tắc `NaN != NaN` của primitive.

Nếu wrapper là `null`, phép unboxing có thể ném `NullPointerException`. Ví dụ `Double d = null; boolean eq = d == 0.0;` **không** cho `false` an toàn mà lỗi khi đánh giá `d`.

Khi so sánh nullable wrapper theo nghĩa đối tượng, `java.util.Objects.equals(a, b)` có thể tránh lỗi `NullPointerException`, nhưng vẫn sử dụng chính `equals` của wrapper cho hai đối tượng không null, nên vẫn giữ ngữ nghĩa NaN/signed zero ở trên.

## 8. Khác lớp bao: `Float` và `Double` không bằng nhau qua `equals`

```java
Float f = Float.valueOf(1.0f);
Double d = Double.valueOf(1.0);

System.out.println(f.equals(d)); // false
System.out.println(d.equals(f)); // false
System.out.println(f.floatValue() == d.doubleValue()); // true
```

Hai wrapper chứa cùng giá trị số học `1`, nhưng `equals` yêu cầu đối tượng cùng loại. Trong biểu thức primitive cuối, binary numeric promotion nâng `float` lên `double` rồi so sánh giá trị, nên trả `true`.

Đừng vì ví dụ `1.0` mà kết luận mọi `float` so với `double` có thể so sánh chính xác: `float` chỉ có 24 bit chính xác và nhiều số thập phân đã được làm tròn khi lưu. Khi nghiệp vụ cần so sánh qua hai kiểu, phải xác định rõ **giá trị mong muốn** và phép chuyển đổi được chấp nhận.

## 9. Khi nào nên dùng cách so sánh nào?

| Mục tiêu | Cách làm phù hợp | Lưu ý |
| --- | --- | --- |
| Xử lý giá trị primitive theo số học IEEE 754 | `a == b`, `a < b` | `NaN` luôn làm so sánh bằng false; zero hai dấu bằng nhau |
| Phát hiện NaN | `Double.isNaN(a)`, `Float.isNaN(a)` | Không dùng `a == NaN` |
| So sánh đối tượng `Double`/`Float` | `a.equals(b)` | NaN bằng NaN; zero hai dấu khác nhau |
| So sánh nullable wrapper | `Objects.equals(a, b)` | Tránh NPE do gọi `equals` trên null; giữ ngữ nghĩa wrapper |
| Sắp xếp số thực với NaN và signed zero | `Double.compare(a, b)` hoặc `Float.compare(a, b)` | NaN cuối, `-0.0 < +0.0` theo comparator |
| Dùng số thực làm khóa `HashMap`/`HashSet` | Định nghĩa dữ liệu theo `equals`/`hashCode` | NaN gộp khóa; signed zero tách khóa |
| So sánh hai kết quả tính toán gần nhau | Một chính sách sai số phù hợp miền nghiệp vụ | Không mặc định dùng `equals` hay epsilon cố định tùy ý |
| So sánh chính xác thập phân tiền tệ | `BigDecimal` hoặc số nguyên đơn vị nhỏ nhất | `BigDecimal.equals` xét cả scale; `compareTo` chỉ so giá trị |

Một ví dụ *so sánh gần đúng* với kết quả phép tính:

```java
double computed = 0.1 + 0.2;
double expected = 0.3;
double tolerance = 1e-12;

boolean close = Double.isFinite(computed)
        && Double.isFinite(expected)
        && Math.abs(computed - expected) <= tolerance;
System.out.println(close); // true
```

Đây là quy tắc ứng dụng riêng, **không thay thế** hợp đồng `Double.equals`. Ngưỡng `1e-12` chỉ có ý nghĩa với bài toán và thang đo thích hợp, không phải hằng số chuẩn cho mọi số thực. Nếu xử lý vô cực, NaN, số rất lớn, rất nhỏ hoặc yêu cầu chính xác bit, cần xác định cách xử lý chi tiết riêng.

## 10. Ví dụ Java 17+ chạy độc lập

Tạo tệp **`FloatingEqualityDemo.java`**:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class FloatingEqualityDemo {
    public static void main(String[] args) {
        double posZero = +0.0;
        double negZero = -0.0;

        System.out.println("primitive NaN == NaN = "
                + (Double.NaN == Double.NaN));
        System.out.println("primitive +0 == -0 = "
                + (posZero == negZero));

        System.out.println("Double.equals NaN = "
                + Double.valueOf(Double.NaN).equals(Double.valueOf(0.0 / 0.0)));
        System.out.println("Double.equals signed zero = "
                + Double.valueOf(posZero).equals(Double.valueOf(negZero)));

        System.out.println("Float.equals NaN = "
                + Float.valueOf(Float.NaN).equals(Float.valueOf(0.0f / 0.0f)));
        System.out.println("Float.equals signed zero = "
                + Float.valueOf(+0.0f).equals(Float.valueOf(-0.0f)));

        System.out.println("Double.compare -0 < +0 = "
                + (Double.compare(negZero, posZero) < 0));
        System.out.println("Double.compare NaN > infinity = "
                + (Double.compare(Double.NaN,
                        Double.POSITIVE_INFINITY) > 0));

        System.out.println("zero bits equal = "
                + (Double.doubleToLongBits(posZero)
                == Double.doubleToLongBits(negZero)));
        System.out.println("NaN canonical bits equal = "
                + (Double.doubleToLongBits(Double.NaN)
                == Double.doubleToLongBits(0.0 / 0.0)));

        Set<Double> set = new HashSet<>();
        set.add(posZero);
        set.add(negZero);
        set.add(Double.NaN);
        set.add(0.0 / 0.0);
        System.out.println("HashSet size = " + set.size());

        Map<Double, String> names = new HashMap<>();
        names.put(posZero, "positive");
        names.put(negZero, "negative");
        names.put(Double.NaN, "first NaN");
        names.put(0.0 / 0.0, "second NaN");
        System.out.println("HashMap size = " + names.size());
        System.out.println("positive zero key = " + names.get(posZero));
        System.out.println("negative zero key = " + names.get(negZero));
        System.out.println("NaN key = " + names.get(Double.NaN));

        System.out.println("Float.equals Double = "
                + Float.valueOf(1.0f).equals(Double.valueOf(1.0)));

        Double boxedNaN = Double.valueOf(Double.NaN);
        double primitiveNaN = Double.NaN;
        System.out.println("unboxed NaN comparison = "
                + (boxedNaN == primitiveNaN));

        System.out.println("NaN detected = " + Double.isNaN(0.0 / 0.0));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac FloatingEqualityDemo.java
java FloatingEqualityDemo
```

Kết quả:

```text
primitive NaN == NaN = false
primitive +0 == -0 = true
Double.equals NaN = true
Double.equals signed zero = false
Float.equals NaN = true
Float.equals signed zero = false
Double.compare -0 < +0 = true
Double.compare NaN > infinity = true
zero bits equal = false
NaN canonical bits equal = true
HashSet size = 3
HashMap size = 3
positive zero key = positive
negative zero key = negative
NaN key = second NaN
Float.equals Double = false
unboxed NaN comparison = false
NaN detected = true
```

Ví dụ tập trung vào hành vi **được hợp đồng Java đảm bảo**, không dựa vào thứ tự lặp của `HashMap`/`HashSet`, cache của wrapper hay payload NaN raw cụ thể. Có thể kiểm chứng những dòng `HashSet`/`HashMap` để hiểu ngay vì sao cùng là “zero” nhưng có hai khóa, còn nhiều nguồn tạo NaN lại gộp thành một khóa.

## 11. Những lỗi dễ mắc khi xử lý `Float`/`Double`

1. **Cho rằng `Double.equals` tương đương `==` trên `double`.** Sai ở hai trường hợp cốt lõi: `NaN` và signed zero.
2. **Dùng `x == Double.NaN` để kiểm tra lỗi tính toán.** Kết quả luôn `false`; dùng `Double.isNaN(x)`.
3. **Cho rằng `NaN` không bao giờ “bằng chính nó” trong mọi API.** Primitive `==` trả `false`, nhưng wrapper `equals` trả `true` và `Double.compare(NaN,NaN)` trả 0.
4. **Cho rằng `+0.0` và `-0.0` là một khóa duy nhất của `HashMap<Double,...>`.** Wrapper phân biệt chúng, nên thường có hai khóa.
5. **Dùng `Double.compare(a,b)==0` rồi suy ra `a==b` đối với mọi giá trị.** Không đúng với NaN và signed zero. Kết quả `compare == 0` nhất quán với wrapper `equals`, không phải toàn bộ phép so sánh primitive.
6. **Dùng `==` giữa hai wrapper để so sánh nội dung.** Khi cả hai là tham chiếu, phép toán xét danh tính đối tượng; muốn theo ngữ nghĩa wrapper hãy dùng `equals`.
7. **Dùng `equals` trên `Float` và `Double` khác lớp và mong `true` vì cùng là số 1.** Wrapper yêu cầu cùng loại đối tượng.
8. **Giả sử mọi NaN có cùng raw-bit payload.** `equals` dựa trên các phép đổi bit có canonicalization; khi làm việc với giao thức nhị phân cần hiểu sự khác biệt với `doubleToRawLongBits`/`floatToRawIntBits`.
9. **Dùng `equals` để kiểm tra kết quả gần đúng** của những phép tính như `0.1+0.2`. `equals` không phải so sánh theo sai số; chọn một chính sách khác nếu bài toán cho phép sai lệch nhỏ.
10. **Không xét tới `null` khi so sánh wrapper.** `a.equals(b)` có thể ném NPE khi `a` null; phép `==` có unboxing cũng có thể ném NPE. Dùng quy tắc nullable phù hợp.

## 12. Checklist thiết kế so sánh số thực

Trước khi chọn toán tử hay API, xác định rõ:

- **Dữ liệu là primitive hay wrapper?** Cùng ký hiệu `==` có thể biểu thị so sánh số học hoặc so sánh danh tính tham chiếu, tùy kiểu toán hạng.
- **NaN có được phép xuất hiện không?** Nếu là tín hiệu dữ liệu lỗi, kiểm tra sớm bằng `isNaN`; nếu là giá trị hợp lệ trong khóa collection, hiểu quy tắc wrapper canonicalization.
- **Hai zero có phải phân biệt không?** Nếu không, cân nhắc chuẩn hóa zero trước khi lưu khóa; nếu có, `Double.equals`/`Float.equals` giữ được sự khác nhau.
- **Có cần thứ tự sắp xếp toàn phần không?** Chọn `Double.compare`/`Float.compare` cho thứ tự có quy tắc rõ ràng với NaN và signed zero.
- **Độ chính xác thực sự yêu cầu là gì?** Nếu so sánh số liệu đo/ước lượng, xác định ngưỡng từ bài toán; nếu cần chính xác theo thập phân, cân nhắc `BigDecimal` và quy tắc `equals`/`compareTo` riêng của lớp đó.
- **Có dùng làm khóa dữ liệu hay collection không?** Một khi chọn định nghĩa bằng nhau, đảm bảo bộ so sánh, mã băm và chuẩn hóa dữ liệu nhất quán với mục đích đó.

**Kết luận:** `==` trên `float`/`double` tuân thủ so sánh số học IEEE 754 (**NaN không bằng NaN, hai zero bằng nhau**). `Float.equals` và `Double.equals` lại dựa trên các mẫu bit đã canonicalize NaN (**NaN bằng NaN, hai zero khác nhau**), giúp xây dựng ngữ nghĩa khóa và thứ tự nhất quán trong các collection. Đừng thay thế hai quy tắc một cách vô thức; hãy lựa chọn theo yêu cầu thực sự của chương trình.

**Tài liệu tham khảo:** [Java SE 21 — Double.equals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html#equals(java.lang.Object)), [Double.compare](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html#compare(double,double)), [Double.doubleToLongBits](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html#doubleToLongBits(double)), [Float.equals](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Float.html#equals(java.lang.Object)), [JLS §15.21.1 — Numerical Equality Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.21.1).
