# Chia theo file hoặc thư mục

**Chia theo file hoặc thư mục (file/directory partitioning)** là chiến lược dùng ranh giới của dữ liệu trên hệ thống lưu trữ để phân công công việc cho các worker trong Spring Batch. Thay vì chia một bảng theo khoảng ID, manager có thể tạo một partition cho từng tệp CSV, JSON Lines, XML đã hoàn chỉnh; hoặc tạo một partition cho từng nhóm tệp, thư mục, ngày dữ liệu hay bucket. Mỗi worker nhận một **ExecutionContext** chứa định danh vùng công việc rồi chạy một **StepExecution** riêng để đọc, xử lý và ghi dữ liệu thuộc vùng đó.

Bài học thuộc chương **Partitioner** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module tập trung mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán, đồng thời đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và chọn kiến trúc phù hợp tài nguyên. Ở bài này, mục tiêu là thiết kế partition theo tài nguyên file/thư mục **có thể kiểm chứng tính đúng đắn và khôi phục sau sự cố**, rồi đánh giá hiệu năng theo phân bố file thực tế.

## 1. Mục tiêu học tập

Sau khi hoàn thành, bạn có thể:

1. Phân biệt **mỗi file một partition**, **mỗi thư mục một partition** và **nhiều file trong một partition**.
2. Hiểu vai trò của `Partitioner.partition(gridSize)`, `ExecutionContext`, `PartitionHandler` và `@StepScope` trong local/remote partitioning.
3. Tạo danh sách đầu vào bất biến (**manifest**) để một file chỉ thuộc một vùng công việc và tên partition không thay đổi khi restart.
4. Triển khai Partitioner cho một tập file CSV với Spring Batch 5.x, cùng reader, processor và writer mẫu.
5. Kiểm soát file đang ghi dở, file được sửa/xóa, file trùng tên, symlink và đường dẫn không an toàn.
6. Giải quyết dữ liệu lệch: một file rất lớn, hàng trăm nghìn file nhỏ hoặc thư mục chứa lượng việc không cân.
7. Kiểm thử không thiếu/trùng dữ liệu, tính idempotent, lỗi giữa chunk, retry/restart và khả năng mở rộng theo CPU, disk, network, DB.

**Tình huống xuyên suốt:** mỗi đêm hệ thống xuất 800 file CSV chứa giao dịch, tổ chức dưới các thư mục như `2026-11-26/region-a/sales-001.csv`. Một step tuần tự mất nhiều giờ; nhóm muốn dùng bốn worker trong cùng JVM trước, sau đó có thể chuyển sang remote partitioning. Kết quả phải đảm bảo mọi bản ghi hợp lệ được xử lý đúng một lần *về mặt nghiệp vụ*, kể cả khi một worker phải chạy lại.

## 2. Chia file/thư mục khác gì chia khoảng khóa chính?

Trong chia theo khoảng ID, Partitioner xác định `[fromInclusive, toExclusive)` và worker dùng một câu SQL với điều kiện khóa chính. Trong chia theo file/thư mục, **định danh nguồn** thường là đường dẫn, object key, manifest entry hoặc nhóm tài nguyên được chốt sẵn. Worker sử dụng `FlatFileItemReader`, `MultiResourceItemReader` hoặc reader riêng cho định dạng nguồn.

| Chiến lược | Đơn vị phân công | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| Một file / partition | Một file đã hoàn chỉnh | Đơn giản, dễ log và restart theo file | Quá nhiều partition nếu có hàng trăm nghìn file nhỏ; một file khổng lồ vẫn chỉ có một worker |
| Một thư mục / partition | Các file của một thư mục hoặc prefix | Hợp với phân vùng theo tenant/ngày/region | Thư mục có thể rất lệch số file và kích thước |
| Nhiều file / partition | Danh sách file được phân nhóm ổn định | Giảm metadata overhead, cân bằng tải tốt hơn | Phải đóng băng danh sách và thứ tự đọc bên trong nhóm |
| Một phần của file / partition | Khoảng byte/record bên trong file | Tận dụng nhiều worker cho file cực lớn | Khó bảo đảm ranh giới record, CSV nhiều dòng, mã hóa và checkpoint |

**Không nên suy ra “một file = một thread”.** Partitioner tạo các **StepExecution**, còn số worker chạy thực sự phụ thuộc PartitionHandler, TaskExecutor, giới hạn thread pool và tài nguyên của hệ thống.

~~~mermaid
flowchart TD
    J["JobExecution"] --> M["Manager Step"]
    M --> P["Partitioner"]
    P --> A["partition0: sales-001.csv"]
    P --> B["partition1: sales-002.csv"]
    P --> C["partition2: sales-003.csv"]
    A --> W1["Worker StepExecution 0"]
    B --> W2["Worker StepExecution 1"]
    C --> W3["Worker StepExecution 2"]
    W1 --> D[("Business database")]
    W2 --> D
    W3 --> D
~~~

Local partitioning chạy các worker trong **cùng JVM**; remote partitioning điều phối worker qua middleware. Cả hai đều có thể dùng ý tưởng phân công theo file, nhưng ở mô hình remote, **đường dẫn file phải có nghĩa tại worker ở máy khác** hoặc phải thay bằng object URI và cơ chế tải nguồn tương ứng.

## 3. Quy tắc quan trọng nhất: đầu vào phải được chốt

Nếu mỗi lần chạy/restart manager lại gọi `Files.list(...)` trên một thư mục đang được ghi thêm file, danh sách partition có thể thay đổi:

~~~text
Tại T0: [a.csv, c.csv]
partition0 -> a.csv
partition1 -> c.csv

Tại T1: người khác thêm b.csv
Danh sách mới: [a.csv, b.csv, c.csv]
partition0 -> a.csv
partition1 -> b.csv   <-- cùng tên partition nhưng khác nguồn
partition2 -> c.csv
~~~

Nếu `partition1` của lần chạy đầu đã COMPLETED và bị đối chiếu với file khác sau restart, hệ thống có nguy cơ **bỏ sót b.csv** hoặc đọc trùng c.csv. Vì vậy, tên partition và ánh xạ từ tên đó đến tập dữ liệu phải **ổn định qua mọi JobExecution của cùng JobInstance**.

Một quy trình nạp file an toàn thường là:

