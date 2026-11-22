# ArithmeticException thay cho kết quả cuộn vòng trong số học kiểm tra tràn Java

## Mục tiêu bài học

Khi thực hiện phép toán trên số nguyên `int` hoặc `long`, Java **không tự động ném ngoại lệ** nếu phép cộng, trừ, nhân, tăng, giảm hoặc đổi dấu vượt khỏi khoảng biểu diễn. Kết quả có thể **cuộn vòng** (*wrap around*) sang một giá trị dương/âm khác. Điều này hợp lệ theo quy tắc ngôn ngữ, nhưng nguy hiểm nếu chương trình dùng kết quả làm số tiền, số lượng tồn kho, kích thước mảng, số thứ tự giao dịch hoặc bộ đếm.

Java cung cấp các phương thức **checked arithmetic** như `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, `Math.incrementExact`, `Math.decrementExact`, `Math.negateExact` và `Math.toIntExact`. Chúng **trả kết quả chính xác khi biểu diễn được trong kiểu đích** và **ném `ArithmeticException` khi phép toán vượt giới hạn kiểu số nguyên**, thay vì âm thầm trả một số đã cuộn vòng.

Sau bài học, bạn sẽ biết:

1. Giải thích giới hạn `int`/`long` và vì sao các toán tử bình thường có thể wrap mà không ném lỗi.
2. Phân biệt `Math.*Exact` với các toán tử `+`, `-`, `*`, `++`, `--` và phép ép kiểu `(int)`.
3. Nhận diện chính xác những phép tính ném `ArithmeticException` và những phép tính vẫn cho kết quả hợp lệ.
4. Sử dụng `Math.toIntExact` khi thu hẹp `long` về `int`; không tạo overflow trước khi mở rộng kiểu.
5. Xử lý ngoại lệ tại ranh giới nghiệp vụ, tránh tiếp tục với dữ liệu sai hoặc sửa lỗi bằng giá trị mặc định thiếu căn cứ.
6. Phân biệt **overflow của số nguyên** với **chia cho 0**, **float/double Infinity**, phép chia `MIN_VALUE / -1` và phép toán trên `BigInteger`.
7. Biên dịch/chạy một chương trình Java 17+ hoàn chỉnh, có stdout xác định và các ca biên được kiểm tra bằng ngoại lệ thật.

**Phạm vi hiện hành:** Những phương thức `Math.*Exact` chủ yếu đã có từ Java 8; `Math.absExact` được bổ sung từ Java 15; Java 14 cũng có các phương thức exact tương ứng trong `StrictMath`. Tất cả vẫn được hỗ trợ trên JDK hiện đại. Ví dụ dùng **JDK 17 trở lên**, không cần `--enable-preview` và không dựa vào những API đã bị thay thế.

## 1. Tại sao toán tử số nguyên thường không báo overflow?

### Giới hạn của hai kiểu

| Kiểu Java | Số bit | Giá trị nhỏ nhất | Giá trị lớn nhất |
| --- | ---: | ---: | ---: |
| `int` | 32 | `-2_147_483_648` | `2_147_483_647` |
| `long` | 64 | `-9_223_372_036_854_775_808L` | `9_223_372_036_854_775_807L` |

Java biểu diễn các kiểu số nguyên có dấu này theo **two's complement**. Khi kết quả của phép cộng, trừ hoặc nhân không vừa kiểu kết quả, các bit cao không thể biểu diễn bị loại, dẫn tới kết quả được xác định bởi các bit thấp. **Không có `ArithmeticException` cho overflow của các toán tử số học `+`, `-`, `*` thông thường.**

Ví dụ:

```java
int max = Integer.MAX_VALUE;
int wrapped = max + 1;
System.out.println(wrapped); // -2147483648
```

Đây không phải phép cộng toán học `2_147_483_647 + 1 = -2_147_483_648`. Kết quả đúng về toán học là `2_147_483_648`, nhưng **không vừa trong `int`**; toán tử `+` trên `int` chỉ giữ bit phù hợp và wrap.

Thử nhân:

```java
int a = 50_000;
int b = 50_000;

int wrapped = a * b;
System.out.println(wrapped); // -1794967296
```

Tích đúng toán học là `2_500_000_000`, vượt quá `Integer.MAX_VALUE`. Nếu dùng số đã wrap làm hạn mức hoặc doanh thu, lỗi có thể lan tới các bước sau.

### Vùng số âm không đối xứng

`int` có **một giá trị âm nhiều hơn số dương**. Vì vậy giá trị đối của `Integer.MIN_VALUE` là `2_147_483_648`, cũng không vừa trong `int`.

```java
int min = Integer.MIN_VALUE;

