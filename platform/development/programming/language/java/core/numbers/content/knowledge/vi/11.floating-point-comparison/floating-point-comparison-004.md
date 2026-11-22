# `+0.0` và `-0.0` với toán tử `==` trong Java

Trong Java, hai giá trị dấu phẩy động `+0.0` (zero dương) và `-0.0` (zero âm) **bằng nhau theo toán tử so sánh số học `==`**:

```java
System.out.println(+0.0 == -0.0);  // true
System.out.println(0.0f == -0.0f);  // true
```

Tuy nhiên, chúng **không có biểu diễn bit giống nhau** và **không thể thay thế nhau trong mọi phép toán**. Ví dụ:

```java
System.out.println(1.0 / +0.0); // Infinity
System.out.println(1.0 / -0.0); // -Infinity
```

Điểm quan trọng của bài học là phân biệt **bằng nhau theo số học**, **giống nhau về biểu diễn**, và **bằng nhau theo các API đối tượng** như `Double.equals` hoặc `Double.compare`. Ba khái niệm này cho kết quả khác nhau với signed zero.

## 1. Tại sao số 0 lại có dấu?

Java dùng dấu phẩy động nhị phân theo IEEE 754 cho `float` và `double`. Một giá trị dấu phẩy động có **bit dấu** riêng ngoài phần số mũ và phần trị. Do vậy `0.0` và `-0.0` là hai mẫu bit hợp lệ khác nhau:

| Kiểu | `+0.0` (hex bit pattern) | `-0.0` (hex bit pattern) |
| --- | --- | --- |
| `float` (32 bit) | `0x00000000` | `0x80000000` |
| `double` (64 bit) | `0x0000000000000000` | `0x8000000000000000` |

Ở cả hai kiểu, phần trị và phần số mũ đều bằng 0; chỉ bit dấu khác nhau. Thông thường `0.0` viết không có dấu là dương zero; biểu thức `-0.0` tạo âm zero.

```java
double positiveZero = 0.0;
double negativeZero = -0.0;

System.out.println(positiveZero); // 0.0
System.out.println(negativeZero); // -0.0
```

Việc Java có hai zero không có nghĩa nó có hai giá trị số nguyên 0. Các kiểu `byte`, `short`, `int`, `long` không có âm zero riêng: biểu thức nguyên `-0` có cùng biểu diễn và giá trị `0`. Signed zero là đặc điểm của `float`/`double`.

### Dấu zero có thể xuất hiện từ phép tính

Âm zero không chỉ có thể viết bằng literal. Ví dụ một giá trị âm rất nhỏ có thể **underflow** về `-0.0` khi kết quả quá gần 0:

```java
double verySmallNegative = -Double.MIN_VALUE;
double roundedToNegativeZero = verySmallNegative / 2.0;
// -0.0
```

`Double.MIN_VALUE` là số `double` dương nhỏ nhất lớn hơn 0, không phải giá trị âm có độ lớn lớn nhất. Vì vậy `-Double.MIN_VALUE` là một giá trị âm rất nhỏ; chia thêm cho 2 làm tròn thành âm zero.

## 2. `==` coi `+0.0` và `-0.0` bằng nhau

Với toán hạng primitive số thực, Java áp dụng quy tắc **floating-point equality**. Trong đó `+0.0` và `-0.0` được xem là **bằng nhau**, còn `NaN` không bằng bất kỳ giá trị nào, kể cả chính nó.

```java
double a = +0.0;
double b = -0.0;

System.out.println(a == b); // true
System.out.println(a != b); // false
System.out.println(a < b);  // false
System.out.println(a > b);  // false
System.out.println(a <= b); // true
System.out.println(a >= b); // true
```

Ở ngữ cảnh so sánh số học, cả hai zero có cùng vị trí tại gốc trục số. `==` **không kiểm tra bit dấu**; nó trả lời rằng hai giá trị số có bằng nhau theo quy tắc toán tử Java hay không.

Bảng tóm tắt:

| Biểu thức | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `+0.0 == -0.0` | `true` | Bằng nhau theo số học |
| `+0.0 != -0.0` | `false` | Không được xem là khác nhau |
| `-0.0 < +0.0` | `false` | Không nhỏ hơn theo phép so sánh số |
| `-0.0 <= +0.0` | `true` | Có bằng nhau |
| `Double.NaN == Double.NaN` | `false` | Quy tắc riêng của NaN |

Cần chú ý **kiểu toán hạng**. `0.0` là literal `double`, `0.0f` là literal `float`. Nếu so sánh `+0.0f == -0.0`, toán hạng `float` được mở rộng thành `double` rồi so sánh; kết quả vẫn `true`.

## 3. Bằng nhau về số học không có nghĩa giống bit

Có thể đọc bit của `double` và `float` bằng các phương thức chuyên dụng:

```java
long pos = Double.doubleToRawLongBits(+0.0);
long neg = Double.doubleToRawLongBits(-0.0);

System.out.println(Long.toHexString(pos)); // 0
System.out.println(Long.toHexString(neg)); // 8000000000000000
System.out.println(pos == neg);            // false
```

Với `float`:

```java
int pos = Float.floatToRawIntBits(+0.0f);
int neg = Float.floatToRawIntBits(-0.0f);

System.out.println(Integer.toHexString(pos)); // 0
System.out.println(Integer.toHexString(neg)); // 80000000
```

`Double.doubleToRawLongBits` và `Float.floatToRawIntBits` rất hữu ích khi debug biểu diễn bit, giao thức nhị phân hoặc lỗi số học. Với signed zero, phương thức có hoặc không có chữ `Raw` đều phân biệt dấu; khác biệt quan trọng của phiên bản `Raw` là cách giữ nguyên các mẫu bit NaN thay vì canonicalize NaN.

**Không nhầm** hai loại phép so sánh:

```java
double x = +0.0;
double y = -0.0;

boolean equalAsNumbers = x == y; // true
boolean sameBitPattern =
        Double.doubleToRawLongBits(x) == Double.doubleToRawLongBits(y); // false
```

Nếu nghiệp vụ chỉ cần so sánh giá trị số, thường dùng `==` là có ý nghĩa cho trường hợp zero. Nếu nghiệp vụ cần phân biệt dấu zero (chẳng hạn tính toán khoa học), phải chọn cách kiểm tra phù hợp.

## 4. Vì sao `1.0 / +0.0` khác `1.0 / -0.0`?

Phép chia dấu phẩy động theo IEEE 754 **sử dụng dấu của zero**. Khi tử số hữu hạn và khác 0, còn mẫu là zero, kết quả là vô cực với dấu tương ứng.

| Phép chia | Kết quả |
| --- | --- |
| `1.0 / +0.0` | `Infinity` |
| `1.0 / -0.0` | `-Infinity` |
| `-1.0 / +0.0` | `-Infinity` |
| `-1.0 / -0.0` | `Infinity` |
| `+0.0 / +0.0` | `NaN` |
| `-0.0 / +0.0` | `NaN` |

Vì vậy:

```java
double x = +0.0;
double y = -0.0;

System.out.println(x == y);  // true
System.out.println(1.0 / x); // Infinity
System.out.println(1.0 / y); // -Infinity
```

**Không mâu thuẫn:** `==` hỏi hai số có bằng nhau về giá trị không; phép chia có quy tắc sử dụng bit dấu để chọn dấu vô cực. Hai giá trị có thể bằng nhau theo một quan hệ so sánh nhưng ảnh hưởng khác nhau tới một phép toán khác.

Đối với `int` hoặc `long`, chia cho 0 ném `ArithmeticException` khi thực thi. Chỉ vì biểu thức có biến đích `double` không làm phép chia nguyên tự trở thành chia số thực:

```java
int numerator = 1;
int denominator = 0;
// double invalid = numerator / denominator; // nếu chạy: ArithmeticException
double floating = (double) numerator / denominator; // Infinity
```

Đây là đoạn **minh họa** chứ không phải chương trình độc lập. Chú ý chuyển một toán hạng sang `double` **trước** phép chia để chọn quy tắc floating-point.

