# Chẩn đoán Java text block qua compiler warning và kiểm thử chuỗi

> **Chủ đề:** Java 15 → **Chẩn đoán lỗi** → **Chẩn đoán text block qua compiler warning và kiểm thử chuỗi**. Bài tập trung vào cách tìm và sửa lỗi **whitespace, indentation, newline, escape và kết quả String thực tế** của text block bằng `javac -Xlint:text-blocks`, `-Werror` và kiểm thử so sánh chuỗi **từng ký tự**. Text block trở thành tính năng Java **chính thức từ Java 15**, vẫn còn áp dụng trên Java 17, 21, 25 và các JDK hiện hành. Ví dụ runnable dùng **JDK 17+**, không dùng chế độ preview cũ hay API nội bộ đã lỗi thời.

## 1. Triệu chứng thường gặp: nhìn source đúng nhưng giá trị String sai

Một Java text block giúp viết nội dung nhiều dòng mà không cần ghép hàng loạt string literal:

```java
String message = """
    first
    second
    """;
```

Giá trị thực của `message` là:

```text
first\nsecond\n
```

Dòng hiển thị trên dùng hai ký tự **`\` + `n`** để mô tả ký tự xuống dòng; giá trị `String` thật chứa các ký tự **LF (U+000A)** chứ không chứa hai ký tự `\` và `n`.

Khi một API kiểm tra chính xác bytes/characters, chỉ một newline hoặc space khác nhau cũng có thể làm dữ liệu không khớp:

- **JSON/XML snapshot test** bị lệch.
- **HTTP request body** hoặc payload chữ ký không trùng bytes mong đợi.
- **SQL fixture** thiếu/thừa newline hoặc khoảng trắng.
- **Golden-file test** thất bại trên máy Windows/Linux.
- **Regex** hoặc đường dẫn có `\` bị Java diễn giải như một escape.
- Text block chứa **TAB và spaces lẫn nhau**, nhìn thẳng cột trong editor nhưng giá trị `String` lại lệch.
- Trailing spaces “nhìn như còn đó” trong source nhưng compiler **loại bỏ**.
- Dòng cuối có hoặc không có newline vì **vị trí dấu `"""` kết thúc**.

Text block **vẫn là `String` thông thường** sau khi biên dịch. Lỗi cần chẩn đoán thuộc về cách **ký tự của source được biến đổi thành chuỗi** và cách chương trình **tiêu thụ chuỗi đó**, không phải một kiểu dữ liệu đặc biệt chỉ tồn tại lúc runtime.

Mục tiêu của bài này: nhìn một text block, dự đoán chính xác `String` mà Java tạo ra, biết khi nào compiler cảnh báo, và viết một test chứng minh giá trị đúng thay vì dựa vào `System.out.println`.

## 2. Cú pháp text block và hai vị trí delimiter không được nhầm

Text block được mở bằng **ba dấu nháy kép `"""`, theo sau bởi line terminator**; nội dung không được bắt đầu trên cùng dòng ngay sau opening delimiter.

**Đúng:**

```java
String correct = """
    alpha
    beta
    """;
```

**Sai cú pháp — không biên dịch:**

```java
// ERROR: thiếu line terminator sau opening delimiter.
String invalid = """alpha
    beta
    """;
```

Với ví dụ sai, `javac` có thể báo **`illegal text block open delimiter sequence, missing line terminator`**. Đây là **compiler error**, **không phải** warning của `-Xlint:text-blocks`.

Một text block có thể kết thúc theo hai cách thường gặp:

```java
// Closing delimiter ở dòng riêng: giá trị CÓ newline cuối.
String withLastLf = """
    red
    blue
    """;

// Closing delimiter ngay cuối dòng nội dung: KHÔNG có newline cuối.
String withoutLastLf = """
    red
    blue""";
