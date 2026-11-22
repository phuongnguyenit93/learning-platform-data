# ThreadLocalRandom: giới hạn cận và xử lý đầu vào không hợp lệ trong Java

**Chủ đề:** Java 7 — ThreadLocalRandom  
**Bài học:** Giới hạn cận và đầu vào không hợp lệ  
**Môi trường thực hành:** Java 17+; `java.util.concurrent.ThreadLocalRandom` ra mắt từ Java 7 nhưng **vẫn là API hiện hành**. Các ví dụ dùng thư viện chuẩn Java, ưu tiên các kỹ thuật đang được hỗ trợ; không sử dụng kiến thức lỗi thời hoặc API legacy.

## 1. Tại sao giới hạn cận quan trọng?

Một ứng dụng thường không cần mọi giá trị có thể có của một kiểu số. Nó cần giá trị trong **một miền có ý nghĩa nghiệp vụ**: index của danh sách, thời gian chờ retry, một con xúc xắc 1–6, tỷ lệ sampling, giá trị mô phỏng trong khoảng cho trước.

`ThreadLocalRandom.current()` lấy bộ sinh giả ngẫu nhiên phù hợp với **luồng đang thực thi**. Nhưng bộ sinh **không thể đoán ý nghĩa nghiệp vụ của cận**. Nó chỉ thực thi hợp đồng của phương thức. Nếu ứng dụng truyền cận sai, có thể có ba vấn đề:

1. Java ném `IllegalArgumentException` vì range **không hợp lệ**.
2. Java vẫn tạo số hợp lệ theo API, nhưng ứng dụng lại **hiểu sai cận trên** dẫn đến off-by-one.
3. Trước khi gọi API, ứng dụng **tự tính cận bị overflow**, làm đầu vào truyền đi khác với ý định.

Ví dụ, với danh sách 5 phần tử, các chỉ số hợp lệ là 0..4. Lời gọi đúng là:

```java
int index = ThreadLocalRandom.current().nextInt(5);
```

Với xúc xắc có mặt 1..6:

```java
int die = ThreadLocalRandom.current().nextInt(1, 7);
```

**Hai lời gọi không dùng cùng cận đầu vào** vì cách biểu diễn miền khác nhau. Hiểu rõ `origin` (cận dưới) và `bound` (cận trên **không bao gồm**) là nền tảng để dùng random an toàn.

### 1.1. Ba mục tiêu của bài

- Đọc chính xác hợp đồng của các overload `nextInt`, `nextLong`, `nextDouble` và phát hiện trường hợp không hợp lệ.
- Bảo vệ application boundary: validate input, tránh overflow, tránh chọn index sai, tránh đưa NaN/Infinity vào khoảng xác suất.
- Viết test đúng với dữ liệu giả ngẫu nhiên: **kiểm tra thuộc tính và ngoại lệ**, không hard-code một số tình cờ được tạo ra.

Đây là nội dung về **bounds và invalid inputs**, không phải một bài khẳng định hiệu năng của `ThreadLocalRandom` hoặc hướng dẫn tạo khóa bảo mật bằng PRNG.

## 2. Quy tắc trung tâm: khoảng nửa mở [origin, bound)

Với overload hai cận:

```java
int value = ThreadLocalRandom.current().nextInt(origin, bound);
```

Giá trị thỏa mãn:

```text
origin <= value < bound

Cận dưới: bao gồm origin.
Cận trên: KHÔNG bao gồm bound.
Điều kiện hợp lệ: origin < bound.
```

Ví dụ `nextInt(-3, 4)` có thể sinh: `-3, -2, -1, 0, 1, 2, 3` — **không bao giờ sinh 4**.

Không phải là khoảng đóng `[origin,bound]`. Không phải là khoảng mở hai đầu `(origin,bound)`. Cú pháp `[a,b)` được gọi là **half-open interval**.

### 2.1. Vì sao thiết kế nửa mở hữu ích?

- Độ dài dải mảng `[lo, hi)` bằng `hi-lo` khi hiệu đó không overflow.
- Hai dải liền nhau `[0,5)` và `[5,10)` không chồng lấp, không bỏ sót.
- `nextInt(list.size())` tạo chỉ số tự nhiên 0..size-1.
- Vòng `for (int i=0; i<length; i++)` dùng cùng quy ước.
- Hai khoảng `[1,6)` và `[1,7)` khác nhau đúng một giá trị 6; dễ kiểm tra off-by-one.

**Lưu ý overflow:** dù giá trị được biểu diễn bằng half-open interval, không phải lúc nào tính `bound-origin` bằng kiểu `int`/`long` cũng an toàn. Phần sau tách riêng lỗi này.

### 2.2. Bảng tổng hợp overload và invalid inputs

| API | Miền kết quả | Điều kiện hợp lệ | Lỗi thường gặp |
| --- | --- | --- | --- |
| `nextInt()` | Toàn miền `int` | Không có bound | Cố ép không âm bằng `Math.abs` |
| `nextInt(bound)` | `[0,bound)` | `bound > 0` | `bound = 0` cho list rỗng |
| `nextInt(origin,bound)` | `[origin,bound)` | `origin < bound` | Nhầm bound inclusive; hai cận bằng nhau |
| `nextLong()` | Toàn miền `long` | Không có bound | Giả định kết quả không âm |
| `nextLong(bound)` | `[0,bound)` | `bound > 0` | Bound 0/âm hoặc tính bound overflow |
| `nextLong(origin,bound)` | `[origin,bound)` | `origin < bound` | Tự tính width long bị overflow |
| `nextDouble()` | `[0.0,1.0)` | Không truyền cận | Dùng `<= 1.0` làm test thiếu chặt chẽ |
| `nextDouble(bound)` | `[0.0,bound)` | Bound dương theo contract | Bound 0/âm; dùng non-finite input từ ngoài |
| `nextDouble(origin,bound)` | `[origin,bound)` | Origin phải nhỏ hơn bound | Cận bằng nhau, đảo ngược hoặc tham số không hữu hạn |
| `nextBoolean()` | `true`/`false` | Không truyền cận | Tưởng rằng boolean random tự xác nhận phân quyền |

Đối với `double`, ứng dụng nên **validate finite values bằng `Double.isFinite`** trước khi gọi nếu cận xuất phát từ input không tin cậy. Việc một phép toán floating-point chấp nhận/chuyển đổi vô cực theo implementation không phải lý do để xem NaN/Infinity là một khoảng xác suất có ý nghĩa.

### 2.3. Một giá trị duy nhất vẫn là khoảng hợp lệ

`nextInt(5,6)` luôn trả 5. `nextLong(100L,101L)` luôn trả 100. Khoảng nửa mở có thể chứa **đúng một giá trị nguyên**.

Ngược lại `nextInt(5,5)` là **khoảng rỗng**, ném `IllegalArgumentException`. Nếu ứng dụng muốn xử lý miền rỗng như “không có lựa chọn”, hãy định nghĩa rõ logic và trả `Optional`/thông báo lỗi; không chờ PRNG tự tạo một giá trị giả.

## 3. Đọc tham số nextInt và kiểm thử lỗi thực tế

### 3.1. Bốn tình huống cần phân biệt

```java
ThreadLocalRandom rng = ThreadLocalRandom.current();

int any = rng.nextInt();       // Có thể âm, 0 hoặc dương.
int index = rng.nextInt(10);   // 0..9.
int value = rng.nextInt(-3, 4); // -3..3.
int one = rng.nextInt(5, 6);   // Luôn 5.
```

Đây là snippet dùng trong class/method phù hợp, cần import `ThreadLocalRandom`. Với `nextInt(bound)`, bound phải **dương**. Với hai cận, origin có thể âm, miễn nhỏ hơn bound.

`nextInt(0)`, `nextInt(-1)`, `nextInt(3,3)` và `nextInt(4,3)` đều là những input không hợp lệ và nên có test.

### 3.2. Chương trình runnable: phạm vi int và bốn ngoại lệ

Tạo `IntBoundsDemo.java`:

