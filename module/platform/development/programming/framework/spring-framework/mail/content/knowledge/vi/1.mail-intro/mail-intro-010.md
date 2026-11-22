# Giới hạn của việc coi email như một lời gọi đồng bộ đơn giản

Khi bắt đầu học **Spring Framework Mail**, ta thường viết vài dòng mã tạo thông điệp, gọi **JavaMailSender.send(...)** rồi kết luận: “Ứng dụng đã gửi email”. Cách viết đó đủ để thấy Spring giúp tích hợp với máy chủ SMTP như thế nào, nhưng dễ dẫn đến một mô hình tư duy sai: **gọi hàm gửi mail thành công không đồng nghĩa người nhận đã nhận được thư**. Nó cũng không bảo đảm thao tác gửi có thể được lặp lại an toàn, không gây ảnh hưởng đến tốc độ API, hoặc luôn nhất quán với dữ liệu vừa lưu.

Bài học này phân tích các giới hạn đó từ góc nhìn ứng dụng Spring, giúp phân biệt rõ trách nhiệm của đoạn mã gửi email, máy chủ SMTP, hệ thống phân phối thư và luồng nghiệp vụ. Đây là nền tảng để quyết định khi nào cách gửi trực tiếp là đủ và khi nào cần xử lý nền, hàng đợi hoặc một cơ chế gửi đáng tin cậy hơn.

## 1. Một lời gọi đồng bộ thực sự đang chờ điều gì?

Xét một lớp dịch vụ Spring đơn giản:

~~~java
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {
    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("no-reply@example.test");
        message.setTo(recipient);
        message.setSubject("Chào mừng");
        message.setText("Tài khoản của bạn đã được tạo.");

        mailSender.send(message);
    }
}
~~~

Đây là **lời gọi đồng bộ ở phía ứng dụng**: luồng đang thực thi phương thức **sendWelcome** phải chờ thao tác gửi thông qua cơ chế mail đã cấu hình hoàn tất hoặc phát sinh lỗi. Với cấu hình SMTP thông thường, phần việc đó gồm việc kết nối tới máy chủ, thực hiện hội thoại giao thức và chuyển nội dung thư tới máy chủ tiếp nhận.

Nhưng thư còn có một hành trình riêng sau thời điểm ứng dụng trao nó cho máy chủ SMTP:

~~~text
HTTP request
    |
    v
Spring service
    |
    | JavaMailSender.send(...)
    v
SMTP server / email provider
    |
    | Xếp hàng, định tuyến, chuyển tiếp, thử gửi lại...
    v
Máy chủ nhận thư
    |
    | Kiểm tra spam, chính sách, bộ lọc, quy tắc hộp thư...
    v
Inbox / Spam / thư bị từ chối hoặc bị trả lại
    |
    v
Người nhận có thể mở và đọc thư
~~~

**Ranh giới cần ghi nhớ:** một lần trao thư thành công cho máy chủ SMTP thường chỉ cho biết máy chủ đã **chấp nhận trách nhiệm xử lý thông điệp** ở giai đoạn đó. Nó chưa chứng minh thư đã đến hộp thư đích, nằm trong Inbox hay đã được con người đọc.

Ngay cả phản hồi SMTP thành công (chẳng hạn mã thuộc nhóm **2xx**, điển hình là **250** sau khi máy chủ chấp nhận dữ liệu thông điệp) cũng chỉ phản ánh kết quả của bước giao tiếp tương ứng. Máy chủ nhận có thể tiếp tục chuyển thư, trì hoãn, áp dụng chính sách hoặc tạo thông báo không phát được về sau. Mức độ theo dõi chi tiết phụ thuộc dịch vụ email và các cơ chế xác nhận mà hệ thống tích hợp.

### Các trạng thái không nên đánh đồng

| Mốc | Ý nghĩa | Có thể kết luận gì? |
| --- | --- | --- |
| Ứng dụng tạo thông điệp | Đã có địa chỉ nhận, tiêu đề và nội dung | Chưa có giao tiếp gửi thư |
| Ứng dụng ghi công việc gửi vào hàng đợi | Yêu cầu đã được lưu để xử lý sau | Chưa chắc đã liên hệ SMTP |
| Máy chủ SMTP chấp nhận thư | Bước nộp thư tương ứng đã thành công | Không khẳng định thư đã đến Inbox |
| Nhà cung cấp báo đã phát tới máy chủ nhận | Có tín hiệu phát thư ở mức hạ tầng | Không bảo đảm thư nằm trong Inbox |
| Người nhận mở hoặc đọc | Có tín hiệu tương tác nếu hệ thống có thu thập | Tín hiệu đọc có thể thiếu hoặc không chính xác tuyệt đối |

