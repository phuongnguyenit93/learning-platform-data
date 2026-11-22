# Ranh giới trách nhiệm giữa ứng dụng và broker

Trong một hệ thống Spring Kafka đáng tin cậy, ứng dụng và Kafka broker cùng tham gia vào đường đi của một message, nhưng mỗi bên chịu trách nhiệm cho một phần khác nhau. Ứng dụng quyết định **message có ý nghĩa gì, được gửi và xử lý như thế nào, khi nào được xem là xử lý thành công**. Broker chịu trách nhiệm **tiếp nhận bản ghi, lưu trữ log, sao chép dữ liệu, phân phối bản ghi cho consumer và duy trì trạng thái của consumer group**.

Ranh giới này cần được hiểu rõ khi thiết kế, cấu hình và xử lý sự cố. Broker có thể xác nhận đã ghi một bản ghi vào Kafka, nhưng không thể tự biết một giao dịch trong cơ sở dữ liệu của ứng dụng đã hoàn tất. Ngược lại, ứng dụng có thể xử lý đúng nghiệp vụ, nhưng không thể tự bảo đảm dữ liệu vẫn tồn tại khi một broker hoặc ổ đĩa gặp sự cố nếu cluster không được cấu hình phù hợp.

## 1. Nhìn hệ thống theo hai phía

Một luồng Kafka thông thường có ba thành phần:

- **Producer application**: tạo sự kiện, xác định key, serialize dữ liệu và gửi bản ghi qua Kafka client. Trong ứng dụng Spring, phần này thường dùng **KafkaTemplate**.
- **Kafka broker/cluster**: nhận yêu cầu ghi, quản lý partition và leader, ghi log, sao chép dữ liệu, lưu trữ theo retention policy và phục vụ yêu cầu đọc.
- **Consumer application**: đọc bản ghi, deserialize, thực hiện nghiệp vụ và quyết định thời điểm xác nhận offset. Trong Spring Kafka, phần này thường dùng **@KafkaListener** và listener container.

~~~mermaid
flowchart LR
    A["Ứng dụng producer<br/>Tạo sự kiện, key, serialize"] -->|"Produce request"| B["Kafka broker<br/>Leader, log, replication"]
    B -->|"Produce acknowledgement"| A
    C["Kafka broker<br/>Partition và group coordination"] -->|"Fetch records"| D["Ứng dụng consumer<br/>Deserialize, xử lý nghiệp vụ"]
    D -->|"Commit offset"| C
~~~

Spring Kafka là lớp tích hợp phía ứng dụng. **KafkaTemplate**, listener container, acknowledgement mode, error handler và transaction integration là các cơ chế mà Spring cung cấp để ứng dụng sử dụng Kafka. Chúng không biến Spring thành broker và cũng không thay thế trách nhiệm vận hành cluster.

## 2. Bảng phân định trách nhiệm

| Vấn đề | Ứng dụng / Spring Kafka | Kafka broker / nền tảng |
|---|---|---|
| Ý nghĩa sự kiện | Định nghĩa event, kiểm tra dữ liệu nghiệp vụ, quyết định khi nào phát sinh event | Lưu byte record; không hiểu ý nghĩa nghiệp vụ của event |
| Serialization | Chọn serializer, định dạng payload, quản lý schema và tương thích phiên bản | Nhận và lưu key/value dưới dạng byte |
| Partitioning | Chọn key hoặc partition theo yêu cầu nghiệp vụ; thiết kế key để phân phối tải và giữ thứ tự | Quản lý partition, leader và việc ghi/đọc trên partition |
| Ghi dữ liệu | Cấu hình producer, gửi record, quan sát kết quả và xử lý lỗi gửi | Tiếp nhận request, append vào log và replication theo cấu hình |
| Độ bền dữ liệu | Chọn mức xác nhận phù hợp với yêu cầu của ứng dụng | Thực hiện replication, quản lý ISR và lưu trữ log |
| Đọc dữ liệu | Cấu hình consumer, poll, deserialize và xử lý record | Phục vụ fetch request và điều phối consumer group |
| Offset | Chọn group ID và thời điểm commit theo tiến độ xử lý | Lưu committed offset và quản lý group coordination |
| Nghiệp vụ consumer | Xác định xử lý thành công, chống xử lý trùng và quản lý side effect | Không biết nghiệp vụ đã hoàn tất hay chưa |
| Retry và DLT | Định nghĩa loại lỗi được retry, backoff, số lần thử và quy trình khôi phục | Lưu record retry/DLT nếu ứng dụng gửi chúng vào topic |
| Retention | Đề xuất thời gian lưu dựa trên nhu cầu replay và nghiệp vụ | Áp dụng retention hoặc log compaction cho topic |
| Bảo mật | Quản lý credential, cấu hình client và không để lộ secret | Xác thực, phân quyền và thực thi ACL/authorizer theo cấu hình cluster |
| Năng lực và tính sẵn sàng | Kiểm soát tốc độ gửi/đọc, concurrency và hành vi khi phụ thuộc bị chậm | Quản lý tài nguyên broker, dung lượng, replication, network và khả năng phục vụ |

