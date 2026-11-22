# String.formatted cho các vị trí thay thế theo định dạng trong Java

> **Phạm vi:** Bài thuộc **Java 14 → Escape và chuỗi**, nhưng sử dụng **kiến thức còn áp dụng trong Java hiện hành**. `String.formatted(Object... args)` là API chính thức từ **Java 15**, được hỗ trợ trong Java 17+; không phải cú pháp preview và **không** tồn tại trên runtime Java 14. Các ví dụ sử dụng Java 17+ và không cần `--enable-preview`. Trọng tâm là cách viết placeholder theo chuẩn `java.util.Formatter`, đặc biệt **chỉ số đối số** như `%2$s`, `%1$d` và **tái sử dụng đối số** bằng `%<s`.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Dùng `template.formatted(args...)` để thay vị trí định dạng trong một `String` bằng các giá trị.
2. Giải thích cấu trúc `%[argument_index$][flags][width][.precision]conversion`; xác định đâu là kiểu chuyển đổi, độ rộng, độ chính xác và chỉ số tham số.
3. Phân biệt **đối số theo thứ tự**, **đối số đánh chỉ số tường minh** (`%2$s`) và **tái dùng đối số trước** (`%<s`).
4. In dấu phần trăm thực bằng `%%`, xuống dòng theo nền tảng bằng `%n`, và không nhầm chúng với escape `\n` hay `\r` trong Java.
5. Dùng `%s`, `%d`, `%f`, `%tF`, độ rộng, căn lề và precision một cách đúng kiểu dữ liệu.
6. Hiểu `String.formatted` dùng locale mặc định dành cho FORMAT, và khi nào cần dùng `String.format(Locale, ...)` để có đầu ra ổn định.
7. Đọc và sửa lỗi `IllegalFormatException` khi thiếu đối số, sai conversion hoặc chuỗi định dạng không hợp lệ.
8. Kết hợp `formatted` với text block, nhưng không coi `formatted` là một công cụ tự động escape SQL, HTML hay JSON.

## 2. `String.formatted` là gì?

`String.formatted(Object... args)` là **instance method của `java.lang.String`**. Nó lấy **chính chuỗi nhận lời gọi** làm *format string*, thay các format specifiers bằng các đối số được cung cấp và trả về **một `String` mới**.

```java
String template = "Xin chào %s, bạn có %d thông báo.";
String output = template.formatted("Lan", 3);

System.out.println(output);
```

Kết quả:

```text
Xin chào Lan, bạn có 3 thông báo.
```

Trong đó:

- `template` chứa **format specifiers** `%s` và `%d`.
- `"Lan"` là đối số đầu tiên, được `%s` chuyển thành chuỗi.
- `3` là đối số thứ hai, được `%d` định dạng như số nguyên thập phân.
- `formatted` không chỉnh sửa `template`: `String` bất biến; `output` là chuỗi kết quả.

Theo Javadoc, lời gọi:

```java
String result = template.formatted(a, b);
```

có ý nghĩa tương đương:

```java
String result = String.format(template, a, b);
```

Cả hai dùng **hệ thống định dạng của `java.util.Formatter`**. Không có quy tắc mới dành riêng cho `formatted`; các specifier hợp lệ và ngoại lệ xuất phát từ Formatter.

**Khác biệt về kiểu API:**

| Cách gọi | Nơi chứa template | Khi nào dùng |
| --- | --- | --- |
| `"Xin chào %s".formatted(name)` | Chuỗi nhận method | Code gọn, nhất là với text block hoặc literal đã có. |
| `String.format("Xin chào %s", name)` | Tham số thứ nhất của static method | Cách dùng quen thuộc, hợp lý khi muốn template là biến. |
| `String.format(Locale.ROOT, "%.2f", price)` | Static method và locale tường minh | Muốn định dạng số/ngày có locale xác định. |

**Không có overload `template.formatted(Locale, args...)` để chọn locale.** Nếu muốn chọn locale cho phép chuyển đổi phụ thuộc vùng, dùng `String.format(Locale, template, args...)`. Truyền một `Locale` vào danh sách `args` chỉ khiến nó trở thành **một đối số định dạng bình thường**, không thay đổi locale của formatter.

## 3. Cú pháp format specifier

Một specifier thông thường có dạng:

```text
%[argument_index$][flags][width][.precision]conversion
```

Các phần trong ngoặc vuông là **tùy chọn**:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `%` | `%s` | Bắt đầu một format specifier. |
| `argument_index$` | `%2$s` | Chọn **đối số thứ 2** (đếm từ 1). |
| `flags` | `%-8s`, `%04d` | Căn trái, đệm zero hoặc điều chỉnh cách hiển thị theo conversion. |
| `width` | `%8s` | **Độ rộng tối thiểu** của trường kết quả. |
| `.precision` | `%.2f`, `%.4s` | Với số thực: số chữ số thập phân; với `%s`: giới hạn độ dài theo quy tắc Formatter. |
| `conversion` | `s`, `d`, `f`, `x`, `tF` | Xác định **kiểu chuyển đổi** và cách trình bày. |

Ví dụ:

```java
String line = "[%1$-8s] [%2$04d]".formatted("Java", 7);
```

Kết quả:

```text
[Java    ] [0007]
```

