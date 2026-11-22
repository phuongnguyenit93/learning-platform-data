# Yêu cầu phản hồi bằng hàng đợi tạm thời hoặc hàng đợi cố định trong Spring JMS

## 1. Bài toán request-reply

Trong mô hình request-reply, một ứng dụng gửi yêu cầu tới JMS destination, một consumer xử lý yêu cầu rồi gửi kết quả về nơi nhận phản hồi. Mô hình này phù hợp khi caller cần nhận kết quả của một thao tác như tra cứu trạng thái đơn hàng, tính báo giá hoặc xác nhận một lệnh.

JMS cung cấp các thành phần nền tảng để xây dựng request-reply:

- **JMSReplyTo:** header chứa destination mà responder dùng để gửi response.
- **JMSCorrelationID:** header liên kết response với request tương ứng.
- **TemporaryQueue:** destination tạm có lifecycle gắn với connection tạo ra nó.
- **Fixed reply queue:** queue được provision và quản lý như một tài nguyên lâu dài.

Spring JMS hỗ trợ request-reply đồng bộ qua `JmsTemplate.sendAndReceive` và các biến thể convert. Các phương thức này tạo TemporaryQueue cho lần gọi. Khi ứng dụng cần một reply queue cố định dùng chung cho nhiều request, cần quản lý correlation và consumer phù hợp; Spring Integration JMS outbound gateway cung cấp cơ chế này ở mức cao hơn.

Hai lựa chọn có mục tiêu khác nhau:

- **TemporaryQueue** phù hợp với một lời gọi đồng bộ có thời gian chờ hữu hạn, caller đang hoạt động và không cần lưu response để truy vấn sau.
- **Fixed reply queue** phù hợp khi response cần đi qua một destination ổn định, có thể tồn tại khi caller tạm offline hoặc được nhiều request/instance dùng chung.

Sau bài học, bạn cần có thể:

- Giải thích vai trò của JMSReplyTo và JMSCorrelationID.
- Dùng JmsTemplate để gửi request và nhận response qua TemporaryQueue.
- Hiểu lifecycle và quyền truy cập của temporary destination.
- Thiết kế fixed reply queue có correlation an toàn.
- Dùng JMS selector để nhận đúng response.
- Phân biệt correlation bằng application ID với correlation bằng JMSMessageID.
- Kết hợp @JmsListener, giá trị trả về và @SendTo.
- Chọn JmsTemplate hoặc Spring Integration outbound gateway.
- Xử lý timeout, response đến muộn, duplicate, transaction và bảo mật destination.

## 2. Các thành phần của request-reply

### 2.1 Request destination

Request destination là queue hoặc topic nơi client gửi yêu cầu. Với request-reply đồng bộ, queue thường phù hợp vì một consumer trong nhóm xử lý request rồi trả một response cho caller.

| Destination | Vai trò |
|---|---|
| `orders.request` | Queue nhận yêu cầu tra cứu đơn hàng |
| `orders.reply` | Queue nhận phản hồi |
| `billing.request` | Queue nhận yêu cầu tính phí |
| `billing.reply` | Queue nhận kết quả tính phí |

Destination phải được broker provision hoặc provider cho phép tạo động. Tên destination không phải broker URL, clientID hay correlation ID.

### 2.2 JMSReplyTo

`JMSReplyTo` là header chuẩn có kiểu `jakarta.jms.Destination`. Producer đặt destination này vào request để responder biết nơi gửi response.

Giá trị có thể là TemporaryQueue hoặc một queue cố định đã được provision. Request không có JMSReplyTo có thể là một sự kiện một chiều hoặc một message mà sender không yêu cầu phản hồi.

Trong Spring JMS, listener method có thể trả về giá trị khác `void`. Spring đóng gói kết quả thành JMS Message rồi gửi tới destination trong JMSReplyTo của request. Nếu request không có header này, listener có thể dùng default response destination được cấu hình bằng `@SendTo` hoặc trên listener adapter.

`JMSReplyTo` là một Destination object do JMS provider quản lý. Không coi nó là một chuỗi queue name tùy ý được nhúng vào body.

### 2.3 JMSCorrelationID

`JMSCorrelationID` liên kết một message với message khác. Cách dùng phổ biến nhất là đặt correlation ID trên request rồi copy đúng giá trị đó sang response.

Có hai quy ước thường gặp:

1. **Application-generated ID:** caller sinh một ID duy nhất, đặt vào JMSCorrelationID của request. Responder copy ID đó vào JMSCorrelationID của response.
2. **Provider message ID:** provider gán JMSMessageID cho request. Responder đặt JMSCorrelationID của response bằng JMSMessageID của request.

Hai bên phải thống nhất một quy ước. Không để caller lọc theo application ID trong khi responder lại copy JMSMessageID.

