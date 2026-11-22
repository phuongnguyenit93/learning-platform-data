# Java 7 — ThreadLocalRandom: Sinh số trong khoảng xác định

## 1. Mục tiêu bài học

Bài này tập trung vào một công việc rất thường gặp khi lập trình Java: **sinh số giả ngẫu nhiên nằm trong một khoảng giá trị cho trước**, với `java.util.concurrent.ThreadLocalRandom`. Kỹ năng quan trọng không phải chỉ là nhớ tên `nextInt()`, mà còn là:

- Phân biệt **cận dưới bao gồm** và **cận trên loại trừ**.
- Chọn đúng overload cho `int`, `long`, `float` và `double`.
- Sinh số trong khoảng dương, âm, đi qua 0, hoặc gần giới hạn của kiểu dữ liệu.
- Chuyển yêu cầu khoảng **hai đầu đều bao gồm** thành code **không tràn số**.
- Kiểm tra cận đầu vào, xử lý danh sách rỗng, xác suất và dữ liệu không hợp lệ.
- Dùng bộ sinh ngẫu nhiên trong các luồng đang thực thi mà không chia sẻ sai một đối tượng thread-local.
- Hiểu điều gì có thể **kiểm thử xác định**, điều gì là kết quả ngẫu nhiên, và điều gì không được dùng cho bảo mật.

`ThreadLocalRandom` được giới thiệu trong Java 7 và **vẫn được hỗ trợ trong Java 17+**. Các ví dụ chạy với API hiện hành của Java 17, không dùng những phương thức lỗi thời.

**Quy tắc nền tảng của hầu hết overload có hai cận:**

```text
[origin, bound)
 ^ bao gồm     ^ không bao gồm
```

Ví dụ `nextInt(3, 8)` chỉ có thể trả các số **3, 4, 5, 6, 7**. Nó có thể không xuất hiện một giá trị nào đó trong một lần thử hữu hạn; **khoảng hợp lệ** không phải lời hứa mọi giá trị đều sẽ xuất hiện trong mỗi tập mẫu.

## 2. ThreadLocalRandom là gì và gọi từ đâu?

`ThreadLocalRandom` là bộ sinh số giả ngẫu nhiên dành cho luồng hiện tại, thuộc gói `java.util.concurrent`. Khi nhiều workers cần lấy số, mỗi worker dùng:

```java
ThreadLocalRandom rng = ThreadLocalRandom.current();
int value = rng.nextInt(10, 20);
```

Đây là **snippet trong một phương thức**, cần:

```java
import java.util.concurrent.ThreadLocalRandom;
```

Ý nghĩa: `value` nằm trong **[10, 20)**, tức 10..19. Mỗi worker nên gọi `current()` **từ chính luồng thực thi công việc**. Không lấy một `ThreadLocalRandom` ở main thread rồi truyền làm shared field cho nhiều workers.

Với một phép lấy số ngắn, cú pháp thường dùng nhất là:

```java
int value = ThreadLocalRandom.current().nextInt(10, 20);
```

Với vòng lặp trong cùng worker, có thể giữ reference cục bộ `rng` để code rõ ràng. Không cần tạo `new ThreadLocalRandom()`: constructor không dành cho ứng dụng trực tiếp gọi.

### 2.1. Vì sao chọn ThreadLocalRandom khi có nhiều luồng?

Một đối tượng `java.util.Random` dùng chung vẫn **thread-safe** trong Java 17, nhưng nhiều workers cập nhật cùng trạng thái bộ sinh có thể tạo contention. `ThreadLocalRandom.current()` giảm việc tranh chấp trạng thái ngẫu nhiên dùng chung. Điều này hữu ích khi nhiều tasks sinh số rất thường xuyên.

Đây là lý do chọn API, **không phải** bảo đảm tốc độ luôn nhanh hơn trên mọi JDK/workload. Nếu chỉ lấy vài số trong một request chủ yếu chờ I/O, khác biệt thường không đáng kể. Bài này ưu tiên **độ đúng của các khoảng sinh số**, không tuyên bố một tỷ lệ tăng tốc không được đo.

### 2.2. Thread-local khác với task-local

Pool có thể tái sử dụng cùng worker thread cho nhiều tasks; trạng thái RNG theo **thread**, không tự reset theo request. Nếu cần tái hiện chính xác số phát ra cho từng task bất kể worker nào chạy, hãy cấp một generator riêng có seed cho task hoặc inject `RandomGenerator`. `ThreadLocalRandom.setSeed(long)` không phải cách tạo sequence test cố định: nó **ném `UnsupportedOperationException`**.

## 3. Bảng API sinh số theo khoảng

| Kiểu | API | Khoảng kết quả |
| --- | --- | --- |
| `int` | `rng.nextInt()` | Một giá trị `int` bất kỳ |
| `int` | `rng.nextInt(bound)` | `[0, bound)`, với `bound > 0` |
| `int` | `rng.nextInt(origin, bound)` | `[origin, bound)`, origin < bound |
| `long` | `rng.nextLong()` | Một giá trị `long` bất kỳ |
| `long` | `rng.nextLong(bound)` | `[0, bound)`, bound > 0 |
| `long` | `rng.nextLong(origin, bound)` | `[origin, bound)`, origin < bound |
| `double` | `rng.nextDouble()` | `[0.0, 1.0)` |
| `double` | `rng.nextDouble(bound)` | `[0.0, bound)`, bound dương và hữu hạn |
| `double` | `rng.nextDouble(origin, bound)` | `[origin, bound)`, hai cận hữu hạn, origin < bound |
| `float` | `rng.nextFloat()` | `[0.0f, 1.0f)` |
| `float` | `rng.nextFloat(bound)` | `[0.0f, bound)`, bound dương và hữu hạn |
| `float` | `rng.nextFloat(origin, bound)` | `[origin, bound)`, hai cận hữu hạn, origin < bound |

Các overload `nextFloat(bound)` và `nextFloat(origin,bound)` có trong **Java 17** (theo API `ThreadLocalRandom`/`RandomGenerator` hiện hành). Không cần tự tạo float từ double rồi ép kiểu nếu API trực tiếp đáp ứng yêu cầu.

**Không phải tất cả overload nhận cận kiểu `int`.** Khi muốn khoảng trên 2^31, dùng `long` và `nextLong`; khi muốn giá trị thực, dùng `float` hoặc `double`. Đừng ép kiểu kết quả một cách mù quáng khiến dữ liệu vượt giới hạn.

### 3.1. Tại sao cận trên bị loại trừ?

Khoảng [origin,bound) rất tiện khi làm việc với chỉ số mảng: danh sách có `size=N` sử dụng các index 0 đến N−1, đúng với `nextInt(N)`. Nó cũng thuận lợi khi chia các khoảng nối tiếp không chồng lấp, như [0,10) và [10,20).

Lưu ý: API chỉ bảo đảm kết quả **nằm trong khoảng và phân phối giả ngẫu nhiên theo hợp đồng**; không có chuyện `bound` “cũng được trả ra trong một trường hợp đặc biệt”.

## 4. Sinh int từ 0 đến một cận trên

Giả sử mảng có 8 phần tử. Index hợp lệ là 0..7:

```java
int index = ThreadLocalRandom.current().nextInt(8);
```

Nếu muốn số nguyên từ 0 đến 999:

```java
int value = ThreadLocalRandom.current().nextInt(1_000);
```

Cả hai trường hợp đều **không thể trả chính bound**.

### 4.1. Bound phải dương

```java
ThreadLocalRandom.current().nextInt(0);  // IllegalArgumentException
ThreadLocalRandom.current().nextInt(-5); // IllegalArgumentException
```

Đây là **mã minh họa tình huống lỗi**, không phải code mẫu cần chạy lần lượt. Khi `bound <= 0`, lời gọi không hợp lệ. Nếu `bound` lấy từ kích thước list hoặc giá trị người dùng nhập, hãy validate **trước khi gọi**.

### 4.2. N=1 thì sao?

`rng.nextInt(1)` chỉ có thể trả **0**. Điều này hoàn toàn hợp lệ; nó không có nghĩa RNG hỏng hoặc “không đủ ngẫu nhiên”. Miền có một giá trị thì mọi kết quả đều là giá trị đó.

### 4.3. Cần cả cận dưới khác 0

Chọn overload hai tham số thay vì tự cộng offset:

```java
int delayBucket = ThreadLocalRandom.current().nextInt(50, 151);
```

Kết quả nằm trong **50..150**, không có 151. Cách này làm ý định khoảng rõ ràng và tránh những công thức thủ công dễ bị tràn hoặc lệch phân phối.

