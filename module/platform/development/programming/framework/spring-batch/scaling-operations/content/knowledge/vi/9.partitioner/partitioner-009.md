# PartitionNameProvider khi restart trong Spring Batch

Giả sử một job xử lý 80 triệu giao dịch, đầu vào được tách thành hàng nghìn file hoặc khoảng ID. Để tạo các partition lần đầu, hệ thống phải quét manifest, đọc metadata nguồn, cân bằng kích thước shard và gắn `ExecutionContext` cho từng worker. Việc phân hoạch có thể mất vài phút. Sau khi 998 trong 1.000 partition đã hoàn tất, chỉ còn hai partition bị lỗi, liệu lần restart có cần **phân hoạch lại toàn bộ dữ liệu**?

Trong Spring Batch, `PartitionNameProvider` giải quyết đúng vấn đề hiệu năng này: khi `Partitioner` đồng thời triển khai interface tùy chọn đó, cơ chế splitter có thể **chỉ yêu cầu tên các partition khi restart**, sử dụng thông tin partition đã lưu từ lần chạy trước trong `JobRepository` thay vì gọi lại logic phân hoạch tốn kém. Việc tối ưu chỉ an toàn nếu **tên partition ổn định và khớp chính xác với lần chạy ban đầu**.

Bài học nằm trong chương **Partitioner** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module nghiên cứu mở rộng Spring Batch bằng multi-threaded step, parallel steps, partitioning và mô hình phân tán trên workload dữ liệu lớn, đồng thời đo nút thắt, bảo đảm thread safety, retry/restart và vận hành theo tài nguyên thực tế. Trọng tâm của bài này là hợp đồng tên partition, cơ chế restart, thiết kế manifest bất biến, ví dụ Java và các tình huống cần kiểm thử.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Nêu đúng lý do xuất hiện `PartitionNameProvider` và phân biệt với `Partitioner`.
2. Giải thích đường đi từ `PartitionStep` đến `SimpleStepExecutionSplitter` và `JobRepository` ở lần chạy đầu và lần restart.
3. Triển khai interface `PartitionNameProvider#getPartitionNames(int)` trong Spring Batch 5.2.x.
4. Thiết kế tên partition ổn định khi nguồn file/range thay đổi thứ tự, khi đổi số worker hoặc khi restart.
5. Nhận diện giới hạn: interface **không** tạo checkpoint mới, không tự chống ghi trùng và không chữa mất metadata.
6. Tạo cơ chế lưu manifest/partition plan bất biến để đọc **tên nhanh** nhưng vẫn giữ context cũ.
7. Kiểm thử rằng khi chỉ một partition lỗi, job không tái phân hoạch tốn kém và không chạy lại phần đã hoàn tất.
8. Phân biệt tối ưu restart với scaling, chunk size, `gridSize` và execution concurrency.

## 2. Nhắc lại cơ chế Partitioning Step

Spring Batch partitioning có **manager step** điều phối một tập **worker StepExecution**. Một `Partitioner` tạo bảng ánh xạ:

~~~java
Map<String, ExecutionContext> partition(int gridSize);
~~~

Ví dụ với ba file:

~~~text
"file-001" -> { inputUri: "s3://batch/snapshots/v42/001.csv" }
"file-002" -> { inputUri: "s3://batch/snapshots/v42/002.csv" }
"file-003" -> { inputUri: "s3://batch/snapshots/v42/003.csv" }
~~~

Tên `file-001`, `file-002`, `file-003` là **partition key**. Framework kết hợp tên worker step với key thành tên `StepExecution`, ví dụ:

~~~text
invoiceWorker:file-001
invoiceWorker:file-002
invoiceWorker:file-003
~~~

`ExecutionContext` của từng partition chứa tham số worker cần để biết file hoặc range nào phải xử lý. Với reader `@StepScope`, worker StepExecution có thể nạp tham số này qua late binding.

~~~mermaid
flowchart LR
    J["JobExecution"] --> M["Manager PartitionStep"]
    M --> S["StepExecutionSplitter"]
    S --> P["Partitioner"]
    P --> C["Map: tên -> ExecutionContext"]
    S --> R[("JobRepository")]
    S --> H["PartitionHandler"]
    H --> W1["worker:file-001"]
    H --> W2["worker:file-002"]
    H --> W3["worker:file-003"]
    W1 --> R
    W2 --> R
    W3 --> R
~~~

**Khác multi-threaded step:** partitioning tạo `StepExecution` và `ExecutionContext` **riêng theo từng partition**. Đây là cơ sở để framework biết partition nào đã `COMPLETED` và partition nào cần chạy lại khi restart.

## 3. Vấn đề: partition() có thể rất tốn kém

Một `Partitioner.partition(gridSize)` đơn giản có thể chỉ chia một khoảng ID cố định. Nhưng trong hệ thống thực, phân hoạch có thể bao gồm:

- Quét hàng chục nghìn object trong object storage và lấy checksum/kích thước.
- Đọc snapshot manifest, tính histogram phân bố theo khóa hoặc cỡ bản ghi.
- Truy vấn `COUNT`, `MIN`, `MAX` theo shard trong một bảng rất lớn.
- Tạo range cân bằng dựa trên chi phí xử lý ước tính, không chỉ số lượng ID.
- Ghi hoặc khóa một partition plan trong metadata nghiệp vụ.
- Kiểm tra tính đủ/không trùng của input trước khi chạy.

Lần chạy đầu **cần** tính được `ExecutionContext` cho từng worker. Nhưng sau khi job đã tạo các worker StepExecution và lưu metadata, việc chạy lại cùng logic phân hoạch có thể thừa hoặc nguy hiểm: input listing có thể thay đổi thứ tự và thuật toán có thể tạo key khác.

### 3.1. Không có PartitionNameProvider

Trong cách partitioner thông thường, ở quá trình split/restart, framework có thể gọi lại `partition(gridSize)` để có các partition key. Sau đó splitter dùng lịch sử StepExecution để chọn các phần cần phục hồi.

~~~text
Lần đầu:
  partition(gridSize) -> map tên/context -> tạo StepExecution

Lần restart:
  partition(gridSize) -> tính lại map tên/context
                    -> đối chiếu StepExecution cũ theo tên
                    -> chọn partition chưa hoàn tất
~~~

