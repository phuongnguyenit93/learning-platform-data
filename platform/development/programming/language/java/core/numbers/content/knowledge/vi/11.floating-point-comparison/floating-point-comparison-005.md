# Float.compare, Double.compare và thứ tự toàn phần trong Java

Trong Java, hai số `float` hoặc `double` có thể được so sánh bằng các toán tử `<`, `>`, `<=`, `>=`, `==`, `!=` hoặc bằng `Float.compare(a, b)` và `Double.compare(a, b)`. Với số hữu hạn thông thường, hai cách thường dẫn đến cùng nhận định lớn/nhỏ; nhưng khi gặp **NaN** và **số 0 có dấu** (`-0.0`, `+0.0`), hành vi khác nhau có chủ đích.

`Float.compare` và `Double.compare` tạo ra một thứ tự so sánh **toàn phần trên các giá trị theo quy ước Java**: kể cả NaN cũng được xếp vào một vị trí xác định để có thể sắp xếp, tìm kiếm và dùng làm khóa collection. Hiểu sự khác nhau này giúp tránh lỗi rất khó phát hiện khi chuyển từ tính toán số học sang `sort`, `TreeSet`, `TreeMap` hoặc wrapper `Float`/`Double`.

## 1. Cần phân biệt hai mục đích so sánh

**Toán tử so sánh primitive** phản ánh quan hệ số học của các toán hạng dấu phẩy động:

- `1.0 < 2.0` là `true`; `2.0 == 2.0` là `true`.
- `-0.0 == +0.0` là `true`: so sánh bằng của primitive xem hai số 0 có dấu là bằng nhau.
- `Double.NaN == Double.NaN` là `false`, kể cả so sánh cùng một biến NaN với chính nó.
- Khi có NaN, các quan hệ `<`, `<=`, `>`, `>=`, `==` đều trả `false`; riêng `!=` trả `true`.

**`Double.compare(a, b)` / `Float.compare(a, b)`** tạo kết quả kiểu `int`:

| Kết quả | Ý nghĩa |
| --- | --- |
| Nhỏ hơn 0 | `a` đứng trước `b` theo thứ tự Java |
| Bằng 0 | `a` và `b` tương đương trong thứ tự Java |
| Lớn hơn 0 | `a` đứng sau `b` theo thứ tự Java |

Hợp đồng API chỉ bảo đảm **dấu** âm/0/dương. Đừng viết logic dựa vào giả định mọi lời gọi luôn trả đúng `-1` hoặc `1`; các ví dụ cụ thể bên dưới có thể trả những số ấy nhưng hợp đồng là dấu kết quả.

## 2. Thứ tự toàn phần mà Java sử dụng

Theo `Double.compare`, các giá trị được sắp như sau (từ nhỏ tới lớn):

~~~text
-Infinity < số hữu hạn âm < -0.0 < +0.0
          < số hữu hạn dương < +Infinity < NaN
~~~

Các điểm cốt lõi:

1. Số hữu hạn và vô cực được xếp theo thứ tự số học bình thường.
2. **`-0.0` nhỏ hơn `+0.0`**, dù toán tử primitive `==` cho rằng chúng bằng nhau.
3. **NaN đứng sau mọi giá trị khác**, kể cả `Double.POSITIVE_INFINITY`.
4. **Mọi NaN được `Double.compare` xem là tương đương** và cho kết quả 0 khi so sánh với nhau. Điều này đúng dù hai NaN có mẫu bit (*payload*) khác nhau.

`Float.compare` có cùng quy ước thứ tự cho `float`. Các chữ ký cần nhớ:

~~~java
int orderD = Double.compare(1.0, 2.0);      // < 0
int orderF = Float.compare(1.0f, 2.0f);     // < 0
~~~

`Float.compare` nhận tham số `float`; `Double.compare` nhận `double`. Không tự ép dữ liệu `double` về `float` chỉ để gọi `Float.compare`: phép ép có thể làm tròn hoặc làm hai số khác nhau trở nên bằng nhau.

**“Toàn phần” ở đây là thứ tự trên giá trị theo định nghĩa Java**, không phải khả năng phân biệt mọi mẫu bit IEEE 754. Mọi payload NaN được gộp về một lớp tương đương khi so sánh. Điều này khác với việc yêu cầu một thứ tự riêng biệt cho *tất cả các encoding bit* của NaN.

