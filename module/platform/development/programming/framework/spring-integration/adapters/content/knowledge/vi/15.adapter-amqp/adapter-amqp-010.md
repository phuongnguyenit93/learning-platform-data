# Manual acknowledgment và retry

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **manual acknowledgment (MANUAL ACK)** với **AUTO ACK** và **NONE** ở Spring AMQP listener container; xác định ai chịu trách nhiệm xác nhận delivery.
- Sử dụng đúng **delivery tag**, **AMQP channel**, **basicAck**, **basicNack**, **basicReject**, các cờ **multiple** và **requeue**.
- Giải thích chính xác mối quan hệ giữa **ACK**, **redelivery**, **prefetch**, **consumer transaction**, lỗi business và độ tin cậy end-to-end.
- Thiết kế retry **có giới hạn**, phân biệt lỗi tạm thời với lỗi cố định; tránh vòng lặp requeue nóng và phối hợp **DLX/DLQ**.
- Xây dựng ví dụ **Spring Integration Java DSL**: RabbitMQ → listener container MANUAL → AMQP inbound channel adapter → DirectChannel → service activator → ACK/NACK.
- Hiểu vì sao **ExecutorChannel**, **QueueChannel**, listener error handler, MessageConverter và shutdown có thể làm thay đổi ranh giới xác nhận.
- Áp dụng **idempotent consumer**, inbox/unique constraint, quan sát ready/unacked, xử lý crash/restart và kiểm thử sự cố trước production.

## 1. Bài toán: khi nào được nói đã xử lý xong?

Giả sử dịch vụ **Warehouse** nhận sự kiện **OrderCreated** từ RabbitMQ và phải cập nhật cơ sở dữ liệu tồn kho. Một delivery đi qua nhiều chặng:

~~~mermaid
flowchart LR
    P["OrderService"] --> X["RabbitMQ exchange"]
    X --> Q["orders.created.q"]
    Q --> L["Spring AMQP<br/>listener container"]
    L --> A["AMQP inbound<br/>channel adapter"]
    A --> C["DirectChannel"]
    C --> H["Service activator<br/>WarehouseService"]
    H --> DB[("Warehouse DB")]
    L -. "basicAck / basicNack / basicReject" .-> Q
~~~

Nếu ứng dụng **ACK trước khi transaction database commit**, rồi tiến trình chết, RabbitMQ có thể xóa trách nhiệm giao lại delivery trong khi nghiệp vụ chưa hoàn tất. Ngược lại, nếu database đã commit nhưng ứng dụng chết **trước khi RabbitMQ nhận ACK**, broker có thể giao lại cùng sự kiện sau khi connection đóng. Khi đó consumer có thể thực hiện side effect hai lần nếu không chống trùng.

**Manual acknowledgment** cho phép ứng dụng chọn thời điểm xác nhận delivery. Tuy nhiên, việc tự gọi ACK **không tạo ra exactly-once end-to-end** và **không biến RabbitMQ thành một phần của transaction database**.

Bài học thuộc chương **Adapter AMQP** của module **SPRING_INTEGRATION_ADAPTERS**. Nguyên tắc chung khi nối những hệ thống ngoài bằng File, SFTP, HTTP, JMS, AMQP, Kafka hoặc database là: **xác định điểm đã tiếp nhận, điểm đã lưu bền, điểm đã xử lý và điểm có thể retry**. Đừng đánh đồng chúng với việc gọi MessageChannel.send() thành công.

## 2. Bốn loại tín hiệu không được nhầm

| Tín hiệu | Hướng | Nó xác nhận điều gì? | Nó không chứng minh |
| --- | --- | --- | --- |
| **Publisher confirm** | RabbitMQ broker → publisher | Broker xác nhận trạng thái một lần publish theo cơ chế confirms | Consumer đã commit nghiệp vụ |
| **Publisher return** | RabbitMQ broker → publisher | Message không route được theo điều kiện mandatory/returns | Consumer đã reject một delivery |
| **Consumer ACK/NACK** | Consumer/listener → RabbitMQ broker | Consumer xác nhận hoặc từ chối một **delivery** | Producer nhận được reply nghiệp vụ |
| **Business reply/event** | Consumer service → caller/hệ thống khác | Kết quả nghiệp vụ theo hợp đồng riêng | Broker chắc chắn không redeliver |

Trong bài này, **ACK** (trừ khi nêu rõ khác) là **consumer acknowledgment**: tín hiệu gửi sau khi RabbitMQ đã giao message đến consumer.

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant B as RabbitMQ
    participant L as Listener container
    participant H as WarehouseService
    P->>B: Publish OrderCreated
    B-->>P: Publisher confirm (nếu bật)
    B->>L: Delivery từ queue
    L->>H: Spring Message qua flow
    H->>H: Database transaction
    H-->>L: Thành công hoặc lỗi
    L-->>B: Consumer ACK/NACK
~~~

Một **AMQP inbound channel adapter** nhận message một chiều, không tự gửi business reply cho producer. Nếu nguồn ngoài cần request–reply, hãy cân nhắc **AMQP inbound/outbound gateway** và hợp đồng reply-to/correlation; ACK của consumer không thay thế reply đó.

## 3. AcknowledgeMode.AUTO, MANUAL và NONE

Spring AMQP listener container có các kiểu xác nhận thường gặp:

| Mode | Ai quyết định ACK? | Đặc điểm | Rủi ro thường gặp |
| --- | --- | --- | --- |
| **AUTO** | Container ACK/NACK dựa vào kết quả listener, error handler và cấu hình | Phù hợp khi handler chạy đồng bộ, muốn container chịu trách nhiệm ACK | Exception bị nuốt hoặc công việc async chạy sau callback có thể khiến ACK sớm |
| **MANUAL** | Ứng dụng chủ động ACK/NACK/reject bằng AMQP channel và delivery tag | Chủ động đặt điểm xác nhận sau commit hoặc bước lưu bền | Quên ACK, double ACK, sai channel/tag, requeue loop |
| **NONE** | Consumer nhận theo cơ chế không yêu cầu explicit acknowledgment | Đơn giản nhưng broker không còn chờ kết quả xử lý theo cách AUTO/MANUAL | Tiến trình chết sau delivery có thể mất cơ hội redelivery |

### 3.1. AUTO không có nghĩa broker ACK ngay khi giao

Trong Spring AMQP, **AUTO** nghĩa **container** chịu trách nhiệm ACK sau khi listener hoàn tất theo policy. Đối với một handler đồng bộ chạy qua DirectChannel, exception có thể lan về container và dẫn đến reject/requeue tùy loại lỗi cùng cấu hình. AUTO không có nghĩa mọi lỗi đều retry và cũng không bảo đảm transaction DB nguyên tử với ACK.

### 3.2. MANUAL không có nghĩa tự động an toàn hơn

Khi chọn MANUAL, ứng dụng phải xử lý mọi đường đi:

1. Thành công, DB đã commit → **basicAck**.
2. Dữ liệu sai, không thể sửa bằng retry → **basicReject** hoặc **basicNack** với **requeue=false**.
3. Lỗi tạm thời → retry theo chính sách, rồi ACK nếu thành công; nếu hết retry, chọn một đích lưu lỗi bền vững.
4. Process crash, connection mất hoặc ACK thất bại → chấp nhận khả năng **redelivery** và chống trùng.
5. Shutdown/cancellation và các exception ngoài dự kiến → không để delivery treo vô hạn do thiếu nhánh xử lý.

Với MANUAL, không có một câu lệnh **finally { basicAck(...); }** an toàn cho mọi trường hợp: ACK trong finally có thể xác nhận cả một message đã xử lý thất bại.

### 3.3. NONE có phù hợp cho nghiệp vụ quan trọng không?

Khi hệ thống không đòi hỏi explicit ACK, broker không thể dựa vào ACK sau xử lý để quyết định giao lại delivery nếu process chết. Chỉ sử dụng với những workload có yêu cầu best-effort rõ ràng, không dựa vào nó để bảo đảm không bỏ sót đơn hàng, thanh toán hoặc nghiệp vụ audit bắt buộc.

## 4. Delivery tag và AMQP channel: nền tảng của manual ACK

Khi RabbitMQ giao delivery, nó gắn một **delivery tag**. Tag này được dùng trong các thao tác acknowledgment trên **channel nhận delivery**.

**Quy tắc quan trọng:**

- Delivery tag được định danh **theo AMQP channel**, không phải ID toàn cục của broker.
- Phải ACK/NACK trên **đúng channel** đã nhận delivery.
- Một delivery chỉ được settle hợp lệ một lần: ACK, NACK hoặc reject theo ngữ nghĩa giao thức.
- Không sử dụng delivery tag như **eventId nghiệp vụ**, correlation ID giữa hai service hoặc ID để truy vết qua connection restart.
- Khi channel mất kết nối, delivery tag của channel cũ không còn là khóa hợp lệ để xác nhận trên channel mới.

### 4.1. Các lệnh ở mức RabbitMQ Java client

~~~java
import com.rabbitmq.client.Channel;

// tag: delivery tag tren channel da nhan message
channel.basicAck(tag, false);          // Xac nhan mot delivery
channel.basicReject(tag, false);       // Tu choi, khong requeue
channel.basicNack(tag, false, true);   // Tu choi mot delivery, requeue
channel.basicNack(tag, false, false);  // Tu choi mot delivery, khong requeue
~~~

Đây là các lời gọi minh họa **từng quyết định riêng biệt**. Không chạy liên tiếp cả bốn lệnh cho cùng một delivery tag.

### 4.2. basicAck(deliveryTag, multiple)

**basicAck(tag, false)** xác nhận **một delivery cụ thể**. **basicAck(tag, true)** xác nhận **nhiều delivery chưa ACK có tag không lớn hơn tag được cung cấp trên cùng channel**, theo ngữ nghĩa AMQP.

**Không dùng multiple=true tùy tiện** trong hệ thống xử lý song song: delivery có tag thấp hơn có thể chưa hoàn tất nghiệp vụ. ACK hàng loạt nhầm có thể làm mất cơ hội redelivery của các message chưa xử lý.

Trong ví dụ học tập, luôn chọn **multiple=false** để tránh ACK nhầm message khác.

### 4.3. basicNack(deliveryTag, multiple, requeue)

- **multiple=false:** chỉ NACK delivery đang xét.
- **multiple=true:** NACK hàng loạt các delivery chưa xác nhận trong phạm vi tag/channel theo cơ chế AMQP.
- **requeue=true:** đề nghị broker đưa message trở lại trạng thái có thể giao lại.
- **requeue=false:** không đưa lại vào queue gốc; broker có thể dead-letter nếu queue được cấu hình DLX, hoặc message có thể bị loại bỏ theo chính sách.

**basicReject(tag, requeue)** có ngữ nghĩa từ chối **một delivery**; không có cờ multiple. Với trường hợp reject một bản tin, **basicNack(tag, false, false)** và **basicReject(tag, false)** thường được dùng cho mục đích tương tự, nhưng không nên tự coi mọi khác biệt protocol/implementation đều không tồn tại.

