# Thời gian chờ phản hồi và dọn dẹp tài nguyên tạm

## 1. Request-reply trong JMS

Request-reply là mô hình một client gửi request tới service rồi chờ response tương ứng. Trong Jakarta Messaging, request và response vẫn là hai message riêng. JMS cung cấp hai header để nối chúng:

- `JMSReplyTo`: destination mà responder gửi response tới.
- `JMSCorrelationID`: giá trị để response tham chiếu request đã tạo ra nó.

Requestor có thể tạo một queue phản hồi tạm thời (`TemporaryQueue`), đặt queue đó vào `JMSReplyTo`, gửi request rồi chờ message trên queue. Responder đọc `JMSReplyTo` từ request và gửi response tới destination đó. `JMSCorrelationID` giúp theo dõi request/response và ghép cặp khi nhiều request dùng chung một reply destination.

Request-reply là một cuộc trao đổi đồng bộ ở phía caller, dù transport JMS vẫn bất đồng bộ. Caller bị block trong lúc chờ. Nếu không có response trước timeout, caller nhận kết quả timeout; service có thể vẫn đang xử lý request.

## 2. Ba khái niệm thời gian cần tách biệt

Không nên dùng một giá trị timeout cho mọi giai đoạn:

| Khái niệm | Ý nghĩa | Cơ chế thường dùng |
| --- | --- | --- |
| Send timeout / send completion | Thời gian hoặc kết quả của thao tác gửi request tới provider | JMS provider, connection và API send; `JmsTemplate` không dùng `receiveTimeout` để giới hạn send |
| Reply receive timeout | Caller chờ response trong bao lâu sau khi gửi request | `JmsTemplate.setReceiveTimeout(...)` hoặc timeout tương ứng của client |
| Request TTL / expiration | Broker giữ request để giao tới responder trong bao lâu | JMS message time-to-live (`JMSExpiration`) |
| Business deadline | Thời điểm muộn nhất mà service còn nên tiếp tục xử lý nghiệp vụ | Deadline hoặc expiry timestamp do ứng dụng truyền trong payload/property |

Ví dụ: caller chờ tối đa 2 giây. Request vẫn có thể nằm trong queue thêm 10 giây nếu chưa đặt TTL. Khi responder nhận được, service có thể mất thêm 5 giây để xử lý. Reply receive timeout chỉ kết thúc việc caller chờ; nó không tự hủy message hoặc dừng công việc phía responder.

### 2.1. Receive timeout của JmsTemplate

`JmsTemplate.setReceiveTimeout(long)` đặt thời gian chờ cho các thao tác nhận đồng bộ, tính bằng milliseconds. Giá trị mặc định là `0`, tương ứng chờ vô thời hạn. Giá trị âm (ví dụ `-1`) yêu cầu kiểm tra message có sẵn mà không block.

Đối với `sendAndReceive(...)`, `JmsTemplate` dùng chính `receiveTimeout` để chờ response trên reply queue. Nếu hết thời gian mà chưa có message, method trả `null`. Vì mặc định là chờ vô hạn, ứng dụng production nên cấu hình timeout hữu hạn rõ ràng.

~~~java
JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
jmsTemplate.setReceiveTimeout(2_000); // chờ reply tối đa 2 giây
~~~

Không dùng `setReceiveTimeout(-1)` cho request-reply cần phản hồi trong thời hạn xác định: giá trị âm là no-wait, nên response chỉ được nhận nếu đã có sẵn ngay lúc consumer kiểm tra.

### 2.2. Request TTL không phải reply timeout

Time-to-live quy định thời gian request còn hiệu lực để broker giao. Khi hết TTL, provider có thể loại request chưa được giao. Nó không giới hạn thời gian responder xử lý sau khi đã nhận request và cũng không giới hạn caller chờ response.

Trong `JmsTemplate`, `setTimeToLive(...)` chỉ được áp dụng nếu bật `setExplicitQosEnabled(true)`. Nếu cần TTL cho request, cấu hình cả hai và chọn TTL theo chính sách nghiệp vụ:

~~~java
JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
jmsTemplate.setExplicitQosEnabled(true);
jmsTemplate.setTimeToLive(5_000); // request có TTL 5 giây
jmsTemplate.setReceiveTimeout(2_000); // caller chờ reply 2 giây
~~~

