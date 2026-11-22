# Tần suất gửi và tín hiệu người nhận trong Spring Framework Mail

Một ứng dụng Spring có thể tạo MIME hợp lệ, xác thực SMTP thành công và nhận phản hồi chấp nhận của relay, nhưng email vẫn có thể vào Spam/Junk, bị trì hoãn hoặc không được người nhận quan tâm. **Deliverability** không chỉ là kết quả của lời gọi `JavaMailSender.send(...)`. Nó còn liên quan đến danh tiếng người gửi, chất lượng danh sách, nội dung, **tần suất gửi** và **các tín hiệu phản hồi của người nhận**.

Nếu liên tục gửi vào một hộp thư, gửi một chiến dịch lớn mà không điều tiết hoặc tiếp tục gửi cho người đã hủy đăng ký, hệ thống vừa tạo trải nghiệm kém vừa có thể tác động tiêu cực đến khả năng giao thư. Ngược lại, gửi đúng nhu cầu, đúng nhịp, tôn trọng preferences và phản ứng sớm với bounce/complaint là nền tảng vận hành lành mạnh.

Trong Spring Framework Mail, `JavaMailSender` phụ trách chuyển message qua SMTP. Thư viện không tự quyết định một người nên nhận bao nhiêu newsletter mỗi tuần, không tự biết họ đã unsubscribe và không có một thuật toán phổ quát dự đoán Inbox placement. Những phần đó thuộc **application policy, notification workflow và sự kiện từ provider**.

Bài này trình bày cách kiểm soát tần suất theo từng người nhận, phân bổ lượng gửi theo thời gian, đọc tín hiệu tích cực/tiêu cực một cách thận trọng và triển khai vào ứng dụng Spring qua các service, outbox, rate limiter và webhook.

## 1. Phân biệt tần suất, tốc độ và khả năng giao thư

Ba khái niệm thường bị gộp lại:

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Send rate** | Hệ thống gửi bao nhiêu message mỗi giây/phút? | 20 SMTP submissions/giây |
| **Recipient frequency** | Một người nhận được liên hệ bao nhiêu lần và cách nhau bao lâu? | Không quá N marketing mail trong một cửa sổ |
| **Pacing** | Phân bố một campaign theo thời gian ra sao? | Chia thành các batch nhỏ |
| **Deliverability** | Thư có được tiếp nhận và đưa đến nơi có thể đọc không? | Delivered, deferred, filtered |
| **Engagement** | Có tín hiệu người nhận quan tâm không? | Click, reply, hành động trong sản phẩm |
| **Negative signal** | Có phản hồi cho thấy không mong muốn hoặc không thể giao không? | Bounce, complaint, unsubscribe |

Một ứng dụng có thể tuân thủ rate limit của SMTP provider nhưng vẫn gửi quá dày tới cùng một cá nhân. Ngược lại, ứng dụng có frequency cap hợp lý nhưng gửi 50.000 email vào một phút vẫn có thể vượt quota hoặc gây deferral.

**Send rate giới hạn hạ tầng; recipient frequency giới hạn mức độ làm phiền từng người.** Hai loại giới hạn cần được quản lý độc lập.

## 2. SMTP submission không phải Inbox delivery

Luồng cơ bản:

~~~text
Business event / campaign
        |
        v
Consent + suppression + frequency policy
        |
        v
Outbox / queue
        |
        v
JavaMailSender / SMTP
        |
        v
SMTP relay accepts message
        |
        v
Downstream filtering / destination provider
        |
        +--> Delivered
        +--> Deferred
        +--> Bounced
        +--> Spam/quarantine
        |
        v
Người nhận có thể tương tác
        |
        +--> Reply / click / unsubscribe / complaint
~~~

Khi `JavaMailSender.send(...)` trả về bình thường, transport thường đã hoàn thành thao tác submission theo hợp đồng thư viện. Không thể suy ra thư đã đến Inbox hoặc được đọc.

| Trạng thái | Ý nghĩa |
| --- | --- |
| `QUEUED` | Yêu cầu gửi đã được lưu hoặc đưa vào hàng đợi |
| `SUBMITTED` | Transport/SMTP relay chấp nhận submission |
| `DELIVERED` | Có tín hiệu delivery từ provider theo định nghĩa của họ |
| `DEFERRED` | Downstream tạm trì hoãn giao thư |
| `BOUNCED` | Có báo cáo không giao được |
| `COMPLAINED` | Có tín hiệu người nhận báo spam |
| `UNSUBSCRIBED` | Người nhận yêu cầu ngừng loại thư |
| `OPENED`/`CLICKED` | Có tín hiệu tracking, không nhất thiết là người thật đã tương tác |

Một số SMTP relay không cung cấp delivery webhook. Spring Mail không tự tạo sự kiện `delivered`, `opened` hay `complained`; muốn có chúng phải tích hợp nguồn dữ liệu provider hoặc hệ thống bounce/inbound phù hợp.

## 3. Vì sao tần suất có thể ảnh hưởng deliverability?

Tần suất gửi liên quan tới:

- **Kỳ vọng của người nhận:** đã đăng ký newsletter tuần không đồng nghĩa muốn nhận khuyến mãi mỗi giờ.
- **Mức độ quan tâm:** email quá nhiều có thể khiến người dùng bỏ qua hoặc hủy đăng ký.
- **Complaint:** thư không được mong đợi có thể bị báo spam.
- **Reputation:** hạ tầng nhận có thể dùng lịch sử gửi và tín hiệu tiêu cực để đánh giá người gửi.
- **Quota:** burst volume có thể tạo throttling hoặc temporary rejection.
- **Queue latency:** newsletter gửi dồn có thể làm OTP, xác nhận đơn hàng bị trễ nếu dùng chung hàng đợi.

Không tồn tại một con số tần suất “tốt nhất” cho mọi ngành, provider và danh sách. Lịch gửi phù hợp phụ thuộc loại email, consent, nội dung, lịch sử tương tác và giới hạn vận hành.

Mục tiêu không phải tăng số message bằng mọi giá, mà là **mỗi email có mục đích rõ, đúng nhu cầu và không vượt kỳ vọng hợp lý của người nhận**.

## 4. Phân loại thư trước khi đặt frequency cap

