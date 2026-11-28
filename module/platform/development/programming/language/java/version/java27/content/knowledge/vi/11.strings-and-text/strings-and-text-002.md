# Text block, escape sequence và định dạng chuỗi

Trong Java 27, `String` vẫn là kiểu nền tảng để biểu diễn dữ liệu văn bản. Khi chuỗi chứa nhiều dòng, dấu nháy kép, ký tự đặc biệt hoặc cần trình bày số và ngày tháng, cách viết literal và cách định dạng phù hợp sẽ ảnh hưởng trực tiếp tới khả năng đọc mã nguồn và tính đúng đắn của dữ liệu.

Bài này tập trung vào ba công cụ còn được hỗ trợ chính thức:

- **String literal** và **escape sequence** để biểu diễn chính xác các ký tự trong chuỗi.
- **Text block** (`"""`) để viết văn bản nhiều dòng với cấu trúc dễ nhìn; đây vẫn là một `String`, không phải định dạng dữ liệu mới.
- **String formatting** thông qua `String.format`, `String.formatted`, `Formatter` và các formatter chuyên biệt để đưa dữ liệu vào văn bản có quy tắc.

Các ví dụ dùng cú pháp ổn định trong Java 27. Khi gặp nội dung có cấu trúc như JSON, HTML hoặc SQL, cần phân biệt **cách viết chuỗi trong Java** với **cách mã hóa và bảo vệ dữ liệu của định dạng đích**.

## 1. String literal và escape sequence

String literal thông thường được đặt giữa hai dấu nháy kép:

```java
String title = "Java 27";
String empty = "";
String message = "Xin chào";
```

Nếu muốn đặt ký tự đặc biệt vào literal, dùng **escape sequence** bắt đầu bằng dấu gạch chéo ngược `\`.

```java
String quoted = "Cô ấy nói: \"Xin chào\"";
String filePath = "C:\\logs\\today.log";
String twoLines = "Hàng 1\nHàng 2";
String tabSeparated = "Mã\tTên\tGiá";
```

Các escape sequence phổ biến theo Java Language Specification:

| Escape | Kết quả | Dùng khi |
|---|---|---|
| `\n` | Line feed (LF), U+000A | Xuống dòng trong chuỗi |
| `\r` | Carriage return (CR), U+000D | Giao thức cần CR |
| `\t` | Horizontal tab, U+0009 | Ký tự tab |
| `\b` | Backspace, U+0008 | Ký tự điều khiển backspace |
| `\f` | Form feed, U+000C | Ký tự điều khiển form feed |
| `\"` | Dấu nháy kép `"` | Đưa `"` vào string literal |
| `\'` | Dấu nháy đơn `'` | Có thể dùng trong literal, thường không cần đối với `String` |
| `\\` | Dấu gạch chéo ngược `\` | Đường dẫn, biểu thức chính quy |
| `\s` | Một dấu cách U+0020 | Giữ dấu cách, đặc biệt ở cuối dòng text block |
| `\<xuống dòng>` | Tiếp dòng; bỏ dấu `\` và line terminator | Nối các dòng trong text block |

Java cũng định nghĩa dạng **octal escape**, nhưng không nên dùng khi có cách viết rõ ràng hơn. Với ký tự Unicode, nên lưu mã nguồn bằng UTF-8 và dùng ký tự trực tiếp khi dễ đọc; chỉ dùng Unicode escape khi thực sự cần biểu diễn bằng mã.

### Phân biệt ký tự đặc biệt với hai ký tự in được

```java
String actualNewline = "A\nB";
String visibleBackslashN = "A\\nB";

