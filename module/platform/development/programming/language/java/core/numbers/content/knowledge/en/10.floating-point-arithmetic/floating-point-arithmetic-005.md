# Lan truyền NaN và các trường hợp đặc biệt trong phép toán dấu phẩy động Java

Trong Java, `float` (32 bit) và `double` (64 bit) dùng kiểu dấu phẩy động nhị phân theo IEEE 754. Bên cạnh số hữu hạn thông thường, chúng còn có **NaN** (*Not a Number*), **vô cực dương/âm** và **số 0 có dấu**. Các giá trị này tham gia vào phép toán theo những quy tắc xác định: một phép toán có thể trả về `NaN` hoặc `Infinity` mà **không ném ngoại lệ chia cho 0** như phép chia số nguyên.

Trọng tâm bài là **NaN sinh ra từ đâu, lan truyền như thế nào, so sánh ra sao và cách xử lý đúng khi dữ liệu đi qua nhiều phép tính**. Các ví dụ dùng Java 17+ và kiểu `double`; phần lớn quy tắc tương ứng cũng áp dụng cho `float`.

## 1. Phân biệt các giá trị đặc biệt

| Giá trị | Ví dụ Java | Ý nghĩa |
| --- | --- | --- |
| Số hữu hạn bình thường | `1.5`, `-20.0` | Một giá trị số nằm trong miền biểu diễn của kiểu |
| Số hữu hạn dưới chuẩn (*subnormal*) | `Double.MIN_VALUE` | Rất gần 0 nhưng khác 0; độ chính xác tương đối có thể giảm |
| Dương vô cực | `Double.POSITIVE_INFINITY` | Có thể thu được do tràn số hữu hạn hoặc chia dương cho `+0.0` |
| Âm vô cực | `Double.NEGATIVE_INFINITY` | Có thể thu được khi chia âm cho `+0.0` |
| NaN | `Double.NaN` | Kết quả không phải một số có thứ tự thông thường |
| Dương và âm 0 | `+0.0`, `-0.0` | Bằng nhau khi dùng `==` nhưng mang bit dấu khác nhau |

`Float.NaN`, `Float.POSITIVE_INFINITY` và `Float.NEGATIVE_INFINITY` là các hằng tương ứng cho `float`. **`Double.MIN_VALUE` là số dương khác 0 nhỏ nhất có thể biểu diễn**, không phải giá trị âm lớn về độ lớn; giá trị hữu hạn âm có độ lớn tối đa là `-Double.MAX_VALUE`.

NaN không có nghĩa là `null`, giá trị còn thiếu hay ngoại lệ Java. Nó là một **giá trị bit hợp lệ** của `float`/`double`, có thể được lưu trong biến, truyền làm tham số và lan qua phép tính. Nếu dữ liệu nghiệp vụ dùng NaN để biểu thị “thiếu”, đó là **quy ước riêng của ứng dụng**, không phải ý nghĩa bắt buộc của IEEE 754.

## 2. Những phép tính sinh ra NaN

Các phép tính sau trả về NaN với kiểu `double`:

~~~java
double a = 0.0 / 0.0;                           // NaN
double b = Double.POSITIVE_INFINITY
         - Double.POSITIVE_INFINITY;           // NaN
double c = Double.POSITIVE_INFINITY * 0.0;      // NaN
double d = Double.POSITIVE_INFINITY
         / Double.POSITIVE_INFINITY;           // NaN
double e = Math.sqrt(-1.0);                     // NaN
double f = Double.NaN;                          // NaN có sẵn
~~~

Giải thích:

- `0.0 / 0.0` không có một thương số được xác định duy nhất.
- `+Infinity - +Infinity` và `Infinity / Infinity` không thể suy ra kết quả hữu hạn chỉ từ hai giá trị vô cực.
- `Infinity * 0.0` là trường hợp không xác định theo quy tắc phép toán dấu phẩy động.
- `Math.sqrt(-1.0)` nằm ngoài miền số thực của hàm căn bậc hai trong API này.

**Không nhầm với các trường hợp trả về vô cực:**

