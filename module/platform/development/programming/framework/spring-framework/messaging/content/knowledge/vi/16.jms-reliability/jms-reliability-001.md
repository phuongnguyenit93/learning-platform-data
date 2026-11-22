# JMSMessageID, JMSCorrelationID và JMSReplyTo

Trong JMS, ba header này hỗ trợ nhận diện message và phối hợp request/reply giữa các thành phần:

- **JMSMessageID** là mã định danh do JMS provider gán cho message khi gửi.
- **JMSCorrelationID** là giá trị ứng dụng dùng để liên kết message với một message khác, thường là liên kết reply với request.
- **JMSReplyTo** là Destination mà bên nhận có thể gửi reply tới. Giá trị này có thể là Queue hoặc Topic; nếu null thì request không khai báo nơi nhận reply.

Ba header có vai trò khác nhau và không thể thay thế cho nhau. Message ID nhận diện một message cụ thể; Correlation ID mô tả quan hệ giữa các message; ReplyTo chỉ nơi gửi phản hồi. Hiểu đúng ba giá trị này giúp xây dựng request/reply, ghép phản hồi với request tương ứng, xử lý nhiều request đồng thời và điều tra lỗi trong hệ thống messaging.

## 1. Vị trí của ba header trong JMS Message

JMS Message gồm header chuẩn, properties và body:

- **Header:** metadata chuẩn do JMS định nghĩa, ví dụ JMSMessageID, JMSCorrelationID, JMSReplyTo, JMSTimestamp, JMSDestination và JMSRedelivered.
- **Properties:** các thuộc tính do ứng dụng hoặc provider bổ sung để định tuyến, lọc hoặc mang metadata nghiệp vụ.
- **Body:** nội dung message như TextMessage, BytesMessage, MapMessage, ObjectMessage hoặc StreamMessage.

JMSMessageID, JMSCorrelationID và JMSReplyTo là header chuẩn. Không nên tự tạo property có tên gần giống rồi kỳ vọng broker hoặc consumer hiểu đó là header JMS tương ứng.

~~~mermaid
flowchart TD
    A["JMS Message"] --> B["Standard headers"]
    A --> C["Properties"]
    A --> D["Body"]
    B --> E["JMSMessageID"]
    B --> F["JMSCorrelationID"]
    B --> G["JMSReplyTo"]
    C --> H["Application metadata"]
    D --> I["Text / Bytes / Map / Object"]
~~~

Các phương thức đọc và ghi header nằm trên interface jakarta.jms.Message trong Jakarta Messaging hiện đại. Với Spring Framework cũ sử dụng JMS API đời trước, package có thể là javax.jms. Hãy dùng package phù hợp với phiên bản Spring và provider của ứng dụng.

## 2. JMSMessageID: mã định danh do provider cấp

JMSMessageID là mã duy nhất mà provider gán cho mỗi message được gửi. Nó hữu ích để:

- Tìm một message cụ thể trong log hoặc công cụ quản trị broker.
- Liên kết request và reply khi dùng message ID làm correlation key.
- Điều tra redelivery hoặc đối chiếu message giữa producer và consumer.
- Lưu dấu vết message trong hệ thống giám sát hoặc kho lịch sử.

### 2.1. Provider gán ID khi gửi

Client tạo message trước khi gửi nhưng không tự quyết định JMSMessageID. Khi phương thức send hoặc publish trả về, provider đã gán giá trị ID và message có thể được đọc qua:

~~~java
String messageId = message.getJMSMessageID();
~~~

Trong Jakarta Messaging, các giá trị message ID do provider tạo phải bắt đầu bằng tiền tố **ID:**. Phạm vi duy nhất của ID do provider xác định; tối thiểu cần bao phủ các message trong một installation của provider. Không được giả định ID là duy nhất toàn cầu giữa nhiều broker hoặc nhiều nhà cung cấp.

Client không được dùng setJMSMessageID() để tự đặt ID. Phương thức này dành cho provider khi gửi message. Nếu ứng dụng cần một mã nghiệp vụ do chính mình quản lý, hãy đặt nó trong một application property hoặc dùng JMSCorrelationID theo đúng mục đích liên kết message.

### 2.2. Có thể tắt việc tạo MessageID

JMS cho phép client đưa ra gợi ý không cần provider tạo message ID, thông qua MessageProducer.setDisableMessageID(true). Spring JmsTemplate cũng có thuộc tính messageIdEnabled để điều khiển hành vi tương ứng.