Một số hạng mục là trách nhiệm chung. Ví dụ, đội nền tảng có thể tạo topic và đặt retention, nhưng đội ứng dụng phải xác định thời gian replay cần thiết. Đội nền tảng có thể cấp ACL, nhưng ứng dụng phải dùng đúng principal và xử lý lỗi authorization. Ranh giới cần được ghi thành thỏa thuận vận hành cho từng topic hoặc domain.

## 3. Đường đi của một bản ghi khi producer gửi

### 3.1 Phần ứng dụng thực hiện

Trước khi Kafka nhận dữ liệu, producer application phải:

1. Quyết định sự kiện nào cần phát ra và bảo đảm nội dung phản ánh đúng trạng thái nghiệp vụ.
2. Chọn key. Key thường là định danh của aggregate hoặc thực thể cần giữ thứ tự, chẳng hạn **orderId**.
3. Serialize key và value thành byte bằng serializer đã cấu hình.
4. Gửi record tới topic. Producer client dùng metadata để xác định partition và broker leader đích.
5. Theo dõi kết quả gửi. Ứng dụng cần xử lý lỗi gửi thay vì giả định lời gọi **send** đồng nghĩa dữ liệu đã được lưu.

Ví dụ với **KafkaTemplate**:

~~~java
kafkaTemplate.send("orders.created", event.orderId(), event)
    .whenComplete((result, error) -> {
        if (error != null) {
            // Ghi nhận lỗi gửi và chuyển sang quy trình phục hồi phù hợp.
            log.error("Could not publish order event", error);
            return;
        }

        // Broker đã xác nhận record theo cấu hình producer.
        log.debug("Published order event to partition {}",
                result.getRecordMetadata().partition());
    });
~~~

Kết quả thành công của future cho biết producer nhận được acknowledgement theo cấu hình gửi. Nó không chứng minh consumer đã đọc record, nghiệp vụ phía consumer đã chạy, hoặc cơ sở dữ liệu đích đã commit.

Nếu API HTTP chỉ được trả về thành công sau khi event được Kafka xác nhận, ứng dụng phải chờ kết quả gửi theo cách phù hợp với thời hạn của request. Nếu nghiệp vụ cập nhật database và phát event phải cùng tồn tại qua sự cố, cần thiết kế outbox hoặc một cơ chế transaction phù hợp; chỉ gọi **KafkaTemplate.send** sau lệnh ghi database không tự tạo ra một giao dịch nguyên tử giữa hai hệ thống.

### 3.2 Phần broker thực hiện

Khi nhận produce request, broker leader của partition đích sẽ kiểm tra request và quyền truy cập theo cấu hình, sau đó append record vào log. Các follower replica lấy dữ liệu từ leader và cập nhật trạng thái replica. Producer nhận acknowledgement dựa trên cấu hình **acks** và trạng thái replication.

Các cấu hình thường được phối hợp:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
~~~

