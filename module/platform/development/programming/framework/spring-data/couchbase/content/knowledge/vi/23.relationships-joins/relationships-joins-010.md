# Ranh giới toàn vẹn tham chiếu do ứng dụng chịu trách nhiệm trong Spring Data Couchbase

Một document `Shipment` có field `orderId` không có nghĩa Couchbase tự kiểm tra rằng Order đó tồn tại. Một document `Order` giữ `customerId` cũng không làm Couchbase tự cấm xóa Customer, đổi Customer ID, xóa Order theo chuỗi hay buộc mọi document tham chiếu cập nhật cùng lúc. Khác với một schema quan hệ có khai báo foreign key và quy tắc `ON DELETE`, các liên kết trong mô hình document của Couchbase phần lớn là **quy ước dữ liệu và bất biến nghiệp vụ mà ứng dụng phải thực thi**.

Điều đó không có nghĩa Couchbase thiếu cơ chế hỗ trợ tính đúng: KV insert theo document ID, CAS, optimistic locking, SDK transactions, SQL++ và các chỉ mục đều có vai trò quan trọng. Nhưng **mỗi cơ chế bảo vệ một phạm vi cụ thể**. Một transaction thành công không tự tạo foreign key cho mọi writer trong hệ thống; một index nhanh không bảo đảm unique business key; một `@N1qlJoin` không kiểm soát thao tác `save` hoặc `delete`; và một lần kiểm tra parent còn tồn tại trước khi tạo child vẫn có thể gặp race.

Bài thuộc chương **Quan hệ và JOIN** của module **SPRING_DATA_COUCHBASE**. Trong phạm vi xây dựng tầng truy cập Couchbase bằng Spring Data, document mapping, repository, `CouchbaseTemplate` và SQL++, người học sẽ thiết kế những bất biến rõ ràng cho bucket/scope/collection, lựa chọn KV/Query/reactive, xử lý TTL, CAS, giao dịch và xây dựng khả năng đối soát — để dữ liệu liên kết **đúng khi ghi, dễ hiểu khi đọc và có thể phục hồi khi một bước thất bại**.

Các ví dụ mô tả mô hình và khả năng thường gặp của Couchbase Server/Java SDK/Spring Data Couchbase. Tên class, Transaction API, index/consistency options và hành vi association thay đổi theo phiên bản; hãy xác nhận với dependency/Server thực tế. Bài không giả định đã chạy cluster production hoặc có một bộ bảo đảm referential integrity tự động.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **ràng buộc giá trị document**, **duy nhất document ID**, **điều kiện truy vấn**, **optimistic concurrency**, **transaction** và **toàn vẹn tham chiếu nghiệp vụ**.
2. Định nghĩa các invariant cho quan hệ 1:1, 1:N, N:M: tồn tại, đúng tenant, đúng trạng thái, duy nhất, quyền cập nhật và chính sách khi xóa.
3. Chọn embedding, ID reference, business-key reference hoặc edge document theo aggregate boundary và vòng đời dữ liệu.
4. Hiểu vì sao **check-then-write**, **check-then-delete** và nhiều mutation rời rạc có race; biết thiết kế guard/state transition, CAS, transaction hoặc workflow bù trừ phù hợp.
5. Xây dựng uniqueness theo document ID xác định và `insert-if-absent`; nhận biết giới hạn khi một khóa nghiệp vụ cần nhiều document hoặc nhiều keyspace cùng được cập nhật.
6. Thiết kế read path khi reference thiếu, soft-deleted, expired hoặc sai tenant; biết lúc nào nên dùng `LEFT JOIN` thay vì `INNER JOIN`.
7. Hiểu rằng TTL, `@N1qlJoin`, GSI, `REQUEST_PLUS` và reactive API **không tự tạo foreign key/cascade/snapshot giao dịch**.
8. Tạo quy trình migration, reconciliation, metrics và integration test để phát hiện và khắc phục mối quan hệ hỏng có kiểm soát.

## 2. Phạm vi dữ liệu: các collection độc lập

Giả sử bucket `commerce` và các scope:

```text
commerce
├── crm
│   └── customers
└── sales
    ├── orders
    ├── shipments
    ├── memberships
    └── relationship_events
```

Document Customer (ID `customer::TENANT-A::42`) trong `commerce.crm.customers`:

```json
{
  "_class": "customer",
  "tenantId": "TENANT-A",
  "customerCode": "C-42",
  "displayName": "Nguyen An",
  "state": "ACTIVE",
  "deleted": false
}
```

Document Order (ID `order::TENANT-A::1001`) trong `commerce.sales.orders`:

```json
{
  "_class": "salesOrder",
  "tenantId": "TENANT-A",
  "orderNumber": "ORD-1001",
  "customerId": "customer::TENANT-A::42",
  "customerCode": "C-42",
  "customerNameAtPurchase": "Nguyen An",
  "state": "PAID",
  "createdAt": "2026-11-20T08:15:00Z",
  "items": [
    { "sku": "SKU-42", "quantity": 2, "priceAtPurchase": 350000 }
  ]
}
```

Document Shipment (ID `shipment::TENANT-A::S-7`) trong `commerce.sales.shipments`:

```json
{
  "_class": "shipment",
  "tenantId": "TENANT-A",
  "orderId": "order::TENANT-A::1001",
  "trackingNumber": "TRACK-7001",
  "state": "IN_TRANSIT",
  "createdAt": "2026-11-21T08:00:00Z"
}
```

Trong một hệ thống nhiều tenant, cùng mã `ORD-1001` hoặc `C-42` có thể hợp lệ ở nhiều tenant khác nhau. Vì vậy `customerCode` và `orderNumber` không mặc nhiên là khóa duy nhất toàn hệ thống. **Document ID** chỉ nhận diện một document trong **keyspace cụ thể**; scope/collection không thể được bỏ qua khi thiết kế lookup.

Các document `Customer`, `Order` và `Shipment` tồn tại độc lập. Ngay cả khi field `customerId` có chuỗi trông giống ID thật, việc write Order **không tự gọi** KV GET, không tự insert Customer và không tự khóa Customer khỏi bị xóa.

## 3. Toàn vẹn tham chiếu là tập những bất biến phải nói rõ

### 3.1. “Có reference” và “reference hợp lệ” khác nhau

Một field:

```json
{
  "orderId": "order::TENANT-A::1001"
}
```

có thể thỏa kiểm tra Java như `@NotBlank` nhưng vẫn không bảo đảm:

- Order thực sự tồn tại ở `commerce.sales.orders`.
- Order thuộc cùng tenant với Shipment.
- Order đang ở trạng thái cho phép tạo Shipment.
- Order chưa bắt đầu quy trình xóa.
- User đang thao tác có quyền tạo Shipment cho Order đó.
- Order sẽ còn tồn tại sau thao tác ghi Shipment.

Một invariant đầy đủ phải diễn đạt **tài nguyên đích, phạm vi tenant, trạng thái hợp lệ, thời điểm kiểm tra và cách ứng phó với cạnh tranh**.

### 3.2. Ma trận invariant mẫu

| Quan hệ | Bất biến cần bảo vệ | Chính sách khi vi phạm |
| --- | --- | --- |
| Order → Customer | Customer cùng tenant; Customer được phép dùng khi tạo Order | Từ chối hoặc chọn guest/snapshot theo nghiệp vụ |
| Shipment → Order | Order tồn tại và chưa `DELETING`; Shipment cùng tenant | Không tạo Shipment; xử lý lỗi hoặc retry có điều kiện |
| Customer 1:1 Preferences | Tối đa một preferences document cho mỗi Customer | ID xác định + KV insert-if-absent |
| User–Team membership | Không có hai membership active cùng user/team/tenant | Edge ID xác định hoặc guard; policy cho rejoin |
| Order → Items nhúng | `quantity > 0`, giá snapshot hợp lệ | Validate và cập nhật cùng một document Order |
| Payment → Order | Không ghi nhận thanh toán hai lần cho cùng idempotency key | Khóa idempotency + transaction/workflow ghi |
| Order deletion | Không làm mất dữ liệu lịch sử bắt buộc; child lifecycle rõ | RESTRICT/DETACH/CASCADE/ARCHIVE có kiểm soát |

Không dùng một chính sách “mọi reference luôn tồn tại mãi” cho tất cả quan hệ. Quan hệ lịch sử có thể cố ý giữ ID sau khi hồ sơ cá nhân bị xóa; một Shipment đang vận chuyển thường không được có Order bất hợp lệ.

### 3.3. Phân biệt bất biến mạnh và bất biến kiểm tra định kỳ

**Bất biến mạnh**: phải đúng ngay khi thao tác được công nhận thành công, ví dụ không được chấp nhận tạo Shipment cho Order đang `DELETING`.

**Bất biến cuối cùng (eventual)**: cho phép trạng thái chuyển tiếp có thể đo và sửa, ví dụ một read model `shipmentCount` cập nhật chậm sau sự kiện tạo Shipment.

Không gọi cả hai là “toàn vẹn” mà không ghi SLA. Nếu một giao dịch tài chính đòi atomicity, không thể chỉ trả lời “sẽ có job sửa sau”; nếu một danh sách gợi ý chỉ cần dữ liệu cuối cùng, transaction nhiều document có thể là chi phí không cần thiết.

## 4. Bảng trách nhiệm: Couchbase bảo đảm gì, ứng dụng phải làm gì?

