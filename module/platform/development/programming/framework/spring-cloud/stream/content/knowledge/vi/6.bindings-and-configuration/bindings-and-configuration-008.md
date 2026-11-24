# Khai báo binding tường minh bằng input-bindings và output-bindings

Spring Cloud Stream thường tạo binding dựa trên các bean Supplier, Function hoặc Consumer. Tuy nhiên, có những ứng dụng nhận dữ liệu từ một framework khác, chẳng hạn Spring Integration, hoặc phát sự kiện từ REST controller, scheduler và dịch vụ nghiệp vụ. Trong những trường hợp đó, ứng dụng có thể cần binding mà không cần khai báo một bean hàm chỉ để làm điểm vào hoặc điểm ra của luồng.

Spring Cloud Stream hỗ trợ khai báo binding tường minh bằng hai thuộc tính **spring.cloud.stream.input-bindings** và **spring.cloud.stream.output-bindings**. Các thuộc tính này tạo binding độc lập với function. Input binding kết nối dữ liệu từ broker vào ứng dụng; output binding kết nối dữ liệu do ứng dụng gửi ra broker. Ứng dụng chịu trách nhiệm kết nối các binding đó với logic xử lý hoặc nguồn phát dữ liệu của mình.

## 1. Khi nào cần binding tường minh?

Hãy dùng binding tường minh khi tên và hướng của luồng dữ liệu đã biết, nhưng nguồn phát hoặc thành phần xử lý không được biểu diễn bằng Supplier, Function hay Consumer.

Một số tình huống thường gặp:

- Một REST controller nhận yêu cầu HTTP rồi phát sự kiện lên broker.
- Một tác vụ định kỳ hoặc ApplicationRunner đọc dữ liệu từ hệ thống khác và phát thông điệp.
- Một luồng Spring Integration cần nhận thông điệp từ broker qua channel rồi xử lý bằng IntegrationFlow.
- Ứng dụng tích hợp thư viện hoặc framework bên ngoài có mô hình message channel riêng.
- Ứng dụng cần tạo sẵn output binding khi khởi động để áp dụng cấu hình destination, binder và producer trước khi phát sinh yêu cầu gửi đầu tiên.

Ví dụ, dịch vụ đơn hàng có thể nhận sự kiện từ topic hoặc queue **orders**, chuyển sự kiện vào một IntegrationFlow để xử lý. Khi xử lý xong, một REST endpoint khác có thể gửi thông báo tới destination **notifications** thông qua StreamBridge. Hai binding này không nhất thiết phải gắn với một bean Function.

## 2. Hai thuộc tính khai báo input và output

Hai thuộc tính có tên ở dạng số nhiều vì mỗi thuộc tính có thể nhận nhiều tên binding:

| Thuộc tính | Mục đích | Hướng dữ liệu |
|---|---|---|
| **spring.cloud.stream.input-bindings** | Tạo một hoặc nhiều input binding. | Broker → ứng dụng |
| **spring.cloud.stream.output-bindings** | Tạo một hoặc nhiều output binding. | Ứng dụng → broker |

Các tên binding được phân tách bằng dấu chấm phẩy (**;**). Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      input-bindings: ordersIn;refundsIn
      output-bindings: notificationsOut;auditOut
~~~

Cấu hình trên yêu cầu framework tạo hai input binding có tên **ordersIn** và **refundsIn**, cùng hai output binding có tên **notificationsOut** và **auditOut**.

Binding tường minh không cần hậu tố **-in-0** hoặc **-out-0**. Tên đã khai báo chính là tên binding, vì hướng input hay output đã được xác định bởi thuộc tính chứa tên đó. Ví dụ, output binding **notificationsOut** được cấu hình bằng **spring.cloud.stream.bindings.notificationsOut.destination**, không phải **notificationsOut-out-0.destination**.

Điểm này khác với binding được suy ra từ function. Nếu bean Function tên **normalizeOrder**, Spring Cloud Stream tạo các binding **normalizeOrder-in-0** và **normalizeOrder-out-0**. Với binding tường minh, tên **ordersIn** hoặc **notificationsOut** được dùng trực tiếp.

## 3. Cấu hình destination và thuộc tính cho từng binding

