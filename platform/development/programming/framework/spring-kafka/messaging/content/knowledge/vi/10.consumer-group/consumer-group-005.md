# Consumer group rebalancing

Kafka consumer group có thể thay đổi thành viên hoặc số partition cần phân phối trong suốt thời gian hoạt động. Khi đó, Kafka phải tính toán lại consumer nào chịu trách nhiệm đọc từng partition. Quá trình thu hồi assignment cũ và phân phối assignment mới được gọi là **rebalance**.

Rebalance giúp group tiếp tục hoạt động khi consumer tham gia, rời đi hoặc gặp sự cố, đồng thời phân phối lại tải khi topic thay đổi. Tuy nhiên, trong thời gian rebalance, việc đọc ở các partition bị ảnh hưởng có thể tạm dừng; listener có thể thấy độ trễ tăng, xử lý bị gián đoạn và record chưa commit có thể được đọc lại. Hiểu trigger, chiến lược phân phối và cách quan sát rebalance giúp vận hành Spring Kafka ổn định hơn.

## 1. Consumer group phân phối partition như thế nào?

Một consumer group gồm các consumer cùng đăng ký đọc một hoặc nhiều topic với cùng group ID. Kafka phân phối các partition của topic cho những consumer trong group. Trong một group, tại một thời điểm, một partition chỉ được gán cho tối đa một consumer.

Ví dụ, topic `orders.events` có sáu partition và group `order-projection` có ba consumer:

```text
Topic orders.events
  P0   P1   P2   P3   P4   P5
   \   |    /    \    |    /
    \  |   /      \   |   /
   Consumer A    Consumer B    Consumer C
```

Một assignment hợp lệ có thể là:

| Consumer | Partition được gán |
|---|---|
| Consumer A | P0, P1 |
| Consumer B | P2, P3 |
| Consumer C | P4, P5 |

Đây chỉ là một ví dụ; kết quả thực tế phụ thuộc partition assignor. Nếu group có nhiều consumer hơn partition, một số consumer sẽ không được gán partition. Nếu một consumer rời group, các partition của nó cần được phân phối lại cho thành viên còn lại.

## 2. Rebalance diễn ra theo những bước nào?

Kafka group coordinator quản lý membership và điều phối quá trình rebalance. Trong giao thức group truyền thống, các consumer trao đổi metadata về subscription, coordinator xác định group cần rebalance, một thành viên được chọn làm group leader để tính assignment theo assignor, rồi assignment được gửi tới các consumer.

Ở mức khái niệm, quá trình gồm:

1. **Phát hiện thay đổi:** coordinator nhận biết thành viên mới, thành viên rời đi, heartbeat hết hạn hoặc metadata subscription/partition thay đổi.
2. **Bắt đầu rebalance:** group bước vào generation mới. Các consumer liên quan thực hiện callback thu hồi partition theo chiến lược assignment.
3. **Tính assignment:** partition assignor xác định partition nào thuộc về consumer nào.
4. **Phân phối assignment:** consumer nhận partition mới và tiếp tục fetch, poll, xử lý record.

Generation là phiên bản membership của group. Nó giúp Kafka nhận biết các yêu cầu commit hoặc hoạt động đến từ thành viên thuộc generation nào. Khi group đã chuyển generation, một commit dựa trên membership cũ có thể bị từ chối vì consumer không còn thuộc generation hiện tại.

Trong các phiên bản Kafka mới có thêm consumer group protocol mới, một số chi tiết điều phối và vai trò leader/assignor thay đổi. Dù dùng protocol nào, ý nghĩa vận hành vẫn là group phải cập nhật membership và assignment khi trạng thái thành viên hoặc tài nguyên thay đổi.

## 3. Những nguyên nhân thường gây rebalance

Rebalance không chỉ xảy ra khi ứng dụng deploy. Những nguyên nhân thường gặp gồm:

| Nguyên nhân | Điều xảy ra |
|---|---|
| Consumer mới tham gia group | Group phải phân phối lại partition để tính đến thành viên mới |
| Consumer dừng bình thường | Consumer rời group và partition của nó được giao cho thành viên khác |
| Consumer hoặc máy chạy bị lỗi | Coordinator phát hiện thành viên không còn heartbeat hợp lệ và loại khỏi group |
| Không gọi `poll()` trong thời gian cho phép | Consumer có thể bị xem là không còn tiến triển và rời group |
| Thay đổi subscription | Thành viên đăng ký thêm/bớt topic hoặc pattern khớp với topic mới |
| Tăng số partition của topic | Group cần cập nhật assignment để phân phối các partition mới |
| Thay đổi cấu hình hoặc giao thức assignor | Các thành viên có thể cần thực hiện rebalance để thống nhất assignment |

