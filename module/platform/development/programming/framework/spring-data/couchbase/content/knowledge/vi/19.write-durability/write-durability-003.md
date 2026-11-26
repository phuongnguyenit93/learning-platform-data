# Cấu hình độ bền trên entity và cho từng thao tác trong Spring Data Couchbase

> **Chương:** Độ bền ghi  
> **Học phần:** `SPRING_DATA_COUCHBASE` — xây dựng tầng truy cập Couchbase bằng document mapping, repository, `CouchbaseTemplate` và SQL++; vận dụng thiết kế bucket/scope/collection, TTL, CAS, giao dịch và API reactive để bảo đảm hiệu năng, nhất quán và khả năng vận hành.

## 1. Mục tiêu bài học

Sau bài này, người học có thể:

1. Xác định ba nơi ảnh hưởng đến durability của một ghi: **annotation trên entity**, **tùy chọn của từng mutation** và **minimum durability của bucket**.
2. Khai báo `@Document(durabilityLevel = ...)`, `@Durability` và `durabilityExpression` trong Spring Data Couchbase.
3. Dùng fluent API `CouchbaseTemplate.withDurability(...)` để đặt mức khác cho một thao tác riêng.
4. Dùng `InsertOptions`, `ReplaceOptions`, `UpsertOptions` trong Couchbase Java SDK khi cần kiểm soát trực tiếp.
5. Giải thích vì sao entity annotation không tự ảnh hưởng đến lệnh SDK thuần và không phải là thuộc tính lưu trong JSON.
6. Phân biệt durability với CAS/`@Version`, TTL, SQL++ scan consistency và transaction.
7. Xử lý lỗi durability, timeout có kết quả không chắc chắn và retry bằng idempotency.
8. Kiểm thử, đo độ trễ và kiểm tra level thực sự được áp dụng trong production.

## 2. Bài toán: cùng OrderDocument nhưng không phải ghi nào cũng giống nhau

Giả sử `commerce.sales.orders` là collection của một hệ thống bán hàng.

~~~json
{
  "tenantId": "42",
  "status": "NEW",
  "total": 1490000,
  "note": "Giao giờ hành chính"
}
~~~

Các API có nhu cầu khác nhau:

| API | Mutation | Điều cần xác nhận |
|---|---|---|
| `POST /orders` | Tạo order | Không tạo trùng, mức bền theo RPO |
| `PATCH /orders/{id}/note` | Sửa ghi chú | Chống ghi đè ngoài ý muốn, latency hợp lý |
| `POST /orders/{id}/pay` | Xác nhận PAID | Business transition hợp lệ, chống lost update, durability phù hợp |
| `DELETE /orders/{id}` | Xóa theo policy | Xử lý lỗi và idempotency khi response thất lạc |
| `GET /orders?status=PAID` | SQL++ | Độ mới của chỉ mục, **không phải durability** |

Có thể chọn **mức mặc định trên entity** cho phần lớn thao tác, rồi **override** tại điểm ghi quan trọng. Nếu bucket có minimum durability, policy tại server vẫn được áp dụng.

Thiết kế không chỉ là chọn một enum mạnh nhất; cần rõ **operation nào**, **yêu cầu mất dữ liệu nào**, **timeout nào** và **quy tắc retry nào**.

## 3. Ba tầng cấu hình durability

~~~mermaid
flowchart TD
    A["Metadata entity<br/>@Document hoặc @Durability"]
    B["Mutation cụ thể<br/>Template.withDurability hoặc SDK Options"]
    C["Minimum durability trên bucket<br/>nếu phiên bản và loại bucket hỗ trợ"]
    D["Couchbase Data Service<br/>durable write protocol"]
    A -->|"Default cho đường Spring Data"| B
    B -->|"Yêu cầu của client"| C
    C -->|"Mức hiệu lực"| D
~~~

| Tầng | Đặt tại đâu? | Áp dụng tới đâu? |
|---|---|---|
| **Entity** | `@Document`/`@Durability` của Spring Data | Các mutation dùng metadata mapping của entity |
| **Từng thao tác** | Fluent `CouchbaseTemplate` hoặc SDK `*.durability(...)` | Chính operation được gọi, không phải mọi ghi trong service |
| **Bucket minimum** | Cấu hình Couchbase Server/Capella | Toàn bộ mutation của bucket theo semantics của policy |

Spring Data template có thể dùng durability từ entity như mặc định; `withDurability(...)` cho phép chọn mức cụ thể ở call site. Bucket minimum là yêu cầu phía server, không bị một lời gọi client yếu hơn bỏ qua. Với các phiên bản hiện đại được hỗ trợ, tài liệu Couchbase mô tả rằng **mức mạnh hơn giữa client và bucket** được thực thi.

Sơ đồ trên là sơ đồ **lựa chọn yêu cầu**, không phải ba mutation nối tiếp. Server thực thi durable-write protocol tương ứng với level hiệu lực.

## 4. Nhắc lại các giá trị DurabilityLevel

Couchbase Java SDK dùng enum trong package:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;
~~~

Các giá trị phổ biến: `NONE`, `MAJORITY`, `MAJORITY_AND_PERSIST_TO_ACTIVE`, `PERSIST_TO_MAJORITY`.

