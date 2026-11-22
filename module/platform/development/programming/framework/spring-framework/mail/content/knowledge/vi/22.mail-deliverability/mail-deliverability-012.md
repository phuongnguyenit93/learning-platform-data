# Theo dõi accepted, bounced, deferred và complained trong Spring Framework Mail

Một lệnh gửi email thành công trong ứng dụng không đồng nghĩa email đã đến hộp thư của người nhận. Với Spring Framework Mail, lời gọi **JavaMailSender.send(...)** thường cho ứng dụng biết quá trình gửi sang SMTP relay đã hoàn tất hoặc đã gặp lỗi ở giai đoạn ứng dụng trực tiếp quan sát được. Sau đó relay và các hệ thống chuyển thư khác vẫn có thể tiếp tục xử lý, thử lại, từ chối, trả thư hoặc ghi nhận người nhận báo cáo spam.

Trong vận hành email, bốn nhóm tín hiệu đặc biệt quan trọng là **accepted**, **bounced**, **deferred** và **complained**. Chúng mô tả những giai đoạn khác nhau trong chuỗi giao thư:

- **Accepted:** một bên nhận trách nhiệm xử lý thông điệp ở một ranh giới nhất định, chẳng hạn SMTP relay chấp nhận yêu cầu gửi. Phải xác định rõ *bên nào chấp nhận*.
- **Bounced:** có bằng chứng thông điệp không giao được và bị trả lại/thất bại ở một giai đoạn giao thư.
- **Deferred:** việc giao thư bị trì hoãn hoặc tạm thời từ chối; hệ thống có thể thử lại theo chính sách.
- **Complained:** có tín hiệu người nhận báo cáo thư là spam hoặc khiếu nại tương đương, thường đến từ feedback loop hoặc nhà cung cấp.

Những tín hiệu này không phải bốn nhãn độc lập hoàn toàn, cũng không phải một danh sách trạng thái luôn đi theo một chiều. Một message có thể được accepted trước, deferred nhiều lần, cuối cùng delivered; hoặc được accepted rồi hard-bounced; hoặc delivered trước khi xuất hiện complaint. Một hệ thống theo dõi deliverability cần lưu **lịch sử sự kiện và trạng thái dẫn xuất**, thay vì chỉ ghi đè một trường status tùy theo webhook đến sau cùng.

## 1. Deliverability khác việc submit email

**Delivery** là việc thông điệp được một hệ thống nhận chấp nhận tại một điểm trên hành trình. **Deliverability** thường được dùng rộng hơn để nói về khả năng email đến đúng nơi được mong muốn, chẳng hạn inbox thay vì spam. Một tín hiệu SMTP 250 hoặc provider “delivered” không nhất thiết xác nhận người nhận đã nhìn thấy email trong Inbox.

Ví dụ:

~~~text
Spring application
       |
       | JavaMailSender.send(...)
       v
Outbound SMTP relay
       |   <-- accepted bởi relay của người gửi
       |
       | Queue / routing / retries
       v
Recipient mail server (MX)
       |   <-- có thể accept, defer hoặc reject
       |
       v
Mailbox / spam folder / policy filters
       |
       | Feedback loop / user action
       v
Complaint signal (nếu có)
~~~

Thông thường có ít nhất ba loại kết quả khác nhau:

1. **Submission result:** ứng dụng có submit message cho transport/relay thành công không?
2. **Provider/remote delivery result:** relay và mail server nhận có chấp nhận, trì hoãn hoặc trả lại message không?
3. **Recipient interaction/reputation result:** có complaint hoặc các tín hiệu người nhận khác không?

Chỉ gọi JavaMailSender không đủ để quan sát cả ba. Cần thêm event từ nhà cung cấp, DSN/bounce mailbox hoặc cơ chế feedback loop tương ứng.

### Ví dụ dễ nhầm

~~~java
mailSender.send(message);
log.info("Email delivered to recipient");
~~~

Log trên khẳng định quá mức. Nên ghi:

~~~java
mailSender.send(message);
log.info("Email submitted to configured SMTP transport");
~~~

Ngay cả thông điệp “submitted” vẫn cần được gắn với transaction/notification cụ thể và kết quả trả về theo SMTP transport. Nếu kết nối bị ngắt vào thời điểm không chắc chắn, ứng dụng có thể không xác định được relay đã nhận message hay chưa.

## 2. Định nghĩa accepted theo đúng ranh giới

**Accepted** phải luôn đi kèm với *accepted by whom?* và *accepted at which stage?*. Ví dụ:

| Tín hiệu | Có thể xác nhận | Không chứng minh |
| --- | --- | --- |
| SMTP relay trả phản hồi thành công sau DATA | Relay đó chấp nhận trách nhiệm xử lý message theo phản hồi | Inbox đã nhận |
| API gửi email trả yêu cầu được chấp nhận/xếp hàng | Provider đã nhận yêu cầu API theo hợp đồng dịch vụ | SMTP phía nhận đã chấp nhận |
| Provider event ACCEPTED | Một mốc accepted được provider định nghĩa | Ý nghĩa giống nhau giữa mọi provider |
| Provider event DELIVERED | Theo định nghĩa provider, việc giao đến hệ thống đích đã đạt mốc nào đó | Người nhận đọc thư hoặc nằm chắc chắn trong Inbox |

Một số nhà cung cấp dùng tên **accepted** cho giai đoạn nhận yêu cầu qua API, một số dùng **processed/queued**; từ **delivered** cũng có thể chỉ tới kết quả remote server trả mã thành công. Vì vậy, **không gán ý nghĩa cho một event name mà chưa xác định nguồn và hợp đồng event của provider**.

### Accepted không phải terminal success của toàn hành trình

Một relay có thể chấp nhận message rồi trả lại DSN sau nhiều phút hoặc nhiều giờ. Nguyên nhân có thể là:

- Remote recipient address không tồn tại.
- Mailbox hoặc hệ thống nhận từ chối theo chính sách.
- Remote server tạm unavailable và hết thời hạn retry.
- Nội dung bị từ chối trong một chặng chuyển tiếp.
- Các lỗi định tuyến hoặc giao thư khác.

Do đó, ứng dụng có thể ghi nhận submission accepted trước và bounce sau. Không coi accepted là kết quả “đã tới tay khách hàng”.

### Accepted ở cấp message hay recipient?

Một MIME message có thể chứa nhiều To/Cc/Bcc recipient. Provider có thể gửi một event ở cấp message, trong khi bounce và complaint xuất hiện **theo từng recipient**. Nếu hệ thống lưu một status chung cho message, lỗi của một người nhận có thể làm sai trạng thái của người khác.

Với email giao dịch cá nhân hóa, thường nên gửi riêng theo recipient để dễ tương quan, bảo mật nội dung và quản lý suppression. Nếu gửi nhiều recipient trong một lần submit, phải thiết kế projection theo message-recipient.

## 3. Bounced: thư bị trả lại hoặc không giao được

**Bounce** là tín hiệu giao thư thất bại. Trong thực tế vận hành, thường phân biệt:

- **Hard bounce:** lỗi khó phục hồi hoặc được coi là vĩnh viễn cho địa chỉ/yêu cầu hiện tại, ví dụ mailbox không tồn tại.
- **Soft bounce:** lỗi tạm thời, ví dụ hộp thư đầy hoặc hệ thống đích tạm unavailable.

Đây là cách phân loại nghiệp vụ phổ biến, **không phải một ánh xạ tuyệt đối của mọi SMTP code**. Một số provider phát event “bounce” cho kết quả cuối sau nhiều lần defer; một số phát soft bounce riêng; một số dùng các trường phân loại khác. Cần chuẩn hóa từ dữ liệu gốc của nhà cung cấp.

### Các nguyên nhân bounce phổ biến

| Nhóm | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Address invalid | Mailbox không tồn tại | Không tiếp tục gửi lặp tới địa chỉ đó |
| Domain invalid | Domain không phân giải được hoặc không có route phù hợp | Kiểm tra địa chỉ, loại lỗi và khả năng phục hồi |
| Policy rejection | Server đích từ chối theo chính sách | Phân tích SMTP reply, xác thực domain và reputation |
| Mailbox full | Mailbox quá giới hạn | Có thể là lỗi tạm thời; theo policy retry của provider |
| Temporary unavailable | MX tạm unavailable | Deferred/retry trước khi trở thành bounce cuối |
| Message/content rejected | Kích thước hoặc nội dung không được phép | Sửa nội dung/chính sách, không retry mù |
| Sender authentication/reputation | Thư bị từ chối do SPF/DKIM/DMARC hoặc uy tín gửi theo chính sách | Điều tra cấu hình và chất lượng gửi |

Không nên mặc định mọi bounce đều do email address sai. Một tỷ lệ bounce tăng đồng thời trên nhiều domain có thể phản ánh sự cố ở phía người gửi, sender authentication, cấu hình DNS hoặc một thay đổi của nhà cung cấp.

### Bounce sau khi accepted là bình thường

Ví dụ:

~~~text
09:00:00  SMTP relay accepts message
09:00:02  Provider emits ACCEPTED
09:00:30  Recipient MX returns temporary failure
09:00:31  Provider emits DEFERRED
10:20:00  Retry policy expires
10:20:01  Provider emits BOUNCED
~~~

Ở đây, accepted là một sự kiện thật, nhưng không phải kết quả cuối. Bounced cho biết quá trình giao thư cuối cùng thất bại theo provider.

### Permanent bounce và suppression

Với địa chỉ được xác định không hợp lệ vĩnh viễn, ứng dụng thường nên:

1. Ghi nhận bounce theo recipient và provider event.
2. Đưa địa chỉ vào suppression list theo chính sách.
3. Ngừng các lần gửi tiếp theo không có cơ sở rõ ràng.
4. Cung cấp cách sửa/cập nhật địa chỉ hợp lệ.
5. Không xóa lịch sử bounce ngay khi người dùng nhập cùng email lần nữa.

Một lần soft bounce không nhất thiết cần suppress vĩnh viễn. Có thể áp dụng ngưỡng, thời gian, lý do và chính sách riêng tùy provider. Tránh biến mọi lỗi tạm thời thành một địa chỉ bị chặn mãi mãi.

## 4. Deferred: tạm trì hoãn không đồng nghĩa thất bại cuối

**Deferred** thường diễn tả việc một lần chuyển thư chưa thành công nhưng còn cơ hội thử lại. Ví dụ, remote MX trả SMTP 4xx, provider tạm giữ message trong queue và đặt lịch retry.

~~~text
Provider relay
     |
     | Try delivery to recipient MX
     v
SMTP 451 / temporary response
     |
     v
DEFERRED
     |
     +-- provider retries later --> delivered/accepted by recipient
     |
     +-- retry limit exhausted --> bounced/expired/failed
~~~

**Điểm cực kỳ quan trọng:** Nếu provider đã accepted một message và đang tự retry downstream, ứng dụng thường **không nên gửi lại một message mới chỉ vì nhận event deferred**. Làm vậy sẽ tạo hai chuỗi giao thư song song, tăng nguy cơ duplicate và làm trầm trọng thêm vấn đề throttling.

### Ai chịu trách nhiệm retry?

