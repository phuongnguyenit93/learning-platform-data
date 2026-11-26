# Chọn truy cập theo khóa khi đã có định danh tài liệu

## 1. Khi đã có document ID, vì sao vẫn có người viết SQL++?

Một endpoint nhận mã đơn hàng `O-2026-001`. Dữ liệu thật nằm tại key `order::O-2026-001` trong bucket `commerce`, scope `sales`, collection `orders`. Nếu service đã biết chính xác key này, cách đọc tự nhiên là **Key-Value (KV)**, không phải một câu truy vấn lọc theo ID.

Trong **Spring Data Couchbase**, có thể đi qua `CouchbaseRepository.findById`, API `CouchbaseTemplate.findById` hoặc `Collection.get` của Couchbase Java SDK. Cả ba hướng này phù hợp hơn một câu SQL++ thông thường khi yêu cầu chỉ là lấy document bằng định danh đã biết.

Bài **“Chọn truy cập theo khóa khi đã có định danh tài liệu”** nằm trong chương **Hiệu năng** của module **SPRING_DATA_COUCHBASE**. Module hướng tới xây dựng tầng truy cập Couchbase bằng document mapping, repository, `CouchbaseTemplate` và truy vấn SQL++; thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và API reactive để đảm bảo hiệu năng, nhất quán và vận hành.

Sau bài, bạn có thể:

1. Giải thích cấu trúc chi phí KV lookup và SQL++ query.
2. Lựa chọn API đọc theo ID trong Spring Data và SDK.
3. Phân biệt document ID với business ID, không nhầm keyspace.
4. Chọn `get`, `exists`, `lookupIn` hay một mutation theo ID tùy nhu cầu.
5. Xử lý nhiều ID bằng concurrency giới hạn, đặc biệt khi dùng Reactor.
6. Giữ semantics CAS, expiry, authorization và converter khi tối ưu.
7. Đo p95/p99, network bytes và tải cluster trước khi kết luận một cách đọc nhanh hơn.

Ví dụ theo hướng Spring Boot 3.x, Spring Data Couchbase 5.x và Couchbase Java SDK 3.x tương thích. Chi tiết chữ ký template, derived query và options có thể khác giữa các release; phải xác minh với dependency và server đang chạy.

## 2. Hai đường truy cập có mục tiêu khác nhau

~~~mermaid
flowchart LR
    A["Spring service"] --> B{"Có chính xác key và collection?"}
    B -- "Có" --> C["KV: get / exists / lookupIn / replace"]
    C --> D["Data service"]
    B -- "Chưa" --> E["SQL++ Query"]
    E --> F["Query service"]
    F --> G["Index hoặc query plan"]
    G --> D
    D --> H["Document hoặc kết quả"]
~~~

Đây là sơ đồ khái niệm; Query optimizer có thể chọn cách truy cập theo key cho SQL++ khi được cung cấp key. Điểm khác biệt chính: **KV request không cần gửi câu SQL++ qua Query service và không phụ thuộc secondary index** cho một lookup theo key.

SQL++ được thiết kế để tìm nhiều document theo predicate, join, aggregate, order và projection. Nếu việc cần làm chỉ là đọc một key đã biết, chi phí parse/plan/execute của Query service có thể là công việc thêm không cần thiết.

### 2.1. Đừng tuyên bố hiệu năng bằng một con số chung

KV thường đơn giản hơn cho exact-key lookup, nhưng không có cam kết “nhanh gấp N lần” trong mọi môi trường. Độ trễ còn chịu:

- Số round trip và vị trí client so với cluster.
- Kích thước JSON và chi phí decode/conversion.
- Mức cạnh tranh trên key và Data service.
- TLS, connection reuse và thời gian chờ.
- Query plan, index, workload và topology.
- Cách đo p50, p95, p99 cùng warm-up.

**Bắt đầu bằng KV theo ID, sau đó benchmark trên workload thật.**

## 3. Quy tắc chọn API từ yêu cầu nghiệp vụ

| Yêu cầu | API ưu tiên đánh giá | Lý do |
| --- | --- | --- |
| Đọc một order theo document ID | `repository.findById` hoặc SDK `get` | KV lookup theo key |
| Lấy entity đã map và converter | Repository/template find-by-ID | Giữ Spring Data mapping |
| Chỉ cần biết key còn tồn tại | SDK `exists` | Không cần tải content |
| Chỉ đọc vài field của document lớn | SDK `lookupIn` | Subdocument lookup theo key |
| Thay JSON theo CAS | SDK `replace` hoặc mapper optimistic locking | Mutation theo key/version |
| Xóa theo ID | SDK `remove` hoặc repository `deleteById` | Không cần query lọc |
| Danh sách 100 IDs | Nhiều KV reads có concurrency giới hạn | Không cần tìm kiếm ID qua index |
| Order của customer theo status | SQL++/derived query | Chưa biết các document IDs |
| Top order theo số tiền | SQL++ và index | Có predicate, sort và limit |
| Tổng hợp doanh thu | SQL++ hoặc Analytics theo nhu cầu | Không phải một lookup |
| Read session và làm mới TTL | `getAndTouch` khi policy **cho phép renew** | Có side effect lên expiry |

