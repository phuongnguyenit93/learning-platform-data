# Kiểm tra trị tuyệt đối an toàn bằng `Math.absExact` (Java 15+)

Bài **Thực hành** này tập trung vào một lỗi nhỏ nhưng nguy hiểm khi xử lý số nguyên Java: `Math.abs(x)` có thể trả về **giá trị âm** nếu `x` là số nguyên âm nhỏ nhất. `Math.absExact`, được bổ sung từ Java 15 và vẫn có mặt trên các JDK hiện hành, giải quyết trường hợp đó bằng cách **ném `ArithmeticException` khi trị tuyệt đối không thể biểu diễn trong kiểu kết quả**. Nội dung dưới đây dùng API còn được hỗ trợ, với ví dụ độc lập chạy được trên Java 17+.

## 1. Mục tiêu và vấn đề thực tế

Sau bài này, bạn có thể:

- Giải thích vì sao `Math.abs(Integer.MIN_VALUE)` và `Math.abs(Long.MIN_VALUE)` không trả về một số dương.
- Chọn đúng overload `Math.absExact(int)` hoặc `Math.absExact(long)` và xác định chính xác lúc nào nó ném ngoại lệ.
- Viết chương trình nhận dữ liệu biên, xử lý ngoại lệ rõ ràng và kiểm thử kết quả mà không phụ thuộc thông điệp lỗi của JVM.
- Nhận ra phép trừ/nhân có thể **tràn trước khi** `absExact` chạy; biết khi nào phải mở rộng sang `long` hoặc `BigInteger`.
- Phân biệt bài toán **lấy độ lớn** với bài toán **tính chỉ số mảng/hash bucket** để không dùng `absExact` sai mục đích.

### Tình huống mở đầu

Giả sử lập trình viên muốn biến mọi độ lệch âm thành số không âm:

~~~java
int difference = Integer.MIN_VALUE;
int magnitude = Math.abs(difference);
System.out.println(magnitude); // -2147483648: vẫn âm!
~~~

Nếu sau đó dùng `magnitude` làm chỉ số, độ dài hoặc độ lệch thời gian, chương trình có thể vi phạm điều kiện mà code tưởng như đã đảm bảo. Lỗi không phải do `Math.abs` trả sai theo tài liệu; nguyên nhân là **trị tuyệt đối toán học không nằm trong miền giá trị của kiểu `int`**.

## 2. Vì sao chỉ có một giá trị đặc biệt?

Các kiểu `int` và `long` của Java dùng biểu diễn số nguyên có dấu kiểu bù hai. Miền giá trị **không đối xứng**:

| Kiểu | Giá trị nhỏ nhất | Giá trị lớn nhất | Trị tuyệt đối của số nhỏ nhất |
| --- | ---: | ---: | ---: |
| `int` (32 bit) | -2.147.483.648 (`Integer.MIN_VALUE`) | 2.147.483.647 | 2.147.483.648, **không vừa `int`** |
| `long` (64 bit) | -9.223.372.036.854.775.808 (`Long.MIN_VALUE`) | 9.223.372.036.854.775.807 | 9.223.372.036.854.775.808, **không vừa `long`** |

Ví dụ toán học: `|-7| = 7`, `|0| = 0`, nhưng `|-2³¹| = 2³¹` lớn hơn `Integer.MAX_VALUE = 2³¹ - 1`. Khi phép đổi dấu bị tràn, `-Integer.MIN_VALUE` vẫn có giá trị `Integer.MIN_VALUE` theo quy tắc số nguyên cố định độ rộng của Java. Điều tương tự đúng với `long`.

Với **mọi** giá trị `int` khác `Integer.MIN_VALUE`, và với **mọi** giá trị `long` khác `Long.MIN_VALUE`, trị tuyệt đối vẫn nằm trong miền biểu diễn. Vì thế `absExact` chỉ cần báo tràn trong đúng trường hợp biên của mỗi kiểu.

## 3. `Math.abs` và `Math.absExact` khác nhau thế nào?

API chuẩn trong `java.lang.Math` (không cần import):

~~~java
public static int absExact(int a);
public static long absExact(long a);
~~~

*Hai dòng trên chỉ là chữ ký API minh họa; không đặt vào một class rồi biên dịch như code tự triển khai.*

Quy tắc:

- `a > 0`: trả về `a`.
- `a == 0`: trả về `0`.
- `a < 0` nhưng không phải `MIN_VALUE`: trả về `-a`.
- `a == Integer.MIN_VALUE` trong overload `int`, hoặc `a == Long.MIN_VALUE` trong overload `long`: ném **`ArithmeticException`**. Không trả về giá trị, không tự ép sang kiểu lớn hơn.

So sánh bằng bảng:

| Biểu thức | Kết quả |
| --- | --- |
| `Math.abs(-12)` | `12` |
| `Math.absExact(-12)` | `12` |
| `Math.absExact(0)` | `0` |
| `Math.absExact(Integer.MAX_VALUE)` | `2147483647` |
| `Math.abs(Integer.MIN_VALUE)` | `-2147483648` |
| `Math.absExact(Integer.MIN_VALUE)` | **`ArithmeticException`** |
| `Math.abs(Long.MIN_VALUE)` | `-9223372036854775808L` |
| `Math.absExact(Long.MIN_VALUE)` | **`ArithmeticException`** |
| `Math.absExact((long) Integer.MIN_VALUE)` | `2147483648L`: lúc này dùng overload `long` |

**Đặc điểm quan trọng:** `Math.absExact` kiểm tra **khả năng biểu diễn kết quả trong chính kiểu đầu vào**. Nó không phải thuật toán số nguyên vô hạn, không tự bão hòa về MAX_VALUE và không tự chuyển `int` thành `long`.

## 4. Thực hành 1: chạy và so sánh tại các giá trị biên

Tạo file **`AbsExactPractice.java`**:

~~~java
import java.math.BigInteger;

public final class AbsExactPractice {
    private static void printInt(int value) {
        try {
            System.out.printf("int %d -> %d%n", value, Math.absExact(value));
        } catch (ArithmeticException e) {
            System.out.printf("int %d -> OVERFLOW%n", value);
        }
    }

    private static void printLong(long value) {
        try {
            System.out.printf("long %d -> %d%n", value, Math.absExact(value));
        } catch (ArithmeticException e) {
            System.out.printf("long %d -> OVERFLOW%n", value);
        }
    }

