# Tên đích của event

## Tên đích giải quyết việc gì?

Khi một application event cần rời khỏi ứng dụng Spring Modulith để đến Kafka, RabbitMQ hoặc một hệ thống tích hợp khác, publisher cần chỉ ra event đó được chuyển đến đâu. Tên đích (*externalization target*) là định danh dùng cho mục đích định tuyến này.

Trong Spring Modulith, một event có thể khai báo đích externalization bằng annotation `@Externalized`. Ví dụ:

~~~java
import org.springframework.modulith.events.Externalized;

@Externalized("commerce.orders.v1")
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}
~~~

Chuỗi `commerce.orders.v1` là tên đích logic của event. Cơ chế externalization được cấu hình trong ứng dụng sử dụng định danh này để chuyển event đến đích tương ứng. Tên logic có thể được ánh xạ sang Kafka topic, RabbitMQ exchange hoặc một địa chỉ đích khác tùy integration đang dùng.

Tên đích giúp tách quyết định nghiệp vụ “event này được công bố cho luồng nào” khỏi chi tiết kết nối broker. Module Orders có thể công bố `OrderConfirmed` mà không cần biết địa chỉ máy chủ Kafka, tên virtual host RabbitMQ hay thông tin xác thực của hạ tầng.

## Phân biệt event type, target và broker destination

Ba khái niệm này thường bị dùng lẫn nhau, nhưng chúng trả lời ba câu hỏi khác nhau:

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Event type | Điều gì đã xảy ra? | `OrderConfirmed` |
| Externalization target | Event được công bố vào luồng tích hợp logic nào? | `commerce.orders.v1` |
| Broker destination | Hạ tầng nhận event ở địa chỉ vật lý nào? | Kafka topic `commerce.orders.v1` hoặc RabbitMQ exchange tương ứng |

Một event type có thể được công bố đến một target có tên khác. Một target cũng có thể được ánh xạ sang destination khác nhau ở từng môi trường. Ví dụ, cùng target `commerce.orders.v1` có thể được ánh xạ tới topic `dev.commerce.orders.v1` ở môi trường phát triển và `prod.commerce.orders.v1` ở production.

Tên target không tự tạo topic, exchange hoặc queue. Hạ tầng broker và cấu hình integration phải bảo đảm destination đã tồn tại, có quyền truy cập và có chính sách lưu giữ phù hợp.

## Khai báo target bằng Spring Modulith

Đặt `@Externalized` trên kiểu event để thể hiện event đó cần được externalize:

~~~java
@Externalized("commerce.orders.v1")
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}
~~~

Publisher vẫn phát application event trong transaction nghiệp vụ như bình thường:

~~~java
@Service
@RequiredArgsConstructor
public class OrderConfirmationService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.confirm();

        events.publishEvent(new OrderConfirmed(
            UUID.randomUUID(),
            order.getId(),
            Instant.now()
        ));
    }
}
~~~

Publisher không cần truyền tên topic vào từng lần gọi `publishEvent`. Target được gắn với loại event, giúp mọi nơi phát cùng loại event dùng chung một quy ước externalization.

Cách khai báo này cũng làm rõ ý định khi đọc mã nguồn: `OrderConfirmed` là event được đưa ra ngoài ứng dụng. Các event chỉ phục vụ giao tiếp nội bộ có thể không cần annotation externalization.

## Chọn tên target theo ngôn ngữ nghiệp vụ

Tên target nên phản ánh luồng dữ liệu mà consumer cần đăng ký nhận. Một tên tốt giúp đội phát triển nhận ra miền nghiệp vụ, nhóm sự kiện và phiên bản hợp đồng mà không phải đọc mã publisher.

Một quy ước có thể dùng:

~~~text
<domain>.<aggregate-or-capability>.<event-group>.v<major-version>
~~~

Ví dụ:

| Target | Ý nghĩa |
|---|---|
| `commerce.orders.v1` | Các sự kiện đơn hàng của miền commerce, hợp đồng phiên bản 1 |
| `identity.customers.v1` | Các sự kiện khách hàng của miền identity |
| `billing.invoices.v1` | Các sự kiện hóa đơn của miền billing |
| `fulfillment.shipments.v1` | Các sự kiện giao vận của miền fulfillment |

