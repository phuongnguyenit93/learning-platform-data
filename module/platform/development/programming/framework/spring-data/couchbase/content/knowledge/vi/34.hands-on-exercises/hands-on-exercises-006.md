# Mô phỏng đọc sau ghi với nhiều mức nhất quán

Trong **Spring Data Couchbase**, việc `repository.save(entity)` hoàn tất và thao tác `repository.findById(id)` đọc lại được document **không đồng nghĩa** mọi truy vấn SQL++ theo `status`, `tenant_id` hoặc một secondary index đều thấy document mới ngay lập tức. Bài thực hành này giúp bạn tự quan sát sự khác nhau giữa **KV read-after-write**, SQL++ mặc định (**`NOT_BOUNDED`**), SQL++ **`REQUEST_PLUS`** và **`AT_PLUS` qua mutation state** khi API cung cấp mutation token.

Bài thuộc chương **Bài thực hành** của module **SPRING_DATA_COUCHBASE**. Nội dung áp dụng document mapping, repository và `ReactiveCouchbaseTemplate` bên cạnh Couchbase Java SDK reactive, SQL++, bucket/scope/collection, secondary index, TTL, CAS, durability, transaction và lựa chọn API phản ứng để đạt hiệu năng, tính nhất quán và khả năng vận hành.

> **Mục tiêu của thí nghiệm không phải ép `NOT_BOUNDED` trả dữ liệu cũ.** Ở cluster khỏe, index có thể bắt kịp trước khi query bắt đầu. Mục tiêu là nhận biết **mỗi mode bảo đảm điều gì**, đo được gì trong một lần chạy, và không suy từ quan sát tức thời thành một bảo đảm mà API không hứa.

## 1. Kết quả cần hoàn thành

Sau bài, bạn cần có:

1. Bucket/scope/collection **chỉ dành cho lab**, index đã xây và `ONLINE`.
2. Tài liệu ngắn về namespace, phiên bản Couchbase Server, Spring Data Couchbase và Java SDK.
3. Một đường **insert → KV get** chứng minh phép đọc bằng ID sau mutation thành công.
4. Một SQL++ query **theo thuộc tính được index**, không dùng `USE KEYS` để tránh chuyển bài tập thành KV lookup.
5. Ba lần chạy cùng statement với `NOT_BOUNDED`, `REQUEST_PLUS` và `consistentWith(MutationState)`.
6. Một bảng ghi document ID, run ID, trạng thái nhìn thấy, `generation`, thời gian chờ, lỗi và query plan.
7. Phần giải thích tại sao không thấy row trong `NOT_BOUNDED` **có thể** liên quan index lag, nhưng cũng có thể do điều kiện sai, index chưa sẵn sàng, TTL hoặc namespace.
8. Bộ kiểm thử `StepVerifier` không assert rằng `NOT_BOUNDED` phải stale.
9. Một kịch bản update kiểm tra **phiên bản mới** chứ không chỉ `rowCount > 0`.
10. Phân tích riêng sự khác nhau giữa query scan consistency, CAS, durability, TTL và transaction.

## 2. Bản đồ các mức nhất quán trong bài

| Đường đọc | Vai trò | Bảo đảm cần hiểu |
| --- | --- | --- |
| KV `get(documentId)` trên active path | Kiểm tra document theo key | Sau KV write được xác nhận và không có writer/TTL cạnh tranh, thông thường đọc được state vừa ghi mà không đợi secondary index. |
| SQL++ `NOT_BOUNDED` | Query không yêu cầu secondary index bắt kịp mutation mới tới mốc riêng | Có thể thấy state mới hoặc chưa thấy; không có read-your-own-write guarantee qua index theo cách này. |
| SQL++ `REQUEST_PLUS` | Yêu cầu các index liên quan bắt kịp tới mốc consistency của query | Có thể phải chờ index, nên latency/timeout có thể lớn hơn. |
| SQL++ `consistentWith(MutationState)`, thường gọi `AT_PLUS` | Ràng buộc query với mutation được ghi trong token/state | Cần mutation token hợp lệ; không có nghĩa mọi writes khác toàn cluster đều phải được index. |
| KV replica-read API | Đọc từ replica khi API cho phép | Không mặc định có freshness như active KV get. |

**Định nghĩa không được nhập nhằng:** `REQUEST_PLUS`/`AT_PLUS` là **scan consistency của Query Service**; durability là **mức xác nhận lưu/replica**, CAS là **kiểm tra cạnh tranh của mutation**, còn transaction là **nguyên tử nhiều operation trong một phạm vi được hỗ trợ**. Không thể thay thế cơ chế này bằng cơ chế kia.

### 2.1. “AT_PLUS” trong Java SDK

Với Couchbase Java SDK 3.x, cách thường dùng để ràng buộc query với mutation là:

```java
import com.couchbase.client.java.query.MutationState;
import com.couchbase.client.java.query.QueryOptions;

import static com.couchbase.client.java.query.QueryOptions.queryOptions;

MutationState state = MutationState.from(mutationResult);
QueryOptions options = queryOptions().consistentWith(state);
```

`mutationResult` phải đến từ **mutation thật** có token khả dụng. Đừng tự dựng token từ document ID, CAS hoặc timestamp. Spring Data repository `save` thường trả entity, **không tự cung cấp trực tiếp SDK `MutationResult`**; vì vậy phần AT_PLUS của lab dùng Java SDK reactive trực tiếp. Kiểm tra chữ ký phương thức theo phiên bản SDK thực tế.

## 3. Chuẩn bị môi trường thử nghiệm an toàn

Ví dụ namespace:

```text
bucket:     training
scope:      consistency_lab
collection: documents
tenant:     lab-tenant-a
```

Bạn cần Couchbase KV, Query và Index Services, một user test có quyền đọc/ghi **chỉ trên namespace lab** và quyền query tương ứng. Index có thể do admin tạo trước, không cần cấp quyền DDL cho tài khoản ứng dụng.

Bảng ghi thông tin môi trường trước khi chạy:

| Thành phần | Ghi nhận |
| --- | --- |
| Couchbase Server version | Điền giá trị thật |
| Spring Boot / Spring Data Couchbase version | Điền giá trị thật |
| Couchbase Java SDK version | Điền giá trị thật |
| Reactor / Java version | Điền giá trị thật |
| Bucket/scope/collection | `training/consistency_lab/documents` |
| Index và trạng thái build | Điền sau khi xác minh `ONLINE` |
| Số trial ban đầu | 10–20, tuần tự |
| Durability option | Giữ cố định, ghi rõ |
| TTL của fixture | Không đặt hoặc đủ dài cho phép đo |
| Query mode / timeout | Ghi rõ từng trial |

Không chạy thí nghiệm trên production và **không tạo tải hàng loạt chỉ để ép stale read**. Nếu index đã cập nhật ngay, đó là một kết quả hợp lệ.

### 3.1. Vì sao không được làm chậm/tắt index production?

