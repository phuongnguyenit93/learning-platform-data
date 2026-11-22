# Content type của tệp và FileTypeMap

Khi gửi email có tệp đính kèm bằng **Spring Framework Mail**, ứng dụng không chỉ cần cung cấp byte của tệp và tên file. Mỗi phần MIME còn cần mô tả **loại nội dung (Content-Type)** để email client biết dữ liệu đó là PDF, ảnh PNG, CSV, tài liệu Word hay một luồng byte tổng quát. Nếu khai báo sai, người nhận có thể thấy file với biểu tượng không đúng, không mở được bằng ứng dụng mong muốn hoặc gặp hành vi xử lý khác dự kiến.

Spring cung cấp **MimeMessageHelper** để thêm attachment và inline resource. Khi chỉ truyền tên file cùng một **InputStreamSource**, helper cần xác định MIME type cho part. Cơ chế **FileTypeMap** của Jakarta Activation thực hiện việc ánh xạ tên file hoặc phần mở rộng sang loại nội dung. Lập trình viên cũng có thể chỉ định MIME type tường minh khi đã biết chính xác loại dữ liệu.

Bài học này giải thích vai trò của **Content-Type**, cách **FileTypeMap** hoạt động, cách cấu hình mapping cho định dạng riêng và cách kiểm tra kết quả trong **MimeMessage**. Phần cuối trình bày các giới hạn quan trọng: đuôi file không chứng minh nội dung thật, **application/octet-stream** là fallback tổng quát, và MIME type không thay thế kiểm tra an toàn tệp.

## 1. Content-Type trong một MIME attachment

Email hỗ trợ nhiều loại nội dung nhờ MIME (*Multipurpose Internet Mail Extensions*). Một attachment thường được biểu diễn như một **body part** bên trong cấu trúc multipart của email.

Ví dụ một PDF đính kèm có thể có các header:

~~~text
Content-Type: application/pdf
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="invoice.pdf"

JVBERi0xLjQK...
~~~

Ba header trên phục vụ ba mục đích riêng:

| Header | Vai trò | Ví dụ |
| --- | --- | --- |
| **Content-Type** | Mô tả loại dữ liệu của part | application/pdf |
| **Content-Transfer-Encoding** | Mô tả cách byte được biểu diễn trong nội dung MIME | base64, quoted-printable, 7bit |
| **Content-Disposition** | Gợi ý cách part được trình bày và tên file | attachment; filename="invoice.pdf" |

**Content-Type không phải tên file.** application/pdf cho biết part chứa dữ liệu PDF; invoice.pdf là tên file được cung cấp cho người nhận. Hai giá trị thường tương ứng, nhưng chúng không tự động xác minh lẫn nhau.

**Content-Transfer-Encoding cũng không quyết định định dạng file.** Base64 có thể được dùng để vận chuyển byte PDF, ảnh PNG hoặc tệp ZIP. Sau khi giải mã transfer encoding, byte gốc vẫn thuộc loại dữ liệu do Content-Type mô tả.

### Cấu trúc media type

Một media type có dạng tổng quát:

~~~text
type/subtype; parameter=value
~~~

Ví dụ:

| Media type | Ý nghĩa |
| --- | --- |
| application/pdf | Tài liệu PDF |
| image/png | Ảnh PNG |
| image/jpeg | Ảnh JPEG |
| text/plain; charset=UTF-8 | Văn bản thuần UTF-8 |
| text/csv; charset=UTF-8 | Dữ liệu CSV dạng văn bản UTF-8 |
| application/zip | Tệp ZIP |
| application/json | Dữ liệu JSON |
| application/octet-stream | Dữ liệu byte tổng quát, chưa mô tả cụ thể |

Phần **type** thường là nhóm tổng quát như text, image, audio, video, application hoặc multipart. Phần **subtype** xác định định dạng cụ thể hơn. Các tham số có thể cung cấp charset hoặc thông tin khác tùy loại nội dung.

### Content-Type ảnh hưởng điều gì?

Email client sử dụng MIME metadata để quyết định cách diễn giải part:

- Một part application/pdf có thể được nhận diện là tài liệu PDF.
- Một part image/png có thể được xem là ảnh.
- Một part text/csv có thể được mở bằng ứng dụng bảng tính hoặc trình xem văn bản.
- Một part application/octet-stream thường được coi là dữ liệu nhị phân tổng quát và có thể yêu cầu người dùng chọn ứng dụng mở.

Đây là **gợi ý định dạng cho phần mềm nhận**, không phải mệnh lệnh bắt buộc. Email client, hệ điều hành và chính sách bảo mật vẫn có thể chọn hành vi khác.

## 2. FileTypeMap là gì?

**FileTypeMap** là lớp trừu tượng thuộc Jakarta Activation, cung cấp cơ chế ánh xạ tên file hoặc đối tượng file sang **MIME content type**. Spring Mail sử dụng cơ chế này khi chuẩn bị MIME body part cho attachment hoặc inline resource mà ứng dụng chưa cung cấp Content-Type cụ thể.

Các API chính nằm trong package:

~~~java
import jakarta.activation.FileTypeMap;
import jakarta.activation.MimetypesFileTypeMap;
~~~

FileTypeMap định nghĩa các phương thức tra cứu MIME type. MimetypesFileTypeMap là một implementation phổ biến, có thể đọc các mapping dạng MIME type và phần mở rộng.

Ví dụ ý tưởng:

~~~java
FileTypeMap map = FileTypeMap.getDefaultFileTypeMap();

String pdfType = map.getContentType("invoice.pdf");
String pngType = map.getContentType("logo.png");
String unknownType = map.getContentType("archive.unknownext");
~~~

Kết quả thường gặp có thể là:

~~~text
invoice.pdf              -> application/pdf
logo.png                 -> image/png
archive.unknownext       -> application/octet-stream
~~~

Kết quả cụ thể phụ thuộc implementation, mapping được nạp, môi trường runtime và cấu hình của ứng dụng. Không nên coi một tập mapping mặc định là giống hệt trên mọi máy.

### FileTypeMap tra cứu theo tên, không xác minh nội dung

Một điểm rất quan trọng: **FileTypeMap chủ yếu suy luận từ tên file/phần mở rộng**. Nếu một tệp văn bản được đặt tên report.pdf, mapping có thể trả về application/pdf dù bytes không phải PDF.

Ví dụ:

~~~text
Tên file: invoice.pdf
Nội dung thật: plain text "hello"

FileTypeMap có thể trả: application/pdf
~~~

Đây không phải lỗi của FileTypeMap. Nó đã trả lời câu hỏi **“đuôi tên này thường tương ứng với MIME type nào?”**, chứ không trả lời **“byte trong file thực sự là định dạng gì?”**.

Muốn xác minh nội dung, ứng dụng cần thêm quy trình kiểm tra bytes hoặc dùng parser phù hợp với loại tệp, cùng chính sách bảo mật và danh sách định dạng được phép.

## 3. MimeMessageHelper dùng FileTypeMap như thế nào?

Spring Mail cung cấp **MimeMessageHelper** để thêm attachment và inline resource mà không phải tự tạo MimeBodyPart hay đặt boundary MIME bằng tay.

Một lời gọi thường gặp:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(invoicePath)
);
~~~

