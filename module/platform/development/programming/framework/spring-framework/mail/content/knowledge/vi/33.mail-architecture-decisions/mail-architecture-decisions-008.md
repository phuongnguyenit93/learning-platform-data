# Chọn đồng bộ hay bất đồng bộ theo trải nghiệm người dùng

Trong **Spring Framework Mail**, một quyết định kiến trúc thường xuất hiện ngay khi sản phẩm thêm tính năng gửi email: **nên gọi JavaMailSender.send(...) ngay trong request của người dùng hay nhận yêu cầu rồi gửi bằng worker bất đồng bộ?**

Câu trả lời không chỉ phụ thuộc vào việc SMTP chậm hay nhanh. Người dùng cần nhận phản hồi nào, họ đang chờ một hành động gì, họ có thể đóng trang không, điều gì xảy ra nếu hệ thống gửi lỗi, và UI có thể nói thật đến đâu về trạng thái email? Đó mới là các yếu tố quyết định kiến trúc.

Ví dụ, khi người dùng đăng ký tài khoản, họ thường muốn giao diện xác nhận “Đã tiếp nhận yêu cầu xác minh” nhanh chóng, trong khi email có thể được gửi sau vài giây. Ngược lại, ở một công cụ nội bộ “Gửi thử email cấu hình”, người vận hành có thể muốn chờ SMTP trả kết quả ngay để biết credential hoặc kết nối có vấn đề. Với OTP đăng nhập, trải nghiệm còn có một ràng buộc quan trọng: email phải đến **đủ sớm để mã vẫn còn giá trị**, nhưng giữ HTTP request chờ SMTP không tự làm thư đến nhanh hơn.

Bài học thuộc chương **Quyết định kiến trúc** của **Spring Framework Mail**, trình bày cách chọn **đồng bộ, bất đồng bộ và mô hình kết hợp** theo trải nghiệm người dùng (UX), đồng thời bảo đảm đúng semantics của JavaMailSender, transaction, outbox, retry, API status, lỗi mạng, bảo mật và monitoring.

Một nguyên tắc xuyên suốt:

**“Hệ thống đã tiếp nhận yêu cầu”, “SMTP relay đã chấp nhận email” và “email đã đến hộp thư” là ba sự kiện khác nhau.** Chọn đồng bộ hay bất đồng bộ không được làm UI đánh đồng ba sự kiện đó.

## 1. Đồng bộ và bất đồng bộ thực sự nghĩa là gì?

**Gửi đồng bộ**: thread xử lý request thực hiện một lời gọi gửi mail và chờ kết quả trước khi trả phản hồi.

~~~text
Browser / Mobile app
        |
        | POST /send-mail
        v
HTTP controller
        |
        v
JavaMailSender.send(...)
        |
        v
SMTP server interaction
        |
        v
Return or exception
        |
        v
HTTP response to user
~~~

**Gửi bất đồng bộ**: request tiếp nhận ý định gửi và trả phản hồi trước khi SMTP submission hoàn tất. Một worker hoặc một thành phần khác thực hiện transport sau.

~~~text
Browser / Mobile app
        |
        | POST /send-mail
        v
HTTP controller
        |
        v
Persist mail request / durable outbox
        |
        v
COMMIT
        |
        v
HTTP 202 Accepted
        |
        +-------------------------+
                                  |
                                  v
                          Background worker
                                  |
                                  v
                          JavaMailSender.send(...)
                                  |
                                  v
                             SMTP relay
~~~

### 1.1. Đồng bộ là quan hệ về thời điểm chờ

Không phải cứ dùng JavaMailSender thì hệ thống “đồng bộ hoàn toàn” đến hộp thư. Lời gọi send có thể hoàn tất sau khi SMTP relay nhận message, trong khi quá trình delivery downstream tiếp tục diễn ra độc lập.

### 1.2. Bất đồng bộ có nhiều mức độ

- Gọi **@Async** trong cùng process.
- Đưa message qua **ExecutorChannel** hoặc local queue.
- Publish vào broker có durability phù hợp.
- Lưu **transactional outbox** rồi để scheduled worker gửi.
- Dùng nhà cung cấp email qua HTTP API với trạng thái xử lý riêng.

Không phải mọi hình thức bất đồng bộ đều chịu được restart hoặc process crash.

### 1.3. Đặt câu hỏi chính xác

Thay vì hỏi “gửi email sync hay async?”, hãy hỏi: **HTTP caller phải chờ đến mốc nào và chúng ta cần bảo đảm điều gì trước khi xác nhận thành công cho người dùng?**

## 2. Ba mốc trạng thái mà UI không được đánh đồng

Sơ đồ:

~~~text
A. Request accepted / persisted
             |
             v
B. SMTP submission completed
   (relay accepted or send returned normally)
             |
             v
C. Downstream delivery status
   (delivered, bounced, deferred, unknown)
             |
             v
D. Recipient read/open, if measurable
~~~

### 2.1. A: đã nhận yêu cầu

Ví dụ: database transaction chèn outbox event thành công. Hệ thống đã có trách nhiệm xử lý ý định gửi theo policy, nhưng mail chưa chắc rời khỏi ứng dụng.

### 2.2. B: kết quả của JavaMailSender.send

Khi **JavaMailSender.send(...)** trả bình thường, ứng dụng có thể ghi nhận **SMTP submit completed theo phía client**. Đây không phải chứng minh email đã vào inbox.

Nếu send ném exception, cũng không phải mọi trường hợp đều chứng minh relay **chưa** nhận message; timeout sau DATA là ví dụ quan trọng.

### 2.3. C: delivery downstream

Muốn biết bounced, deferred hoặc delivered, ứng dụng thường cần provider-specific webhook/API hoặc hệ thống xử lý bounce, với bảo mật và correlation phù hợp. Spring Mail không tự đem lại tín hiệu này.

### 2.4. D: người nhận mở thư

Ngay cả tracking pixel hoặc read receipt cũng không phải bằng chứng đáng tin cho mọi email client. Cần cẩn trọng về quyền riêng tư và không dùng “đã đọc” làm điều kiện xử lý quan trọng nếu không có hợp đồng riêng.

## 3. So sánh theo trải nghiệm người dùng

| Câu hỏi UX | Đồng bộ | Bất đồng bộ |
| --- | --- | --- |
| Người dùng có phải đợi SMTP không? | Có, nếu đặt send trên request path | Không nhất thiết |
| API có thể trả kết quả send ngay không? | Có thể trả caller-observed result | Thường chỉ trả accepted/queued |
| Nếu provider chậm, UI ra sao? | Loading lâu hoặc request timeout | UI phản hồi nhanh hơn, nhưng delivery chưa xong |
| Request có chịu network variability không? | Trực tiếp | Có thể tách khỏi request |
| Khó xử lý retry dài hạn không? | Khó nếu chỉ giữ thread | Phù hợp hơn với durable queue/outbox |
| Có tự bền qua restart không? | Không liên quan; send đang thực hiện có thể mất context | Chỉ khi dùng durable design |
| Có thể hiện progress/status không? | Thường chờ kết quả tại một điểm | Cần status resource/polling hoặc push nếu thật sự cần |
| Độ phức tạp hệ thống | Có thể ít lớp hơn | Cần queue, worker, state, retry, monitoring |
| Email chắc chắn vào inbox? | Không | Không |

### 3.1. Đồng bộ không mặc định đơn giản về nghiệp vụ

Nếu SMTP timeout sau DATA, HTTP request có thể báo lỗi dù relay đã accept. Người dùng nhấn “Gửi lại” và tạo duplicate. Dù code gọi send đơn giản, trải nghiệm có thể khó xử lý.

### 3.2. Bất đồng bộ không mặc định đáng tin cậy

Một **@Async void** không có durable state có thể làm request trả thành công trước khi worker chạy, rồi job biến mất khi process crash. Muốn reliability cần thiết kế thật.

## 4. Câu hỏi đầu tiên: người dùng đang chờ kết quả gì?

Một action gửi email có thể thuộc một trong ba nhóm UX:

1. **Primary action**: người dùng đang hoàn tất một nghiệp vụ chính, email chỉ là thông báo phụ. Ví dụ xác nhận đơn hàng.
2. **Email-dependent action**: người dùng cần email để làm bước tiếp theo. Ví dụ xác minh tài khoản, OTP.
3. **Operational send action**: người dùng muốn kiểm tra chính thao tác gửi. Ví dụ quản trị viên test SMTP connection/email.

### 4.1. Primary action không nên bị giữ bởi email không thiết yếu

Nếu đơn hàng đã được ghi nhận thành công, nhưng SMTP provider đang chậm, việc trả lỗi cho bước đặt hàng chỉ vì email xác nhận chưa gửi có thể khiến người dùng nhấn đặt lại và tạo order trùng.

### 4.2. Email-dependent action cần ưu tiên latency end-to-end

Với OTP, nếu email đến quá muộn, UX thất bại dù HTTP phản hồi rất nhanh. Async chỉ là một phần; còn cần priority queue, provider performance, TTL và cách resend hợp lý.

### 4.3. Operational action có thể phù hợp sync

Một nút “Gửi thử email đến hộp kiểm tra” có thể chờ phản hồi SMTP ngắn để cho phép người vận hành thấy lỗi AUTH/TLS ngay. Tuy nhiên vẫn phải nói rõ đây là **thử submit**, không phải bằng chứng inbox delivery.

