# Routing key

## Routing key có vai trò gì?

Khi một application event được externalize ra broker, ứng dụng cần xác định hai thông tin: message được gửi tới destination nào và message mang khóa định tuyến nào trong destination đó. Spring Modulith gọi thông tin thứ hai là *routing key*.

Routing key cho phép broker hoặc message client nhóm, phân vùng hay định tuyến các message theo một thuộc tính của event. Ví dụ, mọi event liên quan đến cùng một đơn hàng có thể mang key là orderId. Với Kafka, key được dùng làm message key để chọn partition. Với AMQP như RabbitMQ, key được dùng làm routing key để exchange chuyển message tới queue có binding phù hợp.

Trong Spring Modulith, target và key có thể được khai báo cùng trong giá trị của annotation @Externalized theo dạng:

~~~text
<target>::<key>
~~~

Phần trước :: là routing target; phần sau là routing key. Key có thể là một giá trị cố định hoặc biểu thức Spring Expression Language (SpEL) được đánh giá trên instance event.

Ví dụ:

~~~java
@Externalized("commerce.orders.v1::#{#this.orderId()}")
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}
~~~

Trong ví dụ này:

- commerce.orders.v1 là target logic được ánh xạ sang destination của broker.
- #{#this.orderId()} lấy orderId từ event để tạo routing key.
- #this đại diện cho instance event đang được externalize.
- Các event cùng orderId sẽ có cùng key, giúp broker áp dụng cùng quy tắc phân vùng hoặc định tuyến cho chúng.

Nếu chỉ khai báo @Externalized("commerce.orders.v1"), Spring Modulith không chỉ định routing key riêng; broker integration sẽ dùng hành vi mặc định của nó.

## Phân biệt target, routing key và message payload

Ba phần này có nhiệm vụ riêng:

| Thành phần | Mục đích | Ví dụ |
|---|---|---|
| Target | Xác định destination logic | commerce.orders.v1 |
| Routing key | Phân vùng hoặc định tuyến message trong destination | 7f...a91 (order ID) |
| Payload | Nội dung sự kiện consumer cần xử lý | OrderConfirmed cùng dữ liệu đơn hàng |

Target thường ánh xạ sang Kafka topic hoặc AMQP exchange. Routing key không thay thế target và cũng không phải nội dung nghiệp vụ đầy đủ. Payload vẫn phải chứa dữ liệu mà consumer cần để xử lý.

Cần phân biệt thêm routing key với các khái niệm gần nhau:

- **Kafka message key** được dùng để xác định partition theo partitioner. Key giống nhau thường được gửi tới cùng partition, nhờ đó có thể duy trì thứ tự tương đối của các message cùng key trong partition đó.
- **AMQP routing key** được exchange dùng để so khớp với binding của queue. Kết quả định tuyến phụ thuộc loại exchange và binding.
- **Consumer group** là nhóm consumer phối hợp tiêu thụ message. Nó không phải routing key.
- **Event ID** nhận diện một lần phát event để trace hoặc chống xử lý trùng. Event ID có thể khác routing key: nhiều event ID khác nhau có thể cùng thuộc một order ID.

Không có một ý nghĩa vật lý giống nhau cho routing key trên mọi broker. Cần hiểu adapter đang dùng để biết key được diễn giải như thế nào.

## Routing key trong Kafka và AMQP

Spring Modulith hỗ trợ các broker thông qua artifact tích hợp riêng. Ý nghĩa của key phụ thuộc broker được chọn:

| Integration | Target | Routing key |
|---|---|---|
| Kafka | Topic | Kafka message key |
| AMQP / RabbitMQ | Exchange | AMQP routing key |
| JMS | Destination theo cấu hình JMS | Không hỗ trợ routing key trong integration này |
| Spring Messaging | MessageChannel theo tên target | Thông tin routing được chuyển tiếp qua message header để thành phần downstream xử lý |

Với Kafka, key thường được dùng để chọn partition. Các event có cùng key thường đi cùng partition, nhưng thứ tự chỉ được bảo đảm trong phạm vi partition và theo semantics của producer/broker. Key không tạo ra thứ tự toàn cục giữa mọi đơn hàng.

Với RabbitMQ, routing key được exchange so khớp với binding:

- Direct exchange so khớp chính xác routing key với binding key.
- Topic exchange so khớp theo các phần được phân tách bằng dấu chấm và các wildcard như * hoặc #.
- Fanout exchange phát message tới mọi queue được bind và không dựa vào routing key để chọn queue.