1. Producer ghi `sales-001.csv.tmp`, hoàn tất nội dung rồi đóng/flush theo hợp đồng độ bền lưu trữ.
2. Producer công bố file hoàn chỉnh bằng thao tác rename/move có tính nguyên tử **nếu hệ thống file hỗ trợ**, hoặc xuất object version cố định cùng dấu hiệu hoàn thành.
3. Một bước tiền xử lý xác định đúng **tập file thuộc batch**, tạo **manifest bất biến**, sắp xếp và kiểm tra các file trùng.
4. Lưu manifest ở nơi bền vững; dùng `manifestId` hoặc digest cùng các thông tin nhận diện snapshot trong JobParameters/metadata.
5. Manager lấy đúng manifest đó để chia partition. Worker đọc đúng file/version được chỉ định; không tự “quét thêm” các file mới trong quá trình chạy.

**Manifest** có thể là file text UTF-8, bảng database, object manifest hoặc một bản snapshot metadata. Ví dụ file manifest đơn giản:

~~~text
2026-11-26/region-a/sales-001.csv
2026-11-26/region-a/sales-002.csv
2026-11-26/region-b/sales-003.csv
~~~

Từng dòng là một **đường dẫn tương đối** bên trong thư mục gốc đã chốt. Manifest trong ví dụ phải giữ nguyên nội dung và thứ tự trong toàn bộ vòng đời job/restart; hệ thống thực nên thêm **file ID, size, checksum/hash hoặc storage version** để phát hiện file nguồn bị thay thế dù vẫn mang cùng tên. Chỉ kiểm tra `lastModified` hoặc kích thước thường không đủ để chứng minh nội dung không đổi.

### Định danh công việc cần ổn định

- **JobInstance:** được Spring Batch nhận diện bằng job name cùng identifying JobParameters.
- **Partition:** có tên ổn định như `partition0`, `partition1`; giữ ánh xạ với file/nhóm file không đổi.
- **File ID:** định danh file logic trong batch. Đường dẫn có thể là một phần của ID, nhưng với object store cần xét cả bucket, key và version.
- **Record ID:** định danh bản ghi nghiệp vụ bên trong file; cần thiết khi retry hoặc phát lại một chunk.

Nếu file có cùng tên nhưng nội dung mới hợp lệ, phải xác định đây là **batch/version khác**; không ghi đè manifest cũ rồi restart cùng JobInstance.

## 4. Thiết kế ExecutionContext cho worker

`ExecutionContext` là nơi Spring Batch đưa thông tin phân vùng đến một worker step. Với **một file / partition**, chỉ cần lưu một số giá trị nhỏ, có thể serialize:

~~~yaml
partitionName: partition0
stepExecutionContext:
  fileId: file-00000
  inputPath: /batch/input/2026-11-26/region-a/sales-001.csv
~~~

Đây là biểu diễn **minh họa**, không phải cấu trúc YAML mà Spring Batch tự xuất ra. Trong code Java, Partitioner trả `Map<String, ExecutionContext>`; `partitionName` là key trong map, còn `fileId` và `inputPath` là các key bên trong `ExecutionContext`.

Khi dùng một nhóm file, có hai lựa chọn:

1. Chỉ lưu `groupId` và `manifestId`; worker đọc danh sách file của nhóm từ một manifest bền vững. Đây thường là cách tốt nếu nhóm có nhiều file.
2. Lưu danh sách tên file trong `ExecutionContext` khi danh sách **nhỏ, ổn định và tương thích cơ chế serialization** của JobRepository. Tránh nhồi hàng chục nghìn đường dẫn hoặc object không serializable vào metadata.

`ExecutionContext` không phải nơi lưu nội dung toàn bộ file. Kích thước metadata lớn làm tăng thời gian serialize, commit, truy vấn JobRepository và phức tạp restart.

## 5. Triển khai Partitioner đọc manifest bất biến

Ví dụ dưới đây sử dụng **Java 17+ và Spring Batch 5.x**, đầu vào nằm trên filesystem chung của một ứng dụng local partitioning. Manifest có một đường dẫn tương đối trên mỗi dòng. Mọi file phải tồn tại tại thời điểm tạo partition.

Các nguyên tắc triển khai:

- Giữ **đúng thứ tự dòng manifest** để tên partition ổn định.
- Bỏ qua dòng rỗng và dòng chú thích bắt đầu bằng `#`; chuẩn manifest phải được công bố trước khi chạy.
- Chuẩn hóa và kiểm tra đường dẫn thực để không đi ra ngoài thư mục nguồn.
- Phát hiện file được liệt kê hai lần, kể cả khi hai đường dẫn quy về một file thực.
- Mỗi entry tạo một `ExecutionContext` với `fileId` và `inputPath`.
- Trả lỗi rõ khi manifest không có file; workflow cho batch rỗng có thể chọn một nhánh no-op riêng.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class ManifestFilePartitioner implements Partitioner {
    private final Path inputRoot;
    private final Path manifestPath;

    public ManifestFilePartitioner(Path inputRoot, Path manifestPath) {
        this.inputRoot = inputRoot;
        this.manifestPath = manifestPath;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        try {
            Path root = inputRoot.toRealPath();
            if (!Files.isDirectory(root)) {
                throw new IllegalArgumentException("Input root is not a directory");
            }

            List<String> entries =
                    Files.readAllLines(manifestPath, StandardCharsets.UTF_8);
            Map<String, ExecutionContext> result = new LinkedHashMap<>();
            Set<Path> seenFiles = new HashSet<>();

            for (String line : entries) {
                String entry = line.trim();
                if (entry.isEmpty() || entry.startsWith("#")) {
                    continue;
                }

                Path relative = Path.of(entry);
                if (relative.isAbsolute()) {
                    throw new IllegalArgumentException(
                            "Manifest path must be relative: " + entry);
                }

                Path candidate = root.resolve(relative).normalize();
                if (!candidate.startsWith(root)) {
                    throw new IllegalArgumentException(
                            "Path escapes input root: " + entry);
                }

                // toRealPath() follows symlinks; reject escape via symlinks.
                Path file = candidate.toRealPath();
                if (!file.startsWith(root) || !Files.isRegularFile(file)) {
                    throw new IllegalArgumentException(
                            "Invalid input file: " + entry);
                }
                if (!seenFiles.add(file)) {
                    throw new IllegalArgumentException(
                            "Duplicate input file: " + entry);
                }

                int index = result.size();
                String fileId = String.format(
                        Locale.ROOT, "file-%05d", index);
                ExecutionContext context = new ExecutionContext();
                context.putString("fileId", fileId);
                context.putString("inputPath", file.toString());
                result.put("partition" + index, context);
            }

            if (result.isEmpty()) {
                throw new IllegalStateException("Manifest contains no files");
            }
            return result;
        } catch (IOException ex) {
            throw new IllegalStateException(
                    "Cannot load input manifest or files", ex);
        }
    }
}
~~~

