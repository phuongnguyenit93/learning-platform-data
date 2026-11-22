# Base64, quoted-printable và dữ liệu nhị phân

Trong **Spring Framework Mail**, một email có thể chứa văn bản tiếng Việt, HTML, ảnh nội tuyến, PDF và những tệp nhị phân khác. Đối với người lập trình, việc thêm nội dung có vẻ đơn giản: tạo **MimeMessage**, gọi **MimeMessageHelper.setText(...)** hoặc **addAttachment(...)**, rồi dùng **JavaMailSender.send(...)**. Tuy nhiên, SMTP và định dạng thư điện tử được xây dựng từ thời các hệ thống vận chuyển chủ yếu làm việc với ký tự ASCII. Vì vậy, dữ liệu cần được mô tả và đôi khi phải **mã hóa để vận chuyển** trước khi chuyển qua đường email.

Hai phương pháp thường gặp là **Base64** và **quoted-printable**. Chúng cùng thuộc khái niệm **Content-Transfer-Encoding** của MIME nhưng giải quyết các trường hợp dữ liệu khác nhau. Hiểu cách chúng hoạt động giúp ta đọc raw email, nhận biết lỗi dấu tiếng Việt, dự đoán kích thước tệp đính kèm và tránh nhầm lẫn giữa nội dung nhị phân với văn bản mà người dùng nhìn thấy.

## 1. Tại sao cần MIME và mã hóa truyền tải?

**MIME (Multipurpose Internet Mail Extensions)** mở rộng định dạng email để mô tả nhiều loại nội dung: **text/plain**, **text/html**, **image/png**, **application/pdf**, **multipart/mixed** và nhiều kiểu khác. MIME sử dụng các header để cho biết một phần thư mang loại dữ liệu nào, dùng bộ ký tự nào và được biểu diễn thế nào khi truyền tải.

Trước khi có các mở rộng phù hợp, đường vận chuyển thư truyền thống chủ yếu được thiết kế cho dữ liệu **7-bit**. Một byte UTF-8 biểu diễn dấu tiếng Việt có thể vượt quá phạm vi ASCII 7-bit; tệp PDF hay PNG thì chứa các byte tùy ý, kể cả byte không phải ký tự văn bản. Chuyển trực tiếp những byte này qua một tuyến chỉ xử lý 7-bit có thể làm nội dung bị biến đổi hoặc bị từ chối.

MIME giúp tách hai câu hỏi quan trọng:

- **Nội dung là gì?** Ví dụ văn bản UTF-8, HTML, ảnh PNG hoặc tệp PDF. Đây là trách nhiệm của **Content-Type** và các tham số liên quan.
- **Nội dung được biểu diễn thành byte/ký tự nào để vận chuyển?** Đây là trách nhiệm của **Content-Transfer-Encoding**, ví dụ **base64**, **quoted-printable**, **7bit**, **8bit** hoặc **binary**.

Ví dụ:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xin ch=C3=A0o!
~~~

Trong phần trên, chuỗi người dùng cần thấy là **Xin chào!**, nhưng dòng raw chứa **=C3=A0** thay cho chữ **à**. Bộ ký tự **UTF-8** quyết định các byte **C3 A0** tương ứng với ký tự à; **quoted-printable** quyết định biểu diễn các byte đó bằng những ký tự ASCII an toàn khi vận chuyển.

### Ba tầng biến đổi cần phân biệt

~~~text
Ký tự người dùng nhìn thấy
       |
       | Charset (ví dụ UTF-8)
       v
Chuỗi byte đại diện cho văn bản
       |
       | Content-Transfer-Encoding (QP hoặc Base64)
       v
Biểu diễn truyền tải trong phần thân MIME
       |
       | SMTP / hạ tầng email
       v
Bên nhận giải mã truyền tải -> giải mã charset -> hiển thị
~~~

**Charset** và **transfer encoding** không phải cùng một khái niệm. UTF-8 không phải Base64; Base64 cũng không cho biết chuỗi byte sau giải mã là tiếng Việt, PDF hay ảnh. Phải dựa vào các MIME headers tương ứng để diễn giải đúng dữ liệu.

## 2. Cấu trúc của một phần nội dung MIME

Một phần MIME thường có headers và thân nội dung, ngăn nhau bởi một dòng trống:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: base64

SGVsbG8=
~~~

Phần thân raw ở đây là **SGVsbG8=**. Sau khi giải mã Base64, thu được các byte ASCII của **Hello**. Nếu header nói **charset=UTF-8**, trình đọc thư tiếp tục giải mã byte thành ký tự tương ứng. Với chuỗi tiếng Anh đơn giản, ASCII và UTF-8 cho ra cùng kết quả.

Các header quan trọng:

| Header | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Content-Type** | Dữ liệu thuộc loại nào? | **text/plain**, **text/html**, **application/pdf** |
| **charset** (tham số Content-Type) | Byte văn bản được giải mã thành ký tự theo bộ mã nào? | **UTF-8** |
| **Content-Transfer-Encoding** | Thân phần MIME được mã hóa thế nào cho mục đích vận chuyển? | **base64**, **quoted-printable** |
| **Content-Disposition** | Phần này nên được trình bày như nội dung hay tệp đính kèm? | **inline**, **attachment** |
| **filename** / **name** | Tên tệp hoặc tên gợi ý khi hiển thị | **invoice.pdf** |
| **Content-ID** | Định danh một MIME part, thường để HTML tham chiếu tài nguyên nội tuyến | **<logo-1@example.test>** |

