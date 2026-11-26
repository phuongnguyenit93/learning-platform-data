# Thay cập nhật toàn tài liệu bằng sub-document khi phù hợp

## 1. Vấn đề: chỉ đổi một trường nhưng phải gửi lại cả document

Một order trong Couchbase chứa trạng thái, thông tin khách hàng, danh sách sản phẩm, địa chỉ giao hàng, thông tin khuyến mại và lịch sử hoạt động. Một endpoint chỉ cần ghi trạng thái `SHIPPED` hoặc tăng bộ đếm lần xem. Nếu service luôn thực hiện:

~~~text
KV GET toàn document
    -> deserialize JSON / map entity
    -> thay một field
    -> serialize toàn document
    -> KV REPLACE toàn document
~~~

thì kích thước JSON, chi phí chuyển đổi, băng thông và cạnh tranh ghi có thể lớn hơn mức công việc thực sự cần. Với document 80 KiB, thay một số nguyên hoặc chuỗi ngắn không nhất thiết cần client truyền lại 80 KiB.

**Sub-document operations** trong Couchbase cho phép đọc hoặc sửa một phần JSON theo path, qua **KV Data service** thay vì Query service. Lệnh `mutateIn` có thể gom nhiều thao tác sửa path của **cùng một document** vào một mutation có tính nguyên tử; `lookupIn` chỉ đọc một số path khi cần.

Bài **“Thay cập nhật toàn tài liệu bằng sub-document khi phù hợp”** thuộc chương **Hiệu năng** của module **SPRING_DATA_COUCHBASE**. Phạm vi module là xây dựng tầng truy cập Couchbase với document mapping, repository, `CouchbaseTemplate`, truy vấn SQL++; thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và lựa chọn API reactive để đảm bảo hiệu năng, nhất quán và khả năng vận hành.

**Kết quả học tập:**

1. Biết khi nào `mutateIn` phù hợp hơn `get + replace` hay `repository.save`.
2. Sử dụng các phép `upsert`, `replace`, `insert`, `remove`, `increment` và array operations theo path.
3. Hiểu nguyên tử **nhiều path trong một document**, giới hạn số specs và khác biệt với transaction.
4. Phân biệt path-level semantics với document-level `StoreSemantics`.
5. Dùng CAS khi quyết định ghi phụ thuộc vào trạng thái đã đọc; tránh lost update và race.
6. Giữ TTL bằng `preserveExpiry(true)` hoặc đặt deadline phù hợp, không âm thầm hồi sinh document.
7. Tích hợp SDK KV với Spring Data mà không phá schema/converter/`@Version`.
8. Dùng reactive/async có giới hạn concurrency và retry/idempotency phù hợp.
9. Benchmark latency, bytes, index maintenance, error rate và tính đúng đắn trước khi tối ưu.

Ví dụ theo phong cách Java 17, Spring Boot 3.x, Spring Data Couchbase 5.x, Couchbase Java SDK 3.x, Couchbase Server 7.x trở lên khi dùng `preserveExpiry(true)`. API và hành vi phụ thuộc phiên bản chính xác; phần ví dụ chuyên biệt cần kiểm chứng bằng integration test với server đang dùng.

## 2. Một document mẫu để đối chiếu

Bucket/scope/collection:

~~~text
Bucket: commerce
Scope: sales
Collection: orders
Document ID: order::O-2026-001
~~~

JSON:

~~~json
{
  "docType": "order",
  "customerId": "u-42",
  "status": "PAID",
  "total": 150000,
  "updatedAtEpochMs": 1795582800000,
  "shipping": {
    "city": "Ho Chi Minh City",
    "method": "STANDARD"
  },
  "metrics": {
    "viewCount": 41
  },
  "statusHistory": [
    {"status": "CREATED", "at": "2026-11-25T09:00:00Z"},
    {"status": "PAID", "at": "2026-11-25T09:10:00Z"}
  ],
  "items": [
    {"sku": "SKU-A", "quantity": 2},
    {"sku": "SKU-B", "quantity": 1}
  ]
}
~~~

Các thay đổi có thể xảy ra:

| Nghiệp vụ | Phần cần sửa | Khả năng dùng sub-document |
| --- | --- | --- |
| Cập nhật `shipping.city` | Một scalar | Phù hợp nếu không đổi nhiều bất biến |
| Tăng `metrics.viewCount` | Một counter | `increment` là ứng viên tốt |
| Đánh dấu `status = SHIPPED` | Một field, nhưng có state transition | Dùng CAS và xác minh business rule |
| Ghi `status` + `updatedAt` | Hai paths | Một `mutateIn` có nhiều specs |
| Thêm event lịch sử | Append vào array | Phù hợp nếu kích thước mảng được kiểm soát |
| Thay toàn bộ `items` và giá tiền/tổng | Nhiều fields liên quan | Cân nhắc full replace/CAS hoặc transaction theo ngữ nghĩa |
| Thay model JSON toàn bộ | Hầu hết nội dung | Full document update thường rõ ràng hơn |
| Cập nhật order và inventory khác document | Nhiều documents | Sub-document **không đủ** làm multi-document transaction |

## 3. Phân biệt full-document và sub-document

~~~mermaid
flowchart TD
    A["Yêu cầu ghi thay đổi"] --> B{"Sửa bao nhiêu phần JSON?"}
    B -- "Hầu hết nội dung" --> C["Full replace / repository.save"]
    B -- "Một vài paths" --> D{"Có phụ thuộc state cũ?"}
    D -- "Không, update độc lập" --> E["SDK mutateIn"]
    D -- "Có invariant/state transition" --> F["Read state + CAS mutateIn"]
    F --> G{"Liên quan nhiều documents?"}
    G -- "Có" --> H["Transaction / saga / outbox"]
    G -- "Không" --> E
    E --> I["Test TTL, mapping, errors và benchmark"]
    C --> I
    H --> I
~~~

### 3.1. Lợi ích có thể đạt

- Client gửi **paths và values thay đổi**, thay vì serialize lại JSON lớn.
- Tránh một bước GET đầy đủ nếu mutation không cần xem nội dung trước đó.
- Gom nhiều path edits của cùng document trong **một operation**.
- Tránh overwrite các phần JSON độc lập do ứng dụng gửi một bản sao cũ.
- Có thể giảm byte truyền, CPU serialize/map và thời gian một số hot path.

### 3.2. Điều không được mặc định

Sub-document **không bảo đảm** server chỉ ghi đúng từng byte của JSON xuống disk, không loại bỏ chi phí cập nhật index, không tự giải quyết mọi race và không tự nhanh hơn trong mọi workload. Phải đo tác động thực lên KV latency, server CPU, mutation throughput và index maintenance.

## 4. SDK Java 3.x: mở Collection đúng keyspace

Trong Spring Boot, tái sử dụng SDK client do Spring Data quản lý:

~~~java
import com.couchbase.client.java.Collection;
import org.springframework.data.couchbase.core.CouchbaseClientFactory;

public final class OrderKvAccess {

    private final Collection orders;

    public OrderKvAccess(CouchbaseClientFactory factory) {
        this.orders = factory.getBucket()
                .scope("sales")
                .collection("orders");
    }

    public Collection collection() {
        return orders;
    }
}
~~~

Helper này cần được đăng ký bean hoặc tạo từ configuration của ứng dụng. Bucket `commerce` đã được cấu hình và scope/collection phải tồn tại. `Collection` handle nên dùng lại; **không tạo `Cluster.connect()` rồi `disconnect()` cho mỗi request**.

Spring Boot connection properties, RBAC và TLS vẫn cần cấu hình theo môi trường. Một document key chỉ có ý nghĩa khi đặt trong đúng bucket/scope/collection.

## 5. Bản đầy đủ: GET rồi REPLACE

Trước khi tối ưu, hiểu đường cũ:

~~~java
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.kv.ReplaceOptions;
import java.time.Instant;

