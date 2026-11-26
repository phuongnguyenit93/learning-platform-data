# Thao tác nhiều tài liệu với giới hạn đồng thời

Khi xây dựng tầng truy cập **Spring Data Couchbase**, Repository và `CouchbaseTemplate` thuận tiện cho CRUD entity, mapping document và truy vấn SQL++. Tuy nhiên, có những tác vụ cần **đọc hàng trăm document theo danh sách key**, **nhập dữ liệu nhiều nghìn hồ sơ** hoặc **cập nhật hàng loạt những document độc lập**. Vòng lặp gọi `collection.get(...)` hay `upsert(...)` tuần tự dễ hiểu nhưng có thể bị chi phối bởi tổng thời gian chờ network. Ngược lại, khởi tạo hàng chục nghìn thao tác bất đồng bộ cùng lúc lại có thể làm client, node dữ liệu và bộ nhớ quá tải.

Couchbase Java SDK cung cấp ba mặt API — blocking, `CompletableFuture` qua `async()` và Project Reactor qua `reactive()`. Để kiểm soát số thao tác đang chờ hoàn tất (**in-flight operations**), ta thường phối hợp `Flux` với `flatMap(..., concurrency)` hoặc `flatMapSequential(..., concurrency)`. Đây là **chiến lược điều phối phía ứng dụng**, không phải một “bulk transaction” của Couchbase.

> **Điểm cốt lõi:** Giới hạn đồng thời giúp cân bằng throughput, latency và tài nguyên. Nó **không** bảo đảm các document cùng commit/rollback, các lần ghi lên cùng key đúng thứ tự, retry không bị lặp, hoặc kết quả luôn xuất hiện theo thứ tự input.

Bài thuộc chương **Mở rộng bằng SDK** của module **SPRING_DATA_COUCHBASE**: xây dựng tầng truy cập Couchbase với document mapping, Repository, `CouchbaseTemplate`, SQL++, thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và lựa chọn reactive API cho hiệu năng, tính nhất quán và vận hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt thao tác tuần tự, gọi đồng thời vô giới hạn, **bounded concurrency** và transaction nhiều document.
2. Lấy `ReactiveCollection`/`AsyncCollection` từ `Collection` được Spring quản lý.
3. Giới hạn số KV operations in-flight bằng `Flux.flatMap(mapper, maxConcurrency)`.
4. Chọn `flatMap`, `flatMapSequential` hoặc `concatMap` theo thứ tự **kết quả** và **thứ tự side effect**.
5. Biểu diễn kết quả riêng từng key; phân biệt `FOUND`, `NOT_FOUND`, `APPLIED`, `CONFLICT`, `FAILED` và `UNKNOWN`.
6. Chặn việc mất lỗi khi dùng `onErrorResume`, `collectList` và `retry` không đúng chỗ.
7. Hiểu `AmbiguousTimeoutException`, `DocumentExistsException`, `CasMismatchException` và xử lý idempotency.
8. Dùng CAS/`@Version` và sub-document operations theo đúng phạm vi nguyên tử của một document.
9. Tính ngân sách concurrency **theo batch, HTTP request, pod và toàn hệ thống**.
10. Dùng chunking, streaming, checkpoint và backpressure khi input quá lớn.
11. So sánh bounded KV fan-out với SQL++ DML, Repository bulk methods và Couchbase transactions.
12. Xây dựng kiểm thử concurrency, lỗi từng phần, replay, bảo mật tenant và benchmark có ý nghĩa.

## 2. Bài toán: nhập và tra cứu hồ sơ khách hàng

Giả sử dữ liệu ở:

~~~text
Bucket     shop
Scope      crm
Collection customers

customer::tenant-01::1001
customer::tenant-01::1002
customer::tenant-01::1003
...
~~~

Document mẫu:

~~~json
{
  "tenantId": "tenant-01",
  "display_name": "Minh",
  "segment": "STANDARD",
  "emailVerified": true,
  "updatedAt": "2026-11-24T08:30:00Z"
}
~~~

Có ba use case:

- Màn hình quản trị nhận 100 IDs, trả các hồ sơ tìm được, chỉ ra ID không tồn tại.
- Job đồng bộ tạo 50.000 Customers mới. Mỗi key có thể thành công, đã tồn tại hoặc chưa rõ kết quả sau timeout.
- Job thay đổi `segment` của hàng nghìn Customers nhưng phải tránh ghi đè sửa đổi của user khác.

**Hợp đồng thành công khác nhau**:

| Tác vụ | Đơn vị thành công | Có phải tất cả-or-không? | Thứ tự |
| --- | --- | --- | --- |
| Bulk GET | Một document key | Không nhất thiết | Có thể cần theo input |
| Bulk INSERT | Một document key | Không nếu best-effort import | Thường không cần |
| CAS REPLACE | Một document key với expected CAS | Không cho các key khác nhau | Quan trọng nếu trùng key |
| Một command cập nhật ba document gắn cùng invariant | Cả tập document | **Có**, nếu nghiệp vụ yêu cầu | Transaction context |
| Replay event trên cùng key | Chuỗi trạng thái của key | Tùy hợp đồng | **Rất quan trọng** |

Đừng chọn concurrency trước khi xác định câu hỏi: **“Nếu 20 item đã ghi, item thứ 21 lỗi thì hệ thống phải làm gì?”**

## 3. Đọc tuần tự và giới hạn network latency

Code blocking:

~~~java
List<JsonObject> data = new ArrayList<>();

for (String id : ids) {
    GetResult result = customers.get(id);
    data.add(result.contentAsObject());
}
~~~

Nếu mỗi call phải đợi mạng/server, các calls sau chỉ bắt đầu khi call trước hoàn tất:

~~~text
get(A): [send------wait------receive]
get(B):                          [send------wait------receive]
get(C):                                                    [send------wait------receive]
~~~

Reactive fan-out cho phép chồng thời gian đợi:

~~~text
get(A): [send------wait------receive]
get(B): [send---------wait---------receive]
get(C): [send--wait--receive]
get(D):       [send------wait------receive]
~~~

Nhưng **không phải mọi ứng dụng đều cần reactive**: đọc vài keys trong một batch nhỏ bằng blocking code có thể dễ hiểu và đủ nhanh. Hãy đo workload thật; áp dụng bounded concurrency khi latency hoặc throughput tạo ra lợi ích đáng kể.

## 4. Ba mặt API của Couchbase Java SDK

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.AsyncCollection;
import com.couchbase.client.java.ReactiveCollection;

Collection customers = cluster.bucket("shop")
        .scope("crm")
        .collection("customers");

AsyncCollection async = customers.async();
ReactiveCollection reactive = customers.reactive();
~~~

| API | Kết quả của GET | Thế mạnh |
| --- | --- | --- |
| `customers.get(id)` | `GetResult`, blocking | Đơn giản, call ít |
| `customers.async().get(id)` | `CompletableFuture<GetResult>` | Phối hợp với Java futures |
| `customers.reactive().get(id)` | `Mono<GetResult>` | Stream, operator, error/retry và backpressure |

Ba mặt API dùng **cùng hạ tầng SDK**; không tạo một Cluster độc lập cho mỗi call.

Couchbase Java SDK không cung cấp một **bulk API tổng quát** tự động gom mọi operation thành một atomic request. Tài liệu SDK hướng dẫn tận dụng asynchronous/reactive primitives để ghép các calls theo yêu cầu riêng. <https://docs.couchbase.com/java-sdk/current/howtos/concurrent-async-apis.html>

## 5. Lấy `Cluster`/`Collection` do Spring quản lý

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import org.springframework.stereotype.Component;

@Component
public final class CustomerBatchSdkAdapter {

    private final Collection customers;

    public CustomerBatchSdkAdapter(Cluster cluster) {
        this.customers = cluster.bucket("shop")
                .scope("crm")
                .collection("customers");
    }
}
~~~

Trong production, bucket/scope/collection nên lấy từ **trusted configuration** và thống nhất với mapping entity (ví dụ `@Scope("crm")`, `@Collection("customers")`).

