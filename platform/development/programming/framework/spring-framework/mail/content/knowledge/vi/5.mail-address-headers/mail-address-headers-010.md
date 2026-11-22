# Danh sách người nhận rỗng, trùng hoặc không hợp lệ

Khi gửi email bằng **Spring Framework Mail**, việc tạo tiêu đề và nội dung mới chỉ là một nửa công việc. Ứng dụng còn phải xác định **ai được nhận thư**, mỗi người xuất hiện trong nhóm **To**, **Cc** hay **Bcc**, và danh sách địa chỉ đó có phù hợp với quy tắc nghiệp vụ hay không. Một danh sách người nhận bị bỏ trống, chứa địa chỉ lặp hoặc có cú pháp không hợp lệ có thể khiến thao tác gửi thất bại, gửi nhiều thư ngoài ý muốn hoặc vô tình tiết lộ địa chỉ của người nhận.

Những vấn đề này đặc biệt dễ xảy ra khi địa chỉ được tập hợp từ nhiều nguồn: biểu mẫu đăng ký, cơ sở dữ liệu, nhóm phân phối, hệ thống CRM, nhiều người phê duyệt hoặc dữ liệu import từ CSV. Một giá trị trông giống email trong giao diện chưa chắc là một **mailbox** hợp lệ, và một mailbox được viết đúng cú pháp cũng chưa chắc tồn tại hoặc nhận được thư.

Bài học tập trung vào cách nhận diện, xử lý và thiết kế ranh giới trách nhiệm cho **danh sách người nhận rỗng, trùng hoặc không hợp lệ** trong Spring Mail. Các ví dụ sử dụng **JavaMailSender**, **SimpleMailMessage**, **MimeMessageHelper** và **Jakarta Mail**.

## 1. Phân biệt người nhận hiển thị và người nhận vận chuyển

Email có hai lớp thông tin liên quan đến người nhận:

- **Header recipients**: các trường **To**, **Cc** và **Bcc** được ứng dụng dùng khi chuẩn bị thông điệp MIME.
- **SMTP envelope recipients**: các địa chỉ được trình SMTP gửi qua lệnh **RCPT TO** để yêu cầu máy chủ tiếp nhận xử lý thư.

Trong cách sử dụng thông thường của **JavaMailSender**, các địa chỉ được đặt vào trường To/Cc/Bcc của thông điệp sẽ là nguồn để tầng Jakarta Mail xác định người nhận cho quá trình gửi. Tuy nhiên, một SMTP transaction còn có thể nhận danh sách envelope recipients được chỉ định riêng bởi API/transport, và email có thể trải qua alias hoặc forwarding ở những máy chủ tiếp theo.

~~~text
Nguồn dữ liệu ứng dụng
    |
    | Lấy danh sách To / Cc / Bcc
    v
Kiểm tra rỗng, cú pháp, trùng và chính sách nghiệp vụ
    |
    v
MimeMessage hoặc SimpleMailMessage
    |
    | Header: To, Cc, Bcc
    v
JavaMailSender / Jakarta Mail
    |
    | SMTP: RCPT TO cho các đích gửi
    v
Mail server
    |
    | Chấp nhận, từ chối hoặc trì hoãn từng địa chỉ;
    | có thể định tuyến, mở rộng alias hoặc forward
    v
Hộp thư cuối cùng (nếu phát thành công)
~~~

**Điểm mấu chốt:** tiêu chí có người nhận để gửi thường là **có ít nhất một địa chỉ đích hợp lệ trong tập người nhận thực tế**, chứ không nhất thiết phải có phần tử trong **To**. Một thư chỉ có **Bcc** vẫn có thể gửi được. Ngược lại, header To chứa dòng chữ mang tính trình bày không tự tạo ra một người nhận SMTP.

### To, Cc và Bcc có ý nghĩa khác nhau

| Nhóm | Ý nghĩa thông thường | Ai có thể nhìn thấy? |
| --- | --- | --- |
| **To** | Người nhận chính | Được hiển thị trong header thư |
| **Cc** | Người nhận bản sao công khai | Được hiển thị trong header thư |
| **Bcc** | Người nhận bản sao ẩn | Không được tiết lộ danh sách Bcc cho các người nhận khác |

Về vận chuyển, một địa chỉ ở To, Cc hoặc Bcc đều có thể dẫn đến lệnh **RCPT TO**. Nhưng về nghiệp vụ và quyền riêng tư, ba nhóm có **ngữ nghĩa khác nhau**. Vì vậy, xử lý trùng lặp không đơn giản là gộp cả ba danh sách lại rồi ghi tất cả vào To.

## 2. Danh sách người nhận rỗng: nhiều trường hợp khác nhau

Từ “rỗng” có thể chỉ nhiều trạng thái đầu vào:

~~~text
to = null
to = []
to = [""]
to = ["   "]
to = ["", "  ", null]
to = []
cc = []
bcc = ["hidden@example.test"]
~~~

Bốn ví dụ đầu chưa cung cấp một mailbox có thể dùng; ví dụ cuối lại **có một người nhận Bcc** dù To và Cc đều rỗng. Quy tắc kiểm tra phải xét đúng nghiệp vụ và cả ba nhóm.

### Rỗng ở tầng dữ liệu và rỗng sau khi lọc

Giả sử hệ thống đọc danh sách người đăng ký từ cơ sở dữ liệu:

~~~text
Nguồn ban đầu:
["lan@example.test", " ", null, "minh@example.test"]

Sau khi loại bỏ mục trống:
["lan@example.test", "minh@example.test"]
~~~

Nếu quy tắc là **loại bỏ các mục trống** và tiếp tục gửi tới các địa chỉ hợp lệ, danh sách vẫn có người nhận. Nhưng nếu hệ thống xử lý **thông báo tài chính hoặc phê duyệt bắt buộc**, việc bỏ im lặng một địa chỉ có thể là lỗi nghiệp vụ nghiêm trọng. Khi đó nên **từ chối toàn bộ yêu cầu và trả lỗi rõ ràng** thay vì âm thầm loại bỏ.

Không có một chính sách dùng được cho mọi loại email. Cần quyết định từ trước:

1. **Danh sách rỗng có được phép không?** Có thể không gửi nếu không có subscriber nào trong một tác vụ định kỳ, nhưng một API “gửi hóa đơn cho khách hàng X” thường phải báo lỗi.
2. **Một mục rỗng làm hỏng toàn bộ request hay được bỏ qua?** Điều này phụ thuộc mức độ quan trọng và nguồn dữ liệu.
3. **Có yêu cầu phải có To hay chỉ cần To/Cc/Bcc tổng cộng không?** Với thư chỉ gửi Bcc, nhiều hệ thống không yêu cầu To.
4. **Nếu sau lọc không còn người nhận thì kết quả là gì?** “Bỏ qua vì không có mục tiêu” và “gửi thành công” không phải cùng một trạng thái.

### Không có To vẫn có thể có người nhận

Ví dụ minh họa:

~~~text
To:  []
Cc:  []
Bcc: ["audit@example.test"]
~~~

Đây là một yêu cầu gửi có người nhận hợp lệ. Tùy thư viện và hạ tầng, email có thể được vận chuyển với Bcc là envelope recipient. Một số hệ thống hiển thị nhãn kiểu **undisclosed recipients** khi không có To; nhãn hiển thị đó không phải danh sách đích SMTP.