Ở phía cluster, ví dụ một chính sách mặc định:

~~~properties
default.replication.factor=3
min.insync.replicas=2
~~~

Với replication factor bằng 3 và **min.insync.replicas** bằng 2, một lần ghi dùng **acks=all** cần có tối thiểu hai replica trong ISR để được chấp nhận. **acks=all** chờ các replica hiện thuộc ISR xác nhận; nó không có nghĩa là luôn chờ đủ mọi replica được cấu hình ban đầu. Nếu ISR giảm xuống dưới ngưỡng tối thiểu, broker có thể từ chối ghi để giữ mức bảo vệ dữ liệu đã đặt ra.

**default.replication.factor** là giá trị mặc định khi tạo topic nếu không chỉ định replication factor khác. Topic có thể có cấu hình riêng; vì vậy cần kiểm tra cấu hình thực tế của topic, không chỉ nhìn cấu hình mặc định của broker.

### 3.3 Giới hạn của producer idempotence

**enable.idempotence=true** giúp Kafka producer tránh tạo bản ghi trùng do cơ chế retry nội bộ của producer trong phạm vi mà Kafka hỗ trợ. Đây là một lớp bảo vệ quan trọng khi gửi qua mạng không ổn định.

Tuy nhiên, idempotence của producer không tự loại bỏ các sự kiện nghiệp vụ trùng nhau. Ví dụ, một request thanh toán được gửi lại từ client có thể khiến ứng dụng tạo một event mới sau khi producer trước đó đã gửi thành công nhưng response bị thất lạc. Muốn chống trường hợp này, ứng dụng cần idempotency key, kiểm tra trạng thái nghiệp vụ hoặc ràng buộc duy nhất trong database.

Broker cũng không thể tự quyết định hai record có cùng nội dung là cùng một hành động nghiệp vụ. Hai record giống byte vẫn có thể là hai sự kiện hợp lệ.

## 4. Đường đi của một bản ghi khi consumer đọc

### 4.1 Broker quản lý việc phân phối, ứng dụng quản lý việc xử lý

Consumer tham gia một consumer group bằng group ID. Broker group coordinator phối hợp membership, generation và trạng thái group; cơ chế assignor phía consumer xác định partition được giao cho từng consumer. Trong cùng một group, tại một thời điểm, một partition được giao cho tối đa một consumer thành viên đang hoạt động.

Consumer poll record từ broker. Kafka client thực hiện fetch và deserialize theo cấu hình; Spring listener container điều phối việc poll và gọi listener. Listener thực hiện nghiệp vụ như ghi database, gọi dịch vụ khác hoặc phát một event tiếp theo.

Broker có thể biết consumer đã commit offset nào. Broker không thể biết listener đã cập nhật database, gửi email hay hoàn tất một side effect bên ngoài hay chưa.

### 4.2 Offset là vị trí đọc đã xác nhận

Offset là vị trí của record trong một partition. Committed offset cho biết consumer group đã xác nhận vị trí đọc đến đâu. Offset không phải là bằng chứng độc lập rằng mọi side effect nghiệp vụ tương ứng đã hoàn tất.

Trong Spring Kafka, listener container có các acknowledgement mode như **RECORD**, **BATCH**, **MANUAL** và **MANUAL_IMMEDIATE**. Với chế độ container-managed, thời điểm commit phụ thuộc acknowledgement mode và kết quả xử lý listener. Cần chọn mode dựa trên cách ứng dụng xác định một batch hoặc record đã hoàn tất.

Ví dụ consumer:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "billing-service"
)
public void onOrderCreated(OrderCreated event) {
    billingService.applyOnce(event.eventId(), event);
}
~~~

Trong ví dụ, **applyOnce** đại diện cho một thao tác nghiệp vụ có khả năng nhận diện và bỏ qua event đã xử lý. Khi listener kết thúc bình thường, container xử lý acknowledgement/commit theo cấu hình. Nếu listener ném exception, lỗi được chuyển tới error handler đã cấu hình.

