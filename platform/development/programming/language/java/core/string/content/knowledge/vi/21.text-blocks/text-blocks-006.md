# Text block trong Java: dòng cuối có hoặc không có ký tự xuống dòng

Khi dùng **text block** trong Java, dấu xuống dòng cuối cùng có thể là một phần của giá trị String hoặc không. Khác biệt đúng một ký tự này ảnh hưởng đến so sánh chuỗi, xuất file, tạo payload và kiểm thử. Bài này tập trung vào cách quyết định **dòng cuối có hoặc không có ký tự xuống dòng** bằng vị trí dấu đóng và escape của text block trong Java 17+.

## 1. Cú pháp và ý nghĩa của xuống dòng

Text block bắt đầu bằng ba dấu nháy kép liên tiếp (**"""**) theo sau là dấu kết thúc dòng bắt buộc, chứa nội dung nhiều dòng, rồi kết thúc bằng **"""**:

~~~java
String text = """
        first
        second
        """;
~~~

Trong ví dụ này, String có nội dung tương đương:

~~~java
String text = "first\nsecond\n";
~~~

Dấu xuống dòng ngay sau **dấu mở** text block dùng để bắt đầu nội dung, **không xuất hiện** ở đầu giá trị String. Ngược lại, dấu xuống dòng sau dòng nội dung cuối có thể được giữ lại tùy cách đặt dấu đóng.

Quy tắc quan trọng:

- Nếu **dấu đóng ở dòng riêng bên dưới dòng cuối**, ký tự xuống dòng giữa nội dung cuối và dấu đóng thuộc về String.
- Nếu **dấu đóng ngay sau ký tự cuối của nội dung** trên cùng dòng, không có xuống dòng cuối do dấu đóng tạo ra.
- Các dấu xuống dòng giữa hai dòng nội dung vẫn được giữ lại.
- Trong text block, Java chuẩn hóa dấu kết thúc dòng của mã nguồn thành LF (**\n**, U+000A), kể cả khi file nguồn lưu với CRLF.
- Text block vẫn trải qua bước loại bỏ phần thụt lề ngẫu nhiên; hãy giữ cách căn lề nhất quán khi so sánh hai biến thể.

Text block được hỗ trợ chính thức từ Java 15, nên Java 17 trở lên có thể biên dịch các ví dụ sau mà không cần bật preview feature.

## 2. Đặt dấu đóng ở dòng riêng: có LF cuối

~~~java
String withFinalLf = """
        first
        second
        """;
~~~

Có **hai ký tự LF**: một giữa **first** và **second**, một sau **second**. Giá trị chính xác là:

~~~text
first\nsecond\n
~~~

Dòng minh họa này dùng hai ký tự hiển thị **\** và **n** để biểu diễn **mỗi LF**; trong String thật, mỗi LF chỉ là **một** ký tự.

~~~java
withFinalLf.equals("first\nsecond\n"); // true
withFinalLf.endsWith("\n");             // true
withFinalLf.length();                   // 13
~~~

Vì **first** có 5 ký tự, **second** có 6 ký tự và có hai LF, tổng độ dài là 13.

## 3. Đặt dấu đóng ngay sau nội dung cuối: không có LF cuối

~~~java
String withoutFinalLf = """
        first
        second""";
~~~

Ở đây dấu đóng đứng sát sau **second**, nên giá trị là:

~~~text
first\nsecond
~~~

Kiểm chứng:

~~~java
withoutFinalLf.equals("first\nsecond"); // true
withoutFinalLf.endsWith("\n");           // false
withoutFinalLf.length();                 // 12
~~~

Hai String trên có cùng các chữ và cùng LF **ở giữa** hai dòng, nhưng không bằng nhau vì biến đầu có thêm LF sau dòng thứ hai.

| Cách viết | String tương đương | LF cuối? |
| --- | --- | --- |
| Dấu đóng ở dòng riêng sau dòng cuối | **"first\nsecond\n"** | Có |
| Dấu đóng sát ký tự cuối của nội dung | **"first\nsecond"** | Không |

**Chú ý:** Việc đưa dấu đóng sang một dòng khác cũng có thể tác động đến quy tắc loại bỏ thụt lề nếu các dòng không căn nhất quán. Các ví dụ trong bài có cùng thụt lề nội dung để sự khác biệt chỉ là một LF cuối.

## 4. Ví dụ Java 17+ hoàn chỉnh

Lưu thành file **TextBlockFinalNewlineDemo.java**:

~~~java
public class TextBlockFinalNewlineDemo {
    public static void main(String[] args) {
        String withLF = """
                first
                second
                """;

        String withoutLF = """
                first
                second""";

        // Dấu '\' nối dòng làm mất LF ở cuối dòng second.
        String continued = """
                first
                second\
                """;

        // Escape '\n' chủ động thêm LF sau second.
        String explicitLF = """
                first
                second\n""";

        show("withLF", withLF);
        show("withoutLF", withoutLF);
        show("continued", continued);
        show("explicitLF", explicitLF);

        System.out.println("withLF equals explicitLF: "
                + withLF.equals(explicitLF));
        System.out.println("withoutLF equals continued: "
                + withoutLF.equals(continued));
    }

    private static void show(String label, String value) {
        String visible = value.replace("\n", "\\n");
        System.out.printf("%s: [%s], length=%d, endsWithLF=%b%n",
                label, visible, value.length(), value.endsWith("\n"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac TextBlockFinalNewlineDemo.java
java TextBlockFinalNewlineDemo
~~~

Stdout:

~~~text
withLF: [first\nsecond\n], length=13, endsWithLF=true
withoutLF: [first\nsecond], length=12, endsWithLF=false
continued: [first\nsecond], length=12, endsWithLF=false
explicitLF: [first\nsecond\n], length=13, endsWithLF=true
withLF equals explicitLF: true
withoutLF equals continued: true
~~~

Hàm **show** đổi LF trong giá trị thành hai ký tự hiển thị **\n** để tiện kiểm tra và in cả **length** lẫn **endsWith**. Phần **%n** trong **printf** là ký tự xuống dòng của thao tác in ra console, **không phải** dấu xuống dòng nằm trong String được kiểm tra.

## 5. Ba cách chủ động kiểm soát dấu xuống dòng cuối

### 5.1. Đổi vị trí dấu đóng

Có LF cuối:

~~~java
String sql = """
        SELECT id
        FROM users
        """;
~~~

Không có LF cuối:

~~~java
String sql = """
        SELECT id
        FROM users""";
~~~

Đây là cách trực tiếp nhất để người đọc nhận ra ý định. Trong trường hợp dấu đóng ngay sau dòng cuối khiến mã kém dễ đọc, có thể dùng escape nối dòng.

### 5.2. Escape nối dòng: dấu gạch chéo ngược ở cuối dòng

Trong text block, dấu **\** đặt **ngay cuối dòng** sẽ loại bỏ dấu xuống dòng của dòng đó:

~~~java
String text = """
        alpha
        omega\
        """;

// Bằng "alpha\nomega" — không có LF cuối.
~~~

Cách này cho phép đặt dấu đóng ở dòng riêng mà vẫn bỏ LF cuối. **Không chèn khoảng trắng sau dấu \** vì escape nối dòng cần dấu gạch chéo ngược đứng sát ký tự xuống dòng thực tế. Editor tự thêm khoảng trắng cuối dòng có thể làm thay đổi hành vi mong muốn.

Escape nối dòng cũng có thể dùng giữa các dòng nội dung để nối chúng mà không sinh LF ở điểm nối; khi đó cần cân nhắc cả thụt lề và khoảng trắng.

### 5.3. Escape LF tường minh

Nếu muốn dấu đóng sát nội dung nhưng vẫn có LF cuối, thêm escape **\n**:

~~~java
String text = """
        alpha
        omega\n""";

// Bằng "alpha\nomega\n" — có LF cuối.
~~~

Escape **\n** của Java đại diện đúng một ký tự LF. Đây không phải cặp ký tự thường gồm dấu gạch chéo ngược và chữ n.

Có thể chọn theo style chung của codebase. Điều cốt yếu là kết quả mong muốn được thể hiện rõ và có test kiểm chứng khi đây là dữ liệu cần khớp chính xác.

## 6. LF cuối, dòng trống cuối và khoảng trắng cuối khác nhau

Xét ba chuỗi:

~~~java
String a = "alpha";
String b = "alpha\n";
String c = "alpha\n\n";
~~~

- **a** không có LF nào.
- **b** có một LF ngay sau **alpha**.
- **c** có hai LF liên tiếp sau **alpha**, nghĩa là có thêm một dòng rỗng sau dòng nội dung.

Biểu diễn b và c bằng text block:

~~~java
String b = """
        alpha
        """;

String c = """
        alpha

        """;
~~~

Dòng hoàn toàn trống trước dấu đóng trong ví dụ c làm giá trị có thêm một LF. Nếu dữ liệu cần chính xác, không tự ý xóa dòng trống cuối chỉ vì nó không có chữ.

**Dấu cách trước LF** cũng là dữ liệu khác với **LF**. Java xử lý thụt lề và khoảng trắng cuối dòng trong quá trình tạo text block. Nếu muốn giữ rõ một dấu cách trước LF, có thể dùng escape **\s** (dấu cách) trong text block:

~~~java
String text = """
        alpha\s
        beta
        """;

// Kết quả tương đương "alpha \nbeta\n".
~~~

Ở đây **\s** là **escape của Java** tạo ra dấu cách; không nhầm với mẫu regex **\\s** trong một Java String.

## 7. Vì sao println có thể gây hiểu lầm?

Lệnh **System.out.print(text)** in đúng dữ liệu vốn có; **System.out.println(text)** còn tự thêm một dấu kết thúc dòng cho lệnh in, tùy nền tảng. Nếu text đã có LF cuối, dùng println sẽ đưa hai lần xuống dòng liên tiếp ra console:

~~~java
String text = """
        hello
        """;

System.out.print(text);    // In "hello" và LF vốn nằm trong text.
System.out.println(text); // In text rồi thêm newline của println.
~~~

Vì vậy chỉ nhìn màn hình console là chưa đủ để kết luận chuỗi có LF cuối hay không. Hãy in **length()**, **endsWith("\n")**, hoặc thay ký tự LF thành hai ký tự hiển thị bằng **replace("\n", "\\n")**.

Khi lưu file văn bản, gửi request body, tính checksum, kiểm tra chữ ký số hoặc so sánh snapshot, một LF cuối có thể làm payload khác về byte. Với định dạng đặt yêu cầu chính xác, phải chọn và giữ nhất quán quy ước newline.

## 8. Kiểm thử và API xử lý dòng dễ che mất LF cuối

Hai chuỗi có cùng các dòng nội dung nhưng khác dấu xuống dòng cuối:

~~~java
String expected = "one\ntwo";
String actual = """
        one
        two
        """;

System.out.println(expected.equals(actual)); // false
System.out.println(actual.endsWith("\n"));     // true
System.out.println(actual.length());          // 8
~~~

Khi cần phát hiện sự khác biệt, không nên chỉ dùng số dòng:

~~~java
String withLF = "one\ntwo\n";
String withoutLF = "one\ntwo";

System.out.println(withLF.lines().count());        // 2
System.out.println(withoutLF.lines().count());     // 2
System.out.println(withLF.split("\n").length);     // 2
System.out.println(withLF.split("\n", -1).length); // 3
~~~

**String.lines()** không phát sinh một dòng rỗng cuối chỉ vì String kết thúc bằng dấu xuống dòng; **split** theo mặc định cũng loại bỏ các phần tử rỗng cuối. Truyền **-1** vào split để giữ chuỗi rỗng cuối. Muốn kiểm tra trực tiếp dấu LF cuối, cách đơn giản nhất vẫn là **endsWith("\n")**.

Ví dụ kiểm thử chính xác nội dung mong muốn:

~~~java
String expected = "line 1\nline 2\n";
String actual = """
        line 1
        line 2
        """;

if (!expected.equals(actual)) {
    throw new AssertionError("Text block không khớp chính xác");
}
~~~

Đoạn trên là mã minh họa điều kiện assert, có thể đặt trong một phương thức Java; chỉ có chương trình ở phần 4 là ví dụ lớp hoàn chỉnh độc lập.

## 9. Bỏ đúng một LF cuối sau khi đã tạo String

Khi cần bỏ **duy nhất một LF cuối**, có thể dùng String API mà không ảnh hưởng các ký tự cuối khác:

~~~java
String raw = """
        first
        second
        """;

String withoutOneFinalLF = raw.endsWith("\n")
        ? raw.substring(0, raw.length() - 1)
        : raw;

// withoutOneFinalLF bằng "first\nsecond".
~~~

Không dùng **stripTrailing()** hay **strip()** để thực hiện yêu cầu này khi khoảng trắng khác phải được giữ, vì những phương thức đó loại bỏ **nhiều ký tự whitespace**:

~~~java
String raw = "alpha  \n";

String onlyLfRemoved = raw.substring(0, raw.length() - 1);
// "alpha  " — hai dấu cách cuối được giữ.

String stripped = raw.stripTrailing();
// "alpha" — bỏ cả hai dấu cách và LF.
~~~

Nếu dữ liệu đến từ ngoài text block và có CRLF, cần xác định quy ước newline trước khi bỏ; ví dụ trên được viết cho dữ liệu text block đã chuẩn hóa LF.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Chuỗi so sánh không bằng nhau dù console trông giống | Một bên có LF cuối, bên kia không | So sánh **length**, **endsWith**, và nội dung escape |
| Thêm một dòng trống khi in ra | Dùng **println** với String vốn đã có LF cuối | Dùng **print** nếu cần in chính xác nội dung |
| Text block không có LF cuối | Đặt dấu đóng sát ký tự nội dung cuối | Đưa dấu đóng xuống dòng riêng hoặc thêm **\n** |
| Text block có LF cuối ngoài dự kiến | Dấu đóng nằm dòng riêng bên dưới | Đặt dấu đóng sát nội dung hoặc dùng nối dòng **\** |
| Đếm dòng vẫn giống nhau | **lines()** và **split** mặc định không giữ dấu hiệu LF cuối | Kiểm tra **endsWith("\n")** |
| Thêm/xóa cả khoảng trắng đầu dòng | Thay đổi vị trí dấu đóng làm thay đổi thụt lề ngẫu nhiên | Căn lề nhất quán và kiểm tra String thực tế |
| Xóa nhiều whitespace hơn dự kiến | Dùng **stripTrailing()** để bỏ một LF | Bỏ đúng một ký tự sau khi kiểm tra **endsWith** |

## 11. Tự kiểm tra

Đoán độ dài và ký tự cuối của hai chuỗi:

~~~java
String x = """
        A
        B
        """;

String y = """
        A
        B""";
~~~

Đáp án:

- **x** bằng **"A\nB\n"**, dài **4**, **endsWith("\n")** là **true**.
- **y** bằng **"A\nB"**, dài **3**, **endsWith("\n")** là **false**.
- **x.equals(y)** là **false** vì chỉ x có một LF cuối.

Khi thiết kế text block, hãy xác định **dữ liệu phải kết thúc bằng LF hay không**, rồi đặt dấu đóng **"""** hoặc dùng escape cho đúng. Ký tự LF cuối là thành phần của String, không chỉ là cách trình bày mã Java.