Ngược lại:

~~~text
To:  []
Cc:  []
Bcc: []
~~~

Nếu không có danh sách envelope recipient riêng, ứng dụng **không có đích giao thư**. Hãy phát hiện tình huống này **trước khi gọi JavaMailSender.send(...)**, thay vì phụ thuộc vào dạng exception cụ thể mà phiên bản thư viện hoặc SMTP transport có thể phát sinh.

### Thứ tự kiểm tra giúp thông báo lỗi rõ hơn

Một luồng xử lý có thể được biểu diễn:

~~~text
Nhận yêu cầu gửi thư
      |
      v
Có dữ liệu danh sách? ---- Không ---> Lỗi thiếu người nhận
      |
      Có
      v
Chuẩn hóa đầu vào theo chính sách
      |
      v
Có mục rỗng/cú pháp lỗi? ---- Có ---> Từ chối hoặc ghi nhận lỗi từng mục
      |
      Không
      v
Xử lý trùng To / Cc / Bcc
      |
      v
Còn ít nhất một người nhận? ---- Không ---> Bỏ qua có lý do hoặc trả lỗi
      |
      Có
      v
Tạo thông điệp và gửi
~~~

Nếu đầu vào có **người nhận nhưng địa chỉ sai**, nên báo lỗi **địa chỉ không hợp lệ** thay vì diễn giải thành **danh sách rỗng**. Thông tin đó giúp phía gọi sửa lỗi đúng chỗ.

## 3. Địa chỉ trùng: trùng chuỗi, trùng mailbox và trùng đích phát

Địa chỉ trùng có nhiều cấp độ:

| Loại trùng | Ví dụ | Lưu ý |
| --- | --- | --- |
| Trùng tuyệt đối | **lan@example.test** xuất hiện hai lần | Có thể phát hiện bằng so sánh chuỗi |
| Trùng sau khi bỏ khoảng trắng quanh đầu vào | **" lan@example.test "** và **"lan@example.test"** | Có thể chuẩn hóa tại ranh giới nhận dữ liệu |
| Khác chữ hoa/thường của domain | **Lan@Example.Test** và **Lan@example.test** | Phần domain không phân biệt hoa/thường |
| Khác chữ hoa/thường của local-part | **Lan@example.test** và **lan@example.test** | Không nên mặc định chúng là cùng mailbox trong mọi hệ thống |
| Khác cách viết nhưng cùng alias | **team@example.test** và **member@example.test** | Ứng dụng thường không biết alias đích thực |
| Thay đổi dấu chấm hoặc phần sau dấu cộng | **name+promo@...**, **name@...** | Không thể áp dụng quy tắc của một nhà cung cấp cho mọi domain |
| Trùng giữa nhóm | **lan@example.test** ở cả To và Bcc | Phát sinh xung đột quyền hiển thị, cần chính sách rõ ràng |

Một danh sách có hai chuỗi bằng nhau chắc chắn chứa **bản ghi trùng ở tầng dữ liệu**. Nhưng hai địa chỉ khác nhau có cùng hộp thư cuối cùng hay không là thông tin thuộc hệ thống mail/alias mà ứng dụng không nhất thiết xác định được.

### Không tùy tiện chuyển mọi địa chỉ về chữ thường

Trong địa chỉ email thông thường:

~~~text
local-part@domain
~~~

Phần **domain** không phân biệt chữ hoa/chữ thường. Phần **local-part** theo quy tắc SMTP truyền thống có thể có ý nghĩa phân biệt hoa/thường do mail server đích quyết định, dù nhiều nhà cung cấp phổ biến xử lý không phân biệt. Vì vậy, nếu muốn một khóa loại trùng mang tính kỹ thuật an toàn, có thể **giữ nguyên local-part, chỉ chuẩn hóa hoa/thường của domain**.

Đừng tự động bỏ dấu chấm, dấu cộng và phần mở rộng như **+news** trong local-part. Một số dịch vụ có quy tắc alias như vậy, nhưng chúng không phải quy tắc chung cho mọi địa chỉ email. Tự gộp sai có thể khiến một người nhận hợp lệ bị bỏ qua.

Đối với sản phẩm có cơ chế xác minh email theo tài khoản nội bộ, ứng dụng có thể có **quy tắc đồng nhất riêng đã được công bố**. Quy tắc đó phải được dùng nhất quán tại ranh giới tài khoản và quá trình gửi; không nên tùy tiện suy đoán từ hình thức địa chỉ.

### Trùng trong cùng một nhóm

Ví dụ:

~~~text
To:
  - lan@example.test
  - minh@example.test
  - lan@example.test
~~~

Nếu hai mục thực sự cùng một mailbox theo chính sách được chọn, thường chỉ cần một recipient cho cùng một **thông điệp**. Việc xuất hiện hai lần trong danh sách có thể dẫn đến trùng lệnh recipient, hành vi gộp ở máy chủ hoặc các kết quả khác tùy mail transport. Không nên trông chờ SMTP luôn tự xử lý trường hợp này theo cách ứng dụng mong muốn.

Có hai cách phổ biến:

- **Từ chối đầu vào trùng** với thông báo rõ mục nào bị lặp, phù hợp API yêu cầu dữ liệu chính xác.
- **Loại trùng có kiểm soát** và ghi lại số mục được loại, phù hợp một số luồng nhập dữ liệu/batch mà việc lặp không mang ý nghĩa nghiệp vụ.

Nếu loại trùng, nên **giữ thứ tự xuất hiện đầu tiên** để dữ liệu dễ giải thích và truy vết. Không nhất thiết sắp xếp lại toàn bộ danh sách chỉ vì dùng một cấu trúc tập hợp.

### Trùng giữa To, Cc và Bcc nguy hiểm hơn

Xét:

~~~text
To:  ["lan@example.test"]
Cc:  []
Bcc: ["lan@example.test"]
~~~

Cùng một địa chỉ xuất hiện trong nhóm công khai và nhóm ẩn. Việc đơn giản dùng một tập hợp chung sẽ làm **mất thông tin nhóm gốc**: nếu giữ bản ở To thì đối tượng xuất hiện công khai; nếu giữ bản ở Bcc thì có thể thay đổi ngữ nghĩa của yêu cầu.

Với hệ thống nghiêm túc, nên thiết kế **quy tắc giải quyết xung đột giữa các nhóm**. Chẳng hạn:

1. **Từ chối khi cùng mailbox xuất hiện ở nhiều nhóm**, yêu cầu bên gọi quyết định phân loại. Đây là lựa chọn dễ dự đoán và thận trọng với Bcc.
2. Hoặc **áp dụng thứ tự ưu tiên được thống nhất từ trước**, ví dụ quy tắc gửi thông báo tổ chức xác định To ưu tiên trước Cc và Bcc. Cần hiểu rõ hệ quả hiển thị và ghi lại quyết định.
3. Với yêu cầu bảo mật riêng tư cao, **tạo thông điệp riêng cho từng người nhận** thay vì cố gộp nhiều đối tượng vào một MIME message.

Không nên “sửa trùng” bằng cách chuyển mọi recipient thành **To**, vì làm vậy có thể tiết lộ người nhận vốn được chỉ định là Bcc.

### Một địa chỉ có thể xuất hiện trong nhiều công việc gửi khác nhau

