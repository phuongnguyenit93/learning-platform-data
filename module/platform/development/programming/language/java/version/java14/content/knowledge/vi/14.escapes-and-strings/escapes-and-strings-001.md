# Escape `\s` để biểu diễn khoảng trắng cần giữ trong Java (Java 15+)

> **Mục tiêu:** hiểu `\s` trong mã nguồn Java biểu diễn một dấu cách thông thường (space, U+0020), dùng nó để giữ khoảng trắng có ý nghĩa — nhất là ở cuối dòng **text block** — và không nhầm `\s` của Java với `\s` trong biểu thức chính quy. Đây là cú pháp đã **chính thức** cùng text blocks từ Java 15, vẫn áp dụng trong Java hiện đại; các ví dụ chạy với JDK 17+ và không dùng tính năng preview của Java 14.

## 1. `\s` thật sự tạo ra ký tự gì?

Trong một **string literal** hoặc **text block** (và cả character literal), `\s` là một *escape sequence* của ngôn ngữ Java. Khi compiler xử lý chuỗi, hai ký tự ở mã nguồn là dấu `\` và chữ `s` được chuyển thành đúng **một dấu cách ASCII SP**, có giá trị Unicode **U+0020** và mã thập phân **32**.

```java
String a = "Hello\sWorld";
String b = "Hello World";
char space = '\s';

System.out.println(a.equals(b));       // true
System.out.println(a.length());        // 11
System.out.println((int) space);        // 32
```

Đây là **snippet minh họa** đặt trong thân phương thức, không phải tệp chạy độc lập. `a` và `b` có nội dung ký tự giống nhau. Java không lưu nguyên văn chữ `\s` trong giá trị `String` của `a`, và `\s` **không** có tác dụng đặc biệt khi đọc dữ liệu đã ở dạng `String` trong bộ nhớ.

**Điều `\s` không có nghĩa:** nó không biểu diễn mọi loại whitespace, không phải tab (`\t`), newline (`\n`), carriage return (`\r`), non-breaking space (U+00A0), và cũng không tự tạo nhiều dấu cách. Một lần `\s` tạo **một dấu cách U+0020**; muốn hai dấu cách rõ ràng, có thể viết `\s\s`.

| Cách viết ở Java source | Ký tự được tạo trong chuỗi | Số ký tự trong giá trị |
|---|---|---:|
| `"A\sB"` | `A`, space, `B` | 3 |
| `"A B"` | `A`, space, `B` | 3 |
| `"A\s\sB"` | `A`, hai space, `B` | 4 |
| `"A\tB"` | `A`, tab, `B` | 3 |
| `"A\nB"` | `A`, newline LF, `B` | 3 |
| `"A\\sB"` | `A`, ký tự backslash, chữ `s`, `B` | 4 |

Trong bảng, số ký tự được nói tới là số **đơn vị UTF-16** mà `String.length()` trả về cho các ví dụ ASCII. `\s` không tạo mã điều khiển hoặc dấu cách “ẩn” có thuộc tính riêng; nó tạo space bình thường.

## 2. Vì sao cần `\s` trong text block?

Text block cho phép viết chuỗi nhiều dòng dễ đọc hơn các string literal nối bằng `+`. Tuy nhiên compiler cố tình loại bỏ **incidental whitespace**, gồm phần thụt lề chung và **khoảng trắng cuối dòng**. Nếu cần bảo toàn các dấu cách ở cuối dòng vì căn cột, định dạng cố định hoặc dữ liệu chính xác từng ký tự, chỉ gõ các dấu cách vô hình vào mã nguồn có thể không tạo ra chuỗi mong muốn.

Ví dụ text block không cần khoảng trắng cuối dòng:

```java
String plain = """
        red
        green
        blue
        """;