    public static void main(String[] args) {
        printInt(0);
        printInt(-27);
        printInt(Integer.MAX_VALUE);
        printInt(Integer.MIN_VALUE);
        printLong(-27L);
        printLong(Long.MIN_VALUE);

        System.out.println("Math.abs(MIN_INT) = "
                + Math.abs(Integer.MIN_VALUE));
        System.out.println("widen int MIN to long = "
                + Math.absExact((long) Integer.MIN_VALUE));
        System.out.println("BigInteger long MIN = "
                + BigInteger.valueOf(Long.MIN_VALUE).abs());
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên (lệnh tương tự trên Linux/macOS và PowerShell):

~~~bash
javac --release 17 AbsExactPractice.java
java AbsExactPractice
~~~

**Stdout chính xác:**

~~~text
int 0 -> 0
int -27 -> 27
int 2147483647 -> 2147483647
int -2147483648 -> OVERFLOW
long -27 -> 27
long -9223372036854775808 -> OVERFLOW
Math.abs(MIN_INT) = -2147483648
widen int MIN to long = 2147483648
BigInteger long MIN = 9223372036854775808
~~~

Đây là kết quả đã được kiểm tra bằng biên dịch với `--release 17` và chạy trên JDK hiện đại.

**Đọc kết quả:**

1. `Math.absExact(-27)` tính đúng như `Math.abs(-27)` vì `27` nằm trong miền của `int` và `long`.
2. Khi gặp `Integer.MIN_VALUE`/`Long.MIN_VALUE`, `absExact` báo tràn thay vì âm thầm trả số âm.
3. `Math.abs(Integer.MIN_VALUE)` vẫn trả về số âm theo hợp đồng của `Math.abs(int)`.
4. Cast **trước** khi tính: `Math.absExact((long) Integer.MIN_VALUE)` có thể tạo `2147483648L`. Giá trị này không vừa `int`, nhưng vừa `long`.
5. `BigInteger.valueOf(Long.MIN_VALUE).abs()` tính trị tuyệt đối chính xác không phụ thuộc giới hạn `long`.

Nên bắt `ArithmeticException` tại nơi có quyết định xử lý lỗi có ý nghĩa. Không bắt `Exception` quá rộng và không âm thầm trả `0` hoặc `Integer.MAX_VALUE` khi yêu cầu nghiệp vụ đòi kết quả chính xác.

## 5. Chọn cách xử lý tùy hợp đồng dữ liệu

### 5.1. Trường hợp cần giữ kết quả trong `int`/`long`

Dùng `absExact` để **fail fast**:

~~~java
static int requireIntMagnitude(int delta) {
    return Math.absExact(delta);
}

static long requireLongMagnitude(long delta) {
    return Math.absExact(delta);
}
~~~

Hai phương thức trên là **đoạn mã minh họa** cần đặt trong một class; không phải hai chương trình độc lập. Nếu `delta` bằng MIN_VALUE tương ứng, lời gọi ném `ArithmeticException` cho caller xử lý.

Khi lỗi là dữ liệu đầu vào không hợp lệ theo nghiệp vụ, có thể chuyển ngoại lệ tại ranh giới API:

~~~java
static int validatedMagnitude(int delta) {
    try {
        return Math.absExact(delta);
    } catch (ArithmeticException cause) {
        throw new IllegalArgumentException(
                "Do lon khong nam trong mien int", cause);
    }
}
~~~

Cách chuyển lỗi phải nhất quán với hợp đồng: nếu tầng xử lý đang cung cấp hàm toán học, giữ `ArithmeticException` có thể hợp lý hơn. **Không assert chuỗi `e.getMessage()` của `ArithmeticException`**; thông điệp không phải API contract ổn định.

### 5.2. Muốn chấp nhận `Integer.MIN_VALUE`? Mở rộng sang `long` trước

~~~java
int x = Integer.MIN_VALUE;
long magnitude = Math.absExact((long) x);
System.out.println(magnitude); // 2147483648
~~~

`(long) x` được thực hiện **trước khi** lấy trị tuyệt đối, vì thế overload `absExact(long)` được chọn. Mọi giá trị `int` đều có trị tuyệt đối vừa `long`, kể cả MIN_VALUE.

Các phép sau **không** tương đương:

~~~java
// Sai: abs(int) đã tràn trước khi chuyển thành long.
long wrong = (long) Math.abs(Integer.MIN_VALUE);

// Đúng: chuyển int sang long trước phép abs.
long correct = Math.absExact((long) Integer.MIN_VALUE);
~~~

`wrong` vẫn là `-2147483648L`; `correct` là `2147483648L`. Nếu sau đó ép `correct` trở lại `int` bằng cast, kết quả lại bị thu hẹp sai. Nếu cần chuyển có kiểm tra, dùng `Math.toIntExact(correct)` và chấp nhận ngoại lệ khi không vừa `int`.

### 5.3. Muốn chấp nhận `Long.MIN_VALUE`? Dùng `BigInteger`

Không có kiểu nguyên primitive có dấu rộng hơn `long` trong Java. Khi độ lớn của mọi giá trị `long` đều phải hợp lệ, dùng:

~~~java
import java.math.BigInteger;

// Đặt trong method:
long value = Long.MIN_VALUE;
BigInteger magnitude = BigInteger.valueOf(value).abs();
System.out.println(magnitude); // 9223372036854775808
~~~

Nếu gọi `magnitude.longValueExact()`, kết quả sẽ ném `ArithmeticException` vì không vừa `long`. Đây là hành vi **đúng**: muốn chính xác thì phải giữ kết quả bằng `BigInteger` (hoặc biểu diễn khác đáp ứng yêu cầu), không cố thu hẹp trở lại. `BigInteger` có chi phí cấp phát/tính toán cao hơn primitive, nên chỉ dùng khi bài toán thật sự cần miền giá trị rộng.

### 5.4. Khi đầu vào phải không âm, kiểm tra quy tắc nghiệp vụ trước

`Math.absExact` **không** phải hàm xác nhận rằng đầu vào không âm: `Math.absExact(-3)` trả `3`. Nếu tham số `size`, `quantity` hay `timeout` buộc phải không âm, viết điều kiện rõ ràng:

~~~java
static int requireNonNegative(int value) {
    if (value < 0) {
        throw new IllegalArgumentException("value must be >= 0");
    }
    return value;
}
~~~

Với yêu cầu "lấy độ lớn của độ lệch có dấu", `absExact` hợp lý; với yêu cầu "từ chối mọi dữ liệu âm", dùng validation. Hai hợp đồng khác nhau.

## 6. Lỗi nguy hiểm hơn: tính trừ trước rồi mới gọi `absExact`

Hàm `absExact` chỉ kiểm tra **phép lấy trị tuyệt đối**. Nếu biểu thức bên trong đã tràn, nó **không thể phục hồi** hai toán hạng ban đầu.

Ví dụ sai:

~~~java
int left = Integer.MIN_VALUE;
int right = Integer.MAX_VALUE;

// Sai: left - right bị tràn int trước khi Math.absExact nhận kết quả.
int wrongDistance = Math.absExact(left - right);
System.out.println(wrongDistance); // 1, nhưng khoảng cách thật là 4294967295
~~~

Vì phép trừ `int` này tràn thành `1`, `absExact(1)` hoàn toàn hợp lệ và không ném ngoại lệ. **Không có ngoại lệ không đồng nghĩa phép tính toàn bộ là an toàn.**

Đúng với hai đầu vào `int`:

~~~java
int left = Integer.MIN_VALUE;
int right = Integer.MAX_VALUE;

long delta = (long) left - right;
long distance = Math.absExact(delta);

System.out.println(distance); // 4294967295
~~~

Lý do: đưa ít nhất **một toán hạng sang `long` trước phép trừ**. Chênh lệch lớn nhất giữa hai `int` là `4294967295`, vẫn vừa `long`.

Nếu giữ kết quả bằng `int` và muốn phát hiện tràn:

~~~java
int delta = Math.subtractExact(left, right); // Ném ArithmeticException.
int distance = Math.absExact(delta);
~~~

`Math.subtractExact` ngăn phép trừ `int` tràn âm thầm, nhưng cách này **từ chối** độ lệch hợp lệ về toán học nếu nằm ngoài miền `int`. Chọn kiểu kết quả theo nghiệp vụ.

Với hai đầu vào `long`, ngay cả hiệu `long` cũng có thể vượt miền `long`. Có hai hướng:

- Nếu hợp đồng chỉ cho kết quả trong `long`: dùng `Math.subtractExact(a, b)` rồi `Math.absExact(delta)`; phép nào không biểu diễn được sẽ ném `ArithmeticException`.
- Nếu cần khoảng cách chính xác của **mọi** cặp `long`: dùng `BigInteger.valueOf(a).subtract(BigInteger.valueOf(b)).abs()`.

### Thực hành 2: tính khoảng cách an toàn

Tạo file **`SafeDistance.java`**:

~~~java
import java.math.BigInteger;

public final class SafeDistance {
    public static long distance(int left, int right) {
        // Cast trước phép trừ để tránh overflow của int.
        long delta = (long) left - right;
        return Math.absExact(delta);
    }

    public static boolean withinTolerance(
            int left, int right, long tolerance) {
        if (tolerance < 0) {
            throw new IllegalArgumentException("tolerance must be >= 0");
        }
        return distance(left, right) <= tolerance;
    }

    public static BigInteger distance(long left, long right) {
        return BigInteger.valueOf(left)
                .subtract(BigInteger.valueOf(right))
                .abs();
    }

    public static void main(String[] args) {
        System.out.println(distance(
                Integer.MIN_VALUE, Integer.MAX_VALUE));
        System.out.println(withinTolerance(7, 10, 3));
        System.out.println(withinTolerance(7, 10, 2));
        System.out.println(distance(
                Long.MIN_VALUE, Long.MAX_VALUE));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 SafeDistance.java
java SafeDistance
~~~

Stdout:

~~~text
4294967295
true
false
18446744073709551615
~~~

Đầu ra cuối lớn hơn `Long.MAX_VALUE`, vì thế overload dành cho `long` trả về `BigInteger`. Đây là ví dụ **hai overload có kiểu trả về khác nhau theo kiểu tham số**; Java phân biệt overload nhờ kiểu tham số `(int,int)` và `(long,long)`, không dựa vào kiểu trả về.

## 7. Các trường hợp áp dụng dễ nhầm

### 7.1. Hash bucket và chỉ số mảng: dùng `floorMod` thay vì `absExact`

Đoạn code dễ lỗi:

~~~java
int index = Math.abs(hash) % bucketCount;
~~~

Nếu `hash == Integer.MIN_VALUE`, `Math.abs(hash)` vẫn âm; phép `%` trong Java có thể để lại remainder âm, dẫn tới index âm. Thay bằng:

~~~java
static int bucketIndex(int hash, int bucketCount) {
    if (bucketCount <= 0) {
        throw new IllegalArgumentException("bucketCount must be positive");
    }
    return Math.floorMod(hash, bucketCount);
}
~~~

Với `bucketCount > 0`, kết quả nằm trong `[0, bucketCount - 1]`, kể cả hash là `Integer.MIN_VALUE`. Ví dụ `Math.floorMod(Integer.MIN_VALUE, 10)` trả `2`.

**Vì sao không dùng `absExact(hash) % bucketCount`?** Cách đó sẽ ném ngoại lệ với một hash hợp lệ (`Integer.MIN_VALUE`), trong khi chọn bucket không đòi trị tuyệt đối toán học. `floorMod` diễn đạt đúng bài toán.

### 7.2. `byte` và `short` được nâng lên `int`

Không tồn tại overload `Math.absExact(byte)` hay `Math.absExact(short)`. Khi truyền hai kiểu đó, Java **widen** sang `int`:

~~~java
byte small = Byte.MIN_VALUE;       // -128
int magnitude = Math.absExact(small); // 128: hợp lệ trong int
byte narrowed = (byte) magnitude;  // -128: thu hẹp bị mất giá trị
~~~

Bởi vậy, khi API của bạn phải trả lại `byte`/`short`, cần kiểm tra miền của **kiểu đích** trước khi cast. `absExact` bảo vệ kiểu overload được chọn, không tự kiểm tra mọi phép cast tiếp theo. Với `long` sang `int`, sử dụng `Math.toIntExact` là một lựa chọn kiểm tra thu hẹp hiện hành.

### 7.3. `float` và `double`

`Math.absExact` **chỉ có overload `int` và `long`**, không nhận `float`/`double`. Dùng `Math.abs(float)` hoặc `Math.abs(double)` khi tính trị tuyệt đối số thực; riêng `NaN`, infinity và số không âm/âm theo IEEE 754 có hợp đồng khác. Đừng suy luận cơ chế overflow của số nguyên áp dụng y nguyên cho số thực.

### 7.4. Không dùng ngoại lệ làm cách kiểm soát luồng bình thường

Khi đầu vào `Integer.MIN_VALUE` là một **lỗi nghiệp vụ cần từ chối**, `absExact` với exception rõ nghĩa là phù hợp. Nếu đầu vào thường xuyên có thể là MIN_VALUE nhưng vẫn cần xử lý chính xác, hãy chọn `long` hoặc `BigInteger` **từ đầu**, thay vì thường xuyên ném rồi bắt exception. Chi phí và ý nghĩa của API sẽ rõ ràng hơn.

## 8. Kiểm thử biên không phụ thuộc framework

Một phép kiểm thử tốt phải xác nhận được *giá trị bình thường* lẫn *exception đúng kiểu*, đồng thời không phụ thuộc thời gian chạy hay nội dung message của exception.

Tạo file **`AbsExactBoundaryTest.java`**:

~~~java
public final class AbsExactBoundaryTest {
    private static int passed;

    private static void equal(long expected, long actual) {
        if (expected != actual) {
            throw new AssertionError(
                    "expected " + expected + ", got " + actual);
        }
        passed++;
    }

    private static void overflow(Runnable action) {
        try {
            action.run();
        } catch (ArithmeticException expected) {
            passed++;
            return;
        }
        throw new AssertionError("Expected ArithmeticException");
    }

    public static void main(String[] args) {
        equal(0, Math.absExact(0));
        equal(27, Math.absExact(-27));
        equal(Integer.MAX_VALUE,
                Math.absExact(-Integer.MAX_VALUE));
        overflow(() -> Math.absExact(Integer.MIN_VALUE));

        equal(Long.MAX_VALUE,
                Math.absExact(-Long.MAX_VALUE));
        overflow(() -> Math.absExact(Long.MIN_VALUE));

        equal(2147483648L,
                Math.absExact((long) Integer.MIN_VALUE));
        equal(4294967295L,
                Math.absExact((long) Integer.MIN_VALUE
                        - Integer.MAX_VALUE));

        System.out.println(passed + " checks passed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 AbsExactBoundaryTest.java
java AbsExactBoundaryTest
~~~

Stdout:

~~~text
8 checks passed
~~~

Nếu dùng **JUnit Jupiter** trong ứng dụng có dependency test tương ứng, có thể diễn đạt hai case quan trọng bằng snippet sau (đặt trong test class có `@Test` và các static import):

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class AbsExactJUnitTest {
    @Test
    void normalCases() {
        assertEquals(0, Math.absExact(0));
        assertEquals(27, Math.absExact(-27));
        assertEquals(Integer.MAX_VALUE,
                Math.absExact(-Integer.MAX_VALUE));
    }

    @Test
    void minimumValuesThrow() {
        assertThrows(ArithmeticException.class,
                () -> Math.absExact(Integer.MIN_VALUE));
        assertThrows(ArithmeticException.class,
                () -> Math.absExact(Long.MIN_VALUE));
    }

    @Test
    void wideningBeforeAbsSupportsIntMinimum() {
        assertEquals(2147483648L,
                Math.absExact((long) Integer.MIN_VALUE));
    }
}
~~~

Đây là **source test cần JUnit Jupiter trên test classpath**, không phải Java SE standalone. Khi viết test ở dự án thật, thêm các biến thể của `Math.absExact` và `Math.abs` vào cùng test suite chỉ khi bài toán cần so sánh hai hợp đồng; tránh nhân đôi test không có ý nghĩa.

### Ma trận test nên có

| Phân loại | Giá trị đầu vào | Kỳ vọng |
| --- | --- | --- |
| Số không | `0` | `0` |
| Dương bình thường | `27` | `27` |
| Âm bình thường | `-27` | `27` |
| Cận dương `int` | `Integer.MAX_VALUE` | Trả nguyên giá trị |
| Kề cận âm `int` | `Integer.MIN_VALUE + 1` | `Integer.MAX_VALUE` |
| Cực tiểu `int` | `Integer.MIN_VALUE` | `ArithmeticException` |
| Cận âm `long` | `Long.MIN_VALUE + 1` | `Long.MAX_VALUE` |
| Cực tiểu `long` | `Long.MIN_VALUE` | `ArithmeticException` |
| Mở rộng trước phép toán | `(long) Integer.MIN_VALUE` | `2147483648L` |
| Chênh lệch hai `int` cực biên | `(long) MIN_INT - MAX_INT` | Trị tuyệt đối bằng `4294967295L` |

Đối với kiểm thử tính toán phức hợp, test cả **tràn ở toán tử trước `absExact`** và **tràn ngay tại `absExact`**; chúng là hai loại lỗi khác nhau.

## 9. Lỗi thường gặp và cách sửa

| Cách viết/vấn đề | Rủi ro | Cách sửa |
| --- | --- | --- |
| `Math.abs(Integer.MIN_VALUE)` rồi tin kết quả không âm | Nhận số âm | `Math.absExact` nếu cần `int`, hoặc widen sang `long` nếu cần chấp nhận MIN |
| `Math.absExact(a - b)` khi `a,b` là `int` | Phép trừ đã tràn, kết quả sai nhưng không exception | `Math.absExact((long) a - b)` |
| `Math.absExact(Math.subtractExact(a,b))` nhưng yêu cầu mọi khoảng cách hai `int` | Ném ngoại lệ với khoảng cách toán học > MAX_INT | Đổi kết quả sang `long` |
| `Math.absExact(leftLong - rightLong)` | Hiệu `long` có thể tràn trước `absExact` | `Math.subtractExact` nếu fail fast; `BigInteger` nếu cần mọi khoảng cách |
| `(long) Math.abs(intValue)` | Cast xảy ra sau overflow | `Math.absExact((long) intValue)` |
| `(byte) Math.absExact(byteValue)` | Narrowing làm sai kết quả dù `absExact` đúng | Giữ `int` hoặc kiểm tra miền `byte` trước cast |
| `Math.absExact(hash) % n` | Một hash hợp lệ có thể làm exception | `Math.floorMod(hash, n)` với `n > 0` |
| `catch (ArithmeticException e) { return 0; }` | Biến dữ liệu không biểu diễn được thành zero hợp lệ | Propagate hoặc map lỗi theo hợp đồng API |
| Cố so khớp toàn bộ message exception | Message không có hợp đồng ổn định | Kiểm tra **loại** exception và điều kiện ném |
| Dùng `BigInteger` nhưng lại gọi `longValue()` vô điều kiện | Có thể mất phần giá trị vượt miền `long` | Giữ `BigInteger`; nếu cần chuyển, dùng `longValueExact()` |
| Mong `absExact` làm tròn hay saturation | API không thực hiện chuyển nghĩa đó | Thiết kế saturation rõ ràng riêng, chỉ khi nghiệp vụ cho phép |

## 10. Bài tập mở rộng có đáp án định hướng

1. **Bài 1 — So sánh biên.** Chạy `Math.abs(Integer.MIN_VALUE)` và `Math.absExact(Integer.MIN_VALUE)`. Giải thích vì sao một bên trả số âm, một bên ném ngoại lệ. **Đáp án:** trị tuyệt đối `2³¹` ngoài miền `int`; `abs` giữ kết quả overflow còn `absExact` phát hiện.
2. **Bài 2 — Không làm mất dữ liệu.** Viết hàm `long magnitude(int x)` nhận mọi `int`. **Đáp án cốt lõi:** `return Math.absExact((long) x);`. Kiểm thử `Integer.MIN_VALUE` trả `2147483648L`.
3. **Bài 3 — Tránh overflow trước `absExact`.** Tính khoảng cách giữa `Integer.MIN_VALUE` và `Integer.MAX_VALUE`. **Đáp án:** ép một operand sang `long` trước phép trừ, lấy trị tuyệt đối để nhận `4294967295L`.
4. **Bài 4 — Khoảng cách `long` tổng quát.** Viết hàm nhận hai `long` bất kỳ mà không được làm mất giá trị. **Đáp án cốt lõi:** `BigInteger.valueOf(a).subtract(BigInteger.valueOf(b)).abs()`; cặp cực biên cho `18446744073709551615`.
5. **Bài 5 — Bucket index.** Với `hash = Integer.MIN_VALUE` và `bucketCount = 10`, vì sao dùng `Math.abs(hash) % 10` là sai? **Đáp án:** `Math.abs` giữ kết quả âm; dùng `Math.floorMod(hash, 10)` để nhận chỉ số `2`.
6. **Bài 6 — API contract.** Một hệ thống chỉ cho phép `int` magnitude. Nên làm gì khi nhận `Integer.MIN_VALUE`? **Đáp án:** từ chối có chủ đích bằng `ArithmeticException`/lỗi miền nghiệp vụ; không trả số âm hoặc tự thay bằng MAX_INT.

## 11. Ghi nhớ khi áp dụng vào hệ thống thật

- `Math.absExact` là phép **trị tuyệt đối có kiểm tra overflow**, dành cho `int` và `long`, từ Java 15 trở lên.
- Giá trị gây exception là **đúng một số** cho mỗi overload: `Integer.MIN_VALUE` hoặc `Long.MIN_VALUE`.
- Muốn trả về độ lớn của **mọi `int`**, mở rộng sang `long` **trước** phép toán.
- Muốn độ lớn/chênh lệch đầy đủ cho **mọi `long`**, dùng `BigInteger`.
- Muốn bảo vệ chuỗi biểu thức, kiểm tra **tất cả phép tính trung gian**; `absExact` không sửa được overflow đã xảy ra.
- Muốn bucket index không âm, ưu tiên `floorMod` và kiểm tra số bucket dương.
- Test giá trị bình thường, cực biên và exception; không phụ thuộc exception message. Khi biên dịch bằng JDK mới cho sản phẩm có mức Java tối thiểu, dùng `javac --release <phiên_bản_hỗ_trợ>` và chạy test trên runtime tối thiểu. Các ví dụ ở đây dùng `--release 17`.

## 12. Tài liệu chuẩn để đối chiếu

- [Oracle Java SE 25 — `Math.absExact`, `abs`, `subtractExact` và `floorMod`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html)
- [Oracle Java SE 17 — `Math.absExact`, ghi nhận `Since: 15`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html)
- [Java Language Specification — `4.2.1 Integral Types and Values`](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.2.1)
- [Oracle Java SE 25 — `BigInteger.abs`, `valueOf`, `longValueExact`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigInteger.html)