Do đó, một key có giá trị hợp lệ về mặt Java vẫn có thể không đưa message đến queue mong muốn nếu không có binding tương ứng.

## Chọn key theo aggregate để giữ thứ tự xử lý

Một lựa chọn phổ biến là dùng định danh aggregate làm key. Ví dụ, event OrderPlaced, OrderConfirmed và OrderCancelled của cùng đơn hàng đều dùng orderId.

~~~java
@Externalized("commerce.orders.v1::#{#this.orderId()}")
public record OrderPlaced(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}

@Externalized("commerce.orders.v1::#{#this.orderId()}")
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}

@Externalized("commerce.orders.v1::#{#this.orderId()}")
public record OrderCancelled(
    UUID eventId,
    UUID orderId,
    String reason,
    Instant occurredAt
) {}
~~~

Với Kafka, cách này giúp các event của cùng một đơn hàng được ánh xạ tới cùng partition theo partitioner đang cấu hình. Consumer có thể xử lý chuỗi sự kiện của một aggregate theo thứ tự mà partition cung cấp.

Với RabbitMQ, dùng order ID làm routing key chỉ có ý nghĩa định tuyến nếu exchange và queue binding được thiết kế để nhận key đó. Nếu tất cả order ID đều khác nhau, binding cần một chiến lược phù hợp; không thể giả định một queue sẽ nhận mọi key chỉ vì key đã được tạo.

Không nên dùng event ID làm key nếu mục tiêu là gom event theo aggregate. Event ID thường khác nhau cho mỗi lần phát, nên các event của cùng một aggregate có thể bị phân tán sang nhiều partition.

## Chọn key theo loại nghiệp vụ

Không phải lúc nào aggregate ID cũng là lựa chọn tốt nhất. Key cần phản ánh đơn vị mà hệ thống muốn giữ cùng luồng hoặc muốn định tuyến.

| Nhu cầu | Key có thể dùng | Lý do |
|---|---|---|
| Giữ event của cùng đơn hàng trên một partition | orderId | Gom các thay đổi của một aggregate |
| Gom thay đổi của cùng khách hàng | customerId | Consumer xử lý theo hồ sơ khách hàng |
| Định tuyến message theo vùng trong topic exchange | region.eventType | Binding có thể chọn theo vùng và loại sự kiện |
| Chia tải theo tenant | tenantId | Các event của cùng tenant có cùng key |
| Phân tích theo loại event | eventType | Consumer có thể nhận và xử lý theo nhóm event |

Hãy chọn key dựa trên cách consumer xử lý và yêu cầu thứ tự, không chỉ dựa trên field có sẵn trong event. Nếu consumer cần cập nhật một aggregate theo trình tự, aggregate ID thường phù hợp. Nếu cần phân luồng theo vùng, một key thể hiện vùng có thể hữu ích hơn.

## Khai báo routing key bằng SpEL

Cách đơn giản nhất là khai báo key trực tiếp trong annotation. Spring Modulith dùng event instance làm root object của biểu thức SpEL.

~~~java
@Externalized("commerce.orders.v1::#{#this.orderId()}")
public record OrderConfirmed(UUID orderId) {}
~~~

Có thể truy cập accessor của Java record như orderId(), hoặc method/getter được event cung cấp. Với event JavaBean, ví dụ:

~~~java
@Externalized("commerce.customers.v1::#{#this.getCustomerId()}")
public class CustomerAddressChanged {

    private final UUID customerId;

    public CustomerAddressChanged(UUID customerId) {
        this.customerId = customerId;
    }

    public UUID getCustomerId() {
        return customerId;
    }
}
~~~

Khi key cần logic phức tạp, không nên nhồi toàn bộ quy tắc vào annotation. Có thể ủy quyền cho một Spring bean:

~~~java
@Component
public class OrderRoutingKey {

    public String forEvent(OrderConfirmed event) {
        return event.region() + "." + event.orderId();
    }
}
~~~

~~~java
@Externalized("commerce.orders.v1::#{@orderRoutingKey.forEvent(#this)}")
public record OrderConfirmed(
    UUID orderId,
    String region
) {}
~~~

Bean tính key giúp quy tắc có thể được đặt tên, tái sử dụng và kiểm thử độc lập. Cần bảo đảm bean có tên đúng với tham chiếu trong SpEL và có thể được Spring quản lý khi externalization xử lý event.

