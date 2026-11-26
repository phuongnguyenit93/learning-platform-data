# Worker execution trong JobRepository của Spring Batch

> **Chương:** Partitioning
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các mô hình xử lý phân tán. Bài này tập trung vào cách lưu, tra cứu và sử dụng metadata **worker StepExecution** trong `JobRepository` để giám sát, retry/restart và vận hành job an toàn.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt `JobInstance`, `JobExecution`, manager `StepExecution` và worker `StepExecution` trong một job partitioning.
2. Giải thích thông tin worker được lưu trong `BATCH_STEP_EXECUTION` và `BATCH_STEP_EXECUTION_CONTEXT`, cùng vai trò của `JobRepository`.
3. Theo dõi vòng đời worker từ lúc splitter tạo execution đến lúc handler thực thi và repository ghi trạng thái/checkpoint.
4. Dùng `JobExplorer` hoặc truy vấn metadata để tìm partition lỗi, chưa hoàn tất, chậm hoặc cần restart.
5. Nhận diện giới hạn của metadata khi có concurrency, broker, hiệu ứng ngoài transaction, thay đổi input và nhiều lần chạy cùng dữ liệu.

## 1. Worker execution là gì?

Trong **partitioning**, một manager step chia công việc thành nhiều partition rồi giao mỗi phần cho **worker step**. Mỗi phần việc được framework thể hiện bằng một **`StepExecution` riêng**, dù các worker có thể sử dụng chung một định nghĩa Java `Step`.

Giả sử một job import đơn hàng chia dữ liệu thành bốn range:

| Partition key | Phạm vi ID của worker | Tên worker `StepExecution` thường gặp |
| --- | --- | --- |
| `range-0000` | `[1, 25001)` | `ordersWorkerStep:range-0000` |
| `range-0001` | `[25001, 50001)` | `ordersWorkerStep:range-0001` |
| `range-0002` | `[50001, 75001)` | `ordersWorkerStep:range-0002` |
| `range-0003` | `[75001, 100001)` | `ordersWorkerStep:range-0003` |

Mỗi worker execution có metadata riêng: ID, trạng thái, thời gian bắt đầu/kết thúc, các counter và `ExecutionContext`. `JobRepository` là nơi lưu metadata đó để manager và worker biết **đã xử lý đến đâu**, **partition nào hoàn thành** và **partition nào có thể cần chạy lại**.

### Các mức định danh phải phân biệt

| Đối tượng | Ý nghĩa | Có thay đổi khi restart? |
| --- | --- | --- |
| `JobInstance` | Một công việc logic được nhận diện bởi job name và identifying `JobParameters` | Giữ nguyên khi restart đúng cùng instance |
| `JobExecution` | Một lần cố gắng thực thi của `JobInstance` | Có execution mới khi job được restart |
| Manager `StepExecution` | Một lần thực thi bước điều phối partition | Có thể có execution mới trong lần chạy lại |
| Worker `StepExecution` | Một lần thực thi step đối với một partition cụ thể | Có thể có ID mới khi partition được chạy lại |
| Partition key | Tên phần việc logic, ví dụ `range-0002` | **Cần ổn định** theo kế hoạch phân vùng cần restart |
| Business key | Định danh bản ghi/sự kiện, ví dụ `order_id` | Cần ổn định để đối soát dữ liệu và chống ghi trùng |

**Điểm quan trọng:** `StepExecutionId` là ID của **lần thực thi**, không phải khóa nghiệp vụ và không thay thế partition key. Một partition logic có thể có nhiều `StepExecution` qua các lần restart; ngược lại, mỗi execution mang trạng thái và checkpoint riêng của lượt thực thi đó.

## 2. Vị trí của JobRepository trong kiến trúc manager–worker

~~~mermaid
flowchart TB
    J["JobExecution"] --> M["Manager PartitionStep"]
    M --> H["PartitionHandler"]
    H --> S["StepExecutionSplitter"]
    S --> P["Partitioner: partition key + input context"]
    S <--> R[("JobRepository<br/>StepExecution và ExecutionContext")]
    S --> H
    H --> A["Worker A<br/>StepExecution range-0000"]
    H --> B["Worker B<br/>StepExecution range-0001"]
    H --> C["Worker C<br/>StepExecution range-0002"]
    A <--> R
    B <--> R
    C <--> R
    A --> D[("Business database / output")]
    B --> D
    C --> D