Thay đổi trạng thái Index Service ở môi trường chung có thể ảnh hưởng nhiều ứng dụng không liên quan. Bài yêu cầu đo behavior đúng semantics, **không** yêu cầu gây sự cố. Khi muốn nghiên cứu index backlog, dùng cluster riêng với giới hạn tải và quyền được cấp.

## 4. Thiết kế fixture chống kết quả giả

Mỗi trial tạo document mới, có `run_id` duy nhất:

```json
{
  "tenant_id": "lab-tenant-a",
  "run_id": "batch-a1f3-trial-001",
  "status": "ACTIVE",
  "generation": 1,
  "payload": "consistency-demo"
}
```

Document key:

```text
consistency::lab-tenant-a::batch-a1f3-trial-001
```

**Lý do thiết kế:**

- KV lookup dùng **document ID** chính xác.
- SQL++ query dùng field `tenant_id`/`status`/`run_id` để thực sự kiểm tra index.
- `generation=1` giúp kiểm tra version; ở phần update, đổi thành 2 để thấy bản nào được quan sát.
- `run_id` duy nhất tránh lấy nhầm kết quả từ một lần chạy trước.
- Tenant có giá trị cố định đã được server/test runner kiểm soát, không lấy ngẫu nhiên từ HTTP request.

Không tái sử dụng document ID đã tồn tại với `insert`: insert-only sẽ trả lỗi duplicate, và lỗi đó **không** phải tình huống index lag.

## 5. Tạo secondary index và câu SQL++ chuẩn

Chạy trên **Query Workbench của cluster test** hoặc công cụ DDL được cho phép:

```sql
CREATE INDEX ix_lab_tenant_status_run_gen
ON `training`.`consistency_lab`.`documents` (
    `tenant_id`,
    `status`,
    `run_id`,
    `generation`
);
```

Index tạo một đường truy cập cho query theo tenant, status và run ID. Không cần tạo lại index mỗi lần trial. Nếu index đã tồn tại, kiểm tra định nghĩa và trạng thái `ONLINE` thay vì tạo một index trùng.

SQL++ chuẩn cho cả ba modes:

```sql
SELECT META(d).id AS documentId,
       d.run_id AS runId,
       d.generation AS generation
FROM `training`.`consistency_lab`.`documents` AS d
WHERE d.tenant_id = $tenantId
  AND d.status = $status
  AND d.run_id = $runId;
```

### 5.1. Tại sao không dùng `USE KEYS`?

`USE KEYS` hoặc predicate key-based có thể cho query một đường truy cập không phụ thuộc secondary index như bài muốn đo. Nếu sau đó thấy document ngay, ta chỉ chứng minh một đường query theo key, **không** so sánh đúng secondary-index visibility. Giữ nguyên SQL++ theo ba JSON fields ở trên.

### 5.2. Xem `EXPLAIN` trước khi thu số liệu

```sql
EXPLAIN
SELECT META(d).id AS documentId,
       d.run_id AS runId,
       d.generation AS generation
FROM `training`.`consistency_lab`.`documents` AS d
WHERE d.tenant_id = "lab-tenant-a"
  AND d.status = "ACTIVE"
  AND d.run_id = "example-run";
```

Kiểm tra index được planner chọn, vùng index scan, có cần fetch/sort hay không và độ phù hợp của các field JSON. Nếu plan khác dự kiến, phải ghi lại, không kết luận “đã đo index X” chỉ vì có lệnh `CREATE INDEX`.

### 5.3. Những lý do query không trả row dù không phải stale index

- Sai bucket/scope/collection.
- Query dùng `status="SUSPENDED"` trong khi document là ACTIVE.
- `run_id`/`tenant_id` bind sai hoặc dùng ID cũ.
- Index chưa ONLINE.
- Câu SQL++ lỗi syntax hoặc quyền Query Service.
- Document đã hết TTL hoặc bị test khác xóa.
- Query đang dùng type discriminator khác do Spring Data ánh xạ.
- Truy vấn không thực sự được subscribe.

Hãy xác minh **KV readback + JSON field values + SQL++ parameters + plan** trước khi quy kết index lag.

## 6. Document mapping trong Spring Data Couchbase

Mặc dù phép đo AT_PLUS dùng SDK trực tiếp, cần hiểu cách ứng dụng Spring Data tạo và đọc dữ liệu.

```java
package example.consistency;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("consistency_lab")
@Collection("documents")
public class ConsistencyDocument {

    @Id
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("run_id")
    private String runId;

    @Field("status")
    private String status;

    @Field("generation")
    private Integer generation;

    @Version
    private Long version;

    protected ConsistencyDocument() {}

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getRunId() { return runId; }
    public String getStatus() { return status; }
    public Integer getGeneration() { return generation; }
    public Long getVersion() { return version; }

    // Constructor/factory và setters nghiệp vụ lược bỏ.
}
```

Repository:

```java
package example.consistency;

import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Flux;

public interface ConsistencyRepository
        extends ReactiveCouchbaseRepository<
            ConsistencyDocument, String> {

    Flux<ConsistencyDocument> findByTenantIdAndStatusAndRunId(
        String tenantId,
        String status,
        String runId
    );
}
```

Giải thích:

- `@Id` ánh xạ document key; không tự tạo JSON field `id`.
- `@Field` map property Java sang tên field JSON.
- `@Version` hỗ trợ optimistic locking/CAS theo Spring Data Couchbase release/đường ghi, **không** là query scan consistency.
- `findById` thường truy cập KV theo ID.
- Derived query theo ba thuộc tính thường qua SQL++/secondary index; cần kiểm chứng SQL++ thực thi và index.
- Spring Data có thể thêm type discriminator như `_class` và metadata để map entity; document viết trực tiếp bằng SDK `JsonObject` **không tự mang đúng metadata của Spring Data entity**.

**Quy tắc lab:** Những document insert trực tiếp bằng SDK được đọc lại qua SDK `get`/SQL++ trực tiếp. Một test `repository.save` độc lập phải tạo fixture bằng repository với mapping phù hợp, tránh kết luận sai do thiếu discriminator.

## 7. Baseline: repository `save` rồi `findById`

```java
import reactor.core.publisher.Mono;

Mono<ConsistencyDocument> readAfterWrite =
    repository.save(document)
        .flatMap(saved ->
            repository.findById(saved.getId())
        );
```

Với một subscription, `findById` được thực thi **sau khi `save` trả thành công**. Đây là thứ tự reactive đúng. Đừng viết:

```java
// Sai: hai subscription độc lập, không ràng buộc thứ tự.
repository.save(document).subscribe();
repository.findById(document.getId()).subscribe();
```

Một KV read thông thường từ active path theo ID, trong điều kiện không có write/delete/TTL cạnh tranh, được kỳ vọng đọc thấy document sau write đã xác nhận. Nếu không, kiểm tra ID, namespace, TTL, lỗi hay đọc replica, thay vì đổ lỗi cho secondary index.

**Điều nó chưa chứng minh:** Query theo `WHERE tenant_id = ...` qua Query Service đã thấy cùng mutation.

## 8. Baseline: SDK reactive insert rồi KV get

