# DNS MX và cách miền nhận thư được tìm thấy

Khi ứng dụng gửi thư đến `linh@example.org`, nó biết địa chỉ người nhận nhưng chưa biết máy chủ nào đang tiếp nhận email cho miền `example.org`. Địa chỉ người nhận không chứa địa chỉ IP hay cổng mạng của máy chủ nhận thư. Cần một cơ chế công bố thông tin định tuyến để máy chủ gửi có thể tìm đúng nơi chuyển thư đến.

**Bản ghi DNS MX (Mail Exchanger)** giải quyết phần tìm nơi nhận thư của một miền: nó chỉ ra những **tên máy chủ được miền đó công bố để tiếp nhận email** và thứ tự ưu tiên thử gửi. MX là một mảnh quan trọng trong việc chuyển thư giữa các máy chủ SMTP, nhưng tự nó không xác nhận hộp thư có tồn tại, không bảo đảm thư được chuyển phát và không quyết định việc thư có bị đánh dấu spam hay không.

Trong ngữ cảnh **Spring Framework Mail**, cần phân biệt rõ đường đi của email trong ứng dụng với đường đi của email trên Internet. Ứng dụng thường kết nối đến máy chủ SMTP đã cấu hình qua `JavaMailSender`. Chính máy chủ SMTP chuyển tiếp hoặc hạ tầng phía sau nó mới thực hiện tra cứu MX của miền người nhận để chuyển thư tiếp.

## 1. Vì sao cần DNS MX?

Một địa chỉ email thường có dạng:

~~~text
linh@example.org
│    └── Miền nhận thư: example.org
└─────── Phần định danh hộp thư trong miền: linh
~~~

Từ phần sau dấu `@`, hệ thống gửi xác định **miền nhận thư**. Tuy nhiên, một miền web và hệ thống nhận email của nó có thể nằm ở những nơi hoàn toàn khác nhau:

- `example.org` có thể phục vụ website bằng một máy chủ web.
- Email gửi đến `@example.org` có thể do một nhà cung cấp email khác tiếp nhận.
- Miền có thể khai báo nhiều máy chủ nhận thư để dự phòng hoặc phân phối lưu lượng.

Vì thế, chỉ phân giải `example.org` thành địa chỉ IP của website là chưa đủ để tìm nơi gửi email. DNS cho phép miền công bố **bản ghi MX** riêng cho chức năng nhận thư.

| Thành phần | Công dụng | Ví dụ minh họa |
| --- | --- | --- |
| `A` | Ánh xạ tên máy chủ thành địa chỉ IPv4 | `mx1.mail.example.net → 192.0.2.10` |
| `AAAA` | Ánh xạ tên máy chủ thành địa chỉ IPv6 | `mx1.mail.example.net → 2001:db8::10` |
| `MX` | Chỉ định tên máy chủ tiếp nhận email cho một miền cùng mức ưu tiên | `example.org → 10 mx1.mail.example.net` |
| `TXT` | Lưu dữ liệu văn bản, chẳng hạn chính sách SPF hoặc thông tin xác thực tên miền | `v=spf1 ...` |

Các địa chỉ `192.0.2.10` và `2001:db8::10` ở trên là địa chỉ dành cho tài liệu minh họa, không phải máy chủ gửi thư thật. **MX trỏ đến tên máy chủ**, rồi tên máy chủ đó mới được phân giải tiếp thành địa chỉ IP thông qua `A` hoặc `AAAA`.

## 2. Một email đi từ Spring đến miền nhận như thế nào?

Giả sử hệ thống Spring gửi thông báo cho `linh@example.org` và sử dụng SMTP relay của nhà cung cấp. Đường đi thường có dạng:

~~~mermaid
flowchart TD
    A["Ứng dụng Spring"] -->|"JavaMailSender.send()"| B["SMTP relay đã cấu hình"]
    B --> C["Tra cứu DNS MX của example.org"]
    C --> D["Nhận danh sách tên máy chủ và độ ưu tiên"]
    D --> E["Tra cứu A/AAAA cho máy chủ MX"]
    E --> F["Kết nối SMTP đến máy chủ nhận"]
    F --> G["Máy chủ nhận kiểm tra người nhận/chính sách"]
    G --> H["Hộp thư hoặc hệ thống xử lý tiếp theo"]