~~~

Trình tự khái niệm:

1. **`Partitioner`** xác định các partition bằng `Map<String, ExecutionContext>`. Giá trị context chứa phạm vi đầu vào, như `minId`, `maxIdExclusive` hoặc file ID.
2. **`StepExecutionSplitter`** dựa trên kế hoạch partition và lịch sử trong `JobRepository` để tạo/chọn những worker `StepExecution` cần chạy.
3. **`PartitionHandler`** nhận các worker executions, đưa chúng vào executor cục bộ hoặc gửi yêu cầu tới worker từ xa.
4. **Worker step** đọc/xử lý/ghi dữ liệu theo `ExecutionContext` của mình và thực hiện các chunk transaction.
5. **`JobRepository`** lưu trạng thái, counters và checkpoint của worker; manager thu kết quả để xác định kết quả bước partitioning.

Sơ đồ thể hiện quan hệ logic. Trong đường chạy phổ biến, `PartitionStep` gọi `PartitionHandler.handle(...)`; handler gọi splitter để lấy các worker executions, không nhất thiết manager gọi `split()` trực tiếp.

### JobRepository không phải bảng nghiệp vụ

`JobRepository` lưu **metadata vận hành của Batch**, không phải tập đơn hàng đã import hoặc ledger chống ghi trùng. Một dòng trong bảng metadata nói rằng worker đã `COMPLETED` không thể tự chứng minh hệ thống bên ngoài đã nhận đúng một email hoặc đã charge đúng một lần. Các hiệu ứng ngoài transaction cần kiểm soát bằng idempotency key, outbox/inbox hoặc cơ chế xác nhận riêng.

## 3. Worker được lưu vào những bảng metadata nào?

Với schema metadata **mặc định** của Spring Batch trên database quan hệ:

| Bảng | Nội dung liên quan |
| --- | --- |
| `BATCH_JOB_INSTANCE` | Danh tính job logic và khóa tham số định danh |
| `BATCH_JOB_EXECUTION` | Một lần chạy/restart của job; trạng thái tổng thể, thời gian |
| `BATCH_STEP_EXECUTION` | **Mỗi lần thực thi manager hoặc worker step**: ID, tên, trạng thái, read/write/skip/rollback count |
| `BATCH_STEP_EXECUTION_CONTEXT` | **ExecutionContext của từng StepExecution**: dữ liệu phân vùng và checkpoint của worker |
| `BATCH_JOB_EXECUTION_CONTEXT` | Context cấp job; không đồng nghĩa context riêng của từng partition |

Tên bảng có thể khác nếu ứng dụng cấu hình prefix metadata riêng. Trong các phiên bản/schema triển khai khác nhau, độ dài cột, kiểu dữ liệu, cơ chế sinh ID và serializer có thể khác; không tự chỉnh bảng mặc định để xử lý lỗi nghiệp vụ.

### 3.1. BATCH_STEP_EXECUTION lưu trạng thái worker

Một truy vấn thường dùng để xem tất cả step executions của **một JobExecution**:

~~~sql
SELECT
    STEP_EXECUTION_ID,
    JOB_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    EXIT_CODE,
    READ_COUNT,
    WRITE_COUNT,
    FILTER_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT,
    START_TIME,
    END_TIME,
    LAST_UPDATED
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
~~~

Kết quả bao gồm **manager step** và **worker steps**, nếu chúng thuộc `JobExecution` đang tra cứu. Không cộng mọi dòng một cách mù quáng: manager có thể mang counters riêng với ý nghĩa khác worker.

Tên worker step khi partitioning thường theo dạng `workerStepName:partitionName`. Ví dụ các dòng `ordersWorkerStep:range-0000` và `ordersWorkerStep:range-0001` là **hai StepExecution**, dù đều chạy cùng một định nghĩa `ordersWorkerStep`.