```java
import java.util.concurrent.ThreadLocalRandom;
public class IntBoundsDemo {
  public static void main(String[] args) {
    ThreadLocalRandom rng = ThreadLocalRandom.current();
    boolean valid = true;
    for (int i = 0; i < 10_000; i++) {
      int value = rng.nextInt(-11, 12);
      valid &= value >= -11 && value < 12;
    }
    int failures = 0;
    try { rng.nextInt(0); } catch (IllegalArgumentException ex) { failures++; }
    try { rng.nextInt(-1); } catch (IllegalArgumentException ex) { failures++; }
    try { rng.nextInt(4, 4); } catch (IllegalArgumentException ex) { failures++; }
    try { rng.nextInt(5, 4); } catch (IllegalArgumentException ex) { failures++; }
    System.out.println("range-valid=" + valid);
    System.out.println("single-value=" + rng.nextInt(5, 6));
    System.out.println("invalid-rejected=" + failures);
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all IntBoundsDemo.java
java IntBoundsDemo
```

**stdout đã kiểm thử:**

```text
range-valid=true
single-value=5
invalid-rejected=4
```

**Giải thích:** 10.000 mẫu từ [-11,12) được kiểm tra theo **bất biến của API** chứ không in số thực tế. Lời gọi `nextInt(5,6)` có duy nhất giá trị hợp lệ là 5. Bốn lời gọi sai được catch theo **kiểu ngoại lệ dự kiến**, không bắt `Exception` chung rồi lặng lẽ bỏ qua.

### 3.3. Đầu vào hợp lệ nhưng không đúng mục tiêu

Ví dụ `nextInt(1,6)` **hợp lệ** theo Java, nhưng nếu dự định tung xúc xắc sáu mặt thì **sai nghiệp vụ** vì chỉ có các mặt 1..5. Đây là lỗi khó phát hiện bằng test chỉ bắt exception — cần test chính sách cận bằng cách kiểm tra **quy ước đầu vào**.

Ngược lại, `nextInt(1,7)` là đúng cho 1..6. Không dùng số 6 được tạo ra “bao nhiêu lần” làm acceptance test; xác nhận logic cận đã biểu diễn đủ 6 giá trị.

## 4. nextLong: giới hạn lớn và range bị overflow khi trừ

Một giá trị `long` có miền rộng hơn `int`. Sử dụng:

```java
long number = ThreadLocalRandom.current().nextLong(1_000L, 2_000L);
```

Giá trị thỏa `1000 <= number < 2000`.

**Không tự tính kích thước khoảng** bằng:

```java
long width = upperExclusive - lowerInclusive;
```

...khi hai cận có thể gần `Long.MIN_VALUE` và `Long.MAX_VALUE`. Phép trừ có thể overflow mặc dù **`lowerInclusive < upperExclusive`** là đúng. `ThreadLocalRandom.nextLong(origin,bound)` tự xử lý phạm vi theo contract; không cần bắt ứng dụng tạo width trong `long` rồi thực hiện modulo thủ công.

### 4.1. Chương trình runnable: khoảng gần toàn miền long

Tạo `LongBoundsDemo.java`:

```java
import java.util.concurrent.ThreadLocalRandom;
public class LongBoundsDemo {
  public static void main(String[] args) {
    ThreadLocalRandom rng = ThreadLocalRandom.current();
    boolean fullRangeValid = true;
    for (int i = 0; i < 10_000; i++) {
      long value = rng.nextLong(Long.MIN_VALUE, Long.MAX_VALUE);
      fullRangeValid &= value >= Long.MIN_VALUE && value < Long.MAX_VALUE;
    }
    int failures = 0;
    try { rng.nextLong(0L); } catch (IllegalArgumentException ex) { failures++; }
    try { rng.nextLong(7L, 7L); } catch (IllegalArgumentException ex) { failures++; }
    try { rng.nextLong(9L, 2L); } catch (IllegalArgumentException ex) { failures++; }
    System.out.println("extreme-range-valid=" + fullRangeValid);
    System.out.println("single-long=" + rng.nextLong(100L, 101L));
    System.out.println("invalid-rejected=" + failures);
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all LongBoundsDemo.java
java LongBoundsDemo
```

**stdout đã kiểm thử:**

```text
extreme-range-valid=true
single-long=100
invalid-rejected=3
```

**Điểm quan trọng:** `Long.MIN_VALUE` và `Long.MAX_VALUE` có thể là hai cận hợp lệ của overload hai tham số vì origin nhỏ hơn bound, dù hiệu số toán học giữa chúng lớn hơn `Long.MAX_VALUE`. **Đừng tự viết `Math.abs(nextLong()) % width`** để thay thế vì overflow, modulo bias và các lỗi cận.

### 4.2. Muốn lấy toàn bộ miền long

Nếu không cần giới hạn, dùng `rng.nextLong()`. Nó có thể trả số âm hoặc dương, kể cả những giá trị gần cực trị. Nếu một code path đòi long luôn dương, hãy dùng `rng.nextLong(positiveBound)` hoặc có validation riêng, không sử dụng `Math.abs` cho mọi giá trị có thể.

### 4.3. Một khoảng quá lớn không nhất thiết là “invalid”

Tự tính width mà bị overflow là **lỗi tính toán của ứng dụng**, không chứng minh bộ sinh không thể xử lý khoảng. Tuy nhiên nếu domain yêu cầu giới hạn width tối đa (ví dụ một request chỉ được chọn trong 1.000 ids), bạn cần kiểm tra bằng kiểu rộng hơn hoặc phép trừ có kiểm tra overflow rồi báo **lỗi nghiệp vụ**, không gán trực tiếp giới hạn kỹ thuật của RNG thành policy.

## 5. nextDouble: nửa mở với số thực và input không hữu hạn

`nextDouble()` trả về giá trị trong `[0.0,1.0)`. Các overload có bound hoặc origin/bound cũng dùng cận trên không bao gồm.

Ví dụ:

```java
double p = ThreadLocalRandom.current().nextDouble();
double x = ThreadLocalRandom.current().nextDouble(-0.75, 0.5);
double y = ThreadLocalRandom.current().nextDouble(0.75);
```

Đây là snippet. Ta có `0.0 <= p < 1.0`, `-0.75 <= x < 0.5` và `0.0 <= y < 0.75`.

**Kiểm tra đầu vào double phải nghiêm hơn kiểm tra int/long** nếu lấy dữ liệu từ request:

- `NaN` làm các phép so sánh thông thường bất thường: `NaN < 1.0` là false và `NaN >= 1.0` cũng false.
- `Double.POSITIVE_INFINITY` hoặc `Double.NEGATIVE_INFINITY` không có ý nghĩa trong nhiều khoảng phục vụ xác suất hoặc latency.
- `origin == bound` kể cả khi cả hai là `0.0` hoặc `-0.0` không tạo miền có độ rộng dương.
- Không tự gọi `nextDouble(Double.NaN,1.0)` rồi phụ thuộc vào kết quả cho business logic.
- Validate cả `Double.isFinite(origin)` và `Double.isFinite(bound)` trước khi áp dụng numeric policy.
- Với độ chính xác rất lớn, phải xem xét rounding; không tự kết luận một khoảng giữa hai số thực **luôn có vô hạn giá trị double biểu diễn được**.

### 5.1. Chương trình runnable: double range và invalid bounds

Tạo `DoubleBoundsDemo.java`:

```java
import java.util.concurrent.ThreadLocalRandom;
public class DoubleBoundsDemo {
  public static void main(String[] args) {
    ThreadLocalRandom rng = ThreadLocalRandom.current();
    boolean valid = true;
    for (int i = 0; i < 10_000; i++) {
      double a = rng.nextDouble(-0.75, 0.5);
      double b = rng.nextDouble(0.75);
      valid &= a >= -0.75 && a < 0.5 && b >= 0.0 && b < 0.75;
    }
    int errors = 0;
    try { rng.nextDouble(0.0); } catch (IllegalArgumentException ex) { errors++; }
    try { rng.nextDouble(2.0, 2.0); } catch (IllegalArgumentException ex) { errors++; }
    try { rng.nextDouble(5.0, -5.0); } catch (IllegalArgumentException ex) { errors++; }
    System.out.println("finite-range-valid=" + valid);
    System.out.println("invalid-rejected=" + errors);
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all DoubleBoundsDemo.java
java DoubleBoundsDemo
```

