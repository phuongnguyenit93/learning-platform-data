# Remote step so với partitioning trong Spring Batch

## 1. Cùng chạy từ xa nhưng không cùng mục đích

Một nền tảng xử lý dữ liệu cần làm hai việc:

- Bước `generateMonthlyReport` cần chạy trên máy có thư viện xử lý tài liệu và nhiều RAM, tách khỏi máy điều phối job.
- Bước `normalizeTransactions` cần xử lý 24 triệu giao dịch; dữ liệu có thể chia thành hàng chục miền ID, mỗi miền do một worker xử lý song song.

Hai yêu cầu này đều có thể liên quan đến **worker ở tiến trình khác**, nhưng không nên dùng cùng một kiến trúc:

- **Remote step** chuyển **một step logic** sang một worker từ xa. Mục tiêu chính là **thực thi step ở nơi khác**, không phải tự chia step thành nhiều partition.
- **Partitioning** chia **một step logic** thành nhiều **`StepExecution` độc lập**, mỗi execution sở hữu một phần dữ liệu. Nó có thể chạy trên nhiều thread cùng JVM (**local partitioning**) hoặc nhiều worker service (**remote partitioning**).

Đó là nội dung bài **“Remote step so với partitioning”**, thuộc chương **Remote Step** của module `SPRING_BATCH_SCALING_OPERATIONS`. Module hướng tới mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và xử lý phân tán; học đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và chọn kiến trúc phù hợp tài nguyên thực tế.

Sau bài này, bạn sẽ có thể:

1. Phân biệt **di chuyển vị trí chạy step** với **chia nhỏ step để chạy song song**.
2. Mô tả đường đi của metadata, `StepExecutionRequest`, worker step và `JobRepository`.
3. Chọn giữa remote step, local/remote partitioning, remote chunking và parallel flows.
4. Thiết kế ranh giới dữ liệu, concurrency, checkpoint và idempotency an toàn.
5. Dự báo chi phí broker/DB/connection và phân tích vì sao thêm worker chưa chắc nhanh hơn.
6. Lập kế hoạch kiểm thử lỗi manager, worker, broker và kịch bản restart.

**Phạm vi phiên bản:** `RemoteStep` là API được giới thiệu trong **Spring Batch 6.0**. Local/remote partitioning đã tồn tại từ các phiên bản Spring Batch trước đó, trong đó có **5.x**. Khi dùng 5.x, không lấy ví dụ API `RemoteStep` 6.x áp thẳng vào project; hãy sử dụng các cơ chế partitioning hoặc flow phù hợp với phiên bản dự án.

## 2. Nhìn nhanh sự khác biệt

| Tiêu chí | Remote step | Local partitioning | Remote partitioning |
|---|---|---|---|
| Mục tiêu chính | Đưa một step sang process/máy khác | Chia một step thành nhiều phần trong JVM | Chia một step thành nhiều phần và phân phối qua process/máy |
| Đơn vị giao việc | **Một lần thực thi worker step** | Nhiều worker `StepExecution` | Nhiều worker `StepExecution` |
| Ai chia dữ liệu? | **Không tự chia**; reader/step tự xác định input | `Partitioner` tạo `ExecutionContext` theo partition | `Partitioner` tạo `ExecutionContext` theo partition |
| Số execution làm việc | Thường một cho mỗi remote step logic | Một cho mỗi partition | Một cho mỗi partition |
| Vị trí worker | Service/process từ xa | Thread trong JVM manager | Service/process từ xa |
| Truyền qua broker | Yêu cầu chạy step | Không bắt buộc | Yêu cầu chạy từng partition |
| Metadata | Execution được phối hợp qua repository dùng chung | Repository chứa các partition execution | Repository dùng chung để theo dõi các partition execution |
| Mở rộng theo số phần dữ liệu | Không tự động | Bằng số partition và executor | Bằng số partition và số worker/concurrency |
| Restart | Theo metadata và lifecycle của step được giao | Theo trạng thái/checkpoint từng partition | Theo trạng thái/checkpoint từng partition |
| Chi phí vận hành | Worker riêng, middleware, timeout/polling | Đồng bộ/lifecycle nhiều thread trong một JVM | Broker, nhiều worker, aggregation, distributed failures |

**Kết luận sơ bộ:** nếu bạn muốn “chạy bước tạo PDF nặng ở service khác”, hãy xem **remote step**; nếu muốn “chia 24 triệu bản ghi thành 48 phần để xử lý nhanh hơn”, hãy xem **partitioning**. Nếu cả hai yêu cầu cùng xuất hiện, có thể thiết kế nhiều tầng theo ràng buộc framework và vận hành thực tế, nhưng không giả định một remote step tự biến thành 48 worker.

## 3. Kiến trúc remote step: dịch chuyển nơi thực thi

Trong **Spring Batch 6.x**, manager job chứa một `RemoteStep` đóng vai trò đại diện cho bước thực thi ở xa. Nó gửi yêu cầu đến worker qua một message channel; worker nhận yêu cầu và gọi step đã đăng ký. Metadata theo dõi thực thi được lưu trong `JobRepository` để manager biết step đã kết thúc hay chưa.

