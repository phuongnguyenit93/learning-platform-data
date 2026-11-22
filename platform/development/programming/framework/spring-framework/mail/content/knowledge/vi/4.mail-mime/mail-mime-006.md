# Boundary và cách các phần được phân tách

Một email chỉ có văn bản thuần thường có thể được biểu diễn bằng một phần thân duy nhất. Nhưng một email thông báo trong ứng dụng Spring có thể đồng thời chứa **bản văn bản thuần**, **bản HTML**, **ảnh hiển thị trong HTML** và **tệp PDF đính kèm**. Người nhận cần biết phần nào là nội dung thư, phần nào là tệp, và mỗi phần bắt đầu, kết thúc ở đâu.

**MIME (Multipurpose Internet Mail Extensions)** mở rộng định dạng email để biểu diễn nhiều loại nội dung. Khi email có nhiều thành phần, MIME dùng loại nội dung `multipart/*` và một chuỗi phân cách gọi là **boundary**. Boundary đóng vai trò như những vạch ranh giới có cấu trúc giữa các phần của thông điệp, để chương trình nhận có thể tách và đọc đúng từng phần.

Trong **Spring Framework Mail**, khi sử dụng `JavaMailSender`, `MimeMessage` và `MimeMessageHelper`, thông thường ta **không tự tạo boundary**. Thư viện Jakarta Mail phụ trách sinh và đưa các dấu phân cách phù hợp vào thông điệp. Tuy vậy, hiểu boundary rất có ích khi đọc email gốc, chẩn đoán tệp đính kèm lỗi, phân biệt HTML với ảnh nội tuyến và tìm nguyên nhân một email hiển thị sai.

## 1. Từ email một phần đến email nhiều phần

Một email có hai khu vực lớn:

- **Header của thông điệp**: chứa những trường như `From`, `To`, `Subject`, `MIME-Version` và `Content-Type`.
- **Body của thông điệp**: chứa nội dung. Body có thể là một phần văn bản duy nhất hoặc một cấu trúc nhiều phần được phân cách bằng boundary.

Với nội dung đơn giản:

~~~text
From: notice@example.org
To: reader@example.net
Subject: Hello
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

Hello, your account is ready.
~~~

Dòng trống giữa header và body phân tách **phần đầu email** khỏi **phần thân email**. Trong ví dụ này, `Content-Type: text/plain` cho biết body là văn bản thuần, nên **không cần boundary**.

Ngược lại, khi một email vừa có HTML vừa có tệp đính kèm, body không còn là một khối văn bản đồng nhất. Máy đọc thư phải nhận biết được một danh sách các phần nhỏ hơn. Khi đó header có thể chứa:

~~~text
Content-Type: multipart/mixed; boundary="mail_outer_8d42"
~~~

Các thông tin trong dòng này có ý nghĩa khác nhau:

| Thành phần | Ý nghĩa |
| --- | --- |
| `Content-Type` | Trường MIME cho biết cấu trúc hoặc loại nội dung của body. |
| `multipart/mixed` | Body gồm nhiều phần độc lập, thường dùng khi có tệp đính kèm. |
| `boundary=...` | Tham số công bố chuỗi dùng để nhận diện các dòng phân cách phần. |
| `"mail_outer_8d42"` | Giá trị boundary minh họa; dấu ngoặc kép bao quanh giá trị trong header không phải là một phần của chuỗi boundary. |

Boundary là **một tham số của `Content-Type` ở phần bao ngoài**. Nó không phải địa chỉ email, tên tệp, cổng SMTP hay cơ chế mã hóa.

## 2. Cú pháp chính xác của dấu phân cách

Giả sử phần bao ngoài khai báo:

~~~text
Content-Type: multipart/mixed; boundary="mail_outer_8d42"
~~~

Giá trị boundary là `mail_outer_8d42`. Các dấu phân cách trong body được tạo theo quy tắc:

~~~text
--mail_outer_8d42       ← mở đầu phần thứ nhất
...nội dung phần thứ nhất...

--mail_outer_8d42       ← mở đầu phần tiếp theo
...nội dung phần tiếp theo...

--mail_outer_8d42--     ← kết thúc toàn bộ danh sách phần
~~~

Cần phân biệt **giá trị boundary** với **dòng delimiter**:

| Thành phần | Cú pháp | Vai trò |
| --- | --- | --- |
| Giá trị trong header | `boundary="mail_outer_8d42"` | Cho biết chuỗi nhận diện. |
| Delimiter thông thường | `--mail_outer_8d42` | Kết thúc phần trước và bắt đầu phần kế tiếp. |
| Delimiter đóng | `--mail_outer_8d42--` | Kết thúc vùng multipart hiện tại; hai dấu gạch ngang bổ sung nằm **ở cuối**. |

