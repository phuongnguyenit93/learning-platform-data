# Giảm rebalance khi triển khai hoặc khởi động lại ứng dụng

Mỗi khi một consumer gia nhập, rời consumer group hoặc mất kết nối đủ lâu, Kafka có thể phải phân công lại các partition. Quá trình này gọi là **rebalance**. Rebalance là cơ chế cần thiết để group thích nghi với thay đổi thành viên, nhưng nếu xảy ra liên tục trong lúc triển khai hoặc khởi động lại ứng dụng, việc đọc dữ liệu có thể bị gián đoạn, consumer phải xử lý lại record và độ trễ tăng.

Để giảm rebalance không cần thiết, cần phối hợp cách triển khai ứng dụng, thời gian shutdown, cơ chế assignment và cấu hình membership. Ba hướng quan trọng là triển khai rolling có kiểm soát, dùng **static membership** khi instance có danh tính ổn định và dùng **cooperative-sticky assignor** để chỉ thu hồi những partition thực sự cần chuyển.

## 1. Vì sao triển khai ứng dụng gây rebalance?

Consumer group duy trì danh sách thành viên và phân công partition cho từng consumer. Khi membership hoặc subscription thay đổi, group coordinator phối hợp với các thành viên để cập nhật assignment.

Các tình huống thường gặp:

- Một consumer mới khởi động và tham gia group.
- Một consumer dừng bình thường hoặc bị crash.
- Container/pod bị thay thế trong quá trình deploy.
- Liveness/readiness probe làm instance restart liên tục.
- Mạng giữa consumer và broker gián đoạn khiến heartbeat không đến được coordinator.
- Consumer không gọi poll trong thời gian cho phép vì xử lý batch quá lâu.
- Số partition, subscription hoặc cấu hình partition assignor thay đổi.

Trong một đợt rolling deployment, nếu tất cả instance cùng dừng rồi khởi động lại, group có thể trải qua nhiều lần membership change. Với eager rebalance, các thành viên có thể phải dừng xử lý và thu hồi toàn bộ partition trước khi assignment mới được áp dụng. Nếu deploy từng instance nhưng instance mới và cũ liên tục gia nhập/rời group, vẫn có thể tạo nhiều lần rebalance.

~~~mermaid
flowchart TD
    A["Triển khai phiên bản mới"] --> B["Consumer cũ dừng"]
    B --> C["Group nhận membership change"]
    C --> D["Coordinator khởi tạo rebalance"]
    D --> E["Partition được phân công lại"]
    E --> F["Consumer tiếp tục poll"]
    F --> G["Ứng dụng ổn định"]
~~~

Mục tiêu vận hành là giảm số lần membership change và giảm lượng partition phải dừng/di chuyển trong mỗi lần rebalance. Không thể loại bỏ hoàn toàn rebalance khi topology group thực sự thay đổi.

## 2. Phân biệt eager và cooperative rebalance

Partition assignor quyết định cách phân phối partition cho các thành viên trong group. Hai kiểu giao thức quan trọng là eager và cooperative.

### Eager rebalance

Trong eager rebalance, các consumer tham gia group thu hồi toàn bộ partition đang giữ trước khi nhận assignment mới. Vì vậy, một thay đổi nhỏ về membership có thể làm nhiều partition tạm ngừng được xử lý, kể cả partition không cần chuyển sang consumer khác.

### Cooperative rebalance

Cooperative rebalance cho phép chuyển partition theo từng bước. Consumer chỉ thu hồi các partition cần chuyển; các partition vẫn thuộc consumer đó có thể tiếp tục được xử lý. Ở vòng rebalance tiếp theo, group hoàn tất việc chuyển giao những partition đã được thu hồi.

**Cooperative-sticky assignor** kết hợp hai mục tiêu:

- Sticky: cố gắng giữ partition ở consumer cũ nếu assignment vẫn hợp lệ, giảm lượng partition di chuyển.
- Cooperative: chỉ thu hồi partition cần chuyển thay vì thu hồi toàn bộ assignment cùng lúc.

