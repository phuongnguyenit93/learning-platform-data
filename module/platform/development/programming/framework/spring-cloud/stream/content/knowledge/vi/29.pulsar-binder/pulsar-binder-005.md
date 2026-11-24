# Tự cấp phát topic và cấu hình số partition

Spring Cloud Stream Pulsar Binder có **topic provisioner** để chuẩn bị topic khi ứng dụng tạo binding. Nếu topic chưa tồn tại, Pulsar có thể tự tạo một topic cơ bản không phân vùng khi client truy cập. Khi cần topic có nhiều partition, binder sử dụng `PulsarAdministration` để gọi Pulsar Admin API và tạo partitioned topic theo số lượng được cấu hình.

Hai thuộc tính quan trọng là `spring.cloud.stream.pulsar.binder.partition-count` và `spring.cloud.stream.pulsar.bindings.<binding-name>.producer|consumer.partition-count`. Thuộc tính cấp binder đặt số partition mặc định cho các topic do ứng dụng tạo; thuộc tính cấp binding cho phép mỗi luồng dữ liệu có số partition riêng. Để provision partitioned topic, ứng dụng cần kết nối được cả Pulsar broker lẫn endpoint quản trị Pulsar.

Bài thuộc chương **Pulsar Binder** của module `SPRING_CLOUD_STREAM`. Nội dung tập trung vào mô hình hàm `Supplier`/`Function`/`Consumer`, destination, tự cấp phát topic, tenant/namespace, partitioned topic, cấu hình partition count ở hai cấp, Pulsar Admin API, routing theo key, mở rộng consumer, thay đổi partition count và kiểm thử vận hành.

## 1. Topic trong Apache Pulsar

Topic là kênh lưu trữ và truyền message giữa producer và consumer. Tên đầy đủ của topic có cấu trúc:

```text
{persistent|non-persistent}://tenant/namespace/topic
```

Ví dụ:

```text
persistent://acme/orders/orders.created
```

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| `persistent` | Loại topic; message được lưu bền vững theo cơ chế lưu trữ Pulsar | `persistent` |
| `tenant` | Ranh giới đa thuê bao và quyền quản trị cấp cao | `acme` |
| `namespace` | Nhóm topic để áp dụng policy, quota và quyền | `orders` |
| `topic` | Tên luồng message trong namespace | `orders.created` |

Nếu không chỉ định loại topic, Pulsar thường mặc định là persistent. Topic non-persistent không lưu message bền vững trên BookKeeper như persistent topic. Với sự kiện nghiệp vụ cần lưu trữ và phục hồi, hãy chọn persistent topic trừ khi có lý do rõ ràng để dùng non-persistent.

Tenant và namespace là các đơn vị quản trị. Trong môi trường production, tenant/namespace thường được đội nền tảng tạo trước để gán quyền, retention, replication, backlog quota và policy. Không nên giả định việc tự tạo topic cũng sẽ tự tạo tenant và namespace còn thiếu.

## 2. Destination của Spring Cloud Stream liên kết với topic

Spring Cloud Stream dùng `destination` để chỉ ra topic mà binding sẽ đọc hoặc ghi. Tên function và binding là tên logic ở tầng ứng dụng; destination là tên topic trên Pulsar.

Ví dụ function producer:

```java
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderCreated(String eventId, String orderId, long total) {}

@Configuration
class OrderPublisherConfiguration {

    @Bean
    Supplier<OrderCreated> publishOrder() {
        return () -> new OrderCreated(
            "evt-1001",
            "order-1001",
            250000L
        );
    }
}
```

Binding mặc định của supplier là `publishOrder-out-0`. Cấu hình destination:

```yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: persistent://acme/orders/orders.created
```

Binder kết nối output binding với topic `persistent://acme/orders/orders.created`. Nếu không chỉ định destination, Spring Cloud Stream có thể dùng tên binding làm destination mặc định. Trong production nên đặt tên topic tường minh để dễ quản trị và tránh tạo nhầm topic.

Với function có input và output, mỗi binding có thể trỏ đến một destination riêng:

```yaml
spring:
  cloud:
    function:
      definition: enrichOrder
    stream:
      bindings:
        enrichOrder-in-0:
          destination: persistent://acme/orders/orders.created
        enrichOrder-out-0:
          destination: persistent://acme/orders/orders.enriched
```

## 3. Topic provisioner của Pulsar Binder

Pulsar Binder tích hợp topic provisioner để chuẩn bị tài nguyên mà binding cần. Khi ứng dụng khởi động và binding tham chiếu đến topic chưa có, provisioner có thể tạo topic theo cấu hình.

Cần phân biệt hai trường hợp:

1. **Topic không phân vùng:** Pulsar có thể tự tạo topic cơ bản khi producer/consumer truy cập một tên topic chưa tồn tại, nếu policy của broker/namespace cho phép.
2. **Partitioned topic:** cần metadata về số partition. Pulsar Binder dùng topic provisioner và Pulsar Admin API để tạo partitioned topic theo `partition-count`.

Nếu chỉ dựa vào việc client truy cập một topic chưa tồn tại, topic được tạo tự động có thể là topic không phân vùng. Muốn topic có nhiều partition, hãy cấu hình partition count để provisioner tạo đúng loại topic ngay từ đầu.

```text
Spring Cloud Stream binding
          |
          v
Pulsar Binder / Topic Provisioner
          |
          +---- topic chưa tồn tại, không yêu cầu partition
          |          |
          |          v
          |     topic cơ bản
          |
          +---- partition-count được cấu hình
                     |
                     v
               PulsarAdministration
                     |
                     v
               Pulsar Admin API
                     |
                     v
               partitioned topic
```

Việc provision cần quyền quản trị topic. Một ứng dụng có thể có quyền publish/consume nhưng không có quyền tạo topic. Khi đó hãy để pipeline hạ tầng tạo topic trước và cấp quyền runtime phù hợp cho ứng dụng.

## 4. Client URL và Admin URL là hai endpoint khác nhau

Pulsar client dùng giao thức Pulsar để gửi/nhận message. Pulsar Admin client dùng HTTP/HTTPS để thực hiện thao tác quản trị như tạo topic và partition metadata.

| Kết nối | Thuộc tính Spring Boot | Ví dụ |
|---|---|---|
| Pulsar broker/client | `spring.pulsar.client.service-url` | `pulsar://pulsar-broker:6650` |
| Pulsar Administration | `spring.pulsar.administration.service-url` trong một số phiên bản Spring for Apache Pulsar; `spring.pulsar.admin.service-url` trong các phiên bản Spring Boot/Spring Pulsar mới hơn | `http://pulsar-admin:8080` |

Ví dụ cấu hình:

```yaml
spring:
  pulsar:
    client:
      service-url: pulsar://pulsar-broker:6650
    administration:
      service-url: http://pulsar-admin:8080
```

Pulsar Binder dùng `PulsarAdministration` để provision partitioned topic. Nếu client URL đúng nhưng Admin URL sai hoặc không truy cập được, ứng dụng có thể kết nối broker nhưng thất bại khi tạo topic/partition. Hãy kiểm tra riêng DNS, port, TLS, authentication và quyền trên cả hai endpoint.

Tên property của Spring for Apache Pulsar có thể thay đổi theo phiên bản Spring Boot/Spring Pulsar đi kèm. Tài liệu Pulsar Binder có phiên bản dùng `spring.pulsar.administration.service-url`; property catalog của Spring Boot mới hơn dùng `spring.pulsar.admin.service-url`. Nếu dự án dùng namespace mới, phần cấu hình tương ứng là:

```yaml
spring:
  pulsar:
    admin:
      service-url: http://pulsar-admin:8080
```

Đối chiếu property metadata của release train dự án trước khi triển khai; không khai báo cả hai tên với giá trị khác nhau hoặc sao chép nguyên xi cấu hình Admin URL từ một phiên bản khác.

## 5. Cấu hình partition count ở cấp binder

Thuộc tính:

```text
spring.cloud.stream.pulsar.binder.partition-count
```

đặt số partition mặc định cho các topic mà ứng dụng tạo thông qua Pulsar Binder. Ví dụ:

```yaml
spring:
  cloud:
    stream:
      pulsar:
        binder:
          partition-count: 6
```

Với cấu hình này, các topic được provision bởi ứng dụng sẽ kế thừa số partition là sáu, trừ khi binding cụ thể có cấu hình partition count riêng. Cấu hình cấp binder hữu ích khi các luồng trong ứng dụng có yêu cầu throughput và concurrency gần giống nhau.

Không hiểu `partition-count` cấp binder là số consumer, số subscription hay số replica ứng dụng. Đây là số partition của topic được provision.

## 6. Cấu hình partition count theo từng binding

Khi các topic có tải khác nhau, có thể cấu hình partition count riêng cho từng binding. Mẫu thuộc tính:

```text
spring.cloud.stream.pulsar.bindings.<binding-name>.producer.partition-count
spring.cloud.stream.pulsar.bindings.<binding-name>.consumer.partition-count
```

Ví dụ:

```yaml
spring:
  cloud:
    function:
      definition: publishOrder;publishAudit
    stream:
      bindings:
        publishOrder-out-0:
          destination: persistent://acme/orders/orders.created
        publishAudit-out-0:
          destination: persistent://acme/audit/audit.events
      pulsar:
        bindings:
          publishOrder-out-0:
            producer:
              partition-count: 12
          publishAudit-out-0:
            producer:
              partition-count: 3
```

Trong ví dụ, topic đơn hàng được provision với 12 partition, còn topic audit được provision với 3 partition. Số lượng khác nhau phản ánh tải và yêu cầu mở rộng riêng của từng luồng.

Có thể đặt thuộc tính tương ứng ở consumer binding khi binding đó là nơi provision topic. Ví dụ:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processPayment-in-0:
          destination: persistent://acme/payments/payment.events
      pulsar:
        bindings:
          processPayment-in-0:
            consumer:
              partition-count: 8
```

Nếu producer và consumer cùng tham chiếu một topic, hãy thống nhất số partition giữa hai phía. Tránh để hai binding cùng provision một destination nhưng khai báo số partition mâu thuẫn.

## 7. Thứ tự ưu tiên của cấu hình

Pulsar Binder áp dụng cấu hình theo thứ tự ưu tiên từ cao xuống thấp:

1. Extended binding properties: `spring.cloud.stream.pulsar.bindings.<binding-name>...`
2. Binder-level properties: `spring.cloud.stream.pulsar.binder...`
3. Spring Boot Pulsar properties: `spring.pulsar...`

Ví dụ binder đặt sáu partition mặc định nhưng binding `publishOrder-out-0` đặt riêng 12 partition:

```yaml
spring:
  cloud:
    stream:
      pulsar:
        binder:
          partition-count: 6
        bindings:
          publishOrder-out-0:
            producer:
              partition-count: 12
```

Binding `publishOrder-out-0` dùng cấu hình cụ thể 12; các topic khác do binder tạo có thể kế thừa giá trị cấp binder là sáu. Quy tắc ưu tiên này giúp một ứng dụng có thể quản lý nhiều function với yêu cầu partition khác nhau.

## 8. Cấu hình hoàn chỉnh cho producer và consumer

Ví dụ ứng dụng vừa phát sự kiện đơn hàng, vừa xử lý sự kiện đó:

```yaml
spring:
  pulsar:
    client:
      service-url: pulsar://pulsar-broker:6650
    administration:
      service-url: http://pulsar-admin:8080
  cloud:
    function:
      definition: publishOrder;processOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: persistent://acme/orders/orders.created
        processOrder-in-0:
          destination: persistent://acme/orders/orders.created
          group: order-processing
      pulsar:
        binder:
          partition-count: 6
