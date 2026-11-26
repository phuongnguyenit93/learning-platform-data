# Spring Integration flow cho worker trong Spring Batch

## Mục tiêu bài học

Trong **remote partitioning**, manager chia một Spring Batch step thành nhiều phần việc. Worker chạy trong tiến trình JVM riêng phải nhận yêu cầu, xác định đúng `StepExecution`, thực thi worker step, lưu trạng thái và phản hồi kết quả. **Spring Integration flow** là một cách kết nối kênh nhận yêu cầu, bộ xử lý của Spring Batch và kênh trả kết quả với message broker.

Bài này thuộc chương **Remote Step** của module **SPRING_BATCH_SCALING_OPERATIONS**. Chủ đề tập trung vào **thiết kế flow phía worker**, từ hợp đồng message tới cách nhận input qua `ExecutionContext`, lỗi giao tiếp, retry/restart và vận hành. Những điểm về concurrency, thread safety, hiệu năng đọc/ghi và mở rộng nhiều JVM được xem xét trong bối cảnh workload dữ liệu lớn.

Sau bài học, bạn có thể:

- Diễn tả đường đi của một yêu cầu remote partition từ manager đến worker rồi trả kết quả.
- Hiểu vai trò của `StepExecutionRequestHandler`, `JobExplorer`, `StepLocator`, `JobRepository` và Spring Integration channel.
- Tạo một **worker IntegrationFlow** gồm inbound request → xử lý `StepExecutionRequest` → outbound reply.
- Phân biệt **kênh điều phối partition** với **kênh truyền item/chunk** của remote chunking.
- Xây worker step nhận phạm vi dữ liệu bằng `@StepScope` và `stepExecutionContext`.
- Xác định những điều phải kiểm chứng về serialization, ack, redelivery, timeout, transaction, tính đúng dữ liệu và restart.
- Đo số worker, throughput, message latency và tải DB trước khi nâng quy mô.

## 1. Worker Integration flow giải quyết vấn đề gì?

Một `Step` Spring Batch không tự chạy trên JVM khác chỉ vì chúng ta tăng số replica. Với remote partitioning, hệ thống cần **một giao thức thực thi phần việc từ xa**.

Phía manager thực hiện ba việc chính:

1. Dùng `Partitioner` tạo các partition có tên và `ExecutionContext` riêng.
2. Tạo/ghi nhận `StepExecution` cho các phần việc bằng cơ chế Spring Batch.
3. Dùng partition handler và kênh giao tiếp để yêu cầu worker thực thi phần việc rồi theo dõi kết quả.

Phía worker thực hiện:

1. Nhận message request từ transport.
2. Chuyển request đến Spring Batch handler.
3. Từ request, tìm metadata `StepExecution` và định nghĩa `Step` tương ứng.
4. Gọi worker step, thực hiện `ItemReader`/`ItemProcessor`/`ItemWriter` và commit/checkpoint.
5. Gửi response hoặc làm trạng thái sẵn có qua cơ chế điều phối phù hợp.

~~~mermaid
sequenceDiagram
    participant M as Manager JVM
    participant J as JobRepository
    participant Q as Message broker
    participant I as Worker IntegrationFlow
    participant H as StepExecutionRequestHandler
    participant D as Business DB

    M->>J: Tạo StepExecution và ExecutionContext
    M->>Q: Gửi StepExecutionRequest
    Q->>I: Inbound adapter nhận request
    I->>H: handle(request)
    H->>J: JobExplorer tìm StepExecution
    H->>H: StepLocator tìm worker step
    H->>D: Step đọc / xử lý / ghi
    H->>J: Step cập nhật metadata / checkpoint
    H-->>I: Kết quả StepExecution
    I->>Q: Outbound adapter gửi reply
    Q-->>M: Manager nhận hoặc đối chiếu trạng thái
~~~

Đây là **sơ đồ logic**, không phải hợp đồng giao dịch nguyên tử qua DB và broker. Thứ tự cập nhật chi tiết, cách chờ response và việc manager kiểm tra trạng thái phụ thuộc phiên bản Spring Batch Integration và loại `PartitionHandler` được cấu hình.

**Điểm cốt lõi:** `IntegrationFlow` là lớp kết nối **message và handler**, còn **Spring Batch step** mới là nơi xử lý dữ liệu nghiệp vụ và quản lý chunk/transaction.

## 2. Phân biệt remote partitioning và remote chunking

Cả hai có thể dùng Spring Integration, nhưng loại message và trách nhiệm worker khác nhau.

| Câu hỏi | Remote partitioning | Remote chunking |
| --- | --- | --- |
| Manager gửi gì? | Yêu cầu thực thi một `StepExecution` đã được tạo | Item/chunk mà manager đã đọc |
| Worker tự đọc nguồn? | **Có**, theo phạm vi phân công | Thông thường **không**; manager là nơi đọc |
| Input riêng của worker | `StepExecution ExecutionContext` | Payload item/chunk và metadata giao thức |
| Handler đặc trưng | `StepExecutionRequestHandler` | Thành phần xử lý chunk theo protocol remote chunking |
| Tải mạng | Chủ yếu request/reply về phần việc; dữ liệu nghiệp vụ do worker tự truy vấn nguồn | Có thể phải vận chuyển toàn bộ item/chunk qua broker |
| Restart | Metadata, partition name, checkpoint và writer | Checkpoint manager, ack/retry message và side effect ở worker |
| Điểm nghẽn thường gặp | DB nguồn/đích, partition không đều, metadata | Reader manager, broker, serialization, writer |

Bài này mô tả **worker của remote partitioning**, với request liên quan `StepExecution`. Không được áp dụng máy móc tên handler hoặc định dạng message này cho remote chunking.

## 3. Hợp đồng message giữa manager và worker

Trong mô hình worker request/reply thông dụng, manager gửi đối tượng `StepExecutionRequest` chứa các định danh cần thiết để worker tìm phần việc. Về mặt ý nghĩa, request mang:

- **jobExecutionId:** xác định lần thực thi job.
- **stepExecutionId:** xác định phần việc/step execution cụ thể.
- **stepName:** tên step mà worker có thể tìm qua `StepLocator`.

