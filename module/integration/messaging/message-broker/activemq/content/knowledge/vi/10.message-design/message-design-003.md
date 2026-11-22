# JMSMessageID, JMSCorrelationID, JMSReplyTo và định danh nghiệp vụ

> **Chương:** Thiết kế thông điệp  
> **Phạm vi:** Thiết kế danh tính, liên kết yêu cầu–phản hồi và chống xử lý trùng khi dùng Java/JMS với Apache ActiveMQ Classic hoặc ActiveMQ Artemis.

Trong ứng dụng bất đồng bộ, cùng một yêu cầu thanh toán có thể đi qua nhiều lần gửi, nhiều lần giao cho consumer và nhiều lần kết nối lại. Việc chọn sai ID sẽ tạo ra lỗi khó thấy: consumer coi một retry là lệnh thanh toán mới; requester không ghép được phản hồi đã đến; hoặc reply được gửi vào hàng đợi tạm đã biến mất.

Bài này phân biệt rõ **ID của message do JMS provider cấp**, **ID liên kết request và reply**, **destination trả lời**, và **ID của tác vụ nghiệp vụ**. Từng loại có vòng đời, phạm vi duy nhất và cách dùng khác nhau. Những khác biệt này quan trọng hơn cú pháp tạo UUID.

## 1. Bốn loại thông tin có vai trò khác nhau

| Thông tin | Ai gán? | Trả lời câu hỏi | Có thích hợp để chống trùng nghiệp vụ? |
|---|---|---|---|
| **JMSMessageID** | JMS provider khi gửi message | Đây là message nào trong lần gửi/đường đi của provider? | **Không** cho trường hợp producer gửi lại bằng một message mới |
| **JMSCorrelationID** | Thường do ứng dụng đặt | Message này thuộc request hay workflow nào? | Chỉ khi hợp đồng quy định nó cũng là ID của một thao tác logic |
| **JMSReplyTo** | Requester đặt một JMS Destination | Phải trả kết quả về đâu? | **Không**, đây là địa chỉ nhận |
| **commandId/eventId/paymentAttemptId** | Ứng dụng nghiệp vụ | Đây là tác vụ/sự kiện logic nào, dù được gửi bao nhiêu lần? | **Có**, nếu phạm vi và quy tắc phát sinh ID đúng |

Ba trường **JMSMessageID**, **JMSCorrelationID**, **JMSReplyTo** là **JMS header**. ID nghiệp vụ thường được đặt trong **body có schema** và có thể lặp thêm trong **JMS properties** khi consumer/selector/telemetry cần đọc. Không dùng một tên chung “messageId” để vừa chỉ ID của broker, vừa chỉ ID lệnh thanh toán.

### 1.1. Ví dụ cùng command gửi hai lần

~~~text
Yêu cầu logic: xử lý lần thanh toán pay-try-7f3 cho đơn OD-1042

Lần send A:
  JMSMessageID     ID:provider-001
  JMSCorrelationID req-8bd9
  commandId        cmd-4c91
  paymentAttemptId pay-try-7f3

Lần send B do producer timeout rồi retry:
  JMSMessageID     ID:provider-002
  JMSCorrelationID req-8bd9
  commandId        cmd-4c91
  paymentAttemptId pay-try-7f3
~~~

**JMSMessageID khác nhau không có nghĩa đây là hai khoản thanh toán hợp lệ.** Consumer phải dựa trên **commandId/paymentAttemptId** và trạng thái đã lưu để đảm bảo một hiệu ứng nghiệp vụ, kể cả khi broker nhìn thấy hai message.

## 2. JMSMessageID: ID của lần gửi do provider quản lý

JMS provider gán **JMSMessageID** trong quá trình producer gửi message, trừ trường hợp tính năng tạo ID bị vô hiệu hóa bằng tùy chọn được provider hỗ trợ. Giá trị thường là chuỗi bắt đầu bằng **ID:**. Đây là chuỗi mờ đối với ứng dụng: không phân tích nó để lấy timestamp, broker name hoặc thứ tự gửi.

~~~mermaid
sequenceDiagram
    participant P as Java Producer
    participant B as JMS Provider / Broker
    P->>P: createTextMessage(...)
    Note over P: Chưa có message ID của lần gửi này
    P->>B: send(destination, message)
    B->>B: Gán provider JMSMessageID
    B-->>P: Send hoàn tất
    P->>P: message.getJMSMessageID()
~~~

**Hệ quả:**

1. Đọc **getJMSMessageID() sau khi send**, không tạo business ID bằng giá trị chưa được provider cấp.
2. Nếu session transacted, **send hoàn tất chưa đồng nghĩa transaction đã commit**. Không coi một ID đã có là bằng chứng message đã được lưu bền vững và consumer đã nhận.
3. Một **send mới** có thể nhận **ID mới**, dù body và commandId giống hệt lần trước.
4. Broker **redelivery message đang giữ** thường giữ ID của message đó, nhưng điều này không giải quyết producer resend hoặc bridge tạo message mới.
5. Header có thể bị thay đổi qua bridge, chuyển đổi protocol hoặc provider khác; nếu cần danh tính xuyên ranh giới, gửi **ID nghiệp vụ ổn định**.
6. Không dùng JMSMessageID làm khóa sắp xếp thời gian. Nếu phải áp dụng sự kiện theo phiên bản, dùng **aggregateVersion/sequence** thuộc contract nghiệp vụ.

### 2.1. Gửi message và đọc ID sau send

Ví dụ JMS 2.x với Artemis client tương thích **javax.jms**:

~~~java
import javax.jms.ConnectionFactory;
import javax.jms.DeliveryMode;
import javax.jms.JMSContext;
import javax.jms.Queue;
import javax.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class ProviderMessageIdExample {
    public static void main(String[] args) throws Exception {
        ConnectionFactory factory = new ActiveMQConnectionFactory(
            System.getenv("MQ_URL"));

        try (JMSContext ctx = factory.createContext(
                 System.getenv("MQ_USER"),
                 System.getenv("MQ_PASSWORD"),
                 JMSContext.SESSION_TRANSACTED)) {

            Queue queue = ctx.createQueue("billing.payment.commands.v1");
            TextMessage message = ctx.createTextMessage(
                "{\"type\":\"ChargePayment\",\"orderId\":\"OD-1042\"}");

            message.setStringProperty("commandId", "cmd-4c91");

            ctx.createProducer()
                .setDeliveryMode(DeliveryMode.PERSISTENT)
                .send(queue, message);

            // Provider đã gán JMSMessageID của lần send này.
            System.out.println("Provider ID=" + message.getJMSMessageID());
            ctx.commit(); // Hoàn tất transaction JMS.
        }
    }
}
~~~

**Điều kiện thực hành:** broker Artemis có queue **billing.payment.commands.v1** (hoặc cấu hình auto-create hợp lệ), tài khoản có quyền send, thư viện **org.apache.activemq:artemis-jms-client** tương thích với phiên bản broker, Java và API **javax.jms**. Nếu dùng **jakarta.jms**, chọn client Jakarta phù hợp và thay toàn bộ import. **createQueue()** trong Java chỉ tạo handle Destination, không tự chứng minh queue vật lý đã tồn tại.

### 2.2. Khi ID không được tạo

JMS có tùy chọn như **JMSProducer.setDisableMessageID(true)** để yêu cầu provider tối ưu bằng cách không tạo ID. Provider có thể chấp nhận hoặc bỏ qua tùy chọn theo API và implementation.

Nếu ứng dụng chọn kiểu request–reply mà reply dùng **JMSMessageID của request** làm correlation key, phải bảo đảm tính năng ID được bật, giá trị thực sự có sau send và được bảo toàn trên đường kết nối cần thiết. **Không giả định ID luôn khác null trong mọi cấu hình tối ưu hoặc giao thức chuyển tiếp.**

### 2.3. Phân biệt redelivery với producer resend

| Tình huống | JMSMessageID | commandId/eventId |
|---|---|---|
| Consumer rollback và broker giao lại message đang giữ | Thường là ID của message cũ | Không đổi |
| Producer tạo một lần gửi mới sau timeout | Thường có ID mới | **Phải giữ nguyên** nếu đây vẫn là cùng tác vụ/sự kiện |
| Bridge tạo message mới ở provider khác | Có thể khác theo bridge/protocol | Phải được truyền rõ qua contract |
| Responder tạo reply message | Reply có ID riêng của nó | Có thể sao chép requestId và business ID liên quan |

**JMSRedelivered** và **JMSXDeliveryCount** chỉ là tín hiệu về delivery và phụ thuộc khả năng provider. Chúng không chứng minh hai message từ **hai send** có cùng một hiệu ứng nghiệp vụ.

## 3. JMSCorrelationID: liên kết request–reply và workflow

**JMSCorrelationID** là header mà ứng dụng có thể đặt để nối những message có quan hệ. Một use case điển hình: requester đặt ID trên request; responder sao chép ID tương ứng sang reply; requester nhận reply và đối chiếu ID.

~~~text
Request:
  JMSMessageID       ID:req-send-981
  JMSCorrelationID   req-8bd9
  JMSReplyTo         reply-queue

Reply:
  JMSMessageID       ID:reply-send-224
  JMSCorrelationID   req-8bd9
  JMSReplyTo         null
~~~

**JMSMessageID của reply không bằng JMSMessageID của request** là điều bình thường. Chúng là hai message độc lập. Requester ghép chúng qua **JMSCorrelationID theo hợp đồng**.

### 3.1. Hai quy ước correlation đều hợp lệ

**Quy ước A — requester tự tạo ID trước send:**

~~~text
requestId = UUID được tạo và lưu bởi ứng dụng
request.setJMSCorrelationID(requestId)
send(request)
reply.setJMSCorrelationID(request.getJMSCorrelationID())
requester tìm reply có JMSCorrelationID == requestId
~~~

Ưu điểm: biết ID **trước khi gửi**, dễ lưu trạng thái request/outbox và sử dụng lại khi retry. Đây thường là lựa chọn tốt cho tích hợp bất đồng bộ cần phục hồi qua restart.

**Quy ước B — reply liên kết bằng JMSMessageID của request:**

~~~text
send(request)
sentId = request.getJMSMessageID()
reply.setJMSCorrelationID(request.getJMSMessageID())
requester tìm reply có JMSCorrelationID == sentId
~~~

Quy ước B có trong các thiết kế JMS request–reply truyền thống. Nhược điểm: requester chỉ biết ID sau send và một lần send mới có thể có provider ID khác. Nó cũng phụ thuộc việc Message ID không bị vô hiệu hóa và được giữ nguyên qua các lớp trung gian.

**Phải thỏa thuận quy ước duy nhất cho mỗi integration.** Nếu requester dùng quy ước A còn responder dùng B, message vẫn có thể được gửi và nhận nhưng không khớp phiên chờ.

### 3.2. Khi nào nên dùng ID như thế nào?