Việc gọi lại `partition` không nhất thiết gây xử lý lại mọi partition, vì splitter vẫn dùng metadata. Nhưng **chi phí khám phá/sắp xếp/phân hoạch đầu vào** có thể phát sinh lần nữa.

### 3.2. Có PartitionNameProvider

Với implementation tùy chọn:

~~~java
public interface PartitionNameProvider {
    Collection<String> getPartitionNames(int gridSize);
}
~~~

Ở Spring Batch 5.2.x, interface nằm trong package `org.springframework.batch.core.partition.support`. Nếu partitioner triển khai interface này, **khi restart framework dùng `getPartitionNames(...)` thay cho `partition(...)`** và khớp tên với partition của lần chạy trước trong repository. <https://docs.spring.io/spring-batch/reference/5.2/scalability.html>

~~~text
Lần đầu:
  partition(gridSize) -> map tên/context đầy đủ -> lưu metadata

Lần restart:
  getPartitionNames(gridSize) -> collection tên
                              -> đối chiếu metadata cũ
                              -> khôi phục context đã lưu
                              -> chỉ thực thi partition cần restart
~~~

**Đây là tối ưu việc lấy tên**, không phải cơ chế ghi `ExecutionContext` mới. Các context ban đầu được giữ trong `JobRepository`; nếu metadata tương ứng bị mất hoặc đã bị thay sai, `getPartitionNames` không thể tự khôi phục chúng từ một danh sách chuỗi.

### 3.3. So sánh ngắn

| Nội dung | Chỉ triển khai `Partitioner` | Triển khai thêm `PartitionNameProvider` |
| --- | --- | --- |
| Lần chạy đầu | Gọi `partition(gridSize)` | Vẫn gọi `partition(gridSize)` |
| Khi restart với metadata hợp lệ | Có thể cần chạy lại `partition(...)` | Dùng `getPartitionNames(...)`, không tái tạo map context |
| Dữ liệu trả về ở bước tính partition | `Map<String, ExecutionContext>` | Khi restart chỉ cần `Collection<String>` |
| Tối ưu gì? | Chưa tách chi phí phân hoạch | Bỏ chi phí phân hoạch lại tốn kém |
| Có bắt buộc để restart? | Không | Không; interface tùy chọn |
| Có tự bảo đảm idempotency? | Không | Không |
| Điều kiện cốt lõi | Tên và phạm vi ổn định | **Tên getPartitionNames phải khớp key của partition ban đầu** |

Lưu ý: các mô tả trên áp dụng cho cơ chế partitioning tiêu chuẩn dùng `SimpleStepExecutionSplitter` của Spring Batch 5.2.x. Nếu ứng dụng triển khai `StepExecutionSplitter` tùy biến, cần kiểm tra hợp đồng restart của chính implementation đó.

## 4. Cơ chế restart qua JobRepository

Giả sử job `dailyInvoiceJob` đang xử lý snapshot `v42`:

| Partition | Lần chạy #510 | Khi restart #511 |
| --- | --- | --- |
| `invoiceWorker:file-001` | `COMPLETED` | Không chạy lại theo mặc định |
| `invoiceWorker:file-002` | `COMPLETED` | Không chạy lại theo mặc định |
| `invoiceWorker:file-003` | `FAILED` | Chạy lại, có thể resume từ checkpoint |
| `invoiceWorker:file-004` | `COMPLETED` | Không chạy lại theo mặc định |

Spring Batch ghi `StepExecution` cùng `ExecutionContext` của từng partition qua `JobRepository`. Khi restart **cùng JobInstance**, splitter sử dụng tên để tìm các StepExecution lịch sử và quyết định cái nào cần chạy lại.

~~~mermaid
sequenceDiagram
    participant O as JobOperator
    participant M as PartitionStep
    participant N as PartitionNameProvider
    participant R as JobRepository
    participant W as Worker
    O->>M: Restart cùng JobInstance
    M->>N: getPartitionNames(gridSize)
    N-->>M: [file-001, file-002, file-003, file-004]
    M->>R: Tra cứu StepExecution theo tên
    R-->>M: COMPLETED, COMPLETED, FAILED, COMPLETED
    M->>R: Lấy ExecutionContext đã lưu của file-003
    M->>W: Thực thi lại invoiceWorker:file-003
    W->>R: Commit/checkpoint/status mới
    Note over M,W: Các partition COMPLETED được giữ kết quả
~~~

Sơ đồ là luồng logic, không khẳng định chính xác thứ tự từng lời gọi nội bộ của framework.

### 4.1. Hai tầng phục hồi cần phân biệt

**Tầng partition:** `StepExecutionSplitter` xác định partition nào cần thực thi lại dựa trên tên và trạng thái trước đó.

**Tầng chunk:** reader/writer của worker partition khôi phục `ExecutionContext`/checkpoint của các chunk đã commit. Một partition lỗi ở item 8.001 có thể chỉ cần xử lý phần còn lại, không nhất thiết toàn bộ file.

`PartitionNameProvider` **chỉ tham gia việc lấy danh sách tên**. Nó không thay cho `ItemStream.open/update/close`, transaction manager, checkpoint, error handling, logic retry hay reconciliation.

### 4.2. Metadata nào phải còn?

Để restart đúng, cần giữ:

- `JobInstance` cùng identifying `JobParameters`.
- Lịch sử `JobExecution` của instance đó.
- `StepExecution` của manager và từng partition, với tên không đổi.
- `BATCH_STEP_EXECUTION_CONTEXT` hoặc kho context tương đương, chứa checkpoint/partition parameters.
- Tình trạng thực tế của các worker (đặc biệt khi remote partitioning và có worker cũ chưa dừng).

Không xóa metadata JobRepository để “chạy lại cho sạch” nếu mục tiêu là **restart từ điểm lỗi**. Nếu metadata mất, phải phục hồi backup hoặc thực hiện quy trình **reprocess có đối soát**, không tạo một danh sách tên giả rồi tin rằng checkpoint cũ còn tồn tại.

## 5. Hợp đồng bất biến của tên partition

Spring Batch 5.2 Javadoc yêu cầu tên do `PartitionNameProvider` trả về phải **khớp các key do `Partitioner` cung cấp**. Không chỉ “gần giống” hoặc “cùng số partition”, mà phải khớp định danh logic cho cùng JobInstance.

Ví dụ đúng:

~~~text
partition(12).keySet():
    range-0001
    range-0002
    range-0003

getPartitionNames(12):
    range-0001
    range-0002
    range-0003
