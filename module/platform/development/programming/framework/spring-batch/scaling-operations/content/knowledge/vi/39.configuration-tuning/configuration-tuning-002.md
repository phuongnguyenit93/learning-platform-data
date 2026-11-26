# Chọn pool size theo IO trong Spring Batch

Trong các job xử lý dữ liệu lớn, tăng số thread từ 4 lên 32 có thể cải thiện throughput nếu worker đang **đợi I/O**, nhưng cũng có thể làm throughput giảm khi database hết connection, khóa ghi tranh chấp hoặc dịch vụ bên ngoài giới hạn request. Vì vậy, **pool size** không có một con số tối ưu áp dụng cho mọi Spring Batch job; nó phụ thuộc vào tỷ lệ **thời gian dùng CPU / thời gian chờ I/O**, giới hạn của các tài nguyên dùng chung và cách job phân phối công việc.

Bài học thuộc chương **Tối ưu cấu hình** của module **SPRING_BATCH_SCALING_OPERATIONS**. Mục tiêu của module là mở rộng Spring Batch bằng multi-threaded step, parallel steps, partitioning và xử lý phân tán dựa trên tài nguyên thực tế, đồng thời bảo đảm thread safety, retry/restart và vận hành ổn định. Nội dung ở đây tập trung vào cách **chọn pool size theo IO** bằng số đo, công thức gần đúng, cấu hình Spring Batch và phép thử tải có kiểm soát.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt thread pool của Spring Batch với JDBC connection pool, HTTP connection pool và số worker phân tán.
2. Ước lượng mức song song hữu ích từ thời gian CPU và I/O wait; biết khi nào áp dụng Little's law.
3. Tính ngân sách connection để tránh tăng concurrency vượt giới hạn database hoặc API bên ngoài.
4. Cấu hình `TaskExecutor` và HikariCP theo nhu cầu của multi-threaded step hoặc partitioned step.
5. Thực hiện benchmark tăng tải từng bước, phát hiện điểm bão hòa và chọn một cấu hình có khoảng dự phòng.
6. Nhận diện rủi ro mất restartability, chia sẻ state giữa thread và tăng pool khiến lỗi timeout, deadlock hoặc retry lan rộng.

## 2. Trước tiên phải biết đang chọn pool nào

Một Spring Batch job thường có **nhiều lớp giới hạn concurrency**:

| Lớp | Ví dụ | Quy định điều gì? | Cạm bẫy |
| --- | --- | --- | --- |
| **Worker thread pool** | `ThreadPoolTaskExecutor` | Số tác vụ/chunk/partition có thể được thực thi đồng thời trong cùng JVM | Thêm thread khi writer đang nghẽn DB chỉ làm thêm tác vụ chờ |
| **JDBC connection pool** | HikariCP `maximumPoolSize` | Số kết nối DB đồng thời tối đa mà **một pool** cấp ra | Không tính tổng số pool từ nhiều process/pod và các ứng dụng khác |
| **HTTP client connection pool** | Connection manager của HTTP client | Số connection tới API/host có thể sử dụng đồng thời | Nhiều thread nhưng HTTP max connections thấp tạo hàng đợi ẩn |
| **Remote worker concurrency** | Số worker JVM/pod × consumer/threads mỗi worker | Tổng tác vụ phân tán có thể chạy | Nhân số pod làm tổng áp lực DB và API tăng |
| **Broker prefetch / in-flight** | Kafka partitions, RabbitMQ prefetch | Số message có thể được phân phối và chưa hoàn tất | Backlog dịch chuyển từ queue sang bộ nhớ worker |
| **Giới hạn phía đích** | DB max connections, API rate limit, IOPS | Năng lực chịu tải thực của hệ thống được gọi | Pool ứng dụng không thể mở rộng tài nguyên phía đích |

Trong **multi-threaded step**, `TaskExecutor` điều khiển số chunk task có thể hoạt động song song (tùy cơ chế thực thi và phiên bản framework). Với **partitioning**, pool của `PartitionHandler` điều khiển số partition chạy cùng lúc. Đây là những đơn vị tải khác nhau: một partition còn có thể xử lý nhiều chunk tuần tự, và một job có thể có nhiều step dùng chung pool.

**Một phép gán “thread pool size = DB pool size” không tự động đúng.** Có luồng giữ connection suốt transaction; có luồng chờ HTTP mà không giữ JDBC connection; có luồng cần hai connection cùng lúc. Phải đo **thời gian connection bị chiếm**, số tác vụ DB đồng thời và các phần khác cùng sử dụng pool.

### 2.1. Sơ đồ đường đi tài nguyên

~~~mermaid
flowchart LR
    J["Spring Batch manager / step"] --> T["TaskExecutor<br/>N worker threads"]
    T -->|Chunk / partition| R["Reader + Processor + Writer"]
    R -->|JDBC borrow| P["HikariCP<br/>M connections"]
    R -->|HTTP call| H["HTTP client pool"]
    P --> D[("Database<br/>CPU / IOPS / locks")]
    H --> A["Remote API<br/>rate limit"]
    J --> JR[("JobRepository")]
    JR -.->|có thể dùng cùng datasource| P