| Level | Yêu cầu xác nhận cốt lõi | Điều không được tự suy ra |
|---|---|---|
| `NONE` | Không đặt yêu cầu synchronous durability bổ sung từ client | Các replica đã nhận hoặc đã persist |
| `MAJORITY` | Mutation được xác nhận bởi majority bản dữ liệu liên quan | Active đã persist |
| `MAJORITY_AND_PERSIST_TO_ACTIVE` | Majority **và** persistence tại active | Mọi replica đều đã persist |
| `PERSIST_TO_MAJORITY` | Persistence trên majority bản liên quan | Backup và mọi failure domain đều đã có dữ liệu |

Trong Couchbase, mỗi document được ánh xạ đến một **vBucket**. vBucket có một active trên Data node và có thể có replica trên node khác. Durability yêu cầu mức xác nhận theo những bản liên quan, **không phải** chờ tất cả node của cluster.

**Replication** và **persistence** khác nhau: một replica đã nhận mutation trong bộ nhớ chưa chắc đã persist. Với level yêu cầu persistence, loại bucket/storage engine phải hỗ trợ.

## 5. Khai báo mặc định bằng @Document

Spring Data Couchbase các phiên bản hiện đại hỗ trợ thuộc tính `durabilityLevel` của `@Document`:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

@Document(durabilityLevel = DurabilityLevel.MAJORITY)
@Scope("sales")
@Collection("orders")
public class OrderDocument {

    @Id
    private String id;

    @Version
    private Long version;

    private String tenantId;
    private String status;
    private Long total;

    // Constructors, getters và setters được lược bỏ.
}
~~~

Cách hiểu chính xác:

- `@Document` đánh dấu đối tượng được mapping thành Couchbase document.
- `durabilityLevel` là **mức mặc định của các thao tác mutation qua Spring Data mapping** cho entity này.
- `@Scope` và `@Collection` xác định keyspace; bucket thường nằm ở cấu hình kết nối.
- `@Id` là document ID.
- `@Version` dùng CAS/optimistic locking, **không phải durability level**.

Giá trị annotation là metadata của class ở phía Java. Nó không tự ghi một field `durabilityLevel` vào JSON body và không tự thay đổi policy của bucket.

### 5.1. Repository sử dụng annotation

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {
}
~~~

~~~java
OrderDocument saved = orderRepository.save(order);
~~~

Khi repository dùng đường mapping của Spring Data cho `OrderDocument`, mức trong annotation được framework dùng làm mặc định theo API hỗ trợ.

Nhưng chỉ nhìn `save(order)` chưa thể kết luận mức thực sự được server áp dụng. Cần xem phiên bản, entity được nhận diện đúng không, có override ở tầng khác không và bucket minimum là gì.

### 5.2. Annotation không quyết định loại mutation

`save` có thể dùng insert, replace hoặc upsert tùy metadata `@Version`, trạng thái entity và ngữ cảnh transaction. Việc đặt `MAJORITY` không khiến `upsert` trở thành `insert-only` hoặc tự phát hiện duplicate nghiệp vụ.

Cần kiểm tra **semantics thao tác ghi** riêng với **mức xác nhận ghi**.

## 6. Annotation @Durability và quan hệ với @Document

Spring Data Couchbase cũng cung cấp annotation:

~~~java
import org.springframework.data.couchbase.core.mapping.Durability;
~~~

Trong những phiên bản hỗ trợ, `@Durability` có `durabilityLevel` và `durabilityExpression`; `@Document` cung cấp các thuộc tính alias tương ứng.

Ví dụ cách khai báo riêng:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Durability;

@Document
@Durability(durabilityLevel = DurabilityLevel.MAJORITY)
public class AuditEventDocument {
    // @Id, các trường và accessors...
}
~~~

Trong code base thông thường, có thể ưu tiên `@Document(durabilityLevel = ...)` để hợp đồng dễ nhìn. Không cấu hình các annotation cùng loại với các giá trị mâu thuẫn rồi hy vọng Spring Data tự tổng hợp theo một quy tắc chưa được xác minh.

### 6.1. Chú ý package

- `org.springframework.data.couchbase.core.mapping.Durability` là **annotation Spring Data**.
- `com.couchbase.client.core.msg.kv.DurabilityLevel` là **enum SDK**.

Một entity có `@Durability` không khiến lệnh `Collection.insert(id, JsonObject)` từ SDK tự đọc metadata của Spring; SDK trực tiếp dùng các option riêng.

## 7. Cấu hình từ property source bằng durabilityExpression

Khi muốn cùng code nhưng khác mức ở môi trường chạy, có thể dùng `durabilityExpression`.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;

@Document(durabilityExpression = "${app.couchbase.order-durability}")
public class OrderDocument {

    @Id
    private String id;

    private String status;

    // Các trường/accessors khác...
}
~~~

Ví dụ `application.yml`:

~~~yaml
app:
  couchbase:
    order-durability: MAJORITY
~~~

Giá trị property có thể được cấu hình qua profile hoặc secret/configuration management theo quy trình.

**Giới hạn từ Javadoc Spring Data Couchbase:**

- `durabilityExpression` hỗ trợ **Spring property placeholder resolution** theo `PropertyResolver`.
- **Không hỗ trợ SpEL** cho thuộc tính này.
- Chỉ được cấu hình **một trong hai**: `durabilityLevel` hoặc `durabilityExpression`.
- Một property thiếu hoặc sai định dạng enum có thể khiến cấu hình invalid; cần test khởi động và ghi thực.

Đúng: `"${app.couchbase.order-durability}"`. Không nên thử dùng một biểu thức `"#{someBean.choose(order)}"` để lựa chọn theo từng entity instance — đó không phải API tính per-request durability.

