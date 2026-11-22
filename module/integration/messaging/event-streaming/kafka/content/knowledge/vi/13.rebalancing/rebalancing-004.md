# Nhận diện cấu hình phụ thuộc phía client hoặc phía broker

Kafka consumer group rebalance là quá trình coordinator phân phối lại partition cho các consumer member. Một lần rebalance có thể bắt đầu vì consumer tham gia hoặc rời group, heartbeat bị mất, xử lý vượt thời gian cho phép, subscription thay đổi hoặc topic được thêm partition.

Khi điều tra rebalance, cần phân biệt **cấu hình do consumer client gửi và thực thi** với **cấu hình broker dùng để giới hạn, điều phối hoặc áp dụng chính sách cho group**. Nhiều tham số có tên gần nhau nhưng thuộc hai phía khác nhau. Ví dụ, client khai báo `session.timeout.ms`, còn broker đặt giới hạn chấp nhận qua `group.min.session.timeout.ms` và `group.max.session.timeout.ms` trong classic group protocol.

Bài này giúp xác định cấu hình nằm ở đâu, ai chịu trách nhiệm, cách các giá trị phối hợp với nhau và cách kiểm tra khi consumer group rebalance liên tục hoặc giữ partition quá lâu.

## 1. Rebalance được điều phối như thế nào?

Một consumer group có một group coordinator trên broker. Coordinator theo dõi membership, heartbeat, trạng thái group và assignment của partition. Consumer client tham gia group, gửi heartbeat, gọi poll và thực thi phần xử lý record. Broker điều phối thay đổi group dựa trên giao thức và chính sách đã cấu hình.

Có thể hình dung hai phía phối hợp:

~~~mermaid
flowchart TB
    subgraph Client["Phía consumer client"]
      C1["group.id / group.instance.id"]
      C2["session / heartbeat"]
      C3["max.poll.interval.ms"]
      C4["subscription / assignor"]
      C5["poll và xử lý record"]
    end
    subgraph Broker["Phía Kafka broker"]
      B1["Group coordinator"]
      B2["Session timeout bounds"]
      B3["Initial rebalance delay"]
      B4["Maximum group size"]
      B5["Group protocol và assignment policy"]
    end
    C1 --> B1
    C2 --> B1
    C3 --> C5
    C4 --> B1
    C5 --> B1
    B2 --> B1
    B3 --> B1
    B4 --> B1
    B5 --> B1
    B1 --> A["Partition assignment / rebalance"]
~~~

Client và broker không hoạt động độc lập. Client gửi thông tin và hành vi tham gia group; broker xác thực các giá trị được phép, theo dõi member và thực hiện điều phối. Một số giá trị client cấu hình có thể bị giới hạn bởi broker, còn một số chính sách do broker quyết định hoàn toàn.

## 2. Bảng phân biệt nhanh cấu hình client và broker

| Mục tiêu | Phía client | Phía broker |
|---|---|---|
| Nhận diện group và instance | `group.id`, `group.instance.id`, `client.id` | Coordinator lưu membership theo group |
| Heartbeat và session trong classic protocol | `session.timeout.ms`, `heartbeat.interval.ms` | `group.min.session.timeout.ms`, `group.max.session.timeout.ms` giới hạn session timeout |
| Phát hiện consumer không gọi poll | `max.poll.interval.ms`, `max.poll.records` | Coordinator xử lý member mất tiến triển theo protocol |
| Phân phối partition trong classic protocol | `partition.assignment.strategy` | Coordinator phối hợp các member và áp dụng protocol/assignor được thống nhất |
| Trì hoãn lần rebalance đầu | Không có tham số client tương đương trực tiếp | `group.initial.rebalance.delay.ms` |
| Giới hạn số member trong group | Client chọn có tham gia group hay không | `group.max.size` |
| Consumer group protocol mới | `group.protocol=consumer` để chọn protocol nếu phiên bản hỗ trợ | Các cấu hình `group.consumer.*` điều khiển heartbeat, session và assignor phía broker |

Bảng này là định hướng. Tên cấu hình và khả năng hỗ trợ thay đổi theo phiên bản Kafka client/broker. Đặc biệt, không áp dụng các tham số classic một cách máy móc cho consumer group protocol mới.