## 5. Ma trận quyết định theo từng tình huống

| Tình huống | Thiên hướng kiến trúc | Phản hồi UX phù hợp |
| --- | --- | --- |
| Đặt hàng thành công, email xác nhận | Async qua outbox | “Đơn hàng đã được xác nhận; email thông báo đang được xử lý” |
| Đăng ký tài khoản và mail xác minh | Async bền vững, ưu tiên cao | “Nếu địa chỉ hợp lệ, chúng tôi sẽ gửi hướng dẫn xác minh” |
| Quên mật khẩu | Async bền vững, bảo mật anti-enumeration | Thông báo trung tính, không lộ tài khoản |
| OTP email cho đăng nhập | Async ưu tiên cao hoặc bounded sync tùy UX/SLO | Trạng thái gửi yêu cầu, đếm thời hạn theo mã thật |
| Gửi thử SMTP trong trang quản trị | Bounded sync có thể phù hợp | “SMTP đã chấp nhận yêu cầu thử” hoặc lỗi cấu hình |
| Gửi hóa đơn PDF | Async + snapshot nội dung | “Hóa đơn đang được chuẩn bị/gửi” |
| Báo cáo định kỳ qua email | Scheduled async | “Đã lên lịch”, theo dõi job status |
| Newsletter hàng chục nghìn recipients | Async worker/broker | “Chiến dịch đã được xếp hàng”, progress tổng hợp |
| Thông báo bảo mật nhạy cảm | Durable async với priority + alert | “Yêu cầu đã được ghi nhận”, không hứa inbox |
| Một công cụ nội bộ send-and-wait đơn giản | Sync có timeout rõ | Trả kết quả caller-observed và hướng dẫn xử lý |

### 5.1. Đây là định hướng chứ không phải luật cứng

Một ứng dụng cực nhỏ có thể gửi sync cho thông báo ít rủi ro. Một nền tảng yêu cầu độ sẵn sàng cao có thể cần async ngay cả với một mail đơn giản.

### 5.2. Ưu tiên theo lợi ích của người dùng

Nếu email không cần thiết để hoàn tất action chính, mặc định cân nhắc tách khỏi critical path. Nếu email là bước tiếp theo, tối ưu toàn bộ thời gian từ request đến khi người dùng có thể dùng email.

## 6. Đo độ trễ thực sự trước khi chọn

Các thành phần latency:

~~~text
T_total = T_validate
        + T_transaction
        + T_render
        + T_mime_build
        + T_queue_wait
        + T_smtp_submit
        + T_downstream_delivery
~~~

Đây là phân rã khái niệm; các thành phần có thể overlap trong kiến trúc song song.

### 6.1. Sync request latency

Nếu gọi JavaMailSender.send trên request thread, user-visible request duration chịu T_smtp_submit. Duration này có thể chứa DNS, TCP, STARTTLS, SMTP AUTH, serialize MIME, attachment I/O, DATA và server reply.

### 6.2. Async request latency

HTTP response có thể chỉ chờ validate và **commit durable intent**. Nhưng trải nghiệm nhận được mail vẫn chịu queue delay, worker, SMTP và downstream.

### 6.3. Tách p50, p95, p99

SMTP có thể nhanh ở p50 nhưng rất chậm ở p99 khi provider gặp timeout. Đừng chọn sync chỉ dựa trên một lần test gửi mail 200 ms trong môi trường phát triển.

### 6.4. Tail latency quan trọng với UI

Nếu 1% request phải đợi 20 giây, người dùng có thể nhìn thấy spinner hoặc timeout dù trung bình rất đẹp. Cần xem p95/p99, failure rate, request timeout và UX tolerance.

## 7. SLO và thời gian chờ của người dùng

Không có một “con số chuẩn” phù hợp mọi sản phẩm. Có thể định nghĩa các mục tiêu mẫu:

| Chỉ tiêu minh họa | Ý nghĩa | Ví dụ SLO do đội sản phẩm tự chọn |
| --- | --- | --- |
| API request acceptance | Tới lúc durable enqueue commit | p95 dưới 500 ms |
| SMTP submit-call | Thời gian mỗi attempt | p95 dưới 3 giây khi provider khỏe |
| Event-to-submit | Từ business event tới submit success | p95 dưới 30 giây |
| OTP usable time | Từ request đến lúc có thể nhập mã | Phần lớn trước khi TTL hết |
| Queue oldest age | Độ trễ event chờ lâu nhất | Cảnh báo khi vượt threshold |
| Manual SMTP test | Caller chờ tối đa | Bounded budget, ví dụ vài giây |

**Các giá trị chỉ là minh họa thiết kế**, không phải thông số mặc định hoặc cam kết của Spring Framework Mail.

### 7.1. SLO của API khác SLO của email

API trả 202 nhanh có thể đáp ứng UX responsiveness, nhưng email bị kẹt 20 phút vẫn là lỗi trải nghiệm. Phải theo dõi cả hai.

### 7.2. Không đo inbox delivery bằng SMTP success

Nếu mục tiêu là delivery thật, cần provider webhook/bounce feedback có độ tin cậy phù hợp. Không lấy JavaMailSender.send duration làm delivery latency.

### 7.3. Tính deadline theo nghiệp vụ

Mã OTP hết hạn sau 5 phút không nên nằm RETRY_WAIT 30 phút. Deadline phải ảnh hưởng retry policy và thứ tự ưu tiên.

## 8. Khi nào đồng bộ là lựa chọn hợp lý?

Sync có thể tốt khi:

- Hành động được thiết kế rõ là **“test mail transport”**.
- Người dùng cần biết ngay kết quả submit phía client để sửa cấu hình.
- Lưu lượng thấp, payload nhỏ, p99 SMTP có thể chấp nhận và timeout được kiểm soát.
- Không có nhu cầu retry dài hạn hoặc durability phức tạp.
- API không giữ một business transaction mở trong lúc gửi.
- Giao diện hiển thị đúng kết quả và biết cách xử lý khi kết quả không rõ.

### 8.1. Sync có chi phí UX

Một SMTP outage làm request chậm hoặc thất bại. Nếu nút gọi send có thể được nhấn lại, phải có idempotency hoặc chính sách resend để tránh duplicate.

### 8.2. Sync không bảo đảm mọi lỗi đều chắc chắn chưa gửi

Timeout sau SMTP DATA có thể tạo unknown outcome. API không nên luôn trả “chưa gửi, bạn hãy thử lại ngay”.

### 8.3. Sync nên có time budget

Các timeouts **mail.smtp.connectiontimeout**, **mail.smtp.timeout** và **mail.smtp.writetimeout** giúp tránh chờ I/O quá lâu ở từng giai đoạn. Chúng không nhất thiết tạo một overall deadline cho toàn bộ SMTP operation, nên phải quan sát tổng thời gian và đặt giới hạn phù hợp với môi trường chạy.

## 9. Ví dụ JavaMailSender dùng đồng bộ trong một service

Ví dụ một dịch vụ nội bộ có quyền hạn đã được kiểm tra từ tầng API:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class SmtpTestMailService {

    private final JavaMailSender sender;

    public SmtpTestMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void submitTestMail(String authorizedRecipient) {
        SimpleMailMessage mail =
                new SimpleMailMessage();

        mail.setFrom("operations@example.org");
        mail.setTo(authorizedRecipient);
        mail.setSubject("Kiểm tra kết nối gửi email");
        mail.setText(
                "Đây là email kiểm tra SMTP từ hệ thống."
        );

        sender.send(mail);
    }
}
~~~

Tầng controller có thể gọi service này và trả **SMTP_SUBMITTED** khi lời gọi hoàn tất bình thường, hoặc phản hồi lỗi được phân loại khi có exception.

### 9.1. Điều code bảo đảm

- Gọi send trên thread hiện tại.
- Nếu send trả bình thường, có thể ghi nhận submit-call success.
- Nếu ném MailException, cần xem cause/phase và phản hồi phù hợp.

### 9.2. Điều code không bảo đảm

- Recipient có mailbox thật.
- Email vào inbox.
- Không bị spam filtering.
- Người nhận đã mở thư.
- Không có duplicate trong tình huống mất final reply.

### 9.3. Không biến thành open mail relay

Không mở API công khai cho phép bất kỳ người dùng nào đặt To/From tùy ý. Kiểm tra authorization, rate limit, sender identity và recipient policy trước khi gọi service.

## 10. Phản hồi HTTP trong mô hình đồng bộ

Khi request chờ SMTP:

~~~text
POST /admin/mail-test
       |
       v
Authenticate + authorize
       |
       v
Send through SMTP
       |
       +-- send returned normally
       |      -> 200 OK + status SMTP_SUBMITTED
       |
       +-- known configuration failure
       |      -> controlled error + support action
       |
       +-- ambiguous timeout after DATA
              -> outcome UNKNOWN; avoid blind resend
~~~

HTTP **200** ở đây chỉ nói endpoint đã hoàn tất thao tác được nó công bố. Nếu API công bố “test SMTP submit”, dùng một trường status có nghĩa rõ là hợp lý.

### 10.1. Không trả “Delivered” chỉ vì send trả

Hãy dùng thông điệp như “Máy chủ gửi mail đã tiếp nhận yêu cầu” thay vì “Người nhận đã nhận email”.

### 10.2. UX khi lỗi timeout