Do đó, tên trạng thái như **PENDING**, **SUBMITTED**, **DELIVERED** hay **FAILED** phải được định nghĩa theo **bằng chứng mà ứng dụng thực sự có**. Không nên đổi sang **DELIVERED** chỉ vì **send(...)** trả về mà không ném ngoại lệ.

## 2. Giới hạn về độ trễ và tài nguyên ứng dụng

Nếu gọi gửi thư ngay trong một API HTTP, thời gian phản hồi API sẽ bao gồm thời gian xử lý nghiệp vụ **cộng với thời gian chờ hệ thống mail**. Trong thời gian chờ, luồng xử lý request của kiểu ứng dụng Spring MVC thông thường vẫn đang bị chiếm dụng.

Ví dụ một luồng đăng ký tài khoản:

~~~text
POST /register
    -> kiểm tra dữ liệu:       20 ms
    -> ghi tài khoản:          40 ms
    -> gọi SMTP:            2.000 ms
    -> trả HTTP response

Tổng thời gian khoảng 2.060 ms, dù thao tác đăng ký chính chỉ mất 60 ms.
~~~

Các con số chỉ minh họa; độ trễ thực tế phụ thuộc mạng, máy chủ, cấu hình timeout và tải hệ thống. Khi lưu lượng tăng, hàng trăm request cùng chờ SMTP có thể khiến thread pool của máy chủ web bị sử dụng hết, dẫn đến request khác cũng bị chậm. Nếu email provider gặp sự cố, một chức năng phụ trợ như thư chào mừng có thể khiến cả luồng đăng ký có vẻ “bị hỏng”.

Vấn đề không nằm ở việc Spring Mail có lỗi: **một thao tác I/O mạng có thời gian hoàn thành khó dự đoán đã bị gắn trực tiếp vào thời gian sống của HTTP request**.

Hệ quả thường thấy:

- **Latency tăng:** người dùng chờ thao tác chính chỉ vì chờ SMTP.
- **Khả năng phục vụ giảm:** nhiều luồng bị chiếm trong lúc đợi phản hồi mạng.
- **Lỗi lan truyền:** máy chủ mail chậm hoặc gián đoạn kéo theo lỗi của API vốn vẫn có thể hoàn thành nghiệp vụ chính.
- **Timeout chồng nhau:** HTTP client, reverse proxy, web server và SMTP có các giới hạn chờ khác nhau; lớp bên ngoài có thể hết hạn trước khi kết quả gửi được xác định.

Chuyển việc gửi sang xử lý nền giúp giảm thời gian chờ của API, nhưng lúc đó cần một cơ chế quản lý công việc gửi riêng. Việc làm cho lời gọi “không chặn request” **không tự động làm nó đáng tin cậy hơn**.

## 3. Giới hạn về lỗi: thất bại và kết quả không rõ ràng

Từ góc nhìn Java, ta thường phân loại đơn giản:

~~~java
try {
    mailSender.send(message);
    // Lời gọi gửi hoàn tất mà không báo lỗi.
} catch (org.springframework.mail.MailException ex) {
    // Có lỗi trong quá trình chuẩn bị hoặc gửi thư.
}
~~~

**MailException** thể hiện lỗi ở tầng API Spring Mail. Tùy nguyên nhân, lỗi có thể liên quan đến cấu hình, xác thực, địa chỉ, kết nối, phản hồi của máy chủ hoặc thao tác gửi. Tuy nhiên, phân loại thành “hàm trả về” và “hàm ném lỗi” vẫn chưa đủ để kết luận chắc chắn một email cụ thể đã hoặc chưa được hệ thống ở xa tiếp nhận.

Hãy xét trường hợp sau:

1. Ứng dụng gửi đầy đủ nội dung thông điệp tới SMTP server.
2. SMTP server chấp nhận thư và chuẩn bị gửi phản hồi thành công.
3. Kết nối mạng bị đứt trước khi ứng dụng đọc được phản hồi.
4. Ứng dụng thấy lỗi I/O hoặc timeout.

Từ phía ứng dụng, kết quả lúc này **không xác định**: thư có thể đã được nhận để xử lý, hoặc chưa. Nếu lập tức gửi lại toàn bộ thông điệp, người nhận có khả năng nhận hai thư. Nếu không gửi lại, có khả năng người nhận không nhận được thư nào.

