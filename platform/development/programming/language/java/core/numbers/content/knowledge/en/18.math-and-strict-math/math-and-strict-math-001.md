# abs, min, max, signum và clamp theo phiên bản JDK

> **Java core – numbers · Math và StrictMath**  
> **Mục tiêu:** Dùng đúng các hàm trị tuyệt đối, chọn cực tiểu/cực đại, xác định dấu và giới hạn giá trị; xử lý tràn số nguyên, NaN, vô cực, số 0 có dấu; phân biệt API chạy được trên Java 17 với `Math.clamp`/`StrictMath.clamp` được bổ sung từ JDK 21.

## 1. Tổng quan: 5 thao tác nhìn đơn giản nhưng có nhiều bẫy

Khi xử lý số, những câu hỏi thường gặp là:

- **`abs(x)`:** độ lớn không âm của x là bao nhiêu?
- **`min(a,b)`:** giá trị nào nhỏ hơn?
- **`max(a,b)`:** giá trị nào lớn hơn?
- **`signum(x)`:** x âm, bằng 0 hay dương?
- **`clamp(x,low,high)`:** đưa x về **đoạn đóng** từ low đến high; nếu x thấp hơn low lấy low, nếu cao hơn high lấy high, nếu nằm trong đoạn thì giữ x.

Ví dụ trực quan trên số nguyên:

```text
             -∞               0         10              +∞
--------------|---------------|----------|----------------|----
                              [0--------10]
clamp(-5,0,10) -> 0
clamp( 7,0,10) -> 7
clamp(20,0,10) -> 10
```

Nhưng Java không chỉ có một hệ số: kiểu nguyên có miền hữu hạn; kiểu floating-point IEEE 754 có NaN, ±Infinity và cả +0.0/-0.0. Một số API cũng **không có trên các JDK cũ**. Vì vậy cần đọc cả **kiểu tham số** lẫn **phiên bản JDK**.

### Bảng định hướng API

| Thao tác | Java 17 | JDK 21+ | Lưu ý |
| --- | --- | --- | --- |
| `Math.abs` / `StrictMath.abs` | Có | Có | `int/long MIN_VALUE` vẫn âm khi lấy abs thường |
| `Math.absExact` / `StrictMath.absExact` | Có (từ 15) | Có | Ném `ArithmeticException` nếu trị tuyệt đối nguyên tràn |
| `Math.min` / `StrictMath.min` | Có | Có | Có overload int, long, float, double |
| `Math.max` / `StrictMath.max` | Có | Có | Truyền NaN cho overload float/double trả NaN |
| `Math.signum` / `StrictMath.signum` | Có | Có | Chỉ có overload float/double |
| `Integer.signum` / `Long.signum` | Có | Có | Trả int −1, 0 hoặc 1 |
| `Math.clamp` / `StrictMath.clamp` | **Không** | **Có, từ 21** | Kiểm tra min/max hợp lệ, nhiều overload |

**Điểm đặc biệt:** trên JDK 21, phương thức `clamp` cho số nguyên nhận `(long value,long min,long max)` hoặc `(long value,int min,int max)`; **không có riêng overload `clamp(int,int,int)` trong bảng API**. Lời gọi với ba biểu thức `int` vẫn có thể dùng overload `long,int,int` bằng cách mở rộng đối số đầu tiên sang `long`, và kiểu trả về khi đó là `int`.

## 2. Math và StrictMath: nên chọn cái nào?

Cả `java.lang.Math` và `java.lang.StrictMath` đều cung cấp những phép toán số học cơ bản. Hai lớp đều có phương thức **static** nên gọi trực tiếp:

```java
int magnitude = Math.abs(-12);
double minimum = StrictMath.min(3.0, 5.0);
```

Không tạo đối tượng `new Math()` hay `new StrictMath()`. Hai lớp này không được thiết kế để khởi tạo.

Với các phép đơn giản trong bài như `abs`, `min`, `max`, `signum`, quy tắc kết quả đặc biệt được mô tả rõ trong Javadoc và hai lớp có ngữ nghĩa tương ứng. `StrictMath` nổi bật ở những phép toán toán học nâng cao có yêu cầu đặc biệt về tính tái lập của thuật toán; **không cần chuyển mọi `Math.abs` thành `StrictMath.abs` để sửa lỗi tràn nguyên hay NaN**.

Từ Java 17, ngữ nghĩa biểu thức dấu phẩy động của Java được thống nhất theo chế độ *always-strict*; điều này **không làm biến mất** NaN, số 0 có dấu hoặc các giới hạn biểu diễn. `Math` và `StrictMath` vẫn là hai API được tài liệu hóa riêng, nhưng trong chủ đề này phải tập trung vào **contract từng phương thức** thay vì coi tên `StrictMath` như một cách đảm bảo phép toán nguyên tự kiểm tra tràn.

## 3. Math.abs và StrictMath.abs: trị tuyệt đối

`abs` trả độ lớn của một số theo quy tắc của kiểu đầu vào:

```java
System.out.println(Math.abs(-7));        // 7
System.out.println(Math.abs(-7L));       // 7
System.out.println(Math.abs(-3.25));     // 3.25
System.out.println(Math.abs(-3.25f));    // 3.25
```

Các overload chuẩn:

| Hàm | Tham số | Kiểu trả về |
| --- | --- | --- |
| `Math.abs(int)` | int | int |
| `Math.abs(long)` | long | long |
| `Math.abs(float)` | float | float |
| `Math.abs(double)` | double | double |

`StrictMath.abs` cũng có bốn overload tương ứng.

Với `float`/`double`, cần nhớ ba trường hợp:

```java
System.out.println(Math.abs(-0.0));                    // 0.0
System.out.println(Math.abs(Double.NEGATIVE_INFINITY)); // Infinity
System.out.println(Double.isNaN(Math.abs(Double.NaN)));  // true
```

`Math.abs(-0.0)` trả **+0.0**, không giữ dấu âm của zero. Nếu phải giữ riêng bit dấu (ví dụ logic nhị phân đặc biệt), `abs` không phải thao tác thích hợp để lưu dấu.

## 4. Bẫy quan trọng: abs của MIN_VALUE có thể vẫn âm

Với số nguyên có dấu theo bù hai, miền âm có thêm **một** giá trị không có đối ứng dương cùng độ lớn:

```text
int:
MIN_VALUE = -2147483648
MAX_VALUE =  2147483647

long:
MIN_VALUE = -9223372036854775808
MAX_VALUE =  9223372036854775807
```

Vì thế trị tuyệt đối toán học của `Integer.MIN_VALUE` là 2.147.483.648, **vượt miền `int`**.

```java
int minimum = Integer.MIN_VALUE;
System.out.println(Math.abs(minimum)); // -2147483648
```

Đây là kết quả của **overflow theo quy tắc số nguyên Java**: `Math.abs(int)` không tự ném ngoại lệ. Tương tự:

```java
System.out.println(Math.abs(Long.MIN_VALUE));
// -9223372036854775808
```

Hậu quả rất thực tế:

```java
int hash = Integer.MIN_VALUE;
int bucket = Math.abs(hash) % 10;
System.out.println(bucket); // -8
```

Nếu sau đó dùng `bucket` làm chỉ số mảng, bạn có thể gặp lỗi. Không dùng công thức `Math.abs(x) % size` như cách **luôn bảo đảm chỉ số không âm**.

### Cách xử lý tùy mục tiêu

**Cần nhận biết overflow và báo lỗi:** từ Java 15 có `Math.absExact(int)`/`Math.absExact(long)` và các phương thức tương ứng của `StrictMath`:

```java
try {
    Math.absExact(Integer.MIN_VALUE);
} catch (ArithmeticException ex) {
    System.out.println("abs overflow");
}
```

**Cần trị tuyệt đối của mọi giá trị int theo một kiểu đủ rộng:**

```java
long exactMagnitude = Math.abs((long) Integer.MIN_VALUE);
System.out.println(exactMagnitude); // 2147483648
```

Cast sang `long` phải xảy ra **trước** khi gọi `abs`. Viết `(long) Math.abs(Integer.MIN_VALUE)` là quá muộn: phép `abs(int)` đã overflow.

**Với `Long.MIN_VALUE`**, ngay cả `long` cũng không đủ chứa độ lớn dương. Khi cần một số nguyên toán học chính xác, dùng `BigInteger`:

```java
import java.math.BigInteger;

BigInteger magnitude =
        BigInteger.valueOf(Long.MIN_VALUE).abs();
System.out.println(magnitude); // 9223372036854775808
```

**Nếu mục tiêu là chỉ số 0..size−1**, cân nhắc `Math.floorMod(hash,size)` khi `size > 0`, thay vì ép trị tuyệt đối:

```java
System.out.println(Math.floorMod(Integer.MIN_VALUE, 10)); // 2
```

Công thức chọn phụ thuộc yêu cầu nghiệp vụ: `floorMod` mang nghĩa modulo không âm với môđun dương, **khác** việc lấy trị tuyệt đối rồi chia lấy dư.

## 5. min và max cho số nguyên

Các phương thức `Math.min(a,b)` và `Math.max(a,b)` chọn phần tử nhỏ/lớn theo thứ tự số.

```java
System.out.println(Math.min(7, 12));   // 7
System.out.println(Math.max(7, 12));   // 12
System.out.println(Math.min(-5L, 3L)); // -5
```

Có overload int, long, float và double. Nếu có lẫn các kiểu, **numeric promotion** và khả năng chọn overload là vấn đề cần để ý:

```java
int small = 5;
long large = 9L;
long result = Math.max(small, large); // chọn overload long
```

Nếu bắt buộc kết quả giữ nguyên kiểu `int`, cần bảo đảm các toán hạng và miền giá trị phù hợp. Đừng ép thu hẹp một giá trị `long` về `int` trước khi chọn min/max nếu có thể mất bit.

### min/max không tự kiểm tra tràn phép tính đầu vào

```java
int a = Integer.MAX_VALUE;
int b = 2;
int chosen = Math.max(a + b, 0); // a+b tràn thành số âm
System.out.println(chosen);      // 0
```

`Math.max` không thể biết biểu thức `a+b` từng có ý định biểu diễn số lớn hơn `Integer.MAX_VALUE`. Phải kiểm tra phép cộng từ trước, chẳng hạn bằng `Math.addExact(a,b)` hoặc chuyển sang `long` trước phép cộng nếu miền đủ rộng.

## 6. min/max với float/double: NaN và số 0 có dấu

Khác số nguyên, kiểu IEEE 754 có `NaN` và hai cách mã hóa số 0.

