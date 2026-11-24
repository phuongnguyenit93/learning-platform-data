# Hàng đợi bền vững, nhóm ẩn danh và auto-delete

Trong Spring Cloud Stream RabbitMQ binder, mỗi consumer binding được kết nối với một queue trên RabbitMQ. Queue đó có thể tồn tại lâu dài để giữ backlog khi ứng dụng tạm ngừng, hoặc chỉ tồn tại trong thời gian một consumer đang hoạt động. Lựa chọn này phụ thuộc vào việc binding có khai báo **group** hay không, thuộc tính **durableSubscription** và các chính sách vòng đời queue của RabbitMQ.

Hiểu ba khái niệm **durable**, **anonymous group** và **auto-delete** giúp tránh hai lỗi triển khai phổ biến: dùng queue tạm thời cho sự kiện nghiệp vụ cần được giữ qua thời gian ứng dụng ngừng hoạt động, hoặc tạo queue bền vững cho một consumer tạm thời khiến broker tích lũy tài nguyên không cần thiết.

## 1. RabbitMQ binder ánh xạ destination thành exchange và queue

Trong mô hình mặc định, RabbitMQ binder provision một topic exchange cho destination. Khi có consumer binding, binder tạo queue rồi bind queue vào exchange. Routing key mặc định của binding không phân vùng là **#**, nên queue nhận mọi message được định tuyến tới exchange đó.

Tên queue phụ thuộc vào cấu hình group:

- Có **group**: queue có tên ổn định theo dạng **prefix + destination + group**.
- Không có **group**: binder tạo một anonymous queue với tên ngẫu nhiên, mặc định bắt đầu bằng **anonymous.**; queue này được cấu hình auto-delete.

~~~mermaid
flowchart TD
    P[Producer binding] --> X[(Topic exchange: orders)]
    X --> Q1[Queue: orders.billing]
    X --> Q2[Queue: orders.analytics]
    X --> QA[Anonymous queue: anonymous.UUID]
    Q1 --> C1[Billing consumer instances]
    Q2 --> C2[Analytics consumer instances]
    QA --> CA[Temporary consumer]
~~~

Trong sơ đồ, **billing** và **analytics** là hai group ổn định nên mỗi group có queue riêng. Các instance cùng group chia sẻ queue tương ứng. Anonymous consumer có queue riêng, không tham gia queue dùng chung của một group đã đặt tên.

Ví dụ cấu hình một consumer có group:

~~~yaml
spring:
  cloud:
    function:
      definition: billingConsumer
    stream:
      bindings:
        billingConsumer-in-0:
          destination: orders
          group: billing
          content-type: application/json
~~~

Với prefix mặc định rỗng, queue được provision theo tên **orders.billing**. Một ứng dụng khác có group **analytics** sẽ có queue **orders.analytics**, cũng được bind vào exchange **orders**.

## 2. Durable queue có ý nghĩa gì?

Queue có thuộc tính **durable** sẽ được RabbitMQ khôi phục sau khi broker khởi động lại. Metadata của queue như tên, binding và cấu hình được lưu bền vững. Queue không durable là transient; nó bị xóa khi node khởi động lại.

Trong RabbitMQ binder, consumer group có tên được cấu hình **durableSubscription**:

| Thuộc tính | Ý nghĩa | Mặc định |
|---|---|---|
| **durableSubscription** | Queue/subscription của consumer group có bền vững qua lần restart broker hay không. | true |
| **exchangeDurable** | Exchange do binder khai báo có bền vững qua lần restart broker hay không. | true |
| **exchangeAutoDelete** | Exchange có bị xóa sau khi queue cuối cùng được gỡ bỏ hay không. | true |

**durableSubscription** chỉ có tác dụng khi input binding có **group**. Nếu không khai báo group, binder dùng anonymous auto-delete queue; đặt durableSubscription true không biến anonymous queue thành queue bền vững.

Ví dụ đặt tường minh queue bền vững:

~~~yaml
spring:
  cloud:
    function:
      definition: billingConsumer
    stream:
      bindings:
        billingConsumer-in-0:
          destination: orders
          group: billing
      rabbit:
        bindings:
          billingConsumer-in-0:
            consumer:
              durable-subscription: true
              exchange-durable: true
