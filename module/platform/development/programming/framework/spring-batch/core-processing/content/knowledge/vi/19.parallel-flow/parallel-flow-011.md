# Khi dùng scaling module thay vì core flow

Spring Batch có nhiều cách chạy công việc song song. Với các Step độc lập trong cùng một Job, có thể dùng **core flow** và toán tử split để chạy nhiều flow đồng thời. Khi cần phân phối xử lý qua nhiều process hoặc nhiều máy, có thể dùng các mẫu tích hợp trong **Spring Batch Integration**, thường được gọi trong ngữ cảnh này là scaling module.

Hai hướng giải quyết hai bài toán khác nhau. Core flow điều phối các nhánh thực thi trong một ứng dụng Spring Batch. Spring Batch Integration bổ sung cơ chế giao tiếp qua message channel hoặc middleware để manager và worker có thể chạy tách biệt. Chọn module tích hợp khi yêu cầu mở rộng vượt khỏi phạm vi một JVM hoặc cần mô hình remote chunking/remote partitioning; không cần thêm module chỉ để chạy hai Step độc lập song song.

## 1. Core flow và scaling module khác nhau ở đâu?

Spring Batch Core cung cấp các abstraction nền tảng để xây dựng Job, Step, Flow, chunk processing, partitioning và concurrency trong cùng ứng dụng. Core flow có thể dùng split để chạy nhiều flow song song bằng TaskExecutor.

Spring Batch Integration là module bổ sung kết nối Spring Batch với Spring Integration. Nó hỗ trợ các mẫu phân phối công việc qua message channel, chẳng hạn remote chunking và remote partitioning. Các worker có thể chạy trong process khác hoặc trên máy khác, tùy cách triển khai messaging và hạ tầng.

| Tiêu chí | Core flow | Spring Batch Integration |
| --- | --- | --- |
| Mục tiêu chính | Điều phối các Step/flow trong một Job | Phân phối công việc giữa manager và worker qua messaging |
| Phạm vi chạy | Thường trong cùng ứng dụng/JVM | Có thể tách nhiều process hoặc node |
| Cơ chế phối hợp | Flow transition, split và TaskExecutor | Message channel, adapter và middleware |
| Mẫu thường dùng | Parallel flow, local multi-threading, local partitioning | Remote chunking, remote partitioning |
| Độ phức tạp vận hành | Thấp hơn khi mọi thành phần ở cùng ứng dụng | Cao hơn do cần quản lý message, worker và giao tiếp |
| Trường hợp phù hợp | Các nhánh độc lập hoặc scale trong một JVM | Cần scale ngang và phân phối tải qua nhiều node |

Điểm cần phân biệt: Spring Batch Integration không thay thế Spring Batch Core. Module tích hợp dùng các abstraction của Core và bổ sung cách kết nối manager với worker ở xa.

## 2. Khi core flow là đủ

Core flow phù hợp khi các công việc có thể chạy trong cùng ứng dụng và không cần message broker để phân phối xử lý.

Ví dụ Job cần tạo ba loại dữ liệu độc lập sau khi kiểm tra input:

- Tính tổng doanh thu.
- Cập nhật chỉ số khách hàng.
- Tạo dữ liệu đối soát.

Ba nhánh không phụ thuộc kết quả của nhau nên có thể chạy song song rồi chờ hoàn tất trước khi thực hiện Step tổng hợp.

~~~text
                 +--> calculateRevenueFlow --+
                 |                           |
validateInput ---+--> updateCustomerFlow -----+--> summarizeStep
                 |                           |
                 +--> reconcileFlow ----------+
~~~

Ví dụ cấu hình core flow với Spring Batch 5:

~~~java
@Bean
public Job reportingJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step calculateRevenueStep,
        Step updateCustomerStep,
        Step reconcileStep,
        Step summarizeStep,
        TaskExecutor taskExecutor) {

    return new JobBuilder("reportingJob", jobRepository)
            .start(validateInputStep)
            .split(taskExecutor)
            .add(
                    new FlowBuilder<SimpleFlow>("revenueFlow")
                            .start(calculateRevenueStep)
                            .build(),
                    new FlowBuilder<SimpleFlow>("customerFlow")
                            .start(updateCustomerStep)
                            .build(),
                    new FlowBuilder<SimpleFlow>("reconcileFlow")
                            .start(reconcileStep)
                            .build())
            .next(summarizeStep)
            .end()
            .build();
}
~~~