### 4.3 Vì sao consumer cần idempotency

Giả sử consumer đọc record ở offset 42 và cập nhật database thành công. Ngay sau đó, process dừng trước khi offset mới được commit. Khi consumer khởi động lại, Kafka có thể giao lại record ở offset 42. Database đã nhận side effect lần đầu, nhưng Kafka vẫn xem record đó là chưa được xác nhận.

Đây là lý do phổ biến khiến consumer cần idempotency. Một số cách thực hiện:

- Lưu **eventId** đã xử lý trong database và đặt unique constraint để cùng một event không tạo side effect lần thứ hai.
- Thiết kế lệnh cập nhật theo kiểu upsert hoặc phép cập nhật có điều kiện để chạy lại vẫn cho kết quả đúng.
- Dùng inbox table để ghi nhận event đã nhận trong cùng transaction với thay đổi nghiệp vụ.
- Đưa side effect ra một outbox nếu cần phát tiếp event sau khi database commit.

Với xử lý database thông thường, lựa chọn phổ biến là at-least-once delivery kết hợp idempotent consumer. Ứng dụng chấp nhận có thể nhận lại record và bảo đảm thao tác nghiệp vụ không bị nhân đôi.

### 4.4 Exactly-once có phạm vi cụ thể

Kafka transactions có thể phối hợp việc đọc record, ghi record đầu ra và commit offset trong một giao dịch Kafka. Consumer đọc với **isolation.level=read_committed** chỉ thấy các record thuộc giao dịch đã commit. Spring Kafka hỗ trợ tích hợp transaction cho các luồng Kafka phù hợp.

Phạm vi này không tự bao trùm một database quan hệ, REST API hoặc hệ thống bên ngoài. Nếu listener cập nhật database rồi ghi Kafka, Kafka transaction không tự rollback được database khi Kafka transaction thất bại. Với luồng có nhiều hệ thống, hãy dùng outbox/inbox, idempotency hoặc một giải pháp phối hợp giao dịch được thiết kế rõ ràng. Chỉ dùng thuật ngữ exactly-once khi xác định được chính xác tài nguyên và side effect nằm trong phạm vi bảo đảm.

## 5. Những bảo đảm broker cung cấp và những việc ứng dụng phải hoàn tất

### 5.1 Lưu trữ, replication và retention

Broker quản lý log của từng partition, replication giữa các broker, leader election và việc áp dụng retention hoặc log compaction. Những cơ chế này bảo vệ và quản lý dữ liệu trong Kafka theo cấu hình cluster/topic.

Ứng dụng phải xác định dữ liệu cần lưu bao lâu, cần replay trong khoảng thời gian nào và có cần lưu trữ lâu dài ở hệ thống khác hay không. Retention không phải kho lưu trữ nghiệp vụ vĩnh viễn. Khi record hết hạn, broker có thể xóa dữ liệu theo chính sách. Với log compaction, Kafka giữ lại giá trị mới nhất theo key theo cơ chế compaction; điều đó không tương đương với việc giữ toàn bộ lịch sử sự kiện.

### 5.2 Thứ tự và partition key

Kafka giữ thứ tự record trong một partition. Broker không bảo đảm thứ tự toàn cục giữa nhiều partition.

Ứng dụng quyết định key và cách xử lý song song. Nếu mọi event của cùng một đơn hàng phải được xử lý theo thứ tự, producer cần dùng key ổn định như **orderId** để các event đó đi vào cùng partition. Consumer cũng cần tránh tự đưa xử lý bất đồng bộ ra ngoài listener theo cách làm các side effect hoàn tất sai thứ tự.

Tăng số partition có thể tăng khả năng song song, nhưng có thể ảnh hưởng phân bố key và thứ tự theo cách ứng dụng cần đánh giá. Broker không thể sửa một thiết kế key không phù hợp với nghiệp vụ.

### 5.3 Retry và dead-letter topic

Có nhiều loại retry khác nhau:

- **Producer retry**: Kafka producer thử gửi lại khi gặp lỗi có thể phục hồi ở tầng giao tiếp hoặc broker.
- **Consumer/listener retry**: ứng dụng thử xử lý lại khi listener gặp lỗi.
- **Business retry**: ứng dụng lên lịch thử lại một thao tác nghiệp vụ sau một khoảng thời gian, có thể cần workflow hoặc retry topic riêng.

Spring Kafka cung cấp cơ chế error handler và recovery, chẳng hạn **DefaultErrorHandler** và **DeadLetterPublishingRecoverer**, để xây dựng chính sách xử lý lỗi. Ứng dụng phải xác định lỗi nào có thể retry, backoff bao lâu, giới hạn số lần thử, lỗi nào không nên retry và khi nào chuyển record sang DLT.

Dead-letter topic là một topic Kafka bình thường. Broker chỉ lưu record được producer gửi tới topic đó. Broker không tự tạo DLT, không tự quyết định record nào là poison message và không tự lên lịch replay. Ứng dụng và đội nền tảng cần thống nhất quyền ghi/đọc, retention, dung lượng, cảnh báo, định dạng metadata lỗi và quy trình replay. Khi replay, cần giữ khả năng nhận diện event cũ để không lặp lại side effect.

### 5.4 Schema và dữ liệu không hợp lệ

Broker lưu key/value dưới dạng byte. Broker không xác minh rằng JSON có đúng trường bắt buộc, Avro schema tương thích hay một giá trị trạng thái hợp lệ với domain.

Ứng dụng chịu trách nhiệm serialize/deserialize, xác thực dữ liệu nghiệp vụ và xử lý lỗi schema. Nếu tổ chức dùng Schema Registry, registry và chính sách compatibility là một phần của nền tảng dữ liệu; producer/consumer vẫn phải tuân thủ schema contract. Một record có thể được broker ghi thành công nhưng consumer vẫn không deserialize được.

## 6. Phân chia công việc khi vận hành production

### Đội nền tảng Kafka

Đội nền tảng thường chịu trách nhiệm:

- Vận hành broker, controller, network, storage, nâng cấp và capacity planning.
- Đặt replication policy, rack awareness, ISR policy, retention mặc định và quota.
- Tạo topic hoặc quản lý quy trình cấp topic, partition và topic-level configuration.
- Cấu hình authentication, authorization, TLS, ACL/authorizer và cấp quyền cho principal.
- Theo dõi sức khỏe cluster: broker availability, under-replicated partitions, offline partitions, disk usage, request latency và tình trạng replication.
- Cung cấp thông tin bootstrap servers, topic contract, giới hạn dung lượng và quy trình xử lý sự cố cluster.

### Đội phát triển ứng dụng

Đội ứng dụng thường chịu trách nhiệm:

- Định nghĩa event contract, schema, key và ý nghĩa của từng topic.
- Cấu hình producer/consumer client phù hợp với yêu cầu độ bền, độ trễ và thông lượng.
- Quản lý group ID, concurrency, poll behavior và acknowledgement/commit strategy.
- Bảo đảm consumer xử lý idempotent và kiểm soát side effect ngoài Kafka.
- Định nghĩa retry, backoff, DLT, cảnh báo poison message và quy trình replay.
- Theo dõi lỗi gửi, lỗi deserialize, listener failure, consumer lag và thời gian xử lý.
- Bảo đảm ứng dụng xử lý được timeout, broker unavailable, rebalance, duplicate delivery và dữ liệu không hợp lệ.

### Các quyết định cần thống nhất

| Quyết định | Cần đội nền tảng | Cần đội ứng dụng |
|---|---|---|
| Tạo topic | Quy trình cấp topic, quyền, giới hạn cluster | Tên topic, mục đích, owner và event contract |
| Số partition | Khả năng cluster và giới hạn vận hành | Throughput, key distribution và mức song song cần thiết |
| Replication/retention | Chính sách và cấu hình thực tế | Mức độ mất dữ liệu chấp nhận được, thời gian replay |
| Security | Principal, ACL, TLS và credential provisioning | Dùng đúng credential, bootstrap và xử lý authorization failure |
| DLT/replay | Dung lượng, quyền, retention và giám sát topic | Điều kiện đưa vào DLT, format lỗi, chống side effect trùng và phê duyệt replay |
| SLO/alert | Chỉ số cluster và broker | Chỉ số producer/consumer, nghiệp vụ và hành động khi vi phạm SLO |

