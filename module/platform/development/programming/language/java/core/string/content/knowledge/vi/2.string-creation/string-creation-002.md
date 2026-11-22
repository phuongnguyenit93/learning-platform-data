# Escape dấu nháy, dấu gạch chéo và ký tự điều khiển trong Java

Khi khai báo chuỗi bằng `String` hoặc ký tự bằng `char`, dấu nháy dùng để **đánh dấu ranh giới literal**. Nếu muốn một dấu nháy hoặc ký tự đặc biệt trở thành **dữ liệu bên trong** literal, Java cung cấp *escape sequence* (chuỗi thoát): một dấu gạch chéo ngược `\` theo sau là ký tự có ý nghĩa đặc biệt. Cần phân biệt rõ **cách viết trong mã nguồn** và **giá trị thật lúc chương trình chạy**.

Bài này tập trung vào Java 17 trở lên: nháy kép `"`, nháy đơn `'`, gạch chéo ngược `\` và các ký tự điều khiển như xuống dòng, tab, carriage return.

## 1. Vì sao phải escape?

`String` literal thông thường được bao bởi nháy kép; `char` literal được bao bởi nháy đơn:

```java
String greeting = "Xin chào";
char initial = 'J';
```

Nếu đặt dấu nháy kép trực tiếp vào giữa `String` literal, trình biên dịch hiểu đó là dấu kết thúc chuỗi. Để đưa dấu `"` vào dữ liệu, viết `\"`:

```java
String message = "Cô ấy nói: \"Xin chào!\"";
System.out.println(message); // Cô ấy nói: "Xin chào!"
```

Trong mã nguồn, `\"` gồm hai ký tự được gõ; trong `message` sau khi biên dịch và chạy, phần đó chỉ là **một ký tự nháy kép**. Dấu `\` phục vụ cú pháp escape, không tự xuất hiện trong giá trị trừ khi ta escape chính nó.

## 2. Bảng escape sequence cần biết

| Viết trong Java literal | Ký tự nhận được | Ý nghĩa và lưu ý |
|---|---|---|
| `\"` | `"` | Nháy kép; cần khi nháy kép nằm trong `String` literal. |
| `\'` | `'` | Nháy đơn; cần khi nháy đơn nằm trong `char` literal. |
| `\\` | `\` | Một dấu gạch chéo **ngược** (backslash). |
| `\n` | LF, U+000A | Xuống dòng (*line feed*). |
| `\r` | CR, U+000D | Đưa vị trí về đầu dòng (*carriage return*); cách hiển thị tùy môi trường. |
| `\t` | TAB, U+0009 | Tab ngang; độ rộng hiển thị tùy thiết bị. |
| `\b` | BS, U+0008 | Backspace; có thể ảnh hưởng vị trí con trỏ, không chắc sẽ xóa ký tự đã in. |
| `\f` | FF, U+000C | Form feed; thường dùng cho ngắt trang trong một số định dạng. |
| `\s` | SPACE, U+0020 | Một dấu cách thông thường; hỗ trợ từ Java 15. |
| `\0` | NUL, U+0000 | Ví dụ một escape bát phân; ít dùng khi viết chuỗi hiện đại. |

`\0` thuộc nhóm *octal escapes* (`\0` đến `\377` theo quy tắc chữ số bát phân), có mặt trong Java nhưng không được nhầm với ký tự kết thúc chuỗi kiểu C: `String` của Java không kết thúc tại NUL. Với ký tự điều khiển thông dụng, nên dùng các escape có tên rõ ràng ở trên.

Dấu gạch chéo **xuôi** `/` không phải là ký tự mở đầu escape trong Java: `"a/b"` dùng trực tiếp, không cần `\/`. Trái lại, gạch chéo **ngược** `\` phải được viết `\\` nếu muốn biểu diễn chính nó.

## 3. Nháy kép và nháy đơn: xem đúng loại literal

### Chuỗi `String` dùng nháy kép

```java
String quoted = "Tên sách: \"Effective Java\"";
String contraction = "It's fine";
String alsoValid = "It\'s fine";
```

- Với `String` được bao bằng `"..."`, dấu `"` bên trong cần escape thành `\"`.
- Dấu `'` bên trong `String` **không bắt buộc** escape. Vì thế `"It's fine"` dễ đọc hơn `"It\'s fine"`.
- `\"` và `\'` là cú pháp hợp lệ trong `String`, nhưng chỉ dùng khi giúp tránh nhầm lẫn.

### Ký tự `char` dùng nháy đơn

```java
char apostrophe = '\'';
char quotationMark = '"';
char backslash = '\\';
char tab = '\t';
```

