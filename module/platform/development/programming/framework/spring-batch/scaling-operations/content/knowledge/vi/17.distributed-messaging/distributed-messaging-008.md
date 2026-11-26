# Serialization ExecutionContext trong Spring Batch phân tán

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích vì sao `ExecutionContext` của Spring Batch phải được **serialize** để lưu bền vững và **deserialize** khi restart, đặc biệt ở kiến trúc nhiều worker.
- Phân biệt **serialization của metadata `JobRepository`** với **serialization thông điệp** qua RabbitMQ, Kafka hoặc các message channel khác.
- Nhận diện các giá trị phù hợp cho `ExecutionContext`: String, số, boolean, định danh snapshot, khoảng dữ liệu, offset hoặc đường dẫn manifest; tránh object đồ thị lớn và kiểu khó tương thích.
- Mô tả vai trò của `ExecutionContextSerializer`, `DefaultExecutionContextSerializer` và các lựa chọn JSON ở dòng Spring Batch 5.x.
- Thiết kế contract state ổn định qua restart và rolling deployment, có kiểm thử đọc dữ liệu từ phiên bản cũ.
- Áp dụng các yêu cầu về bảo mật deserialization, giới hạn kích thước metadata, idempotency và xử lý khi một worker commit xong nhưng phản hồi bị mất.
- Kiểm tra sự tương thích giữa manager, worker, schema `JobRepository`, transaction manager và broker trước khi scale-out workload lớn.

## 1. Đặt vấn đề: checkpoint phải sống lâu hơn JVM

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, job dữ liệu lớn có thể chạy bằng local partitioning, remote partitioning hoặc remote chunking. Những mô hình này tận dụng nhiều thread hoặc nhiều process để tăng thông lượng, nhưng cũng làm tăng xác suất gặp các tình huống:

- Worker chết sau khi đã commit một số chunk.
- Manager khởi động lại trong lúc một số partition đang xử lý.
- Worker mới ở phiên bản ứng dụng khác cần đọc lại metadata do phiên bản cũ ghi.
- Database chứa metadata được chuyển server hoặc khôi phục từ backup.
- Message giữa manager và worker bị timeout, giao lại hoặc đến sau khi worker cũ đã hoàn thành.

Nếu `ExecutionContext` chỉ tồn tại trong RAM, worker thay thế không biết nó được giao khoảng dữ liệu nào hoặc reader đã đọc đến đâu. Spring Batch có khả năng lưu state trong `JobRepository`; để đưa map state từ object Java vào lưu trữ, framework cần **serialization**.

~~~mermaid
flowchart LR
    P["Partitioner / Reader / Writer"] --> C["ExecutionContext trong JVM"]
    C --> S["ExecutionContextSerializer"]
    S --> R["JobRepository: metadata bền vững"]
    R --> D["Deserializer khi restart"]
    D --> N["Worker StepExecution mới"]
    N --> P
~~~

**Thông điệp chính:** serialization là một mắt xích của khả năng restart, **không phải** cơ chế tạo exactly-once, không tự bảo đảm phân vùng đúng và cũng không phải lời giải cho giao tiếp phân tán.

### Khái niệm nền tảng

| Thuật ngữ | Ý nghĩa trong bài |
| --- | --- |
| `ExecutionContext` | Bản đồ key–value dùng lưu state gắn với một `JobExecution` hoặc `StepExecution` |
| **Serialization** | Chuyển state thành biểu diễn có thể lưu/truyền theo một định dạng xác định |
| **Deserialization** | Khôi phục các giá trị từ biểu diễn đã lưu |
| **Codec/serializer** | Thành phần quyết định encoding, kiểu dữ liệu và cách tái tạo object |
| **Checkpoint** | State đủ để tiếp tục phần việc sau một điểm commit hợp lệ |
| **Wire format** | Định dạng thông điệp thực sự đi qua broker hoặc kết nối mạng |
| **Compatibility** | Khả năng phiên bản mới đọc và hiểu state cũ với cùng ngữ nghĩa |

Không phải mọi object Java đều có thể hoặc nên đưa vào `ExecutionContext`. Việc gọi `put("key", object)` thành công trong RAM chưa chứng minh object đó có thể được lưu và đọc lại bởi serializer được cấu hình.

## 2. Có hai lớp serialization khác nhau

Điểm dễ nhầm nhất ở hệ thống phân tán là tưởng rằng `ExecutionContextSerializer` chính là message serializer của broker.

~~~mermaid
flowchart TD
    M["Manager JVM"] --> P["Partitioner tạo StepExecutionContext"]
    P --> A["Lớp A: serialize metadata cho JobRepository"]
    A --> JR["BATCH_STEP_EXECUTION_CONTEXT"]
    M --> B["Lớp B: serialize request/reply cho broker"]
    B --> Q["RabbitMQ / Kafka / Middleware"]
    Q --> W["Remote Worker JVM"]
    W --> F["Tra metadata StepExecution theo protocol"]
    F --> JR
    W --> A
~~~

**Lớp A – metadata serialization:** `JobRepository` chuyển nội dung `ExecutionContext` thành định dạng lưu bền vững. Khi `JobExplorer`, repository hoặc worker đọc lại, nội dung phải được deserialize bằng cấu hình tương thích.

**Lớp B – message serialization:** Spring Integration, broker adapter hoặc application serializer chuyển **request/reply message** sang bytes. Định dạng này phụ thuộc transport và giao thức. Với một cách triển khai remote partitioning, request chỉ mang các định danh như `jobExecutionId`, `stepExecutionId` và tên step, sau đó worker lấy `ExecutionContext` từ shared repository. Nghĩa là **toàn bộ `ExecutionContext` không nhất thiết xuất hiện trong broker payload**.

