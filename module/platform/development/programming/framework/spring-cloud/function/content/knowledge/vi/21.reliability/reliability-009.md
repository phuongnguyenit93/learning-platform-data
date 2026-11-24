
# Quản lý trạng thái dùng chung trong môi trường nhiều lần gọi

## 1. Mục tiêu bài học

Một Spring Cloud Function có thể được gọi hàng nghìn lần, từ nhiều HTTP request, message hoặc serverless invocation. Mỗi lần gọi có thể chạy trên cùng một JVM, một instance khác, hoặc một process vừa được khởi động. Nếu trạng thái nghiệp vụ chỉ nằm trong field của bean hay biến static, lần gọi sau không có bảo đảm sẽ nhìn thấy đúng dữ liệu; hai lần gọi đồng thời còn có thể ghi đè kết quả của nhau.

Trong module **SPRING_CLOUD_FUNCTION**, logic nghiệp vụ được tổ chức bằng `Supplier`, `Function` và `Consumer`, đăng ký qua `FunctionCatalog`, ghép thành pipeline và triển khai độc lập với giao thức HTTP, event hoặc serverless. Mô hình function khuyến khích xử lý input thành output; khi nghiệp vụ cần nhớ dữ liệu qua nhiều lần gọi, trạng thái phải có nơi lưu trữ và quy tắc đồng bộ rõ ràng.

Bài thuộc chương **Độ tin cậy**, tập trung vào **quản lý trạng thái dùng chung trong môi trường nhiều lần gọi**. Sau bài học, bạn có thể:

- Phân biệt dữ liệu chỉ tồn tại trong một invocation với trạng thái cần chia sẻ lâu dài.
- Hiểu vì sao mutable field, `static` và local memory không phải nguồn dữ liệu dùng chung đáng tin cậy.
- Chọn database, distributed cache, event log hoặc object storage theo loại trạng thái.
- Thiết kế key có tenant, aggregate và version để tránh va chạm.
- Cập nhật trạng thái an toàn khi nhiều invocation chạy đồng thời.
- Tổ chức Function thuần, application service và state store.
- Quản lý cache, TTL, event ordering, idempotency và state migration.
- Kiểm thử nhiều instance, restart, race condition và dữ liệu tenant khác nhau.

> **Nguyên tắc xuyên suốt:** Invocation là một lần thực thi; instance là một process có thể bị thay thế. Nếu dữ liệu cần tồn tại qua invocation hoặc được nhiều instance chia sẻ, hãy lưu nó trong một hệ thống có durability và concurrency semantics phù hợp. Bộ nhớ cục bộ chỉ là cache/tối ưu, trừ khi nghiệp vụ chủ ý giới hạn trong đúng một process.

## 2. Invocation không đồng nghĩa với instance

Spring Cloud Function cho phép cùng một function được gọi từ nhiều adapter. Mỗi lần gọi là một invocation; invocation có thể được xử lý bởi cùng instance hoặc instance khác.

~~~text
                 ┌──────────────────────┐
HTTP request ───>│                      │
Message event ──>│  Function adapter   │
Serverless event>│                      │
                 └──────────┬───────────┘
                            |
                            v
                    Function invocation
                            |
                 ┌──────────┴──────────┐
                 v                     v
             Instance A            Instance B
                 |                     |
                 +---------+-----------+
                           |
                           v
                    Shared state store
~~~

Trong môi trường scale out, nhiều instance có thể xử lý đồng thời. Trong serverless, runtime có thể tái sử dụng một instance cho nhiều invocation hoặc khởi tạo instance mới; không nên dựa vào việc instance chắc chắn được giữ lại.

### 2.1. Những điều không được bảo đảm

- Invocation tiếp theo chạy trên cùng JVM.
- Hai message cùng aggregate luôn được xử lý tuần tự.
- Một biến `static` được chia sẻ giữa nhiều container/replica.
- Instance không restart giữa hai lần gọi.
- Memory của instance được giữ sau scale-to-zero.
- Sticky session hoặc routing luôn đưa cùng người dùng tới cùng instance.
- Một lần ghi local đã được replicate sang instance khác.

Các đặc tính này phụ thuộc adapter, platform, concurrency và deployment. Thiết kế nghiệp vụ cần đúng ngay cả khi hai invocation cùng lúc chạy ở hai instance khác nhau.

### 2.2. Một bean Function thường sống lâu hơn một invocation

Bean Spring thường là singleton theo application context. Vì vậy, một field mutable trong bean có thể được nhiều thread truy cập cùng lúc:

~~~java
@Bean
public Function<Command, Result> process() {
    Map<String, Result> recentResults = new HashMap<>();

    return command -> {
        Result result = calculate(command);
        recentResults.put(command.id(), result);
        return result;
    };
}
~~~

Ví dụ này có hai vấn đề:

1. `HashMap` không an toàn khi nhiều thread cùng ghi/đọc.
2. Dữ liệu chỉ tồn tại trong instance hiện tại; restart hoặc request sang instance khác sẽ không thấy.

Đổi sang `ConcurrentHashMap` chỉ giải quyết một phần concurrency trong một JVM. Nó không làm dữ liệu bền vững, không chia sẻ qua replica và không tạo transaction với database.

## 3. Phân loại trạng thái trước khi chọn nơi lưu

Không phải mọi dữ liệu đều cần database. Trước hết hãy xác định vòng đời và mức độ nhất quán cần thiết.

| Loại dữ liệu | Ví dụ | Vòng đời | Nơi lưu phù hợp |
|---|---|---|---|
| Cấu hình bất biến | Thuế suất mặc định, endpoint | Theo deployment | Configuration/properties |
| Input của invocation | Command, headers, correlation ID | Một lần gọi | Tham số/Message |
| Dữ liệu tạm trong pipeline | Kết quả validation, intermediate DTO | Một lần gọi | Biến local/Function composition |
| Trạng thái nghiệp vụ | Order status, payment state | Qua nhiều invocation | Database/state store |
| Session/workflow | Wizard state, job progress | Nhiều request/event | DB hoặc distributed state store |
| Cache | Giá sản phẩm đọc nhiều | Có TTL, có thể tái tạo | Cache local/distributed |
| Event history | OrderCreated, PaymentCaptured | Theo retention/audit | Event log/event store |
| File lớn | Báo cáo, payload blob | Dài hạn | Object storage, DB giữ metadata |
| Metric/trace | Latency, count | Theo retention telemetry | Monitoring backend |

### 3.1. Cấu hình không phải trạng thái nghiệp vụ

Giá trị cấu hình đọc lúc khởi động có thể nằm trong bean nếu bất biến trong vòng đời context. Nếu cấu hình được thay đổi động, cần cơ chế refresh/version rõ ràng; không biến một field thành nguồn sự thật mà không biết ai cập nhật.

### 3.2. Dữ liệu trung gian nên ở trong invocation

Kết quả normalize/validate/calculate chỉ cần cho một pipeline thì truyền qua Function composition:

~~~text
OrderCommand
    |
    v
normalizeOrder
    |
    v
validateOrder
    |
    v
calculateQuote
    |
    v
Quote
~~~

Không cần ghi mọi intermediate value vào global map. Giữ dữ liệu local giúp dễ kiểm thử, giảm coupling và tránh cleanup state tạm.

### 3.3. Trạng thái nghiệp vụ phải có owner

Mỗi loại state nên có một owner rõ:
- Service nào được quyền tạo/cập nhật?
- Key nào định danh một aggregate?
- Quy tắc chuyển trạng thái hợp lệ là gì?
- Ai được đọc và ai được ghi?
- Có cần audit/history không?
- Retention và xóa dữ liệu theo policy nào?

Không để nhiều function bean tự sửa cùng một bảng theo các quy tắc khác nhau mà không có một application service/state transition owner.

## 4. Vì sao mutable state trong Function bean nguy hiểm?

