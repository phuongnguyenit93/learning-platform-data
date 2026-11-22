# Kiểm thử `String.formatted()`: sai kiểu, thiếu tham số và khác biệt `Locale`

## 1. Mục tiêu bài học

Trong Java 15, `String.formatted(Object... args)` cho phép dùng chính một chuỗi làm mẫu định dạng:

```java
String result = "Mã=%d; tên=%s".formatted(15, "Java");
System.out.println(result); // Mã=15; tên=Java
```

Phương thức này vẫn được hỗ trợ trong các Java hiện đại. Điểm cần kiểm thử: **mã có thể biên dịch thành công nhưng phép định dạng vẫn có thể thất bại lúc chạy** nếu placeholder không phù hợp với kiểu tham số, thiếu tham số hoặc format string sai cú pháp. Ngoài ra, cùng một format string cho số có thể trả về chuỗi khác nhau tùy `Locale`.

Sau bài này, bạn có thể:

1. Viết test cho trường hợp hợp lệ và **sai kiểu** (ví dụ `%d` nhận `String`).
2. Viết test cho **thiếu tham số**, chỉ số tham số không tồn tại, và biết rằng tham số **thừa thường bị bỏ qua**.
3. Kiểm thử đầu ra phụ thuộc `Locale.Category.FORMAT` của `String.formatted`.
4. Chọn `String.format(Locale, ...)` khi đầu ra cần ổn định theo một `Locale` cụ thể.
5. Tách lỗi do format string, dữ liệu đầu vào và cấu hình môi trường để tránh test thất thường.

Ngữ cảnh là **Kiểm thử** của module **Java 15**, vì `String.formatted` được bổ sung từ Java 15. Các quy tắc `Formatter` và kỹ thuật test dưới đây vẫn áp dụng hiện nay; không dựa vào hành vi đã lỗi thời.

## 2. `formatted` thực sự hoạt động thế nào?

Theo Java API, phép gọi:

```java
String actual = "Số: %d".formatted(15);
```

tương đương về hành vi với:

```java
String actual = String.format("Số: %d", 15);
```

Nó sử dụng cú pháp định dạng của `java.util.Formatter` và trả về một `String` mới; không thay đổi mẫu gốc. Tên format specifier phổ biến:

| Specifier | Dữ liệu phù hợp điển hình | Ví dụ với `Locale.US` |
|---|---|---|
| `%s` | Nhiều kiểu đối tượng; dùng biểu diễn chuỗi | `"Tên: %s".formatted("Lan")` → `Tên: Lan` |
| `%d` | Kiểu số nguyên được `Formatter` hỗ trợ, như `int`/`long`/`BigInteger` | `"%d".formatted(15)` → `15` |
| `%f` | Kiểu số thực được hỗ trợ, như `double`/`float`/`BigDecimal` | `"%.2f".formatted(3.5)` → `3.50` |
| `%,.2f` | Số thực, có dấu tách nhóm và 2 chữ số phần thập phân | `1,234.50` với `1234.5` |
| `%%` | Dấu phần trăm literal, **không tiêu thụ tham số** | `"100%%".formatted()` → `100%` |
| `%n` | Dấu xuống dòng theo hệ điều hành, **không tiêu thụ tham số** | Không giả định luôn là `\n` |

**`%s` tương đối “dễ tính”**: số nguyên như `15` cũng có thể được biểu diễn thành `"15"`. Do đó, test “sai kiểu” nên ưu tiên specifier nghiêm ngặt như `%d` hoặc `%f`, tránh kết luận sai rằng truyền số vào `%s` nhất định gây exception.

**Phân biệt thời điểm lỗi:** Java kiểm tra được cú pháp gọi phương thức và số lượng tham số Java ở mức `Object...`, nhưng không kiểm tra tương thích giữa từng placeholder và giá trị truyền vào ngay lúc compile. Phần lớn lỗi format xuất hiện **khi chạy `formatted(...)`**.