JMSCorrelationID có thể chứa application-specific String hoặc provider message ID. Với String do ứng dụng tự đặt, không dùng prefix `ID:` vì prefix đó dành cho định danh message do provider tạo. Dạng byte[] provider-native không portable giữa các provider.

### 2.4 Luồng request-reply

~~~text
Client                         Responder
  |                                |
  | Request                        |
  | JMSReplyTo = reply destination |
  | Correlation = R-123             |
  |------------------------------->|
  |                                | xử lý request
  |                                |
  |<-------------------------------|
  | Response                       |
  | Correlation = R-123             |
  |                                |
  | kiểm tra correlation            |
  | hoàn tất request đang chờ       |
~~~

JMS cung cấp header và destination để xây dựng mô hình này. Việc quản lý request đang chờ, timeout, correlation registry và retry thuộc về ứng dụng hoặc framework tích hợp được sử dụng.

## 3. TemporaryQueue và lifecycle

### 3.1 TemporaryQueue là gì?

`TemporaryQueue` là destination tạm được tạo bằng JMS Session hoặc JMSContext. Nó thường được dùng làm nơi nhận response cho một request hoặc cho một gateway instance.

Các đặc điểm quan trọng:

- Được tạo lúc runtime, không cần khai báo như một queue lâu dài.
- Có lifecycle gắn với connection đã tạo nó.
- Khi connection tạo temporary destination đóng, destination tạm bị xóa và nội dung của nó không còn được giữ.
- Consumer đọc temporary destination phải được tạo trên cùng connection đã tạo destination.
- Responder có thể dùng JMSReplyTo nhận được trong request để gửi response tới temporary destination theo quyền và semantics của provider.
- TemporaryQueue không phải kho lưu kết quả lâu dài cho caller offline.

Không nhầm TemporaryQueue với một queue cố định có tên được sinh ngẫu nhiên. Queue thông thường có tên động vẫn là tài nguyên broker lâu dài cho tới khi được quản trị viên hoặc provider xóa. TemporaryQueue có lifecycle riêng theo JMS.

### 3.2 Khi nào TemporaryQueue phù hợp?

TemporaryQueue phù hợp khi:

- Caller cần kết quả ngay trong cùng một thao tác.
- Thời gian xử lý có giới hạn và caller có thể chờ.
- Mỗi request có một response destination riêng.
- Không cần giữ response sau khi caller đóng connection.
- Ứng dụng muốn tránh quản lý một reply queue dùng chung và selector cho từng request.

TemporaryQueue giúp giảm nguy cơ một caller lấy nhầm response của caller khác vì mỗi thao tác chờ trên destination riêng. Nó cũng giảm công việc provision queue lâu dài.

### 3.3 Giới hạn cần biết

TemporaryQueue có chi phí tạo destination và consumer. Nếu request volume rất cao, việc tạo một temporary destination cho mỗi request có thể tăng tải broker và churn tài nguyên.

TemporaryQueue không phù hợp nếu:

- Caller cần disconnect rồi reconnect để lấy response sau.
- Tác vụ có thể chạy lâu hơn timeout của caller.
- Response phải được lưu để đối soát hoặc truy vấn lại.
- Hệ thống cần một reply endpoint cố định để nhiều ứng dụng cùng sử dụng.
- Broker giới hạn số temporary destination hoặc hạn chế quyền gửi tới temporary destination của client khác.

Trong những trường hợp đó, hãy cân nhắc fixed reply queue, một reply listener dùng chung hoặc mô hình bất đồng bộ có result store.

## 4. JmsTemplate request-reply bằng TemporaryQueue

### 4.1 sendAndReceive

`JmsTemplate.sendAndReceive` gửi một request và chờ response. Trong Spring Framework 6.2, phương thức này tạo một TemporaryQueue, đặt queue vào JMSReplyTo của request rồi nhận response trên queue tạm đó.

Ví dụ dùng JMS Message trực tiếp:

~~~java
import jakarta.jms.Message;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.springframework.jms.core.JmsTemplate;

public class TemporaryReplyClient {

    private final JmsTemplate jmsTemplate;

    public TemporaryReplyClient(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
        this.jmsTemplate.setReceiveTimeout(5_000L);
    }

    public String lookup(String orderId) {
        Message reply = jmsTemplate.sendAndReceive(
                "orders.request",
                (Session session) -> session.createTextMessage(orderId)
        );

        if (reply == null) {
            return null;
        }

        try {
            return ((TextMessage) reply).getText();
        }
        catch (jakarta.jms.JMSException ex) {
            throw new IllegalStateException("Cannot read JMS reply", ex);
        }
    }
}
~~~

Đây là class service cần được inject JmsTemplate đã cấu hình ConnectionFactory hợp lệ. Phương thức trả về JMS Message hoặc null khi không có response trong thời gian chờ.