System.out.println(-min);          // -2147483648 (wrap)
System.out.println(Math.abs(min)); // -2147483648
```

`Math.abs(int)` **không ném lỗi** ở trường hợp `Integer.MIN_VALUE`. Nếu cần kết quả trị tuyệt đối có đảm bảo không overflow, dùng `Math.absExact(int)` trên JDK 17+.

### Đó là quy tắc ngôn ngữ, không phải bug JVM

Java Language Specification định nghĩa rõ số học số nguyên wrap ở trường hợp overflow của các toán tử liên quan. Vì vậy JIT tối ưu hóa chương trình **vẫn phải giữ đúng semantics**, không được thay quy tắc thành “đôi khi ném exception”.

Khi nghiệp vụ yêu cầu phát hiện overflow, bạn phải **chọn phép toán checked** hoặc sử dụng một kiểu dữ liệu đủ rộng hơn, chứ không mong JVM tự thay `+` thành kiểm tra tràn.

## 2. Exact methods thay đổi điều gì?

So sánh hai đoạn:

```java
int x = Integer.MAX_VALUE;
int bad = x + 1;               // -2147483648, không ném exception
```

```java
int x = Integer.MAX_VALUE;
int sum = Math.addExact(x, 1); // Ném ArithmeticException
```

`Math.addExact` yêu cầu kết quả toán học phải **vừa trong kiểu kết quả**. Nếu vừa, nó trả đúng số nguyên; nếu không, ném `ArithmeticException`, một subclass của `RuntimeException`.

Chương trình **không cần khai báo `throws ArithmeticException`** để dùng phương thức exact, vì đây là ngoại lệ unchecked. Tuy nhiên, bạn cần xác định chính sách ứng dụng: liệu overflow là lỗi dữ liệu, lỗi thiết kế giới hạn miền giá trị, sự cố nghiêm trọng cần dừng giao dịch hay một điều kiện có thể xử lý bằng cách chọn kiểu lớn hơn?

Một so sánh thực tế:

| Phép tính | Dạng thông thường | Dạng checked | Khi overflow |
| --- | --- | --- | --- |
| Cộng | `a + b` | `Math.addExact(a, b)` | Checked ném `ArithmeticException` |
| Trừ | `a - b` | `Math.subtractExact(a, b)` | Checked ném `ArithmeticException` |
| Nhân | `a * b` | `Math.multiplyExact(a, b)` | Checked ném `ArithmeticException` |
| Tăng 1 | `a++`, `++a` | `Math.incrementExact(a)` | Checked ném `ArithmeticException` |
| Giảm 1 | `a--`, `--a` | `Math.decrementExact(a)` | Checked ném `ArithmeticException` |
| Đổi dấu | `-a` | `Math.negateExact(a)` | Checked ném `ArithmeticException` |
| Trị tuyệt đối | `Math.abs(a)` | `Math.absExact(a)` | Checked ném với `MIN_VALUE` |
| Thu hẹp long → int | `(int) x` | `Math.toIntExact(x)` | Checked ném nếu long không vừa int |

**Không nhầm:** `Math.multiplyExact` có các overload cho `int,int` và `long,long` (cũng có `long,int`). Kiểu trả về phụ thuộc overload được chọn khi biên dịch. Một phép `Math.multiplyExact(int,int)` không “tự trả long” để tránh overflow; nó **ném lỗi nếu tích không vừa int**.

## 3. Các API quan trọng và ví dụ biên

### 3.1. Cộng: addExact

```java
int answer = Math.addExact(40, 2); // 42

Math.addExact(Integer.MAX_VALUE, 1); // ArithmeticException
Math.addExact(Long.MAX_VALUE, 1L);   // ArithmeticException
```

Hai dòng gọi với MAX là **đoạn minh họa cố ý gây exception**; trong chương trình thực tế, cần để lỗi truyền lên hoặc bắt tại ranh giới có trách nhiệm, không tiếp tục giả định có kết quả.

### 3.2. Trừ: subtractExact

```java
int balance = Math.subtractExact(50, 8); // 42

Math.subtractExact(Integer.MIN_VALUE, 1);
Math.subtractExact(Long.MIN_VALUE, 1L);
```

Khi trừ `1` khỏi MIN, kết quả đúng nằm ngoài khoảng âm của kiểu nên ném `ArithmeticException`. Với `a - b` thông thường, giá trị có thể wrap lên MAX mà không báo lỗi.

### 3.3. Nhân: multiplyExact

```java
int small = Math.multiplyExact(7, 6); // 42

Math.multiplyExact(50_000, 50_000);       // int overflow
Math.multiplyExact(Long.MAX_VALUE, 2L);   // long overflow
```

Nếu muốn nhận `2_500_000_000` trong `long`, hãy **mở rộng operand trước khi thực hiện phép nhân**:

```java
int a = 50_000;
int b = 50_000;

long correct = Math.multiplyExact((long) a, b);
// correct == 2_500_000_000L
```

Lệnh `Math.multiplyExact((long) a, b)` chọn overload trả `long`. Nó chỉ ném nếu tích **không vừa long**.

### 3.4. Tăng/giảm chính xác

```java
int next = Math.incrementExact(41); // 42
int previous = Math.decrementExact(43); // 42

Math.incrementExact(Integer.MAX_VALUE); // exception
Math.decrementExact(Integer.MIN_VALUE); // exception
```

Nếu bạn cần kiểm tra bộ đếm `counter` trước khi cập nhật, viết:

```java
counter = Math.incrementExact(counter);
```

Dòng này là **mã minh họa bên trong một method**, giả sử `counter` là biến `int` đã khai báo. Java đánh giá biểu thức bên phải **trước** phép gán. Nếu `incrementExact` ném exception, câu lệnh này không gán một giá trị wrap vào `counter`.

Không suy rộng thành “mọi trạng thái ứng dụng vẫn nguyên vẹn”: nếu các lệnh trước đó đã thay đổi dữ liệu hoặc gọi dịch vụ bên ngoài, exception không tự rollback những thay đổi ấy. Cần xử lý transaction theo nghiệp vụ.

### 3.5. Đổi dấu: negateExact

```java
int opposite = Math.negateExact(-42); // 42

Math.negateExact(Integer.MIN_VALUE); // ArithmeticException
Math.negateExact(Long.MIN_VALUE);    // ArithmeticException
```

Không nhầm với toán tử `-Integer.MIN_VALUE`: toán tử thường cho kết quả cuộn vòng là chính `Integer.MIN_VALUE`.

### 3.6. Trị tuyệt đối: absExact

`Math.absExact(int)` và `Math.absExact(long)` đã có từ **Java 15**, vì vậy dùng được khi biên dịch với `--release 17`. Các method này ném `ArithmeticException` nếu đầu vào là giá trị MIN của kiểu.

```java
int d = Math.absExact(-42); // 42

