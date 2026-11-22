# Kiểm tra `MIN_VALUE`, `MAX_VALUE`, số 0 và các giá trị lân cận biên trong Java

## 1. Vì sao kiểm thử số phải tập trung vào biên?

Một đoạn mã xử lý số có thể chạy đúng với dữ liệu thông thường nhưng sai ở **giới hạn miền giá trị**: phép cộng `int` tràn, phép chia cho 0, số thực dưới ngưỡng biểu diễn thành 0, hoặc kiểm tra khoảng sử dụng `MAX_VALUE + 1`. Những lỗi này thường không xuất hiện khi chỉ thử các giá trị như 10, 20 và 50.

Đề bài “kiểm tra `MIN_VALUE`, `MAX_VALUE`, số 0 và lân cận biên” yêu cầu lập tập ca kiểm thử theo **phân vùng tương đương** (*equivalence partitioning*) và **phân tích giá trị biên** (*boundary-value analysis*). Nếu một hàm chấp nhận khoảng `[min, max]`, tối thiểu cần nghĩ đến `min`, `max`, giá trị ngay **bên trong**, ngay **bên ngoài** và các ca trung tâm/0 khi có ý nghĩa.

Đặc biệt cần phân biệt hai loại số trong Java:

- **Số nguyên kiểu nguyên thủy**: `byte`, `short`, `int`, `long` có biên hữu hạn, phép tính thông thường có thể tràn mà không ném ngoại lệ.
- **Số dấu phẩy động**: `float`, `double` có giá trị hữu hạn cực lớn, giá trị dương khác 0 nhỏ nhất, số *subnormal*, `+0.0`/`-0.0`, `NaN` và `±Infinity`. “Lân cận” phải được hiểu theo những giá trị **có thể biểu diễn** chứ không đơn giản cộng/trừ 1.

Với `BigInteger` và `BigDecimal`, miền giá trị được mở rộng tùy ý trong giới hạn tài nguyên, nhưng chuyển sang `int`, `long` và các phép kiểm tra scale/precision vẫn có ca biên.

Mục tiêu bài học: lập ma trận ca thử có hệ thống, dự đoán và kiểm chứng kết quả Java 17+, chẩn đoán lỗi tràn/thiếu chính xác, và viết test không phụ thuộc may rủi.

## 2. Quy trình thiết kế ca biên

Giả sử hàm `accept(int value)` chỉ chấp nhận `0 <= value <= 100`. Hãy bắt đầu bằng đặc tả, rồi lấy các điểm:

| Phân vùng | Giá trị | Kết quả mong đợi |
|---|---:|---|
| Ngay ngoài biên dưới | `-1` | Từ chối |
| Đúng biên dưới | `0` | Chấp nhận |
| Vừa trên biên dưới | `1` | Chấp nhận |
| Một giá trị giữa khoảng | `50` | Chấp nhận |
| Vừa dưới biên trên | `99` | Chấp nhận |
| Đúng biên trên | `100` | Chấp nhận |
| Ngay ngoài biên trên | `101` | Từ chối |

Từ ví dụ này, mở rộng thành một checklist khi làm việc với số:

1. **Loại giá trị**: số nguyên, `double`, `BigDecimal`, v.v.; cùng ký hiệu nhưng quy tắc overflow khác nhau.
2. **Miền hợp lệ**: cận dưới/trên là **bao gồm** (`>=`, `<=`) hay **không bao gồm** (`>`, `<`)? Có chấp nhận số âm, 0, số thập phân?
3. **Lân cận giá trị**: với số nguyên có thể dùng `±1` **nếu còn trong miền**; với `double` nên dùng `Math.nextUp`/`Math.nextDown`.
4. **Các trường hợp đặc biệt**: chia 0, `MIN_VALUE / -1`, `Math.abs(MIN_VALUE)`, `-0.0`, `NaN`, vô cực, subnormal.
5. **Hành vi mong đợi**: trả đúng kết quả, ném ngoại lệ, bão hòa, từ chối dữ liệu hay làm tròn theo đặc tả. Đừng chỉ kiểm tra “không crash”.
6. **Không tự tạo lỗi trong bộ test**: biểu thức `Integer.MAX_VALUE + 1` đã tràn trước khi đưa vào hàm; đó là một đầu vào âm, không phải một `int` vượt max.
7. **Kiểm thử nhiều biến**: ưu tiên những tổ hợp khiến phép tính chạm biên, ví dụ `a + b`, `a * b`, chia cho 0 hoặc chia `MIN_VALUE / -1`.

