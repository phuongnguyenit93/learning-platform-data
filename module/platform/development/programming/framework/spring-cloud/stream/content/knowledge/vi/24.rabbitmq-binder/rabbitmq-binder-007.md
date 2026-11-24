# Quorum queue và lựa chọn kiểu queue theo nhu cầu

RabbitMQ hỗ trợ nhiều kiểu lưu trữ message, trong đó classic queue, quorum queue và stream giải quyết những nhu cầu khác nhau. Classic queue phù hợp với mô hình queue truyền thống khi một bản sao là đủ. Quorum queue lưu bản sao trên nhiều node và dùng thuật toán Raft để duy trì trạng thái khi node gặp sự cố. RabbitMQ stream là log bền vững, cho phép nhiều consumer đọc lại dữ liệu theo offset thay vì xóa message sau khi một consumer xác nhận.

Spring Cloud Stream RabbitMQ binder ánh xạ destination logic thành exchange và queue cho từng consumer group. Với queue thông thường, binder tạo classic queue theo mặc định. Có thể cấu hình thuộc tính quorum.enabled để binder tạo quorum queue cho group queue; dead-letter queue cũng có cấu hình riêng. Binder còn có hỗ trợ RabbitMQ Stream Plugin với cấu hình container và producer riêng. Việc chọn đúng kiểu dữ liệu cần dựa trên yêu cầu về tính sẵn sàng, replay, fan-out, retention, thứ tự và chi phí vận hành.

Bài học này giải thích sự khác nhau giữa classic queue, quorum queue và stream; cách RabbitMQ binder khai báo các kiểu này; cách chọn quorum size, xử lý poison message và dead-letter; các giới hạn cần biết; cũng như cách triển khai, kiểm thử và chuyển đổi queue an toàn.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt classic queue, quorum queue và RabbitMQ stream.
- Giải thích quorum, leader/follower và replication dựa trên Raft.
- Chọn quorum queue cho luồng công việc cần độ bền và tính sẵn sàng cao.
- Cấu hình quorum queue bằng RabbitMQ binder cho consumer group.
- Cấu hình quorum size, delivery limit và dead-letter queue.
- Hiểu các giới hạn của quorum queue so với classic queue.
- Phân biệt queue tiêu thụ phá hủy với stream có thể đọc lại.
- Sử dụng hỗ trợ RabbitMQ Stream Plugin trong binder đúng trường hợp.
- Lập kế hoạch migration và kiểm thử failure, redelivery, DLQ.

## 1. Kiểu queue quyết định semantics lưu trữ

Trong RabbitMQ, exchange nhận message từ producer rồi định tuyến tới queue hoặc stream theo binding. Queue lưu message cho tới khi consumer xử lý và xác nhận; stream lưu log có thể được nhiều consumer đọc lại.

Ba lựa chọn chính:

| Kiểu | Cấu trúc lưu trữ | Replication | Cách đọc | Trường hợp điển hình |
|---|---|---|---|---|
| Classic queue | Queue FIFO truyền thống | Không replicate queue trên nhiều node trong RabbitMQ 4.x | Destructive consume: message được loại bỏ sau khi ack | Work queue thông thường, dữ liệu có thể tái tạo hoặc yêu cầu HA không cao |
| Quorum queue | Queue có leader và follower | Replicate theo Raft, cần majority để tiến triển | Destructive consume, có ack và redelivery | Đơn hàng, thanh toán, công việc quan trọng cần HA |
| Stream | Log append-only | Replicated, durable | Non-destructive; consumer đọc theo offset và có thể replay | Event log, fan-out lớn, replay, backlog dài và throughput cao |

Kiểu queue không chỉ là một tùy chọn hiệu năng. Nó ảnh hưởng cách dữ liệu sống qua sự cố, cách consumer đọc lại, cách dead-letter hoạt động và cách đội vận hành mở rộng topology.

## 2. Classic queue

Classic queue là kiểu queue truyền thống của RabbitMQ. Nó hỗ trợ exchange/binding, acknowledgement, prefetch, message TTL, queue TTL, priority, queue length limit và dead-letter exchange.

### 2.1. Đặc điểm

- Một queue classic không replicate message state trên nhiều node.
- Queue có thể durable; message có thể persistent để tồn tại qua restart theo điều kiện lưu trữ.
- Consumer nhận message và ack; sau khi ack thành công, message được loại bỏ khỏi queue.
- Hỗ trợ queue tạm thời, exclusive queue và auto-delete queue.
- Hỗ trợ nhiều tính năng queue truyền thống như priority và TTL.