| Cơ chế | Có thể hỗ trợ | **Không tự bảo đảm** |
| --- | --- | --- |
| KV document ID | Tra/ghi document theo khóa cụ thể; `insert` phát hiện ID đã tồn tại | Unique theo business key khác ID; foreign key giữa collection |
| Schema validation trong Java | Kiểu dữ liệu và quy tắc field ở những writer dùng validator | Mọi writer/CLI/import đều tuân thủ; document đích tồn tại |
| Secondary/Global Secondary Index | Tìm nhanh theo field, lọc, sort/join theo query | Unique constraint thường dùng như hệ quan hệ; ngăn xóa parent |
| SQL++ `JOIN`/`NEST` | Kết hợp document theo ID hoặc điều kiện JSON | Tạo, sửa, xóa hay kiểm chứng reference khi ghi |
| `@N1qlJoin` | Khai báo quy tắc tải associated entities trong Spring Data | JPA-style cascade, foreign key, transaction mặc định |
| CAS/`@Version` | Phát hiện ghi cạnh tranh trên document đang sửa | Atomic invariant xuyên nhiều document |
| Couchbase transactions | Atomic commit/rollback cho các thao tác tham gia transaction trong phạm vi hỗ trợ | Mọi writer bên ngoài transaction tự tuân thủ business invariant |
| TTL | Làm document hết hạn theo chính sách | Xóa các reference trỏ tới document, giữ lịch sử chính xác |
| GSI scan consistency | Kiểm soát yêu cầu độ mới của index đối với một query | Snapshot transaction cho nhiều request, FK/uniqueness |
| Reconciliation job | Phát hiện/sửa trường hợp lệch theo policy | Đảm bảo không có trạng thái lệch trước khi job chạy |

**Giới hạn quan trọng:** Một document ID duy nhất trong một collection là thuộc tính lưu trữ hữu ích, nhưng không đại diện cho “unique business key” nếu ứng dụng cho phép nhiều ID khác nhau chứa cùng `customerCode`.

## 5. Đặt ranh giới aggregate trước khi chọn phương thức JOIN

### 5.1. Khi quan hệ có vòng đời chung: ưu tiên xem xét embedding

Nếu Order có vài `items` gắn với đúng một hóa đơn, snapshot giá/số lượng cần được lưu và thay đổi cùng Order, mô hình nhúng thường đơn giản:

```json
{
  "orderNumber": "ORD-1001",
  "items": [
    { "lineId": "L1", "sku": "SKU-42", "quantity": 2 }
  ]
}
```

Khi cập nhật Order bằng một mutation có CAS, các item nhúng nằm **trong cùng một document**. Không cần JOIN để đọc; một bất biến như “số lượng từng item phải dương” có thể được kiểm tra trước khi replace document.

**Nhưng embedding không phù hợp với mọi quan hệ:**

- Mảng tăng không giới hạn khiến document lớn, contention hoặc nhiều lần ghi lại.
- Child có vòng đời/TTL khác hẳn parent.
- Child được truy cập độc lập, cần phân trang hoặc thay đổi thường xuyên.
- Nhiều parent cùng tham chiếu một entity dùng chung.

### 5.2. Khi vòng đời độc lập: dùng ID reference

Shipment thường có ID, trạng thái giao hàng, sự kiện và retention riêng. `Shipment.orderId` là một liên kết giữa document độc lập, thuận tiện truy vấn child nhưng **đưa trách nhiệm kiểm tra Order tồn tại sang tầng ứng dụng**.

Một đường đọc:

```text
Order (ID o1)
    |
    | Shipment.orderId == o1
    v
Shipments (s1, s2, ...)
```

và một đường ghi có thể khác. API đọc danh sách Shipment dùng index theo `tenantId/orderId`; API tạo Shipment cần xác định parent có hợp lệ **tại thời điểm ghi**.

### 5.3. Business key khác document ID

Truy vấn:

```sql
SELECT META(o).id AS orderId, c.displayName
FROM `commerce`.`sales`.`orders` AS o
JOIN `commerce`.`crm`.`customers` AS c
  ON o.tenantId = c.tenantId
 AND o.customerCode = c.customerCode
WHERE o.tenantId = "TENANT-A";
```

dùng **business key**. Nếu Customer bị trùng cặp `(tenantId, customerCode)`, một Order có thể match nhiều Customer. Nếu Customer đổi mã, Order cũ có thể không match.

Nếu Order lưu `customerId`:

```sql
SELECT META(o).id AS orderId, c.displayName
FROM `commerce`.`sales`.`orders` AS o
JOIN `commerce`.`crm`.`customers` AS c
  ON KEYS o.customerId
WHERE o.tenantId = "TENANT-A";
```

thì lookup theo ID cụ thể có thể rõ hơn; nhưng ID vẫn có thể sai tenant, đã xóa hoặc thuộc một collection khác. Chọn ID reference thường giúp quản lý danh tính ổn định hơn, **không tự tạo toàn vẹn tham chiếu**.

## 6. Tạo ID xác định để bảo vệ uniqueness một quan hệ

### 6.1. Một Customer Preferences cho mỗi Customer

Giả sử mỗi Customer có tối đa một Preferences document trong `crm.customer_preferences`. Một thiết kế ID:

```text
customer-preferences::<tenantId>::<customerId-encoded>
```

Mọi writer phải tạo cùng ID khi cùng một Customer. Khi tạo mới, dùng **KV insert-if-absent**, không dùng `upsert` để “thử tạo nếu chưa có”:

```java
import com.couchbase.client.core.error.DocumentExistsException;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;

public boolean createPreferencesOnce(
        Collection preferences,
        String preferencesId,
        JsonObject data) {
    try {
        preferences.insert(preferencesId, data);
        return true; // Trước đó chưa có document với ID này.
    } catch (DocumentExistsException alreadyExists) {
        return false;
    }
}
```

Mẫu này bảo vệ tính duy nhất **của document ID trong đúng collection** khi mọi writer dùng chung quy tắc ID. Nó không kiểm tra Customer còn tồn tại hoặc cùng tenant; phần đó cần thêm bất biến/validation và ranh giới thao tác phù hợp.

### 6.2. Canonicalization là một phần của ràng buộc

Nếu ID được tạo từ `customerCode` hoặc email, hãy quy định:

- Kiểu dữ liệu: `"042"` có khác `42` hoặc `"42"` không?
- Cách xử lý chữ hoa/thường, khoảng trắng và Unicode.
- Tenant là thành phần bắt buộc của phạm vi duy nhất hay không.
- Chuỗi phân cách có thể xuất hiện trong dữ liệu gốc không?
- Có cần hash một business key nhạy cảm để tránh lộ PII qua document ID/log không?
- Khi business key đổi, ID có thay theo hay nên dùng surrogate ID ổn định?

Không ghép chuỗi `tenant + ":" + code` tùy tiện nếu có nguy cơ hai cặp khác nhau tạo cùng ID. Cần encoding chuẩn hoặc schema ID rõ ràng, kiểm thử collision và chính sách đổi phiên bản.

### 6.3. Guard/claim document cho uniqueness theo business key

Nếu Customer có ID ngẫu nhiên nhưng vẫn phải unique theo `(tenantId, customerCode)`, có thể thiết kế **claim** ở một keyspace:

```text
customer-code::<tenantId>::<normalizedCustomerCode>
    -> customerId
```

Một writer phải chiếm quyền sử dụng claim bằng `insert-if-absent`. Nhưng **chỉ insert claim rồi insert Customer ở hai lệnh rời rạc** sẽ có failure window: claim tồn tại mà Customer chưa được tạo, hoặc Customer được tạo nhưng claim chưa cập nhật. Cần transaction được hỗ trợ hoặc workflow có trạng thái, idempotency và reconciliation.

Nếu dùng claim, mọi writer (API, import, event consumer, migration) phải tuân thủ cùng giao thức. Một writer bỏ qua claim vẫn có thể tạo Customer duplicate.

## 7. Ranh giới check-then-write: TOCTOU không biến mất vì có `findById`

Đây là lỗi thường gặp:

```java
SalesOrder parent = orderRepository.findById(orderId)
    .orElseThrow(() -> new IllegalArgumentException("Order not found"));

if (!"PAID".equals(parent.getState())) {
    throw new IllegalStateException("Order not ready");
}

shipmentRepository.save(new Shipment(orderId, trackingNumber));
```

Đoạn trên là **giả mã service rút gọn**, không phải một phương thức đang có sẵn để sao chép nguyên vào production. Nó cho thấy hai thao tác độc lập:

1. Đọc Order, kiểm tra trạng thái.
2. Ghi Shipment.

Giữa hai bước, luồng khác có thể bắt đầu xóa Order hoặc chuyển trạng thái Order sang `CANCELLED`.

### 7.1. Dòng thời gian race

```text
T1  Service A: GET Order -> PAID
T2  Service B: Order PAID -> DELETING
T3  Service A: INSERT Shipment
T4  Service B: DELETE Order
---------------------------------
Kết quả: Shipment trỏ Order không còn hợp lệ
```

Check trước khi write là một biện pháp cần thiết nhưng **không đủ nếu writer/delete cạnh tranh không có giao thức chung**.

### 7.2. Hai lựa chọn hợp lệ

**A. Bất biến mạnh:** thiết kế một guard/state transition chung và đảm bảo cả creator lẫn deleter tham gia cùng cơ chế đồng bộ, có thể sử dụng transaction hoặc optimistic conflict theo phạm vi hỗ trợ.