~~~mermaid
flowchart LR
    S[Scheduler / JobLauncher] --> J[Manager Job]
    J --> R[RemoteStep proxy]
    R -->|Một yêu cầu chạy step| Q[(Request queue)]
    Q --> H[Worker service<br/>StepExecutionRequestHandler]
    H --> W[Worker Step<br/>reportGenerator]
    W --> D[(Nguồn/đích nghiệp vụ)]
    R <-->|Theo dõi trạng thái| DB[(Shared JobRepository)]
    H <-->|Truy xuất execution| DB
    W <-->|Checkpoint/metadata| DB
~~~

### Remote step làm gì?

Một chu kỳ thông thường:

1. Manager khởi chạy job với `JobParameters` xác định.
2. Đến `RemoteStep`, manager chuẩn bị/tham chiếu metadata của lần thực thi step và gửi `StepExecutionRequest` tới worker.
3. Worker dùng `StepExecutionRequestHandler` để tìm metadata và mã `Step` có tên tương ứng (qua `StepLocator`), rồi chạy step.
4. Reader/processor/writer phía worker thực hiện logic nghiệp vụ và lưu trạng thái/checkpoint qua repository.
5. Manager theo dõi trạng thái step trong `JobRepository` theo cơ chế **polling** của remote step; khi step kết thúc hoặc gặp lỗi, manager xử lý kết quả theo flow job.

Handler **không tự chia dữ liệu** và cũng không tạo một `JobInstance` mới cho mỗi message. Step mà nó gọi vẫn có thể là chunk-oriented step hoặc tasklet, với transaction và lifecycle riêng.

### Tại sao cần dùng remote step?

Các lý do phù hợp thường liên quan đến **placement**:

- Bước kết xuất báo cáo cần font/engine hoặc bộ nhớ nhiều hơn manager.
- Bước ETL cần chạy trong mạng nội bộ chỉ worker được phép truy cập.
- Bước xử lý dữ liệu cần được cách ly khỏi service điều phối để bảo vệ uptime.
- Một flow có nhiều bước khác nhau, mỗi bước phù hợp một loại node/role khác nhau.
- Muốn phát hành worker logic và cấp tài nguyên riêng cho một bước tốn CPU/I/O.

Đây là lợi ích **cô lập và điều phối**, không phải bằng chứng rằng remote step nhanh hơn local step. Thêm network, startup, message broker, polling và quản trị nhiều service có thể còn làm tăng độ trễ cho tác vụ nhỏ.

### Giới hạn quan trọng

Một remote step **không tự động tạo nhiều worker execution cho cùng tập dữ liệu**. Nếu worker step đọc toàn bộ 24 triệu bản ghi bằng một cursor tuần tự, chuyển nó sang máy khác vẫn chỉ có một luồng logic đọc/ghi trừ khi chính worker step áp dụng một cơ chế xử lý đồng thời khác. Muốn chia data thành N phần có checkpoint độc lập thì partitioning thường diễn đạt bài toán tốt hơn.

## 4. Kiến trúc partitioning: chia một bước thành nhiều phần

Trong partitioning, manager thực hiện **planning**: gọi `Partitioner` để tạo các `ExecutionContext` riêng cho từng partition. Spring Batch gắn chúng với các worker `StepExecution` được định danh ổn định. Worker step đọc dữ liệu theo context được giao.

~~~mermaid
flowchart TB
    J[Job] --> M[Partition manager step]
    M --> P[Partitioner]
    P --> A[partition0<br/>id 1..100000]
    P --> B[partition1<br/>id 100001..200000]
    P --> C[partition2<br/>id 200001..300000]
    A --> E1[Worker StepExecution 0]
    B --> E2[Worker StepExecution 1]
    C --> E3[Worker StepExecution 2]
    E1 --> D[(Business data)]
    E2 --> D
    E3 --> D
    M <-->|Manager + worker metadata| R[(JobRepository)]
    E1 --> R
    E2 --> R
    E3 --> R
~~~

Sơ đồ trên thể hiện **logic partition**, chưa quyết định worker chạy tại đâu:

- Với **local partitioning**, `TaskExecutorPartitionHandler` hoặc cơ chế phù hợp chạy các `StepExecution` trong cùng JVM.
- Với **remote partitioning**, manager chuyển `StepExecutionRequest` qua middleware; worker service chạy step và cập nhật metadata.

Khác remote step, partitioning cho phép manager biết **các đơn vị công việc nhỏ** và theo dõi tiến độ/lỗi của từng phần.

### Định danh và ranh giới dữ liệu

Một execution context có thể gồm:

~~~yaml
# Minh họa giá trị logic trong StepExecutionContext, không phải payload bắt buộc của broker
partitionName: partition03
minId: 300001
maxId: 400000
snapshotKey: orders-2026-11-26-v1
~~~

Trong remote partitioning chuẩn, message thường mang **tên step và các ID execution**, còn `ExecutionContext` gắn với metadata trong `JobRepository`. Worker truy xuất context đó; không giả định phải chuyển toàn bộ dữ liệu nghiệp vụ trong message.

