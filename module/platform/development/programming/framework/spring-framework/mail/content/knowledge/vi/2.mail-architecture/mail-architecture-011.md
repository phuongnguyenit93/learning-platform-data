# Khác biệt giữa accepted, delivered, opened và clicked trong kiến trúc email

Khi gửi email từ ứng dụng Spring, trạng thái “đã gửi” thường chưa có nghĩa là người nhận đã nhận được email, càng chưa có nghĩa là họ đã đọc hoặc bấm vào một liên kết. Một email có thể được máy chủ SMTP chấp nhận nhưng sau đó bị từ chối; cũng có thể được giao thành công vào hệ thống thư của người nhận nhưng bị lọc vào thư rác; hoặc một hệ thống bảo vệ thư có thể tải ảnh và truy cập liên kết trước khi người dùng làm điều đó.

Để thiết kế hệ thống thông báo đáng tin cậy, cần tách bốn tín hiệu thường gặp:

- **Accepted**: một hệ thống gửi hoặc máy chủ SMTP đã chấp nhận thông điệp để xử lý tiếp.
- **Delivered**: máy chủ thư phía nhận hoặc một chặng được nhà cung cấp định nghĩa đã chấp nhận thông điệp; thường **không xác nhận vào inbox**.
- **Opened**: hệ thống ghi nhận dấu hiệu nội dung email được hiển thị hoặc tài nguyên theo dõi được tải; **không chứng minh con người đã đọc**.
- **Clicked**: hệ thống ghi nhận truy cập một URL theo dõi trong email; **không chứng minh người dùng đã thực hiện hành động nghiệp vụ mong muốn**.

Đây là các **sự kiện quan sát được ở những tầng khác nhau**, không phải bốn giá trị chắc chắn tiến đều từ thấp tới cao.

## 1. Email đi qua những thành phần nào?

Giả sử ứng dụng Spring gửi một email xác nhận đơn hàng:

```text
Ứng dụng Spring
    |
    | JavaMailSender.send(...)
    v
SMTP relay / Email Service Provider (ESP)
    |  accepted: nhận thư để xếp hàng và chuyển tiếp
    |
    | xử lý hàng đợi, chính sách gửi, retry
    v
Máy chủ thư phía nhận (MX / receiving MTA)
    |  delivered: tiếp nhận thư theo định nghĩa của nhà cung cấp
    |
    | lọc spam, phân loại thư mục, chuyển vào mailbox
    v
Ứng dụng đọc email / thiết bị / proxy ảnh
    |  opened: tín hiệu tải ảnh theo dõi (nếu có)
    |
    | người dùng hoặc hệ thống bảo vệ truy cập liên kết
    v
Tracking redirect / Website
       clicked: ghi nhận lượt truy cập liên kết (nếu theo dõi)
```

Trong sơ đồ này, “accepted” cần được hiểu theo **chặng giao nhận**. Ví dụ, thành công của `JavaMailSender.send(...)` thường cho biết máy chủ SMTP mà ứng dụng kết nối đã chấp nhận quá trình gửi trong phiên giao tiếp đó. Một ESP cũng có thể phát event `accepted` khi API của họ nhận yêu cầu hoặc khi thư vào hàng đợi. Hai sự kiện có thể dùng cùng tên nhưng phản ánh **hai ranh giới trách nhiệm khác nhau**.

Tương tự, một ESP có thể báo `delivered` khi máy chủ thư đích trả về phản hồi SMTP thành công cho quá trình giao thư. Hệ thống gửi không quan sát trực tiếp việc thư được đặt trong tab Primary, Promotions, Spam hay đã bị người dùng xóa.

### Bảng so sánh nhanh

| Trạng thái | Điều được quan sát | Điều **không thể kết luận** | Nguồn tín hiệu điển hình |
| --- | --- | --- | --- |
| `accepted` | Máy chủ/API gửi đồng ý nhận nhiệm vụ gửi | Thư đã tới máy chủ đích; thư đã vào inbox | SMTP response hoặc sự kiện ESP |
| `delivered` | Chặng tiếp nhận được ESP coi là giao thành công | Người nhận thấy thư trong inbox, đã mở hay đã đọc | SMTP response của phía nhận, webhook ESP |
| `opened` | Ảnh theo dõi được tải hoặc client phát tín hiệu tương đương | Người thật đã đọc và hiểu nội dung | Tracking pixel, proxy ảnh, API ESP |
| `clicked` | Một liên kết theo dõi được truy cập | Có người thật bấm; giao dịch hay xác nhận đã hoàn tất | Redirect tracking, webhook ESP |

