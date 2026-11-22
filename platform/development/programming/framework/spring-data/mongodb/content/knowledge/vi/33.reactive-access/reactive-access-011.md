# Ghép nhiều thao tác ghi với mức đồng thời phù hợp

> **Chương:** Truy cập reactive  
> **Module:** `SPRING_DATA_MONGODB` — sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác dữ liệu qua `MongoTemplate` hoặc repository; thực hành thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.  
> **Mục tiêu:** Phân biệt thao tác ghi phụ thuộc/độc lập; xây pipeline ghi bằng `Mono`/`Flux`, `then`, `flatMap`, `concatMap` và `flatMapSequential`; chọn giới hạn đồng thời phù hợp với kết nối, database và bộ nhớ; xử lý lỗi từng item, partial success, retry/idempotency và write concern; hiểu tại sao **không chạy song song các write trong cùng MongoDB transaction**; đo và kiểm thử bằng `StepVerifier` cùng MongoDB test thật.

## 1. Bài toán: ghi 10.000 bản ghi có nên gọi đồng thời tất cả?

Một API nhận một loạt sự kiện nhập kho. Mỗi sự kiện cần lưu vào MongoDB, có ID nghiệp vụ riêng. Nếu dùng WebFlux và `ReactiveMongoRepository`, code sau trông rất tự nhiên:

~~~java
return Flux.fromIterable(commands)
    .flatMap(command -> repository.insert(toDocument(command)));
~~~

Nhưng `flatMap` có khả năng **đăng ký nhiều inner Publisher sớm** và trộn kết quả khi chúng hoàn tất. Nếu không có giới hạn đồng thời có chủ đích, số operation đang chạy phụ thuộc cấu hình operator và nguồn dữ liệu; không phải một giao thức tự điều tiết theo tải MongoDB mà application đã kiểm soát.

Các tình huống thực tế có **nhu cầu khác nhau**:

1. Mỗi event độc lập, có khóa duy nhất: có thể ghi **đồng thời có giới hạn**.
2. Hai command cùng sửa một order theo thứ tự `PENDING → APPROVED → SHIPPED`: phải giữ **thứ tự theo order** hoặc dùng điều kiện/version.
3. Update order rồi insert outbox trong **một transaction**: phải chạy **tuần tự trong cùng session**.
4. Bulk import hàng trăm nghìn document: cần cân nhắc **batch/bulk** thay vì mỗi document là một request riêng.
5. Một item lỗi duplicate key: phải quyết định **dừng toàn luồng**, **báo lỗi riêng item**, hay **đối soát idempotency**.

Vì thế, câu hỏi không phải “Reactive nhanh hơn vì song song?” mà là:

> **Có thể có bao nhiêu write đang hoạt động cùng lúc mà vẫn đúng nghiệp vụ, không quá tải database và vẫn xử lý failure an toàn?**

### 1.1. Ba khái niệm không được đánh đồng

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Concurrent writes** | Nhiều operation đang chờ/xử lý cùng lúc | `flatMap(write, 8)` |
| **Parallel threads** | Nhiều thread CPU chạy cùng lúc | `parallel().runOn(...)` |
| **Atomic transaction** | Nhóm write commit/abort như một đơn vị | `TransactionalOperator` / reactive `@Transactional` |

**Concurrency không đòi hỏi mỗi operation một thread.** Reactive MongoDB Driver dùng I/O bất đồng bộ, nên nhiều request có thể in-flight mà không cần `boundedElastic` hoặc `parallel()`. Và **transaction không đồng nghĩa với việc cho các write trong transaction chạy song song**.

~~~mermaid
flowchart TD
    A["Flux<WriteCommand>"] --> B{"Có phụ thuộc trạng thái/ordering?"}
    B -->|"Không, độc lập"| C["flatMap(write, concurrency=N)"]
    B -->|"Có theo từng ID"| D["Tuần tự theo key + đồng thời giữa key"]
    B -->|"Cùng MongoDB transaction"| E["then/flatMap tuần tự trong session"]
    C --> F["Giới hạn pool, tài nguyên, retry"]
    D --> F
    E --> G["commit/abort cả transaction"]
    F --> H["Kết quả từng item / batch"]
~~~

## 2. Reactive write hoạt động khi nào?

`ReactiveMongoTemplate` và `ReactiveMongoRepository` trả **Publisher**: thường là `Mono<T>` cho một kết quả hoặc `Flux<T>` cho nhiều kết quả. Với những API CRUD reactive chuẩn, publisher biểu diễn công việc bất đồng bộ, và I/O thực tế diễn ra khi có **subscription**.

~~~java
Mono<WriteJob> operation = repository.insert(job);
// Tạo publisher, chưa đồng nghĩa đã nhận ACK từ MongoDB.
~~~

Nếu không có subscriber, application thường **chưa thực hiện write**.

### 2.1. Một subscription có thể tạo một lần ghi

~~~java
Mono<WriteJob> operation = repository.insert(job);

// Hai subscription có thể dẫn tới hai lần thực thi insert.
// Lần sau có thể gặp duplicate _id.
operation.subscribe();
operation.subscribe();
~~~

Đoạn trên là **phản ví dụ**. Trong service **không tự `subscribe()`** rồi bỏ Publisher trả về: bạn sẽ tách operation khỏi error handling, transaction context và lifecycle của caller.

### 2.2. Pipeline đúng: trả Publisher cho caller

~~~java
public Mono<WriteJob> create(WriteJob job) {
    return repository.insert(job);
}
~~~

Trong WebFlux, controller trả `Mono<ResponseEntity<...>>` hoặc `Flux<...>` để framework subscribe. Trong background consumer, subscriber cần được quản lý bằng lifecycle/acknowledgment của consumer; không tạo `subscribe()` tùy tiện mà không theo dõi lỗi.

### 2.3. `map` không “chờ” một `Mono` lồng bên trong

Sai:

~~~java
Flux<Mono<WriteJob>> nested = Flux.fromIterable(commands)
    .map(command -> repository.insert(toDocument(command)));
// Đây là Flux phát ra CÁC PUBLISHER, không phải Flux<WriteJob>.
~~~

Đúng:

~~~java
Flux<WriteJob> writes = Flux.fromIterable(commands)
    .flatMap(command -> repository.insert(toDocument(command)), 8);
~~~

`map` dùng cho biến đổi đồng bộ **T → R**. Khi mapper trả `Mono<R>`/`Flux<R>` và cần subscribe inner Publisher, dùng `flatMap`, `concatMap` hoặc operator phù hợp.

## 3. Mô hình dữ liệu dùng trong bài

Ví dụ Java trong package `com.example.reactivewrites`. Sử dụng **collection test riêng**; đoạn lệnh `mongosh` chỉ phục vụ học tập, không chạy trên dữ liệu production.

### 3.1. Mỗi command có khóa nghiệp vụ

~~~java
// WriteCommand.java
package com.example.reactivewrites;

public record WriteCommand(
    String id,
    String tenantId,
    String payload
) {
}
~~~

`id` phải **ổn định qua retry**, ví dụ event ID từ nguồn vào hoặc một idempotency key. Không tạo UUID hoàn toàn mới mỗi lần thử lại nếu nghiệp vụ yêu cầu không chèn trùng.

### 3.2. Entity MongoDB

~~~java
// WriteJob.java
package com.example.reactivewrites;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "write_jobs_reactive_011")
public class WriteJob {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    private String payload;
    private String status;

    @Field("created_at")
    private Instant createdAt;

    protected WriteJob() {}