| Câu hỏi | Metadata codec | Broker/message codec |
| --- | --- | --- |
| Dữ liệu chính | Map checkpoint, partition state | Work request, result, header và correlation |
| Được lưu ở đâu? | `JobRepository`, thường JDBC DB | Queue/log/topic hoặc buffer của transport |
| Ai đọc? | Repository, explorer, worker dùng metadata | Consumer/message handler của manager và worker |
| Khi lỗi tương thích | Không mở được checkpoint, restart thất bại | Không nhận/parse được message, retry hoặc DLQ |
| Tác động của version | Thay cấu trúc state đã lưu từ trước | Thay schema request/reply trong rolling deploy |
| Cách bảo vệ | Codec nhất quán, state nhỏ, thử restart | Schema/version contract, consumer compatibility, retry, idempotency |

**Quy tắc:** trước khi thay codec, phải biết mình đang thay **lớp nào**. Thay message converter của broker không tự chuyển đổi metadata đã ghi trong bảng `BATCH_STEP_EXECUTION_CONTEXT`; đổi serializer metadata cũng không tự đổi wire format của các message cũ còn trong queue.

## 3. ExecutionContext nào được lưu?

Spring Batch quản lý ít nhất hai phạm vi:

- **`JobExecutionContext`** gắn với `JobExecution`, phù hợp với state cấp job và dữ liệu trao đổi qua các bước có thứ tự rõ.
- **`StepExecutionContext`** gắn với từng `StepExecution`, phù hợp với input key của partition và checkpoint reader/writer.

Trong partitioning, mỗi worker partition có `StepExecution` riêng, do đó có context riêng. Tên key như `startId` hoặc `inputKey` có thể giống nhau giữa các partition, nhưng giá trị khác nhau theo miền công việc.

~~~text
JobInstance: importOrders(snapshotId=orders-2026-11-25)
  JobExecution
    JobExecutionContext:
      manifestVersion = v7

    workerStep:partition0000
      StepExecutionContext:
        inputKey = orders/2026-11-25/shard-0000
        workerReader.read.count = checkpoint của partition 0

    workerStep:partition0001
      StepExecutionContext:
        inputKey = orders/2026-11-25/shard-0001
        workerReader.read.count = checkpoint của partition 1
~~~

Khi worker commit chunk, các component có `ItemStream` có thể cập nhật `StepExecutionContext` theo lifecycle `open/update/close`, và repository lưu state ở thời điểm được framework quản lý. `JobExecutionContext` không mặc định được persist theo **mỗi chunk** như state của step.

| State | Nơi nên đặt | Vì sao |
| --- | --- | --- |
| `snapshotId` / business date chung | Identifying `JobParameters` hoặc manifest được tham chiếu | Xác định công việc logic để restart đúng instance |
| `inputKey`, `startId`, `endExclusive` | Worker `StepExecutionContext` | Mỗi partition có assignment riêng |
| Offset/cursor của reader | State `ItemStream` trong worker context | Gắn với tiến độ từng partition |
| ID file/manifest group | Worker `StepExecutionContext` | Chỉ giữ tham chiếu nhỏ, tái lập được |
| Hàng triệu record đã xử lý | Business DB hoặc object storage | Không dùng metadata context để chứa payload |
| Event đã phát sang broker | Outbox/ledger/reconciliation | Context không thay thế delivery semantics |

`ExecutionContext` không phải một channel shared-memory để các worker gửi tín hiệu realtime cho nhau. Nó cũng không phải distributed lock hay nơi lưu danh sách toàn bộ object đang xử lý.

## 4. Định dạng và serializer trong Spring Batch 5.x

Spring Batch cung cấp giao diện `ExecutionContextSerializer` dùng cho metadata repository. Ở dòng **Spring Batch 5.x**, các implementation thường được biết đến gồm:

- `DefaultExecutionContextSerializer`: serializer mặc định dựa vào cơ chế Java serialization và biểu diễn lưu trữ phù hợp cho metadata. Các giá trị custom cần tương thích với Java serialization và môi trường đọc lại.
- `Jackson2ExecutionContextStringSerializer`: một lựa chọn dùng Jackson JSON, với cấu hình kiểu dữ liệu được phép deserialize. Cần kiểm tra dependency, trusted classes và API chính xác của release đang dùng.

**Điều phải kiểm tra trước khi cấu hình:** phiên bản Spring Batch, Spring Boot auto-configuration, serializer mặc định thực tế, repository factory, explorer factory, schema JDBC và dữ liệu đã tồn tại. Không giả định tất cả release có cùng implementation/default hoặc tự động sử dụng một `@Bean ExecutionContextSerializer` nếu repository đã được auto-configure theo cách khác.

### Phân biệt representation trong DB

Schema JDBC metadata phổ biến có các bảng:

- `BATCH_JOB_EXECUTION_CONTEXT` cho context cấp job execution.
- `BATCH_STEP_EXECUTION_CONTEXT` cho context cấp step execution.

Trong các schema Spring Batch thông dụng, có cột `SHORT_CONTEXT` và `SERIALIZED_CONTEXT` để lưu biểu diễn context. `SHORT_CONTEXT` có thể chỉ chứa phần rút gọn, còn nội dung đầy đủ có thể ở cột lớn tương ứng; cách chọn, độ dài cột và encoding phụ thuộc serializer/schema/DB cụ thể.

Không suy luận `SHORT_CONTEXT` là JSON ứng dụng có thể parse ổn định. Khi cần làm việc với state, ưu tiên `JobExplorer` hoặc API repository và serializer tương ứng.

~~~sql
-- Cú pháp tham số :jobExecutionId tùy SQL client.
SELECT s.STEP_EXECUTION_ID,
       s.STEP_NAME,
       s.STATUS,
       c.SHORT_CONTEXT