```

Giá trị là `"red\ngreen\nblue\n"`; mỗi dòng văn bản không có space ở cuối. Dấu đóng `"""` trên một dòng riêng làm giá trị có `\n` sau dòng `blue`. Nếu các dấu cách được gõ **thật** ở cuối các dòng trong text block, Java cũng có bước loại bỏ chúng như incidental whitespace.

**Cách làm đúng: đặt `\s` ở cuối dòng cần giữ khoảng trắng**. Vì compiler chưa dịch escape này thành dấu cách tại lúc loại bỏ incidental whitespace, chuỗi `\s` đóng vai trò một **character fence**: các dấu cách đứng ngay trước nó không bị coi là trailing whitespace để loại bỏ.

```java
String colors = """
        red  \s
        green\s
        blue \s
        """;
```

Giá trị được tạo ra (dùng `[sp]` để biểu diễn một dấu cách, `\n` để biểu diễn một LF, chỉ là **ký hiệu minh họa**, không phải giá trị thực):

```text
red[sp][sp][sp]\n
green[sp]\n
blue[sp][sp]\n
```

Diễn giải: ở dòng `red`, **hai space được gõ tường minh** trước escape vẫn còn, rồi `\s` thêm một space thứ ba. `green\s` có một space; `blue \s` có hai space. Các dòng có độ dài trước LF lần lượt là 6, 6 và 6, phù hợp cho dữ liệu có độ rộng cột cố định.

**Nếu chỉ muốn một space:** đặt `\s` ngay sau ký tự cuối. **Nếu muốn ba space:** có thể viết hai dấu cách thực rồi `\s` như trên, hoặc `\s\s\s` để mọi dấu cách đều được thể hiện qua escape. Cách thứ hai tránh việc editor xóa/thay đổi khoảng trắng vô hình ở mã nguồn.

## 3. Thứ tự xử lý: nguyên nhân `\s` giữ được space

Theo Java Language Specification, nội dung **text block** được xử lý theo ba bước theo đúng thứ tự:

1. Chuẩn hóa các line terminator của nội dung thành LF `\n` (bao gồm trường hợp file nguồn dùng CRLF hoặc CR).
2. Loại bỏ *incidental whitespace* như cách mô tả bởi `String.stripIndent()` — thụt lề chung và khoảng trắng cuối dòng không được bảo vệ.
3. Diễn giải escape sequences như cách mô tả bởi `String.translateEscapes()` — lúc này `\s` mới trở thành ký tự SP.

Do bước 2 xảy ra **trước** bước 3, chuỗi ký tự `\s` trong source chưa phải là một space thông thường khi Java tiến hành cắt trailing whitespace. Nó tạo một ranh giới bảo vệ các dấu cách có ý nghĩa đứng trước, sau đó chính nó biến thành một space trong giá trị `String` cuối.

**Hãy phân biệt ba mức:** mã nguồn có cú pháp `\s` → compiler dịch thành U+0020 → `String` runtime chứa **space bình thường**. Một khi đã được tạo thành `String`, dấu cách từ `\s` không khác dấu cách gõ trực tiếp; chẳng hạn `equals()`, `hashCode()`, `charAt()`, `length()` và truyền sang API không thể phân biệt nguồn gốc.

Thứ tự này là quy tắc của text block. Đối với string literal một dòng thông thường, không có bước loại bỏ thụt lề chung như text block; `\s` vẫn hợp lệ và tạo một space, nhưng thường chỉ cần gõ dấu cách trực tiếp nếu nó không nằm ở chỗ dễ bị lược bỏ.

## 4. Đặt `\s` ở đâu và đặt dấu đóng `"""` thế nào?

### 4.1. Dòng có newline ở cuối

```java
String s = """
        X\s
        """;
```

Giá trị của `s` là `"X \n"`: một `X`, một space, rồi một LF. Dấu `\s` **không xóa LF**; nó chỉ tạo space ngay trước LF.

### 4.2. Dòng cuối không cần newline

```java
String s = """
        X\s""";
```

Giá trị là `"X "`: vẫn có space nhưng không có LF ở cuối, bởi dấu đóng cùng dòng nội dung. Nên chọn vị trí dấu đóng theo hợp đồng dữ liệu: API đòi `"X "` hay `"X \n"` là hai chuỗi khác nhau.

### 4.3. Nhiều dấu cách và dòng rỗng có ý nghĩa

```java
String twoSpaces = """
        X\s\s
        """;

