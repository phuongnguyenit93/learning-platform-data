# String.stripIndent() với văn bản nhận từ bên ngoài (Java 15+)

## Mục tiêu

Biết khi nào nên dùng **String.stripIndent()** để chuẩn hóa phần thụt lề chung của văn bản nhiều dòng được đọc từ **tệp, phản hồi mạng hoặc nguồn dữ liệu bên ngoài**; hiểu chính xác cơ chế loại khoảng trắng và chuẩn hóa xuống dòng; phân biệt phương thức này với **strip()**, **stripTrailing()** và việc xử lý text block trong mã nguồn. Đặc biệt, nhận biết trường hợp dữ liệu đầu vào **có ký tự xuống dòng ở cuối**, vì nó có thể khiến phần thụt lề chung không bị loại bỏ.

**String.stripIndent()** có từ Java 15 và vẫn là API chính thức trong Java 17 trở lên. Phương thức không cần tham số, trả về **String** và không thay đổi chuỗi gốc.

## 1. Tình huống: dữ liệu nhiều dòng đến từ bên ngoài

Giả sử ứng dụng đọc một đoạn XML phục vụ hiển thị từ tệp UTF-8. Nội dung tệp có thể là:

~~~text
    <list>
      <item>Tea</item>
    </list>
~~~

Bốn dấu cách đầu mỗi dòng có thể là phần thụt lề thêm vào khi lưu trữ, trong khi hai dấu cách trước thẻ item là cấu trúc tương đối cần giữ. Nếu dữ liệu được nhận dưới dạng một biến String và **không có ký tự xuống dòng cuối**, có thể chuẩn hóa:

~~~java
String incoming = "    <list>\n      <item>Tea</item>\n    </list>";
String normalized = incoming.stripIndent();
~~~

Khi đó, normalized tương đương với:

~~~text
<list>
  <item>Tea</item>
</list>
~~~

**Điểm khác với text block:** Text block trong mã nguồn Java được trình biên dịch xử lý phần thụt lề không chủ ý khi tạo literal. Dữ liệu đọc lúc chạy từ tệp hoặc mạng là **String đã tồn tại**; cú pháp text block không thể tự xử lý dữ liệu đó. Gọi **incoming.stripIndent()** sẽ áp dụng phép xử lý tại thời điểm chạy lên chính chuỗi nhận được.

Mục đích là dời **toàn bộ khối** về bên trái một lượng phù hợp, đồng thời giữ **mức thụt lề tương đối** giữa các dòng còn lại. Đây không phải thao tác xóa toàn bộ dấu cách đầu từng dòng.

## 2. stripIndent() hoạt động như thế nào?

Theo hợp đồng API Java, phương thức xử lý nội dung theo các bước:

1. **Tách thành các dòng.** Dấu kết thúc dòng được nhận diện là LF, CR hoặc cặp CRLF. Các dấu kết thúc dòng sẽ được chuẩn hóa thành **LF (ký tự \n)** ở chuỗi kết quả.
2. **Tìm mức thụt lề chung nhỏ nhất.** Đếm các ký tự whitespace ở đầu mỗi dòng **không trống**. Dòng cuối cũng được xét, kể cả khi dòng cuối trống. Đây là lý do dữ liệu có dấu kết thúc dòng cuối có thể cho kết quả khác.
3. **Giảm thụt lề.** Trừ mức chung đó khỏi đầu các dòng không trống; **cấu trúc thụt lề tương đối** còn lại được giữ.
4. **Xử lý phần cuối dòng.** Whitespace cuối mỗi dòng không trống bị loại bỏ; dòng chỉ chứa whitespace biến thành dòng rỗng.
5. **Ghép các dòng lại.** Kết quả dùng LF. Số lượng dấu kết thúc dòng được giữ; nếu đầu vào có dấu kết thúc dòng ở cuối thì đầu ra cũng có dấu kết thúc dòng ở cuối.

Ví dụ xét nội dung sau, biểu diễn khoảng trắng đầu dòng bằng dấu chấm để dễ đếm:

~~~text
....A
......B
....C
~~~

Các dòng không trống lần lượt thụt vào 4, 6 và 4 dấu cách; mức chung là 4. Sau khi stripIndent(), kết quả có dòng A và C sát lề trái, còn B vẫn lùi 2 dấu cách.

