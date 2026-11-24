# Consumer bị rebalance liên tục hoặc chậm commit offset

Một ứng dụng Spring Cloud Stream có thể vẫn khởi động bình thường nhưng Kafka consumer lại nhận partition rồi mất partition liên tục, consumer lag tăng dù CPU không cao, hoặc xuất hiện thông báo commit offset thất bại. Đây là nhóm sự cố dễ dẫn đến xử lý lại message, mất ổn định throughput, tăng độ trễ và gây nhầm lẫn giữa lỗi consumer group với lỗi business logic.

Bài này hướng dẫn chẩn đoán **Kafka consumer dùng regular Kafka Binder** trong Spring Cloud Stream: xác định rebalance thật sự, phân biệt thời gian xử lý với thời gian commit, đọc log và metrics của Kafka client, kiểm tra `max.poll.interval.ms`, heartbeat/session timeout, group membership, acknowledgement, retry, network và broker coordinator. Phần cuối nêu khác biệt với Kafka Streams Binder, RabbitMQ/Pulsar và cách kiểm thử hồi quy. Không thay đổi group ID, reset offset hoặc tắt acknowledgement chỉ để làm biểu đồ lag đẹp hơn.

## 1. Nhận diện đúng triệu chứng trước khi chỉnh cấu hình

Các tín hiệu thường gặp:

- Log lặp lại `Revoking previously assigned partitions`, `partitions revoked`, `partitions assigned` hoặc `Successfully joined group` dù không có deployment hay thay đổi tải đáng kể.
- Consumer group liên tục chuyển giữa trạng thái ổn định và rebalance; các member ID và partition assignment thay đổi thường xuyên.
- Log `CommitFailedException`, `RebalanceInProgressException` hoặc `Offset commit failed`.
- Giá trị committed offset không tăng theo kỳ vọng, trong khi handler vẫn có log xử lý.
- Kafka consumer lag tăng, throughput giảm; các message đã xử lý có thể được phát lại sau restart/rebalance.
- Broker trả lời heartbeat/commit chậm, request timeout, hoặc ứng dụng bị restart do OOM, liveness probe, deploy rolling.

**Không phải mọi lần rebalance đều là lỗi.** Rebalance là hành vi bình thường khi member gia nhập/rời group, topic đổi partition hoặc group coordinator thay đổi. Vấn đề là rebalance lặp lại với tần suất bất thường, ảnh hưởng SLO hoặc kéo dài quá lâu.

## 2. Ba hiện tượng dễ bị nhầm

| Hiện tượng | Dấu hiệu nổi bật | Cần đo gì? |
|---|---|---|
| **Rebalance storm** | Nhiều chu kỳ revoke/join/assign, generation/member thay đổi | Rebalance rate, last-rebalance time, member count, pod restart |
| **Commit request chậm** | `commit-latency-avg/max` tăng, commit timeout hoặc lỗi coordinator | Client commit latency, request/network latency, coordinator health |
| **Committed offset tiến chậm** | `CURRENT-OFFSET` không đổi hoặc tăng ít; nhưng chưa chắc Kafka commit chậm | Ack mode, số record hoàn tất, thời điểm ack, retry/batch |

Consumer lag thường được tính từ end offset và committed offset của group. Khi xử lý một batch mà chưa commit, lag có thể vẫn cao dù ứng dụng đã nhận nhiều record. Ngược lại, committed offset có thể tăng nhanh hơn tốc độ nghiệp vụ hoàn tất nếu ứng dụng ack quá sớm hoặc bật auto commit không phù hợp. Vì vậy, so sánh **position của consumer, committed offset, end offset và completion của business processing** trước khi kết luận nguyên nhân.

## 3. Cơ chế Kafka consumer group và rebalance

Trong consumer group, Kafka gán các partition cho những consumer member hiện có. Một partition thường chỉ do một consumer trong cùng group xử lý tại một thời điểm. Khi membership thay đổi, Kafka phải cập nhật assignment.

Các thành phần cần phân biệt:

- **`group.id`**: tên group; trong Spring Cloud Stream thường xuất phát từ `spring.cloud.stream.bindings.<binding>.group`.
- **Group coordinator**: broker quản lý membership và commit offset của consumer group.
- **Member/instance**: một consumer tham gia group; một Spring Boot instance có thể tạo nhiều Kafka consumer khi `concurrency` lớn hơn 1.
- **Assignment**: danh sách partition mà một consumer được phân công.
- **Heartbeat**: tín hiệu để coordinator biết member vẫn hoạt động.
- **Poll loop**: lời gọi `poll()` tiếp nhận records; khi listener xử lý quá lâu, lần poll tiếp theo bị chậm.
- **Offset commit**: lưu tiến độ của group; offset được commit thường là **vị trí tiếp theo cần đọc**, không phải offset cuối cùng đã xử lý.

Ví dụ xử lý thành công record có offset 41 thì giá trị được commit thường là 42. Đừng chẩn đoán sai một đơn vị offset trong kết quả `kafka-consumer-groups.sh`.

## 4. Thu thập bằng chứng trong 10 phút đầu

Trước khi chỉnh tham số, thu thập đủ:

1. Thời điểm sự cố bắt đầu, phiên bản ứng dụng/binder/Kafka client, thay đổi deploy gần nhất.
2. Tên Kafka cluster, topic, group ID, binding name, số partition, số pod và `consumer.concurrency`.
3. Các log revoke/assign, heartbeat, coordinator, commit và exception theo cùng mốc thời gian.
4. CPU, GC pause, heap, thread dump, thời gian xử lý function và dependency latency.
5. Consumer group lag và member assignment trước/sau rebalance.
6. Metrics commit latency/rate, rebalance rate và poll interval từ Kafka client.
7. Container restarts, HPA scaling events, graceful shutdown và thời gian giữ readiness/liveness.

Không thay đổi group ID, xóa topic, reset offsets hoặc chạy lệnh mutate consumer group trong bước thu thập bằng chứng. Những thao tác đó có thể làm mất dấu nguyên nhân hoặc khiến message replay hàng loạt.

## 5. Kiểm tra group bằng công cụ Kafka

Ví dụ lệnh trên máy có Kafka CLI và quyền truy cập broker:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server broker-1:9092 \
  --describe --group order-service
~~~

Kết quả thường có các trường:

~~~text
GROUP         TOPIC          PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
order-service orders.events  0          12500           12800           300
order-service orders.events  1          12480           12600           120
~~~

Kiểm tra thành viên:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server broker-1:9092 \
  --describe --group order-service --members --verbose
~~~

Nếu phiên bản CLI hỗ trợ, có thể xem tổng quan state:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server broker-1:9092 \
  --describe --group order-service --state
~~~

Diễn giải:

- `CURRENT-OFFSET`: offset đã commit của group ở partition đó; không nhất thiết là record đang được xử lý.
- `LOG-END-OFFSET`: offset kết thúc log theo góc nhìn công cụ; có thể chịu ảnh hưởng isolation và trạng thái giao dịch.
- `LAG`: chênh lệch offset; tăng khi nguồn phát nhanh hơn tốc độ group tiến offset.
- `MEMBER-ID`/`CLIENT-ID`/`HOST`: giúp phát hiện một pod/consumer liên tục ra-vào group.

Chụp nhiều lần cách nhau 30–60 giây để phân biệt lag tăng liên tục với dao động bình thường. Nếu group luôn đổi member nhưng pod không restart, tập trung vào poll/heartbeat/network. Nếu member đổi cùng nhịp pod restart, ưu tiên điều tra tiến trình/health probes.

## 6. Đọc log theo nhóm nguyên nhân

| Log/triệu chứng | Giả thuyết đầu tiên | Bước kiểm tra |
|---|---|---|
| `max.poll.interval.ms` exceeded | Handler/retry/batch chặn poll quá lâu | Đo thời gian từ poll đến poll, max.poll.records và thời gian xử lý |
| `session timeout`, heartbeat failure | Coordinator không nhận heartbeat kịp | Kiểm tra GC pause, network, coordinator, session config |
| `CommitFailedException` | Consumer không còn là member hợp lệ/generation đổi | Tìm rebalance ngay trước commit; kiểm tra poll interval |
| `RebalanceInProgressException` | Rebalance đang diễn ra khi commit | Theo dõi poll/rejoin và kiểm tra tần suất rebalance |
| `NotCoordinator` hoặc `CoordinatorNotAvailable` | Coordinator đang chuyển/broker khó truy cập | Kiểm tra broker health, metadata, network, client retries |
| `FencedInstanceIdException` | Nhiều consumer dùng cùng static `group.instance.id` | Bảo đảm ID duy nhất cho từng consumer instance |
| Partition revoke/assign đúng lúc deploy | Rolling deployment hoặc autoscaling | Kiểm tra rollout policy, readiness và graceful termination |
| Offset không tăng nhưng không có lỗi commit | Ack chưa diễn ra hoặc batch chưa hoàn tất | Kiểm tra ack mode, handler completion, manual acknowledgement |

Không dựa vào một dòng `CommitFailedException` để kết luận broker chậm. Trong nhiều trường hợp lỗi commit là **hậu quả** của rebalance: member đã bị loại hoặc generation cũ không còn quyền commit.

## 7. Nguyên nhân phổ biến: vượt max.poll.interval.ms

`max.poll.interval.ms` giới hạn khoảng cách tối đa giữa hai lần gọi `poll()` trong consumer group. Giá trị mặc định của Kafka client hiện đại thường là **300.000 ms (5 phút)**. Nếu thread xử lý message quá lâu và không quay lại poll kịp, Kafka xem consumer không còn tiến triển đúng hạn.

Kịch bản điển hình:

~~~text
poll() returns up to N records
    |
    v
Listener handles records (DB/HTTP/retries)
    |
    +-- processing and backoff exceed max.poll.interval.ms
    |
    v
Consumer loses valid membership / group assignment changes
    |
    v
Commit attempted with stale generation -> failure
    |
    v
Partitions reassigned, records may be replayed
~~~

