# Math.abs với MIN_VALUE và lựa chọn absExact trong Java

`Math.abs(x)` có vẻ là cách đơn giản để lấy trị tuyệt đối, nhưng với **`Integer.MIN_VALUE`** và **`Long.MIN_VALUE`** nó không thể trả về số dương tương ứng trong cùng kiểu số nguyên. Điều bất ngờ là **`Math.abs` không ném ngoại lệ**: kết quả vẫn là chính `MIN_VALUE`, tức một số âm.

```java
System.out.println(Math.abs(Integer.MIN_VALUE)); // -2147483648
System.out.println(Math.abs(Long.MIN_VALUE));    // -9223372036854775808
```

Nếu một thuật toán dựa vào giả định “`Math.abs` luôn không âm”, lỗi có thể xuất hiện trong chỉ số mảng, kiểm tra khoảng cách, sắp xếp theo độ lớn, chọn bucket của bảng băm hoặc kiểm soát giới hạn. **`Math.absExact`** (có trong Java 17+) giúp phát hiện riêng trường hợp trị tuyệt đối không biểu diễn được bằng kiểu số nguyên đầu vào: nó **ném `ArithmeticException`** thay vì trả giá trị âm sai kỳ vọng.

Bài này thuộc mục **Tràn và kiểm tra biên** trong **Java core – numbers**, tập trung vào cơ chế hai's complement, sự khác nhau giữa `abs` và `absExact`, lựa chọn xử lý thích hợp và những bẫy khi làm phép toán trước khi lấy trị tuyệt đối.

## 1. Vì sao MIN_VALUE không có trị tuyệt đối dương trong cùng kiểu?