Hai dấu `--` ở **đầu** dòng delimiter là ký hiệu bắt buộc do MIME quy định; chúng **không nằm trong giá trị** của tham số `boundary` trong ví dụ này. Hai dấu `--` ở **cuối** chỉ xuất hiện với delimiter đóng. Vì vậy:

- `--mail_outer_8d42` là dấu mở ranh giới một phần;
- `--mail_outer_8d42--` là dấu đóng vùng multipart;
- `mail_outer_8d42` đứng một mình trong văn bản **không phải** là dòng delimiter MIME.

Ký tự của boundary có phân biệt chữ hoa, chữ thường. Một dấu phân cách được nhận diện theo đúng chuỗi mà header đã công bố.

### Vị trí và ký tự xuống dòng

Trong dữ liệu MIME chuẩn, các dòng sử dụng kết thúc dòng **CRLF** (`\r\n`). Dòng delimiter phải được đặt ở vị trí đầu một dòng và được tạo đúng cú pháp. Về mặt quy tắc MIME, chuỗi CRLF ngay trước delimiter được xem là gắn với delimiter, không phải nhất thiết là một dòng trống thuộc nội dung trước đó. Điều này có ý nghĩa khi tách dữ liệu nhị phân hoặc kiểm tra độ dài nội dung đã được mã hóa.

Các khối ví dụ ở tài liệu này hiển thị xuống dòng theo cách Markdown thông thường để dễ đọc. Khi gửi thư thật, **thư viện MIME thực hiện chuẩn hóa kết thúc dòng và dựng cấu trúc**. Không nên tự nối các chuỗi văn bản tùy ý rồi đoán cách trình đọc email nhận diện phần.

## 3. Ví dụ hoàn chỉnh: HTML + văn bản + một tệp đính kèm

Hãy xem một thông điệp có hai dạng hiển thị của phần thân và một tệp `note.txt` đính kèm. Đây là **dữ liệu MIME minh họa**, không phải nội dung được gửi từ một hệ thống thật.

~~~text
From: notice@example.org
To: reader@example.net
Subject: Your report
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="outer_8d42"

This is a multipart message.
--outer_8d42
Content-Type: multipart/alternative; boundary="inner_53b7"

--inner_53b7
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: 7bit

Your report is ready.
--inner_53b7
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: 7bit

<p>Your <strong>report</strong> is ready.</p>
--inner_53b7--
--outer_8d42
Content-Type: text/plain; name="note.txt"
Content-Disposition: attachment; filename="note.txt"
Content-Transfer-Encoding: base64

SGVsbG8K
--outer_8d42--
~~~

Thông điệp chứa **hai lớp multipart lồng nhau**:

~~~mermaid
flowchart TD
    A["multipart/mixed — outer_8d42"] --> B["multipart/alternative — inner_53b7"]
    A --> E["attachment — note.txt"]
    B --> C["text/plain"]
    B --> D["text/html"]
~~~

### Đọc ví dụ theo từng lớp

**Lớp ngoài: `multipart/mixed`.** Header của thông điệp công bố `outer_8d42`. Vì thế, `--outer_8d42` xác định từng phần trực tiếp thuộc lớp ngoài. Ở đây, phần thứ nhất là một nhóm nội dung thay thế, phần thứ hai là tệp đính kèm. `--outer_8d42--` đóng lớp ngoài.

**Lớp trong: `multipart/alternative`.** Phần thứ nhất của lớp ngoài lại có header riêng:

~~~text
Content-Type: multipart/alternative; boundary="inner_53b7"
~~~

Phần này chứa hai cách biểu diễn cùng một thông tin: `text/plain` và `text/html`. Trình đọc email có thể chọn dạng hiển thị thích hợp; hai phần không mặc nhiên là hai thông điệp riêng biệt. Dòng `--inner_53b7--` chỉ kết thúc **nhóm alternative**; sau đó trình phân tích vẫn tiếp tục xử lý phần tiếp theo thuộc `outer_8d42`.

**Phần đính kèm.** Tệp `note.txt` được khai báo là `text/plain`, có `Content-Disposition: attachment` và được mã hóa bằng `base64` để đưa vào đường truyền an toàn cho định dạng thông điệp. Chuỗi `SGVsbG8K` chỉ là dữ liệu Base64 minh họa của một tệp văn bản rất nhỏ; nó không phải boundary.

### Vì sao cần hai boundary khác nhau?

Nếu cả lớp ngoài và lớp trong dùng cùng một boundary, trình phân tích sẽ gặp các dòng ranh giới khó phân biệt về phạm vi. Mỗi vùng `multipart` phải có **boundary riêng**, không gây nhầm với các delimiter của lớp cha, lớp con hoặc dữ liệu thực tế. Khi gặp `--inner_53b7--`, trình đọc kết thúc nhóm bên trong rồi quay lại tiếp tục lớp ngoài.