| Loại email | Ví dụ | Chính sách thường cần |
| --- | --- | --- |
| **Security** | OTP, cảnh báo đăng nhập, reset password | Kịp thời, anti-abuse và rate limit riêng |
| **Transactional** | Xác nhận đơn hàng, hóa đơn | Gắn sự kiện thật, dedup theo event |
| **Operational** | Báo cáo định kỳ, cảnh báo kỹ thuật | Gom digest, phân loại severity |
| **Lifecycle** | Onboarding, nhắc hoàn thành bước | Khoảng cách hợp lý giữa các bước |
| **Marketing** | Newsletter, ưu đãi | Consent, preferences, frequency cap và unsubscribe |
| **Bulk campaign** | Gửi hàng loạt tới danh sách đã đăng ký | Pacing, segmentation và provider quota |

Không áp một cap marketing cứng cho email bảo mật thực sự cần thiết. Nhưng cũng không vì gắn nhãn “transactional” mà cho gửi không giới hạn. Ví dụ một sự kiện `OrderConfirmed` bị publish trùng 100 lần phải được chống lặp bằng idempotency.

OTP cần anti-abuse theo user, IP hoặc action. Email marketing phải dựa trên consent và preference phù hợp, không lách quy tắc bằng cách đổi nhãn category.

## 5. Recipient cap phải tính xuyên các chiến dịch

Giả sử trong cùng một ngày:

~~~text
08:00   Bản tin sản phẩm
11:00   Ưu đãi riêng
16:00   Nhắc hoàn tất khảo sát
~~~

Mỗi campaign có thể tự thấy rằng người nhận chưa nhận email của **chiến dịch đó**. Nhưng tổng cộng người nhận vẫn nhận ba marketing mail.

~~~text
Campaign A ----+
Campaign B ----+--> Global marketing cap
Campaign C ----+           |
                          v
                     ALLOW / DEFER / SUPPRESS
~~~

Có thể đặt giới hạn theo:

- Recipient và category.
- Recipient và campaign.
- Recipient và workflow/journey.
- Global marketing frequency.
- Tenant/account.
- Recipient domain.
- Provider/sender account.

Tránh tạo quá nhiều cap không có quy tắc ưu tiên, vì một notification có thể được nhiều cap cho phép/từ chối khác nhau. Cần định nghĩa điều gì xảy ra khi một cap hết slot nhưng cap khác còn chỗ.

## 6. Calendar window, rolling window và minimum gap

Frequency cap có nhiều cách diễn đạt:

| Cơ chế | Cách tính | Lưu ý |
| --- | --- | --- |
| Calendar day | Theo một ngày trong timezone định nghĩa | Có thể burst quanh nửa đêm |
| Calendar week | Theo tuần của locale/policy | Cần rõ ngày bắt đầu tuần |
| Rolling 24 hours | 24 giờ trước thời điểm hiện tại | Tránh ranh giới ngày gây burst |
| Rolling 7 days | Bảy ngày gần nhất | Cần lịch sử hoặc cơ chế đếm phù hợp |
| Minimum gap | Cách email gần nhất ít nhất X giờ | Không giới hạn tổng volume theo tuần |
| Token bucket | Rate trung bình và burst allowance | Phù hợp vận chuyển hơn là consent cadence |

Một cấu hình minh họa:

~~~yaml
app:
  mail:
    frequency:
      marketing:
        max-per-day: 1
        max-per-week: 3
      onboarding:
        minimum-gap-hours: 24
~~~

Đây **không phải default của Spring hoặc khuyến nghị cố định cho mọi hệ thống**. Đó là ví dụ về policy do ứng dụng tự xây.

Nếu tính “mỗi ngày theo địa phương”, dùng timezone có định danh đầy đủ như `Asia/Ho_Chi_Minh` hoặc `Europe/Paris`. Không coi cộng 24 giờ lúc nào cũng đồng nghĩa “ngày mai cùng giờ” khi có daylight saving time.

## 7. Đếm lúc enqueue hay lúc gửi thành công?

Cần xác định rõ frequency cap đo **số notification logic**, không nhất thiết đo số lần gọi SMTP.

Các mốc có thể dùng:

1. Khi notification được duyệt và **reserve slot**.
2. Khi notification được enqueue vào outbox.
3. Khi SMTP submission thành công.
4. Khi provider báo delivered.

Nếu chỉ tăng counter sau SMTP success, hai campaign đồng thời có thể cùng nhìn thấy “còn slot” và tạo các job vượt cap. Vì vậy, với hệ thống đồng thời, nên **reserve atomically trước khi enqueue**.

Một notification có thể retry SMTP nhiều lần nhưng vẫn chỉ là một email logic; retry không nên tiêu tốn nhiều recipient-frequency slots.

Nếu job bị hủy trước khi gửi, có thể giải phóng reservation theo policy. Với SMTP outcome `AMBIGUOUS`, nên thận trọng vì server có thể đã nhận, dù worker chưa biết.

## 8. Consent và preferences đứng trước frequency

Frequency cap không thay thế quyền được gửi.

~~~text
Có yêu cầu gửi
      |
      v
Recipient có được liên hệ cho category này?
      |
   +--+--+
   |     |
 Không  Có
   |     |
   v     v
Suppress  Có hard-bounce/complaint suppression?
             |
          +--+--+
          |     |
         Có    Không
          |     |
          v     v
       Suppress  Frequency cap?
                  |
              +---+----+
              |        |
            Đầy      Còn slot
              |        |
              v        v
          Defer/skip   Reserve + enqueue
~~~

Một người đã unsubscribe khỏi marketing không nên tiếp tục nhận marketing chỉ vì cap còn chỗ. Ngược lại, việc hủy marketing không tự động có nghĩa phải dừng mọi email bảo mật/giao dịch hợp pháp. Cần định nghĩa phạm vi preference và suppression.

### Kiểm tra lại trước khi submit

Một email có thể được xếp lịch nhiều giờ trước:

~~~text
09:00 Campaign được enqueue
10:00 Người dùng unsubscribe
11:00 Worker chuẩn bị gửi
          |
          v
   Kiểm tra preference hiện tại
          |
          v
       Suppress marketing
~~~

Nếu chỉ kiểm tra consent một lần khi enqueue, hệ thống có thể vẫn gửi sau khi người nhận đã yêu cầu dừng. Với marketing mail, nên kiểm tra lại suppression gần thời điểm submit.