Ở overload này, ứng dụng truyền:

- Tên attachment sẽ xuất hiện với người nhận: invoice.pdf.
- Một **InputStreamSource** cung cấp nội dung file.

Helper cần xác định Content-Type cho part. Nó sử dụng **FileTypeMap** được cấu hình cho helper để suy luận từ tên file. Sau đó, helper tạo body part và gắn nguồn dữ liệu.

Luồng khái niệm:

~~~text
MimeMessageHelper.addAttachment(filename, resource)
                 |
                 v
          FileTypeMap
                 |
                 | filename -> MIME type
                 v
          application/pdf
                 |
                 v
          MIME body part
          Content-Type: application/pdf
          Content-Disposition: attachment
                 |
                 v
          MimeMessage
                 |
                 v
          JavaMailSender.send(...)
~~~

### Tên attachment có thể khác tên file nguồn

Ví dụ:

~~~java
helper.addAttachment(
        "monthly-report.pdf",
        new FileSystemResource(sourcePath)
);
~~~

MIME type được suy luận từ **attachment filename** mà helper sử dụng. Nếu tên file nguồn có phần mở rộng khác hoặc không có phần mở rộng, nhưng tên attachment truyền vào là .pdf, kết quả tra cứu có thể theo .pdf.

Điều này hữu ích khi ứng dụng đổi tên file cho người nhận, nhưng cũng là lý do cần kiểm tra **tên file và MIME type có khớp với nội dung thật không**. Đặt tên .pdf không biến dữ liệu bất kỳ thành PDF.

### Attachment và inline resource cùng cần MIME type

Khi thêm ảnh nội tuyến:

~~~java
helper.addInline(
        "company-logo",
        new FileSystemResource(logoPath)
);
~~~

Part ảnh cũng cần Content-Type để email client biết cách diễn giải byte. Nếu suy luận từ tên file, logo.png có thể được ánh xạ thành image/png; một tên không có phần mở rộng hoặc mapping thiếu có thể rơi về kiểu tổng quát.

Nếu đã biết chính xác loại ảnh, có thể truyền MIME type tường minh vào overload phù hợp. Việc xác định Content-Type không thay thế **Content-ID** và cấu trúc multipart/related; đó là những phần riêng để HTML tham chiếu ảnh.

## 4. MIME type mặc định và application/octet-stream

Khi không tìm được mapping cho tên file, implementation phổ biến của MimetypesFileTypeMap thường trả về:

~~~text
application/octet-stream
~~~

Đây là media type tổng quát cho một luồng byte. Nó có nghĩa ứng dụng không cung cấp được loại cụ thể hơn từ mapping hiện có.

Ví dụ:

| Tên file | Kết quả có thể gặp |
| --- | --- |
| photo.png | image/png |
| invoice.pdf | application/pdf |
| notes.txt | text/plain |
| data.unknownext | application/octet-stream |
| payload | application/octet-stream |

Không nên coi application/octet-stream là lỗi gửi email. Tệp vẫn có thể được đính kèm và tải xuống; client chỉ thiếu thông tin định dạng cụ thể. Nhưng nếu nghiệp vụ yêu cầu recipient nhận một PDF, CSV hoặc ảnh với Content-Type rõ ràng, nên cung cấp mapping hoặc chỉ định MIME type tường minh.

### Không thay octet-stream bằng một loại tùy tiện

Khi thấy application/octet-stream, không nên đặt mọi file thành application/pdf hoặc application/zip chỉ để biểu tượng attachment trông đẹp hơn. Một MIME type sai có thể khiến phần mềm nhận cố mở byte bằng parser không phù hợp.

Hãy xác định định dạng thực tế từ nguồn dữ liệu có thẩm quyền, rồi chọn MIME type phù hợp. Nếu không xác định được, giữ kiểu tổng quát hoặc từ chối tệp tùy chính sách sản phẩm.

## 5. Các cách cung cấp Content-Type trong Spring Mail

Có ba cách thường dùng:

1. Để **FileTypeMap** suy luận từ filename.
2. Cấu hình **mapping tùy chỉnh** để tên phần mở rộng được nhận diện.
3. Truyền **Content-Type tường minh** khi gọi phương thức thêm attachment/inline resource.

Lựa chọn phù hợp phụ thuộc vào nguồn dữ liệu và mức độ chắc chắn về định dạng.

### Cách 1: Dùng mapping mặc định

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setTo(recipient);
helper.setSubject("Tài liệu");
helper.setText("Tệp được đính kèm.");

helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(invoicePath)
);

mailSender.send(message);
~~~

Với mapping mặc định phù hợp, .pdf thường được nhận diện là application/pdf. Cách này đơn giản khi dùng các định dạng phổ biến và runtime đã có mapping tương ứng.

### Cách 2: Chỉ định Content-Type khi thêm attachment

Khi ứng dụng đã biết loại dữ liệu từ một nguồn đáng tin cậy:

~~~java
helper.addAttachment(
        "export.csv",
        new FileSystemResource(csvPath),
        "text/csv; charset=UTF-8"
);
~~~

Hoặc:

~~~java
helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(invoicePath),
        "application/pdf"
);
~~~

Overload nhận **contentType** giúp tránh phụ thuộc mapping theo tên file cho part đó. Nó đặc biệt hữu ích với tên file do ứng dụng tự tạo, tên không có extension hoặc loại nội dung không được mapping mặc định nhận diện.

**MIME type tường minh vẫn phải đúng với bytes thực tế.** Đây là cách khai báo metadata, không phải thao tác chuyển đổi định dạng. Nếu truyền application/pdf cho một CSV, part vẫn chứa byte CSV.

## 6. Tạo FileTypeMap tùy chỉnh

Khi ứng dụng thường xuyên đính kèm các định dạng mà mapping mặc định chưa nhận diện, có thể bổ sung mapping riêng. Với **MimetypesFileTypeMap**, phương thức **addMimeTypes(...)** nhận các dòng có dạng:

~~~text
mime/type extension1 extension2 ...
~~~

Ví dụ:

~~~java
import jakarta.activation.MimetypesFileTypeMap;

MimetypesFileTypeMap fileTypeMap = new MimetypesFileTypeMap();
fileTypeMap.addMimeTypes("text/csv csv");
fileTypeMap.addMimeTypes(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document docx"
);
fileTypeMap.addMimeTypes(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet xlsx"
);
fileTypeMap.addMimeTypes("application/x-example-report rptx");
~~~

Mapping này cho biết:

| Phần mở rộng | MIME type |
| --- | --- |
| docx | application/vnd.openxmlformats-officedocument.wordprocessingml.document |
| xlsx | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| csv | text/csv |
| rptx | application/x-example-report |

Hai MIME type đầu là loại thường dùng cho định dạng Office Open XML. **application/x-example-report** chỉ là ví dụ về media type riêng của một ứng dụng; khi thiết kế định dạng thực tế, nên chọn loại đã đăng ký hoặc loại vendor phù hợp theo quy ước của tổ chức.

Sau khi tạo mapping, có thể tra cứu:

~~~java
System.out.println(fileTypeMap.getContentType("quarterly.docx"));
System.out.println(fileTypeMap.getContentType("sales.xlsx"));
System.out.println(fileTypeMap.getContentType("export.csv"));
~~~

