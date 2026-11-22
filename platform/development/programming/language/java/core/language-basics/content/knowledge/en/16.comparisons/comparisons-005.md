# NaN và những kết quả so sánh khác trực giác — Java 17+

`NaN` (*Not a Number*) là một giá trị đặc biệt thuộc các kiểu số thực `float` và `double` của Java, không phải `null` hoặc ngoại lệ. Các phép tính không xác định có thể trả về NaN:

~~~java
double nan = 0.0 / 0.0;
double alsoNan = Math.sqrt(-1.0);
~~~

**Điểm khác trực giác:** với các phép so sánh số thực primitive, NaN **không bằng chính nó**. Nếu ít nhất một toán hạng là NaN thì các phép `==`, `<`, `<=`, `>` và `>=` đều **false**, trong khi `!=` là **true**.

~~~java
double x = Double.NaN;
System.out.println(x == x);    // false.
System.out.println(x != x);    // true.
System.out.println(x < 10.0);  // false.
System.out.println(x >= 10.0); // false.
~~~

Vì vậy **`!(x > 10)` không luôn tương đương `x <= 10`**. Khi `x` là NaN, biểu thức đầu là true còn biểu thức sau false.

## 1. Bảng quy tắc so sánh NaN

Giả sử `double x = Double.NaN`:

| Biểu thức | Kết quả | Giải thích |
| --- | --- | --- |
| `x == x` | false | NaN không bằng chính nó theo `==` |
| `x != x` | true | Quy tắc so sánh khác với NaN |
| `x < 5.0` | false | Không xác định quan hệ thứ tự |
| `x <= 5.0` | false | Không thể suy từ “không lớn hơn” |
| `x > 5.0` | false | Không xác định quan hệ thứ tự |
| `x >= 5.0` | false | Không xác định quan hệ thứ tự |
| `5.0 < x` | false | NaN ở toán hạng phải cũng vậy |
| `!(x > 5.0)` | true | Phủ định một phép so sánh trả false |
| `Double.isNaN(x)` | true | Kiểm tra NaN đúng mục đích |

Các quy tắc tương ứng cũng áp dụng cho `float`. **Không dùng `x == Double.NaN` để kiểm tra NaN**; dùng `Double.isNaN(x)` hoặc `Float.isNaN(x)`.

## 2. Demo Java 17+ tự chứa, chạy bằng CLI

Tạo tệp UTF-8 có tên **`NaNComparisonDemo.java`**:

~~~java
import java.util.TreeSet;

