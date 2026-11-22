# Java 15 — Dòng rỗng, lề chung và newline trong `String.stripIndent()`

## 1. Mục tiêu của bài

`String.stripIndent()` là phương thức của `java.lang.String` có từ **Java 15** và vẫn được hỗ trợ trong Java hiện đại. Nó xử lý **một chuỗi đã tồn tại trong runtime**: loại khoảng trắng thụt đầu dòng chung (*incidental indentation*), xóa khoảng trắng cuối mỗi dòng có nội dung và chuẩn hóa ký tự xuống dòng. Cơ chế này liên quan trực tiếp đến cách trình biên dịch Java xử lý **text blocks** (`"""..."""`), nhưng có một khác biệt quan trọng giữa **chuỗi runtime đã kết thúc bằng newline** và **phần văn bản của text block trước khi đóng dấu nháy**.

Bài tập trung vào ba câu hỏi thực tế:

1. Dòng rỗng nằm giữa hoặc ở cuối chuỗi có ảnh hưởng như thế nào tới lề chung?
2. Vì sao `"    A\n    B"` và `"    A\n    B\n"` lại cho kết quả khác nhau khi gọi `stripIndent()`?
3. Khi nào phương thức giữ nguyên ký tự xuống dòng, chuẩn hóa CR/CRLF thành LF, hoặc làm mất khoảng trắng mà dữ liệu thực sự cần?

**Đích học tập:** đọc và dự đoán chính xác `String` kết quả; sử dụng Java 17+ để kiểm chứng bằng code; tránh dùng `stripIndent()` khi định dạng byte/khoảng trắng phải được giữ tuyệt đối. Không cần bật preview để sử dụng API này.

## 2. Thuật toán chính xác của `stripIndent()`

Theo hợp đồng API của `String.stripIndent()`, có thể hiểu quá trình xử lý theo bốn bước:

1. **Tách chuỗi thành các dòng logic.** Các dấu ngắt dòng được nhận biết là `\n` (LF), `\r` (CR) và `\r\n` (CRLF). Bản thân dấu ngắt dòng không thuộc phần nội dung dòng. Nếu chuỗi kết thúc bằng một dấu ngắt dòng thì **dòng cuối cùng trong phép tính của `stripIndent()` là dòng rỗng** sau dấu ngắt đó; nếu không có dấu ngắt, toàn bộ chuỗi là một dòng. Với chuỗi rỗng, kết quả là chuỗi rỗng.
2. **Tìm lề chung `min`.** Đếm số ký tự khoảng trắng đầu dòng của **từng dòng không rỗng theo nghĩa `isBlank() == false`**; đồng thời **luôn xét cả dòng cuối, kể cả nếu nó chỉ chứa khoảng trắng hoặc rỗng**. `min` là giá trị đếm nhỏ nhất. Các dòng rỗng nằm giữa không tham gia tìm `min`.
3. **Chỉnh nội dung dòng.** Với mỗi dòng không blank, bỏ `min` ký tự khoảng trắng ở đầu và **toàn bộ khoảng trắng cuối dòng**. Các dòng blank được thay bằng chuỗi rỗng `""`; chúng **không bị loại khỏi danh sách dòng**, nên vẫn giữ vị trí dòng rỗng.
4. **Nối lại bằng LF.** Dùng `\n` để ngăn cách các dòng. Số lượng **dấu ngắt dòng logic** được giữ nguyên; nếu đầu vào kết thúc bằng một dấu ngắt dòng, kết quả vẫn kết thúc bằng `\n`. CR và CRLF được chuẩn hóa thành LF.

Khoảng trắng ở đây theo quy tắc `Character.isWhitespace`. Mỗi ký tự khoảng trắng đầu dòng được tính là **một đơn vị**; **một tab (`\t`) không được mở rộng thành 4 hay 8 space** như cách editor thường hiển thị. Vì thế không nên dự đoán kết quả cắt lề chỉ bằng việc nhìn các cột thẳng hàng trong IDE.