System.out.println(actualNewline);
System.out.println(visibleBackslashN);
```

Kết quả:

```text
A
B
A\nB
```

Chuỗi thứ nhất chứa LF thực sự; chuỗi thứ hai chứa dấu `\` và chữ `n`. Đây là khác biệt quan trọng khi tạo log, gửi dữ liệu qua giao thức hoặc so sánh văn bản.

Khi làm việc với regex, Java và regex đều có quy tắc escape riêng:

```java
String digitsRegex = "\\d+";
System.out.println("12345".matches(digitsRegex)); // true
```

Trong mã nguồn Java, `"\d+"` là literal không hợp lệ vì `\d` không phải escape sequence của Java. Phải viết `"\\d+"` ở mã nguồn để regex engine nhận được `\d+`. Kiểm tra kỹ **hai lớp diễn giải** khi đặt regex bên trong String.

### Unicode escape được xử lý rất sớm

Java nhận Unicode escape dạng `\uXXXX` ở giai đoạn đọc mã nguồn, **trước** khi nhận diện string literal và text block. Vì vậy, cách viết này không hoàn toàn tương đương với escape runtime `\n`.

```java
String letterA = "\u0041"; // Kết quả là "A"
String lineBreak = "\n";   // Escape cho LF trong String
```

Không nên viết `\u000a` trực tiếp trong literal để thay `\n`: compiler có thể biến nó thành ký tự xuống dòng *trong mã nguồn* trước khi phân tích literal, dẫn đến lỗi cú pháp. Nếu cần chuỗi hiển thị nguyên văn `\u0041`, hãy hiểu rõ quy tắc Unicode escape trong JLS thay vì giả định dấu gạch chéo ngược luôn được giữ lại như ký tự thông thường.

## 2. Text block: viết chuỗi nhiều dòng

Text block là cú pháp để tạo một đối tượng `String` từ một khối văn bản nhiều dòng. Tính năng được chính thức hóa trong Java 15 (JEP 378) và tiếp tục được hỗ trợ trong Java 27.

```java
String html = """
        <section>
            <h1>Java 27</h1>
            <p>Text block dễ đọc hơn chuỗi nối dài.</p>
        </section>
        """;

System.out.print(html);
```

Giá trị chuỗi:

```text
<section>
    <h1>Java 27</h1>
    <p>Text block dễ đọc hơn chuỗi nối dài.</p>
</section>
```

Văn bản đầu ra trên **có thêm LF ở cuối**, dù không nhìn thấy trong khối hiển thị. Trong text block, bạn có thể viết dấu nháy kép thông thường mà không phải thêm `\"` cho từng dấu.

Cú pháp bắt đầu bằng **ba dấu nháy kép**, có thể có khoảng trắng sau đó, rồi **bắt buộc có line terminator**:

```java
String valid = """
        Chào mừng đến với Java 27
        """;

// Không hợp lệ: thiếu line terminator sau dấu mở.
// String invalid = """Hello""";
```

Text block không có nội suy biến tự động. Nó tạo ra chuỗi tĩnh sau bước biên dịch; muốn đưa dữ liệu vào mẫu văn bản, bạn cần dùng API định dạng hoặc giải pháp serialization thích hợp.

### Text block và string literal có cùng kiểu

```java
String regular = "A\nB\n";
String block = """
        A
        B
        """;

System.out.println(regular.equals(block)); // true
```

Text block không tạo kiểu `RawString` hay đối tượng có hành vi so sánh khác. Các phương thức quen thuộc như `length()`, `lines()`, `replace()`, `formatted()` đều dùng được trên giá trị nhận từ text block.

## 3. Quy tắc chuẩn hóa dòng và thụt lề

Đây là điểm dễ sai nhất khi chuyển từ string literal sang text block.

Theo JLS §3.10.6, trình biên dịch chuyển nội dung text block theo ba bước **đúng thứ tự**:

1. Chuẩn hóa line terminator trong nội dung về LF (`\n`): CRLF và CR cũng trở thành LF.
2. Loại bỏ thụt lề ngẫu nhiên (*incidental indentation*) và khoảng trắng cuối dòng tương đương với quy tắc của `String.stripIndent()`.
3. Diễn giải escape sequence, tương đương với `String.translateEscapes()`.

Thứ tự này giúp code giữ được thụt lề tương đối và cho phép dùng `\s` để bảo tồn dấu cách cuối dòng sau khi các khoảng trắng ngẫu nhiên đã bị loại bỏ.