```

Kiểm tra:

```java
System.out.println(withLastLf.equals("red\nblue\n"));     // true
System.out.println(withoutLastLf.equals("red\nblue"));    // true
```

Các snippet trên cần đặt trong một method/class và có khai báo biến tương ứng. Chúng minh họa **hai giá trị khác nhau**, dù việc in ra terminal có thể khó nhận biết. Đây thường là nguồn gốc của lỗi khi so sánh chuỗi **exact match**.

### Dòng xuống ngay sau `"""` mở đầu có được thêm vào String không?

**Không.** Line terminator bắt buộc ngay sau opening delimiter là một phần cú pháp mở, **không trở thành dòng trống đầu tiên** của chuỗi. Nếu muốn chuỗi bắt đầu bằng newline thật, phải có **dòng trống bên trong nội dung**:

```java
String beginsWithLf = """

    alpha
    """;
```

Giá trị `beginsWithLf` là `"\nalpha\n"`. Đừng đưa thêm hay bớt một dòng trống trong source chỉ để “làm đẹp” rồi cho rằng output không đổi.

### Không cần preview flag

Text block là tính năng chính thức từ Java 15; với JDK 17+, lệnh đơn giản:

```bash
javac -encoding UTF-8 TextBlockValueTests.java
java TextBlockValueTests
```

là đủ. **Không dùng `--enable-preview` hoặc `--source 14`** cho các bài text block hiện hành; các cách dùng preview từ giai đoạn trước Java 15 không phải hướng dẫn nên áp dụng hôm nay.

## 3. Ba bước compiler chuyển text block thành giá trị String

Mô hình xử lý theo Java Language Specification/JEP 378:

1. **Chuẩn hóa line terminators** trong nội dung nguồn: CRLF hoặc CR thường được chuẩn hóa thành **LF `\n`**.
2. **Loại incidental whitespace**: common leading indentation không mang nghĩa và trailing whitespace nằm cuối dòng được loại bỏ.
3. **Dịch escape sequences**: `\n`, `\t`, `\s`, `\\`, `\"`, ký hiệu nối dòng `\` + line terminator và các escape hợp lệ khác được diễn giải.

Sơ đồ:

```text
Source text giữa triple quotes
             |
             v
(1) Normalize line terminators
    CRLF / CR -> LF
             |
             v
(2) Strip incidental whitespace
    leading indent chung + trailing blanks
             |
             v
(3) Translate escape sequences
    \s -> U+0020, \t -> TAB, \ + newline -> bỏ newline
             |
             v
java.lang.String (runtime)
             |
             v
Kiểm thử bằng equals / length / code points / bytes
```

**Trình tự là quan trọng.** Vì escape được xử lý **sau bước loại whitespace**, `\s` đặt ở cuối dòng **có thể bảo vệ một space cuối dòng**, trong khi một dấu cách literal ở ngay mép phải thường bị xóa.

### Nhớ vai trò của Unicode escapes

Các **Unicode escapes trong mã nguồn Java** như `\u0020` được dịch **rất sớm**, trước cả quá trình phân tích token. Vì thế **không dùng `\u0020` thay cho `\s`** để giữ trailing space trong text block: ký tự space tạo từ Unicode escape có thể bị coi là incidental whitespace rồi bị strip.

Tương tự, khi viết dữ liệu chứa nhiều ký tự `\`, hãy kiểm tra cả lớp xử lý escape của Java trước khi kết luận dữ liệu có đúng bytes như bạn thấy trong editor.

## 4. Leading indentation: compiler bỏ thụt lề chung như thế nào?

Text block cho phép indent nội dung sao cho **dễ đọc trong Java source** mà không buộc mọi dấu space đó trở thành dữ liệu.

```java
String html = """
    <html>
        <body>
            <p>Hello</p>
        </body>
    </html>
    """;
```

Giá trị `html` bắt đầu bằng `<html>` **không có bốn space phía trước**, nhưng các dòng `<body>` và `<p>` vẫn giữ relative indentation của chúng.

Java xem common incidental indentation dựa trên **các dòng nội dung không trắng** cùng với vị trí đóng delimiter như một đường lề tham chiếu. Các dòng được dịch trái tương ứng, còn sự chênh lệch thụt lề tương đối được giữ.

### Closing delimiter là thành phần của tính toán indentation

Xét:

```java
String aligned = """
    red
      blue
    """;
```

Kết quả tương đương:

```java
"red\n  blue\n"
```

Nhưng nếu đặt closing delimiter **lùi sang trái hơn**:

```java
String keepMargin = """
        red
          blue
    """;
```

Kết quả giữ thêm spaces:

```java
"    red\n      blue\n"
```

**Không nhất thiết có compiler warning.** Hai text block trên đều cú pháp hợp lệ và có thể biên dịch sạch với `-Xlint:text-blocks`; nhưng **giá trị khác nhau**. Vì vậy compiler lint chỉ là một tầng phát hiện; **unit test so sánh chuỗi mới kiểm chứng contract**.

### Dòng trống và indentation

Những dòng blank/whitespace-only chịu quy tắc loại incidental whitespace của text block. Đừng dựa vào việc chèn spaces vô hình trên dòng trống để giữ bố cục dữ liệu nhạy cảm. Nếu ứng dụng cần một dòng trống, biểu diễn bằng **newline có chủ đích** và so sánh `String` thật.

### TAB không được tính như cột hiển thị

Trong tính toán common indentation, Java coi **mỗi ký tự whitespace** như một ký tự riêng, không quy đổi một TAB thành “bốn space” hoặc “tám space” theo thiết lập editor.

Ví dụ một dòng có 8 spaces và dòng khác có 1 TAB có thể **trông cùng cột trong editor** nhưng **không** có cùng số ký tự whitespace. Kết quả sau khi strip có thể mất cân đối.

Đây chính là một trong các lỗi mà `-Xlint:text-blocks` phát hiện.

## 5. Trailing whitespace: tại sao cuối dòng bị mất?

Ở text block, **trailing whitespace literal** của từng dòng là incidental và được compiler loại bỏ. Ví dụ nguồn trông như:

```text
String s = """
    red··
    green·
    """;
```

Trong sơ đồ này, dấu **`·` chỉ đại diện một space**, không phải ký tự nguồn Java để copy. Nếu trong file thật hai space đứng ngay sau `red` và một space ngay sau `green` trước LF, **những space ấy sẽ bị compiler strip**.

Giá trị có thể trở thành:

```java
"red\ngreen\n"
```

Điều này làm các định dạng nhạy cảm tới cuối dòng như Markdown hard-break bằng hai spaces, một số file test/golden file hoặc dữ liệu fixed-width dễ bị sai.

**Đừng cố sửa bằng cách đánh nhiều spaces hơn trong editor.** Hãy chọn cách biểu diễn rõ ràng:

- `\s` cho space cần giữ, xử lý **sau** bước strip whitespace.
- `\040` (octal escape cho ASCII space) trong những trường hợp bạn cần thể hiện rõ ký tự.
- Tạo chuỗi bằng concatenation/replacement khi mục đích thật sự cần trailing blanks.
- Lựa chọn giao thức/serialization phù hợp thay vì buộc text block phải chứa toàn bộ dữ liệu whitespace nhạy cảm.

### `\s` giữ space cuối dòng đúng cách

```java
String fixedWidth = """
    red  \s
    green\s
    """;
```

Trong dòng `red`, hai dấu space literal nằm **trước escape `\s`** nên không đứng ở vị trí cuối dòng khi compiler strip. Sau bước translate, `\s` trở thành **một space**. Kết quả:

```java
"red   \ngreen \n"
```

Dòng thứ nhất có **3 spaces** sau `red`, dòng thứ hai có **1 space** sau `green`.

**Lưu ý:** `\s` không phải marker “bảo vệ mọi ký tự trắng ở mọi vị trí”. Nó là một escape cho **ASCII space U+0020**; những ký tự trắng literal đứng **sau** `\s` ở cuối dòng vẫn có thể bị strip trước khi escape được dịch.

### Vì sao `\u0020` không thay được `\s`?

`\u0020` là Unicode escape được Java xử lý ở giai đoạn rất sớm, trước khi thực hiện incidental whitespace stripping. Vì thế nó không có cùng đặc tính “deferred translation” như `\s` hay `\040`.

Khi cần trailing space trong text block, dùng `\s` hoặc `\040` thay vì cố giấu một space qua `\u0020`.

## 6. Công cụ chẩn đoán thứ nhất: `javac -Xlint:text-blocks`

Compiler `javac` hiện hành có lint category **`text-blocks`**, bật bằng:

```bash
javac -encoding UTF-8 -Xlint:text-blocks Example.java
```

Với source có vấn đề, hai warning quan trọng là:

| Warning | Nội dung thường gặp | Nguyên nhân |
| --- | --- | --- |
| `inconsistent white space indentation` | Các ký tự spaces/TAB bị trộn theo cách gây mất cân đối indentation | Common indent theo ký tự không trùng lề editor |
| `trailing white space will be removed` | Các spaces/TAB ở cuối dòng text block sẽ bị strip | Giá trị sau biên dịch khác điều nhìn trong source |

**Thông điệp cụ thể và vị trí dòng có thể thay đổi theo bản javac.** Không xây hệ thống CI phụ thuộc tuyệt đối vào câu tiếng Anh và số dòng của mọi vendor. Hai kiểu warning và tên lint category được tài liệu Java hiện hành mô tả.

### Lint có kích hoạt trên tất cả text block không?

Không. Một text block có nội dung hợp lệ, indentation dùng spaces thống nhất và không chứa trailing whitespace có thể hoàn toàn **không sinh warning**.

Điều đó **không chứng minh giá trị String đúng với nghiệp vụ**. Ví dụ closing delimiter bị lùi trái có thể thay đổi indentation mà vẫn không nhận warning. Cần unit test.

### Kiểm tra javac có hỗ trợ category

```bash
javac --help-lint
```

Tìm mục `text-blocks`. Đây là cách kiểm tra hiệu lực trên **chính compiler** bạn dùng trong môi trường build.

### `-Xlint:all` có thay được không?

```bash
javac -Xlint:all Example.java
```

Có thể phát hiện nhiều loại vấn đề hơn, bao gồm text-block warnings, nhưng cũng có thể sinh warning **không liên quan** (unchecked, deprecation, raw types...). Để chẩn đoán riêng text block, dùng `-Xlint:text-blocks` là cách mục tiêu rõ nhất.

## 7. Khi nào warning trở thành lỗi build? `-Werror`

Bản thân một `javac warning` **không nhất thiết làm biên dịch thất bại**. Muốn pipeline CI không chấp nhận những cảnh báo còn tồn tại:

```bash
javac -encoding UTF-8 \
    -Xlint:text-blocks -Werror \
    TextBlockValueTests.java
```

**Ý nghĩa:**

- `-Xlint:text-blocks` yêu cầu compiler phát hiện các vấn đề đã mô tả.
- `-Werror` làm việc biên dịch **thất bại khi có warning**, thay vì coi là thành công.
- Nếu source không có warning, lệnh có thể biên dịch bình thường.
- `-Werror` áp dụng với warning của compilation task, không chỉ mọi warning liên quan text block. Nếu công cụ build bật các lint category khác, chúng cũng có thể ảnh hưởng.

Trên CI, lệnh javac có exit code nonzero khi `-Werror` kích hoạt. Không nên chỉ tìm chữ “warning” trong console rồi bỏ qua exit code.

### Phân biệt `-Werror` và lỗi cú pháp

| Tình huống | Không bật `-Xlint:text-blocks` | Bật `-Xlint:text-blocks` | Thêm `-Werror` |
| --- | --- | --- | --- |
| Thiếu line terminator sau `"""` mở | **Error** | **Error** | Vẫn **error** |
| Một escape bất hợp lệ, ví dụ `\q` | **Error** | **Error** | Vẫn **error** |
| TAB/spaces trộn gây inconsistent indentation | Có thể compile không cảnh báo | Compile **warning** | Fail build |
| Trailing spaces literal bị strip | Có thể compile không cảnh báo | Compile **warning** | Fail build |
| Closing delimiter đổi vị trí gây thay đổi chuỗi nhưng không vi phạm lint | Có thể compile sạch | Có thể compile sạch | Có thể compile sạch |
| Test `expected.equals(actual)` thấy lệch | Không thuộc bước compiler | Không thuộc bước compiler | Phải có **test riêng** để fail |

**Không tắt warning chỉ để “xanh CI” khi kết quả chuỗi là phần của giao thức.** Hãy sửa whitespace và bổ sung exact-string test.

## 8. Compiler error khác compiler warning khác runtime mismatch

Có ba lớp lỗi cần tách:

**Lớp A — lỗi cú pháp/lexical (compile error):**

```java
// Cố tình sai, KHÔNG đặt chung file với ví dụ runnable.
String bad1 = """hello""";  // thiếu newline ngay sau opening """