### 4.4. ACK chỉ có ý nghĩa nếu broker nhận được

Giả sử ứng dụng gọi **basicAck** sau khi DB commit, nhưng kết nối mất ngay trước khi broker nhận frame ACK. Ứng dụng không thể chỉ nhìn “đã gọi method” để tuyên bố broker chắc chắn sẽ không giao lại message.

Do đó, dù chủ động ACK, consumer vẫn cần **idempotency** nếu một side effect được yêu cầu thực hiện tối đa một lần theo eventId.

## 5. Redelivery, requeue và thứ tự xử lý

Một delivery có thể được broker giao lại khi:

- Consumer NACK/reject với **requeue=true**.
- Connection/channel đóng khi còn delivery chưa ACK.
- Process bị kill hoặc broker phát hiện consumer không còn kết nối.
- Một cơ chế retry/republish đưa lại event cùng nội dung vào queue.

### 5.1. Requeue không có nghĩa “đợi vài giây rồi thử”

**basicNack(tag, false, true)** yêu cầu đưa delivery trở lại queue theo semantics RabbitMQ. Nếu các consumer còn hoạt động, broker có thể giao lại **rất nhanh**, có thể cho **cùng consumer** hoặc consumer khác. Không được hiểu requeue=true tự tạo delayed retry hay exponential backoff.

~~~mermaid
flowchart TD
    Q["Queue"] --> C["Consumer"]
    C --> H{"Xử lý"}
    H -- "Lỗi tạm thời" --> N["basicNack(requeue=true)"]
    N --> Q
    H -- "Thành công" --> A["basicAck"]
~~~

Nếu payload luôn lỗi schema, vòng requeue này có thể chạy liên tục, tạo **poison message loop**, tăng CPU, network, log và làm chậm những message hợp lệ.

### 5.2. Cờ redelivered có giá trị gì?

RabbitMQ có thể đánh dấu delivery **redelivered** để consumer biết có khả năng message đã được giao trước đây. Đây là tín hiệu vận hành hữu ích nhưng:

- Không phải **business eventId**.
- Không chứng minh delivery trước đã commit hay chưa.
- Không phải cơ sở duy nhất để quyết định bỏ qua side effect.
- Một event được producer publish lại có thể là message mới với cờ redelivered không giống broker requeue.

Chống trùng phải dựa trên **eventId/idempotency key** ổn định do ứng dụng xác định, kết hợp kho trạng thái bền vững.

### 5.3. Thứ tự delivery khác thứ tự business completion

Ngay cả khi một queue thường lưu message theo thứ tự, việc xử lý có thể không đúng thứ tự publish vì:

- Có nhiều consumer cạnh tranh.
- Có prefetch lớn, callback/handler chạy đồng thời.
- NACK/requeue làm message được giao lại.
- Có retry queue, delayed retry, priority hoặc chuyển sang ExecutorChannel.

Nếu **OrderCreated** phải được áp dụng trước **OrderCancelled** cho cùng orderId, cần version/sequence của domain hoặc cơ chế xử lý thứ tự phù hợp. **Prefetch=1 không bảo đảm thứ tự nghiệp vụ toàn cục khi có nhiều consumer.**

## 6. Prefetch là giới hạn số delivery chưa ACK

RabbitMQ **basic.qos(prefetch)** giới hạn số delivery chưa ACK có thể đang được giao trước theo QoS. Trong cấu hình thông thường của RabbitMQ, prefetch được áp **theo consumer**, nhưng cần xét những cấu hình global QoS hoặc giới hạn khác nếu sử dụng.

Giả sử:

~~~text
concurrentConsumers = 3
prefetchCount     = 10
~~~

Khi ba consumer đang hoạt động, mức in-flight chưa ACK có thể xấp xỉ:

~~~text
3 consumer × 10 delivery/consumer = 30 delivery chưa ACK
~~~

Đây chỉ là **cửa sổ tối đa ước lượng**, không phải throughput, số thread nghiệp vụ, số message luôn sẵn có hay tổng số message trong queue.

| Giá trị/tham số | Tác động | Lưu ý với MANUAL |
| --- | --- | --- |
| **prefetchCount thấp** | Ít message bị giữ trước mỗi consumer | Tăng fairness, có thể giảm throughput khi chờ ACK/network |
| **prefetchCount cao** | Nhiều delivery unacked hơn có thể được gửi trước | Nếu quên ACK, nhanh lấp đầy quota; tăng memory và lượng redelivery sau crash |
| **concurrentConsumers** | Số consumer hoạt động song song của SMLC | Tổng in-flight có thể tăng theo N × P |
| **maxConcurrentConsumers** | Mức tối đa khi SMLC scale | Số consumer thực tế còn phụ thuộc trigger và tải |
| **consumersPerQueue** | Mức consumer mỗi queue của DMLC | Cách tính tổng khác khi một container theo dõi nhiều queue |

### 6.1. Quên ACK thì điều gì xảy ra?

Với MANUAL, nếu handler không ACK/NACK/reject, broker giữ delivery ở trạng thái **unacked**. Khi đạt giới hạn prefetch, consumer có thể không được giao thêm message dù queue còn nhiều message **ready**.

Một dấu hiệu điển hình:

~~~text
Queue ready   : tăng
Queue unacked : gần số consumer × prefetch
Consumer ACK  : rất thấp hoặc bằng 0
~~~

Cần kiểm tra code ACK, exception trước ACK, thread bị treo và connection/channel, không chỉ tăng prefetch để che giấu vấn đề.

### 6.2. Manual ACK không tự tăng năng lực xử lý

Nếu một handler mất **200 ms/message** và chỉ có một consumer xử lý tuần tự, throughput lý tưởng khoảng **5 message/giây**, bỏ qua overhead. Tăng prefetch từ 10 lên 100 **không làm DB transaction nhanh hơn 10 lần**; nó chỉ cho phép giữ trước nhiều delivery hơn.

Tăng concurrency có thể giúp nếu database và downstream đủ năng lực, nhưng cũng có thể gây lock contention hoặc làm sai thứ tự áp dụng event.

## 7. Phân loại lỗi trước khi thiết kế retry

Không có retry policy an toàn nếu không biết **lỗi nào có thể hồi phục**.

| Loại lỗi | Ví dụ | Chính sách thường phù hợp |
| --- | --- | --- |
| **Dữ liệu sai cố định** | JSON malformed, thiếu orderId, schemaVersion không hỗ trợ | Reject/cách ly; không requeue ngay vô hạn |
| **Business rule từ chối** | Đơn hàng không đủ điều kiện theo hợp đồng | Trả kết quả nghiệp vụ hoặc ghi trạng thái từ chối; tránh lặp side effect |
| **Hạ tầng tạm thời** | DB connection timeout, API 503, khóa tạm thời | Retry hữu hạn với backoff/jitter |
| **Hạ tầng/cấu hình cố định** | Thiếu quyền DB, credentials sai, resource không tồn tại | Alert và sửa cấu hình, không retry nóng |
| **Kết quả transaction không rõ** | Network mất gần lúc commit | Đối soát bằng business key; retry idempotent |
| **Message đã xử lý** | eventId đã có trong inbox | Không lặp tác động; ACK sau khi kiểm tra an toàn |
| **Lỗi gọi ACK** | Channel bị đóng/IOException | Có thể redeliver; không tự phát ACK/NACK khác trên channel mới |

### 7.1. Retry trong listener hay retry qua broker?

**Retry trong listener (in-process):**

- Giữ delivery unacked trong lúc thử lại.
- Có thể dùng Spring Retry để giới hạn attempts/backoff.
- Thích hợp với lỗi tạm thời ngắn và khả năng giữ worker bận trong giới hạn.
- Không bền vững nếu tiến trình chết giữa các attempt; broker có thể redeliver sau khi connection đóng.

**Retry qua broker hoặc nguồn lưu bền:**

- Sau khi thất bại, chuyển bản tin sang một queue retry có delay/TTL hoặc một outbox/inbox bền vững.
- Worker có thể tiếp tục xử lý sau restart.
- Cần topology, giới hạn số lượt, correlation/eventId và chính sách khi gửi lại thất bại.
- Nếu **republish** sang queue retry, phải có quy tắc tránh **ACK bản gốc trước khi bản retry đã được tiếp nhận bền vững**.

Không có phương án duy nhất phù hợp mọi loại lỗi. Hãy chọn theo SLA, thông lượng, thời gian lỗi dự kiến và khả năng chịu được message trùng.

### 7.2. Retry “mãi cho tới khi thành công” là nguy hiểm

Một poison message có thể chiếm consumer lâu, làm tăng queue ready, gây log storm, đẩy tải vào downstream và che khuất message hợp lệ. Đặt:

- Số attempts tối đa.
- Backoff phù hợp, thêm jitter khi nhiều instance.
- Giới hạn thời gian tổng thể.
- Điểm chuyển sang DLQ hoặc trạng thái lỗi cần điều tra.
- Cơ chế replay có kiểm soát, không tự động phát lại vô hạn.

## 8. Dead-letter exchange và queue khác NACK requeue

Khi consumer **basicReject(tag, false)** hoặc **basicNack(tag, false, false)**, RabbitMQ có thể **dead-letter** message nếu queue được cấu hình dead-letter exchange. Nếu không có cấu hình/binding phù hợp, không nên kỳ vọng message sẽ tự có trong DLQ.

~~~mermaid
flowchart LR
    X["orders.events exchange"] --> Q["orders.created.q"]
    Q --> C["Consumer MANUAL ACK"]
    C -->|"ACK"| DONE["Hoàn tất delivery"]
    C -->|"NACK, requeue=true"| Q
    C -->|"Reject/NACK, requeue=false"| DLX["orders.dead.exchange"]
    DLX --> DLQ["orders.created.dlq"]
~~~

**DLX là cơ chế xử lý message đã nằm trong queue**, có thể phát sinh từ reject/NACK không requeue, TTL, max length hoặc delivery limit tùy loại queue/chính sách. **Publisher return** xảy ra khi publish không route được ở exchange; nó không tự đưa dữ liệu vào consumer DLQ.

### 8.1. Requeue=true không vào DLQ ngay

Một lệnh **basicNack(tag, false, true)** thông thường đặt delivery trở lại để xử lý, không tương đương “chuyển sang DLQ”. Nếu muốn cách ly sau khi hết attempts, phải chọn **requeue=false** hoặc một cơ chế retry/delivery-limit có điểm kết thúc và topology đúng.

### 8.2. DLQ cũng cần người sở hữu và quy trình xử lý

DLQ không phải “thùng rác an toàn vô hạn”. Cần xác định:

1. Ai xem cảnh báo và xử lý các bản tin trong DLQ?
2. Có quyền truy cập payload nhạy cảm không?
3. DLQ có retention, TTL, giới hạn kích thước hoặc policy gì?
4. Sửa và replay có giữ nguyên eventId, schemaVersion, ordering không?
5. Replay có nguy cơ tạo side effect trùng không?
6. Có thể xác định message vào DLQ vì dữ liệu lỗi, hết retry hay queue policy không?