| Giai đoạn | Thành phần thường retry |
| --- | --- |
| Ứng dụng chưa submit được tới outbound relay | Application outbox/worker theo chính sách |
| Outbound relay đã nhận message nhưng remote MX trả 4xx | Relay/provider theo lịch riêng |
| Provider có event deferred và cho biết đang retry | Theo dõi provider, không tự tạo message mới |
| Provider trả kết quả cuối hết hạn retry | Ứng dụng đánh dấu bounce/failure và xử lý nghiệp vụ |
| Kết quả SMTP submit không xác định | Đối soát hoặc chính sách duplicate trước khi retry |

Một hệ thống cần lưu ranh giới trách nhiệm này; nếu không, hai lớp retry độc lập có thể gây retry storm.

### Deferred có thể xảy ra nhiều lần

Một message có thể có hàng chục lần thử giao thư trước khi kết thúc. Webhook có thể gửi nhiều DEFERRED events với reason khác nhau. Không nên cập nhật status từ DEFERRED sang FAILED ngay chỉ vì đã xuất hiện một lần tạm lỗi.

Với mỗi deferral, hữu ích khi lưu:

- Thời điểm occurrence.
- SMTP response code và enhanced status nếu provider cung cấp.
- Recipient domain/remote MX nếu được cung cấp và được phép lưu.
- Số lần provider đã thử, nếu có.
- Next retry hint hoặc thời điểm thử tiếp, nếu provider cung cấp.
- Provider message ID và internal notification ID.

Không suy đoán thời điểm retry tiếp theo nếu nhà cung cấp không công bố; nên hiển thị “đang chờ provider thử lại” thay vì tạo một ETA không có căn cứ.

## 5. Complained: người nhận báo cáo spam

**Complaint** là tín hiệu liên quan việc người nhận báo cáo thư không mong muốn, thường được chuyển tới sender qua feedback loop, abuse reporting hoặc provider event. Trong hệ thống email marketing, complaint rate cao là dấu hiệu nghiêm trọng về chất lượng danh sách, kỳ vọng của người nhận và uy tín gửi.

Một complaint không phải bounce:

- Bounce: thông điệp không giao được hoặc thất bại trong vận chuyển.
- Complaint: có tín hiệu phản hồi tiêu cực sau khi thông điệp đã được xử lý/giao tới mức có thể bị người nhận đánh dấu.

Không phải mọi mailbox provider đều gửi complaint chi tiết về từng recipient cho người gửi. Một số chỉ cung cấp số liệu tổng hợp hoặc giới hạn thông tin vì quyền riêng tư. **Không có complaint event không chứng minh người nhận không bấm Report spam**.

### Khi nhận complaint đáng tin cậy

Với marketing hoặc email tùy chọn, quy trình thường gồm:

1. Xác thực nguồn event.
2. Lưu complaint cùng provider, message, recipient (nếu có) và thời điểm.
3. Suppress người nhận khỏi những chiến dịch tương ứng theo chính sách.
4. Dừng email marketing đang nằm trong queue nếu policy yêu cầu.
5. Kiểm tra nguyên nhân: tần suất, nội dung, consent, nguồn danh sách, unsubscribe.
6. Theo dõi complaint rate của campaign, sender domain và provider.

Complaint có thể xảy ra sau sự kiện DELIVERED. Vì vậy một message đã delivered vẫn có thể có **complained=true**, không nên thay thế mọi thông tin lịch sử bằng một status duy nhất.

### Complaint khác unsubscribe

Người dùng nhấn unsubscribe là một yêu cầu từ chối nhận trong phạm vi cụ thể. Complaint là tín hiệu báo thư không mong muốn, có thể đi qua provider và mang ý nghĩa khác. Hai sự kiện đều có thể dẫn đến suppression marketing, nhưng:

- Nguồn và mức độ tin cậy khác nhau.
- Phạm vi suppression có thể khác.
- Thời điểm biết sự kiện khác.
- Quy định và cơ chế xử lý có thể khác tùy chính sách.

Không xóa trạng thái complaint chỉ vì user không bấm unsubscribe. Cũng không tự coi mọi click unsubscribe là spam complaint.

### Email bảo mật và thông báo giao dịch

Nếu một địa chỉ có complaint, hệ thống không nên tiếp tục gửi quảng cáo cho địa chỉ đó. Tuy nhiên, chính sách đối với email bảo mật hoặc giao dịch bắt buộc cần được thiết kế riêng, bao gồm khả năng xác thực lại địa chỉ, chọn kênh thay thế hoặc hạn chế tiếp tục gửi gây hại. Không dùng một boolean “mailEnabled” mơ hồ để xử lý mọi loại email.

## 6. Bảng so sánh bốn nhóm trạng thái

| Tín hiệu | Mức độ cuối cùng? | Nguồn quan sát phổ biến | Phản ứng phù hợp |
| --- | --- | --- | --- |
| ACCEPTED | Chưa chắc; thường là một mốc trung gian | SMTP submission response hoặc provider event | Ghi nhận mốc accepted, tiếp tục theo dõi |
| BOUNCED | Thường là kết quả thất bại cho một lần giao | Provider bounce event, DSN/NDR | Phân loại permanent/temporary, suppression khi cần |
| DEFERRED | Chưa; đang chờ retry hoặc xử lý | SMTP 4xx/downstream event | Theo dõi, không gửi lại khi provider đang retry |
| COMPLAINED | Phản hồi tiêu cực có ý nghĩa lâu dài | Feedback loop, provider complaint event | Suppress email tùy chọn và điều tra uy tín |

Không xây hệ thống theo quy tắc “accepted tốt, bounced xấu, deferred chờ, complained xấu” rồi bỏ hết lý do, recipient và timeline. **Một event không có nguồn và ngữ cảnh có thể dẫn tới quyết định sai.**

## 7. Luồng sự kiện đầy đủ cho một notification

Một ứng dụng có thể dùng các trạng thái nội bộ:

~~~text
CREATED
   |
   v
PENDING_SUBMISSION
   |
   +-- SMTP submit fails before acceptance --> RETRY_PENDING
   |
   +-- accepted by outbound relay --> SUBMITTED
                                            |
                                            v
                                     PROVIDER_ACCEPTED
                                            |
                         +------------------+-------------------+
                         |                  |                   |
                         v                  v                   v
                      DEFERRED           DELIVERED            BOUNCED
                         |                  |
                         +---- retry ------>|
                                            |
                                            v
                                         COMPLAINT
~~~

Sơ đồ mô tả các nhánh phổ biến, không bao quát mọi thứ tự. Một provider có thể gửi event với độ trễ, duplicate hoặc out of order; complaint có thể xuất hiện sau delivered; bounce có thể tới sau một mốc accepted. Một số event là thông tin lịch sử, không phải trạng thái mới làm “hồi quy” thành công.

### Nên tách transport state và feedback flags

Ví dụ mô hình:

~~~java
public enum SubmissionStatus {
    NOT_STARTED,
    RETRY_PENDING,
    SUBMITTED,
    SUBMISSION_UNKNOWN,
    FAILED
}

public enum DeliveryStatus {
    UNKNOWN,
    ACCEPTED_BY_PROVIDER,
    DEFERRED,
    DELIVERED,
    BOUNCED
}

public record RecipientDeliveryView(
        SubmissionStatus submission,
        DeliveryStatus delivery,
        boolean complained,
        boolean suppressed,
        String latestReasonCode
) {
}
~~~

Đây là các enum/record do ứng dụng định nghĩa. **JavaMailSender không cung cấp trực tiếp trạng thái delivered hoặc complained**. Những trạng thái này phải đến từ event provider hoặc nguồn dữ liệu khác và được ánh xạ vào mô hình nội bộ.

### Tại sao không tạo một enum duy nhất?

Một enum duy nhất khó thể hiện:

- SUBMITTED rồi BOUNCED.
- DELIVERED rồi COMPLAINED.
- DEFERRED nhiều lần trước DELIVERED.
- Một message có nhiều recipient, người này DELIVERED, người khác BOUNCED.
- SUPPRESSED vì complaint trước khi các job khác được submit.

Hãy giữ timeline event, tạo projection hiện tại cho UI/alert và lưu flags/trạng thái cần thiết cho các quyết định gửi trong tương lai.

## 8. Nguồn dữ liệu nào cung cấp các event?

Spring Mail chủ yếu quản lý bước xây dựng và submit email. Các event sau submission thường đến từ những thành phần khác:

| Nguồn | Tín hiệu có thể cung cấp | Giới hạn |
| --- | --- | --- |
| JavaMailSender/Jakarta Mail | Kết quả submit, exception và phản hồi SMTP có thể đọc được | Không biết chắc kết quả giao thư sau khi relay nhận |
| SMTP relay logs | Thời điểm nhận, chuyển tiếp, defer/reject, queue ID | Cần quyền log; định dạng tùy relay |
| Email service provider webhook | Accepted, delivered, bounce, defer, complaint theo hợp đồng provider | Có thể trễ, trùng, thiếu event hoặc không có đủ chi tiết recipient |
| Provider event API/export | Lịch sử message, event và mã lỗi | Cần polling, phân trang, quota và thời gian lưu dữ liệu |
| Bounce mailbox/DSN | Non-delivery report hoặc status thông điệp | Có thể thiếu, đến trễ, khó tương quan; có thể giả mạo |
| Complaint feedback loop | Khiếu nại spam từ mailbox/provider tham gia | Không phủ mọi mailbox, có thể chỉ có dữ liệu tổng hợp |
| Admin/user actions | Unsubscribe, report và yêu cầu hỗ trợ do hệ thống sở hữu | Không tương đương mọi complaint do mailbox provider ghi nhận |

Không nên xây dashboard “delivered 100%” chỉ bằng số lần JavaMailSender không ném exception. Nếu không tích hợp provider event/DSN, hãy gọi metric là **submission accepted** hoặc **submitted**, và ghi rõ giới hạn quan sát.

### Lựa chọn đường lấy event

Nếu ứng dụng dùng một email provider có webhook, đó thường là nguồn thuận tiện để biết delivery lifecycle. Nếu dùng SMTP relay nội bộ, có thể lấy relay log hoặc bounce/feedback mailbox. Nếu chỉ có SMTP AUTH và không có event export, ứng dụng cần chấp nhận rằng các kết quả downstream có thể **không biết được**.

Không tự tạo delivered event sau một timeout cố định chỉ vì không nhận được bounce. **Không có bằng chứng thất bại không phải bằng chứng giao thành công.**

## 9. SMTP response, DSN và provider webhook là các lớp khác nhau

### Kết quả submit SMTP

Một phiên SMTP có các bước đại diện:

~~~text
Client        SMTP relay
  |  EHLO         |
  |-------------->|
  |  STARTTLS     |
  |-------------->|
  |  AUTH         |
  |-------------->|
  |  MAIL FROM    |
  |-------------->|
  |  RCPT TO      |
  |-------------->|
  |  DATA         |
  |-------------->|
  |  message      |
  |-------------->|
  |  .            |
  |-------------->|
  |<----- 250 ----|  Accepted by this relay
~~~

Một mã thành công sau DATA xác nhận relay đó nhận trách nhiệm xử lý thông điệp. Các mã phản hồi ở MAIL FROM hoặc RCPT TO có thể phản ánh vấn đề gửi/recipient ngay thời điểm submit; không nên đồng nhất chúng với bounce không đồng bộ sau khi relay đã chấp nhận.

### DSN: Delivery Status Notification

DSN là cơ chế thông báo kết quả vận chuyển email. Một DSN có thể cho biết action như failed, delayed hoặc delivered theo thông tin của hệ thống phát DSN, kèm trường diagnostic code/status nếu có. Một số hệ thống còn gửi báo cáo không đúng định dạng chuẩn hoặc thiếu trường.

