# Kiến thức nền và thứ tự học: từ message đến độ tin cậy trong JMS

**Phạm vi:** Bức tranh JMS trong Spring Framework. Bài này xây dựng mô hình tư duy và lộ trình học từ thông điệp đầu tiên cho tới câu hỏi “đã xử lý an toàn chưa?”. Các cấu hình riêng của từng broker là phần cần kiểm chứng ở tài liệu của broker đang dùng.

## 1. Bắt đầu từ bài toán: vì sao cần message?

Trong lời gọi HTTP đồng bộ, bên gọi thường chờ bên nhận hoàn tất hoặc trả lỗi. Với messaging, bên gửi (**producer**) gửi một **message** tới một **destination** do hệ thống nhắn tin quản lý; bên nhận (**consumer**) có thể xử lý ở một thời điểm khác. Producer và consumer không cần chạy đồng thời hoặc biết trực tiếp địa chỉ của nhau. Điều đó giúp tách thời điểm xử lý, hấp thụ tải đột biến và chia nhiệm vụ cho nhiều tiến trình.

~~~text
Ứng dụng đặt hàng (producer)
    → JMS API / thư viện Spring JMS
    → JMS provider / broker
    → Queue hoặc Topic (destination)
    → Consumer / @JmsListener
    → Kiểm tra dữ liệu → nghiệp vụ → ghi nhận kết quả
~~~

Ví dụ: sau khi ghi nhận đơn hàng, hệ thống phát thông điệp “đơn đã tạo” để một dịch vụ khác chuẩn bị giao hàng. **Gửi được message không đồng nghĩa công việc giao hàng đã xong.** Cần phân biệt ít nhất ba mốc: (1) bên gửi yêu cầu gửi; (2) broker chấp nhận/lưu hoặc định tuyến thông điệp theo cấu hình; (3) consumer xử lý và xác nhận thành công.

**JMS** là tên gọi quen thuộc của Java Message Service; API hiện đại được chuẩn hóa dưới tên **Jakarta Messaging** (gói `jakarta.jms` trong Jakarta Messaging 3.x). JMS là **API/hợp đồng lập trình**, không phải một broker cụ thể. Apache ActiveMQ Artemis, IBM MQ và các sản phẩm tương thích cung cấp implementation/provider. **Spring JMS** bổ sung lớp hỗ trợ để gửi, nhận, chuyển đổi payload và quản lý listener. Không nên đồng nhất Spring JMS, chuẩn JMS và cơ chế riêng của broker.

## 2. Nắm chắc một message trước khi nói về độ tin cậy

Một message JMS có ba phần quan trọng:

| Phần | Nội dung | Ví dụ/công dụng |
| --- | --- | --- |
| **Header chuẩn** | Trường do JMS định nghĩa, một số được provider thiết lập | `JMSMessageID`, `JMSDestination`, `JMSTimestamp`, `JMSDeliveryMode`, `JMSExpiration`, `JMSRedelivered` |
| **Properties** | Metadata dạng cặp tên–giá trị, phục vụ lọc/điều phối | `eventType=OrderCreated`, `tenantId`; `JMSXDeliveryCount` là property do JMS định nghĩa |
| **Body** | Nội dung nghiệp vụ | Văn bản JSON trong `TextMessage`, bytes trong `BytesMessage`, v.v. |

Một hợp đồng sự kiện có thể dùng body dạng JSON:

~~~json
{
  "eventId": "evt-1001",
  "type": "OrderCreated",
  "schemaVersion": 1,
  "orderId": "O-42",
  "occurredAt": "2026-10-30T01:00:00Z"
}
~~~

`eventId` là **định danh nghiệp vụ** do ứng dụng quản lý để nhận biết sự kiện lặp lại; `JMSMessageID` là định danh message ở tầng JMS, do provider gán theo quy tắc của API. Không thay thế tùy tiện hai loại ID cho nhau. `JMSCorrelationID` thường dùng để ghép yêu cầu–phản hồi hoặc chuỗi xử lý; `JMSReplyTo` có thể chỉ destination trả lời. `JMSRedelivered` cho biết thông điệp có thể đang được phát lại, còn `JMSXDeliveryCount` thường là 1 ở lần giao đầu và từ 2 khi giao lại. Đừng dựa duy nhất vào chúng để thực hiện idempotency nghiệp vụ.

