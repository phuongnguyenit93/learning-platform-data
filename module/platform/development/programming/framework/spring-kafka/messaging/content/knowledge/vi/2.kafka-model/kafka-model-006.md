# Replication và tính sẵn sàng

## 1. Vì sao Kafka cần replication?

Kafka lưu dữ liệu trong các partition. Nếu một partition chỉ có một bản sao và broker đang giữ partition đó bị hỏng, partition sẽ không thể phục vụ đọc/ghi cho đến khi broker phục hồi. Điều này tạo ra điểm lỗi đơn (*single point of failure*) và có thể làm gián đoạn cả luồng sự kiện.

**Replication** là cơ chế duy trì nhiều bản sao của một partition trên các broker khác nhau. Khi một broker gặp sự cố, Kafka có thể chọn một bản sao còn đủ điều kiện làm leader mới để partition tiếp tục hoạt động. Replication vì vậy góp phần tăng khả năng sẵn sàng (*availability*) và độ bền dữ liệu (*durability*).

Trong module Spring Kafka Messaging, producer gửi sự kiện qua `KafkaTemplate`, consumer nhận sự kiện qua `@KafkaListener`. Các API Spring Kafka giúp ứng dụng giao tiếp với cụm Kafka; khả năng chịu lỗi của dữ liệu phía broker lại phụ thuộc vào replication factor, ISR, cấu hình producer và cách triển khai cụm.

## 2. Leader và follower replica

Mỗi partition có một hoặc nhiều replica. Tại một thời điểm, một replica giữ vai trò **leader**; các replica còn lại là **follower**.

- Producer gửi record đến leader của partition đích.
- Consumer thông thường đọc record từ leader.
- Follower chủ động fetch dữ liệu từ leader để cập nhật bản sao log của mình.
- Khi leader gặp sự cố, Kafka điều phối bầu chọn một replica đủ điều kiện làm leader mới.

Ví dụ, topic `orders` có partition `orders-0` với replication factor bằng 3:

```text
                    ghi record
Producer ------------------------------> Broker A
                                         Leader orders-0
                                              |
                             follower fetch   |   follower fetch
                                  +-----------+-----------+
                                  |                       |
                                  v                       v
                              Broker B                Broker C
                              Follower                Follower
```

Ba replica là ba bản sao của **cùng một partition**, không phải ba partition khác nhau. Broker A, B và C có thể đồng thời giữ replica của những partition khác; Kafka phân bố leader và replica để phân tán tải.

### Replication factor

Replication factor (RF) là số replica được cấu hình cho mỗi partition, bao gồm cả leader. Ví dụ:

| Replication factor | Số bản sao mỗi partition | Ý nghĩa vận hành |
|---:|---:|---|
| 1 | 1 | Không có bản sao dự phòng; broker chứa replica lỗi có thể làm partition mất khả năng phục vụ |
| 2 | 2 | Có một bản sao dự phòng; khả năng chịu lỗi và mức dự phòng thấp hơn RF=3 |
| 3 | 3 | Có thể duy trì một bản sao khác khi một broker chứa replica gặp sự cố, nếu các điều kiện ISR và cấu hình ghi phù hợp |

RF phải nhỏ hơn hoặc bằng số broker có thể nhận replica. RF=3 không có nghĩa mọi record được ghi ba lần bởi producer; producer chỉ gửi đến leader, còn Kafka sao chép record sang follower.

## 3. ISR và điều kiện một replica được tham gia bầu chọn

**ISR (In-Sync Replicas)** là tập các replica đang theo kịp leader theo tiêu chí đồng bộ của Kafka. ISR luôn bao gồm leader hiện tại. Follower cần fetch dữ liệu đủ thường xuyên để tiếp tục nằm trong tập này; replica tụt lại quá lâu có thể bị loại khỏi ISR và được thêm lại khi bắt kịp.

Giả sử partition có RF=3:

| Replica | Broker | Trạng thái | Có trong ISR? |
|---|---|---|---|
| Replica 0 | A | Leader | Có |
| Replica 1 | B | Follower, theo kịp leader | Có |
| Replica 2 | C | Follower, đang tụt lại | Có thể đã bị loại |