Một ví dụ counter đơn giản:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CounterFunctions {

    private long counter = 0;

    @Bean
    public Supplier<Long> nextCounter() {
        return () -> ++counter;
    }
}
~~~

Với một instance và một thread, ví dụ có vẻ hoạt động. Nhưng khi nhiều invocation đồng thời, phép `++` không atomic; hai thread có thể cùng đọc một giá trị và trả về cùng số. Khi có hai instance, mỗi instance lại có counter riêng. Khi restart, counter trở về 0.

### 4.1. AtomicLong vẫn chỉ atomic trong một process

~~~java
private final AtomicLong counter = new AtomicLong();
~~~

`AtomicLong` bảo đảm thao tác nguyên tử giữa các thread dùng chung object trong một JVM. Nó không:
- Chia sẻ giá trị qua hai container.
- Ghi bền vững qua restart.
- Đồng bộ với database.
- Ngăn cùng operation được thực hiện hai lần sau redelivery.

Dùng `AtomicLong` cho metric/local sequence không quan trọng có thể hợp lý; dùng nó làm ID nghiệp vụ toàn hệ thống thì không.

### 4.2. Static không phải distributed storage

`static` gắn với classloader trong một process. Hai pod có hai vùng static riêng. Khi rolling deployment, pod mới không tự nhận state của pod cũ. Nếu cần ID duy nhất, dùng database sequence, UUID/ULID hoặc dịch vụ định danh phù hợp thay vì tự tăng static counter.

### 4.3. Thread-safe không đồng nghĩa với nghiệp vụ an toàn

`ConcurrentHashMap` có thể bảo vệ cấu trúc map, nhưng chuỗi thao tác đọc → tính → ghi vẫn có race:

~~~java
Integer oldValue = map.get(key);
Integer newValue = oldValue + delta;
map.put(key, newValue);
~~~

Hai thread cùng đọc 10, mỗi thread cộng 1, rồi cùng ghi 11. Kết quả đúng phải là 12. Dùng `compute` có thể atomic trong một map cục bộ, nhưng vẫn không giải quyết nhiều instance hoặc durability.

## 5. Nguyên tắc thiết kế Function stateless

Function stateless không có nghĩa hệ thống không lưu trạng thái. Nó có nghĩa kết quả của invocation được xác định bởi input, context cần thiết và state store được quản lý rõ ràng, thay vì một field ẩn trong bean.

### 5.1. Function thuần

~~~java
@Bean
public Function<NormalizeCommand, NormalizedCommand> normalize() {
    return command -> new NormalizedCommand(
            command.tenantId(),
            command.orderId().trim().toUpperCase(),
            command.quantity());
}
~~~

Cùng input tạo cùng output và không sửa shared state. Function thuần dễ test và có thể chạy lại.

### 5.2. Function có đọc state

Một function có thể nhận service để đọc dữ liệu hiện tại:

~~~java
@Bean
public Function<OrderId, OrderView> getOrder(OrderQueryService queryService) {
    return queryService::findView;
}
~~~

Function vẫn không giữ state trong field. Service lấy state từ nguồn lưu trữ có owner, quyền truy cập và consistency được định nghĩa.

### 5.3. Consumer có side effect

~~~java
@Bean
public Consumer<OrderUpdated> updateOrder(OrderApplicationService service) {
    return service::apply;
}
~~~

Consumer có thể cập nhật state, nhưng transaction, idempotency, validation và concurrency cần nằm trong application service/repository. Không để mỗi adapter tự viết một bản cập nhật khác nhau.

### 5.4. FunctionCatalog chỉ đăng ký và tra cứu function

`FunctionCatalog` hỗ trợ lookup theo tên và kiểu function. Nó không phải state store, cache phân tán hay transaction coordinator. Composition như:

~~~text
normalizeOrder|validateOrder|calculateQuote|recordQuote
~~~

chỉ mô tả chuỗi xử lý. Nếu `recordQuote` ghi database, chính application service/repository chịu trách nhiệm lưu bền vững và bảo vệ cập nhật đồng thời.

## 6. Chọn storage theo semantics của state

| Storage | Phù hợp | Điểm cần cân nhắc |
|---|---|---|
| Relational database | State nghiệp vụ, transaction, unique key, query | Lock, isolation, schema migration, connection pool |
| Redis/distributed cache | Lookup nhanh, counter/lease/TTL, ephemeral shared state | Persistence/replication config, eviction, failover, atomic scripts |
| Event log/event store | Lịch sử thay đổi, replay, audit | Ordering, projection, schema evolution, replay cost |
| Kafka compacted topic | State snapshot theo key hoặc changelog | Eventual visibility, partition ordering, consumer offset |
| Object storage | Blob/file lớn, artifact, snapshot | Không phù hợp read-modify-write nhỏ có concurrency cao |
| Local cache | Giảm latency cho dữ liệu có thể tái tạo | Stale data, mỗi instance một bản, invalidation |

### 6.1. Nguồn sự thật và cache

Chọn một **source of truth** cho mỗi aggregate. Cache có thể tăng tốc đọc nhưng không nên trở thành bản ghi duy nhất của trạng thái quan trọng nếu cache có thể evict/restart theo cấu hình.

Mô hình cache-aside:

~~~text
Read state
   |
   v
Cache hit? ---- yes ----> Return cached view
   |
   no
   v
Read source of truth
   |
   v
Populate cache with TTL
   |
   v
Return
~~~

Khi cập nhật state, cần quy tắc invalidate/update cache. Nếu ghi DB thành công nhưng invalidate cache thất bại, client có thể đọc dữ liệu cũ. Với state quan trọng, cân nhắc outbox/cache invalidation event, version check hoặc TTL ngắn phù hợp.

### 6.2. Cache local và cache phân tán

Cache local có latency thấp nhưng mỗi instance có bản riêng. Nó phù hợp dữ liệu reference có thể stale trong một khoảng cho phép, không phù hợp làm state duy nhất cho session/job cần chia sẻ.

Cache phân tán cho phép nhiều instance đọc cùng hệ thống cache, nhưng vẫn cần hiểu consistency, eviction, replication, persistence và failover. “Distributed” không tự có nghĩa dữ liệu không thể mất.

### 6.3. Redis counter và atomic operation

Redis có các lệnh atomic như `INCRBY`; một thao tác tăng counter có thể an toàn hơn read-modify-write ở client. Nhưng cần chọn key, TTL, persistence và failover phù hợp. Nếu counter là dữ liệu tài chính/audit bắt buộc không mất, đánh giá DB transaction và durable log thay vì chỉ dựa vào cache.

## 7. Thiết kế key và phạm vi truy cập

Một key state cần định danh đúng đối tượng và tenant. Ví dụ:

~~~text
tenant:{tenantId}:order:{orderId}
tenant:{tenantId}:session:{sessionId}
tenant:{tenantId}:job:{jobId}
~~~

Không dùng riêng `orderId` nếu các tenant có thể trùng ID. Không dùng username/email làm key duy nhất nếu có thể thay đổi hoặc tái sử dụng.

### 7.1. Key phải phản ánh business identity

Phân biệt:
- **Tenant ID:** phạm vi khách hàng/tổ chức.
- **Aggregate ID:** order, account, workflow.
- **Operation ID:** một lần yêu cầu/command.
- **Event ID:** một event được phát.
- **Version:** phiên bản state hoặc thứ tự cập nhật.

Event ID giúp nhận biết delivery trùng; aggregate ID định danh state; operation ID giúp retry cùng thao tác; version giúp phát hiện cập nhật cũ.

### 7.2. Authorization độc lập với key

Biết một state key không có nghĩa được quyền đọc/ghi. Mỗi invocation phải xác thực principal và kiểm tra tenant/permission trước khi truy cập. Không nhận `tenantId` từ payload rồi tin ngay; derive hoặc đối chiếu với identity đã xác thực.