Trong ví dụ, validateInputStep là bước đầu của Job. Sau đó ba flow được chạy đồng thời bằng TaskExecutor. Job chỉ đi đến summarizeStep sau khi các nhánh trong split hoàn tất.

Core flow đặc biệt phù hợp khi:

- Các Step độc lập và chỉ cần chạy đồng thời.
- Dữ liệu có thể được chia sẻ thông qua database hoặc resource dùng chung.
- Tất cả worker có thể chạy trong cùng một ứng dụng.
- Tải xử lý vẫn nằm trong giới hạn CPU, memory, connection pool và I/O của một node.
- Đội vận hành muốn triển khai và theo dõi một ứng dụng thay vì thêm broker cùng worker service.

### Split không phải là data partitioning

Split chạy nhiều flow độc lập song song. Nó không tự chia một tập item của cùng một reader thành nhiều vùng dữ liệu.

Nếu cần chia một bảng thành nhiều phạm vi ID để nhiều worker cùng xử lý, hãy xem xét partitioning. Spring Batch Core đã có Partitioner và local PartitionHandler để thực hiện partitioning trong cùng ứng dụng. Chỉ khi cần remote worker mới cần cân nhắc phần tích hợp messaging.

## 3. Các lựa chọn scale có sẵn trong Spring Batch Core

Trước khi thêm module tích hợp, cần xác định liệu một trong các cơ chế Core đã giải quyết được bài toán hay chưa.

| Cơ chế Core | Cách scale | Phù hợp khi |
| --- | --- | --- |
| Parallel flow với split | Chạy các flow/Step độc lập đồng thời | Nhiều nhánh công việc không phụ thuộc nhau |
| Multi-threaded Step | Nhiều thread cùng tham gia xử lý một Step theo cấu hình | Công việc trong Step có thể chạy đồng thời và component an toàn với concurrency |
| Local partitioning | Chia dữ liệu thành partition, chạy worker Step trong cùng JVM | Một Step cần chia dữ liệu thành nhiều phạm vi độc lập |
| Sequential chunk Step | Tăng hiệu năng bằng tối ưu reader, processor, writer và chunk size | Chưa cần concurrency hoặc bottleneck có thể tối ưu tại chỗ |

Ví dụ local partitioning:

~~~java
@Bean
public Step managerStep(
        JobRepository jobRepository,
        Step workerStep,
        Partitioner partitioner,
        TaskExecutor taskExecutor) {

    return new StepBuilder("managerStep", jobRepository)
            .partitioner(workerStep.getName(), partitioner)
            .step(workerStep)
            .gridSize(8)
            .taskExecutor(taskExecutor)
            .build();
}
~~~

Đây vẫn là khả năng của Spring Batch Core. Nếu tám worker có thể chạy trong cùng JVM và database có đủ khả năng phục vụ chúng, không cần remote partitioning chỉ để đạt concurrency.

## 4. Khi nào nên dùng Spring Batch Integration?

Nên cân nhắc Spring Batch Integration khi bài toán có yêu cầu phân phối tải hoặc tách vòng đời manager/worker khỏi một process:

- Một node không đủ CPU, memory hoặc I/O để xử lý khối lượng dữ liệu.
- Có thể triển khai nhiều worker trên nhiều máy hoặc container.
- Muốn scale worker độc lập với manager.
- Các worker có thể nhận công việc qua message channel hoặc broker.
- Cần tận dụng hạ tầng messaging đã có trong hệ thống.
- Muốn tách nơi đọc dữ liệu khỏi nơi xử lý/ghi dữ liệu.
- Cần xử lý nhiều partition độc lập trên các node khác nhau.

Ví dụ, manager đọc một tập dữ liệu lớn nhưng bước xử lý từng item tiêu tốn CPU. Có thể gửi các chunk đến worker để xử lý song song. Hoặc manager chia dữ liệu theo tenant, ngày hay khoảng khóa rồi gửi từng partition cho worker tự đọc và ghi dữ liệu của phạm vi đó.