Việc loại trùng **trong danh sách của một thông điệp** không tự ngăn việc gửi nhiều thông điệp tới cùng người. Ví dụ, một người có thể nằm trong hai nhóm đăng ký khác nhau; hai sự kiện nghiệp vụ tạo ra hai mail jobs giống nhau. Khi retry, worker cũng có thể gửi lại email nếu trạng thái của lần gửi trước không xác định.

Để giảm phát sinh thư trùng do cùng một sự kiện, cần khóa nghiệp vụ hoặc **idempotency key** cho công việc gửi, tách khỏi việc kiểm tra trùng địa chỉ. Ngay cả cơ chế idempotency ở ứng dụng cũng không thể luôn bảo đảm **exactly-once email delivery** nếu provider đã nhận thư nhưng phản hồi bị mất.

## 4. “Không hợp lệ” có ít nhất bốn nghĩa

Một địa chỉ có thể vượt qua một lớp kiểm tra và thất bại ở lớp sau:

| Lớp kiểm tra | Câu hỏi | Ví dụ vấn đề |
| --- | --- | --- |
| **Hình dạng dữ liệu** | Có chuỗi đơn, không null, không chỉ toàn khoảng trắng không? | **null**, **""**, **"   "** |
| **Cú pháp email** | Chuỗi có tuân theo dạng mailbox được hệ thống chấp nhận không? | **user@**, **@example.test**, dấu ngoặc hoặc ký tự sai vị trí |
| **Chính sách ứng dụng** | Địa chỉ có được phép nhận loại thư này không? | Người dùng chưa đồng ý nhận marketing, domain bị cấm theo quy định nội bộ |
| **Khả năng phát thực tế** | Mail server và mailbox có thể nhận thư ở thời điểm gửi không? | Mailbox không tồn tại, domain không nhận mail, quota hoặc policy từ chối |

Kiểm tra cú pháp trong Java chỉ cho biết dữ liệu **có vẻ hợp lệ theo quy tắc parser**. Nó không bảo đảm DNS đúng, mailbox tồn tại, người dùng sở hữu địa chỉ hay thư sẽ đến Inbox.

### Các giá trị điển hình cần xem xét

| Dữ liệu đầu vào | Nhận định |
| --- | --- |
| **lan@example.test** | Hình thức mailbox thông thường hợp lệ |
| **" lan@example.test "** | Có khoảng trắng ngoài; có thể strip ở ranh giới nhập liệu |
| **""** hoặc **null** | Không có địa chỉ |
| **lan@** | Thiếu phần domain |
| **@example.test** | Thiếu local-part |
| **lan@@example.test** | Cú pháp không phù hợp mailbox thông thường |
| **Lan Nguyen <lan@example.test>** | Là dạng mailbox có display name theo cú pháp email; có thể được parser chấp nhận, nhưng API yêu cầu chuỗi địa chỉ thuần có thể chủ động từ chối |
| **lan+course@example.test** | Ký tự **+** ở local-part không tự làm địa chỉ sai |
| **a.b@example.test** | Dấu chấm trong local-part thông thường là hợp lệ |
| **"a b"@example.test** | Một trường hợp cú pháp local-part được đặt trong dấu nháy; validator quá đơn giản có thể từ chối dù chuẩn hỗ trợ |
| **lan@example.test, minh@example.test** | Có thể là *danh sách* trong một chuỗi khi parser được gọi để đọc list; không phải một mailbox đơn nếu API quy định mỗi phần tử một địa chỉ |

Tên miền **.test** trong các ví dụ chỉ phục vụ minh họa, không phải miền gửi/nhận thư thật. Danh sách trên cũng không phải bộ quy tắc cú pháp đầy đủ của RFC; nhiều địa chỉ hợp chuẩn có cách viết không phổ biến.

### Tránh regex quá đơn giản để phán xét mọi địa chỉ

Một regex kiểu:

~~~regex
^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+$
~~~

có thể bỏ sót nhiều địa chỉ hợp lệ (ví dụ local-part chứa **+**), trong khi vẫn chưa phát hiện hết trường hợp sai (như một số vị trí dấu chấm hoặc nhãn domain không hợp lệ). Việc “có một dấu @ và một dấu chấm” không đủ để xác nhận cú pháp.

Nếu dùng hệ sinh thái Spring Mail/Jakarta Mail, có thể sử dụng lớp **InternetAddress** để phân tích và kiểm tra cú pháp. Sau đó vẫn cần một **chính sách đầu vào** của sản phẩm, ví dụ chỉ cho phép mỗi phần tử là một mailbox thuần, không nhận group hay danh sách nhiều mailbox trong một chuỗi.

### InternetAddress không xác minh hộp thư tồn tại

Ví dụ kiểm tra cú pháp:

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;

public final class MailboxParser {
    private MailboxParser() {
    }

    public static InternetAddress parseOne(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("Thiếu địa chỉ người nhận");
        }

        String value = input.strip();
        if (value.indexOf('\r') >= 0 || value.indexOf('\n') >= 0) {
            throw new IllegalArgumentException("Địa chỉ chứa xuống dòng");
        }

        try {
            InternetAddress mailbox = new InternetAddress(value, true);
            mailbox.validate();
            if (mailbox.isGroup() || !value.equals(mailbox.getAddress())) {
                throw new IllegalArgumentException(
                        "Mỗi phần tử phải là một mailbox thuần"
                );
            }
            return mailbox;
        } catch (AddressException ex) {
            throw new IllegalArgumentException(
                    "Cú pháp địa chỉ người nhận không hợp lệ", ex
            );
        }
    }
}
~~~

Đoạn trên minh họa **một chính sách cụ thể**: nhận một mailbox thuần cho mỗi phần tử, loại bỏ khoảng trắng ở hai đầu, từ chối xuống dòng, không chấp nhận group hay display name do người dùng đưa vào. Đây không phải bộ phân tích đầy đủ mọi địa chỉ RFC dành cho mọi sản phẩm; quy định ứng dụng có thể rộng hoặc hẹp hơn.

Việc gọi **validate()** không kiểm tra domain có MX record, mailbox có thật hay SMTP server có chấp nhận nhận thư. Một địa chỉ vượt qua bước này vẫn có thể bị từ chối sau đó. Đừng tạo tính năng “xác minh email tồn tại” chỉ bằng cách gọi InternetAddress.validate().

### Địa chỉ quốc tế và SMTPUTF8

Địa chỉ chứa ký tự Unicode ở local-part hoặc domain cần được xử lý theo khả năng hỗ trợ thực tế của parser, ứng dụng, SMTP server và các phần mở rộng liên quan như **SMTPUTF8**. Đối với tên miền quốc tế, có thể cần biểu diễn IDN phù hợp khi chuyển tải và kiểm tra.

Không nên tự đổi toàn bộ địa chỉ Unicode sang ASCII hay chỉ dùng một regex ASCII rồi kết luận tất cả địa chỉ quốc tế là sai. Ngược lại, chấp nhận một chuỗi Unicode ở tầng API cũng **không bảo đảm tuyến SMTP hỗ trợ gửi tới địa chỉ đó**. Chính sách sản phẩm phải đi kèm giới hạn hạ tầng cụ thể.

## 5. Dữ liệu người nhận là đầu vào không đáng tin cậy