### 8.3. Retry bằng DLX/TTL có thể tạo vòng lặp

Một thiết kế tùy chọn là chuyển từ main queue sang retry queue có TTL rồi quay lại main queue qua DLX. Nếu không có **giới hạn số lần thử** và dead-letter routing hợp lý, hệ thống có thể quay vòng mãi. Một số cấu hình quorum queue hỗ trợ delivery limit, nhưng không nên mặc định loại queue nào cũng có cùng behavior.

**Các header như x-death mô tả lịch sử dead-letter** ở broker; chúng không thay thế một attempt counter nghiệp vụ bền vững nếu hệ thống republish và thay đổi headers. Không tin blindly vào trường từ nguồn ngoài để quyết định đã retry bao nhiêu lần.

## 9. Ví dụ Spring Integration: topology có DLX/DLQ

Ta xây dựng một bài thực hành cụ thể:

~~~text
Exchange chính  : orders.events
Routing key     : orders.created
Queue chính     : orders.created.q          (durable)
Dead exchange   : orders.dead.exchange
Dead routing key: orders.failed
Dead queue      : orders.created.dlq        (durable)
Payload ví dụ   : evt-1001|O-1001|150000

Consumer:
  SimpleMessageListenerContainer
  acknowledgeMode = MANUAL
  concurrentConsumers = 2
  maxConcurrentConsumers = 4
  prefetchCount = 8
  -> AMQP inbound channel adapter
  -> DirectChannel
  -> retry (3 lần trong listener)
  -> business service
  -> ACK hoặc reject không requeue
~~~

### 9.1. Dependencies

Với Spring Boot có dependency management quản lý phiên bản tương thích:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.retry</groupId>
        <artifactId>spring-retry</artifactId>
    </dependency>
</dependencies>
~~~

**spring-retry** cần cho RetryTemplate ở ví dụ bên dưới. Nếu muốn chạy ví dụ xử lý database bằng JdbcTemplate, ứng dụng còn cần starter JDBC, JDBC driver và bảng được tạo trước; mã hướng dẫn không tự tạo schema DB.

Ứng dụng phải có RabbitMQ broker test, ConnectionFactory cấu hình host/port/vhost, credentials/TLS theo môi trường. Không đặt password thật trong mã nguồn.

### 9.2. Khai báo exchange, queue, binding

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersManualAckTopology {

    public static final String EVENTS_EXCHANGE = "orders.events";
    public static final String ROUTING_KEY = "orders.created";
    public static final String QUEUE = "orders.created.q";

    public static final String DEAD_EXCHANGE = "orders.dead.exchange";
    public static final String DEAD_KEY = "orders.failed";
    public static final String DLQ = "orders.created.dlq";

    @Bean
    public DirectExchange ordersEventsExchange() {
        return new DirectExchange(EVENTS_EXCHANGE, true, false);
    }

    @Bean
    public Queue ordersCreatedQueue() {
        return QueueBuilder.durable(QUEUE)
            .deadLetterExchange(DEAD_EXCHANGE)
            .deadLetterRoutingKey(DEAD_KEY)
            .build();
    }

    @Bean
    public Binding ordersCreatedBinding(
            Queue ordersCreatedQueue,
            DirectExchange ordersEventsExchange) {
        return BindingBuilder.bind(ordersCreatedQueue)
            .to(ordersEventsExchange)
            .with(ROUTING_KEY);
    }

    @Bean
    public DirectExchange ordersDeadExchange() {
        return new DirectExchange(DEAD_EXCHANGE, true, false);
    }

    @Bean
    public Queue ordersCreatedDeadQueue() {
        return QueueBuilder.durable(DLQ).build();
    }

    @Bean
    public Binding ordersCreatedDeadBinding(
            Queue ordersCreatedDeadQueue,
            DirectExchange ordersDeadExchange) {
        return BindingBuilder.bind(ordersCreatedDeadQueue)
            .to(ordersDeadExchange)
            .with(DEAD_KEY);
    }
}
~~~

**Lưu ý triển khai:** Các bean chỉ mô tả topology. RabbitAdmin/AmqpAdmin cần được bật và có quyền khai báo, hoặc topology phải được provision ngoài ứng dụng. Nếu queue cùng tên đã tồn tại nhưng thiếu DLX arguments hoặc có thuộc tính không tương thích, RabbitMQ có thể từ chối redeclare. Với production, nên lên kế hoạch migration hoặc dùng policy broker phù hợp thay vì tùy tiện đổi arguments của queue đang chạy.

### 9.3. Tại sao DLQ cần có binding riêng?

**basicReject(tag, false)** chỉ yêu cầu không requeue. RabbitMQ đưa message vào dead-letter exchange theo cấu hình của **queue nguồn**. Dead-letter exchange lại cần binding để route tới **orders.created.dlq**.

Không có exchange, queue hoặc binding tương ứng thì **không thể đảm bảo message lỗi được lưu**. Đây là việc cần kiểm thử độc lập với việc code Java gọi reject thành công.

## 10. Listener container MANUAL + prefetch

Đối với **AMQP inbound channel adapter** dạng message-driven, Spring AMQP listener container quản lý consumer, concurrency và acknowledgment. Ví dụ dùng **SimpleMessageListenerContainer (SMLC)**:

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersManualListenerConfiguration {

    @Bean("ordersManualContainer")
    public SimpleMessageListenerContainer ordersManualContainer(
            ConnectionFactory connectionFactory) {

        SimpleMessageListenerContainer container =
            new SimpleMessageListenerContainer(connectionFactory);

        container.setQueueNames(OrdersManualAckTopology.QUEUE);
        container.setConcurrentConsumers(2);
        container.setMaxConcurrentConsumers(4);
        container.setPrefetchCount(8);
        container.setAcknowledgeMode(AcknowledgeMode.MANUAL);

        // Fallback cho loi listener chua duoc settle.
        // Khong thay the quyet dinh ACK/NACK cua application.
        container.setDefaultRequeueRejected(false);

        return container;
    }
}
~~~

**Tại sao setDefaultRequeueRejected(false)?** Đây là chính sách dự phòng của container với những lỗi được container xử lý theo đường reject; trong MANUAL, handler vẫn phải chủ động ACK/NACK những delivery nó sở hữu. **Không được giả định setter này bảo đảm mọi exception đều được đưa vào DLQ**: cần xem error handler, loại exception, có tồn tại channel/tag hay không và trạng thái connection.

**Số in-flight minh họa:** 2 consumer × prefetch 8 ≈ **16 delivery unacked** có thể được giao trước. Nếu SMLC scale tới 4 consumer, giới hạn ước lượng tăng tới **32**. Điều đó không có nghĩa có đúng 32 worker nghiệp vụ hoặc DB transaction song song.

### 10.1. SMLC và DMLC là hai lựa chọn khác nhau

**SimpleMessageListenerContainer** thường điều chỉnh concurrency bằng **concurrentConsumers/maxConcurrentConsumers**. **DirectMessageListenerContainer** dùng thiết lập **consumersPerQueue** và mô hình dispatch/thread khác. Cả hai đều có thể dùng manual acknowledge và prefetch nhưng cần áp dụng đúng cấu hình của container được chọn.

Không nhầm **DirectMessageListenerContainer** với Spring Integration **DirectChannel**: một bên là container AMQP, một bên là kênh nội bộ đồng bộ.

### 10.2. Message-driven không cần Spring Integration poller

RabbitMQ phân phối delivery tới consumer được listener container đăng ký. **AMQP inbound adapter** nhận theo cơ chế message-driven; không thêm **Pollers.fixedDelay** như File/SFTP inbound adapter chỉ vì muốn kiểm soát tốc độ. Đối với AMQP, thường điều chỉnh **prefetch, concurrency, ACK, handler latency và backpressure**.

## 11. RetryTemplate: chỉ retry lỗi có thể hồi phục

Để tránh NACK requeue liên tục khi database tạm lỗi, ta thiết kế **retry bên trong listener** tối đa ba attempts, exponential backoff ngắn và chỉ retry lớp **TransientOrderProcessingException**.

~~~java
public class InvalidOrderEventException extends RuntimeException {
    public InvalidOrderEventException(String message) {
        super(message);
    }