Thí nghiệm chính cần `MutationResult`. Dùng Couchbase Java SDK reactive với `Collection` trỏ đúng namespace test:

```java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import reactor.core.publisher.Mono;

public Mono<JsonObject> insertThenKvGet(
        Collection collection,
        String documentId,
        String runId) {

    JsonObject body = JsonObject.create()
        .put("tenant_id", "lab-tenant-a")
        .put("status", "ACTIVE")
        .put("run_id", runId)
        .put("generation", 1)
        .put("payload", "consistency-demo");

    return collection.reactive()
        .insert(documentId, body)
        .flatMap(result ->
            collection.reactive().get(documentId)
        )
        .map(getResult -> getResult.contentAsObject());
}
```

Chạy với **ID mới**, không dùng lại cho `insert` ở thử nghiệm AT_PLUS. Khi insert complete, kiểm tra KV get trả `run_id` và `generation=1`. Đây là một luồng I/O non-blocking; không cần `block()`/`subscribe()` trong WebFlux service.

### 8.1. KV và secondary index là hai đường khác nhau

```text
KV insert -> mutation được xác nhận -> KV get(docId)
                                       |
                                       +-> SQL++ WHERE field
                                            -> Query Service
                                            -> secondary index
```

KV get không cần chờ secondary index cho key lookup. SQL++ query có index freshness semantics riêng. Vì thế “KV thấy nhưng SQL++ chưa thấy” không đủ để nói Couchbase làm mất dữ liệu.

## 9. Mode 1 — SQL++ mặc định/`NOT_BOUNDED`

Java SDK 3.x:

```java
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryScanConsistency;
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

QueryOptions ordinary = queryOptions()
    .scanConsistency(QueryScanConsistency.NOT_BOUNDED);
```

Mode này không yêu cầu Query Service phải đợi index thấy mutation vừa ghi. Kết quả hợp lệ có thể là 0 row **hoặc** 1 row ở trial insert mới. Nếu index đã bắt kịp nhanh, `NOT_BOUNDED` vẫn thấy row.

**Sai:** `assertEquals(0, rowCount)` như một bảo đảm của mode này.

**Đúng:** Ghi lại số row/elapsed time và so sánh với query consistency mạnh trong cùng điều kiện; nếu không thấy, điều tra query/index/TTL/parameters trước khi kết luận.

## 10. Mode 2 — SQL++ `REQUEST_PLUS`

```java
QueryOptions requestPlus = queryOptions()
    .scanConsistency(QueryScanConsistency.REQUEST_PLUS);
```

`REQUEST_PLUS` yêu cầu index liên quan đáp ứng mốc consistency của query trước khi trả kết quả tương ứng. Vì có thể phải chờ index, mode này có thể tăng thời gian chờ hoặc timeout khi index backlog.

Nó **không**:

- Mở transaction nhiều document.
- Tăng durability cho mutation trước đó.
- Ngăn một writer khác cập nhật cùng document.
- Tạo snapshot không đổi cho nhiều HTTP requests.
- Bảo đảm query nhanh hoặc luôn trả row khi predicate không khớp/TTL đã hết hạn.

Trong fixture không có race, sau insert đã xác nhận và điều kiện query đúng, một query REQUEST_PLUS hoàn thành bình thường được kỳ vọng thấy mutation.

## 11. Mode 3 — `AT_PLUS` với mutation token

Sau KV `insert`/`replace`, SDK có thể trả `MutationResult` chứa mutation token. Từ đó:

```java
import com.couchbase.client.java.query.MutationState;
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

MutationState state = MutationState.from(mutationResult);
QueryOptions atPlus = queryOptions().consistentWith(state);
```

Đây là cách ràng buộc query với mutation cụ thể. `consistentWith` không cần `REQUEST_PLUS` cùng lúc; hãy dùng **QueryOptions mới** cho mỗi mode.

### 11.1. Token không khả dụng

Tùy SDK/Server config, mutation token có thể thiếu:

```java
if (mutationResult.mutationToken().isEmpty()) {
    throw new IllegalStateException(
        "Mutation token unavailable; AT_PLUS not run"
    );
}
```

Trong báo cáo, ghi `AT_PLUS: NOT_RUN` và lý do khi không có token. **Không** dùng CAS hoặc thời điểm hiện tại để tự chế token; không thay bằng REQUEST_PLUS rồi gắn nhãn AT_PLUS.

### 11.2. AT_PLUS và REQUEST_PLUS khác phạm vi

Mutation state mô tả các mutation được chỉ định mà query cần thấy. `REQUEST_PLUS` có yêu cầu index freshness theo mốc query; giữa hai mode có thể khác mức chờ khi có nhiều writes khác trên cluster. Không khẳng định AT_PLUS **luôn** nhanh hơn; cần đo với query plan/load tương đương.

## 12. Dùng một SQL++ và named parameters cho mọi mode

Java SDK 3.x, với `Cluster` và `QueryOptions`:

```java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import reactor.core.publisher.Flux;

private static final String SELECT_SQL = """
    SELECT META(d).id AS documentId,
           d.run_id AS runId,
           d.generation AS generation
    FROM `training`.`consistency_lab`.`documents` AS d
    WHERE d.tenant_id = $tenantId
      AND d.status = $status
      AND d.run_id = $runId
    """;

public Flux<JsonObject> queryByRunId(
        Cluster cluster,
        String tenantId,
        String runId,
        QueryOptions options) {

    options.parameters(
        JsonObject.create()
            .put("tenantId", tenantId)
            .put("status", "ACTIVE")
            .put("runId", runId)
    );

    return cluster.reactive()
        .query(SELECT_SQL, options)
        .flatMapMany(result -> result.rowsAsObject());
}
```

**Lưu ý phiên bản:** Đây là dạng API của SDK Java 3.x, phải đối chiếu imports/signatures với dependency thực tế. `QueryOptions` nên được tạo **mới cho từng query**, không dùng chung một instance mutable giữa các requests hoặc giữa nhiều subscriptions đồng thời.

Không nối chuỗi SQL++ từ `runId`/tenant do client gửi. Named parameters tránh lỗi escaping và giảm nguy cơ injection. Bucket/scope/collection phải được kiểm soát phía server, không cho client tự chọn ngoài quyền.

## 13. Ghi lại quan sát mỗi lần query

Một record tối thiểu:

```java
public record Observation(
    String mode,
    int rowCount,
    boolean sawGenerationOne,
    long clientElapsedMillis
) {}
```

Helper:

```java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.query.QueryOptions;
import java.util.concurrent.TimeUnit;
import reactor.core.publisher.Mono;

public Mono<Observation> observe(
        Cluster cluster,
        String tenantId,
        String runId,
        String mode,
        QueryOptions options) {

    return Mono.defer(() -> {
        long startedAt = System.nanoTime();

        return queryByRunId(cluster, tenantId, runId, options)
            .collectList()
            .map(rows -> new Observation(
                mode,
                rows.size(),
                rows.stream().anyMatch(
                    row -> runId.equals(row.getString("runId"))
                        && Integer.valueOf(1).equals(
                            row.getInt("generation")
                        )
                ),
                TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - startedAt
                )
            ));
    });
}
```