### 2.1. Lề chung chỉ tính các dòng có nội dung và dòng cuối

Ví dụ đầu vào được tạo bằng Java string literal:

~~~java
String source = "    red\n   \n      green\n    blue";
String result = source.stripIndent();
~~~

Đây là **đoạn mã đặt bên trong một phương thức**, không phải chương trình chạy độc lập. Cách tính:

| Dòng | Nội dung ban đầu | Có đóng góp vào `min`? | Lý do |
| --- | --- | --- | --- |
| 1 | 4 space + `red` | Có: 4 | Dòng không blank |
| 2 | 3 space | Không | Dòng blank nằm giữa |
| 3 | 6 space + `green` | Có: 6 | Dòng không blank |
| 4 | 4 space + `blue` | Có: 4 | Dòng cuối, đồng thời không blank |

Vậy `min = 4`. Kết quả chính xác:

~~~text
red

  green
blue
~~~

Dòng trống ở giữa **vẫn còn** sau `stripIndent()`; 3 space của dòng ấy biến mất vì mọi dòng blank được thay bằng `""`. Dòng `green` còn 2 space có chủ đích để thể hiện mức thụt tương đối. `stripIndent()` không phải `filter` loại bỏ các dòng trắng.

### 2.2. Dòng cuối blank là ngoại lệ dễ bỏ sót

Xét ba chuỗi có các dòng nội dung giống nhau nhưng kết thúc khác nhau:

| `String` đầu vào (ký pháp Java) | Lề chung tính được | Kết quả dễ nhìn |
| --- | ---: | --- |
| `"    Alpha\n      Beta"` | 4 | `Alpha\n  Beta` |
| `"    Alpha\n      Beta\n"` | **0** | `    Alpha\n      Beta\n` |
| `"    Alpha\n      Beta\n  "` | **2** | `  Alpha\n    Beta\n` |

Ở trường hợp thứ hai, dấu `\n` cuối tạo ra **một dòng cuối rỗng có lề 0**. Do dòng cuối luôn được tham gia xác định `min`, lề chung bằng 0; hai dòng nội dung **không bị xóa indent đầu dòng**. Các khoảng trắng **cuối** của từng dòng vẫn có thể bị xóa.

Ở trường hợp thứ ba, chuỗi **không kết thúc bằng newline** mà kết thúc bằng hai space. Dòng cuối blank này có 2 ký tự khoảng trắng, nên kéo `min` xuống 2. Sau khi dòng cuối bị biến thành `""`, ký tự `\n` ngăn cách phía trước nó vẫn tồn tại. Do đó **kết quả lại kết thúc bằng `\n`**, dù chuỗi đầu vào kết thúc bằng space chứ không trực tiếp bằng newline.

**Ghi nhớ:** “có dấu xuống dòng ở cuối” khác với “có một dòng cuối chứa dấu cách”; cả hai đều tác động tới `min`. Khi chẩn đoán lỗi indent, kiểm tra chính xác ký tự cuối của chuỗi.

## 3. Chương trình thực hành: quan sát toàn bộ trường hợp

Lưu mã sau vào tệp **`StripIndentDemo.java`**. Đây là chương trình độc lập, dùng API chuẩn và chạy từ **Java 17 trở lên**. Phương thức `show(...)` thay space bằng dấu chấm, tab bằng `<TAB>` và ký tự xuống dòng bằng `<LF>`/`<CR>`, để output không che giấu khác biệt khoảng trắng.

~~~java
public class StripIndentDemo {
    static void show(String label, String value) {
        String visible = value
                .replace(" ", ".")
                .replace("\t", "<TAB>")
                .replace("\r", "<CR>")
                .replace("\n", "<LF>");
        System.out.println(label + "=[" + visible + "]");
    }