Câu hỏi đầu tiên không phải “repository hay SDK nhanh hơn”, mà là **“đã biết document key và collection hay mới biết một thuộc tính?”**

## 4. Document ID chỉ có nghĩa trong đúng keyspace

Ví dụ:

~~~text
Bucket: commerce
├── Scope: sales
│   ├── Collection: orders
│   │   └── order::O-2026-001
│   └── Collection: invoices
│       └── invoice::I-2026-001
└── Scope: checkout
    ├── Collection: carts
    │   └── cart::u-42
    └── Collection: sessions
        └── session::opaque-id
~~~

Cùng chuỗi ID có thể nằm trong nhiều collection. Vì vậy lookup chính xác cần **bucket + scope + collection + document ID**.

Nếu client gọi `commerce.checkout.carts.get("order::O-2026-001")` thì not-found không chứng minh đơn hàng bị xóa hay TTL hết hạn. Có thể chỉ đọc sai collection.

### 4.1. Business ID chưa chắc là document ID

JSON:

~~~json
{
  "orderId": "O-2026-001",
  "customerId": "u-42",
  "status": "PAID",
  "total": 150000
}
~~~

Document key có thể là `order::O-2026-001` hoặc một UUID khác. Nếu dùng tiền tố ổn định, tạo key bằng một hàm rõ ràng:

~~~java
public final class OrderKeys {
    private OrderKeys() { }

    public static String fromBusinessId(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("Order ID is required");
        }
        return "order::" + id;
    }
}
~~~

Trong thực tế cần validate định dạng ID, tenant và normalization. Nếu entity sử dụng `@GeneratedValue`, custom converter hoặc mapping key đặc biệt, đừng tự đoán key chỉ dựa trên field `orderId`.

## 5. Thiết kế key cho những access pattern chính

| Thiết kế | Lợi ích | Cần chú ý |
| --- | --- | --- |
| `order::<orderId>` | Lookup order trực tiếp | Unique ID, validate quyền |
| `cart::<userId>` | Một cart đang hoạt động theo user | Đa tenant, cập nhật cạnh tranh |
| `session::<randomId>` | Lookup token/ID | Entropy cao, bảo vệ bearer token |
| UUID độc lập | Không lộ business ID | Cần mapping/index để tìm theo ID nghiệp vụ |
| `tenant::<tenantId>::order::<orderId>` | Key gắn tenant rõ ràng | Không thay thế authorization |

Nếu phần lớn request tìm theo customerId nhưng document key chỉ chứa orderId, cần index theo customerId. Không nên ép một key chứa mọi trường và biến thành một chuỗi khó bảo trì.

Document ID phục vụ định danh; **nó không cấp quyền truy cập**. Một endpoint biết order ID vẫn phải xác minh caller có quyền đọc đơn hàng hoặc thuộc đúng tenant.

## 6. Mapping một entity cho keyspace xác định

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("sales")
@Collection("orders")
public class OrderDocument {

    @Id
    private String id;

    private String customerId;
    private String status;
    private long total;

    protected OrderDocument() { }

    public OrderDocument(
            String id, String customerId,
            String status, long total) {
        this.id = id;
        this.customerId = customerId;
        this.status = status;
        this.total = total;
    }

    public String getId() { return id; }
    public String getCustomerId() { return customerId; }
    public String getStatus() { return status; }
    public long getTotal() { return total; }
}
~~~

`@Id` là thuộc tính ánh xạ tới **document key**. `@Scope` và `@Collection` chọn namespace trong bucket mặc định; chúng không tự tạo keyspace trên server.

Ví dụ Spring Boot:

~~~yaml
spring:
  couchbase:
    connection-string: "couchbases://cb.example.internal"
    username: "application-user"
    password: "inject-secret-in-real-deployment"
  data:
    couchbase:
      bucket-name: commerce
~~~

Cấu hình chỉ minh họa kết nối. Production cần secret injection, TLS/trust đúng cluster và RBAC tối thiểu.

## 7. `CouchbaseRepository.findById`: lựa chọn mặc định khi cần entity

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {
}
~~~

Service:

~~~java
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public final class OrderReadService {

    private final OrderRepository orders;

    public OrderReadService(OrderRepository orders) {
        this.orders = orders;
    }

    public Optional<OrderDocument> byBusinessId(String businessId) {
        String documentId = OrderKeys.fromBusinessId(businessId);
        return orders.findById(documentId);
    }
}
~~~