Một partition plan đáng tin phải **không giao nhau**, **phủ đủ tập dữ liệu dự kiến**, **ổn định khi restart** và không lệ thuộc vào số worker đang chạy. Nếu dữ liệu skew nặng, các khoảng ID bằng độ rộng có thể tạo thời gian xử lý rất khác nhau.

## 5. Remote step và remote partitioning: cùng transport, khác contract

Hai mô hình có thể dùng Spring Batch Integration, `StepExecutionRequestHandler` và message broker, nhưng yêu cầu của manager khác nhau:

~~~mermaid
flowchart TB
    subgraph RS[Remote step]
      R1[Manager: RemoteStep] -->|Một worker step request| Q1[(Broker)]
      Q1 --> W1[Worker: một step logic]
      W1 --> Repo1[(JobRepository)]
      Repo1 -. Manager polling .-> R1
    end
    subgraph RP[Remote partitioning]
      R2[Manager: Partitioner] --> R3[N partition executions]
      R3 -->|N execution requests| Q2[(Broker)]
      Q2 --> W2[Worker A]
      Q2 --> W3[Worker B]
      W2 --> Repo2[(JobRepository)]
      W3 --> Repo2
      Repo2 -. Aggregation / status .-> R2
    end
~~~

### Tại manager

**Remote step:** khai báo một bước từ xa trong flow của job. Điều cần quyết định là **worker step nào**, routing tới đâu, polling/timeout và điều kiện kết thúc của bước đó.

**Remote partitioning:** khai báo một **manager step** gắn với `Partitioner` và worker step name. Manager tạo nhiều partition execution, phân phối request, rồi **aggregate** trạng thái hoàn thành/thất bại của tập partition.

### Tại worker

**Remote step:** worker có một bean `Step` với tên được yêu cầu, đủ dependency để chạy; handler tải/nhận execution và gọi step.

**Remote partitioning:** worker có worker step dùng chung **định nghĩa code**, nhưng được gọi với nhiều `StepExecution` và `ExecutionContext` khác nhau. Reader thường cần `@StepScope` để nhận range/file/tenant riêng.

### Tại JobRepository

**Remote step** và **remote partitioning** đều dựa vào metadata để phân biệt job instance, trạng thái step, checkpoint và retry/restart. Tuy nhiên, partitioning có **nhiều child step execution** tương ứng các partition; remote step không tạo ra danh sách partition chỉ vì được chạy qua broker.

**Lưu ý về version:** `StepExecutionRequest`/handler của Spring Batch 5.x và 6.x không có API giống hệt nhau. Khi xây service riêng, manager và worker phải dùng **bộ version tương thích** (gồm metadata schema, tên step và serialization). Không dùng request serialized từ major version này rồi kỳ vọng handler major version khác đọc được.

## 6. Ví dụ cùng bài toán, hai thiết kế khác nhau

### Tình huống A — Chạy bước kết xuất báo cáo tại worker riêng

Một job có các bước:

~~~text
validateInputStep
       |
       v
renderReportRemoteStep  ---> renderReportWorker (dịch vụ RAM lớn)
       |
       v
publishReportStep
~~~

Tất cả input của một lần xuất báo cáo là một package bất biến, chẳng hạn một snapshot ID. Việc dựng báo cáo cần thư viện native và 8 GiB RAM; manager chỉ cần giữ flow, retry/restart và ghi kết quả.

Ở đây **remote step** là lựa chọn tự nhiên vì cần **đổi nơi chạy một bước**, không nhất thiết cần chia bước thành nhiều execution. Có thể cung cấp `reportSnapshotKey` qua `JobParameters` hoặc context chuẩn bị trước, để worker tự tải dữ liệu. Worker không nên nhận cả bản báo cáo đầu vào dung lượng lớn dưới dạng message.

Trong ứng dụng thật, manager phải cấu hình transport của `RemoteStep` để gửi request qua broker và chọn timeout hợp lý với thời gian dựng báo cáo; worker đăng ký đúng step name, xử lý lỗi và ghi trạng thái vào repository chung.

### Tình huống B — Chuẩn hóa hàng chục triệu giao dịch

Cùng một logic `normalizeTransaction` áp dụng cho tất cả giao dịch. Dữ liệu có khóa `id` và có thể chia thành 48 khoảng không giao nhau; từng khoảng được đọc, xử lý và ghi độc lập. Hệ thống muốn scale từ 4 lên 12 worker pod.

**Remote partitioning** phù hợp hơn vì:

- Mỗi khoảng có `StepExecution` và checkpoint riêng.
- Nhiều pod có thể xử lý các phần khác nhau đồng thời.
- Khi một pod chết, chỉ những partition chưa hoàn tất cần khôi phục theo chính sách restart.
- Manager nhìn thấy phân bố thời gian và lỗi theo partition.
- Có thể thay đổi số worker mà không thay đổi kế hoạch partition của một lần chạy.

Nếu chuyển toàn bộ logic sang **một remote step**, vẫn chỉ có một vùng làm việc logic. Mặc dù worker có thể dùng CPU mạnh hơn, kiến trúc đó **không tự tạo 48 partition**.

### Tình huống C — 300 file có kích thước khác nhau

