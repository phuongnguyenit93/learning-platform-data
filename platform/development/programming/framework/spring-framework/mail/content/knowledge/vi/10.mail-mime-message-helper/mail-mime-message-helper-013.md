# Kiểm tra MIME tree sau khi helper tạo message

Khi sử dụng **Spring Framework Mail**, các lời gọi **MimeMessageHelper.setText(...)**, **addInline(...)** và **addAttachment(...)** giúp tạo email HTML, nội dung thay thế dạng văn bản, ảnh trong body và tệp đính kèm mà không cần tự ghép MIME headers. Tuy nhiên, sự tiện lợi đó có một hệ quả: lập trình viên dễ biết **mình đã gọi phương thức gì**, nhưng lại chưa chắc biết **MIME tree thực tế được tạo ra như thế nào**.

Đó là khác biệt quan trọng. Một email có thể có đủ HTML, logo và PDF trong chương trình nhưng khi nhận lại bị lỗi hiển thị, mất attachment hoặc hiện ảnh dưới dạng tệp tải xuống. Nguyên nhân đôi khi không nằm ở dữ liệu gốc, mà ở cách các phần **multipart/alternative**, **multipart/related**, **multipart/mixed** được lồng nhau, cách **Content-ID** được đặt hoặc thứ tự thao tác lúc chuẩn bị message.

Bài học này hướng dẫn **kiểm tra MIME tree sau khi MimeMessageHelper tạo message**: nhìn các nút của cây, phân tích headers từng phần, đọc cấu trúc bằng API **Jakarta Mail**, quan sát bản thư đã serialize và hiểu giới hạn của việc kiểm tra trên message còn nằm trong bộ nhớ. Mục tiêu là biết **thư thật sự mang cấu trúc nào**, không chỉ suy đoán từ tên phương thức helper.

## 1. MIME tree là gì?

MIME (*Multipurpose Internet Mail Extensions*) mô tả cách một email chứa nhiều loại nội dung. Một thông điệp **MimeMessage** là nút gốc; khi body là **multipart**, nó chứa nhiều **body parts**; mỗi body part lại có thể chứa một **multipart** khác.

Ví dụ một email đơn giản:

~~~text
MimeMessage
|
'-- text/plain; charset=UTF-8
      "Xin chào!"
~~~

Ví dụ có hai cách trình bày cùng nội dung:

~~~text
MimeMessage
|
'-- multipart/alternative
     |
     +-- text/plain; charset=UTF-8
     |     "Bạn có một thông báo mới."
     |
     '-- text/html; charset=UTF-8
           <p>Bạn có <strong>một thông báo</strong> mới.</p>
~~~

Ví dụ có HTML tham chiếu logo và một tệp PDF:

~~~text
MimeMessage
|
'-- multipart/mixed
     |
     +-- multipart/related
     |    |
     |    +-- multipart/alternative
     |    |    |
     |    |    +-- text/plain
     |    |    '-- text/html
     |    |
     |    '-- image/png
     |          Content-ID: <logo-1>
     |          Content-Disposition: inline
     |
     '-- application/pdf
           Content-Disposition: attachment
           filename="guide.pdf"
~~~

Sơ đồ cuối là một **cấu trúc MIME có thể gặp**, dùng để thể hiện mục đích của các quan hệ **mixed**, **related** và **alternative**. Cây thực tế còn phụ thuộc **multipart mode**, overload của **setText**, cách thêm resource và implementation/version của thư viện mail. Vì vậy, **không nên mặc định mọi email do helper tạo đều có cây y hệt sơ đồ**.

### Một cây MIME, nhiều câu hỏi kiểm tra