Với lookup theo document ID, `findById` của Spring Data Couchbase thường đi qua **key-based access**. Nó có lợi khi cần mapping entity, converter và repository abstraction.

**Sai lầm:** gọi `findById(customerId)` khi `customerId` là field JSON chứ không phải document key. Kết quả `Optional.empty()` chỉ cho biết không tìm được theo key đã truyền, không chứng minh khách hàng chưa có order.

### 7.1. Không nhầm “empty” với lỗi hạ tầng

`Optional.empty()` có thể do key không tồn tại, bị xóa, đã hết hạn hoặc sai namespace. Nhưng timeout, lỗi xác thực và lỗi mapping là **những tình huống khác**. Không catch mọi exception rồi trả empty để tạo 404 giả lúc cluster outage.

## 8. `existsById` và `deleteById`

Repository hỗ trợ các thao tác theo ID:

~~~java
boolean exists = orders.existsById(
        "order::O-2026-001"
);

orders.deleteById(
        "order::O-2026-001"
);
~~~

Chúng thường có đường xử lý theo key trong những phiên bản phù hợp, nhưng phải kiểm tra behavior chính xác nếu ứng dụng dùng mapping đặc biệt.

**Không gọi EXISTS trước GET chỉ để lấy content**:

~~~java
// Không cần thiết nếu mục tiêu cuối là lấy entity.
if (orders.existsById(key)) {
    return orders.findById(key);
}
~~~

Hai thao tác thêm network round trip và có race: document có thể hết hạn hoặc bị xóa giữa EXISTS và GET. Nếu cần entity, gọi trực tiếp `findById`. Nếu chỉ cần boolean, EXISTS là đầu ra thích hợp.

Delete by ID cũng không tự xác minh quyền sở hữu hoặc trạng thái nghiệp vụ; authorization cần xử lý riêng.

## 9. `CouchbaseTemplate.findById`

Khi dùng template thay repository, vẫn có API đọc entity theo key ở các phiên bản Spring Data phù hợp:

~~~java
import org.springframework.data.couchbase.core.CouchbaseTemplate;

public final class OrderTemplateReader {

    private final CouchbaseTemplate template;

    public OrderTemplateReader(CouchbaseTemplate template) {
        this.template = template;
    }

    public OrderDocument load(String documentId) {
        return template.findById(OrderDocument.class)
                .one(documentId);
    }
}
~~~

Đây là ví dụ theo fluent API `findById(...).one(...)` trong nhánh Spring Data Couchbase 5.x. Nếu bản đang dùng có chữ ký hoặc kiểu trả về khác, dùng Javadoc của dependency resolved để điều chỉnh.

**Không đổi sang SQL++ chỉ vì đã chọn template.** Template có thao tác theo ID và thao tác truy vấn theo điều kiện, phục vụ hai mục đích khác nhau.

## 10. SDK `Collection.get`: đọc KV trực tiếp

Spring Data có thể cung cấp SDK handles qua `CouchbaseClientFactory`:

~~~java
import com.couchbase.client.java.Collection;
import org.springframework.data.couchbase.core.CouchbaseClientFactory;

public final class OrderKvGateway {

    private final Collection orders;

    public OrderKvGateway(CouchbaseClientFactory factory) {
        this.orders = factory.getBucket()
                .scope("sales")
                .collection("orders");
    }
}
~~~

Đọc bằng key:

~~~java
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.json.JsonObject;

GetResult result = orders.get("order::O-2026-001");
JsonObject json = result.contentAsObject();

String status = json.getString("status");
Long total = json.getLong("total");
~~~

`Collection.get` là **KV lookup**, không chạy SQL++ và không cần secondary index trên `status` hoặc `orderId` khi đã biết key.

### 10.1. Cảnh báo khi refactor repository sang SDK

SDK `JsonObject` trực tiếp không tự chạy Spring Data converter, `@Id`, `@Field`, `@Version` hay `@Document(expiry)`. Một update SDK có thể làm mất type metadata, reset expiry hoặc không đồng bộ schema nếu code chỉ ghi một phần JSON.

Vì vậy, tối ưu hot path bằng SDK cần **test chéo**: repository tạo entity, SDK GET đọc đúng content, SDK update giữ metadata quan trọng và repository vẫn decode được entity sau đó.

## 11. Trường hợp không tìm thấy: `DocumentNotFoundException`

~~~java
import com.couchbase.client.core.error.DocumentNotFoundException;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import java.util.Optional;

public Optional<JsonObject> findJson(
        Collection collection, String documentId) {
    try {
        return Optional.of(
                collection.get(documentId).contentAsObject());
    } catch (DocumentNotFoundException ignored) {
        return Optional.empty();
    }
}
~~~