~~~

Đây cũng là hành vi mặc định của một group queue nếu không ghi đè durable-subscription. Khai báo tường minh hữu ích khi muốn làm rõ yêu cầu vận hành trong cấu hình.

### Durable queue không đồng nghĩa mọi message đều được giữ

Độ bền của queue và độ bền của message là hai thuộc tính riêng:

- Durable queue giữ metadata và được khôi phục sau restart.
- Persistent message được đánh dấu để RabbitMQ lưu bền vững và khôi phục cùng durable queue.
- Message transient có thể bị loại khi broker khởi động lại, ngay cả khi queue là durable.

RabbitMQ binder đặt deliveryMode mặc định của producer là **PERSISTENT**. Có thể giữ mặc định này hoặc cấu hình tường minh:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
      rabbit:
        bindings:
          orderPublisher-out-0:
            producer:
              delivery-mode: PERSISTENT
~~~

Vì vậy, để queue nhận và giữ backlog qua restart, cần ít nhất queue durable và message persistent. Với yêu cầu an toàn dữ liệu cao, còn phải xem xét publisher confirms, acknowledgement của consumer, loại queue và replication. Chỉ hai thuộc tính durable/persistent không tự tạo ra bảo đảm end-to-end tuyệt đối.

## 3. durableSubscription và group trong Spring Cloud Stream

**group** là thuộc tính chung của Spring Cloud Stream, còn **durableSubscription** là thuộc tính mở rộng riêng của RabbitMQ binder. Hai thuộc tính phối hợp như sau:

| Cấu hình input binding | Kết quả queue |
|---|---|
| Có group, durable-subscription true | Queue tên ổn định, durable. |
| Có group, durable-subscription false | Queue tên ổn định, non-durable/transient. |
| Không có group | Anonymous queue có tên ngẫu nhiên và auto-delete; durableSubscription không áp dụng. |

Ví dụ hai consumer instance cùng group:

~~~yaml
spring:
  cloud:
    function:
      definition: billingConsumer
    stream:
      bindings:
        billingConsumer-in-0:
          destination: orders
          group: billing
      rabbit:
        bindings:
          billingConsumer-in-0:
            consumer:
              durable-subscription: true
              max-concurrency: 2
~~~

Các instance chạy cùng ứng dụng và cùng group **billing** tiêu thụ từ queue **orders.billing**. RabbitMQ phân phối message giữa các consumer đang hoạt động trên queue đó. Khi một instance dừng, các message chưa ACK có thể được giao lại theo cơ chế broker; instance còn lại tiếp tục nhận message.

Nếu hai ứng dụng cần mỗi ứng dụng nhận một bản sao của toàn bộ sự kiện, chúng phải dùng hai group khác nhau, ví dụ **billing** và **analytics**. Nếu chúng dùng cùng group, chúng chia tải trên một queue thay vì mỗi ứng dụng nhận một bản sao riêng.

### Vì sao không nên đổi group tùy tiện?

Tên group góp phần xác định tên queue. Đổi **group: billing** thành **group: billing-v2** có thể khiến binder tạo queue mới **orders.billing-v2**. Queue cũ có thể vẫn còn và chứa backlog chưa xử lý. Việc đổi group vì thế là thay đổi topology và tiến độ tiêu thụ, không chỉ là đổi tên trong cấu hình.

Trước khi đổi group, cần quyết định xử lý queue cũ: tiếp tục tiêu thụ, chuyển backlog, phát lại, lưu trữ hoặc xóa sau khi xác nhận không còn dữ liệu cần thiết.

## 4. Nhóm ẩn danh khi không khai báo group

Khi input binding không có **group**, RabbitMQ binder tạo một queue anonymous có tên duy nhất. Theo mặc định, tên queue bắt đầu bằng **anonymous.** theo sau là biểu diễn Base64 của một UUID. Có thể đổi prefix bằng thuộc tính **anonymousGroupPrefix**.

Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: liveNotificationConsumer
    stream:
      bindings:
        liveNotificationConsumer-in-0:
          destination: notifications
      rabbit:
        bindings:
          liveNotificationConsumer-in-0:
            consumer:
              anonymous-group-prefix: "live."
~~~