Nếu không chắc email đã được chấp nhận, hiển thị “Không xác nhận được kết quả gửi; vui lòng kiểm tra trạng thái trước khi gửi lại” thay vì thúc giục click retry ngay.

### 10.3. Không expose raw SMTP errors cho end users

Provider reply text hoặc stack trace có thể chứa host, account và metadata. UI cho người dùng cuối nên có lỗi thân thiện; chi tiết kỹ thuật ở log/runbook có phân quyền.

## 11. Khi nào bất đồng bộ phù hợp hơn?

Async thường tốt khi:

- Email chỉ là thông báo sau một business action đã commit.
- SMTP latency và khả năng lỗi không nên ảnh hưởng đến phản hồi chính.
- Hệ thống có nhiều loại email, nhiều providers hoặc tải biến động.
- Có lịch gửi, retry, outbox, batch hoặc worker scaling.
- Cần đảm bảo ý định gửi không mất khi process restart.
- Có nhu cầu xử lý lỗi/đối soát ngoài request life cycle.
- Người dùng không cần nhìn thấy SMTP submit result ngay trong response.

### 11.1. Async trả nhanh nhưng phải minh bạch

Nếu API mới chỉ commit một outbox event, kết quả đúng là **QUEUED/ACCEPTED**, không phải **SENT**.

### 11.2. Async không nhất thiết là “gửi trễ”

Với worker capacity tốt, event được lấy gần như ngay sau commit. Async có thể cải thiện user-visible latency mà không làm email chậm đáng kể; phải đo thực tế.

### 11.3. Async không tự đồng nghĩa resilient

Executor trong memory, local queue hoặc @Async đơn thuần không đảm bảo job còn sau crash. Cần durability theo yêu cầu sản phẩm.

## 12. Ba mức bất đồng bộ và đánh đổi

| Mô hình | Phản hồi HTTP | Durability | Độ phức tạp |
| --- | --- | --- | --- |
| **@Async trong cùng JVM** | Trước khi send xong | Không tự bền qua restart | Thấp |
| **In-memory ExecutorChannel/QueueChannel** | Trước khi worker send | Không tự bền nếu không có message store | Trung bình |
| **Durable broker hoặc transactional outbox** | Sau khi enqueue/commit | Có thể bền theo cấu hình/transaction | Cao hơn |

### 12.1. @Async phù hợp tác vụ best-effort

Ví dụ một email không quan trọng, chấp nhận mất khi process dừng có thể dùng @Async để giảm thời gian chờ. Nhưng phải biết rằng request thành công không đồng nghĩa task đã được gửi.

### 12.2. Local queue không phải durable queue

ExecutorChannel chỉ chuyển dispatch sang executor; một QueueChannel thông thường trong memory không chịu được process crash. Nếu cần persistence, phải cấu hình message store/broker/outbox phù hợp.

### 12.3. Outbox phù hợp khi email quan trọng

Xác nhận đơn hàng, thông báo hóa đơn, cảnh báo bảo mật hoặc workflow đòi audit thường hưởng lợi từ durable event + retry policy và ownership rõ ràng.

## 13. Ví dụ dùng @Async và giới hạn của nó

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class BestEffortMailWorker {

    private final JavaMailSender mailSender;

    public BestEffortMailWorker(
            JavaMailSender mailSender
    ) {
        this.mailSender = mailSender;
    }

    @Async("mailExecutor")
    public void sendLater(SimpleMailMessage mail) {
        mailSender.send(mail);
    }
}
~~~

Ứng dụng cần bật async support và cấu hình **mailExecutor** có giới hạn threads/queue phù hợp.

### 13.1. @Async không tự tạo transaction commit ordering

Nếu gọi sendLater trong một @Transactional method trước khi commit, worker có thể chạy trong lúc database transaction nghiệp vụ chưa commit hoặc sau khi nó rollback. Phải thiết kế đúng ranh giới after-commit/outbox.

### 13.2. Exception không tự trở về HTTP caller

Một method @Async void có thể ném exception ở worker sau khi HTTP response đã trả. Cần exception handling, logging và state recording riêng.

### 13.3. Self-invocation là bẫy AOP

Trong Spring proxy-based async, gọi method @Async từ method khác **cùng instance** có thể bỏ qua proxy và chạy đồng bộ. Nên gọi qua Spring bean proxy hoặc dùng cơ chế dispatch rõ ràng.

### 13.4. Không mutate SimpleMailMessage sau khi publish

SimpleMailMessage có setters. Producer không nên sửa cùng object sau khi chuyển sang async worker; tạo một instance riêng cho mỗi yêu cầu.

## 14. Vì sao transactional outbox thường là điểm khởi đầu tốt cho email nghiệp vụ?

Mô hình:

~~~text
HTTP request
      |
      v
Business transaction
      |
      +-- Update order/account state
      +-- INSERT mail_outbox event
      |
      v
COMMIT
      |
      v
HTTP response: business success + email queued
      |
      v
Background scheduled worker
      |
      +-- Claim due outbox event
      +-- Render/build MIME
      +-- JavaMailSender.send(...)
      +-- Record result
      +-- Retry/reconcile if needed
~~~

### 14.1. Atomicity trong database

Business state và outbox intent có thể được commit trong **cùng một database transaction**. Nếu rollback, cả hai đều không tồn tại theo transaction đó.

### 14.2. SMTP nằm ngoài transaction

Worker gửi sau commit. Không giữ database transaction mở trong lúc SMTP socket đang chạy.

### 14.3. Outbox hỗ trợ recovery

Khi worker crash, event vẫn ở durable store. Có thể dùng claim lease, retry/backoff và terminal state để xử lý tiếp.

### 14.4. Outbox không tạo exactly-once SMTP

Nếu relay accept message rồi worker crash trước khi cập nhật SENT, event có thể được xử lý lại. Cần idempotent business intent, attempt history và policy cho **UNKNOWN_OUTCOME**.

## 15. Schema outbox cho phản hồi UX và worker

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    business_key VARCHAR(200) NOT NULL,
    mail_kind VARCHAR(64) NOT NULL,
    user_ref VARCHAR(200) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'QUEUED',
    payload_ref TEXT NOT NULL,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    deadline_at TIMESTAMPTZ,
    provider_alias VARCHAR(64),
    last_error_category VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(business_key, mail_kind)
);

CREATE INDEX idx_mail_outbox_due
    ON mail_outbox(status, next_attempt_at);
~~~

Đây là schema minh họa; claim ownership/version và bảng attempt history được bổ sung ở môi trường cần multi-worker và audit.

### 15.1. business_key chống tạo nhiều intents

Nếu client retry HTTP request vì mất phản hồi, ứng dụng có thể nhận lại cùng business key để trả về event đã tồn tại, thay vì tạo thêm email.

### 15.2. user_ref phục vụ quyền truy cập

Không cho người dùng truy vấn trạng thái email của người khác chỉ bằng cách đoán UUID. Endpoint tra status phải xác thực và authorize theo business resource/user_ref.

### 15.3. payload_ref phải được bảo vệ

Email cá nhân hóa có thể chứa OTP, reset URL, hóa đơn hoặc dữ liệu riêng tư. Payload reference và storage cần encryption/retention/access policy phù hợp.

### 15.4. Trạng thái UX và trạng thái internal có thể khác độ chi tiết

UI có thể chỉ cần “Đang xử lý”, “Đã chuyển tới hệ thống gửi”, “Cần thử lại”, trong khi worker cần lưu errorCategory, attemptCount, lease và provider.

## 16. Ví dụ transactional enqueue trong Spring

Một service minh họa:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderConfirmationUseCase {

    private final OrderRepository orders;
    private final MailOutboxRepository outbox;

    public OrderConfirmationUseCase(
            OrderRepository orders,
            MailOutboxRepository outbox
    ) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public UUID confirmAndQueueMail(
            UUID orderId,
            String authorizedUserId
    ) {
        Order order =
                orders.getOwnedOrder(
                        orderId,
                        authorizedUserId
                );

        order.confirm();

        String businessKey =
                "order_confirmed:" + orderId;

        return outbox.insertOrGetExisting(
                businessKey,
                "order_confirmation",
                authorizedUserId,
                order.mailPayloadReference()
        );
    }
}
~~~

**OrderRepository, MailOutboxRepository và Order** là các abstraction ứng dụng. Ví dụ nhấn mạnh **business update và enqueue cùng transaction**, không phải bộ API Spring Mail có sẵn.

### 16.1. Đặt business key phù hợp

Nếu một đơn hàng có thể được xác nhận nhiều lần hợp lệ hoặc gửi nhiều thông báo phiên bản khác nhau, business key cần chứa version/event type để không vô tình suppress email mới.

### 16.2. Không gửi SMTP trong transaction

Use case ở trên **không gọi JavaMailSender.send**. Worker chỉ xử lý event sau commit.

### 16.3. Phản hồi HTTP sau commit

Khi service return và transaction commit thành công, API có thể xác nhận ý định gửi đã được lưu. Nếu commit thất bại, không được báo 202 accepted.

## 17. REST API 202 Accepted cho xử lý bất đồng bộ

Ví dụ controller:

~~~java
import java.net.URI;
import java.security.Principal;
import java.util.UUID;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderConfirmationController {

    private final OrderConfirmationUseCase useCase;

    public OrderConfirmationController(
            OrderConfirmationUseCase useCase
    ) {
        this.useCase = useCase;
    }

    @PostMapping("/{orderId}/confirm")
    public ResponseEntity<MailQueueReceipt> confirm(
            @PathVariable UUID orderId,
            Principal principal
    ) {
        UUID eventId = useCase.confirmAndQueueMail(
                orderId,
                principal.getName()
        );

        URI statusUri = URI.create(
                "/api/mail-requests/" + eventId
        );

        return ResponseEntity
                .accepted()
                .location(statusUri)
                .body(
                        new MailQueueReceipt(
                                eventId,
                                "QUEUED"
                        )
                );
    }
}

record MailQueueReceipt(
        UUID mailEventId,
        String state
) {}
~~~

Ví dụ này giả định đã có authentication và authorization đúng cho order. Một số ứng dụng nên trả **200/201** cho nghiệp vụ xác nhận đơn hàng chính và mô tả email như một side effect đã được enqueue, thay vì buộc 202 chỉ vì email chạy async.

### 17.1. 202 nói điều gì?

Theo ý nghĩa thông dụng của HTTP, **202 Accepted** cho biết request đã được nhận để xử lý, nhưng xử lý chưa chắc hoàn tất. Nó phù hợp khi chính action API cũng đang diễn ra bất đồng bộ.

### 17.2. Khi nào 200 hoặc 201 hợp lý hơn?

Nếu nghiệp vụ chính (ví dụ xác nhận đơn hàng) đã hoàn tất trong database, trả **200 OK** hoặc **201 Created** tùy resource semantics có thể đúng hơn. Email queued chỉ là thuộc tính phụ, không nhất thiết khiến cả HTTP action trở thành 202.

### 17.3. Không trả 202 trước khi durable enqueue thành công

Nếu outbox INSERT chưa commit nhưng API đã báo accepted, người dùng có thể tưởng yêu cầu đã được ghi nhận dù nó bị rollback sau đó.

### 17.4. Location header có thể hữu ích

Endpoint GET status theo URI được trả về cho phép UI đối chiếu. Phải có authorization; không thể chỉ dựa vào việc ID khó đoán.

## 18. API đọc trạng thái và mapping cho UI

Một endpoint tra status có thể trả:

~~~json
{
  "mailEventId": "a14d9009-20b9-4983-bdef-340074d410dc",
  "state": "PROCESSING",
  "lastUpdatedAt": "2026-11-12T09:05:00Z",
  "canRequestResend": false
}
~~~

Các state nội bộ:

~~~text
QUEUED
PROCESSING
RETRY_WAIT
SMTP_SUBMITTED
FAILED
UNKNOWN_OUTCOME
CANCELLED
~~~

### 18.1. Không expose raw internal states nếu gây hiểu nhầm

UI có thể map:

| Internal state | Thông điệp UX |
| --- | --- |
| QUEUED | Yêu cầu đã được tiếp nhận |
| PROCESSING | Đang xử lý gửi email |
| RETRY_WAIT | Việc gửi đang bị trì hoãn, hệ thống sẽ thử lại nếu phù hợp |
| SMTP_SUBMITTED | Email đã được chuyển tới hệ thống gửi |
| FAILED | Không thể hoàn tất gửi; có hướng xử lý |
| UNKNOWN_OUTCOME | Chưa xác nhận được kết quả, vui lòng kiểm tra |
| CANCELLED | Yêu cầu gửi đã được hủy nếu chưa thực hiện |

### 18.2. SMTP_SUBMITTED không phải DELIVERED

Nếu UI nói “Đã gửi”, nên có tooltip/copy rõ đây là mốc submission. Với nghiệp vụ cần delivery, bổ sung sự kiện downstream riêng.

### 18.3. canRequestResend phải là policy phía server

Không chỉ bật nút dựa trên trạng thái client. Backend phải quyết định resend có được phép, có rate limit, deadline và idempotency phù hợp không.

## 19. UX copy đúng với từng mốc

Những thông điệp cụ thể:

| Trạng thái thật | Nên hiển thị | Tránh hiển thị |
| --- | --- | --- |
| Durable queued | “Yêu cầu gửi đã được ghi nhận” | “Email đã tới hộp thư” |
| SMTP returned OK | “Đã chuyển email tới máy chủ gửi” | “Người nhận đã đọc thư” |
| Retry scheduled | “Đang gặp gián đoạn, chúng tôi sẽ thử lại” | “Gửi thất bại vĩnh viễn” |
| Permanent failure | “Không thể gửi; vui lòng kiểm tra địa chỉ hoặc liên hệ hỗ trợ” | “Thử lại liên tục sẽ được” |
| Unknown after DATA | “Chưa xác nhận được kết quả gửi” | “Chắc chắn chưa gửi; nhấn lại ngay” |
| Provider delivered event | “Nhà cung cấp báo đã chuyển phát” | “Người nhận chắc chắn đã đọc” |

### 19.1. Không có spinner vĩnh viễn

UI cần giới hạn chờ, có thể đóng trang, quay lại kiểm tra hoặc nhận thông báo khác; không giữ một kết nối chờ vô hạn cho SMTP.

### 19.2. Trạng thái phục vụ quyết định người dùng

Nếu user không cần thao tác tiếp, hiển thị “Đã ghi nhận yêu cầu” và tiếp tục luồng chính thường tốt hơn một trang tiến độ nhiều bước.

### 19.3. Không tạo kỳ vọng không thể bảo đảm

Ngay cả provider webhook delivered có thể chỉ phản ánh hệ thống đích chấp nhận message. Cần tránh dùng ngôn ngữ mạnh hơn dữ liệu thực sự chứng minh.

## 20. UX cho quên mật khẩu và chống dò tài khoản

Một API quên mật khẩu không nên trả:

~~~text
404 "Email này chưa đăng ký"
~~~

trong khi với email tồn tại thì trả “Đã gửi”, vì sự khác biệt có thể cho phép dò danh sách tài khoản.

### 20.1. Phản hồi trung tính

Thông điệp gợi ý:

~~~text
Nếu địa chỉ email được liên kết với một tài khoản,
chúng tôi sẽ gửi hướng dẫn đặt lại mật khẩu.
~~~

Hành vi HTTP timing, rate limiting và lỗi cũng phải được thiết kế để giảm rò rỉ thông tin qua side channels.

### 20.2. Có thể enqueue async cho account tồn tại

Request xử lý input, áp dụng abuse controls và tạo outbox intent khi phù hợp. UI không cần tiết lộ liệu intent đã được tạo.

### 20.3. Không để retry gửi token hết hạn

Mail job cần deadline gắn với token lifecycle. Nếu SMTP outage kéo dài quá TTL, nên dừng và để người dùng tạo yêu cầu mới.

### 20.4. Resend cần throttle

Nút “Gửi lại” phải có cooldown/limit phía server và chiến lược tránh tạo nhiều tokens/emails cùng lúc.

## 21. UX cho OTP: nhanh không đồng nghĩa đồng bộ

Với OTP qua email, người dùng thường mong mã đến trong một thời gian ngắn. Hai hướng:

**Option A: sync/bounded wait**

~~~text
User requests OTP
      |
      v
Generate and store challenge
      |
      v
Try SMTP submission during request
      |
      v
Return submission outcome if within budget
~~~

**Option B: durable async**

~~~text
User requests OTP
      |
      v
Persist challenge + outbox intent
      |
      v
Return accepted quickly
      |
      v
High-priority worker submits
      |
      v
User receives code later
~~~

### 21.1. Lựa chọn theo end-to-end measurable SLO

Nếu high-priority async worker luôn xử lý nhanh, nó có thể tốt hơn sync vì API không bị kẹt khi provider timeout. Nếu sản phẩm cần hiển thị lỗi cấu hình ngay, có thể dùng mô hình khác. Đo thời gian **request → usable code**, không chỉ latency HTTP.

### 21.2. TTL tính từ mốc phù hợp

Nếu OTP hết hạn 2 phút từ lúc sinh và queue delay 90 giây, user chỉ còn rất ít thời gian. Có thể cần phát hành challenge theo lifecycle kiểm soát hoặc không submit OTP đã hết hạn.

### 21.3. Không để nút resend tạo cạnh tranh vô hạn

Rate limit theo tài khoản, địa chỉ hoặc risk profile, deduplicate challenge thích hợp, và không khẳng định lần trước chưa gửi nếu outcome unknown.

### 21.4. Không tiết lộ OTP trong status API

Status chỉ cho biết tiến độ và thông tin không nhạy cảm. Không đưa OTP hoặc signed reset URL vào response/log/tracing.

## 22. UX cho xác nhận đơn hàng

Một checkout thành công thường có hai mốc:

1. Order state đã commit.
2. Email confirmation được xử lý.

Nếu gọi SMTP đồng bộ ngay trong transaction:

~~~text
BEGIN database transaction
    |
    +-- Save confirmed order
    |
    +-- SMTP send
    |
    +-- Database commit fails
    |
    v
Customer may receive an email
for an order that was rolled back
~~~

### 22.1. Transactional outbox

Thay vào đó, commit order và outbox event trong cùng transaction. API xác nhận nghiệp vụ chính, email được xử lý sau.

### 22.2. Phản hồi UX nên phân cấp

Ví dụ “Đơn hàng đã được xác nhận. Chúng tôi sẽ gửi email thông tin tới địa chỉ đã đăng ký.” Không biến một lỗi SMTP tạm thời thành “Đặt hàng thất bại”.

### 22.3. Không gửi trùng do client retry request

