# Dấu mở, dấu đóng và dòng mới đầu tiên của text block trong Java 17

**Chủ đề:** Java 17 → Text block  
**Mục tiêu:** Đọc đúng cú pháp `"""`; hiểu dòng mới bắt buộc sau dấu mở có nằm trong chuỗi hay không; nhận biết việc đặt dấu đóng làm thay đổi ký tự xuống dòng ở cuối chuỗi.

Text block là một dạng **string literal nhiều dòng** của Java. Nó dùng ba dấu nháy kép liên tiếp (`"""`) để mở và đóng, giúp biểu diễn những đoạn văn bản như HTML, JSON, SQL hay thông báo nhiều dòng mà không phải ghép một chuỗi dài từ nhiều literal. Text block đã trở thành tính năng ngôn ngữ **chính thức từ Java 15** (JEP 378), nên Java 17 sử dụng bình thường, **không cần `--enable-preview`**.

Điểm dễ nhầm nằm ở chỗ **dấu mở và dấu đóng không đối xứng về cách đặt dòng**:

- **Dấu mở** phải được theo sau bởi một **line terminator** (sau đó văn bản mới bắt đầu ở dòng tiếp theo).
- **Dấu đóng** có thể nằm trên dòng riêng hoặc cùng dòng với ký tự nội dung cuối cùng.
- **Dòng mới bắt buộc ngay sau dấu mở không được đưa vào giá trị của chuỗi**.
- **Dòng mới ngay trước dấu đóng**, nếu nằm sau một dòng nội dung, **thường là một phần của chuỗi**. Nó quyết định chuỗi có ký tự `\n` ở cuối hay không.

Các ví dụ trong tài liệu dùng cú pháp và API tiêu chuẩn còn áp dụng trong Java 17.

## 1. Cấu trúc tối thiểu của một text block

Ví dụ:

~~~java
String greeting = """
    Xin chào,
    Java 17!
    """;
~~~

Đọc từng phần:

| Phần trong mã nguồn | Vai trò | Có nằm trong giá trị chuỗi? |
| --- | --- | --- |
| `"""` đầu tiên | **Dấu mở** (*opening delimiter*). | Không. |
| Ký tự xuống dòng sau dấu mở | Kết thúc dòng khai báo dấu mở; **bắt buộc theo cú pháp**. | **Không**. |
| `Xin chào,` và `Java 17!` | Các dòng nội dung. | Có. |
| Dấu xuống dòng sau `Xin chào,` | Phân tách hai dòng nội dung. | Có; trong chuỗi là `\n`. |
| Dấu xuống dòng sau `Java 17!` | Dấu xuống dòng trước dòng chứa dấu đóng. | Có; trong chuỗi là `\n`. |
| `"""` cuối | **Dấu đóng** (*closing delimiter*). | Không. |
| Dấu `;` sau dấu đóng | Kết thúc câu lệnh Java. | Không. |

Trong trường hợp trên, sau khi xử lý phần thụt lề chung, giá trị tương đương một string literal thông thường:

~~~java
String greeting = "Xin chào,\nJava 17!\n";
~~~

Điều này dẫn đến hai nguyên tắc quan trọng:

1. Text block không tự thêm một ký tự `\n` **ở đầu** chỉ vì dấu mở nằm trên một dòng riêng.
2. Text block có thể có `\n` **ở cuối** nếu dòng nội dung cuối cùng kết thúc bằng line terminator trước dấu đóng.

> Trong những ví dụ trên, các dấu cách đầu dòng trước nội dung và dấu đóng là **thụt lề trong mã nguồn**. Java 17 tự xử lý phần thụt lề ngẫu nhiên của text block. Vì vậy kết quả được mô tả không chứa bốn dấu cách ở đầu mỗi dòng.

## 2. Dấu mở `"""`: bắt buộc phải xuống dòng

Dạng hợp lệ của opening delimiter là **ba dấu nháy kép liên tiếp**, sau đó có thể có khoảng trắng và phải có **line terminator**. Nội dung text block bắt đầu từ **dòng mã nguồn kế tiếp**.

**Đúng:**