`gridSize` trong implementation này được **validate nhưng không dùng để giới hạn số file**: một file sẽ tạo một partition dù `gridSize=4`. Đây là lựa chọn có chủ đích cho ví dụ một-file-một-partition. Số worker thực chạy đồng thời được giới hạn bởi executor/handler. Với lượng file cực lớn, không nên giữ nguyên cách này; phần 9 trình bày phương án nhóm file.

Đây là lớp minh họa cho **manifest đã được chốt bởi hệ thống tin cậy**. Ở production, còn phải kiểm tra quyền đọc, loại file cho phép, dung lượng/digest, giới hạn số lượng entry, symlink thay đổi trong lúc chạy và khả năng snapshot của storage. Việc gọi `toRealPath()` xác nhận đường dẫn tại thời điểm partition; **không khóa nội dung file** cho tới khi worker đọc. Không cho một tiến trình khác thay đổi file hoặc manifest trong lúc job đang chạy.

### Vì sao không quét thư mục ngay trong partition()?

~~~java
// Ví dụ ngắn nhưng dễ gây sai khi restart nếu directory đang thay đổi:
try (Stream<Path> paths = Files.list(inputRoot)) {
    List<Path> files = paths.filter(Files::isRegularFile).toList();
    // Dựa vào thứ tự listing chưa chắc đã ổn định.
}
~~~

Ngay cả khi sắp xếp bằng `sorted()`, một file thêm/xóa/đổi tên trước lần restart vẫn có thể làm các chỉ số partition thay đổi. Nên tạo **manifest cố định trước khi bắt đầu job** rồi dùng lại manifest đó cho mọi lần khôi phục cùng JobInstance.

## 6. Reader và worker Step: mỗi partition đọc một file

Một worker nhận đường dẫn từ `stepExecutionContext['inputPath']`. `@StepScope` tạo reader có trạng thái riêng theo mỗi **StepExecution**, đặc biệt quan trọng với `FlatFileItemReader` vì reader giữ vị trí dòng và checkpoint.

Giả sử file CSV có header:

~~~csv
orderId,grossTotal
O-1001,120.00
O-1002,99.50
O-1003,450.75
~~~

Khai báo record đầu vào/đầu ra và reader:

~~~java
record SaleInput(String orderId, BigDecimal grossTotal) {}
record SaleResult(String orderId, BigDecimal netTotal) {}

@Bean
@StepScope
FlatFileItemReader<SaleInput> saleFileReader(
        @Value("#{stepExecutionContext['inputPath']}") String inputPath) {

    return new FlatFileItemReaderBuilder<SaleInput>()
            .name("saleFileReader")
            .resource(new FileSystemResource(inputPath))
            .strict(true)
            .linesToSkip(1)
            .saveState(true)
            .delimited()
            .names("orderId", "grossTotal")
            .fieldSetMapper(fields -> new SaleInput(
                    fields.readString("orderId"),
                    fields.readBigDecimal("grossTotal")))
            .build();
}

@Bean
ItemProcessor<SaleInput, SaleResult> saleProcessor() {
    return sale -> {
        if (sale.orderId().isBlank()
                || sale.grossTotal() == null
                || sale.grossTotal().signum() < 0) {
            throw new IllegalArgumentException("Invalid sale input");
        }
        return new SaleResult(
                sale.orderId(),
                sale.grossTotal().setScale(2, RoundingMode.HALF_UP));
    };
}
~~~

Trong ví dụ, `strict(true)` giúp phát hiện tệp không tồn tại lúc reader mở. `linesToSkip(1)` bỏ một dòng header. `saveState(true)` cho phép reader lưu vị trí phục hồi theo cơ chế Spring Batch, **với điều kiện nội dung file và cách xác định dòng không thay đổi**. Chỉ vì reader có `saveState(true)` không có nghĩa dữ liệu nguồn đã được đóng băng.

`@StepScope` có nghĩa là **mỗi StepExecution có reader riêng**, không phải mỗi thread hoặc mỗi item có reader riêng. Trong local partitioning, các partition có StepExecution khác nhau. Không nên bật thêm `taskExecutor` cho **worker step** khi dùng reader stateful mà chưa kiểm tra riêng hành vi multi-threaded step và restart của reader.

### Writer idempotent cho bản ghi có business key

Giả sử `orderId` là duy nhất **trong một file**, và `fileId` ổn định theo manifest. Ta định nghĩa khóa kết quả `(batch_key, file_id, order_id)` để một item có thể ghi lại khi retry/restart mà không tạo thêm dòng.

~~~sql
CREATE TABLE normalized_sale (
    batch_key   VARCHAR(80) NOT NULL,
    file_id     VARCHAR(80) NOT NULL,
    order_id    VARCHAR(120) NOT NULL,
    net_total   NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (batch_key, file_id, order_id)
);
~~~

~~~java
@Bean
@StepScope
JdbcBatchItemWriter<SaleResult> saleWriter(
        DataSource dataSource,
        @Value("#{jobParameters['batchKey']}") String batchKey,
        @Value("#{stepExecutionContext['fileId']}") String fileId) {

    return new JdbcBatchItemWriterBuilder<SaleResult>()
            .dataSource(dataSource)
            .sql("""
                 INSERT INTO normalized_sale
                     (batch_key, file_id, order_id, net_total)
                 VALUES (:batchKey, :fileId, :orderId, :netTotal)
                 ON CONFLICT (batch_key, file_id, order_id)
                 DO UPDATE SET net_total = EXCLUDED.net_total
                 """)
            .itemSqlParameterSourceProvider(item ->
                    new MapSqlParameterSource()
                            .addValue("batchKey", batchKey)
                            .addValue("fileId", fileId)
                            .addValue("orderId", item.orderId())
                            .addValue("netTotal", item.netTotal()))
            .build();
}
~~~

Nếu file có thể chứa hai bản ghi khác nhau cùng `orderId`, cần phân biệt chúng bằng một **record ID/line ID ổn định**, hoặc đưa trùng lặp vào quy trình phát hiện lỗi. Nếu nhiều file chứa cùng order logic và nghiệp vụ chỉ muốn một kết quả chung, chọn khóa nghiệp vụ ở phạm vi **toàn batch** thay vì đưa `fileId` vào khóa chính.

UPSERT làm tác động ghi một dòng **không tăng số dòng khi lặp**, nhưng có thể ghi đè giá trị cũ nếu nguồn hoặc quy tắc thay đổi. Để bảo đảm dữ liệu đúng, phải có snapshot và chính sách version/checksum; side effect ngoài database như gửi email hoặc gọi API vẫn cần idempotency hoặc outbox riêng.

## 7. Nối Partitioner với manager và worker Step

Ví dụ local partitioning Spring Batch 5.x, Spring Boot 3.x/Java 17+:

~~~java
@Bean
@StepScope
Partitioner saleFilePartitioner(
        @Value("#{jobParameters['inputRoot']}") String inputRoot,
        @Value("#{jobParameters['manifestPath']}") String manifestPath) {

    return new ManifestFilePartitioner(
            Path.of(inputRoot),
            Path.of(manifestPath));
}

@Bean
Step saleWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        @Qualifier("saleFileReader") ItemReader<SaleInput> reader,
        @Qualifier("saleProcessor") ItemProcessor<SaleInput, SaleResult> processor,
        @Qualifier("saleWriter") ItemWriter<SaleResult> writer) {

    return new StepBuilder("saleWorkerStep", jobRepository)
            .<SaleInput, SaleResult>chunk(200, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}

@Bean
ThreadPoolTaskExecutor salePartitionExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("sale-partition-");
    executor.initialize();
    return executor;
}

@Bean
Step saleManagerStep(
        JobRepository jobRepository,
        @Qualifier("saleWorkerStep") Step workerStep,
        @Qualifier("saleFilePartitioner") Partitioner partitioner,
        @Qualifier("salePartitionExecutor") TaskExecutor executor) {

    return new StepBuilder("saleManagerStep", jobRepository)
            .partitioner(workerStep.getName(), partitioner)
            .step(workerStep)
            .gridSize(4)
            .taskExecutor(executor)
            .build();
}

@Bean
Job saleImportJob(JobRepository jobRepository,
                  @Qualifier("saleManagerStep") Step managerStep) {
    return new JobBuilder("saleImportJob", jobRepository)
            .start(managerStep)
            .build();
}
~~~

Trong ví dụ:

- `saleManagerStep` tạo các worker StepExecution từ manifest.
- Mỗi worker dùng `FlatFileItemReader` riêng, đọc theo chunk 200 item và ghi kết quả trong transaction do step quản lý.
- `gridSize(4)` **không** giới hạn số partition trong `ManifestFilePartitioner`; nếu manifest có 800 file, sẽ có khoảng **800 worker StepExecution** được lập lịch qua executor có bốn thread trong mô hình local.
- `batchKey`, `manifestPath` và `inputRoot` phải có mặt trong JobParameters và được quản lý nhất quán cho lần restart.
- Các import, cấu hình datasource, transaction manager và exception policy được lược bớt; đây là bộ khung học thuật cần ghép với hạ tầng Spring Batch của ứng dụng.

Với 800 file, tạo 800 StepExecution có thể vẫn chấp nhận được. Với 500.000 file nhỏ, cùng cách tiếp cận có thể làm JobRepository và việc điều phối tốn tài nguyên hơn nội dung cần xử lý; hãy nhóm file như phần tiếp theo.

## 8. Chia theo thư mục: một StepExecution cho nhiều file

Giả sử cấu trúc nguồn:

~~~text
/data/inbound/
  2026-11-26/
    region-a/
      sales-001.csv
      sales-002.csv
    region-b/
      sales-003.csv
      sales-004.csv
    region-c/
      sales-005.csv
~~~

Có thể tạo ba partition:

| Partition | Nguồn được giao | Worker xử lý |
| --- | --- | --- |
| `region-a` | `sales-001.csv`, `sales-002.csv` | Đọc tuần tự hai file trong StepExecution của vùng A |
| `region-b` | `sales-003.csv`, `sales-004.csv` | Đọc tuần tự hai file trong StepExecution của vùng B |
| `region-c` | `sales-005.csv` | Đọc một file trong StepExecution của vùng C |

Một worker có thể dùng **MultiResourceItemReader** với delegate `FlatFileItemReader` để đi qua nhiều file. Hãy giữ **danh sách file và thứ tự duyệt cố định** khi restart.

~~~mermaid
flowchart LR
    P["Directory Partitioner"] --> G1["group A / region-a"]
    P --> G2["group B / region-b"]
    P --> G3["group C / region-c"]
    G1 --> R1["MultiResourceItemReader A"]
    G2 --> R2["MultiResourceItemReader B"]
    G3 --> R3["MultiResourceItemReader C"]
    R1 --> D[("Output")]
    R2 --> D
    R3 --> D
~~~

### MultiResourceItemReader hoạt động như thế nào?

Reader này có một **delegate** biết đọc một tài nguyên, chẳng hạn `FlatFileItemReader`. Khi hết một file, nó chuyển sang file tiếp theo trong mảng `Resource[]`. Với danh sách tài nguyên bất biến, thứ tự rõ ràng và cơ chế `ItemStream` phù hợp, metadata có thể lưu vị trí file và vị trí item bên trong file.

Ví dụ cách xây reader cho một nhóm file nhỏ, với điều kiện phương thức `loadFrozenGroupResources(groupId)` trả về **cùng danh sách resource, cùng thứ tự** sau restart:

~~~java
@Bean
@StepScope
MultiResourceItemReader<SaleInput> groupedSalesReader(
        @Value("#{stepExecutionContext['groupId']}") String groupId,
        FrozenManifestService manifestService) {

    Resource[] resources = manifestService
            .loadFrozenGroupResources(groupId);

    FlatFileItemReader<SaleInput> delegate =
            new FlatFileItemReaderBuilder<SaleInput>()
                    .name("groupedSaleDelegate")
                    .strict(true)
                    .linesToSkip(1)
                    .delimited()
                    .names("orderId", "grossTotal")
                    .fieldSetMapper(fields -> new SaleInput(
                            fields.readString("orderId"),
                            fields.readBigDecimal("grossTotal")))
                    .build();

    return new MultiResourceItemReaderBuilder<SaleInput>()
            .name("groupedSalesReader")
            .resources(resources)
            .delegate(delegate)
            .saveState(true)
            .build();
}
~~~

`FrozenManifestService` là **interface/service minh họa cần triển khai** cho nơi lưu manifest của ứng dụng; đoạn code này thể hiện cách lắp reader chứ không phải project có thể chạy ngay khi chưa khai báo service đó. Nếu reader của thư viện tự sắp xếp resources bằng comparator, phải dùng comparator ổn định và bảo đảm danh sách không thay đổi. Với các file trùng tên ở nhiều thư mục, so sánh theo **đường dẫn/định danh đầy đủ** để tránh thứ tự bất định.

**Chia theo thư mục chỉ hợp lý khi ranh giới thư mục có ý nghĩa và tương đối cân bằng.** Một thư mục có 200 GB dữ liệu, thư mục khác có 3 KB thì tạo hai partition vẫn có worker lớn kéo dài toàn job. Nếu dữ liệu lệch, tạo các **nhóm file cân bằng** độc lập với cấu trúc thư mục vật lý.