String id = "order::O-2026-001";

GetResult current = orders.get(id);
var json = current.contentAsObject();

json.put("shipping",
        json.getObject("shipping")
                .put("city", "Da Nang"));
json.put("updatedAtEpochMs", Instant.now().toEpochMilli());

orders.replace(
        id,
        json,
        ReplaceOptions.replaceOptions()
                .cas(current.cas())
                .preserveExpiry(true)
);
~~~

Khi chạy thành công, `replace` gửi lại **toàn bộ JSON** đã sửa; với document lớn, chi phí đọc, serialize và truyền có thể đáng kể. CAS giúp chặn lost update nhưng cũng khiến thao tác có thể phải retry nếu người khác thay cùng document.

**Đoạn minh họa:** production cần validation, authorized update, timeout/retry và xử lý null của `shipping`. `preserveExpiry(true)` ở Server 7.0+ cần được kiểm tra thực tế.

## 6. Thay bằng `mutateIn` trên hai path

SDK Java 3.x:

~~~java
import java.time.Instant;
import java.util.List;

import com.couchbase.client.java.kv.MutateInOptions;
import com.couchbase.client.java.kv.MutateInResult;
import com.couchbase.client.java.kv.MutateInSpec;
import com.couchbase.client.java.kv.StoreSemantics;

String id = "order::O-2026-001";
long updatedAt = Instant.now().toEpochMilli();

MutateInResult result = orders.mutateIn(
        id,
        List.of(
                MutateInSpec.replace(
                        "shipping.city", "Da Nang"),
                MutateInSpec.upsert(
                        "updatedAtEpochMs", updatedAt)
        ),
        MutateInOptions.mutateInOptions()
                .storeSemantics(StoreSemantics.REPLACE)
                .preserveExpiry(true)
);

long newCas = result.cas();
~~~

Ý nghĩa:

1. `replace("shipping.city", ...)` yêu cầu path tồn tại.
2. `upsert("updatedAtEpochMs", ...)` thêm hoặc thay field lá khi cha cần thiết có sẵn.
3. Các specs trong cùng `mutateIn` được xử lý như **một mutation nguyên tử trên document**.
4. `StoreSemantics.REPLACE` yêu cầu **document gốc đã tồn tại**; nó khác tên `replace` ở path.
5. `preserveExpiry(true)` giữ TTL metadata hiện có ở server hỗ trợ.
6. `result.cas()` là token phiên bản sau mutation để dùng nếu cần.

Không cần tải toàn bộ JSON về ứng dụng trong đường này. Tuy nhiên schema validation, business authorization và sự tương thích mapping vẫn do service chịu trách nhiệm.

## 7. Tính nguyên tử của nhiều specs

Ví dụ muốn sửa đồng thời `status` và timestamp:

~~~java
orders.mutateIn(
        id,
        List.of(
                MutateInSpec.replace("status", "PACKED"),
                MutateInSpec.upsert(
                        "updatedAtEpochMs",
                        Instant.now().toEpochMilli())
        ),
        MutateInOptions.mutateInOptions()
                .storeSemantics(StoreSemantics.REPLACE)
                .preserveExpiry(true)
);
~~~

Nếu một path operation thất bại, **toàn bộ mutation sub-document bị từ chối**, không để `status` đã đổi nhưng `updatedAtEpochMs` chưa đổi trong cùng lệnh.

Đây là atomicity **trong một document**. Nó không biến một lệnh `mutateIn` thành transaction bao gồm `order`, `inventory` và `payment` ở các keys khác nhau.

### 7.1. Giới hạn số specs

Couchbase sub-document API hỗ trợ **tối đa 16 operations trong một lệnh** theo tài liệu SDK hiện hành. Nếu cần thay hàng chục hoặc hàng trăm field, xem lại modeling và cân nhắc full-document mutation.

**Đừng tách 20 specs thành hai `mutateIn` rồi mặc định cả 20 vẫn là một transaction.** Hai lệnh riêng biệt có thể thành công/thất bại độc lập.

### 7.2. Một lệnh không có nghĩa “không conflict”

Atomicity bảo vệ không có partial update **bên trong một lệnh**. Hai client vẫn có thể cùng ghi field `status`, hoặc một client ghi full JSON trong khi client khác mutate path. Phải thiết kế concurrency/ordering riêng.

## 8. Các thao tác field path cần phân biệt

| Spec | Ý nghĩa | Hành vi khi field lá |
| --- | --- | --- |
| `MutateInSpec.replace(path, value)` | Thay field đã tồn tại | Lỗi nếu path không tồn tại |
| `MutateInSpec.insert(path, value)` | Thêm field mới | Lỗi nếu field đã tồn tại |
| `MutateInSpec.upsert(path, value)` | Thêm hoặc thay | Không yêu cầu field lá đã có |
| `MutateInSpec.remove(path)` | Xóa field | Lỗi nếu path không tồn tại |
| `MutateInSpec.increment(path, delta)` | Cộng số nguyên | Dùng atomic counter, có ràng buộc kiểu/range |
| `MutateInSpec.decrement(path, delta)` | Trừ số nguyên | Ràng buộc kiểu/range tương tự |
| `MutateInSpec.arrayAppend(path, values)` | Thêm vào cuối mảng | Path phải là array hoặc dùng cơ chế tạo phù hợp |
| `MutateInSpec.arrayPrepend(path, values)` | Thêm vào đầu mảng | Kiểm tra array type/size |
| `MutateInSpec.arrayAddUnique(path, value)` | Thêm scalar nếu chưa tồn tại | Giới hạn kiểu JSON và thứ tự |

Chọn spec có ý nghĩa **với business contract**; không dùng `upsert` cho mọi đường chỉ vì nó ít báo lỗi nhất.

## 9. `replace` và `upsert` ở path khác document-level UPSERT

Một nhầm lẫn dễ gặp:

~~~java
MutateInSpec.upsert("shipping.city", "Da Nang");
~~~

Lời gọi này mô tả **upsert JSON path**, **không tự bảo đảm tạo document gốc nếu key chưa tồn tại**.

Document-level semantics được cấu hình riêng:

~~~java
MutateInOptions.mutateInOptions()
        .storeSemantics(StoreSemantics.REPLACE);
~~~

Một bảng so sánh:

| Lớp | Giá trị | Ý nghĩa |
| --- | --- | --- |
| Document-level | `StoreSemantics.REPLACE` | Chỉ sửa document gốc có sẵn |
| Document-level | `StoreSemantics.INSERT` | Chỉ tạo document gốc chưa có |
| Document-level | `StoreSemantics.UPSERT` | Cho phép tạo hoặc ghi vào document |
| Path-level | `MutateInSpec.insert` | Field lá phải chưa có |
| Path-level | `MutateInSpec.replace` | Field lá phải có |
| Path-level | `MutateInSpec.upsert` | Field lá có hoặc chưa có |

Với order đã tồn tại, dùng `StoreSemantics.REPLACE` để tránh vô ý **hồi sinh document đã hết hạn**. Với document thực sự mới, hãy thiết kế API tạo mới rõ ràng và test schema/TTL.

## 10. Nested path và `createPath()`

Giả sử JSON có:

~~~json
{"shipping":{"city":"Ha Noi"}}
~~~

Lệnh:

~~~java
MutateInSpec.upsert(
        "shipping.method", "EXPRESS");
~~~

có thể thêm field `method` do cha `shipping` có sẵn.

Nhưng nếu chưa có `shipping`, thao tác vào `shipping.method` có thể báo `PathNotFoundException`. Khi nghiệp vụ cho phép tạo cả nhánh cha:

~~~java
MutateInSpec.upsert(
        "shipping.method", "EXPRESS")
        .createPath();
~~~

**Không bật `createPath()` vô điều kiện:** một lỗi gõ sai tên path như `shiping.method` có thể âm thầm tạo cấu trúc sai, khó phát hiện. Nên định nghĩa path constants, schema validation và integration tests.