Ví dụ một poll trả tối đa 500 records, mỗi record xử lý trung bình 800 ms theo cách tuần tự. Thời gian xử lý có thể lên tới khoảng 400 giây, **vượt 300 giây**, chưa tính retry và mạng. Consumer có thể mất membership trước khi commit. Đó là vấn đề **làm việc quá lâu giữa các lần poll**, không được chữa triệt để chỉ bằng tăng số broker.

Ưu tiên:

1. Đo duration của từng handler, bao gồm dependency, serialization và retry.
2. Giảm `max.poll.records` để giới hạn lượng công việc mỗi poll.
3. Chia nhỏ/bulk xử lý hợp lý, giảm blocking I/O, đặt timeout cho dependency.
4. Kiểm tra batch-mode và error handler; batch lớn có thể kéo dài một lần xử lý.
5. Chỉ tăng `max.poll.interval.ms` sau khi đã đo và có lý do rõ ràng, vì cấu hình quá lớn làm chậm phát hiện consumer bị treo.

Không giả định `max.poll.records` giới hạn số record Kafka tải từ broker trong một lần fetch; nó giới hạn số record trả về một lần `poll()`.

## 8. Cấu hình Spring Cloud Stream cho trường hợp poll quá lớn

Ví dụ **regular Kafka Binder** với bean `Consumer<Message<OrderEvent>> handleOrder`:

~~~yaml
spring:
  cloud:
    function:
      definition: handleOrder
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.events
          group: order-service
          consumer:
            concurrency: 3
      kafka:
        bindings:
          handleOrder-in-0:
            consumer:
              ack-mode: BATCH
              configuration:
                max.poll.records: 100
                max.poll.interval.ms: 300000
~~~

Cấu hình trên minh họa **giới hạn 100 records/poll** và lựa chọn `ack-mode: BATCH` tường minh để dễ quan sát. Nó **không phải khuyến nghị phổ quát**: nếu ứng dụng đang dùng `RECORD`, `MANUAL` hoặc transaction, không đổi ack mode khi chưa hiểu yêu cầu xử lý lại và duplicate.

Thuộc tính Kafka client nằm ở `spring.cloud.stream.kafka.bindings.<binding>.consumer.configuration`; thuộc tính Spring Cloud Stream chung như `concurrency` nằm ở `spring.cloud.stream.bindings.<binding>.consumer`; `ack-mode` nằm trong nhánh consumer của Kafka binder. Nếu binding đã được alias bằng `spring.cloud.stream.function.bindings`, hãy dùng đúng **tên binding hiệu lực** trong cả hai nhánh.

Hãy benchmark với message kích thước lớn, tải đỉnh và retry, không chỉ với các bản ghi nhỏ trong môi trường local.

## 9. Nguyên nhân khác: session timeout và heartbeat

`session.timeout.ms` là thời gian coordinator chờ heartbeat trước khi xem một member không còn sống. Nó khác với `max.poll.interval.ms`:

| Thuộc tính | Bảo vệ điều gì? | Khi vượt ngưỡng |
|---|---|---|
| `max.poll.interval.ms` | Tiến độ poll/processing của consumer | Member có thể mất quyền giữ partition dù heartbeat trước đó vẫn hoạt động |
| `session.timeout.ms` | Sự sống của member qua heartbeat | Coordinator loại member không gửi heartbeat kịp |
| `heartbeat.interval.ms` | Chu kỳ gửi heartbeat khi dùng classic protocol | Quá thưa hoặc network chậm có thể gây timeout |

Các nguyên nhân mất heartbeat gồm:

- JVM có stop-the-world GC pause dài, CPU bị throttling hoặc hết tài nguyên.
- Mạng tới group coordinator không ổn định, DNS/TLS/SASL chậm hoặc lỗi.
- Broker coordinator quá tải, đang failover hoặc partition nội bộ `__consumer_offsets` gặp vấn đề.
- Container bị kill/restart, rolling deployment, node drain, liveness probe cấu hình quá nhạy.

**Quan trọng với phiên bản Kafka mới:** consumer có thể dùng `group.protocol=classic` hoặc `group.protocol=consumer`. Với **classic**, các tham số client `heartbeat.interval.ms` và `session.timeout.ms` được hỗ trợ; heartbeat thường nên nhỏ hơn session timeout và nhiều hướng dẫn dùng không quá khoảng một phần ba. Với **consumer protocol**, các nhịp heartbeat và session timeout này do broker kiểm soát qua `group.consumer.heartbeat.interval.ms` và `group.consumer.session.timeout.ms`; không đặt các thuộc tính client classic rồi kỳ vọng chúng có tác dụng.

Không tăng timeout gấp nhiều lần khi chưa xác minh nguyên nhân; timeout dài có thể kéo dài thời gian failover thực tế. Nếu lỗi chỉ xuất hiện khi mất kết nối hoặc GC kéo dài, ưu tiên sửa điều kiện hạ tầng.

## 10. Vì sao một pod có thể gây rebalance liên tục?

Trên Kubernetes, một consumer member có thể bị tạo và hủy nhiều lần vì:

- Liveness probe dùng consumer lag hoặc dependency xa làm tiêu chí chết; khi Kafka bị chậm, probe restart pod và gây rebalance vòng lặp.
- Thời gian `terminationGracePeriodSeconds` quá ngắn; Kafka consumer không kịp close/graceful leave khi rolling update.
- Deployment rollout tạo quá nhiều pod mới cùng lúc, thay đổi member count liên tục.
- HPA scale lên/xuống sát ngưỡng, không có stabilization window.
- Memory limit quá thấp, JVM OOMKilled; CPU limit gây GC hoặc scheduling pause.
- Readiness/liveness không phản ánh đúng sự khác biệt giữa broker tạm unavailable và tiến trình thật sự treo.

Các bước kiểm tra vận hành:

~~~bash
kubectl get pods -n orders -o wide
kubectl describe pod <pod-name> -n orders
kubectl get events -n orders --sort-by=.lastTimestamp
kubectl rollout status deployment/order-service -n orders
~~~

Lệnh chỉ để quan sát; thay namespace/deployment theo môi trường. Đối chiếu timestamp pod restart, rollout và HPA với thời điểm `partitions revoked` trong log.

Nếu rebalances tương quan với deployment, sửa chiến lược rollout/graceful shutdown trước khi đổi `max.poll.interval.ms` hoặc `session.timeout.ms`.

## 11. Group ID, số consumer và partition assignment

Trong Spring Cloud Stream, `spring.cloud.stream.bindings.handleOrder-in-0.group` xác định consumer group cho binding. Số member thực tế có thể lớn hơn số pod vì mỗi pod có thể tạo nhiều consumer container:

~~~text
Total consumer instances ~ pods × concurrency
Effective parallelism <= topic partition count
~~~

Ví dụ 5 pod, mỗi pod có `concurrency=4`, tạo khoảng 20 consumer cùng group. Nếu topic chỉ có 12 partition, một số consumer sẽ không có partition để làm việc. Điều này **không tự động tạo rebalance storm**, nhưng làm tăng số member tham gia/join/leave khi deploy hoặc autoscale.

Lỗi thường gặp:

- Hai service **khác nghiệp vụ** vô tình dùng cùng group ID và topic, rồi cạnh tranh partition dù được kỳ vọng mỗi service nhận đủ message.
- App thay đổi group ID khi deploy vì biến môi trường hoặc profile, dẫn đến group mới và offset riêng.
- Một số instance dùng cấu hình khác nhau (topic subscription, partition assignor, group protocol), gây join/rebalance không ổn định.
- Gắn `group.instance.id` trùng nhau cho nhiều consumer instance, dẫn đến fencing.
- Dùng chức năng gán partition tĩnh của binder với `auto-rebalance-enabled=false` mà không đồng bộ `instanceCount`/`instanceIndex` cho mọi instance.

Không thay đổi group ID chỉ để “reset” tình trạng rebalance. Việc này có thể khiến ứng dụng đọc lại dữ liệu hoặc bỏ qua dữ liệu, tùy offset hiện có và `auto.offset.reset`.

## 12. Static membership và cooperative rebalancing

Hai cơ chế có thể giảm xáo trộn group trong những môi trường phù hợp:

- **Static membership** qua `group.instance.id`: giúp Kafka nhận diện lại cùng consumer instance sau restart ngắn. ID phải **duy nhất và ổn định cho từng Kafka consumer**, không chỉ từng pod nếu pod có concurrency lớn hơn 1. Trùng ID có thể gây fencing; timeout dài cũng có thể làm việc chuyển partition sang instance khác chậm hơn.
- **Cooperative assignment** trong classic group protocol, ví dụ `CooperativeStickyAssignor`: có thể giảm việc thu hồi toàn bộ partition khi membership thay đổi. Cần kiểm tra client/broker version và tiến hành chuyển đổi assignor đồng bộ, có kiểm soát. Không trộn cấu hình không tương thích giữa các member.

Với `group.protocol=consumer`, assignment và heartbeat có các quy tắc broker-driven riêng; không áp dụng máy móc các hướng dẫn thay `partition.assignment.strategy` của classic protocol.

Đây là tối ưu ổn định membership sau khi đã giải quyết crash, timeout, slow handler và restart loop, không phải lựa chọn đầu tiên để che giấu sự cố.

## 13. Offset commit: phân biệt processed, acknowledged và committed

Trong Spring Kafka message listener container, khi `enable.auto.commit=false`, `AckMode` quyết định **khi nào container commit offset**:

| Ack mode | Thời điểm commit theo semantics chung | Đánh đổi |
|---|---|---|
| `RECORD` | Sau khi listener xử lý xong mỗi record | Commit thường xuyên hơn, cửa sổ redelivery nhỏ hơn |
| `BATCH` | Sau khi xử lý toàn bộ records trả về từ một poll | Ít commit hơn, committed offset có thể tăng theo từng đợt |
| `TIME` | Theo ngưỡng `ackTime` sau khi records của poll được xử lý | Committed offset có thể đứng yên trong một khoảng |
| `COUNT` | Khi số record tích lũy đạt `ackCount` | Tốc độ commit phụ thuộc message rate |
| `COUNT_TIME` | Khi đủ số record hoặc đủ thời gian | Cân bằng frequency và delay |
| `MANUAL` | Ứng dụng gọi `acknowledge()`, sau đó commit theo semantics giống BATCH | Dễ quên ack hoặc ack quá sớm |
| `MANUAL_IMMEDIATE` | Khi gọi `acknowledge()` trên listener thread, commit ngay | Tốn chi phí commit hơn; cần chú ý thread/callback |

