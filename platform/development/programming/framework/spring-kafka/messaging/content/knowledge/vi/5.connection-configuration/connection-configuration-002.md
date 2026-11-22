# client.id và nhận diện client

Trong Kafka, một ứng dụng có thể tạo nhiều Kafka client: producer để gửi record, consumer để đọc record, admin client để quản trị cluster. Mỗi client có thể mang một chuỗi nhận diện gọi là **`client.id`**. Broker dùng giá trị này để ghi nhận client gửi request; Kafka client cũng dùng nó làm nhãn trong nhiều metric. Nhờ vậy, người vận hành có thể phân biệt request và số liệu đến từ producer, consumer hoặc instance nào.

`client.id` là metadata nhận diện phục vụ quan sát và quản lý lưu lượng. Nó không phải tên consumer group, không định danh record, không xác thực ứng dụng và cũng không quyết định record được gửi đến partition nào. Hiểu đúng ranh giới này giúp đặt tên nhất quán và chẩn đoán hệ thống khi có nhiều instance cùng kết nối Kafka.

## 1. `client.id` là gì?

`client.id` là cấu hình dạng chuỗi trên một Kafka client. Ứng dụng có thể đặt giá trị này khi tạo producer, consumer hoặc admin client. Nếu không cấu hình, Kafka client có thể tự sinh một ID mặc định. Giá trị tự sinh hữu ích để client hoạt động, nhưng thường khó đọc khi phải đối chiếu log và metric ở môi trường nhiều dịch vụ.

Ví dụ một dịch vụ xử lý đơn hàng có thể dùng:

| Thành phần | `client.id` gợi ý | Mục đích |
|---|---|---|
| Producer gửi sự kiện đơn hàng | `order-api-producer` | Nhận diện lưu lượng gửi |
| Consumer cập nhật hóa đơn | `billing-consumer` | Nhận diện client đọc |
| Listener cập nhật projection | `orders-projection` | Phân biệt một luồng listener |
| Admin client quản trị topic | `messaging-admin` | Nhận diện thao tác quản trị |

Một `client.id` tốt cho biết client thuộc ứng dụng hoặc vai trò nào. Khi cần phân biệt từng bản chạy, có thể bổ sung tên instance, pod hoặc một hậu tố do nền tảng triển khai cấp.

## 2. Phân biệt `client.id` với các ID Kafka khác

Kafka có nhiều loại ID vì chúng giải quyết những vấn đề khác nhau. Không nên dùng một giá trị thay cho tất cả:

| ID | Phạm vi và ý nghĩa | Ví dụ |
|---|---|---|
| `client.id` | Nhãn nhận diện một Kafka client để quan sát, ghi log và áp dụng một số quota | `billing-consumer-pod-2` |
| `group.id` | Tên consumer group; các consumer cùng group phối hợp chia partition | `billing-v1` |
| `member.id` | ID thành viên consumer group do group coordinator quản lý trong quá trình tham gia group | Kafka cấp khi consumer gia nhập |
| `group.instance.id` | ID ổn định của một thành viên khi dùng static membership | `billing-pod-2` |
| `transactional.id` | Định danh producer dùng Kafka transaction và cơ chế fencing producer cũ | `billing-tx-pod-2` |
| Producer ID | ID nội bộ do Kafka cấp cho producer, liên quan đến idempotence và sequence | Kafka quản lý |
| Security principal | Danh tính được xác thực qua SASL hoặc TLS client authentication | `User:billing-service` |

Hai consumer có thể dùng cùng `group.id=billing-v1` để chia nhau partition, nhưng mỗi consumer nên có `client.id` riêng nếu cần quan sát từng instance. Ngược lại, hai consumer dùng hai group ID khác nhau sẽ có tiến độ đọc độc lập, dù chúng có thể dùng cùng một `client.id`.

`group.instance.id` cũng không phải `client.id`: static membership dùng ID ổn định để nhận diện thành viên trong group. Giá trị này phải duy nhất trong group; nếu hai consumer đang hoạt động cùng dùng một giá trị, chúng có thể fencing hoặc thay thế lẫn nhau. `client.id` không có vai trò điều phối thành viên như vậy.

Tương tự, `transactional.id` phục vụ giao dịch và fencing producer. Không dùng `client.id` thay cho `transactional.id`, và không chia sẻ một transactional ID giữa các producer độc lập đang chạy đồng thời.

## 3. Kafka sử dụng `client.id` ở đâu?

### Nhận diện request và log broker