### Vị trí dấu đóng quyết định thụt lề được giữ

```java
String normalized = """
        root
            child
        """;

System.out.println(normalized.equals("root\n    child\n")); // true
```

Ở đây, các khoảng trắng dùng để đặt text block trong mã nguồn bị loại bỏ, còn bốn dấu cách trước `child` được giữ.

Nếu dịch dấu đóng sang trái, bạn có thể giữ lại thụt lề chủ ý:

```java
String indented = """
        root
            child
    """;
```

Dấu đóng của ví dụ này nằm ít thụt lề hơn các dòng nội dung; kết quả vẫn có thêm dấu cách đầu dòng. Hãy thống nhất kiểu căn lề trong dự án để tránh thay đổi vô ý khi format code.

### Dòng cuối có newline hay không?

```java
String withFinalLf = """
        first
        second
        """;

String withoutFinalLf = """
        first
        second""";

System.out.println(withFinalLf.endsWith("\n"));     // true
System.out.println(withoutFinalLf.endsWith("\n"));  // false
```

Với dấu đóng đứng ở dòng riêng, LF ngay trước dấu đóng là một phần của nội dung. Nếu đặt dấu đóng ở cuối dòng nội dung, text block không tự thêm LF sau ký tự cuối.

Trong file cấu hình, HTTP payload hoặc các bài kiểm thử so sánh chuỗi chính xác, một ký tự LF ở cuối có thể ảnh hưởng đến kết quả. Hãy kiểm tra bằng `endsWith("\n")` hoặc `equals(...)` khi định dạng quan trọng.

## 4. Escape sequence trong text block

Text block cho phép nhiều dòng và nháy kép trực tiếp nhưng **không phải raw string**. Các escape sequence vẫn được diễn giải.

### Giữ khoảng trắng cuối dòng bằng \s

Giả sử định dạng cần hai dấu cách sau dấu hai chấm trước khi xuống dòng:

```java
String lines = """
        key:\s\s
        value
        """;
```

Hai `\s` ở cuối dòng được đổi thành hai dấu cách **sau bước stripIndent**, nên được giữ trong giá trị cuối cùng. Gõ hai dấu cách thực sự vào cuối dòng mã nguồn thường không cho kết quả như vậy vì chúng có thể bị loại trong bước chuẩn hóa.

Bạn có thể kiểm tra giá trị:

```java
System.out.println(lines.startsWith("key:  \n")); // true
```

### Tiếp dòng bằng dấu gạch chéo ngược

Nếu muốn mã nguồn xuống dòng nhưng giá trị `String` nối liền, đặt dấu `\` ngay trước line terminator:

```java
String sentence = """
        Học Java 27 \
        với text block.
        """;

System.out.println(sentence.equals("Học Java 27 với text block.\n")); // true
```

Dấu cách sau `27` vẫn là ký tự trong chuỗi; escape tiếp dòng chỉ bỏ dấu gạch chéo ngược và line terminator theo sau. Hãy tránh thêm dấu cách hoặc ký tự khác **sau** dấu `\` vì lúc đó không còn là escape tiếp dòng hợp lệ.

### Giữ dấu gạch chéo ngược và ký tự nháy

```java
String windowsPath = """
        C:\\logs\\server.log
        """;
```

Trong đoạn mã trên, mỗi `\\` trong text block là một dấu `\` ở giá trị kết quả. Nếu nhập `C:\logs` với một dấu gạch chéo ngược đơn trong mã nguồn, `\l` không phải escape Java hợp lệ.

Dấu nháy kép đơn có thể xuất hiện trực tiếp:

```java
String quoted = """
        Khách hàng nói: "Tôi đồng ý"
        """;
