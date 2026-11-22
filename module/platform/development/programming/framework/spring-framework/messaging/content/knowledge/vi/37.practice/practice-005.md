# Xây dựng trao đổi yêu cầu phản hồi JMS có thời gian chờ

## 1. Request/reply trong JMS là gì?

JMS chủ yếu được dùng để gửi message bất đồng bộ, nhưng giao thức cũng hỗ trợ mô hình **request/reply**: một phía gửi yêu cầu tới destination, phía nhận xử lý rồi gửi một message phản hồi về destination do bên gọi chỉ định.

Một request/reply thường có các thành phần:

- **Request destination:** queue nhận yêu cầu.
- **Request message:** payload và metadata mô tả thao tác cần thực hiện.
- **JMSReplyTo:** header chứa destination mà bên xử lý phải dùng để gửi phản hồi.
- **Reply message:** kết quả trả về.
- **JMSCorrelationID:** header giúp liên kết reply với request tương ứng.
- **Timeout:** khoảng thời gian tối đa caller chờ reply trước khi kết luận chưa nhận được phản hồi.

Ví dụ tra cứu giá:

~~~text
Pricing Client
     |
     | 1. Request: "SKU-100"
     |    JMSReplyTo = temporary reply queue
     v
orders/pricing.request
     |
     v
Pricing Service
     |
     | 2. Xử lý yêu cầu
     | 3. Reply: "SKU-100 costs 120000 VND"
     v
Temporary reply queue
     |
     | 4. Caller nhận reply hoặc hết timeout
     v
Pricing Client
~~~

Request/reply phù hợp khi caller cần kết quả để tiếp tục một thao tác và thời gian xử lý có giới hạn. Nếu công việc kéo dài, có nhiều bước hoặc không cần phản hồi ngay, command bất đồng bộ kết hợp event/notification thường phù hợp hơn.

## 2. Các header JMS quyết định luồng phản hồi

### 2.1. JMSReplyTo

`JMSReplyTo` là header chuẩn của Jakarta Messaging. Requester gắn một `Destination` vào header này khi gửi request. Responder đọc header và gửi reply tới destination được chỉ định.

Nếu `JMSReplyTo` là `null`, message có thể chỉ là notification hoặc dữ liệu một chiều; responder không có destination được chỉ định để trả lời.

`JMSReplyTo` có thể là queue hoặc topic. Với mô hình một request tạo một reply, queue thường dễ kiểm soát hơn vì message được chuyển tới một consumer nhận duy nhất. Nếu cần nhiều phản hồi hoặc broadcast, đó là một giao thức khác cần thiết kế riêng.

### 2.2. JMSCorrelationID

`JMSCorrelationID` liên kết reply với request. Có hai quy ước phổ biến:

1. **Dùng JMSMessageID của request:** provider cấp `JMSMessageID` khi gửi request; responder đặt giá trị đó vào `JMSCorrelationID` của reply.
2. **Dùng application correlation ID:** requester tự đặt một ID duy nhất trong `JMSCorrelationID` của request; responder sao chép nguyên giá trị sang reply.

Ví dụ:

~~~text
Request:
  JMSMessageID     = ID:broker-12345
  JMSCorrelationID = null
  JMSReplyTo       = temp-queue-42

Reply:
  JMSMessageID     = ID:broker-67890
  JMSCorrelationID = ID:broker-12345
  JMSReplyTo       = null
~~~

Nếu dùng application correlation ID, giá trị là chuỗi do ứng dụng tạo. Theo đặc tả JMS, chuỗi application-specified không được bắt đầu bằng tiền tố `ID:`, vì tiền tố đó được dành cho provider-generated message ID.

Không nhầm `JMSMessageID` với `JMSCorrelationID`: message ID định danh message do broker gửi; correlation ID chỉ ra message nào có quan hệ với message hiện tại.

### 2.3. Quy tắc khi dùng reply queue dùng chung

Khi nhiều request dùng chung một reply queue, chỉ có `JMSReplyTo` là chưa đủ. Các reply có thể đến xen kẽ, vì vậy requester cần lọc theo correlation ID hoặc một cơ chế dispatcher tương đương.

Ví dụ quy ước:

- Requester tạo correlation ID duy nhất cho từng request.
- Requester gửi request với correlation ID đó.
- Responder sao chép correlation ID vào reply.
- Reply listener nhận message và chuyển tới đúng future/callback đang chờ ID tương ứng.

Không dùng một consumer không có selector cho mỗi request trên cùng reply queue nếu các consumer có thể nhận nhầm reply của nhau. Với nhiều request đồng thời, nên có một reply listener dùng chung và bảng correlation ID tới đối tượng đang chờ phản hồi, hoặc dùng một cơ chế gateway đã quản lý việc này.

