# `float` và `double` theo mô hình dấu phẩy động nhị phân — Java 17+

## 1. Vì sao số thực trong máy tính không luôn chính xác?

Trong Java, `float` và `double` là **kiểu nguyên thủy dấu phẩy động nhị phân** (*binary floating-point*), phù hợp với mô hình IEEE 754. Chúng lưu một **giá trị nhị phân hữu hạn số bit**, không lưu mọi số thập phân theo đúng dạng con người viết.

Chẳng hạn:

~~~java
double sum = 0.1 + 0.2;
System.out.println(sum);
System.out.println(sum == 0.3);
~~~

Đầu ra:

~~~text
0.30000000000000004
false
~~~

Lý do không phải Java cộng sai. Các giá trị thập phân như `0.1` và `0.2` không có biểu diễn nhị phân hữu hạn chính xác, nên được làm tròn sang giá trị gần nhất có thể lưu trong `double`. Sau phép cộng và làm tròn, kết quả khác giá trị `double` gần nhất đại diện cho literal `0.3`.

**Thông điệp quan trọng:** `float` và `double` biểu diễn **các số thực xấp xỉ hữu hạn độ chính xác**; không nên mặc định mọi phép so sánh bằng `==` sẽ phản ánh đẳng thức toán học trên số thập phân.

## 2. Cấu trúc bit: dấu, số mũ và phần trị

Về mặt biểu diễn, cả hai kiểu gồm một **bit dấu**, phần **số mũ** (*exponent*) và phần **fraction/significand**.

| Đặc tính | `float` | `double` |
|---|---:|---:|
| Tổng số bit | 32 | 64 |
| Bit dấu | 1 | 1 |
| Bit trường số mũ | 8 | 11 |
| Bit fraction được lưu | 23 | 52 |
| Độ chính xác significand hiệu dụng của số normal | 24 bit | 53 bit |
| Chữ số thập phân có nghĩa thường dùng để ước lượng | khoảng 6–7 | khoảng 15–16 |
| Giá trị hữu hạn dương lớn nhất | khoảng `3.4028235E38` | khoảng `1.7976931348623157E308` |

Đối với số **normal** khác 0, giá trị mang dạng khái quát:

\[
(-1)^{sign}\times(1.fraction)_2\times2^{exponent-bias}.
\]

- `sign` cho biết dấu dương/âm.
- `fraction` là các bit phần lẻ sau dấu phẩy nhị phân.
- `exponent` xác định thang độ lớn dựa trên lũy thừa của 2.
- Với số normal, có một bit dẫn đầu `1` được hiểu ngầm, vì vậy độ chính xác hiệu dụng là 24 hoặc 53 bit.

Số **subnormal**, số 0, vô cực và NaN dùng các dạng biểu diễn đặc biệt, không áp dụng công thức số normal một cách nguyên xi.

Từ Java 17, ngữ nghĩa dấu phẩy động được xác định theo hướng **always-strict**: lập trình viên có thể dựa vào các quy tắc làm tròn/độ rộng của ngôn ngữ thay vì giả định JVM tùy tiện giữ kết quả trung gian với độ chính xác mở rộng. Không cần gắn `strictfp` chỉ để bật điều đó trong Java 17.

## 3. Literal, hậu tố F và kiểu mặc định

Một literal có dấu chấm thập phân hoặc số mũ như `1.25` thường có kiểu **`double`** nếu không có hậu tố. Muốn literal kiểu `float`, viết hậu tố `f` hoặc `F`.

~~~java
double distanceKm = 12.5;     // Literal double
double large = 1.23e6;       // 1_230_000.0, kiểu double
float temperature = 26.5f;   // Literal float
float ratio = 1.25F;         // Literal float
double fromFloat = 1.25f;    // float literal được mở rộng sang double
~~~

Không hợp lệ:

~~~java
// float bad = 0.1; // Lỗi compile: double không tự thu hẹp sang float
~~~

