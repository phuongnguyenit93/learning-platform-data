# Tính số partition, instance và concurrency theo tải

Muốn mở rộng một ứng dụng Spring Cloud Stream, cần trả lời ba câu hỏi liên quan nhưng khác nhau: cần bao nhiêu partition để chia dữ liệu, cần bao nhiêu instance để chạy ứng dụng và mỗi instance cần bao nhiêu consumer đồng thời. Nếu chỉ tăng số pod mà broker không có đủ khả năng phân phối dữ liệu, các instance mới có thể không nhận thêm việc. Nếu tăng concurrency quá cao, database, connection pool hoặc CPU có thể trở thành nút thắt.

Cách sizing đáng tin cậy bắt đầu từ tải thực tế và phép đo trên một consumer worker. Sau đó tính số worker cần thiết, phân bổ worker vào instance, rồi kiểm tra giới hạn partition và khả năng của broker. Kafka, RabbitMQ và Pulsar có mô hình phân phối khác nhau nên không thể áp dụng một công thức partition duy nhất cho cả ba.

## 1. Phân biệt partition, instance và concurrency

| Khái niệm | Ý nghĩa | Điều khiển điều gì? |
|---|---|---|
| Partition | Phần dữ liệu độc lập của một topic hoặc luồng đã phân vùng | Khả năng chia tải, song song hóa và thứ tự trong phạm vi partition |
| Instance | Một tiến trình ứng dụng đang chạy, thường là một pod/container/VM | Tài nguyên CPU, RAM, network và fault isolation |
| Concurrency | Số consumer/listener có thể xử lý đồng thời trong một instance cho một binding | Số luồng xử lý message đồng thời trên mỗi instance |
| Worker slot | Một đơn vị xử lý message đồng thời được capacity test xác nhận | Tổng năng lực xử lý cần triển khai |
| Consumer group/subscription | Nhóm consumer cùng chia sẻ tiến độ xử lý một luồng | Cách broker phân phối message cho các consumer |

Ví dụ một ứng dụng có 12 pod và mỗi pod có concurrency 2 thì có tối đa 24 consumer slot cho binding đó. Con số này không có nghĩa ứng dụng luôn xử lý được 24 lần tải của một pod: hiệu năng còn phụ thuộc partition, key skew, thời gian xử lý, broker, database và giới hạn downstream.

Không đồng nhất partition với instance. Một partition có thể được một consumer xử lý; một instance có thể sở hữu nhiều partition; một instance cũng có thể có nhiều consumer thread. Quan hệ chính xác phụ thuộc binder và subscription mode.

## 2. Thu thập dữ liệu tải trước khi tính

Trước khi chọn số partition hoặc replica, cần đo ít nhất các thông số sau:

| Ký hiệu | Thông số | Cách lấy |
|---|---|---|
| λavg | Tốc độ event trung bình, event/giây | Broker metrics hoặc application counter |
| λpeak | Tốc độ event đỉnh trong cửa sổ tải phù hợp | Peak rate theo 1 phút, 5 phút hoặc cửa sổ nghiệp vụ |
| S | Thời gian một worker bận xử lý một event | Timer/benchmark, tách CPU time và thời gian chờ I/O |
| μworker | Throughput bền vững của một consumer slot | Load test ở latency và error rate mục tiêu |
| B | Backlog đang tồn tại | Kafka lag, RabbitMQ ready/unacked hoặc Pulsar backlog |
| Tdrain | Thời gian mong muốn để xử lý hết backlog | SLO vận hành |
| C | Concurrency trên mỗi instance | Cấu hình consumer binding và phép đo |
| I | Số instance ứng dụng | Deployment/HPA/replica count |
| P | Số partition hoặc đơn vị phân vùng | Topic/queue topology của broker |

Đừng chỉ dùng tốc độ trung bình. Hệ thống có thể nhận 200 event/giây trong phần lớn thời gian nhưng tăng lên 1.500 event/giây trong đợt chốt đơn. Sizing theo trung bình sẽ khiến backlog tăng trong giờ cao điểm.

Đo thời gian xử lý trên cùng loại payload và cùng dependency với production. Một event nhỏ chỉ kiểm tra cache không đại diện cho event phải gọi ba dịch vụ, ghi database và publish output. Nên đo p50/p95/p99, error rate, CPU, heap, database connection và broker lag trong cùng bài load test.

## 3. Tính số worker cần thiết

Có hai cách ước lượng. Cách thứ nhất dùng thời gian worker bị chiếm dụng; cách thứ hai dùng throughput thực đo.

### 3.1. Từ arrival rate và service time

Gọi:

- λpeak là tốc độ event cao điểm, event/giây.
- S là số giây một worker bận xử lý một event.
- ρ là mức sử dụng mục tiêu của worker, nhỏ hơn 1 để giữ headroom.
- W là số worker slot cần thiết.

Một worker xử lý tuần tự có năng lực lý thuyết khoảng 1/S event/giây. Nếu không muốn worker chạy sát 100% liên tục, dùng utilization mục tiêu:

    W = ceil((λpeak × S) / ρ)

Công thức này giả định mỗi worker xử lý một event tại một thời điểm và S là thời gian worker bị chiếm dụng. Nó là ước lượng ban đầu; load test vẫn cần xác nhận latency và throughput.

Ví dụ, luồng nhận 800 event/giây ở peak. Một consumer worker mất trung bình 40 ms để xử lý một event, tức S = 0,04 giây. Chọn utilization mục tiêu 65%:

    W = ceil((800 × 0,04) / 0,65)
      = ceil(32 / 0,65)
      = 50 worker slots

Một worker có throughput lý thuyết 25 event/giây, nhưng ở utilization 65% chỉ nên lập kế hoạch khoảng 16,25 event/giây. Năm mươi slot cung cấp năng lực mục tiêu khoảng 812,5 event/giây, vừa đủ tải 800 event/giây với headroom theo giả định trên.

ρ không phải một con số bắt buộc. Với CPU-bound workload, mức 60–75% có thể là điểm bắt đầu để giữ headroom cho burst và GC. Với I/O-bound workload, có thể cần nhiều request đang chờ đồng thời; khi đó hãy dùng benchmark thay vì áp dụng utilization CPU một cách máy móc.

### 3.2. Từ throughput đo được

Nếu load test cho thấy một consumer slot xử lý bền vững μworker event/giây trong khi vẫn đạt latency và error budget, tính:

    W = ceil(λpeak / μworker)

Ví dụ một slot xử lý bền vững 32 event/giây ở p95 dưới 100 ms. Với peak 800 event/giây:

    W = ceil(800 / 32)
      = 25 worker slots

Không nhân thêm hệ số utilization nếu μworker đã được đo ở mức tải an toàn và có headroom. Nếu throughput được đo ở mức bão hòa, hãy giảm nó theo utilization mục tiêu trước khi dùng công thức.

Cách đo throughput bền vững thường đáng tin cậy hơn vì nó phản ánh code, serialization, database, network, broker và cấu hình thực tế. Có thể dùng công thức service time để kiểm tra chéo kết quả benchmark.

### 3.3. Không dùng thời gian end-to-end thay cho service time

End-to-end latency có thể gồm thời gian chờ trong broker, thời gian chờ retry và thời gian downstream. Nếu dùng toàn bộ độ trễ này làm S, số worker tính ra có thể bị phóng đại. Đo riêng thời gian worker thực sự bận và thời gian message chờ trước khi được xử lý.

Với I/O bất đồng bộ, một worker có thể có nhiều request đang chờ cùng lúc. Khi đó, số in-flight operation có thể lớn hơn số thread. Hãy đo concurrency thực tế của function/runtime và giới hạn connection của dependency.

## 4. Tính thêm năng lực để xóa backlog

Sizing chỉ đủ cho traffic mới sẽ không tự xóa backlog đã tích lũy. Nếu có B event đang chờ và muốn xử lý hết trong Tdrain giây, tốc độ xử lý cần có thêm:

    λdrain = B / Tdrain

Tổng năng lực cần đạt trong thời gian drain:

    λrequired = λpeak + λdrain

Sau đó tính worker slot bằng công thức throughput hoặc service time tương ứng.

Ví dụ có 600.000 event tồn đọng và muốn xử lý hết trong 10 phút:

    λdrain = 600.000 / 600 = 1.000 event/giây
    λrequired = 800 + 1.000 = 1.800 event/giây

Với S = 40 ms và ρ = 65%:

    W = ceil((1.800 × 0,04) / 0,65)
      = 111 worker slots

Đây là năng lực trong giai đoạn phục hồi, có thể lớn hơn nhiều so với sizing bình thường. Nếu downstream chỉ chịu được 900 request/giây, không thể scale consumer lên 111 slot mà không gây quá tải downstream. Khi đó cần tăng thời gian drain, giảm tốc độ đầu vào hoặc mở rộng dependency.

## 5. Tính số instance từ worker slot

Khi đã có số worker slot W và chọn concurrency C cho mỗi instance:

    I = ceil(W / C)

Với ví dụ W = 50:

| Concurrency mỗi instance | Số instance cần | Tổng slot được cấp |
|---:|---:|---:|
| 1 | 50 | 50 |
| 2 | 25 | 50 |
| 4 | 13 | 52 |
| 5 | 10 | 50 |
| 8 | 7 | 56 |