## 3. Số 0 có dấu: `==` và `compare` cố ý khác nhau

IEEE 754 cho phép `+0.0` và `-0.0` là hai mẫu bit khác nhau. Java giữ dấu của 0 trong nhiều phép toán; ví dụ:

~~~java
double positiveZero = +0.0;
double negativeZero = -0.0;

boolean primitiveEqual = positiveZero == negativeZero; // true
int first = Double.compare(negativeZero, positiveZero); // < 0
int second = Double.compare(positiveZero, negativeZero); // > 0

double inversePositive = 1.0 / positiveZero; // Infinity
double inverseNegative = 1.0 / negativeZero; // -Infinity
~~~

Trong ví dụ chạy phía dưới, `Double.compare(-0.0, +0.0)` trả `-1`, còn chiều ngược lại trả `1`. Hai số 0 vì thế **có thể chiếm hai vị trí riêng** trong một `TreeSet<Double>`.

Lưu ý khi dùng logic kiểu `if (x == 0.0)`: biểu thức này đúng với **cả hai** dấu của 0. Nếu phải phân biệt bit dấu vì nghiệp vụ số học, dùng `Double.compare`, `Double.doubleToRawLongBits` hoặc API phù hợp thay vì chỉ dùng `==`.

## 4. NaN: primitive unordered nhưng `compare` vẫn sắp xếp được

NaN có thể xuất hiện từ `0.0 / 0.0`, `Infinity - Infinity`, `Math.sqrt(-1.0)` hoặc một nguồn dữ liệu có giá trị NaN. Toán tử primitive không áp đặt quan hệ thứ tự giữa NaN và số khác:

~~~java
double nan = Double.NaN;

boolean equalsSelf = nan == nan;                 // false
boolean smaller = nan < Double.POSITIVE_INFINITY; // false
boolean greater = nan > Double.POSITIVE_INFINITY; // false
boolean differs = nan != nan;                   // true
~~~

Trong khi đó:

~~~java
int afterInfinity =
        Double.compare(Double.NaN, Double.POSITIVE_INFINITY); // > 0
int equalNaNs =
        Double.compare(Double.NaN, Double.NaN);               // 0
~~~

Không có mâu thuẫn: toán tử primitive mô tả **so sánh số học**, còn `compare` dùng **quy tắc total ordering của API Java** để làm việc với sorting và collections.

Kiểm tra “có phải NaN không” bằng `Double.isNaN(value)` hoặc `Float.isNaN(value)`, **không dùng** `value == Double.NaN` (luôn false) và cũng không dùng `Double.compare(value, Double.NaN) == 0` để che mất ý định phân loại giá trị. Cách thứ hai có thể nhận ra NaN nhưng diễn đạt sai mục đích, khó bảo trì hơn `isNaN`.

## 5. Hai NaN có payload khác nhau vẫn cho `compare == 0`

Một `double` NaN có thể có nhiều mẫu bit IEEE 754 khác nhau. Java có hai API cần phân biệt:

- `Double.doubleToRawLongBits(x)` giữ mẫu bit thô của giá trị `double` tại thời điểm gọi.
- `Double.doubleToLongBits(x)` **chuẩn hóa mọi NaN thành mẫu canonical NaN**; vì vậy thích hợp với quy ước `Double.equals`/`hashCode`.

~~~java
double nanA = Double.longBitsToDouble(0x7ff8_0000_0000_0001L);
double nanB = Double.longBitsToDouble(0x7ff8_0000_0000_0002L);

boolean rawDifferent = Double.doubleToRawLongBits(nanA)
                    != Double.doubleToRawLongBits(nanB); // true
int order = Double.compare(nanA, nanB);        // 0
boolean wrapperEqual =
        Double.valueOf(nanA).equals(Double.valueOf(nanB)); // true
~~~

Đừng dựa vào `compare` để phân biệt payload, dấu NaN hoặc truy vết nguyên vẹn encoding từng NaN. Nếu việc phân biệt payload là một yêu cầu giao thức/bit-level, cần định nghĩa chính sách dựa trên bit thô và biết rằng một số thao tác dấu phẩy động có thể không giữ nguyên payload. Với `float`, cặp API tương ứng là `Float.floatToRawIntBits` và `Float.floatToIntBits`.