Ranh giới dạng cây giúp MIME biểu diễn nhiều tầng nội dung mà không phải “trải phẳng” tất cả thành một danh sách duy nhất.

## 4. Một MIME part gồm những gì?

Trong vùng `multipart`, mỗi phần thường có cấu trúc:

~~~text
--some_boundary
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
Content-Disposition: inline

...dữ liệu của phần này...
~~~

Ngay sau delimiter, các dòng header dành riêng cho **phần con** xuất hiện; một dòng trống đánh dấu nơi body của phần con bắt đầu. Các header của một part không nhất thiết giống header của toàn email.

| Trường MIME trong một part | Dùng để làm gì? |
| --- | --- |
| `Content-Type` | Chỉ định loại nội dung của part, ví dụ `text/plain`, `text/html`, `image/png`, `application/pdf` hoặc `multipart/related`. |
| `Content-Transfer-Encoding` | Chỉ định cách dữ liệu của part được biểu diễn trong thông điệp, ví dụ `base64` hoặc `quoted-printable`. |
| `Content-Disposition` | Gợi ý cách dùng part: `inline` để thể hiện trong nội dung hoặc `attachment` để coi như đính kèm. |
| `Content-ID` | Cấp định danh cho một part, thường dùng khi HTML tham chiếu ảnh hay tài nguyên nội tuyến bằng `cid:`. |
| `Content-Type: ...; name=...` | Có thể mang tên gợi ý cho tài nguyên; với tệp đính kèm nên quan tâm thêm `filename` của `Content-Disposition`. |

Không phải mọi part đều cần tất cả các header này. Một phần `multipart` là **vùng chứa các part con**, nên bản thân nó có `Content-Type: multipart/...; boundary=...` và trong body lại có các delimiter. Một phần `text/plain` thông thường có body văn bản và không cần khai báo boundary của riêng nó.

**Phân tách bằng boundary** và **giải mã nội dung** là hai công việc khác nhau. Trình đọc MIME trước hết xác định phần nào thuộc vùng bao ngoài, sau đó sử dụng `Content-Transfer-Encoding` và `Content-Type` để diễn giải dữ liệu của từng phần.

## 5. Các loại multipart thường gặp và vai trò của boundary

Boundary sử dụng chung một cơ chế cú pháp, nhưng **loại multipart** quy định quan hệ giữa những phần con.

| Loại | Ý nghĩa thường gặp | Cách đọc điển hình |
| --- | --- | --- |
| `multipart/mixed` | Nhiều phần độc lập theo thứ tự; thường kết hợp nội dung chính và tệp đính kèm | Hiển thị nội dung, đồng thời cung cấp tệp đính kèm để tải xuống |
| `multipart/alternative` | Nhiều cách thể hiện **cùng một nội dung** | Chọn bản phù hợp với khả năng trình đọc; thường có plain text và HTML |
| `multipart/related` | Những phần có quan hệ tạo thành một nội dung tổng thể | HTML tham chiếu ảnh hoặc tài nguyên kèm theo bằng `cid:` |
| `multipart/signed` | Vùng chứa nội dung và chữ ký theo định dạng bảo mật phù hợp | Cần bộ xử lý chữ ký để xác minh; boundary vẫn chỉ phân tách các part |
| `multipart/encrypted` | Vùng chứa thông tin điều khiển và dữ liệu đã mã hóa theo giao thức thích hợp | Boundary không tự mã hóa; cần cơ chế mật mã tương ứng |

### `multipart/alternative`

Ví dụ một email có bản văn bản thuần và bản HTML:

~~~text
Content-Type: multipart/alternative; boundary="alt_q91"

--alt_q91
Content-Type: text/plain; charset=UTF-8

Your booking is confirmed.
--alt_q91
Content-Type: text/html; charset=UTF-8

<p>Your <strong>booking</strong> is confirmed.</p>
--alt_q91--
~~~

Các phần biểu diễn cùng thông tin theo những mức định dạng khác nhau. Theo cách tổ chức thông dụng, dạng đơn giản hơn như `text/plain` xuất hiện trước, còn dạng phong phú hơn như `text/html` theo sau. Trình đọc có thể chọn bản mà nó hỗ trợ tốt nhất, thay vì hiển thị cả hai liên tiếp.

### `multipart/mixed`

Khi email có tài liệu đính kèm, `multipart/mixed` thường là vùng chứa cấp cao:

~~~text
multipart/mixed
├── phần nội dung thư
├── attachment: invoice.pdf
└── attachment: terms.txt
~~~

Mỗi phần có thể có `Content-Type` và `Content-Disposition` của riêng mình. Trình đọc không suy ra tệp đính kèm chỉ bằng tên boundary.