**B. Eventual invariant:** chấp nhận trạng thái Shipment `PENDING`, không công bố là hợp lệ cho tới khi xác nhận parent; nếu parent bị xóa, workflow bù trừ/đối soát phải hủy hoặc xử lý Shipment.

Không gắn nhãn “atomic” cho lựa chọn B. Cũng không gọi A là an toàn chỉ vì viết một lần `@Transactional` nếu transaction manager/runtime không được cấu hình đúng hoặc một bên vẫn ghi trực tiếp ngoài giao thức.

## 8. Giao thức tạo child có parent guard

### 8.1. Trạng thái parent là tín hiệu của vòng đời

Một Order có thể có:

```json
{
  "state": "PAID",
  "relationState": "OPEN",
  "childGeneration": 7
}
```

Trong quy tắc nghiệp vụ:

- Chỉ tạo Shipment khi `relationState = "OPEN"`.
- Quá trình xóa/đóng Order trước tiên chuyển `relationState` thành `CLOSING`.
- Sau khi đã chặn tạo Shipment mới theo **giao thức chung**, hệ thống mới xử lý các Shipment còn lại và hoàn tất trạng thái `CLOSED`/xóa.

Trường `childGeneration` là một cách mô hình hóa phiên bản giai đoạn quan hệ; không phải chức năng Couchbase cung cấp tự động. Nếu người viết child chỉ **đọc** `relationState` rồi ghi độc lập, race vẫn còn.

### 8.2. Bắt buộc có điểm xung đột chung khi cần bất biến mạnh

Một giao thức mạnh hơn có thể dùng transaction:

```text
CREATE SHIPMENT TRANSACTION
  - Đọc Order
  - Xác minh tenant + relationState == OPEN
  - Cập nhật guard/version trên Order
  - Insert Shipment với ID xác định

CLOSE ORDER TRANSACTION
  - Đọc Order
  - Cập nhật guard/version từ OPEN -> CLOSING
  - Commit
```

Khi hai thao tác cạnh tranh thực sự cùng cập nhật một guard document trong transaction, cơ chế kiểm soát xung đột có thể phát hiện/đẩy một thao tác phải retry, thay vì hai bên chỉ đọc trạng thái rồi ghi ở hai document độc lập. Cần xem khả năng transaction và exception/retry thực tế của Couchbase version.

**Lưu ý cốt lõi:** Một transaction chỉ **đọc** Order rồi **ghi** Shipment chưa chắc đã ngăn toàn bộ race phantom nếu luồng delete/child insert không tạo xung đột hoặc không cùng tuân thủ giao thức. Phải thiết kế protocol và kiểm thử concurrency, không chỉ dựa vào tên API.

### 8.3. Idempotency khi retry

Insert Shipment nên gắn một ID/idempotency key ổn định từ yêu cầu nghiệp vụ:

```text
shipment::<tenantId>::<shipmentRequestId>
```

Nếu transaction hoặc network timeout khiến client không chắc commit đã xảy ra, retry cùng ID có thể giúp không sinh hai Shipment mới. Nhưng hãy phân biệt:

- Retry **cùng lệnh nghiệp vụ**: nhận diện duplicate đã xử lý, trả kết quả tương ứng.
- Hai yêu cầu nghiệp vụ **khác nhau**: có thể tạo hai Shipment hợp lệ.
- Trùng ID nhưng payload khác: phải báo conflict, không âm thầm ghi đè.

`insert-if-absent` có thể bảo vệ duplicate ID, còn logic kết quả idempotent phải kiểm chứng payload và trạng thái do ứng dụng định nghĩa.

## 9. Tạo quan hệ 1:N và xóa Order: RESTRICT không thể chỉ là một SELECT COUNT

Một đề xuất đơn giản:

```sql
SELECT COUNT(1) AS shipmentCount
FROM `commerce`.`sales`.`shipments` AS s
WHERE s.tenantId = "TENANT-A"
  AND s.orderId = "order::TENANT-A::1001";
```

Rồi:

```text
if shipmentCount == 0:
    delete Order
```

Sai lầm nằm ở **khoảng giữa**: một Shipment có thể được insert ngay sau khi query đếm trả 0. GSI lag còn có thể làm query theo field chưa thấy Shipment vừa được ghi.

### 9.1. RESTRICT theo giao thức nhiều bước

Một quy trình có thể là:

1. Đặt Order từ `OPEN` sang `CLOSING` bằng CAS/transaction với guard mà mọi writer child dùng.
2. Khi một writer Shipment thấy `CLOSING`, nó không được insert; nếu đang có race, giao thức phải phát hiện conflict.
3. Rà những Shipment hiện có qua đường đọc phù hợp với yêu cầu độ mới; thực hiện xử lý hoặc từ chối xóa.
4. Chỉ sau khi xác minh không còn child bắt buộc và không có writer mới được phép, chuyển sang `CLOSED` hoặc hard delete.
5. Nếu không xóa được, giữ trạng thái có thể phục hồi hoặc chuyển về `OPEN` theo policy đã xác định.

Trạng thái `CLOSING` là **business workflow**. Couchbase không tự ngăn một writer bỏ qua trạng thái; mọi đường ghi phải dùng service/protocol chung và được kiểm thử.

### 9.2. Đừng đọc GSI không chờ rồi khẳng định không còn child

Chỉ số GSI cập nhật bất đồng bộ. Đối với quyết định xóa không thể đảo ngược, một query `NOT_BOUNDED` trả 0 chưa chắc chứng minh không có Shipment vừa tạo.

Khi cần bảo đảm mạnh, hãy dùng thiết kế giao thức guard/transaction, lựa chọn consistency thích hợp, và đối soát. `REQUEST_PLUS` có thể hỗ trợ độ mới của query index, **không tự khóa không gian predicate** để ngăn insertion mới sau khi COUNT xong.

## 10. DETACH, CASCADE, ARCHIVE: sự lựa chọn của nghiệp vụ

| Chính sách | Ý nghĩa | Khi dùng | Rủi ro |
| --- | --- | --- | --- |
| `RESTRICT` | Chặn xóa khi còn quan hệ bắt buộc | Order đang vận chuyển, resource đang dùng | Race nếu chỉ kiểm tra rồi xóa |
| `DETACH` | Giữ child nhưng gỡ/mất reference theo quy tắc | Quan hệ tùy chọn, wishlist, saved search | Có thể làm mất khả năng truy vết |
| `CASCADE` | Xóa hoặc đánh dấu child liên quan theo workflow | Dữ liệu phụ thuộc cùng vòng đời | Xóa nhầm dữ liệu có retention riêng; ghi dở |
| `ARCHIVE` | Giữ snapshot/audit, hạn chế truy cập nguồn hiện hành | Hóa đơn, dữ liệu lịch sử | Chính sách PII/TTL/retention |

### 10.1. CASCADE nhiều document không phải một thao tác `delete(orderId)`

Nếu Order có 20.000 Event, việc “xóa theo chuỗi” có thể cần nhiều đợt thao tác. Một transaction quá lớn có thể gặp giới hạn tài nguyên và thời gian; thay vì một giao dịch khổng lồ, thiết kế:

```text
Order OPEN -> DELETING
    |
    +--> ngừng tạo child mới theo guard
    |
    +--> xử lý từng batch Shipments
    |       +--> xử lý Event liên quan
    |
    +--> ghi progress/checkpoint
    |
    +--> xác minh hoàn thành
    |
    +--> Order DELETED / archive
```

Mỗi batch phải **idempotent**, có retry và kiểm tra quyền; không hard delete parent trước rồi hy vọng child sẽ tự biến mất.

### 10.2. Một workflow xóa không được làm lộ dữ liệu

Nếu Customer yêu cầu xóa dữ liệu cá nhân, hệ thống phải tính tới bản sao trong Order, read model, cache, event payload, logs và hệ thống khác theo chính sách áp dụng. Cơ chế “giữ snapshot lịch sử” chỉ hợp lệ nếu chính sách retention cho phép.

Không dùng `ON DELETE CASCADE` như tên gọi ngầm trong code khiến người bảo trì tưởng Couchbase tự làm thay.

## 11. Khi đổi reference: update một field có thể ảnh hưởng nhiều invariant

Giả sử Order được chuyển từ Customer C-42 sang C-99 vì hợp nhất tài khoản.

**Đường update không đủ an toàn:**

```java
order.setCustomerId(newCustomerId);
orderRepository.save(order);
```

Nếu không kiểm chứng:

- `newCustomerId` có thuộc cùng tenant không?
- Customer mới đang ACTIVE hay bị xóa mềm?
- User có quyền thay Customer của Order đã thanh toán không?
- Các snapshot trong Order có được đổi hay phải giữ giá trị tại thời điểm mua?
- Một job đồng bộ đang sửa Order cùng lúc không?
- Những read model/query theo `customerCode` có cần update không?

### 11.1. CAS bảo vệ chống ghi đè cùng Order

Spring Data Couchbase có thể dùng `@Version` cho optimistic locking:

```java
import org.springframework.data.annotation.Version;

@Version
private Long version;
```

Khi hai luồng cùng lưu một Order phiên bản cũ, optimistic locking có thể phát hiện conflict theo khả năng mapping đang dùng. Nhưng CAS/`@Version` **không tự xác nhận Customer mới hợp lệ**, cũng không sửa Preferences hoặc read model liên quan.

Với conflict, đọc lại Order, kiểm tra quyền và quy tắc chuyển reference từ trạng thái mới, rồi retry có giới hạn hoặc trả conflict. Không chạy vòng retry mù để ép update vượt qua thay đổi nghiệp vụ của người khác.

