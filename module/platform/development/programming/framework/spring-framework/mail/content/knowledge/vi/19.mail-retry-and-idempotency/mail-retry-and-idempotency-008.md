# Ngăn gửi trùng sau timeout không rõ kết quả

Khi ứng dụng gửi email bằng **Spring Framework Mail**, một lần gọi **JavaMailSender.send(...)** có thể kết thúc bằng timeout. Câu hỏi khó nhất không phải chỉ là “làm sao thử lại?”, mà là **“email trước đó đã được SMTP server nhận hay chưa?”**. Nếu server đã chấp nhận thư nhưng phản hồi thành công bị mất trên đường truyền, ứng dụng có thể ghi nhận một lần gửi thất bại và gửi lại cùng email. Người nhận khi đó có thể nhận hai thư dù người dùng chỉ thao tác một lần.

Vấn đề này đặc biệt quan trọng với email xác nhận đơn hàng, hóa đơn, cấp quyền, mã xác thực, liên kết khôi phục mật khẩu và các thông báo giao dịch. Một email chào mừng bị gửi trùng có thể gây phiền; hai email chứa mã dùng một lần khác nhau hoặc hai hóa đơn cùng số giao dịch có thể khiến người nhận nghi ngờ hệ thống.

Bài học tập trung vào **timeout có kết quả không xác định (ambiguous outcome)**, cách thiết kế **idempotency key**, trạng thái gửi **UNKNOWN**, hàng đợi **transactional outbox**, cơ chế **reconciliation** và chính sách retry an toàn. Ví dụ sử dụng Spring Mail với SMTP; khi so sánh với email provider API, cần phân biệt rõ khả năng deduplication do provider thực sự cung cấp với metadata tự đặt trong MIME message.

> **Nguyên tắc chính:** Không xem mọi timeout là “chưa gửi”, không coi việc gắn Message-ID là bảo đảm chống gửi trùng, và không tuyên bố exactly-once email delivery chỉ vì đã thêm retry hoặc outbox.

## 1. Tình huống: SMTP đã nhận thư nhưng ứng dụng báo timeout

Một luồng gửi đơn giản:

~~~text
OrderService
    |
    v
JavaMailSender.send(...)
    |
    v
SMTP server
    |
    v
Phản hồi thành công
    |
    v
Ứng dụng đánh dấu SENT
~~~

Nhưng mạng có thể bị gián đoạn đúng thời điểm SMTP server gửi phản hồi:

~~~text
Ứng dụng Spring                      SMTP server
       |                                  |
       |-- MAIL FROM -------------------->|
       |<--------------------------- 250 -|
       |-- RCPT TO ---------------------->|
       |<--------------------------- 250 -|
       |-- DATA ------------------------->|
       |<--------------------------- 354 -|
       |-- MIME body + <CRLF>.<CRLF> ---->|
       |                                  | nhận và xếp hàng
       |              X (mất kết nối)     |
       |<--- 250 accepted (bị mất) -------|
       |                                  |
    Timeout                               |
       |                                  |
       v                                  v
  Không biết kết quả               Thư đã được nhận
~~~

Ở đây, server **có thể đã chấp nhận message**, nhưng client không nhận được câu trả lời cuối cùng. Nếu ứng dụng lập tức retry toàn bộ message, server có thể chấp nhận cả lần thứ hai.

### Hai thế giới không thể phân biệt từ phía client

Cùng một lỗi timeout được quan sát, có thể tồn tại hai tình huống:

| Thế giới | Điều đã xảy ra trên server | Điều ứng dụng nhìn thấy |
| --- | --- | --- |
| **A** | Server chưa nhận/chưa chấp nhận message | Timeout |
| **B** | Server đã chấp nhận message; phản hồi bị mất | Timeout |

Nếu không có bằng chứng bổ sung, ứng dụng **không thể suy ra chắc chắn A hay B chỉ từ exception timeout**.

Nếu retry khi thực tế là B, có nguy cơ gửi trùng. Nếu không retry khi thực tế là A, có nguy cơ email bị bỏ lỡ. Đây là sự đánh đổi bản chất của việc gửi sang một hệ thống bên ngoài qua mạng.

### “Server accepted” không đồng nghĩa “Inbox delivered”

Phản hồi thành công sau lệnh SMTP DATA thường cho biết **SMTP server đã chấp nhận trách nhiệm xử lý message**. Nó không bảo đảm:

- Thư đã được chuyển tới mailbox cuối cùng.
- Thư không bị bounce về sau.
- Thư không đi vào thư mục spam.
- Người nhận đã mở hoặc đọc thư.

Vì vậy, nên phân biệt trạng thái **ACCEPTED/SUBMITTED** với **DELIVERED** nếu hệ thống có tích hợp delivery events của provider. Trong ví dụ về chống gửi trùng, “đã gửi thành công” được hiểu là đã được transport/provider chấp nhận, không phải chắc chắn đã vào Inbox.

## 2. Timeout nào thực sự tạo ra kết quả không rõ?

Không phải tất cả lỗi kết nối đều có độ mơ hồ giống nhau. Vị trí xảy ra lỗi trong giao thức ảnh hưởng đến khả năng server đã nhận message.

| Thời điểm lỗi | Nhận định hợp lý | Hành động |
| --- | --- | --- |
| Không thể thiết lập kết nối TCP và chưa gửi SMTP command | Thường chưa có message nào được truyền trên kết nối đó | Có thể retry sau khi xác định chắc đây là lỗi trước khi truyền |
| Không hoàn thành SMTP authentication | Thường message chưa được nộp | Sửa thông tin đăng nhập/cấu hình; không retry vô hạn |
| Server trả lỗi rõ ràng ở MAIL FROM hoặc RCPT TO | Message chưa được hoàn tất qua DATA cho những người nhận bị từ chối | Phân loại lỗi và người nhận theo phản hồi |
| Server trả lỗi rõ ràng khi chưa chấp nhận DATA | Có bằng chứng từ chối ở giai đoạn đó | Theo chính sách mã phản hồi |
| Mất kết nối khi đang truyền DATA | Chưa biết server đã nhận đủ phần kết thúc message hay chưa | Xử lý thận trọng; đánh dấu UNKNOWN nếu không chứng minh được |
| Mất kết nối hoặc read timeout khi chờ phản hồi cuối sau DATA | **Có thể server đã chấp nhận message** | UNKNOWN; ưu tiên đối soát |
| Client nhận phản hồi thành công cuối cùng | Có bằng chứng SMTP server đã chấp nhận message | Đánh dấu ACCEPTED, không retry vì lỗi mạng khác về sau |
| Ứng dụng chết sau SMTP success nhưng trước khi lưu kết quả | Server có thể đã chấp nhận, database chưa ghi nhận | UNKNOWN khi phục hồi; cần reconciliation |

Bảng trên là hướng phân loại. Một exception từ thư viện có thể không chứa đủ thông tin để kết luận chính xác server đã đi tới command nào. Nếu không có bằng chứng chắc chắn về giai đoạn lỗi, nên mặc định thận trọng thay vì ép timeout về trạng thái “chưa gửi”.

### Phân biệt lỗi được từ chối và lỗi không nhận được phản hồi

Nếu server gửi một phản hồi SMTP rõ ràng, ứng dụng có bằng chứng để phân loại:

- **4xx** thường chỉ lỗi tạm thời; có thể thử lại theo chính sách khi điều kiện cho phép.
- **5xx** thường chỉ lỗi vĩnh viễn ở bước đó; không nên retry vô hạn.
- **2xx** cho thấy thao tác SMTP tương ứng được chấp nhận.

Ngược lại, **timeout không phải một mã phản hồi SMTP**. Nó thường cho biết client không nhận được kết quả đúng thời hạn, nên không thể suy luận “server trả 4xx” hoặc “server đã từ chối”.

Lưu ý một lần gửi cho nhiều người nhận có thể có kết quả từng recipient khác nhau. Nếu cần chống trùng theo từng người nhận, nên lưu trạng thái cụ thể cho từng recipient hoặc gửi riêng từng notification theo hợp đồng nghiệp vụ.

## 3. Ba khái niệm phải tách bạch

### Retry — thử thực hiện lại

**Retry** là việc lặp lại một thao tác sau lỗi. Retry giúp vượt qua lỗi tạm thời như network outage hoặc SMTP 4xx, nhưng có thể gây trùng nếu thao tác trước đó đã có hiệu lực.

### Idempotency — nhiều yêu cầu tương đương chỉ có một hiệu ứng logic

Một thao tác được xem là idempotent trong một phạm vi nhất định nếu lặp lại nó với cùng định danh không tạo thêm tác động nghiệp vụ ngoài hiệu ứng đã có. Ví dụ, API nhận yêu cầu **gửi hóa đơn cho đơn hàng ORD-1528, phiên bản 1** có thể chỉ tạo một công việc mail outbox cho cùng khóa.

Tuy nhiên, chống trùng ở **tầng tạo công việc** khác với chống trùng ở **tầng SMTP chấp nhận message**.

### Deduplication — phát hiện và loại bỏ yêu cầu trùng

**Deduplication** sử dụng một định danh hoặc fingerprint để nhận ra hai yêu cầu thuộc cùng một thao tác logic. Nó có thể được triển khai tại:

- API nhận yêu cầu.
- Database outbox/job queue.
- Worker trước khi gửi.
- Email provider API, **chỉ nếu provider công bố và hỗ trợ idempotency/deduplication**.

Không tồn tại một cơ chế deduplication mặc định áp dụng chung cho mọi SMTP server.

### Phân biệt ba tầng bảo đảm

| Tầng | Có thể bảo đảm điều gì? | Không tự bảo đảm điều gì? |
| --- | --- | --- |
| **Business API** | Một thao tác nghiệp vụ tương đương được nhận một lần theo key | Chỉ có một lần gửi qua SMTP |
| **Outbox + unique key** | Một notification logic có một bản ghi công việc | Worker không bao giờ gửi trùng sau crash |
| **Provider có idempotency thực sự** | Provider có thể không tạo thêm một lần submission khi retry cùng key trong thời hạn hỗ trợ | Tất cả mailboxes chỉ nhận đúng một bản hoặc provider khác cũng hỗ trợ |

Muốn biết hệ thống đạt mức nào, phải kiểm tra **ở ranh giới nào deduplication thực sự được thực thi**.

## 4. Message-ID có giúp ngăn gửi trùng không?

Email có header **Message-ID**, ví dụ:

~~~text
Message-ID: <order-1528-v1@mail.example.test>
~~~

Header này giúp định danh một email message để phục vụ threading, tra cứu và correlation. Ứng dụng có thể chọn một Message-ID ổn định cho một notification logic theo quy ước hợp lệ.

Nhưng có hai giới hạn:

1. **SMTP không yêu cầu server từ chối message chỉ vì Message-ID đã từng xuất hiện**.
2. Hai lần SMTP submission với cùng Message-ID vẫn **có thể tạo hai bản thư** ở phía nhận.