**stdout đã kiểm thử:**

```text
finite-range-valid=true
invalid-rejected=3
```

Không in mẫu ngẫu nhiên, vì chúng khác nhau giữa các runs. **Kiểm thử** nằm ở bất biến numeric và số exceptions cho các bounds rõ ràng sai.

### 5.2. Vì sao không nên tự sinh bằng `origin + rng.nextDouble()*(bound-origin)`?

Cách tự biến đổi có thể gặp:

- Overflow hoặc Infinity ở `bound-origin` ngay cả khi hai cận được biểu diễn hữu hạn.
- Rounding tạo kết quả tại/ngoài bound mong muốn nếu không xử lý kỹ.
- NaN/Infinity từ input.
- Phân phối khác điều bạn nghĩ khi xử lý cận bất thường.

Ưu tiên `rng.nextDouble(origin,bound)`, kết hợp validation bên ngoài cho các yêu cầu domain. Không tự viết numeric sampler nếu chưa có lý do và test toán học rõ ràng.

## 6. Validate input ở ranh giới ứng dụng trước khi gọi RNG

Với số đến từ form, HTTP request, config hoặc database, xử lý thành ba lớp:

```text
Raw input (string/JSON)
       |
       v
Parse đúng kiểu, phát hiện NumberFormatException
       |
       v
Validate domain (origin < bound, max width, quotas, finite)
       |
       v
ThreadLocalRandom.current().nextInt/nextLong/nextDouble
       |
       v
Sử dụng kết quả với quy tắc nghiệp vụ rõ ràng
```

**Đừng chỉ dựa vào exception của PRNG làm toàn bộ thông báo đầu vào.** Nó biết cận hợp lệ hay không, nhưng không biết business rule “mỗi request chỉ được chọn tối đa 1.000 mã”.

### 6.1. Kiểm tra width mà không overflow int

Nếu `origin` và `exclusiveBound` là `int`, việc trừ bằng `long` tránh overflow:

```java
long width = (long) exclusiveBound - origin;
if (origin >= exclusiveBound || width > maxAllowedWidth) {
    throw new IllegalArgumentException("invalid interval");
}
```

Đây là snippet; `maxAllowedWidth` do ứng dụng định nghĩa. Ép kiểu sang `long` phải xảy ra **trước phép trừ**, không phải sau:

```java
long wrong = (long) (exclusiveBound - origin); // Đã có thể overflow ở phép trừ int.
```

Đây là snippet **minh họa sai**. Nếu width lấy từ kiểu `long` có thể tràn ngay trong long, cần policy dùng `Math.subtractExact`/`BigInteger`/quy tắc so sánh khác.

### 6.2. Chương trình runnable: parse và giới hạn domain

Tạo `BoundsValidationDemo.java`:

```java
import java.util.concurrent.ThreadLocalRandom;
public class BoundsValidationDemo {
  static int sampleLimited(int origin, int exclusiveBound) {
    long width = (long) exclusiveBound - origin;
    if (origin >= exclusiveBound || width > 1_000L)
      throw new IllegalArgumentException("invalid or too-wide interval");
    return ThreadLocalRandom.current().nextInt(origin, exclusiveBound);
  }
  public static void main(String[] args) {
    int sample = sampleLimited(-5, 5);
    int errors = 0;
    try { sampleLimited(5, 5); } catch (IllegalArgumentException ex) { errors++; }
    try { sampleLimited(6, 2); } catch (IllegalArgumentException ex) { errors++; }
    try { sampleLimited(-1_000, 1_000); } catch (IllegalArgumentException ex) { errors++; }
    try { Integer.parseInt("2147483648"); } catch (NumberFormatException ex) { errors++; }
    System.out.println("sample-valid=" + (sample >= -5 && sample < 5));
    System.out.println("input-errors=" + errors);
    System.out.println("max-width-accepted=" + (sampleLimited(0, 1_000) >= 0));
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all BoundsValidationDemo.java
java BoundsValidationDemo
```

**stdout đã kiểm thử:**

```text
sample-valid=true
input-errors=4
max-width-accepted=true
```

**Bốn lỗi được đếm:**

1. `origin==bound` tạo miền rỗng.
2. `origin>bound` đảo ngược cận.
3. `width=2.000` vượt quota 1.000.
4. Chuỗi "2147483648" vượt giới hạn `Integer.MAX_VALUE` nên `Integer.parseInt` ném `NumberFormatException`.

Chương trình tách rõ **lỗi parse**, **lỗi numeric range** và **lỗi policy width**. Đây là ba lý do khác nhau có thể quy ra thông báo người dùng/API response thích hợp.

### 6.3. Vì sao điều kiện width>1.000 không thay thế điều kiện origin<bound?

Với `origin==bound`, width=0, không lớn hơn 1.000 nhưng vẫn là **miền rỗng**. Với `origin>bound`, width âm, điều kiện upper width cũng không bắt được. Vì vậy validate **origin < bound** trước; width quota là bước sau.

### 6.4. Phân biệt số lượng samples với width

Một request có thể yêu cầu `nextInt(0,10)` **100 triệu lần**. Cận hợp lệ và width nhỏ nhưng job vẫn có thể gây DoS CPU. Do đó phải kiểm tra **sampleCount**, deadline, concurrency quota và output volume **ngoài** checks của bounds.

## 7. Khoảng đóng [min,max] và lỗi max+1

Giao diện `ThreadLocalRandom.nextInt(origin,bound)` dùng **bound exclusive**, nhưng nghiệp vụ đôi khi dùng **cả hai cận inclusive**.

Một ví dụ dễ sai:

```java
int number = ThreadLocalRandom.current().nextInt(min, max + 1);
```

Đây là snippet **có điều kiện**: nếu `max==Integer.MAX_VALUE` thì `max+1` overflow thành `Integer.MIN_VALUE`. Khi đó lời gọi nhận cận trên âm và có thể ném exception hoặc biểu diễn sai range.

### 7.1. Cách an toàn cho mọi khoảng đóng của int

Với kiểu `int`, có thể chuyển cận sang `long` **trước khi cộng 1**:

```java
static int randomInclusive(int min, int max) {
    if (min > max) throw new IllegalArgumentException("min > max");
    long upperExclusive = (long) max + 1L;
    return Math.toIntExact(ThreadLocalRandom.current().nextLong(min, upperExclusive));
}
```

Đây là snippet method hoàn chỉnh đặt trong một class có import phù hợp. Khi `max==Integer.MAX_VALUE`, `upperExclusive==2_147_483_648L` vẫn biểu diễn được trong `long`. Kết quả `nextLong` luôn nằm trong miền int đầu vào; `Math.toIntExact` xác minh kết quả khi chuyển kiểu.

**Không tự áp dụng công thức tương tự cho long bằng `Long.MAX_VALUE+1`.** Toàn miền `long` có thể lấy bằng `nextLong()`, hoặc khi cần khoảng đóng đặc biệt có max lớn nhất phải thiết kế lại không dùng phép cộng vượt miền long.

### 7.2. Chương trình runnable: int inclusive kể cả Integer.MAX_VALUE

Tạo `InclusiveIntDemo.java`:

```java
import java.util.concurrent.ThreadLocalRandom;
public class InclusiveIntDemo {
  static int randomInclusive(int min, int max) {
    if (min > max) throw new IllegalArgumentException("min > max");
    long upperExclusive = (long) max + 1L;
    return Math.toIntExact(ThreadLocalRandom.current().nextLong(min, upperExclusive));
  }
  public static void main(String[] args) {
    boolean ordinaryValid = true;
    for (int i = 0; i < 10_000; i++) {
      int v = randomInclusive(-2, 2);
      ordinaryValid &= v >= -2 && v <= 2;
    }
    int top = randomInclusive(Integer.MAX_VALUE, Integer.MAX_VALUE);
    boolean fullDomainValid = true;
    for (int i = 0; i < 100; i++) {
      int value = randomInclusive(Integer.MIN_VALUE, Integer.MAX_VALUE);
      fullDomainValid &= value >= Integer.MIN_VALUE && value <= Integer.MAX_VALUE;
    }
    boolean invertedRejected = false;
    try { randomInclusive(10, 9); } catch (IllegalArgumentException ex) { invertedRejected = true; }
    System.out.println("closed-range-valid=" + ordinaryValid);
    System.out.println("max-int-selected=" + (top == Integer.MAX_VALUE));
    System.out.println("full-domain-valid=" + fullDomainValid);
    System.out.println("inverted-rejected=" + invertedRejected);
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all InclusiveIntDemo.java
java InclusiveIntDemo
```

