# Tạm dừng, tiếp tục nhận và theo dõi consumer nhàn rỗi

Một consumer Kafka không phải lúc nào cũng cần nhận dữ liệu liên tục. Ứng dụng có thể cần tạm ngừng nhận khi hệ thống phụ thuộc đang quá tải, khi triển khai bảo trì, khi cần điều tiết tốc độ xử lý hoặc khi một quy trình vận hành yêu cầu giữ backlog để xử lý sau. Sau đó, consumer phải tiếp tục từ vị trí đã lưu mà không làm mất tiến độ.

Spring Cloud Stream Kafka binder hỗ trợ tạm dừng và tiếp tục một input binding bằng vòng đời binding. Khả năng này dựa trên pause/resume của listener container trong Spring Kafka. Consumer vẫn tham gia cơ chế poll của Kafka khi đang pause, nhờ đó có thể giữ membership trong consumer group và tránh rebalance chỉ vì ứng dụng tạm ngừng nhận record.

Bài học này trình bày cách phân biệt pause với stop, điều khiển binding bằng API và Actuator, cấu hình sự kiện idle, nhận biết consumer hoạt động trở lại và theo dõi trạng thái trong vận hành.

## 1. Phân biệt pause, resume và stop

Ba thao tác có mục đích khác nhau:

| Trạng thái | Hành vi | Ảnh hưởng tới consumer group |
|---|---|---|
| **PAUSED** | Tạm ngừng lấy record mới từ Kafka. Listener container vẫn tiếp tục poll nhưng không trả record cho ứng dụng. | Consumer tiếp tục duy trì membership; thường tránh rebalance chỉ do thao tác pause. |
| **RESUMED** | Tiếp tục nhận record sau khi binding đã pause. | Consumer tiếp tục đọc từ tiến độ hiện tại theo offset đã commit và trạng thái xử lý. |
| **STOPPED** | Dừng binding và consumer container. | Consumer rời group; Kafka có thể rebalance và giao partition cho thành viên khác. |
| **STARTED** | Khởi động lại binding đã dừng. | Consumer tham gia group lại và được phân công partition theo cơ chế rebalance. |

Khi cần ngừng nhận tạm thời nhưng vẫn muốn giữ consumer trong group, hãy chọn **pause**. Khi cần dừng ứng dụng thực sự, giải phóng tài nguyên hoặc bảo trì container, **stop** có thể phù hợp hơn.

~~~mermaid
stateDiagram-v2
    [*] --> STARTED
    STARTED --> PAUSED: pause
    PAUSED --> RESUMED: resume
    RESUMED --> PAUSED: pause
    STARTED --> STOPPED: stop
    PAUSED --> STOPPED: stop
    RESUMED --> STOPPED: stop
    STOPPED --> STARTED: start
~~~

Pause không xóa record khỏi topic và không tự commit offset. Producer vẫn có thể ghi dữ liệu vào topic trong lúc consumer pause. Backlog vì vậy có thể tăng lên; khả năng lưu giữ vẫn chịu ảnh hưởng của retention, dung lượng broker và chính sách topic.

## 2. Vì sao pause không gây rebalance như stop?

Kafka consumer phải tiếp tục gọi poll() để duy trì hoạt động và tham gia group management. Nếu ứng dụng ngừng poll quá lâu, consumer có thể vượt max.poll.interval.ms, bị xem là không còn hoạt động và dẫn tới việc partition được giao lại.

Spring Kafka triển khai pause bằng cách yêu cầu container tạm dừng việc lấy record ở ranh giới poll tiếp theo. Container vẫn poll Kafka nhưng không lấy record mới trong thời gian pause. Vì thế, consumer có thể tiếp tục duy trì group membership trong khi ứng dụng tạm ngừng xử lý dữ liệu.

Các điểm cần lưu ý:

- Lệnh pause là một yêu cầu điều khiển; trạng thái pause thực tế có hiệu lực ở chu kỳ poll phù hợp tiếp theo.
- Các record đã được trả về từ lần poll trước có thể vẫn đang được xử lý trước khi trạng thái pause có hiệu lực.
- Khi resume, consumer tiếp tục lấy record theo tiến độ offset và quy tắc ACK/commit đã cấu hình.
- Nếu consumer bị dừng hẳn, mất kết nối hoặc không poll đúng hạn, Kafka vẫn có thể rebalance vì những lý do đó.
- Pause không ngăn producer gửi dữ liệu và không kéo dài retention của topic.