Nếu muốn `float`, hãy viết `0.1f` thay vì cast tùy tiện. Nếu bài toán không có lý do đặc biệt chọn `float`, **`double` thường là lựa chọn mặc định** cho phép tính số thực trên Java.

**Đừng nhầm hậu tố:** `L` dành cho literal số nguyên kiểu `long`; `F` dành cho literal dấu phẩy động kiểu `float`; `D` có thể viết cho `double` nhưng thường không cần.

Độ rộng 64 bit của `double` không có nghĩa nó biểu diễn **mọi** số nguyên 64 bit chính xác: khi các số đủ lớn, các số nguyên liên tiếp có thể cùng làm tròn về một `double`.

## 4. Sai số biểu diễn bắt đầu từ bước lưu giá trị

Trong hệ thập phân, `1/10 = 0.1` có một chữ số sau dấu phẩy. Trong hệ nhị phân, `1/10` lặp vô hạn, nên `float`/`double` phải cắt làm tròn trong giới hạn số bit.

~~~java
float f = 0.1f;
double d = 0.1;

System.out.println(f);
System.out.println((double) f);
System.out.println(d);
~~~

Đầu ra:

~~~text
0.1
0.10000000149011612
0.1
~~~

Giải thích:

- `System.out.println(f)` hiển thị một **chuỗi thập phân ngắn đủ để tái tạo** cùng giá trị `float` theo quy tắc chuyển sang chuỗi. Việc in `0.1` không chứng minh giá trị nhị phân được lưu bằng chính xác 1/10.
- Ép `float` sang `double` giữ đúng **giá trị xấp xỉ đã lưu ở float**, vì mọi giá trị `float` hữu hạn đều biểu diễn chính xác được ở `double`. Nó không khôi phục số thập phân gốc `0.1`.
- `double d = 0.1;` chọn một xấp xỉ khác, thường chính xác hơn do có 53 bit significand.

Nếu cần phân tích sâu có thể dùng `Float.floatToRawIntBits` và `Double.doubleToRawLongBits` để nhìn mẫu bit; còn khi học ứng dụng, chỉ cần hiểu `float`/ `double` không phải kiểu thập phân chính xác.

## 5. Miền giá trị, MIN_VALUE và số subnormal

Hai kiểu có miền giá trị rất lớn, nhưng có **độ chính xác hữu hạn**. Java cung cấp các hằng:

| Hằng | Ý nghĩa | Giá trị xấp xỉ |
|---|---|---:|
| `Float.MAX_VALUE` | Số hữu hạn dương lớn nhất của float | `3.4028235E38` |
| `Float.MIN_NORMAL` | Số normal dương nhỏ nhất của float | `1.17549435E-38` |
| `Float.MIN_VALUE` | Số subnormal dương nhỏ nhất khác 0 của float | `1.4E-45` |
| `Double.MAX_VALUE` | Số hữu hạn dương lớn nhất của double | `1.7976931348623157E308` |
| `Double.MIN_NORMAL` | Số normal dương nhỏ nhất của double | `2.2250738585072014E-308` |
| `Double.MIN_VALUE` | Số subnormal dương nhỏ nhất khác 0 của double | `4.9E-324` |

**Bẫy quan trọng:** `Float.MIN_VALUE` và `Double.MIN_VALUE` **không phải số âm nhỏ nhất**. Chúng là **số dương nhỏ nhất khác 0** có thể biểu diễn. Số hữu hạn âm có độ lớn lớn nhất lần lượt là `-Float.MAX_VALUE` và `-Double.MAX_VALUE`.

**Subnormal** cho phép biểu diễn các giá trị gần 0 hơn `MIN_NORMAL` bằng cách hy sinh dần các bit có nghĩa hiệu dụng. Nếu phép tính tạo ra giá trị có độ lớn quá nhỏ, kết quả có thể **underflow** về một giá trị subnormal hoặc thành số 0 (có dấu). Nếu độ lớn vượt miền hữu hạn, kết quả có thể thành **Infinity**.