Ví dụ *biểu diễn logic* để dễ hình dung:

~~~json
{
  "jobExecutionId": 4102,
  "stepExecutionId": 4188,
  "stepName": "workerStep"
}
~~~

JSON trên **chỉ minh họa thông tin**. Không nên mặc định đây là payload JSON nguyên dạng mà mọi phiên bản Spring Batch Integration gửi. Format thực phụ thuộc message converter/serializer, transport và các lớp request đang sử dụng.

**Input nghiệp vụ** như khoảng ID, tenant hoặc file thường nằm trong `ExecutionContext` đã được gắn với `StepExecution`. Ví dụ:

~~~yaml
# Nội dung logic của StepExecution ExecutionContext
minIdInclusive: 1000001
maxIdExclusive: 1250001
businessDate: "2026-11-25"
~~~

Manager chịu trách nhiệm tạo các input này, và worker **không tự suy ra** chúng từ tên pod, số replica hay thứ tự message. Khi xử lý request, worker tra metadata rồi chạy đúng step với context của phần việc đó.

### Vì sao không nhét toàn bộ dữ liệu vào request?

ExecutionContext nên chứa thông tin điều khiển và trạng thái nhỏ. Nếu manager gửi hàng trăm nghìn record trong một request, nó phải trả chi phí serialization, network, broker storage và xử lý lỗi payload lớn. Đó là dấu hiệu cần cân nhắc một hợp đồng partition (worker tự đọc) hoặc mô hình remote chunking thực sự.

## 4. Những thành phần cần có trong worker JVM

| Thành phần | Trách nhiệm |
| --- | --- |
| **Inbound adapter** | Nhận request từ RabbitMQ, Kafka hoặc transport tương thích đã chọn |
| **Request channel** | Cung cấp điểm vào nội bộ của `IntegrationFlow` |
| **`StepExecutionRequestHandler`** | Xử lý request, tra `StepExecution`, tìm và thực thi worker step |
| **`JobExplorer`** | Đọc metadata job/step cần thiết từ repository |
| **`StepLocator`** | Tìm `Step` đã đăng ký theo tên request |
| **`JobRepository`** | Lưu/cập nhật metadata execution/checkpoint trong hạ tầng Spring Batch |
| **Worker `Step`** | Định nghĩa reader/processor/writer, transaction và chunk size |
| **Reply channel + outbound adapter** | Đưa kết quả theo protocol trở lại manager |
| **Message converter** | Chuyển message broker thành request/response tương thích ở cả hai đầu |

Một worker có thể chạy trên Kubernetes, VM hoặc container, nhưng những thành phần trên phải được cấu hình thống nhất với manager. `JobExplorer` và `JobRepository` phải tham chiếu metadata phù hợp để tìm `StepExecution` mà manager đã tạo.

Trong triển khai remote partitioning thông dụng, manager và các worker **cùng truy cập JobRepository bền vững** theo cấu hình phù hợp. `JobExplorer` là phía đọc metadata; worker step vẫn sử dụng hạ tầng Spring Batch để cập nhật execution khi thực thi.

Không chọn repository chỉ tồn tại trong bộ nhớ nếu cần worker ở tiến trình khác truy xuất `StepExecution` và muốn restart tin cậy sau sự cố.

## 5. Tạo flow xử lý request/reply trong worker

Ví dụ sau minh họa **cấu trúc kênh nội bộ** với Spring Integration Java DSL và Spring Batch Integration, dựa trên các API thường gặp ở dòng Spring Batch 5.x. Đây là cấu hình nền để hiểu đường đi message; muốn chạy thật cần thêm inbound/outbound broker adapter, worker step, JobRepository, JobExplorer và StepLocator tương thích phiên bản.

~~~java
import org.springframework.batch.core.configuration.StepLocator;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.integration.partition.StepExecutionRequestHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class PartitionWorkerIntegrationConfig {

    @Bean
    public MessageChannel partitionRequests() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel partitionReplies() {
        return new DirectChannel();
    }

    @Bean
    public StepExecutionRequestHandler partitionRequestHandler(
            JobExplorer jobExplorer,
            StepLocator stepLocator) {

        StepExecutionRequestHandler handler =
                new StepExecutionRequestHandler();
        handler.setJobExplorer(jobExplorer);
        handler.setStepLocator(stepLocator);
        return handler;
    }

    @Bean
    public IntegrationFlow partitionWorkerFlow(
            StepExecutionRequestHandler partitionRequestHandler) {

        return IntegrationFlow.from("partitionRequests")
                .handle(partitionRequestHandler, "handle")
                .channel("partitionReplies")
                .get();
    }
}
~~~

**Cách đọc flow:**

1. `partitionRequests` là channel mà inbound adapter sẽ gửi `StepExecutionRequest` đã chuyển đổi đúng kiểu.
2. `.handle(partitionRequestHandler, "handle")` gọi handler thực thi step trong Spring Batch.
3. Kết quả trả về được chuyển tiếp tới `partitionReplies`.
4. Outbound adapter của transport thực tế sẽ nhận từ `partitionReplies` và gửi response tới đúng destination của manager.

**Giới hạn của ví dụ:** `DirectChannel` là channel gọi handler đồng bộ trên thread gửi message; nó không tự kết nối broker, tạo concurrency hay xử lý redelivery. Nếu chưa có subscriber cho `partitionReplies`, response không được chuyển đi. Khi dùng `StepExecutionRequestHandler` và DSL phiên bản khác, phải đối chiếu tên lớp/phương thức và dependency tương ứng trước khi biên dịch.

Trong ứng dụng thực tế, nên tách **inbound, handler, outbound** thành các bean/flow có mục đích rõ, thay vì để mọi logic xử lý nghiệp vụ trong một `MessageHandler` tùy biến.

## 6. Đưa message từ broker vào worker flow

Hai channel ở trên chỉ hoạt động **trong bộ nhớ của worker JVM**. Cần thiết lập adapter đưa message từ broker vào `partitionRequests` và lấy response từ `partitionReplies` để trả về manager.