Spring Kafka cung cấp pause() và resume() ở listener container để điều khiển an toàn. Với ứng dụng Spring Cloud Stream, nên điều khiển qua vòng đời binding thay vì tự lấy Kafka Consumer từ header rồi gọi trực tiếp từ một thread tùy ý.

## 3. Xác định đúng input binding cần điều khiển

Giả sử ứng dụng khai báo function consumer:

~~~java
@Bean
public Consumer<OrderCreated> ordersConsumer(OrderService service) {
    return service::handle;
}
~~~

Với function tên ordersConsumer, input binding mặc định là:

~~~text
ordersConsumer-in-0
~~~

Binding này có thể được cấu hình nhận từ topic orders:

~~~yaml
spring:
  cloud:
    function:
      definition: ordersConsumer
    stream:
      bindings:
        ordersConsumer-in-0:
          destination: orders
          group: order-service
          content-type: application/json
~~~

Các lệnh pause/resume phải dùng tên binding, không dùng tên topic hoặc consumer group. Nếu ứng dụng đổi tên binding qua spring.cloud.stream.function.bindings, hãy dùng tên alias đã cấu hình. Với binding được tạo tường minh và không gắn với function, tên binding cũng có thể khác quy tắc in-0/out-0.

Khi một function có nhiều input, mỗi input binding có vòng đời riêng. Có thể tạm dừng một input mà không nhất thiết phải dừng các binding còn lại trong cùng ứng dụng.

## 4. Điều khiển binding bằng BindingsLifecycleController

Từ Spring Cloud Stream 3.1, BindingsLifecycleController được đăng ký như một bean để ứng dụng điều khiển vòng đời từng binding. API có các thao tác pause, resume, stop và start.

Ví dụ tạo một service điều khiển consumer:

~~~java
import org.springframework.cloud.stream.binding.BindingsLifecycleController;
import org.springframework.stereotype.Service;

@Service
public class OrdersConsumerControl {

    private static final String BINDING_NAME = "ordersConsumer-in-0";

    private final BindingsLifecycleController bindings;

    public OrdersConsumerControl(
            BindingsLifecycleController bindings) {
        this.bindings = bindings;
    }

    public void pause() {
        bindings.pause(BINDING_NAME);
    }

    public void resume() {
        bindings.resume(BINDING_NAME);
    }

    public void stop() {
        bindings.stop(BINDING_NAME);
    }

    public void start() {
        bindings.start(BINDING_NAME);
    }
}
~~~

Ứng dụng có thể gọi service này từ một API quản trị nội bộ, một quy trình điều phối hoặc một điều kiện nghiệp vụ. Không nên cho mọi request bên ngoài quyền pause/resume binding; hãy kiểm soát quyền truy cập và ghi nhận người hoặc quy trình đã thực hiện thao tác.

Nếu cần đặt trạng thái tổng quát, controller còn hỗ trợ changeState với các giá trị BindingsLifecycleController.State.PAUSED, RESUMED, STOPPED và STARTED.

### Kiểm tra trạng thái binding

BindingsLifecycleController có thể truy vấn trạng thái binding. Ở các phiên bản hiện hành, kết quả truy vấn có thể bao gồm một hoặc nhiều Binding tương ứng với các lifecycle instance. Mỗi binding cung cấp thông tin như đang chạy hay đang pause. Khi binding có concurrency, cần xem trạng thái của các instance thay vì chỉ kiểm tra một cờ ở tầng ứng dụng.

Một quy trình điều khiển an toàn nên:

1. Xác nhận binding tồn tại và đang chạy.
2. Gửi yêu cầu pause hoặc resume.
3. Quan sát sự kiện ConsumerPausedEvent hoặc ConsumerResumedEvent, hoặc truy vấn trạng thái để xác nhận chuyển đổi.
4. Ghi log binding name, thời điểm, lý do và người/luồng yêu cầu.