### 6.1. Khi một đối số là NaN

Đối với overload `float`/`double`:

```java
double result = Math.min(Double.NaN, 42.0);
System.out.println(Double.isNaN(result)); // true
```

Tương tự:

```java
System.out.println(Double.isNaN(
        Math.max(42.0, Double.NaN))); // true
```

**Math.min/max truyền thống ở đây là NaN-propagating.** Không giả định rằng `Math.max(x,0.0)` “lọc bỏ NaN” hoặc trả giá trị 0 khi `x` là NaN.

Nếu nghiệp vụ quy định bỏ qua mẫu đo NaN, hãy định nghĩa logic xử lý missing/invalid data trước, thay vì trông chờ `min/max` tự loại giá trị NaN. Quy tắc bỏ NaN khác với quy tắc làm phép toán đại số thông thường.

### 6.2. Khi một đối số là +0.0, đối số kia -0.0

Hai số 0 so sánh bằng nhau dưới `==`:

```java
System.out.println(+0.0 == -0.0); // true
```

Nhưng `Math.min` và `Math.max` phân biệt dấu của zero:

```java
System.out.println(Math.min(+0.0, -0.0)); // -0.0
System.out.println(Math.max(+0.0, -0.0)); // 0.0
```

Trong thứ tự của các phương thức này, **−0.0 được coi là nhỏ hơn +0.0**. Điều này khác khi dùng toán tử `<`/`>` với zero vì `-0.0 < +0.0` là false.

Các trường hợp tương tự áp dụng cho overload `float`:

```java
float small = Math.min(+0.0f, -0.0f); // -0.0f
float big = Math.max(+0.0f, -0.0f);   // +0.0f
```

Khi debug dạng bit, kiểm tra:

```java
long bits = Double.doubleToRawLongBits(
        Math.min(+0.0, -0.0));
System.out.printf("%016x%n", bits);
// 8000000000000000
```

Số `0x8000000000000000` là mẫu IEEE 754 của `-0.0`. Dùng raw bits khi cần kiểm chứng chính xác dấu zero hoặc mã hóa nhị phân.

## 7. signum là dấu của số, không phải trị tuyệt đối

`Math.signum(float)` và `Math.signum(double)` trả:

- `-1.0` hoặc `-1.0f` nếu đối số là một số âm **khác 0**;
- `+1.0` hoặc `+1.0f` nếu đối số là một số dương **khác 0**;
- giữ nguyên `+0.0` hoặc `-0.0` nếu đầu vào là signed zero;
- trả `NaN` nếu đối số là NaN.

```java
System.out.println(Math.signum(-12.5)); // -1.0
System.out.println(Math.signum( 12.5)); // 1.0
System.out.println(Math.signum(  0.0)); // 0.0
System.out.println(Math.signum( -0.0)); // -0.0
System.out.println(Double.isNaN(
        Math.signum(Double.NaN)));      // true
```

Với `±Infinity`, dấu vẫn xác định: `signum(+Infinity)=+1.0`, `signum(-Infinity)=-1.0`.

**Không có overload `Math.signum(int)` hay `Math.signum(long)`.** Với số nguyên dùng:

```java
System.out.println(Integer.signum(-12)); // -1
System.out.println(Integer.signum(0));   // 0
System.out.println(Long.signum(100L));   // 1
```

Đừng mặc định kiểu trả về của `Math.signum(-12)` là `int`: đối số `int` có thể được chuyển sang `float` và chọn overload `float` (theo quy tắc overload của Java); kết quả **không** phải kiểu `int`. Khi cần xử lý số nguyên tường minh và đúng kiểu, chọn `Integer.signum`/`Long.signum`.

### Tại sao signum(-0.0) không phải 0.0 dương?

Theo IEEE 754, `-0.0` và `+0.0` có dấu khác nhau dù `==` trả true. `Math.signum` trả **chính zero đầu vào** khi đối số bằng zero, nên:

```java
double negativeZero = -0.0;
double result = Math.signum(negativeZero);
System.out.println(result); // -0.0
```

Nếu bạn cần chỉ một phân loại 3 trạng thái `-1,0,+1` trong ứng dụng và **không muốn phân biệt dấu zero**, có thể kiểm tra `x == 0.0` trước để trả số nguyên 0 theo ý nghĩa nghiệp vụ. Nhưng phải xử lý NaN riêng vì phép so sánh `NaN == 0.0` và `NaN < 0.0` đều là false.

## 8. Clamp nghĩa là gì?

*Clamp* (giới hạn/bão hòa) đưa một giá trị vào đoạn đóng `[min,max]`:

\[
\operatorname{clamp}(x,\ell,h)=
\begin{cases}
\ell,&x<\ell\\
h,&x>h\\
x,&\ell\le x\le h.
\end{cases}
\]

Ví dụ ứng dụng:

- Khống chế mức âm lượng từ 0 đến 100.
- Giới hạn chỉ số tiến độ từ 0.0 đến 1.0.
- Đưa điểm số ngoài miền về biên hợp lệ **khi nghiệp vụ chấp nhận bão hòa**.
- Chuyển một `long` thành `int` bằng cách **bão hòa** theo biên `int`, thay vì cắt bit.

**Clamp không giống** phép chia lấy dư, thu hẹp bit hoặc chuẩn hóa (normalization). `clamp(150,0,100)` là 100; `150 % 101` là 49, còn ép `byte` có thể cho số khác nữa.

