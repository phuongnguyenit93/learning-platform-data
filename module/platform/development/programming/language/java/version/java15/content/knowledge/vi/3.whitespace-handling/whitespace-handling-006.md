# Trộn tab với dấu cách và ảnh hưởng đến kết quả trong Java 15

## Mục tiêu và phạm vi

Trong Java, một dòng mã có thể được thụt lề bằng **dấu cách** (*space*, U+0020) hoặc **tab ngang** (*horizontal tab*, U+0009). Hai ký tự này thường có tác dụng giống nhau **khi đứng giữa các token hoặc dùng để căn lề mã nguồn bên ngoài chuỗi**. Tuy nhiên, chúng là **hai ký tự dữ liệu khác nhau**; khi xuất hiện trong `String`, text block, file định dạng nhạy cảm với khoảng trắng hoặc đầu vào cần phân tích, chúng có thể làm thay đổi kết quả.

Bài này phân biệt rõ tác động lên **cú pháp Java**, **giá trị chuỗi**, **text blocks chính thức từ Java 15** và **khả năng tái lập kết quả trong IDE, terminal, Git, CI**. Những quy tắc này vẫn áp dụng trong Java hiện đại; không cần sử dụng cú pháp preview hoặc thư viện đã lỗi thời.

### Quy ước minh họa

| Ký hiệu dùng để giải thích | Ký tự thật | Mã Unicode | Ý nghĩa |
| --- | --- | --- | --- |
| `·` | Một space thông thường | U+0020 | Một ký tự dấu cách |
| `⇥` | Một tab ngang | U+0009 | Một ký tự tab, **không tự động biến thành bốn dấu cách** |
| `\n` | Ký tự xuống dòng trong chuỗi Java | U+000A (LF) | Kết thúc một dòng dữ liệu |
| `\t` | Escape trong mã nguồn Java | Sau khi giải mã thành U+0009 | Cách viết tab tường minh, dễ nhìn thấy khi review |

`·` và `⇥` chỉ là **ký hiệu trực quan trong output minh họa**, không phải cách Java viết space/tab trong mã nguồn. Tab có thể được editor hoặc terminal *hiển thị* như nhiều cột, nhưng bản thân tab vẫn là một ký tự.

## 1. Với cú pháp Java thông thường, tab và space là ký tự phân cách

Java Language Specification `3.6` định nghĩa whitespace thuộc cú pháp từ space ASCII, horizontal tab, form feed và ký tự kết thúc dòng. Trong mã Java bên ngoài literal/comment, thay **space bằng tab ở vị trí thụt lề hoặc giữa các token vẫn được phân tách như trước** thì kết quả biên dịch/chạy không đổi.

Ví dụ, hai dòng sau làm cùng một phép cộng; ký hiệu `⇥` ở dòng thứ hai chỉ mô tả một tab thật giữa các token, **không phải ký tự được gõ vào mã Java**:

```text
int·total·=·7·+·5;
int⇥total⇥=⇥7⇥+⇥5;
```

Cả hai đều biểu diễn các token `int`, `total`, `=`, `7`, `+`, `5`, `;` nên giá trị `total` đều là `12`. Tương tự, thay tab bằng bốn space ở **đầu một dòng Java thông thường** không tự đổi điều kiện `if`, vòng lặp hoặc phạm vi `{ ... }`. Java không dùng số cột thụt lề để xác định block; dấu ngoặc nhọn và cú pháp mới quyết định block.

**Cần giữ ranh giới token.** Việc *xóa hết* whitespace khác với việc *đổi tab thành space*. Chẳng hạn `int total` là khai báo hợp lệ, còn `inttotal` là một định danh khác, không phải hai token. Hoặc `a + +b` là phép cộng với toán tử dấu cộng đơn ngôi, trong khi gộp thành `a++b` dẫn đến cách tách token khác và không tạo biểu thức tương đương. Xuống dòng cũng đặc biệt quan trọng đối với chú thích `//`, text blocks và cấu trúc nội dung chuỗi.