    public WriteJob(
            String id, String tenantId, String payload,
            String status, Instant createdAt) {
        this.id = id;
        this.tenantId = tenantId;
        this.payload = payload;
        this.status = status;
        this.createdAt = createdAt;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getPayload() { return payload; }
    public String getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
}
~~~

`@MongoId(FieldType.STRING)` bảo đảm `_id` được biểu diễn bằng string theo chính sách ví dụ, tránh sự nhầm lẫn với phép chuyển ObjectId khi các ID có định dạng đặc biệt.

### 3.3. Reactive repository

~~~java
// WriteJobRepository.java
package com.example.reactivewrites;

import org.springframework.data.mongodb.repository.ReactiveMongoRepository;

public interface WriteJobRepository
        extends ReactiveMongoRepository<WriteJob, String> {
}
~~~

MongoDB tạo index unique cho `_id`. Nếu client gửi cùng `id` lần thứ hai, `insert` thường bị từ chối với duplicate key (trừ khi lần đầu chưa ghi/đã rollback). Đây là cơ chế quan trọng cho idempotency, nhưng application vẫn phải kiểm **nội dung request cũ có cùng ý nghĩa hay không**.

### 3.4. Fixture `mongosh`

~~~javascript
use spring_data_mongodb_lab

db.createCollection("write_jobs_reactive_011");
db.write_jobs_reactive_011.createIndex(
  { tenant_id: 1, status: 1, created_at: -1 },
  { name: "ix_tenant_status_created" }
);

db.write_jobs_reactive_011.insertMany([
  {
    _id: "j011-01", tenant_id: "t01",
    payload: "A", status: "NEW",
    created_at: ISODate("2026-11-01T00:00:00Z")
  },
  {
    _id: "j011-02", tenant_id: "t01",
    payload: "B", status: "NEW",
    created_at: ISODate("2026-11-01T00:01:00Z")
  },
  {
    _id: "j011-03", tenant_id: "t02",
    payload: "C", status: "NEW",
    created_at: ISODate("2026-11-01T00:02:00Z")
  }
]);
~~~

Các ID có sẵn chỉ dùng khi truy vấn/update fixture; khi thử thêm dữ liệu bằng code Java, chọn ID mới như `import-011-001`. Không chạy lại `insertMany` trên cùng ID; duplicate key là kết quả mong đợi chứ không phải lỗi Reactor.

### 3.5. Factory chuyển command thành entity

~~~java
import java.time.Instant;

private static WriteJob toDocument(WriteCommand command) {
    if (command.id() == null || command.id().isBlank()) {
        throw new IllegalArgumentException("id is required");
    }
    if (command.tenantId() == null
            || command.tenantId().isBlank()) {
        throw new IllegalArgumentException("tenantId is required");
    }
    return new WriteJob(
        command.id(), command.tenantId(), command.payload(),
        "NEW", Instant.now()
    );
}
~~~

Trong production, lấy tenant từ security context và kiểm quyền; không tin `tenantId` do client tùy ý cung cấp. Nếu cần thời gian tạo **ổn định qua retry**, truyền `createdAt` từ command gốc thay vì gọi `Instant.now()` mỗi lần; điều này ảnh hưởng đến phép so fingerprint khi đối soát duplicate.

## 4. Ghép hai write phụ thuộc: `flatMap` và `then`

Giả sử phải ghi `WriteJob` trước rồi mới cập nhật trạng thái của **chính document đó** từ `NEW` sang `READY`.

### 4.1. Dùng kết quả của write trước làm input sau

~~~java
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import reactor.core.publisher.Mono;

public Mono<WriteJob> insertThenMarkReady(WriteJob job) {
    return repository.insert(job)
        .flatMap(inserted -> {
            Query query = Query.query(
                Criteria.where("id").is(inserted.getId())
                    .and("tenantId").is(inserted.getTenantId())
                    .and("status").is("NEW")
            );

            return template.updateFirst(
                query,
                new Update().set("status", "READY"),
                WriteJob.class
            ).flatMap(result -> {
                if (result.getMatchedCount() != 1) {
                    return Mono.error(
                        new IllegalStateException(
                            "Unexpected state after insert"));
                }
                return template.findById(
                    inserted.getId(), WriteJob.class
                );
            });
        });
}
~~~

Ở đây `repository` là `WriteJobRepository` và `template` là `ReactiveMongoTemplate` được inject; snippet thuộc một service có hai dependency này. `flatMap` bảo đảm update **chỉ được subscribe sau khi insert phát kết quả**.

**Lưu ý tính nguyên tử:** Hai write không tự thuộc cùng một transaction chỉ vì ghép `flatMap`. Nếu insert thành công nhưng update lỗi, document có thể còn ở `NEW`. Muốn all-or-nothing giữa nhiều write cần transaction phù hợp, hoặc thiết kế một thao tác single-document có điều kiện có thể thực hiện mục tiêu ngay từ đầu.

### 4.2. Dùng `then` khi không cần giá trị của bước trước

~~~java
Mono<Void> first = writeAuditFor(job);
Mono<Void> second = publishOutboxRecordFor(job);

Mono<Void> ordered = first.then(second);
// second được subscribe sau khi first complete thành công.
~~~

`then(other)` **bỏ giá trị onNext từ upstream** và chờ upstream **complete thành công** trước khi subscribe `other`. Nếu upstream phát `onError`, `other` không được subscribe.

Để trì hoãn cả việc **tạo Publisher** thứ hai nếu factory có logic cần chạy sau:

~~~java
Mono<Void> ordered = writeAuditFor(job)
    .then(Mono.defer(() -> publishOutboxRecordFor(job)));
~~~

Trong code thuần Reactor/ReactiveMongoTemplate, tạo publisher thường chưa chạy I/O, nhưng **hàm factory vẫn có thể có side effect đồng bộ**. `Mono.defer` làm điểm tạo/đăng ký rõ ràng.

### 4.3. `thenReturn` và `thenMany`

~~~java
Mono<String> confirmation = repository.insert(job)
    .thenReturn(job.getId());

Flux<WriteJob> afterSetup = ensureImportMarker()
    .thenMany(Flux.fromIterable(batch)
        .flatMap(repository::insert, 4));
~~~

`thenReturn` bỏ giá trị insert rồi phát ID sau khi hoàn tất. `thenMany` đợi bước chuẩn bị xong rồi mới subscribe chuỗi nhiều item.

**Không dùng `thenReturn("SUCCESS")` như lời hứa commit toàn workflow nếu vẫn còn các side effect ngoài MongoDB chạy sau đó hoặc write concern không phù hợp.** Thành công là theo điều kiện acknowledgment thực tế của operation.

## 5. `Mono.when` và `Mono.zip`: ghép operation độc lập

Hai write thuộc **hai key không phụ thuộc nhau** và **không nằm chung một transaction** có thể thực hiện đồng thời.

### 5.1. `Mono.when` chờ cả hai complete

~~~java
Mono<Void> both = Mono.when(
    repository.insert(jobA).then(),
    repository.insert(jobB).then()
);
~~~

`Mono.when` subscribe các source và hoàn tất khi **tất cả** complete thành công. Nhưng:

- Nếu source B lỗi, A có thể **đã ghi xong**.
- `Mono.when` mặc định phát lỗi và có thể cancel các source khác; **cancellation không rollback write đã được server xử lý**.
- Không có tính nguyên tử all-or-nothing giữa A và B.

Vì vậy `Mono.when` phù hợp khi **các write thực sự độc lập**, chấp nhận partial completion và có chính sách khôi phục rõ.

### 5.2. `Mono.zip` khi cần giá trị cả hai

~~~java
Mono<reactor.util.function.Tuple2<WriteJob, WriteJob>> pair =
    Mono.zip(
        repository.insert(jobA),
        repository.insert(jobB)
    );

Mono<String> summary = pair.map(tuple ->
    tuple.getT1().getId() + "," + tuple.getT2().getId()
);
~~~

`zip` phối hợp **kết quả**, không tạo transaction. Nếu một source không phát giá trị (ví dụ `Mono<Void>` complete rỗng), `zip` có thể complete rỗng và cancel source khác. **Không dùng `Mono.zip(Mono<Void>, Mono<Void>)`** để “đợi hai thao tác”; hãy dùng `Mono.when` nếu chỉ cần completion.

### 5.3. Không dùng `when` để phá thứ tự nghiệp vụ

Sai:

~~~java
// Không có thứ tự insert -> update.
Mono.when(
    repository.insert(job),
    template.updateFirst(query, update, WriteJob.class)
);
~~~

Update có thể chạy trước insert; result `matchedCount=0` không phải một lỗi của Reactive Driver mà là **race do pipeline**. Đúng là `insert.flatMap(...)` hoặc `insert.then(update...)`.

## 6. Ba lựa chọn để xử lý một `Flux` command

Giả sử `commands` là `Flux<WriteCommand>` và mỗi mapper gọi:

~~~java
Mono<WriteJob> writeOne(WriteCommand command) {
    return repository.insert(toDocument(command));
}
~~~

### 6.1. `concatMap` — tuần tự tuyệt đối ở phạm vi Flux

~~~java
Flux<WriteJob> result = commands
    .concatMap(this::writeOne);
~~~

`concatMap` đợi inner Publisher trước **hoàn tất** rồi mới subscribe inner kế tiếp. Khi mỗi inner là một `Mono` ghi:

~~~text
write(A) ─── ACK
                write(B) ── ACK
                              write(C) ─── ACK
~~~

Ưu điểm: giữ thứ tự **thực hiện/đăng ký** và **kết quả**; tránh ghi A, B chồng nhau ở phạm vi pipeline. Nhược điểm: latency từng write cộng dồn, throughput thấp khi từng operation không phụ thuộc.

### 6.2. `flatMap(..., N)` — đồng thời tối đa N inner Publisher

~~~java
int concurrency = 8;

Flux<WriteJob> result = commands
    .flatMap(this::writeOne, concurrency);
~~~

`flatMap` có thể có tối đa khoảng **N inner subscriptions đang hoạt động** cùng lúc và phát kết quả khi từng inner hoàn tất, nên:

~~~text
write(A) ───────── ACK A
write(B) ── ACK B
write(C) ───── ACK C

Downstream nhận: B, C, A (thứ tự có thể khác nguồn).
~~~

**N giới hạn concurrency của pipeline này, không phải tổng số MongoDB writes của cả service/cluster.** Nếu có 30 request HTTP đồng thời, mỗi request dùng `flatMap(..., 8)` thì có thể tạo khoảng **240 inner write** qua các pipeline — chưa kể các service khác.

### 6.3. `flatMapSequential(..., N)` — chạy đồng thời nhưng phát kết quả theo thứ tự nguồn

~~~java
Flux<WriteJob> result = commands
    .flatMapSequential(this::writeOne, 8);
~~~

Operator có thể subscribe nhiều inner sớm giống `flatMap`, nhưng **buffer kết quả đến sớm** để emit theo thứ tự source.

> **Cực kỳ quan trọng:** `flatMapSequential` giữ thứ tự **onNext downstream**, **không bảo đảm write trên MongoDB xảy ra theo thứ tự**.

Nếu A và B cùng sửa một document với hai trạng thái khác nhau, `flatMapSequential` vẫn có thể để B cập nhật DB trước A. Khi nghiệp vụ cần ordering write, dùng `concatMap`/phân luồng theo key hoặc optimistic locking.

### 6.4. Bảng so sánh

| Operator | Số inner write cùng lúc | Thứ tự phát kết quả | Thứ tự thực thi write |
| --- | --- | --- | --- |
| `concatMap` | 1 tại một pipeline | Theo nguồn | **Tuần tự** |
| `flatMap(mapper,N)` | Tối đa N | Theo hoàn tất | Không cố định |
| `flatMapSequential(mapper,N)` | Tối đa N | Theo nguồn | **Không cố định** |
| `merge` | Có thể đồng thời nhiều source | Theo hoàn tất | Không cố định |
| `Mono.when` | Các source được subscribe cùng nhau | Chỉ completion | Không cố định |
| `then` | Lần lượt upstream rồi downstream | Không áp dụng | **Tuần tự dependency** |

### 6.5. `flatMapSequential` có chi phí giữ kết quả

Nếu item đầu nguồn rất chậm nhưng các item sau hoàn tất nhanh, `flatMapSequential` phải **giữ kết quả đến sớm** trong buffer để bảo toàn thứ tự. Do đó nó có thể dùng thêm bộ nhớ hoặc tăng latency output. Chỉ chọn nếu client **cần output theo thứ tự nhập** nhưng các write thực sự độc lập.

## 7. Lựa chọn concurrency không dựa vào một con số thần kỳ

Không có giá trị N tối ưu chung như 16, 32 hoặc 256. Số phù hợp phụ thuộc:

- Connection pool và giới hạn simultaneous connections của MongoDB Driver.
- RTT và thời gian trung bình/p95 của mỗi write.
- Indexes, số shard, replica lag và write concern (majority có thể chờ lâu hơn).
- Dung lượng document, WAL/journal, lock contention, write hot spots.
- Tốc độ producer phát command và giới hạn bộ nhớ của ứng dụng.
- Số request/consumer instances chạy đồng thời trong toàn hệ thống.

### 7.1. Bắt đầu với N nhỏ có giới hạn

~~~java
int concurrency = 8; // Giá trị KHỞI ĐIỂM thử nghiệm, không phải mặc định chung.

return commands.flatMap(this::writeOne, concurrency);
~~~

Đo trước/sau trên dữ liệu và topology đại diện rồi tăng có kiểm soát. Khi thấy p95/p99 tăng mạnh, pool wait queue dài hoặc secondary lag, nâng N tiếp có thể làm throughput **giảm**.

### 7.2. Mô hình gần đúng: Little's Law

Với throughput ổn định và latency trung bình:

\[
L \approx \lambda \times W
\]

Trong đó `L` là số request in-flight trung bình, `λ` là số write hoàn tất/giây, `W` là thời gian xử lý trung bình tính bằng giây.

Ví dụ (chỉ mô phỏng):

~~~text
Mục tiêu:       400 write/giây
Latency trung bình: 20 ms = 0,02 s
Số in-flight trung bình ≈ 400 × 0,02 = 8
~~~

Con số này là **ước lượng nhu cầu in-flight**, không phải công thức bảo đảm N=8 đáp ứng SLO. Thực tế có tail latency, burst, pool contention và concurrent clients. Cần đo benchmark trước khi chọn N.

### 7.3. Tính concurrency toàn hệ thống

Giả sử:

~~~text
20 WebFlux requests đồng thời
× 8 writes/request
= 160 inner writes có thể đang hoạt động
~~~

Nếu thêm ba worker instances cùng làm vậy, toàn deployment còn cao hơn. Vì thế giới hạn ở `flatMap` **chỉ cục bộ**, không phải rate-limit/cluster admission control. Khi nguồn tải không kiểm soát được, cần một **semaphore/queue/bulkhead có vòng đời rõ**, hoặc consumer concurrency giới hạn ở tầng ingest, để áp trần tổng trên instance/cluster.

### 7.4. Đừng mặc định thêm `parallel()`/`subscribeOn(boundedElastic)`

~~~java
// Không cần thiết chỉ để gọi MongoDB reactive API:
commands.parallel()
    .runOn(reactor.core.scheduler.Schedulers.parallel())
    .flatMap(this::writeOne);
~~~

`parallel()` phù hợp hơn cho xử lý CPU-bound có khả năng chia việc. I/O MongoDB reactive vốn không blocking; tạo thêm scheduler hops thường làm pipeline khó đọc và đo, không tự tăng khả năng DB ghi.

`Schedulers.boundedElastic()` dành cho việc **tách API blocking** mà không có lựa chọn non-blocking. Nếu đã có Reactive MongoDB Driver, đừng bọc `repository.insert(...)` bằng `Mono.fromCallable(...).subscribeOn(boundedElastic)` như thể nó là lệnh blocking.

## 8. Tuần tự theo từng khóa, đồng thời giữa các khóa

Một hệ thống có nhiều order. Các thay đổi của **cùng một order** phải được xử lý theo thứ tự, nhưng các order **khác nhau** có thể ghi đồng thời nếu nghiệp vụ không phụ thuộc chéo.

Ví dụ:

~~~text
order-01: PENDING → APPROVED → SHIPPED  (phải tuần tự)
order-02: PENDING → CANCELLED          (độc lập với order-01)
order-03: PENDING → APPROVED           (độc lập với order-01 và 02)
~~~

### 8.1. Một luồng `concatMap` toàn cục: đúng nhưng có thể chậm

~~~java
Flux<OrderMutation> mutations = sourceOfMutations();

Flux<MutationResult> results = mutations
    .concatMap(this::applyMutation);
~~~

Mọi order đều bị tuần tự hóa, kể cả khi không cần. Đây là lựa chọn đơn giản và an toàn nếu throughput thấp hoặc chưa chứng minh được các write độc lập.

### 8.2. `groupBy` kết hợp `concatMap` và `flatMap`

~~~java
int activeKeyGroups = 8;

Flux<MutationResult> results = mutations
    .groupBy(OrderMutation::orderId)
    .flatMap(
        group -> group.concatMap(this::applyMutation),
        activeKeyGroups
    );
~~~

Ví dụ giả định:

~~~java
record OrderMutation(
    String orderId,
    String tenantId,
    String newState
) {}

record MutationResult(
    String orderId,
    String appliedState
) {}

Mono<MutationResult> applyMutation(OrderMutation command) {
    // Kiểm trạng thái/tenant/version và thực hiện atomic update.
    // Trả Mono<MutationResult> sau khi DB xác nhận.
    return writeOrderState(command);
}
~~~

**Cơ chế:**

- `groupBy(OrderMutation::orderId)` tách stream thành các `GroupedFlux` theo order ID.
- Mỗi nhóm dùng `concatMap` nên **những event cùng order được subscribe tuần tự**.
- `flatMap(..., 8)` cho phép tối đa tám **nhóm đang được tiêu thụ** cùng lúc, tạo concurrency giữa các order.

**Giới hạn nghiêm trọng:** `groupBy` không thích hợp vô điều kiện với một **stream vô hạn có số key không giới hạn**. Nó giữ trạng thái và queue cho các nhóm; khi số nhóm lớn nhưng outer concurrency thấp, nguồn có thể bị backpressure hoặc đình trệ vì các nhóm chưa được tiêu thụ. Chỉ dùng với cardinality đã kiểm soát, hoặc phân hoạch bằng **số partition cố định**, consumer theo key, hay hệ thống queue riêng.

### 8.3. Bounded partitions khi số key lớn

Một ingest service có thể hash `orderId` vào **K partition cố định**; mỗi partition xử lý tuần tự, các partition khác chạy đồng thời. Tuy nhiên cần xác định:

- Partition ordering của message broker, nhiều consumer instances.
- Retry/rebalance có làm đảo thứ tự hay không.
- Tính đồng nhất của hash function khi scale K.
- Hot-key làm một partition quá tải.

Ví dụ thiết kế:

~~~text
hash(orderId) % 8
     |
     +-- partition 0: concatMap(write)
     +-- partition 1: concatMap(write)
     ...
     +-- partition 7: concatMap(write)

Các partition được consume đồng thời; mỗi partition giữ FIFO.
~~~

Đừng xem `groupBy` trong **một process** là khóa phân tán: hai instance service vẫn có thể ghi cùng order đồng thời. Dù đã tuần tự theo key tại một worker, vẫn nên dùng **atomic conditional update**, optimistic locking/`@Version` và idempotency ở MongoDB.

### 8.4. Atomic update là tuyến bảo vệ cuối

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import reactor.core.publisher.Mono;

Mono<MutationResult> applyMutation(OrderMutation command) {
    Query eligible = Query.query(
        Criteria.where("id").is(command.orderId())
            .and("tenantId").is(command.tenantId())
            .and("state").is("PENDING")
    );

    return reactiveMongoTemplate.updateFirst(
        eligible,
        new Update().set("state", command.newState()),
        OrderDocument.class
    ).flatMap(result -> {
        if (result.getMatchedCount() != 1) {
            return Mono.error(
                new IllegalStateException(
                    "Order missing, wrong tenant or state changed"));
        }
        return Mono.just(new MutationResult(
            command.orderId(), command.newState()
        ));
    });
}
~~~

`OrderDocument` ở mục 18 được ánh xạ vào collection order dùng cho transaction example; điều kiện ở đây minh họa chuyển từ `PENDING`. Với chuỗi trạng thái `APPROVED → SHIPPED` phải truyền/kiểm expected state đúng từng command, không hardcode mọi transition đều từ PENDING.

Atomic conditional update giúp phát hiện cạnh tranh **kể cả khi nhiều service instances cùng ghi**, trong khi `concatMap` chỉ kiểm soát thứ tự trên **stream cục bộ**.

## 9. Backpressure không thay thế giới hạn số write

Reactive Streams hỗ trợ **request(n)** để consumer yêu cầu item theo năng lực xử lý. Nhưng backpressure ở một nguồn không chứng minh MongoDB có đủ CPU, connection và journal bandwidth cho mọi write.

### 9.1. Điều `flatMap(..., N)` kiểm soát

~~~java
Flux<WriteJob> stream = commands
    .flatMap(this::writeOne, 8);
~~~

N giới hạn số inner Publisher active **của pipeline đó**. Reactor còn có các thuộc tính như `prefetch` làm thay đổi cách lấy dữ liệu nguồn và buffering. Nếu mapper chỉ phát `Mono`, đây là mô hình tương đối dễ suy luận; nếu mỗi mapper phát `Flux` nhiều result, phải xem cả số item **trong từng inner**.

### 9.2. `limitRate` chỉ điều tiết demand

~~~java
commands
    .limitRate(64)
    .flatMap(this::writeOne, 8);
~~~

`limitRate` điều tiết cách request từ upstream theo từng đợt. Nó **không giới hạn tổng concurrency trên toàn app** và không phải một hàng đợi chịu lỗi/durable queue. Nếu producer là nguồn hot tạo sự kiện nhanh hơn consumer, cần kiểm backpressure behavior của chính producer.

### 9.3. `onBackpressureBuffer` không thể giải quyết vô hạn

~~~java
// Nguy cơ: buffer không giới hạn nếu producer luôn nhanh hơn MongoDB.
// source.onBackpressureBuffer()
//       .flatMap(this::writeOne, 8);
~~~

Một buffer tăng không giới hạn chỉ **chuyển nghẽn từ MongoDB sang heap**. Với nguồn hot, đặt capacity rõ, chính sách overflow cụ thể và tôn trọng semantic **không được mất write**. Không được chọn `DROP` chỉ vì nó dễ giảm RAM nếu đây là payment/ledger event.

### 9.4. Rate-limit và concurrency-limit là hai trục khác

| Giới hạn | Ví dụ | Bảo vệ |
| --- | --- | --- |
| Concurrent in-flight | Tối đa 8 write active | Tránh quá nhiều operation cùng lúc |
| Rate per second | Tối đa 300 write/giây | Giảm burst/sức ép bền vững theo thời gian |
| Queue capacity | Tối đa 5.000 event chờ | Không để RAM/queue tăng vô hạn |
| Batch size | 200 document/request | Giảm round trip, kiểm kích thước gói |
| Request deadline | 5 giây/API | Giới hạn thời gian chờ client, **không hủy chắc write** |

Một thiết kế nghiêm túc cần chọn các giới hạn theo SLO. Giới hạn in-flight 8 vẫn có thể tạo tốc độ cao nếu mỗi write chỉ 1 ms; ngược lại tốc độ thấp nếu majority write mất 500 ms.

### 9.5. Phải giới hạn cả ingress

Giả sử controller nhận một `Flux<WriteCommand>` rất dài:

~~~java
public Flux<WriteJob> importCommands(Flux<WriteCommand> source) {
    return source.flatMap(this::writeOne, 8);
}
~~~

Điều này kiểm soát write tại pipeline, nhưng API còn cần:

- Authentication/authorization và tenant isolation.
- Kích thước body, số command tối đa hoặc giao thức streaming có quota.
- Deadline và hành vi client disconnect.
- Giới hạn job đang chờ/đang xử lý theo tenant và instance.
- Hình thức báo nhận `ACCEPTED` vs `PERSISTED` vs `PROCESSING`.

Không trộn “client đã gửi toàn bộ JSON body” với “MongoDB đã xác nhận toàn bộ writes”.

## 10. Khi nào nên chọn batch insert hoặc bulk operations?

Nếu có 100.000 document độc lập, gọi 100.000 lần `repository.insert` có overhead. Spring Data Reactive MongoDB hỗ trợ **insert collection** và **bulk operations** để giảm round trip.

### 10.1. Batch insert bằng `ReactiveMongoTemplate.insert`

~~~java
import java.util.List;
import reactor.core.publisher.Flux;

Flux<WriteJob> insertBatch(List<WriteJob> docs) {
    return reactiveMongoTemplate.insert(docs, WriteJob.class);
}
~~~

Đây là **batch insert** qua template; mỗi document vẫn chịu constraint như `_id` unique và validation. Hành vi lỗi/batch result phụ thuộc driver, ordered behavior và cấu hình, không tự tạo một transaction xuyên suốt toàn bộ batch.

### 10.2. Chia nguồn thành batch có kích thước hữu hạn

~~~java
int batchSize = 200;

Mono<Void> writeAll = commands
    .map(command -> toDocument(command))
    .buffer(batchSize)
    .concatMap(batch ->
        reactiveMongoTemplate.insert(batch, WriteJob.class)
            .then()
    )
    .then();
~~~

Lúc này chỉ có **một batch write đang được subscribe** tại một thời điểm vì dùng `concatMap`. Mỗi batch có tối đa 200 document. Batch size phải tôn trọng kích thước document, giới hạn BSON/request và RAM thực tế.

### 10.3. Cho phép một số batch cùng xử lý

~~~java
Mono<Void> writeAll = commands
    .map(command -> toDocument(command))
    .buffer(200)
    .flatMap(
        batch -> reactiveMongoTemplate
            .insert(batch, WriteJob.class)
            .then(),
        2  // Tối đa 2 batch Publisher active.
    )
    .then();
~~~

**Cần giải thích đúng:** hai batch đồng thời **không đồng nghĩa 400 single-document requests đồng thời**. Mỗi batch là một lần gọi insert(collection) theo driver, có thể được chia thành nhiều wire batches khi giới hạn kích thước; server vẫn xử lý các document bên trong theo cơ chế batch. `N × batchSize` chỉ là giới hạn **số document được pipeline giữ để gửi theo các batch đang active**, không phải số connection.

### 10.4. `ReactiveBulkOperations` với ordered/unordered

~~~java
import com.mongodb.bulk.BulkWriteResult;
import org.springframework.data.mongodb.core.BulkOperations;
import reactor.core.publisher.Mono;

Mono<BulkWriteResult> bulkInsert(List<WriteJob> docs) {
    return reactiveMongoTemplate
        .bulkOps(
            BulkOperations.BulkMode.UNORDERED,
            WriteJob.class
        )
        .insert(docs)
        .execute();
}
~~~

`BulkMode.ORDERED` yêu cầu các thao tác trong batch tuân theo trình tự nhất định và thường dừng khi lỗi đầu xảy ra; `UNORDERED` cho phép server/driver thực hiện các thao tác với thứ tự không được đảm bảo và có thể tiếp tục nhiều thao tác dù có lỗi. **Unordered không tự bảo đảm batch atomic hay exactly-once.**

Khi dùng bulk:

- Lỗi duplicate có thể làm **một phần document đã được chèn**.
- `BulkWriteResult` và exception có thông tin thành công/thất bại tùy write concern/driver.
- Không dựa vào thứ tự kết quả để khẳng định thứ tự nghiệp vụ khi chọn unordered.
- Bulk operations có giới hạn về entity lifecycle events/callbacks/version mapping so với các lệnh repository thông thường; đối chiếu tài liệu Spring Data theo phiên bản dự án.

### 10.5. Bulk write hiện đại ở MongoDB 8.0+

Các phiên bản Spring Data MongoDB mới có API `bulkWrite(...)`; MongoDB 8.0+ cho phép bulk write qua **nhiều collection trong một request**. Tính năng này khác với `bulkOps(...)` truyền thống cho một collection.

**Không nhầm “một bulk request” với “một multi-document transaction”.** Nếu nghiệp vụ cần commit/abort xuyên nhiều collection, phải xác định transaction/session và các giới hạn driver/server; chỉ gom vào một request chưa đảm bảo all-or-nothing.

### 10.6. Batch theo thời gian: `bufferTimeout`

Nếu input đến đều hoặc từng đợt nhỏ:

~~~java
Flux<List<WriteJob>> batches = commands
    .map(command -> toDocument(command))
    .bufferTimeout(
        200,
        java.time.Duration.ofMillis(250)
    );

Mono<Void> done = batches
    .flatMap(
        batch -> bulkInsert(batch).then(),
        2
    )
    .then();
~~~

Pipeline phát batch khi đủ 200 phần tử hoặc tới mốc thời gian 250 ms (với các điều kiện thời gian/demand của Reactor). Thời gian giúp giảm độ trễ của **batch chưa đầy**; nó không phải flush durability hay database journal timeout.

### 10.7. Bảng chọn thao tác

| Tình huống | API/operator phù hợp | Cảnh báo |
| --- | --- | --- |
| Một document, cần result entity | `repository.insert` | ID duplicate/acknowledgment |
| Nhiều document độc lập, lượng nhỏ | `flatMap(insert,N)` | Có thể ra sai thứ tự và partial success |
| Rất nhiều document cùng collection | `template.insert(List,Class)` hoặc `bulkOps` | Batch limit, lỗi từng item |
| Bulk insert/update/delete trong collection | `bulkOps(ORDERED/UNORDERED)` | Không atomic toàn batch |
| Multiple collections, server 8.0+ | `bulkWrite` API mới nếu phiên bản hỗ trợ | Không tự là transaction |
| Nhiều write phụ thuộc theo thứ tự | `concatMap`, `then` | Thứ tự không đồng nghĩa atomicity |
| Hai collection cần cùng commit/abort | Reactive transaction, write **tuần tự** | Không dùng parallel writes chung transaction |

## 11. Lỗi giữa chừng: luồng dừng nhưng dữ liệu có thể đã ghi

Giả sử:

~~~java
return Flux.fromIterable(commands)
    .flatMap(this::writeOne, 8);
~~~

Nếu command số 7 gặp duplicate key:

1. Ít nhất một số command khác **có thể đã được server ghi thành công**.
2. `flatMap` mặc định phát error ra downstream và có thể cancel các inner chưa hoàn thành.
3. Cancellation làm ngừng đăng ký/tiêu thụ ở client, **không tự rollback** các write đã tới server.
4. Có thể không biết chắc tất cả write đang in-flight đã được apply hay chưa, nếu lỗi mạng/timeout xen vào.

**Không kết luận “Flux lỗi thì toàn bộ 8 writes đang chạy đều thất bại”.**

### 11.1. Fail-fast có ý nghĩa khi nào?

Nếu pipeline là một tác vụ import có yêu cầu **dừng gửi thêm** khi lỗi bất kỳ, fail-fast có thể hợp lý. Nhưng phải ghi nhận partial results và có quy trình đối soát/retry. Nếu nghiệp vụ cần all-or-nothing, fail-fast **không thay transaction**.

### 11.2. `onErrorResume` ở ngoài khác ở trong mapper

Ở **ngoài**:

~~~java
Flux<WriteJob> result = commands
    .flatMap(this::writeOne, 8)
    .onErrorResume(ex -> Flux.empty());
~~~

Đây thường là **mẫu nguy hiểm**: một lỗi có thể làm luồng chính dừng, rồi `onErrorResume` che lỗi và complete rỗng, trong khi các item đã ghi có thể còn tồn tại. Không có báo cáo item nào lỗi và outcome nào unknown.

Ở **mỗi item**:

~~~java
Flux<WriteOutcome> report = commands.flatMap(
    command -> writeWithOutcome(command),
    8
);
~~~

`writeWithOutcome` có thể biến **một số lỗi đã phân loại** thành giá trị `WriteOutcome` thay vì ném ra lỗi luồng toàn cục, để những item khác tiếp tục. Nhưng điều này **chỉ đúng khi chúng thực sự độc lập**, không có yêu cầu atomicity toàn batch.

### 11.3. `flatMapDelayError` và giới hạn của nó

Reactor có `flatMapDelayError` để **trì hoãn phát lỗi** tới khi đã cho nhiều inner kết thúc, theo giới hạn cấu hình. Nó có thể hữu ích khi muốn thu thập kết quả trong điều kiện lỗi từng item, nhưng:

- Không tạo transaction.
- Không biến lỗi không xác định thành lỗi chắc chắn không ghi.
- Không tự sinh báo cáo status của từng command.

Nếu hệ thống phải trả danh sách kết quả từng item cho API, **dùng kiểu `WriteOutcome` explicit** thường dễ duy trì hơn một exception tổng hợp duy nhất.

### 11.4. Đừng dùng `onErrorContinue` như cơ chế “bỏ item lỗi”

`onErrorContinue` tác động đến cách một số upstream operator xử lý lỗi và có semantics phức tạp; không phải toàn bộ reactive MongoDB write đều hỗ trợ recover theo cách bạn mong muốn.

Đặt error handling **ngay ở inner Publisher của từng command** bằng `onErrorResume` có chọn lọc, hoặc chia batch thành job bền vững có trạng thái riêng.

## 12. Thiết kế kết quả từng item (`WriteOutcome`)

Khi client cần biết cái gì đã ghi, cái gì trùng và cái gì chưa chắc chắn, một `Flux<WriteJob>` đơn giản có thể chưa đủ.

### 12.1. Trạng thái kết quả

~~~java
// WriteOutcome.java
package com.example.reactivewrites;

public record WriteOutcome(
    String id,
    Status status,
    String detail
) {
    public enum Status {
        INSERTED,
        ALREADY_PRESENT,
        CONFLICT,
        UNKNOWN
    }

    public static WriteOutcome inserted(String id) {
        return new WriteOutcome(id, Status.INSERTED, "acknowledged");
    }
    public static WriteOutcome existing(String id) {
        return new WriteOutcome(id, Status.ALREADY_PRESENT, "same payload");
    }
    public static WriteOutcome conflict(String id) {
        return new WriteOutcome(id, Status.CONFLICT, "payload mismatch");
    }
    public static WriteOutcome unknown(String id) {
        return new WriteOutcome(id, Status.UNKNOWN, "reconciliation needed");
    }
}
~~~

`UNKNOWN` không có nghĩa chắc chắn đã thất bại: đó là trạng thái **không đủ thông tin để xác nhận**, thường gặp khi mất kết nối hoặc write concern chưa đạt mức yêu cầu.

### 12.2. Insert có đối chiếu khi gặp duplicate

~~~java
import org.springframework.dao.DuplicateKeyException;
import reactor.core.publisher.Mono;

Mono<WriteOutcome> writeWithOutcome(WriteCommand command) {
    WriteJob desired = toDocument(command);

    return repository.insert(desired)
        .map(saved -> WriteOutcome.inserted(saved.getId()))
        .onErrorResume(DuplicateKeyException.class, error ->
            repository.findById(command.id())
                .map(existing -> {
                    boolean same =
                        command.tenantId().equals(existing.getTenantId())
                        && java.util.Objects.equals(
                            command.payload(), existing.getPayload());

                    return same
                        ? WriteOutcome.existing(command.id())
                        : WriteOutcome.conflict(command.id());
                })
                .switchIfEmpty(
                    Mono.just(WriteOutcome.unknown(command.id()))
                )
        );
}
~~~

Đoạn ví dụ chỉ minh họa duplicate `_id` do cùng command. Trong ứng dụng có **unique indexes khác**, một `DuplicateKeyException` có thể phát sinh từ một constraint không phải `_id`; khi đó `findById(command.id())` chưa đủ để kết luận cùng request. Cần xác định index vi phạm và so sánh **request fingerprint đầy đủ** (tenant, loại thao tác, payload chuẩn hóa, version, v.v.).

Nếu đọc đối soát từ secondary bị trễ, `findById` có thể tạm không thấy dữ liệu; nên áp read concern/read preference phù hợp với policy đối soát và để outcome UNKNOWN khi chưa đủ bằng chứng.

### 12.3. Không che mọi lỗi thành UNKNOWN

~~~java
// Tránh mẫu này khi chưa phân loại lỗi:
// .onErrorResume(Exception.class, ex ->
//     Mono.just(WriteOutcome.unknown(command.id())))
~~~

Lỗi validation, mapping sai kiểu, thiếu quyền tenant, server selection timeout hoặc lỗi programming không nên bị coi giống nhau. Định nghĩa rõ policy:

- **Conflict chắc chắn:** payload không khớp, ràng buộc nghiệp vụ.
- **Recoverable transient:** có thể retry khi an toàn, giới hạn số lần.
- **Unknown outcome:** có thể đã được server xử lý, cần đối soát.
- **Fatal/system error:** ngừng job và báo vận hành, không im lặng complete.

### 12.4. Kết quả theo thứ tự nhập

~~~java
Flux<WriteOutcome> outcomes =
    Flux.fromIterable(commands)
        .flatMapSequential(this::writeWithOutcome, 8);
~~~

Ở đây output `WriteOutcome` giữ thứ tự source, **dù các insert được thực thi đồng thời**. Điều này hợp lý vì từng command độc lập; nếu cùng ID cần thứ tự ghi, vẫn phải dùng tuần tự theo key hoặc conditional update.

### 12.5. Không `collectList()` vô hạn

~~~java
Mono<List<WriteOutcome>> all = outcomes.collectList();
~~~

`collectList()` giữ toàn bộ kết quả trong heap. Với input cố định nhỏ (ví dụ 100 command/API) có thể chấp nhận; với 10 triệu item hoặc unbounded stream nên **stream kết quả, phân trang/batch, hoặc lưu job status vào DB**.

## 13. Retry: phân loại lỗi và giữ idempotency

### 13.1. Retryable write của driver khác retry của application

MongoDB Java Driver có cơ chế **retryable writes** cho các thao tác đủ điều kiện và topology hỗ trợ. Reactor `retryWhen` ở tầng ứng dụng tạo **subscription lại**; nó không có cùng semantics session/transaction identity như retry nội bộ driver trong mọi trường hợp.

~~~java
import reactor.util.retry.Retry;
import java.time.Duration;

Mono<WriteJob> writeWithLimitedRetry(WriteCommand command) {
    return Mono.defer(() ->
        repository.insert(toDocument(command))
    ).retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
            .filter(this::isTransientAndSafeToRetry)
    );
}
~~~