Số test càng nhiều không tự động càng tốt; hãy chọn các trường hợp có **lý do trực tiếp từ hợp đồng và loại dữ liệu**.

## 3. Biên các kiểu số nguyên nguyên thủy

| Kiểu | `MIN_VALUE` | `MAX_VALUE` | Miền |
|---|---:|---:|---|
| `byte` | `-128` | `127` | 8 bit có dấu |
| `short` | `-32768` | `32767` | 16 bit có dấu |
| `int` | `-2147483648` | `2147483647` | 32 bit có dấu |
| `long` | `-9223372036854775808` | `9223372036854775807` | 64 bit có dấu |

Với `int` có thể chia các giá trị quan trọng thành:

```text
Integer.MIN_VALUE       = -2147483648
Integer.MIN_VALUE + 1   = -2147483647
-1
0
1
Integer.MAX_VALUE - 1   =  2147483646
Integer.MAX_VALUE       =  2147483647
```

Đây là **bảy điểm kiểm tra** chính ở biên vật lý của kiểu. Nếu hàm có giới hạn nghiệp vụ khác, hãy bổ sung biên nghiệp vụ đó (ví dụ `0` và `100`). Cần đọc kỹ: `Integer.MIN_VALUE - 1` **không phải một `int` hợp lệ**; phép toán kiểu `int` sẽ tràn.

### 3.1. Tràn số `int` thường âm thầm quay vòng

Java tính toán `int` trong miền 32 bit. Nếu kết quả toán học vượt giới hạn, phép cộng/trừ/nhân nguyên thủy thông thường **không tự ném ngoại lệ**:

```java
int wrappedUp = Integer.MAX_VALUE + 1;
int wrappedDown = Integer.MIN_VALUE - 1;

System.out.println(wrappedUp);   // -2147483648
System.out.println(wrappedDown); // 2147483647
```

Không xem kết quả âm sau phép tăng là bằng chứng dữ liệu âm đã được nhập vào; chính **phép toán** có thể tạo ra giá trị ngoài ý định.

Khi yêu cầu “tính đúng hoặc báo lỗi”, dùng họ `Math.addExact`, `subtractExact`, `multiplyExact`, `incrementExact`, `decrementExact` hoặc `negateExact` tùy phép toán. Chúng ném `ArithmeticException` nếu kết quả không vừa kiểu đích.

### 3.2. Bẫy `Math.abs(Integer.MIN_VALUE)`

Miền `int` không đối xứng: trị tuyệt đối toán học của `Integer.MIN_VALUE` là `2147483648`, lớn hơn `Integer.MAX_VALUE` một đơn vị. Vì vậy:

```java
System.out.println(Math.abs(Integer.MIN_VALUE)); // -2147483648
```

Với `Math.abs(long)` cũng có vấn đề tương tự ở `Long.MIN_VALUE`. Nếu muốn kết quả trị tuyệt đối chính xác cho `int` nhưng đủ miền, có thể nâng kiểu **trước** khi tính:

```java
long magnitude = Math.abs((long) Integer.MIN_VALUE);
System.out.println(magnitude); // 2147483648
```

Với `Long.MIN_VALUE`, nâng lên `long` không giúp được vì đã ở giới hạn `long`; có thể dùng `BigInteger.valueOf(Long.MIN_VALUE).abs()` khi thực sự cần độ lớn chính xác.

### 3.3. Trường hợp `MIN_VALUE / -1`

Trong số học toán học, `-2147483648 / -1 = 2147483648`, ngoài miền `int`. Java quy định phép chia nguyên `Integer.MIN_VALUE / -1` trả `Integer.MIN_VALUE` do overflow, không báo lỗi. Với `long`, `Long.MIN_VALUE / -1L` tương tự.