Nếu mỗi file có thể xử lý độc lập, dùng một manifest chứa file ID và version rồi tạo một partition cho mỗi file hoặc nhóm file. Worker step dùng `stepExecutionContext['fileKey']` để mở đúng file. Cần ước lượng dung lượng mỗi file để tránh một partition lớn gấp 50 lần những partition còn lại.

Trường hợp này phân phối theo **partition/file** thích hợp hơn một remote step chung cho 300 file tuần tự. Nhưng nếu chỉ cần một worker có đặc quyền truy cập file để chuyển toàn bộ một dataset không chia được, remote step có thể đơn giản hơn.

### Tình huống D — Một API downstream giới hạn 100 request/giây

Nếu mọi worker đều gọi cùng API bị áp quota, tăng từ 4 lên 40 partition concurrent có thể gây HTTP 429, retry storm và wall-clock time **tệ hơn**. Trước khi chọn remote partitioning, cần xác định quota/rate limit, backpressure và giới hạn concurrency toàn cụm. Remote step đơn có thể đủ nếu độ song song không mang lại lợi ích.

## 7. Mẫu code: một Partitioner và reader late binding

Đây là ví dụ **Spring Batch 5.x** minh họa phần quan trọng khiến partitioning khác remote step: mỗi execution có ranh giới dữ liệu riêng. Có thể dùng nó với local hoặc remote partitioning; các bean Job/Step, DataSource và message adapter đầy đủ được lược bớt.

### 7.1. Partitioner chia range không giao nhau

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class IdRangePartitioner implements Partitioner {
    private final long firstId;
    private final long lastId;

    public IdRangePartitioner(long firstId, long lastId) {
        if (firstId > lastId) {
            throw new IllegalArgumentException("Empty input range");
        }
        this.firstId = firstId;
        this.lastId = lastId;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        long total = Math.addExact(
                Math.subtractExact(lastId, firstId), 1L);
        int count = (int) Math.min((long) gridSize, total);
        long base = total / count;
        long extra = total % count;
        long start = firstId;

        Map<String, ExecutionContext> plan = new LinkedHashMap<>();
        for (int i = 0; i < count; i++) {
            long size = base + (i < extra ? 1L : 0L);
            long end = Math.addExact(start, size - 1L);

            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", start);
            context.putLong("maxId", end);
            plan.put("partition" + i, context);

            if (i + 1 < count) {
                start = Math.addExact(end, 1L);
            }
        }
        return plan;
    }
}
~~~

Với `firstId=1`, `lastId=11`, `gridSize=3`, hàm trả `partition0=1..4`, `partition1=5..8`, `partition2=9..11`. Mỗi ID thuộc chính xác một khoảng; nếu bảng có ID thưa thì vẫn không làm sai điều kiện không giao nhau, nhưng số record trong mỗi khoảng có thể rất chênh lệch.

`gridSize` là chỉ dẫn về **số phần công việc**, không tự tạo số pod/consumer tương ứng. Với `Partitioner` đặc thù, số partition thực trả về có thể khác `gridSize`.

### 7.2. Worker reader lấy range từ StepExecutionContext

~~~java
import javax.sql.DataSource;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
public JdbcCursorItemReader<Long> transactionReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    if (minId == null || maxId == null || minId > maxId) {
        throw new IllegalArgumentException("Invalid partition context");
    }

    return new JdbcCursorItemReaderBuilder<Long>()
            .name("transactionRangeReader")
            .dataSource(dataSource)
            .sql("SELECT id FROM transactions "
               + "WHERE id >= ? AND id <= ? ORDER BY id")
            .preparedStatementSetter(ps -> {
                ps.setLong(1, minId);
                ps.setLong(2, maxId);
            })
            .rowMapper((rs, rowNum) -> rs.getLong("id"))
            .saveState(true)
            .build();
}
~~~

Từng partition sẽ có **reader target riêng** vì `@StepScope` tạo bean theo `StepExecution`. `ORDER BY id` ổn định giúp checkpoint có ý nghĩa. Nên chốt snapshot/cutoff và tránh việc writer cập nhật điều kiện lọc của reader trong lúc chạy.

Ví dụ này cũng nhấn mạnh giới hạn của scope: nếu nhiều thread xử lý **cùng một `StepExecution`** trong multi-threaded step, `@StepScope` chỉ có một target reader cho execution ấy; nó không tự biến cursor thành thread-safe. Local/remote partitioning với nhiều `StepExecution` tách biệt thường dễ cô lập trạng thái hơn.

### 7.3. Pseudocode cấu hình hai kiến trúc

Để tránh nhầm API giữa major versions, sơ đồ sau diễn đạt **thứ tự wiring**, không phải Java copy-paste chạy ngay:

~~~text
REMOTE STEP (Spring Batch 6.x):
  manager Job
    -> RemoteStep (tên logical step, tên worker step)
    -> MessagingTemplate / outbound request adapter
    -> broker
  worker service
    -> inbound message adapter
    -> StepExecutionRequestHandler + StepLocator
    -> worker Step thực thi
    -> JobRepository chung
  manager RemoteStep -> polling JobRepository -> kết quả