String bad2 = """
    broken \q
    """;                     // escape \q không hợp lệ
```

Với source kiểu này, compiler không tạo class đúng. `-Xlint` không phải công cụ để “bỏ qua” lỗi.

**Lớp B — warning của compiler:**

- Đoạn text block hợp cú pháp nhưng trộn indent TAB/spaces.
- Đoạn text block có trailing blanks literal.
- Compiler vẫn có thể tạo class khi không bật `-Werror`.

**Lớp C — lỗi giá trị runtime:**

- Có/thiếu newline cuối.
- Thêm indentation do dời delimiter.
- JSON string chứa newline thật thay vì hai ký tự `\` và `n`.
- Ký tự `\r`, `\n`, `\t` khác mong đợi.
- Tệp golden test có CRLF trong khi text block chuẩn hóa LF.

Lớp C có thể xảy ra **không có một compiler warning nào**. Muốn phát hiện, phải kiểm tra chuỗi thật trong unit/integration test.

## 9. Line terminators: CRLF/CR và LF được chuẩn hóa

Trong text block Java, line terminators từ source (CRLF, CR hay LF) được chuẩn hóa thành **LF `\n`**. Điều này giúp mã nguồn được biên dịch trên Windows/Linux với giá trị chuỗi dễ dự đoán hơn.

Ví dụ:

```java
String csv = """
    col1,col2
    a,b
    """;
```

Giá trị `csv` là:

```java
"col1,col2\na,b\n"
```

cho dù file source được lưu bằng CRLF (với cùng nội dung text block).

### Khi cần CRLF thật

Nếu giao thức yêu cầu CRLF, đừng chỉ dựa vào editor/source file dùng Windows line endings. Có thể tạo rõ:

```java
String crlf = """
    one
    two
    """.replace("\n", "\r\n");
```

Khi đó `crlf.equals("one\r\ntwo\r\n")` là `true`.

Đây là snippet minh họa. Cần kiểm tra chính xác protocol: không phải định dạng nào cũng cho phép tự chuyển mọi newline thành CRLF. **Đừng thay thế bừa** nếu dữ liệu có các escape hoặc ký tự xuống dòng có ý nghĩa phân biệt.

### Vì sao so sánh bytes cũng quan trọng?

Nếu bạn gửi text block ra file/socket hoặc ký số payload:

```java
byte[] actual = csv.getBytes(StandardCharsets.UTF_8);
```

Cần import `java.nio.charset.StandardCharsets`. Cùng `String` nhưng chọn charset khác có thể cho bytes khác. Ngược lại, hai source file có line endings khác nhau nhưng text block được chuẩn hóa có thể cho cùng bytes sau khi encode UTF-8.

Đối với các protocol nhạy cảm byte-for-byte, hãy kiểm tra cả **chuỗi** và **byte[]** theo serialization đã thỏa thuận.

## 10. Escape sequences: `\s`, `\t`, `\\` và nối dòng

Text blocks **không phải raw string**. Một số escape Java vẫn có hiệu lực:

| Trong source text block | Ý nghĩa ở String thật | Điểm dễ nhầm |
| --- | --- | --- |
| `\n` | Một LF U+000A | Không phải hai ký tự `\` và `n` |
| `\r` | Một CR U+000D | Khác LF |
| `\t` | Một TAB U+0009 | TAB không phải số spaces cố định |
| `\s` | Một ASCII space U+0020 | Rất hữu ích để giữ trailing spaces |
| `\\` | Một dấu backslash thật | Path, JSON, regex phải kiểm tra kỹ |
| `\"` | Một double quote thật | Thường không cần với quote đơn lẻ |
| `\` ngay trước line terminator | **Bỏ** line terminator trong String | Dùng để nối dòng visual thành một dòng dữ liệu |
| `\040` | Một ASCII space qua octal escape | Có thể giữ trailing space do dịch muộn |

### Nối dòng bằng dấu backslash cuối dòng

```java
String joined = """
    long \
    line\
    """;
```

Giá trị thực:

```java
"long line"
```

Dấu `\` ở cuối dòng **loại bỏ newline** tương ứng. Trong ví dụ này có một space sau từ `long` **đứng trước** dấu `\`, nên `long` và `line` vẫn cách nhau một space.

**Nếu bỏ space trước dấu `\`**, kết quả sẽ là `"longline"`. Đây là lỗi dễ mắc khi reformat source.

**Tránh có trailing spaces sau dấu backslash** nối dòng: cần để backslash theo đúng cú pháp ngay trước line terminator, không để editor tự chèn blanks cuối dòng.

### Windows path và regex

Giả sử muốn giá trị thật chứa một đường dẫn Windows:

```java
String path = """
    C:\\temp\\data
    """;