FROM BATCH_STEP_EXECUTION s
JOIN BATCH_STEP_EXECUTION_CONTEXT c
  ON c.STEP_EXECUTION_ID = s.STEP_EXECUTION_ID
WHERE s.JOB_EXECUTION_ID = :jobExecutionId
  AND s.STEP_NAME LIKE 'workerStep:%'
ORDER BY s.STEP_NAME;
~~~

Truy vấn này giúp quan sát partition nào có metadata, **không** phải giao diện được hỗ trợ để sửa checkpoint. Không cập nhật trực tiếp chuỗi đã serialize trong DB để “tua cursor”, vì còn encoding, kiểu dữ liệu, transaction và tính nhất quán của `StepExecution`.

## 5. Thí nghiệm Java: serialize rồi deserialize một context nhỏ

Ví dụ sau dùng `DefaultExecutionContextSerializer` của Spring Batch 5.x, đặt các giá trị đơn giản có kiểu rõ ràng, sau đó thực hiện round-trip **trong bộ nhớ**. Mục đích là minh họa hợp đồng serialization, không thay thế job thật.

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.batch.core.repository.dao.DefaultExecutionContextSerializer;
import org.springframework.batch.core.repository.dao.ExecutionContextSerializer;

public final class ExecutionContextRoundTrip {

    public static void main(String[] args) throws IOException {
        Map<String, Object> state = new LinkedHashMap<>();
        state.put("inputKey", "orders/2026-11-25/shard-0001");
        state.put("snapshotId", "orders-2026-11-25");
        state.put("startId", 3_000_001L);
        state.put("endExclusive", 6_000_001L);
        state.put("schemaVersion", 1);

        ExecutionContextSerializer serializer =
                new DefaultExecutionContextSerializer();

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        serializer.serialize(state, bytes);

        byte[] encoded = bytes.toByteArray();
        Map<String, Object> restored = serializer.deserialize(
                new ByteArrayInputStream(encoded));

        if (!state.equals(restored)) {
            throw new IllegalStateException(
                    "ExecutionContext serialization changed state");
        }

        if (!(restored.get("startId") instanceof Long)) {
            throw new IllegalStateException("Lost Long type");
        }

        System.out.println("Round-trip OK");
        System.out.println("Bytes stored: " + encoded.length);
        System.out.println("Restored inputKey: " + restored.get("inputKey"));
    }
}
~~~

Với những input ở trên, chương trình kỳ vọng có thông báo `Round-trip OK` và input key được khôi phục chính xác. **Kích thước byte phải đo thực tế** theo serializer/phiên bản đang dùng; không gán một giá trị kích thước cố định.

Đây là phép thử **đọc–ghi cùng codec trong một lần chạy**. Nó **chưa** kiểm tra tương thích khi:

- Phiên bản ứng dụng ghi state khác phiên bản đang đọc.
- Tên package/class của object custom đã thay đổi.
- Serializer chuyển từ Java serialization sang JSON.
- Trusted types hoặc dependency Jackson khác nhau.
- DB metadata đã tồn tại từ release trước.

Do đó cần thêm bộ test **golden fixtures**: lưu một vài payload metadata thật từ bản đang chạy, sau đó dùng bản ứng dụng mới deserialize và kiểm tra **kiểu lẫn ngữ nghĩa** của key.

## 6. Các kiểu dữ liệu nên và không nên lưu vào ExecutionContext

Một rule hữu ích cho batch phân tán là **đưa vào context các định danh bất biến và checkpoint nhỏ, không đưa vào object graph sống**.

| Loại giá trị | Ví dụ | Đánh giá |
| --- | --- | --- |
| String | `inputKey`, `snapshotId`, `fileVersion` | Phù hợp khi ý nghĩa ổn định |
| Số nguyên/long | `startId`, `endExclusive`, `fileIndex` | Phù hợp, cần giữ type qua round-trip |
| Boolean | `headerSkipped` | Phù hợp cho state đơn giản, có default rõ |
| Danh sách ít String | Một số object key của manifest | Có thể dùng, nhưng cân nhắc lưu ID manifest thay vì list |
| Custom Java record/class | `MyCheckpoint` | Có thể phát sinh phụ thuộc class/package/serializer; nên tránh nếu không cần |
| `InputStream`, `Connection`, `EntityManager` | Handle tài nguyên đang mở | **Không lưu**; không thể tái sử dụng đúng trên worker/JVM mới |
| Spring bean, lambda, `TaskExecutor` | Object runtime | **Không lưu**; không có contract restart |
| Toàn bộ chunk hoặc hàng triệu item | Payload dữ liệu lớn | **Không lưu**; dùng DB/object storage |
| Access token/password | Secret runtime | **Không lưu**; sử dụng secret manager/identity của worker |
| Exception graph hoặc HTTP client | Object có nhiều reference | **Không lưu**; log lỗi được kiểm soát riêng |

### Chú ý kiểu số và kiểu thời gian

Một `Long` ở context không giống `Integer`, và một String chứa timestamp không tự mang timezone. Nếu đặt `startId` bằng `putLong` rồi phiên bản mới đọc bằng `getInt`, có thể phát sinh lỗi kiểu hoặc cắt giá trị.

Nên thống nhất contract:

~~~java
ExecutionContext context = new ExecutionContext();
context.putString("inputKey", "orders/2026-11-25/shard-0001");
context.putLong("startId", 3_000_001L);
context.putLong("endExclusive", 6_000_001L);
context.putInt("stateSchemaVersion", 1);
~~~

Ở worker, kiểm tra key tồn tại và đọc bằng đúng kiểu:

~~~java
String inputKey = context.getString("inputKey");
long startId = context.getLong("startId");
long endExclusive = context.getLong("endExclusive");

if (inputKey == null || inputKey.isBlank()
        || startId >= endExclusive) {
    throw new IllegalStateException("Invalid partition metadata");
}
~~~

Với ngày/giờ, dùng format xác định (ISO-8601 và múi giờ thống nhất) hoặc epoch với đơn vị rõ, thay vì serializer phụ thuộc vào object `ZoneId`/`LocalDateTime` và ngầm định timezone của host.

## 7. Java: partitioner chỉ giao state nhỏ, worker giải quyết nguồn

Trong remote partitioning, manager nên truyền **định danh miền dữ liệu**, không chuyển cả reader hay nội dung hàng triệu item vào context.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class StablePartitioner implements Partitioner {

    private final String snapshotId;

    public StablePartitioner(String snapshotId) {
        this.snapshotId = snapshotId;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }
        if (snapshotId == null || snapshotId.isBlank()) {
            throw new IllegalArgumentException("snapshotId required");
        }

        Map<String, ExecutionContext> partitions =
                new LinkedHashMap<>();

        // Ví dụ 4 shard của manifest đã đóng băng:
        for (int i = 0; i < 4; i++) {
            ExecutionContext context = new ExecutionContext();
            context.putString("snapshotId", snapshotId);
            context.putString("inputKey",
                    snapshotId + "/shard-" + String.format("%04d", i));
            context.putInt("stateSchemaVersion", 1);

            partitions.put(
                    String.format("partition%04d", i), context);
        }

        return partitions;
    }
}
~~~

Ví dụ dùng bốn shard cố định cho mục đích học tập. Trong production, tên và assignment nên lấy từ **manifest bất biến**, có checksum/version, được quản lý theo `JobInstance`. `gridSize` không trực tiếp đồng nghĩa số worker JVM chạy đồng thời.

Worker có thể bind input key qua `@StepScope`:

~~~java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

record OrderRow(long orderId, String payload) {}

@Bean
@StepScope
JdbcCursorItemReader<OrderRow> partitionReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['inputKey']}") String inputKey) {

    if (inputKey == null || inputKey.isBlank()) {
        throw new IllegalArgumentException("Missing inputKey");
    }

    return new JdbcCursorItemReaderBuilder<OrderRow>()
            .name("partitionReader")
            .dataSource(dataSource)
            .sql("""
                SELECT order_id, payload
                FROM frozen_order_shard
                WHERE input_key = ?
                ORDER BY order_id
                """)
            .preparedStatementSetter(
                    ps -> ps.setString(1, inputKey))
            .rowMapper((rs, n) ->
                    new OrderRow(rs.getLong("order_id"),
                                 rs.getString("payload")))
            .saveState(true)
            .build();
}
~~~

Đoạn bean nằm trong một class `@Configuration`. Mỗi partition `StepExecution` có reader riêng khi framework quản lý step scope đúng; `.saveState(true)` cho phép reader lưu tiến độ qua `ItemStream`.

**Điều không đổi khi chuyển từ local sang remote:** worker mới phải được cung cấp đúng input key sau khi metadata deserialize; không truyền `JdbcCursorItemReader`, `Connection`, ThreadLocal transaction hoặc bean singleton từ manager sang worker qua message.

### Hai đường lấy context trong remote partitioning

Tùy handler/protocol:

1. Manager tạo `StepExecution`, lưu context trong repository, message mang **ID/metadata đủ để worker tra cứu**, worker dùng repository lấy state.
2. Giao thức tùy biến có thể gửi một DTO chứa **assignment được thiết kế riêng**; trường hợp đó còn có message serializer độc lập.

Đường thứ nhất thường gặp trong Spring Batch Integration, vì `StepExecutionRequest` có vai trò định danh step execution. Không tự khẳng định mọi transport đều gửi full map context qua broker.

## 8. Metadata serializer được cấu hình ở đâu?

Với JDBC-based batch metadata trong Spring Batch 5.x, serializer là một phần cấu hình của repository DAO/factory. `JobRepositoryFactoryBean` có thể nhận serializer thông qua API cấu hình, và những thành phần **đọc metadata** như `JobExplorerFactoryBean` cũng cần tương thích.

Ví dụ *phác họa cấu hình có chủ đích*, chỉ để nhấn mạnh chỗ cấu hình serializer:

~~~java
import javax.sql.DataSource;

import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.repository.dao.DefaultExecutionContextSerializer;
import org.springframework.batch.core.repository.dao.ExecutionContextSerializer;
import org.springframework.batch.core.repository.support.JobRepositoryFactoryBean;
import org.springframework.transaction.PlatformTransactionManager;

static JobRepository createRepository(
        DataSource metadataDataSource,
        PlatformTransactionManager transactionManager) throws Exception {

    ExecutionContextSerializer serializer =
            new DefaultExecutionContextSerializer();

    JobRepositoryFactoryBean factory = new JobRepositoryFactoryBean();
    factory.setDataSource(metadataDataSource);
    factory.setTransactionManager(transactionManager);
    factory.setSerializer(serializer);
    factory.afterPropertiesSet();
    return factory.getObject();
}
~~~

Đây là ví dụ **tạo repository thủ công**, không phải đoạn code được khuyến khích chèn song song với `JobRepository` do Spring Boot đã auto-configure. Trong một ứng dụng thực tế, cần thống nhất **một** cấu hình quản lý repository, explorer, schema, transaction manager và table prefix. Không tạo thêm repository thứ hai vô tình trỏ vào cùng metadata rồi có hành vi khác.