Nếu provider chấp nhận gợi ý này, JMSMessageID của message gửi ra phải là null. Provider có thể bỏ qua gợi ý và vẫn tạo ID bình thường.

Chỉ tắt MessageID khi ứng dụng chắc chắn không dùng ID để correlation, logging, tracing hoặc chẩn đoán. Nếu bên nhận cần lấy JMSMessageID của request để đặt JMSCorrelationID cho reply, không được dựa vào message ID khi đã tắt chức năng này.

### 2.3. MessageID không phải khóa idempotency nghiệp vụ

JMSMessageID nhận diện một lần gửi message do provider xử lý. Nếu ứng dụng gửi lại cùng một sự kiện thành một message mới, provider có thể cấp một JMSMessageID khác. Vì vậy, không dùng MessageID làm khóa duy nhất để chống xử lý trùng ở cấp nghiệp vụ.

Nếu cần idempotency, hãy mang một event ID hoặc request ID do ứng dụng tạo trong property/body và lưu dấu đã xử lý theo khóa đó. JMSMessageID vẫn hữu ích cho việc truy vết từng bản gửi cụ thể.

## 3. JMSCorrelationID: liên kết các message có quan hệ

JMSCorrelationID dùng để liên kết một message với message khác. Mẫu phổ biến nhất là gắn reply với request ban đầu.

Ví dụ:

~~~text
Request:
  JMSMessageID     = ID:provider-001
  JMSCorrelationID = order-request-42

Reply:
  JMSMessageID     = ID:provider-002
  JMSCorrelationID = ID:provider-001
~~~

Ở ví dụ này, reply mang JMSCorrelationID bằng JMSMessageID của request. Nhờ vậy, bên gửi có thể xác định reply tương ứng với request nào.

### 3.1. Hai cách dùng CorrelationID phổ biến

Có hai quy ước thường gặp:

**Cách A — Reply tham chiếu JMSMessageID của request**

1. Producer gửi request.
2. Provider gán JMSMessageID cho request.
3. Consumer xử lý request đọc JMSMessageID.
4. Consumer tạo reply và đặt JMSCorrelationID bằng JMSMessageID của request.
5. Producer nhận reply và so sánh JMSCorrelationID với ID request đã gửi.

Đây là cách dùng chuẩn và dễ hiểu khi phía gửi có thể lấy được ID của request sau khi send hoàn tất.

**Cách B — Dùng correlation ID do ứng dụng tạo**

1. Producer tạo một request ID duy nhất, ví dụ UUID.
2. Producer đặt request ID vào JMSCorrelationID trước khi gửi.
3. Consumer đọc JMSCorrelationID của request.
4. Consumer sao chép giá trị đó sang JMSCorrelationID của reply.
5. Producer dùng giá trị đã biết để ghép reply với request đang chờ.

Cách B thuận tiện khi có nhiều request đồng thời và ứng dụng muốn biết correlation key ngay trước khi gửi. Nó cũng cho phép giữ cùng một request ID xuyên qua nhiều bước xử lý.

Không nên trộn hai quy ước trong cùng một luồng nếu các thành phần không thống nhất. Producer và consumer phải biết reply sẽ trả về JMSMessageID hay JMSCorrelationID ban đầu.

### 3.2. Kiểu giá trị hợp lệ

JMSCorrelationID có thể chứa:

- Một provider-specific message ID, thường là JMSMessageID của request.
- Một String do ứng dụng quy định.
- Một byte[] theo định dạng native của provider.

Dùng byte[] cho CorrelationID là không portable. Provider không hỗ trợ khái niệm correlation ID native không bắt buộc phải hỗ trợ các phương thức byte-array. Trong ứng dụng đa provider, nên ưu tiên String.

Nếu ứng dụng tự đặt correlation ID dạng String, giá trị đó không được bắt đầu bằng **ID:** vì tiền tố này dành riêng cho message ID do provider tạo.

Ví dụ:

~~~java
request.setJMSCorrelationID(UUID.randomUUID().toString());
~~~

Giá trị UUID là một lựa chọn phù hợp vì dễ tạo, có xác suất trùng rất thấp và không dùng tiền tố ID:.

### 3.3. CorrelationID không tự bảo đảm thứ tự hoặc delivery

JMSCorrelationID chỉ là metadata liên kết. Nó không:

- Bảo đảm request đã được xử lý.
- Bảo đảm reply sẽ được gửi.
- Bảo đảm reply đến trước timeout.
- Tự tạo transaction giữa request và reply.
- Ngăn broker giao lại message.
- Thay thế message ID hoặc event ID phục vụ idempotency.

Ứng dụng phải định nghĩa timeout, retry, xử lý reply đến muộn và dọn dữ liệu correlation đang chờ.

## 4. JMSReplyTo: chỉ định nơi nhận phản hồi

JMSReplyTo là một header chứa đối tượng **Destination**. Destination này có thể là Queue hoặc Topic. Producer đặt giá trị này trên request để thông báo cho consumer biết nơi có thể gửi reply.

Ví dụ:

~~~java
request.setJMSReplyTo(replyQueue);
~~~

Bên nhận đọc destination bằng:

~~~java
Destination replyTo = request.getJMSReplyTo();
~~~

Nếu JMSReplyTo là null, request không khai báo nơi nhận reply. Điều đó thường có nghĩa message chỉ mang dữ liệu hoặc thông báo một chiều. Nếu có ReplyTo, bên gửi thường mong đợi phản hồi, nhưng JMS không bắt buộc consumer phải gửi reply.

### 4.1. ReplyTo là Destination, không phải nội dung phản hồi

JMSReplyTo chỉ ra địa chỉ gửi phản hồi. Nó không chứa kết quả xử lý và không tự gửi message. Consumer phải chủ động tạo reply và gửi đến destination này.

~~~mermaid
sequenceDiagram
    participant A as Requester
    participant Q as Request Queue
    participant B as Responder
    participant R as Reply Queue
    A->>Q: Request + JMSReplyTo + JMSCorrelationID
    Q->>B: Deliver request
    B->>B: Process request
    B->>R: Reply + JMSCorrelationID
    R->>A: Deliver matching reply
~~~

Queue thường được dùng cho reply vì mỗi reply được giao cho một consumer nhận phù hợp. Nếu dùng Topic, cần hiểu subscription và khả năng có nhiều subscriber nhận cùng publication. Nếu requester chưa đăng ký subscription khi reply được publish, reply có thể không được nhận theo semantics của Topic.

### 4.2. TemporaryQueue và TemporaryTopic

Requester có thể tạo temporary destination cho một request hoặc một phiên làm việc:

~~~java
TemporaryQueue replyQueue = session.createTemporaryQueue();
request.setJMSReplyTo(replyQueue);
~~~

Temporary destination hữu ích vì không cần cấu hình sẵn một reply queue dùng chung. Responder có thể gửi reply đến destination được cung cấp trong request.

Temporary destination có vòng đời gắn với Connection đã tạo nó. Khi Connection đóng, temporary destination được xóa theo semantics của JMS provider. Vì vậy:

- Không lưu temporary destination để dùng lâu dài sau khi Connection đóng.
- Không gửi reply sau khi requester đã đóng Connection và temporary destination không còn tồn tại.
- Nếu ứng dụng cần reply queue dùng chung hoặc xử lý bất đồng bộ lâu dài, hãy dùng destination được quản trị phù hợp.
- Kiểm tra quyền broker cho phép responder gửi tới temporary destination.

## 5. Request/reply bằng JMS: quy trình đầy đủ

Một request/reply thường có các bước:

1. Requester tạo hoặc chọn reply destination.
2. Requester tạo request message.
3. Requester đặt JMSReplyTo và correlation key.
4. Requester gửi request đến destination xử lý.
5. Responder nhận request, đọc JMSReplyTo và correlation key.
6. Responder xử lý nghiệp vụ.
7. Responder tạo reply và đặt JMSCorrelationID theo quy ước đã thống nhất.
8. Responder gửi reply đến JMSReplyTo.
9. Requester nhận reply và ghép với request đang chờ.
10. Requester hoàn tất hoặc timeout, rồi dọn trạng thái correlation.

Ví dụ request có application correlation ID:

~~~java
String correlationId = UUID.randomUUID().toString();

jmsTemplate.send("orders.request", session -> {
    TextMessage request =
            session.createTextMessage("Create order ORD-42");

    request.setJMSCorrelationID(correlationId);
    request.setJMSReplyTo(replyQueue);

    return request;
});
~~~

Responder sao chép correlation ID sang reply:

~~~java
@JmsListener(destination = "orders.request")
public void handle(Message request) throws JMSException {
    Destination replyTo = request.getJMSReplyTo();

    if (replyTo == null) {
        return; // Request không yêu cầu reply.
    }

    String correlationId = request.getJMSCorrelationID();

    jmsTemplate.send(replyTo, session -> {
        TextMessage reply =
                session.createTextMessage("Order ORD-42 accepted");

        if (correlationId != null) {
            reply.setJMSCorrelationID(correlationId);
        }

        return reply;
    });
}
~~~

Đây là ví dụ dùng Jakarta JMS API trong Spring Framework hiện đại. Nếu dự án dùng Spring cũ, thay import jakarta.jms bằng javax.jms tương ứng. Trong ứng dụng thực tế, cần xác định cách xử lý khi correlation ID thiếu, reply destination không hợp lệ hoặc nghiệp vụ không tạo được kết quả.

## 6. Dùng JmsTemplate.sendAndReceive()

Spring cung cấp request/reply đồng bộ qua JmsTemplate.sendAndReceive(). Template tạo một TemporaryQueue cho thao tác, đặt Queue đó vào JMSReplyTo của request rồi chờ reply.

Ví dụ:

~~~java
Message reply = jmsTemplate.sendAndReceive(
        "orders.request",
        session -> session.createTextMessage("Create order ORD-42")
);

if (reply instanceof TextMessage textReply) {
    String result = textReply.getText();
    // Xử lý kết quả.
}
else if (reply == null) {
    // Hết receive timeout mà chưa nhận được reply.
}
~~~

JmsTemplate quản lý việc tạo và giải phóng resource trong phạm vi thao tác. Có thể cấu hình receive timeout bằng setReceiveTimeout(). Nếu timeout hết, sendAndReceive() có thể trả về null.

Trong mô hình temporary queue riêng cho một lần gọi, requester có một destination riêng để chờ reply nên không cần selector correlation để phân biệt nhiều reply trên cùng queue. Dù vậy, responder vẫn có thể đặt JMSCorrelationID của reply bằng JMSMessageID hoặc JMSCorrelationID của request để giữ ngữ cảnh truy vết.

JmsTemplate phù hợp với request/reply đồng bộ: thread gọi bị block trong thời gian chờ phản hồi. Nếu số request lớn hoặc thời gian xử lý dài, cần cân nhắc mô hình bất đồng bộ để không giữ quá nhiều thread chờ.

## 7. Reply queue dùng chung và message selector

Khi nhiều request cùng dùng một reply Queue, requester phải phân biệt reply nào thuộc request nào. Cách thường dùng là JMS message selector lọc theo JMSCorrelationID.

Ví dụ requester tạo correlation ID trước khi gửi:

~~~java
String correlationId = UUID.randomUUID().toString();

jmsTemplate.send("orders.request", session -> {
    TextMessage request = session.createTextMessage("Create order");
    request.setJMSCorrelationID(correlationId);
    request.setJMSReplyTo(replyQueue);
    return request;
});
~~~

Sau khi responder sao chép correlation ID vào reply, requester có thể nhận đúng reply:

~~~java
String selector =
        "JMSCorrelationID = '" + correlationId + "'";

Message reply = jmsTemplate.receiveSelected(
        "orders.reply",
        selector
);
~~~

JmsTemplate sử dụng receive timeout đã cấu hình. Nếu timeout hết, receiveSelected() trả về null.

Trong ví dụ trên, correlation ID là UUID do ứng dụng tạo nên không chứa dấu nháy đơn. Nếu selector được xây dựng từ giá trị bên ngoài, phải escape ký tự nháy đơn theo cú pháp selector và xác thực đầu vào. Không nối trực tiếp dữ liệu không tin cậy vào message selector.

### 7.1. Một consumer hay nhiều consumer trên reply queue?

Nếu mỗi request tạo một consumer với selector riêng, nhiều consumer có thể cùng lắng nghe một reply queue. Cần kiểm tra cách provider xử lý selector và phân phối message. Với số request lớn, việc tạo consumer liên tục có thể tăng chi phí.

Một mô hình khác là dùng một reply listener chung cho reply queue, sau đó định tuyến reply đến request đang chờ bằng một bảng correlation:

~~~text
correlationId -> CompletableFuture / pending request
~~~

Khi reply đến, listener đọc JMSCorrelationID, tìm future tương ứng và hoàn tất nó. Khi timeout hoặc request kết thúc, xóa entry khỏi bảng. Cần xử lý trường hợp reply đến sau timeout để tránh rò rỉ bộ nhớ.