### 7.3. Tránh key không có giới hạn

Key do client gửi cần giới hạn độ dài/charset, chuẩn hóa và tránh cho phép tạo vô hạn namespace. Nếu key được đưa vào Redis/database, cần kiểm soát cardinality và quota để tránh một client tạo quá nhiều state tạm.

## 8. Cập nhật state an toàn khi nhiều invocation đồng thời

Một state store dùng chung không tự ngăn lost update. Cần thao tác atomic hoặc kiểm soát version/lock tại nơi lưu trữ.

### 8.1. Lost update khi read-modify-write

Giả sử counter đang là 10:

~~~text
Invocation A                 Invocation B
-------------                 -------------
READ value = 10
                              READ value = 10
value = 11
                              value = 11
WRITE 11
                              WRITE 11
~~~

Hai invocation đều thành công nhưng kết quả chỉ tăng một đơn vị. Đây là race condition dù database là shared store.

### 8.2. Atomic update tại database

Thay vì đọc rồi ghi ở client, thực hiện phép tăng trong một câu lệnh SQL:

~~~sql
INSERT INTO counter_state (
    tenant_id, counter_id, value, version
)
VALUES (
    :tenantId, :counterId, :delta, 1
)
ON CONFLICT (tenant_id, counter_id)
DO UPDATE SET
    value = counter_state.value + EXCLUDED.value,
    version = counter_state.version + 1
RETURNING value, version;
~~~

Với PostgreSQL, thao tác `INSERT ... ON CONFLICT DO UPDATE` trên một row được database điều phối nguyên tử. Các invocation đồng thời trên cùng key được serialize ở row conflict/lock; mỗi phép tăng được áp dụng một lần cho mỗi lần câu lệnh thực sự chạy thành công. Cần kiểm tra isolation, retry deadlock và semantics của database đang dùng.

### 8.3. Bảng và port minh họa

~~~sql
CREATE TABLE counter_state (
    tenant_id   VARCHAR(80) NOT NULL,
    counter_id  VARCHAR(120) NOT NULL,
    value       BIGINT NOT NULL,
    version     BIGINT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, counter_id)
);

CREATE TABLE processed_operation (
    tenant_id       VARCHAR(80) NOT NULL,
    operation_id    VARCHAR(120) NOT NULL,
    counter_id      VARCHAR(120) NOT NULL,
    command_hash    CHAR(64) NOT NULL,
    result_value    BIGINT,
    result_version  BIGINT,
    PRIMARY KEY (tenant_id, operation_id)
);
~~~

Port storage:

~~~java
package example.functions;

public interface CounterStore {
    CounterSnapshot incrementAndRead(
            String tenantId, String counterId, long delta);
}

public interface ProcessedOperationStore {
    boolean insertIfAbsent(
            String tenantId, String operationId,
            String commandHash, String counterId);

    String findCommandHash(String tenantId, String operationId);

    CounterSnapshot findResult(
            String tenantId, String operationId);

    void saveResult(
            String tenantId, String operationId,
            CounterSnapshot result);
}
~~~

Các method `insertIfAbsent` và `saveResult` cần dùng cùng transaction manager với `CounterStore`. Bản triển khai PostgreSQL của `incrementAndRead` chạy câu lệnh `RETURNING` ở trên và ánh xạ kết quả thành record.

### 8.4. Application service chống gửi lặp

~~~java
package example.functions;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CounterService {

    private final CounterStore counters;
    private final ProcessedOperationStore operations;
    private final TenantAccess tenantAccess;
    private final CommandFingerprint fingerprint;

    public CounterService(
            CounterStore counters,
            ProcessedOperationStore operations,
            TenantAccess tenantAccess,
            CommandFingerprint fingerprint) {
        this.counters = counters;
        this.operations = operations;
        this.tenantAccess = tenantAccess;
        this.fingerprint = fingerprint;
    }

    @Transactional
    public CounterSnapshot increment(IncrementCommand command) {
        String tenantId = tenantAccess.requireTenantId();
        String commandHash = fingerprint.hash(command);

        boolean claimed = operations.insertIfAbsent(
                tenantId, command.operationId(),
                commandHash, command.counterId());

        if (!claimed) {
            String oldHash = operations.findCommandHash(
                    tenantId, command.operationId());
            if (!commandHash.equals(oldHash)) {
                throw new OperationKeyConflictException(
                        "Operation ID reused with a different command");
            }
            CounterSnapshot previous = operations.findResult(
                    tenantId, command.operationId());
            if (previous == null) {
                throw new IllegalStateException(
                        "Committed operation has no stored result");
            }
            return previous;
        }

        CounterSnapshot result = counters.incrementAndRead(
                tenantId, command.counterId(), command.delta());

        operations.saveResult(
                tenantId, command.operationId(), result);

        return result;
    }
}
~~~

Các record/port phụ trợ:

~~~java
package example.functions;

public record IncrementCommand(
        String operationId, String counterId, long delta) {}

public record CounterSnapshot(long value, long version) {}

public interface TenantAccess {
    String requireTenantId();
}

public interface CommandFingerprint {
    String hash(IncrementCommand command);
}
~~~

~~~java
package example.functions;

public class OperationKeyConflictException extends RuntimeException {
    public OperationKeyConflictException(String message) {
        super(message);
    }
}
~~~

`TenantAccess` lấy tenant từ principal/context đã xác thực; không tin tenant do client tùy ý truyền. `operationId` là định danh ổn định cho một lần yêu cầu. `CommandFingerprint` tính hash ở server từ command đã validate/normalize, không nhận hash do client gửi. Nếu cùng operation được gửi lại với cùng fingerprint, service trả snapshot đã lưu và không tăng lần nữa.

Đây là ví dụ create-once cho một operation. Nếu cùng `operationId` được gửi với `counterId` hoặc `delta` khác, fingerprint khác và service báo conflict thay vì trả kết quả cũ mà không kiểm tra payload.

### 8.5. Function chỉ làm boundary mỏng

~~~java
@Configuration
public class CounterFunctions {

    @Bean
    public Function<IncrementCommand, CounterSnapshot> incrementCounter(
            CounterService service) {
        return service::increment;
    }
}
~~~

Function bean không giữ counter trong field. Mỗi invocation gọi service; service quản lý tenant, idempotency và transaction. Nếu cùng Function được bind qua HTTP hoặc message, quy tắc cập nhật state vẫn nằm ở cùng application service.

### 8.6. Atomicity không có nghĩa mọi nghiệp vụ đều là phép cộng

Một câu lệnh atomic phù hợp với counter, nhưng cập nhật order có thể cần kiểm tra trạng thái hiện tại, hạn mức và nhiều bảng. Khi đó dùng transaction, version/lock và state transition hợp lệ. Đừng gom mọi logic thành một Redis `INCR` chỉ vì thao tác đó atomic.

## 9. Optimistic locking và pessimistic locking

Khi nhiều invocation cập nhật cùng aggregate, có thể dùng version để phát hiện xung đột.

### 9.1. Optimistic locking với version

Một entity JPA có thể dùng `@Version`:

~~~java
@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private String id;

    private String tenantId;

    private String status;

    @Version
    private long version;

    // getters/setters/constructor omitted
}
~~~

Khi update, JPA dùng version hiện tại trong điều kiện ghi. Nếu invocation khác đã commit version mới, update hiện tại không khớp và provider báo optimistic-lock failure. Ứng dụng phải quyết định đọc lại, kiểm tra business rule và retry transaction khi an toàn.

Optimistic locking phù hợp khi xung đột không thường xuyên. Nó không tự giải quyết duplicate command; operation idempotency vẫn cần thiết.

### 9.2. Pessimistic locking

Có thể khóa row trong transaction khi đọc để cập nhật, ví dụ `SELECT ... FOR UPDATE` hoặc JPA lock mode. Invocation khác phải chờ lock hoặc timeout.