Nếu ISR hiện tại là `{A, B}`, Kafka xem A và B là các bản sao đủ điều kiện theo kịp để phục vụ cơ chế ghi và bầu chọn leader. Replica C không nằm trong ISR thì không được xem là bản sao an toàn tương đương tại thời điểm đó.

ISR thay đổi theo tình trạng broker và tốc độ đồng bộ. Vì thế, không nên chỉ nhìn RF để kết luận một partition đang có bao nhiêu bản sao an toàn. Cần theo dõi cả số replica thực tế, ISR và trạng thái leader.

### High watermark

Kafka dùng **high watermark** để đánh dấu ranh giới dữ liệu đã được các replica trong ISR đồng bộ. Consumer chỉ đọc được các record đã vượt qua điều kiện hiển thị theo high watermark; điều này tránh việc consumer thông thường đọc một record mới chỉ tồn tại trên leader rồi sau đó record biến mất khi leader lỗi.

High watermark không phải offset đã commit của consumer. High watermark phản ánh tiến độ sao chép của partition; committed offset phản ánh tiến độ đọc mà consumer group đã lưu. Hai khái niệm phục vụ hai mục đích khác nhau.

## 4. Leader election và xử lý khi broker gặp sự cố

Khi broker đang giữ leader bị mất kết nối hoặc dừng, controller của Kafka phát hiện sự cố và điều phối việc chọn leader mới. Một replica còn hoạt động trong ISR có thể được chọn làm leader. Sau khi chuyển vai trò, producer và consumer tiếp tục làm việc với leader mới thông qua metadata cập nhật từ cụm.

Ví dụ với RF=3 và ISR ban đầu `{A, B, C}`:

1. Broker A đang giữ leader của partition.
2. Broker A gặp sự cố.
3. Kafka chọn B hoặc C, là replica còn trong ISR, làm leader mới.
4. Client cập nhật metadata và gửi yêu cầu đến leader mới.
5. Khi A phục hồi, replica của A đồng bộ lại và có thể tham gia ISR.

Việc bầu chọn có thể gây một khoảng gián đoạn ngắn. Ứng dụng cần cấu hình timeout, retry và xử lý lỗi phù hợp; không nên giả định mọi lần gửi đều thành công ngay lập tức khi broker thay đổi.

### Unclean leader election

Trong điều kiện bình thường, Kafka ưu tiên chọn leader mới từ ISR. Cấu hình `unclean.leader.election.enable` quyết định có cho phép chọn một replica không nằm trong ISR khi không còn replica ISR khả dụng hay không.

- Nếu không cho phép unclean election, partition có thể tạm thời không khả dụng khi không còn replica ISR nào có thể làm leader. Cách này ưu tiên bảo toàn dữ liệu đã được đồng bộ.
- Nếu cho phép unclean election, một replica tụt hậu có thể được chọn để khôi phục phục vụ. Những record chưa kịp sao chép sang replica đó có thể bị mất.

Đây là lựa chọn giữa khả năng phục vụ và nguy cơ mất dữ liệu. Với luồng nghiệp vụ quan trọng, cần hiểu rõ hậu quả trước khi bật unclean election; không nên bật chỉ để giảm thời gian partition offline.

## 5. Kết hợp replication với acks và min.insync.replicas

Replication factor quyết định số replica được duy trì. Cấu hình `acks` của producer quyết định mức xác nhận cần nhận khi ghi; `min.insync.replicas` đặt ngưỡng ISR tối thiểu để broker chấp nhận một yêu cầu ghi với `acks=all`.

### Các chế độ acks

| Giá trị | Producer nhận xác nhận khi nào? | Đánh đổi |
|---|---|---|
| `0` | Không chờ broker xác nhận | Độ trễ thấp nhưng producer không biết broker đã nhận record hay chưa |
| `1` | Leader xác nhận sau khi ghi record vào log cục bộ | Nhanh hơn; record có thể mất nếu leader lỗi trước khi follower sao chép |
| `all` (`-1`) | Leader chờ các replica hiện có trong ISR xác nhận theo giao thức replication | Mức bảo đảm cao hơn; có thể từ chối ghi nếu ISR thấp hơn ngưỡng tối thiểu |