Số slot được cấp có thể lớn hơn nhu cầu do phải làm tròn instance. Điều này tạo một ít headroom nhưng cũng tiêu thụ CPU/RAM và connection. Chọn C theo benchmark trên một instance, sau đó chọn I theo ngân sách tài nguyên và yêu cầu HA.

### 5.1. Khi nào tăng instance?

Tăng instance phù hợp khi:
- Một instance đã sử dụng phần lớn CPU/RAM hoặc thread.
- Muốn tách failure domain và deploy từng nhóm nhỏ.
- Có đủ partition/queue consumer capacity để phân phối thêm việc.
- Downstream có thể chịu thêm connection và request.
- Cần scale độc lập theo tải.

Tăng instance không hữu ích nếu broker chỉ có một partition đang được một consumer xử lý, hoặc nếu database đã đạt giới hạn connection/IO. Trong trường hợp đó, instance mới có thể idle hoặc làm dependency quá tải hơn.

### 5.2. Khi nào tăng concurrency?

Tăng concurrency trên mỗi instance phù hợp khi:
- Consumer có thời gian chờ I/O đáng kể.
- CPU và heap còn headroom.
- Database/API pool có đủ connection và quota.
- Broker có thể cấp thêm partition/message cho consumer mới.
- Load test chứng minh throughput tăng mà p95/p99 không xấu đi.

Không tăng concurrency chỉ để làm CPU utilization cao hơn. Nếu function CPU-bound và đã dùng hết core, tăng thread thường làm context switch và contention tăng. Nếu message xử lý theo thứ tự hoặc có state không thread-safe, tăng concurrency có thể làm sai semantics.

## 6. Giới hạn quan trọng khi dùng Kafka

Trong Kafka, các record của một topic được chia thành partition. Với cùng một consumer group, tại một thời điểm mỗi partition được gán cho tối đa một consumer trong group. Vì vậy, số consumer đang hoạt động hữu ích bị giới hạn bởi số partition.

Gọi:
- P là số partition của topic.
- I là số instance ứng dụng.
- C là concurrency trên mỗi instance.
- A là số consumer đang được cấp partition.

Trong một consumer group Kafka thông thường:

    A ≤ min(P, I × C)

Đây là giới hạn song song hữu ích theo partition. Nếu I × C lớn hơn P, một số consumer không được gán partition và không tăng throughput. Nếu P lớn hơn I × C, một số partition có thể chưa được gán consumer trong group hiện tại; chúng có thể được dùng khi scale out.

Ví dụ topic có 64 partition:
- 25 instance × concurrency 2 = 50 consumer slot.
- Tối đa 50 consumer có việc; 14 partition chưa có consumer trong group.
- Khi scale lên 32 instance × concurrency 2 = 64 slot, cả 64 partition có thể được xử lý song song.
- Khi scale lên 40 instance × concurrency 2 = 80 slot, tối đa 64 consumer có partition; 16 slot còn lại idle.

Do đó, partition count cần tính theo mức scale tối đa dự kiến của consumer group, không chỉ số pod đang chạy hôm nay.

### 6.1. Tính partition cho Kafka

Với một consumer group xử lý tuần tự mỗi partition, có thể dùng:

    Ptarget ≥ Imax × C

Trong đó Imax là số instance tối đa mà hệ thống dự định scale tới. Đây là điều kiện để có đủ partition cho số consumer slot dự kiến; nó không chứng minh broker có đủ throughput hoặc mọi partition được phân phối đều.

Sau đó kiểm tra thêm:
- Throughput producer và consumer trên mỗi partition.
- Kích thước message và network bandwidth.
- Số broker và khả năng phân bố partition leader.
- Replication factor và dung lượng disk.
- Số key nóng và độ lệch tải giữa partition.
- Thời gian rebalance khi instance tăng/giảm.
- Chi phí metadata, file handle và recovery của nhiều partition.

Không đặt partition count quá lớn chỉ để dự phòng vô hạn. Mỗi partition có chi phí broker, replication, metadata và vận hành.

### 6.2. Key distribution và partition nóng

Tăng partition không bảo đảm tăng throughput nếu dữ liệu phân bố lệch. Ví dụ 40% event thuộc một khách hàng lớn và partition key là customerId. Tất cả event của khách hàng đó có thể dồn vào cùng partition, trong khi các partition khác ít tải.