Các kiểu body phổ biến gồm `TextMessage`, `BytesMessage`, `MapMessage`, `StreamMessage` và `ObjectMessage`. Khi trao đổi giữa các ứng dụng, thường ưu tiên định dạng có schema rõ và độc lập ngôn ngữ (chẳng hạn JSON hoặc Avro) cùng quy tắc version hóa. Cẩn trọng với `ObjectMessage` vì việc deserialize đối tượng Java từ nguồn không tin cậy có rủi ro bảo mật và phụ thuộc classpath.

**Message contract cần trả lời:** ai phát, ai tiêu thụ, tên loại sự kiện, schema/version, khóa định danh, dữ liệu bắt buộc, cách ứng xử khi thiếu trường, dữ liệu nhạy cảm, TTL và khả năng xử lý lặp. Message selector của JMS lọc theo **headers/properties**, không tự truy vấn các trường JSON nằm trong body.

## 3. Phân biệt Queue và Topic bằng câu hỏi “ai nhận một bản?”

| Tiêu chí | Queue – point-to-point | Topic – publish/subscribe |
| --- | --- | --- |
| Mục đích | Chia công việc cho các consumer cùng một queue | Phân phối sự kiện cho nhiều subscription độc lập |
| Khi có nhiều consumer | Một message được giao cho **một** consumer trong nhóm cạnh tranh, trừ các lần redelivery | Mỗi subscription phù hợp nhận một bản message; nhiều consumer có thể cùng phục vụ một shared subscription |
| Khi consumer tạm offline | Message có thể chờ trong queue nếu chưa hết hạn và broker còn khả năng lưu giữ | Non-durable subscription thường bỏ lỡ sự kiện lúc offline; durable subscription giữ phần chưa nhận theo điều kiện cấu hình |
| Ví dụ | Xử lý một tác vụ xuất hóa đơn | Thông báo đơn hàng cho kho, vận chuyển và phân tích |

Không suy ra “topic luôn lưu mọi sự kiện vô thời hạn”: **subscription** (non-durable/durable/shared), delivery mode, TTL, giới hạn tài nguyên và chính sách broker quyết định dữ liệu nào được giữ. Với queue, hai consumer không có nghĩa cả hai đều nhận mọi message. Với topic, hai subscription độc lập có thể nhận hai bản riêng biệt của cùng một sự kiện.

**Chọn theo ý định nghiệp vụ:** “một đơn vị xử lý tác vụ này” thường gợi ý queue; “nhiều hệ thống độc lập cần biết sự kiện này” thường gợi ý topic. Nếu cần mỗi hệ thống có backlog riêng, hãy thiết kế subscription hoặc queue tương ứng, không kỳ vọng một queue chia sẻ tự nhân bản message.

## 4. Các mảnh API và Spring tương ứng

- **`ConnectionFactory`** tạo kết nối/ngữ cảnh tới provider; cấu hình địa chỉ, xác thực, TLS và pool/caching thường đi cùng nó.
- **`Connection` / `Session` / `JMSContext`** đại diện kết nối và ngữ cảnh làm việc. `Session` cổ điển quản lý gửi/nhận, acknowledgment và local transaction; không chia sẻ một session tùy tiện giữa nhiều thread. `JMSContext` là API đơn giản hóa trong Jakarta Messaging.
- **`Destination`** đại diện queue hoặc topic; tên destination không tự xác định đầy đủ chính sách quản trị của broker.
- **`MessageProducer` / `MessageConsumer`** là API cấp thấp để gửi/nhận. Nhận có thể đồng bộ (chờ bằng `receive`) hoặc bất đồng bộ qua listener.
- **`JmsTemplate`** của Spring đơn giản hóa việc tạo tài nguyên, convert và send/receive. **`@JmsListener`** gắn consumer vào phương thức ứng dụng; listener container của Spring quản lý vòng đời, kết nối, số consumer và xử lý lỗi.
- **`MessageConverter`** xác định cách đổi đối tượng Java sang JMS message và ngược lại; hai phía cần thống nhất kiểu body, content type và schema.

Một chuỗi xử lý cơ bản: producer dùng `JmsTemplate.convertAndSend(...)` → broker nhận thông điệp → listener container nhận từ destination → Spring chuyển payload thành tham số `@JmsListener` → mã nghiệp vụ chạy → container thực hiện ack/commit hoặc rollback theo cấu hình. **Chính bước cuối** nối kiến thức “nhận message” với “xử lý đáng tin cậy”.

## 5. Độ tin cậy không phải một nút bật/tắt

Để nhận định một hệ thống “reliable”, xem từng lớp và tình huống thất bại:

| Cơ chế | Giúp ích | Không tự bảo đảm |
| --- | --- | --- |
| `PERSISTENT` delivery | Yêu cầu provider áp dụng cơ chế lưu bền hơn để chịu lỗi provider | Consumer xử lý thành công; message không hết TTL hoặc không bị loại bởi giới hạn tài nguyên |
| Queue / durable topic subscription | Giữ các message chưa nhận trong phạm vi chính sách lưu trữ | Không mất message trong mọi lỗi/vận hành; xử lý đúng một lần |
| Acknowledgment (ack) | Provider biết một lần nhận đã được xác nhận | Side effect ở DB đã commit cùng thời điểm |
| Local JMS transaction | Gộp việc nhận và các thao tác JMS trong cùng session thành commit/rollback | Tự động gộp commit của cơ sở dữ liệu ngoài JMS |
| Redelivery/retry | Có cơ hội xử lý lại sau lỗi | Không gây xử lý trùng, không làm nghẽn bởi poison message |
| DLQ / quarantine | Cách ly message liên tục thất bại để điều tra | Tự sửa dữ liệu sai hay khôi phục nghiệp vụ |
| Idempotency | Cùng một sự kiện xử lý lặp vẫn giữ kết quả nghiệp vụ mong muốn | Broker ngừng phát trùng; mọi hoạt động bên ngoài có sẵn tính idempotent |

**Delivery mode khác acknowledgment.** `PERSISTENT`/`NON_PERSISTENT` liên quan cách provider bảo vệ message trước lỗi. Ack/transaction liên quan việc tiêu thụ đã được ghi nhận hay chưa. TTL đặt thời hạn hữu ích: message có thể hết hạn dù đã gửi thành công. Priority, selector, nhiều consumer và redelivery cũng có thể ảnh hưởng thứ tự giao.

### Các chế độ ack cần hiểu trước khi cấu hình

- `AUTO_ACKNOWLEDGE`: provider/container tự xác nhận theo vòng đời nhận. Với **Spring `DefaultMessageListenerContainer`**, chế độ mặc định này có thể xác nhận **trước khi listener thực thi**, nên exception trong listener không bảo đảm redelivery; không dùng mặc định một cách vô thức cho tác vụ quan trọng.
- `CLIENT_ACKNOWLEDGE`: consumer chủ động xác nhận theo semantics của JMS session; Spring container có thể quản lý ack thay cho phương thức listener. Việc ack ở cấp session cần được nghiên cứu trước khi tự gọi API.
- `DUPS_OK_ACKNOWLEDGE`: cho phép ack trì hoãn và khả năng giao lặp; không phải cơ chế “bảo đảm đúng một lần”.
- **Transacted session** (`sessionTransacted=true`): listener thành công thì commit JMS; lỗi khiến JMS rollback và message có thể được giao lại theo chính sách provider. Đây là điểm khởi đầu hợp lý khi cần reliability với listener của Spring.

**Điều kiện của lời hứa:** việc trả lại message, số lần retry, delay/backoff, DLQ, persistence và failover có phần phụ thuộc broker/cấu hình. Đừng viết tài liệu “JMS mặc định retry 3 lần” hoặc “mọi exception luôn được phát lại”: đó không phải quy tắc chung.

### Ba mức diễn giải thường gặp

- **At-most-once:** ưu tiên tránh phát lại; có tình huống mất xử lý.
- **At-least-once:** chấp nhận phát lại khi chưa chắc đã xử lý xong; ứng dụng phải xử lý trường hợp trùng.
- **Exactly-once business effect:** kết quả nghiệp vụ chỉ được áp dụng một lần dù message có thể giao lại. Đây là mục tiêu **end-to-end**, thường cần transaction/idempotency tại dữ liệu nghiệp vụ (và đôi khi outbox/inbox, hoặc một giao thức giao dịch phân tán được thiết kế riêng), không suy ra chỉ từ một cấu hình JMS.

## 6. Ví dụ Spring JMS: từ message tới listener có local transaction

Ví dụ dưới đây dùng **Java 17+**, **Spring Boot 3.x / Spring Framework 6.x**, package `jakarta.jms` và một provider JMS đã cấu hình (chẳng hạn Artemis). Trong dự án Spring Boot cần dependency hỗ trợ Spring JMS và provider tương thích, ví dụ `org.springframework.boot:spring-boot-starter-artemis`, cùng một broker có thể kết nối. Đây là mã nguồn ứng dụng, **không phải chương trình `javac` độc lập**; đường dẫn tệp: `src/main/java/com/example/jmsdemo/MessagingDemoApplication.java`.