Một email address có thể đến từ biểu mẫu, file import, token hay dữ liệu hệ thống khác. Tại ranh giới ứng dụng, cần tránh để đầu vào làm thay đổi cấu trúc header hoặc gây thất thoát dữ liệu.

### Chú ý nguy cơ header injection

Một chuỗi chứa ký tự xuống dòng:

~~~text
lan@example.test
Bcc: attacker@example.test
~~~

không được coi là một mailbox bình thường. Khi ứng dụng tự nối chuỗi raw email header, ký tự **CR/LF** trong đầu vào có thể tạo ra header ngoài ý muốn. Các API như **MimeMessageHelper** và **InternetAddress** giúp quản lý cấu trúc MIME, nhưng ứng dụng vẫn nên xác định ranh giới đầu vào rõ ràng, từ chối ký tự điều khiển không phù hợp và **không tự nối raw header từ dữ liệu chưa kiểm soát**.

Đừng “sửa” địa chỉ bằng cách xóa mọi ký tự lạ cho đến khi parser chấp nhận, vì hành động đó có thể biến dữ liệu sai thành **một mailbox khác**. Với lỗi cú pháp, thường nên báo cụ thể cho người tạo dữ liệu chỉnh lại.

### Địa chỉ hợp cú pháp chưa chắc được phép nhận

Ví dụ một nền tảng có hai luồng:

- **Transactional mail**: mã xác minh, thông tin hóa đơn, cập nhật quan trọng của tài khoản.
- **Marketing mail**: bản tin, thông báo ưu đãi.

Cùng một mailbox có thể hợp lệ với một loại thông điệp nhưng không phù hợp với loại còn lại vì lựa chọn nhận thư, quy định đồng ý hoặc trạng thái unsubscribe. **Parser không thể thay thế việc kiểm tra mục đích và quyền gửi**.

Hệ thống cũng nên áp dụng giới hạn số recipient mỗi request, giới hạn tốc độ và phân quyền tài khoản gọi API. Nếu một người dùng được phép nhập danh sách bất kỳ mà không có hạn mức, việc gửi thư hàng loạt có thể gây lạm dụng tài nguyên và tổn hại danh tiếng miền gửi.

## 6. Xây dựng một chính sách kiểm tra chung cho To, Cc và Bcc

Để tránh mỗi chức năng gửi email lại xử lý địa chỉ theo một cách, ứng dụng có thể tập trung quy tắc kiểm tra tại ranh giới trước khi tạo **MimeMessage**. Chọn một chính sách minh họa như sau:

1. **null** ở cấp danh sách tương đương danh sách rỗng; **null** hoặc chuỗi trắng ở cấp phần tử là lỗi.
2. Mỗi phần tử phải là **một mailbox thuần**. Không nhận chuỗi nhiều địa chỉ ngăn bằng dấu phẩy trong cùng một phần tử.
3. Dùng **InternetAddress** để phân tích cú pháp; giới hạn số người nhận theo yêu cầu vận hành.
4. Phát hiện trùng giữa **cả To, Cc và Bcc**. Trùng sẽ bị từ chối để bên gọi tự quyết định nhóm đúng; không tự đổi Bcc thành To.
5. Nếu cả ba nhóm không có mailbox nào, trả lỗi **không có người nhận**.
6. Bảo toàn thứ tự và cách viết địa chỉ đã được chấp nhận khi đưa vào thông điệp.

Ví dụ Java 21 sau dùng **MailboxParser.parseOne(...)** đã định nghĩa ở phần trước:

~~~java
import jakarta.mail.internet.InternetAddress;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public final class RecipientPolicy {

    private static final int MAX_RECIPIENTS = 100; // Ví dụ giới hạn nghiệp vụ

    private RecipientPolicy() {
    }

    public record RecipientSet(
            List<InternetAddress> to,
            List<InternetAddress> cc,
            List<InternetAddress> bcc
    ) {
        public int total() {
            return to.size() + cc.size() + bcc.size();
        }
    }

    public static RecipientSet check(
            List<String> to,
            List<String> cc,
            List<String> bcc
    ) {
        Set<String> seen = new HashSet<>();

        List<InternetAddress> checkedTo = checkGroup(to, "To", seen);
        List<InternetAddress> checkedCc = checkGroup(cc, "Cc", seen);
        List<InternetAddress> checkedBcc = checkGroup(bcc, "Bcc", seen);

        RecipientSet result = new RecipientSet(
                List.copyOf(checkedTo),
                List.copyOf(checkedCc),
                List.copyOf(checkedBcc)
        );

        if (result.total() == 0) {
            throw new IllegalArgumentException(
                    "Không có người nhận trong To/Cc/Bcc"
            );
        }

        return result;
    }

    private static List<InternetAddress> checkGroup(
            List<String> input,
            String group,
            Set<String> seen
    ) {
        List<InternetAddress> checked = new ArrayList<>();
        if (input == null) {
            return checked;
        }

        for (int index = 0; index < input.size(); index++) {
            InternetAddress address = MailboxParser.parseOne(
                    input.get(index)
            );
            String key = duplicateKey(address.getAddress());

            if (!seen.add(key)) {
                throw new IllegalArgumentException(
                        "Người nhận bị trùng tại " + group
                        + "[" + index + "]"
                );
            }

            checked.add(address);
            if (seen.size() > MAX_RECIPIENTS) {
                throw new IllegalArgumentException(
                        "Vượt quá số người nhận cho phép"
                );
            }
        }
        return checked;
    }

    private static String duplicateKey(String mailbox) {
        int at = mailbox.lastIndexOf('@');
        if (at <= 0 || at == mailbox.length() - 1) {
            throw new IllegalArgumentException(
                    "Địa chỉ phải có local-part và domain"
            );
        }
        // Bảo toàn local-part. Chỉ đưa domain về chữ thường.
        return mailbox.substring(0, at)
                + "@"
                + mailbox.substring(at + 1).toLowerCase(Locale.ROOT);
    }
}
~~~

Đây là **một triển khai chính sách đầu vào được lựa chọn**, không phải khẳng định mọi địa chỉ hợp chuẩn đều phải được xử lý như vậy. Việc chuẩn hóa domain trong ví dụ dành cho tình huống thông thường; các hệ thống hỗ trợ địa chỉ quốc tế có thể cần bước xử lý IDN theo quy tắc thống nhất của mình. Cách phân tách tại dấu **@** cuối cùng cũng được dùng sau bước parser và chính sách chỉ nhận mailbox thuần.

### Vì sao dùng chung một tập seen?

Nếu tạo ba tập riêng cho To, Cc và Bcc, ta chỉ phát hiện trùng **trong từng nhóm** mà bỏ sót trường hợp cùng địa chỉ vừa ở To vừa ở Bcc. Dùng **một tập seen cho cả ba nhóm** giúp nhận diện xung đột trước khi tạo message.

**HashSet** ở ví dụ chỉ lưu khóa để kiểm tra trùng; các **ArrayList** riêng của từng nhóm bảo toàn thứ tự đầu vào. Vì ví dụ **báo lỗi khi trùng** nên không có thao tác loại trùng làm mất thông tin phân loại. Nếu muốn loại trùng thay vì từ chối, phải thay đổi chính sách rõ ràng, đặc biệt đối với Bcc.