```

Giá trị thật là `"C:\\temp\\data\n"` trong cách biểu diễn Java string literal (hai dấu backslash trong source thể hiện một dấu backslash ở giá trị).

Với regex, nếu cần biểu thức `\s+` (regex whitespace), phần Java source text block **phải chứa `\\s+`** để tạo ra hai ký tự backslash + `s` cho regex engine. Nếu viết `\s+` trong text block, Java sẽ dịch `\s` thành **space**, làm regex đổi nghĩa. Text block không loại bỏ tầng escape Java.

## 11. Text block chứa dấu nháy kép và chuỗi JSON

Ưu điểm của text block là không cần escape **mọi** dấu double quote:

```java
String json = """
    {"name":"Ada","active":true}
    """;
```

Giá trị thật kết thúc bằng newline.

Nhưng nếu nội dung có **ba dấu nháy kép liên tiếp**, chúng có thể kết thúc delimiter hoặc gây lỗi nếu không được escape theo quy tắc. Để chứa một chuỗi ba dấu nháy kép trong giá trị, cần dùng escape để không tạo token đóng text block ngoài ý muốn.

**Quan trọng khi tạo JSON:** text block giúp dễ đọc **template JSON**, không thay thư viện serialize JSON:

- Một giá trị Java `String` cần được escape theo JSON nếu có quote, backslash, control characters.
- Ghép dữ liệu không tin cậy vào text block bằng `formatted(...)` không tự bảo đảm JSON hợp lệ.
- Với dữ liệu động, ưu tiên JSON serializer đáng tin; kiểm thử chuỗi/binary payload nếu có chữ ký hoặc giao thức yêu cầu canonical format.

### Khi text block chứa ký tự `\n` ở phía JSON

Hai biểu thức:

```java
// Một newline THẬT trong giá trị Java String:
String actualLf = """
    A\nB
    """;

// Hai ký tự \ và n trong giá trị Java String:
String escapedForAnotherLayer = """
    A\\nB
    """;
```

Lưu ý chúng **khác nhau**. Đối với JSON, dấu `\n` trong JSON text là một escape mà **JSON parser** sẽ xử lý ở tầng tiếp theo; Java phải tạo đúng hai ký tự backslash + `n` trong JSON source nếu đó là ý định.

Một pipeline có thể qua **hai tầng escaping**: Java source → Java String → JSON parser. Đừng kiểm tra bằng cảm giác khi nhìn một text block.

## 12. Chương trình chạy được: kiểm thử chính xác giá trị các text blocks

Tạo file **`TextBlockValueTests.java`**. Đây là một chương trình Java 17+ tự kiểm tra, không cần JUnit hay thư viện ngoài. Nó so sánh **toàn bộ chuỗi** thay vì chỉ in nội dung rồi nhìn bằng mắt.

### 12.1. Mã nguồn đầy đủ

```java
import java.util.Objects;

public class TextBlockValueTests {
    private static int tests;

    private static String visible(String s) {
        return s.replace(" ", "·")
                .replace("\t", "\\t")
                .replace("\r", "\\r")
                .replace("\n", "\\n");
    }

    private static void expect(
            String name, String expected, String actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    name + " mismatch\nexpected: "
                    + visible(expected) + "\nactual:   "
                    + visible(actual));
        }
        tests++;
        System.out.println("PASS " + name);
    }

    public static void main(String[] args) {
        String finalBreak = """
            red
            blue
            """;
        expect("final-newline",
                "red\nblue\n", finalBreak);

        String noFinalBreak = """
            red
            blue""";
        expect("no-final-newline",
                "red\nblue", noFinalBreak);

        String extraIndent = """
                left
                  right
            """;
        expect("relative-indent",
                "    left\n      right\n", extraIndent);

        String trailingSpaces = """
            red  \s
            green\s
            """;
        expect("trailing-spaces",
                "red   \ngreen \n", trailingSpaces);

        String joined = """
            long \
            line\
            """;
        expect("line-continuation",
                "long line", joined);

        String tab = """
            A\tB
            """;
        expect("tab-escape",
                "A\tB\n", tab);

        String json = """
            {"name":"Ada","active":true}
            """;
        expect("literal-quotes",
                "{\"name\":\"Ada\",\"active\":true}\n", json);

        String path = """
            C:\\temp\\data
            """;
        expect("backslash-escape",
                "C:\\temp\\data\n", path);

        System.out.println("tests.passed=" + tests);
        System.out.println("trailingSpaces.length="
                + trailingSpaces.length());
    }
}
```

### 12.2. Lệnh biên dịch và chạy

```bash
javac -encoding UTF-8 -Xlint:text-blocks -Werror TextBlockValueTests.java
java TextBlockValueTests
```

Đây là file Java hợp lệ trên JDK 17+. Những text blocks trong chương trình dùng indentation thống nhất, không có trailing whitespace literal gây warning, và tự bảo vệ trailing spaces cần thiết bằng `\s`.

**Stdout dự kiến:**

```text
PASS final-newline
PASS no-final-newline
PASS relative-indent
PASS trailing-spaces
PASS line-continuation
PASS tab-escape
PASS literal-quotes
PASS backslash-escape
tests.passed=8
trailingSpaces.length=14
```

### 12.3. Giải thích từng test

- `final-newline`: đóng delimiter ở dòng riêng, giá trị kết thúc bằng `\n`.
- `no-final-newline`: delimiter đóng ở cuối dòng nội dung, giá trị không có newline cuối.
- `relative-indent`: closing delimiter lùi trái so với nội dung nên còn **4 spaces trước “left”**, **6 trước “right”**.
- `trailing-spaces`: `\s` bảo toàn các blanks bắt buộc; giá trị có độ dài `14` ký tự cho hai dòng.
- `line-continuation`: dấu `\` cuối dòng suppress newline, kết quả là `"long line"`.
- `tab-escape`: Java dịch `\t` thành một TAB thật; test so sánh TAB chứ không so sánh spaces.
- `literal-quotes`: dấu `"` đơn lẻ trong text block không cần escape, nhưng **newline cuối vẫn tồn tại**.
- `backslash-escape`: muốn một backslash trong giá trị thì viết `\\` trong Java source.

**Điểm mạnh của test:** nếu IDE auto-format lại closing delimiter và thay đổi lề, `expect(...)` ném `AssertionError` kèm cách biểu diễn whitespace dễ đọc. Không tự gọi `strip()` hoặc `trim()` trước khi so sánh, vì làm vậy có thể che mất lỗi mà bài muốn phát hiện.

### 12.4. Tại sao dùng `String.equals` thay vì `println`?

`System.out.println(s)` **tự thêm newline**, nên màn hình có thể hiển thị gần như giống nhau cho hai String khác nhau ở newline cuối. Terminal cũng không hiển thị rõ trailing spaces hoặc TAB.

Test `expected.equals(actual)` bắt được khác biệt. Hàm `visible(...)` được dùng **chỉ khi có lỗi** để hiện `·` (space), `\\t` (TAB) và `\\n` (LF). Các ký hiệu đó chỉ để debug; **không thay đổi** chuỗi được kiểm thử.

