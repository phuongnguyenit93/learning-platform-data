# Partitioning từ xa bằng service trong Spring Batch

## 1. Khi một JVM không còn đủ để xử lý batch

Giả sử hệ thống phải xử lý 12 triệu giao dịch trong một cửa sổ vận hành hai giờ. Dữ liệu có thể chia thành các miền độc lập, nhưng tăng số thread trong một JVM không còn cải thiện tốc độ: CPU và heap của tiến trình đã gần giới hạn, còn hệ thống vẫn có nhiều máy khác để sử dụng. Khi đó, **remote partitioning** cho phép một tiến trình **manager** chia công việc và giao từng partition cho các **worker service** chạy trên những tiến trình, container hoặc máy khác.

Đây là chủ đề **“Partitioning từ xa bằng service”** trong chương **Partitioning** của module `SPRING_BATCH_SCALING_OPERATIONS`. Mục tiêu là mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và xử lý phân tán, đồng thời biết đo nút thắt, giữ thread safety, retry/restart, vận hành job và chọn kiến trúc theo tài nguyên thực tế.

Sau bài học, bạn có thể:

- Giải thích cách manager, message broker, worker service và `JobRepository` phối hợp.
- Thiết kế `Partitioner`, `ExecutionContext` và reader riêng cho mỗi partition.
- Lắp ghép manager step và worker step bằng Spring Batch Integration theo cơ chế request/reply.
- Phân biệt remote partitioning với local partitioning, multi-threaded step và remote chunking.
- Xử lý worker chết, request gửi lặp, phản hồi thất lạc, checkpoint và restart mà không làm sai dữ liệu.
- Chọn số partition, số service instance, giới hạn connection và timeout dựa trên đo lường.

Ví dụ dùng **Spring Batch 5.x, Java 17+, Spring Batch Integration và RabbitMQ**. Phần cấu hình transport là sơ đồ tích hợp cần bổ sung adapter, credentials và khai báo queue trong ứng dụng thật. Không có cơ chế phân tán nào tự động bảo đảm mọi tác động nghiệp vụ xảy ra chính xác một lần.

## 2. Kiến trúc và ranh giới trách nhiệm

**Remote partitioning** là phiên bản phân tán của partitioned step. Manager quyết định **phần việc nào cần chạy**; worker quyết định **đọc, xử lý và ghi phần việc đó như thế nào**. Worker không cần manager gửi toàn bộ dữ liệu từng item, vì nó có thể dùng ranh giới partition để tự đọc từ nguồn.

~~~mermaid
flowchart TD
    S[Scheduler hoặc JobLauncher] --> M[Manager service<br/>Job + partition manager step]
    M --> P[Partitioner<br/>Tạo tên và ExecutionContext]
    P --> JR[(Shared JobRepository)]
    M --> RQ[(Request queue)]
    RQ --> W1[Worker service A<br/>worker step]
    RQ --> W2[Worker service B<br/>worker step]
    RQ --> W3[Worker service C<br/>worker step]
    W1 --> D[(Nguồn và đích dữ liệu)]
    W2 --> D
    W3 --> D
    W1 <--> JR
    W2 <--> JR
    W3 <--> JR
    W1 --> AQ[(Reply queue)]
    W2 --> AQ
    W3 --> AQ
    AQ --> M
    M <--> JR
~~~

| Thành phần | Nhiệm vụ | Trạng thái cần lưu |
|---|---|---|
| **Manager service** | Khởi chạy job, gọi `Partitioner`, gửi yêu cầu và tổng hợp kết quả | `JobExecution`, manager `StepExecution`, danh sách partition |
| **Partitioner** | Chia dữ liệu thành những miền xác định, độc lập | Tên partition và các tham số trong `ExecutionContext` |
| **Request/reply middleware** | Phân phối yêu cầu cho worker và mang kết quả về manager | Message bền vững, correlation, ACK/redelivery |
| **Worker service** | Nhận yêu cầu, chạy worker step trên vùng dữ liệu được giao | Checkpoint, các lần commit/rollback, trạng thái `StepExecution` |
| **Shared JobRepository** | Nguồn sự thật về metadata thực thi của Spring Batch | `JobInstance`, `JobExecution`, `StepExecution`, `ExecutionContext` |
| **Nguồn/đích nghiệp vụ** | Đọc item, lưu kết quả hoặc phát sự kiện | Khóa nghiệp vụ, giao dịch, cơ chế idempotency |

Một service worker có thể nhận nhiều partition **tuần tự** hoặc **đồng thời** tùy listener concurrency và executor của nó. Việc manager tạo 20 partition không có nghĩa cần 20 pod hoặc 20 TCP connection.

### Điểm khác biệt với các mô hình scale khác

