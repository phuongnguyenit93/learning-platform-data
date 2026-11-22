# Integer.MIN_VALUE, Long.MIN_VALUE và miền số bất đối xứng trong Java 15+

## 1. Mục tiêu và bối cảnh

`Integer.MIN_VALUE` và `Long.MIN_VALUE` là các hằng biểu thị số nguyên âm nhỏ nhất của kiểu `int` và `long` trong Java. Giá trị nhỏ nhất của chúng có độ lớn tuyệt đối lớn hơn giá trị dương lớn nhất **đúng một đơn vị**. Hệ quả rất dễ bỏ sót: `Math.abs(Integer.MIN_VALUE)` vẫn âm, phép `-Integer.MIN_VALUE` không ra số dương, và một phép cộng/trừ tưởng như đơn giản có thể bị tràn.

Đây là kiến thức của Java SE **vẫn áp dụng trong các JDK hiện hành**. Java 15 bổ sung `Math.absExact(int)` và `Math.absExact(long)` để báo lỗi thay vì âm thầm trả về giá trị âm trong trường hợp này.

Sau bài, bạn có thể:

- Đọc chính xác giới hạn và biểu diễn bù hai của `int`/`long`.
- Giải thích nguyên nhân miền số có dấu bất đối xứng.
- Dự đoán kết quả tràn của đổi dấu, `Math.abs`, `MAX_VALUE + 1` và `MIN_VALUE / -1`.
- Chọn `Math.absExact`, `Math.negateExact`, ép kiểu `long` hoặc `BigInteger` khi cần.
- Viết comparator, phép lấy chỉ số bucket, phép đếm kích thước miền và kiểm thử biên an toàn.

## 2. Miền số nguyên có dấu và các hằng chuẩn

Java định nghĩa kiểu `int` là **32 bit có dấu** và `long` là **64 bit có dấu** theo biểu diễn **two's complement (bù hai)**, bất kể JVM chạy trên hệ điều hành 32 hay 64 bit.

| Kiểu | Số bit | `MIN_VALUE` | `MAX_VALUE` | Tổng số giá trị |
| --- | ---: | ---: | ---: | ---: |
| `int` | 32 | `-2147483648` (`-2^31`) | `2147483647` (`2^31 - 1`) | `2^32` |
| `long` | 64 | `-9223372036854775808` (`-2^63`) | `9223372036854775807` (`2^63 - 1`) | `2^64` |

Trong mã, sử dụng các hằng `public static final` có kiểu nguyên thủy:

```java
int minInt = Integer.MIN_VALUE;
int maxInt = Integer.MAX_VALUE;
long minLong = Long.MIN_VALUE;
long maxLong = Long.MAX_VALUE;
```

Các hằng trên thuộc wrapper class `Integer` / `Long` nhưng mang giá trị `int` / `long`. Không cần tạo đối tượng wrapper. Nếu cần đối chiếu ở runtime, in trực tiếp hằng thay vì viết lại những số dài dễ sai chữ số.

Với một số nguyên có dấu rộng `w` bit:

- Miền đầy đủ: `[-2^(w-1), 2^(w-1)-1]`.
- Số âm: `2^(w-1)` giá trị, từ `-2^(w-1)` đến `-1`.
- Số dương: `2^(w-1)-1` giá trị, từ `1` đến `2^(w-1)-1`.
- Số không: một giá trị `0`, không có số âm 0 riêng biệt.

Do đó **số âm nhiều hơn số dương một giá trị**. Hai đẳng thức mô tả biên:

```text
Integer.MIN_VALUE = -Integer.MAX_VALUE - 1
Long.MIN_VALUE    = -Long.MAX_VALUE - 1
```

Lý do biểu diễn: 32 bit có `2^32` mẫu; trong số đó, mẫu với bit cao nhất 1 đại diện số âm theo bù hai, còn nửa còn lại đại diện số 0 và số dương. Một số mẫu `int`:

| Giá trị | Mẫu bit ở dạng hexadecimal |
| --- | --- |
| `0` | `0x00000000` |
| `1` | `0x00000001` |
| `Integer.MAX_VALUE` | `0x7fffffff` |
| `-1` | `0xffffffff` |
| `Integer.MIN_VALUE` | `0x80000000` |

Mẫu `long` tương ứng: `Long.MIN_VALUE` = `0x8000000000000000` và `Long.MAX_VALUE` = `0x7fffffffffffffff`. Giá trị dương `2147483648` không nằm trong miền `int`; dương `9223372036854775808` không nằm trong miền `long`.

## 3. Tràn khi đổi dấu và phép toán thông thường

Hãy thử mã Java sau:

```java
int a = Integer.MIN_VALUE;
long b = Long.MIN_VALUE;

System.out.println(-a); // -2147483648
System.out.println(-b); // -9223372036854775808
```

Theo toán học, `-(-2147483648) = +2147483648`. Nhưng kết quả dương này **vượt `Integer.MAX_VALUE`**. Đổi dấu số nguyên `int`/`long` không tự nâng sang kiểu rộng hơn; phép toán số nguyên thông thường của Java **không ném ngoại lệ khi tràn**, và kết quả wrap-around theo độ rộng bit. Vì vậy `-Integer.MIN_VALUE == Integer.MIN_VALUE` và `-Long.MIN_VALUE == Long.MIN_VALUE`.

Thêm hai trường hợp đáng nhớ:

```java
System.out.println(Integer.MAX_VALUE + 1); // -2147483648
System.out.println(Integer.MIN_VALUE / -1); // -2147483648
```

`MAX_VALUE + 1` vượt biên dương rồi quay sang cực âm. `MIN_VALUE / -1` có thương toán học là số dương vượt miền `int`, nên phép chia số nguyên cho kết quả cực âm thay vì báo lỗi tràn. **Chia cho 0** mới là trường hợp toán tử chia `/` ném `ArithmeticException`.

Điều này không có nghĩa mọi phép toán với `MIN_VALUE` đều lỗi; ví dụ `Integer.MIN_VALUE + 1` và `Integer.MIN_VALUE / 2` đều biểu diễn được. Cần xét **kết quả của phép tính cụ thể**, không xem `MIN_VALUE` là một giá trị bất hợp lệ.

## 4. Bẫy `Math.abs`: trị tuyệt đối của MIN_VALUE vẫn âm

Thông thường `Math.abs(-5) == 5`. Nhưng Javadoc quy định:

```java
System.out.println(Math.abs(Integer.MIN_VALUE));
// -2147483648

System.out.println(Math.abs(Long.MIN_VALUE));
// -9223372036854775808
```

Vì `2^31` không biểu diễn được bằng `int` và `2^63` không biểu diễn được bằng `long`, `Math.abs` trả về **chính giá trị cực âm**. Đó là hành vi chuẩn xác định, không phụ thuộc triển khai máy ảo.

| Biểu thức | Kết quả |
| --- | --- |
| `Math.abs(-1)` | `1` |
| `Math.abs(Integer.MAX_VALUE)` | `2147483647` |
| `Math.abs(Integer.MIN_VALUE + 1)` | `2147483647` |
| `Math.abs(Integer.MIN_VALUE)` | `-2147483648` |
| `Math.abs(Long.MIN_VALUE)` | `-9223372036854775808` |

Bởi vậy, với biến `int x` bất kỳ, khẳng định `Math.abs(x) >= 0` **không luôn đúng**. Với `long` cũng tương tự. Không sử dụng `Math.abs` như một phép "bảo đảm kết quả không âm" khi giá trị đầu vào có thể là `MIN_VALUE`.

Chú ý `Float.MIN_VALUE`/`Double.MIN_VALUE` mang ý nghĩa khác (giá trị dương nhỏ nhất khác 0 của kiểu floating-point). Đừng áp dụng trực tiếp kết luận này cho mọi overload `Math.abs` của số thực.

## 5. API hiện hành để xử lý đúng: `Math.absExact` và `Math.negateExact`