## 13. Chương trình chạy được: tạo warning bằng JavaCompiler mà không phụ thuộc whitespace vô hình

Đây là cách kiểm chứng đặc biệt hữu ích cho chủ đề **compiler warning**. Thay vì yêu cầu bạn copy một file chứa spaces cuối dòng mà editor có thể xóa, chương trình tự tạo **mã nguồn Java trong bộ nhớ**, đưa một TAB và trailing spaces vào đúng vị trí, rồi gọi **Java Compiler API `javax.tools`**.

Chương trình không ghi file `.java` hoặc `.class` ra dự án; output class của compiler được chuyển vào `ByteArrayOutputStream`. Nó kiểm tra warning theo mã chẩn đoán của **javac/OpenJDK**, rồi chạy lại với `-Werror`.

### 13.1. Tệp `TextBlockCompilerLintDemo.java`

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class TextBlockCompilerLintDemo {
    private static JavaFileObject sourceFile(String content) {
        return new SimpleJavaFileObject(
                URI.create("string:///WarningFixture.java"),
                JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(
                    boolean ignoreEncodingErrors) {
                return content;
            }
        };
    }

    private static void compile(boolean warningsAsErrors)
            throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "Use a full JDK, not a runtime without javac");
        }

        // Cố tình tạo nội dung có:
        // 1) 2 spaces thật ở cuối dòng alpha.
        // 2) Một space + một TAB trước beta.
        String badSource =
                "class WarningFixture {\n"
                + " String value = \"\"\"\n"
                + "        alpha" + "  " + "\n"
                + " " + "\t" + "beta\n"
                + "        gamma\n"
                + "        \"\"\";\n"
                + "}\n";

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager standard =
                    compiler.getStandardFileManager(
                            diagnostics, Locale.ROOT, null);
             JavaFileManager manager =
                    new ForwardingJavaFileManager<
                            StandardJavaFileManager>(standard) {
                        @Override
                        public JavaFileObject getJavaFileForOutput(
                                Location location, String name,
                                JavaFileObject.Kind kind,
                                FileObject sibling) {
                            return new SimpleJavaFileObject(
                                    URI.create("mem:///" + name
                                            + kind.extension), kind) {
                                @Override
                                public OutputStream openOutputStream() {
                                    return new ByteArrayOutputStream();
                                }
                            };
                        }
                    }) {
            List<String> options = warningsAsErrors
                    ? List.of("-Xlint:text-blocks", "-Werror")
                    : List.of("-Xlint:text-blocks");

            boolean success = compiler.getTask(
                    null, manager, diagnostics,
                    options, null, List.of(sourceFile(badSource)))
                    .call();

            boolean inconsistentIndent = diagnostics.getDiagnostics()
                    .stream()
                    .map(Diagnostic::getCode)
                    .anyMatch(code -> code.contains(
                            "inconsistent.white.space"));

            boolean trailingWhitespace = diagnostics.getDiagnostics()
                    .stream()
                    .map(Diagnostic::getCode)
                    .anyMatch(code -> code.contains(
                            "trailing.white.space"));

            String label = warningsAsErrors ? "werror" : "lint";
            System.out.println(label + ".success=" + success);
            System.out.println(label + ".inconsistentIndent="
                    + inconsistentIndent);
            System.out.println(label + ".trailingWhitespace="
                    + trailingWhitespace);
        }
    }

    public static void main(String[] args) throws IOException {
        compile(false);
        compile(true);
    }
}
```

### 13.2. Biên dịch và chạy

```bash
javac -encoding UTF-8 TextBlockCompilerLintDemo.java
java TextBlockCompilerLintDemo
```

**Stdout với OpenJDK/HotSpot `javac` hiện hành:**

```text
lint.success=true
lint.inconsistentIndent=true
lint.trailingWhitespace=true
werror.success=false
werror.inconsistentIndent=true
werror.trailingWhitespace=true
```

Đã kiểm chứng quy trình tương đương trên **OpenJDK 24**: không có `-Werror`, compiler hoàn tất thành công nhưng nhận đủ hai warning; với `-Werror`, compilation task trả `false`.

**Lưu ý phạm vi:**

- Class cần một **full JDK** có `ToolProvider.getSystemJavaCompiler()`. Một runtime không đóng gói compiler có thể trả `null`.
- Các `Diagnostic.getCode()` dùng để phân loại ở đây thuộc **cách đặt tên của javac/OpenJDK**; không phải API đảm bảo mọi Java compiler vendor giữ nguyên diagnostic key. Trên compiler khác, có thể vẫn cảnh báo nhưng tên code khác.
- Ví dụ phát hiện warning mà **không ghi các file generated vào project**, nhưng nó không thay thế việc CI compile **mã nguồn dự án thực**.
- Một compilation task với `-Werror` có thể chứa chẩn đoán error bổ sung “warnings and -Werror” bên cạnh hai warnings; chương trình tập trung vào kết quả thành công/thất bại và hai nhóm lint.

### 13.3. Tại sao code tạo source bằng chuỗi ghép?

`"        alpha" + "  " + "\n"` tạo chính xác **hai spaces thật trước line feed** mà không đặt trailing whitespace trong file chứa demo. `" " + "\t" + "beta\n"` tạo hỗn hợp **space + TAB** trước nội dung. Nhờ đó công cụ format của IDE không vô tình xóa lỗi khỏi fixture.

Đây là cách tạo **negative test reproducible** cho những cảnh báo rất khó mô tả bằng Markdown/rendered code.

## 14. Chẩn đoán giá trị String bằng hiển thị “ký tự vô hình”

Khi một exact-string test fail, cần kiểm tra:

- `length()`: số **UTF-16 code units**, không phải bytes UTF-8 hay luôn bằng số Unicode code points.
- `isEmpty()`/`isBlank()`: có thể hữu ích để khảo sát nhưng **không** thay so sánh giá trị.
- `charAt(i)` hoặc `codePointAt(i)`: xác định ký tự tại vị trí cụ thể.
- `equals(...)`: so sánh **toàn bộ nội dung** từng ký tự.
- `Arrays.equals(expected.getBytes(UTF_8), actual.getBytes(UTF_8))`: kiểm tra bytes UTF-8 khi hợp đồng giao thức là byte-for-byte.
- `startsWith(...)`, `endsWith(...)`: định vị vấn đề newline đầu/cuối.
- `String.lines()`: hỗ trợ quan sát từng dòng nhưng **không thay** test newline cuối vì cách tách dòng có quy tắc riêng.

### Biểu diễn dấu space/TAB/LF rõ ràng

Snippet:

```java
static String showInvisible(String value) {
    return value.replace(" ", "·")
            .replace("\t", "\\t")
            .replace("\r", "\\r")
            .replace("\n", "\\n");
}
```

Đây là một phương thức có thể đặt trong class, không phải chương trình độc lập. Nếu input là `"A \tB\n"`, kết quả trả về gồm ký hiệu `·` sau `A`, hai ký tự `\` + `t` thay TAB, và hai ký tự `\` + `n` thay LF.

**Không dùng `trim()`/`strip()` trước khi xác định lỗi.** Những hàm đó có mục đích riêng và có thể **che mất chênh lệch** ở đầu/cuối, khiến test “xanh” nhưng bytes gửi qua mạng vẫn sai.

### Tìm vị trí khác biệt đầu tiên

Một helper chẩn đoán:

```java
static int firstDifference(String a, String b) {
    int n = Math.min(a.length(), b.length());
    for (int i = 0; i < n; i++) {
        if (a.charAt(i) != b.charAt(i)) {
            return i;
        }
    }
    return a.length() == b.length() ? -1 : n;
}
```

Snippet này so theo **UTF-16 code units**. Trả `-1` nếu chuỗi hoàn toàn giống; nếu khác độ dài nhưng prefix giống, trả độ dài prefix chung.

Với dữ liệu có surrogate pairs, giá trị trả về có thể nằm trong vùng UTF-16 của một ký tự Unicode; nếu cần hiển thị theo code points, dùng `codePoints()` hoặc `offsetByCodePoints(...)` để dịch vị trí có nghĩa hơn.

## 15. Biên dịch sạch nhưng test vẫn fail: checklist theo thứ tự

Khi compiler không báo warning mà unit test so sánh chuỗi thất bại, làm tuần tự:

1. **Kiểm tra opening delimiter:** nội dung có bắt đầu đúng dòng không? Có vô tình tạo dòng trống đầu?
2. **Kiểm tra closing delimiter:** cùng dòng với dữ liệu hay ở dòng riêng? Có newline cuối không?
3. **Kiểm tra lề closing delimiter:** có làm common incidental indentation thay đổi không?
4. **Kiểm tra số dấu space ở đầu mỗi dòng:** đây là dữ liệu hay chỉ là indent source?
5. **Kiểm tra TAB:** editor hiển thị TAB theo mấy cột, nhưng compiler tính theo một ký tự.
6. **Kiểm tra trailing whitespace:** những spaces cuối dòng có bị strip không? Có nên dùng `\s`?
7. **Kiểm tra ký tự `\`:** đó là Java escape hay muốn gửi hai ký tự literal cho JSON/regex?
8. **Kiểm tra line continuation:** `\` ở cuối dòng có suppress newline không?
9. **Kiểm tra source encoding/line endings:** text block chuẩn hóa source CRLF thành LF, còn charset output phải chọn rõ.
10. **Kiểm tra những thao tác sau text block:** `formatted(...)`, `indent(...)`, `stripIndent()`, `replace(...)` hay serializer có đang sửa giá trị?
11. **Kiểm tra phía nhận:** có protocol canonicalization, parser JSON/XML, SQL engine hoặc line-ending conversion riêng không?
12. **Viết expected String literal rõ ràng**, chạy `equals`, in chỉ số khác biệt trước khi thay code.

**Đừng vội bật `-Xlint:all` rồi kỳ vọng nó tìm được mọi vấn đề nội dung.** Lint có phạm vi cảnh báo compiler; đúng sai nghiệp vụ là trách nhiệm của tests và contract.

## 16. `String.stripIndent()`, `indent()` và `translateEscapes()`: dùng đúng chỗ

Các phương thức `String` hiện hành có thể hữu ích khi làm việc với nội dung nhiều dòng:

| API | Ý nghĩa | Chú ý khi chẩn đoán |
| --- | --- | --- |
| `String.stripIndent()` | Loại common incidental indentation của một `String` nhiều dòng theo quy tắc của API | Có thể thay whitespace, đừng gọi vô tội vạ để “sửa” expected |
| `String.indent(int)` | Thêm/bớt indentation ở từng dòng theo hợp đồng API | Có thể làm thay đổi cấu trúc newline; test exact result |
| `String.translateEscapes()` | Diễn giải escapes Java hợp lệ có trong **chuỗi runtime** | Text block đã được compiler dịch escapes rồi; gọi lần nữa có thể làm dữ liệu khác |
| `String.formatted(...)` | Format text block như một template | Không tự escape SQL/JSON hay đảm bảo an toàn |

Ví dụ:

```java
String greeting = """
    Hello, %s!
    """.formatted("Ada");