Nếu request xác nhận đơn hàng bị timeout trước khi client nhận response, client có thể gửi lại. Cần idempotent order confirmation và outbox business key, không tạo nhiều mail intents.

## 23. UX cho hóa đơn và attachment lớn

Một hóa đơn PDF có thể cần:

- Đọc dữ liệu nghiệp vụ.
- Render PDF.
- Lưu file có quyền truy cập.
- Dựng MIME multipart.
- Truyền attachment qua SMTP.
- Retry khi provider tạm lỗi.

### 23.1. Async thường phù hợp

Người dùng có thể được chuyển tới trang hóa đơn hoặc tải PDF trực tiếp trong web, trong khi email gửi sau. Không cần giữ HTTP request chờ đọc file, render và SMTP.

### 23.2. Attachment có thể được đọc muộn

Khi dùng MimeMessageHelper.addAttachment với resource, dữ liệu có thể được đọc trong lúc serialize/send. Send-call duration có thể chứa I/O file, không chỉ network latency.

### 23.3. Snapshot giúp retry nhất quán

Nếu invoice thay đổi sau lần submit đầu, retry từ dữ liệu live có thể phát ra nội dung khác. Chọn version/snapshot policy rõ.

### 23.4. File lớn cần capacity planning

Kiểm soát message size, quota, memory, streaming và attachments; không mặc định @Async giải quyết giới hạn provider.

## 24. UI trạng thái: polling, SSE, WebSocket hay không cần?

Một API async có thể trả eventId và URI trạng thái. UI có thể:

- **Không theo dõi**: khi email chỉ là thông báo phụ.
- **Polling GET status**: khi cần cập nhật đơn giản.
- **Server-Sent Events (SSE)**: khi cần server đẩy trạng thái một chiều.
- **WebSocket**: khi ứng dụng đã có nhu cầu real-time hai chiều.
- **Push/in-app notification**: khi người dùng có thể rời trang.

### 24.1. Đừng thêm WebSocket chỉ vì có async email

Với một email confirmation, không phải lúc nào người dùng cũng cần tiến độ. Thêm real-time infrastructure có thể tăng complexity không cần thiết.

### 24.2. Polling cần giới hạn và backoff

Không cho hàng chục nghìn clients gọi status mỗi 100 ms liên tục. Có thể polling theo nhịp thưa, dừng khi terminal hoặc khi user rời flow.

### 24.3. SSE/WebSocket vẫn cần durable source

Nếu server restart, một push event có thể bị lỡ. Status endpoint dựa trên database giúp client đồng bộ lại.

### 24.4. Progress phải phản ánh mốc thật

Không hiển thị “90% delivered” chỉ vì SMTP socket đã truyền 90% byte. Email delivery không có progress % chuẩn như upload file.

## 25. Mô hình kết hợp: trả nhanh nhưng chờ có giới hạn

Có những sản phẩm muốn phản hồi nhanh nếu SMTP hoàn tất trong một khoảng nhỏ, nhưng không muốn request chờ lâu khi provider chậm.

Một mô hình **bounded wait**:

~~~text
HTTP request
     |
     v
Durable enqueue and commit
     |
     v
Trigger worker
     |
     v
Wait briefly for recorded submit status
     |
     +-- worker finishes within budget
     |       -> return observed submit status
     |
     +-- still processing
             -> return accepted + status URL
~~~

### 25.1. Phải enqueue bền vững trước khi đợi

Nếu request đã timeout trong lúc chờ worker, outbox event vẫn tồn tại và có thể được xử lý tiếp. Tránh mất intent khi caller disconnect.

### 25.2. Không chờ bằng busy polling

Nếu muốn bounded wait, cân nhắc completion signal/future có timeout hoặc polling có giới hạn. Không spin liên tục trên database.

### 25.3. Cần xử lý race và disconnect

Worker có thể hoàn thành ngay sau thời hạn HTTP wait. API đã trả 202, client vẫn có thể GET status để thấy SMTP_SUBMITTED.

### 25.4. Bounded wait phức tạp hơn cả hai cực

Mô hình này có thêm state coordination và edge cases, chỉ nên chọn nếu UX thực sự hưởng lợi từ kết quả submit nhanh khi có sẵn.

## 26. HTTP status cần phản ánh contract của endpoint

Một bảng thực dụng:

| HTTP outcome | Khi có thể phù hợp | Lưu ý |
| --- | --- | --- |
| **200 OK** | Nghiệp vụ hoàn tất hoặc sync operation đã có result | Định nghĩa rõ điều gì hoàn tất |
| **201 Created** | Tạo resource mới theo REST contract | Có thể là mail-request resource |
| **202 Accepted** | Yêu cầu đã được nhận để xử lý async | Không khẳng định SMTP xong |
| **400 Bad Request** | Input không hợp lệ theo public contract | Tránh account enumeration |
| **401/403** | Chưa xác thực/không có quyền | Không để endpoint thành open relay |
| **409 Conflict** | Action xung đột với state hiện tại | Không dùng cho mọi duplicate retry |
| **429 Too Many Requests** | Rate limit của API | Khác SMTP provider throttling |
| **5xx** | Hệ thống không tiếp nhận/xử lý được theo contract | Không mặc định có nghĩa email chưa gửi |

### 26.1. 202 phải có khả năng theo dõi hoặc semantics rõ

HTTP 202 không bắt buộc phải có status endpoint theo mọi protocol usage, nhưng với UX quan trọng, **Location/status URL** rất hữu ích để người dùng không phải đoán.

### 26.2. SMTP 421 không phải HTTP 421

Các mã SMTP và HTTP thuộc hai giao thức khác nhau. Không ánh xạ trực tiếp reply code 421/450/550 của SMTP thành HTTP status cùng số.

### 26.3. HTTP timeout cũng có ambiguous result

Client có thể timeout sau khi server đã commit outbox. Khi client retry, backend phải dùng idempotency/business key để trả event cũ, tránh tạo intent mới.

## 27. Idempotency cho API và email intent

Giả sử user nhấn “Gửi hóa đơn”, trình duyệt mất response và tự retry:

~~~text
Request 1:
    Server commits mail event E
    HTTP response lost

Request 2:
    Same business operation
    Without dedup -> mail event F
~~~

Nếu không có idempotency, hệ thống có thể gửi hai email dù user chỉ có một ý định.

### 27.1. Business key

Có thể dùng:

~~~text
invoice_send:invoice-1001:version-2:recipient-42
~~~

để biểu diễn cùng một ý định gửi. Unique index trong outbox ngăn insert duplicate cho event tương ứng.

### 27.2. Client idempotency key

Một số APIs cho client gửi Idempotency-Key; server lưu mapping khóa tới kết quả/request. Phải gắn với identity, scope và TTL phù hợp để tránh một client dùng lại khóa cho action khác.

### 27.3. Idempotent enqueue không tạo exactly-once SMTP

Nó giảm duplicated intent ở tầng API. Worker vẫn có thể phải retry transport sau crash và tạo duplicate side effect khi outcome unknown.

## 28. Resend UX: khi nào cho phép nhấn lại?

Một nút “Gửi lại” hữu ích nhưng dễ tạo duplicate, spam và abuse.

### 28.1. Chỉ dựa vào client cooldown là không đủ

Nút disabled 30 giây trong frontend không ngăn một script gửi nhiều requests. Cần server-side rate limit và policy.

### 28.2. Phân biệt gửi lại và thử tiếp

- **Retry background**: tiếp tục cùng event theo policy.
- **Manual resend**: user chủ động tạo một intent hoặc attempt theo contract và audit.
- **Unknown result**: có thể cần đối soát trước khi cho phép.

### 28.3. Cảnh báo người dùng nếu kết quả chưa rõ

Ví dụ: “Yêu cầu trước chưa xác nhận được kết quả. Kiểm tra trạng thái trước khi gửi lại để tránh nhận nhiều email.”

### 28.4. Không cho resend token đã hết hạn

Nếu reset/OTP token cũ không còn hợp lệ, nghiệp vụ có thể cần tạo challenge mới một cách kiểm soát, không requeue một email cũ vô dụng.

## 29. Transaction boundary: email không rollback theo database

Một anti-pattern:

~~~java
@Transactional
public void placeOrder(OrderCommand command) {
    orderRepository.save(command.toEntity());
    javaMailSender.send(
            buildConfirmationMail(command)
    );
}
~~~

Nếu SMTP relay đã nhận message rồi database commit fail, user có thể nhận xác nhận cho một order không tồn tại. Nếu SMTP fail rồi transaction rollback, order có thể không được lưu dù business requirement không phụ thuộc email.

### 29.1. Tách thời điểm commit

Với transactional outbox, business state và mail intent được commit cùng nhau; SMTP send chạy sau.

### 29.2. AFTER_COMMIT listener là một lựa chọn nhẹ

**@TransactionalEventListener(phase = AFTER_COMMIT)** có thể tránh gửi trước commit trong một process, nhưng không tự durable trước crash sau commit và trước khi event listener hoàn tất.

### 29.3. Async không tự sửa transaction semantics

Đổi lời gọi sender sang @Async có thể khiến email được gửi **trước** commit hoặc mất khi restart. Vấn đề là ranh giới business commit và durable intent, không chỉ thread.

## 30. Durable outbox và worker state machine

Một state machine:

~~~text
QUEUED
   |
   v
