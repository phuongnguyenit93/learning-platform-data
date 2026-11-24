# Phân biệt tên bean, tên binding và tên destination

Khi cấu hình Spring Cloud Stream, một lỗi dễ gặp là dùng lẫn tên hàm Java, tên binding và tên destination. Ba tên này có liên quan nhưng đại diện cho ba lớp khác nhau. Tên bean xác định hàm nào được Spring Cloud Function nhận diện; tên binding xác định cổng vào hoặc ra mà Spring Cloud Stream quản lý; destination xác định luồng logic trên broker mà binding kết nối đến.

Ví dụ, bean validateOrder có binding đầu vào validateOrder-in-0 và binding đầu ra validateOrder-out-0. Hai binding này có thể lần lượt kết nối đến destination orders.created và orders.validated. Nếu chỉ đổi tên destination, tên bean và tên binding vẫn giữ nguyên. Nếu đổi tên bean, các tên binding mặc định được suy ra từ tên mới và cấu hình cần được cập nhật tương ứng.

## 1. Ba khái niệm và trách nhiệm của từng tên

### Tên bean hàm

Tên bean là định danh Spring dùng để đăng ký một thành phần trong application context. Với phương thức được đánh dấu @Bean, tên phương thức thường trở thành tên bean mặc định. Ví dụ:

~~~java
@Bean
public Function<OrderCreated, OrderValidated> validateOrder() {
    return event -> new OrderValidated(
            event.orderId(),
            event.customerId(),
            "VALIDATED");
}
~~~

Trong ví dụ này, tên bean là validateOrder. Spring Cloud Function sử dụng tên bean để chọn hàm cần kích hoạt thông qua spring.cloud.function.definition. Vì vậy, tên bean thuộc lớp khai báo và lựa chọn logic xử lý trong ứng dụng.

Nếu khai báo @Bean(name = "checkOrder"), tên bean được đăng ký theo tên đã chỉ định; khi đó phải dùng tên bean tương ứng trong function definition. Không nên đổi tên phương thức hoặc tên bean mà quên cập nhật cấu hình chọn hàm.

### Tên binding

Binding là kết nối logic giữa cổng vào/ra của hàm và hạ tầng truyền tin. Với mô hình hàm, Spring Cloud Stream tạo tên binding mặc định từ tên bean và hướng dữ liệu:

| Loại bean | Binding mặc định |
|---|---|
| Supplier<T> orderSource | orderSource-out-0 |
| Function<T, R> validateOrder | validateOrder-in-0, validateOrder-out-0 |
| Consumer<T> auditOrder | auditOrder-in-0 |

Hậu tố in-0 chỉ đầu vào thứ nhất, còn out-0 chỉ đầu ra thứ nhất. Hàm có nhiều đầu vào hoặc đầu ra có thể có thêm chỉ số tương ứng. Binding là tên mà ta dùng để cấu hình destination, group, content type và các thuộc tính của cổng message.

### Tên destination

Destination là tên logic của luồng message trên broker. Ví dụ orders.created có thể ánh xạ đến topic Kafka, exchange RabbitMQ hoặc topic Pulsar tùy binder. Destination cho biết message được gửi đến hoặc nhận từ luồng nào; nó không phải tên bean và cũng không phải tên binding.

Nhiều binding có thể cùng trỏ đến một destination. Đây là trường hợp thường gặp: đầu ra của producer gửi đến orders.created, còn đầu vào của consumer đọc từ chính destination đó. Hai binding vẫn có tên riêng vì chúng thuộc về hai cổng khác nhau.

## 2. Theo dõi tên qua một pipeline

Giả sử ứng dụng có ba hàm:

~~~java
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderFunctions {

    @Bean
    Supplier<OrderCreated> orderSource() {
        return () -> new OrderCreated("ORD-1001", "CUST-01");
    }

    @Bean
    Function<OrderCreated, OrderValidated> validateOrder() {
        return event -> new OrderValidated(
                event.orderId(), event.customerId(), "VALIDATED");
    }

    @Bean
    Consumer<OrderValidated> auditOrder() {
        return event -> System.out.println(
                "Received " + event.orderId() + ": " + event.status());
    }
}