`isTransientAndSafeToRetry(Throwable)` là một **policy function do dự án phải triển khai**: kiểm loại lỗi, error labels, dạng thao tác và khả năng đối soát. Đừng thay bằng `ex -> true`. Một lỗi duplicate key hoặc validation **không phải** transient retry candidate.

### 13.2. Một request lặp với ID mới là nguy cơ ghi hai lần

Sai:

~~~java
// Anti-pattern: mỗi lần retry tạo ID mới:
// return repository.insert(new WriteJob(
//     UUID.randomUUID().toString(), ...));
~~~

Nếu lần ghi trước đã tới MongoDB nhưng ACK bị mất, retry với ID mới tạo **document thứ hai**. Hãy tạo ID ổn định **trước khi bắt đầu request**, dùng nó xuyên suốt các lần retry và xác minh content trước khi kết luận “đã xử lý”.

### 13.3. `timeout` làm pipeline ngừng chờ, không undo MongoDB

~~~java
Mono<WriteJob> boundedWait = repository.insert(job)
    .timeout(Duration.ofSeconds(3));
~~~

Nếu 3 giây trôi qua, Reactor có thể cancel subscription và phát timeout. Nhưng **write đang in-flight có thể đã được primary xử lý và vẫn commit/replicate sau đó**. Không trả “chưa ghi” chỉ từ `TimeoutException`.