Tên event, cách đặt mốc và mức độ bảo đảm là **đặc thù từng nhà cung cấp**. Khi tích hợp, phải đọc định nghĩa cụ thể của ESP, kể cả các trạng thái `processed`, `queued`, `deferred`, `dropped` hay `bounce`.

## 2. Accepted: được chấp nhận để xử lý, chưa chắc được giao

Ở bước gửi bằng SMTP, máy chủ trả về mã phản hồi cho từng giai đoạn. Mã `250` là phản hồi thành công trong nhiều lệnh SMTP, nhưng phải xem nó xuất hiện **sau lệnh nào**.

Ví dụ minh họa tối giản cho quá trình gửi:

```text
C: MAIL FROM:<no-reply@example.com>
S: 250 OK

C: RCPT TO:<customer@example.net>
S: 250 Recipient accepted

C: DATA
S: 354 End data with <CRLF>.<CRLF>

C: Subject: Xac nhan don hang
C:
C: Noi dung email
C: .
S: 250 Message queued as 12345
```

Trong đó:

- `250` sau `RCPT TO` nói rằng máy chủ chấp nhận địa chỉ người nhận cho phiên giao dịch, **chưa xác nhận nội dung thư đã được nhận trọn vẹn**.
- `250` sau kết thúc `DATA` cho biết máy chủ này nhận thông điệp để xử lý tiếp. Nó có thể đưa thư vào hàng đợi, chuyển tiếp hoặc thử gửi lại sau.
- Nếu đó là máy chủ relay/ESP, quá trình chuyển tới máy chủ thư đích còn ở phía sau.
- Với API gửi email, HTTP `202 Accepted` (nếu ESP dùng mã đó) thường chỉ có nghĩa là API đã nhận yêu cầu để xử lý bất đồng bộ; ý nghĩa chính xác phải theo hợp đồng API.

Trong Spring Framework Mail:

```java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

public class ConfirmationMailer {
    private final JavaMailSender mailSender;

    public ConfirmationMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(String recipient) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("no-reply@example.com");
        mail.setTo(recipient);
        mail.setSubject("Xác nhận đơn hàng");
        mail.setText("Đơn hàng của bạn đã được ghi nhận.");

        // Thành công ở đây chỉ xác nhận bước gửi tới SMTP/relay mà ứng dụng dùng.
        mailSender.send(mail);
    }
}
```

Nếu `send` trả về bình thường, ứng dụng có thể ghi nhận **SMTP submission succeeded** hoặc `submitted_to_relay`. Không nên ngay lập tức đổi trạng thái người nhận thành `delivered`.

Nếu xảy ra `MailException`, cũng cần phân biệt lỗi chắc chắn xảy ra **trước khi máy chủ tiếp nhận** và lỗi kết nối xảy ra **sau khi máy chủ có thể đã nhận thông điệp**. Trường hợp sau có rủi ro gửi trùng nếu hệ thống retry vô điều kiện. Sử dụng một mã thông báo nghiệp vụ ổn định, lưu dấu các lần thử gửi và thiết kế retry phù hợp với nhà cung cấp.

### Accepted có thể đứng trước các kết cục nào?

```text
accepted
   ├── delivered
   ├── deferred → retry → delivered
   ├── deferred → retry → bounced/failed
   ├── bounced/failed
   └── dropped/suppressed (tùy định nghĩa ESP)
```

`Deferred` thường diễn tả trở ngại tạm thời, chẳng hạn phía nhận bận hoặc giới hạn tốc độ; `bounce` thường diễn tả không thể giao thư. Phân loại **hard bounce** và **soft bounce** cũng tùy nhà cung cấp và bối cảnh lỗi. Một thư được accepted không buộc phải có delivered sau đó.

## 3. Delivered: đã giao đến chặng đích, không đồng nghĩa inbox

Trạng thái `delivered` trong nhiều dịch vụ gửi email có nghĩa là **hệ thống thư phía nhận chấp nhận email**. Phản hồi SMTP thành công từ receiving MTA là bằng chứng giao nhận ở cấp vận chuyển, chứ không chứng minh:

- Email đã nằm trong inbox thay vì Spam/Junk hoặc tab khác.
- Mailbox sẽ giữ thư mãi; hệ thống đích có thể thực hiện xử lý hoặc thông báo lỗi bất đồng bộ.
- Người nhận đã nhìn thấy thông báo trên điện thoại hoặc ứng dụng email.
- Địa chỉ đó thuộc về người đang sử dụng tài khoản hợp lệ.
- Nội dung đã được mở hoặc liên kết đã được bấm.

Trong giao thức SMTP, thư có thể trải qua nhiều relay. Một sự kiện `delivered` từ nhà cung cấp A có thể phản ánh chặng khác với sự kiện cùng tên từ nhà cung cấp B; vì vậy, tài liệu kiến trúc nội bộ cần lưu **nguồn và định nghĩa của sự kiện**.