Đặc biệt, clamp cũng **không phải validate** theo nghĩa từ chối mọi giá trị ngoài miền; nó **chủ động thay** giá trị bằng cận. Nếu dữ liệu ngoài miền phải gây lỗi, kiểm tra biên và ném ngoại lệ thay vì âm thầm clamp.

## 9. Phiên bản JDK: Math.clamp/StrictMath.clamp được thêm từ 21

Một bẫy tương thích rất phổ biến:

```java
// Chỉ có từ JDK 21:
// int volume = Math.clamp(150L, 0, 100);
```

Mã này **không biên dịch khi dùng `javac --release 17`** hoặc biên dịch trên JDK 17 vì ở đó không có phương thức `clamp` của `Math`.

JDK 21 bổ sung bốn overload trong cả `Math` và `StrictMath`:

| Chữ ký overload | Kiểu kết quả | Ý nghĩa |
| --- | --- | --- |
| `clamp(long value, int min, int max)` | `int` | Clamp một `long` vào miền `int` được chỉ rõ |
| `clamp(long value, long min, long max)` | `long` | Clamp số nguyên 64 bit |
| `clamp(float value, float min, float max)` | `float` | Clamp floating-point 32 bit |
| `clamp(double value, double min, double max)` | `double` | Clamp floating-point 64 bit |

Các overload này có cùng ý nghĩa cơ bản ở `Math` và `StrictMath`. Tài liệu Java 21 ghi rõ `Since: 21` cho chúng.

Một lời gọi với ba `int` được giải quyết bằng overload nhận `long,int,int`:

```java
// Java 21+:
int level = Math.clamp(150, 0, 100);
System.out.println(level); // 100
```

Tuy nhiên, nên viết `150L` nếu đang minh họa tính năng **thu hẹp long một cách bão hòa thành int**, để ý định về overload rõ ràng.

### Dùng khi code chạy nhiều phiên bản JDK

Nếu dự án target Java 17 hoặc vẫn phát hành ứng dụng cho Java 17:

- **Không gọi trực tiếp** `Math.clamp` trong code chung được biên dịch bằng `--release 17`.
- Viết helper clamp cho kiểu cần thiết, với kiểm tra `min <= max`.
- Khi nâng tối thiểu lên JDK 21+, cân nhắc chuyển helper về `Math.clamp` và kiểm thử lại các trường hợp NaN/±0.0.

Không đánh giá API chỉ bằng JDK đang chạy trên máy lập trình: một dự án có thể dùng JDK mới để build nhưng dùng `--release 17` cho mục tiêu tương thích.

## 10. Clamp số nguyên: từ long về int bằng bão hòa

Overload:

```java
// Java 21+:
int result = Math.clamp(hugeLong, lowInt, highInt);
```

nhận giá trị đầu vào `long` và hai cận `int`, kết quả luôn nằm trong đoạn được xác định bởi hai cận, nên trả được kiểu `int` mà **không cắt mất các bit cao như narrowing cast**.

Ví dụ:

```java
// Java 21+:
long count = 5_000_000_000L;
int limited = Math.clamp(count, 0, 100);

System.out.println(limited); // 100
```

So sánh với cast:

```java
long count = 5_000_000_000L;
int truncated = (int) count; // làm hẹp theo bit, không clamp
```

Hai thao tác thể hiện **hai hợp đồng hoàn toàn khác**:

- `(int) longValue`: giữ 32 bit thấp và có thể thay đổi dấu/giá trị.
- `Math.clamp(longValue, min, max)`: trả cận gần nhất nếu vượt, giữ giá trị khi nằm trong đoạn.
- `Math.toIntExact(longValue)`: yêu cầu giá trị nằm trong miền `int`, nếu không sẽ **ném `ArithmeticException`**.

Nếu yêu cầu là “giữ nguyên chính xác hoặc báo lỗi”, `Math.toIntExact` phù hợp hơn clamp. Nếu yêu cầu là “luôn cho ra một chỉ số hoặc mức trong giới hạn”, clamp đúng hơn.

### Cận không hợp lệ phải bị từ chối

```java
// Java 21+:
// Math.clamp(5L, 10, 0); // IllegalArgumentException vì 10 > 0
```

Hàm clamp chuẩn **không tự tráo min và max**. Nếu ứng dụng cho phép hai cận bị đảo và muốn đảo chúng, đó là bước **chuẩn hóa dữ liệu nghiệp vụ** riêng; cần định nghĩa rõ trước khi gọi API.

## 11. Clamp float/double: NaN và signed zero không được bỏ qua

Với JDK 21+:

```java
double result = Math.clamp(1.4, 0.0, 1.0);
System.out.println(result); // 1.0
```

Tuy nhiên floating-point cần kiểm tra ràng buộc đặc biệt:

**1. Nếu chính `value` là NaN**, kết quả vẫn là NaN:

```java
// Java 21+:
double result = Math.clamp(Double.NaN, 0.0, 1.0);
System.out.println(Double.isNaN(result)); // true
```

**2. Nếu một trong hai cận là NaN**, hàm ném `IllegalArgumentException`:

```java
// Java 21+:
// Math.clamp(0.5, Double.NaN, 1.0); // IllegalArgumentException
```

