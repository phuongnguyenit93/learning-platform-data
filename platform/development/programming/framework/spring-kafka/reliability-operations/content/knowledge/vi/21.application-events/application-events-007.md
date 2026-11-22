# ConsumerStoppedEvent

Trong Spring Kafka, listener container quản lý vòng đời của Kafka consumer: khởi tạo, gia nhập consumer group, poll, giao record cho listener, commit offset và đóng consumer. Một ứng dụng production cần biết không chỉ **record có xử lý thành công hay không**, mà còn **consumer có thực sự còn hoạt động không**.

**ConsumerStoppedEvent** là một application event do Spring Kafka phát ra khi một consumer được dừng. Nó cung cấp tín hiệu vòng đời để ứng dụng ghi log, cập nhật metric, cảnh báo và phân tích nguyên nhân consumer ngừng chạy. Sự kiện này đặc biệt hữu ích khi consumer dừng do lỗi bất thường như lỗi xác thực, lỗi transaction hoặc không tìm được offset hợp lệ.

Điểm cần nhớ từ đầu: **ConsumerStoppedEvent không phải một cơ chế retry record, không phải callback commit offset và cũng không tự khởi động lại consumer.** Nó là tín hiệu quan sát trạng thái lifecycle. Muốn phục hồi, cần kết hợp Kafka listener container, error handler, chính sách restart và vận hành consumer group.

## 1. ConsumerStoppedEvent nằm ở đâu trong Spring Kafka?

Một tiến trình Spring Kafka có thể tạo nhiều listener containers, mỗi container có một hoặc nhiều consumer thực tế tùy concurrency.

    Spring Boot application
             |
             v
    KafkaListenerEndpointRegistry
             |
             +--- Container "orders"
             |         |
             |         +--- Child consumer 1
             |         +--- Child consumer 2
             |
             +--- Container "payments"
                       |
                       +--- Child consumer 3

Mỗi consumer có lifecycle riêng, dù các consumer có thể thuộc cùng consumer group. Khi một consumer dừng và Spring Kafka phát event tương ứng, các Spring application event listeners có thể quan sát được ConsumerStoppedEvent.

Các mục đích phổ biến:

- Phân biệt consumer dừng bình thường với dừng do lỗi.
- Phát hiện vấn đề producer fencing trong listener giao dịch.
- Phát cảnh báo khi consumer không thể duy trì xác thực.
- Ghi nhận consumer dừng vì không có offset hợp lệ.
- Quan sát quá trình shutdown hoặc scale down của application.
- Điều tra vì sao consumer lag tăng do số consumer hoạt động giảm.
- Kết hợp với các event khác để theo dõi trạng thái listener container.

ConsumerStoppedEvent không thay thế Kafka AdminClient, consumer group metrics hoặc container health check. Nó là **một tín hiệu cục bộ** bên trong JVM ứng dụng.

## 2. Phân biệt consumer, listener và container

Ba khái niệm này dễ bị dùng thay thế cho nhau:

| Thành phần | Trách nhiệm | Khi dừng cần quan sát gì? |
|---|---|---|
| Kafka Consumer | Poll records, quản lý group membership và offset | Consumer thread có còn chạy không? |
| @KafkaListener method | Xử lý record hoặc batch | Logic nghiệp vụ có ném exception không? |
| KafkaMessageListenerContainer | Quản lý một Kafka consumer | Consumer bắt đầu/dừng với lý do nào? |
| ConcurrentMessageListenerContainer | Quản lý nhiều child containers | Có bao nhiêu child vẫn đang chạy? |
| KafkaListenerEndpointRegistry | Quản lý container được tạo từ @KafkaListener | Listener container theo ID nào đang running? |

Một exception trong @KafkaListener **không đồng nghĩa** ConsumerStoppedEvent sẽ xuất hiện. DefaultErrorHandler có thể retry hoặc recovery thành công, khiến consumer tiếp tục chạy.

Ngược lại, consumer có thể dừng trong lúc shutdown bình thường mà không có exception nghiệp vụ nào.

## 3. ConsumerStoppedEvent so với các application events khác

Spring Kafka phát nhiều sự kiện liên quan lifecycle. Một số event thường gặp:

| Event | Thời điểm/ý nghĩa |
|---|---|
| ConsumerStartingEvent | Consumer chuẩn bị khởi động |
| ConsumerStartedEvent | Consumer đã khởi động |
| ConsumerStoppingEvent | Consumer chuẩn bị dừng |
| ConsumerStoppedEvent | Consumer đã dừng; có thông tin lý do |
| ContainerStoppedEvent | Container đã dừng theo lifecycle tương ứng |
| ConsumerPausedEvent | Consumer thực sự được pause |
| ConsumerResumedEvent | Consumer được resume |
| ConsumerPartitionPausedEvent | Một partition được pause |
| ConsumerPartitionResumedEvent | Một partition được resume |
| NonResponsiveConsumerEvent | Theo dõi thấy consumer poll không phản hồi đủ lâu |
| ListenerContainerIdleEvent | Listener container không nhận record trong khoảng idle đã cấu hình |

Các event trên không phải tất cả luôn được phát cùng nhau, cũng không bảo đảm một chuỗi tuyệt đối giống nhau cho mọi phiên bản và tình huống lỗi.

**ConsumerStoppingEvent** và **ConsumerStoppedEvent** khác nhau ở thời điểm. Nếu cần biết consumer đang trong quá trình dừng, quan sát Stopping. Nếu cần ghi nhận rằng vòng đời consumer đã chấm dứt, dùng Stopped.

**ContainerStoppedEvent** phản ánh lifecycle container; ConsumerStoppedEvent phản ánh consumer cụ thể. Trong môi trường nhiều child consumer, chúng không có tỷ lệ 1:1 trong mọi tình huống.

## 4. Ý nghĩa của thuộc tính Reason

ConsumerStoppedEvent cung cấp lý do dừng thông qua getReason() trong các phiên bản Spring Kafka hỗ trợ API này.

Các giá trị thường gặp của ConsumerStoppedEvent.Reason gồm:

| Reason | Diễn giải | Hướng điều tra |
|---|---|---|
| NORMAL | Consumer kết thúc theo đường dừng thông thường | Shutdown, scale down, container.stop |
| ERROR | Consumer dừng do lỗi ngoài đường xử lý bình thường | Kafka client, listener container, stack trace gần thời điểm dừng |
| FENCED | Transactional producer bị fencing | transactional.id, trùng identity, rolling deployment, zombie producer |
| AUTH | Lỗi authentication hoặc authorization khiến consumer dừng | SASL/TLS, credentials, ACL, broker |
| NO_OFFSET | Không tìm được offset có thể bắt đầu khi chính sách yêu cầu offset hợp lệ | consumer group offset, auto.offset.reset, retention |

Danh sách enum và những trường hợp phát sinh từng Reason có thể thay đổi theo phiên bản Spring Kafka. Trong production, hãy ghi nhận nguyên văn reason mà phiên bản đang dùng cung cấp và đối chiếu thêm log exception, thay vì suy luận root cause chỉ từ enum.

Reason là **một phân loại cấp cao**, không phải toàn bộ exception stack hay bằng chứng đầy đủ về trạng thái broker.

## 5. NORMAL không có nghĩa ứng dụng luôn khỏe

Khi triển khai rolling deployment, ứng dụng nhận SIGTERM, Spring context đóng lại và listener container dừng có kiểm soát. ConsumerStoppedEvent với Reason.NORMAL có thể là điều hoàn toàn dự kiến.

Ví dụ:

    Kubernetes scale down
            |
            v
    Spring context closes
            |
            v
    Listener container stops
            |
            v
    Consumer closes normally
            |
            v
    ConsumerStoppedEvent(NORMAL)

Nhưng nếu một thành phần trong ứng dụng vô tình gọi stop() trên container, consumer cũng có thể dừng theo cách bình thường về mặt lifecycle trong khi nghiệp vụ **không mong muốn**.

Vì vậy:

- Reason.NORMAL không tự chứng minh service vẫn đang tiêu thụ dữ liệu.
- Khi deploy/scale, có thể coi NORMAL là tín hiệu kỳ vọng.
- Khi không có kế hoạch shutdown, NORMAL lặp lại có thể là dấu hiệu container bị stop bởi logic ứng dụng.
- Để xác định sức khỏe hiện tại, kiểm tra registry, số consumer đang chạy, consumer lag và tình trạng readiness.

Không nên đặt cảnh báo mức khẩn cấp cho mọi NORMAL event, nhưng cũng không nên bỏ qua mọi NORMAL nếu ứng dụng đột ngột không còn consumer.

## 6. ERROR: Consumer dừng bất thường

Reason.ERROR báo rằng consumer dừng do một đường lỗi không được xử lý như một shutdown bình thường.

Các nguyên nhân có thể liên quan:

- Exception ngoài vòng xử lý listener thông thường.
- Lỗi Kafka client hoặc quá trình poll.
- Lỗi lifecycle của container.
- Lỗi không thể tiếp tục mà framework quyết định dừng consumer.
- Tương tác lỗi với handler, transaction hoặc hệ thống phụ thuộc.

**Không** suy luận mọi IllegalArgumentException hoặc RuntimeException từ business listener sẽ tạo ERROR. Nếu error handler đã retry, recover hoặc bỏ qua lỗi theo chính sách, consumer có thể vẫn đang chạy.

Khi nhận ERROR, thực hiện điều tra theo thời gian:

1. Xác định source container/consumer của event.
2. Tìm exception đầu tiên trước thời điểm dừng.
3. Kiểm tra consumer group và membership.
4. Kiểm tra broker connectivity, poll, deserializer, authorization và transaction.
5. Xác định container có cơ chế restart hay đã ngừng vĩnh viễn.
6. Theo dõi committed offset và lag để đánh giá tác động dữ liệu.

Log một mình ConsumerStoppedEvent không đủ để khôi phục nguyên nhân; hãy giữ trace/correlation với log của container cùng thời điểm.

## 7. FENCED: Nguyên nhân liên quan transactional producer

Trong ứng dụng Spring Kafka dùng Kafka transactions, Kafka broker có thể fencing một transactional producer cũ khi một producer khác dùng cùng transactional.id với producer epoch mới hơn.

Ví dụ:

    Pod A tạo producer transactional.id=orders-tx-1
               |
               v
    Pod A bị network partition nhưng chưa chết
               |
               v
    Pod B sử dụng cùng transactional.id=orders-tx-1
               |
               v
    Broker fencing producer cũ của Pod A
               |
               v
    Pod A không thể tiếp tục transaction như trước

Khi container dừng vì producer fencing, ConsumerStoppedEvent có thể mang Reason.FENCED.

Hướng xử lý:

- Kiểm tra transaction-id-prefix của mỗi instance.
- Kiểm tra có pod cũ và mới cùng sống trong rolling deployment không.
- Xác định transactional.id có được cấp duy nhất cho producer đang hoạt động không.
- Tìm ProducerFencedException hoặc exception liên quan trong log.
- Kiểm tra cơ chế producer cache/lifecycle do Spring Kafka quản lý.
- Chỉ thiết kế restart sau khi đảm bảo producer identity không tiếp tục xung đột.

Không chữa FENCED chỉ bằng cách restart liên tục. Nếu cấu hình transactional ID vẫn trùng, restart có thể tạo vòng lặp fencing và làm consumer group bất ổn.

Kafka fencing bảo vệ tính đúng đắn của transaction trong Kafka; side effect đã chạy ngoài Kafka như database và API vẫn phải idempotent.

## 8. AUTH: Consumer dừng do xác thực hoặc phân quyền

Reason.AUTH có thể xuất hiện khi consumer không xác thực được với broker hoặc thiếu quyền thực hiện thao tác bắt buộc.

Một số nguyên nhân:

- SASL username/password hoặc token hết hạn.
- TLS certificate không hợp lệ hoặc đã hết hạn.
- ACL không cho consumer đọc topic hoặc tham gia group.
- Broker thay đổi cấu hình bảo mật mà client chưa được cập nhật.
- Secret rotation triển khai không đồng bộ.
- Lỗi service xác thực bên ngoài.