Đối với các hệ thống quan trọng (mã xác thực, thông báo thanh toán, cảnh báo bảo mật), không nên dựa vào `delivered` để suy ra người dùng đã biết thông tin. Nếu nghiệp vụ thực sự cần xác nhận, hãy thiết kế một hành động xác nhận **trong ứng dụng**, được xác thực và ghi nhận riêng.

### Delivered và bounce có mâu thuẫn không?

Không nhất thiết. Một receiving server có thể nhận email rồi gửi **thông báo không phát được (DSN)** ở giai đoạn xử lý sau. ESP cũng có thể cập nhật lại phân loại khi nhận tín hiệu trễ. Bởi vậy, nếu event `delivered` xuất hiện trước event `bounce` đối với cùng thông điệp/người nhận, đừng mặc định dữ liệu bị sai.

Khi cần hiển thị một trạng thái ngắn gọn, phải định nghĩa **chính sách tổng hợp riêng**: ví dụ ưu tiên một bounce xác nhận không phát được so với tín hiệu delivered trước đó, nhưng vẫn giữ cả hai event và timestamp để truy vết.

## 4. Opened: tín hiệu quan sát hạn chế về việc hiển thị

Một cách theo dõi mở email phổ biến là chèn ảnh 1×1 pixel hoặc một URL tài nguyên có mã định danh riêng vào HTML:

```html
<img
  src="https://mail.example.com/t/open/opaque-token"
  width="1"
  height="1"
  alt=""
>
```

Nếu ứng dụng đọc thư tải URL này, hệ thống theo dõi có thể ghi một sự kiện `opened`. ESP thường làm phần việc này nếu đã bật open tracking; `JavaMailSender` của Spring **không tự tạo tracking pixel và cũng không tự biết thư được mở**.

Tuy nhiên, giữa việc tải pixel và việc con người đọc email có nhiều khác biệt:

1. **Chặn ảnh**: Người dùng có thể đọc đầy đủ nội dung văn bản nhưng client không tải pixel. Không có event mở.
2. **Image proxy và cache**: Dịch vụ email có thể tải ảnh qua máy chủ trung gian; IP, thiết bị và lượt tải có thể không phản ánh trực tiếp người đọc.
3. **Mail Privacy Protection và cơ chế prefetch**: Một số ứng dụng/hệ thống có thể tải nội dung từ xa mà không cần người dùng thực sự mở thư. Event có thể được ghi nhận dù không có lần đọc tương ứng.
4. **Thư plain text**: Không có thẻ `<img>` HTML để đo bằng pixel; việc người dùng đọc thư không tạo open event theo cơ chế này.
5. **Nhiều thiết bị hoặc nhiều lần mở**: Một email có thể được tải lại nhiều lần; số lần tải pixel không bằng số người đọc.
6. **Hệ thống quét bảo mật**: Một số bộ lọc kiểm tra nội dung, tải tài nguyên hoặc ảnh để đánh giá rủi ro trước khi giao thư.

Vì vậy, `opened_at` nên được hiểu là thời điểm ghi nhận **tín hiệu mở** theo phương pháp theo dõi cụ thể, không nên đặt tên như `read_at` hay dùng làm bằng chứng đã đọc về mặt pháp lý/nghiệp vụ.

### Có cần đo opened?

Có thể hữu ích để quan sát xu hướng tương đối trong chiến dịch email, nhưng số đo dễ sai lệch nếu nhiều người dùng bật các chế độ bảo vệ quyền riêng tư. Với email giao dịch, ưu tiên tín hiệu có ý nghĩa nghiệp vụ hơn: người dùng đã xác minh tài khoản, hoàn tất đặt lại mật khẩu, hoặc xem thông báo trong ứng dụng.

## 5. Clicked: liên kết được truy cập, chưa chắc là hành động của con người

Để ghi nhận lượt click, ESP có thể thay liên kết gốc trong nội dung thư bằng liên kết redirect:

```text
Liên kết gốc:
https://example.com/orders/123

Liên kết theo dõi xuất hiện trong email:
https://click.mail.example.com/r/opaque-token

Khi được truy cập:
1. Server theo dõi ghi event "clicked".
2. Server trả HTTP redirect đến URL đích.
3. Trình duyệt hoặc hệ thống gọi URL đích.
```

Ví dụ liên kết trong HTML:

```html
<a href="https://click.mail.example.com/r/opaque-token">
  Xem đơn hàng
</a>
```