Đây là semantics của listener container khi không dùng transaction. Spring Cloud Stream Kafka Binder có thể đặt mặc định khác theo phiên bản và cấu hình, đặc biệt khi dùng record mode hoặc batch mode; **kiểm tra ack mode hiệu lực** trong runtime, đừng suy ra chỉ từ default của Kafka client.

Khi dùng Kafka transaction, offset thường được gửi vào transaction và commit theo transaction; không diễn giải tần suất commit như container không transaction.

## 14. Vì sao committed offset “đứng yên” khi handler vẫn chạy?

Có thể hoàn toàn hợp lý trong những tình huống:

- `BATCH`: consumer vừa nhận batch lớn, nhưng chưa hoàn tất record cuối của poll.
- `TIME` hoặc `COUNT`: ngưỡng commit chưa đạt.
- `MANUAL`: business logic chạy nhưng callback chưa gọi `acknowledge()`.
- Async worker vẫn đang xử lý, listener chưa coi là hoàn tất.
- Retry/backoff đang giữ một record; container chưa được phép tiến offset vượt lỗi đó.
- Kafka Streams đang giữ state/transaction hoặc chờ commit interval riêng.

Phân biệt:

~~~text
Fetched / delivered records
        |
        v
Business processing completed?
        |
        +-- no -> slow handler, dependency, retry, poison message
        |
        v
Acknowledgement reached?
        |
        +-- no -> ACK mode, missing manual ack, async completion
        |
        v
Offset commit attempted?
        |
        +-- no -> threshold/transaction timing, container lifecycle
        |
        v
Commit request sent and accepted by coordinator?
        |
        +-- no -> rebalance, coordinator/network, request timeout
        |
        v
Committed offset advances
~~~

Không ép committed offset tăng bằng cách ack trước khi dữ liệu thực sự được ghi bền vững: cách đó có thể gây mất dữ liệu nghiệp vụ khi process crash.

## 15. Manual acknowledgement: kiểm tra đúng header và thread

Khi bật `MANUAL` hoặc `MANUAL_IMMEDIATE` cho Kafka binding, `Message` có thể mang `KafkaHeaders.ACKNOWLEDGMENT`. Một consumer minh họa:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

@Bean
Consumer<Message<OrderEvent>> handleOrder(OrderService orderService) {
    return message -> {
        // Complete the durable business operation before acknowledging.
        orderService.saveIdempotently(message.getPayload());

        Acknowledgment ack = message.getHeaders().get(
            KafkaHeaders.ACKNOWLEDGMENT, Acknowledgment.class);
        if (ack == null) {
            throw new IllegalStateException(
                "Kafka acknowledgment header is missing");
        }
        ack.acknowledge();
    };
}
~~~

Với binding `handleOrder-in-0`, cấu hình:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.events
          group: order-service
      kafka:
        bindings:
          handleOrder-in-0:
            consumer:
              ack-mode: MANUAL
~~~

Chú ý:

- `MANUAL` không đồng nghĩa với một request commit ngay lập tức; container áp dụng cơ chế BATCH sau khi đã được acknowledge.
- `MANUAL_IMMEDIATE` có semantics commit ngay khi acknowledgement được gọi trên listener thread; từ thread khác có thể có hành vi khác theo cấu hình container/version.
- Không giả định `acknowledge()` trả về nghĩa là broker đã commit sync hoàn tất trong mọi mode.
- Nếu gọi worker bất đồng bộ rồi ack trước khi worker ghi kết quả, một lần crash có thể làm message biến mất khỏi góc nhìn consumer group dù nghiệp vụ chưa hoàn thành.
- Nếu bỏ sót ack trên một nhánh return/exception, committed offset có thể đứng yên hoặc hình thành gap.
- Với `asyncAcks` của Spring Kafka, out-of-order ack có thể làm container tạm pause cho đến khi các gap được lấp. Đây không phải cơ chế tăng throughput miễn phí.

Không thay `MANUAL` bằng `RECORD` chỉ để che lỗi quên acknowledgement; trước hết phải xác minh rằng việc chuyển policy không phá vỡ semantics hệ thống.

## 16. Commit sync, async và độ trễ từ coordinator

Kafka consumer có hai cách cơ bản để lưu offset:

- `commitSync()`: chờ coordinator trả kết quả hoặc hết timeout; có thể chặn poll thread và tăng xử lý chậm khi broker/network bất ổn.
- `commitAsync()`: gửi commit bất đồng bộ; cần callback/log để nhìn thấy lỗi và phải hiểu rủi ro khi không kiểm soát thứ tự callback hoặc shutdown.

Trong Spring Kafka listener container, thuộc tính `syncCommits` quyết định cơ chế dùng và mặc định container thường là `true`. Có thể tùy biến listener container qua cơ chế của Spring Kafka/Spring Cloud Stream khi thật sự cần thay đổi. Không tự chuyển sang async commit chỉ để có p99 thấp hơn mà chưa kiểm thử restart, rebalance và khả năng redelivery.