## 9. Nhiều file nhỏ: nhóm theo số lượng hoặc tổng kích thước

Mỗi file một partition tạo rất nhiều metadata và chi phí mở/đóng reader khi có hàng trăm nghìn file nhỏ. Có thể tạo `G` nhóm từ một manifest bất biến, mỗi nhóm có nhiều file và một `groupId` cố định.

### Phương án A — chia theo số file

Với 10.000 file cùng cỡ và muốn 100 nhóm, sắp xếp file theo định danh ổn định rồi chia mỗi nhóm khoảng 100 file. Phương án này dễ thực hiện nhưng **không cân bằng** nếu có file 1 KB và file 5 GB.

### Phương án B — chia theo tổng byte

Một chiến lược xấp xỉ:

1. Chốt manifest gồm `fileId`, vị trí và **size** của mỗi file.
2. Sắp file theo kích thước giảm dần; khi size bằng nhau dùng `fileId` để tie-break ổn định.
3. Lần lượt đưa file vào nhóm có tổng byte nhỏ nhất.
4. Ghi **kết quả nhóm đã chọn** vào manifest/snapshot bền vững. Partitioner chỉ trả `groupId`.
5. Worker tra lại đúng danh sách file của nhóm, giữ thứ tự bất biến trong mỗi lần restart.

Thuật toán greedy theo byte không bảo đảm thời gian chạy cân bằng: file nén, file nhiều dòng lỗi, API call nặng và định dạng khác nhau có thể khiến cùng 1 GB tốn thời gian rất khác. Nếu có dữ liệu lịch sử, hãy đo **thời gian xử lý/item hoặc chi phí theo định dạng** để cải thiện ước lượng.

| Tình huống | Đơn vị chia nên cân nhắc | Lý do |
| --- | --- | --- |
| 30 file lớn, kích thước khá đều | Một file/partition | Ít metadata, dễ retry theo file |
| 100.000 file vài KB | Nhóm 50–500 file/partition tùy đo đạc | Giảm overhead mở/đóng file và StepExecution |
| Thư mục tương ứng tenant, tải đều | Một thư mục/partition | Ranh giới nghiệp vụ và kiểm toán rõ |
| Một tenant có 90% dung lượng | Chia tenant nặng thành nhiều nhóm | Tránh một worker thành critical path |
| Một file duy nhất cực lớn | Xem xét split nội file hoặc staging | Một file/partition không tạo thêm song song cho file đó |

**Không lựa chọn số file/nhóm theo một con số cứng duy nhất.** Hãy đo thời gian mở file, chi phí parse, commit, metadata và độ lệch của từng partition. Một nhóm quá lớn làm restart phải xử lý lại nhiều công việc nếu checkpoint không đáng tin; nhóm quá nhỏ gây áp lực điều phối.

## 10. Một file cực lớn: khi nào cần chia bên trong file?

Một file CSV 500 GB chỉ tạo **một** partition nếu dùng chiến lược một-file-một-worker. Dù tăng thread pool từ 4 lên 32, step xử lý file đó thường vẫn chỉ có một worker đọc tuần tự.

Các lựa chọn:

- Nếu nguồn hỗ trợ chia theo record độc lập, tạo **chunk manifest** gồm các khoảng record/index có biên rõ, sau đó phân công theo các khoảng ấy.
- Với file line-delimited không có record nhiều dòng, có thể tính các **byte offset** của ranh giới xuống dòng, nhưng phải xử lý UTF-8, BOM, CRLF, record lỗi và thứ tự resume.
- Với CSV có **trường được quote chứa newline**, không thể cắt tùy ý theo byte hoặc ký tự xuống dòng; cần parser hiểu định dạng, một pass xây index record hoặc chuyển trước sang nhiều file.
- Với gzip stream thông thường, giải nén tuần tự thường khó random seek theo byte nén; cần format splittable hoặc tiền xử lý/tách file.
- Nếu dữ liệu ở object store, có thể dùng range requests khi định dạng và codec cho phép; việc nhận byte range **không bảo đảm** có ranh giới record đúng.

Trong nhiều trường hợp, **tiền xử lý file lớn thành các shard bất biến** rồi chạy một-file-một-partition đơn giản và dễ restart hơn việc phát triển reader theo byte offset tùy biến. Phải cân nhắc chi phí staging, I/O bổ sung và dung lượng đĩa.

## 11. Thread safety và tài nguyên của file worker

Trong local partitioning, các worker StepExecution độc lập nhưng vẫn chia sẻ JVM, executor, DB pool, CPU, cache và có thể cùng đọc một thiết bị lưu trữ.

| Thành phần | Nguyên tắc triển khai | Rủi ro |
| --- | --- | --- |
| `FlatFileItemReader` | Tạo mới theo `@StepScope` cho từng StepExecution | Chia sẻ cursor/state dẫn đến đọc thiếu hoặc lỗi checkpoint |
| `MultiResourceItemReader` | Danh sách resource bất biến, thứ tự ổn định, delegate per worker | File xuất hiện/biến mất khiến vị trí resume lệch |
| `ItemProcessor` | Stateless hoặc dependency thread-safe | Mutable singleton service gây race dù reader đã tách |
| `ItemWriter` | Transactional; uniqueness/idempotency theo business key | Ghi trùng khi retry và conflict giữa các file |
| `JobRepository` | Metadata ổn định, connection pool đủ, theo dõi StepExecution | Nhiều partition gây quá tải update/commit metadata |
| Filesystem/object store | Read-only snapshot, rate limit và throughput phù hợp | File bị sửa; IOPS/network quá tải |

**Một pool thread lớn không tự tăng throughput.** Bốn worker có thể cùng đọc một ổ đĩa làm tăng seek/IOPS; 32 worker cùng tải từ object store có thể gặp throttling hoặc cạn kết nối HTTP. Đo cả dung lượng/giây, file/giây, CPU parse, thời gian chờ DB và hiệu ứng cache.

Nếu dùng remote partitioning, đừng gửi một đường dẫn cục bộ như `C:\batch\input\file.csv` tới worker Linux rồi giả định đọc được. Manager và worker cần hợp đồng địa chỉ chung: shared mount nhất quán, network filesystem, object key/version hoặc một bước staging/tải file riêng. Worker phải đọc **đúng nội dung đã được manifest định danh**, dù đường dẫn local khác nhau.

## 12. Retry, rollback và restart theo file/nhóm

Spring Batch lưu `JobExecution`, `StepExecution` và `ExecutionContext` trong `JobRepository`. Một partition hoàn tất có thể được bỏ qua trong lần restart của cùng JobInstance theo quy tắc step; partition thất bại được chạy tiếp hoặc chạy lại dựa trên trạng thái và cơ chế checkpoint của reader.