### 7.1. Dynamic cấu hình khác dynamic theo request

Property source giúp tách giá trị giữa các môi trường/triển khai. Nó **không phải** cơ chế tự động nâng mức khi `order.status` chuyển thành `PAID`. Muốn chọn theo use case, dùng per-operation option hoặc thiết kế entity/keyspace phù hợp.

## 8. Repository save có giới hạn gì khi muốn override?

`CouchbaseRepository.save(entity)` không có tham số `DurabilityLevel` ngay trong chữ ký gọi thông thường. Nếu chỉ cần một default thống nhất, annotation là cách gọn.

Nếu một endpoint quan trọng cần mức khác default, các lựa chọn thực tế là:

1. Sử dụng fluent `CouchbaseTemplate` để đặt `withDurability(...)` cho operation.
2. Dùng reactive template tương ứng nếu ứng dụng dùng Reactor.
3. Dùng Java SDK mutation options khi cần metadata/semantics thấp hơn.
4. Thiết kế keyspace/policy khác nếu yêu cầu của hai loại dữ liệu khác biệt lớn.

Không cố đặt `@Durability` lên **một method tùy ý** rồi suy rằng Spring Data sẽ thay mức theo từng lời gọi: cần kiểm tra target và cơ chế của annotation. `@Durability` được thiết kế cho type/annotation type, không phải bất kỳ service method nào.

## 9. Per-operation với CouchbaseTemplate

Fluent template API cung cấp `withDurability(...)`:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import org.springframework.data.couchbase.core.CouchbaseTemplate;

public class OrderWriter {

    private final CouchbaseTemplate template;

    public OrderWriter(CouchbaseTemplate template) {
        this.template = template;
    }

    public OrderDocument upsertOrder(OrderDocument order) {
        return template
                .upsertById(OrderDocument.class)
                .withDurability(DurabilityLevel.PERSIST_TO_MAJORITY)
                .one(order);
    }
}
~~~

Mẫu `upsertById(Entity.class).withDurability(level).one(entity)` là cách thể hiện mức riêng cho **một thao tác** ở Spring Data Couchbase. Theo tài liệu template, nếu không override, default durability từ `@Document` được sử dụng.

### 9.1. Với insert-only

~~~java
OrderDocument created = template
        .insertById(OrderDocument.class)
        .withDurability(DurabilityLevel.MAJORITY)
        .one(order);
~~~

`insertById` hướng tới tạo mới và từ chối ID trùng theo semantics thao tác. `upsertById` có thể thay document đang tồn tại; đừng dùng upsert vô điều kiện cho API cần chống duplicate.

### 9.2. Với replace/update

Các API fluent `replaceById`, `removeById`, `mutateInById` có thể hỗ trợ `withDurability(...)` theo Spring Data version. Khi thay một entity đã có `@Version`, còn phải kiểm tra CAS và cách framework áp dụng optimistic locking.

Không có gì trong `withDurability(PERSIST_TO_MAJORITY)` tự kiểm tra phép chuyển trạng thái `NEW → PAID` là hợp lệ. **Durability, CAS và business rule** là ba vấn đề độc lập.

### 9.3. Scope của override

Một override không thay đổi annotation trên class và không áp sang lần gọi repository tiếp theo. Nếu muốn bảo vệ toàn bộ workload, đánh giá entity default hoặc bucket minimum cùng DBA/SRE.

## 10. Ma trận chọn default và override

| Trường hợp | Default entity | Override cần cân nhắc |
|---|---|---|
| Đơn nháp có thể tái tạo | Theo RPO của loại đơn | Có thể không cần |
| Xác nhận PAID quan trọng | `MAJORITY` nếu phù hợp toàn entity | `PERSIST_TO_MAJORITY` hoặc mức khác sau đánh giá |
| Ghi chú/tags | Theo hợp đồng entity | Chỉ khi có SLA riêng |
| Audit event | Có thể dùng entity/keyspace riêng | Khi từng event có mức rủi ro khác |
| Session/cache tạm | Theo chi phí mất dữ liệu thấp hơn | Không mặc định dùng mức mạnh nhất |

Đây là ví dụ để ra quyết định, không phải quy định mọi thanh toán phải sử dụng một mức cố định. Cần nêu rõ **failure scenario, RPO, latency SLO, backup và khả năng retry**.

### 10.1. Entity default phù hợp khi

- Các mutation của entity có giá trị và RPO tương tự.
- Muốn giảm lặp cấu hình giữa nhiều repository.
- Đã test framework version áp dụng annotation đúng.
- Có review để phát hiện đường SDK trực tiếp bỏ qua metadata.

### 10.2. Per-operation phù hợp khi

- Chỉ một số sự kiện quan trọng cần chờ mức mạnh hơn.
- Muốn đọc call site là biết hợp đồng độ bền.
- Có monitoring và retry policy riêng cho từng endpoint.
- Bucket minimum không áp thêm yêu cầu ngoài dự kiến.

## 11. Java SDK: mutation options trực tiếp

Couchbase Java SDK 3.x có `InsertOptions`, `ReplaceOptions`, `UpsertOptions` và các option tương ứng với những mutation khác.

Giả sử `orders` là `com.couchbase.client.java.Collection` đã nối đến `commerce.sales.orders`.

### 11.1. Insert cùng durability