**stdout đã kiểm thử:**

```text
closed-range-valid=true
max-int-selected=true
full-domain-valid=true
inverted-rejected=true
```

**Không nên diễn giải sai test toàn miền:** `value >= Integer.MIN_VALUE && value <= Integer.MAX_VALUE` luôn đúng cho một `int`, nên dòng đó xác minh API chạy được mà không exception trên extreme bounds, **không** chứng minh phân phối đều hay có khả năng tạo chính xác hai cực trị trong 100 draws. Với test phân phối, cần kỹ thuật kiểm định thống kê riêng và không assert mọi giá trị hiếm sẽ xuất hiện.

### 7.3. Có cách đơn giản hơn nếu chỉ muốn toàn miền?

Có: `ThreadLocalRandom.current().nextInt()`. Helper inclusive có ích khi input thay đổi và phải hỗ trợ một khoảng đóng bất kỳ. Nếu domain luôn là toàn miền int, gọi method không bound dễ hiểu hơn.

## 8. Tràn số và phép Math.abs không sửa được mọi giá trị

Ba anti-pattern thường gặp:

```java
int x = Integer.MAX_VALUE + 1;                       // Overflow.
int y = Math.abs(ThreadLocalRandom.current().nextInt()); // Có thể âm.
int z = Math.abs(ThreadLocalRandom.current().nextInt()) % size; // Bias/race với size=0.
```

Đây là snippets minh họa **không nên dùng** cho index/range code. Trong Java, arithmetic với `int` có thể wrap khi overflow. `Math.abs(Integer.MIN_VALUE)` vẫn trả một số âm, vì magnitude của MIN không biểu diễn được bằng int dương.

Thay vì lấy random bất kỳ rồi biến đổi, dùng **overload bounded** `nextInt(size)` với size dương. Khi ứng dụng cần kiểm soát overflow, dùng `Math.addExact`, `Math.subtractExact`, ép sang kiểu rộng hơn **trước phép tính**, hoặc `BigInteger` nếu miền vượt long.

### 8.1. Chương trình runnable: nhìn thấy overflow mà không dựa vào số random

Tạo `OverflowPitfallsDemo.java`:

```java
import java.util.concurrent.ThreadLocalRandom;
public class OverflowPitfallsDemo {
  public static void main(String[] args) {
    int wrapped = Integer.MAX_VALUE + 1;
    long widened = (long) Integer.MAX_VALUE + 1;
    boolean absNegative = Math.abs(Integer.MIN_VALUE) < 0;
    int dice = ThreadLocalRandom.current().nextInt(1, 7);
    System.out.println("int-upper-overflow=" + (wrapped < 0));
    System.out.println("wide-upper-valid=" + (widened == 2_147_483_648L));
    System.out.println("abs-min-negative=" + absNegative);
    System.out.println("dice-valid=" + (dice >= 1 && dice <= 6));
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all OverflowPitfallsDemo.java
java OverflowPitfallsDemo
```

**stdout đã kiểm thử:**

```text
int-upper-overflow=true
wide-upper-valid=true
abs-min-negative=true
dice-valid=true
```

**Phân tích:**

- `Integer.MAX_VALUE+1` tính trong int → wrap thành giá trị âm.
- `(long)Integer.MAX_VALUE+1` tính trong long → tạo `2147483648L` hợp lệ.
- `Math.abs(Integer.MIN_VALUE)` âm → sai nếu bạn tưởng absolute value luôn không âm.
- `nextInt(1,7)` trả 1..6 → không cần modulo, absolute hoặc cộng bound tự phát.

### 8.2. Modulo bias là gì?

Nếu bạn lấy một số giả ngẫu nhiên trên miền có K khả năng rồi lấy `%n` với n không chia hết K, có phần dư có nhiều tiền ảnh hơn phần dư khác. Kết quả có thể **bị thiên lệch**. `nextInt(n)` có logic bounded generation phù hợp hơn, giảm những lỗi chuyển miền phổ biến.

**Không** khẳng định `%n` luôn sinh phân bố sai với mọi n/nguồn; vấn đề là bạn không có bảo đảm chung nếu tự chế phép biến đổi. Hãy dùng API bounded trực tiếp khi mục tiêu là random index/bucket.

## 9. Danh sách rỗng và lỗi chỉ số

Chọn một phần tử từ `List<T>` là use case phổ biến nhất của `nextInt(size)`:

```java
List<String> names = List.of("A", "B", "C");
int index = ThreadLocalRandom.current().nextInt(names.size());
String name = names.get(index);
```

Đây là snippet. Với list 3 phần tử, index 0..2 hợp lệ. Nhưng nếu list rỗng, `names.size()==0` → `nextInt(0)` ném `IllegalArgumentException`.

**Hãy validate trước** thay vì bắt lỗi RNG rồi gọi là “list index out of bounds”. Với input null, error khác là `NullPointerException` khi đọc `items.size()`; API service nên xác định rõ null có được phép không.

### 9.1. Chương trình runnable: chọn phần tử và xử lý empty/null

Tạo `ChoiceValidationDemo.java`:

```java
import java.util.*;
import java.util.concurrent.ThreadLocalRandom;
public class ChoiceValidationDemo {
  static <T> T choose(List<T> items) {
    Objects.requireNonNull(items, "items");
    if (items.isEmpty()) throw new IllegalArgumentException("empty collection");
    return items.get(ThreadLocalRandom.current().nextInt(items.size()));
  }
  public static void main(String[] args) {
    List<String> names = List.of("A", "B", "C");
    boolean inList = names.contains(choose(names));
    boolean emptyRejected = false, nullRejected = false;
    try { choose(List.of()); } catch (IllegalArgumentException ex) { emptyRejected = true; }
    try { choose(null); } catch (NullPointerException ex) { nullRejected = true; }
    System.out.println("choice-valid=" + inList);
    System.out.println("empty-rejected=" + emptyRejected);
    System.out.println("null-rejected=" + nullRejected);
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ChoiceValidationDemo.java
java ChoiceValidationDemo
```

**stdout đã kiểm thử:**

```text
choice-valid=true
empty-rejected=true
null-rejected=true
```

### 9.2. Có nên chọn lại nếu list đang thay đổi?

Nếu list được thread khác thêm/xóa sau khi đọc `size` nhưng trước khi `get(index)`, dù random index hợp lệ đối với snapshot cũ, một `ArrayList` không được đồng bộ vẫn có thể thay đổi và gây lỗi hoặc data race.

**ThreadLocalRandom không làm List thread-safe.** Giải pháp là snapshot immutable như `List.copyOf` khi thích hợp, giữ lock quanh bước chọn theo chính sách, hoặc dùng cấu trúc concurrent và thuật toán phù hợp. Đừng hiểu check `index<size` là một giao thức an toàn trong môi trường concurrent.

### 9.3. Uniform over entries ≠ uniform over business entities

Nếu `List` chứa bản ghi trùng một khách hàng nhiều lần, xác suất chọn theo **index** không đồng nghĩa xác suất mỗi khách hàng bằng nhau. Valid bounds chỉ xác nhận index không vượt mảng, không xác nhận policy fairness ở tầng nghiệp vụ.

## 10. Xác suất: hợp đồng [0.0, 1.0] đối với input probability

Với ngẫu nhiên kiểu event:

```java
boolean happens = ThreadLocalRandom.current().nextDouble() < p;
```

Đây là snippet. `p` là tham số xác suất nghiệp vụ, thường được phép nằm trong **[0.0,1.0]**:

- `p==0.0`: event **luôn false** vì random ≥0.
- `p==1.0`: event **luôn true** vì random <1.
- `0<p<1`: kết quả thay đổi; không có bảo đảm tỷ lệ đúng tuyệt đối trên một sample nhỏ.
- `p<0`, `p>1`, NaN hoặc Infinity: input **không hợp lệ theo domain**. Quyết định throw/reject thay vì tự clamp ngầm nếu API không công bố policy clamp.

**Đừng nhầm `[0,1]` của xác suất đầu vào với `[0,1)` của `nextDouble()`:** đầu vào `p=1.0` hợp lệ cho event luôn đúng dù `nextDouble()` không tự trả chính xác 1.0.

### 10.1. Chương trình runnable: validate xác suất finite

Tạo `ProbabilityValidationDemo.java`:

```java
import java.util.concurrent.ThreadLocalRandom;
public class ProbabilityValidationDemo {
  static boolean event(double probability) {
    if (!Double.isFinite(probability) || probability < 0.0 || probability > 1.0)
      throw new IllegalArgumentException("probability must be finite in [0, 1]");
    return ThreadLocalRandom.current().nextDouble() < probability;
  }
  public static void main(String[] args) {
    int rejected = 0;
    double[] invalid = {-0.1, 1.1, Double.NaN, Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY};
    for (double probability : invalid) {
      try { event(probability); } catch (IllegalArgumentException ex) { rejected++; }
    }
    System.out.println("zero-always-false=" + !event(0.0));
    System.out.println("one-always-true=" + event(1.0));
    System.out.println("invalid-probabilities=" + rejected);
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ProbabilityValidationDemo.java
java ProbabilityValidationDemo
```

**stdout đã kiểm thử:**

```text
zero-always-false=true
one-always-true=true
invalid-probabilities=5
```

**Vì sao dùng `Double.isFinite` trước so sánh?** NaN có các quy tắc so sánh đặc biệt, dễ khiến điều kiện `p<0||p>1` **không nhận diện được** NaN. Test cũng bao gồm cả hai hướng Infinity.

### 10.2. Không viết test tỷ lệ ngẫu nhiên kiểu “trăm lần phải đúng 10 lần”

Nếu `p=0.1`, số event true trong 100 lần thử là một biến ngẫu nhiên. Không có bảo đảm đúng 10 lần. Muốn test thống kê phải có ngưỡng xác suất, sample size và confidence hợp lý; unit test correctness nên tập trung vào **cận, invalid input và các trường hợp chắc chắn như p=0/p=1**.

## 11. Tái lập test: đừng hard-code kết quả của current()

`ThreadLocalRandom.current()` **không có seed setter hợp lệ cho client**. `setSeed` trên `ThreadLocalRandom` ném `UnsupportedOperationException`; không được dùng nó để “khóa” chuỗi random trong test.

Nếu logic số ngẫu nhiên là một phần của business helper, hãy nhận abstraction `java.util.random.RandomGenerator` (có từ Java 17) rồi truyền implementation vào:

```java
static int sample(RandomGenerator generator, int origin, int bound) {
    if (origin >= bound) throw new IllegalArgumentException("empty range");
    return generator.nextInt(origin, bound);
}
```

Đây là snippet method, cần import `RandomGenerator` và class bao ngoài. Production có thể truyền `ThreadLocalRandom.current()`, trong khi test truyền `SplittableRandom(seed)`.

### 11.1. Chương trình runnable: seeded tests và setSeed bị từ chối

Tạo `SeededBoundsTestDemo.java`:

```java
import java.util.*;
import java.util.random.RandomGenerator;
import java.util.concurrent.ThreadLocalRandom;
public class SeededBoundsTestDemo {
  static int sample(RandomGenerator generator, int origin, int bound) {
    if (origin >= bound) throw new IllegalArgumentException("empty range");
    return generator.nextInt(origin, bound);
  }
  public static void main(String[] args) {
    RandomGenerator a = new SplittableRandom(2026L);
    RandomGenerator b = new SplittableRandom(2026L);
    boolean matches = true, valid = true;
    for (int i = 0; i < 1_000; i++) {
      int x = sample(a, -10, 11), y = sample(b, -10, 11);
      matches &= x == y;
      valid &= x >= -10 && x < 11;
    }
    boolean seedRejected = false;
    try { ThreadLocalRandom.current().setSeed(77L); }
    catch (UnsupportedOperationException ex) { seedRejected = true; }
    System.out.println("repeatable=" + matches);
    System.out.println("range-valid=" + valid);
    System.out.println("threadlocal-seed-rejected=" + seedRejected);
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all SeededBoundsTestDemo.java
java SeededBoundsTestDemo
```

**stdout đã kiểm thử:**

```text
repeatable=true
range-valid=true
threadlocal-seed-rejected=true
```

**Không diễn giải “repeatable=true” là chứng minh ThreadLocalRandom tái lập bằng seed.** Tính lặp lại ở đây là từ **hai `SplittableRandom` độc lập nhận cùng seed**, cùng thuật toán và cùng thứ tự lời gọi. `ThreadLocalRandom` được thử riêng để xác nhận `setSeed` bị từ chối.

### 11.2. Unit test nên kiểm những gì?

- **Positive cases:** sample luôn trong range mong muốn.
- **Negative cases:** invalid ranges ném `IllegalArgumentException`, input parse sai ném `NumberFormatException`.
- **Boundary cases:** origin==bound, đảo ngược, bound=0, số nguyên cực trị, xác suất 0/1.
- **Deterministic paths:** helper nhận seeded generator để tái tạo inputs trong môi trường kiểm soát.
- **Concurrency:** kết quả luôn hợp lệ khi nhiều workers gọi `current()`, không assert thứ tự thread.
- **Performance:** benchmark riêng, không coi unit test làm benchmark phân phối.

### 11.3. Không sử dụng PRNG làm khóa bảo mật

Một seeded generator như `SplittableRandom` giúp test ổn định, **không** nên dùng để tạo API token, password reset token, session secret hoặc cryptographic nonce. `ThreadLocalRandom` cũng không thích hợp cho security-sensitive randomness. Phần 14 có ví dụ phân biệt.

## 12. Nhiều threads: kiểm tra bounds nhưng không giả định thứ tự

Một điểm tốt của `ThreadLocalRandom.current()` là các worker threads có thể sinh random mà không yêu cầu cùng cập nhật một shared `Random` object. Tuy nhiên:

- `ThreadLocalRandom` không bảo đảm mỗi task có một seed riêng theo logical task ID.
- Không khẳng định hai tasks có outputs không bao giờ trùng nhau.
- Không assert một thread chạy trước thread khác.
- Không dùng kết quả random để xác nhận một shared mutable object đã thread-safe.
- Nếu cần giới hạn CPU/RAM/thời gian, có quotas ở cấp service, không phó mặc vào bounds hợp lệ.

### 12.1. Chương trình runnable: 4 tasks × 1.000 mẫu

Tạo `ConcurrentBoundsDemo.java`:

```java
import java.util.*;
import java.util.concurrent.*;
public class ConcurrentBoundsDemo {
  public static void main(String[] args) throws Exception {
    ExecutorService pool = Executors.newFixedThreadPool(4);
    try {
      List<Callable<Integer>> tasks = new ArrayList<>();
      for (int worker = 0; worker < 4; worker++) {
        tasks.add(() -> {
          int violations = 0;
          ThreadLocalRandom rng = ThreadLocalRandom.current();
          for (int i = 0; i < 1_000; i++) {
            long value = rng.nextLong(-1_000L, 1_000L);
            if (value < -1_000L || value >= 1_000L) violations++;
          }
          return violations;
        });
      }
      List<Future<Integer>> futures = pool.invokeAll(tasks, 5, TimeUnit.SECONDS);
      int violations = 0;
      for (Future<Integer> future : futures) violations += future.get();
      System.out.println("tasks=" + futures.size());
      System.out.println("samples=" + 4 * 1_000);
      System.out.println("violations=" + violations);
    } finally {
      pool.shutdownNow();
      pool.awaitTermination(5, TimeUnit.SECONDS);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ConcurrentBoundsDemo.java
java ConcurrentBoundsDemo
```

**stdout đã kiểm thử:**

```text
tasks=4
samples=4000
violations=0
```

**Giải thích:**