Chọn key theo yêu cầu ordering và phân bố tải. Nếu cần giữ thứ tự theo order, dùng orderId làm key thường hợp lý. Nếu một key rất nóng, cân nhắc thiết kế aggregate nhỏ hơn, chia shard có kiểm soát hoặc xử lý riêng workload nóng; không đổi key tùy tiện vì có thể phá thứ tự nghiệp vụ.

### 6.3. Tăng partition có ảnh hưởng gì?

Kafka cho phép tăng partition count nhưng không giảm partition count của topic theo cách thông thường. Khi tăng partition, cách ánh xạ key sang partition có thể thay đổi. Các event mới của cùng key có thể được ghi vào partition khác so với event cũ, làm mất giả định ordering xuyên qua thời điểm thay đổi.

Với hệ thống yêu cầu thứ tự theo key, lập kế hoạch migration hoặc giữ partitioning strategy ổn định. Không coi tăng partition là thao tác scale hoàn toàn không rủi ro.

## 7. Phân biệt partitionCount của Spring Cloud Stream với partition của broker

Spring Cloud Stream có abstraction partitioning dùng ở producer và consumer:

- Producer dùng partitionKeyExpression hoặc PartitionKeyExtractor để lấy key.
- Producer dùng partitionCount để xác định không gian partition mà binder partitioning sử dụng.
- Consumer dùng partitioned cùng instanceCount/instanceIndex trong các kịch bản partitioned consumer.
- Broker có thể có partitioning native riêng, như Kafka topic partitions hoặc Pulsar partitioned topic.

Đối với Kafka, partitionCount của producer trong Spring Cloud Stream được xem là một gợi ý; binder sử dụng số lớn hơn giữa giá trị đó và partition count thực tế của topic. Cấu hình producer partitioning không tự thay thế việc quản trị topic partition count trong cluster.

Ví dụ cấu hình producer partitioning:

    spring:
      cloud:
        stream:
          bindings:
            publishOrder-out-0:
              destination: orders
              producer:
                partition-key-expression: payload.orderId
                partition-count: 64

Biểu thức lấy orderId làm partition key. Cấu hình này chỉ có hiệu lực khi partitioning được bật và partitionCount lớn hơn 1. Cần xác nhận destination có số partition tương ứng theo binder.

### 7.1. instanceCount và instanceIndex

Spring Cloud Stream có các thuộc tính:
- spring.cloud.stream.instanceCount: tổng số instance trong ứng dụng được partition.
- spring.cloud.stream.instanceIndex: chỉ số duy nhất của instance, từ 0 tới instanceCount - 1.

Với Kafka và autoRebalanceEnabled mặc định là true, Kafka tự phân phối partition trong consumer group; consumer không cần tự đặt instanceIndex để rebalance thông thường. Nếu tắt autoRebalanceEnabled và giao binder phân bổ partition tĩnh, cần cấu hình instanceCount/instanceIndex chính xác.

Với RabbitMQ partitioned consumer, instanceCount/instanceIndex được dùng để xác định instance nhận partition/queue tương ứng. Không đặt cùng instanceIndex cho tất cả pod nếu mô hình yêu cầu phân vùng tĩnh; mỗi instance phải có chỉ số duy nhất.

## 8. Cấu hình Kafka consumer concurrency

Thuộc tính consumer concurrency chung của Spring Cloud Stream nằm ở binding input:

    spring:
      cloud:
        function:
          definition: processOrder
        stream:
          bindings:
            processOrder-in-0:
              destination: orders
              group: order-workers
              consumer:
                concurrency: 2
        kafka:
          binder:
            auto-create-topics: true
            auto-add-partitions: true
            min-partition-count: 64

Trong ví dụ:
- Mỗi instance có hai consumer concurrency cho binding processOrder-in-0.
- Kafka tự rebalance partition trong consumer group order-workers theo mặc định.
- Binder có thể dùng min-partition-count khi auto-create hoặc auto-add partitions được bật.
- Topic đã tồn tại có thể cần được quản trị trước; kiểm tra số partition thực tế sau khi provision.

Nếu topic đã được tạo sẵn và auto-add-partitions tắt, binder không tự tăng partition khi số partition thực tế nhỏ hơn yêu cầu. Hãy quản lý topic bằng quy trình hạ tầng và xác nhận trước khi rollout.

Concurrency là thuộc tính của từng input binding. Nếu ứng dụng có nhiều function/input binding, tính capacity riêng cho từng binding và kiểm tra tổng số consumer thread, connection và memory trên mỗi instance. Không cộng concurrency của một binding rồi mặc định đó là concurrency toàn ứng dụng.

## 9. RabbitMQ: queue và competing consumers

RabbitMQ không có partition native giống Kafka topic. Với RabbitMQ Binder mặc định, một destination thường ánh xạ tới exchange; mỗi consumer group có queue riêng được bind vào exchange. Nhiều consumer instance của cùng group có thể cùng consume queue đó như competing consumers.