~~~

Quy trình có thể được diễn giải chi tiết:

1. **Ứng dụng tạo thông điệp.** Mã Java chuẩn bị địa chỉ người gửi, người nhận, tiêu đề và nội dung. `JavaMailSender` gửi thông điệp đến máy chủ SMTP được cấu hình cho ứng dụng.
2. **Máy chủ gửi xác định miền đích.** Khi cần chuyển thư ra ngoài, hệ thống gửi đọc miền trong địa chỉ người nhận của **SMTP envelope**, chẳng hạn `example.org` từ lệnh `RCPT TO:<linh@example.org>`.
3. **Máy chủ gửi hỏi DNS.** Nó yêu cầu các bản ghi `MX` của `example.org`, thường thông qua bộ phân giải DNS (recursive resolver). Bộ phân giải có thể trả lời từ bộ nhớ đệm hoặc truy vấn các máy chủ DNS có thẩm quyền.
4. **Nhận danh sách MX.** Kết quả bao gồm tên các máy chủ nhận thư và số ưu tiên của từng máy chủ. Số **nhỏ hơn** được ưu tiên hơn.
5. **Phân giải địa chỉ mạng.** Máy chủ gửi tra `A`/`AAAA` cho tên máy chủ MX được chọn để lấy địa chỉ IP có thể kết nối.
6. **Thực hiện phiên SMTP.** Máy chủ gửi kết nối đến máy chủ nhận, thường qua TCP **cổng 25** cho việc chuyển thư giữa các máy chủ, sau đó trao đổi lệnh SMTP và truyền nội dung thư nếu được chấp nhận.
7. **Máy chủ nhận xử lý.** Hạ tầng đích quyết định có chấp nhận người nhận, áp dụng chính sách chống lạm dụng, lưu thư vào hộp thư hoặc chuyển tiếp vào hệ thống nội bộ.

Hệ thống gửi có thể dùng nhiều bước chuyển tiếp và hàng đợi trung gian. Sơ đồ mô tả nguyên lý định tuyến giữa các miền, không có nghĩa mỗi email chỉ đi qua đúng một máy chủ.

### Miền trong SMTP envelope mới là đầu vào định tuyến

Một email có thể có tiêu đề hiển thị:

~~~text
From: Thông báo <notify@example.com>
To: Linh <linh@example.org>
Subject: Xác nhận đăng ký
~~~

Nhưng phiên SMTP có thông tin *envelope* riêng, ví dụ:

~~~text
MAIL FROM:<bounce@example.com>
RCPT TO:<linh@example.org>
~~~

Địa chỉ trong `RCPT TO` là nơi máy chủ gửi cần chuyển thư tới; MX được tìm dựa trên miền của địa chỉ nhận ở bước này. Các trường `From` và `To` trong tiêu đề phục vụ trình bày thông điệp và có thể khác thông tin envelope, chẳng hạn khi có chuyển tiếp, danh sách thư hoặc xử lý thư bị trả lại (*bounce*). Vì thế, không nên mặc định rằng hệ thống tìm MX chỉ bằng cách đọc trường `To` trong nội dung email.

## 3. Cấu trúc và cách đọc bản ghi MX

Giả sử nhà quản trị công bố các bản ghi DNS minh họa sau:

~~~dns
example.org.  3600  IN  MX  10 mx1.mail.example.net.
example.org.  3600  IN  MX  20 mx2.mail.example.net.

mx1.mail.example.net.  3600  IN  A     192.0.2.10
mx2.mail.example.net.  3600  IN  A     192.0.2.20
~~~

Đây là bộ bản ghi **giả định để học**, không phải kết quả truy vấn DNS hiện tại của `example.org` hay `example.net`.

| Phần trong bản ghi | Ý nghĩa |
| --- | --- |
| `example.org.` | Tên miền nhận thư mà bản ghi MX áp dụng. Dấu chấm cuối thể hiện tên DNS đầy đủ (FQDN). |
| `3600` | TTL, thời gian bộ phân giải có thể lưu kết quả trong bộ nhớ đệm, đơn vị giây. |
| `IN` | Lớp bản ghi Internet trong DNS. |
| `MX` | Loại bản ghi Mail Exchanger. |
| `10` hoặc `20` | Giá trị `preference`: số thấp hơn có mức ưu tiên cao hơn. |
| `mx1.mail.example.net.` | Tên máy chủ được chỉ định để nhận thư; cần phân giải được thành địa chỉ IP. |

