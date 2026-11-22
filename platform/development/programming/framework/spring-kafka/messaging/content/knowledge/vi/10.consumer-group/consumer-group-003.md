# Group coordinator và quản lý membership

## Mục tiêu của bài học

Trong chương **Consumer group**, bài này giải thích cách Kafka điều phối các consumer cùng thuộc một group thông qua group coordinator. Coordinator theo dõi thành viên, xử lý heartbeat, quản lý generation và phối hợp rebalance để phân phối partition cho các consumer đang hoạt động.

**SPRING_KAFKA_MESSAGING** tập trung xây dựng ứng dụng gửi và nhận sự kiện Kafka bằng Spring Kafka, KafkaTemplate và @KafkaListener; đồng thời giúp người học hiểu topic, partition, offset, consumer group, serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử. Hiểu group coordinator giúp giải thích vì sao consumer được gán partition, vì sao rebalance xảy ra và cách cấu hình Spring Kafka để group hoạt động ổn định.

Sau bài học, người học có thể:

- Giải thích vai trò của group coordinator trong một consumer group.
- Phân biệt group coordinator, group leader, Kafka controller và broker.
- Mô tả cách consumer tìm coordinator và tham gia group.
- Hiểu member ID, generation ID, heartbeat và trạng thái membership.
- Nhận diện nguyên nhân gây rebalance và ảnh hưởng tới việc phân phối partition.
- Phân biệt eager rebalance với cooperative rebalance.
- Cấu hình group membership và theo dõi consumer group trong Spring Kafka.
- Chẩn đoán các vấn đề như consumer liên tục rebalance, member bị loại hoặc partition không được gán.

## 1. Consumer group cần một cơ chế điều phối

Một topic Kafka có thể có nhiều partition. Trong cùng một consumer group, mỗi partition tại một thời điểm được gán cho tối đa một consumer. Nhiều consumer có thể cùng đọc một topic và chia sẻ công việc bằng cách nhận các partition khác nhau.

Ví dụ topic commerce.order.created có 6 partition và group billing-service có 3 consumer:

~~~mermaid
flowchart TB
    T["Topic: commerce.order.created"]
    T --> P0["Partition 0"]
    T --> P1["Partition 1"]
    T --> P2["Partition 2"]
    T --> P3["Partition 3"]
    T --> P4["Partition 4"]
    T --> P5["Partition 5"]
    P0 --> C1["Consumer 1"]
    P3 --> C1
    P1 --> C2["Consumer 2"]
    P4 --> C2
    P2 --> C3["Consumer 3"]
    P5 --> C3
~~~

Để thực hiện việc phân phối này, Kafka cần biết:

- Consumer nào đang tham gia group.
- Consumer nào còn hoạt động.
- Mỗi consumer subscribe những topic nào.
- Partition nào đang được gán cho từng consumer.
- Khi có thành viên mới hoặc thành viên rời đi, assignment cần thay đổi ra sao.
- Tiến độ đọc của group ở từng partition đã được commit tới đâu.

Kafka sử dụng group coordinator để quản lý membership và phối hợp quá trình phân phối partition. Mỗi consumer group có một coordinator chịu trách nhiệm điều phối group đó.

## 2. Group coordinator là gì?

Group coordinator là một broker Kafka được chọn để quản lý một consumer group cụ thể. Coordinator nhận các request liên quan đến membership, heartbeat, generation, rebalance và commit offset của group.

Coordinator không phải một tiến trình riêng mà ứng dụng cần triển khai. Nó là vai trò mà một broker đảm nhiệm cho group được giao.

Các trách nhiệm chính:

- Tiếp nhận consumer tham gia hoặc rời group.
- Theo dõi thành viên thông qua heartbeat.
- Quản lý generation và trạng thái group.
- Phát hiện thành viên không còn hoạt động.
- Điều phối rebalance khi membership hoặc subscription thay đổi.
- Xác nhận assignment được hoàn tất để group chuyển về trạng thái ổn định.
- Xử lý request commit offset và lưu tiến độ đọc của group.

Coordinator giúp mọi thành viên có một điểm điều phối chung. Các consumer không tự thỏa thuận độc lập về partition assignment; chúng tham gia giao thức group do coordinator quản lý.