## 5. Khoảng chứa số âm hoặc cắt ngang 0

`ThreadLocalRandom` không yêu cầu origin phải không âm:

```java
int temperature = ThreadLocalRandom.current().nextInt(-10, 11);
```

Có thể nhận giá trị từ **−10 đến +10**, bao gồm 0. Hai tham số vẫn theo [origin,bound), nghĩa là bound 11 không xuất hiện.

Ví dụ khác:

```java
int negativeOnly = ThreadLocalRandom.current().nextInt(-9, -2);
```

Kết quả chỉ có thể là **−9, −8, −7, −6, −5, −4, −3**. Cả cận dưới và cận trên đều có thể âm, miễn origin < bound.

### 5.1. Không tự tạo khoảng bằng Math.abs

Anti-pattern:

```java
int value = Math.abs(ThreadLocalRandom.current().nextInt()) % 10;
```

Vấn đề:

- `Math.abs(Integer.MIN_VALUE)` vẫn âm vì trị tuyệt đối không biểu diễn được trong `int`.
- Phép modulo có thể tạo **modulo bias** khi số đầu vào không chia đều theo bound.
- Số âm đầu vào có thể khiến tính toán sau đó sai.

Dùng:

```java
int value = ThreadLocalRandom.current().nextInt(10);
```

Nếu cần khoảng âm/dương, dùng `nextInt(origin,bound)` trực tiếp.

### 5.2. Khoảng rộng có thể vượt kích thước int khi tính chênh lệch

Ví dụ một khoảng từ `Integer.MIN_VALUE` đến cận gần `Integer.MAX_VALUE` có **độ rộng toán học** lớn hơn giá trị dương tối đa của `int`. Không tự viết:

```java
int width = bound - origin; // Có thể overflow.
int value = origin + rng.nextInt(width);
```

Đây là anti-pattern khi `bound-origin` không biểu diễn được trong `int`. Java SE 17 `ThreadLocalRandom.nextInt(origin,bound)` xử lý những khoảng hợp lệ theo hợp đồng; nếu cần một khoảng rộng như vậy, **gọi overload trực tiếp** thay vì tự tính width.

## 6. Sinh long với cận lớn

Nếu giá trị đếm/mốc thời gian lớn hơn phạm vi `int`, dùng `long`:

```java
long serialPart = ThreadLocalRandom.current()
        .nextLong(1_000_000_000_000L, 1_000_000_000_101L);
```

Kết quả trong khoảng từ **1.000.000.000.000** đến **1.000.000.000.100** bao gồm. Chữ `L` sau số literal xác định kiểu long.

### 6.1. nextLong(bound)

```java
long number = ThreadLocalRandom.current().nextLong(10_000_000_000L);
```

Kết quả trong [0,10 tỷ). Bound phải dương.

### 6.2. nextLong(origin,bound)

```java
long adjustment = ThreadLocalRandom.current().nextLong(-1_000L, 1_001L);
```

Có thể trả từ −1000 đến +1000, vì 1001 là exclusive.

### 6.3. Khi khoảng rất rộng

`nextLong(Long.MIN_VALUE, Long.MAX_VALUE)` hợp lệ vì origin < bound, dù phép `bound-origin` nếu tính bằng `long` có thể overflow. **Không** tự lấy hiệu hai cận rồi gọi `nextLong(width)` nếu width có thể tràn.

Hợp đồng API cho phép khoảng hợp lệ, nhưng không suy ra đây là một cơ chế tạo ID duy nhất hoặc khóa bảo mật. Những giá trị long ngẫu nhiên **có thể trùng nhau**.

## 7. Sinh float và double trong khoảng thực

Nếu cần biến thực, dùng:

```java
double ratio = ThreadLocalRandom.current().nextDouble(0.0, 1.0);
double delta = ThreadLocalRandom.current().nextDouble(-2.0, 5.0);
float variation = ThreadLocalRandom.current().nextFloat(-1.5f, 2.5f);
```

Đây là snippet trong phương thức. Khoảng của `delta` là [−2.0,5.0); `variation` là [−1.5f,2.5f). Không có gì cấm origin âm.

### 7.1. Các cận float/double phải hữu hạn

Java SE 17 `ThreadLocalRandom.nextDouble(origin,bound)` và `nextFloat(origin,bound)` yêu cầu **hai cận hữu hạn** và origin < bound. Các cận `NaN`, `Double.POSITIVE_INFINITY` hoặc `Float.NEGATIVE_INFINITY` là không hợp lệ.

```java
ThreadLocalRandom.current().nextDouble(Double.NaN, 1.0);
ThreadLocalRandom.current().nextDouble(0.0, Double.POSITIVE_INFINITY);
ThreadLocalRandom.current().nextFloat(2.0f, 2.0f);
```

Các dòng trên đều minh họa **IllegalArgumentException**, không nên chạy như một nhóm thao tác thành công.

Khi nhận cận từ cấu hình:

```java
static double sampleBetween(double minimum, double maximum) {
    if (!Double.isFinite(minimum) || !Double.isFinite(maximum) ||
            !(minimum < maximum)) {
        throw new IllegalArgumentException("Invalid finite range");
    }
    return ThreadLocalRandom.current().nextDouble(minimum, maximum);
}
```

Đây là phương thức Java 17+ có import `ThreadLocalRandom`. Validate tại boundary giúp thông báo lỗi rõ và không để cấu hình `NaN` đi sâu vào pipeline.

### 7.2. Floating-point không là tập số thực liên tục

`double` chỉ có một tập hữu hạn các giá trị biểu diễn được. Việc tạo `nextDouble(0.0,1.0)` không phải “mọi số thực từ 0 tới 1 có xác suất bằng nhau” theo toán học liên tục. Kết quả là một trong các floating-point values theo phân phối PRNG.

Không đòi phần cuối thập phân cố định, và không dùng equality trực tiếp với một giá trị kỳ vọng như `0.3` để kiểm thử một sample ngẫu nhiên. Dùng **range/property tests** thay cho giá trị cụ thể.

### 7.3. Kết quả có thể bằng origin

Vì cận dưới **bao gồm**, API cho phép kết quả đúng bằng origin. Nhưng với một tập mẫu hữu hạn, **không có bảo đảm origin nhất định xuất hiện**. Vì vậy test “đã thử 100 lần mà chưa thấy origin, chắc API sai” là một test sai.

### 7.4. Cận trên không thể xuất hiện

Theo hợp đồng, nếu bound là 5.0 thì giá trị trả về phải < 5.0. Các thao tác nội bộ của bộ sinh cần xử lý việc làm tròn phù hợp để giữ ràng buộc đó. Không viết code “nếu ra 5.0 thì sửa về 4.999999” ở tầng application như một cơ chế mặc định.

### 7.5. Không dùng công thức scale thủ công nếu overload trực tiếp đáp ứng

Mẫu tự viết:

```java
double value = min + (max - min) *
        ThreadLocalRandom.current().nextDouble();
```

có vẻ đơn giản nhưng có thể gây vấn đề **rounding**, các cận rất lớn hoặc tính toán hiệu cận. Khi dùng được API, hãy gọi `nextDouble(min,max)` và validate finite bounds. Nó thể hiện rõ ý định [min,max).

## 8. Muốn cả hai đầu bao gồm: [minimum, maximum]?

Đề bài thường được nói bằng ngôn ngữ đời thường: “sinh số nguyên từ 1 đến 6”, trong đó số 6 **được phép xuất hiện**. Nhưng overload `nextInt(1,6)` **không** cho 6. Với khoảng nguyên mà max còn nhỏ hơn `Integer.MAX_VALUE`, cách phổ biến:

```java
int dice = ThreadLocalRandom.current().nextInt(1, 7);
```

Đây là biến đổi từ **[1,6]** sang **[1,7)**.

### 8.1. Lỗi tràn số với max+1

Công thức thủ công:

```java
int value = ThreadLocalRandom.current().nextInt(min, max + 1);
```

là một snippet **chỉ an toàn khi min <= max và max < Integer.MAX_VALUE**. Khi `max == Integer.MAX_VALUE`, phép `max + 1` trên kiểu int **tràn về Integer.MIN_VALUE**, khiến origin/bound sai.

Không đưa công thức này vào helper dùng cho mọi `int` nếu chưa xét trường hợp biên.

### 8.2. Cách an toàn cho toàn bộ khoảng int inclusive

Một kỹ thuật dễ chứng minh là **nâng hai cận lên long trước**:

```java
static int nextInclusive(int minimum, int maximum) {
    if (minimum > maximum) {
        throw new IllegalArgumentException("minimum > maximum");
    }
    if (minimum == maximum) return minimum;
    return (int) ThreadLocalRandom.current()
            .nextLong((long) minimum, (long) maximum + 1L);
}
```

Đây là phương thức Java 17+; import `ThreadLocalRandom`. Chúng ta chuyển [minimum,maximum] kiểu int thành [(long)minimum,(long)maximum+1L) kiểu long. Vì maximum kiểu int, `(long)maximum+1L` **không thể tràn long**, kể cả maximum bằng `Integer.MAX_VALUE`. Mọi kết quả trong khoảng vẫn thuộc int, nên cast về int hợp lệ.

Nhánh `minimum == maximum` trả chính giá trị duy nhất. Nhánh `minimum > maximum` báo lỗi theo hợp đồng helper thay vì tạo số vô nghĩa.

### 8.3. Tại sao không cứ nextInt() khi toàn khoảng int?

Nếu yêu cầu đúng **[Integer.MIN_VALUE, Integer.MAX_VALUE]**, `rng.nextInt()` cho giá trị trên toàn bộ miền int. Nhưng helper ở trên hỗ trợ cả **mọi khoảng con** và trường hợp biên bằng một quy tắc rõ ràng.

### 8.4. Cảnh báo riêng với khoảng long inclusive

Công thức `nextLong(min,max+1)` **không an toàn khi `max==Long.MAX_VALUE`** vì long cũng có giới hạn. Không áp dụng helper int nêu trên cho long bằng cách đổi kiểu mù quáng. Nếu yêu cầu sinh từ một khoảng long bao gồm cả `Long.MAX_VALUE`, cần thiết kế thuật toán xét từng trường hợp hoặc dùng cấu trúc số rộng hơn và sampling không thiên lệch; nên ưu tiên mô hình **half-open long [origin,bound)** trong các API ứng dụng khi có thể.

Một số use cases chỉ cần long trong [0,Long.MAX_VALUE), khi ấy `rng.nextLong(Long.MAX_VALUE)` là đủ, nhưng nó **không bao gồm Long.MAX_VALUE**.

## 9. Vì sao không nên tự sinh range bằng modulo?

Sai lầm phổ biến:

```java
int result = min + (rng.nextInt() % (max - min));
```

Các vấn đề: modulo của số âm có thể âm, hiệu có thể overflow, và phân phối có thể bị lệch. Ngay cả thay `nextInt()` bằng `Math.abs(nextInt())` không giải quyết được `Integer.MIN_VALUE` và modulo bias.

Với trường hợp cần [origin,bound), hãy viết:

```java
int result = ThreadLocalRandom.current().nextInt(origin, bound);
```

Đây là snippet trong phương thức với hai cận đã được xác minh hợp lệ. Thư viện xử lý giới hạn phạm vi để giữ hợp đồng.

### 9.1. Có phải nextInt(origin,bound) phân phối hoàn toàn đều?

Javadoc sử dụng ngôn ngữ **pseudorandom/uniformly distributed** cho các overload integer. Trong thực tế, PRNG là thuật toán xác định từ seed nội bộ, không phải nguồn ngẫu nhiên vật lý. Bounded sampling tránh bias do người dùng tự lấy modulo một cách sai, nhưng nó không biến generator thành thiết bị có entropy mật mã.

### 9.2. Không dùng random range để đảm bảo uniqueness

Nếu bạn gọi `rng.nextInt(1,1_000_001)` một triệu lần, các kết quả **có thể trùng**. Khoảng có một triệu khả năng không có nghĩa sinh một triệu lượt sẽ trả đủ một triệu giá trị khác nhau. Nếu cần không trùng, quản lý tập đã dùng hoặc chọn thuật toán permutation/ID generator phù hợp.

## 10. Chương trình Java 17+ hoàn chỉnh: kiểm tra mọi loại range

**Tệp: `RangeBasicsDemo.java`**

Để kiểm thử hợp đồng mà **không in ra những giá trị ngẫu nhiên bất định**, chương trình tạo 50.000 samples và chỉ báo các điều kiện phạm vi. Nó sử dụng:

- `nextInt(1,7)` cho xúc xắc.
- `nextInt(-10,11)` cho miền nguyên âm và dương.
- `nextLong(1_000_000_000_000L,1_000_000_000_101L)` cho miền long lớn.
- `nextFloat(-1.5f,2.5f)`.
- `nextDouble(-2.0,5.0)` và `nextDouble()`.

```java
import java.util.concurrent.ThreadLocalRandom;

public class RangeBasicsDemo {
    public static void main(String[] args) {
        ThreadLocalRandom rng = ThreadLocalRandom.current();
        boolean dice = true, signed = true, large = true;
        boolean floats = true, doubles = true, unit = true;
        final int samples = 50_000;

        for (int i = 0; i < samples; i++) {
            int d = rng.nextInt(1, 7);
            int n = rng.nextInt(-10, 11);
            long largeValue = rng.nextLong(
                    1_000_000_000_000L, 1_000_000_000_101L);
            float f = rng.nextFloat(-1.5f, 2.5f);
            double x = rng.nextDouble(-2.0, 5.0);
            double u = rng.nextDouble();

            dice &= 1 <= d && d < 7;
            signed &= -10 <= n && n < 11;
            large &= 1_000_000_000_000L <= largeValue &&
                    largeValue < 1_000_000_000_101L;
            floats &= -1.5f <= f && f < 2.5f;
            doubles &= -2.0 <= x && x < 5.0;
            unit &= 0.0 <= u && u < 1.0;
        }

        System.out.println("samples = " + samples);
        System.out.println("dice in [1, 7) = " + dice);
        System.out.println("signed int in [-10, 11) = " + signed);
        System.out.println("long in target range = " + large);
        System.out.println("float in [-1.5, 2.5) = " + floats);
        System.out.println("double in [-2.0, 5.0) = " + doubles);
        System.out.println("unit double in [0, 1) = " + unit);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 RangeBasicsDemo.java
java RangeBasicsDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24, mã dùng API Java 17:**

```text
samples = 50000
dice in [1, 7) = true
signed int in [-10, 11) = true
long in target range = true
float in [-1.5, 2.5) = true
double in [-2.0, 5.0) = true
unit double in [0, 1) = true
```

### 10.1. Những gì demo chứng minh

- Overloads được gọi đúng cú pháp Java.
- Tất cả samples quan sát đều tuân thủ khoảng đặt ra.
- Đầu ra gồm các tính chất **ổn định**, không phụ thuộc số được lấy ngẫu nhiên trong từng lần chạy.
- Kiểu int/long/float/double và số literal có suffix phù hợp.

Đây **không phải** phép chứng minh thống kê rằng generator có phân phối hoàn hảo. Một kiểm thử hữu hạn không thể chứng minh tất cả trường hợp của PRNG; nó xác nhận các invariants quan trọng của code.

### 10.2. Vì sao không in ra một giá trị xúc xắc?

Vì nó có thể khác sau mỗi lần chạy. Nếu README ghi `dice=4` làm stdout cố định cho `ThreadLocalRandom`, người học có thể hiểu sai rằng kết quả được bảo đảm. Bài này chỉ in các tính chất mà API cần thỏa.

### 10.3. Độ dài vòng lặp có ý nghĩa gì?

50.000 là số lần thử minh họa, không phải ngưỡng chứng minh tính đúng hay mức tối thiểu mọi ứng dụng phải chạy. Tests trong ứng dụng thật cần chọn số samples theo thời gian kiểm thử và lỗi muốn phát hiện, và nên có thêm boundary/unit tests.

## 11. Chương trình Java 17+: inclusive int không tràn cận trên

**Tệp: `InclusiveIntRangeDemo.java`**

Ví dụ thể hiện helper [minimum,maximum] cho **mọi giá trị int**, kể cả cận có `Integer.MIN_VALUE` và `Integer.MAX_VALUE`.

```java
import java.util.concurrent.ThreadLocalRandom;

public class InclusiveIntRangeDemo {
    static int nextInclusive(int minimum, int maximum) {
        if (minimum > maximum) {
            throw new IllegalArgumentException("minimum > maximum");
        }
        if (minimum == maximum) return minimum;
        return (int) ThreadLocalRandom.current()
                .nextLong((long) minimum, (long) maximum + 1L);
    }