- Với **requestId**, dùng chuỗi ASCII/UUID đủ duy nhất trong phạm vi các request đang theo dõi.
- Với **workflowCorrelationId**, giữ ổn định qua nhiều bước của cùng quy trình.
- Với **causationId**, lưu ID của message hoặc sự kiện logic đã tạo ra bước hiện tại.
- Với **commandId**, dùng khóa của một command nghiệp vụ cụ thể; cùng workflow có thể có nhiều command khác nhau.
- Với **eventId**, mỗi sự kiện logic có một ID ổn định ngay cả khi được phát lại.

JMSCorrelationID **không tự động trở thành khóa chống trùng**. Nếu một saga có ba command **reserve-stock**, **authorize-payment**, **ship-order**, cả ba có thể cùng workflowCorrelationId nhưng mỗi command vẫn phải được xử lý riêng.

### 3.3. Vấn đề định dạng

Dùng ID ứng dụng kiểu chuỗi, ví dụ UUID, giúp dễ trao đổi qua Classic, Artemis, API JSON và log. JMS cũng có API correlation ID dạng byte array trong những trường hợp nhất định; support và mapping có thể khác theo provider. Không dựa vào định dạng nhị phân nếu nhiều phía chưa thống nhất.

Không đưa mật khẩu, token, thông tin thẻ hay email khách hàng vào correlation ID. Header có thể bị ghi vào dashboard, metric, trace và DLQ.

## 4. JMSReplyTo: destination trả kết quả

**JMSReplyTo** chứa một đối tượng **Destination**: Queue, Topic hoặc TemporaryQueue/TemporaryTopic tùy kịch bản. Requester đặt nó trước send; responder đọc rồi **chủ động gửi** một reply. Broker không tạo reply thay ứng dụng.

~~~mermaid
sequenceDiagram
    participant R as Requester
    participant B as ActiveMQ
    participant S as Responder
    R->>B: Tạo reply destination / consumer
    R->>B: Send request (correlationId=req-8bd9, replyTo=Q)
    B->>S: Deliver request
    S->>S: Xử lý nghiệp vụ
    S->>B: Send reply to Q (correlationId=req-8bd9)
    S->>B: Ack/commit request
    B->>R: Deliver reply
    R->>R: Match correlationId
~~~

Không được đồng nhất **JMSReplyTo tồn tại** với việc một consumer đang online hoặc reply chắc chắn sẽ tới. Responder vẫn phải kiểm tra destination, quyền send, thời hạn reply và khả năng mất kết nối.

### 4.1. TemporaryQueue so với queue cố định

| Yêu cầu | **TemporaryQueue** | **Reply queue cố định** |
|---|---|---|
| Chờ phản hồi nhanh, requester đang online | Phù hợp | Phù hợp |
| Reply có thể tới sau khi requester restart | Không phù hợp | Có thể thiết kế để giữ lâu |
| Vòng đời | Phụ thuộc connection tạo đích | Được quản lý độc lập với connection |
| Gửi từ connection khác | Có thể nếu destination còn hiệu lực và ACL cho phép | Có |
| Nhận reply | Bị ràng buộc bởi connection tạo temporary destination | Theo quyền và mô hình consumer/subscription |
| Quản lý nhiều request | Có thể tách bằng đích tạm | Cần correlation selector hoặc dispatcher |
| Recovery và backlog | Không dùng cho kết quả quan trọng tới trễ | Cần policy durability, TTL, retention, owner |

Temporary destination thường có vòng đời gắn với **connection**; đóng connection sẽ chấm dứt khả năng dựa vào đích đó để nhận phản hồi. Trường hợp reply đến sau khi connection đã đóng cần được coi là **kết quả chưa rõ ở phía requester**, không mặc định nghiệp vụ thất bại.

### 4.2. Rủi ro bảo mật

Một producer có thể đặt **JMSReplyTo** tới destination không thuộc quyền nhận hợp lệ của nó. Responder không nên mù quáng gửi dữ liệu nhạy cảm tới bất kỳ địa chỉ nào mà request cung cấp. Cần:

- Quyền **send/consume** giới hạn cho từng ứng dụng hoặc tenant.
- Namespace reply được quản trị và kiểm tra theo hợp đồng.
- Xác thực chủ thể của request, kiểm tra bên nhận dự kiến.
- TTL hợp lý cho reply và giới hạn kích thước nội dung.
- Tránh lộ dữ liệu thanh toán/PII trong reply queue dùng chung.

Nếu replyTo thiếu, responder phải phân loại theo contract: request có thể là **one-way command** hợp lệ, hoặc là request–reply bị thiếu metadata và cần reject/quarantine. Không viết logic gửi reply khi chưa kiểm tra null.

## 5. Chọn ID nghiệp vụ theo phạm vi đúng

| ID nghiệp vụ | Ví dụ | Ý nghĩa | Sai lầm thường gặp |
|---|---|---|---|
| **orderId** | OD-1042 | Một đơn hàng | Dùng làm dedup key cho mọi lần thanh toán của đơn |
| **commandId** | cmd-4c91 | Một lệnh logic cụ thể | Sinh lại ID cho mỗi retry |
| **eventId** | evt-3b17 | Một sự kiện logic | Dùng JMSMessageID thay thế khi phát lại outbox |
| **paymentAttemptId** | pay-try-7f3 | Một lần thử thanh toán do nghiệp vụ định nghĩa | Tạo attempt mới khi mạng timeout nhưng chưa rõ kết quả |
| **requestId** | req-8bd9 | Một yêu cầu đang chờ reply | Dùng như định danh toàn bộ saga nhiều bước |
| **workflowCorrelationId** | checkout-7e82 | Một quy trình gồm nhiều command/event | Dedupe mọi message trong workflow như thể chúng trùng nhau |
| **causationId** | evt-previous-09 | Message/sự kiện gây ra bước tiếp theo | Đồng nhất với current eventId |
| **traceId** | ID trace OpenTelemetry | Kết nối các span/log | Xem như idempotency key |

