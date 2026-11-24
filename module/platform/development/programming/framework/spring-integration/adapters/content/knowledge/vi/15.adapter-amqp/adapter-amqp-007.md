# Message-driven container và prefetch

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao **AMQP inbound channel adapter** thường sử dụng **message-driven listener container** thay cho Spring Integration poller.
- Phân biệt trách nhiệm của RabbitMQ broker, **Spring AMQP listener container**, AMQP inbound adapter, MessageChannel và service activator.
- So sánh **SimpleMessageListenerContainer (SMLC)** và **DirectMessageListenerContainer (DMLC)**, đặc biệt về thread model và cấu hình concurrency.
- Hiểu **prefetch (basic.qos)**, số delivery chưa ACK, mối quan hệ với throughput, memory, độ công bằng và thời gian xử lý.
- Cấu hình một luồng **Spring Integration Java DSL** với SMLC, prefetch, concurrent consumers, ACK tự động và dead-letter queue.
- Phân tích các tình huống ACK quá sớm, requeue lặp, redelivery, idempotency, kết nối lỗi và graceful shutdown.
- Thiết lập phương pháp đo **ready/unacked backlog**, publish/ack rate, latency và các thử nghiệm tải để điều chỉnh prefetch có căn cứ.

## 1. Bài toán: message đến nhanh hơn khả năng xử lý

Một RabbitMQ queue **orders.created.q** nhận sự kiện đơn hàng. Nhà xuất bản gửi vài trăm sự kiện mỗi giây, còn ứng dụng nhận phải kiểm tra schema, gọi database và ghi trạng thái tồn kho. Nếu consumer chỉ xử lý từng message tuần tự, backlog có thể tăng. Nếu mở quá nhiều consumer hoặc nâng prefetch quá cao, nhiều delivery bị giữ ở phía ứng dụng, gây tăng bộ nhớ, mất công bằng hoặc timeout khi ACK.

Spring Integration giải bài toán kết nối bằng **AMQP inbound channel adapter**: adapter nhận dữ liệu từ Spring AMQP listener rồi đưa vào MessageChannel. Nhưng tốc độ nhận và khả năng giao lại message phụ thuộc mạnh vào **listener container** và cơ chế **prefetch** của RabbitMQ.

~~~mermaid
flowchart LR
    P["Producer"] --> X["RabbitMQ exchange"]
    X --> Q["Queue<br/>orders.created.q"]
    Q --> LC["Spring AMQP<br/>listener container"]
    LC --> IA["AMQP inbound<br/>channel adapter"]
    IA --> CH["Spring Integration<br/>MessageChannel"]
    CH --> H["Service activator<br/>OrderService"]
    H --> DB[("Database")]
    LC -. "ACK / NACK" .-> Q
~~~

**Hai câu hỏi phải được tách biệt:**

1. **Có thể nhận trước bao nhiêu message chưa ACK?** Prefetch/broker QoS chi phối.
2. **Có bao nhiêu consumer hoặc công việc xử lý đồng thời?** Listener concurrency, thread model và downstream chi phối.

Prefetch **không tự tạo thêm worker xử lý**. Tăng concurrency **không tự bảo đảm** database hoặc API downstream sẽ xử lý nhanh hơn.

## 2. Từ queue đến MessageChannel: các lớp trách nhiệm

| Thành phần | Chức năng | Không nên nhầm với |
| --- | --- | --- |
| **RabbitMQ queue** | Giữ message ready hoặc đang được giao cho consumer | Spring MessageChannel |
| **ConnectionFactory** | Cấp kết nối/channel AMQP | Queue hoặc bộ lưu message |
| **Message listener container** | Quản lý consumer, nhận delivery, concurrency, prefetch, ACK/NACK, shutdown | Business handler |
| **AMQP inbound channel adapter** | Chuyển delivery thành Spring Message và gửi tới output channel | AMQP inbound gateway request–reply |
| **MessageConverter** | Chuyển body AMQP thành kiểu payload phù hợp | Transformer chuẩn hóa domain |
| **MessageChannel** | Chuyển message nội bộ đến filter, transformer, service activator | Queue bền vững của RabbitMQ |
| **Service activator** | Kiểm tra và thực hiện nghiệp vụ | Listener quản lý acknowledgment |

Một delivery có thể trải qua:

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ queue
    participant L as Listener container
    participant A as AMQP inbound adapter
    participant C as DirectChannel
    participant H as OrderService
    B-->>L: Giao delivery (prefetch cho phép)
    L->>A: Gọi listener
    A->>C: send(Spring Message)
    C->>H: Xử lý đồng bộ
    H-->>C: Hoàn tất / exception
    C-->>A: Kết quả xử lý đồng bộ
    A-->>L: Listener callback kết thúc
    L-->>B: ACK / NACK theo policy
~~~

Sơ đồ trên giả định **DirectChannel và handler đồng bộ**. Nếu MessageChannel đổi thành **ExecutorChannel**, listener có thể trả về sau khi đã giao việc cho executor mà **chưa biết** nghiệp vụ ở thread khác đã thành công hay chưa. Đây là thay đổi lớn về ranh giới ACK, không phải tối ưu hiệu năng vô hại.

## 3. Message-driven khác polling như thế nào?

Các adapter File, SFTP, JDBC thường dùng **MessageSource + Spring Integration poller** để chủ động quét nguồn theo lịch. Với AMQP inbound, RabbitMQ đã có cơ chế consumer/delivery nên cách phổ biến là **message-driven listener container**.

| Đặc điểm | Polling File/SFTP/JDBC | AMQP message-driven |
| --- | --- | --- |
| Nguồn kích hoạt | Scheduler gọi MessageSource.receive() | RabbitMQ/client giao delivery cho listener |
| Cấu hình nhịp | fixedDelay/fixedRate, maxMessagesPerPoll | consumer concurrency, prefetch, listener container |
| Tiến độ nguồn | File filter, watermark, metadata store | Consumer ACK/NACK, ready/unacked, redelivery |
| Không có dữ liệu | Poller có thể tiếp tục chạy và nhận null | Consumer tiếp tục chờ delivery theo cơ chế client |
| Kiểm soát tải | Tần suất poll/batch, capacity | QoS/prefetch, số consumer, thời gian xử lý |
| Khởi động/dừng | Bật/tắt scheduled endpoint | Bật/tắt listener container/consumer |

**RabbitMQ client có hoạt động nhận dữ liệu nội bộ**, nhưng điều đó không có nghĩa mọi AMQP inbound adapter cần một **Spring Integration Poller**. Ngược lại, khi dùng RabbitTemplate.receive(...) để chủ động kéo message, ứng dụng đang chọn một mô hình khác và phải tự thiết kế nhịp, lỗi, ACK, vòng đời phù hợp.

### 3.1. Message-driven container có phải request–reply gateway?

Không. **AMQP inbound channel adapter** nhận delivery một chiều, không tự trả response nghiệp vụ. **AMQP inbound gateway** nhận request và gửi AMQP reply theo hợp đồng reply-to/correlation. Cả hai có thể dùng listener container nhưng khác loại endpoint và kỳ vọng từ phía caller.

Broker **consumer ACK** chỉ xác nhận delivery ở mức giao thức; không biến một inbound adapter một chiều thành gateway hai chiều.

## 4. Hai loại listener container thường gặp

Spring AMQP cung cấp nhiều kiểu listener container. Hai loại phổ biến khi tích hợp RabbitMQ là:

- **SimpleMessageListenerContainer (SMLC)**.
- **DirectMessageListenerContainer (DMLC)**.