~~~java
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import com.couchbase.client.java.json.JsonObject;

String id = "tenant::42::order::1001";

JsonObject body = JsonObject.create()
        .put("tenantId", "42")
        .put("status", "NEW")
        .put("total", 1490000);

var inserted = orders.insert(
        id, body,
        insertOptions().durability(DurabilityLevel.MAJORITY)
);
~~~

Đây là mutation **create-only**; nếu ID trùng sẽ có lỗi. Việc dùng durability không tự bổ sung idempotency key, nên vẫn cần thiết kế ID ổn định.

### 11.2. Replace cùng CAS

~~~java
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;

var old = orders.get(id);
var next = old.contentAsObject().put("status", "PAID");

var saved = orders.replace(
        id,
        next,
        replaceOptions()
                .cas(old.cas())
                .durability(DurabilityLevel.MAJORITY_AND_PERSIST_TO_ACTIVE)
);
~~~

- `cas(old.cas())` tránh replace dựa trên phiên bản đã bị thay đổi.
- `durability(...)` yêu cầu điều kiện majority và active persistence.
- Business logic vẫn phải kiểm tra trạng thái `NEW` có được chuyển `PAID` không.

### 11.3. Upsert với mức khác

~~~java
import static com.couchbase.client.java.kv.UpsertOptions.upsertOptions;

orders.upsert(
        "tenant::42::order::summary-1001",
        summaryBody,
        upsertOptions().durability(DurabilityLevel.PERSIST_TO_MAJORITY)
);
~~~

Upsert không tương đương insert-only. Nếu thao tác phải tránh ghi đè dữ liệu đã có, dùng operation và CAS phù hợp.

### 11.4. Xóa cũng là mutation

~~~java
import static com.couchbase.client.java.kv.RemoveOptions.removeOptions;

orders.remove(
        id,
        removeOptions().durability(DurabilityLevel.MAJORITY)
);
~~~

Không coi remove không cần độ bền chỉ vì không có body mới; việc xóa được xác nhận và tồn tại sau failure cũng là yêu cầu dữ liệu.

## 12. Annotation không tự ảnh hưởng Java SDK trực tiếp

Xét:

~~~java
@Document(durabilityLevel = DurabilityLevel.PERSIST_TO_MAJORITY)
public class OrderDocument {
    // ...
}
~~~

Và một lời gọi khác:

~~~java
// Dùng Couchbase Java SDK Collection, body là JsonObject.
orders.insert(id, jsonBody);
~~~

Lời gọi SDK thuần **không đọc** annotation của class `OrderDocument`. Nó được chi phối bởi mutation options gửi đi, default SDK/server và minimum bucket.

Nếu ứng dụng trộn repository với SDK trực tiếp:

1. Đảm bảo cùng bucket/scope/collection và document ID.
2. Đảm bảo body JSON đúng mapping conventions, kể cả field discriminator như `_class` nếu có.
3. Xác định đường nào dùng CAS/expiry.
4. Test requested durability của từng đường.
5. Tránh hai writer dùng hai cơ chế serialize khác nhau dẫn đến mất field hoặc đọc repository không match.

## 13. Minimum durability của bucket

Couchbase Server/Capella những phiên bản được hỗ trợ có thể áp dụng **minimum durability** ở cấp bucket.

~~~text
Bucket commerce: minimum MAJORITY
OrderDocument: default MAJORITY

Thao tác A: repository.save -> entity default
Thao tác B: template.withDurability(PERSIST_TO_MAJORITY)
Thao tác C: SDK upsert(...NONE)
~~~

Ở server, policy minimum vẫn ràng buộc. Client không thể dùng `NONE` để bảo đảm rằng một ghi được ack yếu hơn mức bucket đặt.

| Entity default | Override ở operation | Bucket minimum | Điều cần hiểu |
|---|---|---|---|
| `MAJORITY` | Không có | Không đặt riêng | Dùng default Spring Data nếu mapping path |
| `MAJORITY` | `PERSIST_TO_MAJORITY` | `MAJORITY` | Operation yêu cầu mạnh hơn |
| `PERSIST_TO_MAJORITY` | `MAJORITY` | `MAJORITY` | Override được chọn; cần review có được phép hạ so với default hay không |
| `NONE` | Không có | `MAJORITY` | Server policy áp mức tối thiểu |
| `MAJORITY` | `NONE` | `PERSIST_TO_MAJORITY` | Không được kết luận hiệu lực là NONE |

Đây là bảng đánh giá logic. Luôn kiểm tra khả năng hỗ trợ và hành vi thực tế của phiên bản, bucket type và SDK.

### 13.1. Vì sao policy bucket có thể gây tác động lớn?

Một bucket có thể chứa nhiều collection do nhiều service sử dụng. Nâng minimum durability làm thay đổi chi phí của **mọi mutation bị ảnh hưởng**, không chỉ một endpoint thanh toán.

Trước khi đổi:

- Liệt kê các service và mutation rate.
- Kiểm tra replica availability và storage engine.
- Đo write p95/p99, error rate và throughput.
- Xác định RPO nghiệp vụ.
- Có rollout/rollback và thông báo cho các nhóm sở hữu workload.

## 14. Các cấu hình legacy persistTo/replicateTo

Javadoc của `@Document` cũng đề cập `persistTo` và `replicateTo` trong các hệ thống đời cũ. Chúng liên quan mô hình xác nhận theo số bản với **client-verified durability**.