Ví dụ một luồng checkout:

~~~text
workflowCorrelationId = checkout-7e82

  commandId = reserve-stock-a10       (Inventory Service)
  commandId = authorize-payment-b11   (Payment Service)
  commandId = create-shipment-c12     (Shipping Service)
~~~

Tất cả thuộc một workflow, nhưng là **ba tác vụ khác nhau**. Một ID duy nhất của saga không đủ để nhận biết nghiệp vụ đã xử lý bước nào.

### 5.1. Một hợp đồng message cụ thể

~~~json
{
  "schemaVersion": 1,
  "type": "ChargePayment",
  "commandId": "cmd-4c91",
  "orderId": "OD-1042",
  "paymentAttemptId": "pay-try-7f3",
  "amountMinor": 259000,
  "currency": "VND",
  "occurredAt": "2026-11-17T07:45:00Z",
  "workflowCorrelationId": "checkout-7e82",
  "causationId": "evt-order-confirmed-09"
}
~~~

Các property cần tra cứu/selector có thể được lặp lại:

~~~java
message.setStringProperty("commandId", "cmd-4c91");
message.setStringProperty("orderId", "OD-1042");
message.setStringProperty("workflowCorrelationId", "checkout-7e82");
message.setIntProperty("schemaVersion", 1);
message.setJMSCorrelationID("req-8bd9");
~~~

Không tự động đưa tất cả body vào message properties. Chỉ sao chép trường cần thiết và bảo đảm **property khớp body**; nếu commandId giữa property và body khác nhau, consumer phải coi đây là lỗi contract để xử lý có kiểm soát.

### 5.2. Quy tắc tạo ID trước khi publish

1. ID của tác vụ logic phải được tạo tại **ranh giới nhận yêu cầu** hoặc transaction nghiệp vụ ban đầu, trước khi outbox publisher bắt đầu retry.
2. Nếu publish thất bại mơ hồ, phát lại **cùng commandId/eventId**; không sinh ID mới theo mỗi lần gửi.
3. Nếu người dùng chủ động tạo một tác vụ mới theo quy tắc nghiệp vụ, có thể cần ID mới, dù orderId không đổi.
4. Khi gọi payment provider có hỗ trợ idempotency key, dùng khóa ổn định phù hợp của **paymentAttemptId** và không thay giữa các retry của cùng lần thử.
5. Với bridge hoặc đổi wire protocol, truyền ID nghiệp vụ như dữ liệu contract; đừng dựa riêng vào JMSMessageID.

## 6. Lab request–reply Java/JMS với Artemis

Lab sử dụng **JMS 2.x**, namespace **javax.jms** và **org.apache.activemq:artemis-jms-client** tương thích. Nếu dự án dùng **jakarta.jms**, thay toàn bộ API import và client Jakarta theo phiên bản đang dùng.

**Chuẩn bị:** broker Artemis đang chạy; queue ANYCAST **billing.payment.commands.v1** đã được provision hoặc được phép auto-create; ứng dụng có quyền gửi/nhận queue và tạo temporary reply destination; đặt **MQ_URL**, **MQ_USER**, **MQ_PASSWORD**. URI ví dụ **tcp://localhost:61616** chỉ có hiệu lực khi acceptor tương ứng đang hoạt động.

Hợp đồng của lab:

- Requester tạo **requestId** trước send rồi đặt **JMSCorrelationID=requestId**, **commandId=requestId** để đơn giản hóa ví dụ.
- Requester tạo **TemporaryQueue** và đặt vào **JMSReplyTo**.
- Responder đọc JMSReplyTo, sao chép **JMSCorrelationID** sang reply, gửi reply và commit JMS.
- Requester chỉ chấp nhận reply có correlation ID khớp. **Không có cổng thanh toán hoặc database thật trong lab.**

### 6.1. Requester

~~~java
import java.util.UUID;
import javax.jms.ConnectionFactory;
import javax.jms.DeliveryMode;
import javax.jms.JMSConsumer;
import javax.jms.JMSContext;
import javax.jms.Message;
import javax.jms.Queue;
import javax.jms.TemporaryQueue;
import javax.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class PaymentRequester {
    public static void main(String[] args) throws Exception {
        String url = required("MQ_URL");
        String user = required("MQ_USER");
        String password = required("MQ_PASSWORD");

        ConnectionFactory factory = new ActiveMQConnectionFactory(url);
        String requestId = UUID.randomUUID().toString();

        try (JMSContext ctx = factory.createContext(
                 user, password, JMSContext.AUTO_ACKNOWLEDGE)) {
            Queue commands = ctx.createQueue("billing.payment.commands.v1");
            TemporaryQueue replyQueue = ctx.createTemporaryQueue();
            JMSConsumer replies = ctx.createConsumer(replyQueue);
            try {
                ctx.start();
                TextMessage request = ctx.createTextMessage(
                    "{\"type\":\"ChargePayment\","
                    + "\"orderId\":\"OD-1042\","
                    + "\"amountMinor\":259000,"
                    + "\"currency\":\"VND\"}");

                request.setJMSCorrelationID(requestId);
                request.setStringProperty("commandId", requestId);
                request.setJMSReplyTo(replyQueue);

                ctx.createProducer()
                   .setDeliveryMode(DeliveryMode.PERSISTENT)
                   .send(commands, request);

                // ID provider chỉ đọc sau send.
                System.out.println("requestId=" + requestId);
                System.out.println("JMSMessageID="
                    + request.getJMSMessageID());

                Message reply = replies.receive(15000);
                if (reply == null) {
                    System.out.println(
                        "Reply timeout; outcome UNKNOWN. requestId="
                        + requestId);
                    return;
                }
                if (!requestId.equals(reply.getJMSCorrelationID())) {
                    throw new IllegalStateException(
                        "Reply has wrong correlation ID");
                }
                if (!(reply instanceof TextMessage)) {
                    throw new IllegalStateException(
                        "Unexpected reply type");
                }

                System.out.println("Reply payload="
                    + ((TextMessage) reply).getText());
                System.out.println("Reply JMSMessageID="
                    + reply.getJMSMessageID());
            } finally {
                replies.close();
                replyQueue.delete();
            }
        }
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException("Missing env: " + key);
        }
        return value;
    }
}
~~~