Durable queue và persistent message giúp phục hồi sau restart, nhưng không đồng nghĩa queue được replicate giữa các node. Nếu node chứa classic queue gặp sự cố nghiêm trọng, khả năng phục hồi phụ thuộc bản lưu trữ và cấu hình cụ thể.

### 2.2. Khi nào chọn classic queue?

Classic queue phù hợp khi:

- Workload có thể chấp nhận một bản sao queue.
- Message có thể tái tạo hoặc tác động khi mất dữ liệu được đánh giá là chấp nhận được.
- Cần queue tạm thời, exclusive hoặc auto-delete.
- Workload cần các tính năng classic mà quorum queue không hỗ trợ.
- Topology có số lượng queue lớn và yêu cầu footprint thấp hơn.

Trong RabbitMQ 4.0 trở lên, classic queue không còn mirrored queue replication. Nếu cần một queue replicated và có HA, nên đánh giá quorum queue hoặc stream.

## 3. Quorum queue

Quorum queue là queue durable và replicated dựa trên thuật toán Raft. Mỗi quorum queue có một leader và các follower. Leader xử lý hoạt động ghi; thay đổi được replicate tới các thành viên. Một thao tác cần được đa số thành viên xác nhận để được xem là committed.

### 3.1. Quorum nghĩa là gì?

Với N thành viên, majority là:

\[
Q = \left\lfloor \frac{N}{2} \right\rfloor + 1
\]

Ví dụ:

| Số thành viên | Majority cần thiết | Số thành viên có thể mất mà vẫn còn majority |
|---:|---:|---:|
| 1 | 1 | 0 |
| 3 | 2 | 1 |
| 5 | 3 | 2 |
| 7 | 4 | 3 |

Một quorum queue có ba thành viên có thể tiếp tục hoạt động khi một thành viên không sẵn sàng, miễn là hai thành viên còn lại có thể liên lạc và tạo thành majority. Nếu mất majority, queue không thể tiếp tục các thao tác cần consensus cho đến khi majority được khôi phục.

Quorum size lẻ thường được ưu tiên vì thêm một thành viên từ số chẵn sang số lẻ có thể tăng khả năng chịu lỗi; thêm một thành viên từ số lẻ sang số chẵn thường không tăng số node có thể mất mà vẫn giữ majority.

### 3.2. Leader và follower

~~~text
Quorum queue: orders.fulfillment

Node A: Leader
   | \
   |  \ replicate log
   v   v
Node B: Follower
Node C: Follower

Majority = 2 trong 3 thành viên
~~~

Nếu leader gặp sự cố, các thành viên còn lại có thể bầu leader mới. Thời gian chuyển đổi phụ thuộc trạng thái cluster, mạng và việc các follower có đủ dữ liệu cần thiết. Consumer có thể gặp gián đoạn ngắn trong lúc leader được bầu lại.

Replication không loại bỏ mọi lỗi. Nếu mạng phân vùng làm mất majority hoặc nhiều node cùng hỏng, queue có thể tạm ngừng nhận/đẩy message. Quorum queue ưu tiên tính nhất quán và an toàn dữ liệu hơn việc tiếp tục ghi trên một minority bị cô lập.

### 3.3. Đặc điểm dữ liệu

- Quorum queue luôn durable; không hỗ trợ queue non-durable.
- Quorum queue không hỗ trợ exclusive queue hoặc queue tạm thời.
- Message được lưu bền vững trên các thành viên theo semantics của quorum queue.
- Có poison message handling và delivery limit.
- Hỗ trợ dead-letter exchange; có thể cấu hình dead-letter at-least-once với các điều kiện cụ thể.
- Hỗ trợ TTL và giới hạn độ dài queue, nhưng một số overflow/dead-letter combination bị giới hạn.

Quorum queue phù hợp với queue sống lâu và chứa công việc quan trọng, ví dụ lệnh thanh toán, đơn hàng cần xử lý hoặc yêu cầu nghiệp vụ không nên mất khi một node dừng.

## 4. Khi nào nên chọn quorum queue?

Chọn quorum queue khi yêu cầu chính là một queue công việc có độ bền cao và khả năng tiếp tục hoạt động khi một node RabbitMQ gặp sự cố.

Ví dụ:

- Tiếp nhận đơn hàng và lệnh thanh toán.
- Công việc nền quan trọng cần được giao lại sau khi consumer hoặc node lỗi.
- Hàng đợi xử lý nghiệp vụ mà mất message làm sai trạng thái hệ thống.
- Queue cần leader election và replication thay vì một bản sao đơn.

