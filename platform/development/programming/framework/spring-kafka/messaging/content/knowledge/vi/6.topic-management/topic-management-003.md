# Tên topic và quy ước đặt tên

## Mục tiêu của bài học

Trong chương **Quản lý topic**, bài này xác định cách chọn tên topic Kafka rõ nghĩa, ổn định và nhất quán để producer, consumer, nhóm vận hành và các đội phát triển cùng hiểu hợp đồng messaging.

**SPRING_KAFKA_MESSAGING** tập trung xây dựng ứng dụng gửi và nhận sự kiện Kafka bằng Spring Kafka, KafkaTemplate và @KafkaListener; đồng thời giúp người học hiểu topic, partition, offset, consumer group, serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử. Tên topic là một phần của hợp đồng giữa các thành phần trong luồng sự kiện: tên tốt giúp nhận diện mục đích của dữ liệu và giảm nhầm lẫn khi hệ thống mở rộng.

Sau bài học, người học có thể:

- Nắm vai trò của tên topic trong kiến trúc event-driven.
- Áp dụng giới hạn ký tự và quy tắc tên topic của Kafka.
- Xây dựng quy ước tên dựa trên domain, thực thể và loại sự kiện.
- Phân biệt tên topic với consumer group, partition, schema version và môi trường.
- Nhận diện các anti-pattern như tên quá chung chung, tên theo bảng database hoặc tên chứa thông tin biến đổi.
- Đưa quy ước tên vào cấu hình Spring Kafka và quy trình quản trị topic.

## 1. Vì sao tên topic quan trọng?

Topic là nơi Kafka lưu các bản ghi có cùng một luồng dữ liệu logic. Producer ghi bản ghi vào topic; consumer thuộc các consumer group đọc bản ghi từ topic theo partition và offset. Một topic có thể được nhiều consumer group độc lập tiêu thụ.

Tên topic thường xuất hiện trong:

- Mã producer và consumer.
- Cấu hình tạo topic, retention, partition và replication.
- ACL và chính sách bảo mật.
- Dashboard, metric, log và cảnh báo.
- Tài liệu hợp đồng sự kiện và danh mục dữ liệu.
- Công cụ vận hành, triển khai và xử lý dead-letter.

Một tên như **orders** có thể đủ dễ hiểu khi hệ thống còn nhỏ. Khi có thêm nhiều luồng đơn hàng, chẳng hạn đơn hàng được tạo, thanh toán, hủy, giao hàng và hoàn tiền, tên quá chung khiến người đọc khó biết chính xác topic chứa loại dữ liệu nào.

Ngược lại, tên **commerce.order.created** mô tả được ngữ cảnh nghiệp vụ, thực thể và sự kiện. Nhóm phát triển có thể nhận diện mục đích của topic ngay từ tên mà không cần đọc mã nguồn của mọi producer.

Tên topic nên được xem là một phần của giao diện tích hợp giữa các hệ thống. Đổi tên topic có thể ảnh hưởng đồng thời tới producer, consumer, ACL, dashboard, connector và quy trình vận hành.

## 2. Quy tắc kỹ thuật của tên topic Kafka

Kafka áp dụng các giới hạn kỹ thuật cho tên topic. Quy ước nội bộ của tổ chức cần tuân thủ các giới hạn này trước khi xét tới khả năng đọc hiểu.

### 2.1. Ký tự được phép

Tên topic Kafka sử dụng các ký tự ASCII sau:

- Chữ cái từ **a** đến **z** và **A** đến **Z**.
- Chữ số từ **0** đến **9**.
- Dấu chấm **.**
- Dấu gạch dưới **_**.
- Dấu gạch ngang **-**.

Tên topic không được là dấu chấm đơn **.** hoặc hai dấu chấm **..**. Độ dài tối đa của tên topic là **249 ký tự**.

Ví dụ hợp lệ:

~~~text
orders
orders.created
commerce.order.created
inventory-stock-reserved
payment_events
orders-v2
~~~

Ví dụ không hợp lệ:

~~~text
order created
orders/created
orders:created
đơn-hàng-đã-tạo
.
..
~~~