`Mono.defer` bắt đầu đồng hồ **khi có subscription**, không phải lúc tạo biến. `collectList` chỉ phù hợp vì `run_id` mỗi trial là duy nhất và dự kiến 0–1 row; không áp dụng nguyên mẫu cho một query production có thể trả hàng triệu row.

**Diễn giải số đo:**

- `clientElapsedMillis` bao gồm scheduling, SDK, network, Query Service và decode; **không phải server execution time thuần**.
- `rowCount > 1` là dấu hiệu test fixture/predicate có vấn đề; không che bằng `take(1)`.
- Lỗi phải được phát xuống test/report, không chuyển bằng `onErrorResume(error -> Mono.just(emptyObservation))`.
- Không có row khác hẳn query timeout hoặc permission error.

## 14. Thực hiện ba mode từ cùng mutation

Kết hợp các helper trên trong một class `ConsistencyLab` đã inject `Cluster` và `Collection`. Cấu trúc Java SDK 3.x minh họa:

```java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.MutationState;
import com.couchbase.client.java.query.QueryScanConsistency;
import reactor.core.publisher.Mono;

import static com.couchbase.client.java.query.QueryOptions.queryOptions;

public record Trial(
    String documentId,
    String runId,
    Observation notBounded,
    Observation atPlus,
    Observation requestPlus
) {}

public Mono<Trial> runTrial(
        Cluster cluster,
        Collection collection,
        String tenantId,
        String runId) {

    String documentId =
        "consistency::" + tenantId + "::" + runId;

    JsonObject doc = JsonObject.create()
        .put("tenant_id", tenantId)
        .put("run_id", runId)
        .put("status", "ACTIVE")
        .put("generation", 1)
        .put("payload", "consistency-demo");

    return collection.reactive()
        .insert(documentId, doc)
        .flatMap(mutation -> {
            if (mutation.mutationToken().isEmpty()) {
                return Mono.error(new IllegalStateException(
                    "Mutation token missing; cannot claim AT_PLUS"
                ));
            }

            MutationState state = MutationState.from(mutation);

            return observe(
                    cluster, tenantId, runId,
                    "NOT_BOUNDED",
                    queryOptions().scanConsistency(
                        QueryScanConsistency.NOT_BOUNDED
                    )
                )
                .flatMap(notBounded ->
                    observe(
                        cluster, tenantId, runId,
                        "AT_PLUS",
                        queryOptions().consistentWith(state)
                    )
                    .flatMap(atPlus ->
                        observe(
                            cluster, tenantId, runId,
                            "REQUEST_PLUS",
                            queryOptions().scanConsistency(
                                QueryScanConsistency.REQUEST_PLUS
                            )
                        )
                        .map(plus -> new Trial(
                            documentId, runId,
                            notBounded, atPlus, plus
                        ))
                    )
                );
        });
}
```

**Code ví dụ là một đoạn class, không phải ứng dụng hoàn chỉnh**: cần gom `SELECT_SQL`, `queryByRunId` và `observe` vào cùng component, cấu hình cluster/collection test, exception handling, transaction scope nếu có và dependency đúng release.

### 14.1. Tại sao một mutation chứ không phải ba?

Nếu chạy ba `insert` độc lập cùng ID, hai lệnh sau sẽ gặp duplicate. Nếu dùng ID khác cho mỗi mode trong cùng một phép đo mà không kiểm soát biến, dữ liệu/index state không còn tương đương. Thiết kế trên tạo **một mutation** rồi chạy ba queries với cùng `runId`.

### 14.2. Tại sao NOT_BOUNDED chạy trước?

Thử `NOT_BOUNDED` ngay sau insert làm tăng cơ hội quan sát secondary-index lag. Sau `AT_PLUS` hoặc `REQUEST_PLUS`, index có thể đã tiến thêm, khiến một phép thử mặc định ở cuối dễ thấy document.

**Cảnh báo về tính công bằng:** Ba queries được thực hiện tại các thời điểm khác nhau; một trial không đủ để kết luận mode nào nhanh hơn. Muốn nghiên cứu latency, chạy nhiều trial độc lập với run ID mới, đổi thứ tự có kiểm soát và ghi thời điểm/load.

### 14.3. Thiếu mutation token thì làm gì?

Code trả lỗi rõ vì trial yêu cầu đủ ba mode. Một harness hoàn thiện có thể ghi:

```text
NOT_BOUNDED:  RUN
AT_PLUS:      NOT_RUN (mutation token unavailable)
REQUEST_PLUS: RUN
```

Không được báo một query `NOT_BOUNDED` tình cờ thấy row là “AT_PLUS PASS”. Việc có token là **điều kiện thực nghiệm**, không phải điều có thể giả lập bằng `MutationState` rỗng.

## 15. Chạy nhiều trial không gây tải lớn

Ví dụ service `lab` wrapper có method `runTrial(tenantId,runId)`:

```java
import java.util.UUID;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

String batchId = UUID.randomUUID().toString();

Mono<java.util.List<Trial>> experiment = Flux.range(1, 20)
    .concatMap(i -> lab.runTrial(
        "lab-tenant-a",
        batchId + "-trial-" + i
    ))
    .collectList();
```

`concatMap` giúp chạy các trial **tuần tự**. Số lượng 20 document nhỏ đủ cho bài đầu tiên; tăng concurrency là **một biến khác** và phải được ghi rõ khi thử tải riêng.

Không thêm `Thread.sleep` giữa insert và query: nó thay đổi cơ hội index bắt kịp và có thể khiến lab không còn kiểm tra “đọc ngay sau ghi”. Không tự `subscribe()` nhiều lần vào cùng publisher `insert`.

## 16. `StepVerifier`: assert bảo đảm, không assert tình cờ

Một integration test khi có index ONLINE, query đúng, mutation token và TTL hợp lệ:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

@Test
void requestPlusAndAtPlusObserveOwnWrite() {
    String runId = "trial-" + UUID.randomUUID();

    StepVerifier.create(
            lab.runTrial("lab-tenant-a", runId)
        )
        .assertNext(trial -> {
            assertThat(trial.atPlus().sawGenerationOne())
                .isTrue();
            assertThat(trial.requestPlus().sawGenerationOne())
                .isTrue();
            assertThat(trial.notBounded().rowCount())
                .isBetween(0, 1);
        })
        .verifyComplete();
}
```

**Tại sao `NOT_BOUNDED` không bị buộc = 0?** Vì nó cho phép dùng trạng thái index hiện có, không bắt buộc query phải stale. Một lần thực nghiệm thấy dữ liệu ngay là hoàn toàn hợp lệ.

### 16.1. Test KV riêng

```java
StepVerifier.create(
        collection.reactive().insert(key, body)
            .then(collection.reactive().get(key))
            .map(result -> result.contentAsObject()
                .getString("run_id"))
    )
    .expectNext(expectedRunId)
    .verifyComplete();