~~~java
String message = """
    Hello, Java 17!
    """;
~~~

**Sai:**

~~~java
// LỖI BIÊN DỊCH: thiếu line terminator sau dấu mở.
// String message = """Hello, Java 17!""";
~~~

**Sai:**

~~~java
// LỖI BIÊN DỊCH: có nội dung văn bản ngay sau dấu mở.
// String message = """Hello,
//     Java 17!""";
~~~

Trong hai ví dụ sai, việc đóng bằng ba dấu nháy kép không cứu được lỗi: **dấu mở chưa hoàn tất đúng cú pháp**. Một text block của Java không phải dấu nháy ba dùng để bao chuỗi một dòng.

### 2.1. Sau dấu mở có thể có khoảng trắng không?

Có. Theo cú pháp Java, sau `"""` mở được phép có khoảng trắng thuộc nhóm *text block white space* trước line terminator. Những khoảng trắng nằm ngay sau dấu mở này **không phải nội dung text block**.

Ví dụ bên dưới hợp lệ; để mã dễ nhìn, thông thường nên đặt dấu mở ở cuối dòng mà không để khoảng trắng thừa:

~~~java
String text = """   
    Hello
    """;
~~~

Ở dòng khai báo `text`, có ba dấu cách nằm sau `"""` rồi mới xuống dòng. Giá trị vẫn là `"Hello\n"`; ba dấu cách ấy không tạo thành tiền tố của chuỗi.

**Khuyến nghị về cách viết:** Đặt dấu mở ở cuối dòng, lập tức xuống dòng, rồi bắt đầu nội dung. Cách này giúp người đọc phân biệt rõ **dòng cú pháp bắt buộc** với **dòng nội dung thực sự**.

## 3. Dòng mới đầu tiên có thuộc về chuỗi không?

**Không.** Line terminator ngay sau dấu mở là một phần bắt buộc của opening delimiter, nên Java không đưa nó vào giá trị string.

Xét:

~~~java
String first = """
    Alpha
    """;
~~~

Sau khi loại phần thụt lề chung, `first` có giá trị:

~~~text
Alpha\n
~~~

Ký tự đầu tiên là `A`, không phải `\n`. Nói cách khác:

~~~java
System.out.println(first.startsWith("A"));  // true
System.out.println(first.startsWith("\n")); // false
System.out.println(first.equals("Alpha\n")); // true
~~~

Nếu chuyển mã nguồn sang dạng sơ đồ:

~~~text
Dòng mã nguồn 1: String first = """  +  [xuống dòng bắt buộc]
                                                   |
                                                   v
                                             KHÔNG nằm trong chuỗi

Dòng mã nguồn 2:     Alpha              +  [xuống dòng nội dung]
                                                   |
                                                   v
                                               "Alpha\n"

Dòng mã nguồn 3:     """                +  [dấu đóng]
~~~

**Lưu ý:** Việc bỏ dòng mới sau dấu mở chỉ xảy ra với **line terminator của opening delimiter**. Nó không có nghĩa Java sẽ bỏ mọi dòng trống ở đầu nội dung.

## 4. Muốn chuỗi bắt đầu bằng ký tự xuống dòng thì làm thế nào?

Để có `\n` thật sự ở đầu chuỗi, hãy **để một dòng nội dung trống sau dòng dấu mở**:

~~~java
String withLeadingNewline = """

    Alpha
    """;
~~~

Ở đây:

1. Dấu mở `"""` và line terminator bắt buộc đứng trên dòng đầu.
2. Dòng tiếp theo **trống**, nhưng có line terminator riêng: dòng trống này đóng góp một `\n` vào chuỗi.
3. Dòng `Alpha` là dòng nội dung tiếp theo.
4. Dấu xuống dòng sau `Alpha` tiếp tục nằm trong chuỗi vì dấu đóng ở dòng sau.

Vậy:

~~~java
System.out.println(
    withLeadingNewline.equals("\nAlpha\n")
); // true
~~~

So sánh trực tiếp:

| Mã nguồn | Giá trị chuỗi |
| --- | --- |
| Dấu mở, xuống dòng, `Alpha`, xuống dòng, dấu đóng | `"Alpha\n"` |
| Dấu mở, xuống dòng, **một dòng trống**, `Alpha`, xuống dòng, dấu đóng | `"\nAlpha\n"` |

Quy tắc này hữu ích khi viết nội dung cần đúng một dòng trống đầu tiên, chẳng hạn văn bản định dạng sẵn. Với nội dung ứng dụng thông thường, một dòng trống đầu vào dễ gây lỗi so sánh nên hãy thêm nó có chủ đích.

## 5. Dấu đóng `"""` quyết định ký tự mới cuối chuỗi

Khác dấu mở, **dấu đóng không bắt buộc phải ở một dòng riêng**. Trong Java 17, vị trí của closing delimiter là yếu tố quan trọng để xác định kết thúc chuỗi.

### 5.1. Dấu đóng trên dòng riêng: thường có `\n` ở cuối

~~~java
String withFinalNewline = """
    Hello
    """;
~~~

Giá trị là:

~~~java
"Hello\n"
~~~

Tại đây, ký tự xuống dòng **sau chữ `Hello`** thuộc nội dung. Dấu đóng nằm trên dòng tiếp theo nên dòng nội dung đã kết thúc bằng line terminator.

### 5.2. Dấu đóng ở cuối dòng nội dung: không tự thêm `\n`

~~~java
String withoutFinalNewline = """
    Hello""";
~~~

Giá trị là:

~~~java
"Hello"
~~~

Không có line terminator giữa chữ `o` cuối cùng và dấu đóng. Dấu đóng tự nó không thêm ký tự xuống dòng.

### 5.3. Đặt cạnh nhau để quan sát

~~~java
System.out.println(withFinalNewline.equals("Hello\n"));   // true
System.out.println(withoutFinalNewline.equals("Hello"));   // true
System.out.println(withFinalNewline.length());             // 6
System.out.println(withoutFinalNewline.length());          // 5
~~~

Khác biệt chỉ là **một ký tự line feed `\n` cuối chuỗi**, nhưng có thể ảnh hưởng đến tệp xuất, kiểm tra chuỗi chính xác, chữ ký điện tử và định dạng thông báo.

**Đừng hiểu nhầm:** Không phải ba dấu nháy kép “tạo ra” `\n`. Dấu xuống dòng được đưa vào giá trị vì **nó xuất hiện giữa nội dung và dấu đóng**. Đưa dấu đóng lên cùng dòng nội dung làm bỏ đi dấu xuống dòng ấy.

## 6. Dấu đóng có thể kết thúc ngay sau một text block trống

Text block không nhất thiết phải có chữ nào trong nội dung:

~~~java
String empty = """
    """;
~~~

Giá trị của `empty` là **chuỗi rỗng `""`**:

~~~java
System.out.println(empty.isEmpty()); // true
System.out.println(empty.length());  // 0
~~~

Dòng mới sau dấu mở bị bỏ theo quy tắc cú pháp. Dấu đóng đặt ngay ở dòng nội dung đầu tiên nên không có ký tự nội dung nào được thu thập.

Nếu có **một dòng trống thật sự nằm giữa dấu mở và dấu đóng**:

~~~java
String oneNewline = """

    """;
~~~

thì giá trị là **`"\n"`**:

~~~java
System.out.println(oneNewline.equals("\n")); // true
System.out.println(oneNewline.length());     // 1
~~~

Đây là ví dụ rõ nhất để phân biệt **dòng mới bắt buộc của dấu mở** với **dòng trống thuộc nội dung**.

## 7. Dấu đóng trên dòng riêng và xử lý thụt lề

Ngoài việc quyết định ký tự xuống dòng ở cuối, vị trí thụt lề của **dòng chứa dấu đóng** còn tham gia quy tắc xử lý *incidental whitespace* của Java 17.

Ví dụ thông dụng:

~~~java
String text = """
        A
        B
        """;
~~~

Giá trị sau khi Java bỏ phần thụt lề chung:

~~~java
"A\nB\n"
~~~