Sau khi khai báo tên binding, cấu hình destination và các thuộc tính chung theo mẫu:

**spring.cloud.stream.bindings.<tên-binding>.<thuộc-tính>**

Ví dụ hoàn chỉnh:

~~~yaml
spring:
  application:
    name: order-integration
  cloud:
    stream:
      input-bindings: ordersIn;refundsIn
      output-bindings: notificationsOut;auditOut
      bindings:
        ordersIn:
          destination: orders
          group: order-integration
          content-type: application/json
        refundsIn:
          destination: refunds
          group: refund-integration
          content-type: application/json
        notificationsOut:
          destination: notifications
          content-type: application/json
        auditOut:
          destination: audit-events
          content-type: application/json
~~~

Trong ví dụ:

- **ordersIn** nhận thông điệp từ destination **orders** và thuộc consumer group **order-integration**.
- **refundsIn** nhận thông điệp từ destination **refunds** và thuộc consumer group **refund-integration**.
- **notificationsOut** gửi thông điệp tới destination **notifications**.
- **auditOut** gửi thông điệp tới destination **audit-events**.

Thuộc tính **destination** xác định tài nguyên messaging mà binding kết nối tới. Tùy binder, destination có thể tương ứng với topic Kafka, exchange và queue do RabbitMQ binder quản lý, hoặc topic Pulsar. Không nên suy ra tên tài nguyên vật lý chỉ từ tên binding; hãy kiểm tra cách binder provision tài nguyên.

Thuộc tính **group** chỉ áp dụng cho input binding. Group giúp các bản sao của cùng một năng lực xử lý phối hợp nhận thông điệp theo ngữ nghĩa của broker. Nếu bỏ group, binding có thể hoạt động như một anonymous consumer và tài nguyên tiêu thụ có thể không giữ trạng thái theo cách mong muốn khi khởi động lại. Với luồng nghiệp vụ cần tiếp tục ổn định qua các lần triển khai, hãy chọn group có ý nghĩa và giữ tên nhất quán.

Thuộc tính **content-type** mô tả định dạng nội dung để Spring Cloud Stream thực hiện chuyển đổi thông điệp phù hợp. Nếu hệ thống bên ngoài gửi dữ liệu theo định dạng riêng hoặc sử dụng native serialization của broker, cần cấu hình serializer/deserializer và chế độ chuyển đổi tương ứng theo binder.

## 4. Kết nối input binding với Spring Integration

Khai báo **input-bindings** chỉ tạo binding và channel nhận dữ liệu. Ứng dụng vẫn cần đăng ký thành phần lắng nghe channel đó để xử lý thông điệp. Một cách tích hợp tự nhiên là sử dụng Spring Integration Java DSL.

Ví dụ, cấu hình input binding:

~~~yaml
spring:
  cloud:
    stream:
      input-bindings: ordersIn
      bindings:
        ordersIn:
          destination: orders
          group: order-integration
          content-type: application/json
~~~

Tạo IntegrationFlow đọc channel có tên **ordersIn**:

~~~java
@Configuration
public class OrderIntegrationConfiguration {

    @Bean
    IntegrationFlow ordersFlow(OrderService orderService) {
        return IntegrationFlow.from("ordersIn")
                .handle(orderService, "handle")
                .get();
    }
}
~~~

Phương thức **handle** của OrderService nhận đối tượng đã được chuyển đổi theo cấu hình message converter và xử lý nghiệp vụ. Tên channel trong **IntegrationFlow.from("ordersIn")** phải trùng với tên input binding đã khai báo. Nếu đổi tên binding, hãy cập nhật cả nơi tham chiếu channel.

Luồng dữ liệu có thể hình dung như sau:

~~~mermaid
flowchart LR
    A[Kafka, RabbitMQ hoặc Pulsar] --> B[Input binding ordersIn]
    B --> C[Message channel]
    C --> D[Spring IntegrationFlow]
    D --> E[OrderService]
~~~

Có thể dùng các adapter hoặc endpoint Spring Integration khác để đăng ký subscriber cho channel. Điều quan trọng là channel phải có thành phần nhận thông điệp; nếu không, binding vẫn có thể được tạo nhưng dữ liệu không đi tới logic nghiệp vụ như mong đợi.

## 5. Kết nối output binding với StreamBridge