Ví dụ khái niệm:

~~~text
Reporting-MTA: dns; relay.example.net
Final-Recipient: rfc822; buyer@example.org
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 User unknown
~~~

Đây là đoạn minh họa một phần nội dung DSN, không phải thông điệp đầy đủ. Khi parse DSN thực, có thể cần đọc cấu trúc MIME multipart/report và phần message/delivery-status bằng thư viện phù hợp; không coi mọi email có subject “Undelivered” là DSN đáng tin.

### Feedback loop và complaint

Complaint có thể đến qua báo cáo feedback mà email provider nhận từ mailbox provider hoặc qua event API của provider. Phạm vi dữ liệu có thể hạn chế. Không chắc tất cả complaint đều có recipient identifier hoặc original message ID.

### Return-Path và SMTP envelope

Bounce thường liên quan địa chỉ **envelope sender/MAIL FROM**. Header From hiển thị cho người đọc có thể khác envelope sender. Return-Path là header được thêm/định hình trong quá trình giao thư, không phải thứ mà ứng dụng nên tự ghép để định tuyến bounce.

Nếu vận hành relay riêng, có thể dùng envelope sender hoặc cơ chế VERP/token hóa để nhận diện recipient khi có bounce. Với managed email provider, nên dùng tracking/correlation ID và bounce handling do provider hỗ trợ. Đừng mặc định tùy chỉnh Return-Path hoạt động như nhau trên mọi provider.

## 10. Định danh và tương quan một email xuyên suốt hệ thống

Muốn ghép accepted, deferred, bounced và complained vào một notification, cần chiến lược correlation từ lúc tạo yêu cầu gửi.

### Các ID thường gặp

| ID | Nơi sinh | Vai trò |
| --- | --- | --- |
| Internal notification ID | Ứng dụng | ID bền vững đại diện cho yêu cầu nghiệp vụ |
| Delivery attempt ID | Worker/outbox | Phân biệt từng lần submit |
| RFC Message-ID | MIME message/header | Hỗ trợ truy vết thông điệp qua các hệ thống |
| Provider message ID | Email provider/relay | Đối chiếu event tới message provider quản lý |
| Provider event ID | Hệ thống event | Deduplicate các lần webhook giao trùng |
| Recipient ID | Ứng dụng | Định danh người nhận nội bộ và preference/suppression |
| Recipient address snapshot | Tại thời điểm gửi | Xác định địa chỉ thực đã dùng cho attempt |
| SMTP queue ID | Relay | Tra cứu log chuyển thư nếu được cung cấp |

**Không giả định mọi ID đều giống nhau.** Provider có thể sinh message ID mới khác RFC Message-ID. Một webhook có thể dùng provider message ID còn log ứng dụng chỉ lưu notification ID; nếu không ghi ánh xạ, việc tương quan sẽ rất khó.

### Lưu ánh xạ theo attempt

Ví dụ:

~~~text
notificationId:  notif-184
attemptId:       attempt-2
recipientId:     customer-42
recipient:       buyer@example.org
messageId:       <notif-184-attempt-2@mail.example.com>
providerMessageId: provider-msg-9901
provider:        primary-smtp
~~~

Các ID chỉ là dữ liệu minh họa. Khi provider trả về ID trong API response, hãy lưu nó cùng attempt. Với SMTP relay, provider message ID có thể không hiện diện theo cách bạn kỳ vọng; xem khả năng log/tracing thực tế trước khi thiết kế.

### Header correlation tùy chỉnh

Trong trường hợp cần theo dõi, ứng dụng có thể thêm header nội bộ:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, "UTF-8");

helper.setFrom("notifications@example.com");
helper.setTo("buyer@example.org");
helper.setSubject("Xác nhận đơn hàng");
helper.setText("Đơn hàng của bạn đã được ghi nhận.");

message.setHeader("X-Notification-ID", "notif-184");
mailSender.send(message);
~~~

Header tùy chỉnh có thể xuất hiện trong raw email và đi qua hệ thống ngoài; **không đưa PII, email address, credential, token hoặc ID nhạy cảm** vào header. Không cho người dùng kiểm soát trực tiếp giá trị header. Một số provider có cơ chế metadata/tag riêng tốt hơn, và có thể không giữ nguyên custom header.

### Một message nhiều recipient

Nếu provider event có recipient riêng, correlation key phải chứa cả recipient hoặc recipient ID. Một provider message ID có thể ánh xạ tới nhiều recipient; không đặt unique constraint chỉ trên provider message ID nếu điều đó khiến bạn không lưu được kết quả riêng cho từng người nhận.

### Message-ID không bảo đảm exactly-once

Khi SMTP reply cuối bị mất sau DATA, ứng dụng có thể gửi lại và tạo duplicate. Dùng Message-ID ổn định hỗ trợ truy vết nhưng không buộc mọi relay/mailbox loại bỏ trùng. Internal idempotency key giúp ngăn tạo yêu cầu nghiệp vụ trùng; nó không tự bảo đảm một thư chỉ được người nhận nhận đúng một lần.

## 11. Thiết kế bảng lưu event và trạng thái hiện tại

Một thiết kế có thể tách ba tập dữ liệu:

1. **Notification/outbox:** ai cần nhận thông điệp gì và tại sao.
2. **Delivery attempts:** mỗi lần submit ra SMTP/API, có thời gian và provider ID.
3. **Provider events:** từng accepted/bounced/deferred/complained hoặc delivered signal đến từ bên ngoài.

Một projection recipient-level tổng hợp các event thành trạng thái hiện tại cho dashboard và logic suppression.

### Schema SQL minh họa

~~~sql
CREATE TABLE email_notification (
    id                  VARCHAR(100) PRIMARY KEY,
    notification_type   VARCHAR(100) NOT NULL,
    recipient_id        VARCHAR(100) NOT NULL,
    recipient_address   VARCHAR(320) NOT NULL,
    created_at          TIMESTAMP NOT NULL
);

CREATE TABLE email_delivery_attempt (
    id                  VARCHAR(100) PRIMARY KEY,
    notification_id     VARCHAR(100) NOT NULL,
    provider_key        VARCHAR(100) NOT NULL,
    provider_message_id VARCHAR(250),
    smtp_message_id     VARCHAR(250),
    submission_status   VARCHAR(40) NOT NULL,
    started_at          TIMESTAMP NOT NULL,
    finished_at         TIMESTAMP,
    FOREIGN KEY (notification_id)
        REFERENCES email_notification(id)
);

CREATE TABLE email_provider_event (
    id                   VARCHAR(100) PRIMARY KEY,
    provider_key         VARCHAR(100) NOT NULL,
    provider_event_id    VARCHAR(250),
    attempt_id           VARCHAR(100),
    recipient_address    VARCHAR(320),
    event_type           VARCHAR(50) NOT NULL,
    reason_code          VARCHAR(100),
    occurred_at          TIMESTAMP,
    received_at          TIMESTAMP NOT NULL,
    raw_payload_ref      VARCHAR(400),
    FOREIGN KEY (attempt_id)
        REFERENCES email_delivery_attempt(id)
);

CREATE TABLE email_recipient_delivery (
    notification_id      VARCHAR(100) PRIMARY KEY,
    delivery_status      VARCHAR(40) NOT NULL,
    complained           BOOLEAN NOT NULL,
    suppressed           BOOLEAN NOT NULL,
    last_event_at        TIMESTAMP,
    updated_at           TIMESTAMP NOT NULL,
    FOREIGN KEY (notification_id)
        REFERENCES email_notification(id)
);
~~~

Đây là schema rút gọn để minh họa; cần thêm indexes, unique constraints phù hợp provider, các cột multi-recipient nếu hỗ trợ, timezone/type thực tế, tenant isolation, retention và quyền truy cập. Nếu có nhiều người nhận trong một notification, khóa projection cần bao gồm recipient ID hoặc một record email-recipient riêng.

### Unique key cho provider event

Nếu provider cung cấp event ID ổn định, đặt unique constraint theo **provider + event ID**, có thể thêm phạm vi account nếu ID chỉ duy nhất trong tài khoản đó. Một ID do provider định nghĩa đôi khi không duy nhất toàn hệ thống. Không tự dùng event timestamp hoặc type làm unique key vì nhiều event hợp lệ có thể có timestamp giống nhau.

Ví dụ:

~~~sql
CREATE UNIQUE INDEX uq_provider_event
ON email_provider_event(provider_key, provider_event_id);
~~~

Khi provider_event_id có thể null, cần quy định dedup riêng và xem hành vi unique/null của database. Event không có ID đáng tin không thể dedup tuyệt đối bằng cách nối tùy tiện các trường; có thể lưu hash payload và một key có scope, song phải hiểu nguy cơ gộp nhầm hai event hợp lệ.

### Vì sao nên giữ event append-only?

Nếu một webhook đến trễ hoặc xuất hiện lỗi trong logic projection, lịch sử event giúp:

- Tái xây dựng trạng thái.
- Điều tra timeline deferral/bounce.
- Phân biệt event giao trùng với nhiều lần retry thật.
- Xác minh hệ thống đã xử lý complaint hay chưa.
- Đối chiếu provider export và metric.

Không cần lưu raw payload vô thời hạn. Nếu giữ raw payload, đặt chính sách retention, mã hóa, quyền đọc và làm sạch dữ liệu cá nhân. Một event log được bảo vệ hợp lý có thể đủ để tính lại projection mà không cần lưu toàn bộ raw JSON.

## 12. Model event chuẩn hóa trong Java

Mỗi provider có tên field và event type riêng. Nên ánh xạ về model trung lập, rồi để business logic xử lý theo model đó.

~~~java
package com.example.mail.delivery;

import java.time.Instant;

public enum DeliveryEventType {
    ACCEPTED,
    DELIVERED,
    DEFERRED,
    BOUNCED,
    COMPLAINED,
    UNKNOWN
}

public record MailDeliveryEvent(
        String providerKey,
        String providerEventId,
        String providerMessageId,
        String internalNotificationId,
        String recipientAddress,
        DeliveryEventType type,
        String providerReasonCode,
        Instant occurredAt,
        Instant receivedAt
) {
}
~~~

Record và enum trên là kiểu do ứng dụng tự tạo; Spring Mail không có sẵn class MailDeliveryEvent với cấu trúc này. Nếu provider dùng các event như processed, dropped, blocked hoặc spamreport, mapper phải quy định rõ cách chuyển đổi và các trường hợp UNKNOWN.

### Không đánh mất raw reason

Việc chuẩn hóa thành BOUNCED hữu ích cho dashboard, nhưng nếu chỉ giữ nhãn đó, người vận hành không thể phân biệt:

- Permanent mailbox not found.
- Sender policy violation.
- Message too large.
- Domain DNS issue.
- Provider block theo reputation.

Nên giữ mã lỗi/nhóm lỗi đã làm sạch và source event type từ provider, đồng thời lưu chỉ dẫn về raw payload có thời hạn nếu thật sự cần điều tra.

## 13. Nhận event qua webhook

Một email provider có thể gửi HTTP POST tới endpoint ứng dụng khi thông điệp accepted, delivered, deferred, bounced hoặc complained. Webhook là **nguồn dữ liệu bên ngoài**, nên phải xác thực trước khi tin event.

### Luồng nhận event