Với queue không partition:
- Có thể tăng số instance hoặc listener concurrency để tăng số consumer.
- Không có quy tắc cứng P ≥ I × C như Kafka topic partition.
- Queue, broker node, prefetch, acknowledgement, message size và downstream vẫn giới hạn throughput.
- Nhiều consumer xử lý song song có thể làm thứ tự hoàn tất khác thứ tự enqueue.

RabbitMQ Binder hỗ trợ consumer concurrency và maxConcurrency trong listener container theo cấu hình binder/version. Với container type direct, một số tùy chọn như maxConcurrency không được hỗ trợ; kiểm tra đúng container type và release đang dùng.

Ví dụ cấu hình:

    spring:
      cloud:
        stream:
          bindings:
            orders-in-0:
              destination: orders
              group: order-workers
              consumer:
                concurrency: 4
          rabbit:
            bindings:
              orders-in-0:
                consumer:
                  max-concurrency: 8
                  prefetch: 20

Concurrency ban đầu là 4 và listener có thể tăng tới 8 consumer theo hỗ trợ của container. Prefetch 20 cho phép mỗi consumer có tối đa số message chưa ack tương ứng theo semantics của Rabbit client; tăng prefetch có thể tăng throughput nhưng cũng làm tăng số message in-flight và bộ nhớ.

### 9.1. RabbitMQ partitioning khi cần thứ tự theo key

Spring Cloud Stream Rabbit Binder hỗ trợ partitioning bằng cách tạo queue cho từng partition và routing key tương ứng. Đây là abstraction do binder xây dựng, không phải partition native của RabbitMQ.

Trong kịch bản partitioned consumer:
- Producer tính partition từ key.
- Binder định tuyến message tới queue của partition.
- Instance được gán partition qua instanceCount/instanceIndex.
- Mỗi partition có queue riêng, giúp giữ nhóm event cùng key ở cùng partition theo cấu hình.

Cấu hình partitioned Rabbit cần phối hợp producer và consumer; chỉ tăng số consumer trên một queue không tạo thêm partition. Nếu dùng RabbitMQ Stream/Super Stream, mô hình partition và concurrency khác với queue AMQP thông thường; đọc đúng phần tài liệu stream plugin trước khi sizing.

## 10. Pulsar: partitioned topic và subscription type

Pulsar tách hai quyết định:
- Partitioned topic quyết định cách producer phân phối dữ liệu qua các partition/broker.
- Subscription type quyết định cách các consumer chia sẻ message và tiến độ.

Một partitioned topic cần được tạo với số partition. Subscription type làm thay đổi giới hạn song song và ordering:

| Subscription type | Cách phân phối | Ảnh hưởng khi scale |
|---|---|---|
| Exclusive | Chỉ một consumer được gắn vào subscription | Không scale nhiều consumer active trên cùng subscription |
| Failover | Có nhiều consumer nhưng một consumer active theo topic/partition, consumer khác standby | Partitioned topic có thể chia các partition active giữa consumer; instance dư có thể standby |
| Shared | Nhiều consumer cùng nhận message phân phối | Tăng consumer song song; không bảo đảm thứ tự message |
| Key_Shared | Nhiều consumer cùng subscription; message cùng key được gửi tới một consumer tại một thời điểm | Có thể song song giữa key và giữ ordering theo key khi producer batching/routing được cấu hình đúng |

Với Shared hoặc Key_Shared, không dùng công thức Kafka một cách máy móc. Số consumer, partition, routing, subscription type và khả năng broker quyết định mức song song hữu ích. Key_Shared cần producer dùng key/ordering key và batching tương thích; nếu batching gộp nhiều key không phù hợp, routing theo key có thể không như mong đợi.

Khi dùng Pulsar Binder, cấu hình consumer và subscription type theo extended binding properties của phiên bản đang chạy. Sau khi thay subscription type, cần kiểm tra quy trình restart và trạng thái subscription vì một subscription chỉ có một loại tại một thời điểm.

## 11. CPU-bound và I/O-bound cần cách chọn concurrency khác nhau

### 11.1. CPU-bound

Ví dụ: mã hóa ảnh, nén dữ liệu, tính toán scoring hoặc xử lý JSON lớn. Mỗi message chiếm CPU đáng kể.

- Bắt đầu với concurrency gần số CPU core được cấp cho instance.
- Đo CPU throttling, context switch, GC và p95.
- Tăng instance khi cần thêm core và broker có thể phân phối thêm việc.
- Không tăng thread vô hạn trên cùng số core.