Một sơ đồ adapter:

~~~mermaid
flowchart LR
    MQ1[["Queue: partition.requests"]] --> IA["Inbound adapter"]
    IA --> RC["partitionRequests"]
    RC --> H["StepExecutionRequestHandler"]
    H --> PC["partitionReplies"]
    PC --> OA["Outbound adapter"]
    OA --> MQ2[["Queue: partition.replies"]]
~~~

Ví dụ khung Spring Integration dùng AMQP/RabbitMQ, minh họa ý tưởng ràng buộc adapter:

~~~java
// Cấu hình minh họa; cần chọn adapter, converter và
// request/reply destination tương thích với broker thực tế.

@Bean
public IntegrationFlow requestIngress(
        org.springframework.amqp.rabbit.connection.ConnectionFactory factory) {

    return IntegrationFlow
            .from(org.springframework.integration.amqp.dsl.Amqp
                    .inboundAdapter(factory, "partition.requests"))
            .channel("partitionRequests")
            .get();
}

// Luồng gửi reply phải dùng outbound AMQP adapter tương ứng,
// map đúng routing key/queue "partition.replies" và message converter
// mà manager chấp nhận. Không chỉ tạo queue rồi bỏ quên subscriber.
~~~

Đoạn cấu hình chỉ minh họa **request ingress**. Nó chưa phải một ví dụ tích hợp RabbitMQ hoàn chỉnh: cần đảm bảo queue/exchange/binding, consumer concurrency, converter, publish/confirm, reply destination, retry và xác thực được cấu hình nhất quán. Đặc biệt, Java DSL adapter có thể thay đổi giữa các phiên bản Spring Integration AMQP, nên kiểm tra API thật của phiên bản dự án.

### Dùng broker nào?

Spring Integration hỗ trợ nhiều giao thức qua adapter. Sự lựa chọn dựa trên:

- Message delivery semantics: redelivery, retention, consumer group, offset/ack.
- Khả năng định tuyến **request/reply** của manager và worker.
- Kích thước payload, message age, visibility/ack timeout.
- Quan sát queue depth, dead-letter và retry.
- Hạ tầng vận hành đã có và năng lực quản trị sự cố.

Không mặc định Kafka và RabbitMQ có cùng request/reply hoặc ack behavior. Phần tích hợp cụ thể phải khớp broker được chọn, cùng cấu hình của `PartitionHandler` phía manager.

## 7. JobExplorer và StepLocator giúp worker xác định việc gì cần chạy

`StepExecutionRequestHandler` không tự tìm mọi step có trong hệ thống một cách tùy ý. Nó cần những khả năng:

**JobExplorer:** dùng định danh `JobExecution`/`StepExecution` trong request để truy xuất metadata đã lưu. Điều này giúp worker nhận đúng trạng thái phần việc, trong đó có `ExecutionContext`.

**StepLocator:** từ `stepName`, trả về đối tượng `Step` đúng định nghĩa nghiệp vụ để thực thi. Nếu manager gọi `workerStep` mà worker chỉ đăng ký `paymentStep`, yêu cầu có thể thất bại vì không tìm thấy step tương ứng.

Ví dụ khai báo danh sách step được phép thực thi:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.StepLocator;
import org.springframework.batch.core.configuration.support.MapStepLocator;
import org.springframework.context.annotation.Bean;
import org.springframework.beans.factory.annotation.Qualifier;

@Bean
public StepLocator workerStepLocator(
        @Qualifier("workerStep") Step workerStep) {

    MapStepLocator locator = new MapStepLocator();
    locator.register(workerStep);
    return locator;
}
~~~

Các API `MapStepLocator`/`StepLocator` và package cụ thể cần đối chiếu với phiên bản Spring Batch đang dùng. Ý tưởng cần giữ là **đăng ký một danh sách step có chủ đích**, không thực thi tên step tùy ý từ message chưa được xác thực.

**Quy tắc quan trọng:** tên mà manager dùng để chỉ worker step phải khớp tên được đăng ký ở `StepLocator`. Với partitioning, `StepExecution` có thể được quản lý theo tên gắn partition; đừng tự ghép chuỗi tên trong worker để tìm step khi framework đã có hợp đồng request rõ ràng.

### Xử lý request không hợp lệ

Nếu request trỏ tới `StepExecution` không tồn tại, step name không hợp lệ, hoặc metadata không truy cập được, worker cần **thất bại có quan sát**, phân loại lỗi và để cơ chế retry/điều phối phản ứng.

Không tự tạo `StepExecution` mới với các ID trong message khi `JobExplorer` không tìm thấy. Điều này có thể phá vỡ tính nhất quán của JobRepository và restart.

## 8. Worker nhận input nghiệp vụ qua ExecutionContext

Giả sử manager đã tạo partition cho đơn hàng theo khoảng ID, mỗi worker nhận input riêng:

| Partition | `minIdInclusive` | `maxIdExclusive` |
| --- | ---: | ---: |
| partition-0 | 1 | 250001 |
| partition-1 | 250001 | 500001 |
| partition-2 | 500001 | 750001 |
| partition-3 | 750001 | 1000001 |

Nguyên tắc `[minIdInclusive, maxIdExclusive)` giúp tránh chồng lấn tại ranh giới.

Trong worker JVM, bean có `@StepScope` đọc `stepExecutionContext` của phần việc đang thực thi:

~~~java
import java.math.BigDecimal;
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

public record OrderRow(long id, BigDecimal amount) {}

@Bean
@StepScope
public JdbcCursorItemReader<OrderRow> rangeReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minIdInclusive']}")
        Long minIdInclusive,
        @Value("#{stepExecutionContext['maxIdExclusive']}")
        Long maxIdExclusive) {

    if (minIdInclusive == null || maxIdExclusive == null
            || minIdInclusive >= maxIdExclusive) {
        throw new IllegalArgumentException("Invalid partition range");
    }

    return new JdbcCursorItemReaderBuilder<OrderRow>()
            .name("rangeReader")
            .dataSource(dataSource)
            .sql("""
                 SELECT id, amount
                 FROM orders
                 WHERE id >= ? AND id < ?
                 ORDER BY id
                 """)
            .preparedStatementSetter(ps -> {
                ps.setLong(1, minIdInclusive);
                ps.setLong(2, maxIdExclusive);
            })
            .rowMapper((rs, index) -> new OrderRow(
                    rs.getLong("id"),
                    rs.getBigDecimal("amount")))
            .saveState(true)
            .build();
}
~~~