~~~

Nếu reader đọc 10.000 bản ghi nhưng writer gửi 10.000 HTTP requests, nút thắt có thể nằm ở mạng/API. Nếu writer thực hiện hàng loạt `INSERT` vào một bảng có khóa nóng, nút thắt thường nằm ở database. Hai job cùng “I/O-bound” có thể cần pool size rất khác nhau.

## 3. CPU-bound và I/O-bound là phổ liên tục

Một task xử lý chunk có thể dành thời gian theo chu trình:

~~~text
Đọc dữ liệu từ DB -> biến đổi JSON -> gọi API -> ghi DB -> commit
        chờ I/O           CPU          chờ I/O    I/O/lock
~~~

Đặt:

- `C` = thời gian một task thực sự dùng CPU (CPU service time).
- `W` = thời gian task bị chặn/chờ I/O khi **không dùng CPU**.
- `Ncpu` = số CPU core hữu ích sẵn cho workload (xem CPU quota và các process khác).
- `Nthread` = số thread worker chạy đồng thời.

Ước lượng truyền thống cho workload dạng blocking I/O là:

\[
N_{\text{thread,heuristic}}
\approx N_{\text{cpu}}\left(1+\frac{W}{C}\right)
\]

Đây là **điểm bắt đầu để thử nghiệm**, không phải giới hạn cứng hay công thức tính được một cấu hình tối ưu. Nó giả định các task tương đối độc lập, thời gian CPU/I/O được đo đúng, các tài nguyên ngoài CPU chưa bão hòa và việc tăng thread có thể chồng lấp thời gian chờ.

Ví dụ một task sử dụng trung bình **20 ms CPU** và **80 ms blocked I/O**, ứng dụng có ngân sách khoảng **4 CPU core**:

\[
4\times (1+80/20)=20\text{ threads (gợi ý ban đầu)}
\]

Nếu 20 thread đều tranh một DB chỉ cho phép tối đa 8 transaction hữu ích chạy cùng lúc thì 20 chưa chắc tốt hơn 8–12. Công thức CPU/I/O **không biết** về DB connection, lock contention, HTTP quota, bộ nhớ hay queue.

### 3.1. Ba kiểu workload để so sánh

| Workload | Phần lớn thời gian | Hướng thử nghiệm pool |
| --- | --- | --- |
| Transform ảnh / mã hóa / tính toán nặng | CPU | Bắt đầu gần số CPU core hữu ích; thêm thread thường không giúp |
| Đọc từ S3 rồi gọi HTTP API chậm | Chờ mạng | Thử concurrency lớn hơn core, nhưng theo dõi HTTP pool, timeout và rate limit |
| JDBC đọc/ghi hàng loạt | DB I/O, lock hoặc log flush | Thử tăng thận trọng trong giới hạn connection/transaction hữu ích; đo DB wait và TPS |

Khi dùng **virtual threads** trên phiên bản Java/Spring phù hợp, chi phí tạo thread chờ I/O có thể thấp hơn platform threads, nhưng **database connection, network connection, quota, khóa DB và throughput đích không biến mất**. Vẫn cần giới hạn concurrency theo năng lực hệ thống.

## 4. Dùng Little's law để kiểm tra nhu cầu in-flight

Với một hệ thống ổn định trong một khoảng đo, định luật Little:

\[
L = \lambda \times W_{\mathrm{system}}
\]

Trong đó:

- `L` = **số yêu cầu trung bình đang ở trong hệ thống** (in-flight + đang đợi, tùy ranh giới được chọn).
- `\lambda` = throughput trung bình, đơn vị yêu cầu/giây.
- `Wsystem` = **thời gian trung bình** một yêu cầu ở trong ranh giới đó, đơn vị giây.

Ví dụ mục tiêu 200 HTTP requests/giây, thời gian trung bình từ lúc bắt đầu gửi tới khi nhận kết quả là 120 ms:

\[
L \approx 200\times0.12 = 24
\]

Nghĩa là cần khoảng **24 HTTP requests đang hoạt động trung bình** để đạt throughput ấy nếu latency trung bình vẫn 120 ms. Điều này có thể giúp kiểm tra HTTP connection concurrency, rate limit và hệ thống đích; **không suy ra trực tiếp** rằng phải đặt JDBC pool là 24 nếu mỗi HTTP request không dùng JDBC.

Không lấy p95 latency đưa vào Little's law rồi gọi kết quả là **số in-flight trung bình**: công thức dùng **trung bình**, còn p95/p99 cần theo dõi thêm để tính headroom, timeout và nguy cơ tăng backlog.

### 4.1. Khi nào công thức không còn dự báo được kết quả?

Khi bạn tăng `Nthread` mà các yêu cầu bắt đầu xếp hàng tại DB, `Wsystem` sẽ tăng. Lúc đó `L` có thể tăng nhưng `\lambda` giữ nguyên hoặc giảm. Dấu hiệu này cho thấy tài nguyên đích đã bão hòa và **thêm pool size chỉ chuyển hàng đợi** từ tầng này sang tầng khác.