Binding này không có group. Binder tạo một queue anonymous, ví dụ **live.UUID**, rồi bind queue vào exchange **notifications**. Prefix chỉ làm tên queue dễ nhận biết hơn; nó không tạo một group ổn định và không làm queue trở nên durable.

### Hành vi khi chạy nhiều instance

Giả sử có ba instance ứng dụng cùng khai báo consumer không có group. Mỗi instance tạo queue anonymous riêng:

~~~mermaid
flowchart TD
    X[(Exchange notifications)] --> Q1[Queue anonymous A]
    X --> Q2[Queue anonymous B]
    X --> Q3[Queue anonymous C]
    Q1 --> A[Instance A]
    Q2 --> B[Instance B]
    Q3 --> C[Instance C]
~~~

Mỗi queue được bind vào cùng exchange nên mỗi instance có thể nhận một bản sao của message. Đây là hành vi broadcast theo từng queue. Nó phù hợp khi mỗi instance cần một luồng tạm thời riêng, chẳng hạn các kết nối theo phiên hoặc consumer thử nghiệm.

Hành vi này khác với ba instance cùng group **notifications-service**: khi dùng group, cả ba instance chia sẻ một queue và phân phối message để chia tải. Không có group, mỗi instance có queue riêng và có thể nhận cùng một message; nếu xử lý nghiệp vụ ghi dữ liệu hoặc gửi thanh toán, điều này có thể tạo side effect lặp.

### Anonymous queue không phải nơi lưu backlog lâu dài

Anonymous queue được thiết kế cho consumer tạm thời. Khi ứng dụng dừng và consumer cuối cùng bị hủy, queue auto-delete sẽ bị xóa. Message đang nằm trong queue cũng không còn sau khi queue bị xóa.

Nếu consumer kết nối lại, binder tạo một queue anonymous mới với tên khác. Queue mới không tự khôi phục backlog của queue cũ và không có cursor/offset chung để tiếp tục từ lần chạy trước.

Vì vậy:

- Dùng anonymous group cho dữ liệu tạm thời, chỉ cần nhận trong thời gian consumer đang hoạt động.
- Dùng group ổn định cho sự kiện cần được giữ khi consumer tạm ngừng.
- Không dùng anonymous queue cho đơn hàng, thanh toán, hóa đơn hoặc sự kiện kiểm toán cần được xử lý sau restart.

## 5. Auto-delete queue hoạt động thế nào?

Thuộc tính **auto-delete** của RabbitMQ quy định queue được xóa khi consumer cuối cùng bị hủy hoặc biến mất, với điều kiện queue đã từng có consumer. Việc consumer biến mất có thể do ứng dụng hủy subscription, channel/connection đóng hoặc kết nối TCP bị mất.

Một số điểm quan trọng:

1. Auto-delete không có nghĩa queue bị xóa ngay sau khi xử lý hết message.
2. Queue chỉ được auto-delete khi consumer cuối cùng rời đi.
3. Queue chưa từng có consumer sẽ không tự bị xóa chỉ nhờ auto-delete.
4. Auto-delete khác với exclusive: exclusive queue bị xóa khi connection khai báo queue đóng; auto-delete queue chờ consumer cuối cùng rời queue.
5. Auto-delete khác với TTL: TTL là cơ chế hết hạn theo thời gian.

Với anonymous consumer của Rabbit binder, binder tạo queue auto-delete. Khi ứng dụng dừng bình thường, consumer được hủy và queue được xóa. Nếu ứng dụng bị crash, RabbitMQ phát hiện connection/channel đã đóng hoặc mất và xử lý queue theo quy tắc auto-delete.

### Auto-delete queue và exclusive queue

| Thuộc tính | Auto-delete | Exclusive |
|---|---|---|
| Điều kiện xóa | Consumer cuối cùng bị hủy hoặc biến mất, sau khi queue từng có consumer. | Connection khai báo queue đóng hoặc mất. |
| Ai có thể sử dụng queue | Có thể có nhiều consumer, tùy queue và quyền truy cập. | Chỉ connection khai báo queue được sử dụng queue. |
| Phạm vi sống | Gắn với vòng đời consumer cuối cùng. | Gắn trực tiếp với connection khai báo. |
| Trường hợp thường gặp | Queue tạm cho consumer đang hoạt động. | Queue tạm chỉ dành cho một client connection. |

