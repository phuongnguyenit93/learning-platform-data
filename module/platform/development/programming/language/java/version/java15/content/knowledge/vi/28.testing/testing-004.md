# Kiểm thử `CharSequence` tùy biến và số nguyên nhỏ nhất (`Integer.MIN_VALUE`)

Trong Java 15, hai thay đổi API nhỏ nhưng rất đáng kiểm thử là **`CharSequence.isEmpty()`** và **`Math.absExact(int/long)`**. Cả hai vẫn tồn tại và hữu ích trong các phiên bản Java hiện đại. Bài học tập trung vào hai nhóm ca kiểm thử: (1) một lớp tự triển khai `CharSequence` phải tuân thủ hợp đồng về độ dài, chỉ số và chuỗi con; (2) phép lấy trị tuyệt đối phải xử lý chính xác giá trị nguyên nhỏ nhất, nơi phép toán thông thường có thể tràn.

Ngữ cảnh học là **kiểm thử**. Vì thế, mỗi khái niệm đều đi kèm các bất biến (*invariant*), đầu vào biên, kết quả kỳ vọng và cách viết bài test có thể tái chạy trên Java 17+. Java 15 được nhắc ở đây như mốc giới thiệu API; không cần sử dụng một JDK đã hết vòng hỗ trợ để áp dụng nội dung.

## 1. Điều cần chứng minh bằng test

| Đối tượng kiểm thử | Điều kiện cần bảo đảm | Ca biên quan trọng |
| --- | --- | --- |
| `CharSequence` tự cài đặt | `length()`, `charAt()`, `subSequence()` và `toString()` nhất quán | Chuỗi rỗng, một ký tự, cắt đầu/cuối, chỉ số âm, chỉ số bằng độ dài, vùng ngược |
| `CharSequence.isEmpty()` | Mặc định trả `length() == 0`; kế thừa hoạt động với lớp tùy biến | `""` là rỗng, `" "` **không** rỗng, lát cắt có `start == end` là rỗng |
| Chuỗi Unicode | Chỉ số của `CharSequence` dùng **UTF-16 code unit** (đơn vị `char`), không trực tiếp đếm ký tự người nhìn thấy | Ký tự ngoài BMP như `🙂` chiếm hai `char`; `subSequence` có thể cắt giữa cặp surrogate |
| `Math.abs(int)` | Trả trị tuyệt đối ngoại trừ trường hợp số âm nhỏ nhất | `Math.abs(Integer.MIN_VALUE)` vẫn là số âm |
| `Math.absExact(int)` | Trả trị tuyệt đối khi biểu diễn được bằng `int`, ngược lại ném `ArithmeticException` | `Integer.MIN_VALUE`, `Integer.MIN_VALUE + 1`, `-1`, `0`, `Integer.MAX_VALUE` |
| `Math.absExact(long)` | Hành vi tương ứng cho `long` | `Long.MIN_VALUE` |

Phân biệt **đúng hợp đồng** với **đúng dữ liệu kiểm thử**: nếu test dùng lại chính thuật toán của mã sản xuất để tính expected value, cả hai có thể sai giống nhau. Với biên nguyên nhỏ nhất, dùng hằng số được định nghĩa rõ hoặc kiểm tra trên kiểu rộng hơn (`long` cho `int`).

## 2. Hợp đồng của `CharSequence` còn áp dụng hiện nay

`CharSequence` là interface mô tả một dãy các đơn vị ký tự UTF-16. `String`, `StringBuilder` và các lớp riêng của ứng dụng có thể triển khai nó. Những thành viên chính:

```java
int length();
char charAt(int index);
CharSequence subSequence(int start, int end);
String toString();
```

Bên cạnh đó interface còn cung cấp các default methods như `chars()`, `codePoints()` và `isEmpty()` (được bổ sung trong Java 15):

```java
default boolean isEmpty() {
    return length() == 0;
}
```

Đây là mô tả đúng hành vi của default method; khi triển khai lớp riêng, chỉ cần `length()` đúng thì `isEmpty()` kế thừa cũng đúng, miễn là lớp không tự override khác đi.

Những quy tắc có thể viết thành test:

1. `length()` trả số lượng `char` UTF-16, luôn không âm.
2. `charAt(i)` hợp lệ khi `0 <= i < length()` và phải trả đúng đơn vị `char` tại vị trí đó; ngoài khoảng ném `IndexOutOfBoundsException`.
3. `subSequence(start, end)` lấy đoạn `[start, end)`: bao gồm `start`, loại trừ `end`, kết quả dài `end - start`. Các trường hợp `0 <= start <= end <= length()` đều hợp lệ.
4. `subSequence(i, i)` phải cho dãy rỗng, kể cả khi `i == length()`.
5. `toString()` phải phản ánh đúng thứ tự các `char` mà đối tượng biểu diễn tại thời điểm chuyển đổi.
6. `isEmpty()` kiểm tra **độ dài bằng 0**, không kiểm tra dấu cách, tab hay chuỗi chỉ có whitespace. `String.isBlank()` có mục đích khác.
7. Nếu đây là một *view* lên chuỗi gốc, các vị trí trong `charAt()` và `subSequence()` phải được cộng đúng offset; test trên một lát cắt **không bắt đầu tại 0** đặc biệt quan trọng.

**Đừng áp đặt `equals()` giữa các kiểu `CharSequence`.** Interface này không quy định một cách so sánh bằng nhau chung cho mọi implementation. Ví dụ `new CustomSequence("abc").equals("abc")` có thể là `false` nếu lớp chưa override `equals()`. Khi cần so sánh nội dung, dùng `toString()`, kiểm tra ký tự hoặc API như `String.contentEquals(CharSequence)` theo đúng ngữ nghĩa.

### 2.1. Vì sao Unicode phải nằm trong test?

Java đo độ dài `CharSequence` bằng các đơn vị `char` 16-bit:

```java
String s = "A🙂Z";
System.out.println(s.length());                    // 4
System.out.println(s.codePointCount(0, s.length())); // 3
```

Một emoji `🙂` gồm hai *surrogate code units* trong UTF-16. Vì vậy `subSequence(1, 3)` biểu diễn trọn emoji, còn `subSequence(1, 2)` chỉ giữ một surrogate. Việc cắt giữa cặp surrogate **không tự động vi phạm hợp đồng chỉ số `CharSequence`**, nhưng có thể tạo đoạn văn bản Unicode không hoàn chỉnh. Nếu ứng dụng cần cắt theo Unicode code point hoặc grapheme cluster, phải xử lý ở lớp nghiệp vụ khác và viết test riêng.

### 2.2. `isEmpty()` khi lớp có nhiều interface

Khi một lớp triển khai `CharSequence` và một interface khác cũng khai báo **default `isEmpty()`** có cùng chữ ký, có thể xuất hiện xung đột default methods. Một cách giải quyết rõ ràng trong lớp cụ thể là:

```java
@Override
public boolean isEmpty() {
    return length() == 0;
}
```

Đoạn trên là **phương thức đặt bên trong một lớp đã triển khai `CharSequence`**, không phải chương trình độc lập. Khi test, xác nhận cùng một hành vi qua tham chiếu `CharSequence`. Đây là vấn đề tương thích Java vẫn có giá trị khi nâng JDK hoặc kết hợp nhiều interface; không nên chỉ tin rằng một phương thức default luôn được chọn như mong muốn.

## 3. Ví dụ đầy đủ: lớp `CharSequence` tùy biến và kiểm thử không cần thư viện

Tạo tệp **`BoundaryCasesDemo.java`** với mã sau. Lớp `Window` là một *immutable view* lên đoạn `[from, to)` của `String`; nó không tự override `isEmpty()` để chúng ta kiểm tra default method của Java 15. Bộ kiểm thử sử dụng `AssertionError` để luôn hoạt động mà không cần bật JVM flag `-ea`.