Cũng cần phân biệt:

- **Service time**: thời gian tài nguyên thực sự xử lý request.
- **Queueing time**: thời gian đợi được nhận vào connection pool, broker, DB hoặc API.
- **End-to-end latency**: service time cộng các khoảng chờ trên toàn đường đi.

Việc “I/O wait tăng” vì đợi **connection trong HikariCP** không có nghĩa nên tăng thread pool; ngược lại, bạn đang có nhiều thread hơn số connection khả dụng.

## 5. Ngân sách connection phải tính ở cấp hệ thống

Giả sử PostgreSQL được phép sử dụng tổng cộng 80 connection cho tất cả ứng dụng batch và nghiệp vụ, không tính các connection đặc biệt được DB dự trữ. Trong đó:

- 24 connection cho hệ thống online.
- 12 connection cho một dịch vụ khác.
- 8 connection dự phòng quản trị, metadata hoặc đỉnh tải.
- Còn khoảng **36 connection** có thể phân bổ cho các instance xử lý batch.

Nếu có **3 batch pod**, cấu hình `maximumPoolSize=12` cho mỗi pod sẽ tiêu thụ **tối đa 36 connection** từ riêng ba pool đó. Đây là **trần**, không phải con số luôn được mở tức thì. Nếu cùng pod còn nhiều `DataSource` khác, tổng connection của chúng phải được cộng riêng.

\[
\underbrace{\sum_i (\text{pod}_i \times \text{poolMax}_i)}_{\text{trần từ ứng dụng}}
+ \text{nhu cầu connection khác}
\le \text{connection budget an toàn của DB}
\]

Con số 80 chỉ là tình huống minh họa. **Đừng đặt budget đúng bằng `max_connections` của DB**: phải tính các nguồn kết nối không thuộc ứng dụng, kết nối quản trị, cơ chế dự trữ của hệ quản trị và mức tải phù hợp với CPU/IOPS thực tế.

### 5.1. Headroom trong một JVM

Một batch pod có pool 12 connection nhưng còn dùng pool cho `JobRepository`, job launcher và các tác vụ giám sát. Nếu 12 worker cùng giữ connection chờ một API chậm, manager có thể thiếu connection để ghi metadata. Vì vậy:

1. Xác định thời điểm worker **borrow** và **release** connection.
2. Đo `active`/`idle`/`pending` connection khi job chạy tải đại diện.
3. Dành ngân sách cho manager, transaction nền và hoạt động khác dùng cùng `DataSource`.
4. Đặt pool worker đủ để đáp ứng throughput mục tiêu nhưng **không làm DB quá tải**; nếu cần tách datasource/pool, hãy đánh giá giao dịch và tính nhất quán metadata.

**Cảnh báo về transaction:** Nếu một chunk transaction giữ JDBC connection trong lúc chờ API 2 giây, connection bị chiếm vô ích và có thể giữ lock lâu. Cách xử lý tốt hơn có thể là **tách I/O gọi API khỏi transaction DB dài**, hoặc thiết kế outbox/đối soát. Tăng JDBC pool lên 100 không sửa gốc vấn đề này.

### 5.2. Khi connection pool nhỏ hơn thread pool

Điều này có thể hợp lý khi chỉ một tỷ lệ nhỏ thread truy cập DB cùng lúc. Nhưng nếu mọi thread phải giữ connection trong toàn bộ chunk transaction, hệ quả thường là:

~~~text
16 worker threads
         |
         +---  8 giữ connection, đang xử lý transaction
         |
         +---  8 chờ HikariCP connection
                 |
                 +-- timeout nếu chờ quá connectionTimeout
~~~

Tăng số thread thêm 16 chỉ tạo thêm request chờ. Cần giảm concurrent tasks, rút ngắn transaction, tối ưu query hoặc tăng capacity DB khi đo đạc chứng minh cần thiết.

## 6. Ví dụ cấu hình Spring Batch có thể điều chỉnh

Ví dụ sử dụng **Spring Batch 5.x / Spring Boot 3.x** theo kiểu **multi-threaded step** với `TaskExecutor` riêng. Đây là khung cấu hình; dự án vẫn phải khai báo `JobRepository`, `PlatformTransactionManager`, `ItemReader`, `ItemProcessor` và `ItemWriter` thích hợp.

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
class BatchConcurrencyConfig {

    @Bean
    public TaskExecutor chunkTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("batch-io-");
        executor.initialize();
        return executor;
    }

    @Bean
    public Step importStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<InputRow> reader,
            ItemProcessor<InputRow, OutputRow> processor,
            ItemWriter<OutputRow> writer,
            @Qualifier("chunkTaskExecutor") TaskExecutor executor) {

        return new StepBuilder("importStep", jobRepository)
                .<InputRow, OutputRow>chunk(200, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .taskExecutor(executor)
                .build();
    }
}
~~~

`InputRow` và `OutputRow` là hai kiểu nghiệp vụ minh họa. Có thể tách worker step hoặc partition handler khi chuyển từ multi-threaded step sang partitioning; **không nên gắn cùng một executor cho mọi step mà không xét giới hạn tổng concurrency**.