### 2.1. Coordinator được chọn như thế nào?

Kafka lưu committed offset của consumer group trong topic nội bộ __consumer_offsets. Group ID được ánh xạ tới một partition của topic nội bộ này. Broker đang làm leader của partition tương ứng sẽ đảm nhiệm vai trò group coordinator cho group đó.

Có thể hình dung:

~~~mermaid
flowchart TD
    A["Consumer group: billing-service"] --> B["Ánh xạ group ID"]
    B --> C["Partition tương ứng của __consumer_offsets"]
    C --> D["Broker leader của partition"]
    D --> E["Group coordinator"]
    E --> F["Quản lý membership và offset"]
~~~

Cơ chế này giúp Kafka phân tán trách nhiệm điều phối giữa các broker. Nhiều group có thể có coordinator ở các broker khác nhau.

Nếu broker đang làm coordinator gặp sự cố, consumer cần tìm coordinator mới. Kafka bầu hoặc xác định leader cho partition __consumer_offsets theo cơ chế replication; broker leader mới có thể đảm nhiệm vai trò coordinator sau khi metadata được cập nhật.

### 2.2. Group coordinator không phải Kafka controller

Hai vai trò này dễ bị nhầm lẫn, đặc biệt trong cluster chạy KRaft.

| Thành phần | Trách nhiệm |
|---|---|
| Kafka broker | Nhận request producer/consumer, lưu partition log và phục vụ dữ liệu |
| Group coordinator | Quản lý membership, heartbeat, rebalance và offset của một consumer group |
| Group leader trong classic protocol | Đại diện các member để tính partition assignment và gửi assignment trong SyncGroup |
| KRaft controller | Quản lý metadata và trạng thái cluster thông qua controller quorum |

Group coordinator là vai trò điều phối consumer group ở phía broker. KRaft controller quản lý metadata cluster. Hai vai trò có thể nằm trên các node khác nhau và có phạm vi công việc khác nhau.

### 2.3. Coordinator và group leader khác nhau

Trong classic consumer group protocol, coordinator quản lý group và chọn một member làm group leader cho một generation. Group leader thường chạy partition assignor phía client để tính assignment dựa trên subscription của các member.

Group leader không phải broker leader của partition dữ liệu và cũng không phải group coordinator.

Với các giao thức consumer group mới hơn, một số trách nhiệm assignment có thể được chuyển sang phía server. Vì vậy, mô hình group leader tính assignment chủ yếu mô tả classic protocol; hãy kiểm tra protocol và phiên bản Kafka client đang dùng khi phân tích log hoặc cấu hình.

## 3. Consumer tìm group coordinator

Khi consumer khởi động và cần tham gia một group, nó phải xác định broker nào đang làm coordinator.

Quy trình khái quát:

1. Consumer kết nối tới một broker từ bootstrap.servers.
2. Consumer gửi request FindCoordinator với group ID.
3. Broker trả về địa chỉ broker đang làm group coordinator.
4. Consumer kết nối tới coordinator.
5. Consumer gửi request tham gia group.
6. Coordinator quản lý membership và bắt đầu hoặc hoàn tất rebalance khi cần.

~~~mermaid
sequenceDiagram
    participant C as Kafka Consumer
    participant B as Bootstrap Broker
    participant G as Group Coordinator

    C->>B: Kết nối bootstrap
    C->>B: FindCoordinator(group.id)
    B-->>C: Coordinator host và port
    C->>G: Kết nối coordinator
    C->>G: JoinGroup
    G-->>C: Kết quả membership
~~~

Nếu coordinator thay đổi do broker restart, partition __consumer_offsets được chuyển leader hoặc cluster có sự kiện quản trị, consumer có thể nhận lỗi coordinator unavailable hoặc not coordinator. Kafka client sẽ tìm coordinator lại theo cơ chế retry và metadata refresh.

Ứng dụng không cần tự gọi FindCoordinator. Kafka consumer client và Spring Kafka xử lý giao thức này.

## 4. Membership của consumer group

Membership mô tả tập hợp consumer hiện đang tham gia một group. Mỗi consumer member có thông tin định danh và trạng thái riêng.

Các thông tin quan trọng:

| Thành phần | Ý nghĩa |
|---|---|
| group.id | Định danh consumer group |
| member.id | Định danh member do Kafka quản lý trong group |
| group.instance.id | Định danh ổn định của static member nếu được cấu hình |
| generation.id | Phiên bản membership hiện tại của group |
| subscription | Các topic hoặc pattern mà member đăng ký |
| assignment | Các partition được giao cho member |
| coordinator | Broker quản lý membership của group |

### 4.1. group.id

group.id xác định các consumer cùng chia sẻ tiến độ đọc và tham gia phân phối partition. Các consumer có cùng group.id và tương thích về cấu hình subscription có thể tham gia cùng một group.

Ví dụ:

~~~text
billing-service
inventory-service
notification-service
analytics-service
~~~

Nếu billing-service có ba instance cùng group.id, Kafka phân phối partition giữa các instance đó. Nếu analytics-service dùng group ID riêng, nó có tiến độ đọc độc lập và có thể đọc toàn bộ luồng mà billing-service cũng đang tiêu thụ.

Không dùng group ID thay đổi ngẫu nhiên qua mỗi lần deploy nếu muốn giữ tiến độ đọc. Một group ID mới thường đồng nghĩa một tiến độ đọc độc lập.

### 4.2. member.id

member.id định danh một consumer trong group. Với dynamic membership, Kafka có thể cấp member ID khi consumer tham gia. ID này được dùng trong các request group như heartbeat, leave và sync.

Khi consumer rời group rồi tham gia lại, member ID có thể thay đổi. Ứng dụng không nên dùng member.id như một định danh nghiệp vụ hoặc lưu nó làm ID lâu dài của instance.

### 4.3. generation.id

generation.id đại diện cho một thế hệ membership của group. Khi group trải qua rebalance và assignment mới được thiết lập, generation có thể tăng.

Các request của member thường gắn với generation hiện tại. Request mang generation cũ có thể bị coordinator từ chối vì membership đã thay đổi.

Generation giúp coordinator nhận diện request từ thành viên thuộc trạng thái group cũ, tránh việc một consumer tiếp tục commit hoặc heartbeat như thể nó vẫn sở hữu assignment đã bị thu hồi.

### 4.4. Subscription và assignment

Subscription cho biết member muốn đọc những topic nào hoặc đăng ký theo pattern nào. Assignment là tập partition thực tế mà member được giao sau quá trình phân phối.

Hai khái niệm không giống nhau:

- Consumer có thể subscribe một topic gồm 12 partition.
- Group có 3 consumer.
- Mỗi consumer nhận một phần partition theo assignor.
- Một consumer chỉ xử lý partition được giao cho nó trong group.

Nếu một consumer subscribe topic khác với các member còn lại, assignment phụ thuộc subscription của toàn group và assignor. Trong ứng dụng production, nên thiết kế các member cùng group có cấu hình subscription tương thích để tránh assignment bất ngờ.

## 5. Classic membership protocol: JoinGroup và SyncGroup

Trong classic consumer group protocol, quá trình tham gia group thường gồm các request chính sau.

### 5.1. JoinGroup

Consumer gửi JoinGroup tới coordinator để đăng ký hoặc gia nhập group. Request chứa group ID, thông tin member, subscription và khả năng hỗ trợ partition assignor.

Coordinator thu thập các member tham gia generation. Khi điều kiện group cho phép, coordinator chọn group leader và trả về thông tin membership cho các member.

### 5.2. Group leader tính assignment

Trong classic protocol, group leader nhận thông tin subscription của các member. Nó sử dụng partition assignor để xác định partition nào sẽ được giao cho từng member.

Ví dụ topic có 6 partition và group có 3 member:

~~~text
Member A -> partition 0, 3
Member B -> partition 1, 4
Member C -> partition 2, 5
~~~

Đây là assignment minh họa. Assignment thực tế phụ thuộc assignor, subscription và số topic/partition.

### 5.3. SyncGroup

Group leader gửi assignment tới coordinator thông qua SyncGroup. Coordinator phân phối assignment tương ứng cho các member. Khi các member nhận assignment và group hoàn tất quá trình đồng bộ, group chuyển về trạng thái ổn định.