Math.absExact(Integer.MIN_VALUE); // ArithmeticException
Math.absExact(Long.MIN_VALUE);    // ArithmeticException
```

Trái lại, `Math.abs(Integer.MIN_VALUE)` trả lại số âm MIN; kiểm tra `Math.abs(x) >= 0` không đúng với mọi `int`.

### 3.7. Thu hẹp giá trị: toIntExact

Ép kiểu long xuống int bằng cast có thể **bỏ các bit cao**, không tự kiểm tra:

```java
long large = (long) Integer.MAX_VALUE + 1L;
int wrapped = (int) large; // -2147483648
```

Dùng:

```java
long large = (long) Integer.MAX_VALUE + 1L;
int number = Math.toIntExact(large); // ArithmeticException
```

Đây là trường hợp khác với overflow trong `Math.addExact`: phép cộng `long` hoàn toàn hợp lệ, nhưng **kết quả không vừa kiểu đích `int`**.

Nếu chuyển `BigInteger` sang kiểu primitive, có các method riêng như `intValueExact()`/`longValueExact()`, cũng kiểm tra có thể biểu diễn chính xác. Đừng dùng `intValue()` rồi hy vọng JVM báo overflow; method đó có thể mất thông tin khi narrowing.

## 4. Chương trình hoàn chỉnh chạy bằng Java 17 trở lên

Tạo file **`CheckedArithmeticDemo.java`**. Chương trình cố tình làm cả phép toán wrap và checked; mỗi ca dự kiến ném exception được bọc trong một hàm kiểm thử, để stdout không phụ thuộc câu chữ JVM dùng trong `ArithmeticException.getMessage()`.

```java
import java.math.BigInteger;

public final class CheckedArithmeticDemo {
    private CheckedArithmeticDemo() {
    }