## 3. Cấu hình thuộc phía consumer client

### 3.1. group.id

`group.id` xác định consumer group mà instance tham gia. Các consumer có cùng group ID cùng chia sẻ partition của topic đã subscribe. Consumer dùng group ID khác sẽ có tiến độ đọc và assignment độc lập.

~~~properties
group.id=orders-projection
~~~

Đây là cấu hình phía client. Broker dùng giá trị nhận được để định tuyến request đến group coordinator và quản lý group tương ứng.

Nếu hai ứng dụng vô tình dùng cùng `group.id`, chúng có thể chia nhau partition thay vì mỗi ứng dụng đọc toàn bộ topic. Đây là lỗi cấu hình thường gặp khi một consumer phục vụ dashboard và một consumer khác phục vụ nghiệp vụ nhưng lại dùng chung group ID.

### 3.2. group.instance.id

`group.instance.id` là định danh ổn định của một static member. Client cung cấp giá trị này để coordinator nhận diện logical instance qua các lần restart ngắn.

~~~properties
group.instance.id=orders-projection-0
~~~

Mỗi instance trong cùng group phải có ID riêng. Cùng một ID được dùng đồng thời bởi hai process có thể dẫn đến fencing và lỗi membership.

Static membership giúp tránh một số rebalance do restart ngắn, nhưng không loại bỏ rebalance khi topology, subscription hoặc partition thay đổi. Nó cũng có thể làm coordinator chờ session timeout trước khi giải phóng partition của một instance mất tích.

### 3.3. session.timeout.ms trong classic group protocol

Với classic protocol, consumer client gửi `session.timeout.ms` khi tham gia group. Đây là khoảng thời gian coordinator chờ heartbeat trước khi xem member mất kết nối.

~~~properties
session.timeout.ms=45000
~~~

Giá trị client gửi phải nằm trong giới hạn broker cho phép:

~~~properties
group.min.session.timeout.ms=6000
group.max.session.timeout.ms=1800000
~~~

Hai giá trị broker ở trên là ví dụ theo cấu hình phổ biến; hãy kiểm tra giá trị hiệu lực của cluster đang chạy. Nếu client yêu cầu session timeout nhỏ hơn min hoặc lớn hơn max, broker có thể từ chối yêu cầu tham gia group.

Tăng session timeout giúp chịu được gián đoạn heartbeat lâu hơn, nhưng làm chậm việc phát hiện consumer chết. Giảm session timeout giúp phát hiện nhanh hơn nhưng dễ loại consumer khi mạng chập chờn hoặc broker quá tải.

### 3.4. heartbeat.interval.ms trong classic group protocol

`heartbeat.interval.ms` xác định khoảng thời gian client gửi heartbeat trong classic protocol:

~~~properties
heartbeat.interval.ms=15000
~~~

Giá trị này thường nhỏ hơn đáng kể so với `session.timeout.ms`; một quy tắc cấu hình phổ biến là khoảng một phần ba session timeout. Cần tuân thủ giới hạn và khuyến nghị của phiên bản client/broker.

Heartbeat cho coordinator biết consumer còn hoạt động trong group. Nó không chứng minh ứng dụng đã xử lý xong record. Consumer vẫn có thể gửi heartbeat trong khi một luồng nghiệp vụ khác bị nghẽn, vì vậy cần theo dõi cả poll progress và thời gian xử lý.

### 3.5. max.poll.interval.ms

`max.poll.interval.ms` là cấu hình phía client, giới hạn thời gian tối đa giữa các lần gọi `poll()`:

~~~properties
max.poll.interval.ms=300000
max.poll.records=100
~~~

Nếu ứng dụng lấy một batch rồi xử lý quá lâu trước lần poll tiếp theo, consumer có thể bị xem là không còn tiến triển và rời group hoặc ngừng heartbeat theo semantics của protocol. Group sau đó có thể rebalance.

`max.poll.records` giới hạn số record trả về trong một lần poll. Giảm số record có thể rút ngắn thời gian xử lý batch; tăng nó có thể tăng throughput nhưng cũng kéo dài thời gian xử lý và tăng bộ nhớ.