| Tiêu chí | SimpleMessageListenerContainer | DirectMessageListenerContainer |
| --- | --- | --- |
| Thread model | Delivery được chuyển qua cơ chế nội bộ của container rồi gọi listener trên thread tiêu thụ do container quản lý | Listener được gọi trực tiếp theo cơ chế thread của RabbitMQ Java client, với cách điều phối khác SMLC |
| Thiết lập concurrency | **concurrentConsumers**, **maxConcurrentConsumers**; có thể scale trong khoảng khi cấu hình | **consumersPerQueue** cùng các thiết lập liên quan; không dùng cùng thuật toán autoscale của SMLC |
| Prefetch | Cấu hình **prefetchCount** trên container | Cấu hình **prefetchCount** trên container |
| Queue management | Phù hợp nhiều mô hình listener truyền thống; có cơ chế điều chỉnh worker động | Có cơ chế quản lý consumer/queue và thread trực tiếp riêng |
| ACK/requeue | Dựa vào acknowledge mode, transaction, error handler/advice | Cũng dựa vào ACK mode và chính sách container nhưng khác triển khai |
| Khi lựa chọn | Dễ bắt đầu, đặc biệt khi cần scale consumer theo khoảng | Cân nhắc khi muốn đặc tính dispatch trực tiếp, quản lý consumer theo queue và mô hình thread tương ứng |

Không nên tuyên bố DMLC **luôn nhanh hơn** SMLC hoặc SMLC **luôn an toàn hơn**. Hãy đo hiệu năng theo payload, độ trễ handler, số queue, kết nối, concurrency và phiên bản thư viện.

### 4.1. SMLC: concurrentConsumers và maxConcurrentConsumers

Với SMLC:

- **concurrentConsumers** là mức consumer ban đầu/tối thiểu.
- **maxConcurrentConsumers** là mức tối đa được phép khi cơ chế autoscaling động áp dụng.
- Các ngưỡng active/idle và khoảng thời gian điều chỉnh consumer ảnh hưởng tốc độ tăng/giảm.
- Tăng consumer cần thêm năng lực xử lý downstream; nó không phải cách sửa lỗi schema hoặc broker mất kết nối.

Ví dụ **concurrentConsumers = 2**, **maxConcurrentConsumers = 4** cho phép SMLC điều chỉnh số consumer trong khoảng đó theo thuật toán riêng, chứ không có nghĩa luôn chạy 4 worker.

### 4.2. DMLC: consumersPerQueue

Với DMLC, **consumersPerQueue** mô tả số consumer trên **mỗi queue** mà container quản lý. Nếu một DMLC theo dõi hai queue với consumersPerQueue = 3, mô hình có thể có ba consumer cho từng queue, tổng khoảng sáu consumer khi hoạt động bình thường.

Không chuyển máy móc các tham số SMLC như maxConcurrentConsumers sang DMLC. Cần xem API, thread pool, cấu hình connection và cách thay đổi số consumer theo phiên bản Spring AMQP.

### 4.3. Có cần tự tạo container?

Spring Boot có thể cấu hình listener container factory, nhưng Spring Integration endpoint có thể sử dụng **container tự tạo**, hoặc cấu hình container qua DSL/factory phù hợp. Quy tắc quan trọng: phải biết **container cụ thể nào** đang sở hữu inbound adapter, thay vì chỉnh một bean listener factory không được flow sử dụng rồi nghĩ rằng prefetch đã thay đổi.

## 5. Prefetch là gì?

**Prefetch** là giới hạn số **delivery chưa được consumer ACK** mà broker cho phép gửi trước theo QoS áp dụng. Trong RabbitMQ, cấu hình thường được thực hiện bằng **basic.qos(prefetchCount)** thông qua Spring AMQP.

~~~mermaid
flowchart LR
    Q["RabbitMQ queue<br/>ready"] -->|"Đẩy tối đa trong cửa sổ QoS"| C["Consumer"]
    C --> D["Unacked deliveries"]
    D --> H["Handler"]
    H -->|"ACK"| ACK["Giải phóng quota<br/>nhận thêm delivery"]
    H -. "NACK / reject" .-> R["Requeue / dead-letter<br/>theo policy"]
~~~

Ví dụ **prefetchCount = 5** trên một consumer có nghĩa broker có thể giao nhiều delivery chưa ACK nhưng giới hạn theo cửa sổ 5 delivery trong điều kiện QoS tương ứng. Khi một delivery được ACK, một vị trí trong cửa sổ được giải phóng để broker tiếp tục gửi.

**Prefetch không có nghĩa mỗi lần phải nhận đúng 5 message**, cũng không có nghĩa một consumer có 5 thread chạy nghiệp vụ song song. Nó giới hạn **cửa sổ unacked**, không quyết định độ dài batch Java hay số message lưu trong queue.

### 5.1. RabbitMQ áp dụng prefetch theo consumer như thế nào?

RabbitMQ có cách áp dụng **per-consumer prefetch** trong cấu hình thường dùng: giới hạn được áp cho từng consumer thay vì mặc định coi đây là một quota chung cho toàn channel. Một số cấu hình global QoS hoặc cơ chế client khác có thể làm phạm vi giới hạn thay đổi.

Trong Spring AMQP, **prefetchCount** của container thường được áp cho các consumer do container quản lý. Vì vậy, để ước lượng lượng message có thể đang in-flight, phải tính **prefetch của mỗi consumer × số consumer thực sự** thay vì chỉ nhìn một giá trị prefetch duy nhất.

### 5.2. Ready, unacked và ACK là ba trạng thái khác nhau

Trong RabbitMQ management, thường gặp:

- **Ready:** message đang ở queue và có thể được giao cho consumer.
- **Unacked:** delivery đã được broker giao nhưng đang chờ consumer ACK/NACK theo ngữ nghĩa đang dùng.
- **Total/queue depth:** tổng số message theo số liệu broker, có thể bao gồm ready và unacked.

Một queue có **Ready = 0** nhưng **Unacked = 80** không có nghĩa consumer đã hoàn thành 80 nghiệp vụ; có thể chúng đang giữ nhiều delivery chưa xác nhận. Ngược lại, **Ready tăng đều** khi consumer không theo kịp producer là dấu hiệu backlog đang tích lũy.

### 5.3. Công thức ước lượng cửa sổ unacked

Giả sử có **N consumer** với prefetch **P** mỗi consumer, không có giới hạn global bổ sung:

~~~text
Số delivery chưa ACK có thể in-flight ≈ N × P
~~~

Ví dụ **4 consumer × prefetch 20** cho phép tối đa khoảng **80 delivery đang unacked** trong điều kiện lý tưởng theo QoS áp dụng. Đây **không phải** cam kết broker sẽ luôn giao đủ 80, cũng không phải giới hạn toàn bộ backlog tại RabbitMQ. Số thực tế còn phụ thuộc tốc độ xử lý, kết nối, ACK, batch, consumer đang hoạt động và những giới hạn khác.

Nếu kích thước một payload trung bình khoảng **256 KiB**, chỉ riêng dữ liệu thô của 80 delivery đã khoảng **20 MiB**, chưa kể wrapper objects, decode, buffer và đối tượng nghiệp vụ. Với message lớn, tăng prefetch có thể gây áp lực bộ nhớ đáng kể.

### 5.4. Prefetch = 1

**Prefetch = 1** thường được cân nhắc khi:

- Message xử lý lâu và không đều về thời gian.
- Muốn giảm tình trạng một consumer giữ nhiều công việc trong khi consumer khác rảnh.
- Mỗi consumer nên chỉ có rất ít message chưa ACK.
- Cần giới hạn rủi ro phải redeliver nhiều message khi một consumer chết.

Đổi lại, throughput có thể giảm do broker phải chờ ACK trước khi cấp thêm message cho consumer. Với tác vụ nhanh và độ trễ mạng đáng kể, prefetch lớn hơn thường có ích. **Không có một giá trị prefetch tối ưu cho mọi workload.**

### 5.5. Prefetch lớn

Prefetch lớn có thể:

- Giảm thời gian consumer phải chờ lượt delivery tiếp theo.
- Tăng throughput cho handler xử lý nhanh.
- Nhưng cũng tăng **unacked**, mức dùng bộ nhớ và số delivery bị giữ khi một consumer chậm/chết.
- Làm sự phân bố công việc kém công bằng giữa các consumer khi thời gian xử lý không đều.
- Tăng số delivery phải requeue/redeliver khi connection đóng trước ACK.

