# Khởi động, dừng binding và giới hạn điều khiển vòng đời

Kafka Streams processor trong Spring Cloud Stream thường tự khởi động cùng ứng dụng Spring Boot. Khi vận hành, có lúc cần trì hoãn việc xử lý để state store restore xong, dừng một processor trong lúc bảo trì, hoặc bật lại sau khi cấu hình và tài nguyên đã sẵn sàng. Kafka Streams Binder cung cấp các cơ chế điều khiển vòng đời ở cấp processor thông qua binding, Spring Boot Actuator và API lập trình.

Điểm quan trọng là binding của Kafka Streams không độc lập hoàn toàn như các message-channel binding thông thường. Các input/output binding của cùng một function thường được xây dựng trên cùng một StreamsBuilderFactoryBean và cùng một KafkaStreams instance. Vì vậy, gọi stop trên một binding của function sẽ dừng processor đó; nó không chỉ tạm ngừng riêng một topic. Ngoài ra, Kafka Streams Binder chỉ hỗ trợ hai trạng thái điều khiển STARTED và STOPPED. Trạng thái PAUSED và RESUMED không được hỗ trợ qua binding lifecycle của binder.

## 1. Các lớp vòng đời cần phân biệt

Trong ứng dụng Spring Cloud Stream dùng Kafka Streams, có nhiều thành phần cùng có vòng đời:

| Thành phần | Vai trò | Cách điều khiển |
|---|---|---|
| Spring Boot application | JVM, Spring context và các bean | Khởi động/dừng tiến trình hoặc context |
| Kafka Streams processor | Một topology được quản lý bởi StreamsBuilderFactoryBean | StreamsBuilderFactoryManager hoặc binding lifecycle |
| Input/output binding | Điểm nối logic giữa function và Kafka topic | BindingsLifecycleController hoặc Actuator |
| Kafka consumer group/application ID | Tiến độ đọc, phân phối partition và state của processor | Cấu hình Kafka Streams; không phải nút start/stop của binding |

Một function kiểu Consumer<KStream<...>> thường có binding input tên functionName-in-0. Một Function<KStream<...>, KStream<...>> thường có input functionName-in-0 và output functionName-out-0. Tên binding được dùng khi cấu hình destination và khi gọi endpoint điều khiển.

Ví dụ:

~~~java
@Bean
Consumer<KStream<String, OrderCreated>> processOrders() {
    return orders -> orders.foreach((key, event) ->
        orderService.record(event));
}
~~~

Binding input mặc định là processOrders-in-0. Với một processor có input và output:

~~~java
@Bean
Function<KStream<String, OrderCreated>,
         KStream<String, OrderSummary>> summarizeOrders() {
    return orders -> orders.mapValues(event ->
        new OrderSummary(event.orderId(), event.total()));
}
~~~

Hai binding mặc định là summarizeOrders-in-0 và summarizeOrders-out-0. Cả hai thuộc cùng processor function summarizeOrders.

## 2. Vòng đời mặc định: processor tự khởi động

Khi Spring context khởi động, Kafka Streams Binder tạo topology từ các function bean, tạo binding tương ứng và khởi động Kafka Streams processor theo cấu hình mặc định. Processor sẽ tham gia consumer group, nhận partition, khôi phục state store nếu có và bắt đầu xử lý record khi đã sẵn sàng.

Không cần gọi start thủ công trong trường hợp thông thường. Hãy để binder quản lý lifecycle để Spring có thể đóng processor theo lifecycle của application context.

Một processor có state store lớn có thể cần thời gian restore từ changelog topic trước khi chuyển sang trạng thái RUNNING. Nếu việc restore kéo dài trong giai đoạn khởi động, readiness/liveness probe của nền tảng triển khai có thể đánh giá sai ứng dụng là không khỏe và restart liên tục. Khi đó, có thể tách thời điểm khởi động Spring Boot khỏi thời điểm bắt đầu các processor.

## 3. Quan sát trạng thái binding qua Actuator