Không coi việc phương thức pause trả về là bằng chứng mọi consumer thread đã dừng nhận record ngay tại thời điểm gọi. Trạng thái thực tế được áp dụng theo vòng đời listener container.

## 5. Điều khiển bằng Actuator endpoint

Nếu muốn điều khiển từ công cụ vận hành hoặc hệ thống quản trị, có thể dùng bindings Actuator endpoint.

Cần có dependency Actuator và một web runtime:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Nếu ứng dụng dùng WebFlux, có thể dùng spring-boot-starter-webflux thay cho starter web MVC.

Bật endpoint bindings:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,bindings
~~~

Sau khi ứng dụng khởi động, có thể xem danh sách binding:

~~~http
GET /actuator/bindings
~~~

Xem trạng thái của một binding:

~~~http
GET /actuator/bindings/ordersConsumer-in-0
~~~

Tạm dừng consumer:

~~~bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"state":"PAUSED"}' \
  http://localhost:8080/actuator/bindings/ordersConsumer-in-0
~~~

Tiếp tục nhận:

~~~bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"state":"RESUMED"}' \
  http://localhost:8080/actuator/bindings/ordersConsumer-in-0
~~~

Dừng hẳn binding:

~~~bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"state":"STOPPED"}' \
  http://localhost:8080/actuator/bindings/ordersConsumer-in-0
~~~

Khởi động lại binding:

~~~bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"state":"STARTED"}' \
  http://localhost:8080/actuator/bindings/ordersConsumer-in-0
~~~

Bindings endpoint cho phép điều khiển lifecycle từ xa nên phải được bảo vệ bằng Spring Security, mạng quản trị hoặc cơ chế xác thực tương đương. Không công khai endpoint pause/resume cho Internet hoặc cho mọi người dùng ứng dụng. Chỉ expose các endpoint cần thiết và ghi audit log cho thao tác quản trị.

## 6. Binder nào hỗ trợ PAUSED và RESUMED?

Trạng thái pause/resume phụ thuộc binder và công nghệ messaging phía dưới. Tài liệu Spring Cloud Stream hiện hành nêu rõ Kafka và Solace hỗ trợ PAUSED/RESUMED. Không được giả định mọi binder đều hỗ trợ hai trạng thái này.

| Binder | Pause/resume binding | Ghi chú |
|---|---|---|
| Apache Kafka binder | Có | Consumer tiếp tục poll trong lúc pause để tránh rebalance do tạm ngừng nhận. |
| Solace binder | Có | Theo khả năng pause/resume của binder và công nghệ nền. |
| RabbitMQ binder | Không hỗ trợ trạng thái PAUSED/RESUMED theo lifecycle binding chung hiện hành. | Dùng cơ chế điều tiết/điều khiển riêng phù hợp với Rabbit binder nếu cần. |
| Pulsar binder | Không được tài liệu lifecycle binding hiện hành liệt kê là hỗ trợ PAUSED/RESUMED. | Kiểm tra API và khả năng của phiên bản binder đang triển khai. |
| Kafka Streams binder | Không hỗ trợ PAUSED/RESUMED | Binder này hỗ trợ STARTED và STOPPED cho binding visualization/control. |

Đặc biệt, Kafka binder và Kafka Streams binder là hai binder khác nhau. Kafka Streams binder hiện chỉ hỗ trợ các lifecycle state STARTED và STOPPED; không dùng ví dụ pause/resume của regular Kafka binder để suy ra Kafka Streams topology có thể pause ở cấp binding.

Nếu gọi PAUSED hoặc RESUMED trên binder không hỗ trợ, framework có thể ghi cảnh báo và không thực hiện hành vi mong muốn. Hãy kiểm tra tài liệu đúng binder và phiên bản dependency của dự án.

## 7. Theo dõi consumer nhàn rỗi bằng ListenerContainerIdleEvent

Một consumer có thể đang hoạt động bình thường nhưng không nhận được record nào trong một khoảng thời gian. Điều này có thể xảy ra vì topic không có dữ liệu mới, producer đang ngừng phát hoặc consumer đang đọc sai destination. Để quan sát tình trạng này, Kafka binder có thể cấu hình idleEventInterval.