Nếu dấu đóng được đặt **ít thụt lề hơn**, phần thụt lề còn lại trên nội dung có thể được giữ lại:

~~~java
String indented = """
        A
        B
    """;
~~~

Giá trị tương đương:

~~~java
"    A\n    B\n"
~~~

Ở đây, các dòng `A`, `B` thụt vào tám dấu cách trong source, còn dấu đóng thụt vào bốn dấu cách. Java loại phần thụt lề chung bốn dấu cách; bốn dấu cách còn lại ở trước `A` và `B` là **nội dung có ý nghĩa**.

Vì vậy, khi nói “dấu đóng trên một dòng riêng thì chuỗi kết thúc bằng `\n`”, ta vẫn cần phân biệt **dòng mới cuối** với **khoảng trắng thụt lề**:

- Dòng mới giữa `B` và dấu đóng được giữ thành `\n`.
- Số dấu cách đầu mỗi dòng nội dung phụ thuộc vào mức thụt lề chung và vị trí dấu đóng.
- Dấu đóng không được đưa vào chuỗi, nhưng vị trí của nó có thể ảnh hưởng cách xử lý thụt lề.

Chi tiết này đặc biệt hữu ích khi cần giữ nguyên khoảng trắng đầu dòng của mã nguồn mẫu hoặc những đoạn định dạng như YAML, ASCII art.

## 8. Cách nhìn rõ ký tự xuống dòng khi chạy chương trình

Lệnh `System.out.println(text)` không phải lúc nào cũng giúp người học nhìn rõ sự khác biệt giữa **dòng mới ở cuối chuỗi** và **dòng mới do chính `println` thêm vào**.

Để quan sát, ta có thể thay mỗi ký tự line feed `\n` thành hai ký tự hiển thị là dấu gạch chéo ngược và chữ `n`:

~~~java
static String visible(String text) {
    return text.replace("\n", "\\n");
}
~~~