~~~mermaid
sequenceDiagram
    participant A as Consumer A
    participant B as Consumer B
    participant G as Group Coordinator

    A->>G: JoinGroup(subscription)
    B->>G: JoinGroup(subscription)
    G-->>A: A được chọn làm group leader
    G-->>B: B là follower
    Note over A: Tính assignment
    A->>G: SyncGroup(assignments)
    B->>G: SyncGroup
    G-->>A: Assignment cho A
    G-->>B: Assignment cho B
    Note over A,B: Bắt đầu consume
~~~

Với giao thức consumer group mới hơn, quá trình assignment và rebalance có thể khác classic protocol. Không nên giả định mọi phiên bản đều dùng cùng vai trò group leader và cùng trình tự request.

## 6. Heartbeat và phát hiện member không còn hoạt động

Sau khi tham gia group, consumer cần duy trì membership. Trong classic protocol, consumer gửi heartbeat định kỳ tới coordinator để chứng minh nó vẫn tham gia group.

Các thuộc tính thường gặp:

| Thuộc tính | Ý nghĩa |
|---|---|
| heartbeat.interval.ms | Khoảng thời gian giữa các heartbeat |
| session.timeout.ms | Thời gian coordinator chờ heartbeat trước khi xem member đã mất |
| max.poll.interval.ms | Khoảng thời gian tối đa giữa hai lần poll trước khi consumer bị xem là không tiếp tục tiến triển |

### 6.1. heartbeat.interval.ms

Heartbeat interval xác định tần suất consumer gửi heartbeat. Thông thường giá trị này cần nhỏ hơn session timeout đủ nhiều để có thể chịu được độ trễ mạng hoặc thời điểm tải cao.

Trong classic protocol, client thường cấu hình heartbeat.interval.ms nhỏ hơn session.timeout.ms. Giá trị cụ thể phải tuân theo giới hạn broker và khuyến nghị của phiên bản Kafka.

### 6.2. session.timeout.ms

Nếu coordinator không nhận heartbeat trong thời gian session timeout, nó có thể xem member đã mất và khởi động rebalance để partition của member đó được phân phối lại.

Session timeout quá thấp khiến group nhạy với gián đoạn mạng hoặc pause ngắn. Giá trị quá cao làm việc phát hiện consumer thực sự chết chậm hơn và kéo dài thời gian partition chưa được xử lý bởi member khác.

### 6.3. max.poll.interval.ms

max.poll.interval.ms giới hạn thời gian giữa hai lần gọi poll. Consumer có thể vẫn gửi heartbeat nhưng nếu ứng dụng xử lý quá lâu và không gọi poll tiếp theo trong giới hạn, Kafka client có thể chủ động rời group hoặc đánh dấu member không còn tiến triển, dẫn tới rebalance.

Điểm cần phân biệt:

- session.timeout.ms theo dõi heartbeat và khả năng member còn sống.
- max.poll.interval.ms theo dõi tiến độ gọi poll của consumer.
- heartbeat.interval.ms xác định tần suất heartbeat trong classic protocol.

Tăng session timeout không tự sửa được listener xử lý quá lâu vượt max.poll.interval.ms.

### 6.4. Ví dụ cấu hình

~~~yaml
spring:
  kafka:
    consumer:
      group-id: billing-service
      properties:
        heartbeat.interval.ms: 3000
        session.timeout.ms: 45000
        max.poll.interval.ms: 300000
~~~

Đây là các giá trị minh họa, không phải cấu hình tối ưu cho mọi hệ thống. Cần đo thời gian xử lý listener, thời gian poll, độ trễ mạng và giới hạn broker trước khi điều chỉnh.

## 7. Trạng thái của consumer group

Trong classic group protocol, coordinator quản lý các trạng thái group để điều phối quá trình gia nhập và rebalance.

Các trạng thái thường gặp:

| Trạng thái | Ý nghĩa |
|---|---|
| Empty | Group chưa có member hoạt động |
| PreparingRebalance | Group đang chuẩn bị rebalance, chờ member tham gia hoặc hoàn tất bước chuyển đổi |
| CompletingRebalance | Coordinator đang hoàn tất đồng bộ assignment |
| Stable | Membership và assignment đã ổn định |
| Dead | Group không còn tồn tại hoặc đang bị loại bỏ khỏi metadata quản lý |