Một ứng dụng liên tục restart, liveness probe quá nhạy, xử lý listener kéo dài hoặc mạng chập chờn có thể làm group rebalance thường xuyên. Nếu rebalance lặp lại trong thời gian ngắn, throughput giảm và độ trễ xử lý tăng dù tổng số record không thay đổi.

## 4. Heartbeat, session timeout và max poll interval

Ba cấu hình thường được xem xét khi chẩn đoán consumer bị loại khỏi group:

| Thuộc tính | Vai trò |
|---|---|
| `heartbeat.interval.ms` | Khoảng thời gian consumer gửi heartbeat tới group coordinator |
| `session.timeout.ms` | Thời gian coordinator chờ heartbeat hợp lệ trước khi xem consumer đã mất kết nối |
| `max.poll.interval.ms` | Thời gian tối đa giữa các lần `poll()`; bảo vệ group khỏi consumer không tiến triển xử lý |

Heartbeat cho coordinator biết consumer vẫn tham gia group. `session.timeout.ms` quyết định coordinator chờ bao lâu khi heartbeat bị mất. `max.poll.interval.ms` kiểm soát tiến độ gọi poll của ứng dụng. Một consumer có thể vẫn gửi heartbeat nền nhưng xử lý record quá lâu và không gọi poll kịp hạn; khi đó consumer vẫn có thể bị rời group do vi phạm max poll interval.

Với listener xử lý đồng bộ, thời gian xử lý lô cần nằm trong `max.poll.interval.ms` với khoảng dự phòng. Nếu lô quá lớn hoặc listener gọi dịch vụ ngoài không có timeout, consumer có thể vượt giới hạn và gây rebalance. Hãy đo thời gian xử lý thực tế, đặc biệt percentile cao, thay vì chỉ dựa vào thời gian trung bình.

Ví dụ cấu hình trong Spring Boot:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-projection
      properties:
        "[heartbeat.interval.ms]": 3000
        "[session.timeout.ms]": 10000
        "[max.poll.interval.ms]": 300000
```

Các con số trên chỉ minh họa. Với giao thức classic, `heartbeat.interval.ms` thường cần nhỏ hơn đáng kể so với `session.timeout.ms`; giới hạn hợp lệ còn phụ thuộc cấu hình broker. Hãy điều chỉnh theo môi trường và phiên bản Kafka, không sao chép máy móc vào production.

## 5. Eager và cooperative rebalancing

Partition assignor quyết định cách phân phối partition. Cách thức thu hồi assignment có ảnh hưởng lớn đến mức độ gián đoạn khi rebalance.

### Eager rebalancing

Với eager rebalancing, các consumer trong group thu hồi toàn bộ partition đang giữ trước khi nhận assignment mới. Trong giai đoạn chuyển đổi, group có thể tạm dừng xử lý trên tất cả partition thuộc group, kể cả partition mà về lý thuyết không cần chuyển sang consumer khác.

Ưu điểm là quy trình đơn giản và tương thích với các assignor eager truyền thống. Nhược điểm là phạm vi tạm dừng có thể lớn, đặc biệt khi group có nhiều consumer và partition.

### Cooperative rebalancing

Cooperative rebalancing cho phép chuyển partition theo từng phần. Consumer chỉ thu hồi những partition thực sự cần chuyển; các partition không bị ảnh hưởng có thể tiếp tục được xử lý. Nếu assignment cần nhiều bước, coordinator có thể yêu cầu thêm một vòng rebalance để hoàn tất việc chuyển giao.

`CooperativeStickyAssignor` cố gắng giữ assignment ổn định giữa các lần rebalance, đồng thời phân phối tải tương đối cân bằng. Cách này thường giảm phạm vi gián đoạn khi group thay đổi membership.

Để dùng cooperative assignor với Kafka client hỗ trợ, có thể cấu hình:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[partition.assignment.strategy]": org.apache.kafka.clients.consumer.CooperativeStickyAssignor
```

Khi triển khai theo rolling upgrade, cần tuân thủ hướng dẫn tương thích của phiên bản Kafka và assignor đang dùng. Tất cả consumer trong cùng group phải có chiến lược tương thích; không nên thay đổi assignor đồng loạt mà không tính đến consumer phiên bản cũ còn đang chạy.

Cooperative rebalancing giảm số partition phải dừng, nhưng không loại bỏ rebalance. Consumer vẫn phải xử lý thu hồi và nhận partition, đồng thời ứng dụng phải chuẩn bị cho việc callback revoke/assign được gọi nhiều lần.

## 6. Static membership giảm rebalance khi restart ngắn