### 3.2. BATCH_STEP_EXECUTION_CONTEXT lưu dữ liệu nào?

Mỗi worker có một `ExecutionContext`, có thể chứa:

- **Tham số phân vùng ban đầu:** `minIdInclusive`, `maxIdExclusive`, `fileId`, `inputVersion`.
- **State/checkpoint của reader hoặc writer:** vị trí đã đọc, chỉ số trang, trạng thái cần để tiếp tục ở lần restart (tùy loại component và `saveState`).
- **Dữ liệu tiến độ bổ sung:** chỉ lưu những giá trị thật sự cần cho vận hành/restart.

Một ví dụ **mô tả logic**, không phải JSON thô chắc chắn được lưu trực tiếp:

~~~json
{
  "minIdInclusive": 25001,
  "maxIdExclusive": 50001,
  "inputVersion": "snapshot-2026-11-26",
  "ordersReader.read.count": 12400
}
~~~

Tên key checkpoint cụ thể do component/version quyết định; đoạn JSON chỉ giúp hình dung sự khác nhau giữa **phạm vi partition** và **tiến độ đọc**. Spring Batch lưu `ExecutionContext` bằng cơ chế **serialization** được cấu hình; nội dung các cột như `SHORT_CONTEXT` và `SERIALIZED_CONTEXT` không nhất thiết là JSON đọc trực tiếp.

Liên kết worker và context qua `STEP_EXECUTION_ID`:

~~~sql
SELECT
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    ec.SHORT_CONTEXT
FROM BATCH_STEP_EXECUTION se
JOIN BATCH_STEP_EXECUTION_CONTEXT ec
  ON ec.STEP_EXECUTION_ID = se.STEP_EXECUTION_ID
WHERE se.JOB_EXECUTION_ID = :jobExecutionId
ORDER BY se.STEP_EXECUTION_ID;
~~~

**Không ghi hoặc xuất toàn bộ context vào log công khai**: context có thể chứa đường dẫn, thông tin nội bộ, và ứng dụng có thể vô tình đặt dữ liệu nhạy cảm ở đó. Nên lưu các giá trị nhỏ, cần thiết, có kiểu dữ liệu tương thích với serializer; tránh đưa cả hàng triệu bản ghi hay đối tượng kết nối vào context.

### 3.3. Khi nào metadata được cập nhật?

Metadata không phải một dòng log ghi sau **mỗi item**. Với chunk-oriented step, framework ghi state/counters và checkpoint tại các thời điểm của vòng đời step, thường gắn với **ranh giới commit chunk**. Trong lúc một chunk đang chạy, số liệu trong repository có thể **chưa phản ánh item chưa commit**. Nếu transaction rollback, những cập nhật chưa commit cũng không thể được coi là kết quả cuối.

`readCount` và `writeCount` là **item counts theo `StepExecution`**, không luôn bằng số dòng database thực sự insert. Ví dụ writer dùng `INSERT ... ON CONFLICT DO NOTHING` có thể xử lý item thành công mà không tạo hàng mới. Dashboard vận hành phải đối soát với dữ liệu đích và quy tắc lọc/skip.

## 4. Vòng đời một worker StepExecution

~~~mermaid
sequenceDiagram
    participant M as Manager / PartitionHandler
    participant S as StepExecutionSplitter
    participant R as JobRepository
    participant W as Worker step
    participant D as Đích dữ liệu
    M->>S: Lấy worker executions cần chạy
    S->>R: Đối chiếu lịch sử, tạo/chuẩn bị StepExecution
    R-->>S: ID, trạng thái, ExecutionContext
    S-->>M: Worker StepExecution theo partition
    M->>W: Thực thi worker
    W->>R: Cập nhật trạng thái bắt đầu
    loop Theo từng chunk
        W->>W: Read / Process
        W->>D: Write
        W->>R: Ghi context/counters theo commit
    end
    W->>R: Ghi trạng thái cuối, ExitStatus, thời gian
    W-->>M: Kết quả worker
~~~