~~~

Ví dụ sai:

~~~text
Lần đầu:
    partition0 -> file A
    partition1 -> file B
    partition2 -> file C

Restart sau khi danh sách file đổi thứ tự:
    partition0 -> file C
    partition1 -> file A
    partition2 -> file B
~~~

Dù vẫn có ba key `partition0`, ánh xạ tên tới file đã thay đổi. Nếu code hoặc manifest sử dụng mapping mới thay vì context được lưu, một partition đã hoàn tất có thể được gắn với file sai. Ngay cả khi Spring Batch khôi phục context cũ, việc thiết kế tên theo thứ tự ngẫu nhiên vẫn là dấu hiệu của partition plan không bền vững và gây rủi ro ở các luồng reprocess khác.

### 5.1. Tên tốt nên có tính chất nào?

1. **Deterministic:** cùng partition plan thì cùng tên, không phụ thuộc thời gian hiện tại hoặc thứ tự listing không bảo đảm.
2. **Unique:** không có hai shard khác nhau dùng chung một key.
3. **Stable across restart:** thay đổi số pod, thread pool hoặc máy chạy không làm đổi key.
4. **Recoverable:** sau JVM crash vẫn lấy được danh sách tên từ một nguồn bền vững.
5. **Meaningful:** đủ để chẩn đoán, ví dụ `file-0042` hoặc `tenant-018`; không nhất thiết chứa cả đường dẫn dài.
6. **Scoped by JobInstance:** tên có thể dùng lại ở JobInstance khác, nhưng plan phải gắn với identifying parameters/snapshot tương ứng.

**Tên partition ổn định là điều kiện cần, chưa đủ.** Phạm vi dữ liệu, snapshot version, checksum và quy tắc xử lý cũng phải giữ nhất quán qua restart.

### 5.2. Những cách đặt tên dễ lỗi

| Cách đặt tên | Rủi ro | Phương án tốt hơn |
| --- | --- | --- |
| `UUID.randomUUID()` mỗi lần | Không khớp tên lần đầu | Tên sinh một lần, ghi vào manifest bền vững |
| Chỉ số từ `File.listFiles()` chưa sort | File order có thể thay đổi | File ID hoặc manifest index cố định |
| `hash(key) % currentWorkerCount` | Đổi số workers làm đổi mapping | Cố định shard count/algorithm theo snapshot |
| Dùng timestamp chạy lại | Restart tạo tên khác | Lấy snapshot ID của JobInstance |
| Chỉ số range tính từ `MAX(id)` mới | Vùng chia đổi khi DB có dữ liệu mới | Phân hoạch từ snapshot/cutoff bất biến |
| Đổi worker step name | Tên StepExecution đầy đủ thay đổi | Giữ version tương thích hoặc migration có kiểm soát |
| Trả danh sách chỉ gồm partition `FAILED` | Có thể không đúng hợp đồng danh tính của splitter | Trả **toàn bộ tên của plan gốc**, để framework chọn cái cần chạy |

`getPartitionNames` không có nhiệm vụ tự quyết định “partition nào FAILED”. Nó phải cung cấp **tên của partition plan**, còn splitter dùng repository để quyết định phần được thực thi.

## 6. Thiết kế manifest bất biến để lấy tên nhanh

Giải pháp dễ duy trì là **lưu partition plan ngay từ lúc chuẩn bị job**. Ví dụ có snapshot `2026-11-25-v42` và bảng manifest:

| snapshot_id | partition_key | input_uri | checksum | item_count |
| --- | --- | --- | --- | ---: |
| `v42` | `file-001` | `s3://batch/v42/a.csv` | `sha256:...` | 100.000 |
| `v42` | `file-002` | `s3://batch/v42/b.csv` | `sha256:...` | 80.000 |
| `v42` | `file-003` | `s3://batch/v42/c.csv` | `sha256:...` | 125.000 |

**Luồng lần đầu:**

1. Hoàn thành manifest cho đúng snapshot/cutoff trước khi job chạy; chốt version immutable.
2. `partition(gridSize)` đọc thông tin shard đầy đủ từ manifest và xây `Map<partitionKey, ExecutionContext>`.
3. Splitter tạo `StepExecution` và lưu context trong JobRepository.
4. Worker dùng URI/checksum/limits từ context để đọc đúng shard.

**Luồng restart:**

1. `getPartitionNames(gridSize)` đọc **chỉ cột `partition_key`** của manifest đã chốt, có thể bằng một index scan ngắn hoặc cache bền vững.
2. Splitter dùng tên để khớp các StepExecution đã lưu.
3. Worker lỗi dùng **context lịch sử** từ JobRepository, không cần gọi lại thuật toán cân bằng tải.

Một table/manifest source có thể được cache, nhưng **bộ nhớ JVM đơn thuần không bền vững qua crash**. Nếu cache hết hạn khi restart, phải có cách lấy lại danh sách từ durable storage. Cần kiểm soát phiên bản manifest sao cho cùng `snapshotId` không trả về một tập shard khác.

### 6.1. Chi phí tính toán

Giả sử lần đầu phải quét 10 triệu record metadata để chia thành 1.000 partition. Chi phí gần đúng:

\[
T_{\mathrm{initial}}
= T_{\mathrm{discover}}+T_{\mathrm{plan}}+T_{\mathrm{persist}}
\]

Khi restart với `PartitionNameProvider`:

\[
T_{\mathrm{restart\ naming}}
\approx T_{\mathrm{list\ 1000\ names}}
\]

Không có nghĩa `getPartitionNames` là `O(1)`: nó vẫn phải trả về một tên cho mỗi partition. Lợi ích là bỏ qua quét/đếm/chia lại input nặng, còn lookup `JobRepository` và phục hồi worker vẫn mất thời gian.

### 6.2. Không dùng nguồn động để tạo tên trên restart

Nếu `getPartitionNames` lại quét bucket, tìm tất cả file đang có và sắp xếp theo kích thước, nó có thể tốn gần bằng `partition` và trả thêm/xóa tên ngoài plan gốc. Tối ưu thật cần **metadata nhẹ, có version, ổn định**, không chỉ đổi tên phương thức.

Nếu manifest bị xóa hoặc checksum không khớp, nên **fail closed** và yêu cầu xử lý vận hành. Sinh lại một plan mới một cách âm thầm có thể khiến worker đọc sai dữ liệu nhưng JobExecution vẫn báo thành công.