### `multipart/related` và ảnh nội tuyến

Một email HTML có ảnh logo nội tuyến có thể được tổ chức như sau:

~~~text
Content-Type: multipart/related; boundary="rel_x4"

--rel_x4
Content-Type: text/html; charset=UTF-8

<html><body><img src="cid:brand-logo"></body></html>
--rel_x4
Content-Type: image/png
Content-ID: <brand-logo>
Content-Disposition: inline
Content-Transfer-Encoding: base64

...du lieu anh da ma hoa Base64...
--rel_x4--
~~~

`cid:brand-logo` trong HTML tham chiếu part có `Content-ID: <brand-logo>`. Ảnh là **một MIME part riêng**, được liên kết bằng Content-ID. Boundary giúp tìm ranh giới của phần ảnh, nhưng việc HTML gắn ảnh vào vị trí hiển thị dựa vào `cid:` và `Content-ID`.

Trình đọc email và các chính sách bảo mật có thể ảnh hưởng đến việc hiển thị ảnh. Việc thêm ảnh vào MIME không bảo đảm mọi ứng dụng đọc thư đều thể hiện giống nhau.

## 6. Boundary được chọn như thế nào?

Thông thường, thư viện tạo ra một giá trị đủ khác biệt để không vô tình xuất hiện như một dòng delimiter trong dữ liệu được bao bọc.

Một boundary hợp lệ cần tuân theo quy tắc cú pháp MIME; theo RFC 2046, giá trị có độ dài **không quá 70 ký tự** (không tính hai dấu `--` của delimiter), sử dụng các ký tự cho phép và không kết thúc bằng khoảng trắng. Giá trị có thể đặt trong dấu ngoặc kép khi khai báo tham số header. Trong thực tế, nên dùng chuỗi ASCII đơn giản và để thư viện chọn thay vì tự thiết kế.

Ví dụ hai thông điệp độc lập có thể có boundary khác nhau:

~~~text
boundary="----=_Part_842_1234567890"
boundary="----=_Part_843_1234567891"
~~~

Với chuỗi boundary bắt đầu bằng dấu gạch ngang như trên, **delimiter vẫn được thêm hai dấu `--` ở đầu**:

~~~text
------=_Part_842_1234567890
~~~

Không nên cắt hai dấu đầu của giá trị boundary khi đọc header. Chỉ có quy tắc thêm tiền tố `--` để tạo dòng delimiter.

### Boundary phải tránh va chạm với dữ liệu

Giả sử một phần văn bản bất ngờ chứa nguyên dòng:

~~~text
--outer_8d42
~~~

trong khi container đang dùng `outer_8d42` làm boundary. Một MIME parser có thể coi đó là điểm tách phần, khiến dữ liệu bị đọc sai. Vì vậy, boundary phải được chọn sao cho không trùng với dòng delimiter trong các part được chứa; boundary của multipart lồng nhau cũng phải khác nhau và tránh gây nhập nhằng.

Đây là một lý do nên để Jakarta Mail tạo MIME: việc xử lý boundary và encoding phải diễn ra đồng bộ với dữ liệu của thông điệp.

## 7. Preamble và epilogue là gì?

MIME cho phép có nội dung trước delimiter đầu tiên và sau delimiter đóng:

~~~text
Content-Type: multipart/mixed; boundary="demo_123"

This message uses MIME multipart.
--demo_123
Content-Type: text/plain

Hello.
--demo_123--
Optional text after the final delimiter.
~~~

- **Preamble**: vùng văn bản sau phần header của multipart nhưng **trước** dòng `--demo_123` đầu tiên.
- **Epilogue**: vùng văn bản **sau** dòng `--demo_123--` kết thúc multipart.

Trình đọc MIME thường bỏ qua cả hai khi dựng nội dung các part. Preamble lịch sử được dùng để cung cấp gợi ý cho phần mềm chưa hỗ trợ MIME; nó **không phải part đầu tiên**. Epilogue cũng không phải một tệp đính kèm bổ sung.

Khi tự xem thông điệp raw, đừng nhầm preamble với `text/plain` của email hay tưởng rằng cứ có chữ sau boundary đóng là một part mới.

## 8. Boundary và Content-Transfer-Encoding có quan hệ ra sao?

SMTP và định dạng email truyền thống ban đầu được xây dựng xoay quanh dữ liệu dạng dòng. MIME có thể cần mang theo tệp PDF, ảnh hoặc văn bản nhiều ký tự ngoài ASCII. Vì thế, mỗi part có thể khai báo cách chuyển dữ liệu thành dạng phù hợp để truyền.

Ví dụ:

~~~text
--file_20
Content-Type: application/pdf
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="guide.pdf"

JVBERi0xLjQKJ...
--file_20--
~~~