Đặc biệt, phép chia nguyên với mẫu số **0** lại ném `ArithmeticException`. Do đó hai ca sau phải được kiểm tra **riêng biệt**, không gộp:

```text
MIN_VALUE / -1  -> overflow đặc biệt, không ném
anyInteger / 0  -> ArithmeticException
```

Nếu dùng Java 18+ và có nhu cầu phép chia chính xác với báo tràn, xem `Math.divideExact`. Để minh họa/test Java 17, có thể kiểm tra tường minh cặp `MIN_VALUE, -1` trước phép chia.

## 4. Ví dụ chạy được: chẩn đoán biên `int`

**Tệp `IntegralBoundaryDemo.java`:**

```java
public class IntegralBoundaryDemo {
    public static void main(String[] args) {
        System.out.println("int.min=" + Integer.MIN_VALUE);
        System.out.println("int.max=" + Integer.MAX_VALUE);

        System.out.println("wrapMax=" + (Integer.MAX_VALUE + 1));
        System.out.println("wrapMin=" + (Integer.MIN_VALUE - 1));
        System.out.println("absMin=" + Math.abs(Integer.MIN_VALUE));
        System.out.println("minDivNegOne=" + (Integer.MIN_VALUE / -1));

        try {
            System.out.println(Math.addExact(Integer.MAX_VALUE, 1));
        } catch (ArithmeticException ex) {
            System.out.println("addExact=ArithmeticException");
        }

        try {
            int impossible = Integer.MAX_VALUE / 0;
            System.out.println(impossible);
        } catch (ArithmeticException ex) {
            System.out.println("divideZero=ArithmeticException");
        }

        long magnitude = Math.abs((long) Integer.MIN_VALUE);
        System.out.println("safeAbs=" + magnitude);
    }
}
```

```bash
javac IntegralBoundaryDemo.java
java IntegralBoundaryDemo
```

Kết quả:

```text
int.min=-2147483648
int.max=2147483647
wrapMax=-2147483648
wrapMin=2147483647
absMin=-2147483648
minDivNegOne=-2147483648
addExact=ArithmeticException
divideZero=ArithmeticException
safeAbs=2147483648
```

Ví dụ đặt phép chia cho 0 trong biến `int` với mẫu số là literal `0`; Java cho phép biên dịch phép chia nguyên như vậy và chỉ ném ngoại lệ khi chạy. Hãy lưu ý rằng biểu thức `Integer.MAX_VALUE + 1` có kết quả tràn theo kiểu `int`, và việc gán về `long` **sau** phép cộng không sửa được giá trị đã tràn:

```java
long wrong = Integer.MAX_VALUE + 1;     // Đã tràn int trước khi gán
long right = (long) Integer.MAX_VALUE + 1; // Cộng ở miền long

System.out.println(wrong); // -2147483648
System.out.println(right); // 2147483648
```

## 5. Lân cận biên với số thực: khác bản chất số nguyên

`float`/`double` theo IEEE 754 biểu diễn một tập các số có mật độ không đều. Khoảng cách giữa hai giá trị biểu diễn được liên tiếp thay đổi theo độ lớn. Vì vậy **không thể tùy tiện dùng `x + 1` để tìm giá trị kế bên**.

Các trường hợp đặc biệt của `double`:

| Hằng / giá trị | Ý nghĩa |
|---|---|
| `Double.MAX_VALUE` | Số hữu hạn dương lớn nhất, khoảng `1.7976931348623157E308` |
| `-Double.MAX_VALUE` | Số hữu hạn âm nhỏ nhất về thứ tự |
| `Double.MIN_NORMAL` | Số **normal dương** nhỏ nhất, khoảng `2.2250738585072014E-308` |
| `Double.MIN_VALUE` | Số **dương khác 0 nhỏ nhất**, khoảng `4.9E-324` |
| `+0.0`, `-0.0` | Hai biểu diễn zero khác bit dấu |
| `Double.POSITIVE_INFINITY` / `NEGATIVE_INFINITY` | Giá trị vô cực |
| `Double.NaN` | Không phải số, có quy tắc so sánh đặc biệt |