~~~java
double p = 1.0 / 0.0;   // +Infinity
double n = -1.0 / 0.0;  // -Infinity
double z = -1.0 / -0.0; // +Infinity
~~~

Chia số nguyên `1 / 0` (nếu thực thi với mẫu số nguyên 0) gây `ArithmeticException`, còn chia dấu phẩy động cho 0 tuân theo quy tắc NaN/vô cực. Chú ý kiểu của toán hạng: `1.0 / 0.0` khác với `1 / 0`.

Các trường hợp tràn/thiếu phạm vi cũng đáng lưu ý:

~~~java
double overflow = Double.MAX_VALUE * 2.0; // Infinity
double underflow = Double.MIN_VALUE / 2.0; // 0.0 do quá nhỏ
~~~

Tràn số hữu hạn có thể cho vô cực; kết quả quá nhỏ có thể được làm tròn thành 0 có dấu hoặc một số dưới chuẩn. **Không phải mọi lần tràn hoặc mất chính xác đều sinh NaN.**

## 3. NaN lan truyền qua phép toán như thế nào?

Trong các phép tính số học thông thường (`+`, `-`, `*`, `/`) trên `float` và `double`, nếu một toán hạng là NaN thì kết quả là NaN. NaN có thể đi tiếp qua nhiều bước:

~~~java
double reading = Double.NaN;
double adjusted = reading + 5.0;  // NaN
double scaled = adjusted * 2.0;   // NaN
double average = scaled / 3.0;    // NaN
~~~

Khi kết quả một bước đã thành NaN, cộng thêm một số hữu hạn **không làm kết quả “trở lại bình thường”**. Vì vậy, một dữ liệu đầu vào bất thường có thể làm toàn bộ tổng, trung bình, hệ số hoặc kết quả tính toán phía sau thành NaN.

Tuy nhiên, **đừng khẳng định mọi API nhận NaN đều luôn trả NaN**: các hàm thư viện có quy tắc đặc biệt riêng. Chẳng hạn:

~~~java
double result = Math.pow(Double.NaN, 0.0); // 1.0
~~~

Số mũ bằng 0 là trường hợp được `Math.pow` quy định trả `1.0`, kể cả khi cơ số là NaN. Ngược lại, `Math.min(Double.NaN, 2.0)` trả NaN. Hãy đọc hợp đồng của API thay vì suy diễn một quy tắc truyền NaN cho mọi hàm.

Một chương trình nên phát hiện NaN tại **điểm nhập dữ liệu hoặc trước phép tính có ràng buộc giá trị hữu hạn**, để tránh làm mất dấu vị trí đã tạo ra vấn đề.

## 4. So sánh NaN: không dùng `==` để nhận biết

NaN có hành vi so sánh **unordered** (*không có thứ tự thông thường*) trong các phép so sánh primitive. Dù hai biểu thức cùng là NaN:

~~~java
double x = Double.NaN;

boolean equal = x == x;      // false
boolean different = x != x;  // true
boolean less = x < 1.0;      // false
boolean greater = x > 1.0;   // false
boolean atMost = x <= 1.0;   // false
boolean atLeast = x >= 1.0;  // false
~~~

Đối với NaN, `==`, `<`, `>`, `<=` và `>=` đều trả `false`; `!=` trả `true`. Điều này cũng áp dụng khi toán hạng còn lại là NaN. **Đừng thay kiểm tra NaN bằng `x == Double.NaN`:** biểu thức này luôn là `false`.

Cách kiểm tra chuẩn:

~~~java
double x = Double.NaN;

if (Double.isNaN(x)) {
    System.out.println("Dữ liệu không phải số hợp lệ");
}
~~~

Với `float`, dùng `Float.isNaN(value)`. Mẹo kiểm tra `x != x` có thể hoạt động do quy tắc IEEE 754 nhưng khó đọc, nên ưu tiên `Double.isNaN` hoặc `Float.isNaN`.

## 5. Vô cực và số 0 có dấu: không được bỏ qua

Vô cực **không đồng nghĩa NaN**: nó có thứ tự đối với các số hữu hạn và có thể là kết quả hợp lệ theo quy tắc dấu phẩy động. Ví dụ `Double.POSITIVE_INFINITY > Double.MAX_VALUE` là `true`; `Double.NEGATIVE_INFINITY < -Double.MAX_VALUE` cũng là `true`.