Thuộc tính được đặt ở phần Kafka consumer properties của binding:

~~~yaml
spring:
  cloud:
    function:
      definition: ordersConsumer
    stream:
      bindings:
        ordersConsumer-in-0:
          destination: orders
          group: order-service
      kafka:
        bindings:
          ordersConsumer-in-0:
            consumer:
              idle-event-interval: 30000
~~~

Giá trị tính bằng mili giây. Ví dụ trên yêu cầu listener container phát ListenerContainerIdleEvent sau khoảng 30 giây không nhận record. Kafka binder hiện đặt mặc định idleEventInterval là 30.000 ms; có thể đặt giá trị khác theo nhu cầu giám sát.

ListenerContainerIdleEvent là Spring application event do listener container phát ra. Event có các thông tin quan trọng:

- **listenerId:** định danh listener/container phát sự kiện.
- **idleTime:** thời gian container không nhận record, tính bằng mili giây.
- **topicPartitions:** danh sách topic/partition đang được gán tại thời điểm phát event.
- **paused:** trạng thái pause của consumer khi event được tạo.

Khi một record được nhận trở lại sau trạng thái idle, Spring Kafka có thể phát ListenerContainerNoLongerIdleEvent. Event này hữu ích để đo thời gian chờ dữ liệu và xác nhận consumer đã hoạt động trở lại.

### Nhận sự kiện idle và active

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ListenerContainerIdleEvent;
import org.springframework.kafka.event.ListenerContainerNoLongerIdleEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaConsumerIdleMonitor {

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info(
                "Kafka listener {} idle {} ms; partitions={}; paused={}",
                event.getListenerId(),
                event.getIdleTime(),
                event.getTopicPartitions(),
                event.isPaused()
        );
    }

    @EventListener
    public void onActive(ListenerContainerNoLongerIdleEvent event) {
        log.info(
                "Kafka listener {} nhận lại record; partitions={}",
                event.getListenerId(),
                event.getTopicPartitions()
        );
    }
}
~~~

Một application context có thể nhận event từ nhiều listener container. Nếu ứng dụng có nhiều input binding hoặc concurrency, hãy lọc theo listener ID phù hợp. ID thực tế có thể là listener ID hoặc tên container; container con do concurrency tạo ra có thể có hậu tố riêng. Hãy ghi log event đầu tiên để xác định ID thực tế rồi mới viết điều kiện lọc.

ListenerContainerIdleEvent được phát lặp lại theo chu kỳ trong lúc container vẫn idle. Vì vậy, handler nên ghi metric hoặc trạng thái một cách idempotent; tránh gửi cảnh báo mới ở mọi event nếu trạng thái idle chưa thay đổi.

## 8. Phân biệt idle với consumer không phản hồi

Idle không đồng nghĩa với lỗi. Một consumer có thể poll bình thường nhưng topic không có record mới. Trạng thái này khác với consumer bị kẹt trong poll() hoặc không thể giao tiếp với broker.

| Sự kiện | Ý nghĩa | Cách diễn giải |
|---|---|---|
| ListenerContainerIdleEvent | Không nhận record trong khoảng idleEventInterval. | Có thể là trạng thái bình thường nếu không có dữ liệu mới. |
| ListenerContainerNoLongerIdleEvent | Record mới được nhận sau giai đoạn idle. | Consumer đã quay lại trạng thái có dữ liệu. |
| ListenerContainerPartitionIdleEvent | Một partition cụ thể không có record trong khoảng thời gian cấu hình. | Hữu ích khi một số partition có dữ liệu còn partition khác không có. |
| NonResponsiveConsumerEvent | Consumer có vẻ bị chặn trong phương thức poll. | Cần điều tra kết nối broker, poll timeout, network và thread. |
| ConsumerPausedEvent | Consumer/container đã chuyển sang trạng thái paused. | Xác nhận thao tác pause đã có hiệu lực. |
| ConsumerResumedEvent | Consumer/container đã chuyển sang trạng thái resumed. | Xác nhận consumer đã tiếp tục nhận. |

Nếu consumer không trả về từ poll(), container không thể tạo idle event theo cách thông thường vì nó không hoàn tất chu kỳ poll để kiểm tra việc không có record. Spring Kafka có NonResponsiveConsumerEvent để báo hiệu trường hợp poll không phản hồi theo ngưỡng giám sát container.