```

Trong cấu hình này:

- `publishOrder-out-0` là output binding của supplier.
- `processOrder-in-0` là input binding của consumer.
- Cả hai cùng tham chiếu một destination.
- Pulsar client URL kết nối broker để publish/consume.
- Admin URL cho phép topic provisioner thực hiện thao tác quản trị.
- Binder-level partition count đặt sáu partition cho topic được tạo.

Tên `group` trong cấu hình Spring Cloud Stream là tên consumer group logic. Với Pulsar, cần xem cách binder ánh xạ group sang subscription name theo phiên bản binder. Không coi group là tên tenant, namespace hay partition.

## 9. Tạo partitioned topic bằng Pulsar Admin CLI

Nếu tổ chức quản lý topic bên ngoài ứng dụng, có thể tạo partitioned topic trước bằng Pulsar Admin CLI:

```bash
pulsar-admin topics create-partitioned-topic \
  persistent://acme/orders/orders.created \
  --partitions 6
```

Trước đó, tenant và namespace phải tồn tại:

```bash
pulsar-admin tenants list
pulsar-admin namespaces list acme
```

Nếu namespace `acme/orders` chưa tồn tại và tài khoản có quyền quản trị, tạo namespace theo quy trình hạ tầng:

```bash
pulsar-admin namespaces create acme/orders
```

Kiểm tra metadata partition count:

```bash
pulsar-admin topics get-partitioned-topic-metadata \
  persistent://acme/orders/orders.created
```

Kết quả cần thể hiện số partition đã khai báo. Các lệnh CLI cần quyền quản trị phù hợp và phải chạy với cấu hình kết nối/authentication đúng cluster.

## 10. Partitioned topic được triển khai như thế nào?

Một partitioned topic là một topic logic được triển khai thành nhiều partition nội bộ. Nếu topic `orders.created` có sáu partition, Pulsar quản lý các partition riêng và phân phối chúng trên các broker phù hợp.

```text
Logical topic:
persistent://acme/orders/orders.created
                 |
                 +---- partition 0
                 +---- partition 1
                 +---- partition 2
                 +---- partition 3
                 +---- partition 4
                 +---- partition 5