**Đặc biệt dễ sai:** `Double.MIN_VALUE` **không phải** số âm hữu hạn nhỏ nhất. `Double.MIN_VALUE` là số **dương** khác 0 nhỏ nhất. Với `Float.MIN_VALUE` cũng vậy. Nếu cần kiểm tra biên âm hữu hạn, dùng `-Double.MAX_VALUE` hoặc `-Float.MAX_VALUE`.

Số **subnormal** nằm giữa 0 và `MIN_NORMAL` (về độ lớn tuyệt đối). Chúng cho phép biểu diễn những số cực nhỏ gần 0 bằng độ chính xác tương đối giảm dần. Khi phép tính tạo ra số nhỏ hơn khả năng biểu diễn, kết quả có thể underflow về 0.

### 5.1. `Math.nextUp`, `Math.nextDown` và `Math.ulp`

Để tạo các giá trị có thể biểu diễn **kề nhau**:

- `Math.nextUp(x)`: giá trị dấu phẩy động biểu diễn được liền sau theo thứ tự số học.
- `Math.nextDown(x)`: giá trị liền trước.
- `Math.nextAfter(x, direction)`: bước sang giá trị kề theo hướng `direction`.
- `Math.ulp(x)`: độ lớn một đơn vị ở vị trí thấp nhất (*unit in the last place*) tại độ lớn tương ứng của `x`.

Ví dụ:

```java
System.out.println(Math.nextUp(1.0));   // 1.0000000000000002
System.out.println(Math.nextDown(1.0)); // 0.9999999999999999
System.out.println(Math.nextUp(0.0));   // 4.9E-324
System.out.println(Math.nextDown(0.0)); // -4.9E-324
```

Khác với `+1`, các hàm này có thể tạo **sát biên biểu diễn** để kiểm tra điều kiện so sánh, thuật toán số và việc làm tròn.

### 5.2. Cẩn thận với số 0 có dấu

Theo `==`, `+0.0 == -0.0` là `true`, nhưng bit dấu khác nhau và có thể ảnh hưởng phép chia:

```java
System.out.println(1.0 / 0.0);  // Infinity
System.out.println(1.0 / -0.0); // -Infinity
```

`Double.compare(0.0, -0.0)` **không trả 0** vì `Double.compare` phân biệt signed zero trong thứ tự toàn phần của API. Nếu chỉ kiểm tra điều kiện `x == 0.0`, cả hai sẽ được xem là zero. Trong một số thuật toán, cần xác định liệu dấu zero có là một phần của hợp đồng hay không.

### 5.3. `NaN` và vô cực

`Double.NaN` không thể kiểm tra bằng `x == Double.NaN` vì mọi so sánh `==` với `NaN` đều là `false`. Dùng `Double.isNaN(x)`. Để từ chối mọi giá trị không hữu hạn, dùng `Double.isFinite(x)`.

Nếu `x` là `NaN`, cả `x < limit` lẫn `x > limit` đều `false`. Vì vậy, một validator viết chỉ bằng hai phép so sánh cận có thể vô tình **chấp nhận NaN**; kiểm tra `Double.isFinite` trước là lựa chọn rõ ràng khi miền chỉ chấp nhận số hữu hạn.

## 6. Ví dụ chạy được: số thực và lân cận biên

**Tệp `FloatingBoundaryDemo.java`:**

```java
public class FloatingBoundaryDemo {
    public static void main(String[] args) {
        System.out.println("smallestPositive=" + Double.MIN_VALUE);
        System.out.println("smallestNormal=" + Double.MIN_NORMAL);

        System.out.println("nextUpZero=" + Math.nextUp(0.0));
        System.out.println("nextDownZero=" + Math.nextDown(0.0));
        System.out.println("nextUpOne=" + Math.nextUp(1.0));
        System.out.println("nextDownOne=" + Math.nextDown(1.0));

        System.out.println("underflow=" + (Double.MIN_VALUE / 2));
        System.out.println("overflow="
                + Double.isInfinite(Double.MAX_VALUE * 2));
        System.out.println("negativeZeroSign=" + (1.0 / -0.0));

        System.out.println("zeroEqual=" + (0.0 == -0.0));
        System.out.println("nanEqual=" + (Double.NaN == Double.NaN));
        System.out.println("finiteOne=" + Double.isFinite(1.0));
        System.out.println("finiteInfinity="
                + Double.isFinite(Double.POSITIVE_INFINITY));
    }
}
```