Đây là vấn đề phổ biến trong các hệ thống phân tán: **mất phản hồi không chứng minh thao tác từ xa chưa diễn ra**.

Ngoài ra, một đợt gửi tới nhiều người nhận có thể có kết quả khác nhau theo từng địa chỉ tùy máy chủ, cách gửi và cấu hình. Không nên mặc định mọi recipient luôn thành công hoặc thất bại cùng lúc như một giao dịch nguyên tử.

### Timeout có ích, nhưng không giải quyết toàn bộ bài toán

Trong ứng dụng Spring Boot dùng cấu hình SMTP, nên đặt các giới hạn chờ mạng một cách chủ động, chẳng hạn:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    properties:
      "[mail.smtp.connectiontimeout]": 3000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000
~~~

Các giá trị trên được tính bằng mili giây và chỉ là ví dụ:

- **connectiontimeout:** giới hạn thời gian chờ thiết lập kết nối.
- **timeout:** giới hạn thời gian chờ khi đọc dữ liệu qua socket.
- **writetimeout:** giới hạn thời gian chờ khi ghi dữ liệu qua socket.

Trong triển khai thật còn phải cấu hình xác thực, mã hóa TLS và thông tin máy chủ theo nhà cung cấp. Timeout nên được chọn dựa trên yêu cầu vận hành, không sao chép máy móc giá trị minh họa.

Đặt timeout giúp tránh một request treo quá lâu, **nhưng không biến thao tác SMTP thành một giao dịch bảo đảm phát thư**, và cũng không loại bỏ trường hợp máy chủ đã nhận thư trong khi phía ứng dụng mất kết nối.

## 4. Giới hạn về tính nhất quán với cơ sở dữ liệu

Giả sử yêu cầu đăng ký tài khoản có hai hành động: **lưu người dùng** và **gửi thư chào mừng**. Nhiều người đặt cả hai trong một phương thức có **@Transactional**:

~~~java
@Transactional
public void register(RegisterCommand command) {
    User user = userRepository.save(/* dữ liệu từ command */);
    welcomeMailService.sendWelcome(user.getEmail());
}
~~~

Đoạn trên mô tả ý tưởng, chưa phải ví dụ có thể biên dịch độc lập. Điểm quan trọng là phạm vi của transaction: **@Transactional của cơ sở dữ liệu không bao bọc được việc chuyển email qua SMTP**.

Hai tình huống điển hình:

**Tình huống A — thư gửi được, dữ liệu bị rollback.**

Ứng dụng gọi SMTP thành công rồi một thao tác cơ sở dữ liệu tiếp theo thất bại, khiến transaction rollback. Người dùng đã nhận thông báo “Tài khoản được tạo”, nhưng trong cơ sở dữ liệu lại không có tài khoản tương ứng. Spring không có cách tự động “thu hồi” email đã rời khỏi hệ thống để rollback cùng dữ liệu.

**Tình huống B — dữ liệu đã commit, thư gửi thất bại.**

Nếu lưu tài khoản và commit trước rồi mới gửi mail, lỗi SMTP không thể làm dữ liệu tự quay về trạng thái cũ. API có thể trả lỗi dù tài khoản đã tồn tại. Người dùng thử lại, gây lỗi trùng tài khoản hoặc kích hoạt thêm nhiều thư.

Vì vậy cần xác định rõ **nguồn sự thật của nghiệp vụ**: việc đăng ký được coi là hoàn thành theo trạng thái trong cơ sở dữ liệu, còn gửi email là công việc liên quan có vòng đời và khả năng lỗi riêng. Đối với một số tác vụ như xác minh email hay đặt lại mật khẩu, việc thư không đến có thể ngăn người dùng hoàn tất bước tiếp theo; hệ thống phải có cơ chế gửi lại và thông báo trạng thái hợp lý.

Đăng ký một callback gửi thư sau commit (ví dụ dùng sự kiện transaction hoặc cơ chế after-commit) giúp tránh tình huống gửi trước rồi rollback. Tuy nhiên, nếu tiến trình dừng **sau khi commit và trước khi callback gửi thành công**, yêu cầu gửi có thể bị mất. Muốn phục hồi công việc qua lần khởi động lại, cần lưu trạng thái công việc một cách bền vững.

## 5. Giới hạn về retry, gửi trùng và idempotency