**3. Nếu `min > max`**, hàm ném `IllegalArgumentException`. Đây là phần kiểm tra hợp đồng không nên bỏ qua khi tự viết helper cho Java 17.

**4. Zero có dấu được phân biệt theo thứ tự của clamp.**

```java
// Java 21+:
double z = Math.clamp(-0.0, +0.0, 1.0);
System.out.println(z); // 0.0 (zero dương)
```

Khi cận dưới là `+0.0` và giá trị là `-0.0`, việc clamp nâng lên `+0.0`. Đây là điểm khác với việc tự viết:

```java
double naive = -0.0;
if (naive < +0.0) naive = +0.0; // điều kiện false!
```

Vì `-0.0 < +0.0` trả false, cách so sánh thuần `<`/`>` có thể **không tái tạo đúng** kết quả `Math.clamp`.

**5. Một khoảng với `min=+0.0` và `max=-0.0` được xem là không hợp lệ**, dù `+0.0 == -0.0` là true theo phép so sánh số học:

```java
// Java 21+:
// Math.clamp(0.0, +0.0, -0.0); // IllegalArgumentException
```

Với cận hợp lệ `min=-0.0`, `max=+0.0`, đoạn này cho phép cả hai dạng zero theo quy tắc signed-zero của floating-point API.

### Infinity cũng là đối số có quy tắc rõ ràng

Cận có thể là ±Infinity nếu thứ tự hợp lệ; ví dụ `[-Infinity,+Infinity]` là đoạn đầy đủ theo thứ tự của số floating-point không phải NaN.

Nếu input là `+Infinity` và cận trên hữu hạn, clamp trả cận trên. Nhưng nếu application yêu cầu đầu vào **phải hữu hạn**, clamp không thay thế việc `Double.isFinite(x)` trước đó (đặc biệt nếu cận cho phép Infinity).

## 12. Java 17: viết helper clamp khi API chưa có

Một helper cho số nguyên trên Java 17:

```java
static int clampInt17(int value, int min, int max) {
    if (min > max) {
        throw new IllegalArgumentException("min > max");
    }
    return Math.max(min, Math.min(value, max));
}
```

Đây là **phương thức minh họa**, cần nằm trong class. Nó thực hiện bão hòa như định nghĩa clamp cho kiểu `int`, có kiểm tra cận hợp lệ.

Nếu cần thu hẹp `long` thành `int` có bão hòa trên Java 17, dùng helper phù hợp:

```java
static int clampLongToInt17(long value, int min, int max) {
    if (min > max) {
        throw new IllegalArgumentException("min > max");
    }
    if (value < min) return min;
    if (value > max) return max;
    return (int) value; // an toàn: đã chứng minh nằm giữa cận int
}
```

Đây là phiên bản dễ đọc của ý tưởng overload `Math.clamp(long,int,int)` trên Java 21+. Các phép so sánh mở rộng cận `int` lên `long`; cast cuối **chỉ xảy ra khi giá trị đã nằm trong miền cận int**.

### Có nên tự viết float/double bằng Math.min/max?

Có thể viết:

```java
double candidate = Math.max(min, Math.min(value, max));
```

trong ngữ cảnh đã bảo đảm cận hợp lệ, nhưng **không coi đây là drop-in replacement đầy đủ cho Math.clamp trên mọi trường hợp** nếu chưa thêm quy tắc kiểm tra NaN cận, cận đảo và signed zero. Với JDK 21+, ưu tiên API chuẩn khi cần chính xác ngữ nghĩa; với Java 17, xác định chính sách xử lý số thực đặc biệt một cách rõ ràng rồi kiểm thử.

### Tránh bẫy clamp rồi đổi kiểu

```java
// Cần thu hẹp long an toàn trên Java 17:
long total = 5_000_000_000L;
int limited = clampLongToInt17(total, 0, 100);
// limited == 100
```

Đừng làm:

```java
// Sai thứ tự:
// int limited = clampInt17((int) total, 0, 100);
```

Vì cast `long → int` có thể mất bit **trước** khi clamp, làm giá trị đi theo một nhánh sai.

## 13. Đọc overload cho đúng: literal, promotion và kiểu trả về

Java chọn một overload dựa trên **kiểu compile-time của đối số**, không chỉ giá trị hiện tại.

```java
int i = 5;
long l = 5L;

int small = Math.abs(i);  // overload int -> int
long big = Math.abs(l);   // overload long -> long
```

Trong `min/max`, khi trộn `int` và `long`, overload `long` có thể được chọn:

```java
int a = 100;
long b = 200L;
long larger = Math.max(a, b); // 200L
```

Với `signum`, chỉ overload `float` và `double` có trong `Math`/`StrictMath`. Muốn nhận lại số nguyên −1/0/1, dùng `Integer.signum` hoặc `Long.signum`.

Với `clamp` trên JDK 21+:

```java
// long, int, int => kết quả int:
int first = Math.clamp(15L, 0, 10);  // 10

// long, long, long => kết quả long:
long second = Math.clamp(15L, 0L, 10L); // 10

// double, double, double => kết quả double:
double third = Math.clamp(1.5, 0.0, 1.0); // 1.0
```

Nhấn mạnh: **kiểu literal** `0`, `0L` và `0.0` có thể ảnh hưởng phương thức nào được gọi và kiểu của biểu thức kết quả.