Phân tích:

- `%1$-8s` lấy **đối số 1** là `"Java"`, căn trái `-`, độ rộng tối thiểu 8 và chuyển thành chuỗi.
- `%2$04d` lấy **đối số 2** là số nguyên `7`, dùng độ rộng 4 và đệm ký tự `0` ở bên trái.

**Không phải flags/width/precision nào cũng dùng được với mọi conversion.** Chẳng hạn precision không áp dụng cho `%d`, và `%n` không nhận width hoặc đối số. Formatter kiểm tra các ràng buộc này tại runtime và có thể ném ngoại lệ.

## 4. Các conversion hữu ích còn được hỗ trợ

| Format specifier | Kiểu đối số điển hình | Kết quả minh họa | Ghi chú |
| --- | --- | --- | --- |
| `%s` | Chuỗi, object, giá trị bất kỳ | `"%s".formatted("Java")` → `Java` | Chuyển thành văn bản, có quy tắc riêng cho `Formattable` và `null`. |
| `%S` | Chuỗi hoặc object | `"%S".formatted("java")` → `JAVA` | Viết hoa theo locale áp dụng. |
| `%d` | `byte`, `short`, `int`, `long`, `BigInteger` hoặc boxed tương ứng | `"%d".formatted(42)` → `42` | Không nhận chuỗi `"42"` như số nguyên. |
| `%x` | Kiểu số nguyên thích hợp | `"%x".formatted(255)` → `ff` | Hex thường. |
| `%f` | `float`, `double`, `BigDecimal` hoặc boxed tương ứng | `String.format(Locale.ROOT, "%.2f", 12.5)` → `12.50` | Phụ thuộc locale, precision. |
| `%b` | Boolean, object | `"%b".formatted(true)` → `true` | Với object không null và không phải Boolean, thường là `true`. |
| `%c` | Character hoặc code point hợp lệ | `"%c".formatted('A')` → `A` | Không nhận tùy ý một `String` nhiều ký tự. |
| `%tF` | Đối tượng ngày/giờ phù hợp như `LocalDate` | `2026-11-07` | Định dạng ngày ISO-like `yyyy-MM-dd` theo quy tắc Formatter. |
| `%%` | **Không lấy đối số** | `"100%%".formatted()` → `100%` | In dấu phần trăm thật. |
| `%n` | **Không lấy đối số** | Một line separator của nền tảng | Tương đương giá trị `System.lineSeparator()`, không nhất thiết là LF. |

Các giá trị ví dụ có định dạng locale-sensitive được ghi với `Locale.ROOT` khi cần stdout ổn định. `%f` hoặc dấu phân cách nhóm có thể cho kết quả khác nếu chạy với default FORMAT locale khác.

**Lưu ý về số:** `%d`, `%f`, `%x` không có nghĩa «Java sẽ thử tự parse mọi đối số». Formatter không tự đổi `"7"` thành `7` cho `%d`. Nếu dữ liệu đến từ text, parse và validate trước khi truyền cho formatter.

## 5. Ba cách chỉ vị trí đối số

Đây là phần trọng tâm của chủ đề **các vị trí thay thế theo định dạng**. `Formatter` có ba cơ chế chọn argument:

### 5.1. Ordinary indexing — theo thứ tự xuất hiện

```java
String result = "%s có %d điểm".formatted("Lan", 12);
```

Các specifier thông thường không ghi chỉ số:

- `%s` đầu tiên dùng argument thứ 1;
- `%d` tiếp theo dùng argument thứ 2.

Kết quả:

```text
Lan có 12 điểm
```

Nếu đổi thứ tự đối số thành `(12, "Lan")`, `%s` có thể in `12` nhưng `%d` nhận `String` và gây lỗi. Compiler Java không kiểm tra mối liên hệ kiểu conversion với từng varargs argument tại compile time; Formatter kiểm tra khi thực thi.

### 5.2. Explicit indexing — chọn tham số bằng `N$`

Chỉ số bắt đầu từ **1**, không phải 0:

```java
String result = "thứ hai=%2$s, thứ nhất=%1$s".formatted("A", "B");
```

Kết quả:

```text
thứ hai=B, thứ nhất=A
```

Khi có yêu cầu đổi thứ tự từ hoặc dịch câu theo ngôn ngữ khác, explicit indexing giúp dùng đúng đối số mà không phải thay đổi signature hay thứ tự tham số:

```java
String vi = "%1$s đã gửi %2$d tài liệu".formatted("Mai", 3);
String en = "%1$s submitted %2$d documents".formatted("Mai", 3);
```

Cả hai vẫn dùng **argument 1 là người**, **argument 2 là số lượng**. Nếu bản dịch cần đảo vị trí thành phần câu, ta có thể viết format mới có `%2$d` trước `%1$s` mà không đảo tham số khi gọi.

Một argument có thể xuất hiện nhiều lần:

```java
String result = "%1$s / %1$s / %2$s".formatted("left", "right");
```

Kết quả:

```text
left / left / right
```

**Sai thường gặp:** Viết `%0$s`. Chỉ số argument hợp lệ bắt đầu ở 1; số 0 không hợp lệ. Chỉ số lớn hơn số lượng argument được cung cấp có thể gây `MissingFormatArgumentException`.