~~~mermaid
flowchart TD
    A["Email provider webhook"] --> B["HTTPS endpoint"]
    B --> C["Verify signature / timestamp"]
    C --> D{"Valid?"}
    D -- "No" --> E["Reject and record safe audit"]
    D -- "Yes" --> F["Parse and normalize"]
    F --> G["Durably store event / inbox"]
    G --> H["Ack provider"]
    G --> I["Async event consumer"]
    I --> J["Deduplicate + correlate"]
    J --> K["Update timeline / projection"]
    K --> L["Suppression / metrics / alert"]
~~~

Việc trả HTTP 2xx nên gắn với **đã lưu bền vững** event hoặc đã chuyển thành công tới một queue bền vững, không chỉ vì controller vừa nhận payload trong memory. Nếu database/broker tạm lỗi, chính sách HTTP response phải tương thích với cơ chế retry của provider; không tự xác nhận đã xử lý nếu event có thể mất ngay sau đó.

### Xác minh webhook ở lớp biên

Cần kiểm tra theo hợp đồng provider:

- HTTPS và endpoint không công khai dữ liệu không cần thiết.
- Signature hoặc authentication scheme của provider.
- Tính toàn vẹn của **raw request body** theo quy tắc provider.
- Timestamp/tolerance chống replay nếu provider hỗ trợ.
- Key rotation và nhiều signing key hợp lệ trong cửa sổ chuyển tiếp.
- Giới hạn kích thước body, số event mỗi batch và timeout.
- Phân biệt test/staging và production account.
- Xử lý sai chữ ký trước khi cập nhật suppression.

Không dùng một header tự đặt như X-Provider-Signature rồi giả định đó là header chuẩn của mọi email provider. Tên header, encoding, canonicalization, HMAC/public-key verification và response code đều phải theo tài liệu provider đang tích hợp.

### Mã controller Spring Boot minh họa

~~~java
package com.example.mail.delivery;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/internal/webhooks/email-provider")
public class MailProviderWebhookController {

    private final ProviderWebhookVerifier verifier;
    private final ProviderEventInbox inbox;

    public MailProviderWebhookController(
            ProviderWebhookVerifier verifier,
            ProviderEventInbox inbox) {
        this.verifier = verifier;
        this.inbox = inbox;
    }

    @PostMapping(consumes = "application/json")
    public ResponseEntity<Void> receive(
            @RequestBody byte[] rawBody,
            @RequestHeader("X-Provider-Signature")
                    String signature,
            @RequestHeader("X-Provider-Timestamp")
                    String timestamp) {

        if (!verifier.isAuthentic(
                rawBody, signature, timestamp)) {
            return ResponseEntity
                    .status(HttpStatus.UNAUTHORIZED).build();
        }

        // Phải là thao tác lưu bền vững, có dedup hoặc
        // một inbox/outbox transaction phù hợp.
        inbox.storeVerifiedPayload(rawBody);

        return ResponseEntity.accepted().build();
    }
}
~~~

**Giả định của ví dụ:** một provider cụ thể đã được cấu hình dùng hai header giả định trên và ProviderWebhookVerifier triển khai đúng thuật toán chữ ký/timestamp của provider. Đây không phải ví dụ copy-paste dùng được với mọi provider; trong hệ thống thật phải thay header, xác thực và event schema theo tài liệu tích hợp.

### Interface cho verifier và inbox

~~~java
public interface ProviderWebhookVerifier {
    boolean isAuthentic(
            byte[] rawBody,
            String signature,
            String timestamp);
}

public interface ProviderEventInbox {
    void storeVerifiedPayload(byte[] rawBody);
}
~~~

Khi storeVerifiedPayload thất bại, exception phải được chuyển thành response báo lỗi server theo cơ chế retry phù hợp, không âm thầm trả 202. Một event đã lưu lặp lại có thể được acknowledge, miễn là quy trình dedup vẫn nhất quán.

### Nếu webhook dùng form hoặc event batch?

Không giả định mọi webhook đều JSON một event. Provider có thể gửi form data, JSON array, nhiều event trong một request hoặc thông báo thông qua queue/cloud event bus. Controller, verifier và parser phải được viết đúng format; đặc biệt signature cần được tính trên biểu diễn mà provider quy định. Việc parse rồi serialize lại JSON trước khi xác minh có thể làm chữ ký không khớp.

## 14. Xử lý webhook trùng lặp, đến trễ và sai thứ tự

Một webhook provider thường có khả năng giao theo mô hình **at-least-once**: khi không nhận được response xác nhận, provider có thể giao lại event. Kể cả khi provider cam kết một trật tự nhất định, network, retry và các worker khác nhau vẫn có thể tạo thứ tự xử lý không như mong đợi.

Ví dụ, một timeline gốc:

~~~text
09:00:00  ACCEPTED
09:01:00  DEFERRED
09:03:00  DELIVERED
09:10:00  COMPLAINED
~~~

Nhưng thứ tự webhook tới ứng dụng có thể là:

~~~text
09:03:02  DELIVERED
09:03:04  ACCEPTED (event cũ đến muộn)
09:03:05  DEFERRED (event cũ đến muộn)
09:10:03  COMPLAINED
09:10:10  COMPLAINED (bản giao lặp)
~~~

Nếu đơn giản viết “status = event.type” cho mỗi webhook, trạng thái hiện tại có thể bị **hồi quy từ DELIVERED về DEFERRED** khi một sự kiện cũ đến trễ. Hoặc hai complaint webhook trùng lặp có thể bị đếm thành hai người khiếu nại.

### Hai quy tắc độc lập

1. **Deduplication:** chỉ ghi nhận một event độc nhất một lần theo khóa do provider bảo đảm.
2. **Projection ordering:** cập nhật trạng thái hiện tại bằng các quy tắc nghiệp vụ, không đơn thuần lấy event cuối cùng nhận được.

Dedup không tự giải quyết ordering: ACCEPTED và BOUNCED có event ID khác nhau, cả hai hợp lệ. Ordering không tự giải quyết dedup: cùng một COMPLAINED event có thể được giao hai lần.

### Thuật toán xử lý khái niệm

~~~text
receive verified event:
    persist raw/normalized event durably

process event in transaction:
    if provider event key already handled:
        ACK duplicate, do not reapply side effects

    correlate provider ID, attempt and recipient
    if no matching attempt:
        store UNMATCHED for bounded reconciliation
        do not attach to another recipient by guess

    append immutable event
    rebuild/update projection with source-specific rules
    if newly observed complaint or permanent bounce:
        apply suppression policy idempotently
    commit
~~~

**Lưu ý:** Cần có một cơ chế bảo đảm ghi event và kết quả “đã xử lý” nhất quán. Nếu dedup state được commit nhưng suppression không được commit, replay event có thể bị bỏ qua và không bao giờ suppress. Nếu suppression tạo một tác vụ ở hệ thống khác, dùng outbox hoặc event riêng bền vững để đảm bảo tác vụ không bị mất.

### Dùng occurredAt hay receivedAt?

- **occurredAt:** thời điểm provider cho biết sự kiện thực sự xảy ra.
- **receivedAt:** thời điểm hệ thống của bạn nhận và lưu event.

Hai giá trị đều hữu ích. Không mặc định clock của provider và ứng dụng hoàn toàn đồng bộ; không coi occurredAt luôn đáng tin tuyệt đối hoặc đủ để giải quyết xung đột nếu provider chỉ cho timestamp chính xác đến giây.

Với dữ liệu từ nhiều nguồn, có thể cần thứ tự ưu tiên event theo provider-specific sequence ID, trạng thái final, event timestamp và lịch sử attempt. Không tự thiết kế một so sánh timestamp duy nhất rồi cho rằng đúng với mọi nguồn.

## 15. Quy tắc cập nhật projection

Một projection cần thể hiện rõ đã biết gì, chưa biết gì và khi nào phải điều tra. Gợi ý nguyên tắc:

- ACCEPTED: ghi nhận mốc provider/relay chấp nhận; không xóa một kết quả giao thư cuối đã ghi nhận.
- DEFERRED: ghi nhận deferral và lý do; có thể đặt trạng thái đang chờ nếu chưa có kết quả kết thúc mới hơn.
- DELIVERED: ghi nhận mốc remote delivery mà provider định nghĩa; không suy ra inbox/read.
- BOUNCED: ghi nhận bounce và phân loại; nếu là outcome cuối của đúng attempt/recipient, thể hiện thất bại.
- COMPLAINED: đặt feedback flag, cập nhật suppression theo policy; không hủy lịch sử DELIVERED.

### Vì sao không có thứ tự ưu tiên toàn cục đơn giản?

“BOUNCED luôn ưu tiên DELIVERED” hoặc “DELIVERED luôn ưu tiên BOUNCED” đều có thể sai nếu:

- Hai event thuộc hai delivery attempts khác nhau.
- Một event delayed bounce liên quan message đã được accepted ở một relay nhưng delivery event lại nói về một bước khác.
- Provider định nghĩa soft bounce khác với final bounce.
- Event timestamp không đáng tin hoặc thiếu recipient ID.

Nên so sánh theo **provider + attempt + recipient**, sau đó áp dụng semantics của nguồn. Nếu event mâu thuẫn không thể phân giải, lưu trạng thái cần reconciliation và giữ cả hai sự kiện, không xóa một event hợp lệ để “làm sạch” dashboard.

### Ví dụ service xử lý event

~~~java
package com.example.mail.delivery;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DeliveryEventProcessor {

    private final DeliveryEventRepository eventRepository;
    private final AttemptResolver attemptResolver;
    private final DeliveryProjectionRepository projectionRepository;
    private final SuppressionPolicyService suppressionPolicy;

    public DeliveryEventProcessor(
            DeliveryEventRepository eventRepository,
            AttemptResolver attemptResolver,
            DeliveryProjectionRepository projectionRepository,
            SuppressionPolicyService suppressionPolicy) {
        this.eventRepository = eventRepository;
        this.attemptResolver = attemptResolver;
        this.projectionRepository = projectionRepository;
        this.suppressionPolicy = suppressionPolicy;
    }

    @Transactional
    public void handle(MailDeliveryEvent event) {
        // Insert-if-absent phải có unique constraint / atomicity.
        boolean inserted = eventRepository.insertIfAbsent(event);
        if (!inserted) {
            return;
        }

        var resolution = attemptResolver.resolve(event);
        if (resolution.isEmpty()) {
            eventRepository.markUnmatched(
                    event.providerKey(), event.providerEventId());
            return;
        }

        var key = resolution.get();
        var view = projectionRepository.lockByRecipientKey(key);

        view.applyAccordingToProviderSemantics(event);
        projectionRepository.save(view);

        if (event.type() == DeliveryEventType.COMPLAINED
                || view.isPermanentBounceNewlyObserved()) {
            suppressionPolicy.applyIfRequired(key, event);
        }
    }
}
~~~

Các interface và method ở đây là **mã giả có hình thức Java**, không phải API Spring Mail có sẵn. Dự án thật phải định nghĩa kiểu resolution/projection, unique constraint và semantics từng provider. Lớp suppressionPolicy phải ghi dữ liệu trong cùng transaction hoặc tạo outbox event bền vững, tránh side effect ngoài transaction không thể rollback.

### Dữ liệu unmatched không được gán bừa

Một event có providerMessageId lạ có thể do:

- Message do tài khoản khác gửi.
- Event đến trước khi attempt mapping được commit.
- Provider chuyển đổi ID.
- Email gửi ngoài ứng dụng.
- Webhook cấu hình sai environment/account.
- Dữ liệu bị lỗi hoặc giả mạo.