Không nên chuyển mọi queue sang quorum chỉ vì quorum có replication. Một hệ thống có hàng nghìn queue nhỏ, queue tạm thời, RPC reply queue hoặc message có thể tái tạo có thể không cần chi phí replication cho từng queue.

### 4.1. Những trường hợp quorum không phải lựa chọn tốt nhất

| Nhu cầu | Lý do cần cân nhắc |
|---|---|
| Queue tạm thời, exclusive hoặc auto-delete | Quorum queue không hỗ trợ semantics queue tạm thời |
| RPC reply queue tồn tại ngắn | Replication thường không mang lại lợi ích tương xứng |
| Message có thể tái tạo và không yêu cầu HA | Classic queue có thể đơn giản hơn |
| Fan-out lớn với nhiều subscriber cần đọc lại | Stream có thể phù hợp hơn |
| Event log dài hạn | Stream hỗ trợ offset và replay tự nhiên hơn |
| Hàng triệu message cần được giữ lại lâu | Stream thường phù hợp hơn queue truyền thống |

Quorum queue là lựa chọn tốt cho nhiều queue công việc quan trọng, nhưng không phải giải pháp thay thế mọi kiểu queue.

## 5. Cấu hình quorum queue bằng Spring Cloud Stream RabbitMQ binder

RabbitMQ binder mặc định tạo queue classic cho consumer group. Có thể đặt thuộc tính consumer quorum.enabled thành true để tạo quorum queue thay cho classic queue.

Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: fulfillment
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              quorum:
                enabled: true
                initialGroupSize: 3
                deliveryLimit: 10
~~~

Trong ví dụ:

- Destination là tên exchange logic mà binder sử dụng.
- Group tạo queue riêng cho consumer group, thường theo tên destination và group.
- quorum.enabled yêu cầu binder khai báo queue dưới dạng quorum queue.
- quorum.initialGroupSize đặt số thành viên ban đầu của quorum khi queue được tạo.
- quorum.deliveryLimit đặt giới hạn delivery trước khi message bị drop hoặc dead-letter theo cấu hình broker.

Các thuộc tính quorum là thuộc tính riêng của Rabbit binder, nằm dưới prefix spring.cloud.stream.rabbit.bindings.<binding>.consumer. Hãy dùng đúng tên binding thực tế, ví dụ processOrder-in-0.

### 5.1. Dùng cấu hình properties để dễ đối chiếu

~~~properties
spring.cloud.stream.bindings.processOrder-in-0.destination=orders
spring.cloud.stream.bindings.processOrder-in-0.group=fulfillment
spring.cloud.stream.rabbit.bindings.processOrder-in-0.consumer.quorum.enabled=true
spring.cloud.stream.rabbit.bindings.processOrder-in-0.consumer.quorum.initialGroupSize=3
spring.cloud.stream.rabbit.bindings.processOrder-in-0.consumer.quorum.deliveryLimit=10
~~~

Nếu binder đang dùng không nhận các thuộc tính này, kiểm tra phiên bản Spring Cloud Stream Rabbit binder và metadata cấu hình của phiên bản đó. Không giả định mọi version có cùng property set.

### 5.2. Provision queue trước khi consumer chạy

Rabbit binder có thể khai báo queue khi consumer binding được tạo. Với producer cần provision queue cho các group trước khi consumer khởi động, dùng requiredGroups ở producer binding. Các thuộc tính quorum phía producer chỉ áp dụng cho các group được khai báo trong requiredGroups.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          producer:
            required-groups:
              - fulfillment
      rabbit:
        bindings:
          publishOrder-out-0:
            producer:
              quorum:
                enabled: true
                initialGroupSize: 3
                deliveryLimit: 10
~~~

required-groups giúp binder tạo queue cho group đã chỉ định ngay cả khi consumer chưa được triển khai. Nếu không có requiredGroups, các thuộc tính quorum phía producer không có queue group nào để áp dụng.

### 5.3. Quorum queue và dead-letter queue

Quorum queue nguồn và dead-letter queue là hai queue riêng, có thể chọn kiểu khác nhau. Rabbit binder cung cấp dlqQuorum.enabled để tạo DLQ dưới dạng quorum queue khi binder tự provision DLQ cho required group.

Ví dụ cấu hình consumer:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: fulfillment
          consumer:
            max-attempts: 3
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              quorum:
                enabled: true
                deliveryLimit: 10
              autoBindDlq: true
              dlqQuorum:
                enabled: true