Không suy ra queue anonymous của binder là exclusive chỉ từ việc nó auto-delete. Đây là hai thuộc tính khác nhau trong RabbitMQ. Khi cần một queue chỉ dành cho một connection, phải xác nhận thuộc tính exclusive của topology thực tế.

## 6. Auto-delete queue khác TTL và exchangeAutoDelete

Rabbit binder có nhiều thuộc tính vòng đời dễ nhầm lẫn:

| Thuộc tính | Tác động lên | Ý nghĩa |
|---|---|---|
| Queue auto-delete | Queue anonymous | Xóa queue khi consumer cuối cùng rời đi sau khi queue từng có consumer. |
| **expires** | Queue có group được binder khai báo | Xóa queue nếu queue không được sử dụng trong khoảng thời gian cấu hình. |
| **ttl** | Message trong queue | Thời gian sống mặc định của message; message hết hạn có thể bị loại hoặc dead-letter theo cấu hình broker. |
| **exchangeAutoDelete** | Exchange | Xóa exchange sau khi queue cuối cùng được gỡ bỏ. |
| **exchangeDurable** | Exchange | Giữ exchange qua broker restart. |
| **durableSubscription** | Queue của group | Giữ queue qua broker restart khi bật. |

Ví dụ queue của group có thể được xóa nếu không còn được sử dụng trong một khoảng thời gian:

~~~yaml
spring:
  cloud:
    function:
      definition: archiveConsumer
    stream:
      bindings:
        archiveConsumer-in-0:
          destination: archive-events
          group: temporary-archive-reader
      rabbit:
        bindings:
          archiveConsumer-in-0:
            consumer:
              durable-subscription: true
              expires: 86400000
~~~

**expires** ở ví dụ là 24 giờ tính bằng mili giây. Đây là thời gian queue không được sử dụng trước khi broker xóa queue; nó không phải thời gian hết hạn của từng message. Nếu queue đang được consumer sử dụng, không nên xem expires như bộ đếm thời gian xóa cố định kể từ lúc khởi tạo.

Thuộc tính **ttl** có ý nghĩa khác:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        notificationsConsumer-in-0:
          destination: notifications
          group: notification-worker
      rabbit:
        bindings:
          notificationsConsumer-in-0:
            consumer:
              ttl: 3600000
~~~

Ở đây message trong queue có TTL một giờ theo cấu hình queue. Một queue durable vẫn có thể chứa message hết hạn; durability không ngăn TTL hoặc queue length policy loại bỏ message.

**exchangeAutoDelete** chỉ điều khiển exchange, không xóa queue consumer. Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
      rabbit:
        bindings:
          orderPublisher-out-0:
            producer:
              exchange-durable: true
              exchange-auto-delete: true
~~~

Khi queue cuối cùng bị xóa, exchange có thể bị xóa theo cấu hình exchange-auto-delete. Nếu exchange được dùng chung bởi nhiều queue hoặc ứng dụng khác, hãy đánh giá vòng đời này trước khi bật.

## 7. Chọn mô hình queue theo yêu cầu nghiệp vụ

Không phải mọi consumer đều cần queue durable. Hãy bắt đầu từ câu hỏi: message có cần được giữ trong lúc consumer không hoạt động hay không?

| Nhu cầu | Cấu hình nên chọn | Lý do |
|---|---|---|
| Xử lý đơn hàng sau khi ứng dụng restart | Group ổn định và durable-subscription true | Queue có tên ổn định và tồn tại qua restart broker. |
| Mỗi ứng dụng nghiệp vụ nhận một bản sao sự kiện | Mỗi ứng dụng dùng group riêng | Mỗi group có queue riêng được bind vào exchange. |
| Chia tải giữa nhiều instance của cùng service | Các instance dùng cùng group | Cùng tiêu thụ một queue và phân phối message. |
| Consumer tạm thời theo phiên hoặc kết nối | Không khai báo group | Mỗi consumer có anonymous auto-delete queue. |
| Queue group không cần giữ qua broker restart | Group ổn định và durable-subscription false nếu broker/version cho phép | Queue transient, nhưng message không được bảo vệ qua restart. |
| Dọn queue group không còn được sử dụng | Group ổn định và expires | Queue hết hạn sau khoảng thời gian không hoạt động. |