Một endpoint có thể trả `202 Accepted / processing` hoặc trạng thái cần đối soát tùy hợp đồng; chỉ phát `201 Created` khi đạt mức xác nhận cần thiết.

### 13.4. `$inc` và cập nhật không idempotent

~~~java
Mono<com.mongodb.client.result.UpdateResult> decrementStock(
        String productId, int amount) {
    return reactiveMongoTemplate.updateFirst(
        Query.query(Criteria.where("id").is(productId)),
        new Update().inc("stock", -amount),
        ProductStock.class
    );
}
~~~

**Không** retry toàn workflow này mù sau timeout: một retry thành operation mới có thể trừ hàng tồn **hai lần** nếu lần đầu đã ghi.

Thay vào đó, thiết kế **reservation ID duy nhất**, guard trạng thái/version, hoặc transaction/ledger cho mỗi nghiệp vụ; kiểm kết quả trước khi áp lại thay đổi.

### 13.5. Retry không thay thế việc kiểm tra nguồn

Nếu một pipeline đã có 8 write in-flight nhưng bị driver connection pool timeout, retry tất cả ngay lập tức có thể tạo **retry storm**. Kết hợp:

- Exponential backoff + jitter (khi retry an toàn).
- Giới hạn attempt/deadline.
- Giới hạn concurrency toàn instance.
- Circuit breaker/bulkhead khi cluster suy giảm.
- Idempotency/đối soát.
- Metric retry, latency và error labels.

## 14. MongoDB transaction: bắt buộc tuần tự thao tác trong cùng session

Đây là **ranh giới quan trọng nhất** của concurrency.

> MongoDB Java Reactive Streams Driver **không hỗ trợ chạy song song nhiều operation trong cùng một transaction**. Spring Data `ReactiveMongoTransactionManager` gắn `ClientSession` vào Reactor Context; việc share transaction context không làm session hỗ trợ `flatMap(...,8)` hay `Mono.when(...)` an toàn.

### 14.1. Phản ví dụ: concurrent write trong transaction

~~~java
// KHÔNG LÀM:
Mono<Void> invalid = Flux.fromIterable(commands)
    .flatMap(command -> repository.insert(toDocument(command)), 8)
    .then()
    .as(transactionalOperator::transactional);
~~~