~~~

max-attempts là retry của binder container. quorum.deliveryLimit là giới hạn delivery ở broker cho quorum queue; hai thuộc tính giải quyết các lớp retry khác nhau. Cần kiểm tra cách binder reject/requeue message để tránh retry của container và delivery limit của broker tương tác ngoài dự kiến.

Nếu tự quản lý DLX/DLQ, hãy cấu hình topology ở RabbitMQ và tắt các phần auto declaration tương ứng của binder để tránh hai bên khai báo không thống nhất.

## 6. Quorum size và placement

Quorum queue chỉ có thể chịu lỗi node nếu các thành viên được phân bố trên những node độc lập. Đặt initialGroupSize bằng ba nhưng cả ba thành viên đều phụ thuộc cùng một node hoặc cùng failure domain sẽ không tạo HA thực chất.

### 6.1. Chọn số thành viên

Một cấu hình thường gặp:

- 3 thành viên cho đa số queue quan trọng, có thể chịu mất một thành viên.
- 5 thành viên khi cần chịu mất hai thành viên và chấp nhận chi phí replication cao hơn.
- Tránh tăng thành viên chỉ để tăng số consumer; replication member count và consumer concurrency là hai khái niệm khác nhau.

Số thành viên lớn hơn làm tăng lưu lượng replicate, disk I/O và yêu cầu mạng. Hãy cân bằng mức chịu lỗi với chi phí vận hành.

### 6.2. Đặt thành viên qua nhiều node hoặc availability zone

Trong cluster nhiều node, RabbitMQ quản lý thành viên queue. Nên phân bố member trên các node và failure domain khác nhau, ví dụ các availability zone riêng biệt nếu hạ tầng hỗ trợ.

Nếu cả leader và follower đều nằm trên cùng một máy vật lý hoặc cùng một zone có thể mất đồng thời, quorum queue không bảo vệ được trước lỗi chung đó. Hãy kiểm tra placement thực tế thay vì chỉ nhìn số member.

### 6.3. Thay đổi thành viên sau khi tạo

initialGroupSize là số thành viên ban đầu khi queue được khai báo. Nó không phải cơ chế tự thay đổi số replica theo mỗi lần ứng dụng restart. RabbitMQ có cơ chế quản lý membership và reconciliation riêng; hãy dùng công cụ quản trị hoặc policy/feature được hỗ trợ để thay đổi topology.

Không xóa queue production để đổi quorum size mà chưa có kế hoạch drain, backup hoặc chuyển dữ liệu. Thay đổi membership cần được kiểm thử khi node đang hoạt động và khi node mất kết nối.

## 7. Poison message và delivery limit

Poison message là message liên tục khiến consumer thất bại và bị requeue, nên không bao giờ được ack thành công. Nếu không có giới hạn, một message lỗi có thể tạo vòng lặp redelivery và chiếm tài nguyên.

Quorum queue theo dõi số lần giao lại không thành công và có thể áp dụng delivery limit. Khi vượt giới hạn, message được drop hoặc dead-letter nếu queue có DLX.

Ví dụ binder:

~~~yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              quorum:
                enabled: true
                deliveryLimit: 10
              autoBindDlq: true
~~~

deliveryLimit là thuộc tính của quorum queue và phụ thuộc broker version. Giá trị mặc định có thể do RabbitMQ broker quyết định; nếu muốn hành vi ổn định giữa các môi trường, hãy cấu hình rõ ràng và kiểm thử.

### 7.1. Delivery limit khác retry của binder

Binder retry có thể gọi lại listener trong container trước khi message bị reject. Delivery limit của quorum queue theo dõi các lần giao lại thất bại ở broker. Nếu binder retry ba lần trong cùng một delivery rồi reject, delivery count của broker có thể không tăng ba lần như cách đếm application retry.

Hãy xác định rõ:

- Số lần listener được gọi trong một delivery.
- Khi nào binder reject hoặc requeue.
- Khi nào broker tăng delivery count.
- Điều gì xảy ra khi vượt delivery limit.
- DLX có được cấu hình để giữ message lỗi hay không.

### 7.2. RabbitMQ 4.3 và nack/reject

Từ RabbitMQ 4.3, delivery limit của quorum queue dựa trên delivery-count. Một số kiểu trả message về queue bằng basic.nack có thể không tăng delivery count theo cách các phiên bản trước đã làm. Nếu ứng dụng dựa vào delivery limit để ngăn poison message nhưng dùng nack với requeue=true, cần kiểm tra semantics phiên bản broker và cân nhắc basic.reject theo hướng dẫn RabbitMQ.