**Content-Disposition: attachment** không thay thế **Content-Type** hay **Content-Transfer-Encoding**. Cùng một phần PDF vẫn có thể dùng **Content-Type: application/pdf**, **Content-Disposition: attachment** và **Content-Transfer-Encoding: base64**.

MIME có thể là một phần duy nhất hoặc cấu trúc **multipart** chứa nhiều phần, mỗi phần có Content-Type và Content-Transfer-Encoding riêng. Không có quy tắc một email phải sử dụng cùng một transfer encoding cho tất cả nội dung.

## 3. Base64: biến byte tùy ý thành ký tự có thể vận chuyển

**Base64** là một phép biến đổi có thể đảo ngược: nó mã hóa dữ liệu byte thành các ký tự thuộc bảng chữ cái Base64, chủ yếu gồm **A–Z**, **a–z**, **0–9**, **+**, **/** và ký tự đệm **=** khi cần. Bộ ký tự này nằm trong ASCII nên thuận tiện khi đi qua hạ tầng vốn xử lý văn bản 7-bit.

### Nguyên lý 3 byte thành 4 ký tự

Base64 gom tối đa **3 byte = 24 bit**, chia thành **4 nhóm 6 bit**. Mỗi nhóm ánh xạ tới một ký tự Base64. Khi dữ liệu không đủ 3 byte cuối cùng, phép mã hóa thường bổ sung **=** để hoàn thành nhóm 4 ký tự.

~~~text
Bytes ban đầu:
  00        FF        10
00000000  11111111  00010000

Chia 24 bit thành 4 nhóm:
000000  001111  111100  010000
   0      15      60      16
   A       P       8       Q

Kết quả Base64: AP8Q
~~~

Với chuỗi **Hello**:

~~~text
Bytes ASCII: 48 65 6C 6C 6F
Base64:      SGVsbG8=
~~~

Ví dụ tệp nhị phân có ba byte **00 FF 10** cho thấy Base64 không phụ thuộc dữ liệu có phải văn bản hay không. Nó chỉ xử lý **byte**.

### Kích thước tăng bao nhiêu?

Với **n** byte đầu vào, số ký tự Base64 trước khi xuống dòng thường là:

~~~text
4 * ceil(n / 3)
~~~

Tỷ lệ tiệm cận là **4/3**, nghĩa là dữ liệu lớn thường tăng khoảng **33%** chỉ do Base64. MIME Base64 cũng thường xuống dòng sau tối đa **76 ký tự mã hóa**, nên khi tính kích thước dữ liệu qua mạng còn phải kể đến các ký tự ngắt dòng **CRLF**, MIME headers và ranh giới multipart.

Ví dụ, nếu một tệp có kích thước danh nghĩa **3 MiB** thì phần Base64 của nó cần khoảng **4 MiB** ký tự trước khi tính CRLF và overhead khác. Do đó, giới hạn “dung lượng file đính kèm” mà giao diện đưa ra không nhất thiết bằng giới hạn kích thước **toàn bộ email truyền qua SMTP**.

### Base64 MIME và Base64 trong API không hoàn toàn giống cách trình bày

Base64 được dùng trong MIME thuộc biến thể truyền tải email có quy tắc chia dòng. Khi làm việc với Base64 trong URL hoặc một số API JSON, ta có thể gặp Base64 không xuống dòng hoặc **base64url** dùng ký tự **-**, **_** thay cho **+**, **/**. Không nên giả định mọi chuỗi Base64 đều có cùng cách xuống dòng, bảng chữ cái và quy tắc đệm.

Khi đọc raw email, **Content-Transfer-Encoding: base64** cho phép trình phân tích MIME áp dụng đúng quy tắc giải mã của email; ứng dụng thường không cần tự xóa CRLF rồi viết decoder tùy chỉnh.

### Base64 không phải mã hóa bảo mật

Bất kỳ ai có dữ liệu Base64 đều có thể giải mã trở lại byte ban đầu. Base64:

- **Không mã hóa bí mật**; người có raw message có thể đọc dữ liệu sau giải mã.
- **Không nén nội dung**; kích thước thường tăng.
- **Không bảo vệ tính toàn vẹn** khỏi thay đổi có chủ ý.
- **Không xác thực người gửi**.

Muốn bảo vệ email trên đường truyền, cần cơ chế phù hợp như **TLS** khi vận chuyển; muốn bảo vệ nội dung đầu cuối cần công nghệ mã hóa/ký nội dung như **S/MIME** hoặc giải pháp tương đương, tùy nghiệp vụ. Base64 chỉ là một lớp **biểu diễn dữ liệu để vận chuyển**.

## 4. Quoted-printable: giữ văn bản dễ đọc ở dạng raw

**Quoted-printable** đặc biệt phù hợp khi phần lớn nội dung là ASCII và chỉ có một số byte không thể biểu diễn trực tiếp an toàn. Thay vì chuyển toàn bộ byte thành ký tự Base64, nó giữ nguyên nhiều ký tự ASCII in được và dùng dạng **=HH** để biểu diễn các byte cần mã hóa, trong đó **HH** là hai chữ số thập lục phân.

Ví dụ chữ **Café** được mã hóa UTF-8 thành các byte:

~~~text
C    a    f     é
43   61   66   C3 A9
~~~