Trong ví dụ này, caller có thể timeout sau 2 giây trong khi request vẫn còn hạn giao thêm 3 giây. Nếu service không nên xử lý request sau deadline, truyền thêm `deadlineAt` hoặc `expiresAt` do ứng dụng quản lý và để responder kiểm tra trước khi bắt đầu nghiệp vụ. TTL của broker là lớp bảo vệ bổ sung, không thay thế deadline nghiệp vụ.

## 3. JmsTemplate.sendAndReceive() quản lý reply queue thế nào?

`JmsTemplate` cung cấp các overload `sendAndReceive(...)` nhận destination và `MessageCreator`. Trong Spring Framework 6.2, luồng cơ bản là:

1. Tạo một JMS `TemporaryQueue` cho lần gọi.
2. Tạo consumer trên queue tạm đó.
3. Tạo request bằng `MessageCreator` và đặt queue tạm vào `JMSReplyTo`.
4. Gửi request tới destination đích.
5. Chờ reply theo `receiveTimeout`.
6. Đóng reply consumer và producer, sau đó xóa temporary queue trong `finally`.

Vì vậy mỗi lời gọi request-reply độc lập có reply destination riêng. Nhiều caller có thể cùng gọi template mà không phải tự tạo tên queue phản hồi riêng hoặc dùng chung một queue để phân loại reply.

Ví dụ:

~~~java
Message reply = jmsTemplate.sendAndReceive(
        "pricing.requests",
        session -> {
            TextMessage request = session.createTextMessage("SKU-42");
            request.setJMSCorrelationID("price-request-42");
            return request;
        });

if (reply == null) {
    // Không có reply trước receiveTimeout.
}
~~~

`JmsTemplate` tự đặt `JMSReplyTo` trong quá trình request-reply. Không cần tự tạo temporary queue cho trường hợp cơ bản này. Caller vẫn có thể đặt `JMSCorrelationID` để log/trace; responder nên sao chép giá trị đó vào response.

### 3.1. TemporaryQueue có phạm vi theo Connection

JMS tạo temporary destination qua `Session` cho tiện sử dụng, nhưng vòng đời thực tế thuộc về `Connection` đã tạo nó:

- Destination được provider tạo với tên duy nhất.
- Chỉ connection đã tạo temporary destination mới được tạo consumer trên destination đó.
- Các Session khác thuộc cùng connection có thể tạo consumer.
- Temporary destination nên được xóa khi không còn dùng; provider cũng tự xóa khi connection đóng.

Trong request-reply, requestor tạo temporary queue và consumer nhận reply bằng cùng connection. Responder đọc `JMSReplyTo` rồi gửi message tới destination được chỉ định. Đặc tả Jakarta Messaging minh họa chính mô hình này.

## 4. Timeout không hủy request

Đây là điểm vận hành dễ gây lỗi nhất. Khi `sendAndReceive()` trả `null`, điều đã xảy ra chỉ là caller không nhận được reply trong khoảng thời gian cấu hình.

Request có thể đang ở một trong các trạng thái:

- Chưa được broker giao vì queue còn backlog.
- Đã được giao và responder đang xử lý.
- Responder đã hoàn tất nhưng response chưa tới reply queue.
- Response đến sát thời điểm timeout và caller không nhận được trước khi consumer đóng.
- Responder gửi reply sau khi caller timeout và temporary queue đã bị xóa.

Việc caller timeout không tự gửi lệnh hủy tới broker hoặc responder. Nếu nghiệp vụ cần hủy công việc, phải thiết kế một cancellation message/API riêng có request ID, trạng thái và quy tắc xử lý race. Responder cần kiểm tra cancellation/deadline ở các điểm an toàn trước khi tạo side effect.

### 4.1. Reply đến muộn

Với temporary queue do `JmsTemplate` tạo, khi method kết thúc vì timeout, Spring đóng consumer và xóa queue. Reply đến sau đó không còn nơi nhận hợp lệ; provider có thể từ chối thao tác gửi hoặc xử lý theo chính sách riêng. Responder cần xử lý lỗi gửi reply một cách có kiểm soát và tránh retry vô hạn.

Nếu dùng một reply queue cố định/shared, reply đến muộn có thể nằm lại trong queue. Consumer phải dùng correlation ID để phân biệt response cũ, loại bỏ message hết hạn và dọn các correlation entry không còn caller chờ.

### 4.2. Timeout và retry request

