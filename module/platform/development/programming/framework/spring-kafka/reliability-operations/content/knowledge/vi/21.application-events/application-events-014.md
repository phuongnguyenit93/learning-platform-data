# Event listener của tất cả container trong Spring Kafka

Spring Kafka không chỉ chuyển các record từ topic tới phương thức @KafkaListener. **Listener container còn phát ra những Spring application events** phản ánh vòng đời consumer, trạng thái idle, pause/resume, bất thường của vòng poll và một số tình huống vận hành khác.

Khi ứng dụng có nhiều @KafkaListener, nhiều topics, nhiều consumer groups hoặc một ConcurrentMessageListenerContainer với nhiều child consumers, việc viết một observer riêng cho từng listener thường gây lặp code và dễ bỏ sót. Một **event listener ở cấp ứng dụng** có thể nhận sự kiện từ **tất cả listener containers cùng công bố event vào Spring ApplicationContext đó**, từ đó tập trung logging, metrics, alerts và điều khiển vận hành.

Trong module **Spring Kafka Reliability Operations**, bài học **Event listener của tất cả container** tập trung vào cách xây một observer dùng @EventListener hoặc ApplicationListener để giám sát mọi container, cách phân biệt các nguồn sự kiện, tránh xử lý trùng, bảo vệ consumer thread, và sử dụng sự kiện đúng mục đích.

**Điểm cần phân biệt ngay:** @KafkaListener nhận **Kafka records** từ broker; @EventListener nhận **Spring application events** được phát trong ứng dụng. Một ApplicationEvent không phải Kafka record, không có Kafka offset riêng, và không được lưu bền vững trong Kafka.

## 1. Hai cơ chế listener không giống nhau

Một ứng dụng có thể có hai kiểu listener song song:

~~~text
Kafka broker
    |
    +--> orders.events
    |        |
    |        v
    |   @KafkaListener onOrder(...)
    |
    +--> payments.events
    |        |
    |        v
    |   @KafkaListener onPayment(...)
    |
    +--> notifications.events
             |
             v
        @KafkaListener onNotification(...)


Spring Kafka listener containers
    |
    +--> ConsumerStartedEvent
    +--> ListenerContainerIdleEvent
    +--> ConsumerPausedEvent
    +--> NonResponsiveConsumerEvent
    +--> ConsumerStoppedEvent
             |
             v
     Spring ApplicationEventPublisher
             |
             v
      @EventListener observer
             |
             +--> logs / metrics / alerts
~~~

Sự khác biệt:

| Tiêu chí | @KafkaListener | Spring @EventListener |
|---|---|---|
| Nguồn dữ liệu | Kafka topics/partitions | Spring ApplicationContext event publisher |
| Kiểu dữ liệu | Kafka ConsumerRecord hoặc payload | Java event object |
| Dùng để | Xử lý nghiệp vụ khi có record | Quan sát vòng đời và tình trạng container |
| Offset/ack | Có Kafka offset và chính sách commit | Không có offset hoặc Kafka ack riêng |
| Consumer group | Listener container tham gia group | Observer không tự tham gia Kafka group |
| Phạm vi | Theo topics/listener endpoint | Theo loại event, trong ApplicationContext |
| Độ bền | Kafka lưu record theo retention | Application events mặc định là tín hiệu tại runtime |
| Retry | Qua listener error handling/recovery | Không có Kafka retry semantics tự động |

Một event listener không phải kênh thay thế để xử lý OrderCreated hoặc PaymentAuthorized. Nó chỉ nên làm công việc vận hành liên quan tới **container phát sự kiện**.

## 2. Vì sao một event listener có thể quan sát tất cả containers?

Spring Kafka listener containers phát các event dựa trên cơ chế Spring ApplicationEventPublisher. Spring sẽ chuyển event đến các bean đăng ký nhận đúng loại event trong application context.

Ví dụ một ứng dụng có ba Kafka listener endpoints:

~~~java
@Component
public class BusinessListeners {

    @KafkaListener(
            id = "orderListener",
            topics = "orders.events",
            groupId = "orders-service"
    )
    public void onOrder(OrderEvent event) {
        orderService.handle(event);
    }

    @KafkaListener(
            id = "paymentListener",
            topics = "payments.events",
            groupId = "payments-service"
    )
    public void onPayment(PaymentEvent event) {
        paymentService.handle(event);
    }

    @KafkaListener(
            id = "notificationListener",
            topics = "notifications.events",
            groupId = "notifications-service"
    )
    public void onNotification(NotificationEvent event) {
        notificationService.handle(event);
    }
}
~~~

Một Spring bean khác đăng ký:

~~~java
@Component
public class AllKafkaContainerEventObserver {

    private static final Logger log =
            LoggerFactory.getLogger(AllKafkaContainerEventObserver.class);

    @EventListener
    public void onKafkaEvent(KafkaEvent event) {
        log.debug(
                "Kafka event: type={}, source={}",
                event.getClass().getSimpleName(),
                event.getSource()
        );
    }
}
~~~

**KafkaEvent** là lớp cơ sở cho các application events của Spring Kafka. Khi Spring publish một event thuộc hệ phân cấp đó, phương thức nhận KafkaEvent có thể nhận các subtype tương ứng.

Observer này không cần biết trước ba listener IDs. Nó cũng không cần đăng ký với từng @KafkaListener method. Khi listener container phù hợp phát event vào cùng ApplicationContext, Spring event mechanism sẽ định tuyến tới observer.

Tuy nhiên, phạm vi **tất cả containers** ở đây có nghĩa là các containers publish event vào **ApplicationContext mà bean đang lắng nghe**, không phải tất cả containers của mọi JVM, mọi Kubernetes pod hoặc mọi microservice trong hệ thống.

## 3. Hai cách đăng ký observer toàn cục

### 3.1. Dùng @EventListener

Đây thường là cách dễ đọc nhất:

~~~java
@Component
public class KafkaLifecycleObserver {

    @EventListener
    public void onAnyKafkaEvent(KafkaEvent event) {
        recordInternalEvent(
                event.getClass().getSimpleName(),
                event.getSource()
        );
    }

    private void recordInternalEvent(String type, Object source) {
        // Ghi log hoặc cập nhật metric nhẹ.
    }
}
~~~

Nếu muốn chỉ nhận một vài loại sự kiện, khai báo nhiều methods với kiểu cụ thể:

~~~java
@Component
public class KafkaOperationsEvents {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaOperationsEvents.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.warn(
                "Kafka listener idle: listenerId={}, idleTimeMs={}",
                event.getListenerId(),
                event.getIdleTime()
        );
    }

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.error(
                "Kafka consumer may be blocked: source={}",
                event.getSource()
        );
    }

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        log.info(
                "Kafka consumer paused: source={}, partitions={}",
                event.getSource(),
                event.getPartitions()
        );
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        log.info(
                "Kafka consumer resumed: source={}, partitions={}",
                event.getSource(),
                event.getPartitions()
        );
    }
}
~~~