Không nên chỉ tăng `max.poll.interval.ms` để che giấu handler chậm. Hãy đo thời gian xử lý batch, đặt timeout cho downstream và chọn số record phù hợp.

### 3.6. partition.assignment.strategy

Trong classic protocol, `partition.assignment.strategy` xác định assignor mà consumer client hỗ trợ:

~~~properties
partition.assignment.strategy=org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

Một số assignor phổ biến:

- `RangeAssignor`: phân chia partition theo range cho consumer.
- `RoundRobinAssignor`: phân phối lần lượt các partition.
- `StickyAssignor`: cố gắng cân bằng tải và giữ assignment ổn định.
- `CooperativeStickyAssignor`: chuyển partition theo từng phần để giảm việc thu hồi toàn bộ assignment trong một lần rebalance.

Các member trong cùng group cần thống nhất protocol và có assignor tương thích. Nếu rollout client với danh sách assignor không tương thích, group có thể không chọn được chiến lược chung hoặc phát sinh thay đổi assignment.

Với consumer group protocol mới, cơ chế assignor được điều phối khác và không nên giả định `partition.assignment.strategy` vẫn có cùng vai trò.

## 4. Cấu hình thuộc phía broker

### 4.1. group.min.session.timeout.ms và group.max.session.timeout.ms

Hai cấu hình broker này đặt khoảng session timeout mà classic consumer được phép yêu cầu:

~~~properties
group.min.session.timeout.ms=6000
group.max.session.timeout.ms=1800000
~~~

Broker dùng chúng như guardrail cho giá trị `session.timeout.ms` do client gửi. Chúng không phải giá trị session timeout mặc định mà mọi consumer tự động dùng.

Ví dụ:

| Broker min | Broker max | Client yêu cầu | Kết quả |
|---:|---:|---:|---|
| 6 giây | 30 phút | 45 giây | Trong giới hạn |
| 6 giây | 30 phút | 3 giây | Thấp hơn min |
| 6 giây | 30 phút | 40 phút | Cao hơn max |

Nếu cần thay đổi khả năng phát hiện member mất kết nối, hãy xem cả client session timeout và broker bounds. Chỉ tăng broker max không làm consumer tự động dùng timeout mới; client vẫn gửi giá trị của nó.

### 4.2. group.initial.rebalance.delay.ms

Đây là cấu hình broker xác định thời gian coordinator trì hoãn lần rebalance ban đầu để có cơ hội nhận thêm member:

~~~properties
group.initial.rebalance.delay.ms=3000
~~~

Trong lúc group mới hình thành, coordinator có thể chờ một khoảng ngắn trước khi chốt assignment. Điều này hữu ích khi nhiều consumer khởi động gần nhau: thay vì rebalance liên tiếp mỗi khi một member đến, group có thể gom các member vào lần phân phối ban đầu.

Đánh đổi là thời gian group bắt đầu xử lý có thể tăng. Tham số này chủ yếu ảnh hưởng lần rebalance ban đầu; không phải cách sửa mọi rebalance liên tục trong suốt vòng đời group.

### 4.3. group.max.size

`group.max.size` giới hạn số member tối đa mà một group có thể có trên broker:

~~~properties
group.max.size=2147483647
~~~

Giá trị ví dụ trên là mức trần lớn theo cấu hình phổ biến. Trong môi trường có nhiều tenant hoặc nhiều ứng dụng, có thể đặt giới hạn thấp hơn để bảo vệ coordinator và kiểm soát số member.

Khi group đạt giới hạn, member mới có thể không tham gia được và nhận lỗi tương ứng. Tăng số consumer vượt quá số partition cũng không làm tăng mức song song hữu ích của group, vì mỗi partition chỉ được giao cho tối đa một consumer trong group tại một thời điểm.

### 4.4. Group coordinator và trạng thái broker

Coordinator là vai trò broker quản lý group state, membership, generation và offset. Không có một thuộc tính client nào thay thế coordinator. Khi coordinator broker thay đổi hoặc broker gặp sự cố, client cần tìm coordinator mới và tham gia lại theo protocol.

Khi chẩn đoán, cần kiểm tra log coordinator trên broker đang giữ vai trò đó, trạng thái group, heartbeat và lỗi JoinGroup/SyncGroup/Heartbeat. Việc chỉ xem log của ứng dụng consumer có thể bỏ sót nguyên nhân do broker từ chối session timeout hoặc group đạt giới hạn member.