```

Giá trị bằng `"Hello, Ada!\n"`.

**Không thêm `translateEscapes()` sau text block** với mục đích “để text block hiểu `\n`”; compiler đã xử lý `\n` rồi. Trường hợp dùng `translateEscapes()` là khi chương trình **nhận một chuỗi chứa các dấu backslash và ký tự escape ở runtime** và có nhu cầu dịch chúng một cách có chủ đích.

### `String.stripIndent()` có phải cách thay compiler?

Không. Text block đã thực hiện incidental whitespace stripping ở thời điểm biên dịch. Gọi `stripIndent()` tiếp có thể làm giá trị đổi thêm; không dùng như một thao tác “phải có” sau mọi text block. Nếu thứ bạn cần là một String runtime **đọc từ file/nguồn khác**, `stripIndent()` có thể phù hợp nhưng cần test đầu vào/đầu ra.

### Không dùng `formatted(...)` để thay prepared statement

Với SQL:

```java
String query = """
    SELECT id, name
    FROM customer
    WHERE email = ?
    """;
```

Dấu `?` dành cho **prepared statement parameter**, không được thay bằng `formatted(userInput)` để nối trực tiếp dữ liệu không tin cậy vào SQL. Text block chỉ cung cấp cú pháp dễ đọc, **không** giải quyết SQL injection.

## 17. Thử đúng cả text và bytes của payload

Một JSON, XML, HTTP body, Markdown fixture hoặc thông điệp dùng làm đầu vào ký số cần chính xác ở mức bytes. Sự khác biệt giữa LF và CRLF hay space cuối có thể ảnh hưởng digest/chữ ký.

Snippet Java 17+:

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

String content = """
    action=approve
    version=1
    """;

byte[] bytes = content.getBytes(StandardCharsets.UTF_8);
byte[] expectedBytes =
        "action=approve\nversion=1\n"
                .getBytes(StandardCharsets.UTF_8);

if (!Arrays.equals(expectedBytes, bytes)) {
    throw new AssertionError("Payload bytes changed");
}
```

Đây là **snippet**, cần đặt trong method, không phải một file Java hoàn chỉnh với import ở giữa method. Chuyển text block sang UTF-8 rõ ràng; không lấy default charset một cách mơ hồ trong giao thức. Nếu contract yêu cầu CRLF, hãy tạo CRLF theo quy định rõ trước khi encode.

### Snapshot/golden tests

Với các fixtures đa nền tảng:

- Ghi **rõ** yêu cầu có hay không có trailing LF.
- Quy định LF hay CRLF ở file output.
- Kiểm thử canonicalization nếu có.
- Không dùng `trim()` để so sánh cho “đỡ lỗi” nếu ký tự trắng có ý nghĩa.
- Khi cần dễ review, hiển thị khoảng trắng bằng ký hiệu trong thông báo test, nhưng **giữ chuỗi thật** để so sánh.
- Có thể kèm kiểm tra SHA-256 của bytes trong hệ thống phù hợp, nhưng không dùng hash thay cho test nội dung khi cần biết nguyên nhân fail.

