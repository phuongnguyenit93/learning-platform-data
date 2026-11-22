# Chẩn đoán dấu mở, dấu đóng hoặc xuống dòng sai trong Java text block (Java 15+)

Text block là một biểu thức tạo `String` nhiều dòng, viết giữa hai dấu phân cách gồm **ba dấu nháy kép liên tiếp** (`"""`). Khi gặp lỗi, cần phân biệt hai nhóm: **lỗi cú pháp khiến `javac` không biên dịch** và **chuỗi biên dịch được nhưng chứa dấu xuống dòng/khoảng trắng khác dự kiến**. Tính năng này là cú pháp Java chính thức từ Java 15 và vẫn áp dụng trong các JDK hiện hành.

## 1. Nhận diện đúng hai dấu phân cách

Một text block hợp lệ có dạng:

```java
String message = """
        Xin chào
        Java
        """;
```

- **Dấu mở**: đúng ba dấu `"`, có thể theo sau bởi khoảng trắng ngang, nhưng **bắt buộc phải có ký tự kết thúc dòng ngay sau đó**. Nội dung không được viết trên cùng dòng với dấu mở. Ký tự kết thúc dòng sau dấu mở là thành phần cú pháp, **không tự tạo một `\n` ở đầu chuỗi**.
- **Dấu đóng**: đúng ba dấu `"`; có thể ở một dòng riêng hoặc ở cuối dòng nội dung. Không cần xuống dòng sau dấu đóng. Dấu `;` kết thúc câu lệnh gán, không thuộc chuỗi.
- Dấu `"` đơn hoặc cặp `""` **được phép xuất hiện bên trong** text block. Một chuỗi ba dấu nháy kép liên tiếp trong nội dung cần được escape để không bị hiểu là dấu đóng.

Ví dụ trên tạo chuỗi tương đương `"Xin chào\nJava\n"`: có ký tự LF (`\n`) **sau** `Java` vì dấu đóng ở dòng kế tiếp.

## 2. Lỗi dấu mở: thiếu xuống dòng sau ba dấu nháy

**Sai – không biên dịch:**

```java
String title = """Xin chào""";
```

`"""` ngay trước `Xin` chưa tạo dấu mở hợp lệ: trình biên dịch yêu cầu một **line terminator thật** sau dấu mở. Viết `\n` bằng hai ký tự backslash và `n` trên chính dòng mở cũng không đáp ứng quy tắc này; escape chỉ được xử lý khi text block đã hợp lệ.

**Đúng:**

```java
String title = """
        Xin chào""";
```

Giá trị là `"Xin chào"` (không có LF cuối). Nếu chuỗi chỉ có một dòng đơn giản, `String title = "Xin chào";` cũng phù hợp và dễ đọc.

**Cách nhận diện:** Khi `javac` báo lỗi gần `"""` ở dòng khai báo, trước tiên xem giữa ba dấu mở và nội dung có **xuống dòng vật lý** hay không. Đừng sửa dấu đóng trước khi sửa dấu mở.

## 3. Lỗi dấu đóng: thiếu, thừa hoặc bị đóng quá sớm

**Sai – không có dấu đóng ba nháy kép:**

```java
String data = """
        first
        second
        ""; // chỉ hai dấu nháy kép
```

Hai dấu `""` cuối chưa đóng text block. Trình biên dịch có thể tiếp tục đọc các dòng kế tiếp như nội dung cho đến khi gặp ba dấu nháy kép hoặc hết tệp rồi báo lỗi. Hãy xác định cặp dấu phân cách thực tế, không chỉ nhìn vị trí dòng được trình biên dịch gạch chân.

**Đúng:**

```java
String data = """
        first
        second
        """;
```

Vấn đề ngược lại là **ba dấu nháy kép nằm ngay trong nội dung**: chúng có thể bị coi là dấu đóng sớm, khiến phần mã theo sau không còn nằm trong chuỗi. Với một hoặc hai dấu nháy kép, không cần escape:

```java
String quote = """
        Người dùng nói: "OK".
        """;
```

Nếu muốn tạo **chính ba ký tự `"""`** trong giá trị chuỗi, escape **ít nhất một** dấu nháy kép của dãy đó:

```java
String marker = """
        Dấu phân cách là \"""
        """;
```

Giá trị tương đương `"Dấu phân cách là \"\"\"\n"`. Đừng thêm `\` tùy tiện trước dấu đóng thực sự: nó có thể biến một phần dấu đóng thành nội dung và làm text block không kết thúc.

## 4. Lỗi xuống dòng: biên dịch được nhưng chuỗi khác mong đợi

### 4.1. LF cuối chuỗi phụ thuộc vị trí dấu đóng

```java
String withLf = """
        A
        B
        """;

String withoutLf = """
        A
        B""";