```java
import java.util.Objects;

public class BoundaryCasesDemo {

    public static final class Window implements CharSequence {
        private final String source;
        private final int from;
        private final int to;

        public Window(String source) {
            this(Objects.requireNonNull(source, "source"),
                 0, source.length());
        }

        private Window(String source, int from, int to) {
            this.source = Objects.requireNonNull(source, "source");
            Objects.checkFromToIndex(from, to, source.length());
            this.from = from;
            this.to = to;
        }

        @Override
        public int length() {
            return to - from;
        }

        @Override
        public char charAt(int index) {
            Objects.checkIndex(index, length());
            return source.charAt(from + index);
        }

        @Override
        public CharSequence subSequence(int start, int end) {
            Objects.checkFromToIndex(start, end, length());
            return new Window(source, from + start, from + end);
        }

        @Override
        public String toString() {
            return source.substring(from, to);
        }
    }

    private static void check(boolean condition, String description) {
        if (!condition) {
            throw new AssertionError(description);
        }
    }

    private static void expectThrows(
            Class<? extends Throwable> expected, Runnable action) {
        try {
            action.run();
        } catch (Throwable actual) {
            if (expected.isInstance(actual)) {
                return;
            }
            throw new AssertionError(
                    "Wrong exception: " + actual.getClass().getName(), actual);
        }
        throw new AssertionError("Expected: " + expected.getName());
    }

    private static void testEmpty() {
        CharSequence empty = new Window("");
        CharSequence blank = new Window(" ");
        CharSequence text = new Window("abc");

        check(empty.length() == 0 && empty.isEmpty(), "empty sequence");
        check(blank.length() == 1 && !blank.isEmpty(), "blank not empty");
        check(!text.isEmpty(), "non-empty sequence");
        check(text.subSequence(2, 2).isEmpty(), "empty slice");

        System.out.println("PASS CharSequence.isEmpty");
    }

    private static void testSliceAndUnicode() {
        CharSequence text = new Window("A🙂Z");

        check(text.length() == 4, "UTF-16 length");
        check(text.charAt(0) == 'A', "first char");
        check("🙂".contentEquals(text.subSequence(1, 3)), "surrogate pair");
        check("Z".contentEquals(text.subSequence(3, 4)), "last char");
        check("🙂Z".contentEquals(text.subSequence(1, 4)),
              "non-zero offset");
        check(text.subSequence(4, 4).isEmpty(), "empty end slice");
        check("A🙂Z".contentEquals(text), "string content");
        check(text.toString().codePointCount(0, text.length()) == 3,
              "code point count");

        expectThrows(IndexOutOfBoundsException.class,
                     () -> text.charAt(-1));
        expectThrows(IndexOutOfBoundsException.class,
                     () -> text.charAt(text.length()));
        expectThrows(IndexOutOfBoundsException.class,
                     () -> text.subSequence(-1, 2));
        expectThrows(IndexOutOfBoundsException.class,
                     () -> text.subSequence(3, 2));
        expectThrows(IndexOutOfBoundsException.class,
                     () -> text.subSequence(0, 5));

        System.out.println("PASS CharSequence bounds and Unicode");
    }

    private static void testMinInteger() {
        int min = Integer.MIN_VALUE;

        check(min == -2_147_483_648, "int minimum");
        check(Math.abs(min) == min, "normal abs overflows");
        check(Math.absExact(min + 1) == Integer.MAX_VALUE,
              "adjacent minimum");
        check(Math.absExact(-1) == 1, "negative one");
        check(Math.absExact(0) == 0, "zero");
        check(Math.absExact(Integer.MAX_VALUE) == Integer.MAX_VALUE,
              "maximum positive");

        expectThrows(ArithmeticException.class,
                     () -> Math.absExact(min));
        expectThrows(ArithmeticException.class,
                     () -> Math.absExact(Long.MIN_VALUE));

        check(Math.abs((long) min) == 2_147_483_648L,
              "widen to long before abs");

        System.out.println("PASS Integer.MIN_VALUE and absExact");
    }

    public static void main(String[] args) {
        testEmpty();
        testSliceAndUnicode();
        testMinInteger();
    }
}
```

Biên dịch và chạy với **JDK 17 hoặc mới hơn**:

```bash
javac -encoding UTF-8 BoundaryCasesDemo.java
java BoundaryCasesDemo
```

**Stdout kỳ vọng khi tất cả kiểm thử đều qua:**

```text
PASS CharSequence.isEmpty
PASS CharSequence bounds and Unicode
PASS Integer.MIN_VALUE and absExact
```

Nếu một invariant sai, chương trình ném `AssertionError` và dừng; vì vậy output ba dòng chỉ xuất hiện khi cả ba nhóm đều hoàn thành. Dù lớp `Window` nhận `String` bất biến nên view ổn định, các lớp `CharSequence` tùy biến đọc từ bộ đệm có thể thay đổi cần thêm test về mutation và vòng đời dữ liệu. Không mặc định rằng một `CharSequence` bất kỳ là immutable hoặc thread-safe.