    private static void expectArithmetic(
            String label, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError(
                    "Expected ArithmeticException: " + label);
        } catch (ArithmeticException expected) {
            System.out.println(label + "=ArithmeticException");
        }
    }

    private static int divideExactOn17(int a, int b) {
        if (b == 0) {
            throw new ArithmeticException("division by zero");
        }
        if (a == Integer.MIN_VALUE && b == -1) {
            throw new ArithmeticException("int division overflow");
        }
        return a / b;
    }

    private static long itemTotalCents(
            long unitPriceCents, int quantity) {
        if (unitPriceCents < 0 || quantity < 0) {
            throw new IllegalArgumentException(
                    "price and quantity must not be negative");
        }
        return Math.multiplyExact(unitPriceCents, (long) quantity);
    }

    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;
        int min = Integer.MIN_VALUE;

        System.out.println("wrapAdd=" + (max + 1));
        System.out.println("wrapMultiply=" + (50_000 * 50_000));
        System.out.println("wrapNegate=" + (-min));
        System.out.println("wrapToInt="
                + (int) ((long) max + 1L));
        System.out.println("wrapDivideMin=" + (min / -1));

        System.out.println("safeAdd=" + Math.addExact(40, 2));
        System.out.println("safeSubtract=" + Math.subtractExact(50, 8));
        System.out.println("safeMultiply=" + Math.multiplyExact(7, 6));
        System.out.println("safeIncrement=" + Math.incrementExact(41));
        System.out.println("safeDecrement=" + Math.decrementExact(43));
        System.out.println("safeNegate=" + Math.negateExact(-42));
        System.out.println("safeAbs=" + Math.absExact(-42));
        System.out.println("safeToInt=" + Math.toIntExact(42L));
        System.out.println("widenBeforeMultiply="
                + Math.multiplyExact((long) 50_000, 50_000));
        System.out.println("itemTotalCents="
                + itemTotalCents(199L, 3));
        System.out.println("bigInteger="
                + BigInteger.valueOf(Long.MAX_VALUE)
                        .add(BigInteger.ONE));

        expectArithmetic("addOverflow",
                () -> Math.addExact(max, 1));
        expectArithmetic("subtractOverflow",
                () -> Math.subtractExact(min, 1));
        expectArithmetic("multiplyOverflow",
                () -> Math.multiplyExact(50_000, 50_000));
        expectArithmetic("incrementOverflow",
                () -> Math.incrementExact(max));
        expectArithmetic("decrementOverflow",
                () -> Math.decrementExact(min));
        expectArithmetic("negateOverflow",
                () -> Math.negateExact(min));
        expectArithmetic("absOverflow",
                () -> Math.absExact(min));
        expectArithmetic("longAddOverflow",
                () -> Math.addExact(Long.MAX_VALUE, 1L));
        expectArithmetic("toIntOverflow",
                () -> Math.toIntExact((long) max + 1L));
        expectArithmetic("divideMinOverflow",
                () -> divideExactOn17(min, -1));
        expectArithmetic("divideZero",
                () -> divideExactOn17(1, 0));
    }
}
```

### Lệnh biên dịch và chạy

Mở terminal trong thư mục chứa tệp nguồn, dùng JDK 17+:

```bash
javac --release 17 CheckedArithmeticDemo.java
java CheckedArithmeticDemo
```

**Stdout mong đợi chính xác:**

```text
wrapAdd=-2147483648
wrapMultiply=-1794967296
wrapNegate=-2147483648
wrapToInt=-2147483648
wrapDivideMin=-2147483648
safeAdd=42
safeSubtract=42
safeMultiply=42
safeIncrement=42
safeDecrement=42
safeNegate=42
safeAbs=42
safeToInt=42
widenBeforeMultiply=2500000000
itemTotalCents=597
bigInteger=9223372036854775808
addOverflow=ArithmeticException
subtractOverflow=ArithmeticException
multiplyOverflow=ArithmeticException
incrementOverflow=ArithmeticException
decrementOverflow=ArithmeticException
negateOverflow=ArithmeticException
absOverflow=ArithmeticException
longAddOverflow=ArithmeticException
toIntOverflow=ArithmeticException
divideMinOverflow=ArithmeticException
divideZero=ArithmeticException
```

Kết quả trong ví dụ không phụ thuộc thời gian, hệ điều hành, số ngẫu nhiên hay một thông điệp exception được cài đặt riêng. Các phép toán overflow có quy tắc xác định theo Java; chương trình chỉ in **loại ngoại lệ** chứ không so sánh `getMessage()` với một chuỗi chưa được bảo đảm.

### Giải thích các nhóm dòng

**Nhóm `wrap...`** minh họa năm trường hợp toán tử hoặc cast thông thường không báo tràn:

- `max + 1` chuyển từ số dương lớn nhất sang `Integer.MIN_VALUE`.
- `50_000 * 50_000` cho giá trị âm `-1_794_967_296` thay vì tích toán học `2_500_000_000`.
- `-min` vẫn cho `min` do số dương tương ứng không thể biểu diễn.
- `(int) ((long) max + 1L)` bỏ phần dữ liệu không vừa int khi narrowing.
- `min / -1` là trường hợp ngoại lệ của chia số nguyên: phép chia tràn nhưng toán tử thường **trả lại `min`**, không ném exception.

**Nhóm `safe...`** cho thấy mỗi `Math.*Exact` trả đúng `42` khi kết quả vừa trong kiểu. Cả `safeToInt=42` và `widenBeforeMultiply=2500000000` giải thích sự khác nhau giữa **chuyển kiểu được kiểm tra** và **mở rộng operand trước khi nhân**.

**`itemTotalCents`** mô phỏng tổng tiền của một dòng hàng (giá đơn vị tính bằng cent, số lượng). Hàm từ chối đầu vào âm theo contract nghiệp vụ và dùng `Math.multiplyExact` để từ chối tích vượt `long`. Không sử dụng `double` cho phép tính tiền nguyên cent.

**`bigInteger`** dùng kiểu nguyên độ chính xác tùy ý khi phạm vi `long` không đủ: `Long.MAX_VALUE + 1` được biểu diễn thành `9223372036854775808` thay vì wrap hoặc phải bỏ phép toán.

**Nhóm `...Overflow`** xác nhận ngoại lệ thực sự được ném. `expectArithmetic` sẽ ném `AssertionError` nếu một phép toán đáng ra tràn lại **không ném**; nhờ vậy output không thể đánh dấu giả là thành công.

## 5. Phép chia là trường hợp cần quan sát riêng

### 5.1. Chia cho 0 vốn đã ném ArithmeticException

Ngay cả khi không có `Math.*Exact`:

```java
int a = 10;
int zero = 0;
int result = a / zero; // ArithmeticException: / by zero
```

Tương tự, chia nguyên `long` cho 0 sẽ ném `ArithmeticException`. Vì vậy **không phải mọi `ArithmeticException` đều do overflow**. Loại exception này có thể biểu diễn nhiều điều kiện số học bất thường.

### 5.2. Nhưng MIN_VALUE / -1 lại không ném trong toán tử thông thường

Đối với `int`:

```java
int min = Integer.MIN_VALUE;
int result = min / -1;
// result == Integer.MIN_VALUE; không ném ArithmeticException.
```

Kết quả đúng toán học là `2_147_483_648`, không vừa `int`. Java định nghĩa trường hợp này trả lại dividend. `long` cũng có trường hợp tương ứng với `Long.MIN_VALUE / -1L`.

Nếu dùng **Java 17**, có thể kiểm tra trực tiếp:

```java
static int divideExactOn17(int a, int b) {
    if (b == 0) {
        throw new ArithmeticException("division by zero");
    }
    if (a == Integer.MIN_VALUE && b == -1) {
        throw new ArithmeticException("int division overflow");
    }
    return a / b;
}
```

Đây là **method minh họa đặt trong một class**; chương trình ở mục 4 đã bao gồm phiên bản chạy được.

### 5.3. API trên JDK mới hơn

Các phương thức **`Math.divideExact(int,int)` và `Math.divideExact(long,long)` được bổ sung từ Java 18**. Do đó:

- Trên **JDK 18 trở lên**, `Math.divideExact(a, b)` có thể thay phần kiểm tra thủ công cho phép chia, ném `ArithmeticException` khi quotient tràn hoặc chia cho 0.
- Trên **JDK 17**, **không dùng `Math.divideExact` trong mã biên dịch `--release 17`**, vì API đó chưa tồn tại ở mức release tương ứng.
- `Math.floorDiv` và toán tử `/` không phải những phương thức phát hiện overflow thay thế `divideExact`.

Khi thực hiện phép chia trong hệ thống tương thích nhiều phiên bản Java, hãy xác định baseline JDK trước khi chọn API.

## 6. Overflow có thể xảy ra trước khi bạn ép kiểu lên long

Lỗi phổ biến:

```java
int price = 50_000;
int quantity = 50_000;

long wrong = price * quantity;
// wrong == -1794967296L, vì phép nhân int đã tràn trước phép gán.
```

Java chọn kiểu kết quả của `price * quantity` từ **kiểu hai operand**, không dựa vào biến đích `wrong`. Phép nhân hai `int` đã wrap rồi mới được chuyển thành `long`, nên chuyển kiểu sau đó **không phục hồi được thông tin đã mất**.

Cách đúng:

```java
long correct = (long) price * quantity;
// correct == 2_500_000_000L

long checked = Math.multiplyExact((long) price, quantity);
// checked == 2_500_000_000L; vẫn kiểm tra giới hạn long.
```

**Nhưng mở rộng lên long không phải lá chắn vô hạn.** Nếu tích lớn hơn `Long.MAX_VALUE`, cả phép nhân thường trên long cũng có thể wrap, trong khi `Math.multiplyExact(long,long)` sẽ ném `ArithmeticException`.

### Một phép toán đã wrap trước khi gọi exact vẫn không được phát hiện

Ví dụ sai:

```java
int a = Integer.MAX_VALUE;
int b = 1;