Không dùng khoảng trắng, dấu **/**, dấu **:**, ký tự tiếng Việt có dấu hoặc ký tự ngoài tập được phép. Nên chọn tên ASCII để tránh lỗi khi dùng shell, cấu hình, công cụ giám sát và hệ thống tích hợp.

### 2.2. Phân biệt chữ hoa và chữ thường

Tên topic có phân biệt chữ hoa và chữ thường. Vì vậy, **Orders.Created** và **orders.created** là hai tên khác nhau.

Dù Kafka cho phép chữ hoa, nên thống nhất dùng chữ thường để giảm lỗi gõ và tránh việc các nhóm vô tình tạo hai topic có ý nghĩa giống nhau nhưng khác cách viết.

### 2.3. Tránh trộn dấu chấm và dấu gạch dưới

Kafka cho phép cả **.** và **_**, nhưng tên topic chứa hai loại dấu này có thể gây va chạm trong một số tên metric JMX vì chúng được ánh xạ thành dạng tên metric tương tự.

Ví dụ, các tên như:

~~~text
orders.created
orders_created
~~~

có thể khó phân biệt trong một số hệ thống metric. Vì vậy, hãy chọn một quy ước phân tách nhất quán. Bài này dùng dấu chấm để chia các thành phần nghiệp vụ và dấu gạch ngang nếu cần nối nhiều từ trong cùng một thành phần.

### 2.4. Tránh tiền tố dành cho topic nội bộ

Kafka sử dụng các topic nội bộ có tên bắt đầu bằng hai dấu gạch dưới, chẳng hạn **__consumer_offsets** và **__transaction_state**.

Ứng dụng nghiệp vụ nên tránh tiền tố **__** để không nhầm lẫn với topic do Kafka quản lý. Có thể đặt quy tắc cấm tên bắt đầu bằng **__** trong công cụ tạo topic của tổ chức.

## 3. Mẫu đặt tên được khuyến nghị

Một mẫu dễ mở rộng cho topic chứa business event là:

~~~text
<domain>.<entity>.<event>
~~~

Trong đó:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| domain | Bounded context hoặc miền nghiệp vụ sở hữu dữ liệu | commerce, inventory, identity |
| entity | Thực thể hoặc aggregate mà sự kiện mô tả | order, payment, stock |
| event | Sự kiện nghiệp vụ đã xảy ra | created, authorized, reserved |

Ví dụ:

~~~text
commerce.order.created
commerce.order.cancelled
commerce.payment.authorized
commerce.payment.refunded
inventory.stock.reserved
identity.customer.registered
~~~

Mẫu này không phải yêu cầu bắt buộc của Kafka. Đây là quy ước kiến trúc giúp tên topic thể hiện ngữ nghĩa nghiệp vụ và hỗ trợ tổ chức nhiều nhóm phát triển.

### 3.1. Đặt tên theo domain

Domain nên phản ánh miền nghiệp vụ hoặc bounded context chịu trách nhiệm về event. Dùng từ ngắn, ổn định và được tổ chức thống nhất.

Ví dụ:

- **commerce**: đơn hàng, thanh toán và giao dịch thương mại.
- **inventory**: tồn kho và đặt giữ hàng.
- **shipping**: vận chuyển và giao nhận.
- **identity**: tài khoản, danh tính và xác thực.

Tránh dùng tên phòng ban hoặc tên cá nhân vì cơ cấu tổ chức có thể thay đổi trong khi hợp đồng sự kiện cần tồn tại lâu dài.

Nếu một event được phát bởi dịch vụ kỹ thuật nhưng thuộc về domain khác, hãy đặt tên theo ngữ nghĩa nghiệp vụ của event. Ví dụ, dịch vụ **order-service** phát event **commerce.order.created**, thay vì tạo tên **order-service-created**.

### 3.2. Đặt tên theo entity hoặc aggregate

Entity giúp người đọc biết event mô tả đối tượng nào. Nên dùng danh từ số ít khi event nói về một thực thể:

~~~text
commerce.order.created
commerce.payment.authorized
inventory.product.updated
~~~

Không trộn số ít và số nhiều tùy tiện. Nếu tổ chức chọn danh từ số nhiều, cần áp dụng nhất quán ở tất cả domain. Trong ví dụ của bài này, entity dùng số ít.

Không nhất thiết mỗi bảng database tương ứng với một entity topic. Một aggregate có thể phát nhiều event; một event cũng có thể phản ánh thay đổi nghiệp vụ liên quan đến nhiều bảng.

### 3.3. Đặt tên theo event

Event nên diễn đạt điều đã xảy ra, thường dùng dạng quá khứ hoặc phân từ trong tiếng Anh:

- **created**
- **approved**
- **cancelled**
- **paid**
- **shipped**
- **reserved**
- **refunded**

Ví dụ:

~~~text
commerce.order.created
commerce.order.approved
commerce.order.cancelled
commerce.payment.refunded
~~~

Tên event nên phản ánh sự kiện nghiệp vụ có ý nghĩa. Tránh tên quá kỹ thuật như **row-inserted**, **column-updated** hoặc **save-success** nếu người tiêu thụ cần hiểu trạng thái nghiệp vụ chứ không phải chi tiết database.

### 3.4. Phân biệt event với command

Event mô tả điều đã xảy ra; command biểu đạt yêu cầu một thành phần thực hiện hành động.

| Ý nghĩa | Ví dụ tên | Cách hiểu |
|---|---|---|
| Event | commerce.order.created | Một đơn hàng đã được tạo |
| Event | commerce.payment.authorized | Một khoản thanh toán đã được cấp phép |
| Command | commerce.order.create | Yêu cầu tạo đơn hàng |
| Command | commerce.payment.authorize | Yêu cầu cấp phép thanh toán |

Không trộn command và event vào cùng một topic nếu hai loại thông điệp có semantics, quyền xử lý hoặc chính sách retry khác nhau. Nếu hệ thống dùng Kafka cho command, hãy quy định rõ tên và hợp đồng riêng cho luồng command.

## 4. Chọn mức độ chi tiết của tên

Tên topic cần đủ cụ thể để phân biệt các luồng dữ liệu, nhưng không nên tạo ra một topic mới cho từng biến thể nhỏ không có khác biệt về hợp đồng hoặc vận hành.

### 4.1. Tránh tên quá chung

| Tên chưa rõ nghĩa | Vấn đề | Tên cụ thể hơn |
|---|---|---|
| data | Không biết dữ liệu thuộc domain nào | commerce.order.created |
| events | Trộn nhiều loại event | inventory.stock.reserved |
| updates | Không rõ thực thể và thay đổi gì | identity.customer.updated |
| messages | Chỉ mô tả phương tiện truyền tin | shipping.delivery.dispatched |
| orders | Có thể chứa mọi trạng thái đơn hàng | commerce.order.created hoặc commerce.order.cancelled |

### 4.2. Tránh tên quá chi tiết theo triển khai

Không đưa thông tin dễ thay đổi theo mã nguồn hoặc hạ tầng vào tên topic:

~~~text
order-service-v2-instance-03-created
mysql-orders-table-cdc-prod
billing-worker-thread-4
~~~

Những thông tin như tên instance, thread, host, database vật lý hoặc tên deployment thường thuộc metadata, cấu hình hay hệ thống quan sát.

Nếu topic thực sự là luồng CDC, có thể dùng quy ước riêng thể hiện nguồn dữ liệu và bảng, nhưng phải phân biệt rõ topic CDC với business event. Ví dụ:

~~~text
cdc.sales.orders
~~~

Không nên đặt tên CDC như thể đó là event nghiệp vụ đã được chuẩn hóa nếu payload chỉ phản ánh thay đổi bản ghi database.

### 4.3. Không tạo topic theo từng bản ghi hoặc từng người dùng

Không tạo tên topic động dựa trên order ID, customer ID, tenant ID hoặc timestamp:

~~~text
order-10001
order-10002
customer-9382-events
events-2026-11-17
~~~

Mô hình này làm số lượng topic tăng không kiểm soát, gây áp lực lên metadata, controller, ACL, giám sát và vận hành.

Thay vào đó, đặt một topic ổn định và dùng record key, header hoặc trường payload để phân biệt từng thực thể:

~~~text
Topic: commerce.order.created
Key:   order-10001
Value: {"orderId":"order-10001","status":"CREATED"}
~~~

Nếu cần phân vùng dữ liệu theo tenant, hãy đánh giá key, partitioning, authorization và chính sách cách ly. Không dùng một topic riêng cho mỗi tenant trừ khi có yêu cầu cách ly hoặc vận hành thực sự cần thiết.

## 5. Tên topic và các khái niệm không nên trộn lẫn

Tên topic chỉ nhận diện luồng dữ liệu logic. Nó không thay thế các cấu hình và định danh khác của Kafka.

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| Topic | Luồng dữ liệu được lưu trong Kafka | commerce.order.created |
| Record key | Định tuyến và nhận diện nhóm bản ghi liên quan | order-10001 |
| Partition | Đơn vị lưu trữ và song song trong topic | Partition 0, 1, 2 |
| Consumer group | Nhóm consumer cùng chia sẻ việc đọc topic | billing-service |
| Offset | Vị trí bản ghi trong một partition | Offset 125 |
| Schema version | Phiên bản hợp đồng cấu trúc dữ liệu | Schema version 3 |
| Environment | Môi trường triển khai | dev, staging, prod |
| Replication factor | Số replica của mỗi partition | 3 |

Ví dụ, **commerce.order.created** là tên topic; **order-10001** có thể là record key; **billing-service** là consumer group. Không nối tất cả các thông tin này thành một tên topic.

### 5.1. Tên topic không quyết định partition

Tên topic không quy định số partition hoặc cách phân phối key. Các thuộc tính đó được cấu hình khi tạo topic và producer gửi record.

Ví dụ:

~~~text
Topic: commerce.order.created
Partitions: 6
Key strategy: orderId
Replication factor: 3
~~~

Tên topic ổn định ngay cả khi số partition thay đổi theo kế hoạch mở rộng. Tuy nhiên, tăng partition có thể ảnh hưởng tới mapping key-partition và thứ tự giữa các bản ghi cùng key nếu partitioner mặc định được sử dụng. Đây là quyết định vận hành cần đánh giá riêng.

### 5.2. Tên topic không thay thế consumer group

Một topic có thể được nhiều consumer group đọc độc lập:

~~~text
Topic: commerce.order.created

Consumer groups:
- billing-service
- analytics-service
- notification-service
~~~

Không tạo các topic **commerce.order.created.billing**, **commerce.order.created.analytics** chỉ để mỗi ứng dụng có một luồng đọc riêng. Consumer group đã giải quyết nhu cầu tiêu thụ độc lập trong mô hình Kafka thông thường.

### 5.3. Tên topic không thay thế schema version

Schema version thường thuộc schema registry, header hoặc metadata của hợp đồng dữ liệu. Không nên thêm số phiên bản vào mọi tên topic khi cấu trúc chỉ thay đổi tương thích.

Chỉ cân nhắc topic version mới khi có thay đổi semantics hoặc hợp đồng không tương thích khiến producer và consumer cần một luồng tách biệt trong thời gian chuyển đổi.

## 6. Quy ước môi trường và khu vực triển khai

Có hai cách tổ chức phổ biến.

### 6.1. Mỗi môi trường dùng cluster riêng

Nếu development, staging và production chạy trên các Kafka cluster độc lập, có thể giữ cùng tên topic ở tất cả môi trường:

~~~text
dev cluster:     commerce.order.created
staging cluster: commerce.order.created
production:      commerce.order.created
~~~

Cách này giúp mã ứng dụng và tài liệu không phải thay đổi tên topic theo môi trường. Bootstrap server và secret được cấu hình theo deployment.

### 6.2. Nhiều môi trường dùng chung một cluster

Nếu tổ chức buộc phải chia sẻ một cluster, có thể thêm environment prefix:

~~~text
dev.commerce.order.created
staging.commerce.order.created
prod.commerce.order.created
~~~

Khi chọn cách này, phải áp dụng thống nhất cho tất cả topic liên quan, gồm retry, DLT và topic phục vụ tích hợp. ACL và quy trình tạo topic cần kiểm tra prefix để tránh ứng dụng môi trường này truy cập nhầm dữ liệu môi trường khác.

Không thêm prefix môi trường chỉ vì thói quen nếu các cluster đã được tách biệt. Prefix dư thừa làm tên dài hơn và khiến hợp đồng logic phụ thuộc vào topology triển khai.

### 6.3. Khu vực hoặc vùng dữ liệu

Chỉ đưa region vào tên topic khi một cluster thực sự chứa nhiều luồng dữ liệu theo vùng và consumer cần phân biệt chúng bằng topic. Nếu region chỉ là thông tin triển khai, hãy để nó trong cấu hình hoặc metadata.

Ví dụ có thể dùng:

~~~text
apac.commerce.order.created
eu.commerce.order.created
~~~

Quyết định này cần được phối hợp với chính sách data residency, replication liên vùng và quyền truy cập. Không thêm region nếu nó không mang ý nghĩa trong hợp đồng dữ liệu.

## 7. Versioning và thay đổi tên topic

Tên topic thường được tham chiếu trong mã nguồn và cấu hình của nhiều dịch vụ. Kafka không cung cấp thao tác đổi tên topic trực tiếp như đổi tên một file. Khi cần thay tên hoặc tách hợp đồng, cách an toàn thường là tạo topic mới và thực hiện migration có kiểm soát.

### 7.1. Khi nào không cần tạo topic version mới?

Nếu thay đổi payload vẫn tương thích với consumer hiện có, hãy ưu tiên schema evolution:

- Thêm field tùy chọn có default phù hợp.
- Giữ nguyên ý nghĩa field hiện có.
- Không đổi kiểu dữ liệu theo cách phá vỡ consumer cũ.
- Kiểm tra quy tắc tương thích của schema registry nếu đang sử dụng.

Ví dụ, thêm **currency** vào event có thể tương thích nếu consumer cũ bỏ qua field chưa biết và hợp đồng có quy định rõ giá trị mặc định.

### 7.2. Khi nào nên tạo topic mới?

Cân nhắc topic mới khi:

- Ý nghĩa event thay đổi đáng kể.
- Payload mới không tương thích với consumer hiện có.
- Cần chuyển đổi sang partitioning hoặc retention khác mà không thể thay đổi an toàn tại chỗ.
- Muốn tách luồng có quyền truy cập hoặc vòng đời dữ liệu khác nhau.
- Cần migration theo giai đoạn để nhiều consumer chuyển đổi độc lập.

Ví dụ:

~~~text
commerce.order.created
commerce.order.created.v2
~~~

Chỉ dùng suffix version khi có lý do về hợp đồng. Không tăng version chỉ vì ứng dụng được release phiên bản mới.

### 7.3. Quy trình migration topic

Một quy trình migration có thể gồm:

1. Xác định khác biệt giữa topic cũ và topic mới.
2. Khai báo hợp đồng event, owner, key, schema và chính sách lưu trữ cho topic mới.
3. Tạo topic mới với partition, replication và retention phù hợp.
4. Cập nhật producer để phát event theo chiến lược chuyển tiếp đã chọn.
5. Cập nhật consumer, kiểm thử dữ liệu và xác nhận không bỏ sót hoặc xử lý trùng ngoài dự kiến.
6. Theo dõi lag, lỗi và mức tiêu thụ trên topic mới.
7. Chuyển toàn bộ consumer sang topic mới.
8. Ngừng producer cũ, chờ hết thời gian lưu trữ và xử lý yêu cầu replay.
9. Xóa topic cũ theo chính sách quản trị và thời hạn đã thống nhất.

Trong giai đoạn dual-publish, hai topic có thể chứa cùng một sự kiện. Consumer cần idempotency hoặc cơ chế deduplicate nếu có khả năng đọc cả hai luồng.

## 8. Quy ước cho retry topic và dead-letter topic

Retry và dead-letter topic thường có quan hệ với topic nghiệp vụ gốc. Nên đặt tên sao cho người vận hành nhìn vào biết topic gốc và mục đích xử lý.

Một số mẫu có thể chọn:

~~~text
commerce.order.created.retry
commerce.order.created.dlt
~~~

Hoặc nếu có nhiều mức retry:

~~~text
commerce.order.created.retry.1
commerce.order.created.retry.2
commerce.order.created.dlt
~~~

Đây là quy ước ví dụ; Spring Kafka có thể tạo retry topic theo cấu hình và naming strategy được chọn. Cần kiểm tra tên thực tế mà ứng dụng tạo ra, đặc biệt khi dùng @RetryableTopic.

Các nguyên tắc:

- Giữ tên topic gốc trong tên retry/DLT để truy vết.
- Dùng cùng một suffix và thứ tự thành phần trên toàn hệ thống.
- Không nhầm retry topic với event nghiệp vụ mới.
- Đặt retention và quyền truy cập phù hợp với dữ liệu lỗi.
- Theo dõi số bản ghi vào DLT và xác định owner chịu trách nhiệm phục hồi.
- Tránh tạo retry topic bằng cách nối thêm suffix nhiều lần qua các lần retry.

Topic nội bộ do Kafka quản lý như **__consumer_offsets** không phải DLT của ứng dụng và không nên được xử lý như topic nghiệp vụ.

## 9. Quy ước tên trong mã nguồn Spring Kafka

Để giảm lỗi gõ sai tên topic, ứng dụng nên tập trung tên topic tại một nơi có thể kiểm soát, chẳng hạn cấu hình hoặc lớp constants.

### 9.1. Dùng constants trong ứng dụng

~~~java
public final class KafkaTopics {

    private KafkaTopics() {
    }

    public static final String ORDER_CREATED =
        "commerce.order.created";

    public static final String PAYMENT_AUTHORIZED =
        "commerce.payment.authorized";
}
~~~

Producer:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event) {
        kafkaTemplate.send(
            KafkaTopics.ORDER_CREATED,
            event.orderId(),
            event
        );
    }
}
~~~

Consumer:

~~~java
@Service
public class OrderEventListener {

    @KafkaListener(
        topics = KafkaTopics.ORDER_CREATED,
        groupId = "billing-service"
    )
    public void receive(OrderCreated event) {
        // Xử lý sự kiện đơn hàng.
    }
}
~~~

Constants giúp tránh việc producer và consumer trong cùng ứng dụng dùng hai chuỗi khác nhau. Với nhiều ứng dụng độc lập, cần duy trì hợp đồng qua tài liệu, schema registry hoặc artifact chia sẻ được quản lý phiên bản; không nên phụ thuộc vào việc mọi service phải import cùng một lớp Java.

### 9.2. Dùng cấu hình bên ngoài

Nếu tên topic thay đổi theo môi trường hoặc deployment, có thể đưa vào cấu hình:

~~~yaml
app:
  kafka:
    topics:
      order-created: commerce.order.created
      payment-authorized: commerce.payment.authorized
~~~

Inject giá trị vào listener:

~~~java
@KafkaListener(
    topics = "${app.kafka.topics.order-created}",
    groupId = "billing-service"
)
public void receive(OrderCreated event) {
    // Xử lý sự kiện.
}
~~~

Cấu hình ngoài hữu ích khi cần prefix môi trường hoặc thay đổi endpoint theo deployment. Hãy kiểm tra giá trị đã resolve khi ứng dụng khởi động và xác nhận topic tồn tại theo chính sách tạo topic.

### 9.3. Khai báo topic bằng NewTopic

Ứng dụng có thể khai báo topic cần tạo qua KafkaAdmin và bean NewTopic:

~~~java
@Configuration
public class TopicConfiguration {

    @Bean
    public NewTopic orderCreatedTopic() {
        return TopicBuilder.name(KafkaTopics.ORDER_CREATED)
            .partitions(6)
            .replicas(3)
            .build();
    }
}
~~~

Ví dụ này giả định cluster có đủ broker để đặt ba replica. Với môi trường development một broker, cần dùng replication factor bằng 1.

Tên topic trong bean phải tuân theo cùng naming convention với producer, consumer và tài liệu hợp đồng. Nếu topic đã tồn tại, việc khai báo bean không có nghĩa mọi thuộc tính hiện hữu sẽ tự động được thay đổi như mong muốn; việc thay đổi partition hoặc cấu hình topic cần theo chính sách quản trị và khả năng của Kafka.

## 10. Ví dụ quy ước hoàn chỉnh cho một domain

Giả sử hệ thống thương mại điện tử có các bounded context Commerce, Inventory, Payment và Shipping.

| Domain | Topic | Ý nghĩa |
|---|---|---|
| Commerce | commerce.order.created | Đơn hàng được tạo |
| Commerce | commerce.order.cancelled | Đơn hàng bị hủy |
| Commerce | commerce.order.completed | Đơn hàng hoàn tất |
| Commerce | commerce.payment.authorized | Thanh toán được cấp phép |
| Commerce | commerce.payment.captured | Tiền được thu |
| Commerce | commerce.payment.refunded | Khoản tiền được hoàn |
| Inventory | inventory.stock.reserved | Tồn kho được giữ |
| Inventory | inventory.stock.released | Tồn kho được giải phóng |
| Shipping | shipping.delivery.dispatched | Đơn giao hàng được bàn giao |
| Shipping | shipping.delivery.delivered | Hàng đã được giao |

Một số consumer group có thể sử dụng các topic này:

| Consumer group | Topic quan tâm | Mục đích |
|---|---|---|
| billing-service | commerce.order.created, commerce.payment.captured | Tạo và đối soát hóa đơn |
| inventory-service | commerce.order.created, commerce.order.cancelled | Giữ hoặc giải phóng tồn kho |
| notification-service | Các topic order, payment và delivery | Gửi thông báo |
| analytics-service | Nhiều topic nghiệp vụ | Tổng hợp dữ liệu phân tích |

Topic phản ánh loại event; consumer group phản ánh một nhóm ứng dụng cùng chia sẻ tiến trình tiêu thụ. Nhờ tách hai khái niệm, một event có thể phục vụ nhiều nhu cầu mà producer không cần tạo topic riêng cho từng consumer.

## 11. Những anti-pattern cần tránh

| Anti-pattern | Ví dụ | Vấn đề |
|---|---|---|
| Tên quá chung | data, events, messages | Không thể hiện domain hoặc event |
| Tên theo service | order-service-events | Gắn hợp đồng vào tên triển khai |
| Tên theo database | orders_table_changes | Nhầm CDC với business event |
| Tên động theo entity ID | order-10001 | Tạo quá nhiều topic |
| Tên chứa môi trường không nhất quán | dev.orders, orders.prod, staging-orders | Khó tự động hóa và quản trị |
| Trộn separator | commerce_order.created | Dễ gây nhầm lẫn và metric collision |
| Dùng chữ hoa tùy tiện | Commerce.Order.Created | Dễ tạo topic trùng nghĩa khác case |
| Tạo version không có lý do | order.v3, order.v4, order.v5 | Tăng chi phí migration và quản lý consumer |
| Dùng tên command cho event | create-order | Không thể hiện sự kiện đã xảy ra |
| Dùng prefix nội bộ | __commerce.order.created | Dễ nhầm với topic nội bộ Kafka |

## 12. Quản trị và kiểm soát quy ước đặt tên

Quy ước chỉ hữu ích khi được áp dụng nhất quán. Tổ chức nên có danh mục topic (topic catalog) và quy trình duyệt tạo topic.

Mỗi topic nên có metadata quản trị tối thiểu:

| Metadata | Nội dung |
|---|---|
| Topic name | Tên topic chính thức |
| Domain owner | Nhóm chịu trách nhiệm về event |
| Purpose | Mô tả ngắn mục đích và ngữ nghĩa |
| Producer | Các ứng dụng được phép publish |
| Consumer groups | Các nhóm đang tiêu thụ |
| Key strategy | Quy tắc chọn record key |
| Partition count | Số partition dự kiến |
| Replication factor | Số replica |
| Retention | Thời gian hoặc dung lượng lưu trữ |
| Schema/contract | Vị trí và phiên bản hợp đồng dữ liệu |
| Data classification | Mức độ nhạy cảm của dữ liệu |
| Retry/DLT | Topic liên quan và quy trình xử lý lỗi |
| Lifecycle | Trạng thái active, deprecated hoặc retired |

### 12.1. Quy trình tạo topic mới

Trước khi tạo topic:

1. Xác định domain owner và producer chịu trách nhiệm phát event.
2. Viết mô tả event, thời điểm phát và ý nghĩa payload.
3. Chọn tên theo mẫu thống nhất.
4. Kiểm tra giới hạn ký tự và tên trùng nghĩa trong catalog.
5. Xác định key, partition, retention và replication.
6. Xác định schema compatibility và data classification.
7. Xác định consumer group dự kiến, retry và DLT nếu cần.
8. Đăng ký topic trong catalog và áp dụng ACL.
9. Tạo topic qua quy trình quản trị hoặc deployment đã thống nhất.

### 12.2. Kiểm tra tên tự động

Có thể xây dựng quy tắc kiểm tra trong CI hoặc công cụ tạo topic:

- Tên không vượt quá 249 ký tự.
- Chỉ chứa chữ ASCII, chữ số, dấu chấm, gạch dưới hoặc gạch ngang.
- Không bằng **.** hoặc **..**.
- Không bắt đầu bằng **__**.
- Dùng chữ thường theo convention.
- Không trộn dấu chấm và dấu gạch dưới.
- Có đủ thành phần domain, entity và event.
- Không trùng với tên đã đăng ký hoặc tên có ý nghĩa tương đương.

Regex có thể hỗ trợ kiểm tra cú pháp, nhưng không thể xác nhận ngữ nghĩa domain. Việc duyệt catalog vẫn cần owner nghiệp vụ hoặc nhóm kiến trúc.

Một biểu thức kiểm tra sơ bộ cho convention chữ thường, phân tách bằng dấu chấm:

~~~regex
^[a-z0-9-]+(\.[a-z0-9-]+)+$
~~~

Regex này là quy tắc nội bộ minh họa, không phải regex đầy đủ mô tả mọi tên topic Kafka hợp lệ. Sau khi kiểm tra regex vẫn cần kiểm tra độ dài, tên đặc biệt, prefix nội bộ và catalog.

## 13. Checklist chọn tên topic

Trước khi tạo topic, hãy tự hỏi:

- [ ] Tên có thể hiện đúng domain hoặc bounded context không?
- [ ] Entity và event có được phân biệt rõ không?
- [ ] Event name diễn tả điều đã xảy ra hay chỉ mô tả thao tác kỹ thuật?
- [ ] Tên chỉ dùng ký tự Kafka cho phép và không vượt 249 ký tự?
- [ ] Tên dùng chữ thường và một separator nhất quán?
- [ ] Tên có tránh prefix **__** dành cho Kafka internal topic?
- [ ] Tên có tránh order ID, tenant ID, timestamp hoặc instance ID?
- [ ] Tên có độc lập với tên service, bảng database và framework không?
- [ ] Có cần environment prefix hay cluster đã tách riêng?
- [ ] Có lý do rõ ràng nếu đưa version vào tên?
- [ ] Topic có owner, purpose, key, retention và schema được ghi nhận?
- [ ] Retry và DLT có quy ước nhất quán với topic gốc?
- [ ] Producer, consumer, ACL và catalog dùng cùng một tên?

## Kết luận

Tên topic là một phần của hợp đồng tích hợp giữa producer, consumer và hệ thống vận hành. Một quy ước tốt thường thể hiện domain, entity và event; dùng ký tự hợp lệ, chữ thường và separator nhất quán; tránh tên động, tên quá chung, thông tin triển khai và tiền tố dành cho topic nội bộ.

Khi kết hợp quy ước đặt tên với catalog, owner, schema, partition, retention và ACL, tổ chức có thể quản lý luồng sự kiện rõ ràng hơn khi số lượng topic và consumer group tăng lên. Spring Kafka sử dụng các tên topic này qua KafkaTemplate, @KafkaListener và cấu hình quản trị topic; việc thống nhất tên từ đầu giúp các thành phần giao tiếp ổn định và dễ vận hành.