Mã minh họa quy tắc A: **requestId của ứng dụng được biết trước send**, reply phải giữ correlation đó. TemporaryQueue sẽ hết vòng đời khi connection đóng; **delete()** trong finally chỉ thu hồi đích tạm, không liên quan việc xóa queue thanh toán.

**Khi timeout, requester không biết chắc nghiệp vụ đã hoàn tất hay chưa.** Demo chỉ in thông báo; production phải lưu requestId/commandId bền vững trước khi gửi, có API hoặc query để tra cứu kết quả, và không tự tạo một paymentAttemptId mới vì chưa thấy reply.

### 6.2. Responder

~~~java
import javax.jms.ConnectionFactory;
import javax.jms.DeliveryMode;
import javax.jms.Destination;
import javax.jms.JMSConsumer;
import javax.jms.JMSContext;
import javax.jms.Message;
import javax.jms.Queue;
import javax.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class PaymentResponder {
    public static void main(String[] args) throws Exception {
        String url = required("MQ_URL");
        String user = required("MQ_USER");
        String password = required("MQ_PASSWORD");
        ConnectionFactory factory = new ActiveMQConnectionFactory(url);

        try (JMSContext ctx = factory.createContext(
                 user, password, JMSContext.SESSION_TRANSACTED)) {
            Queue commands = ctx.createQueue("billing.payment.commands.v1");
            JMSConsumer requests = ctx.createConsumer(commands);
            try {
                ctx.start();
                Message request = requests.receive(10000);
                if (request == null) {
                    System.out.println("No request");
                    return;
                }

                try {
                    Destination replyTo = request.getJMSReplyTo();
                    String requestId = request.getJMSCorrelationID();
                    String commandId =
                        request.getStringProperty("commandId");

                    if (replyTo == null || requestId == null
                            || !requestId.equals(commandId)) {
                        throw new IllegalArgumentException(
                            "Invalid reply metadata");
                    }
                    if (!(request instanceof TextMessage)) {
                        throw new IllegalArgumentException(
                            "Unexpected request message type");
                    }

                    // LAB ONLY: giả lập kết quả, không có DB/payment API.
                    TextMessage reply = ctx.createTextMessage(
                        "{\"status\":\"ACCEPTED\","
                        + "\"orderId\":\"OD-1042\"}");

                    reply.setJMSCorrelationID(requestId);
                    reply.setStringProperty("commandId", commandId);

                    ctx.createProducer()
                       .setDeliveryMode(DeliveryMode.NON_PERSISTENT)
                       .setTimeToLive(15000)
                       .send(replyTo, reply);

                    // Receive request và send reply thuộc transaction JMS.
                    ctx.commit();
                    System.out.println("requestId=" + requestId);
                    System.out.println("Request JMSMessageID="
                        + request.getJMSMessageID());
                    System.out.println("Reply JMSMessageID="
                        + reply.getJMSMessageID());
                } catch (Exception error) {
                    ctx.rollback(); // Request có thể được giao lại.
                    throw error;
                }
            } finally {
                requests.close();
            }
        }
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException("Missing env: " + key);
        }
        return value;
    }
}
~~~

**Đọc ví dụ đúng giới hạn:** responder dùng một **JMSContext transacted** để nhận request và gửi reply trong cùng transaction messaging. **Transaction JMS không bao trùm PostgreSQL hoặc một API thanh toán bên ngoài**. Nếu responder cập nhật database, cần cơ chế chống trùng nghiệp vụ và phối hợp transaction phù hợp. Reply **NON_PERSISTENT** chỉ phù hợp với destination tạm và lab ngắn hạn; reply cần tồn tại qua restart phải dùng queue/retention và delivery mode thích hợp.

### 6.3. Chạy và kiểm tra

Chạy **PaymentResponder** trước, rồi **PaymentRequester** trước khi responder hết thời gian chờ 10 giây. Requester chờ reply tối đa 15 giây.

~~~text
Kết quả kỳ vọng:
  Request JMSMessageID = ID:...          (provider cấp)
  Reply JMSMessageID   = ID:...          (một message khác)
  Request JMSCorrelationID = requestId
  Reply JMSCorrelationID   = requestId
  Requester nhận {"status":"ACCEPTED", ...}
~~~

Test lỗi:

1. Chạy requester khi responder chưa chạy; sau timeout, temporary reply queue có thể bị thu hồi khi requester đóng connection.
2. Chạy responder sau đó; việc gửi tới replyTo đã hết hiệu lực có thể thất bại và transaction JMS rollback. Cần chính sách retry/DLQ hoặc quản lý response timeout, tránh retry vĩnh viễn vào đích không còn.
3. Dùng **reply queue cố định** để thử phản hồi tới muộn hoặc cần lưu qua reconnect; bảo đảm có ACL, TTL, persistence và consumer phù hợp.
4. Gửi hai request khác nhau, cho responder trả reply ngược thứ tự; ghép bằng correlation ID, không dựa vào thứ tự nhận.
5. Thử hai lần send cùng commandId; quan sát ID provider khác nhưng ứng dụng phải chống trùng bằng commandId.

## 7. Reply queue chung: selector hoặc dispatcher

Nếu dùng **reply queue cố định** cho nhiều request đồng thời, cần cơ chế phân phối kết quả theo correlation ID.

### 7.1. JMS message selector

JMS cho phép lọc bằng **JMSCorrelationID**:

~~~java
String requestId = "req-8bd9";
// Ví dụ chỉ dùng ID do ứng dụng tạo theo định dạng an toàn.
String selector = "JMSCorrelationID = '" + requestId + "'";
JMSConsumer consumer = context.createConsumer(replyQueue, selector);
~~~

Selector chỉ đọc header/property hỗ trợ, **không parse JSON body**. Không nối chuỗi input chưa được kiểm tra vào selector vì dấu nháy hoặc ký tự đặc biệt có thể tạo lỗi cú pháp hoặc làm thay đổi điều kiện. Có thể dùng UUID do ứng dụng sinh, giới hạn định dạng, hoặc escape đúng theo cú pháp selector.

**Chi phí:** hàng nghìn request đồng thời có thể dẫn tới hàng nghìn consumer/selector ngắn hạn. Cần đo CPU, metadata, broker dispatch và cleanup trước khi chọn kiểu này.

### 7.2. Một reply dispatcher dùng correlation map

~~~mermaid
flowchart LR
    Q["Reply queue cố định"] --> C["Reply Dispatcher"]
    C --> M["requestId → waiter / result"]
    M --> R1["Request A"]
    M --> R2["Request B"]
~~~

Một consumer đọc reply, so khớp **JMSCorrelationID**, rồi cập nhật promise/future hoặc database.

- **Map trong RAM** mất khi process crash; chỉ phù hợp khi chấp nhận mất waiter và có cơ chế tra cứu kết quả khác.
- **Shared database result store** giúp nhiều replica đọc kết quả và khôi phục request state, nhưng phải ghi result rồi mới ack reply.
- Reply **đến trễ** vẫn có thể cập nhật trạng thái dù HTTP request ban đầu đã timeout.
- Reply **gửi trùng** phải idempotent theo requestId và reply result version.
- Nếu nhiều dispatcher cùng đọc một queue, reply có thể tới một replica khác requester ban đầu; hệ thống cần shared state hoặc cơ chế routing rõ ràng.

**JMSReplyTo** chỉ cung cấp đích trả lời. Khả năng ghép reply với đúng waiter là trách nhiệm của ứng dụng.

## 8. Ba cửa sổ lỗi và chiến lược nhận diện

### 8.1. Producer đã gửi nhưng phản hồi commit bị mất

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as Broker
    participant C as Consumer
    P->>B: send(commandId=cmd-4c91)
    B->>B: Lưu message A
    Note over P,B: Network timeout trước phản hồi
    P->>B: resend(commandId=cmd-4c91)
    B->>B: Lưu message B
    B->>C: Deliver A, B
    C->>C: Dedupe theo cmd-4c91
~~~

Hai message có thể có **JMSMessageID khác nhau**; producer phải giữ **commandId** ổn định qua resend. Khi có transactional outbox, tạo ID trước khi ghi outbox và publisher dùng lại ID từ bản ghi đó.

### 8.2. Consumer commit database nhưng chưa ack JMS

~~~text
1. Nhận commandId=cmd-4c91
2. Database commit kết quả nghiệp vụ thành công
3. Process crash trước JMS ack/commit
4. Broker redeliver message
5. Consumer tra cmd-4c91: đã xử lý → không thực hiện side effect
6. Ack/commit JMS, hoàn tất delivery
~~~

Dùng ID nghiệp vụ vừa giải quyết **producer resend** vừa giải quyết **consumer redelivery**. **JMSRedelivered** có thể giúp debug, nhưng không thay thế idempotency.

### 8.3. Requester timeout nhưng payment đã hoàn tất

~~~text
Requester send req-8bd9, JMSReplyTo = TemporaryQueue
Responder hoàn thành payment nhưng reply bị trễ
Requester hết thời gian chờ, đóng connection
TemporaryQueue không còn hợp lệ
Requester không nhận reply dù payment đã thành công
~~~

Không xem **timeout = thất bại**. Hãy tra trạng thái dựa trên **paymentAttemptId/commandId** và có phương án **RECONCILING** khi chưa xác định được kết quả. Nếu bên thanh toán ngoài cung cấp idempotency key, giữ nguyên khóa qua retry để không thu tiền hai lần.

## 9. Idempotency bằng inbox: không dùng JMSMessageID làm khóa

Một bảng chống trùng theo ID nghiệp vụ có thể dùng PostgreSQL:

~~~sql
CREATE TABLE processed_commands (
    consumer_name TEXT NOT NULL,
    command_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    result_json JSONB,
    PRIMARY KEY (consumer_name, command_id)
);
~~~

Flow nghiệp vụ:

~~~text
BEGIN DATABASE TRANSACTION
  INSERT INTO processed_commands(consumer_name, command_id)
  VALUES ('payment-worker', commandId)
  ON CONFLICT DO NOTHING
  RETURNING command_id

  Nếu chèn thành công:
      thực hiện cập nhật nghiệp vụ / ghi kết quả
  Nếu commandId đã có:
      lấy kết quả xử lý trước đó
COMMIT DATABASE TRANSACTION

ACK / COMMIT JMS RECEIVE
~~~

Mọi cập nhật **processed_commands** và thay đổi nghiệp vụ trong database phải thuộc **cùng transaction**; nếu nghiệp vụ rollback, marker chống trùng cũng phải rollback. Unique constraint giúp xử lý hai message trùng đến đồng thời; ứng dụng phải quản lý tình huống transaction thứ nhất còn chạy hoặc kết quả chưa sẵn sàng.

**Nếu consumer gọi API ngoài database**, transaction SQL không bao trùm side effect đó. Dùng idempotency key của API downstream khi hỗ trợ, lưu kết quả và đối soát trạng thái không rõ. Với payment, không gọi charge lần nữa bằng attempt ID mới chỉ vì mất JMS ack.

### 9.1. Chọn phạm vi unique key

~~~text
(consumer_name, commandId)
(tenant_id, paymentAttemptId)
(consumer_group, eventId)
~~~

Phạm vi phải xuất phát từ logic nghiệp vụ. **UNIQUE(orderId)** quá thô nếu một đơn có nhiều lần thanh toán hợp lệ. **UNIQUE(JMSMessageID)** quá hẹp nếu producer có thể phát lại cùng command bằng message mới. Dùng **workflowCorrelationId** để dedup toàn bộ saga cũng sai vì một workflow có nhiều bước độc lập.

## 10. Log và tracing theo đúng loại ID

Để chẩn đoán message trùng hoặc reply mất, log nên có cả ID provider và business ID:

~~~json
{
  "event": "payment-command-consumed",
  "jmsMessageId": "ID:provider-001",
  "jmsCorrelationId": "req-8bd9",
  "commandId": "cmd-4c91",
  "paymentAttemptId": "pay-try-7f3",
  "orderId": "OD-1042",
  "workflowCorrelationId": "checkout-7e82",
  "consumer": "payment-worker",
  "redelivered": true,
  "deliveryCount": 2,
  "result": "already-processed"
}
~~~

Ví dụ chỉ minh họa cấu trúc log. Các provider có thể cung cấp **JMSXDeliveryCount** và **JMSRedelivered** theo hành vi delivery tương ứng; đừng coi một count cụ thể là định nghĩa chuẩn của tất cả hình thức retry.

Các khóa truy vấn có ý nghĩa khác nhau:

| Khóa truy vấn | Dùng để |
|---|---|
| **JMSMessageID** | Theo dõi một message tại broker, DLQ và lần giao cụ thể |
| **commandId/eventId** | Gom tất cả lần gửi/giao của cùng một thao tác hoặc sự kiện logic |
| **JMSCorrelationID/requestId** | Ghép request, reply và tìm nguyên nhân timeout |
| **workflowCorrelationId** | Xem hành trình nhiều bước |
| **traceId/spanId** | Điều tra span và log trong hệ quan sát, không dùng dedup |

Với OpenTelemetry, có thể truyền **traceparent** qua message property theo chuẩn instrumentation phù hợp. **JMSCorrelationID không tự động là traceparent**, và một workflow có thể trải qua nhiều trace. Không lưu dữ liệu cá nhân, mật khẩu hoặc token trong các ID chỉ để tiện tìm log.

## 11. ActiveMQ Classic, Artemis và chuyển đổi protocol

JMS định nghĩa ý nghĩa chung của các header, nhưng khi chạy Classic/Artemis hoặc đi qua bridge, phải thử sự tương thích thực tế.

| Trường hợp | Điểm cần kiểm chứng |
|---|---|
| **Classic + OpenWire JMS client** | Header request/reply, quyền tạo TemporaryQueue, mapping queue/topic và phiên bản client |
| **Artemis + Core JMS client** | Address/queue routing type, temporary destination, quyền send/consume và transaction |
| **AMQP/STOMP/bridge** | Mapping correlation ID, reply-to, message ID và các properties được giữ hay chuyển đổi |
| **Forward nhiều broker** | Temporary reply destination có route được tới requester không, ID provider có bị thay không |
| **Reply queue cố định** | ACL, persistence, retention, selector/dispatcher và quyền giữa nhiều replica |
| **Failover/reconnect** | Requester phục hồi correlation state thế nào, reply queue tạm cũ có còn hiệu lực không |
| **javax.jms / jakarta.jms** | Dependency đúng phiên bản; không trộn hai namespace |

**JMSReplyTo là đối tượng Destination** theo client/provider tương ứng. Đừng giả định có thể chuyển nguyên một Destination tạo bởi Classic sang Artemis qua bridge, hoặc từ Core sang STOMP mà vẫn giữ ý nghĩa định tuyến. Với tích hợp liên protocol, nên dùng **business ID và correlation key dạng chuỗi** trong contract, đồng thời thiết kế reply routing rõ ràng cho topology.

## 12. Lỗi thiết kế thường gặp