## 3. Nhóm test 1 — Truyền sai kiểu dữ liệu

### 3.1. `%d` nhận `String`

```java
String output = "Mã: %d".formatted("15");
```

Mặc dù chuỗi `"15"` nhìn giống số, đối tượng được truyền vào vẫn là `String`. `%d` không tự parse chuỗi này thành số. Lúc chạy, `Formatter` phát sinh:

```text
java.util.IllegalFormatConversionException
```

Đây là tên **loại exception**, không phải toàn bộ stack trace cố định. Một test phù hợp cần khẳng định **đúng lớp exception**; đừng phụ thuộc nguyên văn thông báo lỗi.

### 3.2. `%f` nhận số nguyên

```java
String output = "Điểm: %.1f".formatted(15);
```

`%.1f` yêu cầu một loại số thực phù hợp, còn `15` là `Integer` sau khi boxing. Đây cũng là tình huống `IllegalFormatConversionException`. Đổi tham số thành `15.0`, `15.0f` hoặc `BigDecimal` phù hợp, thay vì chỉ đổi format để test “qua” mà che sai yêu cầu dữ liệu.

### 3.3. Test exception cụ thể

Nếu dùng JUnit Jupiter, biểu thức kiểm thử cốt lõi là:

```java
assertThrows(
    IllegalFormatConversionException.class,
    () -> "Mã: %d".formatted("15")
);
```

Trong một test source đầy đủ phải import `assertThrows` và `IllegalFormatConversionException` (xem mục 8). `IllegalFormatConversionException` là con của `IllegalFormatException`; kiểm tra lớp cụ thể thường cho chẩn đoán tốt hơn chỉ kiểm tra lớp cha.

Một vài trường hợp khác cần phân biệt:

- `"%s".formatted(15)` **thành công**, trả về `15`; không phải ca sai kiểu.
- `"%.2f".formatted(15.0)` **thành công**, với `Locale.US` cho kết quả `15.00`.
- `"%d".formatted(15.0)` **không** tự ép `double` thành `int`; phát sinh `IllegalFormatConversionException`.
- Nếu format string đến từ dữ liệu bên ngoài, còn có thể phát sinh lỗi về ký hiệu chuyển đổi hoặc cờ; đó là **nhóm lỗi mẫu**, cần test riêng.

## 4. Nhóm test 2 — Thiếu tham số, chỉ số và tham số thừa

### 4.1. Thiếu đối số

```java
String output = "%s - %d".formatted("Java");
```

Mẫu cần hai giá trị nhưng chỉ nhận một. `Formatter` phát sinh `MissingFormatArgumentException`. Với ví dụ trên, `getFormatSpecifier()` của exception có thể xác nhận vị trí còn thiếu là `%d`:

```java
MissingFormatArgumentException ex = assertThrows(
    MissingFormatArgumentException.class,
    () -> "%s - %d".formatted("Java")
);
assertEquals("%d", ex.getFormatSpecifier());
```

Đây là test tốt vì vừa xác nhận **loại lỗi** vừa chỉ ra specifier gây lỗi.

### 4.2. Chỉ số đối số vượt phạm vi

```java
String output = "%2$s".formatted("Java");
```

`2$` nghĩa là lấy **đối số thứ hai** (đánh chỉ số từ 1), nhưng chỉ có một đối số. Kết quả: `MissingFormatArgumentException`. Kiểm tra `getFormatSpecifier()` có thể giúp định vị specifier sai.

### 4.3. Truyền tham số thừa

```java
String output = "%s".formatted("Java", "thừa");
System.out.println(output); // Java
```

Không có exception: `Formatter` **bỏ qua tham số dư**. Nếu ứng dụng yêu cầu một tham số đầu vào phải được dùng, test chỉ dựa vào exception **không phát hiện được** lỗi này. Hãy kiểm tra chuỗi kết quả và kiểm soát cách tạo mẫu/danh sách tham số.