### Ba nguồn gây trùng hoặc thiếu phổ biến

1. **File nguồn thay đổi giữa hai lần chạy:** checkpoint được ghi theo số dòng nhưng nội dung đã được chèn/xóa dòng; resume từ vị trí cũ không còn trỏ đúng bản ghi.
2. **Partition name đổi ý nghĩa:** danh sách file được tạo lại theo directory listing mới, khiến `partition3` chỉ tới file khác.
3. **Side effect ngoài transaction:** processor gửi email hoặc writer gọi API ngoài, sau đó chunk rollback; khi retry, tác động ngoài DB có thể lặp.

Hãy bảo vệ bằng:

- **Manifest/nhóm bất biến**: job restart dùng đúng danh sách, thứ tự, phiên bản file.
- **Reader có state bền vững**: tên ItemStream ổn định và dữ liệu nguồn không đổi.
- **Writer idempotent**: unique key theo `batchKey` và record ID logic; upsert hoặc dedup được thiết kế đúng.
- **JobParameters định danh ổn định**: restart đúng JobInstance; tạo parameters mới nghĩa là chạy một JobInstance khác.
- **Đối soát**: nguồn vs kết quả, số record theo file/nhóm và dữ liệu thực; đừng chỉ nhìn `BatchStatus.COMPLETED`.

### Ví dụ failure sau khi một số chunk đã commit

Giả sử `sales-002.csv` chứa 5.000 record, chunk size 200:

~~~text
Worker partition1:
  chunk 1..10: đã commit 2.000 record
  chunk 11: lỗi ghi DB, transaction rollback
  StepExecution: FAILED

Restart cùng JobInstance:
  Đọc lại đúng file đã chốt với checkpoint phù hợp
  Tiếp tục hoặc replay phần cần thiết theo trạng thái
  Writer giữ unique key, không tạo output trùng
  Hoàn tất file -> StepExecution COMPLETED
~~~

Đây là mô hình lý tưởng; số item được đọc lại phụ thuộc reader, vị trí checkpoint, cách Spring Batch khôi phục transaction và có phải input bất biến hay không. Không được giả định luôn restart chính xác tại “dòng 2.001” nếu chưa kiểm chứng implementation và metadata.

### Phân biệt retry và skip

**Retry** dành cho lỗi có thể hồi phục như kết nối DB tạm thời; **skip** dành cho item lỗi theo chính sách dữ liệu được phê duyệt. Một file có nhiều dòng CSV sai định dạng có thể khiến skip count tăng đáng kể: hãy lưu lý do và tọa độ file/dòng. Không nên `skip(Exception.class)` vô điều kiện, vì có thể bỏ qua lỗi mất file hoặc lỗi schema làm job báo thành công sai.

Nếu một file bị hỏng toàn bộ, chính sách có thể là:

- Làm **FAILED** partition để sửa nguồn và restart từ snapshot hợp lệ.
- Đưa file sang khu vực quarantine, ghi trạng thái lỗi và tiếp tục **chỉ khi nghiệp vụ cho phép**, với báo cáo số file bị bỏ qua và quy trình đối soát độc lập.

Đừng xóa hoặc di chuyển file đang được worker khác dùng khi chưa giải quyết vòng đời công việc.

## 13. Các tình huống biên cần thiết kế trước

| Tình huống | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Thư mục không có file | Partitioner trả map rỗng, job không có công việc hoặc kết thúc khác dự kiến | Định nghĩa chính sách batch rỗng, kiểm thử rõ |
| File đang ghi dở | Worker đọc file thiếu, parser lỗi, restart nguồn thay đổi | Dùng tên tạm + tín hiệu hoàn thành + manifest sau khi chốt |
| File bị thay bằng nội dung khác cùng tên | Resume từ số dòng cũ vào dữ liệu mới | Lưu version/checksum, snapshot immutable |
| Một file xuất hiện hai lần trong manifest | Hai worker xử lý cùng input | Dedup theo file identity, từ chối manifest trùng |
| Trùng basename ở hai thư mục | File ID hoặc tên partition bị đè | Dùng định danh tương đối/full key, không chỉ basename |
| Symlink hoặc `../` thoát thư mục nguồn | Đọc file ngoài phạm vi batch | Chuẩn hóa/kiểm tra real path, hạn chế symlink, quyền truy cập tối thiểu |
| Quá nhiều file nhỏ | Tốn thời gian tạo StepExecution và mở file | Nhóm file thành partition có số lượng hợp lý |
| Một file khổng lồ | Chỉ một worker hoạt động hiệu quả | Pre-shard hoặc reader chia record đúng biên |
| Storage chậm hoặc throttle | Tăng thread nhưng throughput giảm | Đo I/O, giới hạn concurrency, cache/staging có kiểm soát |
| Partition restart sau code deploy mới | Định dạng parser/manifest/rules thay đổi | Version hóa input và parser/rules, kiểm chứng tương thích |

**Đường dẫn an toàn và file bất biến là hai yêu cầu khác nhau.** Ngay cả khi `Path.toRealPath()` hợp lệ lúc chia partition, tiến trình ghi nguồn hoặc thay thế symlink vẫn có thể làm nội dung được đọc về sau khác dự kiến. Hợp đồng vận hành phải bảo vệ toàn bộ vòng đời của snapshot.

## 14. Unit test Partitioner và manifest

Với `ManifestFilePartitioner`, kiểm thử unit không cần khởi động JobRepository. Nên kiểm tra file được giao đúng một lần, thứ tự ổn định, input không hợp lệ bị từ chối và `gridSize` được hiểu đúng.

~~~java
@TempDir
Path temp;

@Test
void assignsEveryManifestFileExactlyOnce() throws Exception {
    Path input = Files.createDirectory(temp.resolve("input"));
    Files.writeString(input.resolve("a.csv"), "header\nA,10\n");
    Files.writeString(input.resolve("b.csv"), "header\nB,20\n");
    Path manifest = temp.resolve("manifest.txt");
    Files.writeString(manifest, "a.csv\nb.csv\n");

    Map<String, ExecutionContext> parts =
            new ManifestFilePartitioner(input, manifest).partition(2);

    assertEquals(List.of("partition0", "partition1"),
            new ArrayList<>(parts.keySet()));
    assertEquals("file-00000",
            parts.get("partition0").getString("fileId"));
    assertEquals("file-00001",
            parts.get("partition1").getString("fileId"));
    assertEquals(input.resolve("a.csv").toRealPath().toString(),
            parts.get("partition0").getString("inputPath"));
    assertEquals(input.resolve("b.csv").toRealPath().toString(),
            parts.get("partition1").getString("inputPath"));
}