## 9. Pacing để không gửi dồn

Một campaign có danh sách lớn không nhất thiết phải gửi toàn bộ vào thời điểm nhấn nút.

Pacing là cách phân bố việc gửi qua nhiều batch hoặc khoảng thời gian:

~~~text
Campaign approved
       |
       v
Segment người nhận đủ điều kiện
       |
       v
Đặt rate/concurrency budget
       |
       +--> Batch A
       +--> Batch B
       +--> Batch C
       +--> ...
       |
       v
Quan sát kết quả trước khi tăng nhịp
~~~

Lợi ích:

- Giảm burst lên SMTP/provider.
- Phân bổ tải worker.
- Có cơ hội phát hiện bounce/complaint tăng sớm.
- Tránh newsletter làm trễ transactional email.
- Điều chỉnh theo cooldown của provider.

Pacing kiểm soát **cách giải ngân volume**; recipient cap kiểm soát **mỗi người được gửi bao nhiêu**. Chúng không thay thế nhau.

## 10. Warm-up khi sender hoặc domain mới tăng volume

Một domain, IP hoặc account mới có thể chưa có nhiều lịch sử gửi với các hệ thống nhận. Tăng volume đột ngột dễ gặp bất ổn hơn tăng có kiểm soát.

Warm-up nên dựa trên:

- Danh sách có consent và dữ liệu sạch.
- Nội dung người nhận mong đợi.
- Volume tăng theo khả năng thực tế.
- Bounce, deferral và complaint đang được theo dõi.
- Cấu hình sender identity và authentication thích hợp.
- Dừng tăng khi tín hiệu xấu.

Không có lịch warm-up bảo đảm Inbox placement chung cho mọi mailbox provider. Danh tiếng có thể liên quan account, IP, domain và các yếu tố khác. Warm-up không phải thủ thuật đánh lừa bộ lọc; nó là cách triển khai gửi có trách nhiệm với khả năng quan sát.

## 11. Transport limit khác recipient limit

Các quota của provider có thể được tính theo:

- SMTP messages/second.
- Recipients/minute.
- Active connections.
- Daily quota theo account.
- Domain-specific throttling.
- Message size và attachment limits.

Những giới hạn này nằm ở tầng transport:

~~~text
Application:
  Consent + suppression + recipient frequency

Dispatcher:
  Provider rate + max concurrency + backoff

Transport:
  JavaMailSender + SMTP
~~~

Một limiter chỉ nằm trong mỗi JVM không đảm bảo tổng quota nếu ứng dụng chạy nhiều instance. Nếu mỗi instance cho phép 20 gửi/giây và có 10 instances, tổng có thể lớn hơn mức provider cho phép. Với quota toàn cục, cần limiter/shared scheduler hoặc phân bổ budget có kiểm soát.

## 12. Tín hiệu người nhận và mức độ tin cậy

| Tín hiệu | Nguồn | Ý nghĩa | Cần thận trọng |
| --- | --- | --- | --- |
| Hard bounce | Provider/DSN | Không giao được theo lỗi rõ | Phân loại đúng lý do |
| Soft bounce/deferred | Provider/SMTP | Tạm thời chưa giao | Có thể phục hồi |
| Spam complaint | Feedback event | Người nhận báo spam | Có thể không quan sát đủ mọi provider |
| Unsubscribe | Preference center/link | Yêu cầu dừng thư | Phải tôn trọng scope |
| Reply | Inbound mailbox/CRM | Có tương tác qua thư trả lời | Có auto-reply/bounce |
| Click | Tracking/link | URL được truy cập | Bot/security scanner có thể click |
| Open | Tracking pixel | Ảnh được tải | Proxy/cache/privacy protection |
| Conversion | Hành vi trong sản phẩm | Có hành động theo mục tiêu | Attribution không chắc chắn |
| Không có tương tác quan sát được | Thiếu event | Chưa có bằng chứng tương tác | Không chứng minh người dùng không đọc |

Tín hiệu “không mở” yếu hơn rất nhiều so với một yêu cầu unsubscribe rõ ràng. Đừng để một chỉ số engagement gián tiếp ghi đè quyền kiểm soát của người nhận.

## 13. Hard bounce và danh sách suppression

Hard bounce thường là lỗi giao thư mang tính vĩnh viễn như mailbox không tồn tại, nhưng cách provider đặt nhãn có thể khác nhau. Không dùng riêng mã `550` để tự động kết luận recipient không tồn tại: một số rejection liên quan sender policy hoặc content.

Khi có hard bounce đáng tin:

1. Đối chiếu provider message ID, notification ID và recipient.
2. Lưu failure code và sự kiện gốc.
3. Suppress địa chỉ theo phạm vi hợp lý.
4. Không tiếp tục gửi cùng loại thư tới địa chỉ lỗi.
5. Có quy trình sửa/verify địa chỉ mới.
6. Phân biệt lỗi recipient và lỗi sender/provider policy.

Nếu một user đổi email address, hard bounce của địa chỉ cũ không nhất thiết làm địa chỉ mới mất quyền nhận. Thiết kế suppression có scope theo email address, user hoặc category cho rõ ràng.

## 14. Soft bounce, deferral và việc retry

Soft bounce hoặc deferred thường phản ánh tạm thời chưa giao được, có thể do mailbox đầy, provider bận hoặc giới hạn lưu lượng.

Cần phân biệt:

- SMTP server **từ chối submission tạm thời** trước khi chấp nhận DATA: application worker có thể cần retry.
- SMTP relay **đã chấp nhận submission** rồi báo deferred downstream: provider có thể tự đang retry delivery. Ứng dụng không nên lập tức submit bản thứ hai.

Khi deferral tăng:

- Giảm tốc độ tới provider/domain tương ứng.
- Tôn trọng cooldown/throttling guidance.
- Kiểm tra account quota và sender reputation.
- Theo dõi provider delivery events.
- Không retry nóng tất cả message.
- Không suppress vĩnh viễn khi chưa có bằng chứng permanent failure.

Đây là lý do cần tách trạng thái `SUBMITTED` khỏi `DELIVERED` trong application.

## 15. Spam complaint là tín hiệu mạnh