```

- `withLf` bằng `"A\nB\n"`: xuống dòng ở cuối `B` nằm **trong** text block vì dấu đóng ở dòng sau.
- `withoutLf` bằng `"A\nB"`: dấu đóng nằm ngay sau `B`, vì vậy **không có LF cuối**.

Đây là nguyên nhân thường gặp khi kiểm tra `equals`, so sánh JSON/text, đọc snapshot hoặc ghi nội dung ra tệp. `println` còn tự in thêm xuống dòng, nên chỉ nhìn kết quả in có thể gây nhầm lẫn.

### 4.2. Dòng trống sau dấu mở là nội dung thật

```java
String value = """

        A
        """;
```

Giá trị là `"\nA\n"`. Dấu xuống dòng bắt buộc **ngay sau** `"""` mở không nằm trong giá trị; **dòng trống tiếp theo** mới tạo LF ở đầu. Nếu xuất hiện LF thừa, hãy kiểm tra có dòng trống thực sự ngay sau dấu mở hay không.

### 4.3. Kết thúc dòng trong mã nguồn được chuẩn hóa thành LF

Bất kể tệp `.java` dùng CRLF (Windows), CR hay LF, ký tự kết thúc dòng **của nội dung text block** được chuẩn hóa thành `\n` (LF). Đừng mặc định text block dùng `System.lineSeparator()`. Nếu một API thực sự cần kết thúc dòng theo hệ điều hành, chuyển đổi có chủ đích ở ranh giới xuất dữ liệu, chẳng hạn `value.replace("\n", System.lineSeparator())` khi nội dung không chứa LF có ý nghĩa khác.

### 4.4. Backslash ngay trước xuống dòng sẽ nối hai dòng

```java
String joined = """
        Alpha\
        Beta""";
```

Giá trị là `"AlphaBeta"`. Dấu `\` ngay trước **line terminator** là cú pháp tiếp dòng, làm mất ký tự xuống dòng đó. Phân biệt rõ:

- Ký tự xuống dòng thật trong nội dung: thường tạo `\n`.
- Escape `\n` (backslash + chữ `n` trong mã nguồn): tạo một LF trong giá trị, sau bước xử lý escape.
- Backslash `\` ngay trước xuống dòng thật: **loại bỏ** xuống dòng tại vị trí đó.
- `\s`: tạo một dấu cách và hữu ích nếu cần giữ dấu cách ở cuối dòng.

### 4.5. Thụt lề và dấu cách cuối dòng bị xử lý

Java loại bỏ **incidental indentation** (phần thụt lề chung) và các khoảng trắng thừa ở cuối dòng trong text block. Khi dấu đóng ở dòng riêng, độ thụt lề của dòng dấu đóng cũng tham gia xác định lề chung.

```java
String plain = """
        text
        """;

String fourSpaces = """
            text
        """;
```

`plain` là `"text\n"`; `fourSpaces` là `"    text\n"` (bốn dấu cách đầu nội dung vẫn còn). Nếu copy code làm đổi khoảng trắng bên trái hoặc lẫn tab với space, chuỗi có thể đổi dù dấu phân cách vẫn hợp lệ. Khi cần giữ dấu cách cuối dòng, viết `\s` tại vị trí cần giữ thay vì dựa vào dấu cách vô hình trong trình soạn thảo:

```java
String trailingSpace = """
        A\s
        """;
```

Giá trị là `"A \n"`: có một dấu cách sau `A`, rồi LF.

## 5. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh và sửa |
|---|---|---|
| Lỗi biên dịch ngay tại `"""` mở | Nội dung đặt cùng dòng với dấu mở; thiếu xuống dòng vật lý | Đưa nội dung xuống dòng tiếp theo; giữ đúng ba dấu nháy kép |
| Lỗi chuỗi chưa kết thúc, thông báo ở cuối tệp | Chưa có dấu đóng `"""`, hoặc đã escape nhầm dấu đóng | Tìm cặp ba dấu nháy kép theo thứ tự từ dấu mở |
| Các dòng Java sau chuỗi báo lỗi cú pháp | Dãy `"""` trong nội dung đóng chuỗi sớm | Escape một dấu trong dãy ba nháy kép cần giữ |
| `equals(...)` trả `false` dù chữ trông giống nhau | Thừa/thiếu LF cuối, LF đầu hoặc khoảng trắng | So sánh `length()`, `endsWith("\n")` và in ký tự điều khiển dạng nhìn thấy |
| Text block có LF dù mã nguồn là CRLF | Java chuẩn hóa line terminator thành LF | So sánh với `"\n"`, chỉ chuyển sang line separator hệ điều hành khi cần |
| Hai dòng bị ghép thành một | Có backslash ngay trước xuống dòng | Xóa dấu tiếp dòng `\` nếu muốn giữ LF |
| Mất dấu cách cuối dòng | Java xóa trailing whitespace | Dùng `\s` khi dấu cách là dữ liệu có ý nghĩa |
| Còn hoặc mất dấu cách đầu dòng | Lề chung và vị trí dấu đóng quyết định thụt lề | Căn chỉnh nội dung/dấu đóng, kiểm tra tab/space; bật `-Xlint:text-blocks` khi phù hợp |

Thông báo của `javac` có thể khác giữa các phiên bản hoặc do lỗi thứ cấp; **vị trí lỗi đầu tiên và cặp dấu phân cách thực tế** đáng tin cậy hơn việc đoán từ một thông báo đơn lẻ.

## 6. Chương trình kiểm chứng tự chạy (Java 17+)

Lưu **đúng tên tệp** `TextBlockCheck.java`. Đây là chương trình độc lập; các đoạn đánh dấu *Sai* phía trên chỉ dùng để nhận diện lỗi và **không** được ghép vào tệp này.

```java
public class TextBlockCheck {
    private static String visible(String value) {
        return value.replace("\\", "\\\\")
                .replace("\r", "\\r")
                .replace("\n", "\\n")
                .replace("\t", "\\t");
    }