Overload nhận destination cho phép chỉ định queue request trực tiếp. Overload không nhận destination yêu cầu JmsTemplate đã có default destination.

### 4.2 convertSendAndReceive

Nếu ứng dụng muốn làm việc với object Java thay vì tự tạo JMS Message, dùng biến thể convert:

~~~java
import org.springframework.jms.core.JmsTemplate;

public class OrderRequestClient {

    private final JmsTemplate jmsTemplate;

    public OrderRequestClient(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
        this.jmsTemplate.setReceiveTimeout(5_000L);
    }

    public String getStatus(String orderId) {
        Object reply = jmsTemplate.convertSendAndReceive(
                "orders.request",
                orderId
        );

        if (reply == null) {
            return null;
        }

        return (String) reply;
    }
}
~~~

`convertSendAndReceive` dùng MessageConverter của JmsTemplate để chuyển request object thành JMS Message và chuyển response trở lại object Java. Với converter mặc định, String thường được ánh xạ thành TextMessage. Nếu request hoặc response là DTO, hãy cấu hình converter JSON hoặc converter phù hợp ở cả hai phía.

### 4.3 Listener trả về response

Một `@JmsListener` method có thể trả về giá trị khác `void`. Spring listener adapter chuyển giá trị đó thành JMS Message rồi gửi tới JMSReplyTo trong request.

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderRequestListener {

    @JmsListener(destination = "orders.request")
    public String handle(String orderId) {
        return "STATUS:" + orderId + ":READY";
    }
}
~~~

Khi request được gửi bằng JmsTemplate.sendAndReceive, JMSReplyTo đã trỏ tới TemporaryQueue do JmsTemplate tạo. Listener không cần hard-code tên reply queue.

Nếu listener method trả về `void`, Spring không có payload để tự động gửi reply. Nếu method trả về DTO, converter phải hỗ trợ DTO đó. Nếu converter không thể chuyển đổi response, thao tác gửi reply sẽ thất bại.

### 4.4 Timeout và cleanup

Có thể đặt `setReceiveTimeout` trên JmsTemplate để giới hạn thời gian chờ response. Khi hết timeout, thao tác request-reply có thể trả về null.

Timeout chỉ kết thúc việc caller chờ. Nó không hủy request đã được broker giao và không dừng method listener đang chạy. Server có thể tiếp tục xử lý sau khi caller đã timeout.

Trong sendAndReceive, Spring xóa TemporaryQueue khi thao tác hoàn tất, kể cả khi không nhận được response. Vì vậy response đến muộn có thể không còn destination hoặc consumer hợp lệ để nhận.

Nếu kết quả cần tồn tại sau timeout, disconnect hoặc restart, hãy dùng fixed reply queue hoặc lưu kết quả theo request ID trong một result store.

## 5. Cấu hình listener trả về response

### 5.1 JMSReplyTo được ưu tiên

Khi listener method có kiểu trả về khác void:

1. Nếu request có JMSReplyTo, Spring gửi response tới destination đó.
2. Nếu request không có JMSReplyTo, Spring dùng default response destination nếu đã cấu hình.
3. Nếu không có destination phù hợp, ứng dụng chưa có route hợp lệ để gửi response.

Có thể khai báo destination mặc định bằng `@SendTo`:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Component;

@Component
public class BillingListener {

    @JmsListener(destination = "billing.request")
    @SendTo("billing.reply")
    public String calculate(String accountId) {
        return "BILLING-STATUS:" + accountId;
    }
}
~~~

`@SendTo` cung cấp destination mặc định. Khi request có JMSReplyTo, destination do request chỉ định được dùng. Điều này cho phép cùng một listener phục vụ caller có reply destination khác nhau.

### 5.2 Trả Spring Message

Nếu response cần metadata, listener có thể trả về `org.springframework.messaging.Message<T>`:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.support.MessageBuilder;

@JmsListener(destination = "orders.request")
@SendTo("orders.reply")
public Message<String> handle(String orderId) {
    return MessageBuilder
            .withPayload("READY:" + orderId)
            .setHeader("app.responseCode", "OK")
            .setHeader("app.schemaVersion", 1)
            .build();
}
~~~

Spring Message cho phép bổ sung header ở tầng Spring. Adapter và header mapper quyết định cách ánh xạ metadata đó sang JMS properties. Nếu consumer cần một JMS property cụ thể cho selector, hãy kiểm tra header mapping thực tế.

### 5.3 Chọn destination động bằng JmsResponse

Nếu destination phụ thuộc vào nội dung request hoặc kết quả xử lý, có thể trả `JmsResponse<T>`:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.listener.adapter.JmsResponse;