### 10.1. Nếu field cha sai kiểu

Nếu `shipping` là chuỗi thay vì object, thao tác vào `shipping.city` có thể gặp lỗi kiểu/path. Đừng catch tất cả lỗi rồi tạo document mới; phải phân biệt schema cũ, dữ liệu lỗi và đường ghi cạnh tranh.

## 11. `insert` khi cần bảo vệ sự tồn tại của field

Một use case muốn ghi dấu thời điểm xác nhận **chỉ lần đầu**, có thể dùng:

~~~java
orders.mutateIn(
        id,
        List.of(MutateInSpec.insert(
                "approval.acceptedAt", acceptedAt)),
        MutateInOptions.mutateInOptions()
                .storeSemantics(StoreSemantics.REPLACE)
                .preserveExpiry(true)
);
~~~

Lệnh `insert` thất bại nếu field đã có; điều đó có thể giúp phát hiện ghi trùng. **Nhưng không tự đủ để xác minh nghiệp vụ**: còn cần kiểm tra trạng thái order, quyền user, deadline và side effects theo contract.

Với parent `approval` chưa tồn tại, cần khởi tạo cấu trúc hoặc dùng `createPath()` có chủ đích.

### 11.1. Khi nào `upsert` sẽ nguy hiểm?

Nếu muốn ghi `consumedAt` chỉ một lần mà dùng `upsert`, request lặp có thể ghi đè thời điểm đã có. Khi business yêu cầu one-time, cần state transition được kiểm tra/CAS/idempotency, không chỉ một phép gán field.

## 12. `remove` để xóa field cũ

~~~java
orders.mutateIn(
        id,
        List.of(MutateInSpec.remove(
                "legacyShipmentReference")),
        MutateInOptions.mutateInOptions()
                .storeSemantics(StoreSemantics.REPLACE)
                .preserveExpiry(true)
);
~~~

`remove(path)` xóa field JSON, không xóa toàn document.

Nếu field đã bị xóa hoặc chưa từng có, path removal có thể báo `PathNotFoundException`. Nếu migration cần idempotent cleanup, phải định nghĩa cách đối soát missing path, không catch mọi exception thành success.

**Bảo mật dữ liệu:** xóa một field khỏi document hiện tại không đồng nghĩa toàn bộ byte đã biến mất tức thời khỏi backups, replica hay downstream systems; retention cần chính sách riêng.

## 13. Counter nội bộ bằng `increment`

Ví dụ tăng số lần xem:

~~~java
import com.couchbase.client.java.kv.MutateInResult;

MutateInResult updated = orders.mutateIn(
        id,
        List.of(
                MutateInSpec.increment(
                        "metrics.viewCount", 1)
        ),
        MutateInOptions.mutateInOptions()
                .storeSemantics(StoreSemantics.REPLACE)
                .preserveExpiry(true)
);

Long count = updated.contentAs(0, Long.class);
~~~

`increment` thực hiện thao tác số ở server, tránh luồng:

~~~text
GET viewCount=41
A tính 42
B cũng tính 42
A replace 42
B replace 42
=> Mất một lần tăng
~~~

Với một counter độc lập, subdocument increment là ứng viên phù hợp hơn GET/replace toàn document.

### 13.1. Hạn chế và quyết định nghiệp vụ

- Counter phải là numeric integer phù hợp giới hạn server.
- Nếu field chưa tồn tại, SDK/server có thể tạo field counter theo semantics; nếu cha thiếu thì cần `createPath()` hoặc khởi tạo.
- Không coi increment là sự kiện idempotent. Một retry sau ambiguous timeout có thể **tăng hai lần**.
- Nếu số đếm gắn với quyền/billing, cần idempotency key hoặc record sự kiện, không chỉ increment vô điều kiện.
- Một hot key vẫn có thể chịu contention/tải cao dù không có lost update của read-modify-write thông thường.

### 13.2. Tại sao không luôn dùng CAS cho counter?

CAS giúp chặn ghi dựa trên phiên bản cũ, nhưng một increment đơn lẻ có thể hoạt động atomically mà không cần đọc CAS trước. Nếu business invariant phụ thuộc **nhiều field** hoặc trạng thái, cần điều kiện/CAS phù hợp. Không thêm GET + CAS vào mọi counter rồi vô tình loại bỏ lợi ích giảm round trip.

## 14. Array append và nguy cơ tăng kích thước document

Thêm một event:

~~~java
import com.couchbase.client.java.json.JsonObject;

JsonObject event = JsonObject.create()
        .put("status", "PACKED")
        .put("at", "2026-11-25T10:30:00Z");

orders.mutateIn(
        id,
        List.of(
                MutateInSpec.arrayAppend(
                        "statusHistory", List.of(event))
        ),
        MutateInOptions.mutateInOptions()
                .storeSemantics(StoreSemantics.REPLACE)
                .preserveExpiry(true)
);
~~~

`arrayAppend` yêu cầu array path hợp lệ, cho phép gửi **phần tử mới** thay vì gửi lại toàn bộ array/document qua client.

**Nhưng:** mảng lịch sử tăng vô hạn có thể biến một order thành document lớn và hot. Nếu audit history thực sự nhiều, cân nhắc lưu event thành document riêng hoặc stream/outbox để tránh unbounded growth.

### 14.1. Append không idempotent

Hai lần append cùng event tạo hai phần tử nếu không có cơ chế chống trùng. Với ambiguous timeout, đừng retry mù quáng rồi mong Couchbase tự loại duplicate. Xem xét event ID ổn định và dedupe ở tầng nghiệp vụ.

### 14.2. Array position có thể thay đổi

`arrayInsert("items[1]", ...)` và các thao tác theo index bị ảnh hưởng khi writer khác append/remove/insert. Nếu vị trí item mang ý nghĩa business, cân nhắc CAS và kiểm tra version. Tránh dùng vị trí mảng thay cho định danh bền vững khi dữ liệu thay đổi thường xuyên.

## 15. `arrayAddUnique` không phải unique constraint cho mọi object

SDK hỗ trợ thêm một scalar duy nhất vào array ở một số trường hợp:

~~~java
orders.mutateIn(
        id,
        List.of(
                MutateInSpec.arrayAddUnique(
                        "labels", "priority")
        )
);
~~~

Nếu giá trị đã có, thao tác có thể báo path-exists. Có giới hạn với JSON float, object hoặc array; không dùng nó như một cơ chế unique index tổng quát cho domain objects.

Thứ tự phần tử với “unique set” không phải semantics sắp xếp đáng tin cậy. Nếu business cần ordered events, sử dụng array append/event records với chiến lược khác.

## 16. Nhiều specs cùng một document khác nhiều operations song song

So sánh:

~~~java
// Một mutateIn: nhiều specs trên một document.
orders.mutateIn(
        id,
        List.of(
                MutateInSpec.replace("status", "PACKED"),
                MutateInSpec.upsert("updatedAtEpochMs", now),
                MutateInSpec.increment("metrics.updateCount", 1)
        )
);
~~~

với:

~~~java
// Ba lệnh độc lập: KHÔNG có nguyên tử chung.
orders.mutateIn(
        id, List.of(MutateInSpec.replace("status", "PACKED")));
orders.mutateIn(
        id, List.of(MutateInSpec.upsert("updatedAtEpochMs", now)));
orders.mutateIn(
        id, List.of(MutateInSpec.increment("metrics.updateCount", 1)));
~~~

Nếu lệnh thứ hai thất bại, trạng thái sau cùng có thể không đồng bộ. Gom các edits **cần đi cùng nhau** vào một `mutateIn` nếu giới hạn specs và schema cho phép.

Đừng nhầm `flatMap` nhiều mutateIn calls là “batch atomic”; các emissions trong Reactor không tạo một transaction chỉ vì nằm trong cùng publisher.