```

Khi nội dung chứa chính chuỗi ba dấu nháy kép liên tiếp, cần escape một dấu nháy để tránh bị hiểu thành dấu đóng text block. Đối với mẫu phức tạp có nhiều ký tự đặc biệt, dùng file tài nguyên riêng nếu điều đó giúp dễ đọc và bảo trì hơn.

## 5. Những API xử lý văn bản liên quan

Một số API hiện hành trong `java.lang.String` hỗ trợ làm việc với nhiều dòng:

| API | Ý nghĩa |
|---|---|
| `lines()` | Trả về stream các dòng văn bản, không bao gồm dấu kết thúc dòng |
| `stripIndent()` | Loại bỏ thụt lề ngẫu nhiên theo quy tắc của API |
| `indent(int)` | Thêm hoặc giảm thụt lề đầu dòng và chuẩn hóa line terminator |
| `translateEscapes()` | Diễn giải các escape sequence được hỗ trợ như trong literal |
| `strip()`, `stripLeading()`, `stripTrailing()` | Loại khoảng trắng ở đầu/cuối theo Unicode whitespace |
| `formatted(Object...)` | Áp dụng format specifier trên chính chuỗi nhận |

Ví dụ dùng `lines()` để lấy từng dòng:

```java
String messages = """
        alpha
        beta
        gamma
        """;

var normalized = messages.lines()
    .map(String::strip)
    .filter(line -> !line.isEmpty())
    .toList();

System.out.println(normalized); // [alpha, beta, gamma]
```

`String.translateEscapes()` hữu ích khi cần diễn giải văn bản chứa escape do ứng dụng chủ động cung cấp:

```java
String encoded = "Line 1\\nLine 2";
String decoded = encoded.translateEscapes();
System.out.println(decoded);
```

Không gọi `translateEscapes()` lần nữa trên chuỗi đã được giải mã nếu bạn muốn giữ nguyên dấu gạch chéo ngược trong nội dung. API có thể ném `IllegalArgumentException` khi gặp escape không hợp lệ, và nó **không** thay thế bộ giải mã JSON hay các ngôn ngữ có quy tắc escape riêng.

## 6. Định dạng chuỗi bằng String.format

Khi cần chèn giá trị vào mẫu văn bản, `String.format` sử dụng cú pháp của `java.util.Formatter`.

```java
String user = "Lan";
int count = 3;

String message = String.format(
    "Xin chào %s, bạn có %d thông báo.",
    user, count
);

System.out.println(message);
// Xin chào Lan, bạn có 3 thông báo.
```

Các format specifier thường gặp:

| Ký hiệu | Tác dụng | Ví dụ |
|---|---|---|
| `%s` | Biểu diễn một đối tượng thành văn bản | `"Java"` |
| `%d` | Số nguyên dạng thập phân | `27` |
| `%f` | Số dấu phẩy động dạng thập phân | `12.500000` |
| `%.2f` | Hiển thị hai chữ số sau dấu phân cách thập phân | `12.50` |
| `%,.2f` | Có phân nhóm hàng nghìn (theo locale) | `12,345.60` trong `Locale.US` |
| `%02d` | Độ rộng tối thiểu 2, thêm số 0 ở bên trái | `07` |
| `%-10s` | Căn trái chuỗi trong vùng rộng tối thiểu 10 | Cột bảng |
| `%tF` | Ngày dạng ISO 8601 từ giá trị tương thích | `2026-11-27` |
| `%%` | Dấu phần trăm `%` | Chuỗi tỉ lệ |
| `%n` | Dấu kết thúc dòng theo nền tảng | In dòng kết thúc |

Để hiển thị ổn định với dấu thập phân và phân nhóm mong muốn, truyền `Locale` tường minh:

```java
import java.util.Locale;

double price = 12345.6;

String us = String.format(Locale.US, "Price: %,.2f", price);
System.out.println(us); // Price: 12,345.60
```

Không truyền locale thì `String.format(format, args)` dùng locale mặc định cho danh mục FORMAT của môi trường. Điều đó thích hợp với một số thông điệp người dùng nhưng có thể khiến output khác nhau giữa máy và bài kiểm thử.

### Dùng chỉ số đối số và ký hiệu phần trăm

```java
String text = String.format(
    "%2$s có %1$d điểm; tỉ lệ 100%%.",
    95, "Lan"
);