Đoạn minh họa cho Java 17/Spring Batch 5.x, giả định kiểu bảng, bean, import và lớp cấu hình đã được khai báo phù hợp. Nếu viết tệp Java thực tế, record top-level phải đặt đúng vị trí và dùng cách tổ chức lớp Java hợp lệ; ở đây các đoạn được trình bày để giải thích từng phần của worker.

Ở worker step:

~~~java
@Bean
public Step workerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcCursorItemReader<OrderRow> rangeReader,
        ItemWriter<OrderRow> idempotentWriter) {

    return new StepBuilder("workerStep", jobRepository)
            .<OrderRow, OrderRow>chunk(250, transactionManager)
            .reader(rangeReader)
            .writer(idempotentWriter)
            .build();
}
~~~

`idempotentWriter` là bean ứng dụng phải tự triển khai đúng nghiệp vụ; tên không tự bảo đảm idempotency.

**Vì sao phải dùng StepScope?** Worker được tạo bean theo `StepExecution` đang chạy để lấy input riêng. Nếu tạo reader singleton với một khoảng ID cố định, tất cả partition có thể cùng đọc sai phạm vi.

**Vì sao phải giữ context nhỏ?** Worker có thể truy vấn DB bằng range, tenant hoặc file name, không cần gửi toàn bộ record qua JobRepository hoặc broker. Điều này giảm chi phí phối hợp so với chuyển payload lớn trong mỗi request.

## 9. Request đến worker có đồng nghĩa worker lập tức bắt đầu chạy?

Không nhất thiết. Request có thể nằm trong queue, chờ consumer rảnh hoặc mất thời gian tải metadata, tạo scoped bean và mở kết nối.

Phân biệt bốn mốc:

1. **Dispatch:** manager đưa request tới transport.
2. **Receive:** inbound adapter của worker lấy request.
3. **Start:** handler thực thi `Step` và reader bắt đầu đọc.
4. **Complete/Reply:** StepExecution hoàn thành hoặc thất bại, response đến manager hoặc trạng thái được ghi nhận.

Mỗi mốc nên có timestamp hoặc metric tương ứng. Nếu chỉ đo `StepExecution` elapsed time, có thể bỏ qua thời gian request nằm trong queue trước khi worker bắt đầu.

### DirectChannel và concurrency

`DirectChannel` gọi subscriber đồng bộ trên thread gửi message. Nếu inbound AMQP adapter có bốn consumer threads và mỗi consumer xử lý một request đồng bộ, thường có tối đa khoảng bốn request đang thực thi theo cấu hình đó, nhưng con số thực tế còn do listener container, pool, handler và hạ tầng quyết định.

Không tăng `ExecutorChannel`, số consumer và thread pool của step cùng lúc rồi giả định tổng số worker đã được giới hạn. Nhiều tầng executor có thể làm số request đang hoạt động lớn hơn dự tính hoặc tạo hàng chờ khó quan sát.

## 10. Message reply và các trạng thái hoàn thành

Một handler thực thi step trả về kết quả liên quan `StepExecution` để manager có thể tổng hợp trạng thái. Response này cần được serializer và outbound adapter chuyển đúng qua kênh phản hồi.

Các trạng thái cần phân biệt:

| Tình huống | Điều worker biết | Điều manager có thể thấy trước khi đối chiếu |
| --- | --- | --- |
| Step hoàn tất, reply đến nơi | StepExecution có kết quả cuối | Có cơ sở đánh dấu phần việc hoàn tất |
| Step thất bại và có reply | Lỗi/ExitStatus đã ghi nhận theo cơ chế step | Có thể đánh dấu partition lỗi hoặc áp dụng policy |
| Step hoàn tất, reply bị mất | Worker đã xong nhưng phản hồi không tới manager | Có thể chờ, timeout hoặc phải kiểm tra metadata |
| Request bị giao lại | Có thể gặp phần việc đã chạy/đang chạy | Phải tránh thực thi trùng thiếu kiểm soát |
| Worker JVM chết giữa chunk | Metadata/checkpoint có thể dở dang | Cần xác minh trạng thái trước khi restart |

**Không dùng việc “message đã được broker ack” làm bằng chứng duy nhất rằng nghiệp vụ đã ghi đúng một lần.** Ack của broker, commit DB và phản hồi manager có thể thuộc các transaction độc lập.

Đối với yêu cầu chạy phân tán, chọn quy tắc xử lý trường hợp **kết quả chưa rõ**: kiểm tra JobRepository, phân biệt execution còn đang chạy với execution đã kết thúc và tuân theo cơ chế restart/partition handler đang sử dụng.

## 11. Transaction và rủi ro xử lý trùng

Trong chunk-oriented worker step, `PlatformTransactionManager` quản lý giao dịch dữ liệu phù hợp với resource được cấu hình. Broker ack và DB commit **không mặc nhiên thuộc cùng một transaction**.

Một tình huống:

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant W as Worker
    participant D as Database
    participant M as Manager

    B->>W: StepExecutionRequest
    W->>D: Ghi chunk
    D-->>W: COMMIT thành công
    W--xM: Reply thất lạc / kết nối đứt
    B-->>W: Có thể giao lại request tùy ack/retry
    W->>D: Phải xác minh metadata và ghi lặp an toàn
~~~

Sơ đồ minh họa một **nguy cơ**, không khẳng định rằng mọi cấu hình đều tự chạy lại toàn bộ partition khi reply mất. Cơ chế nào thực thi lại, quản lý trạng thái và timeout phụ thuộc `PartitionHandler`, ack policy và trạng thái StepExecution.

### Writer idempotent