Trong các server hiện đại hỗ trợ Sync Writes, tài liệu Spring Data định hướng sử dụng `durabilityLevel()`. Không đồng nhất hai cách cấu hình:

~~~text
Legacy:
  persistTo / replicateTo

Modern:
  durabilityLevel / durabilityExpression
~~~

Khi nâng cấp project cũ:

1. Xác định Spring Data, SDK và server version.
2. Đối chiếu code/annotation cũ với cơ chế server-enforced durability.
3. Không chỉ đổi tên property rồi giả định timeout/visibility behavior vẫn giống.
4. Test trên môi trường hỗ trợ và có rollback.
5. Không dùng đồng thời các option mâu thuẫn nếu API không xác định semantics mong muốn.

Với ứng dụng mới, ưu tiên lựa chọn **synchronous durability theo `DurabilityLevel`** khi có thể dùng với loại bucket và server được hỗ trợ.

## 15. CAS và `@Version` khác DurabilityLevel

Một document có thể được sửa bởi hai request:

~~~text
T0: order.status = NEW, CAS = V1
T1: A đọc V1, dự tính PAID
T2: B đọc V1, dự tính CANCELLED
T3: A replace với CAS V1 -> thành công, CAS V2
T4: B replace với CAS V1 -> CAS mismatch
~~~

`@Version`/CAS giúp tránh lost update khi code kiểm tra phiên bản. Durability giúp một mutation **đã được chấp nhận** đạt điều kiện xác nhận replica/persistence. Không mức nào tự kiểm tra rằng chuyển trạng thái `NEW → PAID` đúng business rule.

| Cơ chế | Giải quyết | Không thay thế |
|---|---|---|
| `@Version` / CAS | Cập nhật cạnh tranh trên một document | Replication/persistence |
| `DurabilityLevel` | Điều kiện xác nhận mutation | CAS và validation |
| `insert` + ID ổn định | Tránh create-only trùng ID | Durability |
| Couchbase Transactions | Atomicity nhóm mutation đa document | Backup/side effect ngoài |

Khi CAS conflict, cần **đọc lại document và tính lại business rule**, không chỉ retry cùng body và CAS mới. Durability cao không sửa được invariant nghiệp vụ sai.

## 16. TTL/expiry vẫn độc lập

Một session có thể được ghi với `MAJORITY` nhưng hết hạn sau 30 phút. TTL là metadata vòng đời, không phải mức durability.

~~~java
import java.time.Duration;
import static com.couchbase.client.java.kv.UpsertOptions.upsertOptions;

sessions.upsert(
        "session::abc123",
        sessionBody,
        upsertOptions()
                .expiry(Duration.ofMinutes(30))
                .durability(DurabilityLevel.MAJORITY)
);
~~~

Phân biệt:

- `expiry(...)`: document hết hạn khi nào.
- `preserveExpiry`/`touch` khi được hỗ trợ: giữ hoặc thay đổi hạn.
- `durability(...)`: điều kiện ghi được xác nhận.
- `@Version`/CAS: bảo vệ ghi theo phiên bản.
- Backup/restore: phục hồi sau lỗi ngoài phạm vi replica.

Một đường Spring Data mapping có thể quản lý TTL khác đường SDK JSON. Hãy kiểm tra **expiry metadata thực tế** khi trộn hai cách ghi, không suy ra chỉ từ trường JSON `expiresAt`.

## 17. Độ mới SQL++/GSI không phải độ bền ghi

~~~text
T0: insert order::1001 với PERSIST_TO_MAJORITY -> thành công
T1: SQL++ WHERE status = "PAID" -> chưa thấy đơn
T2: Index Service bắt kịp mutation
T3: Query sau đó thấy đơn
~~~

GSI có thể được cập nhật bất đồng bộ. Một mutation đã bền theo level không làm chỉ mục SQL++ bắt kịp ngay.

~~~sql
SELECT META(o).id AS id, o.status
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "42"
  AND o.status = "PAID";
~~~

| Nhu cầu | Cơ chế đúng |
|---|---|
| Đã biết ID | KV `get(id)` hoặc repository `findById` |
| Danh sách chấp nhận cập nhật trễ | SQL++ `not_bounded` |
| Đợi index bắt kịp mutation trước query | `request_plus` |
| Đợi một hoặc vài mutation đã biết | `consistentWith(MutationState)` |

Không bật durability mạnh để sửa index lag; cũng không dùng `request_plus` để biến một mutation thành persist-on-majority.

## 18. Reactive template và SDK

Spring Data Couchbase reactive template có fluent API tương tự ở các phiên bản hỗ trợ:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import org.springframework.data.couchbase.core.ReactiveCouchbaseTemplate;
import reactor.core.publisher.Mono;

public class ReactiveOrderWriter {
    private final ReactiveCouchbaseTemplate template;

    public ReactiveOrderWriter(ReactiveCouchbaseTemplate template) {
        this.template = template;
    }

    public Mono<OrderDocument> persist(OrderDocument order) {
        return template
                .upsertById(OrderDocument.class)
                .withDurability(DurabilityLevel.MAJORITY)
                .one(order);
    }
}
~~~

Reactive Java SDK trực tiếp cũng truyền options:

~~~java
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;
import com.couchbase.client.java.kv.MutationResult;
import reactor.core.publisher.Mono;

Mono<MutationResult> write = orders.reactive().insert(
        id, body,
        insertOptions().durability(DurabilityLevel.MAJORITY)
);
~~~

