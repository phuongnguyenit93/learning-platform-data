# BrokerAvailabilityEvent và phản ứng khi STOMP broker không sẵn sàng

## Mục tiêu

Trong ứng dụng Spring WebSocket dùng STOMP, broker là thành phần nhận, định tuyến và phân phối message giữa các client. Khi ứng dụng dùng một broker bên ngoài thông qua STOMP broker relay, kết nối tới broker có thể bị mất do broker khởi động lại, mạng gián đoạn, timeout hoặc lỗi vận hành. Nếu code server tiếp tục gửi message như thể broker luôn sẵn sàng, message có thể không được chuyển đi và luồng nghiệp vụ có thể thất bại.

Spring cung cấp **BrokerAvailabilityEvent** để thông báo khi trạng thái sẵn sàng của broker thay đổi. Ứng dụng có thể lắng nghe event này để:

- Ngừng hoặc trì hoãn các lần gửi message mới khi broker không sẵn sàng.
- Hiển thị trạng thái suy giảm cho các chức năng phụ thuộc vào STOMP.
- Lưu message cần gửi vào cơ chế bền vững để xử lý lại sau khi kết nối phục hồi.
- Theo dõi thời điểm mất kết nối và khôi phục bằng log, metric hoặc health indicator.

Cần kết hợp event với xử lý lỗi gửi thực tế. Trạng thái có thể thay đổi giữa lúc kiểm tra và lúc gửi, vì vậy việc thấy broker đang sẵn sàng không đảm bảo lần gửi kế tiếp chắc chắn thành công.

## 1. BrokerAvailabilityEvent là gì?

BrokerAvailabilityEvent là một Spring ApplicationContext event thuộc package:

~~~java
org.springframework.messaging.simp.broker
~~~

Event được phát khi trạng thái sẵn sàng của message broker thay đổi. Nó có constructor nhận trạng thái boolean và source phát event, đồng thời cung cấp phương thức **isBrokerAvailable()** để đọc trạng thái:

~~~java
import org.springframework.messaging.simp.broker.BrokerAvailabilityEvent;

public void onBrokerAvailability(BrokerAvailabilityEvent event) {
    boolean available = event.isBrokerAvailable();
}
~~~

Ý nghĩa của giá trị:

| Giá trị | Ý nghĩa | Hành động ứng dụng thường làm |
|---|---|---|
| true | Broker đã sẵn sàng nhận xử lý message theo trạng thái được Spring theo dõi | Cho phép thử gửi; bắt đầu xử lý backlog nếu có |
| false | Broker không sẵn sàng | Tạm ngừng gửi trực tiếp; lưu hoặc trì hoãn message |

Event biểu thị **một lần chuyển trạng thái**, không phải một luồng kiểm tra liên tục. Ứng dụng nên lưu trạng thái mới nhất để các service khác có thể đọc nhanh.

Có thể nhận event bằng một trong hai cách:

- Triển khai **ApplicationListener<BrokerAvailabilityEvent>**.
- Dùng annotation **@EventListener** trên một Spring bean.

Không cần tự tạo event để kiểm tra broker. Trong cấu hình STOMP thông thường, Spring phát event từ message broker handler khi trạng thái broker thay đổi.

## 2. Event áp dụng cho Simple Broker và Broker Relay như thế nào?

Spring hỗ trợ hai kiểu broker phổ biến:

| Kiểu | Cách hoạt động | Đặc điểm availability |
|---|---|---|
| Simple Broker | Broker đơn giản chạy bên trong ứng dụng Spring | Được xem là sẵn sàng ngay sau khi khởi động và duy trì trạng thái đó khi ứng dụng đang chạy |
| STOMP Broker Relay | Spring chuyển tiếp STOMP message tới broker đầy đủ tính năng bên ngoài, chẳng hạn RabbitMQ hoặc ActiveMQ có hỗ trợ STOMP | Kết nối tới broker ngoài có thể mất rồi được thiết lập lại |

Với Simple Broker, event chủ yếu phản ánh vòng đời broker nội bộ. Simple Broker không cung cấp đầy đủ khả năng lưu trữ, phân phối và vận hành như một broker chuyên dụng.

