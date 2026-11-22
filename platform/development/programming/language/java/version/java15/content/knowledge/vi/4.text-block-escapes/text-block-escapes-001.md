# Dấu nháy kép đơn lẻ, liên tiếp và delimiter trong Java text block

## Mục tiêu

Phân biệt dấu nháy kép nằm **trong nội dung String** và bộ ba dấu nháy kép **đánh dấu ranh giới text block**. Hiểu khi nào một hoặc hai dấu nháy kép được giữ nguyên, vì sao ba dấu liên tiếp phải escape khi chúng là dữ liệu, và cách viết các đoạn mã Java chứa chính delimiter. Đây là cú pháp ổn định từ **Java 15**, tiếp tục dùng được trên các phiên bản hiện hành như **Java 17+**.

## 1. Delimiter mở, delimiter đóng và nội dung

Text block là một cách viết **String literal**. Delimiter mở gồm đúng ba dấu nháy kép, theo sau là dấu xuống dòng; delimiter đóng cũng gồm ba dấu nháy kép.

~~~java
String message = """
        Cô ấy nói: "Xin chào!"
        Hai dấu liền nhau: ""
        """;
~~~

Trong ví dụ, bộ ba dấu nháy sau dấu bằng là **delimiter mở**; bộ ba trước dấu chấm phẩy là **delimiter đóng**. Dấu nháy bao quanh câu nói và cặp dấu nháy ở giữa là **ký tự dữ liệu**, không phải delimiter.

Sau ba dấu nháy mở phải có dấu xuống dòng. Vì vậy, cách viết sau **cố ý sai và không biên dịch**:

~~~java
String wrong = """Xin chào""";
~~~

Dấu xuống dòng sau delimiter mở là phần của cú pháp mở, không tự thêm một dòng rỗng vào đầu giá trị String. Java đồng thời loại bỏ phần thụt lề chung không chủ ý của nội dung text block.

## 2. Một dấu nháy kép: được dùng trực tiếp

Dấu nháy kép đơn lẻ trong text block **không cần escape**. Đây là điểm khác biệt dễ thấy khi so với String literal thường dùng một cặp dấu nháy kép.

~~~java
String quote = """
        Tên sách: "Effective Java".
        Anh ấy nói "OK" rồi rời đi.
        """;
~~~

Hai dấu nháy bao quanh tên sách hoặc chữ OK đều là dữ liệu String. Nếu đặt delimiter đóng trên dòng riêng như trên, mỗi dòng nội dung có dấu xuống dòng cuối; ví dụ này cho một chuỗi kết thúc bằng dấu xuống dòng sau câu thứ hai.

Việc text block giữ dấu nháy làm nội dung JSON, HTML, SQL hay mã nguồn Java dễ đọc hơn. Tuy nhiên, một text block chỉ tạo String: nó không tự xác nhận JSON/HTML hợp lệ, không tự chạy mã Java bên trong và không tự escape dữ liệu động cho định dạng đích.

## 3. Hai dấu nháy kép liên tiếp: vẫn là dữ liệu

Hai dấu nháy kép liền nhau **không tạo thành delimiter**; chúng chỉ là hai ký tự của chuỗi text block.

~~~java
String pairs = """
        Ký hiệu hai nháy: ""
        Có thể chứa cả ""Java"".
        Ví dụ mã: String empty = "";
        """;
~~~

Ở đây, dòng chữ chứa câu lệnh khai báo String rỗng chỉ là **văn bản** được lưu trong biến pairs. Nó không tạo thêm biến empty trong chương trình đang chạy. Cũng cần phân biệt:

- **Ngoài text block**, hai dấu nháy kép là một String literal rỗng của Java.
- **Trong nội dung text block**, hai dấu nháy kép là hai ký tự nháy kép liên tiếp nằm trong một String lớn hơn.

Các dấu nháy kép đơn hoặc thành cặp thường có thể viết trực tiếp, không có lý do phải thêm gạch chéo ngược trước từng dấu.

## 4. Ba dấu nháy kép liên tiếp: cần tránh đóng text block

Khi cần lưu **ba dấu nháy kép liên tiếp** như dữ liệu, nếu viết nguyên cả ba dấu mà không escape, trình biên dịch có thể nhận chúng là **delimiter đóng** của text block đang mở. Khi ấy đoạn mã theo sau không còn nằm trong String và thường gây lỗi cú pháp.

Cách rõ ràng nhất là dùng escape sequence gồm gạch chéo ngược và một dấu nháy kép cho **dấu đầu tiên** của bộ ba:

~~~java
String triple = """
        Ba dấu: \"""
        """;