    public static void main(String[] args) {
        String internal = "    Alpha  \r\n      Beta\t\r\n\r\n    Gamma ";
        show("internal", internal.stripIndent());

        String withLF = "    Alpha\n      Beta\n";
        show("withLF", withLF.stripIndent());

        String withoutLF = "    Alpha\n      Beta";
        show("withoutLF", withoutLF.stripIndent());

        String lastBlank = "    Alpha\n      Beta\n  ";
        show("lastBlank", lastBlank.stripIndent());

        String allBlank = " \t\r\n  \r\n";
        show("allBlank", allBlank.stripIndent());

        String mixed = "    A\n\tB\n    C";
        show("mixed", mixed.stripIndent());

        show("indentMinus4", withLF.indent(-4));

        String textBlock = """
            Alpha
              Beta
            """;
        show("textBlock", textBlock);
        show("textBlockStripped", textBlock.stripIndent());

        String withSpace = """
            tail\s
            """;
        show("textBlockSpace", withSpace);
        show("textBlockSpaceStripped", withSpace.stripIndent());

        System.out.println("withLF.length=" + withLF.stripIndent().length());
        System.out.println("withoutLF.length=" + withoutLF.stripIndent().length());
    }
}
~~~

Biên dịch và chạy trong thư mục có tệp nguồn:

~~~bash
javac --release 17 -Xlint:all StripIndentDemo.java
java StripIndentDemo
~~~

**Kết quả stdout đã được kiểm tra bằng JDK:**

~~~text
internal=[Alpha<LF>..Beta<LF><LF>Gamma]
withLF=[....Alpha<LF>......Beta<LF>]
withoutLF=[Alpha<LF>..Beta]
lastBlank=[..Alpha<LF>....Beta<LF>]
allBlank=[<LF><LF>]
mixed=[...A<LF>B<LF>...C]
indentMinus4=[Alpha<LF>..Beta<LF>]
textBlock=[Alpha<LF>..Beta<LF>]
textBlockStripped=[Alpha<LF>..Beta<LF>]
textBlockSpace=[tail.<LF>]
textBlockSpaceStripped=[tail<LF>]
withLF.length=21
withoutLF.length=12
~~~

### 3.1. Diễn giải `internal`: dòng trống và chuẩn hóa newline

Đầu vào `internal` là:

~~~java
"    Alpha  \r\n      Beta\t\r\n\r\n    Gamma "
~~~

- `Alpha` có 4 space ở đầu và 2 space ở cuối; `Beta` có 6 space đầu và một tab ở cuối; `Gamma` có 4 space đầu và một space cuối.
- Giữa `Beta` và `Gamma` có dòng rỗng (hai dấu `\r\n` liên tiếp). Nó **được giữ lại** thành hai dấu `<LF>` liên tiếp trong biểu diễn output.
- Dòng cuối `Gamma` không phải blank và có 4 space đầu, nên `min = 4`; `Beta` còn 2 space.
- Khoảng trắng cuối `Alpha`, tab cuối `Beta` và space cuối `Gamma` đều bị xóa.
- Tất cả CRLF được chuyển thành LF; chuỗi kết quả không còn ký tự CR.

Kết quả `Alpha<LF>..Beta<LF><LF>Gamma` thể hiện đúng cả **vị trí dòng rỗng**, **mức indent tương đối** và **newline chuẩn hóa**.

### 3.2. Diễn giải `withLF` và `withoutLF`: một ký tự đổi cả lề chung

`withLF` có newline cuối, vì vậy `min = 0`; `withoutLF` không có newline cuối, nên `min = 4`. Hai chuỗi có cùng nội dung hiển thị nhưng số space còn lại khác hẳn. Độ dài cũng chứng minh điều này:

- `withLF.stripIndent().length() == 21`: còn 4 space trước `Alpha`, 6 space trước `Beta` và một LF cuối.
- `withoutLF.stripIndent().length() == 12`: không còn space trước `Alpha`, chỉ còn 2 space trước `Beta` và không có LF cuối.