## 5. Classic protocol và consumer group protocol mới

Kafka có nhiều thế hệ consumer group protocol. Cấu hình heartbeat/session không hoàn toàn giống nhau giữa classic protocol và consumer protocol mới.

### 5.1. Classic protocol

Với classic protocol, consumer client thường điều khiển các giá trị:

- `session.timeout.ms`
- `heartbeat.interval.ms`
- `max.poll.interval.ms`
- `partition.assignment.strategy`

Broker xác thực session timeout bằng:

- `group.min.session.timeout.ms`
- `group.max.session.timeout.ms`

Đây là mô hình nhiều ứng dụng Kafka đã sử dụng lâu nay.

### 5.2. Consumer group protocol mới

Các phiên bản Kafka mới hỗ trợ consumer group protocol mới, được chọn ở client bằng:

~~~properties
group.protocol=consumer
~~~

Trong protocol này, một số chính sách heartbeat và session được chuyển sang broker. Các cấu hình broker thường gặp có tiền tố `group.consumer.`, chẳng hạn:

~~~properties
group.consumer.heartbeat.interval.ms=5000
group.consumer.session.timeout.ms=45000
~~~

Các giá trị trên chỉ là ví dụ; mặc định, giới hạn và danh sách cấu hình hợp lệ phụ thuộc phiên bản Kafka. Client không điều khiển heartbeat/session theo cùng cách classic; hãy kiểm tra tài liệu phiên bản đang chạy để biết thuộc tính nào được hỗ trợ hoặc không còn áp dụng khi `group.protocol=consumer`.

Consumer protocol mới cũng thay đổi cách assignment được phối hợp. Không sao chép nguyên cấu hình classic sang protocol mới mà không kiểm tra compatibility giữa broker, Java client và framework.

### 5.3. Chọn protocol nào?

| Tiêu chí | Classic | Consumer protocol mới |
|---|---|---|
| Cấu hình heartbeat/session | Chủ yếu do client gửi, broker áp dụng giới hạn | Nhiều chính sách do broker quản lý |
| Assignment | Consumer hỗ trợ assignor và phối hợp qua group protocol | Có cơ chế điều phối assignment phía broker theo protocol mới |
| Tương thích | Hỗ trợ rộng trong các phiên bản Kafka | Cần broker/client phiên bản hỗ trợ |
| Thay đổi cấu hình | Dùng các tham số classic | Phải kiểm tra nhóm `group.consumer.*` và thuộc tính client tương ứng |

Khi nâng cấp, cần triển khai có kế hoạch. Không chuyển protocol chỉ để xử lý một lỗi rebalance chưa được chẩn đoán.

## 6. Bảng đối chiếu theo triệu chứng

| Triệu chứng | Cấu hình client cần kiểm tra | Cấu hình broker cần kiểm tra |
|---|---|---|
| Consumer bị loại dù mạng chỉ gián đoạn ngắn | `session.timeout.ms`, heartbeat, static membership | Min/max session timeout; coordinator logs |
| Rebalance vì xử lý batch quá lâu | `max.poll.interval.ms`, `max.poll.records`, thời gian handler | Coordinator logs và group state |
| Consumer group khởi động chậm | Thời điểm các instance start, subscription | `group.initial.rebalance.delay.ms` |
| Member mới không tham gia được | `group.id`, `group.instance.id`, protocol | `group.max.size`, session timeout bounds, coordinator logs |
| Partition assignment thay đổi quá nhiều | `partition.assignment.strategy`, subscription, static identity | Protocol compatibility và group coordinator |
| FencedInstanceIdException | `group.instance.id` bị trùng | Coordinator log xác nhận member fencing |
| Client không dùng được session timeout mong muốn | Giá trị `session.timeout.ms` thực tế | `group.min.session.timeout.ms` và `group.max.session.timeout.ms` |
| Consumer protocol mới có heartbeat/session khác dự kiến | `group.protocol` và client version | `group.consumer.heartbeat.interval.ms`, `group.consumer.session.timeout.ms` |