### 5.3. Relative indexing — `%<s` dùng lại đối số trước

Cờ **`<`** cho phép specifier hiện tại dùng lại **argument mà specifier có đối số trước đó đã sử dụng**:

```java
String result =
        "id=%1$s, again=%<s, upper=%<S".formatted("ab-7");
```

Kết quả:

```text
id=ab-7, again=ab-7, upper=AB-7
```

Trong đó:

- `%1$s` dùng argument 1;
- `%<s` dùng lại argument đó;
- `%<S` vẫn dùng argument đó nhưng chuyển sang chữ hoa.

Một ví dụ khác:

```java
String result =
        "second=%2$s, first=%1$s, again=%<s".formatted("A", "B");
```

Kết quả:

```text
second=B, first=A, again=A
```

Specifier cuối dùng lại **`%1$s` ngay trước nó**, vì vậy kết quả là `A`, không phải `B`. `%<s` **không** có nghĩa «luôn dùng argument 1»; nó là quan hệ tới argument của **specifier trước**.

**Quan trọng:** `<` chỉ phù hợp với các conversion có argument. Không thể mở đầu một format string bằng `%<s` khi chưa có argument trước để tái sử dụng; Formatter sẽ báo thiếu argument.

### 5.4. Trộn explicit và ordinary indexing có quy tắc riêng

Theo Javadoc Formatter, chỉ số **ordinary** được đếm tuần tự **độc lập** với các specifier có explicit index.

```java
String mixed = "[%2$s|%s|%<s|%s]".formatted("A", "B");
```

Kết quả:

```text
[B|A|A|B]
```

Phân tích chi tiết:

1. `%2$s` lấy argument 2 → `B`.
2. `%s` ordinary đầu tiên lấy argument 1 → `A`, **không** nhảy sang argument 3 chỉ vì `%2$s` đã xuất hiện.
3. `%<s` lặp lại argument mà specifier trước đã dùng → `A`.
4. `%s` ordinary thứ hai lấy argument 2 → `B`.

Quy tắc này hợp lệ nhưng dễ gây nhầm khi sửa template. **Khuyến nghị:** Trong template phức tạp, ưu tiên một chiến lược index rõ ràng; nếu dùng nhiều argument lặp hoặc thứ tự linh hoạt, dùng toàn bộ `%1$s`/`%2$s` thay vì trộn mặc dù Formatter cho phép.

## 6. `%%` và `%n` không dùng argument

### 6.1. Viết dấu phần trăm thật

Dấu `%` là ký hiệu bắt đầu format specifier. Nếu format string cần chứa một dấu phần trăm **ở vị trí literal**, hãy viết `%%`:

```java
String ratio = "Tiến độ: %d%%".formatted(75);
```

Kết quả:

```text
Tiến độ: 75%
```

Ở đây:

- `%d` tiêu thụ `75`;
- `%%` tạo đúng một ký tự `%`, **không** tiêu thụ argument.

Khác với dấu phần trăm **bên trong argument đã thay vào**:

```java
String value = "Tiến độ: %s".formatted("75%");
```

Kết quả cũng là `Tiến độ: 75%`. Formatter **không chạy thêm một vòng parse** đối với ký tự `%` có trong argument `"75%"`. Chỉ **format string** được phân tích các placeholder.

**Ví dụ sai:** `"Tiến độ 75%".formatted()` có thể ném `IllegalFormatException` vì `%` đơn lẻ ở cuối template không phải conversion hoàn chỉnh. Viết `"Tiến độ 75%%".formatted()` hoặc dùng chuỗi thường nếu không hề có định dạng.

### 6.2. `%n` — newline theo nền tảng, không phải escape `\n`

Trong Formatter, `%n` chèn **line separator của hệ thống**, tương ứng với `System.lineSeparator()`.

```java
String message = "first%nsecond".formatted();
boolean same = message.equals(
        "first" + System.lineSeparator() + "second");
System.out.println(same);
```

Kết quả ở mọi nền tảng Java tuân thủ API:

```text
true
```

Không nên khẳng định `"first%nsecond".formatted()` luôn bằng `"first\nsecond"`: trên nhiều môi trường `%n` là LF nhưng nơi khác có thể là CRLF.

`%n` là **format conversion**, không phải Java escape; ngược lại `\n` được Java lexer/escape processing chuyển thành LF ngay từ string literal:

```java
String platform = "A%nB".formatted();
String fixedLf = "A\nB".formatted();
```

Hai giá trị có thể giống nhau hoặc khác nhau tùy nền tảng. Nếu một giao thức yêu cầu **LF cố định**, dùng `\n`. Nếu muốn ngắt dòng theo nền tảng khi làm thông báo văn bản, `%n` có thể phù hợp.

**Đừng viết `%1$n` hay `%5n`:** `%n` không nhận argument index, width hoặc precision như conversion có đối số; dùng những thành phần không phù hợp sẽ tạo lỗi Formatter.

## 7. Phân biệt dấu `%` với dấu `\` của Java String

Một format string là **`String` hợp lệ trước khi gọi `formatted`**. Vì vậy có hai tầng xử lý tách biệt:

1. **Java xử lý literal/text block**: escape như `\n`, `\r`, `\t`, `\\`, và quy tắc text block.
2. **Formatter xử lý format string runtime**: tìm `%s`, `%d`, `%2$s`, `%%`, `%n` và dùng argument tương ứng.

| Cú pháp trong source | Tầng xử lý | Giá trị kết quả |
| --- | --- | --- |
| `"\n"` | Java escape | LF cố định `U+000A` |
| `"\r\n"` | Java escape | CR rồi LF |
| `"\\n"` | Java escape | Backslash và chữ `n`, không phải LF |
| `"%n".formatted()` | Formatter | Platform line separator |
| `"%%".formatted()` | Formatter | Dấu `%` thật |
| `"%s".formatted("A")` | Formatter | `A` |
| `"\\%s".formatted("A")` | Java xử lý `\\` thành backslash; Formatter xử lý `%s` | Backslash rồi `A` |

**Đừng dùng `\%`** với ý định escape dấu phần trăm: `\%` không phải một escape hợp lệ của Java string literal. Trong **format string**, dấu phần trăm literal cần `%%`.

**Đừng dùng `String.replace("%s",...)` thay cho formatter một cách máy móc.** `replace` chỉ thay văn bản literal, không hiểu type conversion, width, precision, argument indexing, `%%` hay `%n`. Chọn `replace` khi bài toán thực sự là thay chuỗi literal; chọn `formatted` khi muốn hợp đồng Formatter.

## 8. `formatted` với text block

Text block phù hợp để tạo template nhiều dòng. Compiler tạo giá trị String của text block **trước**; lời gọi `formatted` thay placeholder **sau**, tại runtime.

```java
String template = """
        Name: %s
        Quantity: %03d
        Status: %s
        """;

String output = template.formatted("Mai", 7, "READY");
```

Giá trị tương đương:

```java
"Name: Mai\nQuantity: 007\nStatus: READY\n"
```

Nếu delimiter đóng `"""` nằm trên dòng riêng, text block thường có **LF ở cuối String**. Nếu format specifier nằm bên trong text block, nó sẽ được thay trong chính chuỗi nhiều dòng đó; các bước normalize line ending và strip indentation của text block không diễn ra lại sau `formatted`.

### 8.1. Thứ tự xử lý quan trọng

```text
Mã nguồn text block chứa %s, %d, v.v.
            |
            v
Compiler: chuẩn hóa line terminators / stripIndent / xử lý escapes
            |
            v
String template tại runtime, có các ký tự %s, %d
            |
            v
template.formatted(arguments)
            |
            v
String mới chứa giá trị đã định dạng
```

Vì thế, một argument `"A\nB"` có thể thêm newline vào kết quả của `%s` **sau** khi text block ban đầu đã strip indentation. Không có bước compiler nào tự căn lề lại nội dung được chèn vào. Nếu cần căn lề multiline của dữ liệu chèn, bạn phải chuẩn hóa/indent argument hoặc dùng thuật toán trình bày phù hợp.

### 8.2. Dấu phần trăm literal trong template

```java
String template = """
        Completion: %d%%
        """;

String output = template.formatted(75);
```

Giá trị:

```java
"Completion: 75%\n"
```

Nếu một text block chứa CSS, SQL hoặc tài liệu có nhiều dấu phần trăm literal, hãy kiểm tra mọi ký tự `%` **trong template**. Các dấu `%` cần được escape thành `%%` nếu format string được xử lý bằng Formatter, trừ khi chúng là specifier thật. Không nên gọi `formatted` bừa bãi trên text block chứa phần trăm không phục vụ format.

## 9. Chương trình Java 17+ hoàn chỉnh với stdout xác định

Lưu file dưới tên **`FormattedPositionsDemo.java`**:

```java
import java.time.LocalDate;
import java.util.Locale;

public class FormattedPositionsDemo {
    static String visible(String text) {
        return text.replace("\r", "<CR>")
                   .replace("\n", "<LF>");
    }

    public static void main(String[] args) {
        String template = "Hello, %s!";
        String greeting = template.formatted("Mai");
        System.out.println("greeting=" + greeting);
        System.out.println("template=" + template);

        System.out.println("number=" + "code=%04d".formatted(7));
        System.out.println("percent=" + "progress=%d%%".formatted(75));
        System.out.println("position=" +
                "second=%2$s / first=%1$s / repeated=%<s"
                        .formatted("A", "B"));
        System.out.println("mixed=" +
                "[%2$s|%s|%<s|%s]".formatted("A", "B"));

        String card = """
                name=%s
                count=%d
                """.formatted("Mai", 2);
        System.out.println("block=" + visible(card));

        // Chọn locale rõ ràng cho ví dụ có số thực/ngày.
        System.out.println("fixed-locale=" +
                String.format(Locale.ROOT, "price=%.2f", 12.5));
        System.out.println("date=" +
                String.format(Locale.ROOT, "%tF",
                        LocalDate.of(2026, 11, 7)));

        String platform = "A%nB".formatted();
        System.out.println("platform=" +
                platform.equals("A" + System.lineSeparator() + "B"));

        System.out.println("argument-percent=" +
                "value=%s".formatted("50%"));
        System.out.println("literal-percent=" +
                "100%%".formatted());
    }
}
```

Biên dịch và chạy với JDK 17+ có hỗ trợ `--release 17`:

```bash
javac --release 17 FormattedPositionsDemo.java
java FormattedPositionsDemo
```

**Stdout:**

```text
greeting=Hello, Mai!
template=Hello, %s!
number=code=0007
percent=progress=75%
position=second=B / first=A / repeated=A
mixed=[B|A|A|B]
block=name=Mai<LF>count=2<LF>
fixed-locale=price=12.50
date=2026-11-07
platform=true
argument-percent=value=50%
literal-percent=100%
```

**Kiểm tra từng điểm:**

1. `greeting` là chuỗi mới đã định dạng, còn `template` vẫn chứa `%s`.
2. `%04d` hiển thị số 7 với độ rộng 4, thêm ba ký tự `0`.
3. `%d%%` in số 75 rồi một `%` literal; `%%` không lấy đối số.
4. Trong `position`, `%2$s` lấy `B`, `%1$s` lấy `A`, rồi `%<s` lặp lại đối số vừa dùng: `A`.
5. Trong `mixed`, ordinary index chạy độc lập với explicit index nên có kết quả `[B|A|A|B]`.
6. `card` là text block có LF vật lý cuối; hàm `visible` thay ký tự điều khiển bằng các nhãn `<LF>` để output không phụ thuộc cách terminal hiển thị.
7. `fixed-locale` và `date` dùng `Locale.ROOT` nên không phụ thuộc default locale của máy.
8. `platform` chỉ kiểm tra biểu thức boolean, không giả định newline của OS luôn là một ký tự `\n`.
9. Dấu phần trăm bên trong argument `"50%"` không bị parser xử lý lần nữa; `100%%` trong template phải viết hai dấu `%` để in một.

**Tại sao không dùng ví dụ `"%.2f".formatted(12.5)` với stdout cố định?** Vì `formatted` dùng default FORMAT locale. Ở một máy dùng dấu phẩy làm dấu thập phân, kết quả có thể khác dấu chấm. Chương trình cố ý dùng `String.format(Locale.ROOT, ...)` cho phần phụ thuộc locale để đảm bảo kết quả dự kiến.

## 10. Locale: khác biệt giữa `formatted` và `String.format(Locale, ...)`

Mặc định, `String.formatted(...)` dùng `String.format(String, Object...)`, và bản không truyền locale này dùng locale mặc định theo **`Locale.Category.FORMAT`** của môi trường Java. Điều này ảnh hưởng một số định dạng:

- `%,d` có thể dùng dấu phân cách nhóm số theo locale.
- `%.2f` có thể dùng dấu phẩy hoặc dấu chấm làm dấu thập phân.
- Một số định dạng ngày/giờ và chữ viết hoa cũng phụ thuộc locale.
- Cách viết số thông dụng giữa ngôn ngữ/quốc gia có thể khác nhau.

Ví dụ:

```java
import java.util.Locale;

class LocaleExample {
    static String formatPrice(double value) {
        return String.format(Locale.ROOT, "price=%.2f", value);
    }
}
```

Đây là **lớp minh họa** chưa có `main`. Với `value = 12.5`, kết quả là `price=12.50` theo `Locale.ROOT`. Khi cần hiển thị cho người dùng, chọn locale cụ thể của họ, ví dụ `Locale.forLanguageTag("vi-VN")`; khi tạo nội dung máy đọc/so khớp bằng test, chọn locale theo **hợp đồng định dạng**.

**Không dùng `Locale.setDefault(...)` chỉ để ép một chỗ `formatted` ra dấu chấm**: thay đổi default locale có thể tác động đến những phần khác của ứng dụng. Nếu cần một locale cụ thể, dùng overload có locale tường minh.

**Không nhầm `Locale.ROOT` với bảo đảm an toàn cho mọi giao thức.** Hãy đối chiếu chính xác format được đích yêu cầu, kể cả ký tự phân cách, precision, rounding, encoding và newline.

## 11. Kiểu đối số, `null` và lỗi runtime

Formatter kiểm tra định dạng khi thực thi. Những lỗi dưới đây phổ biến khi số lượng placeholder hoặc kiểu argument không khớp template.

| Format string và arguments | Kết quả | Giải thích |
| --- | --- | --- |
| `"%s %d".formatted("A", 2)` | `A 2` | Khớp conversion và số lượng arguments. |
| `"%s %s".formatted("A")` | `MissingFormatArgumentException` | Thiếu đối số cho `%s` thứ hai. |
| `"%d".formatted("7")` | `IllegalFormatConversionException` | `%d` không nhận `String` như số nguyên. |
| `"%f".formatted(7)` | `IllegalFormatConversionException` | `int` không thuộc nhóm floating-point conversion `%f`. |
| `"%1$s %1$s".formatted("A")` | `A A` | Một argument dùng nhiều lần. |
| `"x".formatted(1, 2)` | `x` | Đối số thừa không được tham chiếu thì bị bỏ qua. |
| `"100%%".formatted()` | `100%` | `%%` không cần argument. |
| `"x=%s".formatted((Object) null)` | `x=null` | Cast giúp truyền **một argument null**, không phải một mảng varargs null. |

`IllegalFormatException` là lớp nền cho nhiều lỗi cú pháp/đối số của Formatter, trong đó có `MissingFormatArgumentException` và `IllegalFormatConversionException`.