**Không hard-code một hash** nếu pipeline có thể thay đổi encoding hoặc newline policy; hash chỉ có ý nghĩa khi contract bytes đã được định nghĩa.

## 18. Xây pipeline CI cho text blocks

Một quy trình kiểm chứng thực tế, không cần thư viện ngoài:

```text
1. Compile với JDK target và encoding rõ ràng.
2. Bật -Xlint:text-blocks.
3. Dùng -Werror nếu dự án đã thống nhất policy warnings.
4. Chạy unit tests so sánh String chính xác.
5. Chạy integration tests cho payload/serialization quan trọng.
6. Chạy trên các môi trường được hỗ trợ.
7. Lưu diagnostic/log khi lỗi, không sửa tự động bằng trim/strip.
```

Ví dụ lệnh chạy các demo trong thư mục bạn **chủ động tạo các file nguồn**:

```bash
javac -encoding UTF-8 \
    -Xlint:text-blocks -Werror \
    TextBlockValueTests.java TextBlockCompilerLintDemo.java

java TextBlockValueTests
java TextBlockCompilerLintDemo
```

**Vì `TextBlockCompilerLintDemo` cố ý tạo source xấu bằng JavaCompiler trong bộ nhớ**, câu lệnh compile class demo ở bước đầu vẫn sạch; chỉ khi **chạy demo** mới xuất hiện các warnings/`-Werror` cho source fixture mà nó tạo.

Nếu dùng Gradle/Maven, cấu hình Java compiler args tương ứng cho module của dự án và runner tests phù hợp. Không tự coi những flags được truyền qua `java` (runtime) là compiler flags: `-Xlint:text-blocks` và `-Werror` phải tới **`javac`**, không phải đối số VM ở runtime.

### Có nên thêm `--release 17`?

Nếu công cụ build là JDK mới hơn và ứng dụng phải chạy trên Java 17, có thể dùng:

```bash
javac --release 17 -encoding UTF-8 \
    -Xlint:text-blocks -Werror \
    TextBlockValueTests.java
```

`--release 17` giúp kiểm tra ngôn ngữ/API tương thích mục tiêu Java 17. Nếu đang dùng `javac` JDK 17, `--release 17` cũng hợp lệ. Không sử dụng `--release 15` chỉ vì tính năng được giới thiệu ở Java 15 khi ứng dụng thực tế cần toàn bộ API của Java 17.

## 19. Bảng chẩn đoán nhanh: lỗi → bằng chứng → cách sửa