`base64` cho biết dữ liệu tệp đang được biểu diễn bằng ký tự văn bản; khi nhận, trình xử lý sẽ giải mã chuỗi đó để thu lại byte của tệp. Trong khi đó, `--file_20--` là delimiter kết thúc **container**, không phải dữ liệu Base64.

Điểm cần nhớ:

1. **Boundary làm việc ở cấu trúc MIME**, xác định nơi part bắt đầu và kết thúc.
2. **Content-Transfer-Encoding làm việc ở dữ liệu một part**, xác định cách đọc và giải mã phần thân đã tách.
3. **Content-Type và charset** hướng dẫn cách diễn giải dữ liệu sau khi giải mã, chẳng hạn văn bản UTF-8 hay ảnh PNG.
4. **Content-Disposition/Content-ID** giúp trình đọc quyết định phần đó là tệp, tài nguyên nội tuyến hay lựa chọn hiển thị khác.

Với `quoted-printable`, các ký tự nhất định có thể được biểu diễn bằng dấu bằng và mã byte, thích hợp cho văn bản có nhiều ký tự thông thường. Với `base64`, dữ liệu nhị phân được biểu diễn thành chuỗi ký tự an toàn hơn cho môi trường truyền email. Không nên dùng các chuỗi đã mã hóa để suy ra trực tiếp nội dung hiển thị nếu chưa giải mã và biết charset.

**Không đặt delimiter vào bên trong chuỗi Base64 rồi mong trình đọc tự đoán**. Boundary phải xuất hiện ở đúng vị trí trong cấu trúc MIME do phần chứa quy định.

## 9. Cơ chế nhận diện và phân tích multipart

Có thể hình dung quá trình một MIME parser xử lý thông điệp:

~~~mermaid
flowchart TD
    A["Đọc header của MIME entity"] --> B{"Content-Type có là multipart?"}
    B -->|"Không"| C["Giải mã/diễn giải body theo Content-Type và encoding"]
    B -->|"Có"| D["Lấy tham số boundary"]
    D --> E["Tìm dòng delimiter đầu tiên"]
    E --> F["Đọc header của part kế tiếp"]
    F --> G{"Part là multipart?"}
    G -->|"Có"| H["Phân tích đệ quy với boundary riêng"]
    G -->|"Không"| I["Đọc body cho đến delimiter của container"]
    H --> J{"Delimiter kế tiếp?"}
    I --> J
    J -->|"Delimiter thường"| F
    J -->|"Delimiter đóng"| K["Kết thúc container; quay về phần cha"]
~~~

Đây là mô hình khái niệm. Bộ phân tích thật phải tuân thủ các quy tắc cú pháp header, dòng, encoding, phần lồng nhau và giới hạn tài nguyên. Một chuỗi tìm kiếm đơn giản với `split("--boundary")` không đủ để triển khai MIME parser đúng chuẩn vì có thể cắt nhầm nội dung, xử lý sai CRLF, nhầm delimiter đóng hoặc phân tích sai phần lồng nhau.

Trong một email, **mỗi cấp multipart dùng chính boundary được khai báo ở header của cấp đó**. Một delimiter của cấp cha không thay thế delimiter của cấp con. Khi cấp con đóng lại, bộ phân tích tiếp tục xử lý cấu trúc cấp cha.

## 10. Spring Framework Mail tạo multipart và boundary như thế nào?

Spring Framework Mail cung cấp `MimeMessageHelper` để xây dựng thông điệp MIME thuận tiện. Lập trình viên thường quyết định **nội dung logic** — văn bản, HTML, ảnh, tệp — và để Jakarta Mail xử lý phần serialization, bao gồm header, boundary và các dấu phân cách.

### 10.1. Ví dụ: một email có plain text, HTML, ảnh nội tuyến và PDF

Giả sử ứng dụng có hai tài nguyên trên classpath:

~~~text
src/main/resources/mail/logo.png
src/main/resources/mail/guide.pdf
~~~

Ta có thể viết dịch vụ:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class GuideMailService {
    private final JavaMailSender mailSender;

    public GuideMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendGuide(String recipient) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom("notice@example.org");
        helper.setTo(recipient);
        helper.setSubject("Tài liệu hướng dẫn");

        String plainText = "Tài liệu hướng dẫn đã được đính kèm.";
        String htmlText = """
                <html>
                  <body>
                    <p>Tài liệu hướng dẫn đã được đính kèm.</p>
                    <img src="cid:brandLogo" alt="Logo">
                  </body>
                </html>
                """;

        // Hai cách biểu diễn cùng một nội dung.
        helper.setText(plainText, htmlText);

        // Thêm tài nguyên nội tuyến sau khi đã đặt HTML.
        helper.addInline(
                "brandLogo",
                new ClassPathResource("mail/logo.png"),
                "image/png"
        );

        // Tệp độc lập được gắn vào email.
        helper.addAttachment(
                "guide.pdf",
                new ClassPathResource("mail/guide.pdf"),
                "application/pdf"
        );

        mailSender.send(message);
    }
}
~~~