Nếu dùng `System.out.println(result)` thông thường, khác biệt này rất khó quan sát. Khi viết test, dùng `equals(...)`, `length()`, `endsWith("\n")` hoặc biểu diễn khoảng trắng như `show(...)`.

### 3.3. Diễn giải `lastBlank` và `allBlank`

`lastBlank` kết thúc bằng hai space sau `\n`. Hai space này làm `min = 2`, dẫn tới `..Alpha<LF>....Beta<LF>`. Không có nội dung của dòng cuối được giữ lại, nhưng dấu ngắt dòng trước nó vẫn còn.

`allBlank` gồm hai dòng chứa toàn khoảng trắng và kết thúc bằng CRLF. Sau xử lý, phần khoảng trắng biến mất, song hai dấu ngắt dòng được giữ lại dưới dạng LF. Kết quả là `<LF><LF>`, **không phải chuỗi rỗng**. Trường hợp chuỗi đầu vào thật sự rỗng `""` thì `stripIndent()` trả `""`.

### 3.4. Diễn giải `mixed`: tab không bằng nhiều space

`mixed` có bốn space trước `A` và `C`, nhưng chỉ một tab trước `B`. Lề chung tính theo ký tự bằng 1. Vì vậy `A` và `C` còn ba space sau cắt lề. Một tab không được tự chuyển thành 4 space, dù editor làm nó trông rộng bằng bốn cột.

## 4. `stripIndent()` và text block: cùng quy tắc, khác đầu vào

Text block là cú pháp ngôn ngữ chính thức từ Java 15; **trình biên dịch** chuẩn hóa line endings, loại incidental whitespace rồi xử lý escape sequences để tạo `String`. Phương thức `stripIndent()` thì hoạt động trên **giá trị `String` hiện đã có tại runtime**. Vì thế không thể lấy nguyên chuỗi có newline cuối rồi mặc định kết quả xử lý sẽ giống text block chứa nội dung trông tương tự.

Xét text block trong chương trình phần 3:

~~~java
String textBlock = """
    Alpha
      Beta
    """;
~~~

Dấu đóng nằm trên một dòng riêng và lề của dấu đóng được tính trong quá trình compiler phân tích phần nội dung nguồn. Compiler loại 4 space thụt chung và tạo ra chuỗi có giá trị `"Alpha\n  Beta\n"`. Khi gọi `textBlock.stripIndent()` sau đó, chuỗi runtime **đã kết thúc bằng `\n`**, nên `min = 0`; giá trị không bị cắt lề thêm.

Ngược lại, chuỗi runtime viết trực tiếp:

~~~java
String manual = "    Alpha\n      Beta\n";
String result = manual.stripIndent();
~~~

có giá trị **còn nguyên** 4 và 6 space trước các dòng. Vì nó kết thúc bằng `\n`, `min = 0` và hai mức indent đó vẫn còn. Đây không phải lỗi của API: **compiler đã xử lý nguồn text block trước khi sinh `String`, còn runtime method đang xử lý một giá trị khác**.

Nếu bạn chỉ muốn tạo text block để gán biến trong mã Java, thường **không cần gọi `stripIndent()` lần thứ hai**; hãy kiểm tra vị trí dấu đóng để kiểm soát mức indent và newline. `stripIndent()` phát huy tác dụng khi cần chuẩn hóa một chuỗi multiline **đọc từ file, request, template engine hoặc nguồn runtime khác**, miễn là chính sách dữ liệu cho phép thay đổi whitespace.

### 4.1. Vị trí dấu đóng text block ảnh hưởng LF cuối

Đoạn sau minh họa một text block có newline cuối:

~~~java
String withFinalLF = """
    A
    B
    """;
~~~

Chuỗi có giá trị `"A\nB\n"`. Nếu đặt dấu đóng ngay sau `B`:

~~~java
String withoutFinalLF = """
    A
    B""";
~~~