### 4.4. Phân biệt placeholder với ký tự phần trăm

```java
String output = "Tiến độ 100%%: %s".formatted("xong");
System.out.println(output); // Tiến độ 100%: xong
```

`%%` không dùng tham số, nên chỉ cần đối số cho `%s`. Nếu viết dấu `%` tùy tiện hoặc dùng conversion không hợp lệ như `%q`, bạn có thể nhận `UnknownFormatConversionException`. Test mẫu định dạng không hợp lệ khác với test thiếu tham số. Mặt khác, `%n` không ăn tham số nhưng phụ thuộc dấu xuống dòng của môi trường; trong test đa nền tảng, dùng `System.lineSeparator()` hoặc tránh so sánh literal `\n` với `%n`.

## 5. Nhóm test 3 — `Locale` làm thay đổi đầu ra

### 5.1. `String.formatted` lấy `Locale` nào?

`String.formatted(args)` tương đương `String.format(format, args)`. Bản `String.format` **không nhận tham số `Locale`** sử dụng locale mặc định thuộc **`Locale.Category.FORMAT`**, tức:

```java
Locale current = Locale.getDefault(Locale.Category.FORMAT);
```

Vì thế hai máy hoặc hai lượt test cùng chạy `"%,.2f".formatted(1234.5)` có thể cho kết quả khác nhau nếu cấu hình locale khác. `String.formatted` **không có overload nhận `Locale`**. Đừng viết `pattern.formatted(Locale.US, value)` với hy vọng đối số đầu chọn locale: đó sẽ chỉ là một đối số format và có thể tạo lỗi hoặc kết quả sai.

Ví dụ giá trị số `1234.5` với cùng mẫu `%,.2f`:

| Locale | Kết quả mong đợi | Giải thích |
|---|---|---|
| `Locale.US` | `1,234.50` | Dấu phẩy nhóm hàng nghìn; dấu chấm thập phân |
| `Locale.GERMANY` | `1.234,50` | Dấu chấm nhóm hàng nghìn; dấu phẩy thập phân |

Hai kết quả khác nhau nhưng **cùng là hành vi hợp lệ**. Format số nên được test theo yêu cầu hiển thị của từng locale, không áp một snapshot duy nhất cho mọi vùng.

### 5.2. Cách chủ động chọn locale: `String.format(Locale, ...)`

```java
String us = String.format(Locale.US, "%,.2f", 1234.5);
String de = String.format(Locale.GERMANY, "%,.2f", 1234.5);

System.out.println(us); // 1,234.50
System.out.println(de); // 1.234,50
```

Khi ứng dụng sinh báo cáo hoặc chuỗi giao tiếp cần chuẩn hóa, việc truyền `Locale` tường minh làm test dễ dự đoán và không phụ thuộc locale mặc định của máy chạy.

### 5.3. Test chính hành vi mặc định của `formatted`

Để xác minh bản thân `formatted` thay đổi theo locale, có thể tạm đổi locale mặc định của nhóm `FORMAT` rồi phục hồi:

```java
Locale before = Locale.getDefault(Locale.Category.FORMAT);
try {
    Locale.setDefault(Locale.Category.FORMAT, Locale.US);
    String us = "%,.2f".formatted(1234.5);

    Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY);
    String de = "%,.2f".formatted(1234.5);

    // Assert: us là "1,234.50", de là "1.234,50".
} finally {
    Locale.setDefault(Locale.Category.FORMAT, before);
}
```

**Cảnh báo quan trọng khi test:** `Locale.setDefault(...)` thay đổi trạng thái **chung của JVM**. Nếu nhiều test hoặc luồng khác chạy song song, chúng có thể ảnh hưởng lẫn nhau. Luôn phục hồi trong `finally`; test thay đổi default locale nên chạy tuần tự/có cơ chế khóa tài nguyên chung hoặc trong tiến trình JVM riêng. Khi chỉ cần kiểm tra định dạng của hai vùng, ưu tiên **`String.format(Locale, ...)`** và không đổi trạng thái toàn cục.