Complaint xuất hiện khi người nhận báo email không mong muốn qua mailbox provider. Khả năng nhận feedback khác nhau theo nhà cung cấp, nhưng khi có complaint đáng tin, ứng dụng cần phản ứng nhanh.

Một luồng xử lý:

~~~text
Provider sends complaint event
           |
           v
Webhook verifies authenticity
           |
           v
Correlate recipient / notification
           |
           v
Deduplicate event
           |
           v
Suppress relevant marketing scope
           |
           v
Review cadence, list source, content
~~~

Spam complaint không nên chỉ được dùng để tăng một counter báo cáo. Nếu campaign vẫn đang chạy, suppression phải ảnh hưởng các email chưa gửi.

Một chiến dịch có nhiều click nhưng cũng nhiều complaint không nên được xem là thành công chỉ dựa trên click rate.

## 16. Unsubscribe và preference center

Unsubscribe là tín hiệu trực tiếp: người nhận không muốn tiếp tục nhận một loại thông báo. Hệ thống nên có cơ chế rõ ràng cho:

- Hủy một newsletter cụ thể.
- Hủy mọi marketing mail.
- Chọn tần suất thưa hơn.
- Chọn chủ đề quan tâm.
- Tạm dừng nhận email trong khoảng thời gian nếu sản phẩm hỗ trợ.

Đối với bulk marketing, các hệ thống thường dùng link unsubscribe dễ tìm và có thể dùng header `List-Unsubscribe` / `List-Unsubscribe-Post` theo tiêu chuẩn và chính sách nhà cung cấp tương ứng. Không chỉ đặt header mà quên xây endpoint cập nhật preference thực sự.

Cần thiết kế link/token hủy đăng ký an toàn, chống giả mạo/lạm dụng, và kiểm tra tình trạng preference khi worker gửi. Quy định về consent, retention và unsubscribe khác nhau theo thị trường; ứng dụng phải tuân thủ yêu cầu áp dụng, không thay thế chúng bằng một frequency cap.

## 17. Open rate: tín hiệu gián tiếp có nhiều sai lệch

Open tracking thường dùng một ảnh pixel trong HTML; khi ảnh được tải, hệ thống ghi một request và suy đoán email đã mở.

Nhưng:

- Một số email clients chặn ảnh.
- Privacy proxies có thể tự tải/cache ảnh.
- Email có thể được đọc mà không tải pixel.
- Security scanners có thể truy cập asset.
- Nhiều lần mở không nhất thiết tạo nhiều request.
- Thư plain text không có pixel tracking.

Vì vậy:

- `OPENED` chỉ nói rằng hệ thống nhận thấy tín hiệu tải ảnh phù hợp.
- `NOT_OPENED` chỉ nói rằng không quan sát thấy sự kiện.
- Không dùng open rate đơn độc để đánh giá Inbox placement.
- Không loại recipient ngay chỉ vì không có open event.
- Không tăng gửi marketing chỉ vì open rate bị tăng bởi proxy.

Vấn đề tracking còn liên quan quyền riêng tư. Chỉ thu thập dữ liệu cần thiết và có căn cứ/consent theo chính sách áp dụng.

## 18. Click rate: tốt hơn trong vài trường hợp, nhưng vẫn không hoàn hảo

Click event thường xuất hiện khi người dùng hoặc hệ thống bảo mật truy cập một URL trong email. Security gateway có thể tự mở link để quét rủi ro, khiến click event xuất hiện dù người dùng chưa click.

Vì vậy:

- Dùng unique recipient click thay vì chỉ raw click count khi đo engagement.
- Tách bot/scanner traffic nếu có tín hiệu đáng tin.
- Đối chiếu với hành động thực trong ứng dụng.
- Không coi click là conversion chắc chắn.
- Không đo “người thật đã đọc” chỉ bằng click.

### Link không được kích hoạt hành động nguy hiểm bằng GET

Security scanner có thể tự mở URL. Vì vậy, không thiết kế link email sao cho một GET request tự động chuyển tiền, xóa tài khoản hoặc hoàn tất hành động nhạy cảm. Cần bước xác nhận, token hợp lệ, kiểm tra session/quyền và phương thức request phù hợp.

## 19. Reply và hành vi trong sản phẩm

Reply có thể là tín hiệu quan tâm, nhưng không phải mọi thư trả lời đều do người thật gửi.

Phân biệt:

- Reply có nội dung từ người dùng.
- Auto-reply/out-of-office.
- Bounce report.
- Thư từ mailing list.
- Ticket hỗ trợ do hệ thống tạo.
- Reply mang nội dung khiếu nại/hủy đăng ký.

Nếu có inbound mail integration, cần phân loại và xử lý reply theo mục đích, không tự lấy toàn bộ nội dung riêng tư cho marketing analytics khi không cần.

Các tín hiệu nghiệp vụ như đăng nhập sau email, hoàn tất onboarding hoặc sử dụng tính năng có thể hữu ích. Nhưng conversion attribution cần được định nghĩa rõ: một sự kiện xảy ra sau email không chứng minh email là nguyên nhân duy nhất.

## 20. Thứ tự ưu tiên của tín hiệu

Một hệ thống nên ưu tiên:

1. Suppression và yêu cầu unsubscribe/complaint.
2. Consent và recipient preferences.
3. Business validity (email còn phù hợp, token còn hạn).
4. Frequency cap và quiet hours.
5. Provider rate quota/cooldown.
6. Engagement-based optimization.

Ví dụ: người đã unsubscribe không nên nhận newsletter dù trước đây họ click nhiều. Địa chỉ hard bounce không nên được phép nhận thêm chỉ vì một open pixel cũ tồn tại.

Dữ liệu engagement là công cụ điều chỉnh trải nghiệm, không phải lý do bỏ qua sự từ chối rõ ràng.

## 21. Thiết kế application model

Có thể biểu diễn email intent độc lập với SMTP:

~~~java
public enum MailCategory {
    SECURITY,
    TRANSACTIONAL,
    OPERATIONAL,
    ONBOARDING,
    MARKETING
}
~~~

~~~java
public record MailIntent(
    UUID notificationId,
    String recipientId,
    String recipientAddress,
    MailCategory category,
    String templateKey,
    String campaignId,
    Instant requestedAt
) {}
~~~