Không tự động gửi request mới với ID mới ngay sau timeout. Request trước có thể đã được xử lý thành công; retry có thể thực hiện nghiệp vụ lần thứ hai.

Với thao tác có side effect, giữ một `requestId` hoặc idempotency key ổn định qua các lần retry. Responder lưu kết quả theo key hoặc áp dụng idempotent operation để khi nhận lại cùng request, nó có thể trả kết quả cũ mà không thực hiện side effect lần nữa.

### 4.3. Chọn timeout theo ngân sách end-to-end

Timeout của caller cần tính cả thời gian xếp hàng, xử lý và trả response. Hãy đặt timeout nhỏ hơn deadline của request bên ngoài nếu còn cần thời gian chuyển lỗi, ghi log hoặc trả HTTP response.

Ví dụ một request HTTP có deadline 3 giây có thể dành 2 giây cho JMS request-reply và phần còn lại cho xử lý trước/sau JMS. Đây là ngân sách ứng dụng; con số cụ thể phải dựa trên latency thực tế và SLA.

Không đặt timeout quá ngắn so với p95/p99 của service vì sẽ tạo nhiều request timeout trong khi service vẫn hoàn thành. Ngược lại, timeout vô hạn có thể giữ thread web/server, session và connection lâu không cần thiết.

## 5. Correlation ID và định tuyến response

`JMSReplyTo` cho responder biết gửi reply ở đâu. `JMSCorrelationID` cho ứng dụng biết reply thuộc request nào.

Responder thường sao chép correlation ID từ request sang response:

~~~java
String correlationId = request.getJMSCorrelationID();
TextMessage reply = session.createTextMessage("price=19.95");
reply.setJMSCorrelationID(correlationId);
~~~

Với một temporary queue cho mỗi lời gọi, destination riêng đã cô lập response của các request đồng thời. Correlation ID vẫn hữu ích cho tracing, log và đối soát. Khi dùng reply queue chung cho nhiều request, correlation ID trở thành thành phần định tuyến quan trọng: consumer cần selector hoặc registry để ghép đúng reply với waiter.

Không dùng `JMSMessageID` của response như business request ID. Hãy tạo ID ứng dụng ổn định, đặt vào `JMSCorrelationID` hoặc custom property theo hợp đồng đã thống nhất.

## 6. JmsMessagingTemplate và request-reply

`JmsMessagingTemplate` cung cấp Spring Messaging API trên nền `JmsTemplate`:

- `sendAndReceive(destination, Message<?>)` gửi Spring message và trả Spring message phản hồi hoặc `null` khi timeout.
- `convertSendAndReceive(destination, request, targetClass)` chuyển request, gửi, nhận reply và chuyển payload response sang kiểu Java đích.

Để kiểm soát timeout, cấu hình `JmsTemplate` nền rồi truyền template đó vào `JmsMessagingTemplate`:

~~~java
JmsTemplate jmsTemplate = new JmsTemplate(connectionFactory);
jmsTemplate.setReceiveTimeout(2_500);

JmsMessagingTemplate messagingTemplate =
        new JmsMessagingTemplate(jmsTemplate);

String reply = messagingTemplate.convertSendAndReceive(
        "pricing.requests",
        "SKU-42",
        String.class);

if (reply == null) {
    throw new IllegalStateException("Pricing service did not reply in time");
}
~~~

Ví dụ dùng `String`, được `SimpleMessageConverter` ánh xạ sang `TextMessage`. Nếu dùng DTO, cần cấu hình payload converter tương thích ở cả requestor và responder. Timeout của thao tác request-reply vẫn là receive timeout trên `JmsTemplate` nền.

Không nhầm timeout này với timeout của Spring `MessagingTemplate` dùng cho `MessageChannel`; đó là abstraction khác và có cấu hình riêng.

## 7. Responder phải xử lý reply destination như thế nào?

Responder thường chạy trong listener container. Nó đọc `JMSReplyTo`, tạo response và gửi tới destination đó. Nếu request không có `JMSReplyTo`, message có thể là event/command không yêu cầu response; listener cần tuân theo hợp đồng ứng dụng.

Ví dụ với raw JMS `TextMessage`:

~~~java
@Component
public class QuoteResponder {
    private final JmsTemplate jmsTemplate;