Do đó, không dùng idle event như một health check duy nhất. Cần kết hợp:

- Binding lifecycle state.
- Consumer lag và backlog theo partition.
- Thời gian kể từ lần nhận record gần nhất.
- Số lần poll hoặc tình trạng consumer thread.
- Trạng thái kết nối và health indicator của binder.
- Log lỗi xác thực, phân quyền, timeout hoặc rebalance.

## 9. Tự động resume theo điều kiện

Một ứng dụng có thể tự resume khi điều kiện vận hành cho phép. Ví dụ, consumer được pause trong lúc dịch vụ downstream quá tải; sau khi hệ thống giám sát xác nhận dịch vụ đã phục hồi, ứng dụng mới resume binding.

Có thể kết hợp idle event với một chính sách điều khiển riêng:

~~~java
@Component
public class OrdersConsumerAutoResume {

    private static final String BINDING_NAME = "ordersConsumer-in-0";
    private static final String LISTENER_ID_PREFIX = "ordersConsumer-in-0";

    private final BindingsLifecycleController bindings;
    private final ResumePolicy resumePolicy;

    public OrdersConsumerAutoResume(
            BindingsLifecycleController bindings,
            ResumePolicy resumePolicy) {
        this.bindings = bindings;
        this.resumePolicy = resumePolicy;
    }

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        if (!event.getListenerId().startsWith(LISTENER_ID_PREFIX)) {
            return;
        }

        if (event.isPaused() && resumePolicy.isReadyToResume()) {
            bindings.resume(BINDING_NAME);
        }
    }
}
~~~

ResumePolicy là thành phần nghiệp vụ của ứng dụng, chịu trách nhiệm xác nhận điều kiện resume như dịch vụ phụ thuộc đã khỏe, circuit breaker đã đóng hoặc cửa sổ bảo trì đã kết thúc. Hãy thay LISTENER_ID_PREFIX bằng ID thực tế quan sát được từ event của ứng dụng; nếu có nhiều container con, lọc theo prefix hoặc quy tắc định danh phù hợp.

Không tự resume chỉ vì consumer idle. Idle có thể là trạng thái bình thường khi topic không có dữ liệu. Cần có điều kiện rõ ràng để tránh vòng lặp pause/resume liên tục hoặc làm consumer hoạt động lại trong khi hệ thống phụ thuộc vẫn chưa sẵn sàng.

Nếu application event multicaster được cấu hình chạy listener bất đồng bộ, không gọi trực tiếp các phương thức trên Kafka Consumer được đính kèm trong event. Với Spring Cloud Stream, ưu tiên điều khiển qua BindingsLifecycleController; cách này tránh phụ thuộc vào thread sở hữu Kafka Consumer.

## 10. Theo dõi sự kiện pause và resume

Spring Kafka phát ConsumerPausedEvent và ConsumerResumedEvent khi container thực sự chuyển trạng thái. Có thể lắng nghe các event này để ghi nhận thao tác:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerPausedEvent;
import org.springframework.kafka.event.ConsumerResumedEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaConsumerLifecycleMonitor {

    @EventListener
    public void onPaused(ConsumerPausedEvent event) {
        log.info(
                "Kafka consumer paused; partitions={}",
                event.getPartitions()
        );
    }

    @EventListener
    public void onResumed(ConsumerResumedEvent event) {
        log.info(
                "Kafka consumer resumed; partitions={}",
                event.getPartitions()
        );
    }
}
~~~

Event pause/resume cho biết partition liên quan tới thao tác. Nếu binding chạy nhiều consumer instance, có thể có nhiều event tương ứng. Không đếm một event như một lần pause toàn ứng dụng nếu chưa tổng hợp theo container và partition.

Các metric hữu ích:

- Số lần pause và resume theo binding.
- Tổng thời gian binding ở trạng thái paused.
- Thời gian idle của listener container.
- Số lần container chuyển từ idle sang nhận record.
- Consumer lag trước, trong và sau thời gian pause.
- Backlog tăng trong thời gian pause và tốc độ xử lý sau resume.
- Số lần rebalance ngoài dự kiến.