- Để tạo giá trị `char` là dấu nháy đơn, viết `'\''`.
- Nháy kép bên trong `char` không cần escape: `'"'` hợp lệ.
- `char` biểu diễn đúng **một đơn vị UTF-16**; ví dụ `'\n'` là một ký tự điều khiển, còn `'\\'` là một dấu `\`.
- Không thể viết `char bad = '';` hoặc `char bad = ''';`: đó không phải literal ký tự hợp lệ.

Đừng nhầm biểu diễn chuỗi hai ký tự `"\\n"` với ký tự xuống dòng `'\n'`: kiểu dữ liệu và giá trị của chúng khác nhau.

## 4. Gạch chéo ngược và đường dẫn

`\\` trong source code bắt đầu một escape sequence, vì thế `"C:\temp\new"` **không** chứa đường dẫn mong muốn: `\t` trở thành tab và `\n` trở thành xuống dòng.

```java
String windowsPath = "C:\\temp\\new";
String unixPath = "/home/user/data.txt";
String regexDigits = "\\d+";

System.out.println(windowsPath);  // C:\temp\new
System.out.println(unixPath);     // /home/user/data.txt
System.out.println("123".matches(regexDigits)); // true
```

Với regex, có **hai lớp cú pháp**: Java xử lý literal trước, sau đó trình phân tích regex nhận chuỗi. Muốn regex nhận `\d+` (chữ số), cần viết `"\\d+"` trong Java. Viết `"\d+"` là **lỗi biên dịch** vì `\d` không phải Java escape hợp lệ.

Tương tự, các chuỗi `"\q"` hay `"\x41"` không phải Java string literal hợp lệ. Java không cho phép dùng dấu `\` tùy tiện trước ký tự bất kỳ. Một chuỗi có dấu `\` thật, chẳng hạn nội dung `\n` dưới dạng văn bản, được viết bằng `"\\n"`.

> Khi thao tác đường dẫn thực tế, ưu tiên API `java.nio.file.Path` để ghép hoặc phân tích đường dẫn theo hệ điều hành. Ví dụ đường dẫn Windows ở trên chỉ minh họa cách viết *literal*, không khẳng định tệp tồn tại.

## 5. Ký tự điều khiển và chiều dài chuỗi

`"\n"` là một ký tự LF. `"\\n"` là **hai ký tự**: backslash và chữ `n`.

```java
System.out.println("\n".length());     // 1
System.out.println("\\n".length());    // 2
System.out.println("A\tB".length());   // 3
System.out.println("\r\n".length());   // 2
```

`\r\n` là cặp CR + LF được dùng làm dấu xuống dòng ở một số ngữ cảnh; `\n` là LF đơn lẻ. Khi **tạo xuống dòng theo nền tảng**, cân nhắc `System.lineSeparator()`; khi một giao thức hoặc định dạng yêu cầu LF hoặc CRLF cố định, hãy dùng đúng ký tự mà đặc tả đó quy định.

`\t` thường hiển thị giống nhiều dấu cách nhưng **không phải** nhiều dấu cách. `\b`, `\f` và `\r` có thể làm đầu ra terminal thay đổi hoặc khó quan sát; chúng vẫn là những ký tự bên trong chuỗi, kể cả khi không thấy hình dạng trên màn hình.

### Bài chạy hoàn chỉnh: quan sát đúng ký tự được tạo

Lưu vào `EscapeDemo.java`:

```java
public class EscapeDemo {
    public static void main(String[] args) {
        String greeting = "Cô ấy nói: \"Xin chào!\"";
        char apostrophe = '\'';
        String path = "C:\\temp\\notes.txt";
        String control = "A\n\tB\rC\bD\fE";
        String literalBackslashN = "\\n";
        String regex = "\\d+";

        System.out.println(greeting);
        System.out.println(apostrophe);
        System.out.println(path);
        System.out.println("control: " + visible(control));
        System.out.println("literal: " + visible(literalBackslashN));
        System.out.println("LF length: " + "\n".length());
        System.out.println("literal length: " + literalBackslashN.length());
        System.out.println("digits: " + "123".matches(regex));
    }

    private static String visible(String text) {
        StringBuilder result = new StringBuilder();
        for (int i = 0; i < text.length(); i++) {
            switch (text.charAt(i)) {
                case '\\' -> result.append("\\\\");
                case '\n' -> result.append("\\n");
                case '\r' -> result.append("\\r");
                case '\t' -> result.append("\\t");
                case '\b' -> result.append("\\b");
                case '\f' -> result.append("\\f");
                default -> result.append(text.charAt(i));
            }
        }
        return result.toString();
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 EscapeDemo.java
java EscapeDemo
```

Đầu ra:

```text
Cô ấy nói: "Xin chào!"
'
C:\temp\notes.txt
control: A\n\tB\rC\bD\fE
literal: \\n
LF length: 1
literal length: 2
digits: true
```

Hàm `visible` là **công cụ quan sát**: nó đổi những ký tự điều khiển và dấu backslash thật thành cách viết có thể nhìn thấy, nên đầu ra không bị ảnh hưởng bởi cách terminal xử lý backspace hoặc carriage return. Đặc biệt, dòng `literal: \\n` nghĩa là chuỗi đầu vào có **một backslash thật và chữ n**, sau đó hàm `visible` hiển thị backslash đó bằng hai dấu `\\`.

Nếu in `control` trực tiếp, LF/tab/CR/backspace/form feed có thể ảnh hưởng bố cục hiển thị; không nên suy luận chính xác nội dung chuỗi chỉ từ ảnh chụp terminal.

## 6. Unicode escape khác với escape thông thường

Java còn có Unicode escape dạng `\uXXXX`, được xử lý **trước khi** nhận diện token của mã nguồn. Đây là cơ chế khác với các escape `\n`, `\t`, `\\` được phân tích **sau khi** đã nhận diện literal `String` hoặc `char`.

Ví dụ, `String s = "\n";` hợp lệ và chứa một LF; ngược lại, viết `\u000A` trực tiếp giữa dấu nháy có thể tạo xuống dòng trong nguồn quá sớm và làm lỗi cú pháp. Nếu cần ký tự Unicode theo code point lúc chạy, có thể dùng `Character.toString(0x1F600)`; một code point ngoài BMP thường cần hai đơn vị `char`. Bài kế tiếp giải thích toàn bộ thứ tự dịch Unicode và quy tắc backslash của trình biên dịch.

## 7. Text block có làm mất nhu cầu escape không?

Từ Java 15, text block `"""..."""` cho phép viết chuỗi nhiều dòng dễ đọc, tránh việc phải chèn `\n` liên tục. Dấu nháy kép đơn lẻ thường có thể xuất hiện trực tiếp bên trong text block; nhưng **backslash vẫn là ký tự escape**, và các escape như `\t`, `\n` vẫn được xử lý.

```java
String text = """
        Người dùng nói: "Xin chào!"
        Đường dẫn: C:\\temp
        """;
```

Text block trên chứa dấu nháy kép trực tiếp và ký tự xuống dòng thật theo cấu trúc text block; `\\` vẫn cần để tạo backslash cho đường dẫn. Java còn có quy tắc xử lý thụt lề và xuống dòng ở cuối text block; không thể coi mọi khoảng trắng trong source đều được giữ nguyên. Dùng string literal `"..."` cho một dòng ngắn, text block cho nội dung nhiều dòng khi cách trình bày rõ ràng hơn.

## 8. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách sửa |
|---|---|---|
| `String s = "He said "Hi"";` lỗi biên dịch | Dấu `"` bên trong kết thúc literal quá sớm | Viết `"He said \"Hi\""`. |
| `char c = ''';` lỗi | Chưa escape nháy đơn của `char` | Viết `char c = '\'';`. |
| `String s = "C:\Users";` lỗi `illegal escape character` | `\U` không phải Java escape | Viết `"C:\\Users"` hoặc xử lý bằng `Path`. |
| `"C:\temp"` chạy nhưng có tab | `\t` được hiểu là TAB | Viết `"C:\\temp"`. |
| `String s = "\d+";` lỗi | Nhầm escape của regex với Java | Viết `"\\d+"`. |
| In `"\n"` nhưng muốn hiện ký tự `\` và `n` | `\n` tạo xuống dòng thật | Viết `"\\n"`. |
| Ghép `"a" + "\t" + "b"` rồi thấy khoảng cách không đều | TAB tùy vị trí tab stop của nơi hiển thị | Dùng khoảng trắng hoặc định dạng đầu ra rõ ràng nếu cần canh cột. |
| So sánh `"\r\n".length()` với `"\n".length()` | CRLF là hai ký tự; LF là một | Phân biệt rõ chuẩn xuống dòng của dữ liệu. |

Đừng dùng `String.replace("\\n", "\n")` một cách mặc định cho mọi văn bản nhận từ bên ngoài: thao tác đó biến hai ký tự backslash + n thành một dấu xuống dòng, có thể làm đổi dữ liệu người dùng. Chỉ giải mã escape khi định dạng đầu vào **thực sự** xác định có một lớp escape cần giải mã; Java không tự động giải mã ký tự backslash trong dữ liệu nhận lúc chạy.

## 9. Tự kiểm tra

Hãy đoán giá trị thật, sau đó kiểm chứng bằng `length()` hoặc hàm `visible` phía trên:

```java
String a = "\"";
String b = "\\";
String c = "\\t";
String d = "\t";
String e = "a/b";
char f = '\'';
```

- `a` là **một** dấu nháy kép, `a.length() == 1`.
- `b` là **một** dấu backslash, `b.length() == 1`.
- `c` chứa **hai** ký tự (backslash và `t`); `d` chứa **một** tab.
- `e` chứa ba ký tự; dấu `/` không cần escape.
- `f` là giá trị `char` chứa một dấu nháy đơn.

**Ghi nhớ:** Cú pháp `\...` nằm trong **mã nguồn literal** để biểu diễn ký tự dữ liệu. Muốn nhìn thấy backslash thật trong giá trị `String`/`char`, phải viết `\\`; muốn có xuống dòng/tab thật, dùng `\n`/`\t`. Luôn phân biệt cái được gõ trong source, ký tự tồn tại trong bộ nhớ và cách ký tự đó được hiển thị.