Nếu dùng `Jackson2ExecutionContextStringSerializer`, **không** chỉ thay `new DefaultExecutionContextSerializer()` trong production đang có dữ liệu cũ rồi restart lập tức. Hai định dạng có thể không đọc được lẫn nhau; việc chuyển codec đòi hỏi chiến lược migration hoặc bảo đảm đọc được cả state cũ và mới.

### Kiểm tra cùng serializer ở mọi thành phần đọc state

| Thành phần | Hành động | Rủi ro nếu mismatch |
| --- | --- | --- |
| Manager `JobRepository` | Lưu context sau phân chia, checkpoint | Ghi định dạng worker không hiểu |
| Remote worker metadata access | Tra worker `StepExecution` / context | Không deserialize được hoặc sai kiểu |
| `JobExplorer` / JobOperator | Xem/restart execution | Không đọc lại được context lịch sử |
| Công cụ vận hành | Tra cứu state | Đọc lỗi hoặc giải thích sai dữ liệu |
| Database migration process | Backup/chuyển format | Có thể phá khả năng restart nếu bỏ state cũ |

Không tùy tiện parse `SHORT_CONTEXT` bằng regex/SQL rồi tự “sửa” serialized payload. Trong môi trường có nhiều phiên bản framework cùng chạy, cần test **cross-version, cross-process** trước khi rolling upgrade.

## 9. Versioning: state của hôm qua phải đọc được hôm nay

Một job có thể chạy 8 giờ và thất bại sau khi đã commit 7 giờ dữ liệu. Việc deploy phiên bản mới giữa hai lần chạy làm thay đổi class/package, tên key hoặc default của serializer có thể khiến state hôm qua không khôi phục được.

Có ba cấp tương thích riêng:

1. **Codec-level:** bytes cũ có deserialize bằng codec mới không?
2. **Type-level:** kiểu dữ liệu cũ có còn class, tên field và cách khởi tạo tương ứng không?
3. **Semantic-level:** một key như `lastProcessedId` hoặc `inputKey` còn có cùng ý nghĩa không?

Ví dụ, phiên bản 1 lưu:

~~~text
inputKey = "orders-2026-11-25/shard-1"
nextOffset = 1800  (Integer)
stateSchemaVersion = 1
~~~

Phiên bản 2 dự kiến dùng:

~~~text
inputKey = "orders-2026-11-25/shard-1"
lastCommittedOrderId = 875000L  (Long)
stateSchemaVersion = 2
~~~

Hai giá trị `nextOffset` và `lastCommittedOrderId` **không tương đương**: offset có thể thay đổi khi nguồn thêm/xóa record, trong khi ID cần thứ tự/độ duy nhất và quy tắc resume khác. Ngay cả khi cả hai deserialize được, phiên bản mới cũng **không được tự suy luận** chúng là cùng checkpoint.

### Chiến lược thay đổi an toàn

- **Giữ schema cũ trong khi còn JobInstance cần restart.** Đây thường là lựa chọn ít rủi ro nhất.
- Khi cần thay đổi, thêm `stateSchemaVersion` hoặc marker tương đương vào **state do ứng dụng sở hữu**, không ghi đè key của framework reader.
- Hỗ trợ đọc cả key cũ và key mới **khi chuyển đổi ngữ nghĩa được chứng minh đúng**; không tạo fallback ngẫu nhiên làm bỏ sót item.
- Di chuyển dữ liệu metadata trên **bản sao repository đã backup**, kiểm chứng restore và restart trước khi production.
- Đảm bảo các serializer/worker phiên bản cũ và mới có **rolling-compatibility window** rõ ràng.
- Nếu không có phép migration an toàn, để job cũ hoàn tất theo phiên bản cũ hoặc tạo một **reprocess instance mới có chủ đích** cùng writer idempotent và đối soát, không gọi reprocess đó là restart.

Thay `run.id` hoặc timestamp identifying để tạo instance mới chỉ tránh phải đọc checkpoint cũ; nó **không** làm dữ liệu đã commit tự biến mất. Đó là một thao tác nghiệp vụ khác, phải có kế hoạch chống duplicate và xử lý side effect.

## 10. An toàn deserialization và dữ liệu nhạy cảm

Serialization và deserialization thường chạy bằng quyền của ứng dụng. Đặc biệt với Java object serialization hoặc cơ chế JSON đa hình, đọc object có kiểu không đáng tin cậy có thể có rủi ro **code execution, gadget chain, denial-of-service hoặc dựng object sai ngữ nghĩa** nếu data/codec/trusted types không được kiểm soát.

Nguyên tắc:

- `JobRepository` phải được bảo vệ bằng **quyền DB tối thiểu**, xác thực, network policy và backup controls. Không xem metadata là nguồn input công khai không được tin cậy.
- Ưu tiên **primitive/String/số/ID** thay vì graph của class nghiệp vụ phức tạp; giảm surface của deserialization.
- Nếu dùng Jackson-based serializer, cấu hình **trusted classes/package tối thiểu** theo đúng API phiên bản; tránh mở rộng trust không có kiểm soát.
- Không tùy tiện bật kiểu polymorphic deserialization toàn cục với danh sách class không giới hạn để “sửa lỗi class not allowed”.
- Không deserialize bytes từ broker/HTTP bằng Java object serialization mặc định mà không xác thực/kiểm soát nguồn, schema và class được phép.
- Giới hạn kích thước context; không đưa hàng triệu item, exception graph, binary payload hoặc token vào state.
- Không ghi secret (`password`, API token, private key) vào `ExecutionContext`. Metadata có thể được persist và backup lâu hơn execution.
- Validate `inputKey`/path/URL trước khi dùng: chống path traversal, SQL injection (dùng prepared statement), truy cập URL ngoài allowlist.
- Thử với object không hợp lệ, payload lớn bất thường và class không được phép; lỗi phải được báo rõ, không fallback sang context rỗng.