@JmsListener(destination = "orders.request")
public JmsResponse<String> handle(OrderCommand command) {
    String response = process(command);
    String destination = resolveAllowedReplyQueue(command.region());

    return JmsResponse.forQueue(response, destination);
}
~~~

`JmsResponse.forQueue` đóng gói payload cùng queue đích. Có biến thể cho topic. Trong ứng dụng thật, `resolveAllowedReplyQueue` phải ánh xạ dữ liệu qua danh sách destination được cấu hình và kiểm soát; không nối trực tiếp chuỗi do client cung cấp thành tên queue.

## 6. Fixed reply queue

### 6.1 Đặc điểm

Fixed reply queue là queue lâu dài được provision và quản lý như một phần của topology messaging. Ví dụ `orders.reply` có thể là reply endpoint cho một ứng dụng hoặc một nhóm client.

Đặc điểm:

- Tồn tại qua nhiều lần restart của client theo lifecycle broker.
- Có thể lưu response khi caller tạm offline nếu message persistent, broker persistence và policy cho phép.
- Có thể được nhiều request đồng thời sử dụng.
- Cần correlation ID để caller nhận đúng response.
- Cần chính sách TTL, cleanup và xử lý response không còn request đang chờ.
- Cần ACL cho producer gửi response và consumer đọc reply.

Fixed queue không tự động bảo đảm response bền vững. Delivery mode, broker persistence, message expiration, quota và policy vẫn quyết định response có còn tồn tại sau restart hay không.

### 6.2 Khi nào nên dùng?

Dùng fixed reply queue khi:

- Caller cần nhận response sau khi reconnect.
- Response cần được lưu hoặc đối soát.
- Nhiều request dùng một reply endpoint ổn định.
- Nhiều client hoặc instance cần được quản lý tập trung.
- Ứng dụng có reply listener chạy lâu dài.
- Cần tách lifecycle của request và response.

Fixed queue có thể được cấp riêng cho từng client hoặc dùng chung. Nếu nhiều client dùng chung queue, correlation và authorization cần được thiết kế kỹ hơn.

## 7. Vì sao fixed reply queue cần correlation?

Giả sử hai request cùng đặt JMSReplyTo là `orders.reply`:

~~~text
Request A (correlation=A-101) ---+
                                 +----> orders.reply
Request B (correlation=B-202) ---+

Response B (correlation=B-202) --+
                                 +----> orders.reply
Response A (correlation=A-101) --+
~~~

Nếu caller A nhận message đầu tiên mà không kiểm tra correlation, nó có thể lấy response B. Kết quả nghiệp vụ sẽ bị ghép nhầm.

Correlation ID là khóa liên kết giữa request và response. Một giá trị cần duy nhất trong phạm vi các request có thể đồng thời chờ trên reply endpoint.

Có thể dùng JMS selector để consumer chỉ nhận response có correlation ID tương ứng. Selector đánh giá JMS headers và properties, không đọc trực tiếp JSON body hoặc DTO.

## 8. Fixed reply queue với JmsTemplate và selector

### 8.1 Quy ước application-generated correlation ID

Ví dụ client tạo ID bằng UUID, đặt vào JMSCorrelationID của request và dùng cùng ID để nhận response:

~~~java
import java.util.UUID;

import jakarta.jms.Queue;

import org.springframework.jms.core.JmsTemplate;

public class FixedReplyQueueClient {

    private final JmsTemplate jmsTemplate;
    private final Queue replyQueue;

    public FixedReplyQueueClient(
            JmsTemplate jmsTemplate,
            Queue replyQueue) {

        this.jmsTemplate = jmsTemplate;
        this.replyQueue = replyQueue;
        this.jmsTemplate.setReceiveTimeout(5_000L);
    }

    public String lookup(String orderId) {
        String correlationId = UUID.randomUUID().toString();

        jmsTemplate.convertAndSend(
                "orders.request",
                orderId,
                message -> {
                    message.setJMSReplyTo(replyQueue);
                    message.setJMSCorrelationID(correlationId);
                    return message;
                }
        );

        String selector =
                "JMSCorrelationID = '" + correlationId + "'";

        Object reply = jmsTemplate.receiveSelectedAndConvert(
                replyQueue,
                selector
        );

        return reply == null ? null : (String) reply;
    }
}
~~~

`replyQueue` là Queue bean đã được provision hoặc lookup từ provider. JmsTemplate cần ConnectionFactory có quyền gửi request và nhận response.

Luồng thực hiện:

1. Client sinh correlation ID duy nhất.
2. Request đặt JMSReplyTo thành fixed reply queue.
3. Request đặt JMSCorrelationID bằng ID đó.
4. JmsTemplate gửi request tới orders.request.
5. Client nhận trên replyQueue với selector chỉ khớp ID đang chờ.
6. Nếu hết timeout, kết quả nhận là null theo cấu hình receive timeout.