PROCESSING (claimed)
   |
   +-- submit returned normally -> SMTP_SUBMITTED
   |
   +-- known retryable failure -> RETRY_WAIT
   |
   +-- permanent failure -> FAILED
   |
   +-- ambiguous after DATA -> UNKNOWN_OUTCOME
   |
   +-- worker crash -> recovery by lease/policy
~~~

### 30.1. Retry phải phân loại lỗi

- Invalid address: thường dừng và sửa dữ liệu.
- AUTH/TLS misconfiguration: thường cần operator/config fix.
- SMTP temporary 4xx: có thể backoff.
- Provider throttling: giới hạn throughput và dùng provider-aware delay.
- Timeout sau DATA: cần unknown/reconciliation policy.

### 30.2. Retry budget và deadline

Có **maxAttempts, exponential backoff, jitter, nextAttemptAt và deadline** theo mailKind. Không retry mãi khi người dùng không còn cần email.

### 30.3. Một lần send không phải một lần delivered

Đếm SMTP attempts tách unique mail events. Một event có thể có hai attempts, một failure rồi một success.

## 31. Multi-worker và distributed coordination

Nếu triển khai nhiều instances:

~~~text
Application A @Scheduled ----+
                             |
                             v
                         mail_outbox
                             ^
                             |
Application B @Scheduled ----+
~~~

Chỉ dùng @Scheduled không ngăn cả hai cùng đọc PENDING.

### 31.1. Atomic claim

Database UPDATE có điều kiện hoặc **SELECT ... FOR UPDATE SKIP LOCKED** (PostgreSQL) có thể giúp worker claim những rows khác nhau trong transaction ngắn.

### 31.2. Lease và stale owner

Lưu claimOwner, claimUntil, token/version; khi update SMTP_SUBMITTED/RETRY_WAIT cần kiểm tra vẫn là owner hợp lệ. Worker cũ không được ghi đè state khi lease đã hết.

### 31.3. Không giữ row lock khi gọi SMTP

Claim và commit trước, gửi sau; không kéo dài database transaction qua network call.

### 31.4. Lock không bảo đảm exactly-once SMTP

Nếu relay đã accept DATA trước khi worker crash, worker mới có thể gửi lại. Fencing bảo vệ database state, không buộc SMTP server từ chối message trùng.

## 32. Điều gì xảy ra khi HTTP client rời trang?

Với sync:

~~~text
Client disconnects
      |
      v
Server may still be in SMTP send
      |
      v
Result may complete or fail later
~~~

Với durable async:

~~~text
Client disconnects
      |
      v
Outbox event remains durable
      |
      v
Worker continues
~~~

### 32.1. Client disconnect không phải cancellation của SMTP

Đóng tab không tự động hủy một lời gọi gửi đang diễn ra. Khi đã truyền DATA, thậm chí cố hủy cũng có nguy cơ outcome ambiguous.

### 32.2. Async giúp tách người dùng khỏi công việc dài

Người dùng có thể tiếp tục sử dụng ứng dụng; ý định gửi vẫn được xử lý. Đây là lợi ích UX lớn với email không đòi đồng bộ.

### 32.3. Nếu cung cấp cancel

Chỉ hứa hủy khi event chưa bị SMTP submit hoặc khi hệ thống có đủ kiểm soát. Hủy lúc PROCESSING có race; “cancel requested” có thể khác “cancel completed”.

## 33. Queue depth, priority và fairness ảnh hưởng UX

Async có thể phản hồi HTTP nhanh nhưng backlog lớn khiến email quan trọng đến muộn.

### 33.1. Tách priority

Ví dụ:

~~~text
High: password reset / login verification
Medium: order confirmation / invoice
Low: marketing newsletter / digest
~~~

Đây là priority policy gợi ý, không phải thứ tự bắt buộc mọi sản phẩm.

### 33.2. Tránh starvation

Nếu worker luôn ưu tiên high queue và traffic security quá lớn, medium/low có thể không bao giờ được xử lý. Cần fair scheduling/weighted queues và deadline.

### 33.3. Tách provider quota

Một provider có rate limit khác provider khác. Worker concurrency và route policy cần phù hợp quota, không chỉ tăng threads.

### 33.4. UX của queued state cần phản ánh backlog

Nếu hệ thống đã biết email sẽ chậm, có thể hiển thị “Đang xử lý, có thể mất thêm thời gian” hoặc dùng kênh thông báo thay thế khi đó là nhu cầu chính đáng.

## 34. Tại sao không dùng async để giấu lỗi?

Một thiết kế kém:

~~~text
POST /send
    |
    v
Enqueue to in-memory task
    |
    v
HTTP 200 "Email đã gửi"
    |
    v
Worker throws exception
    |
    v
Task lost, no status, no retry, no alert
~~~

Giao diện trông nhanh nhưng lời hứa với người dùng không đúng.

### 34.1. Chọn status trung thực

HTTP response khi enqueue không được hiển thị “email delivered”. Backend phải có đường ghi lỗi async vào outbox, DLQ hoặc error processing.

### 34.2. Không có status endpoint vẫn phải có monitoring

Nếu user không cần theo dõi, đội vận hành vẫn cần pending/retry/failed counters, alerts và runbook.

### 34.3. Không giấu failure bằng cách retry mãi

Một AUTH password sai không tự hết sau 10.000 retries. Chính sách phải có phân loại lỗi, giới hạn và terminal state.

## 35. UX và bảo mật của trạng thái gửi email

Status API có thể vô tình làm lộ thông tin:

- Email có được liên kết với tài khoản hay không.
- Người dùng đã thực hiện một giao dịch hay chưa.
- Recipient address hoặc Subject.
- Reset token hoặc verification URL.
- Provider/account nội bộ.
- Loại sự kiện bảo mật cụ thể.

### 35.1. Authorization theo resource owner

Một requestId khó đoán **không đủ** để cấp quyền đọc. API GET status cần xác thực và kiểm tra ownership/context hoặc một access token giới hạn quyền/hạn dùng.

### 35.2. Account enumeration

Với forgot-password, không trả status phân biệt “không có tài khoản” với “đã enqueue mail thật” cho người dùng chưa xác thực.

### 35.3. Không đưa secrets vào logs hoặc SSE

Mail body, signed links, OTP, credentials hoặc attachment content không nên đi vào message status events/log/tracing chỉ vì UI muốn tiến độ.

### 35.4. From/recipient validation

Một endpoint gửi email phải kiểm soát người nhận, sender identity, tenant/domain authorization và rate limits để không thành công cụ phát spam.

## 36. Observability: đo cả request và email lifecycle

Một bộ metric gợi ý:

| Metric | Đo gì? |
| --- | --- |
| **mail.api.accept.duration** | Từ HTTP request tới durable acceptance |
| **mail.outbox.queue.delay** | Event chờ trước khi worker bắt đầu |
| **mail.smtp.submit.call.duration** | Duration JavaMailSender.send |
| **mail.event.to.submit.duration** | Event created tới SMTP submitted |
| **mail.event.terminal.failures** | Business intents không thể submit |
| **mail.smtp.submit.attempts** | Actual transport attempts |
| **mail.smtp.unknown.outcomes** | Kết quả relay không chắc |
| **mail.outbox.ready.count** | Events đến hạn |
| **mail.outbox.oldest.pending.age** | Độ tuổi event chờ lâu nhất |
| **mail.outbox.retry.wait.count** | Events đang backoff |
| **mail.worker.active** | Worker concurrency |
| **mail.api.resend.requests** | Số lượt người dùng yêu cầu gửi lại |
| **mail.delivery.events** | Provider downstream events nếu tích hợp |

### 36.1. Không lấy API p95 thay email SLO

API 202 trong 100 ms nhưng mail chờ queue 5 phút không phải UX tốt cho OTP.

### 36.2. Không lấy SMTP p95 thay inbox delivery

SMTP submit-call nhanh không bảo đảm thư đến hộp thư nhanh. Nếu cần đo delivery, tích hợp tín hiệu provider và nêu giới hạn.

### 36.3. Labels có cardinality thấp

Dùng mailKind, providerAlias, outcome, priority. Không dùng email recipient, mailEventId, token hoặc raw Subject làm tags.

## 37. Structured logging và tracing theo ba mốc

Log khi durable enqueue:

~~~json
{
  "event": "mail.request.accepted",
  "mailEventId": "event-42",
  "mailKind": "order_confirmation",
  "state": "QUEUED"
}
~~~

Log khi SMTP attempt hoàn tất:

~~~json
{
  "event": "mail.smtp.attempt.finished",
  "mailEventId": "event-42",
  "attemptId": "attempt-2",
  "providerAlias": "smtp-primary",
  "outcome": "success",
  "durationMs": 950
}
~~~

Log khi provider báo downstream delivery:

~~~json
{
  "event": "mail.delivery.status.updated",
  "mailEventId": "event-42",
  "providerAlias": "smtp-primary",
  "deliveryState": "delivered"
}
~~~

### 37.1. Ba event không đồng nghĩa

Một queued event có thể không bao giờ submit. Một submitted event có thể bounce. Một delivered webhook cần được verify/authenticate theo provider contract.

### 37.2. Tracing qua outbox

Request trace và worker trace có thể cách nhau vài phút. Có thể dùng trace context/span links và mailEventId để nối, nhưng không dùng trace ID làm durable business key duy nhất.

### 37.3. Bảo vệ nội dung

Logs/traces chỉ nên chứa metadata đã được cho phép. Không dump MimeMessage hoặc SMTP AUTH transcript.