Kafka protocol đưa client ID vào metadata của request. Broker có thể ghi client ID trong log hoặc thông tin chẩn đoán, giúp truy ngược request đến nhóm client tương ứng. Khi broker có nhiều kết nối, tên như `order-api-prod-consumer` dễ đọc hơn một ID tự sinh.

### Metrics của client và broker

Kafka client cung cấp nhiều metric có gắn nhãn client ID, chẳng hạn metric về request, tốc độ gửi/nhận, byte, lỗi và độ trễ. Metric cụ thể phụ thuộc loại client và phiên bản Kafka. Broker cũng có các metric request và thông tin quan sát có thể phân loại theo client ID.

Không phải mọi metric trong cluster đều có nhãn `client.id`. Việc đưa metric Kafka ra hệ thống giám sát còn phụ thuộc JMX, Micrometer hoặc exporter đang dùng. Khi cấu hình dashboard, hãy kiểm tra tag thực tế thay vì giả định mọi metric đều có cùng bộ nhãn.

### Client quota

Kafka hỗ trợ áp dụng một số quota theo client ID, theo user đã xác thực hoặc kết hợp các tiêu chí này. Ví dụ, broker có thể giới hạn tốc độ byte producer của nhóm client mang ID `bulk-importer` để luồng nhập dữ liệu không chiếm hết tài nguyên.

Quota theo `client.id` là cơ chế quản lý lưu lượng, không phải cơ chế xác thực. Một client có thể tự khai báo chuỗi client ID; nếu cần giới hạn theo danh tính đáng tin cậy, hãy kết hợp với xác thực và quota theo principal phù hợp.

### Theo dõi thành viên consumer group

Lệnh `kafka-consumer-groups.sh --describe` thường hiển thị cột `CLIENT-ID` cùng consumer ID, host và partition assignment. Nhờ đó, người vận hành có thể biết consumer instance nào đang giữ partition của group.

## 4. Cấu hình trong Spring Boot

Spring Boot bind các thuộc tính Kafka từ `application.yml` vào `KafkaProperties`, sau đó dùng chúng để tạo producer factory và consumer factory. Có thể đặt client ID riêng cho producer và consumer:

```yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092
    producer:
      client-id: order-api-prod-producer
    consumer:
      client-id: order-api-prod-consumer
      group-id: billing-v1
      auto-offset-reset: earliest
      enable-auto-commit: false
```

Trong cấu hình này:

- Producer được nhận diện là `order-api-prod-producer`.
- Consumer dùng `order-api-prod-consumer` làm client ID mặc định từ consumer factory.
- `group.id=billing-v1` xác định nhóm xử lý và tiến độ đọc chung.
- `auto-offset-reset` và `enable-auto-commit` điều khiển vị trí bắt đầu và cách xác nhận offset; chúng không được quyết định bởi client ID.

Tên thuộc tính cụ thể cần đối chiếu với phiên bản Spring Boot đang dùng. Khi tự tạo Kafka client hoặc factory thủ công, đặt cấu hình native Kafka bằng khóa `ProducerConfig.CLIENT_ID_CONFIG` hoặc `ConsumerConfig.CLIENT_ID_CONFIG`.

Ví dụ cấu hình producer và consumer bằng Java Kafka client:

```java
import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.producer.ProducerConfig;

Map<String, Object> producerProperties = new HashMap<>();
producerProperties.put(
        ProducerConfig.CLIENT_ID_CONFIG,
        "order-api-prod-producer"
);

Map<String, Object> consumerProperties = new HashMap<>();
consumerProperties.put(
        ConsumerConfig.CLIENT_ID_CONFIG,
        "order-api-prod-consumer"
);
```

Khi dùng Spring Boot auto-configuration, ưu tiên cấu hình bằng `spring.kafka.producer.client-id` và `spring.kafka.consumer.client-id`. Chỉ cần đặt trực tiếp trong map khi ứng dụng tự xây dựng client hoặc cần factory có cấu hình riêng.

## 5. Đặt client ID riêng cho từng `@KafkaListener`