### 11.2. Cập nhật nhiều nguồn chân lý

Nếu Order lưu cả `customerId` và `customerCode`, hãy chỉ rõ:

- ID nào là **nguồn chân lý của quan hệ**.
- `customerCode` là snapshot, alias hay field tìm kiếm hiện tại.
- Ai/cách nào cập nhật field còn lại khi ID đổi.
- Đọc bằng `ON KEYS` và ANSI JOIN theo `customerCode` có bắt buộc cùng kết quả không.

Hai reference đồng thời làm tăng rủi ro lệch dữ liệu. Nếu không có nhu cầu rõ, đừng lưu “hai nguồn sự thật” không được quản trị.

## 12. SDK transactions: hỗ trợ tính nguyên tử, không sinh bất biến tự động

Trong phiên bản Couchbase Java SDK có Transactions API, một khối transaction có thể nhóm những operation được hỗ trợ để commit/rollback cùng nhau. Dùng nó khi cần **trạng thái nhiều document thay đổi như một đơn vị**.

### 12.1. Ví dụ luồng tạo Shipment có guard

Giả mã để làm rõ các **bước nghiệp vụ bên trong transaction**:

```text
transactions.run(context -> {
    order = context.get(orders, orderId)
    assert order.tenantId == authenticatedTenant
    assert order.relationState == OPEN

    context.replace(order, order.withGuardRevisionIncremented())
    context.insert(shipments, stableShipmentId, shipmentBody)
})
```

Đây là **pseudocode**, không phải snippet Java SDK có thể compile nguyên văn. API thật yêu cầu `TransactionGetResult`, serialization, exception semantics và thao tác `context` phù hợp version.

Vì creator và deleter cùng sửa guard Order, transaction có thể bảo vệ conflict; nhưng điều kiện bắt buộc là **cả hai đường ghi đều tuân thủ** protocol. Nếu một job khác xóa Order bằng KV trực tiếp ngoài quy trình, bất biến có thể lại bị phá.

### 12.2. Quy tắc quan trọng khi thiết kế transaction

- Chỉ đưa các thao tác thật sự cần atomicity vào transaction.
- Không thực hiện lời gọi HTTP/queue với side effect không đảo ngược rồi kỳ vọng transaction rollback được tác dụng ấy.
- Mọi retry của transaction phải xử lý idempotency; callback có thể được thực thi lại theo chính sách SDK.
- Không phụ thuộc side effect trong lambda transaction được chạy đúng một lần.
- Kiểm tra các giới hạn transaction, độ bền, timeout, consistency và hành vi query trong phiên bản đang dùng.
- Nếu có writer không tham gia transaction, cần policy/gate riêng để giữ invariant.

### 12.3. Có transaction chưa chắc có unique query predicate

Giả sử hai transaction cùng chạy query:

```sql
SELECT META(c).id
FROM `commerce`.`crm`.`customers` AS c
WHERE c.tenantId = "TENANT-A"
  AND c.customerCode = "C-42";
```

cả hai đều có thể thấy “chưa có record” tại thời điểm riêng, rồi insert Customer bằng **hai ID khác nhau** nếu không có điểm xung đột/quy tắc khóa chung. Không mặc định query kiểm tra vắng trong transaction là **unique constraint** cho một phạm vi predicate.

Để uniqueness chắc hơn, tạo **một ID xác định hoặc claim/guard key duy nhất mà tất cả writer cùng tranh chấp**, và xử lý phần ghi nhiều document qua transaction/protocol phù hợp.

## 13. Khi không thể transaction toàn quy trình: saga và outbox

Trong hệ thống nhiều dịch vụ, một nghiệp vụ có thể tạo Order trong Couchbase, gọi cổng vận chuyển và phát sự kiện sang hệ thống khác. Transaction Couchbase không thể tự rollback một hành động bên ngoài như đã đặt lệnh giao hàng với đối tác.

### 13.1. Chọn state machine và compensation

Ví dụ:

```text
Order PAID
   |
   v
Shipment PENDING
   |
   +--> Partner API accepted --> Shipment ACTIVE
   |
   +--> Partner timeout -----> retry/idempotency check
   |
   +--> Partner rejected ----> Shipment FAILED / compensate
```

Các trạng thái phải rõ nghĩa. `PENDING` không được hiển thị thành `ACTIVE` chỉ vì document đã tồn tại. Nếu mất Order giữa quá trình, cần guard/policy đã thống nhất với writer.

### 13.2. Outbox để không “ghi DB thành công, quên phát event”

Một thiết kế outbox có thể ghi trạng thái nghiệp vụ và event cần phát trong cùng ranh giới transaction có hỗ trợ. Worker phát event **sau commit**, theo dõi trạng thái gửi và retry.

```json
{
  "_class": "relationshipEvent",
  "eventId": "evt::TENANT-A::shipment-request-723",
  "tenantId": "TENANT-A",
  "type": "SHIPMENT_CREATED",
  "aggregateId": "order::TENANT-A::1001",
  "shipmentId": "shipment::TENANT-A::S-7",
  "deliveryState": "PENDING"
}
```

Consumer phải idempotent vì retry/delivery có thể xảy ra nhiều lần. Outbox không tự bảo đảm “exactly once” cho side effect bên ngoài; cần idempotency key, state reconciliation và cơ chế nhận diện đã xử lý.

### 13.3. Không nhầm eventual consistency với lỗi đã được giải quyết

Nếu hai document lệch trong vài giây và workflow sẽ hoàn thiện, phải có:

- Trạng thái chuyển tiếp được định nghĩa.
- SLA hoàn tất và timeout.
- Hành vi API khi còn `PENDING`.
- Retry/backoff và dead-letter/review.
- Metrics về backlog và thời gian pending.

“Có event” mà không có kiểm tra hoàn tất, retry hoặc reconciliation thì chưa phải một thiết kế đảm bảo toàn vẹn có thể vận hành.

## 14. TTL và xóa: vòng đời reference không tự đi theo vòng đời document

### 14.1. Tham chiếu chết vì TTL

Nếu Customer có TTL 30 phút nhưng Order phải lưu 7 năm:

```text
T0 Customer created, expiry=30m
T1 Order paid, customerId saved
T2 Customer expired
T3 Order still exists; customerId still present
```

Không có hành vi Couchbase mặc định tự xóa `order.customerId` hay cascade delete Order khi Customer hết TTL. Nếu Customer có retention ngắn, Order cần snapshot/hiển thị khác theo chính sách.

### 14.2. Phân biệt “không có match” với nguyên nhân lịch sử

KV `DocumentNotFoundException` có thể biểu hiện khi ID chưa tồn tại, đã xóa hoặc hết hạn. Một câu `LEFT JOIN` không match cũng không tự phân biệt các trường hợp ấy. Muốn hiển thị “đã xóa” hoặc “đã hết hạn” như kết luận chắc chắn, cần audit/event/tombstone nghiệp vụ đáng tin và được phép lưu.

Không bắt mọi exception thành “không tìm thấy”. Timeout, RBAC deny hoặc cluster unavailable phải được phân loại riêng.

### 14.3. TTL và cache/read model

Một hệ thống có Customer cache/read model cần đặt câu hỏi:

1. Khi nguồn hết TTL, cache có còn dữ liệu không?
2. Nếu quyền xem Customer bị thu hồi, có thể trả tên cũ từ cache không?
3. Snapshot lịch sử có hợp pháp và đúng nghĩa nghiệp vụ không?
4. TTL của claim/guard có thể hết **trước** tài nguyên được bảo vệ không?
5. Sau khi claim hết TTL, một writer khác có thể chiếm cùng business key và làm hai document “trùng logic” không?

Đặc biệt, **không gán TTL ngắn cho uniqueness guard** nếu document nghiệp vụ cần giữ key độc quyền lâu hơn. Hết hạn guard không tương đương giải phóng business key an toàn.

## 15. Soft delete và quá trình xóa nhiều bước

### 15.1. Soft delete giữ document nhưng đổi tính hợp lệ

Customer:

```json
{
  "tenantId": "TENANT-A",
  "customerCode": "C-42",
  "state": "INACTIVE",
  "deleted": true,
  "deletedAt": "2026-11-24T12:00:00Z"
}
```

vẫn có thể được KV GET hoặc SQL++ JOIN trả về. Nếu quy tắc nghiệp vụ nói “Order mới chỉ được tham chiếu Customer ACTIVE”, service phải kiểm tra `state`/`deleted` và chặn writer theo protocol. Không chỉ dựa vào document tồn tại.

### 15.2. Tránh xóa parent trước khi xử lý child

Một flow được thiết kế:

```text
Parent ACTIVE -> DELETING
    |
    +--> từ chối child writes mới theo guard
    +--> xử lý child batches idempotent
    +--> ghi checkpoint
    +--> reconcile
    +--> Parent DELETED / archive
```

Nếu workflow dừng giữa chừng, trạng thái `DELETING` cùng checkpoint cho phép resume. Nếu hard delete parent ngay từ đầu, một child chưa xử lý có thể thành orphan và khó xác định vì sao.

### 15.3. Không giữ PII chỉ để duy trì liên kết

Một Order lịch sử có thể cần giữ chứng từ nhưng không nhất thiết được giữ mọi dữ liệu cá nhân của Customer. Định nghĩa mục đích/sự cho phép của snapshot, retention, audit và policy xóa trước khi quyết định ARCHIVE.

`customerNameAtPurchase` hữu ích cho hóa đơn nhưng không mặc nhiên được giữ vô hạn.