    public InvalidOrderEventException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

~~~java
public class TransientOrderProcessingException
        extends RuntimeException {

    public TransientOrderProcessingException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

### 11.1. Bean cấu hình retry hữu hạn

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.retry.support.RetryTemplateBuilder;

@Configuration
public class OrdersRetryConfiguration {

    @Bean
    public RetryTemplate ordersRetryTemplate() {
        return new RetryTemplateBuilder()
            .maxAttempts(3)
            .exponentialBackoff(200L, 2.0, 1500L)
            .retryOn(TransientOrderProcessingException.class)
            .build();
    }
}
~~~

**maxAttempts(3)** có nghĩa thường gồm **lần xử lý đầu tiên và tối đa hai lần thử lại**, không phải ba lần retry cộng thêm lần đầu. Với backoff minh họa, các lần retry không chạy trong vòng lặp tức thời; tuy nhiên worker/listener vẫn giữ delivery unacked khi chờ.

**Lưu ý cấu hình:** Spring Retry APIs thay đổi theo phiên bản; mã minh họa sử dụng RetryTemplateBuilder trong các phiên bản hỗ trợ builder này. Với lỗi database, lớp service cần phân loại ngoại lệ tương ứng thành TransientOrderProcessingException; **không retry tất cả RuntimeException**.

### 11.2. Mốc retry ở đâu?

~~~mermaid
flowchart TD
    D["Delivery từ broker"] --> P["Parse và validate"]
    P -->|"Invalid"| BAD["Reject requeue=false"]
    P -->|"Hợp lệ"| T["RetryTemplate"]
    T --> S["BusinessService<br/>DB transaction"]
    S -->|"Thành công"| A["basicAck"]
    S -->|"Transient failure"| R{"Còn lượt retry?"}
    R -->|"Có"| WAIT["Backoff"] --> T
    R -->|"Không"| DLQ["basicNack requeue=false"]
    S -->|"Non-retryable failure"| DLQ
~~~

Trong ví dụ **cả ba attempt xảy ra trên cùng một delivery đang unacked**. Nếu tiến trình chết sau hai lần thử, bộ đếm in-memory của RetryTemplate không còn; RabbitMQ có thể redeliver và một lượt xử lý mới lại có tối đa ba attempt. Vì thế **maxAttempts(3) không phải giới hạn bền vững tổng số lần xử lý của một event qua mọi lần redelivery**.

### 11.3. Có nên gọi basicNack(requeue=true) ngay sau ba lỗi?

Nếu không có delayed retry, việc NACK requeue=true có thể làm message được giao lại ngay và bắt đầu ba attempts khác, tạo vòng lặp vô hạn ở cấp broker. Vì vậy mẫu cơ bản trong bài **NACK requeue=false sau khi hết attempts** để đưa message về DLQ có giám sát.

Trong workflow cho phép lỗi tạm thời kéo dài, có thể bổ sung **retry queue có delay**, job scheduler hoặc inbox bền vững; nhưng phải thiết kế giới hạn tổng số lượt và xử lý giao nhận giữa các queue.

## 12. Service nghiệp vụ và ranh giới transaction

Ta tách phần xử lý nghiệp vụ khỏi lệnh ACK để rõ trách nhiệm:

- **OrderBusinessService** parse, validate và thực hiện transaction nghiệp vụ.
- **OrderManualAckHandler** chọn ACK/NACK/reject **sau khi phương thức nghiệp vụ trả về**.
- Listener container và inbound adapter chỉ chịu trách nhiệm tiếp nhận delivery/chuyển message.

### 12.1. Model và parser minh họa

~~~java
public record OrderCreatedEvent(
        String eventId,
        String orderId,
        long totalVnd) {
}
~~~

~~~java
public final class OrderEventParser {

    private OrderEventParser() {}

    public static OrderCreatedEvent parse(String body) {
        if (body == null || body.length() > 1024) {
            throw new InvalidOrderEventException(
                "Payload missing or too large");
        }

        String[] fields = body.split("\\|", -1);
        if (fields.length != 3
                || !fields[0].matches("[A-Za-z0-9_-]{1,80}")
                || !fields[1].matches("[A-Za-z0-9_-]{1,80}")) {
            throw new InvalidOrderEventException(
                "Expected eventId|orderId|totalVnd");
        }

        long total;
        try {
            total = Long.parseLong(fields[2]);
        } catch (NumberFormatException ex) {
            throw new InvalidOrderEventException(
                "totalVnd is not a valid integer", ex);
        }

        if (total <= 0) {
            throw new InvalidOrderEventException(
                "totalVnd must be positive");
        }
        return new OrderCreatedEvent(
            fields[0], fields[1], total);
    }
}
~~~

Parser này chỉ phục vụ bài học. Production nên dùng JSON/Avro/Protobuf có **schemaVersion** và validation, tránh format phân tách chuỗi khi payload không được giới hạn ký tự.

### 12.2. BusinessService với boundary transaction độc lập

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderBusinessService {

    private final WarehouseProjectionRepository repository;

    public OrderBusinessService(
            WarehouseProjectionRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void process(String body) {
        OrderCreatedEvent event = OrderEventParser.parse(body);

        // insertInboxIfAbsent PHAI duoc bao ve boi UNIQUE
        // tren (consumerName, eventId) trong cung DB transaction.
        boolean firstTime = repository.insertInboxIfAbsent(
            "warehouse", event.eventId());

        if (!firstTime) {
            return; // Event da duoc xu ly truoc day.
        }

        repository.upsertOrderProjection(
            event.orderId(), event.totalVnd());
    }
}
~~~

~~~java
public interface WarehouseProjectionRepository {

    // Atomic insert; returns false on duplicate unique key.
    boolean insertInboxIfAbsent(
        String consumerName, String eventId);

    // Updates projection in the SAME database transaction.
    void upsertOrderProjection(
        String orderId, long totalVnd);
}
~~~

**Các interface trong ví dụ là hợp đồng cần triển khai**, không phải repository đã được Spring Data/JDBC tự sinh chỉ vì có tên. Để áp dụng thực tế, cần triển khai insert atomic (ví dụ unique constraint/INSERT ... ON CONFLICT theo database), transaction manager, database schema và migration.

**Điểm then chốt:** Nếu việc ghi inbox và cập nhật dữ liệu cùng một database transaction, rollback khi lỗi sẽ hoàn tác cả hai. Không dùng chuỗi **exists(eventId) → insert** thiếu unique constraint vì hai consumer có thể race rồi cùng tạo side effect.

### 12.3. Phạm vi của @Transactional

Phương thức **OrderBusinessService.process()** được gọi qua Spring bean/proxy từ bean handler khác, để transaction advice có hiệu lực theo cấu hình. **Transaction database không bao phủ RabbitMQ basicAck một cách tự động.**

Hai khoảng rủi ro cần chấp nhận:

1. DB commit thành công, ACK thất bại → broker có thể redeliver; inbox giúp xử lý lại an toàn.
2. DB chưa commit, ứng dụng ACK trước → delivery có thể không được giao lại dù business chưa hoàn tất. Vì thế **ACK phải sau khi method transactional hoàn tất thành công**.

Nếu method bên trong thực hiện một HTTP call hoặc gọi tài nguyên khác không nằm trong cùng transaction, cần thiết kế bù trừ/idempotency của tài nguyên đó; annotation @Transactional không biến các hệ thống ngoài thành một transaction phân tán.

### 12.4. Chuyển exception tạm thời sang loại được retry

RetryTemplate của bài chỉ retry **TransientOrderProcessingException**. Nếu repository phát trực tiếp một loại lỗi khác, cần phân loại có chủ đích. Chẳng hạn, trong method **process** có thể bọc thao tác DB:

~~~java
import org.springframework.dao.TransientDataAccessException;

// Minh hoa doan trong OrderBusinessService.process(...):
try {
    repository.upsertOrderProjection(
        event.orderId(), event.totalVnd());
} catch (TransientDataAccessException ex) {
    throw new TransientOrderProcessingException(
        "Temporary database failure", ex);
}
~~~

Đây là **đoạn thay thế** thao tác repository tương ứng trong mục 12.2, không phải gọi **upsertOrderProjection** thêm lần thứ hai. Transaction sẽ rollback khi exception runtime thoát ra. Hãy kiểm tra cơ chế phân loại exception của driver/framework đang dùng và transaction commit failures; không mặc định mọi lỗi DB đều thuộc nhóm có thể retry.

## 13. Manual ACK handler: xử lý xong rồi mới xác nhận

Spring Integration AMQP inbound adapter có thể cung cấp metadata AMQP của delivery qua headers, trong đó thường có **AmqpHeaders.CHANNEL** và **AmqpHeaders.DELIVERY_TAG** khi dùng chế độ manual acknowledgment và cấu hình endpoint hỗ trợ.

**Quan trọng về phiên bản:** Tên/khả năng expose header phụ thuộc cách tạo endpoint và phiên bản Spring AMQP/Spring Integration. Trước khi dựa vào mẫu này, phải xác nhận **channel và delivery tag thực sự hiện diện** trong Spring Message được tạo bởi inbound adapter đang chạy; nếu thiếu, không được tự tạo tag mới hoặc ACK bằng connection/channel khác.

### 13.1. Service đảm nhiệm settlement

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.Map;

import com.rabbitmq.client.Channel;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderManualAckHandler {

    private final RetryTemplate ordersRetryTemplate;
    private final OrderBusinessService businessService;

    public OrderManualAckHandler(
            RetryTemplate ordersRetryTemplate,
            OrderBusinessService businessService) {
        this.ordersRetryTemplate = ordersRetryTemplate;
        this.businessService = businessService;
    }

    public void handle(
            String payload, Map<String, Object> headers) {

        Object rawChannel = headers.get(AmqpHeaders.CHANNEL);
        Object rawTag = headers.get(AmqpHeaders.DELIVERY_TAG);

        if (!(rawChannel instanceof Channel)
                || !(rawTag instanceof Number)) {
            throw new IllegalStateException(
                "MANUAL ACK requires channel and delivery tag headers");
        }

        Channel channel = (Channel) rawChannel;
        long deliveryTag = ((Number) rawTag).longValue();

        try {
            ordersRetryTemplate.execute(context -> {
                businessService.process(payload);
                return null;
            });
        } catch (InvalidOrderEventException ex) {
            // Permanent payload error: do not requeue.
            reject(channel, deliveryTag);
            return;
        } catch (RuntimeException ex) {
            // Retries exhausted, or a non-retryable technical error.
            // Route to DLQ according to the queue topology.
            nackWithoutRequeue(channel, deliveryTag);
            return;
        }

        // Called only AFTER businessService.process returned,
        // including completion of its database transaction.
        ack(channel, deliveryTag);
    }

    private void ack(Channel channel, long deliveryTag) {
        try {
            channel.basicAck(deliveryTag, false);
        } catch (IOException ex) {
            // Do not issue a second ACK/NACK on an unknown channel state.
            throw new UncheckedIOException("ACK failed", ex);
        }
    }

    private void reject(Channel channel, long deliveryTag) {
        try {
            channel.basicReject(deliveryTag, false);
        } catch (IOException ex) {
            throw new UncheckedIOException("Reject failed", ex);
        }
    }

    private void nackWithoutRequeue(
            Channel channel, long deliveryTag) {
        try {
            channel.basicNack(deliveryTag, false, false);
        } catch (IOException ex) {
            throw new UncheckedIOException("NACK failed", ex);
        }
    }
}
~~~

**Phân tích các nhánh:**

1. **businessService.process thành công:** transaction method hoàn tất, sau đó **basicAck(tag, false)**.
2. **InvalidOrderEventException:** dữ liệu không hợp lệ, **basicReject(tag, false)**; nếu DLX/DLQ đủ điều kiện, message được dead-letter.
3. **TransientOrderProcessingException:** RetryTemplate thử lại tối đa ba attempts; nếu cuối cùng vẫn thất bại thì **basicNack(tag, false, false)** để cách ly.
4. **RuntimeException khác:** không retry bằng policy mẫu; NACK không requeue để tránh hot loop. Trong hệ thống thật nên mở rộng bộ phân loại lỗi thay vì mặc định mọi lỗi ngoài dự kiến đều đi DLQ.
5. **IOException khi ACK/NACK/reject:** handler ném lỗi lên container và **không gửi thêm một settlement khác** cho cùng tag. Kết quả broker có thể không rõ; phải chấp nhận khả năng redelivery và có idempotency.

**Không đặt các lệnh ACK/NACK trong cùng một try/catch với toàn bộ công việc xử lý rồi catch chung để NACK.** Nếu basicAck đã được gửi nhưng lỗi phát sinh sau đó, việc NACK lại cùng delivery tag có thể gây lỗi protocol hoặc channel bị đóng vì double acknowledgment.

### 13.2. Ví dụ này cần xử lý ra sao khi thiếu headers?

Việc thiếu **AmqpHeaders.CHANNEL** hoặc **DELIVERY_TAG** là lỗi **cấu hình integration boundary**, không phải một lỗi nghiệp vụ có thể sửa bằng retry. Mẫu trên fail fast trước khi xử lý business. Cần:

- Kiểm tra AcknowledgeMode.MANUAL thực sự được áp vào container đang chạy.
- Kiểm tra phiên bản adapter/header mapper, những headers bị lọc hoặc transformer làm mất metadata.
- Kiểm tra error handler của listener khi lỗi xảy ra **trước khi có thể settle**.
- Dừng triển khai nếu không có đường ACK/NACK hợp lệ; không cho hệ thống xử lý và commit DB trong trạng thái không thể xác nhận delivery.

Không nên thêm một channel mới và một delivery tag giả định chỉ để qua bước kiểm tra.

### 13.3. Không gửi Channel/Tag ra hệ thống ngoài

**AMQP Channel** là tài nguyên client liên quan connection/thread/lifecycle của delivery. Đừng:

- Serialize Channel vào JSON.
- Lưu Channel hoặc delivery tag vào database để ACK sau khi restart.
- Đưa chúng sang Kafka/HTTP/SFTP dưới dạng header nghiệp vụ.
- Giữ Channel trong một singleton field để ACK nhiều delivery khác nhau.

Nếu cần trao đổi trạng thái sau một bước xử lý bất đồng bộ kéo dài, dùng **eventId/jobId và nguồn trạng thái bền vững**, không dùng channel/tag như tham chiếu nghiệp vụ lâu dài.

## 14. Tích hợp handler vào AMQP inbound IntegrationFlow

Ta nối container **ordersManualContainer** ở mục 10 với Spring Integration: inbound adapter → DirectChannel → handler manual ACK.

### 14.1. Spring Integration Java DSL

~~~java
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrdersManualAckIntegrationConfiguration {

    @Bean
    public MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow ordersInboundFlow(
            @Qualifier("ordersManualContainer")
            SimpleMessageListenerContainer container,
            OrderManualAckHandler manualAckHandler) {

        return IntegrationFlow
            .from(Amqp.inboundAdapter(container))
            .channel("ordersInput")
            .handle(String.class, (payload, headers) -> {
                manualAckHandler.handle(payload, headers);
                return null;
            })
            .get();
    }
}
~~~

**Những class cấu hình trên là các file Java riêng**; đây là ví dụ cấu trúc tổng thể, không phải yêu cầu chép toàn bộ code vào một file. Có thể triển khai producer và consumer trong hai ứng dụng khác nhau; ví dụ đặt ở cùng ứng dụng để người học quan sát.

### 14.2. Vì sao dùng DirectChannel?

Với **DirectChannel**, service activator thường chạy trong chuỗi gọi đồng bộ của listener:

~~~mermaid
sequenceDiagram
    participant Q as RabbitMQ queue
    participant L as SMLC MANUAL
    participant A as AMQP inbound adapter
    participant C as DirectChannel
    participant H as OrderManualAckHandler
    participant DB as Warehouse DB
    Q->>L: Delivery + tag + channel
    L->>A: Listener callback
    A->>C: Spring Message
    C->>H: handle(payload, headers)
    H->>DB: Business transaction
    DB-->>H: Commit success
    H-->>Q: basicAck(tag, false)
    H-->>C: Handler returns
    C-->>A: Flow completes
~~~

Flow không tự ACK ngay tại MessageChannel.send(); handler chủ động ACK sau khi transaction service hoàn tất. Tuy nhiên, nếu processor gọi hệ thống ngoài bất đồng bộ bên trong và trả về trước khi bên ngoài xong, **ACK vẫn có thể sớm so với nghiệp vụ thực tế**. Ranh giới thành công phải được định nghĩa theo đúng hợp đồng.

### 14.3. Nếu adapter phát payload khác String?

Ví dụ giả định AMQP converter của inbound adapter chuyển message **text/plain** thành **String**. Nếu producer gửi JSON/binary, inbound converter có thể phát **byte[]** hoặc DTO. Khi đó handler yêu cầu String không còn đúng hợp đồng.

Hãy kiểm thử **body/properties**, contentType, charset, converter và khả năng giữ **AmqpHeaders.CHANNEL/DELIVERY_TAG** qua các bước transformer trước handler. Không được sửa schema hoặc header mapper tùy tiện trong lúc hệ thống đang xử lý message quan trọng.

### 14.4. Khi nào dùng @RabbitListener thay vì inbound adapter?

Nếu ứng dụng chỉ cần một consumer RabbitMQ nhỏ, không có nhu cầu MessageChannel/IntegrationFlow, **@RabbitListener** của Spring AMQP cũng có thể thực hiện MANUAL ACK với Channel và deliveryTag. Nhưng khi cần nối với router/filter/transformer/service activator hay những hệ thống khác, **AMQP inbound channel adapter** giúp đưa dữ liệu vào cùng kiến trúc Spring Integration.

Không đăng ký **cả @RabbitListener và inbound adapter** làm consumer cùng queue trong bài test nếu bạn muốn mỗi test message chỉ được luồng đang kiểm tra nhận; hai consumer đó sẽ cạnh tranh delivery.

## 15. ErrorChannel, converter và listener error handler

Lỗi trong Spring Integration và lỗi của Spring AMQP listener container nằm ở những lớp khác nhau:

| Ranh giới lỗi | Ví dụ | Thành phần thường xử lý |
| --- | --- | --- |
| **AMQP delivery / MessageConverter** | JSON malformed, contentType sai, object type không được phép | Spring AMQP converter + listener error handler |
| **Spring Integration transformer/filter** | SchemaVersion sai, header thiếu | IntegrationFlow/errorChannel nếu được cấu hình |
| **Service activator** | DB timeout, business validation | Business service, RetryTemplate/advice, error flow |
| **Manual settlement** | Channel đã đóng, basicAck IOException | RabbitMQ channel/connection và listener container |
| **Dead-letter routing** | DLQ hoặc binding không tồn tại | RabbitMQ topology, broker logs/management |

### 15.1. Lỗi xảy ra trước OrderManualAckHandler

Nếu **MessageConverter** không thể tạo Spring Message từ AMQP body, mã trong **OrderManualAckHandler** có thể chưa bao giờ chạy; vì thế handler không thể dùng channel/tag để reject delivery. Cần cấu hình và kiểm thử **Spring AMQP listener error handler** cùng exception classification cho lỗi conversion.

Những phiên bản Spring AMQP có cơ chế nhận biết một số lỗi conversion là **fatal**, có thể reject không requeue theo error handler mặc định. Nhưng không nên khẳng định mọi cấu hình MANUAL hoặc mọi exception đều tự động đi tới DLQ; điều đó còn phụ thuộc **acknowledge mode, error handler, listener container, queue topology và loại exception**.

### 15.2. Lỗi bị errorChannel hấp thụ

Nếu IntegrationFlow định tuyến exception tới **ErrorMessage** trên errorChannel, rồi luồng xử lý lỗi kết thúc bình thường, container có thể không thấy một exception giống khi handler ném trực tiếp.

- Với **AUTO**, listener có thể bị coi là hoàn tất và container ACK theo policy.
- Với **MANUAL**, nếu code chịu trách nhiệm ACK/NACK không chạy hoặc error flow không settle delivery, nó có thể **treo unacked**.
- Nếu error flow tự ACK rồi một đoạn code khác cũng ACK, có thể gây **double ACK**.

Vì vậy, khi sử dụng manual ack, phải có **một chủ sở hữu settlement cuối cùng** cho mỗi delivery và kiểm thử từng nhánh lỗi. Không chỉ log exception rồi return nếu chưa biết ACK/NACK đã xảy ra chưa.

### 15.3. Không chuyển lỗi runtime bất kỳ thành requeue=true

Các exception chuyên biệt của Spring AMQP có thể ảnh hưởng chính sách requeue/reject trong một số cấu hình. Tuy nhiên **MANUAL ACK** là mô hình ứng dụng tự quyết định settlement; không nên suy ra rằng ném một exception từ Spring Integration handler luôn khiến broker thực hiện basicNack theo mong muốn.

Muốn retry theo classifier, hãy kiểm tra đường đi:

~~~text
AMQP delivery
  -> converter
  -> Spring Message
  -> transformer
  -> service activator
  -> RetryTemplate
  -> MANUAL ACK/NACK
~~~

Nếu lỗi nằm **trước** hoặc **sau** đoạn handler có quyền settle, cần đường xử lý riêng tại container hoặc topology.

## 16. Xử lý bất đồng bộ và vấn đề ACK sớm

Trong Spring Integration, đổi từ DirectChannel sang **ExecutorChannel** hoặc **QueueChannel** có thể thay đổi thời điểm listener callback kết thúc.

### 16.1. Nguy cơ với AUTO ACK

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ
    participant L as Listener AUTO
    participant E as ExecutorChannel
    participant H as Async worker
    L->>E: Send Spring Message
    E-->>L: Executor nhận task
    L-->>B: ACK theo callback hoàn tất
    E->>H: Thực hiện nghiệp vụ sau đó
    H--xH: Database error
    Note over B,H: Broker có thể đã ACK trước khi business thất bại
~~~

Với channel bất đồng bộ, caller có thể chỉ biết executor đã nhận việc. Nếu ACK được thực hiện trước khi side effect hoàn tất, RabbitMQ không còn cơ sở để redeliver delivery đó do lỗi phía sau.

### 16.2. MANUAL ACK có thể giải quyết, nhưng phải kiểm soát Channel

Manual ACK **có khả năng** trì hoãn xác nhận tới khi công việc async xong, nhưng không đơn giản là chuyển **com.rabbitmq.client.Channel** và delivery tag sang một thread bất kỳ:

- Channel có vòng đời gắn với connection/consumer; connection có thể đóng trong khi task đang chạy.
- Một số consumer/channel không được dùng tùy tiện đồng thời bởi nhiều thread.
- ACK **multiple=true** có thể xác nhận nhầm các delivery đang chờ.
- Có thể ACK lệch thứ tự; một số phiên bản container có tính năng hỗ trợ asynchronous acknowledgment riêng, phải cấu hình/kiểm thử theo tài liệu phiên bản.
- Nếu executor queue đầy, task bị reject hoặc shutdown, message vẫn cần một chính sách settlement/phục hồi.

Một phương án an toàn hơn trong nhiều trường hợp là **giữ handler đồng bộ đến lúc DB commit** rồi ACK, đồng thời tăng số consumer trong giới hạn downstream. Nếu nghiệp vụ bắt buộc xử lý bất đồng bộ, hãy cân nhắc **lưu bền vào inbox/job table trước ACK**, sau đó worker đọc job và xử lý tiếp với idempotency.

### 16.3. Lưu bền trước ACK: mô hình inbox

~~~mermaid
flowchart LR
    MQ["RabbitMQ delivery"] --> IA["AMQP inbound adapter"]
    IA --> DB["DB transaction:<br/>insert inbox eventId + body"]
    DB --> ACK["basicAck sau commit"]
    DB --> W["Async inbox worker"]
    W --> H["Business processing"]
    H --> DONE["Cập nhật trạng thái job"]
~~~

Trong mô hình này, ACK có nghĩa **sự kiện đã được lưu bền vào inbox**, không phải business processing đã hoàn tất. SLA phải mô tả rõ ý nghĩa đó. Worker bên trong ứng dụng cần retry, kiểm soát concurrency, trạng thái lỗi và bảo vệ idempotency. **QueueChannel trong bộ nhớ không thay thế inbox bền vững.**

### 16.4. Không dùng “async” để che lỗi upstream

Nếu một HTTP inbound gateway gửi việc vào ExecutorChannel rồi trả HTTP 200 ngay, nhưng AMQP inbound/consumer downstream hoặc DB worker chưa xử lý, response HTTP không nên mô tả công việc đã hoàn tất. Có thể chọn **202 Accepted + jobId** và API tra cứu trạng thái, nếu hợp đồng cho phép.

## 17. Delayed retry và khả năng phục hồi sau restart

RetryTemplate trong ví dụ hữu ích cho lỗi tạm thời ngắn. Khi hệ thống đích có thể lỗi hàng phút, giữ nhiều listener thread ngủ backoff là tốn tài nguyên. Khi đó cần mô hình **retry bền vững**.

### 17.1. Retry queue với TTL/DLX

Một topology thường gặp:

~~~mermaid
flowchart TD
    MQ["orders.created.q"] --> C["Consumer"]
    C -->|"Thành công"| A["ACK"]
    C -->|"Cần thử lại sau"| RX["Retry exchange"]
    RX --> RQ["Retry queue<br/>TTL có kiểm soát"]
    RQ -->|"Hết TTL / DLX"| EX["orders.events"]
    EX --> MQ
    C -->|"Hết retry / dữ liệu lỗi"| D["Final DLQ"]
~~~

Có thể thiết kế main queue dead-letter tới retry queue rồi retry queue dead-letter quay lại main queue. Hoặc consumer **republish** message sang retry exchange. Các cách này khác nhau về khả năng kiểm soát **số lượt**, delay và mốc ACK của bản gốc.

### 17.2. Không ACK bản gốc trước khi lưu bản retry an toàn

Nếu consumer chủ động republish sang retry exchange, rồi **ACK bản gốc ngay trước khi broker xác nhận bản mới**, có khoảng trống mất sự kiện khi publish mới thất bại.

Một quy trình cần cân nhắc:

1. Có một eventId nghiệp vụ ổn định.
2. Tạo/ghi nhận retry intent trong kho bền vững hoặc publish sang retry exchange với confirms/returns phù hợp.
3. Chỉ ACK delivery gốc khi mốc nhận trách nhiệm mới đạt yêu cầu.
4. Nếu kết quả republish **UNKNOWN**, không tự cho rằng nó chưa gửi.
5. Chấp nhận khả năng có **hai bản cùng eventId**, để consumer idempotent bảo vệ side effect.

**Không dễ tạo một transaction nguyên tử giữa ACK delivery gốc và publish message mới**, ngay cả khi cả hai thao tác dùng RabbitMQ. Nếu yêu cầu bảo đảm nghiêm ngặt, cần phân tích transaction/confirm của broker và điểm lưu bền riêng, không chỉ thêm hai dòng gọi API.

### 17.3. Bounded attempts qua nhiều lần redelivery

**RetryTemplate.maxAttempts(3)** chỉ giới hạn một vòng xử lý trong tiến trình. Sau crash/connection reset, broker có thể giao lại delivery và vòng retry bắt đầu lại.

Nếu muốn giới hạn tổng số lần thực thi theo eventId:

- Lưu **attempt counter bền vững** trong inbox/job table hoặc nguồn trạng thái phù hợp.
- Hoặc dựa trên một chính sách broker được hỗ trợ, như **delivery limit** của loại queue tương ứng, với các điều kiện/version được kiểm chứng.
- Không chỉ dùng một counter Java trong bộ nhớ.
- Nếu sử dụng **x-death**, kiểm tra việc broker cập nhật header và cách republish/headers ảnh hưởng tới giá trị; không dùng dữ liệu có thể do producer tự đặt để thay quyền kiểm soát retry.

### 17.4. Khi retry thất bại mãi

Message cần được đưa tới **final DLQ hoặc trạng thái lỗi bền vững**, có người sở hữu quy trình điều tra. Một retry queue không có stop condition có thể tạo vòng lặp vài giờ hoặc vài ngày, liên tục tốn tài nguyên mà không giải quyết được nguyên nhân.

## 18. Idempotency và giới hạn của “exactly once”

Manual ACK giải quyết quyền quyết định **khi nào báo broker rằng delivery đã được xử lý theo hợp đồng consumer**. Nó không đảm bảo mọi business side effect chỉ xảy ra một lần.

### 18.1. Hai khoảng crash cơ bản

~~~text
Trường hợp A:
  Message nhận
  -> ACK
  -> process crash
  -> DB chưa commit
  => Có nguy cơ mất tác động nghiệp vụ

Trường hợp B:
  Message nhận
  -> DB commit
  -> process crash trước ACK
  -> broker redelivery
  => Có nguy cơ lặp tác động nghiệp vụ
~~~

Chọn **DB commit rồi ACK** để tránh trường hợp A, và dùng **idempotent consumer** để kiểm soát trường hợp B.

### 18.2. Inbox với unique constraint

~~~text
processed_events
  consumer_name   VARCHAR
  event_id        VARCHAR
  processed_at    TIMESTAMP

UNIQUE(consumer_name, event_id)
~~~

Khi xử lý:

1. Parse/validate eventId.
2. Trong transaction database, **insert nếu chưa tồn tại** theo unique constraint.
3. Nếu duplicate hợp lệ, không lặp side effect.
4. Nếu mới, áp dụng nghiệp vụ và commit cùng dấu đã xử lý.
5. Sau khi method transaction thành công, gửi ACK.

Nếu eventId trùng nhưng payload khác, cần policy phát hiện **collision/conflict**, không âm thầm coi mọi trường hợp cùng ID đều hợp lệ. Có thể lưu checksum hoặc định danh nguồn trong inbox nếu hợp đồng yêu cầu.

### 18.3. Khi side effect thuộc hệ thống khác

Nếu consumer gọi HTTP API đặt hàng, dịch vụ thanh toán hoặc ghi JMS/Kafka ngoài transaction DB, một unique constraint local chưa đủ để bảo đảm side effect ngoài không lặp. Cần:

- Gửi **idempotency key** tới bên nhận nếu API hỗ trợ.
- Lưu trạng thái yêu cầu/response trong durable workflow.
- Có phương án reconcile khi timeout xảy ra gần lúc hệ thống ngoài commit.
- Thiết kế compensating action khi hợp đồng cho phép.

Không tuyên bố exactly-once end-to-end chỉ vì đã bật MANUAL ACK hoặc queue durable.

## 19. Vòng đời listener, shutdown và quyền truy cập

Spring AMQP listener container và Spring Integration endpoint thường tham gia cơ chế **Lifecycle/SmartLifecycle**: start, stop, autoStartup và phase theo configuration. ConnectionFactory quản lý connection/channel dùng chung với RabbitTemplate và những listener khác.

### 19.1. Thứ tự shutdown có ảnh hưởng tới ACK

Giả sử một handler đang chạy transaction lâu, trong khi hệ thống bắt đầu shutdown:

1. Dừng tiếp nhận công việc mới theo cơ chế của ứng dụng/listener container.
2. Cho những handler đã nhận delivery có một khoảng thời gian hoàn tất.
3. Nếu transaction commit thành công và channel còn khả dụng, ACK đúng tag.
4. Nếu channel/connection đã đóng, không cố ACK qua một channel mới; để broker xử lý những delivery chưa được xác nhận theo cơ chế phục hồi.
5. Khi restart, consumer đọc lại event chưa settle, inbox/idempotency ngăn side effect trùng.

**stop() không đồng nghĩa toàn bộ delivery đang unacked đều đã ACK.** Thời gian shutdown, container semantics và trạng thái connection quyết định chuyện gì xảy ra với những delivery đang xử lý.

### 19.2. Manual ACK với nhiều consumer

Nếu SMLC có nhiều consumer trên cùng queue, mỗi consumer nhận các delivery trên channel tương ứng. **Tag 1** của channel A không phải cùng delivery với **tag 1** của channel B.

Đừng lưu **Channel** và **deliveryTag** vào singleton field “lastDelivery” rồi dùng cho mọi handler. Lấy metadata đi cùng **chính Spring Message** của delivery đang xử lý; settlement phải dùng đúng channel/tag, không multiple ACK tràn sang delivery khác.

### 19.3. Thread model và độ an toàn của AMQP Channel

RabbitMQ Java client Channel không được coi là một data object thread-safe có thể đưa vào mọi task tùy ý. Nếu dùng mô hình ACK bất đồng bộ, kiểm tra các tính năng async ACK/out-of-order ACK được Spring AMQP phiên bản đó hỗ trợ và hạn chế thread crossing.

Một hướng đơn giản, dễ chứng minh đúng là **handler đồng bộ trong DirectChannel** với một điểm settlement rõ ràng. Nếu cần kéo dài thời gian xử lý, chuyển sang mô hình **durable inbox** có thể phù hợp hơn việc giữ channel mở nhiều phút.

### 19.4. Bảo mật và quyền RabbitMQ

- Consumer cần quyền **read** trên queue và quyền liên quan theo broker/vhost.
- Tài khoản có quyền configure được sử dụng cho khai báo exchange/queue/binding nếu topology do ứng dụng tạo; không cấp quyền rộng không cần thiết.
- Dùng TLS và xác minh chứng chỉ khi môi trường yêu cầu; nạp credential từ secret manager/environment.
- Đừng log toàn bộ payload, header nhạy cảm hoặc RabbitMQ connection URI có password.
- DLQ cũng có thể chứa dữ liệu cá nhân hoặc nghiệp vụ quan trọng; cần quyền đọc, retention và quy trình xóa phù hợp.

### 19.5. Khác biệt giữa MANUAL ACK và producer confirm trong vận hành

Nếu một luồng có cả AMQP inbound adapter và outbound adapter:

~~~text
RabbitMQ queue A
  -> consumer MANUAL ACK
  -> transform
  -> AMQP outbound adapter
  -> RabbitMQ queue B
~~~

Không thể khẳng định rằng sau khi **MessageChannel.send vào outbound adapter thành công** thì đã có publisher confirm/return phù hợp ở queue B. Nếu consumer A **ACK trước khi publish sang B được xác nhận**, message có thể bị mất giữa hai queue.

Với một bridge quan trọng, cần định nghĩa điểm lưu bền/transaction giữa nguồn và đích, hoặc dùng outbox/inbox và producer confirms để có khả năng khôi phục. **MANUAL ACK của queue A không thay thế publisher confirms của lần publish sang queue B.**

## 20. Quan sát và điều tra sự cố

Manual ACK chỉ đáng tin nếu ứng dụng biết bao nhiêu delivery đang chờ, bao nhiêu được settle và điều gì xảy ra với những lỗi chưa xử lý.

| Lớp | Chỉ số nên theo dõi | Khi bất thường có thể gợi ý |
| --- | --- | --- |
| **RabbitMQ queue** | ready, unacked, total, message age | Backlog hoặc delivery bị giữ quá lâu |
| **RabbitMQ consumer** | consumer count, delivery rate, ACK/NACK/reject/requeue rate | Listener có hoạt động, có poison loop không |
| **Spring AMQP container** | Consumer hiện tại, reconnect, listener exceptions, shutdown | Vấn đề connection hoặc error handler |
| **Spring Integration flow** | Input count, handler latency/errors, errorChannel | Lỗi trước hoặc sau service activator |
| **Retry** | attempts, exhausted count, backoff duration | Downstream tạm lỗi hay lỗi cố định |
| **DLQ** | Number of entries, oldest age, error category | Message không thể xử lý và backlog điều tra |
| **Database** | Transaction latency, rollbacks, unique violations | Nút thắt hoặc tranh chấp idempotency |
| **Nghiệp vụ** | Unique eventId processed, duplicates ignored, business success | ACK có tương ứng với hoàn tất nghiệp vụ không |

### 20.1. Các mẫu dữ liệu thường gặp

**Ready tăng, Unacked gần consumer × prefetch, ACK rate thấp:** có thể handler chậm, retry trong listener giữ message hoặc quên ACK. Đừng phản xạ tăng prefetch ngay; kiểm tra worker đang làm gì.

**Unacked gần 0, ACK rate cao, business success thấp:** có thể ACK trước side effect, error flow nuốt exception, hoặc counter nghiệp vụ không đo đúng. Đối chiếu transaction database và thời điểm settlement.

**Requeue/redelivery tăng rất nhanh:** nghi ngờ basicNack(requeue=true) lặp vô hạn, thiếu backoff hoặc downstream luôn lỗi.

**DLQ tăng nhanh sau deploy:** kiểm tra JSON schema/version, converter, eventType, quyền DB và những thay đổi topology; không chỉ tăng số consumer.

**Số consumer về 0 dù queue còn ready:** có thể listener không chạy, RabbitMQ connection/credential lỗi hoặc container đang reconnect.

**Duplicate eventId tăng sau restart:** redelivery hoặc producer retry có thể bình thường; quan trọng là **số business side effects trùng** phải được khống chế.

### 20.2. Log và tracing an toàn

Ví dụ metadata có ích:

~~~text
consumer=warehouse
eventId=evt-1001
queue=orders.created.q
deliveryTag=42
redelivered=true
retryAttempt=3
outcome=REJECT_TO_DLQ
errorCategory=TRANSIENT_EXHAUSTED
processingMillis=1850
~~~

**deliveryTag=42** chỉ mang ý nghĩa trong channel tại thời điểm delivery; log có thể hỗ trợ điều tra nhưng không lưu tag như khóa nghiệp vụ lâu dài. Không dump Channel object, credential, token hay payload nhạy cảm.

### 20.3. Cảnh báo theo SLA

Nên có cảnh báo khi:

- Message age vượt thời gian xử lý cho phép.
- Ready/unacked vượt ngưỡng tải được xác định qua benchmark.
- Retry exhausted hoặc DLQ ingress tăng bất thường.
- Consumer count về 0 lâu hơn ngưỡng phục hồi.
- Thời gian xử lý p95/p99 hoặc DB rollback tăng.
- Không có ACK tiến triển dù delivery rate cao.

Ngưỡng cụ thể phải dựa trên workload và SLA thực, không chép một con số từ bài học sang production.

## 21. Ma trận kiểm thử MANUAL ACK và retry

Nên thử với **RabbitMQ thật trong môi trường cô lập** (chẳng hạn broker test riêng hoặc Testcontainers), không chỉ mock OrderManualAckHandler.

| Kịch bản | Hành động test | Kết quả cần xác minh |
| --- | --- | --- |
| **Thành công** | Gửi event hợp lệ, DB hoạt động | Transaction hoàn tất, ACK một lần, message rời unacked |
| **Duplicate eventId** | Gửi lại cùng eventId | Side effect không lặp; ACK delivery hợp lệ |
| **Payload sai** | Gửi String không đúng contract | Reject không requeue, vào DLQ nếu topology đúng |
| **Schema không hỗ trợ** | Gửi phiên bản mới consumer không hiểu | Không retry nóng; có log/cách ly theo policy |
| **DB lỗi lần đầu, lần hai thành công** | Mock/stub transient exception 1 lần | Retry hữu hạn, cuối cùng ACK |
| **DB liên tục lỗi tạm thời** | Fail tất cả attempts | Sau 3 attempts, NACK requeue=false, vào DLQ |
| **Non-retryable technical error** | Ném exception không thuộc retryable | Không retry vô hạn; đi nhánh lỗi phù hợp |
| **Quên ACK** | Test handler không settle | Unacked giữ quota prefetch; queue ready có thể tăng |
| **ACK hai lần** | Test cố ý settle cùng tag hai lần ở broker cô lập | Phát hiện channel/protocol error, không dùng multiple sai |
| **Sai channel/tag** | Test cố ý ACK trên channel khác | Phát hiện lỗi delivery tag/channel, không coi là thành công |
| **basicAck IOException** | Đóng connection gần lúc ACK | Có khả năng redelivery; idempotency bảo vệ side effect |
| **Crash sau DB commit** | Kill consumer trước ACK | Delivery có thể được giao lại, side effect không trùng |
| **Crash trước DB commit** | Kill consumer giữa transaction | Rollback và xử lý lại đúng |
| **Lỗi converter trước handler** | Gửi malformed JSON | Error handler của container xử lý đúng, không treo unacked |
| **errorChannel hấp thụ lỗi** | Flow bắt exception nhưng không settle | Test phát hiện thiếu ACK/NACK |
| **ExecutorChannel** | Đưa xử lý sang thread khác trong test | Xác minh không ACK sớm hoặc thay bằng inbox bền vững |
| **DLX thiếu binding** | Reject message sai trong broker test | Phát hiện topology không thể giữ message lỗi |
| **NACK requeue=true** | Cho handler liên tục lỗi trong test ngắn | Quan sát redelivery nóng để chứng minh cần bounded retry |
| **Prefetch = 1 so với 16** | Handler chậm, nhiều consumer | Đo unacked, fairness, throughput, latency |
| **Graceful shutdown** | Dừng app khi một số delivery unacked | Không tạo mất side effect; phục hồi theo policy |
| **Multiple instances** | Chạy hai JVM cùng queue | Competing consumers, cùng inbox/unique key chống trùng |

### 21.1. Test unit business handler chưa đủ

Một unit test có thể mock **Channel** để kiểm tra:

~~~text
success       -> basicAck(tag, false)
invalid       -> basicReject(tag, false)
exhausted     -> basicNack(tag, false, false)
ack IOException -> exception propagated, no second settlement
~~~

Nhưng mock không chứng minh:

- Listener container đã cấu hình MANUAL thật.
- AmqpHeaders.CHANNEL và DELIVERY_TAG có được mapper chuyển qua hay không.
- DLX/DLQ tồn tại và broker có route message bị reject.
- Broker có redeliver sau connection close hay không.
- Transaction thực sự commit trước ACK.

Do đó cần **integration test** kiểm chứng hành vi trên RabbitMQ thật và database test với unique constraint.

### 21.2. Thử publish message

Với RabbitTemplate và topology ví dụ:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class OrdersTestPublisher {

    private final RabbitTemplate rabbitTemplate;

    public OrdersTestPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void sendValid() {
        rabbitTemplate.convertAndSend(
            OrdersManualAckTopology.EVENTS_EXCHANGE,
            OrdersManualAckTopology.ROUTING_KEY,
            "evt-1001|O-1001|150000");
    }

    public void sendMalformed() {
        rabbitTemplate.convertAndSend(
            OrdersManualAckTopology.EVENTS_EXCHANGE,
            OrdersManualAckTopology.ROUTING_KEY,
            "not-a-valid-event");
    }
}
~~~

**Cảnh báo:** Hai lời gọi chỉ minh họa tạo message test. Hãy dùng queue hoặc virtual host test riêng; không đẩy message malformed vào queue production. Khi listener đang chạy, message có thể được xử lý ngay nên **queue depth bằng 0 không chứng minh publisher gửi thất bại**.

### 21.3. Test đúng điểm transaction

Một test quan trọng nên dùng **fake repository/DB test** để tạo các thời điểm:

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ
    participant L as Listener
    participant S as Business Service
    participant DB as Test DB
    B->>L: Delivery evt-1001
    L->>S: process(evt-1001)
    S->>DB: Insert inbox + update projection
    DB-->>S: Commit
    S-->>L: Return success
    L-->>B: basicAck
    Note over B,DB: Kill trước ACK để thử redelivery
~~~

Khi kill sau commit nhưng trước ACK, consumer mới có thể nhận lại **evt-1001**, kiểm tra inbox và ACK mà không cập nhật projection lần hai. Đây mới là kiểm thử có giá trị cho idempotency, không chỉ kiểm tra method được gọi đúng số lần trong một tiến trình.

### 21.4. Kiểm thử số lần retry

Đặt stub database sao cho:

- Attempt 1 ném TransientOrderProcessingException.
- Attempt 2 thành công.
- Xác minh handler gọi ACK **một lần** sau attempt 2, không ACK sau attempt 1.

Một bài khác để database luôn ném transient exception:

- Xác minh tổng **ba attempts trong vòng retry cục bộ**.
- Không ACK trên các attempts thất bại.
- Cuối cùng NACK requeue=false một lần.
- Broker giữ message trong DLQ nếu topology đã khai báo đúng.

Không dùng số lần nhận từ broker làm số attempts của RetryTemplate: một delivery có thể được xử lý nhiều lần trong listener trước khi NACK/ACK.

## 22. Khi nào nên chọn MANUAL thay vì AUTO?

**MANUAL ACK** có giá trị khi bạn phải kiểm soát chính xác việc xác nhận delivery sau một mốc xử lý hoặc lưu bền, hay cần một workflow settlement có cấu trúc. Tuy nhiên nó tăng trách nhiệm về channel/tag, exception, thread model và vận hành.

| Tình huống | Phương án nên cân nhắc | Lý do |
| --- | --- | --- |
| Handler đồng bộ, exception lan đúng, không có điểm ACK đặc biệt | **AUTO** cùng retry/error policy đã kiểm thử | Ít nguy cơ quên/double ACK, container quản lý settlement |
| Cần tự quyết định ACK sau DB commit và phân loại từng message | **MANUAL** với một chủ sở hữu settlement | Có thể chọn ACK/reject/NACK có chủ đích |
| Công việc cực nhanh, best-effort, chấp nhận mất delivery | **NONE** chỉ khi hợp đồng cho phép | Không bảo đảm redelivery sau xử lý thất bại |
| Handler async dài, cần phục hồi sau restart | **Durable inbox/job + ACK sau lưu bền** | Không cần giữ channel/tag sống suốt công việc dài |
| Chuyển RabbitMQ A sang RabbitMQ B quan trọng | **Publisher confirms + durable state + ACK nguồn có kiểm soát** | Không coi ACK của nguồn là xác nhận broker đích |
| Lỗi hạ tầng kéo dài phút/giờ | **Delayed retry bền vững** | Tránh giữ nhiều listener thread ngủ trong retry |
| Cần đúng một side effect theo eventId | **Idempotent consumer + transaction** | Manual ACK đơn lẻ không bảo đảm exactly-once |

### 22.1. Khuyến nghị chọn điểm ACK

Với consumer cập nhật một database, lựa chọn dễ giải thích là:

~~~text
Receive delivery
  -> validate
  -> begin DB transaction
  -> atomic inbox uniqueness + business change
  -> DB commit
  -> basicAck(tag, false)
~~~

Với consumer chuyển việc sang worker bất đồng bộ:

~~~text
Receive delivery
  -> validate
  -> begin DB transaction
  -> save durable inbox/job
  -> DB commit
  -> basicAck(tag, false)
  -> background worker later handles job
~~~

Hai mô hình đều có thể đúng, nhưng **ý nghĩa ACK khác nhau**. Mô hình thứ hai ACK việc **đã lưu bền để xử lý sau**, không phải **đã hoàn thành business processing**. Hãy nêu rõ trong thiết kế và tài liệu SLA.

## 23. Các sai lầm thường gặp

**“Manual ACK đảm bảo exactly-once.”** Sai. Nếu DB đã commit nhưng ACK mất, message vẫn có thể redeliver. Cần **eventId ổn định, unique constraint/inbox và transaction**.

**“Có thể ACK trước khi gọi DB rồi retry nếu DB lỗi.”** Khi ACK đã được broker chấp nhận, broker không còn chờ xử lý delivery đó để tự redeliver. Nếu chưa lưu bền nguồn retry khác, nghiệp vụ có thể mất.

**“basicAck(tag, true) chỉ xác nhận một message.”** Cờ multiple=true có thể ACK **nhiều delivery chưa xác nhận** trên cùng channel. Với nhiều message đang in-flight, dùng nhầm cờ này có thể ACK sớm các delivery chưa xử lý.

**“Delivery tag là ID toàn cục.”** Tag chỉ có ý nghĩa trên channel tương ứng. Không ACK delivery của channel A bằng channel B hay giữ tag để dùng sau reconnect.

**“Gọi basicAck thành công chắc chắn broker đã xử lý ACK.”** Nếu connection mất gần thời điểm gửi frame, trạng thái có thể không được quan sát đầy đủ; consumer phải chấp nhận redelivery.

**“basicNack(requeue=true) tự có exponential backoff.”** Requeue có thể diễn ra ngay. Nếu dữ liệu sai cố định, có thể tạo hot loop không có điểm dừng.

**“basicNack(requeue=false) đảm bảo vào DLQ.”** Cần DLX, DLQ và binding hoạt động; nếu topology/policy không phù hợp, message có thể không được giữ.

**“DLQ tự động sửa được message.”** DLQ chỉ cách ly/giữ theo policy; vẫn cần người sở hữu, thời hạn lưu và công cụ sửa/replay an toàn.

**“Spring Retry maxAttempts=3 nghĩa là toàn đời event chỉ chạy ba lần.”** RetryTemplate giới hạn một vòng chạy; broker redelivery hoặc republish sau restart có thể tạo vòng mới. Muốn giới hạn tổng cần trạng thái bền vững/chính sách broker tương ứng.

**“Mọi RuntimeException đều nên retry.”** Lỗi schema, quyền, cấu hình và business validation thường không tự hồi phục. Chỉ retry lớp lỗi thực sự có thể hồi phục.

**“MANUAL là AUTO nhưng có thể gọi basicAck thêm cho chắc.”** Hai mode có owner settlement khác nhau. Đừng tự ACK cùng delivery nếu container đã xử lý theo AUTO.

**“Cứ đặt ACK trong finally là an toàn.”** finally vẫn chạy khi DB rollback hoặc handler lỗi, có thể làm mất khả năng broker giao lại message.

**“Nếu handler ném lỗi thì chắc chắn vào errorChannel rồi DLQ.”** Lỗi converter có thể xảy ra trước khi có Spring Message; errorChannel có thể hấp thụ lỗi; đường reject/NACK phụ thuộc container và topology.

**“DirectMessageListenerContainer là DirectChannel.”** Một bên là listener container AMQP, bên kia là Spring Integration channel chạy đồng bộ.

**“ExecutorChannel luôn an toàn cho consumer MANUAL.”** Có rủi ro channel/tag được chuyển giữa thread, mất connection, ACK lệch thứ tự và mất công việc khi queue nội bộ không bền vững.

**“QueueChannel trong bộ nhớ là một durable inbox.”** QueueChannel mặc định không mang cùng bảo đảm lưu bền với database inbox; crash có thể làm mất task đã ACK ở broker.

**“Prefetch=100 tức là có 100 nghiệp vụ xử lý song song.”** Prefetch là giới hạn delivery chưa ACK, không phải số worker. Nó có thể chỉ làm unacked và memory tăng.

**“Prefetch=1 bảo đảm thứ tự và không trùng.”** Có thể có nhiều consumer, crash, requeue hoặc producer retry. Thứ tự/duplicate cần cơ chế nghiệp vụ riêng.

**“Cứ có @Transactional là ACK và DB commit nguyên tử.”** @Transactional thường quản lý transaction của tài nguyên cụ thể; ACK RabbitMQ không tự tham gia transaction đó.

**“Sau khi đã NACK, handler có thể gọi ACK để sửa quyết định.”** Một delivery không được settle hai lần; phải coi quyết định settlement là kết thúc cho tag tương ứng.

**“Nhiều consumer trên một queue đều nhận mọi event.”** Chúng thường cạnh tranh delivery. Nếu hai dịch vụ đều cần cùng sự kiện, dùng hai queue/bindings riêng.

**“Publisher confirm thay thế consumer ACK.”** Confirm thuộc producer/broker; consumer ACK chỉ xác nhận sau delivery. Một bridge RabbitMQ A → B phải phân biệt xác nhận nguồn và xác nhận đích.

**“redelivered=true nghĩa là business đã chạy một lần.”** Đó không phải bằng chứng transaction thành công, chỉ là gợi ý về giao nhận.

**“Lưu delivery tag trong database cho phép ACK sau khi ứng dụng restart.”** Channel/tag cũ có thể không còn hợp lệ sau connection restart; lưu **eventId và trạng thái nghiệp vụ**, không lưu tag làm tham chiếu bền vững.

## 24. Câu hỏi tự kiểm tra

1. Manual acknowledgment cho phép ứng dụng kiểm soát điều gì mà AUTO ACK thường giao cho container?
2. Trong Spring AMQP, AUTO có phải broker ACK ngay khi message được giao không?
3. Delivery tag có phạm vi định danh như thế nào? Tại sao không dùng tag làm eventId?
4. Khác biệt giữa **basicAck(tag, false)** và **basicAck(tag, true)** là gì?
5. **basicReject(tag, false)** và **basicNack(tag, false, false)** được dùng trong trường hợp nào?
6. Khi gọi **basicNack(tag, false, true)**, broker có bắt buộc chờ vài giây trước khi giao lại không?
7. Vì sao một message có thể được xử lý lại sau khi DB đã commit thành công?
8. Nếu code ACK trước DB commit rồi process crash, điều gì có thể xảy ra?
9. Vì sao MANUAL ACK vẫn cần idempotent consumer và unique constraint?
10. Giữa retry trong listener và retry qua broker có những khác biệt nào về unacked, backoff và phục hồi sau restart?
11. RetryTemplate với maxAttempts(3) nghĩa là bao nhiêu lượt xử lý trong một lần gọi?
12. Nếu RabbitMQ redeliver event sau process crash, bộ đếm RetryTemplate trong tiến trình có còn không?
13. Trường hợp nào nên reject không requeue ngay thay vì retry?
14. Nếu queue chưa có DLX/binding, điều gì có thể xảy ra sau basicReject(tag, false)?
15. Tại sao dùng DLQ không có nghĩa nghiệp vụ đã được hoàn tất hoặc dữ liệu lỗi đã được sửa?
16. Với 4 consumer và prefetch 8 mỗi consumer, cửa sổ unacked lý thuyết khoảng bao nhiêu?
17. Nếu unacked đạt giới hạn nhưng ACK rate bằng 0, bạn sẽ kiểm tra những điểm nào?
18. Khi inbound adapter dùng MANUAL, cần lấy **Channel** và **delivery tag** từ đâu và kiểm tra điều gì trước khi ACK?
19. Nếu Spring Integration Message không có AmqpHeaders.CHANNEL, có thể tạo channel mới và dùng delivery tag cũ để ACK không?
20. Nếu MessageConverter lỗi trước khi tạo Spring Message, handler manual ACK có chắc được gọi không?
21. Chuyển DirectChannel sang ExecutorChannel thay đổi ranh giới lỗi và ACK như thế nào?
22. Khi nào nên ACK sau khi lưu **durable inbox** nhưng trước khi business worker hoàn tất?
23. Nếu consumer chuyển message từ queue A sang queue B, vì sao ACK của A không thay publisher confirm của B?
24. Những test nào cần để chứng minh DB commit thực sự xảy ra **trước** ACK?
25. Khi ACK gặp IOException sau DB commit, consumer nên xử lý rủi ro redelivery thế nào?
26. Vì sao nên đặt số attempts, backoff và DLQ cho lỗi DB tạm thời thay vì requeue vô hạn?
27. Nếu eventId trùng nhưng payload khác, một idempotent consumer nên xử lý ra sao?
28. Khi graceful shutdown còn delivery unacked, những vấn đề nào cần theo dõi?
29. Khi nào dùng AUTO ACK đã kiểm thử có thể đơn giản và phù hợp hơn MANUAL ACK?
30. Phân biệt consumer ACK, publisher confirm và business reply trong một hệ thống có cả AMQP inbound và outbound gateway.

## Tổng kết

**Manual acknowledgment** là quyền quyết định **khi nào xác nhận hoặc từ chối một RabbitMQ delivery**. Trong Spring Integration, cơ chế này được đặt trên **Spring AMQP listener container** của **AMQP inbound channel adapter**, còn handler có thể lấy **channel và delivery tag** phù hợp để gọi **basicAck**, **basicNack** hoặc **basicReject**. Phải dùng **đúng tag trên đúng channel**, tránh **multiple ACK** ngoài ý muốn và không settle hai lần.

Retry đáng tin cậy bắt đầu từ **phân loại lỗi**: dữ liệu sai thì cách ly, lỗi tạm thời retry hữu hạn với backoff, hết retry thì reject/NACK không requeue để đi vào **DLX/DLQ** đã được cấu hình và kiểm thử. **basicNack(requeue=true)** không phải delayed retry và có thể tạo vòng lặp nóng; **RetryTemplate** trong bộ nhớ không giới hạn tổng số lần xử lý sau mọi lần broker redelivery.

Điểm ACK nên theo một **ranh giới đã cam kết**: DB transaction commit hoặc dữ liệu đã được lưu vào **durable inbox**. Vì broker vẫn có thể giao lại delivery sau crash hoặc mất kết nối gần ACK, consumer phải có **eventId ổn định, idempotency, unique constraint và chiến lược phục hồi**. Cuối cùng, để vận hành đúng cần kiểm soát **prefetch/concurrency, thread model, errorChannel, converter, lifecycle, queue ready/unacked, DLQ và business outcomes**. Những nguyên tắc này giúp tích hợp AMQP với các luồng File, SFTP, HTTP, JMS, Kafka và database mà không nhầm một lời gọi gửi thành công với một nghiệp vụ đã hoàn tất.