**Không phải mọi ký tự trông giống dấu cách đều là whitespace cú pháp Java.** Ví dụ non-breaking space (U+00A0) có thể hiển thị giống space nhưng không phải space ASCII được liệt kê trong ngữ pháp `3.6`. Khi copy mã từ trang web, tài liệu hoặc chat, hãy kiểm tra ký tự lạ nếu `javac` báo lỗi dù mã trông đúng.

## 2. Trong `String` và `char`, tab với space tạo **giá trị khác nhau**

Một literal `"A\tB"` chứa ba ký tự: `A`, **tab U+0009**, `B`. Trong khi đó `"A    B"` chứa sáu ký tự: `A`, **bốn space**, `B`. Tùy console và thiết lập tab stop, hai giá trị đôi khi nhìn gần giống nhau nhưng không bằng nhau theo `String.equals`.

Các khác biệt có thể lan sang:

- **So sánh, kiểm thử và dữ liệu lưu trữ:** `equals`, `hashCode`, checksum, cache key và snapshot dựa vào ký tự thật.
- **Tách cột:** dữ liệu TSV phân tách bằng tab sẽ không tách đúng nếu thay các tab bằng space.
- **Căn cột khi hiển thị:** terminal/editor có thể đặt tab stop khác nhau; **không giả định tab bằng đúng 4 hoặc 8 space**.
- **Tìm kiếm và regex:** biểu thức chỉ khớp space sẽ khác biểu thức khớp tab hoặc nhiều loại whitespace.