thì giá trị là `"A\nB"`. Hai đoạn chỉ minh họa **giá trị compiler tạo**, không phải chương trình độc lập. Sự khác biệt có thể quan trọng nếu chuỗi được gửi đi qua giao thức yêu cầu payload chính xác.

### 4.2. Escape `\s` có thể bị xóa khi gọi `stripIndent()` thêm lần nữa

Trong text block, `\s` cho phép giữ một space cuối dòng vì escape được giải nghĩa **sau khi** compiler xử lý incidental whitespace:

~~~java
String withSpace = """
    tail\s
    """;
~~~

Giá trị compiler tạo ra là `"tail \n"` (một space trước LF). Nhưng `withSpace.stripIndent()` là lời gọi **runtime mới**; theo hợp đồng của method, khoảng trắng cuối dòng có nội dung sẽ bị loại, nên kết quả là `"tail\n"`. Chương trình ở phần 3 đã kiểm tra hai output:

~~~text
textBlockSpace=[tail.<LF>]
textBlockSpaceStripped=[tail<LF>]
~~~

**Hệ quả:** đừng thêm `.stripIndent()` vào một text block vốn chứa trailing space có ý nghĩa nghiệp vụ rồi mong `\s` vẫn được bảo toàn. Cần quyết định rõ **định dạng chuỗi mong muốn** trước khi chuẩn hóa.

## 5. Phân biệt với những phương thức `String` khác

| API | Quy tắc cốt lõi | Ảnh hưởng đến dòng và newline |
| --- | --- | --- |
| `stripIndent()` (Java 15+) | Tính lề chung theo các dòng không blank và dòng cuối; bỏ indent chung, trim cuối từng dòng | **Giữ số dấu ngắt dòng logic**, chuẩn hóa CR/CRLF thành LF; dòng blank còn vị trí |
| `indent(int n)` (Java 12+) | Thêm `n` space nếu `n > 0`; nếu `n < 0`, bỏ tối đa `-n` ký tự whitespace đầu **mỗi dòng** | Chuẩn hóa line endings; **mỗi dòng đầu ra được kết thúc bằng LF**, kể cả đầu vào ban đầu không có LF cuối |
| `strip()` (Java 11+) | Bỏ whitespace ở **hai đầu toàn bộ chuỗi**, không tính lề chung từng dòng | Có thể mất newline/blank lines ở **đầu và cuối chuỗi**; không tự xử lý indent nội bộ |
| `stripLeading()` / `stripTrailing()` | Chỉ bỏ whitespace ở một đầu **toàn bộ chuỗi** | Không dùng để loại lề chung của một khối nhiều dòng |
| `lines()` (Java 11+) | Trả luồng các dòng, không gồm ký tự ngắt dòng | **Không tạo phần tử dòng rỗng sau dấu terminator cuối**; không tự bảo toàn newline khi ghép lại |

Ví dụ `withLF.indent(-4)` trong phần 3 tạo kết quả `Alpha<LF>..Beta<LF>`, dù `withLF.stripIndent()` giữ nguyên 4 và 6 space. Hai phương thức có mục tiêu khác nhau: `indent(-4)` được yêu cầu bỏ tối đa bốn ký tự đầu **từng dòng**, còn `stripIndent()` phải **tự tính `min`** và chịu ảnh hưởng của dòng cuối rỗng.

Khi biết chính xác số space cần bỏ và muốn xử lý cả chuỗi kết thúc bằng newline, `indent(-4)` có thể thích hợp hơn, nhưng cần nhớ nó **cũng có thể thêm newline cuối** đối với chuỗi vốn không có newline. Khi muốn duy trì đúng byte payload, không thay thế hai hàm cho nhau mà không có test.

Một lưu ý tinh tế: `String.lines()` thường không tạo phần tử rỗng cuối nếu chuỗi kết thúc bằng `\n`; trong khi quy tắc `stripIndent()` vẫn xét dòng cuối rỗng để tính `min`. Vì vậy tự viết `stream = source.lines()...` rồi loại indent dựa trên các phần tử này có thể cho kết quả **khác** `source.stripIndent()`. Nếu tự triển khai, phải mô tả và kiểm thử rõ chính sách newline cuối.