Policy trả một quyết định:

~~~java
public enum EligibilityAction {
    ALLOW,
    DEFER,
    SUPPRESS
}
~~~

~~~java
public record MailEligibilityDecision(
    EligibilityAction action,
    Instant nextAllowedAt,
    String reason
) {}
~~~

Ý nghĩa:

| Action | Hành vi |
| --- | --- |
| `ALLOW` | Có thể reserve slot và enqueue |
| `DEFER` | Chưa đủ khoảng cách/tốc độ, xếp lịch khi còn phù hợp |
| `SUPPRESS` | Không được tiếp tục gửi trong phạm vi quy tắc |

`MailIntent`, `MailEligibilityDecision` không phụ thuộc vào `MimeMessage` hoặc `JavaMailSender`. Chúng nằm ở application boundary; SMTP adapter chỉ xử lý transport.

## 22. Eligibility service trong Spring

Các port:

~~~java
public interface RecipientPreferences {
    boolean permits(String recipientId, MailCategory category);
}
~~~

~~~java
public interface SuppressionService {
    boolean isSuppressed(
        String recipientAddress,
        MailCategory category
    );
}
~~~

~~~java
public interface FrequencyCapService {
    MailEligibilityDecision check(
        String recipientId,
        MailCategory category,
        Instant now
    );
}
~~~

Use case:

~~~java
public class MailEligibilityService {

    private final RecipientPreferences preferences;
    private final SuppressionService suppression;
    private final FrequencyCapService frequencyCap;
    private final Clock clock;

    public MailEligibilityService(
            RecipientPreferences preferences,
            SuppressionService suppression,
            FrequencyCapService frequencyCap,
            Clock clock) {
        this.preferences = preferences;
        this.suppression = suppression;
        this.frequencyCap = frequencyCap;
        this.clock = clock;
    }

    public MailEligibilityDecision evaluate(MailIntent intent) {
        if (suppression.isSuppressed(
                intent.recipientAddress(),
                intent.category())) {
            return new MailEligibilityDecision(
                EligibilityAction.SUPPRESS,
                null,
                "Recipient is suppressed"
            );
        }

        if (!preferences.permits(
                intent.recipientId(),
                intent.category())) {
            return new MailEligibilityDecision(
                EligibilityAction.SUPPRESS,
                null,
                "Recipient preference disallows this category"
            );
        }

        return frequencyCap.check(
            intent.recipientId(),
            intent.category(),
            clock.instant()
        );
    }
}
~~~

Code trên chỉ minh họa luồng **đọc policy**, chưa xử lý race condition. Một check độc lập không đủ khi hai request cùng tranh slot cuối. Cần reservation atomically trong transaction phù hợp.

## 23. Atomic frequency reservation

Giả sử recipient còn một slot marketing:

~~~text
Worker A: check used=0 -> ALLOW
Worker B: check used=0 -> ALLOW
Worker A: enqueue
Worker B: enqueue
~~~

Cả hai cùng đọc trước khi cập nhật, nên dễ vượt cap. Giải pháp là **atomic reserve** qua database/shared store với transaction, conditional update và unique constraint.

Ví dụ bảng PostgreSQL cho count cap theo một cửa sổ:

~~~sql
CREATE TABLE mail_frequency_usage (
    recipient_id VARCHAR(120) NOT NULL,
    category VARCHAR(40) NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    used_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (recipient_id, category, window_start)
);
~~~

Một thao tác reservation minh họa:

~~~sql
INSERT INTO mail_frequency_usage (
    recipient_id, category, window_start, used_count
)
VALUES (
    :recipientId, :category, :windowStart, 1
)
ON CONFLICT (
    recipient_id, category, window_start
)
DO UPDATE
SET used_count = mail_frequency_usage.used_count + 1
WHERE mail_frequency_usage.used_count < :limit
RETURNING used_count;
~~~

Giả sử `limit` là số nguyên dương đã được validate. Khi không trả row (cap đã đầy), ứng dụng có thể DEFER hoặc SUPPRESS. Đây là ví dụ **một fixed window**; rolling windows, minimum gap và nhiều cap đồng thời cần thiết kế chi tiết hơn.

**Reservation và insert outbox nên nằm trong cùng database transaction** để tránh giữ slot mà không tạo được notification job:

~~~text
BEGIN TRANSACTION
   Check preference và suppression
   Atomic reserve slot
   Insert mail_outbox
COMMIT
~~~

Nếu có daily, weekly và campaign cap cùng lúc, cần bảo đảm mọi reservation commit cùng nhau hoặc rollback khi một cap không đủ.

## 24. Một retry không phải một email marketing mới

Một notification đã reserve slot có thể thất bại SMTP rồi retry:

~~~text
Notification N-123
     |
     +--> Attempt 1: timeout
     +--> Attempt 2: temporary reject
     +--> Attempt 3: SUBMITTED
~~~

Về mặt frequency cap, đó vẫn là **một notification logic**, không phải ba marketing email khác nhau. Counter nên gắn với notification ID duy nhất; attempts được theo dõi riêng.

Nếu worker nhận kết quả SMTP mơ hồ, không nên vội giải phóng slot vì server có thể đã chấp nhận email. Nếu job bị hủy trước lần gửi đầu, policy có thể giải phóng reservation theo quy tắc nhất quán.

Đừng tạo notification mới với ID khác mỗi khi retry để tránh lách dedup và frequency cap.

## 25. Kết hợp outbox, worker và rate limiter

Một kiến trúc triển khai:

~~~text
Business event / campaign
          |
          v
Eligibility + consent + suppression
          |
          v
Atomic recipient frequency reservation
          |
          v
Durable outbox
          |
          v
Dispatcher / TaskExecutor
          |
          +--> Provider rate budget
          +--> Per-domain pacing
          +--> Concurrency limit
          +--> Retry/backoff
          |
          v
MailDeliveryPort / JavaMailSender
          |
          v
SMTP relay
          |
          v
Submission status + provider events
          |
          v
Suppression / preference / metrics
~~~

`JavaMailSender` là phần vận chuyển. Phần eligibility, reserve, outbox, rate limit và event handling là logic cần được xây trong ứng dụng hoặc nền tảng notification.