Hãy lưu với trạng thái UNMATCHED trong thời gian giới hạn, chạy reconciliation có kiểm soát và cảnh báo khi tỷ lệ unmatched tăng. Không dùng chỉ email address + timestamp gần đúng để sửa trạng thái một thông điệp bất kỳ.

## 16. Đồng bộ hóa trạng thái với outbox gửi

Ứng dụng có thể có outbox để gửi email bền vững. Trạng thái outbox và delivery event là hai lớp:

~~~text
OUTBOX / SUBMISSION           PROVIDER DELIVERY

PENDING
   |
   v
PROCESSING
   |
   v
SUBMITTED ------------------> ACCEPTED
                                |
                                +--> DEFERRED
                                |       |
                                |       +--> DELIVERED
                                |       +--> BOUNCED
                                |
                                +--> BOUNCED
                                +--> DELIVERED
                                         |
                                         +--> COMPLAINED
~~~

Nếu JavaMailSender thành công, record outbox có thể chuyển SUBMITTED. Không được mặc định chuyển thành DELIVERED. Ngược lại, nếu provider DELIVERED event đến nhưng worker chưa kịp ghi SUBMITTED do database tạm lỗi, hệ thống cần ghi nhận event và đối chiếu thay vì xóa sự kiện vì “outbox chưa gửi”.

### SMTP submit không chắc chắn

Ví dụ:

1. Worker gửi DATA tới relay.
2. Relay chấp nhận message.
3. Client mất kết nối trước khi nhận final response.
4. Worker đánh dấu SUBMISSION_UNKNOWN.
5. Provider event ACCEPTED hoặc DELIVERED xuất hiện sau đó.

Event provider đã được xác thực có thể giúp reconciliation, nếu mapping đáng tin cậy. Nếu không có event hoặc provider không hỗ trợ tra cứu, vẫn có rủi ro duplicate khi retry. Không tự gửi lại ngay chỉ vì outbox chưa có SUBMITTED.

### Trách nhiệm retry theo ranh giới

Trường hợp outbox chưa submit được, application worker có thể retry. Trường hợp provider đã accepted và đang DEFERRED, provider thường sở hữu retry tới remote MX. Nếu application tự gửi một bản mới, nó có thể tạo duplicate cho cả recipient và provider.

**Một thông điệp không nên có hai cơ chế retry độc lập cho cùng chặng vận chuyển mà không có phối hợp trạng thái.**

## 17. Thiết kế suppression list

Suppression list là danh sách recipient hoặc phạm vi recipient mà hệ thống **không nên gửi** theo một số quy tắc. Một bản ghi suppression có thể có:

| Trường | Ý nghĩa |
| --- | --- |
| recipientKey | User/recipient ID hoặc địa chỉ đã chuẩn hóa theo policy |
| tenant/providerScope | Phạm vi áp dụng |
| reason | HARD_BOUNCE, COMPLAINT, UNSUBSCRIBE, ADMIN_BLOCK... |
| sourceEventId | Sự kiện gây suppression |
| categoryScope | Marketing, product update, hoặc chính sách khác |
| createdAt | Thời điểm áp dụng |
| expiresAt | Nếu suppression có thời hạn theo policy |
| reviewStatus | Có cần can thiệp hay xác minh lại không |

### Không dùng một boolean cho mọi tình huống

Nếu người dùng unsubscribe newsletter, ứng dụng có thể vẫn cần gửi email bảo mật theo chính sách; nếu mailbox bị hard bounce xác nhận không tồn tại, việc cố gửi OTP vào đó cũng không hữu ích. Complaint lại cần quy tắc rõ về giới hạn gửi và xác minh người nhận. Do đó, áp dụng suppression theo **reason, category, recipient validity và policy**, không phải một biến global duy nhất.

### Hard bounce

Một hard bounce đáng tin có thể khiến địa chỉ bị suppress khỏi các lần gửi tiếp theo. Người dùng có thể được yêu cầu cập nhật/xác minh lại địa chỉ, theo cơ chế nghiệp vụ. Không tự bỏ suppression chỉ vì một user thay đổi tên hiển thị.

### Repeated soft bounce

Nhiều soft bounce liên tiếp trong một khoảng thời gian có thể khiến ứng dụng tạm suppress, nhưng ngưỡng và thời hạn phải dựa trên chính sách và hành vi provider. Không “phong tỏa vĩnh viễn” tất cả soft bounce theo một quy tắc chung.

### Complaint

Complaint đáng tin cậy thường cần ngừng email marketing/tùy chọn cho recipient liên quan. Không chờ xử lý thống kê hàng ngày rồi mới suppress nếu event có thể được xử lý ngay. Đồng thời cần kiểm tra lại preference khi worker dispatch để không gửi tiếp job đã xếp hàng trước complaint.

### Không suppress dựa trên webhook chưa xác thực

Nếu bất kỳ ai có thể POST một event COMPLAINED tới endpoint công khai, kẻ tấn công có thể khiến ứng dụng ngừng gửi email quan trọng. Webhook phải được xác minh, correlate với provider/account và recipient hợp lệ trước khi cập nhật suppression.

## 18. Tách deliverability metrics và quality metrics

Một số metric mô tả transport, một số mô tả chất lượng danh sách và phản hồi người nhận:

| Metric | Trả lời câu hỏi |
| --- | --- |
| Submission success | Bao nhiêu yêu cầu được relay/provider nhận thành công? |
| Provider accepted | Bao nhiêu message được provider xác nhận nhận/xếp hàng? |
| Deferred count/rate | Bao nhiêu thông điệp gặp trở ngại tạm thời? |
| Bounce count/rate | Bao nhiêu thông điệp có kết quả thất bại? |
| Hard bounce rate | Tỷ lệ lỗi địa chỉ/policy vĩnh viễn theo phân loại |
| Complaint count/rate | Có bao nhiêu phản hồi spam, trong phạm vi nguồn quan sát? |
| Delivered count/rate | Bao nhiêu thông điệp có provider delivery confirmation? |
| Time to delivery | Bao lâu từ accepted đến delivered theo provider? |
| Delivery event lag | Event đến hệ thống sau bao lâu? |
| Unmatched event rate | Bao nhiêu event không tương quan được? |
| Suppression count | Bao nhiêu recipient đang bị chặn theo reason/category? |

### Định nghĩa mẫu số trước khi tính tỷ lệ

Một tỷ lệ chỉ có ý nghĩa khi nói rõ:

- Đơn vị là **message**, **recipient** hay **attempt**?
- Mẫu số là **submitted**, **accepted**, **delivered**, hay **eligible recipients**?
- Khoảng thời gian là theo createdAt, acceptedAt, event occurredAt hay receivedAt?
- Có đợi đủ thời gian để delayed bounce/complaint xuất hiện không?
- Provider có gửi đủ loại event cho tập người nhận không?

Không nên lấy “số complaint webhook / số tất cả email từ mọi kênh” làm một tỷ lệ rồi so sánh nhà cung cấp khi khả năng quan sát và định nghĩa không giống nhau.

### Công thức minh họa

Nếu cùng một cohort, cùng provider, và có định nghĩa nhất quán:

\[
\text{Bounce Rate} =
\frac{\text{Số recipient-message bị bounce}}
{\text{Số recipient-message được accepted}}
\times 100\%
\]

\[
\text{Deferral Incidence} =
\frac{\text{Số recipient-message từng có deferred}}
{\text{Số recipient-message được accepted}}
\times 100\%
\]

\[
\text{Complaint Rate} =
\frac{\text{Số recipient-message có complaint quan sát được}}
{\text{Số recipient-message trong mẫu số đã công bố}}
\times 100\%
\]

**Mẫu số complaint rate không có một lựa chọn duy nhất dùng được cho mọi provider.** Một dashboard có thể dùng accepted hoặc delivered, tùy chuẩn báo cáo. Một feedback loop có phạm vi hạn chế không nên được trình bày như tỷ lệ complaint của toàn bộ hộp thư mà không ghi chú. Một message deferred ba lần nên tính là **một message có deferral** trong deferral incidence, không phải ba message.

### Không chia cho 0

Nếu cohort không có accepted message, tỷ lệ bounce theo công thức trên là *không xác định*, không phải 0%. UI nên hiển thị “N/A” hoặc thiếu mẫu số, không tự báo 0% để trông có vẻ tốt.

## 19. Cohort và độ trễ của event

Nếu đo bounce rate bằng số bounce nhận hôm nay chia cho số message gửi hôm nay, có thể tạo lệch:

- Message gửi hôm qua có bounce đến hôm nay.
- Message gửi hôm nay chưa đủ thời gian để provider báo kết quả.
- Complaint có thể xuất hiện nhiều ngày sau khi delivered.
- Provider webhook có thể bị trễ do outage hoặc queue backlog.

Một cách tiếp cận là nhóm theo **cohort thời điểm submit/accept**, sau đó quan sát outcome trong một cửa sổ maturation phù hợp. Dashboard real-time có thể hiển thị trạng thái tạm thời và cập nhật khi event muộn tới.

### Ví dụ cohort

~~~text
Ngày tạo cohort: 2026-11-10
Accepted recipient-messages: 10,000
    |
    +-- ngày 10: 70 bounce events
    +-- ngày 11: 20 bounce events
    +-- ngày 12: 10 bounce events
    |
    +-- tính theo cohort: 100 unique recipient-messages bounced
~~~

Ví dụ chỉ minh họa cách nhìn theo cohort, không đưa ra benchmark deliverability. Nếu cả 100 event là cùng một message được provider retry webhook, số bounce unique thực tế phải thấp hơn; cần deduplicate trước khi tính.

### Báo cáo real-time và báo cáo đã trưởng thành

Nên phân biệt:

- **Provisional:** số liệu gần thời điểm gửi, có thể chưa nhận đủ bounce/complaint.
- **Matured:** số liệu sau khoảng chờ được định nghĩa cho phân tích.
- **Reconciled:** số liệu đã đối chiếu với provider export hoặc nguồn đáng tin khác.

Không quảng cáo một tỷ lệ delivered 100% vào vài giây sau khi submit nếu provider còn nhiều thông điệp trong queue.

## 20. Dashboard theo loại email và nhóm người nhận

Một dashboard deliverability hữu ích thường có các chiều:

- Provider/account/SMTP route.
- Sender domain/verified identity.
- Notification category: security, transactional, marketing.
- Campaign/template version.
- Recipient domain hoặc nhóm miền hợp lý.
- Quốc gia/khu vực khi có cơ sở hợp pháp và dữ liệu phù hợp.
- Thời gian/cohort.
- Lý do bounce và complaint.

### Giao diện tổng quan khái niệm

~~~text
Provider: transactional-primary       Period: last 24 hours

Accepted                    18,420
Deferred (unique messages)      310
Bounced (unique messages)       128
Complained (observed)            12
Delivered (provider events)   17,802

Oldest accepted without terminal event: 2h 14m
Provider webhook lag p95: 42s
Unmatched events: 8
Hard bounce reason top: mailbox unavailable / address rejected
~~~

Tất cả số liệu trên là ví dụ, không phải số liệu thật hoặc benchmark. Những tập hợp có thể **chồng lấn**: một message có thể vừa deferred vừa delivered; một message có thể delivered rồi complained. Vì vậy tổng các hàng **không nhất thiết bằng accepted**. UI phải chú thích rõ đây là event counts, unique message counts hay current-status counts.