REMOTE PARTITIONING (Spring Batch 5.x hoặc 6.x):
  manager Job
    -> partition manager step
    -> Partitioner (N ExecutionContext)
    -> RemotePartitioningManagerStepBuilder / partition handler
    -> broker: N StepExecutionRequest
  worker service
    -> inbound request adapter
    -> remote partition worker configuration / handler
    -> worker Step + @StepScope reader
    -> JobRepository chung
  manager -> aggregate trạng thái N worker StepExecution
~~~

Trong remote partitioning, manager có thể nhận **reply channel** hoặc theo dõi kết quả qua metadata repository tùy cấu hình. Với `RemoteStep` 6.x, manager được thiết kế để **polling trạng thái ở JobRepository**, nên không nên máy móc sao chép một reply queue bắt buộc từ ví dụ remote partitioning.

## 8. So sánh lifecycle, retry và restart

Một job phân tán có ít nhất hai loại rủi ro:

1. **Lỗi nghiệp vụ:** SQL, file, API, validation, transaction trong worker.
2. **Lỗi điều phối:** request không tới worker, worker bị kill, broker reconnect, phản hồi mất hoặc manager chết.

### Remote step

Một remote step có **một logical step được giao thực thi ở worker**. Khi worker thất bại, Spring Batch sử dụng metadata để nhận biết trạng thái thực thi và quyết định restart theo job/step lifecycle. Chi tiết phục hồi phụ thuộc cách worker lưu checkpoint, `ItemStream`, transaction và timeout của remote step.

Nếu worker đã commit dữ liệu nhưng manager mất kết nối, **timeout ở manager không có nghĩa worker chưa xử lý**. Cần tra `JobRepository`, worker log và side effect. Không tự phát một request mới khi execution cũ có thể còn chạy.

### Partitioning

Mỗi partition có `StepExecution` riêng. Khi một partition thất bại, manager có thể xác định **partition nào** chưa hoàn thành; các partition `COMPLETED` thường được bỏ qua trên restart bình thường nếu cấu hình step và metadata cho phép.

Checkpoint thuộc context của từng partition, ví dụ một reader đọc `1..100000` có vị trí riêng, độc lập với reader `100001..200000`. Điều này giúp giảm việc xử lý lại **khi công việc thực sự có thể chia nhỏ**.

### Bảng tình huống lỗi

| Sự cố | Remote step | Remote partitioning |
|---|---|---|
| Worker chết trước khi bắt đầu | Kiểm tra trạng thái một step, delivery/timeout trước khi redeliver | Xác định request/partition chưa xử lý và consumer khác có thể nhận |
| Worker chết giữa chunk | Khôi phục từ checkpoint của step nếu reader restartable | Khôi phục checkpoint của partition đó |
| Manager chết | Worker có thể vẫn chạy; cần chống hai manager cùng điều phối | Nhiều partition có thể đang chạy; đối soát tất cả execution trước restart |
| Broker redeliver request | Nguy cơ chạy trùng logical step | Nguy cơ hai worker cùng nhận một partition |
| Worker commit dữ liệu nhưng ACK/reply mất | Metadata có thể đã hoàn tất dù manager chưa thấy | Metadata partition có thể hoàn tất dù aggregation thiếu reply |
| Một đơn vị công việc quá chậm | Step logic duy nhất là bottleneck nếu nội bộ tuần tự | Partition chậm nhất chi phối thời gian kết thúc |
| Thay đổi input khi restart | Checkpoint có thể mất ý nghĩa | Range/manifest/cutoff của các partition có thể không còn đúng |

### Các bất biến cần giữ trong cả hai mô hình

- Restart dùng **cùng identifying `JobParameters`** cho `JobInstance` bị lỗi; tạo `run.id` mới có thể biến thành job instance khác.
- Không để hai worker cùng gây side effect cho cùng một execution khi request bị redeliver hoặc có tình huống split-brain.
- Dùng checkpoint `ItemStream` với tên ổn định; không dựa vào field singleton trong RAM để phục hồi khi JVM chết.
- Nguồn dữ liệu/snapshot/cutoff phải phù hợp để đọc lại mà không bỏ sót hoặc thay đổi thứ tự.
- Dùng idempotency key, unique constraint, upsert hoặc transactional outbox khi có side effect ngoài một transaction chung.
- Retry có giới hạn và backoff; tránh worker đồng loạt retry khi DB/API đang quá tải.

**Không hứa exactly-once chỉ vì Spring Batch có `JobRepository`.** Broker acknowledgment, metadata DB, database nghiệp vụ và API ngoài thường không nằm trong một giao dịch nguyên tử. Hệ thống cần thiết kế khả năng thực hiện lại an toàn.

## 9. Thread safety: một step ở xa không tự an toàn hơn

Với remote step, worker vẫn chạy reader/processor/writer theo lifecycle Spring Batch. Nếu worker dùng singleton có mutable state chia sẻ giữa nhiều execution hoặc thread, vẫn có nguy cơ race.

Với partitioning, mỗi `StepExecution` có context riêng; bean `@StepScope` có thể tạo reader target theo partition. Nhưng singleton processor/writer hoặc connection client được nhiều partition dùng chung phải được kiểm tra contract thread safety.