**`Math.absExact(int)` và `Math.absExact(long)` được thêm từ Java 15**, vẫn tồn tại trên JDK hiện đại. Chúng trả trị tuyệt đối khi biểu diễn được trong cùng kiểu; với `MIN_VALUE`, chúng **ném `ArithmeticException`**.

```java
int valid = Math.absExact(-7); // 7
long alsoValid = Math.absExact(-7L); // 7L

// Hai dòng sau cố ý ném ArithmeticException:
Math.absExact(Integer.MIN_VALUE);
Math.absExact(Long.MIN_VALUE);
```

Đây là đoạn minh họa các lời gọi độc lập, trong đó hai lời gọi sau chủ đích ném ngoại lệ; khi dùng trong ứng dụng cần xử lý hoặc để ngoại lệ được truyền cho nơi kiểm soát lỗi.

Để **đổi dấu và báo tràn**, `Math.negateExact` là một lựa chọn rõ nghĩa:

```java
int ok = Math.negateExact(9); // -9

// Ném ArithmeticException:
Math.negateExact(Integer.MIN_VALUE);
```

Các phương thức `Math.addExact`, `subtractExact`, `multiplyExact`, `incrementExact` và `toIntExact` cũng giúp kiểm soát thao tác hoặc thu hẹp kiểu mà không chấp nhận overflow âm thầm. Chúng **không tự động tạo ra một kiểu rộng hơn** để chứa mọi kết quả.

| Nhu cầu | Chọn cách nào? | Với `MIN_VALUE` |
| --- | --- | --- |
| Lấy trị tuyệt đối trong cùng kiểu và chấp nhận quy tắc wrap | `Math.abs` | Trả về số âm `MIN_VALUE` |
| Cần giá trị chính xác **trong cùng kiểu** hoặc báo lỗi | `Math.absExact` | Ném `ArithmeticException` |
| Đổi dấu chính xác trong cùng kiểu hoặc báo lỗi | `Math.negateExact` | Ném `ArithmeticException` |
| Cần trị tuyệt đối của mọi `int` | `Math.abs((long) x)` | Trả về `2147483648L` |
| Cần trị tuyệt đối của mọi `long` | `BigInteger.valueOf(x).abs()` | Trả về `9223372036854775808` |

Lựa chọn tùy **hợp đồng dữ liệu**: nếu kết quả ngoài miền phải bị từ chối, dùng API `Exact`. Nếu giá trị toán học vẫn hợp lệ và cần giữ đủ, chọn kiểu lưu kết quả có miền phù hợp.

## 6. Mở rộng kiểu trước khi tính: `long` và `BigInteger`

### 6.1. Tại sao ép kiểu sau `Math.abs` là quá muộn?

```java
int x = Integer.MIN_VALUE;

long wrong = (long) Math.abs(x); // -2147483648
long right = Math.abs((long) x); // 2147483648
```

- `(long) Math.abs(x)` tính `abs(int)` **trước**, khi đó kết quả đã tràn âm; ép kiểu sau không khôi phục trị tuyệt đối.
- `Math.abs((long) x)` chuyển đầu vào sang `long` **trước**, Java chọn overload `abs(long)`; `2147483648L` biểu diễn được, nên kết quả chính xác.

Tương tự, phép trừ của hai `int` có thể tràn trước khi giá trị được gán cho `long`:

```java
int min = Integer.MIN_VALUE;
int max = Integer.MAX_VALUE;

long bad = max - min;          // -1L: tràn từ bước int
long good = (long) max - min;  // 4294967295L
```

Một nguyên tắc quan trọng là **kiểu trung gian quyết định cách phép tính được thực hiện**. Không chỉ nhìn vào kiểu của biến đích.

### 6.2. `Long.MIN_VALUE` cần `BigInteger` nếu muốn trị tuyệt đối chính xác

Không có kiểu nguyên thủy Java có dấu rộng hơn `long`. Ép sang `double` cũng không phải giải pháp cho tính toán số nguyên chính xác nói chung vì `double` không biểu diễn chính xác mọi `long`.

