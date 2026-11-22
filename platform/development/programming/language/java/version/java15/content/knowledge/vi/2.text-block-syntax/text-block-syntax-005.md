# Text block rỗng và nội dung chỉ có một dòng (Java 15+)

## 1. Bản chất và quy tắc cú pháp

**Text block** là cách viết một giá trị `java.lang.String` bằng cặp dấu phân định `"""`. Tính năng này đã chính thức có từ **Java 15** và vẫn được hỗ trợ trong các bản Java hiện đại. Text block thường giúp trình bày chuỗi nhiều dòng dễ đọc, nhưng cũng biểu diễn được **chuỗi rỗng** hoặc **chuỗi chỉ có một dòng nội dung**.

Cú pháp có hai quy tắc cần nhớ:

- Sau **ba dấu nháy kép mở** `"""` bắt buộc phải có ký tự xuống dòng của mã nguồn (có thể có khoảng trắng trước ký tự xuống dòng). Không đặt nội dung ngay trên dòng chứa dấu mở.
- **Ba dấu nháy kép đóng** `"""` có thể đứng ngay sau ký tự cuối cùng của nội dung hoặc trên một dòng riêng. Vị trí này quyết định có giữ ký tự xuống dòng cuối trong chuỗi hay không.

Ví dụ sau **sai cú pháp** (chỉ để nhận diện lỗi, không đặt vào chương trình chạy):

~~~java
String invalid = """Xin chào!"""; // Lỗi: thiếu xuống dòng sau dấu mở
~~~

Dòng xuống dòng *ngay sau dấu mở* chỉ phục vụ cú pháp và **không tự tạo ra** ký tự `\n` đầu chuỗi.

## 2. Text block rỗng: giá trị chính xác là `""`

~~~java
String empty = """
        """;
~~~

Dấu đóng nằm ở đầu dòng nội dung đầu tiên; sau khi Java xử lý thụt lề, giữa hai dấu phân định không có ký tự nào. Vì vậy:

- `empty.equals("")` trả về `true`.
- `empty.length()` bằng `0`.
- `empty.isEmpty()` trả về `true`.

Không nhầm **chuỗi rỗng** với một chuỗi chứa ký tự xuống dòng. Chỉ cần thêm **một dòng trống bên trong text block** như ví dụ dưới đây, kết quả đã khác:

~~~java
String onlyNewline = """

        """;
~~~

Giá trị của `onlyNewline` là `"\n"`: `length() == 1`, `isEmpty() == false`, nhưng `isBlank() == true`. Trong mã nguồn, có một dòng trống giữa dấu mở và dấu đóng; ký tự xuống dòng kết thúc dòng trống đó thuộc về nội dung.

## 3. Nội dung chỉ có một dòng, không có `\n` cuối

~~~java
String oneLine = """
        Xin chào!""";
~~~

Đây là một text block hợp lệ, dù giá trị Java chỉ có một dòng. Nó hoàn toàn tương đương với:

~~~java
String oneLine = "Xin chào!";
~~~

Dấu đóng đặt **ngay sau dấu chấm than** nên không có ký tự xuống dòng cuối chuỗi. Phần thụt lề dùng để căn chỉnh mã nguồn được Java loại bỏ theo quy tắc *incidental indentation*. Kết quả `oneLine.equals("Xin chào!")` là `true`.

**Phân biệt số dòng của mã nguồn và số dòng của giá trị:** dù text block phải trải qua ít nhất hai dòng trong tệp `.java`, nội dung `String` thu được vẫn có thể có một dòng hoặc không có dòng nào.

## 4. Một dòng nội dung nhưng có xuống dòng cuối

So sánh với cách đặt dấu đóng trên dòng riêng:

~~~java
String withFinalNewline = """
        Xin chào!
        """;
~~~

Giá trị tương đương là `"Xin chào!\n"`, **khác** với `"Xin chào!"`. Dòng chứa dấu đóng không tự thêm nội dung; chính ký tự xuống dòng **sau** `Xin chào!` và **trước** dấu đóng trở thành `\n` cuối chuỗi.