Không dựa vào delivery limit như lớp bảo vệ duy nhất. Binder retry, dead-letter, idempotency và logging vẫn cần được cấu hình.

## 8. Dead-letter và at-least-once dead-lettering

Quorum queue hỗ trợ dead-letter exchange. Tuy nhiên, mặc định dead-lettering có thể là at-most-once: message được chuyển khỏi queue nguồn và có thể mất nếu đích không nhận thành công trong một số tình huống.

RabbitMQ hỗ trợ at-least-once dead-lettering cho quorum queue với điều kiện cấu hình cụ thể:

- dead-letter-strategy phải là at-least-once.
- overflow phải là reject-publish.
- Queue phải có dead-letter-exchange.
- Với các phiên bản yêu cầu, cần bật feature flag stream_queue của broker.

Các khóa dead-letter-strategy, overflow và dead-letter-exchange thường được cấu hình bằng policy RabbitMQ. Hãy xác minh broker version, feature flag và policy áp dụng cho đúng queue trước khi bật cơ chế này.

Ở chế độ này, queue nguồn giữ message đã dead-letter cho tới khi queue đích xác nhận. Điều này giảm nguy cơ mất message trong quá trình chuyển, nhưng có thể tạo duplicate ở đích khi confirm bị mất hoặc retry.

### 8.1. Vì sao cần giới hạn độ dài?

At-least-once dead-lettering giữ message ở queue nguồn trong khi đích chưa xác nhận. Nếu DLX hoặc queue đích không sẵn sàng lâu, message dead-letter có thể tiếp tục chiếm dung lượng queue nguồn.

Nên đặt max-length hoặc max-length-bytes phù hợp và theo dõi queue depth, disk và memory. Overflow reject-publish có thể khiến publisher bị từ chối khi queue đầy; ứng dụng cần xử lý publish nack/return và retry.

### 8.2. Không nhầm binder republish với broker dead-letter

Rabbit binder có thể dùng retry trong container rồi republish message lỗi tới DLQ với các header exception. Đây là hành vi binder thực hiện. RabbitMQ broker dead-lettering chuyển message theo DLX khi message bị reject, hết TTL hoặc vượt một số giới hạn queue.

Hai cách có thể khác nhau về metadata, xác nhận, duplicate và nơi message được chuyển. Hãy xác định một chính sách rõ ràng để không vừa republish vừa broker-dead-letter cùng một luồng ngoài ý muốn.

## 9. RabbitMQ stream và super stream

RabbitMQ stream là một cấu trúc dữ liệu khác queue truyền thống. Stream là log append-only, replicated và durable. Consumer đọc theo offset; việc một consumer đọc message không xóa message khỏi stream. Nhiều consumer có thể đọc cùng dữ liệu độc lập và replay từ offset cũ trong thời gian retention.

### 9.1. Khi nào chọn stream?

Stream phù hợp khi:

- Nhiều consumer cần đọc lại cùng một event log.
- Cần replay hoặc đọc từ offset/timestamp.
- Fan-out lớn mà không muốn tạo một queue riêng cho mỗi subscriber.
- Có backlog dài hoặc workload thiên về throughput.
- Muốn mô hình log bền vững thay vì work queue destructive.

Stream không thay thế quorum queue cho mọi use case. Work queue thông thường cần message biến mất sau ack vẫn phù hợp với queue. Stream giữ dữ liệu theo retention và consumer offset.

### 9.2. Stream khác quorum queue

| Khía cạnh | Quorum queue | RabbitMQ stream |
|---|---|---|
| Mô hình | Queue replicated dựa trên Raft | Log append-only replicated |
| Đọc | Destructive consume, ack xong message được loại khỏi queue | Non-destructive, consumer đọc theo offset |
| Replay | Không phải mô hình đọc lại tự nhiên sau ack | Hỗ trợ replay trong retention |
| Dead-letter exchange | Có | Không có DLX như queue thông thường |
| TTL | Có message/queue TTL với một số giới hạn | Dùng retention thay vì queue TTL |
| Priority | Có strict priority | Không hỗ trợ message priority |
| Work distribution | Phù hợp worker queue | Phù hợp log/fan-out/replay |

Stream cần plugin và client/protocol phù hợp. Không thể bật stream bằng cách đặt quorum.enabled=true; đó là hai loại dữ liệu khác nhau.

## 10. Hỗ trợ RabbitMQ Stream Plugin trong binder

