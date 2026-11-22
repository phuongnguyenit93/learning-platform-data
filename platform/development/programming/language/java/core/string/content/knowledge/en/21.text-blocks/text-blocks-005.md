# Escape khoảng trắng bằng \s và nối dòng bằng gạch chéo ngược trong Java Text Block

## 1. Bài toán

`Text block` là cú pháp chuỗi nhiều dòng của Java, giới hạn bằng `"""`. Đây là tính năng chính thức từ **Java 15**, nên Java 17 trở lên sử dụng bình thường mà không cần bật preview. Giá trị tạo ra vẫn là một đối tượng `String`. Ví dụ:

~~~java
String s = """
    red
    blue
    """;
System.out.println(s.equals("red\nblue\n")); // true
~~~

Ở đây, xuống dòng vật lý trong text block trở thành LF (`\n`) trong giá trị chuỗi. Dấu đóng `"""` nằm trên dòng riêng nên LF sau `blue` vẫn thuộc kết quả.

Có hai yêu cầu thường gặp khi soạn văn bản nhiều dòng:

1. **Giữ khoảng trắng cuối dòng**: một hoặc nhiều dấu cách ở sau ký tự cuối dòng có thể là dữ liệu quan trọng (chẳng hạn định dạng Markdown).
2. **Trình bày source code thành nhiều dòng nhưng kết quả một dòng**: một câu dài hoặc một phần SQL không nên chứa LF tại điểm tách mã.