Các inner Publisher có thể cùng dùng một session transaction trong Reactor Context và chạy đồng thời, vi phạm giới hạn của MongoDB driver; có thể lỗi session/transaction hoặc kết quả không được hỗ trợ.

### 14.2. Cách đúng nếu mọi item phải cùng commit/abort

~~~java
Mono<Void> atomicBatch = Flux.fromIterable(commands)
    .concatMap(command -> repository.insert(toDocument(command)))
    .then()
    .as(transactionalOperator::transactional);
~~~

`concatMap` khiến từng write hoàn tất trước khi write kế tiếp được subscribe. `TransactionalOperator` bao toàn chuỗi theo reactive transaction context khi các repository/template dùng cùng reactive database factory.

**Nhưng** transaction rất dài cho 100.000 command không phải thiết kế tốt: tài nguyên/snapshot/timeout tăng. Nên giới hạn kích thước atomic batch theo nghiệp vụ, hoặc thay bằng transaction nhỏ per aggregate.

### 14.3. Có thể đồng thời nhiều transaction **riêng biệt**

Giả sử có nhiều order độc lập, mỗi order cần hai write **tuần tự** và atomic:

~~~java
Mono<Void> processOneOrderAtomically(OrderCommand command) {
    return updateOrder(command)
        .then(insertOutbox(command))
        .as(transactionalOperator::transactional);
}

Flux<Void> jobs = Flux.fromIterable(orderCommands)
    .flatMap(command -> processOneOrderAtomically(command), 4);

Mono<Void> allDone = jobs.then();
~~~

Mỗi subscription của inner flow có thể tạo **transaction riêng** khi **không có outer transaction đang active** (hoặc propagation được cấu hình rõ). Tối đa bốn order workflows chạy đồng thời, **nhưng hai write trong từng transaction chạy tuần tự**.

Trong ví dụ thực tế, `flatMap` với `Mono<Void>` không phát `onNext`, chỉ completion/error; `jobs.then()` là tín hiệu chờ cả pipeline. Để báo kết quả từng order, phát một `OrderOutcome` sau commit, không dùng `zip` các `Mono<Void>`.

### 14.4. Hết sức thận trọng với outer transaction

Nếu caller đã đặt:

~~~java
@Transactional(transactionManager = "reactiveMongoTransactionManager")
public Mono<Void> processAll(List<OrderCommand> commands) {
    return Flux.fromIterable(commands)
        .flatMap(this::processOneOrderAtomically, 4)
        .then();
}
~~~

thì các inner transactional operators có thể **tham gia transaction outer** theo `PROPAGATION_REQUIRED` mặc định, khiến nhiều write ở một shared transaction chạy song song. Không đặt outer transaction bao trùm khi mục tiêu là **nhiều transaction tách biệt**.

Nếu cần phân tách rõ, dùng transaction definition với propagation phù hợp, kiểm resource/session/context và test. Đừng giải quyết bằng cách tăng concurrency mà bỏ qua transaction boundary.

### 14.5. Transaction và error handling per item

Trong transaction atomic, nếu một item lỗi mà code chuyển thành `WriteOutcome.CONFLICT` rồi complete bình thường **bên trong operator**, transaction có thể đi tới commit các write trước đó nếu server chưa abort.

Vì vậy:

- Muốn **all-or-nothing**: lỗi phải khiến transaction abort, không nuốt error.
- Muốn **partial success per item**: đừng bọc mọi item trong một transaction chung; chia transaction nhỏ hoặc dùng độc lập.
- Muốn **retry transaction body**: cần phân loại `TransientTransactionError` và đảm bảo toàn body idempotent/không side effect ngoài DB.
- Muốn **retry commit** khi `UnknownTransactionCommitResult`: dùng cơ chế driver/session phù hợp, không tự lặp toàn bộ body như command mới.

## 15. Cấu hình reactive transaction trong Spring

### 15.1. Bean transaction manager

~~~java
// ReactiveTransactionConfig.java
package com.example.reactivewrites;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Configuration
public class ReactiveTransactionConfig {

    @Bean
    ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }

    @Bean
    TransactionalOperator transactionalOperator(
            ReactiveMongoTransactionManager manager) {
        return TransactionalOperator.create(manager);
    }
}
~~~

MongoDB phải chạy dưới **replica set/sharded deployment hỗ trợ transactions**; một standalone server không đáp ứng use case multi-document transaction. Đồng thời `ReactiveMongoTemplate` và repository phải dùng cùng `ReactiveMongoDatabaseFactory` để tham gia transaction nhất quán.

### 15.2. Reactive service dùng `@Transactional`

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class OrderWriteService {
    private final ReactiveMongoTemplate mongo;

    public OrderWriteService(ReactiveMongoTemplate mongo) {
        this.mongo = mongo;
    }

    @Transactional(
        transactionManager = "reactiveMongoTransactionManager"
    )
    public Mono<Void> approveAndPublish(OrderCommand command) {
        return updateOrder(command)
            .then(insertOutbox(command))
            .then();
    }
}
~~~

`updateOrder`/`insertOutbox` là phương thức reactive được định nghĩa với lệnh MongoDB cụ thể trong mục 18. Khi `@Transactional` được intercept **qua Spring proxy**, transaction bao quanh quá trình subscription và commit/abort của Publisher, không chỉ khoảng thời gian Java tạo object `Mono`.

### 15.3. Không tự `subscribe()` trong method transactional

~~~java
// KHÔNG LÀM:
@Transactional
public Mono<Void> broken(OrderCommand command) {
    updateOrder(command).subscribe();    // Chuỗi bị tách khỏi transaction.
    insertOutbox(command).subscribe();   // Không có ordering rõ.
    return Mono.empty();
}
~~~

Inner `subscribe` tạo subscriber/context mới và không nối completion/error vào publisher trả về. Dù may mắn DB đã ghi, transaction interceptor không quản lý được những thao tác ấy như một chuỗi duy nhất. **Luôn return một publisher đã được compose đầy đủ**.

### 15.4. Không gọi `block()` trong WebFlux event loop

~~~java
// KHÔNG LÀM trên reactive thread:
// reactiveMongoTemplate.insert(job).block();
~~~

`block()` giữ thread chờ và có thể gây starvation; thêm `Schedulers.boundedElastic` vô tội vạ cũng không giải quyết vấn đề phối hợp transaction/reactive context. Dùng `then`, `flatMap` và transaction operator/manager đúng loại.

### 15.5. Cancellation và commit ambiguity

Nếu client ngắt kết nối khi transaction đang commit, cancellation phía Publisher **không chứng minh MongoDB đã abort thành công**. Một commit có thể hoàn tất nhưng client không nhận ACK. Trong nghiệp vụ có giá trị cao, cần ID ổn định và quy trình đối soát trạng thái, không tự coi HTTP disconnect là rollback.

## 16. Thiết kế mức đồng thời theo phạm vi nghiệp vụ

### 16.1. Ba cấp thường gặp

~~~text
LEVEL A: trong một aggregate
  -> tuần tự / conditional update / transaction nhỏ.

LEVEL B: giữa các aggregate độc lập
  -> flatMap(..., N) có giới hạn.

LEVEL C: toàn instance / nhiều instance
  -> bounded ingress, queue/consumer concurrency, quota, metric.
~~~

Một `flatMap(..., N)` ở Level B không thay thế giới hạn ở Level C. Một transaction ở Level A không làm mọi order khác tự động bị tuần tự hóa.

### 16.2. Công thức quyết định thực tế

Trước khi chọn operator, trả lời:

1. Nếu write A và B đến ngược thứ tự, nghiệp vụ có sai không?
2. Nếu A thành công nhưng B thất bại, trạng thái có chấp nhận được không?
3. Nếu retry một command sau timeout, có thể tạo hiệu ứng hai lần không?
4. Có cùng `ClientSession`/transaction hay không?
5. Có bao nhiêu request/consumer chạy **đồng thời toàn hệ thống**?
6. Nếu MongoDB chậm 10 lần, hàng đợi/heap sẽ tăng tới bao nhiêu?
7. Caller cần response theo **thứ tự gửi**, thứ tự hoàn tất, hay không quan trọng?

### 16.3. Bảng khuyến nghị

| Đặc điểm | Thiết kế ưu tiên |
| --- | --- |
| Các insert độc lập, key duy nhất | `flatMap(insert,N)`, bounded ingress |
| Cần response theo input order, write vẫn độc lập | `flatMapSequential(insert,N)` |
| Cùng document, nhiều transition theo thứ tự | `concatMap` per key + atomic condition |
| Một write phải xong trước write thứ hai | `flatMap`/`then` |
| Mọi write phải commit/abort cùng nhau | Transaction + **sequential operators** |
| Cần hai write độc lập hoàn thành | `Mono.when`, chấp nhận partial failure |
| Cần giá trị từ hai write độc lập | `Mono.zip` với hai `Mono<T>` không rỗng |
| Khối lượng lớn, cùng collection | `buffer` + `template.insert`/`bulkOps` |
| Bulk có thể partial failure | Kết quả/bản ghi outcome từng item, idempotency |
| Rất nhiều tenants/jobs, nhiều process | Queue/partition/admission control toàn hệ thống |

### 16.4. Concurrency là cấu hình vận hành, không phải constant vô hạn

Có thể cấu hình từ properties:

~~~properties
app.mongo-write.max-in-flight-per-worker=8
app.mongo-write.batch-size=200
app.mongo-write.active-batches=2
~~~

Đây là **custom properties của ứng dụng**, không phải những tên cấu hình built-in của Spring Data MongoDB. Phải khai báo `@ConfigurationProperties`/validation hoặc inject biến cấu hình. Cần giới hạn min/max cho chúng; một operator nhận concurrency `0` hoặc giá trị quá lớn không phải cơ chế tự chữa.

## 17. Ví dụ end-to-end: import độc lập có kết quả từng item

Ứng dụng nhận một danh sách `WriteCommand`, muốn ghi tối đa tám item đồng thời, giữ thứ tự **response** theo input và phân loại duplicate đã tồn tại thành công hay conflict.

### 17.1. Service hoàn chỉnh trong phạm vi import

~~~java
// WriteImportService.java
package com.example.reactivewrites;

import java.time.Instant;
import java.util.Objects;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class WriteImportService {
    private final WriteJobRepository repository;

    public WriteImportService(WriteJobRepository repository) {
        this.repository = repository;
    }

    public Flux<WriteOutcome> importIndependent(
            Flux<WriteCommand> commands) {
        return commands.flatMapSequential(
            this::insertOrReconcile,
            8
        );
    }

    private Mono<WriteOutcome> insertOrReconcile(
            WriteCommand command) {
        return Mono.defer(() -> {
            validate(command);

            WriteJob desired = new WriteJob(
                command.id(),
                command.tenantId(),
                command.payload(),
                "NEW",
                Instant.now()
            );

            return repository.insert(desired)
                .map(saved ->
                    WriteOutcome.inserted(saved.getId()))
                .onErrorResume(
                    DuplicateKeyException.class,
                    error -> repository.findById(command.id())
                        .map(existing -> sameRequest(
                            existing, command)
                                ? WriteOutcome.existing(command.id())
                                : WriteOutcome.conflict(command.id()))
                        .switchIfEmpty(Mono.just(
                            WriteOutcome.unknown(command.id())))
                );
        });
    }

    private static boolean sameRequest(
            WriteJob existing, WriteCommand command) {
        return command.tenantId().equals(existing.getTenantId())
            && Objects.equals(
                command.payload(), existing.getPayload());
    }

    private static void validate(WriteCommand command) {
        if (command == null ||
                command.id() == null || command.id().isBlank() ||
                command.tenantId() == null ||
                command.tenantId().isBlank()) {
            throw new IllegalArgumentException(
                "id and tenantId are required");
        }
    }
}
~~~

Đoạn này sử dụng `WriteJobRepository`/`WriteOutcome` đã khai báo ở mục 3 và 12. Nó có **concurrency=8** cho các insert độc lập; `flatMapSequential` giữ thứ tự response theo input.

**Hợp đồng giới hạn rõ:** Code demo chưa có authorization, max request size, global admission control, retry policy cho network/write concern error hoặc fingerprint đầy đủ. `Instant.now()` trong entity có thể khác qua retry; nếu thời điểm là một phần của fingerprint, phải lưu metadata request gốc ổn định. Nó không phải endpoint production có thể copy trực tiếp.

### 17.2. Vì sao `validate` nằm trong `Mono.defer`?