    public static void main(String[] args) {
        boolean singleton = nextInclusive(42, 42) == 42;
        boolean maxSupported = true;
        boolean minSupported = true;
        boolean fullIntSupported = true;

        for (int i = 0; i < 10_000; i++) {
            int high = nextInclusive(
                    Integer.MAX_VALUE - 2, Integer.MAX_VALUE);
            int low = nextInclusive(
                    Integer.MIN_VALUE, Integer.MIN_VALUE + 2);
            int whole = nextInclusive(
                    Integer.MIN_VALUE, Integer.MAX_VALUE);
            maxSupported &= high >= Integer.MAX_VALUE - 2;
            minSupported &= low <= Integer.MIN_VALUE + 2;
            fullIntSupported &=
                    whole >= Integer.MIN_VALUE && whole <= Integer.MAX_VALUE;
        }

        boolean reversedRejected = false;
        try {
            nextInclusive(9, 8);
        } catch (IllegalArgumentException expected) {
            reversedRejected = true;
        }

        System.out.println("singleton = " + singleton);
        System.out.println("upper int endpoint safe = " + maxSupported);
        System.out.println("lower int endpoint safe = " + minSupported);
        System.out.println("whole int range safe = " + fullIntSupported);
        System.out.println("reversed range rejected = " + reversedRejected);
    }
}
```

Chạy:

```bash
javac --release 17 InclusiveIntRangeDemo.java
java InclusiveIntRangeDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24:**

```text
singleton = true
upper int endpoint safe = true
lower int endpoint safe = true
whole int range safe = true
reversed range rejected = true
```

### 11.1. Vì sao sử dụng nextLong cho helper int?

- Cận `maximum+1` được tính **sau khi cast sang long**, nên không tràn.
- Long có đủ chỗ biểu diễn toàn bộ khoảng của int.
- Kết quả trong [minimum,maximum] luôn nằm trong miền int.
- Trường hợp minimum==maximum trả giá trị đó trực tiếp.
- Trường hợp min>max được từ chối rõ ràng.

### 11.2. Có phải demo chắc sẽ tạo Integer.MAX_VALUE?

Không. Test “upper int endpoint safe” kiểm tra **mọi sample quan sát đều nằm trong phạm vi**, không yêu cầu đã xuất hiện giá trị sát cận trên. Nếu khoảng có ba giá trị, xác suất lấy giá trị MAX trong một lượt là khoảng 1/3 theo mô hình uniform, nhưng không có bảo đảm một số lần thử cụ thể sẽ xuất hiện MAX.

### 11.3. Tại sao kiểm tra whole >= MIN && whole <= MAX có vẻ hiển nhiên?

Vì biến `whole` là int, hai điều kiện hiển nhiên true; dòng kiểm tra chỉ làm rõ **miền giá trị đầy đủ** và chứng minh helper không ném ngoại lệ cho trường hợp hai cận cực đại. Để kiểm thử thuật toán phân phối, phải thiết kế bài test khác, không dựa vào hai so sánh này.

### 11.4. Khi nào dùng direct nextInt thay helper?

Nếu API nghiệp vụ có thể chấp nhận [origin,bound) thì nên gọi `nextInt(origin,bound)` trực tiếp — ít code hơn, không cần thêm helper và tránh hiểu nhầm. Helper inclusive chỉ có ích khi **hợp đồng nghiệp vụ thật sự dùng hai cận đều bao gồm**.

## 12. Dùng range cho chọn phần tử và thời gian retry

Khoảng số thường là một bước trong thuật toán ứng dụng, không phải mục tiêu cuối.

### 12.1. Chọn ngẫu nhiên một phần tử từ List

Với danh sách không rỗng, index hợp lệ [0,size):

```java
static <T> T choose(List<T> items) {
    if (items.isEmpty()) {
        throw new IllegalArgumentException("No choices");
    }
    int index = ThreadLocalRandom.current().nextInt(items.size());
    return items.get(index);
}
```

Đây là phương thức Java 17+ với import `java.util.List` và `ThreadLocalRandom`.

**Quan trọng:** nếu list bị thêm/xóa từ thread khác giữa lúc gọi `size()` và `get(index)`, vẫn có thể xảy ra race/IndexOutOfBoundsException. RNG không khóa list hộ bạn. Dùng immutable snapshot, thích hợp đồng bộ, hoặc API collection thread-safe theo yêu cầu.

### 12.2. Jitter có cận dưới và trên

Nếu muốn ngẫu nhiên 150 đến 350 ms **bao gồm cả hai đầu**:

```java
long delayMs = ThreadLocalRandom.current().nextLong(150L, 351L);
```

Giá trị 351 không xuất hiện. Random jitter có thể giúp phân tán thời điểm retry, nhưng **không thay thế** deadline, backoff, rate limit và tổng số lần thử. Không dùng `Thread.sleep()` hàng loạt trong request threads để làm backoff nếu kiến trúc có scheduler/async phù hợp.

### 12.3. Lấy mẫu theo xác suất

Muốn chọn với xác suất mục tiêu `p` trong [0,1]:

```java
boolean chosen = ThreadLocalRandom.current().nextDouble() < p;
```

Ở đây `p` phải được validate: hữu hạn, `0.0 <= p <= 1.0`. Nếu `p=0`, kết quả luôn false; nếu `p=1`, kết quả luôn true. Với `p=0.25`, **không** có nghĩa cứ 100 lần sẽ chọn đúng 25; tỷ lệ quan sát có biến động.

### 12.4. Mã ví dụ đầy đủ cho ba trường hợp

**Tệp: `RangeApplicationsDemo.java`**

```java
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;

public class RangeApplicationsDemo {
    static <T> T choose(List<T> items) {
        if (items.isEmpty()) {
            throw new IllegalArgumentException("No choices");
        }
        int index = ThreadLocalRandom.current().nextInt(items.size());
        return items.get(index);
    }

    static boolean selectWithProbability(double probability) {
        if (!Double.isFinite(probability) ||
                probability < 0.0 || probability > 1.0) {
            throw new IllegalArgumentException("Invalid probability");
        }
        return ThreadLocalRandom.current().nextDouble() < probability;
    }

    public static void main(String[] args) {
        boolean validDelay = true;
        for (int i = 0; i < 10_000; i++) {
            long delay = ThreadLocalRandom.current()
                    .nextLong(150L, 351L);
            validDelay &= delay >= 150L && delay < 351L;
        }

        boolean emptyRejected = false;
        try {
            choose(List.<String>of());
        } catch (IllegalArgumentException expected) {
            emptyRejected = true;
        }

        boolean invalidProbabilityRejected = false;
        try {
            selectWithProbability(Double.NaN);
        } catch (IllegalArgumentException expected) {
            invalidProbabilityRejected = true;
        }

        System.out.println("single choice = " + choose(List.of("only")));
        System.out.println("delay in [150, 351) = " + validDelay);
        System.out.println("probability zero = " + selectWithProbability(0.0));
        System.out.println("probability one = " + selectWithProbability(1.0));
        System.out.println("empty list rejected = " + emptyRejected);
        System.out.println("NaN probability rejected = " +
                invalidProbabilityRejected);
    }
}
```

Chạy:

```bash
javac --release 17 RangeApplicationsDemo.java
java RangeApplicationsDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24:**

```text
single choice = only
delay in [150, 351) = true
probability zero = false
probability one = true
empty list rejected = true
NaN probability rejected = true
```

### 12.5. Vì sao chọn một phần tử cho stdout?

Với `List.of("only")`, mọi lựa chọn hợp lệ đều là "only", nên output **xác định** dù index vẫn được tạo qua RNG. Điều này tốt hơn việc in một phần tử ngẫu nhiên trong danh sách lớn rồi tuyên bố stdout cố định.

### 12.6. Vì sao dùng Double.isFinite?

`NaN` và ±Infinity có semantics so sánh đặc biệt. Đặc biệt mọi phép so sánh `NaN < p` hoặc `NaN > p` đều false, nên nếu chỉ viết:

```java
if (p < 0 || p > 1) throw new IllegalArgumentException();
```

thì giá trị `NaN` **lọt qua**. Dùng `!Double.isFinite(p)` hoặc một validation tương đương để từ chối NaN và Infinity.

### 12.7. Đừng dùng xác suất làm quota cứng

Một sample 5% dùng `nextDouble()<0.05` **không bảo đảm** tổng số chọn bằng 5% trong một tập hữu hạn. Nếu phải chọn **đúng K trong N**, cần thuật toán sampling theo số lượng hoặc permutation thích hợp, không phải một phép so sánh xác suất độc lập ở từng phần tử.

## 13. Sinh số trong môi trường đa luồng

Khi nhiều worker cùng cần số trong range, mỗi worker nên lấy:

```java
ThreadLocalRandom rng = ThreadLocalRandom.current();
```

**bên trong worker**. Không truyền reference `rng` từ main sang tasks khác. Điều này tận dụng cách dùng thread-confined được tài liệu Java khuyên và không buộc các workers tranh một shared `Random` instance.

### 13.1. Đừng dùng shared mutable sum để “kiểm thử” random

Anti-pattern:

```java
static long sum = 0;
...
sum += ThreadLocalRandom.current().nextInt(1, 7);
```

Đây là **mã sai khi nhiều threads cùng sửa sum không đồng bộ**; phép cộng có data race dù generator là thread-safe. Lỗi ở **kết quả dùng chung**, không phải ở Random.

Hãy tính local sum trong từng task rồi gộp sau `Future.get()`, hoặc dùng primitive đồng bộ nếu cần counter chung.

### 13.2. Mỗi worker có thể trùng số với worker khác

Ngay cả hai workers dùng generator riêng, chúng vẫn có thể cùng trả 4, hoặc cùng trả một `long`. API **không đảm bảo uniqueness** giữa threads. Nếu yêu cầu mã không trùng, dùng ID allocation/protocol riêng.

### 13.3. Kết quả không cố định theo thread scheduling

Thread pool có thể chạy một task khác thread giữa các lần chạy. `ThreadLocalRandom` quản lý state theo **thread**, không phải theo task ID. Do đó unit tests cần replay chính xác nên sử dụng generator seeded riêng theo task, không assert một số cụ thể từ `current()`.

## 14. Chương trình Java 17+ đầy đủ: nhiều worker tạo số trong cùng range

**Tệp: `ParallelRangeAuditDemo.java`**

Chương trình có 4 workers, mỗi worker tạo 20.000 số `long` trong **[-100,101)**, tức từ −100 đến 100 bao gồm. Mỗi worker tự tạo biến `rng` bằng `current()` và trả một `record Audit`. Main đợi cả bốn Futures rồi tổng hợp.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;

public class ParallelRangeAuditDemo {
    private static final int WORKERS = 4;
    private static final int DRAWS_PER_WORKER = 20_000;
    private record Audit(int count, boolean valid, long sum) {}

    private static Audit generate() {
        ThreadLocalRandom rng = ThreadLocalRandom.current();
        long sum = 0L;
        boolean valid = true;
        for (int i = 0; i < DRAWS_PER_WORKER; i++) {
            long n = rng.nextLong(-100L, 101L);
            valid &= n >= -100L && n < 101L;
            sum += n;
        }
        return new Audit(DRAWS_PER_WORKER, valid, sum);
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(WORKERS);
        try {
            List<Future<Audit>> futures = new ArrayList<>();
            for (int i = 0; i < WORKERS; i++) {
                futures.add(pool.submit(ParallelRangeAuditDemo::generate));
            }

            int totalCount = 0;
            long totalSum = 0L;
            boolean allValid = true;
            for (Future<Audit> future : futures) {
                Audit audit = future.get(5, TimeUnit.SECONDS);
                totalCount += audit.count();
                totalSum += audit.sum();
                allValid &= audit.valid();
            }

            System.out.println("workers = " + WORKERS);
            System.out.println("total draws = " + totalCount);
            System.out.println("all values in [-100, 101) = " + allValid);
            System.out.println("sum within possible range = " +
                    (totalSum >= -100L * totalCount &&
                     totalSum <= 100L * totalCount));
            System.out.println("all futures collected = " +
                    (futures.size() == WORKERS));
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Chạy:

```bash
javac --release 17 ParallelRangeAuditDemo.java
java ParallelRangeAuditDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24:**

```text
workers = 4
total draws = 80000
all values in [-100, 101) = true
sum within possible range = true
all futures collected = true
```

### 14.1. Vì sao output không in sum cụ thể?

Tổng số ngẫu nhiên thay đổi theo mỗi lần chạy. Điều có thể xác định là: 4 workers × 20.000 số = 80.000; mỗi số nằm trong [-100,100]; vì vậy tổng nằm trong [-8.000.000,8.000.000]. Main in **một điều kiện** về tổng, không in giá trị tổng cần được cố định.

### 14.2. Tại sao gọi current() trong generate?

Vì `generate()` được thực thi trong worker thread. Mỗi worker dùng RNG của thread hiện hành. Nếu gọi `current()` ở main rồi capture reference vào lambda, sẽ trái với cách dùng thread-local theo Javadoc.

### 14.3. Tại sao dùng Future.get với deadline?

`future.get(5,SECONDS)` đợi task hoàn thành hoặc ném exception nếu thất bại/timeout. Đây là lựa chọn tốt hơn dùng `Thread.sleep(100)` rồi đọc biến chung mà không có bảo đảm synchronization.

Nếu hệ thống quá tải, demo có thể timeout thay vì in đủ năm dòng; đó là failure theo deadline đã chọn, không phải hành vi sai của PRNG.

### 14.4. Thống kê tổng chỉ an toàn ở đâu?

Các workers cập nhật **sum cục bộ**. Main chỉ cộng vào `totalSum` sau khi đã lấy mỗi Future, nên không có hai threads cùng ghi `totalSum`. Sự an toàn về memory và correctness ở phần tổng hợp đến từ thiết kế ownership và Future, không do randomness tạo nên.

## 15. Sinh stream số ngẫu nhiên theo khoảng

`ThreadLocalRandom` có các API tạo streams của số giả ngẫu nhiên. Ví dụ trong **cùng thread**:

```java
int[] draws = ThreadLocalRandom.current()
        .ints(10, 1, 7)
        .toArray();
```

Đây là snippet trong phương thức. Nó tạo 10 int samples trong [1,7). Không có bảo đảm chúng khác nhau.

Với `long` và `double`:

```java
long[] ids = ThreadLocalRandom.current()
        .longs(5, 100L, 200L)
        .toArray();

double[] samples = ThreadLocalRandom.current()
        .doubles(5, 0.0, 1.0)
        .toArray();
```

Đây là snippet trong phương thức. Các overload `ints(streamSize,origin,bound)`, `longs(streamSize,origin,bound)` và `doubles(streamSize,origin,bound)` là API hiện hành. Nếu `streamSize < 0`, phải xử lý lỗi `IllegalArgumentException`; nếu cận không hợp lệ, cũng báo lỗi.

### 15.1. Lười (lazy) và không giới hạn (effectively unlimited)

Có những overload trả streams **effectively unlimited**:

```java
int first = ThreadLocalRandom.current().ints(1, 7)
        .findFirst().orElseThrow();
```

Đây là snippet trong phương thức. Nếu muốn số lượng cụ thể từ stream không giới hạn, dùng `limit(N)` hoặc toán tử giới hạn tương ứng. **Không** gọi `toArray()` trên stream không giới hạn mà thiếu limit: có thể chạy mãi hoặc hết bộ nhớ.

### 15.2. Có nên dùng parallel() trên stream của một ThreadLocalRandom?

Với nhu cầu bình thường, không cần biến stream từ một `ThreadLocalRandom.current()` thành parallel stream rồi phụ thuộc vào một instance được dùng từ các threads khác nhau. Javadoc khuyên lấy `current()` và gọi các phương thức của nó trong **current thread**. Nếu thật sự cần sinh số song song, để mỗi task gọi `ThreadLocalRandom.current()` bên trong thread thực thi, như demo ở phần 14; hoặc dùng một generator có thiết kế splittable và ownership phù hợp.

### 15.3. Khi nào vòng for rõ ràng hơn stream?

Nếu chỉ cần lấy một số, `nextInt(origin,bound)` ngắn nhất. Nếu làm nhiều phép tính phức tạp trong một thread, vòng for với `rng` local dễ kiểm soát. Dùng stream khi nó giúp pipeline đọc rõ hơn; đừng giả định stream luôn có throughput tốt hơn vòng for.

## 16. Cách chọn giá trị ngẫu nhiên cho dữ liệu ứng dụng

### 16.1. Index và kích thước danh sách

Chọn `rng.nextInt(list.size())` sau khi bảo đảm list **không rỗng** và không bị mutate không đồng bộ giữa size/get. Nếu list có một phần tử, index luôn 0. Nếu không cần thứ tự, chọn dựa vào snapshot immutable.

### 16.2. Chọn một bucket từ 0 đến bucketCount−1

```java
if (bucketCount <= 0) {
    throw new IllegalArgumentException("bucketCount must be positive");
}
int bucket = ThreadLocalRandom.current().nextInt(bucketCount);
```

Đây là snippet trong phương thức với biến `bucketCount` đã định nghĩa. Nếu cần weighted buckets, phân phối đều trên index có thể **không phù hợp**; hãy dùng một weighted sampling algorithm có cận và precision đúng.