| Cơ chế | Đơn vị được thực thi song song | Hệ quả |
|---|---|---|
| **Multi-threaded step** | Chunk cùng thuộc một `StepExecution` | Cần kiểm tra các component được chia sẻ và thứ tự xử lý |
| **Parallel steps** | Những step/flow độc lập | Phù hợp khi workflow có nhánh xử lý khác nhau |
| **Local partitioning** | Nhiều `StepExecution` trong một JVM | Không có tầng message broker hay worker process riêng |
| **Remote partitioning** | Nhiều `StepExecution` trên các service worker | Mỗi worker tự đọc dữ liệu của partition, cần metadata và transport nhất quán |
| **Remote chunking** | Chunk được manager đọc rồi gửi qua broker | Manager thường là điểm đọc tập trung; worker xử lý chunk được gửi tới |

Chọn **remote partitioning** khi dữ liệu có thể chia độc lập và mỗi worker truy cập trực tiếp nguồn/đích của mình. Nếu từng item bắt buộc do một manager duy nhất đọc và phân phối, hãy đánh giá remote chunking; đó là một hợp đồng thực thi khác.

## 3. Vòng đời một partition từ xa

Giả sử manager phải xử lý các ID `1..1.200.000` và lập 12 partition. Hệ thống có 4 worker service instance, mỗi instance xử lý một partition tại một thời điểm.

1. **Manager khởi chạy job.** `JobRepository` tạo `JobExecution` dựa trên identifying `JobParameters`, chẳng hạn `businessDate=2026-11-26`.
2. **Partitioner tạo 12 vùng.** Mỗi tên ổn định như `partition0`, `partition1` có `ExecutionContext` chứa `minId`/`maxId`. Spring Batch ghi metadata của các worker `StepExecution`.
3. **Manager phát request.** Với Spring Batch Integration, request thường là `StepExecutionRequest` chứa tên worker step, `jobExecutionId` và `stepExecutionId`. Worker lấy các giá trị partition bằng metadata đã được lưu, thay vì phải tin vào bản sao ranh giới do message tự mang.
4. **Một worker nhận request.** Nó xác định đúng `StepExecution`, khởi tạo các bean scope theo step và chạy worker step theo chunk.
5. **Worker checkpoint.** Từng chunk thành công commit transaction; trạng thái đọc, metric và `ExecutionContext` được lưu theo `StepExecution` tương ứng.
6. **Worker kết thúc và phản hồi.** Kết quả được ghi vào repository và chuyển về manager qua reply flow được cấu hình.
7. **Manager tổng hợp.** Manager step chỉ hoàn tất theo cơ chế aggregation khi các partition cần thiết đã đạt trạng thái phù hợp; nếu lỗi hoặc timeout, job cần được vận hành và restart theo chính sách rõ ràng.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant R as JobRepository
    participant Q as Message broker
    participant W as Worker service
    participant D as Business DB
    M->>R: Tạo JobExecution và partition StepExecutions
    M->>Q: Gửi StepExecutionRequest(stepExecutionId)
    Q->>W: Phân phối yêu cầu
    W->>R: Tải StepExecution và ExecutionContext
    loop Theo từng chunk
        W->>D: Đọc / xử lý / ghi vùng được giao
        W->>R: Lưu checkpoint sau commit
    end
    W->>R: Cập nhật trạng thái StepExecution
    W->>Q: Gửi reply về manager
    Q->>M: Chuyển reply / kết quả
    M->>R: Tổng hợp trạng thái manager step
~~~

> **Điểm cốt lõi:** broker chuyển **lệnh thực thi**, còn `JobRepository` lưu **trạng thái thực thi**. Một message được ACK không đồng nghĩa dữ liệu nghiệp vụ đã đúng; một reply bị mất cũng không đủ chứng minh worker chưa hoàn thành.

## 4. Thiết kế Partitioner ổn định và không chồng lấn

### Quy tắc chia vùng

Với cột khóa chính tăng `id`, mỗi worker có thể đọc một khoảng đóng `[minId, maxId]`. Một partition plan đúng nên thỏa mãn:

1. **Không trùng:** hai partition không cùng sở hữu một ID.
2. **Không hụt:** hợp các khoảng phủ đủ miền dự kiến; việc ID trong bảng bị khuyết không làm mất bản ghi.
3. **Dễ tái tạo:** cùng một job instance và cutoff phải có tên partition, thứ tự và ranh giới ổn định khi restart.
4. **Không phụ thuộc số pod:** scale worker service không được làm thay đổi partition plan đang chạy.
5. **Phân bố tải hợp lý:** độ rộng khoảng ID bằng nhau không đảm bảo số record hoặc chi phí xử lý bằng nhau.