Ví dụ dùng UUID do ứng dụng sinh nên selector không chứa dữ liệu tùy ý từ người dùng. Nếu correlation ID có thể chứa dấu nháy đơn, cần escape đúng cú pháp JMS selector; tốt nhất dùng định dạng ID được ứng dụng kiểm soát.

### 8.2 Responder phải echo correlation

Khi request có JMSCorrelationID do ứng dụng tạo, response phải mang lại đúng giá trị đó.

Spring listener adapter xử lý giá trị trả về có hỗ trợ correlation cho response. Nếu tự tạo reply message bằng JMS API, hãy đặt header rõ ràng:

~~~java
TextMessage response = session.createTextMessage("READY");
response.setJMSCorrelationID(request.getJMSCorrelationID());
producer.send(request.getJMSReplyTo(), response);
~~~

Nếu dùng quy ước provider message ID, responder đặt JMSCorrelationID của response bằng JMSMessageID của request:

~~~java
response.setJMSCorrelationID(request.getJMSMessageID());
~~~

Producer, responder và caller phải dùng cùng một quy ước. Nếu provider được cấu hình tắt message ID, không dựa vào JMSMessageID; hãy dùng application-generated correlation ID.

### 8.3 Nhận response theo selector

Biểu thức selector ví dụ:

~~~sql
JMSCorrelationID = '550e8400-e29b-41d4-a716-446655440000'
~~~

Consumer chỉ nhận response có JMSCorrelationID khớp. Các response mang correlation khác vẫn ở queue để consumer phù hợp nhận sau, tùy provider và topology.

Cách nhận riêng từng request tạo consumer với selector tương ứng. Nó dễ triển khai ở tải vừa phải, nhưng khi có nhiều request đồng thời sẽ tăng số consumer, session và thread chờ. Reply đến sau khi caller timeout có thể còn nằm trong fixed queue mà không còn request nào chờ selector đó.

### 8.4 Một reply dispatcher cho nhiều request

Với lưu lượng lớn, có thể duy trì một reply listener container trên fixed queue. Listener nhận mọi response, đọc correlation ID rồi chuyển response tới request đang chờ trong một registry, ví dụ Map từ correlation ID tới CompletableFuture.

~~~text
Fixed reply queue
       |
       v
Một reply listener
       |
       v
Đọc JMSCorrelationID
       |
       v
Pending request registry
       |
       +---- correlation A -> Future A
       |
       +---- correlation B -> Future B
       |
       +---- correlation C -> Future C
~~~

Registry cần thread-safe. Khi request hoàn tất hoặc timeout, phải xóa entry. Response không có correlation hoặc không còn entry tương ứng cần được ghi nhận và xử lý theo policy, tránh làm rò rỉ bộ nhớ hoặc bỏ qua backlog.

Không tạo một future vô thời hạn cho mỗi request. Đặt timeout, giới hạn số request đang chờ và theo dõi response không ghép được.

## 9. Spring Integration JMS outbound gateway

Khi cần fixed reply queue và nhiều request đồng thời, Spring Integration JMS outbound gateway cung cấp cơ chế correlation và reply listener.

Các thuộc tính quan trọng:

- `request-destination`: destination nhận request.
- `reply-destination`: fixed destination nhận response.
- `correlation-key`: header/property dùng để ghép request và reply.
- `reply-listener`: listener container nhận response liên tục và chuyển tới request đang chờ.
- `receive-timeout`: thời gian chờ response.
- `reply-pub-sub-domain`: chọn topic domain cho reply khi cần.

Ví dụ XML:

~~~xml
<int-jms:outbound-gateway
        id="ordersGateway"
        request-destination="ordersRequestQueue"
        reply-destination="ordersReplyQueue"
        request-channel="ordersRequests"
        reply-channel="ordersReplies"
        correlation-key="JMSCorrelationID">

    <int-jms:reply-listener/>
</int-jms:outbound-gateway>
~~~

Đoạn cấu hình cần namespace Spring Integration JMS, dependency `spring-integration-jms`, ConnectionFactory và các bean destination/channel tương ứng.

### 9.1 Fixed reply queue không có reply-listener

Khi có reply-destination nhưng không có reply-listener:

- Gateway có thể tạo consumer cho từng request.
- Nếu không khai báo correlation-key, gateway dùng JMSMessageID của request làm selector.
- Responder phải đặt JMSCorrelationID của response bằng JMSMessageID của request.
- Nếu khai báo `correlation-key="JMSCorrelationID"`, gateway sinh correlation ID, đặt vào JMSCorrelationID của request và chờ response echo lại giá trị đó.
- Một correlation-key tùy chỉnh có thể dùng JMS property riêng; responder phải copy property đó về response theo cùng tên.