“Nếu gửi lỗi thì thử lại” là hướng xử lý tự nhiên, nhưng chính sách retry thiếu kiểm soát có thể gây thêm sự cố:

- Retry ngay lập tức khi provider đang quá tải có thể khiến tình trạng quá tải nghiêm trọng hơn.
- Một địa chỉ không tồn tại hoặc thông điệp bị từ chối vĩnh viễn thường không nên được gửi đi gửi lại vô hạn.
- Kết quả SMTP không rõ ràng có thể khiến một email đã được tiếp nhận bị gửi lần nữa.
- Nếu người dùng gửi lại HTTP request sau timeout, ứng dụng có thể tạo thêm một công việc gửi khác cho cùng một sự kiện nghiệp vụ.

Nên phân biệt **retry của một công việc gửi đã tồn tại** với **tạo một công việc mới**. Chẳng hạn, sự kiện nghiệp vụ “gửi thư chào mừng cho lần đăng ký có ID 123” có thể mang một khóa duy nhất như **WELCOME:123**. Nhờ ràng buộc duy nhất trong cơ sở dữ liệu, nhiều lần xử lý cùng yêu cầu không vô tình sinh nhiều công việc gửi.

Tuy nhiên, khóa này chủ yếu giúp **chống tạo công việc trùng ở phía ứng dụng**. Nó không thể bảo đảm người nhận chỉ nhận đúng một email trong mọi trường hợp: nếu provider đã nhận thư rồi kết nối mất trước khi ứng dụng ghi nhận kết quả, retry vẫn có thể tạo bản sao. Đặc tính thực tế của nhiều thiết kế là **at-least-once processing**, chấp nhận có khả năng gửi trùng và hạn chế tác động của nó.

Một cơ chế retry vận hành được thường cần:

1. Lưu số lần thử, thời điểm thử gần nhất, lỗi và lịch thử tiếp.
2. Phân biệt lỗi có thể phục hồi (tạm mất kết nối, bị giới hạn tần suất) với lỗi khó phục hồi (địa chỉ/cấu hình không hợp lệ, từ chối vĩnh viễn), dựa trên thông tin thực sự do provider cung cấp.
3. Dùng **exponential backoff** và có thể thêm jitter để giảm việc nhiều worker thử lại cùng lúc.
4. Đặt số lần thử hoặc thời hạn xử lý tối đa, rồi chuyển sang trạng thái cần điều tra thay vì lặp vô hạn.
5. Giới hạn tốc độ gửi và tránh xử lý song song cùng một công việc không được khóa.

Với email chứa liên kết một lần, mã xác minh hoặc thông tin có hiệu lực ngắn, cần xem xét **thời điểm hết hạn**: gửi lại một thông điệp đã không còn sử dụng được sẽ khiến trải nghiệm người dùng tệ hơn.

## 6. Giới hạn về khả năng phát thư và quan sát kết quả

Ngay cả khi SMTP hoạt động ổn định, kết quả tới người nhận vẫn còn phụ thuộc vào hệ thống email:

| Yếu tố | Điều có thể xảy ra | Điều ứng dụng nên cân nhắc |
| --- | --- | --- |
| Giới hạn nhà cung cấp | Rate limit, quota hoặc tạm hoãn gửi | Điều tiết lưu lượng, retry theo chính sách provider |
| Danh tiếng domain/IP | Thư bị xem là đáng ngờ | Cấu hình và vận hành danh tính gửi phù hợp |
| Xác thực email | SPF, DKIM, DMARC không phù hợp | Kiểm tra DNS và chính sách xác thực của miền gửi |
| Hộp thư người nhận | Đầy dung lượng, không tồn tại, chính sách từ chối | Theo dõi bounce hoặc tín hiệu trả về khi có |
| Bộ lọc và cách trình bày | Vào Spam hoặc bị ẩn | Không hứa chắc thư xuất hiện trong Inbox |
| Thời gian phân phối | Thư bị trì hoãn trên nhiều bước trung gian | Thiết kế thông báo/trạng thái và khả năng gửi lại |

Spring Mail cung cấp API để tạo và gửi thông điệp; bản thân một lần gọi **JavaMailSender.send(...)** không phải là hệ thống quan sát đầy đủ vòng đời phát thư. Muốn biết email đã được nhà cung cấp xử lý, phát, bị trả lại hay bị khiếu nại spam, ứng dụng có thể cần báo cáo, webhook, event hoặc API riêng từ dịch vụ email.