int alreadyWrong = a + b; // wrap thành Integer.MIN_VALUE
int result = Math.addExact(alreadyWrong, 0);
// Không ném: đây là phép cộng hợp lệ của số ĐÃ SAI với 0.
```

Cách đúng:

```java
int result = Math.addExact(a, b); // Ném ngay tại bước gây overflow.
```

Quy tắc: **mọi bước trung gian có thể tràn cần được kiểm tra trước khi dữ liệu sai đi vào bước sau**. `Math.*Exact` không thể nhìn lại lịch sử để biết một operand đã bị tính sai ở đâu.

## 7. Xử lý ArithmeticException ở ranh giới nghiệp vụ

### Ném ra ngoài thay vì dùng giá trị wrap

Giả sử ứng dụng tính tổng tiền một giỏ hàng từ các dòng giá/số lượng, dùng `long` đại diện cho cent:

```java
long totalCents = 0L;

for (OrderLine line : lines) {
    long subtotal = Math.multiplyExact(
            line.unitPriceCents(), (long) line.quantity());
    totalCents = Math.addExact(totalCents, subtotal);
}
```

Đây là **mã minh họa**, giả định `OrderLine` có hai accessor nêu trên và `lines` là tập các dòng đã được kiểm tra đầu vào. Trong ứng dụng thật, cần kiểm tra đơn giá/số lượng có âm hay không, giới hạn nghiệp vụ, quyền thay đổi giá và chính sách tiền tệ.

Nếu tổng vượt giới hạn long, chương trình ném `ArithmeticException` thay vì cập nhật tổng bằng số âm hoặc số nhỏ không hợp lệ.

**Nên phân tách hai trách nhiệm:**

- **Tầng tính toán:** ném `ArithmeticException` khi số học không thể biểu diễn đúng.
- **Tầng nghiệp vụ/API:** quyết định cách trả lỗi cho người gọi, ví dụ “amount exceeds supported range”, từ chối transaction hoặc yêu cầu điều chỉnh dữ liệu.

Không cần bắt rồi tiếp tục bằng `0`, `Integer.MAX_VALUE` hoặc một giá trị giả khác nếu contract không hề cho phép cách làm đó.

### Giữ trạng thái nhất quán

Một phép:

```java
currentBalance = Math.addExact(currentBalance, delta);
```

không gán kết quả mới vào biến khi `addExact` ném. Tuy nhiên, nếu bạn đã lưu nhiều bản ghi, trừ tiền, phát sự kiện hoặc ghi database trước đó, **`ArithmeticException` không tự rollback** các side effect cũ.

Trong ứng dụng xử lý nhiều bước, tính **toàn bộ kết quả cần thiết vào biến cục bộ**, kiểm tra được phép commit, rồi thực hiện cập nhật theo một transaction khi phù hợp.

Ví dụ dạng đơn giản:

```java
long newSubtotal = Math.multiplyExact(price, quantity);
long newTotal = Math.addExact(currentTotal, newSubtotal);
// Chỉ sau khi hai bước thành công mới commit kết quả.
currentTotal = newTotal;
```

Đoạn này là ví dụ trong method đã khai báo `price`, `quantity` và `currentTotal`. Việc kiểm tra overflow không thay cho bảo vệ concurrency hoặc transaction ở database.

### Đọc đúng loại exception

`ArithmeticException` còn có thể xuất hiện do chia cho 0 hoặc các API số học khác. Ví dụ `BigDecimal.divide` không cung cấp rounding policy có thể ném khi kết quả thập phân không kết thúc. Do đó không nên bắt rộng mọi `ArithmeticException` rồi luôn báo người dùng “overflow”.

Hãy bắt exception ở **đoạn phép toán cụ thể** có thể tràn, hoặc dùng validation rõ ràng để gắn ngữ cảnh. Không so sánh message ngoại lệ với câu chữ mặc định của JVM: thông điệp không phải API nghiệp vụ ổn định.

## 8. Kiểm tra overflow khi cập nhật counter nhiều thread

Một bộ đếm `AtomicInteger` có phương thức:

```java
counter.getAndIncrement();
```

Đây là phép tăng atomic, nhưng **không có nghĩa được kiểm tra overflow**; counter `int` vẫn có thể wrap. Từ “atomic” liên quan concurrency, còn “exact” liên quan tính biểu diễn của phép toán, là hai thuộc tính riêng.

Nếu cần cả hai:

```java
java.util.concurrent.atomic.AtomicInteger counter =
        new java.util.concurrent.atomic.AtomicInteger();

int updated = counter.updateAndGet(Math::incrementExact);
```

`updateAndGet` gọi hàm cập nhật trong vòng CAS khi cần; `Math::incrementExact` là hàm không side effect, ném `ArithmeticException` nếu `int` tại thời điểm cập nhật bằng MAX.

**Cẩn thận:** Hàm đưa vào `updateAndGet` có thể được gọi **nhiều lần do tranh chấp**. Đừng gửi email, trừ tiền, ghi database hoặc tạo side effect không thể rollback bên trong lambda. Số học kiểm tra tràn không thay thế thiết kế concurrency.

Đối với một sequence ID hoặc số lượt truy cập có thể tăng rất lâu, hãy cân nhắc kiểu `long`, miền giới hạn thực tế, chính sách xử lý khi hết miền và liệu “wrap” có phải semantics cho phép không. `long` chỉ làm vùng số lớn hơn, không loại bỏ overflow về mặt nguyên tắc.

## 9. Exact arithmetic không áp dụng trực tiếp cho float/double

`Math.addExact`, `subtractExact` và phần lớn các phương thức exact nêu trên hoạt động với **`int`/`long`**, không có overload tổng quát cho `float`/`double`. Số thực dấu chấm động theo IEEE 754 có quy tắc riêng.

Ví dụ:

```java
double huge = Double.MAX_VALUE;
double sum = huge + huge;