```

Producer và consumer thường làm việc với tên topic logic. Pulsar client tra cứu metadata và kết nối đến các partition tương ứng. Ứng dụng không cần tự tạo sáu tên topic nghiệp vụ độc lập.

Partition cho phép topic phân phối tải qua nhiều broker và tăng khả năng xử lý song song. Số partition cũng ảnh hưởng số producer/consumer connection, metadata, ledger và công việc quản trị.

## 11. Số partition và khả năng mở rộng

Partition count đặt giới hạn cho mức song song có thể đạt được ở cấp topic, nhưng không tự quyết định số consumer. Số consumer thực tế còn phụ thuộc subscription type, số consumer đăng ký và cách Pulsar phân phối partition.

Ví dụ:

| Cấu trúc topic | Consumer instance | Nhận xét |
|---:|---:|---|
| Topic không phân vùng | 1 | Không có các partition nội bộ để mở rộng song song ở cấp topic |
| 6 | 1 | Một consumer có thể đọc nhiều partition |
| 6 | 3 | Subscription phù hợp có thể phân phối partition cho nhiều consumer |
| 6 | 10 | Không có nghĩa cả 10 consumer đều có partition riêng; một số có thể không nhận partition tùy subscription type |
| 12 | 3 | Có nhiều partition hơn để phân phối, nhưng cần đo tải và broker capacity |

Đây là ví dụ định hướng, không phải quy tắc gán partition cố định cho mọi subscription. Với `Exclusive`, `Shared`, `Failover` và `Key_Shared`, cách phân phối message và partition khác nhau.

## 12. Partition count không thay thế routing key

Partition count xác định số partition của topic. Routing mode và message key quyết định message được gửi vào partition nào.

Pulsar có các chế độ routing phổ biến:

| Routing mode | Khi không có key | Khi có key |
|---|---|---|
| `RoundRobinPartition` | Phân phối luân phiên giữa các partition theo batch/nhịp routing | Hash key để chọn partition tương ứng |
| `SinglePartition` | Chọn một partition cho producer và gửi các message không key vào đó | Hash key để chọn partition tương ứng |
| `CustomPartition` | Dùng message router tùy chỉnh | Logic router quyết định partition |

`RoundRobinPartition` thường là chế độ mặc định của Pulsar producer. Khi cần giữ các message cùng aggregate trên cùng partition, hãy gửi key ổn định như `orderId` hoặc `accountId` và dùng routing mode hỗ trợ key routing.

Nếu message không có key, round-robin có thể tối ưu phân phối tải nhưng không tạo bảo đảm thứ tự theo aggregate. Nếu tất cả message dùng cùng một key nóng, chúng có thể tập trung vào một partition và làm giảm hiệu quả mở rộng.

Lưu ý: `partition-count` của Pulsar Binder là cấu hình provision số partition. Việc chọn key/routing mode là cấu hình gửi message ở tầng producer. Hai cấu hình có liên quan nhưng không phải một thuộc tính duy nhất.

## 13. Partitioning và subscription type

Pulsar tách quyết định producer định tuyến message vào partition nào khỏi quyết định subscription phân phối message cho consumer nào.

| Subscription type | Mô hình tiêu thụ |
|---|---|
| `Exclusive` | Một consumer duy nhất gắn vào subscription |
| `Shared` | Nhiều consumer cùng subscription chia sẻ message; thứ tự toàn cục không được bảo đảm |
| `Failover` | Nhiều consumer có thể đăng ký nhưng broker chọn consumer active theo topic/partition và chuyển vai trò khi cần |
| `Key_Shared` | Phân phối message theo key để message cùng key được gắn với consumer tương ứng theo semantics của subscription |

Partitioned topic có thể kết hợp với các subscription type này. Nếu mục tiêu là throughput, xem xét partition count và `Shared`/`Key_Shared`. Nếu cần active/standby, xem xét `Failover`. Nếu cần thứ tự theo key, phải thiết kế message key, routing mode, subscription type và batching tương thích.

Không tăng partition count chỉ để có thêm consumer nếu subscription đang dùng không phân phối tải theo cách mong muốn. Hãy kiểm tra semantics của subscription trước.

## 14. Chọn số partition ban đầu

Không có một số partition đúng cho mọi topic. Cần dựa trên throughput mục tiêu, kích thước message, key distribution, số consumer, broker capacity và chi phí quản trị.

Một quy trình ước lượng:

1. Đo hoặc ước tính số message/giây và kích thước payload.
2. Benchmark throughput ổn định của một partition với message và cấu hình producer/consumer tương tự production.
3. Ước lượng số partition cần thiết để đạt throughput mục tiêu, cộng biên dự phòng hợp lý.
4. Kiểm tra số broker, namespace bundle, storage và network có thể đáp ứng.
5. Đánh giá số consumer và subscription type dự kiến.
6. Kiểm tra phân bố key để tránh hot partition.
7. Kiểm thử tải và failover trước khi chốt production.

Ví dụ minh họa: nếu một partition xử lý ổn định khoảng 2.000 message/giây trong workload thực tế và topic cần 10.000 message/giây, sáu partition có thể là điểm bắt đầu để benchmark. Đây chỉ là giả định đo tải; không dùng con số minh họa thay cho benchmark trên cluster thực.

Tăng partition count làm tăng số partition nội bộ, metadata, producer/consumer connection và công việc quản trị. Chọn quá nhiều partition ngay từ đầu có thể làm tăng chi phí mà không tạo thêm throughput nếu producer, consumer hoặc broker đang là nút thắt khác.

## 15. Tác động khi tăng partition count

Apache Pulsar hỗ trợ tăng số partition của partitioned topic. Có thể cập nhật bằng lệnh:

```bash
pulsar-admin topics update-partitioned-topic \
  persistent://acme/orders/orders.created \
  --partitions 12