Nếu dùng webhook, cần xác thực nguồn sự kiện, xử lý sự kiện đến trùng hoặc sai thứ tự, và đối chiếu về đúng công việc gửi. Không phải nhà cung cấp nào cũng cung cấp cùng tập trạng thái, và tín hiệu “đã mở thư” không phải bằng chứng tuyệt đối người thật đã đọc nội dung.

## 7. Mô hình phù hợp hơn khi email là tác vụ nền

Một cách thiết kế có khả năng phục hồi tốt là tách **ghi nhận yêu cầu gửi** khỏi **thử giao tiếp với provider**:

~~~text
Request đăng ký
    |
    v
Spring service
    |
    | Một database transaction
    +----> Lưu user
    +----> Lưu outbox event "WELCOME_EMAIL_REQUESTED"
    |
    v
COMMIT -> Trả response phù hợp

Worker nền
    |
    +----> Lấy công việc đang chờ
    +----> Tạo email và gọi SMTP/provider
    +----> Lưu kết quả từng lần thử
    +----> Thành công / chờ retry / cần xử lý thủ công
~~~

Đây là ý tưởng của **transactional outbox**: khi nghiệp vụ chính và bản ghi yêu cầu gửi được lưu trong **cùng một transaction cơ sở dữ liệu**, nếu transaction commit thì yêu cầu gửi cũng được giữ lại để xử lý sau. Worker đọc công việc chưa hoàn thành và tiếp tục sau khi ứng dụng khởi động lại.

Một phác thảo logic:

~~~text
register(command):
    begin database transaction
    user = saveUser(command)
    saveOutbox(
        eventType = "WELCOME_EMAIL_REQUESTED",
        businessKey = "WELCOME:" + user.id,
        recipient = user.email,
        status = "PENDING"
    )
    commit
    return registration result

worker():
    item = claimPendingMailSafely()
    try:
        submitMailToProvider(item)
        markSubmitted(item)
    catch retryable error:
        scheduleNextAttemptWithBackoff(item)
    catch permanent error:
        markFailed(item)
~~~

Đây là **pseudocode minh họa cách phân chia trách nhiệm**, không phải mã hoàn chỉnh có thể chạy ngay. Trong triển khai thật, thao tác nhận công việc cần chống hai worker xử lý cùng một bản ghi; khóa nghiệp vụ, transaction, quản lý lịch retry và trạng thái phải được thiết kế nhất quán. Nếu ứng dụng cần theo dõi phát thư sau bước nộp SMTP thì phải cập nhật thêm trạng thái từ provider.

Outbox giúp không mất **ý định gửi** sau khi commit, nhưng không biến SMTP thành giao dịch nguyên tử với database và không loại bỏ hoàn toàn khả năng gửi trùng. Sau khi provider chấp nhận thư nhưng trước khi worker đánh dấu đã gửi, tiến trình vẫn có thể dừng. Thiết kế vì thế cần chấp nhận hoặc giảm thiểu trường hợp retry mơ hồ.

### Vậy chỉ dùng @Async có đủ không?

Đánh dấu phương thức gửi mail bằng **@Async** (với cơ chế async Spring được cấu hình đúng) có thể chuyển lời gọi SMTP sang executor khác, giúp HTTP request không trực tiếp chờ kết quả. Đây là một cải thiện về **độ trễ request**.

Tuy vậy, task nằm trong bộ nhớ executor có thể mất khi tiến trình dừng; executor cũng có thể hết chỗ, và exception của công việc nền cần được xử lý/quan sát riêng. **@Async không tự cung cấp lưu trữ bền vững, retry, idempotency hay theo dõi trạng thái phát thư.** Nếu hậu quả của việc mất yêu cầu gửi là đáng kể, nên cân nhắc hàng đợi bền vững, outbox hoặc dịch vụ quản lý công việc gửi.

### Chọn cách tiếp cận theo yêu cầu

| Cách làm | Phù hợp khi | Giới hạn chính |
| --- | --- | --- |
| Gọi send(...) trực tiếp | Công cụ nội bộ, thao tác thử nghiệm, khối lượng nhỏ và người gọi chấp nhận chờ/lỗi | Độ trễ và sự cố SMTP gắn trực tiếp vào request |
| @Async / executor trong tiến trình | Muốn giảm chờ của request, có thể chấp nhận mất task khi tiến trình dừng | Không bảo đảm lưu trữ và phục hồi công việc |
| Hàng đợi bền vững hoặc outbox + worker | Thư gắn với sự kiện nghiệp vụ quan trọng, cần retry và trạng thái rõ ràng | Phải vận hành worker, chính sách gửi trùng và giám sát |
| Nhà cung cấp email có API, hàng đợi, event | Cần điều tiết, thống kê hoặc theo dõi sau bước nộp thư | Vẫn phải xử lý lỗi mạng, trạng thái bất đồng bộ và chính sách nhà cung cấp |