Khi dùng quoted-printable, một cách biểu diễn hợp lệ là:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Caf=C3=A9
~~~

Đối với tiếng Việt:

~~~text
Văn bản: Xin chào!
UTF-8 của "à": C3 A0
Quoted-printable: Xin ch=C3=A0o!
~~~

Với văn bản tiếng Anh hay nội dung HTML chứa chủ yếu ASCII, quoted-printable thường dễ đọc hơn Base64 trong raw message. Nếu văn bản có quá nhiều byte ngoài ASCII, mỗi byte phải biểu diễn bằng ba ký tự **=HH**, nên kích thước có thể tăng đáng kể; Base64 đôi khi kinh tế hơn về kích thước.

### Dấu bằng và khoảng trắng có ý nghĩa đặc biệt

Dấu **=** là ký tự điều khiển của quoted-printable. Khi chính dữ liệu chứa dấu bằng, nó cần được mã hóa thành **=3D** ở nơi yêu cầu. Ví dụ:

~~~text
Văn bản gốc: A=B
Quoted-printable: A=3DB
~~~

Khoảng trắng hoặc tab ở **cuối dòng mã hóa** cũng cần được bảo vệ, chẳng hạn khoảng trắng có thể được biểu diễn bằng **=20**. Nếu đặt khoảng trắng nguyên dạng ở cuối dòng, một số hệ thống vận chuyển hoặc trình xử lý có thể xóa nó, làm mất dữ liệu. Quoted-printable có những quy tắc chính xác để tránh trường hợp này.

### Soft line break khác xuống dòng trong văn bản

Quoted-printable giới hạn mỗi dòng mã hóa **tối đa 76 ký tự** theo quy định MIME. Nếu một dòng nội dung dài, encoder có thể chèn **soft line break**: dấu **=** ngay trước **CRLF**. Khi giải mã, tổ hợp này được **loại bỏ**, vì nó chỉ dùng để chia dòng cho vận chuyển.

~~~text
Dữ liệu raw:
Day la mot dong rat dai nen bi chia o day=
 va phan tiep theo van cung mot dong.
~~~

Sau khi giải mã, dấu **=** cùng cặp ngắt dòng ngay sau nó biến mất; phần tiếp nối thuộc **cùng một dòng logic**. Ngược lại, ngắt dòng thông thường không có **=** ở cuối là xuống dòng thực sự của nội dung sau giải mã.

Điều này quan trọng khi so sánh văn bản người dùng nhìn thấy với raw email: các dòng raw không phải lúc nào cũng là các dòng nội dung.

### Khi nào quoted-printable kém phù hợp?

Nếu dữ liệu chứa nhiều byte nhị phân như **00**, **FF** hoặc hàng loạt byte không in được, quoted-printable phải mã hóa từng byte thành **=HH** khiến dữ liệu rất dài và khó đọc. Trong trường hợp đó Base64 thường phù hợp hơn.

## 5. So sánh Base64, quoted-printable và các giá trị transfer encoding khác

MIME định nghĩa nhiều lựa chọn **Content-Transfer-Encoding**. Điều quan trọng là không đồng nhất các giá trị này với **Content-Type**.

| Giá trị | Ý nghĩa | Khi thường dùng | Lưu ý |
| --- | --- | --- | --- |
| **7bit** | Thân phần chỉ dùng dữ liệu phù hợp giới hạn 7-bit của thư truyền thống | Văn bản ASCII đơn giản | Không dùng để chuyển trực tiếp byte UTF-8 ngoài ASCII hay nhị phân tùy ý |
| **quoted-printable** | Byte cần bảo vệ được biểu diễn bằng **=HH**, phần lớn ASCII có thể giữ nguyên | Văn bản gần ASCII, HTML hoặc plain text | Dễ đọc raw nhưng tăng kích thước khi nhiều byte không phải ASCII |
| **base64** | Mỗi 3 byte được mã hóa thành tối đa 4 ký tự ASCII | Ảnh, PDF, tệp nhị phân và một số phần văn bản | Tăng kích thước khoảng 33% cộng overhead xuống dòng |
| **8bit** | Cho phép byte có bit thứ tám trong nội dung | Văn bản được vận chuyển qua tuyến hỗ trợ 8-bit | Phụ thuộc khả năng hỗ trợ và giới hạn của SMTP |
| **binary** | Cho phép dữ liệu nhị phân không bị ràng buộc như 7bit/8bit | Những tuyến và giao thức hỗ trợ binary MIME | Cần điều kiện giao thức phù hợp; không phải tính năng mặc định của mọi SMTP server |

### 8BITMIME và BINARYMIME liên quan gì tới SMTP?

**8BITMIME** là phần mở rộng SMTP cho phép truyền nội dung 8-bit theo các ràng buộc tương ứng, thay vì bắt buộc mọi nội dung đi qua biểu diễn ASCII 7-bit. Tuy nhiên, **8-bit** không có nghĩa tất cả byte nhị phân đều được chấp nhận: độ dài dòng, cách kết thúc dòng và các giới hạn khác vẫn quan trọng.

**BINARYMIME** cùng với cơ chế truyền phù hợp như **CHUNKING/BDAT** cho phép xử lý nội dung nhị phân trực tiếp ở các chặng hỗ trợ. Khả năng này không nên được giả định trong một hệ thống SMTP nói chung; các tuyến chuyển tiếp có thể khác nhau về hỗ trợ phần mở rộng và cách xử lý.