`acks=all` không đồng nghĩa luôn chờ đủ toàn bộ RF. Nó chờ các replica đang thuộc ISR. Nếu RF=3 nhưng chỉ còn một replica trong ISR, `acks=all` một mình vẫn có thể cho phép ghi qua replica đó. Đây là lý do cần kết hợp `min.insync.replicas`.

### Ví dụ RF=3 và min.insync.replicas=2

Giả sử topic có RF=3 và `min.insync.replicas=2`, producer dùng `acks=all`:

- Khi ISR có 3 replica, broker có thể chấp nhận ghi và chờ xác nhận từ các replica trong ISR.
- Khi một replica lỗi và ISR còn 2, broker vẫn có thể chấp nhận ghi. Cụm còn khả năng chịu thêm một lần gián đoạn ngắn tùy trạng thái leader và replica.
- Khi ISR chỉ còn 1, broker từ chối ghi yêu cầu `acks=all` vì không đạt ngưỡng 2. Ứng dụng nhận lỗi thay vì âm thầm ghi với mức dự phòng thấp hơn cấu hình.

Như vậy, RF=3 kết hợp `min.insync.replicas=2` thường được dùng để tiếp tục ghi khi mất một replica mà vẫn yêu cầu ít nhất hai bản sao trong ISR tham gia xác nhận. Kết quả thực tế còn phụ thuộc replica nằm trên broker/rack nào, ISR tại thời điểm ghi và tình trạng leader election.

## 6. Cấu hình replication cho topic

Replication factor được xác định khi tạo topic hoặc khi thực hiện quy trình thay đổi phân bố replica. Ví dụ tạo topic `orders` với 6 partition và RF=3:

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic orders \
  --partitions 6 \
  --replication-factor 3 \
  --config min.insync.replicas=2
```

Lệnh này yêu cầu cụm có ít nhất ba broker có thể nhận replica. Mỗi partition sẽ có ba replica; leader của các partition được phân bố để tránh dồn toàn bộ tải lên một broker.

Có thể kiểm tra leader, replica và ISR bằng lệnh:

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
```

Kết quả mô tả partition thường có các trường `Leader`, `Replicas` và `Isr`. `Replicas` cho biết broker đang giữ bản sao theo assignment; `Isr` cho biết các replica đang đồng bộ; `Leader` cho biết broker hiện phục vụ partition đó.

Một số cấu hình broker/topic thường gặp:

```properties
# Broker configuration
unclean.leader.election.enable=false

# Broker default cho topic được tạo tự động (nếu hệ thống cho phép auto-create)
default.replication.factor=3

# Có thể đặt ở cấp topic để yêu cầu tối thiểu hai replica trong ISR khi ghi acks=all
min.insync.replicas=2
```

`default.replication.factor` là giá trị mặc định cho topic được tạo tự động; nó không tự thay đổi replication factor của các topic đã tồn tại. Với topic quan trọng, nên tạo topic một cách chủ động và xác minh assignment thay vì phụ thuộc auto-create.

## 7. Cấu hình producer trong Spring Kafka

Ứng dụng Spring Boot có thể yêu cầu producer dùng `acks=all` và bật idempotence như sau:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      acks: all
      properties:
        enable.idempotence: true