Hai đường ghi có thể khác ở mapping JSON, CAS và TTL. Reactive không thay đổi server-enforced durability.

### 18.1. Retry/resubscribe

`retryWhen` có thể subscribe lại publisher ghi dữ liệu. Nếu server đã commit lần đầu nhưng response thất lạc, lần subscribe tiếp có thể gây duplicate hoặc CAS conflict.

Cần ID ổn định, retry giới hạn, timeout rõ ràng, idempotency, reconciliation và concurrency limit. Backpressure giúp quản lý tải, **không** tự tạo durability hoặc transaction.

## 19. Transaction nhiều document có cấu hình riêng

Giả sử workflow cần:

~~~text
- insert order::1001
- replace inventory::sku-A1
- insert payment-record::1001
~~~

Ba mutation riêng, dù đều `PERSIST_TO_MAJORITY`, **không phải một transaction**. Nếu mutation thứ ba lỗi, hai thay đổi đầu vẫn có thể tồn tại.

Couchbase Transactions có API/cấu hình durability, timeout, isolation và retry riêng theo phiên bản. Không tự suy ra transaction lấy “mức mạnh nhất” bằng cách đọc các `@Document` khác nhau.

Khi dùng transaction:

1. Xác nhận transaction manager/SDK Transactions API thực tế.
2. Kiểm tra mutation nào nằm trong boundary.
3. Đối chiếu transaction durability và minimum bucket.
4. Xử lý retry/conflict; callback có thể chạy lại.
5. Không gọi payment gateway, gửi email hoặc publish event không idempotent trong callback.
6. Dùng saga/outbox/idempotency cho side effect ngoài Couchbase khi phù hợp.

Durability không thay thế atomicity nhiều document, cũng không biến hệ thống ngoài thành một phần transaction.

## 20. Exception và timeout ở hai tầng API

Spring Data có thể dịch lỗi qua hệ `DataAccessException`; SDK trực tiếp có hệ exception riêng. Do đó cần kiểm tra loại lỗi nhận tại abstraction đang dùng, không giả định catch SDK exception hoạt động giống nhau mọi nơi.

| Outcome | Ý nghĩa | Hướng xử lý |
|---|---|---|
| Success | Mutation hoàn tất theo contract/level hiệu lực | Tiếp tục workflow |
| Duplicate khi insert | ID đã tồn tại | Đối chiếu idempotency, không đổi ID tùy tiện |
| CAS mismatch | Bản đọc cũ | Đọc lại và kiểm tra chuyển trạng thái |
| Durability impossible/unavailable | Level hoặc cluster không đáp ứng | Kiểm tra bucket/replica, báo DBA/SRE |
| Timeout/ambiguous | Có thể đã commit nhưng response bị mất | Readback theo ID, reconciliation |
| SQL++ chưa thấy ghi | GSI chưa theo kịp hoặc query sai | Kiểm tra KV, index và scan consistency |

Không được mặc định timeout đồng nghĩa mutation thất bại. Đồng thời, không được tự coi một lỗi durability là thành công nếu chưa có bằng chứng xác nhận.

### 20.1. Không tự hạ level

Nếu write yêu cầu `PERSIST_TO_MAJORITY` nhưng không thể hoàn tất, retry ngay bằng `NONE` có thể làm thay đổi RPO của nghiệp vụ. Đây là quyết định phải được chấp nhận theo policy, không phải nhánh xử lý lỗi mặc định.

## 21. Ambiguous outcome và idempotency

Một response có thể mất sau khi server commit:

~~~mermaid
sequenceDiagram
    participant App as order-service
    participant SDK as Couchbase SDK
    participant A as Active vBucket
    participant R as Replica
    App->>SDK: INSERT + MAJORITY
    SDK->>A: Mutation KV
    A->>R: Replicate/confirm
    R-->>A: Đạt điều kiện
    Note over A,R: Mutation có thể đã commit
    A--xSDK: Response mất do mạng
    SDK-->>App: Timeout / ambiguous outcome
~~~

Nếu API nhận timeout rồi tạo ID khác để retry, có thể sinh hai đơn cho một checkout dù mutation đầu rất bền.

~~~text
POST /checkout
Idempotency-Key: checkout-abc
Order ID: tenant::42::checkout::checkout-abc

Mọi lần retry cùng checkout đều dùng lại Order ID.
~~~

~~~mermaid
flowchart TD
    A["Nhận request + idempotency key"]
    B["Tạo document ID ổn định"]
    C["INSERT với durability đã chọn"]
    D{"Outcome?"}
    S["Success"]
    E["Duplicate -> đọc và đối chiếu payload"]
    X["Ambiguous -> kiểm tra trạng thái theo ID"]
    H{"Document khớp request?"}
    Y["Trả kết quả đã có"]
    N["Retry có giới hạn hoặc reconciliation"]
    A --> B --> C --> D
    D -->|"Success"| S
    D -->|"Duplicate"| E
    D -->|"Ambiguous"| X
    E --> H
    X --> H
    H -->|"Có"| Y
    H -->|"Không/chưa rõ"| N
~~~

Ngoài ID ổn định cần kiểm tra **fingerprint của business request**, vì hai payload khác nhau không thể chia sẻ idempotency key mà vẫn được chấp nhận vô điều kiện.

Nếu thao tác có charge bên ngoài Couchbase, cần idempotency ở payment gateway; durability của database không tự bảo đảm external charge đúng một lần.