    public QuoteResponder(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @JmsListener(destination = "pricing.requests")
    public void handle(TextMessage request) throws JMSException {
        Destination replyTo = request.getJMSReplyTo();
        if (replyTo == null) {
            // Request không yêu cầu response theo hợp đồng.
            return;
        }

        String sku = request.getText();
        String correlationId = request.getJMSCorrelationID();
        String responseBody = "SKU=" + sku + ";price=19.95";

        jmsTemplate.send(replyTo, session -> {
            TextMessage reply = session.createTextMessage(responseBody);
            if (correlationId != null) {
                reply.setJMSCorrelationID(correlationId);
            }
            return reply;
        });
    }
}
~~~

Đoạn code là integration example: ứng dụng cần một `ConnectionFactory`, broker đang chạy, queue `pricing.requests` và `@EnableJms`. `JmsTemplate` phía responder có thể gửi tới temporary destination mà requestor cung cấp. Requestor phải giữ connection đã tạo temporary queue cho tới khi hoàn tất việc nhận reply.

Trong hệ thống thực tế, không để lỗi gửi reply bị nuốt. Ghi correlation/request ID và exception; quyết định retry theo loại lỗi và transaction policy. Nếu reply destination đã bị xóa do caller timeout, responder có thể gặp lỗi khi gửi. Không retry vô hạn một reply không còn người nhận.

## 8. Ví dụ requestor Spring hoàn chỉnh ở mức tích hợp

Cấu hình timeout dùng chung:

~~~java
@Configuration
@EnableJms
public class JmsClientConfiguration {
    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setReceiveTimeout(2_000);
        return template;
    }
}
~~~

Service gửi request:

~~~java
@Service
public class QuoteClient {
    private final JmsTemplate jmsTemplate;