## 6. Ma trận ca kiểm thử cần có

| Ca | Cách gọi / dữ liệu | Kết quả nên assert |
|---|---|---|
| Hợp lệ, số nguyên | `"ID=%d".formatted(15)` | `ID=15` |
| Sai kiểu `%d` | `"ID=%d".formatted("15")` | `IllegalFormatConversionException` |
| Sai kiểu `%f` | `"%.1f".formatted(15)` | `IllegalFormatConversionException` |
| Thiếu đối số | `"%s-%d".formatted("A")` | `MissingFormatArgumentException` |
| Chỉ số vượt phạm vi | `"%2$s".formatted("A")` | `MissingFormatArgumentException` |
| Đối số thừa | `"%s".formatted("A", "B")` | `A`; đối số `B` bị bỏ qua |
| Dấu phần trăm literal | `"%% %s".formatted("A")` | `% A` |
| Explicit US | `String.format(Locale.US, "%,.2f", 1234.5)` | `1,234.50` |
| Explicit Germany | `String.format(Locale.GERMANY, "%,.2f", 1234.5)` | `1.234,50` |
| Default FORMAT = US | `"%,.2f".formatted(1234.5)` | `1,234.50` |
| Default FORMAT = Germany | `"%,.2f".formatted(1234.5)` | `1.234,50` |
| Specifier không hợp lệ | `"%q".formatted(15)` | `UnknownFormatConversionException` |

Không nhất thiết đưa tất cả vào cùng một test method. Nên tách **happy path**, **kiểm thử exception**, và **kiểm thử locale** để lúc thất bại xác định nhanh nguyên nhân.

## 7. Ví dụ độc lập có thể biên dịch và chạy bằng Java 15+

Tạo tệp **`FormattedChecks.java`** (tên tệp khớp tên public class). Đoạn sau **không cần JUnit hoặc thư viện bên ngoài**; dùng bộ kiểm tra đơn giản để bất kỳ người học nào có JDK 15+ đều thử được.

```java
import java.util.IllegalFormatConversionException;
import java.util.Locale;
import java.util.MissingFormatArgumentException;

public class FormattedChecks {
    private static int checks = 0;

    public static void main(String[] args) {
        // 1. Trường hợp hợp lệ.
        equal("ID=15", "ID=%d".formatted(15));

        // 2-3. Sai kiểu so với conversion.
        expect(IllegalFormatConversionException.class,
                () -> "ID=%d".formatted("15"));
        expect(IllegalFormatConversionException.class,
                () -> "%.1f".formatted(15));

        // 4-5. Thiếu đối số thường và đối số theo chỉ số.
        expect(MissingFormatArgumentException.class,
                () -> "%s-%d".formatted("A"));
        expect(MissingFormatArgumentException.class,
                () -> "%2$s".formatted("A"));

        // 6-7. Đối số thừa bị bỏ qua; %% không tiêu thụ đối số.
        equal("A", "%s".formatted("A", "B"));
        equal("% A", "%% %s".formatted("A"));

        // 8-9. Locale tường minh: kết quả ổn định.
        equal("1,234.50",
                String.format(Locale.US, "%,.2f", 1234.5));
        equal("1.234,50",
                String.format(Locale.GERMANY, "%,.2f", 1234.5));

        // 10-11. formatted() lấy default FORMAT locale.
        Locale saved = Locale.getDefault(Locale.Category.FORMAT);
        try {
            Locale.setDefault(Locale.Category.FORMAT, Locale.US);
            equal("1,234.50", "%,.2f".formatted(1234.5));

            Locale.setDefault(Locale.Category.FORMAT, Locale.GERMANY);
            equal("1.234,50", "%,.2f".formatted(1234.5));
        } finally {
            Locale.setDefault(Locale.Category.FORMAT, saved);
        }

        System.out.println("PASS: " + checks + " checks");
    }

    private static void equal(String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Expected [" + expected + "], actual [" + actual + "]");
        }
        checks++;
    }

    private static void expect(
            Class<? extends RuntimeException> expectedType,
            Runnable action) {
        try {
            action.run();
        } catch (RuntimeException ex) {
            if (expectedType.isInstance(ex)) {
                checks++;
                return;
            }
            throw new AssertionError(
                    "Expected " + expectedType.getSimpleName()
                    + ", got " + ex.getClass().getSimpleName(), ex);
        }
        throw new AssertionError(
                "Expected " + expectedType.getSimpleName()
                + ", but no exception was thrown");
    }
}
```