Không gọi `Cluster.connect(...)` trong từng batch, không gọi `cluster.disconnect()` khi batch kết thúc. Spring sở hữu lifecycle của Cluster bean dùng chung với Repository/Template. Nếu có nhiều clusters có chủ đích, dùng `@Qualifier` và định tuyến rõ ràng.

Đừng để tên collection do user nhập trực tiếp điều khiển SDK. Có cùng Cluster không chứng minh đã chọn đúng keyspace.

## 6. `flatMap(mapper, concurrency)` giới hạn điều gì?

~~~java
ReactiveCollection reactive = customers.reactive();

Flux<GetResult> results =
        Flux.fromIterable(ids)
                .flatMap(id -> reactive.get(id), 16);
~~~

Ở mức operator này, Reactor giới hạn tối đa **16 inner publishers được subscribe đồng thời**. Với mỗi inner là một `Mono` đại diện một GET, đó thường tương ứng tối đa 16 KV operations đang chờ kết quả tại đoạn pipeline này.

Không suy ra:

- Cluster chỉ có tối đa 16 requests từ mọi user.
- Server tự dùng 16 threads riêng cho batch.
- Có một transaction chứa 16 documents.
- Kết quả phát theo thứ tự input.
- Lệnh GET chắc chắn hoàn tất trong budget.
- Nhiều HTTP requests dùng chung giới hạn 16.

**Con số 16 là giá trị minh họa**, không phải tiêu chuẩn bất biến. Chọn bằng benchmark trên deployment, payload, latency, durability và số batch đồng thời.

## 7. Vì sao `flatMap` không giới hạn tường minh là một thiếu sót?

~~~java
Flux.fromIterable(ids)
        .flatMap(reactive::get)
        .collectList();
~~~

Ví dụ ngắn nhưng thiếu chính sách:

1. Dùng concurrency mặc định của Reactor, không phải thông số đã chọn theo khả năng hệ thống.
2. Nếu một GET lỗi, `Flux` có thể phát `onError` và kết thúc stream.
3. `collectList()` giữ mọi result trong heap.
4. Kết quả về theo thứ tự hoàn thành, không theo input.
5. Không có trạng thái riêng cho các keys không tồn tại.
6. Nếu đem cấu trúc đó sang write, nó không có rollback hoặc idempotency.

Nên luôn xác định **input cap, explicit concurrency, outcome policy, memory cap, retry policy và tổng tải**.

## 8. Mô hình input/output giữ cả document key

~~~java
public record LookupRequest(
        int position,
        String documentId) {}

public enum LookupStatus {
    FOUND, NOT_FOUND, FAILED
}

public record LookupOutcome(
        int position,
        String documentId,
        LookupStatus status,
        JsonObject body,
        String errorCategory) {}
~~~

`position` giúp khôi phục thứ tự input nếu cần. `documentId` cho phép đối soát một kết quả hoặc lỗi với key đã yêu cầu. `status` tránh nhầm **không tồn tại** với **SDK không đọc được**.

Không trả raw `error.message`, `ErrorContext` hoặc document body chứa PII ra public API nếu không có quyền. Dùng mã lỗi ở mức ứng dụng và log chi tiết đã redaction theo chính sách.

## 9. Bulk GET có bounded concurrency và per-key outcomes

~~~java
import com.couchbase.client.core.error.CouchbaseException;
import com.couchbase.client.core.error.DocumentNotFoundException;
import com.couchbase.client.java.Collection;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public Flux<LookupOutcome> readMany(
        Collection customers,
        Flux<LookupRequest> input) {

    return input.flatMap(request ->
            customers.reactive()
                    .get(request.documentId())
                    .map(result -> new LookupOutcome(
                            request.position(),
                            request.documentId(),
                            LookupStatus.FOUND,
                            result.contentAsObject(),
                            null))
                    .onErrorResume(
                            DocumentNotFoundException.class,
                            error -> Mono.just(new LookupOutcome(
                                    request.position(),
                                    request.documentId(),
                                    LookupStatus.NOT_FOUND,
                                    null,
                                    "DOCUMENT_NOT_FOUND")))
                    .onErrorResume(
                            CouchbaseException.class,
                            error -> Mono.just(new LookupOutcome(
                                    request.position(),
                                    request.documentId(),
                                    LookupStatus.FAILED,
                                    null,
                                    error.getClass().getSimpleName()))),
            16);
}
~~~

Giải thích:

- `readMany` chưa subscribe; Flux được thực thi khi caller **subscribe**, giúp gắn lifecycle với request/job.
- `DocumentNotFoundException` trở thành `NOT_FOUND` nếu contract cho phép partial.
- Những `CouchbaseException` khác trở thành `FAILED`, không giả làm 404.
- Lỗi bug/mapping ngoài nhóm đã xử lý vẫn có thể terminate stream — đúng hướng fail-fast với lỗi không được dự kiến.
- `flatMap` có thể phát kết quả **đảo thứ tự**.
- Body JSON từ SDK không tự qua `CouchbaseConverter` của Spring Data.
- Vẫn phải thực thi authorization tenant trước khi trả dữ liệu.

Nếu app yêu cầu **fail closed khi sai RBAC**, nên điều chỉnh nhánh lỗi để exception quyền không được đổi thành một “failed item” có thể bị caller bỏ qua. Policy phải rõ cho từng use case.

## 10. Đừng nuốt lỗi bằng `Mono.empty()` không kiểm soát

~~~java
Flux<JsonObject> bodies =
        Flux.fromIterable(ids)
                .flatMap(id -> customers.reactive()
                        .get(id)
                        .map(r -> r.contentAsObject())
                        .onErrorResume(e -> Mono.empty()),
                        16);
~~~

Nếu 100 GET có 8 failures, pipeline có thể chỉ phát 92 bodies. Nếu caller không có per-key outcomes, 8 keys biến mất mà không được giải thích.

Điều này có thể chấp nhận với một best-effort widget chỉ cần “những item còn đọc được”, nhưng **không** phù hợp cho:

- Báo cáo nhập liệu cần audit.
- Xóa dữ liệu theo yêu cầu người dùng.
- Cập nhật giá/tồn kho/quyền.
- Job phải replay chính xác failed items.
- API trả theo vị trí đầu vào.

Hãy dùng per-key outcome hoặc fail-fast một cách **có chủ đích**, không coi stream không ném lỗi là “cả batch thành công”.

## 11. Thứ tự output: `flatMap`, `flatMapSequential`, `concatMap`

Input:

~~~text
[A, B, C, D]
~~~

Do các GET có độ trễ khác nhau, `flatMap` có thể phát:

~~~text
[C, A, D, B]
~~~

| Operator | IO đồng thời | Thứ tự output | Cái giá |
| --- | --- | --- | --- |
| `flatMap(fn, N)` | N inner publishers | Không bảo đảm | Thông lượng tốt khi không cần order |
| `flatMapSequential(fn, N)` | N inner publishers | Theo input | Buffer output đã xong để đợi item trước |
| `concatMap(fn)` | Một inner publisher mỗi lần | Theo input | Ít song song, có thể chậm hơn |

Ví dụ:

~~~java
Flux<LookupOutcome> ordered = input.flatMapSequential(
        request -> getOneOutcome(customers, request),
        16);
~~~

`getOneOutcome` là helper **ứng dụng minh họa** trả `Mono<LookupOutcome>` và có phân loại lỗi giống mục trước.

Nếu không cần thứ tự, `flatMap` thường đơn giản hơn. Nếu cần output theo input nhưng tốc độ vẫn quan trọng, `flatMapSequential` hợp lý nhưng phải tránh response/buffer quá lớn khi item đầu chậm.

## 12. Thứ tự output không phải thứ tự side effects

Hai changes trên cùng key:

~~~java
Flux.fromIterable(List.of(
        new Change("customer::42", "STANDARD"),
        new Change("customer::42", "VIP")))
    .flatMapSequential(change -> updateReactive(change), 2);
~~~

`flatMapSequential` **không hứa** server ghi STANDARD trước VIP; nó chỉ phát outcomes theo thứ tự input sau khi các inner operations hoàn thành.