Spring Cloud Stream Rabbit binder có hỗ trợ ban đầu cho RabbitMQ Stream Plugin. Để sử dụng, classpath cần có spring-rabbit-stream cùng version với spring-amqp và spring-rabbit tương ứng.

### 10.1. Consumer stream

Có thể cấu hình consumer container type là stream:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        audit-in-0:
          destination: audit-stream
          group: audit-reader
      rabbit:
        bindings:
          audit-in-0:
            consumer:
              containerType: stream
~~~

Với stream container, nhiều consumer property dành cho queue thường không được hỗ trợ. Binder reference nêu rõ concurrency chỉ được hỗ trợ cho super streams; mỗi binding stream thường consume một stream queue. Việc chọn offset, tracking offset và consumer name có thể cần customizer.

### 10.2. Super stream

Super stream là một stream logic được chia thành nhiều partition stream. Nó phù hợp khi cần scale consumer theo partition trong khi vẫn có semantics log.

Binder có hỗ trợ consumer super stream với cấu hình instance count, concurrency, container type và super-stream:

~~~properties
spring.cloud.stream.bindings.audit-in-0.destination=audit
spring.cloud.stream.bindings.audit-in-0.group=audit-reader
spring.cloud.stream.bindings.audit-in-0.consumer.instance-count=3
spring.cloud.stream.bindings.audit-in-0.consumer.concurrency=3
spring.cloud.stream.rabbit.bindings.audit-in-0.consumer.container-type=STREAM
spring.cloud.stream.rabbit.bindings.audit-in-0.consumer.super-stream=true
~~~

Topology super stream và số partition được binder provision theo cấu hình. Hãy kiểm tra mapping partition, routing key và offset trước khi triển khai nhiều instance.

### 10.3. Producer stream

Rabbit binder hỗ trợ producer type:

- AMQP: dùng AMQP client cho classic và quorum queue.
- STREAM_SYNC: dùng RabbitMQ Stream Plugin client và chờ confirm.
- STREAM_ASYNC: dùng RabbitMQ Stream Plugin client bất đồng bộ.

Ví dụ cấu hình producer:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishAudit-out-0:
          destination: audit-stream
      rabbit:
        bindings:
          publishAudit-out-0:
            producer:
              producerType: STREAM_SYNC
~~~

Khi dùng STREAM_SYNC hoặc STREAM_ASYNC, các producer property dành cho AMQP queue có thể không được hỗ trợ. Hãy kiểm tra binder reference cho producer stream và không sao chép cấu hình quorum queue sang stream producer.

## 11. Giới hạn quan trọng khi chuyển sang quorum queue

Quorum queue chia sẻ nhiều hành vi với classic queue nhưng có những khác biệt cần kiểm tra:

- Không hỗ trợ non-durable queue.
- Không hỗ trợ exclusive queue; dùng single active consumer nếu cần một consumer active và standby.
- Không hỗ trợ global QoS prefetch; dùng per-consumer prefetch.
- Có delivery limit và poison message handling.
- Hỗ trợ at-least-once dead-lettering nhưng cần overflow reject-publish và cấu hình DLX.
- Priority được xử lý theo strict priority, không phải mọi semantics priority của classic queue đều giống nhau.
- Một số tính năng và tham số queue có giới hạn riêng.

Trước khi bật quorum.enabled, hãy kiểm tra queue đang tồn tại có đúng type hay không. Queue type được xác định lúc khai báo và không thể đổi bằng policy. Nếu binder cố khai báo quorum trên một queue classic cùng tên, RabbitMQ có thể trả lỗi PRECONDITION_FAILED do argument x-queue-type không khớp.

## 12. Migration từ classic sang quorum

Không thể đổi trực tiếp queue classic hiện hữu thành quorum chỉ bằng việc đổi cấu hình binder. RabbitMQ không thay đổi queue type tại chỗ.

Một quy trình migration an toàn:

1. Xác định queue, exchange, binding và consumer group đang sử dụng.
2. Đánh giá backlog, message đang unacknowledged và khả năng dừng producer.
3. Tạo queue quorum mới với tên hoặc destination mới.
4. Kiểm tra số member, placement và DLX/DLQ.
5. Chuyển producer hoặc binding theo một giai đoạn có kiểm soát.
6. Drain queue cũ hoặc xử lý message tồn đọng theo kế hoạch.
7. Chuyển consumer sang queue mới.
8. Theo dõi publisher confirms, redelivery, queue depth và consumer health.
9. Chỉ xóa queue cũ sau khi xác nhận không còn dữ liệu cần giữ.