Không nhầm “miền rộng” với “độ chính xác cao ở mọi giá trị”. Khoảng cách giữa hai số dấu phẩy động liên tiếp **tăng khi độ lớn của số tăng**.

## 6. Độ chính xác, ULP và bước nhảy giữa hai số

**ULP** (*unit in the last place*) giúp mô tả khoảng cách giữa các giá trị biểu diễn gần một số cụ thể. Gần `1.0`:

~~~java
System.out.println(Math.ulp(1.0f)); // 1.1920929E-7
System.out.println(Math.ulp(1.0d)); // 2.220446049250313E-16
~~~

Đối với `float`, số nguyên `16_777_216` (2²⁴) đã đủ lớn để **không thể phân biệt** giá trị đó với giá trị cộng thêm 1 sau khi làm tròn về `float`:

~~~java
float base = 16_777_216f;
System.out.println(base + 1f == base); // true
~~~

Trong `double`, số nguyên liên tiếp được biểu diễn chính xác đến `2^53`, sau đó không còn bảo đảm mọi bước tăng 1 đều được phân biệt.

Như vậy, khả năng lưu **giá trị rất lớn** không có nghĩa vẫn giữ được **sai khác rất nhỏ** trên cùng thang giá trị. Chọn `double` hay `float` phải xét cả độ lớn và độ phân giải cần thiết.

## 7. So sánh: ==, epsilon và giới hạn của dung sai

So sánh trực tiếp:

~~~java
double a = 0.1 + 0.2;
double b = 0.3;

System.out.println(a == b); // false
~~~

Nếu một bài toán cho phép sai số gần đúng, bạn có thể định nghĩa **dung sai có ý nghĩa**:

~~~java
static boolean nearlyEqual(double a, double b, double tolerance) {
    if (tolerance < 0 || !Double.isFinite(tolerance)) {
        throw new IllegalArgumentException("Invalid tolerance");
    }
    return Double.isFinite(a) && Double.isFinite(b)
            && Math.abs(a - b) <= tolerance;
}
~~~

Ví dụ `nearlyEqual(0.1 + 0.2, 0.3, 1e-9)` trả `true`.

Nhưng **không có một epsilon cố định đúng cho mọi bài toán**: dung sai tuyệt đối `1e-9` có thể quá lớn nếu đo nano-đơn vị và quá nhỏ nếu so sánh hai giá trị rất lớn. Khi cần, xét kết hợp dung sai tuyệt đối và tương đối theo miền dữ liệu.

Đặc biệt, **đừng dùng phép so sánh gần đúng** để thay thế định danh, khóa, dữ liệu tiền tệ, hoặc những phép kiểm tra cần sự bằng nhau chính xác theo quy ước nghiệp vụ. Với `NaN` và `Infinity`, cần xác định riêng chính sách chấp nhận giá trị.

## 8. Các giá trị đặc biệt: NaN, Infinity, +0.0 và -0.0

IEEE 754 cho phép nhiều trạng thái ngoài số hữu hạn bình thường:

| Giá trị | Sinh ra như thế nào (ví dụ) | Điều cần nhớ |
|---|---|---|
| `Double.POSITIVE_INFINITY` | `1.0 / 0.0` | Dương vô cực, không phải số hữu hạn |
| `Double.NEGATIVE_INFINITY` | `-1.0 / 0.0` | Âm vô cực |
| `Double.NaN` | `0.0 / 0.0` | Not a Number |
| `+0.0` | `0.0` | Zero dấu dương |
| `-0.0` | `-0.0` | Zero dấu âm, có mẫu bit khác +0.0 |

Ví dụ:

~~~java
double nan = 0.0 / 0.0;
System.out.println(Double.isNaN(nan)); // true
System.out.println(nan == nan);        // false
System.out.println(1.0 / 0.0);         // Infinity
System.out.println(1.0 / -0.0);        // -Infinity
System.out.println(0.0 == -0.0);       // true
~~~

**Phân biệt quan trọng:**