Dùng khi cần tuần tự hóa cập nhật trên một aggregate và contention có thể chấp nhận. Cần:
- Transaction ngắn.
- Thứ tự lấy lock nhất quán để giảm deadlock.
- Lock timeout và xử lý deadlock.
- Không gọi remote service khi đang giữ lock.

### 9.3. Chọn cơ chế theo loại invariant

| Nhu cầu | Cơ chế thường phù hợp |
|---|---|
| Tăng counter | Atomic SQL/Redis command |
| Tránh ghi đè version cũ | Optimistic locking/CAS |
| Chuyển trạng thái phức tạp trên một row | Transaction + row lock hoặc version |
| Một operation chỉ được thực hiện một lần | Unique operation key + transaction |
| Giới hạn quota nhiều row | Transaction/isolation hoặc counter atomic được thiết kế kỹ |
| Phân phối lease/claim | Storage có conditional update/lease semantics |

Không dùng distributed lock làm giải pháp đầu tiên nếu unique constraint/atomic update trong database đã bảo vệ được invariant.

## 10. Trạng thái workflow và state transition

State dùng chung không chỉ là giá trị để đọc/ghi. Nó thường biểu diễn một workflow với các trạng thái hợp lệ.

Ví dụ order:

~~~text
NEW
 |
 v
VALIDATED
 |
 v
RESERVED
 |
 v
PAID
 |
 v
COMPLETED
~~~

Một event cũ không được phép đưa order từ `COMPLETED` trở về `RESERVED` chỉ vì nó đến muộn.

### 10.1. Định nghĩa transition hợp lệ

~~~java
public enum OrderStatus {
    NEW, VALIDATED, RESERVED, PAID, COMPLETED, CANCELLED
}

public OrderStatus transition(
        OrderStatus current, OrderEvent event) {

    return switch (current) {
        case NEW -> switch (event.type()) {
            case VALIDATED -> OrderStatus.VALIDATED;
            case CANCELLED -> OrderStatus.CANCELLED;
            default -> throw new InvalidTransitionException();
        };
        case VALIDATED -> switch (event.type()) {
            case RESERVED -> OrderStatus.RESERVED;
            case CANCELLED -> OrderStatus.CANCELLED;
            default -> throw new InvalidTransitionException();
        };
        case RESERVED -> switch (event.type()) {
            case PAID -> OrderStatus.PAID;
            case CANCELLED -> OrderStatus.CANCELLED;
            default -> throw new InvalidTransitionException();
        };
        case PAID -> {
            if (event.type() == EventType.COMPLETED) {
                yield OrderStatus.COMPLETED;
            }
            throw new InvalidTransitionException();
        }
        case COMPLETED, CANCELLED ->
                throw new InvalidTransitionException();
    };
}
~~~

Đoạn code minh họa cần các enum/exception tương ứng trong ứng dụng. Điểm chính là transition phải kiểm tra state hiện tại và event, không chỉ gán một chuỗi trạng thái do message gửi lên.

### 10.2. Version và thứ tự event

Mỗi aggregate có thể giữ `version` tăng dần. Event chứa aggregate ID và sequence/version. Consumer:
- Chấp nhận event kế tiếp đúng version.
- Nhận diện event cũ/đã xử lý.
- Phát hiện gap nếu event đến trước event cần thiết.
- Không áp dụng event stale lên state mới hơn.

Với Kafka, partition key theo aggregate có thể giữ thứ tự trong một partition, nhưng không bảo đảm thứ tự xuyên nhiều topic/producer hoặc hệ thống khác. Database version vẫn là hàng rào bảo vệ ở consumer.

### 10.3. Event sourcing không phải yêu cầu mặc định

Event sourcing lưu event như nguồn dữ liệu chính rồi dựng state bằng projection. Nó hữu ích khi cần lịch sử đầy đủ, audit, replay hoặc nhiều projection. Đổi lại, cần quản lý schema evolution, ordering, snapshot và chi phí replay.

Nếu chỉ cần lưu trạng thái hiện tại cùng audit log, relational table và outbox có thể đơn giản hơn. Không chọn event sourcing chỉ vì hệ thống có message.

## 11. Truyền context qua invocation, không truyền state bằng biến ẩn

Một request thường mang metadata như correlation ID, tenant, locale, deadline hoặc security principal. Metadata này giúp xử lý đúng invocation; nó không thay thế trạng thái nghiệp vụ bền vững.

### 11.1. Phân biệt payload, metadata và durable state

| Thành phần | Ví dụ | Cách truyền/lưu |
|---|---|---|
| Payload nghiệp vụ | OrderCommand, PaymentCommand | Function input/Message payload |
| Metadata invocation | Correlation ID, trace ID, deadline | Message headers hoặc execution context |
| Identity/authorization | Principal, scopes, tenant đã xác thực | Security context được xác minh |
| Durable state | Order status, workflow progress | Database/state store |
| Cache key/version | Aggregate ID, version | Tính từ identity và state |

Không nhét toàn bộ state vào HTTP header hoặc message header. Header phù hợp cho metadata nhỏ; dữ liệu nghiệp vụ cần kiểm tra tính hợp lệ, version và quyền truy cập tại application service.

### 11.2. Spring Message headers

Spring Cloud Function có thể nhận/trả `Message<T>` để làm việc với headers:

~~~java
@Bean
public Function<Message<OrderCommand>, Message<OrderAccepted>> acceptOrder(
        OrderApplicationService service) {

    return message -> {
        OrderAccepted result = service.accept(message.getPayload());

        return MessageBuilder.withPayload(result)
                .setHeader(
                        "correlationId",
                        message.getHeaders().get("correlationId"))
                .build();
    };
}
~~~

Đây là minh họa việc giữ correlation metadata bằng header ứng dụng `correlationId`. Import `Message` từ Spring Messaging và `MessageBuilder` từ Spring Messaging support. Không copy mọi header tùy ý sang output; chỉ giữ những header được cho phép và cần thiết.

Header tenant do producer/client gửi không tự đáng tin. Adapter phải xác thực identity và ánh xạ tenant từ security context; application service vẫn kiểm tra quyền trên state key.

### 11.3. Correlation ID không phải operation ID

Correlation ID nối log/trace của một luồng xử lý. Operation ID định danh một thao tác nghiệp vụ có thể được retry. Một request mới có thể có correlation ID mới nhưng cùng operation ID nếu đó là retry có chủ đích.

Không dùng trace ID làm idempotency key vì trace có thể đổi qua mỗi lần gọi.

### 11.4. Reactor Context khác ThreadLocal

Reactive pipeline có thể đổi thread giữa các operator. `ThreadLocal` không tự theo subscription/context qua scheduler. Reactor cung cấp `Context` để truyền metadata theo subscriber:

~~~java
Mono<OrderView> view = Mono.deferContextual(context -> {
    String tenantId = context.get("tenantId");
    return orderService.findForTenant(tenantId, orderId);
}).contextWrite(context ->
        context.put("tenantId", authenticatedTenantId));
~~~

Ví dụ minh họa cách đọc/ghi Reactor Context; cần xác minh cách security/context được bridge bởi stack đang dùng. Không tự đặt tenant từ payload chưa xác thực.

Nếu code blocking cần ThreadLocal, phải có cơ chế context propagation tương ứng và cleanup; không để dữ liệu của request trước rò sang task khác trên thread pool.

### 11.5. Function composition phải giữ context cần thiết

Khi ghép nhiều Function, hãy quyết định metadata nào cần đi tiếp và metadata nào chỉ dùng tại boundary. Có thể dùng envelope có kiểu rõ ràng hoặc `Message<T>`; không dựa vào biến static để “nhớ” correlation ID/tenant giữa các bước.

## 12. State qua HTTP, messaging và serverless

Cùng một application service có thể được gọi bởi nhiều adapter, nhưng lifecycle state khác nhau.