## 6. Quan hệ với `Double.equals`, `Float.equals` và `compareTo`

Wrapper `Double` có `equals`/`hashCode` dựa trên biểu diễn chuẩn hóa NaN. Do đó:

| Hai giá trị | Primitive `a == b` | `Double.compare(a,b) == 0` | `Double.valueOf(a).equals(Double.valueOf(b))` |
| --- | --- | --- | --- |
| `2.0` và `2.0` | `true` | `true` | `true` |
| `+0.0` và `-0.0` | `true` | `false` | `false` |
| `NaN` và `NaN` | `false` | `true` | `true` |
| `-Infinity` và `-Infinity` | `true` | `true` | `true` |

`Double.compareTo` sử dụng quy tắc giống `Double.compare`; `Float.compareTo` tương ứng với `Float.compare`. Một lý do tồn tại thứ tự này là để **`compareTo` nhất quán với `equals` của wrapper**, rất quan trọng đối với collection có sắp thứ tự.

Khi viết `Double a = ...; Double b = ...; a.equals(b)`, bạn đang dùng **object equality của wrapper**; còn `a == b` nếu cả hai là object `Double` sẽ kiểm tra **đồng nhất tham chiếu**, không phải so sánh số. Chỉ khi toán hạng được unbox sang primitive, `==` mới thực hiện so sánh dấu phẩy động. Vì vậy muốn nói rõ ngữ nghĩa, hãy xác định kiểu tĩnh của toán hạng trước khi dự đoán kết quả.

## 7. Sắp xếp và cấu trúc dữ liệu

Các API như `Arrays.sort(double[])`, `Arrays.sort(float[])` và comparator dựa trên `Double.compare` hoặc `Float.compare` sử dụng thứ tự xử lý NaN/zero có dấu nhất quán. Với danh sách các `Double`, có thể viết:

~~~java
List<Double> values = new ArrayList<>(Arrays.asList(
        Double.NaN, 3.0, -0.0, Double.NEGATIVE_INFINITY,
        +0.0, Double.POSITIVE_INFINITY, -5.0, Double.NaN));
values.sort(Double::compare);
// [-Infinity, -5.0, -0.0, 0.0, 3.0, Infinity, NaN, NaN]
~~~

Đoạn trên **nằm trong phương thức của lớp có các import `java.util.*`**; ví dụ hoàn chỉnh ở mục 9 có thể chạy trực tiếp.

Với `TreeSet<Double>` (thứ tự tự nhiên theo `Double.compareTo`):

- `-0.0` và `+0.0` được giữ như **hai phần tử phân biệt**.
- Hai giá trị NaN được coi **trùng nhau** và chỉ có một phần tử NaN được giữ.
- NaN đứng cuối khi duyệt tăng dần.

Nếu dùng `TreeMap<Double, ...>` thì `-0.0` và `+0.0` cũng là hai khóa khác nhau, nhưng các NaN được xem là cùng một khóa theo thứ tự comparator. `HashSet<Double>` cũng coi các NaN là bằng nhau và hai zero có dấu khác nhau do `Double.equals`/`hashCode`, dù `HashSet` không bảo đảm thứ tự duyệt.

**Quy tắc cho comparator tự viết:** trả `0` nghĩa là hai khóa tương đương trong `TreeSet`/`TreeMap`. Comparator kiểu `(a, b) -> a < b ? -1 : a > b ? 1 : 0` là **sai** nếu có NaN hoặc số 0 có dấu: nó trả 0 với rất nhiều cặp không tương đương, có thể làm mất phần tử/ghi đè khóa. Dùng `Double.compare(a,b)` hoặc `Comparator.naturalOrder()`.

## 8. Chương trình Java 17+ biên dịch và chạy được