System.out.println(sum);               // Infinity
System.out.println(Double.isInfinite(sum)); // true
```

Đoạn trên không ném `ArithmeticException`; đối với những kết quả không thể biểu diễn dưới dạng một số hữu hạn, double có thể cho `Infinity`, hoặc `NaN` trong các trường hợp khác.

**Không dùng `Math.addExact` để “sửa sai số làm tròn của double”.** Overflow integer và sai số biểu diễn thập phân là hai vấn đề khác nhau.

Nếu phải tính tiền có phần lẻ, cân nhắc `BigDecimal` với quy tắc scale/rounding rõ ràng; nếu dùng **số cent nguyên**, có thể dùng `long` + `Math.*Exact` và kiểm soát conversion ở ranh giới. Không tự chuyển toàn bộ số tiền sang `double` chỉ để tránh exception, vì có thể phát sinh sai số và vi phạm ràng buộc nghiệp vụ.

## 10. Nếu phạm vi int/long không đủ: BigInteger

`BigInteger` là kiểu số nguyên có độ chính xác tùy ý, cho phép biểu diễn nhiều giá trị nằm ngoài phạm vi `long`, trong giới hạn tài nguyên của máy.

```java
import java.math.BigInteger;

BigInteger big = BigInteger.valueOf(Long.MAX_VALUE)
        .add(BigInteger.ONE);
// big == 9223372036854775808
```

Đây là đoạn minh họa cần đặt trong method. Ưu điểm: phép `add`/`subtract`/`multiply` không bị wrap theo 32/64 bit như kiểu primitive. Đổi lại, có chi phí cấp phát và xử lý số lớn hơn; chương trình vẫn bị giới hạn bởi bộ nhớ và tài nguyên thực tế.

Chọn chiến lược theo yêu cầu:

| Yêu cầu | Phương án phù hợp |
| --- | --- |
| Kết quả chắc chắn vừa int | `int` với validation và checked operations ở các bước có nguy cơ |
| Kết quả có thể vượt int nhưng chắc chắn vừa long | Mở rộng operand trước khi tính; dùng `long` và `Math.*Exact` |
| Kết quả có thể vượt long nhưng vẫn cần số nguyên chính xác | `BigInteger` |
| Dữ liệu tài chính thập phân với scale/rounding | `BigDecimal`/số đơn vị nhỏ nhất với quy tắc nghiệp vụ |
| Wrap là chủ đích, ví dụ một số bitmask hoặc vòng đệm giới hạn số bit | Dùng phép toán wrap có chủ đích, **ghi rõ contract** và test |

Một phép cộng `BigInteger` không tự tạo ra `ArithmeticException` chỉ vì kết quả vượt `Long.MAX_VALUE`; nhưng `big.longValueExact()` sẽ ném nếu conversion về long làm mất thông tin. Vì vậy **narrowing ở ranh giới vẫn phải được kiểm tra**.

## 11. Những điểm dễ bị nhầm về dấu, kiểu và literal

### Dùng literal không tự mở rộng kết quả

```java
int a = 50_000;
int b = 50_000;

long wrong = a * b;        // int * int -> int, wrap trước
long right = (long) a * b; // long * int -> long
```

Câu lệnh gán vào long ở vế trái không làm Java đổi kiểu biểu thức ở vế phải trước khi tính.

### Ép kiểu sau phép toán không sửa lỗi

```java
long stillWrong = (long) (a * b); // vẫn đã wrap
long correct = ((long) a) * b;    // mở rộng trước khi nhân
```

Dấu ngoặc làm rõ thứ tự. Đây là lỗi rất thường xuất hiện trong phép tính giá × số lượng hoặc width × height.

### Math.abs(min) không báo overflow

```java
int min = Integer.MIN_VALUE;

int notPositive = Math.abs(min); // vẫn âm
int safe = Math.absExact(min);    // ArithmeticException
```

### Dấu trừ ở phép chia đặc biệt

```java
int min = Integer.MIN_VALUE;

int result = min / -1; // wrap, không ném
```

Cần dùng guard trên JDK 17 hoặc `Math.divideExact` khi ứng dụng đã chuyển baseline sang Java 18+.

### Chuyển long sang int

```java
long count = 3_000_000_000L;

int wrapped = (int) count;          // mất thông tin
int exact = Math.toIntExact(count); // ArithmeticException
```

### Không chỉ kiểm tra overflow ở bước cuối

```java
int a = Integer.MAX_VALUE;
int b = 1;
int c = 0;