Đây là một cách diễn giải not-found thành optional. **Đừng catch `Exception` chung** rồi trả empty, vì có thể biến timeout, RBAC, network outage hoặc dữ liệu lỗi thành “không tồn tại”.

Not-found không tự phân biệt document chưa từng tồn tại, đã `remove`, đã hết hạn TTL hay lookup sai collection.

## 12. SDK `exists` khi chỉ cần boolean

~~~java
var result = orders.exists("order::O-2026-001");
boolean present = result.exists();
~~~

EXISTS có thể tránh việc tải và decode cả JSON nếu đầu ra nghiệp vụ chỉ là boolean. Nhưng nó không khóa document: ngay sau lần gọi, key vẫn có thể bị thay đổi hoặc xóa.

Nếu phải kiểm tra trạng thái `PAID` rồi sửa order, EXISTS **không đủ**. Cần đọc content và dùng CAS/transaction phù hợp với nghiệp vụ.

## 13. `lookupIn` khi chỉ cần một vài field của JSON lớn

Couchbase Java SDK hỗ trợ subdocument lookup theo key và JSON path:

~~~java
import java.util.List;
import com.couchbase.client.java.kv.LookupInSpec;
import com.couchbase.client.java.kv.LookupInResult;

LookupInResult read = orders.lookupIn(
        "order::O-2026-001",
        List.of(
                LookupInSpec.get("status"),
                LookupInSpec.get("total")
        )
);

String status = read.contentAs(0, String.class);
Long total = read.contentAs(1, Long.class);
~~~

Nó có thể giảm băng thông so với tải một order lớn chỉ để lấy status/total. Tuy nhiên, trường thiếu/path sai có thể tạo lỗi; phải kiểm tra schema và xử lý theo SDK version.

**Đừng lạm dụng subdocument** cho document nhỏ hoặc khi cần hầu hết field. Subdocument cũng có chi phí; nên benchmark theo kích thước thực.

### 13.1. Khác biệt với SQL++ projection

- `lookupIn`: biết một document ID và một số path.
- SQL++ projection: có thể tìm nhiều document theo predicate rồi chọn một số field.

Cả hai giảm dữ liệu trả về theo cách khác nhau, nhưng không đi cùng đường Query/Index.

## 14. SQL++ theo `META().id`: có thể làm được, chưa chắc cần thiết

Ví dụ SQL++:

~~~sql
SELECT o.*
FROM `commerce`.`sales`.`orders` AS o
WHERE META(o).id = "order::O-2026-001";
~~~

Query optimizer có thể nhận ra predicate theo ID và sử dụng một plan đọc key hiệu quả, không nhất thiết full scan. Nhưng request vẫn đi qua Query service và SQL++ execution. Nếu chỉ cần document đã biết key, KV GET thường đơn giản hơn.

### 14.1. SQL++ `USE KEYS`

~~~sql
SELECT o.*
FROM `commerce`.`sales`.`orders` AS o
USE KEYS ["order::O-2026-001", "order::O-2026-002"];
~~~

`USE KEYS` cho phép chỉ định key trong query, thường tránh việc tìm key qua secondary index. Dù vậy đây **vẫn là SQL++**. Nó phù hợp nếu còn cần projection/kết hợp cấu trúc truy vấn; không nên nhầm với SDK KV GET.

## 15. Khi SQL++ mới là lựa chọn đúng

| Yêu cầu | Vì sao không giải quyết bằng một GET |
| --- | --- |
| Tìm order theo customerId và status | Không biết key từng order |
| Lấy 20 đơn hàng mới nhất | Filter, sort, limit nhiều records |
| Thống kê doanh thu tháng | Aggregation |
| Join order và shipment | Kết hợp nhiều document |
| Truy vấn nhiều thuộc tính tìm kiếm | Cần predicate và index |
| Tìm full-text hoặc vector | Cần khả năng tìm kiếm chuyên dụng |
| Báo cáo tập dữ liệu lớn | Cân nhắc Query/Analytics/batch |

Ví dụ:

~~~sql
SELECT META(o).id AS id, o.status, o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND o.status = $status
ORDER BY o.total DESC
LIMIT 20;
~~~

Đây là query cần index phù hợp với predicate/sort. Không thể thay bằng KV GET khi caller chưa có danh sách document IDs.

### 15.1. Derived method khác `findById`

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderSearchRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByCustomerIdAndStatus(
            String customerId, String status);
}
~~~

Method tìm theo field thường dùng SQL++/index; `findById` truy cập document key. Cùng một repository nhưng hai đường truy cập khác nhau, không thể suy thời gian phản hồi từ method này sang method kia.

## 16. Có nhiều document IDs: tránh GET tuần tự nếu chi phí lớn

Một vòng lặp GET blocking 100 keys sẽ tạo nhiều thao tác tuần tự:

~~~java
for (String id : orderIds) {
    var result = orders.get(id);
    process(result);
}
~~~

Nếu network latency chiếm tỷ trọng đáng kể, tổng thời gian có thể cao. Một lựa chọn là dùng **nhiều KV operations đồng thời với giới hạn**.

### 16.1. `findAllById` qua repository

~~~java
Iterable<OrderDocument> found =
        repository.findAllById(orderIds);
~~~

Spring Data cung cấp abstraction này, nhưng **không tự giả định một network round trip**. Cần đo implementation version thực tế và batch size điển hình.

### 16.2. Reactor với concurrency được khống chế

~~~java
import java.util.List;
import com.couchbase.client.core.error.DocumentNotFoundException;
import com.couchbase.client.java.json.JsonObject;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

List<String> ids = List.of(
        "order::O-2026-001",
        "order::O-2026-002",
        "order::O-2026-003"
);

Flux<JsonObject> documents =
        Flux.fromIterable(ids)
                .flatMap(
                        id -> orders.reactive()
                                .get(id)
                                .map(r -> r.contentAsObject())
                                .onErrorResume(
                                        DocumentNotFoundException.class,
                                        ex -> Mono.empty()
                                ),
                        16
                );
~~~

`flatMap(..., 16)` là ví dụ giới hạn số inner publishers đang hoạt động, không phải ngưỡng tối ưu được công bố cho mọi cluster.

Nếu cần giữ thứ tự đầu vào, `flatMap` không bảo đảm thứ tự; xét `flatMapSequential` hoặc gắn ID vào kết quả. Không nuốt timeout thành `Mono.empty()` để cho batch trông như hoàn tất dù có sự cố.

### 16.3. Đừng flooding Data service

Concurrency 16 trên một request không có nghĩa 1000 requests đồng thời đều có thể phát thêm 16 operations mà không ảnh hưởng cluster. Cần xem **tổng concurrency qua mọi instance**, timeout, CPU, rate limit và tải node.

## 17. Reactive repository theo ID

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;

public interface ReactiveOrderRepository
        extends ReactiveCouchbaseRepository<OrderDocument, String> {
}
~~~

Service:

~~~java
import reactor.core.publisher.Mono;

Mono<OrderDocument> load(
        ReactiveOrderRepository repository, String orderId) {
    return repository.findById(
            OrderKeys.fromBusinessId(orderId));
}
~~~

Một `Mono` thể hiện pipeline bất đồng bộ; khi chưa subscribe thì operation chưa nhất thiết thực thi. Reactive không tự làm server xử lý một key nhanh hơn, nhưng có thể giúp quản lý I/O/concurrency khi workload phù hợp.

Không gọi `block()` trên WebFlux event loop. Trong Spring MVC đồng bộ, blocking access vẫn có thể phù hợp nếu thread budget và latency được đo hợp lý.

## 18. CAS: đọc theo key rồi ghi có điều kiện

~~~java
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.kv.ReplaceOptions;

String key = "order::O-2026-001";
GetResult existing = orders.get(key);

var updated = existing.contentAsObject();
updated.put("status", "SHIPPED");

orders.replace(
        key,
        updated,
        ReplaceOptions.replaceOptions()
                .cas(existing.cas())
);
~~~

CAS giúp ngăn ghi đè dữ liệu dựa trên một phiên bản cũ. Nếu writer khác đã thay đổi document, replace có thể báo conflict.

**Hai lưu ý:**

1. `replace` gửi lại **toàn bộ JSON**; cần bảo toàn field, metadata mapping và type information.
2. Nếu document có TTL, replace không chỉ định expiry có thể đổi expiry theo semantics server/operation. Cần dùng `preserveExpiry(true)` hoặc option phù hợp khi nghiệp vụ yêu cầu giữ hạn.

Spring Data `@Version` có thể xử lý optimistic locking qua mapper, nhưng SDK raw JSON không tự đọc annotation Java đó.

## 19. Một GET không tạo giao dịch nhiều document

Một nghiệp vụ có thể cần đồng thời cập nhật:

~~~text
order::O-2026-001
inventory::SKU-001
payment::P-001
~~~

Đã biết cả ba key không có nghĩa ba mutation KV sẽ tự là một transaction. Cần đánh giá transaction Couchbase, outbox hoặc saga theo mức nhất quán/side effects.

Không chọn SQL++ chỉ vì muốn “transaction” và cũng không chọn KV chỉ vì “nhanh”. Atomicity và consistency là yêu cầu khác với đường lookup.

## 20. TTL, not-found và GET-AND-TOUCH

KV GET không bỏ qua expiry metadata. Khi document hết hạn logic, kết quả có thể là `DocumentNotFoundException`. Một key không thấy không nhất thiết do TTL: có thể chưa tạo, đã remove hoặc trỏ sai collection.