`Mono.defer` bảo đảm việc kiểm tra và tạo document xảy ra khi inner được subscribe, thay vì thực thi side effect đồng bộ ngay lúc mapper được gọi. Exception của `validate` sẽ biến thành **reactive onError** của inner flow.

Nếu mục tiêu là trả error từng item thay vì abort toàn import, hãy định nghĩa trạng thái `REJECTED` và handler riêng **chỉ cho validation error**; đừng chuyển mọi `IllegalArgumentException` của cả framework thành lỗi dữ liệu người dùng mà không phân loại.

### 17.3. Một controller WebFlux giới hạn số item

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/imports")
public class WriteImportController {
    private final WriteImportService service;

    public WriteImportController(WriteImportService service) {
        this.service = service;
    }

    @PostMapping(
        path = "/jobs",
        consumes = MediaType.APPLICATION_NDJSON_VALUE,
        produces = MediaType.APPLICATION_NDJSON_VALUE
    )
    public Flux<WriteOutcome> importJobs(
            @RequestBody Flux<WriteCommand> commands) {
        // Streaming contract: mỗi item có thể được ghi độc lập.
        // Ingress quotas/authorization phải được áp ở gateway/service.
        return service.importIndependent(commands);
    }
}
~~~

**Đây là ví dụ streaming chấp nhận partial progress**, không phải một atomic batch, và chưa có quota/security. Để bảo đảm **“vượt 500 thì không ghi bất kỳ item nào”**, phải validate/đếm input **trước khi subscribe write** (ví dụ materialize batch tối đa 501 item và reject trước khi chạy, với giới hạn byte/total request ở gateway). Cần xử lý tenant từ security context, không tin field tenant từ body.

Đối với một API streaming cho phép partial progress, có thể quy định rõ rằng item đến trước đã ghi và item sau quota bị từ chối; khi ấy **response không phải một atomic batch**.

### 17.4. Controller an toàn hơn với batch nhỏ và reject trước khi ghi

~~~java
@PostMapping(path = "/jobs/batch")
public Mono<java.util.List<WriteOutcome>> importBatch(
        @RequestBody Flux<WriteCommand> commands) {

    return commands.take(501).collectList()
        .flatMap(all -> {
            if (all.size() > 500) {
                return Mono.error(
                    new IllegalArgumentException(
                        "Maximum 500 commands"));
            }
            // Chỉ bắt đầu ghi SAU khi đã kiểm kích thước batch.
            return service.importIndependent(
                Flux.fromIterable(all)
            ).collectList();
        });
}
~~~

Đoạn method là lựa chọn **thay thế** trong cùng controller, không phải lời khuyên dùng `collectList` cho nguồn vô hạn. Nó giữ tối đa 501 command ở tầng này, nhưng cần cấu hình thêm **max request bytes**, HTTP timeout và chính sách xử lý khi nguồn vượt giới hạn. Nếu dữ liệu cần all-or-nothing, kiểm kích thước xong **vẫn chưa đủ**: service hiện ghi độc lập và có thể partial success.

## 18. Ví dụ transaction nhỏ: cập nhật order và ghi outbox tuần tự

Mỗi order approval gồm hai write cần atomicity. Các order khác nhau có thể được xử lý đồng thời bằng **nhiều transaction độc lập**, nhưng mỗi transaction cần **chuỗi tuần tự**.

### 18.1. Domain model tự chứa

~~~java
// OrderCommand.java
package com.example.reactivewrites;

public record OrderCommand(
    String id,
    String tenantId
) {}
~~~

~~~java
// OrderDocument.java
package com.example.reactivewrites;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_reactive_011")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    private String state;

    protected OrderDocument() {}

    public OrderDocument(
            String id, String tenantId, String state) {
        this.id = id;
        this.tenantId = tenantId;
        this.state = state;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getState() { return state; }
}
~~~

~~~java
// OutboxEvent.java
package com.example.reactivewrites;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "outbox_reactive_011")
public class OutboxEvent {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("order_id")
    private String orderId;

    private String eventType;
    private Instant createdAt;

    protected OutboxEvent() {}

    public OutboxEvent(
            String id, String tenantId, String orderId,
            String eventType, Instant createdAt) {
        this.id = id;
        this.tenantId = tenantId;
        this.orderId = orderId;
        this.eventType = eventType;
        this.createdAt = createdAt;
    }

    public String getId() { return id; }
    public String getOrderId() { return orderId; }
}
~~~

### 18.2. Reactive service với `TransactionalOperator`

~~~java
// ReactiveOrderWorkflow.java
package com.example.reactivewrites;

import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderWorkflow {
    private final ReactiveMongoTemplate template;
    private final TransactionalOperator transactions;

    public ReactiveOrderWorkflow(
            ReactiveMongoTemplate template,
            TransactionalOperator transactions) {
        this.template = template;
        this.transactions = transactions;
    }

    public Mono<Void> approveOne(OrderCommand command) {
        return Mono.defer(() -> {
            Query pending = Query.query(
                Criteria.where("id").is(command.id())
                    .and("tenantId").is(command.tenantId())
                    .and("state").is("PENDING")
            );

            Mono<Void> update = template.updateFirst(
                pending,
                new Update().set("state", "APPROVED"),
                OrderDocument.class
            ).flatMap(result -> {
                if (result.getMatchedCount() != 1) {
                    return Mono.error(
                        new IllegalStateException(
                            "Order not eligible"));
                }
                return Mono.<Void>empty();
            });

            Mono<Void> outbox = Mono.defer(() ->
                template.insert(new OutboxEvent(
                    "approved:" + command.id(),
                    command.tenantId(),
                    command.id(),
                    "OrderApproved",
                    Instant.now()
                )).then()
            );

            return update
                .then(outbox)
                .as(transactions::transactional);
        });
    }

    public Mono<Void> approveManyIndependent(
            List<OrderCommand> commands) {
        // Gọi từ nơi KHÔNG có outer transaction.
        return Flux.fromIterable(commands)
            .flatMap(this::approveOne, 4)
            .then();
    }
}
~~~

**Chính xác điều gì được bảo đảm?**

- Trong mỗi inner flow, `update` hoàn tất trước khi `outbox` được subscribe.
- `TransactionalOperator` quản lý commit/abort của **flow đó** nếu nó tạo transaction riêng.
- `approveManyIndependent` cho phép tối đa bốn **order transaction flows** cùng hoạt động.
- Nếu một flow lỗi, lỗi có thể propagate và cancel các flow khác. **Các transaction khác đã commit sẽ không bị rollback**.
- Hàm đòi caller **không bọc một outer reactive transaction**, tránh cả bốn cùng tham gia một shared session.

Nếu yêu cầu “tất cả order trong danh sách cùng commit hoặc cùng rollback”, **không** dùng `approveManyIndependent`: cần một transaction duy nhất với thao tác **tuần tự** và kích thước hợp lý, hoặc điều chỉnh lại hợp đồng nghiệp vụ.

### 18.3. Tại sao không insert outbox bằng `Mono.when`?

Sai:

~~~java
// Vi phạm ordering và có thể vi phạm giới hạn same-session transaction.
return Mono.when(
    updateOrder(command),
    insertOutbox(command)
).as(transactions::transactional);
~~~

Nếu update không khớp, outbox có thể đã được thực hiện; nếu hai write cùng transaction, driver còn không hỗ trợ vận hành song song trong session. Cách đúng:

~~~java
return updateOrder(command)
    .then(insertOutbox(command))
    .as(transactions::transactional);
~~~

Không gọi `subscribe()` riêng hoặc `parallel()` trong transaction.

## 19. Quan sát hiệu năng và sức khỏe pipeline

### 19.1. Metric nên đo

| Metric | Mục đích |
| --- | --- |
| Active inner write subscriptions | Biết pipeline đang có bao nhiêu write active |
| Acknowledged writes/giây | Throughput thực nhận ACK |
| Latency p50/p95/p99 | Phát hiện tail latency, nghẽn journal/replication |
| MongoDB connection pool checked-out/waiting | Phát hiện pool saturation |
| Retry count, duplicate key count | Phân biệt lỗi dữ liệu và lỗi tạm thời |
| Write concern errors/timeouts | Hiểu độ bền/khả dụng của cluster |
| Buffer/queue depth | Phát hiện backlog và nguy cơ OOM |
| Partial success/UNKNOWN outcomes | Đánh giá khả năng đối soát |
| Transaction commit/abort/conflict | Đo contention trong workflows nguyên tử |
| Secondary lag/write ticket pressure | Phát hiện nghẽn phía MongoDB |

Không chỉ nhìn CPU của WebFlux pod. Một service CPU thấp vẫn có thể đẩy MongoDB vào wait queue lớn và làm p99 tăng.

### 19.2. Đo in-flight ở tầng reactive

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;

AtomicInteger active = new AtomicInteger();
AtomicInteger peak = new AtomicInteger();

Flux<WriteJob> output = commands.flatMap(
    command -> Mono.defer(() -> {
        int now = active.incrementAndGet();
        peak.accumulateAndGet(now, Math::max);

        return writeOne(command)
            .doFinally(signal -> active.decrementAndGet());
    }),
    8
);
~~~

Đây là ví dụ đếm **inner Publisher đang được subscribe**, không phải một phép đo chính xác số MongoDB server threads, sockets hoặc disk I/O. Trong hệ thống thực nên xuất metric qua Micrometer và tag có cardinality thấp (không tag theo từng order ID/tenant ID vô hạn).

### 19.3. Đừng nhìn số active mà bỏ qua nhiều request

Nếu mỗi HTTP request tạo đối tượng `AtomicInteger` riêng, metric đó chỉ phản ánh request riêng. Muốn nhìn sức ép **toàn service instance**, dùng meter/limiter được chia sẻ có lifecycle rõ, hoặc thống kê từ connection pool và MongoDB server.

### 19.4. Benchmark từng phương án với dữ liệu đại diện

So sánh:

~~~text
A: concatMap, concurrency = 1
B: flatMap, concurrency = 4
C: flatMap, concurrency = 8
D: flatMap, concurrency = 16
E: buffer(200) + 2 active bulk requests
~~~

Đo cùng workload, document size, index count, write concern, topology và tổng input size; ghi **throughput, p95/p99, CPU, RAM, pool wait, DB latency, error rate**. Một thay đổi concurrency có thể tăng throughput ban đầu rồi làm giảm khi quá bão hòa.

Không so sánh benchmark trên database vừa trống không index với production có unique indexes, majority write và secondary lag.

## 20. Kiểm thử operator bằng `StepVerifier` trước khi dùng MongoDB

Test Reactor thuần giúp kiểm giới hạn active inner, thứ tự và cách lỗi lan truyền, không cần gây tải lên MongoDB. Sau đó cần integration test MongoDB thật cho database behavior.

### 20.1. Kiểm `flatMap` không vượt concurrency

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveOperatorConcurrencyTest {

    @Test
    void flatMapLimitsActiveInnerPublishers() {
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maximum = new AtomicInteger();

        Flux<Integer> writes = Flux.range(1, 12)
            .flatMap(number -> Mono.defer(() -> {
                int now = active.incrementAndGet();
                maximum.accumulateAndGet(now, Math::max);

                return Mono.delay(Duration.ofMillis(25))
                    .map(tick -> {
                        // Chỉ dùng Mono.delay không lỗi trong unit test:
                        // giảm bộ đếm TRƯỚC khi phát onNext/completion.
                        active.decrementAndGet();
                        return number;
                    });
            }), 3);

        StepVerifier.create(writes.collectList())
            .assertNext(result -> {
                assertThat(result).hasSize(12);
                assertThat(result).containsExactlyInAnyOrder(
                    1, 2, 3, 4, 5, 6,
                    7, 8, 9, 10, 11, 12
                );
            })
            .verifyComplete();

        assertThat(maximum.get()).isLessThanOrEqualTo(3);
    }
}
~~~

Test đo **inner Publisher đang hoạt động** của Publisher mô phỏng, không đo MongoDB. Vì ví dụ chỉ dùng `Mono.delay` hoàn tất thành công, nó giảm bộ đếm ngay trước khi phát kết quả để tránh đếm nhầm khoảng trễ sau terminal signal. Với Publisher thật có thể lỗi/cancel, dùng `doFinally`/Micrometer để cleanup trên mọi terminal signal như mục 19.2. Không assert `maximum == 3` một cách cứng nếu runtime scheduler có thể chạy chậm; trọng tâm là không vượt giới hạn.

### 20.2. Test `concatMap` giữ thứ tự