Để xác định commit thật sự chậm:

1. Kiểm tra Kafka client metrics `commit-latency-avg` và `commit-latency-max`.
2. So sánh `commit-rate`, `commit-total` với expected ack mode và message rate.
3. Xem lỗi `CoordinatorNotAvailable`, timeout, `NotCoordinator`, network reconnection.
4. Kiểm tra broker coordinator, disk/network, throttling, `__consumer_offsets` và broker restarts.
5. Phân biệt thời gian **chờ điều kiện commit** với thời gian **commit request** sau khi gửi.

Nếu committed offset nhảy mỗi 5 giây và `commit-latency-avg` luôn thấp, đó thường là policy/threshold chứ không phải broker commit chậm.

## 17. Retry, DLQ và handler chậm

Trong Spring Cloud Stream, retry có thể thực hiện trong binder hoặc qua listener container/error handler. Mỗi lần xử lý lại có thể giữ một partition/consumer bận. Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        handleOrder-in-0:
          consumer:
            max-attempts: 4
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
      kafka:
        bindings:
          handleOrder-in-0:
            consumer:
              enable-dlq: true
~~~

Các con số chỉ là ví dụ. Khi dependency lỗi kéo dài, tính cả processing time, HTTP timeout, retry count và backoff. Một message poison được retry hàng chục lần hoặc bị requeue liên tục có thể khiến poll interval và committed offset bị ảnh hưởng đáng kể.

Giải pháp:

- Phân loại **transient error** và **permanent error**; không retry vô hạn lỗi schema/business rule.
- Đặt timeout cho dependency; giới hạn retry/backoff.
- Dùng DLQ/recovery cho record không thể xử lý sau số lần thử được phép; giám sát DLQ và replay có kiểm soát.
- Khi retry kéo dài, dùng `DefaultErrorHandler`/container phù hợp thay vì block listener thread không kiểm soát. Spring Kafka có cơ chế pause/continue polling trong một số handler để giữ consumer sống.
- Với `batch-mode`, kiểm tra semantics retry riêng; không mặc định `max-attempts` của binder hoạt động như record mode.
- Khi chỉnh policy, giữ idempotency vì một record có thể được xử lý nhiều lần sau revoke, lỗi commit hoặc restart.

Không bật `enable.auto.commit=true` để “thoát rebalance” khi logic cần at-least-once. Auto commit không bảo đảm công việc nghiệp vụ đã xong, và nó không chữa vấn đề poll/heartbeat gốc.

## 18. Khi broker hoặc coordinator là nút thắt

Nếu handler nhanh, poll đều và pod ổn định nhưng commit latency/heartbeat latency tăng, hãy điều tra:

- Broker coordinator đang restart, bầu leader lại hoặc bị quá tải.
- Tình trạng broker request queue, CPU, disk I/O, `__consumer_offsets` replication và ISR.
- Network jitter, packet loss, TLS handshake hoặc DNS lookup chậm.
- Kafka client metadata không ổn định; firewall, load balancer hoặc NAT idle timeout.
- ACL/SASL/token refresh gây authentication errors hoặc connection churn.
- Consumer group có quá nhiều member và rebalance tốn thời gian.
- Kafka broker/client version hoặc group protocol không tương thích sau nâng cấp.

Đối chiếu metrics trên **cả client và broker** tại cùng timestamp. Sửa client timeout trong khi broker liên tục thay coordinator chỉ làm kéo dài thời gian phát hiện sự cố. Cần phối hợp đội vận hành Kafka và dùng metrics broker có quyền truy cập phù hợp.

## 19. Metrics cần có trên dashboard

| Metric/tín hiệu | Hướng diễn giải | Chú ý |
|---|---|---|
| `rebalance-total` / `rebalance-rate-per-hour` | Tần suất rebalance | Đối chiếu với deploy/HPA |
| `rebalance-latency-avg/max` | Thời gian hoàn tất rebalance | Tên metric phụ thuộc version/client |
| `heartbeat-rate` | Có gửi heartbeat đều không | Cách dùng thay đổi theo group protocol |
| `heartbeat-response-time-max` | Coordinator trả lời heartbeat chậm? | So với request/network errors |
| `last-poll-seconds-ago` | Bao lâu chưa gọi poll | Cần đặt cạnh `max.poll.interval.ms` |
| `time-between-poll-max` | Khoảng cách lớn nhất giữa poll | Phát hiện handler hoặc retry chặn |
| `commit-latency-avg/max` | Thời gian request commit | Phân biệt với chờ ack |
| `commit-rate` / `commit-total` | Tần suất commit | Không nhất thiết bằng message rate |
| `assigned-partitions` | Partition đang giữ | Thay đổi đột ngột có thể báo rebalance |
| Consumer lag theo partition | Backlog theo group | Cần kết hợp throughput và completion |
| GC pause / CPU throttling / pod restarts | Runtime có đang mất khả năng poll/heartbeat? | Dùng cùng timeline |
| Processing p95/p99 / retry / DLQ | Công việc nội bộ có quá chậm không? | Phân tách theo dependency |