### 3.1. Vì sao cần một `Window` thay vì chỉ dùng `String`?

Thử `new Window("abc").isEmpty()` kiểm chứng phương thức mặc định hoạt động với **implementation do ứng dụng tự viết**, trong khi thử `"abc".isEmpty()` chỉ kiểm tra `String` vốn đã có sẵn `isEmpty()` từ trước Java 15.

Thử một lát cắt `text.subSequence(1, 4)` cho thấy `Window` phải chuyển `start`/`end` tương đối về offset của dữ liệu gốc. Nếu sai như `source.charAt(index)` thay vì `source.charAt(from + index)`, các test với `from == 0` vẫn có thể qua, nhưng test với lát cắt từ giữa chuỗi sẽ phát hiện lỗi.

## 4. `Integer.MIN_VALUE`: vì sao phép trị tuyệt đối thông thường không đủ?

Kiểu `int` trong Java là số nguyên **signed 32-bit**, khoảng giá trị:

\[
-2^{31} \leq x \leq 2^{31} - 1
\]

Tức là:

| Hằng số | Giá trị |
| --- | ---: |
| `Integer.MIN_VALUE` | `-2147483648` |
| `Integer.MAX_VALUE` | `2147483647` |

Vế âm có thêm **một** giá trị so với vế dương. Vì `2147483648` không biểu diễn được bằng `int`, phép toán lấy trị tuyệt đối của `Integer.MIN_VALUE` không thể trả kết quả toán học chính xác trong kiểu này.

### 4.1. So sánh `Math.abs` và `Math.absExact`

```java
int value = Integer.MIN_VALUE;

int a = Math.abs(value); // a == Integer.MIN_VALUE: vẫn âm
// int b = Math.absExact(value); // ném ArithmeticException
long c = Math.abs((long) value); // c == 2147483648L
```

- `Math.abs(int)` giữ nguyên `Integer.MIN_VALUE` trong đúng trường hợp đặc biệt này; không phát tín hiệu tràn số.
- **`Math.absExact(int)`**, được bổ sung từ Java 15 và vẫn có mặt trong Java hiện đại, ném `ArithmeticException` nếu đối số là `Integer.MIN_VALUE`. Đây thường là lựa chọn phù hợp khi nghiệp vụ **cần kết quả không âm và không chấp nhận tràn số**.
- Nếu nghiệp vụ chấp nhận trả kiểu rộng hơn, **ép lên `long` trước khi lấy trị tuyệt đối**: `Math.abs((long) value)`. Nếu ép `int` **sau** `Math.abs(value)`, tràn số đã xảy ra.
- Tương tự, `Math.abs(Long.MIN_VALUE)` vẫn trả số âm nhỏ nhất của `long`; `Math.absExact(Long.MIN_VALUE)` ném `ArithmeticException`. Không thể sửa giá trị tuyệt đối của `Long.MIN_VALUE` bằng cách ép lên một kiểu nguyên primitive Java rộng hơn `long`.

Ví dụ những phép tính có nguy cơ lỗi tương tự:

```java
int x = Integer.MIN_VALUE;
int y = -x;                      // vẫn là Integer.MIN_VALUE
int z = Math.negateExact(x);     // ném ArithmeticException
long exact = -((long) x);        // 2147483648L
```

`Math.negateExact` vẫn hữu ích khi chương trình cần phát hiện overflow ở phép đổi dấu. Không dùng mẹo `x < 0 ? -x : x` nếu không xử lý trường hợp biên.

### 4.2. Các test quan trọng cho `Math.absExact(int)`

| Đầu vào | Kết quả kỳ vọng |
| ---: | --- |
| `Integer.MIN_VALUE` (`-2147483648`) | Ném `ArithmeticException` |
| `Integer.MIN_VALUE + 1` (`-2147483647`) | `2147483647` |
| `-123` | `123` |
| `-1` | `1` |
| `0` | `0` |
| `1` | `1` |
| `Integer.MAX_VALUE` (`2147483647`) | `2147483647` |

Điều cần quan sát không chỉ là phương thức có ném exception, mà còn là **đúng loại exception và đúng trường hợp**. Không nên cố kiểm tra chính xác nguyên văn thông báo exception vì chuỗi thông báo có thể phụ thuộc JDK.