## 17. Path-level atomicity không đủ cho state transition

Ví dụ chỉ được đổi order từ `PAID` sang `PACKED`. Lệnh:

~~~java
orders.mutateIn(
        id,
        List.of(MutateInSpec.replace(
                "status", "PACKED"))
);
~~~

sẽ thay field hiện có mà **không biết giá trị trước là `PAID`, `CANCELLED` hay `SHIPPED`**. Đây là lỗi business nếu transition chỉ hợp lệ từ PAID.

Cần đọc trạng thái và dùng CAS/transaction phù hợp:

~~~mermaid
flowchart TD
    A["GET / lookupIn status + CAS"] --> B{"status = PAID?"}
    B -- "Không" --> C["Reject invalid transition"]
    B -- "Có" --> D["mutateIn status + updatedAt với CAS"]
    D --> E{"Mutation thành công?"}
    E -- "Có" --> F["Transition accepted"]
    E -- "CAS mismatch" --> G["Read lại + validate + retry hữu hạn"]
    E -- "Not found/expired" --> H["Reject hoặc xử lý theo contract"]
~~~

Atomicity bảo đảm các path trong mutation không bị nửa vời; **CAS** bảo đảm mutation chỉ áp lên phiên bản document đã kiểm tra.

## 18. `lookupIn` + CAS + `mutateIn`

Một ví dụ skeleton:

~~~java
import com.couchbase.client.java.kv.LookupInResult;
import com.couchbase.client.java.kv.LookupInSpec;
import com.couchbase.client.java.kv.MutateInOptions;
import java.time.Instant;
import java.util.List;

String id = "order::O-2026-001";

LookupInResult initial = orders.lookupIn(
        id,
        List.of(
                LookupInSpec.get("status"),
                LookupInSpec.get("customerId")
        )
);

String currentStatus = initial.contentAs(0, String.class);
String ownerId = initial.contentAs(1, String.class);

if (!"PAID".equals(currentStatus)) {
    throw new IllegalStateException("Invalid order transition");
}

authorizeOwner(ownerId, authenticatedUserId);

orders.mutateIn(
        id,
        List.of(
                MutateInSpec.replace("status", "PACKED"),
                MutateInSpec.upsert(
                        "updatedAtEpochMs",
                        Instant.now().toEpochMilli())
        ),
        MutateInOptions.mutateInOptions()
                .storeSemantics(StoreSemantics.REPLACE)
                .cas(initial.cas())
                .preserveExpiry(true)
);
~~~

Các hàm `authorizeOwner` và biến `authenticatedUserId` do tầng service cung cấp. Đây là ví dụ cơ chế, chưa xử lý retry và external side effects.

Nếu một writer khác sửa document giữa `lookupIn` và `mutateIn`, CAS mismatch là tín hiệu để đọc/kiểm tra lại. **Không bỏ CAS rồi retry bằng blind replace** vì sẽ làm sai state machine.

### 18.1. Đọc một vài field có đủ để validate không?

Nếu logic cần kiểm tra `status`, `paymentConfirmed`, `shippingMethod` và `fraudHold`, cần đọc tất cả field có liên quan hoặc dùng một cơ chế business invariant khác. LookupIn ít fields quá mức có thể khiến validation thiếu điều kiện quan trọng.

## 19. CAS mismatch và vòng retry đúng

Một vòng xử lý hợp lý:

1. Đọc content cần thiết và CAS.
2. Validate authorization và state transition.
3. Tạo mutation specs cho cùng phiên bản.
4. Gửi `mutateIn(...).cas(readCas)`.
5. Nếu CAS mismatch, **đọc lại** vì content đã đổi.
6. Kiểm tra lại toàn bộ business conditions; retry giới hạn nếu còn hợp lệ.
7. Với not-found hoặc expired, không tự chuyển sang UPSERT.
8. Với timeout mơ hồ, **đối soát trạng thái** trước khi retry nếu mutation không idempotent.

CAS có thể đổi cả khi writer khác chỉ sửa path không liên quan. Đây là trade-off: optimistic locking bảo vệ phiên bản document, nhưng hot document nhiều writers có thể tạo contention.

Không có giải pháp “CAS luôn tốt” hay “không CAS luôn tốt”. Cần chọn theo invariant của từng mutation.

## 20. Đường cập nhật độc lập: khi nào không cần GET?

Một mutation:

~~~java
orders.mutateIn(
        id,
        List.of(
                MutateInSpec.upsert(
                        "metrics.lastViewedAtEpochMs", now)
        ),
        MutateInOptions.mutateInOptions()
                .storeSemantics(StoreSemantics.REPLACE)
);
~~~

có thể phù hợp nếu:

- Endpoint đã xác thực quyền bằng nguồn tin cậy khác.
- Field last viewed không phụ thuộc các field trong document.
- Không cần điều kiện “chỉ cập nhật nếu status hiện là X”.
- Semantics last-write-wins được chấp nhận.
- TTL/expiry được cấu hình đúng (ví dụ cần preserve).

Nếu cập nhật dựa trên phiên bản đã đọc, không bỏ GET/CAS chỉ vì muốn cắt round trip. Cần phân loại từng đường nghiệp vụ.

## 21. TTL khi mutateIn: bẫy quan trọng

**Đừng mặc định sub-document mutation sẽ giữ nguyên expiry.** Trong Couchbase Java SDK 3.x, `MutateInOptions.preserveExpiry` có mặc định `false` theo tài liệu API; khi không chủ động preserve hoặc đặt expiry, mutation có thể làm thay đổi deadline theo server bucket/collection `maxTTL` và operation semantics.

Với OTP, session hard deadline, reservation hoặc dữ liệu tạm, thay một field **không đồng nghĩa được gia hạn hoặc xóa TTL**.

Ví dụ đúng với document cần giữ hạn:

~~~java
orders.mutateIn(
        id,
        List.of(
                MutateInSpec.upsert("status", "PACKED")
        ),
        MutateInOptions.mutateInOptions()
                .storeSemantics(StoreSemantics.REPLACE)
                .preserveExpiry(true)
);
~~~

`preserveExpiry(true)` yêu cầu Couchbase Server 7.0+ cho API tương ứng. Nếu triển khai trên version cũ, phải kiểm tra chiến lược đọc expiry/đặt lại `expiry(Instant)` với giới hạn race và CAS.

### 21.1. Gán deadline mới khi nghiệp vụ thật sự cho phép

Một giỏ hàng được làm mới TTL sau thao tác sửa hợp lệ có thể dùng:

~~~java
carts.mutateIn(
        cartId,
        List.of(
                MutateInSpec.upsert("lastEditedAt", nowString)
        ),
        MutateInOptions.mutateInOptions()
                .storeSemantics(StoreSemantics.REPLACE)
                .expiry(java.time.Duration.ofMinutes(30))
);
~~~

Đoạn ví dụ giả định `carts` là SDK `Collection` trỏ tới keyspace giỏ hàng, còn `cartId` và `nowString` do service cung cấp. Khi TTL có hard deadline, dùng `expiry(Instant)` hoặc giới hạn duration theo hard deadline, không refresh vô điều kiện.

### 21.2. `maxTTL` và CAS

Server maxTTL có thể áp deadline mặc định/giới hạn thời gian sống. `preserveExpiry` không làm một document bất tử hoặc miễn trừ policy. Khi cần fixed deadline, đọc metadata expiry và test end-to-end với đúng collection/version.

## 22. Metadata expiry phải được kiểm tra trên server

SDK có thể yêu cầu expiry:

~~~java
import com.couchbase.client.java.kv.GetOptions;

var read = orders.get(
        id,
        GetOptions.getOptions().withExpiry(true)
);

var expiry = read.expiryTime();
~~~

Một integration test:

1. Tạo document test với TTL 60 giây hoặc deadline tương lai.
2. Đọc metadata trước mutation.
3. Thực hiện `mutateIn` có `preserveExpiry(true)`.
4. Đọc metadata sau mutation.
5. Assert expiry không bị dịch vượt dung sai độ phân giải.
6. Assert content thay đổi đúng.
7. Kiểm tra mutation không hồi sinh document sau expiry.

Nếu chỉ kiểm tra `status == PACKED` thì có thể bỏ sót lỗi TTL bị reset; nếu chỉ kiểm tra expiry thì bỏ sót lỗi path update không đúng.

## 23. Phân loại lỗi sub-document đúng cách

| Lỗi/tín hiệu | Nguyên nhân thường gặp | Hành động |
| --- | --- | --- |
| `DocumentNotFoundException` | Document gốc không tồn tại, đã xóa/hết hạn, sai keyspace | Không tự UPSERT nếu đang update |
| `PathNotFoundException` | Field hoặc parent path không có | Xác minh schema/migration |
| `PathExistsException` | `insert` đã gặp field hiện hữu hoặc unique append conflict | Phân biệt request lặp |
| `PathMismatchException` | Path/object/array không đúng kiểu | Kiểm tra version schema |
| `CasMismatchException` | Writer khác cập nhật document | Đọc lại, validate, retry giới hạn |
| Timeout không rõ kết quả | Server có thể đã áp mutation | Đối soát/idempotency |
| Auth/RBAC error | Thiếu quyền trên collection | Không xem là missing path |
| Durability error | Không đạt yêu cầu độ bền đã chọn | Xử lý outcome theo SDK contract |

Không catch `Exception` rồi coi mutation thành công hoặc chuyển thành 404. Cần phân biệt lỗi business, mismatch schema, race và outage để monitoring/HTTP response phản ánh đúng vấn đề.

### 23.1. Một spec fail thì sao?

Với **multi-spec mutateIn**, nếu một mutation path lỗi, **toàn bộ mutation bị rollback về mặt logic** trên document. Đây là bảo đảm quan trọng nhưng không thay thế test: hãy kiểm tra cả những field còn lại chưa đổi sau khi cố tình đưa một path sai.

## 24. Retry: idempotent và non-idempotent khác nhau

Một số mutation lặp lại có thể cho cùng giá trị:

~~~java
MutateInSpec.upsert("shipping.city", "Da Nang");
~~~

Nhưng kết luận “retry luôn an toàn” vẫn cần xét timeout, CAS, TTL và side effects.

Những mutation thường **không idempotent**:

~~~java
MutateInSpec.increment("metrics.viewCount", 1);
MutateInSpec.arrayAppend("statusHistory", List.of(event));
~~~

Nếu request timeout sau khi server đã thực hiện increment/append, retry có thể tạo lần tăng hoặc event thứ hai.

Thiết kế:

- Operation/request ID ổn định.
- State machine/cờ consumed hoặc dedupe records có deadline đúng.
- Đọc lại kết quả khi ambiguous mutation.
- Không retry vô hạn trong WebFlux `retryWhen`.
- Nếu side effect bên ngoài như email, inventory hoặc payment, cần idempotency/outbox ở tầng phù hợp.

## 25. MutateIn không phải transaction đa document

Một order shipment có thể yêu cầu:

~~~text
order::O-2026-001   -> status=SHIPPED
inventory::SKU-A    -> reserved -= 2
shipment::S-001     -> created
~~~

Một lệnh `mutateIn` chỉ làm việc với **một document key**. Không thể gom ba document trên thành một multi-path mutation chỉ bằng cách đặt nhiều specs.

Nếu cần tính nguyên tử nhiều document, cân nhắc **Couchbase Transactions** trong phạm vi/version hỗ trợ. Với hệ thống ngoài Couchbase, dùng saga/outbox/idempotency theo contract. Đừng quảng cáo “subdocument atomic” như bảo đảm thanh toán và inventory đều commit.

### 25.1. Chi phí transaction và mục tiêu hiệu năng

Một giao dịch nhiều document thường tốn công việc hơn một mutateIn đơn. Nhưng nếu nghiệp vụ cần consistency, bỏ transaction để tăng throughput có thể làm sai dữ liệu. Benchmark phải giữ cùng correctness contract.

## 26. Spring Data entity mapping và `@Version`

Entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("sales")
@Collection("orders")
public class OrderDocument {

    @Id
    private String id;

    @Version
    private Long version;

    private String customerId;
    private String status;
    private Long total;
    private Long updatedAtEpochMs;

    protected OrderDocument() { }

    public String getId() { return id; }
    public Long getVersion() { return version; }
    public String getCustomerId() { return customerId; }
    public String getStatus() { return status; }
    public Long getTotal() { return total; }
    public Long getUpdatedAtEpochMs() { return updatedAtEpochMs; }
}
~~~

Repository:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {
}
~~~

`repository.save(entity)` qua mapper có thể sử dụng `@Version` để optimistic locking. Nhưng **SDK `Collection.mutateIn` trực tiếp không tự đọc annotation `@Version` hay lifecycle callbacks của Spring Data**.

### 26.1. Vấn đề hai writers dùng hai đường khác nhau

~~~text
Writer A: repository.findById -> entity version CAS c1
Writer B: SDK mutateIn status -> CAS c2
Writer A: repository.save(entity với CAS c1) -> conflict
~~~

Đây là hành vi tốt nếu optimistic locking đang hoạt động, vì tránh writer A ghi đè giá trị của B.

**Không chữa conflict bằng xóa `@Version`**. Hãy xác định rõ ownership từng field, điều kiện mutation, retry/reload và thời điểm dùng SDK path.

## 27. Spring Data repository không tự biến `save` thành sub-document

Một service:

~~~java
OrderDocument order = repository.findById(id)
        .orElseThrow();

order.changeStatus("PACKED");
repository.save(order);
~~~

vẫn thực hiện entity load + save theo mapping/operation behavior của Spring Data release. **Không mặc định repository.save tự suy ra “chỉ status thay đổi” rồi gửi mutateIn**.

Muốn dùng subdocument trong một service Spring Data, có thể thiết kế **custom repository fragment** hoặc một **KV gateway** dùng SDK handle do Spring quản lý:

~~~java
public interface OrderPatchGateway {
    long patchShippingCity(
            String documentId,
            String city);
}
~~~

Implementation:

~~~java
import java.util.List;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.MutateInOptions;
import com.couchbase.client.java.kv.MutateInSpec;
import com.couchbase.client.java.kv.StoreSemantics;

public final class SdkOrderPatchGateway
        implements OrderPatchGateway {

    private final Collection orders;

    public SdkOrderPatchGateway(Collection orders) {
        this.orders = orders;
    }

    @Override
    public long patchShippingCity(String id, String city) {
        validateCity(city);

        var result = orders.mutateIn(
                id,
                List.of(
                        MutateInSpec.replace(
                                "shipping.city", city)
                ),
                MutateInOptions.mutateInOptions()
                        .storeSemantics(StoreSemantics.REPLACE)
                        .preserveExpiry(true)
        );

        return result.cas();
    }

    private void validateCity(String city) {
        if (city == null || city.isBlank()) {
            throw new IllegalArgumentException(
                    "Shipping city is required");
        }
    }
}
~~~

Code còn cần authorization và business invariants; method trả CAS để service có thể dùng khi cần. Nếu `shipping.city` phải phụ thuộc trạng thái order, dùng lookup+CAS như ví dụ trước, không blind update.

## 28. Mapping JSON field name không trùng Java property

Spring Data có thể dùng:

~~~java
import org.springframework.data.couchbase.core.mapping.Field;

@Field("shipping_address")
private ShippingAddress shippingAddress;
~~~

Khi dùng SDK subdocument, path phải là **JSON đã lưu trên Couchbase**, không phải tên property Java:

~~~text
Java: shippingAddress.city
JSON: shipping_address.city
~~~