@Test
void rejectsDuplicateInputFile() throws Exception {
    Path input = Files.createDirectory(temp.resolve("input"));
    Files.writeString(input.resolve("a.csv"), "header\nA,10\n");
    Path manifest = temp.resolve("manifest.txt");
    Files.writeString(manifest, "a.csv\na.csv\n");

    assertThrows(IllegalArgumentException.class,
            () -> new ManifestFilePartitioner(input, manifest)
                    .partition(4));
}

@Test
void rejectsPathTraversal() throws Exception {
    Path input = Files.createDirectory(temp.resolve("input"));
    Path manifest = temp.resolve("manifest.txt");
    Files.writeString(manifest, "../other.csv\n");

    assertThrows(IllegalArgumentException.class,
            () -> new ManifestFilePartitioner(input, manifest)
                    .partition(2));
}
~~~

Các import JUnit 5, Java NIO và Spring Batch được lược bớt. Test đầu yêu cầu `@TempDir` cung cấp thư mục mới cho từng test case. Có thể bổ sung test file không tồn tại, manifest rỗng, đường dẫn tuyệt đối, đường dẫn symlink thoát input root và `gridSize <= 0`.

**Property quan trọng:** khi manifest đã chốt có N file khác nhau, kết quả Partitioner của kiểu một-file-một-partition phải có **N entry**, tập `inputPath` sau chuẩn hóa **không trùng**, và chạy lại với cùng manifest cho **cùng tên partition cùng fileId/inputPath**. Số entry này không phụ thuộc trực tiếp vào `gridSize` của implementation mẫu.

## 15. Integration test: từ file đến dữ liệu kết quả

Chạy integration test với database tương đương production và vài file nhỏ có nội dung chủ động kiểm soát:

1. Tạo ba file CSV: file A có 5 record, file B có 3 record, file C có 4 record. Dùng `orderId` duy nhất theo từng file và một `batchKey` cố định.
2. Tạo manifest chứa chính xác A, B, C theo thứ tự cố định, rồi chạy job với pool hai worker.
3. Kiểm tra manager step và mọi worker StepExecution hoàn tất; xác minh tập `(batchKey, fileId, orderId)` của kết quả khớp **đúng 12 record** đầu vào nếu không filter/skip.
4. Đối chiếu giá trị `netTotal` theo từng record; không chỉ dùng tổng `COUNT(*)`.
5. Thử lỗi có chủ đích sau một hoặc vài chunk đã commit của B, cho job fail rồi restart cùng identifying JobParameters. Kiểm tra A/C đã hoàn tất không bị xử lý lại ngoài chính sách và output không bị nhân đôi.
6. Sửa hoặc thay một file nhưng giữ tên cũ trong môi trường thử nghiệm; xác minh cơ chế snapshot/checksum của ứng dụng **phát hiện input thay đổi**, không silently resume.
7. Với phương án nhiều file/nhóm, kiểm tra thứ tự resource và checkpoint khi lỗi xuất hiện đúng điểm chuyển từ file thứ nhất sang file thứ hai.

Ví dụ truy vấn phát hiện dữ liệu kết quả trùng hoặc thiếu cần dựa vào manifest/snapshot của job. Nếu ingest tạo bảng staging `expected_sale(batch_key, file_id, order_id, expected_net_total)`, có thể đối soát:

~~~sql
-- Các record kỳ vọng chưa có kết quả tương ứng
SELECT e.batch_key, e.file_id, e.order_id
FROM expected_sale AS e
LEFT JOIN normalized_sale AS n
  ON n.batch_key = e.batch_key
 AND n.file_id = e.file_id
 AND n.order_id = e.order_id
WHERE e.batch_key = :batchKey
  AND n.order_id IS NULL;

-- Các record có giá trị khác dữ liệu kỳ vọng
SELECT e.file_id, e.order_id, e.expected_net_total, n.net_total
FROM expected_sale AS e
JOIN normalized_sale AS n
  ON n.batch_key = e.batch_key
 AND n.file_id = e.file_id
 AND n.order_id = e.order_id
WHERE e.batch_key = :batchKey
  AND e.expected_net_total <> n.net_total;
~~~

Nếu nghiệp vụ lọc record hợp lệ hoặc skip dòng lỗi, `expected_sale` phải phản ánh chính sách đó; không thể kết luận dữ liệu bị thiếu chỉ vì tổng số dòng đích nhỏ hơn số dòng input. Primary key chống **hai dòng trùng khóa**, nhưng không tự chứng minh dữ liệu đã được xử lý theo đúng version/rules.

## 16. Vận hành: quan sát theo file, nhóm và worker

Khi có nhiều partition, log chỉ chứa `JobExecutionId` thường chưa đủ. Nên đính kèm `partitionName`, `fileId` hoặc `groupId`, nguồn (đã loại thông tin nhạy cảm), version/digest, `StepExecutionId` và thread/worker node.

| Metric | Câu hỏi vận hành |
| --- | --- |
| File/nhóm đang chờ, đang chạy, hoàn tất, thất bại | Workload còn bao nhiêu? |
| Dung lượng và record count theo file/nhóm | Có worker quá nặng hay không? |
| Read/write/filter/skip/rollback count theo StepExecution | File nào lỗi parse hoặc business rule? |
| Thời gian mở file, parse, ghi, commit | Bottleneck ở filesystem, CPU hay DB? |
| Active threads và executor queue depth | Có thực sự tận dụng concurrency đã cấu hình? |
| Disk throughput, IOPS, network latency, HTTP throttle | Storage có chịu được nhiều worker? |
| DB connection wait, lock wait, SQL batch latency | Writer có cản throughput không? |
| Restart/retry count, checksum mismatch | Có vấn đề tính bền vững hoặc file biến đổi? |

Một dashboard tổng số record/giây có thể che giấu một file lớn đang chạy rất lâu. Hãy xem **phân phối thời gian theo partition** và phần việc của worker chậm nhất. Giảm skew thường giúp nhiều hơn việc tăng vô hạn số thread.

### Runbook khi một worker đọc file thất bại

1. Ghi lại JobExecution/StepExecution, partition, fileId/groupId, manifestId/version và lỗi.
2. Xác minh file có còn thuộc snapshot bất biến và checksum/size khớp không; kiểm tra quyền, mount hoặc object key đúng.
3. Phân biệt lỗi **tạm thời** (network/storage timeout) với lỗi **cố định** (file hỏng, schema CSV sai, nguồn đã bị thay).
4. Kiểm tra chunk đã commit, số record đã ghi và tác động ngoài transaction.
5. Chỉ cho retry/restart với cùng tập nguồn và writer có thể replay an toàn; không tự ý đánh dấu StepExecution COMPLETED trong JobRepository.
6. Đối soát output sau restart rồi mới đóng sự cố hoặc cho downstream tiếp tục.