| Component | Rủi ro | Thiết kế đề xuất |
|---|---|---|
| `JdbcCursorItemReader`, `FlatFileItemReader` | Cursor, read position mutable | Một instance theo `StepExecution`, `@StepScope` trong partitioning |
| `ItemProcessor` có `currentItem` field | Field bị thread khác ghi đè | Processor stateless, local variable hoặc bean scope phù hợp |
| Writer có buffer `ArrayList` mutable | Ghi/clear đồng thời, mất dữ liệu | Writer stateless hoặc buffer tách riêng theo execution, có transaction rõ |
| `JobRepository` / connection pool | Lock, connection pending khi nhiều step commit | Pool chia sẻ đã được thiết kế concurrency, đo bottleneck metadata |
| JMS session / RabbitMQ channel raw | Không an toàn nếu tùy tiện chia sẻ giữa thread | Dùng adapter/client theo contract và giới hạn consumer concurrency |
| Singleton counter | Một JVM có thể đếm thiếu; nhiều JVM không chia state | Đếm bằng `StepExecution`/metrics, tổng hợp theo execution |

Mục tiêu là **chia đúng dữ liệu và quản lý state**, không phải “thêm càng nhiều thread càng tốt”. Remote step cho phép tách tài nguyên của một step; partitioning cho phép cô lập và song song các đơn vị dữ liệu, nhưng cả hai vẫn phụ thuộc DB, broker, mạng và quota downstream.

## 10. Sizing: số partition, số pod và throughput

Giả sử có `P=48` partition, `N=6` worker pod, mỗi pod xử lý tối đa `L=2` partition đồng thời. Số partition active tối đa theo scheduling:

\[
C_{\mathrm{partition}} \le \min(P, N \times L) = \min(48,12)=12
\]

Nếu mỗi pod chỉ được phép xử lý **một** execution tại một thời điểm để tránh chia sẻ một instance `Step` không được thiết kế an toàn cho concurrency, trần thực tế có thể chỉ là `6`. Tăng số partition không tự tạo pod và không bảo đảm tăng throughput khi DB đã bão hòa.

Với một remote step đơn lẻ, worker count lớn **không làm một step thành nhiều execution**. Có nhiều worker service đang chờ request chỉ giúp dự phòng hoặc phân phối **nhiều job/step độc lập**; nó không biến một lần chạy thành 12 task.

### Mô hình thời gian đơn giản

Với một step xử lý toàn bộ dataset tuần tự:

\[
T_{\mathrm{remoteStep}} \approx T_{\mathrm{dispatch}} +
T_{\mathrm{workerStep}} + T_{\mathrm{completion}}
\]

Với partitioning có `P` phần việc và tối đa `C` phần chạy đồng thời:

\[
T_{\mathrm{partition}} \gtrsim
T_{\mathrm{planning}} +
\max\left(
\frac{\sum_{i=1}^{P}T_i}{C},\;
\max_i T_i
\right)
\]

Hai công thức mang tính **ước lượng minh họa**: worker startup, network, DB contention, queue wait, skew và aggregation có thể làm thời gian thực tăng hơn. Không sử dụng chúng để dự báo SLA mà không có benchmark.

Ví dụ minh họa (không phải kết quả đo của một sản phẩm):

| Mô hình | Thời gian xử lý ước lượng | Điều kiện |
|---|---:|---|
| Local step tuần tự | 90 phút | Dữ liệu được quét tuần tự trên một worker |
| Remote step đơn | 91 phút | Worker tương đương, cộng dispatch/polling overhead |
| Remote step trên node mạnh hơn | 50 phút | Chỉ giảm nhờ tài nguyên/thuật toán của node |
| 12 partition đồng thời | 16 phút | Input chia đều, DB/I/O còn dư, overhead đủ nhỏ |
| 24 partition với DB bão hòa | 20 phút | Tranh chấp DB tăng, throughput giảm so với 12 |

### Ngân sách connection toàn cụm

Nếu mỗi worker pod có JDBC pool tối đa `M` connection, toàn cụm có `N` pod, thì sức chứa tối đa có thể mở từ worker vào DB xấp xỉ `N × M`, chưa kể manager, metadata DB và các dịch vụ khác. Hãy theo dõi `active`, `idle`, `pending`, SQL latency và lock wait. Không đồng nhất **pool max** với số connection active, và không tăng pod chỉ vì CPU worker thấp.

## 11. Observability theo đúng loại đơn vị công việc

| Câu hỏi | Với remote step | Với partitioning |
|---|---|---|
| Đơn vị theo dõi chính | Logical remote step / worker execution | Mỗi partition `StepExecution` cùng manager step |
| Log correlation | `jobExecutionId`, `stepExecutionId`, worker instance, remote step name | Thêm `partitionName`, range/file/tenant và consumer |
| Điểm nghẽn thường thấy | Một worker step chậm, node chưa đủ tài nguyên, dispatch/polling | Partition skew, queue wait, quá nhiều connection, aggregation |
| Kiểm tra đầu ra | Số item và side effect của step | Tổng hợp theo partition và đối soát hợp/không giao nhau |
| Cảnh báo | Step timeout, worker mất heartbeat hoặc metadata không đổi | Partition lâu bất thường, thiếu worker, DLQ, retry/rollback |