Nếu domain cần event order trên cùng key:

1. `concatMap` xử lý tuần tự các mutation trong batch khi số phần tử ít.
2. Dùng keyed queue/partition để chỉ một writer đang xử lý một key tại một thời điểm.
3. Sử dụng event sequence và CAS để từ chối bản cũ.
4. Dùng durable event log partition theo key khi yêu cầu restart/replay.
5. Nếu invariant gồm nhiều keys, xem transaction.

Đừng mở `groupBy(key)` cho vô số key mà không giới hạn cardinality; Reactor cảnh báo có tình huống backpressure/buffering treo khi số groups cao và downstream concurrency thấp.

## 13. Duplicate input keys: read và write có ngữ nghĩa khác

Ví dụ:

~~~text
Input IDs: [customer::42, customer::99, customer::42]
~~~

Với bulk GET, có thể giữ ba outcomes theo ba input positions, hoặc deduplicate hai KV gets rồi phân phối kết quả về ba positions.

Với bulk mutations:

- Hai `upsert` cùng key có thể ghi đè nhau.
- Hai `insert` cùng key có thể tạo `DocumentExistsException`.
- Hai `increment` cùng key có thể tăng **hai lần**.
- Hai `replace` dùng expected CAS giống nhau có thể gây conflict.
- Hai events khác nhau trên cùng key có thể phải xử lý **cả hai**, không phải chỉ một.

**Không gọi `distinct()` cho stream writes chỉ vì muốn giảm tải.** Deduplicate logical commands theo `eventId`/idempotency policy, không chỉ theo document key.

## 14. Giới hạn input bên cạnh concurrency

Một endpoint:

~~~http
POST /customers/bulk-get
Content-Type: application/json

{"ids": ["customer::1001", "customer::1002"]}
~~~

Cần giới hạn:

- Số IDs mỗi request và tổng request body.
- Độ dài key/byte UTF-8, định dạng tenant và duplicates.
- Kích thước response, đặc biệt body JSON lớn.
- Số HTTP bulk requests đồng thời.
- Tổng operation in-flight trên mỗi pod.
- Rate theo tenant/service account.
- Timeout/deadline cả per-item và toàn batch.
- Lỗi/partial outcomes phải được công bố rõ.
- Không nhận trực tiếp bucket/scope/collection từ user nếu không có allowlist.

Ví dụ một giới hạn **chính sách ứng dụng**:

~~~java
public static void validateBatch(List<String> ids) {
    if (ids == null || ids.isEmpty() || ids.size() > 200) {
        throw new IllegalArgumentException(
                "Batch size must be 1..200");
    }

    for (String id : ids) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("Invalid ID");
        }
    }
}
~~~

Không suy ra đây là giới hạn tối đa Couchbase Server; dự án phải kiểm tra document-key constraints và schema thật theo version.

## 15. `collectList()` hợp lý khi batch đã bounded

~~~java
Mono<List<LookupOutcome>> smallBatch =
        readMany(customers, Flux.fromIterable(requests))
                .collectList();
~~~

Nếu API đã validate tối đa 200 keys, memory cap rõ ràng và body không quá lớn, `collectList` có thể phù hợp.

Ngược lại:

~~~java
// Không nên gom hàng triệu JSON bodies vào một danh sách.
Mono<List<LookupOutcome>> all =
        readMany(customers, millionsOfRequests)
                .collectList();
~~~

Giới hạn `flatMap(...,16)` khống chế số IO đang chạy, **không** khống chế kích thước list tích lũy khi tất cả hoàn thành.

Với job lớn, ưu tiên stream/chunk, tổng kết bằng `reduce` hoặc ghi outcomes/checkpoints bền vững theo từng lô.

## 16. Bulk INSERT: lưu trạng thái riêng mỗi key

Dùng `insert` khi nghiệp vụ **không được ghi đè key đã có**.

~~~java
public record InsertRequest(
        String documentId,
        JsonObject body) {}

public enum WriteStatus {
    APPLIED, ALREADY_EXISTS, FAILED, UNKNOWN
}

public record WriteOutcome(
        String documentId,
        WriteStatus status,
        Long cas,
        String errorCategory) {}
~~~

Ví dụ:

~~~java
import com.couchbase.client.core.error.AmbiguousTimeoutException;
import com.couchbase.client.core.error.CouchbaseException;
import com.couchbase.client.core.error.DocumentExistsException;
import com.couchbase.client.java.Collection;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public Flux<WriteOutcome> insertMany(
        Collection customers,
        Flux<InsertRequest> input) {

    return input.flatMap(request ->
            customers.reactive()
                    .insert(request.documentId(), request.body())
                    .map(result -> new WriteOutcome(
                            request.documentId(),
                            WriteStatus.APPLIED,
                            result.cas(),
                            null))
                    .onErrorResume(
                            DocumentExistsException.class,
                            ex -> Mono.just(new WriteOutcome(
                                    request.documentId(),
                                    WriteStatus.ALREADY_EXISTS,
                                    null,
                                    "DOCUMENT_EXISTS")))
                    .onErrorResume(
                            AmbiguousTimeoutException.class,
                            ex -> Mono.just(new WriteOutcome(
                                    request.documentId(),
                                    WriteStatus.UNKNOWN,
                                    null,
                                    "AMBIGUOUS_TIMEOUT")))
                    .onErrorResume(
                            CouchbaseException.class,
                            ex -> Mono.just(new WriteOutcome(
                                    request.documentId(),
                                    WriteStatus.FAILED,
                                    null,
                                    ex.getClass().getSimpleName()))),
            16);
}
~~~

`APPLIED` nghĩa là client nhận xác nhận thành công. `ALREADY_EXISTS` nghĩa key đã có — **không chứng minh** đó là dữ liệu của cùng business event. `UNKNOWN` giữ trạng thái chưa rõ nếu server có thể đã áp dụng mutation. Lỗi cấu hình/phân quyền cần chính sách dừng hoặc báo nghiêm trọng, không bị bỏ qua chỉ vì pipeline hoàn thành.

**Cách bắt exception rộng ở cuối là lựa chọn để lưu per-key status**, không phải một fallback mặc định cho tất cả nghiệp vụ. Caller phải kiểm tra outcomes và có phương án xử lý từng loại lỗi.

## 17. Vì sao `upsert` không phải giải pháp conflict mặc định?

~~~java
Mono<MutationResult> result =
        customers.reactive().upsert(documentId, fullBody);
~~~

`upsert` tạo mới hoặc thay thế body của key. Nhưng trong batch:

- Dữ liệu input có thể cũ hơn document đang lưu.
- Một writer khác có thể cập nhật giữa các lần retry.
- `upsert` raw không tự dùng Spring Data `@Version` hoặc auditing.
- Thay document bằng body thiếu field có thể làm mất thông tin.
- TTL/expiry/durability của SDK operation có thể khác Repository.
- Duplicate command có thể ghi lại desired state sau khi writer khác sửa đổi.

Khi business cho phép overwrite theo trạng thái đích có versioning rõ, `upsert` có thể đúng. Khi cần bảo vệ cập nhật của writer khác, dùng `replace` kèm CAS/logic merge hoặc transaction tùy invariant.

Đừng gọi mọi `upsert` là “idempotent” trong mọi môi trường có concurrent writers chỉ vì cùng body được gửi hai lần.

## 18. `replace` kèm CAS cho một document

~~~java
public record ReplaceRequest(
        String documentId,
        JsonObject newFullBody,
        long expectedCas) {}
~~~

Mutation:

~~~java
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;

Mono<MutationResult> replaceOne(
        Collection customers,
        ReplaceRequest change) {

    return customers.reactive().replace(
            change.documentId(),
            change.newFullBody(),
            replaceOptions().cas(change.expectedCas()));
}
~~~

Nếu document đã bị writer khác cập nhật, expected CAS cũ sẽ bị từ chối với `CasMismatchException` thay vì âm thầm ghi đè.

Trong batch, hãy phân loại conflict riêng và xử lý:

1. Đọc lại document từ active.
2. Xem version và invariant của nghiệp vụ.
3. Merge hoặc từ chối theo chính sách, không ghi đè bừa.
4. Nếu còn phù hợp, replace lại với **CAS mới**.
5. Giới hạn retry và ghi log conflict/reconciliation.

Một CAS check chỉ bảo vệ **một document**. Nó không làm mọi `replace` trong batch cùng thành công hoặc cùng rollback.

## 19. Sub-document mutation vẫn nguyên tử theo từng document

Nếu chỉ muốn đổi JSON field `segment`:

~~~java
import com.couchbase.client.java.kv.MutateInResult;
import com.couchbase.client.java.kv.MutateInSpec;
import java.util.List;

Mono<MutateInResult> mutation =
        customers.reactive().mutateIn(
                documentId,
                List.of(MutateInSpec.replace(
                        "segment", "LOYAL")));
~~~

`mutateIn` dùng JSON path thật, phù hợp khi không muốn thay toàn body. Một lệnh `mutateIn` có thể bao gồm nhiều specs và giữ atomicity trên **một document**.

Nếu chạy `mutateIn` cho A, B, C trong một Flux:

~~~text
A -> success
B -> error
C -> success
~~~

A, C **không tự rollback** khi B lỗi. SDK raw mutation cũng không tự chạy Spring Data converter/auditing, và phải khớp field mapping thật (`@Field`).

## 20. Batch KV khác transaction nhiều document

| Thuộc tính | Fan-out KV reactive | Transaction |
| --- | --- | --- |
| Đơn vị nguyên tử | Mỗi KV operation/document | Nhiều operations theo transaction context |
| Nhiều documents cùng commit/rollback | **Không** | Theo semantics transaction |
| Failure ở item thứ 5 | Các item trước có thể đã ghi | Có protocol rollback/commit |
| CAS riêng từng item | Có thể | Theo transaction integration |
| Timeout/commit ambiguity | Có thể xảy ra | Có semantics/error contract riêng |
| Mức overhead | Thường thấp hơn | Tốn thêm coordination |
| Phù hợp | Import, batch read, best-effort independent updates | Chuyển tiền, tồn kho và order cùng invariant |

Một quy trình:

~~~text
1. Trừ tồn kho document A
2. Tạo Order document B
3. Ghi Payment record document C
~~~

Nếu cần “ba thay đổi cùng có hoặc cùng không”, **không** viết ba `Mono` độc lập rồi chạy `flatMap`. Dùng Couchbase Transactions/Spring integration theo phiên bản, có transaction context nhất quán.

## 21. Fail-fast không rollback những writes đã phát

~~~java
Flux.fromIterable(changes)
        .flatMap(change -> applyWrite(change), 16);
~~~

Nếu một inner operation phát `onError` mà không được phục hồi, Flux có thể cancel những inner khác. Nhưng:

- Những writes đã thành công vẫn thành công.
- Những requests đã gửi có thể tiếp tục xử lý.
- Một số outcomes chưa rõ khi client cancel.
- Không có rollback cho cả batch.

**Fail-fast là hành vi điều khiển stream**, không phải cơ chế transaction. Với job dài, thường cần outcomes + checkpoint hơn là đánh dấu “batch failed” rồi retry toàn bộ.

## 22. Partial success là một hợp đồng nghiệp vụ

Ví dụ 100 inputs:

~~~text
APPLIED          87
ALREADY_EXISTS    5
FAILED            6
UNKNOWN           2
-------------------
TOTAL           100
~~~

Một summary:

~~~java
public record BatchSummary(
        long requested,
        long applied,
        long conflicts,
        long failed,
        long unknown) {}
~~~

Hoặc response minh họa:

~~~json
{
  "batchId": "import-20261125-42",
  "requested": 3,
  "items": [
    {"id": "customer::1001", "status": "APPLIED"},
    {"id": "customer::1002", "status": "ALREADY_EXISTS"},
    {"id": "customer::1003", "status": "UNKNOWN"}
  ]
}
~~~

Đây là **format ứng dụng tự thiết kế**, không phải SDK bulk response. Không trả `success: true` chỉ vì Flux kết thúc bình thường khi đã có per-key FAILED/UNKNOWN.

Với nhiều triệu items, lưu per-key outcomes ở nơi có quyền truy cập phù hợp và trả job ID/tổng kết qua API; không nhồi mọi trạng thái vào một JSON response quá lớn.


## 23. Ambiguous timeout: item `UNKNOWN` không phải item `FAILED`

Tình huống điển hình:

~~~text
Client gửi insert(key-A).
Server đã ghi key-A.
Response bị mất trên mạng.
Client gặp AmbiguousTimeoutException.
~~~

Ở phía client, **không biết chắc mutation đã xảy ra hay chưa**. Nếu retry:

- `insert` có thể trả `DocumentExistsException`, nhưng key có sẵn chưa chứng minh **cùng business event**.
- `upsert` có thể ghi đè một bản cập nhật mới của writer khác.
- `increment` có thể tăng **lần thứ hai**.
- `mutateIn` có thể lặp lại mutation không idempotent.
- `replace` CAS có thể gặp conflict vì lần đầu đã thành công.

Java SDK phân biệt `AmbiguousTimeoutException` và `UnambiguousTimeoutException` trong nhóm timeout. Cần xem loại lỗi và `ErrorContext` tương ứng, không biến mọi timeout thành trạng thái chắc chắn “chưa ghi”.

### Chính sách xử lý

1. Lưu `UNKNOWN` hoặc một trạng thái “cần đối soát” khi outcome ambiguous.
2. Có `batchId`, `eventId`/`itemId` ổn định.
3. Đọc lại key và so với payload fingerprint/version/idempotency marker.
4. Retry chỉ sau khi xác định action có thể lặp an toàn theo contract.
5. Có deadline, budget, jitter và giới hạn retry.
6. Không tự retry toàn batch khi chỉ vài keys UNKNOWN.

**Mỗi write riêng lẻ nguyên tử không có nghĩa một logical command luôn được áp dụng đúng một lần qua timeout/replay.**

## 24. Không đặt `retry(3)` ngoài toàn batch writes

Nguy hiểm:

~~~java
Flux.fromIterable(changes)
        .flatMap(change -> applyWrite(change), 16)
        .retry(3);
~~~

Nếu một item lỗi, `retry` có thể **resubscribe từ đầu**, chạy lại cả các items đã thành công. Điều này có thể gây:

- Duplicate event, tăng counter lần hai.
- Upsert một body cũ sau khi writer khác sửa.
- `DocumentExistsException` ở lần lặp.
- Ghi đè dữ liệu do retry theo thứ tự khác.
- Tăng tải cấp số nhân trong giờ cluster đang yếu.

Hướng đúng là chính sách từng item:

~~~java
Flux.fromIterable(changes)
        .flatMap(change ->
                applyOneWithExplicitRetryPolicy(change),
                16);
~~~

`applyOneWithExplicitRetryPolicy` là **hàm ứng dụng minh họa**; phải phân loại exception và độ idempotent của từng operation.

### Ví dụ retry cho GET idempotent

~~~java
import reactor.util.retry.Retry;
import java.time.Duration;

Mono<GetResult> read = customers.reactive()
        .get(documentId)
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                        .filter(error -> error instanceof
                                UnambiguousTimeoutException));
~~~

Đây chỉ là mẫu cho **read-only GET**, không phải policy tốt nhất mặc định cho mọi deployment. SDK đã có retry strategy; một lớp retry bổ sung phải giữ **total time budget** và tránh retry storm.

Không sao chép cùng `retryWhen` sang `increment` hoặc mọi `upsert` khi chưa có idempotency.

## 25. Idempotency key và checkpoint cho job lâu dài

Với một job nhập một triệu events:

~~~text
batchId = import-20261125
  event-00001 -> customer::1001
  event-00002 -> customer::1002
  event-00003 -> customer::1003
  ...
~~~

Cần có:

- Event identity ổn định giữa các lần chạy.
- Checkpoint đã áp dụng/chưa áp dụng theo chunk hoặc partition.
- Trạng thái `PENDING`, `APPLIED`, `CONFLICT`, `UNKNOWN`, `FAILED` đúng nghĩa.
- Khả năng resume chỉ các item chưa giải quyết.
- Reconciliation cho outcome ambiguous.
- Cơ chế deduplication dựa trên **logical event ID** chứ không chỉ document key.
- Deadline và backoff cho items lỗi tạm thời.
- Giới hạn số parallel workers và tài nguyên khi restart.

**Cảnh báo:** Ghi “processed-event marker” ở một document rồi sửa Customer ở document khác **không tự nguyên tử**. Nếu marker và mutation cần cùng commit, dùng transaction hoặc thiết kế idempotent khác với invariants chứng minh được.

### `DocumentExistsException` không tự bằng “event đã áp dụng”

Nếu `insert(customerId, body)` trả exists sau retry, đọc lại và kiểm tra `eventId`/payload digest/canonical version. Key có thể tồn tại vì một event khác. Không gán mọi exists thành `APPLIED` mà bỏ bước xác minh.

## 26. Bounded concurrency theo batch khác giới hạn toàn service

Giả sử:

~~~text
Một HTTP request: flatMap(...,16)
40 HTTP requests đang chạy song song
=> Có thể có khoảng 40 × 16 = 640 inner operations in-flight
   tại những operators đó, chưa kể jobs và các pod khác.
~~~

Cần **nhiều lớp giới hạn**:

1. `maxConcurrency` cho từng batch.
2. `maxBatchSize` cho số keys/request.
3. Bulkhead/admission limit cho số batch requests đang chạy.
4. Rate limiter theo tenant/API operation.
5. Giới hạn tổng KV operations in-flight ở pod nếu cần.
6. Distributed quota/concurrency khi có nhiều pods.
7. Hàng chờ hữu hạn với timeout/backpressure.
8. Bộ lập lịch cho jobs dài và priority nếu cần.
9. Cơ chế fail fast khi overload thay vì giữ queue vô hạn.
10. Monitoring theo operation và outcome.

**`flatMap(...,16)` không phải global semaphore, cũng không phải distributed rate limiter.**

Nếu các HTTP requests đồng thời tăng mạnh, hãy định nghĩa số lượng tối đa được phép chạy song song hoặc trả 429/503 theo chính sách API, không tin mỗi batch đã giới hạn là đủ.

## 27. Giới hạn số in-flight không đồng nghĩa QPS cap

- **Concurrency**: có bao nhiêu operations chưa hoàn tất cùng lúc.
- **Rate**: có bao nhiêu operations được bắt đầu trong một giây.

Ví dụ 16 in-flight operations với latency thấp có thể tạo QPS lớn; với latency cao thì QPS nhỏ hơn. Do đó:

| Mục tiêu | Công cụ phù hợp |
| --- | --- |
| Tránh có quá nhiều KV requests đang chờ | `flatMap(...,N)`/bulkhead |
| Hạn chế 500 new writes/s | Rate limiter theo đơn vị thời gian |
| Giới hạn mỗi client tối đa 200 IDs | API validation |
| Tránh hàng chờ vô hạn | Bounded queue/admission |
| Hạn chế jobs cùng chạy | Job scheduler/concurrency gate |
| Giảm áp lực hot key | Keyed serialization hoặc phân phối key theo thiết kế |

`delayElements(...)` có thể làm chậm một stream, nhưng **không** là distributed global rate limiter khi có hàng trăm subscriptions và nhiều pods.

## 28. Dùng `buffer` theo chunk thay vì gom toàn bộ

Nếu nguồn IDs là `Flux<String>` có thể stream:

~~~java
Flux<BatchSummary> summaries =
        sourceIds
                .buffer(200)
                .concatMap(chunk -> processOneChunk(chunk, 16));
~~~

`processOneChunk(...)` là hàm ứng dụng trả `Mono<BatchSummary>`, dùng bounded KV fan-out bên trong chunk, lưu checkpoint trước khi hoàn tất.

Diễn giải:

- `buffer(200)` chỉ nhóm tối đa 200 phần tử trong Reactor.
- `concatMap` xử lý lần lượt từng chunk ở tầng này.
- Bên trong mỗi chunk có tối đa 16 operations đang chờ nếu dùng `flatMap(...,16)`.
- Chuyển chunk sau sau khi chunk trước đã xử lý/log outcome theo policy.

Nếu muốn 4 chunks xử lý đồng thời:

~~~java
sourceIds.buffer(200)
        .flatMap(
                chunk -> processOneChunk(chunk, 16),
                4);
~~~

Về mặt cấu trúc, số KV inner ops có thể lên tới **4 × 16 = 64** trong pipeline đó. Chọn concurrency ở **từng cấp** mà không tính tổng có thể gây oversubscription.

**`buffer(200)` không biến 200 KV calls thành một network command atomic hoặc giảm số round trips như một bulk protocol.**

## 29. `reduce` kết quả mà không giữ mọi document trong memory

Một job chỉ cần thống kê:

~~~java
public record OutcomeCounts(
        long found,
        long missing,
        long failed) {

    public OutcomeCounts add(LookupOutcome outcome) {
        return switch (outcome.status()) {
            case FOUND ->
                new OutcomeCounts(found + 1, missing, failed);
            case NOT_FOUND ->
                new OutcomeCounts(found, missing + 1, failed);
            case FAILED ->
                new OutcomeCounts(found, missing, failed + 1);
        };
    }
}
~~~

Tính summary:

~~~java
Mono<OutcomeCounts> counts = readMany(customers, requests)
        .reduce(
                new OutcomeCounts(0, 0, 0),
                OutcomeCounts::add);
~~~

`reduce` giữ accumulator nhỏ và không gom mọi JSON body. Nhưng nếu cần resume failures, **chỉ có summary không đủ**: phải ghi trạng thái từng key hoặc checkpoint lên storage bền vững.

Nếu consumer thực sự cần dữ liệu từng row, hãy xử lý stream/batch, không `collectList()` trên hàng triệu bodies.

## 30. `CompletableFuture.allOf` không giới hạn concurrency

Một mẫu dễ gây overload:

~~~java
List<CompletableFuture<GetResult>> futures = ids.stream()
        .map(id -> customers.async().get(id))
        .toList();

CompletableFuture<Void> all = CompletableFuture.allOf(
        futures.toArray(new CompletableFuture[0]));
~~~

Đoạn đầu có thể khởi tạo **mọi GET ngay** khi tạo list. `allOf` chỉ phối hợp chờ completions, **không** khống chế in-flight count.

Nếu dùng async API:

- Chia input thành window/chunk với số lượng hữu hạn.
- Chỉ khởi tạo futures của window hiện tại khi còn capacity.
- Không `join()` hoặc `get()` trên thread callback IO của SDK.
- Phân loại errors theo từng future thay vì chỉ một failure của `allOf`.
- Quản lý cancellation, ambiguity và memory.
- Dùng chung `AsyncCollection`/Cluster đã có.
- Không tạo một executor thread cho từng document chỉ để bọc blocking API.

Với fan-out và xử lý lỗi linh hoạt, tài liệu Couchbase Java SDK gợi ý **reactive API** là lựa chọn tiện hơn trong đa số trường hợp.

## 31. WebFlux: `Mono.just(blockingCall())` vẫn blocking

Sai:

~~~java
Mono<GetResult> bad = Mono.just(
        customers.get(documentId));
~~~

`customers.get(documentId)` được thực thi **ngay trước** khi `Mono.just` nhận argument, vẫn chặn thread hiện tại.

Nếu bắt buộc bridge một thư viện blocking:

~~~java
Mono<GetResult> bridge =
        Mono.fromCallable(() -> customers.get(documentId))
                .subscribeOn(Schedulers.boundedElastic());
~~~

Đây vẫn là **blocking IO**, chỉ đưa lên scheduler khác, tiêu thụ thread/queue. Khi SDK đã có reactive, ưu tiên:

~~~java
Mono<GetResult> nonBlocking =
        customers.reactive().get(documentId);
~~~

Không gọi `block()` trong WebFlux event-loop. Không gọi `subscribe()` trong service rồi trả “success” trước khi các writes hoàn tất; trả publisher gắn với lifecycle request hoặc job.