Nếu container có 2 vCPU, concurrency 16 cho CPU-bound function thường không làm tăng 8 lần throughput; có thể làm latency tệ hơn do tranh chấp CPU.

### 11.2. I/O-bound

Ví dụ: đọc/ghi database, gọi REST API hoặc chờ object storage. Worker thường chờ I/O nên có thể cần nhiều operation đồng thời hơn số core.

- Có thể tăng concurrency cao hơn số core sau khi benchmark.
- Kiểm tra connection pool và giới hạn request của dependency.
- Giới hạn in-flight operation để không tạo hàng đợi trong process.
- Theo dõi timeout, retry và p99 của downstream.

Nếu concurrency là 20 nhưng database connection pool chỉ có 5 connection, phần lớn message có thể chờ connection. Tăng concurrency khi đó chỉ chuyển backlog từ broker vào bộ nhớ ứng dụng.

### 11.3. Reactive function

Reactive function sử dụng Publisher/Flux và có thể xử lý bất đồng bộ. Số thread, số subscription và số request in-flight không nhất thiết bằng consumer concurrency của message-driven listener. Không suy ra số worker chỉ từ số thread. Đo demand, buffer, operator concurrency và giới hạn client I/O theo reactive pipeline.

## 12. Kiểm soát bộ nhớ và prefetch

Mỗi consumer slot có thể giữ message đang xử lý, message prefetch, payload đã deserialize và object trung gian. Bộ nhớ cho in-flight có thể ước lượng sơ bộ:

    Memory_inflight ≈ concurrent_messages × average_payload_memory × overhead_factor

Payload object sau deserialize thường lớn hơn kích thước wire. Overhead factor phụ thuộc object graph, header, buffer, converter và batch; phải đo bằng heap profile/load test.

Ví dụ 16 consumer, mỗi consumer có prefetch 50, có thể tạo tối đa hàng trăm message đang được giao/chờ xử lý tùy binder. Nếu message sau deserialize chiếm trung bình 200 KB, chỉ riêng payload đã có thể tiêu tốn đáng kể bộ nhớ, chưa tính object overhead và các buffer khác.

Không tăng concurrency và prefetch cùng lúc nếu chưa có baseline. Thay một thông số mỗi lần, theo dõi heap, GC pause, unacked count và backlog age.

## 13. Tính partition theo key và thứ tự nghiệp vụ

Partition count không chỉ phục vụ throughput. Nó còn quyết định phạm vi thứ tự và cách chia state.

Trước khi chọn partition key, trả lời:
- Event nào cần xử lý theo thứ tự?
- Thứ tự cần giữ theo orderId, customerId, accountId hay sensorId?
- Có key nào có lưu lượng vượt xa phần còn lại?
- Có thể thay đổi partition count trong tương lai không?
- Consumer có lưu state local theo partition không?

Nếu mọi event của cùng một order cần tuần tự, chọn orderId làm key. Nếu dùng customerId nhưng một khách hàng có lượng event cực lớn, partition tương ứng có thể thành hot partition. Nếu dùng eventId ngẫu nhiên, tải có thể phân bố đều nhưng các event cùng aggregate không còn được giữ chung partition.

Không chọn partition key chỉ theo tiêu chí cân bằng tải; phải giữ invariant nghiệp vụ trước.

## 14. Ví dụ sizing hoàn chỉnh

Giả sử một function xử lý event đơn hàng với số liệu đo được:

| Thông số | Giá trị |
|---|---:|
| Peak input rate | 800 event/giây |
| Service time trung bình trên một slot | 40 ms |
| Utilization mục tiêu | 65% |
| Worker slot cần thiết | 50 |
| Concurrency mỗi pod | 2 |
| Pod cần thiết | 25 |
| Số partition hiện tại | 64 |
| Mức scale tối đa dự kiến | 32 pod |

Tính worker:

    W = ceil((800 × 0,04) / 0,65) = 50

Tính instance:

    I = ceil(50 / 2) = 25

Kiểm tra Kafka ở mức scale tối đa:

    Imax × C = 32 × 2 = 64 consumer slots
    P = 64 partitions

Topic có đủ partition cho kế hoạch scale tối đa. Ở tải hiện tại, 25 pod tạo 50 consumer; khi scale lên 32 pod, có thể có 64 consumer active nếu partition assignment và broker cho phép.

Trước khi chốt, chạy load test với 25 pod ở peak 800 event/giây và thử tăng tới 32 pod. Xác nhận p95/p99, lag, database pool, CPU, GC và broker throughput. Nếu một partition nóng chiếm phần lớn traffic, kết quả thực tế có thể thấp hơn tính toán.