| Tiêu chí | Eager | Cooperative |
|---|---|---|
| Phạm vi thu hồi | Có thể thu hồi toàn bộ partition của các member | Chỉ thu hồi partition cần chuyển |
| Gián đoạn xử lý | Có thể rộng hơn | Thường hẹp hơn |
| Số vòng rebalance | Một vòng theo giao thức eager | Có thể cần nhiều vòng để hoàn tất chuyển giao |
| Giữ assignment cũ | Tùy assignor | Sticky cố gắng giữ assignment ổn định |
| Mục tiêu | Đơn giản, tương thích rộng | Giảm partition movement và thời gian gián đoạn |

Cooperative rebalance giảm phạm vi gián đoạn nhưng không bảo đảm không có rebalance. Khi member mất hẳn, thêm consumer hoặc thay đổi số partition, group vẫn phải điều chỉnh assignment.

## 3. Cấu hình CooperativeStickyAssignor

Với Kafka Java Consumer, có thể cấu hình partition assignment strategy:

~~~properties
partition.assignment.strategy=org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

Ví dụ trong Java:

~~~java
import java.util.List;
import java.util.Properties;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;

Properties properties = new Properties();
properties.put("bootstrap.servers", "localhost:9092");
properties.put("group.id", "billing-service");
properties.put("key.deserializer", StringDeserializer.class.getName());
properties.put("value.deserializer", StringDeserializer.class.getName());
properties.put(
    "partition.assignment.strategy",
    "org.apache.kafka.clients.consumer.CooperativeStickyAssignor"
);

KafkaConsumer<String, String> consumer =
    new KafkaConsumer<>(properties);
consumer.subscribe(List.of("orders.events"));
~~~

Trong môi trường có nhiều phiên bản consumer cùng chạy khi rolling upgrade, cần bảo đảm các member có tập assignor tương thích và có một assignor chung. Thay đổi assignment protocol nên được triển khai theo kế hoạch tương thích của phiên bản Kafka client; không nên đồng thời thay đổi nhiều thuộc tính group và assignor trong một lần deploy nếu chưa kiểm thử.

Các Kafka client hiện đại có thể liệt kê nhiều assignor mặc định. Nếu muốn chuyển từ eager sang cooperative, hãy kiểm tra danh sách assignor hiệu lực và cách client chọn assignor chung; chỉ thêm CooperativeStickyAssignor vào cuối danh sách có thể không khiến group sử dụng nó nếu một assignor eager vẫn được ưu tiên.

## 4. Static membership giữ danh tính consumer qua lần restart

Thông thường, consumer tham gia group với member ID do coordinator cấp. Khi consumer dừng, group nhận biết thành viên rời đi và có thể rebalance để phân phối lại partition.

**Static membership** cho phép ứng dụng khai báo một group.instance.id ổn định. Coordinator nhận diện member bằng định danh này qua các lần khởi động lại. Nếu instance quay lại trong khoảng session timeout, nó có thể tiếp tục là cùng một thành viên và giữ assignment cũ, tránh rebalance chỉ vì restart ngắn.

Ví dụ:

~~~properties
group.id=billing-service
group.instance.id=billing-worker-0
session.timeout.ms=60000
~~~

group.instance.id phải duy nhất trong cùng consumer group. Nếu hai consumer đang hoạt động dùng cùng một ID, Kafka có thể fencing một member với lỗi FencedInstanceIdException. Không dùng một giá trị giống nhau cho mọi replica.

### Chọn instance ID ổn định

Giá trị ID cần giữ nguyên khi cùng một instance được khởi động lại, nhưng phải khác với các instance khác trong group.

| Nền tảng triển khai | Cách tạo ID phù hợp |
|---|---|
| Kubernetes StatefulSet | Dùng ordinal ổn định, ví dụ billing-0, billing-1 |
| VM hoặc máy chủ cố định | Dùng tên node/slot đã được quản lý |
| Deployment tạo pod ngẫu nhiên | Cần một cơ chế slot/identity ổn định; pod UID mới mỗi lần restart không giữ được static identity |
| Nhiều consumer trong một JVM | Mỗi consumer phải có ID riêng; kiểm tra cách framework tạo suffix cho từng child container |

