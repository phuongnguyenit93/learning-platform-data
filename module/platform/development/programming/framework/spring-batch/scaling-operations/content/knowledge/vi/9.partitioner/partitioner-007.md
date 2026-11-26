# Chia theo tenant hoặc vùng nghiệp vụ

**Chia theo tenant hoặc vùng nghiệp vụ (tenant/business-domain partitioning)** là chiến lược phân phối công việc Spring Batch theo **ranh giới có ý nghĩa trong mô hình dữ liệu**, chẳng hạn tenant, cửa hàng, khu vực bán hàng, pháp nhân, loại nghiệp vụ hoặc cặp `(tenant, region)`. Thay vì cắt một bảng thành các khoảng ID thuần túy, manager xác định từng tập dữ liệu thuộc quyền xử lý của một worker, đặt thông tin đó vào `ExecutionContext` rồi khởi chạy các **worker StepExecution** độc lập. Chiến lược này đặc biệt hữu ích khi các tenant hoặc vùng có chính sách, khóa dữ liệu và giới hạn tài nguyên khác nhau.

Bài học nằm trong chương **Partitioner** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module tập trung mở rộng Spring Batch cho workload dữ liệu lớn thông qua multi-threaded step, parallel steps, partitioning và các mô hình phân tán, đồng thời đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và lựa chọn kiến trúc theo tài nguyên thực tế. Chủ đề này nhấn mạnh **tính độc lập dữ liệu theo miền nghiệp vụ, bảo vệ ranh giới tenant, cân bằng tải khi phân bố dữ liệu lệch và restart theo một kế hoạch phân vùng ổn định**.

## 1. Mục tiêu học tập

Sau bài này, bạn cần:

1. Phân biệt partition **theo tenant**, **theo vùng nghiệp vụ**, **theo tenant kết hợp vùng** và **chia theo khóa chính**.
2. Xác định các **bất biến về quyền sở hữu dữ liệu**: mỗi record hợp lệ thuộc đúng một partition trong snapshot và không có worker nào được ghi sang tenant khác.
3. Thiết kế **manifest phân vùng bất biến**, ánh xạ `partitionName` với `tenantId`, `regionCode`, `snapshotId` và `batchKey`.
4. Cài đặt `Partitioner` bằng Spring Batch 5.x và worker `@StepScope` dùng `JdbcPagingItemReader`, processor stateless, writer idempotent.
5. Giải thích vì sao chỉ truyền `tenantId` vào `ExecutionContext` **không đủ** để bảo đảm cách ly dữ liệu và an toàn bảo mật.
6. Chọn cách chia tiếp tenant lớn, ngăn **noisy neighbor**, điều tiết connection/API quota và đo throughput theo từng nhóm.
7. Kiểm thử cross-tenant leakage, bản ghi chuyển vùng, tenant rỗng, retry/restart và tình huống một worker thất bại trong khi worker khác đã commit.

**Tình huống xuyên suốt:** nền tảng thương mại phục vụ 80 tenant. Mỗi tenant có đơn hàng theo `north`, `central`, `south`; một số tenant có vài trăm đơn mỗi ngày, trong khi hai tenant lớn xử lý hàng triệu đơn. Job cuối ngày cần chuẩn hóa tổng tiền của tất cả tenant đã được chốt dữ liệu, nhưng không được để kết quả, log hoặc side effect của tenant A lọt sang tenant B.

## 2. Ranh giới kỹ thuật và ranh giới nghiệp vụ

Một **partition** trong Spring Batch là **đơn vị điều phối**: một entry trong `Map<String, ExecutionContext>` sinh ra một worker StepExecution. Nó không tự tạo isolation về database hay bảo mật. **Tenant** là ranh giới sở hữu dữ liệu và quyền truy cập; **region** là một thuộc tính nghiệp vụ có thể đại diện chi nhánh, thị trường, khu vực giao hàng hoặc đơn vị kế toán.

| Chiến lược | Khóa phân vùng | Thường phù hợp khi | Rủi ro cần xử lý |
| --- | --- | --- | --- |
| Theo tenant | `tenant_id` | Tenant độc lập, SLA/quota khác nhau | Tenant lớn hơn hẳn các tenant khác |
| Theo vùng | `region_code` | Dữ liệu tổ chức theo khu vực, nghiệp vụ độc lập theo vùng | Một region chứa nhiều tenant; thiếu điều kiện tenant có thể lộ dữ liệu |
| Theo cặp tenant–vùng | `(tenant_id, region_code)` | Cần cả isolation theo tenant lẫn chia nhỏ workload | Vùng thay đổi khi job đang chạy; bản ghi có thể bị xử lý hai nơi |
| Theo business key | `(tenant_id, account_id)` hoặc nhóm khóa | Cần giữ thứ tự hoặc transaction theo tài khoản | Số nhóm quá lớn, tải giữa account không đều |
| Tenant–vùng–bucket | `(tenant_id, region_code, bucket_id)` | Một tenant–vùng quá lớn cần nhiều worker | Thuật toán bucket phải ổn định khi restart |

**Ví dụ:** hai tenant đều có vùng `north`. Nếu reader lọc duy nhất `WHERE region_code = 'north'`, worker của tenant A có thể đọc cả record của B. Vì vậy, khi miền dữ liệu được sở hữu theo tenant, predicate phải gắn với **tenantId và regionCode**, không chỉ tên vùng.

### Một partition không phải một transaction

Worker vẫn là một StepExecution có thể đọc hàng triệu record theo chunk, ví dụ 200 item/transaction. Một partition có nhiều lần commit; worker lỗi giữa chừng không thể tự động rollback những chunk đã commit trước đó. Chính sách restart và writer idempotent vì thế vẫn bắt buộc.

## 3. Đặt mô hình trong kiến trúc Spring Batch

`Partitioner.partition(gridSize)` đọc một **kế hoạch phân vùng đã chốt** và trả về map. `PartitionHandler` hoặc cấu hình partitioned manager step điều phối các worker:

~~~mermaid
flowchart TD
    S["Snapshot dữ liệu + Manifest bất biến"] --> M["Manager Step"]
    M --> P["TenantRegionPartitioner"]
    P --> A["partition001: tenant A / north"]
    P --> B["partition002: tenant A / south"]
    P --> C["partition003: tenant B / north"]
    P --> D["partition004: tenant C / central"]
    A --> W1["Worker StepExecution 001"]
    B --> W2["Worker StepExecution 002"]
    C --> W3["Worker StepExecution 003"]
    D --> W4["Worker StepExecution 004"]
    W1 --> DB[("Output có tenant_id")]
    W2 --> DB
    W3 --> DB
    W4 --> DB
~~~