### Đừng dùng địa chỉ email đầy đủ làm metric label

Micrometer/Prometheus label có cardinality cao nếu thêm recipient ID hoặc email address. Điều này gây tốn bộ nhớ và có thể lộ thông tin cá nhân. Dùng nhãn giới hạn như provider, category, domain nhóm và reason family. Tra cứu theo notification ID riêng qua log/event store có phân quyền.

### Metric gợi ý

~~~text
mail_provider_events_total{provider,type}
mail_provider_event_duplicates_total{provider}
mail_provider_event_unmatched_total{provider}
mail_bounces_total{provider,reason_family}
mail_deferrals_total{provider,reason_family}
mail_complaints_total{provider,category}
mail_delivery_event_lag_seconds{provider}
mail_accepted_without_terminal_age_seconds{provider}
mail_suppression_new_total{reason,category}
~~~

Tên metric do ứng dụng tự định nghĩa, không phải metric mặc định của Spring Mail. Với “accepted without terminal age”, cần xác định nguồn event nào có terminal semantics; không tự coi mọi provider ACCEPTED là terminal.

## 21. Giám sát và cảnh báo bất thường

Theo dõi deliverability không chỉ là lưu event. Cần phát hiện thay đổi đủ sớm để tránh tiếp tục gửi vào một vấn đề hệ thống hoặc làm hỏng uy tín của người gửi.

### Những tín hiệu nên cảnh báo

| Tín hiệu | Điều có thể xảy ra | Hành động ban đầu |
| --- | --- | --- |
| Hard bounce rate tăng mạnh | Danh sách địa chỉ kém chất lượng hoặc provider đang từ chối | Phân nhóm theo sender/recipient domain và reason |
| Deferred rate tăng | Recipient MX throttling, lỗi DNS, tạm unavailable | Kiểm tra mã SMTP và provider queue |
| Complaint tăng | Email không được mong đợi, nội dung/tần suất không phù hợp | Dừng hoặc giảm chiến dịch, kiểm tra consent/suppression |
| Accepted tăng nhưng delivered không theo kịp | Queue đang tồn, webhook lỗi hoặc provider delay | Kiểm tra event lag, provider status và backlog |
| Không thấy webhook trong thời gian dài | Endpoint, authentication hoặc provider event delivery gặp lỗi | Kiểm tra webhook health và dead-letter |
| Event unmatched tăng | Mapping provider message ID bị lỗi, gửi ngoài hệ thống | Kiểm tra integration/account/environment |
| Duplicate webhook tăng | Provider retry hoặc endpoint ack chậm/lỗi | Kiểm tra response, idempotency và latency |
| Nhiều bounce ở một domain | Lỗi cục bộ tới một miền nhận hoặc chính sách miền đó | Điều tra domain-specific, không vội chặn toàn bộ |
| Accepted đột nhiên giảm | SMTP AUTH, quota, provider API lỗi hoặc nguồn gửi giảm | Đối chiếu submission attempts và nguồn nghiệp vụ |

### Không đặt ngưỡng bằng một giá trị tuyệt đối duy nhất

Một hệ thống gửi 20 email mỗi ngày có thể xuất hiện bounce rate 5% chỉ vì một email lỗi. Với hệ thống gửi hàng triệu email, một thay đổi nhỏ về tỷ lệ có thể ảnh hưởng rất nhiều người. Cần cân nhắc:

- Quy mô mẫu số tối thiểu.
- Baseline theo ngày trong tuần, campaign và category.
- Tốc độ tăng/giảm so với lịch sử.
- Số lượng tuyệt đối.
- Mức độ quan trọng của email.
- Khả năng quan sát của từng provider/recipient domain.

Với email OTP, một sự cố delivered latency cao có thể nghiêm trọng dù bounce count thấp. Với marketing, complaint spike có thể cần tạm ngưng chiến dịch trước khi tỷ lệ được tính đủ cohort.

### Alert dựa trên hành động

Alert nên chỉ rõ người trực cần làm gì:

- “SMTP accepted giảm; kiểm tra AUTH và upstream provider.”
- “Deferred tăng ở một recipient domain; xem mã 4xx và throttling.”
- “Complaint tăng cho campaign X; tạm dừng campaign và kiểm tra consent.”
- “Webhook lag tăng; kiểm tra queue consumer và provider retry.”

Không alert mọi lần deferred riêng lẻ như một sự cố diện rộng. Deferred là hành vi bình thường trong nhiều hệ thống SMTP; điều quan trọng là **tỷ lệ, thời gian kéo dài và kết quả cuối**.

## 22. Phân tích nguyên nhân bounce và deferred

Những reason code và text của provider thường là dữ liệu chẩn đoán quý giá. Tuy nhiên, chúng không đồng nhất giữa các nhà cung cấp và có thể chứa thông tin người nhận. Nên ánh xạ về một taxonomy nội bộ để báo cáo.

### Một taxonomy tối thiểu

~~~java
public enum DeliveryReasonFamily {
    INVALID_ADDRESS,
    MAILBOX_FULL,
    TEMPORARY_UNAVAILABLE,
    RATE_LIMIT_OR_THROTTLING,
    AUTHENTICATION_OR_POLICY,
    CONTENT_REJECTED,
    MESSAGE_TOO_LARGE,
    DNS_OR_ROUTING,
    SPAM_OR_REPUTATION,
    UNKNOWN
}
~~~

Không coi taxonomy là định nghĩa chuẩn SMTP. Nó chỉ là mô hình phân loại nội bộ. Một enhanced status code như 5.1.1 thường gợi ý mailbox không tồn tại, nhưng phải dựa trên nguồn cụ thể. Dữ liệu mapping nên có version để khi quy tắc thay đổi vẫn có thể giải thích số liệu cũ.

### Phân tích theo từng chặng

Khi thấy BOUNCED, hãy kiểm tra:

1. Relay nào đã accepted ban đầu?
2. Remote MX có trả mã SMTP cụ thể không?
3. Có DEFERRED trước đó không, và trong bao lâu?
4. Provider đã retry bao nhiêu lần?
5. Bounce là hard, soft hay provider-specific?
6. Recipient address đã được xác minh hay chỉ mới được user nhập?
7. Sự cố có tập trung vào một sender domain, IP, tenant hoặc campaign không?
8. Có thay đổi SPF/DKIM/DMARC hoặc sender policy gần đây không?

### Ví dụ: nhiều deferred ở cùng một recipient domain

~~~text
Provider: relay-a
Recipient domain: example.net
Symptoms: 4.7.x responses, increasing deferrals
Other recipient domains: normal
~~~

Hướng xử lý nên tập trung vào provider/domain đó, kiểm tra tốc độ gửi và nguyên nhân throttling. Không cần đánh dấu mọi recipient ở mọi domain là invalid. Nếu provider đang retry các message đã accepted, ứng dụng nên theo dõi thay vì tạo thêm cùng nội dung qua send() mới.

### Ví dụ: hard bounce tăng sau một chiến dịch import

Nếu bounce tăng sau khi import danh sách, kiểm tra chất lượng địa chỉ, cách thu thập consent, nguồn danh sách và các địa chỉ chưa được xác minh. Tạm dừng campaign nếu cần, không dùng retry để thử đi thử lại địa chỉ đã bị từ chối vĩnh viễn.

## 23. Email authentication hỗ trợ deliverability nhưng không thay event tracking

Một cấu hình gửi thư tốt cần quan tâm tới sender identity, DNS và reputation:

- **SPF:** công bố những nguồn được phép gửi cho một domain trong ngữ cảnh envelope identity phù hợp.
- **DKIM:** ký một số header/body của email để hệ thống nhận xác thực tính toàn vẹn và danh tính domain ký.
- **DMARC:** đưa ra chính sách và alignment dựa trên domain của header From với SPF hoặc DKIM, đồng thời hỗ trợ báo cáo.
- **TLS:** bảo vệ kết nối truyền tải khi được thiết lập và xác thực thích hợp.

Các yếu tố này có thể ảnh hưởng việc mail server nhận chấp nhận hoặc từ chối thông điệp; chúng **không thay thế việc theo dõi accepted, bounce, deferred và complaint**.

### Không suy luận quá mức

- SPF/DKIM/DMARC pass không bảo đảm email nằm trong inbox.
- STARTTLS hoạt động không bảo đảm recipient không bao giờ complaint.
- DKIM fail không tự chứng minh mọi message đều bounce; còn phụ thuộc chính sách receiving server.
- SMTP AUTH thành công chỉ xác nhận điều kiện gửi ở relay, không bảo đảm remote deliverability.

Khi bounce/deferred thay đổi sau một deployment hoặc DNS update, nên so sánh cấu hình sender, From alignment, DKIM signing, IP/domain reputation và phản hồi provider. Không thay các record DNS tùy tiện chỉ vì một vài event bị lỗi.

## 24. Complaint rate và chính sách gửi email tùy chọn

Complaint là một tín hiệu chất lượng danh sách rất nhạy cảm. Khi complaint tăng, cần nhìn rộng hơn transport:

- Địa chỉ có thực sự đăng ký nhận nội dung không?
- Email có phù hợp với kỳ vọng lúc người dùng đăng ký không?
- Unsubscribe có dễ tìm và hoạt động không?
- Tần suất gửi có quá cao không?
- Có gửi lại cùng một campaign ngoài ý muốn do retry/replay không?
- Nội dung có khác quá xa so với mục đích đã được chấp thuận không?
- Provider có đang cung cấp complaint data đầy đủ hay chỉ từ một tập mailbox?

### Đừng “sửa” complaint rate bằng cách đổi mẫu số

Nếu complaint count tăng, thay mẫu số từ delivered sang all attempted hoặc thêm message chưa thực sự được gửi để tỷ lệ thấp đi sẽ làm mất tính nhất quán. Dashboard cần một định nghĩa thống nhất, có version và ghi rõ phạm vi quan sát.

### Có nên gửi email xác nhận unsubscribe?

Việc gửi một thông báo xác nhận thao tác tùy theo sản phẩm và chính sách. Không tự động coi đó là lý do tiếp tục gửi marketing. Nếu cần thông báo xác nhận, chỉ gửi nội dung liên quan đến thay đổi preference và tránh bổ sung quảng cáo.

### Complaint không phải chỉ số cá nhân

Không cố suy đoán danh tính người report spam nếu provider chỉ cung cấp dữ liệu tổng hợp. Phạm vi phản hồi hạn chế có thể là một quyết định bảo vệ quyền riêng tư của mailbox provider.

## 25. Bảo mật và bảo vệ dữ liệu deliverability

Provider event có thể chứa recipient address, reason text, message subject, provider ID, IP hoặc các trường khác có tính cá nhân. Ứng dụng cần quản lý như dữ liệu nhạy cảm vận hành.

### Bảo vệ webhook

- Xác minh chữ ký/authentication trước khi tin event.
- Giới hạn body size và số event mỗi request.
- Chống replay trong phạm vi provider hỗ trợ.
- Không dùng shared signing key của staging cho production.
- Rotate webhook signing keys theo quy trình phù hợp.
- Hạn chế tốc độ request và kiểm soát nguồn khi hữu ích, nhưng không chỉ tin IP allowlist như biện pháp duy nhất.
- Không hiển thị raw webhook payload trực tiếp trên UI không được bảo vệ.
- Cập nhật dependency/parser để tránh lỗi xử lý dữ liệu không tin cậy.