Đừng viết `"x=%s".formatted(null)` khi muốn thể hiện một đối số `null` mà không kiểm tra overload/varargs. Với varargs `Object...`, `null` không cast có thể được hiểu là **mảng arguments null**, không phải một phần tử null như bạn tưởng. Cách minh bạch là `.formatted((Object) null)` hoặc `.formatted(new Object[]{null})`.

### 11.1. Chương trình kiểm tra lỗi một cách có kiểm soát

Lưu file **`FormattedErrorsDemo.java`**:

```java
import java.util.IllegalFormatConversionException;
import java.util.IllegalFormatException;
import java.util.MissingFormatArgumentException;

public class FormattedErrorsDemo {
    public static void main(String[] args) {
        try {
            "%d".formatted("7");
        } catch (IllegalFormatConversionException e) {
            System.out.println("type-error=true");
        }

        try {
            "%s/%s".formatted("one");
        } catch (MissingFormatArgumentException e) {
            System.out.println("missing-argument=true");
        }

        try {
            "100%".formatted();
        } catch (IllegalFormatException e) {
            System.out.println("invalid-percent=true");
        }

        System.out.println("null=" +
                "value=%s".formatted((Object) null));
        System.out.println("extra=" +
                "value=%s".formatted("A", "unused"));
    }
}
```

```bash
javac --release 17 FormattedErrorsDemo.java
java FormattedErrorsDemo
```

**Stdout:**

```text
type-error=true
missing-argument=true
invalid-percent=true
null=value=null
extra=value=A
```

Đoạn này **không** nuốt mọi lỗi một cách mù quáng trong code production; nó chủ đích catch những exception để dạy cách nhận biết lỗi Formatter. Trong ứng dụng thực tế, hãy đảm bảo template được kiểm thử và validation đúng trước khi gọi. Không nên dùng `catch (Exception)` để biến mọi lỗi lập trình thành một chuỗi «OK» giả.

### 11.2. Khi nào cần đối số tường minh thay vì dùng `%s` cho tất cả?

Việc dùng `%s` với mọi đầu vào có thể tạo output, nhưng làm mất khả năng compiler/test phát hiện sai ý nghĩa dữ liệu. Nếu một trường có hợp đồng «số lượng là số nguyên» hoặc «giá đã làm tròn hai chữ số», dùng conversion tương ứng và truyền đúng kiểu.

Ví dụ:

```java
String quantity = "12";
int parsed = Integer.parseInt(quantity);
String message = "count=%d".formatted(parsed);
```

Đây là **đoạn lệnh minh họa trong phương thức**, không phải một file có `main`. `Integer.parseInt` có thể ném `NumberFormatException` nếu đầu vào không đúng định dạng. Với dữ liệu không tin cậy, phải có xử lý/validation riêng trước khi format.

## 12. Formatting ngày, giờ và số: áp dụng có chủ đích

### 12.1. Ngày tháng bằng `%tF`

`Formatter` có nhóm **date/time conversions**. `%tF` là một ví dụ:

```java
import java.time.LocalDate;
import java.util.Locale;

class DateExample {
    static String isoDate(LocalDate date) {
        return String.format(Locale.ROOT, "%tF", date);
    }
}
```

Với `date = LocalDate.of(2026, 11, 7)`, kết quả là `2026-11-07`. `LocalDate` là `TemporalAccessor` phù hợp với nhóm conversion ngày/giờ mà Formatter hỗ trợ.

Bạn cũng có thể gọi:

```java
String text = "date=%tF".formatted(
        java.time.LocalDate.of(2026, 11, 7));
```

Cách này hợp lệ, nhưng khi dùng mặc định locale, không nên lấy một số định dạng hiển thị như tên tháng/ngày ở mọi máy làm golden output trừ khi dự án cố định locale.

**Đừng nhầm `%tF` với `%f`:** `t` là prefix chỉ định date/time và `F` là hậu tố format, còn `f` thường là conversion dành cho số thực.

### 12.2. Độ rộng và precision không thay đổi kiểu dữ liệu gốc

```java
String id = "id=[%04d]".formatted(7);
String item = "item=[%-6s]".formatted("AB");
```

Giá trị:

```text
id=[0007]
item=[AB    ]
```

Việc thêm padding chỉ thay đổi chuỗi kết quả, không thay đổi giá trị số `7` hay object `"AB"`.

Với số thực, precision tác động cách **biểu diễn** trong output; đó không phải phép làm tròn dữ liệu nguồn để lưu trữ nghiệp vụ:

```java
double original = 12.345;
String view = String.format(
        java.util.Locale.ROOT, "value=%.2f", original);
```

Dữ liệu `original` vẫn là `12.345`; `view` là chuỗi đã format theo precision 2. Với nghiệp vụ tài chính cần quy tắc tiền tệ/rounding rõ ràng, dùng kiểu số và API phù hợp (ví dụ `BigDecimal` hoặc `NumberFormat` theo chính sách), không dựa vào output text để tính lại giá trị.

## 13. `formatted` không phải interpolation theo tên và không phải escaping an toàn

### 13.1. Không có named placeholders tự động

`String.formatted` hiểu format specifiers kiểu `%1$s`, `%2$d`, **không tự phân giải các tên biến** trong source:

```java
String name = "Lan";
String text = "Hello, %s".formatted(name);
```

Đoạn này hợp lệ. Ngược lại, một chuỗi chứa dạng ký hiệu tên do bạn tự đặt như `{name}` **không** được `formatted` tự hiểu và thay bằng local variable `name`. Nó sẽ chỉ còn nguyên ký tự nếu không phải format specifier của Formatter.

Nếu dự án muốn template theo tên, cần một thư viện/template engine phù hợp hoặc cơ chế ánh xạ tên do bạn triển khai, không gọi `formatted` rồi mong cú pháp tên biến tự được thay.

### 13.2. Không có escaping HTML, JSON, SQL, URL

`%s` biến argument thành văn bản nhưng **không có nghĩa đã escape cho ngữ cảnh đích**. Ví dụ:

```java
String userText = "<b>hello</b>";
String html = "<p>%s</p>".formatted(userText);
```

Giá trị `html` chứa chính chuỗi markup `<b>hello</b>`. Nó không tự đổi thành text HTML an toàn. Đối với HTML cần escape đúng context; với JSON dùng JSON serializer; với URL dùng URL encoding đúng nơi; với SQL có tham số, ưu tiên **`PreparedStatement` với bind parameters** thay vì ghép câu SQL trực tiếp bằng `formatted`.

Đặc biệt, dùng giá trị người dùng làm **format string** có thể gây lỗi specifier, output không dự đoán hoặc tiêu tốn tài nguyên với width/precision quá lớn. Template nên do ứng dụng kiểm soát; dữ liệu người dùng nên đưa vào dưới dạng **arguments** đã được validate.

### 13.3. Format một lần, không xử lý đệ quy arguments

```java
String payload = "%1$s".formatted("%d");
```

Kết quả là ký tự `%d`, không phải một lần format thứ hai. Sau khi chèn argument, Formatter không đọc lại nội dung argument như một format string mới. Nếu chương trình tự gọi `formatted` thêm lần nữa trên output, đó là **một lời gọi mới** do chính chương trình thực hiện, với rủi ro áp dụng format specifier lên nội dung dữ liệu trước đó.

## 14. So sánh với các cách tạo chuỗi khác

| Cách làm | Phù hợp khi | Cần chú ý |
| --- | --- | --- |
| `"Hello " + name` | Nối vài giá trị đơn giản | Không hỗ trợ positional specifiers, width, precision. |
| `"Hello %s".formatted(name)` | Template đơn giản hoặc text block đã chứa placeholder | Dùng default FORMAT locale cho conversion phụ thuộc locale. |
| `String.format(locale, template, args)` | Muốn locale cố định hoặc được người dùng chọn | Dùng cùng quy tắc specifier của Formatter. |
| `StringBuilder.append(...)` | Xây chuỗi qua nhiều bước/đoạn liên tục | Không tự có Formatter syntax trừ khi dùng Formatter riêng. |
| `MessageFormat` | Template địa phương hóa theo cơ chế argument index của `java.text` | **Cú pháp khác Formatter**, không thay thế bằng `%s` hay `%d` máy móc. |
| `NumberFormat` / `DateTimeFormatter` | Định dạng số/ngày theo chính sách chuyên biệt | Hợp đồng riêng, cần chọn locale/format. |

Không có câu trả lời rằng `formatted` luôn tốt hơn mọi phương án. Đối với một hoặc hai phép nối đơn giản, `+` rất dễ đọc. Đối với template nhiều vị trí với định dạng số, chỉ số rõ ràng hoặc text block, `formatted` làm ý định gọn hơn.

## 15. Cách review template có nhiều placeholder

Trước khi merge code sử dụng `formatted`, nên thực hiện:

1. **Liệt kê các specifier**: `%s`, `%d`, `%.2f`, `%tF`, `%%`, `%n` có đúng ngữ nghĩa không?
2. **Kiểm tra chỉ số**: `%1$s` bắt đầu từ 1; `%<s` thực sự đang tái sử dụng argument của specifier nào?
3. **Đếm argument**: Có đủ cho mọi specifier có đối số không? `%%` và `%n` không được tính như argument mới.
4. **Kiểm tra kiểu**: Đối số cho `%d` có thực sự là integer, cho `%f` là loại số thực được hỗ trợ không?
5. **Kiểm tra locale**: Golden tests hoặc protocol có yêu cầu dấu thập phân, grouping, tên tháng hoặc ngày cụ thể không? Nếu có, dùng `String.format(Locale, ...)`.
6. **Kiểm tra newline**: `%n` theo platform; `\n` cố định LF; text block đã có LF vật lý sau quá trình compiler normalize. Không thêm newline ngoài ý muốn.
7. **Kiểm tra phần trăm literal**: Template có dấu `%` ngoài placeholder? Viết `%%`.
8. **Kiểm tra đầu vào không tin cậy**: Không dùng user input làm format string; không coi `%s` là cơ chế chống injection.
9. **Test giá trị tiêu biểu**: Một argument, nhiều argument, đảo vị trí, argument lặp, dấu `%` trong dữ liệu, `null`, số âm và case thiếu/sai kiểu.
10. **Chọn Java release đúng**: `formatted` có từ Java 15; dùng Java 17+ ổn định theo yêu cầu bài, không giả định runtime Java 14 đã có API này.