~~~java
@Test
void concatMapKeepsSourceOrder() {
    Flux<Integer> flow = Flux.just(1, 2, 3)
        .concatMap(i ->
            Mono.delay(Duration.ofMillis(20L * (4 - i)))
                .thenReturn(i)
        );

    StepVerifier.create(flow)
        .expectNext(1, 2, 3)
        .verifyComplete();
}
~~~

Mỗi inner chỉ được subscribe khi inner trước hoàn tất. Bất kể 1 có delay lâu hơn 3, thứ tự output vẫn là 1, 2, 3.

### 20.3. Test `flatMapSequential` output order, không kết luận write order

~~~java
@Test
void flatMapSequentialKeepsEmissionOrder() {
    Flux<Integer> flow = Flux.just(1, 2, 3)
        .flatMapSequential(
            i -> Mono.delay(
                    Duration.ofMillis(20L * (4 - i)))
                .thenReturn(i),
            3
        );

    StepVerifier.create(flow)
        .expectNext(1, 2, 3)
        .verifyComplete();
}
~~~

Test này chỉ chứng minh **emission order**. Dù item 3 có thể xử lý xong trước item 1, Reactor giữ item 3 đợi tới lượt. Không dùng kết quả test để khẳng định ba write lên **cùng document** xảy ra tuần tự.

### 20.4. Test lỗi không đồng nghĩa rollback

~~~java
@Test
void oneErrorStopsStreamButDoesNotUndoOtherEffects() {
    java.util.List<Integer> completed =
        new java.util.concurrent.CopyOnWriteArrayList<>();

    Flux<Integer> flow = Flux.just(1, 2, 3)
        .concatMap(i -> {
            if (i == 2) {
                return Mono.<Integer>error(
                    new IllegalStateException("item 2 failed"));
            }
            return Mono.just(i)
                .doOnNext(completed::add);
        });

    StepVerifier.create(flow)
        .expectNext(1)
        .expectError(IllegalStateException.class)
        .verify();

    assertThat(completed).containsExactly(1);
}
~~~

Đây là mô phỏng side effect trong memory. Nó minh họa item 1 đã hoàn tất trước khi item 2 lỗi; **không** mô phỏng rollback MongoDB hay các race network của `flatMap`. Integration test mới kiểm được dữ liệu đã persisted.

## 21. Integration test với MongoDB thật

Unit test mock `ReactiveMongoRepository` không kiểm được query mapping, unique indexes, write acknowledgment, lỗi bulk hoặc transaction session. Cần chạy integration test trên MongoDB test instance/Testcontainers phù hợp.

### 21.1. Bộ điều kiện test

- MongoDB test riêng, không dùng production.
- Spring Boot với starter Reactive MongoDB, Reactor Test và test framework.
- Entity/repository có trong phạm vi scan của context.
- Fixture ID/tenant riêng và cleanup đúng dữ liệu do test tạo.
- Không để nhiều test song song tranh cùng key/collection nếu không được thiết kế cách ly.
- Với transaction, dùng **replica set**; single-node replica set đủ kiểm commit/abort cơ bản, không đủ mô phỏng failover nhiều node.
- Khởi tạo collection/index cần thiết **trước khi** bắt đầu transaction.

### 21.2. Test các insert độc lập đồng thời

~~~java
package com.example.reactivewrites;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.stream.IntStream;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@DataMongoTest
class ConcurrentMongoWritesTest {
    private static final String TENANT = "it-reactive-011";

    @Autowired WriteJobRepository repository;
    @Autowired ReactiveMongoTemplate template;

    @AfterEach
    void cleanup() {
        Query scope = Query.query(
            Criteria.where("tenantId").is(TENANT)
        );
        StepVerifier.create(
            template.remove(scope, WriteJob.class)
                .then()
        ).verifyComplete();
    }

    @Test
    void insertsIndependentJobsWithBoundedConcurrency() {
        List<WriteJob> docs = IntStream.range(0, 12)
            .mapToObj(i -> new WriteJob(
                "it-rw011-" + i,
                TENANT,
                "payload-" + i,
                "NEW",
                Instant.parse("2026-11-01T00:00:00Z")
            ))
            .toList();

        StepVerifier.create(
            Flux.fromIterable(docs)
                .flatMap(repository::insert, 3)
                .collectList()
        )
          .assertNext(saved -> {
              assertThat(saved).hasSize(12);
              assertThat(saved)
                  .extracting(WriteJob::getId)
                  .containsExactlyInAnyOrderElementsOf(
                      docs.stream()
                          .map(WriteJob::getId)
                          .toList()
                  );
          })
          .verifyComplete();

        StepVerifier.create(
            template.count(
                Query.query(
                    Criteria.where("tenantId").is(TENANT)
                ),
                WriteJob.class
            )
        )
          .expectNext(12L)
          .verifyComplete();
    }
}
~~~

**Test chứng minh:** tất cả 12 writes có ACK và tồn tại đúng tenant trên database test. Nó **không đo chính xác** số network requests in-flight: để kiểm concurrency/operator, dùng test `AtomicInteger` ở mục 20.1 và metric driver.

### 21.3. Test không có transaction thì partial success có thể tồn tại

Thêm vào class ở trên:

~~~java
@Test
void duplicateAfterFirstInsertDoesNotUndoFirstInsert() {
    String id = "it-rw011-duplicate";

    WriteJob first = new WriteJob(
        id, TENANT, "first", "NEW", Instant.now()
    );
    WriteJob duplicate = new WriteJob(
        id, TENANT, "different", "NEW", Instant.now()
    );

    // concatMap giúp thứ tự test xác định.
    StepVerifier.create(
        Flux.just(first, duplicate)
            .concatMap(repository::insert)
    )
      .assertNext(saved ->
          assertThat(saved.getPayload()).isEqualTo("first"))
      .expectError(
          org.springframework.dao.DuplicateKeyException.class
      )
      .verify();

    // Document của lần insert đầu vẫn tồn tại.
    StepVerifier.create(repository.findById(id))
        .assertNext(saved ->
            assertThat(saved.getPayload()).isEqualTo("first"))
        .verifyComplete();
}
~~~

Vì không có transaction bao quanh, lỗi duplicate của item thứ hai **không undo** item thứ nhất. Đây là lý do batch import cần hợp đồng partial progress rõ ràng và idempotency.

### 21.4. Integration test reactive transaction commit/abort

Để test phần này, dùng bean `ReactiveTransactionConfig` và `ReactiveOrderWorkflow` ở mục 15 và 18:

~~~java
package com.example.reactivewrites;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@DataMongoTest
@Import({
    ReactiveTransactionConfig.class,
    ReactiveOrderWorkflow.class
})
class ReactiveOrderTransactionTest {
    private static final String TENANT = "it-tx-reactive-011";

    @Autowired ReactiveMongoTemplate template;
    @Autowired ReactiveOrderWorkflow workflow;

    private Mono<Void> ensureCollections() {
        return template.collectionExists(OrderDocument.class)
            .flatMap(exists -> exists
                ? Mono.<Void>empty()
                : template.createCollection(OrderDocument.class).then()
            )
            .then(template.collectionExists(OutboxEvent.class)
                .flatMap(exists -> exists
                    ? Mono.<Void>empty()
                    : template.createCollection(OutboxEvent.class).then()
                )
            );
    }

    private Mono<Void> clearFixture(String id) {
        Query order = Query.query(Criteria.where("id").is(id));
        Query event = Query.query(
            Criteria.where("id").is("approved:" + id)
        );

        return template.remove(order, OrderDocument.class)
            .then(template.remove(event, OutboxEvent.class))
            .then();
    }

    @Test
    void commitsOrderAndOutboxTogether() {
        String id = "it-tx011-commit";

        Mono<Void> scenario = ensureCollections()
            .then(clearFixture(id))
            .then(template.insert(new OrderDocument(
                id, TENANT, "PENDING"
            )))
            .then(workflow.approveOne(
                new OrderCommand(id, TENANT)
            ));

        StepVerifier.create(scenario).verifyComplete();

        StepVerifier.create(
            template.findById(id, OrderDocument.class)
        )
          .assertNext(order ->
              assertThat(order.getState())
                  .isEqualTo("APPROVED"))
          .verifyComplete();

        StepVerifier.create(
            template.findById("approved:" + id, OutboxEvent.class)
        )
          .expectNextCount(1)
          .verifyComplete();

        StepVerifier.create(clearFixture(id)).verifyComplete();
    }

    @Test
    void duplicateOutboxAbortsOrderStateChange() {
        String id = "it-tx011-abort";

        Mono<Void> prepare = ensureCollections()
            .then(clearFixture(id))
            .then(template.insert(new OrderDocument(
                id, TENANT, "PENDING"
            )))
            .then(template.insert(new OutboxEvent(
                "approved:" + id,
                TENANT, id, "PREEXISTING",
                Instant.parse("2026-11-01T00:00:00Z")
            )))
            .then();

        StepVerifier.create(prepare).verifyComplete();

        StepVerifier.create(workflow.approveOne(
            new OrderCommand(id, TENANT)
        ))
          .expectError(DuplicateKeyException.class)
          .verify();

        StepVerifier.create(
            template.findById(id, OrderDocument.class)
        )
          .assertNext(order ->
              assertThat(order.getState())
                  .isEqualTo("PENDING"))
          .verifyComplete();

        StepVerifier.create(
            template.findById("approved:" + id, OutboxEvent.class)
        )
          .assertNext(event ->
              assertThat(event.getOrderId()).isEqualTo(id))
          .verifyComplete();

        StepVerifier.create(clearFixture(id)).verifyComplete();
    }
}
~~~

Ý nghĩa test rollback: transaction đã update order sang APPROVED trong session rồi cố insert outbox trùng `_id`; write thứ hai bị lỗi, transaction abort nên **order vẫn PENDING**. Outbox preexisting vẫn tồn tại vì nó được insert **trước transaction** và không thuộc rollback.

**Điều kiện để tái hiện chính xác:**

- Test DB là replica set hỗ trợ transaction.
- Mọi thao tác trong `approveOne` dùng reactive template cùng factory/session do `TransactionalOperator` quản lý.
- Có collection trước transaction.
- Fixture được cách ly khỏi test khác.
- Transaction write concern/driver được cấu hình phù hợp; `expectError` có thể cần điều chỉnh nếu phiên bản Spring Data bọc lỗi duplicate khác, nhưng **trạng thái persisted** mới là điều cốt lõi.

### 21.5. Giới hạn của integration test

Một single-node replica set cho phép chứng minh **atomic commit/abort** cơ bản nhưng không kiểm:

- Election/failover và khả năng rollback của write concern yếu.
- Multi-node majority durability.
- Bão hòa connection pool trên 30 instances.
- Race giữa các workers phân tán.
- Hành vi bulk 1 triệu document dưới load thực.

Những yêu cầu này cần benchmark/chaos test riêng trong môi trường được phép phá lỗi, không làm trên database production hoặc instance test dùng chung.

## 22. Những sai lầm thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `Flux<Mono<WriteJob>>` nhưng không có write | Dùng `map` tạo Publisher lồng | `flatMap`/`concatMap` |
| Service trả thành công trước khi write xong | Tự `subscribe()` rồi return | Return publisher hoàn chỉnh tới caller |
| `flatMapSequential` output đúng thứ tự nhưng DB state sai | Chỉ bảo đảm emission order | Tuần tự write theo key/conditional update |
| Nhiều write cùng order bị đảo thứ tự | `flatMap` trộn inner | `concatMap` theo key, version guard |
| Gọi `Mono.when(insert,update)` làm update không match | Hai operation phụ thuộc bị subscribe cùng lúc | `then`/`flatMap` nối dependency |
| `Mono.zip(Mono<Void>, Mono<Void>)` không emit | Hai nguồn hoàn tất rỗng | `Mono.when` nếu chỉ cần completion |
| Pipeline fail nhưng đã có document | Lỗi không rollback các write independent | Partial outcome/idempotency/transaction khi cần |
| Hủy subscription tưởng như rollback | MongoDB có thể đã xử lý write in-flight | Outcome UNKNOWN và đối soát |
| Retry khi timeout tạo thêm document | Sinh ID mới mỗi attempt | Stable ID + request fingerprint |
| Retry `$inc` làm thay đổi hai lần | Operation không idempotent | Reservation/ledger/guard trước retry |
| N = 8 nhưng DB vẫn có 500 write cùng lúc | 8 là giới hạn từng pipeline, nhiều requests/instances | Global admission/consumer concurrency |
| `onBackpressureBuffer()` ăn hết RAM | Buffer không giới hạn | Bounded queue/overflow policy |
| `limitRate` không làm MongoDB hết nghẽn | Demand shaping không phải database capacity | Concurrency + load/queue control |
| `parallel()` không tăng throughput Mongo | Reactive I/O không cần CPU parallel | Đo DB/pool, dùng flatMap bounded |
| `flatMap(...,8)` trong transaction lỗi session | Driver không hỗ trợ parallel operations trong một transaction | `concatMap`/`then` trong transaction |
| Outer reactive transaction + inner flatMap nhiều transaction sai | Các inner tham gia shared outer session | Không dùng outer; propagation/session rõ |
| Bulk `UNORDERED` có partial data | Unordered không atomic | Báo outcome/item, retry có kiểm soát |
| Bulk không gọi đủ entity callbacks | Bulk có semantics lifecycle khác repository | Xem tài liệu API phiên bản đang dùng |
| `groupBy` stream vô hạn treo khi quá nhiều key | High cardinality + low group concurrency | Partition hữu hạn/queue theo key |
| Client ngắt kết nối rồi write không chắc | Cancellation ≠ guaranteed undo | Idempotency và đối soát |
| Integration test dùng standalone và tx lỗi | Transaction cần replica set/sharded | Dùng test replica set |
| Unit test pass nhưng DB write sai | Mock không có constraint/transaction thực | Integration test với MongoDB thật |