Khi đối chiếu với `Math.abs`, test phải phân biệt `Math.abs(Integer.MIN_VALUE)` là một hành vi **được API định nghĩa**, không phải bug của JDK. Bug của ứng dụng xuất hiện khi giả định rằng mọi kết quả của `Math.abs(int)` đều không âm.

### 4.3. Property-based testing và ranh giới miền hợp lệ

Với mọi `int n` **khác** `Integer.MIN_VALUE`, các thuộc tính sau đúng:

- `Math.absExact(n) >= 0`.
- `Math.absExact(n) == Math.abs((long) n)` khi so sánh sau khi nâng kết quả `int` lên `long`.
- `Math.absExact(n) == Math.absExact(-n)` với điều kiện `-n` biểu diễn được dưới `int` (đã loại `Integer.MIN_VALUE`).
- `Math.absExact(0) == 0`.

Với riêng `Integer.MIN_VALUE`, `Math.absExact` phải ném `ArithmeticException` thay vì tạo một trị tuyệt đối sai. Khi dùng test sinh dữ liệu ngẫu nhiên, **luôn thêm ca biên này cố định** vì xác suất bộ sinh ngẫu nhiên chạm đúng một giá trị đặc biệt là rất nhỏ.

## 5. Viết test bằng JUnit Jupiter

Khi dự án đã có **JUnit Jupiter** và `junit-jupiter-params` trên test classpath, có thể tách các assertion khỏi chương trình `main`. Sau khi lưu `BoundaryCasesDemo.java` vào source set mà test nhìn thấy, tạo **`BoundaryCasesDemoTest.java`** trong test source set tương ứng:

```java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class BoundaryCasesDemoTest {

    @Test
    void customSequenceDistinguishesEmptyFromBlank() {
        CharSequence empty = new BoundaryCasesDemo.Window("");
        CharSequence blank = new BoundaryCasesDemo.Window(" ");

        assertTrue(empty.isEmpty());
        assertEquals(0, empty.length());
        assertFalse(blank.isEmpty());
        assertEquals(1, blank.length());
    }

    @Test
    void customSequenceChecksSliceBounds() {
        CharSequence text = new BoundaryCasesDemo.Window("A🙂Z");

        assertEquals(4, text.length());
        assertTrue("🙂".contentEquals(text.subSequence(1, 3)));
        assertTrue(text.subSequence(4, 4).isEmpty());
        assertThrows(IndexOutOfBoundsException.class,
                     () -> text.charAt(text.length()));
        assertThrows(IndexOutOfBoundsException.class,
                     () -> text.subSequence(3, 2));
    }

    @ParameterizedTest
    @ValueSource(ints = {
        Integer.MIN_VALUE + 1, -123, -1, 0, 1, Integer.MAX_VALUE
    })
    void absExactMatchesLongReferenceForValidInts(int input) {
        int actual = Math.absExact(input);

        assertTrue(actual >= 0);
        assertEquals(Math.abs((long) input), (long) actual);
    }

    @Test
    void absExactRejectsMinValue() {
        assertThrows(ArithmeticException.class,
                     () -> Math.absExact(Integer.MIN_VALUE));
        assertThrows(ArithmeticException.class,
                     () -> Math.absExact(Long.MIN_VALUE));
    }

    @Test
    void traditionalAbsMinValueIsStillNegative() {
        assertEquals(Integer.MIN_VALUE, Math.abs(Integer.MIN_VALUE));
        assertEquals(2_147_483_648L,
                     Math.abs((long) Integer.MIN_VALUE));
    }
}
```

Đây là **mã test JUnit**, cần dependency JUnit Jupiter phù hợp và test task dùng JUnit Platform; không biên dịch test chỉ bằng `javac BoundaryCasesDemoTest.java` nếu chưa có JUnit trên classpath. Cấu hình test trong Gradle/Maven tùy dự án, ví dụ một dự án Gradle Groovy DSL có thể dùng:

```groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.13.4'
}
test {
    useJUnitPlatform()
}
```

Phiên bản dependency chỉ là **một ví dụ để hiểu cú pháp**, cần đối chiếu với phiên bản mà dự án quản lý khi chạy thực tế. `junit-jupiter` bao gồm các thành phần Jupiter API/params/engine cho cấu hình thông thường. Nếu dự án dùng BOM hoặc version catalog, ưu tiên cơ chế dependency hiện có.