record OrderCreated(String orderId, String customerId) {}

record OrderValidated(String orderId, String customerId, String status) {}
~~~

Kích hoạt các hàm và cấu hình binding trong application.yml:

~~~yaml
spring:
  cloud:
    function:
      definition: orderSource;validateOrder;auditOrder
    stream:
      bindings:
        orderSource-out-0:
          destination: orders.created
          content-type: application/json

        validateOrder-in-0:
          destination: orders.created
          group: order-validator
          content-type: application/json
        validateOrder-out-0:
          destination: orders.validated
          content-type: application/json

        auditOrder-in-0:
          destination: orders.validated
          group: order-audit
          content-type: application/json
~~~

Đọc cấu hình theo ba lớp:

| Tên bean | Tên binding | Destination |
|---|---|---|
| orderSource | orderSource-out-0 | orders.created |
| validateOrder | validateOrder-in-0 | orders.created |
| validateOrder | validateOrder-out-0 | orders.validated |
| auditOrder | auditOrder-in-0 | orders.validated |

spring.cloud.function.definition chọn bean orderSource, validateOrder và auditOrder. Các khóa trong spring.cloud.stream.bindings là tên binding. Thuộc tính destination bên trong mỗi binding mới là tên luồng được dùng trên broker.

Luồng message có thể biểu diễn như sau:

~~~text
Bean orderSource
    |
    v
Binding orderSource-out-0
    |
    v
Destination orders.created
    |
    v
Binding validateOrder-in-0
    |
    v
Bean validateOrder
    |
    v
Binding validateOrder-out-0
    |
    v
Destination orders.validated
    |
    v
Binding auditOrder-in-0
    |
    v
Bean auditOrder
~~~

Destination orders.created được dùng ở một binding đầu ra và một binding đầu vào. Đây là hai đầu kết nối độc lập đến cùng luồng message. group: order-validator xác định nhóm consumer cho đầu vào của hàm kiểm tra; group: order-audit xác định nhóm riêng cho consumer kiểm toán. Hai nhóm có thể nhận cùng sự kiện theo ngữ nghĩa pub/sub của broker và binder.

## 3. Đổi tên bean ảnh hưởng đến binding như thế nào?

Tên binding mặc định được suy ra từ tên bean hàm. Nếu đổi phương thức validateOrder thành checkOrder, tên bean mặc định đổi theo và binding mặc định cũng đổi:

| Trước khi đổi | Sau khi đổi |
|---|---|
| Bean validateOrder | Bean checkOrder |
| validateOrder-in-0 | checkOrder-in-0 |
| validateOrder-out-0 | checkOrder-out-0 |

Khi đó, cập nhật cả function definition và khóa binding:

~~~yaml
spring:
  cloud:
    function:
      definition: orderSource;checkOrder;auditOrder
    stream:
      bindings:
        checkOrder-in-0:
          destination: orders.created
          group: order-validator
        checkOrder-out-0:
          destination: orders.validated
~~~

Destination có thể giữ nguyên vì luồng nghiệp vụ vẫn dùng cùng tên. Nếu chỉ đổi tên bean trong mã Java nhưng để cấu hình cũ, Spring Cloud Stream có thể không tìm thấy binding mà ứng dụng dự định cấu hình hoặc hàm không được kích hoạt như mong muốn. Hãy kiểm tra log khởi động và danh sách binding đang hoạt động khi đổi tên hàm.

## 4. Đổi tên binding mà không đổi tên bean

Trong một số dự án, tên binding mặc định dài hoặc không phù hợp với quy ước cấu hình. Spring Cloud Stream cho phép ánh xạ tên binding mặc định sang một tên tường minh bằng thuộc tính spring.cloud.stream.function.bindings.

Ví dụ, giữ bean validateOrder nhưng đổi tên binding đầu vào thành orders-input và đầu ra thành validated-output:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      function:
        bindings:
          validateOrder-in-0: orders-input
          validateOrder-out-0: validated-output
      bindings:
        orders-input:
          destination: orders.created
          group: order-validator
          content-type: application/json
        validated-output:
          destination: orders.validated
          content-type: application/json
~~~