Với Broker Relay, Spring duy trì một kết nối TCP hệ thống tới broker ngoài. Kết nối này được dùng cho message phát sinh từ ứng dụng server. Ngoài ra, relay tạo kết nối TCP riêng cho từng WebSocket client đang kết nối.

**Điểm cần phân biệt:** BrokerAvailabilityEvent của relay theo dõi trạng thái kết nối hệ thống tới broker. Nó không phải báo cáo sức khỏe riêng cho từng kết nối client, từng subscription, từng queue hoặc toàn bộ cluster broker. Nếu kết nối riêng của một client có vấn đề, event này không nhất thiết chuyển sang false.

## 3. Broker Relay tự kết nối lại ra sao?

Khi mất kết nối tới broker ngoài, STOMP broker relay của Spring tự thử thiết lập lại kết nối hệ thống. Theo tài liệu Spring hiện hành, relay thử kết nối lại định kỳ, mặc định khoảng 5 giây giữa các lần thử. Heartbeat trên kết nối hệ thống giúp phát hiện kết nối không còn phản hồi; khoảng gửi và nhận heartbeat mặc định là 10 giây và có thể cấu hình.

Khi kết nối hệ thống bị mất, Spring phát event với trạng thái false. Khi kết nối được thiết lập lại, Spring phát event với trạng thái true.

Việc relay khôi phục kết nối hệ thống **không đồng nghĩa các kết nối TCP riêng của client được tự động khôi phục**. Client cần tự triển khai logic reconnect. Khi dùng heartbeat, client có thể nhận ra broker không phản hồi và thực hiện kết nối lại theo chính sách của ứng dụng.

Một ví dụ cấu hình relay:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");

        registry.enableStompBrokerRelay("/topic", "/queue")
                .setRelayHost("localhost")
                .setRelayPort(61613)
                .setSystemLogin(System.getenv("STOMP_RELAY_SYSTEM_LOGIN"))
                .setSystemPasscode(System.getenv("STOMP_RELAY_SYSTEM_PASSCODE"));
    }
}
~~~

Đây là cấu hình minh họa trong ứng dụng Spring, không phải chương trình độc lập. Thay host, port và tên biến môi trường theo cấu hình của môi trường thực tế. Không lưu mật khẩu broker trực tiếp trong source code; nên lấy từ biến môi trường hoặc secret manager. Các thông tin system login và system passcode dùng cho kết nối hệ thống do ứng dụng tạo ra. Relay cũng có thông tin xác thực dành cho các kết nối client được cấu hình riêng.

## 4. Lắng nghe event và lưu trạng thái broker

Cách đơn giản là tạo một Spring component giữ trạng thái hiện tại bằng AtomicBoolean. Dùng giá trị ban đầu false để ứng dụng chỉ cho phép gửi sau khi nhận được thông báo broker đã sẵn sàng:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.broker.BrokerAvailabilityEvent;
import org.springframework.stereotype.Component;

@Component
public class BrokerAvailabilityMonitor {

    private final AtomicBoolean brokerAvailable = new AtomicBoolean(false);

    @EventListener
    public void onBrokerAvailability(BrokerAvailabilityEvent event) {
        brokerAvailable.set(event.isBrokerAvailable());
    }

    public boolean isBrokerAvailable() {
        return brokerAvailable.get();
    }
}
~~~

Giải thích:

1. @Component để Spring quản lý bean và phát hiện listener.
2. @EventListener đăng ký phương thức nhận BrokerAvailabilityEvent.
3. event.isBrokerAvailable() đọc trạng thái mới mà Spring thông báo.
4. AtomicBoolean.set() cập nhật trạng thái một cách an toàn khi nhiều thread cùng truy cập.
5. Service khác gọi isBrokerAvailable() để quyết định có thử gửi message hay không.

AtomicBoolean phù hợp vì event listener cập nhật trạng thái trong khi nhiều request hoặc worker có thể đọc cùng lúc. Một biến boolean thông thường không thể hiện rõ ý định đồng bộ giữa các thread.

Nếu muốn dùng interface thay annotation, có thể triển khai ApplicationListener<BrokerAvailabilityEvent> và cập nhật trạng thái trong onApplicationEvent. Hai cách đều là cơ chế lắng nghe Spring event; không cần đăng ký cả hai cho cùng một logic.