Các kiểu số nguyên có dấu Java sử dụng biểu diễn **bù hai** (*two's complement*) với độ rộng cố định. Miền giá trị bất đối xứng quanh 0:

| Kiểu | Giá trị nhỏ nhất | Giá trị lớn nhất | Trị tuyệt đối toán học của MIN_VALUE |
| --- | ---: | ---: | ---: |
| `int` 32 bit | `-2_147_483_648` | `2_147_483_647` | `2_147_483_648` |
| `long` 64 bit | `-9_223_372_036_854_775_808` | `9_223_372_036_854_775_807` | `9_223_372_036_854_775_808` |

Với số nguyên có dấu `n` bit, miền là từ `-2^(n-1)` đến `2^(n-1)-1`. Vì vậy trị tuyệt đối của `MIN_VALUE` bằng `2^(n-1)`, **vượt `MAX_VALUE` đúng một đơn vị**.

Ví dụ bit 32:

```text
Integer.MIN_VALUE = -2147483648
Bit của int       = 10000000 00000000 00000000 00000000
Đổi dấu toán học  = +2147483648 (vượt Integer.MAX_VALUE)
Kết quả 32 bit    = 10000000 00000000 00000000 00000000
Diễn giải int     = -2147483648
```

Các phép cộng, trừ và đổi dấu số nguyên Java theo kiểu nguyên thủy có hành vi được định nghĩa trên độ rộng bit cố định. Phép đổi dấu `-Integer.MIN_VALUE` cũng trả lại `Integer.MIN_VALUE`, không ném lỗi. `Math.abs(int)` dùng cùng miền giá trị và cũng **không tự động kiểm tra tràn**.

### Giá trị “gần MIN_VALUE” vẫn xử lý bình thường

```java
int a = Integer.MIN_VALUE + 1;
System.out.println(Math.abs(a)); // 2147483647
```

Chỉ riêng giá trị `Integer.MIN_VALUE` mới không có giá trị đối dương biểu diễn được trong `int`; tương tự, chỉ `Long.MIN_VALUE` là trường hợp đó đối với `long`. Các giá trị nguyên có dấu khác, kể cả `-MAX_VALUE`, đều có trị tuyệt đối nằm trong miền kiểu của chúng.

## 2. Math.abs thực sự cam kết điều gì?

Trong Java, lớp `java.lang.Math` có các overload `abs(int)`, `abs(long)`, `abs(float)`, `abs(double)`. Với **`int` và `long`**, kết quả là độ lớn không âm của đối số trong mọi trường hợp **ngoại trừ giá trị MIN_VALUE của chính kiểu đó**, khi phương thức trả lại MIN_VALUE.

```java
int normal = Math.abs(-42);                  // 42
int zero = Math.abs(0);                      // 0
int edge = Math.abs(Integer.MIN_VALUE);      // Integer.MIN_VALUE
long longEdge = Math.abs(Long.MIN_VALUE);    // Long.MIN_VALUE
```

Các dòng này là mảnh mã Java đặt trong một phương thức. Chúng biên dịch được và không phát sinh exception do giá trị MIN_VALUE.

Điều này có hệ quả rất quan trọng: **kết quả kiểu `int` từ `Math.abs(int)` không thể được xem là bất biến “`result >= 0`”** nếu đầu vào chưa loại trừ `Integer.MIN_VALUE`. Tương tự với `long`.

Một kiểm tra như sau có thể bắt lỗi sau khi nó đã xuất hiện, nhưng không cung cấp một kết quả đúng:

```java
int magnitude = Math.abs(value);
if (magnitude < 0) {
    throw new ArithmeticException("Magnitude does not fit in int");
}
```

Thay vì tự viết lại kiểm tra này khi muốn exception, Java đã có **`Math.absExact(value)`**.

## 3. Math.absExact: phát hiện tràn thay vì trả MIN_VALUE

Java cung cấp hai overload **`Math.absExact(int)`** và **`Math.absExact(long)`**. Cả hai đều có trong Java 17. Chúng trả trị tuyệt đối khi kết quả biểu diễn được trong kiểu đầu vào, và **ném `ArithmeticException`** nếu đầu vào đúng bằng `MIN_VALUE` của kiểu đó.

```java
int a = Math.absExact(-42);       // 42
long b = Math.absExact(-42L);     // 42L

// Math.absExact(Integer.MIN_VALUE) → ArithmeticException
// Math.absExact(Long.MIN_VALUE)    → ArithmeticException
```

So sánh các lựa chọn:

| Đầu vào | `Math.abs` | `Math.absExact` |
| --- | --- | --- |
| `-42` (`int`) | `42` | `42` |
| `0` (`int`) | `0` | `0` |
| `Integer.MAX_VALUE` | `2147483647` | `2147483647` |
| `Integer.MIN_VALUE + 1` | `2147483647` | `2147483647` |
| `Integer.MIN_VALUE` | `-2147483648` | Ném `ArithmeticException` |
| `Long.MIN_VALUE` | `-9223372036854775808` | Ném `ArithmeticException` |

Dùng `absExact` khi hợp đồng phép tính cần **trả một số nguyên không âm trong cùng kiểu hoặc báo lỗi**. Ví dụ: một API yêu cầu trả `int` là độ lớn của độ lệch, và `Integer.MIN_VALUE` được coi là đầu vào không hợp lệ.

Điểm cần hiểu: `Math.absExact` **không trả được `2147483648` dưới dạng `int`**. Nó báo rằng kết quả không biểu diễn được. Nếu bài toán thực sự cần lưu trị tuyệt đối đó, hãy chọn kiểu đủ rộng trước khi tính.

### Không có Math.absExact(float) hoặc Math.absExact(double)

`Math.absExact` dành cho kiểu nguyên `int` và `long`, không phải phương thức có overload cho `float`/`double`. Đối với số dấu phẩy động, các quy tắc như `NaN`, vô cực, `+0.0`/`-0.0` khác với overflow nguyên. Không dùng một phương thức nguyên để suy diễn semantics cho floating point.

## 4. Khi cần trị tuyệt đối thật sự của Integer.MIN_VALUE: nâng kiểu trước

Giá trị `2147483648` vượt `int` nhưng **nằm trong `long`**. Vì vậy, nếu nguồn là `int` mà đầu ra được phép là `long`, chuyển sang `long` **trước khi gọi `Math.abs`**:

```java
int value = Integer.MIN_VALUE;

long correct = Math.abs((long) value);
// correct == 2147483648L
```

Không hoán đổi thứ tự:

```java
int value = Integer.MIN_VALUE;

long tooLate = (long) Math.abs(value);
// tooLate == -2147483648L: Math.abs(int) đã tính sai kỳ vọng trước khi cast.
```

Hai cách này khác nhau ở **overload được chọn**:

- `Math.abs((long) value)`: đối số là `long`, gọi `Math.abs(long)`. `-2147483648L` có trị tuyệt đối vừa trong `long`.
- `(long) Math.abs(value)`: đối số ban đầu là `int`, gọi `Math.abs(int)`; việc mở rộng lên `long` sau đó chỉ giữ nguyên giá trị âm đã nhận.

Cùng một nguyên tắc áp dụng cho đổi dấu:

```java
long correct = -(long) Integer.MIN_VALUE; // 2147483648L
long tooLate = (long) (-Integer.MIN_VALUE); // -2147483648L
```

Việc chọn overload và thứ tự chuyển kiểu quyết định tính đúng đắn, không phải chỉ nhìn kiểu của biến nhận kết quả.

### Nên chọn Math.abs hay Math.absExact sau khi nâng kiểu?

Nếu mục tiêu của một phép xử lý `int` là **trả `long` đúng tuyệt đối**, `Math.abs((long) value)` đã đủ vì mọi giá trị `int` và trị tuyệt đối của chúng đều vừa `long`. `Math.absExact((long) value)` cũng đúng, nhưng trường hợp tràn của overload `long` không thể xảy ra khi đầu vào ban đầu chắc chắn là `int`.

Nếu mục tiêu **trả `int` và fail fast khi không vừa**, dùng `Math.absExact(value)`. Chọn theo hợp đồng trả về và cách ứng dụng xử lý dữ liệu vượt giới hạn.

## 5. Với Long.MIN_VALUE, long rộng hơn không còn đủ

Trị tuyệt đối của `Long.MIN_VALUE` là `9223372036854775808`, lớn hơn `Long.MAX_VALUE` đúng một đơn vị. Không có kiểu số nguyên nguyên thủy Java rộng hơn `long`.

Có ba hướng thiết kế tùy yêu cầu:

1. **Báo lỗi tràn:** `Math.absExact(longValue)` ném `ArithmeticException` khi nhận `Long.MIN_VALUE`.
2. **Biểu diễn độ lớn chính xác:** dùng `BigInteger` và **chuyển trước khi lấy trị tuyệt đối**.
3. **Xử lý dạng unsigned theo hợp đồng bit cụ thể:** có thể cần thao tác không dấu riêng, nhưng không coi kiểu `long` có dấu thành một số dương lớn hơn `Long.MAX_VALUE`.

Ví dụ đúng với `BigInteger`:

```java
import java.math.BigInteger;

// Đặt trong một phương thức Java:
long value = Long.MIN_VALUE;

BigInteger magnitude = BigInteger.valueOf(value).abs();
// 9223372036854775808
```

`BigInteger.valueOf(value)` nhận chính giá trị `long` có dấu rồi tạo đối tượng số nguyên; `BigInteger.abs()` có thể tạo ra trị tuyệt đối vượt 64 bit. Ngược lại, phương án sau là sai về thứ tự:

```java
long value = Long.MIN_VALUE;
BigInteger wrong = BigInteger.valueOf(Math.abs(value));
// wrong vẫn là -9223372036854775808.
```

Đưa giá trị đã xử lý sai vào một kiểu lớn hơn không khôi phục được ý định toán học ban đầu.

## 6. Bẫy nguy hiểm hơn: biểu thức đã tràn trước khi gọi absExact

`Math.absExact` chỉ kiểm tra **trị tuyệt đối của giá trị nó thực sự nhận được**. Phương thức không thể biết phép cộng/trừ/nhân tạo ra đối số đã bị tràn trước đó.

Xét bài toán tính khoảng cách tuyệt đối giữa hai `int`:

```java
int a = Integer.MAX_VALUE;
int b = -Integer.MAX_VALUE;

int wrong = Math.absExact(a - b); // Trả 2, KHÔNG ném ngoại lệ!
```

Phân tích:

```text
a                     =  2147483647
b                     = -2147483647
a - b về mặt toán học =  4294967294
a - b trong int       = -2            (tràn int)
Math.absExact(-2)     =  2            (không có overflow ở bước abs)
```

Kết quả `2` có vẻ hợp lệ và không có exception, nhưng khoảng cách toán học đúng phải là `4294967294`. **`absExact` không phải công cụ tự phát hiện mọi overflow xảy ra trước lời gọi**.

Vì khoảng cách giữa bất kỳ hai `int` nào đều nằm trong miền `long`, cách đúng là **nâng kiểu trước khi trừ**:

```java
long distance = Math.abs((long) a - b);
// distance == 4294967294L
```

Có thể dùng `Math.absExact((long) a - b)` khi muốn thể hiện chính sách checked arithmetic, nhưng ở đầu vào đều là `int`, hiệu tuyệt đối vẫn nằm trong giới hạn `long`.

### Với hai long bất kỳ, BigInteger phù hợp hơn

Hiệu toán học của `Long.MAX_VALUE` và `Long.MIN_VALUE` là `18446744073709551615`, vượt `long`. Cast hai toán hạng `long` thành `long` một lần nữa không giúp ích:

```java
BigInteger distance = BigInteger.valueOf(Long.MAX_VALUE)
        .subtract(BigInteger.valueOf(Long.MIN_VALUE))
        .abs();
// 18446744073709551615
```

Nếu đặc tả yêu cầu trả `long`, phải kiểm tra miền dữ liệu trước hoặc dùng phép trừ checked như `Math.subtractExact` rồi `Math.absExact`, sẵn sàng báo lỗi khi không biểu diễn được. Nếu đặc tả yêu cầu trả khoảng cách **toán học chính xác cho mọi cặp long**, `BigInteger` là hướng đúng.

## 7. Ví dụ thực tế: lấy trị tuyệt đối của hash rồi lấy chỉ số

Một mẫu code dễ gặp là:

```java
int hash = key.hashCode();
int index = Math.abs(hash) % capacity;
```

Nếu `hash == Integer.MIN_VALUE`, `Math.abs(hash)` vẫn âm. Với `capacity = 10`, kết quả `index` là **`-8`**, không nằm trong miền chỉ số `0..9`.

```java
int hash = Integer.MIN_VALUE;
int capacity = 10;

int brokenIndex = Math.abs(hash) % capacity; // -8
```

Có thể sửa bằng cách nâng kiểu trước khi `abs`, nhưng khi mục đích thực sự chỉ là **ánh xạ số nguyên, kể cả âm, vào chu kỳ dương**, `Math.floorMod(hash, capacity)` thể hiện yêu cầu trực tiếp hơn:

```java
int hash = Integer.MIN_VALUE;
int capacity = 10;

int index = Math.floorMod(hash, capacity); // 2
```

Khi `capacity > 0`, `Math.floorMod(hash, capacity)` nằm trong `0..capacity-1` đối với mọi `int hash`. Cần kiểm tra `capacity > 0`; nếu bằng 0 sẽ không có chỉ số hợp lệ. Kết quả `2` của `floorMod` **không bắt buộc giống** `Math.abs((long) hash) % capacity` (giá trị sau là 8). Chúng thể hiện **hai chính sách ánh xạ khác nhau**; chọn chính sách theo thuật toán, tính ổn định phân phối dữ liệu và hợp đồng hiện có.

### Vì sao không dùng absExact để “cứu” công thức hash?

```java
int index = Math.absExact(hash) % capacity;
```

Công thức này phát hiện `Integer.MIN_VALUE` rồi ném exception. Điều đó có thể phù hợp nếu quy tắc của ứng dụng muốn coi hash đặc biệt là lỗi. Nhưng thông thường hash có thể là **bất kỳ int nào**, và việc có một giá trị hash hợp lệ khiến ánh xạ index thất bại không phải điều mong muốn. Trong bài toán index chu kỳ dương, `floorMod` phù hợp hơn.

Một lựa chọn khác khi thuật toán làm việc trên **bit không dấu** là mask bit dấu với `hash & Integer.MAX_VALUE`; cách này cũng tạo giá trị không âm nhưng **chính sách ánh xạ khác** với `floorMod`. Không tự ý thay đổi hàm ánh xạ trong cấu trúc dữ liệu đã có vì có thể ảnh hưởng bucket hoặc tính tương thích với dữ liệu lưu trước đó.

## 8. Ví dụ thực tế: độ lệch, khoảng cách và kiểm tra giới hạn

Giả sử một dịch vụ cần xác định khoảng cách số lượng giữa hai bộ đếm:

```java
static long absoluteDifference(int current, int previous) {
    return Math.abs((long) current - previous);
}
```

Phương thức trên an toàn cho mọi cặp `int`. Nó cho kết quả `long` từ 0 đến `4294967295`, không làm mất giá trị do tràn `int`. Tuy vậy, kiểm tra một điều kiện nghiệp vụ như “chênh lệch không vượt 1000” còn cần so sánh với ngưỡng và xử lý input hợp lệ.

Nếu phương thức bắt buộc trả `int`, phải quyết định rõ:

```java
static int absoluteDifferenceExact(int current, int previous) {
    long distance = Math.abs((long) current - previous);
    return Math.toIntExact(distance);
}
```

`Math.toIntExact` ném `ArithmeticException` khi khoảng cách vượt `Integer.MAX_VALUE`; nó báo lỗi **ở biên trả về**, không để cast làm mất thông tin.

Với `long` là kiểu đầu vào và khoảng cách cần tuyệt đối đúng, dùng `BigInteger` như phần trước.

### Trị tuyệt đối trong phép tính và biểu thức trung gian

Ba lỗi thường gặp có cấu trúc giống nhau:

```java
// 1. Lấy abs quá muộn sau phép trừ int đã tràn:
long wrongDistance = Math.abs(a - b);

// 2. Cast quá muộn, sau khi Math.abs(int) đã trả MIN_VALUE:
long wrongMagnitude = (long) Math.abs(Integer.MIN_VALUE);

// 3. Chuyển sang BigInteger sau khi Math.abs(long) đã trả MIN_VALUE:
BigInteger wrongBigMagnitude =
        BigInteger.valueOf(Math.abs(Long.MIN_VALUE));
```

Phải đặt **kiểu đủ rộng hoặc phép kiểm tra đúng tại thời điểm phép toán có thể tràn**. Chỉ kiểm tra kết quả cuối không thay thế được kiểm soát các bước trung gian.

## 9. Có nên dùng phép if/ternary thay vì Math.absExact?

Một triển khai tự viết dễ thấy:

```java
static int naiveAbs(int value) {
    return value < 0 ? -value : value;
}
```

Nó **không giải quyết** ca `Integer.MIN_VALUE`. Nhánh `-value` cũng quay lại số âm nhỏ nhất mà không ném exception. Muốn giữ `int` và phát hiện overflow, `Math.absExact` làm rõ ý định hơn một nhánh đặc biệt tự viết.

Nếu phải tự tạo thông báo lỗi nghiệp vụ khác `ArithmeticException`, có thể kiểm tra đầu vào tường minh:

```java
static int checkedMagnitude(int value) {
    if (value == Integer.MIN_VALUE) {
        throw new IllegalArgumentException("Magnitude exceeds int range");
    }
    return Math.abs(value);
}
```

Đây là lựa chọn thiết kế **khác hợp đồng** với `Math.absExact`: loại exception và cách mô tả lỗi phụ thuộc API. Không cần viết lại nó nếu yêu cầu chỉ là overflow gây `ArithmeticException`.

Nếu bài toán chấp nhận trả kết quả trong `long`, mở rộng trước khi lấy abs thường gọn và giữ được cả trường hợp biên mà không phải báo lỗi.

## 10. Chương trình Java 17+ chạy độc lập

Lưu đoạn sau thành **`AbsMinValueDemo.java`**. Chương trình minh họa `Math.abs` trả lại MIN_VALUE, `Math.absExact` báo lỗi, phép nâng kiểu đúng thời điểm, `BigInteger`, bẫy hiệu đã tràn và cách tạo chỉ số modulo không âm.

```java
import java.math.BigInteger;

public class AbsMinValueDemo {
    public static void main(String[] args) {
        int minInt = Integer.MIN_VALUE;
        long minLong = Long.MIN_VALUE;

        System.out.println("abs-int-min=" + Math.abs(minInt));
        System.out.println("abs-long-min=" + Math.abs(minLong));
        System.out.println("abs-int-near-min=" +
                Math.absExact(minInt + 1));

        try {
            Math.absExact(minInt);
        } catch (ArithmeticException ex) {
            System.out.println("abs-exact-int=overflow");
        }

        try {
            Math.absExact(minLong);
        } catch (ArithmeticException ex) {
            System.out.println("abs-exact-long=overflow");
        }

        System.out.println("widen-before-abs=" +
                Math.abs((long) minInt));
        System.out.println("widen-after-abs=" +
                (long) Math.abs(minInt));
        System.out.println("big-long-magnitude=" +
                BigInteger.valueOf(minLong).abs());

        int a = Integer.MAX_VALUE;
        int b = -Integer.MAX_VALUE;
        System.out.println("incorrect-abs-diff=" +
                Math.absExact(a - b));
        System.out.println("correct-abs-diff=" +
                Math.abs((long) a - b));

        System.out.println("naive-hash-index=" +
                (Math.abs(minInt) % 10));
        System.out.println("floor-mod-index=" +
                Math.floorMod(minInt, 10));

        BigInteger bigDifference = BigInteger.valueOf(Long.MAX_VALUE)
                .subtract(BigInteger.valueOf(Long.MIN_VALUE))
                .abs();
        System.out.println("big-long-distance=" + bigDifference);
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac AbsMinValueDemo.java
java AbsMinValueDemo
```

Kết quả stdout:

```text
abs-int-min=-2147483648
abs-long-min=-9223372036854775808
abs-int-near-min=2147483647
abs-exact-int=overflow
abs-exact-long=overflow
widen-before-abs=2147483648
widen-after-abs=-2147483648
big-long-magnitude=9223372036854775808
incorrect-abs-diff=2
correct-abs-diff=4294967294
naive-hash-index=-8
floor-mod-index=2
big-long-distance=18446744073709551615
```

**Giải thích:**

- Hai dòng `abs-*-min` cho thấy `Math.abs` không tự ném exception trên số nguyên MIN_VALUE.
- Hai dòng `abs-exact-*` chỉ xuất hiện do khối `catch` bắt exception từ `Math.absExact`.
- `widen-before-abs` giữ đúng độ lớn của `Integer.MIN_VALUE`; `widen-after-abs` không sửa được kết quả `int` đã quay vòng.
- `incorrect-abs-diff=2` đặc biệt quan trọng: `absExact` không phát hiện phép trừ đã tràn trước lời gọi. Phải mở rộng trước khi trừ.
- Chỉ số `-8` từ `Math.abs(minInt) % 10` không hợp lệ cho mảng; `Math.floorMod(minInt, 10)` trả `2`.
- Hai phép tính `BigInteger` giữ được các trị tuyệt đối vượt phạm vi `long`.

## 11. Phân biệt các lỗi dễ nhầm

| Mã hoặc quyết định | Kết quả/vấn đề | Cách dùng phù hợp |
| --- | --- | --- |
| `Math.abs(Integer.MIN_VALUE)` | Trả `Integer.MIN_VALUE`, vẫn âm | Chỉ dùng khi ca biên được xử lý hoặc miền loại trừ MIN_VALUE |
| `Math.absExact(Integer.MIN_VALUE)` | Ném `ArithmeticException` | Khi kết quả phải vừa `int` hoặc phải báo overflow |
| `Math.abs((long) Integer.MIN_VALUE)` | Trả `2147483648L` | Khi cần độ lớn chính xác và chấp nhận `long` |
| `(long) Math.abs(Integer.MIN_VALUE)` | Vẫn âm `-2147483648L` | Tránh: chuyển kiểu quá muộn |
| `Math.abs(Long.MIN_VALUE)` | Trả `Long.MIN_VALUE` | Không dùng như bảo đảm kết quả không âm |
| `Math.absExact(Long.MIN_VALUE)` | Ném `ArithmeticException` | Khi `long` là giới hạn đầu ra |
| `BigInteger.valueOf(Long.MIN_VALUE).abs()` | Trả chính xác `9223372036854775808` | Khi cần độ lớn vượt `long` |
| `Math.absExact(a - b)` với hai `int` | Biểu thức `a-b` có thể đã tràn | Mở rộng trước khi trừ: `Math.abs((long)a-b)` |
| `Math.abs(hash) % capacity` | Có thể âm nếu hash là MIN_VALUE | Với capacity dương, xét `Math.floorMod(hash, capacity)` |
| `Math.absExact(hash) % capacity` | Có thể ném lỗi trên hash hợp lệ | Chọn chính sách mapping toàn miền, không mặc định coi MIN_VALUE là lỗi |

### Một chi tiết về Java floating point

`Math.abs(float)` và `Math.abs(double)` không gặp sự bất đối xứng miền nguyên như `int`/`long`. Với floating point, `Float.MIN_VALUE` và `Double.MIN_VALUE` là **số dương nhỏ nhất khác 0** có thể biểu diễn, không phải giá trị âm lớn nhất về độ lớn. `Math.abs(Double.NaN)` vẫn là NaN, và `Math.abs(-0.0d)` trả dương 0.0.

Vì vậy, khi thấy `MIN_VALUE` trong code, phải đọc đúng **kiểu**: `Integer.MIN_VALUE`/ `Long.MIN_VALUE` là số âm cực tiểu; `Double.MIN_VALUE`/ `Float.MIN_VALUE` có ý nghĩa khác hẳn. Nếu cần kiểm tra dữ liệu đo lường, dùng `Double.isFinite`, xử lý `NaN` hoặc chính sách số thực thích hợp.

## 12. Kiểm thử và bài tập tự luyện

1. Dự đoán kết quả `Math.abs(Integer.MIN_VALUE + 1)`, `Math.abs(Integer.MIN_VALUE)` và `Math.absExact(Integer.MIN_VALUE)`. Giải thích vì sao chỉ một trường hợp không có trị tuyệt đối dương trong `int`.
2. Viết phương thức `long magnitude(int value)` trả đúng trị tuyệt đối của mọi `int`. Thử `-42`, `0`, `Integer.MAX_VALUE`, `Integer.MIN_VALUE`.
3. Viết phương thức `int magnitudeExact(int value)` dùng `Math.absExact`. Kiểm tra ngoại lệ chỉ ở `Integer.MIN_VALUE`, đồng thời xác định kiểu exception.
4. Vì sao `(long) Math.abs(Integer.MIN_VALUE)` sai còn `Math.abs((long) Integer.MIN_VALUE)` đúng? Trình bày overload được chọn tại từng bước.
5. Cho `a=Integer.MAX_VALUE`, `b=-Integer.MAX_VALUE`. Dự đoán `Math.absExact(a-b)` và `Math.abs((long)a-b)`. Trình bày chỗ xảy ra overflow.
6. Viết hàm `BigInteger magnitude(long value)` đúng với `Long.MIN_VALUE`. Giải thích vì sao không được lấy `Math.abs(value)` trước khi gọi `BigInteger.valueOf`.
7. Với `capacity=10`, tính `Math.abs(Integer.MIN_VALUE) % capacity` và `Math.floorMod(Integer.MIN_VALUE, capacity)`. Hai cách khác nhau ở chính sách nào?
8. Thiết kế API tính độ lệch giữa hai giá trị `long`, yêu cầu **chính xác với mọi cặp đầu vào**. Chọn kiểu trả về và phép toán, rồi kiểm thử `Long.MIN_VALUE` và `Long.MAX_VALUE`.
9. Viết kiểm thử chứng minh một giá trị `int` khác `Integer.MIN_VALUE` luôn có trị tuyệt đối không âm trong `int`. Cần bao phủ những nhóm giá trị biên nào?
10. Giải thích sự khác nhau về ý nghĩa giữa `Integer.MIN_VALUE` và `Double.MIN_VALUE`. Tại sao nhầm hai constant này có thể dẫn tới kiểm tra biên sai?

## 13. Checklist chọn cách lấy trị tuyệt đối

- **Đầu vào là int/long?** Nhận diện MIN_VALUE và giới hạn biểu diễn của kiểu.
- **Cần giữ nguyên kiểu và báo lỗi nếu tràn?** Dùng `Math.absExact(int/long)`; xử lý `ArithmeticException` ở tầng thích hợp.
- **Nguồn là int, cần độ lớn toán học chính xác?** Cast sang `long` **trước** `Math.abs`.
- **Nguồn là long, cần độ lớn chính xác kể cả MIN_VALUE?** Đổi sang `BigInteger` trước khi gọi `abs()`.
- **Đối số là kết quả cộng/trừ/nhân?** Kiểm tra **overflow của biểu thức trung gian**, không chỉ gọi `absExact` sau đó.
- **Mục tiêu là index/bucket trong `0..n-1`?** Cân nhắc `Math.floorMod(x,n)` với `n>0`, theo đúng chính sách ánh xạ thuật toán.
- **Giá trị có thể là số thực?** Không áp dụng quy tắc MIN_VALUE của integer sang `float`/`double`; xác định cách xử lý NaN, infinity, signed zero.
- **Kiểm thử:** thêm `MIN_VALUE`, `MIN_VALUE+1`, `-1`, `0`, `1`, `MAX_VALUE` và những biểu thức trung gian có thể tràn.

**Điểm cốt lõi:** `Math.abs` trên `int`/`long` không cam kết mọi kết quả đều không âm; giá trị MIN_VALUE là ngoại lệ do miền bù hai bất đối xứng. `Math.absExact` báo lỗi khi trị tuyệt đối không vừa kiểu; khi cần giá trị chính xác vượt miền, hãy đổi sang kiểu đủ rộng **trước khi thực hiện phép tính**.