Không coi `@Async`/`TaskExecutor` queue trong bộ nhớ là durable queue. Với email quan trọng, outbox giúp phục hồi sau khi process restart. Worker nên claim batch vừa với executor capacity, không để hàng nghìn record PROCESSING hết lease khi còn đang chờ thread.

### Cấu hình SMTP

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000

app:
  mail:
    dispatch:
      batch-size: 20
      poll-delay-ms: 1000
    frequency:
      marketing:
        max-per-day: 1
~~~

Các thuộc tính `app.mail.*` là policy **do ứng dụng tự định nghĩa**, không phải tính năng frequency cap có sẵn chỉ cần bật của Spring Boot.

### Rate limiter trước transport

~~~java
public interface MailRateLimiter {
    boolean tryAcquire(
        String providerAccount,
        String recipientDomain
    );
}
~~~

~~~java
public class RateLimitedMailDispatcher {

    private final MailRateLimiter limiter;
    private final MailDeliveryPort delivery;

    public DispatchResult dispatch(
            String account,
            String recipientDomain,
            OutgoingMail mail) {

        if (!limiter.tryAcquire(account, recipientDomain)) {
            return DispatchResult.DEFERRED;
        }

        delivery.send(mail);
        return DispatchResult.SUBMITTED;
    }
}
~~~

`MailDeliveryPort`, `DispatchResult` và `OutgoingMail` là contract minh họa, không phải class Spring Framework Mail có sẵn. Khi `delivery.send` ném exception, worker phải phân loại và lưu retry/failed state. Đừng catch rồi tự báo SUBMITTED.

Rate limit nên dùng shared coordination nếu có nhiều sender instances cùng dùng quota provider. Retry cũng phải chịu rate limit.

## 26. Lịch gửi theo timezone và quiet hours

Nếu hệ thống có thông tin timezone và preference của người nhận, có thể tránh gửi marketing vào thời điểm không phù hợp.

Một model:

~~~java
public record RecipientDeliveryPreference(
    String recipientId,
    ZoneId timeZone,
    LocalTime quietFrom,
    LocalTime quietUntil
) {}
~~~

Các vấn đề cần xử lý:

- Quiet hours có thể đi qua nửa đêm.
- Timezone của người nhận có thể khác server.
- Daylight saving time khiến một số local time bị lặp hoặc không tồn tại.
- Một email có business deadline có thể không còn giá trị sau quiet hours.
- OTP/security mail cần chính sách riêng thay vì mặc định hoãn như marketing.

Dùng timezone IANA khi cần (ví dụ `Asia/Ho_Chi_Minh`, `Europe/Paris`) thay cho một offset cố định. Lưu lịch thực thi thực tế bằng `Instant`/UTC, nhưng tính giờ người nhận theo `ZoneId` nếu policy yêu cầu.

## 27. Provider webhooks cho tín hiệu giao thư và tương tác

Spring Mail không tự có delivered/opened/clicked events. Một provider integration có thể chuẩn hóa payload vào model ứng dụng:

~~~java
public enum MailProviderEventType {
    ACCEPTED,
    DELIVERED,
    DEFERRED,
    HARD_BOUNCE,
    SOFT_BOUNCE,
    COMPLAINED,
    UNSUBSCRIBED,
    OPENED,
    CLICKED
}
~~~

~~~java
public record MailProviderEvent(
    String provider,
    String providerEventId,
    String providerMessageId,
    String notificationId,
    String recipientId,
    MailProviderEventType type,
    Instant occurredAt
) {}
~~~

Đây là schema nội bộ minh họa. Mỗi provider có event names, field names và mức độ hỗ trợ khác nhau.

### Xác thực webhook

Không tin một payload trên Internet chỉ vì nó tự khai là complaint từ provider. Handler cần:

1. Verify signature/authentication theo giao thức provider.
2. Kiểm tra timestamp/replay window nếu có.
3. Validate schema và giới hạn kích thước request.
4. Correlate với provider message ID/notification ID.
5. Deduplicate event.
6. Lưu event bền vững nếu cần reliability.
7. Cập nhật suppression/status/metrics đúng phạm vi.
8. Không log PII/secret thừa.

Một webhook complaint giả có thể khiến hệ thống suppress khách hàng hợp lệ; kiểm tra nguồn event là yêu cầu bảo mật.

## 28. Webhook idempotency và out-of-order events

Provider có thể gửi lại webhook sau timeout, hoặc một event đến muộn hơn event khác.

Bảng PostgreSQL minh họa:

~~~sql
CREATE TABLE mail_provider_event (
    provider VARCHAR(100) NOT NULL,
    provider_event_id VARCHAR(255) NOT NULL,
    notification_id VARCHAR(120),
    event_type VARCHAR(60) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (provider, provider_event_id)
);
~~~

Nếu provider không cấp event ID bền vững, cần một cơ chế dedup phù hợp khác, nhưng phải hiểu nguy cơ gộp nhầm các sự kiện.

Một duplicate `COMPLAINED` không nên tăng complaint count hai lần. Một `DELIVERED` đến muộn không nên đơn giản ghi đè một trạng thái bounce mà không kiểm tra cùng recipient/attempt/message. Lưu event history giúp tra cứu.

### Signal handler minh họa

~~~java
public class MailSignalHandler {

    private final MailEventRepository events;
    private final SuppressionService suppression;

    @Transactional
    public void handle(MailProviderEvent event) {
        if (!events.insertIfAbsent(event)) {
            return;
        }

        switch (event.type()) {
            case HARD_BOUNCE -> suppression.suppressAddress(
                event.recipientId(), "HARD_BOUNCE");

            case COMPLAINED -> suppression.suppressMarketing(
                event.recipientId(), "SPAM_COMPLAINT");

            case UNSUBSCRIBED -> suppression.suppressMarketing(
                event.recipientId(), "UNSUBSCRIBED");

            default -> {
                // Update delivery/engagement events separately.
            }
        }
    }
}
~~~

Các repository/service trong ví dụ là contract do ứng dụng định nghĩa. Handler giả định webhook đã được verify, event đã được map và recipient ID đã được xác thực. Scope suppression cần được quyết định theo email address, user và category.

## 29. Metrics để nhìn đúng tín hiệu