Ví dụ `Partitioner` sau phân phối cả phần dư khi số ID không chia hết cho `gridSize`:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class OrderIdPartitioner implements Partitioner {
    private final long firstId;
    private final long lastId;

    public OrderIdPartitioner(long firstId, long lastId) {
        if (firstId > lastId) {
            throw new IllegalArgumentException("ID range must not be empty");
        }
        this.firstId = firstId;
        this.lastId = lastId;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        long total = Math.addExact(Math.subtractExact(lastId, firstId), 1);
        int count = (int) Math.min((long) gridSize, total);
        long base = total / count;
        long remainder = total % count;

        Map<String, ExecutionContext> plan = new LinkedHashMap<>();
        long start = firstId;
        for (int i = 0; i < count; i++) {
            long size = base + (i < remainder ? 1 : 0);
            long end = Math.addExact(start, size - 1);

            ExecutionContext ctx = new ExecutionContext();
            ctx.putLong("minId", start);
            ctx.putLong("maxId", end);
            plan.put("partition" + i, ctx);

            if (i + 1 < count) {
                start = Math.addExact(end, 1);
            }
        }
        return plan;
    }
}
~~~

Nếu `firstId=1`, `lastId=11` và `gridSize=3`, kết quả là `1..4`, `5..8`, `9..11`. Mỗi ID thuộc một vùng; hàm chỉ tính ranh giới, **không tạo thread hoặc service**. Với nguồn rỗng, cần xử lý riêng bằng skip/no-op; ví dụ giả định miền ID không rỗng và kiểm tra tràn `long` bằng `Math.addExact`.

Trong thực tế, `firstId`/`lastId` hoặc danh sách khóa nên được **chốt theo job instance**, từ snapshot, cutoff hay bảng manifest. Không dùng một lần `MAX(id)` mới khi restart nếu dữ liệu đã thay đổi trong thời gian đó.

### Chọn một chiến lược theo hình dạng dữ liệu

| Cách chia | Ưu điểm | Rủi ro / biện pháp |
|---|---|---|
| Khoảng ID | Dễ kiểm chứng không trùng; query theo index | ID phân bố không đều, worker có thể lệch tải |
| Khoảng theo thời gian | Thuận tiện cho dữ liệu có ngày/giờ và partition pruning | Event đến muộn, ranh giới timezone, timestamp trùng |
| Băm khóa `hash(key) % N` | Có thể phân bố đều nếu hash tốt | Truy vấn khó tận dụng range index, `N` phải ổn định khi restart |
| Manifest gồm nhóm ID/file | Chốt tập công việc rõ, hỗ trợ dữ liệu thưa/skew | Thêm chi phí lập kế hoạch và lưu manifest |
| Phân vùng theo tenant | Cô lập tenant, thuận tiện quan sát | Tenant lớn áp đảo các tenant nhỏ |

Nếu 80% bản ghi nằm trong một khoảng ID, tăng số service instance sẽ không giải quyết partition chậm nhất. Cần chia lại theo số record, giá trị khóa hoặc ước lượng chi phí trước khi tăng concurrency.

## 5. Cấu hình Spring Batch Integration: manager và worker service

Đây là **khung tích hợp Spring Batch 5.x** giúp nhìn rõ ranh giới trách nhiệm. Ứng dụng thực tế cần khai báo `JobRepository`, transaction manager, message channel, inbound/outbound adapter, queue, credential và các bean reader/writer. Tùy phiên bản Spring Batch Integration, API builder và cấu hình adapter có thể khác nhau; nên biên dịch và chạy thử trên phiên bản đã khóa trong dự án.

### Các dependency và service cần có

Thông thường sử dụng Spring Batch core, `spring-batch-integration`, Spring Integration cùng adapter cho broker cụ thể, thư viện JDBC/driver, và các thành phần Spring Boot tương ứng. Để tránh version conflict, quản lý các dependency Spring Batch/Spring Integration theo BOM hoặc dependency management của phiên bản Spring Boot đang dùng. Hai service cần dùng **schema metadata Spring Batch tương thích**.

Tách hai ứng dụng logic:

~~~text
manager-service
  Job / JobLauncher
  Partitioner + RemotePartitioningManagerStepBuilder
  outboundRequests -> broker request queue
  broker reply queue -> inboundReplies
  JobRepository

worker-service
  broker request queue -> inboundRequests
  RemotePartitioningWorkerStepBuilder
  step-scoped reader + processor + writer
  outboundReplies -> broker reply queue
  JobRepository (cùng metadata DB)
~~~

Tên `workerStep` phía manager phải trùng tên worker step thực tế phía service worker. Không khởi động một job mới cho mỗi request; worker xử lý `StepExecution` mà manager đã tạo.

### Manager: tạo các yêu cầu remote partition

Ví dụ dựng manager step với các bean đã được cung cấp (phần khởi tạo channel/broker được minh họa riêng):

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.integration.partition.RemotePartitioningManagerStepBuilder;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.messaging.MessageChannel;