```java
import java.math.BigInteger;

long x = Long.MIN_VALUE;
BigInteger magnitude = BigInteger.valueOf(x).abs();
System.out.println(magnitude); // 9223372036854775808
```

`BigInteger.valueOf(x)` giữ chính xác đầu vào `long`; `abs()` thực hiện trên số nguyên có độ chính xác tùy ý. Nếu cố lấy lại `long` bằng `magnitude.longValueExact()`, sẽ nhận `ArithmeticException` vì độ lớn ấy vượt `Long.MAX_VALUE`.

Với `int`, ép sang `long` là đủ cho trị tuyệt đối của **mọi** giá trị `int`. Với `long`, dùng `BigInteger` khi thực sự cần giữ kết quả ngoài miền 64 bit.

## 7. Chương trình Java chạy độc lập

Lưu nguyên chương trình thành **`MinValueDemo.java`**:

```java
import java.math.BigInteger;

public final class MinValueDemo {
    public static void main(String[] args) {
        int i = Integer.MIN_VALUE;
        long l = Long.MIN_VALUE;

        System.out.println("int range: " + i + ".." + Integer.MAX_VALUE);
        System.out.println("long range: " + l + ".." + Long.MAX_VALUE);
        System.out.println("Math.abs(int MIN): " + Math.abs(i));
        System.out.println("Math.abs(long MIN): " + Math.abs(l));
        System.out.println("Math.absExact(int MIN): " + absExactInt(i));
        System.out.println("Math.absExact(long MIN): " + absExactLong(l));
        System.out.println("Math.negateExact(int MIN): " + negateExactInt(i));
        System.out.println("Math.abs((long) int MIN): " + Math.abs((long) i));
        System.out.println("BigInteger abs(long MIN): " + BigInteger.valueOf(l).abs());
        System.out.println("int MAX + 1: " + (Integer.MAX_VALUE + 1));
        System.out.println("int MIN / -1: " + (i / -1));
        System.out.println("Integer.compare(MAX, MIN): "
                + Integer.compare(Integer.MAX_VALUE, i));
        System.out.println("Math.floorMod(int MIN, 7): " + Math.floorMod(i, 7));
        System.out.println("count int values: " + ((long) Integer.MAX_VALUE - i + 1));
        System.out.println("count long values: "
                + BigInteger.valueOf(Long.MAX_VALUE)
                    .subtract(BigInteger.valueOf(l))
                    .add(BigInteger.ONE));
    }

    private static String absExactInt(int x) {
        try {
            return Integer.toString(Math.absExact(x));
        } catch (ArithmeticException e) {
            return "ArithmeticException";
        }
    }

    private static String absExactLong(long x) {
        try {
            return Long.toString(Math.absExact(x));
        } catch (ArithmeticException e) {
            return "ArithmeticException";
        }
    }

    private static String negateExactInt(int x) {
        try {
            return Integer.toString(Math.negateExact(x));
        } catch (ArithmeticException e) {
            return "ArithmeticException";
        }
    }
}
```

Biên dịch bằng JDK hỗ trợ đích Java 15:

```bash
javac --release 15 MinValueDemo.java
java MinValueDemo
```

**Stdout chính xác**, đã đối chiếu khi thực thi trên JDK hiện đại:

```text
int range: -2147483648..2147483647
long range: -9223372036854775808..9223372036854775807
Math.abs(int MIN): -2147483648
Math.abs(long MIN): -9223372036854775808
Math.absExact(int MIN): ArithmeticException
Math.absExact(long MIN): ArithmeticException
Math.negateExact(int MIN): ArithmeticException
Math.abs((long) int MIN): 2147483648
BigInteger abs(long MIN): 9223372036854775808
int MAX + 1: -2147483648
int MIN / -1: -2147483648
Integer.compare(MAX, MIN): 1
Math.floorMod(int MIN, 7): 5
count int values: 4294967296
count long values: 18446744073709551616
```