## 16. Đường đọc khi dữ liệu liên kết không hợp lệ

### 16.1. `INNER JOIN` có thể làm mất parent

```sql
SELECT META(o).id AS orderId, c.displayName
FROM `commerce`.`sales`.`orders` AS o
JOIN `commerce`.`crm`.`customers` AS c
  ON KEYS o.customerId
WHERE o.tenantId = $tenantId;
```

Nếu không tìm thấy Customer, Order có thể biến mất khỏi kết quả. Điều này chỉ đúng nếu business **muốn loại những Order không có Customer hợp lệ**.

Với danh sách giao dịch đã thanh toán, việc mất Order vì Customer hết TTL có thể làm sai báo cáo.

### 16.2. `LEFT JOIN` giữ parent để xử lý fallback

```sql
SELECT META(o).id AS orderId,
       o.orderNumber,
       o.customerId,
       o.customerNameAtPurchase,
       c.displayName AS currentCustomerName
FROM `commerce`.`sales`.`orders` AS o
LEFT JOIN `commerce`.`crm`.`customers` AS c
  ON KEYS o.customerId
WHERE o.tenantId = $tenantId;
```

`currentCustomerName` có thể là `MISSING` khi không match, khác field JSON chứa `NULL`. DTO phải xử lý cả hai. Không dùng dữ liệu Customer sai tenant như fallback hợp lệ.

### 16.3. ANSI outer join và predicate phía phải

Nếu Order lưu `customerCode`:

```sql
SELECT META(o).id AS orderId,
       c.displayName AS activeCustomerName
FROM `commerce`.`sales`.`orders` AS o
LEFT JOIN `commerce`.`crm`.`customers` AS c
  ON o.tenantId = c.tenantId
 AND o.customerCode = c.customerCode
 AND c.deleted = FALSE
WHERE o.tenantId = $tenantId;
```

Điều kiện `c.deleted=FALSE` ở `ON` nhằm chỉ match Customer chưa xóa, **giữ Order không match**. Nếu chuyển nó xuống `WHERE`, các Order không có Customer có thể bị loại do `c.deleted` không thỏa.

Thêm `tenantId` vào `ON` khi business key chỉ unique trong tenant. Index phục vụ JOIN không tự đóng vai trò authorization.

### 16.4. Fallback phải không nói dối

Có thể dùng:

```sql
IFMISSINGORNULL(
  c.displayName,
  o.customerNameAtPurchase,
  "Thông tin khách hàng không khả dụng"
)
```

nhưng chuỗi fallback **không xác định** Customer đã xóa, hết TTL hay thiếu dữ liệu. Nếu cần xác định nguyên nhân, thiết kế audit/tombstone riêng và kiểm soát quyền xem.

## 17. GSI consistency: độ mới của query không đồng nghĩa toàn vẹn mạnh

### 17.1. KV và SQL++ qua index có độ mới khác nhau

`findById` theo document ID thường sử dụng KV. Query:

```sql
SELECT META(s).id AS shipmentId
FROM `commerce`.`sales`.`shipments` AS s
WHERE s.tenantId = $tenantId
  AND s.orderId = $orderId;
```

cần đường SQL++/index phù hợp. GSI duy trì bất đồng bộ với KV mutation, vì vậy một Shipment vừa ghi có thể chưa xuất hiện ngay trong query dùng index không chờ.

### 17.2. `NOT_BOUNDED`, `REQUEST_PLUS` và những gì chúng không làm

| Scan consistency | Mục tiêu | Không bảo đảm |
| --- | --- | --- |
| `NOT_BOUNDED` | Không yêu cầu chờ index bắt kịp mutation mới | Không phải read-after-write chắc chắn |
| `REQUEST_PLUS` | Chờ index bắt kịp các mutation liên quan tại thời điểm query | Không cấm writer mới tạo child sau query |
| KV GET theo ID | Đọc document đích trực tiếp | Không chứng minh mọi document liên kết đều hợp lệ |

Ngay cả khi query `REQUEST_PLUS` vừa chứng minh “không có Shipment”, một writer khác vẫn có thể insert Shipment sau đó. Do vậy **read consistency không thể thay thế giao thức ghi/xóa chống race**.

### 17.3. Không nhầm query transaction với FK constraint

Một transaction có thể dùng query trong phạm vi API hỗ trợ, nhưng điều đó không biến một predicate SQL++ thành constraint global áp dụng cho mọi thao tác ngoài transaction. Quy tắc cần được bảo vệ bởi writer protocol, shared guard hoặc một owner của quan hệ.

## 18. Spring Data mapping và repository: phần nào được bảo vệ?

### 18.1. Entity có reference và optimistic locking

```java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

@Document
@TypeAlias("salesOrder")
@Scope("sales")
@Collection("orders")
public class SalesOrder {
    @Id
    private String id;

    @Version
    private Long version;

    private String tenantId;
    private String customerId;
    private String orderNumber;
    private String customerNameAtPurchase;
    private String state;
    private String relationState;
    private Instant createdAt;

    // Constructor, getters và setters được lược bỏ.
}
```

`@Version` có thể bảo vệ optimistic concurrency trên chính document Order theo Spring Data Couchbase được hỗ trợ; nó **không** tự thay đổi Customer/Shipment.

### 18.2. Entity Shipment

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

@Document
@TypeAlias("shipment")
@Scope("sales")
@Collection("shipments")
public class Shipment {
    @Id
    private String id;

    private String tenantId;
    private String orderId;
    private String orderNumber;
    private String state;

    // Constructor, getters và setters được lược bỏ.
}
```

Repository:

```java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface ShipmentRepository
        extends CouchbaseRepository<Shipment, String> {

    List<Shipment> findByTenantIdAndOrderId(
        String tenantId,
        String orderId
    );
}
```

Đây là method truy vấn child theo field. Cần secondary index phù hợp nếu SQL++ được sử dụng. `save(shipment)` không tự xác nhận `orderId` tồn tại; service phải kiểm tra.

### 18.3. `@N1qlJoin` là fetch mapping, không phải write constraint

```java
import java.util.List;
import org.springframework.data.couchbase.core.query.N1qlJoin;
import org.springframework.data.couchbase.core.query.FetchType;

@N1qlJoin(
    on = "lks.tenantId = rks.tenantId " +
         "AND lks.orderNumber = rks.orderNumber",
    fetchType = FetchType.LAZY
)
private List<Shipment> shipments;
```

**Lưu ý mapping:** Ví dụ sử dụng `orderNumber` có thật trong JSON của cả `SalesOrder` và `Shipment`, cùng `tenantId`, để khai báo ANSI JOIN theo business key. `Shipment.orderId` vẫn là tham chiếu ID chính trong mô hình; nếu lưu thêm `orderNumber` để phục vụ JOIN, ứng dụng phải đồng bộ hai field và kiểm tra uniqueness theo tenant. Khi không muốn duy trì khóa nghiệp vụ thứ hai, có thể chọn truy vấn SQL++ `JOIN ... ON KEYS s.orderId` hoặc lookup KV tường minh. Dù `on` đúng, `@N1qlJoin` vẫn chỉ **tải** association; nó không sinh FK/cascade/unique constraint và không bảo đảm query được batch.

### 18.4. `CouchbaseTemplate`, repository và Java SDK cùng cần policy

Một ứng dụng có thể ghi Order bằng repository, ghi Shipment bằng `CouchbaseTemplate` và import Customer qua SDK. Nếu chỉ một đường ghi gọi validation nhưng đường còn lại bỏ qua, invariant không được bảo vệ.

Đặt quy tắc tạo/sửa/xóa quan hệ ở **application service/domain service** hoặc giao thức thư viện chung mà tất cả writer phải tuân thủ. Các quyền RBAC theo collection và contract sự kiện cũng cần khớp.

## 19. Ví dụ service: phân biệt validation với commit bảo đảm

### 19.1. Validation trước khi tạo Shipment

Ví dụ minh họa:

```java
public void validateNewShipment(
        String authenticatedTenant,
        SalesOrder parent) {
    if (!authenticatedTenant.equals(parent.getTenantId())) {
        throw new SecurityException("Tenant mismatch");
    }
    if (!"PAID".equals(parent.getState())) {
        throw new IllegalStateException("Order not ready");
    }
    if (!"OPEN".equals(parent.getRelationState())) {
        throw new IllegalStateException("Order is closing");
    }
}
```

Method này làm rõ điều kiện nghiệp vụ, **không** tự bảo đảm transaction hoặc chặn Order thay đổi sau khi return. Để duy trì invariant mạnh, đường lưu Shipment phải phối hợp với guard/transaction hoặc một owner xử lý tuần tự theo thiết kế.

### 19.2. Tách outcome rõ ràng

Một kiểu kết quả:

```java
public enum ReferenceCheckResult {
    VALID,
    NOT_REFERENCED,
    NOT_FOUND,
    INACTIVE,
    FORBIDDEN,
    TEMPORARILY_UNAVAILABLE
}
```

`NOT_FOUND` không phải kết luận lịch sử “đã xóa” hay “hết TTL”. `FORBIDDEN` không nên bị chuyển thành `NOT_FOUND` trong telemetry nội bộ chỉ để đơn giản hóa, dù API công khai có thể che sự tồn tại theo policy.

### 19.3. Không nuốt lỗi hạ tầng

Mẫu không nên dùng:

```java
try {
    return customerRepository.findById(customerId);
} catch (Exception anyError) {
    return Optional.empty(); // Sai: timeout/RBAC biến thành missing.
}
```

Thay vào đó, phân loại lỗi đúng SDK/repository version, chỉ xử lý trạng thái không tìm thấy như một kết quả hợp lệ; timeout, permission denied hoặc serialization failure cần đi theo đường lỗi/observability thích hợp.

## 20. Quan hệ nhiều–nhiều: edge document và uniqueness của membership

User tham gia Team là quan hệ N:M. Thay vì giữ hai mảng ID mirror và phải cập nhật cả hai phía trong mọi thao tác, có thể dùng document `membership`:

```json
{
  "_class": "membership",
  "tenantId": "TENANT-A",
  "userId": "user::TENANT-A::U-7",
  "teamId": "team::TENANT-A::T-4",
  "role": "MEMBER",
  "state": "ACTIVE",
  "joinedAt": "2026-11-20T08:15:00Z"
}
```

ID xác định:

```text
membership::<tenantId>::<userId-encoded>::<teamId-encoded>
```

### 20.1. Bất biến cần có

1. User tồn tại và được phép tham gia Team.
2. Team tồn tại, cùng tenant và đang nhận thành viên.
3. Có tối đa một membership active theo cặp tenant/user/team.
4. Chỉ người có quyền mới được đổi `role` hoặc `state`.
5. Khi User/Team bị xóa, membership có chính sách `RESTRICT`, `DETACH` hoặc cleanup rõ.

`insert-if-absent` với ID xác định có thể tránh hai membership document cùng ID. Nhưng nếu User/Team có thể bị xóa đồng thời, creator/deleter cần giao thức bảo vệ reference như phần trên.

### 20.2. Index hai chiều

```sql
CREATE INDEX ix_memberships_by_team
ON `commerce`.`sales`.`memberships`(
    `tenantId`, `teamId`, `state`
);