Đây là cách đơn giản để dùng fixed reply queue, nhưng số consumer có thể tăng theo số request đang chờ.

### 9.2 Fixed reply queue có reply-listener

Khi cấu hình reply-listener cùng fixed reply-destination, phải khai báo correlation-key để listener container có selector phân biệt các gateway/request.

Gateway tạo correlation value có namespace riêng cho gateway instance và sequence cho từng request. Reply listener nhận response rồi dispatch tới đúng request đang chờ. Responder phải echo nguyên giá trị correlation.

Nếu có reply-listener nhưng fixed reply destination không có correlation-key, cấu hình này không hợp lệ cho việc phân phối response an toàn; Spring Integration cảnh báo và bỏ qua reply-listener theo hành vi tài liệu mô tả.

### 9.3 TemporaryQueue với reply-listener

Nếu không khai báo fixed reply destination nhưng có reply-listener, Spring Integration có thể tạo một TemporaryQueue dùng chung cho gateway instance. Reply listener nhận các response trên queue đó và dùng thông tin nội bộ để chuyển tới thread đang chờ.

Điều này giảm việc tạo temporary consumer cho từng request. TemporaryQueue được tạo lại khi connection bị mất và được khôi phục theo lifecycle của gateway.

### 9.4 Cảnh báo về consumer cache

Kết hợp fixed reply destination với `CachingConnectionFactory` có `cacheConsumers=true` có thể giữ lại nhiều consumer sau khi request hoàn tất. Mỗi request có thể tạo selector duy nhất, làm cache tăng liên tục.

Khi dùng fixed reply queue:

- Ưu tiên reply-listener cho tải đồng thời cao.
- Không bật cache consumer nếu chưa đánh giá lifecycle selector.
- Theo dõi số consumer, số selector và memory.
- Kiểm thử tải với số request đồng thời gần production.

## 10. So sánh TemporaryQueue và fixed reply queue

| Tiêu chí | TemporaryQueue | Fixed reply queue |
|---|---|---|
| Tạo destination | Runtime, do JMS client tạo | Provision/cấu hình trước |
| Lifecycle | Gắn với connection tạo queue | Theo lifecycle broker/resource |
| Correlation | Thường không cần selector riêng cho từng request | Cần correlation khi chia sẻ queue |
| Consumer | JmsTemplate tạo consumer cho thao tác request-reply | Consumer selector hoặc reply listener |
| Caller offline | Không phù hợp để giữ reply sau khi connection đóng | Có thể giữ nếu persistent và broker policy cho phép |
| Cleanup | Spring/provider quản lý destination tạm | Ứng dụng/broker quản lý backlog và reply cũ |
| Request volume | Phù hợp thao tác đồng bộ ngắn | Phù hợp endpoint ổn định và nhiều request |
| Nhiều instance | Mỗi request/gateway có destination tạm riêng | Cần correlation namespace và dispatcher |
| Truy vấn lại | Không phù hợp | Có thể xây dựng cùng request/result store |
| Quản trị broker | Cần quyền tạo temporary destination | Cần provision, ACL, quota và expiry policy |

Không có lựa chọn phù hợp cho mọi workload. Hãy dựa vào thời gian xử lý, số request đồng thời, yêu cầu giữ response, khả năng broker và cách client reconnect.

## 11. Timeout, reply muộn và message tồn đọng

### 11.1 Timeout không hủy request

Khi JmsTemplate hoặc gateway hết receive timeout, caller chỉ ngừng chờ. Listener có thể vẫn đang xử lý request và có thể hoàn tất sau đó.

Không gửi một command mới chỉ vì caller không nhận response. Request đầu có thể đã được xử lý thành công. Dùng request ID hoặc idempotency key ổn định để server nhận diện retry của cùng thao tác logic.

### 11.2 Reply muộn trên TemporaryQueue

JmsTemplate xóa TemporaryQueue khi request-reply kết thúc. Nếu server gửi response sau timeout, destination có thể đã bị xóa hoặc không còn consumer. Vì vậy không dùng temporary reply queue làm kho kết quả cho tác vụ dài.

Nếu thời gian xử lý không dự đoán được, hãy gửi command bất đồng bộ, trả request ID và lưu trạng thái/kết quả ở một result store hoặc phát event kết quả.

### 11.3 Reply muộn trên fixed queue

Fixed queue có thể giữ response muộn sau khi caller timeout. Khi đó không còn request đang chờ correlation tương ứng. Message có thể tồn tại cho tới khi hết TTL hoặc được cleanup.

Nên:

- Đặt TTL cho response phù hợp với thời hạn nghiệp vụ.
- Theo dõi backlog và response không ghép được.
- Có chính sách xử lý reply cũ.
- Không ghép response cũ vào request mới.
- Xóa pending request registry khi timeout.