// Trong cấu hình @Configuration của manager:
@Bean
Step partitionManagerStep(
        JobRepository jobRepository,
        Partitioner orderIdPartitioner,
        @Qualifier("outboundRequests") MessageChannel requests,
        @Qualifier("inboundReplies") MessageChannel replies) {

    return new RemotePartitioningManagerStepBuilder(
            "partitionManagerStep", jobRepository)
        .partitioner("processOrdersWorkerStep", orderIdPartitioner)
        .gridSize(12)
        .outputChannel(requests)
        .inputChannel(replies)
        .build();
}
~~~

Một bean `Job` bắt đầu bằng `partitionManagerStep`. `gridSize(12)` là đề nghị chia thành 12 phần, còn `Partitioner` quyết định số entry thực tế trong `Map`. Số pod và thread nhận request do deployment/listener quy định, không phải do `gridSize`.

Ngoài cơ chế nhận reply qua channel, một số cấu hình remote partitioning có thể chọn cơ chế manager theo dõi kết quả trong repository. Dù dùng cách nào, phải kiểm soát cách aggregation kết thúc, polling/timeout, trường hợp reply muộn và tính nhất quán của trạng thái.

### Worker: tạo đúng reader cho mỗi StepExecution

Giả sử bảng nghiệp vụ đơn giản:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    processed BOOLEAN NOT NULL DEFAULT FALSE
);
~~~

Reader lấy ranh giới từ `stepExecutionContext`. Annotation `@StepScope` tạo bean theo worker `StepExecution`, thay vì sử dụng chung một cursor giữa nhiều partition. SQL sắp xếp theo khóa duy nhất để checkpoint ổn định.

~~~java
import javax.sql.DataSource;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
JdbcCursorItemReader<Long> ordersReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new JdbcCursorItemReaderBuilder<Long>()
        .name("ordersRangeReader")
        .dataSource(dataSource)
        .sql("SELECT id FROM orders "
           + "WHERE id >= ? AND id <= ? ORDER BY id")
        .preparedStatementSetter(ps -> {
            ps.setLong(1, minId);
            ps.setLong(2, maxId);
        })
        .rowMapper((rs, n) -> rs.getLong("id"))
        .build();
}
~~~

Ví dụ writer cập nhật giá trị cố định nên **lặp lại cùng ID không tạo hiệu ứng mới**:

~~~java
import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@Bean
JdbcBatchItemWriter<Long> ordersWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Long>()
        .dataSource(dataSource)
        .sql("UPDATE orders SET processed = TRUE WHERE id = :id")
        .itemSqlParameterSourceProvider(
            id -> new MapSqlParameterSource("id", id))
        .build();
}
~~~

SQL reader cố ý **không thêm điều kiện `processed = FALSE`**, vì writer đang thay đổi cột đó trong lúc đọc. Lọc theo một trạng thái bị cập nhật có thể khiến tập kết quả di chuyển, đặc biệt với paging reader hoặc khi checkpoint theo vị trí, dẫn đến skip/duplicate trong lúc restart. Hệ thống thật còn cần kiểm soát snapshot/cutoff để không nhận bản ghi mới giữa một job instance.

Worker step cấu hình theo request channel:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.integration.partition.RemotePartitioningWorkerStepBuilder;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.messaging.MessageChannel;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step processOrdersWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        @Qualifier("inboundRequests") MessageChannel requests,
        @Qualifier("outboundReplies") MessageChannel replies,
        JdbcCursorItemReader<Long> ordersReader,
        JdbcBatchItemWriter<Long> ordersWriter) {

    return new RemotePartitioningWorkerStepBuilder(
            "processOrdersWorkerStep", jobRepository)
        .inputChannel(requests)
        .outputChannel(replies)
        .<Long, Long>chunk(250, transactionManager)
        .reader(ordersReader)
        .writer(ordersWriter)
        .build();
}
~~~

Trong ví dụ, mỗi partition xử lý chunk tối đa 250 item. `chunk size` ảnh hưởng số item trong một transaction; nó **không quyết định** số worker service. Cả manager và worker dùng chung `JobRepository`, nhưng từng worker cần bean và connection pool của chính tiến trình.

### Nối các channel với message broker

Trong Spring Integration, một cách phổ biến là:

~~~text
MANAGER:
  outboundRequests --(AMQP outbound adapter)--> queue batch.partition.requests
  inboundReplies  <--(AMQP inbound adapter)--- queue batch.partition.replies

WORKER:
  inboundRequests <--(AMQP inbound adapter)--- queue batch.partition.requests
  outboundReplies --(AMQP outbound adapter)--> queue batch.partition.replies
~~~

Đây là sơ đồ **định tuyến**, không phải code tự động khai báo queue. Cần cấu hình adapter/integration flow với `ConnectionFactory`, serialization converter, delivery mode, consumer concurrency, acknowledgment, error channel và policy xử lý message lỗi. Queue/request cần durability phù hợp; reply phải có correlation với execution và phải đến đúng manager khi có nhiều lần chạy song song.