Tránh tạo code “linh hoạt” bằng nhiều cast tùy tiện như `Math.clamp((int) someLong,... )`: đoạn cast có thể đã mất dữ liệu trước khi lời gọi bắt đầu.

## 14. Chọn hàm đúng theo mục tiêu nghiệp vụ

| Mục tiêu | Phương án |
| --- | --- |
| Trị tuyệt đối float/double, chấp nhận +0.0 và NaN | `Math.abs(x)` |
| Trị tuyệt đối int/long nhưng không cho phép tràn | `Math.absExact(x)` (Java 15+) |
| Trị tuyệt đối của mọi int theo miền long | `Math.abs((long) x)` |
| Trị tuyệt đối của mọi long kể cả MIN_VALUE theo giá trị toán học | `BigInteger.valueOf(x).abs()` |
| Chọn nhỏ nhất/lớn nhất giữa hai số nguyên | `Math.min/max` |
| Chọn nhỏ/lớn floating-point theo quy tắc Java, NaN lan truyền | `Math.min/max` |
| Phân loại dấu float/double, giữ ±0.0 | `Math.signum` |
| Phân loại dấu int/long thành −1/0/1 | `Integer.signum`/`Long.signum` |
| Bão hòa trong đoạn với JDK 21+ | `Math.clamp`/`StrictMath.clamp` |
| Bão hòa trên Java 17 | Helper có kiểm tra cận |
| Từ chối số ngoài miền thay vì sửa giá trị | So sánh cận rồi ném lỗi; dùng `Math.toIntExact` khi chuyển long → int |
| Lấy chỉ số modulo không âm | `Math.floorMod(x,size)` với size dương |

Ba chiến lược **không tương đương** cần phân biệt:

1. **Clamp/saturation**: kéo về cận nếu vượt.
2. **Checked conversion**: từ chối dữ liệu vượt miền.
3. **Modulo/wraparound**: lấy phần dư hoặc giữ bit thấp.

Một giá trị ngoài miền có thể có cách xử lý hợp lý khác nhau tùy yêu cầu. Hãy ghi rõ hợp đồng dữ liệu thay vì chọn theo tên API “nghe an toàn”.

## 15. Chương trình Java 17+ chạy độc lập

Tạo file **`MathBoundsJava17Demo.java`**:

```java
public class MathBoundsJava17Demo {
    private static int clampInt17(int value, int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min > max");
        }
        return Math.max(min, Math.min(value, max));
    }

    private static int clampLongToInt17(long value, int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min > max");
        }
        if (value < min) return min;
        if (value > max) return max;
        return (int) value;
    }

    public static void main(String[] args) {
        System.out.println("abs(-7) = " + Math.abs(-7));
        System.out.println("abs(INT_MIN) = "
                + Math.abs(Integer.MIN_VALUE));

        try {
            Math.absExact(Integer.MIN_VALUE);
        } catch (ArithmeticException ex) {
            System.out.println("absExact(INT_MIN) = rejected");
        }

        System.out.println("wide abs(INT_MIN) = "
                + Math.abs((long) Integer.MIN_VALUE));
        System.out.println("min(7,12) = " + Math.min(7, 12));
        System.out.println("max(7,12) = " + Math.max(7, 12));

        System.out.println("min(+0,-0) = "
                + Math.min(+0.0, -0.0));
        System.out.println("max(+0,-0) = "
                + Math.max(+0.0, -0.0));
        System.out.println("min(NaN,1) is NaN = "
                + Double.isNaN(Math.min(Double.NaN, 1.0)));

        System.out.println("signum(-3.5) = "
                + Math.signum(-3.5));
        System.out.println("signum(-0.0) = "
                + Math.signum(-0.0));
        System.out.println("int signum(-42) = "
                + Integer.signum(-42));
        System.out.println("strict abs(-7) = "
                + StrictMath.abs(-7));

        System.out.println("clamp17(-5) = "
                + clampInt17(-5, 0, 10));
        System.out.println("clamp17(7) = "
                + clampInt17(7, 0, 10));
        System.out.println("clamp17(20) = "
                + clampInt17(20, 0, 10));
        System.out.println("long-to-int clamp17 = "
                + clampLongToInt17(5_000_000_000L, 0, 100));

        try {
            clampInt17(5, 10, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid bounds = rejected");
        }

        System.out.println("floorMod(INT_MIN,10) = "
                + Math.floorMod(Integer.MIN_VALUE, 10));
    }
}
```

Biên dịch theo API Java 17 ngay cả khi máy cài một JDK mới:

```bash
javac --release 17 MathBoundsJava17Demo.java
java MathBoundsJava17Demo
```

**Stdout dự kiến:**

```text
abs(-7) = 7
abs(INT_MIN) = -2147483648
absExact(INT_MIN) = rejected
wide abs(INT_MIN) = 2147483648
min(7,12) = 7
max(7,12) = 12
min(+0,-0) = -0.0
max(+0,-0) = 0.0
min(NaN,1) is NaN = true
signum(-3.5) = -1.0
signum(-0.0) = -0.0
int signum(-42) = -1
strict abs(-7) = 7
clamp17(-5) = 0
clamp17(7) = 7
clamp17(20) = 10
long-to-int clamp17 = 100
invalid bounds = rejected
floorMod(INT_MIN,10) = 2
```

Giải thích:

- `Math.abs(Integer.MIN_VALUE)` không đủ miền dương và trả cùng số âm; `absExact` phát hiện trường hợp ấy.
- Cast `int → long` trước khi `abs` giữ đủ miền để nhận `2147483648`.
- `min/max` của floating-point xử lý signed zero và NaN khác phép so sánh số học thông thường.
- `signum(-0.0)` giữ dấu zero, `Integer.signum` trả primitive int.
- Hai helper cho Java 17 làm clamp nguyên có kiểm tra cận; helper `long→int` tránh cast thu hẹp quá sớm.
- `floorMod` cho phần dư không âm khi môđun dương.

## 16. Ví dụ riêng cho JDK 21+ với Math.clamp

Chương trình này **không tương thích Java 17**. Tạo file **`MathClampJava21Demo.java`** và biên dịch với `--release 21` hoặc dùng JDK 21+:

```java
public class MathClampJava21Demo {
    public static void main(String[] args) {
        System.out.println("int from long = "
                + Math.clamp(5_000_000_000L, 0, 100));
        System.out.println("long = "
                + Math.clamp(15L, 0L, 10L));
        System.out.println("double = "
                + Math.clamp(1.5, 0.0, 1.0));
        System.out.println("strict = "
                + StrictMath.clamp(-3L, 0L, 10L));

        double zero = Math.clamp(-0.0, +0.0, 1.0);
        System.out.println("negative zero clamped = " + zero);

        double nan = Math.clamp(Double.NaN, 0.0, 1.0);
        System.out.println("NaN value = "
                + Double.isNaN(nan));

        try {
            Math.clamp(5L, 10, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("reversed bounds = rejected");
        }

        try {
            Math.clamp(0.5, Double.NaN, 1.0);
        } catch (IllegalArgumentException ex) {
            System.out.println("NaN bound = rejected");
        }

        try {
            Math.clamp(0.0, +0.0, -0.0);
        } catch (IllegalArgumentException ex) {
            System.out.println("signed zero bounds = rejected");
        }
    }
}
```

Lệnh:

```bash
javac --release 21 MathClampJava21Demo.java
java MathClampJava21Demo
```

**Stdout dự kiến (JDK 21+):**

```text
int from long = 100
long = 10
double = 1.0
strict = 0
negative zero clamped = 0.0
NaN value = true
reversed bounds = rejected
NaN bound = rejected
signed zero bounds = rejected
```

Đây là hai bài demo **riêng biệt theo baseline JDK**, không trộn lẫn. Khi một dự án còn bắt buộc Java 17, hãy dùng chương trình thứ nhất hoặc helper tự viết; không gọi API clamp 21 rồi mong runtime 17 tự hiểu.

## 17. Lỗi phổ biến và cách sửa

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “`Math.abs` luôn không âm” | `abs(Integer.MIN_VALUE)` hoặc `abs(Long.MIN_VALUE)` vẫn âm do overflow |
| “Ép kết quả abs int sang long sẽ sửa lỗi” | Phải ép **đầu vào** sang long trước khi `abs` |
| “absExact có trên mọi JDK cũ” | Có từ Java 15; nếu target thấp hơn phải tự kiểm tra |
| “`Math.signum(int)` là phương thức chuẩn” | Dùng `Integer.signum(int)`; Math.signum chỉ có float/double |
| “`Math.min` với NaN trả số còn lại” | `Math.min/max` cho float/double có NaN thì trả NaN |
| “+0.0 và -0.0 không thể phân biệt bởi min/max” | `min(+0,-0)=-0.0`, `max(+0,-0)=+0.0` |
| “`Math.clamp` có trong Java 17” | API được bổ sung ở Java 21 |
| “`Math.clamp` chỉ là viết tắt của một lệnh cast” | Clamp bão hòa theo biên, cast thu hẹp cắt bit |
| “JDK 21 có overload clamp(int,int,int) riêng” | Overload nguyên là `(long,int,int)` và `(long,long,long)`; int có thể widen |
| “Clamp số thực có thể dùng comparator < > mà không xét zero” | So sánh < > không phân biệt -0.0 và +0.0 |
| “Clamp tự lọc NaN” | NaN ở **value** được giữ; NaN ở **bound** gây `IllegalArgumentException` |
| “min lớn hơn max thì Java sẽ tự đảo” | `Math.clamp` ném `IllegalArgumentException` |
| “Math.max(x,0) ngăn x là NaN” | Không; NaN lan truyền khi dùng overload float/double |
| “StrictMath sẽ sửa overflow hoặc kiểu không hợp lệ” | StrictMath cũng tuân hợp đồng của phép toán được gọi |
| “Clamp luôn là validation dữ liệu” | Nó thay giá trị ngoài miền bằng biên; nếu muốn từ chối cần validate riêng |

## 18. Bài tập có đáp án

**Bài 1.** `Math.abs(Integer.MIN_VALUE)` trả gì? Tại sao?  
**Lời giải:** `-2147483648` vì `+2147483648` vượt miền `int`. Dùng `Math.absExact` để phát hiện hoặc `Math.abs((long) x)` để nhận độ lớn đúng của mọi int.

**Bài 2.** `Math.min(+0.0,-0.0)` và `Math.max(+0.0,-0.0)` có cùng kết quả không?  
**Lời giải:** Không. Lần lượt là `-0.0` và `+0.0`, dù `+0.0 == -0.0` là true.