Tạo tệp `CompareDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class CompareDemo {
    public static void main(String[] args) {
        double negZero = -0.0;
        double posZero = 0.0;
        double nanA = Double.NaN;
        double nanB = Double.longBitsToDouble(0x7ff8_0000_0000_0001L);
        double nanC = Double.longBitsToDouble(0x7ff8_0000_0000_0002L);

        System.out.println("primitive +0 == -0: " + (posZero == negZero));
        System.out.println("primitive NaN == NaN: " + (nanA == nanA));
        System.out.println("primitive NaN < Infinity: "
                + (nanA < Double.POSITIVE_INFINITY));
        System.out.println("Double.compare(-0,+0): "
                + Double.compare(negZero, posZero));
        System.out.println("Double.compare(+0,-0): "
                + Double.compare(posZero, negZero));
        System.out.println("Double.compare(NaN,+Infinity): "
                + Double.compare(nanA, Double.POSITIVE_INFINITY));
        System.out.println("Double.compare(NaN,NaN): "
                + Double.compare(nanB, nanC));
        System.out.println("raw NaN payloads differ: "
                + (Double.doubleToRawLongBits(nanB)
                != Double.doubleToRawLongBits(nanC)));
        System.out.println("Double.equals(+0,-0): "
                + Double.valueOf(posZero).equals(Double.valueOf(negZero)));
        System.out.println("Double.equals(NaN,NaN): "
                + Double.valueOf(nanB).equals(Double.valueOf(nanC)));
        System.out.println("Float.compare(-0f,+0f): "
                + Float.compare(-0.0f, 0.0f));
        System.out.println("Float.compare(NaN,Infinity): "
                + Float.compare(Float.NaN, Float.POSITIVE_INFINITY));

        List<Double> values = new ArrayList<>(Arrays.asList(
                Double.NaN, 3.0, -0.0, Double.NEGATIVE_INFINITY,
                +0.0, Double.POSITIVE_INFINITY, -5.0, Double.NaN));
        values.sort(Double::compare);
        System.out.println("sorted: " + values);

        Set<Double> tree = new TreeSet<>(values);
        System.out.println("tree: " + tree);
        System.out.println("tree size: " + tree.size());
        System.out.println("nanB == nanC: " + (nanB == nanC));
    }
}
~~~

Lệnh chạy:

~~~bash
javac CompareDemo.java
java CompareDemo
~~~

Kết quả stdout:

~~~text
primitive +0 == -0: true
primitive NaN == NaN: false
primitive NaN < Infinity: false
Double.compare(-0,+0): -1
Double.compare(+0,-0): 1
Double.compare(NaN,+Infinity): 1
Double.compare(NaN,NaN): 0
raw NaN payloads differ: true
Double.equals(+0,-0): false
Double.equals(NaN,NaN): true
Float.compare(-0f,+0f): -1
Float.compare(NaN,Infinity): 1
sorted: [-Infinity, -5.0, -0.0, 0.0, 3.0, Infinity, NaN, NaN]
tree: [-Infinity, -5.0, -0.0, 0.0, 3.0, Infinity, NaN]
tree size: 7
nanB == nanC: false
~~~

Đầu ra cho thấy điều tưởng nghịch lý: `nanB == nanC` là `false` nhưng `Double.compare(nanB,nanC)` là 0, và hai số 0 có dấu có quan hệ ngược lại. Vì `TreeSet` dùng thứ tự tự nhiên của `Double`, nó giữ hai số 0 có dấu và gộp NaN trùng nhau.

## 9. `compare` không phải phép so sánh số gần bằng

Giả sử hai kết quả tính toán gần nhau do sai số dấu phẩy động. `Double.compare(a,b) == 0` chỉ nhận ra **bằng nhau theo thứ tự wrapper**, không tự áp dụng sai số cho phép (*tolerance*). Không dùng nó thay logic so sánh gần đúng của nghiệp vụ.

Ví dụ:

~~~java
double x = 0.1 + 0.2;
double y = 0.3;

boolean exactlyEqual = Double.compare(x, y) == 0; // false
~~~

Nếu bài toán có tolerance, bạn cần quy định đơn vị/độ lớn sai số. Ví dụ đơn giản với số hữu hạn trong miền không gây overflow khi trừ:

~~~java
static boolean approximatelyEqual(
        double a, double b, double absoluteTolerance) {
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }
    if (!Double.isFinite(absoluteTolerance)
            || absoluteTolerance < 0.0) {
        throw new IllegalArgumentException("Invalid tolerance");
    }
    return Math.abs(a - b) <= absoluteTolerance;
}
~~~

Đây là **phương thức minh họa**, cần đặt trong một lớp. Với độ lớn cực lớn, hiệu `a-b` có thể overflow thành vô cực; nhiều bài toán cần kết hợp tolerance tuyệt đối/tương đối với thuật toán phù hợp miền giá trị. Cần quyết định riêng cách xử lý NaN và infinities, vì chúng không có nghĩa “gần bằng” số hữu hạn chỉ nhờ một epsilon.

Đối với **sắp xếp, khóa dữ liệu, tìm kiếm nhị phân**, tránh dùng comparator dựa trên epsilon tùy ý vì quan hệ gần bằng có thể **không bắc cầu** (ví dụ A gần B, B gần C nhưng A không gần C), vi phạm hợp đồng comparator. Dùng `Double.compare` làm thứ tự và tách riêng logic gần bằng.

## 10. Cách chọn phép so sánh

| Nhu cầu | Công cụ thích hợp | Lưu ý |
| --- | --- | --- |
| Quan hệ số học thông thường giữa primitive | `<`, `>`, `==` ... | NaN làm các quan hệ có thứ tự luôn false; ±0 bằng nhau |
| Kiểm tra NaN | `Double.isNaN` / `Float.isNaN` | Không dùng `x == NaN` |
| Định nghĩa thứ tự ổn định để sort | `Double.compare` / `Float.compare` | `-0 < +0 < Infinity < NaN` |
| So sánh wrapper theo hợp đồng equals | `Double.equals` / `Float.equals` | NaN bằng NaN; ±0 khác nhau |
| Kiểm tra đầu vào hữu hạn | `Double.isFinite` / `Float.isFinite` | Loại NaN và vô cực |
| So sánh kết quả gần bằng | Hàm tolerance có đặc tả nghiệp vụ | Không dùng epsilon comparator cho ordered collections |
| Kiểm tra đúng mẫu bit kể cả NaN payload | `doubleToRawLongBits` / `floatToRawIntBits` | Cần chính sách bit-level riêng |

Sai lầm phổ biến cần tránh là triển khai comparator:

~~~java
// CỐ Ý SAI nếu dữ liệu có NaN hoặc số 0 có dấu:
static int brokenCompare(double a, double b) {
    if (a < b) return -1;
    if (a > b) return 1;
    return 0;
}
~~~

Với `a = Double.NaN` và `b = 5.0`, hàm trên trả 0, dù hai giá trị không tương đương. Với `-0.0` và `+0.0`, hàm cũng trả 0, khác hợp đồng thứ tự của `Double`. Phiên bản đúng cho dữ liệu `double` là:

~~~java
static int correctCompare(double a, double b) {
    return Double.compare(a, b);
}
~~~

Hai đoạn là **phương thức độc lập để minh họa**, không phải các chương trình chạy có `main`.

## 11. Câu hỏi tự luyện

1. `Double.compare(-0.0, +0.0)` âm, 0 hay dương? `-0.0 == +0.0` thì sao?
2. `Double.NaN > Double.POSITIVE_INFINITY` có trả `true` không? `Double.compare(Double.NaN, Double.POSITIVE_INFINITY)` trả dấu nào?
3. Hai NaN có payload bit khác nhau có thể cùng tồn tại như hai phần tử riêng trong `TreeSet<Double>` dùng natural order không?
4. Vì sao `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` trả `true`, nhưng `Double.NaN == Double.NaN` trả `false`?
5. Comparator dùng `a < b ? -1 : a > b ? 1 : 0` có gì nguy hiểm khi so sánh NaN? Có nên dùng epsilon comparator cho `TreeMap` không?

**Đáp án:** (1) âm; toán tử primitive trả `true`. (2) toán tử `>` trả `false`, còn `Double.compare` dương. (3) Không, `Double.compare` coi mọi NaN tương đương nên set chỉ có một giá trị NaN. (4) Wrapper áp dụng quy tắc bằng nhau theo bit canonical, còn primitive NaN là unordered. (5) Hàm trả 0 với NaN và nhiều số không tương đương; epsilon comparator có thể vi phạm tính bắc cầu, vì vậy không dùng cho collection có thứ tự.

## Tài liệu tham khảo

- [Java SE 21: Double.compare, equals, compareTo](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html).
- [Java SE 21: Float.compare, equals, compareTo](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Float.html).
- [JLS `15.20 và `15.21: Relational and Equality Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20).
- [Java SE 21: Comparator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html), [TreeSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html).