Ví dụ, `visible("A\nB\n")` trả về chuỗi hiển thị `A\nB\n` (chứa các ký tự `\` và `n` thay cho line feed). Điều này không thay đổi text block gốc; nó chỉ làm kết quả dễ đọc hơn khi in thử.

### Chương trình hoàn chỉnh cho Java 17

Tạo tệp **`TextBlockDelimitersDemo.java`**:

~~~java
public class TextBlockDelimitersDemo {
    private static void show(String label, String value) {
        String visible = value.replace("\n", "\\n");
        System.out.println(
            label + " = [" + visible + "], length=" + value.length()
        );
    }

    public static void main(String[] args) {
        String withFinalNewline = """
            Hello
            """;

        String withoutFinalNewline = """
            Hello""";

        String withLeadingNewline = """

            Hello
            """;

        String empty = """
            """;

        String oneNewline = """

            """;

        show("withFinalNewline", withFinalNewline);
        show("withoutFinalNewline", withoutFinalNewline);
        show("withLeadingNewline", withLeadingNewline);
        show("empty", empty);
        show("oneNewline", oneNewline);
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~shell
javac --release 17 TextBlockDelimitersDemo.java
java TextBlockDelimitersDemo
~~~

Kết quả hiển thị:

~~~text
withFinalNewline = [Hello\n], length=6
withoutFinalNewline = [Hello], length=5
withLeadingNewline = [\nHello\n], length=7
empty = [], length=0
oneNewline = [\n], length=1
~~~

Giải thích:

1. `withFinalNewline`: dòng mới sau dấu mở bị bỏ; dòng mới sau chữ `Hello` được giữ.
2. `withoutFinalNewline`: dấu đóng nằm ngay sau chữ `Hello`, nên không có `\n` cuối.
3. `withLeadingNewline`: dòng trống **sau dòng mở** tạo một `\n` thật ở đầu.
4. `empty`: chỉ có dòng mới bắt buộc sau dấu mở, nên không có ký tự nội dung.
5. `oneNewline`: có thêm một dòng trống thực sự trước dấu đóng, tạo giá trị một ký tự `\n`.

Chương trình chỉ dùng `String.replace`, `String.length` và cú pháp text block chính thức. Không cần API thử nghiệm hay thư viện bên thứ ba.

## 9. Text block trong JSON, SQL và HTML: chú ý dấu xuống dòng

Text block hữu ích cho những nội dung nhiều dòng nhưng cách đặt dấu đóng ảnh hưởng trực tiếp đến giá trị chuỗi.

### 9.1. JSON có newline cuối

~~~java
String json = """
    {
      "name": "Java 17",
      "active": true
    }
    """;
~~~

Giá trị `json` kết thúc bằng `}\n`. Dấu xuống dòng cuối thường không ảnh hưởng cách một trình phân tích JSON hợp lệ đọc dữ liệu, nhưng **so sánh byte/chuỗi chính xác** sẽ phân biệt `"}"` và `"}\n"`.

### 9.2. JSON không có newline cuối

~~~java
String json = """
    {
      "name": "Java 17",
      "active": true
    }""";
~~~

Giá trị kết thúc bằng ký tự `}`, vì dấu đóng nằm ngay sau dấu ngoặc nhọn. Đây là lựa chọn rõ ràng nếu giao diện hoặc định dạng xuất yêu cầu không có newline cuối.

### 9.3. SQL nhiều dòng

~~~java
String query = """
    SELECT id, title
    FROM lessons
    WHERE published = true
    """;
~~~

Với ví dụ này, câu SQL có ký tự xuống dòng sau `true`. Nếu muốn gửi câu SQL không có dòng mới cuối, có thể đặt dấu đóng ngay sau `true`:

~~~java
String query = """
    SELECT id, title
    FROM lessons
    WHERE published = true""";
~~~

Nhiều hệ thống không quan tâm newline cuối trong câu SQL, nhưng cách tạo literal vẫn cần được nắm rõ khi kiểm thử hoặc so sánh giá trị đầu ra.

### 9.4. HTML và văn bản dùng khi xuất tệp

~~~java
String html = """
    <p>Hello</p>
    """;
~~~

Chuỗi `html` có giá trị `"<p>Hello</p>\n"`. Nếu ghi trực tiếp ra tệp bằng `Files.writeString(path, html)`, ký tự xuống dòng cuối **cũng được ghi**. Text block không phải công cụ tự loại bỏ mọi line terminator trước khi lưu.

## 10. Dòng xuống trong source: `LF`, `CRLF` và giá trị Java nhận được

Tệp mã nguồn Java có thể sử dụng ký tự kết thúc dòng khác nhau tùy hệ điều hành hoặc cấu hình editor, phổ biến là:

- `LF` (line feed, `\n`).
- `CRLF` (carriage return + line feed, `\r\n`).

**Java 17 chuẩn hóa line terminator trong nội dung text block thành `LF`**, theo quy tắc xử lý text block. Vì thế:

~~~java
String lines = """
    One
    Two
    """;
~~~

Giá trị tương đương:

~~~java
"One\nTwo\n"
~~~

ngay cả khi tệp nguồn được lưu theo kiểu xuống dòng CRLF. Dòng mới bắt buộc ngay sau dấu mở vẫn không được đưa vào chuỗi.

**Không nên đồng nhất line separator của hệ điều hành với text block.** `System.lineSeparator()` có thể trả `"\r\n"` trên Windows, nhưng text block trên Java 17 vẫn dùng `\n` cho các line terminator được chuẩn hóa trong nội dung. Khi cần chuyển sang định dạng xuống dòng cụ thể, hãy xử lý có chủ đích tại nơi xuất dữ liệu.

Thứ tự xử lý nội dung text block của Java 17 bao gồm chuẩn hóa line terminator, xử lý thụt lề ngẫu nhiên, rồi xử lý escape sequence. Do đó, các escape như `\n`, `\s` và `\` nối dòng là một vấn đề riêng, khác với **dòng mới xuất hiện tự nhiên trong mã nguồn**.

## 11. Nếu không muốn xuống dòng cuối thì còn cách nào khác?

Ngoài việc để dấu đóng ngay sau dòng nội dung cuối, Java 17 hỗ trợ **line continuation escape**: một dấu gạch chéo ngược `\` ở cuối dòng nội dung có thể loại line terminator nối tiếp nó.

Ví dụ:

~~~java
String joined = """
    Hello \
    Java 17
    """;
~~~

Sau xử lý thụt lề và escape, giá trị tương đương:

~~~java
"Hello Java 17\n"
~~~

Dấu `\` sau khoảng trắng nằm trong nội dung bảo Java không giữ line terminator tại vị trí đó; phần `Java 17` được nối tiếp. Nếu chỉ muốn bỏ newline cuối, có thể viết:

~~~java
String withoutFinalNewline = """
    Hello\
    """;
~~~

Giá trị là `"Hello"`. Tuy nhiên, đối với bài học đang tập trung vào **dấu đóng**, cách dễ đọc hơn thường là:

~~~java
String withoutFinalNewline = """
    Hello""";
~~~

**Không nhầm line continuation với việc Java tự bỏ xuống dòng**: dấu `\` ở cuối dòng là cú pháp escape có chủ đích; còn dòng mới bắt buộc sau dấu mở bị loại vì nó thuộc opening delimiter.

## 12. Các lỗi dễ mắc khi dùng dấu mở và dấu đóng

| Lỗi hoặc giả định | Điều gì thực sự xảy ra? | Cách viết phù hợp |
| --- | --- | --- |
| Viết `"""Hello"""` trên một dòng. | Không có line terminator bắt buộc sau dấu mở; lỗi cú pháp. | Đặt nội dung từ dòng sau `"""`. |
| Nghĩ rằng text block luôn bắt đầu bằng `\n`. | Dòng mới ngay sau dấu mở bị bỏ. | Thêm **một dòng nội dung trống** nếu thật sự muốn leading newline. |
| Nghĩ rằng dấu đóng tự thêm `\n`. | Dấu đóng không tạo ký tự xuống dòng; `\n` đến từ line terminator trước đó. | Đặt dấu đóng cùng dòng cuối nếu không muốn final newline. |
| Đưa dấu đóng xuống dòng mới chỉ để code đẹp, không để ý giá trị. | Có thể khiến chuỗi kết thúc bằng `\n`. | Xác nhận hợp đồng đầu ra có cho phép newline cuối hay không. |
| So sánh hai text block cùng chữ hiển thị, cho là bằng nhau. | Có thể khác ở `\n` đầu/cuối hoặc thụt lề. | So sánh `equals`, quan sát ký tự escape và `length`. |
| Nhìn kết quả qua `println` và cho rằng text block có thêm dòng trống. | `println` tự thêm một line terminator sau giá trị được in. | Dùng hàm `visible` hoặc `System.out.print`. |
| Tưởng mọi khoảng trắng trước dấu đóng đều thành nội dung. | Quy tắc incidental indentation có thể loại bớt khoảng trắng đầu dòng. | Cố định mức thụt lề và quan sát chuỗi thực tế. |
| Cho rằng text block là raw string không xử lý escape. | Java 17 vẫn xử lý escape sequence sau khi chuẩn hóa nội dung. | Phân biệt `\n` từ line terminator nguồn với escape `\n` viết trong nội dung. |

## 13. Tình huống thực tế: so sánh giá trị chính xác

Giả sử một phương thức trả về nội dung văn bản dùng trong bài kiểm tra tự động:

~~~java
static String welcomeMessage() {
    return """
        Welcome
        """;
}
~~~

Nếu chương trình kiểm thử viết:

~~~java
String expected = "Welcome";
String actual = welcomeMessage();

System.out.println(expected.equals(actual)); // false
~~~

thì nguyên nhân không nằm ở chữ `Welcome` mà ở dấu xuống dòng cuối. Giá trị `actual` là `"Welcome\n"`.

Có ít nhất hai hướng giải quyết tùy hợp đồng:

**Hướng A — giá trị cần giữ newline cuối:**

~~~java
String expected = "Welcome\n";
~~~

**Hướng B — giá trị cần không có newline cuối:**

~~~java
static String welcomeMessage() {
    return """
        Welcome""";
}
~~~

Nên chọn theo định dạng dữ liệu cần cung cấp. Tránh gọi `strip()` hoặc `trim()` một cách vô điều kiện chỉ để làm một phép so sánh đi qua, vì những thao tác này có thể xóa cả khoảng trắng hoặc dòng mới vốn có ý nghĩa ở nội dung khác.

## 14. Bài tập tự luyện

**Bài 1.** Dự đoán `length()`:

~~~java
String a = """
    A
    """;

String b = """
    A""";

String c = """

    A""";
~~~

**Đáp án:** `a.length() == 2` (`"A\n"`), `b.length() == 1` (`"A"`), `c.length() == 2` (`"\nA"`).

**Bài 2.** Chuyển chuỗi thông thường `"red\nblue"` sang text block mà **không** có dòng mới cuối.

~~~java
String colors = """
    red
    blue""";
~~~

**Bài 3.** Chuyển chuỗi thông thường `"\nred\nblue\n"` sang text block.

~~~java
String colors = """

    red
    blue
    """;
~~~

**Bài 4.** Nhận diện lỗi cú pháp:

~~~java
// Sai:
// String invalid = """first line
//     second line""";
~~~