public class NaNComparisonDemo {
    public static void main(String[] args) {
        double nan = 0.0 / 0.0;

        System.out.println("== primitive ==");
        System.out.println("nanIsNaN=" + Double.isNaN(nan));
        System.out.println("nanEqSelf=" + (nan == nan));
        System.out.println("nanNeSelf=" + (nan != nan));
        System.out.println("nanLess=" + (nan < 5.0));
        System.out.println("nanLessEqual=" + (nan <= 5.0));
        System.out.println("nanGreater=" + (nan > 5.0));
        System.out.println("nanGreaterEqual=" + (nan >= 5.0));
        System.out.println("reverseLess=" + (5.0 < nan));
        System.out.println("notGreater=" + (!(nan > 5.0)));
        System.out.println("lessOrEqual=" + (nan <= 5.0));

        System.out.println("== detecting ==");
        System.out.println("sqrtNaN="
                + Double.isNaN(Math.sqrt(-1.0)));
        System.out.println("infinityMinusInfinityNaN="
                + Double.isNaN(Double.POSITIVE_INFINITY
                        - Double.POSITIVE_INFINITY));
        System.out.println("nanPlusOne="
                + Double.isNaN(nan + 1.0));
        System.out.println("parsedNaN="
                + Double.isNaN(Double.parseDouble("NaN")));
        System.out.println("nanFinite=" + Double.isFinite(nan));
        System.out.println("fiveFinite=" + Double.isFinite(5.0));
        System.out.println("infinityFinite="
                + Double.isFinite(Double.POSITIVE_INFINITY));
        System.out.println("mathMinNaN="
                + Double.isNaN(Math.min(nan, 3.0)));

        System.out.println("== wrapper and ordering ==");
        Double first = Double.valueOf(Double.NaN);
        Double second = Double.valueOf(Double.NaN);
        System.out.println("wrapperEquals=" + first.equals(second));
        System.out.println("compareNaNs=" + Double.compare(nan, nan));
        System.out.println("nanAfterInfinity="
                + (Double.compare(nan, Double.POSITIVE_INFINITY) > 0));

        double positiveZero = 0.0;
        double negativeZero = -0.0;
        System.out.println("zerosPrimitiveEqual="
                + (positiveZero == negativeZero));
        System.out.println("zerosWrapperEqual="
                + Double.valueOf(positiveZero)
                        .equals(Double.valueOf(negativeZero)));
        System.out.println("compareZeros="
                + Double.compare(positiveZero, negativeZero));
        System.out.println("reciprocalNegZero="
                + (1.0 / negativeZero));

        TreeSet<Double> sorted = new TreeSet<>();
        sorted.add(Double.NaN);
        sorted.add(Double.NaN);
        sorted.add(Double.POSITIVE_INFINITY);
        sorted.add(Double.NEGATIVE_INFINITY);
        sorted.add(positiveZero);
        sorted.add(negativeZero);
        System.out.println("sorted=" + sorted);
        System.out.println("sortedSize=" + sorted.size());

        System.out.println("== float and precision ==");
        float fn = Float.NaN;
        System.out.println("floatEqualsSelf=" + (fn == fn));
        System.out.println("floatIsNaN=" + Float.isNaN(fn));

        double sum = 0.1 + 0.2;
        System.out.println("decimalSum=" + sum);
        System.out.println("decimalExactlyEqual=" + (sum == 0.3));

        boolean validScore = Double.isFinite(nan)
                && nan >= 0.0 && nan <= 100.0;
        System.out.println("nanValidScore=" + validScore);
    }
}
~~~

Yêu cầu **JDK 17 trở lên**. Mở PowerShell (Windows) hoặc Bash (Linux/macOS) tại thư mục chứa file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 NaNComparisonDemo.java
java NaNComparisonDemo
~~~

**Expected stdout chính xác** của lệnh `java NaNComparisonDemo` (không tính đầu ra phiên bản JDK):

~~~text
== primitive ==
nanIsNaN=true
nanEqSelf=false
nanNeSelf=true
nanLess=false
nanLessEqual=false
nanGreater=false
nanGreaterEqual=false
reverseLess=false
notGreater=true
lessOrEqual=false
== detecting ==
sqrtNaN=true
infinityMinusInfinityNaN=true
nanPlusOne=true
parsedNaN=true
nanFinite=false
fiveFinite=true
infinityFinite=false
mathMinNaN=true
== wrapper and ordering ==
wrapperEquals=true
compareNaNs=0
nanAfterInfinity=true
zerosPrimitiveEqual=true
zerosWrapperEqual=false
compareZeros=1
reciprocalNegZero=-Infinity
sorted=[-Infinity, -0.0, 0.0, Infinity, NaN]
sortedSize=5
== float and precision ==
floatEqualsSelf=false
floatIsNaN=true
decimalSum=0.30000000000000004
decimalExactlyEqual=false
nanValidScore=false
~~~

## 3. Phủ định một quan hệ không tự tạo ra quan hệ đối nghịch

Với hai số hữu hạn thông thường, lập trình viên có thể xem `!(a > b)` tương đương `a <= b`. Nhưng với NaN:

~~~java
double a = Double.NaN;
double b = 5.0;
boolean negated = !(a > b); // true.
boolean opposite = a <= b; // false.
~~~

Bảng sau cho thấy những biến đổi **không được dùng mù quáng** khi có NaN:

| Biểu thức phủ định | Biểu thức thay thế tưởng tương đương | Kết quả khi `a` là NaN |
| --- | --- | --- |
| `!(a > b)` | `a <= b` | true so với false |
| `!(a >= b)` | `a < b` | true so với false |
| `!(a < b)` | `a >= b` | true so với false |
| `!(a <= b)` | `a > b` | true so với false |
| `!(a == b)` | `a != b` | Cả hai true |