Sơ đồ là một **kế hoạch ví dụ**, không giả định mọi tenant có đủ ba vùng hay một vùng chỉ có một tenant. Các partition có thể chạy đồng thời ở nhiều thread trong cùng JVM (**local partitioning**) hoặc qua middleware đến các worker khác (**remote partitioning**).

**Các khái niệm cần tách bạch:**

- `gridSize` là số partition được đề nghị hoặc thông số điều phối tùy `Partitioner`; không mặc định bằng số tenant hay số worker.
- **Số entry trong manifest** quyết định số partition mà implementation ở bài này tạo. Có thể nhiều hơn hoặc ít hơn `gridSize`.
- **Thread pool/worker concurrency** quyết định số partition thực thi đồng thời, giới hạn bởi CPU/DB/API và các tác vụ cạnh tranh khác.
- **Chunk size** là số item mỗi transaction của worker, không phải số tenant hoặc số region mỗi partition.
- **JobRepository** lưu `JobExecution`, `StepExecution`, `ExecutionContext`; metadata của partition giúp kiểm tra và restart, nhưng không thay thế ràng buộc quyền truy cập trong DB.

## 4. Định nghĩa bất biến: không trùng, không thiếu, không lẫn tenant

Trước khi viết code, hãy xác định tập dữ liệu logic cần xử lý:

~~~text
S = {record thuộc snapshot X, được phép xử lý trong batch B}

owner(record) = (tenantId, regionCode)

partition(record) = đúng một entry trong manifest B
~~~

Một thiết kế đúng cần các **bất biến**:

1. **Coverage:** mọi record hợp lệ trong snapshot được giao cho **đúng một partition**.
2. **Non-overlap:** hai partition không cùng sở hữu một record của snapshot.
3. **Tenant isolation:** worker của tenant A không đọc hoặc ghi record của tenant B, kể cả khi cùng `regionCode` hoặc `orderId`.
4. **Identity stability:** tên partition, tenant, region, snapshot và quy tắc chia giữ nguyên trên các lần restart cùng JobInstance.
5. **Replay safety:** retry/restart không tạo thêm tác động nghiệp vụ ngoài ý muốn; writer sử dụng khóa idempotency đúng phạm vi tenant.
6. **Tenant fairness:** một tenant lớn không mặc nhiên lấy hết connection pool, API quota hoặc thời gian phục vụ các tenant nhỏ nếu SLA yêu cầu sự công bằng.

**Tập khóa đầu vào và đầu ra phải được đối soát theo cặp `(tenantId, businessId)`**, không theo `businessId` đơn lẻ nếu mã đơn hàng có thể lặp giữa các tenant.

### Region không phải lúc nào cũng là một phép chia

Một đơn có thể vừa thuộc vùng bán hàng `north`, vừa thuộc vùng giao vận `south`. Nếu tạo partition theo cả hai loại vùng trên cùng job mà không định nghĩa **một quy tắc owner duy nhất**, đơn ấy có thể được xử lý hai lần. Hãy chọn **một dimension phân vùng chính** cho mỗi snapshot hoặc tạo **mapping record → partition** bền vững với constraint duy nhất.

Nếu nghiệp vụ muốn một record đóng góp vào nhiều vùng báo cáo, đó là **fan-out có chủ đích**, không phải non-overlap partitioning: cần xác định khóa kết quả có thêm `reportDimension` và kiểm soát double counting.

## 5. Manifest và snapshot: nền tảng để restart

Không nên để Partitioner truy vấn bảng tenant/vùng **đang thay đổi** mỗi khi chạy lại, rồi gán `partition0`, `partition1` theo thứ tự mới. Một tenant/vùng mới thêm vào có thể dịch chỉ số partition và làm Spring Batch hiểu sai StepExecution đã hoàn tất.

Thay vào đó, hãy **chốt một kế hoạch công việc** trước manager step:

1. Xác định `batchKey` và `snapshotId` cố định.
2. Chụp hoặc stage các record nguồn cùng `tenantId`, `regionCode` đã được tính theo **quy tắc phiên bản cố định**.
3. Liệt kê các cặp `(tenantId, regionCode)` có công việc, hoặc những vùng no-op được phép theo chính sách.
4. Gán `partitionKey` ổn định như `p00001`, `p00002`, lưu vào bảng manifest. Tránh đặt tên bằng chuỗi tenant chưa được chuẩn hóa vì có thể trùng, chứa ký tự không an toàn hoặc tiết lộ danh tính khách hàng trong log.
5. Công bố manifest/snapshot **bất biến**. Trong lần restart, dùng lại đúng bảng staging và manifest đó, không tính lại phân vùng từ live source.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE staged_order (
    snapshot_id  VARCHAR(100) NOT NULL,
    tenant_id    VARCHAR(80) NOT NULL,
    region_code  VARCHAR(40) NOT NULL,
    order_id     BIGINT NOT NULL,
    gross_total  NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (snapshot_id, tenant_id, order_id)
);

CREATE INDEX idx_staged_order_owner
    ON staged_order (snapshot_id, tenant_id, region_code, order_id);

CREATE TABLE partition_manifest (
    batch_key     VARCHAR(100) NOT NULL,
    partition_key VARCHAR(40) NOT NULL,
    snapshot_id   VARCHAR(100) NOT NULL,
    tenant_id     VARCHAR(80) NOT NULL,
    region_code   VARCHAR(40) NOT NULL,
    estimated_rows BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (batch_key, partition_key),
    UNIQUE (batch_key, tenant_id, region_code)
);

CREATE TABLE normalized_order (
    batch_key    VARCHAR(100) NOT NULL,
    tenant_id    VARCHAR(80) NOT NULL,
    order_id     BIGINT NOT NULL,
    region_code  VARCHAR(40) NOT NULL,
    net_total    NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (batch_key, tenant_id, order_id)
);
~~~

Trong mô hình này, một order thuộc **một tenant và một region** trong snapshot; `PRIMARY KEY(snapshot_id, tenant_id, order_id)` đảm bảo không có cùng order ở hai region trong cùng snapshot. Nếu dữ liệu thực sự cho phép một order thuộc nhiều region, phải thay đổi mô hình dữ liệu và ý nghĩa công việc trước khi áp dụng nguyên xi ràng buộc này.

Ví dụ manifest:

| partition_key | snapshot_id | tenant_id | region_code | estimated_rows |
| --- | --- | --- | --- | ---: |
| `p00001` | `snap-20261126` | `tenant-a` | `north` | 1.200.000 |
| `p00002` | `snap-20261126` | `tenant-a` | `south` | 340.000 |
| `p00003` | `snap-20261126` | `tenant-b` | `north` | 250 |
| `p00004` | `snap-20261126` | `tenant-c` | `central` | 18.000 |