## 5. `Double.compare` và `Double.equals` lại phân biệt dấu zero

Đây là điểm dễ gây ngạc nhiên nhất khi chuyển từ primitive sang wrapper `Double`:

```java
System.out.println(Double.compare(-0.0, +0.0)); // -1
System.out.println(Double.compare(+0.0, -0.0)); // 1

System.out.println(Double.valueOf(-0.0)
        .equals(Double.valueOf(+0.0))); // false
```

`Double.compare` tạo một thứ tự nhất quán để sắp xếp số thực theo quy tắc wrapper; nó xem **`-0.0` đứng trước `+0.0`**. `Double.equals` định nghĩa bằng nhau theo biểu diễn chuẩn hóa bit của wrapper, nên **không coi hai zero khác dấu là bằng nhau**.

| Cách kiểm tra | `-0.0` so với `+0.0` |
| --- | --- |
| Primitive `a == b` | `true` |
| Primitive `a != b` | `false` |
| `Double.compare(a, b) == 0` | `false` |
| `Double.valueOf(a).equals(Double.valueOf(b))` | `false` |
| So sánh bit bằng `Double.doubleToLongBits` | Khác nhau |

`Double.compare` trả số âm, 0 hoặc số dương, tùy thứ tự; không nên xây dựng thuật toán đòi hỏi mọi kết quả khác nhau phải chính xác bằng `-1` hoặc `1` theo một quy tắc chung cho các comparator khác.

### Tại sao wrapper cần cách hiểu khác?

`Double.equals` và `Double.hashCode` có hợp đồng phù hợp cho các cấu trúc dữ liệu kiểu `HashMap` hoặc `HashSet`. Java wrapper muốn phân biệt signed zero như hai khóa riêng; đồng thời xử lý NaN nhất quán trong `equals` và `compare`.

```java
java.util.Set<Double> values = new java.util.HashSet<>();
values.add(+0.0);
values.add(-0.0);
System.out.println(values.size()); // 2
```

Nếu so sánh primitive `+0.0 == -0.0` ta được `true`, nhưng một `HashSet<Double>` có thể chứa cả hai phần tử và coi chúng là **hai key khác nhau**. Đây là hệ quả có thật khi lưu kết quả tính toán trong collection.

### Không dùng `==` giữa hai object `Double` để hỏi giá trị

`==` trên **hai tham chiếu object** hỏi chúng có trỏ đến cùng object không, khác hoàn toàn với `==` trên primitive `double`:

```java
Double first = Double.valueOf(+0.0);
Double second = Double.valueOf(-0.0);

// first == second: so sánh identity tham chiếu, không phải numeric equality
boolean primitiveEqual = first.doubleValue() == second.doubleValue(); // true
boolean objectEqual = first.equals(second); // false
```

Đừng diễn giải kết quả của `first == second` thành quy tắc signed zero: đó là câu hỏi về **identity của object**. Việc Java có tự boxing/unboxing trong một số ngữ cảnh không đồng nghĩa so sánh hai wrapper tham chiếu luôn unbox.

## 6. `Float` có quy tắc tương tự `Double`

Đối với `float`:

```java
float a = +0.0f;
float b = -0.0f;

System.out.println(a == b);                  // true
System.out.println(Float.compare(a, b));      // 1
System.out.println(Float.valueOf(a).equals(
        Float.valueOf(b)));                   // false
```

`Float.compare(-0.0f, +0.0f)` trả số âm; `Float.compare(+0.0f, -0.0f)` trả số dương. Vì vậy khi dùng `List<Float>` và sort, giá trị âm zero có thể xuất hiện trước dương zero dù phép `==` cho kết quả bằng nhau.

Một lưu ý khác: `Double.NaN == Double.NaN` trả `false`, nhưng `Double.compare(Double.NaN, Double.NaN) == 0` và `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` đều trả `true`. Wrapper có quan hệ bằng nhau phục vụ collection và sắp xếp, không hoàn toàn giống toán tử số học `==`.