### `Flux.parallel()` không phải lựa chọn mặc định

SDK reactive đã xử lý IO nonblocking. `parallel().runOn(Schedulers.parallel())` không tự làm Data Service nhanh hơn và có thể làm concurrency/ordering khó đo hơn. Bắt đầu với `flatMap(...,N)`; nếu có xử lý CPU nặng riêng, profiling và tách scheduler cho **CPU stage** sau đó.

## 32. Cancellation và overall timeout không rollback operations

Một giới hạn cho cả batch:

~~~java
Flux<WriteOutcome> batch =
        insertMany(customers, input)
                .timeout(Duration.ofSeconds(5));
~~~

Khi Reactor timeout/cancel subscription:

- Những operations đã hoàn tất vẫn áp dụng.
- Requests đã dispatch có thể đang thực thi.
- Không phải key nào chưa có outcome cũng “chưa được ghi”.
- Một response có thể mất, tạo trạng thái UNKNOWN.
- Không có rollback như transaction.

**Đặt timeout theo hai cấp:** per-KV operation và overall batch/job budget. Một batch deadline cần tính tới số items, concurrency, retry và SLA thực tế, không lấy `N × perItemTimeout` làm công thức mặc định.

Nếu timeout khi bulk write, hướng đúng là checkpoint + reconciliation, không replay vô điều kiện cả danh sách input.

## 33. Spring Data mapping, `@Version` và SDK raw

Entity Spring Data:

~~~java
@Document
@Scope("crm")
@Collection("customers")
public class Customer {

    @Id
    private String id;

    @Version
    private Long version;

    @Field("display_name")
    private String displayName;

    private String tenantId;
}
~~~

Repository `save(...)` đi qua mapping, converter, optimistic locking và callbacks theo cấu hình.

Raw SDK:

~~~java
customers.reactive().upsert(documentId, rawJson);
~~~

**Không tự chạy** Spring Data:

- `@Field`/custom converter từ Java property sang JSON field.
- `@Version` CAS check.
- Auditing/lifecycle callbacks.
- Entity expiry policy nếu raw operation có TTL options khác.
- Bảo mật tenant/business invariants.

Nếu cùng document được ghi qua Repository và SDK batch, hãy có **document contract** thống nhất và integration test chéo. Sử dụng SDK direct khi cần per-key options/outcomes, reactive orchestration hoặc thấp tầng KV mà Repository/Template chưa cung cấp thuận tiện; không chuyển mọi entity mutation sang SDK chỉ vì có batch.

## 34. TTL và durability là lựa chọn từng mutation

Ví dụ expiry:

~~~java
import java.time.Duration;
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;

Mono<MutationResult> write = customers.reactive().insert(
        documentId,
        body,
        insertOptions().expiry(Duration.ofDays(30)));
~~~

Ví dụ durability:

~~~java
import com.couchbase.client.java.durability.DurabilityLevel;
import static com.couchbase.client.java.kv.UpsertOptions.upsertOptions;

Mono<MutationResult> durable = customers.reactive().upsert(
        documentId,
        body,
        upsertOptions().durability(DurabilityLevel.MAJORITY));
~~~

- TTL có semantics khác tùy insert/replace/upsert, maxTTL và preserve-expiry options; cần kiểm chứng cho version.
- Durability chỉ áp dụng với operation đã cấu hình, **không làm cả batch atomic**.
- Durability cao có thể tăng latency, khiến `maxConcurrency` tối ưu thay đổi.
- Không suy ra UNKNOWN là không đạt durability hay chưa ghi.
- Cùng Cluster không làm Repository/Template và SDK direct có cùng mutation options.

## 35. Khi nào SQL++ DML phù hợp hơn fan-out KV?

Nếu cần cập nhật **mọi document khớp một predicate**:

~~~sql
UPDATE `shop`.`crm`.`customers` AS c
SET c.segment = "LOYAL"
WHERE c.tenantId = $tenantId
  AND c.loyaltyPoints >= $minPoints;
~~~

SQL++ DML có thể tránh vòng “query hàng nghìn ID rồi get/replace từng document”. Tuy nhiên phải đánh giá:

1. Index và `EXPLAIN` cho predicate.
2. Có nguy cơ cập nhật nhầm tenant/collection không?
3. Mutation count/timeout có đủ cho reconciliation không?
4. Điều kiện CAS/transaction/business invariants cần gì?
5. Cần per-key outcomes hay chỉ report tổng?
6. Workload đẩy sang Query Service có ảnh hưởng OLTP không?
7. Có idempotency và rollback plan khi lỗi?

**Một câu SQL++ UPDATE không phải cách thay thế mặc định cho một transaction nhiều document**. Nếu invariant yêu cầu all-or-nothing, dùng transaction API phù hợp.

Với **danh sách key xác định** và từng mutation độc lập, bounded KV fan-out có thể dễ kiểm soát per-key errors hơn.

## 36. Đo hiệu năng theo cả throughput lẫn tail latency

Theo dõi:

| Chỉ số | Cần quan sát |
| --- | --- |
| KV operations in-flight | Budget có được giữ không? |
| Items/s và batch completion time | Throughput và latency tổng |
| KV p50/p95/p99 | Tail latency của mỗi operation |
| Batch p95/p99 | Độ trễ user/job chờ cả lô |
| RequestCanceled/timeout | SDK/server bị quá tải không? |
| Ambiguous/unknown outcomes | Cần bao nhiêu reconciliation? |
| CAS conflicts/DocumentExists | Đụng contention/data quality không? |
| Retry attempts | Có retry storm không? |
| JVM heap/GC | Buffer/`collectList` có tạo memory pressure không? |
| Pending queue | Có tăng vô hạn không? |
| Data Service CPU/disk/vBucket | Có hot node/key không? |
| Tenant throughput | Có tenant chiếm hết capacity không? |
| Completed vs unresolved items | Job có backlog chưa đối soát không? |

Benchmark một workload đại diện:

~~~text
Concurrency:   1, 4, 8, 16, 32, 64
Batch sizes:   100, 1000, 10000
Operations:    GET, INSERT, REPLACE(CAS)
Payloads:      small, medium, large
Durability:    default, MAJORITY
~~~

Không chọn concurrency chỉ vì p50 thấp nhất. Cần xem **p99, error rate, memory và tác động lên những query/transaction OLTP chạy chung cluster**.

## 37. Chọn `maxConcurrency` dựa trên bằng chứng

Các câu hỏi tuning:

- Tải read-only hay write?
- Payload size/encoding có lớn không?
- Key phân phối đều hay cùng hot key?
- Có yêu cầu durability/số replica cao không?
- Số HTTP requests và jobs đồng thời là bao nhiêu?
- Có bao nhiêu pods cùng dùng Cluster?
- Network latency và timeout budget thế nào?
- P95/p99 tăng ra sao khi từ 16 lên 32?
- Rate retry/timeout có tăng không?
- Có service khác cần được ưu tiên?
- Khi queue đầy, trả 429/503 hay chờ hữu hạn?
- Có SLO cho reconciliation, không chỉ request thành công?

**Không có một mức `maxConcurrency=16` lý tưởng cho mọi hệ thống**. Tăng theo benchmark đến khi throughput không còn cải thiện tương xứng hoặc latency/errors/resource quá mức.

## 38. Bảo mật multi-tenant ở cấp từng item

Bulk endpoint có thể truy cập dữ liệu của nhiều users/tenants chỉ trong một request. Vì vậy:

1. Lấy tenant từ principal/context xác thực.
2. Validate **mọi key**, không chỉ key đầu batch.
3. Chặn việc chọn bucket/scope/collection tự do theo request.
4. Không cho phép một key có prefix tenant khác vượt ranh giới; prefix check không thay full authorization khi key format không đáng tin.
5. Giới hạn số IDs, write amount, rate và concurrency theo tenant.
6. Đọc/hydrate document vẫn phải kiểm tra authorization khi cần.
7. Log outcomes với IDs được che/hashed theo policy.
8. Không đưa raw `ErrorContext`, token hoặc PII vào response.
9. Audit quyền và nguồn của bulk mutations.
10. Giới hạn quyền service account/RBAC đúng keyspace và operation.