Listener nên xử lý nhanh: chỉ cập nhật trạng thái, ghi metric hoặc phát tín hiệu nội bộ. Không nên thực hiện thao tác I/O kéo dài, gửi hàng nghìn message hoặc chờ retry bên trong listener, vì có thể làm chậm luồng phát event.

## 5. Kiểm tra trạng thái trước khi gửi và vẫn bắt MessageDeliveryException

Spring khuyến nghị component dùng SimpMessagingTemplate theo dõi BrokerAvailabilityEvent để tránh gửi khi broker không sẵn sàng. Tuy vậy, ứng dụng vẫn phải xử lý MessageDeliveryException khi gửi message.

Lý do là có một khoảng thời gian giữa hai thao tác:

1. Service đọc trạng thái và thấy broker đang sẵn sàng.
2. Kết nối broker bị ngắt ngay sau lần kiểm tra.
3. Service gọi convertAndSend() và thao tác gửi thất bại.

Đây là race condition bình thường trong hệ thống phân tán. Kiểm tra trạng thái giúp tránh những lần gửi chắc chắn không nên thực hiện, còn bắt exception xử lý tình huống trạng thái vừa thay đổi.

Ví dụ service gửi notification:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.MessageDeliveryException;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationPublisher {

    private static final Logger log =
            LoggerFactory.getLogger(NotificationPublisher.class);

    private final SimpMessagingTemplate messagingTemplate;
    private final BrokerAvailabilityMonitor brokerMonitor;

    public NotificationPublisher(
            SimpMessagingTemplate messagingTemplate,
            BrokerAvailabilityMonitor brokerMonitor) {
        this.messagingTemplate = messagingTemplate;
        this.brokerMonitor = brokerMonitor;
    }

    public PublishResult publish(Notification notification) {
        if (!brokerMonitor.isBrokerAvailable()) {
            return PublishResult.BROKER_UNAVAILABLE;
        }

        try {
            messagingTemplate.convertAndSend(
                    "/topic/notifications",
                    notification
            );
            return PublishResult.ACCEPTED_BY_SPRING_CHANNEL;
        }
        catch (MessageDeliveryException ex) {
            log.warn("Không gửi được notification qua STOMP broker", ex);
            return PublishResult.DELIVERY_FAILED;
        }
    }
}

enum PublishResult {
    ACCEPTED_BY_SPRING_CHANNEL,
    BROKER_UNAVAILABLE,
    DELIVERY_FAILED
}

record Notification(String id, String message) {}
~~~

Ví dụ trên minh họa cách phân biệt ba kết quả:

- BROKER_UNAVAILABLE: service không gọi thao tác gửi vì trạng thái hiện tại là không sẵn sàng.
- ACCEPTED_BY_SPRING_CHANNEL: Spring message channel chấp nhận thao tác gửi.
- DELIVERY_FAILED: thao tác gửi thất bại và phát sinh MessageDeliveryException.

Tên kết quả ACCEPTED_BY_SPRING_CHANNEL được chọn có chủ ý. Việc convertAndSend() trả về bình thường không tự chứng minh client đã nhận message, consumer đã xử lý message hoặc broker đã lưu message bền vững. Nếu nghiệp vụ cần xác nhận giao nhận, phải thiết kế acknowledgement, persistence và retry phù hợp với broker cùng giao thức đang sử dụng.

Không nên bắt mọi Exception rồi trả về thành công. Hãy chỉ xử lý lỗi gửi mà ứng dụng có thể phản ứng, ghi log đủ ngữ cảnh và chuyển lỗi không dự kiến tới cơ chế xử lý lỗi chung.

## 6. Ứng dụng nên làm gì khi broker không sẵn sàng?

Cách phản ứng phụ thuộc mức độ quan trọng của message.

### 6.1. Tạm bỏ qua message có thể mất

Một số message chỉ mang tính thời điểm, chẳng hạn:

- Cập nhật vị trí hiện tại.
- Thông báo trạng thái đang gõ.
- Dữ liệu hiển thị tạm thời.
- Số liệu realtime có thể được gửi lại ở chu kỳ kế tiếp.

Với nhóm này, service có thể trả kết quả BROKER_UNAVAILABLE, bỏ lần phát hiện tại và chờ dữ liệu mới. Cần xác định rõ việc bỏ qua là chính sách nghiệp vụ được chấp nhận.