~~~

Phần dữ liệu sau chữ “Ba dấu:” có ba dấu nháy kép: dấu thứ nhất được viết bằng escape **backslash + nháy kép**, hai dấu sau viết trực tiếp. Khi in String, cả ba đều thành dấu nháy kép thông thường, **không có gạch chéo ngược**.

~~~text
Ba dấu: """
~~~

Escaping xảy ra trong quá trình xử lý String của Java. Escape **backslash + nháy kép** sinh ra đúng một ký tự nháy kép. Đây là lý do có thể dùng nó để tránh nhầm với delimiter.

Nếu văn bản chứa ba dấu nháy kép trong một chú thích, đoạn JSON hoặc đoạn mã Java **nằm trong text block**, chúng vẫn chịu quy tắc này. Dấu nháy không được bảo vệ bởi việc nó “trông giống comment” của ngôn ngữ khác.

## 5. Bốn dấu và nhiều dấu liên tiếp

Với dãy dài hơn ba dấu nháy, cần bảo đảm **không còn một bộ ba dấu nháy chưa escape nằm liền nhau trong phần nội dung**. Có thể escape nhiều hơn một dấu cho dễ đọc.

Ví dụ, để lưu **bốn** dấu nháy kép liền nhau:

~~~java
String four = """
        Bốn dấu: \"\"""
        """;
~~~

Ở dòng dữ liệu, hai dấu đầu được biểu diễn bằng hai escape **backslash + nháy kép**, hai dấu sau viết trực tiếp. Kết quả vẫn là đúng bốn dấu nháy kép nối nhau:

~~~text
Bốn dấu: """"
~~~

Đừng thêm khoảng trắng vào giữa dãy dấu nháy chỉ để chương trình biên dịch: điều đó sẽ làm **thay đổi giá trị String**. Với những dãy rất dài, hãy dùng đủ escape để người đọc đếm được từng dấu và không có một bộ ba dấu chưa escape bị hiểu thành delimiter.

## 6. Nhúng đoạn mã Java có text block trong một text block khác

Tình huống thường gặp khi soạn tài liệu, ví dụ code hoặc tạo mã nguồn là muốn một String chứa chính đoạn Java có text block. Cần escape bộ ba dấu nháy của **đoạn mã được lưu** để chúng không đóng text block **bao ngoài**.

~~~java
String nestedCode = """
        String message = \"""
                Xin chào!
                \""";
        """;
~~~

Nội dung String ở trên chứa một đoạn mã Java tương đương với:

~~~java
String message = """
        Xin chào!
        """;
~~~

Đây **không phải text block lồng nhau ở cấp cú pháp Java**. Trình biên dịch chỉ thấy một text block bên ngoài; các ký tự delimiter của đoạn mã nhúng là dữ liệu. Escape của cả bộ ba mở và bộ ba đóng của đoạn mã nhúng sẽ được chuyển thành ký tự nháy bình thường ở giá trị String. Việc lưu đoạn mã trong String không khiến đoạn mã bên trong tự chạy.

## 7. Vị trí delimiter đóng và dấu xuống dòng cuối

Đối với text block, delimiter đóng trên một dòng riêng thường giúp phân biệt ranh giới dễ nhất. Vị trí dấu đóng cũng quyết định **có dấu xuống dòng ở cuối String hay không**.

~~~java
String withNewline = """
        Hello
        """;
String withoutNewline = """
        Hello""";

System.out.println(withNewline.equals("Hello\n"));  // true
System.out.println(withoutNewline.equals("Hello"));  // true
~~~

Khi đặt dấu đóng sát sau nội dung cùng dòng, đặc biệt nếu nội dung cũng kết thúc bằng dấu nháy kép, một dãy nháy liền nhau rất dễ bị đọc nhầm. Nếu muốn kết quả String có thể so sánh byte/ký tự chính xác, hãy kiểm tra cả vị trí delimiter và ký tự xuống dòng sau khi biên dịch.

**Không dùng Unicode escape để né delimiter.** Ví dụ, Unicode escape chỉ đến dấu nháy kép được xử lý sớm, trước bước Java phân chia token. Muốn tránh bộ ba nháy đóng text block, hãy dùng escape **backslash + nháy kép** thông thường; không dựa vào Unicode escape như giải pháp thay thế.

## 8. Chương trình Java 17+ hoàn chỉnh

Lưu tệp với tên **QuoteTextBlockDemo.java**. Ví dụ này chạy thật với một dấu, hai dấu, ba dấu, bốn dấu nháy kép; đoạn mã có text block được lưu trong String; và dấu xuống dòng cuối.