### Runbook: manager chờ quá lâu

1. Xác định chính xác mô hình: đang chờ **một remote step** hay **N worker partition executions**?
2. Từ `jobExecutionId` truy `JobRepository`, tìm status/timestamp của các `StepExecution` liên quan.
3. Kiểm tra request queue: message pending/unacked, redelivery, DLQ và số consumer đang hoạt động.
4. Đối chiếu worker log, `stepExecutionId` và checkpoint gần nhất; đừng dispatch lại nếu worker cũ có thể còn chạy.
5. Nếu remote step đơn, kiểm tra việc polling và timeout có phù hợp với thời gian step không. Nếu partitioning, xem **partition chậm nhất** và độ lệch số item giữa các partition.
6. Đo DB connection wait, SQL lock, broker latency, CPU/GC trước khi quyết định tăng worker.
7. Khi restart, giữ identifying parameters và snapshot; sau đó đối soát **khóa nghiệp vụ**, không chỉ tổng số item.

## 12. Decision tree: chọn kiến trúc nào?

~~~mermaid
flowchart TD
    Start[Bài toán cần scale hoặc tách step] --> D{Cần đưa step<br/>sang process/máy khác?}
    D -->|Không| P{Dữ liệu chia<br/>thành phần độc lập?}
    P -->|Có| LP[Local partitioning]
    P -->|Không| SE[Step thường hoặc multi-threaded step có kiểm soát]
    D -->|Có| R{Chỉ cần di chuyển<br/>một step logic?}
    R -->|Có| RS[Remote step<br/>Spring Batch 6.x]
    R -->|Không| C{Worker tự đọc<br/>được vùng dữ liệu?}
    C -->|Có| RP[Remote partitioning]
    C -->|Không| RC[Cân nhắc remote chunking<br/>manager đọc và gửi chunk]
~~~

Decision tree là **gợi ý đầu tiên**, không thay thế benchmark. Một số điểm giúp quyết định:

- **Remote step** hợp lý cho step có yêu cầu placement, dependency hoặc isolation đặc biệt, và nhu cầu chia dữ liệu không rõ ràng.
- **Local partitioning** hợp lý nếu một máy còn đủ tài nguyên; ít network/broker phức tạp hơn.
- **Remote partitioning** hợp lý nếu dataset có partition plan tự nhiên, worker tự đọc/ghi vùng riêng và cần scale ngang.
- **Remote chunking** hợp lý nếu manager cần giữ trách nhiệm đọc rồi phân phối các chunk, thay vì worker tự chọn vùng dữ liệu. Cần tính bottleneck reader và chi phí message payload.
- **Parallel steps/flows** hợp lý khi có nhiều **bước khác nhau** độc lập, không phải nhiều partition của một bước.
- **Multi-threaded step** chỉ phù hợp khi reader/processor/writer và checkpoint chịu được concurrency trong cùng `StepExecution`. `@StepScope` không tự giải quyết concurrency đó.

**Không nên chọn cơ chế phân tán khi nút thắt nằm ở DB hoặc API bị quota**. Tối ưu SQL/index, contention, transaction duration, pool và rate limit có thể quan trọng hơn việc bổ sung manager/worker.

## 13. Vận hành khi triển khai manager/worker riêng

### Một topology thường gặp

~~~text
Kubernetes Job: manager
  - JobLauncher, job flow, RemoteStep hoặc partition manager step
  - JobRepository access
  - Request publisher, cơ chế theo dõi kết quả

Kubernetes Deployment: worker
  - StepExecutionRequestHandler / remote worker configuration
  - Worker Step, reader/processor/writer
  - JobRepository và business data access
  - Consumer concurrency và graceful shutdown

Hạ tầng chung:
  - Broker request queue (và reply queue khi cơ chế cần)
  - Metadata database cho JobRepository
  - Business DB/object storage
  - Logging, metrics, secrets, network policies
~~~

Với worker service, tránh để Spring Boot tự chạy toàn bộ job ngay khi startup nếu nó chỉ có trách nhiệm nhận remote request; có thể cấu hình `spring.batch.job.enabled=false` nếu dùng Spring Boot auto-launch. Điều này **không thay thế** việc wiring inbound adapter và worker step thật.

### Các lỗi deployment cần thử

- Manager Job restart trong lúc worker cũ vẫn chạy.
- Pod worker bị `SIGTERM` rồi `SIGKILL` giữa chunk; cấu hình grace period và drain listener.
- Broker tạm mất kết nối và redeliver message.
- Rolling update manager/worker có version không tương thích.
- Worker thiếu quyền truy cập metadata DB hoặc snapshot/object storage.
- Nhiều job đồng thời gửi request vào queue chung, cần đúng correlation và giới hạn concurrency.

Một Kubernetes `backoffLimit` hoặc CronJob `concurrencyPolicy` chỉ giải quyết một phần vấn đề orchestration. Nó **không tự bảo đảm** semantics của `JobInstance`, không giải quyết idempotency của writer và không thay thế cơ chế chống hai manager cùng điều phối một execution.