Khi pause để điều tiết tải, nên theo dõi cả tốc độ tạo backlog và tốc độ tiêu thụ sau khi resume. Nếu producer tạo dữ liệu nhanh hơn nhiều so với năng lực xử lý, consumer có thể cần tăng concurrency hoặc số replica sau khi hệ thống phục hồi.

## 11. Kiểm thử pause, resume và idle event

Kiểm thử cần dùng Kafka broker thử nghiệm để xác nhận hành vi poll, partition assignment và backlog. Test binder có thể kiểm tra logic ở mức Spring Cloud Stream nhưng không mô phỏng đầy đủ pause/resume và rebalance của Kafka.

### Kịch bản pause và resume

1. Khởi động Kafka và ứng dụng có input binding ordersConsumer-in-0.
2. Gửi một vài record và xác nhận consumer xử lý bình thường.
3. Gọi BindingsLifecycleController.pause() hoặc Actuator với state PAUSED.
4. Xác nhận consumer phát ConsumerPausedEvent.
5. Gửi thêm record trong lúc binding paused.
6. Xác nhận ứng dụng chưa xử lý các record mới trong khoảng pause.
7. Gọi resume và xác nhận ConsumerResumedEvent.
8. Xác nhận backlog được tiêu thụ và tiến độ tiếp tục theo offset.
9. Quan sát group membership để xác nhận thao tác pause không tạo rebalance chỉ vì consumer tạm ngừng nhận.

### Ma trận kiểm thử

| Tình huống | Thiết lập | Kết quả cần xác nhận |
|---|---|---|
| Pause binding | Gọi controller.pause(bindingName). | Binding chuyển sang paused; consumer ngừng lấy record mới. |
| Resume binding | Gọi controller.resume(bindingName). | Consumer tiếp tục nhận record. |
| Stop binding | Gọi controller.stop(bindingName). | Container dừng và group có thể rebalance. |
| Actuator pause | POST state PAUSED. | Endpoint điều khiển đúng binding name. |
| Actuator resume | POST state RESUMED. | Binding tiếp tục nhận dữ liệu. |
| Idle event | Không gửi record trong thời gian lớn hơn idleEventInterval. | ListenerContainerIdleEvent được phát. |
| No longer idle | Gửi record sau khi listener đã idle. | ListenerContainerNoLongerIdleEvent được phát. |
| Partition idle | Một partition không có record trong khoảng cấu hình. | Partition idle event xác định đúng topic/partition. |
| Non-responsive poll | Mô phỏng poll bị chặn hoặc broker không phản hồi trong môi trường test phù hợp. | Có cảnh báo/event giám sát không phản hồi theo cấu hình. |
| Nhiều binding | Ứng dụng có hai input binding. | Pause một binding không làm binding còn lại dừng ngoài ý muốn. |
| Nhiều replica | Chạy consumer group với nhiều instance. | Theo dõi trạng thái và event theo từng container/partition. |
| Binder không hỗ trợ | Thử PAUSED với binder không hỗ trợ. | Ứng dụng ghi nhận cảnh báo và không giả định đã pause. |

### Kiểm tra backlog và offset

Trong test, ghi lại số record đã gửi, số record đã xử lý và consumer lag trước khi pause. Trong lúc pause, producer vẫn tiếp tục ghi nên lag có thể tăng. Sau resume, xác nhận consumer đọc tiếp và lag giảm dần.