- `corePoolSize=8` và `maxPoolSize=8` tạo trần 8 worker threads cho executor này.
- `queueCapacity=16` là sức chứa queue nội bộ của executor; **không** tăng khả năng xử lý song song lên 24. Hàng đợi lớn có thể làm tăng độ trễ hoặc giữ lâu nhiều task/chunk.
- `chunk(200)` là kích thước transaction theo số item, **khác** số thread. Đổi kích thước chunk ảnh hưởng số commit, kích thước batch SQL, bộ nhớ và thời gian giữ lock.
- Ở một số kiểu executor, `maxPoolSize` chỉ phát huy thêm trên `corePoolSize` khi queue đã đầy; đừng nhầm việc tăng max pool với luôn có thêm thread.
- Cơ chế multi-threaded step và hành vi dispatch/throttle phụ thuộc phiên bản Spring Batch. `throttleLimit` trong Spring Batch 5 bị deprecated; cần đối chiếu với phiên bản đang dùng trước khi đổi concurrency hoặc `RepeatOperations`. **Số thread cấu hình không chứng minh số chunk thật sự chạy đồng thời**: cần đo.

### 6.1. HikariCP: một lớp giới hạn khác

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 12
      minimum-idle: 4
      connection-timeout: 30000
      pool-name: batch-main-db
~~~

Ý nghĩa:

- `maximum-pool-size: 12` là **trần kết nối đồng thời** của datasource này trong một ứng dụng/pod. Không phải 12 connection cho mỗi worker hoặc cho toàn cluster.
- `minimum-idle: 4` là cấu hình phần connection nhàn rỗi mà pool có xu hướng duy trì; không bắt buộc mở sẵn mọi connection lên đến 12.
- `connection-timeout: 30000` là thời gian chờ tối đa tính bằng mili giây để **mượn connection** trước khi lỗi; không phải thời gian tối đa query được chạy.
- `pool-name` giúp nhận diện đúng datasource trong metric.

**Bộ số 8 worker threads + 12 JDBC connections chỉ là baseline minh họa.** Nếu từng worker tạo nhiều transaction hoặc mở thêm connection cùng lúc, mức 12 có thể không đủ; nếu database ít năng lực xử lý, 12 vẫn có thể quá nhiều. Cần kiểm chứng bằng số đo thực tế.

### 6.2. Đảm bảo thread safety và restartability trước khi tăng pool

Multi-threaded step có thể xử lý các chunk **không theo cùng thứ tự hoàn tất** như thứ tự đọc. Những thành phần chứa trạng thái mutable cần được kiểm chứng riêng:

- `ItemReader` như nhiều reader đọc file/stream có cursor thường **không mặc định thread-safe**. Chia sẻ một instance stateful giữa thread có thể làm đọc trùng, bỏ sót hoặc hỏng checkpoint.
- Có thể dùng partitioning để cấp reader riêng theo `@StepScope`/`StepExecution` nếu dữ liệu chia được thành các phạm vi độc lập.
- Wrapper đồng bộ hóa reader có thể bảo vệ lời gọi `read()` nhưng không bảo đảm cách checkpoint/restart đúng trong mọi mô hình nhiều thread.
- `ItemProcessor`/`ItemWriter` và service singleton không được giữ biến instance mutable cho “item hiện tại” nếu dùng chung giữa nhiều thread.
- Với chunk restart sau crash, reader/writer phải duy trì `ExecutionContext` nhất quán; không bật `saveState(false)` tùy tiện chỉ để tránh vấn đề concurrency, vì có thể làm mất checkpoint.

Nếu không thể xác minh thread safety và restartability của một shared reader, **partitioning với reader riêng cho mỗi partition** thường dễ kiểm soát hơn so với tăng thread cho một step dùng chung state.

## 7. Pool size cho local partitioning, parallel steps và remote workers

### 7.1. Local partitioning

Với `TaskExecutorPartitionHandler`, executor điều khiển số **worker step executions** có thể chạy đồng thời; `gridSize` thể hiện mức phân chia/gợi ý số partition và không đồng nghĩa trần thread. Ví dụ chia 16 partition và dùng pool 4 threads thì thường chỉ tối đa bốn partition chạy một thời điểm (trong một manager dùng một executor theo cách minh họa):

~~~text
16 partitions -> executor(4 threads) -> tối đa khoảng 4 partition đang chạy
                                      -> phần còn lại đợi lượt
~~~

Tối ưu pool nếu một partition có job nhỏ? Cần phân biệt **partition skew**: nếu 15 partition hoàn tất nhanh nhưng một partition nặng gấp 20 lần, tăng thread pool chỉ giúp giai đoạn đầu; còn bottleneck cuối job nằm ở partition quá lớn. Khi đó cần chia dữ liệu cân bằng và ổn định cho restart.

### 7.2. Parallel steps

Hai step độc lập chạy song song có thể đều dùng pool riêng:

~~~text
step A: 6 threads
step B: 8 threads
-----------------
Concurrent worker tasks có thể lên tới khoảng 14 trong cùng ứng dụng
~~~