## 6. Các tình huống ứng dụng thực tế

### 6.1. Chuẩn hóa văn bản đa dòng trước khi hiển thị

Một ứng dụng nhận phần mô tả nhiều dòng từ file hoặc hệ thống khác. Nếu nghiệp vụ cho phép **bỏ khoảng trắng thụt chung và space cuối dòng**, `stripIndent()` giúp giữ lại cấu trúc lồng nhau tương đối và các dòng rỗng. Nên chạy test cho các mẫu có/không có LF cuối, CRLF, dòng blank ở giữa, dòng cuối chỉ chứa space.

**Lưu ý:** Nếu đầu vào luôn kết thúc bằng LF và bạn muốn loại indent, `stripIndent()` có thể **không** thực hiện điều bạn kỳ vọng vì `min = 0`. Hãy quyết định chính sách newline trước; không tự động gọi thêm `strip()` một cách mù quáng vì `strip()` có thể làm mất cả newline/blank line có ý nghĩa.

### 6.2. Xử lý JSON, YAML, SQL hoặc template

Dòng rỗng và số space có thể mang ý nghĩa:

- **YAML hoặc code block:** mức indent tương đối có thể thay đổi cách diễn giải; cần test chuỗi sau xử lý với parser thích hợp.
- **SQL nhiều dòng:** `stripIndent()` chỉ định dạng chuỗi, **không ngăn SQL injection**; giá trị động vẫn cần tham số hóa qua `PreparedStatement`.
- **JSON:** nên dùng serializer/parser đúng chuẩn cho dữ liệu động, thay vì coi xử lý indent là bước xác thực hoặc escape dữ liệu.
- **Markdown, email, mẫu văn bản:** newline cuối và các dòng blank có thể ảnh hưởng tới hiển thị; không bỏ chúng nếu sản phẩm cần giữ.

### 6.3. Dữ liệu cần giữ nguyên tuyệt đối

Khi dữ liệu đang được ký số, băm, so sánh checksum, truyền qua giao thức có yêu cầu CRLF, hoặc chứa khoảng trắng cuối dòng có ý nghĩa, **không nên âm thầm gọi `stripIndent()`**. Phương thức có thể chuyển `\r\n` thành `\n`, loại trailing whitespace và thay đổi byte được mã hóa. Nếu hệ thống cần canonicalization, các bên phải thống nhất thuật toán, encoding và thời điểm áp dụng, rồi kiểm tra byte cuối cùng trước ký/xác minh.

## 7. Lỗi phổ biến và cách chẩn đoán

**Sai lầm 1 — “`stripIndent()` luôn đưa dòng ít thụt nhất về cột 0.”**  
Sai với chuỗi kết thúc bằng newline: dòng cuối rỗng khiến `min = 0`. Kiểm tra `endsWith("\n")`, `endsWith("\r")` hoặc `endsWith("\r\n")`; quan sát chiều dài và ký tự cuối.

**Sai lầm 2 — “Một dòng trống giữa block làm lề chung thành 0.”**  
Không đúng. Dòng blank **nằm giữa** không tham gia tính `min`; **dòng cuối** mới được xét cả khi blank. Dù vậy, các dòng blank vẫn còn dưới dạng dòng rỗng trong kết quả.

**Sai lầm 3 — “`stripIndent()` xóa luôn các dòng trống.”**  
Không. Nó biến nội dung dòng blank thành `""`, nhưng vẫn duy trì số terminator logic. Với `" \t\r\n  \r\n"`, kết quả là `"\n\n"`.

**Sai lầm 4 — “Kết quả giữ nguyên CRLF gốc.”**  
Không. Phương thức chuẩn hóa các line terminator `\n`, `\r` và `\r\n` thành LF. Nếu protocol yêu cầu CRLF, hãy xử lý định dạng đó tại tầng giao thức và kiểm thử byte thực tế.