### 16.3. Chọn một thời điểm tương lai

Để jitter một duration, nên sinh **duration delta** trong một khoảng nhỏ đã xác minh rồi cộng bằng phép cộng có kiểm soát:

```java
long jitterMillis = ThreadLocalRandom.current().nextLong(100L, 501L);
```

Tránh tính thẳng timestamp lớn bằng `nowMillis + jitterMillis` nếu có nguy cơ overflow. Với thời gian thật, `java.time.Duration`, `Instant` và `Math.addExact` hoặc API time có kiểm tra biên có thể rõ ràng hơn.

### 16.4. Tạo tọa độ mô phỏng

Ví dụ `nextDouble(-90.0,90.0)` cho vĩ độ **nhỏ hơn 90.0**, không bao gồm 90.0. Nếu mô hình nghiệp vụ cần chính xác cả hai cực hoặc chính sách phân phối đều trên bề mặt Trái Đất, không thể chỉ lấy vĩ độ/kinh độ đều trên một khoảng và kết luận sample đều trên diện tích. Phải chọn một phân phối phù hợp bản chất bài toán.

### 16.5. Số tiền không nên tùy tiện sinh bằng double

Nếu đang mô phỏng giá trị tiền tệ với bước 0.01, nên xét việc sinh số **đơn vị nhỏ nhất** (ví dụ cents) bằng integer rồi chuyển sang `BigDecimal` hoặc phép tính chính xác phù hợp. Sinh `nextDouble(min,max)` rồi cast/round một cách ngẫu nhiên có thể sinh bias và sai số floating-point ở ranh giới tiền tệ.

### 16.6. Sinh số có các giá trị bị loại trừ

Nếu chỉ muốn các số trong [1,10) **trừ 5**, không thể gọi một overload đơn giản rồi giả định nó biết về ngoại lệ. Có thể dùng rejection sampling khi tỷ lệ bị loại nhỏ, hoặc lập danh sách các giá trị hợp lệ để chọn index. Khi tập bị loại lớn, lặp tới khi trúng giá trị hợp lệ có thể rất chậm; cần thiết kế phân phối/cấu trúc dữ liệu tốt hơn.

## 17. Exception, kiểm tra tham số và khả năng quan sát

| Lời gọi/tình huống | Hành vi |
| --- | --- |
| `nextInt(0)` | `IllegalArgumentException` |
| `nextInt(-1)` | `IllegalArgumentException` |
| `nextInt(5,5)` | `IllegalArgumentException` |
| `nextInt(9,3)` | `IllegalArgumentException` |
| `nextLong(0L)` | `IllegalArgumentException` |
| `nextLong(12L,12L)` | `IllegalArgumentException` |
| `nextDouble(0.0)` | `IllegalArgumentException` (bound không dương) |
| `nextFloat(-1.0f,1.0f)` | Hợp lệ |
| `nextDouble(Double.NaN,1.0)` | `IllegalArgumentException` |
| `nextDouble(0.0,Double.POSITIVE_INFINITY)` | `IllegalArgumentException` |
| `nextFloat(Float.NEGATIVE_INFINITY,1.0f)` | `IllegalArgumentException` |
| `ThreadLocalRandom.current().setSeed(42L)` | `UnsupportedOperationException` |
| Danh sách rỗng và gọi `rng.nextInt(list.size())` | `IllegalArgumentException` |
| Helper inclusive int có minimum > maximum | Helper nên ném `IllegalArgumentException` |

Các lỗi do **cận không hợp lệ** không nên bị catch đại trà rồi im lặng trả 0. Giá trị 0 có thể là đầu ra nghiệp vụ hợp lệ, khiến caller không biết cấu hình đã sai.

### 17.1. Validate ngay tại boundary

Nếu cận đến từ request/config, báo lỗi rõ:

```java
static int randomIndex(int size) {
    if (size <= 0) {
        throw new IllegalArgumentException("size must be positive");
    }
    return ThreadLocalRandom.current().nextInt(size);
}
```

Đây là phương thức Java 17+ với import `ThreadLocalRandom`.

### 17.2. Đừng dùng retry không giới hạn cho cận sai

Một lời gọi `nextInt(5,5)` **luôn sai** vì khoảng rỗng. Lặp lại nó một triệu lần sẽ chỉ ném lỗi một triệu lần. Sửa validation hoặc business configuration, không dùng retry với kỳ vọng lần sau tự hợp lệ.

### 17.3. Logging không nên lộ giá trị nhạy cảm

Nếu sinh test data hoặc jitter, log phạm vi cấu hình, số lần gọi, failures khi cần diagnostic; không log token/password/secret. Quan trọng hơn: **ThreadLocalRandom không phải nguồn để tạo secret ngay từ đầu**.

## 18. Sinh số ngẫu nhiên không bảo đảm bảo mật

`ThreadLocalRandom` tạo **pseudorandom values**, không phải cryptographically secure random. Nó phù hợp cho simulation, load sampling, jitter, lựa chọn không bảo mật. Nó **không** phù hợp để tạo session token, reset-password token, OTP, nonce/key material nhạy cảm.

Ví dụ security-sensitive cần dùng `java.security.SecureRandom`:

```java
SecureRandom secure = new SecureRandom();
byte[] token = new byte[32];
secure.nextBytes(token);
```

Đây là snippet với `import java.security.SecureRandom;`. Đầu ra cần được xử lý an toàn theo authentication/token protocol; bản thân việc chọn SecureRandom chưa thay thế expiration, lưu trữ/chống replay hoặc kiểm soát quyền truy cập.

### 18.1. Random trong khoảng không tạo unique ID

Giá trị trong một dải hữu hạn có thể trùng, ngay cả khi generator có chất lượng thống kê tốt. Nếu cần ID duy nhất, sử dụng chiến lược allocation/sequence/UUID có đánh giá collision và yêu cầu hệ thống rõ. Không suy rằng chọn dải long lớn là “unique guaranteed”.

### 18.2. Random trong khoảng không tạo fairness tuyệt đối cho mọi mẫu

Nếu đặt cược, phân chia phần thưởng, chọn lottery hoặc business yêu cầu chống gian lận, cần algorithm, nguồn entropy, auditing và security design phù hợp. `nextInt(origin,bound)` không thay được toàn bộ fairness/security protocol.

## 19. Tái lập kết quả khi cần test theo giá trị cụ thể

`ThreadLocalRandom` không hỗ trợ `setSeed` để người viết kiểm soát chuỗi. Nếu một unit test cần expected sequence cụ thể, có thể dùng `new Random(seed)`, `new SplittableRandom(seed)` hoặc một `RandomGenerator` hỗ trợ seed/algorithm đã chọn.

Trong Java 17:

```java
import java.util.Random;
import java.util.random.RandomGenerator;

static int roll(RandomGenerator rng) {
    return rng.nextInt(1, 7);
}

// Trong một phương thức test:
int value = roll(new Random(2026L));
```

Đây là **snippet** gồm import/method/call; không phải một file độc lập vì call cần đặt trong method/initializer. Dùng interface `RandomGenerator` giúp ứng dụng phân biệt một **production RNG** với một **seeded test RNG** mà không viết lại business logic.

### 19.1. Không chia sẻ mọi generator seeded giữa nhiều threads

Một `java.util.Random` instance có hợp đồng thread-safe nhưng có thể contention; một `SplittableRandom` instance **không** thread-safe cho shared concurrent use. Nếu muốn replay theo task ID, tạo generator riêng cho từng task với seed mapping được thiết kế và giữ thứ tự gọi.

### 19.2. Test range khác test distribution

- **Range test:** mọi giá trị đều thuộc [origin,bound), không đòi trúng từng giá trị.
- **Boundary test:** các cận không hợp lệ bị từ chối; cận cực đại không overflow.
- **Distribution test:** kiểm tra đặc tính thống kê trên một lượng mẫu đủ lớn, với ngưỡng sai số/hypothesis test phù hợp.
- **Reproducibility test:** same seed + same generator algorithm + same call sequence → expected output.
- **Concurrency test:** nhiều workers hoàn thành, không có race ở aggregation.

Không dùng một test gồm 10 hoặc 20 samples để khẳng định “mỗi giá trị phải xuất hiện ít nhất một lần” hoặc phân phối hoàn toàn đều.

## 20. Test boundary values một cách có hệ thống

Một bảng test có giá trị học tập:

| Input | Kỳ vọng |
| --- | --- |
| `nextInt(1)` | Luôn 0 |
| `nextInt(1,2)` | Luôn 1 |
| `nextInt(-1,1)` | Chỉ -1 hoặc 0 |
| `nextInt(Integer.MIN_VALUE,Integer.MAX_VALUE)` | Hợp lệ; kết quả < MAX |
| `nextInt(0)` | IllegalArgumentException |
| `nextInt(3,3)` | IllegalArgumentException |
| `nextInt(4,-4)` | IllegalArgumentException |
| `nextLong(0L,1L)` | Luôn 0L |
| `nextLong(Long.MIN_VALUE,Long.MAX_VALUE)` | Hợp lệ; không bao gồm MAX |
| `nextDouble(0.0,1.0)` | 0 <= r < 1 |
| `nextDouble(-1.0,1.0)` | -1 <= r < 1 |
| `nextDouble(Double.NaN,1.0)` | IllegalArgumentException |
| `nextDouble(0.0,Double.POSITIVE_INFINITY)` | IllegalArgumentException |
| `nextFloat(-2.0f,3.0f)` | -2 <= r < 3 |
| Inclusive helper `nextInclusive(42,42)` | Luôn 42 |
| Inclusive helper `nextInclusive(MAX-2,MAX)` | Không overflow, kết quả trong range |
| Inclusive helper `nextInclusive(9,8)` | IllegalArgumentException |

### 20.1. Không ép test trúng endpoint

Một generator có thể hợp lệ mà lần thử chưa lấy đúng origin hoặc giá trị sát bound. Nếu cần kiểm thử việc endpoint **có thể** xuất hiện, phải thiết kế test double/sampling test có chiến lược rõ, không bắt chương trình bốc ngẫu nhiên liên tục cho tới khi trúng rồi xem số lần chờ là tiêu chuẩn.

### 20.2. Khoảng rất nhỏ dễ kiểm chứng

- [5,6) chỉ trả 5.
- [-1,1) chỉ trả -1 hoặc 0.
- [0.0,1.0) là range floating-point chuẩn, không đòi mỗi giá trị xuất hiện.
- [7,7) là khoảng rỗng, không có giá trị hợp lệ: API phải báo lỗi.

### 20.3. Khoảng nguyên lớn vẫn hợp lệ

Java có thể tạo số trong [Integer.MIN_VALUE,Integer.MAX_VALUE) bằng overload hai cận; đừng tự trừ origin khỏi bound bằng int rồi báo “không thể dùng”. Bản thân **hợp đồng overload** khác với công thức thủ công có thể overflow.

## 21. Hiệu năng: đo sau khi code đúng

`ThreadLocalRandom` thường là lựa chọn tốt khi nhiều threads sinh số non-security. Nhưng performance có nhiều yếu tố:

- Số lượng lần gọi RNG trên mỗi task.
- Số workers đang chạy đồng thời và CPU cores.
- Shared `Random` có contention thực tế hay không.
- Chi phí cập nhật cấu trúc dữ liệu sau khi tạo số.
- Việc đồng bộ result aggregation.
- JVM JIT, GC, phần cứng và tải hệ thống.
- Sự khác nhau giữa bounded integer, long và floating-point generation.

### 21.1. Benchmark công bằng

So các biến thể với cùng số threads, cùng kiểu nextX, cùng khoảng và cùng cách tiêu thụ kết quả:

1. Shared `Random` instance.
2. `ThreadLocalRandom.current()` trong mỗi worker.
3. Một `Random` riêng cho mỗi worker.
4. Nếu phù hợp: một `SplittableRandom` riêng cho từng task.

Dùng JMH, warmup, nhiều iterations/forks và đo throughput/tail latency. Không in stdout trong hot loop, không tạo `new Random()` cho mỗi sample ở một variant rồi so với các variant tái sử dụng instance.

### 21.2. RNG không sửa data race của dữ liệu kết quả

Dù generator an toàn, nếu workers cùng thêm vào `ArrayList` không synchronized hoặc cùng ghi `counter++`, kết quả vẫn có thể sai. Tạo số cục bộ, trả result qua Future hoặc dùng collections/atomics thích hợp. Không quy mọi lỗi concurrency cho RNG.

### 21.3. Không benchmark bằng bốn ví dụ ở trên

Các chương trình trên nhằm **kiểm tra hợp đồng range và concurrency**, không phải thử tốc độ. Không suy từ việc các demos hoàn tất nhanh rằng ThreadLocalRandom có một mức speedup cố định. Khi viết báo cáo hiệu năng, phải công bố hardware, JVM version, inputs và phương pháp đo.

## 22. Những lỗi phổ biến và cách sửa

**1. “`nextInt(1,6)` sinh xúc xắc 1..6.”** Sai: chỉ 1..5. Dùng [1,7).

**2. “Cận trên của `nextInt(origin,bound)` được bao gồm.”** Sai; bound exclusive.

**3. “`nextInt(0)` trả số 0.”** Sai; bound phải dương.

**4. “Khoảng [5,5) trả 5.”** Sai; khoảng rỗng, IllegalArgumentException.

**5. “Không thể sinh số âm bằng ThreadLocalRandom.”** Sai; dùng origin âm.

**6. “Có thể dùng `nextInt(-10,10)` để sinh -10..10 bao gồm.”** Sai; không thể trả 10.

**7. “Độ rộng khoảng luôn tính được bằng int.”** Sai; bound-origin có thể overflow.

**8. “`Math.abs(nextInt())` luôn không âm.”** Sai với Integer.MIN_VALUE.

**9. “Lấy modulo kết quả random luôn đều và đúng.”** Không; có thể âm hoặc lệch phân phối.

**10. “Inclusive max thì cứ max+1 với int.”** Sai khi max==Integer.MAX_VALUE.

**11. “Helper inclusive int dùng long là không cần vì int đủ lớn.”** Không; dùng long giải quyết an toàn cận trên MAX.

**12. “Helper inclusive long cũng chỉ cần max+1L.”** Sai khi max==Long.MAX_VALUE.

**13. “`nextLong(100L)` cũng giống `nextInt(100)` về kiểu trả về.”** Không; một cái long, một cái int.

**14. “nextDouble(0.0,1.0) có thể trả 1.0.”** Không, bound exclusive.

**15. “Origin âm làm nextFloat/nextDouble lỗi.”** Sai; miễn cận hữu hạn và origin < bound.

**16. “NaN là cận hợp lệ vì là double.”** Sai; phải dùng cận finite.

**17. “Infinity là cận hợp lệ vì lớn hơn mọi số.”** Sai với overload bounded float/double.

**18. “Chỉ cần p<0 || p>1 là validate được NaN.”** Sai; NaN lọt qua hai điều kiện này.

**19. “Probability 0.25 chắc đúng 25 lần chọn trên 100.”** Không; đó là xác suất, không quota.

**20. “Chọn index ngẫu nhiên không cần kiểm tra list rỗng.”** Sai; size=0 làm bound invalid.

**21. “Concurrent list được chỉnh sửa cùng lúc mà size/get vẫn an toàn.”** Không nhất thiết; cần ownership/snapshot/synchronization.

**22. “ThreadLocalRandom là bộ sinh mật mã.”** Sai; dùng SecureRandom cho secrets.

**23. “Random number trong khoảng rộng luôn unique.”** Sai; collision bình thường.

**24. “current() tạo luồng mới.”** Sai; lấy generator trong current thread.

**25. “Lấy một instance ThreadLocalRandom trong main rồi share cho pool là cách dùng chuẩn.”** Sai; lấy current trong mỗi worker.

**26. “ThreadLocalRandom.setSeed cho test cố định.”** Sai; UnsupportedOperationException.

**27. “Một task luôn nhận cùng random sequence bất kể worker nào chạy.”** Không; state theo thread.

**28. “Có thể in random value vào stdout mẫu rồi mong người học thấy đúng số.”** Không, trừ khi dùng seeded generator được kiểm soát.

**29. “Range test 10.000 mẫu chứng minh uniform distribution tuyệt đối.”** Sai; chỉ kiểm tra những sample đã quan sát.

**30. “Nhiều threads dùng ThreadLocalRandom thì mọi biến khác cũng thread-safe.”** Sai; data races ở shared mutable state vẫn xảy ra.

**31. “Random stream không giới hạn gọi toArray là an toàn.”** Không; phải giới hạn số lượng.

**32. “Một RNG nhanh chắc chắn làm cả dịch vụ nhanh hơn.”** Không; phải benchmark đúng bottleneck.

**33. “Bảo mật có thể cải thiện chỉ bằng tăng bound lên rất lớn.”** Không đủ; cần CSPRNG và protocol phù hợp.