Event `clicked` thường chứa thông điệp, người nhận, thời điểm và liên kết được click. Nó có thể có thêm user-agent, IP hoặc danh tính chiến dịch tùy nguồn, nhưng dữ liệu này không nhất thiết đáng tin để nhận diện người dùng.

**Các trường hợp gây hiểu nhầm:**

- Bộ lọc chống phishing mở thử đường dẫn trước khi giao email, tạo click tự động.
- Link scanner hoặc hệ thống bảo mật truy cập nhiều liên kết trong vài giây.
- Công cụ kiểm tra preview, proxy hay trình duyệt tự động truy cập URL.
- Người dùng chuyển tiếp email cho người khác; click được gắn với token của email gốc.
- Liên kết không được rewrite hoặc tracking bị vô hiệu hóa: người dùng bấm thật nhưng hệ thống không nhận event.
- Chỉ truy cập landing page; chưa chắc người dùng đã đăng nhập, thanh toán hoặc xác nhận điều khoản.

Một số ESP có phân loại **bot click** hay cung cấp cờ chất lượng, nhưng độ chính xác và cách lọc khác nhau. Không nên tự tin gọi mọi `clicked` là “người nhận đã chủ động click”.

**Click event không thay thế event nghiệp vụ.** Ví dụ:

```text
Email clicked → Landing page viewed → Authenticated → Order confirmed
        |                |                 |                |
    mail telemetry   web analytics   auth/session      nghiệp vụ
```

Đối với chức năng xác minh email hoặc đổi mật khẩu, không dùng **GET request của liên kết** làm hành động nhạy cảm có hiệu lực ngay. Link scanner có thể truy cập GET trước người dùng. Nên thiết kế trang đích cho phép người dùng chủ động xác nhận qua hành động bổ sung thích hợp; xác thực token, chống lặp, thời hạn và các bước nghiệp vụ phải xử lý ở backend.

## 6. Bốn trạng thái không phải một máy trạng thái tuyến tính

Mô hình `accepted → delivered → opened → clicked` chỉ là **minh họa một hành trình lý tưởng**. Dữ liệu thu thập thực tế có thể khác:

| Chuỗi event quan sát | Cách diễn giải có thể hợp lý |
| --- | --- |
| `accepted`, `delivered` | Đã có bằng chứng giao; không có tín hiệu mở hoặc click |
| `accepted`, `delivered`, `clicked` | Người dùng hoặc hệ thống đã truy cập liên kết; pixel không được tải hoặc không có open tracking |
| `accepted`, `delivered`, `opened` | Có tín hiệu tải ảnh; chưa có click được ghi nhận |
| `accepted`, `bounced` | Được ESP nhận, nhưng không giao được tới đích |
| `delivered` rồi `bounced` | Có khả năng thông báo lỗi bất đồng bộ sau khi chặng nhận đồng ý |
| `clicked` đến webhook trước `delivered` | Event được phân phối không theo thứ tự hoặc timestamp của các nguồn khác nhau |
| Hai event `opened` giống nhau | Có thể là nhiều lần mở hoặc webhook bị gửi lại; phải kiểm tra ID event |
| `clicked` ngay sau `delivered` với nhiều URL | Có thể là bộ lọc bảo mật truy cập hàng loạt; chưa đủ bằng chứng để kết luận |

Ngoài bốn sự kiện này, kiến trúc gửi email thường cần các trạng thái khác:

- `requested` hoặc `queued`: ứng dụng đã tạo yêu cầu và chuẩn bị gửi.
- `submitted`: ứng dụng gửi thành công tới SMTP/API.
- `deferred`: nhà cung cấp hoãn thử giao, có thể retry.
- `bounced` / `failed`: thất bại giao thư.
- `dropped` / `suppressed`: nhà cung cấp chủ động không gửi, chẳng hạn do danh sách chặn hoặc chính sách.
- `complained`: nhận phản hồi phàn nàn/spam complaint.
- `unsubscribed`: yêu cầu hủy đăng ký nhận loại email liên quan.

Đặc biệt, `unsubscribed` là sự kiện quản lý lựa chọn nhận tin, không phải một mức thấp/cao hơn `opened` hoặc `clicked`.

### Tách sự kiện gốc khỏi trạng thái tổng hợp

Một kiến trúc hữu ích là lưu **event log bất biến** rồi suy ra các nhãn phục vụ giao diện. Ví dụ:

```text
email_delivery (mỗi email đến một người nhận)
    delivery_id = d-001
    business_id = order-123
    provider_message_id = p-555

email_event (nhiều bản ghi)
    09:00 accepted
    09:00 delivered
    09:02 opened
    09:05 clicked (link=order-details)
    09:06 opened
```