**Concurrency cap không phải cơ chế bảo mật.** Một batch với N=1 vẫn có thể gây lộ dữ liệu nếu tenant validation sai.

## 39. Integration test cho bounded bulk read

Seed:

~~~text
customer::A -> body A
customer::B -> body B
customer::C -> body C

Input [A, missing, B, A]
~~~

Kỳ vọng:

- **4 outcomes** nếu contract giữ duplicate positions.
- **3 FOUND**, **1 NOT_FOUND**.
- Mỗi outcome giữ đúng key/position.
- Không giả định `flatMap` theo thứ tự input.
- Chọn `flatMapSequential` thì output theo input.
- Không có body tenant khác lọt qua.
- Concurrency 1/4/16 cho cùng tập results (không assert thứ tự completion).
- Không gọi `Cluster.connect(...)` theo mỗi key.

### Test max concurrency

Với một nguồn `Mono` giả có instrumentation:

~~~text
active += 1 khi inner subscribe
active -= 1 khi inner terminate/cancel
maxActive = max(maxActive, active)
assert maxActive <= maxConcurrency
~~~

Test operator semantics này không thay integration test trên Couchbase thật, nhưng giúp xác nhận **giới hạn trong một subscription**. Một test tổng service cần tạo nhiều subscriptions và kiểm tra global admission policy.

## 40. Integration test cho writes, CAS và idempotency

**A. Insert conflicts**

~~~text
Seed: A đã tồn tại, B chưa có, C chưa có
Batch: insert(A), insert(B), insert(C)
Expect: ALREADY_EXISTS, APPLIED, APPLIED
~~~

Xác minh A không bị overwrite. Nếu retry sau timeout và B đã tồn tại, chỉ coi “event B đã xử lý” khi current body/event ID khớp.

**B. CAS**

1. Đọc A lấy CAS1.
2. Writer khác cập nhật A sinh CAS2.
3. Batch gửi `replace(A, expectedCas=CAS1)`.
4. Xác minh `CasMismatchException`/conflict.
5. Không ghi đè update của writer khác.
6. Không retry CAS1 vô hạn.

**C. Cùng key**

Gửi hai changes liên tiếp trên A, thử `flatMapSequential` và `concatMap`. Chứng minh cái đầu **chỉ giữ output order**, cái sau có thể giữ thứ tự execution vì inner publisher được subscribe tuần tự.

**D. Replay**

Mô phỏng job restart, chỉ replay pending/unknown theo policy; không tăng counter hoặc upsert toàn bộ items mà không kiểm tra.

**E. Cấu hình dữ liệu**

Xác minh đúng bucket/scope/collection, JSON mapping `@Field`, TTL, CAS, auditing và quyền tenant khi Repository/SDK cùng ghi.

## 41. Fault injection và kiểm tra khả năng khôi phục

| Tình huống | Điều cần chứng minh |
| --- | --- |
| DocumentNotFound trên một item | Không mất dấu item |
| DocumentExists khi insert | Không upsert ghi đè |
| CAS mismatch | Không mất cập nhật cạnh tranh |
| Timeout ambiguous | Có UNKNOWN/reconciliation |
| RequestCanceled do quá tải | Có telemetry, không trả thành 404 |
| Cluster failover/rebalance | Partial outcomes và restart đúng |
| Batch cancellation | Không khẳng định in-flight writes rollback |
| Process crash giữa chunk | Checkpoint phục hồi an toàn |
| 100 bulk HTTP requests song song | Global in-flight budget |
| 100.000 IDs | Không giữ mọi bodies trong một list |
| Wrong scope/collection | Test phát hiện keyspace sai |
| Missing RBAC | Không tự fallback credential quyền cao |
| TTL/durability khác mặc định | Không phá chính sách entity |
| Duplicate event/key | Có quy tắc idempotency/order |
| Mạng chậm, high tail latency | Bounded concurrency giữ tài nguyên ổn định |

Dùng cluster/test deployment cô lập; không gây fault trên production để kiểm thử.

## 42. Những lỗi thường gặp

| Anti-pattern | Hậu quả | Thay thế |
| --- | --- | --- |
| Blocking KV trong WebFlux event-loop | Chặn request threads | SDK reactive |
| `flatMap` không có concurrency policy | Dễ quá tải hoặc không dự đoán được | `flatMap(...,N)` |
| Phát mọi futures rồi `allOf` | Không có in-flight cap | Windows/reactive |
| Nghĩ `flatMap(...,N)` giới hạn toàn cluster | N áp dụng cho mỗi subscription | Global bulkhead/rate limiting |
| `flatMapSequential` để giữ thứ tự write | Chỉ bảo đảm output order | `concatMap`/keyed serialization |
| `collectList` cho triệu bodies | OOM/GC | Streaming/chunks |
| `onErrorResume(e -> Mono.empty())` mọi lỗi | Che partial failures | Per-key outcomes |
| `retry(3)` ngoài batch writes | Replay items đã thành công | Per-item policy + idempotency |
| `upsert` thay mọi conflict | Ghi đè cập nhật mới | `insert`/CAS/merge |
| Ambiguous timeout coi chắc chắn failed | Duplicate side effects | UNKNOWN + reconciliation |
| `DocumentExists` coi chắc chắn cùng event | Có thể key khác payload | Verify event/payload |
| Batch KV coi là transaction | Partial commits | Transaction khi cần |
| `buffer(200)` coi như bulk network atomic | Sai semantics | Xem nó như client-side chunk |
| SDK raw map như entity Spring | Sai `@Field`, CAS, TTL | Document contract |
| Chỉ giới hạn per-batch không giới hạn HTTP | Overload khi nhiều callers | Global admission |
| Không kiểm tra tenant từng key | Bulk data leak | Trusted auth/routing |

## 43. Ma trận chọn kỹ thuật

| Use case | Công cụ khởi đầu | Lý do |
| --- | --- | --- |
| Đọc 50 keys độc lập | `flatMap(...,N)` | Concurrent KV với budget |
| Đọc 50 keys theo input order | `flatMapSequential(...,N)` | Ordered output |
| Hai mutations phải đúng thứ tự cùng key | `concatMap`/keyed queue | Ordered side effects |
| Nhập 10.000 docs mới, không ghi đè | `insert` + chunks + per-key outcome | Phát hiện conflict/replay |
| Đồng bộ desired state được phép replace | `upsert` với version/idempotency policy | Overwrite có chủ ý |
| Chỉnh sửa theo optimistic lock | `replace` kèm CAS | Chặn lost update |
| Sửa vài fields trong một document | `mutateIn` | Atomic theo document |
| Ba documents cùng commit/rollback | Transaction | Nhiều-document atomicity |
| Update mọi docs khớp predicate | SQL++ DML nếu phù hợp | Tránh enumerate IDs |
| Stream hàng triệu IDs | Bounded stream/chunk/checkpoint | Giữ memory và restart |
| Cần batch progress/audit | Per-key results + job store | Biết partial successes |
| Logical event exactly-once qua retry | Idempotency/transaction/event log | Concurrency cap không đủ |
| Hot key | Keyed serialization/partition | Bảo vệ thứ tự và contention |
| 100 HTTP batches chạy cùng lúc | Global bulkhead/rate limiter | Per-batch N không đủ |

## 44. Checklist code review

### Semantics và concurrency

- [ ] Hợp đồng partial success và all-or-nothing được viết rõ.
- [ ] `maxConcurrency` và input cap có số cụ thể, đã benchmark.
- [ ] Có global request/job admission khi traffic lớn.
- [ ] Chọn `flatMap`/`flatMapSequential`/`concatMap` theo **thứ tự thực tế cần**.
- [ ] Key trùng không bị `distinct` vô ý hoặc ghi đè ngoài hợp đồng.
- [ ] Không gọi blocking SDK trong WebFlux event-loop.
- [ ] Không `collectList` không giới hạn.
- [ ] Chunking/checkpoint đối với job lớn.