```bash
javac FloatingBoundaryDemo.java
java FloatingBoundaryDemo
```

Kết quả:

```text
smallestPositive=4.9E-324
smallestNormal=2.2250738585072014E-308
nextUpZero=4.9E-324
nextDownZero=-4.9E-324
nextUpOne=1.0000000000000002
nextDownOne=0.9999999999999999
underflow=0.0
overflow=true
negativeZeroSign=-Infinity
zeroEqual=true
nanEqual=false
finiteOne=true
finiteInfinity=false
```

Những giá trị in ở đây theo biểu diễn `Double.toString` chuẩn của Java. `Double.MIN_VALUE / 2` bị underflow và làm tròn về `+0.0`; `Double.MAX_VALUE * 2` overflow thành `+Infinity`. Khác với chia nguyên cho 0, chia `double` cho `+0.0` hoặc `-0.0` với tử hữu hạn khác 0 thường cho vô cực có dấu theo IEEE 754; `0.0 / 0.0` cho `NaN`.

## 7. Các ca thử cần có ở biên phép chuyển đổi kiểu

Một bộ test tốt không chỉ thử dữ liệu đầu vào mà còn thử **kết quả trung gian** khi chuyển kiểu.

### 7.1. `long` sang `int`: tràn hoặc phát hiện lỗi

```java
long aboveInt = (long) Integer.MAX_VALUE + 1;
int truncated = (int) aboveInt; // -2147483648

// Math.toIntExact(aboveInt) ném ArithmeticException.
```

Ép `long` sang `int` giữ các bit thấp, nên có thể biến một số dương lớn thành số âm. Nếu chuyển đổi phải chính xác, dùng `Math.toIntExact(long)` (Java 8+).

### 7.2. `BigInteger` không có `MAX_VALUE` cố định như `long`

`BigInteger` biểu diễn số nguyên có độ lớn tùy ý trong giới hạn bộ nhớ. Có thể tạo số vượt `Long.MAX_VALUE` chính xác:

```java
BigInteger beyondLong =
        BigInteger.valueOf(Long.MAX_VALUE).add(BigInteger.ONE);

System.out.println(beyondLong); // 9223372036854775808
```

Mảnh mã trên cần import `java.math.BigInteger` và đặt trong một phương thức khi chạy. `beyondLong.longValue()` không kiểm tra mất bit; `beyondLong.longValueExact()` ném `ArithmeticException`. Ca thử nên bao gồm **giá trị cuối còn vừa miền**, và **giá trị đầu tiên vượt miền**.

### 7.3. `BigDecimal` có thể khác cách biểu diễn dù cùng số 0

`new BigDecimal("0.00")` có scale 2, còn `BigDecimal.ZERO` có scale 0:

```java
BigDecimal zero = new BigDecimal("0.00");

System.out.println(zero.signum());                 // 0
System.out.println(zero.compareTo(BigDecimal.ZERO)); // 0
System.out.println(zero.equals(BigDecimal.ZERO)); // false
```

Đây là đoạn mã minh họa với import `java.math.BigDecimal`. `signum()` và `compareTo()` kiểm tra giá trị số học; `equals()` còn xét scale. Vì vậy **test số 0 trong `BigDecimal` nên kiểm tra cả dữ liệu có trailing zeros**, tùy yêu cầu nghiệp vụ.

Khi đưa `BigDecimal` về `int`/`long`, dùng `intValueExact()`/`longValueExact()` nếu phải từ chối giá trị ngoài miền hoặc có phần lẻ. `intValue()`/`longValue()` có thể mất phần lẻ và bit cao mà không báo lỗi.

### 7.4. Không hiểu nhầm `Double.MIN_VALUE` và `Integer.MIN_VALUE`

Tên hằng giống nhau nhưng ý nghĩa khác:

- `Integer.MIN_VALUE` là cận dưới theo thứ tự số học, âm.
- `Double.MIN_VALUE` là **số dương khác 0 nhỏ nhất**, không phải cận dưới âm.
- `BigDecimal` và `BigInteger` không có cặp hằng `MIN_VALUE`/`MAX_VALUE` theo miền cố định tương tự primitive.