## 22. Version, bucket type và replica

Code hợp lệ vẫn có thể không chạy nếu môi trường không hỗ trợ level đã chọn.

| Lớp | Cần kiểm tra |
|---|---|
| Spring Data | Annotation và template fluent API của phiên bản hiện tại |
| Java SDK | Overload/options của mutation đang dùng |
| Couchbase Server | Tính năng synchronous durability và protocol được hỗ trợ |
| Bucket type | Persistence capability nếu level yêu cầu lưu bền |
| Storage engine | Hỗ trợ level tương ứng |
| Replica topology | Số bản/khả năng đáp ứng majority |
| Bucket minimum | Policy phía server có mạnh hơn không |
| Capella/self-managed | Deployment options, region/tier, quyền cấu hình |
| Mạng/TLS/RBAC | App có kết nối và quyền ghi đúng collection không |

**Không có annotation nào tự tăng số replica hoặc biến bucket không hỗ trợ persistence thành bucket có thể persist.**

Khi đổi Spring Data, SDK hoặc server version, kiểm thử lại entity metadata, template overrides, exception translation, bucket minimum và performance trước khi rollout.

## 23. Hiệu năng: default và override dựa trên số đo

Durability cao có thể tăng thời gian chờ replication/persistence. Đo:

- KV mutation latency p50/p95/p99 theo endpoint.
- Requested durability, timeout và ambiguous outcome count.
- Replica health, disk I/O, network, failover/rebalance.
- Throughput và số request in-flight.
- Retry rate, CAS conflict, duplicate và reconciliation backlog.
- Business SLO, không chỉ thời gian database.

### 23.1. Benchmark công bằng

Khi so `@Document(MAJORITY)` với `withDurability(PERSIST_TO_MAJORITY)`:

1. Giữ cùng keyspace và kích thước document.
2. Dùng workload insert/replace và concurrency tương đương.
3. Đo p95/p99, throughput, timeout, không chỉ latency trung bình.
4. Kiểm tra resource bottleneck trên Data/replica/storage/network.
5. Thử failure scenario có kiểm soát ở test cluster.
6. Đánh giá kết quả cùng RPO, không chỉ chọn giá trị nhanh hơn.

## 24. Thiết kế minh họa: entity default và override

Entity:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

@Document(durabilityLevel = DurabilityLevel.MAJORITY)
@Scope("sales")
@Collection("orders")
public class OrderDocument {
    @Id
    private String id;

    @Version
    private Long version;

    private String tenantId;
    private String status;
    private Long total;

    // Constructors/accessors...
}
~~~

Repository:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {
}
~~~

Service override:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import org.springframework.data.couchbase.core.CouchbaseTemplate;

public class CriticalOrderWriter {
    private final CouchbaseTemplate template;

    public CriticalOrderWriter(CouchbaseTemplate template) {
        this.template = template;
    }

    public OrderDocument persistCriticalOrder(OrderDocument order) {
        return template
                .upsertById(OrderDocument.class)
                .withDurability(DurabilityLevel.PERSIST_TO_MAJORITY)
                .one(order);
    }
}
~~~

**Giới hạn:** mẫu trên chỉ minh họa chọn durability. `upsert` không tự chống duplicate hay kiểm tra chuyển trạng thái. Trong production, dùng `insert` cho create-once, CAS/replace cho read-modify-write, transaction cho invariant nhiều document và idempotency cho retry.

Một contract rõ ràng:

~~~text
createDraft:
  - ID ổn định / insert-only
  - entity default MAJORITY
  - duplicate -> đối chiếu idempotency

recordPayment:
  - xác minh trạng thái hợp lệ
  - CAS hoặc transaction nếu cần
  - durability override theo RPO
  - ambiguous -> reconciliation

listPaid:
  - SQL++ và GSI
  - scan consistency theo SLA
  - không lấy query freshness làm bằng chứng durability
~~~

## 25. Kiểm thử default, override và minimum

| Test | Cần xác minh |
|---|---|
| Annotation | `@Document` có level đúng |
| Repository save | Mapping path dùng default đúng |
| `durabilityExpression` | Property resolve, không set trùng level/expression |
| Template override | `withDurability` có hiệu lực trên operation |
| SDK bypass | SDK không tự đọc annotation entity |
| Bucket minimum | Client không bypass policy với `NONE` |
| CAS conflict | Hai writer không ghi đè |
| Replica unavailable | Durability báo lỗi/timeout phù hợp |
| Ambiguous response | Retry không tạo duplicate |
| Reactive resubscribe | Idempotency và deadline được giữ |
| SQL++ | Không dùng GSI freshness thay kiểm chứng write durability |

### 25.1. Unit test annotation chưa đủ

Đọc annotation bằng reflection chỉ chứng minh class có metadata. Nó không chứng minh server nhận level, replica đáp ứng quorum hoặc đường SDK khác cũng đã áp dụng.

Cần integration test trên môi trường tương thích và failure drill trên test cluster được phép. Không hard failover production chỉ để test một bài học.

## 26. Những sai lầm thường gặp