String blankWithSpace = """
        \s
        """;
```

`twoSpaces` là `"X  \n"`, còn `blankWithSpace` là `" \n"` — dòng nhìn như trống nhưng thực ra có **một** space trước LF. Dùng cách này có chủ đích khi định dạng dữ liệu yêu cầu, không nên thêm space cuối dòng vào văn bản thông thường nếu không cần.

### 4.4. `\s` khác line continuation `\` ở cuối dòng

```java
String joined = """
        A\
        B\s
        """;
```

Giá trị của `joined` là `"AB \n"`: dấu backslash đứng ngay trước kết thúc dòng sau `A` dùng **line continuation** để bỏ newline giữa `A` và `B`, trong khi `\s` sau `B` thêm một space trước LF cuối. Không nhầm chúng: `\s` giữ/tạo dấu cách, còn backslash + line terminator nối dòng bằng cách bỏ line terminator.

## 5. `\s` trong string literal, char literal và regex là những vấn đề khác nhau

**Trong Java string literal:** `"A\sB"` đã biên dịch thành chuỗi `"A B"`; hai cách viết bằng nhau theo `String.equals()`.

**Trong Java char literal:** `'\s'` là một ký tự `char` mang mã 32. Nếu cần so sánh với dấu cách, `'\s' == ' '` trả `true`.

**Trong regex:** ký hiệu `\s` là một *metacharacter của biểu thức chính quy*, thường đại diện một lớp whitespace. Nhưng trước khi regex engine nhận chuỗi, **Java compiler đã xử lý string literal**. Do đó mã Java dùng để truyền regex whitespace là:

```java
String regexWhitespace = "\\s+";
String regexOnlySpace = "\s+";
```

- `regexWhitespace` ở runtime chứa ba ký tự: backslash, `s`, `+`; engine `Pattern` hiểu đó là `\s+` (một hoặc nhiều ký tự whitespace theo quy tắc regex).
- `regexOnlySpace` ở runtime chứa **space** và dấu `+`; engine hiểu đó là ` +` (một hoặc nhiều space U+0020), **không phải** lớp whitespace.
- Vì vậy `Pattern.compile(regexWhitespace).matcher("\t ").matches()` là `true`, còn matcher tương tự với `regexOnlySpace` là `false`. Tab không phải space U+0020.

Nếu cần đưa chính chuỗi ký tự backslash và chữ `s` vào kết quả `String`, dùng `"\\s"`, không dùng `"\s"`. Việc Java compile code khác với việc đọc dữ liệu runtime: một `String` nhận từ tệp chứa hai ký tự `\` và `s` không tự chuyển thành space; muốn diễn giải các escape được nhận từ bên ngoài cần một bước xử lý rõ ràng, không nên dịch một cách tùy tiện.

## 6. `\s` khác `\040`, `\u0020` và tab

JLS còn hỗ trợ octal escape `\040` để biểu diễn space. Trong text block, octal escape cũng được xử lý ở giai đoạn escape translation nên có thể bảo vệ khoảng trắng cuối dòng. Tuy nhiên `\s` **ngắn và diễn đạt mục đích giữ space rõ hơn**, nên ưu tiên cách viết này khi code yêu cầu dấu cách cuối dòng.

Không nên thay `\s` bằng **Unicode escape trong Java source** `\u0020` để dựng character fence: Java xử lý Unicode escape từ rất sớm, **trước** khi phân tích token và xử lý incidental whitespace của text block. Vì vậy nó trở thành space gõ trực tiếp và có thể bị strip ở cuối dòng; `\s` không gặp vấn đề đó.

Phân biệt thêm:

| Mã nguồn Java | Ý nghĩa | Có phải space ASCII U+0020? |
|---|---|---|
| `\s` | Đúng một space; hữu ích bảo toàn trailing space trong text block | **Có** |
| `\040` | Octal escape của space, tương đương một ký tự | **Có** |
| `\t` | Horizontal tab U+0009 | Không |
| `\n` | Line feed U+000A | Không |
| `\r` | Carriage return U+000D | Không |
| `\u0020` viết ở Java source | Unicode escape biến thành space ở giai đoạn đọc source | Có, nhưng **không phải fence đáng tin** cho trailing whitespace |
| `"\\s"` | String chứa hai ký tự backslash và `s`, thường dùng để truyền regex | Không |

Trong mã giao tiếp với file hoặc giao thức, cần xác định **độ chính xác từng byte**, encoding và line ending. `\s` chỉ giải quyết ký tự **space trong chuỗi**; nó không tự thiết lập UTF-8, không ngăn `String.strip()` hoặc serializer khác xóa whitespace về sau.

## 7. Chương trình Java 17+ hoàn chỉnh và đầu ra đã kiểm tra

Tạo tệp **`SpaceEscapeDemo.java`** dưới đây. Để nhìn thấy ký tự vô hình, hàm `show()` thay mỗi space bằng `[sp]` và mỗi LF bằng đúng hai ký tự backslash + `n` khi in. Các ký hiệu này chỉ phục vụ việc hiển thị, không thay đổi nội dung gốc trước khi truyền vào `show()`.

```java
public class SpaceEscapeDemo {
    static String show(String s) {
        return s.replace(" ", "[sp]").replace("\n", "\\n");
    }
    public static void main(String[] args) {
        String ordinary = "red\sblue";
        String equivalent = "red blue";
        char ch = '\s';
        String trimmed = """
                red
                green
                blue
                """;
        String kept = """
                red  \s
                green\s
                blue \s
                """;
        String two = """
                x\s\s
                """;
        String joined = """
                A\
                B\s
                """;
        String regexWhitespace = "\\s+";
        String regexOnlySpace = "\s+";
        System.out.println("literalEqual=" + ordinary.equals(equivalent));
        System.out.println("spaceCode=" + (int) ch);
        System.out.println("ordinary=" + show(ordinary));
        System.out.println("trimmed=" + show(trimmed));
        System.out.println("kept=" + show(kept));
        System.out.println("keptLines=" + kept.lines().count());
        System.out.println("firstLength=" + kept.lines().findFirst().orElseThrow().length());
        System.out.println("two=" + show(two));
        System.out.println("joined=" + show(joined));
        System.out.println("regexWhitespace=" + java.util.regex.Pattern.compile(regexWhitespace).matcher("\t ").matches());
        System.out.println("regexOnlySpace=" + java.util.regex.Pattern.compile(regexOnlySpace).matcher("\t ").matches());
        System.out.println("endsWithSpaceLF=" + kept.endsWith(" \n"));
        System.out.println("sameType=" + (kept.getClass() == String.class));
    }
}
```

Biên dịch và chạy (JDK 17+):

```bash
javac -encoding UTF-8 SpaceEscapeDemo.java
java SpaceEscapeDemo
```

**Stdout chính xác:**

```text
literalEqual=true
spaceCode=32
ordinary=red[sp]blue
trimmed=red\ngreen\nblue\n
kept=red[sp][sp][sp]\ngreen[sp]\nblue[sp][sp]\n
keptLines=3
firstLength=6
two=x[sp][sp]\n
joined=AB[sp]\n
regexWhitespace=true
regexOnlySpace=false
endsWithSpaceLF=true
sameType=true
```

**Đọc kết quả:** `literalEqual=true` cho thấy escape `\s` không tạo một kiểu dữ liệu mới; `spaceCode=32` xác nhận ký tự space. `trimmed` không có space cuối dòng; `kept` giữ tương ứng 3, 1 và 2 space trước mỗi LF; `keptLines=3` và `firstLength=6` khớp cấu trúc dữ liệu.

`two` chứng minh viết `\s\s` để tạo chính xác hai space; `joined` chứng minh line continuation và `\s` làm hai việc khác nhau. Hai kết quả regex phân biệt Java `"\\s+"` với `"\s+"`, và `sameType=true` xác nhận text block vẫn tạo `String`.

## 8. Lỗi phổ biến và cách tránh

| Lỗi / triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Muốn một space cuối dòng nhưng text block không giữ | Java loại incidental trailing whitespace trước khi dịch escape | Đặt `\s` ngay trước newline; cần nhiều dấu cách thì thêm space trước fence hoặc viết nhiều `\s` |
| Sau khi thêm `\s` vẫn thừa hoặc thiếu một space | `\s` **cũng tự tạo** một space, không chỉ bảo vệ space đứng trước | Đếm cả space gõ tường minh và space sinh từ từng `\s` |
| Đầu ra có LF cuối dù chỉ muốn space cuối | Dấu đóng `"""` nằm trên một dòng riêng | Đặt dấu đóng cùng dòng nội dung cuối nếu không muốn LF cuối |
| Mong `\s` đại diện cả tab và newline | Nhầm Java escape với lớp whitespace của regex | `\s` của Java là đúng một U+0020; dùng `\t`/`\n` cho ký tự khác |
| Regex `"\s+"` không khớp tab | Java đã dịch `\s` thành space trước khi `Pattern` xử lý | Với regex whitespace, ghi `"\\s+"` ở Java source |
| Hiển thị không cho thấy space cuối | Space là ký tự khó quan sát ở terminal/IDE | Dùng hàm show, `length()`, `charAt()` và test `endsWith(" \n")` |
| `\u0020` không bảo vệ trailing space | Unicode escape được xử lý trước text-block whitespace stripping | Dùng `\s` hoặc octal `\040` |
| `trim()` / `stripTrailing()` làm mất các space đã giữ | Xử lý chuỗi ở runtime xóa khoảng trắng | Không gọi strip khi space là dữ liệu có nghĩa; kiểm tra hợp đồng của API tiếp nhận |
| Dùng `\s` trong mã phải chạy với Java quá cũ | Cú pháp escape này thuộc Java hiện đại từ Java 15 | Biên dịch với JDK 17+ như hướng dẫn; không dùng thiết lập Java 14 preview |

## 9. Thực hành an toàn khi khoảng trắng có ý nghĩa

1. **Định nghĩa chính xác giá trị mong muốn:** dòng có bao nhiêu space, có LF ở cuối hay không? Viết mẫu kỳ vọng bằng literal như `"A  \n"` khi review hoặc kiểm thử.
2. **Ưu tiên thể hiện space cuối dòng rõ ràng:** `\s` giúp người đọc thấy số khoảng trắng quan trọng trong mã nguồn và tránh editor tự xóa dấu cách cuối dòng.
3. **Đếm cả space trước `\s`:** `red  \s` tạo ba dấu cách, không phải một; đừng thêm `\s` vào cuối dòng mà quên các dấu cách đã có.
4. **Không lạm dụng trailing spaces:** nhiều giao thức chuẩn hóa whitespace; chỉ giữ nếu tài liệu định dạng yêu cầu, ví dụ dữ liệu fixed-width hoặc snapshots.
5. **Viết test theo nội dung thay vì hình thức:** so `equals()` với chuỗi kỳ vọng; có thể dùng `length()`, `lines()`, `endsWith(" \n")`, hoặc hiển thị bằng `[sp]` như chương trình.
6. **Phân biệt với regex và xử lý input:** Java source `"\s"` khác runtime regex `\s`; nếu chuyển chuỗi qua JSON, SQL hoặc parser, kiểm tra escaping của từng lớp.
7. **Giữ tính tương thích:** code dùng `\s` nên nhắm tới JDK 17+ hoặc Java 15+ chính thức, không dựa vào cơ chế preview/legacy.

## Tài liệu chính thức

- Java Language Specification, §3.10.6 *Text Blocks*: https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6
- Java Language Specification, §3.10.7 *Escape Sequences* (`\s` là SP U+0020): https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.7
- Oracle, *Programmer's Guide to Text Blocks* — *Trailing White Space*, *Translation of Escape Sequences* và *New Escape Sequences*: https://docs.oracle.com/en/java/javase/15/text-blocks/index.html
- OpenJDK JEP 378, *Text Blocks* — hoàn thiện text blocks trong Java 15: https://openjdk.org/jeps/378
- Java 17 API, `String`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html