```

Pulsar hỗ trợ tăng số partition; không hỗ trợ giảm số partition theo cách cập nhật thông thường. Muốn giảm số partition hoặc thay đổi cấu trúc lớn, cần tạo topic mới và thực hiện migration.

Khi tăng partition count, producer và consumer có thể phát hiện partition mới thông qua metadata. Tuy nhiên, cần đánh giá:

- Tải mới được phân phối lên partition như thế nào.
- Key có thể được hash sang partition khác khi modulus thay đổi.
- Thứ tự theo key trong giai đoạn chuyển đổi.
- Consumer/subscription có cần rebalance hoặc reconnect không.
- Số broker, storage và network có đủ năng lực không.
- Downstream có giả định số partition cố định không.

Nếu yêu cầu thứ tự nghiệp vụ nghiêm ngặt theo key, hãy kiểm thử hành vi trước và sau khi tăng partition. Các message cùng key được publish trước và sau thay đổi có thể không còn nằm cùng một partition nếu cách tính partition thay đổi.

## 16. Không tự chuyển topic thường thành partitioned topic

Nếu topic đã được tạo dưới dạng không phân vùng, không nên giả định chỉ thêm `partition-count` vào YAML là binder tự chuyển đổi topic hiện tại thành partitioned topic. Provisioner không thể tùy ý thay đổi loại tài nguyên đã tồn tại.

Với topic đã tồn tại, cần kiểm tra metadata trước khi triển khai. Nếu cần chuyển sang partitioned topic, cách an toàn thường là:

1. Tạo topic mới với tên mới và partition count mong muốn.
2. Cập nhật producer để phát dữ liệu sang topic mới hoặc dual-publish có kiểm soát.
3. Chạy consumer mới và xác minh dữ liệu.
4. Backfill/replay dữ liệu cũ nếu yêu cầu nghiệp vụ cần.
5. Chuyển downstream consumer sang topic mới.
6. Dừng ghi topic cũ sau khi xác nhận migration.
7. Chỉ xóa topic cũ theo quy trình retention và audit.

Không xóa topic hiện hữu để ép binder tạo lại khi topic còn message chưa xử lý hoặc subscription đang sử dụng.

## 17. Provisioning tự động và provisioning do hạ tầng quản lý

Có hai cách tổ chức provisioning:

| Cách làm | Phù hợp khi | Trách nhiệm |
|---|---|---|
| Binder tự provision | Development, test hoặc môi trường cho phép ứng dụng tạo topic | Ứng dụng cần Admin URL và quyền tạo topic/partition |
| Hạ tầng provision trước | Production có quy trình quản lý topic, ACL và policy tập trung | Platform team tạo tenant/namespace/topic; ứng dụng dùng quyền runtime |

Với production, topic thường cần policy về retention, backlog quota, message TTL, replication, schema và quyền truy cập. Nếu binder tự tạo topic nhưng policy không được áp dụng đúng, topic có thể chạy với cấu hình mặc định không phù hợp.

Có thể dùng binder provisioner trong lúc phát triển và chuyển sang quản lý hạ tầng trước production. Khi đó, hãy bảo đảm tên destination và partition count trong ứng dụng khớp với tài nguyên được provision.

## 18. Quyền cần thiết để tự cấp phát topic

Pulsar client và Pulsar Admin API có thể sử dụng các quyền khác nhau. Khi binder tự provision partitioned topic, principal cần quyền quản trị phù hợp trên tenant/namespace hoặc topic theo chính sách cluster.

Kiểm tra:

- Tenant đã tồn tại.
- Namespace đã tồn tại.
- Admin endpoint có thể truy cập từ ứng dụng.
- Admin principal được phép tạo topic và partition trong namespace.
- Client principal có quyền publish/consume sau khi topic được tạo.
- Authentication và TLS được cấu hình cho cả client và admin.
- Policy namespace không chặn auto topic creation hoặc partitioned topic creation.

Không cấp quyền quản trị toàn cluster cho ứng dụng chỉ để tạo một topic. Nếu tổ chức không cho ứng dụng tự tạo tài nguyên, hãy provision bằng pipeline hạ tầng và cấp quyền runtime tối thiểu.

## 19. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Topic được tạo nhưng không có partition | Chỉ có cơ chế auto topic creation cơ bản; chưa cấu hình partition count | Cấu hình `spring.cloud.stream.pulsar.binder.partition-count` hoặc per-binding partition count |
| Ứng dụng kết nối broker nhưng provision partition thất bại | Admin URL sai hoặc không truy cập được | Kiểm tra Pulsar Administration endpoint riêng với client URL |
| Không tạo được topic | Tenant/namespace chưa tồn tại hoặc thiếu quyền | Provision tenant/namespace và cấp quyền phù hợp |
| Tất cả topic có cùng số partition ngoài ý muốn | Dùng partition count cấp binder cho mọi topic | Chuyển sang cấu hình per-binding cho các topic có tải khác nhau |
| Một topic có count không như mong đợi | Cấu hình per-binding ghi đè binder-level | Kiểm tra thứ tự ưu tiên và binding name |
| Producer/consumer không dùng cùng topic | Destination khác nhau hoặc dùng short name/FQ name không nhất quán | Chuẩn hóa destination đầy đủ |
| Tăng partition nhưng thứ tự theo key thay đổi | Key có thể được hash sang partition khác sau khi tăng count | Lập kế hoạch migration và kiểm thử ordering |
| Consumer không tăng throughput | Subscription type hoặc số consumer không phù hợp | Kiểm tra Shared/Key_Shared/Failover và consumer assignment |
| Topic cũ không trở thành partitioned | Topic hiện hữu là non-partitioned | Tạo topic mới và migrate có kiểm soát |
| Auto provisioning thất bại khi production | Principal runtime không có quyền Admin API | Provision trước bằng hạ tầng hoặc cấp quyền tối thiểu |

## 20. Kiểm tra topic và partition sau khi provision

Sau khi ứng dụng khởi động, kiểm tra metadata topic bằng Pulsar Admin CLI:

```bash
pulsar-admin topics get-partitioned-topic-metadata \
  persistent://acme/orders/orders.created