Vòng đời đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> Empty
    Empty --> PreparingRebalance: Member joins
    PreparingRebalance --> CompletingRebalance: Join phase complete
    CompletingRebalance --> Stable: Assignment synchronized
    Stable --> PreparingRebalance: Member change / subscription change
    Stable --> Empty: Last member leaves
    Empty --> [*]
~~~

Group ở trạng thái Stable nghĩa là assignment đã được thiết lập và các member có thể tiếp tục consume. Nếu group liên tục chuyển từ Stable sang PreparingRebalance, cần kiểm tra member rời group, heartbeat, poll interval, deployment và subscription.

Trạng thái hiển thị qua công cụ quản trị có thể khác đôi chút tùy phiên bản Kafka và loại group. Hãy đọc trạng thái cùng member count, assignment, consumer lag và log coordinator.

## 8. Rebalance: khi membership thay đổi

Rebalance là quá trình group phân phối lại partition khi membership hoặc điều kiện assignment thay đổi.

Các nguyên nhân thường gặp:

- Consumer mới tham gia group.
- Consumer dừng bình thường hoặc gọi leave group.
- Consumer crash hoặc mất kết nối.
- Heartbeat bị mất quá session timeout.
- Listener xử lý quá lâu vượt max.poll.interval.ms.
- Topic được thêm hoặc số partition thay đổi.
- Subscription của consumer thay đổi.
- Partition assignor hoặc cấu hình group thay đổi.
- Coordinator thay đổi sau sự cố broker hoặc chuyển leader của offsets partition.

### 8.1. Rebalance ảnh hưởng thế nào?

Khi rebalance diễn ra:

1. Consumer có thể tạm dừng việc xử lý các partition liên quan.
2. Partition assignment cũ được thu hồi theo protocol đang dùng.
3. Coordinator và assignor xác định assignment mới.
4. Consumer nhận partition mới.
5. Consumer tiếp tục từ committed offset của group cho từng partition, nếu offset còn hợp lệ.

Rebalance có thể làm tăng consumer lag và giảm thông lượng trong khoảng thời gian group chưa ổn định. Nếu xảy ra liên tục, consumer có thể không đủ thời gian xử lý backlog.

### 8.2. Eager rebalance

Trong eager rebalance, các member thu hồi toàn bộ partition được giao trước khi assignment mới được thiết lập. Điều này có thể tạo khoảng dừng rõ rệt trong lúc group phân phối lại.

Cách này đơn giản và được hỗ trợ rộng rãi, nhưng có thể gây gián đoạn lớn khi group có nhiều member hoặc nhiều partition.

### 8.3. Cooperative rebalance

Cooperative rebalance cho phép thay đổi assignment theo từng bước và chỉ thu hồi các partition cần chuyển. Các partition không cần thay đổi có thể tiếp tục được xử lý.

Kafka client cung cấp CooperativeStickyAssignor để hỗ trợ cooperative incremental rebalance trong các cấu hình tương thích.

~~~mermaid
flowchart TD
    A["Membership thay đổi"] --> B["Tính assignment mới"]
    B --> C{"Rebalance protocol"}
    C -->|Eager| D["Thu hồi toàn bộ assignment"]
    C -->|Cooperative| E["Chỉ thu hồi partition cần chuyển"]
    D --> F["Đồng bộ assignment mới"]
    E --> F
    F --> G["Consumer tiếp tục xử lý"]
~~~

Để dùng cooperative assignor, các member trong group cần có cấu hình assignor tương thích. Việc chuyển đổi cần kiểm tra phiên bản Kafka client và cấu hình của mọi ứng dụng tham gia group.

Cooperative rebalance giảm phạm vi gián đoạn, nhưng không loại bỏ mọi rebalance và cũng không bảo đảm không có duplicate. Offset và idempotency vẫn cần được thiết kế đúng.

## 9. Static membership

Mặc định, consumer thường dùng dynamic membership: khi restart, consumer có thể rời group rồi tham gia lại với member ID mới. Điều này có thể kích hoạt rebalance ngay cả khi instance chỉ restart trong thời gian ngắn.

Static membership cho phép consumer khai báo group.instance.id ổn định. Coordinator nhận diện member qua định danh này và có thể giữ membership trong một khoảng thời gian khi instance tạm thời mất kết nối.