Mapping chỉ ảnh hưởng đến các lần tra cứu dùng đúng instance **fileTypeMap**. Tạo một object mapping riêng không tự động thay đổi mọi FileTypeMap trong JVM.

### Cấu hình mapping cho MimeMessageHelper

Một cách dùng là truyền FileTypeMap vào constructor của **MimeMessageHelper**:

~~~java
import jakarta.activation.FileTypeMap;
import jakarta.activation.MimetypesFileTypeMap;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.MimeMessageHelper;

MimetypesFileTypeMap fileTypeMap = new MimetypesFileTypeMap();
fileTypeMap.addMimeTypes("text/csv csv");

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8",
        (FileTypeMap) fileTypeMap
);

helper.setTo(recipient);
helper.setSubject("Báo cáo");
helper.setText("Báo cáo được đính kèm.");
helper.addAttachment(
        "sales.csv",
        new FileSystemResource(csvPath)
);
~~~

Với constructor nhận **FileTypeMap**, helper sử dụng mapping đã cung cấp khi cần suy luận MIME type cho các part. Hãy kiểm tra API của phiên bản Spring Framework trong dự án nếu đang dùng phiên bản cũ; chữ ký constructor có thể khác giữa các thế hệ thư viện.

### Quản lý FileTypeMap như một Spring bean

Nếu nhiều service gửi các loại file giống nhau, có thể tạo một bean dùng chung:

~~~java
import jakarta.activation.FileTypeMap;
import jakarta.activation.MimetypesFileTypeMap;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MailAttachmentConfiguration {

    @Bean
    public FileTypeMap mailFileTypeMap() {
        MimetypesFileTypeMap map = new MimetypesFileTypeMap();
        map.addMimeTypes("text/csv csv");
        map.addMimeTypes("application/x-example-report rptx");
        return map;
    }
}
~~~

Service nhận bean và truyền vào helper:

~~~java
import jakarta.activation.FileTypeMap;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.Resource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class AttachmentMailService {

    private final JavaMailSender mailSender;
    private final FileTypeMap fileTypeMap;

    public AttachmentMailService(
            JavaMailSender mailSender,
            FileTypeMap fileTypeMap
    ) {
        this.mailSender = mailSender;
        this.fileTypeMap = fileTypeMap;
    }

    public void sendReport(String recipient, Resource report)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED,
                "UTF-8",
                fileTypeMap
        );

        helper.setTo(recipient);
        helper.setSubject("Báo cáo");
        helper.setText("Báo cáo được đính kèm.");
        helper.addAttachment("monthly-report.rptx", report);

        mailSender.send(message);
    }
}
~~~

Việc đăng ký bean giúp các service dùng cùng một bộ mapping. Nên coi map sau khi khởi tạo là **cấu hình dùng chung, không sửa đổi tùy tiện theo từng request**. Nếu một service cần ngoại lệ riêng cho một loại file, hãy truyền Content-Type tường minh ở lời gọi đó hoặc tạo một map riêng có phạm vi rõ ràng.

### Vì sao không thay FileTypeMap mặc định toàn JVM?

Jakarta Activation có API để thiết lập **default FileTypeMap** dùng chung. Thay đổi default toàn cục có thể ảnh hưởng các thành phần khác trong cùng tiến trình, không chỉ Spring Mail:

- Một thư viện khác cũng có thể dùng FileTypeMap mặc định.
- Test chạy song song có thể phụ thuộc lẫn nhau nếu thay đổi global state.
- Một cấu hình riêng của một module có thể vô tình làm thay đổi MIME type ở module khác.
- Khó xác định nơi đã thay đổi default khi điều tra lỗi.

Trong ứng dụng Spring, truyền một instance cụ thể vào **MimeMessageHelper** thường làm phạm vi cấu hình rõ ràng và dễ kiểm thử hơn.

## 7. Tệp mapping và nhiều phần mở rộng

Ngoài gọi **addMimeTypes(...)** trong Java, **MimetypesFileTypeMap** có thể nạp mapping từ nguồn cấu hình MIME types mà implementation hỗ trợ. Một file mapping đơn giản có dạng:

~~~text
text/csv csv
application/x-example-report rptx
application/vnd.openxmlformats-officedocument.presentationml.presentation pptx
image/webp webp
~~~

Mỗi dòng chứa media type rồi tới một hoặc nhiều phần mở rộng. Không cần thêm dấu chấm trước extension trong mapping thông thường.

Một MIME type có thể ứng với nhiều extension:

~~~text
image/jpeg jpeg jpg jpe
~~~

Và một extension có thể có mapping khác nhau trong các hệ thống cấu hình khác nhau. Nếu có nhiều mapping trùng nhau, kết quả phụ thuộc quy tắc nạp/ưu tiên của implementation và nguồn mapping; không nên dựa vào thứ tự tình cờ. Hãy giữ mapping nhất quán, tránh khai báo cùng extension thành nhiều MIME type trái ngược.

### Định dạng compound extension

Tên như:

~~~text
backup.tar.gz
~~~

thường được tra cứu dựa trên phần mở rộng cuối cùng theo quy tắc của FileTypeMap, tức **gz**, chứ không nhất thiết hiểu cả chuỗi **tar.gz** như một loại file riêng. Một số hệ thống mapping có thể hỗ trợ quy tắc riêng, nhưng không nên mặc định FileTypeMap nhận diện cấu trúc compound extension.

Nếu nghiệp vụ cần phân biệt **.tar.gz** với **.gz** khác, hãy dùng logic phân loại tệp rõ ràng trước khi gọi helper và truyền Content-Type phù hợp.

### Extension và chữ hoa/thường

Các tên **REPORT.PDF** và **report.pdf** thường được nhận cùng loại qua mapping phổ biến. Tuy nhiên, nếu tự xây một FileTypeMap tùy chỉnh, cần quy định chuẩn hóa tên extension nhất quán; không tự giả định mọi implementation tùy biến đều xử lý chữ hoa/thường như nhau.

## 8. Phân biệt FileTypeMap với các cách dò MIME khác

Trong Java có nhiều API có thể trả về MIME type dựa trên tên hoặc đường dẫn. Chúng không phải cùng một cơ chế.

| API/cơ chế | Nguồn suy luận chính | Điểm cần lưu ý |
| --- | --- | --- |
| **Jakarta Activation FileTypeMap** | Mapping theo tên file hoặc File | Được Jakarta Mail/Activation sử dụng trong luồng MIME |
| **MimetypesFileTypeMap** | Các mapping MIME types được nạp | Có thể bổ sung mapping riêng |
| **Files.probeContentType(Path)** | File type detector/provider của hệ điều hành hoặc runtime | Kết quả phụ thuộc môi trường, có thể trả null |
| **URLConnection.guessContentTypeFromName(...)** | Tên file và mapping của URLConnection | Là cơ chế đoán theo tên, không xác minh bytes |
| **Magic-byte detector/parser** | Chữ ký byte hoặc cấu trúc nội dung | Có thể nhận diện nội dung tốt hơn nhưng không bảo đảm an toàn tuyệt đối |

Ví dụ với NIO:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("report.pdf");
String detected = Files.probeContentType(file);
~~~