### 6.2. Retry có giới hạn

Nếu message cần được gửi lại, dùng cơ chế retry có:

- Giới hạn số lần thử.
- Exponential backoff để tăng dần khoảng chờ.
- Jitter để tránh nhiều worker cùng retry một thời điểm.
- Timeout và giới hạn thời gian giữ message.
- Idempotency key để xử lý trường hợp gửi lặp.
- Dead-letter hoặc trạng thái thất bại cuối cùng để điều tra.

Không retry liên tục trong vòng lặp không có delay. Một vòng lặp như vậy có thể làm đầy CPU, thread pool và log trong lúc broker vẫn đang mất kết nối.

Khi broker phục hồi, có thể phát tín hiệu cho worker xử lý lại backlog. Listener nên chỉ phát tín hiệu hoặc đánh thức worker; worker sẽ xử lý theo batch có giới hạn.

### 6.3. Dùng Transactional Outbox cho message quan trọng

Nếu message đại diện cho một thay đổi nghiệp vụ không được phép mất, chẳng hạn đơn hàng đã thanh toán hoặc giao dịch đã hoàn tất, chỉ giữ message trong RAM là không đủ. Ứng dụng có thể dừng trong lúc broker chưa phục hồi và làm mất queue trong bộ nhớ.

Transactional Outbox là một mẫu thiết kế phù hợp:

1. Trong cùng transaction database, lưu thay đổi nghiệp vụ và một bản ghi outbox.
2. Một worker riêng đọc các bản ghi outbox chưa gửi.
3. Worker chỉ thử gửi khi broker sẵn sàng.
4. Khi gửi thành công theo cơ chế xác nhận mà hệ thống yêu cầu, đánh dấu bản ghi đã xử lý.
5. Nếu lỗi, giữ bản ghi để retry theo chính sách.
6. Dùng message ID hoặc idempotency key để consumer có thể loại bỏ xử lý trùng.

Luồng tổng quát:

~~~text
Business request
      |
      v
Database transaction
  +----------------------+
  | Update business data |
  | Insert outbox record |
  +----------------------+
      |
      v
Outbox publisher
      |
      +---- Broker unavailable ----> Keep pending
      |
      v
Check availability and publish
      |
      +---- Delivery failure ------> Retry with backoff
      |
      v
Broker / consumers
      |
      v
Mark outbox item processed
~~~

Lưu ý: gửi thành công qua SimpMessagingTemplate không phải lúc nào cũng đồng nghĩa broker đã xác nhận lưu bền vững. Với yêu cầu giao nhận nghiêm ngặt, cần thiết kế acknowledgement hoặc publisher confirmation theo khả năng của broker và cơ chế tích hợp đang dùng. Outbox cần được đánh dấu hoàn tất theo mức xác nhận mà nghiệp vụ yêu cầu.

### 6.4. Hiển thị trạng thái suy giảm cho người dùng

Khi broker ngừng hoạt động, các chức năng realtime có thể tạm thời không dùng được dù phần xử lý HTTP và database vẫn hoạt động.

Ứng dụng có thể:

- Trả trạng thái tạm thời cho API cần phát message.
- Hiển thị banner kết nối realtime bị gián đoạn.
- Cho phép người dùng tiếp tục thao tác nghiệp vụ không phụ thuộc broker.
- Hiển thị thời điểm cập nhật cuối cùng nếu dữ liệu realtime đã cũ.
- Cung cấp cơ chế tải lại trạng thái từ API khi kết nối phục hồi.

Không nên để giao diện hiển thị rằng một message đã được gửi thành công nếu server mới chỉ nhận request nhưng chưa có xác nhận giao nhận theo yêu cầu.
## 7. Phân biệt trạng thái broker với trạng thái kết nối client

BrokerAvailabilityEvent là event phía ứng dụng Spring. Nó không tự gửi thông báo tới trình duyệt và không thay thế event vòng đời của STOMP session.