```

`key` là ID mới; `body` có `run_id=expectedRunId`. Test trên chỉ kiểm tra KV path, không chứng minh SQL++ secondary-index visibility.

### 16.2. Test không thể chạy AT_PLUS

Nếu SDK không trả mutation token, test phải báo **SKIPPED/NOT_RUN có lý do cụ thể** hoặc fail setup đúng chính sách. Không sửa assertion thành REQUEST_PLUS rồi khẳng định đó là AT_PLUS.

## 17. Bảng mẫu để ghi số liệu

| Trial | Operation/mode | KV đã xác nhận? | SQL++ thấy generation 1? | Row count | Latency client (ms) | Lỗi/ghi chú |
| --- | --- | --- | --- | --- | --- | --- |
| 001 | KV get | ... | Không áp dụng | ... | ... | ... |
| 001 | NOT_BOUNDED | ... | ... | ... | ... | ... |
| 001 | AT_PLUS | ... | ... | ... | ... | ... |
| 001 | REQUEST_PLUS | ... | ... | ... | ... | ... |
| 002 | KV get | ... | Không áp dụng | ... | ... | ... |
| 002 | NOT_BOUNDED | ... | ... | ... | ... | ... |
| 002 | AT_PLUS | ... | ... | ... | ... | ... |
| 002 | REQUEST_PLUS | ... | ... | ... | ... | ... |

Không điền số liệu giả vào bảng. Khi timeout/exception, để một dòng lỗi rõ ràng, không nhập `rowCount=0` như thể query hoàn tất rỗng.

### 17.1. Thống kê sau nhiều trial

Gợi ý tính:

- Tỉ lệ `NOT_BOUNDED` thấy row trong N trial **trong điều kiện đã đo**.
- Median và p95 latency của từng mode.
- Số query timeout/lỗi.
- Số mutation token unavailable.
- Số trường hợp index/plan không đúng fixture.
- Chênh lệch giữa client latency và Server query metrics khi có.

Kết luận “`NOT_BOUNDED` 20/20 thấy row” **không** được viết lại thành “`NOT_BOUNDED` đảm bảo read-your-own-write”.

## 18. Vì sao index lag có thể không tái hiện được?

Các nguyên nhân hợp lý:

1. Index Service cập nhật nhanh.
2. Khoảng thời gian từ response insert tới query đủ để index catch up.
3. Cluster test ít dữ liệu và nhẹ tải.
4. Query được lập kế hoạch theo đường truy cập khác dự kiến.
5. Một lần query consistency mạnh đã làm index tiến lên trước phép đo khác.
6. Code vô tình đo document cũ hoặc trùng `run_id`.
7. Query có một predicate chưa cần index như `USE KEYS`.
8. Chỉ kiểm tra row tồn tại, không kiểm tra bản `generation` vừa update.

Phản ứng đúng: ghi kết quả, kiểm tra `EXPLAIN`/mutation tokens/elapsed time/fixture. **Không** gây tải phá hoại lên môi trường chung để ép một stale read.

## 19. Thí nghiệm update: nhìn thấy row chưa chắc thấy giá trị mới

Với document đã tồn tại:

1. Insert `generation=1`, `status=ACTIVE`, đợi baseline index nhất quán.
2. Dùng KV `replace` hoặc mutation có điều kiện đổi `generation=2`.
3. Ghi `MutationResult` của **update**, không chỉ của insert.
4. Dùng KV get xác nhận `generation=2`.
5. Chạy ba query modes với **predicate ổn định** và select `generation`.
6. So sánh giá trị 1/2, không chỉ `rowCount`.

SDK update mẫu, trên **test collection**:

```java
JsonObject updated = JsonObject.create()
    .put("tenant_id", tenantId)
    .put("run_id", runId)
    .put("status", "ACTIVE")
    .put("generation", 2)
    .put("payload", "update-trial");

Mono<?> update = collection.reactive()
    .replace(documentId, updated);
```

Trong code đo thực tế, **giữ lại `MutationResult` của replace** để làm `MutationState`. Không dùng một `Mono<Void>` đã loại bỏ kết quả nếu mục tiêu là AT_PLUS. Nếu có concurrent writers, dùng CAS/`@Version`/conditional replace phù hợp, không overwrite mù quáng.

### 19.1. Cẩn thận với query plan và projection

Một index covering và một query có Fetch document có thể có behavior quan sát version khác nhau do thời điểm index/fetch. Khi viết báo cáo, ghi index plan và field `generation` thực tế. Không tự hứa mọi trường hợp `NOT_BOUNDED` sẽ trả version 1 trước version 2.

### 19.2. Không đổi cả predicate khi muốn đo version

Nếu bạn đổi `status=ACTIVE` sang `SUSPENDED`, một query `WHERE status='ACTIVE'` trả **0 row** có thể là kết quả đúng khi index đã bắt kịp, không phải mất document. Dùng điều kiện ổn định `tenant_id + run_id` và select `status/generation` cho bài kiểm tra state; query theo ACTIVE membership là một phép đo **riêng**.
## 20. Những khái niệm khác không được nhầm với scan consistency

### 20.1. Durability — mutation được xác nhận ở đâu?

Durability trả lời câu hỏi **mức xác nhận lưu trữ/replica** của mutation theo option và cluster hỗ trợ. Chọn durability mạnh hơn không làm secondary index nhất thiết cập nhật trước khi KV mutation trả kết quả.

| Câu hỏi | Cơ chế liên quan |
| --- | --- |
| KV mutation đã được xác nhận theo mức durable nào? | KV durability option. |
| SQL++ theo field đã thấy mutation chưa? | Query scan consistency và index. |
| Có writer khác overwrite document không? | CAS/optimistic locking. |
| Hai document có cùng commit hoặc cùng rollback? | Transaction API. |
| Document đã hết hạn chưa? | TTL/expiration. |

Nếu muốn đo durability, hãy tạo **thí nghiệm riêng** và giữ các yếu tố khác không đổi. Đừng thay đồng thời durability và query mode rồi khẳng định độ trễ khác nhau chỉ vì `REQUEST_PLUS`.

### 20.2. CAS — bảo vệ cạnh tranh, không làm index mạnh hơn

`@Version`/CAS giúp phát hiện một writer dùng version cũ khi thay đổi cùng document. CAS từ KV mutation **không phải mutation token cho AT_PLUS**. Một phép read-after-write KV ổn định không có nghĩa hai request cập nhật liên tiếp sẽ không mất dữ liệu nếu không có CAS/điều kiện mutation.

### 20.3. Replica reads — không dùng làm baseline

`getAnyReplica`/`getAllReplicas` có thể đọc bản sao với freshness khác active path. Bài này dùng **KV get thường** để tránh trộn thêm yếu tố replica lag. Nếu nghiên cứu replica consistency, ghi rõ API và tách thành bài thử mới.

## 21. TTL và expiration: nguồn sai lệch khi thử nghiệm

Một document TTL 1 giây có thể đã hết hạn trong khi `REQUEST_PLUS` đang đợi index. Khi đó query trả empty **không chứng minh** mức nhất quán không hoạt động: có thể document không còn hợp lệ ở thời điểm query.

Quy tắc cho baseline:

- Không đặt TTL, hoặc dùng expiry đủ dài để test/query/report hoàn tất.
- Không chạy cleanup cùng lúc với read measurements.
- Không tái sử dụng ID và run ID.
- Khi update, kiểm tra mutation option có giữ hay thay TTL theo SDK version.
- Nếu cần mô phỏng expiration, chạy một trial riêng được gắn nhãn rõ, không trộn vào kết quả index visibility.

TTL, CAS và consistency là **ba chiều độc lập**. Một document hết hạn, một query chưa thấy index entry và một update CAS conflict phải được phân loại khác nhau.

## 22. Transaction: nhất quán của query không tạo tính nguyên tử

Giả sử cần trừ 50 điểm A, cộng 50 điểm B và ghi ledger. Cách viết:

```java
Mono<Void> workflow = repository.save(accountA)
    .then(repository.save(accountB))
    .then();