### 12.1. HTTP request và session

HTTP request thường độc lập. Nếu cần session server-side, lưu session trong shared session store hoặc dịch vụ session phù hợp; không để session chỉ nằm trong memory của một web instance nếu load balancer có thể chuyển request sang instance khác.

Một token stateless như `JWT` mang claims đã ký, nhưng không tự cập nhật được trạng thái thu hồi hoặc thay đổi quyền ngay lập tức. Nếu cần logout/revocation, session version hoặc quyền thay đổi tức thời, phải có cơ chế tra cứu/revocation store hoặc thời hạn token phù hợp.

Sticky session có thể giảm việc đổi instance nhưng không phải durability guarantee; instance vẫn có thể restart hoặc scale down.

### 12.2. Message consumer

Một message có thể được giao lại hoặc được xử lý trên consumer instance khác. State workflow cần lưu trong DB/shared store và gắn với event/operation key. Không dùng biến field của Consumer để nhớ message đã xử lý.

Nếu nhiều event của cùng aggregate có thể chạy đồng thời, dùng partition key, serialization theo aggregate, optimistic locking hoặc transaction phù hợp. Partition ordering chỉ có phạm vi broker/partition, không thay thế version check ở state store.

### 12.3. Serverless invocation

Invocation có thể chạy trên instance mới và memory không được bảo đảm giữ lại. Trạng thái job/session/order phải ở storage bên ngoài với durability phù hợp. Nếu platform có ephemeral local disk hoặc execution context, chỉ dùng cho dữ liệu tạm có thể tạo lại.

### 12.4. Đừng serialize toàn bộ state vào event

Event nên mô tả sự kiện hoặc thay đổi có ý nghĩa, không nhất thiết chứa bản sao đầy đủ của mọi state. Payload lớn dễ lỗi schema, tăng chi phí và làm dữ liệu cũ lan rộng. Chọn giữa event chứa đủ dữ liệu để consumer xử lý và event tham chiếu state theo ID/version dựa trên yêu cầu consistency và coupling.

## 13. Cache consistency và invalidation

Cache giúp giảm tải nhưng tạo một bản sao state. Cần xác định stale data chấp nhận được bao lâu và ai chịu trách nhiệm invalidate.

### 13.1. Cache-aside có thể đọc stale sau update

~~~text
Writer A:
  DB update value = 20
  cache invalidation thất bại

Reader B:
  cache hit value = 10
  trả dữ liệu cũ
~~~

Nếu dữ liệu dùng để hiển thị có thể stale trong vài giây, TTL có thể đủ. Nếu state dùng để quyết định thanh toán/hạn mức/quyền truy cập, đọc từ cache stale có thể gây sai nghiệp vụ; cần version/consistency strategy mạnh hơn.

### 13.2. Invalidate trước hay sau DB update?

- Invalidate trước DB update: reader có thể tải giá trị cũ từ DB vào cache trước khi DB commit.
- Invalidate sau DB update: process có thể chết sau commit nhưng trước invalidation.
- Update cache trực tiếp: cache và DB có thể lệch nếu một trong hai ghi thất bại.

Không có thứ tự hai lệnh độc lập nào tự tạo atomicity giữa DB và cache. Có thể dùng outbox phát cache invalidation event sau commit, versioned cache key hoặc TTL để giới hạn stale window.

### 13.3. Versioned cache key

Nếu state có version, cache key có thể bao gồm version hoặc cache value giữ version. Reader kiểm tra version mong muốn để tránh dùng dữ liệu cũ. Cần nguồn biết version hiện tại; nếu việc đọc version cũng từ cache stale, vấn đề vẫn còn.

### 13.4. Cache stampede

Khi một key hết TTL, nhiều invocation có thể đồng thời miss rồi cùng gọi database/remote service. Dùng request coalescing, refresh ahead, jitter TTL hoặc lock có lease khi phù hợp. Không giữ lock vô hạn nếu worker chết; mọi lease cần expiry/recovery.

## 14. TTL, retention và vòng đời state

Không phải mọi state đều cần lưu vĩnh viễn. TTL/retention phải dựa trên nghiệp vụ và khả năng replay.

| State | Chính sách tham khảo |
|---|---|
| Cache giá/catalog | TTL ngắn, có thể tái tạo |
| Session tạm | Expiry theo thời gian không hoạt động và policy bảo mật |
| Job đang chạy | Không tự xóa khi còn trạng thái pending |
| Idempotency record | Giữ ít nhất hết cửa sổ retry/replay và yêu cầu nghiệp vụ |
| Order/payment state | Theo vòng đời và yêu cầu audit/pháp lý |
| Event log | Retention/archival theo replay và audit needs |
| Lock/lease | Expiry có fencing/recovery |
| Temporary upload | Cleanup sau khi hoàn tất hoặc hết hạn |

### 14.1. TTL không phải cơ chế state transition

Một job đang `PROCESSING` không nên biến mất chỉ vì TTL ngắn. Cần trạng thái terminal, retention sau terminal và quy trình cleanup riêng. Expiry không thay thế việc đánh dấu `COMPLETED`, `FAILED` hoặc `CANCELLED`.

### 14.2. Idempotency retention và replay window

Nếu xóa operation marker trước khi client/broker hết khả năng retry, thao tác cũ có thể được thực hiện lại. Retention phải tính:
- HTTP client retry window.
- Broker retention/redelivery/DLQ replay.
- Serverless retry horizon.
- Job replay thủ công.
- Yêu cầu audit và xóa dữ liệu.

Business uniqueness có thể là lớp bảo vệ dài hạn hơn marker delivery, nhưng phải phân biệt create với update hợp lệ.

### 14.3. Xóa dữ liệu và privacy

State store có thể chứa dữ liệu cá nhân/nhạy cảm. Thiết kế retention, access control, encryption, audit và deletion theo chính sách dữ liệu. Cache, backup, event log và dead-letter store cũng nằm trong phạm vi lưu giữ; xóa row nguồn chưa chắc xóa mọi bản sao.

## 15. Schema evolution và nhiều phiên bản Function cùng chạy

Trong rolling deployment, instance cũ và mới có thể cùng hoạt động trong một khoảng thời gian. Cả hai có thể đọc/ghi cùng state store; schema và quy tắc state phải tương thích trong giai đoạn chuyển tiếp.

### 15.1. Phân biệt state version và schema version

- **Aggregate version:** số thứ tự thay đổi của một order/account.
- **Schema version:** cấu trúc dữ liệu được serialize/lưu trữ.
- **Function version:** phiên bản code xử lý nghiệp vụ.
- **Event version:** phiên bản contract của message/event.

Không dùng một trường `version` cho mọi mục đích. Aggregate version giúp concurrency/order; schema version giúp đọc dữ liệu cũ; event version giúp tương thích producer/consumer.

### 15.2. Expand-migrate-contract

Một quy trình migration an toàn thường có ba giai đoạn:

~~~text
EXPAND
  Thêm field/table/index mới theo cách code cũ vẫn chạy được
       |
       v
MIGRATE
  Deploy code đọc được cả schema cũ/mới
  Backfill dữ liệu và quan sát
       |
       v
CONTRACT
  Chỉ bỏ field cũ khi không còn instance/consumer nào cần
~~~

Không deploy code mới yêu cầu một field bắt buộc trước khi mọi instance cũ đã ngừng ghi schema cũ. Với rolling deployment, hãy xác định tương thích đọc/ghi hai chiều trong giai đoạn chuyển tiếp.

### 15.3. Không serialize Java object tùy tiện làm durable format

Lưu object Java serialization gắn chặt dữ liệu với class/version và có rủi ro tương thích/bảo mật. Với state lâu dài, ưu tiên schema rõ ràng như JSON có version, Avro/Protobuf hoặc các cột relational; validate input và quản lý migration/upcaster.

### 15.4. Enum và field mới phải có chiến lược fallback