Vì vậy cần điều chỉnh đồng thời **prefetch**, **concurrency**, **kích thước payload** và **thời gian xử lý thực tế**, thay vì chỉ tăng một tham số cho tới khi queue ready giảm.

## 6. Prefetch không thể tách rời ACK mode

Spring AMQP listener container hỗ trợ các chế độ ACK phổ biến:

| AcknowledgeMode | Cách xác nhận | Ảnh hưởng tới prefetch |
| --- | --- | --- |
| **AUTO** | Container ACK khi listener hoàn tất thành công; lỗi được xử lý theo policy | Prefetch giới hạn các delivery còn đang chờ container ACK |
| **MANUAL** | Code ứng dụng phải ACK/NACK theo delivery tag và AMQP channel phù hợp | Prefetch quota có thể bị giữ hết nếu quên ACK |
| **NONE** | Consumer dùng chế độ không đòi hỏi ACK thủ công, broker xem như đã giao | Cửa sổ unacked không bảo vệ quá trình xử lý nghiệp vụ theo cách AUTO/MANUAL |

**AUTO không có nghĩa broker tự ACK ngay khi giao.** Trong Spring AMQP, AUTO nghĩa container chủ động quản lý ACK theo kết quả listener. Ngược lại, mode NONE không bảo đảm redelivery khi tiến trình chết sau lúc nhận nhưng trước khi nghiệp vụ hoàn tất.

### 6.1. DirectChannel đồng bộ và AUTO ACK

Nếu inbound adapter đưa message vào **DirectChannel** và handler hoàn tất đồng bộ, exception của handler có thể lan ngược qua channel/adapter tới listener container. Container có thể ACK khi callback hoàn tất, hoặc reject/NACK theo error policy khi callback thất bại.

**ACK của consumer vẫn không tự tạo một transaction nguyên tử với database.** Nếu handler đã commit DB nhưng tiến trình chết trước khi ACK tới broker, message có thể được giao lại. Consumer cần idempotency nghiệp vụ.

### 6.2. ExecutorChannel/QueueChannel có thể làm ACK quá sớm

Nếu inbound adapter gửi tới **ExecutorChannel**:

~~~text
RabbitMQ delivery -> listener -> inbound adapter
                   -> ExecutorChannel chấp nhận tác vụ
                   -> listener callback kết thúc
                   -> container có thể ACK
                   -> handler trên thread khác mới thực thi
                   -> handler lỗi sau khi đã ACK
~~~

Đây là **khoảng rủi ro mất khả năng giao lại ở cấp RabbitMQ**. Không nên thay DirectChannel bằng ExecutorChannel chỉ để tăng throughput nếu mức ACK của nghiệp vụ phải phụ thuộc việc handler kết thúc. QueueChannel cũng tạo ranh giới bất đồng bộ tương tự; nếu có queue/message store bền vững thì có thể thiết kế điểm tiếp nhận an toàn, nhưng phải định nghĩa rõ lúc nào message đã được lưu bền.

### 6.3. Manual ACK cần kỷ luật xử lý

Với MANUAL, phải đảm bảo **mọi nhánh thành công, lỗi có thể hồi phục, lỗi cố định và shutdown** đều có cách ACK/NACK được kiểm soát.

Nếu handler không ACK, **unacked** sẽ tăng cho tới khi đụng prefetch; broker ngừng giao thêm delivery cho consumer trong khi queue ready vẫn có thể tăng. Nếu channel/connection đóng, các delivery chưa ACK có thể được broker giao lại theo chính sách, dẫn đến xử lý trùng.

Khi xử lý bất đồng bộ, không truyền tham chiếu AMQP channel/delivery tag tùy tiện qua nhiều thread và kỳ vọng ACK luôn an toàn. Tính hợp lệ, vòng đời channel và cơ chế phối hợp phải được kiểm chứng theo Spring AMQP/RabbitMQ client thực tế.

### 6.4. Batch size và transaction ảnh hưởng thời điểm ACK

Với SMLC, một số cấu hình **batchSize**, transaction hoặc consumer batching có thể khiến ACK được thực hiện theo đợt thay vì từng delivery. Tùy phiên bản/cấu hình, container có thể điều chỉnh prefetch sao cho không nhỏ hơn batch size cần thiết.

Vì vậy khi nói “prefetch = 10 nên mỗi message được ACK ngay sau handler” là suy luận sai. Cần biết **acknowledge mode, batch size, channelTransacted, advice chain và logic container**. Transaction DB của handler vẫn có phạm vi riêng; không được đồng nhất với transaction/channel ACK của RabbitMQ.

## 7. Concurrency × prefetch: tác động tới throughput và latency

Giả sử thời gian xử lý trung bình của handler là **T giây/message**, có **N consumer** thực sự xử lý độc lập, bỏ qua các giới hạn khác. Một ước lượng lạc quan về thông lượng là:

~~~text
Throughput tối đa do handler giới hạn ≈ N / T (message/giây)
~~~

Nếu mỗi message mất khoảng **0,2 giây**, một consumer tuần tự có thể xử lý khoảng **5 message/giây** và bốn consumer có thể đạt khoảng **20 message/giây**, *nếu* database, broker và CPU cho phép. Đổi prefetch từ 10 thành 100 **không làm thời gian xử lý một message giảm từ 0,2 giây**.

| Điều chỉnh | Có thể cải thiện | Có thể làm xấu |
| --- | --- | --- |
| Tăng prefetch | Giảm thời gian đợi delivery khi handler nhanh | Memory, unacked, công bằng, redelivery burst |
| Tăng concurrent consumers | Tăng xử lý song song | DB contention, thứ tự xử lý, connection/channel load |
| Tăng executor threads downstream | Giảm latency gọi vào channel trong một số mô hình | ACK sớm, backlog nội bộ, lỗi bất đồng bộ |
| Giảm prefetch | Công bằng, giảm số message giữ trước | Throughput thấp nếu ACK/network latency đáng kể |
| Batch xử lý | Giảm overhead/transaction cost tùy nghiệp vụ | Tăng thời gian giữ delivery, độ phức tạp rollback/ACK |

### 7.1. Tính công bằng giữa consumer

Hai consumer cùng queue: worker A xử lý mất 2 giây/message, worker B mất 20 ms/message. Nếu prefetch cao, worker A có thể giữ một lượng lớn delivery chưa ACK trong khi B đã xử lý hết phần việc của mình. Khi giảm prefetch, broker có nhiều cơ hội giao công việc tiếp cho B sau mỗi ACK.

**Fair dispatch** không đơn giản là bật một cờ “đúng/sai”. Nó phụ thuộc prefetch, thời gian xử lý, số consumer, requeue, queue policy và lịch delivery. Cần đo các consumer cụ thể thay vì chỉ xem số message tổng trong queue.

### 7.2. Thứ tự xử lý không được đảm bảo chỉ bằng một queue

Khi có nhiều consumer, prefetch lớn, retry/requeue hoặc handler không đồng bộ, **thứ tự hoàn tất nghiệp vụ** có thể khác thứ tự publish. Nếu OrderCreated phải được áp dụng trước OrderCancelled cho cùng orderId, cần sequence/version và idempotency ở lớp domain hoặc cơ chế phân luồng có thứ tự phù hợp.

Prefetch = 1 **không tự bảo đảm thứ tự toàn cục** khi nhiều consumer đang hoạt động.

## 8. Chọn giá trị ban đầu và đo thay vì đoán

Không có giá trị prefetch “chuẩn” cho tất cả hệ thống. Có thể bắt đầu bằng một cấu hình vừa phải trong test, sau đó điều chỉnh theo workload thực tế:

1. **Đo baseline:** thời gian handler p50/p95/p99, size payload, ready/unacked, consumer count, tốc độ ACK.
2. **Chọn ACK semantics:** người dùng cần điều gì được hoàn tất trước ACK? Có side effect không?
3. **Giới hạn concurrency:** năng lực DB, HTTP downstream, pool, CPU và connection/channel của RabbitMQ.
4. **Thử một prefetch nhỏ đến vừa:** đo throughput và độ công bằng giữa consumer.
5. **Tăng từng bước có kiểm soát:** theo dõi unacked, heap, GC, latency và redelivery khi kill consumer.
6. **Kiểm tra lỗi:** poison message, downstream timeout, broker reconnect, shutdown.
7. **Ghi cấu hình đã chứng minh:** gắn với khối lượng, kích thước message và mục tiêu SLA; không chuyển nguyên giá trị mẫu sang môi trường khác.

**Một kết quả thử tải chỉ có giá trị với workload và điều kiện đi kèm.** Nên ghi rõ số producer, loại exchange/queue, consumer concurrency, payload size, message converter, DB pool, prefetch, batch, ACK mode và cấu hình retry.

## 9. Ví dụ Java DSL: AMQP inbound với SMLC và prefetch

Ta tạo luồng nhận sự kiện **OrderCreated** một chiều:

~~~text
RabbitMQ direct exchange: orders.events
  └── routing key: orders.created
       └── durable queue: orders.created.q
            └── SimpleMessageListenerContainer
                 ├── acknowledgeMode = AUTO
                 ├── prefetchCount = 16
                 ├── concurrentConsumers = 2
                 └── maxConcurrentConsumers = 4
                      └── AMQP inbound channel adapter
                           └── DirectChannel / service activator
~~~

Ví dụ còn cấu hình **dead-letter exchange/queue** cho message bị từ chối không requeue, tránh một poison message làm vòng lặp vô hạn. Đây là **chính sách minh họa**, không có nghĩa mọi lỗi tạm thời nên bỏ qua retry.

### 9.1. Dependencies

Trong Spring Boot, cần các module tương thích với phiên bản được Spring Boot BOM quản lý:

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
</dependencies>
~~~

Môi trường thực hành phải có RabbitMQ broker, ConnectionFactory cấu hình host, port, virtual host và quyền phù hợp. Không để thông tin đăng nhập thật trong code; dùng biến môi trường hoặc secret manager. Cần tạo topology tại đúng virtual host.

### 9.2. Khai báo exchange, queue, binding và dead-letter queue

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderAmqpTopology {

    public static final String EVENTS_EXCHANGE = "orders.events";
    public static final String EVENTS_ROUTING_KEY = "orders.created";
    public static final String INBOUND_QUEUE = "orders.created.q";

    public static final String DEAD_EXCHANGE = "orders.dead.exchange";
    public static final String DEAD_ROUTING_KEY = "orders.dead";
    public static final String DEAD_QUEUE = "orders.created.dlq";

    @Bean
    public DirectExchange ordersExchange() {
        return new DirectExchange(EVENTS_EXCHANGE, true, false);
    }

    @Bean
    public Queue ordersQueue() {
        return QueueBuilder.durable(INBOUND_QUEUE)
            .deadLetterExchange(DEAD_EXCHANGE)
            .deadLetterRoutingKey(DEAD_ROUTING_KEY)
            .build();
    }

    @Bean
    public Binding ordersBinding(
            Queue ordersQueue, DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersQueue)
            .to(ordersExchange)
            .with(EVENTS_ROUTING_KEY);
    }

    @Bean
    public DirectExchange ordersDeadExchange() {
        return new DirectExchange(DEAD_EXCHANGE, true, false);
    }

    @Bean
    public Queue ordersDeadQueue() {
        return QueueBuilder.durable(DEAD_QUEUE).build();
    }

    @Bean
    public Binding ordersDeadBinding(
            Queue ordersDeadQueue,
            DirectExchange ordersDeadExchange) {
        return BindingBuilder.bind(ordersDeadQueue)
            .to(ordersDeadExchange)
            .with(DEAD_ROUTING_KEY);
    }
}
~~~

**Ý nghĩa:** Producer publish đến exchange **orders.events** với routing key **orders.created**. Broker định tuyến vào **orders.created.q**. Khi delivery bị reject/NACK với **requeue=false**, broker có thể dead-letter tới **orders.dead.exchange** rồi route sang **orders.created.dlq**.

**Cảnh báo topology:** Spring bean chỉ mô tả tài nguyên. RabbitAdmin/AmqpAdmin phải được bật và có quyền, hoặc topology phải do hạ tầng provision. Nếu broker đã có queue cùng tên nhưng arguments khác, redeclare có thể bị từ chối. Không thay đổi cấu hình production bằng cách khởi động lại ứng dụng một cách tùy tiện.

### 9.3. SMLC với prefetch và consumer concurrency

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersListenerConfiguration {

    @Bean
    public SimpleMessageListenerContainer ordersListenerContainer(
            ConnectionFactory connectionFactory) {

        SimpleMessageListenerContainer container =
            new SimpleMessageListenerContainer(connectionFactory);

        container.setQueueNames(OrderAmqpTopology.INBOUND_QUEUE);
        container.setConcurrentConsumers(2);
        container.setMaxConcurrentConsumers(4);
        container.setPrefetchCount(16);
        container.setAcknowledgeMode(AcknowledgeMode.AUTO);

        // Demo: loi lan toi container se bi reject khong requeue.
        // Queue phai co DLX/DLQ neu muon giu message loi.
        container.setDefaultRequeueRejected(false);

        return container;
    }
}
~~~

**Phân tích cấu hình:**

| Thiết lập | Giá trị ví dụ | Điều cần hiểu |
| --- | ---: | --- |
| **concurrentConsumers** | 2 | Số consumer cơ sở ban đầu của SMLC |
| **maxConcurrentConsumers** | 4 | Giới hạn trên khi thuật toán tăng consumer áp dụng |
| **prefetchCount** | 16 | Cửa sổ delivery chưa ACK cho mỗi consumer theo QoS thông thường |
| **acknowledgeMode** | AUTO | Container quản lý ACK sau kết quả callback |
| **defaultRequeueRejected** | false | Lỗi lan tới container có thể bị reject không requeue, thay vì gửi lại vô hạn |

Với 2 consumer đang hoạt động, mức in-flight lý thuyết có thể tới khoảng **32 delivery chưa ACK**. Nếu SMLC tăng lên 4 consumer, có thể tới khoảng **64 delivery**. Đây không phải số message luôn hiện hữu hay số thread nghiệp vụ tối đa; các giới hạn batch, transaction, QoS và xử lý thực tế có thể ảnh hưởng.

**defaultRequeueRejected(false) không phải retry policy đầy đủ.** Nó có thể khiến lỗi database tạm thời bị dead-letter ngay nếu chưa có cơ chế retry phù hợp. Với hệ thống thực, phải phân loại lỗi, giới hạn retry/backoff và thiết kế việc chuyển sang DLQ theo chính sách.

### 9.4. Nối container vào Spring Integration

~~~java
import org.springframework.amqp.rabbit.listener.SimpleMessageListenerContainer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrdersInboundIntegrationConfiguration {

    @Bean
    public MessageChannel rabbitOrders() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow ordersInboundFlow(
            SimpleMessageListenerContainer ordersListenerContainer) {

        return IntegrationFlow
            .from(Amqp.inboundAdapter(ordersListenerContainer))
            .channel("rabbitOrders")
            // Handler dung bo, giu exception trong chuoi goi listener.
            .handle(String.class, (payload, headers) -> {
                String[] fields = payload.split("\\|", -1);
                if (fields.length != 3
                        || !fields[0].matches("[A-Za-z0-9_-]{1,80}")
                        || !fields[1].matches("[A-Za-z0-9_-]{1,80}")
                        || !fields[2].matches("[0-9]+")) {
                    throw new IllegalArgumentException(
                        "Payload phai co dang eventId|orderId|totalVnd");
                }

                long totalVnd = Long.parseLong(fields[2]);
                if (totalVnd <= 0) {
                    throw new IllegalArgumentException(
                        "totalVnd phai lon hon 0");
                }

                System.out.println(
                    "Received " + fields[0]
                        + " for order " + fields[1]
                        + ", totalVnd=" + totalVnd);

                // Inbound mot chieu: khong tra business reply.
                return null;
            })
            .get();
    }
}
~~~