Với dữ liệu này, hệ thống gửi **ưu tiên thử** `mx1.mail.example.net` vì giá trị 10 thấp hơn 20. Nếu không thể chuyển thư qua máy chủ ưu tiên theo quy tắc SMTP và chính sách thử lại, hệ thống có thể thử `mx2.mail.example.net`.

### Độ ưu tiên không phải tỷ lệ chia tải

Các giá trị 10 và 20 không mang nghĩa 10% và 20%, cũng không phải số cổng. Chúng chỉ biểu thị **thứ tự ưu tiên**.

- `MX 10 mail-a.example.net` và `MX 20 mail-b.example.net`: ưu tiên máy chủ `mail-a`.
- `MX 10 mail-a.example.net` và `MX 10 mail-b.example.net`: hai máy chủ cùng mức ưu tiên. Hệ thống gửi cần phân phối/thay đổi thứ tự thử theo cách phù hợp với SMTP, thay vì luôn cố định gửi một máy.
- Có nhiều MX **không tự bảo đảm tính sẵn sàng cao**: máy dự phòng cũng phải được cấu hình nhận thư đúng miền, có quyền tiếp nhận và xử lý thư thích hợp.

Giá trị TTL không buộc mọi máy chủ trên thế giới thấy thay đổi ngay lập tức. Các bộ phân giải có thể vẫn dùng bản ghi đã lưu trong thời hạn còn hiệu lực. Khi chuyển nhà cung cấp email, việc thay MX cần tính đến độ trễ bộ nhớ đệm và khả năng thư tiếp tục đến hệ thống cũ một thời gian.

## 4. Quy tắc tìm máy chủ đích khi có, thiếu hoặc lỗi bản ghi MX

Nguyên tắc chung của SMTP khi chuyển thư đến một miền là tìm MX và xác định những máy chủ có thể kết nối, nhưng cần phân biệt một số tình huống rất khác nhau.

### Trường hợp A — Miền có một hoặc nhiều bản ghi MX hợp lệ

Hệ thống gửi chọn các máy chủ theo mức ưu tiên, phân giải tên máy chủ MX thành địa chỉ `A` và/hoặc `AAAA`, rồi cố gắng kết nối bằng SMTP. Nếu một kết nối không thực hiện được, hệ thống có thể thử địa chỉ hoặc máy chủ MX khác. Những lỗi tạm thời cũng có thể khiến thư được giữ lại để thử gửi sau.

**Lưu ý:** nếu miền đã công bố MX nhưng máy chủ MX đó không có địa chỉ IP sử dụng được, đây là vấn đề cấu hình hoặc khả dụng của MX. Không thể tùy tiện bỏ qua MX và chuyển sang địa chỉ IP của website tại tên miền gốc.

### Trường hợp B — Không có bản ghi MX, nhưng miền vẫn tồn tại

Theo quy tắc SMTP truyền thống, khi tra cứu thành công nhưng miền **không có MX**, hệ thống gửi có thể áp dụng cơ chế **MX ngầm định** (*implicit MX*): thử tra `A`/`AAAA` của **chính miền người nhận** rồi gửi SMTP đến địa chỉ nhận được.

Ví dụ minh họa:

~~~dns
example.org.  3600  IN  A  192.0.2.30
; Không khai báo bản ghi MX cho example.org.
~~~

Khi đó, hệ thống gửi có thể thử kết nối SMTP đến `192.0.2.30` của `example.org`. Điều này **không có nghĩa website chạy ở địa chỉ đó chắc chắn nhận được thư**. Máy chủ vẫn phải có dịch vụ SMTP và được cấu hình tiếp nhận email cho miền tương ứng.

Việc không có MX là khác với việc DNS bị lỗi. Cơ chế dự phòng chỉ áp dụng khi kết quả truy vấn cho phép kết luận hợp lệ rằng miền không công bố MX.

### Trường hợp C — Miền chủ động từ chối nhận thư bằng Null MX