```

Liệt kê topic trong namespace:

```bash
pulsar-admin topics list acme/orders
```

Xem thống kê topic:

```bash
pulsar-admin topics stats \
  persistent://acme/orders/orders.created
```

Kiểm tra số partition thực tế, producer/consumer đang kết nối, backlog và tốc độ message. Không chỉ dựa vào việc Spring Boot khởi động thành công để kết luận topic có đúng partition count.

## 21. Kiểm thử tự cấp phát và partition count

Một bộ integration test nên xác minh cả cấu hình binder lẫn metadata trên Pulsar thật hoặc môi trường test tương thích:

| Kịch bản | Cách kiểm thử | Kết quả cần xác minh |
|---|---|---|
| Topic chưa tồn tại | Khởi động binding với destination mới | Topic được tạo theo cơ chế provisioner/policy |
| Topic không partition | Không đặt partition count | Xác minh topic cơ bản được tạo theo cấu hình môi trường |
| Binder-level count | Đặt `binder.partition-count: 6` | Topic do ứng dụng tạo kế thừa sáu partition |
| Binding-level count | Đặt producer partition count là 12 | Binding cụ thể tạo topic với 12 partition |
| Hai binding khác nhau | Một topic 12 partition, một topic 3 partition | Mỗi topic có count đúng cấu hình riêng |
| Binding override | Binder count 6, binding count 12 | Binding dùng giá trị cụ thể theo precedence |
| Admin URL sai | Cấu hình sai endpoint quản trị | Lỗi provisioning được phát hiện rõ ràng |
| Thiếu quyền Admin | Thu hồi quyền tạo topic | Provisioning thất bại và được quan sát |
| Namespace chưa tồn tại | Dùng destination trong namespace chưa provision | Kiểm tra lỗi namespace và quy trình tạo namespace |
| Topic đã tồn tại không partition | Thêm partition count vào cấu hình | Xác minh binder không âm thầm chuyển đổi loại topic |
| Tăng partition | Tăng từ 6 lên 12 bằng Admin API | Metadata phản ánh số partition mới; consumer/producer phát hiện đúng |
| Routing theo key | Gửi nhiều message cùng key | Message cùng key đi cùng partition theo routing mode phù hợp |
| Consumer scaling | Chạy nhiều consumer với subscription type đã chọn | Xác minh phân phối partition/message và throughput |

Test binder có thể kiểm tra function và binding ở tầng Spring, nhưng không thay thế integration test cho Pulsar Admin API, topic metadata, partition routing và subscription behavior.

## 22. Theo dõi trong production

Các chỉ số nên theo dõi:

- Số topic được provision theo tenant/namespace.
- Partition count thực tế của từng topic.
- Tốc độ publish và consume theo partition.
- Phân bố message/key giữa các partition.
- Producer latency, send failure và pending messages.
- Consumer backlog, redelivery và subscription state.
- Broker ownership, storage usage và network throughput.
- Lỗi Admin API, lỗi authentication/authorization và provisioning.
- Thay đổi partition metadata sau mỗi lần deploy.

Đặt cảnh báo khi topic không có partition như mong đợi, một partition có tải vượt trội, backlog tăng kéo dài hoặc binder không thể truy cập Admin API. Log nên có binding name, destination đầy đủ, partition count dự kiến và lỗi provisioning; không ghi credential hoặc token.

## 23. Quy trình cấu hình topic và partition

Khi triển khai Pulsar Binder:

1. Chọn tenant và namespace đã được provision.
2. Đặt destination đầy đủ theo `persistent://tenant/namespace/topic` hoặc loại topic phù hợp.
3. Quyết định topic sẽ được binder tự tạo hay do hạ tầng provision trước.
4. Cấu hình Pulsar client service URL.
5. Nếu binder cần tạo partitioned topic, cấu hình Admin service URL và quyền quản trị tương ứng.
6. Chọn partition count mặc định ở cấp binder nếu các topic có yêu cầu tương tự.
7. Dùng partition count cấp binding cho topic có yêu cầu throughput khác nhau.
8. Chọn routing mode và message key theo yêu cầu phân phối tải/thứ tự.
9. Chọn subscription type và số consumer theo mô hình xử lý.
10. Kiểm tra topic metadata sau khi provision.
11. Kiểm thử publish, consume, routing theo key, tăng partition và failover.
12. Theo dõi partition-level throughput, backlog, Admin API và broker capacity.

