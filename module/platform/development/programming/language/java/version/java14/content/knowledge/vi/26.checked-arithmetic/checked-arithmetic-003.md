# Các bổ sung `negateExact` của `StrictMath` — đổi dấu số nguyên và phát hiện tràn (Java 14+)

## 1. Bài toán: đổi dấu một giá trị nhưng không muốn kết quả sai âm thầm

Đổi dấu (*negation*) một số nguyên nghĩa là biến `x` thành `-x`. Trong Java, cách thông thường là dùng toán tử một ngôi `-`:

```java
int delta = -125;
int reversed = -delta;   // 125
```

Cách này đúng trong hầu hết trường hợp. Tuy nhiên, với kiểu nguyên cố định `int` hoặc `long`, có **một giá trị âm duy nhất không thể đổi sang số dương cùng kiểu**: `MIN_VALUE`. Toán tử `-` của Java **không tự ném ngoại lệ khi kết quả vượt phạm vi**; kết quả bị tràn theo số học nguyên có dấu.

Ví dụ:

```java
int x = Integer.MIN_VALUE;
int wrong = -x;
System.out.println(wrong == Integer.MIN_VALUE); // true
```

Giá trị `wrong` vẫn âm dù code định đổi sang dương. Nếu dữ liệu này đại diện cho số tiền, số lượng, chênh lệch hay số thứ tự, lỗi có thể tiếp tục lan tới nhiều phép tính khác.

Để phát hiện thay vì âm thầm nhận kết quả tràn, Java có:

```java
int safe = StrictMath.negateExact(x); // ArithmeticException nếu x = MIN_VALUE
```

**Chủ đề chính:** hai overload `StrictMath.negateExact(int)` và `StrictMath.negateExact(long)` được **bổ sung vào `StrictMath` trong Java 14**. Chúng **vẫn tồn tại trong API Java hiện đại**, không phải tính năng preview hoặc legacy. Bài giải thích cơ chế, tình huống biên, phân biệt với `Math.negateExact` và toán tử `-`, vấn đề kiểu dữ liệu, kiểm thử và cách dùng trong nghiệp vụ.

### Mục tiêu sau bài học

- Biết khi nào **đổi dấu có thể tràn**, vì sao chỉ tràn tại `MIN_VALUE`.
- Dùng đúng hai chữ ký `StrictMath.negateExact(int)` và `StrictMath.negateExact(long)`.
- Hiểu ngoại lệ `ArithmeticException` và cách xử lý ở tầng phù hợp.
- Phân biệt `-x`, `Math.negateExact(x)`, `StrictMath.negateExact(x)` và `Math.subtractExact(0, x)`.
- Hiểu **ép kiểu trước** và **ép kiểu sau** phép đổi dấu có thể cho kết quả hoàn toàn khác.
- Biết khi nào phải chuyển sang `long` hoặc `BigInteger` vì kết quả không biểu diễn được trong kiểu ban đầu.
- Có ví dụ Java 17+ độc lập đã được biên dịch và kiểm chứng output.

## 2. Vì sao số nguyên có dấu có một giá trị không thể đổi dấu?