Kafka client exposes nhiều metrics qua JMX; Spring Boot Actuator/Micrometer có thể cung cấp một phần metrics tùy dependency và cấu hình. Tên meter sau khi chuyển từ JMX sang Micrometer có thể khác. Không giả định dashboard có sẵn mọi metric nếu chưa cấu hình instrumentation.

Đề xuất alert dựa trên **kết hợp**: rebalance tăng bất thường + lag tăng + throughput giảm, hoặc poll interval tiến gần ngưỡng + p99 handler cao. Một lần rebalance khi rolling deploy không nên tự động bị báo lỗi nghiêm trọng.

## 20. Runbook xử lý theo nhánh nguyên nhân

### Nhánh A — Poll quá chậm

1. Đo `time-between-poll-max` và p99 handler duration.
2. Kiểm tra số record mỗi poll, batch-mode, retry và external I/O.
3. Thử giảm `max.poll.records` trong môi trường kiểm thử.
4. Nếu chậm do dependency, bổ sung timeout/circuit breaker, batching phù hợp hoặc tăng capacity dependency.
5. Chỉ tăng `max.poll.interval.ms` sau khi có budget rõ và kiểm tra failover.

### Nhánh B — Heartbeat/session lỗi

1. Kiểm tra nhóm `session timeout`, heartbeat error và coordinator errors.
2. Xác định `group.protocol` thực tế: `classic` hay `consumer`.
3. Đối chiếu GC pause, CPU throttling, pod restarts và network telemetry.
4. Kiểm tra broker coordinator/metadata và sự cố mạng.
5. Chỉ điều chỉnh session/heartbeat timeout ở đúng phía client/broker theo protocol và policy cluster.

### Nhánh C — Commit offset không tăng

1. Xác minh handler đã **hoàn thành nghiệp vụ** hay chỉ đã nhận record.
2. Xác định `ack-mode` và `enable.auto.commit` hiệu lực.
3. Kiểm tra `MANUAL` có gọi ack đủ mọi nhánh thành công không.
4. So sánh commit metrics với policy `BATCH`/`COUNT`/`TIME`.
5. Nếu commit request chậm thật, kiểm tra coordinator/network/broker; nếu commit failed sau rebalance, sửa nguyên nhân membership.

### Nhánh D — Rebalance trùng với deploy

1. So sánh timeline deployment/HPA/pod restart với Kafka group member changes.
2. Sửa startup readiness, graceful shutdown và resource limits.
3. Giảm scale churn, dùng stabilization window.
4. Sau khi ổn định, cân nhắc static membership hoặc cooperative assignment phù hợp protocol.
5. Kiểm thử lại rolling deployment với tải thật.

## 21. Kiểm thử hồi quy với broker thật

Test Binder trong Spring Cloud Stream rất hữu ích cho logic function nhưng **không mô phỏng Kafka group coordinator, heartbeat, poll interval, rebalance hoặc commit offset thực**. Cần Embedded Kafka hoặc Testcontainers/Kafka cluster để kiểm tra các tình huống sau:

| Kịch bản | Thao tác kiểm thử | Điều cần xác minh |
|---|---|---|
| Handler chậm | Tăng xử lý một batch gần `max.poll.interval.ms` | Có/không mất membership theo thời gian thực |
| Poll size | So sánh `max.poll.records` 500 và 100 | Khoảng cách giữa poll, throughput, lag |
| Manual ack | Cố ý chặn một nhánh ack trong test | Offset không tiến sai; phát hiện missing ack |
| Consumer restart | Kill một instance sau khi ghi DB nhưng trước commit | Redelivery xảy ra và business idempotent |
| Rolling deploy | Thêm/bớt consumer member | Rebalance có kết thúc và assignment ổn định |
| Network/coordinator outage | Tạm ngắt broker/coordinator trong môi trường test | Client hồi phục và commit tiếp tục đúng |
| Retry/poison record | Gửi record gây lỗi vĩnh viễn | DLQ/recovery không chặn group vô hạn |
| Commit latency | Tăng network delay có kiểm soát | Commit metrics cảnh báo, consumer xử lý theo SLO |
| Kafka Streams | Tắt/mở instance đang restore state | Rebalance/task movement, state restore và lag |

Với các test cố tình gây sự cố, phải có timeout hữu hạn, topic/group riêng, cleanup và môi trường không ảnh hưởng production. Nếu sử dụng consumer thực, đảm bảo Test Binder auto-configuration không thay thế Kafka Binder.

## 22. Các anti-pattern cần tránh

**Tăng max.poll.interval.ms lên hàng giờ ngay khi thấy rebalance.** Có thể che giấu listener bị kẹt và khiến group mất rất lâu mới phân phối lại partition khi consumer không tiến triển.

**Tăng session.timeout.ms mà không biết group protocol.** Với protocol `consumer`, timeout/heartbeat được điều khiển bởi broker; cấu hình client classic không có tác dụng như mong đợi.

**Đổi group ID hoặc reset offset để lag về 0.** Đây là thay đổi tiến độ đọc, có thể bỏ qua hoặc replay dữ liệu. Chỉ làm theo quy trình xử lý dữ liệu có phê duyệt.