    public static void main(String[] args) {
        String withLf = """
                Alpha
                Beta
                """;

        String withoutLf = """
                Alpha
                Beta""";

        String joined = """
                Alpha\
                Beta""";

        String quotes = """
                Marker: \"""
                """;

        System.out.println("withLf=" + visible(withLf));
        System.out.println("withoutLf=" + visible(withoutLf));
        System.out.println("joined=" + visible(joined));
        System.out.println("quotes=" + visible(quotes));
        System.out.println("withLf.endsWithLF=" + withLf.endsWith("\n"));
        System.out.println("withoutLf.endsWithLF=" + withoutLf.endsWith("\n"));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp bằng JDK 17 trở lên:

```bash
javac TextBlockCheck.java
java TextBlockCheck
```

**stdout chính xác:**

```text
withLf=Alpha\nBeta\n
withoutLf=Alpha\nBeta
joined=AlphaBeta
quotes=Marker: """\n
withLf.endsWithLF=true
withoutLf.endsWithLF=false
```

Hàm `visible` chuyển backslash, CR, LF, TAB thành dạng có thể nhìn thấy. Nhờ đó `"A\n"` khác rõ `"A"`; việc `println` tự thêm xuống dòng không còn che lấp ký tự cuối thực sự của chuỗi. Với lỗi thụt lề, có thể kiểm tra thêm `value.length()` hoặc `value.codePoints().toArray()` để thấy các ký tự khoảng trắng.

## 7. Quy trình sửa lỗi trong dự án

1. **Biên dịch trước**: `javac TextBlockCheck.java` hoặc lệnh build của dự án; ưu tiên sửa lỗi cú pháp đầu tiên. Không xử lý lỗi so sánh chuỗi trước khi mã biên dịch.
2. **Rà dấu mở**: đủ ba nháy kép, sau đó là xuống dòng thật; không đặt ký tự nội dung cùng dòng.
3. **Rà dấu đóng**: đủ ba nháy kép, đúng vị trí mong muốn; tìm dãy ba nháy kép trong nội dung và escape nếu cần.
4. **Xác định LF cuối/đầu**: đóng ở dòng riêng hay ngay sau ký tự cuối; có dòng trống sau dấu mở không.
5. **Tìm escape và khoảng trắng**: kiểm tra `\` ở cuối dòng, `\n`, `\s`, thụt lề của dấu đóng, tab lẫn space. Có thể dùng `javac -Xlint:text-blocks TextBlockCheck.java` để nhận cảnh báo liên quan đến khoảng trắng khi trình biên dịch phát hiện.
6. **So sánh giá trị thật**: dùng `visible`, `endsWith("\n")`, `equals` hoặc kiểm thử cụ thể; không đánh giá qua ảnh chụp hoặc mắt thường.
7. **Kiểm tra lại tác động**: nếu chuỗi là JSON, SQL, HTML hoặc nội dung tệp, xác nhận định dạng đích có yêu cầu LF cuối và thụt lề nào. Sửa tại text block theo hợp đồng dữ liệu mong muốn.

**Ghi nhớ:** Dấu mở phải xuống dòng; dấu đóng quyết định LF cuối; ba nháy kép trong nội dung cần escape; và thụt lề/escape có thể làm giá trị thực khác với những gì thấy trên màn hình. Đây là các quy tắc text block vẫn được sử dụng trong Java hiện hành.

Tham khảo chính thức: [Oracle — Text Blocks (Java 25)](https://docs.oracle.com/en/java/javase/25/language/text-blocks.html) và [Java Language Specification §3.10.6 — Text Blocks](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6).