**Files.probeContentType(...)** có thể trả về null nếu không có detector nhận diện. Kết quả có thể khác giữa Windows, Linux, macOS, container và provider runtime. Nó không nhất thiết dùng cùng mapping với **MimetypesFileTypeMap**.

### Không trộn các kết quả mà không có chính sách

Giả sử:

~~~text
FileTypeMap.getContentType("report.pdf")
    -> application/pdf

Files.probeContentType(path)
    -> application/octet-stream
~~~

Hai API có thể dùng nguồn mapping khác nhau. Ứng dụng cần quyết định **nguồn nào có thẩm quyền** cho luồng gửi email. Nếu hệ thống đã biết định dạng từ quy trình tạo PDF, dùng MIME type đã xác định theo nghiệp vụ thường rõ ràng hơn việc hỏi nhiều detector rồi chọn ngẫu nhiên kết quả đầu tiên.

### Magic bytes cũng chỉ là một tín hiệu

Một số định dạng có chữ ký byte đặc trưng, ví dụ PDF thường bắt đầu bằng chuỗi byte tương ứng với %PDF-. Kiểm tra magic bytes giúp phát hiện một số file giả mạo phần mở rộng, nhưng:

- Một tệp có thể chứa header đúng nhưng phần nội dung phía sau bị hỏng.
- Nhiều định dạng dùng chung container hoặc cấu trúc ZIP.
- File có thể chứa nội dung chủ động gây hại dù chữ ký đúng.
- Một file hợp lệ về định dạng vẫn có thể chứa macro, script hoặc nội dung nguy hiểm.

Vì vậy, kết hợp extension, MIME mapping, signature detection và parser/antivirus theo chính sách là cách tiếp cận phù hợp hơn nếu ứng dụng nhận file từ nguồn không tin cậy.

## 9. Kiểm tra Content-Type sau khi MimeMessageHelper tạo attachment

Sau khi helper tạo MIME part, có thể kiểm tra **Content-Type**, **Content-Disposition** và **filename** trực tiếp từ message. Việc này giúp xác nhận metadata đã được gắn đúng trước khi gửi.

Ví dụ tạo một message để kiểm tra:

~~~java
import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8"
);

helper.setTo("learner@example.test");
helper.setSubject("Tài liệu");
helper.setText("Tệp PDF được đính kèm.");
helper.addAttachment(
        "invoice.pdf",
        new FileSystemResource(Path.of("data/invoice.pdf"))
);

message.saveChanges();
~~~

Sau đó, đọc root multipart và các part con:

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;

Object content = message.getContent();
if (content instanceof Multipart multipart) {
    for (int i = 0; i < multipart.getCount(); i++) {
        BodyPart part = multipart.getBodyPart(i);
        System.out.println("type=" + part.getContentType());
        System.out.println("disposition=" + part.getDisposition());
        System.out.println("filename=" + part.getFileName());
    }
}
~~~

Với attachment PDF, kết quả dự kiến có dạng:

~~~text
type=application/pdf
disposition=attachment
filename=invoice.pdf
~~~

Đầu ra thực tế có thể có thêm tham số charset, boundary hoặc thông tin header khác. **Content-Type** thường có thể là application/pdf mà không có charset vì PDF là dữ liệu nhị phân.

### Duyệt multipart đệ quy

Một email phức tạp có thể chứa **multipart/mixed** ở root, bên trong có **multipart/related** và **multipart/alternative**. Nếu chỉ kiểm tra part trực tiếp của root, có thể bỏ sót attachment hoặc inline resource nằm sâu hơn.

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Message;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.MessagingException;
import java.io.IOException;

public final class AttachmentInspector {

    private AttachmentInspector() {
    }

    public static void inspect(Part part)
            throws MessagingException, IOException {

        String type = part.getContentType();
        String disposition = part.getDisposition();
        String filename = part.getFileName();

        System.out.printf(
                "type=%s disposition=%s filename=%s%n",
                type,
                disposition,
                filename
        );

        if (part.isMimeType("multipart/*")) {
            Object content = part.getContent();
            if (content instanceof Multipart multipart) {
                for (int i = 0; i < multipart.getCount(); i++) {
                    BodyPart child = multipart.getBodyPart(i);
                    inspect(child);
                }
            }
        } else if (part.isMimeType("message/rfc822")) {
            Object content = part.getContent();
            if (content instanceof Message nested) {
                inspect(nested);
            }
        }
    }
}
~~~

Hàm trên chỉ in metadata và đi sâu vào container multipart/nested message. Nó không đọc payload của file. Đây là lựa chọn an toàn hơn khi chỉ cần kiểm tra cấu trúc; tránh gọi **getContent()** trên mọi part nhị phân nếu không cần thiết.

### Đừng kiểm tra chỉ bằng filename

Nếu test chỉ xác nhận:

~~~java
assertEquals("invoice.pdf", part.getFileName());
~~~

thì vẫn chưa chứng minh Content-Type đúng. Cần kiểm tra ít nhất:

~~~java
assertTrue(part.isMimeType("application/pdf"));
assertEquals(Part.ATTACHMENT, part.getDisposition());
assertEquals("invoice.pdf", part.getFileName());
~~~

Tùy phiên bản Jakarta Mail và cách serialize, disposition có thể khác chữ hoa/thường hoặc được biểu diễn với tham số; khi so sánh trong test, nên dùng kiểm tra không phân biệt hoa/thường hoặc kiểm tra giá trị đã chuẩn hóa.

## 10. Kiểm thử mapping và attachment

Có thể kiểm tra FileTypeMap độc lập với SMTP:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import jakarta.activation.MimetypesFileTypeMap;
import org.junit.jupiter.api.Test;

class MailFileTypeMapTest {

    @Test
    void mapsCustomReportExtension() {
        MimetypesFileTypeMap map = new MimetypesFileTypeMap();
        map.addMimeTypes("application/x-example-report rptx");

        assertEquals(
                "application/x-example-report",
                map.getContentType("monthly.rptx")
        );
    }
}
~~~

Test này chỉ xác nhận **mapping theo tên file**. Nó không kiểm tra nội dung của file hoặc MIME message đã được gửi.

### Kiểm tra MIME part được tạo từ helper

Một bài test có thể tạo message trong bộ nhớ, thêm attachment rồi đọc part:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

class AttachmentContentTypeTest {

    private final JavaMailSender mailSender = createTestMailSender();

    @Test
    void createsPdfAttachmentWithExpectedContentType() throws Exception {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED,
                "UTF-8"
        );

        helper.setTo("learner@example.test");
        helper.setSubject("Invoice");
        helper.setText("Attached.");
        helper.addAttachment(
                "invoice.pdf",
                new FileSystemResource(Path.of("src/test/resources/invoice.pdf"))
        );

        message.saveChanges();
        Multipart multipart = (Multipart) message.getContent();

        Part attachment = multipart.getBodyPart(1);
        assertTrue(attachment.isMimeType("application/pdf"));
        assertEquals(Part.ATTACHMENT, attachment.getDisposition());
        assertEquals("invoice.pdf", attachment.getFileName());
    }
}
~~~

**createTestMailSender()** là hàm thiết lập JavaMailSender phù hợp với test, không phải API có sẵn của Spring. Ví dụ giả định body text là part đầu và attachment là part thứ hai trong cấu trúc đơn giản này. Nếu thay multipart mode hoặc thêm inline/alternative parts, hãy tìm attachment theo **disposition + filename + MIME type** thay vì cố định index.