~~~java
public class QuoteTextBlockDemo {
    public static void main(String[] args) {
        String one = """
                Một dấu: "Java"
                """;
        String two = """
                Hai dấu: ""Java""
                """;
        String three = """
                Ba dấu: \"""
                """;
        String four = """
                Bốn dấu: \"\"""
                """;
        String nestedCode = """
                String message = \"""
                        Xin chào!
                        \""";
                """;

        System.out.print(one);
        System.out.print(two);
        System.out.print(three);
        System.out.print(four);
        System.out.println("Có ba dấu nháy: " + nestedCode.contains("\"\"\""));
        System.out.print(nestedCode);

        String noFinalNewline = """
                Kết thúc bằng dấu nháy: "Java" """;
        System.out.println("Có newline cuối: " + noFinalNewline.endsWith("\n"));
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 QuoteTextBlockDemo.java
java QuoteTextBlockDemo
~~~

Stdout chính xác:

~~~text
Một dấu: "Java"
Hai dấu: ""Java""
Ba dấu: """
Bốn dấu: """"
Có ba dấu nháy: true
String message = """
        Xin chào!
        """;
Có newline cuối: false
~~~

Giải thích: biến one và two không cần escape; three escape một dấu trong cụm ba; four escape hai dấu trong cụm bốn. nestedCode chứa cả bộ ba dấu nháy nên phép kiểm tra contains trả true. Biến noFinalNewline đặt delimiter đóng cùng dòng nội dung nên không có ký tự xuống dòng ở cuối chuỗi.

Chương trình này đã được **biên dịch với tùy chọn Java 17** (javac --release 17) và chạy thành công trên JDK 24; nó không phụ thuộc vào các tính năng Java chưa ổn định.

## 9. Những lỗi thường gặp

1. **Thoát mọi dấu nháy kép một cách máy móc:** trong text block, một và hai nháy liên tiếp thường viết trực tiếp; escape chỉ khi cần ngăn nhận diện delimiter hoặc giúp mã dễ hiểu.
2. **Viết trần bộ ba nháy trong phần dữ liệu:** một bộ ba không escape có thể kết thúc text block sớm. Hãy escape ít nhất một dấu trong cụm.
3. **Tưởng gạch chéo ngược vẫn còn ở giá trị String:** escape tạo ký tự nháy kép, không giữ dấu gạch chéo ngược. Nếu cần ký tự gạch chéo ngược thực sự, hãy cân nhắc escape cho chính dấu đó.
4. **Cho rằng mã Java chứa text block bên trong String được thực thi:** mã nhúng chỉ là văn bản; text block bên ngoài vẫn cần escape các bộ ba nháy của văn bản.
5. **Đặt nội dung ngay sau delimiter mở:** text block yêu cầu xuống dòng sau phần mở; một chuỗi một dòng ngắn thường nên dùng String literal thông thường.
6. **Không tính đến newline cuối và thụt lề:** khi so sánh chuỗi hoặc tạo tài liệu, phân biệt dấu xuống dòng, khoảng trắng bị loại bỏ và dấu nháy thật trong nội dung.
7. **Chèn dữ liệu không tin cậy trực tiếp vào JSON/HTML/SQL:** text block không làm dữ liệu động trở nên an toàn; dùng API tạo định dạng hoặc truy vấn tham số hóa tương ứng.

## 10. Ghi nhớ cách phân biệt

- Một dấu nháy kép trong nội dung: **viết trực tiếp**.
- Hai dấu nháy kép liên tiếp trong nội dung: **viết trực tiếp**.
- Ba dấu nháy kép cần lưu thành dữ liệu: **escape dấu đầu** của cụm ba.
- Bốn dấu nháy kép cần lưu thành dữ liệu: có thể **escape hai dấu đầu**.
- Bộ ba dấu nháy ở đầu literal kèm dấu xuống dòng là **delimiter mở**; bộ ba thích hợp kết thúc nội dung là **delimiter đóng**.
- Khi nhúng mã nguồn Java có text block, các bộ ba nháy của mã được lưu vẫn là **dữ liệu**, cần escape để không đóng text block ngoài.

Các quy tắc trên là hành vi chuẩn của text block từ Java 15 và vẫn áp dụng cho Java 17 trở lên.

## Tham khảo

- Oracle, *Programmer's Guide to Text Blocks* (Java 17): https://docs.oracle.com/en/java/javase/17/text-blocks/index.html
- Oracle, *Text Blocks* (Java 25): https://docs.oracle.com/en/java/javase/25/language/text-blocks.html