Các lớp cấu hình ở trên là **những file Java riêng**. Chúng minh họa việc AMQP inbound adapter nhận **listener container đã cấu hình trước**, thay vì tạo một container mặc định mà không biết prefetch/concurrency thực tế.

**Quan trọng về ACK:** Handler trong ví dụ được gọi đồng bộ trên flow sau adapter. Nếu exception được phép lan ngược tới listener/container, cơ chế reject không requeue có thể đưa message tới DLQ như thiết kế. Tuy nhiên nếu thêm một **errorChannel** hoặc error handler xử lý exception và kết thúc thành công, container có thể thấy callback thành công rồi ACK. Vì vậy phải kiểm tra hành vi ACK cuối cùng, không chỉ dựa vào việc handler có ném exception hay không.

**Không dùng mẫu này để tuyên bố đã xử lý đơn hàng thành công.** Handler chỉ parse rồi in log. Production cần service activator ghi database, eventId làm khóa idempotency, transaction, xử lý lỗi và phương án kiểm soát schema chuẩn.

### 9.5. Vì sao không tăng prefetch trước khi có idempotency?

Một handler đã commit DB nhưng tiến trình chết trước khi broker nhận ACK có thể khiến delivery được giao lại. Prefetch lớn làm tăng số delivery có khả năng đang in-flight khi connection bị mất. **Khả năng redelivery không biến message thành một event nghiệp vụ mới**: nên giữ eventId và lưu dấu đã xử lý.

Ví dụ, Consumer nhận lại **evt-1001** sau crash. Nếu database đã lưu Order O-1001 thì lần nhận mới phải nhận diện bản trùng và không tạo side effect lần hai. Có thể dùng unique constraint theo eventId hoặc bảng inbox trong cùng transaction nghiệp vụ.

## 10. Gửi message thử và xác minh prefetch

Với RabbitTemplate đã kết nối cùng virtual host:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class OrdersTestPublisher {
    private final RabbitTemplate rabbitTemplate;

    public OrdersTestPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void sendOne() {
        rabbitTemplate.convertAndSend(
            OrderAmqpTopology.EVENTS_EXCHANGE,
            OrderAmqpTopology.EVENTS_ROUTING_KEY,
            "evt-1001|O-1001|150000");
    }
}
~~~

Khi topology, broker connection, converter và listener đúng, payload kiểu String sẽ đến handler. Nếu producer gửi **JSON** hoặc **binary** với converter khác, handler String trong ví dụ có thể không tương thích; cần cấu hình message converter hoặc transformer theo hợp đồng trước khi xử lý.

### 10.1. Kiểm tra đường nhận

1. Tạo broker test và xác nhận exchange/queue/bindings tồn tại.
2. Khởi động ứng dụng có listener container ở trên.
3. Publish message **evt-1001|O-1001|150000**.
4. Quan sát handler in thông tin và broker có tiến độ delivery/ACK.
5. Tạm dừng listener rồi gửi nhiều message; broker sẽ giữ queue ready theo chính sách. Bật lại và quan sát queue được tiêu thụ.
6. Gửi một message sai như **bad-message**: khi lỗi lan tới container, chính sách reject không requeue cùng DLX phải đưa message đến DLQ thay vì lặp vô hạn.
7. Giả lập handler chậm trong test để quan sát unacked. Thay đổi prefetch một cách có kiểm soát và ghi lại kết quả.

### 10.2. Vì sao cần làm chậm handler trong bài test QoS?

Khi handler hoàn tất rất nhanh, ACK liên tục giải phóng quota, số unacked trong RabbitMQ management có thể luôn nhỏ dù prefetch cao. Đó không phải bằng chứng prefetch đã bị bỏ qua.

Để quan sát cửa sổ QoS, có thể chạy một **test handler có độ trễ được kiểm soát** hoặc một downstream test service. Trong test độc lập, điều chỉnh latency và số consumer rồi so sánh **unacked peak**, **ready queue depth**, **ACK rate** và thời gian hoàn tất toàn bộ lô.

Không thêm sleep nhân tạo vào handler production để “ổn định prefetch”; đó chỉ là dụng cụ mô phỏng khi test.

### 10.3. Thử nghiệm crash và redelivery

1. Publish một lô event có ID riêng.
2. Cho listener nhận một phần nhưng chưa ACK hết (dùng môi trường test được điều khiển).
3. Đột ngột dừng consumer process/connection thay vì graceful shutdown.
4. Khởi động lại consumer; kiểm tra những delivery chưa ACK được broker xử lý/giao lại theo policy.
5. Đối chiếu **eventId đã áp dụng vào database** với **số lần nhận thực tế** để kiểm chứng idempotency.

Không dựa vào thứ tự delivery sau crash để suy luận thứ tự nghiệp vụ. Hành vi requeue, consumer concurrency và policy có thể thay đổi thứ tự xử lý.

## 11. Khi nào cần DirectMessageListenerContainer?

**DirectMessageListenerContainer** (DMLC) là lựa chọn khác khi cần mô hình dispatch trực tiếp và quản lý consumer theo queue.

Ví dụ cấu hình container ở Spring AMQP:

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.listener.DirectMessageListenerContainer;

// Minh hoa thay the SMLC, khong su dung dong thoi hai
// listener container cho cung queue neu muon test doc lap.
DirectMessageListenerContainer direct =
    new DirectMessageListenerContainer(connectionFactory);
direct.setQueueNames("orders.created.q");
direct.setConsumersPerQueue(2);
direct.setPrefetchCount(16);
direct.setAcknowledgeMode(AcknowledgeMode.AUTO);
~~~

Đây là **mẫu cấu hình để so sánh**, không phải đoạn mã đồng thời tạo thêm consumer thứ hai trong ứng dụng ví dụ. Khi muốn dùng DMLC trong Spring Integration, cấu hình endpoint sử dụng container này thay cho SMLC và xác minh API của phiên bản Spring Integration/Spring AMQP.

### 11.1. SMLC hay DMLC?

Hãy đánh giá theo:

- Loại thao tác listener: I/O chậm, CPU nặng, xử lý DB đồng bộ hay gọi downstream bất đồng bộ.
- Số lượng queue, consumers per queue, tần suất thay đổi topology và cách container quản lý consumer.
- Nhu cầu **dynamic scaling** của SMLC so với quản lý **consumersPerQueue** của DMLC.
- Cách thread pool và RabbitMQ Java client executor bị sử dụng.
- Tương tác giữa prefetch, ACK, batching và shutdown.
- Log, lỗi kết nối, timeout, hiệu năng theo benchmark **cùng workload**.

Không kết luận chỉ từ việc tên có chữ **Direct** rằng DMLC đồng nghĩa Spring Integration **DirectChannel**. Một bên là listener container RabbitMQ, bên còn lại là loại MessageChannel nội bộ.

## 12. Retry, requeue và dead-letter cần phối hợp với prefetch

Khi handler thất bại, số message đang unacked và cách container xử lý lỗi quyết định backlog tiếp tục ra sao:

~~~mermaid
flowchart TD
    Q["RabbitMQ queue"] --> L["Listener container"]
    L --> A{"Handler xử lý?"}
    A -->|"Thành công"| ACK["ACK, giải phóng quota"]
    A -->|"Lỗi tạm thời"| RET["Retry có giới hạn + backoff"]
    RET --> A
    A -->|"Lỗi cố định / hết retry"| NACK["Reject/NACK không requeue"]
    NACK --> DX["Dead-letter exchange nếu cấu hình"]
    DX --> DQ["Dead-letter queue"]
~~~

### 12.1. Poison message và vòng lặp requeue

