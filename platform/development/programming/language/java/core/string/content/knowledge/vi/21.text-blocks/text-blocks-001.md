# Text block là cú pháp tạo `String` nhiều dòng trong Java

## 1. Text block là gì?

**Text block** là một cách viết **chuỗi ký tự nhiều dòng** trong mã nguồn Java bằng dấu phân cách ba dấu nháy kép (`"""`). Tính năng này trở thành **chính thức từ Java 15** (trước đó được thử nghiệm ở các bản preview). Với Java 17 trở lên, text block dùng được trực tiếp mà không cần bật preview feature.

Thay vì nối nhiều literal bằng toán tử `+` hoặc chèn thủ công `\n`, ta có thể viết văn bản theo bố cục gần với nội dung muốn lưu:

~~~java
String html = """
        <html>
          <body>
            <h1>Xin chào Java</h1>
          </body>
        </html>
        """;
~~~

Biến `html` vẫn có kiểu **`java.lang.String`**, giống chuỗi viết bằng dấu nháy kép thông thường. Text block **không** tạo ra kiểu dữ liệu mới, không biến chuỗi thành đối tượng mutable và không tự phân tích HTML, JSON hay SQL. Đây chỉ là **cú pháp biểu diễn một giá trị `String`** dễ đọc hơn khi văn bản có nhiều dòng.

Cách viết tương đương bằng chuỗi thông thường:

~~~java
String html = "<html>\n"
        + "  <body>\n"
        + "    <h1>Xin chào Java</h1>\n"
        + "  </body>\n"
        + "</html>\n";
~~~

Hai biến `html` ở hai đoạn riêng biệt có cùng nội dung. Dấu `\n` trong ví dụ truyền thống là ký tự xuống dòng; ở text block, các dấu xuống dòng chủ yếu xuất phát trực tiếp từ bố cục nhiều dòng của source code.

## 2. Cú pháp và dấu phân cách

Dạng cơ bản:

~~~java
String message = """
        Dòng thứ nhất
        Dòng thứ hai
        """;
~~~

Các quy tắc cần nhớ:

1. **Dấu mở `"""` phải theo sau bởi dấu kết thúc dòng** (có thể có khoảng trắng giữa dấu mở và cuối dòng). Văn bản thực tế bắt đầu ở dòng kế tiếp.
2. **Dấu đóng `"""` kết thúc text block**. Nó có thể nằm trên một dòng riêng hoặc ngay sau văn bản cuối.
3. **Dấu xuống dòng sau dấu mở không tự được thêm vào đầu chuỗi.** Dòng đầu của nội dung bắt đầu với `Dòng thứ nhất`.
4. **Ký tự xuống dòng ngay trước dấu đóng** sẽ là một phần của chuỗi khi dấu đóng nằm trên dòng riêng. Nếu đóng ngay sau nội dung, không có dấu xuống dòng cuối đó.
5. Khoảng trắng thụt lề chung của các dòng được Java tự xử lý để mã nguồn có thể đặt gọn trong khối lệnh.

Ví dụ về **hai giá trị chuỗi khác nhau**:

~~~java
String withNewline = """
        Hello
        """;

String withoutNewline = """
        Hello""";

System.out.println(withNewline.equals("Hello\n"));     // true
System.out.println(withoutNewline.equals("Hello"));    // true
~~~

Dạng sau là **sai cú pháp Java** vì không xuống dòng sau dấu mở:

~~~java
// Không biên dịch được:
String invalid = """Hello""";
~~~

Đối với một chuỗi chỉ có một dòng, có thể dùng literal `"Hello"` bình thường. Text block hữu ích nhất khi nội dung thực sự dài hoặc nhiều dòng.

## 3. Thụt lề (incidental indentation)

Text block thường nằm bên trong một phương thức nên các dòng source phải thụt vào cho dễ đọc. Java bỏ **phần thụt lề chung không chủ ý**, nhưng giữ phần chênh lệch giữa các dòng:

~~~java
String menu = """
        Món chính
          Món phụ
        """;
System.out.println(menu.equals("Món chính\n  Món phụ\n")); // true
~~~

Dòng `Món phụ` vẫn có hai dấu cách trong giá trị, dù source thụt vào sâu hơn. Khi dấu đóng `"""` ở dòng riêng, vị trí của nó cũng tham gia xác định lượng thụt lề chung; di chuyển dấu đóng về trái có thể giữ thêm khoảng trắng ở đầu nội dung. Khoảng trắng cuối dòng nguồn thường bị bỏ, nhưng escape `\s` cho phép giữ một dấu cách có chủ đích.

Bài **Khoảng trắng thụt lề ngẫu nhiên và vị trí dấu đóng** giải thích cách tính chính xác cùng những trường hợp dùng tab, dòng trống và dấu đóng lệch cột.