Đọc sai path có thể báo not-found hoặc tạo field trùng nếu dùng upsert/createPath.

Nếu converter tùy chỉnh serialize money, enum, timestamp hoặc type metadata, SDK raw JSON phải tuân thủ format đó. Trước khi chuyển một phần code sang SDK, hãy kiểm tra document được repository lưu thật và path mapping.

## 29. Lifecycle hooks, auditing và validation có thể không chạy

Spring Data có các cơ chế như auditing annotations, entity callbacks/converters, Bean Validation ở những nơi ứng dụng cấu hình. Một lệnh SDK `mutateIn` trực tiếp **không mặc định chạy các bước Java đó**.

Ví dụ ứng dụng mong `updatedAt` luôn do auditor cập nhật. Nếu chuyển từ `repository.save` sang `mutateIn("status")` mà quên update timestamp, có thể mất tính nhất quán nghiệp vụ.

Giải pháp:

- Định nghĩa `updatedAtEpochMs` là một spec trong cùng `mutateIn`.
- Validate đầu vào tại service/gateway trước khi gọi SDK.
- Giữ permissions và audit events ở tầng nghiệp vụ.
- Nếu có lifecycle side effects phức tạp, cân nhắc giữ repository save hoặc chuyển rõ logic sang service.
- Integration test hai đường ghi để phát hiện khác biệt.

Subdocument là tối ưu **data access**, không thay thế business domain layer.

## 30. Index/SQL++ vẫn chịu ảnh hưởng của mutation

Sửa một path bằng mutateIn không có nghĩa Index service có thể bỏ qua toàn bộ công việc duy trì index. Nếu field `status` đang được index:

~~~sql
CREATE INDEX ix_orders_status_created
ON `commerce`.`sales`.`orders` (
    status,
    updatedAtEpochMs DESC
);
~~~

thì mutation `status` hoặc `updatedAtEpochMs` vẫn có thể tạo index maintenance, ảnh hưởng mutation throughput và query visibility.

**Không tuyên bố “mutateIn chỉ ghi vài byte trên disk hoặc không cập nhật index”.** SDK gửi path/value nhỏ hơn, nhưng server cần duy trì document/index và durability theo engine/version.

### 30.1. Read-after-write qua Query service

Sau khi mutateIn trả thành công, KV GET theo key và SQL++ query dựa trên secondary index có thể có thời điểm quan sát khác nhau theo scan consistency.

- KV read theo key không phải đợi GSI.
- SQL++ `NOT_BOUNDED` có thể chưa thấy mutation mới.
- `REQUEST_PLUS` hoặc mutation-state consistency khi phù hợp có thể yêu cầu index đạt độ mới cần thiết, nhưng đổi lấy thời gian chờ.

Giữ đúng consistency contract khi benchmark trước/sau.

## 31. Durability và timeout của subdocument mutation

`MutateInOptions` hỗ trợ các cấu hình durability theo SDK Java 3.x. Ví dụ khi nghiệp vụ cần bảo đảm ghi cao hơn mặc định:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;

var result = orders.mutateIn(
        id,
        List.of(
                MutateInSpec.replace("status", "PACKED")
        ),
        MutateInOptions.mutateInOptions()
                .storeSemantics(StoreSemantics.REPLACE)
                .preserveExpiry(true)
                .durability(DurabilityLevel.MAJORITY)
);
~~~

Mức durability thực tế phải phù hợp cluster topology, latency SLO và nghiệp vụ. Không so mutateIn không durability với full replace có durability mạnh hơn rồi quy toàn bộ chênh lệch cho subdocument.

**Timeout của SDK không phải TTL của document.** Khi timeout mutation, đặc biệt ambiguous outcome, server có thể đã áp thay đổi. Retry phải được thiết kế theo idempotency.

## 32. Async và reactive API

Java SDK hỗ trợ blocking, async (`CompletableFuture`) và reactive (`Mono`). Ví dụ reactive mutation:

~~~java
import java.util.List;
import reactor.core.publisher.Mono;
import com.couchbase.client.java.kv.MutateInResult;

Mono<MutateInResult> patch =
        orders.reactive().mutateIn(
                id,
                List.of(
                        MutateInSpec.upsert(
                                "metrics.lastViewedAtEpochMs", now)
                ),
                MutateInOptions.mutateInOptions()
                        .storeSemantics(StoreSemantics.REPLACE)
                        .preserveExpiry(true)
        );
~~~

Không có yêu cầu rằng `Mono` đã chạy chỉ vì biến `patch` được tạo; operation thực thi khi publisher được subscribe trong đúng pipeline.

Đường reactive không tự khiến một mutateIn duy nhất nhanh hơn server xử lý; lợi ích chủ yếu là quản lý I/O, thread và concurrency theo workload.

### 32.1. Không gọi `block()` trong WebFlux event loop

Đừng chuyển pipeline reactive thành blocking bằng `patch.block()` trong handler WebFlux. Khi cần chờ kết quả, compose bằng `map`/`flatMap`/`then` và xử lý error signals.

## 33. Bounded concurrency trên nhiều document keys

Khi cần patch 100 documents độc lập:

~~~java
import reactor.core.publisher.Flux;

Flux<Long> newCasValues =
        Flux.fromIterable(documentIds)
                .flatMap(
                        documentId -> orders.reactive()
                                .mutateIn(
                                        documentId,
                                        List.of(
                                                MutateInSpec.upsert(
                                                        "batchProcessed", true)
                                        ),
                                        MutateInOptions.mutateInOptions()
                                                .storeSemantics(
                                                        StoreSemantics.REPLACE)
                                                .preserveExpiry(true)
                                )
                                .map(result -> result.cas()),
                        8
                );
~~~

`flatMap(..., 8)` giới hạn đồng thời ở cấp publisher của **một pipeline**; vẫn cần theo dõi tổng in-flight qua toàn bộ instances và requests. Không gán số 8 là ngưỡng tối ưu chung.

Các mutations giữa **nhiều document keys** trong ví dụ có thể thành công/thất bại độc lập, **không có transaction toàn batch**. Nếu muốn “tất cả hoặc không cái nào”, xem transaction hoặc thiết kế state machine/outbox phù hợp.

### 33.1. `flatMap` và thứ tự

`flatMap` không bảo đảm thứ tự output như input. Nếu order matters, dùng operator thích hợp và cân nhắc throughput trade-off. Nhiều mutations trên **cùng một key** gửi song song có thể cập nhật theo thứ tự không như người dùng mong đợi.

## 34. Benchmark đúng: giảm bytes chưa chắc giảm p99

So sánh hai phương án cùng business contract:

~~~text
A. GET toàn JSON -> sửa shipping.city -> REPLACE + CAS
B. LOOKUP_IN khi cần check -> MUTATE_IN paths + CAS
C. MUTATE_IN trực tiếp khi update độc lập
~~~

Đo:

| Metric | A | B | C |
| --- | --- | --- | --- |
| Số round trips | Đo | Đo | Đo |
| Request bytes | Đo | Đo | Đo |
| Response bytes | Đo | Đo | Đo |
| KV p50/p95/p99 | Đo | Đo | Đo |
| Business goodput/s | Đo | Đo | Đo |
| CAS conflicts | Đo | Đo | Đo |
| Unexpected errors/timeouts | Đo | Đo | Đo |
| Data service CPU/disk | Đo | Đo | Đo |
| Index maintenance | Đo | Đo | Đo |
| GC/allocations | Đo | Đo | Đo |
| TTL preservation | Assert | Assert | Assert |
| Correct state transition | Assert | Assert | Assert |

Không so A có CAS với C không kiểm tra state rồi gọi đó là cùng công việc. Nếu business transition cần validation, benchmark B với A ở contract tương đương.

### 34.1. Kích thước document quyết định lợi ích

Trường hợp khả dĩ:

- Document 1 KiB, update 500 byte: overhead thêm của subdoc path/options có thể làm lợi ích nhỏ.
- Document 200 KiB, update 20 byte: có cơ hội tiết kiệm băng thông và serialization rõ rệt.
- Document lớn nhưng index và disk bottleneck: bytes client giảm không bảo đảm server p99 giảm tương ứng.

Phải thử nhiều size distribution và hot/cold keys gần production.

## 35. Công thức ước lượng payload thay đổi

Giả sử full replace phải gửi body `S_full` bytes, còn mutateIn gửi các path/value có payload `S_patch` bytes. Mức giảm logical request body ước lượng là:

~~~text
Reduction = 1 - (S_patch / S_full)
~~~

Ví dụ giả định:

~~~text
S_full  = 100 KiB
S_patch =   1 KiB

Reduction ≈ 99% logical request body
~~~

Đây là **ước lượng phần thân**; không bao gồm protocol/TLS headers, retries, request framing, response bytes hoặc server internal I/O. Không lấy 99% để tuyên bố latency cũng giảm 99%.

Nếu đường full update phải GET trước, thêm response full JSON trong phép so và ghi rõ số round trips. Đo cả end-to-end latency, không chỉ bytes.

## 36. Test tích hợp: patch đúng hai field, giữ phần còn lại

Một test phù hợp:

1. Tạo key test duy nhất trong collection test.
2. Lưu document với `shipping.city`, `total`, `items`, `statusHistory` và TTL.
3. Đọc body cùng expiry metadata trước mutation.
4. Gọi `mutateIn` thay `shipping.city` và `updatedAtEpochMs`.
5. Đọc document sau mutation.
6. Assert hai path được sửa.
7. Assert các field khác giữ nguyên.
8. Assert expiry metadata đúng policy.
9. Cleanup đúng key test.

Ví dụ phần assertion:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

var after = orders.get(id).contentAsObject();

assertThat(after.getObject("shipping")
        .getString("city")).isEqualTo("Da Nang");

assertThat(after.getLong("total"))
        .isEqualTo(150000L);

assertThat(after.getArray("items").size())
        .isEqualTo(2);
~~~

Đây là **đoạn kiểm tra** trong fixture có sẵn, không phải class test hoàn chỉnh chạy độc lập. Cần test read-back CAS và expiry bằng API metadata riêng.

## 37. Test nguyên tử nhiều specs khi một path sai

Arrange một document có:

~~~json
{
  "status": "PAID",
  "shipping": {"city": "Ha Noi"},
  "updatedAtEpochMs": 1000
}
~~~

Act:

~~~java
orders.mutateIn(
        id,
        List.of(
                MutateInSpec.replace("status", "PACKED"),
                MutateInSpec.replace(
                        "shipping.nonexistent.deepField",
                        "something")
        ),
        MutateInOptions.mutateInOptions()
                .storeSemantics(StoreSemantics.REPLACE)
);
~~~

Test kỳ vọng mutation thất bại vì path không hợp lệ, sau đó GET và khẳng định `status` vẫn là `PAID` và timestamp không đổi. Không chỉ assert exception rồi bỏ qua câu hỏi liệu có partial write.

### 37.1. Test lỗi phải bắt đúng loại

Nếu test dự kiến path error nhưng cluster bị timeout, không được đánh đồng. Bắt exception cụ thể theo SDK version và để lỗi hạ tầng làm test fail.

## 38. Test CAS conflict có thể tái hiện

Không dùng `Thread.sleep(17)` và hy vọng tạo race:

1. GET/lookupIn document, giữ CAS c1.
2. Writer B mutateIn một field hợp lệ, CAS chuyển thành c2.
3. Writer A cố mutateIn với `cas(c1)`.
4. Assert `CasMismatchException` (hoặc lỗi tương ứng SDK).
5. Đọc lại xác minh thay đổi của B được giữ.
6. Nếu service có retry, thử đọc lại và validate trạng thái.

Ví dụ logic:

~~~java
var first = orders.lookupIn(
        id,
        List.of(LookupInSpec.get("status"))
);

orders.mutateIn(
        id,
        List.of(
                MutateInSpec.upsert("updatedAtEpochMs", 2000L)
        )
);

// Với CAS đã cũ, mutation tiếp theo phải conflict.
orders.mutateIn(
        id,
        List.of(
                MutateInSpec.replace("status", "PACKED")
        ),
        MutateInOptions.mutateInOptions()
                .cas(first.cas())
);
~~~

Đoạn cuối **được kỳ vọng ném lỗi**; trong JUnit bao bằng `assertThrows`. Cần khởi tạo test document, cleanup và schema đúng trước khi chạy.

## 39. Test retry và idempotency

Hai test không nên bỏ qua:

- **Scalar upsert:** retry với cùng value và deadline fixed; kiểm tra không tạo thêm side effects, TTL không drift.
- **Increment/array append:** mô phỏng timeout mơ hồ rồi retry; xác minh service đối soát/idempotency, không tăng hai lần hoặc chèn duplicate nếu business chỉ cho một lần.

Một phương pháp là mock gateway tạo một timeout sau khi state trong test fake đã thay đổi, rồi kiểm tra logic service. Integration fault injection nên chạy riêng để không tạo flaky CI.

## 40. Test performance ở nhiều mức tải

Trước/sau tối ưu nên chạy cùng:

- Document sizes 2 KiB, 50 KiB và 200 KiB, hoặc phân bố size production.
- Key popularity uniform và hot-key mix.
- Update tỷ lệ nhỏ/trung bình/nhiều fields.
- Concurrency 1, 8, 32 và số requests/s thực.
- Read/write mix có chỉ mục trên field đang sửa.
- TLS, consistency/durability, TTL và retry giống nhau.
- Cùng number of clients, JVM heap/GC và cluster topology.

Đo p95/p99, goodput, bytes, CPU/GC, CAS conflicts và error rate. Nếu mutation theo subdocument nhanh hơn ở 1 request nhưng làm tăng index/CPU ở tải lớn, phải điều tra thay vì kết luận chung.

## 41. Những trường hợp không nên chuyển sang sub-document

| Tình huống | Lý do |
| --- | --- |
| Thay gần hết JSON | Full replace đơn giản, có thể không đắt hơn |
| Cần validate toàn bộ aggregate | Đọc + CAS/full entity có thể rõ ràng hơn |
| Có nhiều thay đổi liên quan phức tạp | 16 specs limit, cần business invariants |
| Nhiều documents phải đổi atomically | Cần transaction/saga/outbox |
| Entity dùng converter phức tạp | SDK path dễ phá mapping |
| Lifecycle/auditing bắt buộc | SDK trực tiếp không tự kích hoạt callbacks |
| Payload nhỏ, traffic thấp | Lợi ích có thể không bù độ phức tạp |
| Mutation theo index/position thiếu ổn định | CAS/schema redesign cần thiết |
| Retry không idempotent chưa có giải pháp | Increment/append có thể lặp |
| Schema đang đổi nhiều versions | Path-level code dễ vỡ, cần migration |
| Hot document có conflict lớn | Có thể cần data modeling/sharding |
| Cần update qua SQL++ predicate nhiều documents | `mutateIn` chỉ biết key, không tìm tập |

Không xem sub-document là nguyên tắc thay thế `repository.save` trong mọi trường hợp. Đây là tối ưu cho **access pattern chọn lọc, schema ổn định và contract đã hiểu**.

## 42. Troubleshooting