Các methods trên sẽ được gọi cho sự kiện cùng kiểu phát từ mọi container tương ứng trong application context. Code minh họa những API quen thuộc của Spring Kafka; event classes và các accessor khả dụng phụ thuộc phiên bản dependency.

### 3.2. Dùng ApplicationListener

Nếu muốn một class theo contract interface:

~~~java
@Component
public class AllKafkaEventsListener
        implements ApplicationListener<KafkaEvent> {

    private static final Logger log =
            LoggerFactory.getLogger(AllKafkaEventsListener.class);

    @Override
    public void onApplicationEvent(KafkaEvent event) {
        log.debug(
                "Kafka application event: type={}, source={}",
                event.getClass().getSimpleName(),
                event.getSource()
        );
    }
}
~~~

Cả hai cách đều dựa trên Spring event publication, không tiêu thụ records trực tiếp từ Kafka. Có thể chọn một cách cho observer chung. Không nên đăng ký hai handlers cùng phát một metric giống nhau mà không biết chúng **cùng nhận một event**; điều đó có thể làm số liệu bị đếm đôi.

### Khi nào nên chọn cách nào?

| Cách | Lợi thế | Lưu ý |
|---|---|---|
| @EventListener(KafkaEvent) | Một điểm thu thập event tổng quát | Cần phân loại subtype để tránh logs quá nhiều |
| @EventListener(ConcreteEvent) | Handler chuyên biệt, rõ loại sự kiện | Nhiều methods hơn |
| ApplicationListener<KafkaEvent> | Contract Java interface tường minh | Cần một phương thức điều phối |
| ApplicationListener<ConcreteEvent> | Phù hợp một trách nhiệm cụ thể | Không bao phủ mọi event type |
| ApplicationEventMulticaster tùy biến | Điều chỉnh cách phát events toàn app | Có thể thay đổi thread và failure semantics |

Với hệ thống vận hành thực tế, thường nên dùng **typed listeners** cho các sự kiện cần hành động riêng, và một observer tổng quát chỉ cho logging/metrics có giới hạn.

## 4. Các nhóm sự kiện container thường gặp

Không phải mọi phiên bản Spring Kafka đều có cùng tập event classes. Một số event được bổ sung ở phiên bản mới hơn. Bảng sau mô tả các nhóm thường gặp trong Spring Kafka hiện đại:

| Event class / nhóm | Khi nào phát | Cách sử dụng |
|---|---|---|
| ConsumerStartingEvent | Consumer thread/container sắp khởi động | Theo dõi thời gian khởi động |
| ConsumerStartedEvent | Consumer đã bắt đầu vòng đời | Đếm consumers hoạt động |
| ConsumerStoppingEvent | Consumer đang dừng | Ghi nhận shutdown |
| ConsumerStoppedEvent | Consumer đã dừng | Quan sát lý do dừng nếu event hỗ trợ |
| ContainerStoppedEvent | Container đã stop | Phân biệt shutdown bình thường/bất thường |
| ListenerContainerIdleEvent | Container không nhận record trong khoảng được cấu hình | Theo dõi luồng ít traffic hoặc nghi ngờ upstream |
| ListenerContainerNoLongerIdleEvent | Record xuất hiện trở lại sau idle | Kết thúc trạng thái idle |
| ListenerContainerPartitionIdleEvent | Một partition được theo dõi bị idle | Quan sát theo partition |
| ListenerContainerPartitionNoLongerIdleEvent | Partition có record trở lại | Xóa trạng thái idle theo partition |
| ConsumerPausedEvent | Consumer/container được pause | Theo dõi backpressure |
| ConsumerResumedEvent | Consumer/container resume | Đo thời gian pause |
| ConsumerPartitionPausedEvent | Một partition được pause | Điều tra partition-level throttling |
| ConsumerPartitionResumedEvent | Một partition được resume | Đánh dấu partition hoạt động lại |
| NonResponsiveConsumerEvent | Consumer poll không tiến triển theo ngưỡng monitor | Cảnh báo nguy cơ thread bị block |
| ConsumerFailedToStartEvent | Consumer không thể start theo thời hạn cấu hình | Cảnh báo lỗi khởi động |
| ListenerContainerAuthEvent | Sự cố xác thực/ủy quyền được container phản ánh | Cảnh báo security/configuration |

Các tên và kiểu event có thể khác theo phiên bản Spring Kafka. Cần đối chiếu thư viện thực tế trước khi thêm import hoặc dựa vào một event đã xuất hiện ở version mới.

Đặc biệt, **không phải mọi exception trong listener đều tự động sinh ra application event tương ứng**. Lỗi xử lý từng record vẫn cần CommonErrorHandler, DefaultErrorHandler, recovery/DLT và cơ chế log/metrics riêng.

## 5. Ví dụ cấu hình idle event cho tất cả listeners dùng chung factory

Spring Kafka chỉ phát một số event sau khi đã bật hoặc thiết lập ngưỡng tương ứng. Chẳng hạn, ListenerContainerIdleEvent cần idleEventInterval.

Có thể đặt trên ConcurrentKafkaListenerContainerFactory được dùng bởi nhiều listeners:

~~~java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, Object>
    kafkaListenerContainerFactory(
            ConsumerFactory<String, Object> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, Object>();

        factory.setConsumerFactory(consumerFactory);

        factory.getContainerProperties().setIdleEventInterval(60_000L);

        return factory;
    }
}
~~~

Ví dụ này yêu cầu listener factory thực sự được những endpoints cần quan sát sử dụng. Factory dùng chung giúp áp idle interval cho mọi container được tạo từ nó.

Khi có nhiều factories khác nhau, cấu hình ở **một factory** sẽ không tự áp dụng cho những listeners dùng factory khác. Observer @EventListener vẫn có thể nhận events từ mọi factories, nhưng mỗi container chỉ publish những event mà bản thân nó đã được cấu hình để phát.

Một listener chỉ rõ factory:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        groupId = "orders-service",
        containerFactory = "kafkaListenerContainerFactory"
)
public void onOrder(OrderEvent event) {
    orderService.handle(event);
}
~~~

Đừng nhầm **phạm vi nhận event toàn cục** với **phạm vi áp dụng cấu hình idle threshold**. Đây là hai quyết định riêng biệt.

## 6. Idle event không có nghĩa consumer bị lỗi

ListenerContainerIdleEvent thường được phát khi consumer không nhận record trong khoảng thời gian định trước. Đó có thể là điều bình thường:

- Topic ít được publish.
- Nghiệp vụ chỉ có sự kiện theo giờ.
- Producer tạm không có dữ liệu.
- Partition được phân chia nhưng không có traffic.
- Consumer đang pause hoặc đợi dữ liệu theo trạng thái hợp lệ.

Ví dụ:

~~~text
orders.events:
  09:00 event A
  09:01 event B
  09:02 ...
  09:03 không có event
  09:04 không có event
           |
           v
ListenerContainerIdleEvent
~~~

Nếu topic vốn chỉ có vài event mỗi ngày, idle sau 60 giây không phải incident. Ngược lại, với một luồng thanh toán có traffic liên tục, không có record trong nhiều phút có thể cần điều tra upstream producer hoặc broker connectivity.

Cần đặt ngưỡng và chính sách cảnh báo **theo đặc điểm từng luồng**, ngay cả khi observer nhận event từ tất cả containers.

### Ví dụ observer idle chuyên dụng

~~~java
@Component
public class KafkaIdleEventHandler {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaIdleEventHandler.class);

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info(
                "Kafka listener idle: listener={}, idleMs={}, partitions={}",
                event.getListenerId(),
                event.getIdleTime(),
                event.getTopicPartitions()
        );
    }

    @EventListener
    public void onNoLongerIdle(
            ListenerContainerNoLongerIdleEvent event) {

        log.info(
                "Kafka listener no longer idle: listener={}",
                event.getListenerId()
        );
    }
}
~~~

Không dùng idle event để tự động reset offset hoặc skip records. Nó là tín hiệu trạng thái chứ không phải chỉ thị dữ liệu bị hỏng.

## 7. NonResponsiveConsumerEvent khác ListenerContainerIdleEvent

Đây là cặp sự kiện đặc biệt quan trọng trong reliability.

**Idle:** Consumer vẫn có thể poll bình thường nhưng không nhận được record mới.

**Non-responsive:** Một monitor phát hiện consumer đã không thực hiện vòng poll trong khoảng thời gian đáng ngờ so với poll timeout và ngưỡng đã cấu hình.

~~~text
Trường hợp A: IDLE

poll() --> không có record
poll() --> không có record
poll() --> không có record
           |
           v
ListenerContainerIdleEvent
           |
           +--> Consumer vẫn poll


Trường hợp B: NON-RESPONSIVE

poll() --> listener xử lý
                 |
                 +--> SQL query treo
                 +--> Thread.sleep dài
                 +--> Deadlock
                 |
          không quay lại poll đúng hạn
                 |
                 v
        NonResponsiveConsumerEvent
~~~

NonResponsiveConsumerEvent là **dấu hiệu cần điều tra**, không phải chứng cứ chắc chắn rằng consumer đã mất group membership. Nó có thể xuất hiện do listener đang chạy lâu, consumer thread bị block, system pause hoặc những yếu tố scheduling khác.

### Cấu hình monitor

Spring Kafka có các tùy chọn monitor interval và no-poll threshold. Ví dụ minh họa cấu hình ở factory:

~~~java
factory.getContainerProperties().setMonitorInterval(30);
factory.getContainerProperties().setNoPollThreshold(3.0f);
~~~

Ngưỡng được đánh giá tương quan với thời gian poll timeout của container. Tên API và kiểu tham số cần được kiểm tra theo phiên bản đang dùng.

Một observer:

~~~java
@Component
public class KafkaPollHealthObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaPollHealthObserver.class);

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.error(
                "Kafka consumer may be non-responsive; source={}",
                event.getSource()
        );
    }
}
~~~

Khi nhận sự kiện, nên thu thập thread dump, đo listener latency, xem JDBC connection/query timeouts, kiểm tra CPU/GC pause và đánh giá consumer lag. Không tự động kill/restart mọi container chỉ vì một event đơn lẻ nếu chưa có cơ chế chống restart loops.

## 8. Lifecycle events giúp giám sát container khởi động và dừng

Với nhiều listeners, chỉ nhìn trạng thái Spring Boot application RUNNING chưa đủ. Một Kafka listener container có thể gặp lỗi khi start, dừng hoặc chưa được assign partitions.

Các event liên quan đến lifecycle giúp nhận diện:

~~~text
Application start
       |
       v
ConsumerStartingEvent
       |
       v
ConsumerStartedEvent
       |
       v
RUNNING
       |
       +--> Stop requested
       |       |
       |       v
       | ConsumerStoppingEvent
       |       |
       |       v
       | ConsumerStoppedEvent
       |
       v
ContainerStoppedEvent
~~~

Một số sự kiện có thể được phát theo từng child consumer khi container có concurrency cao. Không nên kết luận "toàn bộ listener đã stop" chỉ vì nhận một ConsumerStoppedEvent từ một child.

Ví dụ logging:

~~~java
@Component
public class KafkaConsumerLifecycleLogger {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaConsumerLifecycleLogger.class);

    @EventListener
    public void onStarted(ConsumerStartedEvent event) {
        log.info("Kafka consumer started: source={}", event.getSource());
    }

    @EventListener
    public void onStopped(ConsumerStoppedEvent event) {
        log.warn(
                "Kafka consumer stopped: source={}, reason={}",
                event.getSource(),
                event.getReason()
        );
    }

    @EventListener
    public void onContainerStopped(ContainerStoppedEvent event) {
        log.info("Kafka container stopped: source={}", event.getSource());
    }
}
~~~

ConsumerStoppedEvent trong các phiên bản hỗ trợ có thể cung cấp reason để phân biệt một số nguyên nhân dừng. Không hard-code mọi giá trị enum vào dashboard nếu chưa xác nhận version. Một consumer bị dừng do shutdown chủ động không nên phát cảnh báo cùng mức với consumer dừng bất thường.

## 9. Pause/resume events phục vụ backpressure

Các event pause/resume hữu ích khi hệ thống chủ động hạn chế tải:

~~~text
Database saturation
       |
       v
Container.pause()
       |
       v
ConsumerPausedEvent
       |
       v
Kafka tiếp tục poll trong trạng thái pause
       |
       v
Database recovered
       |
       v
Container.resume()
       |
       v
ConsumerResumedEvent
~~~

Observer toàn cục có thể:

- Ghi lại lý do pause từ hệ thống điều khiển của ứng dụng.
- Đo thời gian consumer được pause.
- Báo cáo số partitions đang pause.
- Phát hiện container bị pause lâu hơn SLO.
- Đối chiếu consumer lag với khoảng thời gian pause.
- Phân biệt pause để backpressure với pause vì retry/backoff.

Ví dụ:

~~~java
@Component
public class KafkaPauseResumeObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaPauseResumeObserver.class);

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        log.info(
                "Kafka paused; source={}, partitions={}",
                event.getSource(),
                event.getPartitions()
        );
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        log.info(
                "Kafka resumed; source={}, partitions={}",
                event.getSource(),
                event.getPartitions()
        );
    }
}
~~~