System.out.println(text);
// Lan có 95 điểm; tỉ lệ 100%.
```

Chỉ số `%2$s` và `%1$d` giúp dùng các đối số theo thứ tự xác định khi cần. Tuy vậy, với mẫu dài, quá nhiều chỉ số và cờ format thường làm mã khó đọc; nên cân nhắc một phương thức dựng thông điệp có tên rõ ràng hoặc công cụ template dành cho nội dung phức tạp.

Sai cú pháp hoặc đối số không tương thích có thể gây các ngoại lệ thuộc nhóm `IllegalFormatException`, ví dụ `MissingFormatArgumentException` khi thiếu đối số. Chỉ dùng **format pattern mà ứng dụng kiểm soát hoặc đã được kiểm tra** nếu cần kết quả ổn định.

## 7. String.formatted: mẫu định dạng là một String

Phương thức instance `String.formatted(Object...)` hoạt động tương đương `String.format(this, args)`. Đây là lựa chọn gọn khi format pattern được lưu trong một biến hoặc text block:

```java
String greeting = "Xin chào %s, mã đơn %s";
String output = greeting.formatted("Lan", "ORD-100");

System.out.println(output);
// Xin chào Lan, mã đơn ORD-100
```

Kết hợp trực tiếp với text block:

```java
String summary = """
        ĐƠN HÀNG: %s
        Khách hàng: %s
        Số dòng hàng: %d
        """.formatted("ORD-100", "Lan", 3);

System.out.print(summary);
```

Text block giải quyết khả năng đọc **cấu trúc nhiều dòng**; `formatted` giải quyết **gắn đối số vào format specifier**. Hai tính năng độc lập và có thể kết hợp.

Lưu ý: `formatted` dùng locale mặc định giống `String.format(String, Object...)`. Nếu yêu cầu locale cụ thể, gọi `String.format(locale, template, args)`:

```java
String template = """
        Khách: %s
        Số tiền: %,.2f
        """;

String display = String.format(
    Locale.US, template, "Lan", 12345.6
);
```

## 8. Định dạng số, tiền tệ và ngày tháng phù hợp ngữ cảnh

Với số và ngày tháng xuất hiện thường xuyên, Java cung cấp các formatter chuyên dụng:

- `NumberFormat` và `DecimalFormat` để định dạng số và tiền theo locale.
- `DateTimeFormatter` để định dạng dữ liệu ngày giờ thuộc `java.time`.
- `String.format` và `Formatter` để căn cột và dựng thông điệp theo format specifier.

Ví dụ định dạng tiền tệ theo locale:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

var formatter = NumberFormat.getCurrencyInstance(Locale.US);
String total = formatter.format(new BigDecimal("1234.50"));
System.out.println(total); // $1,234.50
```

Ký hiệu và dấu phân cách tùy thuộc locale. Việc định dạng số thành tiền tệ không tự áp dụng quy tắc nghiệp vụ về loại tiền, tỷ giá, làm tròn hay độ chính xác tính toán; những quy tắc đó phải được xử lý ở tầng dữ liệu tiền tệ.

Với ngày tháng:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

var date = LocalDate.of(2026, 11, 27);
String iso = date.format(DateTimeFormatter.ISO_LOCAL_DATE);

String localized = date.format(
    DateTimeFormatter.ofPattern("dd MMM uuuu", Locale.US)
);