Nếu hệ thống cần chỉ ra **cả hai vị trí** của địa chỉ trùng, có thể dùng một cấu trúc ánh xạ từ khóa địa chỉ tới vị trí xuất hiện đầu tiên; khi thấy vị trí thứ hai, trả về mã lỗi cùng đường dẫn hai trường. Không nên ghi toàn bộ địa chỉ người dùng vào log hoặc thông báo lỗi công khai nếu chúng chứa dữ liệu cá nhân.

### Giới hạn số địa chỉ nên đặt ở đâu?

Giới hạn nên được kiểm tra ở **phía server** trước khi gọi SMTP, ngay cả khi giao diện đã giới hạn số phần tử. Mức giới hạn là quyết định nghiệp vụ/hạ tầng và có thể khác giữa:

- Email giao dịch một người nhận.
- Email cảnh báo một nhóm quản trị nhỏ.
- Email gửi theo lô qua queue và worker.
- Email gửi cá nhân hóa cho từng subscriber.

Ví dụ **100** trong mã là giá trị minh họa, không phải giới hạn mặc định của Spring Mail hay SMTP. Provider có thể áp dụng giới hạn riêng theo tài khoản, thông điệp, ngày hoặc loại sản phẩm.

## 7. Dùng dữ liệu đã kiểm tra để gửi bằng MimeMessage

Sau khi đã có danh sách kiểm tra thành công, ứng dụng đưa chúng vào **MimeMessage**:

~~~java
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;
import java.util.List;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailService {

    private final JavaMailSender mailSender;

    public NotificationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNotification(
            List<String> to,
            List<String> cc,
            List<String> bcc
    ) throws MessagingException {

        RecipientPolicy.RecipientSet recipients =
                RecipientPolicy.check(to, cc, bcc);

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, "UTF-8");

        helper.setFrom("notifications@example.test");
        helper.setSubject("Thông báo mới");
        helper.setText("Bạn có một thông báo mới.", false);

        if (!recipients.to().isEmpty()) {
            message.setRecipients(
                    Message.RecipientType.TO,
                    recipients.to().toArray(InternetAddress[]::new)
            );
        }
        if (!recipients.cc().isEmpty()) {
            message.setRecipients(
                    Message.RecipientType.CC,
                    recipients.cc().toArray(InternetAddress[]::new)
            );
        }
        if (!recipients.bcc().isEmpty()) {
            message.setRecipients(
                    Message.RecipientType.BCC,
                    recipients.bcc().toArray(InternetAddress[]::new)
            );
        }

        mailSender.send(message);
    }
}
~~~

Đoạn mã này minh họa tách **kiểm tra đầu vào** khỏi **thao tác gửi**:

- **RecipientPolicy.check(...)** thực hiện quy tắc rỗng, cú pháp và trùng lặp trước khi tạo thư.
- **message.setRecipients(...)** đặt từng nhóm vào trường MIME recipient tương ứng.
- Khi **To** rỗng nhưng **Bcc** có địa chỉ, mã vẫn có thể tạo message với Bcc làm người nhận.
- Không gọi **send(...)** khi cả ba nhóm đều trống.
- **MailException** tại thời điểm gửi và **MessagingException** khi tạo message là các trường hợp lỗi ở những tầng khác nhau; chương trình gọi dịch vụ cần xử lý phù hợp.

Ứng dụng thực tế còn cần cấu hình SMTP, địa chỉ From được phép sử dụng, xử lý lỗi và chính sách giám sát. Các địa chỉ **example.test** là dữ liệu ví dụ.

### Dùng SimpleMailMessage với văn bản thuần

**SimpleMailMessage** cũng có **setTo(...)**, **setCc(...)** và **setBcc(...)**. Khi gửi một email đơn giản, có thể áp dụng chính sách kiểm tra trước rồi chuyển các **InternetAddress** đã duyệt thành chuỗi mailbox:

~~~java
import org.springframework.mail.SimpleMailMessage;

RecipientPolicy.RecipientSet recipients =
        RecipientPolicy.check(to, cc, bcc);

SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("notifications@example.test");
mail.setSubject("Thông báo");
mail.setText("Nội dung thông báo.");

mail.setTo(
        recipients.to().stream()
                .map(InternetAddress::getAddress)
                .toArray(String[]::new)
);
mail.setCc(
        recipients.cc().stream()
                .map(InternetAddress::getAddress)
                .toArray(String[]::new)
);
mail.setBcc(
        recipients.bcc().stream()
                .map(InternetAddress::getAddress)
                .toArray(String[]::new)
);

mailSender.send(mail);
~~~

Trong ví dụ, **SimpleMailMessage** phù hợp với văn bản thuần. Khi cần MIME phức tạp (HTML, ảnh, tệp đính kèm, charset và multipart), **MimeMessageHelper** là công cụ phù hợp hơn. Dù dùng API nào, việc **ngăn danh sách người nhận sai trước khi gửi** vẫn là trách nhiệm của ứng dụng.

### Tại sao không chỉ gọi helper.setTo(rawList) rồi để thư viện kiểm tra?

Thư viện mail xử lý cú pháp và tạo thông điệp, nhưng không biết các quy tắc nghiệp vụ như:

- Phải có ít nhất một người nhận thuộc To/Cc/Bcc.
- Mỗi email chỉ được gửi tối đa N recipient.
- Không cho cùng một mailbox xuất hiện ở To và Bcc.
- Chỉ gửi tới người dùng đã xác minh, chưa unsubscribe hoặc có đúng quyền nhận.
- Một người cần nhận **một thông điệp cá nhân hóa** thay vì một bản email chung.

Nếu phát hiện lỗi từ sớm, API có thể trả một thông báo có cấu trúc như **RECIPIENT_LIST_EMPTY**, **INVALID_RECIPIENT** hoặc **DUPLICATE_RECIPIENT** mà không phải phân tích lỗi từ SMTP hay message transport.

## 8. Dùng Bean Validation đúng phạm vi

Trong các API Spring MVC, Bean Validation có thể giúp kiểm tra một phần hình dạng dữ liệu:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import java.util.List;

public record SendMailRequest(
        List<@NotBlank @Email String> to,
        List<@NotBlank @Email String> cc,
        List<@NotBlank @Email String> bcc
) {
}
~~~

Nếu controller kích hoạt validation phù hợp, các ràng buộc **@NotBlank** và **@Email** trên từng phần tử có thể phát hiện giá trị trống hoặc không phù hợp cách kiểm tra của validator. Tuy nhiên:

- **@Email** không kiểm tra mailbox thực sự tồn tại.
- **@Email** không tự loại trùng trong một danh sách.
- **@Email** không phát hiện xung đột giữa To, Cc và Bcc.
- Trong trường hợp các danh sách đều trống, không có phần tử nào vi phạm ràng buộc đặt **trên phần tử**.
- **@Email** của Bean Validation là một validator ứng dụng, không thay thế hoàn toàn parser RFC hoặc khả năng của SMTP transport.

Nếu bài toán cho phép **Bcc-only**, không nên đặt **@NotEmpty** bắt buộc trên trường **to** rồi vô tình từ chối một request hợp lệ. Quy tắc “ít nhất một địa chỉ trong To/Cc/Bcc” cần ràng buộc **liên trường**, ví dụ trong một validator hoặc service policy.

Đối với API dùng danh sách nhiều địa chỉ, cách đặt dữ liệu thành **mảng các mailbox riêng lẻ** giúp lỗi được chỉ rõ theo chỉ số:

~~~json
{
  "to": [
    "lan@example.test",
    "minh@example.test"
  ],
  "cc": [],
  "bcc": [
    "audit@example.test"
  ]
}
~~~

Cách này cũng làm rõ rằng ký tự dấu phẩy trong một phần tử không mặc nhiên có nghĩa là hai recipient. Nếu sản phẩm chủ động hỗ trợ trường nhập nhiều địa chỉ dạng CSV, việc tách CSV phải là bước xử lý riêng theo parser phù hợp, có xem xét dấu nháy và display names, chứ không nên chỉ **split(",")** tùy tiện.

## 9. Địa chỉ đúng cú pháp vẫn có thể bị SMTP từ chối

Sau khi kiểm tra đầu vào, thao tác gửi vẫn có thể gặp lỗi tại máy chủ SMTP. Ví dụ:

~~~text
C: MAIL FROM:<notifications@example.test>
S: 250 Sender OK
C: RCPT TO:<lan@example.test>
S: 250 Recipient OK
C: RCPT TO:<unknown@recipient.test>
S: 550 5.1.1 User unknown
~~~

Đây là phiên minh họa, không phải transcript bắt buộc của mọi SMTP server. Nó cho thấy server có thể chấp nhận một recipient và từ chối recipient khác.

Các tình huống khác:

| Hiện tượng | Cách hiểu thận trọng |
| --- | --- |
| Parser chấp nhận địa chỉ | Cú pháp phù hợp phạm vi kiểm tra của parser |
| SMTP trả lỗi **5xx** cho RCPT TO | Lỗi ở bước nhận recipient được báo là vĩnh viễn trong ngữ cảnh phản hồi đó; mã chi tiết chỉ nguyên nhân |
| SMTP trả lỗi **4xx** cho RCPT TO | Lỗi/từ chối tạm thời; có thể cân nhắc retry theo chính sách |
| SMTP chấp nhận RCPT TO | Chỉ mới chấp nhận địa chỉ ở bước giao thức tương ứng |
| SMTP chấp nhận toàn bộ nội dung DATA | Máy chủ đã tiếp nhận thông điệp ở giai đoạn đó, chưa bảo đảm phát đến Inbox |
| Provider báo bounce về sau | Cần cập nhật trạng thái người nhận/công việc từ dữ liệu provider hoặc DSN |

Mã **550** không phải lúc nào cũng có nghĩa “mailbox không tồn tại”; có thể liên quan chính sách từ chối khác. Nên diễn giải cùng thông tin status bổ sung và nội dung phản hồi đáng tin cậy, đồng thời tránh hiển thị nguyên thông báo của provider cho người dùng.

### Có thể gửi thành công một phần?

Với nhiều recipient trong một thông điệp, kết quả có thể **không đồng nhất theo từng địa chỉ**. Cách SMTP transport xử lý khi một phần địa chỉ bị từ chối phụ thuộc cấu hình và hành vi máy chủ; có môi trường gửi tới một số địa chỉ rồi báo lỗi, có môi trường dừng cả thông điệp.

Trong Jakarta Mail có các dạng thông tin lỗi liên quan đến **SendFailedException** và phân loại **invalid**, **valid sent**, **valid unsent** recipients, nếu transport cung cấp được. Spring có thể chuyển lỗi tầng mail thành các ngoại lệ thuộc họ **MailException**, chẳng hạn **MailSendException**, với nguyên nhân bên dưới.

Ứng dụng không nên suy ra rằng **một exception nghĩa là không ai nhận được thư**, hoặc rằng **không có exception nghĩa là mọi hộp thư đích đã nhận thư**. Khi gửi cho nhiều người, hãy lưu trạng thái ở mức đủ chi tiết và theo bằng chứng thực sự nhận được từ provider.

### Cẩn thận khi retry danh sách recipient

Giả sử gửi tới Lan và Minh. SMTP đã nhận thư cho Lan, nhưng phía ứng dụng gặp lỗi trước khi biết kết quả của Minh. Nếu retry ngay toàn bộ danh sách mà không xem xét trạng thái, Lan có thể nhận hai thư.

Ngược lại, nếu đánh dấu cả batch là thành công chỉ vì có một recipient được chấp nhận, Minh có thể không bao giờ nhận được thông điệp.

Đối với luồng đòi hỏi kiểm soát tốt:

- Lưu **mail job ID**, loại thông điệp và danh sách recipient đã chọn.
- Phân biệt trạng thái **PENDING**, **SUBMITTED**, **TEMPORARY_FAILURE**, **PERMANENT_FAILURE** hoặc trạng thái cụ thể theo provider.
- Chỉ đánh dấu **DELIVERED** khi có bằng chứng phân phối thích hợp, không chỉ vì **send(...)** trả về.
- Thiết kế retry có giới hạn, backoff và cân nhắc rủi ro gửi trùng.
- Khi mỗi recipient cần nội dung hoặc trạng thái riêng, có thể gửi một message/job riêng cho từng người.

Đây là quyết định về độ tin cậy và ngữ nghĩa gửi của ứng dụng, không phải tính năng tự động của một hàm **setTo(...)**.

## 10. Danh sách nhập từ cơ sở dữ liệu và batch gửi hàng loạt

Giả sử một chiến dịch gửi thông báo có các bản ghi:

~~~text
Subscriber 101 -> lan@example.test
Subscriber 102 -> minh@example.test
Subscriber 103 -> lan@example.test
Subscriber 104 -> (email rỗng)
Subscriber 105 -> sai@@example.test
~~~

Nếu việc gửi đại diện cho **mỗi tài khoản subscriber**, các bản ghi 101 và 103 là hai **tài khoản** khác nhau nhưng lại chứa cùng một mailbox. Gộp theo địa chỉ có thể làm mất ngữ nghĩa “mỗi tài khoản một thông báo”, đặc biệt khi nội dung chứa mã riêng hoặc liên kết xác minh riêng. Ngược lại, nếu mục tiêu là “một bản tin công khai cho mỗi mailbox đăng ký”, loại trùng theo địa chỉ có thể phù hợp.

Do đó cần xác định **đơn vị nhận thư**:

- **Mailbox**: một thư được gửi cho một địa chỉ theo chính sách đồng nhất.
- **Tài khoản**: một thư riêng cho từng user, dù email liên hệ trùng.
- **Sự kiện nghiệp vụ**: một thư cho mỗi sự kiện, có thể gửi nhiều thư tới cùng mailbox ở thời điểm khác nhau.
- **Nhóm phân phối**: một thư gửi tới địa chỉ group; nhóm có thể mở rộng thành nhiều mailbox ngoài tầm kiểm soát trực tiếp của ứng dụng.

Việc chọn khóa loại trùng nên xuất phát từ đơn vị nghiệp vụ, không phải phản xạ “thấy hai email giống nhau thì xóa một”.

### Hai chính sách xử lý dữ liệu lỗi trong batch

**Chính sách nguyên khối (all-or-nothing):** nếu bất kỳ recipient bắt buộc nào rỗng, trùng sai chính sách hoặc không hợp lệ, từ chối cả batch trước khi nộp thư. Cách này phù hợp với một giao dịch cần danh sách người nhận chính xác, ví dụ thông báo bắt buộc cho các bên phê duyệt.