Một ứng dụng có thể có nhiều listener cùng dùng một `ConsumerFactory`, nhưng mỗi luồng cần được nhận diện riêng. Spring Kafka cho phép đặt `clientIdPrefix` trên `@KafkaListener`:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class BillingListener {

    private final BillingService billingService;

    BillingListener(BillingService billingService) {
        this.billingService = billingService;
    }

    @KafkaListener(
            topics = "orders",
            groupId = "billing-v1",
            clientIdPrefix = "billing-orders"
    )
    public void onOrder(OrderCreated event) {
        billingService.process(event);
    }
}
```

Prefix trên giúp nhận diện consumer của listener xử lý topic `orders`. Nếu listener container chạy với concurrency lớn hơn 1, Spring Kafka thêm hậu tố cho từng consumer instance để các client ID không trùng nhau trong container. Ví dụ với concurrency bằng 3, các ID có dạng:

| Consumer instance | Client ID |
|---|---|
| Consumer 1 | `billing-orders-0` |
| Consumer 2 | `billing-orders-1` |
| Consumer 3 | `billing-orders-2` |

Khi dùng `clientIdPrefix`, prefix của listener được dùng cho các consumer thuộc listener đó và có thể ghi đè giá trị client ID mặc định từ consumer factory. Đây là cách phù hợp để phân biệt nhiều listener trong cùng ứng dụng. Nếu không cần nhận diện riêng, có thể để container dùng cấu hình mặc định của factory.

Concurrency chỉ tạo thêm consumer instance trong cùng container. Số partition mà group xử lý song song vẫn bị giới hạn bởi số partition được gán cho group; tăng concurrency không tạo thêm partition.

## 6. Quy ước đặt tên trong môi trường nhiều instance

Một quy ước hữu ích là:

```text
<application>-<environment>-<role>-<instance>
```

Ví dụ:

| Thành phần | Client ID |
|---|---|
| Producer của Order API ở production | `order-api-prod-producer` |
| Consumer billing ở pod 2 | `billing-prod-consumer-pod-2` |
| Listener projection trên pod 2 | `projection-prod-orders-pod-2` |
| Consumer import dữ liệu | `data-import-prod-consumer` |

Khi lựa chọn quy ước, lưu ý:

- Dùng tên ứng dụng và vai trò dễ hiểu; tránh tên chung như `client-1` hoặc `consumer`.
- Nếu cần truy vết từng replica, thêm pod name hoặc instance ID. Nếu chỉ cần phân biệt vai trò, có thể dùng một tên ổn định cho cả deployment.
- Giữ độ dài và số lượng biến thể hợp lý để dashboard, log và quota dễ quản lý.
- Không đưa user ID, email, access token hoặc dữ liệu nhạy cảm vào client ID.
- Không đưa order ID hoặc request ID vào client ID. Những giá trị thay đổi theo từng message sẽ tạo cardinality rất cao và làm metric khó sử dụng.
- Giữ tên nhất quán giữa môi trường; chỉ thay phần environment hoặc instance cần thiết.

Nếu chạy nhiều replica, hãy quyết định rõ có cần phân biệt từng replica hay không. ID chung cho một vai trò giúp gom metric; ID riêng cho từng pod giúp tìm instance có lỗi. Có thể dùng cả hai cấp: prefix theo ứng dụng và role, hậu tố theo pod hoặc consumer concurrency.

## 7. Quan sát client ID khi vận hành

### Xem client đang tham gia consumer group

Chạy lệnh sau để xem trạng thái một consumer group:

```bash
kafka-consumer-groups.sh --bootstrap-server kafka-1:9092 --group billing-v1 --describe
```

Kết quả có thể chứa các cột:

| Cột | Ý nghĩa |
|---|---|
| `CONSUMER-ID` | Định danh thành viên do Kafka quản lý |
| `HOST` | Địa chỉ host của consumer |
| `CLIENT-ID` | Client ID consumer đã khai báo |
| `#PARTITIONS` | Số partition đang được gán |
| `ASSIGNMENT` | Các partition được gán cho consumer |

Nếu group không có consumer hoạt động, lệnh có thể không hiển thị dòng thành viên. Khi đó hãy kiểm tra trạng thái group, log khởi động và cấu hình kết nối của ứng dụng.

### Kết hợp log ứng dụng và broker

Ở phía ứng dụng, nên ghi log tên service, vai trò client, group ID, topic, partition và offset tại các điểm khởi động hoặc xử lý lỗi. Ví dụ:

```java
log.info(
        "Kafka record received: topic={}, partition={}, offset={}",
        record.topic(),
        record.partition(),
        record.offset()
);
```

`ConsumerRecord` cung cấp topic, partition, offset và metadata của record; nó không phải nơi lấy `client.id`. Hãy ghi client ID đã cấu hình trong log khởi tạo hoặc thêm nó từ cấu hình ứng dụng vào logging context nếu cần đối chiếu. Không suy ra client ID từ offset hay key của record.

Ở phía broker, lọc log theo client ID giúp khoanh vùng kết nối, request timeout, lỗi xác thực hoặc request bất thường. Khi đọc log, đối chiếu thêm host, principal, thời điểm và group ID để tránh nhầm hai client có cùng tên.

### Dùng metric đúng mục đích

