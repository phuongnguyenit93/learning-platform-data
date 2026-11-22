# Cộng, trừ, nhân và kiểu của kết quả trong số học nguyên Java

## 1. Câu hỏi quan trọng: phép tính chạy bằng kiểu nào?

Với biểu thức số nguyên trong Java, **kiểu của kết quả được xác định từ toán hạng và quy tắc thăng cấp số học** (*numeric promotion*). Kiểu của biến nằm **bên trái phép gán** không tự làm phép cộng, trừ hoặc nhân ở vế phải chạy trên kiểu rộng hơn.

Ví dụ:

```java
int a = 1_500_000_000;
int b = 2;

int wrapped = a * b;        // phép nhân int, tràn số
long stillWrapped = a * b;  // phép nhân vẫn là int, rồi mới đổi sang long
long correct = (long) a * b; // phép nhân long, kết quả chính xác
```

Ở đây, giá trị toán học của \(1\,500\,000\,000 \times 2\) là \(3\,000\,000\,000\), lớn hơn `Integer.MAX_VALUE`. Hai biểu thức `a * b` đầu tiên có **kiểu `int`**, đều cho kết quả -1_294_967_296 do tràn; biến `long` chỉ chứa bản mở rộng có dấu của kết quả đã tràn. Biểu thức `(long) a * b` được thực hiện bằng `long` và cho 3_000_000_000.

Bài học tập trung vào ba toán tử nhị phân:

- `+`: cộng.
- `-`: trừ.
- `*`: nhân.

Chúng áp dụng cho các kiểu số nguyên `byte`, `short`, `char`, `int` và `long`. Với toán hạng nguyên thủy, phải hiểu **thăng cấp**, **miền giá trị**, **tràn số**, **chuyển kiểu**, và **thứ tự đánh giá** để dự đoán đúng kết quả.

## 2. Quy tắc thăng cấp kiểu của phép cộng, trừ và nhân

### 2.1. Thăng cấp số học nhị phân (*binary numeric promotion*)

Đối với hai toán hạng có kiểu tích phân nguyên thủy, Java áp dụng các quy tắc trọng tâm:

1. `byte`, `short` và `char` được **thăng cấp thành `int`** trước khi thực hiện phép cộng, trừ hoặc nhân.
2. Nếu một trong hai toán hạng là `long`, toán hạng còn lại được chuyển thành `long` và **kết quả có kiểu `long`**.
3. Nếu không có `long`, kết quả có **kiểu `int`**.

Bảng minh họa:

| Kiểu toán hạng trái | Kiểu toán hạng phải | Kiểu của `a + b`, `a - b`, `a * b` |
|---|---|---|
| `byte` | `byte` | `int` |
| `short` | `short` | `int` |
| `byte` | `short` | `int` |
| `char` | `char` | `int` |
| `char` | `int` | `int` |
| `int` | `int` | `int` |
| `int` | `long` | `long` |
| `long` | `long` | `long` |

Quy tắc không phụ thuộc **giá trị thực tế đang nhỏ hay lớn**. Ví dụ `byte x = 1; byte y = 2;` thì `x + y` có kiểu `int` dù số 3 hoàn toàn nằm trong miền `byte`.

Trong phạm vi bài này chỉ xét toán hạng tích phân. Nếu một toán hạng là `float` hoặc `double`, quy tắc *binary numeric promotion* rộng hơn sẽ cho kết quả số thực; không dùng bảng trên để suy luận về biểu thức trộn số nguyên và số thực.

### 2.2. Kiểu của biểu thức khác kiểu của biến nhận kết quả

```java
byte first = 10;
byte second = 20;

// byte sum = first + second; // LỖI: kết quả phép cộng có kiểu int
int sum = first + second;     // hợp lệ, sum = 30
byte narrowed = (byte) (first + second); // hợp lệ khi ép kiểu chủ động

long x = 1L + 2;  // 1L là long => phép cộng cho long
long y = 1 + 2;   // phép cộng cho int (3), sau đó mới nới rộng thành long
```

Dòng `long y = 1 + 2;` chạy đúng vì 3 không tràn, nhưng không nên kết luận phép cộng đã được tính bằng `long`.

### 2.3. Dấu cộng/trừ một ngôi cũng có thăng cấp

Các toán tử dấu `+x`, `-x` chỉ có **một toán hạng**. Khi `x` là `byte`, `short` hoặc `char`, kết quả dấu một ngôi có kiểu `int`; `long` vẫn là `long`.