Với output binding tường minh, ứng dụng có thể gửi dữ liệu qua **StreamBridge**. Đây là lựa chọn phù hợp khi dữ liệu được tạo từ REST controller, service hoặc một thành phần không phải Supplier.

Cấu hình output binding:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: notificationsOut
      bindings:
        notificationsOut:
          destination: notifications
          content-type: application/json
~~~

Một service có thể gửi thông báo:

~~~java
@Service
public class NotificationPublisher {

    private final StreamBridge streamBridge;

    public NotificationPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(Notification notification) {
        return streamBridge.send("notificationsOut", notification);
    }
}
~~~

Tên truyền vào **streamBridge.send("notificationsOut", notification)** phải khớp với output binding đã khai báo. Khi binding đã được tạo từ **output-bindings**, ứng dụng có thể cấu hình destination, content type và binder cho binding đó trước khi gửi dữ liệu.

Ví dụ tích hợp với REST:

~~~java
@RestController
@RequestMapping("/notifications")
public class NotificationController {

    private final NotificationPublisher publisher;

    public NotificationController(NotificationPublisher publisher) {
        this.publisher = publisher;
    }

    @PostMapping
    public ResponseEntity<Void> publish(@RequestBody Notification notification) {
        if (publisher.publish(notification)) {
            return ResponseEntity.accepted().build();
        }
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
    }
}
~~~

Giá trị boolean từ **StreamBridge.send** phản ánh kết quả gửi qua message channel của ứng dụng. Không nên diễn giải nó thành xác nhận rằng consumer đích đã xử lý thông điệp. Bảo đảm giao nhận cuối cùng còn phụ thuộc publisher confirm, transaction, acknowledgement và cấu hình riêng của binder cùng broker.

## 6. Binding tường minh và binding động của StreamBridge

Nếu gọi **StreamBridge.send** với tên output chưa tồn tại, StreamBridge có thể tạo output binding động ở lần gửi đầu tiên và tái sử dụng binding đã tạo cho những lần gửi tiếp theo. Đây là cách thuận tiện khi destination chỉ được biết lúc chạy.

Tuy nhiên, nếu tên binding và destination đã biết trước, **spring.cloud.stream.output-bindings** cho phép tạo binding ngay lúc khởi động. Hai cách có mục tiêu khác nhau:

| Cách tạo output | Thời điểm tạo | Khi phù hợp |
|---|---|---|
| **output-bindings** | Khi ứng dụng khởi tạo binding. | Destination đã biết trước; cần cấu hình và provision sớm. |
| StreamBridge tạo binding động | Khi gọi **send** lần đầu với tên chưa tồn tại. | Destination được xác định trong lúc chạy hoặc thay đổi theo yêu cầu. |

Ví dụ tạo sẵn hai output binding:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: notificationsOut;auditOut
      bindings:
        notificationsOut:
          destination: notifications
        auditOut:
          destination: audit-events
~~~

Sau đó có thể gọi:

~~~java
streamBridge.send("notificationsOut", notification);
streamBridge.send("auditOut", auditRecord);
~~~

Không nhầm tên binding với tên destination động. Trong trường hợp binding **notificationsOut** đã được khai báo, StreamBridge gửi qua binding đã cấu hình và destination của nó là **notifications**. Nếu gọi **send** với một tên chưa được khai báo như **tenant-events-42**, StreamBridge có thể xem tên đó là binding/destination động và tạo binding theo cơ chế động. Hãy kiểm soát đầu vào dùng để tạo tên động, tránh để một số lượng tên không giới hạn làm tăng tài nguyên hoặc cache trong tiến trình.

## 7. Cấu hình binder cho binding tường minh

Binding tường minh vẫn sử dụng binder như binding được tạo từ function. Nếu classpath có nhiều binder hoặc ứng dụng kết nối nhiều broker, có thể chỉ định binder cho từng binding bằng thuộc tính **binder**:

~~~yaml
spring:
  cloud:
    stream:
      input-bindings: ordersIn
      output-bindings: auditOut
      bindings:
        ordersIn:
          destination: orders
          group: order-integration
          binder: kafka
        auditOut:
          destination: audit-events
          binder: rabbit
~~~