Vì vậy, **Message-ID không phải một idempotency key có bảo đảm universal ở tầng SMTP**.

### Đặt Message-ID để phục vụ đối soát

Một Message-ID ổn định, ngẫu nhiên/duy nhất ở phạm vi hệ thống có thể giúp:

- Tìm message tương ứng trong log SMTP/provider.
- Liên kết mail event với outbox record.
- Hỗ trợ điều tra khi server báo nhận còn ứng dụng ghi timeout.

Nếu muốn tự đặt Message-ID bằng Jakarta Mail, cần lưu ý **MimeMessage.saveChanges()** hoặc thao tác send có thể sinh/cập nhật header tùy implementation. Hãy xác nhận Message-ID cuối cùng trong MIME thực tế và theo cách provider bảo toàn header; không giả định việc set một header trước send chắc chắn tồn tại nguyên vẹn.

Đối với provider API có hỗ trợ **Idempotency-Key**, **client token** hoặc khóa chống gửi trùng theo tài liệu của họ, cơ chế đó khác với Message-ID: provider có thể tra/lưu kết quả của yêu cầu API dựa trên key và từ chối tạo thêm submission tương đương. Phải kiểm tra rõ phạm vi, thời gian lưu key và điều kiện payload phải giống nhau.

### Một khóa ổn định không được dùng lại cho nội dung khác

Ví dụ, cùng một order có thể cần:

- Email xác nhận đơn hàng lần đầu.
- Email thông báo thay đổi đơn hàng.
- Email gửi lại hóa đơn phiên bản mới theo yêu cầu.

Ba thông báo đó không nên dùng cùng một key chỉ vì chúng có chung order ID. Cần phân biệt **loại sự kiện**, **phiên bản** và **đích nhận**.

## 5. Thiết kế idempotency key theo ý nghĩa nghiệp vụ

Khóa chống trùng nên mô tả **một lần thông báo logic**, không mô tả một lần thực thi kỹ thuật.

Ví dụ:

~~~text
tenant       = shop-7
eventType    = ORDER_CONFIRMED
aggregateId  = ORD-1528
eventVersion = 1
recipientId  = customer-392

notificationKey =
  shop-7:ORDER_CONFIRMED:ORD-1528:1:customer-392
~~~

Cùng một sự kiện được delivery hoặc xử lý lại sẽ tạo cùng key; một sự kiện mới có version khác tạo key khác.

### Vì sao không dùng UUID ngẫu nhiên mới cho mỗi retry?

Nếu mỗi lần retry tạo một UUID mới:

~~~text
Lần 1: key = 1a2b...
Lần 2: key = 7c8d...
~~~

thì hệ thống không có cách nhận ra hai lần đó thuộc cùng một notification. UUID ngẫu nhiên phù hợp làm **ID của notification khi nó được tạo lần đầu**; các attempt sau phải dùng lại ID/key đã lưu thay vì tạo một notification mới.

### Những thành phần của key

| Thành phần | Mục đích |
| --- | --- |
| **tenantId** | Tách cùng mã nghiệp vụ ở nhiều tenant |
| **eventType** | Phân biệt xác nhận đơn, hủy đơn, nhắc thanh toán |
| **aggregateId** | Gắn notification với thực thể nghiệp vụ |
| **eventVersion/sequence** | Phân biệt thông báo mới trên cùng thực thể |
| **recipientIdentity** | Phân biệt người nhận theo hợp đồng gửi |

Không phải mọi hệ thống đều cần đầy đủ năm thành phần. Nếu event upstream đã có một ID ổn định duy nhất, có thể dùng ID đó kết hợp tenant/recipient và loại notification.

Khi tạo key dạng chuỗi, cần quy định cách encode/escape thành phần để không có collision vì ký tự phân cách. Một cách khác là serialize các trường với schema ổn định rồi hash. **Không dùng một hash của nội dung email đã render làm key duy nhất**, vì thay đổi template, timestamp hoặc tracking parameters có thể khiến cùng sự kiện tạo nội dung khác, phá deduplication.

### Khi người dùng yêu cầu “gửi lại”

Một thao tác **resend** có chủ đích khác với **retry vì timeout**:

- **Retry**: cố hoàn tất cùng notification đã phát sinh trước đó; giữ nguyên notification ID/key.
- **Resend**: người dùng hoặc nhân viên tạo một yêu cầu gửi mới có chủ đích; nên ghi một event/notification ID mới và liên kết tới thông báo gốc.

Nếu dùng lại key gốc cho resend, deduplication có thể loại bỏ yêu cầu hợp lệ. Nếu cấp key mới cho retry, hệ thống có thể gửi trùng ngoài ý muốn. Hãy phân biệt hai hành động tại API và trong data model.

### Người nhận cũng là một phần của hợp đồng

Nếu email cần gửi tới nhiều người:

~~~text
ORDER_CONFIRMED:ORD-1528:v1:recipient-A
ORDER_CONFIRMED:ORD-1528:v1:recipient-B
~~~

Hai người nhận có thể cần hai notification riêng. Nếu business notification có To/Cc/Bcc kết hợp, idempotency key phải đại diện chính xác cho **tập người nhận** theo chính sách nghiệp vụ. Tránh suy luận rằng mỗi địa chỉ chỉ có một hộp thư hoặc tự chuẩn hóa địa chỉ email bằng các quy tắc đặc thù một provider; nên dùng recipient ID ổn định hoặc quy tắc canonicalization đã được hệ thống chấp nhận.

## 6. Đặt rào chắn deduplication ở database

Một kiểm tra thuần Java kiểu “tìm chưa có thì insert” có thể bị race condition khi nhiều thread hoặc nhiều instance cùng nhận một event:

~~~text
Worker A                         Worker B
   |                                |
   v                                v
SELECT key -> chưa có          SELECT key -> chưa có
   |                                |
   v                                v
INSERT notification           INSERT notification
~~~

Nếu không có ràng buộc duy nhất, cả hai lần insert có thể thành công và tạo hai công việc gửi cùng email.

### Ràng buộc unique là điểm chặn cuối cùng

Một bảng outbox có thể dùng:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    notification_key VARCHAR(300) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    recipient_email VARCHAR(320) NOT NULL,
    template_code VARCHAR(120) NOT NULL,
    template_version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    status VARCHAR(30) NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    lease_owner VARCHAR(120),
    lease_token BIGINT NOT NULL DEFAULT 0,
    lease_until TIMESTAMPTZ,
    client_correlation_id VARCHAR(120) NOT NULL,
    provider_message_id VARCHAR(200),
    last_error_code VARCHAR(100),
    next_attempt_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    accepted_at TIMESTAMPTZ,
    CONSTRAINT uq_mail_notification
        UNIQUE (tenant_id, notification_key)
);
~~~

Đây là DDL minh họa cho PostgreSQL, không phải schema bắt buộc của Spring Mail. Tên cột và kiểu dữ liệu cần điều chỉnh theo database/ORM thực tế. Các trường quan trọng:

- **notification_key**: định danh nghiệp vụ ổn định.
- **id**: ID bản ghi và tham chiếu từ attempt log.
- **client_correlation_id**: định danh ổn định do ứng dụng tạo trước khi gửi để đối soát.
- **status**: trạng thái submission đang biết.
- **lease_owner/lease_token/lease_until**: hỗ trợ nhiều worker và tránh ghi đè trạng thái cũ.
- **provider_message_id**: ID do provider trả, nếu có.

Ràng buộc UNIQUE phải được enforce ở database, không chỉ bằng **existsBy...** trong ứng dụng. Nó giúp bảo đảm các lần nhận event trùng không tạo hai bản ghi notification logic.

### Chèn idempotent trong transaction nghiệp vụ

Ví dụ SQL của PostgreSQL:

~~~sql
INSERT INTO mail_outbox (
    id, tenant_id, notification_key, event_type,
    recipient_email, template_code, template_version,
    payload_json, status, client_correlation_id
)
VALUES (
    :id, :tenant_id, :notification_key, :event_type,
    :recipient_email, :template_code, :template_version,
    :payload_json, 'PENDING', :correlation_id
)
ON CONFLICT (tenant_id, notification_key) DO NOTHING;
~~~

Nếu cùng key đã tồn tại, insert không tạo một notification mới. Khi xử lý conflict, service cần lấy lại ID/trạng thái của record hiện có thay vì giả định một insert thành công.

**Cùng key phải cùng ý nghĩa nghiệp vụ.** Nếu request dùng lại key nhưng mang payload không tương đương, nên báo conflict hoặc ghi nhận vấn đề dữ liệu; không âm thầm thay payload của notification đang xử lý. Có thể lưu fingerprint của payload đã chuẩn hóa để phát hiện tình huống này.

### Không chỉ dùng synchronized hoặc in-memory Set

~~~java
if (!sentKeys.contains(key)) {
    sentKeys.add(key);
    mailSender.send(message);
}
~~~

Cách này không đủ vì:

- Khi restart, tập key trong RAM bị mất.
- Nhiều instance có Set khác nhau.
- Không giải quyết crash giữa gửi mail và cập nhật key.
- Không cung cấp trạng thái UNKNOWN để đối soát.

Một database unique constraint hoặc storage idempotency bền vững là nền tảng tốt hơn.

## 7. Transactional outbox: một công việc bền vững cho mỗi notification

**Transactional outbox** lưu công việc gửi mail trong cùng database transaction với sự kiện nghiệp vụ. Nó giúp tránh trường hợp đơn hàng đã commit nhưng event gửi mail chưa được ghi.

~~~text
HTTP request / event consumer
             |
             v
       BEGIN TRANSACTION
             |
             +--> Save Order
             |
             '--> INSERT mail_outbox(PENDING)
                    với UNIQUE notification key
             |
             v
           COMMIT
             |
             v
      Background mail worker
             |
             v
       Send via SMTP
~~~

Nếu transaction rollback, cả Order và mail_outbox đều rollback. Nếu commit, outbox row tồn tại để worker có thể phục hồi sau restart.

### Ví dụ Spring service ghi outbox cùng transaction

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final MailOutboxRepository outboxRepository;

    public OrderApplicationService(
            OrderRepository orderRepository,
            MailOutboxRepository outboxRepository
    ) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
    }

    @Transactional
    public Order placeOrder(CreateOrderCommand command) {
        Order order = orderRepository.save(Order.create(command));

        String key = String.join(
                ":",
                order.getTenantId(),
                "ORDER_CONFIRMED",
                order.getBusinessId(),
                String.valueOf(order.getVersion()),
                order.getCustomerId()
        );

        outboxRepository.insertIfAbsent(
                MailOutboxDraft.orderConfirmed(order, key)
        );

        return order;
    }
}
~~~

**MailOutboxRepository** và **MailOutboxDraft** là các thành phần do ứng dụng định nghĩa, không phải API Spring có sẵn. **insertIfAbsent** cần dùng unique constraint/upsert phù hợp với database. Toàn bộ thao tác lưu Order và Outbox phải dùng cùng transaction manager và transaction vật lý để có tính nguyên tử.