**Ack trước khi ghi dữ liệu.** Mất tiến độ nghiệp vụ khi process crash dù Kafka báo group đã commit.

**Chuyển sang async commit không kiểm tra callback/error.** Có thể giảm blocking nhưng mất khả năng phát hiện commit thất bại hoặc làm sai giả định về shutdown/recovery.

**Bật auto commit bất kể logic.** Offset có thể tiến trước công việc nghiệp vụ; không chữa root cause của rebalance.

**Tạo quá nhiều consumer so với partition.** Không làm tăng mức song song hữu hiệu và gây thêm churn khi scale, dù bản thân nó không trực tiếp gây rebalance storm.

**Chỉ nhìn log CommitFailedException.** Bỏ qua event revoke và lý do group mất membership ngay trước đó.

**Dùng liveness probe dựa trên consumer lag.** Khi backlog tăng, Kubernetes có thể kill pod khỏe mạnh, làm rebalance thường xuyên và backlog càng tăng.

**Không phân biệt Kafka Streams và regular binder.** Kafka Streams có stream thread/task, state store, restore và commit interval riêng; không sao chép toàn bộ ackMode container của regular Kafka Binder sang Kafka Streams.

## 23. Phân biệt Kafka Streams Binder, RabbitMQ và Pulsar

Đối với **regular Kafka Binder**, `ack-mode` và Spring Kafka listener container là tâm điểm của commit. Đối với **Kafka Streams Binder**, Kafka Streams điều khiển poll loop, task assignment, state store, restoration và commit theo cơ chế stream processing. Những lần rebalance do task migration hoặc restore state có thể làm lag và throughput thay đổi; hãy quan sát stream thread state, task assignment, restore metrics và `application.id`. Kafka Streams `processing.guarantee` và `commit.interval.ms` có ý nghĩa khác với Spring Kafka listener `ackMode`.

Đối với **RabbitMQ Binder**, không có consumer group rebalance/offset commit của Kafka. Vấn đề tương tự về độ tin cậy thường được chẩn đoán qua queue depth, unacked count, consumer acknowledgements, prefetch và connection/channel recovery. **Pulsar** sử dụng subscription/cursor và cơ chế reassignment của riêng broker. Không áp dụng `max.poll.interval.ms` của Kafka cho RabbitMQ hoặc Pulsar.

Nếu ứng dụng dùng nhiều binder, xác nhận binding đang lỗi thực sự gắn với binder nào trước khi chỉnh cấu hình.

## 24. Checklist trước khi đóng sự cố

- [ ] Đã xác nhận rebalance có bất thường chứ không chỉ do rolling deploy hợp lệ.
- [ ] Đã xác định topic, group, binding, binder, partition count, member count và concurrency.
- [ ] Đã lưu timeline log revoke/join/assign, commit errors và pod restarts.
- [ ] Đã đo `max.poll.interval.ms` so với `time-between-poll-max` và duration xử lý.
- [ ] Đã phân biệt `max.poll.interval.ms` với heartbeat/session timeout.
- [ ] Đã kiểm tra group protocol `classic`/`consumer` trước khi chỉnh heartbeat/session.
- [ ] Đã so sánh committed offset, lag, business completion và ack mode.
- [ ] Đã đo commit request latency để phân biệt commit chậm thật với commit ít lần.
- [ ] Với MANUAL ack, mọi nhánh thành công đều ack đúng thời điểm.
- [ ] Retry/backoff/DLQ và dependency timeout không chặn poll vượt SLO.
- [ ] CPU/GC, network, broker coordinator và deploy/HPA đã được kiểm tra.
- [ ] Không đổi group ID, reset offsets hoặc giảm durability ngoài kế hoạch.
- [ ] Đã kiểm thử restart/rebalance và xác minh idempotency trên Kafka thật.
- [ ] Dashboard/alert theo dõi rebalance rate, commit latency, poll gap, lag và pod health.
- [ ] Có bằng chứng sau sửa: membership ổn định, commit tiến đều theo policy, lag giảm và throughput/latency đạt mục tiêu.

**Kết luận:** khi consumer rebalance liên tục, hãy truy ngược từ log revoke/join tới **poll interval, heartbeat/session, membership thay đổi hoặc coordinator**. Khi committed offset tăng chậm, hãy xác minh **business completion → acknowledgement policy → commit request → coordinator** trước khi kết luận Kafka commit chậm. Trong Spring Cloud Stream, một thay đổi nhỏ như giảm `max.poll.records` hoặc sửa manual ack có thể giải quyết sự cố; nhưng chỉ điều chỉnh sau khi có số đo, giữ nguyên group/destination và kiểm thử lại semantics xử lý trùng hoặc phát lại.

## Tài liệu tham khảo

- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — Kafka Binder Tips, Manual Acknowledgement](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_tips.html)
- [Spring for Apache Kafka — Message Listener Containers and Committing Offsets](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/44/configuration/consumer-configs/)
- [Apache Kafka — Monitoring and Consumer Group Metrics](https://kafka.apache.org/44/operations/monitoring/)
- [Spring Cloud Stream — Kafka Streams Binder Reference](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/index.html)
