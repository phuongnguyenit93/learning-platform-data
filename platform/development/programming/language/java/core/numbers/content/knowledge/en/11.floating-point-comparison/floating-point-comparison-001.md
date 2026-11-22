# Toán tử `==`, `!=`, `<`, `<=`, `>` và `>=` khi so sánh số thực trong Java

Java cho phép so sánh các giá trị `float` và `double` bằng sáu toán tử: **`==`, `!=`, `<`, `<=`, `>` và `>=`**. Chúng trả về `boolean` và sử dụng **ngữ nghĩa so sánh số dấu phẩy động** của Java, không phải cách so sánh xấp xỉ theo suy luận toán học.

Các điểm cốt lõi:

- `==` kiểm tra **hai giá trị số học có bằng nhau theo so sánh dấu phẩy động hay không**, chứ không phải “hai số gần nhau”.
- `!=` trả về kết quả phủ định của `==`, kể cả với `NaN`.
- `<`, `<=`, `>`, `>=` kiểm tra quan hệ thứ tự. **Nếu có toán hạng `NaN`, cả bốn phép so sánh thứ tự đều là `false`.**
- **`NaN == NaN` là `false`**, nhưng **`NaN != NaN` là `true`**.
- **`+0.0 == -0.0` là `true`**, dù hai mẫu bit khác nhau.
- Các giá trị `float`/`double` có độ chính xác nhị phân hữu hạn. Vì vậy `0.1 + 0.2 == 0.3` có thể là `false`, không phải lỗi trình biên dịch.

Để so sánh giá trị tính toán có sai số, cần **quy tắc dung sai do bài toán quyết định**. Để sắp xếp tất cả giá trị, kể cả `NaN` và `-0.0`, có thể dùng `Double.compare`/`Float.compare` với quy tắc thứ tự **khác** các toán tử primitive.

## 1. Sáu toán tử hoạt động như thế nào?

| Toán tử | Ý nghĩa | Ví dụ | Kết quả |
| --- | --- | --- | --- |
| `==` | Bằng nhau về giá trị theo so sánh primitive | `1.5 == 1.5` | `true` |
| `!=` | Không bằng nhau | `1.5 != 2.5` | `true` |
| `<` | Nhỏ hơn | `1.5 < 2.5` | `true` |
| `<=` | Nhỏ hơn hoặc bằng | `2.5 <= 2.5` | `true` |
| `>` | Lớn hơn | `2.5 > 1.5` | `true` |
| `>=` | Lớn hơn hoặc bằng | `2.5 >= 2.5` | `true` |

Khi hai toán hạng là các số hữu hạn không phải `NaN`, chúng tuân theo thứ tự số học quen thuộc. Các toán tử trả `boolean`, không trả số -1/0/1.

```java
double x = 1.5;
double y = 2.5;

boolean a = x == y; // false
boolean b = x != y; // true
boolean c = x < y;  // true
boolean d = x <= y; // true
boolean e = x > y;  // false
boolean f = x >= y; // false
```

Với các phép `<`, `<=`, `>`, `>=`, hai toán hạng phải là kiểu số có thể so sánh bằng phép quan hệ. Java không hỗ trợ so sánh thứ tự hai `String` bằng `<`; `String` dùng cách so sánh riêng như `compareTo` nếu bài toán cần.

## 2. Quy tắc nâng kiểu toán hạng trước khi so sánh

Khi so sánh hai giá trị thuộc kiểu số primitive khác nhau, Java áp dụng **binary numeric promotion**. Nếu một toán hạng là `double`, toán hạng còn lại được đưa sang `double`; nếu có `float` mà không có `double`, phép so sánh dùng `float`; với các kiểu số nguyên thì quy tắc nâng kiểu số nguyên áp dụng.

```java
float f = 0.1f;
double d = 0.1;

boolean equal = f == d; // false
```

Tại sao `equal` là false? Literal `0.1f` đã được làm tròn theo độ chính xác `float` (24 bit phần trị hiệu dụng). Khi `f` được mở rộng sang `double` để so sánh, nó mang giá trị `float` đã làm tròn chứ **không khôi phục** đúng cùng mẫu giá trị của literal `double 0.1`. Do vậy, dù mã nguồn đều viết gần “0.1”, hai giá trị có thể khác.