Spring Cloud Stream cung cấp endpoint bindings để xem danh sách binding và điều khiển vòng đời. Cần có Spring Boot Actuator cùng một web runtime:

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

Nếu ứng dụng dùng WebFlux, có thể dùng spring-boot-starter-webflux thay cho spring-boot-starter-web.

Expose endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: bindings
~~~

Liệt kê binding:

~~~bash
curl http://localhost:8080/actuator/bindings
~~~

Response có thể chứa các trường như:

~~~json
[
  {
    "bindingName": "summarizeOrders-in-0",
    "group": "summarizeOrders-applicationId",
    "pausable": false,
    "state": "running",
    "paused": false,
    "input": true
  },
  {
    "bindingName": "summarizeOrders-out-0",
    "group": "summarizeOrders-applicationId",
    "pausable": false,
    "state": "running",
    "paused": false,
    "input": false
  }
]
~~~

Thông tin cụ thể phụ thuộc phiên bản binder và binding. Với Kafka Streams Binder, pausable thường là false vì binder không hỗ trợ PAUSED/RESUMED. Trường state phản ánh trạng thái binding được quản lý bởi Spring Cloud Stream, không thay thế mọi trạng thái nội bộ của KafkaStreams.

Có thể xem một binding cụ thể bằng URL /actuator/bindings/{bindingName}. Dùng tên binding do function definition tạo ra; không dùng tên topic thay cho tên binding trừ khi chúng tình cờ giống nhau.

## 4. Dừng processor bằng Actuator

Gửi POST với trạng thái STOPPED:

~~~bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"state":"STOPPED"}' \
  http://localhost:8080/actuator/bindings/summarizeOrders-in-0
~~~

Sau khi processor dừng, topology tương ứng không tiếp tục nhận và xử lý record. Record chưa được xử lý còn trong Kafka theo retention và compaction policy của topic; khi processor được khởi động lại, Kafka Streams tiếp tục theo offset đã commit và khôi phục state theo application ID/state store configuration.

Không xem STOPPED là xóa topic, xóa consumer group hoặc reset offset. Đây là thao tác dừng processor được binder quản lý. Việc reset offset/replay từ đầu là một quy trình vận hành riêng.

## 5. Khởi động lại processor

Gửi POST với trạng thái STARTED:

~~~bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"state":"STARTED"}' \
  http://localhost:8080/actuator/bindings/summarizeOrders-in-0
~~~

Kafka Streams processor được khởi động lại. Nó có thể cần tham gia group, nhận partition và restore local state trước khi xử lý bình thường. Lệnh STARTED yêu cầu khởi động; không nên coi response HTTP thành công là bằng chứng rằng mọi state store đã restore xong và processor đã RUNNING. Hãy quan sát health indicator, trạng thái Kafka Streams, lag và log restore để xác nhận processor thực sự sẵn sàng.

## 6. Giới hạn: Kafka Streams Binder chỉ hỗ trợ STARTED và STOPPED

Spring Cloud Stream có API binding lifecycle tổng quát với các trạng thái STARTED, STOPPED, PAUSED và RESUMED. Tuy nhiên, khả năng thực hiện phụ thuộc binder.

Đối với Kafka Streams Binder:

| Trạng thái yêu cầu | Hỗ trợ | Ý nghĩa |
|---|---|---|
| STARTED | Có | Khởi động processor |
| STOPPED | Có | Dừng processor |
| PAUSED | Không | Không thể dùng binding lifecycle để pause consumer mà giữ processor ở trạng thái paused |
| RESUMED | Không | Không có thao tác resume tương ứng sau PAUSED |

Không dùng PAUSED/RESUMED với Kafka Streams Binder rồi giả định nó tương đương Kafka message-channel binder. Nếu cần ngừng xử lý trong một khoảng thời gian, có thể dừng processor và khởi động lại sau đó; cần tính đến rebalance, state restoration và khả năng các processor khác tiếp tục chạy.

## 7. Một function có nhiều binding nhưng chỉ một processor lifecycle

Đây là giới hạn quan trọng khi function có nhiều input hoặc output. Ví dụ:

~~~java
@Bean
BiFunction<KStream<String, OrderCreated>,
           KTable<String, Customer>,
           KStream<String, EnrichedOrder>> enrichOrders() {
    return (orders, customers) -> orders.leftJoin(
        customers,
        (order, customer) -> new EnrichedOrder(order, customer)
    );
}
~~~

Function trên có hai input binding:

- enrichOrders-in-0
- enrichOrders-in-1

và một output binding:

- enrichOrders-out-0

Các binding của cùng function được backing bởi cùng một StreamsBuilderFactoryBean. Do đó, gọi STOPPED trên enrichOrders-in-0, enrichOrders-in-1 hoặc enrichOrders-out-0 đều điều khiển cùng processor enrichOrders. Không thể dùng endpoint binding để chỉ dừng riêng một input mà vẫn để cùng topology tiếp tục xử lý input còn lại.

Nếu cần vòng đời độc lập, hãy tách thành các function/processor riêng để mỗi processor có factory bean và application ID phù hợp. Không tách chỉ để điều khiển nếu topology cần join hoặc state dùng chung; việc tách có thể thay đổi semantics, repartition và độ trễ của pipeline.

## 8. Điều khiển bằng BindingsLifecycleController

Ngoài REST endpoint, Spring Cloud Stream đăng ký bean BindingsLifecycleController để điều khiển binding từ code:

~~~java
import org.springframework.cloud.stream.binding.BindingsLifecycleController;
import org.springframework.stereotype.Component;

@Component
public class ProcessorLifecycle {

    private final BindingsLifecycleController controller;

    public ProcessorLifecycle(BindingsLifecycleController controller) {
        this.controller = controller;
    }

    public void stopOrdersProcessor() {
        controller.stop("summarizeOrders-in-0");
    }

    public void startOrdersProcessor() {
        controller.start("summarizeOrders-in-0");
    }

    public boolean isRunning() {
        var binding = controller.queryState("summarizeOrders-in-0");
        return binding != null && binding.isRunning();
    }
}
~~~

Các thao tác start/stop tiện lợi tương đương thay đổi trạng thái binding. Có thể dùng changeState với State.STARTED hoặc State.STOPPED nếu muốn chỉ định trạng thái tường minh. API này phù hợp khi một điều kiện trong ứng dụng quyết định thời điểm processor bắt đầu hoặc dừng, ví dụ một bước khởi tạo nghiệp vụ đã hoàn tất.

Không gọi start/stop liên tục theo mỗi message hoặc mỗi request. Lifecycle operation là thao tác cấp processor, có thể làm Kafka Streams đóng/mở lại, tái tham gia group và restore state. Hãy dùng một bộ điều phối có trạng thái rõ ràng và tránh nhiều thread cùng thay đổi lifecycle không kiểm soát.

## 9. Trì hoãn auto-start của tất cả processor

Nếu muốn Spring Boot khởi động trước và chỉ bắt đầu Kafka Streams sau khi ứng dụng đã sẵn sàng, đặt:

~~~yaml
spring:
  kafka:
    streams:
      auto-startup: false
~~~

Thuộc tính này tắt auto-start cho toàn bộ Kafka Streams processors trong ứng dụng. Khi cần khởi động, dùng StreamsBuilderFactoryManager do Kafka Streams Binder cung cấp:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cloud.stream.binder.kafka.streams.StreamsBuilderFactoryManager;

@Configuration
public class KafkaStreamsStartupConfiguration {

    @Bean
    ApplicationRunner startKafkaStreamsProcessors(
            StreamsBuilderFactoryManager manager) {
        return args -> manager.start();
    }
}
~~~

StreamsBuilderFactoryManager quản lý nhiều StreamsBuilderFactoryBean do binder tạo. Khi dùng Kafka Streams Binder, hãy điều khiển thông qua manager này thay vì tự lấy KafkaStreams nội bộ hoặc tự tạo StreamsBuilderFactoryBean. Binder giữ quyền quản lý factory bean và các binding liên quan.