Do đó, không viết test tổng quát cho mọi kiểu bằng công thức “`MIN_VALUE` là số âm nhỏ nhất”; phải tra hợp đồng của từng kiểu.

## 8. Viết bộ kiểm tra ranh giới không phụ thuộc framework

Một bài test tốt cần:

1. **Đầu vào đã biết** và kết quả mong đợi lấy từ yêu cầu.
2. Đánh giá đúng ngữ nghĩa dấu, overflow và ngoại lệ.
3. Không dùng `assert` của Java nếu chưa bật `-ea`, vì assertion mặc định có thể không được thực thi; có thể dùng `AssertionError` chủ động hoặc JUnit.
4. Kiểm tra các ca vừa trong/vừa ngoài cận, kể cả 0.
5. Kiểm tra các phép chuyển kiểu và phép tính **sau khi validate**, không chỉ validate riêng.
6. Khi kiểm tra `double` cho thuật toán tính gần đúng, dùng dung sai có ý nghĩa theo độ lớn hoặc ULP; khi cần kiểm tra hành vi đúng tại giá trị kề, dùng `Math.nextUp`/`Math.nextDown` và expected cụ thể.

**Tệp `BoundaryChecks.java` — chạy độc lập Java 17+:**

```java
import java.math.BigDecimal;

public class BoundaryChecks {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static boolean inRange(int value, int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("Invalid bounds");
        }
        return value >= min && value <= max;
    }

    private static boolean isValidFiniteRatio(double value) {
        return Double.isFinite(value) && value >= 0.0 && value <= 1.0;
    }

    private static void expectArithmeticException(Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected ArithmeticException");
        } catch (ArithmeticException expected) {
            // Ca thử thành công: phép toán phải từ chối dữ liệu.
        }
    }

    public static void main(String[] args) {
        // Miền nghiệp vụ bao gồm hai đầu [0, 100].
        check(!inRange(-1, 0, 100), "below min");
        check(inRange(0, 0, 100), "at min");
        check(inRange(1, 0, 100), "above min");
        check(inRange(99, 0, 100), "below max");
        check(inRange(100, 0, 100), "at max");
        check(!inRange(101, 0, 100), "above max");

        // Biên vật lý của kiểu int.
        check(Integer.MAX_VALUE + 1 == Integer.MIN_VALUE,
                "int overflow");
        expectArithmeticException(
                () -> Math.addExact(Integer.MAX_VALUE, 1));
        expectArithmeticException(
                () -> Math.toIntExact((long) Integer.MAX_VALUE + 1));

        // Hai zero của double và giá trị kề.
        check(0.0 == -0.0, "numeric zero comparison");
        check(Double.doubleToRawLongBits(0.0)
                != Double.doubleToRawLongBits(-0.0),
                "signed zero bits");
        check(Math.nextUp(0.0) == Double.MIN_VALUE,
                "successor of zero");
        check(Math.nextDown(0.0) == -Double.MIN_VALUE,
                "predecessor of zero");
        check(!isValidFiniteRatio(Double.NaN), "NaN rejected");
        check(!isValidFiniteRatio(Double.POSITIVE_INFINITY),
                "Infinity rejected");
        check(isValidFiniteRatio(0.0), "ratio min");
        check(isValidFiniteRatio(1.0), "ratio max");
        check(!isValidFiniteRatio(Math.nextUp(1.0)),
                "ratio just above max");

        // Số thập phân zero có scale khác nhau.
        BigDecimal scaledZero = new BigDecimal("0.00");
        check(scaledZero.compareTo(BigDecimal.ZERO) == 0,
                "numeric decimal zero");
        check(!scaledZero.equals(BigDecimal.ZERO),
                "BigDecimal scale preserved");

        System.out.println("All boundary checks passed");
    }
}
```

```bash
javac BoundaryChecks.java
java BoundaryChecks
```

Kết quả:

```text
All boundary checks passed
```