Mặc định, consumer được nhận diện bằng member ID do Kafka quản lý. Khi consumer rời group, thành viên bị loại và group có thể rebalance ngay. Khi ứng dụng restart ngắn trong quá trình deploy, việc rời rồi tham gia lại có thể gây rebalance dù instance mới thực chất thay thế instance cũ.

**Static membership** cho phép cấu hình `group.instance.id` ổn định cho một consumer instance. Khi consumer khởi động lại với cùng ID trong giới hạn session timeout, Kafka có thể nhận diện đó là cùng thành viên và giảm rebalance không cần thiết.

Ví dụ cấu hình thuộc tính cho một consumer instance:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[group.instance.id]": ${KAFKA_CONSUMER_INSTANCE_ID}
```

Giá trị `KAFKA_CONSUMER_INSTANCE_ID` phải ổn định qua lần restart của cùng instance và duy nhất trong group tại cùng thời điểm. Nếu hai consumer đồng thời dùng một static member ID, Kafka có thể từ chối hoặc fencing một thành viên. Với listener container có concurrency lớn hơn một, cần bảo đảm mỗi consumer thực tế có ID riêng theo cách cấu hình được Spring Kafka hỗ trợ.

Static membership hữu ích cho rolling restart ngắn, nhưng có đánh đổi: khi instance thực sự mất, coordinator có thể chờ session timeout trước khi loại thành viên tĩnh và phân phối lại partition. Chọn timeout quá dài có thể khiến partition bị giữ lâu khi instance chết thật.

## 7. Quan sát rebalance trong Spring Kafka

Spring Kafka cho phép đăng ký `ConsumerRebalanceListener` thông qua `ContainerProperties`. Callback thường được dùng để ghi log assignment, giải phóng state gắn với partition sắp bị thu hồi hoặc khởi tạo state cho partition mới.

Ví dụ cấu hình một container factory riêng:

```java
import java.util.Collection;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ConsumerAwareRebalanceListener;