Hệ thống có thể hiển thị “đã được máy chủ đích chấp nhận” dựa trên event `delivered` gần nhất liên quan đến vận chuyển, đồng thời hiển thị “có tín hiệu mở” hoặc “có lượt click”. Cách biểu diễn này tránh việc ghi đè một trường `status` duy nhất thành `clicked` rồi làm mất thông tin `bounced` hay `complained` đến sau.

## 7. JavaMailSender liên quan đến các event thế nào?

Trong Spring Framework Mail, `JavaMailSender` là thành phần gửi qua SMTP và tạo `MimeMessage`. Nó **không cung cấp sẵn hệ thống theo dõi vòng đời giao thư của ESP**, không lắng nghe webhook delivered/opened/clicked và không có khả năng xác định người nhận đã đọc email.

Có ba nhóm nguồn dữ liệu khác nhau:

| Lớp | Tín hiệu có thể thu thập | Thành phần thường đảm nhận |
| --- | --- | --- |
| Ứng dụng Spring | Yêu cầu tạo thư, lần gọi `send` thành công/thất bại, correlation ID | Service gửi mail + database |
| SMTP/ESP | Accepted, deferred, delivered, bounce, complaint | SMTP relay, ESP webhook/API, DSN khi được hỗ trợ |
| Tương tác | Open pixel, link redirect/click và các hành động trong website | ESP tracking, tracking endpoint, analytics hoặc backend nghiệp vụ |

Nếu chỉ cấu hình SMTP thuần mà nhà cung cấp **không có webhook tracking**, việc gọi `JavaMailSender#send(...)` sẽ không tự tạo event `delivered`, `opened` hay `clicked`. Có thể cần tích hợp API/webhook của ESP hoặc hạ tầng theo dõi riêng.

### Gắn correlation ID để nối các dữ liệu

Một giao dịch có thể tạo nhiều email; một email có thể có nhiều người nhận; một lần gửi có thể được retry. Vì vậy nên phân biệt:

- **Business ID**: mã giao dịch hoặc đơn hàng, ví dụ `order-123`.
- **Delivery ID**: mã nội bộ cho **một email gửi đến một người nhận**.
- **Attempt ID**: mã của lần thử gửi; một delivery có thể có nhiều attempt.
- **Provider message ID**: mã mà ESP cấp, có thể được dùng trong webhook.
- **RFC Message-ID**: header `Message-ID` của email; không phải lúc nào cũng giống provider message ID.
- **Provider event ID**: mã duy nhất cho một sự kiện webhook, phục vụ chống xử lý trùng.

Đối với một `MimeMessage` có nhiều người nhận, sự kiện delivered/bounce có thể **khác nhau cho từng người nhận**. Nên lập delivery record riêng theo recipient; không đánh dấu cả thông điệp delivered chỉ vì một địa chỉ được chấp nhận.

Thông tin liên kết có thể được đính qua metadata hoặc custom header như `X-Application-Delivery-ID` nếu nhà cung cấp hỗ trợ. Tuy nhiên **không đưa thông tin bí mật hoặc dữ liệu cá nhân nhạy cảm vào header/URL theo dõi** vì chúng có thể bị lộ cho các trung gian.

## 8. Ví dụ kiến trúc Spring nhận webhook từ ESP

Với một ESP có webhook, quy trình thường gồm:

1. Ứng dụng ghi yêu cầu gửi cùng `delivery_id` và người nhận.
2. Ứng dụng gửi email qua SMTP hoặc API và lưu kết quả submission/provider message ID.
3. ESP gửi webhook cho các event như accepted, delivered, bounced, opened, clicked.
4. Spring xác thực webhook và chuyển payload đặc thù nhà cung cấp sang mô hình event nội bộ.
5. Database lưu event một cách **idempotent**; lớp báo cáo hoặc giao diện đọc event đã chuẩn hóa.

Dữ liệu webhook ví dụ **do ứng dụng nội bộ chuẩn hóa**, không phải định dạng mặc định của một ESP nào:

```json
{
  "provider": "example-esp",
  "providerEventId": "evt-00042",
  "providerMessageId": "msg-0815",
  "deliveryId": "d-001",
  "recipientRef": "customer-27",
  "type": "delivered",
  "occurredAt": "2026-11-12T02:10:35Z",
  "linkId": null
}
```

Ở đây, `occurredAt` là thời điểm sự kiện do nguồn báo; lúc webhook được server nhận có thể muộn hơn. `recipientRef` là mã tham chiếu nội bộ đã giảm thiểu thông tin cá nhân, thay vì địa chỉ email thô.

### Tổ chức lớp nhận webhook

Ví dụ khung controller Spring Boot 3+/Java 17+:

```java
package example.mail.tracking;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/webhooks/email")
public class EmailWebhookController {
    private final WebhookVerifier verifier;
    private final ProviderEventAdapter adapter;
    private final EmailEventIngestion ingestion;

    public EmailWebhookController(
            WebhookVerifier verifier,
            ProviderEventAdapter adapter,
            EmailEventIngestion ingestion) {
        this.verifier = verifier;
        this.adapter = adapter;
        this.ingestion = ingestion;
    }

    @PostMapping
    public ResponseEntity<Void> receive(
            @RequestHeader("X-Provider-Signature") String signature,
            @RequestHeader("X-Provider-Timestamp") String timestamp,
            @RequestBody String rawBody) {

        // Chữ ký phải được kiểm trên rawBody, theo chuẩn của ESP thực tế.
        if (!verifier.isAuthentic(rawBody, timestamp, signature)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }

        List<EmailEvent> events = adapter.toInternalEvents(rawBody);
        ingestion.persistIdempotently(events);
        return ResponseEntity.noContent().build();
    }
}
```

Các giao diện thuộc domain của ứng dụng:

```java
package example.mail.tracking;

import java.time.Instant;
import java.util.List;

public record EmailEvent(
        String provider,
        String providerEventId,
        String deliveryId,
        EventType type,
        Instant occurredAt,
        String linkId) {
}

enum EventType {
    ACCEPTED, DELIVERED, OPENED, CLICKED,
    DEFERRED, BOUNCED, DROPPED, COMPLAINED, UNSUBSCRIBED
}

interface WebhookVerifier {
    boolean isAuthentic(String rawBody, String timestamp, String signature);
}

interface ProviderEventAdapter {
    List<EmailEvent> toInternalEvents(String rawBody);
}

interface EmailEventIngestion {
    void persistIdempotently(List<EmailEvent> events);
}
```

Đây là **bộ khung minh họa ranh giới trách nhiệm**, chưa phải tích hợp hoàn chỉnh với ESP: header, thuật toán chữ ký, cấu trúc payload, chính sách retry và khóa tra cứu delivery đều phải triển khai theo tài liệu của nhà cung cấp cụ thể. Không được thay `WebhookVerifier` bằng hàm luôn trả `true` trong hệ thống thực.

Một implementation cần xác thực chữ ký trên **payload gốc** bằng thuật toán provider quy định, so sánh an toàn, giới hạn độ lệch timestamp và chống replay nếu giao thức hỗ trợ. Xử lý webhook nên hoàn thành nhanh; nếu cần hàng đợi, ghi bền vững thông điệp vào queue trước khi phản hồi thành công. Trả mã HTTP 2xx khi sự kiện đã được tiếp nhận bền vững; nếu xử lý thất bại tạm thời, phản hồi theo hợp đồng retry của ESP.

### Lưu event không xử lý trùng

Ví dụ bảng PostgreSQL:

```sql
CREATE TABLE email_delivery (
    delivery_id UUID PRIMARY KEY,
    notification_id UUID NOT NULL,
    recipient_ref VARCHAR(128) NOT NULL,
    provider_message_id VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE email_event (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    delivery_id UUID NOT NULL REFERENCES email_delivery(delivery_id),
    provider VARCHAR(100) NOT NULL,
    provider_event_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    link_id VARCHAR(128),
    UNIQUE (provider, provider_event_id)
);

CREATE INDEX email_event_delivery_type_idx
    ON email_event (delivery_id, event_type, occurred_at);
```

Nếu provider cung cấp `provider_event_id` ổn định, có thể xử lý trùng an toàn bằng unique constraint, ví dụ `INSERT ... ON CONFLICT DO NOTHING`. Không nên mặc định rằng mọi provider đều có event ID, cũng không nên chống trùng bằng `(delivery_id, event_type)`, vì một email có thể thực sự được mở hoặc click nhiều lần. Cần chọn khóa idempotency theo khả năng và hợp đồng của từng nguồn.

Nếu payload chứa nhiều event, lưu bền vững trong transaction hoặc queue bảo đảm cách retry phù hợp. Khi event tới trước khi mapping provider message ID được lưu, có thể tạm lưu event chưa liên kết và đối soát sau; không vứt event chỉ vì thứ tự đến bất ngờ.

## 9. Thời gian của event và quy tắc cập nhật

Hệ thống tích hợp nhiều webhook có ít nhất hai mốc thời gian:

- `occurred_at`: nguồn sự kiện nói hành động xảy ra khi nào.
- `received_at`: backend nhận và lưu sự kiện khi nào.

Hai timestamp có thể cách nhau vài phút hoặc hơn nếu ESP retry, mạng tắc nghẽn hoặc hệ thống tạm ngừng. Luồng event cũng có thể **giao trễ, giao lặp hoặc không theo thứ tự**.