```

`acks=all` yêu cầu broker xác nhận theo cơ chế ISR. `enable.idempotence` giúp producer tránh tạo bản ghi trùng do retry trong phạm vi đảm bảo của Kafka producer. Cấu hình idempotence cần tương thích với các giới hạn của producer như `acks`, `retries` và số request đang bay tối đa trên mỗi kết nối; Kafka client hiện đại tự kiểm tra các ràng buộc này.

`min.insync.replicas` là cấu hình phía broker/topic, không phải cấu hình chỉ đặt trong producer Spring. Cả hai phía phải được cấu hình đồng bộ: producer yêu cầu `acks=all`, còn topic/broker đặt ngưỡng ISR phù hợp. Nếu chỉ đặt `acks=all` mà không đặt ngưỡng tối thiểu, mức dự phòng ghi có thể thấp hơn kỳ vọng khi ISR co lại.

Ví dụ gửi sự kiện:

```java
@Service
public class OrderEventPublisher {
    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.send("orders", event.orderId(), event);
    }
}
```

Ứng dụng cần quan sát kết quả hoàn tất của `CompletableFuture`. Khi ISR thấp hơn `min.insync.replicas`, broker có thể trả lỗi như `NotEnoughReplicas` hoặc `NotEnoughReplicasAfterAppend`; tầng nghiệp vụ cần phân loại lỗi, retry có giới hạn và ghi nhận trạng thái để xử lý tiếp. Không nên bắt lỗi rồi bỏ qua, vì như vậy có thể biến sự cố hạ tầng thành mất sự kiện ở cấp ứng dụng.

## 8. Phân bố replica và khả năng chịu lỗi theo rack/availability zone

Replication chỉ có ích khi các bản sao được đặt ở những miền lỗi độc lập. Nếu cả ba replica của một partition cùng nằm trên máy chủ vật lý, rack hoặc availability zone có thể hỏng cùng lúc, RF=3 vẫn không bảo vệ được partition.

Kafka hỗ trợ rack awareness thông qua cấu hình `broker.rack`. Khi lập assignment, Kafka có thể phân bố replica qua các rack khác nhau nếu cụm được cấu hình đúng và có đủ broker ở các rack. Trong môi trường cloud, có thể ánh xạ rack vào availability zone.

Một thiết kế cần cân nhắc:

- Mỗi broker phải có định danh rack/zone chính xác và nhất quán.
- Các replica của cùng partition nên được phân bố qua nhiều miền lỗi độc lập.
- Số rack/zone và số broker mỗi rack phải đủ để đáp ứng RF mong muốn.
- Dung lượng mạng và băng thông liên rack phải đủ cho lưu lượng replication.
- Cần kiểm tra assignment thực tế; chỉ cấu hình `broker.rack` không tự bảo đảm mọi topic hiện có đã được phân bố lại đúng cách.

Nếu hệ thống chỉ có một availability zone, replication vẫn bảo vệ được một số lỗi broker/đĩa nhưng không bảo vệ trước sự cố toàn zone. Khi cần khôi phục sau thảm họa ở cấp khu vực, phải có chiến lược dự phòng và sao chép liên cụm phù hợp.

## 9. Replication không đồng nghĩa với backup hay exactly-once

Replication duy trì các bản sao vận hành của cùng partition trong một cụm. Nó không phải bản sao lưu độc lập. Nếu ứng dụng ghi nhầm dữ liệu, xóa topic, phát sự kiện sai hoặc một thao tác quản trị làm thay đổi dữ liệu, lỗi đó có thể ảnh hưởng đến mọi replica. Retention cũng có thể xóa dữ liệu khỏi các bản sao theo chính sách đã cấu hình.

Vì vậy, hệ thống quan trọng vẫn cần quy trình backup/restore, lưu trữ dài hạn hoặc sao chép sang cụm khác tùy mục tiêu khôi phục. Cần kiểm thử phục hồi định kỳ, vì có backup nhưng không thể restore đúng thời gian yêu cầu thì chưa đáp ứng mục tiêu vận hành.

Replication cũng không tự tạo ra exactly-once cho toàn bộ nghiệp vụ. `acks=all` và idempotent producer giúp tăng độ tin cậy khi ghi; Kafka transactions có thể cung cấp bảo đảm xử lý exactly-once trong các luồng Kafka được cấu hình đúng. Khi consumer gọi hệ thống bên ngoài như cơ sở dữ liệu hoặc API thanh toán, vẫn cần thiết kế idempotency, transaction boundary hoặc outbox/inbox phù hợp.

## 10. Theo dõi sức khỏe replication

Đội ngũ vận hành cần theo dõi các tín hiệu cho biết bản sao có đang theo kịp và partition có còn khả năng phục vụ hay không.

| Chỉ số/tín hiệu | Ý nghĩa | Hướng điều tra |
|---|---|---|
| Offline partitions | Partition không có leader khả dụng | Kiểm tra broker, controller, ISR và tình trạng mạng |
| Under-replicated partitions | Số replica hiện tại thấp hơn replication factor hoặc chưa theo kịp | Kiểm tra broker mất kết nối, đĩa, mạng và tải replication |
| Under-min-ISR partitions | Partition có ISR thấp hơn ngưỡng `min.insync.replicas` | Đánh giá khả năng ghi và phục hồi replica |
| ISR shrink/expand | Replica bị loại khỏi hoặc được thêm lại vào ISR | Tìm nguyên nhân follower thường xuyên tụt hậu |
| Leader election rate | Tần suất bầu chọn leader | Kiểm tra broker chập chờn, restart hoặc lỗi mạng |
| Produce errors/latency | Producer bị từ chối ghi hoặc ghi chậm | Đối chiếu `acks`, min ISR, timeout và sức khỏe broker |

Ngoài metric, cần theo dõi log broker, dung lượng đĩa, tốc độ ghi/đọc, lưu lượng mạng và trạng thái controller. Một replica tụt hậu liên tục có thể là dấu hiệu broker thiếu tài nguyên hoặc lưu lượng replication không theo kịp lưu lượng ghi.

## 11. Thực hành vận hành an toàn

Khi bảo trì hoặc thay đổi cụm Kafka, nên thực hiện theo từng broker và kiểm tra sức khỏe partition sau mỗi bước. Dừng nhiều broker cùng lúc có thể làm ISR giảm dưới ngưỡng tối thiểu hoặc khiến partition mất leader.

Một số nguyên tắc hữu ích:

1. Chọn RF dựa trên số broker, miền lỗi và mục tiêu khôi phục; RF=3 thường là điểm khởi đầu cho môi trường production có đủ broker.
2. Kết hợp `acks=all` với `min.insync.replicas` để kiểm soát số bản sao tối thiểu khi xác nhận ghi.
3. Theo dõi offline partition, under-replicated partition và under-min-ISR trước khi tiếp tục rollout.
4. Bảo trì lần lượt, chờ replica bắt kịp và ISR ổn định rồi mới chuyển sang broker tiếp theo.
5. Dùng rack awareness và kiểm tra assignment để giảm nguy cơ một sự cố vật lý làm mất nhiều replica cùng lúc.
6. Thử nghiệm tình huống broker/leader dừng trong môi trường staging; xác minh producer retry, consumer tiếp tục đọc và ứng dụng xử lý lỗi đúng.
7. Có kế hoạch backup, restore và disaster recovery riêng cho dữ liệu cần lưu giữ lâu dài.

## 12. Tổng kết

- Mỗi partition có một leader và có thể có nhiều follower replica; producer ghi vào leader, follower fetch dữ liệu để sao chép.
- Replication factor là tổng số replica của partition, gồm cả leader.
- ISR là tập replica đang theo kịp leader và là cơ sở quan trọng cho xác nhận ghi cũng như leader election an toàn.
- `acks=all` kết hợp `min.insync.replicas` giúp đặt mức xác nhận tối thiểu khi ghi.
- Leader election giúp partition phục hồi sau sự cố broker; unclean election có thể khôi phục khả năng phục vụ nhưng mang nguy cơ mất dữ liệu.
- Rack awareness phân tán replica qua các miền lỗi; monitoring và bảo trì tuần tự giúp duy trì sức khỏe cụm.
- Replication không thay thế backup và không tự bảo đảm exactly-once cho nghiệp vụ bên ngoài Kafka.

Khi triển khai Spring Kafka, cần xem độ tin cậy như một thuộc tính của toàn luồng: producer phải kiểm tra kết quả gửi, cụm Kafka phải duy trì đủ replica trong ISR, consumer phải xử lý lỗi và record được giao lại an toàn. Cấu hình đúng các lớp này giúp hệ thống messaging tiếp tục hoạt động khi broker hoặc một miền hạ tầng gặp sự cố.