Ví dụ cấu hình Kafka consumer:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: billing-service
      properties:
        group.instance.id: billing-instance-1
~~~

Với nhiều instance, mỗi static member phải có group.instance.id duy nhất trong group. Không dùng cùng một giá trị cho hai consumer đang chạy đồng thời; coordinator có thể từ chối member do instance ID trùng.

### 9.1. Lợi ích

- Giảm rebalance không cần thiết khi một instance restart nhanh.
- Hạn chế việc partition bị chuyển liên tục trong môi trường deployment có kiểm soát.
- Giữ định danh member ổn định giữa các lần kết nối.

### 9.2. Đánh đổi

- Nếu instance thực sự chết, group có thể chờ tới khi session timeout trước khi giải phóng membership.
- Cần quản lý ID ổn định và duy nhất cho từng member.
- Không nên dùng một ID cố định cho mọi replica.
- Cần kiểm tra cách Spring Kafka tạo consumer khi listener có concurrency lớn hơn 1.

Static membership phù hợp với các môi trường có định danh instance ổn định, chẳng hạn StatefulSet hoặc node có identity rõ ràng. Với workload co giãn nhanh và instance thay đổi liên tục, dynamic membership có thể phù hợp hơn.

## 10. Partition assignor quyết định cách phân phối

Coordinator quản lý giao thức group; assignor quyết định partition nào được giao cho member nào.

Một số assignor phổ biến trong Kafka client:

| Assignor | Cách phân phối khái quát |
|---|---|
| RangeAssignor | Chia partition theo phạm vi cho từng consumer trên từng topic |
| RoundRobinAssignor | Phân phối partition luân phiên giữa các consumer |
| StickyAssignor | Cân bằng assignment và cố gắng giữ assignment cũ để giảm chuyển partition |
| CooperativeStickyAssignor | Giữ tính sticky và hỗ trợ incremental cooperative rebalance |

Ví dụ cấu hình cooperative sticky:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        partition.assignment.strategy: org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

Assignment thực tế phụ thuộc số member, số partition, subscription, assignor và protocol. Không giả định partition luôn được chia đều trong mọi trường hợp.

### 10.1. Giới hạn bởi số partition

Trong một consumer group, một partition tại một thời điểm chỉ được gán cho tối đa một consumer. Vì vậy, tổng số consumer có thể xử lý dữ liệu đồng thời bị giới hạn bởi số partition được gán.

Ví dụ topic có 4 partition:

| Số consumer trong group | Consumer có partition | Consumer không có partition |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | Tối đa 2 | 0 |
| 4 | Tối đa 4 | 0 |
| 6 | Tối đa 4 | Tối thiểu 2 |

Tăng số consumer vượt số partition không tạo thêm mức song song cho topic đó. Consumer dư vẫn có thể tham gia group nhưng không nhận partition.

## 11. Cấu hình và quản lý membership bằng Spring Kafka

Spring Kafka dùng Kafka consumer client để tham gia group. Ứng dụng thường không tương tác trực tiếp với group coordinator; thay vào đó, cấu hình consumer factory và listener container quyết định hành vi.

### 11.1. Cấu hình application.yml

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      properties:
        session.timeout.ms: 45000
        heartbeat.interval.ms: 3000
        max.poll.interval.ms: 300000
        partition.assignment.strategy: org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

Các thuộc tính này có vai trò khác nhau:

- group-id xác định consumer group.
- enable-auto-commit=false để listener container quản lý commit.
- auto-offset-reset chỉ áp dụng khi không có offset hợp lệ.
- session.timeout.ms và heartbeat.interval.ms ảnh hưởng phát hiện member không hoạt động trong classic protocol.
- max.poll.interval.ms giới hạn thời gian giữa các lần poll.
- partition.assignment.strategy chọn chiến lược phân phối partition.

### 11.2. Khai báo listener

~~~java
@Service
public class OrderListener {

    @KafkaListener(
        topics = "commerce.order.created",
        groupId = "billing-service"
    )
    public void handle(OrderCreated event) {
        // Xử lý event.
    }
}
~~~

groupId của @KafkaListener xác định group cho endpoint. Nếu không chỉ định, listener có thể dùng group ID từ consumer factory hoặc cấu hình mặc định tương ứng.