- Mọi phép so sánh số học `==` với NaN đều trả `false`, kể cả `nan == nan`. Dùng `Double.isNaN` hoặc `Float.isNaN` khi cần phát hiện NaN.
- `0.0 == -0.0` là `true` theo toán tử `==`, nhưng dấu có thể ảnh hưởng kết quả phép chia nghịch đảo và mẫu bit lưu trữ.
- Dùng `Double.isInfinite` hoặc `Double.isFinite` để kiểm tra các trường hợp ngoài miền hữu hạn.
- Khác phép chia số nguyên cho 0, phép chia dấu phẩy động `1.0 / 0.0` **không ném `ArithmeticException`**; nó tạo Infinity theo quy tắc floating-point.

Nếu dữ liệu đầu vào không được phép chứa NaN/Infinity, hãy validation **trước** khi tính hoặc lưu dữ liệu vào hệ thống.

## 9. Chương trình Java 17 đầy đủ và kết quả chạy

Tạo đúng tệp **`BinaryFloatingDemo.java`**:

~~~java
import java.math.BigDecimal;

public final class BinaryFloatingDemo {
    private BinaryFloatingDemo() {}

    static boolean nearlyEqual(double a, double b, double tolerance) {
        if (tolerance < 0 || !Double.isFinite(tolerance)) {
            throw new IllegalArgumentException("Invalid tolerance");
        }
        return Double.isFinite(a) && Double.isFinite(b)
                && Math.abs(a - b) <= tolerance;
    }

    public static void main(String[] args) {
        float f = 0.1f;
        double d = 0.1;

        System.out.println("float bits=" + Float.SIZE);
        System.out.println("double bits=" + Double.SIZE);
        System.out.println("float printed=" + f);
        System.out.println("float as double=" + (double) f);
        System.out.println("double printed=" + d);

        double sum = 0.1 + 0.2;
        System.out.println("0.1+0.2=" + sum);
        System.out.println("equals 0.3=" + (sum == 0.3));
        System.out.println("near 0.3=" + nearlyEqual(sum, 0.3, 1e-9));

        System.out.println("float ULP at 1=" + Math.ulp(1.0f));
        System.out.println("double ULP at 1=" + Math.ulp(1.0d));
        float base = 16_777_216f;
        System.out.println("float loses +1=" + (base + 1f == base));

        System.out.println("float min normal=" + Float.MIN_NORMAL);
        System.out.println("float min positive=" + Float.MIN_VALUE);
        System.out.println("double max finite=" + Double.MAX_VALUE);

        double nan = 0.0 / 0.0;
        System.out.println("positive infinity=" + (1.0 / 0.0));
        System.out.println("negative infinity=" + (1.0 / -0.0));
        System.out.println("is NaN=" + Double.isNaN(nan));
        System.out.println("NaN equals itself=" + (nan == nan));
        System.out.println("zero equality=" + (0.0 == -0.0));

        BigDecimal exact = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println("decimal exact sum=" + exact);
    }
}
~~~

Yêu cầu: **JDK 17+**, terminal mở tại thư mục chứa tệp.

**Bash (Linux/macOS):**

~~~bash
java -version
javac -version
javac --release 17 -encoding UTF-8 BinaryFloatingDemo.java
java -cp . BinaryFloatingDemo
~~~

**PowerShell (Windows):**

~~~powershell
java -version
javac -version
javac --release 17 -encoding UTF-8 .\BinaryFloatingDemo.java
java -cp . BinaryFloatingDemo
~~~

**Expected output:**

~~~text
float bits=32
double bits=64
float printed=0.1
float as double=0.10000000149011612
double printed=0.1
0.1+0.2=0.30000000000000004
equals 0.3=false
near 0.3=true
float ULP at 1=1.1920929E-7
double ULP at 1=2.220446049250313E-16
float loses +1=true
float min normal=1.17549435E-38
float min positive=1.4E-45
double max finite=1.7976931348623157E308
positive infinity=Infinity
negative infinity=-Infinity
is NaN=true
NaN equals itself=false
zero equality=true
decimal exact sum=0.3
~~~