CREATE INDEX ix_memberships_by_user
ON `commerce`.`sales`.`memberships`(
    `tenantId`, `userId`, `state`
);
```

Index hỗ trợ đọc team members và user teams, **không** kiểm chứng User/Team còn tồn tại hay unique membership theo business key. Nếu association lớn, cần phân trang bằng query phù hợp; không tải vô hạn vào một List trong entity.

### 20.3. Không nhân đôi nguồn sự thật vô kiểm soát

Nếu ngoài Membership còn lưu `team.memberIds` và `user.teamIds`, phải xác định cái nào là nguồn chính, cái nào là read model. Cập nhật một phía rồi quên phía khác là lỗi toàn vẹn có thể kéo dài; thiết kế event/reconciliation cho bản sao.

## 21. Đối soát dữ liệu đã tồn tại: phát hiện, phân loại, sửa

Ngay cả với một giao thức ghi tốt, dữ liệu legacy, import thủ công, migration hoặc lỗi triển khai cũ có thể tạo dangling references. Cần **reconciliation**, không chỉ kiểm tra trong endpoint hiện tại.

### 21.1. Phát hiện Shipment thiếu Order

Với child có `orderId`, một truy vấn kiểm toán minh họa:

```sql
SELECT META(s).id AS shipmentId,
       s.tenantId,
       s.orderId
FROM `commerce`.`sales`.`shipments` AS s
LEFT JOIN `commerce`.`sales`.`orders` AS o
  ON KEYS s.orderId
WHERE s.tenantId = $tenantId
  AND s.orderId IS NOT MISSING
  AND s.orderId IS NOT NULL
  AND META(o).id IS MISSING
LIMIT 100;
```

Kết quả là **ứng viên orphan tại thời điểm query**, chưa chứng minh Order đã hard delete hay TTL. Cần recheck, policy và xử lý race trước khi sửa.

### 21.2. Phát hiện reference sai tenant

```sql
SELECT META(s).id AS shipmentId,
       s.tenantId AS shipmentTenant,
       s.orderId,
       o.tenantId AS orderTenant
FROM `commerce`.`sales`.`shipments` AS s
JOIN `commerce`.`sales`.`orders` AS o
  ON KEYS s.orderId
WHERE s.tenantId = $tenantId
  AND (
    o.tenantId IS MISSING
    OR o.tenantId IS NULL
    OR o.tenantId != s.tenantId
  )
LIMIT 100;
```

Đây là job audit có quyền phù hợp, không phải query endpoint công khai: nó có thể đọc dữ liệu cross-tenant để phát hiện lỗi, nên cần phân quyền riêng và giới hạn log PII.

### 21.3. Tạo checkpoint và kiểm soát tài nguyên

Một job có thể chạy:

```text
Scan pages per tenant
  -> record candidate
  -> KV recheck parent
  -> classify: missing / inactive / mismatch / unavailable
  -> apply policy with CAS/transaction
  -> persist checkpoint and metrics
```

Không chạy một query quét cả cluster không giới hạn. `LIMIT 100` không chắc giới hạn lượng index entries bị scan; dùng `EXPLAIN`/Query Profile và phân trang/checkpoint ổn định.

### 21.4. Idempotency và không xóa nhầm

Job nên có trạng thái ứng viên:

```json
{
  "id": "reconcile::TENANT-A::shipment::S-7",
  "tenantId": "TENANT-A",
  "referenceKind": "Shipment.orderId",
  "sourceId": "shipment::TENANT-A::S-7",
  "targetId": "order::TENANT-A::1001",
  "resolution": "NOT_FOUND_CANDIDATE",
  "action": "REVIEW",
  "attempts": 1
}
```

Nếu lúc scan thấy Order thiếu nhưng trước khi xử lý nó đã được phục hồi, phải **recheck**. Nếu Shipment đã thay `orderId`, CAS/`@Version` trên Shipment sẽ giúp tránh ghi đè kết quả mới. Job chạy lại không được làm mất tham chiếu hợp lệ.

## 22. Migration quan hệ: dual-write và backfill phải có định nghĩa tính đúng

Giả sử hệ thống cũ dùng:

```text
Order.customerCode = "C-42"
```

hệ thống mới muốn dùng:

```text
Order.customerId = "customer::TENANT-A::42"
```

### 22.1. Quy trình chuyển đổi theo giai đoạn

1. **Kiểm toán:** tìm Customer trùng `(tenantId,customerCode)`, thiếu Customer, dữ liệu mã khác kiểu hoặc khác tenant.
2. **Định nghĩa ID:** Customer ID phải ổn định; không tự suy ID cho business key mơ hồ.
3. **Expand schema:** Order mới ghi `customerId`; giữ `customerCode` nếu phiên bản cũ vẫn cần.
4. **Backfill:** cập nhật Order cũ có tham chiếu rõ ràng; ghi case không giải được vào queue.
5. **Theo dõi thay đổi trong lúc backfill:** writer/consumer có idempotency và version/checkpoint để không làm mất update mới.
6. **Đối chiếu:** so dữ liệu giải quan hệ qua ANSI JOIN cũ và `ON KEYS` mới trên mẫu đại diện.
7. **Canary:** chuyển read path cho một nhóm request/tenant; giám sát not-found và cross-tenant mismatch.
8. **Contract:** chỉ bỏ `customerCode`/index cũ khi các writer, reader và job legacy đã chuyển xong và có đường rollback.

### 22.2. Dual-write có thể thất bại giữa hai field/document

Nếu hai giá trị cùng được lưu trong Order **một lần replace document**, consistency nội document dễ kiểm soát hơn so với ghi sang hai collection khác nhau. Nhưng nếu phải cập nhật thêm Customer claim/read model độc lập, vẫn có failure window hoặc cần transaction/workflow.

Đừng báo migration hoàn tất chỉ vì backfill chạy hết; phải kiểm tra lỗi, replay, dữ liệu mới phát sinh và một thời gian quan sát sau switch.

### 22.3. Đổi tenant hoặc đổi ownership là migration bảo mật

Không chỉ sửa `tenantId` hoặc tiền tố ID. Chuyển entity giữa tenant ảnh hưởng RBAC, query, cache, index phạm vi, claim ID, references và audit. Cần workflow được phê duyệt và đối soát toàn bộ liên kết thay vì chỉ `repository.save` một field.

## 23. Spring Data reactive: concurrent writes và read-after-write

Reactive repository giúp điều phối I/O nhưng **không tự tạo transaction** hay tuần tự hóa các writer:

```java
Mono<Shipment> flow = reactiveOrderRepository
    .findById(orderId)
    .flatMap(order -> {
        validateNewShipment(tenantId, order);
        return reactiveShipmentRepository.save(shipment);
    });