### Kiểm tra sau serialize

Để quan sát headers ở dạng MIME thực tế, có thể gọi **saveChanges()** rồi ghi message ra output stream trong test. Sau đó parse lại raw message bằng **MimeMessage(Session, InputStream)** và kiểm tra part. Việc này xác nhận metadata được biểu diễn trong MIME sau serialize, thay vì chỉ kiểm tra object đang xây dựng.

Không nên so sánh toàn bộ raw message với một chuỗi cố định vì boundary và một số headers được sinh tự động. Hãy parse MIME và kiểm tra **Content-Type**, **Content-Disposition**, filename cùng nội dung cần thiết.

## 11. Content-Type cho các loại tệp thường gặp

Một số media type thường được sử dụng khi đính kèm:

| Định dạng | Phần mở rộng thường gặp | MIME type |
| --- | --- | --- |
| PDF | pdf | application/pdf |
| PNG | png | image/png |
| JPEG | jpg, jpeg | image/jpeg |
| GIF | gif | image/gif |
| WebP | webp | image/webp |
| CSV | csv | text/csv |
| Văn bản thuần | txt | text/plain |
| JSON | json | application/json |
| XML | xml | application/xml |
| ZIP | zip | application/zip |
| GZIP | gz | application/gzip |
| Microsoft Word Open XML | docx | application/vnd.openxmlformats-officedocument.wordprocessingml.document |
| Microsoft Excel Open XML | xlsx | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| Microsoft PowerPoint Open XML | pptx | application/vnd.openxmlformats-officedocument.presentationml.presentation |

Danh sách trên là ví dụ thông dụng, không phải danh mục đầy đủ. Một số định dạng cũ có MIME type legacy hoặc vendor-specific; khi tích hợp với hệ thống ngoài, nên dùng loại mà hai bên thống nhất.

### Text file và charset

Với file văn bản, Content-Type có thể cần tham số charset:

~~~text
Content-Type: text/csv; charset=UTF-8
~~~

Điều này giúp mô tả cách giải mã byte văn bản. Nhưng **FileTypeMap thường ánh xạ extension sang media type cơ bản**, chẳng hạn text/csv; nó không nhất thiết tự thêm charset phù hợp với nội dung.

Nếu tạo CSV bằng UTF-8, hãy bảo đảm byte thực sự là UTF-8 rồi khai báo Content-Type tương ứng. Nếu byte dùng một encoding khác mà header ghi UTF-8, người nhận có thể thấy ký tự sai. Việc thêm charset vào header không tự chuyển đổi byte.

### Tệp nhị phân không cần charset

PDF, PNG, JPEG và ZIP là dữ liệu nhị phân. Không nên gắn charset UTF-8 vào các loại đó chỉ vì toàn email đang dùng UTF-8. Charset thường áp dụng cho nội dung text, còn byte của attachment nhị phân được bảo toàn qua cơ chế transfer encoding.

## 12. Khi nào nên dùng mapping, khi nào truyền MIME type tường minh?

| Tình huống | Lựa chọn gợi ý | Lý do |
| --- | --- | --- |
| Định dạng phổ biến, extension chuẩn | FileTypeMap mặc định | Đơn giản, ít cấu hình |
| Ứng dụng có định dạng riêng, extension ổn định | Mapping tùy chỉnh | Tái sử dụng cho nhiều attachment |
| Tên file do ứng dụng đổi hoặc không có extension | Content-Type tường minh | Không phụ thuộc tên file |
| Nội dung text cần charset cụ thể | Content-Type tường minh có charset | MIME type cơ bản không đủ mô tả encoding |
| Loại file được xác định từ metadata tin cậy của hệ thống | Truyền MIME type đã xác thực | Không phải đoán lại từ tên |
| File do người dùng tải lên, chưa được kiểm tra | Validate trước, chưa gửi ngay | Extension và MIME header không xác nhận an toàn |

Một hệ thống có thể kết hợp cả ba: dùng mapping mặc định cho file thông thường, bổ sung mapping riêng cho định dạng nội bộ và truyền explicit Content-Type cho từng part đặc biệt.

### Ví dụ CSV có charset UTF-8

~~~java
helper.addAttachment(
        "customers.csv",
        new FileSystemResource(csvPath),
        "text/csv; charset=UTF-8"
);
~~~

Đoạn mã giả định file nguồn đã được ghi bằng UTF-8. Nếu file thực tế là UTF-16 hoặc một encoding khác, cần chuyển byte sang UTF-8 trước khi khai báo. Content-Type chỉ mô tả dữ liệu hiện có, không tự biến đổi nó.

### Ví dụ ảnh inline có MIME type tường minh

~~~java
helper.addInline(
        "brand-logo",
        new FileSystemResource(logoPath),
        "image/png"
);
~~~

HTML có thể tham chiếu:

~~~html
<img src="cid:brand-logo" alt="Logo">
~~~

MIME type mô tả byte ảnh; Content-ID kết nối part ảnh với HTML; cấu trúc multipart/related gom các phần liên quan. Ba yếu tố có vai trò riêng và đều cần đúng.

## 13. Content-Type không phải cơ chế bảo mật tệp

Một lỗi thiết kế nghiêm trọng là tin rằng file an toàn chỉ vì:

- Phần mở rộng nằm trong danh sách cho phép.
- FileTypeMap trả về một MIME type hợp lệ.
- Client hiển thị biểu tượng PDF hoặc ảnh.
- Header Content-Type có vẻ đúng.

Những tín hiệu đó **không chứng minh byte là nội dung an toàn**. Kẻ tấn công có thể đổi tên file, tự đặt MIME type trong request hoặc gửi dữ liệu được tạo có chủ đích.

Ví dụ:

~~~text
Tên file do client gửi: invoice.pdf
Content-Type client khai báo: application/pdf
Bytes thật: nội dung khác hoặc dữ liệu độc hại
~~~

Nếu server chỉ tin tên file và header do client cung cấp rồi chuyển thẳng vào email, ứng dụng có thể phát tán nội dung sai định dạng hoặc nguy hiểm.

### Những lớp kiểm tra nên có

Với tệp đến từ người dùng hoặc hệ thống bên ngoài, có thể áp dụng:

1. **Allowlist loại tệp**: chỉ nhận định dạng nghiệp vụ thật sự cần.
2. **Giới hạn kích thước**: kiểm tra cả từng file và tổng dung lượng attachment.
3. **Chuẩn hóa tên file**: tránh path traversal, ký tự điều khiển, header injection và tên gây nhầm lẫn.
4. **Kiểm tra phần mở rộng**: dùng như một tín hiệu đầu vào, không phải bằng chứng cuối cùng.
5. **Kiểm tra signature/magic bytes**: phát hiện một số file đổi đuôi không phù hợp.
6. **Parse bằng thư viện chuyên dụng**: xác nhận cấu trúc nội dung theo loại file nếu nghiệp vụ yêu cầu.
7. **Quét malware**: áp dụng công cụ bảo mật phù hợp với môi trường.
8. **Xác định MIME type phía server**: chọn theo kết quả validation hoặc metadata tin cậy, không nhận nguyên giá trị tùy ý từ client.
9. **Kiểm soát quyền và vòng đời file**: chỉ cho phép đọc đúng nguồn file đã được kiểm tra, tránh thay thế file giữa bước validate và gửi.