Không có một cấu trúc tên duy nhất phù hợp với mọi hệ thống. Điều quan trọng là thống nhất một quy ước, ghi rõ ý nghĩa từng phần và áp dụng nhất quán cho publisher, consumer, cấu hình broker và tài liệu vận hành.

Nên ưu tiên:

- Tên ổn định theo miền nghiệp vụ hoặc capability.
- Chữ thường và dấu chấm để phân tách các phần.
- Phiên bản hợp đồng khi cần thay đổi không tương thích.
- Tên ngắn, dễ đọc và không phụ thuộc vào tên class Java.
- Một danh mục target có chủ sở hữu và mô tả rõ ràng.

Tránh dùng tên gắn với một method, package hoặc tên nhóm phát triển như `OrderService.confirmOrder.result`. Những chi tiết này dễ đổi khi refactor nhưng không thể hiện hợp đồng mà consumer phụ thuộc.

## Chọn mức độ gom nhóm event

Một quyết định quan trọng là mỗi target chứa một loại event hay một nhóm event có liên quan.

**Một target cho mỗi event type** phù hợp khi mỗi loại event có chính sách lưu giữ, quyền truy cập, tải hoặc nhóm consumer khác nhau. Cách này tạo ranh giới rõ nhưng có thể làm số lượng topic hoặc exchange tăng nhanh.

**Một target cho một nhóm event nghiệp vụ** phù hợp khi các event cùng miền có chung chính sách vận hành và consumer thường cần đăng ký nhận cả nhóm. Khi đó payload hoặc metadata phải giúp consumer phân biệt event type.

Ví dụ, nhóm `commerce.orders.v1` có thể chứa `OrderPlaced`, `OrderConfirmed` và `OrderCancelled`. Consumer cần xử lý từng loại dựa trên event type trong envelope hoặc metadata do integration cung cấp.

| Tiêu chí | Target theo từng event | Target theo nhóm |
|---|---|---|
| Cô lập quyền truy cập | Dễ tách riêng | Cần kiểm soát ở mức nhóm |
| Chính sách retention | Có thể khác nhau theo event | Thường dùng chung |
| Số lượng destination | Nhiều hơn | Ít hơn |
| Consumer nhận nhiều event | Phải đăng ký nhiều target | Có thể đăng ký một target |
| Thay đổi hợp đồng | Cô lập theo từng loại | Cần quản lý tương thích trong cả nhóm |

Không nên tạo target riêng cho từng consumer nếu tất cả consumer đang đọc cùng một luồng sự kiện nghiệp vụ. Với mô hình publish/subscribe, broker thường cung cấp cơ chế consumer group hoặc subscription riêng để nhiều consumer độc lập nhận cùng event. Target mô tả luồng được công bố; consumer group mô tả cách một nhóm consumer cùng tiêu thụ luồng đó.

## Target không phải routing key hay consumer group

Khi thiết kế tích hợp, cần phân biệt thêm một số khái niệm của broker:

- **Target** là tên đích logic mà event được externalize tới.
- **Topic hoặc exchange** là destination được broker quản lý.
- **Routing key** là thông tin định tuyến message bên trong broker, đặc biệt thường gặp với RabbitMQ.
- **Partition key hoặc message key** giúp broker xác định phân vùng hoặc thứ tự tương đối của message, ví dụ trong Kafka.
- **Consumer group** là nhóm consumer phối hợp đọc message; các group khác nhau có thể nhận cùng một message theo semantics của broker.

Ví dụ, tất cả event đơn hàng có thể đi tới target `commerce.orders.v1`, trong khi `orderId` được dùng làm message key để các event của cùng đơn hàng thường được xử lý trong cùng partition. Target không cần chứa từng order ID.

~~~text
Application event
    |
    | @Externalized("commerce.orders.v1")
    v
Logical externalization target
    |
    | Integration mapping
    v