Vì tính tương thích rộng, **base64** vẫn là lựa chọn phổ biến cho attachment nhị phân, ngay cả khi một số hệ thống có khả năng vận chuyển 8-bit hoặc binary.

**Không thể tự đặt Content-Transfer-Encoding: 8bit hoặc binary và mặc nhiên cho rằng mọi SMTP server trên đường đi sẽ xử lý đúng.** Phần metadata và khả năng vận chuyển thực sự phải phù hợp với nhau.

## 6. Multipart: trong một email có thể dùng nhiều encoding

Một email thực tế có thể có cả text plain, text HTML và PDF đính kèm. Cấu trúc MIME thường là một cây: **multipart/mixed** bao phần nội dung chính cùng các attachment; bên trong nội dung chính có thể có **multipart/alternative** cho các cách hiển thị khác nhau.

~~~text
multipart/mixed
|
+-- multipart/alternative
|   |
|   +-- text/plain; charset=UTF-8
|   |       Content-Transfer-Encoding: quoted-printable
|   |
|   +-- text/html; charset=UTF-8
|           Content-Transfer-Encoding: quoted-printable
|
+-- application/pdf
        Content-Transfer-Encoding: base64
        Content-Disposition: attachment
~~~

Trong ví dụ này, **multipart** chỉ mô tả các phần được ghép vào cùng thông điệp; mỗi phần con tự chỉ định loại nội dung và transfer encoding của nó. Phần plain và HTML là **hai phương án hiển thị thay thế**, không phải hai đoạn văn bắt buộc hiện đồng thời. Phần PDF là attachment.

### Một raw MIME message rút gọn

~~~text
MIME-Version: 1.0
From: sender@example.test
To: reader@example.test
Subject: Tai lieu
Content-Type: multipart/mixed; boundary="mix-01"

--mix-01
Content-Type: multipart/alternative; boundary="alt-01"

--alt-01
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xin ch=C3=A0o!

--alt-01
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<p>Xin ch=C3=A0o!</p>

--alt-01--
--mix-01
Content-Type: application/pdf; name="guide.pdf"
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="guide.pdf"

JVBERi0xLjQK

--mix-01--
~~~

**Ví dụ được rút gọn để minh họa cấu trúc**, không phải một tệp PDF hoàn chỉnh. **JVBERi0xLjQK** là đầu biểu diễn Base64 của chuỗi byte bắt đầu bằng **%PDF-1.4** và ký tự xuống dòng; để có một PDF thật phải có toàn bộ nội dung tệp được mã hóa. Dấu **--mix-01** và **--alt-01** là boundary dùng phân định các phần; chúng không thuộc dữ liệu của attachment.

Khi giải mã, trình đọc thư phải:

1. Phân tích boundary và MIME headers để xác định từng phần.
2. Áp dụng **Content-Transfer-Encoding** của từng phần (ví dụ quoted-printable hoặc base64).
3. Với phần **text/**, sử dụng **charset** để biến byte thành ký tự.
4. Với phần nhị phân, chuyển byte đã giải mã cho bộ xử lý tương ứng (PDF viewer, ứng dụng tải file, trình hiển thị ảnh).

Lấy một block Base64 trong raw email rồi hiển thị trực tiếp như văn bản UTF-8 sẽ tạo ra ký tự vô nghĩa, vì nó có thể đại diện cho PDF hoặc ảnh chứ không phải text.

## 7. Văn bản tiếng Việt: charset sai khác transfer encoding sai

Vấn đề dấu tiếng Việt là một trường hợp điển hình giúp nhận biết các lớp encoding.

Giả sử nội dung mong muốn là:

~~~text
Xin chào!
~~~

Ở UTF-8, byte của chữ **à** là **C3 A0**. Khi dùng quoted-printable, raw message có thể ghi:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xin ch=C3=A0o!
~~~

Ở phía nhận, nếu giải mã QP đúng nhưng **giải mã byte theo charset sai**, người dùng có thể thấy chữ lỗi dấu (mojibake). Ngược lại, nếu charset UTF-8 được khai báo đúng mà QP không được giải mã, người dùng có thể nhìn thấy nguyên chuỗi **=C3=A0**.

Để hiểu nơi lỗi xảy ra, hãy phân loại triệu chứng:

| Triệu chứng | Khả năng cần điều tra |
| --- | --- |
| Người đọc thấy **Xin ch=C3=A0o** | MIME QP chưa được giải mã, hoặc dữ liệu QP bị đưa vào như text thuần |
| Người đọc thấy chuỗi ký tự lạ sau khi decoding | Sai charset, nội dung được tạo bằng charset khác với khai báo |
| Attachment mở ra báo hỏng | Dữ liệu đã bị thay đổi, bị cắt hoặc metadata/transfer encoding không phù hợp |
| Raw email chứa Base64 dài | Có thể hoàn toàn bình thường; phải giải mã theo Content-Transfer-Encoding |
| Attachment lớn hơn tệp gốc | Overhead Base64, xuống dòng và MIME headers là điều thường gặp |

Việc chỉ đổi **Content-Type: text/plain** thành **text/html** không chữa được lỗi bytes hoặc charset. Cần đảm bảo dữ liệu đầu vào, charset khi tạo MIME message và transfer encoding phù hợp với nhau.

## 8. Tạo email có tiếng Việt và attachment bằng Spring Mail

**Spring Framework Mail** cung cấp **JavaMailSender** và **MimeMessageHelper** để tạo thông điệp mà không phải tự ghép từng dòng MIME. Với Spring dựa trên Jakarta Mail, ví dụ sau gửi nội dung plain text, HTML và PDF:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class GuideMailService {

    private final JavaMailSender mailSender;

    public GuideMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendGuide(String recipient, Path pdfFile)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom("no-reply@example.test");
        helper.setTo(recipient);
        helper.setSubject("Tài liệu hướng dẫn");

        helper.setText(
                "Xin chào! Tài liệu của bạn được đính kèm.",
                "<p>Xin chào! <strong>Tài liệu</strong> của bạn được đính kèm.</p>"
        );

        helper.addAttachment(
                "guide.pdf",
                new FileSystemResource(pdfFile.toFile())
        );

        mailSender.send(message);
    }
}
~~~

Ví dụ dùng hai biến thể nội dung:

- Tham số thứ nhất của **setText(plainText, htmlText)** là plain text.
- Tham số thứ hai là HTML.
- **addAttachment(...)** thêm tệp PDF như một phần MIME riêng.
- Tham số **"UTF-8"** yêu cầu tạo headers/nội dung văn bản theo charset phù hợp.

**MimeMessageHelper** kết hợp với thư viện Jakarta Mail để xây dựng các phần MIME. Tầng mail quyết định cách mã hóa truyền tải phù hợp cho từng phần; mã ứng dụng thông thường **không cần tự Base64-encode PDF** hay tự biến tiếng Việt thành **=HH** trước khi gọi **addAttachment** hoặc **setText**.

Đặc biệt, tránh tự gọi mã hóa Base64 trên byte PDF rồi đưa **chuỗi Base64** cho **addAttachment** như thể đó là tệp PDF nguyên bản. Khi Jakarta Mail mã hóa cho MIME lần nữa, người nhận có thể tải một attachment chứa **văn bản Base64** thay vì nội dung PDF thật. Đó là tình huống **double encoding**.

### Vì sao dùng FileSystemResource?

**FileSystemResource** cho phép Jakarta Mail đọc nội dung tệp từ hệ thống file theo cơ chế Resource khi tạo/gửi phần MIME. Với nội dung trong bộ nhớ, có thể dùng **ByteArrayResource**, nhưng cần cân nhắc kích thước RAM khi tạo hàng loạt thư lớn. Với nguồn stream, phải chú ý khả năng mở lại stream vì bộ phận gửi có thể cần đọc dữ liệu nhiều lần trong quá trình chuẩn bị MIME.

Nếu phải đính kèm file do người dùng tải lên, nên kiểm tra giới hạn dung lượng, tên file, loại nội dung và quyền truy cập trước khi đưa file vào thông điệp. Đừng coi **Content-Type** do client gửi lên là bằng chứng chắc chắn file đó an toàn hay thuộc định dạng đã khai báo.

## 9. Ảnh nội tuyến khác tệp đính kèm ở điểm nào?

Ảnh hiển thị bên trong HTML email thường được đưa vào một phần MIME riêng với **Content-ID**, rồi HTML tham chiếu bằng đường dẫn **cid:**. Ví dụ:

~~~html
<html>
  <body>
    <p>Xin chào!</p>
    <img src="cid:course-logo" alt="Logo khóa học">
  </body>
</html>
~~~

Phần ảnh liên quan có thể mang các header:

~~~text
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-ID: <course-logo>
Content-Disposition: inline

[dữ liệu ảnh PNG được mã hóa Base64]
~~~

Dòng trong ngoặc vuông chỉ là mô tả, không phải payload Base64 hợp lệ. **Content-ID** liên kết phần nhị phân với tham chiếu **cid:** bên trong HTML; **Content-Disposition: inline** gợi ý trình đọc thư hiển thị phần đó trong nội dung thay vì coi như attachment thông thường.

Một ví dụ thêm ảnh nội tuyến qua Spring:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8"
);

helper.setFrom("no-reply@example.test");
helper.setTo("student@example.test");
helper.setSubject("Thông báo khóa học");
helper.setText(
        "<p>Chào bạn!</p><img src=\"cid:course-logo\" alt=\"Logo\">",
        true
);

helper.addInline(
        "course-logo",
        new FileSystemResource("assets/course-logo.png"),
        "image/png"
);

mailSender.send(message);
~~~

Trong mã trên, cần tạo nội dung HTML bằng **setText(...)** trước khi gọi **addInline(...)** theo cách sử dụng **MimeMessageHelper** thông thường. Chuỗi **course-logo** ở **cid:** và **addInline(...)** phải khớp. Đường dẫn tài nguyên chỉ là ví dụ; ứng dụng thực tế phải biết file ảnh nằm ở đâu.

**Inline** là cách sắp xếp, tham chiếu và hiển thị nội dung, còn **Base64** là cách biểu diễn byte để vận chuyển. Một ảnh inline vẫn có thể có **Content-Transfer-Encoding: base64**, tương tự ảnh đính kèm. Không nên coi hai khái niệm là lựa chọn loại trừ nhau.

Ngoài ra, một số email client chặn ảnh hoặc không hiển thị inline image như mong muốn. Thuộc tính **alt** và nội dung HTML/text rõ nghĩa vẫn cần thiết; việc mã hóa đúng chỉ giải quyết vấn đề vận chuyển byte, không bảo đảm cách hiển thị trên mọi client.

## 10. Mã hóa phần thân khác mã hóa header email

Những trường như **Subject**, tên hiển thị người gửi hoặc tên tệp đính kèm cũng có thể chứa tiếng Việt:

~~~text
Subject: Tài liệu buổi học
From: "Bộ phận đào tạo" <training@example.test>
Content-Disposition: attachment; filename="báo cáo.pdf"
~~~

Tuy nhiên, cơ chế xử lý ký tự không phải ASCII trong **header** không giống việc dùng **Content-Transfer-Encoding** cho phần **body**.

Với các header văn bản truyền thống, MIME định nghĩa cơ chế **encoded-word** (RFC 2047), có các dạng:

~~~text
=?charset?B?encoded-text?=
=?charset?Q?encoded-text?=
~~~

Trong đó **B** là cách mã hóa dựa trên Base64 cho *một đoạn văn bản của header*, còn **Q** là dạng dành cho header, gần với quoted-printable nhưng có những quy tắc riêng. Ví dụ với chữ **Café**, một biểu diễn header hợp lệ là:

~~~text
Subject: =?UTF-8?B?Q2Fmw6k=?=
~~~

Người đọc thư phù hợp sẽ giải mã nội dung header và hiển thị **Café**. Ngược lại, phần thân thư có thể có:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Caf=C3=A9
~~~

Nhìn giống đều có Base64 hoặc quoted-printable, nhưng **ngữ cảnh cú pháp khác nhau**. Không nên lấy raw body QP chèn thẳng vào Subject rồi chờ email client hiểu đúng.

Tên file đính kèm có ký tự ngoài ASCII có thể sử dụng cơ chế tham số mở rộng như **RFC 2231**, tùy thư viện và hệ thống gửi/nhận. Nếu dùng **MimeMessageHelper.setSubject(...)** và **addAttachment(...)**, nên để thư viện mail tạo phần header phù hợp. Khi cần hỗ trợ client cũ, vẫn cần quan sát tên file thực nhận thay vì tự viết chuỗi mã hóa vào header một cách tùy tiện.

### SMTPUTF8 có thay thế Base64 và quoted-printable không?

**SMTPUTF8** mở rộng khả năng sử dụng ký tự quốc tế trong các danh tính/header email khi các bên hỗ trợ. Đây là một chủ đề **khác** với việc biểu diễn phần thân và attachment bằng MIME transfer encoding. Một tuyến email hỗ trợ địa chỉ quốc tế không có nghĩa mọi phần nhị phân sẽ được truyền nguyên dạng hoặc rằng Base64 và QP trở nên vô dụng.

Khi debug lỗi ký tự, cần xác định lỗi xảy ra ở **header**, **body**, **địa chỉ email** hay **filename**, vì mỗi vùng có quy tắc và hỗ trợ giao thức khác nhau.

## 11. Một số lỗi thường gặp với MIME encoding

### Lỗi 1: Đưa dữ liệu Base64 vào setText rồi mong người nhận nhận file

Ví dụ:

~~~java
String encodedPdf = /* Base64 của nội dung PDF */;
helper.setText(encodedPdf, false);
~~~