Trong phần đầu ra, dấu `E` nghĩa là số mũ cơ số 10 của **chuỗi hiển thị**; nó không đổi bản chất dữ liệu nhị phân bên dưới. Chuỗi hiển thị và mẫu bit trong JVM là hai khía cạnh khác nhau của cùng giá trị.

## 10. Khi nào dùng float, double và BigDecimal?

| Nhu cầu | Thường chọn | Lý do |
|---|---|---|
| Tính toán khoa học/thống kê thông thường có dung sai | `double` | Khoảng 15–16 chữ số thập phân có nghĩa; độ chính xác cao hơn `float` |
| Mảng rất lớn, dữ liệu hình ảnh/đồ họa, giao diện yêu cầu 32 bit | `float` khi phù hợp | Dung lượng dữ liệu thấp hơn, nhưng sai số lớn hơn |
| Tiền tệ/quy tắc làm tròn thập phân chặt chẽ | `BigDecimal` hoặc số nguyên đơn vị nhỏ nhất | Cần tính toán và làm tròn theo nghiệp vụ, không theo xấp xỉ nhị phân |
| Chỉ số đếm nguyên | `int` hoặc `long` | Số đếm nguyên không cần dấu phẩy động |

**BigDecimal không phải một hậu tố của float/double.** Nó là kiểu đối tượng trong `java.math`, có quy tắc và API số học riêng.

Khi bạn cần biểu diễn **chính xác các số thập phân trong bài toán tiền tệ**, tạo `BigDecimal` từ **chuỗi thập phân** hoặc từ biểu diễn đã biết, ví dụ:

~~~java
BigDecimal price = new BigDecimal("0.1");
BigDecimal tax = new BigDecimal("0.2");
System.out.println(price.add(tax)); // 0.3
~~~

Tránh `new BigDecimal(0.1)` nếu mục đích là lấy **chính xác giá trị thập phân 0.1**: constructor này nhận giá trị `double` đã xấp xỉ nhị phân và giữ lại sai khác đó. `BigDecimal.valueOf(0.1)` cũng là lựa chọn hợp lý cho nhiều trường hợp chuyển `double` theo chuỗi biểu diễn chuẩn, nhưng **không thể khôi phục độ chính xác đã mất trong phép tính trước đó**.

Với phép chia thập phân có kết quả vô hạn, `BigDecimal` có thể yêu cầu quy tắc làm tròn/`MathContext` phù hợp. Chọn `BigDecimal` không làm bạn hết phải xác định chính sách làm tròn.

## 11. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `float f = 0.1;` không compile | Literal mặc định `double` | `float f = 0.1f;` |
| `0.1 + 0.2 == 0.3` là false | Làm tròn nhị phân | Dùng dung sai phù hợp hoặc mô hình decimal chính xác |
| `Float.MIN_VALUE` bị hiểu là số âm cực tiểu | Tên hằng dễ gây nhầm | Nhớ đây là số dương khác 0 nhỏ nhất |
| `float` mất một bước cộng 1 ở số lớn | Khoảng cách giữa các giá trị float đã lớn | Chọn `double` hoặc kiểu nguyên nếu bài toán đếm |
| `1.0 / 0.0` cho Infinity | Ngữ nghĩa IEEE 754 | Dùng `isFinite`/validation |
| `NaN == NaN` là false | NaN có quy tắc so sánh đặc biệt | Dùng `isNaN` |
| `0.0 == -0.0` là true | So sánh giá trị không phân biệt dấu zero | Kiểm tra bit/dấu nếu bài toán cần phân biệt |
| `new BigDecimal(0.1)` có số lẻ dài | Nhận binary double gần 0.1 | Dùng chuỗi decimal hoặc `valueOf` đúng mục đích |
| Dùng epsilon tuyệt đối cố định cho mọi thang số | Dung sai không theo miền dữ liệu | Định nghĩa sai số tuyệt đối/tương đối theo yêu cầu |
| Trông đợi `double` giữ nguyên mọi số nguyên 64 bit | Significand chỉ 53 bit | Dùng `long`/`BigInteger` khi cần số nguyên chính xác |