Module tích hợp không tự làm Job nhanh hơn. Nó tạo cơ chế giao tiếp và phân phối. Hiệu năng chỉ tăng khi worker có đủ tài nguyên, công việc có thể song song hóa, bottleneck được phân phối và chi phí truyền message không lớn hơn lợi ích xử lý.

## 5. Remote chunking: manager đọc, worker xử lý chunk

Remote chunking phù hợp khi manager có thể đọc dữ liệu và gửi các chunk đến worker qua messaging. Worker nhận chunk, xử lý và ghi kết quả.

~~~text
Manager process
    |
    +-- ItemReader
    |
    +-- tạo chunk
    |
    v
Request channel / message broker
    |
    +------------------+------------------+
    |                  |                  |
    v                  v                  v
Worker A            Worker B            Worker C
    |                  |                  |
    +-- Processor      +-- Processor      +-- Processor
    +-- Writer         +-- Writer         +-- Writer
    |                  |                  |
    +------------------+------------------+
                       |
                       v
                Reply / completion
                       |
                       v
                 Manager Step
~~~

Trong mô hình này:

- Manager sở hữu ItemReader và tạo chunk.
- Manager gửi chunk qua message channel.
- Worker nhận chunk và thực hiện phần xử lý được giao, thường gồm processor và writer.
- Kết quả hoặc tín hiệu hoàn thành được phản hồi để manager điều phối tiến độ.

Remote chunking phù hợp khi:

- Đọc dữ liệu ở manager không phải bottleneck chính.
- Processor hoặc writer là phần tiêu tốn tài nguyên nhất.
- Chunk có thể serialize và truyền qua middleware.
- Worker có thể xử lý các chunk độc lập.
- Hệ thống chấp nhận semantics giao nhận message và có cách xử lý retry/duplicate.

Giới hạn quan trọng: reader vẫn chạy ở manager. Nếu đọc dữ liệu là bottleneck, tăng số worker không làm tăng đáng kể tốc độ đọc. Khi đó remote partitioning hoặc một chiến lược phân chia nguồn đọc có thể phù hợp hơn.

## 6. Remote partitioning: manager chia phạm vi, worker tự đọc

Remote partitioning phù hợp khi dữ liệu có thể được chia thành các partition độc lập. Manager tạo ExecutionContext cho từng partition và gửi yêu cầu chạy worker Step. Worker nhận phạm vi rồi tự đọc, xử lý và ghi dữ liệu.

~~~text
Manager process
    |
    v
Partitioner
    |
    +--> partition 0: ID 1-100000
    +--> partition 1: ID 100001-200000
    +--> partition 2: ID 200001-300000
    |
    v
Messaging / broker
    |
    +------------------+------------------+
    |                  |                  |
    v                  v                  v
Worker A            Worker B            Worker C
    |                  |                  |
  Reader             Reader             Reader
    |                  |                  |
  Processor          Processor          Processor
    |                  |                  |
  Writer             Writer             Writer
    |                  |                  |
    +------------------+------------------+
                       |
                       v
                Worker Step status
                       |
                       v
                 Manager Step
~~~

Remote partitioning phù hợp khi:

- Nguồn dữ liệu có thể chia thành các phạm vi độc lập.
- Cần scale cả reader, processor và writer.
- Worker có thể truy cập nguồn dữ liệu hoặc resource tương ứng.
- Các partition có thể được định danh và tái tạo ổn định.
- Có thể chia sẻ hoặc cấu hình JobRepository phù hợp để theo dõi StepExecution của worker.

Ví dụ partition theo khoảng ID giúp mỗi worker tự truy vấn database với điều kiện phạm vi riêng. Cần bảo đảm các khoảng không chồng lấn và dữ liệu nguồn ổn định trong suốt lần chạy.

## 7. Chọn remote chunking hay remote partitioning?

Hai mẫu đều dùng messaging để phân phối công việc, nhưng đặt trách nhiệm đọc dữ liệu ở vị trí khác nhau:

| Tiêu chí | Remote chunking | Remote partitioning |
| --- | --- | --- |
| Reader | Manager đọc dữ liệu | Mỗi worker đọc phạm vi riêng |
| Phần việc được gửi | Chunk item | Partition metadata/Step execution request |
| Worker thực hiện | Xử lý và ghi chunk | Chạy worker Step cho partition |
| Khi phù hợp | Processor/writer là bottleneck | Cần scale cả việc đọc và xử lý theo vùng dữ liệu |
| Yêu cầu chính | Chunk có thể truyền và worker xử lý độc lập | Partitioner tạo phạm vi ổn định, worker truy cập được nguồn |
| Điểm nghẽn có thể còn lại | Manager reader và kênh gửi message | Database hoặc nguồn dữ liệu dùng chung |

Không có mẫu nào luôn nhanh hơn. Chọn theo nơi đang tốn thời gian, cách dữ liệu được truy cập và khả năng chia công việc.

## 8. Phụ thuộc và cấu hình module tích hợp

Khi cần remote chunking hoặc remote partitioning, ứng dụng manager và worker có thể cần dependency Spring Batch Integration tương thích với phiên bản Spring Batch Core.

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework.batch</groupId>
    <artifactId>spring-batch-integration</artifactId>
</dependency>
~~~

Nếu dự án dùng Spring Boot dependency management, để BOM quản lý version phù hợp. Nếu tự quản lý version, cần căn chỉnh spring-batch-integration với spring-batch-core và các phiên bản Spring Integration tương thích. Không trộn các version khác nhau một cách tùy tiện.

Module tích hợp sử dụng các thành phần Spring Integration như message channel, messaging adapter và endpoint để nối manager với worker. Hình thức cấu hình cụ thể phụ thuộc phiên bản Spring Batch, broker và mô hình triển khai. Các builder/adapter dành cho remote chunking và remote partitioning đã thay đổi theo các thế hệ API, nên cần dùng tài liệu đúng version của dự án.

Không cần thêm spring-batch-integration chỉ để gọi split() hoặc dùng TaskExecutor trong một Step. Những khả năng đó thuộc Spring Batch Core.

## 9. Kiến trúc triển khai remote

Khi manager và worker chạy ở các process khác nhau, cần xác định rõ trách nhiệm và tài nguyên của từng bên.

### Manager

Manager thường chịu trách nhiệm:

- Khởi tạo Job và điều phối flow.
- Đọc dữ liệu và gửi chunk trong remote chunking.
- Hoặc tạo partition và gửi yêu cầu worker trong remote partitioning.
- Theo dõi kết quả, timeout và trạng thái thực thi.
- Điều phối restart theo metadata.

### Worker

Worker thường chịu trách nhiệm:

- Nhận message hoặc partition request.
- Khởi tạo thành phần xử lý phù hợp.
- Thực hiện processor/writer hoặc toàn bộ worker Step.
- Commit dữ liệu theo transaction của worker.
- Gửi kết quả hoặc cập nhật trạng thái để manager theo dõi.

### Middleware

Message broker hoặc transport cần hỗ trợ:

- Định tuyến request đến worker.
- Phân phối message theo khả năng xử lý.
- Durability hoặc cơ chế lưu message phù hợp với yêu cầu.
- Acknowledgement, redelivery và retry.
- Backpressure hoặc giới hạn số message đang chờ.
- Quan sát queue depth, delivery count và consumer health.

Remote worker không tự động có quyền truy cập các bean hoặc object trong JVM manager. Dữ liệu cần truyền phải có định dạng message có thể serialize; không gửi trực tiếp connection, EntityManager, resource handle hoặc object chỉ tồn tại trong bộ nhớ.

## 10. Chọn theo bottleneck thực tế

Trước khi chuyển sang scaling module, hãy đo hệ thống để xác định phần nào giới hạn throughput:

| Bottleneck | Hướng xử lý nên xem xét |
| --- | --- |
| Các Step độc lập chờ nhau không cần thiết | Core flow với split |
| Một Step tuần tự nhưng processor nhẹ, database còn dư tải | Thử core concurrency/local partitioning |
| Processor CPU-bound, reader đủ nhanh | Remote chunking hoặc local multi-threading |
| Reader/database query là bottleneck | Remote partitioning nếu nguồn chia được; tối ưu query/index trước |
| Writer bị giới hạn bởi database | Tối ưu batch write, transaction và schema; tăng worker có thể làm bottleneck nặng hơn |
| Một node không đủ tài nguyên | Remote partitioning/chunking để phân phối sang nhiều node |
| Nhiều worker cùng tranh chấp một bảng | Thiết kế lại partition boundary và access pattern trước khi scale |