Sau khi ánh xạ, validateOrder-in-0 và validateOrder-out-0 vẫn là tên binding mặc định được tạo từ hàm. Tên orders-input và validated-output là tên binding tường minh dùng trong phần cấu hình spring.cloud.stream.bindings. Bean vẫn tên validateOrder, còn destination vẫn là orders.created và orders.validated.

Việc ánh xạ tên binding là một lớp gián tiếp bổ sung. Chỉ sử dụng khi có lợi ích rõ ràng, chẳng hạn cần quy ước tên ổn định cho nhiều hàm hoặc tránh lặp tên dài trong cấu hình. Nếu không cần, giữ tên mặc định giúp người đọc dễ lần từ tên bean sang binding.

## 5. Đổi destination mà không đổi bean hoặc binding

Nếu cần chuyển luồng message sang tên destination khác, chỉ thay giá trị destination ở binding tương ứng. Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          destination: sales.order-created.v2
          group: order-validator
        validateOrder-out-0:
          destination: sales.order-validated.v2
~~~

Trong ví dụ này:

- Bean vẫn là validateOrder.
- Binding vẫn là validateOrder-in-0 và validateOrder-out-0.
- Destination đổi thành sales.order-created.v2 và sales.order-validated.v2.

Đổi destination có thể khiến binder kết nối đến tài nguyên broker khác hoặc tạo tài nguyên mới theo cấu hình. Với consumer, đổi destination có thể làm ứng dụng đọc một luồng mới và không còn đọc message ở luồng cũ. Với producer, đổi destination có thể chuyển message sang nơi nhận khác. Trước khi đổi, cần xác định cách chuyển tiếp dữ liệu, thời gian chạy song song, quyền truy cập và chính sách lưu giữ để tránh bỏ sót message.

## 6. Destination giống nhau không có nghĩa binding giống nhau

Một producer và nhiều consumer có thể kết nối đến cùng destination:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderSource-out-0:
          destination: orders.created
        inventory-in-0:
          destination: orders.created
          group: inventory-service
        billing-in-0:
          destination: orders.created
          group: billing-service
        analytics-in-0:
          destination: orders.created
          group: analytics-service
~~~

Giả sử ứng dụng đã khai báo bean consumer tương ứng với các tên inventory, billing và analytics. Ở đây có bốn binding nhưng chỉ một tên destination logic. Mỗi consumer có group riêng để xử lý sự kiện theo mục đích của nó. Nếu inventory, billing và analytics vô tình dùng chung một group, chúng có thể cạnh tranh nhận message như các instance của cùng một dịch vụ, khiến mỗi sự kiện chỉ đến một nhóm xử lý thay vì cả ba nhóm đều nhận được.

Ngược lại, nếu các instance của cùng một dịch vụ dùng group khác nhau ngoài ý muốn, mỗi instance có thể nhận cùng luồng độc lập và lặp lại side effect. Vì vậy, chọn group là quyết định về ngữ nghĩa phân phối; nó không phải tên thay thế cho destination hay tên bean.

Ánh xạ vật lý phụ thuộc binder:

- Với Kafka, destination thường là topic; group là consumer group và các consumer trong group chia partition.
- Với RabbitMQ, destination thường gắn với exchange; group được ánh xạ đến queue của nhóm. Các consumer trong cùng queue chia tải.
- Với Pulsar, destination là topic; group liên quan đến subscription và kiểu subscription quyết định cách consumer phối hợp.

Do đó, không suy luận rằng một destination chung tự động tạo ra fan-out cho mọi consumer. Hãy kiểm tra group hoặc subscription của từng bên nhận và cấu hình định tuyến thực tế của broker.

## 7. Phân biệt tên trong log và khi gỡ lỗi

Khi ứng dụng khởi động, log có thể nhắc đến tên bean, binding, destination hoặc tài nguyên broker. Đọc đúng lớp tên giúp xác định vị trí lỗi:

| Dấu hiệu | Cần kiểm tra |
|---|---|
| Không tìm thấy hàm hoặc function definition không khớp | Tên bean, phương thức @Bean, cấu hình spring.cloud.function.definition |
| Binding không được tạo hoặc không có cấu hình mong muốn | Tên binding mặc định, chỉ số in-0/out-0, ánh xạ binding tường minh |
| Binding hoạt động nhưng không có message | Destination, tài nguyên broker, quyền truy cập và producer |
| Producer gửi được nhưng consumer không nhận | Destination đầu vào, group/subscription, routing hoặc partition assignment |
| Consumer nhận message nhưng chuyển đổi thất bại | content-type, schema, header và message converter |

Một quy trình kiểm tra hữu ích:

1. Xác nhận bean có được Spring đăng ký và tên bean đúng với function definition.
2. Xác định binding mặc định mà bean tạo ra dựa trên loại hàm và hướng dữ liệu.
3. Nếu có đổi tên binding, kiểm tra ánh xạ trong spring.cloud.stream.function.bindings.
4. Kiểm tra spring.cloud.stream.bindings.<binding-name>.destination và group của binding đầu vào.
5. Kiểm tra tài nguyên broker thực tế và quyền truy cập của ứng dụng.
6. Gửi một message mẫu và theo dõi nó qua producer, destination và consumer.

Đừng sửa destination khi lỗi thực ra nằm ở tên binding. Tương tự, đổi tên bean không giải quyết được lỗi routing của RabbitMQ hoặc lỗi group của Kafka.

## 8. Kiểm thử cấu hình tên

Kiểm thử binding giúp xác nhận tên binding mà ứng dụng sử dụng và message được gửi/nhận qua đúng cổng. Spring Cloud Stream test binder cung cấp InputDestination và OutputDestination để kiểm thử mà không cần broker thật.

Ví dụ kiểm thử hàm validateOrder:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest(properties = {
        "spring.cloud.function.definition=validateOrder",
        "spring.cloud.stream.bindings.validateOrder-in-0.destination=orders.in",
        "spring.cloud.stream.bindings.validateOrder-out-0.destination=orders.out"
})
class ValidateOrderTest {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void usesTheExpectedBindings() {
        OrderCreated event = new OrderCreated("ORD-TEST", "CUST-TEST");

        input.send(
                MessageBuilder.withPayload(event).build(),
                "validateOrder-in-0");

        assertNotNull(output.receive(1000, "validateOrder-out-0"));
    }
}
~~~

Test binder kiểm tra được kết nối logic trong ứng dụng, nhưng không chứng minh Kafka topic, RabbitMQ exchange/queue hoặc Pulsar subscription được tạo đúng. Với từng binder triển khai, bổ sung kiểm thử tích hợp để xác nhận tài nguyên broker, group, routing, partition, xác nhận message và retry/DLQ.

## 9. Quy tắc đặt tên dễ bảo trì

Để giảm nhầm lẫn khi module có nhiều hàm và nhiều luồng, nên áp dụng một số quy tắc:

- Đặt tên bean theo hành động nghiệp vụ, ví dụ validateOrder, publishPayment hoặc auditShipment.
- Giữ tên binding mặc định khi nó đã đủ rõ; chỉ ánh xạ sang tên tường minh khi cần quy ước ổn định hoặc cấu hình dễ đọc hơn.
- Đặt destination theo tên sự kiện hoặc luồng nghiệp vụ, ví dụ orders.created và payments.completed, tránh gắn tên destination với một instance cụ thể.
- Đặt group theo dịch vụ hoặc mục đích xử lý ổn định, ví dụ inventory-service và billing-service.
- Ghi lại quan hệ bean → binding → destination → group trong tài liệu vận hành hoặc sơ đồ luồng.
- Khi đổi tên, cập nhật function definition, ánh xạ binding và khóa cấu hình có liên quan trong cùng thay đổi; kiểm thử khởi động và gửi/nhận message.

Ba định danh giải quyết ba câu hỏi khác nhau: bean nào xử lý dữ liệu, cổng nào kết nối với broker, và message đi qua luồng nào. Giữ ranh giới đó rõ ràng giúp cấu hình Spring Cloud Stream dễ đọc, dễ đổi tên và dễ gỡ lỗi hơn, đồng thời tránh nhầm lẫn giữa việc đổi logic xử lý, đổi kết nối và chuyển message sang destination khác.