**Đừng hiểu rằng phương thức chỉ loại dấu cách ASCII.** API dựa vào định nghĩa whitespace của **Character.isWhitespace**; dấu tab cũng được tính là **một ký tự**, không tự quy đổi thành nhiều cột hiển thị. Nếu dữ liệu trộn tab và dấu cách không nhất quán, kết quả có thể vẫn lệch khi xem trong trình soạn thảo.

## 3. Lưu ý quan trọng: văn bản bên ngoài kết thúc bằng newline

Một tệp văn bản thông thường hay có dấu kết thúc dòng cuối, chẳng hạn:

~~~java
String withoutFinalNewline = "    A\n      B";
String withFinalNewline = "    A\n      B\n";
~~~

Kết quả:

~~~text
withoutFinalNewline.stripIndent() -> "A\n  B"
withFinalNewline.stripIndent()    -> "    A\n      B\n"
~~~

Ở trường hợp thứ hai, chuỗi kết thúc bằng dấu xuống dòng. Dòng cuối trống làm mức thụt lề chung bằng **0**, nên các dấu cách **đầu dòng** vẫn còn. Phương thức vẫn chuẩn hóa kiểu xuống dòng, bỏ whitespace cuối các dòng không trống và giữ dấu kết thúc dòng cuối.

**Hệ quả thực tế:** nếu API hoặc tệp thường luôn kết thúc bằng CRLF/LF, việc gọi **raw.stripIndent()** có thể không cho kết quả “dịch cả khối về trái” như mong muốn, dù đoạn văn đang có phần thụt lề chung rõ ràng. Khi viết chương trình, phải kiểm tra dữ liệu đầu vào có kết thúc bằng dòng mới hay không, thay vì chỉ quan sát các dòng nội dung trên màn hình.

Nếu **yêu cầu nghiệp vụ cho phép bỏ toàn bộ whitespace cuối văn bản**, có thể gọi:

~~~java
String normalized = raw.stripTrailing().stripIndent();
~~~

Cách này bỏ whitespace ở **cuối toàn bộ String trước**, trong đó có các dấu xuống dòng hoặc các dòng trống cuối, rồi mới tìm thụt lề chung. **Không dùng cách này** nếu bắt buộc giữ nguyên số dòng rỗng cuối, dấu xuống dòng cuối, hoặc dấu cách có ý nghĩa. Khi cần vừa giữ chính xác các dòng cuối vừa khử thụt lề, hãy viết quy tắc riêng, định nghĩa rõ số dòng cần bảo toàn và kiểm thử từng trường hợp.

Lưu ý thêm: khi một dòng trống ở cuối chứa dấu cách, chính số whitespace của dòng cuối đó cũng có thể giới hạn lượng thụt lề được loại bỏ. Vì vậy, cùng một nội dung nhìn thấy có thể xử lý khác nhau tùy phần cuối của chuỗi.

## 4. Ví dụ Java 17+ hoàn chỉnh: đọc dữ liệu từ tệp

Ví dụ tạo một tệp tạm UTF-8 để mô phỏng dữ liệu từ bên ngoài, đọc lại bằng **Files.readString(...)**, áp dụng **stripIndent()** và đối chiếu trường hợp có CRLF cuối. Phương thức **visible(...)** giúp hiển thị rõ dấu xuống dòng dưới dạng ký tự gạch chéo và chữ n/r thay vì xuống dòng thật, nên dễ kiểm tra kết quả.