| Sai sót | Hệ quả | Cách xử lý |
|---|---|---|
| Dedupe bằng JMSMessageID | Producer resend có ID mới nên xử lý trùng | Dùng commandId/eventId ổn định |
| Mỗi retry tạo commandId mới | Mất khả năng nhận diện cùng thao tác | Sinh và lưu ID tại ranh giới nghiệp vụ |
| Requester dùng app requestId, responder dùng provider message ID | Reply đến nhưng không match waiter | Thống nhất quy ước correlation |
| Lấy JMSMessageID trước send | Không có ID của lần gửi hiện tại | Lấy sau send; hoặc dùng requestId ứng dụng |
| Reply gửi vào JMSReplyTo không kiểm tra | Có thể gửi sai đích hoặc đích không còn tồn tại | Validate contract, ACL, expiry, error policy |
| Dùng TemporaryQueue cho kết quả tới sau nhiều giờ | Reply mất khi requester connection kết thúc | Reply queue bền vững và lưu trạng thái |
| Timeout thì coi payment thất bại | Có thể thanh toán hai lần | Query/reconcile bằng attempt ID cũ |
| Lấy workflowCorrelationId làm dedup key cho tất cả message | Bỏ nhầm các bước khác trong cùng saga | Dedupe theo commandId của từng bước |
| ACK JMS trước khi nghiệp vụ bền vững | Crash mất hiệu ứng hoặc kết quả | Commit nghiệp vụ trước ACK, idempotency |
| Tưởng JMS transaction bao trùm API ngoài | Có cửa sổ lỗi giữa các hệ thống | Outbox/inbox, khóa idempotency, đối soát |

## 13. Bài tập thực hành có tiêu chí đạt

### Lab A — Message ID và correlation ID

Chạy hai chương trình ở mục 6. Ghi ID provider của request và reply, so sánh với requestId. Kiểm tra reply giữ nguyên **JMSCorrelationID=requestId**, dù JMSMessageID của hai message khác nhau.

**Đạt:** giải thích được vì sao requester không cần dùng JMSMessageID của reply để ghép kết quả.

### Lab B — Producer resend và consumer redelivery

Gửi **hai message mới** cùng commandId, ghi hai JMSMessageID. Sau đó thử rollback một message để broker redeliver và quan sát **JMSRedelivered**.

**Đạt:** cả hai đường gây lặp đều được nhận diện bằng commandId, không phụ thuộc chỉ số redelivery hoặc provider ID.

### Lab C — Reply đến muộn

Gửi request với TemporaryQueue, để requester timeout rồi đóng connection; sau đó chạy responder. So sánh với bài thử sử dụng **reply queue cố định đã provision** và persistent reply có retention phù hợp.

**Đạt:** phân biệt **kết quả nghiệp vụ** với **khả năng chuyển reply**; không kết luận timeout là lỗi payment.

### Lab D — Reply đảo thứ tự

Gửi request A và B, cố tình xử lý B trước A. Dùng selector **JMSCorrelationID** hoặc một dispatcher chia kết quả theo requestId.

**Đạt:** reply được ghép đúng request bất kể thứ tự consumer xử lý xong.

### Lab E — Lỗi correlation contract

Requester mong correlation theo **app requestId**, còn responder cố tình đặt correlation bằng **JMSMessageID request**. Quan sát sự không khớp, sau đó sửa theo một quy ước thống nhất.

**Đạt:** xác định lỗi ở tầng hợp đồng correlation, không nhầm với lỗi broker không gửi reply.

### Lab F — Mất ACK sau database commit

Consumer ghi marker chống trùng và kết quả database trong cùng transaction, rồi bị crash trước JMS ACK. Broker giao lại message; consumer nhận ra commandId cũ và bỏ qua side effect, sau đó ACK.

**Đạt:** hai lần delivery nhưng **một hiệu ứng nghiệp vụ**, có dữ liệu chứng minh trong database.

## 14. Checklist dùng trước khi triển khai

- [ ] Phân biệt rõ **JMSMessageID**, **JMSCorrelationID**, **JMSReplyTo** và ID nghiệp vụ trong contract.
- [ ] **commandId/eventId/paymentAttemptId** được tạo và lưu trước publish; giữ nguyên khi retry hoặc outbox replay.
- [ ] Chọn một quy ước correlation cho request–reply; hai phía dùng cùng quy ước.
- [ ] Thiết kế reply destination: temporary hay cố định, TTL, ACL, retention, timeout và cleanup.
- [ ] Requester xác minh correlation ID, xử lý duplicate/late/out-of-order reply.
- [ ] Timeout không đồng nghĩa command thất bại; có cơ chế tra trạng thái bằng ID nghiệp vụ.
- [ ] Consumer có idempotency theo phạm vi hợp lý và transaction database.
- [ ] Khi có API ngoài, sử dụng idempotency key và đối soát nếu được hỗ trợ.
- [ ] Không dùng JMSMessageID hoặc delivery count làm khóa dedup nghiệp vụ.
- [ ] Log có ID provider, business ID, correlation ID, destination và trạng thái thực thi.
- [ ] Không đưa token/PII vào header ID hoặc JMS properties.
- [ ] Kiểm tra mapping header và ReplyTo nếu đi qua Classic/Artemis, AMQP/STOMP hoặc bridge.
- [ ] Đã thử resend, rollback, timeout, mất ACK và reply queue không còn tồn tại.

**Điểm cần nhớ:** **JMSMessageID** nhận diện message do provider quản lý; **JMSCorrelationID** nối các message liên quan; **JMSReplyTo** xác định kênh phản hồi; **ID nghiệp vụ** mới quyết định tác vụ nào cần được xử lý đúng một lần về mặt hiệu ứng. Thiết kế cả bốn rõ ràng giúp ActiveMQ Classic và Artemis hỗ trợ request–reply, retry và redelivery mà vẫn đối soát được những kết quả chưa chắc chắn.