Ba hàm helper chỉ chuyển `ArithmeticException` thành chuỗi để **minh họa đầy đủ các trường hợp mà không dừng chương trình**. Trong ứng dụng, nếu không cho phép tràn, hãy để lỗi được xử lý rõ ràng hoặc chuyển sang kiểu có thể chứa kết quả.

Giải thích ba số đáng chú ý:

- `Math.floorMod(Integer.MIN_VALUE, 7) == 5` vì phần dư âm thông thường là `-2`, còn `floorMod` với số chia dương đưa phần dư về `[0, 6]`.
- Toàn bộ miền `int` có `4294967296` giá trị, lớn hơn `Integer.MAX_VALUE`; kiểu `long` lưu được số lượng này.
- Toàn bộ miền `long` có `18446744073709551616` giá trị (`2^64`), lớn hơn `Long.MAX_VALUE`; để biểu diễn số lượng này cần `BigInteger`.

## 8. Những lỗi thực tế phải tránh

### 8.1. Comparator dựa vào phép trừ

Sai:

```java
int comparison = Integer.MAX_VALUE - Integer.MIN_VALUE;
// comparison == -1, trái với thứ tự mong muốn
```

Phép trừ có kết quả toán học `4294967295`, vượt `int` rồi thành `-1`, khiến comparator có thể đảo thứ tự và vi phạm hợp đồng sắp xếp.

Đúng:

```java
int comparison = Integer.compare(Integer.MAX_VALUE, Integer.MIN_VALUE);
// comparison == 1
```

Nếu bạn dùng `Comparator<Integer>`, có thể viết `Integer::compare` (đặt trong ngữ cảnh có `import java.util.Comparator;`). Với `long`, dùng `Long.compare(a, b)` thay vì ép kiểu `(int) (a-b)`.

### 8.2. Chọn chỉ số bucket từ hash âm

Không nên giả định `Math.abs(hash) % bucketCount` luôn không âm:

```java
int hash = Integer.MIN_VALUE;
int bucketCount = 7; // Phải > 0.

int invalid = Math.abs(hash) % bucketCount;  // -2
int index = Math.floorMod(hash, bucketCount); // 5
```

Với `bucketCount > 0`, `Math.floorMod(hash, bucketCount)` nằm trong khoảng từ `0` đến `bucketCount-1`. Đây là API hữu ích khi cần chỉ số dương, nhưng không tự bảo đảm phân phối hash tốt.

Nếu cần sinh một số ngẫu nhiên trong khoảng `[0, bound)`, thay vì `Math.abs(random.nextInt()) % bound`, hãy gọi trực tiếp API có bound như `ThreadLocalRandom.current().nextInt(bound)` (với `bound > 0`). Không dùng bộ sinh ngẫu nhiên thông thường cho mục đích bảo mật.

### 8.3. Tính hiệu và số phần tử trong toàn miền

Sai:

```java
int min = Integer.MIN_VALUE;
int max = Integer.MAX_VALUE;
long sizeWrong = max - min + 1; // 0L, vì tràn int trước khi gán
```

Đúng:

```java
long sizeInt = (long) Integer.MAX_VALUE - Integer.MIN_VALUE + 1L;
// 4294967296

BigInteger sizeLong = BigInteger.valueOf(Long.MAX_VALUE)
        .subtract(BigInteger.valueOf(Long.MIN_VALUE))
        .add(BigInteger.ONE);
// 18446744073709551616
```

Công thức `max - min + 1` là đúng về toán, nhưng **kiểu của từng phép tính trung gian** phải chứa được kết quả. Đừng ép kiểu sau một phép trừ đã tràn.

### 8.4. Vòng lặp với điều kiện `i <= MAX_VALUE`

```java
// Vòng lặp này không thể dừng do điều kiện:
for (int i = 0; i <= Integer.MAX_VALUE; i++) {
    // ...
}
```

Mọi giá trị `int` đều `<= Integer.MAX_VALUE`. Khi `i` bằng `MAX_VALUE`, `i++` wrap sang `MIN_VALUE`, nên điều kiện vẫn đúng. Muốn duyệt tới một điểm kết thúc cực đại, dùng điều kiện dừng trước khi tăng:

```java
int i = Integer.MAX_VALUE - 1;
while (true) {
    System.out.println(i);
    if (i == Integer.MAX_VALUE) {
        break;
    }
    i++;
}
```

Đoạn này in `2147483646` và `2147483647` rồi dừng. Không cố duyệt toàn bộ `2^32` giá trị nếu chỉ cần biết kích thước miền.

### 8.5. Parsing và literal gần biên

Hai phép parsing sau hợp lệ:

```java
int a = Integer.parseInt("-2147483648");
long b = Long.parseLong("-9223372036854775808");
```

Nhưng `Integer.parseInt("2147483648")` và `Long.parseLong("9223372036854775808")` ném `NumberFormatException` vì kết quả dương vượt giới hạn của kiểu tương ứng.

Java có quy tắc cú pháp đặc biệt cho hai decimal integer literals `2147483648` và `9223372036854775808L` khi đứng ngay sau toán tử trừ đơn ngôi, vì thế `-2147483648` và `-9223372036854775808L` là cú pháp hợp lệ. Không có nghĩa rằng hai số dương đó là giá trị hợp lệ của `int`/`long`. Trong mã, nên ưu tiên `Integer.MIN_VALUE` hoặc `Long.MIN_VALUE` để tránh nhầm.

## 9. Kiểm thử boundary đầy đủ

Kiểm thử chỉ `-1`, `0`, `1` và `MAX_VALUE` sẽ bỏ sót lỗi nguy hiểm nhất. Với hàm tính trị tuyệt đối, bộ ca biên tối thiểu nên gồm:

| Đầu vào `int` | `Math.abs(x)` | `Math.absExact(x)` |
| --- | --- | --- |
| `0` | `0` | `0` |
| `-1` | `1` | `1` |
| `1` | `1` | `1` |
| `Integer.MAX_VALUE` | `2147483647` | `2147483647` |
| `Integer.MIN_VALUE + 1` | `2147483647` | `2147483647` |
| `Integer.MIN_VALUE` | `-2147483648` | `ArithmeticException` |

Kiểm tra tương tự cho `long`, đặc biệt `Long.MIN_VALUE + 1` và `Long.MIN_VALUE`. Viết test so sánh giá trị chính xác hoặc ngoại lệ, không sử dụng chính `Math.abs` để "bình thường hóa" expected nếu tính đúng của `abs` là thứ bạn muốn kiểm tra.

Một đoạn kiểm thử đơn giản có thể đặt trong `main`:

```java
if (Math.abs(Integer.MIN_VALUE) >= 0) {
    throw new AssertionError("Expected negative abs result for MIN_VALUE");
}

if (Math.abs((long) Integer.MIN_VALUE) != 2147483648L) {
    throw new AssertionError("Widening before abs failed");
}

try {
    Math.absExact(Integer.MIN_VALUE);
    throw new AssertionError("Expected ArithmeticException");
} catch (ArithmeticException expected) {
    // PASS: absExact reports the overflow.
}
```

Đoạn trên là **mã bên trong một phương thức**, không phải một chương trình Java độc lập. Với JUnit hay framework kiểm thử khác, có thể dùng assertion tương đương; không cần phụ thuộc vào phiên bản framework để hiểu kiến thức nền tảng này.

## 10. Checklist chọn giải pháp

