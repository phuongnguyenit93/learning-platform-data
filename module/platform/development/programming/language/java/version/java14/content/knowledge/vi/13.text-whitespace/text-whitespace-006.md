# Giữ khoảng trắng cuối dòng bằng escape phù hợp trong Java text blocks

## 1. Vấn đề và giải pháp hiện đại

**Java text block** là một dạng literal `String` nhiều dòng được giới hạn bởi `"""`. Khi biên dịch, Java chủ động bỏ phần khoảng trắng không thiết yếu (*incidental whitespace*), bao gồm **các dấu cách/tab vật lý ở cuối mỗi dòng**. Điều này làm nội dung trong mã nguồn dễ đọc, nhưng nếu dữ liệu đầu ra phải giữ đúng số dấu cách ở cuối dòng, việc chỉ gõ dấu cách trước phím Enter **không bảo đảm** chúng sẽ còn trong `String` runtime.

Giải pháp chuẩn là dùng escape **`\s`** trong text block. Escape này được dịch thành **một dấu cách ASCII, U+0020**, ở giai đoạn **sau** khi compiler đã loại bỏ trailing whitespace. Nó vừa có thể thêm một dấu cách vào cuối dòng, vừa làm dấu chặn để **những dấu cách vật lý nằm trước `\s`** không bị xóa.

```java
String fixedWidth = """
    red  \s
    green\s
    blue \s
    """;
```

Trong `fixedWidth`, ba dòng lần lượt là `red` + 3 dấu cách, `green` + 1 dấu cách, `blue` + 2 dấu cách. **Mỗi dòng dài đúng 6 ký tự không tính LF**.

| Phần thân dòng trong mã nguồn | Dữ liệu thật trong `String` | Ký tự trước LF |
| --- | --- | ---: |
| `red  \s` | `red` + 3 spaces | 6 |
| `green\s` | `green` + 1 space | 6 |
| `blue \s` | `blue` + 2 spaces | 6 |

Trong dòng `red  \s` có **hai dấu cách thật** nằm trước escape; `\s` tạo thêm dấu thứ ba. Vì vậy, **`\s` không có nghĩa “giữ đúng một dấu cách tổng cộng” nếu trước nó đã có các dấu cách thật**.