int wrong = Math.addExact(a + b, c); // a+b đã wrap
int correct = Math.addExact(Math.addExact(a, b), c);
```

Dòng thứ hai ném đúng tại phép cộng gây overflow. Nếu bạn muốn một expression hoàn chỉnh khác, hãy đảm bảo **mọi thao tác có thể tràn** đều được kiểm tra, không chỉ thao tác ngoài cùng.

## 12. So sánh ArithmeticException với các lựa chọn khác

| Cách làm | Khi tràn | Phù hợp |
| --- | --- | --- |
| `a + b` trên int/long | Wrap, không exception | Khi wrap là thiết kế được kiểm soát |
| `Math.addExact(a, b)` | Ném `ArithmeticException` | Cần *fail fast* khi kết quả không biểu diễn được |
| `Math.multiplyExact(a, b)` | Ném `ArithmeticException` | Giá × số lượng, tổng byte, capacity, offset |
| `Math.toIntExact(long)` | Ném `ArithmeticException` khi narrowing | API/array/DB field yêu cầu int |
| `Math.absExact(a)` | Ném khi `a == MIN_VALUE` | Khoảng cách/độ lớn cần kết quả không âm |
| Mở rộng int → long trước tính | Tránh overflow của bước int nếu long đủ rộng | Bài toán có miền giá trị lớn hơn int |
| `BigInteger` | Không wrap theo int/long | Cần số nguyên lớn và chính xác |
| `double` | Có thể `Infinity`/`NaN` và sai số | Số thực theo semantics IEEE 754, **không** thay cho integer checked |
| Saturating arithmetic tự viết | Trả min/max do code quy định | Chỉ khi contract chủ động muốn bão hòa, không phải kiểm tra sai số |
| `Math.divideExact` (Java 18+) | Ném khi quotient nguyên tràn | Phép chia checked trên baseline JDK hỗ trợ |

**Không thể gắn nhãn một lựa chọn là “an toàn nhất” trong mọi bài toán.** Overflow detection rất phù hợp với yêu cầu không được phép wrap. Nhưng một thuật toán checksum hoặc arithmetic modular có thể chủ động cần wrap. Quan trọng là **chọn semantics có chủ đích**, không dùng wrap ngoài ý muốn trong dữ liệu nghiệp vụ.

## 13. Test đúng miền giá trị và các ca biên

Đừng chỉ test các số như `1 + 2` hoặc `5 × 6`. Phần lớn lỗi overflow chỉ xuất hiện ở cực trị và khi input kết hợp theo cách bất ngờ.

Bảng kiểm thử:

| Bài toán | Input | Kỳ vọng |
| --- | --- | --- |
| Cộng an toàn | `Math.addExact(40, 2)` | `42` |
| Cộng tràn int | `Math.addExact(Integer.MAX_VALUE, 1)` | `ArithmeticException` |
| Cộng tràn long | `Math.addExact(Long.MAX_VALUE, 1L)` | `ArithmeticException` |
| Trừ tràn âm | `Math.subtractExact(Integer.MIN_VALUE, 1)` | `ArithmeticException` |
| Nhân an toàn | `Math.multiplyExact(50_000L, 50_000L)` | `2_500_000_000L` |
| Nhân tràn int | `Math.multiplyExact(50_000, 50_000)` | `ArithmeticException` |
| Tăng vượt MAX | `Math.incrementExact(Integer.MAX_VALUE)` | `ArithmeticException` |
| Giảm dưới MIN | `Math.decrementExact(Integer.MIN_VALUE)` | `ArithmeticException` |
| Đổi dấu MIN | `Math.negateExact(Integer.MIN_VALUE)` | `ArithmeticException` |
| Trị tuyệt đối MIN | `Math.absExact(Integer.MIN_VALUE)` | `ArithmeticException` |
| Thu hẹp hợp lệ | `Math.toIntExact(42L)` | `42` |
| Thu hẹp quá lớn | `Math.toIntExact(3_000_000_000L)` | `ArithmeticException` |
| Chia int cho 0 | `divideExactOn17(1, 0)` | `ArithmeticException` |
| Chia MIN cho -1 | `divideExactOn17(Integer.MIN_VALUE, -1)` | `ArithmeticException` |
| Phép cộng thường vượt MAX | `Integer.MAX_VALUE + 1` | `Integer.MIN_VALUE` (wrap) |

Nếu dùng JUnit 5 trong một dự án có dependency test tương ứng, có thể dùng `assertThrows(ArithmeticException.class, () -> Math.addExact(Integer.MAX_VALUE, 1))`. Đây chỉ là ví dụ cho môi trường đã cấu hình JUnit; JUnit không tự được cài cùng JDK và không cần thiết để chạy chương trình Java SE ở mục 4.

### Cần test cả không tràn lẫn tràn

Nếu bạn kiểm tra đúng loại exception nhưng quên kiểm tra giá trị hợp lệ, có thể bỏ sót logic sai như ném lỗi với mọi input. Chương trình demo vừa in các phép toán hợp lệ, vừa xác nhận các ca tràn ném đúng loại exception.

### Không phụ thuộc message

`ArithmeticException.getMessage()` có thể khác theo method/JVM/JDK hoặc do code tự tạo. Kiểm thử bằng **exception type và hành vi**, không so sánh cứng `"integer overflow"` hoặc `"/ by zero"` trừ khi đó là **contract message do chính ứng dụng sở hữu**.

## 14. Mười hai lỗi thường gặp

**1. “Java tự ném ArithmeticException khi int overflow.”** Sai. Toán tử cộng, trừ, nhân trên `int`/`long` wrap theo quy tắc ngôn ngữ; chỉ một số phép khác như chia cho 0 tự ném.

**2. “Khai báo long ở vế trái sẽ cứu phép nhân int.”** Sai. `long x = a * b` vẫn tính `int * int` nếu `a` và `b` là int. Mở rộng trước khi tính.

**3. “Math.addExact(a + b, 0) phát hiện mọi tràn.”** Sai. `a + b` có thể đã wrap; exact chỉ kiểm tra phép cộng cuối cùng với 0.

**4. “Ép (int) long sẽ báo overflow.”** Sai. Cast narrowing có thể làm mất bit cao; dùng `Math.toIntExact`.

**5. “Math.abs(x) luôn không âm.”** Sai với `Integer.MIN_VALUE` và `Long.MIN_VALUE`. Dùng `Math.absExact` khi cần từ chối trường hợp này.

**6. “Phép chia MIN_VALUE / -1 luôn ném.”** Sai với toán tử `/` trên int/long. Dùng kiểm tra thủ công ở JDK 17 hoặc `Math.divideExact` trên JDK 18+.

**7. “Math.divideExact dùng được với --release 17.”** Sai. API được giới thiệu trong Java 18.

**8. “Math.multiplyExact(int, int) trả long để chứa kết quả.”** Sai. Overload int/int trả int hoặc ném lỗi. Cần cast operand sang long để dùng overload long.

**9. “Mọi ArithmeticException đều chứng minh overflow.”** Sai. Chia nguyên cho 0 và các tình huống số học khác cũng có thể ném.

**10. “Thay toàn bộ phép toán bằng double sẽ tránh mọi lỗi.”** Sai. double có giới hạn, rounding, `Infinity` và `NaN`; thường không phù hợp với tiền, ID hoặc bộ đếm chính xác.

**11. “Catch ArithmeticException rồi cho kết quả bằng 0 là xử lý an toàn.”** Sai nếu contract không hề cho phép bỏ giá trị thật. Điều đó có thể che lỗi dữ liệu nghiêm trọng.

**12. “Exact làm mọi phép cập nhật dữ liệu thành transaction.”** Sai. Nó chỉ xác minh **phép toán được gọi**. Side effects trước exception, concurrency và transaction database vẫn cần được thiết kế độc lập.

## 15. Bài thực hành

### Bài 1 — Phép cộng sát biên

Viết method `int checkedNext(int current)` dùng `Math.incrementExact`. Thử `current=0`, `current=Integer.MAX_VALUE-1` và `current=Integer.MAX_VALUE`. Giải thích vì sao chỉ trường hợp cuối ném exception.

### Bài 2 — Cộng tổng nhiều phần

Tạo một `List<Integer>` và cộng lần lượt bằng `Math.addExact`. Dùng hai bộ test: một có tổng nằm trong int, một có tổng vượt MAX. Chứng minh ngoại lệ được phát hiện **ngay tại bước gây tràn**, không đợi đến phần tử cuối cùng.

### Bài 3 — Giá × số lượng

Giả sử `unitPriceCents` là `long` và `quantity` là `int`. Viết `Math.multiplyExact(unitPriceCents, (long) quantity)`, kiểm tra giá âm/số lượng âm và trường hợp tích vượt `Long.MAX_VALUE`. Nếu tổng còn cần cộng nhiều dòng, dùng tiếp `Math.addExact`.

### Bài 4 — Tìm bug do widen quá muộn

So sánh:

```java
int a = 50_000;
int b = 50_000;