## 7. Ví dụ Java: Partitioner kiêm PartitionNameProvider

Ví dụ dưới đây dùng package của **Spring Batch 5.2.x** và Java 17+. Chúng ta viết một partitioner dựa trên manifest bền vững. Interface `PartitionPlanStore` là thành phần lưu trữ nghiệp vụ cần triển khai bằng PostgreSQL, object-storage index hoặc giải pháp tương đương. Ví dụ tách phần đọc **đủ context** và phần đọc **chỉ tên** để thấy rõ lợi ích tối ưu.

### 7.1. Định nghĩa partition plan

~~~java
import java.util.List;

public record ShardSpec(
        String partitionKey,
        String inputUri,
        String checksum,
        long itemCount) {
}

public interface PartitionPlanStore {

    // Truy vấn đầy đủ chỉ dùng khi tạo partition ban đầu.
    List<ShardSpec> loadShardSpecs(String snapshotId);

    // Truy vấn nhẹ, chỉ lấy các key đã persist, dùng khi restart.
    List<String> loadPartitionKeys(String snapshotId);
}
~~~

Cả hai phương thức phải đọc **cùng một snapshot manifest bất biến**; không tự sinh shard từ dữ liệu sống ở lần gọi sau. Nếu snapshot không tồn tại, store nên ném lỗi rõ ràng thay vì trả về danh sách rỗng và cho job “thành công” giả.

### 7.2. Triển khai hai interface

~~~java
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.partition.support.PartitionNameProvider;
import org.springframework.batch.item.ExecutionContext;

public class ManifestPartitioner
        implements Partitioner, PartitionNameProvider {

    private final PartitionPlanStore store;
    private final String snapshotId;

    public ManifestPartitioner(
            PartitionPlanStore store, String snapshotId) {
        if (snapshotId == null || snapshotId.isBlank()) {
            throw new IllegalArgumentException("snapshotId required");
        }
        this.store = store;
        this.snapshotId = snapshotId;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        List<ShardSpec> specs = store.loadShardSpecs(snapshotId);
        if (specs.isEmpty()) {
            throw new IllegalStateException(
                    "No shards for snapshot " + snapshotId);
        }

        Map<String, ExecutionContext> result = new LinkedHashMap<>();
        for (ShardSpec spec : specs) {
            String name = spec.partitionKey();
            if (name == null || name.isBlank()) {
                throw new IllegalStateException("Blank partition name");
            }

            ExecutionContext ctx = new ExecutionContext();
            ctx.putString("snapshotId", snapshotId);
            ctx.putString("inputUri", spec.inputUri());
            ctx.putString("checksum", spec.checksum());
            ctx.putLong("itemCount", spec.itemCount());

            if (result.putIfAbsent(name, ctx) != null) {
                throw new IllegalStateException(
                        "Duplicate partition name: " + name);
            }
        }
        return result;
    }

    @Override
    public Collection<String> getPartitionNames(int gridSize) {
        // Phải là TẤT CẢ key của kế hoạch gốc, không chỉ key FAILED.
        List<String> names = store.loadPartitionKeys(snapshotId);
        if (names.isEmpty()) {
            throw new IllegalStateException(
                    "Manifest names missing: " + snapshotId);
        }

        Set<String> unique = new LinkedHashSet<>(names);
        if (unique.size() != names.size()
                || unique.stream().anyMatch(
                        n -> n == null || n.isBlank())) {
            throw new IllegalStateException(
                    "Invalid partition name list for " + snapshotId);
        }
        return List.copyOf(names);
    }
}
~~~

Các điểm đáng chú ý:

- `implements Partitioner, PartitionNameProvider` là **hai hợp đồng khác nhau**. `partition(...)` trả context; `getPartitionNames(...)` chỉ trả tên.
- `gridSize` là hint, không phải căn cứ duy nhất để sinh plan. Trong ví dụ, manifest snapshot đã cố định nên hai phương thức **cố ý bỏ qua** giá trị truyền vào.
- `Map` và `Collection` không chứa key trùng. Kiểm tra này chỉ phát hiện vấn đề nội bộ một lần đọc, chưa đủ chứng minh **tập tên bằng nhau giữa hai lần gọi** khi manifest có thể bị sửa.
- `String snapshotId` là identifying context của kỳ dữ liệu. Phải gắn nó với JobInstance và nguồn lưu manifest bất biến.
- `getPartitionNames` không xây `ExecutionContext` giả mới, không mở từng file và không chạy lại thuật toán split.
- Lời gọi `loadPartitionKeys` vẫn cần chịu được lỗi DB/network và có metric latency; nhanh hơn không có nghĩa không cần timeout.
- Nếu worker sử dụng nhiều context keys hơn (`minId`, `maxId`, `tenantId`...), hãy lưu chúng ở lần `partition(...)` đầu. Không kỳ vọng `getPartitionNames` bổ sung key thiếu khi restart.

### 7.3. Bean wiring với JobParameters

Ví dụ đăng ký partitioner qua `@StepScope` để lấy `snapshotId` của JobInstance:

~~~java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PartitionerConfiguration {

    @Bean
    @StepScope
    public ManifestPartitioner manifestPartitioner(
            PartitionPlanStore store,
            @Value("#{jobParameters['snapshotId']}") String snapshotId) {
        return new ManifestPartitioner(store, snapshotId);
    }
}
~~~

`@StepScope` cho phép bean được khởi tạo khi context của manager step sẵn sàng; không nên thay bằng singleton với `snapshotId` mutable bị ghi lại khi chạy nhiều job song song. Ví dụ này giả định `snapshotId` được cấu hình làm **identifying JobParameter** và manifest của snapshot đó không thay đổi.

Nếu custom infrastructure không cung cấp scope đúng cho partitioner, có thể tạo partitioner theo context khi manager step bắt đầu bằng một factory phù hợp, nhưng phải tránh lưu mutable “current snapshot” ở singleton dùng chung nhiều JobExecution.

### 7.4. Manager step sử dụng partitioner

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskExecutor;

@Bean
public Step invoiceManagerStep(
        JobRepository jobRepository,
        @Qualifier("manifestPartitioner") ManifestPartitioner partitioner,
        @Qualifier("invoiceWorkerStep") Step workerStep,
        @Qualifier("partitionTaskExecutor") TaskExecutor executor) {

    return new StepBuilder("invoiceManagerStep", jobRepository)
            .partitioner("invoiceWorkerStep", partitioner)
            .step(workerStep)
            .gridSize(12)
            .taskExecutor(executor)
            .build();
}
~~~