### Lưu snapshot cần thiết để tạo email

Outbox payload có thể chứa:

- Order ID và order version.
- Recipient ID và địa chỉ nhận đã được xác định.
- Mã template và phiên bản template.
- Thông tin cần render hoặc tham chiếu tới snapshot dữ liệu có thể đọc lại.

Nếu chỉ giữ order ID và worker đọc dữ liệu mới nhất, nội dung email có thể thay đổi khi order được sửa trong lúc chờ retry. Nếu notification cần phản ánh đúng thời điểm phát sinh, hãy lưu snapshot có chủ đích và dùng phiên bản template ổn định.

Không lưu mật khẩu, SMTP credentials hoặc token bí mật không cần thiết. Nếu cần gửi link có token, hãy thiết kế vòng đời/token rotation và chính sách bảo vệ dữ liệu lưu trong outbox. Dữ liệu outbox có thể chứa PII nên cần kiểm soát quyền, retention và mã hóa khi cần.

## 8. Mô hình trạng thái có UNKNOWN

Nếu trạng thái gửi chỉ có **PENDING**, **SENT** và **FAILED**, timeout có xu hướng bị ép vào FAILED rồi được retry ngay. Điều đó che mất sự khác biệt giữa “chưa gửi” và “không biết đã gửi hay chưa”.

Một state machine rõ hơn:

| Trạng thái | Ý nghĩa | Retry tự động? |
| --- | --- | --- |
| **PENDING** | Công việc chưa bắt đầu gửi | Có, khi đến lịch |
| **IN_FLIGHT** | Worker đã claim và đang thực hiện attempt | Không cho worker khác gửi song song |
| **ACCEPTED** | Có bằng chứng provider/SMTP đã chấp nhận | Không |
| **RETRYABLE_FAILED** | Có bằng chứng lỗi tạm thời và retry được | Có theo backoff |
| **PERMANENT_FAILED** | Lỗi không nên retry tự động | Không; cần sửa dữ liệu/cấu hình |
| **UNKNOWN** | Không xác định attempt đã được provider chấp nhận chưa | **Không retry mù**; đối soát hoặc theo chính sách rủi ro |
| **CANCELLED** | Notification bị hủy có chủ đích | Không |

Trạng thái **UNKNOWN** là một trạng thái có ý nghĩa nghiệp vụ, không chỉ là một exception message.

~~~text
PENDING
   |
   v
IN_FLIGHT
   |
   +-- nhận SMTP 250 / provider accepted --> ACCEPTED
   |
   +-- lỗi tạm thời được xác nhận -----> RETRYABLE_FAILED
   |                                      |
   |                                      v (backoff)
   |                                    PENDING
   |
   +-- lỗi vĩnh viễn được xác nhận ---> PERMANENT_FAILED
   |
   '-- timeout / crash / mất ACK -----> UNKNOWN
                                          |
                                          +-- đối soát found --> ACCEPTED
                                          |
                                          +-- chắc chắn chưa gửi --> PENDING
                                          |
                                          '-- chưa có bằng chứng --> tiếp tục UNKNOWN
~~~

Nhánh **UNKNOWN -> PENDING** chỉ an toàn khi có bằng chứng đủ tin cậy rằng provider chưa nhận, hoặc provider có cơ chế idempotency thực sự cho cùng key. Nếu không, đó là quyết định đánh đổi giữa nguy cơ mất thông báo và nguy cơ gửi trùng, cần được xác định bởi chính sách sản phẩm chứ không được giả định là luôn an toàn.

## 9. Một attempt gửi email cần được ghi lại như thế nào?

**Notification** là công việc nghiệp vụ duy nhất. **Attempt** là một lần cố gửi notification đó qua transport. Một notification có thể có nhiều attempt vì lỗi tạm thời hoặc retry có chủ đích.

~~~text
Notification: ORDER_CONFIRMED / ORD-1528 / v1 / recipient-392
       |
       +-- Attempt #1: timeout sau DATA => UNKNOWN
       |
       +-- Attempt #2: chỉ tạo nếu được phép retry
       |
       '-- Final outcome: ACCEPTED / PERMANENT_FAILED / UNKNOWN
~~~

Việc lưu riêng attempt có lợi vì cần biết **điểm lỗi của mỗi lần gửi**, không chỉ trạng thái cuối:

| Trường attempt | Ví dụ | Mục đích |
| --- | --- | --- |
| **attemptId** | UUID | Phân biệt từng lần thực thi |
| **notificationId** | UUID của outbox | Liên kết về notification gốc |
| **attemptNumber** | 1, 2, 3 | Quan sát và áp retry limit |
| **startedAt** | Thời điểm bắt đầu | Điều tra thời gian thực thi |
| **completedAt** | Thời điểm hoàn tất nếu có | Biết attempt đã kết thúc hay bị gián đoạn |
| **outcome** | ACCEPTED, REJECTED, UNKNOWN | Phân loại kết quả |
| **smtpStage** | CONNECT, RCPT, DATA, FINAL_REPLY | Phục vụ điều tra nếu instrumentation có dữ liệu |
| **smtpReplyCode** | 250, 451, 550 nếu đã nhận | Không suy diễn mã khi timeout |
| **providerRequestId** | ID do provider cấp | Tra cứu phía provider |
| **errorCategory** | READ_TIMEOUT, WRITE_TIMEOUT, AUTH, INVALID_RECIPIENT | Phân loại và giám sát |

Không phải Jakarta Mail cung cấp sẵn toàn bộ metadata như **smtpStage** hoặc providerRequestId trong mọi exception. Nếu ứng dụng không instrument được, hãy lưu **UNKNOWN** chứ không tự điền một giai đoạn lỗi không có bằng chứng.

### Phân biệt idempotency key và attempt ID

~~~text
notificationKey = shop-7:ORDER_CONFIRMED:ORD-1528:1:customer-392
notificationId  = 6b91... (ổn định)

attemptId #1   = c1f7... (mới cho lần thử thứ nhất)
attemptId #2   = d4a9... (mới cho lần thử thứ hai)
~~~

Notification key phải giữ nguyên khi retry. Attempt ID phải khác nhau để log không bị trộn. Nếu provider hỗ trợ idempotency key, thường phải gửi **notification key hoặc token ổn định**, không phải attempt ID thay đổi từng lần.

### Ghi attempt trước khi thực hiện I/O bên ngoài

Một nguyên tắc quan trọng:

1. **Claim** notification và tạo attempt record ở database.
2. **Commit** trạng thái IN_FLIGHT trước khi gọi SMTP.
3. Gửi email bên ngoài database transaction.
4. Lưu outcome vào một transaction mới/ngắn.

Nếu chỉ ghi attempt sau khi SMTP trả thành công, crash trong lúc gửi sẽ không để lại dấu vết nào cho lần thử chưa biết kết quả.

## 10. Claim job với nhiều worker: tránh gửi song song cùng notification

Trong môi trường nhiều instance Spring, hai worker có thể cùng tìm thấy notification PENDING. Nếu cả hai đều gửi, deduplication ở bước insert outbox không còn đủ.

### Vì sao đọc rồi cập nhật theo hai bước dễ race?

~~~text
Worker A                          Worker B
   |                                 |
SELECT PENDING                    SELECT PENDING
   |                                 |
   +-- thấy notification #42         +-- cũng thấy #42
   |                                 |
send email                        send email
~~~

Cần một thao tác **claim nguyên tử** trên storage dùng chung, ví dụ row lock, compare-and-set hoặc hệ thống queue hỗ trợ claim/visibility timeout.

### Ví dụ claim dùng PostgreSQL

Một câu lệnh minh họa:

~~~sql
WITH candidate AS (
    SELECT id
    FROM mail_outbox
    WHERE status IN ('PENDING', 'RETRYABLE_FAILED')
      AND (next_attempt_at IS NULL
           OR next_attempt_at <= CURRENT_TIMESTAMP)
    ORDER BY created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE mail_outbox AS m
SET status = 'IN_FLIGHT',
    lease_owner = :worker_id,
    lease_token = m.lease_token + 1,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    attempts = m.attempts + 1,
    updated_at = CURRENT_TIMESTAMP
FROM candidate
WHERE m.id = candidate.id
RETURNING
    m.id, m.notification_key, m.recipient_email,
    m.payload_json, m.attempts, m.lease_token;
~~~

Câu lệnh này:

- Chỉ chọn notification có thể retry và tới lịch.
- Bỏ qua row đang bị worker khác khóa.
- Cập nhật status và lease trong cùng một statement/transaction.
- Tăng **lease_token** để phân biệt các lần claim.
- Trả dữ liệu cần thiết cho worker.

Đây là ví dụ PostgreSQL, không phải SQL portable cho mọi hệ quản trị. Cần chạy trong một transaction ngắn và **commit transaction claim trước khi gọi SMTP**.

### Tại sao cần lease?

Nếu worker chết khi đang gửi, notification không nên mắc kẹt IN_FLIGHT mãi mãi. Trường **lease_until** giúp phát hiện job mà worker không còn gia hạn quyền sở hữu.

Nhưng **lease hết hạn không chứng minh email chưa được gửi**. Worker có thể đã gửi SMTP thành công rồi crash trước khi lưu outcome; hoặc vẫn đang chờ phản hồi mạng khi lease hết hạn.

Do đó, với job gửi SMTP:

~~~text
IN_FLIGHT + lease expired
          |
          v
        UNKNOWN
          |
          v
      Reconciliation
~~~

Không nên tự đổi tất cả lease-expired job về PENDING rồi retry ngay. Chính sách đó khôi phục throughput nhưng có nguy cơ gửi trùng chính tại tình huống khó nhất.

### Fencing token bảo vệ việc cập nhật trạng thái

Khi worker A đã mất lease và worker B claim lại, A có thể tỉnh dậy và cố ghi kết quả muộn. Để tránh stale worker ghi đè:

~~~sql
UPDATE mail_outbox
SET status = 'ACCEPTED',
    accepted_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :notification_id
  AND lease_owner = :worker_id
  AND lease_token = :lease_token
  AND status = 'IN_FLIGHT';
~~~

Nếu update ảnh hưởng 0 row, worker không còn là owner hiện tại và không được ghi đè kết quả của attempt khác.

**Fencing token chỉ bảo vệ trạng thái trong database**, không thể hủy một SMTP submission đã được gửi tới provider. Nếu worker A đã bắt đầu gửi khi lease hết hạn, worker B vẫn có thể gửi trùng nếu không có quy tắc xử lý UNKNOWN an toàn. Kết hợp lease/heartbeat, timeout hợp lý và không tự retry mù là cần thiết.

## 11. Ranh giới transaction của worker gửi mail

Không giữ một transaction database mở trong suốt quá trình chờ SMTP. Điều này kéo dài lock, giữ connection trong pool và làm tăng tranh chấp.

Luồng khuyến nghị:

~~~text
Worker
  |
  v
TX #1: claim PENDING -> IN_FLIGHT
  |
  v
COMMIT
  |
  v
Render MIME message từ payload đã lưu
  |
  v
JavaMailSender.send(...)
  |
  +-- success ----> TX #2: mark ACCEPTED
  |
  +-- proven failure ----> TX #2: mark RETRYABLE/PERMANENT
  |
  '-- uncertain ----> TX #2: mark UNKNOWN
~~~

### Các phương thức transaction riêng

Ví dụ tổ chức trách nhiệm:

~~~java
public interface MailJobStore {

    // Mỗi phương thức thực hiện trong transaction DB ngắn.
    Optional<ClaimedMailJob> claimNext(String workerId);

    boolean markAccepted(
            UUID jobId, String workerId, long leaseToken
    );

    boolean markUnknown(
            UUID jobId, String workerId,
            long leaseToken, String errorCode
    );

    boolean markRetryableFailure(
            UUID jobId, String workerId,
            long leaseToken, Instant nextAttemptAt
    );
}
~~~

Đây là interface do ứng dụng thiết kế. Việc implement có thể dùng JdbcTemplate, Spring Data JDBC/JPA với transaction riêng và compare-and-set update; không có interface MailJobStore sẵn trong Spring Framework Mail.

Worker chỉ thực hiện orchestration:

~~~java
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class MailOutboxWorker {

    private final MailJobStore jobStore;
    private final MailSubmitter submitter;

    public MailOutboxWorker(
            MailJobStore jobStore,
            MailSubmitter submitter
    ) {
        this.jobStore = jobStore;
        this.submitter = submitter;
    }

    public void runOne(String workerId) {
        Optional<ClaimedMailJob> found = jobStore.claimNext(workerId);
        if (found.isEmpty()) {
            return;
        }

        ClaimedMailJob job = found.get();
        try {
            submitter.submit(job);
            jobStore.markAccepted(
                    job.id(), workerId, job.leaseToken()
            );
        } catch (ProvenRetryableMailException ex) {
            jobStore.markRetryableFailure(
                    job.id(), workerId, job.leaseToken(),
                    backoffFor(job.attemptNumber())
            );
        } catch (Exception ex) {
            // Không có bằng chứng SMTP đã từ chối một cách dứt khoát.
            jobStore.markUnknown(
                    job.id(), workerId, job.leaseToken(),
                    classifyForAudit(ex)
            );
        }
    }
}
~~~

Các kiểu **ClaimedMailJob**, **MailSubmitter**, **ProvenRetryableMailException** và các hàm backoff/classify là thành phần minh họa, không phải API Spring có sẵn. Đặc biệt, chỉ ném **ProvenRetryableMailException** khi lớp gửi có bằng chứng đủ tin cậy rằng attempt trước không được chấp nhận. Không chuyển mọi **MailSendException** sang loại retryable.

**Một lỗi khác cần tính đến:** sau khi submitter.submit(job) thành công, tiến trình có thể chết trước khi markAccepted được commit. Trường hợp này vẫn cần đối soát; không có một transaction nguyên tử chung giữa SMTP server và database.

### Không nuốt lỗi khi việc ghi UNKNOWN cũng thất bại

Trong ví dụ, nếu database mất kết nối khi markUnknown, attempt có thể giữ IN_FLIGHT đến khi lease hết hạn. Một recovery process cần chuyển trường hợp lease expired sang UNKNOWN và ghi nhận metric/alert. Không nên coi việc xử lý exception là hoàn tất chỉ vì đã gọi hàm markUnknown.

## 12. Retry có kiểm soát thay vì lặp vô hạn

Retry hợp lý cho lỗi **đã biết chưa được provider chấp nhận** và có khả năng phục hồi:

- SMTP 4xx rõ ràng ở bước chưa hoàn tất submission.
- Kết nối chưa thiết lập hoặc lỗi trước khi truyền message, khi ứng dụng có bằng chứng tương ứng.
- Provider API trả lỗi retryable với semantics được công bố.
- Provider hỗ trợ idempotency và xác nhận an toàn khi lặp lại cùng key.

Retry nguy hiểm khi:

- Timeout sau khi gửi hết DATA.
- Mất kết nối lúc chờ 250 final.
- App crash sau server accept nhưng trước khi commit trạng thái.
- Lỗi được gộp chung thành một exception không cho biết server đã nhận chưa.

### Exponential backoff có jitter

Một chính sách retry thông thường:

~~~text
delay = min(maxDelay, baseDelay * 2^(attemptNumber - 1))
actualDelay = delay * randomFactor
~~~

Ví dụ với baseDelay 10 giây, maxDelay 10 phút, jitter trong khoảng 0,5 đến 1,5:

| Attempt | Delay cơ sở trước jitter |
| --- | --- |
| 1 | 10 giây |
| 2 | 20 giây |
| 3 | 40 giây |
| 4 | 80 giây |
| 5 | 160 giây |
| 6 | 320 giây |
| 7 trở đi | Tối đa 10 phút |

Jitter giúp nhiều worker không đồng loạt retry cùng một thời điểm sau sự cố mạng hoặc provider outage. Cần giới hạn số attempt, tổng thời gian retry và tốc độ gửi để tránh spam hoặc vượt rate limit.

**Backoff không giải quyết tính mơ hồ của timeout.** Chờ 10 phút trước khi gửi lại một message đã được chấp nhận vẫn có thể tạo bản trùng. Với UNKNOWN, quyết định retry phải dựa trên kết quả đối soát hoặc chính sách chấp nhận rủi ro.

### Dead-letter hoặc xử lý thủ công

Khi hết số lần retry hoặc quá thời hạn notification, nên:

- Chuyển sang PERMANENT_FAILED hoặc NEEDS_REVIEW theo thiết kế.
- Giữ nguyên lịch sử attempt.
- Tạo alert có mã notification/correlation ID.
- Cung cấp thao tác retry/resend có kiểm soát cho nhân viên vận hành.

Không xóa outbox row ngay khi hết retry nếu vẫn cần đối soát, điều tra hoặc tránh duplicate về sau.

## 13. Reconciliation: xác định kết quả của attempt UNKNOWN

**Reconciliation** là quy trình đối soát kết quả đã biết ở phía ứng dụng với dấu vết ở phía provider/SMTP server. Mục đích là chuyển trạng thái UNKNOWN sang một kết luận có bằng chứng.

~~~text
Outbox notification #42
     |
     v
Attempt #1 => UNKNOWN
     |
     v
Tra cứu provider / server logs / delivery events
     |
     +-- Có bằng chứng đã accepted
     |        |
     |        v
     |     ACCEPTED
     |
     +-- Có bằng chứng chưa accepted
     |        |
     |        v
     |     Có thể retry theo chính sách
     |
     '-- Chưa đủ bằng chứng
              |
              v
        Giữ UNKNOWN / đưa vào review
~~~

### Nguồn bằng chứng có thể sử dụng

| Nguồn | Điều có thể cung cấp | Giới hạn |
| --- | --- | --- |
| **Email provider API** | Tìm request theo key/correlation ID, xem trạng thái accepted | Chỉ dùng được nếu provider thực sự hỗ trợ tìm kiếm và có semantics rõ |
| **Provider webhook** | Event accepted/delivered/bounced kèm ID | Event có thể đến trễ, trùng hoặc khác thứ tự |
| **SMTP server logs** | Log submission, queue ID, recipient và message correlation | Không phải SMTP service nào cũng cho khách hàng truy cập |
| **Queue ID trong SMTP 250** | Dấu vết giao message vào queue server | Client không có ID nếu chính phản hồi 250 bị mất |
| **Header Message-ID/X-Correlation-ID** | Hỗ trợ tra message ở provider nếu hệ thống ghi lại | Không chứng minh bản mail đã được accept, không có dedup mặc định |
| **Recipient feedback** | Người nhận xác nhận đã nhận thư | Không tự động và không bảo đảm kiểm chứng được toàn bộ |

Một lần tra cứu provider trả về **“chưa thấy message”** chưa chắc là bằng chứng message không được chấp nhận. Hệ thống tìm kiếm có thể có độ trễ đồng bộ, giới hạn retention hoặc không index các attempt thất bại. Phải dựa vào hợp đồng cụ thể của provider để biết khi nào “không tìm thấy” đủ tin cậy.

### SMTP thuần có giới hạn quan trọng

SMTP là giao thức nộp và chuyển thư, không cung cấp một API tiêu chuẩn để client hỏi: **“Yêu cầu gửi có khóa K của tôi trước đó đã được nhận chưa?”**.

Nếu dùng JavaMailSender qua SMTP đơn thuần:

- Có thể lưu Message-ID và correlation header để hỗ trợ tìm log.
- Có thể dùng dịch vụ/provider cung cấp giao diện tra cứu message nếu có.
- Có thể theo dõi bounce hoặc delivery events nếu provider hỗ trợ.
- Nhưng không thể mặc định “đã đối soát xong” chỉ bằng cách hỏi SMTP một câu lệnh tiêu chuẩn.

Trong môi trường không có khả năng tra cứu provider, trạng thái UNKNOWN có thể cần xử lý bởi con người hoặc chính sách rủi ro của sản phẩm. Không nên viết một worker gọi lại JavaMailSender và đặt tên hành động đó là reconciliation; đó là **retry**, không phải đối soát.

### Dùng correlation ID riêng trong header

Ứng dụng có thể tạo một định danh bền vững khi ghi outbox:

~~~text
notificationId    = 6b91...
correlationId     = mail-job-6b91...
messageId         = <mail-job-6b91@mail.example.test>
~~~

Sau đó gắn header dùng để tra cứu:

~~~java
MimeMessage mimeMessage = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(mimeMessage, false, "UTF-8");

helper.setFrom("notifications@example.test");
helper.setTo(job.recipientEmail());
helper.setSubject(job.subject());
helper.setText(job.body());

mimeMessage.setHeader(
        "X-Notification-Correlation-ID",
        job.correlationId()
);

mailSender.send(mimeMessage);
~~~

Header tùy chỉnh này **không làm server tự deduplicate**, nhưng có thể giúp đối soát khi provider giữ lại header và cho phép tra cứu. Không đặt token xác thực, địa chỉ nội bộ nhạy cảm hoặc thông tin cá nhân không cần thiết vào correlation ID.

**Cần xác nhận hành vi provider**: một số hệ thống có thể lọc header tùy chỉnh hoặc chỉ lập chỉ mục những trường nhất định. Nếu provider có idempotency key chính thức trong API, hãy dùng đúng tham số API được tài liệu hóa thay vì hy vọng header tùy chỉnh được xử lý như cơ chế chống trùng.

### Webhook cũng cần idempotency

Provider có thể gửi cùng delivery event nhiều lần hoặc gửi các event không theo đúng thứ tự thời gian. Handler webhook nên:

- Xác thực webhook theo chữ ký/cơ chế provider.
- Lưu **providerEventId** với unique constraint để chống xử lý lặp.
- Ánh xạ event về notification ID/correlation ID.
- Áp dụng chuyển trạng thái hợp lệ, không ghi đè ACCEPTED/DELIVERED bằng một event cũ thiếu thông tin.
- Chấp nhận event đến chậm, và đối soát các trường hợp thiếu event.

Webhook **DELIVERED** là bằng chứng mạnh hơn **ACCEPTED** về quá trình chuyển phát, nhưng vẫn không chứng minh người nhận đã đọc email.

## 14. Provider API có idempotency khác SMTP như thế nào?

Một số dịch vụ gửi mail qua HTTP API có thể hỗ trợ cơ chế idempotent request. Khi đó, client gửi một khóa ổn định:

~~~text
POST /messages
Idempotency-Key: mail-job-6b91...

{
  "to": "customer@example.test",
  "template": "order-confirmed-v1",
  "data": {
    "orderNumber": "ORD-1528"
  }
}
~~~

Ví dụ trên là **giao diện giả định để giải thích nguyên tắc**, không phải endpoint hay khả năng chung của mọi provider. Nếu provider thực sự hỗ trợ:

1. Gửi lần đầu với key **K**.
2. Timeout, không biết response.
3. Gửi lại **cùng key K** và payload tương đương.
4. Provider đối chiếu key và không tạo thêm submission nếu yêu cầu đầu đã được xử lý, trong phạm vi bảo đảm/retention của họ.

Đây là một cách giảm ambiguity **ngay tại ranh giới provider**. Ngược lại, nếu provider chỉ chấp nhận header tùy ý nhưng không thực thi deduplication, hành vi không có gì khác SMTP retry thông thường về nguy cơ gửi trùng.

### Những điều cần xác minh trong tài liệu provider

- Provider có hỗ trợ idempotency cho **create/send email** hay chỉ cho API khác?
- Khóa được truyền bằng header hay field nào?
- Phạm vi khóa theo account, workspace, endpoint hay tenant?
- Khóa được lưu trong bao lâu?
- Nếu cùng key nhưng payload khác thì trả về gì?
- Khi request đầu vẫn đang xử lý, retry cùng key sẽ chờ, trả lỗi hay trả kết quả cũ?
- Sau khi hết thời gian lưu khóa, retry có thể tạo submission mới không?
- Webhook và API tra cứu có liên hệ được với cùng key không?

Không có câu trả lời chung cho mọi nhà cung cấp. Phải triển khai theo capability thực sự của provider đang sử dụng.

### Sự khác nhau giữa API idempotency và email threading

Hai email có cùng Message-ID có thể được client gom vào cùng một thread hoặc hiển thị theo cách khác nhau. Điều đó không phải bằng chứng provider đã loại bản gửi trùng. **Threading ở hộp thư** và **deduplication ở send API** là hai chức năng khác nhau.

## 15. Timeout và exception trong JavaMailSender

Spring Mail cung cấp **JavaMailSender** để nộp email qua hạ tầng Jakarta Mail; lỗi có thể được chuyển thành các loại **MailException** của Spring.

Một đoạn mã thường gặp:

~~~java
try {
    mailSender.send(mimeMessage);
    // Có bằng chứng lời gọi gửi đã hoàn tất không ném lỗi.
    jobStore.markAccepted(job.id(), owner, leaseToken);
} catch (MailException ex) {
    // Không tự suy luận rằng SMTP chưa nhận chỉ từ MailException.
    jobStore.markUnknown(
            job.id(), owner, leaseToken,
            ex.getClass().getSimpleName()
    );
}
~~~

Ví dụ trên minh họa **chính sách bảo thủ**: mọi lỗi không được phân loại bằng bằng chứng riêng đều chuyển UNKNOWN. Trong production, có thể phân biệt lỗi có chứng cứ retryable/permanent và không cần coi tất cả là ambiguous. Nhưng không nên viết:

~~~java
catch (MailException ex) {
    mailSender.send(mimeMessage); // retry ngay và vô điều kiện
}
~~~

vì lần trước có thể đã được server chấp nhận.

### Các cấu hình timeout

Với Spring Boot dùng JavaMailSender SMTP, cấu hình minh họa:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

Các giá trị timeout là mili giây, chỉ là ví dụ:

- **connectiontimeout**: giới hạn thời gian thiết lập kết nối socket.
- **timeout**: giới hạn thời gian chờ đọc từ socket.
- **writetimeout**: giới hạn thời gian ghi ra socket.

Timeout phù hợp giúp worker không kẹt vô hạn, nhưng **không làm trạng thái kết quả trở nên chắc chắn**. Một read timeout khi đợi phản hồi cuối vẫn có thể xảy ra sau khi SMTP server đã chấp nhận thư.

### Không phụ thuộc vào exception text để kết luận đã gửi hay chưa

Một thông điệp như:

~~~text
java.net.SocketTimeoutException: Read timed out
~~~

chỉ cho biết thao tác đọc không nhận dữ liệu đúng hạn. Nó không tự cho biết server đã lưu message vào queue hay chưa.

Để phân loại chặt chẽ, cần có bằng chứng từ giai đoạn SMTP được xác nhận hoặc thông tin provider. Nếu công cụ gửi chỉ báo exception ở mức chung, hãy giữ kết quả UNKNOWN cho tới khi đối soát.

### Địa chỉ người nhận và partial outcomes

Khi gửi một message cho nhiều recipients, SMTP có thể chấp nhận một số địa chỉ và từ chối một số địa chỉ khác theo các quy tắc của server và thư viện. Nếu JavaMailSender/Jakarta Mail báo partial send hoặc có thông tin địa chỉ thành công/thất bại, ứng dụng phải lưu outcome **theo người nhận** nếu muốn retry chính xác.

Một chiến lược đơn giản hơn cho email giao dịch là **mỗi notification logic gửi tới một recipient**, tránh phức tạp khi xác định ai đã nhận trong một attempt nhiều địa chỉ. Với thư có To/Cc/Bcc và yêu cầu recipient group thực sự, cần thiết kế idempotency và đối soát theo nhóm/recipient rõ ràng.

## 16. Không gắn @Retryable vô điều kiện lên phương thức gửi SMTP

Spring Retry có thể giúp lặp lại các thao tác thất bại, nhưng chỉ nên dùng khi thao tác **có thể lặp lại một cách an toàn** hoặc có chính sách phân loại rõ.

Một ví dụ nguy hiểm:

~~~java
@Retryable(maxAttempts = 3)
public void sendInvoiceEmail(MimeMessage message) {
    mailSender.send(message);
}
~~~

Nếu lần đầu đã được SMTP server chấp nhận nhưng JavaMailSender ném timeout do mất phản hồi cuối, interceptor có thể gọi lại phương thức lần hai, rồi lần ba. Người nhận có thể nhận nhiều bản.

**Có @Retryable không đồng nghĩa tác vụ gửi email trở thành idempotent.** Retry là cơ chế thực thi; idempotency là hợp đồng cần được thực thi ở ranh giới tạo hoặc gửi message.

### Vị trí phù hợp hơn của retry

Retry có thể áp dụng:

- Truy vấn database tạm thời thất bại **trước khi gửi**.
- Claim job bị lỗi tạm thời và chưa tạo external side effect.
- API provider có idempotency được bảo đảm với key giữ nguyên.
- Những lỗi SMTP được phân loại chắc chắn là chưa được server chấp nhận, nếu lớp transport cung cấp bằng chứng.

Với timeout không rõ kết quả, phải **ghi UNKNOWN và đối soát**; không đơn thuần gọi lại mailSender.send(...).

### Retry ở tầng event consumer cũng có thể tạo bản trùng

Giả sử message broker giao cùng một event ORDER_CONFIRMED hai lần. Nếu consumer phát mail trực tiếp mỗi lần:

~~~text
Event #42 -> Consumer -> send email
Event #42 -> Consumer -> send email
~~~

thì có thể gửi trùng dù SMTP không xảy ra timeout. Dùng notification key ổn định và database unique constraint giúp chỉ tạo một outbox row cho cùng event. Sau đó worker quản lý attempt và UNKNOWN riêng.

Không cần tắt retry toàn bộ hệ thống; cần **đặt retry ở nơi có thể xác định tính an toàn và kết quả**.

## 17. Quy tắc ra quyết định cho trạng thái UNKNOWN

Không có một chính sách retry UNKNOWN phù hợp mọi email. Quyết định phụ thuộc **chi phí gửi trùng** và **chi phí bỏ lỡ**.

| Loại email/tình huống | Rủi ro chính | Hướng xử lý UNKNOWN |
| --- | --- | --- |
| Email marketing/thông báo ít quan trọng | Gửi trùng gây phiền, giảm uy tín | Thường ưu tiên tránh duplicate, đối soát hoặc chấp nhận bỏ lỡ hiếm gặp |
| Xác nhận đơn hàng | Cả gửi trùng lẫn bỏ lỡ đều gây nhầm lẫn | Đối soát provider; hiển thị thông tin đơn hàng trong app để có nguồn xác thực |
| Hóa đơn hoặc biên nhận | Gửi trùng khiến người dùng nghi giao dịch trùng | Bảo đảm mã giao dịch/hóa đơn bất biến, đối soát, resend có kiểm soát |
| Email bảo mật/mã OTP | Gửi nhiều mã khác nhau làm người dùng bối rối | Không sinh token mới khi chỉ retry cùng notification; quản lý hết hạn và resend có chủ đích |
| Thông báo cần bảo đảm không mất | Bỏ lỡ nghiêm trọng | Dùng provider có idempotency và API đối soát, hoặc quy trình vận hành xác minh trước khi retry |

Một policy có thể được biểu diễn:

~~~text
UNKNOWN
   |
   v
Provider hỗ trợ tra cứu?
   |
   +-- Có --> Query by stable correlation/provider key
   |              |
   |              +--> Accepted => ACCEPTED
   |              |
   |              '--> Definitively not accepted => Retryable
   |
   '-- Không
          |
          v
     Provider hỗ trợ idempotent retry cùng key?
          |
          +-- Có --> Retry với đúng key và payload cũ
          |
          '-- Không
                  |
                  v
           Quyết định nghiệp vụ:
           HOLD / MANUAL_REVIEW / RISK_ACCEPTED_RETRY
~~~

### Nếu buộc phải retry UNKNOWN

Có hệ thống ưu tiên khả năng người nhận được thông báo hơn nguy cơ nhận trùng. Khi đó, việc retry UNKNOWN có thể là lựa chọn **có chủ đích**, nhưng cần:

- Ghi rõ trong thiết kế rằng có thể gửi trùng.
- Giới hạn attempts và tần suất.
- Giữ cùng notification key và nội dung logic.
- Không tạo thêm side effect nghiệp vụ (ví dụ không ghi giao dịch thanh toán lần nữa).
- Cung cấp mã giao dịch duy nhất trong email để người nhận hiểu đây cùng một sự kiện.
- Theo dõi tỷ lệ duplicate và phản hồi người dùng.

Không nên mô tả chính sách này là “ngăn gửi trùng hoàn toàn”.

### Giữ nội dung ổn định giữa các retry

Để đối soát và giảm nhầm lẫn, các lần retry cùng notification nên dựa trên cùng dữ liệu có ý nghĩa nghiệp vụ:

- Mã đơn và số hóa đơn không đổi.
- Recipient được xác định rõ.
- Template version hoặc message snapshot có thể tái tạo.
- Không tự sinh mới OTP hay link token mỗi khi retry, trừ khi đó là một quy trình resend nghiệp vụ mới.

Nếu token đã hết hạn, việc gửi lại message cũ có thể vô dụng. Hãy chuyển notification cũ sang trạng thái thích hợp và tạo một **resend event mới có chủ đích**, thay vì tự thay đổi payload dưới cùng một key rồi gọi đó là retry.

## 18. Thời hạn lưu idempotency key và trạng thái

Idempotency chỉ có tác dụng trong **khoảng thời gian hệ thống còn nhớ key**.

Ví dụ:

~~~text
Ngày 1: ORDER_CONFIRMED:ORD-1528:v1 được tạo và gửi
Ngày 2: duplicate event tới -> unique constraint chặn
Ngày 10: event tới lại sau khi bản ghi dedup bị xóa
       -> có nguy cơ tạo notification mới
~~~

Vì vậy, thời hạn giữ key cần bao phủ:

- Khoảng thời gian event upstream có thể replay.
- Thời gian retry/outbox giữ công việc.
- Thời gian các job UNKNOWN còn có thể cần đối soát.
- Khoảng thời gian cho phép resend và yêu cầu audit.
- Yêu cầu retention và xóa dữ liệu cá nhân.

Nếu cần xóa payload chứa PII, có thể cân nhắc lưu **tombstone idempotency record** với key hoặc digest không phục hồi thông tin nhạy cảm, trạng thái kết thúc và thời điểm hết hạn. Cần đánh giá rủi ro re-identification và chính sách dữ liệu của sản phẩm, không giữ dữ liệu vô thời hạn chỉ vì deduplication.

### TTL của provider cũng là một giới hạn

Giả sử provider HTTP API chỉ lưu idempotency key trong một thời hạn xác định. Retry cùng key **sau khi hết thời hạn** có thể tạo submission mới. Vì thế:

- Lưu thời điểm attempt đầu tiên.
- Biết thời hạn idempotency do provider công bố.
- Không tự coi “same key” là an toàn vô thời hạn.
- Sau TTL, chuyển sang đối soát hoặc review thay vì retry mù.

Thời hạn cụ thể tùy provider và phải được xác minh theo tài liệu đang áp dụng.

## 19. Observability: làm sao biết cơ chế chống trùng hoạt động?

Hệ thống cần theo dõi trạng thái **notification** và **attempt** tách biệt.

### Log có cấu trúc

Mỗi lần đổi trạng thái nên ghi metadata tối thiểu:

~~~text
event=mail_attempt_finished
notification_id=6b91...
attempt_id=c1f7...
event_type=ORDER_CONFIRMED
status=UNKNOWN
error_category=READ_TIMEOUT
provider=primary-smtp
duration_ms=10021
~~~

Tránh ghi raw email body, OTP, reset token, SMTP credentials hoặc danh sách người nhận đầy đủ vào log có quyền truy cập rộng. Correlation ID nên là opaque identifier, không phải dữ liệu cá nhân.

### Các metric hữu ích

| Metric | Ý nghĩa |
| --- | --- |
| **mail_outbox_pending_total** | Số notification đang chờ gửi |
| **mail_outbox_unknown_total** | Số notification chưa rõ kết quả |
| **mail_outbox_oldest_pending_age** | Thời gian chờ lớn nhất |
| **mail_unknown_oldest_age** | UNKNOWN bị treo lâu nhất |
| **mail_attempt_total{outcome}** | Số attempt theo ACCEPTED/FAILED/UNKNOWN |
| **mail_submit_duration_seconds** | Thời gian gọi transport |
| **mail_retry_total** | Số lần thử lại |
| **mail_dedup_conflict_total** | Số sự kiện trùng bị unique constraint chặn |
| **mail_lease_expired_total** | Số IN_FLIGHT quá hạn lease |
| **mail_provider_reconciliation_total{result}** | Kết quả đối soát provider |

Các tên trên là ví dụ tự định nghĩa cho hệ thống metrics, không phải metric Spring Mail có sẵn. Dùng labels có cardinality thấp; không đưa notification ID hay email address thành metric label.

### Cảnh báo quan trọng

Một số điều kiện có thể cần alert:

- UNKNOWN tăng đột biến sau khi provider chậm.
- UNKNOWN vượt quá ngưỡng thời gian được phép giữ.
- SMTP submission error rate tăng.
- Queue pending kéo dài và worker không xử lý.
- Lease expired thường xuyên, cho thấy worker bị chậm hoặc timeout/lease chưa phù hợp.
- Nhiều request cùng notification key nhưng payload không tương đương.
- Provider webhook không còn đến trong một khoảng thời gian bất thường.

Mục tiêu là biết được **notification nào đang chờ bằng chứng**, thay vì chỉ nhìn HTTP request hoặc log exception.

## 20. An toàn dữ liệu và bảo mật khi đối soát

Email thường chứa thông tin cá nhân và liên kết hành động. Cơ chế retry/idempotency cần bảo vệ dữ liệu giống các luồng nghiệp vụ khác.

### Không lưu bí mật trong key

Không tạo key từ OTP hoặc reset token dạng thô:

~~~text
KHÔNG NÊN:
RESET_PASSWORD:user-392:token-secret-abc123
~~~

Thay vào đó, dùng event ID ngẫu nhiên/opaque, user ID không nhạy cảm trong phạm vi lưu trữ bảo vệ, và loại notification:

~~~text
NÊN:
RESET_PASSWORD:reset-event-6b91...
~~~

Nếu key xuất hiện trong log, header hoặc metric, nó không được để lộ token sử dụng được.

### Không dùng metadata do client tự khai báo làm quyền gửi

API nhận yêu cầu gửi email có thể chấp nhận **Idempotency-Key** từ client, nhưng vẫn phải:

- Xác thực người gọi và kiểm tra quyền thực hiện nghiệp vụ.
- Scope key theo user/tenant/endpoint phù hợp.
- Kiểm tra payload trùng khớp khi reuse key.
- Giới hạn tốc độ để tránh spam.
- Không cho client dùng key của người khác để đọc trạng thái notification.

Idempotency không thay thế authentication, authorization và rate limiting.

### Bảo vệ outbox payload

Nếu outbox lưu địa chỉ email, nội dung hóa đơn hoặc liên kết xác nhận:

- Giới hạn quyền đọc/ghi bảng.
- Dùng mã hóa ở mức storage hoặc field khi cần.
- Không đưa secrets vào exception/log.
- Xóa hoặc rút gọn payload sau thời hạn lưu theo chính sách.
- Giữ audit đủ phục vụ đối soát mà không lưu nội dung nhạy cảm quá lâu.

Một worker không nên dùng thông tin sender hoặc recipient lấy từ payload chưa được xác thực để gửi thư tùy ý; service chuẩn bị notification cần áp chính sách nghiệp vụ trước khi ghi outbox.

## 21. Kiểm thử tình huống “server accepted, client timeout”

Để kiểm tra cơ chế chống gửi trùng, không đủ test trường hợp mailSender.send(...) trả thành công hoặc ném exception trước khi kết nối.

**Tình huống quan trọng nhất** phải mô phỏng được:

1. Provider đã ghi nhận/chấp nhận submission.
2. Client không nhận được bằng chứng thành công.
3. Ứng dụng ghi UNKNOWN.
4. Worker khởi động lại hoặc lịch retry chạy.
5. Cùng notification **không được gửi lại tự động** khi policy là hold-on-unknown.

### Một transport giả lập kết quả không rõ

Ví dụ Java dưới đây minh họa fault injection ở ranh giới provider:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public final class FakeAmbiguousMailTransport {

    private final AtomicInteger acceptedCount = new AtomicInteger();

    public void sendAndLoseAcknowledgement(String notificationId) {
        // Mô phỏng server đã chấp nhận submission.
        acceptedCount.incrementAndGet();

        // Client không nhận được kết quả thành công.
        throw new AmbiguousMailSubmissionException(
                "Server accepted but final acknowledgement was lost"
        );
    }

    public int acceptedCount() {
        return acceptedCount.get();
    }
}
~~~

~~~java
public class AmbiguousMailSubmissionException
        extends RuntimeException {

    public AmbiguousMailSubmissionException(String message) {
        super(message);
    }
}
~~~

Đây là **fake transport của test**, không phải JavaMailSender thật. Nó mô phỏng một thế giới có hiệu ứng bên ngoài thành công nhưng response phía ứng dụng thất bại. Test cần kiểm tra worker chuyển notification sang UNKNOWN và **không tự gọi lại transport** trong chính sách không retry UNKNOWN.

Kỳ vọng test:

~~~text
Accepted count sau attempt #1 = 1
Outbox status                = UNKNOWN
Job eligible for auto-retry  = false

Sau khi chạy lịch worker lần nữa:
Accepted count               = 1
Outbox status                = UNKNOWN
~~~

### Các kịch bản cần mô phỏng

| Kịch bản | Điều kiện mô phỏng | Kỳ vọng |
| --- | --- | --- |
| **Lỗi trước khi truyền message** | Không có bytes message tới server, có bằng chứng | Retry được theo chính sách |
| **Timeout sau DATA** | Server đã nhận, final ACK bị mất | UNKNOWN, không gửi lại mù |
| **SMTP 250 được nhận** | Client có success acknowledgement | ACCEPTED |
| **Crash trước markAccepted** | Server đã nhận; database vẫn IN_FLIGHT | Lease expired -> UNKNOWN |
| **Hai event trùng** | Cùng tenant + notification key | Một outbox row nhờ unique constraint |
| **Hai worker claim** | Cả hai đang polling | Một worker claim một row tại cùng thời điểm |
| **Lease hết hạn** | Worker chậm hoặc chết | Không tự coi là chưa gửi |
| **Stale worker cập nhật** | Lease token đã đổi | UPDATE bị từ chối, không ghi đè trạng thái mới |
| **Provider webhook lặp** | Cùng providerEventId hai lần | Xử lý một lần ở event store |
| **Provider webhook đến trễ** | ACCEPTED đã ghi, DELIVERED đến sau | Tiến trạng thái hợp lệ, không reset |
| **Key reused with different payload** | Cùng idempotency key, data khác | Báo conflict/điều tra |
| **Resend có chủ đích** | Người dùng yêu cầu gửi mới | Notification mới, liên kết với thông báo gốc |

### Đừng chỉ mock send() ném timeout ngay

Nếu test luôn mô phỏng:

~~~java
doThrow(new RuntimeException("timeout"))
        .when(mailSender).send(any(MimeMessage.class));
~~~

thì test chỉ xác nhận chương trình xử lý exception. Nó chưa chứng minh thiết kế an toàn trong tình huống **external side effect đã xảy ra**. Cần fake transport/state-machine test có thể ghi nhận provider đã accept trước khi client mất acknowledgement.

### Kiểm tra DB transaction và unique constraint thật

Unit test một phương thức **existsByKey(...)** không thay thế integration test ràng buộc UNIQUE. Nếu nhiều instance cùng nhận event, chỉ database transaction và unique constraint mới cung cấp hàng rào chống insert trùng dưới concurrency.

Integration test cần chạy trên database có semantics tương đương production, đặc biệt nếu dùng PostgreSQL **ON CONFLICT** và **FOR UPDATE SKIP LOCKED**. Không suy luận rằng một in-memory map hoặc H2 luôn mô phỏng đúng row locking của PostgreSQL.

### Kiểm tra worker crash và recovery

Một test có thể:

1. Claim notification thành IN_FLIGHT.
2. Không gọi markAccepted hoặc markUnknown (mô phỏng process chết).
3. Cho lease hết hạn trong fake clock hoặc test database.
4. Chạy recovery job.
5. Xác nhận job chuyển UNKNOWN.
6. Xác nhận SMTP transport không được gọi lại chỉ vì lease hết hạn.

Không cần dùng **Thread.sleep(...)** dài để chờ lease thật hết hạn. Có thể inject Clock hoặc tạo bản ghi có lease_until trong quá khứ để test nhanh và ổn định.

## 22. Recovery job xử lý IN_FLIGHT quá hạn

Một hệ thống production cần tìm những job đang IN_FLIGHT nhưng worker không còn phản hồi.

Ví dụ SQL:

~~~sql
UPDATE mail_outbox
SET status = 'UNKNOWN',
    lease_owner = NULL,
    lease_until = NULL,
    last_error_code = 'LEASE_EXPIRED',
    updated_at = CURRENT_TIMESTAMP
WHERE status = 'IN_FLIGHT'
  AND lease_until < CURRENT_TIMESTAMP
RETURNING id, notification_key;
~~~

Không cập nhật về PENDING ở đây. **LEASE_EXPIRED** chỉ cho biết worker đã mất quyền sở hữu theo thời gian lease, không cho biết SMTP server chưa nhận message.

### Recovery và worker đang còn sống

Một worker có thể bị block chờ mạng lâu hơn lease, hoặc bị pause do GC. Recovery job đánh dấu UNKNOWN trong khi worker vẫn đang cố gửi.

Để giảm tình huống này:

- Cấu hình SMTP timeouts hợp lý.
- Đặt lease phù hợp với worst-case task duration và cộng biên an toàn.
- Dùng heartbeat gia hạn lease nếu task được thiết kế cho công việc dài.
- Dùng lease token để ngăn worker cũ ghi đè kết quả database.
- Không cấp ngay một attempt gửi mới khi trạng thái vừa chuyển UNKNOWN.

Fencing/lease là cơ chế điều phối worker, **không phải khả năng ngắt một email đã được gửi đến SMTP server**. Worker cũ dù bị loại quyền ghi DB có thể vẫn hoàn tất một external send.

### Khi worker cũ báo success sau khi job đã UNKNOWN

Nếu worker có bằng chứng rõ ràng từ lần gửi trước và vẫn sở hữu attempt identity, hệ thống có thể ghi nhận một **late outcome** riêng để reconciliation xem xét. Không nên đơn giản cập nhật ACCEPTED nếu điều đó bỏ qua kiểm soát token hoặc xóa lịch sử attempt. Một reconciler có thể dùng bằng chứng đó để chuyển UNKNOWN -> ACCEPTED theo rule có kiểm soát.

## 23. Hai lớp idempotency trong toàn bộ luồng nghiệp vụ

Khi người dùng bấm “Đặt hàng”, timeout có thể xảy ra **ở nhiều ranh giới**, không chỉ lúc gửi SMTP.

### Timeout tại HTTP request tạo đơn hàng

~~~text
Browser                  Spring API                  Database
   |                         |                          |
   |--- POST /orders -------->|                          |
   |                         |--- INSERT order -------->|
   |                         |<---------- commit -------|
   |      X timeout          |                          |
   |                         |                          |
   |--- POST /orders retry -->|                         |
~~~

Nếu API không có idempotency, request retry có thể tạo **hai đơn hàng khác nhau**; mỗi đơn lại có email xác nhận riêng. Trong trường hợp này, outbox mail không thể biết hai đơn là trùng nghiệp vụ nếu chúng mang order ID khác nhau.

Do đó có hai lớp:

1. **Business command idempotency**: cùng thao tác tạo đơn hoặc thanh toán không tạo thêm một nghiệp vụ trùng khi client retry.
2. **Notification idempotency**: cùng event nghiệp vụ không tạo thêm công việc gửi email và không replay mù sau timeout SMTP.

Cả hai cần thiết nếu hệ thống muốn chống trùng end-to-end.

### Một khóa không nên dùng cho mọi endpoint

Idempotency key do client truyền cho POST /orders không nhất thiết là cùng định danh được dùng để gửi email:

~~~text
Business operation key:
  order-create-request-uuid

Email notification key:
  ORDER_CONFIRMED:ORD-1528:v1:recipient-392
~~~

Khóa nghiệp vụ bảo vệ việc tạo Order; khóa notification bảo vệ thông báo. Chúng có thể liên kết qua Order ID và event ID, nhưng nên có phạm vi và retention riêng.

### Không tạo thêm mã xác thực khi chỉ retry mail

Một ví dụ quan trọng:

~~~text
Lần gửi OTP #1 -> mã 123456 -> SMTP timeout UNKNOWN
Retry          -> sinh mã 654321 -> gửi lần nữa
~~~

Nếu người nhận nhận cả hai thư, họ có thể không biết mã nào hợp lệ. Retry cùng notification nên dùng **cùng mã/sự kiện đã phát sinh**, miễn còn hiệu lực và phù hợp chính sách bảo mật. Nếu mã cũ hết hạn hoặc cần thay mới, đó là một **yêu cầu tạo OTP mới**, cần tạo event mới và quản lý hiệu lực mã cũ rõ ràng.

Không dùng việc retry email để lặp lại side effect tạo token, trừ khi nghiệp vụ đã định nghĩa rõ ranh giới đó.

## 24. Runbook xử lý notification UNKNOWN

Một dashboard vận hành nên cho phép quan sát từng notification:

~~~text
Notification ID       6b91...
Business event        ORDER_CONFIRMED
Order ID              ORD-1528
Recipient             (đã che một phần)
Status                UNKNOWN
Attempt               #1
Error                 SMTP_READ_TIMEOUT
First attempted at    ...
Correlation ID        mail-job-6b91...
Provider evidence     NOT_YET_AVAILABLE
Action                RECONCILE / ESCALATE
~~~

Quy trình xử lý:

1. Xác định **notification key, event ID, recipient và thời điểm attempt**.
2. Kiểm tra log phía ứng dụng và xem lỗi xảy ra ở giai đoạn nào có bằng chứng.
3. Tra provider API, webhook hoặc SMTP logs bằng correlation ID/Message-ID nếu hỗ trợ.
4. Nếu có bằng chứng provider chấp nhận, chuyển **ACCEPTED**, không retry.
5. Nếu có bằng chứng provider chưa nhận, chuyển **RETRYABLE_FAILED/PENDING** theo chính sách.
6. Nếu vẫn không rõ, giữ **UNKNOWN**, cảnh báo nếu vượt ngưỡng thời gian.
7. Nếu nghiệp vụ buộc phải gửi lại, ghi rõ **quyết định chấp nhận rủi ro duplicate**, tạo attempt mới có audit trail.
8. Không xóa lịch sử attempt và không âm thầm đổi UNKNOWN thành PENDING.

### Hạn chế thao tác thủ công

Nút **Retry** trong trang quản trị không nên luôn bật cho UNKNOWN. Có thể yêu cầu:

- Quyền nhân viên phù hợp.
- Lý do retry/resend.
- Hiển thị cảnh báo “thư trước có thể đã được nhận”.
- Ghi audit actor, thời điểm và notification ID.
- Xác nhận có tạo một attempt cho notification cũ hay một resend notification mới.

Đặc biệt, không nên cho phép nhân viên dùng giao diện để thử lại cùng một payment/OTP event nhiều lần mà không thấy trạng thái và lịch sử.

## 25. Các lỗi thường gặp

### Lỗi 1 — Cứ gặp timeout là gửi lại ngay

Ứng dụng có thể gửi trùng nếu server đã nhận lần đầu nhưng phản hồi 250 bị mất.

**Cách xử lý:** phân biệt lỗi có bằng chứng chưa accepted và lỗi kết quả UNKNOWN; chỉ retry tự động khi có điều kiện an toàn hoặc chính sách rủi ro được chấp nhận.

### Lỗi 2 — Coi Message-ID là một khóa dedup SMTP

Header Message-ID hỗ trợ định danh/truy vết nhưng SMTP không bắt buộc server loại message có ID giống nhau.

**Cách xử lý:** dùng Message-ID để correlation, không lấy nó làm bằng chứng duy nhất của idempotency.

### Lỗi 3 — Tạo idempotency key mới cho mỗi lần retry

Mỗi attempt được coi là một notification mới nên không thể phát hiện trùng.

**Cách xử lý:** tạo notification ID/key một lần khi ghi outbox; chỉ attempt ID thay đổi.

### Lỗi 4 — Chống trùng bằng kiểm tra exists trong Java

Hai process có thể cùng thấy “chưa tồn tại” và tạo hai job.

**Cách xử lý:** enforce unique constraint ở database và dùng insert/upsert nguyên tử.

### Lỗi 5 — Outbox chỉ có PENDING/SENT/FAILED

Timeout bị ép thành FAILED rồi được scheduler retry, che đi khả năng message đã accepted.

**Cách xử lý:** có trạng thái UNKNOWN và quy trình reconciliation riêng.

### Lỗi 6 — Lease hết hạn thì chuyển ngay về PENDING

Worker có thể đã gửi SMTP thành công nhưng chưa lưu kết quả.

**Cách xử lý:** chuyển lease expired sang UNKNOWN khi không biết outcome, không auto replay.

### Lỗi 7 — Giữ transaction mở trong lúc gửi SMTP

Connection và row lock có thể bị giữ lâu khi mạng chậm, gây nghẽn database.

**Cách xử lý:** commit claim, thực hiện SMTP bên ngoài database transaction, rồi commit outcome trong một transaction ngắn.

### Lỗi 8 — Tưởng fencing token ngăn external duplicate

Fencing chỉ ngăn stale worker ghi trạng thái sai vào database; nó không chặn message đã phát tới SMTP.

**Cách xử lý:** kết hợp lease, timeout, UNKNOWN và provider idempotency/reconciliation.

### Lỗi 9 — Bật @Retryable cho toàn bộ JavaMailSender.send(...)

Interceptor có thể lặp lại một call mà hiệu ứng bên ngoài đã xảy ra.

**Cách xử lý:** giới hạn retry theo bằng chứng/loại lỗi và ranh giới idempotent.

### Lỗi 10 — Gửi qua @Async hoặc AFTER_COMMIT là đủ bền vững

Callback và executor trong bộ nhớ có thể mất khi process dừng. Ngoài ra, sau commit lỗi SMTP không thể rollback database.

**Cách xử lý:** dùng outbox/durable queue cho thông báo cần retry và phục hồi.

### Lỗi 11 — Tin rằng JavaMailSender trả thành công nghĩa là delivered

Transport có thể đã chấp nhận submission nhưng thư vẫn bounce hoặc bị chặn về sau.

**Cách xử lý:** phân biệt ACCEPTED với DELIVERED và theo dõi provider events nếu cần.

### Lỗi 12 — Provider trả “không thấy message” thì chắc chắn chưa gửi

Index và event pipeline có thể trễ; retention tìm kiếm có thể khác retention submission.

**Cách xử lý:** hiểu semantics tra cứu của provider; không coi sự vắng mặt tạm thời là bằng chứng tuyệt đối.

### Lỗi 13 — Một email nhiều recipients nhưng chỉ có một cờ sent

Có thể có outcome khác nhau theo từng recipient. Retry toàn bộ nhóm làm người đã nhận nhận trùng.

**Cách xử lý:** theo dõi trạng thái theo recipient hoặc chia thành notification riêng nếu nghiệp vụ cho phép.

### Lỗi 14 — Sinh token mới khi retry một email cũ

Người nhận có thể nhận nhiều email với mã khác nhau, không biết mã nào còn hiệu lực.

**Cách xử lý:** retry cùng logical notification dùng snapshot đã phát sinh; tạo token mới là một event mới có chủ đích.

### Lỗi 15 — Xóa key dedup quá sớm

Một event được replay sau thời gian retention có thể tạo mail job mới.

**Cách xử lý:** chọn retention theo cửa sổ replay, retry, đối soát và nghĩa vụ lưu/xóa dữ liệu.

### Lỗi 16 — Không xử lý duplicate từ webhook

Provider delivery event có thể được gửi lại nhiều lần; handler cập nhật trạng thái lặp hoặc tạo side effect phụ.

**Cách xử lý:** unique provider event ID, xác thực webhook và chuyển trạng thái idempotent.

## 26. Bài tập tình huống

### Tình huống A — Read timeout sau DATA

SMTP client đã truyền xong MIME body; ứng dụng bị read timeout khi chờ final response.

**Hỏi:** có nên gọi lại JavaMailSender ngay?

**Đáp:** không nếu chưa biết provider đã accepted hay chưa. Lưu UNKNOWN, đối soát bằng provider/logs nếu có. Nếu không thể đối soát, quyết định retry cần nêu rõ rủi ro gửi trùng.

### Tình huống B — Server trả 250, database update thất bại

JavaMailSender hoàn tất, nhưng thao tác chuyển outbox sang ACCEPTED bị lỗi do database timeout.

**Hỏi:** outbox còn IN_FLIGHT, worker mới có được gửi lại?

**Đáp:** không nên tự động gửi lại khi lease hết hạn. Có bằng chứng từ worker/provider nhưng trạng thái chưa được lưu; recovery chuyển UNKNOWN và reconciler dùng bằng chứng đó để quyết định ACCEPTED.

### Tình huống C — Hai instance cùng nhận OrderConfirmedEvent

Cả hai ứng dụng đều xử lý cùng event ID.

**Hỏi:** kiểm tra existsByKey rồi insert có đủ không?

**Đáp:** không, vì race condition. Dùng UNIQUE (tenant_id, notification_key) ở database và thao tác insert/upsert nguyên tử.

### Tình huống D — Hai worker claim một job

Worker A và B cùng poll bảng outbox.

**Hỏi:** cách nào ngăn cả hai gửi cùng job?

**Đáp:** atomic claim bằng row locking/compare-and-set hoặc queue semantics phù hợp. Không thực hiện SELECT rồi gửi trực tiếp khi chưa có claim.

### Tình huống E — Một worker bị kẹt quá thời gian lease

Job chuyển UNKNOWN nhưng worker cũ sau đó nhận được SMTP 250.

**Hỏi:** lease token giải quyết được gì?

**Đáp:** ngăn worker cũ ghi đè trạng thái database nếu đã mất quyền sở hữu. Nó không hủy email đã được SMTP nhận; outcome muộn cần được ghi nhận/đối soát theo thiết kế.

### Tình huống F — Cùng Message-ID trên hai SMTP submissions

Hai email có cùng header Message-ID nhưng server chấp nhận cả hai.

**Hỏi:** server có vi phạm SMTP không?

**Đáp:** không có quy tắc SMTP chung buộc server phải deduplicate theo Message-ID. Header chỉ là metadata định danh; muốn chống trùng ở provider phải có hợp đồng idempotency thực sự.

### Tình huống G — Provider có API idempotency

Request đầu timeout, provider đã chấp nhận thư. API công bố lưu idempotency key trong một khoảng thời gian xác định.

**Hỏi:** retry dùng key nào?

**Đáp:** dùng lại đúng **notification key ổn định** và payload tương đương, trong phạm vi semantics/TTL do provider công bố. Không dùng attempt ID mới làm idempotency key.

### Tình huống H — Không tìm thấy message ngay khi query provider

Sau read timeout, gọi API tìm kiếm trả “not found” trong vài giây đầu.

**Hỏi:** có thể kết luận chưa gửi không?

**Đáp:** không nếu provider có indexing delay hoặc trạng thái eventual consistency. Giữ UNKNOWN và đối soát lại theo SLA/semantics của provider.

### Tình huống I — Người dùng bấm nút Gửi lại hóa đơn

Hóa đơn đã gửi thành công ngày trước, người dùng chủ động yêu cầu gửi thêm một bản.

**Hỏi:** unique key cũ có nên chặn không?

**Đáp:** không nếu nghiệp vụ cho phép resend. Tạo một notification mới với resend event ID riêng, liên kết notification gốc và áp rate limit.

### Tình huống J — Nhiều người nhận, một người thất bại

Message gửi tới A và B; provider xác nhận A thành công nhưng B bị từ chối.

**Hỏi:** retry cả message có an toàn không?

**Đáp:** có thể gửi trùng cho A. Cần theo dõi outcome theo recipient và chỉ thử lại phần thật sự chưa accepted, hoặc thiết kế một notification cho mỗi recipient.

### Tình huống K — Mã OTP hết hạn khi outbox đang UNKNOWN

SMTP lần đầu không rõ kết quả; sau một thời gian, mã OTP đã hết hạn.

**Hỏi:** có nên retry nội dung OTP cũ?

**Đáp:** có thể không còn ý nghĩa. Hãy kết thúc notification cũ theo chính sách, rồi nếu người dùng yêu cầu, phát sinh sự kiện OTP mới với token mới và quản lý hiệu lực các token đúng nghiệp vụ.

### Tình huống L — API tạo đơn cũng bị timeout

Client retry POST /orders, tạo thêm một Order ID mới và một email xác nhận mới.

**Hỏi:** mail outbox unique key theo Order ID đã đủ chưa?

**Đáp:** chưa. Hai Order ID khác nhau sẽ tạo hai notification hợp lệ theo key. Cần thêm business command idempotency tại endpoint tạo đơn.

## 27. Thiết kế tham khảo: từ event nghiệp vụ tới email an toàn hơn

~~~text
                    API / Business Event
                             |
                             v
                 Validate business operation
                             |
                             v
                   BEGIN TRANSACTION
                             |
                 +-----------+-----------+
                 |                       |
                 v                       v
            Save business          Insert Outbox
            state once             UNIQUE logical key
                 |                       |
                 +-----------+-----------+
                             |
                             v
                           COMMIT
                             |
                             v
                    Outbox dispatcher
                             |
                             v
                   Atomic claim + lease
                             |
                             v
                   Durable attempt record
                             |
                             v
                         DB COMMIT
                             |
                             v
                    Submit email via SMTP
                             |
           +-----------------+-----------------+
           |                 |                 |
           v                 v                 v
      ACK accepted     Proven rejection     No reliable ACK
           |                 |                 |
           v                 v                 v
       ACCEPTED          RETRYABLE/          UNKNOWN
                         PERMANENT             |
                                              v
                                       Reconciliation
                                              |
                        +---------------------+------------------+
                        |                     |                  |
                        v                     v                  v
                   ACCEPTED            Safe to retry      Needs review
~~~

### Những bảo đảm thực tế của thiết kế

| Cơ chế | Điều được cải thiện | Giới hạn còn lại |
| --- | --- | --- |
| **Business idempotency** | Không tạo nghiệp vụ trùng khi client retry | Không xử lý SMTP duplicate trực tiếp |
| **Outbox + UNIQUE key** | Không tạo nhiều notification logic từ cùng event | Không ngăn duplicate external submission sau crash |
| **Atomic claim + lease** | Giảm worker gửi song song một job | Lease expiry không chứng minh outcome |
| **Attempt log** | Có lịch sử để điều tra và phục hồi | Log không phải bằng chứng server đã accept |
| **UNKNOWN state** | Không tự retry khi chưa biết kết quả | Có thể trì hoãn thông báo chưa được gửi |
| **Provider reconciliation** | Có thể xác định accepted/not accepted | Phụ thuộc API/logs và tính nhất quán provider |
| **Provider idempotency** | Có thể giảm duplicate ngay tại send boundary | Phụ thuộc capability, scope và TTL provider |
| **Backoff + retry limits** | Tránh quá tải khi lỗi tạm thời | Không biến ambiguous outcome thành safe retry |
| **Idempotent webhook** | Không xử lý delivery event lặp | Không chứng minh người nhận đã đọc |

### Quy tắc ghi nhớ

~~~text
Timeout != chưa gửi
Message-ID != SMTP idempotency guarantee
Outbox UNIQUE != exactly-once external send
Lease expired != chắc chắn chưa accepted
SMTP 250 != Inbox delivered
Retry != reconciliation

Một notification logic -> một key ổn định
Một lần thử gửi -> một attempt ID mới
Không rõ kết quả -> UNKNOWN
UNKNOWN -> đối soát hoặc chính sách rủi ro rõ ràng
~~~

**Ngăn gửi trùng sau timeout không rõ kết quả** không thể chỉ dựa vào một khối catch và vài lần gọi lại JavaMailSender. Cần thiết kế từ **ý nghĩa nghiệp vụ của notification**, ngăn tạo job trùng bằng unique key, ghi attempt trước external I/O, claim worker nguyên tử, có trạng thái UNKNOWN khi thiếu bằng chứng, và đối soát với provider trước khi retry nếu có thể. SMTP thuần không cung cấp cơ chế idempotency phổ quát; Message-ID không thay thế provider deduplication. Khi không thể xác định kết quả, hệ thống phải lựa chọn minh bạch giữa nguy cơ **gửi trùng** và **bỏ lỡ thông báo**. Đó là giới hạn cần được quản lý bằng chính sách, dữ liệu bền vững, observability và quy trình vận hành thay vì che giấu bằng retry tự động.