Ví dụ khác:

```java
int i = 16_777_217;
float f = 16_777_216f;

boolean same = i == f; // true: int được đổi thành float và bị làm tròn
```

`16_777_217` không biểu diễn chính xác trong `float`, nên khi chuyển kiểu để so sánh với `f`, nó có thể được làm tròn thành `16_777_216f`. Vì vậy **`==` không bảo đảm phát hiện khác biệt giữa mọi số nguyên** khi trộn `float` với `int`/`long` lớn. Tránh trộn kiểu khi yêu cầu so sánh số nguyên chính xác; chuyển về loại phù hợp trước khi mất độ chính xác.

Trong `Double`/`Float` wrapper, cần xem thêm quy tắc unboxing và `equals` (mục 8). Không nên suy diễn rằng mọi đối tượng chứa số đều dùng cùng ngữ nghĩa với các toán tử primitive.

## 3. Vì sao `0.1 + 0.2 == 0.3` là `false`?

`float` và `double` dùng biểu diễn nhị phân có độ chính xác hữu hạn. Nhiều phân số thập phân như `0.1`, `0.2`, `0.3` không biểu diễn chính xác dưới dạng nhị phân hữu hạn. Một phép cộng sẽ làm tròn kết quả theo quy tắc dấu phẩy động.

```java
double actual = 0.1 + 0.2;
double expected = 0.3;

System.out.println(actual);             // 0.30000000000000004
System.out.println(actual == expected); // false
System.out.println(actual != expected); // true
```

Lúc này, `==` đang **hoạt động đúng**: hai giá trị `double` cuối cùng thực sự không đồng nhất. Sai lầm nằm ở việc mong muốn số học `double` tạo ra biểu diễn thập phân hoàn toàn chính xác.

**Không có nghĩa là không bao giờ dùng `==` với `double`.** Có những trường hợp `==` là lựa chọn đúng: kiểm tra giá trị sentinel hữu hạn được thiết kế rõ ràng, so sánh hai giá trị cùng quy trình biểu diễn khi cần đúng tính bằng nhau, hoặc so với `0.0` khi ngữ nghĩa bằng 0 phù hợp và xử lý `NaN` riêng. Vấn đề là **mục tiêu so sánh**: bằng nhau chính xác của giá trị `double` hay gần bằng theo sai số cho phép.

### Độ chính xác hữu hạn còn ảnh hưởng phép so sánh thứ tự

```java
float big = 16_777_216f;
boolean stillSame = (big + 1 == big); // true
```

Ở vùng này, khoảng cách giữa hai giá trị `float` biểu diễn được liên tiếp là 2. Khi cộng 1, kết quả nằm ở chính giữa hai giá trị biểu diễn được và có thể làm tròn quay về `big` theo quy tắc round-to-nearest, ties-to-even. Do đó phép so sánh cho `true`, mặc dù về số học thực `x + 1 > x`.

Chọn đúng miền và loại số rất quan trọng trước khi kết luận các phép so sánh số thực có phản ánh thứ tự của **giá trị toán học ban đầu** hay không.

## 4. `NaN` làm thay đổi trực giác về `==`, `!=` và thứ tự

`NaN` (*Not a Number*) là giá trị đặc biệt có thể sinh từ các phép toán không có kết quả số thực xác định, ví dụ `0.0 / 0.0`. Cả `Float.NaN` và `Double.NaN` đều là NaN.

Trong các phép so sánh primitive dấu phẩy động, NaN được coi là **unordered** (không có thứ tự) so với mọi giá trị, **kể cả chính NaN**:

| Biểu thức | Kết quả |
| --- | --- |
| `Double.NaN == Double.NaN` | `false` |
| `Double.NaN != Double.NaN` | `true` |
| `Double.NaN < 1.0` | `false` |
| `Double.NaN <= 1.0` | `false` |
| `Double.NaN > 1.0` | `false` |
| `Double.NaN >= 1.0` | `false` |
| `1.0 < Double.NaN` | `false` |
| `1.0 >= Double.NaN` | `false` |