**Một điểm dễ nhầm:** mặc định Spring Batch Integration truyền `StepExecutionRequest` (có các ID của metadata); đừng tự phát một JSON gồm cả dữ liệu nghiệp vụ rồi xem đó là remote partitioning chuẩn. Nếu tự xây giao thức service-to-service qua HTTP/gRPC, phải tự xử lý correlation, lease, duplicate dispatch, restart và cập nhật metadata tương đương. Broker hỗ trợ redelivery, nhưng không bảo vệ ứng dụng khỏi chạy hai bản sao cùng một partition khi xử lý ACK sai.

## 6. Vận hành các worker như một service thật sự

### Đóng gói và triển khai

Có thể chọn **cùng một image với profile manager/worker**, hoặc tách thành hai image riêng. Tách image giúp cấp quyền và release độc lập; dùng cùng image đơn giản hóa tương thích. Trong cả hai trường hợp, worker **không được tự khởi chạy toàn bộ job** khi ứng dụng boot:

~~~yaml
# application-worker.yml: cấu hình minh họa
spring:
  batch:
    job:
      enabled: false

app:
  batch:
    request-queue: batch.partition.requests
    reply-queue: batch.partition.replies
    consumer-concurrency: 2
~~~

Các khóa `app.batch.*` là **thuộc tính ứng dụng tự định nghĩa**, cần binding sang Integration adapter. Chúng không tự tạo queue, listener hoặc channel. `spring.batch.job.enabled=false` vô hiệu việc Spring Boot tự launch job lúc startup, phù hợp với worker service chỉ chờ message.

Với Kubernetes, topology thực tế thường là:

- **Manager** chạy dưới dạng `Job` theo lịch, workflow hoặc lệnh điều hành. Nó tồn tại đủ lâu để nhận kết quả cuối cùng.
- **Worker** chạy trong `Deployment` luôn sẵn sàng tiêu thụ request; có thể scale replicas theo queue depth hoặc lịch.
- **Broker và JobRepository** có vòng đời riêng, dùng storage/durability thích hợp thay vì nằm trong container của một job ngắn.
- Tài nguyên `requests/limits`, `readiness`, `terminationGracePeriodSeconds`, log correlation, secret và network policy được cấu hình cho từng role.

~~~mermaid
flowchart LR
    CJ[CronJob hoặc orchestration] --> MJ[Kubernetes Job<br/>Manager]
    MJ --> Q[(Durable request queue)]
    Q --> DP[Worker Deployment]
    DP --> A[Pod A]
    DP --> B[Pod B]
    DP --> C[Pod C]
    MJ --> Repo[(Metadata DB)]
    A --> Repo
    B --> Repo
    C --> Repo
~~~

Autoscale worker không làm manager lập lại partition plan. Khi worker thay đổi số lượng, các partition đang chờ được phân phối theo capacity hiện có; điều kiện là message transport đủ bền vững, việc shutdown/drain đúng và không chồng chéo partition đã chạy.

### Tính concurrency và ngân sách connection

Giả sử:

- Manager tạo `P = 24` partition.
- Hệ thống có `N = 4` worker pod đang hoạt động.
- Mỗi pod cho phép `L = 2` partition chạy đồng thời.
- Mỗi partition có thể dùng một JDBC connection cho transaction và một reader cursor connection tùy reader/transaction configuration.

Trần lý thuyết của số partition chạy đồng thời là:

\[
C_{\mathrm{max}} = \min(P, N \times L) = \min(24, 4 \times 2) = 8
\]

Nếu tăng lên 8 pod mà giữ `L=2`, trần tăng thành 16, nhưng database, pool, IOPS và lock wait phải đủ sức. Ví dụ này cho thấy **số partition là mức chia việc, số worker là năng lực phục vụ**; không dùng một con số cho cả hai mục đích.

Ngân sách kết nối nên tính theo cả cụm:

\[
C_{\mathrm{DB,total}} \approx
N_{\mathrm{pods}}\times C_{\mathrm{perPod}} +
C_{\mathrm{manager}} + C_{\mathrm{otherServices}}
\]

Đây là **ước lượng về số connection có thể được mở**, không phải khẳng định chúng luôn active. Reader cursor có thể chiếm connection ngoài transaction tùy loại reader; cần đo trực tiếp active/idle/pending trên JDBC pool và server DB. Đồng thời, broker có giới hạn connection/channel, consumer prefetch, message in-flight và khả năng phục vụ riêng. Không tăng song song chỉ vì CPU worker còn trống.

### Backpressure thay vì tạo vô hạn việc đang chạy

Khi broker xếp hàng nhanh hơn worker xử lý, phải chọn giới hạn thực tế:

- `gridSize` đủ lớn để các worker không bị đói việc nhưng không tạo quá nhiều `StepExecution` và metadata.
- Listener concurrency có giới hạn; không dùng unbounded executor hoặc queue nội bộ tăng vô hạn.
- Giới hạn pending message, prefetch, pool connections và số retry đồng thời theo ngân sách.
- Nếu downstream áp quota, dùng rate limiter/circuit breaker/throttle phù hợp ở worker.
- Khi queue tăng, xác định nguyên nhân: thiếu worker, partition skew, SQL chậm, DB lock hoặc broker nghẽn.

## 7. Retry, restart và các tình huống lỗi phân tán

Remote partitioning tạo thêm vùng lỗi giữa **broker, worker, repository và dữ liệu nghiệp vụ**. Các thao tác đó thường không nằm trong một giao dịch phân tán duy nhất.

| Tình huống | Hiện tượng | Phản ứng an toàn |
|---|---|---|
| Worker chết trước khi nhận request | Request vẫn đang chờ trong queue | Consumer khỏe khác nhận theo cơ chế broker |
| Worker chết giữa chunk | Chunk chưa commit rollback; chunk trước có thể đã commit | Restart từ checkpoint; kiểm chứng writer idempotent |
| Worker commit dữ liệu nhưng chưa ACK request | Broker có thể phát lại message | Không chạy trùng `StepExecution` đồng thời; ghi lặp phải an toàn |
| Reply về manager thất lạc | Metadata có thể `COMPLETED` nhưng manager chờ timeout | Đối chiếu `JobRepository` và correlation, tránh tự dispatch trùng mù quáng |
| Manager service ngừng giữa job | Worker có thể còn chạy | Đảm bảo không có hai manager cùng điều phối một execution; khôi phục và đối soát trạng thái |
| Broker mất kết nối | Request/reply trễ, một số message redelivered | Timeout hữu hạn, retry có backoff, quan sát queue và DLQ |
| Input đổi khi restart | Vùng ID/tập dữ liệu thay đổi | Khóa plan/cutoff theo `JobInstance` và giữ naming nhất quán |
| Phiên bản worker khác nhau | Một worker không hiểu metadata/schema mới | Tương thích rolling upgrade hoặc versioned queue/protocol |

### StepExecution và cơ chế chống thực thi kép

Mỗi partition có `StepExecution` riêng, nhưng việc broker phát lại một request **không tự đảm bảo an toàn**. Nếu worker cũ vẫn đang xử lý sau khi mất mạng mà broker giao cùng partition cho worker mới, có nguy cơ tác động nghiệp vụ hai lần. Cần:

1. Điều phối chỉ một worker được thực thi cùng `StepExecution` tại một thời điểm theo thiết kế consumer, trạng thái và chính sách recovery.
2. Dùng ràng buộc nghiệp vụ ở đích: unique key, upsert, compare-and-set, bảng deduplication hoặc idempotency key.
3. Khi stop/redeploy worker, ngừng nhận việc mới và drain các task hiện tại theo deadline hữu hạn.
4. Chỉ requeue hoặc reset trạng thái thủ công sau khi xác minh không còn worker cũ hoạt động.

Đối với side effect như gửi email, gọi API thanh toán hay publish message, `JobRepository` không thể bảo đảm exactly-once giữa nhiều hệ thống. Dùng **transactional outbox**, request ID bất biến, idempotency ở downstream và đối soát kết quả khi cần.

### Restart đúng JobInstance

Spring Batch xác định `JobInstance` dựa trên job name và identifying `JobParameters`. Nếu job dùng `businessDate=2026-11-26` rồi thất bại ở 2/12 partition, restart cần **cùng identifying parameters** để dùng metadata trước đó. Tự thêm một `run.id` mới thường tạo job instance khác và có thể làm chạy lại cả những phần đã hoàn thành.

Với reader `ItemStream` restartable, tên stream ổn định, SQL ordering ổn định và partition plan không đổi, worker có thể tiếp tục từ checkpoint lưu trong `ExecutionContext` theo chính sách của step. Partition đã `COMPLETED` có thể không phải chạy lại trên một restart thông thường. Không tự coi tất cả side effect đều được bảo đảm đúng một lần chỉ vì checkpoint tồn tại.

### Tác động của retry storm

Nếu hàng chục worker cùng gặp database timeout và retry ngay, hệ thống có thể tăng tải đúng vào điểm nghẽn. Đặt retry giới hạn, backoff và jitter, phân biệt lỗi tạm thời với lỗi dữ liệu, ghi nhận skip nếu được phép. Khi chờ network/pool trong transaction quá lâu, worker có thể giữ lock và connection database; nên giới hạn timeout và cân nhắc tách bước ghi outbox khỏi bước phát sự kiện.

## 8. Giám sát và chẩn đoán bottleneck

Đo hiệu quả theo **wall-clock time, throughput và tính đúng dữ liệu**, không chỉ số pod hoặc số message/giây. Các chỉ số chính:

| Lớp | Cần quan sát | Gợi ý xử lý nếu bất thường |
|---|---|---|
| Manager | Tổng partition, `COMPLETED`/`FAILED`/`STARTED`, manager duration, timeout, reply correlation | Xác định partition chưa hoàn tất hoặc mất phản hồi |
| Worker | `readCount`, `writeCount`, commit/rollback, retry/skip, duration theo `StepExecution` | Tìm partition chậm, reader checkpoint lỗi |
| Queue | Pending, unacked, redelivery, DLQ, consumer count, oldest-message age | Phân biệt thiếu consumer với broker nghẽn |
| Database | JDBC pool active/pending, SQL latency, lock wait, DB CPU/IOPS | Giảm concurrency hoặc tối ưu SQL/index trước khi tăng worker |
| JVM/Kubernetes | CPU, heap, GC, pod restarts, OOMKilled, throttling, health checks | Tìm lỗi tài nguyên của từng service |
| Nghiệp vụ | Số bản ghi kỳ vọng/đã xử lý, trùng ID, thiếu event, độ trễ cutoff | Xác minh tính đúng sau restart và phát lại |

Gắn vào log các giá trị `jobExecutionId`, `stepExecutionId`, `partitionName`, `stepName` và `workerInstanceId` để truy ngược một item tới đúng lần thực thi. Một lỗi SQL tại worker có thể không xuất hiện chi tiết trong log của manager.

### Runbook: manager báo timeout một partition

1. Tìm `stepExecutionId` liên quan trong `JobRepository` và xem status, checkpoint, commit time cuối.
2. Kiểm tra message request/reply, unacked và dead-letter; xác định request thực tế đã vào worker nào.
3. Đối chiếu worker log/health với metadata để xem worker còn chạy hay đã chết.
4. Nếu worker còn hoạt động, không phát lại cùng partition theo kiểu thủ công. Nếu worker đã chết, kiểm tra chunk đã commit và điều kiện restart.
5. Khôi phục cùng job instance/partition plan theo cơ chế của ứng dụng; không thay đổi range hay tạo job instance mới chỉ để vượt qua một timeout.
6. Sau khi hoàn tất, đối soát dữ liệu nghiệp vụ, nhất là side effect có thể thực hiện trùng.

### Thử hiệu năng có kiểm soát

Chạy cùng một snapshot dữ liệu ở các mức 1, 2, 4, 8 worker đồng thời. Ghi thời gian chạy `T_p`; speedup và efficiency:

\[
S(p) = \frac{T_1}{T_p},\qquad E(p) = \frac{S(p)}{p}
\]

Ví dụ một worker mất 100 phút, bốn worker mất 34 phút thì `S(4) \approx 2{,}94` và `E(4) \approx 0{,}74`. Nếu tăng từ 4 lên 8 mà thời gian gần như không đổi, ưu tiên tìm SQL lock, network, broker latency, skew partition, GC hoặc thời gian chờ pool trước khi tăng thêm replica.

## 9. Bảo mật, tương thích phiên bản và vận hành service

Tách service giúp scale nhưng cũng mở rộng bề mặt vận hành:

- **Quyền tối thiểu:** manager có quyền publish request và nhận reply; worker nhận request, publish reply và chỉ truy cập bảng dữ liệu cần xử lý. Cả hai cần quyền phù hợp với schema metadata `JobRepository`.
- **Kết nối an toàn:** TLS tới database/broker; credentials nằm trong secret manager hoặc runtime secret, không hardcode trong image, message hay log.
- **Network policy:** hạn chế traffic giữa worker với hệ thống không liên quan; bảo vệ cả metadata DB.
- **Phiên bản schema/protocol:** manager và worker cùng chạy được với metadata schema, tên step, serializer và kiểu `ExecutionContext`. Khi rolling upgrade, phải có chiến lược tương thích hoặc tách queue theo phiên bản.
- **Graceful shutdown:** giảm/đóng listener trước khi đóng datasource/broker; chờ task đang chạy hoàn thành trong giới hạn vận hành hoặc chủ động tạo trạng thái để restart an toàn.
- **Giới hạn toàn cụm:** tổng pool DB, channel broker, worker concurrency và retry phải nằm trong sức chịu của hệ thống; autoscale không tự điều chỉnh quota.
- **Quan sát:** dashboard cho manager, worker, broker, database và kết quả nghiệp vụ, kèm cảnh báo partition chạy quá lâu hoặc message cũ bất thường.

Với broker nhận lại message, chính sách ACK cần gắn với kết quả xử lý an toàn. ACK quá sớm có thể làm mất yêu cầu khi worker chết; ACK quá muộn có thể làm request bị phát lại sau khi dữ liệu đã commit. Đây là lý do thiết kế idempotency phải tồn tại ngay cả khi đã cấu hình retry/restart.