System.out.println(iso);       // 2026-11-27
System.out.println(localized); // 27 Nov 2026
```

Dùng formatter có locale, múi giờ hoặc chuẩn ISO rõ ràng khi nội dung được lưu trữ, trao đổi giữa hệ thống hoặc sử dụng để kiểm thử. Một chuỗi hiển thị cho người dùng và một định dạng dữ liệu máy có thể cần quy tắc khác nhau.

## 9. Dựng chuỗi nhiều phần bằng StringBuilder

`String` là bất biến: nối chuỗi tạo ra giá trị `String` mới. Với một biểu thức ngắn, toán tử `+` vẫn rất dễ đọc và được compiler tối ưu phù hợp:

```java
String message = "Đơn " + orderId + " có " + itemCount + " dòng.";
```

Khi tạo nhiều dòng trong vòng lặp, `StringBuilder` thường tiện hơn vì giảm các giá trị trung gian và quản lý rõ quá trình dựng văn bản:

```java
import java.util.List;

var codes = List.of("A01", "A02", "A03");
var result = new StringBuilder();

for (var code : codes) {
    result.append("- ").append(code).append('\n');
}

String report = result.toString();
System.out.print(report);
```

Nếu mục tiêu chỉ là nối các phần tử với dấu phân cách, dùng `String.join` hoặc `Collectors.joining` để mã ngắn và rõ hơn:

```java
String csvLine = String.join(",", "A01", "A02", "A03");
// A01,A02,A03
```

`String.join` **không phải CSV encoder**; nếu giá trị có dấu phẩy, dấu nháy hoặc xuống dòng, cần bộ mã hóa CSV đúng chuẩn của định dạng đích.

## 10. Ví dụ hoàn chỉnh: tạo biên nhận dạng văn bản

Chương trình sau kết hợp record, text block, StringBuilder, `String.format`, `Locale` và `BigDecimal`. Đặt toàn bộ đoạn mã vào file `TextFormattingDemo.java` rồi chạy bằng JDK 27.

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class TextFormattingDemo {

    record Item(String sku, int quantity, BigDecimal unitPrice) {
        Item {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(unitPrice, "unitPrice");
            if (sku.isBlank() || quantity <= 0 || unitPrice.signum() < 0) {
                throw new IllegalArgumentException("Dòng hàng không hợp lệ");
            }
        }

        BigDecimal subtotal() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    record Receipt(String code, LocalDate date, List<Item> items) {
        Receipt {
            Objects.requireNonNull(code, "code");
            Objects.requireNonNull(date, "date");
            items = List.copyOf(items);
            if (code.isBlank() || items.isEmpty()) {
                throw new IllegalArgumentException("Biên nhận không hợp lệ");
            }
        }

        BigDecimal total() {
            return items.stream()
                    .map(Item::subtotal)
                    .reduce(BigDecimal.ZERO, BigDecimal::add);
        }
    }

    static String render(Receipt receipt) {
        var rows = new StringBuilder();

        for (var item : receipt.items()) {
            rows.append(String.format(
                Locale.US,
                "  %-8s %3d x %8.2f",
                item.sku(), item.quantity(), item.unitPrice()
            ));
            rows.append('\n');
        }

        String template = """
                BIÊN NHẬN: %s
                Ngày: %s
                ------------------------------
                %sTỔNG: %,.2f
                """;

        return String.format(
            Locale.US,
            template,
            receipt.code(),
            receipt.date().format(DateTimeFormatter.ISO_LOCAL_DATE),
            rows.toString(),
            receipt.total()
        );
    }

    public static void main(String[] args) {
        var receipt = new Receipt(
            "R-100",
            LocalDate.of(2026, 11, 27),
            List.of(
                new Item("BOOK", 2, new BigDecimal("12.50")),
                new Item("PEN", 3, new BigDecimal("3.20"))
            )
        );

        System.out.print(render(receipt));
    }
}
```

Biên dịch và chạy:

```shell
javac TextFormattingDemo.java
java TextFormattingDemo
```

Kết quả dự kiến:

```text
BIÊN NHẬN: R-100
Ngày: 2026-11-27
------------------------------
  BOOK       2 x    12.50
  PEN        3 x     3.20
TỔNG: 34.60
```

Trong ví dụ, `StringBuilder` xây từng dòng; text block xác định bố cục toàn bộ biên nhận; `String.format(Locale.US, ...)` gắn dữ liệu vào mẫu. Giá trị tiền tính bằng `BigDecimal` trước khi được định dạng; việc hiển thị hai chữ số thập phân không thay thế quy tắc làm tròn dữ liệu nghiệp vụ.