Một message sai JSON hoặc thiếu trường bắt buộc có thể làm handler ném lỗi ở mọi lần nhận. Nếu container mặc định requeue mỗi khi lỗi, broker có thể liên tục giao đúng message này, gây nóng CPU, tăng redelivery và làm queue có tiến độ rất thấp.

Đối với lỗi dữ liệu cố định, nên:

- Xác thực payload theo schema.
- Cách ly message lỗi hoặc reject không requeue và đưa vào DLQ phù hợp.
- Ghi event ID, nguyên nhân và số lần xử lý đã thử.
- Có quy trình sửa dữ liệu/replay có kiểm soát; không retry vô hạn.

### 12.2. Lỗi tạm thời và retry

Khi database hoặc API downstream lỗi trong thời gian ngắn, retry giới hạn có backoff có thể phù hợp. Cần quyết định **retry trong listener** hay **đưa về queue với chính sách delay/retry**; mỗi cách có tác động tới prefetch:

- Retry trong listener giữ delivery **chưa ACK** lâu hơn, chiếm một slot prefetch.
- Requeue ngay có thể tạo vòng lặp delivery nóng nếu đích vẫn lỗi.
- Retry qua queue delay/DLX hoặc cơ chế lưu tiến độ riêng đòi hỏi thiết kế topology và khả năng xử lý trùng.

**Prefetch cao + retry chậm** có thể khiến rất nhiều delivery nằm unacked cùng lúc; thay đổi một tham số mà không đo ACK latency, consumer memory và backlog là nguy hiểm.

### 12.3. Không nhầm consumer DLQ với publisher return

Publisher gửi message vào một exchange nhưng không có binding phù hợp: đó là **unroutable**. Cơ chế **mandatory/returns** hoặc alternate exchange giải quyết phía producer. Delivery đã vào queue nhưng consumer reject không requeue: có thể được **dead-letter**. Hai tình huống xảy ra ở **hai giai đoạn khác nhau**.

### 12.4. Exception và errorChannel trong Spring Integration

Với DirectChannel, lỗi handler có thể lan về listener. Nhưng nếu endpoint được cấu hình **errorChannel** và lỗi được chuyển thành ErrorMessage, container có thể không còn thấy exception như lỗi callback.

Vì vậy, khi thiết kế ACK/NACK:

1. Kiểm tra exception có thực sự lan tới Spring AMQP container hay không.
2. Xác định error flow có kết thúc lỗi hay trả về bình thường.
3. Kiểm tra listener error handler/advice có retry hay chuyển đổi exception không.
4. Xác nhận broker ACK/NACK thực tế trong integration test.

**Không nên coi “handler đã log error” là bằng chứng broker sẽ tự redeliver.**

## 13. Dynamic scaling của SMLC: tăng consumer đúng lúc

**SimpleMessageListenerContainer** có thể tăng/giảm số consumer trong khoảng đã cấu hình khi workload thay đổi. Các tham số liên quan có thể gồm:

- **concurrentConsumers:** mức cơ sở.
- **maxConcurrentConsumers:** giới hạn trên.
- **consecutiveActiveTrigger** và **consecutiveIdleTrigger:** ngưỡng hoạt động/rảnh qua những chu kỳ quan sát.
- **startConsumerMinInterval** và **stopConsumerMinInterval:** khoảng tối thiểu giữa những lần thay đổi số consumer.
- **receiveTimeout**, **batchSize** và cách đánh giá chu kỳ active/idle.

Những tham số này tác động lẫn nhau; thuật toán chính xác phải xem theo phiên bản Spring AMQP. **Không nên chỉ giảm startConsumerMinInterval rồi kỳ vọng container ngay lập tức đạt maxConcurrentConsumers**. Điều kiện active/idle, nguồn message, timeout và khả năng downstream vẫn quyết định việc scale.

### 13.1. Scale được consumer không đồng nghĩa scale được database

Giả sử mỗi consumer mở một transaction cập nhật tồn kho. Nếu database connection pool chỉ đủ cho số tác vụ giới hạn, tăng consumer từ 4 lên 32 có thể gây:

- Tăng số thread chờ DB connection.
- Tăng lock contention.
- Tăng thời gian xử lý và số delivery unacked.
- Tăng retry khi transaction timeout.
- Làm độ trễ p95/p99 xấu hơn dù consumer count cao hơn.

Nên đặt **maxConcurrentConsumers** dựa trên năng lực downstream và số lượng application instances, chứ không chỉ số core CPU.

### 13.2. Scale-out và số consumer tổng cộng

Nếu có **3 instance ứng dụng**, mỗi instance có thể tăng từ 2 đến 4 consumer, toàn dịch vụ có thể chạy khoảng **6 đến 12 consumer** trên cùng queue. Với prefetch **16**, số delivery unacked lý thuyết trong các consumer của toàn nhóm có thể lớn hơn nhiều so với cấu hình trên một instance.

Khi scale-out, hãy tính **tổng consumer và prefetch trên tất cả instance**, không chỉ một JVM. Các giới hạn network, RabbitMQ channels/connections, database pool tổng và yêu cầu thứ tự cũng phải được xem xét.

### 13.3. Không mặc định tự động mở rộng mọi container

SMLC hỗ trợ mô hình điều chỉnh concurrency động theo cấu hình. DMLC sử dụng cơ chế quản lý consumer khác với **consumersPerQueue**. Khi muốn thay đổi một container đang chạy, phải xác minh các setter hoặc cấu hình runtime được phiên bản thư viện hỗ trợ và thời điểm thay đổi có hiệu lực.

## 14. Vòng đời container, connection và graceful shutdown

Listener container và AMQP endpoint thường tham gia cơ chế **Lifecycle/SmartLifecycle** của Spring: **start()**, **stop()**, **isRunning()**, **autoStartup** và **phase** theo bean/configuration.

### 14.1. Những mốc cần phân biệt

| Quan sát | Có thể suy ra | Chưa thể kết luận |
| --- | --- | --- |
| Container isRunning = true | Container đang ở trạng thái vòng đời chạy | Broker kết nối khỏe, queue tồn tại, business handler không lỗi |
| RabbitMQ consumer count tăng | Broker thấy consumer đăng ký | Throughput đạt SLA hoặc side effect đã commit |
| Ready = 0 | Không còn message đang chờ delivery ở thời điểm đo | Không có unacked hay task đang xử lý |
| Unacked = 0 | Không thấy delivery đang chờ ACK theo metric đó | Không có message đang xử lý ở channel bất đồng bộ |
| Handler trả về | Callback đã đạt một mốc xử lý | Mọi hệ thống ngoài đã hoàn tất tác vụ kéo dài |

**isRunning() là trạng thái vòng đời**, còn broker connection, queue metrics và business outcome là các góc nhìn khác nhau. Một listener có thể đang liên tục cố reconnect mà vẫn chưa xử lý được message.

### 14.2. Khi dừng ứng dụng

Một quy trình graceful shutdown tham khảo:

1. Ngừng nguồn phát thêm công việc mới nếu ứng dụng sở hữu cả producer.
2. Yêu cầu listener container ngừng tiếp nhận delivery theo cơ chế hỗ trợ.
3. Theo dõi **in-flight/unacked**, handler active và các transaction DB đang chạy.
4. Để những tác vụ đã nhận hoàn tất trong giới hạn vận hành hoặc dựa vào cơ chế requeue/redelivery/idempotency khi không thể hoàn tất.
5. Ngừng downstream và đóng ConnectionFactory/tài nguyên chia sẻ theo vòng đời Spring.
6. Khi restart, xác minh backlog, số consumer, requeue, retry và business checkpoint.

**stop() không mặc nhiên có nghĩa mọi message đã drain hoàn toàn**. Container có shutdown timeout và hành vi khi listener vẫn xử lý; nếu connection/channel bị đóng khi còn delivery chưa ACK, broker có thể giao lại. Vì vậy hãy kiểm thử **shutdown dưới tải**, không chỉ dừng ứng dụng khi queue rỗng.

### 14.3. Sự cố mất connection và tác động của prefetch