Lưu ý khi triển khai ví dụ: địa chỉ gửi phải được nhà cung cấp SMTP cho phép; các file tài nguyên phải thực sự có trong classpath lúc chạy; máy chủ SMTP và thông tin xác thực cần được cấu hình riêng. Ví dụ thể hiện thao tác soạn thư MIME chứ không mô tả một dịch vụ email đã được vận hành.

Điểm đáng chú ý của mã:

- `mailSender.createMimeMessage()` tạo đối tượng MIME thuộc Jakarta Mail.
- Chế độ `MULTIPART_MODE_MIXED_RELATED` giúp tổ chức một vùng chứa tổng hợp với các phần nội dung có liên hệ và phần đính kèm.
- `helper.setText(plainText, htmlText)` cung cấp hai cách thể hiện văn bản để tạo cấu trúc thích hợp cho `multipart/alternative`.
- `helper.addInline("brandLogo", ...)` đăng ký ảnh nội tuyến có Content-ID được HTML tham chiếu bằng `cid:brandLogo`.
- `helper.addAttachment(...)` thêm tệp như một MIME part đính kèm.
- Khi `mailSender.send(message)` thực hiện gửi, Jakarta Mail hoàn thiện biểu diễn MIME để vận chuyển, bao gồm boundary cho các multipart cần thiết.

Không nên giả định chính xác từng chuỗi boundary hoặc thứ tự mọi header mà Jakarta Mail sẽ sinh. Chúng có thể khác theo phiên bản, chế độ multipart, đặc điểm dữ liệu và quá trình lưu/gửi. Quan trọng là các part và quan hệ MIME được tạo đúng.

### 10.2. Vì sao không tự đặt boundary trong mã Java?

Thông thường, ứng dụng chỉ cần gọi:

~~~java
helper.setText(plainText, htmlText);
helper.addInline("brandLogo", logoResource, "image/png");
helper.addAttachment("guide.pdf", pdfResource, "application/pdf");
~~~

Nếu tự đặt `Content-Type: multipart/mixed; boundary=...` nhưng vẫn để helper tạo body, có thể khiến **giá trị trong header không khớp delimiter được sinh trong body**. Trình đọc khi đó không thể tìm đúng các phần, dù nội dung Java đã tạo đủ tệp và HTML.

Tương tự, tự viết các dòng `--boundary` vào chuỗi HTML hoặc plain text không tạo thêm MIME part: chúng chỉ là ký tự nội dung của part hiện tại, trừ khi phần mềm dựng MIME đã thiết lập cấu trúc container tương ứng. Hãy để `MimeMessageHelper` hoặc API Jakarta Mail chuyên dụng quản lý cấu trúc thay vì ghép chuỗi thô.

### 10.3. Chọn chế độ multipart của MimeMessageHelper

`MimeMessageHelper` cung cấp nhiều chế độ tạo multipart tùy nhu cầu và khả năng tương thích của trình đọc email:

| Chế độ | Ý nghĩa khái quát |
| --- | --- |
| `MULTIPART_MODE_NO` | Không dựng cấu trúc multipart; phù hợp khi không cần tài nguyên nội tuyến hay tệp đính kèm. |
| `MULTIPART_MODE_MIXED` | Dùng cấu trúc `multipart/mixed`, thường phục vụ những part đính kèm. |
| `MULTIPART_MODE_RELATED` | Dùng cấu trúc `multipart/related` để gắn những tài nguyên có liên hệ với nội dung chính. |
| `MULTIPART_MODE_MIXED_RELATED` | Tổ chức kết hợp vùng `mixed` và `related` cho trường hợp có nội dung HTML/ảnh nội tuyến cùng tệp đính kèm. |

Khi tạo helper bằng constructor nhận cờ boolean, ví dụ `new MimeMessageHelper(message, true, "UTF-8")`, Spring chọn chế độ multipart mặc định của helper. Dùng hằng số chế độ rõ ràng sẽ dễ diễn đạt ý định khi cần kiểm soát cấu trúc.

### 10.4. Thứ tự gọi setText và addInline

Khi HTML tham chiếu ảnh bằng `cid:`, nên **gọi `setText(...)` trước, sau đó gọi `addInline(...)`**. Thứ tự này giúp tránh vấn đề một số trình đọc email không phân giải được các tham chiếu nội tuyến.

Nếu có tệp đính kèm, `addAttachment(...)` tạo phần tương ứng và thiết lập các header MIME cần thiết. Tên tệp có ký tự không phải ASCII có thể cần cách mã hóa header phù hợp; các API thư viện giúp xử lý những yêu cầu này tốt hơn việc tự ghép header thủ công.