Không thay `get` bằng `getAndTouch` nếu chỉ muốn tối ưu read:

~~~java
var cart = carts.getAndTouch(
        "cart::u-42",
        java.time.Duration.ofMinutes(30)
);
~~~

GET-AND-TOUCH vừa đọc vừa **đặt lại expiry**, có thể gia hạn document ngoài ý định. Với OTP, session hoặc reservation có deadline cố định, đây có thể là lỗi bảo mật/logic nghiệp vụ.

Bucket/collection `maxTTL` vẫn có hiệu lực dù dữ liệu được đọc qua KV thay vì SQL++.

## 21. KV không phải đợi secondary index

Một lookup theo document key được thực hiện qua KV/Data service và không cần GSI phản ánh mutation mới. Đây là điểm quan trọng khi so sánh với một SQL++ query theo field, nhất là ngay sau upsert.

SQL++ có các lựa chọn scan consistency như `NOT_BOUNDED` và `REQUEST_PLUS` để điều khiển yêu cầu index visibility, có thể làm tăng latency của query. **Không cần áp scan consistency của SQL++ cho một SDK KV GET**, vì nó không đi qua cùng đường index.

Tuy vậy, vẫn phải xét hợp đồng đọc cụ thể nếu hệ thống dùng replica reads, transaction, failover hoặc result cache. Không tuyên bố mọi đường đọc luôn nhìn thấy trạng thái giống hệt nhau tại cùng một mili giây.

## 22. Lúc đã dùng SQL++, hãy xem query plan

~~~sql
EXPLAIN
SELECT META(o).id AS id, o.status
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = "u-42";
~~~

Kiểm tra:

- Index nào được sử dụng?
- Có primary/full scan ngoài ý định không?
- Predicate có thể dùng index không?
- Có fetch content sau index scan không?
- Sorting và LIMIT được thực thi thế nào?
- Có join/aggregation làm tăng lượng dữ liệu trung gian không?

Đừng tạo secondary index chỉ để hỗ trợ một use case có thể giải quyết bằng KV key lookup.

## 23. Document lớn: KV GET cũng phải trả giá truyền dữ liệu

Một KV GET document 1 MB vẫn tốn network và deserialization, dù không qua Query service.

Tối ưu có thể là:

- Dùng `lookupIn` nếu chỉ cần status hoặc một path.
- Tách metadata hay đọc khỏi payload lớn ít đọc.
- Tránh lưu toàn bộ lịch sử giao dịch vào một document quá lớn.
- Không GET cùng document lặp lại không cần thiết trong một request.
- Cân nhắc cache an toàn nếu đọc lặp và dữ liệu ít đổi.

Không áp một tối ưu subdocument lên mọi document 200 byte; benchmark trước.

## 24. Hot key: đường KV nhanh nhưng cạnh tranh có thể cao

Một key như:

~~~text
counter::global-checkouts
~~~

nếu bị hàng nghìn writer cập nhật đồng thời có thể trở thành điểm nóng, gây CAS conflict và tail latency, dù truy cập hoàn toàn bằng KV.

Giải pháp cần cân nhắc theo yêu cầu nhất quán:

1. Shard counter/aggregate theo key hoặc time bucket.
2. Giảm số mutation lên cùng document.
3. Dùng counter operation hoặc mô hình event phù hợp.
4. Gom kết quả batch khi chấp nhận eventual consistency.
5. Theo dõi CAS retries và tỷ lệ phân bố tải.

Không thiết kế một giant document toàn cầu chỉ vì “đọc theo một key rất đơn giản”.

## 25. Tái sử dụng kết nối và collection handle

Không `Cluster.connect()` cho mỗi request rồi `disconnect()` ngay sau GET. Việc khởi tạo client mới có overhead kết nối, TLS, resource management và có thể làm giảm throughput.

Trong Spring Boot, dùng client/factory do Spring quản lý, lấy `Collection` handle một lần để dùng chung, để ApplicationContext xử lý vòng đời tài nguyên.

Tuning KV timeout, retry strategy và môi trường SDK phải dựa trên metrics/SDK version, không chỉ tăng timeout thật lớn để che giấu cluster quá tải.

## 26. Cache theo ID: tăng tốc nhưng không được trả dữ liệu sai

Dữ liệu product ít đổi có thể cache; trạng thái order hoặc session cần xem consistency, revoke và deadline.

Một cache key chỉ dựa vào `orderId` có thể sai nếu order ID không duy nhất trên nhiều tenant hoặc response phụ thuộc quyền người đọc. Cần gắn tenant/authorization context hợp lý và thiết kế invalidation.

Cache hit không phải KV GET mới. Một cached session hết hạn hoặc bị revoke trên Couchbase vẫn có thể bị trả lại nếu cache TTL dài hơn business deadline. Tối ưu hit rate không thay thế quyền truy cập và tính đúng đắn.