**34. “Floating-point có vô hạn các giá trị biểu diễn trong [0,1).”** Sai; IEEE-754 có tập giá trị hữu hạn.

**35. “Một giá trị origin không xuất hiện sau 50 lần chứng minh API bỏ cận dưới.”** Không; origin được phép xuất hiện, không bắt buộc trong số mẫu hữu hạn.

## 23. Checklist thực hành

- [ ] Đã xác định kiểu kết quả cần là int, long, float hay double?
- [ ] Đã xác định khoảng nghiệp vụ là [min,max) hay [min,max]?
- [ ] Biết cận dưới được bao gồm, cận trên bị loại trừ với nextX(origin,bound)?
- [ ] Nếu chỉ dùng bound, đã bảo đảm bound > 0?
- [ ] Nếu dùng origin,bound, đã bảo đảm origin < bound?
- [ ] Có xử lý danh sách rỗng trước `nextInt(list.size())`?
- [ ] Có tránh race nếu list bị sửa đồng thời giữa size và get?
- [ ] Nếu max inclusive, đã chọn bound mới đúng và không overflow?
- [ ] Nếu cần inclusive int ở MAX_VALUE, có dùng long intermediate?
- [ ] Không áp dụng công thức max+1L vô điều kiện cho long MAX_VALUE?
- [ ] Không tính bound-origin bằng int có khả năng overflow?
- [ ] Không dùng Math.abs(nextInt())%bound?
- [ ] Với float/double, hai cận đều hữu hạn và đúng thứ tự?
- [ ] Với xác suất, đã từ chối NaN/Infinity và p ngoài [0,1]?
- [ ] Có hiểu ngẫu nhiên xác suất không bảo đảm quota cứng?
- [ ] Với jitter, có giới hạn min/max, deadline và retry policy?
- [ ] Không dùng số ngẫu nhiên thuần để bảo đảm uniqueness?
- [ ] Không dùng ThreadLocalRandom cho token/nonce/secret?
- [ ] Nếu cần bảo mật, có dùng SecureRandom theo threat model?
- [ ] Trong đa luồng, gọi current() trong worker thực thi?
- [ ] Không cache current() ở field singleton dùng qua threads?
- [ ] Không dùng ThreadLocalRandom.setSeed cho deterministic unit tests?
- [ ] Nếu cần replay, dùng generator seeded theo task và injection?
- [ ] Không share SplittableRandom instance đang mutable qua nhiều threads?
- [ ] Các shared counters/results có synchronization/ownership đúng?
- [ ] Dùng Futures/await thay vì sleep để đợi workers hoàn thành?
- [ ] Tests assert range/invariants và ngoại lệ thay vì số random cố định?
- [ ] Có boundary tests cho 0, negative, equal, MAX_VALUE và NaN?
- [ ] Streams ngẫu nhiên không giới hạn có limit trước terminal operation?
- [ ] Không đánh đồng kiểm thử range với kiểm thử thống kê phân phối?
- [ ] Benchmark có workload thật trước khi khẳng định speedup?
- [ ] Đã dùng Java SE 17+ APIs đang được hỗ trợ, không sao chép legacy patterns?

## 24. Câu hỏi tự kiểm tra

**1.** API nào sinh số int từ 0 tới 9? — `nextInt(10)`.

**2.** API nào sinh xúc xắc 1 tới 6? — `nextInt(1,7)`.

**3.** `nextInt(1,7)` có thể trả 7 không? — Không.

**4.** `nextInt(5,5)` có kết quả nào không? — Không; ném IllegalArgumentException.

**5.** `nextInt(-3,3)` có thể trả gì? — -3, -2, -1, 0, 1 hoặc 2.

**6.** Có thể dùng origin âm với nextLong không? — Có, nếu origin < bound.

**7.** Muốn tạo long lớn hơn Integer.MAX_VALUE nên dùng gì? — nextLong với cận kiểu long.

**8.** `nextDouble()` trả trong khoảng nào? — [0.0,1.0).

**9.** Cận trên của nextDouble(origin,bound) được bao gồm không? — Không.

**10.** nextFloat(origin,bound) có trong Java 17 không? — Có.

**11.** Float/Double cận NaN có hợp lệ không? — Không.

**12.** Dùng `nextInt(0)` sẽ ra sao? — IllegalArgumentException.

**13.** Vì sao Math.abs(nextInt())%n nguy hiểm? — MIN_VALUE và modulo bias.

**14.** Vì sao không viết width=bound-origin trên int khi range rất rộng? — Có thể overflow.

**15.** Muốn sinh int trong [a,b] inclusive với b=MAX_VALUE có cách nào an toàn? — Nâng cận lên long rồi nextLong(a,b+1L), cast khi hợp lệ.

**16.** Có thể áp dụng cùng phép cộng b+1L cho b=Long.MAX_VALUE không? — Không, overflow.

**17.** nextInt(1,2) có thể trả gì? — Luôn 1.

**18.** Chọn index cho List size N nên dùng gì? — nextInt(N) nếu N>0.

**19.** List rỗng cần làm gì? — Báo lỗi/không chọn phần tử.

**20.** Dùng nextDouble()<0.2 có bảo đảm đúng 20 trên 100 samples không? — Không.

**21.** Nên validate probability thế nào? — Hữu hạn và 0<=p<=1.

**22.** Jitter [150,350] ms dùng nextLong thế nào? — nextLong(150L,351L).

**23.** ThreadLocalRandom nên được lấy ở đâu trong pool? — Trong worker thread đang thực thi.

**24.** ThreadLocalRandom.setSeed có hoạt động không? — Không, ném UnsupportedOperationException.

**25.** Muốn test cùng seed sinh đúng chuỗi cố định nên dùng gì? — Random/RandomGenerator có seed, với call order cố định.

**26.** Có thể dùng ThreadLocalRandom để sinh session secret không? — Không, dùng SecureRandom.

**27.** Hai workers có thể cùng sinh số 5 không? — Có.

**28.** Trong chương trình đa luồng, nên kiểm thử gì? — Số tasks/draws, tính hợp lệ từng range và hoàn thành đúng.

**29.** Kiểm thử 50.000 samples chứng minh distribution hoàn toàn đều không? — Không.

**30.** Có thể dùng `ints(10,1,7)` để lấy 10 mẫu không? — Có.

**31.** Có thể gọi toArray trên stream không giới hạn mà thiếu limit không? — Không nên.

**32.** Khi nào nên dùng nextInt trực tiếp thay helper inclusive? — Khi hợp đồng cho phép [origin,bound).

**33.** nextLong(Long.MIN_VALUE,Long.MAX_VALUE) có hợp lệ không? — Có; MAX là exclusive.

**34.** Vì sao không in giá trị random làm expected stdout cố định? — Nó biến đổi theo seed/sequence.

**35.** Chọn khoảng đúng đã đủ để bảo đảm tính an toàn của ứng dụng chưa? — Chưa; còn concurrency, error handling, dữ liệu và security requirements.

## 25. Tài liệu chính thức Java SE 17

- [ThreadLocalRandom — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): các overload `nextInt`, `nextLong`, `nextFloat`, `nextDouble`, cận bao gồm/loại trừ, `current()`, `setSeed()`.
- [RandomGenerator — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): hợp đồng generator chung và bounded APIs.
- [Random — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html): seeded deterministic tests, sequence và các overload.
- [SplittableRandom — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html): cấp generator riêng cho tác vụ cần tái lập.
- [SecureRandom — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): RNG dùng cho mục đích bảo mật.
- [ExecutorService — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): quản lý worker threads, shutdown và Futures.
- [Future — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): completion, timeout, exception propagation.
- [Java Streams — IntStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html): giới hạn và xử lý streams số nguyên.

**Ghi nhớ:** Với `ThreadLocalRandom.current()`, hãy chọn overload theo **kiểu dữ liệu** và hiểu **[origin,bound)**. Sinh xúc xắc 1–6 bằng `nextInt(1,7)`, index cho N phần tử bằng `nextInt(N)` khi N>0, giá trị thực bằng `nextFloat/nextDouble` với cận hữu hạn. Nếu nghiệp vụ đòi **cả min và max đều bao gồm**, phải chuyển cận cẩn thận; với mọi khoảng int, dùng trung gian long để tránh overflow ở `Integer.MAX_VALUE`. Không dùng modulo/Math.abs thủ công, không kỳ vọng một mẫu hữu hạn chứa mọi endpoint, không dùng ThreadLocalRandom cho secrets, và luôn test **range properties** thay vì chốt một giá trị random cố định.