### 5.1. Bảng ca kiểm thử nên có

| Nhóm | Input | Assertion |
| --- | --- | --- |
| Empty | `new Window("")` | `isEmpty() == true`, `length() == 0` |
| Blank | `new Window(" ")` | `isEmpty() == false` |
| Nội dung thường | `new Window("abc")` | `charAt`, `subSequence`, `toString` |
| Index biên trái | `charAt(-1)`, `subSequence(-1, 1)` | `IndexOutOfBoundsException` |
| Index biên phải | `charAt(length)`, `subSequence(0, length + 1)` | `IndexOutOfBoundsException` |
| Đoạn rỗng | `subSequence(0, 0)`, `subSequence(length, length)` | Hợp lệ, dãy kết quả rỗng |
| Đoạn đảo chiều | `subSequence(3, 2)` | `IndexOutOfBoundsException` |
| Unicode | `"A🙂Z"` | `length() == 4`, số code point `== 3` |
| `Math.abs` biên | `Integer.MIN_VALUE` | Vẫn là số âm nhỏ nhất |
| `Math.absExact` biên | `Integer.MIN_VALUE` | `ArithmeticException` |
| Sát biên | `Integer.MIN_VALUE + 1` | `Integer.MAX_VALUE` |
| Giá trị chuẩn | `-123`, `-1`, `0`, `1`, `Integer.MAX_VALUE` | Giá trị tuyệt đối không âm, chính xác |
| Biên `long` | `Long.MIN_VALUE` | `Math.absExact(long)` ném `ArithmeticException` |

Khi test *view* của `CharSequence`, nên thêm kiểm thử cắt nhiều tầng: `seq.subSequence(1, 4).subSequence(1, 2)` phải dùng offset tương đối của phần đã cắt. Điều này phát hiện lỗi mà test trên `String` hoặc lát cắt đầu tiên dễ bỏ sót.

## 6. Kiểm thử trực tiếp hành vi nghiệp vụ dùng hai API

Một unit test tốt cần chứng minh **hợp đồng của mã ứng dụng**, không chỉ gọi lại API Java. Ví dụ một hàm lấy độ lớn an toàn từ một số nhập vào dưới dạng `CharSequence`:

```java
public static int parseMagnitude(CharSequence input) {
    if (input == null || input.isEmpty()) {
        throw new IllegalArgumentException("Input is empty");
    }

    int parsed = Integer.parseInt(input.toString());
    return Math.absExact(parsed);
}
```

Đoạn trên là **phương thức minh họa nằm trong một lớp Java**, không phải chương trình độc lập. Nó tận dụng `CharSequence.isEmpty()` để kiểm tra đầu vào và `Math.absExact` để tránh trả độ lớn âm do tràn số. Chính sách nghiệp vụ này coi chuỗi chỉ có whitespace (`" "`) là **không rỗng** nhưng không phải số hợp lệ; `Integer.parseInt(" ")` ném `NumberFormatException`.

Những test nên có cho `parseMagnitude`:

- `new Window("123")` trả `123`.
- `new Window("-123")` trả `123`.
- `new Window("0")` trả `0`.
- `new Window("")` ném `IllegalArgumentException`.
- `new Window(" ")` ném `NumberFormatException`.
- `new Window("-2147483648")` ném `ArithmeticException`.
- `new Window("-2147483647")` trả `2147483647`.
- `new Window("2147483648")` ném `NumberFormatException` vì vượt miền `int`.
- `null` ném `IllegalArgumentException`.

Không phải lúc nào cũng cần chuyển `CharSequence` thành `String`; ở ví dụ này, `Integer.parseInt(CharSequence s, int beginIndex, int endIndex, int radix)` là một API khác có thể phân tích trực tiếp đoạn chữ số (xuất hiện từ Java 9), nhưng chữ ký và cách bắt lỗi khác với `Integer.parseInt(String)`. Chỉ chọn tối ưu đó khi bài toán và phép đo có lý do rõ ràng, rồi viết thêm test cho `beginIndex`, `endIndex`, `radix` và `NumberFormatException`.

## 7. Lỗi phổ biến khi kiểm thử hai chủ đề