## 12. Bài tập ngắn kèm đáp án

### Bài A — kiểu của literal

~~~java
double a = 1.25;
float b = 1.25f;
// float c = 1.25;
~~~

**Đáp án:** `a` và `b` hợp lệ. Dòng `c` lỗi compile vì `1.25` là literal `double` không có hậu tố `f`. Dù giá trị này biểu diễn chính xác được bằng nhị phân, quy tắc kiểu literal vẫn áp dụng.

### Bài B — giá trị in ra khác với giá trị thật

~~~java
float value = 0.1f;
System.out.println(value);
System.out.println((double) value);
~~~

**Đáp án:**

~~~text
0.1
0.10000000149011612
~~~

`println(float)` và `println(double)` dùng cách chuyển giá trị thành chuỗi theo từng kiểu. Ép `float` thành `double` không biến giá trị thành 0.1 thập phân chính xác.

### Bài C — so sánh số thực

Tại sao `0.1 + 0.2 == 0.3` trả false? Cần làm gì nếu bài toán cho phép sai số 1e-9?

**Đáp án:** các giá trị đã làm tròn ở dạng nhị phân nên sau phép cộng có thể không trùng đúng mẫu bit của `0.3`. Có thể so sánh `Math.abs((0.1 + 0.2) - 0.3) <= 1e-9` nếu dung sai này hợp với miền dữ liệu, đồng thời có quy tắc riêng với NaN/Infinity.

### Bài D — số đặc biệt

~~~java
double x = 0.0 / 0.0;
System.out.println(Double.isNaN(x));
System.out.println(x == x);
~~~

**Đáp án:**

~~~text
true
false
~~~

### Bài E — tiền tệ

Cần cộng hai giá trị tiền theo thập phân là 0.1 và 0.2 để được 0.3 đúng tuyệt đối. Chọn gì?

**Đáp án:** `new BigDecimal("0.1").add(new BigDecimal("0.2"))` cho kết quả `0.3` đúng theo biểu diễn decimal; với đơn vị nhỏ nhất hữu hạn có thể cân nhắc số nguyên. Tránh coi `double` cộng thập phân là phép tính decimal chính xác.

## 13. Checklist kết thúc

- [ ] Biết `float` có 32 bit, `double` có 64 bit; significand hiệu dụng tương ứng 24/53 bit.
- [ ] Hiểu vì sao `0.1` không biểu diễn chính xác bằng một số hữu hạn bit nhị phân.
- [ ] Nhớ literal dấu phẩy động mặc định là `double`, dùng `f`/`F` cho `float`.
- [ ] Phân biệt chuỗi in `0.1` với giá trị nhị phân được lưu.
- [ ] Hiểu `MIN_VALUE` là số dương khác 0 nhỏ nhất, khác `MIN_NORMAL`.
- [ ] Biết độ phân giải giảm khi độ lớn tăng, có thể quan sát qua `Math.ulp`.
- [ ] Biết phát hiện NaN/Infinity bằng API chuyên dụng và phân biệt `+0.0`/`-0.0`.
- [ ] Không dùng epsilon chung cho mọi bài toán mà không xét thang đo.
- [ ] Biết khi nào chuyển sang `BigDecimal` hoặc số nguyên.
- [ ] Biên dịch/chạy `BinaryFloatingDemo.java` bằng `javac`/`java` và đối chiếu từng dòng.

**Kết luận:** `float` và `double` biểu diễn số thực bằng **dấu phẩy động nhị phân**, có phạm vi rất rộng nhưng chỉ giữ hữu hạn bit có nghĩa. Hãy dự đoán sai số làm tròn, chọn kiểu theo yêu cầu độ chính xác, kiểm tra các giá trị đặc biệt và dùng mô hình thập phân thích hợp khi nghiệp vụ đòi kết quả decimal chính xác.