Cả target và key đều có thể dùng SpEL khi cần định tuyến động. Tuy nhiên, chỉ nên tạo target động khi có lý do vận hành rõ ràng, vì target thường tương ứng với destination vật lý. Key động thường phù hợp hơn cho việc phân vùng hoặc định tuyến message bên trong một destination đã xác định.

## Cấu hình routing bằng Java

Khi muốn tập trung quy tắc định tuyến trong cấu hình thay vì annotation, Spring Modulith cung cấp EventExternalizationConfiguration. Có thể đăng ký bộ trích xuất key theo từng event type:

~~~java
@Configuration
class ExternalizationConfiguration {

    @Bean
    EventExternalizationConfiguration eventExternalizationConfiguration() {
        return EventExternalizationConfiguration.externalizing()
            .select(EventExternalizationConfiguration.annotatedAsExternalized())
            .routeKey(
                OrderConfirmed.class,
                event -> event.orderId().toString()
            )
            .build();
    }
}
~~~

routeKey đăng ký hàm lấy key từ event instance. Target vẫn được xác định bởi router đang cấu hình, chẳng hạn từ @Externalized. Nếu cần quyết định cả target lẫn key theo từng event, dùng API routing tổng quát của EventExternalizationConfiguration.Router (ví dụ route(...)) phù hợp với phiên bản Spring Modulith của ứng dụng.

Một số điểm cần cân nhắc:

- Chỉ cấu hình một nguồn quyết định key cho mỗi loại event để tránh quy tắc chồng chéo khó hiểu.
- Nếu có bước mapping event sang payload khác, hãy xác định rõ key được tính từ event gốc hay payload sau mapping. API mặc định có thể định tuyến dựa trên event gốc; routeMapped() thay đổi lựa chọn đó.
- Giữ quy tắc trích xuất key thuần, ổn định và dễ kiểm thử.
- Kiểm tra API cụ thể theo phiên bản Spring Modulith đang sử dụng.

## Tránh key gây lệch tải

Một key tốt vừa đáp ứng yêu cầu định tuyến vừa phân bố tải hợp lý. Key có cardinality quá thấp có thể khiến nhiều message dồn vào một partition hoặc một queue. Ví dụ, dùng một giá trị cố định orders cho mọi đơn hàng có thể khiến toàn bộ event đi vào cùng một partition Kafka.

Ngược lại, key có cardinality quá cao không nhất thiết là vấn đề với Kafka, nhưng có thể làm routing/binding trong RabbitMQ trở nên khó quản lý nếu mỗi giá trị cần một binding riêng.

Cần xem xét:

- **Cardinality:** Có bao nhiêu giá trị key khác nhau trong tải thực tế?
- **Skew:** Một số key có nhận nhiều message vượt trội so với phần còn lại không?
- **Ordering:** Có cần giữ thứ tự theo aggregate, tenant hay một nhóm nghiệp vụ không?
- **Throughput:** Một key nóng có giới hạn khả năng xử lý của một partition hoặc consumer không?
- **Topology:** Với AMQP, binding có thể xử lý tập key dự kiến mà không phải tạo tài nguyên cho từng đối tượng không?

Đừng chọn key chỉ để phân phối đều nếu điều đó phá vỡ thứ tự nghiệp vụ cần có. Cần cân bằng giữa thứ tự và khả năng mở rộng, đồng thời đo tải thực tế trước khi điều chỉnh partition hoặc binding.

## Bảo vệ dữ liệu khi tính key

Routing key có thể xuất hiện trong metadata broker, log, trace hoặc công cụ quản trị. Không đưa thông tin bí mật hay dữ liệu cá nhân nhạy cảm vào key. Ưu tiên ID nội bộ ổn định hoặc mã phân loại không nhạy cảm.

Nếu key được tính từ dữ liệu do người dùng hoặc hệ thống ngoài cung cấp, cần xác thực và giới hạn giá trị. Tránh đưa trực tiếp chuỗi tùy ý vào routing key, nhất là khi key ảnh hưởng đến topic, queue hoặc topology. Với AMQP topic exchange, ký tự phân tách và wildcard có thể làm thay đổi cách binding khớp. Với cấu hình động, giá trị bất ngờ có thể làm message đi tới queue không dự kiến.