Spring Integration JMS Gateway cung cấp sẵn nhiều cơ chế correlation cho request/reply. Nếu ứng dụng cần gateway bất đồng bộ hoặc quản lý reply listener dùng chung, hãy cân nhắc dùng gateway thay vì tự triển khai toàn bộ bộ định tuyến.

## 8. JMS headers trong Spring Messaging

Spring JMS cung cấp interface **org.springframework.jms.support.JmsHeaders** với các tên header chuẩn để ánh xạ JMS metadata sang Spring Message:

| JmsHeaders constant | JMS field | Ý nghĩa |
|---|---|---|
| MESSAGE_ID | JMSMessageID | ID do provider gán |
| CORRELATION_ID | JMSCorrelationID | Khóa liên kết message |
| REPLY_TO | JMSReplyTo | Destination nhận reply |
| DESTINATION | JMSDestination | Destination hiện tại |
| REDELIVERED | JMSRedelivered | Dấu hiệu message được giao lại |

SimpleJmsHeaderMapper có thể ánh xạ các header JMS chuẩn giữa jakarta.jms.Message và org.springframework.messaging.Message. Với Spring Message, có thể đọc các header qua JmsMessageHeaderAccessor:

~~~java
JmsMessageHeaderAccessor accessor =
        JmsMessageHeaderAccessor.wrap(springMessage);

String messageId = accessor.getMessageId();
String correlationId = accessor.getCorrelationId();
Destination replyTo = accessor.getReplyTo();
~~~

Lưu ý **MessageHeaders.ID** của Spring Messaging là UUID do Spring tạo cho đối tượng Spring Message. Nó không phải JMSMessageID do broker cấp. Khi cần ID của message JMS, hãy dùng JmsHeaders.MESSAGE_ID hoặc JmsMessageHeaderAccessor.getMessageId().

JMSMessageID là giá trị read-only trong mapping header chuẩn. Ứng dụng không nên cố gắng đặt nó bằng cách ghi vào Spring header map. Nếu cần một ID nghiệp vụ do ứng dụng tạo, hãy dùng JMSCorrelationID hoặc một custom property.

## 9. Quy ước correlation trong hệ thống nhiều dịch vụ

Khi request đi qua nhiều service, correlation ID có thể được giữ nguyên để truy vết cả chuỗi xử lý.

Ví dụ:

~~~text
API Gateway
  correlationId = req-7f31
      |
      v
Order Service
  request JMSCorrelationID = req-7f31
      |
      v
Inventory Service
  reply JMSCorrelationID = req-7f31
      |
      v
Order Service
  response correlationId = req-7f31
~~~

Một số nguyên tắc:

- Tạo correlation ID tại ranh giới đầu tiên của request nếu chưa có.
- Giữ nguyên correlation ID qua các bước xử lý thuộc cùng một request.
- Nếu một message tạo ra nhiều nhánh độc lập, cân nhắc thêm event ID hoặc parent ID để biểu diễn quan hệ cha-con.
- Không dùng một correlation ID chung cho mọi message.
- Không nhầm correlation ID với trace ID của distributed tracing; hai giá trị có thể được liên kết nhưng có mục đích và lifecycle khác nhau.
- Ghi correlation ID vào log, metric hoặc trace để tìm chuỗi request/reply.

JMSCorrelationID không phải một cơ chế bảo mật và không chứng minh người gửi là ai. Không dùng nó để xác thực danh tính hoặc cấp quyền truy cập.

## 10. Độ tin cậy, timeout và message đến muộn

Request/reply có thể gặp nhiều trạng thái:

- Request chưa được broker nhận.
- Request đã được nhận nhưng responder chưa xử lý.
- Responder đã xử lý nhưng reply chưa được gửi.
- Reply đã gửi nhưng requester timeout trước khi nhận.
- Reply đến sau khi requester đã dọn trạng thái correlation.
- Request hoặc reply được redeliver sau rollback.

Timeout chỉ cho biết requester đã ngừng chờ trong thời gian quy định. Nó không chứng minh responder chưa xử lý request. Nếu requester gửi lại sau timeout, nghiệp vụ có thể được thực hiện hai lần.

Cần thiết kế:

1. **Request ID ổn định:** giúp nhận diện cùng một yêu cầu nghiệp vụ qua retry.
2. **Idempotency:** responder lưu dấu request đã xử lý để tránh lặp tác dụng phụ.
3. **Timeout:** giới hạn thời gian chờ reply và ghi nhận trạng thái timeout.
4. **Late reply handling:** quyết định bỏ qua, lưu lại hoặc phát cảnh báo khi reply đến sau timeout.
5. **Retry policy:** xác định lỗi nào có thể retry và số lần thử.
6. **Expiration/TTL:** có thể giới hạn thời gian sống của request/reply nếu nghiệp vụ cho phép.
7. **DLQ:** giữ message không thể xử lý để điều tra thay vì retry vô hạn.

JMSMessageID, JMSCorrelationID và JMSReplyTo không tự cung cấp exactly-once processing. Độ tin cậy còn phụ thuộc delivery mode, transaction, acknowledgement, broker persistence, redelivery policy và idempotency của ứng dụng.

## 11. Bảo mật khi dùng JMSReplyTo

JMSReplyTo là Destination được mang trong message. Nếu consumer nhận request từ một nguồn không đáng tin, không nên mặc định gửi reply tới bất kỳ destination nào mà request chỉ định.

Các biện pháp cần cân nhắc:

- Chỉ cho phép reply tới destination nằm trong namespace hoặc allowlist đã cấu hình.
- Kiểm tra quyền gửi của broker đối với temporary và dynamic destination.
- Không cho phép client tự do chọn destination nội bộ nhạy cảm.
- Ghi log destination sau khi đã loại bỏ thông tin nhạy cảm.
- Giới hạn số request chờ và số temporary destination được tạo.
- Đặt TTL và timeout hợp lý để tránh tài nguyên chờ không được giải phóng.
- Escape và xác thực correlation ID khi đưa vào selector.

Nếu hệ thống dùng multi-tenant, cần kiểm tra requester có quyền nhận reply của tenant tương ứng. Correlation ID có thể giúp định tuyến đúng request nhưng không thay thế kiểm tra quyền.

## 12. Lỗi thường gặp và cách xử lý

### 12.1. Tự đặt JMSMessageID

Client cố gọi setJMSMessageID() để gán ID nghiệp vụ. Đây là field do provider quản lý.

Cách xử lý: dùng application property hoặc JMSCorrelationID cho giá trị do ứng dụng tạo.

### 12.2. Tắt MessageID nhưng vẫn dùng nó làm correlation key

Khi provider chấp nhận disable message ID, JMSMessageID có thể là null. Reply không thể tham chiếu một ID không tồn tại.

Cách xử lý: giữ MessageID nếu cần hoặc tạo correlation ID ứng dụng trước khi gửi.

### 12.3. Request và reply dùng hai quy ước khác nhau

Requester mong reply trả về application correlation ID nhưng responder lại đặt JMSMessageID của request, hoặc ngược lại.

Cách xử lý: công bố rõ reply correlation phải bằng request JMSMessageID hay request JMSCorrelationID và kiểm thử cả hai phía.

### 12.4. JMSReplyTo bị null

Consumer không tìm được nơi gửi reply.

Cách xử lý: xác định request có thật sự yêu cầu phản hồi không; nếu có, producer phải đặt ReplyTo hoặc dùng JmsTemplate.sendAndReceive().

### 12.5. Reply đến nhầm request

Nhiều request dùng chung một correlation ID hoặc reply không sao chép đúng giá trị.

Cách xử lý: dùng correlation ID duy nhất cho mỗi request đang chờ, kiểm tra selector và log giá trị ở cả hai phía.

### 12.6. Reply queue không còn tồn tại

Requester dùng TemporaryQueue rồi đóng Connection trước khi responder gửi reply.

Cách xử lý: giữ Connection/destination còn hiệu lực đến khi reply hoàn tất hoặc dùng reply destination được quản trị có lifecycle dài hơn.

### 12.7. Reply đến sau timeout

Requester đã xóa correlation entry nhưng reply vẫn đến.

Cách xử lý: có chính sách cho late reply, ghi metric và bảo đảm bảng pending request được dọn đúng cách.

### 12.8. Dùng JMSMessageID làm idempotency key

Mỗi lần gửi lại cùng một event có thể tạo ID mới nên dedup theo JMSMessageID không ngăn được duplicate nghiệp vụ.

Cách xử lý: thêm eventId/requestId do ứng dụng tạo và lưu cùng trạng thái đã xử lý.

## 13. Ví dụ Java 17: mô phỏng request/reply bằng ba header