Nếu cần giữ nguyên tên queue, có thể phải dừng consumer, drain hoặc sao chép message, xóa queue cũ rồi khai báo lại đúng type. Đây là thay đổi topology có thể gây gián đoạn và cần backup/rollback plan.

### 12.1. Khai báo queue có sẵn

Nếu hạ tầng RabbitMQ do nhóm nền tảng quản lý, ứng dụng có thể cấu hình binder không tự khai báo queue hoặc không bind queue theo cấu hình. Khi đó, đội vận hành phải tạo exchange, queue, type và binding trước.

Không để binder và hạ tầng khai báo cùng một queue với các tham số không tương thích. Mọi thay đổi x-queue-type, durability, exclusivity và arguments phải được phối hợp giữa application deployment và broker provisioning.

## 13. Kiểm thử quorum queue

Test cần xác minh cả cấu hình khai báo và hành vi khi có lỗi node.

### 13.1. Kiểm thử queue type

Với RabbitMQ test broker:

1. Khởi động broker có hỗ trợ quorum queue.
2. Khởi động ứng dụng Spring Cloud Stream với consumer binding group cố định và quorum.enabled=true.
3. Xác minh queue được tạo có argument x-queue-type=quorum.
4. Xác minh initial group size theo cấu hình.
5. Gửi message và xác minh consumer nhận, xử lý và ack thành công.

Không chỉ kiểm tra property đã được bind vào Spring context. Hãy kiểm tra queue thực tế trong RabbitMQ Management API hoặc CLI.

### 13.2. Kiểm thử leader failure

Trong cluster test có nhiều node:

- Xác định node đang làm leader của queue.
- Dừng hoặc cô lập node đó theo cách kiểm thử có kiểm soát.
- Quan sát leader election và thời gian phục hồi.
- Xác minh consumer reconnect và tiếp tục xử lý.
- Xác minh message đã được confirm không bị mất ngoài semantics được cam kết.

Không chạy thử nghiệm dừng node trên production khi chưa có kế hoạch và phê duyệt vận hành.

### 13.3. Kiểm thử poison message và DLQ

Gửi một message khiến listener luôn thất bại. Xác minh:

- Retry của binder chạy đúng số lần.
- Message bị reject/requeue theo cấu hình.
- Delivery limit của quorum queue hoạt động theo broker version.
- Message được dead-letter hoặc drop theo policy.
- DLQ có đúng queue type nếu dlqQuorum.enabled=true.
- Consumer có thể xử lý message hợp lệ tiếp theo.

### 13.4. Kiểm thử stream riêng biệt

Nếu chọn stream, kiểm thử offset tracking, replay, retention và super stream partition assignment. Không dùng kết quả test quorum queue để suy ra hành vi stream vì semantics consume và storage khác nhau.

## 14. Quan sát và vận hành

Quorum queue cần giám sát cả trạng thái queue lẫn trạng thái cluster:

| Chỉ số | Ý nghĩa |
|---|---|
| Queue leader | Node đang điều phối queue |
| Quorum members | Số member và trạng thái từng follower |
| Majority availability | Queue có đủ thành viên để tiến triển hay không |
| Ready messages | Số message đang chờ consumer |
| Unacknowledged messages | Message đã giao nhưng chưa ack |
| Redelivery/delivery count | Dấu hiệu consumer lỗi hoặc poison message |
| DLQ depth | Message lỗi đang chờ điều tra |
| Publisher confirms/nacks | Kết quả broker xác nhận publish |
| Disk and memory | Tài nguyên node và queue |
| Raft/leader election events | Sự cố hoặc thay đổi trạng thái replication |

Với stream, theo dõi retention, disk, consumer offset/lag và tốc độ đọc. Stream có thể giữ message sau khi consumer đọc; queue depth không phải thước đo backlog tương đương queue destructive.

### 14.1. Cảnh báo

Cân nhắc cảnh báo khi:

- Queue mất majority hoặc không có leader.
- Leader election lặp lại.
- Redelivery tăng liên tục.
- Queue hoặc DLQ depth tăng kéo dài.
- Publisher nack/return tăng.
- Disk gần đầy hoặc node thường xuyên bị resource alarm.
- Consumer lag của stream vượt SLA.

Không chỉ theo dõi số message. Quorum queue có thể còn message nhưng không thể tiến triển vì mất majority; stream có thể giữ dữ liệu theo retention dù consumer đã đọc.

## 15. Những lỗi thường gặp