`inRange` kiểm tra `min > max` để từ chối cấu hình vô nghĩa. Các so sánh trực tiếp `value >= min && value <= max` **không tính `max + 1`**, nên không tạo overflow ngoài ý muốn. Trong validator `double`, kiểm tra `Double.isFinite` trước để chủ động từ chối `NaN`/`Infinity`; ngoài biên trên được tạo bằng `Math.nextUp(1.0)`, không bằng phép cộng một epsilon tùy tiện.

Đối với dự án dùng JUnit 5, các điều kiện `check` có thể chuyển sang `assertTrue`, `assertFalse`, `assertEquals` và `assertThrows`; nội dung test vẫn là các ca biên được thiết kế từ đặc tả.

## 9. Những bẫy trong test giá trị sát biên

### 9.1. Không tự tính `MIN_VALUE - 1` hoặc `MAX_VALUE + 1` trong kiểu nguyên

Nếu cần thử “ngoài biên” của `int`, **không thể lưu số đó vào một biến `int`**. Phải thử tại ranh giới của API parse hoặc ở kiểu rộng hơn:

```java
// Parse "2147483648" thành int -> NumberFormatException.
Integer.parseInt("2147483648");

// Có thể lưu vào long để kiểm tra chuyển kiểu:
long justAboveInt = (long) Integer.MAX_VALUE + 1;
```

Dòng `Integer.parseInt` là minh họa một lời gọi **sẽ ném ngoại lệ** nếu chạy, vì vậy trong test cần bọc bằng `assertThrows`/try-catch như phần trên.

### 9.2. Không mặc định epsilon cố định đúng cho mọi `double`

`Double.MIN_VALUE` không phải một epsilon tương đối có ích cho mọi phép tính. Khoảng cách hai giá trị `double` kề nhau gần `1.0` xấp xỉ `2.220446049250313E-16`, nhưng gần `1E20` khoảng cách lớn hơn nhiều. Kiểm tra sai số cần xác định **dung sai tuyệt đối/ tương đối** theo bài toán; khi kiểm tra bit/cấu trúc số biểu diễn được, dùng `Math.ulp` và `Math.nextUp/Down`.

### 9.3. Không dùng `==` làm tiêu chí gần đúng một cách máy móc

```java
System.out.println((0.1 + 0.2) == 0.3); // false
```

Đây là hệ quả biểu diễn nhị phân, không phải bằng chứng Java thực hiện sai số học. Kiểm thử số gần đúng nên có tolerance rõ; ngược lại, với các trường hợp API quy định chính xác như signed-zero bits, `nextUp(0.0) == Double.MIN_VALUE`, kiểm tra chính xác hoàn toàn phù hợp.

### 9.4. Chẩn đoán bằng bit và loại dữ liệu

Khi điều tra sự khác biệt giữa `+0.0` và `-0.0`, `==` không đủ. Dùng `Double.doubleToRawLongBits` để quan sát biểu diễn dấu; đối với `NaN`, dùng `Double.isNaN` và cân nhắc quy tắc normalize NaN payload ở từng API. Với `BigDecimal`, in `toPlainString()`, `scale()`, `precision()` và `unscaledValue()` để hiểu tại sao hai giá trị bằng nhau theo `compareTo` mà khác `equals`.

Các thông tin chẩn đoán nên bao gồm kiểu dữ liệu, nguồn giá trị và phép biến đổi đã tạo ra kết quả, đặc biệt khi phát hiện overflow hoặc underflow. Không kết luận từ cách Java in số thập phân rằng toàn bộ chữ số đó tồn tại chính xác trong `double`.

## 10. Ma trận kiểm tra nhanh theo loại dữ liệu

| Loại giá trị | Biên và lân cận cần thử | Rủi ro điển hình |
|---|---|---|
| `byte`, `short` | MIN, MIN+1, -1, 0, 1, MAX-1, MAX | Promotion lên `int`, ép hẹp mất bit |
| `int`, `long` | MIN, MIN+1, -1, 0, 1, MAX-1, MAX | Tràn cộng/nhân, `abs(MIN)`, chia `MIN / -1` |
| Chia nguyên | mẫu số -1, 0, 1; tử 0, MIN, MAX | Chia 0 ném lỗi, tràn `MIN/-1` |
| `float`, `double` | ±MAX_VALUE, ±MIN_NORMAL, ±MIN_VALUE, ±0.0, ±Infinity, NaN | Overflow, underflow, signed zero, so sánh NaN |
| Giá trị `double` ngay sát cận | `Math.nextDown(bound)`, `bound`, `Math.nextUp(bound)` | Cộng một “epsilon” không đúng độ lớn |
| `BigDecimal` | 0, 0.00, số sát ngưỡng quy định, scale khác nhau | Nhầm `equals` với `compareTo`, rounding |
| `BigInteger` | Vượt cận `int`/`long` ±1, giá trị âm cực lớn | `intValue`/`longValue` mất bit |