Chỉ hàng cuối luôn giữ quan hệ phủ định trực tiếp giữa `==` và `!=`. Những cặp toán tử thứ tự không còn là các phép phủ định đối nhau khi có NaN.

Đặc biệt, điều kiện `!(score > 100)` sẽ nhận cả giá trị NaN, nên **không dùng nó một mình để xác thực điểm**. Nếu chỉ chấp nhận số hữu hạn trong đoạn [0, 100]:

~~~java
static boolean validScore(double score) {
    return Double.isFinite(score)
            && score >= 0.0
            && score <= 100.0;
}
~~~

`Double.isFinite` từ chối NaN và cả ±Infinity. Toán tử `&&` ngắn mạch nên nếu phần kiểm tra hữu hạn false thì các điều kiện sau không cần đánh giá.

## 4. Primitive `==`, wrapper `equals` và `Double.compare` khác nhau

~~~java
double nan = Double.NaN;

System.out.println(nan == nan); // false.
System.out.println(Double.valueOf(nan)
        .equals(Double.valueOf(nan))); // true.
System.out.println(Double.compare(nan, nan)); // 0.
~~~

| Cơ chế | Hai NaN | `+0.0` và `-0.0` |
| --- | --- | --- |
| Primitive `double ==` | Không bằng | Bằng |
| `Double.equals` | Bằng | Không bằng |
| `Double.compare` | Trả 0 | Phân biệt, `compare(+0.0, -0.0) > 0` |

`Double.compare(a, b)` xác lập thứ tự tổng phù hợp để sắp xếp: NaN **đứng sau mọi giá trị `double` khác**, kể cả `Infinity`; hai NaN được xem là tương đương theo thứ tự đó. Đây là quy tắc **phương thức so sánh**, không thay đổi hành vi của toán tử quan hệ primitive:

~~~java
Double.compare(Double.NaN, Double.POSITIVE_INFINITY) > 0 // true.
Double.NaN > Double.POSITIVE_INFINITY // false.
~~~

Lưu ý: `==` giữa **hai đối tượng `Double`** là phép so sánh tham chiếu. Để so giá trị wrapper, dùng `equals` hoặc `compare` đúng hợp đồng; muốn dùng toán tử primitive thì phải unbox và kiểm tra null khi cần.

## 5. Vì sao `TreeSet<Double>` sắp xếp NaN ở cuối?

`TreeSet<Double>` sử dụng thứ tự tự nhiên của `Double.compareTo`. Ví dụ:

~~~java
TreeSet<Double> set = new TreeSet<>();
set.add(Double.NaN);
set.add(-0.0);
set.add(+0.0);
set.add(Double.POSITIVE_INFINITY);
set.add(Double.NEGATIVE_INFINITY);
~~~

Thứ tự phần tử là:

~~~text
[-Infinity, -0.0, 0.0, Infinity, NaN]
~~~

- `-Infinity` đứng trước các số hữu hạn.
- `-0.0` và `+0.0` là **hai phần tử khác nhau** theo comparator.
- `Infinity` đứng trước NaN.
- Thêm NaN lần nữa không tạo phần tử NaN thứ hai vì `Double.compare` coi các NaN tương đương.

Kết quả không mâu thuẫn với `NaN == NaN` false: container dùng **comparator**, còn biểu thức dùng phép toán trên giá trị primitive.

## 6. Hai số không có dấu `+0.0` và `-0.0`

~~~java
double plus = 0.0;
double minus = -0.0;

System.out.println(plus == minus);       // true.
System.out.println(Double.compare(plus, minus)); // 1.
System.out.println(1.0 / minus);         // -Infinity.
~~~

Primitive `==` coi hai giá trị zero bằng nhau, nhưng dấu vẫn được giữ trong biểu diễn số thực và các phép tính như nghịch đảo. `Double.equals` và `Double.compare` phân biệt chúng.

Vì vậy, cũng đừng dùng các phép `<`, `>` primitive để suy luận về bit dấu của zero: `-0.0 < +0.0` là false, còn `-0.0 <= +0.0` là true.

## 7. NaN khác vô cực và sai số nhị phân