Không dùng hostname hoặc pod name nếu nền tảng tạo tên mới sau mỗi lần thay thế mà mục tiêu là giữ nguyên membership qua restart. Đồng thời, không cấp lại một ID cho instance mới khi instance cũ vẫn còn hoạt động.

### Static membership không miễn phí

Static member không cần bị xem là member mới sau một lần restart ngắn. Tuy nhiên, nếu instance chết hẳn, coordinator có thể phải chờ session timeout trước khi kết luận member đã mất và phân phối partition của nó cho consumer khác. Vì vậy:

- Session timeout quá ngắn có thể không đủ cho thời gian restart.
- Session timeout quá dài làm chậm phát hiện instance mất thật.
- Nếu ID bị dùng trùng, member đang hoạt động có thể bị fencing.
- Khi triển khai, cần tính thời gian drain, shutdown, pull image, startup và join group vào cửa sổ restart dự kiến.

Static membership phù hợp với instance có danh tính ổn định và lịch trình restart có thể dự đoán. Với workload có pod thay đổi liên tục, dynamic membership cùng cooperative assignor và rollout tốt có thể phù hợp hơn.

## 5. Cấu hình static membership trong Java

Ví dụ consumer có ID cố định theo slot:

~~~java
Properties properties = new Properties();
properties.put("bootstrap.servers", "localhost:9092");
properties.put("group.id", "billing-service");
properties.put("group.instance.id", "billing-worker-0");
properties.put("session.timeout.ms", 60_000);
properties.put("heartbeat.interval.ms", 20_000);
properties.put("partition.assignment.strategy",
    "org.apache.kafka.clients.consumer.CooperativeStickyAssignor");
properties.put("enable.auto.commit", false);
~~~

Giá trị billing-worker-0 là ví dụ. Mỗi replica phải nhận ID riêng và ID của cùng slot phải được giữ ổn định qua restart.

Với dynamic membership, consumer thường gửi LeaveGroup khi đóng bình thường để coordinator có thể phân công lại sớm. Với static membership, việc rời tạm thời được xử lý khác: coordinator có thể giữ membership đến khi session timeout thay vì lập tức xóa slot đó. Điều này hỗ trợ restart nhanh mà không rebalance ngay.

## 6. Heartbeat, session timeout và max poll interval

Ba cấu hình này điều khiển những khía cạnh khác nhau của liveness:

| Cấu hình | Ý nghĩa |
|---|---|
| heartbeat.interval.ms | Khoảng cách giữa các heartbeat mà consumer gửi đến group coordinator trong giao thức consumer group cổ điển |
| session.timeout.ms | Thời gian coordinator chờ heartbeat hợp lệ trước khi xem member mất kết nối |
| max.poll.interval.ms | Thời gian tối đa giữa hai lần poll; vượt ngưỡng cho thấy ứng dụng không xử lý/tiến triển đúng nhịp |

Với giao thức consumer group cổ điển, heartbeat.interval.ms thường được đặt thấp hơn session.timeout.ms, thường khoảng một phần ba session timeout. Đây là quan hệ cấu hình tham khảo; hãy kiểm tra ràng buộc của client và broker.

Heartbeat thành công không có nghĩa ứng dụng đã xử lý record. Consumer có thể tiếp tục heartbeat trong lúc code nghiệp vụ bị treo hoặc đang xử lý quá lâu. max.poll.interval.ms bổ sung cơ chế phát hiện tình huống consumer không gọi poll đủ thường xuyên.

Khi vượt max.poll.interval.ms:

- Consumer có thể bị xem là không còn tiến triển và group cần phân phối lại partition.
- Với static membership, việc phân phối lại có thể bị trì hoãn đến khi session timeout hết hạn.
- Nếu tăng max.poll.interval.ms, thời gian phát hiện consumer bị treo cũng dài hơn.