Không yêu cầu offset phải liên tục trong mọi topic; compaction, transaction và các đặc tính log có thể tạo khoảng trống quan sát được. Hãy kiểm tra số record thực tế đã xử lý và tiến độ commit thay vì suy luận mất dữ liệu chỉ từ một offset bị nhảy.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| PAUSED không có tác dụng | Binder không hỗ trợ trạng thái pause/resume hoặc dùng nhầm binding name. | Xác nhận đang dùng regular Kafka binder và kiểm tra tên binding. |
| Pause xong vẫn thấy vài record được xử lý | Các record đã được trả về từ poll trước đang hoàn tất xử lý. | Chờ chu kỳ poll hiện tại kết thúc và kiểm tra thời điểm ConsumerPausedEvent. |
| Stop gây rebalance ngoài ý muốn | Dùng STOPPED cho tình huống chỉ cần tạm ngừng nhận. | Dùng PAUSED khi cần giữ consumer trong group. |
| Resume không nhận lại dữ liệu | Binding name sai, container chưa resumed hoặc topic không có record mới. | Kiểm tra lifecycle event, trạng thái binding và backlog. |
| Idle event không xuất hiện | Chưa cấu hình idleEventInterval hoặc listener chưa được binding. | Kiểm tra Kafka consumer extended properties và input binding. |
| Idle event xuất hiện liên tục | Topic không có record hoặc idleEventInterval quá ngắn. | Xem đây là trạng thái quan sát; tăng chu kỳ hoặc giảm log lặp. |
| Consumer bị kẹt nhưng không có idle event | Poll không trả về nên container không phát hiện trạng thái idle theo chu kỳ. | Theo dõi NonResponsiveConsumerEvent, poll timeout và kết nối broker. |
| Resume tự động quá sớm | Chính sách chỉ dựa vào idle mà không kiểm tra điều kiện downstream. | Dùng ResumePolicy hoặc tín hiệu phục hồi đáng tin cậy. |
| Event listener xử lý nhầm binding | Một context nhận event từ nhiều container. | Lọc theo listener ID/container ID thực tế và binding tương ứng. |
| Kafka Streams binder không pause được | Nhầm khả năng của regular Kafka binder với Kafka Streams binder. | Dùng STARTED/STOPPED theo khả năng của Kafka Streams binder. |

Khi điều tra, hãy kiểm tra lần lượt: binder type, binding name, lifecycle state, pause/resume event, idleEventInterval, listener ID, partition assignment và consumer lag. Phân biệt consumer đang idle hợp lệ với consumer không phản hồi trong poll trước khi khởi động lại hoặc thay đổi group.

## 13. Checklist trước khi triển khai

- [ ] Đã xác định đúng input binding cần điều khiển.
- [ ] Dùng PAUSED/RESUMED cho regular Kafka binder khi cần ngừng nhận tạm thời.
- [ ] Dùng STOPPED/STARTED khi cần dừng và khởi động lại container.
- [ ] Đã xác nhận binder và phiên bản hỗ trợ PAUSED/RESUMED.
- [ ] Đã tính tới backlog, retention và tốc độ xử lý sau resume.
- [ ] Đã bật idleEventInterval cho binding cần theo dõi.
- [ ] Event listener lọc đúng listener/container ID.
- [ ] Đã phân biệt idle bình thường với NonResponsiveConsumerEvent.
- [ ] Chính sách auto-resume có điều kiện phục hồi rõ ràng.
- [ ] Actuator endpoint được bảo vệ bằng xác thực và phân quyền.
- [ ] Có log/metric cho pause, resume, idle, backlog và rebalance.
- [ ] Integration test xác nhận consumer tiếp tục từ tiến độ mong muốn sau resume.

Spring Cloud Stream cho phép điều khiển lifecycle của Kafka input binding bằng BindingsLifecycleController hoặc Actuator. Pause giữ consumer tiếp tục poll để tránh rebalance do tạm ngừng nhận; stop dừng container và có thể khiến group rebalance. idleEventInterval cùng các event của Spring Kafka giúp quan sát listener không nhận dữ liệu, nhận lại dữ liệu hoặc không phản hồi trong poll. Khi kết hợp điều khiển binding với giám sát backlog, trạng thái container và điều kiện phục hồi, ứng dụng có thể tạm ngừng và tiếp tục tiêu thụ Kafka một cách có kiểm soát.

## Tài liệu tham khảo

- [Spring Cloud Stream — Pausing and Resuming the Consumer](https://docs.spring.io/spring-cloud-stream/reference/5.0/kafka/kafka-binder/pause_resume.html)
- [Spring Cloud Stream — Binding Visualization and Control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html)
- [Spring Cloud Stream — Kafka Binder Reference Guide](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/spring-cloud-stream-binder-kafka.html)
- [Spring for Apache Kafka — Pausing and Resuming Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/pause-resume.html)
- [Spring for Apache Kafka — Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html)