## 38. Tình huống: người dùng nhấn nút hai lần

Một người dùng gửi request, đợi spinner, thấy chưa có phản hồi và bấm tiếp.

### 38.1. Sync có thể tạo hai gửi thư

Request A đang chờ SMTP, request B cũng gọi sender. Cả hai có thể thành công và người nhận nhận hai email.

### 38.2. Async cũng có thể tạo hai intents

Nếu API enqueue vô điều kiện mỗi POST, hai requests tạo hai outbox rows.

### 38.3. Giải pháp

- Disable nút tạm thời ở UI để giảm click lặp.
- Backend idempotency/business key để chống request duplicate.
- Cooldown và rate limiting cho resend.
- Status URL rõ để người dùng tra thay vì bấm tiếp.
- Phân biệt resend chủ động với retry tự động.
- Khi outcome unknown, không tự tạo thêm send.

### 38.4. Frontend không phải nguồn bảo đảm duy nhất

Disable nút không chặn retry từ mạng, nhiều tabs hoặc script. Idempotency cần ở server.

## 39. Tình huống: provider outage trong giờ cao điểm

Giả sử:

~~~text
1000 users place orders in one minute
SMTP provider temporarily unavailable
~~~

**Thiết kế sync gắn email với checkout:**

- HTTP requests chờ SMTP timeout.
- Nhiều users tưởng checkout thất bại.
- Users nhấn lại, có nguy cơ tạo đơn trùng.
- Database connections/request threads bị tiêu thụ nhiều hơn.

**Thiết kế async outbox:**

- Order transaction commit và API phản hồi đúng nghiệp vụ.
- Outbox giữ mail confirmations.
- Worker phân loại provider outage, backoff và throttle.
- Dashboard báo retry backlog; mail gửi sau khi provider phục hồi theo policy.

### 39.1. Async không biến mất trách nhiệm gửi

Đội vận hành vẫn phải có alert oldest pending age, terminal failure và SLO. Không để backlog tăng mà không ai biết.

### 39.2. Không xả backlog đồng loạt khi provider phục hồi

Rate limiter, worker concurrency và retry jitter giúp tránh retry storm.

### 39.3. Nếu email là chức năng cốt lõi của sản phẩm

Một email marketing platform có thể cần xác nhận scheduling/dispatch semantics và progress chính xác, thay vì chỉ nói “đã gửi” khi lưu queue.

## 40. Tình huống: admin muốn “Gửi mail thử” ngay

Một quản trị viên cấu hình SMTP host, credentials, STARTTLS rồi bấm “Send test”.

### 40.1. Sync giúp phản hồi lỗi cấu hình trực tiếp

Ứng dụng có thể gọi JavaMailSender.send trong request bounded, rồi hiển thị “SMTP submission thành công” hoặc “Không thể xác thực”/“TLS certificate mismatch”.

### 40.2. Không cho admin chờ vô hạn

Đặt timeout và một overall request budget/UX fallback phù hợp. Nếu timeout nhưng kết quả sau DATA không chắc, không báo “chắc chắn chưa gửi”.

### 40.3. TestConnection và send test khác nhau

Một connection test có thể xác minh một phần kết nối/login, nhưng không chứng minh quyền gửi From cụ thể hoặc MIME message được relay chấp nhận. Test send là thao tác khác và có side effect.

### 40.4. Không dùng inbox arrival làm phản hồi đồng bộ bắt buộc

Ngay cả khi SMTP submit thành công, email có thể đến inbox sau đó. UI có thể hướng dẫn admin kiểm tra hộp thư và xem logs/provider status nếu cần.

## 41. Kiểm thử kiến trúc sync/async theo UX

Các nhóm test:

| Nhóm | Tình huống | Mong đợi |
| --- | --- | --- |
| Sync | Sender returns normally | API trả SMTP_SUBMITTED, không nói delivered |
| Sync | AUTH invalid | Lỗi kỹ thuật được phân loại, không lộ secret |
| Sync | SMTP timeout | Response trung thực về uncertainty |
| Sync | Slow provider | Timeout/budget và UX fallback phù hợp |
| Async | Durable enqueue success | API trả accepted và status URL |
| Async | Enqueue transaction rollback | API không báo accepted |
| Async | Worker success | Event QUEUED → SMTP_SUBMITTED |
| Async | Worker temporary failure | RETRY_WAIT với nextAttemptAt |
| Async | Worker permanent failure | FAILED + actionable reason |
| Async | Timeout after DATA | UNKNOWN_OUTCOME, không retry mù |
| Async | Worker crash | Event còn durable, recovery |
| Async | Client disconnect | Intent đã commit vẫn được xử lý |
| UX | Double-click/resend | Idempotency/cooldown phía server |
| UX | Forgot-password | Không leak existence của account |
| UX | OTP expired | Không gửi mã quá deadline |
| Multi-worker | Concurrent claim | Không có hai active owners hợp lệ |
| Observability | API fast, queue slow | Hai latency metrics phân biệt |
| Security | GET status của user khác | Forbidden/not found theo policy |

### 41.1. Unit tests không cần SMTP thật

Mock JavaMailSender để test service/controller/worker decisions. Dùng fake Clock và outbox repository stub cho timeout/deadline states.

### 41.2. Integration tests cần database thật khi dựa vào locks

Nếu production dùng PostgreSQL FOR UPDATE SKIP LOCKED, dùng PostgreSQL test engine (có thể qua Testcontainers) để test concurrent claims; mock không chứng minh DB locking semantics.

### 41.3. SMTP capture server

Dùng SMTP capture server trong môi trường test để xác nhận MIME content và submit mechanics mà không gửi thư production.

## 42. Ví dụ kiểm thử async response trước khi SMTP gửi

Một unit test service/controller minh họa với Mockito:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.security.Principal;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

class OrderConfirmationControllerTest {

    @Test
    void returnsAcceptedAfterDurableEnqueue() {
        OrderConfirmationUseCase service =
                mock(OrderConfirmationUseCase.class);

        UUID orderId = UUID.randomUUID();
        UUID mailEventId = UUID.randomUUID();

        when(service.confirmAndQueueMail(
                eq(orderId),
                eq("user-42")
        )).thenReturn(mailEventId);

        OrderConfirmationController controller =
                new OrderConfirmationController(service);

        Principal principal = () -> "user-42";

        var response = controller.confirm(
                orderId,
                principal
        );

        assertEquals(
                HttpStatus.ACCEPTED,
                response.getStatusCode()
        );

        assertNotNull(response.getBody());
        assertEquals(
                "QUEUED",
                response.getBody().state()
        );

        verify(service).confirmAndQueueMail(
                orderId, "user-42"
        );
    }
}
~~~

### 42.1. Test chứng minh gì?

Controller trả 202 và trạng thái QUEUED theo service contract, không mở SMTP connection. Nó không chứng minh outbox durable — transaction persistence cần integration test riêng.

### 42.2. Test absence of immediate send ở layer phù hợp

Nếu controller không inject JavaMailSender, code không có direct send dependency. Integration test có thể xác nhận worker xử lý sau commit với fake sender và outbox state phù hợp.

### 42.3. Test rollback

Nếu outbox insert fail/commit rollback, request không nên trả accepted. Dùng transaction integration test với database thực, không chỉ mock service return.

## 43. Ma trận ra quyết định nhanh

Khi cân nhắc một tính năng mới, trả lời:

| Câu hỏi | Nếu “Có” | Hướng nghĩ tới |
| --- | --- | --- |
| Email chỉ là side effect sau nghiệp vụ chính? | Có | Durable async |
| User cần biết SMTP submit result ngay? | Có | Bounded sync hoặc bounded wait |
| Provider p99 vượt UX budget? | Có | Async hoặc fallback rõ |
| Email phải sống qua restart? | Có | Outbox/broker durable |
| Email có deadline/TTL ngắn? | Có | High-priority async + SLO hoặc sync cân nhắc |
| Có hàng nghìn recipients? | Có | Async worker/batch |
| Có retry lâu hơn request timeout? | Có | Outbox nextAttemptAt |
| Có multi-node workers? | Có | Atomic claims/lease |
| Cần progress? | Có | Status resource/polling/push |
| Có account enumeration risk? | Có | Neutral UX response |
| Duplicate email gây hại? | Có | Idempotency + unknown outcome policy |
| SMTP error phải được admin sửa ngay? | Có | Sync diagnostic workflow |
| UI không cần biết gửi xong? | Có | Chỉ cần accepted copy + ops monitoring |

### 43.1. Tránh câu trả lời máy móc

Không phải cứ email thì async; cũng không phải cứ OTP thì sync. Quyết định phải bắt đầu từ **người dùng, thời gian chờ cho phép, reliability và trạng thái thực sự có thể xác nhận**.

### 43.2. Quyết định có thể khác trong cùng sản phẩm

Một hệ thống có thể dùng sync cho admin SMTP test, durable async cho order confirmation, high-priority async cho OTP và campaign queues cho newsletter.

## 44. Các anti-pattern trong quyết định sync/async