```

**Không phải transaction**. Nếu A đã ghi nhưng B lỗi, A có thể vẫn bị trừ điểm. Dùng `REQUEST_PLUS` cho query sau đó không rollback A và không làm ledger tự xuất hiện.

Nếu cần nguyên tử nhiều documents, dùng **Couchbase SDK transaction API hoặc Spring transaction infrastructure thật sự hỗ trợ resource đang dùng** theo version. Trong transaction callback, mọi operation phải tham gia attempt context; một `cluster.reactive().query(...)` bình thường không được mặc định tham gia giao dịch SDK chỉ vì gọi ở cùng block Java.

### 22.1. Query sau commit

Sau transaction được xác nhận commit, một SQL++ query **ngoài transaction** theo secondary index vẫn cần mức scan consistency phù hợp với yêu cầu hiển thị. Một query tạm thời chưa thấy ledger **không tự chứng minh transaction rollback**; trước tiên hãy kiểm tra transaction result, KV ID, TTL, namespace và query/index.

### 22.2. Timeout khi commit không đồng nghĩa abort

Nếu caller timeout đúng lúc commit, outcome có thể chưa rõ. Cần idempotency/ledger và reconciliation thay vì bắt đầu transaction mới với command ID khác. Scan consistency mạnh không thay quy trình xác minh này.

## 23. Deadline, retry và cancellation trong thí nghiệm

`REQUEST_PLUS` và `AT_PLUS` có thể phải đợi index. Nếu index backlog, query có thể timeout và SDK/Reactor phát lỗi. Đó là **kết quả cần ghi lại**, không phải lý do tự biến thành row count bằng 0.

Ví dụ:

```java
Mono<Observation> timed = observe(
        cluster, tenantId, runId,
        "REQUEST_PLUS",
        queryOptions().scanConsistency(
            QueryScanConsistency.REQUEST_PLUS
        )
    )
    .timeout(java.time.Duration.ofSeconds(5));
```

`Mono.timeout` chỉ giới hạn thời gian chờ ở ranh giới Reactor; cần query options/timeout của SDK/Query Service tương ứng nếu muốn giới hạn công việc backend theo đúng API/version.

### 23.1. Không retry vô hạn một query đang chờ index

Sai:

```java
// Anti-pattern: index backlog có thể khiến retry storm.
observe(cluster, tenantId, runId, "REQUEST_PLUS", options)
    .retry(100);
```

Khi phải retry lỗi tạm thời, đặt **retry budget + backoff/jitter + deadline tổng**, giới hạn số queries in-flight và quan sát Query Service. Không retry validation, syntax, permission hoặc thiếu index bằng cách lặp y nguyên câu query.

### 23.2. Cancellation chỉ là tín hiệu tới upstream

Khi client đóng tab hoặc test `thenCancel()`, Reactor có thể hủy subscription. Nhưng SDK/Server có thể đã xử lý một phần query; với mutation, cancellation **không bảo đảm rollback**. Không dùng `doFinally(CANCEL)` làm bằng chứng chưa ghi. Trong lab, giữ danh sách ID và xác minh state cuối bằng KV sau sự cố.

### 23.3. Error khác empty

`Mono.empty()`/`Flux.empty()` là completion không có item. `onError` là lỗi. Không dùng:

```java
// Sai: biến timeout/permission/index error thành "chưa thấy document".
queryFlux.onErrorResume(error -> Flux.empty());
```

Nếu cần báo cáo, phân loại `NOT_FOUND`, `QUERY_ERROR`, `TIMEOUT`, `TOKEN_UNAVAILABLE` và `NOT_RUN` riêng.

## 24. Giải thích kết quả và xác minh index

Khi trial cho thấy KV get có document nhưng SQL++ NOT_BOUNDED không thấy, hãy đi lần lượt:

1. **KV:** đúng document key, đúng namespace, đúng `run_id`/`status`/`generation`?
2. **SQL++:** statement và named parameters đúng giá trị không?
3. **Index:** trạng thái ONLINE và `EXPLAIN` có dùng secondary index kỳ vọng không?
4. **TTL/race:** document có thể hết hạn, bị cập nhật/xóa bởi worker khác không?
5. **Consistency:** `REQUEST_PLUS`/`AT_PLUS` có hoàn thành bình thường và thấy mutation không?
6. **Metric:** Query latency, index scan/fetch và SDK tracing có ủng hộ giả thuyết không?
7. **Thời điểm:** ba queries chạy lúc nào; có query consistency mạnh trước đó không?

Nếu mọi điều kiện được giữ và query mạnh thấy mutation mà NOT_BOUNDED vừa trước đó không thấy, đây là bằng chứng **phù hợp với index lag** tại thời điểm truy vấn. Tuy nhiên, không suy ra một con số cố định “Couchbase index chậm N ms trong mọi trường hợp”.

### 24.1. Một query trả 0 row không tự là kết quả lỗi

Với `runId` không tồn tại hoặc `status` không phù hợp, REQUEST_PLUS cũng có thể trả 0 row hợp lệ. Consistency mode không thay predicate, quyền tenant, dữ liệu JSON hay loại field.

### 24.2. Index scan cost không chỉ do consistency

Một SQL++ có `LIMIT 1` vẫn có thể tốn CPU nếu predicate/index kém. `REQUEST_PLUS` có thể đợi index; sau khi đợi xong, query vẫn có thể scan/sort nhiều candidate. Kết luận hiệu năng cần cả **index plan và query metrics**, không chỉ số rows trả về.

## 25. Bài thực hành mở rộng: hai HTTP requests WebFlux

Một tình huống ứng dụng thực:

```text
POST /customers
    -> save thành công
    -> trả customer ID

GET /customers?status=ACTIVE
    -> SQL++ query theo secondary index
    -> hiển thị danh sách
