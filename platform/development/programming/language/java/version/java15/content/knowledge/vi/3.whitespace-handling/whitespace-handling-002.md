# Cách xác định mức thụt lề chung của Java text block

Trong Java, **text block** là cú pháp khai báo `String` nhiều dòng bằng cặp dấu phân định `"""`. Từ Java 15, cú pháp này là tính năng chính thức và tiếp tục được hỗ trợ trong các phiên bản Java hiện đại. Text block cho phép trình bày văn bản theo lề của mã nguồn nhưng không bắt buộc giữ nguyên toàn bộ dấu cách thụt vào đó trong giá trị `String`.

Để hiểu text block chứa chính xác những ký tự nào, cần nắm cách Java tính **mức thụt lề chung** (*common/incidental indentation*): số ký tự khoảng trắng đầu dòng mà trình biên dịch có thể loại bỏ đồng đều mà vẫn giữ cách thụt lề tương đối giữa các dòng nội dung.

## 1. Phân biệt khoảng trắng phụ và khoảng trắng có ý nghĩa

Ví dụ:

```java
String html = """
        <main>
          <p>Hello</p>
        </main>
        """;
```

Các dòng `<main>`, `</main>` và dấu đóng `"""` đều được thụt vào 8 dấu cách trong mã nguồn; dòng `<p>` được thụt vào 10 dấu cách.

- **8 dấu cách chung** là thụt lề phụ (*incidental indentation*), được Java tự loại bỏ.
- **2 dấu cách còn lại** trước `<p>` là thụt lề có ý nghĩa (*essential indentation*), được giữ lại vì biểu thị cấu trúc lồng nhau.
- Với dấu đóng đặt ở một dòng riêng như trên, giá trị cuối cùng của `html` là `"<main>\n  <p>Hello</p>\n</main>\n"`. Chuỗi **không có 8 dấu cách ở đầu dòng**.

Đây là xử lý ở thời điểm biên dịch. `String` được tạo từ text block đã qua xử lý có nội dung xác định, giống như `String` tạo từ một string literal thông thường.

## 2. Thuật toán tính mức thụt lề chung

Về mặt thực hành, có thể xác định giá trị bằng các bước sau:

1. **Tách các dòng nội dung**: ký tự xuống dòng trong text block được chuẩn hóa thành LF (`\n`) trước khi xử lý thụt lề. Dấu xuống dòng bắt buộc ngay sau dấu mở `"""` không làm chuỗi có một dòng trống ở đầu.
2. **Đếm ký tự khoảng trắng đứng đầu mỗi dòng**: đếm từ mép trái tới ký tự không phải khoảng trắng đầu tiên. Với các ký tự thụt lề thường dùng, một dấu cách và một tab mỗi loại đều được tính là **một ký tự**; tab không tự được tính thành 4 hay 8 dấu cách.
3. **Chọn những dòng tham gia xác định mức chung**: lấy tất cả các dòng có nội dung không chỉ là khoảng trắng (**dòng không rỗng về mặt nội dung**), **cộng với dòng cuối ngay trước dấu đóng**, kể cả khi dòng cuối chỉ có khoảng trắng. Khi dấu đóng đứng riêng trên dòng, khoảng thụt lề trước `"""` chính là mức lề của dòng cuối đó.
4. **Lấy giá trị nhỏ nhất** trong các số lượng đã đếm. Đó là mức thụt lề chung cần bỏ. Dòng trống ở giữa không kéo mức chung xuống 0.
5. **Loại bỏ mức thụt lề chung ở đầu mỗi dòng**, đồng thời loại bỏ khoảng trắng thừa ở cuối các dòng. Sau đó Java mới diễn giải các escape như `\t`, `\s`, `\n` trong nội dung.

Điều cần nhớ: **mức chung là giá trị nhỏ nhất, không phải trung bình và cũng không mặc định bằng độ thụt lề của dòng đầu**.

### Tính từng dòng của ví dụ HTML

| Dòng trong mã nguồn | Số ký tự khoảng trắng ở đầu | Sau khi bỏ mức chung 8 |
| --- | ---: | --- |
| `<main>` | 8 | 0 |
| `<p>Hello</p>` | 10 | 2 |
| `</main>` | 8 | 0 |
| Dòng của dấu đóng `"""` | 8 | Không tạo thêm ký tự nội dung |

Vậy mức chung bằng `min(8, 10, 8, 8) = 8`. Sau khi loại bỏ 8 ký tự ở đầu mỗi dòng, cấu trúc HTML bên trong chuỗi vẫn giữ mức lồng nhau 2 dấu cách.

## 3. Vì sao vị trí dấu đóng thay đổi kết quả?

Với text block có dấu đóng **trên một dòng riêng**, lề trước dấu đóng tham gia tính mức thụt lề chung. Nếu dịch dấu đóng sang trái, Java sẽ bỏ ít khoảng trắng ở các dòng nội dung hơn:

```java
String aligned = """
        A
          B
        """;

String shiftedLeft = """
        A
          B
    """;

String inlineClosing = """
        A
          B""";
```