**Sai lầm 5 — “Tab hiển thị bằng 4 space nên tính indent bằng 4.”**  
Không. Khi tính lề, tab là **một ký tự whitespace**. Bật tính năng hiện dấu cách/tab trong IDE và dùng test nếu có nguồn trộn tab/space.

**Sai lầm 6 — “`\s` trong text block luôn được giữ dù gọi `stripIndent()`.”**  
Không. `\s` giúp bảo toàn dấu cách trong **bước compiler xử lý text block**, nhưng lời gọi `stripIndent()` **sau đó** sẽ loại trailing space trên dòng có nội dung.

**Sai lầm 7 — “`stripIndent()` cũng như `strip()` hoặc `indent(-n)`.”**  
Sai về cả việc tính lề và hành vi newline. Chọn đúng API theo yêu cầu, đặc biệt khi đầu vào kết thúc bằng line terminator.

**Sai lầm 8 — “Chỉ cần nhìn kết quả của `println` là biết chính xác whitespace.”**  
Khoảng trắng thường vô hình trong terminal. Hãy dùng `equals(...)`, `length()`, `codePoints()`, hoặc một hàm hiển thị ký tự như `show(...)`; với file/giao thức nhạy cảm, so sánh byte theo encoding xác định.

## 8. Bài tập tự kiểm tra

**Câu 1.** `"   A\n     B".stripIndent()` có lề chung bằng bao nhiêu, và tạo ra gì?  
**Đáp án:** `min = 3`; kết quả `"A\n  B"`, không có newline cuối.

**Câu 2.** Nếu thêm `\n` vào cuối chuỗi ở câu 1 thì sao?  
**Đáp án:** Dòng cuối rỗng làm `min = 0`; kết quả giữ indent `"   A\n     B\n"`.

**Câu 3.** Trong `"   A\n \n     B"`, dòng giữa gồm một space có kéo `min` xuống 1 không?  
**Đáp án:** Không, vì đó là dòng blank **ở giữa**. `min = 3`, kết quả `"A\n\n  B"`.

**Câu 4.** `" \r\n \r\n".stripIndent()` trả về gì?  
**Đáp án:** `"\n\n"`, vì hai terminator được giữ nhưng blank lines trở thành chuỗi rỗng.

**Câu 5.** Tại sao `"   A\n     B\n".indent(-3)` có thể cho kết quả khác `stripIndent()`?  
**Đáp án:** `indent(-3)` bỏ tối đa ba ký tự đầu trên từng dòng theo yêu cầu; `stripIndent()` tự tính lề chung và tính cả dòng cuối rỗng, nên không bỏ indent ở ví dụ này.

**Câu 6.** Khi cần ký dữ liệu gốc có CRLF, có nên gọi `stripIndent()` trước khi tính chữ ký mà không có thỏa thuận từ hai phía?  
**Đáp án:** Không. Phương thức chuẩn hóa line endings và có thể thay đổi nội dung; chữ ký/checksum phải dùng cùng biểu diễn byte đã thống nhất.

## 9. Tài liệu chính thức

- [Java SE 26 — `String.stripIndent()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html#stripIndent()) — hợp đồng về dòng blank, xác định `min`, chuẩn hóa LF, newline cuối và `Since: 15`.
- [Java SE 26 — `String.indent(int)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html#indent(int)) — để phân biệt quy tắc indent tường minh và newline cuối.
- [Java SE 25 — Text Blocks](https://docs.oracle.com/en/java/javase/25/language/text-blocks.html) — cách compiler xử lý incidental whitespace, vị trí dấu đóng và newline.
- [OpenJDK JEP 378 — Text Blocks](https://openjdk.org/jeps/378) — mô tả thiết kế khi text blocks trở thành tính năng chuẩn trong Java 15.