## 11. Phân biệt boundary MIME với dấu kết thúc DATA của SMTP

Boundary **không phải** dấu kết thúc thông điệp của phiên SMTP. Đây là hai tầng quy tắc khác nhau:

- **MIME:** `--some_boundary` và `--some_boundary--` phân tách những phần bên trong **một email**.
- **SMTP DATA:** khi gửi thư theo SMTP thông thường, dòng chỉ chứa một dấu chấm (`.`) — tức chuỗi `<CRLF>.<CRLF>` — kết thúc phần truyền dữ liệu thông điệp của lệnh `DATA`.

Ví dụ ở mức minh họa:

~~~text
C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: Content-Type: multipart/mixed; boundary="abc123"
C:
C: --abc123
C: Content-Type: text/plain
C:
C: Hello
C: --abc123--
C: .
S: 250 Message accepted
~~~

`--abc123--` kết thúc cấu trúc multipart ở **bên trong dữ liệu email**. Dòng `.` kết thúc **SMTP DATA** để máy chủ SMTP biết client đã truyền xong thông điệp. Nếu bản thân nội dung có dòng bắt đầu bằng dấu chấm, SMTP còn có quy tắc **dot-stuffing** để tránh hiểu nhầm thành kết thúc DATA; đây cũng là việc của tầng truyền SMTP, tách biệt với MIME.

Tương tự, STARTTLS chỉ bảo vệ kênh SMTP; nó không quy định cách phân chia multipart trong body. Một email có thể có cấu trúc MIME giống nhau bất kể kết nối SMTP dùng TLS hay không.

## 12. Những lỗi thường gặp với boundary

### 12.1. Khai báo boundary và delimiter không trùng nhau

Ví dụ header:

~~~text
Content-Type: multipart/mixed; boundary="part_A"
~~~

nhưng phần thân lại dùng:

~~~text
--part_B
Content-Type: text/plain

Hello
--part_B--
~~~

Trình đọc tìm delimiter của `part_A` và có thể không tách được các part. Cần đảm bảo đúng giá trị, đúng chữ hoa/thường và đúng tiền tố `--`.

### 12.2. Quên delimiter đóng

Nếu có nhiều part nhưng không có `--boundary--` kết thúc, parser có thể coi thông điệp bị cắt cụt hoặc áp dụng cơ chế phục hồi riêng. Một số phần mềm hiển thị được một phần nội dung, số khác báo lỗi hoặc bỏ qua tệp đính kèm. Không thể dựa vào khả năng tự sửa lỗi của trình đọc email.

### 12.3. Dùng cùng boundary cho những lớp lồng nhau

Nếu `multipart/mixed` và `multipart/alternative` bên trong khai báo cùng một giá trị, quá trình xác định nơi kết thúc cấu trúc con và nơi bắt đầu phần của cấu trúc cha có thể nhập nhằng. Mỗi container phải dùng một boundary thích hợp, không trùng với delimiter trong các phần bên trong.

### 12.4. Có boundary nhưng thiếu Content-Type multipart

Các dấu `--xyz` trong body không tự biến một thư `text/plain` thành multipart. Parser dựa vào `Content-Type` và tham số `boundary` của **container** để hiểu các dòng delimiter. Nếu toàn bộ email được khai báo là `text/plain`, những dấu này có thể chỉ được hiển thị như văn bản.

### 12.5. Phần thân nhị phân bị thay đổi hoặc mã hóa sai

Nếu một tệp được đưa vào MIME mà không có `Content-Transfer-Encoding` phù hợp, dữ liệu có thể không đi qua các khâu truyền thống an toàn hoặc gây nhầm lẫn cho phần mềm đọc. Hãy để thư viện mã hóa từng part; không chèn trực tiếp byte nhị phân tùy ý vào chuỗi MIME raw.

### 12.6. Tưởng Content-Disposition là delimiter

`Content-Disposition: attachment` giúp ứng dụng đọc thư hiểu đây là tệp đính kèm; nó không chỉ ra điểm bắt đầu/kết thúc của part. Việc tách phần vẫn dựa vào boundary của container. Ngược lại, có boundary đúng cũng không tự làm phần đó xuất hiện như một tệp đính kèm nếu các metadata liên quan không được đặt phù hợp.

### 12.7. Tự sửa header MIME sau khi helper đã dựng cấu trúc

Nếu sửa `Content-Type` hoặc chèn boundary thủ công sau khi `MimeMessageHelper` đã chuẩn bị các part, thông điệp có nguy cơ có header và body không nhất quán. Nên sử dụng API của thư viện để thay đổi cấu trúc và để thư viện serialize lại đúng cách.

## 13. Quan sát MIME trong quá trình xử lý sự cố