| Metric | Diễn giải | Caveat |
| --- | --- | --- |
| Submission success rate | Successful submissions / attempts | Không phải delivery rate |
| Delivery rate | Delivered / accepted messages theo provider | Provider semantics khác nhau |
| Hard bounce rate | Hard bounce / mẫu số đã định nghĩa | Phân loại bounce phải đúng |
| Deferral rate | Deferrals / messages hoặc attempts | Một message có thể deferred nhiều lần |
| Complaint rate | Complaints / delivered hoặc sent theo nguồn | Có thể chỉ quan sát subset |
| Unsubscribe rate | Unique unsubscribes / delivered marketing | Phải lọc event trùng |
| Unique click rate | Recipients with click / delivered | Scanner/bot gây nhiễu |
| Open rate | Observed opens / delivered hoặc sent | Privacy proxies làm sai lệch |
| Frequency distribution | Emails/recipient/rolling window | Tìm nhóm nhận quá dày |
| Queue age p95 | Thời gian chờ trước submit | Phản ánh saturation |
| Retry/throttle rate | Transient errors / submission attempts | Xem theo provider/domain |
| Conversion | Business outcomes / cohort | Attribution cần định nghĩa |

**Luôn ghi rõ mẫu số.** “Complaint rate theo sent” và “complaint rate theo delivered” không thể đem so sánh trực tiếp. Với unique engagement, cần dedup theo recipient/message/event semantics.

Nên phân đoạn theo campaign, category, provider, sending domain, recipient domain hoặc cohort. Tránh đưa raw email/notification ID thành metric label vì dễ lộ dữ liệu và làm cardinality tăng cao.

## 30. Dùng tín hiệu để điều chỉnh cadence

Một ví dụ phân đoạn:

| Nhóm | Tín hiệu | Cách phản ứng |
| --- | --- | --- |
| Quan tâm rõ | Consent, click/conversion có ý nghĩa, không complaint | Giữ nhịp phù hợp, vẫn có cap |
| Chưa rõ tương tác | Không thấy open/click, không complaint | Không kết luận không quan tâm; xem lại nội dung/preferences |
| Phản hồi tiêu cực | Complaint/unsubscribe/hard bounce | Suppress theo phạm vi phù hợp |
| Provider throttled | Nhiều temporary deferrals | Giảm rate, tôn trọng cooldown |
| Workflow chưa hoàn thành | Người dùng chưa làm bước tiếp theo | Có thể nhắc có giới hạn; xem deadline và quiet hours |

Không tăng cadence chỉ vì một lần click. Cũng không xóa toàn bộ danh sách chỉ vì open rate giảm sau thay đổi chính sách privacy của email client.

Một feedback loop lành mạnh:

~~~text
Send small batches
       |
       v
Observe provider + business signals
       |
       v
Negative signals rise?
       |
    +--+--+
    |     |
   Yes    No
    |     |
    v     v
 Reduce  Maintain or cautiously increase
 cadence within consent and quota
       |
       v
Continue monitoring
~~~

Các phép thử cadence nên tiến hành trên cohort có định nghĩa rõ, thay đổi có kiểm soát và không vi phạm consent.

## 31. Danh tiếng người gửi không có một công thức chung

Mailbox providers có thể xem xét lịch sử volume, danh tiếng IP/domain, xác thực sender, phản hồi người nhận và nhiều yếu tố khác. Công thức cụ thể không được công bố đầy đủ và có thể thay đổi.

Vì vậy:

- Không thể hứa một lịch warm-up cố định luôn đưa thư vào Inbox.
- SPF/DKIM/DMARC là nền tảng quan trọng nhưng không bảo đảm placement.
- Một chiến dịch có bounce thấp vẫn có thể vào Spam.
- Tăng open rate không luôn cải thiện deliverability thực tế.
- Khi volume/complaint/deferral thay đổi, cần xem từng provider/domain.
- Người gửi cần tôn trọng thực tế người nhận, không cố tối ưu “mẹo” để che dấu chất lượng danh sách.

Deliverability nên được đo bằng nguồn đáng tin và quản trị dài hạn, không suy ra từ một phản hồi SMTP `250`.

## 32. Tình huống chẩn đoán thường gặp

| Triệu chứng | Có thể do | Cách điều tra |
| --- | --- | --- |
| Một domain trả nhiều `421/4xx` | Throttling, server tạm bận | Giảm pacing và xem provider logs |
| Hard bounce tăng | Danh sách chứa địa chỉ không hợp lệ | Kiểm tra consent source, list hygiene |
| Complaint tăng | Gửi quá dày, nội dung không mong đợi | Giảm cadence, sửa preference/unsubscribe |
| Unsubscribe tăng | Sai tần suất/chủ đề | Kiểm tra recipient expectations |
| Open rate giảm đột ngột | Thay đổi privacy/pixel loading | Không kết luận placement giảm ngay |
| Click tăng ngay sau gửi | Scanner/bot prefetch | Đối chiếu conversion và human behavior |
| Submission cao, delivered thấp | Downstream filtering/deferral | Provider delivery events |
| Queue tồn đọng | Pool/rate quota không đủ | Outbox age, worker throughput |
| Security mail chậm vì campaign | Dùng chung queue/priority | Tách budget/queue |
| Nhiều lỗi AUTH/TLS | Credential hoặc transport config | Sửa hạ tầng, không tăng retry |

Chẩn đoán cần phân biệt lỗi **trước SMTP acceptance**, tình trạng **sau submission** và **thiếu tín hiệu tương tác**. Không quy tất cả thành một “deliverability score” duy nhất.

## 33. Kiểm thử frequency policy

Nên dùng một `Clock` có thể inject:

~~~java
Clock clock = Clock.fixed(
    Instant.parse("2026-11-12T08:00:00Z"),
    ZoneOffset.UTC
);
~~~

Các case:

1. Recipient còn slot → ALLOW.
2. Recipient đạt cap → DEFER/SUPPRESS theo policy.
3. Nhiều campaign dùng chung global cap.
4. Retry cùng notification ID không tăng cap.
5. Unsubscribe sau enqueue nhưng trước submit → không gửi marketing.
6. Complaint/hard bounce cập nhật suppression.
7. Transactional/security không dùng nhầm marketing cap.
8. Rolling window ở ranh giới ngày/tuần.
9. Timezone và DST nếu áp lịch địa phương.
10. Hai worker tranh slot cuối chỉ có một reservation thành công.