**Đáp án:** Dòng khai báo dấu mở chứa `first line` ngay sau ba dấu nháy kép; Java yêu cầu line terminator ngay sau dấu mở (có thể có khoảng trắng trước terminator). Sửa bằng cách đưa `first line` xuống dòng kế tiếp.

**Bài 5.** Nếu file nguồn dùng CRLF, giá trị Java nhận từ text block sau có giữ nguyên CRLF không?

~~~java
String sample = """
    A
    B
    """;
~~~

**Đáp án:** Không. Line terminator của nội dung text block được Java chuẩn hóa thành `\n`; chuỗi tương đương `"A\nB\n"`.

## 15. Những nguyên tắc cần nhớ

1. **Dấu mở text block phải có line terminator ngay sau nó** (cho phép khoảng trắng trước terminator). Không viết nội dung ngay cùng dòng với `"""` mở.
2. **Line terminator đầu tiên này không nằm trong chuỗi.** Dòng nội dung đầu tiên bắt đầu ở dòng nguồn kế tiếp.
3. Muốn có **leading newline**, hãy thêm dòng trống thuộc nội dung sau dòng mở.
4. **Dấu đóng có thể ở dòng riêng hoặc cùng dòng nội dung cuối.** Dòng nội dung cuối có line terminator trước dấu đóng thì `\n` đó được giữ lại.
5. Khi dấu đóng ở **dòng riêng**, vị trí thụt lề của nó còn có thể ảnh hưởng khoảng trắng được giữ ở đầu các dòng nội dung.
6. Text block Java 17 dùng **`\n` cho các line terminator được chuẩn hóa**, dù source file dùng CRLF.
7. Với các chuỗi cần khớp từng ký tự, hãy xem xét cả **newline đầu/cuối** và **thụt lề**, đừng chỉ nhìn văn bản hiển thị.

### Tài liệu tham khảo chính thức

- [JEP 378 — Text Blocks](https://openjdk.org/jeps/378): text block trở thành tính năng chính thức từ JDK 15, bao gồm cú pháp và quy tắc dòng mới.
- [Java Language Specification, Java SE 17 — §3.10.6 Text Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6): dấu mở/dấu đóng và thứ tự xử lý nội dung.
- [Java Language Specification, Java SE 17 — §3.4 Line Terminators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.4): khái niệm line terminator trong mã nguồn Java.
- [Java SE 17 Programmer’s Guide — Text Blocks](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html): hướng dẫn sử dụng text block trong Java 17.

**Kết luận:** Dấu mở quy định **phải xuống dòng để bắt đầu nội dung** nhưng không đưa dòng mới ấy vào chuỗi; dấu đóng quy định **nội dung kết thúc ở đâu** và vì vậy ảnh hưởng trực tiếp đến newline cuối. Hiểu đúng hai vị trí này giúp viết text block Java 17 dễ đọc mà vẫn kiểm soát chính xác giá trị `String`.
