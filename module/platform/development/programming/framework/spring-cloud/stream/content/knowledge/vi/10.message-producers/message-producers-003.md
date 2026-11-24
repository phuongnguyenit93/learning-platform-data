# Cấu hình poller riêng cho từng output binding

Trong Spring Cloud Stream, một Supplier kiểu imperative cung cấp dữ liệu khi framework gọi phương thức get(). Vì Supplier không nhận thông điệp đầu vào, framework cần một cơ chế kích hoạt để biết khi nào lấy dữ liệu mới. Poller đảm nhiệm việc đó: nó gọi Supplier theo lịch, nhận giá trị trả về và chuyển giá trị thành thông điệp gửi qua output binding đến broker.

Mặc định, poller dùng chung tạo một thông điệp mỗi giây cho Supplier thông thường. Cấu hình mặc định phù hợp với một nguồn phát đơn giản, nhưng một ứng dụng có thể có nhiều nguồn với nhịp phát khác nhau. Ví dụ, sự kiện đơn hàng cần phát gần như liên tục, trong khi bản chụp số liệu chỉ cần phát mỗi phút. Spring Cloud Stream cho phép cấu hình poller riêng ngay trên từng output binding để mỗi nguồn có chu kỳ, thời điểm bắt đầu và số thông điệp tối đa cho mỗi lần poll phù hợp với tải của nó.

## 1. Poller kích hoạt Supplier như thế nào?

Function và Consumer thường được gọi khi có thông điệp đến input binding. Supplier là nguồn phát nên không có input binding để kích hoạt. Với Supplier kiểu imperative, Spring Cloud Stream dùng poller để gọi get() theo chu kỳ.

~~~java
import java.time.Instant;
import java.util.UUID;
import java.util.function.Supplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public record OrderEvent(String orderId, Instant createdAt) {}

@Configuration
class OrderSourceConfiguration {

    @Bean
    Supplier<OrderEvent> orderEvents() {
        return () -> new OrderEvent(
            UUID.randomUUID().toString(),
            Instant.now()
        );
    }
}
~~~

Bean orderEvents tạo một OrderEvent mỗi khi get() được gọi. Spring Cloud Stream phát giá trị đó qua output binding có tên mặc định orderEvents-out-0. Nếu destination của binding là orders.created, binder sẽ gửi thông điệp đến destination tương ứng trên Kafka, RabbitMQ hoặc Pulsar.

~~~mermaid
flowchart LR
    P["Poller"] -->|"Gọi get() theo lịch"| S["Supplier<OrderEvent>"]
    S -->|"OrderEvent"| O["orderEvents-out-0"]
    O --> B[("Binder")]
    B --> D[("orders.created")]
~~~

Poller điều khiển thời điểm gọi Supplier trong ứng dụng. Nó không phải cơ chế consumer đọc topic hoặc queue từ broker. Việc gửi thông điệp đến broker vẫn do output binding và binder thực hiện.

## 2. Tên output binding cần cấu hình

Với một Supplier bean tên orderEvents, tên output binding mặc định là orderEvents-out-0. Quy tắc này được áp dụng từ tên bean và hướng dữ liệu:

| Thành phần | Tên ví dụ | Ý nghĩa |
|---|---|---|
| Supplier bean | orderEvents | Hàm nguồn phát được Spring Cloud Function phát hiện |
| Output binding | orderEvents-out-0 | Cổng đầu ra thứ nhất của Supplier |
| Destination | orders.created | Topic, queue hoặc đích logic trên broker |
| Poller | orderEvents-out-0.producer.poller | Cấu hình lịch riêng cho output binding này |

Tên binding là khóa cấu hình trong ứng dụng. Destination là tài nguyên mà binder kết nối. Không dùng tên destination để thay thế tên binding trong nhánh producer.poller.

Ví dụ, nếu binding đã được ánh xạ tên tường minh bằng spring.cloud.stream.function.bindings, hãy dùng tên binding sau ánh xạ khi khai báo thuộc tính producer. Nếu không có ánh xạ, giữ nguyên tên mặc định được suy ra từ bean Supplier.

## 3. Cấu hình poller dùng chung

Nếu mọi Supplier trong ứng dụng có cùng nhịp phát, có thể cấu hình poller mặc định một lần. Trong các phiên bản Spring Cloud Stream hiện hành, nhóm thuộc tính poller mặc định dùng prefix spring.integration.poller:

~~~yaml
spring:
  integration:
    poller:
      fixed-delay: 1000
      initial-delay: 0
      max-messages-per-poll: 1
~~~