| Anti-pattern | Vấn đề | Cách xử lý |
| --- | --- | --- |
| Gọi SMTP trong @Transactional checkout | Email có thể gửi trước rollback | Business commit + outbox |
| 200 “Email delivered” khi send return | Sai semantics | SMTP_SUBMITTED |
| 202 khi queue chưa commit | Lời hứa không có durability | Commit rồi phản hồi |
| @Async void rồi bỏ lỗi | Email mất, không biết | Error state/monitoring |
| In-memory queue được gọi durable | Mất task sau restart | Durable store/broker |
| Chọn async chỉ để HTTP nhanh | Che backlog/provider outage | End-to-end SLO |
| Chọn sync vì “email quan trọng” | Request chậm, failure coupling | UX/latency/reliability analysis |
| Đồng bộ đợi inbox delivery | Không có guarantee | Separate downstream lifecycle |
| Spinner không timeout | UX bị kẹt | Bounded wait + status resource |
| Poll status mỗi 100 ms | Lãng phí tải | Backoff/polling có giới hạn |
| Để client tự quyết resend | Spam, duplicate | Backend policy/idempotency |
| Client double-click tạo hai outbox rows | Duplicate mail | Unique business intent |
| Retry mọi timeout | Unknown-after-DATA duplicate | Reconciliation policy |
| @Async chạy trước transaction commit | Notification sai dữ liệu | After-commit/outbox |
| Worker đánh dấu SENT khi enqueue | Chưa có SMTP submit | State đúng theo milestone |
| Không có status GET authorization | Lộ dữ liệu cá nhân | Resource access control |
| Forgot-password báo không có tài khoản | Account enumeration | Neutral copy |
| Không có retry deadline OTP | Gửi mã đã hết hạn | TTL-aware policy |
| Dùng HTTP 429 cho SMTP throttle nội bộ tùy tiện | Sai semantics API | Tách API limit và provider limit |
| Chỉ xem request p95 | Không thấy queue delay | Event-to-submit metrics |
| Gắn recipient/OTP vào metric/log | PII/secrets leak | Safe telemetry |
| Multi-node @Scheduled không claim | Hai worker gửi trùng | Atomic ownership |
| Không theo dõi unknown outcome | Gửi trùng khi retry | Explicit UNKNOWN_OUTCOME |

## 45. Câu hỏi thường gặp

**1. Gửi email trong controller có luôn sai không?**

Không. Một công cụ nội bộ test SMTP với traffic thấp có thể dùng sync hợp lý. Nhưng đặt mail trên critical path của nghiệp vụ chính thường làm tăng coupling và latency.

**2. Nếu dùng @Async thì có phải email được gửi chắc chắn không?**

Không. @Async chỉ đổi execution thread theo cấu hình, không tự tạo durable storage hoặc retry sau restart.

**3. Async có luôn nhanh hơn không?**

API response thường nhanh hơn nếu chỉ chờ enqueue, nhưng email có thể đến muộn nếu backlog lớn. Phải đo end-to-end time.

**4. JavaMailSender.send trả bình thường có nghĩa inbox đã nhận không?**

Không. Đây là submit-call success, chưa chứng minh downstream delivery/read.

**5. Tại sao HTTP 202 không đồng nghĩa SMTP success?**

202 thường nghĩa server đã tiếp nhận để xử lý, nhưng kết quả xử lý chưa hoàn tất. API phải mô tả đúng contract.

**6. Khi nào nên trả 200 thay vì 202?**

Nếu business operation chính đã hoàn tất, trả 200 có thể đúng dù email queued ở background. Không bắt buộc 202 chỉ vì có một side effect async.

**7. Nếu request timeout, có nên nhấn lại?**

Không tự động. Server có thể đã commit outbox hoặc SMTP đã accept. Cần idempotency key/status endpoint để biết kết quả.

**8. Có cần status endpoint cho mọi email không?**

Không. Nếu email chỉ là thông báo phụ, UI có thể không cần progress. Nhưng hệ thống vẫn cần monitoring và durable state nếu reliability quan trọng.

**9. OTP nên sync hay async?**

Tùy end-to-end SLO, worker priority, time budget và UX. Async bền vững với priority cao thường phù hợp, nhưng phải đo thời gian mã trở nên dùng được và TTL.

**10. Quên mật khẩu có nên báo đã gửi thật hay không?**

Nên dùng thông điệp trung tính tránh dò tài khoản, bất kể có tạo mail intent hay không.

**11. Transactional outbox có ngăn gửi trùng hoàn toàn không?**

Không. Nó giúp durable intent và tách business commit, nhưng không tạo transaction nguyên tử giữa database và SMTP relay.

**12. Có nên gọi JavaMailSender trong @Transactional method không?**

Có thể về kỹ thuật nhưng thường rủi ro: SMTP side effect không rollback khi database rollback. Outbox/after-commit phù hợp hơn khi cần tính nhất quán.

**13. @TransactionalEventListener(AFTER_COMMIT) đã đủ chưa?**

Nó tránh gọi trước commit trong điều kiện phù hợp, nhưng không tự bảo đảm event không mất khi process crash sau commit. Outbox mạnh hơn khi cần durability.

**14. Nếu provider down 20 phút mà API trả 202 có được xem là success không?**

API acceptance có thể thành công, nhưng email SLO vẫn có thể thất bại. Theo dõi retry backlog, oldest pending age và terminal failures riêng.

**15. Cần WebSocket để cập nhật trạng thái gửi mail không?**

Không bắt buộc. Polling hoặc không hiển thị progress có thể đủ; SSE/WebSocket chỉ khi UX thực sự cần real-time.

**16. Sync có giúp giảm duplicate không?**

Không tự động. HTTP timeout và user retry vẫn có thể tạo nhiều submissions. Idempotency và unknown outcome policy là cần thiết.

**17. Email confirmation và marketing newsletter nên dùng cùng queue không?**

Có thể dùng chung infrastructure, nhưng priority, quota, deadline và fairness nên tách phù hợp để marketing không làm chậm email quan trọng.

**18. Có thể hiển thị “100% gửi thành công” khi outbox hết pending không?**

Không. Một số events có thể FAILED/UNKNOWN_OUTCOME, và SMTP submitted không đồng nghĩa downstream delivered. Cần định nghĩa mẫu số và milestone rõ.

**19. Nếu admin cần biết SMTP credentials đúng ngay thì sao?**

Một bounded synchronous test send có thể phù hợp, với timeout, quyền truy cập và copy chỉ khẳng định submit result.

**20. Có nên gửi lại email ngay khi SocketTimeoutException không?**

Không nếu không biết phase. Timeout sau DATA có thể có ambiguous acceptance; cần RECONCILE/UNKNOWN_OUTCOME.

**21. Tại sao không dùng một hàng đợi memory?**

Vì process restart có thể làm mất pending work. Chọn durable outbox/broker nếu người dùng được hứa xử lý sau.

**22. Có thể theo dõi delivered bằng JavaMailSender không?**

Không có API chuẩn JavaMailSender bảo đảm downstream delivered. Cần provider-specific event integration nếu use case yêu cầu.

**23. Có nên cho người dùng hủy email đang gửi không?**

Chỉ nên xác nhận hủy thành công trước khi transport submission xảy ra; nếu đang PROCESSING/đã DATA, có race và outcome không chắc.

**24. Khi nào nên áp dụng bounded wait hybrid?**

Khi user hưởng lợi nếu SMTP hoàn tất rất nhanh nhưng không nên chờ quá budget. Cần durable enqueue và status endpoint để xử lý phần còn lại.

**25. Có thể đo UX chỉ bằng HTTP latency không?**

Không. Với email-dependent actions, cần event-to-submit/delivery indicators và số lần user resend/abandon, không chỉ API p95.

## 46. Ghi nhớ về chọn đồng bộ hay bất đồng bộ theo trải nghiệm người dùng

**Quyết định gửi email đồng bộ hay bất đồng bộ phải bắt đầu từ nhu cầu người dùng và hợp đồng phản hồi của hệ thống, không từ sở thích kỹ thuật.** Sync cho phép request chờ kết quả SMTP submission phía caller, có thể phù hợp cho kiểm tra cấu hình hoặc thao tác nội bộ có time budget nhỏ. Async cho phép trả phản hồi sau khi hệ thống **ghi nhận yêu cầu bền vững**, thích hợp khi email là side effect, khi cần retry/lập lịch hoặc khi SMTP không nên giữ critical HTTP path.

**Đừng nhầm ba mốc**: durable request accepted, SMTP submission completed và downstream delivered. HTTP 202 thường nói “đã tiếp nhận để xử lý”, không phải “đã gửi xong”; send trả bình thường cũng không chứng minh inbox đã nhận. UI nên dùng trạng thái/diễn đạt trung thực, và chỉ cung cấp polling/SSE/WebSocket khi người dùng thực sự cần theo dõi.

Với nghiệp vụ quan trọng, hãy commit **business state + transactional outbox intent** cùng một transaction, rồi để worker claim và gửi sau commit. Dùng retry/backoff, maxAttempts, deadline, idempotency, lease và state tracking; đặc biệt thận trọng với **UNKNOWN_OUTCOME** sau SMTP DATA để tránh duplicate. Không dùng @Async hoặc in-memory queue như một lời bảo đảm durability nếu không có storage tương ứng.

Cuối cùng, **đo cả thời gian phản hồi HTTP lẫn thời gian từ event đến SMTP submission**, theo dõi backlog/age và downstream signals nếu tích hợp. Một kiến trúc tốt không chỉ giúp màn hình tải nhanh hơn, mà còn giúp người dùng nhận phản hồi đúng sự thật, tránh phải thao tác lặp và có đường xử lý rõ ràng khi email bị trì hoãn hoặc thất bại.