**Phiên bản hiện hành:** text blocks bắt đầu ở Java 13 dưới dạng preview (JEP 355), được cải thiện ở Java 14 preview thứ hai (JEP 368), rồi **trở thành tính năng chính thức từ Java 15** (JEP 378). Escape `\s` cùng line continuation `\` là cú pháp **vẫn áp dụng trên Java 17+**; không cần `--enable-preview`. Bài này trình bày quy tắc chuẩn hiện tại, không hướng dẫn cách dùng bản preview cũ.

Mục tiêu: hiểu vì sao whitespace bị loại, chọn đúng `\s`/`\040`/`\`, kiểm tra số ký tự, kiểm soát newline cuối chuỗi và tránh mất khoảng trắng khi xử lý `String` ở runtime.

## 2. Phân biệt khoảng trắng cuối dòng với khoảng trắng khác

Trong một text block có ba loại khoảng trắng nên phân biệt:

- **Leading indentation:** khoảng trắng/tab ở đầu dòng, thường dùng để canh mã nguồn. Compiler loại bỏ **phần thụt lề không thiết yếu** dựa trên cách bố trí các dòng và dấu đóng `"""`. Phần thụt có chủ đích còn lại có thể được giữ.
- **Khoảng trắng bên trong nội dung:** dấu cách giữa các từ, chẳng hạn `hello  world` có hai dấu cách ở giữa. Chúng không phải trailing whitespace và bình thường được giữ.
- **Trailing whitespace:** khoảng trắng/tab ngay trước ký tự kết thúc dòng. Java text blocks mặc định xóa chúng, bởi khoảng trắng vô hình ở cuối dòng rất dễ bị editor/formatter chỉnh sửa mà người đọc không biết.

Ví dụ:

```java
String example = """
    red   
    green
    """;
```

Ở dòng `red` trong ví dụ có ba dấu cách vật lý sau chữ `d`. Chúng bị loại bỏ khỏi giá trị `String`. Kết quả tương đương:

```java
String example = "red\ngreen\n";
```

Nếu trình soạn thảo Markdown đã xóa sẵn các dấu cách thật trong ví dụ, kết quả runtime vẫn là chuỗi trên. Đây chính là lý do **không nên mã hóa dữ liệu quan trọng bằng trailing spaces vô hình trong file nguồn**.

**`\s` khác các escape khác:**

| Cú pháp trong mã Java | Giá trị sau khi dịch | Có dùng để giữ dấu cách U+0020? |
| --- | --- | --- |
| `\s` | Một dấu cách ASCII | **Có, nên ưu tiên** |
| `\040` | Dấu cách ASCII theo octal | Có, nhưng ít dễ đọc hơn |
| `\t` | Một ký tự tab | Không, không tương đương space |
| `\n` | Một LF | Không, đây là xuống dòng |
| `\r` | Một CR | Không, đây là carriage return |
| `\\` | Một backslash thật | Không |
| `\` + line terminator | Nối dòng, **không thêm ký tự** | Không; cần kết hợp `\s` khi muốn có space |
| `\u0020` | Unicode escape dịch sớm thành dấu cách | **Không phù hợp** để bảo toàn trailing space |

## 3. Vì sao `\s` không bị compiler xóa?

Theo **Java Language Specification (JLS) `3.10.6**, Java xử lý nội dung text block theo đúng thứ tự:

1. **Chuẩn hóa line terminators:** `CR` và `CRLF` ở nguồn chuyển thành `LF`.
2. **Loại bỏ incidental whitespace:** áp dụng phép xử lý tương đương `String.stripIndent()`, loại phần thụt không thiết yếu và trailing whitespace của mỗi dòng.
3. **Dịch escape sequences:** áp dụng phép dịch tương đương `String.translateEscapes()`. Chỉ lúc này `\s` thành một dấu cách, `\040` thành dấu cách, hoặc backslash trước line terminator xóa xuống dòng.

Cụ thể:

```java
String value = """
    cat  \s
    """;
```

Ở **bước 2**, dòng mã `cat  \s` kết thúc bằng chữ `s`, chứ **không** kết thúc bằng dấu cách vật lý; hai dấu cách trước escape được xem là một phần của nội dung và được giữ. Ở **bước 3**, `\s` đổi thành dấu cách. Kết quả là `"cat   \n"` (ba dấu cách trước LF).

Nói cách khác, dấu cách do `\s` tạo ra **xuất hiện sau khi bước xóa trailing whitespace đã hoàn thành**. Compiler không quay lại để xóa chúng lần nữa.

### 3.1. Viết nhiều `\s` hay dùng một escape làm hàng rào?

Cả hai cách sau cho cùng kết quả:

```java
String first = """
    key\s\s\s
    """;

String second = """
    key  \s
    """;
```

Cả `first` và `second` đều là `"key   \n"`. Cách dùng nhiều `\s` khiến mỗi dấu cách cần giữ **hiện ra trực tiếp** trong mã nguồn. Cách dùng một `\s` ở cuối sẽ giữ thêm các dấu cách vật lý đứng trước nó, phù hợp khi muốn canh các cột dễ đọc.

Với định dạng dữ liệu yêu cầu đúng độ dài từng dòng, nên **test độ dài**, không chỉ tin vào khoảng cách nhìn thấy.

### 3.2. Nếu có dấu cách *sau* `\s` thì sao?

Xét đoạn:

```java
String value = """
    Q\s  
    """;
```

Sau `\s` là hai dấu cách thật (dễ bị trình soạn thảo giấu đi). Ở bước 2, hai dấu cách cuối dòng bị xóa; ở bước 3, `\s` được dịch thành **một** dấu cách. Giá trị là `"Q \n"`, không phải ba dấu cách. Vì thế hãy đặt `\s` ở vị trí cuối phần nội dung **có nghĩa**, không thêm dấu cách thật sau nó.

### 3.3. Một dòng có `\s` không tự loại bỏ LF

Text block:

```java
String value = """
    Done\s
    """;
```

cho `"Done \n"`. `\s` chỉ là dấu cách. **LF vẫn còn** vì nội dung có line terminator trước dấu đóng trên dòng riêng. Phải tách bạch hai câu hỏi: *giữ dấu cách ở cuối dòng* và *có giữ newline cuối chuỗi hay không*.

## 4. Chương trình chạy được: đếm chính xác dấu cách cuối dòng

Để quan sát ký tự vô hình, chương trình dưới đây biến mỗi dấu cách thành `_`, tab thành `[TAB]`, carriage return thành `[CR]` và line feed thành `[LF]` **chỉ khi in**. Dữ liệu gốc được giữ trong các biến `String`.

**Tệp `TextBlockSpacesDemo.java` — Java 17+:**

```java
public class TextBlockSpacesDemo {
    static String visible(String s) {
        return s.replace(" ", "_")
                .replace("\t", "[TAB]")
                .replace("\r", "[CR]")
                .replace("\n", "[LF]");
    }

    static void show(String name, String content) {
        System.out.println(name + "=" + visible(content));
        System.out.println(name + ".length=" + content.length());
    }

    public static void main(String[] args) {
        String stripped = """
                red   
                green
                """;

        String fenced = """
                red  \s
                green\s
                blue \s
                """;

        String repeated = """
                one\s\s\s
                two\040\040
                """;

        String joined = """
                Hello\s\
                world
                """;

        String noFinalNewline = """
                Done\s""";

        String finalLineSuppressed = """
                End\s\
                """;

        String crlf = """
                A\s\r
                B\s\r
                """;

        show("stripped", stripped);
        show("fenced", fenced);
        show("repeated", repeated);
        show("joined", joined);
        show("noFinalNewline", noFinalNewline);
        show("finalLineSuppressed", finalLineSuppressed);
        show("crlf", crlf);

        System.out.println("fenced-lines=" + fenced.lines()
                .mapToInt(String::length).boxed().toList());
        System.out.println("withoutTrailing=" +
                visible(fenced.stripTrailing()));
    }
}
```

Dòng `red` trong `stripped` có dấu cách thật cuối dòng để minh họa. Nếu editor đã loại chúng đi trước khi bạn dán hoặc chạy mã, kết quả runtime vẫn giống nhau.

**Lệnh chạy:**

```bash
javac --release 17 -encoding UTF-8 TextBlockSpacesDemo.java
java TextBlockSpacesDemo
```

**Stdout đã kiểm chứng chính xác:**

```text
stripped=red[LF]green[LF]
stripped.length=10
fenced=red___[LF]green_[LF]blue__[LF]
fenced.length=21
repeated=one___[LF]two__[LF]
repeated.length=13
joined=Hello_world[LF]
joined.length=12
noFinalNewline=Done_
noFinalNewline.length=5
finalLineSuppressed=End_
finalLineSuppressed.length=4
crlf=A_[CR][LF]B_[CR][LF]
crlf.length=8
fenced-lines=[6, 6, 6]
withoutTrailing=red___[LF]green_[LF]blue
```

**Phân tích cụ thể:**

- `stripped`: chuỗi tương đương `"red\ngreen\n"`. Độ dài bằng `3 + 1 + 5 + 1 = 10`, không tính các dấu cách vô hình mà compiler đã loại.
- `fenced`: `red` giữ 3 dấu cách, `green` giữ 1, `blue` giữ 2. Ba dòng, mỗi dòng **6 ký tự trước LF**; có ba LF nên tổng độ dài `6 × 3 + 3 = 21`.
- `repeated`: `one\s\s\s` tạo ba dấu cách; `two\040\040` tạo hai dấu cách. Cả `\s` và octal `\040` được dịch sau bước xóa trailing whitespace.
- `joined`: `Hello\s\` tạo một dấu cách bằng `\s` rồi **bỏ LF** ở cuối dòng nguồn nhờ `\`. Vì thế `Hello` và `world` được nối thành `"Hello world\n"`, dài 12.
- `noFinalNewline`: dấu đóng cùng dòng với `Done\s`, nên giá trị là `"Done "`, dài 5, không có LF ở cuối.
- `finalLineSuppressed`: dấu `\` cuối dòng nguồn bỏ LF ngay trước dấu đóng; giá trị `"End "`, dài 4.
- `crlf`: compiler chuẩn hóa LF nguồn trước, rồi `\r` mới thêm ký tự CR vào trước LF; giá trị `"A \r\nB \r\n"`, dài 8.
- `String.lines()` tạo stream các dòng **không mang line terminator**; độ dài `[6, 6, 6]` xác nhận từng dòng được đệm đúng.
- `stripTrailing()` xóa whitespace **ở cuối toàn bộ chuỗi**, nên bỏ LF và hai dấu cách cuối `blue`. Dấu cách cuối dòng `red` và `green` vẫn tồn tại, bởi chúng không ở cuối **toàn bộ** String.

### 4.1. Kiểm tra bằng compiler lint

Có thể chạy:

```bash
javac --release 17 -Xlint:text-blocks -encoding UTF-8 TextBlockSpacesDemo.java
```

Nếu mã nguồn còn dấu cách vật lý cuối dòng `red` của `stripped`, `javac` sẽ cảnh báo dạng `[text-blocks] trailing white space will be removed`. Cảnh báo là thông tin hữu ích trong code review, không tự làm lệnh biên dịch thất bại.

Nếu editor đã xóa các dấu cách vô hình trước khi compiler chạy, cảnh báo không xuất hiện; **test `String` runtime** vẫn là cách xác nhận chính xác. `-Xlint:text-blocks` cũng giúp tìm các bất nhất trong cách thụt lề bằng tab và space.

## 5. Đừng nhầm `\s` với `\040`, `\\s`, `\u0020` hoặc `\t`

### 5.1. `\s` và `\040`

`\s` là escape cho **một dấu cách ASCII**. `\040` cũng tạo đúng ký tự đó nhưng theo **mã octal**. Cả hai được xử lý sau bước xóa incidental whitespace, nên đều có thể giữ dấu cách cuối dòng:

```java
String modern = """
    A\s
    """;

String octal = """
    A\040
    """;
```

Hai giá trị đều tương đương `"A \n"`. Với code mới, **ưu tiên `\s`** vì ý nghĩa dễ nhận biết. Dùng `\040` chủ yếu khi đọc code đang biểu diễn dữ liệu bằng octal hoặc khi cần hiểu công thức từ tài liệu JLS.

### 5.2. `\t` không phải dấu cách

```java
String tabbed = """
    A\t
    """;
```

Kết quả gồm `A`, **một tab**, rồi LF. Tab có thể hiển thị ở nhiều độ rộng khác nhau tùy console/editor; nếu giao thức yêu cầu U+0020 và số ký tự chính xác, `\t` không thay thế được `\s`.

### 5.3. `\\s` tạo dấu backslash thật

```java
String literalBackslashS = """
    A\\s
    """;
```

Trong file Java, `\\` biểu diễn **một dấu backslash**, theo sau là chữ `s` bình thường. Chuỗi kết quả chứa `A`, `\`, `s` và LF — **không có dấu cách**. Để sinh dấu cách ở cuối dòng, mã Java thật phải chứa **một** backslash trước `s`.

Nếu bạn tạo mã Java thông qua JSON, JavaScript hoặc shell, các tầng đó có thể yêu cầu escaping riêng. Luôn kiểm tra **nội dung .java cuối cùng** đã được tạo thay vì đếm backslash trong cấu hình của công cụ trung gian.

### 5.4. `\u0020` được dịch quá sớm

Java xử lý các **Unicode escapes** như `\u0020` ngay ở giai đoạn dịch nguồn thành token, **trước** khi text block xử lý incidental whitespace. Do vậy, nếu đặt `Q\u0020` cuối dòng trong một text block, `\u0020` được chuyển thành dấu cách thật, rồi compiler xóa dấu cách đó như trailing whitespace.

**Kết luận:** `\u0020` không phải cách bảo toàn trailing spaces trong text block. Hãy dùng `\s` hoặc `\040` để đưa dấu cách vào **sau** bước strip.

### 5.5. Chương trình so sánh các escape

**Tệp `EscapeCompareDemo.java` — Java 17+:**

```java
public class EscapeCompareDemo {
    static String show(String value) {
        return value.replace(" ", "_")
                .replace("\t", "[TAB]")
                .replace("\n", "[LF]");
    }

    public static void main(String[] args) {
        String unicode = """
                Q\u0020
                """;
        String slashS = """
                Q\\s
                """;
        String tab = """
                Q\t
                """;
        String spacesAfterEscape = """
                Q\s  
                """;
        String explicitOctal = """
                Q\040\040
                """;

        System.out.println("unicode=" + show(unicode));
        System.out.println("slashS=" + show(slashS));
        System.out.println("tab=" + show(tab));
        System.out.println("spacesAfterEscape=" + show(spacesAfterEscape));
        System.out.println("explicitOctal=" + show(explicitOctal));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EscapeCompareDemo.java
java EscapeCompareDemo
```

**Stdout chính xác:**

```text
unicode=Q[LF]
slashS=Q\s[LF]
tab=Q[TAB][LF]
spacesAfterEscape=Q_[LF]
explicitOctal=Q__[LF]
```

Trong `spacesAfterEscape`, hai dấu cách vật lý sau `\s` bị xóa; dấu cách do `\s` tạo ra vẫn còn. Trong `unicode`, dấu cách do `\u0020` tạo ra quá sớm nên cũng bị xóa. `slashS` chứa literal `\s`, không phải space.

## 6. Giữ khoảng trắng cuối dòng khác với giữ xuống dòng cuối String

Opening delimiter `"""` phải được theo sau bởi line terminator, nhưng newline ngay sau dấu mở **không tạo dòng trống đầu tiên** trong giá trị String. Dấu đóng `"""` mới là điểm quyết định có thêm newline cuối giá trị hay không.

**Dấu đóng ở dòng riêng:**

```java
String one = """
    Done\s
    """;
```

`one` là `"Done \n"`: một dấu cách ở cuối **dòng nội dung**, rồi LF.

**Dấu đóng cùng dòng nội dung:**

```java
String two = """
    Done\s""";
```

`two` là `"Done "`: có dấu cách ở cuối **chuỗi**, nhưng không có LF.

**Nối dòng bằng backslash trước line terminator:**

```java
String three = """
    Done\s\
    """;
```

`three` cũng là `"Done "`. Ở đây `\s` tạo dấu cách, còn `\` trước newline **loại bỏ LF**. Đừng nhầm hai escape: `\s` không xóa newline, `\` nối dòng không tạo dấu cách.

Bảng chọn nhanh:

| Ý định | Kỹ thuật |
| --- | --- |
| Một dấu cách cuối dòng | `\s` |
| Ba dấu cách cuối dòng | `\s\s\s`, hoặc hai spaces thật trước `\s` |
| Bỏ newline giữa hai dòng nguồn | `\` ở cuối dòng nguồn |
| Có một space rồi nối từ sang dòng tiếp theo | `Hello\s\` rồi dòng kế tiếp `world` |
| Giữ space ở cuối String, không có LF | `Done\s"""` hoặc `Done\s\` + dấu đóng dòng dưới |
| Tạo xuống dòng tường minh | `\n`, tránh tạo thêm LF không mong muốn |
| Tạo CRLF khi format yêu cầu | `\r` đặt trước LF trong kết quả, rồi kiểm tra ký tự/byte |

### 6.1. Ví dụ nối dòng mà vẫn có một dấu cách

```java
String joined = """
    Hello\s\
    world
    """;