    public QuoteClient(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public String requestQuote(String sku) {
        String requestId = UUID.randomUUID().toString();

        Message reply = jmsTemplate.sendAndReceive(
                "pricing.requests",
                session -> {
                    TextMessage request = session.createTextMessage(sku);
                    request.setJMSCorrelationID(requestId);
                    return request;
                });

        if (reply == null) {
            throw new IllegalStateException(
                    "No quote reply before timeout; requestId=" + requestId);
        }

        if (!(reply instanceof TextMessage textReply)) {
            throw new IllegalStateException(
                    "Expected TextMessage reply; requestId=" + requestId);
        }

        try {
            return textReply.getText();
        } catch (JMSException ex) {
            throw new IllegalStateException(
                    "Cannot read quote reply; requestId=" + requestId, ex);
        }
    }
}
~~~

Imports chính cho service gồm `java.util.UUID`, `jakarta.jms.JMSException`, `jakarta.jms.Message`, `jakarta.jms.TextMessage`, `org.springframework.jms.core.JmsTemplate` và `org.springframework.stereotype.Service`.

Ví dụ này cần một JMS provider được cấu hình trong ứng dụng; Maven dependency Spring/JMS không tự cài broker. Không có stdout cố định nếu chưa chỉ định broker, responder và message thực tế. Khi responder gửi một `TextMessage` trước 2 giây, service trả body; nếu không có reply, service ném exception có request ID để log/trace.

## 9. Tự quản lý TemporaryQueue khi cần API JMS thấp hơn

Trong đa số trường hợp, `JmsTemplate.sendAndReceive()` đã quản lý temporary queue và cleanup. Chỉ tự tạo queue khi cần tùy biến vòng đời hoặc phối hợp nhiều thao tác trên cùng Session/Connection.

Mẫu thủ công:

~~~java
try (Connection connection = connectionFactory.createConnection();
     Session session = connection.createSession(Session.AUTO_ACKNOWLEDGE)) {

    TemporaryQueue replyQueue = session.createTemporaryQueue();
    try {
        try (MessageProducer producer = session.createProducer(requestQueue);
             MessageConsumer consumer = session.createConsumer(replyQueue)) {

            TextMessage request = session.createTextMessage("SKU-42");
            request.setJMSReplyTo(replyQueue);
            request.setJMSCorrelationID("quote-42");

            connection.start();
            producer.send(request);

            Message reply = consumer.receive(2_000);
            if (reply == null) {
                // Timeout: request có thể vẫn đang được xử lý.
            }
        }
    } finally {
        replyQueue.delete();
    }
}
~~~

Đoạn code minh họa cần `connectionFactory` và `requestQueue` đã được cấu hình. `Connection`, `Session`, `MessageProducer` và `MessageConsumer` được đóng bằng try-with-resources; `TemporaryQueue.delete()` chạy trong `finally` kể cả khi send/receive lỗi hoặc timeout.

Không đóng hoặc xóa temporary queue trước khi consumer nhận xong. Không dùng temporary queue sau khi connection tạo nó đã đóng. Nếu queue do framework tạo và quản lý, không tự xóa lần nữa từ code ứng dụng.

## 10. Shared reply queue và nhiều request đồng thời

Temporary queue riêng cho mỗi request dễ hiểu và tự cô lập reply, nhưng tạo thêm destination và consumer cho mỗi lần gọi. Với lưu lượng rất lớn, việc tạo/xóa liên tục có thể tạo overhead ở broker/provider.

Một mô hình khác là reply queue cố định hoặc một temporary queue được tái sử dụng cùng listener container. Khi đó cần correlation registry:

1. Requestor tạo correlation ID duy nhất và đăng ký waiter trước khi gửi request.
2. Request mang correlation ID và reply destination chung.
3. Responder gửi reply với cùng correlation ID.
4. Reply listener tìm waiter theo correlation ID và hoàn tất future/promise.
5. Timeout xóa waiter khỏi registry; reply đến muộn được ghi nhận và loại bỏ.

Spring Integration JMS outbound gateway hỗ trợ mô hình reply listener container; khi không chỉ định reply destination, có thể dùng một TemporaryQueue cho gateway thay vì tạo một queue cho từng request. Cấu hình này hữu ích khi cần tái sử dụng consumer và quản lý nhiều reply đồng thời.

Shared reply queue cần giới hạn kích thước registry, dọn waiter hết hạn, xử lý correlation ID trùng và message đến muộn. Nếu không, map chờ reply có thể tăng mãi hoặc reply cũ ghép nhầm với request mới.

## 11. Transaction và request-reply

Không chờ reply trong cùng một JMS transaction chưa commit. Nếu request được gửi trong transacted Session, provider thường chỉ giao request sau khi transaction commit. Nếu caller giữ transaction đó mở rồi chờ response, responder có thể không bao giờ nhìn thấy request để trả lời.

Đặc tả Jakarta Messaging mô tả request/reply bằng temporary queue với request được gửi trong transaction riêng và response được nhận trong transaction khác. `JmsTemplate.sendAndReceive()` dùng một thao tác cục bộ cho request/receive; không coi nó là một transaction nguyên tử bao trùm nghiệp vụ của responder.

Nếu responder vừa cập nhật database vừa gửi reply, cần xác định thứ tự commit và khả năng retry. JMS transaction chỉ phối hợp các thao tác JMS trong Session. Database transaction là resource riêng trừ khi dùng JTA/XA phù hợp; idempotency vẫn cần thiết để xử lý redelivery hoặc retry.

Với request có side effect, timeout không có nghĩa nghiệp vụ rollback. Trả timeout cho caller trong khi responder đã commit có thể khiến caller retry và tạo thao tác lặp. Dùng request ID ổn định, lưu kết quả theo idempotency key và cung cấp API truy vấn trạng thái nếu nghiệp vụ cần biết kết quả sau timeout.

## 12. Các lỗi thường gặp

- **Để receive timeout mặc định vô hạn:** caller có thể giữ thread mãi nếu responder không trả lời. Đặt timeout hữu hạn phù hợp SLA.
- **Nhầm receive timeout với TTL:** timeout dừng caller chờ; TTL quyết định request còn hạn để broker giao.
- **Cho rằng timeout hủy request:** responder có thể vẫn nhận và xử lý request sau khi caller đã trả timeout.
- **Không kiểm tra `null` từ `sendAndReceive`:** không có reply trước timeout được biểu diễn bằng `null`.
- **Quên cleanup temporary queue tự tạo:** queue có thể giữ resource ở broker cho tới khi connection đóng.
- **Tạo consumer trên connection khác:** temporary destination chỉ cho connection sở hữu tạo consumer.
- **Xóa queue trước khi reply consumer đóng:** provider có thể từ chối xóa hoặc thao tác nhận đang chạy bị lỗi.
- **Không đặt correlation ID:** log và shared reply queue khó ghép request/response chính xác.
- **Dùng chung reply queue nhưng không có selector/registry:** reply của request này có thể bị ghép nhầm với request khác.
- **Retry với request ID mới sau timeout:** service có thể thực hiện side effect hai lần.
- **Chờ reply trong cùng transaction chưa commit:** responder không thấy request để xử lý.
- **Nuốt lỗi gửi reply:** caller timeout mà không có log đủ thông tin để điều tra.
- **Dùng request-reply cho tác vụ dài:** giữ thread chờ lâu; cân nhắc command bất đồng bộ và event kết quả.
- **Dùng temporary queue cho luồng cần lưu reply lâu dài:** temporary destination gắn với connection và không phù hợp làm kho kết quả bền vững.

## 13. Kiểm thử timeout và cleanup

Kiểm thử cần quan sát cả caller, responder và broker:

1. Responder trả lời nhanh: caller nhận đúng payload và correlation ID.
2. Responder không chạy: caller trả timeout đúng thời gian cấu hình.
3. Responder trả lời sau timeout: caller không nhận reply; responder ghi nhận lỗi/late reply theo policy.
4. Request hết TTL trước khi được giao: responder không xử lý request đã hết hạn.
5. Request được giao trước TTL nhưng xử lý lâu: kiểm tra business deadline ở responder.
6. Gửi nhiều request đồng thời: không ghép nhầm reply giữa các caller.
7. Ném exception khi tạo request, gửi, nhận hoặc cleanup: producer/consumer/temporary queue được giải phóng.
8. Broker ngắt kết nối khi đang chờ: phân biệt timeout với JMS/provider exception.
9. Caller retry cùng request ID: responder trả kết quả cũ hoặc xử lý idempotently.
10. Restart ứng dụng: không còn temporary destination bị bỏ quên; shared reply registry được dọn đúng cách.

Metrics nên tách số request gửi, reply nhận, timeout, provider exception, late reply, request hết TTL, thời gian xử lý responder, temporary destination creation/deletion và số waiter đang chờ. Log nên có request ID, correlation ID, destination và deadline; tránh log payload nhạy cảm.

## 14. Checklist thiết kế

1. Request có cần response ngay hay có thể dùng event bất đồng bộ?
2. Reply destination là temporary queue riêng hay shared/permanent queue?
3. `JMSReplyTo` được đặt và đọc ở đâu?
4. Correlation ID có ổn định và được sao chép sang response không?
5. `receiveTimeout` có hữu hạn và phù hợp với deadline của caller không?
6. Request TTL có cần thiết để loại request chưa được giao sau deadline không?
7. Responder có kiểm tra business deadline trước side effect không?
8. Timeout có được xử lý như kết quả chưa xác định thay vì cancellation không?
9. Retry có giữ nguyên request ID/idempotency key không?
10. TemporaryQueue có được xóa trong mọi nhánh thành công, timeout và exception không?
11. Consumer và producer có đóng trước khi delete temporary destination không?
12. Shared reply queue có correlation registry, timeout cleanup và late-reply policy không?
13. Có tránh chờ reply trong transaction chưa commit không?
14. Có test concurrent requests, late reply, broker failure và cleanup failure không?

## 15. Ghi nhớ

`JMSReplyTo` chỉ định nơi responder gửi response; `JMSCorrelationID` liên kết response với request. `JmsTemplate.sendAndReceive()` trong Spring 6.2 tạo TemporaryQueue cho mỗi lần gọi, đặt nó vào request, chờ theo `receiveTimeout`, rồi đóng consumer/producer và xóa queue trong `finally`. `receiveTimeout` mặc định là chờ vô hạn (`0`); timeout hữu hạn trả `null` nếu chưa có reply. Timeout không hủy request và không rollback side effect của responder. Request TTL điều khiển thời gian broker còn được phép giao request; business deadline phải được ứng dụng kiểm tra riêng. Khi tự quản lý temporary destination, phải dùng cùng connection để tạo consumer và xóa queue sau khi đóng consumer. Với retry, giữ request ID ổn định và làm responder idempotent để tránh lặp nghiệp vụ.

### Tài liệu tham khảo

- [Spring Framework 6.2 — Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Spring Framework 6.2 — Receiving a Message](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html)
- [Spring Framework 6.2.14 — JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Framework 6.2.18 — JmsMessagingTemplate Javadoc](https://www.springframework.org/spring/docs/6.2.18/javadoc-api/org/springframework/jms/core/JmsMessagingTemplate.html)
- [Jakarta Messaging 3.1 Specification — Request/reply and temporary destinations](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Spring Integration 6.2 — JMS outbound gateway and reply handling](https://docs.spring.io/spring-integration/reference/6.2/jms.html)