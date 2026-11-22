# Dòng mới bắt buộc sau dấu mở của text block trong Java

## 1. Quy tắc cần nhớ

Từ **Java 15**, `text block` là cú pháp chính thức để viết giá trị `String` có thể trải trên nhiều dòng. Nó dùng ba dấu nháy kép (`"""`) ở đầu và ở cuối, nhưng **dấu mở bắt buộc phải kết thúc bằng một dấu xuống dòng**. Quy tắc này vẫn áp dụng trong Java hiện đại, gồm Java 17, 21 và các phiên bản mới hơn.

Dạng khái quát:

~~~text
"""[khoảng trắng tùy chọn][dấu xuống dòng]
nội dung
"""
~~~

Cụ thể:

- Dấu mở bắt đầu bằng đúng ba dấu nháy kép `"""`.
- Sau ba dấu nháy kép, chỉ được có **0 hoặc nhiều** ký tự khoảng trắng thuộc loại **space, tab hoặc form feed** rồi **bắt buộc** là dấu kết thúc dòng (LF, CR hoặc CRLF). Không được đặt ký tự nội dung, dấu nháy khác hay chú thích `//` vào chỗ đó.
- **Nội dung của chuỗi chỉ bắt đầu sau dấu xuống dòng của dấu mở.** Dấu xuống dòng bắt buộc này là một phần của *cú pháp dấu mở*, không tự thêm ký tự `\n` vào đầu `String`.
- Dấu đóng `"""` không có yêu cầu tương tự: nó có thể nằm ngay cuối dòng nội dung hoặc trên một dòng riêng. Vị trí dấu đóng có thể quyết định chuỗi có chứa `\n` cuối hay không.

Đây là quy tắc của ngôn ngữ, được kiểm tra khi biên dịch; nó không phụ thuộc vào IDE, hệ điều hành hoặc định dạng trình bày Markdown.

## 2. Cú pháp sai và cách sửa

**Sai — nội dung xuất hiện ngay sau dấu mở:**

~~~java
String message = """Xin chào!""";
~~~

Đây không phải cách viết `String` trên một dòng hợp lệ. Sau `"""` mở, Java yêu cầu kết thúc dòng trước khi có `Xin chào!`. Trình biên dịch từ chối với lỗi liên quan đến chuỗi dấu mở text block không hợp lệ; câu chữ chẩn đoán có thể khác nhau giữa các phiên bản `javac`.

**Sai — có dấu xuống dòng ở phía sau, nhưng không phải ngay sau dấu mở:**

~~~java
String message = """Xin chào
Java""";
~~~

Dấu xuống dòng *sau* `Xin chào` không thể thay thế dấu xuống dòng bắt buộc *ngay sau* `"""` mở.

**Đúng — dòng nội dung bắt đầu sau dấu mở:**

~~~java
String message = """
        Xin chào!""";
~~~

Giá trị của `message` là `"Xin chào!"` (không có `\n` đầu hay cuối). Text block hoàn toàn có thể chỉ chứa **một dòng nội dung**; điều kiện bắt buộc là dòng mới **sau dấu mở**, không phải số dòng nội dung.

Nếu cần một chuỗi một dòng và không hưởng lợi từ cách trình bày text block, `String message = "Xin chào!";` cũng là lựa chọn rõ ràng.

## 3. Phân biệt xuống dòng sau dấu mở với xuống dòng trong giá trị

Quan sát vị trí dấu đóng trong ba đoạn sau:

~~~java
// Không có \n ở đầu hoặc cuối
String a = """
        Java""";

// Có \n cuối vì dấu đóng nằm trên dòng kế tiếp
String b = """
        Java
        """;

// Có \n đầu do chủ động để trống một dòng nội dung
String c = """

        Java""";
~~~

Sau khi Java xử lý phần thụt lề không đáng kể, các giá trị tương ứng là:

| Biến | Biểu diễn giá trị thực | Vì sao? |
| --- | --- | --- |
| `a` | `"Java"` | Dấu xuống dòng sau `"""` mở thuộc dấu mở; dấu đóng nằm ngay sau `Java`. |
| `b` | `"Java\n"` | Dòng chứa `Java` kết thúc trước dòng chứa dấu đóng, nên dấu xuống dòng đó thuộc nội dung. |
| `c` | `"\nJava"` | Có **một dòng trống thật** sau dòng bắt buộc của dấu mở. |

Nếu chỉ viết dấu mở, xuống dòng, rồi dấu đóng, text block có thể biểu diễn chuỗi rỗng:

~~~java
String empty = """
        """;
~~~

Giá trị của `empty` là `""`. Không phải mọi text block đều chứa ký tự xuống dòng.

## 4. Ví dụ Java 17+ chạy độc lập

Lưu mã sau vào tệp **`TextBlockOpeningDemo.java`**:

~~~java
public class TextBlockOpeningDemo {
    public static void main(String[] args) {
        String noFinalNewline = """
                Chào Java""";

        String finalNewline = """
                Chào Java
                """;

        String leadingBlankLine = """

                Chào Java""";

        String empty = """
                """;

        show("noFinalNewline", noFinalNewline);
        show("finalNewline", finalNewline);
        show("leadingBlankLine", leadingBlankLine);
        show("empty", empty);
    }

    private static void show(String label, String value) {
        String visible = value.replace("\n", "\\n");
        System.out.println(label + " = [" + visible + "] / length=" + value.length());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 TextBlockOpeningDemo.java
java TextBlockOpeningDemo
~~~

Kết quả chuẩn:

~~~text
noFinalNewline = [Chào Java] / length=9
finalNewline = [Chào Java\n] / length=10
leadingBlankLine = [\nChào Java] / length=10
empty = [] / length=0
~~~

Hàm `show` thay ký tự xuống dòng thực bằng hai ký tự hiển thị `\` và `n`, giúp quan sát chính xác nội dung. `String.length()` ở ví dụ này đếm các đơn vị mã UTF-16; mỗi chữ trong `Chào Java` chiếm một đơn vị.

Ba điều cần rút ra: (1) xuống dòng ngay sau `"""` mở **không** tạo `\n` đầu chuỗi; (2) dòng trống *bổ sung* sau dấu mở tạo `\n` đầu; (3) chuyển dấu đóng sang dòng riêng tạo `\n` cuối khi dòng nội dung kết thúc bằng xuống dòng.

## 5. Khoảng trắng trên dòng mở, thụt lề và kiểu xuống dòng

**Khoảng trắng sau dấu mở.** Java cho phép space, tab hoặc form feed giữa `"""` mở và ký tự kết thúc dòng. Ví dụ, về mặt cú pháp, `"""` rồi ba dấu cách rồi xuống dòng vẫn hợp lệ. Tuy nhiên, không nên dựa vào khoảng trắng cuối dòng vì trình định dạng có thể tự xóa chúng. **Ký tự không phải khoảng trắng** (kể cả `// chú thích`) trước dấu xuống dòng làm dấu mở không hợp lệ.

**Thụt lề ở các dòng tiếp theo.** Java tự loại bỏ phần thụt lề *không đáng kể* của nội dung text block (`incidental white space`). Bước này khác với quy tắc dấu mở phải có xuống dòng. Đừng suy ra số khoảng trắng được giữ trong chuỗi chỉ bằng việc đếm thụt lề nhìn thấy trong mã nguồn; cần xét cả dòng đặt dấu đóng.

**Dấu kết thúc dòng.** Nguồn có thể dùng LF, CR hoặc CRLF làm kết thúc dòng sau dấu mở. Khi tạo giá trị `String`, Java chuẩn hóa các ký tự kết thúc dòng trong nội dung thành LF (`\n`), rồi xử lý thụt lề và các escape sequence. Vì vậy, dấu xuống dòng bắt buộc về mặt cú pháp không đồng nghĩa với việc chuỗi bắt đầu bằng ký tự xuống dòng của hệ điều hành đang dùng.

## 6. Lỗi thường gặp và cách tự kiểm tra

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `"""hello"""` không biên dịch | Có chữ ngay sau dấu mở | Đưa `hello` xuống dòng tiếp theo hoặc dùng chuỗi thông thường `"hello"`. |
| `""" // note` không biên dịch | Chú thích nằm trước dấu xuống dòng bắt buộc | Đặt chú thích ở dòng riêng **trước** text block. |
| Chuỗi có `\n` ở cuối ngoài ý muốn | Dấu đóng nằm ở dòng riêng sau nội dung | Đặt dấu đóng ngay cuối dòng nội dung, nếu muốn bỏ `\n` cuối. |
| Chuỗi có `\n` ở đầu ngoài ý muốn | Có thêm một dòng trống sau dòng bắt buộc của dấu mở | Bắt đầu nội dung ngay tại dòng kế tiếp. |
| Khoảng trắng trong chuỗi khác dự kiến | Java xử lý thụt lề không đáng kể | So sánh giá trị bằng cách hiển thị `\n` và kiểm tra dòng dấu đóng. |

Để tự kiểm tra một text block: xác định `"""` **mở**; nhìn đến hết chính dòng đó — chỉ có khoảng trắng cho phép trước dấu xuống dòng; sau đó xác định dòng nội dung đầu tiên và vị trí `"""` **đóng**. Đừng nhầm dấu xuống dòng cấu thành dấu mở với các dấu xuống dòng thực sự thuộc nội dung.

**Tài liệu tham khảo hiện hành:** [Java Language Specification, mục 3.10.6 — Text Blocks](https://docs.oracle.com/javase/specs/jls/se26/html/jls-3.html#jls-3.10.6).