```java
byte b = 5;
int negative = -b;   // -b có kiểu int, giá trị -5
char c = 'A';
int code = +c;       // +c có kiểu int, giá trị 65
long n = 10L;
long flipped = -n;   // kiểu long, giá trị -10
```

Không đánh đồng `-x` một ngôi với `a - b` hai ngôi; cả hai có thể tràn nếu kết quả toán học vượt miền biểu diễn tương ứng.

## 3. Cách tính cộng, trừ và nhân

### 3.1. Cộng (`+`)

Phép `a + b` tính tổng. Ví dụ `7 + 5` là 12. Khi cả hai toán hạng là `int`, phép tính được thực hiện trong miền số nguyên 32 bit. Nếu có `long`, phép tính được thực hiện trong miền 64 bit.

Dấu `+` còn dùng để **nối chuỗi**: `"total=" + 5` tạo chuỗi `"total=5"`. Đây không phải phép cộng số nguyên; luôn xét kiểu toán hạng trước khi suy luận về `+`. Ví dụ, `"sum=" + 2 + 3` cho `"sum=23"` vì phép toán đánh giá từ trái sang phải; `"sum=" + (2 + 3)` mới cho `"sum=5"`.

### 3.2. Trừ (`-`)

Phép `a - b` tính hiệu; `7 - 5` là 2. Khi trừ số âm, giá trị toán học có thể tăng; ví dụ `7 - (-5)` bằng 12. Đừng chỉ kiểm tra trường hợp cộng số dương khi đánh giá nguy cơ tràn: `Integer.MIN_VALUE - 1` cũng tràn.

### 3.3. Nhân (`*`)

Phép `a * b` tính tích; `7 * 5` là 35. Phép nhân dễ vượt miền ngay cả khi **mỗi toán hạng đều hợp lệ**. Ví dụ, mỗi toán hạng 1_500_000_000 đều là `int` hợp lệ nhưng tích với 2 không còn vừa `int`.

Số 0 là phần tử hấp thụ của phép nhân nguyên: `x * 0` luôn bằng 0. Số 1 là phần tử đơn vị: `x * 1` có cùng giá trị x. Tuy nhiên, kết quả biểu thức vẫn theo quy tắc thăng cấp kiểu; `byte x` nhân `1` cho biểu thức kiểu `int`.

## 4. Độ ưu tiên, kết hợp và thứ tự đánh giá

Phép nhân `*` có **độ ưu tiên cao hơn** phép cộng/trừ `+`, `-`; cộng và trừ cùng mức và kết hợp từ trái sang phải:

```java
int a = 2 + 3 * 4;   // 14
int b = (2 + 3) * 4; // 20
int c = 10 - 3 - 2;  // (10 - 3) - 2 = 5
int d = 10 - (3 - 2); // 9
```

Java đánh giá các toán hạng của toán tử nhị phân theo **thứ tự từ trái sang phải**; với `a() + b()`, `a()` được đánh giá trước `b()`. Đây là thứ tự đánh giá toán hạng, không làm thay đổi độ ưu tiên toán tử.

Ngoài ra, **các phép toán nguyên có thể tràn**, nên biến đổi đại số chỉ an toàn nếu vẫn giữ ý nghĩa nghiệp vụ. Ví dụ, để tránh tràn, `(long) a + b` khác `(long) (a + b)` khi tổng `int` vượt miền. Cả hai có cùng dạng gần như đại số, nhưng thời điểm nâng kiểu khác nhau.

## 5. Ví dụ Java chạy được: giá trị và kiểu kết quả

Tạo tệp `IntegerArithmeticDemo.java`:

```java
public class IntegerArithmeticDemo {
    private static String typeOf(int value) {
        return "int";
    }

    private static String typeOf(long value) {
        return "long";
    }

    public static void main(String[] args) {
        byte smallA = 120;
        byte smallB = 10;
        short shortA = 30_000;
        short shortB = 1_000;
        char letter = 'A';
        int big = 1_500_000_000;
        int multiplier = 2;

        System.out.println("byte + byte = " + (smallA + smallB));
        System.out.println("type byte + byte = " + typeOf(smallA + smallB));
        System.out.println("short * short = " + (shortA * shortB));
        System.out.println("char + int = " + (letter + 1));
        System.out.println("type char + int = " + typeOf(letter + 1));
        System.out.println("type int + long = " + typeOf(1 + 2L));
        System.out.println("int * int = " + (big * multiplier));
        System.out.println("assigned to long = " + (long) (big * multiplier));
        System.out.println("long * int = " + ((long) big * multiplier));
        System.out.println("max + 1 = " + (Integer.MAX_VALUE + 1));
        System.out.println("min - 1 = " + (Integer.MIN_VALUE - 1));
        System.out.println("2 + 3 * 4 = " + (2 + 3 * 4));
        System.out.println("(2 + 3) * 4 = " + ((2 + 3) * 4));
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac IntegerArithmeticDemo.java
java IntegerArithmeticDemo
```

