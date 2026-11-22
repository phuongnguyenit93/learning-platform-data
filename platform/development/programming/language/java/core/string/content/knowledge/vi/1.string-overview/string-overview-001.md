# String là gì và vai trò biểu diễn văn bản trong Java

## 1. String là gì?

**String** là lớp **java.lang.String** dùng để lưu trữ và thao tác với văn bản trong Java. Một giá trị String là một đối tượng biểu diễn **chuỗi các đơn vị mã UTF-16** (UTF-16 code units), ví dụ tên người dùng, thông báo, đường dẫn, dữ liệu văn bản nhận từ API hoặc nội dung cần ghi vào tệp.

~~~java
String greeting = "Xin chào";
String language = "Java";
String sentence = greeting + ", " + language + "!";
~~~

Đây là **đoạn mã minh họa** có thể đặt bên trong một phương thức; biến **sentence** chứa văn bản “Xin chào, Java!”. Lớp String nằm trong gói **java.lang** nên không cần import.

Các đặc điểm nền tảng:

- **Kiểu tham chiếu:** String là một lớp, không phải kiểu nguyên thủy như **int**, **boolean** hay **char**. Biến String có thể tham chiếu đến đối tượng String hoặc có giá trị **null**.
- **Bất biến (immutable):** sau khi một đối tượng String được tạo ra, nội dung của nó không đổi. Các thao tác như **replace**, **concat**, **toUpperCase** hay **strip** trả về giá trị String kết quả; chúng không sửa đối tượng ban đầu.
- **Lớp final:** không thể kế thừa String để thay đổi hành vi của nó.
- **Biểu diễn UTF-16 ở mức API:** nhiều phương thức như **length()**, **charAt()** và **substring()** làm việc theo vị trí đơn vị mã UTF-16. Một ký tự người dùng nhìn thấy trên màn hình không nhất thiết tương ứng đúng một vị trí.
- **Có giá trị rỗng:** chuỗi **""** là một String hợp lệ có độ dài bằng 0. Nó khác **null**, tức không có đối tượng String được tham chiếu.

Vai trò của String là **mô hình dữ liệu văn bản** trong chương trình: nhận và hiển thị dữ liệu nhập, truyền thông điệp giữa các lớp, xử lý định dạng, kết hợp với thư viện I/O, cơ sở dữ liệu, HTTP, JSON và các API xử lý ngôn ngữ. String chỉ là kiểu dữ liệu biểu diễn văn bản; nó không tự xác định bộ mã của tệp hay làm sạch đầu vào.

## 2. Khởi tạo String, literal và string pool

Cách thông dụng nhất là dùng **string literal** trong dấu ngoặc kép:

~~~java
String first = "Java";
String second = "Java";
String third = new String("Java");
~~~

Literal có thể được tái sử dụng qua **string pool** của JVM. Trong ví dụ này, **first** và **second** cùng tham chiếu một đối tượng literal đã intern; **new String("Java")** tạo một đối tượng mới có cùng nội dung. Tuy nhiên, khi kiểm tra **nội dung**, luôn dùng **equals()** thay vì dựa vào địa chỉ đối tượng.

Một số cách hình thành chuỗi khác:

- **Ghép:** **"Xin " + "chào"**, hoặc ghép với biến bằng toán tử **+**.
- **Từ mảng ký tự:** **new String(charArray)** tạo String từ các phần tử của mảng; thay đổi mảng sau đó không sửa String đã tạo.
- **Từ byte:** **new String(bytes, StandardCharsets.UTF_8)** dùng bộ giải mã UTF-8 cụ thể; không xem mỗi byte là một ký tự.
- **Từ giá trị khác:** **String.valueOf(42)** cho ra “42”; **String.valueOf((Object) null)** cho ra chữ “null”, khác với tham chiếu null.
- **Text block (Java 15+):** cú pháp ba dấu ngoặc kép cho văn bản nhiều dòng, phù hợp với JSON, SQL mẫu hoặc thông điệp dài. Các quy tắc xuống dòng và thụt lề của text block cần được tính đến khi so sánh kết quả.

~~~java
String message = """
        Xin chào,
        Java!
        """;
~~~

Đoạn mã text block trên là ví dụ khai báo, không phải chương trình hoàn chỉnh. Nội dung nhận được có dấu xuống dòng ở cuối dòng “Java!” do cách viết literal.

**String.intern()** trả về tham chiếu chuẩn trong pool cho cùng nội dung; đây là cơ chế tối ưu/canonicalize có chủ đích, không phải cách so sánh chuỗi thông thường. Không sử dụng **==** với kỳ vọng mọi chuỗi có cùng văn bản luôn chia sẻ một tham chiếu.

## 3. Bản đồ khái niệm: học đúng trọng tâm

Bài mở đầu này giúp nhìn thấy vai trò của String trong chương trình và thử một ví dụ tổng hợp. Mỗi vấn đề dưới đây có bài riêng để đào sâu, nên ở đây chỉ xác định sự khác nhau cốt yếu:

| Câu hỏi thực tế | Định hướng đầu tiên | Nội dung học sâu |
| --- | --- | --- |
| Một giá trị văn bản khác mảng ký tự ra sao? | `String` bất biến; `char[]` có thể sửa; `CharSequence` là giao diện đọc. | Quan hệ String, char[], CharSequence và đối tượng |
| Hai biến cùng ghi `"Java"` có nhất thiết cùng đối tượng? | Phân biệt tham chiếu với nội dung; dùng `equals()` để so nội dung. | Nội dung chuỗi và biến tham chiếu |
| `null`, `""`, dấu cách và chữ `"null"` có giống nhau không? | Đó là những trạng thái dữ liệu khác nhau; `isEmpty()` không đồng nghĩa `isBlank()`. | Chuỗi rỗng, chuỗi trắng, null |
| Vì sao một lời gọi `replace()` không đổi chuỗi gốc? | Đối tượng String bất biến; phép biến đổi trả về một giá trị String. | Lớp final và tính bất biến |
| Tìm, cắt, so sánh, thay thế hoặc chuyển byte thế nào? | Chọn API theo mục đích và theo đơn vị ký tự/charset. | Các nhóm thao tác String |
| Khi nào dùng StringBuilder/StringBuffer? | Khi cần dựng văn bản theo nhiều bước; xem thêm vấn đề chia sẻ giữa các luồng. | Chọn String, StringBuilder hoặc StringBuffer |

**Ba ranh giới quan trọng:** (1) biến tham chiếu có thể gán lại dù đối tượng String bất biến; (2) `length()` đếm đơn vị mã UTF-16, không luôn bằng số ký tự hiển thị; (3) `String` biểu diễn văn bản, còn tệp/HTTP truyền byte phải có charset phù hợp, thường là UTF-8.

Chẳng hạn `"Java".equals(candidate)` so nội dung và xử lý được `candidate == null`; `"a.b".replace(".", "-")` thay dấu chấm literal, còn `replaceAll` nhận regex. Các lựa chọn ấy sẽ được thực hành có hệ thống ở bài thao tác String.

**Khi ra khỏi bộ nhớ:** đọc/ghi file, JSON, SQL và HTML cần API đúng ngữ cảnh. Charset, serialize, query parameter và escaping không phải chức năng tự động của String. Dữ liệu nhạy cảm trong String cũng không thể chủ động xóa nội dung đối tượng tại chỗ.

## 4. Ví dụ Java 17+ chạy được

Lưu mã sau vào tệp **StringOverviewDemo.java**, bảo đảm tên tệp trùng tên lớp **public**.

~~~java
import java.nio.charset.StandardCharsets;

public class StringOverviewDemo {
    public static void main(String[] args) {
        String raw = "  Xin chào Java  ";
        String cleaned = raw.strip();

        System.out.println(cleaned);
        System.out.println(cleaned.length());
        System.out.println("Java".equals("java"));

        String literal = "Java";
        String copy = new String("Java");
        System.out.println(literal == copy);
        System.out.println(literal.equals(copy));

        String emoji = "😊";
        System.out.println(emoji.length());
        System.out.println(emoji.codePointCount(0, emoji.length()));

        System.out.println("a.b".replace(".", "-"));
        System.out.println("a.b".replaceAll("\\.", "-"));

        byte[] encoded = "Việt".getBytes(StandardCharsets.UTF_8);
        System.out.println(new String(encoded, StandardCharsets.UTF_8));
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 StringOverviewDemo.java
java StringOverviewDemo
~~~

Kết quả stdout (mỗi kết quả một dòng):

~~~text
Xin chào Java
13
false
false
true
2
1
a-b
a-b
Việt
~~~

Giải thích: **strip()** bỏ hai dấu cách hai đầu; độ dài phần còn lại là 13 code unit. Hai chuỗi khác chữ hoa/thường không bằng nhau qua **equals()**. **new String(...)** tạo một đối tượng khác literal dù nội dung bằng nhau. Emoji dùng hai code unit nhưng là một code point. **replace** và **replaceAll** đều thay đúng dấu chấm khi regex được escape. Byte UTF-8 mã hóa rồi giải mã trở về văn bản gốc.

## 5. Tự kiểm tra kiến thức

1. **Vì sao String bất biến nhưng vẫn có thể viết s = s + "!"?** Vì phép gán đổi tham chiếu sang kết quả mới; không sửa đối tượng ban đầu.
2. **Khi nào dùng equals thay cho ==?** Khi cần so nội dung văn bản, bất kể đối tượng được tạo như thế nào.
3. **"".isEmpty() và " ".isBlank() trả về gì?** Cả hai đều **true**, nhưng áp dụng cho hai tình huống khác nhau; **" ".isEmpty()** là **false**.
4. **Vì sao "😊".length() trả về 2?** Emoji này được biểu diễn bằng hai code unit UTF-16, dù chỉ gồm một Unicode code point.
5. **Dùng gì để ghép nhiều nhãn qua vòng lặp?** Thường dùng **StringBuilder**; khi đã có tập các phần tử, **String.join** cũng rất thuận tiện.
6. **Vì sao nên chỉ định StandardCharsets.UTF_8 khi đọc/ghi?** Để encoding nhất quán và không phụ thuộc charset mặc định của hệ thống.

**Ghi nhớ:** String là kiểu dữ liệu trung tâm cho văn bản trong Java, có tính bất biến và API được thiết kế chủ yếu quanh UTF-16. Hiểu đúng sự khác nhau giữa **nội dung và tham chiếu**, **code unit và ký tự hiển thị**, **String và byte đã mã hóa** sẽ giúp tránh phần lớn lỗi xử lý văn bản.