Không dùng từng pool như một ngân sách độc lập khi chúng **truy cập cùng database**. Cần cộng tải đồng thời từ tất cả step, manager, retry và tác vụ nền; riêng connection pool có thể trở thành giới hạn chung.

### 7.3. Remote workers

Với 5 worker pods, mỗi pod cho phép 8 chunk/partition executions, tổng concurrency lý thuyết là:

\[
N_{\text{total}}\approx 5\times8=40
\]

Con số thực có thể bị giới hạn bởi broker partition/consumer, prefetch, connection pool, áp lực database hoặc rate limit API. Nếu mỗi pod có Hikari `maximumPoolSize=12`, trần riêng từ các pod này đã là 60 DB connections; phải cộng chúng vào ngân sách của **toàn bộ DB**.

Dù dùng remote chunking hay remote partitioning, cần xét retry và worker crash. Message giao lại hoặc partition bị chạy lại có thể làm tải đột ngột vượt mức đã đo ở điều kiện bình thường. Đo hệ thống cả trong **failure/recovery mode**, không chỉ khi mọi worker thành công.

## 8. Cách chọn kích thước ban đầu từ phép đo

Giả sử job có bốn CPU core hữu ích trong container, xử lý một chunk trung bình:

| Thành phần một chunk | Thời gian minh họa |
| --- | ---: |
| CPU transform | 25 ms |
| Chờ read DB | 30 ms |
| Chờ HTTP API | 100 ms |
| Chờ write/commit DB | 45 ms |
| **Tổng latency chunk** | **200 ms** |

Ta có `C=25 ms` và phần chờ `W=175 ms` nên:

\[
N_{\text{thread,heuristic}}\approx4(1+175/25)=32
\]

Đây chỉ là giá trị **theo CPU**. Bây giờ kiểm tra giới hạn ngoài CPU:

- HTTP API chỉ cho **120 requests/giây**.
- DB có ngân sách **10 connection** dành cho job này.
- Connection được giữ trong phần lớn chunk transaction; nếu mọi worker giữ connection, 32 thread sẽ khiến nhiều thread đợi pool.
- Mỗi chunk thực hiện **2 HTTP calls**, vậy riêng quota API đã giới hạn tốc độ hoàn tất ở khoảng **60 chunks/giây** trước khi xét retry và lỗi.

Với các ràng buộc ấy, bắt đầu benchmark với **4, 8 và 10 worker threads** sẽ có ý nghĩa hơn là áp dụng máy móc 32. Nếu chỉ 8 threads đã đạt 50 chunks/giây và các requests tới API ổn định, tăng tới 32 có thể vượt quota, gây retry/429 và làm tốc độ thực giảm.

### 8.1. Tính ví dụ theo Little's law

Nếu mục tiêu là **50 chunk/giây** và latency trung bình vẫn **0,20 giây**, cần khoảng:

\[
L=50\times0.20=10\text{ chunk in flight trung bình}
\]

Điều này gợi ý thử quanh **10 worker tasks**. Nhưng để đạt mức ấy trong thực tế, phải xác minh chunk không bị serialize bởi reader, transaction/DB đủ mạnh và API chịu được 100 requests/giây (2 requests/chunk). Nếu latency tăng lên 0,4 giây khi thêm tải, 10 tasks chỉ có thể hoàn tất xấp xỉ 25 chunks/giây và cần tìm nút thắt trước khi tăng pool.

## 9. Benchmark từng mức, dùng kết quả để quyết định

Quy trình đề xuất:

1. **Cố định workload**: snapshot đầu vào, số item, kích thước chunk, tỷ lệ item lỗi và điều kiện hệ thống đích. Đảm bảo chạy thử lặp được hoặc dùng bản sao dữ liệu có thể reset.
2. **Đo baseline** với concurrency nhỏ, ví dụ 2 hoặc 4; ghi throughput, latency, CPU, I/O, DB metrics, retry/skip.
3. **Tăng một biến mỗi lần**: 2 → 4 → 8 → 12 → 16 worker threads; giữ nguyên chunk size và DB pool để biết thay đổi đến từ đâu. Khi chạm giới hạn pool, dừng để đánh giá thay vì tiếp tục tăng.
4. **Chọn mức gần knee point**: mức trước khi throughput gần như phẳng, p95 tăng mạnh, queue pending hoặc lỗi/timeout xuất hiện.
5. **Kiểm tra sự cố và restart**: một worker bị crash, database chậm đột ngột, một chunk retry; xem CPU, pool pending và hiệu ứng backlog.
6. **Chạy lại trên tải đại diện** cùng các workload thực chia sẻ DB/API; xác nhận ngân sách toàn hệ thống còn an toàn.

Bảng số liệu **giả lập để diễn giải**:

| Worker threads | Throughput (chunks/s) | DB pool pending p95 | p95 chunk latency | Nhận định |
| ---: | ---: | ---: | ---: | --- |
| 2 | 10 | 0 | 230 ms | CPU và DB còn dư |
| 4 | 19 | 0 | 250 ms | Tăng gần tuyến tính |
| 8 | 34 | 0 | 320 ms | Throughput tiếp tục tăng |
| 12 | 38 | 3 | 650 ms | Bắt đầu nghẽn connection/DB |
| 16 | 37 | 7 | 1.200 ms | Nhiều chờ hơn, không tăng tốc |

Các số trong bảng **không phải benchmark thực tế**. Trong tình huống này, nên điều tra giới hạn DB và mức 8 trước khi chọn 12 hay 16. Mức 8 có thể có throughput thấp hơn một chút nhưng tốt hơn về latency, headroom và ổn định khi recovery.

~~~mermaid
flowchart TD
    A["Đo CPU / I/O / DB / API baseline"] --> B["Ước lượng concurrency ứng viên"]
    B --> C["Đặt trần theo connection + quota + memory"]
    C --> D["Benchmark tăng một biến mỗi lần"]
    D --> E{"Throughput tăng<br/>và latency/lỗi ổn?"}
    E -->|Có| F["Thử mức tiếp theo nếu còn headroom"]
    F --> D
    E -->|Không| G["Xác định nút thắt<br/>pool / DB / API / lock"]
    G --> H["Chọn cấu hình trước điểm bão hòa<br/>và xác minh restart"]
~~~

### 9.1. Vì sao phải đo throughput *hoàn tất*?

Dữ liệu quan sát khác nhau có thể khiến quyết định khác nhau:

- **Tasks submitted/s** cao chưa chắc job nhanh: queue executor có thể ngày càng dài.
- **Requests sent/s** cao chưa chắc DB commit nhanh: API có thể trả retry/error.
- **Items read/s** cao chưa chắc output bền vững: writer bị nghẽn hoặc transaction rollback.
- **Chunks committed/s** và **items written/s thành công** gần mục tiêu nghiệp vụ hơn, nhưng vẫn phải đối chiếu tổng kết quả để phát hiện ghi trùng/bỏ sót.
- **Job elapsed time** cho biết throughput end-to-end, kể cả khởi động, đọc đầu vào, retry và tổng hợp partition.

Đặc biệt phải xem **số lượng item thực sự đúng** sau restart; cấu hình nhanh nhưng làm hỏng checkpoint không được coi là tối ưu.

## 10. Metric và công cụ kiểm chứng

### 10.1. Metrics cần đối chiếu cùng thời điểm

| Nhóm | Metric quan trọng | Cách đọc dấu hiệu |
| --- | --- | --- |
| **Batch** | Job/step/chunk duration, read/write/commit/rollback/skip count | Chunk dài dần, rollback tăng có thể là nghẽn hoặc lỗi |
| **Executor** | Active threads, pool size, queue depth, rejected tasks | Active = max và queue tăng: thiếu capacity hoặc downstream chậm |
| **HikariCP** | Active, idle, pending, total connection, acquire time/timeouts | Pending và acquire time tăng: pool đang cạn hoặc giữ connection quá lâu |
| **Database** | CPU, buffer/cache hit, locks, wait events, slow query, connection usage | CPU/IOPS/lock đã bão hòa: tăng JDBC pool thường không giúp |
| **API/HTTP** | In-flight, p50/p95/p99, 429/503, timeout, rate limit | Retry/429 tăng: hạ concurrency hoặc rate-limit từ nguồn |
| **JVM/OS** | CPU quota, GC pause, heap, thread count, context switches, disk I/O | Nhiều thread tạo overhead hoặc memory pressure |
| **Broker** | Queue ready/unacked, lag, consumer throughput, redelivery | Backlog tăng với worker bận: service capacity không theo kịp |

Một số metric phụ thuộc ứng dụng đã bật Micrometer/Actuator, executor được đăng ký instrumentation hay chưa, tên datasource và phiên bản thư viện; hãy xác minh **có metric thật** trước khi suy luận từ chúng. HikariCP qua Micrometer thường cung cấp các tên như `hikaricp.connections.active` và `hikaricp.connections.pending`; tên xuất ra Prometheus có thể đổi dấu chấm thành dấu gạch dưới.

### 10.2. Ghi log theo partition và chunk

Một bản ghi quan sát hữu ích:

~~~json
{
  "job": "dailyImportJob",
  "step": "writeOrders",
  "partition": "partition-07",
  "chunkItems": 200,
  "chunkElapsedMs": 410,
  "dbConnectionAcquireMs": 18,
  "remoteApiElapsedMs": 220,
  "writeRows": 200,
  "retryCount": 0
}
~~~

Đây là **mẫu log tự thiết kế**, không phải các field mặc định Spring Batch luôn xuất ra. Khi cần điều tra, gắn job execution ID, step execution ID, tên partition và trace ID; tránh log dữ liệu khách hàng nhạy cảm.

## 11. Các điểm nghẽn thường bị chẩn đoán sai

### 11.1. Tăng pool khi database đang chờ lock

Nếu SQL có nhiều worker cập nhật **cùng một hàng** hoặc các khóa chỉ mục nóng, số connection tăng làm nhiều transaction chờ lock hơn. Cần tối ưu phạm vi partition theo khóa, thứ tự ghi, transaction size và index. Có lúc **giảm** concurrency giúp TPS tăng.