Lưu mã với tên **ExternalStripIndentDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ExternalStripIndentDemo {
    static String visible(String text) {
        return "[" + text.replace("\\", "\\\\")
                         .replace("\r", "\\r")
                         .replace("\n", "\\n")
                         .replace("\t", "\\t") + "]";
    }

    public static void main(String[] args) throws IOException {
        String dataFromOutside =
                "    <list>\r\n      <item>Tea</item>   \r\n    </list>";
        Path file = Files.createTempFile("indent-input-", ".txt");

        try {
            Files.writeString(file, dataFromOutside, StandardCharsets.UTF_8);
            String received = Files.readString(file, StandardCharsets.UTF_8);

            System.out.println("raw: " + visible(received));
            System.out.println("stripIndent: " + visible(received.stripIndent()));

            String withFinalNewline = received + "\r\n";
            System.out.println("final CRLF: "
                    + visible(withFinalNewline.stripIndent()));
            System.out.println("trailing removed first: "
                    + visible(withFinalNewline.stripTrailing().stripIndent()));

            String spaced = "    A\n      B";
            System.out.println("strip: " + visible(spaced.strip()));
            System.out.println("stripIndent 2: " + visible(spaced.stripIndent()));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 ExternalStripIndentDemo.java
java ExternalStripIndentDemo
~~~

**Stdout chính xác:**

~~~text
raw: [    <list>\r\n      <item>Tea</item>   \r\n    </list>]
stripIndent: [<list>\n  <item>Tea</item>\n</list>]
final CRLF: [    <list>\n      <item>Tea</item>\n    </list>\n]
trailing removed first: [<list>\n  <item>Tea</item>\n</list>]
strip: [A\n      B]
stripIndent 2: [A\n  B]
~~~

Phân tích các dòng kết quả:

- **raw:** giữ đúng nội dung đọc từ tệp, gồm CRLF và ba dấu cách ở cuối dòng item.
- **stripIndent:** bỏ 4 dấu cách đầu dòng chung; dòng item vẫn thụt 2 dấu cách; các khoảng trắng cuối dòng item bị bỏ; CRLF đổi thành LF.
- **final CRLF:** khi dữ liệu kết thúc bằng CRLF, mức thụt lề chung thực tế bằng 0, nên cả khối vẫn thụt vào; CRLF cuối trở thành LF.
- **trailing removed first:** bỏ phần trắng cuối văn bản trước khi khử thụt lề nên có thể dời khối về trái; đổi lại, dấu xuống dòng cuối bị mất.
- **strip / stripIndent 2:** phương thức strip() chỉ loại whitespace **ở hai đầu toàn bộ String**; nó không đồng loạt loại thụt lề chung từng dòng. stripIndent() loại mức chung và bảo toàn phần thụt vào tương đối của dòng B.

Chương trình đã được biên dịch bằng **javac --release 17** và chạy trên JDK 24. Tệp tạm được xóa trong khối finally kể cả khi quá trình đọc hoặc ghi phát sinh IOException.

## 5. Chọn API phù hợp với dữ liệu nhận được

| Nhu cầu | API / cách làm | Điều cần chú ý |
| --- | --- | --- |
| Xóa whitespace ở **đầu và cuối toàn bộ** đoạn văn | **strip()** | Không xử lý đồng đều đầu từng dòng; có thể bỏ các newline cuối. |
| Xóa whitespace ở **cuối toàn bộ** đoạn văn | **stripTrailing()** | Mất các dòng trống hoặc newline cuối; chỉ dùng nếu cho phép. |
| Loại phần **thụt lề chung** của khối đa dòng | **stripIndent()** | Có trường hợp newline cuối làm mức thụt lề chung bằng 0; whitespace cuối từng dòng bị bỏ. |
| Thêm hoặc bớt **số ký tự thụt lề cố định** trên từng dòng | **indent(int n)** | Quy tắc khác stripIndent(); cần xem rõ tác động lên newline. |
| Giữ nguyên văn bản để xác minh chữ ký, so sánh byte, lưu log pháp lý hoặc phân tích giao thức | **Không biến đổi tùy tiện** | Hãy lưu/kiểm tra bản gốc; chỉ chuẩn hóa khi định dạng dữ liệu cho phép. |

Đặc biệt, **stripIndent() không phải thuật toán định dạng lại nội dung tùy ý**. Với YAML, Markdown, mã nguồn Python, dữ liệu căn cột hoặc văn bản mà khoảng trắng có ngữ nghĩa, thụt lề và whitespace cuối dòng có thể là một phần của nội dung đúng. Việc tự động biến đổi có thể làm sai dữ liệu.

## 6. Những trường hợp cần thận trọng với nguồn bên ngoài

**Chuỗi không phải văn bản đa dòng:** một String ngắn hoặc không có thụt lề chung thường không cần stripIndent(). Việc gọi phương thức không thay thế kiểm tra schema và định dạng.

**Nội dung chứa tab:** Character.isWhitespace tính mỗi tab là một đơn vị whitespace, không đo chiều rộng hiển thị. Đừng trông đợi nó căn chỉnh chính xác các cột lẫn tab và dấu cách.

**Dữ liệu CRLF từ Windows:** stripIndent() chuẩn hóa các dấu xuống dòng về LF. Điều này thuận tiện cho hiển thị và xử lý nội bộ, nhưng không phù hợp nếu cần giữ nguyên byte của tệp gốc hoặc gửi lại đúng giao thức yêu cầu CRLF.

**Dòng trống và khoảng trắng cuối dòng:** dòng trống được biến thành chuỗi rỗng; whitespace cuối dòng không trống bị loại. Nếu dấu cách cuối dòng có ý nghĩa (ví dụ một số cú pháp Markdown hoặc văn bản định dạng cố định), cần cân nhắc trước khi xử lý.

**Văn bản lớn:** Files.readString và các phép biến đổi String xử lý dữ liệu trong bộ nhớ. Nếu đầu vào rất lớn, hãy đặt giới hạn kích thước và cân nhắc thuật toán xử lý nhiều dòng có quy tắc rõ ràng; tìm thụt lề tối thiểu toàn khối thường cần xem xét toàn bộ dữ liệu.

**Dữ liệu không tin cậy:** stripIndent() chỉ xử lý whitespace. Nó **không** escape HTML, không chống SQL injection và không làm sạch script. Để đưa dữ liệu từ người dùng vào SQL, HTML hoặc JSON, dùng API tham số hóa hay thư viện encoding/serialization tương ứng.

**Chuỗi null hoặc lỗi I/O:** phương thức là lời gọi trên một String; nếu biến nhận dữ liệu là null thì gọi trực tiếp sẽ gây NullPointerException. Các thao tác đọc/ghi tệp có thể phát sinh IOException, vì vậy cần xử lý lỗi và tài nguyên thích hợp.

**Dấu backslash và chữ n:** khi đọc văn bản thực từ tệp, hai ký tự backslash + n không tự thành ký tự xuống dòng. stripIndent() không biên dịch lại escape sequence của ngôn ngữ Java. Nó chỉ nhìn thấy các ký tự thật đã có trong String.

## 7. Quy trình áp dụng trong ứng dụng

1. **Biết chính xác nguồn văn bản.** Dùng charset rõ ràng khi đọc tệp và hiểu API mạng trả về nội dung đã giải mã hay chưa.
2. **Xác định whitespace nào chỉ dùng để trình bày.** Chỉ loại thụt lề chung nếu định dạng và người dùng chấp nhận điều đó.
3. **Kiểm tra phần cuối chuỗi.** Phân biệt không có newline, có một newline, có nhiều dòng trống cuối và dòng cuối chỉ chứa whitespace.
4. **Chọn cách chuẩn hóa phù hợp.** stripIndent() phù hợp với khối có phần thụt lề chung; stripTrailing().stripIndent() chỉ phù hợp khi có thể bỏ whitespace cuối toàn bộ chuỗi.
5. **Kiểm thử bằng chuỗi có dấu xuống dòng và whitespace hiển thị rõ.** So sánh equals với giá trị mong muốn hoặc hiển thị các ký tự \r, \n, \t trong test. Kiểm tra cả file dùng CRLF lẫn LF, dòng rỗng, dấu tab và chuỗi trống.
6. **Giữ bản gốc nếu cần kiểm tra hoặc khôi phục.** Phương thức trả về String khác về mặt giá trị khi có thay đổi; lưu riêng bản gốc khi có yêu cầu audit, chữ ký hoặc xử lý lại.

## 8. Ghi nhớ

**String.stripIndent()** dùng để loại phần thụt lề không chủ ý trên một **String đa dòng đã nhận được tại runtime**. Nó tính mức thụt lề chung, giữ mức thụt lề tương đối, bỏ whitespace cuối từng dòng không trống và chuẩn hóa CR/LF/CRLF thành LF. Với dữ liệu bên ngoài, **đặc biệt phải kiểm tra newline cuối**, vì nó có thể khiến khối không được dịch trái. Chỉ dùng khi quy tắc của dữ liệu cho phép thay đổi whitespace.

## Tham khảo

- Tài liệu chính thức Oracle, **String.stripIndent()**, Java 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#stripIndent()
- Tài liệu chính thức Oracle, **Text Blocks**, Java 17: https://docs.oracle.com/en/java/javase/17/text-blocks/index.html