| Triệu chứng | Bằng chứng nên kiểm tra | Cách xử lý |
| --- | --- | --- |
| `illegal text block open delimiter sequence` | Opening `"""` không có LF sau | Chuyển nội dung xuống dòng tiếp theo |
| `unclosed text block` hoặc syntax error | Thiếu hoặc lệch closing `"""` | Đóng delimiter đúng cú pháp; escape runs of quotes nếu cần |
| `illegal escape character` | Java source chứa `\q` hoặc escape không hợp lệ | Escape backslash đúng hoặc sửa chuỗi |
| `inconsistent white space indentation` | `-Xlint:text-blocks` warning | Dùng chỉ spaces hoặc chỉ TAB, rà lề và test output |
| `trailing white space will be removed` | `-Xlint:text-blocks` warning | Loại blanks vô ý hoặc dùng `\s`/`\040` nếu bắt buộc |
| Không có warning nhưng output bị dư indentation | Closing delimiter lùi trái | Căn closing delimiter đúng; test exact String |
| Không có warning nhưng output thiếu spaces đầu | Compiler strip common incidental indent | Đặt lề có chủ đích hoặc dùng `indent(...)` khi phù hợp |
| Test lệch đúng 1 ký tự cuối | Có/không có trailing LF | Xem vị trí closing delimiter |
| Windows/Linux cho kết quả khác với file golden | Golden file có CRLF, text block ra LF | Quy định newline policy và normalize có chủ đích |
| JSON parse lỗi vì newline | Java source tạo LF thật trong JSON string | Tách tầng escape; dùng serializer |
| Regex không nhận whitespace như mong đợi | `\s` bị Java dịch thành ASCII space | Dùng `\\s` cho regex engine |
| Đường dẫn trong text block sai | Backslash được dịch thành escapes | Viết `\\` để giữ một `\` |
| Text block nhìn đúng, chữ ký/hash sai | Charset/newline/space cuối lệch bytes | Kiểm tra UTF-8 bytes trước khi ký |
| Test xanh vì dùng `trim()` | Đã che mất whitespace mismatch | So sánh `equals`/bytes nguyên bản |
| `-Werror` làm CI fail | Một warning text block hoặc warning khác được phát | Đọc diagnostics, sửa nguyên nhân thay vì tắt hết |
| Một đoạn code in đúng visually nhưng `equals` false | Terminal không hiển thị TAB/trailing blanks/LF rõ | Hiển thị invisible chars, tìm first difference |
| Lỗi chỉ xảy ra sau auto-format | Formatter sửa indentation/closing delimiter | Unit test giá trị, xem diff theo whitespace |
| `TextBlockCompilerLintDemo` không có compiler | Runtime thiếu Java compiler module | Dùng full JDK 17+, không chỉ runtime |
| Copy code có dấu `·` vào Java | `·` là biểu tượng minh họa spaces, không phải ký tự dữ liệu | Dùng source runnable hoặc generate whitespace rõ |
| Template SQL có input không tin cậy | Text block không làm escape SQL | Dùng `PreparedStatement` và bound parameters |

**Lưu ý:** thông báo `javac` cụ thể và tính năng warning có thể thay đổi theo compiler implementation. Hãy tin **kết quả test** cho dữ liệu nghiệp vụ, và dùng warnings để tìm nhanh những sai sót thuộc phạm vi compiler phân tích.

## 20. Câu hỏi tự kiểm tra có đáp án

**1.** Text block có thể viết `String s = """hello""";` không?

**Đáp án:** Không. Opening delimiter phải theo sau bởi line terminator, nên code đó là syntax error.

**2.** Hai cách đóng delimiter `"""` ở dòng riêng và ngay cuối dòng nội dung có cho cùng String không?

**Đáp án:** Thường **không** nếu dòng nội dung cuối lẽ ra có LF. Closing ở dòng riêng thêm LF cuối; closing ngay cuối nội dung có thể không thêm LF đó.

**3.** `-Xlint:text-blocks` phát hiện những vấn đề chính nào?

**Đáp án:** Inconsistent white space indentation (nhất là trộn TAB/spaces gây lệch) và trailing white space sẽ bị remove.

**4.** Bật `-Xlint:text-blocks` nhưng thiếu line terminator sau `"""` thì có chỉ warning không?

**Đáp án:** Không. Đó là **compile error**, dù có bật lint hay không.

**5.** Tại sao compiler có thể strip khoảng trắng đầu các dòng?

**Đáp án:** Java tính incidental indentation để dễ căn text block trong source mà không đưa lề source chung vào dữ liệu.

**6.** Đặt closing delimiter lùi trái có thể làm String khác đi mà không có warning?

**Đáp án:** Có. Cách căn lề hợp lệ vẫn có thể làm số spaces đầu mỗi dòng tăng; cần exact-string test.

**7.** TAB trong common indentation được tính bằng mấy spaces?

**Đáp án:** Compiler xem TAB là **một ký tự whitespace** trong thuật toán, không quy đổi theo 4/8 cột editor.

**8.** Vì sao `\s` có thể giữ trailing space?

**Đáp án:** Escape được dịch thành space **sau** giai đoạn strip trailing whitespace, và có thể bảo vệ spaces literal đứng trước nó.

**9.** `\u0020` có tương đương `\s` để bảo vệ trailing space không?

**Đáp án:** Không. Unicode escape được dịch sớm, ký tự kết quả có thể bị strip.

**10.** Chuỗi source dùng CRLF có làm text block runtime chứa CRLF mặc định?

**Đáp án:** Không. Line terminators trong nội dung text block được chuẩn hóa thành **LF**, trừ khi lập trình viên yêu cầu CRLF có chủ đích.

**11.** `-Werror` có biến warning thành thất bại biên dịch không?

**Đáp án:** Có. Compilation task có warnings sẽ thất bại theo policy `-Werror`.

**12.** Có thể chỉ bật `-Werror` mà chắc chắn mọi lỗi whitespace sẽ được phát hiện?

**Đáp án:** Không. Cần bật lint tương ứng, và nhiều khác biệt giá trị không thuộc warning; phải dùng tests.

**13.** Tại sao `println` không đủ kiểm tra newline cuối?

**Đáp án:** `println` tự thêm newline khi in, khiến các giá trị khác nhau nhìn giống nhau; terminal cũng không hiển thị spaces cuối.

**14.** `String.strip()` trước khi so sánh có phải cách sửa lỗi test snapshot?

**Đáp án:** Không mặc định. Nó có thể che sai khác bytes mà giao thức cần giữ; test exact value trước.

**15.** Với regex muốn truyền literal `\s+` cho regex engine, phải viết gì trong Java text block?

**Đáp án:** `\\s+` ở source Java để giá trị String mang dấu backslash + `s+`; nếu chỉ `\s+`, Java dịch `\s` thành space.

**16.** Có nên gọi `translateEscapes()` sau mọi text block?

**Đáp án:** Không. Compiler đã dịch escapes khi tạo String; gọi lại có thể làm dữ liệu thay đổi lần thứ hai.

**17.** `TextBlockCompilerLintDemo` dùng `ToolProvider.getSystemJavaCompiler()` để làm gì?

**Đáp án:** Tạo và compile một đoạn source có TAB/trailing spaces trong bộ nhớ, thu warnings, thử `-Werror` mà không dựa vào ký tự vô hình trong file source.

**18.** Vì sao không dùng `-Xlint:text-blocks` như phương pháp kiểm tra toàn bộ JSON payload?

**Đáp án:** Lint chỉ kiểm tra một số vấn đề whitespace trong cú pháp text block; cấu trúc JSON, encoding và giao thức cần parser/tests riêng.

**19.** Java text block với closing delimiter trên dòng riêng có tự động bắt đầu bằng newline không?

**Đáp án:** Không. Opening delimiter yêu cầu LF nhưng LF đó không được tính là ký tự đầu chuỗi; muốn bắt đầu bằng LF cần một dòng trống nội dung.

**20.** Khi Java 17 và Java 25 cùng biên dịch một text block chuẩn, có cần preview flag để hỗ trợ không?

**Đáp án:** Không. Text block là tính năng chính thức từ Java 15 và vẫn được hỗ trợ.

### Checklist trước khi merge

- [ ] Text block mở bằng `"""` có line terminator bắt buộc.
- [ ] Vị trí closing delimiter được chọn có chủ đích để kiểm soát LF cuối.
- [ ] Lề source/relative indentation đúng với dữ liệu mong đợi.
- [ ] Indentation không trộn TAB/spaces gây warning.
- [ ] Trailing spaces vô ý đã bỏ; spaces cần thiết dùng `\s`/escape đúng.
- [ ] Không dùng `\u0020` để thay `\s` bảo vệ cuối dòng.
- [ ] Kiểm tra `\n`, `\t`, `\\`, nối dòng và các tầng escape.
- [ ] Biên dịch với `javac -Xlint:text-blocks`; CI dùng `-Werror` theo chính sách.
- [ ] Unit test so sánh **String nguyên bản**, không làm sạch bằng `trim()/strip()`.
- [ ] Test có kiểm tra newline cuối, leading/trailing spaces và ký tự TAB.
- [ ] Payload cần bytes cố định được test thêm với UTF-8.
- [ ] Nếu source được auto-format, chạy lại exact-string tests.
- [ ] Không sử dụng `--enable-preview` cho text block trên Java 17+.
- [ ] Ví dụ `TextBlockValueTests` chạy đủ 8 kiểm tra và báo `tests.passed=8`.
- [ ] Ví dụ `TextBlockCompilerLintDemo` phát hiện hai nhóm warning và fail với `-Werror`.
- [ ] Không nhầm compiler warning với compile error hoặc lỗi nghiệp vụ runtime.

## 21. Tài liệu chính thức còn được hỗ trợ

1. [Oracle Java SE 25 — Text Blocks](https://docs.oracle.com/en/java/javase/25/language/text-blocks.html): cú pháp, closing delimiter, incidental indentation, trailing whitespace, `-Xlint:text-blocks`, escape translation và ví dụ trực quan.
2. [Oracle Java SE 25 — Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/25/text-blocks/index.html): hướng dẫn chi tiết về compiler warning, tabs/spaces, line normalization, `\s` và `\` + line terminator.
3. [Java Language Specification, Java SE 25 — `3.10.6 Text Blocks](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6): quy tắc ngôn ngữ chính thức về định dạng literal và xử lý.
4. [OpenJDK JEP 378 — Text Blocks](https://openjdk.org/jeps/378): tính năng được chuẩn hóa trong **Java 15**; hành vi loại indentation/whitespace và escapes vẫn là nền tảng.
5. [Oracle Java SE 25 — javac Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `-Xlint:text-blocks`, `-Xlint:all`, `-Werror`, `--release` và `-encoding`.
6. [Oracle Java SE 25 — String API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): `equals`, `indent`, `stripIndent`, `translateEscapes`, `formatted`, `getBytes`.
7. [Java SE 25 — Java Compiler API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/JavaCompiler.html): compiler programmatic, `DiagnosticCollector` và `JavaFileManager`.

**Tổng kết:** `javac -Xlint:text-blocks` phát hiện hai nhóm vấn đề thường bị mắt bỏ sót — **indentation whitespace không nhất quán** và **trailing whitespace bị strip**. `-Werror` giúp kiểm tra warning ở CI, nhưng **compiler sạch chưa chứng minh `String` đúng**: phải test chính xác **newline cuối, số spaces, TAB, escape và bytes UTF-8**. Khi một text block trông đúng mà dữ liệu sai, hãy nhớ thứ tự **normalize line endings → strip incidental whitespace → translate escapes**, rồi dùng `equals` và hiển thị ký tự vô hình để tìm lỗi.