Nếu consumer đang có nhiều delivery unacked và connection đứt, RabbitMQ có thể đưa các delivery chưa ACK trở lại trạng thái có thể giao lại theo chính sách. Consumer mới có thể nhận lại cả những message từng được handler xử lý một phần.

Prefetch càng cao, số delivery có thể đang giữ trước càng lớn. Nhưng **giảm prefetch về 1 không loại bỏ hoàn toàn trùng nghiệp vụ**: vẫn có khoảng trống giữa DB commit và ACK.

### 14.4. Không đóng connection factory dùng chung tùy tiện

Nhiều endpoint có thể dùng chung một **CachingConnectionFactory**: inbound listener, outbound RabbitTemplate, AMQP gateway. Dừng một endpoint không đồng nghĩa ứng dụng nên đóng connection factory dùng chung ngay lập tức. ConnectionFactory thường do ApplicationContext quản lý; đóng sai thời điểm có thể làm hỏng những luồng khác.

## 15. Quan sát: metric nào chứng minh cấu hình đang tốt?

Muốn điều chỉnh prefetch, cần đo cả **broker**, **container**, **channel** và **nghiệp vụ**:

| Lớp | Số liệu nên thu thập | Câu hỏi được trả lời |
| --- | --- | --- |
| RabbitMQ queue | ready, unacked, total, message age | Backlog ở đâu, bao nhiêu message đã giao nhưng chưa ACK? |
| RabbitMQ consumer | consumer count, delivery rate, ACK/NACK/requeue rate | Có đủ consumer và chúng có tiến độ không? |
| Listener container | Số consumer hiện tại, reconnect, handler failures, trạng thái running | Container đang làm việc hay đang gặp lỗi kết nối? |
| JVM/thread | Thread count, CPU, heap, GC pause, executor queue | Prefetch/concurrency có gây áp lực tài nguyên không? |
| Handler | p50/p95/p99 latency, DB latency, transaction timeout | Nút thắt nghiệp vụ là gì? |
| Error flow | retry attempts, poison message count, DLQ ingress | Lỗi có bị requeue liên tục hoặc cách ly sai không? |
| Nghiệp vụ | unique eventId processed, duplicate skip count, completion rate | Bao nhiêu nghiệp vụ thực sự hoàn tất? |

### 15.1. Diễn giải một số hình thái dữ liệu

**Ready tăng, unacked thấp, consumer count thấp:** có thể thiếu consumer, listener không chạy, prefetch thấp hoặc các consumer đang xử lý chậm và ít delivery. Kiểm tra log/reconnect và throughput từng consumer.

**Ready cao, unacked gần N × P:** consumer đã lấp đầy cửa sổ prefetch. Cần kiểm tra handler latency, downstream hoặc ACK đang chậm; tăng prefetch tiếp chưa chắc ích lợi.

**Unacked cao nhưng CPU thấp:** có thể đợi DB/network, quên MANUAL ACK, transaction treo hoặc executor đang chờ. Đừng tự kết luận chỉ do RabbitMQ.

**Redelivery/requeue rất cao và business success thấp:** nghi ngờ poison message, lỗi downstream hoặc policy requeue không có điểm dừng.

**ACK rate cao nhưng business outcome thấp:** xem xét liệu ACK diễn ra trước khi xử lý bất đồng bộ hoàn tất, hoặc error flow đã hấp thụ exception.

### 15.2. Prefetch không phải cơ chế flow-control toàn tuyến

RabbitMQ prefetch giới hạn số delivery chưa ACK theo consumer/QoS. Nó **không giới hạn** tổng message do producer đưa vào exchange, số sự kiện đang tồn ở các queue khác hay số tác vụ đã được consumer ACK rồi đưa vào executor nội bộ.

Để kiểm soát overload toàn tuyến, có thể cần:

- Rate limit hoặc backpressure phía producer.
- Channel/executor capacity giới hạn.
- Cấu hình consumer concurrency dựa trên downstream.
- Bounded retry/backoff.
- Lưu bền trạng thái nếu chấp nhận ACK tại một ranh giới nội bộ trước khi nghiệp vụ cuối hoàn tất.

## 16. Kịch bản điều chỉnh prefetch dựa trên dữ liệu

Giả sử một ứng dụng có các yêu cầu **minh họa**, chưa phải số đo của hệ thống thật:

| Yếu tố | Giả định |
| --- | --- |
| Producer | 120 message/giây trong giờ cao điểm |
| Handler | Trung bình 50 ms/message, thực hiện đồng bộ |
| Số application instances | 2 |
| Consumer mỗi instance | 2 (tổng 4) |
| Prefetch ban đầu | 10 mỗi consumer |
| Payload | 4 KiB trung bình |
| ACK mode | AUTO |

Nếu mỗi consumer xử lý tuần tự 50 ms/message và mọi thành phần khác đủ năng lực, tổng năng lực lý tưởng khoảng **4 / 0,05 = 80 message/giây**, thấp hơn 120 message/giây của producer. **Tăng prefetch từ 10 lên 100 không thể làm bốn consumer xử lý nhiều hơn 80 message/giây chỉ nhờ giữ trước nhiều delivery.**

Các hướng cải thiện cần kiểm chứng:

1. Giảm thời gian handler/DB transaction nếu có thể.
2. Tăng số consumer trong giới hạn của DB và broker, đo p95/p99 sau thay đổi.
3. Bố trí thêm instance nếu hạ tầng có thể chịu tải.
4. Điều chỉnh prefetch khi có bằng chứng consumer đang chờ delivery quá lâu hoặc mất công bằng.
5. Chấp nhận backlog có kiểm soát và mục tiêu thời gian xử lý hết hàng nếu đây là tải đỉnh ngắn hạn.

### 16.1. So sánh ba cấu hình để thử

| Cấu hình thử | Tổng consumer | Prefetch mỗi consumer | Cửa sổ unacked ước lượng | Giả thuyết cần đo |
| --- | ---: | ---: | ---: | --- |
| A | 4 | 1 | ~4 | Công bằng, ít message giữ trước nhưng có thể nhiều thời gian chờ ACK |
| B | 4 | 10 | ~40 | Giảm thời gian chờ delivery, không tăng song song nghiệp vụ |
| C | 8 | 10 | ~80 | Có thể tăng throughput nếu DB/CPU cho phép; tăng số delivery in-flight |

Sau mỗi phép thử, so sánh **throughput hoàn tất**, **ready/unacked**, **memory**, **latency p95/p99**, **retry/DLQ** và khả năng phục hồi sau khi kill một consumer. Không chọn cấu hình chỉ theo việc ready giảm nhanh nhất mà bỏ qua tính đúng đắn nghiệp vụ.

### 16.2. Workload không đều

Nếu 90% message xử lý trong 5 ms nhưng 10% mất vài giây, prefetch và nhiều consumer có thể phân phối công việc rất khác workload đồng đều. Nên test **phân bố latency thực**, message lớn/nhỏ trộn nhau và các lỗi theo tỷ lệ thực tế, không chỉ gửi một loại message được handler no-op.

## 17. Ma trận kiểm thử trước production