Nếu consumer selector không khớp một response cũ, message có thể tiếp tục nằm trên queue. Cần một quy trình vận hành để kiểm tra và dọn các message không còn người nhận.

### 11.4 Request TTL và reply TTL

Request TTL giới hạn thời gian request còn hiệu lực trong broker. Reply TTL giới hạn thời gian response còn hiệu lực. Hai giá trị độc lập.

Request hết hạn trước khi listener nhận có thể không tạo response. Response hết hạn trước khi caller nhận có thể làm caller timeout dù listener đã xử lý xong.

Thiết kế TTL dựa trên deadline đầu-cuối, thời gian xử lý và backlog dự kiến.

## 12. Transaction và độ tin cậy

Với listener chạy trong transacted JMS Session, việc nhận request và gửi response có thể nằm trong cùng JMS Session transaction theo cấu hình container/adapter. Nếu xử lý hoặc gửi response thất bại và exception thoát khỏi listener, transaction có thể rollback để broker redeliver request.

Cần xác minh transaction boundary thực tế:

- Response được gửi bằng cùng JMS Session/transaction hay bằng tài nguyên khác?
- Listener container có bật sessionTransacted hoặc transaction manager phù hợp không?
- Nếu gửi response thất bại, request có rollback không?
- Nếu database đã commit nhưng response send thất bại, retry có gây tác dụng phụ lặp không?
- Broker redelivery policy và DLQ đã được cấu hình chưa?

Local JMS transaction không tự bao gồm database hoặc HTTP service. Dùng idempotency, inbox/outbox hoặc XA khi yêu cầu nhất quán cần thiết.

Với fixed reply queue, persistent delivery và broker persistence có thể giúp giữ response khi caller tạm offline. Tuy nhiên, persistence không thay thế correlation, TTL, transaction hoặc quyền truy cập.

## 13. Bảo mật reply destination

JMSReplyTo có thể do client gửi request cung cấp. Vì vậy listener không nên tin mọi destination trong header.

Cần kiểm tra:

- Broker ACL có giới hạn quyền gửi tới reply destination không?
- Ứng dụng có chỉ cho phép destination nằm trong phạm vi được cấu hình không?
- Caller có quyền đọc fixed reply queue của nó không?
- Nhiều tenant có dùng chung reply queue mà thiếu phân tách correlation/authorization không?
- Destination động có được tạo từ input không đáng tin cậy không?
- Response có chứa dữ liệu mà caller không được phép đọc không?

Nếu dùng destination theo tenant/client, hãy ánh xạ ID sang Destination từ cấu hình đã kiểm soát. Không nối trực tiếp chuỗi do request cung cấp thành queue name.

Correlation ID chỉ liên kết request và response. Nó không phải token xác thực và không chứng minh caller có quyền đọc response.

## 14. Chọn mô hình theo tình huống

| Tình huống | Lựa chọn phù hợp |
|---|---|
| Một lời gọi đồng bộ ngắn, caller đang hoạt động | JmsTemplate với TemporaryQueue |
| Muốn gửi và chờ response bằng API đơn giản | sendAndReceive hoặc convertSendAndReceive |
| Reply cần tồn tại khi caller offline | Fixed reply queue với persistent delivery và TTL |
| Nhiều request đồng thời dùng một reply queue | Correlation ID + selector |
| Nhiều request đồng thời với tải cao | Spring Integration outbound gateway và reply-listener |
| Mỗi client có reply endpoint riêng | Fixed queue riêng, vẫn dùng correlation |
| Nhiều instance cùng dùng một reply queue | Correlation namespace và reply dispatcher |
| Tác vụ dài hoặc không có deadline đồng bộ | Async command + request ID + result store/event |
| Cần truy vấn kết quả sau restart | Fixed queue hoặc result store có thể truy vấn |

## 15. Kiểm thử request-reply

Nên kiểm thử với JMS provider/broker mục tiêu. Unit test cho service không đủ để xác minh lifecycle temporary destination, selector và reply dispatch.

Các tình huống quan trọng:

1. JmsTemplate.sendAndReceive tạo TemporaryQueue và nhận được response.
2. Request có JMSReplyTo trỏ tới destination mong muốn.
3. Listener trả về String và adapter gửi response tới JMSReplyTo.
4. Listener dùng @SendTo khi request không có JMSReplyTo.
5. Request có JMSReplyTo được ưu tiên so với default @SendTo.
6. Converter chuyển DTO request và response đúng schema.
7. Timeout trả null hoặc lỗi timeout theo API/gateway đã cấu hình.
8. TemporaryQueue được dọn khi request-reply kết thúc.
9. Fixed reply queue nhận response có correlation ID chính xác.
10. Hai request đồng thời không nhận nhầm response.
11. Selector không nhận response có correlation khác.
12. Provider message ID bị tắt không làm hỏng quy ước correlation nếu dùng JMSMessageID.
13. Reply đến muộn được xử lý theo TTL và cleanup policy.
14. Listener lỗi hoặc reply send lỗi có transaction outcome đúng.
15. Unauthorized reply destination bị broker hoặc ứng dụng từ chối.
16. Reply listener của Spring Integration dispatch đúng response khi nhiều request đồng thời.
17. Broker restart không làm mất response cần giữ theo persistence policy.