Cần phân biệt:

- **Authentication:** client có chứng minh được danh tính với broker không?
- **Authorization:** danh tính hợp lệ nhưng có quyền đọc topic/group không?

Spring Kafka có cấu hình retry khi gặp một số authentication/authorization exceptions ở những phiên bản hỗ trợ, chẳng hạn authExceptionRetryInterval. Khi có cơ chế này, không phải mọi lần AUTH error đều lập tức dẫn tới ConsumerStoppedEvent; consumer có thể thử lại theo chính sách trước khi dừng.

Khi nhận AUTH:

1. Kiểm tra log Kafka client và broker.
2. Xác nhận secret và certificate đang được mount đúng.
3. Xác nhận topic/group ACL.
4. Kiểm tra hệ thống phân phối credentials.
5. Không ghi username/password, token hay toàn bộ cấu hình bảo mật vào event log.
6. Chỉ resume/restart khi điều kiện xác thực đã được sửa hoặc có retry policy an toàn.

## 9. NO_OFFSET: Không có điểm bắt đầu hợp lệ

Kafka consumer group đọc từ committed offset gần nhất nếu offset còn hợp lệ. Nếu không có committed offset hoặc offset hiện tại không còn trong log, hành vi tùy thuộc auto.offset.reset.

Các lựa chọn thường gặp:

- earliest: bắt đầu từ offset còn sớm nhất.
- latest: bắt đầu từ offset mới nhất.
- none: không tự chọn offset mới; có thể phát sinh lỗi khi không có offset hợp lệ.

Ví dụ:

    Topic orders.events
    Retention đã xóa các record cũ
    Group committed offset không còn hợp lệ
              |
              v
    auto.offset.reset=none
              |
              v
    NoOffsetForPartitionException
              |
              v
    Consumer dừng / ConsumerStoppedEvent(NO_OFFSET)

Tình huống khác là consumer group mới chưa từng commit offset nhưng dùng reset policy none.

Không tự động sửa bằng cách đặt latest trong production nếu điều đó làm bỏ qua dữ liệu chưa xử lý. Cần quyết định nghiệp vụ có chấp nhận bắt đầu tại earliest/latest hay phải restore dữ liệu từ nơi khác.

Các bước điều tra:

- Kiểm tra group có committed offset chưa.
- Kiểm tra topic partition tồn tại và offset earliest/latest hiện tại.
- Xác định retention có khiến offset cũ hết hiệu lực.
- Kiểm tra cấu hình auto.offset.reset.
- Xác định vị trí được phép khôi phục theo runbook.

## 10. Lắng nghe ConsumerStoppedEvent bằng @EventListener

Spring Framework hỗ trợ lắng nghe application events bằng @EventListener. Với Spring Kafka, có thể viết một bean đơn giản:

~~~java
package com.example.kafka.monitoring;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerStoppedEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaConsumerStopLogger {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaConsumerStopLogger.class);

    @EventListener
    public void onConsumerStopped(ConsumerStoppedEvent event) {

        ConsumerStoppedEvent.Reason reason = event.getReason();

        if (reason == ConsumerStoppedEvent.Reason.NORMAL) {
            log.info(
                "Kafka consumer stopped normally; source={}",
                event.getSource()
            );
        }
        else {
            log.warn(
                "Kafka consumer stopped abnormally; reason={} source={}",
                reason,
                event.getSource()
            );
        }
    }
}
~~~

Khi ConsumerStoppedEvent được Spring Kafka publish qua ApplicationEventPublisher, Spring sẽ chuyển nó tới listener đã đăng ký.

getSource() là phương thức của Spring ApplicationEvent, phù hợp để ghi thông tin nhận diện nguồn sự kiện. Không nên mặc định source là một KafkaConsumer có thể thao tác, và không cần ép kiểu nó để commit/seek.

Nếu hệ thống có nhiều Kafka listener containers trong cùng application context, observer có thể nhận event từ nhiều container. Khi thiết kế cảnh báo theo từng listener, cần xác định identity ổn định theo contract của phiên bản Spring Kafka đang dùng, không chỉ dựa vào toString() của source.

## 11. Lắng nghe bằng ApplicationListener

Ngoài annotation, có thể triển khai ApplicationListener<ConsumerStoppedEvent>:

~~~java
@Component
public class ConsumerStopObserver
        implements ApplicationListener<ConsumerStoppedEvent> {

    private final Logger log =
            LoggerFactory.getLogger(ConsumerStopObserver.class);

    @Override
    public void onApplicationEvent(ConsumerStoppedEvent event) {
        log.info(
            "ConsumerStoppedEvent observed: reason={}",
            event.getReason()
        );
    }
}
~~~

Hai cách @EventListener và ApplicationListener đều hợp lệ. Nên chọn một phong cách phù hợp với cấu trúc dự án để tránh ghi metric hoặc gửi alert hai lần cho cùng event.

Nếu ứng dụng cần nhận nhiều loại event Spring Kafka, có thể đặt nhiều phương thức @EventListener trong cùng monitoring component, mỗi method nhận một event type.

## 12. Dùng metric thay vì chỉ ghi log

ConsumerStoppedEvent hữu ích cho các counter phân loại lý do dừng.

Ví dụ với Micrometer:

~~~java
@Component
public class ConsumerStopMetrics {

    private final MeterRegistry meterRegistry;