Phương thức **setText(...)** tạo **nội dung văn bản**, vì vậy người nhận có thể thấy chuỗi Base64 dài thay vì có một file PDF đính kèm. Muốn gửi PDF, cần đưa **byte thật** của PDF vào một MIME part có Content-Type và Content-Disposition phù hợp, thường qua **addAttachment(...)**.

Ngược lại, nếu API của nhà cung cấp email *yêu cầu JSON chứa chuỗi Base64 của attachment* thì phải tuân theo hợp đồng của API đó. Cách gọi provider API và cách gọi **JavaMailSender** là hai tầng khác nhau; không áp dụng máy móc cùng một cách chuẩn bị dữ liệu.

### Lỗi 2: Mã hóa Base64 hai lần

Giả sử một tệp chứa các byte nhị phân **00 FF 10**. Base64 đúng của nó là **AP8Q**. Nếu ứng dụng lại lấy bytes của chuỗi ký tự **AP8Q** rồi Base64-encode lần nữa, dữ liệu sau giải mã một lần chỉ là văn bản **AP8Q**, không phải ba byte ban đầu.

Một MIME mail client thường giải mã **một lớp Content-Transfer-Encoding** theo header. Nó không tự biết cần tiếp tục Base64-decode thêm một lần nữa. Vì vậy phải biết rõ dữ liệu trong application đang là **raw bytes** hay **encoded text** trước khi đưa vào mail API.

### Lỗi 3: Chọn charset không khớp với byte đầu vào

Ví dụ body chứa byte UTF-8 nhưng metadata lại ghi **charset=ISO-8859-1**. Quoted-printable hoặc Base64 có thể giải mã hoàn toàn chính xác ở tầng vận chuyển, song các byte sau đó bị chuyển thành ký tự sai. Lỗi không nằm ở chính Base64/QP.

Đối với dữ liệu text do ứng dụng tạo, nên thống nhất sử dụng UTF-8 khi có thể, và tránh những bước chuyển đổi byte/String không xác định charset.

### Lỗi 4: Sửa trực tiếp raw MIME rồi làm hỏng boundary

Một multipart email phụ thuộc vào các dòng **--boundary** và header từng part. Nếu tự nối file, thêm dấu xuống dòng sai vị trí hoặc cắt payload khi truyền, parser ở phía nhận có thể không nhận ra attachment hoặc báo MIME không hợp lệ.