1. Mỗi `Callable` lấy `ThreadLocalRandom.current()` **trong worker thực hiện nó**, không phải tại main.
2. Mỗi task tự đếm violations, không có shared non-atomic counter.
3. Main dùng `ExecutorService.invokeAll` **có timeout**, sau đó `Future.get()` để nhận số lỗi từ từng task.
4. Test không in random values hoặc thread names, nên output ổn định khi scheduling thay đổi.
5. Nếu worker vượt thời hạn hoặc bị cancel, `Future.get` có thể ném lỗi; demo không lặng lẽ coi canceled tasks là PASS.

### 12.2. Vì sao không dùng Math.random() trong ví dụ?

`Math.random()` vẫn hợp lệ cho code rất đơn giản, nhưng nó không bộc lộ lựa chọn generator theo thread tại callsite. Bài tập trung `ThreadLocalRandom.current()` để người học hiểu per-thread generation. Đó không phải tuyên bố `Math.random()` là API đã lỗi thời.

## 13. Case thực tế: random jitter/backoff và tràn số khi cộng cận

Giả sử service muốn chọn delay từ 200 đến **dưới 500 milliseconds**:

```java
long delayMs = ThreadLocalRandom.current().nextLong(200L, 500L);
```

Đây là snippet. Kết quả 200..499 ms, **không bao gồm 500**.

Nếu cận tính bằng `base + window`, có nguy cơ overflow:

```java
long upper = Math.addExact(base, window); // Ném ArithmeticException khi overflow.
long jitter = ThreadLocalRandom.current().nextLong(base, upper);
```

Đây là snippet yêu cầu `base`, `window` và policy hợp lệ. `Math.addExact` giúp phát hiện overflow thay vì để `long` wrap rồi truyền một range sai vào `nextLong`.

### 13.1. Chương trình runnable: jitter hợp lệ và vùng sát Long.MAX_VALUE

Tạo `BackoffBoundsDemo.java`:

```java
import java.util.concurrent.ThreadLocalRandom;
public class BackoffBoundsDemo {
  static long jitter(long minInclusive, long maxExclusive) {
    if (minInclusive < 0 || minInclusive >= maxExclusive)
      throw new IllegalArgumentException("invalid delay range");
    return ThreadLocalRandom.current().nextLong(minInclusive, maxExclusive);
  }
  public static void main(String[] args) {
    long delay = jitter(200L, 500L);
    long nearMax = jitter(Long.MAX_VALUE - 3, Long.MAX_VALUE);
    boolean invalid = false, overflowDetected = false;
    try { jitter(500L, 500L); } catch (IllegalArgumentException ex) { invalid = true; }
    try { Math.addExact(Long.MAX_VALUE, 1L); }
    catch (ArithmeticException ex) { overflowDetected = true; }
    System.out.println("normal-valid=" + (delay >= 200L && delay < 500L));
    System.out.println("near-max-valid=" + (nearMax >= Long.MAX_VALUE - 3 && nearMax < Long.MAX_VALUE));
    System.out.println("empty-delay-rejected=" + invalid);
    System.out.println("overflow-detected=" + overflowDetected);
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all BackoffBoundsDemo.java
java BackoffBoundsDemo
```

**stdout đã kiểm thử:**

```text
normal-valid=true
near-max-valid=true
empty-delay-rejected=true
overflow-detected=true
```

**Không nên lấy Long.MAX_VALUE làm thời gian chờ production chỉ vì RNG cho phép.** Đây là bài kiểm thử numeric boundary, không phải một deadline hợp lý. Hệ thống cần max delay, max retries, overall request deadline và scheduling policy; tránh sleep blocking trong event-loop/critical thread.

### 13.2. Không dùng jitter thay cho rate limits

Random delay giúp phân tán retry storms nhưng không có tính đảm bảo rằng 100 tasks sẽ dàn đều từng milliseconds. Backpressure/quotas vẫn cần thiết nếu hệ thống thực có CPU/network/database limits.

## 14. Bounds hợp lệ không có nghĩa là ngẫu nhiên đủ an toàn cho bí mật

`ThreadLocalRandom` là một PRNG **không dành cho mật mã**. Ngay cả khi bạn gọi `nextLong(Long.MIN_VALUE,Long.MAX_VALUE)` và có rất nhiều khả năng, điều đó **không** làm output trở thành secure secret.

**Không dùng `ThreadLocalRandom` cho:**

- Session tokens, password reset tokens.
- API key hoặc authorization secret.
- OTP/challenge nếu cần khả năng chống đoán.
- Cryptographic keys, nonce theo một giao thức mật mã.
- Token có thể bị kẻ tấn công đoán và lạm dụng.

Dùng `java.security.SecureRandom` và chọn entropy/token length theo threat model. Validate token format/length **không đủ** để chứng minh secure generation; nguồn randomness phải đúng.

### 14.1. Chương trình runnable: phân biệt mô phỏng và secret bytes

Tạo `SecureVsNonSecureDemo.java`:

```java
import java.security.SecureRandom;
import java.util.concurrent.ThreadLocalRandom;
public class SecureVsNonSecureDemo {
  public static void main(String[] args) {
    int simulation = ThreadLocalRandom.current().nextInt(100);
    byte[] token = new byte[32];
    SecureRandom secure = new SecureRandom();
    secure.nextBytes(token);
    boolean allZero = true;
    for (byte b : token) allZero &= b == 0;
    System.out.println("simulation-valid=" + (simulation >= 0 && simulation < 100));
    System.out.println("secure-byte-count=" + token.length);
    System.out.println("token-created=" + (token.length == 32));
    System.out.println("not-printed=true");
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all SecureVsNonSecureDemo.java
java SecureVsNonSecureDemo
```

**stdout đã kiểm thử:**

```text
simulation-valid=true
secure-byte-count=32
token-created=true
not-printed=true
```

**Giải thích:** chương trình chỉ in số bytes và một thuộc tính của sample, không đưa bí mật vào stdout. `SecureRandom` cung cấp primitive phù hợp hơn cho secret bytes. Việc tạo 32 bytes là minh họa; ứng dụng thực phải định nghĩa token expiration, access control, encoding, rotation và token-handling policy.

**Không test security bằng cách assert token có ít nhất một byte khác 0.** Một CSPRNG hợp lệ vẫn có thể tạo mẫu toàn 0 với xác suất cực nhỏ; “trông ngẫu nhiên” không phải phép thử security. `allZero` trong ví dụ chỉ được tính cục bộ và **không dùng làm tiêu chí PASS**. Các thuộc tính security phải được đánh giá theo thuật toán/provider và threat model.

## 15. Bảng quyết định: lỗi là của API hay của nghiệp vụ?

| Tình huống | Loại vấn đề | Cách xử lý |
| --- | --- | --- |
| `nextInt(0)` | Input không hợp lệ với API | Validate size>0; trả lỗi miền rỗng |
| `nextInt(-1)` | Bound âm | Reject |
| `nextInt(8,8)` | Hai cận bằng nhau | Reject hoặc định nghĩa case single-value theo [8,9) |
| `nextInt(9,8)` | Đảo cận | Reject |
| `nextInt(1,6)` dùng cho xúc xắc 1–6 | Java chấp nhận nhưng **sai business** | Đổi thành [1,7) |
| `nextLong(Long.MIN_VALUE,Long.MAX_VALUE)` | Khoảng hợp lệ, width toán học lớn | Gọi API trực tiếp; đừng tự tính width signed long |
| `nextDouble(0.0)` | Bound không dương | Reject |
| `probability=NaN` | Domain không hợp lệ, so sánh khác thường | `Double.isFinite` rồi kiểm [0,1] |
| `probability=+Infinity` | Domain không hợp lệ | Reject |
| `maxInclusive=Integer.MAX_VALUE`, gọi max+1 bằng int | Overflow trước khi gọi API | Nâng sang long trước phép cộng |
| `maxInclusive=Long.MAX_VALUE`, gọi max+1 bằng long | Overflow, vượt miền long | Thiết kế khác hoặc dùng `nextLong()` nếu toàn miền |
| `Math.abs(Integer.MIN_VALUE)` | Arithmetic cực trị | Dùng bounded RNG thay vì abs/modulo |
| List rỗng | `nextInt(list.size())` có bound 0 | Validate empty/null |
| List concurrent bị sửa giữa size và get | Shared-state race | Snapshot/lock/ownership |
| Yêu cầu 1 tỷ samples | Bound có thể hợp lệ nhưng tài nguyên bị lạm dụng | CPU/memory quotas, deadline |
| Security token dùng `ThreadLocalRandom` | Sai cấp độ RNG | `SecureRandom` |
| Test assert một random number cụ thể | Test flaky | Assert bounds hoặc inject seeded generator |