    public ConsumerStopMetrics(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @EventListener
    public void onStopped(ConsumerStoppedEvent event) {
        String reason = event.getReason().name();

        meterRegistry.counter(
            "kafka.consumer.stopped",
            "reason", reason
        ).increment();
    }
}
~~~

Metric trên được tạo theo reason, một nhãn có cardinality thấp. Khi dùng Prometheus, tên counter có thể được chuẩn hóa theo convention của registry; hãy kiểm tra tên hiển thị thực tế trên dashboard.

Không dùng eventId, offset, UUID hoặc full exception message làm metric label. Các giá trị đó có cardinality cao, làm tăng chi phí lưu trữ và có thể gây quá tải hệ thống metrics.

Nếu cần label theo listener ID hoặc group ID, hãy lấy từ nguồn cấu hình/container metadata ổn định theo API phiên bản đang sử dụng. Không suy ra group ID từ tên topic hoặc từ chuỗi source không được tài liệu bảo đảm ổn định.

Counter chỉ cho biết đã có bao nhiêu lần dừng; nó không cho biết **hiện có bao nhiêu consumer còn sống**. Vì vậy cần bổ sung metric running/assignment và trạng thái container.

## 13. Cẩn trọng với concurrent listeners

Khi Spring Kafka dùng ConcurrentMessageListenerContainer và concurrency lớn hơn 1, mỗi child container thường quản lý một consumer riêng.

Ví dụ:

    @KafkaListener(id="orders", concurrency=4)
               |
               v
    Parent container
       |
       +--- Child 0 -> Consumer A
       +--- Child 1 -> Consumer B
       +--- Child 2 -> Consumer C
       +--- Child 3 -> Consumer D

Khi dừng toàn bộ container, có thể quan sát nhiều ConsumerStoppedEvent, thường tương ứng các child consumers đã dừng.

Không nên viết logic kiểu:

    Nhận ConsumerStoppedEvent bất kỳ
        => toàn bộ listener "orders" đã ngừng

Một child consumer dừng không tự chứng minh cả parent container hoặc những child còn lại đã dừng. Tương tự, đếm một event NORMAL như một lần ứng dụng shutdown có thể gây thống kê sai khi concurrency thay đổi.

Cần phân biệt:

- Số event dừng của child consumer.
- Số consumer hiện đang chạy.
- Trạng thái parent container.
- Số partition đang được assign.
- Consumer lag theo partition và consumer group.

Khi muốn phát cảnh báo “toàn bộ listener đã dừng”, hãy kiểm tra container-level state hoặc sử dụng ContainerStoppedEvent theo yêu cầu, không chỉ dựa trên một ConsumerStoppedEvent.

## 14. Lấy trạng thái container qua KafkaListenerEndpointRegistry

Spring Kafka cung cấp KafkaListenerEndpointRegistry để truy xuất listener container được khai báo từ @KafkaListener theo ID.

~~~java
@Service
public class KafkaContainerStatusService {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaContainerStatusService(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isOrdersListenerRunning() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        return container != null && container.isRunning();
    }
}
~~~

Các import chính:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;
~~~

Để lookup đúng, @KafkaListener phải có id="ordersListener" tương ứng.

Lưu ý thời điểm: nếu đọc isRunning() ngay **bên trong** callback ConsumerStoppedEvent, parent container có thể vẫn đang hoàn tất quá trình stop hoặc một số child vẫn đang dừng. Muốn xác nhận trạng thái cuối, có thể kiểm tra lại sau khi lifecycle hoàn tất hoặc quan sát ContainerStoppedEvent.

isRunning() phản ánh lifecycle container, không có nghĩa consumer vừa xử lý record thành công, partition đã được assign hoặc lag ở mức chấp nhận được. Health cần nhiều tín hiệu.

## 15. Sự kiện được publish trên thread nào?

Spring Kafka application events thường được publish từ thread quản lý consumer/container. Với ApplicationEventMulticaster mặc định chạy đồng bộ, phương thức @EventListener có thể chạy trực tiếp trên đường thực thi publish event.

Hệ quả:

- Handler chậm có thể kéo dài bước dừng consumer.
- Một API mạng treo trong handler có thể cản trở graceful shutdown.
- Exception không được xử lý trong handler có thể ảnh hưởng đường phát event.
- Không nên thực hiện thao tác blocking lớn chỉ để gửi cảnh báo.
- Những API của KafkaConsumer chỉ được gọi từ thread sở hữu consumer; không tự chuyển reference sang thread khác.

Spring Framework cho phép thay ApplicationEventMulticaster hoặc dùng cơ chế async. Khi event dispatch bất đồng bộ, callback có thể chạy trên thread khác; **không** dùng callback async để thao tác với KafkaConsumer như commit, seek, pause hoặc poll.

Ví dụ handler nguy hiểm:

~~~java
@EventListener
public void onStopped(ConsumerStoppedEvent event) {
    // Phản ví dụ: thao tác mạng có thể chờ hàng phút.
    remoteIncidentApi.sendFullDiagnosticReport(event);
}
~~~

Nên xử lý nhanh trong callback: ghi metric, log ngắn hoặc đưa thông báo nhẹ vào cơ chế bất đồng bộ được quản lý riêng, có giới hạn queue và timeout.

## 16. Mẫu chuyển tín hiệu ra hệ thống cảnh báo an toàn hơn

Nếu cần đẩy trạng thái bất thường sang alerting service, nên tách **việc tiếp nhận application event** khỏi **việc gửi thông báo mạng**.

Một mẫu minh họa:

~~~java
public record ConsumerStopSignal(
        String reason,
        String applicationInstance,
        Instant occurredAt) {
}

public interface ConsumerStopSignalQueue {
    boolean offer(ConsumerStopSignal signal);
}

@Component
public class ConsumerStopEventAdapter {

    private final ConsumerStopSignalQueue queue;
    private final String instanceId;

    public ConsumerStopEventAdapter(
            ConsumerStopSignalQueue queue,
            @Value("order-service") String instanceId) {

        this.queue = queue;
        this.instanceId = instanceId;
    }