Thuộc tính id của @KafkaListener là ID của listener endpoint trong Spring; nó không đồng nghĩa với groupId. Không nhầm tên bean, listener ID và consumer group ID.

### 11.3. Concurrency và membership

Có thể đặt concurrency cho listener container:

~~~java
factory.setConcurrency(3);
~~~

Spring Kafka tạo nhiều consumer container con cho cùng listener. Mỗi consumer tham gia group bằng consumer client riêng. Coordinator quản lý từng consumer như một member trong group.

Nếu ứng dụng có 2 instance và mỗi instance concurrency bằng 3, group có tổng cộng 6 consumer. Partition assignment diễn ra trên toàn bộ 6 consumer, không chỉ trong từng tiến trình.

Concurrency nên được chọn theo số partition, thời gian xử lý, tải downstream và yêu cầu thứ tự. Tăng concurrency có thể làm group rebalance khi số member thay đổi.

### 11.4. Listener lifecycle

Spring Kafka listener container quản lý vòng đời consumer:

- Tạo consumer từ ConsumerFactory.
- Subscribe topic hoặc pattern.
- Tham gia group và nhận assignment.
- Poll record và gọi listener.
- Quản lý acknowledgment/offset theo cấu hình.
- Dừng consumer khi container stop hoặc Spring context shutdown.

Container quản lý consumer ở phía ứng dụng. Group coordinator vẫn là broker chịu trách nhiệm membership và rebalance.

## 12. Theo dõi consumer group bằng công cụ Kafka

Có thể dùng kafka-consumer-groups để xem group, trạng thái và assignment.

Liệt kê group:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list
~~~

Xem tiến độ và lag:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --describe
~~~

Xem trạng thái group:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --describe \
  --state
~~~

Trên các phiên bản hỗ trợ, có thể xem thành viên và assignment chi tiết:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --describe \
  --members \
  --verbose
~~~

Các cột thường gặp khi mô tả group:

| Cột | Ý nghĩa |
|---|---|
| GROUP | Tên consumer group |
| TOPIC | Topic đang được tiêu thụ |
| PARTITION | Partition được gán |
| CURRENT-OFFSET | Committed offset của group |
| LOG-END-OFFSET | Offset cuối hiện tại của partition |
| LAG | Chênh lệch giữa log end và committed offset |
| CONSUMER-ID | Định danh consumer member |
| HOST | Địa chỉ host của consumer |
| CLIENT-ID | Client ID của Kafka consumer |

Khi điều tra group, nên xem đồng thời state, member count, assignment, current offset và lag. Một group ở trạng thái Stable nhưng lag tăng vẫn có thể gặp vấn đề về throughput hoặc xử lý nghiệp vụ.

## 13. Chẩn đoán các vấn đề membership

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Group liên tục rebalance | Consumer restart, heartbeat timeout hoặc poll quá lâu | Kiểm tra log, session.timeout.ms, max.poll.interval.ms và thời gian xử lý |
| Coordinator unavailable | Broker coordinator restart hoặc offsets partition đổi leader | Kiểm tra broker và trạng thái __consumer_offsets |
| Member bị fenced | Static member ID bị trùng hoặc member cũ vẫn còn hiệu lực | Kiểm tra group.instance.id và các instance |
| Consumer không nhận partition | Số consumer lớn hơn partition hoặc subscription/assignment không tương thích | Kiểm tra group describe và assignor |
| Consumer mất membership sau xử lý lâu | Không gọi poll trong max.poll.interval.ms | Đo thời gian listener và điều chỉnh xử lý/batch |
| Group không chuyển Stable | Member không hoàn tất JoinGroup/SyncGroup hoặc rebalance kéo dài | Kiểm tra coordinator log, member và protocol |
| Partition chuyển liên tục giữa member | Membership thay đổi hoặc assignor không giữ assignment | Kiểm tra deployment, autoscaling và assignor |
| Lag tăng dù group Stable | Consumer xử lý chậm, partition nóng hoặc downstream quá tải | Đo lag từng partition và processing time |

### 13.1. Coordinator unavailable

Lỗi coordinator unavailable có thể xuất hiện khi broker đang làm coordinator tạm thời không sẵn sàng. Kafka client thường thử tìm coordinator lại. Nếu lỗi kéo dài, cần kiểm tra:

- Broker coordinator có hoạt động không.
- Leader của partition __consumer_offsets có ổn định không.
- Network giữa consumer và broker có bị gián đoạn không.
- DNS, advertised.listeners và security protocol có đúng không.
- Broker log có lỗi replication hoặc storage không.

Không nên thay group ID chỉ để né lỗi coordinator. Đổi group ID tạo tiến độ đọc mới và có thể khiến consumer đọc lại hoặc bỏ qua dữ liệu tùy reset policy.

### 13.2. Rebalance liên tục

Rebalance liên tục có thể làm consumer không đủ thời gian xử lý backlog. Hãy tìm nguyên nhân gốc:

- Instance restart liên tục do health check hoặc lỗi ứng dụng.
- Listener xử lý một batch quá lâu.
- Downstream timeout khiến poll bị trì hoãn.
- Session timeout quá thấp so với độ trễ thực tế.
- Deployment làm số member thay đổi thường xuyên.
- Static membership được cấu hình với ID không ổn định hoặc trùng lặp.

Tăng timeout có thể giảm rebalance giả do tải cao, nhưng cũng kéo dài thời gian phát hiện consumer chết. Cần đo và chọn giá trị phù hợp.

## 14. Quan sát và vận hành group coordinator

Các tín hiệu cần theo dõi:

| Tín hiệu | Ý nghĩa |
|---|---|
| Group state | Group có ổn định hay đang rebalance |
| Member count | Số consumer đang tham gia |
| Partition assignment | Phân phối partition giữa các member |
| Rebalance rate | Tần suất group phải phân phối lại |
| Rebalance duration | Thời gian hoàn tất một lần rebalance |
| Consumer lag | Mức chậm xử lý theo group và partition |
| Heartbeat failures | Dấu hiệu mạng hoặc member không ổn định |
| Poll interval / processing time | Khả năng consumer duy trì poll |
| Coordinator errors | Lỗi kết nối hoặc chuyển coordinator |

Spring Kafka phát ra application event liên quan tới listener container và partition assignment. Có thể kết hợp event này với metric Kafka client, log và dashboard để theo dõi trạng thái group.

Không nên chỉ theo dõi tổng lag. Lag từng partition giúp phát hiện một partition bị nóng trong khi các partition khác vẫn được xử lý bình thường.

## 15. Checklist quản lý membership

- [ ] group.id ổn định và được quản lý theo mục đích tiêu thụ?
- [ ] Các consumer trong cùng group có subscription tương thích?
- [ ] Đã hiểu broker nào đang làm group coordinator?
- [ ] Phân biệt coordinator với group leader và KRaft controller?
- [ ] Consumer duy trì heartbeat theo giới hạn phù hợp?
- [ ] Thời gian xử lý listener không vượt max.poll.interval.ms?
- [ ] Generation và membership được phép ổn định qua rebalance?
- [ ] Partition assignor phù hợp yêu cầu cân bằng và giảm gián đoạn?
- [ ] Nếu dùng static membership, group.instance.id duy nhất và ổn định?
- [ ] Concurrency không vượt quá mức song song hữu ích theo partition?
- [ ] Có metric về group state, member, assignment, lag và rebalance?
- [ ] Có quy trình xử lý coordinator unavailable và consumer bị fencing?
- [ ] Kiểm thử khi consumer join, leave, crash, restart và scale instance?

## Kết luận

Group coordinator là broker chịu trách nhiệm quản lý membership, heartbeat, generation, rebalance và offset của một consumer group. Consumer tìm coordinator qua FindCoordinator, tham gia group và nhận partition assignment theo protocol và assignor đang dùng. Trong classic protocol, JoinGroup và SyncGroup phối hợp việc tập hợp member và đồng bộ assignment; heartbeat giúp coordinator phát hiện member không còn hoạt động.

Spring Kafka sử dụng Kafka consumer client và listener container để quản lý vòng đời consumer. Ứng dụng cần giữ group ID ổn định, chọn timeout phù hợp, tránh listener xử lý quá lâu, cấu hình assignor có chủ đích và theo dõi rebalance. Khi hiểu rõ coordinator, membership và assignment, người học có thể chẩn đoán group không ổn định, mở rộng consumer hợp lý và vận hành luồng messaging đáng tin cậy.