1. **Bật quorum cho mọi queue**: tăng chi phí replication không cần thiết. Hãy phân loại queue theo mức độ quan trọng và semantics.
2. **Nhầm durable với replicated**: durable classic queue vẫn không có replication như quorum. Hãy đánh giá failure domain.
3. **Đặt quorum size lớn mà không phân bố node**: các member cùng failure domain có thể hỏng đồng thời. Hãy kiểm tra placement.
4. **Dùng quorum cho exclusive hoặc temporary queue**: quorum không hỗ trợ các semantics này. Hãy dùng classic queue hoặc mô hình khác.
5. **Cho rằng quorum queue hoạt động khi mất majority**: queue có thể ngừng tiến triển khi không đủ consensus. Hãy thiết kế cluster và network đúng.
6. **Bật quorum.enabled trên queue classic đang tồn tại**: queue declaration có thể thất bại do x-queue-type không khớp. Hãy migration bằng queue mới hoặc drain có kế hoạch.
7. **Nhầm deliveryLimit với maxAttempts**: một thuộc tính thuộc broker quorum, một thuộc binder container. Hãy test cả hai.
8. **Không cấu hình DLQ cho poison message**: message có thể bị drop khi vượt delivery limit. Hãy xác định dead-letter policy và giám sát.
9. **Bật at-least-once dead-letter mà không giới hạn queue**: message chờ xác nhận có thể chiếm tài nguyên. Hãy cấu hình overflow và max length theo hướng dẫn broker.
10. **Coi stream là queue quorum**: stream có non-destructive read và replay theo offset. Hãy chọn theo semantics ứng dụng.
11. **Dùng queue consumer properties với stream container**: nhiều thuộc tính queue không được hỗ trợ. Hãy theo tài liệu Rabbit Stream binder.
12. **Dùng STREAM_SYNC/STREAM_ASYNC với cấu hình AMQP producer**: các producer property có thể không áp dụng. Hãy cấu hình theo producer type.
13. **Không kiểm tra queue type thật sau deploy**: cấu hình ứng dụng có thể không được áp dụng do queue đã tồn tại. Hãy kiểm tra broker metadata.

## 16. Quy trình lựa chọn kiểu queue

Khi thiết kế một destination RabbitMQ cho Spring Cloud Stream:

1. Xác định dữ liệu có cần được đọc lại sau khi consumer ack hay không.
2. Nếu cần replay/fan-out/log dài hạn, đánh giá RabbitMQ stream hoặc super stream.
3. Nếu cần work queue destructive và HA, đánh giá quorum queue.
4. Nếu một bản sao queue đáp ứng yêu cầu và cần queue tạm thời/exclusive, xem xét classic queue.
5. Xác định số quorum member và phân bố trên failure domain.
6. Cấu hình quorum.enabled và initialGroupSize trên binding phù hợp.
7. Xác định deliveryLimit, retry của binder và DLQ.
8. Kiểm tra queue type không xung đột với queue đã tồn tại.
9. Kiểm thử node failure, leader election, redelivery, DLT và publisher confirm.
10. Thiết lập dashboard cho queue state, majority, backlog, DLQ và tài nguyên.
11. Lập kế hoạch migration trước khi thay đổi kiểu queue.

## Kết luận

Classic queue là lựa chọn truyền thống cho work queue khi một bản sao đáp ứng yêu cầu. Quorum queue dùng Raft để replicate queue trên nhiều node và là lựa chọn phù hợp cho công việc quan trọng cần độ bền và HA. RabbitMQ stream là log bền vững, replicated và có thể đọc lại theo offset, phù hợp với replay, fan-out và backlog dài.

Spring Cloud Stream RabbitMQ binder cho phép tạo quorum queue bằng quorum.enabled, cấu hình initialGroupSize và deliveryLimit, đồng thời chọn kiểu DLQ riêng bằng dlqQuorum.enabled. Với stream, binder dùng containerType=stream cho consumer và producerType cho producer, kèm dependency/plugin tương ứng. Hãy chọn theo semantics lưu trữ và tiêu thụ, kiểm tra queue type thực tế trên broker và kiểm thử failure trước khi triển khai production.

## Tài liệu tham khảo

- [Spring Cloud Stream RabbitMQ Binder — Consumer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html)
- [Spring Cloud Stream RabbitMQ Binder — Reference Guide](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html)
- [RabbitMQ — Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues)
- [RabbitMQ — Classic Queues](https://www.rabbitmq.com/docs/classic-queues)
- [RabbitMQ — Streams and Super Streams](https://www.rabbitmq.com/docs/streams)