Không nên tăng session.timeout.ms và max.poll.interval.ms một cách máy móc để giảm rebalance. Trước hết hãy đo thời gian xử lý batch, poll gap, GC pause và thời gian restart thực tế.

### Lưu ý về consumer group protocol mới

Ở các Kafka client/broker hỗ trợ consumer group protocol mới (group.protocol=consumer), một số thiết lập heartbeat và session timeout được broker quản lý thay vì dùng hoàn toàn các thuộc tính client cổ điển. Các tên cấu hình và giới hạn có thể khác theo phiên bản. Hãy xác nhận protocol đang dùng trước khi áp dụng các ví dụ heartbeat/session timeout trong bài.

## 7. Shutdown graceful để tránh mất tiến độ

Khi ứng dụng dừng, cần cho consumer thời gian hoàn tất công việc đang xử lý và lưu checkpoint an toàn:

1. Ngừng nhận công việc mới hoặc ngừng dispatch record sang worker.
2. Chờ các record đang xử lý hoàn tất trong giới hạn shutdown budget.
3. Commit offset của các record đã hoàn tất liên tục theo từng partition.
4. Đóng consumer/listener container đúng cách.
5. Cho tiến trình kết thúc trước khi orchestrator gửi SIGKILL.

Nếu consumer commit trước khi xử lý xong, ứng dụng có thể bỏ qua record khi restart. Nếu xử lý xong nhưng chưa commit, record có thể được đọc lại. Vì vậy, xử lý nghiệp vụ nên idempotent khi tác dụng phụ có thể lặp.

Với Java Consumer API, có thể dùng wakeup() để đánh thức poll từ thread khác và đóng consumer trong thread sở hữu consumer:

~~~java
private final AtomicBoolean running = new AtomicBoolean(true);
private KafkaConsumer<String, String> consumer;

public void stop() {
    running.set(false);
    consumer.wakeup();
}

public void run() {
    try {
        while (running.get()) {
            var records = consumer.poll(Duration.ofMillis(500));
            processAndCommitSafely(records);
        }
    } catch (WakeupException exception) {
        if (running.get()) {
            throw exception;
        }
    } finally {
        consumer.close(Duration.ofSeconds(30));
    }
}
~~~

Đây là khung minh họa. processAndCommitSafely phải bảo đảm chỉ commit các offset đã xử lý hoàn tất. Không gọi các API KafkaConsumer tùy tiện từ thread shutdown; KafkaConsumer không thread-safe và wakeup() là cơ chế đánh thức được thiết kế cho tình huống này.

Trong Spring Kafka, để container quản lý lifecycle listener, dùng cơ chế shutdown của Spring ApplicationContext và cấu hình thời gian chờ phù hợp. Không tự tạo consumer khác trong @PreDestroy để commit thay consumer đang chạy.

## 8. Rolling deployment với nhiều replica

Triển khai lần lượt giúp giảm số member thay đổi cùng lúc:

1. Xác định số replica, số partition và consumer concurrency hiện tại.
2. Chọn maxUnavailable nhỏ, thường bắt đầu từ 1 với workload cần tính sẵn sàng cao.
3. Chờ pod mới sẵn sàng và consumer gia nhập group ổn định trước khi tiếp tục thay thế pod kế tiếp.
4. Cho pod cũ drain công việc và shutdown graceful.
5. Theo dõi rebalance count, consumer lag, thời gian không có consumer xử lý và lỗi commit trong suốt đợt deploy.

Với Kubernetes Deployment, có thể dùng rolling update:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: billing-consumer
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: app
          image: example/billing-consumer:1.2.0
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 10"]
~~~

Đây là ví dụ khung, không phải cấu hình dùng nguyên trạng cho mọi cluster. preStop sleep chỉ tạo khoảng thời gian trước khi container nhận tín hiệu dừng; nó không tự drain Kafka listener. Ứng dụng vẫn cần xử lý SIGTERM, dừng nhận record mới và hoàn tất công việc. terminationGracePeriodSeconds phải lớn hơn thời gian drain/shutdown thực tế; nếu hết hạn, Kubernetes có thể buộc dừng container.