Một cách với dữ liệu quan hệ là thiết kế business key duy nhất và upsert, ví dụ PostgreSQL:

~~~sql
INSERT INTO order_summary (order_id, total_amount)
VALUES (:orderId, :totalAmount)
ON CONFLICT (order_id)
DO UPDATE SET total_amount = EXCLUDED.total_amount;
~~~

Ví dụ giả định có UNIQUE/PRIMARY KEY trên `order_id` và ghi đè là đúng nghiệp vụ. Nếu nghiệp vụ **cộng dồn số tiền**, gửi email hoặc gọi API thanh toán thì cần cơ chế idempotency riêng. Upsert không bảo đảm mọi side effect ngoài DB xảy ra đúng một lần.

### Phân loại retry

- **Lỗi dữ liệu:** thiếu key context, kiểu sai, thông tin step không hợp lệ → thường cần fail rõ ràng; retry vô hạn không có ích.
- **Lỗi hạ tầng tạm thời:** DB timeout, broker mất kết nối → có thể retry có giới hạn và backoff, nhưng cần xét tình trạng giao dịch đã commit.
- **Lỗi xử lý item:** có thể sử dụng retry/skip của fault-tolerant step theo chính sách nghiệp vụ, khác với retry message cấp broker.
- **Kết quả chưa rõ:** kiểm tra StepExecution và phần đã commit trước khi giao lại phần việc.

Không trộn retry message với retry item mà không tính số lượt thực thi tổng; việc lặp nhiều tầng có thể tạo retry storm.

## 12. Restart và tính ổn định của partition input

Remote partitioning dựa vào danh tính phần việc và metadata. Khả năng restart chính xác không chỉ đến từ việc manager gửi lại cùng message.

Một thiết kế có thể khôi phục cần:

1. **Partition name ổn định** trong cùng JobInstance.
2. **ExecutionContext đầu vào không đổi** qua các lần thực thi lại phần việc logic.
3. **Reader restartable** và checkpoint phản ánh phần dữ liệu đã commit.
4. **Nguồn dữ liệu được xác định nhất quán** bằng high-watermark/snapshot/cutoff khi cần.
5. **Writer idempotent**, kể cả khi worker chết sau ghi nhưng trước phản hồi.
6. **JobRepository bền vững** và manager/worker dùng metadata tương thích.

Ví dụ không an toàn: ở lần chạy đầu `partition-0` đọc `[1,100000)`; lần restart lại đọc `[1,200000)` vì Partitioner lấy MAX(id) mới. Checkpoint cũ có thể không còn tương ứng với tập dữ liệu, dẫn đến bỏ sót hoặc xử lý lặp.

**Không giả định worker chỉ cần nhớ vị trí trong bộ nhớ.** JVM có thể bị hủy và tái tạo; thông tin phải đến từ `StepExecution` và hạ tầng lưu trạng thái được thiết kế.

### Cẩn trọng với các request đến muộn

Khi manager đã timeout một request nhưng message cũ vẫn nằm trong queue hoặc reply đến chậm, hệ thống có thể thấy kết quả không còn tương ứng với vòng điều phối hiện tại.

Cần gắn và theo dõi ID của JobExecution/StepExecution, correlation ID của request/reply, trạng thái execution và chính sách timeout. Không dùng “tên worker” hoặc thời gian nhận message để quyết định đó là phần việc mới.

## 13. Serialization và phiên bản của hợp đồng giao tiếp

Message transport cần chuyển đổi request/reply thành một dạng có thể lưu và truyền. Sự khác biệt giữa manager và worker có thể gây lỗi:

- Không deserialize được tên lớp hoặc kiểu dữ liệu.
- Thiếu trường bắt buộc hoặc thay đổi kiểu ID.
- Trường ExecutionContext có kiểu tùy biến không tương thích.
- Worker đăng ký step name khác manager.
- Hai đầu dùng thư viện Batch/Integration có protocol khác nhau.
- Broker đưa message tới consumer không có quyền truy cập JobRepository phù hợp.

Ưu tiên **input nhỏ và kiểu dữ liệu đơn giản**, như String, long, boolean hoặc identifier. Không đặt đối tượng domain lớn hoặc secret thô vào ExecutionContext.

Một quy trình triển khai phiên bản an toàn nên có:

- Kiểm tra contract request/reply trong integration test.
- Quản lý phiên bản thư viện manager và worker có chủ đích.
- Xác nhận tương thích serializer/converter.
- Có chiến lược xử lý message cũ khi rollout dần nhiều worker.
- Gắn version của worker vào log để tìm lỗi lệch cấu hình.

Không tự đưa message không tin cậy vào `StepExecutionRequestHandler` mà không kiểm soát nguồn phát: nó yêu cầu thực thi một Step đã đăng ký. Có thể giới hạn broker permission, queue, service account, network và tập step mà `StepLocator` công bố.

## 14. Thread safety bên trong mỗi worker JVM

Một worker JVM có thể chạy **nhiều request partition đồng thời** nếu inbound adapter được cấu hình nhiều consumer. Trong khi mỗi `StepExecution` có context riêng, các singleton component của Spring vẫn có thể chia sẻ state.

| Thành phần | Rủi ro | Cách thiết kế |
| --- | --- | --- |
| ItemReader có cursor | Con trỏ hoặc vị trí đọc dùng chung | Reader `@StepScope` theo partition |
| ItemProcessor giữ buffer mutable | Ghi/đọc lẫn dữ liệu nhiều partition | Stateless hoặc scope/synchronization phù hợp |
| ItemWriter có cache mutable | Ghi nhầm item hoặc flush sai | Đánh giá thread safety và tách state theo step |
| Connection pool | Nhiều transaction tranh kết nối | Giới hạn consumer và pool theo năng lực DB |
| Static cache | Worker này ghi state worker khác | Dùng dữ liệu bất biến hoặc cache có chính sách concurrency |
| File output | Nhiều partition ghi cùng file | Phân file theo partition hoặc đồng bộ/ghép cuối job |