Một topic nên có owner rõ ràng. Owner cần biết ai được publish, ai được consume, key có ý nghĩa gì, schema thay đổi theo quy tắc nào, retention bao lâu, DLT ở đâu và ai có quyền replay. Thiếu những thông tin này sẽ khiến sự cố bị đẩy qua lại giữa đội ứng dụng và đội nền tảng.

## 7. Chẩn đoán sự cố theo đúng ranh giới

| Triệu chứng | Phía ứng dụng cần kiểm tra | Phía broker/nền tảng cần kiểm tra |
|---|---|---|
| Producer timeout hoặc send thất bại | Future/callback, timeout, retry, bootstrap servers, DNS/network từ runtime, serializer và credential | Broker availability, request latency, leader, ISR, quota, ACL và network |
| Lỗi **NotEnoughReplicas** hoặc **NotEnoughReplicasAfterAppend** | **acks**, retry policy và cách ứng dụng phản ứng khi publish thất bại | Replication factor, **min.insync.replicas**, ISR, broker/replica health |
| Broker đã ack nhưng consumer không thấy record | Đúng topic, group ID, subscription, offset, deserializer, filter và listener error | Topic/partition tồn tại, leader health, retention, ACL và khả năng fetch |
| Consumer lag tăng | Thời gian xử lý, concurrency, số consumer, downstream database/API, lỗi retry và pause/resume | Fetch latency, broker load, disk/network và phân bố partition |
| Record được xử lý lặp | Commit timing, listener failure sau side effect, rebalance và idempotency | Group coordination và tính liên tục của committed offset |
| Record sai thứ tự | Key, partition count, async processing, retry và concurrency trong ứng dụng | Xác nhận partition/leader; broker chỉ giữ thứ tự trong từng partition |
| Record liên tục vào DLT | Stack trace, lỗi schema, dữ liệu poison, retry classification và recovery code | DLT tồn tại, quyền publish, retention và dung lượng |
| Consumer bị rebalance liên tục | Thời gian xử lý mỗi poll, heartbeat, **max.poll.interval.ms**, session timeout và shutdown behavior | Group coordinator health, network và cluster stability |

Khi xử lý incident, hãy xác định điểm cuối cùng có bằng chứng quan sát được:

1. Producer đã tạo event chưa?
2. Producer client đã gửi request chưa?
3. Broker đã xác nhận ghi chưa?
4. Consumer group đã nhận partition và fetch record chưa?
5. Listener đã bắt đầu xử lý chưa?
6. Side effect nghiệp vụ đã commit chưa?
7. Offset đã được commit chưa?

Mỗi câu trả lời cần dựa trên log, metric, trace hoặc trạng thái có thể kiểm chứng. Ví dụ, log “send initiated” chỉ chứng minh ứng dụng đã bắt đầu gửi; log acknowledgement mới chứng minh producer đã nhận xác nhận từ broker. Tương tự, log “listener entered” không chứng minh database transaction đã commit.

## 8. Ví dụ cấu hình và cách đọc đúng phạm vi

Một cấu hình ứng dụng tối thiểu có thể làm rõ một số quyết định phía client:

~~~yaml
spring:
  kafka:
    bootstrap-servers: broker-1:9092,broker-2:9092
    producer:
      acks: all
      properties:
        enable.idempotence: true
    consumer:
      group-id: billing-service
      enable-auto-commit: false
~~~

Ý nghĩa:

- **bootstrap-servers** cho client biết địa chỉ ban đầu để lấy metadata cluster.
- **acks: all** yêu cầu producer chờ acknowledgement theo ISR hiện tại.
- **enable.idempotence: true** bật khả năng chống duplicate do retry nội bộ của producer trong phạm vi Kafka hỗ trợ.
- **group-id** xác định consumer group mà ứng dụng tham gia.
- **enable-auto-commit: false** tránh để Kafka client tự commit offset theo chu kỳ độc lập với cách listener container quản lý xử lý. Spring Kafka container có thể quản lý commit theo acknowledgement mode.

Cấu hình phía ứng dụng không thể thay thế cấu hình cluster. Ví dụ, đặt **acks: all** trong Spring Boot không tự tăng replication factor hoặc **min.insync.replicas**. Hai phía phải được cấu hình tương thích. Tương tự, tắt auto commit không tự làm consumer idempotent; ứng dụng vẫn cần chọn commit strategy và bảo vệ side effect.

Nếu dùng Kafka transactions và cần consumer chỉ đọc dữ liệu đã commit, có thể cấu hình **isolation.level=read_committed** cho consumer tương ứng. Chỉ bật thiết lập này khi luồng thực sự sử dụng transactional producer và semantics đó là yêu cầu của ứng dụng.

## 9. Checklist trước khi đưa một luồng vào production

**Hợp đồng sự kiện**

- [ ] Topic có owner, mô tả, producer và consumer rõ ràng.
- [ ] Key được chọn theo yêu cầu partitioning và ordering.
- [ ] Schema, serializer và quy tắc tương thích đã được thống nhất.
- [ ] Có quy tắc xử lý event sai định dạng hoặc không hợp lệ.

**Độ bền và gửi dữ liệu**

- [ ] Replication factor, ISR policy và retention của topic phù hợp với yêu cầu.
- [ ] Producer có cấu hình acknowledgement, idempotence, timeout và retry phù hợp.
- [ ] Ứng dụng quan sát kết quả gửi và có cách phục hồi khi publish thất bại.
- [ ] Luồng database-to-Kafka có outbox hoặc cơ chế bảo đảm nhất quán phù hợp.

**Đọc và xử lý**

- [ ] Group ID và số consumer/concurrency phù hợp với số partition.
- [ ] Acknowledgement mode và commit timing phản ánh đúng thời điểm nghiệp vụ hoàn tất.
- [ ] Consumer có idempotency để chịu được redelivery.
- [ ] Listener có giới hạn xử lý, timeout và hành vi shutdown/rebalance được xác định.

**Retry và vận hành**

- [ ] Retry có phân loại lỗi, backoff và giới hạn số lần thử.
- [ ] DLT có owner, retention, alert, quyền truy cập và quy trình replay.
- [ ] Có metric/log cho publish failure, listener failure, consumer lag, processing latency và DLT rate.
- [ ] Runbook chỉ rõ khi nào đội ứng dụng xử lý và khi nào cần đội nền tảng Kafka.
- [ ] Có kiểm thử hoặc diễn tập các tình huống broker unavailable, rebalance, duplicate delivery, poison message và downstream outage.

## 10. Nguyên tắc cần giữ khi thiết kế

Broker bảo đảm các cơ chế lưu trữ, replication, phân phối và group coordination trong giới hạn cấu hình của cluster. Ứng dụng bảo đảm ý nghĩa dữ liệu, hành vi producer, tiến độ consumer và tính đúng đắn của side effect nghiệp vụ. Spring Kafka cung cấp công cụ phía ứng dụng để thực hiện các quyết định đó.

Vì vậy, một acknowledgement từ broker phải được hiểu là xác nhận ở tầng Kafka; một committed offset phải được hiểu là vị trí đọc đã xác nhận của consumer group. Muốn bảo đảm một nghiệp vụ hoàn tất đúng, hệ thống phải nối các mốc này với transaction, idempotency, retry và quan sát phù hợp ở phía ứng dụng. Khi mỗi mốc có owner và bằng chứng rõ ràng, đội vận hành có thể xác định sự cố nằm ở client, nghiệp vụ hay cluster và khôi phục đúng phần chịu trách nhiệm.