## 10. Quyết định kiến trúc theo tài nguyên thực tế

| Điều kiện | Phương án nên cân nhắc |
|---|---|
| Một JVM chưa bão hòa và chỉ cần thêm thread | Local partitioning hoặc multi-threaded step, sau khi kiểm tra thread safety |
| Dữ liệu chia độc lập, worker có thể tự đọc và ghi từ nhiều máy | **Remote partitioning** |
| Manager đọc dữ liệu tập trung, muốn phân tán xử lý theo chunk | Remote chunking |
| Các quy trình độc lập có thể chạy song song | Parallel steps/flows |
| Database đã là bottleneck và không còn dư IOPS/connection | Tối ưu truy vấn/transaction trước; thêm worker có thể làm chậm hơn |
| Chưa có JobRepository dùng chung, broker bền vững và khả năng đối soát | Cân nhắc triển khai đơn giản hơn cho đến khi có nền tảng vận hành |

Remote partitioning hữu ích nhất khi một partition là **đơn vị công việc đủ lớn và độc lập**, chi phí truyền request nhỏ hơn nhiều chi phí xử lý, và hệ thống có khả năng thu hồi chính xác từ checkpoint khi worker gặp sự cố.

## 11. Checklist thực hành

- [ ] Partition plan có tên ổn định, không overlap, có cutoff/snapshot rõ ràng.
- [ ] Manager và worker dùng `JobRepository` và metadata schema tương thích.
- [ ] `StepExecutionRequest` mang đúng định danh; worker đọc `ExecutionContext` của chính step đó.
- [ ] Request/reply queue có durability, correlation, timeout và DLQ phù hợp.
- [ ] Reader stateful dùng `@StepScope`; writer và bean singleton được kiểm tra thread safety.
- [ ] Chỉ một worker thực thi cùng partition tại một thời điểm theo thiết kế; duplicate request vẫn an toàn với dữ liệu nghiệp vụ.
- [ ] Restart sử dụng cùng identifying `JobParameters` và checkpoint; side effect có idempotency.
- [ ] Pool, concurrency, prefetch và retry được giới hạn theo ngân sách toàn cụm.
- [ ] Có metric và log theo `jobExecutionId`/`stepExecutionId`/partition/worker instance.
- [ ] Đã thử worker chết giữa chunk, mất reply, broker reconnect, manager restart và rolling deployment.

## 12. Bài tập và câu hỏi tự kiểm tra

### Bài tập 1 — Chia 1.001 bản ghi

Với miền ID `1..1001`, `gridSize=6`, hãy tính ranh giới từng partition do `OrderIdPartitioner` sinh ra. Viết kiểm tra xác nhận không ID nào bị trùng hoặc bỏ sót, và giải thích vì sao sáu partition có thể được thực thi bởi hai worker service.

### Bài tập 2 — Thiết kế sơ đồ service

Tạo manager chạy dưới dạng một job theo lịch và worker chạy thành ba service instance. Vẽ request/reply queue, metadata DB và nguồn nghiệp vụ. Đánh dấu ai cần quyền đọc/ghi vào đâu, cùng nơi cấu hình TLS/secret và metric.

### Bài tập 3 — Thử fault injection

Khi một worker đang xử lý partition, cố tình dừng process sau vài chunk commit. Quan sát metadata, queue redelivery và dữ liệu nghiệp vụ; restart cùng `JobInstance`. Thiết kế điều kiện ngăn hai worker cùng thực thi một partition và phép đối soát tính đúng.

### Bài tập 4 — Đo nút thắt

Manager tạo 32 partition. Mỗi worker pod xử lý tối đa hai partition. Chạy các mức 2, 4 và 8 pod, đo duration, read/write count, JDBC wait, broker queue age và thời gian partition chậm nhất. Giải thích tại sao nâng lên tám pod chưa chắc tăng throughput nếu bảng nguồn bị lock contention.

**Câu hỏi tự kiểm tra:** Vì sao `gridSize` không phải số service instance? Vì sao manager và worker cần hiểu cùng `stepName` và cùng metadata? Khi reply thất lạc, vì sao không nên gửi lại request ngay? Điều gì phân biệt restart một job instance với khởi chạy một job instance mới? Khi dùng HTTP/gRPC thay message broker, hệ thống phải tự bổ sung những cơ chế điều phối nào?

**Kết luận:** Partitioning từ xa bằng service cho phép Spring Batch mở rộng từ nhiều thread trong một JVM sang nhiều tiến trình có khả năng scale độc lập. Thiết kế thành công phải đồng thời bảo đảm **phân vùng đúng, metadata nhất quán, vận chuyển request/reply tin cậy, checkpoint có thể phục hồi và tác động nghiệp vụ idempotent**. Tăng số worker chỉ có ý nghĩa khi dữ liệu, broker, database và ngân sách tài nguyên thực tế cùng cho phép.
