# Thứ tự xử lý xuống dòng, thụt lề và escape trong Java text blocks

## 1. Vì sao thứ tự xử lý quan trọng?

**Text block** là một dạng `String` literal nhiều dòng, được mở và đóng bằng ba dấu nháy kép `"""`. Dù source được căn lề đẹp, giá trị `String` cuối cùng không nhất thiết chứa đúng những dấu cách, dấu xuống dòng và dấu gạch chéo ngược mà ta nhìn thấy. Đối với **nội dung text block**, Java áp dụng **ba bước theo thứ tự cố định**:

1. **Normalize line terminators**: chuẩn hóa các ký tự kết thúc dòng thật trong nội dung nguồn (CRLF, CR, LF) về LF (`\n`).
2. **Strip incidental white space**: loại phần thụt lề chung (incidental indentation) và trailing whitespace được coi là không chủ ý.
3. **Translate escape sequences**: sau cùng mới dịch `\s`, `\n`, `\t`, `\r`, `\\`, `\040` và escape nối dòng `\` ngay trước line terminator.

```text
Java source file
    │
    ├─ Trước khi nhận diện literal: xử lý Unicode escapes của source
    │
    └─ Đối với nội dung text block:
          1. CRLF/CR → LF
          2. Bỏ incidental indentation và trailing whitespace
          3. Dịch escape sequences
                    ↓
              java.lang.String
```

**Điểm mấu chốt:** bước 2 xảy ra **trước** bước 3. Vì vậy `\s` có thể giữ những dấu cách cuối dòng; `\n` tạo ra newline sau khi bước xóa whitespace đã kết thúc; và `\` + xuống dòng thực sự có thể xóa newline đó dù bước 1 đã chuẩn hóa nó thành LF.

Các quy tắc này thuộc tính năng **text blocks chính thức từ Java 15 (JEP 378)** và vẫn có trong Java 17, 21, 25, 26. Java 14 chỉ là giai đoạn preview lần hai (JEP 368), đã mang lại `\s` và escape nối dòng; không cần bật preview cho ví dụ Java 17+ hiện nay.

## 2. Phân biệt ba lớp biến đổi thường bị nhầm

Cần tách **việc đọc toàn bộ Java source** ra khỏi **ba bước xử lý nội dung text block**.

| Giai đoạn | Đối tượng xử lý | Kết quả điển hình |
| --- | --- | --- |
| Xử lý Unicode escapes của source | Source Java trước khi token hóa | `\u0020` trong source trở thành một space quá sớm, không phải “hàng rào” giữ trailing spaces |
| Normalize line terminators | Các line terminators **thật** nằm trong text block | CRLF hay CR trở thành LF |
| Strip incidental white space | Các dòng văn bản trong text block | Xóa lề chung và dấu cách/tab cuối dòng |
| Translate escape sequences | Escape còn nguyên trong nội dung | `\s` → space; `\r` → CR; `\` + newline → chuỗi rỗng |

Khi nói “dịch escape cuối cùng”, đó là **escape sequences trong text block**. **Unicode escapes dạng `\uXXXX`** là một cơ chế source-level xảy ra trước, nên không được lẫn hai cơ chế này.

Một trường hợp thường gặp:

```java
String a = """
        Hello
        World
        """;
```

Giá trị `a` là `"Hello\nWorld\n"`. Dòng `Hello` và `World` trong source có cùng mức lề; phần lề ấy không xuất hiện trong giá trị chuỗi. LF cuối chuỗi được giữ vì dòng `World` kết thúc bằng newline thật trước delimiter đóng.

## 3. Bước 1 — Chuẩn hóa các ký tự xuống dòng của source

Java source có thể được lưu bằng **LF** (thường ở Unix) hoặc **CRLF** (thường ở Windows). Text block chuẩn hóa những line terminators **đang là ký tự kết thúc dòng của nội dung** về LF (`\n`), giúp giá trị `String` không đổi chỉ vì file dùng quy ước kết thúc dòng khác nhau.

```java
String lines = """
        red
        blue
        """;