**Phân biệt lỗi do dữ liệu không tương thích với lỗi transient:** một class cũ bị đổi package hoặc một định dạng JSON khác không tự trở nên đúng sau 1.000 lần retry. Cần sửa/migration có chủ đích, không tạo retry storm làm đầy broker và DB.

## 11. Transaction, checkpoint và lỗi giữa hai lần commit

Ngay cả khi serializer round-trip đúng, trạng thái khôi phục vẫn có thể không đồng nhất với dữ liệu nghiệp vụ nếu metadata và business output không thuộc cùng transaction.

Xem chuỗi lỗi:

~~~mermaid
sequenceDiagram
    participant W as Worker
    participant B as Business DB
    participant R as JobRepository
    participant M as Manager
    W->>B: Ghi item/chunk
    B-->>W: COMMIT thành công
    Note over W,R: Worker chết / lỗi metadata trước checkpoint
    M->>R: Đọc trạng thái cũ
    R-->>M: Chưa xác nhận chunk đã hoàn tất
    M->>W: Restart / xử lý lại phần chưa chắc chắn
    W->>B: Ghi lại business key
    B-->>W: UPSERT / dedup giữ kết quả đúng
~~~

Nếu metadata và business DB có transaction manager khác nhau, không thể giả định một transaction vật lý bao phủ cả hai. Bản thân serializer **không** tạo atomicity giữa hai DB, cũng không tạo transaction phân tán giữa broker và DB.

### Ghi lại cho an toàn

Một ví dụ writer PostgreSQL có business key:

~~~sql
CREATE TABLE imported_order (
    snapshot_id VARCHAR(100) NOT NULL,
    order_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, order_id)
);
~~~

~~~sql
INSERT INTO imported_order(snapshot_id, order_id, source_version, payload)
VALUES (:snapshotId, :orderId, :sourceVersion, :payload)
ON CONFLICT (snapshot_id, order_id) DO UPDATE
SET source_version = EXCLUDED.source_version,
    payload = EXCLUDED.payload
WHERE imported_order.source_version < EXCLUDED.source_version;
~~~

Với quy tắc version ổn định, replay bản cũ không ghi đè bản mới. Nhưng còn phải xét trigger/audit/API side effect. Nếu writer có thao tác `UPDATE total = total + :delta`, việc chạy lại có thể cộng hai lần; cần ledger theo operation key, partial aggregate hoặc cách ghi idempotent khác.

### Ranh giới StepExecutionContext

`ItemStream` reader nên lưu checkpoint qua lifecycle của Spring Batch, thay vì ứng dụng tự ý gọi `context.put(...)` bất kỳ rồi giả định đã persist. Nếu dùng một `JdbcCursorItemReader`, giữ input bất biến và thứ tự đọc deterministic để state offset được khôi phục đúng.

Không dùng giá trị trong `ExecutionContext` như “sổ cái đã thanh toán” hoặc nguồn sự thật duy nhất cho side effect ngoài transaction.

## 12. Serialization request/reply khi xử lý phân tán

Trong **remote partitioning**, message thường mô tả một worker `StepExecution` phải chạy. Trong **remote chunking**, request thường mang các item đã đọc ở manager; payload có thể lớn hơn nhiều và cần serialize item, header, correlation hoặc thông tin retry.

| Mô hình | Nơi đọc input | Nội dung message điển hình | Điều phải kiểm tra |
| --- | --- | --- | --- |
| Local partitioning | Worker thread cùng JVM | Không cần broker để giao partition | Context/checkpoint trong repository |
| Remote partitioning | Worker JVM | StepExecution ID/partition request theo protocol | Metadata codec và message converter **riêng** |
| Remote chunking | Manager | Chunk item gửi qua broker, reply kết quả worker | Item serializer, schema, request/reply, backlog |
| Tự xây coordinator | Theo thiết kế | DTO inputKey/range hoặc work ID | Tự chịu trách nhiệm version, ack, ownership, restart |

Một message minh họa *mang ý nghĩa* của remote partitioning:

~~~json
{
  "jobExecutionId": 1204,
  "stepExecutionId": 9331,
  "stepName": "workerStep",
  "schemaVersion": 1
}
~~~

**Đây không phải format JSON mặc định được bảo đảm** của Spring Batch Integration. Cấu trúc thực tế của `StepExecutionRequest` và serializer transport phải theo thư viện đang dùng.

### Mất reply không có nghĩa worker chưa commit

1. Manager gửi request K.
2. Worker K ghi output và commit.
3. Worker gửi reply, nhưng mạng/broker làm mất acknowledgement hoặc manager chưa xử lý được.
4. Manager có thể retry/recover K.
5. Worker mới có thể đọc lại cùng `StepExecutionContext` và thực hiện lại một phần công việc.

Mọi thành phần phải phân biệt **message id**, **step execution id**, **partition name** và **business key**. `StepExecutionId` rất hữu ích cho correlation, nhưng nếu restart tạo execution ID mới, nó không được dùng làm khóa idempotency nghiệp vụ duy nhất. Cần dùng khóa ổn định như `(snapshotId, orderId, sourceVersion)`.

Khi ứng dụng thay codec message mà broker còn message cũ, consumer mới có thể không deserialize được request/reply. Hãy dùng schema version và rollout tương thích, drain/migrate backlog an toàn, tránh xóa message chưa xử lý.

## 13. Tài nguyên và thông lượng: context lớn không vô hại

Mỗi worker/partition có `StepExecution` và context. Với job 50.000 partition, nếu context chứa object lớn hoặc serializer tạo payload phình to, metadata IO và CPU có thể trở thành bottleneck.