## 24. Tự kiểm tra

- [ ] Giải thích được topic name gồm loại topic, tenant, namespace và tên topic.
- [ ] Phân biệt tự tạo topic cơ bản với provision partitioned topic.
- [ ] Giải thích được vai trò của Pulsar Topic Provisioner và `PulsarAdministration`.
- [ ] Phân biệt Pulsar client service URL với Admin service URL.
- [ ] Cấu hình được `spring.cloud.stream.pulsar.binder.partition-count`.
- [ ] Cấu hình được partition count riêng theo producer/consumer binding.
- [ ] Giải thích được thứ tự ưu tiên giữa extended binding, binder và Spring Boot properties.
- [ ] Tạo được partitioned topic bằng Pulsar Admin CLI.
- [ ] Phân biệt partition count với số consumer và subscription type.
- [ ] Giải thích được routing mode và vai trò của message key.
- [ ] Biết partition count có thể tăng nhưng không giảm theo thao tác cập nhật thông thường.
- [ ] Lập được kế hoạch migration khi topic thường cần chuyển sang partitioned topic.
- [ ] Kiểm tra được topic metadata, quyền provisioning và partition-level metrics.

## Kết luận

Pulsar Binder có topic provisioner để tạo topic cần thiết cho các binding. Topic cơ bản có thể được tạo tự động khi truy cập, còn partitioned topic cần provisioner sử dụng Pulsar Admin API với số partition được chỉ định. Dùng `spring.cloud.stream.pulsar.binder.partition-count` cho mặc định toàn ứng dụng và `spring.cloud.stream.pulsar.bindings.<binding-name>.producer|consumer.partition-count` để điều chỉnh từng binding. Việc provision partitioned topic cần Admin URL, tenant/namespace và quyền quản trị phù hợp. Partition count quyết định cấu trúc song song của topic; routing mode/message key và subscription type quyết định cách message được phân phối. Hãy kiểm tra metadata sau khi tạo, benchmark số partition và lập kế hoạch migration trước khi thay đổi topic production.

## Tài liệu tham khảo

- Spring Cloud Stream Pulsar Binder: https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html
- Apache Pulsar, quản lý topic và partitioned topic: https://pulsar.apache.org/docs/4.2.x/admin-api-topics/
- Apache Pulsar, topic, partition, routing mode và subscription: https://pulsar.apache.org/docs/4.2.x/concepts-messaging/
- Spring Boot, kết nối Pulsar client và administration: https://docs.spring.io/spring-boot/4.0/reference/messaging/pulsar.html