Có thể chuẩn hóa giá trị trước khi dùng làm key, nhưng phải bảo đảm mọi producer cùng áp dụng một quy tắc và consumer hiểu cùng quy ước. Nếu hash ID, hãy dùng thuật toán ổn định và định dạng nhất quán; không dùng hash code phụ thuộc runtime.

## Kiểm thử routing key

Kiểm thử cần xác nhận giá trị key được tính đúng và broker sử dụng nó đúng mục đích.

| Trường hợp | Điều cần xác nhận |
|---|---|
| Event có orderId | Key được tạo từ đúng order ID |
| Hai event cùng aggregate | Cùng key |
| Hai aggregate khác nhau | Key khác nhau khi định danh khác nhau |
| Key rỗng hoặc null | Hành vi được xác định rõ và không âm thầm định tuyến sai |
| Key có ký tự đặc biệt | Không phá quy tắc binding hoặc cấu hình |
| Event không có routing key | Integration dùng đúng hành vi mặc định |
| Mapping payload | Key được tính từ event gốc hoặc mapped payload đúng như thiết kế |
| Kafka | Message key dẫn tới partition dự kiến theo partitioner |
| RabbitMQ | Routing key khớp binding và message tới đúng queue |

Có thể kiểm thử hàm trích xuất key bằng unit test. Integration test với broker hoặc môi trường test tương đương cần xác nhận message được gửi tới đúng destination và được định tuyến tới consumer dự kiến.

Đối với Kafka, không nên khẳng định hai key khác nhau luôn nằm ở hai partition khác nhau; partitioner có thể ánh xạ nhiều key vào cùng partition. Điều cần kiểm tra là cùng key được ánh xạ nhất quán theo cấu hình partitioner hiện tại. Với RabbitMQ, cần kiểm tra loại exchange, routing key và binding thực tế.

## Quan sát và xử lý lỗi định tuyến

Khi event không tới consumer mong đợi, điều tra từ publisher đến broker theo từng bước:

1. Xác nhận event được phát và được chọn để externalize.
2. Xác nhận target được giải quyết đúng.
3. Xác nhận routing key được tính từ đúng event instance.
4. Kiểm tra broker destination và quyền publish.
5. Kiểm tra partitioner hoặc exchange type.
6. Kiểm tra queue binding, consumer group và subscription.
7. Kiểm tra consumer có lỗi deserialize hoặc từ chối message không.

Log và metric nên có target, event type, event ID, routing key ở dạng an toàn, destination và kết quả publish. Nếu routing key có thể chứa dữ liệu nhạy cảm, hãy che hoặc băm giá trị khi quan sát.

Theo dõi phân bố message theo partition hoặc queue giúp phát hiện key nóng. Với Kafka, xem xét độ lệch giữa partition và lag của consumer. Với RabbitMQ, theo dõi message không được route, queue depth, consumer count và tình trạng binding. Event Publication Registry giúp theo dõi publication externalization chưa hoàn tất trong ứng dụng; nó không thay thế metric và công cụ quan sát của broker.

## Quy trình chọn routing key

Khi thêm một event cần externalize, thực hiện theo thứ tự:

1. Xác định destination logic của event.
2. Xác định consumer cần giữ thứ tự hoặc cần nhận cùng nhóm message.
3. Chọn định danh ổn định đại diện cho nhóm đó, thường là aggregate ID nếu cần ordering theo aggregate.
4. Khai báo key bằng target::key trong @Externalized, hoặc cấu hình qua EventExternalizationConfiguration.
5. Nếu dùng SpEL, kiểm tra accessor và biểu thức trên event thực tế.
6. Xác nhận adapter diễn giải key đúng với broker: Kafka message key hay AMQP routing key.
7. Kiểm thử partition/binding và trường hợp key thiếu hoặc không hợp lệ.
8. Theo dõi phân bố tải, thứ tự và tình trạng định tuyến sau triển khai.

Routing key là một phần của hợp đồng giao sự kiện. Khi chọn key theo đơn vị nghiệp vụ cần xử lý, giữ giá trị ổn định và kiểm tra semantics của broker, các consumer có thể nhận message theo luồng phù hợp mà không làm publisher phụ thuộc trực tiếp vào topology hạ tầng.

## Tài liệu tham khảo

- Spring Modulith Reference — Working with Application Events, phần Event Externalization: https://docs.spring.io/spring-modulith/reference/events.html
- Spring Modulith API — EventExternalizationConfiguration.Router: https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/EventExternalizationConfiguration.Router.html