## 3. Temporary reply queue và shared reply queue

### 3.1. Temporary queue cho từng request

Jakarta Messaging cho phép tạo `TemporaryQueue` trong thời gian tồn tại của connection tạo ra nó. Chỉ consumer được tạo trên connection sở hữu temporary destination mới có thể nhận message từ queue đó; producer trên connection khác vẫn có thể gửi tới destination này.

Cách này phù hợp với request/reply đơn giản:

1. Requester tạo temporary queue.
2. Requester gắn queue vào `JMSReplyTo`.
3. Requester gửi request.
4. Responder gửi reply tới `JMSReplyTo`.
5. Requester nhận reply từ temporary queue.
6. Temporary destination được giải phóng khi connection sở hữu nó đóng; Spring cũng quản lý việc tạo và dọn tài nguyên cho thao tác request/reply của template.

Ưu điểm:

- Mỗi request có destination reply riêng, không phải lọc reply của request khác.
- Dễ dùng, ít cấu hình.
- Không cần quản lý một reply listener và bảng correlation ID dùng chung.

Hạn chế:

- Tạo temporary destination cho mỗi request có thể tốn tài nguyên và thêm thao tác với broker.
- Broker/provider có thể giới hạn hoặc không cho phép temporary destination trong một số môi trường.
- Không phù hợp khi có lưu lượng request/reply rất lớn hoặc cần reply listener tồn tại lâu dài.

### 3.2. Queue phản hồi dùng chung

Trong hệ thống có lưu lượng cao, có thể dùng một reply queue cố định cho mỗi ứng dụng hoặc mỗi instance. Reply listener nhận tất cả phản hồi và dispatch theo correlation ID.

Cần thiết kế rõ:

- ID phải duy nhất trên phạm vi các requester có thể cùng nhận reply.
- Mỗi reply phải mang đúng correlation ID của request gốc.
- Reply listener phải xử lý reply đến muộn, reply trùng và ID không còn pending.
- Khi request timeout, phải xóa entry tương ứng khỏi bảng pending.
- Nếu nhiều instance cùng đọc một queue, cần tránh việc instance A nhận reply dành cho instance B. Có thể dùng queue riêng theo instance, selector theo namespace correlation, hoặc một reply gateway tập trung.

Không để mỗi caller tự tạo consumer trên một shared reply queue mà không có selector; consumer cạnh tranh sẽ lấy message của nhau.

### 3.3. Chọn mô hình nào?

| Tiêu chí | Temporary reply queue | Shared reply queue |
|---|---|---|
| Cấu hình | Đơn giản | Phức tạp hơn |
| Cô lập reply | Tự nhiên theo destination | Cần correlation/dispatch |
| Tài nguyên broker | Có thể tạo queue cho từng request | Một số queue/listener dùng lâu dài |
| Lưu lượng cao | Cần đo chi phí tạo temporary destination | Phù hợp khi có reply dispatcher tốt |
| Quản lý timeout | Caller chờ trực tiếp | Phải dọn pending correlation entry |
| Nhiều instance | Mỗi request có queue riêng | Cần định tuyến reply đúng instance |

Bắt đầu với temporary reply queue khi lưu lượng vừa phải và request/reply đơn giản. Chỉ chuyển sang shared reply queue khi có số liệu cho thấy chi phí temporary destination đáng kể hoặc cần kiến trúc reply listener dùng chung.

## 4. Spring JMS hỗ trợ request/reply như thế nào?

Spring cung cấp nhiều mức API:

| API | Vai trò | Giá trị trả về khi timeout |
|---|---|---|
| `JmsTemplate.sendAndReceive` | Gửi JMS Message và nhận JMS Message | `null` |
| `JmsMessagingTemplate.convertSendAndReceive` | Chuyển đổi payload/Message và nhận payload kiểu đích | `null` |
| `JmsClient` (Spring 7+) | Fluent API, có timeout theo từng operation | `Optional.empty()` |

`JmsTemplate` quản lý việc tạo/release connection, session, producer, consumer và temporary reply queue. Với request/reply cơ bản, template tự tạo temporary queue và gắn nó vào `JMSReplyTo` của request.

`JmsMessagingTemplate` xây trên `JmsTemplate` và bổ sung abstraction của Spring Messaging cùng khả năng convert payload. `JmsClient` có từ Spring Framework 7.0, cung cấp fluent API và các tùy chọn theo từng operation.

**Phân biệt API:** `JmsTemplate` có `sendAndReceive`; API typed `convertSendAndReceive` thuộc `JmsMessagingTemplate`. Spring 7 có thêm `JmsClient.sendAndReceive` với payload và target class.

## 5. Cấu hình timeout