## 23. Checklist thiết kế một pipeline ghi reactive

1. **Xác định loại write:** độc lập, theo key có thứ tự hay cùng transaction.
2. **Chọn operator theo semantics**, không theo cảm giác “flatMap nhanh hơn”.
3. **Dùng `concatMap` cho dependency/ordering**, nhất là trong transaction.
4. **Dùng `flatMap(..., N)`** cho write độc lập có concurrency hữu hạn.
5. **Chỉ dùng `flatMapSequential` khi muốn output theo source order**, không để bảo đảm order ở database.
6. **Không chạy các operation song song trong một MongoDB transaction**.
7. **Cho phép nhiều transaction riêng** chạy đồng thời chỉ khi không bị outer context chia sẻ session.
8. **Giữ ID/idempotency key ổn định** trước mọi retry.
9. **Phân loại duplicate, conflict, unknown outcome và lỗi hệ thống**.
10. **Không tự `subscribe()`/`block()` trong WebFlux service**.
11. **Đặt giới hạn toàn instance và ingress**, không chỉ concurrency cho một Flux.
12. **Xem batch/bulk khi lượng document lớn**, giới hạn batch size/active batches.
13. **Không hiểu batch/unordered là atomicity**; cân nhắc partial success.
14. **Đặt chính sách backpressure/queue hữu hạn**, không buffer vô hạn trong heap.
15. **Chọn write concern/timeout theo nghiệp vụ**, nhớ timeout/cancel không tự undo server write.
16. **Ràng buộc tenant và state/version trong query**, không dùng ordering cục bộ như khóa phân tán.
17. **Đo pool wait, p95/p99, retry và backlog** trước khi tăng N.
18. **Dùng StepVerifier để kiểm thứ tự/concurrency/error behavior**.
19. **Test MongoDB thật để kiểm unique index, partial success và transaction rollback**.
20. **Review logic khi client disconnect hoặc consumer rebalance**, giữ khả năng đối soát.

## 24. Bài thực hành và đáp án

### Bài 1 — Chọn operator cho 20 insert độc lập

Có 20 `WriteCommand` khác `_id`, có thể ghi độc lập. Muốn tối đa bốn operation in-flight, không quan tâm thứ tự kết quả.

**Đáp án:**

~~~java
Flux<WriteJob> written = Flux.fromIterable(commands)
    .flatMap(c -> repository.insert(toDocument(c)), 4);
~~~

### Bài 2 — Cần kết quả theo thứ tự đầu vào

Vẫn 20 insert độc lập, nhưng report phải giữ đúng thứ tự command.

**Đáp án:** Dùng `flatMapSequential(mapper,4)`. Nó giữ thứ tự **emission**, không tuần tự hóa database writes.

### Bài 3 — Hai update cùng một order

Update A chuyển PENDING → APPROVED, update B chuyển APPROVED → SHIPPED. Có thể dùng `flatMapSequential` để bảo đảm A được DB xử lý trước B không?

**Đáp án:** Không. Dùng `concatMap` theo order hoặc `A.then(B)` và kiểm expected state trong update predicate. `flatMapSequential` chỉ sắp xếp kết quả trả về.

### Bài 4 — Hai write một transaction

Order update và outbox insert cần commit/abort cùng nhau. Dùng `Mono.when` có ổn không?

**Đáp án:** Không. Trong cùng MongoDB transaction, driver không hỗ trợ parallel writes; dùng `update.then(insert).as(tx::transactional)` để tuần tự.

### Bài 5 — Nhiều transaction độc lập

Có 50 order độc lập, mỗi order có hai write tuần tự trong một transaction riêng. Có thể chạy bốn order cùng lúc?

**Đáp án:** Có, nếu không có outer transaction và mỗi inner flow thực sự tạo session/transaction riêng:

~~~java
Flux.fromIterable(orderCommands)
    .flatMap(cmd -> processOneOrderAtomically(cmd), 4)
    .then();
~~~

### Bài 6 — Outer transaction

Nếu method ngoài cũng dùng reactive `@Transactional` rồi gọi `flatMap(cmd -> processOneOrderAtomically(cmd),4)`, chuyện gì có thể xảy ra?

**Đáp án:** Inner có thể tham gia **cùng outer transaction** theo REQUIRED, dẫn tới concurrent writes trong một shared session — không được driver hỗ trợ. Xác định propagation/session scope đúng.

### Bài 7 — `zip` với `Mono<Void>`

Muốn biết hai write không trả dữ liệu đã complete, nên dùng `Mono.zip(monoVoidA,monoVoidB)` hay `Mono.when`?

**Đáp án:** `Mono.when`. `zip` cần mỗi source phát value; `Mono<Void>` chỉ complete và không phát value, dẫn tới kết quả không như mong đợi.

### Bài 8 — Partial failure

`flatMap(insert,8)` nhận duplicate key ở một item. Các item khác có thể đã được insert?

**Đáp án:** Có. Fail-fast/cancel không rollback những write độc lập đã được MongoDB xử lý. Cần báo cáo kết quả/đối soát và idempotency, hoặc transaction nếu hợp đồng yêu cầu atomicity.

### Bài 9 — `onErrorResume` ở cuối

Vì sao `flux.flatMap(write,8).onErrorResume(e -> Flux.empty())` có thể nguy hiểm?

**Đáp án:** Nó che lỗi, không có thông tin item nào thành công/thất bại và có thể làm API trả completion dù DB đã có partial writes. Dùng handler được phân loại **theo từng item** hoặc báo job failed/unknown rõ.

### Bài 10 — Retry với ID mới

Lần insert đầu bị socket timeout, lần retry tạo UUID khác. Nguy cơ?

**Đáp án:** Lần đầu có thể đã ghi; lần hai tạo document thứ hai. Giữ ID nghiệp vụ ổn định và đối soát.

### Bài 11 — `$inc`

Một phép trừ hàng tồn dùng `$inc:-1` bị timeout. Có nên retry như operation mới ngay?

**Đáp án:** Không mặc định. Lần đầu có thể đã áp; cần reservation/ledger ID, state guard hoặc transaction đúng semantics trước retry.

### Bài 12 — Lựa chọn batch

Có 100.000 document cùng collection, mỗi document nhỏ. Chọn một `flatMap(insert,1024)` hay `buffer(200)` + bulk với active batches hữu hạn?

**Đáp án:** Nên thử **batch/bulk bounded** và đo hiệu quả. Concurrency 1024 không có cơ sở có thể làm pool saturation, RAM và p99 tăng. Không bảo đảm bulk luôn nhanh hơn: benchmark dữ liệu thật.

### Bài 13 — `UNORDERED`

Bulk unordered gặp duplicate key ở một document. Có phải tất cả document được rollback?

**Đáp án:** Không. Một số operation có thể đã thành công; unordered không phải multi-document transaction.

### Bài 14 — `groupBy` theo key

Vì sao `source.groupBy(orderId).flatMap(g -> g.concatMap(write),8)` có thể không phù hợp với hàng triệu key trên stream vô hạn?

**Đáp án:** Nhiều nhóm tiêu tốn tài nguyên/buffer; nhóm chưa được consume có thể gây backpressure/đình trệ khi outer concurrency thấp. Dùng partition hữu hạn hoặc queue có khả năng kiểm soát cardinality.

### Bài 15 — Backpressure

`limitRate(64)` có đảm bảo chỉ có 64 MongoDB writes active toàn hệ thống không?

**Đáp án:** Không. Nó điều chỉnh request demand upstream; concurrency thực cần `flatMap(...,N)`/ingress control, và toàn hệ thống còn nhiều pipelines/instances.

### Bài 16 — `parallel()`

ReactiveMongoRepository đã trả `Mono` non-blocking. Có cần `parallel().runOn(Schedulers.parallel())` để “thực sự chạy đồng thời” không?

**Đáp án:** Không. `flatMap` với concurrency hữu hạn có thể có nhiều I/O in-flight mà không yêu cầu CPU parallel scheduler. Đo bottleneck trước khi thêm scheduler.

### Bài 17 — Cancellation

Client gửi 200 command, ngắt HTTP sau 100 result. Có chắc 100 command còn lại không được ghi?

**Đáp án:** Không. Một số writes đang in-flight có thể đã tới server và tiếp tục commit/replicate. Hợp đồng API phải có job ID/đối soát trạng thái.

### Bài 18 — Test concurrency

Test `StepVerifier` thấy 12 item được phát, có chứng minh N không vượt 3 không?

**Đáp án:** Chưa. Cần đo active inner subscriptions bằng `AtomicInteger` trong test, hoặc dùng metric phù hợp; riêng kết quả 12 item không nói gì về peak concurrency.

### Bài 19 — Test transaction

Muốn chứng minh order update và outbox insert rollback cùng nhau khi outbox trùng `_id`, test cần làm gì?

**Đáp án:** Dùng MongoDB **replica set test**, tạo outbox conflict trước, subscribe service transactional, chờ lỗi rồi **đọc lại order** xác nhận vẫn PENDING và outbox preexisting không đổi.

### Bài 20 — Chọn N=8

Một pod có 40 concurrent HTTP requests, mỗi request `flatMap(write,8)`. Có thể có bao nhiêu inner write active tại pod?

**Đáp án:** Xấp xỉ **320** nếu tất cả request đều có đủ item và không có admission control chung. Đây không phải 320 sockets chắc chắn, nhưng thể hiện vì sao N là giới hạn theo pipeline chứ không phải cluster-wide cap.

## Tài liệu tham khảo

- [Project Reactor — Which Operator Do I Need?](https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html): chọn `flatMap`, `concatMap`, `flatMapSequential`, `then`, `when`, `zip`, `collectList`.
- [Project Reactor — `Flux` API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): overload `flatMap(mapper, concurrency)`, `flatMapSequential`, `concatMap`, `groupBy`, `bufferTimeout` và backpressure behavior.
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `onErrorResume`, `retryWhen`, `onErrorContinue` và propagation.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, virtual time, Publisher behavior.
- [Spring Data MongoDB — Reactive MongoDB Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/reactive-mongodb.html): reactive repositories/template, I/O và Publisher composition.
- [Spring Data MongoDB — Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): reactive inserts, batch, `bulkOps`/`bulkWrite`, mapping và lifecycle differences.
- [Spring Data MongoDB — Client Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): `ReactiveMongoTransactionManager`, `TransactionalOperator`, session/transaction context.
- [Spring Data MongoDB — `ReactiveMongoTemplate` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveMongoTemplate.html): `insert`, `updateFirst`, `bulkOps` và reactive transaction operations.
- [MongoDB Java Reactive Streams Driver — Transactions](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/crud/transactions/): **parallel operations are not supported within one transaction**, session và commit semantics.
- [MongoDB Java Reactive Streams Driver — Write Data](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/write/): insert/update/bulk APIs và Publisher contract.
- [MongoDB Manual — Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/): ordered/unordered semantics và partial completion.
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/): atomicity, isolation và operational constraints.
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/): retryable-write behavior và topology.
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): acknowledgment, majority/journal, timeout và unknown outcome.
- [MongoDB Manual — Connection Pool Options](https://www.mongodb.com/docs/drivers/java/reactive-streams/current/connection/specify-connection-options/connection-pools/): pool capacity, max wait time và latency dưới tải.