Nếu version Function mới thêm trạng thái `REFUND_PENDING`, instance cũ có thể không parse được enum mới. Cần rollout theo hướng tương thích, giữ unknown event/state có thể quarantine, hoặc đảm bảo không phát giá trị mới cho tới khi consumer cũ đã được nâng cấp.

Không map unknown state về `NEW` hoặc trạng thái mặc định một cách im lặng; có thể làm workflow quay lui sai.

### 15.5. Snapshot và projection cần được version hóa

Nếu dùng event sourcing hoặc materialized view, snapshot/projection có schema version riêng. Khi code projection thay đổi, cần rebuild hoặc upcast theo kế hoạch; không trộn snapshot của phiên bản cũ với event mới mà không kiểm tra compatibility.

## 16. Local cache, warm instance và dữ liệu reference

Local cache vẫn có giá trị nếu phân biệt rõ cache với nguồn sự thật.

### 16.1. Khi local cache phù hợp

- Dữ liệu reference ít thay đổi và có thể tải lại.
- Kết quả lookup không nhạy cảm với stale window ngắn.
- Cache có giới hạn size/TTL.
- Cache miss có thể đọc source of truth.
- Mỗi instance tự warm-up mà không ảnh hưởng tính đúng của nghiệp vụ.

Ví dụ: danh sách mã quốc gia, metadata sản phẩm công khai, cấu hình mapping bất biến theo version.

### 16.2. Không dùng warm instance làm persistence

Serverless có thể giữ instance ấm trong một khoảng thời gian, nhưng nền tảng có thể thu hồi bất cứ lúc nào. Warm cache chỉ cải thiện latency; invocation mới trên instance lạnh phải cho kết quả nghiệp vụ tương đương.

### 16.3. Cache version và refresh

Một cache entry nên mang version/updatedAt để có thể phát hiện dữ liệu stale. Có thể refresh theo TTL, event invalidation hoặc version check. Nếu refresh thất bại, quyết định dùng stale value phải dựa trên yêu cầu nghiệp vụ; với quyền truy cập hoặc số dư, fail-open có thể không an toàn.

### 16.4. Tránh cache chứa mutable object dùng chung

Nếu cache trả cùng một object mutable cho nhiều thread, caller có thể sửa object khiến các invocation khác nhìn thấy dữ liệu thay đổi ngoài ý muốn. Dùng immutable DTO/value object hoặc copy dữ liệu khi trả ra.

## 17. Consistency, availability và khi state store gặp sự cố

State store là dependency quan trọng. Khi nó chậm hoặc mất kết nối, Function cần có hành vi được định nghĩa thay vì tự fallback vào local mutable state.

### 17.1. Không chuyển sang local state để “cứ tiếp tục”

Nếu database không truy cập được, ghi tạm vào `HashMap` của từng instance sẽ tạo nhiều nhánh state không thể hợp nhất đáng tin cậy. Khi database trở lại, hai bản ghi có thể xung đột và không biết bản nào đúng.

Tùy nghiệp vụ, có thể:
- Từ chối nhanh và để adapter retry/DLQ.
- Ghi command vào durable queue/outbox khác đã được thiết kế.
- Chấp nhận degraded read-only với dữ liệu cache có TTL.
- Trả trạng thái pending và xử lý lại khi store phục hồi.

Không tự coi local memory là bản thay thế tương đương.

### 17.2. Read replica và consistency lag

Read replica có thể trễ so với primary. Nếu vừa ghi state rồi đọc ngay từ replica, invocation có thể nhìn thấy giá trị cũ. Với read-your-writes, đọc từ primary hoặc dùng version/consistency token phù hợp.

Không dùng replica read để quyết định một transition quan trọng nếu dữ liệu có thể stale.

### 17.3. Cache hoặc store có failover

Distributed cache/database có thể failover và có thời gian mất khả dụng hoặc mất một phần write tùy cấu hình durability. Hãy xác định:
- RPO/RTO.
- Persistence/replication policy.
- Acknowledgement level của write.
- Behavior khi leader đổi.
- Recovery và reconciliation.
- Backup/restore test.

Từ “shared” không đồng nghĩa “durable”; từ “replicated” không tự đồng nghĩa “không mất dữ liệu”.

### 17.4. Fail closed hay fail open?

| State được dùng để | Hành vi thường cân nhắc khi store lỗi |
|---|---|
| Authorization/tenant access | Fail closed |
| Số dư/hạn mức/payment | Không chấp nhận quyết định dựa trên cache stale |
| Catalog hiển thị | Có thể dùng stale cache trong giới hạn |
| Metric đếm không quan trọng | Có thể bỏ qua/aggregate sau |
| Workflow progress | Giữ pending, retry/reconcile |
| Idempotency record | Không thực hiện side effect nếu không thể kiểm tra an toàn |

Đây là quyết định nghiệp vụ và rủi ro, không phải một mặc định chung của Spring Cloud Function.

## 18. Kiểm thử state dùng chung qua nhiều lần gọi

Unit test của một Function chỉ xác minh logic trong một invocation. Muốn chứng minh state được chia sẻ đúng, cần test qua storage thật và nhiều đường thực thi.

### 18.1. Ma trận test cần có

| Kịch bản | Cách tạo | Kết quả mong đợi |
|---|---|---|
| Hai invocation tuần tự | Cùng state key, operation ID khác | Lần hai đọc được state sau lần một |
| Gửi lại cùng operation | Cùng tenant và operation ID | Trả kết quả cũ, không cập nhật lần nữa |
| Cùng operation ID, command khác | Đổi delta/counter ID | Conflict, state giữ nguyên |
| Hai operation đồng thời | Hai invocation cùng counter, operation ID khác | Không lost update |
| Hai instance | Hai application context cùng DB | Cùng nhìn thấy state đã commit |
| Restart instance | Ghi rồi khởi động process mới | Đọc lại được state từ storage |
| Tenant trùng aggregate ID | Hai tenant cùng counter ID | State tách biệt |
| Event cũ đến muộn | Gửi version thấp hơn state hiện tại | Không ghi lùi version |
| Cache stale | Cố ý bỏ invalidation | Hành vi theo stale policy đã chọn |
| State store unavailable | Ngắt kết nối storage | Fail/degrade đúng policy, không fallback local tùy tiện |
| TTL/cleanup | Hết hạn cache/session/job | Chỉ xóa state đủ điều kiện |
| Schema rollout | Đọc dữ liệu schema cũ bằng code mới | Migration/upcast hoạt động |

### 18.2. Test concurrency phải dùng operation ID riêng

Khi kiểm tra counter, mỗi invocation đồng thời nên có operation ID riêng để mô phỏng các command mới. Kết quả cuối phải bằng tổng delta đã commit. Sau đó chạy một lượt nữa với cùng operation ID để xác minh replay không tăng counter.

Một test chỉ gọi cùng operation ID nhiều lần sẽ chủ yếu kiểm tra idempotency, chưa kiểm tra lost update của các operation độc lập.

### 18.3. Một JVM không chứng minh nhiều instance

Chạy nhiều thread trên cùng Spring context kiểm tra thread safety và database atomicity. Để kiểm tra state qua instance, khởi chạy hai application context/process riêng cùng trỏ vào một database/cache test; gọi instance A rồi đọc/cập nhật qua B.

Test phải không dùng chung một singleton in-memory fake, nếu không nó che giấu việc production storage chưa được dùng đúng.

### 18.4. Kiểm tra restart và cold start

Ghi state, dừng instance A, tạo instance B mới rồi đọc lại. Với serverless, mô phỏng invocation ở runtime mới hoặc test adapter trên process mới. Nếu kết quả biến mất, state đang phụ thuộc local memory.

### 18.5. Test race và invariant