Không nên chuyển sang remote chỉ vì số lượng item lớn. Một Job đọc 20 triệu dòng nhưng chủ yếu chờ một truy vấn chậm có thể cần tối ưu query hoặc partition theo khóa. Nếu chi phí serialize và gửi message lớn, remote chunking có thể còn chậm hơn xử lý local.

## 11. Transaction và message delivery

Khi manager và worker giao tiếp qua broker, một message có thể được gửi lại nếu consumer lỗi, acknowledgement không đến hoặc broker redeliver sau timeout. Do đó, không nên giả định message chỉ được xử lý đúng một lần.

Các nguyên tắc quan trọng:

- Thiết kế processor/writer idempotent.
- Gắn message ID hoặc partition ID ổn định vào request.
- Lưu trạng thái xử lý để nhận ra message đã hoàn thành.
- Xác định acknowledgement xảy ra trước hay sau khi dữ liệu worker commit.
- Không giả định transaction của manager tự bao trùm transaction của worker ở process khác.
- Dùng outbox/inbox hoặc transaction coordination khi cần bảo đảm giữa database và broker.

Trong remote chunking, manager có thể gửi một chunk nhưng không nhận được phản hồi do worker đã xử lý xong rồi mất kết nối. Khi retry message, worker có thể nhận chunk lần nữa. Writer cần nhận diện chunk/message đã xử lý hoặc có unique key nghiệp vụ để tránh ghi trùng.

Trong remote partitioning, một worker có thể đã commit một số chunk của partition trước khi process dừng. Khi restart, worker cần khôi phục checkpoint của StepExecution và tiếp tục đúng phạm vi. Tên partition, ExecutionContext và input snapshot phải ổn định.

## 12. Lỗi, retry và restart trong mô hình phân tán

Thêm middleware làm xuất hiện các lỗi vận hành mới:

- Worker không khởi động hoặc bị dừng giữa chừng.
- Message bị giữ trong queue quá lâu.
- Request được gửi nhưng reply bị mất.
- Broker tạm thời không khả dụng.
- Worker xử lý xong nhưng manager chưa cập nhật được kết quả.
- Một partition được gửi lại sau timeout.

Hãy phân biệt lỗi nghiệp vụ của item với lỗi transport và lỗi worker:

| Loại lỗi | Xử lý thường phù hợp |
| --- | --- |
| Dữ liệu item không hợp lệ | Skip/reject theo policy của Step |
| Database tạm thời không khả dụng | Retry có giới hạn và backoff |
| Worker mất kết nối | Redelivery/retry theo cơ chế messaging, có idempotency |
| Message không thể deserialize | Quarantine hoặc DLQ, cảnh báo vận hành |
| Lỗi cấu hình worker | Dừng và sửa cấu hình |
| Partition vượt thời gian dự kiến | Điều tra worker, query, lock và resource; không retry vô hạn |

JobRepository vẫn là nguồn quan trọng để theo dõi JobExecution và StepExecution. Với remote partitioning, cần cấu hình worker cập nhật trạng thái StepExecution theo cơ chế metadata mà manager có thể quan sát. Với remote chunking, cần theo dõi cả tiến độ Step phía manager lẫn trạng thái xử lý message/worker theo thiết kế.

Restart không tự động hoàn tác side effect đã xảy ra ở worker. Hãy kiểm tra dữ liệu đã commit trước khi gửi lại chunk hoặc partition.

## 13. Backpressure và giới hạn concurrency

Scale ngang không có nghĩa càng nhiều worker càng tốt. Nếu manager gửi message nhanh hơn tốc độ worker xử lý, queue sẽ tăng liên tục, độ trễ tăng và dữ liệu có thể tiêu thụ nhiều bộ nhớ hoặc dung lượng lưu trữ.

Các giới hạn cần thiết kế:

- Số worker đang hoạt động.
- Số message tối đa đang chờ hoặc in-flight.
- Kích thước chunk và payload message.
- Số connection đến database trên mỗi worker.
- Giới hạn concurrency của broker consumer.
- Tốc độ manager đọc và gửi công việc.
- Thời gian xử lý trung bình và phân vị cao của worker.

Ví dụ, nếu manager phát 500 chunk/phút nhưng toàn bộ worker chỉ xử lý được 300 chunk/phút, backlog tăng 200 chunk mỗi phút. Thêm worker có thể giúp nếu CPU/database còn dư tải; nếu database đã bão hòa, tăng worker chỉ làm contention nặng hơn.

Theo dõi queue depth, oldest message age, worker throughput, error rate, database connection usage và partition duration để quyết định tăng hay giảm concurrency.

## 14. Serialization và kích thước message

Remote chunking gửi dữ liệu item qua transport. Vì vậy, item hoặc chunk cần có biểu diễn có thể serialize và deserialize ở cả hai phía.

Lưu ý:

- Dùng DTO/message contract ổn định, không truyền object gắn với persistence context.
- Tránh gửi payload quá lớn; có thể truyền business key hoặc reference nếu worker truy cập được dữ liệu.
- Đảm bảo manager và worker dùng phiên bản contract tương thích.
- Có chiến lược version hóa message khi deploy rolling update.
- Không đưa secret hoặc dữ liệu nhạy cảm vào message nếu không cần thiết.
- Cấu hình serialization an toàn và xác thực nguồn gửi message.

Remote partitioning thường truyền metadata nhỏ của partition thay vì toàn bộ item. Worker dùng các key trong ExecutionContext để tự đọc dữ liệu. Điều này có thể giảm lưu lượng mạng, nhưng yêu cầu worker truy cập được nguồn dữ liệu và có logic reader phù hợp.

## 15. Triển khai và bảo mật

Khi chuyển từ local sang remote, cần quản lý thêm hạ tầng:

- Broker hoặc message transport có tính sẵn sàng và dung lượng phù hợp.
- Network giữa manager, worker và database.
- Authentication và authorization cho channel/queue.
- Mã hóa kết nối và dữ liệu khi cần.
- Worker deployment, health check và graceful shutdown.
- Quản lý phiên bản message contract.
- Logging có correlation ID để nối manager request với worker result.
- Cảnh báo khi queue backlog, worker failure hoặc partition timeout vượt ngưỡng.

Worker chỉ nên nhận loại công việc và phạm vi được phép xử lý. Không tin tưởng một message chỉ vì nó đến từ broker; xác thực producer, kiểm tra dữ liệu đầu vào và giới hạn quyền truy cập tài nguyên theo nguyên tắc tối thiểu.

## 16. Lộ trình từ core flow sang scaling module

Không cần chuyển toàn bộ Job sang mô hình remote cùng lúc. Có thể tiến hành theo từng bước:

1. Đo thời gian từng Step và xác định bottleneck.
2. Tối ưu query, batch write, chunk size và resource usage.
3. Dùng split nếu các Step độc lập cần chạy song song.
4. Dùng multi-threaded Step hoặc local partitioning nếu cần scale trong một JVM.
5. Xác định worker boundary và dữ liệu có thể truyền qua message.
6. Chọn remote chunking nếu manager đọc và worker xử lý/ghi; chọn remote partitioning nếu worker cần tự đọc từng phạm vi.
7. Thêm spring-batch-integration với version tương thích.
8. Thiết lập broker, message channel, worker deployment và observability.
9. Kiểm thử duplicate delivery, worker crash, broker outage và restart.
10. Đo throughput đầu-cuối và so sánh với baseline local trước khi tăng quy mô.

Mỗi bước cần có số liệu để chứng minh lợi ích. Remote architecture có chi phí vận hành, network và serialization; chỉ nên giữ khi lợi ích scale đáp ứng yêu cầu hệ thống.

## 17. Những trường hợp không nên dùng scaling module

Không nên chọn Spring Batch Integration chỉ vì:

- Muốn chạy hai Step độc lập song song trong một Job.
- Muốn tăng số thread trong cùng một JVM.
- Chưa đo bottleneck và chưa tối ưu truy vấn.
- Dữ liệu không thể serialize hoặc không có contract message ổn định.
- Không có hạ tầng broker/worker để vận hành.
- Công việc quá nhỏ, chi phí message lớn hơn chi phí xử lý.
- Writer hoặc nghiệp vụ không an toàn khi message được giao lại.
- Các worker cùng cập nhật một tài nguyên đang bị lock contention.

Trong những trường hợp này, core flow, local partitioning hoặc tối ưu Step tuần tự thường dễ vận hành và dễ kiểm soát hơn.

## 18. Những lỗi thường gặp

### Dùng split để chia item của cùng một reader

Split chạy các flow độc lập. Nếu muốn chia một tập dữ liệu cho nhiều worker, dùng partitioning thay vì kỳ vọng split tự chia item.

### Thêm spring-batch-integration cho một flow local

Split và TaskExecutor thuộc Core. Chỉ thêm module tích hợp khi cần các mẫu messaging/remote.

### Remote chunking nhưng reader vẫn là bottleneck

Manager vẫn đọc dữ liệu. Nếu tốc độ đọc giới hạn throughput, cân nhắc remote partitioning hoặc tối ưu reader.

### Remote partitioning nhưng partition bị chồng lấn

Worker có thể đọc và ghi cùng bản ghi. Xác định phạm vi không giao nhau, khóa sort ổn định và input snapshot.

### Tăng worker mà không kiểm tra database

Nhiều worker có thể làm cạn connection pool, tăng lock contention và giảm throughput tổng thể.

### Giả định message được xử lý exactly-once

Broker có thể redeliver khi lỗi hoặc timeout. Dùng idempotency key, inbox/outbox và unique constraint.

### Không xử lý message quá lớn

Chunk payload lớn làm tăng network, serialization và memory. Thiết kế DTO gọn hoặc truyền reference dữ liệu.

### Không theo dõi worker và queue

Chỉ nhìn trạng thái manager không đủ để chẩn đoán backlog hoặc worker lỗi. Theo dõi queue depth, delivery count và từng worker execution.

## 19. Cách quyết định

Trước khi chọn core flow hay scaling module, hãy trả lời:

1. Công việc cần chạy song song là nhiều Step độc lập hay nhiều phần của cùng một tập dữ liệu?
2. Có thể scale trong cùng JVM hay cần nhiều process/node?
3. Bottleneck nằm ở reader, processor, writer, database hay tài nguyên ngoài?
4. Nếu dùng remote chunking, manager có đủ khả năng đọc và gửi chunk không?
5. Nếu dùng remote partitioning, dữ liệu có thể chia thành phạm vi ổn định và không chồng lấn không?
6. Worker có truy cập được database/file/service cần thiết không?
7. Có broker và năng lực vận hành message delivery, retry, DLQ và backpressure không?
8. Message/partition có thể được xử lý lại an toàn không?
9. Metadata, checkpoint và Job restart được quản lý thế nào?
10. Đo throughput đầu-cuối có chứng minh remote scaling tốt hơn local không?

Nếu các Step chỉ cần chạy đồng thời trong cùng ứng dụng, dùng core flow. Nếu một Step cần chia dữ liệu trong cùng JVM, dùng local partitioning hoặc cơ chế concurrency của Core. Khi cần đưa công việc sang worker process khác qua messaging, Spring Batch Integration mới là lựa chọn phù hợp.

## Kết luận

Core flow phù hợp để điều phối các Step hoặc flow độc lập chạy song song trong cùng ứng dụng. Spring Batch Core cũng đã có multi-threaded Step và local partitioning cho nhiều nhu cầu scale tại một JVM. Hãy dùng Spring Batch Integration khi cần phân phối công việc qua message channel hoặc broker đến worker process/node khác. Remote chunking phù hợp khi manager đọc và worker xử lý/ghi chunk; remote partitioning phù hợp khi worker cần tự đọc một phạm vi dữ liệu. Quyết định dựa trên bottleneck, ranh giới dữ liệu, khả năng vận hành broker và yêu cầu restart/idempotency, không chỉ dựa trên số lượng item.