Không nhất thiết mọi lớp/hàm đều cần toàn bộ ma trận. Chọn ca từ **kiểu input, thao tác đang dùng và quy tắc nghiệp vụ cụ thể**. Tuy nhiên, nếu phương thức có các phép cộng, nhân, chia, ép kiểu hoặc so sánh cận, các vùng biên tương ứng gần như luôn đáng được kiểm tra.

## 11. Bài tập có lời giải

1. **`Integer.MAX_VALUE + 1` trả gì?**  
   `-2147483648`, vì overflow kiểu `int`. `Math.addExact(Integer.MAX_VALUE, 1)` thì ném `ArithmeticException`.

2. **`Math.abs(Integer.MIN_VALUE)` có dương không?**  
   Không, kết quả vẫn là `-2147483648`. Cần nâng sang `long` trước khi gọi `Math.abs` nếu cần độ lớn chính xác.

3. **`Double.MIN_VALUE` có phải số thực âm nhỏ nhất không?**  
   Không. Đây là giá trị `double` **dương khác 0 nhỏ nhất**. Cận hữu hạn âm là `-Double.MAX_VALUE`.

4. **Giá trị `double` biểu diễn được ngay trên `1.0` là gì?**  
   `Math.nextUp(1.0)`, thường được in `1.0000000000000002`.

5. **`+0.0 == -0.0` trả gì? Hai giá trị có hoàn toàn đồng nhất ở mọi phép toán không?**  
   Trả `true`, nhưng bit dấu khác nhau và `1.0 / +0.0` trả `Infinity` còn `1.0 / -0.0` trả `-Infinity`.

6. **Vì sao chỉ dùng `x < 0 || x > 1` để từ chối tỷ lệ không hợp lệ là chưa đủ?**  
   Vì với `NaN`, cả hai so sánh đều `false`. Cần `Double.isFinite(x)` nếu chỉ chấp nhận số hữu hạn.

7. **Tại sao `BigDecimal("0.00").equals(BigDecimal.ZERO)` là `false`, trong khi `compareTo` trả `0`?**  
   Hai số có cùng giá trị số học 0 nhưng khác scale; `equals` xét thêm scale, `compareTo` chỉ xét giá trị.

8. **`Long.MAX_VALUE + 1` có phải đầu vào `long` lớn hơn `Long.MAX_VALUE` để test hàm không?**  
   Không. Biểu thức đã overflow về `Long.MIN_VALUE`. Muốn mô tả số toán học nằm ngoài miền `long`, dùng `BigInteger` hoặc chuỗi đầu vào và kiểm tra phương thức parse/conversion.

## 12. Ghi nhớ và tài liệu tham khảo

Kiểm thử số cần kiểm tra **đúng ba lớp biên**: **biên kiểu dữ liệu**, **biên phép toán**, và **biên nghiệp vụ**. Đối với số nguyên, thử MIN/MAX/0 và điểm kề bằng phép toán không tự overflow; đối với `double`, thử zero có dấu, MIN_VALUE dương, MIN_NORMAL, ±MAX_VALUE, NaN/vô cực và dùng `Math.nextUp`/`Math.nextDown` để tạo giá trị sát biên. Kỳ vọng của mỗi ca phải bám hợp đồng phương thức, không dựa vào cảm giác về số học thông thường.

Tài liệu chính thức Java 21 (các API chính dùng được trên Java 17 trừ khi Javadoc ghi khác):

- [`Integer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html)
- [`Long`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Long.html)
- [`Double`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html)
- [`Math`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html)
- [`BigDecimal`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
- [`BigInteger`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigInteger.html)