### Concurrent reservation test

~~~text
used_count = limit - 1

Worker A -----+
              +--> atomic reserve
Worker B -----+

Expected:
  Exactly one reservation succeeds.
~~~

Cần test concurrency với database thực/transaction semantics phù hợp, không chỉ unit test đơn thread.

## 34. Kiểm thử provider signals

- Webhook signature sai phải bị từ chối.
- Event trùng không tăng counters hai lần.
- Hard bounce áp suppression đúng scope.
- Complaint/unsubscribe ngăn marketing tiếp theo.
- Event đến sai thứ tự không làm mất thông tin.
- Open/click từ bot không tự động coi là conversion.
- Unknown notification ID được lưu để đối soát.
- Provider outage không làm mất event quan trọng nếu hệ thống yêu cầu durability.
- SMTP submission success không bị gắn nhãn DELIVERED chỉ vì test fake trả thành công.

Một test SMTP server như GreenMail/Mailpit kiểm tra được MIME và acceptance, nhưng không mô phỏng đầy đủ thực tế spam filtering ở tất cả mailbox providers. Phần webhook và tín hiệu nên có contract tests/fixtures riêng.

## 35. Những anti-pattern cần tránh

| Anti-pattern | Hệ quả | Cách làm tốt hơn |
| --- | --- | --- |
| Chỉ đặt SMTP rate limit | Một người nhận vẫn nhận quá nhiều | Recipient frequency cap |
| Mỗi campaign có cap riêng | Nhiều campaign chồng lịch | Global/category cap |
| Dùng cùng FIFO queue cho OTP và newsletter | Security mail trễ | Tách ưu tiên/queue |
| Gửi campaign cùng một lúc | Burst/throttle | Pacing, batches |
| Không kiểm tra unsubscribe trước submit | Gửi sau khi recipient yêu cầu dừng | Recheck suppression |
| Coi open là đã đọc chắc chắn | Proxy/pixel gây nhiễu | Dùng nhiều tín hiệu |
| Coi không-open là không quan tâm chắc chắn | Loại người nhận hợp lệ | Hiểu giới hạn tracking |
| Coi click nào cũng từ người thật | Bot/scanner gây false positive | Phân loại và xác minh |
| Retry message đã accepted nhưng deferred downstream | Có thể duplicate | Theo dõi delivery/retry của provider |
| Không suppress hard bounce/complaint | Gửi lặp gây hại | Suppression nhanh |
| Suppress mọi mã `550` | Có thể chặn email hợp lệ | Xem failure reason |
| Đếm SMTP retries vào recipient cap | Cap tiêu tốn sai | Đếm logical notification |
| In-memory counter nhiều instances | Race/vượt cap | Atomic shared reservation |
| Không verify webhook | Bị giả mạo signal | Signature/auth + dedup |
| Bật tracking không xem privacy | Rủi ro quyền riêng tư | Chỉ dùng dữ liệu cần thiết |
| Tin SMTP success là Inbox | Báo cáo sai deliverability | Tách submission/delivery |
| Metric label chứa email cá nhân | PII và cardinality cao | Cohort/category/provider |

## 36. Quy trình triển khai trong Spring application

1. **Phân loại email** thành transactional/security và marketing/lifecycle.
2. **Tạo preferences, consent và suppression model**.
3. **Xác định frequency cap** theo recipient/category/campaign.
4. **Triển khai atomic reservation** cùng transaction tạo outbox.
5. **Tách application policy khỏi SMTP adapter** qua port.
6. **Điều tiết rate/concurrency/pacing** theo quota provider.
7. **Giữ job bền vững** khi cần retry/restart, không dựa vào queue in-memory.
8. **Tích hợp provider webhook** để nhận delivered/bounce/complaint/unsubscribe.
9. **Verify và dedup events**, xử lý suppression kịp thời.
10. **Theo dõi metrics nhiều tầng** và phân đoạn theo domain/campaign/cohort.
11. **Dùng open/click có caveat**, không suy diễn người thật đã đọc.
12. **Điều chỉnh cadence từ từ** theo phản hồi và provider cooldown.
13. **Kiểm thử concurrency, timezone, unsubscribe race và event duplication**.
14. **Định kỳ rà soát privacy, retention và sender authentication**.

## 37. Ghi nhớ

- **Send rate** là tốc độ transport; **recipient frequency** là mức độ liên hệ một người.
- Một ứng dụng có thể đúng quota SMTP nhưng vẫn gửi quá thường xuyên.
- Consent và suppression luôn cần được xét trước marketing frequency cap.
- Không áp một cap marketing cho mọi email bảo mật/giao dịch.
- Atomic reservation tránh hai worker cùng tiêu slot cuối.
- Retry cùng notification ID không phải một email marketing logic mới.
- Pacing và warm-up giúp tăng gửi có kiểm soát nhưng không bảo đảm Inbox placement.
- Transport rate limiter khác với recipient cap và minimum gap.
- Hard bounce và complaint đáng tin là tín hiệu cần xử lý nghiêm túc.
- Soft bounce/deferred cần phân biệt submission failure và downstream delay.
- Unsubscribe phải ảnh hưởng cả email đang chờ trong queue.
- Open pixel không chứng minh người thật đã đọc; click có thể đến từ scanner.
- `JavaMailSender` không cung cấp engagement event mặc định; cần provider integration.
- Webhook phải được xác thực, dedup và lưu kết quả đúng trạng thái.
- Delivery rate, complaint rate và open rate chỉ so sánh được khi mẫu số rõ ràng.
- Không đánh đồng `SUBMITTED`, `DELIVERED` và `OPENED`.
- Bảo vệ dữ liệu người nhận và tránh log/metric label chứa thông tin cá nhân.

**Nguyên tắc quan trọng nhất:** deliverability bền vững không đến từ việc gửi càng nhiều càng nhanh. Hệ thống nên gửi **đúng người, đúng mục đích, đúng tần suất**, tôn trọng tín hiệu từ chối và theo dõi những phản hồi có bằng chứng. Khi Spring Framework Mail được đặt sau consent policy, frequency cap, outbox, rate limiter và provider event handler, ứng dụng có thể điều chỉnh gửi chủ động mà không gây quá tải hoặc làm phiền người nhận không cần thiết.