Dùng latch, future hoặc Awaitility để chờ kết quả với timeout rõ ràng. Tránh sleep cố định và không yêu cầu broker giao message đúng một millisecond cụ thể.

## 16. Lỗi thường gặp

- **Nghĩ sendAndReceive dùng fixed reply queue:** JmsTemplate request-reply cơ bản tạo TemporaryQueue.
- **Không đặt JMSReplyTo:** listener không biết gửi response tới đâu nếu không có default destination.
- **Nhầm JMSReplyTo với request destination:** một header xác định nơi trả lời, một destination xác định nơi nhận request.
- **Dùng fixed reply queue mà không correlation:** response có thể bị ghép nhầm request.
- **Responder không echo correlation:** selector của caller không tìm được response.
- **Không thống nhất JMSMessageID và JMSCorrelationID:** request và response không khớp hợp đồng.
- **Dựa vào JMSMessageID khi provider tắt message ID:** caller không có giá trị ổn định để tạo correlation.
- **Tạo selector từ dữ liệu tùy ý:** có thể sai cú pháp hoặc tạo rủi ro injection.
- **Dùng topic làm fixed reply destination cho consumer nhận một lần:** publication có thể bị mất nếu không có subscription phù hợp.
- **Tạo consumer cho mọi request ở tải rất cao:** tăng session/consumer churn; cân nhắc reply listener.
- **Bật cacheConsumers với selector duy nhất mà không kiểm soát:** có thể làm cache consumer tăng liên tục.
- **Không xử lý reply muộn:** fixed queue có thể tích tụ response không còn request chờ.
- **Cho rằng timeout hủy server processing:** caller timeout không tự dừng listener.
- **Cho rằng fixed queue luôn bền vững:** còn phụ thuộc delivery mode và broker persistence.
- **Cho rằng TemporaryQueue tồn tại sau khi connection đóng:** destination tạm có lifecycle gắn với connection tạo nó.
- **Không kiểm tra quyền reply destination:** listener có thể bị yêu cầu gửi dữ liệu tới nơi không được phép.
- **Không kiểm thử broker thật:** temporary destination, selector, ACL và transaction có thể khác theo provider.

## 17. Checklist thiết kế

Trước khi chọn TemporaryQueue hay fixed reply queue, hãy xác nhận:

- Request-reply có thực sự cần đồng bộ hay có thể xử lý bất đồng bộ?
- Caller cần chờ tối đa bao lâu?
- JmsTemplate TemporaryQueue có đáp ứng được lifecycle không?
- Reply có cần tồn tại sau khi caller disconnect hoặc restart không?
- Fixed reply queue đã được provision và cấp ACL chưa?
- Mỗi request có correlation ID duy nhất chưa?
- Responder có echo correlation theo đúng hợp đồng không?
- Selector có dùng JMS header/property đúng kiểu không?
- Có nhiều request đồng thời và nhiều application instance không?
- Có cần Spring Integration reply listener hoặc dispatcher chuyên dụng không?
- Receive timeout, request TTL và reply TTL có phù hợp không?
- Reply muộn và message không còn pending được cleanup thế nào?
- Transaction có bao phủ receive và reply send theo yêu cầu không?
- Có idempotency cho retry và redelivery không?
- Có integration test cho timeout, correlation, broker restart và quyền truy cập không?

Khi chọn đúng reply destination và thiết kế correlation nhất quán, Spring JMS có thể hỗ trợ request-reply từ thao tác đơn giản bằng TemporaryQueue tới mô hình fixed reply queue có nhiều request đồng thời. TemporaryQueue giảm công việc quản lý destination cho lời gọi ngắn; fixed reply queue cung cấp một endpoint ổn định nhưng đòi hỏi quản lý correlation, consumer, backlog và lifecycle rõ ràng.

## 18. Tài liệu tham khảo

- [Spring Framework 6.2 — Using Spring JMS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html)
- [Spring Framework 6.2 — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html)
- [JmsTemplate — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html)
- [Spring Integration 6.2 — JMS Support and Outbound Gateway](https://docs.spring.io/spring-integration/reference/6.2/jms.html)
- [Jakarta Messaging 3.1 Specification — Request/reply and message headers](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)