Trong Java 15, escape `\s` bên trong **Java string literal** có nghĩa là **một space U+0020**. Nó khác `\s` của **biểu thức chính quy**, nơi `\s` biểu thị một lớp ký tự whitespace. Muốn truyền regex `\s+` vào `String.split`, viết mã Java `"\\s+"` (hai dấu `\` trong Java source để tạo một dấu `\` trong regex); viết `"\s+"` trong Java 15 chỉ tạo regex `" +"`, khớp các space mà không khớp tab.

## 3. Ví dụ Java chạy được: cùng vẻ ngoài nhưng kết quả khác

Tạo file **`WhitespaceEffects.java`** đúng tên lớp sau. Ví dụ chỉ dùng Java SE, biên dịch ở source/API level Java 15 hoặc bản mới hơn, không có dependency ngoài:

```java
public class WhitespaceEffects {
    public static void main(String[] args) {
        int sum = 7 + 5;

        String withTab = "A\tB";
        String withSpaces = "A    B";

        System.out.println("sum=" + sum);
        System.out.println("equal=" + withTab.equals(withSpaces));
        System.out.println("tab.length=" + withTab.length());
        System.out.println("spaces.length=" + withSpaces.length());
        System.out.println("tab[1]=" + (int) withTab.charAt(1));
        System.out.println("space[1]=" + (int) withSpaces.charAt(1));

        System.out.println("tsv.fields="
                + withTab.split("\t", -1).length + "/"
                + withSpaces.split("\t", -1).length);

        // Java regex \s+ la whitespace; Java literal \s+ la space +.
        System.out.println("regex-whitespace="
                + withTab.split("\\s+").length);
        System.out.println("regex-space-only="
                + withTab.split("\s+").length);

        // Khong co LF o cuoi raw, de dong cuoi tham gia tinh indent.
        String raw = "    red\n\tgreen\n    blue";
        String stripped = raw.stripIndent();

        System.out.println("stripIndent:");
        stripped.lines().forEach(line -> System.out.println(
                "[" + line.replace(" ", "·").replace("\t", "⇥") + "]"
        ));
    }
}
```

Trên máy có JDK hiện đại hỗ trợ target Java 15 (ví dụ JDK 21), biên dịch/chạy tại thư mục chứa file:

```bash
javac --release 15 -encoding UTF-8 -d out WhitespaceEffects.java
java -cp out WhitespaceEffects
```

**stdout chính xác:**

```text
sum=12
equal=false
tab.length=3
spaces.length=6
tab[1]=9
space[1]=32
tsv.fields=2/1
regex-whitespace=2
regex-space-only=1
stripIndent:
[···red]
[green]
[···blue]
```

Giải thích từng nhóm kết quả:

1. `sum=12` là phép toán Java thông thường; thụt lề source bằng tab hay space không đổi giá trị.
2. `equal=false` và mã ký tự `9` so với `32` xác nhận tab/space là **khác nhau ở mức dữ liệu**, dù đều có thể tạo khoảng trống khi hiển thị.
3. `tsv.fields=2/1` chứng minh tab là dấu phân cách TSV thật, không thể tùy ý thay bằng bốn space.
4. Hai dòng regex cho thấy khác biệt giữa **escape của Java** (`"\s+"` thành chuỗi regex `" +"`) và **escape của regex** (`"\\s+"` thành `\s+`).
5. `stripIndent` xóa **một ký tự whitespace ở đầu mỗi dòng** vì dòng `green` bắt đầu bằng đúng một tab, trong khi `red` và `blue` bắt đầu bằng bốn space. Bởi vậy mỗi dòng đỏ/xanh còn ba space (được hiển thị bằng `···`). Thực tế việc lẫn tab và space gây căn lề lệch ngay cả khi editor hiển thị các dòng như có độ thụt gần giống nhau.

`String.stripIndent()` có từ Java 15; nó chuẩn hóa ký tự kết thúc dòng và xử lý lề của các dòng. Trong ví dụ này, `raw` **không có newline cuối chuỗi**, do đó dòng cuối là `blue` và mức indent nhỏ nhất đúng là một ký tự. Nếu đầu vào có newline cuối chuỗi, cần xét cả dòng trống cuối theo quy tắc của `stripIndent`; không suy luận kết quả bằng mắt.

## 4. Java 15 text blocks: trộn tab/space có thể làm đổi nội dung

Từ Java 15, **text blocks** (`"""..."""`) là tính năng chính thức; rất hữu ích cho JSON, HTML, SQL hoặc văn bản nhiều dòng. Java không giữ nguyên mọi khoảng trắng thụt lề nhìn thấy trong mã nguồn. Thay vào đó, nó xử lý nội dung theo thứ tự:

1. Chuẩn hóa ký tự xuống dòng `CRLF` hoặc `CR` thành `LF`.
2. Loại **incidental indentation** như thao tác `String.stripIndent()`.
3. **Sau cùng** mới giải mã các escape như `\t`, `\s` và `\n`.

Trong bước 2, **mỗi ký tự whitespace ở đầu dòng được tính là một**, nên một tab chỉ được tính như **một** space khi đo số lượng ký tự cần bỏ; compiler không biết cách editor vẽ tab thành 4 hay 8 cột. Nếu một dòng bắt đầu bằng 8 space nhưng dòng khác bắt đầu bằng một tab, kết quả loại indent có thể lệch 7 space.

Text block có dấu `"""` đóng ở dòng riêng sẽ sử dụng khoảng trắng trước dấu đóng khi xác định lề. Chuyển vị trí dấu đóng hoặc đổi thành tab ở đó cũng có thể làm thay đổi chuỗi kết quả. Đây là **nội dung String thật** nên có thể ảnh hưởng việc so sánh chuỗi, gửi request, kiểm thử snapshot và định dạng file nhúng.

### So sánh text block dùng bốn space với text block tạo tab có chủ đích

Tạo file **`TextBlockWhitespace.java`**:

```java
public class TextBlockWhitespace {
    public static void main(String[] args) {
        String withSpaces = """
                top
                    child
                """;

        String withTab = """
                top
                \tchild
                """;

        System.out.println("spaces:");
        withSpaces.lines().forEach(
                line -> System.out.println("[" + show(line) + "]")
        );

        System.out.println("tab:");
        withTab.lines().forEach(
                line -> System.out.println("[" + show(line) + "]")
        );
    }

    private static String show(String line) {
        return line.replace(" ", "·").replace("\t", "⇥");
    }
}
```

Biên dịch và chạy:

```bash
javac --release 15 -encoding UTF-8 -d out TextBlockWhitespace.java
java -cp out TextBlockWhitespace
```

**stdout chính xác:**

```text
spaces:
[top]
[····child]
tab:
[top]
[⇥child]
```

Ở text block thứ nhất, `child` được thụt thêm bốn **space thật** so với `top`. Ở text block thứ hai, `\t` trong phần nội dung được giải mã thành **một tab thật** sau khi Java đã xử lý incidental indentation. Nhờ đó, việc định nghĩa ký tự tab của dữ liệu rõ ràng và không phụ thuộc vào tab vô hình trong phần thụt lề của code.

**Nguyên tắc:** dùng nhất quán space hoặc nhất quán tab cho phần thụt lề *mã nguồn* chứa text block; nếu dữ liệu cần tab, đặt escape `\t` một cách tường minh ở vị trí dữ liệu. Nếu cần giữ một space ở cuối dòng dữ liệu text block, dùng `\s` (Java 15+) thay vì gõ một space khó nhìn ở cuối dòng, vì trailing whitespace thông thường bị loại trong bước xử lý text block.

### Nhận cảnh báo từ compiler

Dùng Java compiler có hỗ trợ tùy chọn sau khi biên dịch ví dụ text block:

```bash
javac --release 15 -Xlint:text-blocks -encoding UTF-8 -d out TextBlockWhitespace.java
```

Tùy chọn `-Xlint:text-blocks` giúp phát hiện những tình huống như **inconsistent white space indentation** và **trailing white space will be removed** khi hiện diện trong text block. Hai ví dụ có chủ đích dùng escape `\t` nói trên không cần tạo cảnh báo. Cảnh báo dành cho thụt lề trộn tab và space **thật trong nguồn text block**, hoặc có trailing whitespace sẽ bị loại.

## 5. Khi nào kết quả thay đổi, khi nào chỉ thay đổi cách nhìn?

| Tình huống | Đổi tab thành nhiều space sẽ thế nào? | Cần kiểm tra |
| --- | --- | --- |
| Đầu dòng khai báo, lệnh `if`, vòng lặp hoặc block Java thông thường | Thường chỉ đổi định dạng hiển thị, không đổi runtime behavior | Giữ cú pháp/token và dấu ngoặc đúng |
| Giữa hai token Java đã có ranh giới rõ | Tab và space đều phân cách token | Đừng xóa luôn dấu phân cách hoặc gộp operator |
| Bên trong `String`, `char`, nội dung text block | Có thể đổi **mã ký tự**, độ dài, kết quả `equals` và output | Dùng escape rõ ràng và phép kiểm chứng ký tự |
| Các dòng dẫn đầu của text block, kể cả lề trước dấu đóng | Có thể đổi kết quả **incidental indentation** | Coi tab là **một ký tự**, không phải một số cột |
| Chuỗi TSV / dữ liệu phân tách theo tab | Thay tab bằng space thường phá ranh giới cột | Kiểm tra delimiter thật bằng mã ký tự |
| Định dạng lồng vào text block như YAML hoặc file cấu hình có cú pháp thụt lề | Có thể làm dữ liệu không còn hợp lệ hoặc đổi cấu trúc | Validate/parse đầu ra thực tế với parser tương ứng |
| Review Git/IDE/terminal với tab stop khác nhau | Cách hiển thị/căn lề có thể khác ngay cả khi bytes không đổi | Kiểm tra tab stop và hiển thị ký tự whitespace |

Đừng áp dụng nhận xét “Java bỏ qua whitespace” cho **dữ liệu**. Quy tắc đó chỉ đúng ở vị trí lexical whitespace của **mã nguồn Java**, và còn phụ thuộc ranh giới token.

## 6. Cách phòng tránh khi làm việc nhóm

### Chuẩn hóa phần thụt lề mã nguồn

Một cấu hình `.editorconfig` tham khảo cho dự án chọn **4 space** để thụt lề file Java:

```ini
root = true

[*.java]
indent_style = space
indent_size = 4
tab_width = 4
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
```

`.editorconfig` chỉ có tác dụng khi editor/tool hỗ trợ và đọc cấu hình; nó không thay đổi quy tắc biên dịch của Java. `tab_width = 4` chủ yếu quy định cách **hiển thị tab còn sót lại**, không chứng minh tab được lưu thành bốn space. Đặt cùng cấu hình trong nhóm và bật chức năng **Show Whitespace / Render Whitespace** trong IDE để thấy tab, space và whitespace cuối dòng.

Khi auto-format code, xem lại diff nếu formatter thay đổi literal/text block nhạy cảm với whitespace. Đừng dùng thao tác tìm-thay toàn file để biến mọi `\t` thành bốn space: việc đó có thể làm hỏng chuỗi dữ liệu, TSV hoặc text block.

### Tái lập và chẩn đoán

1. **Đọc từng ký tự thay vì nhìn bằng mắt:** dùng `String.length()`, `charAt(index)` hoặc `codePoints()` trong chương trình, hay hàm hiển thị `replace(" ", "·").replace("\t", "⇥")` như ví dụ.
2. **Đối chiếu byte/ký tự:** tab là U+0009; space là U+0020. Với file UTF-8, byte tương ứng là `09` và `20` (hex). Nếu lỗi liên quan đến copy/paste, kiểm tra thêm ký tự Unicode whitespace khác.
3. **Kiểm tra nguồn sau format:** dùng `git diff --check` để phát hiện một số lỗi whitespace như trailing spaces; lệnh này **không thay thế** kiểm tra thụt lề trộn tab/space hoặc so sánh String thật.
4. **Kiểm tra text block:** biên dịch với `-Xlint:text-blocks`, dùng output hiển thị whitespace và parser cho định dạng nhúng (nếu có).
5. **Xác nhận giữa các môi trường:** chạy trên JDK phù hợp, giữ cố định encoding UTF-8 cho mã có ký tự ví dụ, nhất quán editor settings và kiểm tra stdout/kết quả parse trong CI.

### Quy tắc ra quyết định nhanh

- Nếu khoảng trắng dùng để **thụt lề Java code**, nhất quán một kiểu trong toàn dự án; với nhiều nhóm, **space** thường dễ kiểm soát cách hiển thị hơn.
- Nếu khoảng trắng là **dữ liệu**, xác định chính xác cần U+0020 hay U+0009. Ghi `\t` hoặc `\s` trong Java source khi cần biểu đạt rõ ký tự.
- Nếu đang viết **text block**, kiểm tra dữ liệu sau biên dịch, để ý lề của dấu `"""` đóng và tránh trộn tab/space thật ở đầu dòng.
- Nếu đọc file có delimiter, **parse theo delimiter thực tế**; đừng sửa dữ liệu bằng cách thay tab bằng space tùy ý.

## Tài liệu để tra cứu

- Java Language Specification, Java SE 15, `3.6 White Space` và `3.10.6 Text Blocks`: https://docs.oracle.com/javase/specs/jls/se15/html/jls-3.html
- Java SE 15 `String.stripIndent` và `String.lines`: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/String.html
- Oracle, *Programmer's Guide to Text Blocks*, đặc biệt phần **Detecting Potential Issues with White Space**: https://docs.oracle.com/en/java/javase/17/text-blocks/index.html
- Oracle, mô tả text blocks được duy trì trong Java hiện đại: https://docs.oracle.com/en/java/javase/25/language/text-blocks.html

Các ví dụ chỉ dùng những tính năng **chính thức và vẫn hoạt động** trong Java hiện đại. Nội dung Java 15 ở đây mô tả ranh giới tương thích của cú pháp/API; để phát triển hoặc triển khai ứng dụng thực tế, chọn JDK/JVM còn được nhà cung cấp hỗ trợ.