Các lựa chọn có thể kết hợp: ví dụ ghi outbox trong transaction, worker lấy công việc rồi sử dụng JavaMailSender hoặc API của provider để gửi. Công cụ gửi và cơ chế bảo đảm lưu công việc là **hai trách nhiệm khác nhau**.

## 8. Thiết kế phản hồi API và trạng thái nghiệp vụ đúng với thực tế

Khi người dùng bấm “Đăng ký”, việc ứng dụng xử lý thành công tài khoản và việc email đã phát thành công không xảy ra cùng một thời điểm. Vì vậy:

- Nếu transaction tạo tài khoản và ghi outbox đã commit, phản hồi có thể thông báo **đã tạo tài khoản và đã ghi nhận yêu cầu gửi email**.
- Nếu một API chỉ tiếp nhận yêu cầu gửi email để xử lý nền, có thể dùng **HTTP 202 Accepted** khi đúng với hợp đồng API; mã này không hứa rằng email đã đến người nhận.
- Nếu email có vai trò xác minh, giao diện nên nói rõ **đang chờ xác minh**, có lựa chọn gửi lại phù hợp và giới hạn chống lạm dụng.
- Nếu có nhu cầu hiển thị trạng thái, nên phân biệt ít nhất **PENDING**, **SUBMITTING**, **SUBMITTED**, **FAILED**; chỉ thêm **DELIVERED** khi có tín hiệu đáng tin cậy ở mức tương ứng.
- Không đưa thông tin xác thực SMTP, dữ liệu riêng tư hoặc token nhạy cảm vào log lỗi và không trả nguyên văn exception từ provider cho người dùng cuối.

Nên đo lường tỷ lệ công việc chờ, thời gian từ lúc tạo sự kiện tới lần thử đầu tiên, tỷ lệ gửi bị lỗi, số lần retry, số việc tồn lâu và tín hiệu bounce khi có. Những chỉ số này cho biết hệ thống mail đang ảnh hưởng đến nghiệp vụ thế nào, thay vì chỉ ghi log một dòng “send succeeded”.

## 9. Tự suy luận qua một tình huống

Một người dùng đăng ký tài khoản. Dữ liệu đã lưu thành công. Trong lúc gửi thư xác minh, kết nối bị timeout. Người dùng thấy màn hình báo lỗi và nhấn “Đăng ký” lần nữa.

Với thiết kế **gửi đồng bộ và không lưu trạng thái gửi**, ta chưa thể trả lời chắc chắn: tài khoản đầu tiên đã được tạo chưa, provider đã nhận thư chưa, có bao nhiêu thư sẽ tới và lần nhấn thứ hai có tạo thêm tác vụ nào không. Các hệ thống tham gia đã hoàn thành những phần việc khác nhau, nhưng ứng dụng chỉ biểu diễn toàn bộ hành trình bằng một kết quả HTTP đơn giản.

Với thiết kế **tách trạng thái nghiệp vụ và công việc gửi**, ta có thể xác nhận tài khoản đã được lưu, tìm đúng bản ghi gửi theo khóa sự kiện, xem lịch sử thử gửi, lên lịch retry khi thích hợp và cho người dùng hành động tiếp theo phù hợp. Kết quả phát thư cuối cùng vẫn phụ thuộc hệ thống email, nhưng ứng dụng có dữ liệu để quản lý sự không chắc chắn đó.

**Điều cốt lõi cần hiểu khi học Spring Framework Mail:** **JavaMailSender.send(...)** là một thao tác gửi thông điệp qua hạ tầng mail tại một thời điểm, không phải lời hứa toàn bộ chuỗi “tạo dữ liệu → nộp thư → phát tới hộp thư → người nhận đọc” sẽ hoàn tất đồng bộ, đúng một lần và thành công cùng nhau. Mô hình ứng dụng tốt bắt đầu bằng việc đặt ranh giới chính xác cho lời gọi này, rồi thiết kế timeout, transaction, retry và trạng thái theo mức độ tin cậy mà nghiệp vụ yêu cầu.