Điều này cũng đúng với các phép so sánh `float` khi có `Float.NaN`.

**Hệ quả logic rất dễ nhầm:** Với giá trị NaN, `!(a < b)` là `true` nhưng `a >= b` lại `false`. Vì vậy biến đổi điều kiện `!(x < y)` thành `x >= y` **không tương đương** nếu `x` hoặc `y` có thể là NaN. Tương tự, `!(x <= y)` không đồng nghĩa với `x > y` khi có NaN. Quy tắc “không nhỏ hơn thì phải lớn hơn hoặc bằng” chỉ đúng khi dữ liệu được bảo đảm **không NaN**.

`!=` là phủ định trực tiếp của `==`, vì thế khi xuất hiện NaN, `!=` là `true` ngay cả khi hai biến chứa cùng một đối tượng NaN theo cách lưu trữ số thực.

### Kiểm tra NaN đúng cách

```java
double value = Double.NaN;

boolean wrong = value == Double.NaN; // false
boolean isNan = Double.isNaN(value);  // true
```

Không dùng `value == Double.NaN` để nhận biết NaN. Có thể dựa vào `value != value` theo tính chất NaN, nhưng `Double.isNaN(value)`/`Float.isNaN(value)` diễn đạt rõ ý định hơn và dễ đọc hơn.

Nếu phải loại cả NaN lẫn vô cực, dùng `Double.isFinite(value)` hoặc `Float.isFinite(value)` trước khi tính toán/so sánh thứ tự.

## 5. `+0.0` và `-0.0`: bằng nhau về toán tử, khác mẫu bit

IEEE 754 có hai biểu diễn zero: **zero dương** và **zero âm**. Java coi chúng là bằng nhau trong các toán tử primitive:

```java
double positive = +0.0;
double negative = -0.0;

boolean eq = (positive == negative); // true
boolean ne = (positive != negative); // false
boolean lt = (negative < positive);  // false
boolean le = (negative <= positive); // true
boolean gt = (negative > positive);  // false
boolean ge = (negative >= positive); // true
```

Tuy nhiên, dấu bit của zero có thể ảnh hưởng đến phép tính khác:

```java
double p = 1.0 / +0.0; // +Infinity
double n = 1.0 / -0.0; // -Infinity
```

`Double.doubleToLongBits(0.0)` và `Double.doubleToLongBits(-0.0)` trả hai mẫu bit khác nhau. Tương tự với `Float.floatToIntBits`. **Nếu chỉ dùng `==`, bạn đang chọn ngữ nghĩa số học rằng cả hai số zero bằng nhau**; đó không phải công cụ nhận diện dấu bit.

Khi cần nhận dạng bit vì định dạng nhị phân hay tính toán có dấu zero, sử dụng API bit hoặc `Double.compare`/`Float.compare` với quy tắc thứ tự bổ sung, thay vì kết luận từ `==`.

## 6. `+Infinity` và `-Infinity`: có thứ tự nếu không có NaN

Khác với NaN, vô cực tham gia thứ tự số thực theo quy tắc quen thuộc:

\[
-\infty < \text{mọi số hữu hạn} < +\infty
\]

Ví dụ:

```java
boolean a = Double.POSITIVE_INFINITY > Double.MAX_VALUE; // true
boolean b = Double.NEGATIVE_INFINITY < -Double.MAX_VALUE; // true
boolean c = Double.POSITIVE_INFINITY == (1.0 / 0.0);     // true
boolean d = Double.POSITIVE_INFINITY == Double.NEGATIVE_INFINITY; // false
```

Dù có quan hệ thứ tự, vô cực thường **không phải dữ liệu đầu vào hợp lệ** cho tỷ lệ, giá cả, số đo hay bộ đếm thực tế. Nhiều phép toán có thể biến dữ liệu hữu hạn thành vô cực do overflow hoặc chia cho zero theo kiểu dấu phẩy động; cần quyết định rõ có cho phép trạng thái này hay không.