```

Hai HTTP requests không chia sẻ cùng một subscription. Nếu `repository.save` chỉ trả entity, request GET sau đó có thể **không có mutation token** để tự áp `consistentWith(MutationState)`.

Các giải pháp cần cân nhắc:

- Để màn hình chi tiết đọc bằng KV ID hoặc dùng response từ POST.
- Chấp nhận `NOT_BOUNDED` với danh sách nếu UX cho phép eventual consistency ngắn.
- Dùng `REQUEST_PLUS` cho danh sách buộc thấy mutation tới mốc query, với deadline và chi phí được chấp nhận.
- Xây một contract truyền **consistency token** đã xác thực/bảo vệ, khi framework/API thực sự hỗ trợ; không để client tự tạo token từ CAS hay timestamp.
- Với workflow quan trọng, dùng job/result state và idempotency thay vì phụ thuộc frontend có nhận lại row ngay ở query sau hay không.

**Bảo mật:** Query consistency không thay xác thực/ủy quyền. `tenantId` phải đến từ security context đáng tin cậy và được bind vào SQL++, không nhận như quyền tự khai từ client.

## 26. Phân trang và list query: thêm một yêu cầu khác

Nếu màn hình cần 20 khách hàng ACTIVE, phải thiết kế server-side query có thứ tự và giới hạn:

```sql
SELECT META(d).id AS documentId,
       d.run_id AS runId,
       d.generation AS generation
FROM `training`.`consistency_lab`.`documents` AS d
WHERE d.tenant_id = $tenantId
  AND d.status = "ACTIVE"
ORDER BY d.run_id ASC
LIMIT 20;
```

Với dataset lớn, cân nhắc keyset pagination thay `OFFSET` sâu; đảm bảo khóa sort ổn định, có tie-breaker khi không unique, và index hỗ trợ order.

**Giữ riêng hai trục:**

- Consistency quyết định query phải đợi index tới mức nào.
- Pagination/order quyết định lấy những row nào, thứ tự nào và chi phí scan/sort.

`take(20)` ở Reactor không thay SQL++ `LIMIT 20`, còn `REQUEST_PLUS` không tạo snapshot bất biến giữa các trang HTTP. TTL/insert/update/delete giữa requests vẫn có thể thay danh sách.

## 27. Cleanup chỉ theo ID do lab tạo

Sau khi đã ghi kết quả, dọn **đúng các ID** được trial tạo:

```java
import reactor.core.publisher.Flux;

Flux<Void> cleanup = Flux.fromIterable(createdIds)
    .concatMap(id ->
        collection.reactive()
            .remove(id)
            .then()
    );