### 15.1. Có nên bắt IllegalArgumentException từ RNG không?

Ở boundary nơi input không tin cậy, **validate trước** để đưa lỗi rõ ràng cho người dùng và không dùng exception làm vòng điều khiển bình thường. Ở tầng thấp, `IllegalArgumentException` của API vẫn hữu ích vì chặn trạng thái sai.

Tránh:

```java
try {
    return ThreadLocalRandom.current().nextInt(origin, bound);
} catch (IllegalArgumentException ignored) {
    return 0;
}
```

Đây là snippet **anti-pattern**: nó che lấp invalid input bằng 0, có thể là index hợp lệ nhưng **không phản ánh lựa chọn của người dùng**. Nếu muốn default 0, phải có quy tắc business rõ ràng và kiểm tra miền trước.

### 15.2. Phân loại lỗi trong REST API

Ví dụ một API nhận `min`, `maxExclusive`, `count`:

- Parse lỗi hoặc range sai: thường là **4xx validation response** (tùy API contract).
- Hết quota công việc: trả trạng thái busy/rate-limited theo hợp đồng.
- Lỗi resource hoặc internal failure: phân loại riêng, không báo là lỗi random range.
- Các lỗi non-finite probability: reject trước khi tạo random.

Đây là nguyên tắc thiết kế API, không bắt buộc mọi hệ thống sử dụng cùng một HTTP status code. Quan trọng là **không biến mọi ngoại lệ thành “random failed” mơ hồ**.

## 16. Kiểm thử tốt cho random bounds

### 16.1. Test thuộc tính thay vì số cụ thể

Cách không ổn định:

```java
// Sai về mục tiêu unit test: số có thể khác qua mỗi lần chạy.
assertEquals(6, ThreadLocalRandom.current().nextInt(1, 7));
```

Đây là snippet minh họa một test **flaky**; `assertEquals` thuộc một test framework chứ không phải API Java SE mặc định. Cách phù hợp hơn:

```java
int sample = ThreadLocalRandom.current().nextInt(1, 7);
assertTrue(sample >= 1 && sample < 7);
```

Đây là snippet, `assertTrue` cũng là method của test framework. Trong bài runnable, chúng ta dùng `System.out.println` để in các invariants thay vì phụ thuộc một test library.

### 16.2. Test invalid input theo exception cụ thể

Với unit test hiện đại, có thể dùng `assertThrows(IllegalArgumentException.class, () -> rng.nextInt(0))` trong JUnit nếu dự án đã có JUnit. Đừng nghĩ JUnit là một phần của Java SE; các ví dụ standalone ở đây sử dụng try/catch để không cần dependency.

### 16.3. Boundary tests cần kiểm tra từng lớp

Đối với int:

- `bound==0`, `bound==-1`.
- `origin==bound`.
- `origin>bound`.
- Khoảng chỉ một giá trị `[k,k+1)`.
- Khoảng có số âm, có 0, hoặc gần cực trị.
- Inclusive upper bound là `Integer.MAX_VALUE`.
- List rỗng/null và list có một phần tử.

Đối với long:

- `bound==0`/âm.
- Hai cận bằng nhau và đảo cận.
- Khoảng `[Long.MIN_VALUE,Long.MAX_VALUE)`.
- Khoảng gần `Long.MAX_VALUE`.
- Full domain dùng `nextLong()` khi thích hợp.
- Nghiệp vụ cộng width có thể overflow và cần `Math.addExact`.

Đối với double/probability:

- `bound==0.0`/âm.
- Hai cận bằng nhau.
- NaN/±Infinity từ input; reject theo policy finite.
- `p==0.0`, `p==1.0`, `0<p<1`.
- Cận rất gần nhau có thể cần test về rounding/precision.
- Đừng kiểm tần suất chính xác của một batch nhỏ.

### 16.4. Metamorphic/property-based checks

Một số thuộc tính hữu ích:

- Với input valid, **mọi** output nằm trong [origin,bound).
- Với int range một phần tử, output luôn bằng phần tử đó.
- Với invalid origin>=bound, method ném `IllegalArgumentException`.
- Với seeded generator cùng seed và call order, results có thể được tái lập trong môi trường được kiểm soát.
- Với list size n>0, index luôn thuộc `[0,n)`.
- Với probability 0/1, event luôn false/true.
- Với concurrency, mỗi sample của từng worker vẫn nằm trong range; aggregation không có lost updates nếu state per task.

**Không thể chứng minh uniform distribution chỉ từ 10.000 lần thử trả về trong range.** Range test là **correctness of bounds**, còn randomness quality là một loại kiểm định khác.

## 17. Hiệu năng và độ an toàn trong sản phẩm

### 17.1. Tránh công việc quá lớn do input hợp lệ về mặt numeric

Một request có thể có cận hợp lệ mà vẫn gây tải rất nặng:

```text
min=0, maxExclusive=10
count=1000000000
```

Đầu vào không sai với RNG, nhưng yêu cầu tạo một tỷ mẫu có thể chiếm CPU, bộ nhớ, network nếu trả toàn bộ output. Bắt buộc kiểm soát **count**, payload bytes, timeout, concurrency quota và rate limit theo service.

### 17.2. nextInt() nhanh không cứu một thuật toán O(n²)

Trong một hot loop, chi phí PRNG thường không phải bottleneck duy nhất. Trước khi tối ưu:

1. Tách chi phí tạo số khỏi chi phí xử lý đối tượng và ghi dữ liệu.
2. Đo JIT-warmed workload với JMH nếu cần microbenchmark.
3. So `Random` local/shared, `ThreadLocalRandom`, `SplittableRandom` trong đúng concurrency pattern.
4. Đừng in từng random value trong benchmark.
5. Đảm bảo test correctness và constraints không bị bỏ để tăng tốc.
6. Không đưa crypto API vào benchmark nonsecure rồi kết luận về security.
7. Không chạy test stress vô hạn; đặt time/memory limits.

### 17.3. Nếu cần deterministic replay

Dùng `RandomGenerator` abstraction được cung cấp từ Java 17 và `SplittableRandom(seed)` (hoặc implementation có seed khác) theo ownership per test/task. `ThreadLocalRandom.current()` phù hợp cho workloads đa luồng không cần replay sequence theo task.

Không dùng một mutable `SplittableRandom` instance **chia sẻ cho nhiều threads** vì nó không được thiết kế để thread-safe. Không giả định thread pool giữ mỗi task trên cùng một worker qua các lần chạy.

### 17.4. Nếu cần bảo mật

Chọn `SecureRandom` và threat model phù hợp. Không dùng `nextInt(Integer.MAX_VALUE)` như một “mã OTP mạnh” chỉ vì range lớn. Entropy, secrecy, session life cycle và retry/rate limits là các phần khác nhau của thiết kế an toàn.

## 18. Checklist code review cho bounds