### 5.1. JmsTemplate.setReceiveTimeout

`JmsTemplate.setReceiveTimeout(long)` cấu hình thời gian chờ cho các thao tác nhận message, tính bằng mili giây. `sendAndReceive` sử dụng giá trị này khi chờ reply.

Ví dụ:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@Bean
JmsTemplate requestReplyJmsTemplate(ConnectionFactory connectionFactory) {
    JmsTemplate template = new JmsTemplate(connectionFactory);
    template.setReceiveTimeout(2_000L);
    return template;
}
~~~

Các giá trị có ý nghĩa:

| Giá trị | Hành vi |
|---|---|
| Số dương, ví dụ `2000` | Chờ tối đa 2.000 mili giây |
| `0` | Chờ vô thời hạn |
| Số âm | Kiểm tra message có sẵn ngay lập tức, không chờ |

Mặc định của `JmsTemplate` là `RECEIVE_TIMEOUT_INDEFINITE_WAIT`. Vì vậy, nếu không cấu hình timeout, một thao tác nhận hoặc request/reply có thể giữ thread chờ vô hạn.

Timeout phải là số dương trong request/reply phục vụ HTTP hoặc thao tác tương tác có SLA. Không dùng giá trị mặc định vô thời hạn cho request path mà caller cần trả kết quả trong một khoảng thời gian hữu hạn.

### 5.2. Timeout theo từng operation với JmsClient

Từ Spring Framework 7.0, `JmsClient.OperationSpec.withReceiveTimeout(long)` cho phép đặt timeout riêng cho từng operation:

~~~java
import java.util.Optional;

import org.springframework.jms.core.JmsClient;

public class PricingClient {

    private final JmsClient jmsClient;

    public PricingClient(JmsClient jmsClient) {
        this.jmsClient = jmsClient;
    }

    public String quote(String sku) {
        Optional<String> reply = jmsClient
            .destination("pricing.request")
            .withReceiveTimeout(2_000L)
            .sendAndReceive(sku, String.class);

        return reply.orElseThrow(
            () -> new IllegalStateException("Pricing reply timed out"));
    }
}
~~~

`withReceiveTimeout` chỉ áp dụng cho các thao tác nhận tiếp theo trên operation handle đó. Kết quả `Optional.empty()` có nghĩa không nhận được reply trong thời gian chờ; lỗi kết nối hoặc lỗi gửi message vẫn được ném dưới dạng `MessagingException`.

Có thể tạo `JmsClient` từ `ConnectionFactory` hoặc từ một `JmsTemplate` đã cấu hình:

~~~java
@Bean
JmsClient jmsClient(ConnectionFactory connectionFactory) {
    return JmsClient.create(connectionFactory);
}
~~~

Nếu cần dùng chung cấu hình connection, converter hoặc các thuộc tính template hiện có, có thể tạo client từ `JmsTemplate`:

~~~java
@Bean
JmsClient jmsClient(JmsTemplate jmsTemplate) {
    return JmsClient.create(jmsTemplate);
}
~~~

### 5.3. Timeout không phải message TTL

Hai khái niệm này có mục đích khác nhau:

- **Receive timeout:** caller chờ reply trong bao lâu.
- **Message Time-To-Live (TTL):** broker được phép giữ request để giao trong bao lâu trước khi message hết hạn.

Ví dụ caller chờ 2 giây nhưng request vẫn có thể còn trong queue và được xử lý sau đó. Nếu muốn request hết hạn ở broker, cần đặt TTL riêng qua cấu hình QoS hoặc `JmsClient.withTimeToLive`.

Với `JmsTemplate`, `setTimeToLive` chỉ được áp dụng theo cấu hình QoS khi `explicitQosEnabled` được bật. Không giả định `setReceiveTimeout` tự đặt message expiration.

### 5.4. Timeout không hủy xử lý ở responder

Khi requester hết thời gian chờ, request có thể đã:

- Chưa được broker giao tới responder.
- Đang nằm trong queue.
- Đã được responder nhận và đang xử lý.
- Đã hoàn tất, nhưng reply đang chậm hoặc bị mất.
- Đã gửi reply nhưng caller không nhận được trước deadline.

Do đó, timeout chỉ cho biết caller chưa nhận được reply đúng hạn. Nó không chứng minh nghiệp vụ thất bại và cũng không hủy công việc ở phía responder.

Nếu thao tác có side effect, hãy dùng request ID/idempotency key để retry an toàn. Khi timeout, caller có thể truy vấn trạng thái bằng request ID thay vì gửi lại một command có thể tạo side effect lần nữa.

## 6. Ví dụ hoàn chỉnh với Spring Framework 6.2