## 14. Checklist thiết kế trước production

- [ ] Đã xác định mục tiêu chính là **dịch chuyển step** hay **chia dữ liệu để chạy song song**.
- [ ] Đã chọn API theo Spring Batch 5.x/6.x; không gọi `RemoteStep` 6.x trong project 5.x.
- [ ] Nếu partitioning, có partition plan không overlap, đủ coverage và ổn định khi restart.
- [ ] Nếu remote step, không kỳ vọng một request tạo N partition tự động.
- [ ] Manager/worker dùng `JobRepository` và metadata schema tương thích.
- [ ] `StepExecutionRequest`, tên worker step và transport/serializer tương thích.
- [ ] Message delivery, ACK/redelivery, reply/polling và timeout được thiết kế rõ.
- [ ] Reader stateful có scope/lifecycle `ItemStream` đúng; singleton mutable state được loại bỏ hoặc cô lập.
- [ ] Writer/side effect idempotent, kể cả sau crash/retry/duplicate request.
- [ ] Pool, CPU/RAM, IOPS, quota downstream và số worker được giới hạn theo ngân sách.
- [ ] Có log/metric/trace theo execution; với partitioning, có thêm ID/range/file từng partition.
- [ ] Đã thử worker crash, lost reply, manager restart và nâng cấp worker giữa job.
- [ ] Đã đối soát số lượng **và tập khóa nghiệp vụ** sau khi phục hồi.

## 15. Bài tập thực hành

### Bài 1 — Phân loại kiến trúc

Với bốn yêu cầu, chọn một kiến trúc và giải thích: (a) render báo cáo tại service có thư viện native; (b) xử lý 12 triệu row theo range ID; (c) 200 tệp độc lập trên object storage; (d) một API downstream chỉ cho 100 request/giây. Nêu ít nhất một rủi ro và một metric nên đo cho mỗi lựa chọn.

### Bài 2 — Tính trần concurrency

Manager tạo 36 partition, có 5 worker pod, mỗi pod tối đa 2 execution đồng thời. Tính trần số partition active, số partition có thể phải chờ và so sánh với một remote step đơn. Điều gì xảy ra nếu chỉ có một singleton `Step` không an toàn khi nhiều execution dùng cùng lúc?

### Bài 3 — Thiết kế restart

Một remote step đã ghi dữ liệu nhưng manager timeout. Ở bài toán khác, 2 trong 24 partition `FAILED`, 22 partition `COMPLETED`. Viết hai runbook khác nhau, chỉ rõ metadata cần kiểm tra trước khi re-dispatch và điều kiện giữ nguyên `JobInstance`.

### Bài 4 — Tìm partition skew

Giả sử bốn khoảng ID bằng nhau nhưng số record lần lượt là 1 triệu, 1 triệu, 1 triệu và 9 triệu. Vì sao thời gian của job vẫn bị khoảng cuối chi phối? Thiết kế lại partition bằng manifest hoặc histogram sao cho tải đồng đều mà ranh giới vẫn ổn định qua restart.

### Bài 5 — Benchmark có kiểm soát

Giữ nguyên snapshot. Đo thời gian chạy với một local step, một remote step trên cùng loại máy, local partitioning và remote partitioning tại ba mức worker. Thu `readCount`/`writeCount`, DB pool wait, CPU, queue age, partition duration và kết quả nghiệp vụ. Giải thích khi nào overhead của phân tán lớn hơn lợi ích.

### Câu hỏi tự kiểm tra

1. Tại sao remote step không đương nhiên là remote partitioning?
2. Khi nào một remote step có thể hữu ích dù không tăng tốc độ xử lý dữ liệu?
3. `Partitioner` tạo ra giá trị gì, và vì sao worker count không quyết định `ExecutionContext` của một partition?
4. Vì sao manager timeout không chứng minh worker chưa commit?
5. Điều gì thay đổi khi remote partitioning có 48 worker `StepExecution` thay vì một remote step logic?
6. Vì sao `@StepScope` cô lập state giữa partition nhưng chưa đủ cho multi-threaded step cùng một `StepExecution`?
7. Nếu database đã hết connection, lựa chọn thêm worker có thể gây hậu quả gì?

## 16. Tổng kết

**Remote step** và **partitioning** trả lời hai câu hỏi khác nhau: **“bước này nên chạy ở đâu?”** và **“bước này có thể chia thành bao nhiêu phần độc lập?”**. Remote step trong Spring Batch 6.x cho phép chuyển execution sang một worker process; partitioning chia dữ liệu thành các worker `StepExecution`, chạy trong một JVM hoặc qua middleware tới nhiều worker.

Chọn mô hình đúng cần xem **hình dạng dữ liệu, dependency của step, khả năng restart, thread safety, nguồn tài nguyên thật sự đang nghẽn và chi phí vận hành phân tán**. Dù chọn mô hình nào, `JobRepository` nhất quán, input/cutoff ổn định, idempotency và khả năng quan sát tới từng execution mới là nền tảng cho một job Spring Batch mở rộng an toàn.