```

Giá trị là `"Hello world\n"`, không phải `"Helloworld\n"`. Nếu bỏ `\s` và chỉ có `Hello\`, hai từ sẽ nối liền không có space.

### 6.2. CRLF và yêu cầu byte-level

Văn bản nguồn có line ending CRLF vẫn được compiler **chuẩn hóa thành LF trong text block**. Nếu cần CRLF khi xuất file hoặc nói chuyện qua giao thức, phải tạo CR rõ ràng ở dữ liệu cuối cùng:

```java
String message = """
    A\s\r
    B\s\r
    """;
```

Đoạn này cho `"A \r\nB \r\n"`. Nếu xuất qua network/file, `String.length()` là số **UTF-16 code units**, không phải số byte ở mọi charset. Khi đặc tả yêu cầu byte chính xác, hãy xác định encoding và test mảng bytes.

## 7. Ứng dụng thực tế và cách kiểm thử

### 7.1. Văn bản có độ rộng cố định

Trong định dạng dạng cột, số dấu cách sau dữ liệu đôi khi là một phần của giao thức. Ví dụ `fixedWidth` ở phần đầu có ba dòng đều dài 6 ký tự trước LF:

```java
boolean allSix = fixedWidth.lines()
        .allMatch(line -> line.length() == 6);