Với sự kiện nghiệp vụ quan trọng, lựa chọn thường là group ổn định, durable queue và persistent message. Với dữ liệu tạm như trạng thái hiện diện, thông báo trực tiếp tới client đang online hoặc feed thử nghiệm, anonymous auto-delete queue có thể phù hợp.

## 8. Cấu hình durable queue cho một service nghiệp vụ

Ví dụ service xử lý đơn hàng cần giữ backlog khi ứng dụng ngừng hoạt động:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderConsumerConfiguration {

    @Bean
    public Consumer<OrderCreated> orderConsumer(
            OrderService orderService) {
        return orderService::handle;
    }
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: orderConsumer
    stream:
      bindings:
        orderConsumer-in-0:
          destination: orders
          group: order-processing
          content-type: application/json
      rabbit:
        bindings:
          orderConsumer-in-0:
            consumer:
              durable-subscription: true
              exchange-durable: true
              acknowledge-mode: AUTO
  rabbitmq:
    host: rabbitmq.internal
    port: 5672
~~~

Producer gửi message persistent:

~~~yaml
spring:
  cloud:
    function:
      definition: orderPublisher
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
          content-type: application/json
      rabbit:
        bindings:
          orderPublisher-out-0:
            producer:
              delivery-mode: PERSISTENT
              exchange-durable: true
~~~

Trong cấu hình này:

1. Queue **orders.order-processing** có tên ổn định.
2. durable-subscription true giữ queue qua broker restart.
3. Producer phát message với delivery mode persistent.
4. Consumer dùng group ổn định để tiếp tục nhận backlog khi được khởi động lại.
5. acknowledge-mode AUTO cho container quản lý ACK theo kết quả xử lý message.

Durable queue không tự động tạo một queue dự phòng hoặc bản sao message cho mỗi instance. Nếu cần khả năng chịu lỗi ở tầng queue, hãy cân nhắc quorum queue và cấu hình cluster/replication của RabbitMQ.

## 9. Cấu hình anonymous consumer cho dữ liệu tạm thời

Ví dụ một service gửi thông báo trạng thái tới các phiên đang hoạt động:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class LiveNotificationConfiguration {

    @Bean
    public Consumer<NotificationEvent> liveNotificationConsumer(
            NotificationService service) {
        return service::deliverToConnectedClient;
    }
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: liveNotificationConsumer
    stream:
      bindings:
        liveNotificationConsumer-in-0:
          destination: live-notifications
      rabbit:
        bindings:
          liveNotificationConsumer-in-0:
            consumer:
              anonymous-group-prefix: "session."
~~~

Không khai báo **group**. Binder tạo queue tên **session.<unique-id>** và bind queue vào exchange **live-notifications**. Khi service dừng, queue auto-delete được gỡ bỏ sau khi consumer cuối cùng rời đi. Khi service khởi động lại, queue mới được tạo.

Nếu có hai instance service, mỗi instance có queue anonymous riêng và có thể nhận cùng notification. Nếu mục tiêu là chia notification cho một instance trong nhóm xử lý, hãy đặt group ổn định thay vì bỏ group.

## 10. Khi cần dùng queue đã được tạo sẵn

Trong môi trường production, đội vận hành có thể tạo exchange và queue bằng RabbitMQ definitions, Terraform, Ansible hoặc công cụ quản trị. Khi đó, binder có thể được cấu hình để không tự provision tài nguyên:

~~~yaml
spring:
  cloud:
    function:
      definition: legacyOrderConsumer
    stream:
      bindings:
        legacyOrderConsumer-in-0:
          destination: orders-exchange
          group: orders-legacy
      rabbit:
        bindings:
          legacyOrderConsumer-in-0:
            consumer:
              bind-queue: false
              declare-exchange: false
              queue-name-group-only: true
~~~

Với **queue-name-group-only: true**, binder dùng tên group làm tên queue, trong ví dụ là **orders-legacy**. **bind-queue: false** và **declare-exchange: false** yêu cầu hạ tầng đã có queue/exchange và binding cần thiết.

Trước khi triển khai, xác nhận:

- Queue tồn tại trong đúng virtual host.
- Queue có durability và queue type đúng yêu cầu.
- Queue đã được bind vào exchange với routing key phù hợp.
- User của ứng dụng có quyền read/configure cần thiết.
- Tên queue và exchange khớp cấu hình.

Nếu queue tồn tại nhưng thuộc tính khai báo khác với thuộc tính binder yêu cầu, RabbitMQ có thể trả **PRECONDITION_FAILED** khi ứng dụng cố khai báo lại. Đổi durable, auto-delete, exclusive hoặc queue type không phải lúc nào cũng là cập nhật tại chỗ; có thể cần quy trình tạo queue mới, chuyển backlog và chuyển binding.

## 11. Thay đổi durability và dọn queue an toàn

Queue là tài nguyên có trạng thái. Thay đổi group hoặc durability có thể làm thay đổi nơi message đang được lưu.

### Chuyển từ anonymous sang named group

1. Xác định queue anonymous hiện tại và message còn trong queue.
2. Tạo group mới với tên ổn định.
3. Xác nhận queue durable được provision.
4. Cấu hình producer và consumer để message được định tuyến tới queue mới theo kế hoạch.
5. Kiểm thử nhận message và xử lý backlog.
6. Dừng consumer anonymous và xác nhận queue cũ được auto-delete.

Không kỳ vọng backlog trong anonymous queue tự chuyển sang queue group mới. Nếu cần giữ dữ liệu đang có, phải có kế hoạch drain hoặc republish trước khi queue bị xóa.

### Chuyển từ non-durable sang durable

1. Tạo một queue mới với tên hoặc group mới và durable-subscription true.
2. Đảm bảo producer gửi message persistent.
3. Chuyển routing/binding theo kế hoạch để producer ghi tới queue mới.
4. Chờ hoặc xử lý hết backlog queue cũ.
5. Xác minh consumer mới xử lý ổn định.
6. Xóa queue cũ sau khi xác nhận không còn dữ liệu cần giữ.

RabbitMQ kiểm tra tính tương đương của thuộc tính khi client khai báo lại queue cùng tên. Nếu khai báo không khớp, broker có thể đóng channel với lỗi 406 **PRECONDITION_FAILED**. Không đổi trực tiếp một queue đang chạy mà chưa có phương án di chuyển dữ liệu.

### Dọn queue cũ

Queue group bền vững có thể còn tồn tại sau khi service bị gỡ bỏ. Hãy dùng expires, RabbitMQ policy hoặc quy trình quản trị để dọn queue không còn sử dụng. Trước khi xóa, kiểm tra message ready, unacknowledged, consumer đang hoạt động, DLQ và yêu cầu kiểm toán.

## 12. Lưu ý phiên bản RabbitMQ và queue type

RabbitMQ 4.3.0 trở lên không cho phép mặc định khai báo transient non-durable, non-exclusive classic queue; tính năng này đã bị deprecated và bị tắt theo mặc định. Nếu ứng dụng đặt durable-subscription false cho named group và binder tạo non-durable, non-exclusive classic queue, việc khai báo có thể bị từ chối trên broker mới tùy queue type và cấu hình.

Với RabbitMQ hiện đại:

- Ưu tiên durable queue cho luồng nghiệp vụ cần tồn tại qua restart.
- Dùng non-durable exclusive queue cho dữ liệu tạm thời gắn với một connection.
- Nếu cần dọn queue durable không hoạt động, cân nhắc queue TTL (expires) thay vì tạo transient non-exclusive queue.
- Quorum queue là queue durable và replicated; không dùng exclusive hoặc transient queue cho quorum queue.

Rabbit binder hỗ trợ cấu hình quorum queue cho group:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderConsumer-in-0:
          destination: orders
          group: order-processing
      rabbit:
        bindings:
          orderConsumer-in-0:
            consumer:
              durable-subscription: true
              quorum:
                enabled: true
                initial-group-size: 3
~~~

Ví dụ minh họa lựa chọn quorum queue; kích thước nhóm ban đầu phải phù hợp số node và chính sách triển khai RabbitMQ. Quorum queue có chi phí replication và yêu cầu vận hành khác classic queue. Không bật chỉ vì muốn queue durable; hãy chọn theo yêu cầu chịu lỗi và hạ tầng thực tế.

## 13. Kiểm thử durability và auto-delete

Unit test function không thể chứng minh queue được RabbitMQ khai báo durable hoặc auto-delete. Cần integration test với RabbitMQ thật hoặc container thử nghiệm, sau đó kiểm tra thuộc tính queue trên broker.

### Kịch bản kiểm thử named group durable

1. Khởi động RabbitMQ.
2. Khởi động consumer có group billing và durable-subscription true.
3. Xác nhận queue orders.billing tồn tại và durable.
4. Tắt consumer nhưng giữ broker hoạt động.
5. Gửi message persistent vào exchange orders.
6. Xác nhận queue vẫn tồn tại và message được giữ trong backlog.
7. Restart broker trong môi trường test.
8. Xác nhận queue và message persistent được khôi phục.
9. Khởi động consumer lại và xác nhận backlog được xử lý.

### Kịch bản kiểm thử anonymous auto-delete

1. Khởi động consumer không có group.
2. Xác nhận queue có prefix anonymous. hoặc prefix tùy chỉnh.
3. Gửi một message khi consumer đang hoạt động và xác nhận nhận được.
4. Dừng consumer hoặc đóng connection.
5. Xác nhận queue bị xóa sau khi consumer cuối cùng rời đi.
6. Khởi động lại ứng dụng và xác nhận một queue mới có tên khác được tạo.
7. Xác nhận message được gửi trước khi queue mới tồn tại không tự xuất hiện trong queue mới.

### Ma trận kiểm thử

| Tình huống | Cấu hình | Kết quả cần xác nhận |
|---|---|---|
| Group durable | group có tên, durable-subscription true | Queue có tên ổn định và durable. |
| Group transient | group có tên, durable-subscription false | Queue không durable; kiểm tra tương thích phiên bản RabbitMQ. |
| Anonymous consumer | Không khai báo group | Queue có tên ngẫu nhiên và auto-delete. |
| Hai instance cùng group | Cùng destination và group | Cùng tiêu thụ queue, message được chia tải. |
| Hai instance anonymous | Cùng destination, không group | Mỗi instance có queue riêng và nhận bản sao message. |
| Consumer dừng | Dừng instance cuối của anonymous queue | Queue auto-delete bị xóa sau khi consumer rời đi. |
| Queue chưa có consumer | Provision queue nhưng chưa có consumer | Không giả định auto-delete tự xóa queue; kiểm tra TTL/expires nếu cần. |
| Broker restart | Durable queue và persistent message | Queue cùng message được khôi phục theo điều kiện broker. |
| Durable queue, transient message | Queue durable, producer delivery mode non-persistent | Queue tồn tại nhưng message transient có thể mất sau restart. |
| Queue expiration | Group queue có expires | Queue không hoạt động bị xóa sau thời gian cấu hình. |
| Message TTL | Consumer queue có ttl | Message hết hạn theo TTL, không xóa queue. |
| Queue declaration mismatch | Thay durability/queue type trên cùng tên queue | Phát hiện lỗi PRECONDITION_FAILED và xử lý theo kế hoạch migration. |

### Quan sát queue trên RabbitMQ

RabbitMQ Management UI hiển thị queue name, durability, auto-delete, consumers, message ready và unacknowledged. Có thể dùng CLI để kiểm tra các thuộc tính cơ bản:

~~~bash
rabbitmqctl list_queues name durable auto_delete consumers messages_ready messages_unacknowledged
~~~

Khi kiểm thử anonymous queue, ghi lại tên queue trước khi dừng ứng dụng rồi kiểm tra queue đó đã biến mất. Khi kiểm thử durable queue, xác nhận cùng tên queue vẫn còn sau khi consumer dừng và sau khi broker restart.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Message biến mất khi ứng dụng restart | Consumer không có group nên dùng anonymous auto-delete queue. | Đặt group ổn định nếu cần giữ backlog. |
| Queue còn nhưng message mất sau broker restart | Queue durable nhưng message được publish transient. | Dùng delivery mode persistent và kiểm tra publisher confirms. |
| Mỗi instance xử lý cùng một message | Không khai báo group, mỗi instance có anonymous queue riêng. | Dùng cùng group nếu muốn chia tải. |
| Queue anonymous cũ không biến mất | Consumer vẫn còn hoạt động hoặc queue chưa từng có consumer. | Kiểm tra connection/consumer và dùng TTL/expires cho tài nguyên phù hợp. |
| Queue durable không được tạo | durable-subscription bị đặt false hoặc binder không có group. | Kiểm tra group và durableSubscription. |
| Broker báo PRECONDITION_FAILED | Queue cùng tên đã tồn tại với thuộc tính khác. | Migration queue có kế hoạch; không khai báo lại với thuộc tính xung đột. |
| Queue cũ tích lũy sau khi service bị xóa | Group queue durable vẫn tồn tại. | Dùng expires/policy và quy trình dọn tài nguyên. |
| Đổi anonymousGroupPrefix nhưng queue vẫn có tên cũ | Prefix mới chỉ áp dụng cho queue được tạo sau khi binding khởi tạo lại. | Kiểm tra queue hiện có và khởi tạo lại binding theo kế hoạch. |
| Nhầm exchangeAutoDelete với queue auto-delete | Hai thuộc tính áp dụng lên hai loại tài nguyên khác nhau. | Kiểm tra consumer properties và producer/exchange properties riêng. |
| Bật durableSubscription nhưng không có backlog khi consumer ngừng | Producer chưa publish tới queue đó, queue được tạo sau thời điểm publish hoặc message bị TTL/overflow loại. | Kiểm tra queue provisioning, requiredGroups, routing key, TTL và giới hạn queue. |

Khi điều tra, xác định queue thực tế trước: tên queue, group, durable, auto-delete, consumer count và message count. Sau đó đối chiếu cấu hình đã phân giải của binding, không chỉ nhìn YAML. Cuối cùng kiểm tra producer delivery mode, exchange binding, routing key, TTL, queue expiration và broker version.

## 15. Checklist trước khi triển khai

- [ ] Mỗi consumer đã quyết định rõ có cần group ổn định hay anonymous queue.
- [ ] Luồng nghiệp vụ quan trọng dùng group ổn định.
- [ ] durable-subscription được đặt đúng và chỉ có tác dụng khi group được khai báo.
- [ ] Producer gửi persistent message nếu cần khôi phục message sau broker restart.
- [ ] Exchange durability được đánh giá riêng với queue durability.
- [ ] Anonymous queue chỉ dùng cho dữ liệu tạm thời và chấp nhận mất backlog khi queue bị xóa.
- [ ] Đã hiểu auto-delete khác exclusive, expires và ttl.
- [ ] exchange-auto-delete không bị nhầm với queue auto-delete.
- [ ] Đã kiểm tra tên queue, prefix và group trên RabbitMQ Management UI.
- [ ] Queue cũ có quy trình drain, migrate hoặc cleanup trước khi xóa.
- [ ] Queue declaration không xung đột với tài nguyên đã được provision sẵn.
- [ ] Đã kiểm thử broker restart, consumer restart và nhiều instance.
- [ ] Đã xem xét RabbitMQ 4.3+ nếu dùng non-durable non-exclusive classic queue.

Trong RabbitMQ binder, một input binding có group thường dùng queue tên ổn định và durableSubscription mặc định là true; queue này phù hợp với luồng nghiệp vụ cần giữ backlog. Khi không khai báo group, binder tạo anonymous auto-delete queue có tên ngẫu nhiên; queue phù hợp với consumer tạm thời và có thể bị xóa khi consumer cuối cùng rời đi. Durability của queue phải đi cùng persistent message nếu cần phục hồi dữ liệu sau broker restart. Phân biệt đúng queue auto-delete, exclusive, queue expiration, message TTL và exchange auto-delete giúp lựa chọn vòng đời tài nguyên phù hợp và tránh mất backlog ngoài dự kiến.

## Tài liệu tham khảo

- [Spring Cloud Stream — RabbitMQ Consumer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html)
- [Spring Cloud Stream — Using Existing Queues and Exchanges](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/existing-destinations.html)
- [Spring Cloud Stream — RabbitMQ Producer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/prod-props.html)
- [RabbitMQ — Queues, Durability and Temporary Queues](https://www.rabbitmq.com/docs/queues)
- [RabbitMQ — Message Persistence](https://www.rabbitmq.com/docs/publishers)