Một miền chỉ dùng cho website, tài liệu hoặc hạ tầng kỹ thuật có thể muốn thông báo rõ rằng mình **không nhận email**. Nó có thể công bố *Null MX* theo RFC 7505:

~~~dns
example.org.  3600  IN  MX  0 .
~~~

Dấu chấm `.` là đích MX đặc biệt, không phải tên một máy chủ cần kết nối. Cấu hình Null MX có nghĩa miền tuyên bố không có dịch vụ email nhận; hệ thống gửi tuân thủ chuẩn sẽ không tìm máy chủ theo cơ chế MX ngầm định rồi cố gửi thư.

Null MX là một bản ghi riêng và không nên đặt xen kẽ với các MX nhận thư thông thường. Nếu mục tiêu là nhận thư, không dùng Null MX.

### Trường hợp D — DNS lỗi hoặc không tìm được miền

Cần phân biệt:

- **`NXDOMAIN`:** tên miền được hỏi không tồn tại theo phản hồi DNS. Đây không tương đương với miền hợp lệ nhưng không khai báo MX.
- **Không có MX (`NOERROR`/không có dữ liệu MX):** miền hợp lệ nhưng không có bản ghi loại MX. Lúc này có thể xét cơ chế MX ngầm định nếu đáp ứng điều kiện.
- **`SERVFAIL`, hết thời gian chờ hoặc lỗi DNS tạm thời:** không thể xác định tuyến nhận thư một cách đáng tin cậy. Máy chủ gửi thường giữ thư trong hàng đợi và thử lại theo chính sách thay vì kết luận miền không có MX.
- **MX trỏ đến tên không phân giải được thành địa chỉ:** việc tìm tuyến có thể thất bại dù miền gốc có `A`, bởi một MX đã được khai báo phải dẫn tới máy chủ có thể kết nối.

Kết quả xử lý cuối cùng còn tùy phản hồi SMTP, thời gian lưu trong hàng đợi và chính sách của máy chủ gửi. Không nên quy mọi lỗi nhận thư về việc thiếu bản ghi MX.

### Một quy tắc quan trọng về tên đích MX

Giá trị đích của MX phải là **tên máy chủ**, không phải địa chỉ IPv4/IPv6 viết trực tiếp. Tên máy chủ được dùng làm đích MX cũng không nên là bí danh `CNAME`; theo quy định DNS, đích MX phải trỏ đến tên có thể phân giải trực tiếp thành địa chỉ thích hợp, thay vì phụ thuộc vào CNAME. Ví dụ, cấu hình sau là sai kiểu dữ liệu:

~~~text
example.org. IN MX 10 192.0.2.10
~~~

Hãy khai báo một hostname trong MX, sau đó tạo bản ghi `A`/`AAAA` cho hostname đó. Cách này cũng giúp địa chỉ IP của máy chủ thay đổi độc lập với bản ghi định tuyến thư.

## 5. Phân biệt DNS MX với cổng SMTP 25, 587 và 465

Một nhầm lẫn phổ biến là nghĩ MX cung cấp thông tin cổng hoặc thông số đăng nhập SMTP. **MX chỉ công bố tên máy chủ và mức ưu tiên, không chứa cổng, tài khoản, mật khẩu hay chế độ TLS.**

| Kết nối | Cổng thường dùng | Mục đích |
| --- | ---: | --- |
| SMTP giữa máy chủ gửi và máy chủ nhận (mail transfer) | `25` | Máy chủ chuyển thư đến máy chủ nhận được tìm qua MX. |
| SMTP submission từ ứng dụng/mail client tới nhà cung cấp | `587` | Ứng dụng nộp thư cho relay, thường dùng xác thực và nâng cấp kết nối bằng STARTTLS. |
| Submission qua TLS ngay từ đầu (implicit TLS) | `465` | Một lựa chọn submission khác khi nhà cung cấp hỗ trợ. |

Các cổng là quy ước phổ biến; cấu hình thực tế cần làm theo dịch vụ sử dụng. Một dịch vụ SMTP nội bộ có thể dùng cổng khác trong mạng riêng.

**Đường đi qua relay** là tình huống phổ biến của Spring Framework Mail:

~~~mermaid
flowchart LR
    A["JavaMailSender"] -->|"SMTP submission: 587/465"| B["SMTP relay"]
    B -->|"DNS MX + SMTP transfer: thường 25"| C["MX của miền người nhận"]
~~~

Trong trường hợp này, ứng dụng **không cần tra cứu MX của từng người nhận**. Nó chỉ cần kết nối đến hostname SMTP được cấu hình, ví dụ `smtp.provider.example`; relay chịu trách nhiệm tìm miền đích và chuyển thư. Đây là lý do không tìm thấy mã truy vấn MX trong một ứng dụng Spring vẫn có thể hoàn toàn bình thường.

## 6. Vai trò cụ thể của Spring Framework Mail

Spring Mail cung cấp giao diện như `JavaMailSender` và công cụ tạo thông điệp. Với Spring Boot, cấu hình gửi thư thường có dạng:

~~~properties
spring.mail.host=smtp.provider.example
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000
~~~

Hostname `smtp.provider.example` chỉ dùng để minh họa. Người triển khai phải thay bằng máy chủ submission do nhà cung cấp cấp và thiết lập biến môi trường phù hợp. Cấu hình `spring.mail.host` xác định **máy chủ mà ứng dụng kết nối để gửi thư**, không phải MX của miền người nhận. Việc DNS phân giải hostname này để thiết lập kết nối mạng là thao tác khác với tra MX của `example.org`.

Ví dụ gọi gửi một thông báo:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class OrderMailService {
    private final JavaMailSender mailSender;

    public OrderMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderNotice(String recipient, String sender) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(sender);
        message.setTo(recipient);
        message.setSubject("Đơn hàng đã được ghi nhận");
        message.setText("Hệ thống đã tiếp nhận đơn hàng của bạn.");

        mailSender.send(message);
    }
}
~~~

Mã gửi thư không cần trích miền từ `recipient` rồi tự gọi DNS MX. Khi `mailSender.send(message)` hoàn tất, kết quả chỉ phản ánh bước gửi đến hạ tầng SMTP đã kết nối; **không chứng minh người nhận đã có thư trong Inbox**.

Nếu ứng dụng cố gắng chuyển thư trực tiếp tới máy chủ MX của mỗi miền thay vì qua relay, nó phải đảm nhận cả logic định tuyến SMTP, tương tác DNS, hàng đợi thử lại, xử lý bounce, bảo mật và khả năng chuyển phát. Đây thường là trách nhiệm của một mail transfer agent (MTA) chuyên dụng, không phải mục tiêu mặc định của `JavaMailSender`.

## 7. Tự quan sát MX và địa chỉ máy chủ bằng công cụ DNS

Có thể dùng công cụ dòng lệnh để xem miền công bố máy chủ nhận thư nào. Những ví dụ dưới đây là **cú pháp truy vấn**, không khẳng định kết quả DNS thực tế tại một thời điểm cụ thể.

### Trên Linux/macOS với `dig`

~~~bash
dig MX example.org
dig +short MX example.org
~~~

Trong truy vấn đầu tiên, phần `ANSWER SECTION` (nếu có) cho biết bản ghi MX; tùy bộ phân giải và miền, có thể xuất hiện thông tin bổ sung. Tùy chọn `+short` giúp xem các MX gọn hơn.

Ví dụ **đầu ra giả định**:

~~~text
10 mx1.mail.example.net.
20 mx2.mail.example.net.
~~~

Sau khi biết hostname MX, truy vấn địa chỉ tương ứng:

~~~bash
dig A mx1.mail.example.net
dig AAAA mx1.mail.example.net
~~~

Khi cần kiểm tra máy chủ DNS có thẩm quyền, có thể bắt đầu từ bản ghi `NS` của miền và truy vấn trực tiếp tới máy chủ đó; đừng nhầm kết quả lưu trong bộ nhớ đệm của resolver với việc bản ghi đã được cập nhật tại nguồn.

### Trên Windows với PowerShell

~~~powershell
Resolve-DnsName -Name example.org -Type MX
Resolve-DnsName -Name mx1.mail.example.net -Type A
Resolve-DnsName -Name mx1.mail.example.net -Type AAAA
~~~

Hoặc dùng `nslookup` trên hệ thống có hỗ trợ:

~~~text
nslookup -type=mx example.org
~~~

Quy trình quan sát hợp lý là **xem MX trước → đọc hostname và priority → xem A/AAAA của hostname → kiểm tra SMTP và cấu hình nhà cung cấp nếu vẫn lỗi**. Chỉ tra MX không đủ để chẩn đoán toàn bộ đường đi của thư.

## 8. MX không thay thế SPF, DKIM, DMARC hay TLS

MX nói **nơi có thể chuyển email đến**. Những bản ghi và cơ chế khác giải quyết những câu hỏi độc lập:

| Cơ chế | Câu hỏi chính mà nó giải quyết | Liên hệ với MX |
| --- | --- | --- |
| MX | Máy chủ nào công bố nhận email cho miền? | Nền tảng tìm nơi nhận thư giữa các miền. |
| SPF | Những máy chủ nào được phép gửi email với danh tính envelope-domain đã khai báo? | Thường công bố qua DNS TXT; không dùng MX để suy ra toàn bộ người gửi hợp lệ. |
| DKIM | Nội dung và một số tiêu đề có chữ ký mật mã từ miền ký không? | Khóa công khai được tra qua DNS; không quyết định máy chủ nhận. |
| DMARC | Kết quả SPF/DKIM có phù hợp với miền `From` hiển thị và chính sách của miền không? | Thường dùng DNS TXT; giúp miền công bố chính sách xác thực và báo cáo. |
| STARTTLS | Có thể mã hóa kết nối SMTP trong lúc truyền không? | Hoạt động ở phiên SMTP; MX tự nó không bảo đảm có TLS. |
| MTA-STS / DANE | Có thể tăng độ tin cậy của việc chọn/thiết lập kết nối TLS tới MX không? | Các cơ chế bổ sung, cần hạ tầng và cấu hình riêng. |

Một miền có MX hợp lệ vẫn có thể bị mạo danh phần hiển thị nếu thiếu các lớp bảo vệ phù hợp; ngược lại, cấu hình SPF/DKIM/DMARC cho việc gửi thư cũng không đồng nghĩa miền đã có hộp thư nhận. Khi vận hành email hai chiều, thường cần thiết lập **cả tuyến nhận và danh tính gửi**.

## 9. Những tình huống cấu hình và vận hành thường gặp

### 9.1. Miền có website nhưng không nhận được email

Website đang hoạt động chứng tỏ tên miền có thể được phân giải phục vụ HTTP/HTTPS; điều đó **không xác nhận cấu hình MX hoặc dịch vụ SMTP nhận thư đã đúng**. Cần xem liệu miền có MX không, đích MX có địa chỉ IP không, cổng 25 và máy chủ SMTP có hoạt động không, và nhà cung cấp có thực sự được cấu hình nhận thư cho miền không.

### 9.2. Đã tạo MX nhưng chưa tạo hộp thư

MX chỉ giúp tìm máy chủ. Máy chủ nhận có thể từ chối `RCPT TO` nếu hộp thư `linh` không tồn tại, hoặc chuyển thư tới một chính sách nhận khác. Cần tạo hộp thư, bí danh, tuyến chuyển tiếp hoặc cấu hình nhận tương ứng ở hệ thống đích.

### 9.3. Có hai MX nhưng dự phòng vẫn thất bại

Máy MX thứ hai không được tự động biến thành bản sao máy MX thứ nhất. Nó có thể không nhận đúng miền, không biết nơi lưu/chuyển tiếp thư hoặc bị tường lửa chặn. Để dự phòng hiệu quả, cần chuẩn bị cả hai phía: **bản ghi DNS phù hợp và hạ tầng nhận thư thực sự tương thích**.

### 9.4. Vừa đổi MX nhưng thư vẫn đi tới nhà cung cấp cũ

Resolver có thể đang giữ bản ghi theo TTL; một số mail server cũng có hàng đợi thư cần xử lý. Khi di chuyển hệ thống email, nên duy trì nhà cung cấp cũ trong giai đoạn chuyển tiếp có kiểm soát, kiểm tra DNS từ nhiều nguồn và xem log ở cả hạ tầng cũ lẫn mới nếu có quyền truy cập.

### 9.5. Spring gửi báo thành công nhưng người dùng không thấy thư