Các phép tính kết hợp vô cực có kết quả khác nhau:

| Biểu thức | Kết quả |
| --- | --- |
| `+Infinity + 5.0` | `Infinity` |
| `-Infinity - 5.0` | `-Infinity` |
| `+Infinity + -Infinity` | `NaN` |
| `+Infinity * -2.0` | `-Infinity` |
| `+Infinity * 0.0` | `NaN` |
| `1.0 / +0.0` | `Infinity` |
| `1.0 / -0.0` | `-Infinity` |
| `-1.0 / -0.0` | `Infinity` |

Số 0 có dấu giữ thông tin dấu trong phép chia và trong một số API:

~~~java
System.out.println(+0.0 == -0.0);            // true
System.out.println(1.0 / -0.0);               // -Infinity
System.out.println(Double.compare(+0.0, -0.0)); // 1
~~~

So sánh primitive `==` xem `+0.0` và `-0.0` bằng nhau, trong khi `Double.compare` phân biệt được bit dấu. Nếu thuật toán sử dụng dấu của 0 (chẳng hạn khi tính nghịch đảo), đừng chuẩn hóa `-0.0` thành `+0.0` một cách tùy tiện.

## 6. Phân biệt `Double.isNaN`, `isInfinite` và `isFinite`

Các API hữu ích:

| API | NaN | ±Infinity | Số hữu hạn (kể cả ±0 và subnormal) |
| --- | --- | --- | --- |
| `Double.isNaN(x)` | `true` | `false` | `false` |
| `Double.isInfinite(x)` | `false` | `true` | `false` |
| `Double.isFinite(x)` | `false` | `false` | `true` |

Với dữ liệu nghiệp vụ **bắt buộc hữu hạn**, kiểm tra `Double.isFinite(value)` ngăn cả NaN lẫn vô cực đi sâu vào phép tính:

~~~java
static double requireFinite(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Expected finite value");
    }
    return value;
}
~~~

Ngược lại, trong một số lĩnh vực như tính toán khoa học, vô cực hoặc NaN có thể là tín hiệu có ích cần giữ để chẩn đoán. Chỉ loại bỏ hoặc chuyển đổi chúng khi **hợp đồng dữ liệu** quy định rõ.

## 7. So sánh primitive khác với `Double.compare` và `Double.equals`

Java cung cấp một thứ tự được định nghĩa bởi `Double.compare(a, b)` để hỗ trợ sắp xếp/collections. Theo thứ tự này:

- `-0.0` **nhỏ hơn** `+0.0`.
- NaN được xem **lớn hơn mọi giá trị khác**, kể cả `+Infinity`.
- Các NaN được xem **bằng nhau** theo `Double.compare`.

Vì thế:

~~~java
Double.compare(+0.0, -0.0); // 1
Double.compare(Double.NaN, Double.POSITIVE_INFINITY); // 1
Double.compare(Double.NaN, Double.NaN); // 0
~~~

Trong khi `Double.NaN == Double.NaN` là `false`, lời gọi `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` lại là `true`. Ngược lại, hai wrapper `Double.valueOf(+0.0)` và `Double.valueOf(-0.0)` không bằng nhau theo `equals`. Quy ước này giúp `Double.compare` và `Double.equals` nhất quán với nhau trong các collections và phép sắp xếp.

Đó là khác biệt **giữa quy tắc toán tử primitive và hợp đồng so sánh của wrapper**. Không dùng `Double.compare` để suy ra rằng NaN bỗng trở thành một số có thứ tự theo phép so sánh primitive.

## 8. Ví dụ Java 17+ hoàn chỉnh và kết quả chạy

Lưu tệp `FloatingSpecialCases.java`:

~~~java
public class FloatingSpecialCases {
    public static void main(String[] args) {
        double nan = Double.NaN;
        double infinity = Double.POSITIVE_INFINITY;
        double negZero = -0.0;

        System.out.println("nan + 5 = " + (nan + 5.0));
        System.out.println("0.0 / 0.0 = " + (0.0 / 0.0));
        System.out.println("1.0 / 0.0 = " + (1.0 / 0.0));
        System.out.println("-1.0 / 0.0 = " + (-1.0 / 0.0));
        System.out.println("infinity - infinity = "
                + (infinity - infinity));
        System.out.println("infinity * 0.0 = " + (infinity * 0.0));

        System.out.println("NaN == NaN = " + (nan == nan));
        System.out.println("NaN != NaN = " + (nan != nan));
        System.out.println("NaN < 1 = " + (nan < 1.0));
        System.out.println("isNaN = " + Double.isNaN(nan));
        System.out.println("isFinite(1.5) = " + Double.isFinite(1.5));
        System.out.println("isInfinite = "
                + Double.isInfinite(infinity));

        System.out.println("+0.0 == -0.0 = " + (0.0 == negZero));
        System.out.println("1.0 / -0.0 = " + (1.0 / negZero));
        System.out.println("Double.compare(+0,-0) = "
                + Double.compare(+0.0, -0.0));
        System.out.println("Double.compare(NaN,+Inf) = "
                + Double.compare(nan, infinity));
        System.out.println("Double.NaN.equals = "
                + Double.valueOf(nan).equals(Double.valueOf(nan)));
        System.out.println("Double(+0).equals(Double(-0)) = "
                + Double.valueOf(0.0).equals(Double.valueOf(-0.0)));
        System.out.println("sqrt(-1.0) = " + Math.sqrt(-1.0));
        System.out.println("Math.min(NaN, 2) = " + Math.min(nan, 2.0));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac FloatingSpecialCases.java
java FloatingSpecialCases
~~~

Stdout chính xác:

~~~text
nan + 5 = NaN
0.0 / 0.0 = NaN
1.0 / 0.0 = Infinity
-1.0 / 0.0 = -Infinity
infinity - infinity = NaN
infinity * 0.0 = NaN
NaN == NaN = false
NaN != NaN = true
NaN < 1 = false
isNaN = true
isFinite(1.5) = true
isInfinite = true
+0.0 == -0.0 = true
1.0 / -0.0 = -Infinity
Double.compare(+0,-0) = 1
Double.compare(NaN,+Inf) = 1
Double.NaN.equals = true
Double(+0).equals(Double(-0)) = false
sqrt(-1.0) = NaN
Math.min(NaN, 2) = NaN
~~~

Mỗi dòng kiểm tra một đặc tính: nguồn tạo NaN, lan truyền, so sánh không có thứ tự, nhận diện giá trị không hữu hạn, dấu của 0 và sự khác nhau giữa toán tử `==` với comparator/wrapper.

## 9. Khi NaN xuất hiện trong tập dữ liệu

Giả sử ứng dụng cần tính tổng ba giá trị `2.0`, `NaN` và `3.0`. Tổng thông thường sẽ là NaN:

~~~java
double sum = java.util.stream.DoubleStream
        .of(2.0, Double.NaN, 3.0)
        .sum(); // NaN
~~~

Nếu yêu cầu nghiệp vụ quy định rõ **chỉ cộng các giá trị hữu hạn**, có thể lọc trước:

~~~java
double finiteSum = java.util.stream.DoubleStream
        .of(2.0, Double.NaN, 3.0)
        .filter(Double::isFinite)
        .sum(); // 5.0
~~~

Hai đoạn này minh họa hai **chính sách khác nhau**, không phải hai cách tính thay thế tùy ý. Việc bỏ NaN khỏi tập dữ liệu có thể thay đổi ý nghĩa trung bình, mẫu số, chất lượng thống kê và khả năng phát hiện lỗi cảm biến/đầu vào. Khi cần điều tra, hãy ghi nhận nguồn dữ liệu bất thường thay vì âm thầm lọc.

Một cách kiểm tra tại ranh giới nhận đầu vào:

~~~java
static double normalizedRate(double numerator, double denominator) {
    if (!Double.isFinite(numerator) || !Double.isFinite(denominator)) {
        throw new IllegalArgumentException("Inputs must be finite");
    }
    if (denominator == 0.0) {
        throw new IllegalArgumentException("Denominator must be nonzero");
    }
    double result = numerator / denominator;
    if (!Double.isFinite(result)) {
        throw new ArithmeticException("Non-finite quotient");
    }
    return result;
}
~~~

Đây là **đoạn phương thức minh họa**, có thể đặt vào một lớp Java; không phải chương trình chạy độc lập. Nó từ chối đầu vào không hữu hạn và số chia ±0, đồng thời phát hiện kết quả không hữu hạn do tính toán. Nếu nghiệp vụ cho phép vô cực/NaN, chính sách cần đổi tương ứng.

## 10. Các lỗi phổ biến cần tránh

1. **Dùng `x == Double.NaN` hoặc `x != Double.NaN` để phân loại NaN.** Cái đầu luôn sai, cái sau luôn đúng; dùng `Double.isNaN(x)`.
2. **Chỉ kiểm tra NaN nhưng quên vô cực.** `!Double.isNaN(x)` vẫn nhận `Infinity`. Nếu yêu cầu số hữu hạn, dùng `Double.isFinite(x)`.
3. **Cho rằng phép chia `double` cho 0 ném `ArithmeticException`.** `1.0 / 0.0` trả vô cực và `0.0 / 0.0` trả NaN; kết quả không hữu hạn cần được xử lý theo hợp đồng API.
4. **Dùng `==` để kỳ vọng hành vi giống `Double.equals`.** Đặc biệt với NaN và số 0 có dấu, hai kiểu so sánh khác nhau.
5. **Tin rằng có thể “sửa” NaN bằng cộng 0 hoặc nhân 1.** Các phép số học thông thường vẫn lan truyền NaN; cần giải quyết nguồn sinh NaN hoặc thay đổi chính sách dữ liệu có chủ đích.
6. **Cho rằng mọi kết quả số học bất thường đều là NaN.** Tràn có thể thành vô cực; thiếu phạm vi có thể thành 0 hoặc số dưới chuẩn.
7. **Nói mọi hàm toán học đều truyền NaN không điều kiện.** Một số trường hợp đặc biệt được API định nghĩa khác, như `Math.pow(Double.NaN, 0.0)` trả `1.0`.
8. **Không phân biệt phép tính nội bộ với biểu diễn/serialize dữ liệu.** Hệ thống JSON, cơ sở dữ liệu hoặc giao thức có thể không chấp nhận NaN/vô cực như các số thông thường; cần xác định cách biểu diễn ở ranh giới tích hợp.

## 11. Tự kiểm tra

1. `0.0 / 0.0`, `-1.0 / 0.0` và `Double.POSITIVE_INFINITY * 0.0` lần lượt trả gì?
2. Có đúng rằng `Double.NaN > Double.POSITIVE_INFINITY` không? `Double.compare(Double.NaN, Double.POSITIVE_INFINITY)` có trả số dương không?
3. Nếu một tổng có một phần tử NaN thì tiếp tục cộng `100.0` có cho tổng hữu hạn không?
4. Vì sao `1.0 / -0.0` là âm vô cực dù `+0.0 == -0.0` là `true`?
5. Cần hàm nào để từ chối đồng thời NaN, `+Infinity` và `-Infinity`?

**Đáp án:** (1) NaN, `-Infinity`, NaN. (2) Toán tử `>` trả `false`; `Double.compare` trả số dương. (3) Không, tổng tiếp tục là NaN trong phép cộng thông thường. (4) IEEE 754 giữ dấu của 0 để xác định dấu của kết quả phép chia, còn primitive equality xem hai số 0 bằng nhau. (5) `Double.isFinite(value)` phải là `true` mới chấp nhận.

## Tài liệu tham khảo

- [Java Language Specification `4.2.3 — Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.2.3).
- [Java Language Specification `15.20–15.21 — Comparisons and Equality](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20).
- [Java SE API — Double](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html): `isNaN`, `isFinite`, `isInfinite`, `compare`, `equals`.
- [Java SE API — Math](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html): `sqrt`, `pow`, `min` và quy tắc trường hợp đặc biệt.