**Không nhầm** chia dấu phẩy động cho zero với chia nguyên cho zero: `1.0 / 0.0` trả `Infinity`, còn phép chia nguyên `1 / 0` (khi được thực hiện) gây `ArithmeticException`; Java có thể báo lỗi sớm nếu đó là biểu thức hằng không hợp lệ trong ngữ cảnh yêu cầu hằng số.

## 7. Khi nào dùng so sánh gần đúng thay vì `==`?

Với kết quả của nhiều phép tính `double`, đôi khi cần coi hai giá trị là “gần bằng” trong **ngưỡng sai số ứng dụng cho phép**, thay vì yêu cầu `==`.

Một cách thông dụng kết hợp **dung sai tuyệt đối** và **dung sai tương đối**:

\[
|a-b| \leq \max(\text{absTol},\ \text{relTol}\cdot\max(|a|,|b|)).
\]

- `absTol` phù hợp với mức sai số cố định, đặc biệt **gần số 0**.
- `relTol` phù hợp khi độ lớn của số thay đổi nhiều bậc, giúp giới hạn sai số theo tỉ lệ.
- Các ngưỡng phải **được xác định từ đơn vị đo, yêu cầu nghiệp vụ và đặc tính thuật toán**; không có một epsilon cố định đúng cho mọi bài toán.

Ví dụ phương thức minh họa:

```java
static boolean nearlyEqual(double a, double b, double absTol, double relTol) {
    if (Double.isNaN(a) || Double.isNaN(b)) return false;
    if (a == b) return true; // Bao gồm hai vô cực cùng dấu và ±0.0
    if (!Double.isFinite(a) || !Double.isFinite(b)) return false;

    double delta = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return delta <= Math.max(absTol, relTol * scale);
}
```

Đây là **mảnh phương thức** cần đặt trong class. Nó giả định người gọi truyền ngưỡng **hữu hạn, không âm, đã lựa chọn hợp lý**. Nếu đây là API dùng cho dữ liệu không tin cậy, nên xác thực `absTol` và `relTol` (không NaN/Infinity, không âm), đồng thời xét nguy cơ tràn số trong phép trừ hay nhân tạo ngưỡng khi trị tuyệt đối rất lớn.

**Quan trọng:** `nearlyEqual` không phải thay thế phổ quát cho `==`:

- Quan hệ “gần bằng” với dung sai dương **thường không có tính bắc cầu**. Có thể `a` gần `b` và `b` gần `c`, nhưng `a` không gần `c`.
- Vì thế không dùng trực tiếp gần bằng để định nghĩa `equals`/`hashCode` hoặc comparator sắp xếp, vốn đòi hợp đồng nhất quán.
- Không nên dùng `Double.MIN_VALUE` làm một epsilon tuyệt đối mặc định: nó là **số dương subnormal nhỏ nhất**, không phải sai số đại diện khi cộng trừ nhiều giá trị `double`.
- Gần bằng **0** cần giới hạn tuyệt đối phù hợp; chỉ dùng tương đối có thể phản trực giác khi hai số đều rất nhỏ.
- Với tiền tệ và yêu cầu chính xác chữ số thập phân, `BigDecimal` với `RoundingMode` phù hợp hơn trong nhiều trường hợp, nhưng phải khai báo chính sách chính xác.

Nếu mục tiêu là phát hiện **bit thay đổi**, dùng API bit. Nếu mục tiêu là so sánh **giá trị chính xác theo kiểu `double`**, dùng `==`. Nếu cần so sánh **độ gần theo phép đo**, dùng tolerance được định nghĩa cụ thể. Ba yêu cầu khác nhau.

## 8. So sánh primitive khác `Double.compare`, `Float.compare` và wrapper `equals`

Khi cần **sắp xếp** danh sách chứa NaN hay signed zero, các toán tử primitive không tạo được thứ tự toàn phần hợp lệ cho mọi giá trị: NaN làm tất cả phép `<`/`>` thành `false`.

Java cung cấp:

```java
int orderDouble = Double.compare(a, b);
int orderFloat = Float.compare(x, y);
```

Giá trị trả về **âm, zero hoặc dương** (không cần chính xác -1, 0, 1 trong mọi API so sánh) theo thứ tự được định nghĩa. Với `Double.compare`/`Float.compare`:

- `-Infinity` nhỏ hơn mọi số hữu hạn, `+Infinity` lớn hơn mọi số hữu hạn.
- **`-0.0` nhỏ hơn `+0.0`**, dù phép primitive `-0.0 == +0.0` là `true`.
- **NaN được coi lớn hơn mọi giá trị khác**, kể cả `+Infinity`.
- Các NaN được xem là **bằng nhau trong phép compare** vì các mẫu NaN được xử lý theo ngữ nghĩa canonical.

Ví dụ:

```java
int z = Double.compare(-0.0, +0.0); // Giá trị âm (-1 trong JDK hiện hành)
int n = Double.compare(Double.NaN, Double.POSITIVE_INFINITY); // Giá trị dương
int bothNaN = Double.compare(Double.NaN, Double.NaN); // 0
```

`Double.valueOf(0.0).equals(Double.valueOf(-0.0))` là `false`; `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` là `true`. Wrapper `equals` sử dụng ngữ nghĩa nhất quán với `Double.compare` cho giá trị tương ứng, **khác** primitive `==` đối với signed zero/NaN.

Nếu cả hai toán hạng là object wrapper `Double`, toán tử `==` giữa chúng có thể **so sánh tham chiếu**, không phải số học. Khi một bên là primitive và Java áp dụng unboxing, có thể thành so sánh số học; unboxing `null` sẽ ném `NullPointerException`. Khi làm việc với collection, phải chọn `equals` hoặc comparator phù hợp thay vì dùng `==` trên hai object wrapper.

**Sắp xếp đúng:**

```java
double[] values = { Double.NaN, +0.0, -0.0, Double.POSITIVE_INFINITY };
java.util.Arrays.sort(values);
// [-0.0, 0.0, Infinity, NaN] theo thứ tự của Double.compare
```

Không viết comparator bằng `(int) (a - b)`, bởi phép trừ có thể là số rất nhỏ bị cast thành 0, có thể overflow thành infinity, và với NaN cho 0 theo quy tắc cast sang nguyên. Comparator như thế có thể vi phạm yêu cầu sắp xếp.

## 9. Chương trình Java 17+ kiểm chứng sáu toán tử và trường hợp biên

Lưu vào tệp `FloatingComparisonDemo.java`:

```java
public class FloatingComparisonDemo {
    static boolean nearlyEqual(double a, double b, double absTol, double relTol) {
        if (Double.isNaN(a) || Double.isNaN(b)) return false;
        if (a == b) return true;
        if (!Double.isFinite(a) || !Double.isFinite(b)) return false;

        double delta = Math.abs(a - b);
        double scale = Math.max(Math.abs(a), Math.abs(b));
        return delta <= Math.max(absTol, relTol * scale);
    }

    public static void main(String[] args) {
        double a = 0.1 + 0.2, b = 0.3;
        System.out.println("sum: " + a);
        System.out.println("sum == 0.3: " + (a == b));
        System.out.println("sum != 0.3: " + (a != b));
        System.out.println("near sum: " + nearlyEqual(a, b, 1e-12, 1e-9));

        System.out.println("1 < 2: " + (1.0 < 2.0));
        System.out.println("2 <= 2: " + (2.0 <= 2.0));
        System.out.println("2 > 1: " + (2.0 > 1.0));
        System.out.println("2 >= 2: " + (2.0 >= 2.0));

        double nan = Double.NaN;
        System.out.println("NaN == NaN: " + (nan == nan));
        System.out.println("NaN != NaN: " + (nan != nan));
        System.out.println("NaN < 1: " + (nan < 1));
        System.out.println("NaN <= 1: " + (nan <= 1));
        System.out.println("NaN > 1: " + (nan > 1));
        System.out.println("NaN >= 1: " + (nan >= 1));

        System.out.println("+0 == -0: " + (0.0 == -0.0));
        System.out.println("1/+0: " + (1.0 / 0.0));
        System.out.println("1/-0: " + (1.0 / -0.0));
        System.out.println("Infinity > MAX: "
            + (Double.POSITIVE_INFINITY > Double.MAX_VALUE));
        System.out.println("-Infinity < MIN: "
            + (Double.NEGATIVE_INFINITY < -Double.MAX_VALUE));

        float f = 0.1f;
        System.out.println("0.1f == 0.1: " + (f == 0.1));
        float big = 16_777_216f;
        System.out.println("float next equals: " + (big + 1 == big));

        System.out.println("compare -0,+0: " + Double.compare(-0.0, +0.0));
        System.out.println("compare NaN,+Infinity: "
            + Double.compare(Double.NaN, Double.POSITIVE_INFINITY));
        System.out.println("compare NaN,NaN: " + Double.compare(Double.NaN, Double.NaN));
        System.out.println("boxed zeros equals: "
            + Double.valueOf(0.0).equals(Double.valueOf(-0.0)));
        System.out.println("boxed NaNs equals: "
            + Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN)));
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac FloatingComparisonDemo.java
java FloatingComparisonDemo
```