| Tình huống | Cơ chế cần theo dõi |
|---|---|
| Kết nối hệ thống từ Spring broker relay tới broker ngoài bị mất hoặc phục hồi | BrokerAvailabilityEvent |
| Một client bắt đầu gửi STOMP CONNECT | SessionConnectEvent |
| Broker phản hồi STOMP CONNECTED cho client | SessionConnectedEvent |
| Client đăng ký destination | SessionSubscribeEvent |
| Client ngắt session | SessionDisconnectEvent |
| Client cần tự kết nối lại sau sự cố mạng hoặc broker | Logic reconnect của STOMP client |

Đối với relay, kết nối hệ thống và kết nối riêng của từng client có vòng đời riêng. Vì vậy:

- BrokerAvailabilityEvent có thể báo kết nối hệ thống đã phục hồi trong khi client vẫn cần reconnect.
- Client có thể mất kết nối riêng dù kết nối hệ thống vẫn đang hoạt động.
- Trạng thái broker sẵn sàng không chứng minh mọi subscription đang hoạt động hoặc mọi message đều được consumer xử lý.
- Nếu cần trạng thái realtime ở giao diện, server phải cung cấp một endpoint hoặc message trạng thái riêng; client vẫn cần phát hiện close/error và reconnect.

Nếu xử lý SessionDisconnectEvent, hãy làm thao tác cleanup theo cách idempotent. Spring lưu ý event này có thể được phát nhiều hơn một lần cho cùng một session.

## 8. Theo dõi trạng thái bằng log, metric và health check

Một listener có thể ghi nhận mỗi lần trạng thái thay đổi:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.broker.BrokerAvailabilityEvent;
import org.springframework.stereotype.Component;

@Component
public class BrokerAvailabilityLogger {

    private static final Logger log =
            LoggerFactory.getLogger(BrokerAvailabilityLogger.class);

    @EventListener
    public void onBrokerAvailability(BrokerAvailabilityEvent event) {
        if (event.isBrokerAvailable()) {
            log.info("STOMP broker đã sẵn sàng");
        }
        else {
            log.warn("STOMP broker hiện không sẵn sàng");
        }
    }
}
~~~

Trong hệ thống thực tế, nên theo dõi thêm:

- Số lần chuyển từ available sang unavailable.
- Tổng thời gian broker ở trạng thái unavailable.
- Số message chờ trong outbox hoặc retry queue.
- Số lần gửi thất bại do MessageDeliveryException.
- Độ trễ từ lúc broker phục hồi tới lúc backlog được xử lý hết.
- Số lần client reconnect thành công hoặc thất bại.

Có thể đưa trạng thái vào Spring Boot Actuator HealthIndicator hoặc endpoint nội bộ. Tuy nhiên cần chọn chính sách readiness phù hợp:

- Nếu ứng dụng không thể phục vụ phần lớn chức năng khi broker mất kết nối, có thể đánh dấu readiness không đạt.
- Nếu chỉ chức năng realtime bị suy giảm, ứng dụng vẫn có thể nhận HTTP request và xử lý database. Khi đó nên biểu diễn trạng thái dependency riêng, không nhất thiết đánh dấu toàn bộ ứng dụng là không khỏe.
- Không dùng broker availability để thay thế liveness. Một broker bên ngoài bị lỗi không đồng nghĩa tiến trình Spring đã chết.

Health check cần phản ánh chính sách vận hành của dịch vụ. Tránh để một dependency tạm thời không sẵn sàng làm hệ thống điều phối liên tục restart toàn bộ ứng dụng, khiến việc phục hồi khó hơn.

## 9. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Service gửi message khi broker đã mất kết nối | Không lắng nghe BrokerAvailabilityEvent | Lưu trạng thái mới nhất và kiểm tra trước khi gửi |
| Broker vừa bị ngắt sau khi kiểm tra availability | Race condition giữa kiểm tra và gửi | Bắt MessageDeliveryException ở thao tác gửi |
| Ứng dụng nghĩ client đã kết nối lại khi event chuyển true | Nhầm kết nối hệ thống với kết nối riêng của client | Client tự reconnect và chờ STOMP CONNECTED |
| Message quan trọng bị mất khi broker ngừng hoạt động | Chỉ lưu message trong bộ nhớ hoặc bỏ qua lỗi | Dùng outbox hoặc hàng đợi bền vững |
| Retry tạo nhiều message trùng | Gửi lại sau timeout mà không có idempotency | Gắn message ID và xử lý idempotent ở consumer |
| CPU tăng mạnh trong lúc broker lỗi | Retry liên tục không có backoff | Exponential backoff, jitter và giới hạn retry |
| Listener làm chậm luồng xử lý event | Thực hiện gửi hàng loạt hoặc I/O đồng bộ trong listener | Chỉ cập nhật trạng thái và đánh thức worker |
| Health check báo toàn bộ app DOWN khi broker lỗi | Gộp trạng thái broker vào liveness | Phân biệt liveness, readiness và trạng thái dependency |