**estimated_rows** chỉ là thông tin lập lịch/đo tải, không phải số item mà framework tự động đọc hoặc điều kiện để hoàn thành. Cần kiểm tra catalog và staging nhất quán **trước khi** manager bắt đầu. Nếu một tenant/vùng đã chốt có số row bằng 0, có thể không sinh partition hoặc sinh no-op có chủ đích; đừng coi rỗng là lỗi dữ liệu nếu nghiệp vụ cho phép.

## 6. Cài đặt TenantRegionPartitioner

Trong Spring Batch 5.x, interface `org.springframework.batch.core.partition.support.Partitioner` có phương thức `partition(int gridSize)`, trả `Map<String, ExecutionContext>`. Ta đọc **manifest bất biến**, không tự tìm tenant từ bảng live.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.jdbc.core.JdbcTemplate;

public final class TenantRegionPartitioner implements Partitioner {
    private final JdbcTemplate jdbc;
    private final String batchKey;

    public TenantRegionPartitioner(JdbcTemplate jdbc, String batchKey) {
        this.jdbc = jdbc;
        this.batchKey = batchKey;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be > 0");
        }

        var entries = jdbc.query("""
                SELECT partition_key, snapshot_id, tenant_id, region_code
                FROM partition_manifest
                WHERE batch_key = ?
                ORDER BY partition_key
                """,
                (rs, rowNum) -> new ManifestEntry(
                        rs.getString("partition_key"),
                        rs.getString("snapshot_id"),
                        rs.getString("tenant_id"),
                        rs.getString("region_code")),
                batchKey);

        if (entries.isEmpty()) {
            throw new IllegalStateException(
                    "No frozen partitions for batch " + batchKey);
        }

        Map<String, ExecutionContext> result = new LinkedHashMap<>();
        for (ManifestEntry entry : entries) {
            ExecutionContext context = new ExecutionContext();
            context.putString("snapshotId", entry.snapshotId());
            context.putString("tenantId", entry.tenantId());
            context.putString("regionCode", entry.regionCode());

            ExecutionContext previous =
                    result.putIfAbsent(entry.partitionKey(), context);
            if (previous != null) {
                throw new IllegalStateException(
                        "Duplicate partition key: " + entry.partitionKey());
            }
        }
        return result;
    }

    private record ManifestEntry(
            String partitionKey,
            String snapshotId,
            String tenantId,
            String regionCode) {}
}
~~~

**Đặc điểm cần hiểu:**

- `gridSize` được kiểm tra nhưng **không quy định số entry** trong bản triển khai này. Một entry manifest tạo một partition, dù executor có ít thread hơn.
- `partitionKey` phải được tạo bền vững trong bước chuẩn bị. `ORDER BY partition_key` cho map ổn định, nhưng **không có cam kết thứ tự thực thi hoặc hoàn tất worker**.
- `ExecutionContext` chỉ chứa metadata nhỏ, serializable. Không nhét cả tập order hoặc credentials nhạy cảm vào đó.
- Mọi trường `snapshotId`, `tenantId`, `regionCode` cần khác null và phải qua bước kiểm tra manifest; không được để chuỗi trống ngầm có nghĩa “mọi tenant”.
- Nếu manifest thay đổi sau khi job chạy, một lần `partition()` khác có thể trả vùng khác; đây là **vi phạm hợp đồng snapshot** chứ không phải cơ chế Spring Batch tự sửa.

Ở production, có thể thêm `manifestVersion` và checksum hoặc lưu trực tiếp ánh xạ partition bất biến trong metadata bền vững; xây dựng/kiểm tra manifest là bước riêng, không làm lại tùy ý bên trong Partitioner.

## 7. Reader: lọc đủ tenant, region và snapshot

Worker nhận `tenantId`, `regionCode` và `snapshotId` từ `stepExecutionContext`. Ví dụ reader dùng `JdbcPagingItemReader`, sắp xếp bằng `order_id` vốn là khóa duy nhất **trong cặp snapshot–tenant–region** theo schema đã chốt.

~~~java
record StagedOrder(
        String tenantId,
        String regionCode,
        long orderId,
        BigDecimal grossTotal) {}

record NormalizedOrder(
        String tenantId,
        String regionCode,
        long orderId,
        BigDecimal netTotal) {}

@Bean
@StepScope
JdbcPagingItemReader<StagedOrder> tenantRegionReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['snapshotId']}") String snapshotId,
        @Value("#{stepExecutionContext['tenantId']}") String tenantId,
        @Value("#{stepExecutionContext['regionCode']}") String regionCode) {

    return new JdbcPagingItemReaderBuilder<StagedOrder>()
            .name("tenantRegionReader")
            .dataSource(dataSource)
            .selectClause("""
                    SELECT tenant_id, region_code, order_id, gross_total
                    """)
            .fromClause("FROM staged_order")
            .whereClause("""
                    WHERE snapshot_id = :snapshotId
                      AND tenant_id = :tenantId
                      AND region_code = :regionCode
                    """)
            .sortKeys(Map.of("order_id", Order.ASCENDING))
            .parameterValues(Map.of(
                    "snapshotId", snapshotId,
                    "tenantId", tenantId,
                    "regionCode", regionCode))
            .rowMapper((rs, rowNum) -> new StagedOrder(
                    rs.getString("tenant_id"),
                    rs.getString("region_code"),
                    rs.getLong("order_id"),
                    rs.getBigDecimal("gross_total")))
            .pageSize(200)
            .saveState(true)
            .build();
}
~~~

**Ba điều quan trọng nhất về cách ly dữ liệu:**

1. Worker truy vấn theo **cả ba khóa** `snapshot_id`, `tenant_id`, `region_code`; không chỉ theo `region_code`.
2. `@StepScope` tạo **reader riêng theo StepExecution**, nên trạng thái paging/checkpoint của tenant A không bị chia sẻ với worker của B. Scope không tự bảo vệ các singleton service khác.
3. `sortKeys` phải tạo **thứ tự duy nhất và ổn định** trong tập đọc; nếu cùng `order_id` được phép lặp trong một vùng, cần sort key kết hợp hoặc khóa record khác.

`saveState(true)` chỉ hữu ích khi nguồn staging không bị thay đổi giữa các lần restart. Nếu order chuyển vùng khi job đang chạy nhưng worker đọc dữ liệu live thay vì snapshot, một record có thể bị hai worker xử lý hoặc không worker nào nhận.

### Kiểm tra trực tiếp điều kiện SQL

~~~sql
SELECT order_id, gross_total
FROM staged_order
WHERE snapshot_id = :snapshot_id
  AND tenant_id = :tenant_id
  AND region_code = :region_code
ORDER BY order_id;
~~~

Với index `(snapshot_id, tenant_id, region_code, order_id)`, DB có thể thực hiện truy vấn vùng tương đối hiệu quả. Hãy kiểm tra execution plan trên DB thật; không khẳng định một index luôn là tối ưu cho mọi độ phân bố tenant và kiểu workload.