Ví dụ chủ động dùng LF (`'\n'` và text block) cho các dòng của tài liệu. Nếu mục tiêu là in văn bản theo hệ điều hành, cân nhắc `%n` hoặc `System.lineSeparator()`; với dữ liệu theo giao thức, hãy làm đúng quy định cụ thể của giao thức thay vì phụ thuộc nền tảng.

## 11. Text block không tự làm cho JSON, HTML hay SQL an toàn

Text block phù hợp để trình bày **nội dung tĩnh** nhiều dòng:

```java
String jsonExample = """
        {
          "service": "java",
          "version": 27,
          "enabled": true
        }
        """;
```

Đây là một `String` trông giống JSON, nhưng không có bước kiểm tra JSON hay serialize tự động. Khi nội dung động được chèn vào, định dạng đích cần quy tắc escape riêng. Ví dụ, dùng `formatted()` để chèn trực tiếp một tên chứa dấu nháy vào JSON có thể tạo JSON không hợp lệ. Với JSON động, nên dùng thư viện JSON có chức năng serialize hợp lệ.

Tương tự, khi tạo HTML, cần xử lý ký tự đặc biệt trong đúng ngữ cảnh HTML (text node, attribute, URL...). Chỉ dựa vào `String.format` không bảo vệ khỏi HTML injection.

**Đối với SQL**, không nối hoặc format đầu vào người dùng thành câu lệnh:

```java
// Ví dụ không an toàn nếu username do người dùng nhập:
// String sql = "SELECT id FROM users WHERE name = '%s'".formatted(username);
```

Dùng parameterized query với `PreparedStatement`:

```java
String sql = """
        SELECT id, name
        FROM users
        WHERE name = ?
        """;

try (var statement = connection.prepareStatement(sql)) {
    statement.setString(1, username);
    try (var results = statement.executeQuery()) {
        while (results.next()) {
            System.out.println(results.getString("name"));
        }
    }
}
```

Ở đây `connection` là đối tượng `java.sql.Connection` đã được thiết lập trong tầng truy cập dữ liệu, còn `username` là biến đầu vào. Text block chỉ giúp câu SQL dễ đọc; `PreparedStatement` cung cấp cơ chế gắn giá trị tham số mà không phải ghép chuỗi SQL.

## 12. Các lỗi phổ biến và cách tránh

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Cho rằng text block là raw string | `\n`, `\t` hoặc `\\` vẫn được diễn giải | Viết escape chính xác và kiểm tra kết quả |
| Bỏ qua LF ở cuối text block | So sánh chuỗi hoặc dữ liệu đầu ra lệch một ký tự | Chọn vị trí dấu đóng phù hợp |
| Dùng khoảng trắng cuối dòng để cố định bố cục | Bước stripIndent có thể loại khoảng trắng | Dùng `\s` khi cần giữ dấu cách |
| Nhầm `\n` với `%n` | Line ending khác nhau theo nền tảng | Chọn LF cố định cho giao thức; `%n` cho hiển thị theo nền tảng |
| Format số bằng locale mặc định rồi so sánh chuỗi cứng | Dấu phân cách số thay đổi theo máy | Truyền `Locale` tường minh |
| Sai format specifier hoặc thiếu đối số | `IllegalFormatException` khi chạy | Kiểm tra format pattern và đối số |
| Dùng `String.join` thay cho CSV encoder | Dữ liệu chứa dấu phẩy bị phân tách sai | Dùng encoder theo định dạng CSV |
| Dùng `formatted` để chèn SQL người dùng | Có thể tạo SQL injection | Dùng `PreparedStatement` |
| Dùng text block như JSON serializer | Giá trị động có thể không escape hợp lệ | Dùng thư viện serializer |
| Dùng `String Templates` preview đã bị rút | Mã không được hỗ trợ trong Java 27 | Dùng API `format`/`formatted` và thư viện template phù hợp |