Phân tích:

| Biến | Các số lề tham gia | Mức chung | Giá trị chuỗi, dùng `\n` để biểu diễn newline |
| --- | --- | ---: | --- |
| `aligned` | 8, 10, 8 (dòng đóng) | 8 | `A\n  B\n` |
| `shiftedLeft` | 8, 10, 4 (dòng đóng) | 4 | `    A\n      B\n` |
| `inlineClosing` | 8, 10 (không có dòng đóng riêng) | 8 | `A\n  B` |

Hai chi tiết quan trọng:

- Đặt dấu đóng **ít thụt lề hơn** dòng nội dung là một cách chủ động giữ lại khoảng trắng đầu chuỗi. Ví dụ `shiftedLeft` giữ bốn dấu cách trước `A`.
- Nếu dấu đóng nằm ngay sau ký tự cuối của nội dung, không có dòng dấu đóng riêng để tham gia phép lấy giá trị nhỏ nhất. Cách viết này cũng **không giữ ký tự `\n` cuối chuỗi**. Muốn thêm khoảng trắng đầu vào trường hợp ấy, có thể chủ động đưa khoảng trắng vào sau khi tạo chuỗi, nhưng phải xét hành vi xuống dòng của phương thức áp dụng.

Dấu **mở** `"""` phải theo sau bởi ký tự xuống dòng, nhưng vị trí ngang của dấu mở **không trực tiếp là một ứng viên tính mức thụt lề chung**. Đừng lấy vị trí dấu mở thay cho lề của dòng nội dung hoặc dấu đóng.

## 4. Dòng trống, dấu cách cuối dòng và tab

### Dòng trống ở giữa

```java
String paragraph = """
        red

          blue
        """;
```

Dòng trống ở giữa không được dùng để lấy mức thụt lề nhỏ nhất. Mức chung vẫn là 8; kết quả là `"red\n\n  blue\n"`. Dù có thêm một dòng chỉ chứa khoảng trắng ở giữa, dòng ấy cũng được coi là trống khi tính mức chung, và phần khoảng trắng không có ý nghĩa của dòng đó bị loại bỏ.

**Ngoại lệ của dòng cuối:** Nếu dấu đóng ở dòng riêng, dòng trống cuối nơi đặt dấu đóng vẫn tham gia phép tính. Đây là lý do việc đưa dấu đóng về cột đầu tiên (mức lề 0) có thể giữ nguyên thụt lề đầu các dòng nội dung.

### Khoảng trắng cuối dòng

Java còn tự loại bỏ các khoảng trắng vô tình nằm ở **cuối dòng** của text block. Chúng khác với mức thụt lề chung ở đầu dòng. Khi thực sự cần một dấu cách cuối dòng, có thể dùng escape `\s` (được diễn giải sau bước loại khoảng trắng):

```java
String trailingSpace = """
        X\s
        """;
```

Giá trị của `trailingSpace` là `"X \n"`: có một dấu cách giữa `X` và ký tự xuống dòng. Viết các dấu cách vô hình trực tiếp ở cuối dòng dễ bị trình soạn thảo tự xóa, nên `\s` rõ ràng và ổn định hơn.

### Không trộn tab và dấu cách

Java đếm **số ký tự** khoảng trắng chứ không suy đoán độ rộng hiển thị của tab. Chẳng hạn năm tab đầu dòng được đếm là 5 ký tự, khác với 20 dấu cách, dù trình soạn thảo có thể căn chúng gần giống nhau. Trộn tab với dấu cách có thể khiến mức chung bị xác định thấp hơn dự định, tạo đầu dòng lệch lạc trong chuỗi kết quả.

Nên nhất quán dùng dấu cách hoặc tab cho toàn bộ thụt lề trong một text block. Có thể bật cảnh báo liên quan bằng `javac -Xlint:text-blocks`, chẳng hạn để phát hiện thụt lề không nhất quán hoặc khoảng trắng cuối dòng sẽ bị bỏ.

## 5. Ví dụ Java 17+ đầy đủ, có thể biên dịch và chạy

Lưu vào file `CommonIndentDemo.java` với mã hóa UTF-8:

```java
public class CommonIndentDemo {
    private static String show(String value) {
        // Thay khoảng trắng bằng "·"; hiển thị newline bằng "\n".
        return value.replace(" ", "·").replace("\n", "\\n");
    }

    public static void main(String[] args) {
        String aligned = """
                A
                  B
                """;

        String shiftedLeft = """
                A
                  B
            """;

        String inlineClosing = """
                A
                  B""";

        String blankLine = """
                red

                  blue
                """;

        String trailingSpace = """
                X\s
                """;

        System.out.println("aligned=" + show(aligned));
        System.out.println("shiftedLeft=" + show(shiftedLeft));
        System.out.println("inlineClosing=" + show(inlineClosing));
        System.out.println("blankLine=" + show(blankLine));
        System.out.println("trailingSpace=" + show(trailingSpace));
    }
}
```

Biên dịch rồi chạy từ thư mục chứa tệp:

```bash
javac -encoding UTF-8 CommonIndentDemo.java
java CommonIndentDemo
```