Đừng chỉ assert không có exception. Kiểm tra invariant:
- Counter bằng tổng delta đã nhận.
- Một operation ID có một kết quả duy nhất.
- Một tenant không đọc được state tenant khác.
- Aggregate version chỉ tăng, không giảm.
- State transition không bỏ qua bước.
- Duplicate event không tạo side effect mới.
- Cache stale không được dùng cho quyết định yêu cầu consistency mạnh.

## 19. Kiểm thử FunctionCatalog và adapter

Có thể lookup Function theo tên trong integration test:

~~~java
@SpringBootTest
class CounterFunctionIntegrationTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void functionUsesSharedStateStore() {
        Function<IncrementCommand, CounterSnapshot> increment =
                catalog.lookup("incrementCounter");

        assertNotNull(increment);

        IncrementCommand first =
                new IncrementCommand("op-100", "daily", 1);
        IncrementCommand replay =
                new IncrementCommand("op-100", "daily", 1);

        CounterSnapshot created = increment.apply(first);
        CounterSnapshot repeated = increment.apply(replay);

        assertEquals(created, repeated);
    }
}
~~~

Đây là skeleton test; bổ sung import JUnit/Spring Boot Test, `java.util.function.Function` và `org.springframework.cloud.function.context.FunctionCatalog`. Tenant test identity, `CommandFingerprint` bean và database fixture do test configuration cung cấp. Nếu FunctionCatalog trả null, kiểm tra bean registration, tên function và context trước khi kết luận lỗi storage.

### 19.1. Test qua HTTP và message

Cùng application service có thể được gọi qua HTTP function adapter và Stream binder. Cần kiểm tra:
- Request cùng operation ID qua HTTP trả kết quả đã lưu.
- Message redelivery không áp dụng state lần hai.
- Tenant context được ánh xạ đúng từ từng adapter.
- Headers/correlation metadata được giữ theo contract.
- Adapter không làm mất exception hoặc ACK quá sớm.

Test binder nội bộ không thay thế integration test với broker thật nếu cần xác minh partition, redelivery, visibility hoặc consumer concurrency.

### 19.2. Test khi hai phiên bản Function cùng chạy

Trong rolling deployment, tạo writer bằng code version cũ và reader bằng code version mới (và ngược lại nếu cần). Xác minh schema/enum/event mới không làm instance cũ crash hoặc ghi state không đọc được.

## 20. Observability cho shared state

Nên đo cả hiệu năng storage và chất lượng invariant. Metric gợi ý:

| Metric | Ý nghĩa |
|---|---|
| `state_read_total` / `state_write_total` | Lưu lượng đọc/ghi |
| `state_store_latency` | Độ trễ storage |
| `state_store_error_total` | Lỗi truy cập store |
| `state_conflict_total` | Conflict version/operation key |
| `optimistic_lock_retry_total` | Số lần retry do version conflict |
| `operation_duplicate_total` | Operation replay được nhận diện |
| `cache_hit_ratio` / `cache_miss_total` | Hiệu quả cache |
| `cache_stale_read_total` | Lượt đọc dữ liệu stale nếu quan sát được |
| `state_version_gap_total` | Event/version đến thiếu thứ tự |
| `state_migration_failure_total` | Lỗi migration/upcast |
| `state_key_count` | Cardinality theo loại/tenant (đã aggregate) |
| `state_expired_total` | Số state hết hạn/cleanup |

Tên metric là đề xuất của ứng dụng, không phải metric mặc định của Spring Cloud Function.

### 20.1. Log có context nhưng không lộ state nhạy cảm

Log nên có tenant ID đã được phép ghi, aggregate ID, operation ID, state version, function name, adapter, outcome và trace ID. Không log toàn bộ payload, token, số dư hoặc dữ liệu cá nhân chỉ để tiện debug.

### 20.2. Theo dõi conflict và hot key

Một aggregate được cập nhật quá thường xuyên có thể tạo hot row/lock contention. Theo dõi optimistic conflict, lock wait, Redis command latency và số invocation cùng key. Cân nhắc partitioning/sharding hoặc thiết kế aggregate boundary nếu bottleneck kéo dài; không bỏ version check để tăng throughput.

### 20.3. Phân biệt duplicate bình thường với state corruption

Một operation replay cùng fingerprint có thể là bình thường. Cùng operation ID nhưng command khác, version giảm hoặc state transition không hợp lệ là tín hiệu cần điều tra. Metric/log phải phân biệt rõ các outcome này.

## 21. Các lỗi thiết kế thường gặp

| Anti-pattern | Hậu quả | Hướng sửa |
|---|---|---|
| Mutable field trong Function singleton | Race giữa thread | Chỉ giữ immutable config; state ở store |
| `static` làm nguồn sự thật | Instance khác không thấy; restart mất | Database/distributed store |
| `AtomicLong` làm ID toàn hệ thống | Chỉ atomic trong một JVM | DB sequence/UUID/ULID |
| `ConcurrentHashMap` làm state nghiệp vụ | Không durability, không cross-instance | Storage bền vững |
| Read-modify-write không atomic | Lost update | Atomic SQL, version/CAS hoặc lock |
| Cache là nguồn duy nhất | Eviction/failover làm mất state | Source of truth riêng |
| Tin sticky session | Instance restart làm mất session | Shared session store |
| Tin tenant từ message payload | Cross-tenant access | Derive/verify tenant từ principal |
| Dùng correlation ID làm idempotency key | Retry có trace mới bị tính thành operation mới | Operation ID ổn định |
| Chỉ dedupe theo event ID | Producer phát ID mới cho cùng business action | Business key/version |
| Không kiểm tra event version | Event cũ ghi lùi state | Version guard/state transition |
| TTL xóa job đang chạy | Workflow mất trạng thái | State-aware cleanup |
| Cache invalidation fire-and-forget | Stale data kéo dài | Outbox/event/version/TTL |
| Serialize Java object dài hạn | Khó migrate và tương thích | Schema version rõ ràng |
| Local fallback khi DB lỗi | Nhiều nhánh state không thể hợp nhất | Fail/degrade có chủ đích |
| Distributed lock không lease/fencing | Lock hết hạn nhưng worker cũ vẫn ghi | Lease + fencing/conditional update |

### 21.1. Anti-pattern: coi cache thread-safe là state phân tán

Một cache local có thể an toàn với nhiều thread nhưng vẫn chỉ tồn tại trong một process. Khi thêm replica, mỗi instance có bản cache khác nhau. Thread-safe không có nghĩa cross-instance consistent.

### 21.2. Anti-pattern: update state bằng cách ghi đè toàn object

Nếu client đọc aggregate version 5 rồi gửi toàn bộ object để ghi đè, trong lúc đó invocation khác đã commit version 6, dữ liệu mới có thể bị mất. Dùng version check/conditional update và chỉ áp dụng command hợp lệ lên state mới nhất.

### 21.3. Anti-pattern: tự động khởi tạo state khi không tìm thấy

Nếu đọc state không thấy rồi mặc định tạo `NEW`, có thể che giấu tenant/key sai, dữ liệu bị xóa hoặc replica lag. Phân biệt “chưa từng tồn tại” với “không đọc được” và “chưa đồng bộ”; chỉ tạo state khi command nghiệp vụ cho phép.

## 22. Checklist trước khi triển khai production

### 22.1. Mô hình state

- [ ] Đã phân loại dữ liệu invocation, intermediate, cache và durable state.
- [ ] Mỗi aggregate/workflow có owner và transition rule.
- [ ] Đã chọn source of truth.
- [ ] Không dùng bean field/static làm state chia sẻ qua instance.
- [ ] Có tenant/aggregate/operation/version key phù hợp.
- [ ] Identity và authorization được xác minh độc lập với key.

### 22.2. Concurrency và consistency