## 16. Bài tập tự kiểm tra

### Bài 1 — Chỉ số tường minh

```java
String r = "%2$s-%1$s-%2$s".formatted("ONE", "TWO");
System.out.println(r);
```

**Đáp án:** `TWO-ONE-TWO`. `%2$s` dùng argument thứ hai, `%1$s` dùng thứ nhất; một argument có thể xuất hiện nhiều lần.

### Bài 2 — Reuse với `%<s`

```java
String r = "A=%2$s; B=%1$s; C=%<s".formatted("x", "y");
System.out.println(r);
```

**Đáp án:** `A=y; B=x; C=x`. `%<s` dùng lại argument của specifier ngay trước là `%1$s`.

### Bài 3 — Trộn ordinary và explicit indexes

```java
String r = "%2$s|%s|%<s|%s".formatted("x", "y");
System.out.println(r);
```

**Đáp án:** `y|x|x|y`. Ordinary indexing duy trì bộ đếm riêng, không tự nhảy sau explicit index.

### Bài 4 — Dấu phần trăm và số lượng argument

```java
String r = "%d%% finished".formatted(90);
System.out.println(r);
```

**Đáp án:** `90% finished`. Chỉ `%d` cần argument; `%%` tạo một dấu phần trăm thật.

### Bài 5 — `%n` khác `\n` ở đâu?

**Đáp án:** `%n` là conversion của Formatter, tạo line separator do `System.lineSeparator()` cung cấp. `\n` là Java escape tạo LF `U+000A` cố định. Trên một số OS hai giá trị giống nhau, nhưng không được giả định luôn vậy.

### Bài 6 — Đoán lỗi khi truyền sai kiểu

```java
String r = "count=%d".formatted("10");
```

**Đáp án:** Khi thực thi sẽ ném `IllegalFormatConversionException` vì `%d` không tự parse String `"10"`. Nếu cần số, parse/validate trước khi format.

### Bài 7 — Text block và newline cuối

```java
String r = """
        user=%s
        """.formatted("An");
System.out.println(r.equals("user=An\n"));
```

**Đáp án:** `true`. Text block có một LF cuối do vị trí delimiter đóng trên dòng riêng; `formatted` chỉ thay `%s` bằng `"An"`, không xóa newline.

### Bài 8 — Argument có dấu `%` thì sao?

```java
String r = "data=%s".formatted("A%B");
System.out.println(r);
```

**Đáp án:** `data=A%B`. Dấu `%` trong argument không được parse lại như specifier; đây không phải `format string`.

### Bài 9 — Loại conversion cần Locale

```java
String a = "%.2f".formatted(12.5);
String b = String.format(java.util.Locale.ROOT, "%.2f", 12.5);
```

**Đáp án:** `b` là `12.50`. Với `a`, dấu thập phân có thể khác theo default FORMAT locale; không khẳng định cố định `12.50` cho mọi máy.

### Bài 10 — Cần truyền `null` như một argument đơn lẻ

```java
String r = "arg=%s".formatted((Object) null);
System.out.println(r);
```

**Đáp án:** `arg=null`. Cast `(Object) null` làm rõ đây là **một phần tử** của varargs, thay vì một reference mảng `Object[]` bằng null.

## 17. Tài liệu chính thức còn áp dụng

1. [Javadoc Java SE 25 — `String.formatted(Object... args)`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#formatted(java.lang.Object...)): hợp đồng instance method, sử dụng String hiện tại làm format string, tương đương `String.format(this, args)`.
2. [Javadoc Java SE 25 — `String.format`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#format(java.lang.String,java.lang.Object...)): format theo default FORMAT locale, ngoại lệ Formatter và overload có locale.
3. [Javadoc Java SE 25 — `java.util.Formatter`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Formatter.html): cú pháp specifier, conversion, độ rộng/precision, explicit/relative/ordinary argument index, `%%` và `%n`.
4. [Javadoc Java SE 25 — `java.util.Locale`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Locale.html): default locale, category FORMAT và cách chọn locale rõ ràng.
5. [JLS Java SE 25 — `3.10.6 Text Blocks](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6): nếu dùng multiline format string dạng text block, thứ tự chuẩn hóa line endings, indentation và escapes.
6. [JEP 378 — Text Blocks](https://openjdk.org/jeps/378): text block là cú pháp chuẩn từ Java 15; dùng JDK hỗ trợ release phù hợp.
7. [Java SE 17 API — `String.formatted`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#formatted(java.lang.Object...)): tham chiếu phù hợp với các lệnh `javac --release 17` trong bài.

**Ghi nhớ:** `String.formatted` là cách gọi thuận tiện của **Formatter** trên một `String` có sẵn. Các vị trí thay thế có thể theo thứ tự (`%s`, `%d`), **chỉ số tường minh** (`%2$s`, `%1$s`) hoặc **tái sử dụng** (`%<s`). Dùng `%%` cho dấu phần trăm literal và `%n` cho platform newline; dùng `String.format(Locale, ...)` nếu cần locale cụ thể. Luôn kiểm tra số lượng/kiểu đối số và **không coi định dạng chuỗi là cơ chế escaping dữ liệu không tin cậy**.