```

Đây là **giả mã minh họa** với `validateNewShipment` và biến/bean do ứng dụng định nghĩa. Việc dùng `flatMap` chỉ sắp thứ tự “đọc Order trước, lưu Shipment sau” trong pipeline này; một request khác vẫn có thể xóa/chuyển trạng thái Order song song.

### 23.1. Reactive cần protocol giống synchronous

- Nếu cần invariant mạnh, dùng transaction/guard hoặc single-writer protocol phù hợp với reactive stack/version.
- Không `subscribe()` tùy tiện trong method rồi trả success trước khi write hoàn tất.
- Không nuốt mọi error bằng `onErrorResume(error -> Mono.empty())`; timeout/RBAC khác missing reference.
- Giới hạn concurrency khi tạo/xóa nhiều child, xử lý cancellation và retry idempotent.
- Theo dõi số lần ghi và result, không suy từ hoàn tất một publisher trung gian rằng cả workflow đã commit.

### 23.2. Độ mới khi query child sau KV write

GSI duy trì bất đồng bộ. Một reactive query SQL++ đọc child theo field ngay sau KV write có thể thấy dữ liệu tạm cũ nếu scan consistency không yêu cầu chờ. `REQUEST_PLUS`/mutation consistency có thể hữu ích trong những phiên bản hỗ trợ, nhưng **không thay thế giao thức ghi/xóa chống race**.

## 24. Observability và trách nhiệm của mọi writer

Một invariant chỉ tốt bằng **đường ghi yếu nhất**. Kiểm kê:

| Writer/đường thao tác | Có nguy cơ phá invariant nào? | Bằng chứng cần |
| --- | --- | --- |
| REST API Spring Boot | Tạo Shipment sai Order hoặc tenant | Validation, guard, integration test |
| Batch import | Bỏ qua service, tạo ID trùng nghiệp vụ | Quy tắc ID/claim và kiểm thử import |
| Scheduled cleanup | Xóa parent khi còn child mới | State transition, checkpoint, CAS |
| Event consumer | Xử lý sự kiện trùng/đến muộn | Idempotency key và version |
| Admin script | Ghi trực tiếp không qua validation | Runbook/quyền/approval/audit |
| Migration | Đổi schema/ID nhưng thiếu backfill | Reconciliation và rollback |
| Read model updater | Cập nhật bản sao lệch hoặc out-of-order | Source version, lag metrics |

### 24.1. Metric gợi ý

| Metric | Ý nghĩa |
| --- | --- |
| `reference.validation.failed` | Số yêu cầu không thỏa invariant tại write path |
| `reference.cross_tenant_blocked` | Số lần bị chặn vì tenant mismatch |
| `reference.guard.conflict` | Conflict CAS/transaction trên guard |
| `reference.orphan_candidates` | Số liên kết nghi vấn từ job scan |
| `reference.orphan_confirmed` | Số trường hợp xác nhận sau recheck |
| `reference.repair.success` | Số repair đúng policy |
| `reference.repair.retry` | Số lần sửa gặp conflict/tạm lỗi |
| `relationship.workflow.pending_age` | Thời gian một workflow liên kết chưa hoàn tất |
| `outbox.delivery.lag` | Độ trễ phát event/đối soát read model |
| `relationship.query.missing_ratio` | Tỷ lệ lookup không match theo endpoint/loại quan hệ |

Không đưa raw `customerId`, `orderId` hoặc email vào tên metric label; nguy cơ cardinality cao và lộ dữ liệu. Log đủ correlation/trace ID nhưng che PII theo chính sách.

### 24.2. Phân loại lỗi vận hành

**NOT_FOUND** không có nghĩa chắc chắn EXPIRED; **FORBIDDEN** không được xem là “không tồn tại” trong báo cáo nội bộ; **UNAVAILABLE** vì timeout/query failure không phải lỗi dữ liệu; **INACTIVE** là trạng thái business dù document còn tồn tại.

Đối với API công khai, có thể chọn 404 để không tiết lộ existence theo policy, nhưng telemetry nội bộ vẫn cần phân loại an toàn và rõ.

## 25. Kiểm thử invariant: tập tình huống nên có trong pipeline

| Test | Setup | Kỳ vọng |
| --- | --- | --- |
| Create Shipment hợp lệ | Order `OPEN` cùng tenant | Tạo đúng một child |
| Parent không tồn tại | `orderId` chưa từng được tạo | Chặn/tạo PENDING theo policy |
| Parent khác tenant | Shipment A trỏ Order B | Chặn, không lộ dữ liệu |
| Parent `CLOSING` | Order đang xóa | Không nhận child mới |
| Concurrent insert cùng ID | Hai request có cùng idempotency key | Một logical operation; duplicate được phân loại |
| Concurrent child create/delete parent | Hai writer chạy cùng lúc | Không có trạng thái “xóa thành công và child ACTIVE mồ côi” nếu invariant mạnh |
| Customer code duplicate | Hai ID chứa cùng `tenant/code` | Claim/guard hoặc import test phát hiện |
| Change reference với version cũ | Hai update cùng Order | CAS conflict, không overwrite |
| Soft delete | Customer `deleted=true` | Không dùng như Customer active |
| TTL expiry | Customer hết TTL, Order còn | Không đánh đồng với hard delete |
| Query GSI lag | Vừa insert Shipment | Đọc theo SLA; không xóa Order từ một count stale |
| LEFT JOIN missing | Order thiếu Customer | Giữ Order theo contract |
| INNER JOIN missing | Order thiếu Customer | Biết Order bị loại theo semantics |
| Index missing/offline | Query link qua field | Báo lỗi/query plan, không quy thành no reference |
| Outbox retry | Event được phát/nhận lại | Consumer idempotent |
| Reconcile race | Parent được phục hồi giữa scan và repair | Recheck + CAS, không detach sai |
| Legacy writer bypass | Import thử bỏ guard | Bị chặn bằng quyền/quy trình hoặc phát hiện qua audit |
| Reactive cancellation | Client hủy request | Không báo success không có commit; workflow có recover |

### 25.1. Kiểm thử concurrency phải tạo race có kiểm soát

Chỉ một unit test tuần tự “Order tồn tại → save Shipment” không chứng minh đúng khi có concurrent delete. Dùng integration test với barrier/coordination phù hợp để buộc hai luồng:

```text
Worker A: validate/prepare Shipment
                 |
           synchronization barrier
                 |
Worker B: close/delete Order
                 |
Worker A: attempt insert/commit
```

Kiểm tra kết quả cuối, transaction conflicts, retry và state của guard. Không chạy test phá hoại này trên production.

### 25.2. Test thay version không chỉ compile

Khi nâng Couchbase Server/Spring Data/SDK, kiểm tra:

- Mapping `@Version` và CAS có còn đúng.
- SQL++ generated từ repository và `@N1qlJoin` có thay đổi không.
- Transaction API, retry và exception types.
- Scope/collection/TTL mapping.
- `EXPLAIN` và Query Profile của những query kiểm toán.
- Quyền RBAC, service account và writer ngoài framework.

## 26. Bài thực hành: xây và kiểm chứng một invariant Shipment → Order

**Môi trường:** bucket/scope/collection thử nghiệm của Couchbase, Spring Data Couchbase và Java SDK bản được hỗ trợ, tài khoản có quyền thích hợp. Các thao tác xóa/TTL và test race chỉ thực hiện trong lab.

### Bước 1 — Tạo contract nghiệp vụ

Viết rõ:

```text
INVARIANT: Shipment.orderId bắt buộc tham chiếu Order hợp lệ
SCOPE: cùng tenant
STATE: Order.relationState phải OPEN khi tạo child
UNIQUENESS: shipmentRequestId không tạo duplicate shipment
DELETE: Order chuyển CLOSING trước khi cleanup
FAILURE: timeout != not found; retry idempotent
VALIDATION: tạo Order và Shipment phải theo protocol chung
```

Chọn mức bảo đảm:

- **Strong**: cần guard/transaction hoặc cơ chế writer coordination có kiểm chứng.
- **Eventual**: có `PENDING`, reconciliation SLA và không public child trước khi hợp lệ.

Không trộn hai mức bảo đảm trong cùng contract.

### Bước 2 — Tạo dữ liệu lab

Tạo:

- Order `order::TENANT-A::1001`, `relationState=OPEN`.
- Order `order::TENANT-A::1002`, `relationState=CLOSING`.
- Một Order tenant B có cùng `orderNumber` nhưng ID khác.
- Một Shipment hợp lệ của Order 1001.
- Một Shipment cố tình tham chiếu ID Order không tồn tại (chỉ để chạy audit).
- Hai request cùng `shipmentRequestId`.

### Bước 3 — Quan sát lỗi check-then-write

Tạo một service thử nghiệm:

```text
read Order
if relationState == OPEN:
    insert Shipment
```

Dùng concurrency barrier để cho delete process chuyển Order sang `CLOSING` ngay sau read. Ghi nhận trạng thái cuối. Mục đích là **minh họa race**, không phải cho code lỗi này vào production.

### Bước 4 — Thiết kế guard/transaction

Chuyển hai workflow:

```text
Create child:
  transaction -> read Order, validate OPEN,
                 conflict-bearing guard update,
                 insert child by stable ID

Close parent:
  transaction -> read Order,
                 guard update OPEN -> CLOSING
  then cleanup / verify / close
```

Test hai workflow chạy đồng thời. Đo số conflict và kết quả cuối. Nếu SDK/version/edition/config không hỗ trợ lựa chọn dự kiến, mô tả **blocker và phương án eventual protocol**, không tự khẳng định code đã atomic.

### Bước 5 — Chạy query audit

```sql
SELECT META(s).id AS shipmentId,
       s.tenantId, s.orderId
FROM `commerce`.`sales`.`shipments` AS s
LEFT JOIN `commerce`.`sales`.`orders` AS o
  ON KEYS s.orderId
WHERE s.tenantId = "TENANT-A"
  AND META(o).id IS MISSING