- [ ] Read-modify-write được thay bằng atomic update/version/lock.
- [ ] Operation retry có idempotency key và fingerprint.
- [ ] Event cũ/gap/version conflict có policy rõ.
- [ ] Cache stale window được chấp nhận rõ ràng.
- [ ] Cache invalidation có retry/outbox hoặc TTL phù hợp.
- [ ] Read replica lag không ảnh hưởng quyết định quan trọng.

### 22.3. Vòng đời và triển khai

- [ ] State sống qua restart/cold start.
- [ ] TTL không xóa workflow chưa terminal.
- [ ] Retention đáp ứng retry/replay/audit.
- [ ] Schema/event version tương thích rolling deployment.
- [ ] Có backup/restore và recovery test.
- [ ] Store unavailable có fail/degrade policy, không fallback local tùy tiện.

### 22.4. Kiểm thử và vận hành

- [ ] Test nhiều thread cùng key.
- [ ] Test hai instance/process cùng storage.
- [ ] Test restart/cold start.
- [ ] Test tenant isolation và duplicate operation.
- [ ] Test stale cache, out-of-order event và schema migration.
- [ ] Có metric latency, conflict, duplicate, cache stale và store errors.
- [ ] Log có operation/aggregate/version nhưng không lộ payload nhạy cảm.

## 23. Bài tập thực hành

**Bài 1 — Function singleton.** Một bean Function giữ `HashMap` trong field để nhớ kết quả của người dùng. Nêu ba vấn đề khi scale out và xử lý đồng thời.

**Bài 2 — AtomicLong.** Vì sao `AtomicLong` giải quyết race giữa thread nhưng không tạo sequence bền vững cho nhiều pod?

**Bài 3 — Source of truth.** Hệ thống có PostgreSQL và Redis cache. Nơi nào giữ order status? Điều gì xảy ra nếu Redis bị flush?

**Bài 4 — Lost update.** Hai invocation cùng đọc counter 10 rồi ghi 11. Hãy đề xuất atomic SQL hoặc CAS để kết quả thành 12.

**Bài 5 — Idempotency.** Một command increment bị gửi lại sau timeout. Vì sao atomic increment vẫn có thể tăng hai lần? Cần operation key và transaction thế nào?

**Bài 6 — Tenant key.** Hai tenant có cùng `orderId`. Hãy thiết kế key và giải thích vì sao authorization vẫn cần kiểm tra riêng.

**Bài 7 — Version.** Event version 4 đến sau khi state đã ở version 5. Consumer nên xử lý thế nào?

**Bài 8 — State transition.** Order đã `COMPLETED` nhưng nhận event `RESERVED` cũ. Vì sao không thể gán status theo payload?

**Bài 9 — Cache invalidation.** DB update commit nhưng process chết trước khi xóa cache. Đưa ra hai cách giảm stale window.

**Bài 10 — Cache stampede.** 100 invocation cùng miss một key hết TTL. Điều gì xảy ra và có thể giảm tải bằng cách nào?

**Bài 11 — HTTP session.** Vì sao session trong memory của một web instance không phù hợp khi load balancer chuyển request sang instance khác?

**Bài 12 — JWT.** Vì sao JWT stateless không tự giải quyết revocation ngay lập tức?

**Bài 13 — Reactor Context.** Vì sao dùng `ThreadLocal` để giữ tenant có thể sai khi pipeline đổi scheduler?

**Bài 14 — Serverless.** Invocation đầu lưu state vào static map, invocation sau chạy trên instance lạnh. Điều gì xảy ra? Thiết kế lại ra sao?

**Bài 15 — TTL.** Một job đang `PROCESSING` có TTL 15 phút nhưng có thể chạy 40 phút. Rủi ro và cách sửa?

**Bài 16 — Rolling deployment.** Code mới thêm enum state mà code cũ không nhận biết. Hãy đề xuất thứ tự rollout/schema compatibility.

**Bài 17 — Test concurrency.** Thiết kế test nhiều operation ID riêng cùng tăng một counter. Assertion nào chứng minh không lost update?

**Bài 18 — Multi-instance test.** Vì sao nhiều thread trong cùng Spring context chưa chứng minh state chia sẻ giữa hai instance?

**Bài 19 — Store unavailable.** Khi DB mất kết nối, vì sao không nên ghi tạm vào local map rồi đồng bộ sau mà không có protocol?

**Bài 20 — Observability.** Nêu metric/log giúp phân biệt duplicate hợp lệ, optimistic conflict, cache stale và state version gap.

### Gợi ý đáp án

- **Bài 1:** HashMap không thread-safe, state chỉ ở một instance, restart/scale down làm mất dữ liệu.
- **Bài 2:** AtomicLong chỉ đồng bộ object trong một JVM; pod khác có object khác và restart mất giá trị.
- **Bài 3:** PostgreSQL giữ source of truth; Redis flush thì cache miss và đọc lại DB.
- **Bài 4:** Một câu lệnh atomic update/returning hoặc optimistic version/CAS.
- **Bài 5:** Atomic update mỗi lần gọi vẫn cộng hai lần; claim operation key và increment cùng transaction, lưu kết quả/fingerprint.
- **Bài 6:** Key gồm tenant + order; authorization xác minh principal có quyền với tenant/order.
- **Bài 7:** Bỏ qua nếu duplicate/stale đã xử lý, hoặc quarantine/gap policy; tuyệt đối không ghi lùi version.
- **Bài 8:** State transition phải kiểm tra current state và event; payload không được tùy ý ghi đè.
- **Bài 9:** Outbox invalidation event sau commit hoặc versioned key/TTL.
- **Bài 10:** Nhiều request cùng tải source of truth; request coalescing, refresh ahead, jitter hoặc lease.
- **Bài 11:** Instance khác không có session memory; dùng shared session store.
- **Bài 12:** Token còn hiệu lực tới expiry nếu không có revocation lookup/version check.
- **Bài 13:** ThreadLocal gắn với thread, không theo reactive subscriber khi scheduler đổi thread.
- **Bài 14:** Static state mất/không được chia sẻ; lưu durable state ngoài instance.
- **Bài 15:** TTL có thể xóa job đang chạy; TTL chỉ sau terminal hoặc heartbeat/lease gia hạn có kiểm soát.
- **Bài 16:** Expand schema trước, deploy code đọc cũ/mới, migrate/backfill, rồi contract sau khi instance cũ đã hết.
- **Bài 17:** Chạy N command khác operation ID đồng thời, assert counter tăng đúng tổng delta và version phù hợp.
- **Bài 18:** Thread chỉ kiểm tra một JVM; cần hai process/application context dùng chung storage.
- **Bài 19:** Hai local map có thể diverge và không có thứ tự merge; cần durable queue/outbox hoặc fail/degrade rõ.
- **Bài 20:** Metric state conflict/duplicate/cache stale/version gap và log tenant/aggregate/operation/version/outcome.

## 24. Ghi nhớ

- Invocation là một lần gọi; instance là một process có thể được tái sử dụng hoặc thay thế.
- Bean singleton, `static`, `AtomicLong` và `ConcurrentHashMap` không tự trở thành state store dùng chung nhiều instance.
- Phân biệt input/context tạm, immutable config, cache và durable business state.
- Chọn source of truth theo yêu cầu durability/consistency; cache chỉ là bản sao có stale window.
- Key phải phản ánh tenant, aggregate, operation và version; authorization luôn được kiểm tra riêng.
- Dùng atomic update, unique constraint, optimistic/pessimistic locking và state transition để xử lý concurrency.
- Operation ID/fingerprint bảo vệ retry; event version ngăn state bị ghi lùi.
- FunctionCatalog và composition tổ chức Function; application service/repository quản lý state.
- HTTP session, message workflow và serverless state cần storage phù hợp với lifecycle của từng adapter.
- TTL, schema evolution, cache invalidation, backup và privacy là một phần của vòng đời state.
- Kiểm thử nhiều thread, nhiều process, restart, tenant isolation và event out-of-order; quan sát conflict, stale cache và state store latency.