Ví dụ giả định ứng dụng đã cấu hình các binder có tên **kafka** và **rabbit** tương ứng. Tên binder phải khớp với tên instance binder đã khai báo trong cấu hình ứng dụng. Chỉ thêm thuộc tính này khi thực sự cần chọn binder cụ thể; nếu chỉ có một default binder phù hợp, có thể để framework chọn binder mặc định.

Không phải mọi thuộc tính mở rộng đều dùng chung giữa Kafka, RabbitMQ và Pulsar. Thuộc tính chung như **destination**, **group** và **content-type** được cấu hình dưới tên binding. Các thuộc tính riêng về xác nhận gửi, consumer acknowledgement, TLS, retry, partition hoặc dead-letter cần theo đúng namespace và tài liệu của binder được chọn.

## 8. Phân biệt ba kiểu binding

Các tên và cơ chế tạo binding dễ bị nhầm khi một ứng dụng kết hợp function, binding tường minh và StreamBridge.

| Đặc điểm | Function binding | Binding tường minh | Binding động |
|---|---|---|---|
| Cách tạo | Suy ra từ bean và function definition. | Khai báo bằng input-bindings hoặc output-bindings. | Được tạo khi StreamBridge gửi tới tên chưa tồn tại. |
| Ví dụ tên input | **normalizeOrder-in-0** | **ordersIn** | Không áp dụng cho input theo cơ chế StreamBridge output động. |
| Ví dụ tên output | **normalizeOrder-out-0** | **notificationsOut** | Tên được truyền vào send, ví dụ **tenant-events-42**. |
| Liên kết với function | Có. | Không bắt buộc. | Không bắt buộc. |
| Cấu hình destination | Theo binding name của function. | Theo tên khai báo trực tiếp. | Có thể được tạo theo tên đích khi chạy hoặc cấu hình động. |

Với function binding, **spring.cloud.function.definition** chọn hàm cần chạy. Với binding tường minh, **input-bindings** và **output-bindings** tạo channel mà không cần function. Với binding động, StreamBridge tạo output khi có lệnh gửi tới tên chưa được đăng ký trước. Không dùng **input-bindings** hoặc **output-bindings** như cách thay thế cho **spring.cloud.function.definition**.

## 9. Kiểm thử binding tường minh

Nên kiểm tra riêng ba lớp: binding có được tạo không, channel có được nối với logic ứng dụng không, và broker thật có nhận/giao thông điệp theo cấu hình không.

Test binder của Spring Cloud Stream cho phép kiểm thử luồng trong ứng dụng mà không cần khởi động Kafka, RabbitMQ hoặc Pulsar. Có thể khởi tạo ứng dụng kiểm thử với các thuộc tính:

~~~text
spring.cloud.stream.input-bindings=ordersIn;refundsIn
spring.cloud.stream.output-bindings=notificationsOut;auditOut
~~~

Một số tình huống kiểm thử cần có:

| Tình huống | Cách kiểm tra | Kết quả mong đợi |
|---|---|---|
| Một input binding | Khai báo **input-bindings=ordersIn**. | Binding và channel **ordersIn** được tạo. |
| Nhiều input binding | Khai báo tên phân tách bằng dấu chấm phẩy. | Từng input binding được tạo với tên chính xác. |
| Nhiều output binding | Khai báo **output-bindings=notificationsOut;auditOut**. | Các output binding được tạo khi khởi động. |
| Tên không có hậu tố | Kiểm tra tên binding trong context hoặc công cụ quan sát binding. | Tên là **ordersIn** hoặc **notificationsOut**, không tự thêm **-in-0** hay **-out-0**. |
| Input qua IntegrationFlow | Gửi thông điệp thử vào input binding. | IntegrationFlow nhận thông điệp và gọi đúng service. |
| Output qua StreamBridge | Gọi service gửi một thông điệp thử. | Thông điệp đi qua đúng output binding và destination. |
| Nhiều binder | Gán binder cho từng binding và chạy với binder thử nghiệm tương ứng. | Mỗi binding kết nối đúng binder. |
| Destination sai hoặc thiếu quyền | Dùng cấu hình thử nghiệm không hợp lệ. | Ứng dụng ghi nhận lỗi provision hoặc kết nối rõ ràng; không đánh dấu thông điệp đã được xử lý thành công. |