Làm việc với **MimeMessage**, **MimeBodyPart** hoặc **MimeMessageHelper** thường an toàn hơn tự ghép văn bản MIME, nhất là khi có nhiều phần và attachment.

### Lỗi 5: Nhìn thấy chuỗi =HH và nghĩ nội dung đã bị hỏng

Trong raw email, **=C3=A0** là biểu diễn bình thường của byte UTF-8 theo quoted-printable; **SGVsbG8=** là biểu diễn bình thường của Hello theo Base64. Cần đọc **Content-Transfer-Encoding** trước khi kết luận dữ liệu sai.

Nếu giao diện email hiển thị nguyên những chuỗi đó thay vì text sau giải mã, lúc ấy mới cần điều tra quá trình tạo MIME hoặc xử lý ở phía nhận.

### Lỗi 6: Coi Content-Type là bằng chứng tệp an toàn

Attachment khai báo **Content-Type: application/pdf** vẫn có thể chứa dữ liệu không phải PDF. Base64 chỉ biến đổi byte, không xác nhận nội dung. Với hệ thống nhận file do người dùng cung cấp, cần kiểm tra định dạng thực tế, giới hạn dung lượng và quét nội dung theo yêu cầu bảo mật; không dựa vào đuôi file hoặc MIME header.

## 12. Giới hạn kích thước và hiệu năng khi gửi file nhị phân

Với email có attachment, kích thước toàn bộ thông điệp thường lớn hơn tổng byte của các file ban đầu:

~~~text
Kích thước gửi qua SMTP
  ≈ nội dung text đã mã hóa
    + phần Base64 của attachments
    + CRLF chia dòng
    + MIME headers và boundaries
    + các headers email
~~~

Chẳng hạn, một file **9 MiB** đã chiếm khoảng **12 MiB** chỉ tính ký tự Base64, chưa kể chia dòng và những phần khác. Nếu một provider đặt giới hạn tổng thông điệp là một mức nhất định, ứng dụng không nên cho phép attachment sát bằng mức giới hạn đó rồi mặc định gửi được.

Những chi phí nên cân nhắc:

- **Băng thông và thời gian SMTP:** Base64 tăng số byte cần chuyển.
- **Bộ nhớ:** lưu nhiều attachment dưới dạng byte array đồng thời có thể làm heap tăng nhanh.
- **Đọc file/stream:** dữ liệu đính kèm có thể cần được đọc khi thông điệp được serialize hoặc gửi.
- **Hàng đợi và retry:** gửi lại một thông điệp lớn tiêu tốn băng thông và thời gian đáng kể.
- **Giới hạn provider:** nhà cung cấp có thể giới hạn tổng kích thước thư, số recipient, lưu lượng hoặc định dạng attachment.

Nếu tệp rất lớn hoặc cần nhiều người tải về, giải pháp hợp lý có thể là **lưu tệp ở một dịch vụ lưu trữ có kiểm soát quyền và gửi đường dẫn tải có thời hạn**. Cách đó tránh phải sao chép nội dung nhị phân vào mỗi thông điệp, nhưng cần thiết kế quyền truy cập, thời hạn link và quy trình thu hồi độc lập.

### Lưu ý về dữ liệu nhị phân và CRLF

Đừng đọc một file nhị phân bằng **Reader** rồi ghi lại bằng **Writer** để chuẩn bị attachment. Quá trình chuyển byte thành ký tự có thể làm thay đổi dữ liệu, đặc biệt với byte không hợp lệ trong charset đã chọn. File PDF, ZIP hoặc ảnh phải đi qua **byte stream/Resource**, còn plain text mới đi qua lớp charset.

Trong quoted-printable, CRLF có thể là một phần của quy tắc biểu diễn dòng văn bản; trong Base64, những ngắt dòng của biểu diễn mã hóa thường bị bỏ qua khi khôi phục **payload bytes**. Hai cơ chế có xử lý dòng khác nhau; không nên dùng thao tác thay thế ký tự xuống dòng tùy tiện cho cả hai.

## 13. Cách đọc và xử lý một email MIME khi nhận

Giả sử ứng dụng cần đọc thư phản hồi có attachment. Quy trình khái niệm:

~~~text
Nhận raw email
    |
    v
Đọc MIME headers của thông điệp
    |
    v
Nếu multipart, phân tách các MIME part theo boundary
    |
    +--> Với text/plain hoặc text/html:
    |      Giải mã transfer encoding
    |      Chuyển byte thành text theo charset
    |
    +--> Với application/pdf hoặc image/png:
    |      Giải mã transfer encoding
    |      Thu được byte của tệp hoặc ảnh
    |
    v
Kiểm tra, lưu trữ hoặc hiển thị theo loại nội dung
~~~

Một parser MIME tốt phải quan sát **Content-Type** của từng part và cả cấu trúc multipart lồng nhau. Không thể đơn giản chia raw email tại từ khóa **Content-Transfer-Encoding** rồi mong phần tiếp theo luôn là attachment.

Khi nhận dữ liệu từ bên ngoài, cũng cần giới hạn kích thước thư, số phần MIME, độ sâu multipart và tài nguyên giải mã. Một email có thể chứa nhiều phần hoặc cấu trúc bất thường; không nên để quá trình phân tích file tiêu tốn tài nguyên vô hạn.

### Kiểm tra tính toàn vẹn của attachment