1. `ThreadLocalRandom.current()` được gọi trong thread đang chạy computation cần random chưa?
2. Đây là random **không bảo mật** hay đầu ra được dùng cho bí mật? Nếu là bí mật, đã dùng `SecureRandom` chưa?
3. Với `nextInt(bound)`/`nextLong(bound)`, có validate `bound>0` không?
4. Với hai cận, có validate **`origin<bound`** không?
5. Code có hiểu **origin inclusive, bound exclusive** không?
6. Range có thể chứa số âm không, và code có cố ép mọi số không âm sai cách không?
7. Nếu list rỗng hoặc null, có business policy rõ trước `nextInt(size)` không?
8. Có tránh gọi `Math.abs(Integer.MIN_VALUE)` hoặc modulo thủ công để lấy index không?
9. Có chỗ nào dùng `maxInclusive+1` bằng int/long rồi overflow không?
10. Với int inclusive full range, có nâng cận lên `long` trước khi cộng 1 không?
11. Với long extreme range, có tránh tự tính width signed long bị overflow không?
12. Nếu tính interval width, đã ép kiểu rộng trước phép trừ và đặt quota riêng chưa?
13. Input số từ string có được parse và bắt `NumberFormatException` rõ không?
14. Nếu có double bounds, đã reject NaN/Infinity theo domain policy chưa?
15. Xác suất `p` có nằm trong **[0,1]** và kiểm bằng `Double.isFinite` không?
16. Có phân biệt p=1 hợp lệ với bound=1 exclusive của generator không?
17. Có dùng property-based assertions thay vì assert một số bất kỳ từ current không?
18. Nếu test cần cùng chuỗi, có seeded generator injection không?
19. Có tránh gọi `ThreadLocalRandom.current().setSeed` không?
20. Có không biến invalid range thành default giá trị im lặng không?
21. Có không trộn lỗi RNG với lỗi ứng dụng như count quota, parsing, security không?
22. Có xử lý concurrency riêng của list, array, map hoặc accumulators không?
23. Có giới hạn sampleCount, memory, CPU và request deadline không?
24. Nếu dùng jitter, có min/max, overflow check, max retries và max total deadline không?
25. Có xác nhận API Java 17+ còn hiện hành và tránh APIs chỉ có ở JDK mới hơn nếu yêu cầu 17 không?
26. Có biên dịch, chạy và xác nhận output theo thuộc tính thay vì random values cụ thể chưa?

## 19. Bài tập và đáp án định hướng

**Bài 1 — Hai cận int.** Chạy `IntBoundsDemo`; thay `[-11,12)` bằng `[-2,3)`. Liệt kê các giá trị hợp lệ, không đưa 3 vào đáp án.

**Bài 2 — Bound bằng 0.** Thử `nextInt(0)` và `nextLong(0)`. Viết assertion kiểm đúng `IllegalArgumentException`.

**Bài 3 — Hai cận bằng nhau.** Thử `nextInt(7,7)`. Vì sao không được hiểu là một khoảng có một phần tử 7? Sửa thành `nextInt(7,8)`.

**Bài 4 — List empty.** Chạy `ChoiceValidationDemo`, đổi helper thành trả `Optional<T>` khi list rỗng. Giải thích trade-off giữa return empty và throw.

**Bài 5 — Long extremes.** Chạy `LongBoundsDemo` với cận `Long.MIN_VALUE` và `Long.MAX_VALUE`. Vì sao `bound-origin` có thể overflow dù API hợp lệ?

**Bài 6 — Double range.** Chạy `DoubleBoundsDemo`; bổ sung thử nghiệm `nextDouble(-0.25,0.25)`; assert mọi giá trị trong nửa khoảng.

**Bài 7 — Invalid doubles.** Viết hàm `sampleFinite` validate `Double.isFinite` với input user và reject NaN, Infinity, đảo cận.

**Bài 8 — Domain quota.** Chạy `BoundsValidationDemo`, đổi max width từ 1000 sang 256. Tại sao origin<bound không đủ để enforce quota?

**Bài 9 — Inclusive max.** Chạy `InclusiveIntDemo`; thử khoảng `[Integer.MAX_VALUE-2,Integer.MAX_VALUE]`. Vì sao `(long)max+1` an toàn còn `max+1` bằng int không an toàn?

**Bài 10 — Full domain int.** So `nextInt()` với helper `randomInclusive(Integer.MIN_VALUE,Integer.MAX_VALUE)` về tính hợp lệ; phương án nào rõ nhất nếu luôn muốn toàn miền?

**Bài 11 — Math.abs issue.** Chạy `OverflowPitfallsDemo` và giải thích giá trị `Math.abs(Integer.MIN_VALUE)`. Viết cách lấy random index đúng.

**Bài 12 — Xúc xắc.** Tạo xúc xắc 1..6 bằng hai cách `nextInt(1,7)` và `nextInt(6)+1`; giải thích điều kiện khiến cách cộng có thể nguy hiểm ở miền lớn hơn.

**Bài 13 — Xác suất.** Chạy `ProbabilityValidationDemo`. Kiểm tra p=0, p=1 và 5 invalid probabilities. Tại sao không so tần suất đúng trên 100 lần?

**Bài 14 — Reproducible test.** Chạy `SeededBoundsTestDemo`. Thay seed 2026 bằng 42 ở cả hai generators và xác nhận cùng call order cho cùng results.

**Bài 15 — Nhiều workers.** Chạy `ConcurrentBoundsDemo` với 8 tasks trên pool 4 threads. Không assert threads chạy theo thứ tự và không dùng chung mutable counters.

**Bài 16 — Thread-local vs task-local.** Chạy hai tasks nối tiếp trên một worker thread và phân tích vì sao `current()` không tạo một seed theo logical task ID.

**Bài 17 — Backoff.** Chạy `BackoffBoundsDemo`; thêm max attempts, overall deadline và `Math.addExact` khi tính upper bound.

**Bài 18 — API validation.** Thiết kế endpoint nhận `origin, bound, count`, trả lỗi riêng cho parse, empty range, quá rộng và count vượt quota.

**Bài 19 — Secure random.** Chạy `SecureVsNonSecureDemo`. Giải thích vì sao không dùng `ThreadLocalRandom` tạo reset token và không in secret bytes.

**Bài 20 — Test matrix.** Xây ma trận int/long/double gồm normal, empty, reversed, extreme, non-finite và boundary conditions; kiểm chứng bằng JDK 17 với deadline, không gây treo hoặc tạo lượng random quá lớn.

## 20. Tổng kết

- `ThreadLocalRandom.current()` là cách lấy generator cho luồng hiện tại, phù hợp cho **nonsecurity randomness** trong Java hiện hành.
- `nextInt`, `nextLong`, `nextDouble` với cận dùng **[origin,bound)**: origin bao gồm, bound không bao gồm.
- `nextInt(bound)`/`nextLong(bound)` yêu cầu bound dương; overload hai cận yêu cầu origin nhỏ hơn bound. Input không hợp lệ được báo bằng `IllegalArgumentException`.
- Đừng tự đoán các con số ngẫu nhiên trong unit test; hãy test **range, exceptions và invariants**.
- `Math.abs(Integer.MIN_VALUE)` không làm ra số dương, và `maxInclusive+1` có thể overflow nếu tính bằng cùng kiểu; dùng bounded methods và kiểu rộng hơn đúng chỗ.
- Với long cực trị, không tự tính width signed long; gọi overload `nextLong(origin,bound)` theo contract.
- Dữ liệu ứng dụng cần validation thêm: list không rỗng, xác suất hữu hạn trong [0,1], max range width, sampleCount quota, deadline.
- Seed của `ThreadLocalRandom` không thể đặt thủ công qua `setSeed`; khi test cần tái lập, inject `RandomGenerator` có seed.
- Một RNG thân thiện với concurrency **không tự làm shared state thread-safe**.
- Không dùng `ThreadLocalRandom` cho secrets; dùng `SecureRandom` và chính sách bảo mật phù hợp.
- Các API và kiến thức được trình bày **vẫn áp dụng trên Java 17+**, không dựa vào kỹ thuật đã lỗi thời/legacy.

## Tài liệu chính thức

- [ThreadLocalRandom — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): overload bounds, `current()`, `setSeed`, per-thread pseudorandom.
- [ThreadLocalRandom — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): xác nhận các API vẫn được hỗ trợ.
- [RandomGenerator — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/random/RandomGenerator.html): contract `nextInt/nextLong/nextDouble`, testable abstraction.
- [SplittableRandom — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SplittableRandom.html): seeded generator có thể dùng cho reproducible tests với ownership rõ.
- [Math — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html): `abs`, `addExact`, `toIntExact` và hành vi overflow.
- [Integer — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html): các giá trị cực trị và `parseInt`.
- [Double — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html): `isFinite`, NaN/Infinity.
- [SecureRandom — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html): random mật mã.
- [ExecutorService — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): bounded task execution và lifecycle của executor.