System.out.println(lines.equals("red\nblue\n")); // true
```

Khi file source được lưu với CRLF, giá trị `lines` vẫn chứa **LF**, không phải `\r\n`. Biểu diễn gọn là `red<LF>blue<LF>`.

**Giới hạn của bước 1:** `\n` và `\r` gồm các dấu `\`, `n`/`r` trong source là **escape sequences**, chưa phải LF/CR thực vào thời điểm normalize. Chúng chỉ trở thành các ký tự điều khiển ở bước **3**, sau khi chuẩn hóa đã hoàn tất:

```java
String actualCR = """
        left\rRight\
        """;
// actualCR là "left\rRight", có CR thực giữa "left" và "Right".
```

`actualCR` vẫn có ký tự CR vì escape `\r` được dịch cuối cùng; không có giai đoạn normalize thứ hai sau khi escape đã dịch.

### 3.1. LF không nhất thiết bằng dấu xuống dòng của hệ điều hành

Nếu cần chuyển LF sang quy ước của môi trường ghi file/giao thức, hãy làm **rõ ràng tại ranh giới xuất dữ liệu**, chẳng hạn dùng API text writer phù hợp. Không giả định rằng text block tự tạo `System.lineSeparator()`. Với giao thức có quy định chính xác CRLF, phải chuyển đổi theo hợp đồng giao thức, đồng thời kiểm thử số byte/ký tự thật.

## 4. Bước 2 — Loại incidental indentation

Một text block thường được thụt vào trong thân method/class để source dễ đọc. Compiler cố loại **lề dùng để trình bày source**, giữ lại lề tương đối của nội dung.

```java
String text = """
        first
          second
        """;
```

Giá trị tương đương:

```java
String text = "first\n  second\n";
```

Dòng `second` vẫn có **hai dấu cách tương đối** so với `first`; các dấu cách căn thẳng cả khối với code Java đã được loại.

### 4.1. Lề chung được xác định như thế nào?

Ở mức khái niệm, compiler xem các dòng có nội dung và **vị trí delimiter đóng nếu ở dòng riêng** để xác định lề chung có thể loại. Nó bỏ phần lề chung đó ở đầu mỗi dòng, không xóa tùy ý khoảng trắng **bên trong** văn bản.

Ví dụ:

```java
String html = """
            <div>
              <span>Hi</span>
            </div>
        """;