| Bài thử | Thao tác | Kết quả cần xác minh |
| --- | --- | --- |
| Kết nối bình thường | Start broker/consumer, publish hợp lệ | Handler nhận dữ liệu và broker ghi nhận ACK phù hợp |
| Không có message | Giữ queue trống | Container vẫn hoạt động, không tự coi là lỗi |
| Prefetch thấp | Prefetch 1, handler chậm | Unacked theo QoS phù hợp, không nhận trước quá cửa sổ |
| Prefetch cao | Prefetch 32, handler chậm | Unacked tăng có giới hạn, đo heap và latency |
| Nhiều consumer | 2 rồi 4 consumer | Kiểm tra tổng in-flight, throughput và fairness |
| SMLC autoscale | Tăng/giảm tải theo thời gian | Consumer count thay đổi trong khoảng cấu hình khi điều kiện thỏa |
| Manual ACK quên xác nhận | Test riêng, không dùng production | Unacked tăng và khả năng nhận mới bị giới hạn |
| Poison message | Payload sai schema | Retry/DLQ theo chính sách, không requeue vô hạn |
| Downstream timeout | DB/API lỗi tạm thời | Retry có giới hạn và ACK/NACK đúng |
| Async channel | Đổi DirectChannel sang ExecutorChannel trong test | Xác minh thời điểm ACK và lỗi worker sau khi listener trả về |
| Consumer crash | Kill một instance khi unacked | Redelivery theo broker, nghiệp vụ không tạo side effect trùng |
| Broker restart | Ngắt và mở lại broker test | Container reconnect, backlog xử lý theo policy |
| Scale-out | Chạy nhiều instance cùng queue | Message được chia giữa consumer; không mặc nhiên broadcast |
| Shutdown có tải | Dừng ứng dụng khi handler đang chạy | Tác vụ hoàn tất hoặc phục hồi, không đánh dấu sai tiến độ |
| DLX thiếu binding | Reject message sai | Phát hiện lỗi topology, không khẳng định DLQ sẽ tự nhận |

### 17.1. Checklist thực nghiệm

Trước khi tăng prefetch ở production, cần ghi lại:

1. **Mục tiêu:** tăng throughput, giảm latency hay cải thiện fairness?
2. **Định dạng và kích thước:** payload String/JSON/bytes, trung bình và p99.
3. **Điểm ACK:** handler đồng bộ, batch, manual ACK hay errorChannel?
4. **Các ngưỡng:** consumer count tối đa, DB pool, thread pool, heap, max connection.
5. **Phục hồi:** message chưa ACK khi crash có được xử lý lại idempotent không?
6. **Điểm báo động:** ready/unacked, retry, DLQ, consumer lag/age và business failures.
7. **Rollback cấu hình:** nếu latency hoặc memory tăng, có thể khôi phục prefetch/concurrency trước đó không?

## 18. Những sai lầm thường gặp

**“Prefetch = 100 tức là có 100 thread xử lý.”** Prefetch là cửa sổ delivery chưa ACK, không phải concurrency.

**“Tăng prefetch luôn tăng throughput.”** Khi handler/DB là nút thắt, chỉ làm tăng số message giữ trước.

**“Prefetch được áp chung một lần cho mọi consumer.”** RabbitMQ thường áp prefetch theo consumer; phải xét phạm vi QoS và tổng consumer.

**“SMLC và DMLC là cùng một container có hai tên.”** Chúng có thread model và cơ chế quản lý consumer khác nhau.

**“DMLC chính là DirectChannel.”** Một bên là listener container RabbitMQ, một bên là Spring Integration channel đồng bộ.

**“AMQP inbound adapter cần Pollers.fixedDelay giống File inbound.”** Message-driven listener thường nhận qua broker consumer/container, không cần poller đó.

**“AUTO ACK nghĩa là broker tự ACK khi giao message.”** Spring AMQP AUTO để container ACK theo kết quả callback, khác NONE.

**“Dùng ExecutorChannel không thay đổi giao nhận.”** Listener có thể ACK trước khi handler bất đồng bộ thực hiện xong.

**“Unacked = 0 nghĩa là tất cả nghiệp vụ đã xong.”** Có thể message đã ACK nhưng vẫn nằm trong queue nội bộ hoặc executor đang xử lý.

**“MANUAL ACK luôn an toàn hơn.”** Quên ACK có thể làm đầy cửa sổ prefetch; xử lý sai delivery tag/channel gây lỗi.

**“Mọi exception chắc chắn khiến broker requeue.”** ErrorChannel, retry advice, error handler và policy container có thể thay đổi kết quả.

**“DLQ tự tồn tại khi gọi setDefaultRequeueRejected(false).”** Phải cấu hình DLX, DLQ và binding thực tế; nếu không, message bị reject có thể không được giữ lại.

**“Prefetch = 1 bảo đảm exactly-once và thứ tự tuyệt đối.”** Redelivery, nhiều consumer và side effect ngoài broker vẫn tồn tại.

**“Đã có queue durable nên bỏ được idempotency.”** Message có thể bị giao lại khi consumer crash trước ACK; nghiệp vụ cần chống trùng.

**“Tăng consumer chỉ tác động trên một JVM.”** Trong triển khai nhiều instance, tổng consumer/prefetch cần cộng across toàn bộ nhóm.

## 19. Câu hỏi tự kiểm tra

1. Vai trò của RabbitMQ queue, Spring AMQP listener container và Spring Integration AMQP inbound adapter khác nhau ở đâu?
2. Vì sao message-driven adapter thông thường không cần Spring Integration Poller?
3. So sánh SMLC và DMLC theo thread model và cách cấu hình concurrency.
4. PrefetchCount = 20 với bốn consumer thường cho phép khoảng bao nhiêu delivery chưa ACK? Con số đó có phải throughput không?
5. Ready và unacked khác nhau thế nào? Khi nào ready = 0 nhưng nghiệp vụ chưa xử lý xong?
6. Vì sao prefetch = 1 có thể cải thiện fairness nhưng làm throughput giảm?
7. AUTO ACK, MANUAL ACK và NONE khác nhau thế nào về người chịu trách nhiệm xác nhận delivery?
8. Nếu handler đã commit DB nhưng tiến trình chết trước ACK, điều gì có thể xảy ra?
9. Vì sao chuyển DirectChannel sang ExecutorChannel có thể khiến listener ACK quá sớm?
10. Trong ví dụ Java DSL, những thiết lập nào quyết định concurrency và cửa sổ unacked?
11. defaultRequeueRejected(false) có tự tạo DLQ không? Những tài nguyên nào phải tồn tại?
12. Khi handler lỗi database tạm thời, tại sao reject thẳng vào DLQ có thể không phải chính sách tốt nhất?
13. Khi có 3 instance, mỗi instance chạy 4 consumer và prefetch 16, cần xem xét tổng in-flight như thế nào?
14. Nếu unacked tăng đến sát quota nhưng CPU thấp, nên kiểm tra những thành phần nào?
15. Tại sao tăng prefetch không tăng tốc một handler đang bị DB giới hạn?
16. Khi container stop hoặc RabbitMQ connection đứt, delivery chưa ACK có thể được xử lý như thế nào?
17. Muốn bảo đảm mỗi dịch vụ Warehouse và Analytics đều nhận một event, dùng hai queue hay hai consumer cùng queue?
18. Những metric và test nào giúp quyết định cấu hình prefetch đã đủ tốt cho production?
19. Vì sao cần kiểm tra errorChannel và retry advice trước khi kết luận container sẽ NACK khi handler ném exception?
20. Khi nghiệp vụ cần xử lý đúng một lần theo eventId, prefetch và ACK có thay thế được unique constraint/inbox table không?

## Tổng kết

**Message-driven listener container** là cầu nối nhận delivery của RabbitMQ để Spring Integration **AMQP inbound channel adapter** tạo Spring Message và gửi vào **MessageChannel**. **SimpleMessageListenerContainer** và **DirectMessageListenerContainer** có mô hình quản lý consumer khác nhau; cả hai đều cần hiểu ACK, concurrency và vòng đời kết nối trước khi vận hành.

**Prefetch** giới hạn số delivery **chưa ACK** mà broker có thể cấp trước theo QoS thường áp dụng cho từng consumer. Nó không phải số thread, không phải giới hạn backlog toàn queue và không tự tăng năng lực handler. Cấu hình tốt cần cân bằng **throughput, fairness, memory, số consumer, kích thước message và độ trễ downstream**. Đặc biệt phải xác định **điểm ACK** khi dùng DirectChannel hoặc channel bất đồng bộ, phân loại lỗi để retry/DLQ đúng cách và triển khai idempotency khi message có thể redeliver. Chỉ nên tăng prefetch dựa trên số liệu ready/unacked, ACK rate, độ trễ, lỗi và kết quả nghiệp vụ đã kiểm chứng trong test tải và test sự cố.