~~~java
package com.example.jmsdemo;

import java.util.UUID;
import jakarta.jms.ConnectionFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class MessagingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MessagingDemoApplication.class, args);
    }

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean
    ApplicationRunner sendExample(JmsTemplate jmsTemplate) {
        return args -> {
            String eventId = UUID.randomUUID().toString();
            String json = """
                    {"eventId":"%s","type":"OrderCreated","orderId":"O-42"}
                    """.formatted(eventId).strip();
            jmsTemplate.convertAndSend("orders.created", json);
        };
    }
}

@Component
class OrderListener {
    @JmsListener(destination = "orders.created")
    public void handle(String json) {
        System.out.println("Received: " + json);
        // Trong ứng dụng thật: kiểm tra schema và xử lý nghiệp vụ idempotent.
    }
}
~~~

**Đọc theo thứ tự:**

1. `ConnectionFactory` là cấu hình kết nối được Spring Boot/provider cấp; ví dụ giả định nó đã hoạt động. Với Boot 3 và Artemis native, các thiết lập như `spring.artemis.mode=native`, `spring.artemis.broker-url` và credentials phải phù hợp broker thực tế.
2. `JmsTemplate.convertAndSend` với String mặc định dùng converter thích hợp để tạo JMS text message gửi tới queue `orders.created` trong ví dụ. `ApplicationRunner` chỉ phát **một bản mẫu khi ứng dụng khởi động**, không biểu diễn thiết kế publish sự kiện gắn với giao dịch đặt hàng trong production.
3. `@JmsListener` nhận body dưới dạng String. Bean factory tên `jmsListenerContainerFactory` được listener infrastructure sử dụng; `setSessionTransacted(true)` khiến JMS receive được commit khi phương thức kết thúc thành công và rollback khi có lỗi.
4. Với broker sẵn sàng và message được giao, có thể thấy dòng dạng `Received: {"eventId":"...","type":"OrderCreated","orderId":"O-42"}`. Thời điểm dòng này xuất hiện **không xác định** vì listener chạy bất đồng bộ; nếu broker không kết nối, không có kết quả nhận thành công để khẳng định.

**Thử lỗi có kiểm soát:** cho listener ném `IllegalStateException` trước khi hoàn thành, quan sát rollback/redelivery và chính sách retry thực tế; sau đó khôi phục listener. Nếu lần nào cũng ném lỗi, đó là **poison message**: cần giới hạn retry và DLQ theo tài liệu broker để tránh vòng lặp vô hạn. Không diễn giải “một lần in ra” thành bằng chứng exactly-once khi chạy lại tiến trình, có nhiều consumer hoặc có lỗi mạng.

## 7. Khi JMS thành công nhưng nghiệp vụ vẫn sai

Hãy xét thứ tự thời gian sau:

~~~text
Consumer nhận M → cập nhật DB → DB commit thành công
                 → ứng dụng chết trước khi JMS commit/ack
                 → broker phát lại M → consumer nhận M lần thứ hai
~~~

Local JMS transaction xử lý rollback của **JMS**, nhưng DB đã commit độc lập. Lần phát lại có thể trừ tiền, cộng tồn kho hoặc gửi email lần hai nếu logic không chống trùng. Cách tiếp cận thường dùng:

1. Mỗi sự kiện có `eventId` ổn định; định nghĩa **khóa idempotency** theo nghiệp vụ và consumer, ví dụ cặp (`consumerName`, `eventId`).
2. Trong **cùng DB transaction** với thay đổi nghiệp vụ, ghi khóa vào bảng đã xử lý có **unique constraint**. Chỉ thực hiện side effect khi khóa được chèn mới. Khi sự kiện tới lại, nhận ra đã xử lý và kết thúc thành công để JMS có thể commit.
3. Với side effect ở hệ thống khác (email/payment/API), dùng idempotency key do hệ thống đích hỗ trợ hoặc một quy trình trạng thái có thể phục hồi; unique constraint trong DB của mình không tự đảo ngược request bên ngoài đã hoàn tất.
4. Với chiều **DB transaction → publish JMS**, cân nhắc **transactional outbox**: ghi sự kiện vào bảng outbox trong cùng transaction với dữ liệu nghiệp vụ, rồi một publisher riêng gửi tới broker và đánh dấu trạng thái. Publisher có thể gửi trùng khi retry, nên consumer vẫn cần idempotency.
5. Phối hợp giao dịch phân tán (XA/JTA) chỉ khi thật sự cần và đã hiểu chi phí, khả năng tương thích provider, giới hạn vận hành; không xem đó là cấu hình mặc định của Spring JMS.