**Một ConsumerPausedEvent không đồng nghĩa tất cả child containers trong ứng dụng đã pause.** Hãy xác định source, partition assignment và container liên quan.

Không gọi Consumer.pause() hoặc Consumer.resume() trực tiếp từ observer chạy ở thread khác. Khi muốn điều khiển container, dùng Spring Kafka MessageListenerContainer.pause()/resume() qua reference hoặc KafkaListenerEndpointRegistry, và xác định rõ các lý do pause khác nhau để tránh resume nhầm.

## 10. Mọi container trong một ứng dụng không giống mọi consumer trong cluster

Một Spring Boot service có thể chạy nhiều replicas:

~~~text
Kubernetes Deployment: orders-service

Pod A                         Pod B
  Spring ApplicationContext     Spring ApplicationContext
  @KafkaListener order          @KafkaListener order
  @KafkaListener payment        @KafkaListener payment
  Event observer A              Event observer B

         |                              |
         +--------------+---------------+
                        |
                    Kafka cluster
~~~

Observer A chỉ nhận application events được publish trong context mà A đang nghe. Nó không trực tiếp nhận sự kiện nội bộ của listener container ở Pod B.

Do đó:

- **Trong một pod/context:** @EventListener có thể quan sát nhiều containers.
- **Giữa nhiều pods:** gom logs/metrics/traces về hệ observability như Prometheus, OpenTelemetry hoặc log aggregator.
- **Giữa nhiều services:** dùng hệ giám sát tập trung hoặc một event bus nghiệp vụ nếu thật sự cần tín hiệu liên dịch vụ.
- **Giữa nhiều ApplicationContexts trong một JVM:** phải hiểu cơ chế event propagation của Spring, không mặc định mọi context đều nhận nhau.

Spring application events thường có khả năng propagate từ child context lên parent context, nhưng không tự broadcast hai chiều tới mọi sibling contexts. Nếu dùng child/parent contexts, đặt observer ở context phù hợp và kiểm tra event propagation thực tế.

## 11. Concurrent container có thể phát nhiều events cho cùng listener ID

Với:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        concurrency = "3"
)
public void onOrder(OrderEvent event) {
    orderService.handle(event);
}
~~~

Spring Kafka có thể tạo một ConcurrentMessageListenerContainer chứa ba child containers, tương ứng với các Kafka consumers riêng.

~~~text
ordersListener (parent)
     |
     +--> child consumer 0 --> partitions P0, P1
     |
     +--> child consumer 1 --> partitions P2, P3
     |
     +--> child consumer 2 --> partitions P4, P5
~~~

Một event lifecycle hoặc pause có thể là trạng thái của **một child consumer**, không phải toàn parent. Khi tính số consumers đang chạy, nên định danh theo source/child ID hoặc client ID ổn định thay vì chỉ group ID.

Nếu chỉ lưu:

~~~text
ordersListener = RUNNING
~~~

thì khi một trong ba consumers dừng bất thường, thông tin sẽ mất độ chi tiết. Nên có mô hình:

~~~text
ordersListener / consumer 0 = RUNNING
ordersListener / consumer 1 = STOPPED
ordersListener / consumer 2 = RUNNING
~~~

Cách lấy child identity phụ thuộc Spring Kafka version, listener ID và container source của event. Khi làm metrics, hãy dùng các nhãn có tập giá trị hữu hạn như application, listener và client/child index; không dùng partition offset hoặc eventId làm tag.

## 12. Nhận diện nguồn sự kiện để biết container nào phát event

Một observer tổng quát phải xác định tối thiểu:

1. Event type.
2. Listener container source.
3. Listener ID khi event hỗ trợ.
4. Topic/partitions liên quan khi event hỗ trợ.
5. Consumer client/group identity nếu cần để điều tra.
6. Application instance/pod ID trong hệ thống triển khai.

Ví dụ event idle cung cấp listener ID:

~~~java
@EventListener
public void onIdle(ListenerContainerIdleEvent event) {

    String listenerId = event.getListenerId();

    log.info(
            "Idle: listener={}, durationMs={}, partitions={}",
            listenerId,
            event.getIdleTime(),
            event.getTopicPartitions()
    );
}
~~~

Với sự kiện không có getListenerId, có thể ghi nhận event.getSource() và ánh xạ nguồn theo container lifecycle metadata. Tránh ép mọi event type có cùng tập accessors khi API thực tế không hỗ trợ.

Không parse listener ID bằng cách giả định mọi ID đều có một hậu tố cố định. Với concurrent containers, Spring Kafka có thể dùng hậu tố cho child containers; định danh thực tế cần được ghi nhận theo version và cấu hình container.

### Lọc event theo listener cụ thể

Một global observer có thể nhận mọi idle event, nhưng chỉ cảnh báo cho topic nghiệp vụ quan trọng:

~~~java
@EventListener
public void onCriticalListenerIdle(
        ListenerContainerIdleEvent event) {

    String listenerId = event.getListenerId();

    if (!listenerId.startsWith("paymentsListener")) {
        return;
    }

    log.warn(
            "Critical listener idle: id={}, idleMs={}",
            listenerId,
            event.getIdleTime()
    );
}
~~~

Ví dụ dùng tiền tố vì listener ID có thể chứa suffix của child consumer. Trong production, nên dùng policy mapping rõ ràng theo listener IDs hoặc metadata do ứng dụng quản lý, không phụ thuộc parser tên dễ thay đổi mà không có kiểm soát.

Lọc theo event type và source là cách tái sử dụng một observer mà vẫn có ngưỡng vận hành khác nhau cho orders, payments và notifications.

## 13. Theo dõi nhiều container factories

Một ứng dụng thực tế thường có nhiều factories:

~~~text
orderListenerFactory
    +--> ordersListener

paymentListenerFactory
    +--> paymentsListener

batchListenerFactory
    +--> settlementBatchListener
~~~

Nếu mỗi factory có idle interval khác nhau, global observer có thể nhận events từ tất cả containers nhưng tần suất events cũng khác.

Ví dụ:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
orderListenerFactory(
        ConsumerFactory<String, OrderEvent> cf) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderEvent>();

    factory.setConsumerFactory(cf);
    factory.getContainerProperties().setIdleEventInterval(60_000L);

    return factory;
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, PaymentEvent>
paymentListenerFactory(
        ConsumerFactory<String, PaymentEvent> cf) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, PaymentEvent>();

    factory.setConsumerFactory(cf);
    factory.getContainerProperties().setIdleEventInterval(15_000L);

    return factory;
}
~~~

Cùng một @EventListener(ListenerContainerIdleEvent) có thể nhận events từ cả hai nhóm factories nếu chúng publish event trong cùng context. Chính sách cảnh báo có thể xác định payments idle 15 giây là đáng chú ý nhưng orders idle 60 giây chỉ là thông tin.