**@StepScope không tự làm an toàn mọi resource được gọi bên trong bean.** Ví dụ mỗi reader có instance riêng nhưng cùng gọi một client stateful không thread-safe vẫn có thể bị race.

Nếu chạy 4 JVM, mỗi JVM có 3 consumer và worker step thực thi đồng bộ, tổng số StepExecution đồng thời có thể lên tới khoảng 12 theo cấu hình đó. DB phải có ngân sách connection/lock phù hợp trên **toàn bộ cluster**, không chỉ từng instance.

## 15. Backpressure và giới hạn số partition đang chạy

Giả sử manager giao nhiều partition nhanh, trong khi worker cần thời gian dài để xử lý. Queue có thể tích lũy request, hoặc số transaction DB tăng quá mức nếu consumer concurrency quá lớn.

Nên có giới hạn ở các tầng:

- **Manager/PartitionHandler:** số partition đang được điều phối và timeout hợp lý.
- **Inbound listener:** số consumer/chủ đề nhận request.
- **Worker JVM:** số request/step đồng thời, CPU, heap và connection pool.
- **Database nguồn/đích:** mức query, transaction, lock và I/O cho phép.
- **Message broker:** queue depth, message age, redelivery và dead-letter policy.
- **Retry:** giới hạn số lần, backoff và xử lý lỗi không thể phục hồi.

### Chunk size khác số partition

Một partition có thể chứa hàng triệu item và được xử lý qua nhiều chunk, ví dụ mỗi chunk 500 item. `gridSize` liên quan đến cách chia partition; consumer concurrency liên quan số worker chạy đồng thời; `chunk(500)` liên quan transaction/checkpoint của worker step.

Không đổi ba tham số cùng lúc khi benchmark. Có thể giữ 16 partition, bốn consumer và thử chunk 250 rồi 500. Sau đó mới cân nhắc tăng consumer khi DB còn dư tải.

### Chi phí của phần việc quá nhỏ

Nếu một partition chỉ xử lý 50 item nhưng cần khởi động bean, tải StepExecution, request/reply và ghi metadata, overhead có thể chiếm phần lớn thời gian. Ngược lại, một partition quá lớn sẽ làm worker chậm nhất kéo dài job.

Hãy chọn số partition qua phép đo **thời gian mỗi partition**, số item, dispatch latency và năng lực DB, thay vì chỉ chọn bằng số CPU core.

## 16. Quan sát worker flow từ đầu tới cuối

Khi manager chỉ thấy job “đang chạy”, cần biết thời gian bị mất ở đâu:

| Metric / mốc | Cần trả lời |
| --- | --- |
| Request published timestamp | Manager đã giao việc chưa? |
| Queue age / lag | Request chờ broker/consumer bao lâu? |
| Worker receive timestamp | Message đã tới worker nào? |
| Step start timestamp | Worker có đang load metadata, tạo bean hay mở connection? |
| Step read/write counts | Worker tiến được bao nhiêu item? |
| Chunk duration và rollbackCount | Transaction có chậm hoặc bị làm lại? |
| Reply published/received | Worker xong mà manager còn chờ phản hồi? |
| JobRepository latency | Metadata có thành nút thắt khi tăng worker? |
| DB connection wait/lock wait | Có tranh chấp khi nhiều JVM cùng chạy? |
| Partition duration | Có worker/partition chậm nhất giữ toàn job? |

Log minh họa:

~~~text
jobExecutionId=4102
stepExecutionId=4188
stepName=workerStep
partitionName=orders-2026-11-25-03
workerInstance=worker-b
requestReceivedAt=2026-11-26T02:10:00Z
readCount=249820
writeCount=249820
rollbackCount=0
stepStatus=COMPLETED
replyPublished=true
~~~

Các giá trị là giả định. Nên có correlation ID cho request/reply và log structured, nhưng tránh ghi toàn bộ payload hoặc PII. Với hệ thống metric, cân nhắc cardinality khi dùng stepExecutionId/partition ID làm nhãn vì số giá trị có thể rất lớn.

**Phân biệt latency:** thời gian StepExecution không nhất thiết chứa thời gian message nằm trong queue. Để đo full request-to-reply, cần các mốc cả ở manager và worker.

## 17. Các lỗi thường gặp và hướng chẩn đoán

| Triệu chứng | Khả năng nguyên nhân | Kiểm tra trước |
| --- | --- | --- |
| Queue có request nhưng worker không chạy | Inbound adapter thiếu binding/consumer, message converter lỗi | Queue binding, consumer log, định dạng request |
| Worker nhận message nhưng không tìm thấy step | `stepName` không có trong `StepLocator` | Tên worker step, registration, manager contract |
| Không tìm được StepExecution | JobExplorer trỏ sai repository/ID, metadata chưa sẵn sàng | jobExecutionId, stepExecutionId, DB/schema |
| Reader nhận null range | Context key không khớp, bean không có StepScope | `ExecutionContext`, `@StepScope`, tên key |
| Worker ghi xong nhưng manager vẫn chờ | Reply adapter/routing, timeout, serializer, network | Reply channel, queue, correlation ID, handler logs |
| Một partition bị thực thi lại | Redelivery, timeout hoặc restart chưa điều phối đúng | StepExecution status, ack policy, idempotency |
| Thêm worker mà tốc độ giảm | DB lock/connection, full scan hoặc quá nhiều partition | Throughput, DB wait, p95 chunk latency |
| Worker chết giữa chunk | Process crash, OOM, lỗi I/O | Heap/GC, transaction, checkpoint và metadata |
| Worker khác phiên bản không đọc được request | Thay payload converter hoặc kiểu class | Dependency versions, serialization contract |
| Thấy duplicate output | Writer không idempotent hoặc partition overlap | Business key, range, retry/ack sequence |

Trước khi cho manager gửi lại một request thất bại, cần biết **worker trước đã dừng hoàn toàn hay vẫn đang thực thi**. Nếu cùng `StepExecution` bị chạy đồng thời thiếu kiểm soát, metadata hoặc dữ liệu có thể sai dù hai worker đều chạy “đúng code”.

## 18. Kiểm thử từ flow nhỏ đến toàn kiến trúc