Ví dụ dưới đây dùng chuỗi văn bản để giữ payload đơn giản và sử dụng `JmsMessagingTemplate` cho request/reply có chuyển đổi payload.

### 6.1. Cấu hình template và listener

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.core.JmsMessagingTemplate;

@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    JmsTemplate requestReplyJmsTemplate(
            ConnectionFactory connectionFactory) {

        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setReceiveTimeout(2_000L);
        return template;
    }

    @Bean
    JmsMessagingTemplate jmsMessagingTemplate(
            JmsTemplate requestReplyJmsTemplate) {

        return new JmsMessagingTemplate(requestReplyJmsTemplate);
    }
}
~~~

Nếu ứng dụng dùng Spring Boot và đã có `JmsTemplate` auto-configured, hãy cấu hình timeout trên template được dùng thực tế hoặc tạo bean riêng cho request/reply. Tránh tạo nhiều template với timeout không rõ ràng rồi inject nhầm bean.

### 6.2. Requester

~~~java
import org.springframework.jms.core.JmsMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class PricingRequestClient {

    private final JmsMessagingTemplate jmsMessagingTemplate;

    public PricingRequestClient(JmsMessagingTemplate jmsMessagingTemplate) {
        this.jmsMessagingTemplate = jmsMessagingTemplate;
    }

    public String quote(String sku) {
        String reply = jmsMessagingTemplate.convertSendAndReceive(
            "pricing.request",
            sku,
            String.class
        );

        if (reply == null) {
            throw new IllegalStateException(
                "No pricing reply received within 2000 ms");
        }

        return reply;
    }
}
~~~

`convertSendAndReceive` chuyển request thành JMS message, gửi tới `pricing.request`, nhận reply và chuyển body thành `String`. Nếu không nhận được message trước timeout của underlying `JmsTemplate`, kết quả là `null`.

### 6.3. Responder với @JmsListener

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class PricingRequestListener {

    @JmsListener(destination = "pricing.request")
    public String handle(String sku) {
        if (sku == null || sku.isBlank()) {
            return "ERROR: sku is required";
        }

        return "PRICE:" + sku + ":120000";
    }
}
~~~

Khi method listener trả về giá trị khác `void`, Spring chuyển kết quả thành JMS message và gửi về destination trong `JMSReplyTo` của request. Với request do `JmsTemplate.sendAndReceive` hoặc `JmsMessagingTemplate.convertSendAndReceive` tạo, `JMSReplyTo` trỏ tới temporary reply queue.

Không cần khai báo `@SendTo` cho ví dụ này. `@SendTo` dùng để chỉ định default reply destination trong trường hợp request không mang `JMSReplyTo` hoặc khi ứng dụng cần một destination mặc định.

### 6.4. Luồng xử lý

1. `PricingRequestClient` gửi SKU tới `pricing.request`.
2. Spring tạo temporary reply queue và gắn vào `JMSReplyTo`.
3. Listener nhận request, gọi xử lý nghiệp vụ và trả về kết quả.
4. Spring gửi reply tới `JMSReplyTo`.
5. Requester nhận reply và trả kết quả cho caller.
6. Nếu không có reply trong 2 giây, requester nhận `null` và chuyển thành timeout theo chính sách ứng dụng.

Các class trên là những thành phần trong một ứng dụng Spring có `ConnectionFactory` trỏ tới broker JMS đang chạy. Chúng cần được đặt trong project có dependency Spring JMS, Jakarta Messaging và cấu hình broker tương ứng; không phải chương trình Java độc lập chỉ có JDK.

## 7. Ví dụ Spring Framework 7 với JmsClient

`JmsClient` giảm phần cấu hình typed request/reply xuống một operation:

~~~java
import java.util.Optional;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsClient;

@Configuration
public class JmsClientConfiguration {

    @Bean
    JmsClient jmsClient(ConnectionFactory connectionFactory) {
        return JmsClient.create(connectionFactory);
    }
}
~~~

Requester:

~~~java
import java.util.Optional;

import org.springframework.jms.core.JmsClient;
import org.springframework.stereotype.Service;

@Service
public class PricingClient {

    private final JmsClient jmsClient;

    public PricingClient(JmsClient jmsClient) {
        this.jmsClient = jmsClient;
    }

    public String quote(String sku) {
        Optional<String> reply = jmsClient
            .destination("pricing.request")
            .withReceiveTimeout(2_000L)
            .sendAndReceive(sku, String.class);

        return reply.orElseThrow(
            () -> new IllegalStateException("Pricing request timed out"));
    }
}
~~~

`JmsClient` dùng Spring Messaging converter mặc định hoặc converter được cấu hình qua client/template. Nếu payload là DTO phức tạp, hãy cấu hình converter/schema rõ ràng thay vì giả định mọi object đều được serialize thành JSON.