Cần nhớ factory configuration là nơi thiết lập **điều kiện phát event**, còn observer quyết định **cách phản ứng khi event xuất hiện**.

## 14. Thread model của Spring ApplicationEvents

Spring event publication thông thường dùng ApplicationEventMulticaster. Với thiết lập mặc định phổ biến, event listeners được gọi **đồng bộ** trên thread phát event, trừ khi ứng dụng cấu hình khác hoặc một kiểu event có semantics riêng.

Với Spring Kafka, nhiều events được phát từ thread của Kafka consumer/container. Khi đó code trong @EventListener có thể đang chạy **trên chính thread cần tiếp tục poll và xử lý records**.

~~~text
Kafka consumer thread
        |
        +--> poll()
        |
        +--> Spring Kafka publish ConsumerPausedEvent
        |         |
        |         v
        |   @EventListener chạy đồng bộ
        |         |
        |         +--> ghi log nhẹ
        |         +--> cập nhật counter
        |
        +--> trở lại consumer loop
~~~

Nếu observer gọi HTTP tới hệ alerting và chờ 30 giây, consumer thread có thể bị chặn, làm poll trễ và tăng nguy cơ vượt max.poll.interval.ms.

**Quy tắc:** Event handlers nên nhanh, có giới hạn và không thực hiện I/O dài. Những tác vụ như gửi Slack/email, gọi incident API hoặc truy vấn database nên được chuyển sang một cơ chế bất đồng bộ có queue và timeout được kiểm soát.

Không gửi toàn bộ KafkaEvent object hoặc Consumer instance sang một worker thread rồi thao tác consumer ở đó. KafkaConsumer không được dùng tùy tiện từ thread khác, và event có thể chứa reference tới object chỉ an toàn trong lifecycle hiện tại.

## 15. Cẩn thận khi cấu hình asynchronous ApplicationEventMulticaster

Một ứng dụng có thể cấu hình SimpleApplicationEventMulticaster với TaskExecutor để dispatch events bất đồng bộ. Điều đó thay đổi context thread của observer và có thể ảnh hưởng cả những application events khác, không riêng Spring Kafka.

~~~text
Kafka consumer thread
        |
        +--> publish(event)
                 |
                 v
          Async event executor
                 |
                 +--> observer thread
~~~

Lợi ích:

- Observer I/O không nhất thiết block consumer thread.
- Dễ tách logging/alerting latency khỏi poll loop.

Rủi ro:

- Không được gọi KafkaConsumer methods từ observer thread khác.
- Thứ tự xử lý events có thể thay đổi giữa các tasks.
- Một event có thể được xử lý sau khi container đã stop hoặc rebalance.
- Queue đầy có thể làm mất telemetry hoặc gây backpressure không mong muốn.
- Thay đổi global multicaster có thể ảnh hưởng transaction-related Spring events.
- Một số Spring events không thích hợp hoặc không được phép chạy bất đồng bộ theo contract của framework.

Do đó, nếu chỉ cần gửi alert bất đồng bộ, thường an toàn hơn khi **typed @EventListener ghi nhận một snapshot nhỏ** rồi đẩy thông tin vào bounded queue riêng. Không thay đổi toàn bộ application event multicaster nếu chưa hiểu tác động đến các Spring components khác.

## 16. Ví dụ chuyển alert sang cơ chế bất đồng bộ an toàn

Giả sử một NonResponsiveConsumerEvent cần cảnh báo tới hệ thống bên ngoài. Không nên gọi API cảnh báo trực tiếp trong event handler:

~~~java
@EventListener
public void onNonResponsive(NonResponsiveConsumerEvent event) {
    incidentClient.createIncident(event); // Không nên làm trực tiếp.
}
~~~

Một hướng phù hợp hơn là tạo **snapshot dữ liệu thuần**:

~~~java
public record KafkaContainerAlert(
        String type,
        String source,
        Instant observedAt
) {}
~~~

Handler:

~~~java
@Component
public class KafkaContainerAlertPublisher {

    private final KafkaAlertQueue queue;

    public KafkaContainerAlertPublisher(KafkaAlertQueue queue) {
        this.queue = queue;
    }

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {

        KafkaContainerAlert alert = new KafkaContainerAlert(
                "NON_RESPONSIVE_CONSUMER",
                String.valueOf(event.getSource()),
                Instant.now()
        );

        queue.offer(alert);
    }
}
~~~

KafkaAlertQueue đại diện bounded queue hoặc publisher được ứng dụng cài đặt, có timeout, policy khi queue đầy và metrics cho dropped alerts. Nó không mang Consumer object sang thread khác.

Ở worker khác, hệ thống có thể đọc KafkaContainerAlert rồi gọi incident API với retry/backoff phù hợp. Vì event telemetry không giống business record, cần quyết định liệu việc bỏ lỡ một alert khi process crash có chấp nhận được hay không. Nếu không, dùng durable alert outbox hoặc event storage riêng.

## 17. Không phải mọi application event đều cần một hành động sửa lỗi

Một observer toàn cục rất dễ trở thành một bộ điều khiển quá quyền, ví dụ cứ thấy idle là seek hoặc restart, thấy non-responsive là stop container, thấy pause là resume ngay.

Những phản ứng này có thể tạo vòng lỗi:

~~~text
Container idle
     |
     +--> Observer restart container
               |
               v
          Consumer rebalance
               |
               v
          Container idle lại
               |
               v
          Restart lần nữa
~~~

Nên phân nhóm phản ứng:

| Event | Phản ứng ưu tiên | Không nên tự động |
|---|---|---|
| ConsumerStartedEvent | Ghi nhận trạng thái, đánh dấu readiness phù hợp | Đếm như business success |
| ListenerContainerIdleEvent | Quan sát traffic, đặt alert theo expected rate | Reset offset hoặc restart ngay |
| ListenerContainerNoLongerIdleEvent | Kết thúc cảnh báo idle | Gán nghĩa record đã xử lý thành công |
| NonResponsiveConsumerEvent | Thu thập thread dump, latency, cảnh báo | Kill container ở mọi lần nhận event |
| ConsumerPausedEvent | Ghi nhận pause state/duration/reason | Resume nếu có controller khác đang pause |
| ConsumerStoppedEvent | Phân biệt stop bình thường/bất thường | Restart vô hạn không cooldown |
| ListenerContainerAuthEvent | Cảnh báo thông tin bảo mật/configuration | Log credentials/token |
| ContainerStoppedEvent | Quan sát shutdown completion | Kết luận cả deployment đã dừng |

Một event phản ánh **tình trạng tại thời điểm quan sát**, không phải toàn bộ sự thật về record processing. Để quyết định retry/DLT, vẫn cần data path và error-handling mechanisms tương ứng.