Đây là snippet Spring Batch 5.2.x cho **local partitioning**. Worker step và executor được định nghĩa riêng, không được trình bày ở đây để giữ trọng tâm tên partition. Tương tự, remote partitioning có thể sử dụng partitioner này và thay handler/transport; cơ chế tên partition trong repository vẫn là nguyên tắc chung.

**Quan trọng:** `gridSize(12)` không giới hạn số worker threads hoặc bắt buộc đúng 12 partition. Số partition đến từ manifest; executor và `PartitionHandler` mới là nơi quyết định concurrency. Khi restart, splitter dùng kích thước/plan lịch sử theo hợp đồng của nó, không nên đổi tên partition chỉ vì số pod hiện tại tăng hoặc giảm.

## 8. Thiết kế reader kiểm tra snapshot

Trong ví dụ trên, worker `ExecutionContext` chứa:

~~~text
snapshotId = v42
inputUri   = s3://batch/v42/a.csv
checksum   = sha256:...
itemCount  = 100000
~~~

Reader có thể dùng `@StepScope` để late-bind `inputUri` và kiểm tra checksum trước khi đọc:

~~~java
@Bean
@StepScope
public FlatFileItemReader<InvoiceRow> invoiceReader(
        @Value("#{stepExecutionContext['inputUri']}") String inputUri,
        @Value("#{stepExecutionContext['checksum']}") String checksum) {

    // Pseudocode phần lưu trữ: resource cần được resolve từ URI
    // bằng adapter phù hợp và xác minh checksum/version trước khi đọc.
    Resource resource = resolveAndVerifyResource(inputUri, checksum);

    return new FlatFileItemReaderBuilder<InvoiceRow>()
            .name("invoiceReader")
            .resource(resource)
            .delimited()
            .names("invoice_id", "amount")
            .fieldSetMapper(this::toInvoiceRow)
            .saveState(true)
            .build();
}
~~~

Các hàm `resolveAndVerifyResource`, `toInvoiceRow` và class `InvoiceRow` do ứng dụng cung cấp; đây là **phác thảo logic**, không phải snippet tự biên dịch độc lập. Điểm cần hiểu: **checksum/snapshot và URI được khôi phục từ context đã lưu**, không lấy từ file listing mới trong lần restart.

Khi worker bị lỗi giữa file, `ItemStream` quản lý checkpoint theo cơ chế Spring Batch. Vị trí đọc có thể phục hồi được nếu dữ liệu không đổi và `ExecutionContext` được ghi đúng với các transaction đã commit.

### 8.1. Stateful readers và tính nhất quán

Với local/remote partitioning, từng partition có `StepExecution` riêng, nên một reader `@StepScope` có thể có state riêng. Điều này **khác** multi-threaded step, nơi nhiều chunk threads có thể chia sẻ cùng một StepExecution và StepScoped bean.

Tuy nhiên, đừng suy rằng reader riêng đồng nghĩa output exactly-once:

- Một chunk có thể rollback rồi được đọc/xử lý lại.
- Worker chết sau khi API đã gửi request nhưng trước khi commit metadata.
- Input file bị sửa giữa hai lần chạy.
- Writer có thể ghi trùng nếu không có khóa idempotency.

Phải dùng transaction, unique business keys và đối soát khi cần.

## 9. Test chính xác hợp đồng tên giữa hai API

Lập test cho một snapshot cố định:

~~~java
@Test
void namesMustEqualPartitionKeys() {
    ManifestPartitioner p =
            new ManifestPartitioner(store, "snapshot-v42");

    Set<String> fromPartition =
            p.partition(12).keySet();

    Set<String> fromNames =
            new LinkedHashSet<>(p.getPartitionNames(12));

    assertEquals(fromPartition, fromNames);
}
~~~

Ví dụ giả định `store` là test fixture bất biến và đã import đúng JUnit/collections. Nên kiểm tra thêm:

- Tất cả key duy nhất, không blank, không chứa ký tự mơ hồ cho log/metric.
- `getPartitionNames` và `partition` không phụ thuộc thứ tự không ổn định.
- Snapshot khác có plan riêng và không bị lấy nhầm.
- Gọi lại `getPartitionNames` sau khởi động JVM mới vẫn trả đúng danh sách.
- `loadPartitionKeys` không chạm vào đường tính toán nặng hoặc quét lại nguồn.
- Cả hai hàm thất bại rõ ràng nếu manifest mất/thay đổi bất hợp pháp.

### 9.1. Test không gọi partition() khi restart

Một bài test quan trọng khác phải chứng minh **hiệu năng và cơ chế thực thi**, không chỉ test hai hàm trong class:

~~~text
Run #1:
    create JobInstance(snapshot=v42)
    partition() được gọi để tạo context ban đầu
    file-001 -> COMPLETED
    file-002 -> FAILED sau một số chunk đã commit
    file-003 -> COMPLETED

Restart cùng JobInstance:
    getPartitionNames() được gọi
    partition() KHÔNG được gọi lại trong đường restart chuẩn
    file-001 / file-003 không thực thi lại
    file-002 tiếp tục từ context/checkpoint hợp lệ
    output cuối giống clean run
~~~

Có thể dùng một `PartitionPlanStore` spy để đo số lần gọi `loadShardSpecs` và `loadPartitionKeys`, kết hợp test job thật với `JobRepository` bền vững. Không cần giả lập việc gọi `SimpleStepExecutionSplitter` ở mọi cấp nếu test end-to-end đã xác minh đúng.

**Điều kiện quan sát:** chỉ khẳng định không gọi lại `partition` khi cùng JobInstance được restart qua cơ chế splitter tiêu chuẩn và metadata còn hợp lệ. Nếu chạy một JobInstance **mới**, phải tạo partition plan ban đầu cho instance đó; đây không phải tình huống restart của instance cũ.

## 10. Tình huống lỗi và kết quả mong đợi