Khi một email gửi được nhưng HTML bị hiển thị như tệp đính kèm, ảnh `cid:` không xuất hiện hoặc PDF bị lỗi, có thể quan sát phần **nguồn MIME gốc** của email trong môi trường kiểm thử.

Một quy trình đọc hữu ích:

1. Tìm `MIME-Version` và `Content-Type` ở cấp thông điệp.
2. Nếu thấy `multipart/*`, ghi nhận giá trị `boundary` của chính cấp đó.
3. Tìm các delimiter bắt đầu bằng `--<boundary>` và delimiter đóng `--<boundary>--`.
4. Trong từng part, đọc `Content-Type`, `Content-Transfer-Encoding`, `Content-Disposition` và `Content-ID` nếu có.
5. Nếu part tiếp tục là `multipart/*`, lặp lại quy trình bằng **boundary mới của part con**.
6. Khi đã xác định đúng part, mới diễn giải dữ liệu sau khi giải mã; ví dụ `text/html`, ảnh có `cid:` hay tệp `application/pdf`.

Để suy luận nhanh, có thể biểu diễn dạng cây:

~~~text
message/rfc822
└── multipart/mixed [boundary = outer]
    ├── multipart/related [boundary = related]
    │   ├── multipart/alternative [boundary = alt]
    │   │   ├── text/plain
    │   │   └── text/html
    │   └── image/png [Content-ID: <brandLogo>]
    └── application/pdf [attachment]
~~~

Cây trên chỉ là **một cấu trúc có thể có**, không phải bắt buộc cho mọi thư chứa HTML và ảnh. Cấu trúc thực tế do công cụ tạo MIME và cách ứng dụng khai báo nội dung quyết định.

Khi lưu hoặc chia sẻ email raw để gỡ lỗi, cần loại bỏ địa chỉ người dùng, token, nội dung nhạy cảm và dữ liệu tệp thực. Một thông điệp MIME có thể chứa đầy đủ nội dung email ở dạng văn bản hoặc dạng có thể giải mã dễ dàng từ Base64.

## 14. Câu hỏi thực hành

**Câu 1.** Header khai báo `boundary="abc"`. Dòng nào đánh dấu kết thúc tất cả các phần của container?

~~~text
--abc
--abc--
abc--
~~~

**Đáp án:** `--abc--`. Dòng `--abc` chỉ bắt đầu một part tiếp theo; `abc--` không phải cú pháp delimiter hợp lệ cho boundary này.

**Câu 2.** Một phần trong `multipart/mixed` có `Content-Type: multipart/alternative; boundary="alt"`. Khi gặp `--alt--`, toàn email đã kết thúc chưa?

**Chưa.** Chỉ vùng `multipart/alternative` kết thúc; parser quay về vùng `multipart/mixed` của cấp cha để tìm những part tiếp theo.

**Câu 3.** Một ảnh có `Content-ID: <banner>`. HTML muốn dùng ảnh đó thì có thể tham chiếu thế nào?

~~~html
<img src="cid:banner" alt="Banner">
~~~

**Giải thích:** Boundary tách part ảnh ra khỏi các part khác; `Content-ID` và `cid:` giúp HTML liên kết đúng ảnh.

**Câu 4.** Khi dùng `MimeMessageHelper` gửi HTML và PDF, có cần tự ghép các dòng `--boundary` không?

**Không.** Nên gọi `setText(...)` và `addAttachment(...)` với chế độ multipart phù hợp, rồi để Jakarta Mail sinh và xuất cấu trúc MIME.

**Câu 5.** Vì sao `Content-Transfer-Encoding: base64` không thay thế boundary?

Vì Base64 mô tả **cách biểu diễn dữ liệu của một part**, còn boundary mô tả **ranh giới giữa các part** trong container.

## 15. Mô hình ghi nhớ

Một email MIME nhiều phần giống một **cây các vùng chứa**. Mỗi vùng `multipart` tự công bố loại quan hệ của các phần con (`mixed`, `alternative`, `related`, ...) và **một boundary riêng** để phân chia những phần trực tiếp thuộc vùng đó. Mỗi part có header của riêng mình để mô tả kiểu dữ liệu, cách mã hóa, vị trí hiển thị hoặc quan hệ với các part khác.

Trong Spring Framework Mail, **`MimeMessageHelper` là nơi lập trình viên mô tả nội dung logic**, còn **Jakarta Mail chịu trách nhiệm biến cấu trúc ấy thành thông điệp MIME đúng định dạng**. Khi thấy HTML lỗi, ảnh nội tuyến không hiển thị hoặc tệp đính kèm không đọc được, hãy xác định lớp multipart, boundary của lớp đó, các header part và dữ liệu đã được mã hóa trước khi tìm nguyên nhân ở SMTP hay giao diện đọc thư.