## 27. Đo trước và sau tối ưu

| Metric | Đọc theo key | SQL++ |
| --- | --- | --- |
| p50/p95/p99 latency | Theo KV operation | Theo query và consistency |
| Throughput | KV req/s | Query req/s, cùng các service liên quan |
| Bytes truyền | Theo JSON/subdocument | Theo projection/result |
| App CPU | Decode và mapping | Parse result và mapping |
| Server load | Data service | Query/Index/Data tùy plan |
| Error rate | Not-found, KV timeout | Query timeout, index errors |
| Concurrency | Số KV operations đang chạy | Query concurrency, queueing |
| Index dependency | Không cho GET theo key | Có thể cần cho predicate |

Kịch bản benchmark nên tách:

~~~text
A. KV GET một document 2 KB
B. KV GET một document 100 KB
C. KV LOOKUP_IN hai field của document 100 KB
D. SQL++ WHERE META().id = một key
E. SQL++ USE KEYS danh sách 20 key
F. 20 KV GET với concurrency 4/16/32
G. SQL++ tìm theo customerId có index
~~~

Thử với cùng dataset, topology, TLS, số clients, warm-up và lượng request hợp lý. Không so một query trả 1000 rows với một GET trả một document rồi tuyên bố tỷ lệ chênh lệch là do framework.

### 27.1. Vì sao cần p95/p99?

Average thấp có thể che tail latency cao khi server chịu tải, mạng dao động hoặc một key nóng bị tranh chấp. Với hot endpoint, p95/p99, tỷ lệ timeout và throughput theo tải là chỉ số hữu ích hơn một lần chạy local.

## 28. Kiểm thử sau khi đổi repository sang SDK

Một integration test nên:

1. Tạo unique document key trong collection test.
2. Lưu entity bằng repository, qua converter thật.
3. `repository.findById(key)` đọc ra đúng entity.
4. SDK `Collection.get(key)` đọc đúng JSON ở cùng keyspace.
5. Nếu SDK update, đảm bảo repository còn deserialize được entity.
6. Xác minh CAS/`@Version` nếu entity có optimistic locking.
7. Xác minh TTL/`@Document(expiry)` nếu document có expiry.
8. Cleanup chỉ key test của bài.

Không tạo raw JSON bằng SDK rồi mặc định mọi entity mapper sẽ đọc được: Spring Data có thể yêu cầu type information và field conversion mà JSON tự viết chưa cung cấp.

### 28.1. Unit test key factory

~~~java
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class OrderKeysTest {

    @Test
    void createsExpectedDocumentKey() {
        assertThat(OrderKeys.fromBusinessId("O-2026-001"))
                .isEqualTo("order::O-2026-001");
    }
}
~~~

Đơn giản nhưng hiệu quả: key prefix sai làm lookup thất bại mà không phải lỗi hiệu năng.

### 28.2. Test SQL++ riêng với KV

Test repository `findById` không chứng minh derived query hoạt động. Nếu cần `findByCustomerIdAndStatus`, phải provision index phù hợp, chọn scan consistency theo yêu cầu và kiểm tra query plan độc lập.

## 29. Bảng chẩn đoán vấn đề thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Có ID nhưng query chậm | Dùng SQL++ không cần thiết | Thử KV GET theo key |
| `findById` trả empty | Truyền business ID thay vì document key | Xác minh key factory |
| SDK GET báo not-found | Sai bucket/scope/collection hoặc key đã mất | Kiểm tra namespace, expiry và delete |
| EXISTS đúng nhưng GET ngay sau fail | Race giữa hai operation | Bỏ check thừa, xử lý not-found |
| SDK đọc được nhưng repository decode lỗi | Thiếu type metadata/field mapping | Thống nhất converter/schema |
| SDK update làm mất TTL | Không preserve hoặc sai options | Kiểm tra expiry metadata |
| Derived query không thấy data vừa ghi | Index consistency | Kiểm tra Query plan, REQUEST_PLUS khi phù hợp |
| Truy vấn theo customerId rất chậm | Thiếu index hoặc plan không tốt | EXPLAIN và index phù hợp |
| Đọc 100 keys tuần tự chậm | Tổng network latency | Bounded concurrency |
| Reactive GET không chạy | Chưa subscribe | Kiểm tra pipeline và signal |
| API chỉ đọc mà làm mới TTL | Dùng getAndTouch | Chuyển GET thuần |
| Update mất dữ liệu | Replace JSON thiếu field hoặc không CAS | Full content + CAS |
| Chỉ một key có latency cao | Hot key/CAS conflict | Xem data model và mutation rate |
| p50 đẹp nhưng người dùng than chậm | Tail latency cao | Đo p95/p99, timeout, load |
| Cache trả sai user | Cache key/authorization thiếu tenant | Cô lập cache và kiểm tra quyền |
| Cluster outage bị báo 404 | Catch mọi exception thành empty | Phân loại not-found và timeout |