## 10. Kiểm thử phản ứng khi broker không sẵn sàng

Nên kiểm thử cả logic listener và luồng tích hợp với broker.

### Unit test cho listener

Có thể tạo event để kiểm tra monitor cập nhật trạng thái:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.simp.broker.BrokerAvailabilityEvent;

class BrokerAvailabilityMonitorTest {

    @Test
    void updatesAvailabilityWhenEventArrives() {
        BrokerAvailabilityMonitor monitor = new BrokerAvailabilityMonitor();

        assertFalse(monitor.isBrokerAvailable());

        monitor.onBrokerAvailability(
                new BrokerAvailabilityEvent(true, this)
        );
        assertTrue(monitor.isBrokerAvailable());

        monitor.onBrokerAvailability(
                new BrokerAvailabilityEvent(false, this)
        );
        assertFalse(monitor.isBrokerAvailable());
    }
}
~~~

Đây là ví dụ kiểm thử JUnit cho component monitor; cần có dependency JUnit Jupiter và Spring Messaging trong project. Test xác minh listener xử lý đúng hai chuyển trạng thái.

### Integration test với broker ngoài

Với STOMP broker relay, có thể dùng broker thật trong môi trường kiểm thử hoặc Testcontainers nếu có image phù hợp:

1. Khởi động ứng dụng và broker.
2. Chờ event báo broker available.
3. Gửi message và xác minh luồng nhận.
4. Dừng broker hoặc chặn kết nối TCP.
5. Xác minh trạng thái chuyển unavailable.
6. Gọi service gửi và xác minh message được trì hoãn hoặc trả kết quả thất bại theo chính sách.
7. Khởi động lại broker.
8. Xác minh relay kết nối lại và event chuyển available.
9. Xác minh outbox/retry worker xử lý message còn chờ.
10. Xác minh client STOMP tự reconnect và đăng ký lại subscription.

Simple Broker nội bộ không thể mô phỏng đầy đủ việc broker ngoài mất kết nối. Muốn kiểm thử đường đi của Broker Relay, hãy dùng một broker hỗ trợ STOMP trong integration test.

## 11. Checklist triển khai

- [ ] Hiểu rõ event thuộc package org.springframework.messaging.simp.broker.
- [ ] Lắng nghe event bằng @EventListener hoặc ApplicationListener.
- [ ] Lưu trạng thái hiện tại bằng AtomicBoolean hoặc cơ chế đồng bộ phù hợp.
- [ ] Mặc định không cho phép gửi trước khi nhận trạng thái available.
- [ ] Kiểm tra availability trước khi gọi SimpMessagingTemplate.
- [ ] Bắt MessageDeliveryException vì trạng thái có thể đổi giữa kiểm tra và gửi.
- [ ] Không coi gửi qua Spring channel là xác nhận client đã nhận.
- [ ] Chọn rõ chính sách bỏ qua, retry hoặc lưu outbox theo mức độ quan trọng của message.
- [ ] Dùng backoff, jitter và idempotency khi retry.
- [ ] Để client tự phát hiện lỗi và reconnect session.
- [ ] Theo dõi thời gian gián đoạn, lỗi gửi và backlog.
- [ ] Phân biệt liveness với readiness và trạng thái dependency.
- [ ] Kiểm thử cả trạng thái mất kết nối và phục hồi bằng broker thật.

## Tài liệu tham khảo

- [Spring Framework — ApplicationContext Events for STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)
- [Spring Framework — Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html)
- [Javadoc — BrokerAvailabilityEvent](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/broker/BrokerAvailabilityEvent.html)
- [Javadoc — SimpMessagingTemplate](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/SimpMessagingTemplate.html)
- [Javadoc — MessageDeliveryException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageDeliveryException.html)