| Sai lầm | Vì sao sai |
|---|---|
| `@Version` đã là durability | CAS chỉ xử lý concurrency |
| Annotation tự áp cho SDK JSON write | SDK không đọc Spring metadata |
| `withDurability` thay annotation class | Override chỉ cho operation |
| `durabilityExpression` dùng SpEL | API dùng property placeholder |
| Client `NONE` bỏ qua bucket minimum | Server vẫn áp policy |
| `save` trả entity chứng minh persist majority | Cần xác định effective level |
| Durability làm SQL++ lập tức thấy document | GSI cập nhật bất đồng bộ |
| Timeout luôn có nghĩa chưa ghi | Response có thể mất sau commit |
| Retry bằng ID mới an toàn | Có thể tạo duplicate |
| Mức cao nhất làm backup không cần thiết | Backup giải quyết khôi phục ngoài replica |
| Reactive làm write bền hơn | Server protocol không đổi |
| Transaction tự lấy level từ từng entity | Có transaction config riêng |

## 27. Bài tập và checklist

### Bài tập A — entity annotation

Viết `OrderDocument` có `@Document(durabilityLevel = MAJORITY)`, `@Version` và keyspace `sales.orders`. Giải thích hai annotation bảo vệ những rủi ro nào.

### Bài tập B — property source

Thay mức hard-code bằng `durabilityExpression = "${app.couchbase.order-durability}"`. Giải thích vì sao không dùng SpEL và không set cả expression lẫn level.

### Bài tập C — per-operation

Dùng `CouchbaseTemplate.upsertById(...).withDurability(PERSIST_TO_MAJORITY)`. Phân biệt với default entity và minimum bucket.

### Bài tập D — create-once

Vì sao `insertById`/`insert` phù hợp hơn upsert không điều kiện khi API nhận idempotency key? Durability có ngăn duplicate không?

### Bài tập E — repository và SDK

Repository dùng entity default `MAJORITY` nhưng import job gọi SDK `upsert` không có options. Xác định những tầng ảnh hưởng mức thực tế và cách test.

### Bài tập F — CAS

Hai request cùng chuyển `NEW → PAID` và `NEW → CANCELLED`. Đặt `PERSIST_TO_MAJORITY` có giải quyết lost update không? Thiết kế retry đúng.

### Bài tập G — bucket minimum

Bucket đặt minimum `MAJORITY`, client gửi `NONE`. Có thể kết luận operation success chỉ sau active ack không?

### Bài tập H — reactive retry

`retryWhen` chạy lại mutation đã commit nhưng response mất. Trình bày ID ổn định, phân loại exception và reconciliation.

### Bài tập I — consistency

Order ghi bền thành công nhưng SQL++ theo `status` chưa thấy. Vì sao và chọn KV/`request_plus`/MutationState khi nào?

### Checklist trước production

- [ ] Kiểm tra Spring Data, SDK và server version.
- [ ] Đặt entity default khi phù hợp; override operation đặc biệt có review.
- [ ] Không đặt đồng thời `durabilityLevel` và `durabilityExpression`.
- [ ] Không dùng SpEL trong durabilityExpression.
- [ ] Kiểm tra SDK direct writes có bỏ qua annotation không.
- [ ] Đối chiếu minimum bucket, loại bucket và replica topology.
- [ ] Dùng CAS/`@Version` cho update cạnh tranh.
- [ ] Tách durability khỏi TTL, SQL++ freshness, transaction và backup.
- [ ] Có idempotency cho retry/ambiguous outcome.
- [ ] Giới hạn reactive retry, concurrency và deadline.
- [ ] Đo write p95/p99, timeout, ambiguous count và server health.
- [ ] Có integration tests và rollout/rollback plan.

## 28. Tổng kết

Spring Data Couchbase hỗ trợ đặt durability mặc định trên entity qua `@Document(durabilityLevel = ...)` hoặc `@Durability`. `durabilityExpression` dùng Spring property sources; còn `CouchbaseTemplate.withDurability(...)` và Couchbase Java SDK mutation options cho phép chọn **mức riêng cho từng thao tác**.

Cần phân biệt **entity metadata**, **per-operation options** và **minimum durability của bucket**. SDK thuần không tự đọc Spring annotation; tùy chọn client không thể bỏ qua minimum của server. Đồng thời CAS, TTL, SQL++ scan consistency, transaction, backup và idempotency giải quyết các mục tiêu khác.

Thiết kế tốt cần nêu rõ **mức xác nhận, loại lỗi chịu đựng, RPO, latency SLO và hành vi khi kết quả ghi không xác định**. Hãy kiểm chứng bằng integration test, telemetry và failure drill có kiểm soát, không suy diễn từ mỗi lời gọi `save` thành công.

## Tài liệu tham khảo chính thức

- [Spring Data Couchbase — Template & direct operations](https://docs.spring.io/spring-data/couchbase/reference/5.5/couchbase/template.html): fluent `withDurability` và default từ entity.
- [Spring Data Couchbase — Javadoc @Document](https://docs.spring.io/spring-data/couchbase/reference/5.5/api/java/org/springframework/data/couchbase/core/mapping/Document.html): `durabilityLevel`, `durabilityExpression`.
- [Spring Data Couchbase — Javadoc @Durability](https://docs.spring.io/spring-data/couchbase/docs/5.5.x/api/org/springframework/data/couchbase/core/mapping/Durability.html): property placeholder và API annotation.
- [Couchbase Java SDK — Data Modelling, Durability, and Consistency](https://docs.couchbase.com/java-sdk/current/concept-docs/data-durability-acid-transactions.html): synchronous durability và bucket policy.

Đối chiếu tài liệu với **phiên bản Spring Data, SDK, server và loại bucket thực tế** trước khi đưa ví dụ vào ứng dụng.