@Configuration
class RebalanceListenerConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(RebalanceListenerConfiguration.class);

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
            rebalanceAwareKafkaListenerContainerFactory(
                    ConsumerFactory<String, String> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setConsumerRebalanceListener(
                new ConsumerAwareRebalanceListener() {
                    @Override
                    public void onPartitionsRevokedBeforeCommit(
                            Consumer<?, ?> consumer,
                            Collection<TopicPartition> partitions) {
                        log.info("Partitions revoked: {}", partitions);
                        // Flush hoặc giải phóng state cục bộ của các partition này.
                    }

                    @Override
                    public void onPartitionsAssigned(
                            Consumer<?, ?> consumer,
                            Collection<TopicPartition> partitions) {
                        log.info("Partitions assigned: {}", partitions);
                        // Khởi tạo state cần thiết cho các partition mới.
                    }
                }
        );
        return factory;
    }
}
```

Listener có thể chọn factory này:

```java
@KafkaListener(
        topics = "orders.events",
        groupId = "order-projection",
        containerFactory = "rebalanceAwareKafkaListenerContainerFactory"
)
public void consume(String payload) {
    process(payload);
}
```

Callback chạy trong ngữ cảnh luồng consumer. Không thực hiện công việc blocking kéo dài trong callback, vì nó có thể trì hoãn việc hoàn tất rebalance. Nếu ứng dụng dùng state cục bộ theo partition, hãy flush hoặc giải phóng đúng partition trong callback revoke; khi assign, khôi phục state từ nguồn bền vững trước khi xử lý phụ thuộc vào state đó.

Kafka client mới còn có callback `onPartitionsLost()` để phân biệt partition bị mất quyền sở hữu mà không có cơ hội revoke bình thường. Nếu cần dùng callback này, hãy kiểm tra phiên bản Kafka client và API Spring Kafka tương ứng. Trong tình huống partition đã lost, không nên giả định consumer vẫn có thể commit offset cho partition đó.

## 8. Rebalance ảnh hưởng đến offset và xử lý record

Khi partition bị revoke, consumer cũ cần hoàn tất công việc và commit offset theo chính sách ứng dụng trước khi nhường quyền. Spring Kafka listener container quản lý commit theo acknowledgement mode. Nếu listener xử lý xong nhưng chưa commit và partition được giao cho consumer khác, record có thể được đọc lại từ offset đã commit gần nhất.

Một số nguyên tắc giúp giảm lỗi:

- Đặt `enable.auto.commit=false` để Spring Kafka quản lý commit theo acknowledgement mode.
- Chọn `AckMode` phù hợp, chẳng hạn `BATCH` cho xử lý record theo poll hoặc manual acknowledgement khi cần kiểm soát thời điểm commit.
- Không thực hiện side effect không idempotent trước khi commit mà không có cơ chế chống xử lý lặp.
- Giữ công việc trong callback rebalance ngắn và tránh gọi dịch vụ ngoài có độ trễ không kiểm soát.
- Khi cần state theo partition, lưu checkpoint hoặc state bền vững để consumer mới có thể tiếp tục an toàn.

Rebalance không làm mất record chưa hết retention. Vấn đề thường là record có thể được đọc lại do offset commit chưa phản ánh phần xử lý vừa hoàn thành. Ứng dụng nên thiết kế theo hướng at-least-once và idempotent nếu không dùng một cơ chế transaction bao phủ toàn bộ thao tác cần bảo đảm.

## 9. Cách giảm rebalance không cần thiết

| Biện pháp | Tác dụng |
|---|---|
| Đặt timeout cho database/API và xử lý listener | Tránh vượt `max.poll.interval.ms` |
| Chọn `max.poll.records` theo thời gian xử lý lô | Giữ thời gian giữa các lần poll trong giới hạn |
| Dùng cooperative assignor tương thích | Giảm số partition phải thu hồi trong một lần chuyển assignment |
| Dùng static membership khi phù hợp | Giảm rebalance do restart ngắn của cùng instance |
| Ổn định số consumer và tránh restart liên tục | Hạn chế membership thay đổi liên tục |
| Đồng bộ cấu hình group và assignor | Tránh consumer không tương thích trong cùng group |
| Giám sát heartbeat, poll, lag và thời gian rebalance | Phát hiện nguyên nhân trước khi ảnh hưởng kéo dài |

Không nên cố ngăn mọi rebalance. Rebalance là cơ chế phục hồi và phân phối tải của Kafka. Mục tiêu là giảm rebalance bất thường, đồng thời bảo đảm group vẫn phản ứng đúng khi consumer thực sự hỏng hoặc cần mở rộng.

## 10. Chẩn đoán rebalance thường xuyên

Khi log cho thấy group liên tục rebalancing, hãy kiểm tra theo thứ tự:

1. Xem log consumer để tìm nguyên nhân rời group: heartbeat timeout, poll interval exceeded, explicit leave, member ID trùng hoặc lỗi kết nối coordinator.
2. Đo thời gian xử lý listener và kích thước lô. Đối chiếu percentile cao với `max.poll.interval.ms`.
3. Kiểm tra CPU, garbage collection, network và thời gian chờ database/API trên từng instance.
4. Xem số lần restart của pod/VM và readiness/liveness probe; restart liên tục có thể khiến membership thay đổi liên tục.
5. Kiểm tra subscription, regex topic pattern và thay đổi số partition có làm assignment thay đổi hay không.
6. Xác minh tất cả consumer trong group dùng assignor và group protocol tương thích.
7. Kiểm tra callback revoke/assign có blocking hoặc phát sinh lỗi không.

Có thể dùng các công cụ quản trị Kafka để xem thành viên group, consumer ID, partition assignment và lag. Với Spring Kafka, bổ sung log có cấu trúc trong rebalance callback giúp liên kết sự kiện revoke/assign với thời điểm deploy và tình trạng xử lý.

## 11. Những nhầm lẫn thường gặp

1. **Cho rằng rebalance chỉ xảy ra khi consumer chết.** Consumer mới tham gia, subscription thay đổi, tăng partition hoặc vượt `max.poll.interval.ms` cũng có thể gây rebalance.
2. **Cho rằng cooperative rebalancing loại bỏ hoàn toàn downtime.** Nó chỉ giảm phạm vi partition phải revoke; group vẫn có thể cần một hoặc nhiều vòng chuyển giao.
3. **Dùng chung `group.instance.id` cho nhiều consumer.** Static member ID phải duy nhất cho từng consumer instance trong group.
4. **Tăng `session.timeout.ms` để sửa mọi rebalance.** Cấu hình này chỉ thay đổi thời gian phát hiện mất heartbeat; nó không giải quyết listener xử lý quá lâu hoặc consumer bị treo.
5. **Làm việc nặng trong callback revoke/assign.** Callback blocking có thể làm rebalance kéo dài hơn.
6. **Cho rằng record đã xử lý thì chắc chắn không được xử lý lại.** Nếu offset chưa commit, consumer mới có thể đọc lại record.
7. **Cố giữ assignment bằng mọi giá.** Rebalance là cần thiết để group phục hồi khi consumer mất hoặc tải thay đổi.

Rebalance là một phần bình thường trong vòng đời consumer group. Khi hiểu nguyên nhân kích hoạt, sự khác nhau giữa eager và cooperative assignment, cùng cách Spring Kafka quản lý callback và offset, bạn có thể giảm gián đoạn không cần thiết mà vẫn giữ khả năng phục hồi của hệ thống messaging.