Về nguyên tắc, Base64 và quoted-printable là các phép biến đổi không làm mất thông tin nếu được mã hóa và giải mã đúng. Vì vậy:

~~~text
raw bytes
  -> MIME transfer encode
  -> MIME transfer decode
  -> raw bytes ban đầu
~~~

Nếu cần xác minh dữ liệu không bị thay đổi, có thể so sánh **hash** của byte trước gửi và byte sau nhận trong một bài kiểm tra có kiểm soát. Nhưng việc truyền qua MIME không tự cung cấp chữ ký bảo mật; để xác thực tính toàn vẹn/chủ thể cần dùng cơ chế ký hoặc xác thực phù hợp.

## 14. Bài tập phân tích

### Tình huống A: Hai email có nội dung hiển thị giống nhau

Email thứ nhất:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Caf=C3=A9
~~~

Email thứ hai:

~~~text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: base64

Q2Fmw6k=
~~~

**Hỏi:** người nhận có thể nhìn thấy nội dung khác nhau không?

**Đáp:** nếu được giải mã đúng theo headers, cả hai đều hiển thị **Café**. Hai phần có **biểu diễn truyền tải khác nhau** nhưng cùng chuỗi byte UTF-8 sau giải mã.

### Tình huống B: Thấy file PDF dưới dạng chuỗi Base64

Một đoạn raw email có:

~~~text
Content-Type: application/pdf
Content-Disposition: attachment; filename="manual.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQK
~~~

**Hỏi:** tại sao không thể mở đoạn Base64 đó thành PDF hoàn chỉnh?

**Đáp:** vì đây chỉ là vài byte đầu được mã hóa, không có toàn bộ cấu trúc file PDF. Muốn tải về PDF hợp lệ, bộ nhận phải giải mã **toàn bộ body part** và có đầy đủ dữ liệu đầu vào. Việc thấy tiền tố Base64 thường gặp của PDF không bảo đảm payload đã đủ hoặc đúng định dạng.

### Tình huống C: Mail có dấu tiếng Việt hiển thị hỏng

Một email khai báo:

~~~text
Content-Type: text/plain; charset=ISO-8859-1
Content-Transfer-Encoding: quoted-printable

Caf=C3=A9
~~~

**Hỏi:** lỗi ở đâu nếu người gửi thực sự sử dụng byte UTF-8 cho phần body?

**Đáp:** QP có thể giải mã chính xác thành byte **43 61 66 C3 A9**, nhưng charset khai báo **ISO-8859-1** không phù hợp với byte UTF-8 gốc. Cần sửa cách tạo và khai báo charset, thay vì đổi bừa quoted-printable thành Base64.

### Tình huống D: Mail có plain text, HTML và file đính kèm

**Hỏi:** có bắt buộc cả ba phần cùng dùng Base64 không?

**Đáp:** không. Mỗi MIME part có thể dùng transfer encoding riêng. Plain text và HTML có thể dùng quoted-printable, còn file nhị phân dùng Base64. Cấu trúc multipart mô tả quan hệ giữa các phần và không áp đặt một encoding duy nhất.

### Tình huống E: Đổi từ Base64 sang 8bit để giảm kích thước

**Hỏi:** chỉ sửa header thành **Content-Transfer-Encoding: 8bit** có đủ không?

**Đáp:** không. Phải bảo đảm body phù hợp biểu diễn 8bit và đường vận chuyển SMTP thực sự hỗ trợ; **8bit không thể chuyển tùy ý mọi byte nhị phân** như một attachment PDF/ZIP. Nếu không chắc các điều kiện, Base64 vẫn là giải pháp tương thích rộng.

## 15. Những nguyên tắc nên ghi nhớ

Khi tạo email trong Spring Framework Mail, có thể suy luận theo thứ tự:

~~~text
Nội dung là văn bản?
    |
    +-- Có:
    |     Chọn charset, thường là UTF-8
    |     -> tạo text/plain hoặc text/html
    |     -> thư viện chọn transfer encoding phù hợp
    |
    +-- Không:
          Giữ nguyên byte nhị phân
          -> đưa vào một MIME part có Content-Type đúng
          -> thư viện áp dụng Base64 khi phù hợp

Có nhiều nội dung?
    -> dùng multipart và xác định quan hệ alternative/related/mixed

Muốn xem raw email?
    -> đọc Content-Type, charset, Content-Transfer-Encoding
    -> giải mã theo từng MIME part

Gặp lỗi tiếng Việt hoặc file hỏng?
    -> xác định sai ở charset, transfer encoding,
       cấu trúc multipart hay byte đầu vào
~~~

**Base64** phù hợp với byte tùy ý, đặc biệt là attachment nhị phân; **quoted-printable** phù hợp với văn bản có nhiều ký tự ASCII và muốn giữ phần raw tương đối dễ đọc. Cả hai chỉ là **cơ chế mã hóa để vận chuyển của MIME**, không định nghĩa nội dung là gì, không đảm bảo thư được phát thành công và không phải giải pháp mã hóa bảo mật.

Trong Spring, cách làm bền vững là **đưa đúng dữ liệu gốc vào JavaMailSender/MimeMessageHelper, chọn charset và MIME structure phù hợp, rồi để tầng mail xử lý mã hóa truyền tải**. Khi đọc một email nhận được, hãy thực hiện quá trình ngược lại: phân tích MIME, giải mã transfer encoding, sau đó mới diễn giải byte theo Content-Type và charset.