long first = (long) (a * b);
long second = (long) a * b;
```

Dự đoán rồi chạy chương trình: `first == -1_794_967_296L`, `second == 2_500_000_000L`. Giải thích rõ Java xác định kiểu biểu thức **trước hay sau** phép cast.

### Bài 5 — Phép chia đặc biệt

Viết `divideExactOn17(int,int)` với hai guard: chia cho 0 và `Integer.MIN_VALUE/-1`. Trên JDK 18+, so sánh hành vi với `Math.divideExact` nếu môi trường có API. Không gọi phương thức mới khi compile mục tiêu JDK 17.

### Bài 6 — So sánh miền dữ liệu

Chọn `int`, `long` hoặc `BigInteger` cho các trường hợp: số người dùng trong một lượt, tổng cent của tài khoản, số lượng phép tổ hợp có thể rất lớn và bộ đếm tăng liên tục. Nêu **giới hạn miền** và chính sách xử lý khi overflow xảy ra.

### Bài 7 — Kiểm tra không có cập nhật dở dang

Mô phỏng một giỏ hàng có hai dòng; dòng thứ hai làm tràn tổng. Chỉ cập nhật total sau khi các phép tính trung gian đã được kiểm tra. Nếu dùng database thật, bổ sung transaction để tránh side effects đã ghi trước khi ném exception.

### Bài 8 — Concurrency và counter

Dùng `AtomicInteger.updateAndGet(Math::incrementExact)` để tạo bộ đếm không wrap. Thử ở gần MAX, quan sát ngoại lệ và xác nhận phép cập nhật không đưa counter về MIN. Giải thích vì sao hàm updater phải **không có side effects** khi CAS retry.

**Tiêu chí hoàn thành:** Người học mô tả đúng sự khác nhau giữa wrap và checked arithmetic, áp dụng `Math.*Exact` tại đúng phép toán có nguy cơ tràn, phát hiện narrowing sai, xử lý trường hợp MIN/-1, phân biệt overflow với chia cho 0 và chọn kiểu dữ liệu/chiến lược lỗi thích hợp.

## 16. Tài liệu chính thức

- [Oracle Java SE 17 — Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `addExact`, `subtractExact`, `multiplyExact`, `incrementExact`, `decrementExact`, `negateExact`, `toIntExact` và `absExact`.
- [Oracle Java SE 26 — Math](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Math.html): API exact hiện hành và các phương thức bổ sung như `divideExact` trên JDK mới.
- [Oracle Java SE 17 — ArithmeticException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ArithmeticException.html): loại ngoại lệ số học unchecked.
- [Java Language Specification SE 17 — Operators and expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html): phép cộng/trừ/nhân số nguyên overflow và trường hợp đặc biệt phép chia.
- [Oracle Java SE 17 — StrictMath](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StrictMath.html): các method exact có mặt trong `StrictMath` từ Java 14, vẫn tồn tại nhưng không phải yêu cầu thay `Math` trong ứng dụng thông thường.
- [Oracle Java SE 17 — BigInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): kiểu số nguyên lớn và `intValueExact`/`longValueExact`.
- [Oracle Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): tính toán thập phân, scale và rounding khi miền bài toán yêu cầu.

**Ghi nhớ:** Toán tử trên `int`/`long` có thể **cuộn vòng theo bit** mà không ném exception; các phương thức `Math.*Exact` trả số chính xác hoặc **ném `ArithmeticException` ngay khi phép toán không vừa kiểu đích**. Hãy kiểm tra ở **mỗi bước có nguy cơ tràn**, xử lý lỗi theo hợp đồng dữ liệu và dùng kiểu lớn hơn khi miền giá trị thực sự cần thiết — thay vì cho một kết quả sai trôi qua im lặng.