Khi dùng maxSurge: 1, pod mới có thể gia nhập group trước khi pod cũ rời đi, làm membership tăng tạm thời và kích hoạt rebalance. Cooperative assignor giúp thu hồi ít partition hơn; static membership có thể giúp giữ slot nếu định danh và rollout được thiết kế đúng. Cần thử trên môi trường staging để xác nhận trình tự thực tế.

Nếu kết hợp static membership với maxSurge lớn hơn 0, không để pod mới dùng lại group.instance.id của pod cũ trong lúc cả hai còn chạy. Hai member cùng ID sẽ fencing lẫn nhau hoặc khiến một member bị loại khỏi group. Chỉ chuyển một slot sau khi member cũ đã dừng và ID được giải phóng; với StatefulSet, rollout theo ordinal giúp quản lý slot ổn định hơn.

## 9. Cấu hình Spring Boot và Spring Kafka

Ví dụ cấu hình consumer dùng cooperative-sticky assignor và static instance ID:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      properties:
        partition.assignment.strategy: org.apache.kafka.clients.consumer.CooperativeStickyAssignor
        group.instance.id: ${KAFKA_GROUP_INSTANCE_ID}
        session.timeout.ms: 60000
        heartbeat.interval.ms: 20000
        max.poll.interval.ms: 300000
    listener:
      ack-mode: record
~~~

KAFKA_GROUP_INSTANCE_ID phải được cấp riêng cho mỗi consumer instance và ổn định khi cùng instance restart. Không để mọi replica nhận chung một giá trị.

Nếu listener container có concurrency lớn hơn 1, mỗi child consumer cần có group instance ID duy nhất. Một số phiên bản Spring Kafka hỗ trợ tự thêm suffix cho group.instance.id theo concurrency; hãy xác minh hành vi của phiên bản framework đang dùng và kiểm tra ID thực tế khi consumer khởi động.

AckMode record chỉ là ví dụ về thời điểm container commit sau khi listener xử lý record thành công. Chọn RECORD, BATCH hoặc MANUAL theo semantics xử lý của ứng dụng; cấu hình ack không tự ngăn rebalance nếu listener xử lý quá lâu.

## 10. Giảm rebalance do xử lý lâu hoặc lỗi ứng dụng

Không phải mọi rebalance đều do deploy. Consumer có thể liên tục rời group nếu:

- Xử lý một batch quá lâu và vượt max.poll.interval.ms.
- GC pause kéo dài làm consumer không poll/heartbeat đúng nhịp.
- Database/API downstream chậm khiến listener bị chặn.
- Container thiếu CPU hoặc memory dẫn đến throttling/OOM.
- Readiness/liveness probe đặt quá nhạy, gây restart dù ứng dụng chỉ đang tải cao.

Các biện pháp:

- Đo thời gian xử lý p95/p99 và điều chỉnh max.poll.records phù hợp.
- Tách I/O chậm khỏi luồng poll nhưng giới hạn worker queue và giữ thứ tự commit an toàn.
- Tăng tài nguyên hoặc tối ưu dependency gây nghẽn.
- Thiết lập probe theo trạng thái ứng dụng thực tế; không dùng lag nhất thời làm liveness failure.
- Tăng max.poll.interval.ms chỉ khi có số liệu chứng minh batch cần thời gian dài hơn.
- Theo dõi GC pause, CPU throttling, OOM và số lần restart của pod.

## 11. Khi nào rebalance là cần thiết?

Không nên tìm cách loại bỏ mọi rebalance. Một số thay đổi đòi hỏi group cập nhật assignment:

| Thay đổi | Vì sao cần điều chỉnh |
|---|---|
| Tăng/giảm số consumer | Phân phối lại partition để tận dụng member mới hoặc xử lý member đã mất |
| Tăng số partition của topic | Có partition mới cần được giao cho consumer |
| Thay đổi subscription | Tập partition mà group cần đọc thay đổi |
| Member mất hẳn | Partition của member cần được giao lại để tiếp tục xử lý |
| Thay đổi assignor/protocol | Group cần thống nhất cách phân phối assignment |