Không nên dùng mỗi quy tắc “event mới nhận sẽ ghi đè status hiện tại”, bởi một webhook `accepted` đến trễ có thể vô tình thay trạng thái `delivered` đã biết. Một cách tốt hơn là:

1. Lưu event gốc cùng nguồn và hai timestamp.
2. Kiểm tra trùng dựa vào event ID/khóa ổn định.
3. Tạo projection cho câu hỏi cụ thể: đã từng accepted? đã từng delivered? có bounce cuối cùng? có tín hiệu open? link nào được click?
4. Khi muốn hiển thị một status duy nhất, đặt quy tắc ưu tiên rõ ràng cho các event vận chuyển (ví dụ bounced/failed liên quan trực tiếp đến delivery), đồng thời giữ các tín hiệu tương tác thành thuộc tính riêng.

Báo cáo và công cụ vận hành có thể biểu diễn như sau:

```json
{
  "deliveryId": "d-001",
  "transport": {
    "accepted": true,
    "delivered": true,
    "bounced": false
  },
  "engagement": {
    "openSignalObserved": true,
    "trackedLinkAccessObserved": true
  }
}
```

Cấu trúc này tránh mâu thuẫn giả tạo “đã clicked thì status còn là delivered hay không?”. Delivered và clicked mô tả **hai chiều khác nhau**: vận chuyển và tương tác.

## 10. Tính chỉ số accepted, delivered, opened và clicked

Nếu dùng telemetry cho báo cáo, phải chọn **đơn vị tính** (một email gửi tới một người nhận), **nhóm gửi** (cohort) và định nghĩa sự kiện thống nhất.

Ví dụ, trong một chiến dịch có 1.000 delivery được ESP accepted, 970 delivery có event delivered, 700 delivery có ít nhất một open signal và 125 delivery có ít nhất một tracked click. Giả sử các con số là **số delivery duy nhất** thuộc cùng cohort:

| Chỉ số | Công thức | Kết quả minh họa |
| --- | --- | --- |
| Delivery rate | `970 / 1.000 × 100%` | `97,0%` |
| Unique open-signal rate | `700 / 970 × 100%` | `72,2%` |
| Unique tracked-click rate | `125 / 970 × 100%` | `12,9%` |
| Click-to-open ratio | `125 / 700 × 100%` | `17,9%` |

**Các tỷ lệ không thay thế nhau.** Delivery rate giúp theo dõi khả năng giao thư; open-signal rate chịu ảnh hưởng đáng kể từ ảnh/proxy/privacy; tracked-click rate có thể bị scanner hoặc tracking blocker tác động; click-to-open ratio kế thừa sai lệch của cả open lẫn click.

Để tránh kết luận sai:

- Dùng `COUNT(DISTINCT delivery_id)` cho **unique opens/clicks**, khác với tổng số event.
- Định nghĩa rõ “denominator”: accepted, delivered, attempted, hay toàn bộ yêu cầu gửi; mỗi mẫu số trả lời một câu hỏi khác.
- Tính theo cohort email được khởi tạo trong cùng một khoảng thời gian và chừa cửa sổ quan sát đủ dài cho event đến trễ; tránh đếm accepted của hôm nay nhưng delivered của ngày khác mà không gắn cùng cohort.
- Với nhiều recipient trong một API call, đếm theo delivery/recipient, không đếm một message chung thành một delivery.
- Tách bot-detected click và auto-prefetch open nếu ESP có phân loại; ghi chú độ tin cậy và phương pháp lọc.
- Không coi `opened_count > 0` là bằng chứng nghĩa vụ pháp lý “đã đọc”, hoặc `clicked_count > 0` là chứng cứ hoàn tất thao tác tài chính.

### Ví dụ phân biệt chỉ số truyền thông và chỉ số nghiệp vụ

Một email yêu cầu người dùng xác nhận đơn hàng có các event sau:

```text
delivery accepted
delivery delivered
tracked link clicked
checkout page visited
user authenticated
order confirmation submitted
```

Để biết email có được gửi và hệ thống đích nhận hay không, đọc `accepted` và `delivered`. Để biết liên kết có được truy cập hay không, đọc `clicked`. Để chứng minh người dùng xác nhận đơn hàng, dùng **event xác nhận đã xác thực từ hệ thống nghiệp vụ**; nó có tiêu chuẩn dữ liệu khác và không phụ thuộc vào pixel hoặc redirect.

## 11. Quyền riêng tư, bảo mật và khả năng quan sát

Open/click tracking liên quan đến hành vi của người nhận. Vì vậy cần xem xét mục đích đo lường, lựa chọn người dùng, chính sách dữ liệu của tổ chức và quy định áp dụng trước khi bật tracking.