Sau kiểm thử bằng test binder, hãy chạy integration test với broker thật hoặc broker container phù hợp. Kiểm tra topic, exchange, queue hoặc subscription được provision; xác nhận group của input binding; gửi và nhận thông điệp có payload thực tế; đồng thời kiểm tra serializer, content type và quyền truy cập.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Binding không được tạo | Tên thuộc tính sai, sai namespace hoặc tên bị bỏ khỏi danh sách. | Kiểm tra **spring.cloud.stream.input-bindings** và **spring.cloud.stream.output-bindings**. |
| Ứng dụng không tìm thấy binding khi gửi | Tên trong **StreamBridge.send** không khớp tên output binding đã tạo. | Đối chiếu chính xác tên khai báo và tên truyền vào send. |
| Channel input không xử lý thông điệp | Chưa có IntegrationFlow hoặc subscriber lắng nghe channel. | Nối channel với endpoint xử lý và kiểm thử thông điệp đầu vào. |
| Framework không tìm thấy destination | Cấu hình destination sai hoặc broker không cho phép provision. | Kiểm tra tên destination, quyền tạo tài nguyên và log binder. |
| Cấu hình không áp dụng cho output | Dùng hậu tố **-out-0** cho binding tường minh hoặc cấu hình nhầm tên channel. | Dùng trực tiếp tên output binding trong **spring.cloud.stream.bindings**. |
| Input không giữ trạng thái tiêu thụ mong muốn | Thiếu group hoặc dùng group không ổn định. | Đặt group rõ ràng và kiểm tra ngữ nghĩa của broker. |
| Gửi thành công ở cấp channel nhưng consumer không nhận | Nhầm kết quả **StreamBridge.send** với xác nhận xử lý đầu cuối, hoặc broker/binding chưa được cấu hình đúng. | Kiểm tra publisher confirm, destination, quyền, consumer group và log broker. |
| Nhiều binding kết nối nhầm broker | Không chỉ định binder hoặc dùng sai tên binder. | Xác nhận cấu hình multi-binder và thuộc tính **binder** của từng binding. |

Khi điều tra, hãy xác minh theo thứ tự: danh sách tên binding, tên binding đã được tạo, thuộc tính destination/group, binder được chọn, channel hoặc StreamBridge đang dùng, rồi mới kiểm tra trạng thái broker và logic nghiệp vụ. Cách này giúp tách lỗi khai báo binding khỏi lỗi xử lý thông điệp.

## 11. Checklist trước khi triển khai

- [ ] Mỗi input/output binding tường minh có tên duy nhất và đúng hướng.
- [ ] Nhiều tên binding được phân tách bằng dấu chấm phẩy.
- [ ] Tên binding tường minh được dùng trực tiếp, không tự thêm hậu tố function.
- [ ] Mỗi binding có destination rõ ràng.
- [ ] Input binding có group ổn định khi cần trạng thái tiêu thụ bền vững.
- [ ] Input channel được nối với IntegrationFlow hoặc subscriber thực sự.
- [ ] Output binding được gọi bằng đúng tên qua StreamBridge.
- [ ] Binder được chọn đúng nếu ứng dụng sử dụng nhiều broker.
- [ ] Content type, serializer và các thuộc tính producer/consumer phù hợp với broker.
- [ ] Integration test xác nhận tài nguyên broker, gửi, nhận và xử lý thông điệp.
- [ ] Giám sát lỗi kết nối, lỗi provision và kết quả gửi thông điệp đã được cấu hình.

Binding tường minh giúp Spring Cloud Stream kết nối broker với những thành phần không được mô tả bằng function bean. **input-bindings** tạo đầu vào cho channel của ứng dụng, còn **output-bindings** tạo sẵn đầu ra để StreamBridge hoặc thành phần phát thông điệp sử dụng. Khi giữ tên binding nhất quán, cấu hình đúng destination và kiểm thử cả channel lẫn broker, ứng dụng có thể tích hợp các framework và nguồn sự kiện bên ngoài một cách rõ ràng.

## Tài liệu tham khảo

- [Spring Cloud Stream — Explicit binding creation](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/explicit-binding-creation.html)
- [Spring Cloud Stream — Producing and consuming messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Binding properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