**Cần chứng minh kết quả ở tầng dữ liệu nghiệp vụ**, không chỉ đếm số lần gọi listener.

## 8. Thứ tự học đề xuất: mỗi tầng trả lời một câu hỏi

| Bước | Câu hỏi cần trả lời | Thực hành nhỏ / bằng chứng cần thấy |
| --- | --- | --- |
| **1. Message contract** | Ta truyền sự kiện hay lệnh gì? | Viết payload có `eventId`, loại, version, khóa đối tượng; nêu owner/schema và cách validation |
| **2. Queue vs Topic** | Ai cần nhận một bản? | Gửi một message tới queue có hai consumer, đối chiếu với hai topic subscription độc lập |
| **3. JMS API** | Ai tạo kết nối, session, producer, consumer? | Vẽ đường đi từ `ConnectionFactory` tới destination, ghi rõ nguồn tài nguyên |
| **4. Spring JMS** | Spring giảm mã lặp ở đâu? | Dùng `JmsTemplate` và `@JmsListener`, kiểm tra converter, destination và log nhận |
| **5. Header/selector/correlation** | Phân luồng và truy vết ra sao? | Gán custom property, thử selector theo property, kiểm tra `JMSCorrelationID` |
| **6. Ack + transaction** | Khi listener lỗi, message đi đâu? | Bật `sessionTransacted=true`, ném exception, quan sát commit/rollback/redelivery |
| **7. Persistence + lifetime** | Broker hoặc subscriber ngừng thì sao? | So sánh `PERSISTENT`/`NON_PERSISTENT`, TTL, queue và durable topic trong điều kiện có kiểm soát |
| **8. Retry + DLQ** | Khi message lỗi mãi, hệ thống xử lý thế nào? | Cấu hình retry/backoff/max attempts theo broker, kiểm tra DLQ và cách replay an toàn |
| **9. Idempotency + DB consistency** | Có thể hoàn thành side effect hai lần không? | Làm rớt tiến trình sau DB commit, phát lại event và chứng minh DB chỉ đổi một lần |
| **10. Observability + operation** | Làm sao biết hệ thống thực sự ổn? | Theo dõi queue depth, tuổi message lâu nhất, consumer lag, số redelivery/DLQ, latency và alert |

Đừng học DLQ trước khi hiểu ack/rollback, cũng đừng khẳng định “đúng một lần” trước khi thử **crash sau DB commit**. Từ bước 6 trở đi, nên viết một giả thuyết trước phép thử (“rollback sẽ cho phép broker phát lại”), đo đạc và ghi kết quả theo **provider/version/config**; hành vi retries và giới hạn lưu trữ không giống nhau giữa mọi broker.

## 9. Những thí nghiệm lỗi nhất định phải làm

| Điểm gây lỗi | Kết quả cần kiểm tra | Hướng kiểm soát |
| --- | --- | --- |
| Producer không gửi được do broker mất kết nối | Gửi có lỗi? ứng dụng có retry? cùng event có bị gửi lại nhiều lần? | Retry có giới hạn, outbox khi cần nhất quán với DB, key chống trùng |
| Broker restart sau khi chấp nhận message | Message còn không, với delivery mode/TTL/tài nguyên hiện tại? | Persistence, cấu hình storage/HA và test recovery theo broker |
| Consumer ném exception trước JMS commit | Có rollback và redelivery? `JMSRedelivered`/`JMSXDeliveryCount` thay đổi thế nào? | Transacted listener, retry policy và xử lý lỗi phân loại |
| Consumer chết sau DB commit nhưng trước JMS commit | DB đã đổi, message có bị giao lại và nhân đôi side effect? | Idempotency có unique constraint cùng DB transaction |
| Message lỗi dữ liệu ở mọi lần thử | Có làm tắc queue hoặc lặp vô hạn? | DLQ/quarantine, log nguyên nhân, sửa payload/handler và replay có kiểm soát |
| Subscriber topic offline | Khi trở lại có nhận event gửi lúc vắng mặt không? | Đúng loại subscription, policy/TTL phù hợp |
| Nhiều consumer và message tới dồn dập | Thứ tự xử lý có thay đổi không? | Tránh giả định FIFO toàn cục; thiết kế key/order, giới hạn concurrency hoặc cơ chế grouping do provider hỗ trợ |