Ví dụ sau dùng JDK thuần để minh họa cách ba header phối hợp. DemoMessage là record do chương trình tự định nghĩa, không phải jakarta.jms.Message. MessageID được mô phỏng như ID do provider cấp; chương trình không kết nối broker.

Tạo file **JmsRequestReplyHeadersDemo.java**:

~~~java
public class JmsRequestReplyHeadersDemo {

    record DemoMessage(
            String messageId,
            String correlationId,
            String replyTo,
            String body) {}

    static DemoMessage createRequest() {
        // Mô phỏng JMS provider gán MessageID sau khi gửi.
        return new DemoMessage(
                "ID:provider-001",
                "order-request-42",
                "orders.reply",
                "Create order ORD-42"
        );
    }

    static DemoMessage createReply(DemoMessage request) {
        if (request.replyTo() == null) {
            throw new IllegalArgumentException(
                    "Request has no JMSReplyTo destination");
        }

        // Quy ước: reply CorrelationID = request MessageID.
        return new DemoMessage(
                "ID:provider-002",
                request.messageId(),
                null,
                "Order ORD-42 accepted"
        );
    }

    public static void main(String[] args) {
        DemoMessage request = createRequest();
        DemoMessage reply = createReply(request);

        boolean matched = request.messageId()
                .equals(reply.correlationId());

        System.out.println(
                "Request JMSMessageID: " + request.messageId());
        System.out.println(
                "Request JMSCorrelationID: " + request.correlationId());
        System.out.println(
                "Request JMSReplyTo: " + request.replyTo());
        System.out.println(
                "Reply JMSCorrelationID: " + reply.correlationId());
        System.out.println("Reply matched request: " + matched);
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac JmsRequestReplyHeadersDemo.java
java JmsRequestReplyHeadersDemo
~~~

Kết quả:

~~~text
Request JMSMessageID: ID:provider-001
Request JMSCorrelationID: order-request-42
Request JMSReplyTo: orders.reply
Reply JMSCorrelationID: ID:provider-001
Reply matched request: true
~~~

Ví dụ sử dụng quy ước reply JMSCorrelationID bằng request JMSMessageID. Nếu hệ thống chọn quy ước application correlation ID, responder sẽ đặt reply correlation ID bằng order-request-42 thay vì ID:provider-001. Hai phía phải thống nhất cùng một quy ước.

## 14. Checklist thiết kế request/reply

Trước khi triển khai, hãy xác định:

- Ai cấp JMSMessageID và ứng dụng có cần giữ ID này không?
- Có cần tắt việc tạo message ID vì lý do hiệu năng không?
- Correlation key là JMSMessageID hay application-generated JMSCorrelationID?
- Reply phải sao chép giá trị correlation nào?
- JMSReplyTo là Queue, Topic, TemporaryQueue hay destination dùng chung?
- Ai sở hữu và đóng temporary destination?
- Requester chờ reply đồng bộ hay nhận bất đồng bộ?
- Nếu dùng reply queue chung, selector hoặc correlation map được quản lý thế nào?
- Timeout, late reply, retry và DLQ được xử lý ra sao?
- Responder có idempotent khi request được redeliver không?
- Destination trong JMSReplyTo có được xác thực và giới hạn quyền không?
- Log có lưu message ID, correlation ID và destination theo cách an toàn không?

JMSMessageID nhận diện message do provider gửi; JMSCorrelationID liên kết request với reply hoặc các message liên quan; JMSReplyTo chỉ định destination nhận phản hồi. Khi kết hợp đúng, ba header tạo nên một giao thức request/reply rõ ràng. Trong Spring, JmsTemplate.sendAndReceive() giúp đơn giản hóa request/reply đồng bộ bằng temporary queue, còn reply queue dùng chung cần correlation ID duy nhất và selector hoặc listener định tuyến. Độ tin cậy vẫn cần timeout, transaction, retry, idempotency và kiểm soát lifecycle destination.

## Tài liệu tham khảo

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.pdf)
- [Jakarta Messaging Message API](https://github.com/jakartaee/messaging/blob/master/api/src/main/java/jakarta/jms/Message.java)
- [Spring Framework 6.2: JmsHeaders Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/support/JmsHeaders.html)
- [Spring Framework 6.2: JmsTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Framework: Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Integration: JMS Support and Gateway Reply Correlation](https://docs.spring.io/spring-integration/reference/jms.html)