| Câu hỏi | Thứ cần quan sát |
| --- | --- |
| Email chỉ có một body hay nhiều phần? | **Content-Type** của root: text/* hay multipart/* |
| Plain text và HTML có phải hai lựa chọn thay thế? | Có **multipart/alternative** bao hai part tương ứng không |
| Ảnh nào thuộc nội dung HTML? | **multipart/related**, **Content-ID** và tham chiếu **cid:** |
| PDF là attachment hay một phần body? | **Content-Type**, **Content-Disposition**, **filename** |
| Tệp có chứa đúng bytes không? | Nội dung part sau khi giải mã transfer encoding |
| Thư có định dạng phát đi tương ứng với đối tượng trong bộ nhớ không? | Bản MIME serialize hoặc raw message |

Điểm quan trọng: **MIME tree mô tả cách đóng gói và quan hệ giữa các phần**, không cho biết thư đã được phát đến inbox hay chưa.

## 2. Phân biệt các loại multipart trước khi kiểm tra

MIME dùng **Content-Type** của từng nút để định nghĩa ý nghĩa quan hệ giữa các part con.

### multipart/alternative: nhiều cách thể hiện cùng thông điệp

~~~text
multipart/alternative
    +-- text/plain
    '-- text/html
~~~

Hai part thường truyền đạt **cùng thông tin** bằng hai định dạng. Client chọn phiên bản phù hợp với khả năng và lựa chọn người đọc. Không nên coi đây là hai đoạn bắt buộc được nối liên tiếp khi hiển thị. Theo cách dùng thông thường, phiên bản phong phú hơn như HTML được đặt sau phiên bản text.

Nếu kiểm tra thấy plain text là “Vui lòng bật HTML”, trong khi HTML chứa mã xác minh quan trọng, cây MIME có thể đúng về kỹ thuật nhưng bản thay thế **không cung cấp nội dung tương đương** cho người không dùng HTML.

### multipart/related: các phần phụ thuộc nhau để tạo một nội dung

~~~text
multipart/related
    +-- text/html
    '-- image/png
          Content-ID: <course-logo>
~~~

HTML có thể chứa:

~~~html
<img src="cid:course-logo" alt="Logo khóa học">
~~~

Part ảnh với **Content-ID: <course-logo>** là tài nguyên liên quan đến nội dung HTML. Việc chỉ thấy **image/png** trong cây chưa đủ; cần xác định HTML có tham chiếu đúng ID hay không.

Một email cũng có thể có **alternative** lồng bên trong **related**, để vừa có plain text fallback vừa có HTML kèm ảnh. Dạng lồng cụ thể thay đổi theo cách message được tạo.

### multipart/mixed: tập hợp nội dung và phần đính kèm

~~~text
multipart/mixed
    +-- text/plain
    '-- application/pdf
          Content-Disposition: attachment
~~~

Đây là ví dụ đơn giản của email có body và PDF attachment. Nếu còn HTML, ảnh inline hay các phần khác, **mixed** có thể chứa một cây multipart con thay vì chỉ một phần text. Khi rà soát cây, cần đi **đệ quy** qua các nút con, không chỉ đếm body parts của root.

### MIME type khác disposition

Một part:

~~~text
Content-Type: image/png
Content-Disposition: inline
Content-ID: <logo-1>
~~~

và part:

~~~text
Content-Type: image/png
Content-Disposition: attachment; filename="logo.png"
~~~

đều có **Content-Type: image/png**, nhưng mục đích hiển thị khác nhau. **Content-Type** giải thích loại dữ liệu; **Content-Disposition** gợi ý cách trình bày; **Content-ID** cho phép tham chiếu nội dung nội tuyến.

Các header là tín hiệu cho client, **không phải mệnh lệnh tuyệt đối**. Một số ứng dụng đọc thư vẫn có thể hiển thị ảnh inline như attachment hoặc chặn việc tải/hiển thị ảnh.

## 3. MimeMessageHelper và bốn chế độ multipart

**MimeMessageHelper** cung cấp các chế độ tạo MIME multipart. Chúng quyết định dạng cây nền tảng trước khi thêm plain text, HTML, inline resources và attachments.

| Chế độ | Ý định cấu trúc | Điểm cần nhớ khi quan sát tree |
| --- | --- | --- |
| **MULTIPART_MODE_NO** | Không khởi tạo multipart | Phù hợp email một body; không dùng để thêm nhiều MIME part |
| **MULTIPART_MODE_MIXED** | Root **multipart/mixed** | Phần body, inline và attachment có thể cùng nằm dưới mixed; một số client xử lý inline khác mong muốn |
| **MULTIPART_MODE_RELATED** | Root **multipart/related** | Phù hợp gom nội dung và tài nguyên liên quan; attachment có thể bị một số client hiển thị khác dự kiến |
| **MULTIPART_MODE_MIXED_RELATED** | Root **multipart/mixed** với **multipart/related** lồng bên trong | Tách nhóm nội dung/inline khỏi attachment; thường là lựa chọn thuận tiện khi có cả ảnh inline và file đính kèm |

Ví dụ khởi tạo:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);
~~~

Lưu ý: **MULTIPART_MODE_MIXED_RELATED** là chế độ tạo cấu trúc **mixed/related**, không có nghĩa bản thân nó tự thêm **multipart/alternative**. Cấu trúc alternative chỉ xuất hiện khi có nhu cầu tạo nhiều cách trình bày cùng body, chẳng hạn dùng **setText(plainText, htmlText)**.

### Cùng nội dung, khác chế độ có thể tạo cây khác

Giả sử ứng dụng thực hiện:

~~~java
helper.setText(plainText, htmlText);
helper.addInline("logo-1", logoResource, "image/png");
helper.addAttachment("report.pdf", reportResource);
~~~

Với chế độ **MIXED_RELATED**, một cây ý tưởng có thể là:

~~~text
multipart/mixed
|
|-- multipart/related
|    |-- multipart/alternative
|    |    |-- text/plain
|    |    '-- text/html
|    '-- image/png (Content-ID: <logo-1>)
|
'-- application/pdf (attachment)
~~~

Trong các chế độ khác, các phần có thể ở các nút khác hoặc không được tổ chức thành lớp related dưới mixed. **Không kết luận message đúng chỉ dựa trên tổng số part**: quan hệ cha/con cũng quan trọng.

### Một số overload dễ nhầm

~~~java
new MimeMessageHelper(message, false, "UTF-8");
helper.setText(html, true);
~~~

Tham số **false** ở constructor thể hiện **không bật multipart**; tham số **true** ở **setText** thể hiện **đây là HTML body**. Một email HTML đơn giản vẫn có thể là một part **text/html**, không nhất thiết có root multipart.

Ngược lại:

~~~java
new MimeMessageHelper(message, true, "UTF-8");
helper.setText(plainText, htmlText);
~~~

Tham số **true** ở constructor yêu cầu sử dụng multipart mode mặc định phù hợp của helper; **setText(plainText, htmlText)** tạo hai phương án nội dung trong cấu trúc MIME. Muốn kiểm soát cây chính xác hơn, nên chọn **multipart mode** một cách tường minh.

## 4. Tạo một MimeMessage điển hình để quan sát

Ví dụ sau tạo một email có:

- Văn bản thuần phục vụ fallback.
- Nội dung HTML có một hình ảnh tham chiếu bằng **cid:**.
- Tệp **PDF** đính kèm.
- Header **From**, **To**, **Subject** được khai báo rõ.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class CourseMailFactory {

    private final JavaMailSender mailSender;

    public CourseMailFactory(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public MimeMessage createCourseMail(
            String recipient,
            Path logoPath,
            Path guidePath
    ) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom("academy@example.test");
        helper.setTo(recipient);
        helper.setSubject("Tài liệu khóa học");

        String plainText = """
                Xin chào,

                Tài liệu khóa học đã được đính kèm.
                Vui lòng xem tệp guide.pdf.
                """;

        String htmlText = """
                <html>
                  <body>
                    <h2>Tài liệu khóa học</h2>
                    <p>Vui lòng xem tệp <strong>guide.pdf</strong>.</p>
                    <img src="cid:course-logo" alt="Logo khóa học">
                  </body>
                </html>
                """;

        helper.setText(plainText, htmlText);
        helper.addInline(
                "course-logo",
                new FileSystemResource(logoPath.toFile()),
                "image/png"
        );
        helper.addAttachment(
                "guide.pdf",
                new FileSystemResource(guidePath.toFile())
        );

        return message;
    }
}
~~~

Ở đây **chỉ tạo và trả về MimeMessage**, **không gọi send(...)**. Nhờ vậy có thể kiểm tra đối tượng trong bộ nhớ trước khi nộp thư cho SMTP. Thứ tự **setText(...) trước addInline(...)** quan trọng trong cách sử dụng MimeMessageHelper thông thường: một số email client và tình huống dựng part dễ gặp lỗi hiển thị nếu thêm inline resource không đúng thứ tự hoặc tham chiếu.

Các file ở **logoPath** và **guidePath** phải tồn tại, có quyền đọc và còn khả dụng tới thời điểm thư được serialize/gửi. Một phần MIME có thể giữ **DataHandler/Resource** và chưa đọc hết nội dung byte tại thời điểm gọi **addAttachment(...)**. Vì vậy, **tạo cây thành công không chứng minh file đã được đọc thành công khi gửi**.

### Chọn cách kiểm tra theo mục đích

Có ba mức quan sát bổ sung nhau:

1. **Duyệt cấu trúc đối tượng MIME** bằng **Part**, **Multipart**, **BodyPart**, để biết loại nút và metadata của mỗi part.
2. **Serialize message thành MIME raw** rồi xem headers, boundaries, transfer encoding và payload thực được tạo ở thời điểm serialize.
3. **Gửi qua mail capture/test SMTP** và xem bản thư phía nhận để biết có bước transport/provider nào thay đổi cách đóng gói hay không.

Hai mức đầu không cần kết nối SMTP thật. Mức thứ ba giúp quan sát gần trải nghiệm nhận thư hơn, nhưng vẫn không chứng minh mọi email client sẽ render giống nhau.

## 5. Duyệt MIME tree bằng API Jakarta Mail

Các kiểu dữ liệu cơ bản:

| Kiểu | Vai trò |
| --- | --- |
| **MimeMessage** | Thông điệp email ở cấp root |
| **Part** | Giao diện chung của message/body part |
| **Multipart** | Container có nhiều body parts |
| **BodyPart** | Một phần con trong multipart |
| **MimeBodyPart** | Implementation MIME phổ biến cho một body part |
| **Content-Type** | Header mô tả loại nội dung và tham số |

Với một message vừa tạo, có thể đi từ root xuống con theo nguyên tắc:

~~~text
inspect(part):
    in ra metadata của part
    nếu part là multipart:
        lấy Multipart
        với từng BodyPart:
            inspect(bodyPart)
    nếu part là message/rfc822:
        có thể inspect thông điệp đính kèm
    nếu part là text, image, PDF, ...:
        chỉ in metadata; không bắt buộc đọc toàn bộ bytes
~~~

Điểm cần chú ý: **Multipart** không phải là một **Part**. Part có thể **chứa** Multipart; Multipart cung cấp **getCount()** và **getBodyPart(index)** để truy cập các phần con. Khi một body part lại chứa Multipart khác, thuật toán phải đi đệ quy thay vì chỉ liệt kê root.

### Một công cụ in cây không dump nội dung nhạy cảm

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.io.IOException;
import java.util.Arrays;

public final class MimeTreeInspector {

    private MimeTreeInspector() {
    }

    public static void printTree(Part part)
            throws MessagingException, IOException {
        inspect(part, "root", 0);
    }

    private static void inspect(Part part, String path, int depth)
            throws MessagingException, IOException {

        String indent = "  ".repeat(depth);
        String contentId = String.join(
                ", ", safeHeaders(part.getHeader("Content-ID"))
        );
        String transferEncoding = String.join(
                ", ", safeHeaders(
                        part.getHeader("Content-Transfer-Encoding")
                )
        );

        System.out.printf(
                "%s%s type=%s disposition=%s filename=%s"
                + " contentId=%s cte=%s size=%d%n",
                indent,
                path,
                part.getContentType(),
                part.getDisposition(),
                part.getFileName(),
                contentId,
                transferEncoding,
                part.getSize()
        );

        if (part.isMimeType("multipart/*")) {
            Object content = part.getContent();
            if (content instanceof Multipart multipart) {
                for (int index = 0; index < multipart.getCount(); index++) {
                    BodyPart child = multipart.getBodyPart(index);
                    inspect(
                            child,
                            path + "." + index,
                            depth + 1
                    );
                }
            }
        } else if (part.isMimeType("message/rfc822")) {
            Object content = part.getContent();
            if (content instanceof Message nestedMessage) {
                inspect(nestedMessage, path + ".message", depth + 1);
            }
        }
    }

    private static String[] safeHeaders(String[] values) {
        return values == null
                ? new String[0]
                : Arrays.copyOf(values, values.length);
    }
}
~~~

Ví dụ chỉ **in metadata**, không đọc hoặc in body của từng part, vì attachment có thể rất lớn hoặc mang thông tin nhạy cảm. Đây là một công cụ minh họa dành cho dữ liệu thử nghiệm, **không nên ghi nguyên Content-ID, filename hay tất cả headers vào production log** khi chúng có thể chứa thông tin cá nhân hoặc dữ liệu nội bộ.

Với một part còn chưa được serialize, **getSize()** có thể trả **-1** nếu implementation không biết kích thước. Header **Content-Transfer-Encoding** cũng có thể chưa được tính hoặc chưa xuất hiện theo dạng cuối cùng. Điều đó không tự chứng minh message hỏng; nó cho thấy sự khác biệt giữa **đối tượng MIME đang xây dựng** và **dạng MIME đã được chuẩn bị/serialize**.

Ngoài ra, việc gọi **getContent()** cho multipart có thể yêu cầu thư viện phân tích một cấu trúc đã có sẵn. Đừng áp dụng cùng thao tác lên mọi attachment nhị phân chỉ để in cây, vì nó có thể kéo payload lớn vào bộ nhớ.

## 6. Kiểm tra sau saveChanges và serialize

Một **MimeMessage** có thể đang ở trạng thái được chỉnh sửa. Khi đó, một số header được tạo muộn hoặc được suy ra từ **DataHandler**, nội dung part và các thuộc tính MIME. Vì vậy nên phân biệt:

- **Cây đối tượng sau các lời gọi helper**: phản ánh các part và dữ liệu mà ứng dụng đã gắn.
- **Thông điệp sau saveChanges()**: cập nhật những header và metadata cần thiết theo cơ chế Jakarta Mail.
- **Dữ liệu sau writeTo(...)**: biểu diễn RFC/MIME có thể được ghi ra output stream, với headers, boundaries và payload đã được mã hóa truyền tải.

Ví dụ:

~~~java
import jakarta.mail.internet.MimeMessage;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class MimeMessageDump {

    private MimeMessageDump() {
    }

    public static void writeForLocalInspection(
            MimeMessage message,
            Path destination
    ) throws Exception {

        // Chuẩn bị headers và metadata MIME ở thời điểm quan sát.
        message.saveChanges();

        try (OutputStream output = Files.newOutputStream(destination)) {
            message.writeTo(output);
        }
    }
}
~~~

Đây là tiện ích minh họa dùng trong **test hoặc môi trường chẩn đoán**. File kết quả có thể chứa toàn bộ nội dung thư, địa chỉ, token trong liên kết và byte attachment đã mã hóa Base64; cần dùng dữ liệu thử nghiệm, ghi vào vị trí được bảo vệ và xóa theo chính sách. Không nên bật việc dump raw MIME vô điều kiện trong production.

**saveChanges() không gửi email.** Nó giúp chuẩn bị message theo trạng thái hiện tại. Tùy implementation, việc ghi message có thể yêu cầu mở nguồn tài nguyên, đọc attachment và tính transfer encoding, vì vậy thao tác serialize cũng có thể thất bại nếu tài nguyên không còn đọc được.

Một số header như **Message-ID**, **Date** hoặc boundary có thể được sinh/chỉnh trong quá trình chuẩn bị và ghi thư. Do đó, test không nên phụ thuộc vào **giá trị ngẫu nhiên hoặc thứ tự headers chính xác** trừ khi đó là điều ứng dụng chủ động kiểm soát.

### Vì sao không nên so sánh raw MIME bằng một chuỗi cố định?

Hai thông điệp có nội dung tương đương có thể khác nhau ở:

- Chuỗi **boundary** được sinh tự động.
- **Message-ID**, ngày giờ hoặc headers bổ sung.
- Cách gấp dòng header dài (*header folding*).
- Cách chọn **Content-Transfer-Encoding** (ví dụ quoted-printable hoặc Base64).
- Cách viết tham số charset hoặc filename.
- Thứ tự một số headers và chi tiết của provider.

So sánh toàn bộ raw bytes với một “golden string” có thể khiến test thất bại vì khác biệt hợp lệ, không liên quan tới yêu cầu nghiệp vụ. Thường nên **parse lại raw MIME rồi kiểm tra cấu trúc, MIME types và nội dung sau giải mã**.

### Đọc raw MIME để nhận biết boundary

Một bản raw được rút gọn có thể trông như sau:

~~~text
MIME-Version: 1.0
From: academy@example.test
To: learner@example.test
Subject: Tai lieu khoa hoc
Content-Type: multipart/mixed; boundary="mix-01"

--mix-01
Content-Type: multipart/related; boundary="rel-01"

--rel-01
Content-Type: multipart/alternative; boundary="alt-01"

--alt-01
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

T=C3=A0i li=E1=BB=87u kh=C3=B3a h=E1=BB=8Dc

--alt-01
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<h2>T=C3=A0i li=E1=BB=87u kh=C3=B3a h=E1=BB=8Dc</h2>
<img src=3D"cid:course-logo">

--alt-01--
--rel-01
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-ID: <course-logo>
Content-Disposition: inline

[base64 cua anh - da luoc bot]

--rel-01--
--mix-01
Content-Type: application/pdf; name="guide.pdf"
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="guide.pdf"

[base64 cua PDF - da luoc bot]

--mix-01--
~~~

Đây là **raw MIME minh họa**, không phải message hoàn chỉnh có thể dùng để mở file: hai khối payload đặt trong ngoặc vuông là chú thích và đã được lược bỏ. Giá trị boundary trong thực tế sẽ do thư viện tạo ra. Mục tiêu của ví dụ là làm rõ **quan hệ lồng nhau**:

1. Boundary của **mixed** tách nhóm nội dung khỏi attachment PDF.
2. Boundary của **related** tách nội dung hiển thị và ảnh inline.
3. Boundary của **alternative** tách plain text khỏi HTML.
4. Mỗi part có header riêng; **Content-Type** và **Content-Transfer-Encoding** không nhất thiết giống nhau.

**Không nên tự tách MIME bằng chuỗi split("--boundary")**: boundary có thể lồng nhau, có quy tắc đóng, header có thể được gấp dòng và body có các lớp transfer encoding. Hãy dùng parser MIME của Jakarta Mail.

## 7. Parse lại raw bytes: kiểm tra định dạng có thể đọc được

Sau khi serialize, có thể tạo một **MimeMessage mới** từ dữ liệu raw. Việc này mô phỏng quá trình parser phải diễn giải lại message thay vì chỉ nhìn đối tượng helper đang thao tác.

~~~java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public final class MimeMessageReader {

    private MimeMessageReader() {
    }

    public static MimeMessage parseFromFile(Path emlFile)
            throws Exception {

        Session session = Session.getInstance(new Properties());

        try (InputStream input = Files.newInputStream(emlFile)) {
            return new MimeMessage(session, input);
        }
    }
}
~~~

Ví dụ sử dụng Session rỗng vì mục đích **đọc MIME đã lưu**, không yêu cầu kết nối SMTP. Đối tượng được tạo từ InputStream có thể giữ dữ liệu cần thiết trong quá trình parse tùy implementation; với thư rất lớn, vẫn phải chú ý bộ nhớ và tài nguyên.

Sau khi parse lại:

~~~java
MimeMessage parsed = MimeMessageReader.parseFromFile(emlFile);
MimeTreeInspector.printTree(parsed);
~~~

Lúc này, việc duyệt cây phản ánh cấu trúc của **bản đã serialize**, giúp phát hiện sai khác giữa dự định ban đầu và biểu diễn thực tế.

### Đừng nhầm parse lại với thử gửi thật

Parse lại file **.eml** kiểm tra rằng parser MIME có thể giải thích message do ứng dụng tạo. Nó không kiểm tra:

- SMTP account và quyền gửi.
- Giới hạn kích thước của provider.
- Phản hồi **MAIL FROM / RCPT TO / DATA**.
- Việc email client đích render HTML hoặc ảnh inline thế nào.
- Kết quả phát tới Inbox.

Vì vậy, kiểm tra MIME tree là một **kiểm tra cấu trúc thông điệp**, bổ sung chứ không thay thế integration test SMTP và kiểm tra hiển thị trên email client.

## 8. Đọc kết quả cây và xác định nút quan trọng

Một công cụ in tree có thể tạo đầu ra khái niệm như:

~~~text
root type=multipart/mixed; boundary=... disposition=null
  root.0 type=multipart/related; boundary=...
    root.0.0 type=multipart/alternative; boundary=...
      root.0.0.0 type=text/plain; charset=UTF-8
      root.0.0.1 type=text/html; charset=UTF-8
    root.0.1 type=image/png
      disposition=inline contentId=<course-logo>
  root.1 type=application/pdf
    disposition=attachment filename=guide.pdf
~~~

Đầu ra này chỉ minh họa; số index và cấu trúc có thể khác tùy mode và phiên bản helper. Điều cần tìm không phải một chuỗi log tuyệt đối, mà là **những quan hệ có ý nghĩa**.

### Kiểm tra phần nội dung chính

Nếu bạn gọi:

~~~java
helper.setText(plainText, htmlText);
~~~

hãy tìm một **multipart/alternative** có hai phần **text/plain** và **text/html**. Nếu code chỉ gọi:

~~~java
helper.setText(html, true);
~~~

thì không nên tự đòi phải có text/plain fallback. Một message với body **text/html** đơn vẫn có thể đúng theo cách nó được tạo, dù sản phẩm có thể muốn bổ sung fallback vì khả năng truy cập.

### Kiểm tra ảnh inline

Với:

~~~java
helper.addInline("course-logo", resource, "image/png");
~~~

hãy xác định:

1. Có part **image/png** tương ứng.
2. Part có **Content-ID** phù hợp, ví dụ **<course-logo>**.
3. Nội dung HTML chứa **cid:course-logo**.
4. Quan hệ **multipart/related** phù hợp với cách HTML và image part được nhóm.
5. Part có nguồn bytes thực và có thể được serialize mà không lỗi.

Nếu Content-ID là **logo-1** nhưng HTML tham chiếu **cid:course-logo**, việc có đủ hai part trong cây vẫn không giúp client tìm đúng ảnh. **Content-ID và cid: phải khớp về định danh sử dụng**, kể cả khi raw header có cặp dấu **<...>**.

### Kiểm tra attachment

Với:

~~~java
helper.addAttachment("guide.pdf", pdfResource);
~~~

hãy tìm part có metadata tương ứng:

~~~text
Content-Disposition: attachment; filename="guide.pdf"
Content-Type: application/pdf
Content-Transfer-Encoding: base64
~~~

Loại **application/pdf** là trường hợp phổ biến khi resource/filename được nhận diện; một số môi trường hoặc resource không khai báo loại nội dung có thể nhận **application/octet-stream** hoặc kiểu khác. Vì vậy, việc test đòi tuyệt đối application/pdf nên xuất phát từ **yêu cầu dữ liệu và cách cấu hình Content-Type rõ ràng**, không chỉ dựa vào đuôi filename.

Lưu ý **Content-Transfer-Encoding** có thể được quyết định ở giai đoạn serialize. Với tệp nhị phân, Base64 là lựa chọn phổ biến, nhưng parser nhận thư phải dùng **header thực tế của part** để giải mã, không áp dụng giả định một encoding cho tất cả parts.

## 9. Kiểm tra payload sau giải mã, không đọc Base64 như text

Từ raw MIME:

~~~text
Content-Type: application/pdf
Content-Transfer-Encoding: base64

JVBERi0xLjQK...
~~~

Nếu cần xác minh file PDF không bị thay đổi, không nên so sánh chuỗi Base64 nguyên văn với một chuỗi do ứng dụng tự tạo. Cách xuống dòng Base64 có thể thay đổi, nhưng **byte sau giải mã** vẫn có thể giống nhau.

**Part.getInputStream()** trả dữ liệu của part qua cơ chế xử lý MIME, thường là stream đã được áp dụng **Content-Transfer-Encoding** khi đọc một message đã parse. Vì vậy, có thể lấy byte attachment từ stream đó và tính hash thay vì cố parse dữ liệu raw bằng regex.

Ví dụ phương thức đọc hash của một part:

~~~java
import jakarta.mail.Part;
import java.io.InputStream;
import java.security.MessageDigest;
import java.util.HexFormat;

public final class MimeAttachmentDigest {

    private MimeAttachmentDigest() {
    }

    public static String sha256(Part part) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] buffer = new byte[8192];

        try (InputStream stream = part.getInputStream()) {
            int read;
            while ((read = stream.read(buffer)) != -1) {
                digest.update(buffer, 0, read);
            }
        }

        return HexFormat.of().formatHex(digest.digest());
    }
}
~~~

Trong một bài kiểm tra có kiểm soát, hash của bytes đính kèm sau khi parse có thể được so với hash của file nguồn. Phương thức dùng buffer để tránh đọc cả file vào một mảng byte lớn. Nó giả định caller đã tìm đúng **part attachment**; ví dụ chưa bao gồm logic duyệt cây và chọn part theo filename/disposition.

Hash bằng nhau là bằng chứng bytes được bảo toàn trong đường tạo/serialize/parse được thử, **không phải xác thực chữ ký nguồn gửi**, cũng không đảm bảo attachment an toàn để mở. Dữ liệu đính kèm từ người dùng vẫn phải qua quy trình kiểm tra định dạng, kích thước và bảo mật phù hợp.

## 10. Kiểm tra MIME tree tự động bằng test cấu trúc

Một bài test có thể kiểm tra các tính chất sau:

- Root là một **multipart** phù hợp khi có nhiều phần.
- Có **multipart/alternative** chứa **text/plain** và **text/html**.
- Có ít nhất một part **image/png** tham chiếu bằng Content-ID.
- Có part **application/pdf** (hoặc content type được cấu hình) với **attachment** và filename mong muốn.
- Nội dung plain text và HTML sau giải mã chứa những thông tin nghiệp vụ cần thiết.
- Bytes attachment sau serialize/parse khớp file nguồn khi bài kiểm tra yêu cầu bảo toàn dữ liệu.

Điều quan trọng là **test cấu trúc theo ý nghĩa**, không đóng đinh index của mọi part nếu cấu trúc do helper/version khác nhau mà vẫn đáp ứng nghiệp vụ.

### Ví dụ một phép tìm kiếm đệ quy đơn giản

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public final class MimePartFinder {

    private MimePartFinder() {
    }

    public static List<Part> findByMimeType(
            Part root,
            String expectedMimeType
    ) throws MessagingException, IOException {

        List<Part> found = new ArrayList<>();
        walk(root, expectedMimeType, found);
        return found;
    }

    private static void walk(
            Part part,
            String expectedMimeType,
            List<Part> found
    ) throws MessagingException, IOException {

        if (part.isMimeType(expectedMimeType)) {
            found.add(part);
        }

        if (part.isMimeType("multipart/*")) {
            Object content = part.getContent();
            if (content instanceof Multipart multipart) {
                for (int i = 0; i < multipart.getCount(); i++) {
                    BodyPart child = multipart.getBodyPart(i);
                    walk(child, expectedMimeType, found);
                }
            }
        } else if (part.isMimeType("message/rfc822")) {
            Object content = part.getContent();
            if (content instanceof Message nested) {
                walk(nested, expectedMimeType, found);
            }
        }
    }
}
~~~

Với utility trên, một test có thể bắt đầu:

~~~java
import static org.junit.jupiter.api.Assertions.*;

MimeMessage message = factory.createCourseMail(
        "student@example.test",
        logoPath,
        guidePath
);
message.saveChanges();

assertTrue(message.isMimeType("multipart/mixed"));
assertFalse(
        MimePartFinder.findByMimeType(message, "text/plain").isEmpty()
);
assertFalse(
        MimePartFinder.findByMimeType(message, "text/html").isEmpty()
);
assertFalse(
        MimePartFinder.findByMimeType(message, "image/png").isEmpty()
);
~~~

Đây là **đoạn kiểm tra minh họa**, giả định đã có **factory**, **logoPath**, **guidePath** và dependencies JUnit tương ứng. Nó cho thấy cách duyệt **không phụ thuộc part index**, nhưng một test chặt hơn còn cần xác minh **quan hệ cha/con**, **Content-ID**, **disposition**, **filename** và nội dung, chứ không chỉ nhìn thấy một part mang MIME type mong muốn.

### Vì sao chỉ đếm MIME types chưa đủ?

Một message có **text/html** và **image/png** chưa chắc ảnh đã được HTML sử dụng. Một message có plain và HTML chưa chắc hai phần được đặt trong **multipart/alternative**. Một message có PDF chưa chắc PDF được khai báo **attachment**.

Do đó, các test quan trọng nên tập trung vào **đúng cây con**:

~~~text
alternative
  -> có plain và HTML là sibling đúng quan hệ

related
  -> HTML cùng nhóm với ảnh được tham chiếu bằng cid

mixed
  -> attachment nằm ngoài nhóm nội dung thay thế/related
~~~

Nếu muốn kiểm tra chính xác cha/con, test có thể xây một cấu trúc trung gian mô tả **MIME node, path, type, headers và children** rồi assert các quan hệ tương ứng. Không nên chỉ tìm chuỗi **"multipart/related"** trong toàn bộ raw message, vì chuỗi đó có thể xuất hiện trong header, content hoặc nhiều vị trí không đại diện cho quan hệ mong muốn.

## 11. Những tình huống MIME tree thường giúp phát hiện

### HTML có mặt nhưng thiếu bản plain text

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");
helper.setText("<h1>Xin chào</h1>", true);
~~~

Cây có thể chỉ gồm một part **text/html**. Điều đó phù hợp với lời gọi ở trên: **setText(html, true)** không tự tạo bản plain text thay thế. Nếu sản phẩm yêu cầu fallback cho trình đọc thư không dùng HTML, cần khởi tạo chế độ multipart thích hợp và gọi **setText(plainText, htmlText)**.

### Ảnh có trong tree nhưng không hiển thị trong HTML

~~~text
HTML:    <img src="cid:logo-header">
Part:    Content-ID: <logo-footer>
~~~

Hai định danh khác nhau nên HTML không tham chiếu đúng part ảnh. Trong tình huống khác, Content-ID có thể đúng nhưng:

- Image part nằm ngoài nhóm **multipart/related** mà client cần.
- **Content-Type** không phản ánh đúng loại ảnh.
- File nguồn đã bị xóa hoặc không đọc được khi serialize.
- Email client chặn ảnh hoặc chọn cách hiển thị khác.

**Có đủ part chưa đồng nghĩa các part có quan hệ đúng**, và cây hợp lệ vẫn không bảo đảm mọi client hiển thị giống nhau.

### PDF có trong tree nhưng không xuất hiện như attachment

Nếu part PDF thiếu **Content-Disposition: attachment** hoặc filename, một số email client có thể hiển thị khác ý định. Khi nghiệp vụ yêu cầu file đính kèm, nên tìm metadata như:

~~~text
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice.pdf"
~~~

Trong một số trường hợp, Content-Type có thể là **application/octet-stream** nếu thư viện không nhận diện loại tệp; cần xác định yêu cầu thực sự là metadata nào và liệu byte file có còn nguyên hay không.

### Chỉ đếm part ở root

Một root **multipart/mixed** có thể có **hai part trực tiếp**, nhưng part đầu tiên lại là **multipart/related** chứa **multipart/alternative** và logo. Vì vậy, **root.getCount() == 2** không có nghĩa toàn bộ email chỉ có hai nội dung. Cần duyệt đệ quy.

### Headers transfer encoding chưa xuất hiện

Khi message vẫn đang được xây dựng, một số header có thể được suy ra hoặc hoàn thiện muộn khi **saveChanges()/writeTo()**. Đừng coi việc thiếu **Content-Transfer-Encoding** trước khi serialize là bằng chứng chắc chắn lỗi. Hãy kiểm tra bản raw đã được chuẩn bị và parse lại nếu cần.

### Có filename nhưng file nguồn không đọc được

**addAttachment(...)** có thể gắn một **Resource/DataHandler** mà việc đọc byte thực diễn ra khi message được ghi/gửi. Nếu file tạm bị xóa trước khi serialize, metadata có thể vẫn xuất hiện nhưng lần đọc payload sau đó gặp lỗi. Vì vậy phải phân biệt:

1. **Part được tạo** và có metadata.
2. **Resource còn khả dụng** khi thư viện cần đọc.
3. **Message serialize hoàn chỉnh**, payload đã được xử lý thành công.

## 12. Bộ nhớ, stream và bảo mật khi quan sát cây

Kiểm tra MIME tree nên ưu tiên metadata, tránh đọc không cần thiết toàn bộ attachment. Một file có kích thước lớn có thể khiến quá trình dùng **ByteArrayOutputStream** hoặc chuyển raw message thành **String** tiêu thụ nhiều RAM; Base64 còn làm kích thước biểu diễn tăng thêm.

Với attachment lớn, việc dùng **getInputStream()** theo từng khối để tính hash thường phù hợp hơn tải toàn bộ bytes lên heap. Với nguồn stream chỉ đọc một lần, cần lưu ý Jakarta Mail có thể cần đọc lại tài nguyên khi chuẩn bị message; tránh giả định **InputStreamResource** được mở lại an toàn như file hoặc byte-array resource.

Không nên chia sẻ một **MimeMessage mutable** cho nhiều worker rồi đồng thời gọi **setText**, **addAttachment**, **saveChanges** và **writeTo**. Tốt hơn là tạo một đối tượng message riêng cho mỗi công việc gửi, hoàn thành các thao tác helper rồi mới quan sát hoặc gửi.

### Đừng dump raw email vào production log

Một MIME dump có thể chứa địa chỉ người gửi/người nhận, nội dung giao dịch, URL có token, filename và tệp đính kèm. **Base64 không phải mã hóa bảo mật**; payload có thể được khôi phục về byte ban đầu. Nếu cần điều tra:

- Ưu tiên **dữ liệu giả lập**, mail capture cục bộ và file trong thư mục được bảo vệ.
- Chỉ log các thuộc tính cần thiết như loại part, path trong tree và số lượng part.
- Che địa chỉ, mã định danh và dữ liệu nội dung nhạy cảm trước khi chia sẻ.
- Không đưa nguyên raw MIME, attachment hoặc token vào log tập trung mặc định.
- Xóa bản dump thử nghiệm theo chính sách lưu trữ dữ liệu.

Ngoài ra, việc **getContent()** trên attachment nhị phân chỉ để biết type có thể gây tốn bộ nhớ hoặc tài nguyên. Utility duyệt cây nên gọi **getContent()** khi cần đi sâu vào **multipart** hoặc nested message, còn với leaf thì chỉ đọc metadata, trừ lúc có yêu cầu kiểm tra payload rõ ràng.

## 13. Kiểm tra MIME tree khác với kiểm tra gửi thư và hiển thị

Sau khi kiểm tra MIME structure, có thể gửi thông điệp qua một **SMTP test server/mail capture** để xem bản thư mà transport nộp. Tuy nhiên, phạm vi kiểm tra ở mỗi giai đoạn khác nhau:

| Giai đoạn | Có thể xác nhận | Không thể tự kết luận |
| --- | --- | --- |
| Duyệt object tree | Helper đã tạo các part và metadata nào | Payload đã được ghi hết hay SMTP đã nhận thư |
| Serialize và parse lại .eml | Parser đọc được cấu trúc, headers, encoding và dữ liệu theo phép kiểm tra | Hạ tầng gửi sẽ chấp nhận thư |
| SMTP test server | Transport đã nộp được message vào môi trường kiểm thử | Provider thật sẽ phát thư tới Inbox |
| Mở thư trong email client mục tiêu | Cách một client cụ thể hiển thị HTML, inline image và attachment | Mọi client sẽ hiển thị giống nhau |
| Provider events / DSN | Bằng chứng nộp thư, phát hoặc bounce trong hạ tầng hỗ trợ | Người nhận đã thực sự đọc và hiểu nội dung |

Nếu MIME tree ở ứng dụng đúng nhưng ảnh không hiển thị khi người nhận mở thư, hãy so sánh **bản MIME được tạo tại ứng dụng** với **raw message ở phía nhận**. SMTP gateway hoặc mail server có thể thêm headers như **Received**, **Return-Path**, các kết quả xác thực, và đôi khi thay đổi thông điệp theo chính sách. Một email client cũng có thể chặn ảnh ngay cả khi MIME tree đã đúng.

**JavaMailSender.send(...)** trả về không có nghĩa cây MIME đó đã xuất hiện nguyên vẹn trong Inbox. Nó chỉ là bước gửi qua transport theo hợp đồng API tại thời điểm gọi.

## 14. Tình huống luyện tập

### Tình huống 1: Chỉ có HTML

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");
helper.setText("<h2>Thông báo</h2>", true);
~~~

**Hỏi:** cần tìm **multipart/alternative** trong tree không?

**Đáp:** không bắt buộc. Code chỉ tạo body HTML. Nếu cần cả plain fallback thì phải tạo hai phiên bản nội dung bằng API phù hợp.

### Tình huống 2: HTML có ảnh nội tuyến

~~~text
HTML: <img src="cid:course-logo">
Content-ID: <different-logo>
Content-Type: image/png
~~~

**Hỏi:** có đủ image/png nghĩa là ảnh sẽ hiện?

**Đáp:** không. CID trong HTML khác với Content-ID của image part. Cần khớp định danh và có quan hệ MIME phù hợp với nội dung HTML.

### Tình huống 3: Root có hai part

~~~text
multipart/mixed
  +-- multipart/related
  |    +-- multipart/alternative
  |    |    +-- text/plain
  |    |    '-- text/html
  |    '-- image/png
  '-- application/pdf
~~~

**Hỏi:** vì sao root.getCount() chỉ trả 2?

**Đáp:** vì nó đếm hai **con trực tiếp** của root: related và PDF. Muốn thấy plain, HTML và ảnh phải đi sâu qua các multipart lồng nhau.

### Tình huống 4: Hai raw email khác boundary

Hai lần tạo cùng nội dung có các giá trị boundary và Message-ID khác nhau.

**Hỏi:** có phải lần tạo sau bị lỗi?

**Đáp:** không nhất thiết. Những giá trị này có thể được sinh tự động. Nên so sánh cấu trúc, headers có ý nghĩa và nội dung đã giải mã thay vì so toàn bộ chuỗi raw tuyệt đối.

### Tình huống 5: Attachment có đúng filename nhưng writeTo thất bại

**Hỏi:** liệu chỉ cần kiểm tra MIME tree là đủ?

**Đáp:** không. Part có metadata không đảm bảo nguồn byte còn đọc được. Kiểm tra vòng đời resource, file tạm và giai đoạn serialize để xác định dữ liệu có thể được cung cấp thực sự.

### Tình huống 6: PDF có Content-Type application/octet-stream

**Hỏi:** có chắc người dùng không nhận được PDF?

**Đáp:** chưa đủ căn cứ. File có thể chứa đúng bytes nhưng loại nội dung được mô tả chung chung. Cần xem yêu cầu ứng dụng, attachment disposition, filename và kiểm tra payload sau giải mã.

### Tình huống 7: HTML có logo nhưng email client hiển thị như attachment

**Hỏi:** lỗi chắc chắn do MimeMessageHelper?

**Đáp:** chưa thể kết luận. Cần xem cây related, Content-ID, tham chiếu cid, raw MIME phía nhận và cách client đó xử lý inline resources. Một cấu trúc hợp lệ vẫn có thể được hiển thị khác nhau.

### Tình huống 8: Bài test tìm thấy text/plain và text/html

**Hỏi:** đã đủ chứng minh đó là hai cách hiển thị thay thế của cùng nội dung?

**Đáp:** chưa. Cần xác nhận cả hai thuộc quan hệ **multipart/alternative** tương ứng và nội dung thiết yếu tương đương, không chỉ có hai MIME types ở hai vị trí bất kỳ trong cây.

## 15. Quy trình ghi nhớ

~~~text
1. Xác định nhu cầu nội dung
   -> plain, HTML, alternative, inline, attachment

2. Chọn multipart mode của MimeMessageHelper
   -> NO / MIXED / RELATED / MIXED_RELATED

3. Hoàn thành việc tạo message
   -> setText, addInline, addAttachment
   -> đảm bảo nguồn resource còn đọc được

4. Quan sát MIME tree
   -> root Content-Type và tất cả part con
   -> alternative / related / mixed có đúng quan hệ?
   -> Content-ID, filename, disposition có phù hợp?

5. Khi cần xác nhận dạng MIME hoàn chỉnh
   -> saveChanges
   -> writeTo / serialize
   -> parse lại và kiểm tra metadata, content, bytes

6. Khi cần xác nhận quá trình gửi/hiển thị
   -> SMTP test capture, raw message phía nhận
   -> email client và provider delivery events
~~~

**Kiểm tra MIME tree sau khi MimeMessageHelper tạo message là kiểm tra cấu trúc, không chỉ kiểm tra số phần tử.** Một thông điệp cần có đúng quan hệ giữa các cách trình bày (**alternative**), những tài nguyên phụ thuộc (**related**) và các attachment (**mixed**). Bằng cách duyệt **Part/Multipart** đệ quy, xem **Content-Type/Content-ID/Content-Disposition**, rồi serialize và parse lại khi cần, lập trình viên có thể phát hiện vấn đề của MIME message trước khi gửi và phân biệt nó với lỗi SMTP hoặc hành vi của email client.