Không phải mọi hệ thống đều cần mọi lớp ở cùng mức độ. Mức kiểm soát phụ thuộc loại dữ liệu, nguồn upload và hậu quả nếu phát tán file sai.

### Không tự nối raw MIME header

Không nên tạo header theo kiểu nối chuỗi từ dữ liệu người dùng:

~~~java
part.setHeader(
        "Content-Type",
        uploadedMimeType + "; name=" + uploadedFilename
);
~~~

Tên file hoặc MIME type không được kiểm soát có thể làm header sai định dạng hoặc gây injection nếu được ghép trực tiếp. Hãy dùng API MIME của Jakarta Mail/Spring, validate tên và loại dữ liệu, đồng thời để thư viện xử lý encoding/quoting phù hợp.

**MimeMessageHelper** giúp xây MIME part đúng cấu trúc; nó không thay thế validation của ứng dụng đối với dữ liệu upload.

### Tên file và quyền riêng tư

Tên attachment có thể chứa tên khách hàng, mã hồ sơ, số tài khoản hoặc thông tin nội bộ. Trước khi gửi email, nên tạo tên hiển thị vừa đủ, tránh đưa dữ liệu nhạy cảm không cần thiết vào filename.

Ví dụ thay vì dùng một đường dẫn nội bộ:

~~~text
/srv/app/private/customer-12345/medical-record-2026.pdf
~~~

có thể cung cấp tên hiển thị trung tính theo nghiệp vụ:

~~~text
document.pdf
~~~

Đường dẫn lưu trữ nội bộ không nên trở thành tên file hiển thị cho người nhận.

## 14. Một số lỗi thường gặp và cách điều tra

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Attachment hiện là application/octet-stream | Không có mapping cho extension hoặc tên file không có extension | Kiểm tra FileTypeMap đang được helper dùng và tên attachment |
| PDF bị khai báo là text/plain | Mapping sai hoặc extension được gán MIME type không đúng | Kiểm tra mapping trùng, explicit Content-Type và bytes nguồn |
| Ảnh inline không hiển thị | MIME type ảnh sai, Content-ID không khớp hoặc multipart/related không phù hợp | Kiểm tra Content-Type, Content-ID, HTML cid reference và MIME tree |
| CSV mở ra bị lỗi tiếng Việt | Charset header không khớp encoding byte | Kiểm tra byte file và khai báo charset |
| File có tên đúng nhưng mở không được | Nội dung thật không đúng định dạng, file hỏng hoặc thiếu bytes | Kiểm tra signature/parser và payload sau giải mã |
| Tên attachment bị sai ký tự | Filename encoding/quoting hoặc dữ liệu tên chưa chuẩn hóa | Kiểm tra getFileName() và raw MIME header |
| Không đọc được attachment lúc send | Resource không còn khả dụng hoặc InputStream chỉ đọc một lần | Kiểm tra vòng đời Resource và thời điểm serialize |
| Mapping tùy chỉnh không có tác dụng | Helper đang dùng một FileTypeMap khác | Kiểm tra constructor/bean được truyền vào helper |

### Mapping không được dùng như dự kiến

Nếu đã thêm mapping nhưng part vẫn có application/octet-stream, kiểm tra:

1. Attachment filename thực sự được truyền vào helper là gì?
2. FileTypeMap nào được gắn vào instance MimeMessageHelper?
3. Mapping có phần mở rộng đúng và cú pháp hợp lệ không?
4. Có một mapping khác xung đột với extension không?
5. Có overload explicit Content-Type nào ghi đè kết quả suy luận không?

Đừng chỉ kiểm tra FileTypeMap mặc định của JVM nếu helper đã được tạo với một instance riêng.

### Content-Type sai dù extension đúng

FileTypeMap không đọc nội dung file. Nếu một tệp sai định dạng nhưng có đuôi hợp lệ, mapping vẫn có thể trả về MIME type theo extension. Trong trường hợp này, việc thêm mapping khác không giải quyết vấn đề; cần kiểm tra bytes hoặc nguồn tạo file.

### Charset sai ở CSV

Một file CSV UTF-8 có thể được đính kèm với Content-Type text/csv nhưng không có charset. Nhiều client vẫn đoán đúng, nhưng không nên dựa vào hành vi đó khi nghiệp vụ yêu cầu dữ liệu đa ngôn ngữ. Hãy khai báo charset phù hợp và bảo đảm bytes thực sự dùng encoding đó.

Nếu file được tạo bởi một hệ thống ngoài, hãy kiểm tra encoding ở bước đọc/ghi dữ liệu. Không chuyển byte tùy tiện bằng cách đổi header.

## 15. Resource phải còn đọc được khi message được serialize

**MimeMessageHelper** nhận **InputStreamSource** hoặc **DataSource** để lấy nội dung attachment. Tùy loại nguồn, byte có thể được đọc khi tạo part hoặc muộn hơn lúc Jakarta Mail serialize/gửi message.

Vì vậy, cần bảo đảm resource còn khả dụng tới khi thư được gửi xong:

- **FileSystemResource** cần file tồn tại và tiến trình có quyền đọc.
- **ByteArrayResource** phù hợp với nội dung nhỏ đã có trong bộ nhớ.
- **InputStreamResource** thường đại diện một stream có thể chỉ mở/đọc một lần; cần thận trọng nếu thư viện cần mở lại stream.
- Resource lấy từ object storage cần còn quyền truy cập và không hết hạn trước khi serialize.

Ví dụ dùng ByteArrayResource cho file nhỏ:

~~~java
import org.springframework.core.io.ByteArrayResource;

byte[] reportBytes = createSmallReport();
ByteArrayResource resource = new ByteArrayResource(reportBytes);

helper.addAttachment(
        "report.pdf",
        resource,
        "application/pdf"
);
~~~

Ví dụ giả định **reportBytes** thực sự chứa PDF hợp lệ. ByteArrayResource giữ dữ liệu trong RAM; không nên dùng cách này cho attachment lớn nếu nó làm tăng đáng kể heap của ứng dụng.

### Không đóng stream quá sớm

Một lỗi thường gặp là tạo một InputStream, đóng nó sau khi gọi **addAttachment(...)**, rồi mới gọi **send(...)**. Nếu resource phụ thuộc stream đã đóng, quá trình serialize có thể thất bại.

Với API nhận **InputStreamSource**, hãy cung cấp nguồn có khả năng mở stream mới theo hợp đồng của nó. Nếu chỉ có một stream dùng một lần, hãy đọc vào một resource phù hợp trong giới hạn dung lượng hoặc thiết kế luồng gửi để quản lý vòng đời stream đúng thời điểm.

## 16. Dùng ConfigurableMimeFileTypeMap của Spring

Ngoài implementation chung của Jakarta Activation, Spring Mail cung cấp **ConfigurableMimeFileTypeMap** để cấu hình mapping trong ứng dụng Spring.

Ví dụ:

~~~java
import jakarta.activation.FileTypeMap;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.ConfigurableMimeFileTypeMap;

@Configuration
public class MailMimeTypeConfiguration {