### Correctness

- [ ] `NOT_FOUND` khác `FAILED` và `UNKNOWN`.
- [ ] Không retry cả batch mutation vô điều kiện.
- [ ] Ambiguous timeout được đối soát.
- [ ] `DocumentExists` phải xác minh event identity trước khi coi là idempotent.
- [ ] CAS được dùng khi cần chống lost update.
- [ ] Nhiều document cần all-or-nothing dùng transaction.
- [ ] SDK raw tuân thủ `@Field`/`@Version`/TTL/durability contract.
- [ ] Có tenant authorization cho từng item.

### Vận hành và test

- [ ] Cluster/Collection là Spring-managed, không connect từng key.
- [ ] Theo dõi throughput, p95/p99, in-flight, retry, conflict, unknown.
- [ ] Có test Couchbase thật với insert conflict/CAS/TTL/tenant.
- [ ] Có fault injection timeout/cancellation tại môi trường test.
- [ ] Có queue/bulkhead và rate limit theo tenant/operation.
- [ ] Không log body, token hoặc ErrorContext nhạy cảm công khai.
- [ ] Job có thể resume sau crash không duplicate blindly.

## 45. Bài tập thực hành

**A. Bounded bulk GET**

1. Seed 500 Customers trong `shop.crm.customers`.
2. Inject Spring-managed `Cluster`, giữ `Collection` ở adapter.
3. Viết `readMany` bằng `flatMap(...,16)` với `LookupOutcome`.
4. Thử 10 IDs không có, xác nhận `NOT_FOUND`.
5. Thử ID trùng và kiểm tra `position`.
6. So với `flatMapSequential`.
7. Benchmark concurrency 1/4/8/16/32.
8. Giới hạn input API 200 IDs.
9. Kiểm tra không đọc dữ liệu tenant khác.

**B. Bulk INSERT có per-key outcomes**

1. Dùng `InsertRequest` với key ổn định.
2. Viết `insertMany` dựa trên `customers.reactive().insert`.
3. Seed 5 keys trùng để tạo `DocumentExistsException`.
4. Ghi outcome từng key, tổng kết `APPLIED/CONFLICT/UNKNOWN/FAILED`.
5. Giả lập ambiguous timeout rồi thiết kế reconciliation.
6. Tạo chunk 200 items, lưu checkpoint sau chunk.
7. Test restart mà không replay bừa cả batch.

**C. CAS và thứ tự trên cùng key**

1. Đọc Customer để lấy CAS1.
2. Writer khác thay đổi Customer.
3. Thử replace với CAS1, nhận conflict.
4. Gửi hai mutations trên cùng key bằng `flatMap(...,2)`.
5. Thử `flatMapSequential`, quan sát nó chỉ giữ output order.
6. Sửa bằng `concatMap`/keyed queue.
7. Kiểm tra Spring Data `@Version` và raw JSON mapping.

**D. Kiến trúc và vận hành**

1. Đo 1000 KV writes so với SQL++ `UPDATE WHERE` trên workload tương đương.
2. Mô tả tình huống cần transaction 3 documents.
3. Thiết kế global bulkhead cho 50 HTTP bulk requests.
4. Thử high latency, cancellation và retry.
5. Vẽ timeline server đã commit nhưng client không nhận ack.
6. Viết ADR giải thích concurrency, rate cap và partial failure policy.

### Câu hỏi tự kiểm tra

1. Couchbase Java SDK có một bulk API chung tự động transaction nhiều KV writes không?
2. `Collection.get`, `async().get` và `reactive().get` khác nhau ở đâu?
3. `flatMap(...,16)` giới hạn chính xác điều gì?
4. Vì sao 40 HTTP requests có thể vượt tổng 16 KV ops?
5. `flatMapSequential` có bảo đảm thứ tự ghi cùng key không?
6. Khi nào `concatMap` phù hợp hơn `flatMap`?
7. Vì sao `onErrorResume(e -> Mono.empty())` có thể nguy hiểm?
8. `collectList` có làm mất lợi ích memory của bounded concurrency không?
9. `buffer(200)` có tạo một network command atomic không?
10. `CompletableFuture.allOf` có giới hạn số futures được tạo không?
11. Lỗi item 5 có rollback các mutations item 1-4 không?
12. `DocumentExistsException` đủ chứng minh event xử lý đúng không?
13. `AmbiguousTimeoutException` có nghĩa chắc chắn chưa ghi không?
14. Vì sao retry cả Flux writes có thể gây duplicate?
15. CAS bảo vệ loại xung đột nào, và có bảo vệ nhiều docs cùng lúc không?
16. SDK `upsert` có tự dùng Spring Data `@Version` không?
17. Concurrency cap và rate limit khác nhau thế nào?
18. Khi nào SQL++ UPDATE phù hợp hơn fan-out KV?
19. Khi nào phải dùng transaction?
20. Test nào chứng minh in-flight cap?
21. Test nào chứng minh partial outcomes và replay?
22. Vì sao fail-fast không bảo đảm những writes in-flight đã rollback?
23. Job dài cần checkpoint/idempotency vì lý do gì?
24. Metrics nào cảnh báo bạn đã tăng concurrency quá cao?

## 46. Tài liệu chính thức và kiểm chứng phiên bản

- [Couchbase Java SDK — Async and Reactive APIs](https://docs.couchbase.com/java-sdk/current/howtos/concurrent-async-apis.html): `async()`, `reactive()`, batching qua Reactor và per-key error handling.
- [Couchbase Java SDK — KV Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): `get`, `insert`, `upsert`, `replace`, CAS, expiry, durability.
- [Couchbase Java SDK — Handling Errors](https://docs.couchbase.com/java-sdk/current/howtos/error-handling.html): ambiguous/unambiguous timeouts, RequestCanceled, ErrorContext và idempotency.
- [Couchbase Java SDK — Transactions](https://docs.couchbase.com/java-sdk/current/howtos/distributed-acid-transactions-from-the-sdk.html): atomicity nhiều document theo transaction context.
- [Couchbase Java SDK — Sub-Document Operations](https://docs.couchbase.com/java-sdk/current/howtos/subdocument-operations.html): `mutateIn` theo một document.
- [Java SDK API — ReactiveCollection](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/ReactiveCollection.html): kiểu `Mono` cho các KV operations.
- [Java SDK API — AsyncCollection](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/AsyncCollection.html): `CompletableFuture` variants.
- [Project Reactor — Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `flatMap`, `flatMapSequential`, `concatMap`, prefetch và concurrency.
- [Project Reactor — Batching, Grouping, Windowing](https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-three-sorts-batching.html): `buffer`/`groupBy` và caveats.
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `onErrorResume`, `retryWhen` và termination.
- [Spring Data Couchbase — Repository](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): entity CRUD/mapping.
- [Spring Data Couchbase — Template](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): thao tác entity và mở rộng bằng SDK.
- [Couchbase Server — SQL++ UPDATE](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/update.html): DML theo predicate.

**Lưu ý theo phiên bản:** Các ví dụ sử dụng hướng API **Couchbase Java SDK 3.x** và **Project Reactor 3.x**. Cần kiểm tra kiểu/method/options, exception hierarchy, TTL/durability behavior, Spring mapping và policy retry theo dependencies thực tế. `LookupOutcome`, `WriteOutcome`, batch summary, bulkhead, checkpoint là **kiểu kiến trúc ứng dụng**, không phải một API bulk transaction do SDK cung cấp. Vòng QA chuyên môn/biên dịch/integration test thuộc bước sau soạn nội dung.

> **Ghi nhớ:** Bounded concurrency là cách **bảo vệ hệ thống khi xử lý nhiều document**, không phải cách tạo một giao dịch. Dùng `flatMap(...,N)` cho IO độc lập; `flatMapSequential` khi cần thứ tự kết quả; `concatMap`/keyed serialization khi cần thứ tự **side effects**. Có input/global limits, outcome từng key, idempotency/reconciliation cho timeout ambiguous, CAS cho một document và transaction cho bất biến nhiều documents. Một batch nhanh nhưng không thể đối soát không phải một batch đáng tin cậy.