### Tránh giả mạo bounce

Email DSN/NDR nhận trong một mailbox có thể bị giả mạo. Nếu sử dụng inbound bounce processor, cần kiểm tra định dạng, nguồn và correlation token/identifier đủ tin cậy trước khi suppress địa chỉ. Không xóa người nhận khỏi danh sách chỉ vì nhận một email có subject “Mail Delivery Failed” do người ngoài gửi.

### Retention

Nên phân loại dữ liệu:

| Dữ liệu | Ví dụ chính sách |
| --- | --- |
| Provider event normalized | Giữ theo thời gian cần cho vận hành/audit |
| Raw provider webhook body | Giữ ngắn hoặc chỉ khi cần điều tra; bảo vệ và xóa theo retention |
| Complaint/suppression records | Giữ đủ để không gửi nhầm lại; xem xét yêu cầu quyền riêng tư |
| Metrics tổng hợp | Giữ dài hơn nếu không chứa PII và được phép |
| Email body/attachment | Không mặc định sao chép vào event store |
| SMTP diagnostic text | Làm sạch hoặc giới hạn quyền vì có thể chứa recipient/identifier |

Không có một thời gian lưu phù hợp với mọi tổ chức; phải theo mục đích nghiệp vụ, quy định áp dụng và chính sách bảo vệ dữ liệu.

### Logging có cấu trúc

Một log an toàn có thể như:

~~~json
{
  "event": "mail_delivery_event_processed",
  "notificationId": "notif-184",
  "providerKey": "primary-mail",
  "type": "BOUNCED",
  "reasonFamily": "INVALID_ADDRESS",
  "duplicate": false,
  "correlated": true
}
~~~

Không đưa full recipient address, token, SMTP password hoặc raw payload vào log khi không cần. Nếu cần tra cứu theo recipient, sử dụng ID nội bộ và công cụ có phân quyền.

## 26. Xử lý event khi provider gặp sự cố

Khi provider webhook bị gián đoạn, các message có thể vẫn được xử lý nhưng ứng dụng không nhận event kịp thời.

### Không tự thay UNKNOWN thành DELIVERED

Nếu event thiếu, để trạng thái UNKNOWN hoặc ACCEPTED_BY_PROVIDER và hiển thị event lag/reconciliation status. Không tạo giả một outcome tích cực để giảm số lượng UNKNOWN trên dashboard.

### Reconciliation bằng provider API/export

Nếu provider có API tra cứu event:

1. Xác định khoảng thời gian hoặc set message IDs cần đối chiếu.
2. Gọi API có rate limit, pagination và retry phù hợp.
3. Lưu event qua cùng pipeline dedup/projection như webhook.
4. Không tạo logic trạng thái riêng mâu thuẫn giữa webhook và polling.
5. Ghi dấu kết quả đối soát và số record vẫn chưa xác định.

Provider API có thể chỉ lưu event trong một thời hạn nhất định; lên lịch reconciliation trước khi dữ liệu ngoài hết retention.

### Provider gửi event theo batch sau outage

Khi webhook hoạt động lại, có thể có hàng chục nghìn event đến cùng lúc. Inbox phải lưu bền vững, consumer xử lý theo batch, bảo vệ database và giữ độ trễ hợp lý. Nếu số complaint tăng trong backlog, suppression cần được ưu tiên xử lý để tránh tiếp tục gửi marketing cho người đã khiếu nại.

### Chuyển provider

Khi chuyển SMTP provider, các ID và event name có thể thay đổi. Không nối event của hai provider chỉ bằng Message-ID nếu không bảo đảm duy nhất và mapping đúng. Giữ providerKey, account scope và attempt; chuẩn hóa event về model chung nhưng lưu source-specific fields cần thiết cho điều tra.

## 27. Kịch bản kiểm thử theo sự kiện

Kiểm thử cần có cả unit test cho projection và integration test cho webhook/inbox:

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| E01 | ACCEPTED rồi DELIVERED | Lưu cả hai event, projection phản ánh mốc delivered |
| E02 | ACCEPTED rồi DEFERRED rồi DELIVERED | Có deferral history, kết quả giao cuối không bị xóa |
| E03 | ACCEPTED rồi BOUNCED | Kết quả bounce và reason được lưu |
| E04 | DELIVERED rồi COMPLAINED | Giữ delivery evidence, set complained và suppression theo policy |
| E05 | DELIVERED webhook tới trước ACCEPTED | Accepted đến muộn không làm hồi quy projection |
| E06 | DEFERRED tới sau DELIVERED | Không đổi outcome hiện tại về deferred chỉ vì arrival order |
| E07 | Cùng complaint event được giao hai lần | Chỉ một logical complaint; suppression idempotent |
| E08 | Hai deferred events khác ID | Giữ cả hai, incidence tính theo unique recipient-message |
| E09 | Event không có provider ID hợp lệ | UNMATCHED/reconciliation, không ghép bừa |
| E10 | Webhook sai chữ ký | Không xử lý hoặc suppress |
| E11 | Inbox lưu thất bại | Không xác nhận thành công giả tạo với provider |
| E12 | Worker crash sau persist trước projection | Có thể replay event mà không mất side effect |
| E13 | Multi-recipient message với một bounce | Chỉ recipient tương ứng bị cập nhật |
| E14 | Provider accepted rồi deferred | Không gọi JavaMailSender gửi thêm nếu provider còn retry |
| E15 | Message outcome unknown rồi provider event tới | Reconcile đúng attempt và recipient |
| E16 | Complaint sau khi user unsubscribe | Giữ cả hai reason nếu phù hợp, không xóa lịch sử |
| E17 | Soft bounce rồi giao thành công | Không suppress vĩnh viễn chỉ vì transient event |
| E18 | Hard bounce rồi email khác cùng recipient | Dispatch policy suppress/validate lại đúng phạm vi |
| E19 | Provider webhook backlog lớn | Dedup, batch và metrics vẫn đúng |
| E20 | Unknown/new provider event type | Ghi nhận để xử lý, không crash toàn pipeline |

### Unit test projection với event đến trễ

~~~java
@Test
void delayedAcceptedEventDoesNotUndoDeliveredOutcome() {
    DeliveryProjection projection =
            DeliveryProjection.empty("notif-184", "recipient-42");

    projection.apply(deliveredEvent(
            "evt-2", "2026-11-10T09:03:00Z"));
    projection.apply(acceptedEvent(
            "evt-1", "2026-11-10T09:00:00Z"));

    assertEquals(
            DeliveryStatus.DELIVERED,
            projection.deliveryStatus());
    assertEquals(2, projection.eventCount());
}
~~~

Đây là pseudocode kiểu JUnit, dùng các helper/domain class do dự án định nghĩa. Unit test này kiểm tra quy tắc projection, không xác nhận webhook signature hay database unique constraint.

### Test idempotency với database

Cho hai consumer cùng xử lý một provider event ID. Với unique constraint và transaction đúng, cả hai không được tạo hai logical events hoặc áp dụng suppression hai lần. Mock repository đơn giản không chứng minh atomicity; cần integration test trên database thật hoặc môi trường tương đương.

### Test webhook signature

Với provider đã chọn, dùng payload và signing scheme trong test fixture được phép, bao gồm:

- Signature hợp lệ.
- Signature bị thay đổi.
- Payload bị sửa một byte.
- Timestamp quá hạn theo tolerance.
- Signing key được rotate.
- Thiếu header bắt buộc.
- Event trùng nhưng được giao lại hợp lệ.

Không tự “test HMAC” bằng cách dùng cùng một hàm tự viết tạo và xác minh signature rồi coi như đã tương thích với provider. Khi có thể, sử dụng test vector/SDK chính thức để chứng minh interoperability.

## 28. Runbook: bounce tăng bất thường

Khi hard bounce tăng mạnh:

1. Xem thay đổi theo provider, sender domain, template, campaign và recipient domain.
2. Phân biệt hard bounce với soft bounce/deferred và event giao trùng.
3. Đọc các nhóm SMTP response hoặc provider reason code đã làm sạch.
4. Kiểm tra nguồn danh sách, mức xác minh email và đợt import gần đây.
5. Kiểm tra sender authentication (SPF/DKIM/DMARC) và From identity nếu phù hợp.
6. Tạm dừng nguồn gửi đang tạo lỗi lớn nếu cần để giảm tác động.
7. Suppress địa chỉ được xác định hard-bounced theo policy.
8. Không retry vô hạn hoặc đổi provider để cố gửi vào địa chỉ chắc chắn không hợp lệ.
9. Theo dõi cohort mới sau khi sửa; không kết luận đã phục hồi chỉ vì số bounce mới giảm khi ứng dụng đã ngừng gửi hoàn toàn.
10. Ghi incident, thay đổi policy và kết quả xử lý.

### Nếu bounce tập trung vào một miền nhận

Kiểm tra khả năng lỗi cục bộ theo miền, policy rejection hoặc throttling. Không tự chuyển mọi recipient thuộc miền đó thành invalid nếu chưa đủ bằng chứng. Có thể giảm tốc gửi tới miền đó khi lỗi là rate-related và provider cho phép.

## 29. Runbook: deferred tăng hoặc giao thư chậm

Khi deferred hoặc delivery latency tăng:

1. Kiểm tra provider đang sở hữu retry hay application chưa submit được.
2. Xác định mã 4xx, enhanced status và domain liên quan.
3. Xem provider spool/queue age và số message accepted chưa có outcome.
4. Kiểm tra quota, tốc độ gửi và connection concurrency.
5. Nếu throttling, giảm throughput và tránh resend tạo duplicate.
6. Nếu DNS/network/provider outage, xử lý hạ tầng theo nhóm chịu trách nhiệm.
7. Theo dõi tỷ lệ deferred chuyển sang delivered hoặc bounced.
8. Alert khi email quan trọng vượt SLA; cân nhắc kênh thay thế theo chính sách.
9. Khi provider phục hồi, không xả toàn bộ backlog qua send() mới.

Một event DEFERRED riêng lẻ không đủ lý do để đánh dấu địa chỉ xấu. Chỉ khi provider ghi nhận thất bại cuối, hoặc chính sách nghiệp vụ có ngưỡng rõ, mới đưa ra quyết định thích hợp.

## 30. Runbook: complaint tăng

Với complaint spike, phản ứng nên nhanh và dựa trên dữ liệu:

1. Xác minh event source và loại bỏ duplicate webhook.
2. Xác định campaign/template, sender domain, đối tượng và nguồn danh sách.
3. Suppress marketing cho recipient có complaint được xác nhận.
4. Tạm dừng hoặc giảm campaign gây complaint khi cần.
5. Kiểm tra consent và khả năng unsubscribe.
6. Xem lại nội dung, tần suất, mức độ cá nhân hóa và kỳ vọng của người nhận.
7. Kiểm tra có lỗi retry/replay khiến người nhận được gửi nhiều lần không.
8. Theo dõi complaint rate theo cohort/mẫu số cố định và phạm vi provider cung cấp.
9. Ghi lại những thay đổi và quy trình phê duyệt trước khi mở lại campaign.

Không cố “khắc phục” bằng cách xóa dữ liệu complaint hoặc loại bỏ event khỏi dashboard. Complaint là phản hồi thật cần được xử lý theo chính sách.

## 31. Những sai lầm thường gặp

### 31.1. Log delivered ngay sau JavaMailSender.send()