1. **Đầu vào có thể đạt `MIN_VALUE` không?** Nếu có, không giả định `-x` hoặc `Math.abs(x)` luôn không âm.
2. **Cần giá trị toán học đầy đủ hay báo lỗi?** `Math.absExact` để từ chối trường hợp ngoài miền; `Math.abs((long) x)` cho `int` nếu cần trị tuyệt đối; `BigInteger` cho `long` nếu cần đầy đủ.
3. **Ép kiểu trước phép tính:** `(long) a - b`, không phải `(long) (a - b)`.
4. **Không lấy hiệu để so sánh:** dùng `Integer.compare`/`Long.compare`.
5. **Không lấy `abs` để sinh chỉ số:** dùng `Math.floorMod(value, positiveBound)` hoặc API sinh random có bound.
6. **Không để vòng lặp tăng qua MAX_VALUE:** dừng trước khi tăng hoặc dùng kiểu đủ rộng với điều kiện có điểm kết thúc thực tế.
7. **Thu hẹp kết quả có kiểm tra:** dùng `Math.toIntExact(long)` hay `BigInteger.longValueExact()` khi phải phát hiện giá trị không nằm trong kiểu đích.
8. **Bao phủ ranh giới:** thử cả `MIN_VALUE`, `MIN_VALUE + 1`, `-1`, `0`, `1` và `MAX_VALUE`.

Các hằng `MIN_VALUE`, các phương thức `Math`, `Integer.compare`, `Math.floorMod` và `BigInteger` vẫn là công cụ thiết thực trong Java hiện hành. Trường hợp tràn này không phải hành vi lỗi thời của Java 15.

## 11. Tự kiểm tra

**Câu 1.** `Math.abs(Integer.MIN_VALUE)` có phải `2147483648` không? **Không**: kết quả là `-2147483648`, vì `2147483648` không nằm trong `int`.

**Câu 2.** `Math.absExact(Integer.MIN_VALUE)` làm gì? **Ném `ArithmeticException`**. API này xuất hiện từ Java 15 và vẫn có trong JDK hiện hành.

**Câu 3.** Làm sao nhận trị tuyệt đối chính xác của `Integer.MIN_VALUE` mà không dùng `BigInteger`? **`Math.abs((long) Integer.MIN_VALUE)`** trả `2147483648L`.

**Câu 4.** Làm sao nhận trị tuyệt đối chính xác của `Long.MIN_VALUE`? **`BigInteger.valueOf(Long.MIN_VALUE).abs()`** trả `9223372036854775808` dưới dạng `BigInteger`.

**Câu 5.** Vì sao comparator `(a, b) -> a - b` có thể sai? **Phép trừ tràn và đảo dấu**. Dùng `Integer.compare(a,b)`.

**Câu 6.** Có bao nhiêu giá trị `long` khác nhau? **`2^64 = 18446744073709551616`**; không thể cất số lượng này trong `long`, cần `BigInteger`.

**Tiêu chí đạt:** bạn giải thích được sự lệch một giá trị giữa miền âm và miền dương, dự đoán tràn ở hai kiểu, chọn cách xử lý đúng theo hợp đồng và có phép thử `MIN_VALUE` thực sự.

## 12. Nguồn chính thức

- [Java SE 15 JLS §4.2.1 – Integral Types and Values](https://docs.oracle.com/javase/specs/jls/se15/html/jls-4.html#jls-4.2.1): miền giá trị và biểu diễn bù hai của `int`/`long`.
- [Java SE 15 JLS §4.2.2 – Integer Operations](https://docs.oracle.com/javase/specs/jls/se15/html/jls-4.html#jls-4.2.2): quy tắc toán tử và tràn số nguyên.
- [Java SE 27 Javadoc: Integer](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Integer.html): `MIN_VALUE`, `MAX_VALUE` và `compare`.
- [Java SE 27 Javadoc: Long](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Long.html): miền `long` và `compare`.
- [Java SE 27 Javadoc: Math](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Math.html): `abs`, `absExact` (Since 15), `negateExact`, `floorMod`, `toIntExact`.
- [Java SE 27 Javadoc: BigInteger](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/math/BigInteger.html): `valueOf`, `abs`, `subtract`, `add` và phép chuyển có kiểm tra.

**Ghi nhớ:** với số nguyên bù hai có dấu, `MIN_VALUE` có độ lớn tuyệt đối hơn `MAX_VALUE` đúng một đơn vị. Nếu phép tính cần vượt miền, hãy dùng kiểu có thể chứa kết quả; nếu cần phát hiện thay vì âm thầm chấp nhận overflow, hãy dùng API `Exact`.