**Chính sách từng bản ghi (per-recipient):** phân loại đầu vào trước, đưa recipient hợp lệ vào danh sách gửi, còn bản ghi không hợp lệ vào báo cáo riêng; cần báo cáo rõ số thành công, số không được gửi và lý do. Cách này có thể phù hợp với danh sách subscription lớn, nhưng không được tự động loại bỏ người nhận bắt buộc của một nghiệp vụ quan trọng.

Một mô hình kết quả cho batch:

~~~text
Batch validation:
    received_count = 5
    accepted_count = 2
    duplicate_count = 1
    empty_count = 1
    malformed_count = 1

Batch sending:
    submitted_count = ...
    failed_count = ...
    pending_retry_count = ...
~~~

Các chỉ số **validation** và **sending** là hai thời điểm khác nhau. **accepted_count = 2** nghĩa là hai người nhận vượt qua chính sách đầu vào, không có nghĩa hai thư đã được phát đến hộp thư.

### Gửi riêng từng người giúp kiểm soát trạng thái và riêng tư

Với các thư có tên, mã hoặc URL riêng, nên xây dựng **một message/job cho từng người nhận hoặc từng sự kiện**. Ví dụ, thư đặt lại mật khẩu của Lan không được dùng chung với Minh dưới dạng một message có nhiều To/Cc/Bcc.

Khi gửi riêng:

- Dễ ghi nhận trạng thái gửi theo người nhận.
- Dễ áp dụng quyền nhận nội dung riêng.
- Tránh lộ danh sách người nhận cho nhau.
- Có thể retry một người nhận mà không chủ động lặp lại toàn bộ batch.

Đổi lại, số công việc và số lần nộp thư tăng; cần quản lý giới hạn gửi, tốc độ và queue phù hợp. Không nên xem đó là lý do để gộp những nội dung đáng lẽ phải cá nhân hóa vào một thư chung.

## 11. Thiết kế phản hồi API rõ ràng

Một API gửi mail nên phân biệt **lỗi dữ liệu đầu vào** với **lỗi transport**. Ví dụ:

| Tình huống | Kết quả API gợi ý | Trạng thái nội bộ nên ghi nhận |
| --- | --- | --- |
| Cả To/Cc/Bcc rỗng nhưng nghiệp vụ bắt buộc có người nhận | Trả lỗi xác thực dữ liệu phía client, thường là **400 Bad Request** | **REJECTED_INPUT** |
| Địa chỉ có cú pháp sai | Trả lỗi tại vị trí phần tử với mã **INVALID_RECIPIENT** | **REJECTED_INPUT** |
| Người nhận trùng giữa To và Bcc theo chính sách cấm | Trả **DUPLICATE_RECIPIENT** hoặc **CONFLICTING_RECIPIENT_GROUP** | **REJECTED_INPUT** |
| Yêu cầu hợp lệ đã được lưu để xử lý nền | Có thể trả **202 Accepted** theo hợp đồng API | **PENDING** |
| SMTP submit thành công | Trả hoặc ghi trạng thái nộp thư thành công ở tầng ứng dụng | **SUBMITTED** |
| SMTP/provider gặp lỗi tạm thời | Ghi lỗi có thể retry và lịch thử lại | **RETRY_PENDING** |
| Provider báo không phát được | Ghi trạng thái lỗi phù hợp theo người nhận | **BOUNCED/FAILED** |

Các mã HTTP là gợi ý thiết kế, không phải ánh xạ bắt buộc của Spring Mail. Với API gửi mail đồng bộ, cách trả kết quả còn phụ thuộc contract và thời điểm nghiệp vụ được coi là hoàn thành. Nếu đã ghi nhận công việc gửi bền vững, **202 Accepted** mô tả việc yêu cầu được nhận xử lý, không cam kết người nhận đã đọc thư.

### Ví dụ lỗi đầu vào không làm lộ dữ liệu thừa

~~~json
{
  "code": "INVALID_RECIPIENT",
  "field": "to[2]",
  "message": "Địa chỉ người nhận không đúng định dạng."
}
~~~

Hoặc khi trùng giữa các nhóm:

~~~json
{
  "code": "CONFLICTING_RECIPIENT_GROUP",
  "fields": ["to[0]", "bcc[1]"],
  "message": "Một người nhận xuất hiện ở nhiều nhóm."
}
~~~

Trong hệ thống có dữ liệu riêng tư, việc trả **vị trí phần tử** thường đủ để client hiển thị lỗi đúng nơi mà không phải trả lại nguyên danh sách địa chỉ hoặc thông điệp lỗi dài từ provider.

### Đừng làm lệch kết quả nghiệp vụ khi email là tác vụ phụ

Ví dụ một yêu cầu “tạo đơn hàng và gửi email thông báo”. Nếu đơn hàng đã lưu thành công nhưng SMTP thất bại, việc API trả lỗi “không tạo được đơn hàng” có thể khiến người dùng thử tạo lại đơn. Nên tách **kết quả tạo đơn hàng** khỏi **trạng thái công việc gửi mail**, nhất là khi gửi thư được thực hiện nền.

Điều này cũng giúp xử lý danh sách người nhận rỗng:

- Nếu gửi email là **điều kiện bắt buộc của nghiệp vụ**, hệ thống có thể từ chối request trước khi commit.
- Nếu email là **thông báo tùy chọn**, hệ thống có thể hoàn thành nghiệp vụ chính và ghi “không có người nhận được cấu hình” trong trạng thái thông báo.

Cần đưa quyết định vào yêu cầu sản phẩm thay vì để ngoại lệ từ SMTP vô tình quyết định thành công/thất bại của thao tác chính.

## 12. Quan sát lỗi mà vẫn bảo vệ dữ liệu người nhận

Để phát hiện xu hướng lỗi, nên có chỉ số cho từng nhóm:

| Chỉ số hoặc sự kiện | Ý nghĩa |
| --- | --- |
| **recipient.validation.empty** | Bao nhiêu yêu cầu thiếu người nhận |
| **recipient.validation.invalid** | Bao nhiêu phần tử không vượt qua quy tắc cú pháp/chính sách |
| **recipient.validation.duplicate** | Bao nhiêu xung đột trùng được phát hiện |
| **mail.submitted** | Bao nhiêu message được submit thành công tới hạ tầng gửi |
| **mail.submit_failed** | Bao nhiêu lần nộp thư gặp lỗi |
| **mail.bounced** | Bao nhiêu sự kiện không phát được do provider thông báo |
| **mail.retry_pending** | Bao nhiêu công việc đang chờ thử lại |

Đây chỉ là ví dụ tên metric; có thể điều chỉnh theo hệ thống observability đang dùng. Khi ghi log, nên bao gồm **mailJobId**, loại email, mã lỗi chuẩn hóa, nhóm To/Cc/Bcc và vị trí lỗi. Với địa chỉ cụ thể, chỉ lưu nếu thực sự cần và tuân thủ chính sách xử lý dữ liệu cá nhân.

Một số nguyên tắc:

- Không ghi toàn bộ nội dung email và danh sách địa chỉ vào mọi dòng log.
- Tránh dùng địa chỉ email nguyên bản làm metric label vì có thể gây **cardinality cao** và lộ dữ liệu.
- Với danh sách Bcc, hạn chế việc hiển thị, log hoặc đưa vào thông báo lỗi cho người không có quyền truy cập.
- Nếu cần tương quan sự kiện provider, dùng **job ID**, **recipient ID** hoặc định danh được thiết kế riêng.
- Không xem lỗi cú pháp và bounce là cùng một nhóm: một lỗi được phát hiện **trước khi gửi**, lỗi còn lại thường xuất hiện **sau khi hệ thống tiếp nhận thư**.

## 13. Các tình huống thực hành

### Tình huống A — Chỉ có Bcc

~~~text
To  = []
Cc  = []
Bcc = ["audit@example.test"]
~~~

**Hỏi:** đây có phải danh sách rỗng không?

**Đáp:** không, vì vẫn có một người nhận thực tế trong Bcc. Ứng dụng có thể gửi nếu loại thông điệp và chính sách cho phép. Không được thêm Bcc vào To chỉ để “hết rỗng”.

### Tình huống B — Sau khi loại phần tử trắng, không còn ai

~~~text
To  = [" ", ""]
Cc  = []
Bcc = []
~~~

**Hỏi:** có nên gọi send(...) với mảng rỗng không?

**Đáp:** không. Nếu chính sách là từ chối phần tử trắng, báo lỗi đầu vào ngay. Nếu chính sách được phép bỏ phần tử trắng, kết quả không còn recipient nên phải **skip có lý do** hoặc trả lỗi thiếu người nhận theo hợp đồng nghiệp vụ. Không được ghi nhận là email đã phát thành công.

### Tình huống C — Trùng khác cách viết domain

~~~text
To = ["lan@Example.Test", "lan@example.test"]
~~~

**Hỏi:** có thể xem là trùng không?

**Đáp:** với chính sách chuẩn hóa domain về chữ thường và giữ nguyên local-part, đây là hai bản ghi có cùng khóa. Có thể báo lỗi hoặc loại trùng theo quy tắc đã công bố.

### Tình huống D — Khác chữ hoa ở local-part

~~~text
To = ["Lan@example.test", "lan@example.test"]
~~~

**Hỏi:** có nên ép thành một địa chỉ không?

**Đáp:** không nên áp dụng một cách vô điều kiện. Theo giao thức truyền thống, ý nghĩa phân biệt hoa/thường của local-part có thể do hệ thống nhận quyết định. Nếu sản phẩm có quy tắc tài khoản riêng thì áp dụng quy tắc đó, nhưng không tự suy rộng cho mọi domain.

### Tình huống E — Trùng giữa To và Bcc

~~~text
To  = ["lan@example.test"]
Bcc = ["lan@example.test"]
~~~

**Hỏi:** vì sao không chỉ gộp thành một mục?

**Đáp:** To và Bcc mang ngữ nghĩa hiển thị khác nhau. Tự chọn một vị trí có thể làm thay đổi ý định của người tạo thư. Chính sách minh họa trong bài **từ chối xung đột** và yêu cầu bên gọi phân loại lại.

### Tình huống F — Parser chấp nhận nhưng SMTP từ chối

~~~text
To = ["unknown@recipient.test"]
~~~

**Hỏi:** bước kiểm tra InternetAddress.validate() thành công có nghĩa sẽ phát thư được không?

**Đáp:** không. Đây là kiểm tra cú pháp, không phải xác minh mailbox tồn tại. SMTP server hoặc provider có thể từ chối ở bước RCPT TO hoặc chấp nhận trước rồi phát thông báo bounce về sau.

### Tình huống G — Người nhận nhập hai địa chỉ vào một ô

~~~text
"lan@example.test, minh@example.test"
~~~

**Hỏi:** chuỗi này là một địa chỉ hay hai địa chỉ?

**Đáp:** tùy contract của API. Nếu mỗi phần tử danh sách phải là một mailbox thuần, đây là dữ liệu **không phù hợp đầu vào**. Nếu giao diện có một ô nhập nhiều địa chỉ, cần dùng parser phù hợp rồi chuyển thành hai phần tử trước khi chạy chính sách. Không nên giả định mọi dấu phẩy đều là dấu ngăn tách an toàn trong mọi cú pháp địa chỉ.

### Tình huống H — Gửi hai email giống nhau do hai sự kiện

~~~text
Job 1001 -> lan@example.test -> EVENT_ORDER_CREATED
Job 1002 -> lan@example.test -> EVENT_ORDER_SHIPPED
~~~

**Hỏi:** có nên loại bỏ job thứ hai vì người nhận đã xuất hiện trong job trước?

**Đáp:** không. Đây là hai sự kiện nghiệp vụ khác nhau; loại trùng recipient trong một message không được dùng để loại bỏ thông báo của sự kiện khác. Để chống **cùng một sự kiện bị tạo job nhiều lần**, dùng khóa idempotency gắn với event cụ thể.

### Tình huống I — Batch gửi thành công cho một số người

~~~text
To = ["lan@example.test", "minh@example.test"]
SMTP provider xác nhận tiếp nhận Lan;
trạng thái của Minh không rõ do mất kết nối.
~~~

**Hỏi:** có thể đánh dấu toàn bộ batch là thất bại rồi retry tất cả ngay không?

**Đáp:** điều đó có thể tạo thư trùng cho Lan. Cần đối chiếu kết quả đã biết, trạng thái provider và cơ chế retry; với yêu cầu quan trọng nên quản lý công việc riêng cho từng recipient hoặc lưu trạng thái từng recipient.

## 14. Nguyên tắc thiết kế có thể áp dụng

Một luồng gửi thư ổn định trong Spring Framework Mail có thể được tổ chức như sau:

~~~text
1. Nhận dữ liệu
   -> To, Cc, Bcc cùng thông tin nghiệp vụ

2. Xác định chính sách
   -> yêu cầu To hay chỉ cần ít nhất một recipient?
   -> bỏ qua phần tử trống hay trả lỗi?
   -> trùng trong nhóm / giữa nhóm xử lý ra sao?

3. Kiểm tra trước khi gửi
   -> null, blank, ký tự điều khiển
   -> parse một mailbox cho mỗi phần tử
   -> giới hạn số địa chỉ
   -> kiểm tra nghiệp vụ và quyền nhận

4. Chuẩn hóa và xử lý trùng đúng phạm vi
   -> không tự đổi Bcc thành To
   -> không suy đoán alias của provider
   -> không làm mất thông tin sự kiện nghiệp vụ

5. Tạo message
   -> JavaMailSender / MimeMessageHelper / SimpleMailMessage
   -> giữ To, Cc, Bcc đúng ý nghĩa

6. Gửi và theo dõi
   -> SMTP submit có thể lỗi từng recipient
   -> không đồng nhất submit với delivered
   -> retry và quản lý trạng thái theo bằng chứng có được
~~~

**Danh sách rỗng**, **danh sách trùng** và **địa chỉ không hợp lệ** là ba loại vấn đề khác nhau: rỗng khiến không có đích gửi, trùng gây mơ hồ về số lần gửi hoặc quyền hiển thị, còn không hợp lệ có thể được phát hiện ở cú pháp, chính sách hoặc lúc hạ tầng SMTP chuyển phát. Khi phân biệt đúng các trường hợp này, ứng dụng Spring Mail có thể từ chối đầu vào sai sớm, tránh để lộ Bcc và báo trạng thái gửi thư chính xác hơn.