Broker destination
    |
    +--> Consumer group: fulfillment
    |
    +--> Consumer group: analytics
    |
    +--> Consumer group: notifications
~~~

Với RabbitMQ, integration có thể ánh xạ target sang exchange rồi dùng routing key để chọn queue. Với Kafka, target thường được ánh xạ sang topic, còn message key có thể được lấy từ định danh aggregate. Cách ánh xạ cụ thể thuộc cấu hình integration, không nên suy ra chỉ từ chuỗi annotation.

## Tên target và cấu hình theo môi trường

Giữ tên target logic ổn định trong mã nguồn và xử lý khác biệt môi trường ở cấu hình triển khai. Ví dụ:

| Môi trường | Target logic | Broker destination |
|---|---|---|
| Local | `commerce.orders.v1` | `local.commerce.orders.v1` |
| Test | `commerce.orders.v1` | `test.commerce.orders.v1` |
| Production | `commerce.orders.v1` | `prod.commerce.orders.v1` |

Bảng này chỉ minh họa một chiến lược ánh xạ. Tên prefix có thể được áp dụng bởi cấu hình hoặc integration của hệ thống.

Không nên viết cứng tên môi trường, hostname, credential hoặc namespace triển khai vào annotation. Làm như vậy khiến cùng một artifact khó chạy ở nhiều môi trường và dễ gây gửi nhầm dữ liệu. Các thông tin kết nối, prefix, quyền truy cập và địa chỉ broker nên được quản lý bằng cấu hình triển khai hoặc secret management.

Khi kiểm tra cấu hình, cần xác nhận:

1. Target được annotation khai báo có mapping tương ứng.
2. Destination vật lý tồn tại hoặc được provision đúng cách.
3. Ứng dụng có quyền publish vào destination.
4. Consumer có quyền subscribe hoặc bind vào destination.
5. Serialization, content type và schema của payload thống nhất giữa producer và consumer.
6. Môi trường test không thể vô tình publish vào destination production.

## Đặt tên có tính đến phiên bản hợp đồng

Tên target thường trở thành một phần của hợp đồng tích hợp. Consumer có thể cấu hình trực tiếp tên topic hoặc exchange, vì vậy đổi tên target có thể ảnh hưởng nhiều ứng dụng độc lập.

Khi payload thay đổi, hãy phân biệt thay đổi tương thích và không tương thích:

- Thêm một field tùy chọn mà consumer cũ có thể bỏ qua thường dễ triển khai hơn.
- Đổi ý nghĩa hoặc kiểu dữ liệu của field hiện có có thể phá vỡ consumer.
- Xóa field đang được consumer sử dụng là thay đổi không tương thích.
- Thay đổi cách serialize hoặc envelope cũng có thể là thay đổi hợp đồng dù tên target không đổi.

Với thay đổi không tương thích, cân nhắc tạo target phiên bản mới, chẳng hạn `commerce.orders.v2`. Có thể cần giai đoạn chuyển tiếp trong đó publisher công bố hợp đồng cũ và mới, hoặc một adapter chuyển đổi dữ liệu để consumer di chuyển theo lịch riêng.

Không nên tăng version chỉ vì đổi tên class hoặc refactor nội bộ nếu hợp đồng bên ngoài không thay đổi. Ngược lại, không nên giữ nguyên version khi consumer phải sửa mã để hiểu payload mới.

## Tránh target động làm phình topology

Tên target nên ổn định và có thể dự đoán. Không nên ghép ID khách hàng, đơn hàng hoặc dữ liệu đầu vào tùy ý vào tên destination để tạo ra một topic hay exchange mới cho từng đối tượng.

Ví dụ, thiết kế target như `commerce.orders.<orderId>` có thể khiến số lượng destination tăng theo số đơn hàng, làm phức tạp provisioning, phân quyền, monitoring và cleanup.

Nếu cần phân luồng theo đối tượng, hãy ưu tiên:

- Dùng một target ổn định cho nhóm event.
- Đưa aggregate ID hoặc tenant ID vào payload hay metadata thích hợp.
- Dùng message key, partition key hoặc routing key theo khả năng của broker.
- Tách destination chỉ khi có lý do vận hành rõ ràng như phân quyền, retention, tải hoặc vùng dữ liệu.

Một số cơ chế externalization có thể hỗ trợ biểu thức để tính target. Chỉ sử dụng khả năng đó khi integration và phiên bản Spring Modulith đang dùng hỗ trợ rõ ràng, đồng thời giới hạn tập giá trị đầu ra. Không dùng biểu thức để biến dữ liệu không tin cậy thành tên destination tùy ý.

## Kiểm thử việc ánh xạ target

Kiểm thử externalization cần xác nhận cả ý định trong mã nguồn và kết quả ánh xạ. Một số trường hợp nên kiểm tra:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Event có `@Externalized` | Được chọn để externalize |
| Event nội bộ không có annotation | Không bị gửi ra broker ngoài ý muốn |
| Target đã khai báo có mapping | Event được gửi đến destination dự kiến |
| Target không có mapping | Lỗi cấu hình được phát hiện sớm hoặc được xử lý theo chính sách đã định |
| Môi trường test | Không gửi sang destination production |
| Payload có event type khác nhau trong cùng target | Consumer phân biệt được loại event |
| Thay đổi version | Consumer cũ và mới xử lý đúng hợp đồng được hỗ trợ |

Có thể kiểm tra annotation bằng test đơn vị, còn mapping target và việc gửi message nên được kiểm thử ở mức integration với broker giả lập hoặc broker dùng cho test. Test cần xác nhận destination, message key hoặc routing metadata nếu ứng dụng có sử dụng chúng.

Tránh chỉ kiểm tra rằng một lời gọi publish đã xảy ra. Một message được gửi thành công tới sai topic vẫn là lỗi tích hợp.

## Quan sát target trong môi trường chạy

Tên target nên xuất hiện nhất quán trong log, metric và trace để đội vận hành lần theo đường đi của event. Các thông tin hữu ích gồm:

- Target logic được khai báo.
- Destination vật lý sau khi mapping.
- Event type và event ID.
- Thời điểm publish và kết quả xác nhận từ broker.
- Số publication chờ, lỗi và thời gian chờ lâu nhất nếu registry/integration cung cấp.
- Số message theo target, partition hoặc queue tùy broker.

Không đưa payload nhạy cảm, token hoặc thông tin xác thực vào log. Khi log có event ID và target, đội vận hành thường đã có đủ khóa để tra cứu message mà không cần ghi toàn bộ payload.

Nếu một target không có traffic, hãy kiểm tra publisher có phát event hay không, annotation có đúng kiểu event không, externalization selector có chọn event đó không, và mapping có trỏ tới destination đang được consumer theo dõi không. Nếu broker nhận message nhưng consumer không xử lý, kiểm tra subscription, consumer group, routing key, quyền truy cập và lỗi deserialize.

## Quy trình đặt tên target

Khi thêm một loại event cần externalize, thực hiện theo thứ tự:

1. Xác định miền nghiệp vụ và nhóm consumer cần nhận event.
2. Quyết định target đại diện cho một event type hay một nhóm event có chung chính sách vận hành.
3. Chọn tên ổn định theo quy ước của hệ thống, có version khi hợp đồng cần quản lý phiên bản.
4. Gắn `@Externalized` lên event type cần công bố.
5. Cấu hình mapping target sang destination phù hợp cho từng môi trường.
6. Xác định message key, routing key hoặc metadata riêng nếu cần phân vùng và định tuyến.
7. Kiểm thử target, destination, payload và quyền publish/subscribe.
8. Ghi lại owner, mục đích, schema, consumer và chính sách vòng đời của destination.

Tên đích tốt làm cho ranh giới tích hợp dễ hiểu và dễ vận hành. Khi target ổn định, có quy ước rõ và được ánh xạ qua cấu hình, module Spring Modulith có thể công bố sự kiện theo ngôn ngữ nghiệp vụ trong khi broker vẫn được quản lý theo nhu cầu triển khai.