Kết quả chính xác:

```text
byte + byte = 130
type byte + byte = int
short * short = 30000000
char + int = 66
type char + int = int
type int + long = long
int * int = -1294967296
assigned to long = -1294967296
long * int = 3000000000
max + 1 = -2147483648
min - 1 = 2147483647
2 + 3 * 4 = 14
(2 + 3) * 4 = 20
```

Hai phương thức `typeOf` overload chỉ để **chứng minh kiểu tĩnh mà compiler chọn**: nếu đối số là `int`, gọi `typeOf(int)`; nếu là `long`, gọi `typeOf(long)`. Các số 130 và 30_000_000 chứng minh kết quả của `byte + byte` và `short * short` được tính trên `int`, thay vì tự giới hạn vào miền `byte`/`short`.

## 6. Overflow và underflow: giá trị quay vòng ở độ rộng cố định

### 6.1. Miền biểu diễn liên quan

| Kiểu kết quả của phép toán | Miền số có dấu |
|---|---|
| `int` (32 bit) | -2_147_483_648 tới 2_147_483_647 |
| `long` (64 bit) | -9_223_372_036_854_775_808 tới 9_223_372_036_854_775_807 |

Với `+`, `-`, `*` nguyên, Java tính kết quả theo **độ rộng của kiểu phép toán**. Nếu kết quả toán học không nằm trong miền của kiểu có dấu, phần bit cao vượt độ rộng bị loại bỏ và mẫu bit còn lại được diễn giải theo bù hai (*two's complement*). Có thể hình dung kết quả được lấy modulo \(2^{32}\) đối với `int` hoặc \(2^{64}\) đối với `long`, rồi diễn giải có dấu.

Ví dụ:

- `Integer.MAX_VALUE + 1` → `Integer.MIN_VALUE`.
- `Integer.MIN_VALUE - 1` → `Integer.MAX_VALUE`.
- `1_500_000_000 * 2` → -1_294_967_296 (phép nhân `int`).
- `Long.MAX_VALUE + 1L` → `Long.MIN_VALUE`.

Cả **overflow** (vượt giới hạn lớn nhất) và **underflow ở phía âm** (nhỏ hơn giới hạn dưới) đều có thể làm sai giá trị mong đợi trong số học nguyên. Những phép `+`, `-`, `*` thông thường **không tự ném ngoại lệ** khi vượt miền.

### 6.2. Nới rộng kiểu trước hay sau phép tính

Để một phép tính chạy bằng `long`, ít nhất một toán hạng phải là `long` **trước khi toán tử thực thi**:

```java
int a = 1_500_000_000;
int b = 2;

long wrong = a * b;             // -1294967296 (int đã tràn)
long alsoWrong = (long) (a * b); // -1294967296
long right = (long) a * b;      // 3000000000
long alsoRight = a * 2L;        // 3000000000
```

Việc gán sang `long` sau phép tính không khôi phục các bit đã mất. Ngay cả `long` cũng có giới hạn: nếu tích lớn hơn `Long.MAX_VALUE` hoặc nhỏ hơn `Long.MIN_VALUE`, phép nhân `long` vẫn có thể tràn.

### 6.3. Số nhỏ nhất đổi dấu vẫn tràn

Miền số có dấu **không đối xứng**: `Integer.MIN_VALUE` là -2_147_483_648, nhưng `Integer.MAX_VALUE` chỉ 2_147_483_647. Do đó:

```java
int min = Integer.MIN_VALUE;
System.out.println(-min);              // -2147483648
System.out.println(min * -1);           // -2147483648
System.out.println(Math.abs(min));      // -2147483648
```

Các trường hợp này đều không tạo ra số dương như trực giác toán học vì +2_147_483_648 không có trong miền `int`. `Long.MIN_VALUE` cũng có tính chất tương tự đối với `long`.

## 7. Kiểm tra tràn số bằng các phương thức `Math.*Exact`

Nếu tràn số là **lỗi nghiệp vụ**, Java cung cấp phép toán kiểm tra:

| Phương thức | Công dụng |
|---|---|
| `Math.addExact(a, b)` | Cộng, ném `ArithmeticException` nếu tràn |
| `Math.subtractExact(a, b)` | Trừ, ném ngoại lệ nếu tràn |
| `Math.multiplyExact(a, b)` | Nhân, ném ngoại lệ nếu tràn |
| `Math.negateExact(value)` | Đổi dấu, ném ngoại lệ với giá trị nhỏ nhất |
| `Math.toIntExact(longValue)` | Thu hẹp `long` sang `int`, ném ngoại lệ nếu ngoài miền |

`addExact`, `subtractExact` và `multiplyExact` có các overload cho số nguyên với độ rộng phù hợp; kiểu kết quả của overload nhận hai `int` là `int`, hai `long` là `long`. `Math.multiplyExact` cũng có overload cho `long` và `int` trong Java hiện đại.

Tạo tệp `CheckedArithmeticDemo.java`:

```java
public class CheckedArithmeticDemo {
    public static void main(String[] args) {
        System.out.println("safe sum = " + Math.addExact(7, 5));
        System.out.println("safe diff = " + Math.subtractExact(7, 5));
        System.out.println("safe product = " + Math.multiplyExact(7, 5));

        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException e) {
            System.out.println("addExact: overflow");
        }

        try {
            Math.subtractExact(Integer.MIN_VALUE, 1);
        } catch (ArithmeticException e) {
            System.out.println("subtractExact: overflow");
        }

        try {
            Math.multiplyExact(1_500_000_000, 2);
        } catch (ArithmeticException e) {
            System.out.println("multiplyExact: overflow");
        }

        long exactLong = (long) 1_500_000_000 * 2;
        System.out.println("long product = " + exactLong);

        try {
            Math.toIntExact(exactLong);
        } catch (ArithmeticException e) {
            System.out.println("toIntExact: outside int range");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac CheckedArithmeticDemo.java
java CheckedArithmeticDemo
```

Kết quả:

```text
safe sum = 12
safe diff = 2
safe product = 35
addExact: overflow
subtractExact: overflow
multiplyExact: overflow
long product = 3000000000
toIntExact: outside int range
```

**Không bắt `ArithmeticException` rồi tiếp tục sử dụng một kết quả số đã sai.** Hãy xác định cách xử lý lỗi phù hợp: thông báo dữ liệu vượt giới hạn, từ chối phép tính, hoặc chuyển sang một cách biểu diễn số rộng hơn.

Nếu nghiệp vụ yêu cầu số nguyên vượt cả miền `long`, dùng `java.math.BigInteger`:

```java
import java.math.BigInteger;

BigInteger a = BigInteger.valueOf(Long.MAX_VALUE);
BigInteger bigger = a.add(BigInteger.ONE);  // 9223372036854775808
BigInteger squared = bigger.multiply(bigger);
```

Đoạn mã `BigInteger` chỉ minh họa **các biểu thức đặt trong một phương thức**, không phải một tệp Java độc lập. `BigInteger` dùng các phương thức như `add`, `subtract`, `multiply` và không hỗ trợ toán tử `+`/`-`/`*` cho hai đối tượng.

## 8. Phép gán, ép kiểu và toán tử gán kết hợp

### 8.1. Gán thông thường yêu cầu kiểu tương thích

```java
byte x = 10;
byte y = 20;

// byte total = x + y; // LỖI BIÊN DỊCH: x + y là int
int total = x + y;     // hợp lệ
byte narrowed = (byte) (x + y); // ép kiểu tường minh
```

Nếu tổng `int` không nằm trong miền `byte`, phép ép sẽ chỉ giữ 8 bit thấp và có thể làm **thay đổi giá trị**:

```java
byte x = 120;
byte y = 10;
byte result = (byte) (x + y); // 130 -> -126
```

### 8.2. `+=`, `-=` và `*=` có ép kiểu ngầm

Với toán tử gán kết hợp, Java thực hiện một phép toán trên các toán hạng đã thăng cấp rồi **chuyển kết quả về kiểu của biến vế trái**, tương tự:

```java
// Với biến kiểu T:
x += y;          // gần tương đương: x = (T) (x + y)
x -= y;          // gần tương đương: x = (T) (x - y)
x *= y;          // gần tương đương: x = (T) (x * y)
```

Chữ `T` chỉ là ký hiệu kiểu trong **mã giả minh họa**. Hai cách viết không hoàn toàn tương đương khi `x` là biểu thức có tác dụng phụ: toán tử gán kết hợp **chỉ đánh giá vế trái một lần**. Điểm cần nhớ ở đây là phép chuyển kiểu ngầm có thể làm mất bit.

Ví dụ:

```java
byte b = 120;
b += 10;  // tương đương về giá trị với (byte) (120 + 10)
System.out.println(b); // -126

short s = 30_000;
s *= 2; // phép nhân thành int rồi thu hẹp về short
System.out.println(s); // -5536
```

Ở ví dụ `short`, số 60_000 vượt miền `short` (-32_768..32_767), và việc giữ 16 bit thấp cho -5_536. **`+=` và `*=` không tự bảo vệ chống tràn hoặc thu hẹp kiểu.**

### 8.3. Biểu thức hằng số khi biên dịch là ngoại lệ cần biết

Java cho phép một số **biểu thức hằng** kiểu `int` gán trực tiếp vào `byte`, `short` hoặc `char` nếu giá trị biểu diễn được:

```java
byte a = 100 + 20;       // hợp lệ: biểu thức hằng int bằng 120
short b = 10_000 * 3;    // hợp lệ: hằng int bằng 30000
char c = 'A' + 1;        // hợp lệ: hằng int bằng 66, nằm trong miền char

// byte bad = 100 + 30;  // lỗi biên dịch: 130 vượt miền byte

int variable = 20;
// byte another = 100 + variable; // lỗi: không còn là hằng biểu diễn được
```

Dòng `char c = 'A' + 1;` biên dịch được vì kết quả là **hằng số `int` 66** được phép chuyển hẹp ở bước gán. Nó **không** chứng minh toán tử cộng trên `char` trả `char`: kiểu của biểu thức cộng vẫn là `int`. Một `char current` không phải hằng số biên dịch thông thường muốn tăng bằng phép `+` rồi gán lại `char` sẽ cần ép kiểu hoặc `+=`.

## 9. Kết hợp với literal, wrapper và autoboxing

### 9.1. Literal quyết định kiểu trung gian

```java
long a = 2_000_000_000 + 1_000_000_000;  // phép cộng int bị tràn
long b = 2_000_000_000L + 1_000_000_000; // phép cộng long = 3000000000
```

Dấu `L` biến literal đầu thành `long`, do đó toán hạng còn lại được nâng lên `long` và kết quả phép cộng có kiểu `long`. Nếu muốn ép rõ ràng, viết `(long) first + second` thay vì `(long) (first + second)`.

### 9.2. Wrapper được unbox trước khi tính

Khi dùng `Integer`, `Long` hoặc các wrapper khác trong biểu thức số học, Java có thể **unbox** thành giá trị nguyên thủy rồi áp dụng thăng cấp số học:

```java
Integer a = 10;
Long b = 20L;
long sum = a + b; // unbox int/long, thăng cấp lên long => 30
```

Nếu một wrapper là `null`, unboxing sẽ ném `NullPointerException` **trước khi phép toán hoàn tất**. Vì thế cần kiểm tra null khi dữ liệu wrapper có thể không có giá trị.

Không dùng `Integer`/`Long` để kỳ vọng tự động tránh tràn: sau unboxing, các phép toán vẫn chịu miền `int`/`long` tương ứng.

## 10. Cách áp dụng an toàn trong chương trình

Có ba tình huống chính:

**Tình huống A — chắc chắn phép toán vừa `int`:** dùng `int` bình thường, nhưng dựa trên ràng buộc miền đầu vào có thể kiểm tra được. Ví dụ hai số đếm nhỏ trong khoảng 0..1000 sẽ có tổng nhiều nhất 2000.

**Tình huống B — `int` có thể tràn nhưng `long` đủ rộng:** chủ động nâng toán hạng **trước khi tính**, chẳng hạn `long total = (long) quantity * unitPrice;` khi cả hai biến nguồn là `int`. Kiểm tra thêm ràng buộc nghiệp vụ nếu `long` cũng có khả năng vượt miền.

**Tình huống C — tràn số phải được phát hiện:** dùng `Math.addExact`, `subtractExact`, `multiplyExact` hoặc thiết kế dữ liệu với `BigInteger` khi miền không cố định. Không coi kết quả phép tính tràn số là dữ liệu hợp lệ nếu nghiệp vụ không có quy tắc wraparound.

Đối với yêu cầu đếm byte, thời gian, tổng tiền, tích số lượng và giá đơn vị, nên xác định **giá trị lớn nhất hợp lệ** trước khi chọn kiểu. Nếu cần số tiền thập phân, độ chính xác của tiền tệ là vấn đề riêng: thường cân nhắc `BigDecimal` hoặc lưu đơn vị tiền nhỏ nhất dưới dạng số nguyên theo quy ước rõ ràng.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách sửa |
|---|---|---|
| `byte result = a + b;` báo lỗi | `byte + byte` cho kiểu `int` | Dùng `int` hoặc ép kiểu có kiểm tra |
| `long total = a * b;` vẫn sai | Hai `int` nhân trước rồi mới gán sang `long` | Viết `(long) a * b` |
| `Integer.MAX_VALUE + 1` thành số âm | Tràn `int` 32 bit | Dùng `long` trước phép cộng hoặc `addExact` |
| `Integer.MIN_VALUE - 1` thành số dương | Vượt giới hạn âm `int` | Dùng kiểu rộng hơn hoặc `subtractExact` |
| `-Integer.MIN_VALUE` vẫn âm | Giá trị dương đối xứng ngoài miền `int` | Dùng `negateExact` hoặc chuyển sang `long` trước |
| `b += 10` làm `byte` thành âm | Gán kết hợp thu hẹp kết quả ngầm | Tính trên `int`, kiểm tra miền trước khi ép |
| `Math.multiplyExact(a, b)` ném lỗi | Tích ngoài miền kiểu của overload | Chọn `long`/`BigInteger` hoặc xử lý overflow |
| `"sum=" + 2 + 3` in `sum=23` | Toán tử `+` đang nối chuỗi từ trái sang phải | Viết `"sum=" + (2 + 3)` |
| Wrapper số học gây `NullPointerException` | Unboxing giá trị `null` | Kiểm tra wrapper trước phép toán |

## 12. Tự kiểm tra

**Câu 1.** `byte a = 1; byte b = 2;` thì `a * b` có kiểu gì?  
**Đáp án:** `int`, dù tích bằng 2 và vừa trong `byte`.

**Câu 2.** `short a = 100; short b = 20;` thì `a - b` có kiểu gì?  
**Đáp án:** `int`, giá trị 80.

**Câu 3.** `long x = Integer.MAX_VALUE + 1;` có giá trị bao nhiêu?  
**Đáp án:** -2_147_483_648, vì phép cộng hai `int` tràn trước khi gán sang `long`.

**Câu 4.** Viết biểu thức nhân hai biến `int` `price` và `count` nhưng tính bằng `long`.  
**Đáp án:** `(long) price * count` hoặc `price * (long) count`.

**Câu 5.** `byte b = 120; b += 10;` cho kết quả gì?  
**Đáp án:** -126 vì biểu thức cộng bằng `int` cho 130, sau đó bị thu hẹp về `byte`.

**Câu 6.** Khi nào `Math.multiplyExact` phù hợp hơn `*`?  
**Đáp án:** Khi tích vượt miền số nguyên phải được coi là lỗi và cần phát hiện bằng `ArithmeticException`.

**Câu 7.** Vì sao `char c = 'A' + 1;` hợp lệ nhưng một biểu thức `charVariable + 1` có kiểu `int`?  
**Đáp án:** Cả hai phép cộng đều cho kiểu `int`. Ở trường hợp đầu, đó là hằng số `int` 66 nằm trong miền `char` nên compiler cho phép phép gán thu hẹp đặc biệt.

**Câu 8.** `10 - 3 - 2` và `10 - (3 - 2)` khác nhau thế nào?  
**Đáp án:** Lần lượt là 5 và 9, vì `-` nhị phân kết hợp trái; dấu ngoặc thay đổi thứ tự phép toán.

**Ghi nhớ:** Với số nguyên Java, **`byte`/`short`/`char` được thăng cấp thành `int` khi cộng, trừ, nhân; có `long` thì kết quả `long`**. Kết quả được tính ở kiểu của **biểu thức**, sau đó mới được gán. Muốn tránh tràn, nâng kiểu **trước phép tính** hoặc dùng `Math.*Exact` để phát hiện và xử lý kết quả ngoài miền.