## 8. Dùng JmsTemplate trực tiếp khi cần JMS Message

`JmsTemplate.sendAndReceive` hữu ích khi cần tạo message và thao tác header/property trực tiếp:

~~~java
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class RawPricingClient {

    private final JmsTemplate jmsTemplate;

    public RawPricingClient(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public String quote(String sku) {
        Message reply = jmsTemplate.sendAndReceive(
            "pricing.request",
            session -> session.createTextMessage(sku)
        );

        if (reply == null) {
            throw new IllegalStateException("Pricing reply timed out");
        }

        if (!(reply instanceof TextMessage textMessage)) {
            throw new IllegalStateException("Unexpected JMS reply type");
        }

        try {
            return textMessage.getText();
        }
        catch (jakarta.jms.JMSException ex) {
            throw new IllegalStateException("Cannot read JMS reply", ex);
        }
    }
}
~~~

`sendAndReceive` nhận một `MessageCreator` để tạo request message từ `Session`. Spring tạo temporary reply queue, gắn nó vào `JMSReplyTo`, gửi request và chờ reply theo `receiveTimeout` đã cấu hình.

`JmsTemplate` trả về raw `jakarta.jms.Message`; caller tự kiểm tra kiểu message và đọc payload. Nếu chỉ cần payload đã convert, `JmsMessagingTemplate` hoặc `JmsClient` thường gọn hơn.

## 9. Responder tự tạo reply bằng JMS API

Khi listener cần kiểm soát message header, destination hoặc QoS, có thể nhận raw JMS message và session rồi gửi reply thủ công.

~~~java
import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class ManualReplyListener {

    @JmsListener(destination = "pricing.request")
    public void handle(TextMessage request, Session session)
            throws JMSException {

        Destination replyTo = request.getJMSReplyTo();
        if (replyTo == null) {
            return;
        }

        TextMessage reply = session.createTextMessage(
            "PRICE:SKU-100:120000"
        );

        String requestMessageId = request.getJMSMessageID();
        if (requestMessageId != null) {
            reply.setJMSCorrelationID(requestMessageId);
        }

        MessageProducer producer = session.createProducer(replyTo);
        try {
            producer.send(reply);
        }
        finally {
            producer.close();
        }
    }
}
~~~

Ví dụ này minh họa giao thức ở mức JMS. Trong ứng dụng thực tế, payload reply cần được tính từ request; không hard-code dữ liệu nghiệp vụ như ví dụ minh họa.

Spring hỗ trợ inject raw `jakarta.jms.Message` và `jakarta.jms.Session` vào method `@JmsListener`. Với listener method trả về non-void, Spring đã tự xử lý phần lớn logic tạo và gửi reply; chỉ dùng cách thủ công khi cần kiểm soát sâu.

## 10. Dùng reply queue cố định và correlation ID

Khi cần một reply queue dùng chung, requester và responder phải tuân theo cùng một correlation contract.

### 10.1. Mô hình request message

~~~text
Request:
  Destination      = orders.request
  JMSCorrelationID = req-7d2f
  JMSReplyTo       = orders.reply

Reply:
  Destination      = orders.reply
  JMSCorrelationID = req-7d2f
~~~

Requester tạo correlation ID đủ duy nhất, đặt vào request. Responder sao chép giá trị đó sang reply. Reply listener sử dụng correlation ID để tìm đúng request đang chờ.

Nếu dùng `JMSMessageID` thay cho application correlation ID, responder cần đọc message ID của request rồi đặt nó vào `JMSCorrelationID` của reply. Đây là quy ước phổ biến và được Spring `MessageListenerAdapter` hỗ trợ khi gửi response.

### 10.2. Không nhận reply bằng một consumer không lọc

Giả sử có ba request đang chờ cùng trên `orders.reply`:

| Request | Correlation ID |
|---|---|
| R1 | req-A |
| R2 | req-B |
| R3 | req-C |

Reply có thể đến theo thứ tự R3, R1, R2. Nếu mỗi caller tự tạo một consumer trên cùng queue mà không selector, một caller có thể lấy reply của caller khác.

Một reply listener dùng chung có thể dispatch:

~~~text
orders.reply
    |
    v
Reply Listener
    |
    +-- req-A -> Future R1
    +-- req-B -> Future R2
    +-- req-C -> Future R3
~~~

Khi timeout, phải xóa correlation entry khỏi bảng pending. Nếu không, map sẽ giữ các future đã hết hạn và tăng bộ nhớ theo thời gian. Reply đến muộn cần được ghi nhận hoặc bỏ qua theo chính sách, không được giao nhầm cho request mới.

### 10.3. Khi nào dùng Spring Integration JMS Gateway?

Nếu ứng dụng cần shared reply queue, reply listener lâu dài, correlation mapping, timeout và quản lý nhiều request đồng thời, Spring Integration JMS Gateway có thể phù hợp hơn việc tự viết dispatcher.

Gateway hỗ trợ các chiến lược temporary queue, fixed reply destination, reply listener và correlation key. Cần cấu hình nhất quán giữa producer và responder, đồng thời kiểm tra hành vi với broker thực tế.

## 11. Xử lý timeout đúng cách

### 11.1. Phân biệt timeout và lỗi gửi

Có hai nhóm kết quả khác nhau:

| Kết quả | Ý nghĩa | Cách xử lý |
|---|---|---|
| Reply nhận được | Responder đã trả lời | Validate response và tiếp tục |
| Timeout, trả null/Optional.empty | Không nhận reply trong thời gian chờ | Trả timeout hoặc tra cứu trạng thái |
| JMS/Messaging exception | Gửi, kết nối, conversion hoặc receive gặp lỗi | Phân loại lỗi và áp dụng retry/fallback |
| Reply sai correlation | Reply không thuộc request hiện tại | Ghi log, quarantine hoặc bỏ qua theo policy |
| Reply payload sai schema | Không thể chuyển đổi/validate kết quả | Xử lý lỗi contract, không coi là timeout |

Timeout thường chỉ giới hạn giai đoạn chờ reply. Nếu broker không thể kết nối hoặc gửi request thất bại, Spring ném exception thay vì trả null như trường hợp không có reply.

### 11.2. Không retry mù quáng

Giả sử caller gửi `CreatePayment` nhưng timeout sau 2 giây. Payment Service có thể đã tạo payment thành công và chỉ bị chậm khi gửi reply. Nếu caller gửi lại một command mới, payment thứ hai có thể được tạo.

Giải pháp:

- Đưa `requestId` hoặc `idempotencyKey` vào payload.
- Lưu kết quả xử lý theo key ở phía responder.
- Nếu nhận lại cùng key, trả kết quả đã lưu thay vì thực hiện side effect lần nữa.
- Khi retry cùng một ý định, giữ idempotency key; có thể dùng correlation ID mới cho từng lần trao đổi để theo dõi từng attempt.
- Nếu nghiệp vụ hỗ trợ, cung cấp query để kiểm tra trạng thái theo request ID.

Không xem timeout như tín hiệu hủy command. Muốn hủy công việc đang chạy cần một command hủy riêng và responder phải hỗ trợ semantics đó.

### 11.3. Đặt timeout theo SLA

Timeout cần cân bằng giữa thời gian xử lý bình thường và trải nghiệm caller. Ví dụ:

- Tác vụ đọc dữ liệu nhẹ: có thể dùng deadline ngắn.
- Tác vụ cần nhiều service hoặc database: phải tính cả queue delay và processing time.
- Tác vụ nặng hoặc kéo dài: chuyển sang async workflow thay vì giữ thread chờ.

Timeout ở JMS requester nên nhỏ hơn hoặc bằng deadline của tầng gọi phía trên. Nếu HTTP request hết hạn trước JMS request/reply, thread có thể vẫn tiếp tục chờ và giữ tài nguyên dù caller đã rời đi.

### 11.4. Blocking và giới hạn thread

`JmsTemplate.sendAndReceive`, `JmsMessagingTemplate.convertSendAndReceive` và `JmsClient.sendAndReceive` đều thực hiện request/reply đồng bộ. Thread gọi sẽ bị giữ trong thời gian gửi và chờ phản hồi.

Trong hệ thống có nhiều request đồng thời:

- Dùng bounded thread pool cho các thao tác blocking.
- Giới hạn số request in-flight.
- Đặt timeout hữu hạn.
- Theo dõi queue depth và thời gian phản hồi.
- Tránh gọi trực tiếp từ event-loop thread của reactive server; nếu cần, chuyển sang scheduler dành cho blocking I/O.

Nếu cần hàng nghìn request đồng thời hoặc tác vụ kéo dài, mô hình bất đồng bộ với correlation registry và event trả kết quả thường phù hợp hơn.

## 12. Thiết kế response contract

Không nên chỉ trả một chuỗi lỗi tự do. Hãy định nghĩa response contract có trạng thái và thông tin cần thiết.

Ví dụ JSON:

~~~json
{
  "requestId": "req-7d2f",
  "status": "COMPLETED",
  "result": {
    "sku": "SKU-100",
    "price": 120000,
    "currency": "VND"
  },
  "errorCode": null,
  "message": null
}
~~~

Các trạng thái có thể gồm:

- `COMPLETED`: nghiệp vụ đã hoàn tất.
- `REJECTED`: yêu cầu bị từ chối theo quy tắc nghiệp vụ.
- `ACCEPTED`: hệ thống đã tiếp nhận, nhưng workflow vẫn đang chạy.
- `FAILED`: xử lý thất bại theo contract đã định nghĩa.

Với request/reply đồng bộ, `ACCEPTED` thường không đủ nếu caller cần kết quả cuối cùng ngay. Nếu workflow dài, trả operation ID và dùng API/event để theo dõi trạng thái.

Tách lỗi nghiệp vụ khỏi lỗi kỹ thuật:

- Lỗi nghiệp vụ nên được biểu diễn trong response rõ ràng, ví dụ `REJECTED` với `INSUFFICIENT_STOCK`.
- Lỗi kỹ thuật tạm thời có thể khiến listener rollback và message được redeliver theo cấu hình container.
- Lỗi không thể retry như payload sai schema cần được đưa vào dead-letter/quarantine hoặc trả một error response có contract rõ ràng.

Nếu listener ném exception, requester không tự động nhận một response lỗi nghiệp vụ. Nếu caller bắt buộc phải nhận lỗi có cấu trúc, responder phải map lỗi sang response message hoặc ứng dụng phải dùng một error-reply strategy riêng.

## 13. Transaction và acknowledgement

Request/reply gồm hai thao tác: nhận request và gửi reply. Nếu listener xử lý trong transacted JMS session, việc nhận request và gửi response có thể nằm trong cùng JMS transaction của listener container. Khi xử lý thất bại và transaction rollback, request có thể được redeliver theo broker policy.

Điều này giúp tránh tình huống listener acknowledge request nhưng chưa gửi được reply trong cùng transaction JMS. Tuy nhiên, transaction JMS không tự bao gồm transaction database. Nếu listener cập nhật database rồi gửi reply, cần thiết kế ranh giới commit phù hợp.

Một số nguyên tắc:

- Chỉ trả `COMPLETED` sau khi thay đổi nghiệp vụ đã đạt trạng thái bền vững.
- Dùng idempotency để xử lý request bị redeliver.
- Không acknowledge trước khi side effect quan trọng được commit.
- Nếu database và JMS phải được phối hợp, xem xét outbox/inbox hoặc transaction manager phù hợp.
- Không giữ transaction database dài trong khi thread chờ reply của một service khác.

Request/reply không tự đảm bảo exactly-once. Broker có thể redeliver khi consumer rollback, và requester có thể retry sau timeout dù request cũ đã được xử lý.

## 14. Bảo mật destination phản hồi

`JMSReplyTo` là destination do requester đưa vào message. Responder cần kiểm soát nơi nó được phép gửi phản hồi.

Với producer nội bộ đã xác thực, việc dùng `JMSReplyTo` do requester cung cấp là mô hình bình thường. Với message từ nguồn không tin cậy, không nên gửi dữ liệu nhạy cảm tới bất kỳ destination nào được ghi trong header mà không kiểm tra policy.

Cần xem xét:

- Broker authorization cho queue/topic request và reply.
- Danh sách destination reply được phép.
- Authentication của producer/consumer.
- Dữ liệu nhạy cảm trong response.
- Kích thước message và giới hạn payload.
- Correlation ID không được dùng thay cho xác thực hoặc phân quyền.

Không log toàn bộ payload nếu chứa thông tin cá nhân, token hoặc dữ liệu thanh toán. Nên log request ID, correlation ID, destination, thời gian xử lý và trạng thái.

## 15. Kiểm thử request/reply

Kiểm thử cần chạy với broker JMS thực tế hoặc test broker tương thích. Mock `JmsTemplate` không thể chứng minh `JMSReplyTo`, correlation, temporary queue hoặc message selector hoạt động đúng.

Các trường hợp nên có:

1. **Happy path:** request được gửi, responder trả lời, caller nhận đúng payload.
2. **Timeout:** responder không trả reply; caller nhận null/Optional.empty trong giới hạn cấu hình.
3. **Late reply:** responder trả lời sau timeout; reply không được giao nhầm cho request khác.
4. **Concurrent requests:** nhiều request cùng destination nhận đúng reply theo correlation.
5. **Responder exception:** kiểm tra rollback, redelivery hoặc error reply theo policy.
6. **No JMSReplyTo:** xác nhận responder xử lý đúng khi request không mong đợi reply.
7. **Invalid reply type/schema:** caller xử lý lỗi conversion có kiểm soát.
8. **Broker unavailable:** lỗi gửi/kết nối được phân biệt với timeout chờ reply.
9. **Duplicate request:** idempotency key ngăn side effect lặp.
10. **Shutdown:** temporary destination, consumer và connection được giải phóng đúng vòng đời.

Có thể dùng Testcontainers với broker như ActiveMQ Artemis hoặc broker JMS mà hệ thống triển khai thực tế sử dụng. Cần test cả cấu hình transacted listener và non-transacted listener nếu hai cấu hình này được dùng trong production.

## 16. Lỗi thường gặp

1. **Không đặt receive timeout.** Mặc định JmsTemplate chờ vô hạn, có thể giữ thread mãi.
2. **Nhầm timeout với TTL.** Timeout chỉ giới hạn thời gian caller chờ reply; TTL điều khiển thời gian message còn hiệu lực trong broker.
3. **Cho rằng timeout hủy request.** Responder có thể vẫn đang xử lý và hoàn tất side effect sau khi caller đã timeout.
4. **Retry request tạo side effect mà không idempotency.** Có thể tạo đơn hàng hoặc thanh toán trùng.
5. **Dùng shared reply queue không correlation.** Caller có thể nhận reply của request khác.
6. **Dùng application correlation ID không duy nhất.** Reply bị dispatch nhầm hoặc bị selector khớp nhiều request.
7. **Tạo một consumer riêng cho mỗi request trên reply queue dùng chung.** Consumer cạnh tranh có thể lấy reply của nhau.
8. **Cho rằng mọi listener return value đều có destination.** Nếu request không có JMSReplyTo và listener không cấu hình default reply destination, việc gửi reply có thể thất bại.
9. **Trả exception nhưng mong caller nhận error DTO.** Exception không tự động trở thành reply contract.
10. **Dùng request/reply cho tác vụ dài.** Caller giữ thread và phụ thuộc trực tiếp vào thời gian hoạt động của responder; cân nhắc async workflow.
11. **Tin JMSReplyTo từ nguồn không tin cậy.** Có thể gửi reply tới destination không được phép.
12. **Dùng một timeout toàn cục cho mọi use case.** Mỗi operation có SLA khác nhau; Spring 7 JmsClient hỗ trợ timeout theo operation.
13. **Nhầm API của JmsTemplate.** JmsTemplate có sendAndReceive raw Message; typed convertSendAndReceive thuộc JmsMessagingTemplate.
14. **Không kiểm tra broker thật.** Mock không kiểm tra được temporary queue, reply header, selector và correlation.

## 17. Checklist trước khi phát hành

- [ ] Request destination và reply destination được xác định rõ.
- [ ] Request có `JMSReplyTo` hợp lệ khi cần reply.
- [ ] Reply có correlation ID đúng theo contract.
- [ ] Requester có timeout hữu hạn phù hợp với SLA.
- [ ] Phân biệt timeout chờ reply với lỗi gửi/kết nối.
- [ ] Có idempotency key cho request có side effect.
- [ ] Late reply và duplicate reply có chính sách xử lý.
- [ ] Chọn temporary queue hoặc shared reply queue theo lưu lượng.
- [ ] Shared reply queue có correlation dispatcher/selector đúng.
- [ ] Listener return value hoặc manual reply có destination hợp lệ.
- [ ] Business rejection và technical failure có response/error semantics rõ ràng.
- [ ] Transaction/acknowledgement phù hợp với side effect.
- [ ] Có giới hạn concurrency và tài nguyên thread cho thao tác blocking.
- [ ] Kiểm soát quyền gửi tới JMSReplyTo.
- [ ] Integration test bao gồm timeout, concurrency, late reply và broker failure.

## 18. Tài liệu tham khảo

- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): JmsTemplate, JmsClient và các thao tác request/reply.
- [Spring Framework Reference — Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html): gửi message, MessageCreator, MessageConverter và JmsClient.
- [Spring Framework Reference — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): synchronous receive, timeout và listener.
- [Spring Framework Reference — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): @JmsListener, response management, @SendTo và listener return value.
- [Spring Framework Javadoc — JmsTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsTemplate.html): sendAndReceive, setReceiveTimeout và giá trị mặc định.
- [Spring Framework Javadoc — JmsMessagingTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsMessagingTemplate.html): convertSendAndReceive và typed reply conversion.
- [Spring Framework Javadoc — JmsClient](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsClient.html): fluent client API có từ Spring Framework 7.0.
- [Spring Framework Javadoc — JmsClient.OperationSpec](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/core/JmsClient.OperationSpec.html): withReceiveTimeout và sendAndReceive trả Optional.
- [Jakarta Messaging 3.1 Specification — Request/reply and message headers](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): JMSReplyTo, JMSCorrelationID, temporary destinations và request/reply semantics.
- [Jakarta EE Tutorial — JMS Concepts](https://jakartaee.github.io/jakartaee-documentation/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html): temporary queue và ví dụ request/reply.
- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): gateway, reply listener và correlation strategy cho shared reply destination.