Mẫu trên khởi động tất cả processor được quản lý. Nếu ứng dụng có nhiều processor nhưng chỉ muốn bật một số processor, không dùng manager.start() như một cách chọn lọc; hãy dùng auto-startup ở từng consumer binding và điều khiển processor tương ứng qua binding lifecycle.

## 10. Chỉ trì hoãn auto-start của một processor

Có thể đặt auto-startup=false trên một input consumer binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        reconcileOrders-in-0:
          destination: orders.events
          group: order-reconciler
          consumer:
            auto-startup: false
~~~

Ứng dụng vẫn khởi động và các processor khác vẫn auto-start theo cấu hình của chúng. Processor reconcileOrders chưa bắt đầu cho đến khi được điều khiển STARTED qua Actuator hoặc BindingsLifecycleController.

Với function có nhiều input, đặt auto-startup=false trên một input binding là đủ để trì hoãn processor vì các input dùng chung factory bean. Có thể đặt trên tất cả input binding để cấu hình dễ đọc hơn. Thuộc tính này chỉ có ý nghĩa trên consumer binding; đặt trên output binding không tắt auto-start của processor.

## 11. Khởi động processor đã bị trì hoãn

Sau khi dùng auto-startup=false, có thể khởi động qua Actuator:

~~~bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"state":"STARTED"}' \
  http://localhost:8080/actuator/bindings/reconcileOrders-in-0
~~~

Hoặc qua BindingsLifecycleController:

~~~java
controller.start("reconcileOrders-in-0");
~~~

Ví dụ này cho phép ứng dụng hoàn tất các bước khởi tạo khác trước khi processor tham gia consumer group. Một trường hợp sử dụng là state store lớn cần thời gian restore. Tuy nhiên, cần thiết kế readiness probe riêng: ứng dụng có thể đang sống nhưng processor chưa xử lý message. Liveness chỉ nên phản ánh tiến trình có cần restart hay không; readiness cần phản ánh processor đã sẵn sàng nhận traffic theo yêu cầu triển khai.

## 12. Theo dõi health khi processor bị dừng

Kafka Streams Binder có thuộc tính binder-level:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            include-stopped-processors-for-health-check: true
~~~

Mặc định includeStoppedProcessorsForHealthCheck là false. Processor bị dừng qua Actuator không tham gia health check. Đặt true nếu muốn health check vẫn tính cả processor đang STOPPED.

Hãy chọn chính sách theo cách ứng dụng dùng trạng thái STOPPED:

- Nếu dừng là trạng thái bảo trì có chủ đích, có thể không muốn processor đó làm health của toàn ứng dụng chuyển sang DOWN.
- Nếu processor phải luôn hoạt động để đáp ứng chức năng chính, việc bỏ qua processor đã dừng có thể che giấu một tình trạng không mong muốn; bật kiểm tra và bổ sung cảnh báo phù hợp.

Health indicator và trạng thái binding trả lời các câu hỏi khác nhau. Binding running cho biết lifecycle đã được khởi động; health và KafkaStreams state cho biết processor có hoạt động bình thường, restore xong và tham gia xử lý hay không.

## 13. Dừng binding không đồng nghĩa xóa local state

Khi dừng Kafka Streams binding, local state store mặc định không bị xóa. Đây là hành vi mặc định của Spring Kafka từ phiên bản 2.7 và được Kafka Streams Binder giữ nguyên.

Điều này có lợi khi bảo trì ngắn hạn: processor có thể được start lại và sử dụng local state hiện có, đồng thời Kafka Streams có thể đồng bộ phần thay đổi từ changelog. Không nên xóa thư mục state bằng tay trong lúc processor đang chạy hoặc khi một instance khác còn sử dụng cùng state directory.

Nếu cần điều khiển việc dọn local state khi start/stop, Kafka Streams Binder phát hiện một bean CleanupConfig trong application context. Bean này cho phép cấu hình cleanup khi start, khi stop hoặc không cleanup. Chỉ bật cleanup khi đã hiểu tác động đến thời gian restore và nguồn changelog; xóa local state thường làm processor phải khôi phục lại dữ liệu trạng thái từ Kafka.