Chạy trong terminal tại thư mục chứa file, với JDK 15 hoặc mới hơn:

```bash
javac -encoding UTF-8 FormattedChecks.java
java FormattedChecks
```

Stdout chính xác nếu tất cả kiểm tra đều đạt:

```text
PASS: 11 checks
```

Nếu bất kỳ điều kiện nào sai, `AssertionError` làm chương trình kết thúc thất bại; đó là tín hiệu test fail. Bài test thay đổi default locale rồi khôi phục, nên chạy nó trong một JVM test tuần tự/riêng để tránh tương tác với tác vụ khác. Với quy trình CI, mã kiểm thử JUnit bên dưới thuận tiện hơn để lọc và báo cáo từng case.

## 8. Ví dụ JUnit Jupiter: test tách biệt theo hành vi

Đây là **mã test hoàn chỉnh** cho tệp **`FormattedTest.java`**, với điều kiện dự án đã cấu hình JUnit Jupiter và JDK/runtime tương thích. Đoạn này cần thư viện JUnit trên classpath; nó **không** biên dịch chỉ bằng `javac` của JDK trần.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.IllegalFormatConversionException;
import java.util.Locale;
import java.util.MissingFormatArgumentException;

import org.junit.jupiter.api.Test;

class FormattedTest {

    @Test
    void validIntegerFormat() {
        assertEquals("ID=15", "ID=%d".formatted(15));
    }

    @Test
    void incompatibleTypeThrows() {
        IllegalFormatConversionException ex = assertThrows(
                IllegalFormatConversionException.class,
                () -> "ID=%d".formatted("15"));
        assertEquals('d', ex.getConversion());
    }

    @Test
    void missingArgumentThrows() {
        MissingFormatArgumentException ex = assertThrows(
                MissingFormatArgumentException.class,
                () -> "%s - %d".formatted("Java"));
        assertEquals("%d", ex.getFormatSpecifier());
    }

    @Test
    void extraArgumentIsIgnored() {
        assertEquals("Java", "%s".formatted("Java", "unused"));
    }