## 4. Text block có tự động tạo dấu xuống dòng không?

Text block dùng LF (`\n`) làm ký tự kết thúc dòng trong giá trị, ngay cả khi file source sử dụng CRLF. Dấu xuống dòng bắt buộc **sau dấu mở** không tự tạo một dòng trống đầu chuỗi. Nếu dấu đóng ở dòng riêng, LF trước dấu đóng thuộc về nội dung; nếu đóng sát dòng cuối, LF cuối không xuất hiện:

~~~java
String a = """
        one
        two
        """;
String b = """
        one
        two""";
System.out.println(a.equals("one\ntwo\n")); // true
System.out.println(b.equals("one\ntwo"));   // true
~~~

Muốn chia một câu dài ra nhiều dòng mã nguồn mà không sinh LF tại điểm chia, đặt dấu `\` ở cuối dòng nội dung; đặt `\s` trước dấu nối nếu cần giữ một khoảng trắng. Các bài **Chuẩn hóa kết thúc dòng**, **Escape khoảng trắng và nối dòng**, và **Dòng cuối có hoặc không có ký tự xuống dòng** sẽ kiểm chứng riêng từng quy tắc và những trường hợp biên.

## 5. Dấu nháy kép, escape và tính chất không “raw”

Text block giúp giảm nhu cầu escape các dấu nháy kép trong nội dung:

~~~java
String json = """
        {
          "name": "An",
          "active": true
        }
        """;

System.out.println(json.contains("\"name\": \"An\"")); // true
~~~

Trong text block, `"name"` được viết trực tiếp; không cần đổi thành `\"name\"` như trong literal truyền thống. Tuy nhiên, text block **không phải raw string**: Java vẫn xử lý escape như `\n`, `\t`, `\\`, `\"` và `\s`. Nếu nội dung cần chứa **ba dấu nháy kép liền nhau**, phải escape phù hợp để không bị hiểu là dấu đóng `"""`.

Ví dụ, đường dẫn có gạch chéo ngược phải được viết đúng:

~~~java
String path = """
        C:\\temp\\data.txt
        """;

System.out.println(path.equals("C:\\temp\\data.txt\n")); // true
~~~

Nếu viết `C:\temp\data.txt` trực tiếp trong text block, `\t` có thể trở thành tab và `\d` là escape Java không hợp lệ. Text block giúp viết nhiều dòng, **không miễn trừ quy tắc escape của Java**.

Điều tương tự áp dụng với regex: muốn tạo chuỗi chứa biểu thức chính quy `\d+` thì vẫn phải viết `\\d+` trong text block, chẳng hạn:

~~~java
String regex = """
        \\d+""";
System.out.println(regex.equals("\\d+")); // true
~~~

Dấu đóng cùng dòng với `\\d+` giúp không có ký tự xuống dòng ở cuối regex.

## 6. Chương trình Java 17+ đầy đủ, có thể biên dịch và chạy

Lưu thành file `TextBlockDemo.java`:

~~~java
public class TextBlockDemo {
    public static void main(String[] args) {
        String greeting = """
                Xin chào,
                Java!
                """;

        String withoutEnd = """
                Xin chào,
                Java!""";

        String indented = """
                item
                  detail
                """;

        String joined = """
                Một \
                dòng.
                """;

        String space = """
                A\s
                B
                """;

        String path = """
                C:\\temp\\data.txt
                """;

        String json = """
                {
                  "name": "An",
                  "active": true
                }
                """;

        System.out.println(greeting.equals("Xin chào,\nJava!\n"));
        System.out.println(withoutEnd.equals("Xin chào,\nJava!"));
        System.out.println(indented.equals("item\n  detail\n"));
        System.out.println(joined.equals("Một dòng.\n"));
        System.out.println(space.equals("A \nB\n"));
        System.out.println(path.equals("C:\\temp\\data.txt\n"));
        System.out.println(json.contains("\"name\": \"An\""));
        System.out.println(
                "Xin chào, %s!".formatted("An")
                        .equals("Xin chào, An!"));
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac -encoding UTF-8 TextBlockDemo.java
java TextBlockDemo
~~~

Kết quả `stdout`:

~~~text
true
true
true
true
true
true
true
true
~~~

Tám lần trả về `true` cho thấy: text block có hoặc không có xuống dòng cuối tùy vị trí dấu đóng; thụt lề tương đối được giữ; dấu `\` cuối dòng source nối hai dòng thành một; `\s` giữ dấu cách cuối dòng; `\\` tạo gạch chéo ngược thật; dấu nháy kép trong JSON không cần escape; và `formatted` có thể đưa dữ liệu vào một mẫu `String`.

Các trường hợp trọng tâm trong chương trình đã được biên dịch và đối chiếu trên Java với mức source compatibility Java 17.

## 7. Sử dụng text block trong thực tế

### 7.1. JSON, HTML hoặc XML

Văn bản nhiều dòng có cấu trúc trở nên dễ đọc hơn:

~~~java
String payload = """
        {
          "event": "user.created",
          "id": 101,
          "enabled": true
        }
        """;
~~~

Text block giữ định dạng dễ quan sát nhưng **không kiểm tra cú pháp JSON** và **không tự escape dữ liệu động**. Khi tạo JSON thực tế từ đối tượng hay giá trị người dùng, nên dùng JSON serializer (ví dụ Jackson) để xử lý escape và cấu trúc dữ liệu đúng.

### 7.2. SQL nhiều dòng

~~~java
String sql = """
        SELECT id, name, email
        FROM users
        WHERE status = ?
        ORDER BY name
        """;
~~~

Câu SQL dễ đọc hơn và giữ nguyên dấu `?` làm placeholder cho `PreparedStatement`. Text block **không chống SQL injection**; việc ràng buộc tham số bằng `PreparedStatement` vẫn cần thiết. Không ghép giá trị người dùng thẳng vào SQL chỉ vì đã dùng text block.

### 7.3. Mẫu nội dung có tham số

Text block không hỗ trợ nội suy biến tự động kiểu `${name}` như một số ngôn ngữ khác. Có thể kết hợp với `String.formatted(...)` hoặc `String.format(...)`:

~~~java
String template = """
        Xin chào %s!
        Bạn có %d thông báo mới.
        """;

String result = template.formatted("An", 3);
System.out.print(result);
~~~

Kết quả:

~~~text
Xin chào An!
Bạn có 3 thông báo mới.
~~~

`formatted` sử dụng cú pháp định dạng với `%s`, `%d`…, **không** thay đổi quy tắc escape hay thụt lề của text block. Dữ liệu đưa vào định dạng cần phù hợp với placeholder; dấu `%` literal trong format string phải được viết là `%%`.

### 7.4. Định nghĩa thông báo và dữ liệu thử nghiệm

Text block thuận tiện khi biểu diễn mẫu email, nội dung trợ giúp trên CLI, fixture HTML/JSON, hoặc nhiều dòng kết quả mong đợi trong unit test. Tuy nhiên, trong các bài test so khớp chính xác, nên quyết định rõ có cần dấu `\n` cuối chuỗi, khoảng trắng cuối dòng và ký tự xuống dòng theo nền tảng hay không.

## 8. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế và cách xử lý |
| --- | --- |
| Text block là kiểu dữ liệu mới | Nó vẫn là `String`, immutable như mọi `String` Java khác |
| Dấu mở `"""` có thể cùng dòng với nội dung | Phải có dấu kết thúc dòng sau dấu mở |
| Text block luôn có xuống dòng ở cuối | Phụ thuộc vị trí dấu đóng và cú pháp nối dòng |
| Thụt lề trong source giữ nguyên 100% | Java loại bỏ phần thụt lề chung; dấu đóng cũng ảnh hưởng |
| Text block là raw string | Escape Java vẫn được diễn giải |
| Có thể dùng `\d` hoặc đường dẫn Windows mà không escape | Muốn gạch chéo ngược thật phải viết `\\` trong source |
| Text block tự thay biến bên trong nội dung | Dùng `formatted`, `format` hoặc công cụ template phù hợp |
| JSON, SQL trong text block được xác thực và an toàn | Text block chỉ biểu diễn chuỗi; vẫn cần serializer, validation và parameter binding |
| Text block không phù hợp cho chuỗi một dòng | Vẫn dùng được nhưng literal bình thường thường đơn giản hơn |

## 9. Khi nào nên và không nên dùng?

**Nên dùng** khi cần lưu văn bản có nhiều dòng hoặc nhiều dấu nháy kép: HTML, JSON minh họa, SQL, thông báo, mã nguồn mẫu hay nội dung test. Lợi ích chính là giảm nối chuỗi `+`, giảm `\n` viết tay và tăng khả năng đọc mã.

**Cân nhắc dùng literal thông thường** cho một đoạn rất ngắn không có xuống dòng, hoặc khi cần xem toàn bộ escape ký tự trong một dòng rõ ràng. Với nội dung dài cần thay đổi độc lập mã nguồn, resource file hoặc template engine có thể phù hợp hơn text block.

**Ghi nhớ:** Text block bắt đầu bằng `"""` rồi xuống dòng, trả về một `String` thông thường, tự xử lý thụt lề chung và giữ các quy tắc escape của Java. Vị trí dấu đóng quyết định nhiều đến thụt lề và dấu xuống dòng cuối. Muốn tránh sai lệch, hãy kiểm tra **giá trị chuỗi sau biên dịch**, đặc biệt khi dữ liệu cần so khớp từng ký tự.