| Tình huống | Rủi ro | Phản ứng đúng |
| --- | --- | --- |
| `getPartitionNames` trả thiếu `file-002` | Partition lỗi bị mất khỏi tập tên cần đối chiếu | Fail/alert vì plan sai; không tuyên bố job đã đủ |
| Trả thêm `file-999` không có context cũ | Tạo danh tính không thuộc plan gốc | Từ chối drift; phục hồi manifest/version |
| Thay tên `file-002` bằng `partition2` | Không khớp StepExecution lịch sử | Giữ tên gốc hoặc migration có đối soát |
| `gridSize` thay từ 12 sang 24 khi restart | Ứng dụng muốn repartition trong khi checkpoint cũ đang tồn tại | Không thay plan của JobInstance; scale số worker độc lập |
| Manifest bị ghi đè | Tên có thể giữ nhưng `inputUri`/checksum sai | Dùng immutable/versioned manifest, xác minh checksum |
| `JobRepository` mất bảng context | Không khôi phục được worker checkpoints | Backup/restore hoặc reprocess có đối soát |
| Worker step được đổi tên | `workerStep:partitionKey` không còn khớp | Giữ tên tương thích trong thời gian restart |
| DB/API bị nghẽn khi restart | Partition lỗi retry gây quá tải | Backoff, giới hạn concurrency, quan sát downstream |
| Worker cũ vẫn chạy sau manager fail | Hai thế hệ xử lý cùng shard | Fencing/stop-confirmation, idempotency và kiểm tra liveness |
| `allowStartIfComplete(true)` được bật | Partition đã thành công có thể chạy lại | Dùng chính sách mặc định nếu chỉ muốn restart partition lỗi |
| Tăng `run.id` để chạy tiếp | Tạo JobInstance khác, mất mapping restart | Dùng `JobOperator.restart(...)` đúng execution |
| Quét file ở mỗi lần `getPartitionNames` | Mất lợi ích tối ưu, dễ drift | Dùng manifest key index bền vững |

### 10.1. Case study: đổi số pod khi restart

Lần đầu manager phân 64 partition từ manifest `v42`, chạy trên tám worker pods; 60 partition hoàn tất, bốn partition lỗi. Khi restart, đội vận hành tăng worker pods lên 16.

**Đúng:** `getPartitionNames` vẫn trả 64 tên của `v42`; splitter lựa chọn bốn partition cần chạy; handler có thể phân phối chúng trên 16 pod nếu resource quota cho phép.

**Sai:** thay partitioner để trả 128 key mới vì “đã có 16 pod”, làm `StepExecution` lịch sử không còn khớp. Số pod là quyết định concurrency tại tầng thực thi, **không nên được dùng để đổi identity của partition plan đang restart**.

### 10.2. Case study: file listing đổi thứ tự

Lần đầu `file-A`, `file-B`, `file-C` được map theo thứ tự listing thành `partition0`, `partition1`, `partition2`. Sau sự cố, object storage trả listing theo thứ tự `file-C`, `file-A`, `file-B`. Nếu `getPartitionNames` chỉ tạo các tên `partition0..2` nhưng một phần hệ thống bên ngoài lại dùng mapping theo listing mới, nguy cơ đối soát và logging sai vẫn tồn tại.

Giải pháp là lưu một **mapping bất biến** từ `partitionKey` tới `URI/checksum` ngay từ lần đầu. Worker restart đọc context đã lưu. Nếu muốn inspect manifest, công cụ phải đọc phiên bản `v42`, không đọc folder “latest”.

## 11. Không nhầm PartitionNameProvider với cơ chế scaling

Bài toán của interface là **chi phí chia lại khi restart**, khác với số task chạy đồng thời.

| Tham số/công cụ | Chức năng |
| --- | --- |
| `Partitioner.partition(gridSize)` | Tạo tên và `ExecutionContext` cho các partition |
| `PartitionNameProvider.getPartitionNames(gridSize)` | Lấy **chỉ tên** khi restart để tránh tái phân hoạch |
| `StepExecutionSplitter` | Tạo/khôi phục StepExecution và quyết định phần cần chạy |
| `gridSize` | Gợi ý số partition, không phải trần thread |
| `TaskExecutor` | Giới hạn số worker step chạy đồng thời trong local partitioning |
| Remote `PartitionHandler` | Phân phối StepExecution sang worker JVM |
| `chunk(size)` | Ranh giới đọc/xử lý/ghi và commit của từng worker |
| `JobRepository` | Metadata checkpoint/status để restart |

Nếu job đang chạy 2 giờ và mất 5 phút ở lần split đầu, thêm `PartitionNameProvider` **không làm thời gian xử lý bình thường giảm đáng kể**; nó giúp restart tránh lặp lại bước split đắt đỏ. Nếu quá trình đọc/ghi vẫn nghẽn DB, cần tối ưu truy vấn, worker concurrency, batching hoặc phân bố partition.

### 11.1. Chi phí restart có ảnh hưởng SLA

Giả sử deadline còn 20 phút. Hai partition lỗi cần 8 phút để chạy nốt; tính lại partition plan mất 15 phút; khởi động/đối soát thêm 3 phút:

~~~text
Không có tối ưu:
  15 phút repartition + 8 phút xử lý + 3 phút đối soát
  = 26 phút -> trễ deadline.

Có PartitionNameProvider với tra tên 10 giây:
  ~0,17 phút + 8 phút + 3 phút
  = ~11,17 phút -> còn headroom.
~~~

Đây là phép tính **minh họa**, không phải một benchmark của Spring Batch. Quan trọng là đo thời gian `partition`, `getPartitionNames`, repository lookup, worker startup, remaining work, retry và publish trên môi trường thật.

## 12. Chọn số partition và gridSize trong vòng đời JobInstance

**Lần chạy đầu:** partitioner có thể chọn số shard dựa trên manifest, `gridSize` chỉ là hint. Có thể tạo 128 partition logic nhưng chỉ chạy tám worker đồng thời để cân bằng tải và giảm skew.

**Khi restart:** splitter cần khôi phục các partition từ lần chạy trước. Đừng kỳ vọng `gridSize` mới sẽ tự thay đổi các tên và phạm vi của partition đang có checkpoint. Muốn đổi kế hoạch phân vùng hoàn toàn, cần JobInstance mới/reprocess được thiết kế rõ, không coi đó là restart.

Phương án khả thi để ứng phó tăng/giảm tải **trong cùng plan** là:

- Điều chỉnh số remote worker pods.
- Điều chỉnh executor concurrency có giới hạn trong local partitioning.
- Tối ưu query hoặc writer mà không làm đổi thứ tự/ý nghĩa input của context đã lưu.
- Giảm pressure DB bằng rate limiting, connection budget hoặc job scheduling.