Dừng và khởi động lại binding cũng không reset committed offsets. Thuộc tính resetOffsets của consumer thuộc regular Kafka message-channel binder không có tác dụng với Kafka Streams Binder. Nếu cần replay từ đầu, phải lập kế hoạch offset/application ID/state store riêng và thực hiện bằng quy trình vận hành có kiểm soát.

## 14. Phân biệt stop/start với đóng KafkaStreams trực tiếp

KafkaStreams có API start() và close(). Tuy nhiên, sau khi một KafkaStreams instance đã close, không thể gọi start() trên chính instance đó để tái sử dụng; cần tạo KafkaStreams instance mới.

Spring for Apache Kafka cung cấp StreamsBuilderFactoryBean để quản lý việc tạo và đóng KafkaStreams. Kafka Streams Binder đặt thêm StreamsBuilderFactoryManager để quản lý nhiều factory bean cho các processor. Khi ứng dụng dùng binder, hãy điều khiển lifecycle ở tầng manager hoặc binding controller.

Không inject KafkaStreams nội bộ rồi gọi close() trực tiếp trong khi binder vẫn quản lý binding. Làm vậy có thể khiến trạng thái Spring binding và trạng thái Kafka Streams không còn đồng bộ. Dùng API lifecycle được binder hỗ trợ để stop/start và để Spring quản lý shutdown.

## 15. Trạng thái processor và thời gian restore

Sau lệnh STARTED, processor có thể đi qua các giai đoạn như khởi tạo, tham gia group, nhận partition, khôi phục state store và cuối cùng chạy ổn định. Với topology không có state store, thời gian sẵn sàng có thể ngắn. Với topology có state lớn, restore có thể mất nhiều phút.

Không chỉ kiểm tra HTTP response của endpoint. Nên quan sát:

- Trạng thái binding qua /actuator/bindings.
- Kafka Streams state và health indicator.
- Log bắt đầu/kết thúc state restoration.
- Consumer lag và tốc độ xử lý.
- Rebalance và partition assignment.
- Trạng thái local state store/changelog.

Nếu cần xác định processor đã sẵn sàng cho nghiệp vụ, hãy xây dựng readiness condition dựa trên các tín hiệu này thay vì chỉ dựa vào việc binding đã nhận trạng thái STARTED.

## 16. Các giới hạn vận hành thường gặp

| Nhu cầu | Cách phù hợp | Giới hạn cần nhớ |
|---|---|---|
| Xem binding đang chạy | GET /actuator/bindings | Cần Actuator, web runtime và expose endpoint |
| Dừng processor | POST state STOPPED | Dừng cả processor dùng chung factory bean |
| Khởi động processor | POST state STARTED | Có thể cần thời gian join group và restore state |
| Pause/resume mà không stop | Không được Kafka Streams Binder hỗ trợ qua binding lifecycle | PAUSED/RESUMED không khả dụng |
| Trì hoãn mọi processor | spring.kafka.streams.auto-startup=false và StreamsBuilderFactoryManager | manager.start() khởi động tất cả processor được quản lý |
| Trì hoãn một processor | consumer.auto-startup=false trên input binding | Không đặt trên output binding |
| Điều khiển bằng code | BindingsLifecycleController | Gọi theo sự kiện vận hành, không gọi liên tục |
| Dọn local state | CleanupConfig | Có thể làm tăng thời gian restore |
| Replay từ đầu | Quy trình offset/state riêng | Start binding không reset offset |

## 17. Kiểm thử lifecycle

Nên kiểm tra các hành vi sau trong integration test:

1. Khởi động ứng dụng và xác nhận processor mặc định ở trạng thái running.
2. Gọi Actuator STOPPED và xác nhận processor không tiếp tục nhận/xử lý record.
3. Gửi thêm record trong lúc processor dừng; xác nhận record vẫn còn trên Kafka theo retention/compaction và được xử lý khi processor start lại.
4. Gọi STARTED và chờ processor restore state, tham gia group trước khi xác nhận sẵn sàng.
5. Với function có hai input và một output, stop từ tên input thứ nhất rồi xác nhận cả processor dừng; start từ output binding rồi xác nhận processor chạy lại.
6. Xác nhận PAUSED/RESUMED không được dùng như trạng thái hợp lệ của Kafka Streams Binder.
7. Đặt global auto-startup=false và xác nhận processor chưa chạy trước khi manager.start().
8. Đặt consumer auto-startup=false trên một processor và xác nhận processor khác vẫn auto-start.
9. Kiểm tra health check khi processor STOPPED với include-stopped-processors-for-health-check ở false và true.
10. Stop/start processor có state store và xác nhận local state được giữ theo cấu hình mặc định.
11. Kiểm tra graceful application shutdown để Kafka Streams đóng theo Spring lifecycle.

Test Binder có thể xác nhận wiring và một phần logic ứng dụng, nhưng không mô phỏng đầy đủ rebalance, partition assignment, state restoration và Kafka Streams lifecycle. Dùng Kafka broker thật hoặc Testcontainers cho integration test, nhất là khi topology có state store.

## 18. Bảo vệ endpoint điều khiển

Bindings Actuator có thể dừng hoặc khởi động processor đang xử lý dữ liệu production. Chỉ expose endpoint cần thiết và đặt nó sau cơ chế xác thực/phân quyền, mạng quản trị hoặc API gateway nội bộ. Không expose toàn bộ Actuator ra Internet chỉ để bật bindings endpoint.

Nếu response binding chứa cấu hình mở rộng có thông tin nhạy cảm, dùng cơ chế sanitization phù hợp của Spring Boot. Không ghi credentials, SASL JAAS config, SSL key hoặc secret vào log vận hành.

## 19. Checklist triển khai

- [ ] Đã xác định tên binding thực tế từ function definition.
- [ ] Đã xác định các binding nào dùng chung một processor/StreamsBuilderFactoryBean.
- [ ] Đã cài Actuator và web runtime nếu điều khiển qua REST.
- [ ] Đã expose endpoint bindings một cách có kiểm soát.
- [ ] Đã xác thực và phân quyền thao tác STOPPED/STARTED.
- [ ] Đã nhớ Kafka Streams Binder chỉ hỗ trợ STARTED/STOPPED.
- [ ] Đã chọn global auto-startup hoặc selective consumer auto-startup theo yêu cầu.
- [ ] Đã dùng StreamsBuilderFactoryManager khi cần quản lý auto-start toàn bộ processor.
- [ ] Đã thiết kế readiness trong thời gian state store restore.
- [ ] Đã quyết định health check có tính processor đang STOPPED hay không.
- [ ] Đã hiểu local state mặc định không bị xóa khi stop.
- [ ] Đã có quy trình riêng nếu cần reset offset hoặc rebuild state.
- [ ] Đã kiểm thử stop/start, multi-input, state restore và graceful shutdown với Kafka thật.

Spring Cloud Stream Kafka Streams Binder cho phép quan sát và điều khiển vòng đời processor qua binding. Dùng Actuator hoặc BindingsLifecycleController để stop/start; dùng StreamsBuilderFactoryManager khi cần trì hoãn auto-start của tất cả processor, hoặc consumer.auto-startup để chọn một processor. Luôn nhớ các binding của cùng function chia sẻ lifecycle, binder không hỗ trợ PAUSED/RESUMED, và stop không tự xóa local state hay reset offset.

## Tài liệu tham khảo

- [Spring Cloud Stream — Binding Visualization and Control in Kafka Streams Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/binding-visualization-and-control-in-binder.html)
- [Spring Cloud Stream — Manually Starting Kafka Streams Processors](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/manually-starting-processors.html)
- [Spring Cloud Stream — Manually Starting Kafka Streams Processors Selectively](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/manually-starting-processors-selectively.html)
- [Spring Cloud Stream — Binding Visualization and Control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html)
- [Spring for Apache Kafka — Kafka Streams Lifecycle](https://docs.spring.io/spring-kafka/reference/streams.html)