Cần xem log và trạng thái giao cho SMTP relay trước, sau đó dùng dashboard hoặc mã phản hồi chuyển phát của nhà cung cấp để kiểm tra thư bị trả lại, từ chối, chậm hoặc xếp vào spam. Chỉ kiểm tra MX của miền đích chưa thể xác định lỗi xảy ra ở đâu. `JavaMailSender` không cung cấp cơ chế theo dõi trạng thái mở thư hoặc thư đã vào Inbox.

### 9.6. SMTP relay của Spring hoạt động nhưng miền của chính ứng dụng không có MX

Nếu ứng dụng chỉ **gửi đi** từ một địa chỉ đã được nhà cung cấp cho phép, việc gửi đi có thể vẫn hoạt động qua SMTP relay dù miền đó chưa cấu hình MX nhận thư. Tuy vậy, nếu muốn người nhận trả lời email hoặc nhận bounce qua hộp thư của mình, miền cần có tuyến nhận phù hợp. Quy tắc xác thực và chính sách của nhà cung cấp có thể đặt thêm yêu cầu đối với miền gửi.

## 10. Một sơ đồ quyết định để ghi nhớ

Khi một mail server chuẩn bị chuyển thư đến `user@domain.example`, có thể hình dung quá trình tìm tuyến nhận như sau:

~~~mermaid
flowchart TD
    A["Lấy miền trong RCPT TO"] --> B["Tra cứu DNS MX"]
    B --> C{"Kết quả DNS?"}
    C -->|"Có MX thường"| D["Sắp xếp theo preference"]
    D --> E["Tra A/AAAA của đích MX"]
    E --> F["Thử SMTP tới máy chủ nhận"]
    C -->|"Không có MX, miền hợp lệ"| G["Thử A/AAAA của chính miền"]
    G --> F
    C -->|"Null MX"| H["Miền công bố không nhận email"]
    C -->|"Lỗi DNS tạm thời"| I["Hoãn và thử lại theo chính sách"]
    C -->|"Miền không tồn tại"| J["Không có tuyến nhận hợp lệ"]
~~~

Sơ đồ này chỉ tập trung vào việc tìm tuyến. Sau bước kết nối, máy chủ nhận còn có thể chấp nhận, trì hoãn hoặc từ chối thư tùy địa chỉ nhận và chính sách vận hành.

Một bài tập nhỏ để tự suy luận:

1. `example.org` có `MX 5 mx-a.example.net` và `MX 50 mx-b.example.net`. Máy chủ nào được ưu tiên trước? **`mx-a.example.net`**, vì giá trị preference nhỏ hơn.
2. `example.org` không có MX, nhưng có `A`. Có chắc email được nhận không? **Không**; SMTP có cơ chế MX ngầm định nhưng máy chủ tại IP đó còn phải thật sự tiếp nhận thư.
3. `example.org` có `MX 0 .`. Có nên thử gửi đến địa chỉ web của miền? **Không**; Null MX tuyên bố miền không nhận email.
4. Ứng dụng Spring dùng `spring.mail.host=smtp.provider.example`. Thành phần nào thường tìm MX của người nhận? **SMTP relay của nhà cung cấp** khi chuyển thư ra ngoài.

## 11. Kết nối lại với kiến trúc Spring Framework Mail

Trong toàn bộ hành trình gửi email, **Spring Framework Mail** hỗ trợ ứng dụng xây dựng thông điệp và nộp thư cho một máy chủ SMTP đã cấu hình. **DNS MX** phục vụ bước định tuyến khi một máy chủ gửi cần tìm nơi nhận email của miền đích. Sau đó, **SMTP và hạ tầng email** thực hiện chuyển thư, kiểm tra người nhận và xử lý trạng thái chuyển phát.

Giữ rõ ba phần việc — **tạo yêu cầu gửi trong Spring**, **tìm miền nhận bằng DNS MX**, **chuyển phát qua SMTP** — giúp tránh nhầm lẫn giữa lỗi cấu hình ứng dụng, lỗi DNS và lỗi hạ tầng nhận thư. Đây cũng là nền tảng để tìm hiểu sâu hơn về SMTP relay, DNS cho hệ thống email, xác thực miền và chiến lược gửi thư tin cậy.