    @EventListener
    public void onStopped(ConsumerStoppedEvent event) {

        if (event.getReason() == ConsumerStoppedEvent.Reason.NORMAL) {
            return;
        }

        ConsumerStopSignal signal = new ConsumerStopSignal(
            event.getReason().name(),
            instanceId,
            Instant.now()
        );

        boolean accepted = queue.offer(signal);

        if (!accepted) {
            // Ghi metric dropped notification để vận hành biết.
            // Không block vô hạn trong consumer event callback.
        }
    }
}
~~~

Đây là mẫu thiết kế: ConsumerStopSignalQueue là interface ứng dụng phải tự triển khai, chẳng hạn một bounded queue có worker riêng hoặc một cơ chế xuất bản sự kiện nội bộ. Trong production cần import Instant, Value, EventListener, Component và các kiểu liên quan.

Nếu queue trong RAM bị mất khi process chết, cảnh báo chưa gửi cũng có thể mất. Với sự cố nghiêm trọng, nên kết hợp các tín hiệu độc lập như Kubernetes readiness, metrics từ Prometheus hoặc kiểm tra consumer group ở ngoài JVM. Không coi thông báo từ chính process đang chết là kênh cảnh báo duy nhất.

## 17. Không tự restart container ngay trong callback một cách mù quáng

Khi nhận ConsumerStoppedEvent với ERROR hoặc FENCED, ý tưởng đơn giản là gọi start() tức thì:

~~~java
@EventListener
public void onStopped(ConsumerStoppedEvent event) {
    registry.getListenerContainer("ordersListener").start();
}
~~~

Đây là **phản ví dụ**, không phải cách khuyến nghị. Có nhiều vấn đề:

1. Container có thể vẫn đang hoàn tất stop lifecycle.
2. Event có thể thuộc về một child, trong khi parent container đang running.
3. Reason.FENCED hoặc AUTH có thể phản ánh cấu hình chưa được sửa.
4. Gọi start/stop ngay trên thread event có thể gây tương tác lifecycle khó kiểm soát.
5. Khởi động lại liên tục tạo rebalance storm và che giấu nguyên nhân thật.

Nếu cần tự phục hồi, nên có một supervisor riêng:

- Nhận tín hiệu stopped.
- Kiểm tra container/state và nguyên nhân.
- Chọn lỗi retryable hoặc non-retryable.
- Áp dụng backoff, giới hạn số lần restart và cooldown.
- Đảm bảo không có tiến trình khác đang quản lý restart đồng thời.
- Kiểm tra tình trạng credentials, broker hoặc transactional ID.
- Phát metric và cảnh báo nếu liên tục thất bại.

Với hệ thống chạy Kubernetes, readiness/liveness policy và deployment controller có thể đảm nhận một phần restart. Cần tránh để supervisor trong JVM và orchestrator cùng tạo hai vòng restart không kiểm soát.

## 18. Một policy mẫu phân loại hành động

| Reason | Phản ứng tức thời | Phản ứng phục hồi |
|---|---|---|
| NORMAL | Log mức thông tin, xác định có planned shutdown | Không restart nếu đang scale down/deploy |
| ERROR | Log WARN/ERROR, tăng metric, kiểm tra exception | Có thể restart có backoff nếu lỗi tạm thời |
| FENCED | Cảnh báo producer transaction, kiểm tra identity | Sửa transactional.id/prefix và lifecycle rồi mới phục hồi |
| AUTH | Cảnh báo cấu hình xác thực và quyền | Kiểm tra secret/ACL; retry có kiểm soát sau khi sửa |
| NO_OFFSET | Dừng tiêu thụ, xác minh committed offset/retention | Quyết định vị trí reset theo nghiệp vụ |
| Reason mới/chưa biết | Ghi nhận nguyên văn, không bỏ qua | Áp dụng policy mặc định an toàn, kiểm tra version |

Không nên coi Reason.ERROR là luôn có thể auto-restart. Ví dụ nếu listener bị dừng vì lỗi cấu hình lặp lại, restart tức thì chỉ tạo thêm traffic, log và mất ổn định consumer group.

Tương tự, không nên tự reset offset về latest với NO_OFFSET nếu dịch vụ có yêu cầu không mất dữ liệu.

## 19. ConsumerStoppedEvent không thay thế error handler

Spring Kafka error handling có mục tiêu xử lý lỗi **record**. ConsumerStoppedEvent mô tả trạng thái **consumer lifecycle**.

Ví dụ:

    Listener đọc OrderCreated
            |
            v
    Database timeout
            |
            v
    DefaultErrorHandler retry
            |
            v
    Lần hai thành công
            |
            v
    Consumer tiếp tục poll

Trong tình huống này có thể không có ConsumerStoppedEvent vì consumer chưa dừng.

Nếu record không thể xử lý, DefaultErrorHandler có thể gọi DeadLetterPublishingRecoverer để publish sang DLT, rồi tiếp tục với record sau. Đây vẫn không phải sự kiện consumer stopped.

Ngược lại, khi consumer không còn đủ quyền đọc topic, callback error handler có thể không giải quyết được vấn đề vì lỗi xảy ra ở mức consumer/broker authorization. ConsumerStoppedEvent.AUTH giúp vận hành biết vòng đời consumer đã dừng do đường lỗi xác thực.

Theo dõi song song:

- Listener processing failures.
- Retry và recovery/DLT.
- ConsumerStoppedEvent và reason.
- Consumer lag, assignment và offset commit.
- Kafka client health và broker connectivity.

## 20. ConsumerStoppedEvent và Kafka transactions

Với listener container transactional, có một ranh giới quan trọng:

    Consumer poll input
          |
          v
    Begin Kafka transaction
          |
          v
    Listener xử lý và send output
          |
          v
    Commit output + source offsets

Nếu transactional producer bị fenced hoặc transaction không thể tiếp tục, container có thể dừng consumer và phát ConsumerStoppedEvent.FENCED hoặc một Reason phù hợp với đường lỗi.

Kafka transaction có thể bảo đảm atomicity giữa Kafka output và consumer offset khi được cấu hình đúng. Tuy nhiên:

- ConsumerStoppedEvent không tự commit hoặc abort transaction.
- Sự kiện stopped không xác nhận một transaction cụ thể đã commit.
- Nếu transaction bị abort, input có thể được redeliver từ committed offset an toàn.
- Nếu database/API ngoài Kafka đã thực hiện side effect, nó không tự rollback theo Kafka.
- Việc nhận event FENCED không thay thế kiểm tra producer ID/epoch và container transaction log.

Khi điều tra sự cố, nên quan sát cả transaction commit/abort metrics, số lần consumer dừng, group generation và duplicate xử lý bằng eventId.

## 21. Offset, acknowledgment và khả năng redelivery

Consumer dừng không chứng minh mọi record đã được commit.

Ví dụ:

    Committed offset = 200
    Consumer poll records 200..209
    Listener xử lý thành công tới 204
    Consumer dừng bất thường

Nếu container chưa commit offset qua record 204, consumer mới có thể đọc lại từ 200. Nếu một số record đã được commit theo AckMode, phạm vi replay khác đi.

Do vậy:

- Không suy luận trạng thái commit từ ConsumerStoppedEvent.
- Không lấy sự kiện stopped làm điểm để “ack nốt” các record chưa hoàn tất.
- Không gọi KafkaConsumer.commitSync() hoặc seek() từ event listener để sửa trạng thái.
- Luôn xác nhận offset committed thực tế khi phân tích loss/duplicate.
- Thiết kế side effect idempotent theo eventId hoặc unique business key.
- Phân biệt việc consumer đã poll record với việc listener xử lý và commit thành công.

Khi một process bị kill đột ngột, ConsumerStoppedEvent thậm chí có thể không được phát. Phục hồi phải dựa vào committed offsets và hợp đồng xử lý bền vững, không phụ thuộc vào callback cleanup.

## 22. ConsumerStoppedEvent khác rebalance

Rebalance là quá trình Kafka consumer group phân phối lại partition. Một consumer đang chạy có thể mất một số partition hoặc nhận thêm partition mà không dừng toàn bộ consumer.

Các callback liên quan rebalance:

- onPartitionsAssigned.
- onPartitionsRevoked.
- onPartitionsLost.

Trong khi đó, ConsumerStoppedEvent báo về lifecycle dừng consumer.

Ví dụ:

    Rebalance:
      Consumer A mất P2, vẫn xử lý P0/P1
      => không nhất thiết có ConsumerStoppedEvent

    Consumer shutdown:
      Consumer A đóng và rời group
      => có thể có ConsumerStoppedEvent(NORMAL)

Không dùng ConsumerStoppedEvent để thay thế onPartitionsLost khi cần hủy partition-local state hoặc fencing công việc của owner cũ. Lost ownership có thể xuất hiện trong lúc consumer thread vẫn hoạt động.

Tương tự, nhận ConsumerStoppedEvent không cung cấp danh sách chính xác partition vừa revoke; cần callback rebalance hoặc nhóm metric assignment để phân tích.

## 23. ConsumerStoppedEvent không phải điều kiện cảnh báo duy nhất

Một hệ thống không thể chỉ dựa vào event từ chính JVM để biết consumer đã chết.

Một số tình huống không bảo đảm event được phát hoặc được nhận:

- JVM bị SIGKILL hoặc hết bộ nhớ và dừng đột ngột.
- Container/pod bị kill trước khi Spring context shutdown.
- Mất điện hoặc node bị loại khỏi cluster.
- Process crash trước khi ApplicationEventListener được gọi.
- Application event handler bị lỗi hoặc không được đăng ký.
- Đường gửi cảnh báo bất đồng bộ mất message khi JVM chết.

Bởi vậy production nên có **external monitoring**:

1. Consumer group member count/assignment.
2. Consumer lag và tốc độ commit offset.
3. Listener container running state/readiness.
4. Pod/process health và restart count.
5. Broker/client connection metrics.
6. Các event ConsumerStoppedEvent đã được ghi nhận trong thời gian process còn sống.

Event hữu ích cho phân tích **vì sao** consumer dừng nếu framework đã kịp xử lý lifecycle; hệ thống bên ngoài cần phát hiện **consumer không còn tồn tại** kể cả khi không có event.

## 24. Readiness và liveness cần phân biệt

Khi consumer dừng bất thường, ứng dụng web vẫn có thể trả HTTP 200 vì Tomcat/Netty còn chạy. Nhưng API khỏe không có nghĩa consumer khỏe.

Readiness có thể xem xét:

- Listener containers bắt buộc đang running.
- Consumer group đã có assignment đủ để xử lý workload cần thiết.
- Consumer không gặp auth/fenced lỗi chưa phục hồi.
- Committed offsets còn tiến nếu có lưu lượng input.
- Lag hoặc record age nằm trong ngưỡng SLO.

Liveness không nên tự động fail chỉ vì một consumer tạm thời rebalance; điều đó có thể gây restart storm. Ngược lại, một consumer lỗi vĩnh viễn có thể cần restart process nếu application không có cơ chế khởi động lại listener an toàn.

Một policy tốt tách rõ:

| Câu hỏi | Nguồn |
|---|---|
| JVM/process còn sống? | Liveness probe/process metrics |
| Consumer có đủ điều kiện nhận traffic? | Readiness + registry + group assignment |
| Consumer đã dừng vì gì? | ConsumerStoppedEvent.Reason + logs |
| Dữ liệu có bị chậm? | Consumer lag, oldest age, commit rate |
| Có record không xử lý được? | Error handler, DLT, retry metrics |

## 25. Quan sát nhiều lần stop/start trong cùng thời gian

Consumer có thể trải qua một chuỗi:

    ConsumerStartingEvent
             |
             v
    ConsumerStartedEvent
             |
             v
    ConsumerStoppedEvent(ERROR)
             |
             v
    Supervisor bắt đầu lại sau backoff
             |
             v
    ConsumerStartingEvent
             |
             v
    ConsumerStartedEvent

Nếu chỉ nhìn event cuối cùng, khó biết có restart loop. Cần lưu lịch sử ngắn của lifecycle transitions kèm timestamp và identifier ổn định.

Chỉ số cần quan sát:

- Số lần consumer stopped trong 5 hoặc 15 phút.
- Tỷ lệ ERROR/FENCED/AUTH/NO_OFFSET.
- Thời gian từ stopped tới started tiếp theo.
- Số vòng restart liên tiếp.
- Consumer lag tại thời điểm stopped và sau khi started.
- Số partition không còn consumer xử lý.
- Số side effect duplicate sau redelivery.

Có thể đặt alert khi một container bắt buộc không running quá ngưỡng thời gian, hoặc có N lần abnormal stop trong một cửa sổ. Thời gian và N phải dựa trên SLO, không mặc định một event đã là outage toàn hệ thống.

## 26. Thiết kế logging hữu ích và an toàn

Một log message cho ConsumerStoppedEvent nên có những trường sau nếu lấy được từ thông tin và cấu hình hợp lệ:

    event_type=ConsumerStoppedEvent
    timestamp=...
    application=order-service
    instance=order-service-pod-3
    listener_id=ordersListener
    reason=FENCED
    source=...
    severity=WARN

Không cần log toàn bộ Consumer hoặc credentials, cũng không nên serialize nguyên object event để gửi log.

Nếu hệ thống dùng JSON structured logging, có thể làm một adapter biến Kafka event thành một record nhẹ. Event nội bộ không phải hợp đồng dữ liệu ổn định để publish trực tiếp cho bên ngoài.

Với exception context, thường cần tham chiếu log trước thời điểm stopped. ConsumerStoppedEvent.Reason không thay thế stack trace của lỗi gốc.

Nên dùng một correlation theo application instance, listener ID và thời điểm xảy ra. Không sử dụng offset hay eventId làm metric labels; khi điều tra một record cụ thể, dùng log có độ chi tiết phù hợp.

## 27. Kiểm thử nhận ConsumerStoppedEvent

Có thể kiểm tra một Spring context nhận đúng event bằng một observer test, rồi kiểm thử lifecycle với Kafka broker test (EmbeddedKafka hoặc Testcontainers).

Mẫu observer đơn giản:

~~~java
@Component
public class StoppedEventRecorder {

    private final BlockingQueue<ConsumerStoppedEvent> events =
            new LinkedBlockingQueue<>();

    @EventListener
    public void record(ConsumerStoppedEvent event) {
        events.offer(event);
    }