    @Bean
    public FileTypeMap mailFileTypeMap() {
        ConfigurableMimeFileTypeMap map =
                new ConfigurableMimeFileTypeMap();

        map.setMappings(
                "text/csv csv",
                "application/x-example-report rptx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document docx"
        );

        return map;
    }
}
~~~

Spring quản lý bean sẽ thực hiện vòng đời khởi tạo của đối tượng cấu hình. Có thể truyền bean này vào constructor **MimeMessageHelper** nhận **FileTypeMap** như phần trước.

**ConfigurableMimeFileTypeMap** phù hợp khi muốn giữ mapping ở lớp cấu hình Spring và có thể bổ sung mapping riêng. Các tùy chọn mapping/resource cụ thể phụ thuộc phiên bản Spring Framework; hãy dùng API có trong dependency thực tế của dự án.

### Nên dùng MimetypesFileTypeMap hay ConfigurableMimeFileTypeMap?

| Lựa chọn | Khi phù hợp |
| --- | --- |
| **MimetypesFileTypeMap** | Muốn dùng trực tiếp Jakarta Activation và bổ sung mapping bằng addMimeTypes(...) |
| **ConfigurableMimeFileTypeMap** | Muốn cấu hình mapping theo cách Spring bean và tích hợp vòng đời cấu hình Spring |
| **Content-Type tường minh** | Chỉ một part có loại đã biết rõ, không cần thay đổi mapping chung |

Không cần tạo một lớp FileTypeMap riêng cho từng attachment nếu mapping mặc định hoặc explicit content type đã đáp ứng yêu cầu. Giữ cấu hình đơn giản giúp tránh việc cùng một extension bị nhận diện khác nhau giữa các service.

## 17. Xây luồng gửi attachment từ dữ liệu đã được xác nhận

Với file upload, không nên để controller lấy tên file và Content-Type từ request rồi truyền thẳng vào **MimeMessageHelper**. Một luồng có trách nhiệm rõ ràng có thể là:

~~~text
File upload / generated file
        |
        v
Kiểm tra kích thước và tên
        |
        v
Kiểm tra loại file được phép
        |
        v
Phân tích bytes / signature / parser
        |
        v
Quét nội dung theo chính sách
        |
        v
ValidatedAttachment
  - resource
  - safe filename
  - trusted content type
        |
        v
MimeMessageHelper.addAttachment(...)
        |
        v
JavaMailSender.send(...)
~~~

**ValidatedAttachment** là một khái niệm model của ứng dụng, không phải class Spring có sẵn. Nó biểu diễn dữ liệu đã được kiểm tra và có metadata đáng tin cậy hơn dữ liệu raw từ client.

Ví dụ record:

~~~java
import org.springframework.core.io.Resource;

public record ValidatedAttachment(
        String filename,
        String contentType,
        Resource resource
) {
    public ValidatedAttachment {
        if (filename == null || filename.isBlank()) {
            throw new IllegalArgumentException("Thiếu filename");
        }
        if (contentType == null || contentType.isBlank()) {
            throw new IllegalArgumentException("Thiếu contentType");
        }
        if (resource == null) {
            throw new IllegalArgumentException("Thiếu resource");
        }
    }
}
~~~

Service gửi thư chỉ nhận đối tượng đã qua validation:

~~~java
public void sendDocument(
        String recipient,
        ValidatedAttachment attachment
) throws MessagingException {

    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED,
            "UTF-8"
    );

    helper.setTo(recipient);
    helper.setSubject("Tài liệu của bạn");
    helper.setText("Tài liệu đã được đính kèm.");
    helper.addAttachment(
            attachment.filename(),
            attachment.resource(),
            attachment.contentType()
    );

    mailSender.send(message);
}
~~~

Đoạn mã minh họa trách nhiệm của lớp gửi thư: dùng filename và content type đã được xác định, rồi tạo MIME part. Nó không tự thực hiện kiểm tra upload, quét malware hoặc xác minh bytes; những việc đó thuộc service chuẩn bị attachment.

### Tại sao không tin Content-Type do trình duyệt gửi?

Một multipart HTTP upload thường có tên file và Content-Type do client khai báo. Giá trị đó hữu ích để tham khảo, nhưng client có thể gửi bất kỳ chuỗi nào. Nếu server chỉ lấy header upload làm Content-Type cho email, người gửi có thể cố ý khai báo một tệp không an toàn thành image/png hoặc application/pdf.

Hãy xem MIME type do client gửi là **metadata không đáng tin cậy**. Server cần áp dụng allowlist, kiểm tra nội dung và xác định loại dữ liệu theo chính sách của hệ thống trước khi gửi.

### Giới hạn tổng dung lượng

Khi email có nhiều attachment, cần kiểm tra:

- Kích thước từng file.
- Tổng kích thước tất cả file.
- Overhead do MIME boundary, header và Content-Transfer-Encoding.
- Giới hạn thông điệp của SMTP provider.
- Giới hạn mà mailbox người nhận có thể chấp nhận.

Base64 làm phần biểu diễn dữ liệu nhị phân lớn hơn byte gốc, ngoài các header và multipart boundary. Vì vậy, không nên chỉ cộng kích thước file rồi kết luận email chắc chắn nằm dưới giới hạn provider.

## 18. Namespace Jakarta và JavaMail cũ

Trong các phiên bản Spring Framework mới dùng hệ sinh thái Jakarta, các import thường có dạng:

~~~java
import jakarta.activation.FileTypeMap;
import jakarta.activation.MimetypesFileTypeMap;
import jakarta.mail.internet.MimeMessage;
~~~

Ở các ứng dụng cũ dựa trên Java EE/JavaMail trước khi chuyển sang Jakarta, package có thể bắt đầu bằng:

~~~java
import javax.activation.FileTypeMap;
import javax.activation.MimetypesFileTypeMap;
import javax.mail.internet.MimeMessage;
~~~

**javax.activation** và **jakarta.activation** là hai namespace khác nhau. Không thể truyền một FileTypeMap thuộc javax vào constructor yêu cầu jakarta chỉ vì tên lớp giống nhau. Hãy dùng đồng bộ phiên bản Spring Mail, Jakarta Mail/Activation và import tương ứng với dependency của ứng dụng.

Nếu IDE báo không tìm thấy **MimetypesFileTypeMap** hoặc **FileTypeMap**, kiểm tra dependency Activation và phiên bản thư viện mail trước khi tự tạo một class trùng tên.

## 19. Những nhầm lẫn thường gặp

### Nhầm 1: Đuôi .pdf chứng minh file là PDF

Không. FileTypeMap ánh xạ extension sang MIME type. Nó không đọc toàn bộ bytes để xác nhận cấu trúc PDF.

**Cách xử lý:** xác minh file ở bước tiếp nhận hoặc tạo tài liệu, rồi dùng MIME type được xác định từ nguồn đáng tin cậy.

### Nhầm 2: Content-Type quyết định byte được chuyển đổi

Không. Đặt application/pdf cho một part không biến dữ liệu CSV thành PDF.

**Cách xử lý:** tạo đúng nội dung file trước; Content-Type chỉ mô tả loại dữ liệu.

### Nhầm 3: Base64 là MIME type