## 18. Quan sát idle toàn container so với idle theo partition

Một container có thể được assign nhiều partitions. Nếu chỉ một partition không có record, nhưng các partition khác liên tục có dữ liệu, container nhìn chung chưa idle.

~~~text
Consumer A:
  P0: 100 records / second
  P1: 0 records / minute
  P2: 50 records / second
~~~

Nếu cần biết P1 ngừng có dữ liệu, các **partition idle events** (khi phiên bản hỗ trợ và được cấu hình) hữu ích hơn listener-level idle.

Các tiêu chí lựa chọn:

- **ListenerContainerIdleEvent:** theo dõi một container/consumer không có dữ liệu nói chung.
- **ListenerContainerPartitionIdleEvent:** theo dõi một partition cụ thể không có dữ liệu.
- **Consumer lag:** đo backlog Kafka theo partition.
- **Producer metrics:** xác định upstream không publish.
- **Topic retention/offsets:** xác nhận dữ liệu có hay không.

Một partition không có record có thể bình thường nếu key distribution lệch hoặc tenant ít giao dịch. Ngược lại, lag cao mà listener idle có thể cho biết partition bị pause, assignment sai, consumer mắc lỗi hoặc một vấn đề khác. Không suy diễn duy nhất từ một event.

## 19. Dùng KafkaListenerEndpointRegistry để liên hệ events với containers

KafkaListenerEndpointRegistry giúp tìm những listener containers được đăng ký bằng @KafkaListener, tra cứu theo ID và thao tác lifecycle có kiểm soát.

~~~java
@Component
public class KafkaContainerRegistryView {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaContainerRegistryView(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void listKnownContainers() {
        for (MessageListenerContainer container
                : registry.getListenerContainers()) {

            log.info(
                    "Kafka container: id={}, running={}",
                    container.getListenerId(),
                    container.isRunning()
            );
        }
    }
}
~~~

Lấy container cụ thể:

~~~java
MessageListenerContainer orders =
        registry.getListenerContainer("ordersListener");

if (orders != null && orders.isRunning()) {
    orders.pause();
}
~~~

Registry là công cụ quản lý container; **không phải bắt buộc để Spring @EventListener nhận event từ container**.

Cần chú ý: registry thường tập trung những containers được tạo từ @KafkaListener endpoints. Các container tạo thủ công dưới dạng Spring beans có thể có cách quản lý khác. Để quan sát event từ mọi container thực tế, phải đảm bảo chúng sử dụng ApplicationEventPublisher/context phù hợp.

Không dùng registry như một bảng event history. Nó phản ánh containers đang được quản lý, không lưu đầy đủ những events đã xảy ra trong quá khứ.

## 20. Event observer trong nhiều context và test environments

Một ứng dụng đơn giản thường chỉ có một ApplicationContext. Nhưng các hệ thống phức tạp có thể dùng parent/child contexts, embedded modules hoặc nhiều Spring Boot applications trong một JVM.

~~~text
Parent ApplicationContext
       |
       +--> Child Context A
       |       |
       |       +--> Kafka Container A
       |
       +--> Child Context B
               |
               +--> Kafka Container B
~~~

Spring application event propagation phụ thuộc mối quan hệ contexts. Event từ child có thể được publish lên parent; event không tự phát từ một child sang sibling child. Một observer đặt ở Child A không mặc nhiên nhận events từ Child B.

Trong integration tests, context có thể được tạo và đóng nhiều lần, làm listener containers start/stop và phát lifecycle events. Nếu observer ghi metrics vào một singleton bên ngoài context mà không reset đúng cách, test có thể bị số liệu cũ ảnh hưởng.

Khi có nhiều contexts, cần kiểm tra:

1. Container publish event vào context nào?
2. Observer bean nằm trong context nào?
3. Parent/child event propagation có phù hợp không?
4. Có nguy cơ cùng observer được tạo ở cả parent và child rồi đếm đôi không?
5. Có cần ghi application instance/context ID vào log không?

Đừng giả định "tất cả" là phạm vi toàn bộ hệ thống nếu thực tế chỉ là một Spring ApplicationContext.

## 21. Dùng ApplicationEvents làm tín hiệu monitoring, không làm event store

Spring ApplicationEvents thường không được lưu bền vững như Kafka records. Nếu JVM crash ngay sau khi phát một event, observer có thể chưa xử lý xong hoặc chưa gửi telemetry ra bên ngoài.

Do đó:

- ApplicationEvents phù hợp cho runtime monitoring, state notifications và hooks.
- Kafka broker metrics thích hợp để theo dõi partition lag, consumer membership và throughput.
- Micrometer/OpenTelemetry phù hợp cho metrics/tracing.
- Log aggregator hoặc incident platform phù hợp cho alert có lịch sử.
- Nếu một sự kiện vận hành phải được lưu chắc chắn, cần một durable outbox/topic/storage riêng.

Đừng coi việc observer đã log ConsumerStartedEvent là bằng chứng business data sẽ không bị mất. Consumer lifecycle và record-level reliability là hai mảng khác nhau.

## 22. Những event nào không phải nơi xử lý exception của record?

Một lỗi trong @KafkaListener:

~~~java
@KafkaListener(topics = "orders.events")
public void onOrder(OrderEvent event) {

    if (event.amount().signum() < 0) {
        throw new InvalidOrderException("Negative amount");
    }

    orderService.process(event);
}
~~~

Lỗi InvalidOrderException cần cơ chế như DefaultErrorHandler, retry/recoverer và DLT. Không thể kỳ vọng có một ConsumerStoppedEvent hoặc ListenerContainerIdleEvent tương ứng cho mỗi record lỗi.

Luồng đúng:

~~~text
Record listener
     |
     +--> Exception
     |
     v
DefaultErrorHandler / AfterRollbackProcessor
     |
     +--> Retry
     |
     +--> DLT / recovery
     |
     v
Offset policy

ApplicationEvents
     |
     +--> Container idle
     +--> Pause/resume
     +--> Lifecycle
     +--> Poll health
     |
     v
Logs / metrics / alerts
~~~

Tách rõ hai luồng giúp tránh một observer toàn cục vô tình skip record hoặc tự seek consumer không đúng thời điểm.

Với transactional container, lỗi xử lý record cần làm transaction rollback theo cấu hình, sau đó AfterRollbackProcessor có thể quyết định redelivery/recovery. Application event listener không thay thế transaction/error lifecycle.

## 23. Xử lý lỗi bên trong event observer

Nếu một @EventListener handler ném exception trong mô hình event dispatch đồng bộ, exception có thể lan tới thread publish event hoặc error handling của ApplicationEventMulticaster, tùy cấu hình.

Một handler chỉ để logging/metrics không nên khiến consumer thread thất bại vì telemetry server không sẵn sàng.

Ví dụ thiết kế:

~~~java
@Component
public class SafeKafkaEventObserver {