Stdout:

```text
sum: 0.30000000000000004
sum == 0.3: false
sum != 0.3: true
near sum: true
1 < 2: true
2 <= 2: true
2 > 1: true
2 >= 2: true
NaN == NaN: false
NaN != NaN: true
NaN < 1: false
NaN <= 1: false
NaN > 1: false
NaN >= 1: false
+0 == -0: true
1/+0: Infinity
1/-0: -Infinity
Infinity > MAX: true
-Infinity < MIN: true
0.1f == 0.1: false
float next equals: true
compare -0,+0: -1
compare NaN,+Infinity: 1
compare NaN,NaN: 0
boxed zeros equals: false
boxed NaNs equals: true
```

**Đọc kết quả:** Các dòng đầu cho thấy phép so sánh chính xác giữa hai giá trị `double` đã làm tròn khác với so sánh theo tolerance. Các dòng `NaN` chứng minh mọi phép quan hệ thứ tự đều false, `==` false và `!=` true. Các dòng `±0` và vô cực cho thấy sự khác biệt giữa bằng nhau về giá trị số học với dấu zero. Cuối cùng, `Double.compare` và wrapper `equals` thể hiện quy tắc phục vụ sắp xếp/collection, không đồng nhất với primitive `==`.

## 10. Thiết kế điều kiện so sánh an toàn

### Kiểm tra miền đầu vào

Nếu hệ thống chỉ chấp nhận kết quả số hữu hạn, **xác thực trước**:

```java
static boolean inRange(double value, double min, double max) {
    return Double.isFinite(value)
        && value >= min
        && value <= max;
}
```

Đoạn này là **mảnh mã minh họa**: chỉ dùng khi `min` và `max` là các ngưỡng hữu hạn được kiểm chứng và `min <= max`. Việc kiểm tra `isFinite` diễn đạt rõ yêu cầu không chấp nhận NaN/Infinity; riêng toán tử `>=` và `<=` đã trả false với NaN, nhưng không loại vô cực trong mọi miền nếu ngưỡng không hữu hạn.

### Tránh đảo điều kiện bất cẩn khi có NaN

Nếu muốn bác bỏ mọi giá trị **không nhỏ hơn ngưỡng** hoặc NaN, đừng mặc định đổi `!(x < threshold)` thành `x >= threshold` vì chúng khác nhau với NaN.

```java
double x = Double.NaN;
boolean notLess = !(x < 10.0); // true
boolean greaterOrEqual = x >= 10.0; // false
```

Khi muốn điều kiện độc lập với NaN, hãy viết tường minh:

```java
boolean accepted = Double.isFinite(x) && x >= 0.0 && x <= 10.0;
```

### Khi cần kiểm tra gần bằng

Đặt tên có chủ đích như `nearlyEqual`, `withinTolerance` và truyền các tham số `absTol`/`relTol` theo đơn vị đo. Không áp dụng tolerance tùy ý để so sánh khóa map, mã định danh, mã giao dịch hoặc mọi giá trị trong bài toán.

### Khi cần thứ tự ổn định để sắp xếp

Dùng `Double.compare`/`Float.compare`, hoặc `Comparator.comparingDouble` khi làm việc với object và trường dữ liệu `double`. Nếu dữ liệu có thể chứa `NaN`, hãy quyết định liệu quy tắc “NaN xếp cuối” của comparator này có phù hợp, hay cần lọc dữ liệu trước.