| Trường hợp | Giá trị `String` | Độ dài/ký tự cần chú ý |
| --- | --- | --- |
| Dấu đóng ngay sau dấu mở trên dòng nội dung kế tiếp | `""` | 0 ký tự |
| Một dòng `Xin chào!`, dấu đóng ngay cuối nội dung | `"Xin chào!"` | Không có `\n` cuối |
| Một dòng `Xin chào!`, dấu đóng ở dòng sau | `"Xin chào!\n"` | Có một `\n` cuối |
| Một dòng trống giữa dấu mở và dấu đóng | `"\n"` | Một ký tự xuống dòng |

Trong text block, Java chuẩn hóa các ký tự kết thúc dòng của mã nguồn thành **LF (`\n`)**, kể cả khi tệp được lưu với CRLF trên Windows. Vì vậy, khi so sánh chuỗi hoặc viết bài kiểm thử, hãy chú ý đến `\n` thực sự có trong giá trị.

## 5. Chương trình chạy được: kiểm chứng cả bốn trường hợp

Lưu thành tệp **`TextBlockOneLineDemo.java`** (Java 15 trở lên):

~~~java
public class TextBlockOneLineDemo {
    public static void main(String[] args) {
        String empty = """
                """;

        String oneLine = """
                Xin chào!""";

        String withFinalNewline = """
                Xin chào!
                """;

        String onlyNewline = """

                """;

        System.out.println("empty.length = " + empty.length());
        System.out.println("oneLine.equals = " + oneLine.equals("Xin chào!"));
        System.out.println("withFinalNewline.equals = "
                + withFinalNewline.equals("Xin chào!\n"));
        System.out.println("onlyNewline.equals = "
                + onlyNewline.equals("\n"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 TextBlockOneLineDemo.java
java TextBlockOneLineDemo
~~~

Kết quả chuẩn:

~~~text
empty.length = 0
oneLine.equals = true
withFinalNewline.equals = true
onlyNewline.equals = true
~~~

Những phép so sánh bằng `equals` cho thấy chính xác nội dung chuỗi, kể cả ký tự xuống dòng khó nhìn thấy khi chỉ gọi `println`. Ví dụ đã được biên dịch và chạy với JDK 24; ngữ nghĩa ở đây áp dụng từ Java 15 trở đi, không cần cờ kích hoạt tính năng thử nghiệm.

## 6. Lưu ý khi áp dụng và lỗi thường gặp

1. **Viết nội dung ngay sau dấu mở:** `"""Hello"""` không hợp lệ. Luôn xuống dòng ngay sau dấu mở.
2. **Quên ký tự xuống dòng cuối:** `"""` đóng trên dòng riêng thường giữ lại `\n` của dòng nội dung cuối; khi cần giá trị một dòng không có `\n`, đặt dấu đóng ngay sau nội dung như ở mục 3.
3. **Nhầm rỗng với chỉ chứa khoảng trắng/xuống dòng:** `isEmpty()` kiểm tra độ dài bằng 0; `isBlank()` kiểm tra chuỗi toàn ký tự khoảng trắng, nên `"\n"` là blank nhưng không empty.
4. **Tưởng khoảng trắng thụt lề luôn được giữ nguyên:** Java tự loại bỏ mức thụt lề phụ trợ và thường bỏ khoảng trắng cuối dòng. Nếu cần dữ liệu có khoảng trắng chính xác, kiểm tra bằng `equals` hoặc mã ký tự; khi cần cố ý giữ một dấu cách cuối dòng, có thể dùng escape `\s`.
5. **Lạm dụng text block cho chuỗi rất ngắn:** nếu chỉ cần `""` hoặc `"Xin chào!"` trong mã ứng dụng, string literal thông thường thường ngắn và dễ hiểu hơn. Text block hữu ích nhất khi chuỗi nhiều dòng, cần trình bày đúng bố cục, hoặc đang làm việc nhất quán với mẫu text block.

**Tự kiểm tra:** nếu một text block đang trả về `"OK\n"`, muốn đổi thành `"OK"` mà không thêm thao tác xử lý chuỗi, hãy đưa dấu đóng `"""` lên cùng dòng và ngay sau `OK`.

## Tài liệu chính thức

- Oracle, *Text Blocks* (Java 25): https://docs.oracle.com/en/java/javase/25/language/text-blocks.html
- OpenJDK, *JEP 378: Text Blocks* (tính năng chuẩn từ Java 15): https://openjdk.org/jeps/378