## 7. `Math.copySign`, `Math.abs`, `Math.min` và `Math.max`

Để phát hiện hoặc bảo toàn dấu zero khi cần, Java có các API hữu ích.

### `Math.copySign`: đọc dấu zero mà không so sánh bit

`Math.copySign(magnitude, sign)` trả giá trị có **độ lớn lấy từ đối số đầu** và **dấu từ đối số thứ hai**.

```java
System.out.println(Math.copySign(1.0, +0.0)); // 1.0
System.out.println(Math.copySign(1.0, -0.0)); // -1.0
```

Nếu chỉ cần xem một zero là dương hay âm, áp dụng `Math.copySign(1.0, zero)` có thể dễ đọc. Phương pháp này được dùng khi đã biết biến cần phân tích là zero; tránh suy luận mọi giá trị âm được gặp là âm zero.

### `Math.abs` có thể bỏ dấu âm zero

```java
System.out.println(Math.abs(-0.0));  // 0.0
```

Kết quả là dương zero. Nếu dấu zero có ý nghĩa trong thuật toán, phép lấy trị tuyệt đối đã làm mất thông tin đó.

### `Math.min` và `Math.max` xử lý signed zero riêng

Theo quy tắc Java:

```java
System.out.println(Math.min(+0.0, -0.0)); // -0.0
System.out.println(Math.max(+0.0, -0.0)); // 0.0
```

`Math.min` chọn `-0.0` khi gặp hai zero khác dấu; `Math.max` chọn `+0.0`. Như vậy không thể suy ra mọi API đều phải đối xử signed zero giống `==`.

Lưu ý thêm: có NaN tham gia `Math.min`/`Math.max` có thể tạo NaN; khi chọn giá trị min/max từ dữ liệu ngoài, cần cân nhắc chính sách xử lý NaN.

## 8. Các trường hợp sinh âm zero và cần giữ nó

Signed zero có giá trị trong một số bài toán số học:

- **Underflow:** kết quả âm rất nhỏ có thể làm tròn thành `-0.0`, lưu thông tin dấu của giá trị rất nhỏ trước khi làm tròn.
- **Phép nhân/chia:** dấu các toán hạng ảnh hưởng dấu zero hoặc vô cực trong kết quả.
- **Hàm toán học:** một số phép toán và hàm thư viện có thể dùng signed zero để chọn dấu kết quả hoặc giữ thông tin giới hạn một phía.

Ví dụ:

```java
double underflow = -Double.MIN_VALUE / 2.0; // -0.0
double fromProduct = -2.0 * 0.0;            // -0.0
double reciprocal = 1.0 / fromProduct;      // -Infinity
```

Nếu hệ thống tự chuyển mọi `-0.0` thành `+0.0`, hai loại giá trị sẽ vẫn bằng nhau theo `==`, nhưng một số bước tính sau đó có thể đổi kết quả.

Ở hệ thống thông thường chỉ cần coi zero là zero, việc phân biệt dấu có thể không cần thiết. **Phụ thuộc vào mục đích dữ liệu**: không phải mọi chương trình đều nên dùng so sánh bit thay thế `==`.

## 9. Thiết kế so sánh, sắp xếp và khóa tập hợp

Khi làm việc với zero có dấu, cần chọn **một quy tắc nhất quán**.

| Mục tiêu | Cách làm điển hình | Hệ quả |
| --- | --- | --- |
| Chỉ hỏi hai giá trị primitive có bằng nhau về số học? | `a == b` | `+0.0` bằng `-0.0`; NaN không bằng chính nó |
| Muốn phân biệt bit dấu zero | `Double.doubleToRawLongBits(a) == Double.doubleToRawLongBits(b)` | Hai zero khác nhau |
| Muốn thứ tự tương thích với wrapper `Double` | `Double.compare(a,b)` | `-0.0` đứng trước `+0.0` |
| Muốn dùng `Double` làm khóa map/set | `Double.equals`/`hashCode` theo collection | Hai zero khác dấu được xem là hai khóa |
| Muốn coi hai zero là một khóa | **Chuẩn hóa** `x == 0.0 ? 0.0 : x` trước khi làm khóa | Mất chủ đích phân biệt dấu |
| Cần giữ dấu zero qua xử lý | Giữ primitive/raw bits hoặc cấu trúc dữ liệu phù hợp | Không làm mất dấu do normalize hay `abs` |