```

Đây là pipeline cleanup, phải có subscription do test runner sở hữu. `createdIds` do lab lưu lại sau mỗi insert; không dùng wildcard hoặc xóa toàn bộ collection chỉ vì muốn “dọn nhanh”.

Nếu document đã expire hoặc đã bị xóa, xử lý lỗi not-found theo **chính sách cleanup riêng**; không áp `onErrorComplete()` rộng cho các mutation nghiệp vụ. Cũng không cleanup trước khi query trials hoàn tất vì như vậy làm kết quả read-after-write không còn kiểm soát.

### 27.1. Những việc không được làm

- Không xóa cả bucket/scope/collection chung.
- Không chạy `DELETE FROM collection` không có `WHERE` trên môi trường chia sẻ.
- Không xóa ngay khi đang đo Query Service.
- Không tái dùng ID của dữ liệu do người khác sở hữu.
- Không coi cleanup là rollback của một transaction nghiệp vụ.

## 28. Bảng chẩn đoán lỗi thực hành

| Triệu chứng | Nguyên nhân có thể | Bước kiểm tra |
| --- | --- | --- |
| KV get không thấy sau insert | Sai ID/namespace, read replica, TTL, write chưa success | Trạng thái mutation, active KV get, ID, namespace. |
| NOT_BOUNDED thấy ngay mọi trial | Index nhanh, độ trễ giữa write/query | Chấp nhận kết quả, ghi plan/load, không ép stale. |
| REQUEST_PLUS timeout | Index backlog, Query Service quá tải, deadline ngắn | Query/Index metrics, query timeout options. |
| AT_PLUS không chạy | Không có mutation token từ SDK | Kiểm tra `mutationToken`, SDK/cluster support. |
| SQL++ không trả row ở cả ba modes | Sai predicate, type JSON, index, TTL, keyspace | KV JSON, named params, `EXPLAIN`. |
| SQL++ trả nhiều row | `run_id` không unique, query thiếu filter | Kiểm tra fixture và bind params. |
| SQL++ trả generation cũ | Query/index/fetch timing, update không được xác nhận | KV generation, mutation result, plan, consistency. |
| REQUEST_PLUS rỗng sau status đổi | Predicate loại document khỏi tập | Dùng predicate ổn định và select status/generation. |
| `repository.findById` lỗi mapping | SDK JSON thiếu Spring discriminator/converter | Tách test SDK direct và repository-created fixture. |
| CAS conflict | Concurrent writer sửa document | Re-read và business conflict policy. |
| Query chậm dù trả một row | Index scan/fetch/sort lớn hoặc chờ consistency | `EXPLAIN`, Query Service metrics. |
| Retry làm chậm toàn cluster | Attempts tăng khi query đang chờ index | Bounded retry/admission và deadline. |

## 29. Bài tập vận dụng kèm đáp án

### Bài A — KV thấy, NOT_BOUNDED chưa thấy

Một insert đã được xác nhận và KV get trả đúng JSON. SQL++ `NOT_BOUNDED` theo `tenant_id/status/run_id` trả 0 row. Nêu ít nhất bốn điều cần kiểm tra.

**Đáp án:** Namespace/keyspace, named parameters, index ONLINE/`EXPLAIN`, TTL/race, và query consistency. Nếu mọi điều kiện đúng, thử REQUEST_PLUS/AT_PLUS để kiểm tra khả năng index lag.

### Bài B — NOT_BOUNDED thấy 20/20 trial

Có được viết “NOT_BOUNDED bảo đảm read-your-own-write” không?

**Đáp án:** Không. Đây là **quan sát trong môi trường thử nghiệm**, không thay đổi guarantee của mode.

### Bài C — Nguồn AT_PLUS

`repository.save(entity)` trả entity. Có thể lấy `@Version` làm mutation state không?

**Đáp án:** Không. CAS/version khác mutation token. Cần SDK operation trả `MutationResult`/token hoặc một API adapter hợp lệ; nếu không, AT_PLUS không chạy và phải báo rõ.

### Bài D — Token không khả dụng

SDK mutation thành công nhưng `mutationToken()` rỗng. Có nên ghi kết quả REQUEST_PLUS dưới nhãn AT_PLUS?

**Đáp án:** Không. Đánh dấu `NOT_RUN` cho AT_PLUS; sửa setup/API nếu muốn chạy chế độ này.

### Bài E — Update generation

Trước update document là generation 1; sau update KV là generation 2. SQL++ trả một row generation 1. Có xem read-your-own-update thành công chưa?

**Đáp án:** Chưa. Test update phải xác minh **giá trị mới**, không chỉ sự tồn tại của row.

### Bài F — Trạng thái đổi

Status đổi ACTIVE → SUSPENDED. Query `WHERE status='ACTIVE'` dưới REQUEST_PLUS trả 0 row. Có chứng minh consistency lỗi không?

**Đáp án:** Không; đó có thể là kết quả đúng. Query bằng predicate ổn định và lấy status/generation.

### Bài G — KV durability

Durability mạnh hơn có làm secondary index tự động cập nhật trước khi write trả success không?

**Đáp án:** Không mặc định. Durability và Query Service index visibility là hai chính sách khác nhau.

### Bài H — Transaction

`Mono.when(saveA, saveB)` và một query REQUEST_PLUS có bảo đảm cả A/B cùng commit không?

**Đáp án:** Không. Phải dùng transaction API phù hợp khi cần all-or-nothing; REQUEST_PLUS không rollback.

### Bài I — TTL

Document test TTL 1 giây, query REQUEST_PLUS đợi lâu rồi trả empty. Kết luận index lag có đúng chưa?

**Đáp án:** Chưa. Document có thể hết hạn; tách expiration thành bài riêng.

### Bài J — REQUEST_PLUS latency

Một trial REQUEST_PLUS nhanh hơn NOT_BOUNDED. Có mâu thuẫn với guarantee không?

**Đáp án:** Không. Latency có nhiều nguồn noise; REQUEST_PLUS có khả năng phải chờ index nhưng không nhất thiết chậm hơn **trong từng phép đo**.

### Bài K — `USE KEYS`

Một developer đổi query sang `USE KEYS $id` để “dễ thấy ngay”. Lab còn kiểm tra secondary-index consistency như ban đầu không?

**Đáp án:** Không; query có thể dùng key-based access. Giữ predicate indexed fields và kiểm tra plan.

### Bài L — Bảo mật tenant

Client gửi `tenantId=another-tenant`. Nếu dùng REQUEST_PLUS có chặn lộ dữ liệu khác tenant không?

**Đáp án:** Không. Consistency không cấp quyền. Tenant phải lấy từ security context và kiểm tra ACL.

### Bài M — Retry query chậm

Index backlog, REQUEST_PLUS timeout. Retry 100 lần không backoff có tốt không?

**Đáp án:** Không. Có thể tạo retry storm; cần tối ưu index/tải, deadline và retry hữu hạn theo loại lỗi.

### Bài N — Đánh giá thí nghiệm

Ba mode được chạy tuần tự từ một insert. Có thể coi chênh lệch latency chỉ do mode?

**Đáp án:** Không. Thời điểm và thứ tự cũng thay đổi index state; cần nhiều trial độc lập và control variables.

### Bài O — Quyết định UX

Trang chi tiết sau POST và trang list lọc status cần consistency giống nhau không?

**Đáp án:** Không nhất thiết. Trang chi tiết có thể dùng write result/KV get; list có thể chấp nhận NOT_BOUNDED hoặc yêu cầu REQUEST_PLUS/AT_PLUS tùy nghiệp vụ.

## 30. Rubric tự đánh giá

| Tiêu chí | Đạt | Chưa đạt |
| --- | --- | --- |
| Môi trường | Namespace test riêng, index ONLINE | Đụng production hoặc index không kiểm tra. |
| Baseline KV | Insert → KV get có thứ tự trong cùng subscription | Hai `subscribe()` độc lập. |
| Query | SQL++ theo indexed fields, bind tham số, `EXPLAIN` | `USE KEYS` rồi gọi là index lag. |
| Modes | Phân biệt rõ NOT_BOUNDED, REQUEST_PLUS, AT_PLUS | Trộn options/token hoặc giả AT_PLUS. |
| Assertions | Mode mạnh nhìn thấy own mutation; NOT_BOUNDED linh hoạt | Buộc NOT_BOUNDED luôn stale. |
| Update | Kiểm tra generation mới và predicate đúng | Chỉ đếm row. |
| Đo lường | Ghi version, latency, row count, lỗi, plan | Chỉ nói PASS/FAIL. |
| Đúng đắn | Tách TTL, CAS, durability, transaction | Dùng consistency thay CAS/transaction. |
| An toàn | Chạy tải giới hạn, cleanup theo ID | Thử phá index hay xóa rộng. |
| Giải thích | Nêu KV path khác secondary-index SQL++ | Kết luận “Couchbase mất dữ liệu” không có bằng chứng. |

## 31. Checklist hoàn thành

- [ ] Dùng namespace test, không dùng production.
- [ ] Index đã được tạo và ONLINE; `EXPLAIN` được kiểm tra.
- [ ] Mỗi trial có `run_id`/document ID duy nhất.
- [ ] Insert success, KV get thấy đúng document.
- [ ] SQL++ WHERE theo indexed fields, không `USE KEYS`.
- [ ] Các mode dùng cùng statement, named params và dataset.
- [ ] NOT_BOUNDED được đánh giá theo quan sát, không ép stale.
- [ ] REQUEST_PLUS có assertion đúng khi hoàn thành thành công.
- [ ] AT_PLUS dùng token thật hoặc báo NOT_RUN nếu thiếu.
- [ ] Có kiểm tra `generation` khi update.
- [ ] Có lưu latency, rowCount, error, version, index plan.
- [ ] Không gộp timeout vào rowCount=0.
- [ ] Không tự `subscribe()`/`block()` trong service reactive.
- [ ] TTL/CAS/durability/transaction được phân biệt rõ.
- [ ] Có chính sách read-your-own-write theo từng endpoint.
- [ ] Có retry budget/deadline và không tạo tải vô hạn.
- [ ] Cleanup đúng những IDs do lab tạo.
- [ ] Kết luận bám dữ liệu, không hứa guarantee từ một thử nghiệm may mắn.

## 32. Ghi nhớ

**Đọc sau ghi trong Couchbase phải được xác định theo đường đọc.** KV get thông thường theo ID qua active path, sau một write đã xác nhận và không có race/TTL, có thể thấy trạng thái vừa ghi mà không cần secondary index. SQL++ theo field lại phụ thuộc Query Service/index: **`NOT_BOUNDED`** không đợi một mutation vừa ghi, **`REQUEST_PLUS`** yêu cầu mức mới của index tại mốc query, còn **`consistentWith(MutationState)`/AT_PLUS** dựa vào mutation token để ràng buộc với mutation được chỉ định.

Một bài thực hành tốt **không cố chứng minh NOT_BOUNDED luôn stale hoặc REQUEST_PLUS luôn chậm**. Hãy ghi rõ **statement thật, index plan, run ID, generation, mutation token, client/server latency và lỗi**. Khi đưa vào ứng dụng **Spring Data Couchbase**, chọn KV/SQL++ và scan consistency theo yêu cầu nghiệp vụ, đồng thời tách bạch **CAS, durability, TTL, transaction, idempotency và quyền tenant**. Đảm bảo publisher được compose trong cùng subscription và không biến các kết quả quan sát tình cờ thành cam kết mà framework hay SDK không cung cấp.