## 17. Chọn mức song song từ số đo

Giả sử có 800 file và pool bốn thread, `gridSize=4` không có nghĩa job chỉ có bốn partition. Trong ví dụ một-file-một-partition, sẽ có **800 partition được quản lý**, nhưng chỉ khoảng bốn worker đồng thời tùy executor và tài nguyên.

Một ma trận thử nghiệm thực tế:

| Thử nghiệm | Cách chia | Pool | Cần đo |
| --- | --- | --- | --- |
| A | Một file/partition | 1 thread | Baseline, metadata overhead, disk I/O |
| B | Một file/partition | 4 thread | Throughput, storage queue, DB wait |
| C | Một file/partition | 8 thread | Có tăng thêm hay gây throttle/lock? |
| D | Nhóm 20 file/partition | 4 thread | Chi phí điều phối và độ lệch thời gian |
| E | Nhóm theo tổng byte | 4 thread | Thời gian worker chậm nhất |

Với file cỡ tương đối đồng đều và xử lý độc lập, số worker tăng có thể giảm thời gian tổng. Nhưng với file rất nhỏ, nhiều StepExecution và mở file liên tục có thể tốn hơn công việc thực; với file rất lớn, một worker chậm nhất chi phối thời gian hoàn tất.

**Không xem tổng byte là ước lượng tuyệt đối cho thời gian.** Một file CSV nhiều field có thể tốn CPU parse hơn file đơn giản cùng kích thước; một object store có thể throttle khi mở nhiều stream; batch insert vào DB có thể nghẽn ở unique index. Hãy chọn `gridSize`, số nhóm và pool dựa trên các metric nêu ở phần trước.

## 18. Lỗi phổ biến và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Restart bỏ qua nhầm file | Danh sách file thay đổi hoặc partition name không ổn định | Chốt manifest, không thay nội dung/thứ tự khi restart |
| File được xử lý hai lần bởi hai partition | Manifest có đường dẫn trùng hoặc alias/symlink | Canonicalize, dedup và kiểm tra mapping |
| Ghi kết quả trùng sau retry | Writer thiếu unique key/idempotency | Thiết kế khóa record logic và transaction phù hợp |
| Reader resume sai dòng | File đổi nội dung hoặc danh sách MultiResourceReader đổi thứ tự | Snapshot, version/checksum và stable resource order |
| File rỗng hoặc chỉ có header | Không định nghĩa chính sách empty file | Kiểm tra và log; có thể hoàn tất với readCount=0 nếu hợp lệ |
| Job tạo hàng trăm nghìn StepExecution | Một-file-một-partition cho quá nhiều file nhỏ | Nhóm file, cân bằng và giới hạn metadata |
| Một worker làm gần hết thời gian | Nhóm file hoặc thư mục có workload lệch | Chia lại theo byte/record cost và đo critical path |
| Tăng thread làm job chậm | Disk I/O, remote storage, DB pool hoặc CPU quá tải | Giảm concurrency, tối ưu reader/writer, đo bottleneck |
| Worker remote không mở được file | Đường dẫn local chỉ có trên manager | Shared storage/object URI/version, staging trên worker |
| Lỗi parser chỉ xảy ra ở file mới | Schema/encoding/header khác kỳ vọng | Kiểm tra schema version, UTF-8/BOM, định dạng trước khi tạo manifest |

## 19. Bài thực hành cuối bài

Chuẩn bị tập dữ liệu thử gồm ít nhất sáu file CSV:

- Hai file nhỏ, một file rỗng chỉ có header và một file có dòng thiếu dữ liệu.
- Hai file lớn với phân bố record lệch mạnh.
- Hai thư mục khác nhau cùng có file tên `sales.csv`.
- Manifest bất biến cho một `batchKey`, có thứ tự và checksum được ghi nhận.

Thực hiện các lượt chạy:

1. **Một file/partition:** xây job theo phần 5–7, dùng pool hai rồi bốn thread, kiểm tra mọi file được đọc đúng nguồn.
2. **Một thư mục/partition:** chuyển sang `MultiResourceItemReader`, bảo đảm resource list và thứ tự bất biến; so sánh metadata và thời gian.
3. **Nhóm theo size:** lập các nhóm cân bằng trên cùng manifest, so sánh thời gian worker chậm nhất và throughput.
4. **Failure test:** làm một worker fail sau một số chunk đã commit rồi restart với cùng JobInstance, xác minh dữ liệu không bị trùng/thiếu.
5. **Negative test:** cố thêm file vào thư mục và thay đổi một file sau khi manifest đã chốt; kiểm tra quy trình phát hiện thay đổi và không tự xử lý dữ liệu ngoài snapshot.
6. **Đối soát:** so sánh tập record kỳ vọng với output, cả business value và các side effect khác nếu có.

### Checklist trước khi triển khai production

- [ ] File được công bố hoàn chỉnh trước khi manager tạo manifest.
- [ ] Manifest có định danh/version bền vững, bất biến qua restart; thứ tự và ánh xạ partition cố định.
- [ ] Đường dẫn được chuẩn hóa, xác nhận nằm trong phạm vi nguồn; symlink/quyền truy cập được kiểm soát.
- [ ] Worker có reader theo `@StepScope`, InputStream/ItemStream được đóng và checkpoint phù hợp.
- [ ] Nếu partition chứa nhiều file, danh sách resource, comparator và thứ tự đọc được chốt.
- [ ] Writer dùng unique key/idempotency theo nghiệp vụ; retry không lặp side effect ngoài transaction.
- [ ] Đã kiểm thử file rỗng, file lỗi, duplicate, directory skew, file đổi sau snapshot và restart giữa chunk.
- [ ] Đã đo JobRepository overhead, storage IOPS, network, CPU, DB pool, thời gian partition chậm nhất.
- [ ] Đã lựa chọn một-file-một-partition, một-thư-mục-một-partition hoặc nhóm file theo số đo thực.

**Ghi nhớ:** Partitioner chia theo file hoặc thư mục giúp tận dụng những đơn vị dữ liệu đã tồn tại trên storage để mở rộng Spring Batch. Muốn hệ thống đúng và có thể restart, phải **đóng băng tập nguồn, giữ ổn định partition name và resource order, quản lý checkpoint và ghi idempotent**. Muốn mở rộng hiệu quả, cần chia workload cân bằng theo chi phí thực và giới hạn concurrency dựa trên filesystem/object store, CPU, JobRepository và database chứ không chỉ dựa vào số lượng file.