### 18.1. Kiểm tra handler với message hợp lệ

Trong kiểm thử tích hợp, tạo job/step metadata qua API Spring Batch phù hợp, tạo `StepExecution` có ExecutionContext và bảo đảm StepLocator biết worker step. Sau đó gửi `StepExecutionRequest` đúng ID tới inbound channel.

Kiểm tra:

- Handler tìm đúng StepExecution và Step.
- Reader nhận đúng min/max qua StepScope.
- Writer chỉ ghi bản ghi thuộc partition.
- StepExecution lưu trạng thái và checkpoint mong đợi.
- Response tương thích với message converter mà manager sử dụng.

Không nên tự giả lập mọi hành vi JobRepository bằng một Map đơn giản rồi kết luận rằng cơ chế restart phân tán đã được kiểm chứng.

### 18.2. Kiểm thử adapter và broker

Chạy manager và worker trên **hai JVM riêng**, dùng broker thử nghiệm cùng loại với production:

1. Gửi một request phân vùng hợp lệ.
2. Kiểm tra message được chuyển đổi đúng kiểu.
3. Kiểm tra reply trở về đúng channel/queue và được manager nhận.
4. Thử nhiều request, bảo đảm worker không xử lý dữ liệu chồng lấn.
5. Giả lập kết nối broker bị mất và message đến trễ.

Có thể dùng containerized broker và database thử nghiệm nếu môi trường cho phép, nhưng phải xác nhận lược đồ JobRepository và phiên bản thư viện thực tế.

### 18.3. Fault injection và restart

Các tình huống bắt buộc có:

| Tình huống | Kỳ vọng cần chứng minh |
| --- | --- |
| Kill worker trước khi commit chunk | Phần chưa commit được xử lý lại an toàn |
| Kill worker sau commit nhưng trước reply | Không ghi trùng side effect, trạng thái được đối chiếu |
| Broker mất kết nối tạm thời | Retry/timeout có giới hạn, không mất dấu phần việc |
| Duplicate request | Không chạy đồng thời cùng phần việc thiếu kiểm soát |
| Worker nhận range sai kiểu | Fail rõ, không ghi dữ liệu |
| DB nguồn/đích chậm | Có backpressure, pool wait nằm trong ngân sách |
| Restart JobInstance | Partition name, context và checkpoint không đổi ngoài ý muốn |
| Manager khởi động lại | Có quy trình xác định trạng thái đang chạy/dang dở |

Không tuyên bố “exactly once” chỉ vì các kiểm thử happy path đi qua. Tính đúng cần được chứng minh bằng đối soát khóa nghiệp vụ sau lỗi.

## 19. Tình huống thực tế: chuyển local sang remote partitioning

Một hệ thống cần đọc **24 triệu giao dịch** cuối ngày để tính điểm và ghi vào bảng phân tích. Dữ liệu có ID số, có thể chia thành những khoảng ổn định; một JVM đã gần giới hạn CPU.

### Bước 1 — Giữ nguyên hợp đồng input

Manager dùng Partitioner tạo 48 partition theo khoảng ID; mỗi ExecutionContext chứa:

~~~yaml
minIdInclusive: 2000001
maxIdExclusive: 2500001
businessDate: "2026-11-25"
~~~

Đây là ví dụ một partition. Các range phải bao phủ tập dữ liệu hợp lệ, không chồng lấn; businessDate và high-watermark cần được chốt cho lần chạy. Không nhất thiết mọi khoảng có cùng số record nếu ID có lỗ hổng.

### Bước 2 — Triển khai worker JVM

Mỗi worker triển khai:

- Worker step có `JdbcCursorItemReader` hoặc reader phù hợp, dùng `@StepScope`.
- Writer idempotent theo transactionId.
- `JobExplorer`, `JobRepository` và `StepLocator` tương thích manager.
- Inbound adapter → `partitionRequests` → `StepExecutionRequestHandler` → `partitionReplies` → outbound adapter.
- Metric, log và giới hạn consumer/connection.

### Bước 3 — Đo concurrency

Giả định kết quả benchmark:

| Worker JVM | Partition đồng thời tổng | Write throughput | DB lock wait | Nhận xét |
| ---: | ---: | ---: | --- | --- |
| 1 | 2 | 5.000 item/s | Thấp | Baseline phân tán |
| 2 | 4 | 8.900 item/s | Thấp | Mở rộng có ích |
| 4 | 8 | 13.500 item/s | Trung bình | Gần giới hạn DB |
| 8 | 16 | 13.900 item/s | Cao | Cải thiện rất ít |
| 12 | 24 | 12.400 item/s | Rất cao | Contention làm chậm |

Các số là **giả định để thực hành phân tích**, không phải benchmark Spring Batch. Với bốn JVM, việc tăng lên tám chỉ cải thiện khoảng 3% throughput theo bảng, nhưng tăng lock wait. Nếu SLA đã đạt và có dự phòng, bốn worker có thể là cấu hình phù hợp hơn.

### Bước 4 — Kiểm thử sự cố

Dừng worker khi đang ghi một partition, thử restart và đối chiếu toàn bộ business key. Nếu worker đã ghi chunk trước khi mất reply, writer phải lặp lại an toàn. Kiểm tra queue/JobRepository để tránh hai JVM thực thi cùng StepExecution đồng thời.

### Bước 5 — Kết luận kiến trúc

Remote partitioning có ích ở đây vì worker tự đọc từ DB, manager chỉ gửi yêu cầu phần việc và nhiều JVM cung cấp thêm CPU. Nhưng tốc độ cuối vẫn bị DB đích và chi phí điều phối giới hạn. **Mục tiêu là hoàn thành đúng SLA và phục hồi an toàn**, không phải có số replica lớn nhất.

## 20. Những nhầm lẫn phổ biến