## 11. Những nhầm lẫn thường gặp

1. **“Hai biểu thức thập phân giống nhau về toán học phải so sánh `==` bằng nhau.”** Sai: `double` có sai số biểu diễn và làm tròn.
2. **“`!=` cũng false khi có NaN vì không so sánh được.”** Sai: `NaN != NaN` là true.
3. **“Không nhỏ hơn thì chắc chắn lớn hơn hoặc bằng.”** Sai với NaN: `!(x < y)` có thể true trong khi `x >= y` false.
4. **“`NaN == NaN` là true vì hai bên đều là NaN.”** Sai: primitive `==` trả false; dùng `Double.isNaN` để kiểm tra.
5. **“`+0.0` và `-0.0` khác nhau theo `==` vì bit dấu khác.”** Sai: `+0.0 == -0.0` true.
6. **“`Double.compare` hoạt động y hệt `<`, `>` và `==` trên mọi giá trị.”** Sai: nó phân biệt signed zero và quy định vị trí cho NaN.
7. **“Chỉ cần dùng `Double.MIN_VALUE` làm epsilon khi so sánh gần đúng.”** Sai: đây là số dương nhỏ nhất, thường không phù hợp sai số của thuật toán.
8. **“Tolerance gần đúng có thể thay thế `equals` và `hashCode`.”** Sai: gần bằng thường không bắc cầu nên không phải quan hệ tương đương hợp lệ cho nhiều collection.
9. **“`0.1f` và `0.1` chắc chắn bằng nhau sau khi nâng kiểu.”** Sai: `float` đã bị làm tròn theo độ chính xác thấp hơn trước khi sang `double`.
10. **“So sánh số thực bằng cách ép phép trừ về `int` là comparator tốt.”** Sai: mất sai khác nhỏ, xử lý NaN sai và có thể phá hợp đồng comparator.
11. **“Vô cực luôn không có quan hệ thứ tự.”** Sai: chỉ NaN unordered; `-Infinity` và `+Infinity` có thứ tự.
12. **“Dùng toán tử `==` trên hai wrapper `Double` luôn so sánh giá trị số.”** Sai: hai object có thể bị so sánh tham chiếu; `equals` và unboxing có quy tắc riêng.

## 12. Câu hỏi tự kiểm tra

- `Double.NaN == Double.NaN` có kết quả gì? **false**.
- `Double.NaN != Double.NaN` có kết quả gì? **true**.
- Với `x = Double.NaN`, `!(x < 3.0)` và `x >= 3.0` bằng nhau không? **Không**: kết quả lần lượt true và false.
- `-0.0 == 0.0` có đúng không? **Đúng**; tuy nhiên `Double.compare(-0.0, 0.0)` cho kết quả âm.
- `Double.POSITIVE_INFINITY > Double.MAX_VALUE` là gì? **true**.
- `float a = 0.1f; double b = 0.1;` thì `a == b` chắc chắn true không? **Không**: trong ví dụ này là false vì làm tròn `float`.
- Nếu muốn “gần bằng” theo sai số đo cụ thể, nên dùng gì? **Một hàm so sánh với tolerance được chọn theo miền/đơn vị**, kiểm tra NaN và vô cực theo chính sách.
- Nếu cần sắp xếp một danh sách chứa NaN và signed zero, nên dùng gì? **`Double.compare`/`Float.compare`** hoặc comparator theo quy tắc thứ tự nghiệp vụ, không dùng `(int)(a-b)`.

**Ghi nhớ:** Sáu toán tử trên `float`/`double` so sánh **giá trị số thực đã được biểu diễn**, không tự áp dụng ngưỡng sai số. `NaN` làm `==` và bốn phép quan hệ thứ tự thành false, nhưng `!=` thành true. `+0.0` và `-0.0` bằng nhau theo primitive `==`, còn các comparator chuẩn phân biệt chúng. Khi cần so sánh gần đúng hoặc sắp xếp, hãy chọn **quy tắc riêng phù hợp mục tiêu**, thay vì suy diễn trực tiếp từ toán học số thực vô hạn độ chính xác.