Cooperative assignor, static membership và rolling deploy giúp giảm rebalance do thay đổi tạm thời. Chúng không thay thế nhu cầu phân phối lại khi topology thực sự thay đổi.

## 12. Theo dõi rebalance trong triển khai

Trong mỗi đợt deploy hoặc restart, nên theo dõi:

- Số lần rebalance và thời lượng mỗi lần.
- Số partition bị revoke/assign ở từng member.
- Consumer group state và số member đang hoạt động.
- Consumer lag theo partition và tốc độ xử lý sau rebalance.
- Thời gian startup, thời gian join group và thời gian listener sẵn sàng.
- Số lần restart, lý do restart và thời gian shutdown.
- max.poll.interval.ms violation, heartbeat/session timeout và lỗi coordinator.
- CPU, memory, GC pause, network latency và downstream request latency.

Các công cụ thường dùng:

~~~bash
bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group billing-service
~~~

Trên Windows, dùng kafka-consumer-groups.bat trong bin/windows. Lệnh này giúp xem member/assignment/lag theo phiên bản CLI; để biết nguyên nhân rebalance và thời lượng chính xác, cần kết hợp log consumer, log coordinator và metric của client/broker.

## 13. Runbook khi deploy gây rebalance liên tục

1. Kiểm tra group ID có giữ nguyên giữa phiên bản cũ và mới hay không.
2. Kiểm tra số member, partition assignment và thời điểm từng pod restart.
3. Đối chiếu log để xác định rebalance do LeaveGroup, session timeout, poll timeout hay subscription/partition change.
4. Xác minh partition assignor hiệu lực; nếu cần, lập kế hoạch chuyển sang CooperativeStickyAssignor.
5. Nếu dùng static membership, kiểm tra group.instance.id có ổn định và duy nhất không.
6. Kiểm tra graceful shutdown, termination grace period và thời gian drain.
7. Đo batch processing time, poll gap, heartbeat, GC và downstream latency.
8. Triển khai lại theo rolling với số pod unavailable nhỏ và chờ group ổn định giữa các bước.
9. Xác nhận lag trở về mức bình thường, partition assignment ổn định và không có lỗi commit trước khi kết thúc rollout.

Không thay đổi đồng thời group ID, partition count, assignor, static instance ID và timeout nếu chưa có kế hoạch chuyển đổi. Thay đổi nhiều yếu tố cùng lúc khiến việc tìm nguyên nhân rebalance khó hơn và có thể tạo assignment mới ngoài dự kiến.

## 14. Bài tập tự kiểm tra

1. Vì sao restart một dynamic member có thể kích hoạt rebalance?
2. Cooperative rebalance khác eager rebalance ở phạm vi partition bị thu hồi như thế nào?
3. Vì sao group.instance.id phải vừa ổn định vừa duy nhất?
4. Static member restart trong session timeout có thể tránh rebalance bằng cách nào? Đổi lại, điều gì xảy ra khi instance chết hẳn?
5. max.poll.interval.ms khác session.timeout.ms ở điểm nào?
6. Vì sao preStop: sleep 10 không đủ để bảo đảm consumer đã drain an toàn?
7. Khi rolling deploy có maxSurge: 1, vì sao số member của group có thể tăng tạm thời?

## Kết luận

Giảm rebalance khi triển khai hoặc khởi động lại ứng dụng cần kết hợp nhiều lớp. Cooperative-sticky assignor hạn chế số partition phải thu hồi và di chuyển; static membership giữ danh tính consumer qua lần restart ngắn; graceful shutdown và rolling deployment giúp thay đổi membership có kiểm soát. Các timeout heartbeat, session và poll phải được chọn theo thời gian restart, thời gian xử lý và yêu cầu phát hiện sự cố.

Hãy đo rebalance, partition movement, consumer lag, poll gap và thời gian shutdown trong staging trước khi triển khai rộng. Mục tiêu là để consumer tiếp tục xử lý ổn định qua những lần restart dự kiến, đồng thời vẫn phát hiện và thay thế member thực sự đã mất.