Bảng này chỉ ra nơi bắt đầu điều tra. Một triệu chứng có thể do nhiều nguyên nhân kết hợp, chẳng hạn batch quá lớn cộng với downstream chậm và broker coordinator đang quá tải.

## 7. Ví dụ cấu hình classic cho Java consumer

Ví dụ client:

~~~properties
bootstrap.servers=kafka-1:9092,kafka-2:9092
group.id=orders-projection
client.id=orders-projection-0
group.instance.id=orders-projection-0
group.protocol=classic
session.timeout.ms=45000
heartbeat.interval.ms=15000
max.poll.interval.ms=300000
max.poll.records=100
enable.auto.commit=false
partition.assignment.strategy=org.apache.kafka.clients.consumer.CooperativeStickyAssignor
~~~

Ví dụ broker:

~~~properties
group.min.session.timeout.ms=6000
group.max.session.timeout.ms=1800000
group.initial.rebalance.delay.ms=3000
group.max.size=1000
~~~

Các giá trị chỉ để minh họa cho một triển khai classic. Cần kiểm tra cấu hình hiệu lực, giới hạn broker và version client thực tế.

Cấu hình Spring Boot có thể truyền client properties như sau:

~~~properties
spring.kafka.consumer.group-id=orders-projection
spring.kafka.consumer.properties[group.instance.id]=orders-projection-0
spring.kafka.consumer.properties[session.timeout.ms]=45000
spring.kafka.consumer.properties[heartbeat.interval.ms]=15000
spring.kafka.consumer.properties[max.poll.interval.ms]=300000
spring.kafka.consumer.properties[max.poll.records]=100
~~~

Nếu có nhiều replica, mỗi instance cần một `group.instance.id` riêng. Với Spring listener concurrency lớn hơn một, xác minh cách phiên bản Spring Kafka đang dùng tạo identity cho các child consumer.

## 8. Cách kiểm tra cấu hình broker và client

### 8.1. Kiểm tra broker configuration

Có thể xem cấu hình broker qua CLI:

~~~bash
kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type brokers \
  --entity-name 1 \
  --describe --all
~~~

Lệnh hiển thị cấu hình broker theo phiên bản và quyền truy cập. Một số cấu hình có thể đến từ file tĩnh, một số có thể được override động. Cần phân biệt giá trị mặc định, giá trị trong file cấu hình và dynamic override.

Để kiểm tra cấu hình mặc định của broker, cú pháp hỗ trợ `--entity-default` tùy phiên bản CLI:

~~~bash
kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type brokers \
  --entity-default \
  --describe --all
~~~

Nếu CLI của bản phân phối không hỗ trợ tùy chọn này, xem `--help` và tài liệu phiên bản đang dùng.

### 8.2. Kiểm tra consumer group

Xem trạng thái và lag:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-projection
~~~

Nếu phiên bản CLI hỗ trợ, có thể xem member và assignment:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-projection \
  --members --verbose
~~~

Có thể xem group state:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-projection \
  --state
~~~

Các tùy chọn và trường output thay đổi theo phiên bản. Dùng `--help` nếu CLI không nhận một tham số.

### 8.3. Kiểm tra cấu hình client thực tế

Client configuration nên được xác minh tại đúng process đang chạy, không chỉ nhìn file mẫu. Có thể:

- Bật log cấu hình consumer khi khởi động trong môi trường an toàn.
- Ghi lại các giá trị quan trọng đã resolve sau khi nạp environment/config.
- Kiểm tra command line, biến môi trường, Spring profile và ConfigMap/Secret.
- Ghi log group ID, client ID, group instance ID và protocol.
- Đối chiếu phiên bản `kafka-clients` mà ứng dụng thực sự nạp.

Không log credential, password, JAAS config hoặc dữ liệu nhạy cảm khi dump cấu hình.

## 9. Quy trình chẩn đoán rebalance theo từng bước

Khi consumer group rebalance liên tục, hãy làm theo thứ tự:

1. **Xác nhận protocol:** kiểm tra client đang dùng classic hay consumer group protocol mới.
2. **Xác nhận group identity:** kiểm tra `group.id`, `group.instance.id` và số member thực tế.
3. **Kiểm tra poll progress:** đo khoảng cách giữa các lần poll và thời gian xử lý batch.
4. **Kiểm tra heartbeat/session:** đối chiếu heartbeat, session timeout và giới hạn broker tương ứng.
5. **Kiểm tra assignment:** xem assignor, subscription và số partition.
6. **Kiểm tra broker coordinator:** tìm log JoinGroup, SyncGroup, heartbeat, fencing và coordinator movement.
7. **Kiểm tra tải hệ thống:** đo CPU, network, GC, downstream latency và consumer lag.
8. **Thử nghiệm một thay đổi:** chỉ thay một nhóm cấu hình mỗi lần để biết nguyên nhân và tác động.
9. **Xác minh sau thay đổi:** theo dõi rebalance count, partition assignment, lag và thời gian phục hồi.

Không tăng tất cả timeout cùng lúc. Nếu vấn đề do handler bị treo, tăng session timeout và max poll interval có thể chỉ làm partition bị giữ lâu hơn.

## 10. Những nhầm lẫn phổ biến

### session.timeout.ms là cấu hình broker

Không đúng trong classic protocol. Đây là cấu hình client gửi trong quá trình tham gia group; broker có min/max để giới hạn. Với consumer protocol mới, heartbeat/session được điều khiển theo cấu hình broker tương ứng.

### max.poll.interval.ms được đặt ở broker

Không đúng. Đây là cấu hình client quyết định khoảng cách tối đa giữa các lần poll. Broker phản ứng khi member không còn đáp ứng tiến độ group theo protocol.

### group.initial.rebalance.delay.ms sửa được mọi rebalance

Không đúng. Nó chủ yếu trì hoãn lần rebalance ban đầu để gom member mới. Nó không sửa được heartbeat bị mất, handler quá chậm, duplicate static ID hoặc subscription thay đổi liên tục.

### Tăng session timeout luôn làm group ổn định hơn

Không đúng. Timeout lớn giảm nguy cơ loại member do gián đoạn ngắn, nhưng làm chậm phát hiện member chết. Chọn theo mục tiêu phục hồi và thời gian chấp nhận partition không được xử lý.

### Tăng số consumer luôn tăng throughput

Không đúng. Một partition trong cùng group chỉ được giao cho tối đa một consumer tại một thời điểm. Consumer vượt số partition có thể không nhận assignment.

### Static membership loại bỏ hoàn toàn rebalance

Không đúng. `group.instance.id` giảm rebalance do restart ngắn của cùng logical instance. Thay đổi topology, subscription, partition hoặc assignor vẫn có thể làm group rebalance.

## 11. Checklist xác định đúng phía cấu hình

- [ ] Đã xác định client dùng classic hay consumer group protocol mới.
- [ ] `group.id` đúng với luồng xử lý và không vô tình dùng chung giữa ứng dụng độc lập.
- [ ] `group.instance.id` ổn định, duy nhất nếu dùng static membership.
- [ ] Với classic protocol, `session.timeout.ms` nằm trong broker min/max.
- [ ] Với classic protocol, `heartbeat.interval.ms` phù hợp session timeout.
- [ ] `max.poll.interval.ms` phù hợp thời gian xử lý batch thực tế.
- [ ] `max.poll.records` không làm batch vượt giới hạn xử lý.
- [ ] Assignor tương thích giữa các member trong classic protocol.
- [ ] `group.initial.rebalance.delay.ms` chỉ được điều chỉnh cho mục tiêu initial rebalance.
- [ ] `group.max.size` đủ cho số member dự kiến.
- [ ] Nếu dùng consumer protocol mới, đã kiểm tra cấu hình `group.consumer.*` trên broker.
- [ ] Đã đối chiếu cấu hình runtime, broker effective config và log coordinator.
- [ ] Đã đo rebalance, lag, poll interval và thời gian xử lý trước khi thay đổi.

Rebalance là kết quả phối hợp giữa consumer client và group coordinator. Client quyết định cách tham gia, heartbeat, poll và subscription; broker xác thực giới hạn, giữ trạng thái group và thực hiện điều phối. Xác định đúng phía sở hữu từng cấu hình giúp thay đổi có mục tiêu, tránh chỉnh nhầm tham số và làm sự cố kéo dài hơn.