| Dấu hiệu | Khả năng | Cách khắc phục |
| --- | --- | --- |
| `mutateIn` báo not-found | Key sai, TTL hết hạn, sai collection | Kiểm tra keyspace, không tự UPSERT |
| `replace("x.y")` thất bại | Path chưa có | Kiểm tra schema hoặc `upsert` có chủ đích |
| `upsert("x.y")` lỗi cha thiếu | Parent `x` chưa tồn tại | Khởi tạo path hoặc `createPath` |
| Path mismatch | Cha là scalar/array sai kiểu | Migration/schema validation |
| Trùng field sau SDK patch | Java property khác JSON mapped field | Kiểm tra `@Field` và converter |
| TTL bị reset sau patch | Không preserve expiry | `preserveExpiry(true)` và metadata test |
| Counter tăng hai lần | Retry sau timeout mơ hồ | Idempotency/đối soát |
| Array có duplicate events | Append non-idempotent | Event ID/dedupe, không blind retry |
| Status đổi từ trạng thái cấm | Blind field replace | Read state + CAS |
| CAS conflict tăng cao | Nhiều writers cùng doc | Retry hữu hạn hoặc redesign |
| Repo save sau SDK patch báo conflict | CAS đã thay | Reload entity, validate |
| Query chưa thấy status mới | Index consistency | Kiểm tra SQL++ consistency |
| Index write load không giảm | Indexed field vẫn đổi | Đo index maintenance |
| Client bytes giảm nhưng p99 không giảm | Bottleneck server/network khác | Trace và benchmark |
| Reactive mutation không chạy | Publisher chưa subscribe | Compose/subscribe |
| Batch chỉ update một phần documents | Mỗi key độc lập | Transaction hoặc per-item result |
| Audit timestamp không được ghi | SDK bỏ callback | Thêm spec/logic trong gateway |
| Remove path làm service crash | Path chưa tồn tại | Phân loại missing path |
| 17 specs bị từ chối | Vượt giới hạn subdoc | Gom model hoặc full replace |

## 43. Bài tập tình huống

Một ứng dụng có:

~~~text
commerce.sales.orders
commerce.checkout.carts
commerce.auth.otp_challenges
commerce.inventory.stock
~~~

Các yêu cầu:

1. Chỉ cập nhật `shipping.city` của order 80 KiB.
2. Chỉ tăng `metrics.viewCount`.
3. Ghi `status` và `updatedAt` trong một thao tác.
4. Chuyển order từ PAID sang PACKED, cấm chuyển từ CANCELLED.
5. Thêm event lịch sử vận chuyển vào mảng có thể dài.
6. Giảm `attemptsRemaining` của OTP không được gia hạn deadline.
7. Update item[2] khi nhiều users sửa cart đồng thời.
8. Chuyển order sang SHIPPED và trừ inventory khác document.
9. Reactive batch patch 200 orders theo key.
10. Đổi endpoint repository save sang SDK mutateIn mà không phá converter.
11. Một mutation timeout sau increment: client có nên retry ngay không?
12. Index trên `status` bị update 1000 lần/s: subdoc có chắc giảm Index CPU không?
13. Một document mất `shipping`: nên createPath hay fail?
14. Collection có maxTTL 10 phút, order cần thời hạn 1 giờ: patch phải chú ý gì?
15. Dataset JSON nhỏ 512 bytes: có nên mặc định chuyển toàn bộ saves sang mutateIn?

**Định hướng:**

- Bài 1: `mutateIn(replace path)` với schema/permission checks.
- Bài 2: `increment`, phân biệt retry và idempotency.
- Bài 3: nhiều specs trong một `mutateIn`.
- Bài 4: `lookupIn + CAS + mutateIn`, kiểm tra lại sau conflict.
- Bài 5: `arrayAppend` có quản lý kích thước/dedupe hoặc event documents riêng.
- Bài 6: cố định deadline, `preserveExpiry(true)`, CAS nếu counter/state cần ràng buộc.
- Bài 7: vị trí mảng có race, cân nhắc ID bền vững và CAS.
- Bài 8: transaction/saga/outbox, không chỉ subdoc.
- Bài 9: bounded `flatMap` và kết quả từng key.
- Bài 10: kiểm tra `@Field`, `@Version`, lifecycle, TTL và serialization.
- Bài 11: không blind retry non-idempotent mutation.
- Bài 12: có thể vẫn phải duy trì index.
- Bài 13: phụ thuộc contract schema; không luôn tự tạo.
- Bài 14: effective server maxTTL và expiry metadata.
- Bài 15: benchmark cùng correctness, tránh over-engineering.

## 44. Checklist production

- [ ] Đã xác định phần JSON thật sự cần cập nhật.
- [ ] Document ID và bucket/scope/collection đúng.
- [ ] Đã benchmark full replace vs mutateIn trên kích thước dữ liệu thật.
- [ ] Đường nghiệp vụ có yêu cầu state transition được kiểm tra.
- [ ] Nhiều paths liên quan đã được gom trong một lệnh khi phù hợp.
- [ ] Không vượt giới hạn số specs/lệnh được SDK/server hỗ trợ.
- [ ] Phân biệt path `upsert/replace/insert` với document `StoreSemantics`.
- [ ] Không dùng document upsert cho update của document đã expired.
- [ ] Tên JSON path khớp `@Field`/converter và schema persisted.
- [ ] `createPath()` chỉ bật khi nghiệp vụ cho phép.
- [ ] Path/array type/parent missing có error handling rõ.
- [ ] Counter uses correct integer range/semantics.
- [ ] Array append không vô hạn; event duplicate/ordering được xử lý.
- [ ] One-time/status transition có CAS hoặc phương án phù hợp.
- [ ] CAS conflict retry có giới hạn và kiểm tra lại business conditions.
- [ ] Retry timeout phân biệt mutation idempotent và non-idempotent.
- [ ] SDK direct không bỏ auditing/callback/validation của Spring Data.
- [ ] Entity `@Version` và raw SDK CAS phối hợp rõ ràng.
- [ ] TTL được preserve hoặc đặt lại theo policy, không reset âm thầm.
- [ ] `maxTTL` server được đối chiếu trong đúng collection.
- [ ] Có integration test đọc expiry metadata trước/sau patch.
- [ ] Có test atomicity một spec fail thì các specs khác không ghi.
- [ ] Có test CAS mismatch và concurrent independent paths.
- [ ] Có test cross-path invariant, đặc biệt status và timestamps.
- [ ] Subdocument mutation không được hiểu là transaction nhiều keys.
- [ ] Authorization và tenant validation được giữ nguyên.
- [ ] Durability/consistency giữ nguyên khi so performance.
- [ ] SQL++/index visibility được kiểm tra theo yêu cầu.
- [ ] Reactive publisher được subscribe, không block event loop.
- [ ] Batch mutations giới hạn concurrency và xử lý partial outcomes.
- [ ] Metrics có KV latency p50/p95/p99, throughput và error rate.
- [ ] Đã đo logical payload/wire bytes và Data/Index service load.
- [ ] Không kết luận server disk writes tỷ lệ thuận với patch bytes.
- [ ] Có rollback/migration nếu đổi đường repository save sang SDK.

## 45. Tổng kết

**Sub-document `mutateIn`** là công cụ tối ưu tốt khi ứng dụng **đã biết document key** và chỉ cần thay một vài path của JSON. Nó giảm nhu cầu GET/serialize/REPLACE toàn document, có thể gom nhiều path edits **nguyên tử trong một document**, hỗ trợ increment/array operations và giảm băng thông trên hot path.

Tuy nhiên, **atomicity không thay CAS**, và CAS không thay transaction nhiều document. `StoreSemantics` của document gốc khác `upsert` ở JSON path; TTL có thể đổi nếu không dùng `preserveExpiry` đúng cách; SDK trực tiếp không tự chạy converter, `@Version` và lifecycle callbacks của Spring Data.

Khi quyết định thay toàn bộ `repository.save` hoặc `Collection.replace` bằng `mutateIn`, hãy bắt đầu từ **contract nghiệp vụ**, kiểm tra schema/CAS/TTL, đánh giá idempotency và đo thật trên workload về **latency, bytes, throughput, index/write cost và errors**. Tối ưu chỉ đáng dùng nếu lợi ích đo được lớn hơn độ phức tạp và vẫn bảo vệ tính đúng đắn của dữ liệu.