**Đầu ra chính xác** (ký hiệu `·` biểu diễn **một dấu cách**, còn `\n` được in thành hai ký tự để dễ nhìn):

```text
aligned=A\n··B\n
shiftedLeft=····A\n······B\n
inlineClosing=A\n··B
blankLine=red\n\n··blue\n
trailingSpace=X·\n
```

Giải thích: ở ví dụ chạy được này, `aligned` có lề 16, 18 và 16 nên bị loại 16 ký tự ở đầu mỗi dòng; `shiftedLeft` có lề 16, 18 và 12 nên bị loại 12; `inlineClosing` không có dòng đóng riêng nên mức chung lấy từ hai dòng 16 và 18. Chênh lệch hai dấu cách giữa các dòng `A` và `B` vẫn được bảo toàn.

**Lưu ý:** Dấu `·` trong chương trình là ký hiệu do hàm `show` thay thế để kiểm tra kết quả, không phải ký tự do Java tự thêm vào text block.

## 6. Quy tắc thực hành khi soạn text block

- Đặt dấu đóng trên **một dòng riêng có lề thẳng với dòng nội dung ngoài cùng** nếu muốn giá trị không có lề thừa nhưng vẫn giữ thụt lề tương đối giữa các dòng.
- Đặt dấu đóng **lùi trái hơn nội dung** nếu bạn có chủ ý giữ một số dấu cách ở đầu mọi dòng. Hãy kiểm tra kết quả thay vì chỉ dựa vào cách trình soạn thảo hiển thị.
- Đặt dấu đóng **ngay sau ký tự cuối** khi không muốn ký tự xuống dòng cuối chuỗi; trong trường hợp này, dấu đóng không đóng vai trò một dòng trắng riêng khi tính lề.
- Dùng một kiểu ký tự thụt lề thống nhất. Không để dấu cách vô hình ở cuối dòng, trừ khi đã cố ý dùng escape như `\s`.
- Khi cần kiểm tra chính xác, thay dấu cách/newline bằng ký hiệu dễ thấy như hàm `show` ở trên. Chỉ so sánh bằng mắt có thể bỏ sót ký tự vô hình.
- Giữ cho việc thụt lề của HTML, SQL hoặc JSON bên trong chuỗi phản ánh cấu trúc mong muốn. Java chỉ loại bỏ phần lề chung, không tự định dạng nội dung của ngôn ngữ nhúng.

## 7. Lỗi thường gặp

| Nhầm lẫn | Kết quả thực tế | Cách xử lý |
| --- | --- | --- |
| Lấy trung bình các lề đầu dòng | Java chọn **mức nhỏ nhất**, không lấy trung bình | Liệt kê từng dòng tham gia rồi tìm `min(...)` |
| Mặc định lấy lề dòng đầu | Một dòng khác hoặc dòng đóng có thể có lề nhỏ hơn | Tính cả dòng đóng nếu nó ở dòng riêng |
| Cho rằng một dòng trống ở giữa có lề 0 nên mức chung bằng 0 | Dòng trống giữa các đoạn không quyết định mức chung | Bỏ qua dòng trống giữa khi tìm mức nhỏ nhất |
| Không tính dòng đóng riêng | Chuỗi có thể giữ nhiều dấu cách đầu dòng hơn dự kiến | Tính cả khoảng trắng trước `"""` trên dòng đóng |
| Coi tab có độ rộng cố định 4/8 dấu cách | Mỗi tab được tính như một ký tự khoảng trắng | Không trộn tab và dấu cách |
| Nghĩ Java giữ mọi khoảng trắng cuối dòng | Khoảng trắng cuối dòng thường bị loại | Dùng `\s` khi cố ý giữ dấu cách cuối dòng |
| Nghĩ dấu đóng cùng dòng vẫn có lề riêng để tính | Không có dòng đóng riêng, và thường không có `\n` cuối | Phân biệt hai kiểu đặt dấu đóng |

## 8. Tự kiểm tra

Không chạy chương trình, hãy xác định chuỗi chính xác được tạo bởi:

```java
String answer = """
          one

            two
        """;
```

- Có bao nhiêu dấu cách đứng đầu `one` và `two` trong giá trị `String`?
- Mức thụt lề chung bằng bao nhiêu?
- Ký tự xuống dòng cuối chuỗi có tồn tại không?

**Đáp án:** Hai dòng nội dung có 10 và 12 dấu cách đầu dòng; dòng dấu đóng có 8, dòng trống giữa bị bỏ qua khi tìm mức chung. Do đó mức chung là `min(10, 12, 8) = 8`. Giá trị `answer` là `"  one\n\n    two\n"`: có 2 dấu cách trước `one`, 4 trước `two`, một dòng trống ở giữa và một ký tự `\n` cuối chuỗi.

**Tài liệu tham khảo còn áp dụng:** [Oracle — Text Blocks (Incidental White Space)](https://docs.oracle.com/en/java/javase/25/language/text-blocks.html) và [Java Language Specification §3.10.6 — Text Blocks](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6).