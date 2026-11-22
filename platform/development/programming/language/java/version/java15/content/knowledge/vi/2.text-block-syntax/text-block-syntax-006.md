# Dùng text block trong biểu thức, tham số và hằng chuỗi (Java 15+)

## Mục tiêu

Biết dùng **text block** khi một biểu thức Java cần chuỗi nhiều dòng, khi truyền chuỗi trực tiếp vào phương thức hoặc hàm tạo, và khi khai báo hằng chuỗi. Các cách dùng dưới đây là cú pháp chính thức từ Java 15 và tiếp tục dùng được trong Java 17 trở lên.

## 1. Text block là gì?

Text block là **literal có kiểu String**: viết nội dung nhiều dòng giữa hai bộ ba dấu nháy kép ("""). Nó có thể xuất hiện ở những vị trí mà một literal chuỗi thông thường xuất hiện. Text block không phải kiểu dữ liệu mới, không phải raw string và không tự thay tên biến bằng giá trị.

Dấu mở """ **phải theo sau bởi dấu xuống dòng**; có thể có khoảng trắng trước dấu xuống dòng. Trình biên dịch chuẩn hóa dấu kết thúc dòng, loại bỏ phần thụt lề chung ngoài ý muốn (incidental indentation) và xử lý escape sequence. Vì vậy, nội dung thực tế có thể khác cách canh lề của mã nguồn.

Ví dụ sau là các câu lệnh đặt trong phương thức, chẳng hạn main:

~~~java
String withFinalNewline = """
        A
        B
        """;
String withoutFinalNewline = """
        A
        B""";

System.out.println(withFinalNewline.equals("A\nB\n")); // true
System.out.println(withoutFinalNewline.equals("A\nB")); // true
~~~

Khi dấu đóng nằm trên **dòng riêng**, ký tự xuống dòng ngay trước dấu đóng trở thành một phần của chuỗi. Khi đặt dấu đóng **ngay sau ký tự cuối**, không tự phát sinh dòng mới ở cuối. Điều này quan trọng với lệnh in, nội dung gửi qua mạng và các phép so sánh chuỗi.

## 2. Dùng text block như một biểu thức

Vì kết quả là String, text block có thể đứng bên phải phép gán, trong nhánh của toán tử điều kiện, trong phép nối chuỗi và trước các lời gọi phương thức String.

- **Gán và chọn nội dung**: mỗi nhánh của biểu thức điều kiện có thể trả về một text block.
- **Nối chuỗi**: dùng toán tử + khi cần ghép với nhãn hoặc một chuỗi khác; giữ đúng dấu xuống dòng ở điểm nối.
- **Biến đổi và định dạng**: gọi các phương thức String như .contains(), .strip(), .replace() hoặc .formatted() trên kết quả của text block.

Ví dụ:

~~~java
boolean detailed = true;
String description = detailed
        ? """
          Chế độ đầy đủ
          Hiện toàn bộ trường dữ liệu.
          """
        : """
          Chế độ ngắn gọn
          """;

String message = """
        Xin chào, %s!
        Bạn có %d thông báo.
        """.formatted("Lan", 3);

String report = "Báo cáo:\n" + description;
~~~

**.formatted(...)** là phương thức String có từ Java 15; trong mẫu trên, %s được thay bằng chuỗi và %d bằng số nguyên khi chạy chương trình. Phương thức này tạo ra chuỗi mới. Text block **không có nội suy biến tự động**: viết tên biến bên trong nội dung chỉ tạo ra các ký tự tương ứng. Khi muốn xuất hiện ký tự phần trăm thực sự trong một chuỗi dùng với .formatted(), cần ghi %%.

## 3. Truyền trực tiếp làm đối số

Một text block có thể được truyền **trực tiếp** cho bất kỳ tham số kiểu String tương thích nào, chẳng hạn phương thức in, phương thức xử lý văn bản hoặc hàm tạo nhận String:

~~~java
System.out.print("""
        Hướng dẫn:
        1. Đăng nhập.
        2. Chọn tài liệu.
        """);
~~~

Không cần tạo biến tạm nếu nội dung chỉ dùng một lần. Khi phương thức nhận đúng một chuỗi, toàn bộ text block là **một đối số String**, bất kể có bao nhiêu dòng. Nếu phương thức in thêm ký tự xuống dòng, hãy cân nhắc text block đã có ký tự xuống dòng cuối hay chưa: dùng print khi không muốn println thêm một dấu xuống dòng nữa.

Nội dung JSON, HTML hoặc SQL tĩnh cũng có thể dùng cách truyền đối số này. Text block chỉ tạo chuỗi; việc phân tích cú pháp, escaping và tính hợp lệ theo định dạng đích vẫn do API nhận chuỗi đảm nhiệm.

## 4. Dùng làm hằng chuỗi

Text block là **string literal**, vì vậy nó là một **biểu thức hằng tại thời điểm biên dịch**. Một biến kiểu String khai báo final và được khởi tạo bằng text block hoặc phép nối các hằng chuỗi có thể là *constant variable* của Java.

~~~java
static final String COMMAND = """
        RUN""";

static final String SQL = """
        SELECT id, name
        FROM users
        WHERE active = ?
        """;
~~~

COMMAND có giá trị chính xác là "RUN" (không có ký tự xuống dòng ở cuối). Nó có thể dùng ở vị trí yêu cầu hằng String tại thời điểm biên dịch, chẳng hạn nhãn case trong switch. SQL giữ các dấu xuống dòng giữa các dòng và cuối chuỗi; dấu ? được dành cho tham số của PreparedStatement nếu dùng JDBC.

**Phân biệt final và hằng tại thời điểm biên dịch:** static final String được khởi tạo bằng một lời gọi như .formatted(...) là tham chiếu không thể gán lại sau khi khởi tạo, nhưng **giá trị đó không phải constant expression**. Vì vậy, nó không dùng được làm nhãn case đòi hằng biên dịch. Chỉ khai báo final không làm một phép tính lúc chạy trở thành hằng biên dịch.

## 5. Ví dụ Java 17+ hoàn chỉnh

Lưu mã dưới đây trong tệp **TextBlockDemo.java**. Chương trình minh họa đồng thời biểu thức điều kiện, lời gọi phương thức nhận đối số String, định dạng chuỗi và hằng String dùng trong switch.

~~~java
public class TextBlockDemo {
    private static final String COMMAND = """
            RUN""";
    private static final String SQL = """
            SELECT id, name
            FROM users
            WHERE active = ?
            """;

    static void show(String text) {
        System.out.print(text);
    }

    public static void main(String[] args) {
        boolean full = true;
        String view = full
                ? """
                  Chế độ: đầy đủ
                  """
                : """
                  Chế độ: gọn
                  """;
        show(view);

        show("""
                Truyền trực tiếp text block.
                """);

        String greeting = """
                Xin chào, %s!
                """.formatted("Lan");
        show(greeting);

        System.out.println("SQL có xuống dòng: " + SQL.contains("\n"));

        switch ("RUN") {
            case COMMAND -> System.out.println("Khớp hằng chuỗi.");
            default -> System.out.println("Không khớp.");
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 TextBlockDemo.java
java TextBlockDemo
~~~

Kết quả stdout:

~~~text
Chế độ: đầy đủ
Truyền trực tiếp text block.
Xin chào, Lan!
SQL có xuống dòng: true
Khớp hằng chuỗi.
~~~

Giải thích: nhánh true của toán tử điều kiện cho chuỗi "Chế độ: đầy đủ" cùng dấu xuống dòng cuối; show in ra nguyên chuỗi đó. Đối số text block tiếp theo được đưa thẳng vào show. Lời gọi .formatted("Lan") điền tên vào mẫu và trả về String. SQL chứa ký tự xuống dòng nên contains("\n") trả true. Cuối cùng, COMMAND là hằng biên dịch mang giá trị "RUN", vì thế nhãn case COMMAND hợp lệ và được chọn. Ví dụ đã được biên dịch và chạy với JDK 24; cú pháp sử dụng cũng hợp lệ trên Java 17.

## 6. Lưu ý thực tế và lỗi thường gặp

1. **Quên ký tự xuống dòng sau dấu mở.** Không thể viết toàn bộ text block trên một dòng theo dạng mở ba nháy rồi đặt nội dung ngay sau đó. Nếu chỉ cần một dòng ngắn, chuỗi nháy kép thông thường thường rõ ràng hơn.
2. **Hiểu sai khoảng trắng và dấu xuống dòng.** Đừng suy từ số dấu cách thụt lề trong trình soạn thảo ra giá trị cuối; Java tự bỏ phần thụt lề chung. Vị trí dấu đóng quyết định dấu xuống dòng cuối. Khi cần kiểm tra chính xác, so sánh với literal có \n như ví dụ ở mục 1.
3. **Tưởng text block là raw string.** Escape như \n, \t, \\ vẫn có ý nghĩa. Có thể dùng \s để giữ một dấu cách cần thiết và dấu \ ở cuối dòng để bỏ dấu xuống dòng liền kề; chỉ dùng khi mục đích hiển thị thật sự yêu cầu. Dấu nháy kép đơn lẻ trong text block thường không cần escape.
4. **Tưởng có nội suy biến.** Text block chứa %s chỉ là mẫu ký tự cho tới khi gọi .formatted(...) hoặc String.format(...). Kết quả định dạng phụ thuộc vào đối số lúc chạy, nên không phải hằng biên dịch.
5. **Nhầm text block với xử lý dữ liệu an toàn.** Với SQL có giá trị từ người dùng, dùng PreparedStatement và gán tham số bằng API tương ứng; không dùng .formatted(...) để chèn trực tiếp đầu vào vào câu SQL. Với JSON/HTML, hãy dùng thư viện encoding/escaping thích hợp cho dữ liệu động.
6. **Thêm hoặc thiếu dấu xuống dòng khi truyền đối số.** Nhiều API coi khoảng trắng là dữ liệu. Kiểm tra nội dung và yêu cầu của API đích trước khi gửi chuỗi, nhất là với giao thức, so khớp chính xác hoặc snapshot test.
7. **Dùng hằng sai ngữ cảnh.** Một text block trực tiếp có thể là hằng String, nhưng kết quả .formatted(), lời gọi phương thức khác hoặc nối với biến runtime không tự trở thành constant expression, kể cả khi giữ trong biến final.

## 7. Cách chọn nhanh

Dùng **text block** khi nội dung vốn có nhiều dòng và giữ nguyên bố cục giúp mã dễ đọc; dùng literal chuỗi thông thường khi chỉ có một dòng ngắn. Dùng trực tiếp trong **biểu thức** để chọn/ghép/biến đổi chuỗi; truyền trực tiếp làm **đối số** nếu chỉ dùng một lần; dùng **static final String** khi cần mẫu nhiều dòng dùng chung. Luôn kiểm tra thụt lề, dấu xuống dòng cuối và sự khác nhau giữa hằng lúc biên dịch với chuỗi sinh ra lúc chạy.