Các nguyên tắc thực tế trong kiến trúc:

1. **Giảm thiểu dữ liệu**: chỉ lưu những trường cần cho phân tích/vận hành. Tránh đưa email, token đăng nhập, mã xác thực, thông tin đơn hàng nhạy cảm vào URL pixel hoặc redirect.
2. **Token không dễ đoán**: sử dụng định danh ngẫu nhiên hoặc token được ký phù hợp, gắn với delivery/link trong backend; đặt thời hạn lưu hoặc hủy hiệu lực khi phù hợp. Đừng để link theo dõi trở thành open redirect cho URL tùy ý.
3. **Tách tracking khỏi authorization**: URL tracking không được cấp quyền truy cập nghiệp vụ; backend đích vẫn xác thực và kiểm tra quyền.
4. **Bảo vệ webhook**: xác minh chữ ký, thời gian và nguồn theo cơ chế ESP; idempotency khi retry; hạn chế public endpoint chỉ chấp nhận payload hợp lệ.
5. **Chính sách lưu trữ**: giới hạn thời gian giữ event và truy cập dashboard; ẩn thông tin cá nhân trong log, báo cáo và bản sao lưu theo chính sách tổ chức.
6. **Minh bạch phép đo**: trong báo cáo, ghi “open signals” hoặc “tracked clicks” nếu đó là dữ liệu thực sự đo được, thay vì khẳng định chắc chắn đã đọc/đã hành động.

Với các tính năng như xác minh email, đăng nhập không mật khẩu hoặc đặt lại mật khẩu, nên đặc biệt tránh việc một **GET tự động từ scanner** kích hoạt hành động có hiệu lực ngay. Trang đích có thể hiển thị thông tin an toàn trước, rồi người dùng xác nhận qua một thao tác chủ động; quy trình xác thực và chống replay cần được áp dụng theo mức độ nhạy cảm.

## 12. Tình huống thực tế: theo dõi email xác nhận đơn hàng

Giả sử một hệ thống Spring gửi email sau khi khách hàng đặt hàng:

**Bước A — Người dùng đặt hàng.** Backend tạo `notification_id` và một `delivery_id` cho email cần gửi. Hệ thống nghiệp vụ đã biết đơn hàng được tạo; chưa có bằng chứng SMTP nào.

**Bước B — Spring gọi `JavaMailSender.send`.** Nếu thành công, backend ghi `submitted_at` và kết quả tương ứng. Đây là mức quan sát được từ ứng dụng; không đặt `delivered=true`.

**Bước C — ESP nhận và xử lý.** Webhook `accepted` xác nhận theo định nghĩa của ESP; nếu máy chủ đích tạm thời không nhận, có thể xuất hiện `deferred`. Nếu thư không thể giao, có thể có `bounced`.

**Bước D — Máy chủ thư phía nhận trả kết quả thành công.** ESP báo `delivered`. Dashboard hiển thị “Hệ thống thư phía nhận đã chấp nhận”, không hiển thị “Khách hàng đã đọc”.

**Bước E — Ảnh được tải.** ESP báo `opened`. Ghi nhận `openSignalObserved=true`, nhưng không sử dụng tín hiệu này để kết luận khách hàng đã xem nội dung.

**Bước F — Liên kết được truy cập.** ESP báo `clicked`. Dashboard ghi nhận lượt truy cập liên kết; nếu website nhận được hành động xác nhận đơn hàng đã xác thực, backend tạo một **business event riêng**.

Trong tình huống này, bốn trạng thái giúp trả lời bốn câu hỏi khác nhau:

| Câu hỏi | Tín hiệu phù hợp nhất |
| --- | --- |
| Hệ thống gửi có nhận yêu cầu chuyển thư chưa? | `accepted`, hoặc submission từ ứng dụng tùy ranh giới |
| Phía nhận đã chấp nhận thư chưa? | `delivered` theo định nghĩa ESP |
| Có dấu hiệu nội dung email được tải để hiển thị không? | `opened` |
| Có truy cập liên kết theo dõi không? | `clicked` |
| Khách hàng thực sự xác nhận đơn hàng chưa? | **Business event** từ backend đã xác thực |

Nguyên tắc thiết kế là **đo đúng điều từng sự kiện có thể chứng minh**, giữ event gốc để đối soát, và không đồng nhất trạng thái vận chuyển email với hành vi của người dùng. Trong Spring Framework Mail, `JavaMailSender` giải quyết việc gửi SMTP; còn delivered, opened và clicked cần được lấy từ hạ tầng giao thư/tracking và tích hợp vào hệ thống event của ứng dụng.