    private static final Logger log =
            LoggerFactory.getLogger(SafeKafkaEventObserver.class);

    private final KafkaContainerMetrics metrics;

    public SafeKafkaEventObserver(KafkaContainerMetrics metrics) {
        this.metrics = metrics;
    }

    @EventListener
    public void onStopped(ConsumerStoppedEvent event) {
        try {
            metrics.recordConsumerStopped(
                    String.valueOf(event.getSource()),
                    event.getReason().name()
            );
        }
        catch (RuntimeException ex) {
            log.warn(
                    "Could not publish consumer stopped metric",
                    ex
            );
        }
    }
}
~~~

KafkaContainerMetrics đại diện một abstraction nội bộ; không nên cho nó gọi HTTP đồng bộ lâu trên consumer thread. Đưa telemetry tới bounded queue hoặc local in-memory metrics registry thường phù hợp hơn.

Lỗi từ observer phải được đánh giá theo mức độ: không nuốt những lỗi ảnh hưởng tới business transaction nếu event là một hook bắt buộc cho nghiệp vụ; ngược lại, hầu hết operational telemetry không nên ngăn Kafka consumer tiếp tục poll.

## 24. Giám sát và cảnh báo không tạo metrics cardinality quá lớn

Một observer nhận events từ mọi listeners có thể xuất những metrics:

| Metric | Tag hữu ích |
|---|---|
| kafka_container_started_total | application, listener, reason/source category |
| kafka_container_stopped_total | application, listener, stop reason |
| kafka_container_idle_total | application, listener |
| kafka_container_nonresponsive_total | application, listener |
| kafka_container_pause_total | application, listener, reason |
| kafka_container_paused_seconds | application, listener |
| kafka_container_resume_total | application, listener |
| kafka_partition_idle_total | application, topic, partition hoặc partition band |
| kafka_container_alert_dropped_total | application, alert type |

Tên metric trên là ví dụ custom, không phải bảo đảm Spring Kafka tự phát sẵn đúng những tên đó.

Tránh các tags có số giá trị không giới hạn:

- Record key.
- Event ID.
- Kafka offset.
- Raw exception message có chứa request ID.
- Dynamic client ID không giới hạn.
- Topic name do input tùy ý điều khiển.

Lựa chọn tags phải phù hợp quy mô topics, partitions và replica count. Nếu hàng nghìn partitions, xuất một time series cho từng partition có thể rất tốn chi phí; cân nhắc tổng hợp theo topic/group hoặc dùng dashboard chuyên biệt.

### Gợi ý alert severity

- **Info:** consumer start/stop trong rolling deployment dự kiến.
- **Warning:** listener quan trọng idle lâu hơn SLO; pause kéo dài vượt ngưỡng.
- **Critical:** consumer non-responsive kéo dài kết hợp với lag tăng; authentication failures; container unexpected stop.
- **Recovery:** no-longer-idle, consumer resumed, restart thành công sau incident.

Không phát page trực tiếp cho mọi idle event nếu topic bình thường ít traffic.

## 25. Phân loại theo trạng thái và sự kiện để xây runbook

Một runbook đơn giản:

~~~text
Event: NonResponsiveConsumerEvent
    |
    +--> Kiểm tra thread dump / long-running listener
    |
    +--> Kiểm tra max.poll.interval.ms và poll timeout
    |
    +--> Kiểm tra DB query/connection timeout
    |
    +--> Kiểm tra consumer lag và rebalance
    |
    +--> Quyết định xử lý theo trạng thái thực


Event: ConsumerPausedEvent
    |
    +--> Kiểm tra pause reason
    |
    +--> Xác định container/partition
    |
    +--> Xem DB/backpressure/retry state
    |
    +--> Theo dõi paused duration và lag
    |
    +--> Resume khi mọi lý do pause đã hết


Event: ConsumerStoppedEvent
    |
    +--> Xem reason và shutdown context
    |
    +--> Phân biệt rolling deploy với unexpected stop
    |
    +--> Kiểm tra group assignment và lag
    |
    +--> Alert/restart theo policy đã giới hạn
~~~

Điều này biến event thành tín hiệu hỗ trợ chẩn đoán, không biến handler thành một chuỗi restart không kiểm soát.

## 26. Ví dụ một observer chung có phân loại rõ ràng

Một cách kết hợp nhẹ, dùng một bean và typed handlers:

~~~java
@Component
public class GlobalKafkaContainerObserver {

    private static final Logger log =
            LoggerFactory.getLogger(GlobalKafkaContainerObserver.class);

    @EventListener
    public void onStarted(ConsumerStartedEvent event) {
        log.info(
                "Kafka consumer started; source={}",
                event.getSource()
        );
    }

    @EventListener
    public void onStopped(ConsumerStoppedEvent event) {
        log.warn(
                "Kafka consumer stopped; reason={}, source={}",
                event.getReason(),
                event.getSource()
        );
    }

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.debug(
                "Kafka listener idle; id={}, idleMs={}",
                event.getListenerId(),
                event.getIdleTime()
        );
    }

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.error(
                "Kafka consumer non-responsive; source={}",
                event.getSource()
        );
    }

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        log.info(
                "Kafka paused; source={}, partitions={}",
                event.getSource(),
                event.getPartitions()
        );
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        log.info(
                "Kafka resumed; source={}, partitions={}",
                event.getSource(),
                event.getPartitions()
        );
    }
}
~~~

Ví dụ hướng tới Spring Kafka hiện đại và Java phù hợp với ứng dụng. Cần imports cho Spring @Component, @EventListener, các classes trong org.springframework.kafka.event, Logger/LoggerFactory. Trong production, nên chuyển từ logging thuần sang metrics có nhãn hữu hạn và chỉ phát alerts cho những trường hợp vượt ngưỡng.

Lưu ý: Bean này không cần được đăng ký riêng cho từng @KafkaListener. Spring sẽ dispatch event tới nó dựa trên event type và application context.

## 27. Tránh đếm đôi khi vừa dùng handler tổng quát vừa handler chuyên biệt

Giả sử một class có:

~~~java
@EventListener
public void all(KafkaEvent event) {
    metrics.increment("kafka_events_total");
}

@EventListener
public void onIdle(ListenerContainerIdleEvent event) {
    metrics.increment("kafka_events_total");
}
~~~

Với một ListenerContainerIdleEvent, **cả hai phương thức đều có thể được gọi**, dẫn đến metric kafka_events_total tăng hai lần nếu không có policy đếm rõ ràng.

Có thể thiết kế:

- Handler tổng quát chỉ tăng một metric tổng theo event type.
- Handler chuyên biệt chỉ ghi metric chuyên biệt như idle_duration.
- Không tăng cùng counter từ nhiều handlers.
- Dùng một dispatcher duy nhất nếu cần đo mọi event đúng một lần.
- Nếu event source có parent/child hierarchy, phân biệt event của từng child với event tổng hợp do application tự tạo.

Đếm đôi trong observability cũng là lỗi reliability: dashboard có thể báo container stop hai lần và kích hoạt restart/alert policy không đúng.

## 28. Kiểm thử observer nhận events từ tất cả containers

Một test tích hợp nên tạo nhiều listener endpoints trong cùng Spring ApplicationContext, bật idle event hoặc publish một event phù hợp, rồi xác nhận observer nhận đúng loại và nguồn event.

Ví dụ kịch bản:

| Tình huống | Điều cần xác nhận |
|---|---|
| Có hai @KafkaListener cùng context | Global observer nhận events của cả hai |
| Một listener concurrency=3 | Observer thấy các child consumers khi lifecycle events được phát |
| Listener A idle, listener B có traffic | Không kết luận toàn ứng dụng bị idle |
| Consumer A pause | Observer xác định đúng source/partitions |
| Consumer B resume | Không xóa trạng thái pause của A |
| NonResponsiveConsumerEvent | Alert được tạo mà không block consumer thread |
| Handler log/metric ném exception | Data path không bị ảnh hưởng ngoài policy |
| Application shutdown bình thường | ConsumerStoppedEvent không tạo false critical alert |
| Nhiều factories, chỉ một bật idle interval | Chỉ các container đã bật interval phát idle events |
| Child/parent ApplicationContext | Event propagation không bị hiểu nhầm |
| Async event delivery | Không dùng KafkaConsumer từ thread khác |
| Observer tổng quát và typed handlers | Không đếm đôi metric giống nhau |

Với Spring Kafka, có thể sử dụng EmbeddedKafka hoặc Testcontainers Kafka để tạo tình huống start/idle/pause thực tế. Unit test chỉ gọi trực tiếp phương thức onIdle(...) không chứng minh Spring event listener registration và container event publication.

Cần kiểm tra cả listener registry state, event source, metrics, và không để test fail vì event dispatch bất đồng bộ có độ trễ mà test chưa chờ hợp lý.

## 29. Các lỗi cấu hình hay gặp

### @EventListener không nhận được sự kiện idle

Kiểm tra setIdleEventInterval có được đặt trên **đúng listener container factory** hay không. Một event không phát sẽ không thể được observer nhận, dù method signature đúng.

### Observer chỉ nhận sự kiện từ một listener

Kiểm tra observer thuộc ApplicationContext nào, các listeners dùng factories ở context nào và có các filters listener ID nào đang loại bỏ event. Không nhầm @KafkaListener topic filtering với Spring event subscription.

### Một sự kiện được ghi log nhiều lần

Có thể có nhiều observer beans, cả generic và typed event handlers, hoặc parent/child contexts cùng đăng ký. Kiểm tra số bean đăng ký và event source.

### Event handler làm consumer bị chậm

Handler đang chạy I/O đồng bộ hoặc lock quá lâu trên consumer thread. Chuyển công việc nặng sang bounded async processing và chỉ chuyển snapshot metadata.

### Idle alert nổ liên tục dù Kafka khỏe

Topic có traffic thấp, khoảng idle quá ngắn hoặc partition không có dữ liệu là điều bình thường. Điều chỉnh alert theo expected traffic và SLO.

### ConsumerPausedEvent xuất hiện nhưng toàn bộ ứng dụng không pause

Event có thể thuộc một child container hoặc partition. Xác định source/partitions trước khi suy luận.

### Application đang chạy nhưng có ConsumerStoppedEvent

Một child consumer có thể stop trong khi parent hoặc các child khác vẫn đang running. Kiểm tra reason, concurrency và trạng thái các consumers.

### NonResponsiveConsumerEvent xuất hiện sau query chậm

Listener có thể bị block và không quay lại poll. Kiểm tra JDBC timeout, max.poll.interval.ms, processing latency và thread dump. Không chỉ tăng timeout để che đi nguyên nhân.

### Observer cố gọi Consumer API từ async thread

KafkaConsumer không được dùng tùy ý từ thread khác. Sử dụng MessageListenerContainer API hoặc gửi yêu cầu tới luồng điều khiển phù hợp.

### Events không xuất hiện trong dashboard toàn cluster

Spring ApplicationEvents là local tới application context, không broadcast sang các pods khác. Export metrics/logs từ từng pod rồi tập hợp về hệ observability.

## 30. Checklist thiết kế event listener toàn cục

- Phân biệt @KafkaListener nhận records với @EventListener nhận Spring application events.
- Observer là Spring bean trong context phù hợp.
- Dùng @EventListener(KafkaEvent) hoặc ApplicationListener<KafkaEvent> nếu cần quan sát rộng.
- Dùng typed listeners cho idle, non-responsive, lifecycle, pause/resume khi cần policy riêng.
- Cấu hình idleEventInterval và monitor settings tại đúng listener factory.
- Hiểu một factory có thể tạo nhiều listener containers.
- Hiểu một concurrent container có nhiều child consumers.
- Định danh event source và listener ID, không gộp tất cả child state thành một boolean.
- Phân biệt container idle với consumer non-responsive.
- Không xem một application event là Kafka record có offset/ack.
- Không thay DefaultErrorHandler/DLT bằng observer.
- Event handlers nhẹ, không block consumer poll thread.
- Không chuyển Consumer reference sang async worker.
- Có giới hạn queue và timeout nếu phát alerts bất đồng bộ.
- Không tạo restart/pause/resume loops từ một event đơn lẻ.
- Phân biệt shutdown bình thường và unexpected stop.
- Tránh đếm đôi giữa generic và typed handlers.
- Metrics dùng labels có cardinality hữu hạn.
- ApplicationEvents được hiểu là tín hiệu local, không phải event stream toàn cluster.
- Có observability tập trung cho nhiều pods/instances.
- Đã kiểm thử multi-listener, concurrency, idle, pause, shutdown và error scenarios.

**Kết luận:** Một Spring @EventListener hoặc ApplicationListener nhận các kiểu KafkaEvent có thể đóng vai trò **observer dùng chung cho mọi listener containers trong cùng Spring ApplicationContext**, không cần sửa từng @KafkaListener. Giá trị thực tế nằm ở việc phân loại đúng idle, non-responsive, lifecycle và pause/resume; gắn event với nguồn container/partition; tránh blocking consumer thread; và chuyển những tín hiệu đó thành logging, metrics, alerts có kiểm soát. Event listener toàn cục là lớp observability của container, **không thay thế Kafka record processing, offset commit, retry hoặc DLT**.