## 15. Cấu hình và triển khai nhiều instance

Ví dụ cấu hình Kafka cho function xử lý đơn hàng:

    spring:
      cloud:
        function:
          definition: processOrder
        stream:
          bindings:
            processOrder-in-0:
              destination: orders
              group: order-workers
              consumer:
                concurrency: 2
          kafka:
            binder:
              min-partition-count: 64
              auto-create-topics: true
              auto-add-partitions: true

Với Kafka consumer group dùng auto rebalance mặc định, các instance dùng cùng group và Kafka phân phối partition. Số replica được đặt bởi nền tảng triển khai; concurrency được áp dụng trên mỗi instance.

Nếu dùng partition assignment tĩnh với Kafka hoặc partitioned consumer của RabbitMQ, cần truyền instanceCount và instanceIndex đúng cho từng instance. Ví dụ biến môi trường:

    SPRING_CLOUD_STREAM_INSTANCE_COUNT=25
    SPRING_CLOUD_STREAM_INSTANCE_INDEX=0

Instance khác phải có index riêng từ 0 tới 24. Không dùng cùng index cho tất cả replica trong mô hình static partition assignment. Trong Kubernetes, cần cơ chế cấp ordinal/index ổn định hoặc dùng runtime như Spring Cloud Data Flow để cung cấp thông tin instance.

## 16. Autoscaling theo lag và backlog

CPU không phải tín hiệu duy nhất để scale consumer. Một ứng dụng I/O-bound có thể CPU thấp nhưng backlog tăng nhanh. Ngược lại, CPU cao trong khi lag vẫn bằng 0 có thể cho thấy consumer đang bận xử lý đúng mức.

Các tín hiệu scale phù hợp:
- Kafka consumer group lag và tốc độ tăng lag.
- RabbitMQ ready message count, unacked count và message age.
- Pulsar subscription backlog và backlog age.
- Processing rate so với input rate.
- p95/p99 processing time.
- CPU, memory và downstream saturation.

Một chính sách autoscaling có thể dùng lag trên mỗi consumer slot, ví dụ mục tiêu 5.000 record/slot, nhưng cần kết hợp giới hạn min/max replica và thời gian ổn định. Không scale vượt khả năng partition hoặc queue topology.

### 16.1. Giới hạn scale của Kafka

Với Kafka, số consumer hữu ích của một group bị giới hạn bởi partition count. HPA có thể yêu cầu 100 pod nhưng topic chỉ có 48 partition; tối đa 48 consumer có thể nhận partition trong group đó. Các pod còn lại tiêu thụ tài nguyên mà không xử lý partition.

### 16.2. Giới hạn scale của RabbitMQ và Pulsar

Với RabbitMQ queue thông thường, nhiều competing consumer có thể cùng đọc một queue, nhưng broker, queue throughput, prefetch và ordering là giới hạn. Với RabbitMQ partitioned queue hoặc Super Stream, số partition/stream segment và consumer assignment mới quyết định parallelism.

Với Pulsar, kiểm tra subscription type. Exclusive chỉ cho một consumer; Failover giữ consumer standby; Shared và Key_Shared cho phép nhiều consumer active nhưng có semantics ordering khác nhau. Không scale consumer chỉ theo số partition mà bỏ qua subscription type.

## 17. Load test để xác nhận sizing

Một phép tính chỉ là giả thuyết cho tới khi được đo trên workload đại diện. Load test nên có các kịch bản:

1. Tải ổn định ở λavg trong thời gian đủ dài để xác nhận baseline.
2. Tải peak λpeak để xác nhận không tăng backlog kéo dài.
3. Burst cao hơn peak trong một khoảng ngắn để kiểm tra headroom.
4. Tải có key skew để phát hiện hot partition/queue.
5. Payload lớn và schema phức tạp.
6. Dependency chậm hoặc timeout để đo tác động tới concurrency.
7. Restart/rebalance một phần instance để kiểm tra recovery.
8. Tăng và giảm replica để xác nhận autoscaling không tạo rebalance storm.
9. Backlog drain để xác nhận thời gian phục hồi theo SLO.

Ghi lại input rate, processed rate, p50/p95/p99, lag/backlog, oldest message age, error/retry/DLQ, CPU, heap, GC, thread, connection pool và broker resource. Một cấu hình chỉ đạt yêu cầu nếu vừa đáp ứng throughput vừa giữ latency và error rate trong mục tiêu.

## 18. Quy trình sizing thực tế