## 30. Tình huống thực hành

Ứng dụng checkout có:

~~~text
GET /orders/{orderId}
GET /customers/{customerId}/orders?status=PAID
GET /orders/{orderId}/status
POST /orders/{orderId}/ship
GET /carts/{userId}
GET /reports/revenue?month=2026-11
~~~

Keyspace:

~~~text
commerce.sales.orders
commerce.checkout.carts
commerce.reporting.daily_totals
~~~

**Câu hỏi:**

1. Với GET một order, khi nào dùng repository `findById` và khi nào dùng SDK `get`?
2. Nếu field `orderId` khác document ID, vì sao `findById(orderId)` có thể rỗng?
3. Danh sách order theo customerId cần SQL++/index như thế nào?
4. Chỉ đọc status trên document lớn có thể dùng `lookupIn` không?
5. Khi cập nhật status cùng lúc ở hai request, CAS giúp giải quyết gì?
6. Vì sao không dùng `exists` rồi `get` để giảm lỗi?
7. Nếu có 50 keys, nên giới hạn `flatMap` concurrency ra sao?
8. Query `USE KEYS` có được coi là SDK KV GET không?
9. Vì sao `REQUEST_PLUS` không cần cho một GET trực tiếp theo key?
10. Đổi repo sang SDK cần kiểm tra converter, expiry và `@Version` nào?
11. Nếu order ID dễ đoán, tối ưu theo key có làm giảm nhu cầu kiểm tra quyền không?
12. Hãy đề xuất benchmark đo latency p95/p99, CPU, network bytes và index dependency.

**Định hướng:** khi đã biết keyspace + document ID thì ưu tiên KV; SQL++ dùng cho predicate/join/aggregate. Tối ưu cần đảm bảo mapping, CAS, TTL, authorization, concurrency và được chứng minh bằng benchmark.

## 31. Checklist production

- [ ] Phân biệt document ID với business ID/field JSON.
- [ ] Đã xác định chính xác bucket/scope/collection.
- [ ] Chọn `findById`/template theo ID khi muốn entity mapping.
- [ ] Dùng SDK `get` khi cần KV JSON/options trực tiếp.
- [ ] `exists` chỉ dùng khi thật sự cần boolean.
- [ ] Không EXISTS rồi GET nếu mục tiêu cuối là lấy content.
- [ ] Đánh giá `lookupIn` khi document lớn, chỉ cần vài field.
- [ ] Không dùng SQL++ chỉ để tìm một key đã biết nếu KV đủ.
- [ ] Dùng SQL++ đúng chỗ: predicate, sort, join, aggregate.
- [ ] Kiểm tra Query index/EXPLAIN nếu dùng derived query.
- [ ] Nhiều keys được đọc bằng concurrency có giới hạn.
- [ ] Reactive pipeline không block event loop.
- [ ] Khi update, CAS/`@Version` được xử lý đúng.
- [ ] Mapping/type metadata không mất khi dùng SDK raw JSON.
- [ ] Không thay TTL/`maxTTL` ngoài chính sách nghiệp vụ.
- [ ] Getter read-only không gọi getAndTouch trái ý định.
- [ ] Phân biệt document-not-found với timeout/outage/RBAC error.
- [ ] Kiểm tra tenant/authorization dù caller đã biết ID.
- [ ] Reuse Spring-managed client và collection handle.
- [ ] Cache theo key có invalidation và isolation phù hợp.
- [ ] Đo p95/p99, throughput, bytes và server load trên workload thật.
- [ ] Regression test đường repository, SDK, SQL++ liên quan.

## 32. Tổng kết

Khi đã biết **document key và collection chính xác**, đường **Key-Value** là lựa chọn ưu tiên cho những thao tác một document: `CouchbaseRepository.findById`, `CouchbaseTemplate.findById`, SDK `Collection.get`, `exists` hoặc `lookupIn`. Không cần đưa một lookup đơn giản qua Query service hoặc secondary index khi KV đáp ứng đầy đủ.

SQL++ vẫn là công cụ đúng khi caller chỉ biết **điều kiện tìm kiếm**, cần đọc nhiều document, lọc/sắp xếp, join hay tổng hợp. Tối ưu hiệu năng không chỉ là chọn API: còn phải thiết kế key, giữ converter, CAS/TTL, bảo đảm quyền, giới hạn reactive concurrency và tránh hot key.

Bằng cách đo các luồng truy cập thực và kiểm thử sau refactor, tầng Spring Data Couchbase có thể tận dụng ưu điểm KV theo ID mà vẫn duy trì đúng tính nhất quán, hiệu năng và khả năng vận hành của hệ thống.