Giả sử mỗi context sau serialize có kích thước trung bình `2 KiB`:

~~~text
50.000 partitions × 2 KiB ≈ 97,7 MiB serialized context data
~~~

Nếu mỗi context là `200 KiB`:

~~~text
50.000 partitions × 200 KiB ≈ 9,54 GiB serialized context data
~~~

Đây là phép tính *dung lượng nội dung*, chưa tính index, hàng/cột DB, transaction log, các bản ghi execution nhiều lần khi restart, replication và backup. Context lớn còn làm tăng thời gian serialize/deserialize và cập nhật checkpoint, ngay cả khi payload không thay đổi nhiều.

### Quy tắc sizing thực tế

- Ưu tiên lưu **snapshotId / objectKey / manifestVersion** thay vì nhét manifest khổng lồ vào context.
- Chọn số partition dựa trên thời gian xử lý, skew, worker concurrency và overhead metadata, không chỉ dựa vào `gridSize` cao nhất.
- Đo serializer latency, `JobRepository` query/update latency, row size và transaction log khi tăng partition.
- Đo `readCount`, `writeCount`, rollback/retry, duration theo partition và throughput nghiệp vụ hữu ích.
- Kiểm tra CPU/heap/GC của manager và worker, JDBC pool, DB lock/IO và broker backlog.
- Nếu metadata DB dùng chung business DB, checkpoint quá dày có thể cạnh tranh tài nguyên với writer.
- Không tắt `saveState` chỉ để giảm IO nếu job còn yêu cầu resume đúng checkpoint; phải đánh giá chi phí restart.

### Bảng phân tích nhanh

| Hiện tượng | Giả thuyết | Phép đo xác minh |
| --- | --- | --- |
| Job chạy được lần đầu nhưng restart lỗi | Codec/class/format cũ không đọc được | Deserialization error, golden fixture |
| Worker mới lỗi khi mở context | Repository khác version hoặc trusted type không hợp lệ | Serializer config của manager/worker |
| Broker DLQ tăng nhưng DB metadata vẫn đọc được | Message codec/schema không tương thích | Consumer error, payload version |
| Repository CPU tăng theo số partition | Context lớn, checkpoint dày, metadata writes | Byte size, latency, DB profiling |
| Worker đọc lại dữ liệu trùng sau crash | Checkpoint/DB commit lệch hoặc input drift | Step state và business key reconciliation |
| Tăng worker nhưng throughput không tăng | DB/API/broker trở thành bottleneck | Connection wait, lock, in-flight, broker lag |

## 14. Kiểm thử compatibility trước khi rolling deploy

Một bộ test đáng tin cậy cho state phân tán cần kiểm tra cả **round-trip**, **restart** và **cross-version**:

1. **Serializer round-trip:** ghi/đọc state chứa String, Long, Integer, Boolean; xác minh cả giá trị và kiểu.
2. **Empty/default state:** context thiếu key bắt buộc phải fail rõ; không tự đọc toàn bộ nguồn nếu `inputKey` mất.
3. **Custom type:** nếu thực sự dùng class nghiệp vụ, kiểm tra `Serializable`/trusted package/class compatibility; ưu tiên đổi sang ID typed.
4. **Metadata fixture cũ:** dùng serializer của bản mới đọc bytes từ DB của bản cũ trên **bản sao dữ liệu**.
5. **Message fixture cũ:** dùng consumer mới deserialize request/reply đang có trong broker theo contract.
6. **Rolling upgrade:** manager cũ–worker mới và manager mới–worker cũ trong giai đoạn hỗ trợ, không trộn protocol ngoài chính sách.
7. **Checkpoint sau commit:** worker commit 120 chunk rồi crash; restart tiếp tục đúng phần và không duplicate.
8. **DB metadata khác business DB:** mô phỏng lỗi giữa commit dữ liệu và checkpoint, xác minh writer replay-safe.
9. **Schema/version change:** đổi tên key hoặc type trong staging; kiểm tra bị chặn hoặc migration có test rõ ràng.
10. **Serializer security:** payload có class không được phép/không hợp lệ phải bị từ chối, không tạo object không tin cậy.
11. **Size limit:** state có nhiều key hoặc String bất thường; xác minh ngưỡng từ chối và giới hạn column/memory.
12. **Remote partitioning:** worker JVM mới tra được `StepExecutionContext` sau manager JVM restart.
13. **Remote chunking:** item codec và reply correlation tương thích; mất ack không gây side effect lặp.
14. **Reconciliation:** so sánh tập business key, payload/version, output thừa/thiếu sau các tình huống lỗi.
15. **Backup/restore:** repository metadata khôi phục cùng snapshot business data; worker đọc được checkpoint sau restore.

Nên có phép thử với **một partition hoàn thành** và **một partition thất bại**. Khi restart cùng `JobInstance`, partition đã hoàn thành thường được bỏ qua theo policy mặc định, partition lỗi tiếp tục từ context/checkpoint tương ứng. Nếu context bị lỗi deserialize, không được lặng lẽ tạo context rỗng rồi chạy lại từ đầu mà không có chính sách idempotency/reprocess.

## 15. Runbook khi deserialization lỗi ở production

Nếu worker mới liên tục báo lỗi mở `ExecutionContext` hoặc broker không giải mã được message, xử lý theo trình tự:

1. **Xác định lớp lỗi:** metadata repository hay broker message? Kiểm tra stack trace, class của serializer, mã exception, thời điểm thay version.
2. **Khoanh vùng:** job instance, step/partition, `JobExecutionId`/`StepExecutionId`, worker pod và phiên bản phần mềm.
3. **Ngừng retry vô hạn:** hạn chế admission/concurrency để tránh retry storm và làm đầy DLQ/DB.
4. **Bảo toàn bằng chứng:** backup metadata và tham chiếu message có kiểm soát; không sửa trực tiếp serialized column.
5. **Kiểm tra codec:** cấu hình ghi trước đây, cấu hình đọc hiện tại, Jackson trusted types/classpath hoặc Java class compatibility.
6. **Đánh giá worker đang hoạt động:** bảo đảm worker cũ không còn ghi cùng business key trước khi tiếp tục hoặc rollback rollout.
7. **Thử rollback/migration trên bản sao:** chứng minh đọc được checkpoint cũ và output đã commit giữ nguyên.
8. **Khôi phục có chủ đích:** quay lại phiên bản tương thích hoặc áp dụng migration đã kiểm thử; không tự đổi identifying `JobParameters` để bỏ qua metadata.
9. **Đối soát nghiệp vụ:** record đã commit, outbox/event, các side effect ở API; không chỉ nhìn trạng thái `COMPLETED`.
10. **Bổ sung regression test:** lưu fixture lỗi, thêm hợp đồng version và phép thử rolling deploy.

Không dùng giải pháp kiểu “bắt mọi deserialization exception rồi trả map rỗng”. Nếu reader được phục hồi từ đầu trong khi nghiệp vụ đã ghi một phần, cách đó có thể tạo duplicate hoặc làm hỏng thứ tự cập nhật.

## 16. Bài tập tự kiểm tra

Một job remote partitioning chạy qua ba JVM worker, mỗi worker xử lý các shard từ snapshot `orders-2026-11-25`. Manager sử dụng `DefaultExecutionContextSerializer` và lưu trong repository chung. Sau 70 phút:

- `partition0000` đã `COMPLETED`.
- `partition0001` đã commit 100 chunk, sau đó `FAILED`.
- `partition0002` đã commit 80 chunk, nhưng worker chết trước khi manager nhận kết quả.
- Nhóm triển khai phiên bản worker mới. Phiên bản mới đổi class custom `com.acme.batch.CheckpointV1` thành `com.acme.batch.state.CheckpointV2`, đồng thời đổi message converter từ định dạng A sang B.
- Broker vẫn giữ một số request cũ ở định dạng A.

**Câu hỏi:**

1. Vì sao việc đổi tên class checkpoint có thể khiến worker mới không đọc được state từ repository?
2. Vì sao đổi message converter có thể gây lỗi **khác** với lỗi đọc `ExecutionContext`?
3. Nếu không thay codec metadata nhưng worker thiếu class cũ, có thể round-trip bằng cùng serializer vẫn thất bại không?
4. Có nên sửa trực tiếp `SHORT_CONTEXT` hoặc reset context thành rỗng để job chạy tiếp không?
5. Nếu `partition0002` đã commit nhưng reply mất, dùng `stepExecutionId` mới làm business idempotency key có đủ an toàn không?
6. Một cách thiết kế state ngay từ đầu để giảm rủi ro là gì?
7. Cần kiểm thử gì trước khi deploy phiên bản mới tiếp theo?

**Gợi ý đáp án:**

- (1) Java serialization có thể cần tên class/`serialVersionUID` và graph tương thích; đổi package/class làm dữ liệu cũ khó tái tạo.
- (2) Broker message converter xử lý request/reply trên wire, còn repository serializer xử lý checkpoint lưu DB; hai lớp có định dạng/consumer khác nhau.
- (3) Có. Codec được chọn giống nhau nhưng thiếu class hoặc kiểu không tương thích vẫn gây lỗi.
- (4) Không. Phải sao lưu, dùng API/framework/migration được kiểm thử và bảo toàn tiến độ nghiệp vụ.
- (5) Không. ID thực thi có thể đổi giữa các attempt; cần business key ổn định theo snapshot/record/operation.
- (6) Chỉ lưu String/Long/ID manifest/offset có contract rõ, không lưu object runtime hoặc class phức tạp.
- (7) Golden fixtures DB và message, thử rollback/forward compatibility, worker crash sau commit, restore, security và reconciliation.

## Tài liệu tham khảo

- [Spring Batch Reference – ExecutionContext](https://docs.spring.io/spring-batch/reference/domain.html): `JobExecution`, `StepExecution` và state dùng khi restart.
- [Spring Batch Reference – Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): repository, transaction và các tùy chọn persistence.
- [Spring Batch Reference – Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): bảng metadata và các cột execution context.
- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): partitioning, remote workers và `ExecutionContext`.
- [Spring Batch Reference – Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): request/reply, remote chunking và partitioning.
- [Spring Batch 5.2 Reference](https://docs.spring.io/spring-batch/reference/5.2/index.html): đối chiếu API serializer và cấu hình đúng release 5.x đang sử dụng.
- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/): serialization, message channels và middleware adapters.
- [Oracle Java Serialization Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/index.html): đặc điểm và ràng buộc Java object serialization.

## Ghi nhớ

**Serialization của `ExecutionContext` là điều kiện để Spring Batch lưu và khôi phục state phục vụ restart; nó khác với serialization message giữa manager và worker.** Trong một workload dữ liệu lớn chạy phân tán, hãy giữ context nhỏ và có kiểu ổn định, lưu input key/snapshot/checkpoint theo `StepExecution`, cấu hình codec tương thích với `JobRepository` và mọi thành phần đọc metadata, kiểm soát deserialization và thử đọc state từ phiên bản cũ. Mất reply hoặc thay codec không làm dữ liệu đã commit biến mất: worker phải replay an toàn bằng business key/idempotency và đối soát kết quả. Chỉ khi metadata, message protocol, transaction và cơ chế restart đều được kiểm chứng mới nên tăng số worker để mở rộng Spring Batch.