### 11.2. Hikari active cao nhưng CPU DB thấp

Có thể connection đang bị giữ trong giao dịch khi gọi API hoặc code xử lý khác. DB CPU thấp không chứng minh thiếu DB pool; cần phân tích **connection hold time** và transaction lifetime.

### 11.3. CPU ứng dụng 30%, tăng thread chưa chắc hữu ích

Container có CPU quota, JVM GC, reader tuần tự, lock Java, DB pool hoặc HTTP pool có thể gây chặn. CPU thấp chỉ cho biết có thời gian không chạy trên CPU; **không nói rõ đang chờ gì**.

### 11.4. Chỉ nhìn average latency

Average ổn nhưng p99 tăng mạnh có thể làm chunk timeout, worker retry và kéo dài JobExecution. Cần theo dõi histogram, p95/p99 và error rate; workload batch rất dễ có partition dài bất thường.

### 11.5. Đặt queueCapacity thật lớn để chống nghẽn

Queue nội bộ lớn chỉ che giấu overload, làm heap tăng và kéo dài thời gian từ lúc submit đến lúc chạy. Nên dùng concurrency giới hạn rõ ràng, backpressure hoặc điều phối tốc độ phát việc dựa trên capacity thực.

### 11.6. Tăng retry mà không có rate limit

Khi API trả 429 hoặc DB timeout, retry hàng loạt của nhiều worker có thể tạo **retry storm**. Dùng backoff có jitter, giới hạn số lần và rate limiter/circuit breaker phù hợp; kiểm chứng xử lý trùng và restart.

## 12. Tối ưu chunk size cùng với pool size

Hai tham số có quan hệ nhưng không đồng nghĩa:

- **Chunk size**: số item được xử lý trước một lần commit (trong step chunk-oriented thông thường). Chunk lớn giảm commit overhead nhưng giữ transaction/lock và memory lâu hơn.
- **Pool size**: số tác vụ được phép thực thi đồng thời. Pool lớn tăng áp lực lên transaction, DB connection và các downstream services.

Nếu chunk 5.000 items giữ connection 20 giây, tăng thread từ 4 lên 16 có thể khiến 16 transaction dài tranh chấp cùng bảng. Thử **chunk 100/500/1.000** theo kích thước bản ghi và thời gian commit rồi tune pool theo kết quả; không đổi cả hai cùng lúc ở bước đầu vì khó quy nguyên nhân.

Ngoài ra `fetchSize` (JDBC reader), `pageSize` (paging reader), batch size JDBC writer, cách đánh index và transaction isolation level ảnh hưởng throughput mạnh. Khi tối ưu connection pool mà thiếu các biến này có thể chỉ giải quyết triệu chứng.

## 13. Tình huống thực hành: chọn pool cho job đồng bộ đơn hàng

**Bối cảnh:** Job `syncOrdersJob` chia 2 triệu order thành 20 partition, mỗi partition đọc từ PostgreSQL, gọi REST API nội bộ rồi ghi trạng thái về DB. Chạy bằng local partitioning trên JVM 8 vCPU, có HikariCP giới hạn 16 connections và dịch vụ REST giới hạn 100 concurrent calls.

**Số đo ban đầu (giả lập):**

| Chỉ số | Giá trị |
| --- | --- |
| CPU hữu ích cho job sau khi trừ nền | 6 core |
| CPU mỗi task | 30 ms |
| Chờ DB + HTTP mỗi task | 120 ms |
| Partition count | 20 |
| Hikari max | 16 |
| DB connections cần dành cho manager và tác vụ khác | 4 |
| Số worker có thể giữ connection cùng lúc (ước lượng bảo thủ) | 12 |

Theo công thức CPU/I/O:

\[
N_{\mathrm{CPU/I/O}}\approx 6(1+120/30)=30
\]

Nhưng toàn job chỉ có 20 partition; nếu mỗi partition giữ một JDBC connection phần lớn thời gian, và chỉ có ngân sách 12 cho worker, **12 là trần thăm dò** hợp lý hơn 30. Hãy thử `poolSize=4, 8, 12` và đo tốc độ commit, thời gian giữ connection, HTTP latency và DB locks. Nếu 8 partition đồng thời đã đạt gần tối đa TPS của DB, cấu hình 8 có thể là lựa chọn tốt hơn 12.

Nếu đổi sang remote partitioning với 3 worker pods, không thể để mỗi pod tự tính “12 là phù hợp” rồi nhân lên 36 mà không xem lại tổng connection của database. **Pool size phải được tính từ tổng capacity của downstream**, sau đó chia cho số worker, cộng headroom và khả năng scale tự động.

### 13.1. Câu hỏi phản biện