```

Ở đây delimiter đóng được đặt **ít thụt hơn** các dòng nội dung. Một phần lề đầu dòng của nội dung có thể được **giữ lại có chủ ý** sau khi phần lề chung bị loại. Vị trí đóng `"""` do đó **có ảnh hưởng tới kết quả**, không chỉ là vấn đề trang trí.

Nếu muốn lề dữ liệu chính xác, hãy thiết kế vị trí delimiter rõ ràng, hoặc xử lý sau bằng `String.indent(int)` và kiểm thử đầu ra. Không nên tự đếm số khoảng trắng bằng mắt khi các dòng còn bị formatter tác động.

### 4.2. Dấu cách và tab không tương đương khi hiển thị

Ở bước xác định incidental white space, **mỗi ký tự whitespace ở đầu dòng được xét như một ký tự**, không phải theo độ rộng “tab = 4 hoặc 8 ô” do editor hiển thị. Khi các dòng trộn tabs và spaces, hai dòng trông giống lề nhau có thể có số ký tự whitespace khác nhau, gây lệch nội dung sau khi strip.

**Thực hành:** thống nhất kiểu thụt lề trong text block, tránh tab/space trộn lẫn; với `javac`, có thể bật `-Xlint:text-blocks` để tìm một số vấn đề căn lề/trailing whitespace. Không nên giả định mọi editor sẽ hiển thị tab giống nhau.

### 4.3. Whitespace cuối dòng cũng bị loại

Bước 2 không chỉ bỏ lề bên trái mà còn bỏ **trailing whitespace** trên mỗi dòng. Điều này ngăn việc editor tự xóa dấu cách cuối dòng làm thay đổi String mà mắt thường không phát hiện.

```java
String s = """
        red
        green
        """;
```

Khi cần dấu cách thật ở cuối các dòng, **không dựa vào khoảng trắng vô hình trong source**. Các escape `\s` và `\040` chỉ trở thành space ở bước 3, nên hữu ích hơn.

## 5. Bước 3 — Dịch escape sequences cuối cùng

Sau khi hoàn thành normalize + strip, compiler mới dịch escape sequences trong text block:

| Escape trong source | Ký tự/kết quả sau bước 3 | Ghi chú |
| --- | --- | --- |
| `\n` | LF (U+000A) | Có thể chèn newline **bên trong cùng một dòng source** |
| `\r` | CR (U+000D) | Không bị normalize lại thành LF |
| `\t` | Tab (U+0009) | Xuất hiện sau bước tính lề |
| `\s` | Một space (U+0020) | Giữ trailing spaces có chủ ý |
| `\040` | Một space (octal escape) | Cũng dịch sau bước strip |
| `\\` | Một backslash thật | Dùng khi nội dung cần dấu `\` |
| `\"` | Dấu nháy kép | Trong text block thường không cần trừ khi cần tránh kết thúc delimiter |
| `\` + line terminator thật | **Không thêm ký tự nào** | Nối hai dòng nguồn hoặc bỏ newline cuối |

Các escape `\b`, `\f`, `\'` và octal escapes hợp lệ khác cũng theo các quy tắc String literal của Java. Text block **không phải raw string**: backslash vẫn có ý nghĩa escape.

### 5.1. Escape tạo ký tự sau khi đã strip

```java
String escapedNewline = """
        X\nY\
        """;
```

Một dòng source chứa `X\nY`, rồi `\` ngay trước newline cuối. Kết quả `"X\nY"`: có **LF giữa X và Y**, không có LF cuối. Trình tự là: strip xử lý lề trước, `\n` mới thêm LF, còn escape nối dòng cuối xóa newline nguồn.

Tương tự:

```java
String tab = """
        x\tY\
        """;
```

kết quả là ba ký tự `x`, TAB, `Y`. Dấu tab được tạo **sau** bước strip, nên không tự chuyển thành dấu cách hoặc bị “căn lề” bởi compiler.

## 6. Vì sao `\s` giữ được trailing spaces?

Xét:

```java
String padded = """
        red  \s
        green\s
        blue \s
        """;
```

Sau bước 1, source được normalize về LF; bước 2 bỏ lề chung nhưng các phần cuối dòng **chưa được dịch escape**:

```text
red  \s<LF>
green\s<LF>
blue \s<LF>
```

`\s` hoạt động như một **hàng rào ký tự** sau các dấu cách nguồn. Ở bước 2, các dấu cách đứng trước escape không bị coi là trailing whitespace cần xóa. Sau bước 3, các escape tạo thêm một dấu cách thật:

```text
red···<LF>
green·<LF>
blue··<LF>
```

Trong biểu diễn trên, `·` chỉ một dấu cách. Độ dài mỗi dòng tính trước LF là **6 ký tự**: `red` + 3, `green` + 1, `blue` + 2.

```java
System.out.println(
    java.util.Arrays.toString(
        padded.lines().mapToInt(String::length).toArray()
    )
); // [6, 6, 6]
```

**Lưu ý nguồn:** `\u0020` **không** thay được `\s` trong trường hợp này. Unicode escapes được xử lý **trước khi parser nhận diện text block**, nghĩa là `\u0020` sớm trở thành space thật và lại có thể bị loại ở bước strip. Trái lại, `\s`/`\040` còn được giữ dưới dạng escape cho tới bước 3.

### 6.1. Khác biệt giữa Java `\s` và regex `\s`

```java
// Java compiler dịch "\s" thành một space trước khi regex engine nhận:
java.util.regex.Pattern onlySpaces =
        java.util.regex.Pattern.compile("\s+");

// Regex engine cần nhận một dấu backslash rồi chữ s:
java.util.regex.Pattern whitespace =
        java.util.regex.Pattern.compile("\\s+");
```

Dạng thứ hai là cách viết Java để regex nhận `\s+` theo ngữ nghĩa biểu thức chính quy. Cẩn thận khi để regex hay JSON trong text block vì các lớp escape có thể được xử lý ở các giai đoạn khác nhau.

## 7. Escape nối dòng: `\` + newline xóa newline sau khi normalize

Xét:

```java
String joined = """
        Hello \
        Java\
        """;
```

Bước 1 normalize các newline nguồn thành LF. Bước 2 bỏ lề chung. Bước 3 thực hiện hai escape nối dòng:

- Dòng `Hello \`: loại `\` + LF, nhưng **giữ một dấu cách** trước `\`, nên `Hello` và `Java` không dính vào nhau.
- Dòng `Java\`: loại newline cuối trước delimiter đóng.

Giá trị chính xác là `"Hello Java"`, một dòng, **không có LF cuối**:

```java
System.out.println(joined.equals("Hello Java")); // true
```

Nếu **không có** dấu cách trước `\` ở dòng đầu, `Hello\` + `Java` tạo `"HelloJava"`. Escape nối dòng **không tự chèn space**.

Dấu `\` phải nằm **liền trước line terminator thực**; nếu có dấu cách sau backslash, đó không còn là escape nối dòng. Tránh những công cụ tự chèn khoảng trắng cuối dòng hoặc cắt dòng nguồn mà không hiểu Java escape.

### 7.1. Newline cuối text block

```java
String withLF = """
        A
        B
        """;

String noLF = """
        A
        B\
        """;
```

`withLF` có giá trị `"A\nB\n"`; `noLF` có giá trị `"A\nB"`. Sự khác biệt là LF **sau chữ B**. Để giá trị đúng với định dạng test, HTTP payload, snapshot hoặc file text, phải quyết định rõ có muốn newline cuối hay không.

Có thể đặt delimiter đóng ngay sau ký tự cuối để bỏ newline:

```java
String alsoNoLF = """
        A
        B""";
```

Nhưng cách đó cũng có thể ảnh hưởng tới mức incidental indentation; khi muốn delimiter trên dòng riêng, escape nối dòng cuối thường dễ hiểu hơn.

## 8. Chương trình Java 17+ hoàn chỉnh, biên dịch và chạy được

Lưu thành **`EscapeOrderDemo.java`**:

```java
public class EscapeOrderDemo {
    static String visible(String s) {
        return s.replace("\\", "\\\\")
                .replace(" ", "·")
                .replace("\t", "<TAB>")
                .replace("\r", "<CR>")
                .replace("\n", "<LF>");
    }

    public static void main(String[] args) {
        String normalized = """
                red
                  blue
                """;
        String padded = """
                red  \s
                green\s
                blue \s
                """;
        String joined = """
                Hello \
                Java\
                """;
        String withFinalLF = """
                A
                B
                """;
        String withoutFinalLF = """
                A
                B\
                """;
        String escapedNewline = """
                X\nY\
                """;
        String escapedCR = """
                left\rRight\
                """;
        String tab = """
                x\tY\
                """;
        String backslash = """
                C:\\data\
                """;
        String strip = "    one\n      two".stripIndent();
        String directSpace = "A\sB";

        System.out.println("normal=" + visible(normalized));
        System.out.println("padded=" + visible(padded));
        System.out.println("paddedLines=" +
                java.util.Arrays.toString(
                        padded.lines().mapToInt(String::length).toArray()));
        System.out.println("joined=" + visible(joined));
        System.out.println("withFinalLF=" + visible(withFinalLF));
        System.out.println("withoutFinalLF=" + visible(withoutFinalLF));
        System.out.println("escapedNewline=" + visible(escapedNewline));
        System.out.println("escapedCR=" + visible(escapedCR));
        System.out.println("tab=" + visible(tab));
        System.out.println("backslash=" + visible(backslash));
        System.out.println("stripIndent=" + visible(strip));
        System.out.println("directSpace=" + visible(directSpace));
        System.out.println("lineCount=" + normalized.lines().count());
    }
}
```

Biên dịch và chạy với **JDK 17 hoặc mới hơn**:

```bash
javac --release 17 EscapeOrderDemo.java
java EscapeOrderDemo
```

Kết quả chính xác khi chạy:

```text
normal=red<LF>··blue<LF>
padded=red···<LF>green·<LF>blue··<LF>
paddedLines=[6, 6, 6]
joined=Hello·Java
withFinalLF=A<LF>B<LF>
withoutFinalLF=A<LF>B
escapedNewline=X<LF>Y
escapedCR=left<CR>Right
tab=x<TAB>Y
backslash=C:\\data
stripIndent=one<LF>··two
directSpace=A·B
lineCount=2
```

**Quy ước output:** method `visible` biến mỗi dấu cách thật thành `·`, TAB thành `<TAB>`, CR thành `<CR>` và LF thành `<LF>`. Nó còn biến một ký tự backslash thật thành hai ký tự backslash để nhìn rõ. Đây là **ký hiệu hiển thị trong demo**, không phải cách Java tự biểu diễn chuỗi.

### Giải thích kết quả theo giai đoạn

1. `normal`: sau normalize và strip, chuỗi gồm `red`, LF, hai dấu cách, `blue`, LF. Phần lề chung của mã Java không còn.
2. `padded`: mỗi `\s` giữ trailing spaces; ba dòng có độ dài 6, và LF cuối.
3. `joined`: `\` + LF ở hai vị trí bị bỏ ở bước 3; giữ một space giữa hai từ.
4. `withFinalLF` so với `withoutFinalLF`: chỉ khác dấu LF cuối.
5. `escapedNewline`: escape `\n` trong source trở thành LF thực **sau** bước strip.
6. `escapedCR`: escape `\r` tạo CR thực ở bước 3; **không bị normalize lại**.
7. `tab`: escape `\t` tạo TAB thực sau xử lý lề.
8. `backslash`: source `C:\\data` cho String `C:\data`; method `visible` in thành `C:\\data` để tránh khó nhìn.
9. `stripIndent`: phương thức `String.stripIndent()` xử lý một String runtime và giữ hai dấu cách tương đối trên dòng thứ hai.
10. `directSpace`: `\s` cũng là space escape trong literal `"..."` thông thường.
11. `lineCount=2`: `String.lines()` của `red\n  blue\n` cho hai dòng nội dung, không tạo thêm một dòng thứ ba chỉ vì kết thúc bằng LF.

**Kiểm thử cross-platform:** ví dụ này đã được biên dịch với source file dùng CRLF; kết quả `normal` vẫn hiển thị `<LF>` thay vì `<CR><LF>`.

## 9. Xử lý ở compile time và các String API runtime không giống nhau

Ba bước ở đầu bài áp dụng cho việc xác định **giá trị text block literal** từ source. Sau khi có object `String`, bạn vẫn có thể gọi các phương thức xử lý chuỗi ở runtime, nhưng **chúng là thao tác riêng** chứ không làm Java “biên dịch lại” text block.

### 9.1. `String.stripIndent()`

```java
String raw = "    one\n      two";
String cleaned = raw.stripIndent();

System.out.println(cleaned.equals("one\n  two")); // true
```

`stripIndent()` xử lý thụt lề trong **giá trị String đã tồn tại**. Nó có thể hữu ích khi nguồn dữ liệu nhiều dòng đến từ tệp hoặc API chứ không phải text block. Tuy nhiên, có/không có newline cuối ảnh hưởng tới thuật toán xác định lề trong một số trường hợp; hãy kiểm thử thay vì tưởng rằng `stripIndent` lúc nào cũng loại hết lề như ý.

### 9.2. `String.translateEscapes()`

```java
String encoded = "\\n"; // Giá trị gồm hai ký tự backslash, n.
String decoded = encoded.translateEscapes();

System.out.println(decoded.equals("\n")); // true
```

`translateEscapes()` dịch escape từ một **String runtime**, không thực hiện toàn bộ ba bước đặc thù của text block literal, và không dùng để dịch Unicode source escapes theo cách compiler làm. Hãy dùng khi thật sự nhận dữ liệu được encode theo escape rules tương thích; đừng dùng nó như JSON parser hay decoder cho mọi định dạng bên ngoài.

### 9.3. `String.indent(int)`, `lines()` và `formatted(...)`

- `indent(int n)` thay đổi lề **sau khi** String đã tồn tại; kiểm tra hợp đồng newline của method nếu dữ liệu yêu cầu chính xác.
- `lines()` duyệt các dòng, hữu ích khi kiểm chứng chiều dài và whitespace; một String kết thúc bằng newline không nhất thiết sinh thêm dòng rỗng cuối.
- `formatted(...)` thay thế placeholder theo cú pháp Formatter, **không** phải nội suy biến tự động hay escaping an toàn cho JSON/HTML/SQL.

Chọn đúng tầng xử lý: nếu định dạng source cố định, dùng text block và escape hợp lý; nếu dữ liệu đến từ người dùng hoặc hệ thống khác, dùng API xử lý runtime/serializer phù hợp.

## 10. Lỗi thường gặp

### Lỗi A — Nghĩ rằng `\n` được normalize trước khi strip

```java
String s = """
        X\nY\
        """;
```

`\n` **chưa** là newline khi chạy bước 1 và 2, nên nó trở thành LF ở bước 3. Đừng tính lề các dòng mới tạo bởi escape `\n` như thể chúng đã tồn tại trong source trước bước strip.

### Lỗi B — Dùng `\u0020` để giữ trailing spaces

```java
// CỐ Ý MINH HỌA KHÔNG NÊN LÀM:
String value = """
        red\u0020
        """;
```

`\u0020` là Unicode escape source-level, được chuyển thành dấu cách sớm nên có thể bị strip. Thay bằng `red\s` hoặc `red\040` nếu muốn một space cuối dòng thực sự.

### Lỗi C — Nhầm `\r` và CRLF của file nguồn

Nếu nguồn text block dùng CRLF, bước 1 đổi chúng thành LF. Nhưng `\r` là escape được dịch ở bước 3, do đó có thể tạo CR thật. Đừng viết phép thay thế dòng theo hệ điều hành chỉ dựa vào nơi source file được tạo.

### Lỗi D — Cho rằng tabs bằng một số dấu cách cố định

Một tab ở lề source là **một ký tự**, không phải bốn hay tám dấu cách cố định do Java compiler giả định. Dùng tabs/spaces nhất quán; nếu phải giữ tab trong dữ liệu, `\t` được dịch sau bước strip giúp ý định rõ hơn.

### Lỗi E — Mặc định text block có/không có newline cuối

```java
String a = """
        ready
        """;
String b = """
        ready\
        """;
```

`a.equals("ready\n")` là `true`; `b.equals("ready")` cũng là `true`. Khi viết tests, file generation hay payload, cần so khớp newline cuối.

### Lỗi F — Không đặt space trước escape nối dòng

```java
String glued = """
        Hello\
        Java\
        """;
```

Giá trị là `"HelloJava"`, không phải `"Hello Java"`. Muốn một dấu cách, đặt `Hello \` ở dòng đầu. Không đặt dấu cách **sau** `\` vì khi đó escape nối dòng có thể không còn hợp lệ.

### Lỗi G — Nghĩ text block là raw string

```java
String path = """
        C:\\data\
        """;
```

Giá trị chứa **một** backslash trước `data`, không phải hai; `\\` vẫn là Java escape. Nếu tạo JSON/regex có nhiều lớp escaping, hãy dùng serializer hoặc parser đúng định dạng, tránh ghép thủ công thiếu an toàn.

### Lỗi H — Mở text block trên cùng dòng nội dung

```java
// CỐ Ý KHÔNG BIÊN DỊCH:
String invalid = """same line""";
```

Thiếu line terminator sau opening delimiter. Dùng `String s = "same line";` cho chuỗi một dòng hoặc chuyển nội dung xuống dòng tiếp theo.

### Lỗi I — Chỉ nhìn `println`, bỏ qua ký tự ẩn

`println` tự chèn newline khi in nên khó phân biệt String có LF cuối hay không; TAB cũng nhìn giống vài space tùy editor. Dùng `equals`, `length`, `lines()` hoặc method hiển thị ký tự ẩn như `visible` trong demo. Với giao thức yêu cầu chính xác byte, kiểm tra theo encoding thực tế.

## 11. Bài tập kiểm tra hiểu biết

**Câu 1:** Ba bước xử lý text block theo đúng thứ tự là gì?

**Đáp án:** Normalize line terminators → strip incidental whitespace → translate escape sequences. Unicode source escapes là bước sớm **trước** quá trình phân tích literal, không phải bước dịch escape cuối của text block.

**Câu 2:** Tại sao cùng một text block có source CRLF trên Windows và LF trên Linux vẫn cho giá trị giống nhau?

**Đáp án:** Bước normalize chuyển line terminators thực tế trong nội dung text block thành LF; source editor không quyết định kiểu newline của String kết quả.

**Câu 3:** `\r` nằm trong nội dung text block có trở thành LF ở bước 1 không?

**Đáp án:** Không. `\r` khi ấy là hai ký tự escape, chỉ được dịch thành CR ở bước 3; không có normalize lại sau đó.

**Câu 4:** Vì sao `red  \s` giữ được ba dấu cách cuối dòng?

**Đáp án:** `\s` vẫn là escape chưa dịch ở bước 2 nên các space trước nó không bị xóa; bước 3 thêm một space thứ ba.

**Câu 5:** Đoạn nào bỏ LF cuối chuỗi: `"B\n"` hay text block kết thúc bằng `B\` trước newline nguồn?

**Đáp án:** `\n` thêm LF, còn `B\` + newline nguồn xóa newline đó; trường hợp thứ hai không có LF cuối.

**Câu 6:** `String s = "    one\n      two"; s.stripIndent()` có phải compiler chạy lại toàn bộ quy trình text block cho source ban đầu không?

**Đáp án:** Không. Đó là method trên String runtime, có quy tắc của `stripIndent()`, không phải compiler token hóa lại source rồi thực hiện lại cả ba bước.

**Câu 7:** Vì sao một regex muốn nhận whitespace thường cần Java literal `"\\s+"` thay vì `"\s+"`?

**Đáp án:** `\s` trong Java là **space** thật, còn `\\s` chuyển dấu backslash tới regex engine để nó diễn giải nhóm whitespace.

## 12. Checklist khi áp dụng

- [ ] Chọn Java **15+** cho text blocks chính thức; trong dự án Java 17+ không dùng preview flags cũ.
- [ ] Phân biệt Unicode escape xử lý sớm của source với escape được dịch **sau** bước strip của text block.
- [ ] Chỉ trông đợi LF đối với **line terminators thật** trong source text block, không đối với escape `\r`.
- [ ] Đảm bảo mức thụt lề và vị trí delimiter đóng phản ánh số dấu cách muốn giữ.
- [ ] Không trộn tab/space ở lề nếu không có lý do; bật `-Xlint:text-blocks` khi cần kiểm tra.
- [ ] Sử dụng `\s` hoặc `\040` để giữ trailing spaces có chủ ý.
- [ ] Dùng `\` ngay trước newline nguồn khi muốn nối dòng; tự đặt space giữa các từ nếu cần.
- [ ] Kiểm soát LF cuối của String bằng vị trí delimiter và escape nối dòng cuối.
- [ ] Nhớ rằng text block không phải raw string và không tự thực hiện escaping JSON, SQL hay regex.
- [ ] Dùng test so khớp chuỗi thật (kể cả CR, LF, TAB, space) khi định dạng là yêu cầu chức năng.

## Tài liệu chuẩn, vẫn áp dụng hiện nay

1. [Java Language Specification, Java SE 26 — `3.10.6 Text Blocks](https://docs.oracle.com/javase/specs/jls/se26/html/jls-3.html#jls-3.10.6): trình tự normalize line terminators, strip incidental white space và translate escapes.
2. [Oracle — Text Blocks (Java 26)](https://docs.oracle.com/en/java/javase/26/language/text-blocks.html): phân biệt lề nguồn, trailing whitespace, ``\s` và line continuation.
3. [Oracle — Programmer's Guide to Text Blocks (Java 17)](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html): giải thích và ví dụ về normalize, strip, escape, newline cuối.
4. [Java Language Specification, Java SE 26 — `3.3 Unicode Escapes](https://docs.oracle.com/javase/specs/jls/se26/html/jls-3.html#jls-3.3): lý do Unicode source escapes được xử lý trước.
5. [Oracle — Java SE 17 String API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `stripIndent`, `translateEscapes`, `indent` và `lines`.