Các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa | Mặc định |
|---|---|---|
| fixed-delay | Khoảng chờ giữa các lần chạy poller định kỳ, tính bằng mili giây | 1000 |
| initial-delay | Thời gian chờ trước lần poll đầu tiên | 0 |
| max-messages-per-poll | Số thông điệp tối đa được tạo trong một lần poll | 1 |
| cron | Biểu thức lịch dùng Cron Trigger | Không đặt |
| time-unit | Đơn vị áp dụng cho các giá trị delay | MILLISECONDS |

Ví dụ fixed-delay bằng 2000 nghĩa là poller dùng chung chờ theo chu kỳ hai giây. Cấu hình này tác động đến các Supplier imperative đang sử dụng poller mặc định. Nếu mỗi nguồn cần lịch khác nhau, hãy cấu hình ở cấp output binding thay vì đổi poller dùng chung.

Ở các phiên bản cũ, tài liệu từng dùng prefix spring.cloud.stream.poller. Thuộc tính này đã bị deprecated từ Spring Cloud Stream 3.2 để chuyển sang cấu hình Spring Integration poller qua spring.integration.poller. Với dự án đang nâng cấp, cần kiểm tra phiên bản Stream cụ thể và migration guide thay vì sao chép cấu hình cũ.

## 4. Cấu hình poller riêng cho một output binding

Để cấu hình riêng, đặt poller dưới nhánh producer của binding:

~~~yaml
spring:
  cloud:
    function:
      definition: orderEvents
    stream:
      bindings:
        orderEvents-out-0:
          destination: orders.created
          producer:
            poller:
              fixed-delay: 2000
              initial-delay: 500
              max-messages-per-poll: 1
~~~

Trong ví dụ này:

- orderEvents là tên bean Supplier được kích hoạt.
- orderEvents-out-0 là output binding do Supplier tạo ra.
- orders.created là destination trên broker.
- producer.poller.fixed-delay đặt chu kỳ riêng là 2000 mili giây.
- producer.poller.initial-delay trì hoãn lần poll đầu tiên 500 mili giây sau khi khởi tạo.
- producer.poller.max-messages-per-poll giới hạn mỗi lần poll tạo tối đa một thông điệp.

Đường dẫn cấu hình quan trọng là:

~~~text
spring.cloud.stream.bindings.orderEvents-out-0.producer.poller.fixed-delay
~~~

Các thuộc tính poller riêng được khai báo trong producer.poller của output binding. Không đặt chúng dưới consumer, vì Supplier phát dữ liệu ra ngoài. Cũng không đặt chúng dưới spring.cloud.stream.kafka.bindings hoặc spring.cloud.stream.rabbit.bindings: poller là cơ chế kích hoạt của framework, không phải tùy chọn kết nối riêng của broker.

## 5. Dùng nhiều Supplier với chu kỳ khác nhau

Một ứng dụng có thể đăng ký nhiều functional bean. Khi có nhiều bean Supplier/Function/Consumer, khai báo rõ các bean muốn kích hoạt bằng spring.cloud.function.definition. Dùng dấu chấm phẩy để liệt kê nhiều function độc lập; không dùng dấu gạch đứng vì dấu đó biểu diễn phép composition.

Ví dụ ứng dụng có hai nguồn:

~~~java
import java.time.Instant;
import java.util.UUID;
import java.util.function.Supplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public record OrderCreated(String orderId, Instant createdAt) {}

public record MetricSnapshot(Instant capturedAt, long activeOrders) {}

@Configuration
class EventSources {

    @Bean
    Supplier<OrderCreated> orderEvents() {
        return () -> new OrderCreated(
            UUID.randomUUID().toString(),
            Instant.now()
        );
    }

    @Bean
    Supplier<MetricSnapshot> metricSnapshots() {
        return () -> new MetricSnapshot(Instant.now(), 42L);
    }
}
~~~

Khai báo cấu hình cho từng output:

~~~yaml
spring:
  cloud:
    function:
      definition: "orderEvents;metricSnapshots"
    stream:
      bindings:
        orderEvents-out-0:
          destination: orders.created
          content-type: application/json
          producer:
            poller:
              fixed-delay: 500
              initial-delay: 0
              max-messages-per-poll: 1
        metricSnapshots-out-0:
          destination: metrics.snapshots
          content-type: application/json
          producer:
            poller:
              fixed-delay: 30000
              initial-delay: 5000
              max-messages-per-poll: 1
~~~

Hai nguồn có lịch khác nhau:

| Supplier | Output binding | Destination | Fixed delay | Initial delay |
|---|---|---|---:|---:|
| orderEvents | orderEvents-out-0 | orders.created | 500 ms | 0 ms |
| metricSnapshots | metricSnapshots-out-0 | metrics.snapshots | 30000 ms | 5000 ms |

Nhờ cấu hình theo binding, việc thay đổi chu kỳ tạo bản chụp số liệu không làm thay đổi nhịp phát sự kiện đơn hàng. Mỗi output binding có thể có destination, content type và lịch poll riêng.

Các ví dụ trên minh họa cấu hình lịch; trong ứng dụng thật, Supplier cần lấy dữ liệu từ nguồn nghiệp vụ. Không nên phát một bản ghi giả lập mỗi chu kỳ nếu mục tiêu là đọc các bản ghi đang chờ xử lý.

## 6. Chọn fixed-delay hay cron

Poller hỗ trợ lịch định kỳ theo fixed-delay hoặc Cron Trigger. Chọn cách phù hợp với ý nghĩa thời gian của tác vụ:

| Cách lập lịch | Phù hợp khi | Ví dụ |
|---|---|---|
| fixed-delay | Muốn chờ một khoảng thời gian giữa các lần poll | Kiểm tra hàng đợi công việc mỗi 2 giây |
| cron | Muốn chạy vào thời điểm theo lịch | Phát báo cáo vào đầu mỗi giờ |

Ví dụ dùng cron cho một output binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        hourlyReport-out-0:
          destination: reports.hourly
          producer:
            poller:
              cron: "0 0 * * * *"
              max-messages-per-poll: 1
~~~

Biểu thức Cron của Spring có trường giây ở đầu. Biểu thức 0 0 * * * * có nghĩa là chạy tại giây 0, phút 0 của mỗi giờ. Khi dùng cron, không cần đồng thời đặt fixed-delay cho cùng poller; hãy chọn một kiểu lịch để tránh cấu hình khó hiểu.

fixed-delay phù hợp với việc thăm dò liên tục, trong khi cron phù hợp với tác vụ có lịch cố định theo đồng hồ. Cả hai đều không đảm bảo thời điểm gửi tuyệt đối chính xác khi ứng dụng bận, JVM tạm dừng, máy chủ quá tải hoặc broker không sẵn sàng.

## 7. Hiểu max-messages-per-poll

max-messages-per-poll giới hạn số thông điệp mà poller có thể tạo trong một lần kích hoạt. Giá trị mặc định là 1. Với Supplier đọc từng bản ghi từ nguồn dữ liệu, giá trị lớn hơn 1 có thể cho phép một lần poll lấy nhiều bản ghi liên tiếp cho đến khi đạt giới hạn hoặc nguồn không còn dữ liệu.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        pendingOrders-out-0:
          destination: orders.pending
          producer:
            poller:
              fixed-delay: 5000
              max-messages-per-poll: 20
~~~

Poller có thể lấy tối đa 20 thông điệp trong một lần poll. Điều đó không có nghĩa hệ thống luôn phát đủ 20 thông điệp; số thực tế phụ thuộc vào số dữ liệu sẵn có và cách Supplier biểu diễn việc không còn dữ liệu.

Tăng max-messages-per-poll có thể tăng thông lượng khi nguồn có nhiều bản ghi, nhưng cũng làm một lần poll kéo dài hơn và tạo tải đột biến lên broker. Hãy cân nhắc kích thước lô, thời gian xử lý, giới hạn truy vấn, bộ nhớ và năng lực nhận của hệ thống đích.

Không nhầm max-messages-per-poll với batch mode của Kafka consumer. Thuộc tính này điều khiển số thông điệp được tạo bởi poller phía producer; batch consumption là cơ chế đọc thông điệp ở phía consumer và có cấu hình khác.

## 8. Supplier imperative và Supplier reactive

Poller mặc định phù hợp với Supplier imperative có dạng Supplier<T>. Mỗi lần get() trả về một giá trị, framework có thể gửi giá trị đó thành một thông điệp.

Supplier reactive có dạng Supplier<Flux<T>> thường được gọi một lần để cung cấp một luồng liên tục. Framework không lặp việc gọi get() theo chu kỳ như với Supplier imperative, vì Flux đã đại diện cho luồng dữ liệu sẽ phát tiếp tục.

Nếu Supplier<Flux<T>> đại diện một tập dữ liệu hữu hạn cần truy vấn định kỳ, có thể dùng annotation PollableBean để báo cho framework rằng nguồn reactive này vẫn cần được poll. Ví dụ:

~~~java
import org.springframework.cloud.function.context.PollableBean;
import reactor.core.publisher.Flux;
import java.util.function.Supplier;

@PollableBean
public Supplier<Flux<String>> pendingBatch() {
    return () -> Flux.just("order-A", "order-B");
}
~~~

Hành vi pollable của Supplier reactive có thể phụ thuộc cách chia luồng thành từng thông điệp và cấu hình splittable. Cần kiểm tra tài liệu phiên bản đang sử dụng trước khi áp dụng. Không thêm PollableBean chỉ vì Supplier trả về Flux; chỉ dùng khi luồng hữu hạn cần được lấy lại theo lịch.

## 9. Poller và nguồn phát bên ngoài

Không phải mọi output binding đều cần Supplier. Nếu dữ liệu đến từ HTTP endpoint, callback hoặc một hệ thống đã có cơ chế kích hoạt riêng, ứng dụng có thể dùng StreamBridge để gửi thông điệp khi sự kiện xảy ra.

Ví dụ:

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final StreamBridge streamBridge;

    public OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(OrderCreated event) {
        return streamBridge.send("ordersOutput-out-0", event);
    }
}
~~~

Trong trường hợp này, StreamBridge gửi khi phương thức publish được gọi. Không cần poller cho output binding đó. Nếu vừa tạo Supplier poll theo lịch vừa dùng StreamBridge để phát cùng loại dữ liệu, cần xác định rõ trách nhiệm của từng nguồn để tránh phát trùng.

## 10. Thread, thời gian xử lý và tải nguồn dữ liệu

Supplier được poll bởi cơ chế scheduling của framework. Không nên giả định get() chạy trên thread xử lý HTTP request hoặc trên một thread cố định của ứng dụng. Điều này quan trọng khi Supplier dùng ThreadLocal, tracing context hoặc thư viện yêu cầu thread affinity.

Một số nguyên tắc vận hành:

- Giữ thời gian thực thi của get() có giới hạn và đặt timeout cho lời gọi phụ thuộc.
- Tránh để một truy vấn chậm giữ poller quá lâu.
- Đặt giới hạn số bản ghi lấy trong mỗi lần poll.
- Theo dõi thời gian poll, số thông điệp phát và lỗi truy cập nguồn dữ liệu.
- Chọn chu kỳ phù hợp với khả năng nhận của broker và consumer.
- Tránh dùng nhiều Supplier để thăm dò cùng một tập bản ghi nếu chưa có cơ chế chia quyền lấy dữ liệu.

Nếu một lần poll mất nhiều thời gian, chu kỳ thực tế có thể giãn ra. Poller là cơ chế lập lịch, không phải cam kết thông lượng. Khi cần điều khiển thread hoặc gửi từ một callback có sẵn, StreamBridge thường phù hợp hơn.

## 11. Poller không thay thế cơ chế bảo đảm giao nhận

Poller quyết định thời điểm gọi Supplier. Nó không tự bảo đảm bản ghi đã được ghi vào broker đúng một lần hoặc không bị mất. Nếu Supplier đọc một hàng trong cơ sở dữ liệu rồi đánh dấu đã xử lý trước khi việc gửi được broker xác nhận, lỗi mạng có thể khiến dữ liệu không được phát nhưng nguồn đã coi là hoàn tất.

Với dữ liệu nghiệp vụ cần độ tin cậy cao, có thể dùng Transactional Outbox:

1. Transaction nghiệp vụ ghi dữ liệu và một bản ghi outbox trong cùng transaction cơ sở dữ liệu.
2. Supplier đọc các bản ghi outbox chưa phát.
3. Ứng dụng gửi bản ghi qua output binding.
4. Khi có chiến lược xác nhận phù hợp, đánh dấu bản ghi đã phát hoặc lưu trạng thái gửi.
5. Consumer xử lý idempotent để chịu được thông điệp được giao lại.

Việc đánh dấu hoàn tất cần được thiết kế cẩn thận theo khả năng xác nhận của binder và broker. Không nên xóa hoặc đánh dấu bản ghi trước khi có bằng chứng gửi thành công. Poller có thể chạy lại sau lỗi hoặc khi ứng dụng khởi động lại; vì vậy, khóa định danh và khả năng xử lý lặp là cần thiết.

## 12. Kiểm thử cấu hình poller

Nên kiểm tra cả logic Supplier và hành vi binding:

| Cấp kiểm thử | Điều cần xác minh |
|---|---|
| Unit test Supplier | get() trả đúng dữ liệu, xử lý nguồn rỗng và lỗi phụ thuộc |
| Test Binder | Giá trị từ Supplier được gửi đến đúng output binding và payload được chuyển đổi đúng |
| Integration test | Poller theo lịch, destination và binder hoạt động với broker thật |
| Kiểm thử tải | Chu kỳ và max-messages-per-poll không làm quá tải nguồn hoặc broker |

Không nên dùng Thread.sleep dài trong unit test chỉ để chờ poller chạy. Hãy kiểm tra Supplier trực tiếp ở unit test; dành kiểm tra lịch và binding cho integration test có thời gian chờ được kiểm soát.

Khi xác minh nhiều poller, kiểm tra rằng mỗi bean có đúng binding name và mỗi binding có đúng fixed-delay hoặc cron. Quan sát log khởi tạo, thời điểm phát và số lượng thông điệp tại destination. Nếu hai nguồn phát có lịch khác nhau nhưng tốc độ thực tế giống nhau, hãy kiểm tra xem cấu hình per-binding có đặt đúng dưới producer.poller hay đang bị cấu hình dùng chung chi phối.

## 13. Các lỗi cấu hình thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Supplier vẫn phát mỗi giây | Chỉ thay đổi một thuộc tính không đúng prefix hoặc sai binding name | Kiểm tra spring.cloud.stream.bindings.<binding>.producer.poller |
| Tất cả Supplier cùng đổi chu kỳ | Đặt spring.integration.poller thay vì cấu hình riêng | Chuyển thuộc tính vào producer.poller của từng output |
| Poller không chạy | Bean không được chọn trong function definition hoặc không được phát hiện | Kiểm tra tên bean và spring.cloud.function.definition |
| Poller chạy nhưng không có thông điệp | Supplier trả về null, nguồn không có dữ liệu hoặc phát sinh lỗi | Kiểm tra get(), log và trạng thái nguồn dữ liệu |
| Lịch cron chạy sai thời điểm | Biểu thức Cron hoặc múi giờ không đúng kỳ vọng | Kiểm tra cú pháp Cron của Spring và timezone môi trường |
| Supplier reactive chỉ được gọi một lần | Flux được hiểu là luồng liên tục | Dùng Supplier imperative hoặc PollableBean cho luồng hữu hạn cần poll |
| Phát trùng dữ liệu sau khi khởi động lại | Nguồn chưa lưu checkpoint hoặc thao tác gửi không idempotent | Dùng outbox, trạng thái phát và khóa chống trùng |

Ví dụ sai: đặt poller dưới consumer:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderEvents-out-0:
          consumer:
            poller:
              fixed-delay: 5000
~~~

Output binding cần cấu hình dưới producer:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderEvents-out-0:
          producer:
            poller:
              fixed-delay: 5000
~~~

Khi không thấy cấu hình có tác dụng, kiểm tra lần lượt tên bean, tên binding, function definition, cấp producer.poller và nguồn cấu hình có thể ghi đè. Không thay đổi destination hoặc binder nếu vấn đề chỉ nằm ở lịch poll.

## 14. Quy trình cấu hình cho từng nguồn phát

Khi thêm một Supplier mới, thực hiện theo thứ tự:

1. Xác định nguồn dữ liệu và tần suất nghiệp vụ cần phát.
2. Đăng ký Supplier bean với tên rõ ràng.
3. Xác định output binding mặc định từ tên bean.
4. Chọn destination và content type cho binding.
5. Đặt fixed-delay hoặc cron trong producer.poller của binding.
6. Chọn initial-delay và max-messages-per-poll theo đặc tính nguồn dữ liệu.
7. Kiểm thử Supplier trực tiếp và kiểm thử output bằng Test Binder.
8. Chạy integration test với broker tương ứng.
9. Theo dõi tốc độ phát, độ trễ, lỗi và tình trạng dữ liệu nguồn.
10. Thiết kế checkpoint, outbox hoặc idempotency nếu dữ liệu cần bảo đảm giao nhận.

Tách poller theo output binding giúp mỗi nguồn phát có lịch phù hợp với dữ liệu và tải của nó. Supplier tập trung tạo dữ liệu; poller quyết định thời điểm gọi; output binding và binder đảm nhiệm việc gửi thông điệp đến broker.

## Tài liệu tham khảo chính thức

- [Spring Cloud Stream - Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html): Supplier, poller mặc định, thuộc tính poller và cấu hình riêng theo output binding.
- [Spring Cloud Function - Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): functional bean, Supplier imperative/reactive và function definition.
- [Spring Boot - Integration Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html): các thuộc tính Spring Integration poller do Spring Boot cung cấp.