LIMIT 100;
```

Tìm candidate, KV recheck target rồi phân loại. Không hard delete Shipment chỉ vì anti-join trả một hàng. Đánh dấu mức độ nghiêm trọng theo trạng thái Shipment và policy.

### Bước 6 — Thử uniqueness claim

Chọn một pair `(tenantId,customerCode)`, thử hai request tạo Customer với ID ngẫu nhiên. Ghi nhận duplicate nếu không có guard. Sau đó thử claim ID xác định, `insert-if-absent` và transaction/workflow xử lý Customer + claim. Kiểm tra trường hợp claim tồn tại nhưng Customer không được tạo do lỗi giữa hai bước.

### Bước 7 — Thử TTL và LEFT JOIN

Tạo Customer tạm với TTL ngắn trong lab; Order tham chiếu Customer đó. Sau expiry:

- So KV lookup và SQL++ `LEFT JOIN` theo ID.
- Xác minh Order vẫn còn, trường Customer có thể vắng.
- Không báo “hard delete” nếu chỉ có `NOT_FOUND`.
- Kiểm tra fallback lịch sử và policy dữ liệu cá nhân.

### Bước 8 — Kết quả và báo cáo

| Thử nghiệm | Expected invariant | Observed | Query/KV count | Conflict/error | Kết luận |
| --- | --- | --- | --- | --- | --- |
| Create hợp lệ | Same tenant, OPEN | Chưa đo | Chưa đo | Chưa đo | |
| Parent không tồn tại | Chặn hoặc PENDING theo policy | Chưa đo | Chưa đo | Chưa đo | |
| Parent CLOSING | Không ACTIVE child mới | Chưa đo | Chưa đo | Chưa đo | |
| Concurrent create/delete | Không phá invariant strong | Chưa đo | Chưa đo | Chưa đo | |
| Duplicate request | Một logical shipment | Chưa đo | Chưa đo | Chưa đo | |
| Unique claim Customer | Một logical business key | Chưa đo | Chưa đo | Chưa đo | |
| TTL + LEFT JOIN | Giữ Order, Customer có thể vắng | Chưa đo | Chưa đo | Chưa đo | |
| Reconciliation race | Không detach sai | Chưa đo | Chưa đo | Chưa đo | |

“Chưa đo” là chỗ học viên điền khi làm lab; đây **không phải số liệu benchmark đã được chạy**.

## 27. Chẩn đoán lỗi triển khai quan hệ

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Shipment mới tham chiếu Order vừa bị xóa | Check-then-write race | Parent guard và giao thức creator/deleter chung |
| Query COUNT child trả 0 nhưng sau xóa còn child | GSI lag hoặc child writer mới insert | Guard, consistency, two-phase close, recheck |
| Hai Customer có cùng code | ID khác nhau, không có unique claim | Canonical key + insert-if-absent/transaction |
| Claim tồn tại nhưng không có Customer | Ghi claim và entity rời rạc bị lỗi giữa chừng | Transaction hoặc workflow reconcile |
| `@Version` có mà Customer vẫn bị xóa | CAS chỉ bảo vệ document có version | Thiết kế cross-document invariant |
| Ghi trong transaction nhưng job khác phá constraint | Writer ngoài giao thức | Quyền/writer audit, dùng shared guard |
| `@N1qlJoin` trả rỗng khi đích đã xóa | Không có FK/cascade, fetch không match | Define fallback/retention |
| `LEFT JOIN` làm Order biến mất | Filter phía Customer đặt ở `WHERE` | Sửa semantics `ON`/`WHERE` |
| JOIN Customer tenant khác | ID sai tenant hoặc ANSI thiếu tenant | Validation và authorization hai phía |
| Workflow xóa dở không kết thúc | Không có checkpoint/retry | Saga state, idempotency, pending-age metrics |
| TTL claim hết trước Customer | Claim bị giải phóng sớm | Đồng bộ lifecycle guard/business resource |
| Migration đổi reference gây orphan | Backfill thiếu hoặc dual-write lệch | Phased rollout, reconciliation và rollback |
| Batch scan quá chậm | Index/partition/checkpoint kém | `EXPLAIN`, keyset pagination, giới hạn tải |
| `REQUEST_PLUS` nhưng vẫn có race | Scan consistency không khóa writer mới | Guard/transaction protocol |
| Reactive flow trả success nhưng write chưa xong | `subscribe()` rời rạc hoặc bỏ error | Compose publisher, chờ terminal result |
| Retry tạo hai Shipment | Không có idempotency key ổn định | Stable ID, compare payload/response |
| Cache vẫn trả Customer đã xóa | Read model/cache invalidation sai | Policy retention, invalidate/refresh |
| DDL index mới làm mutation chậm | Write amplification/Index Service load | Tối ưu số index, đo read/write trade-off |

## 28. Câu hỏi tự kiểm tra

1. Một field `orderId` không rỗng bảo đảm điều gì và **không** bảo đảm điều gì?
2. Vì sao Couchbase `JOIN` không tương đương foreign key constraint?
3. Khi nào nên nhúng child vào parent thay vì tách collection?
4. Vì sao một index `(tenantId, customerCode)` không tạo uniqueness nghiệp vụ?
5. ID xác định và `insert-if-absent` bảo vệ phạm vi uniqueness nào?
6. Vì sao tạo claim rồi tạo Customer bằng hai thao tác rời rạc có failure window?
7. Check-then-write tạo Shipment gặp TOCTOU trong tình huống nào?
8. Vì sao transaction chỉ đọc Order rồi insert Shipment có thể vẫn chưa đủ nếu deleter không dùng điểm xung đột chung?
9. Parent `OPEN → CLOSING` giải quyết bước nào trong quy trình RESTRICT/CASCADE?
10. Vì sao `REQUEST_PLUS` không cấm Shipment được insert sau một query COUNT?
11. CAS/`@Version` bảo vệ document nào và không thay thế cơ chế nào?
12. Outbox giúp giải quyết tình huống gì và vì sao consumer vẫn cần idempotency?
13. Những field nào nên được giữ như snapshot lịch sử thay vì JOIN dữ liệu hiện hành?
14. TTL của uniqueness guard cần liên hệ gì với TTL của business entity?
15. Vì sao `INNER JOIN` có thể làm biến mất Order hợp lệ khi Customer hết TTL?
16. `LEFT JOIN` có thể làm mất parent do predicate phía phải ở `WHERE` ra sao?
17. Khi nào dùng KV `ON KEYS`, khi nào dùng ANSI JOIN theo business key?
18. Nếu Customer khác tenant bị tìm thấy theo ID, lớp nào phải chặn việc trả dữ liệu?
19. Vì sao recheck bằng KV gần thời điểm repair và CAS update parent lại quan trọng?
20. Một job audit trả candidate orphan có chứng minh parent đã hard delete không?
21. Vì sao không nên đưa raw document ID vào metric labels?
22. Với membership N:M, vì sao edge ID xác định vẫn cần parent lifecycle protocol?
23. Các bước chính để chuyển reference từ `customerCode` sang `customerId` là gì?
24. Nêu hai case concurrency test cần có trước rollout một invariant mạnh.
25. Vì sao reactive `flatMap` không tự tạo transaction?
26. Kể tên ba số liệu production giúp biết giao thức quan hệ có đang thất bại.

## 29. Tài liệu tham khảo và hướng xác minh phiên bản

Khi xây hệ thống thực, dùng tài liệu **đúng phiên bản** Spring Data Couchbase, Java SDK và Couchbase Server:

- [Spring Data Couchbase — Reference](https://docs.spring.io/spring-data/couchbase/reference/): document mapping, optimistic locking, repositories, operations và query.
- [Spring Data Couchbase — ANSI Joins](https://docs.spring.io/spring-data/couchbase/reference/couchbase/ansijoins.html): `@N1qlJoin`, alias `lks`/`rks` và fetch options.
- [Couchbase Java SDK — KV Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): `get`, `insert`, `replace`, `remove`, CAS/expiry.
- [Couchbase Java SDK — Transactions](https://docs.couchbase.com/java-sdk/current/howtos/distributed-acid-transactions-from-the-sdk.html): transaction boundary, retry và usage theo SDK.
- [Couchbase Server — JOIN](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/join.html): ANSI/key joins, điều kiện `ON`, inner/left semantics.
- [Couchbase Server — EXPLAIN](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/explain.html): xác minh query plan/index.

Các ví dụ về guard và domain state là **mẫu thiết kế ứng dụng**, không phải một tính năng FK tích hợp của Couchbase. Nếu cần bất biến mạnh, hãy chứng minh nó bằng integration test cạnh tranh và kiểm tra tất cả writer — không chỉ dựa vào việc code biên dịch hoặc một query trả đúng dữ liệu.

## 30. Kết luận

**Toàn vẹn tham chiếu trong mô hình document là trách nhiệm có ranh giới rõ của ứng dụng.** Couchbase cung cấp ID, KV insert, CAS, index, query và transaction để hỗ trợ, nhưng không tự biết Order nào được phép có Shipment, Customer nào có thể xóa, hay uniqueness nghiệp vụ nào phải giữ giữa nhiều collection. `@N1qlJoin` và SQL++ `JOIN` giúp **đọc quan hệ**, chứ không tạo ràng buộc khi ghi.

Muốn quan hệ bền vững, hãy bắt đầu từ **invariant được viết rõ**, chọn aggregate boundary hợp lý, dùng ID/claim xác định khi cần uniqueness, thiết kế creator/deleter cùng một guard khi cần bảo đảm mạnh, và dùng transaction hoặc workflow idempotent khi nhiều document tham gia. Trên đường đọc, xử lý dữ liệu vắng đúng ngữ nghĩa; trong vận hành, có migration, reconciliation, telemetry và kiểm thử race. Kết hợp tenant/RBAC, TTL, CAS và GSI consistency đúng phạm vi sẽ giúp hệ thống **không chỉ ghép được dữ liệu, mà còn duy trì được ý nghĩa và tính đúng của quan hệ qua mọi thay đổi**.