System.out.println(allSix); // true
```

Đây là snippet nằm trong phương thức có `fixedWidth`. `String.lines()` không gộp line terminator vào từng phần tử, nên phù hợp kiểm tra độ dài văn bản trước LF. Nếu yêu cầu **byte width**, phải kiểm tra bytes sau khi encode.

Với dữ liệu động hoặc bảng lớn, không nên tạo hàng trăm dòng `\s` thủ công. Thường dễ bảo trì hơn khi dùng formatter có kiểm soát (ví dụ `String.format`) rồi test output; text block thích hợp nhất cho mẫu tĩnh, fixture và đoạn văn nhiều dòng ngắn.

### 7.2. Golden-file tests và so sánh nội dung

Trong unit test so sánh String hoặc snapshot, khác đúng **một dấu cách cuối dòng** cũng khiến dữ liệu không khớp. Viết rõ:

```java
String expected = """
    status: ok\s
    """;
```

Kết quả là `"status: ok \n"`. Dùng assertion trên String kỳ vọng và dữ liệu thực, hoặc debug bằng hàm `visible()`. Đừng đánh giá bằng hình chụp console, bởi dấu cách/tab/LF đều khó nhìn.

### 7.3. HTML, XML, JSON, SQL

Text blocks giúp trình bày các đoạn HTML/XML/JSON/SQL dễ đọc hơn, nhưng **không phải mọi khoảng trắng cuối dòng đều cần giữ**. Với JSON, whitespace trong một string value khác whitespace ở ngoài token; với XML/HTML, ngữ nghĩa phụ thuộc vị trí; SQL thường bỏ qua nhiều space giữa token, nhưng không nên dựa vào giả định đó khi kiểm tra dữ liệu.

Chỉ thêm `\s` ở nơi **contract yêu cầu**. Dùng escape vô tội vạ có thể tạo khác biệt không mong muốn trong snapshot, chữ ký số hoặc checksum.

### 7.4. Phương thức String có thể xóa các dấu cách đã giữ

`\s` giúp compiler giữ khoảng trắng trong giá trị literal. Nhưng nếu gọi `strip()`, `trim()`, `stripTrailing()`, `stripIndent()` hoặc một bước chuẩn hóa khác **sau khi String đã được tạo**, dữ liệu vẫn có thể bị xóa theo ngữ nghĩa của phương thức.

Ví dụ trong chương trình chính: `fenced.stripTrailing()` bỏ LF cuối cùng cùng hai dấu cách cuối dòng `blue`, còn các dấu cách ở hai dòng trước vẫn giữ. `stripTrailing()` làm việc ở **cuối toàn bộ chuỗi**, không tự loại trailing spaces của mọi dòng. Phải test kết quả **sau tất cả phép biến đổi**, không chỉ literal ban đầu.

### 7.5. Dùng lint và assertions cùng nhau

`javac -Xlint:text-blocks` giúp phát hiện trailing whitespace vật lý bị xóa hoặc indentation không nhất quán; assertions bảo đảm **dữ liệu runtime đúng từng ký tự**. Hai cách bổ sung cho nhau. Khi file đã được editor tự xóa whitespace, lint không còn thấy lỗi nguồn, nhưng phép so sánh output vẫn bắt được sai lệch dữ liệu.

## 8. Lỗi phổ biến

**Lỗi 1 — Dựa vào dấu cách thật ở cuối dòng.** Text block compiler sẽ bỏ trailing whitespace. Sửa bằng `\s` hoặc `\040`; thêm test số dấu cách.

**Lỗi 2 — Đếm sai `\s` khi còn spaces vật lý trước nó.** `red  \s` cho ba spaces, không phải một. Có thể chọn `red\s\s\s` nếu muốn từng space rõ ràng trong code.

**Lỗi 3 — Viết `\\s` trong file Java.** Kết quả là backslash + `s`, không phải space. Kiểm tra tầng escaping nếu code sinh từ JSON/shell.

**Lỗi 4 — Viết `\u0020` để bảo vệ trailing space.** Unicode escape được dịch trước bước strip và bị xóa như space thường. Sửa bằng `\s`/`\040`.

**Lỗi 5 — Dùng `\t` để giả làm dấu cách.** Tab khác U+0020 và có thể hiển thị độ rộng khác nhau; với định dạng cố định, dùng đúng ký tự yêu cầu.

**Lỗi 6 — Dùng `\` nối dòng và mong nó tự thêm space.** Escape line continuation chỉ **bỏ LF**. Nếu nối `Hello` với `world`, phải có `\s` nếu cần `Hello world`.

**Lỗi 7 — Nhầm space cuối dòng với LF cuối chuỗi.** `Done\s\n` có space và LF; `Done\s"""` không có LF. Dựa vào vị trí dấu đóng hoặc line continuation phù hợp.

**Lỗi 8 — Dùng `\r` và `\n` sai, khiến CRLF/LF đôi.** Compiler chuẩn hóa line endings nguồn trước khi dịch escape; chỉ thêm những ký tự thực sự cần.

**Lỗi 9 — Gọi `stripTrailing()` sau khi dùng `\s`.** Các phương thức strip ở runtime không phải compiler, chúng vẫn có thể xóa khoảng trắng cần giữ.

**Lỗi 10 — Dùng `println` để đếm LF.** `println` tự thêm newline sau String; dùng `length()`, `endsWith()` hoặc `visible()` để quan sát dữ liệu thực.

**Lỗi 11 — Viết opening delimiter và nội dung cùng dòng:**

```java
// KHÔNG hợp lệ: sau opening """ phải có line terminator.
String invalid = """Hello""";
```

Cách đúng là xuống dòng sau `"""`. Đây là cú pháp text block chính thức vẫn đang áp dụng trên Java 17+.

**Lỗi 12 — Không kiểm tra bộ ký tự khi xuất file.** Số ký tự UTF-16 không tự đồng nhất với số byte. Với giao thức chính xác, kiểm thử byte sau encoding.

## 9. Bài tập thực hành

1. Tạo text block chứa hai dòng `yes` và `no`, mỗi dòng có **một** space trước LF. Viết `yes\s` và `no\s`; dùng `lines().mapToInt(String::length)`, kỳ vọng lần lượt 4 và 3.
2. Viết hai text blocks `key\s\s\s` và `key  \s`; chứng minh hai chuỗi kết quả bằng nhau.
3. Dự đoán giá trị của dòng `Q\s  ` (hai spaces thật sau escape) và giải thích vì sao chỉ còn **một** space.
4. Tạo ba dòng `one`, `two`, `three`, mỗi dòng **6 ký tự** không kể LF; đệm bằng `\s` để đạt độ dài yêu cầu.
5. Tạo chuỗi `"End "` có một space ở cuối nhưng **không** có LF cuối. Thử hai cách: dấu đóng ngay sau `End\s` hoặc viết `End\s\` rồi dấu đóng dòng tiếp.
6. Nối hai dòng nguồn `Hello` và `world` thành `"Hello world\n"` bằng `\s` kết hợp line continuation.
7. So sánh `Q\u0020` với `Q\s` ở cuối dòng text block; giải thích sự khác biệt bằng ba bước xử lý JLS.
8. Thử `Q\t` và quan sát dữ liệu bằng hàm `visible()`; tại sao kết quả chứa `[TAB]` chứ không phải `_`?
9. Tạo `"A \r\n"` bằng một dòng text block có `A\s\r`, sau đó kiểm tra length và ký tự `[CR][LF]`.
10. Bật `-Xlint:text-blocks` cho ví dụ có trailing spaces thật rồi thay bằng `\s`. Khi nào lint cảnh báo? Khi nào cần kiểm chứng bằng test?
11. Gọi `stripTrailing()` trên text block có dấu cách cuối dòng cuối và LF cuối; quan sát ký tự mất đi, giải thích vì sao các dòng trước vẫn giữ space.
12. Với một fixture cố định, so sánh cả String và bytes trong encoding yêu cầu. Nêu khi nào `String.length()` không đủ để đo kích thước truyền tải.

**Đáp án định hướng:** (1) `[4,3]`; (2) mỗi dòng chứa ba dấu cách; (3) trailing spaces sau `\s` bị strip, chỉ `\s` được dịch muộn; (4) đệm đến độ dài 6; (5) dùng closing delimiter hoặc nối dòng; (6) `Hello\s\` rồi `world`; (7) Unicode escape được dịch sớm, `\s` dịch sau strip; (8) tab khác space; (9) mỗi CR và LF là một ký tự; (10) lint phát hiện nguồn còn raw trailing spaces, test kiểm tra output; (11) `stripTrailing()` chỉ xử lý cuối toàn bộ String; (12) encoding có thể dùng nhiều byte cho một ký tự.

## 10. Tài liệu chính thức

- **Java Language Specification (Java SE 25), `3.10.6 — Text Blocks:** quy tắc cú pháp và thứ tự normalize line endings → remove incidental whitespace → interpret escapes: https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6
- **JLS `3.10.7 — Escape Sequences:** định nghĩa `\s`, `\040`, line continuation, tab, CR và LF: https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.7
- **Oracle Java 17 Programmer's Guide to Text Blocks:** giải thích *Trailing White Space*, `\s` và `-Xlint:text-blocks`: https://docs.oracle.com/en/java/javase/17/text-blocks/index.html
- **OpenJDK JEP 368 — Text Blocks (Second Preview):** bối cảnh Java 14 bổ sung escape mới: https://openjdk.org/jeps/368
- **OpenJDK JEP 378 — Text Blocks:** tính năng chính thức từ Java 15: https://openjdk.org/jeps/378
- **Java SE 17 `String` API:** `lines()`, `stripTrailing()`, `stripIndent()` và `translateEscapes()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html

**Ghi nhớ:** Java loại bỏ trailing whitespace của text block **trước** khi dịch escape. Do đó **`\s` là cách viết phù hợp để bảo toàn dấu cách cuối dòng**; `\040` cũng có tác dụng, nhưng `\s` dễ đọc hơn. Nếu cần vừa có space vừa bỏ LF, kết hợp `\s` với **`\` line continuation**. Hãy kiểm tra String/bytes kết quả thay vì trông chờ dấu cách vô hình trong mã nguồn.