Nếu số partition logic quá ít gây skew nghiêm trọng, có thể cần kế hoạch phân hoạch mới cho kỳ xử lý tiếp theo; không được tự ý đổi mapping của JobInstance đang lỗi.

## 13. Metrics, log và bảo vệ JobRepository

Để chứng minh `PartitionNameProvider` hữu ích, đo:

| Nhóm | Metric đề xuất | Câu hỏi |
| --- | --- | --- |
| Partition planning | `partition()` duration, count, metadata queries | Lần đầu phân hoạch tốn bao lâu? |
| Restart naming | `getPartitionNames()` duration, returned count | Tra tên có nhanh và đủ không? |
| Repository | StepExecution/context lookup latency, status counts | Metadata còn bền vững, lookup có nhanh không? |
| Worker | Failed/completed partition count, remaining work, checkpoint lag | Có thực sự chỉ chạy lại phần lỗi? |
| Throughput | Committed items/s, chunk duration, DB locks | Restart worker có bị nghẽn downstream? |
| Data quality | Distinct business keys, expected totals, checksum | Có trùng/thiếu sau restart? |
| SLA | ETA, recovery buffer, deadline | Tối ưu restart có giúp giữ hạn không? |

`PartitionNameProvider` không tự phát những metric trên; ứng dụng cần instrument repository/partitioner/handler hoặc tạo log theo tên partition và JobExecution ID.

### 13.1. Truy vấn metadata chỉ đọc

Ví dụ xem lịch sử partition trong JobExecution cụ thể với schema mặc định:

~~~sql
SELECT
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT,
    se.START_TIME,
    se.END_TIME
FROM BATCH_STEP_EXECUTION se
WHERE se.JOB_EXECUTION_ID = :jobExecutionId
  AND se.STEP_NAME LIKE 'invoiceWorker:%'
ORDER BY se.STEP_NAME;
~~~

Khi restart, để hiểu đầy đủ cần xem **các JobExecution thuộc cùng JobInstance**, không chỉ lần chạy mới nhất: partition đã `COMPLETED` ở execution trước có thể không xuất hiện như một worker chạy lại ở execution sau.

Không sửa trực tiếp `STATUS` hoặc `ExecutionContext` để “đánh dấu xong”. Khi metadata bất nhất với output, phải điều tra transaction, worker liveness và triển khai recovery có kiểm soát.

## 14. Kế hoạch kiểm thử thực tế

Chuẩn bị manifest immutable cho một snapshot chứa 20 partition và một nguồn output có khóa nghiệp vụ duy nhất. Chạy trên JobRepository và database thực trong môi trường integration.

| Test | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| Contract tên | So `partition(...).keySet()` với `getPartitionNames(...)` | Hai tập tên bằng nhau, không duplicate/blank |
| Thứ tự listing | Thay thứ tự trả về của object storage | Không làm đổi partition identity |
| Lần chạy đầu | Chạy sạch, ghi lại invocations | `partition(...)` được gọi để tạo context |
| Restart một partition | Cho partition `file-007` fail sau vài commit | `getPartitionNames` được dùng; không phân hoạch lại; chỉ partition cần phục hồi chạy |
| Checkpoint | Kill worker giữa chunk sau khi các chunk trước commit | Context đúng, không thiếu/nhân đôi |
| Manifest drift | Xóa/thay URI/checksum trong manifest cố định | Phát hiện lỗi và từ chối restart không an toàn |
| Mất metadata | Xóa context trên môi trường test cô lập | Job không “phục hồi thành công” giả |
| Đổi pool/pods | Giữ plan, tăng concurrency từ 4 lên 8 | Tên/coverage không đổi, tốc độ được đo |
| Đổi gridSize | Thay hint khi restart | Splitter khôi phục plan cũ; không tự repartition |
| Đổi worker step name | Dùng tên mới không còn khớp lịch sử | Bị phát hiện trước khi publish output |
| Side effect replay | Giả lập commit trước crash/restart | Unique key/idempotency giữ output đúng |
| DB contention | Khi restart DB chậm | Retry/backoff có giới hạn, queue không bùng vô hạn |
| Rollout phiên bản | Restart sau khi triển khai worker mới | Context/schema/reader hợp đồng tương thích |

### 14.1. Tiêu chí nghiệm thu

Kết quả integration test nên chứng minh:

~~~text
1. Original partition keys == restart partition keys
2. No new partition identities were silently introduced
3. Completed partitions were not executed again by default
4. Incomplete partitions resumed from valid historical context
5. Output after restart == output of a clean run
6. No duplicated external business effects
7. Expensive partition() path was not rerun at restart
8. JobRepository retains a verifiable execution history
~~~

Không chỉ assert tổng `readCount` hoặc `BatchStatus.COMPLETED`. Hai lỗi đọc trùng/bỏ sót có thể triệt tiêu số lượng, trong khi dữ liệu nghiệp vụ vẫn sai. Cần đối chiếu theo ID, version, checksum hoặc bất biến có ý nghĩa.

## 15. Những hiểu nhầm thường gặp

| Nhận định | Điều cần chỉnh |
| --- | --- |
| “`PartitionNameProvider` làm partition chạy nhanh hơn.” | Nó tối ưu **khâu lấy tên khi restart**, không tăng CPU, JDBC capacity hoặc số threads. |
| “Có `PartitionNameProvider` thì không cần `Partitioner`.” | Implementation thường phải thực hiện cả hai; lần đầu vẫn cần map context. |
| “`getPartitionNames` trả `Map<String, ExecutionContext>`.” | Nó trả `Collection<String>`; context được khôi phục từ metadata đã lưu. |
| “Chỉ trả tên partition lỗi là đủ.” | Hợp đồng là tên của kế hoạch ban đầu; splitter tự lọc trạng thái. |
| “Tên có thể đổi vì số lượng vẫn như cũ.” | StepExecution và checkpoint được gắn theo identity tên. |
| “Thay `gridSize` là đủ để chia lại khi restart.” | Restart dùng partition lịch sử, không phải một kế hoạch mới. |
| “Dùng UUID ngẫu nhiên an toàn vì không trùng.” | Unique không đồng nghĩa stable giữa các lần chạy. |
| “Đã có JobRepository thì input thay đổi cũng không sao.” | Checkpoint cũ trên file/query mới có thể gây sai dữ liệu. |
| “Provider giúp khôi phục metadata bị xóa.” | Nó chỉ cung cấp tên, không tái tạo context/checkpoint đã mất. |
| “Provider bảo đảm exactly-once.” | Retry/chunk rollback/external side effects vẫn cần idempotency. |
| “Trong remote partitioning chỉ manager cần biết context.” | Remote worker cần đọc `StepExecution`/context đã lưu hoặc data được chuyển đúng. |
| “Nếu getPartitionNames nhanh thì job luôn đạt SLA.” | Còn thời gian worker chạy lại, validation, publish và contention. |