Một worker thành công thường kết thúc với `BatchStatus.COMPLETED`. Worker lỗi có thể `FAILED`; khi nhận yêu cầu dừng hợp lệ có thể `STOPPED`. `ExitStatus` cung cấp kết quả/ý nghĩa kết thúc ở mức Batch, còn exception hoặc log chi tiết giúp xác định nguyên nhân.

**Status worker và status manager là hai đối tượng khác nhau.** Manager có thể thất bại nếu một worker thất bại; nhưng việc đó không tự rollback các chunk đã commit từ worker khác. Mỗi worker có thể có transaction và checkpoint riêng.

### Ví dụ dữ liệu metadata sau một lượt chạy

*Ví dụ minh họa (ID và số đếm giả định):*

| STEP_EXECUTION_ID | STEP_NAME | STATUS | READ_COUNT | WRITE_COUNT |
| ---: | --- | --- | ---: | ---: |
| 210 | `ordersManagerStep` | FAILED | 0 | 0 |
| 211 | `ordersWorkerStep:range-0000` | COMPLETED | 25.000 | 25.000 |
| 212 | `ordersWorkerStep:range-0001` | FAILED | 12.400 | 12.400 |
| 213 | `ordersWorkerStep:range-0002` | COMPLETED | 25.000 | 25.000 |
| 214 | `ordersWorkerStep:range-0003` | STOPPED | 8.000 | 8.000 |

Đây là **một JobExecution**. Không thể kết luận hoàn tất 70.400 đơn hàng duy nhất chỉ bằng phép cộng counters: worker có thể filter/skip, retry, hoặc SQL no-op. Muốn biết phạm vi đã xử lý đầy đủ, cần đối chiếu theo business key tại nguồn/đích.

## 5. Restart: cùng partition, StepExecution có thể khác

Giả sử `JobInstance` đầu tiên có bốn partition như bảng trên. Job thất bại, người vận hành restart bằng **cùng bộ identifying JobParameters**. Spring Batch có thể tạo **JobExecution mới** cho cùng `JobInstance`, trong đó splitter sử dụng lịch sử worker để lựa chọn các partition cần chạy tiếp.

| Partition | Kết quả lượt trước | Quyết định thường gặp khi restart |
| --- | --- | --- |
| `range-0000` | COMPLETED | Không chạy lại theo chính sách mặc định |
| `range-0001` | FAILED | Tạo execution mới để chạy lại/tiếp tục |
| `range-0002` | COMPLETED | Không chạy lại theo chính sách mặc định |
| `range-0003` | STOPPED | Xem xét tiếp tục theo chính sách restart |

Lưu ý: đây là trường hợp **mô tả điển hình**, còn quyết định cụ thể phụ thuộc trạng thái metadata, `allowStartIfComplete`, chính sách restart và các giới hạn cấu hình.

Khi `range-0001` được thực thi lại, nó vẫn mang **tên partition logic** đó nhưng có thể có **`StepExecutionId` mới**. Framework sử dụng context/checkpoint thích hợp của partition theo cơ chế restart; một reader hỗ trợ `ItemStream` và lưu state có thể tiếp tục từ điểm đã lưu, thay vì đọc lại tất cả theo mặc định.

### Điều kiện để restart đáng tin cậy

1. **Giữ partition key ổn định:** Không sinh UUID/timestamp mới mỗi lần `partition()` được gọi.
2. **Giữ ánh xạ key → input:** `range-0001` phải tiếp tục đại diện đúng dải ID/file đã gán trước sự cố.
3. **Giữ nguồn dữ liệu nhất quán:** Nếu dữ liệu thay đổi giữa các lần chạy, cần snapshot, watermark hoặc manifest phù hợp. Chỉ giữ `minId`/`maxId` không tự bảo đảm snapshot.
4. **Lưu checkpoint đúng cách:** Reader/writer có state cần triển khai hoặc sử dụng `ItemStream`, đặt tên ổn định và cập nhật `ExecutionContext` đúng vòng đời.
5. **Bảo vệ đích khi replay:** Idempotent writer, unique business key, transaction hoặc outbox/inbox khi có hiệu ứng ngoài database.