| Hiện tượng | Ví dụ | Cách kiểm tra hoặc xử lý |
| --- | --- | --- |
| NaN | `0.0 / 0.0`, `Math.sqrt(-1.0)` | `Double.isNaN` |
| ±Infinity | `1.0 / 0.0`, `-1.0 / 0.0` | `Double.isInfinite` |
| Số hữu hạn | `5.0`, `-0.0` | `Double.isFinite` |
| Sai số làm tròn | `0.1 + 0.2` | Phân tích độ chính xác của `double` |

~~~java
double sum = 0.1 + 0.2;
System.out.println(sum);         // 0.30000000000000004.
System.out.println(sum == 0.3);  // false.
~~~

`sum` là số **hữu hạn**, không phải NaN. Sai khác là do biểu diễn số thực **nhị phân**, không do quy tắc so sánh NaN. Nếu yêu cầu thập phân chính xác như tiền tệ, cân nhắc `BigDecimal` tạo từ chuỗi và quy tắc scale/làm tròn; với đại lượng đo lường, cần quy tắc sai số thích hợp theo miền giá trị.

## 8. Các hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`x == Double.NaN` phát hiện NaN.” | Luôn false khi so primitive; dùng `Double.isNaN(x)` |
| “Nếu không nhỏ hơn thì chắc lớn hơn hoặc bằng.” | Sai với NaN |
| “`NaN != NaN` phải false vì cùng tên.” | Primitive `!=` trả true |
| “`Double.compare(NaN, NaN)` trả khác 0.” | Trả 0 |
| “`Double.equals` luôn giống `double ==`.” | Khác nhau với NaN và ±0.0 |
| “`0.0` và `-0.0` giống nhau trong mọi API.” | Comparator, wrapper và phép nghịch đảo phân biệt |
| “`Double.parseDouble("NaN")` ném lỗi.” | Có thể parse thành NaN |
| “`Double.isFinite` xác nhận số thập phân chính xác.” | Chỉ xác nhận không phải NaN/Infinity |

## 9. Bài tập và đáp án

1. `Double.NaN == Double.NaN` và `Double.NaN != Double.NaN` là gì?  
   *Đáp án:* `false` và `true`.
2. Với `double x = Double.NaN`, bốn quan hệ `x < 1`, `x <= 1`, `x > 1`, `x >= 1`?  
   *Đáp án:* Tất cả false.
3. `!(x > 1)` và `x <= 1` ra sao khi x là NaN?  
   *Đáp án:* true và false.
4. `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))`?  
   *Đáp án:* true.
5. `Double.compare(Double.NaN, Double.POSITIVE_INFINITY) > 0`?  
   *Đáp án:* true, theo thứ tự `Double.compare`.
6. `0.0 == -0.0` và wrapper `equals` hai zero?  
   *Đáp án:* true và false.
7. `Double.isNaN(0.1 + 0.2)` có true không?  
   *Đáp án:* false; kết quả xấp xỉ hữu hạn `0.30000000000000004`.
8. Cách kiểm tra `score` thuộc [0,100] và từ chối cả NaN/Infinity?  
   *Đáp án:* `Double.isFinite(score) && score >= 0 && score <= 100`.

## Checklist ghi nhớ

- [ ] NaN thuộc `float`/`double`, không phải null hay exception.
- [ ] Với NaN, `==`/`<`/`<=`/`>`/`>=` trả false và `!=` trả true.
- [ ] Dùng `Double.isNaN` hoặc `Float.isNaN`, không so với hằng NaN.
- [ ] `!(a > b)` không tương đương `a <= b` khi có NaN.
- [ ] Phân biệt primitive `==`, wrapper `Double.equals` và `Double.compare`.
- [ ] `Double.compare` xếp NaN sau Infinity, phân biệt signed zero.
- [ ] Dùng `Double.isFinite` nếu chỉ chấp nhận giá trị hữu hạn.
- [ ] Không nhầm sai số nhị phân hữu hạn với NaN.

**Kết luận:** NaN khiến nhiều kết quả so sánh số thực Java **khác trực giác**. Muốn viết điều kiện đúng, phải hiểu **quy tắc phép toán primitive**, phân biệt nó với **wrapper/comparator**, rồi kiểm tra rõ các giá trị đặc biệt mà nghiệp vụ cho phép.