Hành động này đánh đồng SMTP submission với việc giao tới recipient. Ghi SUBMITTED/ACCEPTED_BY_RELAY rồi theo dõi downstream event.

### 31.2. Coi accepted là terminal success

Provider có thể accepted rồi bounce. Phải xác định accepted ở chặng nào.

### 31.3. Coi deferred là bounced

Deferred có thể được retry rồi delivered. Giữ trạng thái tạm thời và quan sát outcome cuối.

### 31.4. Gửi lại một message mới khi nhận deferred

Nếu provider vẫn đang retry, gửi lại tạo luồng song song và nguy cơ duplicate. Xác định trách nhiệm retry ở từng chặng.

### 31.5. Đếm số event như số message

Một message có thể có nhiều deferrals hoặc duplicate webhook. Tính unique recipient-message cho các tỷ lệ incidence.

### 31.6. Cập nhật status bằng webhook cuối cùng nhận được

Webhook đến sai thứ tự có thể làm DELIVERED trở lại DEFERRED. Lưu event timeline và projection theo semantics.

### 31.7. Gộp trạng thái của nhiều recipient

Một email nhiều người nhận có thể chỉ bounce ở một địa chỉ. Projection và suppression phải có recipient scope.

### 31.8. Không lưu provider message ID

Khi nhận webhook rất khó tương quan nếu chỉ có subject và địa chỉ. Lưu mapping từ attempt tới provider ID khi có thể.

### 31.9. Tin webhook chưa xác thực

Kẻ tấn công có thể giả COMPLAINED hoặc BOUNCED để suppress địa chỉ. Xác minh chữ ký và account scope.

### 31.10. Trả 200/202 trước khi lưu event bền vững

Process có thể dừng và mất event. Chỉ acknowledge khi có bảo đảm lưu trữ theo hợp đồng.

### 31.11. Suppress vĩnh viễn mọi soft bounce

Một lỗi tạm thời có thể hồi phục. Dùng chính sách dựa trên reason, số lần, thời gian và provider.

### 31.12. Bỏ qua complaint sau delivered

Complaint là feedback độc lập và có thể xuất hiện sau delivery confirmation. Lưu cả hai.

### 31.13. Không kiểm tra unsubscribe trước khi dispatch marketing

Recipient có thể unsubscribe/complain trong lúc job chờ. Worker phải kiểm tra preference/suppression hiện tại.

### 31.14. Dùng số liệu hôm nay cho cả tử và mẫu mà không cohort

Bounce hôm nay có thể thuộc email hôm qua. Tính theo cohort và cửa sổ thời gian đã định nghĩa.

### 31.15. Không tính phạm vi feedback loop

Complaint data có thể chỉ đến từ một số mailbox provider. Không tuyên bố tỷ lệ này đại diện cho mọi người nhận.

### 31.16. Dùng event time không đáng tin để ghi đè trạng thái

Thứ tự giữa các provider/attempt không luôn suy ra chỉ từ timestamp. Cần correlation và semantics nguồn.

### 31.17. Lưu toàn bộ raw event vô thời hạn

Payload có thể chứa PII. Thiết lập retention, quyền truy cập và chỉ giữ phần cần thiết.

### 31.18. Xem delivered như người nhận đã đọc

Delivered thường biểu thị mốc ở hệ thống nhận, không có nghĩa inbox hoặc hành vi đọc. Open tracking cũng không đáng tin tuyệt đối vì proxy/cache/chặn ảnh.

## 32. Quy trình triển khai từ đầu

Để xây hệ thống quan sát deliverability trong Spring Framework Mail:

1. **Chọn nguồn kết quả:** webhook provider, export API, relay log hoặc DSN/bounce mailbox.
2. **Đọc rõ semantics:** xác định accepted/delivered/deferred/bounced/complained của từng provider.
3. **Thiết kế correlation:** notification ID, attempt ID, provider message ID và recipient key.
4. **Lưu outbox/submission riêng:** không dùng provider event để thay trạng thái transaction nghiệp vụ.
5. **Tạo secure ingress:** xác thực webhook trên raw payload; giới hạn kích thước và chống replay.
6. **Lưu event bền vững:** acknowledgement sau khi lưu thành công.
7. **Deduplicate:** dùng provider event ID có scope và unique constraint phù hợp.
8. **Xử lý out-of-order:** giữ event history, projection source-specific, reconciliation cho event unmatched.
9. **Áp dụng suppression:** hard bounce/complaint/unsubscribe theo reason và category, có audit.
10. **Thiết kế metrics:** unique recipient-message, mẫu số, cohort và event lag rõ.
11. **Kiểm thử:** giao trùng, đảo thứ tự, kết quả mâu thuẫn, multi-recipient, provider outage.
12. **Thiết lập runbook:** alert theo bounce, deferred, complaint và webhook health.
13. **Đánh giá privacy:** dữ liệu PII trong event/log, retention và quyền truy cập.
14. **Vận hành có đối soát:** sử dụng provider export khi cần để kiểm tra event thiếu hoặc đến trễ.

### Mẫu bảng quyết định nhanh

| Khi nhận được | Có gọi JavaMailSender gửi lại ngay? | Hành động chính |
| --- | --- | --- |
| ACCEPTED | Không | Ghi nhận mốc và chờ downstream outcome |
| DEFERRED do provider đang retry | Không | Theo dõi lý do, thời gian, provider queue |
| BOUNCED permanent | Không | Ghi nhận failure/suppression và điều tra |
| BOUNCED temporary/final theo provider | Không retry mù | Xem provider policy và nguyên nhân trước quyết định |
| COMPLAINED | Không | Suppress marketing và xử lý phản hồi |
| Chưa submit được do SMTP lỗi ở ứng dụng | Có thể retry theo outbox policy | Backoff, rate limit và idempotency |
| SUBMISSION_UNKNOWN | Không tự retry mù | Reconcile hoặc xử lý duplicate risk |

## 33. Câu hỏi tự kiểm tra

**1. JavaMailSender.send() thành công có chứng minh email đã tới inbox không?**

Không. Thông thường nó chỉ cho biết SMTP submission sang relay đã thành công theo phản hồi mà ứng dụng nhận được. Remote delivery, spam filtering và việc người nhận đọc thư là những giai đoạn khác.

**2. Accepted có thể xảy ra trước bounced không?**

Có. Outbound relay có thể accepted message rồi trả lại DSN/bounce sau khi không thể giao đến hệ thống đích.

**3. Deferred có phải lỗi cuối không?**

Không nhất thiết. Nó thường là sự kiện giao thư tạm bị trì hoãn và provider có thể tự retry.

**4. Vì sao không gửi lại ngay khi nhận deferred?**

Vì provider có thể vẫn sở hữu bản accepted và đang retry. Gửi lại tạo nhiều bản hoặc tăng tải không cần thiết.

**5. Hard bounce khác soft bounce như thế nào?**

Hard bounce thường được coi là lỗi không thể phục hồi cho yêu cầu/địa chỉ hiện tại; soft bounce thường tạm thời. Phân loại cụ thể phải dựa trên event và semantics provider.

**6. Complaint có nghĩa là email chưa giao được không?**

Không. Complaint thường là phản hồi người nhận báo thư không mong muốn và có thể xuất hiện sau khi email đã delivered.

**7. Nếu webhook không gửi COMPLAINED, có thể kết luận không ai report spam không?**

Không. Feedback loop không phủ mọi mailbox và provider có thể chỉ cho số liệu tổng hợp.

**8. Vì sao lưu provider message ID?**

Để tương quan event nhận sau với đúng delivery attempt; subject và email address không đủ xác định duy nhất.

**9. Cùng một event webhook có thể đến nhiều lần không?**

Có. Provider có thể retry theo cơ chế at-least-once. Cần idempotency key/unique constraint.

**10. Event DELIVERED đến trước event ACCEPTED thì nên làm gì?**

Lưu cả hai và projection không được hồi quy từ DELIVERED về ACCEPTED chỉ vì webhook accepted đến sau.

**11. Vì sao recipient-level tracking quan trọng?**

Vì trong một message nhiều người nhận, mỗi người có thể có kết quả riêng; bounce của một recipient không nên áp lên mọi recipient.

**12. Có nên tính một message deferred ba lần thành ba email bị deferred không?**

Nếu metric là unique deferral incidence thì không: đó là một recipient-message từng deferred. Nếu metric đếm raw deferral events thì có thể là ba; phải ghi rõ định nghĩa.

**13. Bounce rate nên dùng mẫu số gì?**

Một mẫu số được định nghĩa rõ và nhất quán theo cohort/đơn vị, chẳng hạn accepted recipient-messages. Không có công thức duy nhất áp dụng cho mọi provider.

**14. Vì sao dùng cohort thay cho chỉ tính event nhận hôm nay?**

Vì bounce và complaint có thể đến nhiều giờ/ngày sau khi email được gửi; tử và mẫu tính theo ngày nhận event có thể không đại diện cùng một tập email.

**15. Webhook cần kiểm tra những gì trước khi suppress recipient?**

Xác thực nguồn, tính toàn vẹn payload, event type, account/provider scope và correlation recipient/attempt.

**16. Nếu webhook lưu vào memory rồi trả 202 thì có an toàn không?**

Không bảo đảm. Process có thể chết sau khi acknowledge. Nên persist event hoặc queue bền vững trước khi trả thành công.

**17. Khi nào cần đánh dấu SUBMISSION_UNKNOWN?**

Khi không biết chắc relay đã nhận thông điệp hay chưa, ví dụ kết nối mất sau DATA trước phản hồi cuối.

**18. Delivered khác opened như thế nào?**

Delivered là mốc hệ thống giao thư theo provider; opened là tín hiệu tương tác/hiển thị không hoàn toàn đáng tin và không chứng minh người nhận thực sự đọc.

**19. Complained có nhất thiết làm ngừng mọi email bảo mật không?**

Không có quy tắc chung. Nên suppress email marketing/tùy chọn theo policy và xem xét quyền nhận, xác thực địa chỉ, nghĩa vụ thông báo và kênh thay thế cho email giao dịch/bảo mật.

**20. Khi provider đổi tên event, nên sửa logic ở đâu?**

Ở adapter/mapper provider, không rải điều kiện tên event khắp business service. Lưu source event type và mapping version phục vụ điều tra.

## Kết luận

**Theo dõi accepted, bounced, deferred và complained là theo dõi vòng đời email sau khi ứng dụng Spring Mail đã submit, chứ không chỉ đo JavaMailSender.send() có ném exception hay không.** Accepted cần được gắn với đúng ranh giới relay/provider; bounced phải phân loại lý do và recipient; deferred là tín hiệu tạm thời và thường do provider tự retry; complained là phản hồi tiêu cực cần dẫn đến xử lý suppression và chất lượng gửi. Để vận hành đáng tin cậy, hãy lưu notification ID, attempt ID, provider message ID và recipient; nhận webhook/DSN qua đường tin cậy; lưu event bền vững; deduplicate và xử lý event đến trễ/sai thứ tự bằng timeline cùng projection. Dashboard phải dùng cohort, mẫu số, nguồn dữ liệu và event lag rõ ràng; runbook cần phản ứng khác nhau trước bounce, deferral và complaint. **Một hệ thống deliverability tốt không khẳng định đã giao thư khi chưa có bằng chứng, không gửi lại khi provider vẫn đang retry và không bỏ qua tín hiệu người nhận không mong muốn.**