    public ConsumerStoppedEvent nextEvent(Duration timeout)
            throws InterruptedException {

        return events.poll(
            timeout.toMillis(),
            TimeUnit.MILLISECONDS
        );
    }
}
~~~

Các import chính:

~~~java
import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerStoppedEvent;
import org.springframework.stereotype.Component;
~~~

Ví dụ dùng queue không giới hạn chỉ để minh họa recorder trong test. Trong production, đừng giữ toàn bộ application event object vô thời hạn trong bộ nhớ; dùng bounded queue và chỉ giữ metadata cần thiết.

Kịch bản test một listener:

1. Khởi tạo application context, Kafka listener container và broker test.
2. Chờ consumer bắt đầu và có assignment theo điều kiện test.
3. Gọi stop trên container bằng thread test (không từ consumer event callback).
4. Chờ ConsumerStoppedEvent qua recorder.
5. Xác nhận reason của shutdown bình thường.
6. Xác nhận container cuối cùng không running.
7. Khởi động lại theo lifecycle test rồi xác nhận listener tiếp tục poll.

Khi concurrency > 1, recorder có thể nhận nhiều events. Test không nên assert cứng “chỉ có đúng một event” khi một parent container quản lý nhiều child consumers.

## 28. Test các reason bất thường

Không phải reason nào cũng dễ tái tạo bằng unit test. Một số cần môi trường tích hợp hoặc fault injection.

### 28.1. ERROR

Tạo lỗi được phiên bản Spring Kafka đang chạy xem là fatal ở cấp consumer/container. Quan sát event và log gần thời điểm dừng; đừng dùng lỗi business mà DefaultErrorHandler recover thành công rồi mong consumer phải stop.

### 28.2. AUTH

Dùng broker test có cấu hình SASL/TLS hoặc ACL để gây lỗi auth/authz, đồng thời xác nhận cơ chế retry auth nếu đã bật. Kiểm tra event chỉ khi consumer thực sự dừng; một exception tạm thời chưa chắc tạo stopped event.

### 28.3. FENCED

Dùng producer transactional IDs được kiểm soát để mô phỏng fencing theo contract Kafka, hoặc tạo xung đột có chủ ý trong test cô lập. Không chạy kịch bản này với transactional ID production.

### 28.4. NO_OFFSET

Tạo consumer group mới, đặt auto.offset.reset=none rồi không cung cấp committed offset phù hợp. Quan sát đường lỗi và reason trên phiên bản đang dùng. Cần bảo đảm môi trường test không có group offset cũ khiến kịch bản không tái hiện.

### 28.5. JVM crash

Dùng kill process để xác nhận **không giả định callback sẽ được phát**. Test phải dựa vào external health và consumer group recovery. Đây là kịch bản chứng minh giới hạn thiết kế của application events.

Khi viết test, ưu tiên xác nhận **trạng thái container, event thực tế và hậu quả offset/lag**, thay vì dựa duy nhất vào thứ tự callback mà một phiên bản cụ thể tình cờ tạo ra.

## 29. Tình huống vận hành: ConsumerStoppedEvent nhưng lag vẫn bằng 0

Có thể xảy ra vì:

- Topic hiện không có record mới.
- Consumer group có nhiều member; một child dừng nhưng member khác vẫn xử lý.
- Consumer đã commit hết dữ liệu trước khi dừng.
- Topic retention/offset hiện không tạo backlog.
- Metric lag không được cập nhật hoặc bị stale.

Do đó, lag bằng 0 không chứng minh consumer đang hoạt động bình thường. Cần kiểm tra container running state và thành viên group.

Ngược lại, lag tăng không nhất thiết có ConsumerStoppedEvent: consumer vẫn chạy nhưng xử lý chậm, bị pause, bị retry blocking, hot partition hoặc downstream quá tải.

Hai tín hiệu trả lời hai câu hỏi khác nhau: **consumer lifecycle** và **tiến độ tiêu thụ dữ liệu**.

## 30. Tình huống vận hành: Event bị gửi lặp hoặc không tới monitoring

Nếu metrics/log nhận nhiều ConsumerStoppedEvent:

- Xác định có nhiều child consumers/concurrency không.
- Kiểm tra deployment đang dừng nhiều pod cùng lúc không.
- Xác định có hai @EventListener beans cùng xử lý hay không.
- Kiểm tra supervisor có tạo vòng stop/start liên tục không.
- Phân biệt event từ nhiều application instance.

Nếu monitoring không thấy event dù group có consumer mất:

- Có thể process chết trước khi event được publish.
- App context đã đóng quá sớm.
- Listener không nằm trong component scan.
- ApplicationEventMulticaster đã được thay đổi theo hướng không mong đợi.
- Callback handler ném exception hoặc queue cảnh báo mất dữ liệu.
- Consumer chưa chạy trong application instance đang quan sát.

Sự cố external monitoring phải được giải quyết bằng tín hiệu broker/orchestrator, không bằng cách giả định event chắc chắn tồn tại nhưng chưa gửi.

## 31. Các lỗi thiết kế phổ biến

| Sai sót | Hậu quả | Cách xử lý |
|---|---|---|
| Coi mọi ConsumerStoppedEvent là lỗi | Alert khi shutdown/scale bình thường | Phân loại reason và planned lifecycle |
| Coi NORMAL là chắc chắn khỏe | Không phát hiện container bị dừng ngoài dự kiến | Kết hợp registry và business SLO |
| Coi event đồng nghĩa whole parent container stopped | Đánh giá sai khi concurrency > 1 | Theo dõi child và parent riêng |
| Gọi restart ngay trong event handler | Race lifecycle, restart loop, rebalance storm | Supervisor riêng với backoff/cooldown |
| Xử lý HTTP alert blocking trong callback | Dừng container chậm hoặc treo | Queue nhẹ, bounded, timeout |
| Dùng KafkaConsumer từ async event listener | Vi phạm thread safety | Không thao tác Consumer ngoài owner thread |
| Commit offset khi nhận stopped | Có thể ghi nhận record chưa xử lý | Để container/transaction quản lý offset |
| Không theo dõi FENCED/AUTH/NO_OFFSET | Bỏ sót lỗi cấu hình khó tự phục hồi | Alert theo reason với runbook |
| Chỉ dùng event làm liveness | Bỏ sót JVM crash/SIGKILL | External health, group metrics |
| Dùng full exception trong metric label | Cardinality cao và rò rỉ dữ liệu | Label reason cố định; exception ở log có kiểm soát |
| Test chỉ một consumer nhưng production concurrency nhiều | Sai số lượng event mong đợi | Test multi-child listener lifecycle |
| Mong listener business exception luôn tạo event stopped | Hiểu sai error handler | Phân biệt record error và lifecycle stop |

## 32. Runbook khi thấy ConsumerStoppedEvent bất thường

Khi phát hiện consumer dừng ngoài kế hoạch, có thể dùng trình tự:

1. **Xác định phạm vi:** application, instance, listener ID, thời điểm và reason.
2. **Đánh giá tác động:** parent container có running không, group còn member không, lag/oldest age ra sao?
3. **Tìm lỗi gốc:** tra log trước stopped event, phân biệt consumer/client/transaction/auth.
4. **Xác nhận thay đổi gần đây:** deploy, scale, secret rotation, ACL, broker rollout, topic retention.
5. **Kiểm tra offset:** có group offset hợp lệ không, có record chưa commit cần redelivery không?
6. **Phân loại recovery:** lỗi có thể retry hay cần sửa cấu hình/data?
7. **Với FENCED:** kiểm tra transaction ID và vòng đời producer trước khi restart.
8. **Với AUTH:** kiểm tra certificate, secret và quyền; tránh log thông tin bí mật.
9. **Với NO_OFFSET:** xác định reset position với quyết định nghiệp vụ rõ ràng.
10. **Nếu restart:** dùng backoff, tránh nhiều controller cùng restart và theo dõi started event.
11. **Sau phục hồi:** xác nhận listener nhận record mới, offset tiến đúng và không có duplicate side effect ngoài dự kiến.
12. **Ghi lại sự cố:** thêm metric, alert và test để phát hiện sớm trong lần sau.

Không dùng auto.offset.reset=latest hoặc commit offset thủ công như một “cách khôi phục nhanh” khi chưa biết có dữ liệu chưa được xử lý. Hành động đó có thể làm mất work mà consumer group đáng ra phải thực hiện.

## 33. Nguyên tắc áp dụng trong production

- ConsumerStoppedEvent là tín hiệu lifecycle của consumer, không phải retry record.
- Lắng nghe bằng @EventListener hoặc ApplicationListener trong Spring context.
- Sử dụng getReason() để phân loại NORMAL, ERROR, FENCED, AUTH và NO_OFFSET theo khả năng phiên bản.
- Đừng suy luận root cause đầy đủ từ enum; kiểm tra Kafka client/container logs.
- Trong concurrent container, phân biệt từng child consumer với parent container.
- Không dùng callback stopped để commit offset, seek hoặc acknowledge record muộn.
- Không block thread event bằng tác vụ mạng hoặc xử lý dài.
- Khi event dispatch async, không thao tác KafkaConsumer từ thread khác.
- Dùng supervisor và backoff nếu cần restart, không restart tức thì ở mọi stop.
- Với FENCED, sửa transactional producer identity và lifecycle trước khi retry.
- Với AUTH, kiểm tra credentials/ACL và chính sách retry xác thực.
- Với NO_OFFSET, chọn reset position theo chính sách dữ liệu.
- Kết hợp event với container running state, consumer group member count, lag và oldest record age.
- Bảo đảm monitoring bên ngoài vẫn phát hiện process crash dù không có event.
- Kiểm thử shutdown bình thường, concurrent children, lỗi auth/fenced/no-offset và khả năng khởi động lại.

**ConsumerStoppedEvent giúp ứng dụng Spring Kafka nhìn thấy khoảnh khắc một consumer ngừng hoạt động cùng phân loại lý do dừng.** Nếu dùng đúng, event này là đầu vào hữu ích cho logging, metrics, cảnh báo và runbook. Độ tin cậy thực tế vẫn phụ thuộc vào committed offsets, cơ chế recovery, lifecycle container, producer transaction fencing và khả năng theo dõi từ bên ngoài JVM khi process dừng đột ngột.