- Nếu giảm REST latency từ 120 ms xuống 30 ms, nên tự động tăng thread pool không? **Không.** Lúc đó phần CPU trở nên tương đối lớn hơn; concurrency cần thiết để phủ I/O wait có thể giảm.
- Nếu Hikari pending bằng 0 mà throughput không tăng khi thêm thread, liệu có cần tăng JDBC pool? **Chưa có bằng chứng.** Xem CPU, HTTP quota, lock, writer và phân phối partition.
- Nếu Hikari pending tăng, có phải tăng `maximumPoolSize` ngay? **Chưa chắc.** Có thể đang giữ connection quá lâu; tăng max làm DB quá tải hoặc gây deadlock.
- Nếu JobExecution có một partition chậm gấp 20 lần những partition khác, pool lớn có chữa được không? **Không nhất thiết.** Cần cân bằng phạm vi dữ liệu hoặc thay đổi thuật toán xử lý của partition đó.

## 14. Checklist ra quyết định và triển khai an toàn

Trước khi chốt cấu hình cho production:

1. **Định nghĩa pool** đang chỉnh và phạm vi của nó: per step, per executor, per pod hay per database.
2. **Đo** CPU time, thời gian I/O thực, thời gian chờ connection, throughput commit, p95/p99 và error rate.
3. **Tính tổng ngân sách** connection/HTTP/API trên mọi worker pod và các workload cùng dùng downstream.
4. **Đặt giới hạn rõ ràng** cho thread, connection, in-flight calls và queue; giữ headroom cho JobRepository, vận hành và retry.
5. **Benchmark một biến mỗi lần**, dùng dữ liệu và số partition đại diện, ghi lại knee point.
6. **Đảm bảo thread safety** của reader/processor/writer và checkpoint/restart trước khi tăng concurrency.
7. **Kiểm thử thất bại**: DB chậm, API rate limit, worker crash, retry và job restart để phát hiện nghẽn hoặc output trùng.
8. **Theo dõi và điều chỉnh** sau deploy dựa vào metric thật; rollback cấu hình khi latency/error tăng quá ngưỡng đã thống nhất.

Một mức pool size tối ưu không chỉ hoàn thành nhiều item/giây mà còn **giữ ổn định, không vượt ngân sách downstream và cho phép restart an toàn** khi gặp sự cố.

## 15. Câu hỏi tự kiểm tra

1. Một step có `TaskExecutor` 32 threads nhưng Hikari `maximumPoolSize=8`. Điều gì xảy ra nếu mỗi chunk giữ một JDBC connection từ đầu đến cuối?
2. CPU time = 15 ms, blocked I/O = 45 ms, có 4 CPU core hữu ích. Công thức heuristic gợi ý bao nhiêu worker threads? Vì sao đó chưa phải kết quả cuối cùng?
3. Một hệ thống xử lý 150 requests/giây với thời gian trung bình 0,2 giây. Có bao nhiêu request in-flight trung bình theo Little's law? Dùng p99=0,8 giây vào công thức có còn đúng về mặt ý nghĩa không?
4. Vì sao `poolSize=10` trên mỗi pod không có nghĩa tổng số worker threads của hệ thống chỉ là 10?
5. Nếu throughput đã đứng yên nhưng `hikaricp.connections.pending` tăng và p95 chunk latency tăng gấp đôi, bạn đo và thay đổi gì trước?
6. Vì sao tăng concurrency cho reader có mutable cursor có thể làm sai cả throughput lẫn restartability?
7. Khi API trả 429 vì quá tải, nên tăng thread pool, tăng retry vô hạn hay điều chỉnh concurrency/rate limit có kiểm soát?

**Gợi ý:** (1) Nhiều threads chờ mượn connection, có thể timeout. (2) `4×(1+45/15)=16` threads là điểm thử ban đầu; còn DB/API/quota. (3) `30` request trung bình; p99 không dùng để tính L trung bình. (4) Phải nhân theo số pod và tính các step khác. (5) Kiểm tra connection hold time, DB lock/CPU/IOPS và pool budget, không tăng mù. (6) Dữ liệu/checkpoint dùng chung bị tranh chấp. (7) Giới hạn in-flight, rate limiting, backoff/jitter và idempotency.

## Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded steps, parallel steps, partitioning và các giới hạn tài nguyên liên quan.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): trạng thái và checkpoint khi restart, đặc biệt cần thiết cho xử lý song song.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `ThreadPoolTaskExecutor`, thread pool và queue.
- [HikariCP — About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing): vì sao nhiều database connections hơn không luôn làm DB nhanh hơn.
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby): `maximumPoolSize`, `minimumIdle`, `connectionTimeout` và thông số pool.
- [Little's Law — nguyên lý hiệu năng hàng đợi](https://en.wikipedia.org/wiki/Little%27s_law): quan hệ giữa throughput, latency trung bình và số yêu cầu trong hệ thống.

**Ghi nhớ:** Chọn pool size theo I/O là bài toán **đo lường và đặt giới hạn tài nguyên**. Dùng tỷ lệ CPU/I/O và Little's law để lập giả thuyết, kiểm tra connection/quotas toàn hệ thống, rồi benchmark tăng concurrency từng bước. Sự lựa chọn tốt nhất là mức trước khi throughput bão hòa và thời gian chờ, lỗi, chi phí vận hành bắt đầu tăng mạnh.