## 8. Processor và writer: giữ tenant identity đến đầu ra

Processor nên **stateless** và giữ tenant/region trong output. Đây cũng là cách đơn giản để phát hiện phép biến đổi làm mất thông tin sở hữu:

~~~java
@Bean
ItemProcessor<StagedOrder, NormalizedOrder> normalizeOrder() {
    return row -> {
        if (row.grossTotal() == null ||
                row.grossTotal().signum() < 0) {
            throw new IllegalArgumentException(
                    "Invalid amount for order " + row.orderId());
        }
        return new NormalizedOrder(
                row.tenantId(),
                row.regionCode(),
                row.orderId(),
                row.grossTotal().setScale(2, RoundingMode.HALF_UP));
    };
}
~~~

Writer theo `@StepScope` nhận định danh tenant/region của **partition hiện tại**, kiểm tra output không mang tenant/region khác, rồi ghi theo khóa kết quả `(batch_key, tenant_id, order_id)`:

~~~java
@Bean
@StepScope
JdbcBatchItemWriter<NormalizedOrder> normalizedOrderWriter(
        DataSource dataSource,
        @Value("#{jobParameters['batchKey']}") String batchKey,
        @Value("#{stepExecutionContext['tenantId']}") String tenantId,
        @Value("#{stepExecutionContext['regionCode']}") String regionCode) {

    return new JdbcBatchItemWriterBuilder<NormalizedOrder>()
            .dataSource(dataSource)
            .sql("""
                 INSERT INTO normalized_order(
                     batch_key, tenant_id, order_id, region_code, net_total)
                 VALUES (
                     :batchKey, :tenantId, :orderId, :regionCode, :netTotal)
                 ON CONFLICT (batch_key, tenant_id, order_id)
                 DO UPDATE SET
                     region_code = EXCLUDED.region_code,
                     net_total = EXCLUDED.net_total
                 """)
            .itemSqlParameterSourceProvider(item -> {
                if (!tenantId.equals(item.tenantId())
                        || !regionCode.equals(item.regionCode())) {
                    throw new IllegalStateException(
                            "Cross-partition ownership violation");
                }
                return new MapSqlParameterSource()
                        .addValue("batchKey", batchKey)
                        .addValue("tenantId", tenantId)
                        .addValue("regionCode", regionCode)
                        .addValue("orderId", item.orderId())
                        .addValue("netTotal", item.netTotal());
            })
            .build();
}
~~~

**Tại sao khóa chứa `tenant_id`?** Hai tenant có thể cùng một `order_id`. Nếu output chỉ dùng `order_id` làm primary key, writer của tenant B có thể ghi đè dữ liệu tenant A dù reader đã lọc đúng.

UPSERT khiến phát lại một item không tạo thêm dòng, nhưng **không tự bảo đảm kết quả bằng nhau** nếu giá trị, region hoặc phiên bản quy tắc thay đổi. Khi cùng khóa `(batchKey, tenantId, orderId)` phát sinh ở region khác, `DO UPDATE` có thể che giấu lỗi di chuyển vùng; trong môi trường yêu cầu nghiêm ngặt, dùng version/snapshot check và **fail on mismatch** thay vì tự ghi đè.

Nếu nghiệp vụ cần tích lũy tiền hoặc trừ tồn kho, một lệnh `UPDATE total = total + delta` **không idempotent** khi chunk bị replay. Dùng operation ID duy nhất, kiểm tra dedup trong cùng transaction hoặc thiết kế phép ghi kết quả mang tính quyết định từ snapshot.

## 9. Ghép manager và worker Step trong local partitioning

Ví dụ Spring Batch 5.x, Java 17+, với JobRepository, JdbcTemplate, DataSource và PlatformTransactionManager đã cấu hình hợp lệ:

~~~java
@Bean
@StepScope
Partitioner tenantRegionPartitioner(
        JdbcTemplate jdbcTemplate,
        @Value("#{jobParameters['batchKey']}") String batchKey) {
    return new TenantRegionPartitioner(jdbcTemplate, batchKey);
}

@Bean
Step tenantRegionWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        @Qualifier("tenantRegionReader") ItemReader<StagedOrder> reader,
        @Qualifier("normalizeOrder")
                ItemProcessor<StagedOrder, NormalizedOrder> processor,
        @Qualifier("normalizedOrderWriter")
                ItemWriter<NormalizedOrder> writer) {

    return new StepBuilder("tenantRegionWorkerStep", jobRepository)
            .<StagedOrder, NormalizedOrder>chunk(200, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}

@Bean
ThreadPoolTaskExecutor tenantRegionExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("tenant-region-");
    executor.initialize();
    return executor;
}

@Bean
Step tenantRegionManagerStep(
        JobRepository jobRepository,
        @Qualifier("tenantRegionWorkerStep") Step workerStep,
        @Qualifier("tenantRegionPartitioner") Partitioner partitioner,
        @Qualifier("tenantRegionExecutor") TaskExecutor executor) {

    return new StepBuilder("tenantRegionManagerStep", jobRepository)
            .partitioner(workerStep.getName(), partitioner)
            .step(workerStep)
            .gridSize(4)
            .taskExecutor(executor)
            .build();
}

@Bean
Job tenantRegionJob(
        JobRepository jobRepository,
        @Qualifier("tenantRegionManagerStep") Step managerStep) {
    return new JobBuilder("tenantRegionJob", jobRepository)
            .start(managerStep)
            .build();
}
~~~

Trong ví dụ:

- Manager dùng manifest hiện tại của `batchKey` và tạo một partition cho mỗi entry.
- Mỗi worker StepExecution nhận chính xác một bộ `(snapshotId, tenantId, regionCode)` qua `ExecutionContext`.
- Reader và writer `@StepScope` gắn với worker StepExecution, tránh chia sẻ state paging hoặc context giữa các partition.
- `gridSize=4` không buộc Partitioner chỉ trả bốn entry; executor có bốn thread, số partition có thể lớn hơn nhiều.
- `chunk(200)` xác định kích thước xử lý theo transaction của **mỗi** worker; không phải một transaction cho toàn tenant.

Đây là cấu hình **local partitioning**. Để dùng remote partitioning, cần thay cách điều phối bằng cơ chế Spring Batch Integration/PartitionHandler phù hợp, bảo đảm mọi worker truy cập snapshot và JobRepository nhất quán, và xử lý các lỗi gửi/nhận thông điệp. Không chỉ đổi `TaskExecutor` thành một connection tới broker là hoàn thành chuyển đổi.

## 10. Cách ly tenant: không chỉ là thêm WHERE tenant_id

Vì một worker có thể mang dữ liệu khách hàng, **tenant isolation là yêu cầu bảo mật và correctness**, không chỉ là tối ưu query. Có nhiều lớp phòng vệ:

| Lớp | Cơ chế | Điều cần kiểm tra |
| --- | --- | --- |
| Manifest | Worker chỉ nhận tenant/region được job phê duyệt | Tenant thuộc batch được phép xử lý, không có partition ngoài phạm vi |
| SQL reader | Predicate gồm `snapshot_id`, `tenant_id`, `region_code` | Không trả row ngoài owner partition |
| Processor | Không đổi `tenantId` ngoài quy tắc nghiệp vụ rõ | Không lộ dữ liệu qua cache, log hoặc service dùng chung |
| Writer | Kiểm tra owner của item, key kết quả gồm tenant | Không ghi chéo tenant; constraint phù hợp |
| DB policy | Row-level security hoặc database/schema riêng theo tenant khi yêu cầu | Worker có quyền tối thiểu và policy hoạt động đúng |
| Quan sát | Log/correlation ID đủ truy vết, hạn chế thông tin nhạy cảm | Không để PII hoặc secret tenant trong log/metrics |

**Ví dụ lỗi ngầm:** một service singleton có field `currentTenantId`, worker A đặt `tenant-a` rồi worker B đặt `tenant-b`. Khi A tiếp tục gọi service, nó có thể dùng tenant B. Cách khắc phục là **truyền tenant identity rõ ràng qua tham số**, hoặc dùng đối tượng context bất biến theo lời gọi. Không dùng field mutable toàn cục làm nguồn sự thật.

### ThreadLocal và SecurityContext

`ThreadLocal` có thể được tái sử dụng giữa các chunk/worker vì thread pool tái sử dụng thread. Nếu kiến trúc dùng tenant context trên thread, phải **thiết lập và dọn trong `try/finally`**, kiểm tra context propagation khi có async và không dùng nó thay cho câu SQL giới hạn quyền truy cập. Một lựa chọn đáng tin hơn là để tenant ID nằm trong `ExecutionContext`, input và tham số repository rõ ràng, kết hợp quyền DB tối thiểu.

### Row-level security và connection pool

Với DB hỗ trợ row-level security, có thể thêm lớp bảo vệ độc lập. Tuy nhiên, chính sách dựa trên session variable phải xét **connection được tái sử dụng qua pool**; không để một connection mang tenant context cũ sang transaction của tenant khác. Nếu dùng PostgreSQL, thiết kế session/transaction-local context theo thời điểm transaction và connection thực, rồi có test cross-tenant. Không dùng câu `SET tenant_id` giả định mọi connection luôn gắn với một thread cố định.

Nếu tenant sử dụng **database riêng**, `tenantId` trong `ExecutionContext` chưa đủ để mở được datasource; cần routing datasource được kiểm soát, cấp credential đúng tenant, cơ chế transaction phù hợp và giới hạn kết nối theo tenant. Không lưu plaintext credential vào JobParameters/ExecutionContext vì có thể được ghi trong JobRepository.

## 11. Tenant lớn, region lệch và chiến lược chia tiếp

Với bảng ví dụ, `tenant-a/north` có 1,2 triệu row còn `tenant-b/north` chỉ có 250 row. Nếu một partition tương ứng mỗi cặp tenant–region, worker xử lý `tenant-a/north` có thể chạy lâu sau khi những worker khác đã xong, làm **mất lợi ích mở rộng**.

### Cách 1 — Tạo nhiều partition nhỏ hơn số worker

Nếu có 50 cặp tenant–region và pool 4 thread, mỗi worker có thể lấy một vùng mới sau khi xong vùng trước. Điều này giúp giảm thời gian rảnh ở các worker nhưng vẫn không chia nhỏ **cặp lớn nhất**.

### Cách 2 — Chia tenant lớn theo bucket hoặc khóa chính

Với một tenant–region quá nặng, có thể thêm `bucketId` vào owner:

~~~text
owner = (tenantId, regionCode, bucketId)

tenant-a / north / bucket-0
tenant-a / north / bucket-1
tenant-a / north / bucket-2
tenant-a / north / bucket-3
~~~

Quy tắc `bucketId` phải **deterministic và bất biến trong snapshot**, chẳng hạn `floorMod(hash(orderId), bucketCount)`, và `bucketCount` phải được chốt cho JobInstance. Tuy nhiên, lọc SQL bằng hàm hash/modulo trên cột thường có thể khiến DB không tận dụng range index tốt; một cách hiệu quả hơn ở workload lớn là **ghi bucket_id vào bảng staging** rồi index `(snapshot_id, tenant_id, region_code, bucket_id, order_id)`.

Khi chuyển sang hybrid partitioning, đổi schema manifest từ `UNIQUE(batch_key, tenant_id, region_code)` thành `UNIQUE(batch_key, tenant_id, region_code, bucket_id)` và thêm `bucketId` vào worker reader. **Không chỉ tạo hai partition cho cùng cặp tenant–region rồi giữ nguyên câu SQL**, vì khi đó cả hai worker sẽ đọc cùng toàn bộ dữ liệu.

### Cách 3 — Chia theo business key cần thứ tự

Nếu hai giao dịch cùng tài khoản phải được xử lý có thứ tự, chia ngẫu nhiên theo `orderId` có thể đưa chúng sang hai worker và phá bất biến. Khi đó **partition theo account/merchant/customer ID** (hoặc một consistent hash ổn định của account) thường phù hợp hơn. Việc chia phải dựa trên **đơn vị có thể xử lý độc lập**, không chỉ số dòng.

| Kiểu workload | Hướng chia phù hợp | Rủi ro cần cân nhắc |
| --- | --- | --- |
| Nhiều tenant nhỏ, tải gần đều | Một tenant/partition | Overhead nếu số tenant cực lớn |
| Mỗi tenant có vài region tương đối cân | Một tenant–region/partition | Chi phí và quy tắc owner khi vùng thay đổi |
| Một tenant chiếm đa số dữ liệu | Tenant–region–bucket hoặc PK range trong tenant | Phải thêm predicate bucket/range thật vào reader |
| Nhiều tenant dùng chung quota API | Nhóm theo tenant và giới hạn đồng thời theo tenant | TaskExecutor chung không tự bảo đảm fairness |
| Nghiệp vụ cần xử lý tuần tự theo tài khoản | Partition theo account key | Cardinality cao, hotspot account lớn |

## 12. Fairness, noisy neighbor và backpressure

**Noisy neighbor** là tình huống tenant có workload lớn chiếm phần lớn CPU, connection pool, I/O, thread hoặc API quota, khiến tenant khác bị trễ. Partitioning theo tenant tạo cơ hội quan sát và điều tiết độc lập, nhưng **không tự thực thi quota**.

Biện pháp thực tế:

- **Giới hạn worker đồng thời toàn job:** pool/executor có kích thước đo được; không tạo thread vô hạn tương ứng số tenant.
- **Giới hạn theo tenant nếu SLA yêu cầu:** phân luồng queue có trọng số, semaphore/quota, hoặc lịch chạy tenant riêng. Nếu dùng semaphore trong worker, phải release trong `finally` và không giữ lock quá thời gian cần thiết.
- **Cân bằng thứ tự lập lịch:** ưu tiên nhóm nhỏ để giảm tail latency hoặc dùng weighted fair scheduling; thứ tự map từ Partitioner không bảo đảm một chính sách scheduling/công bằng cứng.
- **Tách workload đòi SLA khác nhau:** một job/queue cho tenant premium và một job/queue cho tác vụ nền có thể dễ quản lý hơn gộp tất cả vào một split.
- **Đo pool và downstream:** DB connection wait, lock, API 429, broker backlog và thời gian chờ theo tenant.

Đừng đặt `gridSize=80` rồi suy ra hệ thống có **80 tenant đang chạy đồng thời**. Với thread pool 4, thông thường tối đa một số nhỏ StepExecution chạy đồng thời. Khi nhiều partition cùng dùng DB, số connection cần thiết còn phụ thuộc reader/writer/transaction/JobRepository, không chỉ số worker.

## 13. Retry, rollback và restart đúng theo owner

Ví dụ:

~~~text
batchKey = settlement-20261126
snapshotId = snap-20261126

p00001 -> tenant-a / north: đã COMPLETED
p00002 -> tenant-a / south: FAILED sau 8 chunk đã commit
p00003 -> tenant-b / north: đã COMPLETED

Restart cùng JobInstance:
  p00001, p00003: giữ kết quả, thường được bỏ qua theo restart policy
  p00002: phục hồi StepExecution/checkpoint phù hợp
  reader của p00002 vẫn chỉ đọc tenant-a / south
  writer có idempotency theo (batchKey, tenantId, orderId)
~~~

**Những điều kiện không thể thiếu:**

1. Identifying JobParameters giữ nguyên khi mục tiêu là restart cùng JobInstance.
2. `partitionKey -> (snapshotId, tenantId, regionCode)` không đổi.
3. Nội dung snapshot và phiên bản business rule không bị thay đổi giữa các lần chạy.
4. Reader có checkpoint phù hợp; `@StepScope` và tên ItemStream ổn định trong từng worker.
5. Writer chịu được replay hoặc có cơ chế đối soát và bù rõ ràng.
6. Không khởi chạy worker thứ hai trên cùng partition khi chưa xác định worker cũ đã dừng hoặc mất quyền xử lý.

**Không tự sửa các bảng JobRepository để ép StepExecution thành COMPLETED.** Metadata là cơ sở Spring Batch quyết định restart nhưng cần đối chiếu thêm dữ liệu nghiệp vụ. Nếu một partition gặp `UNKNOWN` hay `STARTED` kéo dài sau sự cố, hãy xác minh owner thật sự và trạng thái transaction trước khi điều phối lại.

### Side effect ngoài transaction

Một processor gọi API thanh toán hoặc gửi email có thể tạo tác động trước khi chunk rollback. Khi retry, cùng item có thể được xử lý lại. Cần **idempotency key** tại hệ thống nhận, bảng dedup, hoặc transactional outbox cho event được phát ra sau khi DB commit. Không xem processor stateless là đủ để bảo đảm *exactly-once effect* xuyên hệ thống.

### Một tenant lỗi có phải làm cả job thất bại?

Với manager split/partition theo cấu hình mặc định, trạng thái lỗi của worker có thể làm manager/job không COMPLETED. Đây là hành vi **fail-fast/fail-job** phù hợp nhiều nghiệp vụ đối soát toàn batch. Nếu yêu cầu tenant độc lập, có thể thiết kế **job riêng theo tenant**, lịch điều phối riêng hoặc cơ chế lưu kết quả từng tenant rồi tổng hợp; chỉ tiếp tục khi lỗi của một tenant được nghiệp vụ cho phép và có báo cáo chính xác. Không tự động đánh dấu một tenant lỗi là success chỉ để các tenant khác được tiếp tục.

## 14. Kiểm thử Partitioner: manifest đúng và ổn định

Unit/integration test đầu tiên phải kiểm tra Partitioner sinh **đúng map công việc**, không dùng status job để suy đoán:

~~~java
@Test
void mapsFrozenManifestToStablePartitionContexts() {
    JdbcTemplate jdbc = mock(JdbcTemplate.class);
    // Trong test thực, có thể dùng H2/PostgreSQL với bảng manifest cố định
    // thay cho mock để kiểm tra trực tiếp SQL và thứ tự.

    // Kỳ vọng từ một manifest đã chốt:
    // p00001 -> (snap-1, tenant-a, north)
    // p00002 -> (snap-1, tenant-a, south)
    // p00003 -> (snap-1, tenant-b, north)
    //
    // Kiểm tra:
    // - result.keySet() đúng 3 tên partition và thứ tự ổn định;
    // - mọi context có snapshotId, tenantId, regionCode khác rỗng;
    // - không có trùng (tenantId, regionCode) trong cùng batch;
    // - gọi lại với cùng manifest trả ánh xạ giống nhau;
    // - thay đổi gridSize không làm đổi mapping trong implementation này.
}
~~~

Đoạn trên là **khung kịch bản kiểm thử**, chưa phải unit test có assertion thực thi được. Với lớp `TenantRegionPartitioner` dùng `JdbcTemplate`, kiểm thử đơn giản và đáng tin hơn là tạo bảng manifest trong database test rồi assert trực tiếp kết quả:

~~~java
@Test
void frozenManifestIsMappedWithoutCrossTenantCollision() {
    // Giả định JdbcTemplate đã được khởi tạo với database test
    // và đã insert 3 entry thuộc cùng batchKey.
    Map<String, ExecutionContext> parts =
            new TenantRegionPartitioner(jdbcTemplate, "batch-test")
                    .partition(2);

    assertEquals(3, parts.size()); // gridSize chỉ là hint trong ví dụ
    assertEquals(
            List.of("p00001", "p00002", "p00003"),
            new ArrayList<>(parts.keySet()));

    assertEquals("tenant-a",
            parts.get("p00001").getString("tenantId"));
    assertEquals("north",
            parts.get("p00001").getString("regionCode"));
    assertEquals("tenant-b",
            parts.get("p00003").getString("tenantId"));
    assertEquals("north",
            parts.get("p00003").getString("regionCode"));
}
~~~

Test cần tạo fixture SQL được chỉ định và dọn dữ liệu sau mỗi lượt; nếu manifest rỗng thì implementation mẫu sẽ ném `IllegalStateException`. Nên bổ sung test status/error của manager khi dữ liệu manifest sai, test tenant ID không hợp lệ và test schema constraint từ chối trùng cặp owner.