**Bài 3.** `Math.signum(-0.0)` và `Integer.signum(0)` trả gì?  
**Lời giải:** `-0.0` kiểu double và `0` kiểu int. Hai phương thức không hoàn toàn cùng kiểu/hợp đồng signed zero.

**Bài 4.** `Math.min(Double.NaN,5.0)` trả 5 hay NaN?  
**Lời giải:** NaN. Dùng `Double.isNaN` để kiểm tra; không giả định NaN bị bỏ qua.

**Bài 5.** Một chương trình Java 17 viết `Math.clamp(150L,0,100)` có biên dịch với `--release 17` không?  
**Lời giải:** Không. `Math.clamp` có từ JDK 21. Trên Java 17, dùng helper clamp kiểm tra cận.

**Bài 6.** Trên JDK 21+, `Math.clamp(5_000_000_000L,0,100)` trả kiểu gì và giá trị nào?  
**Lời giải:** Kiểu `int`, giá trị **100** qua overload `(long,int,int)`.

**Bài 7.** `Math.clamp(-0.0,+0.0,1.0)` trả zero nào trên JDK 21+?  
**Lời giải:** `+0.0` vì clamp xét thứ tự signed zero và không để −0.0 thấp hơn cận dưới +0.0.

**Bài 8.** Trên JDK 21+, `Math.clamp(0.0,+0.0,-0.0)` có hợp lệ không?  
**Lời giải:** Không. Cặp cận +0.0 và −0.0 theo thứ tự này bị xem là đảo; ném `IllegalArgumentException`.

**Bài 9.** Với `long x = Long.MIN_VALUE` và cần độ lớn dương chính xác, có đủ dùng `Math.abs(x)` không?  
**Lời giải:** Không. Cần `BigInteger.valueOf(x).abs()` hoặc một biểu diễn không bị giới hạn miền `long`.

**Bài 10.** Một hàm cần **từ chối** số lượng ngoài 0..100. Dùng clamp có phù hợp không?  
**Lời giải:** Không nếu hợp đồng yêu cầu từ chối. Clamp sẽ thay mọi giá trị vượt miền bằng 0 hoặc 100; phải kiểm tra đầu vào và báo lỗi.

**Bài 11.** Khi `Integer.MIN_VALUE` được đưa vào công thức chỉ số `Math.abs(hash)%10`, điều gì xảy ra?  
**Lời giải:** `Math.abs(hash)` còn là `Integer.MIN_VALUE`; toán tử `%` có thể cho kết quả âm `-8`. Dùng `Math.floorMod(hash,10)` nếu mục tiêu là modulo không âm.

**Bài 12.** Vì sao một helper `Math.max(min,Math.min(value,max))` không hoàn toàn thay thế `Math.clamp` nếu thiếu kiểm tra cận?  
**Lời giải:** Helper đó không tự ném lỗi khi min>max hoặc bound NaN theo hợp đồng của `Math.clamp`. Với floating-point còn phải chú ý ±0.0 và special values.

## 19. Checklist khi đọc code Math/StrictMath

1. Xác định **JDK tối thiểu** mà code phải chạy: Java 17 không có `clamp`, Java 21+ có.
2. Xác định **kiểu overload**: int, long, float, double; đặc biệt clamp nguyên có overload `long,int,int`.
3. Với `abs(int/long)`, kiểm tra giá trị `MIN_VALUE` và quyết định **cho overflow, ném lỗi hay đổi kiểu**.
4. Với `min/max(float/double)`, kiểm tra hành vi **NaN** và **signed zero** nếu chúng có thể xuất hiện.
5. Với `signum`, phân biệt `Math.signum(float/double)` với `Integer/Long.signum`.
6. Với `clamp`, kiểm tra ràng buộc **min <= max**, cộng thêm quy tắc NaN/signed zero cho floating-point.
7. Không clamp sau khi đã **cast hẹp bị mất dữ liệu** hoặc sau phép tính tràn.
8. Phân biệt **saturation, exact conversion và modulo**; chọn theo hợp đồng nghiệp vụ.
9. Nếu dùng helper Java 17, kiểm thử biên, loại NaN và mô tả rõ cách xử lý bounds không hợp lệ.
10. Kiểm thử ví dụ trên **đúng phiên bản Java mục tiêu** bằng `javac --release N` khi khả thi.
11. Với API cần giữ giá trị nguyên vượt long, cân nhắc `BigInteger` thay vì cố ép về phạm vi.
12. Trong code review, ưu tiên **ý định rõ ràng** hơn những biểu thức min/max lồng nhau rất khó đọc.

### Tài liệu tham khảo theo phiên bản

- [Math – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html)
- [StrictMath – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StrictMath.html)
- [Math – Java SE 21 (bao gồm clamp)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html)
- [StrictMath – Java SE 21 (bao gồm clamp)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StrictMath.html)

**Ghi nhớ:** `abs`, `min`, `max` và `signum` có mặt trên Java 17, nhưng phải tôn trọng các biên số nguyên và quy tắc IEEE 754. `Math.clamp`/`StrictMath.clamp` chỉ xuất hiện từ **JDK 21**, có kiểm tra bounds và đặc tả rõ cho NaN/±0.0. Khi chọn API, hãy kiểm tra **kiểu dữ liệu**, **mục tiêu xử lý vượt miền**, và **phiên bản JDK** thay vì đoán từ tên hàm.