Java sử dụng biểu diễn **bù hai (two's complement)** cho các kiểu nguyên có dấu. Phạm vi của chúng không đối xứng:

| Kiểu | Số bit | Giá trị nhỏ nhất | Giá trị lớn nhất |
| --- | ---: | ---: | ---: |
| `int` | 32 | `-2_147_483_648` (`Integer.MIN_VALUE`) | `2_147_483_647` (`Integer.MAX_VALUE`) |
| `long` | 64 | `-9_223_372_036_854_775_808L` (`Long.MIN_VALUE`) | `9_223_372_036_854_775_807L` (`Long.MAX_VALUE`) |

Với kiểu `int`, số đối của `-2_147_483_648` về mặt toán học là `+2_147_483_648`. Nhưng `+2_147_483_648` **lớn hơn `Integer.MAX_VALUE` một đơn vị**, vì vậy không có giá trị `int` nào biểu diễn được kết quả.

Tương tự, số đối của `Long.MIN_VALUE` là `9_223_372_036_854_775_808`, vượt giới hạn của `long`. Các số âm còn lại đều có số đối nằm trong phạm vi biểu diễn được. Vì thế:

> **Với `int` và `long`, `negateExact` chỉ ném `ArithmeticException` khi đối số đúng bằng giá trị `MIN_VALUE` của kiểu tương ứng.**

### Thử bằng toán tử `-` thông thường

```java
int smallest = Integer.MIN_VALUE;
int wrapped = -smallest;

// Vẫn bằng -2_147_483_648 do tràn trong phép toán int.
System.out.println(wrapped == smallest); // true
```

Đó là ngữ nghĩa số học Java, không phải bug của JVM. Java **không tự bật chế độ “checked arithmetic” cho toán tử `-`** khi chạy. Nếu logic của ứng dụng đòi kết quả chính xác trong phạm vi `int`/`long`, hãy dùng API `negateExact` thay vì trông chờ toán tử `-` tự phát hiện lỗi.

### Những giá trị không gây tràn

| Input | Phép gọi | Kết quả |
| --- | --- | --- |
| `-125` kiểu `int` | `StrictMath.negateExact(-125)` | `125` |
| `125` kiểu `int` | `StrictMath.negateExact(125)` | `-125` |
| `0` kiểu `int` | `StrictMath.negateExact(0)` | `0` |
| `Integer.MAX_VALUE` | `StrictMath.negateExact(Integer.MAX_VALUE)` | `-2_147_483_647` |
| `Integer.MIN_VALUE` | `StrictMath.negateExact(Integer.MIN_VALUE)` | Ném `ArithmeticException` |
| `-9_000_000_000L` | `StrictMath.negateExact(-9_000_000_000L)` | `9_000_000_000L` |
| `Long.MAX_VALUE` | `StrictMath.negateExact(Long.MAX_VALUE)` | `-9_223_372_036_854_775_807L` |
| `Long.MIN_VALUE` | `StrictMath.negateExact(Long.MIN_VALUE)` | Ném `ArithmeticException` |

**Không có “âm không” ở kiểu `int`/`long`:** `StrictMath.negateExact(0)` vẫn là `0`. Khái niệm signed zero của `float`/`double` không phải vấn đề của API này.

## 3. Chữ ký và hợp đồng của hai phương thức

Trong `java.lang.StrictMath` hiện hành:

```java
public static int negateExact(int a)
public static long negateExact(long a)
```

**Đặc điểm:**

1. Cả hai là **phương thức `static`**, gọi qua tên class `StrictMath`; không tạo `new StrictMath()`.
2. `negateExact(int)` nhận `int` và trả **`int`**.
3. `negateExact(long)` nhận `long` và trả **`long`**.
4. Kết quả là **số đối chính xác** của đối số nếu còn nằm trong phạm vi kiểu đó.
5. Nếu kết quả vượt phạm vi, phương thức **ném `java.lang.ArithmeticException`**.
6. Không có kết quả dự phòng đặc biệt hoặc sentinel khi tràn.
7. Không có overload nhận `float`, `double` hoặc `BigInteger`; cần API phù hợp nếu dữ liệu thuộc các kiểu đó.
8. Hai phương thức được đánh dấu **`Since: 14`** trong tài liệu Oracle Java 14 và các phiên bản Java mới.

Ví dụ:

```java
int a = StrictMath.negateExact(-12);    // 12
long b = StrictMath.negateExact(-12L); // 12L
```

Việc chọn overload diễn ra dựa trên **kiểu của biểu thức truyền vào**. Dấu `L` trong `-12L` khiến đối số có kiểu `long`. Trong ví dụ đơn giản, giá trị giống nhau; với những giá trị lớn hơn phạm vi `int`, khác biệt kiểu là thiết yếu.

### Vì sao lại có phương thức mới trong `StrictMath` khi `Math.negateExact` đã tồn tại?

`java.lang.Math.negateExact(int/long)` đã có từ **Java 8**. Java 14 bổ sung các phương thức tương ứng vào **`StrictMath`**, gồm `negateExact`, `incrementExact` và `decrementExact`, để API số học kiểm tra tràn giữa hai class nhất quán hơn.

Với phép **đổi dấu số nguyên chính xác**, `Math.negateExact(x)` và `StrictMath.negateExact(x)` có **cùng yêu cầu về kết quả và ngoại lệ**. Không có lợi ích “floating-point nghiêm ngặt” đặc biệt khi chọn `StrictMath.negateExact`, vì chúng đang thao tác trên `int`/`long`, không phải phép tính dấu phẩy động.

**Nên dùng API nào?**

- Trong code vốn đang dùng `StrictMath` hoặc theo chuẩn thư viện của dự án: `StrictMath.negateExact` là API chính thức và hoàn toàn phù hợp.
- Trong code thông thường đã dùng `Math`: `Math.negateExact` cũng hợp lệ, không cần chuyển toàn bộ code sang `StrictMath` chỉ vì muốn kiểm tra tràn.
- Quan trọng hơn tên class là **dùng phương thức kiểm tra tràn khi dữ liệu yêu cầu kết quả chính xác**.

Không gán cho `StrictMath.negateExact` tính chất “tràn an toàn hơn” `Math.negateExact`; cả hai đáp ứng cùng hợp đồng số học chính xác.

## 4. So sánh trực tiếp với những phép tương tự

| Biểu thức | Phản ứng khi `x = Integer.MIN_VALUE` | Ý nghĩa |
| --- | --- | --- |
| `-x` | Không ném; kết quả wrap thành `Integer.MIN_VALUE` | Toán tử đổi dấu thông thường, **không kiểm tra tràn** |
| `StrictMath.negateExact(x)` | Ném `ArithmeticException` | Đổi dấu **có kiểm tra tràn**, Java 14+ cho StrictMath |
| `Math.negateExact(x)` | Ném `ArithmeticException` | Cùng ngữ nghĩa, có trong Math từ Java 8 |
| `Math.subtractExact(0, x)` | Ném `ArithmeticException` | Phép trừ kiểm tra tràn; tương đương toán học `0 - x` |
| `Math.abs(x)` | Trả lại `Integer.MIN_VALUE` | Giá trị tuyệt đối **không phải** đổi dấu; vẫn có biên tràn |
| `~x + 1` | Wrap thành `Integer.MIN_VALUE` | Cách biểu diễn bù hai, **không** thay checked arithmetic |

**Không nên tự viết `-x` rồi thêm kiểm tra `if (result < 0)`** để phát hiện tràn. Ví dụ nếu `x` dương, kết quả âm là bình thường; nếu `x` âm, kết quả dương là bình thường ngoại trừ MIN. Một phép so sánh dấu đơn giản không phải hợp đồng kiểm tra tràn tổng quát.

Nếu muốn xử lý lỗi **trước** phép đổi dấu, có thể kiểm tra rõ `x == Integer.MIN_VALUE` hoặc `x == Long.MIN_VALUE`, nhưng `negateExact` diễn đạt ý định gọn hơn và tránh nhầm lẫn giữa các kiểu. Việc kiểm tra trước riêng lẻ chỉ cần khi ứng dụng muốn cung cấp thông báo nghiệp vụ đặc biệt hoặc cần điều kiện biên cho một API khác.

### Sự khác nhau giữa `negateExact` và `abs`

`negateExact(x)` luôn đổi dấu: số dương thành âm và số âm thành dương. `abs(x)` chuyển số âm thành dương nhưng **giữ nguyên số dương**, nên không phải thao tác tương đương.

Ví dụ:

```java
int x = 5;
System.out.println(StrictMath.negateExact(x)); // -5
System.out.println(Math.abs(x));               // 5
```

Nếu mục tiêu là “đảo chiều khoản tiền”, dùng `negateExact`. Nếu mục tiêu là “độ lớn của khoản tiền”, đó là bài toán `abs` và cần lựa chọn API chính xác theo điều kiện tràn riêng; không dùng `negateExact` thay thế một cách máy móc.

## 5. Chương trình Java 17+ hoàn chỉnh và đầu ra đã kiểm thử

Tạo tệp **`StrictNegateExactDemo.java`** đúng như sau. Chương trình kiểm tra giá trị bình thường, zero, MAX_VALUE, MIN_VALUE, toán tử `-` bị wrap, vấn đề nới rộng kiểu, `BigInteger` và đối chiếu `Math`.

```java
import java.math.BigInteger;

public class StrictNegateExactDemo {
    private static boolean rejectsIntMin() {
        try {
            StrictMath.negateExact(Integer.MIN_VALUE);
            return false;
        } catch (ArithmeticException expected) {
            return true;
        }
    }

    private static boolean rejectsLongMin() {
        try {
            StrictMath.negateExact(Long.MIN_VALUE);
            return false;
        } catch (ArithmeticException expected) {
            return true;
        }
    }

    private static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        int negative = -125;
        int positive = StrictMath.negateExact(negative);
        long reversed = StrictMath.negateExact(-9_000_000_000L);

        int overflowWrap = -Integer.MIN_VALUE;
        long widenedFirst =
                StrictMath.negateExact((long) Integer.MIN_VALUE);
        BigInteger widenedLong =
                BigInteger.valueOf(Long.MIN_VALUE).negate();

        check(positive == 125, "int negate");
        check(reversed == 9_000_000_000L, "long negate");
        check(StrictMath.negateExact(0) == 0, "zero int");
        check(StrictMath.negateExact(0L) == 0L, "zero long");

        check(StrictMath.negateExact(Integer.MAX_VALUE)
                == -Integer.MAX_VALUE, "int max");
        check(StrictMath.negateExact(Long.MAX_VALUE)
                == -Long.MAX_VALUE, "long max");

        check(rejectsIntMin(), "int min must throw");
        check(rejectsLongMin(), "long min must throw");
        check(overflowWrap == Integer.MIN_VALUE,
                "unary minus must wrap");

        check(widenedFirst == 2_147_483_648L,
                "widen before negate");
        check(widenedLong.toString()
                .equals("9223372036854775808"),
                "big integer");

        check(StrictMath.negateExact(negative)
                == Math.negateExact(negative),
                "Math equivalence");
        check(StrictMath.negateExact(-9_000_000_000L)
                == Math.negateExact(-9_000_000_000L),
                "Math long equivalence");
        check(StrictMath.negateExact(-125)
                == Math.subtractExact(0, -125),
                "subtract identity");

        System.out.println("intNegated=" + positive);
        System.out.println("longNegated=" + reversed);
        System.out.println("zero=" + StrictMath.negateExact(0));
        System.out.println("intMinThrows=" + rejectsIntMin());
        System.out.println("longMinThrows=" + rejectsLongMin());
        System.out.println("plainUnaryMinusWraps="
                + (overflowWrap == Integer.MIN_VALUE));
        System.out.println("widenBeforeNegate=" + widenedFirst);
        System.out.println("longMinBigIntegerNegated="
                + widenedLong);
        System.out.println("sameAsMath=true");
    }
}
```

**Biên dịch và chạy:**

```bash
javac --release 17 -encoding UTF-8 StrictNegateExactDemo.java
java StrictNegateExactDemo
```

**Standard output chính xác trên môi trường OpenJDK 21 đã kiểm thử:**

```text
intNegated=125
longNegated=9000000000
zero=0
intMinThrows=true
longMinThrows=true
plainUnaryMinusWraps=true
widenBeforeNegate=2147483648
longMinBigIntegerNegated=9223372036854775808
sameAsMath=true
```

Chương trình chạy các phép kiểm tra `check(...)` trước khi in kết quả. Bất kỳ điều kiện sai nào đều ném `AssertionError` và không đi tiếp như thể mọi thứ hợp lệ.

**Kiểm chứng phiên bản:** Tệp được biên dịch thành công với `javac --release 17`; cùng nguồn cũng biên dịch thành công với `javac --release 14` trên JDK kiểm thử. Điều này phù hợp với tài liệu `Since: 14` của `StrictMath.negateExact`. Bài hướng dẫn sử dụng Java 17+ vì đây là môi trường hiện hành và ổn định; không cần `--enable-preview`.

### 5.1. Dòng `intNegated` và `longNegated`

- `StrictMath.negateExact(-125)` trả `125`.
- `StrictMath.negateExact(-9_000_000_000L)` trả `9_000_000_000L`.
- Chữ `L` ở literal thứ hai chọn overload `long`; giá trị này lớn hơn `Integer.MAX_VALUE` nên không thể biểu diễn dưới `int`.

### 5.2. Các dòng `intMinThrows` và `longMinThrows`

Hai helper gọi `StrictMath.negateExact(Integer.MIN_VALUE)` và `StrictMath.negateExact(Long.MIN_VALUE)` trong khối `try`. Nếu gặp đúng `ArithmeticException`, helper trả `true`. Không so sánh nguyên văn `exception.getMessage()` vì thông báo lỗi có thể khác nhau giữa các implementation.

### 5.3. Dòng `plainUnaryMinusWraps`

`-Integer.MIN_VALUE` dùng toán tử `-`, không gọi API kiểm tra tràn. Kết quả vẫn bằng `Integer.MIN_VALUE` và chương trình xác nhận điều đó bằng `==`. Đây là tình huống mà `negateExact` giúp tránh kết quả âm thầm sai.

### 5.4. Hai dòng `widenBeforeNegate` và `longMinBigIntegerNegated`

- Khi nới `Integer.MIN_VALUE` sang `long` **trước khi đổi dấu**, số đối `2_147_483_648L` nằm trong phạm vi `long` và tính được.
- Với `Long.MIN_VALUE`, không có kiểu primitive nguyên có dấu lớn hơn `long`; chuyển sang `BigInteger` **trước khi negate** để nhận đúng `9_223_372_036_854_775_808`.

### 5.5. `sameAsMath=true`

Chương trình kiểm tra kết quả `StrictMath.negateExact` bằng `Math.negateExact` cho cả `int` và `long`, đồng thời đối chiếu phép `Math.subtractExact(0, x)` ở tình huống `int` bình thường. Dòng in này là kết luận sau khi **các assertion liên quan đã đạt**, không phải bằng chứng rằng mọi library call cho mọi loại số đều giống nhau.

## 6. Ép kiểu trước hoặc sau: khác biệt có thể quyết định đúng/sai

Đây là một điểm rất dễ nhầm với toán tử và các phương thức exact.

### Cách đúng nếu kết quả không vừa `int` nhưng vừa `long`

```java
int min = Integer.MIN_VALUE;

// Ép int sang long TRƯỚC khi chọn overload.
long correct = StrictMath.negateExact((long) min);

// Giá trị correct = 2147483648L.
```

Việc ép `(long) min` làm biểu thức trở thành `long`; compiler chọn overload `StrictMath.negateExact(long)`. `-(-2_147_483_648L)` vừa trong phạm vi `long`, nên hợp lệ.

### Cách sai: gọi overload `int` rồi mới ép `long`

```java
int min = Integer.MIN_VALUE;

// ArithmeticException xảy ra TRƯỚC phép cast ngoài.
long impossible = (long) StrictMath.negateExact(min);
```

Phép `StrictMath.negateExact(min)` phải được tính xong **trước** khi cast kết quả sang `long`. Vì overload nhận `int` đã ném `ArithmeticException` nên cast không bao giờ được thực hiện.

### Không thể ép ngược về `int` tùy tiện

```java
long widened = StrictMath.negateExact(
        (long) Integer.MIN_VALUE); // 2147483648L

int wrappedAgain = (int) widened; // trở lại Integer.MIN_VALUE
```

Cast từ `long` về `int` có thể **cắt bớt các bit cao**, không tự phát hiện tràn. Nếu muốn nêu rõ điều kiện “kết quả phải nằm trong int”, dùng:

```java
int checked = Math.toIntExact(widened);
// ArithmeticException vì 2147483648L vượt int.
```

**Nguyên tắc:** Nếu domain đòi lưu trong `int`, không thể “sửa” `Integer.MIN_VALUE` bằng cách mở rộng rồi cast ngược lại. Nếu domain thực sự cần giữ số đối dương lớn hơn int, **đích dữ liệu phải là `long`** hoặc kiểu có phạm vi lớn hơn.

## 7. Kiểu `byte`, `short` và `char` có gì đặc biệt?

`StrictMath` chỉ có overload nhận **`int`** và **`long`**. Trong Java, `byte`, `short` và `char` thường được **promote** lên `int` trước các phép toán số học.

```java
byte b = Byte.MIN_VALUE;        // -128
int result = StrictMath.negateExact(b); // 128
```

Đây là một đoạn minh họa hợp lệ trong thân phương thức. Không có `StrictMath.negateExact(byte)`. Compiler chọn `negateExact(int)` và giá trị `-128` đã nằm trong phạm vi `int`, nên `128` là kết quả chính xác.

Nếu sau đó muốn lưu kết quả vào `byte`:

```java
byte again = (byte) result; // -128 do narrowing cast
```

thì lại mất giá trị dương `128`. **Ngoại lệ của `negateExact(int)` không bảo vệ cho phép narrowing cast diễn ra sau đó.** Nếu cần một kiểm tra cho miền giá trị `byte`/`short`, hãy dùng điều kiện range tường minh trước khi ép kiểu về miền hẹp đó.

Với `char`, giá trị ban đầu không âm; `StrictMath.negateExact(charValue)` đi qua overload `int` và có thể trả số âm. Không suy ra kết quả đó vẫn biểu diễn được như `char`.

### `float` và `double` thì sao?

Không có `StrictMath.negateExact(float)` hoặc `StrictMath.negateExact(double)`. Những kiểu này có quy tắc dấu, số không dấu và overflow riêng; phép `-value` trên `double` không tương đương hợp đồng kiểm tra tràn của số nguyên `int`/`long`.

Không ép một số thực thành `int` chỉ để dùng `negateExact`: việc chuyển từ floating-point sang số nguyên có thể mất phần thập phân hoặc gặp quy tắc conversion khác. Chọn API theo **kiểu dữ liệu và yêu cầu chính xác của bài toán**, không chỉ theo tên “negate”.

## 8. Khi nào nên chuyển sang `BigInteger`?

Nếu cần tính số đối của **`Long.MIN_VALUE`** mà vẫn giữ giá trị chính xác, không thể dùng overload nào của `StrictMath.negateExact` để trả `long`. Khi đó có thể chuyển sang `java.math.BigInteger`:

```java
import java.math.BigInteger;

// Snippet trong method:
BigInteger value = BigInteger.valueOf(Long.MIN_VALUE);
BigInteger opposite = value.negate();
System.out.println(opposite); // 9223372036854775808
```

Lưu ý **chuyển sang `BigInteger` trước khi đổi dấu**. Nếu viết:

```java
long broken = -Long.MIN_VALUE;
BigInteger tooLate = BigInteger.valueOf(broken);
```

thì `broken` đã bị wrap thành `Long.MIN_VALUE`. `BigInteger.valueOf(broken)` chỉ nhận **giá trị đã sai**, không thể đoán bạn từng muốn tính một số lớn hơn `Long.MAX_VALUE`.

**`BigInteger` khác `negateExact` ở kết quả/hợp đồng:**

- `StrictMath.negateExact(long)` trả `long` hoặc ném nếu số đối vượt phạm vi.
- `BigInteger.negate()` trả một `BigInteger` mới biểu diễn số đối chính xác, không giới hạn ở 64 bit.
- Chi phí bộ nhớ/CPU và cách lưu trữ/serialize `BigInteger` khác so với primitive `long`.

Nếu dùng `BigInteger` để xử lý một vài giá trị ngoại lệ, cần thiết kế giao diện/hợp đồng của hệ thống cho kiểu mới; không chỉ đổi một dòng rồi giữ các biến lưu trữ kiểu `long`.

### Khi biểu diễn tiền có phần thập phân

Với giá trị tiền theo đơn vị nguyên nhỏ nhất (ví dụ cents), `long` và `negateExact` có thể phù hợp nếu phạm vi được thiết kế rõ. Nếu nghiệp vụ cần tiền thập phân chính xác với scale/rounding, `BigDecimal.negate()` là lựa chọn liên quan nhưng **khác bài toán**: nó không thay thế quy tắc giới hạn miền `int`/`long`, và không nên coi `double` là kiểu tiền chính xác mặc định.

## 9. Ứng dụng thực tế: đảo dấu một giao dịch mà không che lỗi dữ liệu

Giả sử một hệ thống lưu **số tiền thay đổi dưới dạng `long`**. Giá trị dương đại diện cho tăng, giá trị âm đại diện cho giảm. Khi tạo một bút toán đảo, ta cần số đối chính xác:

```java
// Snippet trong một class service.
static long reversedAmount(long originalMinorUnits) {
    return StrictMath.negateExact(originalMinorUnits);
}
```

Nếu `originalMinorUnits == Long.MIN_VALUE`, hàm ném `ArithmeticException` thay vì trả lại một số âm tưởng như đã “đảo” thành công.

Khi cập nhật số dư, cũng cần phép cộng có kiểm tra tràn:

```java
// Snippet: oldBalance và originalAmount có kiểu long.
long reversal = StrictMath.negateExact(originalAmount);
long newBalance = Math.addExact(oldBalance, reversal);

// Chỉ ghi lại state sau khi cả hai phép toán hợp lệ.
saveBalance(newBalance);
```

`saveBalance` là **phương thức nghiệp vụ giả định**; đoạn này không phải một chương trình độc lập. Nó minh họa cách đặt thao tác có thể ném exception **trước** thao tác ghi trạng thái.

**Điểm quan trọng:** `negateExact` chỉ bảo đảm riêng **phép đổi dấu**, không tự bảo vệ phép cộng số dư, lưu trữ database hay transaction. Nếu phép cộng cũng có thể tràn, dùng `Math.addExact` hoặc `StrictMath.addExact` theo yêu cầu của project. Việc ghi database cần cơ chế transaction/rollback riêng, không được coi `ArithmeticException` là một transaction manager.

### Không làm bước ghi trạng thái trước khi tính toán an toàn

Một cách thiết kế rủi ro:

```java
// Pseudocode anti-pattern, không phải class hoàn chỉnh.
savePartialState();
long reversal = StrictMath.negateExact(originalAmount);
```

Nếu `negateExact` ném exception, ứng dụng có thể để lại state đã sửa trước đó. Hãy tính toán/validate giá trị cần thiết, sau đó mới bắt đầu tác vụ có side effect hoặc dùng transaction để bảo đảm rollback theo quy tắc nghiệp vụ.

### Trả lỗi phù hợp với tầng ứng dụng

Ví dụ:

```java
// Snippet trong service.
try {
    long reversal = StrictMath.negateExact(originalAmount);
    persistReversal(reversal);
} catch (ArithmeticException failure) {
    throw new IllegalArgumentException(
            "Không thể đảo dấu giao dịch với giá trị hiện tại",
            failure);
}
```

`persistReversal` và `originalAmount` là những thành phần đã được định nghĩa ở service thực. Wrapper giữ **cause** để log có thể truy vết, nhưng **không nên bắt `ArithmeticException` của cả một khối quá rộng** rồi mặc định mọi trường hợp đều do `negateExact`: trong nhiều phép toán, lỗi có thể đến từ chỗ khác.

Nếu gặp dữ liệu nhập không hợp lệ, tầng validation có thể từ chối sớm theo contract. Nếu gặp một trạng thái không thể xảy ra theo thiết kế, cần ghi nhận như lỗi chất lượng dữ liệu hoặc bug thay vì lặng lẽ dùng giá trị dự phòng.

## 10. Chiến lược xử lý `ArithmeticException`

`ArithmeticException` là một **unchecked exception** (kế thừa `RuntimeException`), nên Java không bắt buộc ghi `throws` hoặc `catch`. Nhưng việc không bắt buộc xử lý không đồng nghĩa lỗi không quan trọng.

Ba cách thường dùng:

### A. Cho ngoại lệ lan lên tầng xử lý có trách nhiệm

Nếu phép đổi dấu là một bất biến của logic và không có giá trị dự phòng hợp lệ, cứ để `ArithmeticException` lan truyền. Tầng ranh giới của request/job có thể ghi log với ngữ cảnh an toàn, trả mã lỗi phù hợp, rồi tránh commit state chưa hoàn chỉnh.

### B. Bắt để chuyển thành lỗi nghiệp vụ có cause

Nếu đầu vào có thể hợp pháp bị từ chối vì miền dữ liệu, bắt và bọc với thông điệp rõ ràng, **luôn giữ cause**. Không tạo exception mới chỉ với `e.getMessage()` khiến mất stack trace gốc.

### C. Chuyển sang kiểu rộng hơn theo yêu cầu

Nếu `Integer.MIN_VALUE` là một input hợp lệ và kết quả dương tương ứng cần lưu, dùng `long` **trước phép đổi dấu**. Nếu `Long.MIN_VALUE` cũng phải được đổi dấu, dùng `BigInteger`. Đây là **quyết định domain** về kiểu kết quả, không phải cách “bỏ qua lỗi”.

**Không nên:**

- Bắt exception rồi trả `0` như thể đã có kết quả.
- Trả lại input MIN_VALUE như thể đổi dấu thành công.
- Tự cộng 1/trừ 1 để né ngưỡng mà không có quy tắc nghiệp vụ.
- Log một chuỗi message rồi bỏ mất `Throwable`/cause.
- Dựa vào thông báo exception cố định như `"integer overflow"` hoặc `"long overflow"` để điều khiển logic. Nội dung message không phải giao diện nghiệp vụ ổn định; hãy test **kiểu exception**.

## 11. Cách viết test cho `StrictMath.negateExact`

Mấu chốt của checked arithmetic là **kiểm tra biên**, không chỉ kiểm tra các giá trị trung bình. Một bộ test nên bao gồm:

| Nhóm test | `int` | `long` | Kỳ vọng |
| --- | --- | --- | --- |
| Số âm thường | `-125` | `-9_000_000_000L` | Kết quả dương chính xác |
| Số dương thường | `125` | `9_000_000_000L` | Kết quả âm chính xác |
| Zero | `0` | `0L` | Trả 0, không exception |
| MIN_VALUE | `Integer.MIN_VALUE` | `Long.MIN_VALUE` | Ném `ArithmeticException` |
| MAX_VALUE | `Integer.MAX_VALUE` | `Long.MAX_VALUE` | Trả số âm, không exception |
| So sánh `Math.negateExact` | Một vài giá trị hợp lệ | Một vài giá trị hợp lệ | Cùng kết quả và semantics |
| Widen trước negate | `(long) Integer.MIN_VALUE` | `BigInteger.valueOf(Long.MIN_VALUE)` | Có kết quả rộng hơn |
| Narrow sau negate | Cast `long` về `int` | — | Phải kiểm tra phạm vi nếu cần kết quả đúng |

### Những thuộc tính hữu ích khi tự động hóa

Với mọi `int x` khác `Integer.MIN_VALUE`:

```java
StrictMath.negateExact(
        StrictMath.negateExact(x)) == x
```

Vì phép đổi dấu lần đầu trả một giá trị hợp lệ (khác `Integer.MIN_VALUE`), lần thứ hai trở lại input. Với `x = Integer.MIN_VALUE`, ngay lời gọi thứ nhất phải **ném exception**, không đưa vào phép so sánh.

Tương tự với `long x` khác `Long.MIN_VALUE`.

Có thể test “đảo dấu hai lần trở về điểm xuất phát” cho nhiều input ngẫu nhiên, nhưng **phải test riêng các điểm biên**. Kiểm thử ngẫu nhiên thuần túy gần như chắc chắn bỏ qua đúng `MIN_VALUE` trong không gian 32/64 bit.

### Đảm bảo test phân biệt toán tử và API

Một test chỉ làm:

```java
assert StrictMath.negateExact(-1) == 1;
```

không thể phát hiện lập trình viên thay nhầm bằng `-x` vì cả hai đều trả 1 khi input bình thường. Test quan trọng nhất là **MIN_VALUE phải ném `ArithmeticException`**.

Có thể dùng JUnit nếu dự án có framework test, nhưng chương trình đầy đủ ở phần 5 không cần dependency bên ngoài và kiểm tra cùng những tính chất cốt lõi bằng `AssertionError`. Không cần bật `-ea` vì `check(...)` là code gọi explicit, không phải Java keyword `assert`.

## 12. Cách đọc và chọn overload khi type inference gây nhầm

`StrictMath.negateExact` chọn kiểu theo biểu thức **trước khi gọi method**, không theo kiểu biến ở vế trái sau khi có kết quả.

```java
int a = -10;
long resultA = StrictMath.negateExact(a);     // chọn int, rồi widen sang long
long resultB = StrictMath.negateExact((long) a); // chọn long
```

Hai giá trị đều là 10 vì `-10` an toàn ở cả hai kiểu. Nhưng khi `a = Integer.MIN_VALUE`, `resultA` ném ngoại lệ và `resultB` trả `2_147_483_648L`.

### Literal và biểu thức phức hợp

```java
int x = 3;
long y = StrictMath.negateExact(x + 1L); // x + 1L là long
```

Kiểu biểu thức `x + 1L` là `long` theo *binary numeric promotion*, nên chọn overload `long`. Nhưng nếu `x + 1` thực hiện **tràn trong int trước khi gọi**, `negateExact` chỉ thấy **giá trị đã bị tràn** và không có cách nào khôi phục toán hạng ban đầu.

Ví dụ:

```java
int max = Integer.MAX_VALUE;
int wrapped = max + 1;        // Integer.MIN_VALUE
// StrictMath.negateExact(wrapped) ném ArithmeticException.
// Nó chỉ phát hiện xấu ở bước đổi dấu, không chỉ ra phép cộng trước đã tràn.
```

Để phát hiện phép cộng ngay tại nơi xảy ra:

```java
int checkedSum = Math.addExact(max, 1); // ArithmeticException
```

**Nguyên tắc:** kiểm tra tràn **từng phép toán cần chính xác**, không chỉ kiểm tra tại bước cuối. `negateExact` không “rửa sạch” hoặc phát hiện mọi lỗi đã xảy ra trước đó.

## 13. `StrictMath.negateExact` không giải quyết mọi yêu cầu số học

| Bài toán | Lựa chọn phù hợp | Vì sao |
| --- | --- | --- |
| Đổi dấu `int`/`long` và muốn ném khi tràn | `StrictMath.negateExact` hoặc `Math.negateExact` | Đúng hợp đồng checked negation |
| Cộng/trừ/nhân nguyên và muốn ném khi tràn | `Math.addExact`, `subtractExact`, `multiplyExact` hoặc đối ứng `StrictMath` | Kiểm tra tại từng phép toán |
| Chuyển `long` sang `int` và muốn ném khi vượt phạm vi | `Math.toIntExact` | Kiểm tra narrowing conversion |
| Đổi dấu `Long.MIN_VALUE` thành số dương chính xác | `BigInteger.valueOf(x).negate()` | Kết quả nằm ngoài phạm vi `long` |
| Đổi dấu số tiền thập phân chính xác | `BigDecimal.negate()` khi domain phù hợp | Không dùng floating-point cho tiền nếu cần decimal exact |
| Cố ý dùng số học nguyên wraparound | Toán tử nguyên theo hợp đồng code | Không cần `negateExact` nếu wrap là ngữ nghĩa thiết kế |
| Giới hạn/saturating arithmetic | Thuật toán saturating được định nghĩa rõ | `negateExact` ném lỗi, không tự clamp |

**Tránh sự nhầm lẫn “exact nghĩa là BigInteger”:** `negateExact` không mở rộng số bit lưu trữ. Nó hoặc trả đúng số đối **trong cùng kiểu nguyên**, hoặc ném exception. Nếu giá trị toán học hợp lệ nhưng kiểu không đủ rộng, **đổi kiểu dữ liệu/đích trả về** mới giải quyết được.

## 14. Những lỗi thường gặp

| Lỗi / suy nghĩ sai | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Dùng `-x` cho giá trị phải không tràn | `MIN_VALUE` wrap thành chính nó | `StrictMath.negateExact(x)` |
| Nghĩ mọi input âm đều có số đối dương cùng kiểu | `MIN_VALUE` không có số đối biểu diễn được | Kiểm tra tràn hoặc nới kiểu |
| Gọi `StrictMath.negateExact(Integer.MIN_VALUE)` rồi kỳ vọng số dương `int` | Không tồn tại kết quả int đó | Chấp nhận exception hoặc tính theo long |
| Cast kết quả sang long **sau** khi gọi overload int | Ngoại lệ đã xảy ra trước cast | Cast input `(long) x` trước |
| Cast long chứa `2_147_483_648L` về int | Có thể wrap trở lại số âm | `Math.toIntExact` nếu cần checked narrowing |
| Tính `-Long.MIN_VALUE` trước khi tạo `BigInteger` | Giá trị đã wrap, mất số mong muốn | `BigInteger.valueOf(x).negate()` |
| Nhầm `negateExact` với `abs` | Số dương bị đổi thành âm thay vì giữ nguyên | Chọn theo mục đích |
| Nghĩ `StrictMath` làm phép nguyên “exact hơn” `Math` | Cùng hợp đồng exact integer negation | Chọn style nhất quán |
| Cho rằng `negateExact` nhận `double` | Không có overload phù hợp | Dùng đúng API cho floating-point |
| Bỏ qua kiểu byte/short khi cast ngược | Kết quả 128 từ byte -128 bị narrowing wrap | Kiểm tra miền đích trước cast |
| Chỉ test `-1`, `1`, không test `MIN_VALUE` | Không phát hiện điểm tràn duy nhất | Có boundary tests |
| Bắt `ArithmeticException` rồi trả input hoặc `0` | Che lỗi, tạo dữ liệu sai | Fail/validate/domain exception có cause |
| Nghĩ `negateExact` phát hiện phép cộng đã tràn trước đó | Chỉ kiểm tra phép đổi dấu được gọi | Dùng `addExact` cho phép cộng |
| So sánh chuỗi message của `ArithmeticException` | Test phụ thuộc runtime | Test loại exception và kết quả |
| Cập nhật state trước phép toán checked | Có thể để lại partial side effects khi ném exception | Tính/validate trước, dùng transaction khi cần |

## 15. Checklist ứng dụng

1. **Kiểu input đúng chưa?** `int`/`long`, hay `byte`/`short` được promote?
2. **Kết quả cần nằm trong cùng kiểu không?** Nếu bắt buộc, dùng `negateExact` và xử lý trường hợp `MIN_VALUE`.
3. **Nếu domain cho phép kết quả rộng hơn, đã widen trước khi đổi dấu chưa?**
4. **Nếu là `Long.MIN_VALUE` và cần số dương thật, đã chọn `BigInteger` chưa?**
5. **Nếu có phép cộng/trừ/nhân trước đó, đã kiểm tra tràn tại các phép toán đó chưa?**
6. **Đã kiểm tra không narrowing cast âm thầm sau bước checked negation chưa?**
7. **Các test có 0, giá trị thường, MAX_VALUE và MIN_VALUE cho cả `int`/`long` không?**
8. **Ứng dụng có xử lý `ArithmeticException` ở tầng thích hợp, không che lỗi không?**
9. **Nếu ghi database hoặc cập nhật state, đã tính toán trước side effects và có transaction khi cần chưa?**
10. **Đang dùng Java 14+ và API chính thức hiện còn hỗ trợ, không dựa trên tính năng preview không?**

## 16. Bài tập ngắn có đáp án

**Bài 1.** `StrictMath.negateExact(0)` và `StrictMath.negateExact(-7)` cho kết quả gì?

**Đáp án:** `0` và `7`.

**Bài 2.** `StrictMath.negateExact(Integer.MIN_VALUE)` trả `Integer.MIN_VALUE` hay ném lỗi?

**Đáp án:** Ném `ArithmeticException`; chính giá trị `Integer.MIN_VALUE` là trường hợp overflow khi đổi dấu kiểu int.

**Bài 3.** `-Integer.MIN_VALUE` cho kết quả gì?

**Đáp án:** Trả lại `Integer.MIN_VALUE` do phép đổi dấu một ngôi trên `int` tràn theo bù hai, không có exception.

**Bài 4.** `long x = StrictMath.negateExact((long) Integer.MIN_VALUE);` có hợp lệ không?

**Đáp án:** Có, kết quả là `2_147_483_648L`. Cast trước phép toán khiến overload `long` được gọi.

**Bài 5.** Vì sao `long x = (long) StrictMath.negateExact(Integer.MIN_VALUE);` không tương đương bài 4?

**Đáp án:** Overload `int` chạy trước và ném exception; cast ngoài không bao giờ tới lượt.

**Bài 6.** Muốn tính số đối của `Long.MIN_VALUE` chính xác, dùng gì?

**Đáp án:** `BigInteger.valueOf(Long.MIN_VALUE).negate()`; kết quả là `9223372036854775808`, không thể chứa trong `long`.

**Bài 7.** `Math.negateExact` và `StrictMath.negateExact` khác về xử lý overflow của `int` không?

**Đáp án:** Không. Cùng hợp đồng giá trị/`ArithmeticException`; khác ở class chứa method và mốc bổ sung API (`Math` từ Java 8, `StrictMath` từ Java 14).

**Bài 8.** Nếu tính `int sum = a + b;` đã overflow rồi mới gọi `StrictMath.negateExact(sum)`, method có phát hiện được lỗi của phép cộng ban đầu không?

**Đáp án:** Không bảo đảm. `negateExact` chỉ kiểm tra phép đổi dấu của **giá trị sum đã nhận**. Dùng `Math.addExact(a,b)` ngay tại phép cộng khi cần an toàn.

## 17. Nguồn tài liệu chính thức còn áp dụng

- [Oracle Java 25 API — `StrictMath`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StrictMath.html): chữ ký `negateExact(int/long)`, `Since: 14` và ngoại lệ khi overflow.
- [Oracle Java 14 API — `StrictMath`](https://docs.oracle.com/en/java/javase/14/docs/api/java.base/java/lang/StrictMath.html): xác nhận thời điểm phương thức được bổ sung trong Java 14.
- [Oracle Java 25 API — `Math`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html): `negateExact`, `subtractExact`, `addExact` và `toIntExact`.
- [Oracle Java 25 API — `BigInteger`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigInteger.html): `valueOf(long)` và `negate()` cho số nguyên vượt `long`.
- [Java Language Specification 25 — Unary Minus Operator](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.15.4): quy tắc toán tử `-` với số nguyên và trường hợp `MIN_VALUE`.

**Ghi nhớ:** `StrictMath.negateExact` có từ **Java 14** và vẫn hữu ích trong Java hiện đại để **đổi dấu `int`/`long` mà không âm thầm chấp nhận tràn**. Nó **chỉ ném `ArithmeticException` ở `MIN_VALUE`**, không mở rộng kiểu trả về. Nếu cần kết quả lớn hơn giới hạn kiểu, **widen trước khi đổi dấu** hoặc dùng `BigInteger`; nếu có nhiều phép toán liên tiếp, hãy kiểm tra tràn ở **từng phép toán cần chính xác**.