**Quan sát tối thiểu:** ghi `eventId`, `JMSMessageID`, `JMSCorrelationID` khi có, destination, lần giao, trạng thái xử lý và lỗi; không log credentials hoặc payload nhạy cảm tràn lan. Đo cả **queue depth**, **oldest-message age**, throughput, lỗi kết nối, số rollback/redelivery, DLQ size và **thời gian end-to-end**, vì chỉ “consumer đang chạy” không chứng minh backlog đang được xử lý đúng.

## 10. Các ngộ nhận thường gặp

1. **“JMS là một broker.”** JMS là API; khả năng persistence, retry, DLQ, HA, grouping và công cụ quản trị cụ thể do provider quyết định.
2. **“Gửi thành công nghĩa là business thành công.”** Send, broker acceptance, consumer ack và DB commit là những mốc khác nhau.
3. **“Queue gửi mỗi message cho mọi consumer.”** Nhiều consumer cùng queue thường cạnh tranh nhận; muốn nhiều bản độc lập phải thiết kế topic/subscription hoặc luồng riêng.
4. **“Topic có sẵn backlog vô hạn.”** Non-durable subscriber có thể bỏ lỡ message; durable subscription vẫn chịu expiry, tài nguyên và chính sách broker.
5. **“Persistent nghĩa là không bao giờ mất.”** TTL, lỗi cấu hình, giới hạn tài nguyên và thao tác quản trị có thể làm message không được giao.
6. **“Exception trong @JmsListener mặc định sẽ retry.”** Không thể bỏ qua semantics của listener container và acknowledgment; với `DefaultMessageListenerContainer` mặc định `AUTO_ACKNOWLEDGE` không đáp ứng bảo đảm redelivery khi handler lỗi.
7. **“Transaction JMS tự commit cùng DB.”** Local JMS transaction và DB transaction là hai phạm vi riêng; cần thiết kế consistency và idempotency.
8. **“JMS bảo đảm exactly-once cho nghiệp vụ.”** Delivery semantics của provider không tự bao phủ các side effect ngoài broker; replay có thể kích hoạt nghiệp vụ lần hai.
9. **“Thêm consumer vẫn giữ thứ tự tuyệt đối.”** Concurrency, ưu tiên, selector, retry và nhiều subscription làm thứ tự quan sát thay đổi; phải định nghĩa thứ tự cần bảo toàn theo khóa nghiệp vụ.
10. **“DLQ là nơi bỏ quên lỗi.”** Cần người sở hữu, cảnh báo, thông tin điều tra, chính sách lưu giữ và quy trình replay tránh phát lại tác dụng phụ.

## 11. Tự kiểm tra trước khi chuyển sang bài nâng cao

- Có thể mô tả đường đi producer → broker/destination → consumer → ack/commit, chỉ rõ ai sở hữu mỗi bước.
- Có thể chọn queue hay topic từ yêu cầu phân phối, giải thích consumer cạnh tranh và durable subscription.
- Có thể phân biệt header, property và body; biết vì sao cần `eventId` bên cạnh `JMSMessageID`.
- Có thể giải thích tác động của `AUTO_ACKNOWLEDGE`, `sessionTransacted`, redelivery, persistence và TTL mà không đánh đồng chúng.
- Có thể chứng minh bằng thí nghiệm lỗi rằng một side effect DB vẫn chỉ thực hiện một lần khi JMS giao trùng.
- Có thể mô tả luồng retry → DLQ → quan sát → sửa → replay; xác định thành phần phụ thuộc broker thay vì tự đặt giả định.

**Đích học tập:** từ “đã nhận message” đi tới “chúng ta biết điều gì xảy ra khi gửi, xử lý, xác nhận, retry hoặc crash”, kèm bằng chứng ở broker **và** trạng thái nghiệp vụ.

## Tài liệu gốc để đối chiếu

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): message model, headers, queue/topic, acknowledgment và delivery semantics.
- [Spring Framework – Annotation-driven JMS Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@JmsListener`, listener container và factory.
- [Spring Framework – Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html): nhận bất đồng bộ và xử lý trong transaction.
- [Spring Guide – Messaging with JMS](https://spring.io/guides/gs/messaging-jms/): ví dụ gửi/nhận và tích hợp Spring Boot.

Đọc thêm hướng dẫn của **broker và phiên bản đang triển khai** trước khi quyết định số lần retry, lịch redelivery, DLQ, lưu trữ bền vững, HA và policy khi đầy tài nguyên.