Không. Base64 là một **Content-Transfer-Encoding**; application/pdf hoặc image/png mới là **Content-Type**.

**Cách xử lý:** kiểm tra đúng header cho từng mục đích.

### Nhầm 4: FileTypeMap không nhận extension nghĩa là không thể gửi file

Không. Có thể dùng MIME type tổng quát hoặc chỉ định content type tường minh nếu đã biết định dạng.

**Cách xử lý:** bổ sung mapping hoặc dùng overload explicit content type; không gán một MIME type giả.

### Nhầm 5: Files.probeContentType và FileTypeMap luôn trả cùng kết quả

Không. Chúng có nguồn detector và mapping khác nhau, phụ thuộc runtime.

**Cách xử lý:** chọn một nguồn có thẩm quyền cho luồng gửi và kiểm tra trên môi trường triển khai.

### Nhầm 6: Gọi addAttachment là file đã được đọc hết

Không nhất thiết. Resource có thể được đọc ở thời điểm serialize hoặc gửi.

**Cách xử lý:** giữ resource khả dụng cho tới khi send hoàn tất; cẩn thận với stream một lần.

### Nhầm 7: Filename đúng là attachment đã đúng

Không. Cần kiểm tra cả Content-Type, disposition và payload.

**Cách xử lý:** duyệt MIME part và kiểm tra bytes sau giải mã nếu yêu cầu bảo toàn dữ liệu.

### Nhầm 8: Có thể thay MIME type mặc định toàn JVM cho một service

Thay đổi default toàn cục có thể ảnh hưởng các thành phần khác.

**Cách xử lý:** truyền FileTypeMap riêng vào MimeMessageHelper hoặc cấu hình bean có phạm vi rõ.

### Nhầm 9: MIME type hợp lệ nghĩa là file an toàn

Không. File có thể chứa nội dung độc hại dù extension và header hợp lệ.

**Cách xử lý:** allowlist, kiểm tra bytes, parser và malware scanning theo mức rủi ro.

## 20. Bài tập tình huống

### Tình huống A — File không có extension

Nguồn dữ liệu là một PDF hợp lệ nhưng tên file hiển thị là **invoice**.

**Hỏi:** FileTypeMap có chắc trả application/pdf không?

**Đáp:** không. Nếu không có extension hoặc mapping theo tên phù hợp, map có thể trả application/octet-stream. Nếu ứng dụng đã xác nhận đây là PDF, truyền content type application/pdf tường minh.

### Tình huống B — File tên report.pdf nhưng byte là CSV

**Hỏi:** FileTypeMap trả MIME type nào?

**Đáp:** mapping theo tên có thể trả application/pdf. Điều đó không xác nhận byte là PDF. Hệ thống cần phát hiện mismatch và từ chối hoặc xử lý theo chính sách.

### Tình huống C — Custom extension rptx

Ứng dụng tạo định dạng báo cáo nội bộ với phần mở rộng rptx.

**Hỏi:** làm sao để helper suy luận MIME type?

**Đáp:** bổ sung mapping cho rptx trong MimetypesFileTypeMap hoặc ConfigurableMimeFileTypeMap rồi truyền map đó vào helper. Nếu chỉ một lần gửi, có thể truyền content type tường minh.

### Tình huống D — CSV có tiếng Việt bị lỗi dấu

File bytes là UTF-8 nhưng part chỉ có text/csv, không có charset.

**Hỏi:** đổi FileTypeMap sang một loại khác có giải quyết không?

**Đáp:** không nhất thiết. Cần bảo đảm byte UTF-8 và khai báo charset=UTF-8 trong Content-Type của part.

### Tình huống E — Attachment có MIME type đúng nhưng mở không được

Header là application/pdf và filename là invoice.pdf, nhưng parser PDF báo file hỏng.

**Hỏi:** có thể kết luận email client lỗi?

**Đáp:** chưa. Kiểm tra file nguồn, resource, serialize và bytes sau khi giải mã Content-Transfer-Encoding. MIME metadata đúng không bảo đảm payload nguyên vẹn.

### Tình huống F — Mapping đúng trong test nhưng sai trên server

Local trả image/webp, container trả application/octet-stream.

**Hỏi:** tại sao?

**Đáp:** có thể môi trường runtime nạp mapping khác hoặc service đang dùng FileTypeMap khác. Cấu hình map tường minh và kiểm tra instance thực tế được truyền vào helper.

### Tình huống G — Ảnh inline bị xem như file đính kèm

**Hỏi:** chỉ cần sửa FileTypeMap sang image/png là đủ?

**Đáp:** chưa chắc. Cần kiểm tra Content-ID, Content-Disposition, HTML cid reference và cấu trúc multipart/related. MIME type chỉ mô tả loại byte ảnh.

### Tình huống H — Một upload khai báo application/pdf nhưng thực tế là tệp thực thi

**Hỏi:** có nên giữ header client gửi?

**Đáp:** không. MIME type do client gửi là dữ liệu không đáng tin. Server phải kiểm tra định dạng thật, allowlist và chính sách bảo mật trước khi đính kèm hoặc từ chối file.

## 21. Quy trình chọn Content-Type cho attachment

~~~text
Ứng dụng có biết chính xác loại dữ liệu từ nguồn tin cậy?
        |
        +-- Có
        |    |
        |    v
        |  Dùng MIME type đã xác định
        |  (có thể truyền tường minh vào helper)
        |
        '-- Không
             |
             v
       Tra FileTypeMap theo filename
             |
             +-- Có mapping phù hợp
             |      |
             |      v
             |   Kiểm tra extension và nội dung
             |
             '-- Không có mapping
                    |
                    v
              application/octet-stream
              hoặc xác định lại loại file

Sau khi chọn MIME type
        |
        v
Kiểm tra Content-Type / filename / disposition
        |
        v
Đảm bảo Resource còn đọc được
        |
        v
Tạo MimeMessage và gửi
~~~

Một checklist thực hành cho từng attachment:

- Xác định **định dạng thực tế** của file từ nguồn đáng tin cậy.
- Chọn **MIME type** phù hợp, bao gồm charset nếu là dữ liệu text cần khai báo.
- Dùng **FileTypeMap** mặc định, mapping tùy chỉnh hoặc Content-Type tường minh theo tình huống.
- Đặt **filename** an toàn và có ý nghĩa với người nhận.
- Xác nhận **Content-Disposition** là attachment hoặc inline theo mục đích.
- Giữ **Resource/InputStreamSource** khả dụng tới lúc message được serialize và gửi.
- Kiểm tra MIME part trong test, bao gồm Content-Type, filename và payload khi cần.
- Với file từ nguồn không tin cậy, thực hiện validation và quét theo chính sách trước khi gửi.

**Content-Type của attachment** giúp phần mềm nhận hiểu loại dữ liệu; **FileTypeMap** giúp Jakarta Activation và Spring Mail suy luận loại đó từ tên file; **MimeMessageHelper** dùng metadata để tạo MIME part. Khi cần kết quả ổn định, hãy cấu hình mapping có phạm vi rõ hoặc truyền Content-Type tường minh từ dữ liệu đã được xác nhận. Luôn nhớ rằng extension, MIME header và transfer encoding là ba khái niệm khác nhau, và không khái niệm nào tự chứng minh file an toàn hay đúng định dạng.