Nếu cùng `range-0001` nhưng ở lần restart bạn đổi từ `[25001, 50001)` thành `[40001, 80001)`, lịch sử và checkpoint cũ sẽ chỉ tới phần việc **không còn tương đương**. Splitter không thể tự suy luận ý nghĩa nghiệp vụ của phạm vi mới từ cùng một tên.

### JobInstance mới khác restart

Nếu chạy job với identifying parameters khác để tạo `JobInstance` mới, các worker execution của instance cũ không tự trở thành checkpoint cho instance mới. `JobRepository` lưu lịch sử, nhưng không thay thế cơ chế dedupe nghiệp vụ giữa những lần chạy khác nhau. Re-run cùng một file dưới instance mới vẫn cần chính sách idempotency để tránh ghi trùng.

## 6. Quan sát worker bằng JobExplorer

Đối với ứng dụng Spring Batch, `JobExplorer` là API **chỉ đọc** để tra cứu metadata job/step. Nó thích hợp cho bảng điều khiển vận hành hoặc tác vụ điều tra mà không cần sửa bảng metadata trực tiếp.

Ví dụ Java dùng Spring Batch 5.x, nhận `jobExecutionId` cụ thể:

~~~java
import java.util.Comparator;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.stereotype.Service;

@Service
public class WorkerExecutionInspector {

    private final JobExplorer jobExplorer;