Java giải quyết bằng hai escape: **`\s` tạo một dấu cách (U+0020)** và **`\` ở ngay cuối dòng vật lý loại bỏ dấu xuống dòng đó** (line continuation).

## 2. Tại sao các escape này hoạt động?

Java xử lý nội dung text block theo thứ tự:

1. Kết thúc dấu mở `"""` bằng một line terminator bắt buộc; nội dung bắt đầu ở dòng sau. Chuẩn hóa line terminator trong source thành LF.
2. Loại bỏ khoảng trắng thụt lề phụ (`incidental indentation`) để cho phép căn lề đẹp trong file Java. Các dấu cách cuối dòng nguồn không được bảo vệ cũng bị loại (`trailing incidental whitespace`).
3. **Cuối cùng mới** diễn giải escape sequence như `\s`, `\n`, `\t` và dấu `\` nối dòng.

Thứ tự 2 trước 3 là điểm mấu chốt: trong source, `\s` là ký hiệu gồm gạch chéo và chữ `s`, không phải một dấu cách thật để bước xóa trailing whitespace loại bỏ. Sau đó nó trở thành một dấu cách.

### Vị trí dấu đóng quyết định LF cuối

~~~java
String withFinalLf = """
    done
    """;
// Bằng "done\n"

String withoutFinalLf = """
    done""";
// Bằng "done"
~~~

Dấu đóng cùng dòng nội dung cuối không tự tạo LF. Đây là quyết định độc lập với việc dùng `\s` hoặc dấu `\` nối dòng.

## 3. `\s`: giữ dấu cách cuối dòng

### Một dấu cách, không phải mọi whitespace

Trong Java string literal, `\s` tạo **đúng một ASCII space U+0020**, không phải tab, LF hay toàn bộ lớp Unicode whitespace:

~~~java
String a = "Hello\sWorld";
String b = "Hello World";
System.out.println(a.equals(b)); // true
~~~

Escape này sử dụng được trong string literal một dòng và text block. Với text block, nó đặc biệt hữu ích để xác định trailing spaces một cách rõ ràng:

~~~java
String text = """
    A\s
    B\s\s
    """;
~~~

Giá trị `text` chính xác là `"A \nB  \n"`: sau `A` có một dấu cách trước LF; sau `B` có hai dấu cách trước LF. Tổng độ dài là **7** đơn vị UTF-16: A + space + LF + B + space + space + LF.

~~~java
System.out.println(text.equals("A \nB  \n")); // true
System.out.println(text.length());             // 7
System.out.println(text.replace(" ", "<SP>").replace("\n", "\\n"));
// A<SP>\nB<SP><SP>\n
~~~

Ở dòng minh họa cuối, `<SP>` là ký hiệu để **nhìn thấy** dấu cách thật; `\n` được in thành hai ký tự có thể quan sát là `\` và `n`. Cách này chắc chắn hơn việc nhìn kết quả `println` vốn không hiện rõ trailing spaces.

### Vì sao không gõ dấu cách thật ở cuối dòng?

~~~java
String invisibleSpaces = """
    A   
    """;

String explicitSpaces = """
    A\s\s\s
    """;
~~~

Ba dấu cách thật nằm sau `A` ở `invisibleSpaces` bị bước xử lý trailing incidental whitespace loại bỏ. Ở `explicitSpaces`, ba escape `\s` tạo ba dấu cách sau khi bước đó đã diễn ra. Đồng thời, editor tự động xóa trailing whitespace sẽ không phá ý đồ của `explicitSpaces`.

Không nên dùng `\s` cho mọi khoảng trắng thông thường giữa các từ. Dùng nó ở nơi cần nhấn mạnh rằng **dấu cách là một phần có chủ đích của dữ liệu**, nhất là ở cuối dòng hoặc trước điểm nối dòng.

### Đừng nhầm với `\s` trong regex

Hai ký hiệu cùng tên nhưng do **hai bộ phân tích cú pháp khác nhau** xử lý:

| Viết trong mã Java | Chuỗi thật đưa vào regex engine | Ý nghĩa |
| --- | --- | --- |
| `Pattern.compile("\s+")` | ` +` | Một hoặc nhiều **ASCII space**; Java đã chuyển `\s` thành space. |
| `Pattern.compile("\\s+")` | `\s+` | Một hoặc nhiều ký tự thuộc **whitespace class của regex**. |

Ở ví dụ thứ hai, `\\` trong Java source cho ra dấu `\` thật để `Pattern` tiếp tục diễn giải `\s`. Khi xây regex bên trong text block cũng phải phân biệt hai tầng escape như vậy.

## 4. `\` cuối dòng: nối hai dòng mà không có LF ở giữa

### Bỏ line terminator

Một dấu `\` đứng **liền trước line terminator của dòng source** yêu cầu trình biên dịch bỏ line terminator đó khỏi giá trị `String`:

~~~java
String normal = """
    red
    blue
    """;
// Bằng "red\nblue\n"

String joined = """
    red\
    blue
    """;
// Bằng "redblue\n"
~~~

Trong `joined`, gạch chéo ngược cuối dòng `red` cũng không nằm trong kết quả. Dòng thứ hai `blue` nối sát với `red`. LF sau `blue` vẫn còn, vì dòng thứ hai không có dấu nối.

Một chuỗi chia thành ba dòng có thể nối tiếp nhiều lần:

~~~java
String word = """
    con\
    tin\
    ued""";
// Bằng "continued"
~~~

Dùng kỹ thuật này khi muốn xuống dòng trong **mã nguồn** để dễ đọc, nhưng không muốn đưa các LF tương ứng vào **dữ liệu**.

### Nối dòng không chèn dấu cách tự động

~~~java
String sentence = """
    Hello\
    World
    """;
// Bằng "HelloWorld\n"
~~~

Nhiều người tưởng Java tự chèn space giữa `Hello` và `World`, nhưng kết quả là một chuỗi dính liền. Nếu cần đúng một dấu cách, phối hợp `\s` và dấu `\`:

~~~java
String sentence = """
    Hello\s\
    World
    """;
// Bằng "Hello World\n"
~~~

Cụm `\s\` ở cuối dòng có hai hành động khác nhau: `\s` tạo một space; `\` loại LF. Đặt `"""` đóng cùng dòng `World` nếu không muốn LF cuối:

~~~java
String sentence = """
    Hello\s\
    World""";
// Bằng "Hello World"
~~~

### Dấu `\` phải đứng sát line terminator

Không để dấu cách hoặc tab **sau** gạch chéo ngược dùng để nối dòng. Nếu có ký tự chen giữa dấu `\` và line terminator, đó không còn là escape nối dòng hợp lệ và có thể gây lỗi biên dịch. Đây cũng là lý do nên tránh editor tự thêm trailing whitespace vào các dòng kết thúc bằng `\`.

Dấu `\\` có ý nghĩa **khác**: nó tạo một gạch chéo ngược **trong kết quả**.

~~~java
String path = """
    C:\\temp\\
    next
    """;
// Giá trị: "C:\\temp\\\nnext\n"
// Dòng đầu kết thúc bằng một dấu \ thật, rồi mới LF.
~~~

Muốn thật sự nối dòng thì dùng dấu `\` đơn độc ở cuối dòng, không dùng `\\`.

## 5. Tác động của thụt lề khi nối dòng

Dấu `\` loại ký tự xuống dòng, nhưng **không đồng nghĩa loại toàn bộ khoảng trắng** ở đầu dòng kế tiếp. Java chỉ loại thụt lề phụ chung:

~~~java
String a = """
    head\
      next
    """;
// Bằng "head  next\n": còn hai dấu cách giữa head và next.

String b = """
    head\
    next
    """;
// Bằng "headnext\n".
~~~

Ví dụ `a` có thêm hai dấu cách ở đầu `next` so với mức thụt lề chung. Chúng được giữ lại và, sau khi bỏ LF bằng `\`, trở thành hai space ở giữa. Để kết quả ổn định, **canh lề phần nối tiếp theo mức chung** nếu không muốn khoảng trắng dư, hoặc dùng `\s\` khi muốn kiểm soát chính xác một space.

Cũng cần phân biệt `\n` trong source (escape **chủ động thêm** LF) với dấu `\` cuối dòng (escape **chủ động bỏ** LF). Chúng là hai thao tác đối nghịch, dù đều thao tác với xuống dòng.

## 6. Chương trình Java 17+ độc lập

Lưu mã nguồn sau dưới tên **`TextBlockWhitespaceDemo.java`**:

~~~java
public class TextBlockWhitespaceDemo {
    public static void main(String[] args) {
        String normal = """
            red
            blue
            """;

        String preserved = """
            A\s
            B\s\s
            """;

        String joined = """
            red\
            blue
            """;

        String withSpace = """
            Xin\s\
            chao
            """;

        String noFinalNewline = """
            done""";

        String relativeIndent = """
            head\
              next
            """;

        System.out.println("normal=" + visible(normal));
        System.out.println("preserved=" + visible(preserved));
        System.out.println("joined=" + visible(joined));
        System.out.println("withSpace=" + visible(withSpace));
        System.out.println("noFinalNewline=" + visible(noFinalNewline));
        System.out.println("relativeIndent=" + visible(relativeIndent));
        System.out.println("preserved.length=" + preserved.length());
        System.out.println("preserved.equals="
                + preserved.equals("A \nB  \n"));
    }

    private static String visible(String s) {
        return s.replace(" ", "<SP>").replace("\n", "\\n");
    }
}
~~~

Biên dịch và chạy ở thư mục chứa file bằng JDK 17+:

~~~bash
javac --release 17 TextBlockWhitespaceDemo.java
java TextBlockWhitespaceDemo
~~~

**Kết quả stdout chính xác:**

~~~text
normal=red\nblue\n
preserved=A<SP>\nB<SP><SP>\n
joined=redblue\n
withSpace=Xin<SP>chao\n
noFinalNewline=done
relativeIndent=head<SP><SP>next\n
preserved.length=7
preserved.equals=true
~~~

Các dòng này dùng hàm `visible` để biến LF thành chữ `\n` và dấu cách thành chữ `<SP>`. Điều đó cho phép xác minh cả **LF ở giữa**, **LF ở cuối**, **số dấu cách** và **khoảng trắng do thụt lề có chủ đích**. Giá trị `preserved.equals=true` kiểm tra trực tiếp nội dung, không dựa vào giao diện terminal.

## 7. So sánh và cách chọn đúng

| Mục đích | Cú pháp nguồn | Giá trị chuỗi |
| --- | --- | --- |
| Giữ LF giữa hai dòng | `red` rồi xuống dòng `blue` trong text block | `red\nblue` |
| Bỏ LF giữa hai dòng | `red\` rồi xuống dòng `blue` | `redblue` |
| Bỏ LF nhưng thêm một dấu cách | `red\s\` rồi xuống dòng `blue` | `red blue` |
| Giữ một space ở cuối dòng | `red\s` rồi xuống dòng | `red \n` |
| Giữ hai space ở cuối dòng | `red\s\s` rồi xuống dòng | `red  \n` |
| Không có LF cuối chuỗi | Đặt `"""` đóng ngay sau nội dung cuối | Không có `\n` cuối |
| Lưu ký tự gạch chéo ngược thật | Dùng `\\` trong source | Một dấu `\` thật |

**Tình huống thực tế:**

- Với **Markdown**, hai dấu cách cuối dòng có thể là ký hiệu xuống dòng cứng (*hard line break*). `\s\s` làm rõ rằng hai space ấy cố ý nằm trước LF.
- Với **SQL hoặc câu văn dài**, nối dòng làm đoạn mã dễ đọc nhưng có thể làm dính token; ví dụ `SELECT\s\` nối với `FROM` tạo `SELECT FROM`, còn chỉ `SELECT\` sẽ tạo `SELECTFROM`.
- Với **giao thức hoặc dữ liệu byte-exact**, cần nhớ LF của text block là `\n`. Nếu tiêu chuẩn yêu cầu CRLF, hãy tạo `\r\n` đúng nơi cần và kiểm tra dữ liệu đã mã hóa, không giả định source xuống dòng theo hệ điều hành sẽ quyết định output.

## 8. Lỗi phổ biến

1. **Đếm khoảng trắng bằng mắt:** terminal khó thể hiện trailing spaces. Dùng `equals(...)`, `length()` hoặc hàm `visible`.
2. **Gõ trailing spaces thật thay vì `\s`:** bước xử lý text block có thể loại chúng. Dùng `\s` để diễn đạt rõ.
3. **Đặt space sau dấu `\` nối dòng:** dấu nối không còn sát line terminator; dễ gây lỗi biên dịch.
4. **Quên dấu cách khi nối:** `\` chỉ loại LF, không tự thêm space. Dùng `\s\` khi cần.
5. **Nhầm regex `\s` và Java `\s`:** nếu muốn mẫu regex trắng khoảng, phải escape thành `"\\s"` trong Java source.
6. **Nhầm `\\` với nối dòng:** `\\` tạo backslash thật và không bỏ LF kế tiếp.
7. **Bỏ qua indentation còn lại sau nối:** phần thụt lề vượt mức chung được giữ, có thể xuất hiện ở giữa câu đã nối.
8. **Quên LF cuối khi dấu đóng đứng trên dòng riêng:** dùng `equals(...)` để xác định chuỗi đích.
9. **Thêm `strip()` hoặc `trim()` để chữa cháy:** hai hàm này có thể xóa whitespace vốn là dữ liệu có chủ đích; xác định nội dung đúng từ source sẽ rõ ràng hơn.

## 9. Bài tập tự kiểm tra

Đoán kết quả trước khi thử chạy:

~~~java
String a = """
    AB\
    CD
    """;
// a.equals("ABCD\n") == true

String b = """
    AB\s\
    CD""";
// b.equals("AB CD") == true

String c = """
    AB\s\s
    CD
    """;
// c.equals("AB  \nCD\n") == true
~~~

Tự sửa ví dụ thứ hai để tạo `"AB  CD"` (hai space và không có LF cuối). Đáp án là dùng `AB\s\s\` ở dòng đầu và dấu đóng `"""` cùng dòng `CD`.

**Ghi nhớ:** `\s` tạo đúng **một space U+0020**; `\` ở cuối dòng **xóa đúng line terminator sau nó**. Các dấu cách do thụt lề tương đối và LF cuối text block vẫn phải xét riêng.

## Tài liệu tham khảo

- [Java Language Specification 17 — §3.10.6 Text Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6): cú pháp và thứ tự xử lý.
- [Java Language Specification 17 — §3.10.7 Escape Sequences](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.7): escape `\s` và line continuation.
- [OpenJDK JEP 378 — Text Blocks](https://openjdk.org/jeps/378): ví dụ về trailing spaces, line terminator, và mục tiêu thiết kế.