1. Đo peak arrival rate theo cửa sổ nghiệp vụ, không chỉ lấy trung bình ngày.
2. Đo service time và throughput bền vững của một consumer slot.
3. Chọn utilization mục tiêu và headroom theo loại workload.
4. Tính worker slot cần thiết bằng service time hoặc measured throughput.
5. Tính thêm năng lực drain backlog nếu có recovery objective.
6. Chọn concurrency mỗi instance theo CPU, I/O, connection pool và memory.
7. Tính số instance bằng cách chia worker slot cho concurrency.
8. Kiểm tra broker-specific parallelism: Kafka partitions, Rabbit queues/partitions, Pulsar partitions/subscription type.
9. Chọn partition key và kiểm tra skew/ordering.
10. Cấu hình binding, binder và instance metadata theo đúng mô hình.
11. Load test, quan sát SLO và điều chỉnh từng thông số.
12. Đặt min/max replica và autoscaling threshold theo giới hạn broker/downstream.

## 19. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Tính theo traffic trung bình | Backlog tăng khi peak | Dùng peak rate và burst test |
| Tăng pod nhưng Kafka topic ít partition | Consumer mới idle | Tính partition theo max consumer slot |
| Tăng concurrency quá cao | CPU contention, heap, connection exhaustion | Benchmark theo loại CPU/I/O workload |
| Dùng partitionCount thay cho broker partition count | Tưởng topic đã được chia đủ | Kiểm tra partition thực tế trên broker |
| Dùng cùng key cho quá nhiều event | Hot partition | Phân tích key distribution và chọn aggregate key phù hợp |
| Dùng eventId làm partition key khi cần ordering theo order | Event của cùng order đi nhiều partition | Dùng orderId/accountId làm key |
| Tăng RabbitMQ consumer mà bỏ qua prefetch | Nhiều message in-flight và memory pressure | Điều chỉnh concurrency/prefetch cùng lúc có kiểm soát |
| Dùng Pulsar Exclusive nhưng scale nhiều consumer | Consumer mới không active | Chọn subscription type phù hợp semantics |
| Scale Kafka vượt partition count | Pod/consumer dư không nhận partition | Đặt max replicas theo P/C |
| Chỉ nhìn CPU để autoscale | Bỏ lỡ backlog I/O-bound | Kết hợp lag, age, input/output rate |
| Tăng partition đột ngột | Key mapping và ordering có thể thay đổi | Lập kế hoạch migration và kiểm thử |
| Bỏ qua downstream capacity | Database/API quá tải | Sizing toàn pipeline, không chỉ consumer |

## 20. Checklist trước khi triển khai

- [ ] Có peak input rate và burst profile thực tế.
- [ ] Đo service time và throughput của một consumer slot.
- [ ] Xác định utilization mục tiêu và headroom.
- [ ] Tính worker slot cho traffic mới và backlog drain.
- [ ] Chọn concurrency theo CPU, I/O, memory và dependency pool.
- [ ] Tính instance count bằng worker slots/concurrency.
- [ ] Với Kafka, partition count đủ cho số consumer slot ở mức scale tối đa.
- [ ] Kafka topic partition count thực tế đã được xác minh.
- [ ] Partition key đáp ứng ordering và không tạo hot partition nghiêm trọng.
- [ ] Phân biệt producer partitionCount của Spring Cloud Stream với partition vật lý của broker.
- [ ] Với RabbitMQ, đã chọn queue/partitioning và concurrency phù hợp.
- [ ] Với Pulsar, subscription type phù hợp với ordering và parallelism.
- [ ] instanceCount/instanceIndex được cấu hình khi mô hình partition yêu cầu.
- [ ] Hạn chế max replica theo broker partition/queue và downstream capacity.
- [ ] Load test bao gồm peak, burst, key skew, dependency slowdown và restart.
- [ ] Dashboard theo dõi lag/backlog, oldest age, p95/p99, error và resource saturation.

Tính đúng số partition, instance và concurrency là bài toán cân bằng giữa tốc độ nhận dữ liệu, năng lực xử lý mỗi worker, tài nguyên ứng dụng và cách broker phân phối message. Bắt đầu từ peak rate và throughput đo được, tính worker slot, chuyển thành replica/concurrency rồi áp dụng giới hạn riêng của Kafka, RabbitMQ hoặc Pulsar. Sau cùng, load test và quan sát backlog/latency mới xác nhận cấu hình có đáp ứng tải thật hay không.

## Tài liệu tham khảo

- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Partitioning](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-partitioning.html)
- [Spring Cloud Stream — Instance Index and Instance Count](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-instance-index-instance-count.html)
- [Spring Cloud Stream — Kafka Binder Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — RabbitMQ Binder Configuration](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html)
- [Apache Pulsar — Messaging and Subscription Types](https://pulsar.apache.org/docs/5.0.x/concepts-messaging/)