    public WorkerExecutionInspector(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public void printWorkerStatus(long jobExecutionId) {
        JobExecution job = jobExplorer.getJobExecution(jobExecutionId);
        if (job == null) {
            throw new IllegalArgumentException(
                    "Không tìm thấy JobExecution: " + jobExecutionId);
        }

        job.getStepExecutions().stream()
                .filter(step -> step.getStepName()
                        .startsWith("ordersWorkerStep:"))
                .sorted(Comparator.comparing(StepExecution::getStepName))
                .forEach(step -> System.out.printf(
                        "id=%d step=%s status=%s read=%d write=%d "
                        + "rollback=%d%n",
                        step.getId(),
                        step.getStepName(),
                        step.getStatus(),
                        step.getReadCount(),
                        step.getWriteCount(),
                        step.getRollbackCount()));
    }
}
~~~

Ở đây điều kiện `startsWith("ordersWorkerStep:")` phù hợp với **quy ước tên worker của ví dụ này**, không phải bộ lọc chung cho mọi job. Trong hệ thống có nhiều loại step hoặc manager names tùy biến, cần chọn cách lọc theo kiến trúc ứng dụng.

Khi cần theo dõi cả **lịch sử restart**, không chỉ lấy một `JobExecution` mới nhất mà cần đọc các `JobExecution` liên quan của cùng `JobInstance`. Các execution đã thất bại trong quá khứ vẫn hữu ích để phân tích sự cố, nhưng **không cộng raw counters qua mọi lần chạy** để kết luận số business record đã ghi thành công duy nhất.

### Vì sao không sửa metadata bằng SQL thủ công?

Việc cập nhật trực tiếp `STATUS`, `VERSION` hoặc context trong bảng `BATCH_STEP_EXECUTION` để “ép” một partition `COMPLETED` có thể làm sai cơ chế optimistic locking, restart và lịch sử xử lý. Hãy dùng API quản trị Batch phù hợp, kiểm tra transaction, khắc phục nguyên nhân lỗi và khởi chạy lại theo chính sách được hỗ trợ.

Nếu context serialization thay đổi giữa các lần nâng cấp, phải kiểm thử khả năng đọc lại metadata của các job đang chờ restart. Không tự chỉnh dữ liệu đã serialize bằng các thao tác chuỗi hoặc công cụ SQL không hiểu format.

## 7. Worker execution trong local và remote partitioning

### Local: nhiều thread, một ứng dụng

Với `TaskExecutorPartitionHandler`, các worker `StepExecution` được thực thi bởi executor trong cùng JVM. Thông thường:

- Mỗi partition có context riêng, có thể bind reader bằng `@StepScope`.
- Các worker vẫn chia sẻ nguồn lực của tiến trình: CPU, heap, thread pool, database connection pool.
- `JobRepository` được dùng để lưu metadata của các worker, bất kể chúng chạy trên thread nào.
- Nếu executor có bốn slot nhưng partitioner tạo 12 phần việc, có thể có tối đa khoảng bốn worker hoạt động đồng thời; `gridSize` không trực tiếp bằng số thread.

### Remote: nhiều JVM/container

Với remote partitioning, manager tạo/chọn worker `StepExecution`, rồi handler gửi yêu cầu đến worker qua hệ thống thông điệp. Worker ở JVM khác cần có quyền truy cập **cùng kho metadata nhất quán** để tải execution/context và ghi lại kết quả, tùy cơ chế tích hợp.

~~~mermaid
flowchart LR
    M["Manager JVM<br/>splitter + handler"] --> Q["Broker / request channel"]
    Q --> W1["Worker JVM 1"]
    Q --> W2["Worker JVM 2"]
    Q --> W3["Worker JVM 3"]
    M <--> R[("JobRepository dùng chung")]
    W1 <--> R
    W2 <--> R
    W3 <--> R
    W1 --> D[("Đích nghiệp vụ")]
    W2 --> D
    W3 --> D
~~~

**Nguy cơ cần kiểm soát:** Nếu broker giao lại request sau timeout hoặc worker đã commit nhưng phản hồi bị mất, có thể có yêu cầu xử lý cùng partition lặp lại. `JobRepository` là cơ sở để hòa giải trạng thái, song không phải cam kết tự động chống mọi chạy chồng hoặc chống tác dụng phụ trùng. Cần thiết kế timeout, dedupe/claim, idempotent writer và quy tắc khôi phục phù hợp.

Khác với remote chunking, remote partitioning gửi **yêu cầu thực thi worker step/partition**, không gửi từng chunk item được manager đọc sẵn.

## 8. Transaction, checkpoint và tính đúng đắn của dữ liệu

Metadata có giá trị khi cơ chế transaction và checkpoint được cấu hình đúng.

### 8.1. Nếu worker ghi cùng database và cùng transaction

Một chunk điển hình thực hiện đọc/xử lý/ghi rồi commit. Nếu writer và metadata checkpoint cùng tham gia một transaction thích hợp, khi lỗi dẫn tới rollback, các thay đổi chưa commit không được coi là đã xử lý xong. Đây là cơ sở để restart từ checkpoint hợp lệ.

Tuy nhiên **không được mặc định** mọi hệ thống đều có một transaction duy nhất: `JobRepository` và dữ liệu nghiệp vụ có thể nằm trên các datasource khác nhau, hoặc có một API bên ngoài không tham gia transaction. Phải kiểm tra rõ `PlatformTransactionManager`, datasource của writer và ranh giới rollback.

### 8.2. Nếu worker gọi API hoặc gửi message

Trường hợp kinh điển:

~~~text
Worker gửi lệnh thanh toán thành công
          ↓
Mạng đứt trước khi worker lưu trạng thái/nhận phản hồi
          ↓
Job restart và thực hiện lại item
          ↓
Nếu API không dedupe, khách hàng có thể bị charge hai lần
~~~

Khi ấy `StepExecution` và checkpoint chỉ phản ánh điều Batch **biết hoặc đã lưu**, không nhất thiết phản ánh mọi tác dụng phụ đã xảy ra ngoài hệ thống. Biện pháp phù hợp có thể là idempotency key bền vững tại API nhận, transaction outbox/inbox hoặc ledger chống trùng nghiệp vụ.

### 8.3. Metadata lỗi hoặc repository quá tải

Mỗi partition có ít nhất một worker execution và context liên quan; nhiều partition nhỏ tạo thêm metadata, transaction, checkpoint và thời gian điều phối. Với hàng chục nghìn partition, metadata DB có thể trở thành một nút thắt.

Các chỉ số nên theo dõi gồm thời gian ghi/đọc `JobRepository`, số kết nối metadata, lock wait/optimistic locking exception, độ dài hàng đợi handler, số worker đang chạy và thời gian restart. Không tăng `gridSize` chỉ vì số CPU tăng mà không đo chi phí tạo execution.

## 9. Các truy vấn điều tra hữu ích

### 9.1. Worker nào thất bại trong một lượt chạy?

~~~sql
SELECT
    STEP_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    EXIT_CODE,
    EXIT_MESSAGE,
    ROLLBACK_COUNT,
    LAST_UPDATED
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
  AND STATUS IN ('FAILED', 'STOPPED', 'UNKNOWN')
ORDER BY STEP_EXECUTION_ID;
~~~

Trong truy vấn trên, có thể xuất hiện **manager step** hoặc worker; cần phân loại theo tên step của ứng dụng trước khi quyết định restart. `EXIT_MESSAGE` có thể dài hoặc chứa thông tin lỗi nội bộ; cần lọc thông tin nhạy cảm khi hiển thị dashboard.

### 9.2. Partition nào có biểu hiện chậm?

~~~sql
SELECT
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT,
    START_TIME,
    END_TIME
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY START_TIME, STEP_EXECUTION_ID;
~~~

Để tính throughput, cần so sánh delta counter theo thời gian hoặc dùng thời lượng của execution **đã hoàn thành** (và tránh chia cho thời gian bằng 0). Một partition có `writeCount` thấp không nhất thiết bị lỗi nếu nó có ít bản ghi hơn hoặc nhiều item bị filter. Hãy quan sát thêm CPU, I/O, transaction latency và business key.

### 9.3. Tìm lịch sử cùng một tên partition

~~~sql
SELECT
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.LAST_UPDATED
FROM BATCH_STEP_EXECUTION se
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_EXECUTION_ID = se.JOB_EXECUTION_ID
JOIN BATCH_JOB_INSTANCE ji
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_INSTANCE_ID = :jobInstanceId
  AND se.STEP_NAME = :workerPartitionStepName
ORDER BY je.JOB_EXECUTION_ID, se.STEP_EXECUTION_ID;
~~~

Truy vấn này giúp thấy một partition logic, ví dụ `ordersWorkerStep:range-0001`, đã có bao nhiêu execution trong **cùng một JobInstance**. Cần phân biệt execution thành công cuối với các attempt trước đó; không dùng tổng `WRITE_COUNT` làm số item duy nhất.

## 10. Case study: điều tra một partition sau sự cố

**Bối cảnh:** Job nhập 1 triệu đơn hàng chia thành 8 partition. Lúc 01:40, một worker trên máy thứ hai mất kết nối database; manager báo `FAILED`. Hệ thống đích đã có nhiều chunk commit từ worker đó.

Một quy trình xử lý tốt:

1. **Xác định JobInstance và JobExecution:** Ghi lại identifying parameters, thời điểm chạy, phiên bản input và ID metadata.
2. **Liệt kê StepExecution:** Xác định manager và tám worker, kiểm tra `STATUS`, `EXIT_CODE`, `ROLLBACK_COUNT` và counters từng partition.
3. **Kiểm tra ExecutionContext:** Đảm bảo worker lỗi dùng đúng dải ID/file; xác định checkpoint đã lưu và phạm vi input có còn bất biến không.
4. **Kiểm tra transaction và lỗi:** Tìm exception gốc, tình trạng DB pool, timeout, deadlock, transaction rollback và thay đổi hạ tầng.
5. **Đối soát dữ liệu:** So sánh business key nguồn/đích, số hàng insert thực tế, các bản ghi bị skip hoặc dedupe. Không coi `writeCount` là số hàng mới.
6. **Restart đúng kế hoạch:** Giữ nguyên partition key→input của `JobInstance`. Dùng cơ chế restart của Batch thay vì tự sửa `STATUS` trong DB.
7. **Xác nhận sau restart:** Đảm bảo tất cả partition kết thúc hợp lệ, số liệu nghiệp vụ đầy đủ, không trùng tác dụng phụ và throughput trở lại bình thường.

### Bảng phân biệt triệu chứng

| Quan sát | Không nên kết luận vội | Cần kiểm tra |
| --- | --- | --- |
| Worker `FAILED` với `readCount = 20.000` | “Đã ghi 20.000 bản ghi” | `writeCount`, chunk commit, dữ liệu đích |
| Manager `FAILED` | “Mọi dữ liệu của job đều rollback” | Những partition khác có thể đã commit |
| Restart tạo `STEP_EXECUTION_ID` mới | “Đó là partition mới” | So sánh partition key và `JobInstance` |
| Job `COMPLETED` nhưng đích thiếu hàng | “JobRepository sai số liệu” | Filter, skip, SQL no-op, nguồn thay đổi, writer |
| Nhiều execution cùng tên partition | “Spring Batch chạy trùng chắc chắn” | Lịch sử restart và status/attempt |
| Worker remote không phản hồi | “Nó chưa ghi gì” | DB commit, JobRepository, broker ack và idempotency |

## 11. Checklist thiết kế và kiểm thử

Trước khi đưa partitioned job lên production, hãy kiểm tra:

- **Định danh:** Mỗi partition key duy nhất trong kế hoạch, ổn định khi restart; worker `STEP_NAME` và `JobInstance` được ghi nhận để điều tra.
- **ExecutionContext:** Chứa tham số đầu vào và checkpoint nhỏ, serializer tương thích, không có dữ liệu nhạy cảm hoặc object không cần thiết.
- **Reader/writer:** Mỗi worker chỉ đọc tập input không giao nhau; reader stateful dùng scope phù hợp; writer idempotent với replay.
- **Metadata:** `JobRepository` dùng backend bền vững, phù hợp concurrency và có giám sát transaction/connection.
- **Remote worker:** Cùng metadata repository nhất quán, worker nhận đúng step/context, kiểm soát retry và trùng request.
- **Restart:** Thử lỗi sau một số chunk đã commit, giữ kế hoạch phân vùng cũ, xác minh worker hoàn thành không chạy lại trái chính sách.
- **Đối soát:** Có metric và phép kiểm tra business key ở nguồn/đích, phân biệt item count với số hàng thực sự thay đổi.
- **Tối ưu tài nguyên:** Đo thời gian tạo/chạy partitions, số slot worker, DB I/O, lock wait và overhead metadata trước khi tăng `gridSize`.

### Câu hỏi tự kiểm tra

Trong lần chạy đầu, `ordersWorkerStep:range-0001` thất bại sau khi ghi được nhiều chunk. Job được restart và xuất hiện `StepExecutionId` mới cho đúng tên `ordersWorkerStep:range-0001`, trong khi `range-0000` không xuất hiện ở lượt này. Người vận hành cho rằng repository bị mất lịch sử vì hai execution có ID khác nhau.

**Định hướng trả lời:** Đây có thể là hành vi **restart bình thường**: cùng partition logic có execution mới, còn partition đã hoàn tất không cần chạy lại theo chính sách mặc định. Lịch sử vẫn thuộc cùng `JobInstance` và cần xem qua các `JobExecution` của instance đó. Chỉ kết luận lỗi sau khi so sánh partition key/context, trạng thái, checkpoint và dữ liệu đích.

## Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): mô hình partitioning và worker steps.
- [Spring Batch Reference — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): bảng `BATCH_STEP_EXECUTION`, `BATCH_STEP_EXECUTION_CONTEXT` và quan hệ job/step.
- [Spring Batch API — JobRepository](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/repository/JobRepository.html): thao tác quản lý metadata execution.
- [Spring Batch API — JobExplorer](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/explore/JobExplorer.html): đọc lịch sử job và step.
- [Spring Batch API — StepExecution](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/StepExecution.html): counters, status và execution context.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): khôi phục step và checkpoint.
- [Spring Batch Integration — Remote Partitioning](https://docs.spring.io/spring-batch/reference/spring-batch-integration/remote-partitioning.html): worker từ xa và metadata.

> **Ghi nhớ:** Mỗi worker partition có **`StepExecution` và `ExecutionContext` riêng trong `JobRepository`**. Metadata giúp điều phối, giám sát và restart, nhưng không thay thế **partition key ổn định, ranh giới input chính xác, transaction đúng và đối soát/idempotency tại hệ thống đích**.