Ví dụ chuẩn hóa trước khi lưu `Double` vào set:

```java
static double normalizeZero(double x) {
    return x == 0.0 ? 0.0 : x;
}
```

Method này là **đoạn đặt trong class**, không phải chương trình độc lập. Nó chuyển cả `-0.0` và `+0.0` về `+0.0`, còn các số khác được giữ nguyên. Với `NaN`, điều kiện `x == 0.0` là `false`, nên giá trị NaN được trả về không đổi. Đây là **chính sách chủ động** để coi signed zero tương đương theo khóa, không phải hành vi sẵn có của `Double.equals`.

Nếu dùng `TreeSet<Double>`, thứ tự mặc định dựa vào so sánh wrapper cũng phân biệt hai zero; khi dùng comparator riêng cho tập có thứ tự, comparator cần nhất quán với định nghĩa “trùng nhau” mà ứng dụng mong muốn.

## 10. Chương trình Java 17+ đầy đủ

Lưu thành tệp **`SignedZeroEqualityDemo.java`**:

```java
import java.util.HashSet;
import java.util.Set;

public class SignedZeroEqualityDemo {
    public static void main(String[] args) {
        double positive = +0.0;
        double negative = -0.0;

        System.out.println("primitiveEquals=" + (positive == negative));
        System.out.println("primitiveNotEquals=" + (positive != negative));
        System.out.println("negativeLess=" + (negative < positive));
        System.out.println("negativeLessOrEqual=" + (negative <= positive));

        System.out.println("positiveText=" + positive);
        System.out.println("negativeText=" + negative);
        System.out.println("positiveBits=" +
                Long.toHexString(Double.doubleToRawLongBits(positive)));
        System.out.println("negativeBits=" +
                Long.toHexString(Double.doubleToRawLongBits(negative)));
        System.out.println("rawBitsEqual=" +
                (Double.doubleToRawLongBits(positive)
                        == Double.doubleToRawLongBits(negative)));

        System.out.println("reciprocalPositive=" + (1.0 / positive));
        System.out.println("reciprocalNegative=" + (1.0 / negative));
        System.out.println("zeroOverZero=" + (positive / negative));

        System.out.println("compareNegativePositive=" +
                Double.compare(negative, positive));
        System.out.println("comparePositiveNegative=" +
                Double.compare(positive, negative));
        System.out.println("wrapperEquals=" +
                Double.valueOf(negative).equals(Double.valueOf(positive)));

        Set<Double> set = new HashSet<>();
        set.add(positive);
        set.add(negative);
        System.out.println("setSize=" + set.size());

        System.out.println("copySignPositive=" + Math.copySign(1.0, positive));
        System.out.println("copySignNegative=" + Math.copySign(1.0, negative));
        System.out.println("absNegative=" + Math.abs(negative));
        System.out.println("minZero=" + Math.min(positive, negative));
        System.out.println("maxZero=" + Math.max(positive, negative));

        System.out.println("floatEquals=" + (+0.0f == -0.0f));
        System.out.println("negativeFloatBits=" +
                Integer.toHexString(Float.floatToRawIntBits(-0.0f)));
        System.out.println("negativeUnderflow=" +
                (-Double.MIN_VALUE / 2.0));

        System.out.println("nanPrimitiveEquals=" + (Double.NaN == Double.NaN));
        System.out.println("nanWrapperCompare=" +
                Double.compare(Double.NaN, Double.NaN));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac SignedZeroEqualityDemo.java
java SignedZeroEqualityDemo
```

Kết quả chính xác:

```text
primitiveEquals=true
primitiveNotEquals=false
negativeLess=false
negativeLessOrEqual=true
positiveText=0.0
negativeText=-0.0
positiveBits=0
negativeBits=8000000000000000
rawBitsEqual=false
reciprocalPositive=Infinity
reciprocalNegative=-Infinity
zeroOverZero=NaN
compareNegativePositive=-1
comparePositiveNegative=1
wrapperEquals=false
setSize=2
copySignPositive=1.0
copySignNegative=-1.0
absNegative=0.0
minZero=-0.0
maxZero=0.0
floatEquals=true
negativeFloatBits=80000000
negativeUnderflow=-0.0
nanPrimitiveEquals=false
nanWrapperCompare=0
```

Dòng `primitiveEquals=true` đặt cạnh `rawBitsEqual=false` cho thấy rõ sự khác biệt giữa **so sánh giá trị số học** và **so sánh biểu diễn bit**. Các dòng `compareNegativePositive=-1`, `wrapperEquals=false` và `setSize=2` chứng minh rằng API wrapper không có cùng quy tắc bằng nhau với primitive `==`.

## 11. Lỗi phổ biến và checklist

| Hiểu nhầm | Giải thích đúng |
| --- | --- |
| “`+0.0 == -0.0` là `false` vì bit dấu khác nhau.” | Sai: `==` so sánh số học và cho `true`. |
| “`+0.0` và `-0.0` có cùng mọi hành vi.” | Sai: `1.0 / ±0.0` tạo vô cực khác dấu; các API khác cũng phân biệt. |
| “`Double.compare(+0.0,-0.0) == 0` vì `==` trả `true`.” | Sai: `Double.compare` xếp `-0.0` trước `+0.0`. |
| “`Double.valueOf(+0.0).equals(Double.valueOf(-0.0))` cho `true`.” | Sai: `Double.equals` phân biệt dấu zero. |
| “`HashSet<Double>` chắc chắn chỉ có một phần tử nếu thêm cả hai zero.” | Sai: có thể giữ hai khóa phân biệt theo `equals`. |
| “`Float` không có âm zero.” | Sai: `-0.0f` có bit dấu và các quy tắc tương ứng. |
| “Nếu Java in `-0.0` thì giá trị nhỏ hơn 0 theo `<`.” | Sai: `-0.0 < +0.0` cho `false`. |
| “`Math.abs(-0.0)` giữ âm zero.” | Sai: trả `+0.0`. |
| “`Double.NaN == Double.NaN` giống `Double.compare(NaN,NaN) == 0`.” | Sai: toán tử `==` cho `false`, `Double.compare` có thể cho `0`. |
| “So sánh hai `Double` object bằng `==` là so sánh giá trị.” | Sai: hai tham chiếu wrapper được `==` so sánh identity, trừ khi có ngữ cảnh unboxing khác. |

Khi xử lý zero có dấu, hãy kiểm tra:

1. **Đang so sánh primitive hay object?** `==` trên `double`/`float` coi hai zero bằng nhau; `==` trên hai wrapper tham chiếu lại xét identity.
2. **Muốn so sánh giá trị số học hay bit lưu trữ?** Chọn `==` hoặc `doubleToRawLongBits`/`floatToRawIntBits` tương ứng.
3. **Đang sắp xếp hoặc làm key của collection?** Hiểu `Double.compare`, `Double.equals` và `hashCode` phân biệt signed zero.
4. **Dấu zero có ý nghĩa ở các phép tiếp theo?** Kiểm tra phép chia, `Math.copySign`, underflow và các hàm có quy tắc dấu.
5. **Ứng dụng có muốn gộp hai zero không?** Chuẩn hóa rõ ràng trước khi lưu và so sánh bằng cấu trúc dữ liệu, thay vì giả định collection tự dùng primitive `==`.

**Ghi nhớ:** `+0.0 == -0.0` là **`true`** với primitive `float`/`double`. Tuy nhiên, **bit dấu khác nhau**, phép chia cho zero cho **vô cực khác dấu**, và `Double.compare`/`Double.equals` **phân biệt hai giá trị zero này**. Luôn chọn quy tắc so sánh phù hợp với mục tiêu của chương trình.