## 15. Integration test: không lọt dữ liệu giữa tenant

Một test end-to-end trên DB cùng loại với production (ví dụ PostgreSQL qua Testcontainers) có thể tạo các record sau:

| snapshot_id | tenant_id | region_code | order_id | gross_total |
| --- | --- | --- | ---: | ---: |
| snap-1 | tenant-a | north | 101 | 100.00 |
| snap-1 | tenant-a | south | 102 | 150.00 |
| snap-1 | tenant-b | north | 101 | 250.00 |
| snap-1 | tenant-b | north | 103 | 350.00 |
| snap-1 | tenant-c | central | 104 | 450.00 |

Trong ví dụ, **hai tenant dùng chung order ID 101**. Manifest có bốn partition (A/north, A/south, B/north, C/central). Sau khi chạy:

- Output có **năm khóa `(batchKey, tenantId, orderId)`** tương ứng năm record nguồn.
- Hai output của `orderId=101` thuộc tenant-a và tenant-b đều tồn tại với giá trị riêng.
- Không có row của tenant-b được ghi với `tenant_id=tenant-a`.
- Khi kiểm tra từng StepExecution theo `partitionKey`, chỉ reader đúng owner đọc những record của partition đó.
- Lần chạy với `gridSize=1` và `gridSize=8` trên cùng snapshot, nhưng dưới **các JobInstance kiểm thử tách biệt**, cho kết quả nghiệp vụ giống nhau.

### Truy vấn đối soát thiếu dữ liệu

~~~sql
SELECT s.tenant_id, s.region_code, s.order_id
FROM staged_order AS s
LEFT JOIN normalized_order AS n
  ON n.batch_key = :batch_key
 AND n.tenant_id = s.tenant_id
 AND n.order_id = s.order_id
WHERE s.snapshot_id = :snapshot_id
  AND n.order_id IS NULL;
~~~

### Truy vấn tìm kết quả ngoài snapshot

~~~sql
SELECT n.tenant_id, n.order_id
FROM normalized_order AS n
LEFT JOIN staged_order AS s
  ON s.snapshot_id = :snapshot_id
 AND s.tenant_id = n.tenant_id
 AND s.order_id = n.order_id
WHERE n.batch_key = :batch_key
  AND s.order_id IS NULL;
~~~

### Truy vấn phát hiện record nguồn chưa có partition owner

~~~sql
SELECT s.tenant_id, s.region_code, COUNT(*) AS missing_rows
FROM staged_order AS s
LEFT JOIN partition_manifest AS p
  ON p.batch_key = :batch_key
 AND p.snapshot_id = s.snapshot_id
 AND p.tenant_id = s.tenant_id
 AND p.region_code = s.region_code
WHERE s.snapshot_id = :snapshot_id
  AND p.partition_key IS NULL
GROUP BY s.tenant_id, s.region_code;
~~~

Truy vấn cuối giúp phát hiện **coverage gap**: một vùng có record nhưng không được liệt kê trong manifest. Cần kiểm tra thêm **record result khác region** hoặc sai giá trị, vì primary key chỉ chống hai dòng cùng `(batchKey, tenantId, orderId)`, không chứng minh region/net_total chính xác.

~~~sql
SELECT s.tenant_id, s.order_id,
       s.region_code AS source_region,
       n.region_code AS output_region,
       s.gross_total,
       n.net_total
FROM staged_order AS s
JOIN normalized_order AS n
  ON n.batch_key = :batch_key
 AND n.tenant_id = s.tenant_id
 AND n.order_id = s.order_id
WHERE s.snapshot_id = :snapshot_id
  AND (n.region_code <> s.region_code
       OR n.net_total <> ROUND(s.gross_total, 2));
~~~

Những truy vấn này giả định quy tắc chuẩn hóa là làm tròn `gross_total` tới hai chữ số như processor mẫu. Nếu processor có filter/skip hợp lệ, phải xác định tập output kỳ vọng theo chính sách, không suy ra thiếu dữ liệu chỉ từ chênh lệch COUNT.

## 16. Failure injection và thử restart

Một bộ test cần chủ động gây lỗi thay vì chờ race condition ngẫu nhiên:

| Kịch bản | Lỗi được đưa vào | Bằng chứng cần xác minh |
| --- | --- | --- |
| Worker A/south fail giữa chunk | Writer ném lỗi DB tạm thời | Chunk rollback, StepExecution FAILED hoặc retry theo policy |
| Tenant-b đã COMPLETED trước khi A/south fail | Giữ dữ liệu đầu ra B sau restart | Không xóa/ghi chồng output của B |
| Mất tiến trình sau vài chunk commit | Worker bị dừng ở ranh giới có kiểm soát | Resume/replay an toàn, không nhân đôi tác động |
| Manifest thay đổi sau khi job bắt đầu | Thêm tenant hoặc đổi mapping `p00002` | Quy trình snapshot phát hiện vi phạm, không quietly remap |
| Tenant đổi region trong bảng live | Chuyển `north` sang `south` | Staging bất biến vẫn gắn owner ban đầu trong batch |
| Processor làm mất `tenantId` | Tiêm item với tenant khác vào writer | Guard trong writer từ chối cross-partition ownership |
| Một tenant có hàng triệu record | Tăng số bucket hoặc chia nhỏ vùng trên snapshot mới | Không trùng/thiếu, throughput và fairness được cải thiện |

Trong restart test, **giữ nguyên identifying JobParameters và manifest của lần chạy thất bại**. Nếu muốn thử thuật toán chia bucket khác, dùng một **batch/snapshot mới** thay vì lén đổi mapping của JobInstance đang có StepExecution cũ.

Ngoài việc assert `BatchStatus` và `ExitStatus`, cần xác minh **dữ liệu thực** cùng số transaction/rollback. Một JobExecution COMPLETED vẫn có thể là lỗi nghiệp vụ nếu SQL thiếu tenant predicate hoặc writer ghi sai khóa.

## 17. Đo hiệu năng và chọn kiến trúc

Với 80 tenant và một số tenant có nhiều vùng, `gridSize=4` không phải giá trị tối ưu mặc định. Hãy chạy các phép đo:

| Lần thử | Số partition | Worker pool | Điều quan sát |
| --- | ---: | ---: | --- |
| A | Theo tenant | 1 | Baseline, thời gian tenant lớn nhất |
| B | Theo tenant | 4 | Nút thắt khi bốn tenant cùng truy cập DB |
| C | Theo tenant–region | 4 | Thời gian partition chậm nhất, metadata overhead |
| D | Theo tenant–region | 8 | Connection wait, SQL lock và API quota |
| E | Tenant–region–bucket cho tenant lớn | 4 | Có giảm skew mà vẫn giữ isolation không? |

Theo dõi ít nhất:

- **Per tenant/region:** số record, read/write/skip, latency, retry, số partition đang chờ, thời gian hoàn tất.
- **Executor:** active threads, queue depth, rejected tasks, task wait time.
- **Database:** connection pool active/wait, query plan, index scan, lock wait, deadlock, transaction/commit latency.
- **JVM:** CPU, memory, GC pause và thread contention.
- **Nghiệp vụ:** số record/giá trị theo tenant, số lần dedup, sự khác biệt giữa snapshot và output.
- **Fairness:** p95 completion time theo tenant, thời gian tenant nhỏ chờ trong hàng đợi khi tenant lớn đang chạy.

**Ví dụ định tính:** nếu 20 partition nhỏ mỗi vùng cần 10 giây, còn một partition lớn cần 20 phút, tăng pool từ 4 lên 16 thread có thể hầu như không rút ngắn tổng thời gian vì **partition chậm nhất** chi phối. Chia nhỏ tenant lớn theo một khóa ổn định hoặc bucket có thể hiệu quả hơn nhiều.

Nếu yêu cầu isolation rất cao, mỗi tenant có SLA và database riêng, có thể cân nhắc **job riêng theo tenant** thay vì một job partitioned duy nhất. Khi đó điều phối lỗi, quota và thông tin trạng thái cần thêm một tầng orchestration, nhưng ranh giới sở hữu và vận hành sẽ rõ hơn.

## 18. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng khắc phục |
| --- | --- | --- |
| Dữ liệu tenant B xuất hiện ở output A | Reader thiếu `tenant_id`; writer dùng khóa không chứa tenant | Truy vấn đủ owner, khóa output `(batch,tenant,businessId)`, test cross-tenant |
| Một order được đọc ở hai vùng | Region assignment không loại trừ nhau hoặc thay đổi giữa job | Chốt owner trong staging, unique constraint và coverage test |
| Restart bỏ qua nhầm vùng | Manifest được tạo lại, tên partition bị dịch | Giữ partitionKey mapping bất biến và JobParameters |
| Tenant lớn khiến job chậm | Skew workload, một partition quá nặng | Chia tiếp theo bucket/range trong tenant |
| Tăng concurrency làm tenant nhỏ trễ hơn | Noisy neighbor, cạn DB/API quota | Giới hạn per-tenant, lập lịch công bằng, đo queue wait |
| Dữ liệu bị trùng sau retry | Writer cộng dồn hoặc side effect ngoài transaction | Idempotency key, UPSERT quyết định, transactional outbox |
| Rò tenant context giữa thread | `ThreadLocal` không dọn, mutable singleton | Truyền tenant rõ ràng, `try/finally`, không dùng global field |
| Worker báo COMPLETED nhưng tổng tiền sai | Processor/version thay đổi, vùng đầu vào bị chỉnh | Cố định snapshot/rules và đối soát giá trị |
| Worker không tìm được dữ liệu khi chạy remote | Snapshot chỉ có ở một DB/máy, chưa có quyền/truy cập | Shared storage/DB hoặc staging phù hợp, kiểm tra permission |
| Lỗi metadata khi nhiều partition | Quá nhiều StepExecution/ExecutionContext hoặc DB pool yếu | Nhóm partition, tăng hiệu quả truy vấn, đo JobRepository |

## 19. Bài thực hành và checklist

**Bài thực hành:** tạo một batch gồm ba tenant A, B, C; mỗi tenant có hai vùng `north` và `south`, phân bố bản ghi lệch mạnh (A/north lớn hơn các vùng khác ít nhất 100 lần). Hai tenant có cùng `orderId=42`. Dùng manifest có `partitionKey` cố định và triển khai job theo cấu trúc ở trên.

Các lượt chạy:

1. **Đúng dữ liệu:** chạy với một worker rồi bốn worker trên cùng snapshot, so sánh `(tenantId, orderId)` và tổng tiền đã chuẩn hóa; không được mất/trùng/cross-tenant.
2. **Sai predicate:** trong test riêng, cố tình bỏ điều kiện `tenant_id` ở reader; integration test phải **phát hiện** dữ liệu lẫn tenant, không chỉ assert `COMPLETED`.
3. **Sai khóa output:** thử một schema chỉ có `orderId` là unique; chứng minh cùng ID của A/B gây conflict, rồi sửa khóa composite.
4. **Lỗi và restart:** cho A/north fail sau vài chunk đã commit, các tenant khác đã COMPLETED; restart cùng JobInstance với manifest bất biến, đối soát dữ liệu cuối.
5. **Tenant lớn:** bổ sung `bucketId` cho A/north trong **batch mới**, giữ predicate và index tương ứng, so sánh thời gian partition chậm nhất.
6. **Isolation:** kiểm thử guard writer, quyền DB hoặc RLS nếu có, và kiểm tra context được dọn khi dùng thread pool.
7. **Vận hành:** đo time per tenant, queue wait, DB pool, CPU, GC, retry và số lần xử lý lặp.

### Checklist trước production

- [ ] Định nghĩa owner record rõ ràng: theo tenant, region hoặc business key; mọi record thuộc đúng một owner trong snapshot.
- [ ] Có snapshot và manifest bất biến với `partitionKey`, `snapshotId`, `tenantId`, `regionCode`; không tái tạo mapping tùy ý khi restart.
- [ ] Reader có predicate **tenant + region + snapshot**, thứ tự đọc ổn định và scope theo StepExecution.
- [ ] Processor/dependency dùng chung thread-safe, không giữ mutable `currentTenant` ở singleton.
- [ ] Writer kiểm tra owner và dùng business key có phạm vi tenant; replay không nhân đôi side effect.
- [ ] Quyền DB/RLS/schema/datasource routing phù hợp yêu cầu cách ly; không đưa secret vào ExecutionContext.
- [ ] Trường hợp region chuyển, tenant rỗng, tenant lớn, double ownership và manifest thiếu được test.
- [ ] Retry/restart dùng đúng JobInstance và dữ liệu snapshot; có đối soát theo tenant trước khi báo thành công.
- [ ] Có giới hạn executor/DB/API quota và metric fairness/noisy-neighbor.
- [ ] Đã đo tải thật để quyết định tenant-only, tenant–region, hybrid bucket hoặc job riêng theo tenant.

**Ghi nhớ:** chia theo tenant hoặc vùng nghiệp vụ là cách mở rộng Spring Batch dựa trên **ranh giới sở hữu dữ liệu thực sự**, không chỉ theo số lượng record. Partitioner giúp phân công `StepExecution`; **manifest bất biến, truy vấn có đủ khóa owner, writer idempotent và kiểm soát bảo mật** mới giữ được dữ liệu đúng qua concurrent processing và retry/restart. Tối ưu hiệu năng đòi hỏi xử lý tenant lớn, fairness và tài nguyên downstream bằng số đo, không chỉ tăng số partition.