### Về String Templates từng xuất hiện ở bản preview

Java từng thử nghiệm cú pháp String Templates trong JDK 21 và 22; tính năng này **đã bị rút**, không phải cú pháp Java chuẩn để dùng trong Java 27. Vì yêu cầu nội dung chỉ bao gồm kiến thức còn áp dụng hiện nay, bài này dùng `String.format`, `String.formatted`, `Formatter`, `StringBuilder` và các formatter chuyên dụng làm công cụ định dạng phù hợp.

## 13. Câu hỏi và bài tập tự kiểm tra

**Câu 1.** Cho khai báo:

```java
String value = """
        A
        B
        """;
```

Biểu thức `value.equals("A\nB\n")` trả về gì?

**Câu 2.** Vì sao chuỗi `"C:\logs\app.log"` có thể không hợp lệ nếu viết với dấu gạch chéo ngược đơn ở mã nguồn? Hãy viết lại đúng.

**Câu 3.** Điểm khác nhau giữa `String.format(Locale.US, "%.2f", 12.5)` và `"%.2f".formatted(12.5)` là gì?

**Câu 4.** Khi đưa dữ liệu do người dùng nhập vào câu SQL nhiều dòng, vì sao text block kết hợp `formatted()` không giải quyết được SQL injection?

**Câu 5.** Hãy viết text block biểu diễn hai dòng `one`, `two` và **không** có LF cuối.

**Câu 6.** Một văn bản có nhiều dòng cần giữ khoảng trắng ở cuối mỗi dòng. Nên dùng escape sequence nào để bảo toàn dấu cách cuối dòng?

**Câu 7.** Khi nào `NumberFormat` hoặc `DateTimeFormatter` thích hợp hơn việc chỉ dùng `%s`?

**Đáp án gợi ý**

1. `true`; dấu đóng ở dòng riêng nên có LF ở cuối.
2. Vì dấu `\` mở escape sequence; ví dụ `\l` không hợp lệ. Cách viết đúng trong mã Java là `"C:\\logs\\app.log"`.
3. Cách thứ nhất truyền tường minh `Locale.US`; `formatted` sử dụng locale FORMAT mặc định.
4. Vì ghép chuỗi không tách tham số khỏi cấu trúc câu SQL. Dùng `PreparedStatement` và `setString(...)`.
5. `String value = """` rồi xuống dòng, viết `one`, `two""";` trên dòng tiếp theo với căn lề nhất quán.
6. `\s`; escape được diễn giải sau khi loại khoảng trắng ngẫu nhiên của text block.
7. Khi cần quy tắc locale, ngày tháng, đơn vị tiền hoặc chính sách hiển thị riêng, formatter chuyên dụng thể hiện mục đích rõ hơn.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 27 — §3.10.5 String Literals](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-3.html#jls-3.10.5): quy tắc string literal thông thường.
- [Java Language Specification, Java SE 27 — §3.10.6 Text Blocks](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-3.html#jls-3.10.6): cú pháp text block và thứ tự chuẩn hóa nội dung.
- [Java Language Specification, Java SE 27 — §3.10.7 Escape Sequences](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-3.html#jls-3.10.7): các escape sequence hợp lệ.
- [Java SE 27 API — String](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/String.html): `format`, `formatted`, `stripIndent`, `translateEscapes`, `lines`.
- [Java SE 27 API — Formatter](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Formatter.html): cú pháp format specifier, flag, width, precision và locale.
- [Java SE 27 API — NumberFormat](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/text/NumberFormat.html): định dạng số và tiền theo locale.
- [Java SE 27 API — DateTimeFormatter](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/format/DateTimeFormatter.html): định dạng ngày giờ hiện hành.
- [JEP 378 — Text Blocks](https://openjdk.org/jeps/378): lịch sử chính thức hóa text block.
- [Java Language Changes by Release — Java SE 27](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html): thông tin tính năng String Templates đã bị rút từ JDK 23.