Metric client có thể giúp so sánh tốc độ gửi/nhận, request latency, lỗi và mức sử dụng mạng giữa các client ID. Với consumer, kết hợp metric client với consumer lag theo partition để phân biệt client đang đọc chậm với group chưa được gán partition.

Không nên chỉ dựa vào client ID để kết luận nguyên nhân. Một consumer có thể có client ID đúng nhưng vẫn không đọc được do ACL, group authorization, deserializer, rebalance hoặc broker không sẵn sàng.

## 8. client ID không phải cơ chế bảo mật

`client.id` do client khai báo và có thể được thay đổi bởi cấu hình ứng dụng. Vì vậy, không dùng nó làm bằng chứng xác thực hay phân quyền. Kafka xác thực client bằng cơ chế như SASL hoặc TLS client certificate; broker xác định principal sau khi xác thực. ACL quyết định principal có quyền đọc, ghi hoặc quản trị tài nguyên nào.

Ví dụ, hai ứng dụng có thể khai báo cùng `client.id=reporting-client` nhưng được xác thực bằng hai principal khác nhau. Broker vẫn phân biệt quyền dựa trên principal, không dựa vào chuỗi client ID. Ngược lại, một principal có thể tạo nhiều client ID để phân loại producer và consumer của cùng dịch vụ.

Nếu dùng quota theo client ID, hãy nhớ rằng các client cùng tên có thể cùng chịu một quota. Khi cần tách lưu lượng theo ứng dụng hoặc theo danh tính xác thực, hãy chọn entity quota và chính sách xác thực phù hợp với mô hình vận hành.

## 9. Những lỗi và nhầm lẫn thường gặp

| Hiện tượng hoặc suy nghĩ | Nguyên nhân hoặc thực tế | Hướng xử lý |
|---|---|---|
| Nhiều consumer trong group có cùng client ID | Cấu hình mặc định được dùng chung hoặc chưa đặt prefix riêng | Đặt client ID rõ ràng; dùng `clientIdPrefix` cho listener và concurrency |
| Đổi client ID nhưng consumer vẫn đọc cùng vị trí | Tiến độ đọc được lưu theo group ID, topic và partition | Kiểm tra `group.id` và committed offset; client ID không reset offset |
| Tạo client ID mới nhưng record vẫn được gửi vào partition cũ | Partitioning dựa trên key, partitioner và số partition | Kiểm tra key và partitioner; client ID không định tuyến record |
| Dùng client ID làm tên consumer group | Nhầm nhận diện client với tiến độ subscription | Đặt `group.id` theo luồng xử lý và chia sẻ giữa các consumer cần phối hợp |
| Dùng client ID làm danh tính bảo mật | Client ID là metadata do client khai báo | Dùng SASL/TLS principal và ACL |
| Dashboard có quá nhiều time series | Client ID thay đổi theo request hoặc message | Chỉ dùng nhãn có cardinality kiểm soát; không gắn ID nghiệp vụ vào client ID |
| Không tìm thấy client ID trong metric mong đợi | Metric đó không có tag client ID hoặc chưa export đúng | Kiểm tra JMX/Micrometer/exporter và tag thực tế |
| Quota áp dụng cho nhiều instance ngoài dự kiến | Nhiều client dùng cùng client ID và cùng khớp quota entity | Xem lại quy ước đặt tên và phạm vi quota |

## 10. Checklist thiết kế client ID

1. Đặt client ID riêng cho producer và consumer nếu cần phân biệt lưu lượng theo vai trò.
2. Đặt `clientIdPrefix` riêng cho listener quan trọng hoặc listener có concurrency.
3. Dùng `group.id` để mô tả luồng xử lý chung; không dùng client ID thay thế.
4. Chỉ dùng `group.instance.id` khi chủ động thiết kế static membership và bảo đảm tính duy nhất trong group.
5. Chỉ dùng `transactional.id` cho producer transaction theo quy tắc vòng đời và fencing.
6. Không xem client ID là danh tính bảo mật; cấu hình SASL/TLS và ACL riêng.
7. Kiểm tra client ID trong log broker, consumer group describe và hệ thống metric sau khi triển khai.
8. Giữ cardinality metric có kiểm soát và tránh nhúng dữ liệu nhạy cảm hoặc ID theo từng message.

`client.id` giúp Kafka và người vận hành nhận diện nguồn request ở mức client. Khi kết hợp tên client rõ ràng với group ID, principal và các metric phù hợp, nhóm phát triển có thể truy vết lưu lượng và sự cố chính xác hơn mà không nhầm lẫn giữa nhận diện client, tiến độ đọc và bảo mật.