## 16. Checklist triển khai

- [ ] Xác nhận `Partitioner.partition(...)` thực sự tốn chi phí đáng kể khi restart, cần tối ưu.
- [ ] Lưu một **partition manifest bất biến** theo snapshot/JobInstance.
- [ ] `partition(...)` và `getPartitionNames(...)` cùng dựa trên manifest đó.
- [ ] Tập tên duy nhất, không blank và **khớp chính xác** giữa hai API.
- [ ] Tên không phụ thuộc thứ tự listing, số workers hiện tại, random ID hoặc clock.
- [ ] `getPartitionNames(...)` trả **toàn bộ tên** kế hoạch, không tự lọc FAILED.
- [ ] Đảm bảo JobRepository/ExecutionContext bền vững, backup và retention.
- [ ] Worker sử dụng context lịch sử và input snapshot không đổi.
- [ ] Writer dùng transaction/idempotency, có cơ chế đối soát external side effect.
- [ ] Không đổi worker step name, partition keys hoặc mapping trong cùng JobInstance.
- [ ] Có metric thời gian partition/get names và số worker StepExecution thực thi lại.
- [ ] Có test crash/restart, drift, missing metadata và đổi concurrency không đổi tên.
- [ ] Tính thời gian restart vào SLA và recovery budget.
- [ ] Khi muốn repartition, có quy trình reprocess/migration riêng thay vì giả dạng restart.

## 17. Câu hỏi tự kiểm tra

1. `PartitionNameProvider#getPartitionNames(int)` trả về kiểu dữ liệu gì trong Spring Batch 5.2.x? Nó khác `Partitioner.partition(int)` ra sao?
2. Trong lần chạy đầu, `partition(...)` có còn được gọi nếu class đã triển khai `PartitionNameProvider` không?
3. Khi restart, vì sao danh sách tên phải bằng tập key của `partition(...)` ban đầu, chứ không chỉ có cùng số phần tử?
4. Nếu `partition(...)` mất 12 phút vì phải quét manifest lớn, còn `getPartitionNames(...)` mất 2 giây, cải thiện nào có thể đạt trong **chi phí restart**?
5. Có 100 partition và chỉ 2 partition `FAILED`. `getPartitionNames` nên trả 2 hay 100 tên? Ai quyết định partition phải chạy lại?
6. Tại sao tăng `gridSize` từ 8 lên 16 trên cùng JobInstance không nên làm thay đổi partition key và context khi restart?
7. Khi hệ thống đổi từ 4 lên 12 worker pods, tên partition có nên đổi theo số pod không?
8. Nếu manifest mất nhưng JobRepository còn context cũ, có thể mặc định sinh tên mới rồi tiếp tục không?
9. Một worker đã commit output nhưng process chết trước khi xác nhận trạng thái. Vì sao `PartitionNameProvider` không giúp chống ghi trùng?
10. Vì sao `@StepScope` có ích cho reader theo partition nhưng không tự bảo đảm writer singleton thread-safe?
11. Sự khác nhau giữa **restart cùng JobInstance** và **tạo JobInstance mới để reprocess** là gì?
12. Test integration quan trọng nhất để chứng minh tối ưu provider có thực sự hoạt động là gì?

**Gợi ý:** (1) `Collection<String>` so với `Map<String,ExecutionContext>`. (2) Có, lần đầu cần context đầy đủ. (3) Tên là danh tính để đối chiếu StepExecution/checkpoint. (4) Tiết kiệm khoảng 11 phút 58 giây ở khâu phân hoạch lại, nếu các giả định khác không đổi. (5) 100 tên; splitter đối chiếu repository và chọn phần cần chạy. (6) Plan/checkpoint cũ phải ổn định. (7) Không, chỉ điều chỉnh concurrency thực thi. (8) Không, phải phục hồi manifest đúng phiên bản hoặc dừng. (9) Retry vẫn có thể lặp side effect, cần idempotency/transaction. (10) Scope theo StepExecution; các singleton còn chia sẻ state. (11) Restart giữ checkpoint và identity cũ; reprocess là lần chạy nghiệp vụ khác. (12) Làm một partition fail, restart đúng instance, spy chứng minh `partition(...)` không bị gọi lại, `getPartitionNames(...)` được dùng và output vẫn đúng.

## Tài liệu tham khảo

- [Spring Batch Reference 5.2 — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): `Partitioner`, `PartitionNameProvider`, tên partition và cơ chế restart.
- [Spring Batch 5.2 Javadoc — PartitionNameProvider](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/partition/support/PartitionNameProvider.html): interface tùy chọn và hợp đồng trả `Collection<String> getPartitionNames(int)`.
- [Spring Batch 5.2 Javadoc — Partitioner](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/partition/support/Partitioner.html): `Map<String, ExecutionContext> partition(int)`.
- [Spring Batch 5.2 Javadoc — SimpleStepExecutionSplitter](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/partition/support/SimpleStepExecutionSplitter.html): quyết định worker executions khi restart.
- [Spring Batch Reference — Step Scope và Late Binding](https://docs.spring.io/spring-batch/reference/step/late-binding.html): đọc `stepExecutionContext` từ reader/worker StepExecution.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): checkpoint, `ItemStream` và khôi phục trạng thái.

**Điểm cốt lõi:** `PartitionNameProvider` là **tối ưu hiệu năng khi restart partitioned step**. Lần đầu `Partitioner.partition(...)` vẫn tạo đủ context; sau khi metadata được lưu, restart có thể gọi `getPartitionNames(...)` để lấy tên và khôi phục context lịch sử thay vì chia lại input. Tính đúng đắn phụ thuộc vào **tên ổn định, partition manifest bất biến, JobRepository bền vững, checkpoint đúng và writer chống xử lý lặp**. Hãy dùng interface này khi phân hoạch ban đầu đắt đỏ và kiểm chứng bằng một lần crash/restart có đối soát dữ liệu thực.