    @Test
    void explicitLocaleProducesExpectedSeparators() {
        assertEquals("1,234.50",
                String.format(Locale.US, "%,.2f", 1234.5));
        assertEquals("1.234,50",
                String.format(Locale.GERMANY, "%,.2f", 1234.5));
    }
}
```

Các test này không sửa locale mặc định của JVM nên an toàn hơn khi chạy song song. Nếu muốn JUnit kiểm thử riêng `String.formatted` dưới nhiều default locale, thêm test với `try/finally` như mục 5.3 và cấu hình **không chạy đồng thời** với test nào cũng thay đổi locale mặc định (hoặc chạy trong JVM riêng). `assertThrows` không yêu cầu phải biết toàn bộ nội dung thông báo exception, vốn có thể thay đổi.

Khi dùng parameterized tests với nhiều loại dữ liệu, nên đặt rõ tên case, kiểu đầu vào và exception mong đợi, ví dụ `String` vào `%d`, `Integer` vào `%f`, và đối số thiếu ở `%2$s`. Không biến **giá trị hợp lệ** thành case exception chỉ vì màn hình in ra khác locale.

## 9. Thiết kế test tốt: test dữ liệu hay test môi trường?

### 9.1. Chọn oracle đúng cho từng loại ca

- **Happy path:** so sánh chuỗi **chính xác** khi locale đã xác định. Với đầu vào `15` và `%d`, mong đợi `15`.
- **Sai kiểu/thiếu tham số:** dùng `assertThrows` với loại exception cụ thể; khi phù hợp thì xác nhận `getConversion()` hoặc `getFormatSpecifier()`, tránh snapshot toàn bộ stack trace.
- **Locale:** test từng locale bằng dữ liệu cố định, hoặc có kiểm soát default `FORMAT`. Mong đợi `1,234.50` và `1.234,50` là hai oracle khác nhau.
- **Dữ liệu thừa:** assert chuỗi đầu ra, vì bản thân `Formatter` không báo lỗi cho tham số dư.
- **Format string tùy biến:** kiểm thử cả đầu vào hợp lệ và format string sai, coi format string cũng là **đầu vào** cần kiểm soát.

### 9.2. Tránh test phụ thuộc môi trường

`String.formatted` lấy locale từ mặc định của JVM. Chạy cùng một test trên laptop Việt Nam, container thiết lập `en_US` và CI cấu hình `de_DE` có thể tạo chữ số/dấu ngăn khác nhau. Nếu logic sản phẩm yêu cầu định dạng **một locale cụ thể**, hãy gọi `String.format(locale, ...)`. Nếu sản phẩm yêu cầu định dạng **theo locale của người dùng**, hãy truyền locale của người dùng vào hàm định dạng, rồi kiểm thử từng locale một cách tường minh.

Ngoài locale, thời gian còn chịu ảnh hưởng **múi giờ** khi dùng một số conversion thời gian của `Formatter`. Tránh snapshot toàn bộ định dạng ngày giờ nếu chưa cố định dữ liệu và timezone. Tên tháng, ký tự khoảng trắng hoặc ký hiệu tiền tệ có thể phụ thuộc dữ liệu vùng/ngôn ngữ của JDK; với các locale ngoài US/Germany, hãy kiểm tra yêu cầu sản phẩm trước khi cố định từng ký tự trong test.

### 9.3. Xử lý input trước khi format

Không nên dùng `formatted` làm công cụ tự động chuyển chuỗi số thành số:

```java
String raw = "15";
int id = Integer.parseInt(raw); // parse/validate theo yêu cầu
String result = "ID=%d".formatted(id);
```

Nếu `raw` đến từ người dùng, test thêm chuỗi không phải số và xử lý `NumberFormatException` ở **bước parse**, tách khỏi `IllegalFormatConversionException` của **bước format**. Khi giữ kiểu dữ liệu đúng ở đầu vào, test trở nên dễ giải thích và lỗi xuất hiện ở vị trí có ý nghĩa.

## 10. Lỗi kiểm thử phổ biến và cách sửa

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Mong `"%s".formatted(15)` ném lỗi sai kiểu | Test fail vì `%s` hỗ trợ biểu diễn số thành chuỗi | Dùng `%d` nhận `String` hoặc `%f` nhận số nguyên |
| Mong compiler bắt lỗi `"%d".formatted("15")` | Build thành công, nhưng chạy mới ném exception | Viết runtime test với `assertThrows` |
| Chỉ test số lượng tham số “không bằng nhau” | Bỏ sót tình huống tham số **thừa** bị bỏ qua | Assert output và kiểm soát dữ liệu format |
| So sánh `"%,.2f".formatted(...)` với một chuỗi US trên mọi máy | Test hỏng khi default locale khác | Dùng explicit `Locale.US` hoặc điều khiển `FORMAT` locale |
| Đổi `Locale.setDefault` mà không khôi phục | Các test khác bị ảnh hưởng, nhất là khi song song | `try/finally`, khóa chia sẻ hoặc JVM riêng |
| Đưa `Locale.GERMANY` vào `formatted` như đối số “cấu hình” | Locale bị hiểu là đối số format thông thường | Dùng `String.format(Locale.GERMANY, format, args)` |
| Assert toàn bộ exception message/stack trace | Test dễ hỏng khi thay đổi JDK | Assert class exception và thuộc tính có ý nghĩa |
| Dùng `%n` rồi mặc định output luôn chứa `\n` | Khác nền tảng có dấu xuống dòng khác | Dùng `System.lineSeparator()` hoặc tách bài test |
| Chỉ test `String.format(Locale.US, ...)` mà coi đã test default locale của `formatted` | Bỏ sót phụ thuộc global `FORMAT` locale | Nếu cần, kiểm thử `formatted` với default FORMAT được kiểm soát |

## 11. Bài tập thực hành và đáp án tự kiểm tra

**Bài 1 — Lỗi nằm ở đâu?**

```java
String x = "Đơn: %d".formatted("25");
```

Kết luận: **compile được** nếu có Java 15+, nhưng lúc chạy phát sinh `IllegalFormatConversionException` vì `%d` không chấp nhận `String`. Hãy parse chuỗi thành số nguyên (nếu dữ liệu hợp lệ) hoặc đổi thiết kế mẫu theo đúng ý nghĩa trường dữ liệu.

**Bài 2 — Đủ bao nhiêu đối số?**

```java
String x = "%2$s / %1$d".formatted(7);
```

Kết luận: `MissingFormatArgumentException` vì `%2$s` tham chiếu đối số thứ hai nhưng chỉ có một. Truyền thêm đối số như `.formatted(7, "Java")` thì kết quả là `Java / 7`.

**Bài 3 — Vì sao hai môi trường cho hai kết quả?**

```java
String x = "%,.2f".formatted(1234.5);
```

Nếu hai môi trường có default `Locale.Category.FORMAT` lần lượt là `Locale.US` và `Locale.GERMANY`, kết quả lần lượt là `1,234.50` và `1.234,50`. Đó là hành vi localization, không phải lỗi ngẫu nhiên. Hãy chuyển sang `String.format(locale, ...)` khi muốn output cố định.

**Bài 4 — Làm sao viết test tin cậy khi thiếu tham số?**

Dùng `assertThrows(MissingFormatArgumentException.class, ...)`; có thể assert thêm `getFormatSpecifier()` bằng `%d`. Không assert nguyên văn stack trace.

**Bài 5 — `"%% %s".formatted("x")` có thiếu đối số không?**

Không. `%%` là phần trăm literal, chỉ `%s` tiêu thụ một đối số. Kết quả là `% x`.

## 12. Ghi nhớ và tài liệu tra cứu

**Ba câu hỏi kiểm thử cốt lõi:**

1. **Kiểu dữ liệu có khớp conversion không?** Nếu không, mong đợi `IllegalFormatConversionException`.
2. **Mọi specifier cần dữ liệu đều tìm được đối số không?** Nếu không, mong đợi `MissingFormatArgumentException`; đừng quên `%%` và `%n` không dùng đối số và tham số thừa có thể bị bỏ qua.
3. **Locale đã được chọn rõ ràng chưa?** `String.formatted` dùng default `Locale.Category.FORMAT`; khi cần locale cố định, dùng `String.format(Locale, ...)`.

Kết hợp **assert chuỗi đầu ra**, **assert lớp exception**, và **kiểm soát môi trường** giúp test đúng cả tính năng Java 15 lẫn những bản Java hiện đại.

**Tài liệu chính thức, còn áp dụng:**

- [Java SE 25 — `String.formatted` và `String.format`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html)
- [Java SE 25 — `Formatter`: conversion, flags, argument index, localization](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Formatter.html)
- [Java SE 25 — `Locale` và `Locale.Category.FORMAT`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Locale.html)
- [Java SE 25 — `IllegalFormatConversionException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/IllegalFormatConversionException.html)
- [Java SE 25 — `MissingFormatArgumentException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/MissingFormatArgumentException.html)