| Nhận định | Cách hiểu đúng |
| --- | --- |
| “Có IntegrationFlow thì Spring Batch tự phân vùng dữ liệu.” | Partitioner/manager phải tạo StepExecution và ExecutionContext; flow chỉ nối đường đi message với handler |
| “Worker request chứa toàn bộ item.” | Remote partitioning thường gửi định danh phần việc; worker tự đọc input |
| “Worker lấy range từ tên pod.” | Range thuộc StepExecution ExecutionContext được manager xác định |
| “Tăng replica là đủ để chạy phân tán.” | Cần broker/channel, handler, step registration và metadata tương thích |
| “Ack thành công nghĩa là DB đã commit đúng một lần.” | Ack và DB commit có thể tách biệt; cần idempotency |
| “JobRepository chỉ dùng ở manager.” | Worker cần tra và cập nhật metadata theo thiết kế remote partitioning |
| “DirectChannel tự tạo nhiều worker thread.” | DirectChannel xử lý đồng bộ; concurrency do inbound/executor và topology quyết định |
| “Mọi request fail đều retry ngay.” | Cần phân biệt lỗi dữ liệu, timeout, request đang chạy và trạng thái commit |
| “Worker có @StepScope là mọi bean đều thread-safe.” | Các singleton, client và DB vẫn có thể chia sẻ state hoặc tranh chấp |
| “Reply đến trễ có thể coi là phần việc mới.” | Phải xác minh JobExecution/StepExecution và correlation ID |
| “Remote partitioning luôn nhanh hơn local.” | DB, network, broker và quản lý worker có thể triệt tiêu lợi ích thêm CPU |
| “Một test handler pass nghĩa là production restart ổn.” | Cần kiểm thử broker thật, crash, duplicate delivery và data reconciliation |

## 21. Checklist thiết kế worker IntegrationFlow

- [ ] Manager dùng đúng mô hình **remote partitioning** và tạo các StepExecution hợp lệ.
- [ ] `StepExecutionRequest` có đủ định danh để worker truy xuất metadata.
- [ ] Worker `StepLocator` đăng ký đúng tên step manager yêu cầu.
- [ ] Worker `JobExplorer` và `JobRepository` trỏ vào metadata bền vững và tương thích.
- [ ] Request inbound adapter/queue và reply outbound adapter/queue được nối đúng channel.
- [ ] Message converter tương thích ở cả manager lẫn worker.
- [ ] Reader `@StepScope` lấy input từ `stepExecutionContext`, validate key và phạm vi.
- [ ] Partition input không trùng/thiếu; snapshot và tên partition ổn định qua restart.
- [ ] Reader/processor/writer và các bean dùng chung đã được đánh giá thread safety.
- [ ] Writer idempotent, transaction/ack/retry được thiết kế theo hạ tầng thực tế.
- [ ] Có giới hạn consumer concurrency, connection pool và backpressure.
- [ ] Có timeout, error channel, dead-letter/alert và quy trình xử lý request lỗi.
- [ ] Metric/log gắn JobExecution ID, StepExecution ID, partition và worker.
- [ ] Đã đo queue lag, dispatch-to-reply latency, throughput và DB contention.
- [ ] Đã thử kill worker, duplicate request, reply thất lạc và restart.
- [ ] Có đối soát đầu ra theo business key, không chỉ dựa trên JobExecution COMPLETED.

## 22. Câu hỏi tự kiểm tra

**1. Spring Integration flow phía worker có tự xác định các khoảng ID để xử lý không?**

Không. Manager/Partitioner xác định phần việc và lưu input trong ExecutionContext. Flow nhận request, đưa tới handler để tải đúng StepExecution và thực thi worker step.

**2. Vai trò khác nhau của JobExplorer và StepLocator là gì?**

JobExplorer truy xuất metadata StepExecution được yêu cầu; StepLocator tìm định nghĩa Step tương ứng với stepName. Thiếu một trong hai, handler khó thực thi đúng phần việc.

**3. Vì sao inbound adapter và outbound adapter cần được cấu hình cả hai?**

Inbound đưa request từ broker vào flow. Outbound chuyển response về kênh mà manager lắng nghe. Chỉ có request channel hoặc xử lý thành công ở worker chưa bảo đảm manager nhận được kết quả.

**4. Tại sao không thể dùng broker ack để kết luận không ghi trùng?**

Vì message ack và DB commit thường là những thao tác không nằm trong cùng một transaction. Khi worker commit xong nhưng mất reply, hệ thống có thể cần kiểm tra/retry; writer phải lặp lại an toàn.

**5. Một worker nhận yêu cầu nhưng không đọc được `minIdInclusive`, nên kiểm tra gì?**

Kiểm tra StepExecution ID, ExecutionContext của partition, tên key, tính khả dụng của JobExplorer và bean reader có `@StepScope` hay không.

**6. Tăng số consumer trong mỗi worker có phải luôn tăng throughput không?**

Không. Nhiều consumer làm tăng concurrent transaction và kết nối DB; khi DB bão hòa, contention và rollback có thể tăng làm throughput giảm.

**7. Worker đã ghi xong nhưng manager chưa nhận reply. Có nên khởi chạy cùng StepExecution ở worker khác ngay không?**

Không nên tự động chạy lại thiếu kiểm soát. Cần xác minh StepExecution status, khả năng worker cũ còn chạy, cơ chế timeout/ack của PartitionHandler và idempotency writer.

**8. Vì sao cần thử toàn hệ thống với broker thật thay vì chỉ unit test IntegrationFlow?**

Vì lỗi serialization, routing reply, ack/redelivery, timeout và worker crash xảy ra tại ranh giới giữa các tiến trình; unit test xử lý nội bộ không kiểm chứng đầy đủ những hành vi đó.

---

**Ghi nhớ:** Với **remote partitioning**, Spring Integration flow của worker là cầu nối giữa **message request/reply** và **Spring Batch StepExecution**. Thiết kế đúng phải kết nối inbound adapter → channel → `StepExecutionRequestHandler` → reply channel → outbound adapter, đồng thời bảo đảm `JobExplorer`, `StepLocator`, `JobRepository` và worker step cùng hiểu một hợp đồng. Khi mở rộng dữ liệu lớn, tính đúng của input, idempotency, khả năng restart và tài nguyên DB quan trọng ngang với tốc độ xử lý.