1. **Chỉ thử `String.isEmpty()` thay vì lớp `CharSequence` tự cài đặt.** Test như vậy không chứng minh default method hoặc hợp đồng `length()` của implementation mới.
2. **Coi `" "` là dãy rỗng.** `isEmpty()` không thay thế kiểm tra whitespace.
3. **Dùng `length()` để đếm ký tự Unicode hiển thị.** Nó đếm UTF-16 code units; code point và grapheme cluster là khái niệm khác.
4. **Thiếu ca `subSequence` có offset khác 0.** Một implementation có thể sai vị trí mà các test trên toàn chuỗi không phát hiện.
5. **Kiểm tra `equals()` tùy ý giữa `Window` và `String`.** `CharSequence` không bảo đảm semantics `equals` thống nhất; so nội dung theo hợp đồng thích hợp.
6. **Viết `Math.abs(Integer.MIN_VALUE) >= 0` làm assertion.** Assertion này sai theo hành vi được đặc tả của `Math.abs`, nên không phải phép kiểm thử hợp lệ cho hàm đó.
7. **Dùng `Math.abs()` để tính expected của `Math.absExact()` tại biên.** Tham chiếu kiểm thử có cùng vấn đề overflow; dùng `long` hoặc giá trị xác định rõ.
8. **Bỏ quên `Integer.MIN_VALUE` trong random tests.** Cần một test cố định cho giá trị đúng tại ranh giới.
9. **Bắt mọi exception và coi là PASS.** Dùng `assertThrows(ArithmeticException.class, ...)` hay kiểm tra đúng kiểu; lỗi `NullPointerException` hoặc `IllegalArgumentException` không phải kết quả thay thế.
10. **Giả định mọi bản JDK đều là Java 15.** Khi học API được giới thiệu từ Java 15, compile/run bằng JDK còn được hỗ trợ; chỉ định `--release 15` nếu đang kiểm tra có chủ đích khả năng chạy trên API của Java 15, không vì thế mà chạy production trên một bản JDK cũ.

## 8. Checklist QA cho người học

- [ ] `Window` triển khai đủ `length`, `charAt`, `subSequence`, `toString` và test kế thừa `isEmpty`.
- [ ] Kiểm thử `""`, `" "`, chuỗi thường, Unicode surrogate và lát cắt lồng nhau.
- [ ] Kiểm thử cả giá trị hợp lệ ở ranh giới và chỉ số không hợp lệ.
- [ ] Nhận diện sự khác nhau giữa `Math.abs` và `Math.absExact` ở `Integer.MIN_VALUE`.
- [ ] Kiểm thử `Integer.MIN_VALUE + 1` như ca **sát biên**, không chỉ riêng ca sinh exception.
- [ ] So sánh trị tuyệt đối `int` với kết quả trên `long` khi cần giá trị tham chiếu.
- [ ] Giữ exception type và ngữ nghĩa test ổn định, tránh phụ thuộc thông báo lỗi.
- [ ] Chạy lại test bằng JDK và dependency mà dự án đang dùng, không phụ thuộc mặc định của IDE.
- [ ] Bảo đảm test thất bại thật sự khi implementation bị cố ý thay sai `isEmpty`, offset hoặc handling của `Integer.MIN_VALUE`.

## 9. Tài liệu API chính thức

- [`CharSequence` — Java SE 15: hợp đồng và `isEmpty()` (`Since: 15`)](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/CharSequence.html)
- [`CharSequence` — Java SE 26: xác nhận API vẫn được hỗ trợ](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/CharSequence.html)
- [`Math` — Java SE 26: `abs`, `absExact(int)` và `absExact(long)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Math.html)
- [`String` — Java SE 15: `length`, `contentEquals`, `subSequence`](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/String.html)
- [Inside Java — xung đột default `CharSequence.isEmpty()` khi nâng cấp JDK](https://inside.java/2020/09/22/incompatibilities-with-jdk15-charsequence/)

**Kết luận về kiểm thử:** xây dựng `CharSequence` tùy biến đòi hỏi kiểm chứng `length`, UTF-16, vị trí cắt và `isEmpty` thực sự qua interface. Với số nguyên nhỏ nhất, test phải khẳng định `Math.absExact(Integer.MIN_VALUE)` phát hiện overflow và các giá trị liền kề vẫn chạy đúng. Hai nhóm ca biên này là những kiểm thử hồi quy có giá trị lâu dài trên Java 17+.
