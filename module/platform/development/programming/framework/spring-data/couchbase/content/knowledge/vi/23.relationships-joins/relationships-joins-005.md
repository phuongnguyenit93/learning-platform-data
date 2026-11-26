# `@N1qlJoin` và khai báo điều kiện liên kết entity trong Spring Data Couchbase

Trong một ứng dụng Spring Data Couchbase, hai class Java có thể thể hiện quan hệ nghiệp vụ, nhưng **việc đặt field `customerCode` giống nhau trên hai entity không tự tạo khóa ngoại hoặc một phép JOIN**. Khi cần truy cập các entity liên quan qua **trường dữ liệu JSON**, Spring Data Couchbase cung cấp annotation `@N1qlJoin` để khai báo điều kiện liên kết ngay trên **field tham chiếu của entity**. Framework có thể dùng điều kiện ấy khi tải các entity liên quan qua ANSI JOIN của Couchbase SQL++.

Điểm quan trọng là phải hiểu rõ giới hạn của sự tiện lợi này. `@N1qlJoin` không biến Couchbase thành ORM quan hệ với foreign key, cascade hoặc tính nguyên tử đa document tự động. Nó cũng không bảo đảm rằng mọi phép tải quan hệ đều rẻ: một field tải tức thời trên hàng trăm entity có thể tạo thêm nhiều công việc đọc, trong khi tải lười có thể phát sinh truy vấn khi UI hoặc bộ tuần tự JSON truy cập field.

Bài thuộc chương **Quan hệ và JOIN** của module **SPRING_DATA_COUCHBASE** — xây dựng tầng truy cập Couchbase bằng document mapping, repository, `CouchbaseTemplate` và SQL++; kết hợp thiết kế bucket/scope/collection, index, TTL, CAS, giao dịch và API reactive để giữ hiệu năng, tính nhất quán và khả năng vận hành.

Trong tài liệu Spring Data Couchbase hiện đại, annotation nằm trong package `org.springframework.data.couchbase.core.query`, khai báo trên field, yêu cầu tham số `on`, hỗ trợ các bí danh `lks` và `rks`. API và hành vi cụ thể cần được kiểm tra với **phiên bản Spring Data Couchbase/Couchbase Server đang triển khai**, nhất là khi liên kết qua scope/collection hoặc dùng tính năng fetch/hint nâng cao.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích `@N1qlJoin` dùng để khai báo **quan hệ truy vấn** giữa entity, khác với nhúng object JSON và field lưu document ID.
2. Viết `on = "lks... = rks..."` cho quan hệ 1:1 và 1:N, kết hợp nhiều điều kiện bằng `AND` và đưa tenant vào khóa ghép.
3. Phân biệt `on` (join criteria) và `where` (điều kiện lọc bổ sung), đánh giá ảnh hưởng khi dữ liệu phía phải thiếu.
4. Sử dụng `fetchType = FetchType.IMMEDIATE` và `FetchType.LAZY` có chủ đích; nhận biết fan-out/N+1 và việc gọi getter có thể kích hoạt I/O.
5. Biết vai trò và ranh giới của `index`, `rightIndex`, `hashside` và `keys`; ưu tiên `EXPLAIN` trước khi đưa hint cố định vào production.
6. Thiết kế composite index cho hai collection, đối chiếu SQL++ thực được sinh ra và đo Query Profile.
7. Xử lý business key không duy nhất, `NULL`/`MISSING`, orphan, soft delete, quyền tenant, TTL, CAS, giao dịch và scan consistency.
8. Chọn thời điểm dùng `@N1qlJoin`, `@Query` hoặc KV/Java SDK trực tiếp theo hợp đồng API.

## 2. Bối cảnh: một Order liên quan Customer và nhiều Shipment

Giả sử bucket `commerce` chứa ba collection:

```text
commerce
├── sales
│   ├── orders
│   └── shipments
└── crm
    └── customers
```

Document Order có ID `order::TENANT-A::1001` tại `commerce.sales.orders`:

```json
{
  "_class": "salesOrder",
  "tenantId": "TENANT-A",
  "orderNumber": "ORD-1001",
  "customerCode": "C-42",
  "status": "PAID",
  "createdAt": "2026-11-20T08:15:00Z",
  "total": 1500000,
  "deleted": false
}
```

Document Customer có ID `customer::TENANT-A::42` tại `commerce.crm.customers`:

```json
{
  "_class": "customer",
  "tenantId": "TENANT-A",
  "customerCode": "C-42",
  "displayName": "Nguyen An",
  "accountStatus": "ACTIVE"
}
```

Hai document Shipment tại `commerce.sales.shipments`:

```json
{
  "_class": "shipment",
  "tenantId": "TENANT-A",
  "orderNumber": "ORD-1001",
  "trackingNumber": "TRACK-7001",
  "state": "IN_TRANSIT",
  "shippedAt": "2026-11-21T08:00:00Z"
}
```

```json
{
  "_class": "shipment",
  "tenantId": "TENANT-A",
  "orderNumber": "ORD-1001",
  "trackingNumber": "TRACK-7002",
  "state": "PREPARING",
  "shippedAt": null
}
```

Ở mô hình này:

- **Order → Customer** là quan hệ nghiệp vụ 0..1 hoặc 1:1, dựa trên cặp `(tenantId, customerCode)`.
- **Order → Shipment** là quan hệ 1:N, dựa trên cặp `(tenantId, orderNumber)`.
- `customerCode` và `orderNumber` là field JSON, **không phải document ID của entity được tham chiếu**.
- Document độc lập có thể thay đổi hoặc bị xóa mà không tự kéo theo cập nhật/xóa các document khác.

Muốn hiển thị Order cùng Customer và danh sách Shipment, có thể sử dụng SQL++ tường minh, nhiều lần KV/Query, read model hoặc `@N1qlJoin` trên field liên quan. Bài này tập trung vào lựa chọn cuối.

## 3. `@N1qlJoin` là annotation gì?

### 3.1. Vị trí sử dụng và ý nghĩa

`@N1qlJoin` là annotation của Spring Data Couchbase:

```java
import org.springframework.data.couchbase.core.query.N1qlJoin;
```

Annotation được đặt lên **field của entity bên trái** và diễn đạt điều kiện liên kết với **entity đích**. Field có thể là một entity tham chiếu đơn lẻ hoặc tập các entity liên quan theo mô hình được Spring Data hỗ trợ.

Ví dụ ở mức khái niệm:

```java
@N1qlJoin(on = "lks.customerCode = rks.customerCode")
private Customer customer;

@N1qlJoin(on = "lks.orderNumber = rks.orderNumber")
private List<Shipment> shipments;
```

Hai field này được **khai báo như quan hệ để tải**, không phải object JSON nhất thiết phải được nhúng vào document Order. Cách một annotation được materialize, query phát sinh, lifecycle của proxy và hành vi khi entity thiếu cần kiểm tra trên phiên bản framework đang chạy.

### 3.2. `lks` và `rks`

Hai bí danh trong biểu thức annotation có ý nghĩa:

| Bí danh | Nghĩa | Trong ví dụ Order |
| --- | --- | --- |
| `lks` | *Left key space*: entity hiện tại mang field `@N1qlJoin` | `SalesOrder`, collection `orders` |
| `rks` | *Right key space*: entity liên quan được khai báo ở field | `Customer` hoặc `Shipment` |

Vì vậy:

```java
@N1qlJoin(on = "lks.orderNumber = rks.orderNumber")
private List<Shipment> shipments;
```

không phải so sánh hai field của cùng một document. Nó biểu thị **điều kiện matching giữa hai tập document**. Khi tham chiếu field ở phía Order, dùng `lks.`; khi tham chiếu field phía Shipment, dùng `rks.`.

Đừng dùng alias `o` hoặc `s` từ một SQL++ viết tay trong `on` nếu annotation yêu cầu `lks`/`rks`. Đó là các bí danh **do API của annotation quy ước**.

### 3.3. `on` là bắt buộc

Tham số `on` là biểu thức boolean cho tiêu chí join. Nó có thể là một equality đơn hoặc nhiều điều kiện ghép:

```java
@N1qlJoin(
    on = "lks.tenantId = rks.tenantId " +
         "AND lks.customerCode = rks.customerCode"
)
private Customer customer;
```

Không nên bỏ điều kiện `tenantId` trong ứng dụng multi-tenant chỉ vì `customerCode` có vẻ duy nhất trong dữ liệu test. Hai tenant có thể cùng sử dụng mã `C-42`, khiến kết quả join sai hoặc lộ dữ liệu.

`on` có thể biểu diễn điều kiện phức tạp hơn, nhưng **càng phức tạp càng khó tối ưu/kiểm chứng**. Ví dụ `OR` hoặc hàm biến đổi field có thể làm index khó được dùng hiệu quả. Chỉ thêm những biểu thức thật sự cần cho nghiệp vụ.

## 4. Ví dụ khai báo quan hệ 1:1: Order → Customer

### 4.1. Entity Customer

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@TypeAlias("customer")
@Scope("crm")
@Collection("customers")
public class Customer {
    @Id
    private String id;
    private String tenantId;
    private String customerCode;
    private String displayName;
    private String accountStatus;

    // Constructor, getters và setters được lược bỏ.
}
```

### 4.2. Entity Order khai báo field liên kết

```java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.query.N1qlJoin;

@Document
@TypeAlias("salesOrder")
@Scope("sales")
@Collection("orders")
public class SalesOrder {
    @Id
    private String id;

    private String tenantId;
    private String orderNumber;
    private String customerCode;
    private String status;
    private Instant createdAt;

    @N1qlJoin(
        on = "lks.tenantId = rks.tenantId " +
             "AND lks.customerCode = rks.customerCode"
    )
    private Customer customer;

    // Constructor, getters và setters được lược bỏ.
}
```

**Giải thích:**

1. `SalesOrder` là entity bên trái; `customer` là field liên kết tới entity bên phải.
2. Điều kiện `on` dùng **hai field JSON chung** trong hai collection, không dựa trên ID của Customer.
3. `@Scope` và `@Collection` xác định collection của từng entity trong mô hình mapping Spring Data hỗ trợ. Bucket `commerce` còn phải đến từ cấu hình runtime.
4. Một Customer hợp lệ phải khớp cả `tenantId` và `customerCode`. Nếu không có bản ghi khớp, ứng dụng phải định nghĩa hành vi với association vắng.
5. Vì kiểu field là `Customer`, nghiệp vụ đang kỳ vọng **tối đa một Customer**. Nếu phía phải có nhiều document trùng cặp key, cần xử lý **lỗi dữ liệu/uniqueness**, không chấp nhận âm thầm chọn một Customer ngẫu nhiên.

`@N1qlJoin` không tạo foreign key, cũng không tự sinh một unique constraint trên `(tenantId, customerCode)`. Đó là yêu cầu thiết kế riêng.

### 4.3. SQL++ tương đương về ý tưởng

Để hiểu điều kiện mà annotation mô tả, trước tiên viết một câu SQL++ **diễn giải nghiệp vụ**, không khẳng định đây là SQL++ chính xác framework sinh ra:

```sql
SELECT META(o).id AS orderId,
       o.customerCode,
       c.displayName AS customerName
FROM `commerce`.`sales`.`orders` AS o
LEFT JOIN `commerce`.`crm`.`customers` AS c
  ON o.tenantId = c.tenantId
 AND o.customerCode = c.customerCode
WHERE o.tenantId = "TENANT-A";
```

Điều quan trọng là **bộ điều kiện liên kết** tương ứng. Spring Data có thể tạo thêm projection, bộ lọc loại entity, alias, điều kiện `where` hoặc các truy vấn phụ tùy `fetchType` và phương thức đọc. Không dùng câu SQL++ viết tay trên để kết luận chi phí thật nếu chưa quan sát query runtime.

## 5. Ví dụ khai báo quan hệ 1:N: Order → Shipments

### 5.1. Entity Shipment độc lập

```java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@TypeAlias("shipment")
@Scope("sales")
@Collection("shipments")
public class Shipment {
    @Id
    private String id;
    private String tenantId;
    private String orderNumber;
    private String trackingNumber;
    private String state;
    private Instant shippedAt;

    // Constructor, getters và setters được lược bỏ.
}
```

### 5.2. Field tập hợp với `@N1qlJoin`

Trong `SalesOrder`, bổ sung:

```java
import java.util.List;
import org.springframework.data.couchbase.core.query.FetchType;
import org.springframework.data.couchbase.core.query.N1qlJoin;

@N1qlJoin(
    on = "lks.tenantId = rks.tenantId " +
         "AND lks.orderNumber = rks.orderNumber",
    fetchType = FetchType.LAZY
)
private List<Shipment> shipments;
```

Với kiểu `List<Shipment>`, quan hệ mô tả **một Order có nhiều Shipment**. Nếu Order `ORD-1001` có hai Shipment, truy vấn liên quan có thể trả về danh sách hai entity phía phải khi field được tải.

Tuy nhiên, **không được giả định list có thứ tự `shippedAt DESC`** chỉ vì các document có field thời gian. Annotation với điều kiện `on` chỉ nói tài liệu nào khớp; nếu API cần thứ tự ổn định, phải thiết kế truy vấn/sắp xếp rõ ràng và test.

### 5.3. Khai báo quan hệ không có nghĩa Cascade Save/Delete

Một `SalesOrder` có field `List<Shipment>` gắn `@N1qlJoin` không chứng minh rằng:

- `orderRepository.save(order)` tự insert/replace toàn bộ Shipment.
- Xóa Order tự xóa những Shipment liên quan.
- Tạo Order và mọi Shipment là một transaction.
- Chỉnh sửa `List<Shipment>` Java tự phản ánh dữ liệu trên collection đích.

`@N1qlJoin` được thiết kế để **tải các associated entities qua truy vấn**. Hành vi persistence của collection con phải được quản lý bằng repository/operations, transaction hoặc luồng nghiệp vụ tương ứng. Đừng coi nó là một `@OneToMany(cascade = ALL)` của JPA.

### 5.4. Khi mảng quan hệ quá lớn

Một Order có tối đa vài Shipment thường có thể tải thành list. Nhưng với một quan hệ 1:N hàng chục nghìn Event, không nên mặc định đặt `@N1qlJoin` tải toàn bộ `List<OrderEvent>` khi hiển thị một Order.

Thay vào đó:

```sql
SELECT META(e).id AS eventId,
       e.eventTime,
       e.eventType
FROM `commerce`.`sales`.`order_events` AS e
WHERE e.tenantId = "TENANT-A"
  AND e.orderNumber = "ORD-1001"
ORDER BY e.eventTime DESC
LIMIT 50;
```

và một repository/Query Service API chuyên cho **phân trang entity con**. Dù dùng `LAZY`, nếu cuối cùng gọi getter để tải mọi event, tổng chi phí vẫn lớn.

## 6. `FetchType.IMMEDIATE` và `FetchType.LAZY`

### 6.1. Mặc định là IMMEDIATE

Theo API `@N1qlJoin` của Spring Data Couchbase, `fetchType` có mặc định:

```java
@N1qlJoin(
    on = "lks.tenantId = rks.tenantId " +
         "AND lks.orderNumber = rks.orderNumber",
    fetchType = FetchType.IMMEDIATE
)
private List<Shipment> shipments;
```

`IMMEDIATE` nghĩa là framework có thể tiến hành tải associated entities trong quá trình tải entity gốc theo đường đi được hỗ trợ. Thuận tiện cho màn hình thực sự luôn cần quan hệ, nhưng nguy cơ là **đọc nhiều hơn yêu cầu**, đặc biệt khi một trang chỉ cần `orderNumber` và `status`.

Không phải mọi `findById`/query đều có cùng một SQL++ hoặc số round trip; cần thu thập log query và thực nghiệm với phiên bản framework đang dùng.

### 6.2. LAZY trì hoãn đến khi truy cập field

```java
@N1qlJoin(
    on = "lks.tenantId = rks.tenantId " +
         "AND lks.orderNumber = rks.orderNumber",
    fetchType = FetchType.LAZY
)
private List<Shipment> shipments;
```

Tài liệu Spring Data mô tả lazy fetch là **tải associated entities khi field được truy cập lần đầu**, thay vì tải ngay. Trong enum `FetchType`, lần fetch lazy được mô tả là thực hiện **một lần trên association đó** theo semantics của API.

Đây không phải bảo đảm rằng toàn bộ request chỉ có một query: một trang gồm N Order, mỗi Order có association lazy riêng, có thể dẫn đến **N lượt fetch quan hệ** nếu code thực sự truy cập N field.

### 6.3. Lazy loading và N+1

Hình dung một endpoint:

```java
List<SalesOrder> orders = repository
    .findByTenantIdAndStatus("TENANT-A", "PAID");

for (SalesOrder order : orders) {
    // Mỗi lần truy cập association có thể kích hoạt việc tải.
    int shipmentCount = order.getShipments().size();
    // Tạo một dòng danh sách.
}
```

Nếu truy vấn lấy 100 Order, dù bản thân query gốc nhanh, bước `getShipments()` có thể làm tổng số truy vấn hoặc lượng dữ liệu lớn hơn nhiều. Ngay cả khi lazy chỉ fetch một lần trên mỗi object, **100 object có thể có 100 association khác nhau**.

Đo số query/round trip, p95 latency và tải Query/Index Service; không chỉ đo thời gian `repository.findBy...` trước vòng lặp.

### 6.4. Truy cập do serialization hoặc logging

Các framework JSON serializer, mapper DTO, công cụ debug hoặc `toString()` có thể truy cập getter và vô tình kích hoạt lazy fetch. Ví dụ trả thẳng entity với field `getShipments()` qua REST có thể biến một danh sách đơn nhẹ thành response chứa nhiều Shipment.

Một cách quản lý:

1. Dùng **DTO tường minh** cho API list, không expose nguyên object graph entity.
2. Không truy cập association lazy từ `toString()`, `equals()` hay log cấu trúc entity.
3. Khi cần chi tiết, gọi rõ nghiệp vụ tải Shipment theo orderNumber và giới hạn kết quả.
4. Kiểm thử serialization thật, kể cả trường hợp association không có match.

### 6.5. Với reactive API, không tự giả định LAZY là non-blocking

`ReactiveCouchbaseRepository` và reactive template có đường thực thi bất đồng bộ của chúng; trong khi lazy association là một cơ chế riêng. Không được suy rằng truy cập `getShipments()` từ một chuỗi Reactor **chắc chắn không chặn thread**, hoặc tự tương đương một `Flux<Shipment>` có backpressure.

Nếu hệ thống reactive yêu cầu kiểm soát I/O rõ ràng, cân nhắc repository reactive cho Shipment hoặc SQL++ query riêng trả `Flux`/`Mono` phù hợp phiên bản. Đo và test đường đi thực tế thay vì chỉ thay `IMMEDIATE` bằng `LAZY`.

## 7. Phân biệt `on` với `where` trong annotation

### 7.1. `on` định nghĩa điều kiện matching

Quan hệ Order–Shipment phải khớp:

```java
@N1qlJoin(
    on = "lks.tenantId = rks.tenantId " +
         "AND lks.orderNumber = rks.orderNumber"
)
private List<Shipment> shipments;
```

Điều kiện này nói **Shipment nào thuộc Order nào**. Nếu bỏ `tenantId`, hai tenant có thể dùng cùng `ORD-1001` và join nhầm dữ liệu.

### 7.2. `where` bổ sung điều kiện liên quan đến tập kết quả

Ví dụ chỉ quan tâm những Shipment chưa bị xóa mềm:

```java
@N1qlJoin(
    on = "lks.tenantId = rks.tenantId " +
         "AND lks.orderNumber = rks.orderNumber",
    where = "rks.deleted = FALSE"
)
private List<Shipment> activeShipments;
```

Đoạn code này **giả định document Shipment có field `deleted`** trong schema thực; nếu không có field hoặc giá trị `NULL`/`MISSING`, predicate cần được thiết kế lại. Nó minh họa tham số `where` mà API hỗ trợ và sử dụng bí danh `rks`.

**Không coi `where` và `on` là hai tham số có thể hoán đổi vô điều kiện.** Trong SQL++ với `LEFT JOIN`, điều kiện phía phải đặt trong `WHERE` có thể loại luôn hàng bên trái không match, trong khi điều kiện đặt ở `ON` có nghĩa giới hạn những match hợp lệ. Cần **xem SQL++ framework thực sự sinh ra và kiểm thử trường hợp không có Shipment**, nhất là khi yêu cầu giữ Order thiếu association.

### 7.3. Điều kiện composite và diễn đạt nghiệp vụ

Ví dụ một hệ thống đơn hàng lưu `channel` và shipment cũng lưu kênh:

```java
@N1qlJoin(
    on = "lks.tenantId = rks.tenantId " +
         "AND lks.orderNumber = rks.orderNumber " +
         "AND lks.channel = rks.channel"
)
private List<Shipment> channelShipments;
```

Điều kiện thứ ba chỉ nên thêm khi business thực sự coi shipment khác `channel` là **không thuộc association**. Đừng thêm mọi field trùng tên vào `on` để “an toàn” vì điều kiện quá chặt có thể làm mất quan hệ hợp lệ.

### 7.4. Không dùng phép biến đổi không nhất quán trên join key

```java
@N1qlJoin(
    on = "LOWER(lks.customerCode) = LOWER(rks.customerCode)"
)
private Customer customer;
```

Đây là ví dụ ý tưởng về biểu thức có hàm được SQL++ hỗ trợ; nhưng nó **không giải quyết** vấn đề mã Customer chỉ duy nhất trong tenant, và có thể làm optimizer khó dùng index field thông thường.

Ưu tiên chuẩn hóa dữ liệu lúc ghi, hoặc dùng field `customerCodeNormalized` ổn định và index tương ứng. Chỉ dùng function trong `on` sau khi xác nhận kết quả, khả năng index và chi phí thực.

## 8. Tóm tắt các phần tử của API `@N1qlJoin`

Tùy phiên bản Spring Data Couchbase, annotation có các phần tử sau:

| Phần tử | Tính chất | Ý nghĩa vận hành |
| --- | --- | --- |
| `on` | **Bắt buộc** | Biểu thức matching của hai entity, dùng `lks`/`rks` |
| `fetchType` | Tùy chọn; mặc định `IMMEDIATE` | Tải liên kết ngay hoặc trì hoãn đến khi truy cập field |
| `where` | Tùy chọn; mặc định chuỗi rỗng | Điều kiện lọc bổ sung cho phép tải association |
| `index` | Tùy chọn | Hint index cho phía `lks` trong dạng indexed nested-loop join được hỗ trợ |
| `rightIndex` | Tùy chọn | Hint index cho phía `rks` trong dạng indexed nested-loop join được hỗ trợ |
| `hashside` | Tùy chọn; mặc định `NONE` | Hint phía build/probe của hash join; cần xác minh hỗ trợ của edition |
| `keys` | Tùy chọn; mặc định mảng rỗng | Hint giới hạn keyspace theo những document key nhất định |

**Lưu ý:** Bảng là mô tả API, không phải khuyến nghị bật đồng thời tất cả tùy chọn. Với phần lớn entity, bắt đầu từ `on` đúng ngữ nghĩa và `fetchType` có chủ đích, rồi đo. Hint của optimizer chỉ nên được dùng nếu có bằng chứng.

### 8.1. `index` và `rightIndex`

Với điều kiện:

```java
@N1qlJoin(
    on = "lks.tenantId = rks.tenantId " +
         "AND lks.customerCode = rks.customerCode",
    index = "ix_orders_tenant_status_created",
    rightIndex = "ix_customers_tenant_code"
)
private Customer customer;
```

ví dụ trên minh họa khả năng khai báo hint index. Nó **chỉ hợp lý khi**:

- Các index thật sự tồn tại và khả dụng trên đúng collection.
- Kế hoạch join của phiên bản đang chạy hỗ trợ cách hint đó.
- `EXPLAIN` chứng minh hint tạo kế hoạch tốt hơn trên dữ liệu đại diện.
- Có phương án cập nhật hint khi tên index/schema thay đổi.

Index hint không phải cách sửa điều kiện `on` sai, dữ liệu Customer trùng hoặc thiếu tenant.

### 8.2. `hashside` và edition

API có enum `HashSide` với các lựa chọn như `BUILD`, `PROBE` và `NONE`. Theo Javadoc, tùy chọn hash join liên quan yêu cầu hỗ trợ của **Couchbase Enterprise Edition** ở các phiên bản tương ứng.

Hash join không đồng nghĩa luôn nhanh hơn indexed nested-loop join; chi phí phụ thuộc số hàng ở hai phía, memory, thống kê và predicate. Không hardcode `hashside = HashSide.BUILD` chỉ vì muốn sử dụng index ít hơn. Hãy xem plan và yêu cầu edition trước.

### 8.3. `keys` không phải khóa ngoại tự động

Phần tử `keys` cho phép cung cấp **key hint** của annotation, nhưng không biến field `customerCode` thành `META(Customer).id` và không thiết lập foreign key/cascade. Nếu mô hình thực sự lưu document ID, thường nên đánh giá KV lookup hoặc SQL++ `JOIN ... ON KEYS` trực tiếp.

## 9. `@N1qlJoin` khác `@Query`, `JOIN ... ON KEYS` và mảng nhúng

### 9.1. Annotation là một mô tả ở mức entity

`@N1qlJoin` giúp khai báo rằng field `shipments` của `SalesOrder` được lấy bằng điều kiện join. Người gọi service có thể thao tác với entity và các associated entities theo cơ chế fetch của Spring Data.

Trong khi đó, một repository `@Query` là **câu truy vấn tường minh cho một method**; Java SDK/`CouchbaseTemplate` cho phép chủ động kiểm soát truy vấn và kết quả:

```sql
SELECT META(o).id AS orderId,
       o.orderNumber,
       s.trackingNumber
FROM `commerce`.`sales`.`orders` AS o
JOIN `commerce`.`sales`.`shipments` AS s
  ON o.tenantId = s.tenantId
 AND o.orderNumber = s.orderNumber
WHERE o.tenantId = "TENANT-A";
```

Nếu API cần một DTO báo cáo với các field cụ thể, việc dùng truy vấn tường minh có thể rõ hơn so với tải cả object graph.

### 9.2. Khi đã có document ID, `ON KEYS` hoặc KV có thể đơn giản hơn

Nếu `SalesOrder` lưu `customerId = "customer::TENANT-A::42"` thay vì business key, có thể truy cập bằng:

```sql
SELECT META(o).id AS orderId,
       c.displayName
FROM `commerce`.`sales`.`orders` AS o
JOIN `commerce`.`crm`.`customers` AS c
  ON KEYS o.customerId
WHERE o.tenantId = "TENANT-A";
```

Đường join theo key khác ANSI `JOIN ... ON o.customerCode = c.customerCode`: nó tìm document cụ thể theo ID. Khi chỉ đọc **một Order** và **một Customer đã có ID**, hai KV lookup do service điều phối có thể phù hợp hơn.

### 9.3. Mảng nhúng không cần `@N1qlJoin`

Nếu Order chứa `items` ngay trong JSON:

```json
{
  "orderNumber": "ORD-1001",
  "items": [
    { "lineId": "L1", "sku": "SKU-42", "quantity": 2 }
  ]
}
```

thì `List<OrderItem> items` là **object value lồng** trong cùng document. Nó được Spring Data mapping như field JSON; không cần `@N1qlJoin`. Khi cần mỗi item thành một hàng SQL++, dùng `UNNEST`; khi chỉ cần kiểm tra tồn tại item, dùng `ANY ... SATISFIES`.

| Nhu cầu | Cách biểu diễn/đọc phù hợp |
| --- | --- |
| Address nhỏ gắn với Order | Object nhúng; không `@N1qlJoin` |
| Nhiều Shipment ở collection riêng, ghép bằng field | `@N1qlJoin` hoặc SQL++ ANSI JOIN |
| Một Customer có document ID đã biết | KV / `JOIN ... ON KEYS` |
| Tập Order cần DTO báo cáo tùy biến | `@Query`, `CouchbaseTemplate` hoặc SDK |
| Hàng trăm nghìn Event cần phân trang | Query riêng trên Event collection với index/limit |

## 10. Thiết kế chỉ mục cho liên kết theo trường dữ liệu

### 10.1. Index trên collection bên trái

Nếu một endpoint lọc Order theo tenant/status và sắp xếp thời gian:

```sql
CREATE INDEX ix_orders_tenant_status_created
ON `commerce`.`sales`.`orders`(
    `tenantId`,
    `status`,
    `createdAt` DESC
);
```

Index này hỗ trợ tìm **Order đầu vào** cho quá trình tải association theo một mẫu truy vấn cụ thể. Nó không tự giúp Query Service tìm Customer theo `customerCode` hoặc Shipment theo `orderNumber`.

### 10.2. Index trên collection bên phải cho Customer

```sql
CREATE INDEX ix_customers_tenant_code
ON `commerce`.`crm`.`customers`(
    `tenantId`,
    `customerCode`
);
```

Với `on = "lks.tenantId = rks.tenantId AND lks.customerCode = rks.customerCode"`, index này là ứng viên cho **phía Customer** khi optimizer chọn chiến lược dựa vào index.

Index thường **không phải unique constraint**. Nếu tồn tại hai Customer cùng cặp `(tenantId, customerCode)`, nhiều match vẫn có thể xảy ra dù index đã hoạt động chính xác.

### 10.3. Index trên collection bên phải cho Shipment

```sql
CREATE INDEX ix_shipments_tenant_order
ON `commerce`.`sales`.`shipments`(
    `tenantId`,
    `orderNumber`
);
```

Đây là ứng viên cho association `List<Shipment>` theo cặp tenant/orderNumber. Nếu service có endpoint phân trang Shipment theo `shippedAt`, có thể cần một index khác/được mở rộng theo workload:

```sql
CREATE INDEX ix_shipments_tenant_order_time
ON `commerce`.`sales`.`shipments`(
    `tenantId`,
    `orderNumber`,
    `shippedAt` DESC
);
```

Không mặc định giữ **cả hai** index nếu một index có thể phục vụ đầy đủ workload với chi phí hợp lý. Mỗi index tăng dung lượng và việc duy trì khi mutation thay đổi.

### 10.4. Scope/collection là ranh giới index

`commerce.crm.customers` và `commerce.sales.shipments` là hai keyspace khác nhau. Không tồn tại “index một lần cho mọi entity liên kết”. DDL phải đặt trên **đúng collection**, và tài khoản Query Service phải có quyền tương ứng.

Kiểm tra:

```sql
SELECT name, state, index_key, condition,
       bucket_id, scope_id, keyspace_id
FROM system:indexes
WHERE bucket_id = "commerce"
  AND (
      (scope_id = "crm" AND keyspace_id = "customers")
      OR
      (scope_id = "sales" AND keyspace_id = "shipments")
      OR
      (scope_id = "sales" AND keyspace_id = "orders")
  );
```

Đợi index khả dụng (thường `online` theo catalog) trước khi bật một endpoint phụ thuộc. Một `CREATE INDEX` được chấp nhận không bảo đảm index đã build xong hoặc optimizer sẽ chọn nó.

## 11. `EXPLAIN`: xác minh SQL++ thực và join plan

### 11.1. Dùng query tương đương về điều kiện

Ví dụ:

```sql
EXPLAIN
SELECT META(o).id AS orderId,
       o.orderNumber,
       c.displayName
FROM `commerce`.`sales`.`orders` AS o
JOIN `commerce`.`crm`.`customers` AS c
  ON o.tenantId = c.tenantId
 AND o.customerCode = c.customerCode
WHERE o.tenantId = "TENANT-A"
  AND o.status = "PAID"
LIMIT 20;
```

Đọc plan để hỏi:

| Dấu hiệu | Câu hỏi |
| --- | --- |
| `IndexScan`/`IndexScan3` trên Orders | Có lọc đúng tenant/status trước join không? |
| `spans` | Hai equality được áp dụng vào dải index hay còn lọc muộn? |
| Đường truy cập Customers | Có index phù hợp với tenant/customerCode không? |
| Operator join | Số hàng vào/ra bao nhiêu; có hash/nested-loop không? |
| `Fetch` | Phải đọc toàn Customer/Order vì projection hoặc predicate nào? |
| `Filter` | Điều kiện nào xử lý sau scan/join? |
| `Order`/`Limit` | Giới hạn đang áp trên hàng Order hay sau fan-out? |

Các tên operator và cấu trúc JSON plan khác nhau theo phiên bản Couchbase. **`EXPLAIN` là kế hoạch dự kiến**, không phải thống kê thời gian cho mọi lần thực thi.

### 11.2. Câu SQL++ viết tay chưa đủ để xác nhận annotation

Đặc biệt với `@N1qlJoin`:

1. Tải entity qua **đường thực tế**: KV `findById`, repository derived query hay `@Query`.
2. Quan sát câu SQL++ và số query phát sinh khi association được tải.
3. Ghi giá trị bind, keyspace, projection, discriminator `_class`, điều kiện `where` và hints.
4. Chạy `EXPLAIN` trên statement thực hoặc tương đương về ngữ nghĩa.
5. Dùng Query Profile để xác định số entry scan, số document fetch, thời gian join và số hàng kết quả.

Không kết luận `LAZY` “nhanh” vì query gốc chỉ đọc Order; cần đo cả thời gian khi code thực sự truy cập field. Không kết luận `IMMEDIATE` “luôn tệ” nếu một màn hình chi tiết nhỏ thường xuyên cần đủ association.

### 11.3. Lỗi do `_class` và partial index

Spring Data Couchbase có thể thêm predicate phân biệt loại document, tùy đường truy cập/mapping. Nếu một partial index yêu cầu:

```sql
WHERE `_class` = "customer"
```

thì phải kiểm tra giá trị `_class` thực được ghi và predicate của SQL++ do framework sinh ra. `@TypeAlias("customer")` là một cách gắn alias, nhưng dữ liệu legacy có thể chứa tên class đầy đủ hoặc loại khác. Đừng giả định index được dùng chỉ vì annotation Java khớp tên trên giấy.

## 12. Tính đúng: cardinality, dữ liệu thiếu và thay đổi khóa liên kết

### 12.1. Một field Customer nhưng nhiều bản ghi khớp

Entity:

```java
@N1qlJoin(
    on = "lks.tenantId = rks.tenantId " +
         "AND lks.customerCode = rks.customerCode"
)
private Customer customer;
```

thể hiện kỳ vọng **một Customer**, nhưng nếu ở collection Customers có hai document cùng tenant/code thì dữ liệu không còn đáp ứng kỳ vọng. Framework không tự áp đặt uniqueness cho business key này. Kết quả materialization trong trường hợp nhiều match là điều phải kiểm thử theo phiên bản; không trông chờ hệ thống chọn bản ghi đúng.

Cơ chế thiết kế tốt hơn có thể là document ID xác định từ business key chuẩn hóa và **KV insert-if-absent**, hoặc một cơ chế quản lý uniqueness phù hợp trên tất cả writer.

### 12.2. Một Order có 2 Shipment sẽ có 2 associated entities

`List<Shipment>` phù hợp với quan hệ 1:N; tuy nhiên, nếu màn hình list chỉ cần `shipmentCount`, tải toàn bộ Shipment để đếm có thể rất tốn kém. Hãy cân nhắc:

- Query aggregate `COUNT(...)` trên collection Shipment theo cặp tenant/orderNumber.
- Lưu `shipmentCount` như một read model nhỏ và có chính sách đồng bộ.
- Không lấy hết hàng nghìn Shipment chỉ để trả một số.

Giữ một collection con riêng cũng cho phép phân trang mà một association list nguyên vẹn khó đáp ứng.

### 12.3. Customer không tồn tại

Sau khi xóa Customer, Order vẫn giữ `customerCode`. `@N1qlJoin` không tự xóa `customerCode` hoặc tạo Customer placeholder.

Với màn hình lịch sử:

```json
{
  "orderNumber": "ORD-1001",
  "customerNameAtPurchase": "Nguyen An"
}
```

một snapshot trong Order có thể giúp bảo tồn tên tại thời điểm giao dịch. Trường snapshot khác bản sao hiển thị tên hiện hành: không tự đồng bộ ngược khi Customer đổi tên, trừ khi nghiệp vụ yêu cầu thay đổi có kiểm soát.

### 12.4. Thay đổi business key làm đứt quan hệ

Nếu Customer đổi `customerCode` từ `C-42` sang `C-99` nhưng Order vẫn chứa `C-42`, điều kiện `on` không còn khớp. Không có cascade update tự động chỉ vì annotation Java tồn tại.

Cần chính sách:

- Business key bất biến sau khi cấp, hoặc
- Lưu document ID ổn định thay cho mã có thể đổi, hoặc
- Migrate các document tham chiếu theo quy trình có transaction/event/reconciliation.

Phải tính đến nhiều phiên bản ứng dụng chạy song song; không sửa `on` rồi mặc định dữ liệu cũ đã tương thích.

## 13. `NULL`, `MISSING`, soft delete và outer join

### 13.1. Chú ý field thiếu và khác kiểu

Hai record:

```json
{ "customerCode": "00042" }
```

```json
{ "customerCode": 42 }
```

không nên coi là cùng business key khi nối bằng equality theo kiểu dữ liệu. Các giá trị `NULL`/`MISSING` có thể khiến predicate không thỏa và association không được tải.

Trước khi triển khai, kiểm thử:

- Cả hai phía có field cần join.
- Chuỗi/số, chữ hoa/thường, khoảng trắng và giá trị rỗng.
- Cách xử lý document bị xóa mềm.
- Giá trị tenant từ context đáng tin cậy.
- Kết quả 0, 1 hoặc nhiều bản ghi phía phải.

### 13.2. Bẫy `where` khi cần giữ entity cha

Với SQL++ tường minh:

```sql
SELECT META(o).id AS orderId,
       s.trackingNumber
FROM `commerce`.`sales`.`orders` AS o
LEFT JOIN `commerce`.`sales`.`shipments` AS s
  ON o.tenantId = s.tenantId
 AND o.orderNumber = s.orderNumber
 AND s.deleted = FALSE
WHERE o.tenantId = "TENANT-A";
```

Order không có Shipment vẫn có thể được giữ bởi `LEFT JOIN`. Nhưng:

```sql
SELECT META(o).id AS orderId,
       s.trackingNumber
FROM `commerce`.`sales`.`orders` AS o
LEFT JOIN `commerce`.`sales`.`shipments` AS s
  ON o.tenantId = s.tenantId
 AND o.orderNumber = s.orderNumber
WHERE o.tenantId = "TENANT-A"
  AND s.deleted = FALSE;
```

có thể loại Order không có Shipment do predicate `s.deleted` nằm ở `WHERE`. Vì vậy, khi dùng tham số `where` của `@N1qlJoin`, **phải kiểm thử semantics của generated query**; không coi nó chắc chắn tương đương với việc gắn mọi filter vào `on`.

### 13.3. Lọc tenant không được đánh đổi bảo mật

Khi cần giữ Order nhưng Customer không hợp lệ, một cách an toàn về ngữ nghĩa có thể là **không trả trường Customer** và fallback snapshot. Không bỏ điều kiện tenant phía phải để “JOIN được nhiều hơn”. Nếu User không có quyền xem Customer, service cũng không nên tạo association chứa dữ liệu nhạy cảm chỉ vì field mã khách trùng.

## 14. TTL, CAS, giao dịch và scan consistency

### 14.1. TTL không tạo cascade

Nếu Customer hoặc Shipment bị xóa/hết hạn theo TTL, Order vẫn tồn tại, đồng thời `@N1qlJoin` có thể không còn tìm được entity liên quan. Điều này phải được xử lý ở hợp đồng API: trả association vắng, dùng snapshot, báo lỗi dữ liệu hay kích hoạt đối soát.

Với dữ liệu có retention khác nhau, **không tự gán cùng TTL** cho mọi document chỉ vì chúng liên kết với nhau.

### 14.2. CAS kiểm soát cạnh tranh ghi của từng document

`CAS` và annotation `@Version` trong Spring Data Couchbase được dùng để hỗ trợ optimistic locking theo mô hình được hỗ trợ. Nhưng CAS trên Order không tự bảo vệ update của Customer/Shipment, và cũng không tạo tính nguyên tử cho thay đổi nhiều document.

Nếu hai luồng cùng cập nhật mã Customer và Order, có thể cần transaction, quy trình đổi khóa có version, hoặc cách lưu document ID bất biến. `@N1qlJoin` chỉ khai báo điều kiện tải, không giải quyết xung đột ghi.

### 14.3. Giao dịch không phải tác dụng phụ của annotation

Nếu nghiệp vụ đòi tạo Order và một Shipment đầu tiên nguyên tử, phải sử dụng transaction/API phù hợp với phiên bản Couchbase được hỗ trợ hoặc thiết kế state machine cùng retry/idempotency. Khai báo:

```java
@N1qlJoin(on = "lks.orderNumber = rks.orderNumber")
private List<Shipment> shipments;
```

không khiến `orderRepository.save(order)` tự lưu mọi Shipment trong một giao dịch.

### 14.4. Độ mới của GSI khác tính nguyên tử

Global Secondary Index được cập nhật bất đồng bộ từ KV mutation. Một quan hệ vừa tạo có thể chưa xuất hiện ngay qua SQL++ dùng index với consistency không yêu cầu chờ.

| Scan consistency | Tính chất |
| --- | --- |
| `NOT_BOUNDED` | Không yêu cầu chờ index bắt kịp mutation trước query; có thể thấy dữ liệu tạm cũ |
| `REQUEST_PLUS` | Đợi index bắt kịp các mutation liên quan ở thời điểm query; có thể tăng độ trễ |

`REQUEST_PLUS` không thay thế transaction hoặc ràng buộc khóa ngoại. Đối với màn hình vừa tạo Shipment rồi lập tức cần xem Shipment, hãy xác định đường đọc/consistency phù hợp thay vì trông chờ annotation tự bảo đảm read-after-write trong mọi tình huống.

## 15. `@N1qlJoin` và đa tenant: điều kiện liên kết là một lớp, không phải toàn bộ bảo mật

Một ứng dụng có nhiều tenant thường có các mã như `C-42`, `ORD-1001` trùng nhau giữa tenant. Nếu `on` chỉ có:

```java
@N1qlJoin(on = "lks.customerCode = rks.customerCode")
private Customer customer;
```

Order của tenant A có thể match Customer tenant B. Đây vừa là **lỗi đúng dữ liệu**, vừa là rủi ro bảo mật.

Một quy tắc tốt hơn:

```java
@N1qlJoin(
    on = "lks.tenantId = rks.tenantId " +
         "AND lks.customerCode = rks.customerCode"
)
private Customer customer;
```

Nhưng vẫn cần:

1. Lấy tenant/identity từ context đã xác thực.
2. Giới hạn query Order theo tenant user được phép.
3. Kiểm soát quyền đọc Customer và Shipment ở API/service.
4. Chỉ trả field cần thiết, không expose nguyên document chứa thông tin nhạy cảm.
5. Cấu hình RBAC của Couchbase trên bucket/scope/collection liên quan.
6. Kiểm thử reference không tồn tại, sai tenant và dữ liệu legacy không có `tenantId`.

Index có khóa `tenantId` giúp truy vấn hiệu quả **nhưng không thay thế authorization**.

## 16. So sánh chiến lược tải quan hệ trong từng endpoint

| Endpoint | Giải pháp khởi đầu | Vì sao |
| --- | --- | --- |
| Chi tiết một Order luôn hiển thị một Customer | `@N1qlJoin` với `IMMEDIATE` hoặc KV lookup rõ ràng | Association nhỏ, được dùng thường xuyên |
| Danh sách 100 Order chỉ cần ID, ngày, trạng thái | Không tải association; `LAZY` hoặc DTO | Tránh tải Customer/Shipment không cần |
| Danh sách Order có tên Customer hiện hành | Query JOIN/DTO hoặc batch lookup | Kiểm soát số row, projection, N+1 |
| Trang chi tiết cần vài Shipment của một Order | `List<Shipment>` có thể phù hợp nếu cardinality nhỏ | Đơn giản nhưng cần xác nhận thứ tự và số lượng |
| Timeline 100.000 Event của một Order | Query Event riêng, index và phân trang | Không dùng list association tải toàn bộ |
| Báo cáo tổng hợp trạng thái Shipment | SQL++ aggregate hoặc read model | Không materialize tất cả entity chỉ để tính `COUNT` |
| Pipeline reactive cần non-blocking rõ ràng | Reactive repository/template/SDK query tường minh | Tránh giả định lazy getter là reactive stream |

Khi chọn, hỏi: **request có cần associated entities ngay không**, có bao nhiêu parent, mỗi parent có bao nhiêu child, có yêu cầu phân trang hay projection nhỏ, và độ mới bao nhiêu là đủ?

## 17. Quy trình thực hành và triển khai production

### 17.1. Kiểm tra schema trước annotation

Xác minh:

- `SalesOrder`, `Customer`, `Shipment` nằm trên những bucket/scope/collection nào.
- Tên field JSON thực có khớp `tenantId`, `customerCode` và `orderNumber` không.
- Spring Data converter hoặc `@Field` có đổi tên JSON field không.
- `_class`/`@TypeAlias` lưu giá trị gì và generated query có thêm predicate nào.
- Mỗi key được mong đợi match 0, 1 hay nhiều document.
- Có dữ liệu trùng key, thiếu key, sai kiểu hoặc sai tenant không.

Nếu một entity Java có field `customerCode` nhưng JSON lưu `customer_code`, **biểu thức `on` phải tương thích với key JSON thực và khả năng xử lý mapping của phiên bản**. Không cho rằng tên Java chắc chắn trùng mọi tên trong SQL++.

### 17.2. Tạo index, chờ sẵn sàng

Tạo DDL qua migration/ops được phê duyệt, không phải mỗi instance runtime tạo index trùng khi khởi động. Kiểm tra `system:indexes` cho từng collection, đợi index `online`, sau đó đo.

Không bật đường đọc phụ thuộc index mới chỉ vì lệnh `CREATE INDEX` đã được chấp nhận. Với collection lớn, build có thể tốn tài nguyên Index Service và ảnh hưởng độ trễ khi ghi/truy vấn.

### 17.3. Kiểm tra SQL++ runtime và lazy

Trên môi trường staging:

1. Gọi `findById` hoặc derived repository query tải Order.
2. Ghi số SQL++ được gửi khi chưa đọc `customer`/`shipments`.
3. Truy cập getter liên quan, ghi số query mới và latency.
4. So sánh `IMMEDIATE` với `LAZY` trong cùng workload.
5. Với trang 50 Order, thử serializer thực để phát hiện lazy fetch bất ngờ.
6. Chạy `EXPLAIN` và Query Profile cho từng SQL++ liên quan.
7. Kiểm thử Customer không có match, Shipment 0/1/nhiều, tenant khác, duplicate và soft delete.

### 17.4. Canary và rollback

Nếu thêm `@N1qlJoin` vào một entity được trả bởi nhiều endpoint, đây là thay đổi có thể làm biến động **hành vi tải dữ liệu** của toàn bộ API chứ không chỉ một method. Trong production:

- Bật theo một nhóm nhỏ hoặc một đường đọc mới trước.
- Theo dõi Query/Index Service, p95/p99, kích thước response và số query trên request.
- Giữ phương án DTO/lookup cũ để rollback nhanh.
- Chỉ thu hồi index cũ khi tất cả query/job liên quan đã được rà soát.

Không coi việc ứng dụng khởi động thành công là bằng chứng annotation join đúng trên dữ liệu production.

## 18. Bảng chẩn đoán lỗi thường gặp

| Triệu chứng | Khả năng nguyên nhân | Hướng kiểm tra |
| --- | --- | --- |
| Association luôn rỗng | `on` sai field JSON, sai alias `lks/rks`, không khớp dữ liệu | Kiểm tra document JSON, SQL++ thực, `NULL`/`MISSING` |
| Customer tenant B xuất hiện trên Order tenant A | Bỏ `tenantId` khỏi join criteria | Thêm điều kiện tenant, test authorization |
| Một Customer field nhưng nhiều record match | Business key không duy nhất | Quy tắc ID/uniqueness, đối soát dữ liệu |
| Query chậm ngay khi tải danh sách Order | `IMMEDIATE` tải nhiều association không cần | DTO hoặc `LAZY`, đếm query và profiling |
| Query chậm khi serialize JSON | Getter kích hoạt lazy fetch N lần | DTO, tránh expose entity, kiểm soát việc tải |
| `LAZY` vẫn gây timeout | N+1 hoặc một association chứa quá nhiều child | Query phân trang/batch, giới hạn fan-out |
| `where` làm mất association/parent ngoài dự kiến | Semantics predicate khác `on`, field thiếu | Xem generated SQL++, test outer join |
| Spring Data trả thiếu field/không map | Projection, `_class`, alias hoặc kiểu association không khớp | Kiểm tra mapping và version |
| Index tồn tại nhưng plan không dùng | Keyspace sai, index chưa online, join không chọn lọc | `system:indexes`, `EXPLAIN`, Query Profile |
| Index hint làm query lỗi sau deploy | Tên index đổi hoặc edition/strategy không tương thích | Bỏ/điều chỉnh hint theo plan và migration |
| Customer đổi code, Order không join được | Business key thay đổi một phía | ID ổn định, migration hoặc đồng bộ |
| Xóa Customer, Order còn field code | Không có FK/cascade tự động | Fallback snapshot, cleanup/retention |
| Vừa thêm Shipment nhưng list chưa thấy | GSI chưa bắt kịp mutation | Đánh giá `REQUEST_PLUS` hoặc KV theo ID |
| `@Version` trên Order không ngăn trùng Customer | CAS chỉ liên quan document đang ghi | Quản lý uniqueness và transaction riêng |
| Reactive chain có blocking bất ngờ | Truy cập lazy getter như thao tác sync | Dùng reactive query explicit, đo thread/I/O |

## 19. Bài thực hành: khai báo và đo liên kết entity

**Môi trường:** Spring Data Couchbase phiên bản có `@N1qlJoin` và Couchbase Server hỗ trợ ANSI JOIN, bucket/scope/collection đã được cấp quyền. Các câu DDL chỉ chạy trong lab hoặc môi trường được phép.

### Bài A — Liên kết Order với Customer

1. Tạo hai document Customer trong hai tenant đều có `customerCode = "C-42"`, và một Order của tenant A.
2. Trong `SalesOrder`, khai báo:

```java
@N1qlJoin(
    on = "lks.tenantId = rks.tenantId " +
         "AND lks.customerCode = rks.customerCode"
)
private Customer customer;
```

3. Tải Order, đọc `customer`, xác minh Customer thuộc tenant A.
4. Thử tạm bỏ điều kiện tenant trong lab để giải thích nguy cơ ghép sai.
5. Xóa Customer tenant A trong lab, kiểm tra hành vi khi association không có match và quyết định fallback.

### Bài B — Liên kết Order với nhiều Shipment

1. Tạo Order `ORD-1001` và hai Shipment cùng tenant/orderNumber.
2. Khai báo:

```java
@N1qlJoin(
    on = "lks.tenantId = rks.tenantId " +
         "AND lks.orderNumber = rks.orderNumber",
    fetchType = FetchType.LAZY
)
private List<Shipment> shipments;
```

3. Tải Order nhưng chưa gọi getter `shipments`; ghi số query.
4. Gọi `getShipments()` lần đầu rồi lần tiếp theo; ghi số query và so sánh.
5. Tạo 50 Order, mỗi Order có 1–5 Shipment, rồi truy cập list của tất cả Order. Đếm query/fetch thực tế và tìm dấu hiệu N+1.
6. Khi tăng lên 1.000 Shipment cho một Order, đề xuất API query phân trang thay cho một list tải hết.

### Bài C — `on` so với `where`

Thêm field `deleted` vào Shipment ở lab và dùng:

```java
@N1qlJoin(
    on = "lks.tenantId = rks.tenantId " +
         "AND lks.orderNumber = rks.orderNumber",
    where = "rks.deleted = FALSE"
)
private List<Shipment> activeShipments;
```

Thử một Order có ba Shipment: một `deleted = FALSE`, một `TRUE`, một thiếu field `deleted`. Đối chiếu kết quả, SQL++ runtime và cách query xử lý `MISSING`. So sánh với câu SQL++ `LEFT JOIN` đặt `rks.deleted = FALSE` trong `ON`, rồi trong `WHERE` để nhận biết sự khác nhau.

### Bài D — Tạo index và xem `EXPLAIN`

```sql
CREATE INDEX ix_lab_customers_tenant_code
ON `commerce`.`crm`.`customers`(
    `tenantId`, `customerCode`
);

CREATE INDEX ix_lab_shipments_tenant_order
ON `commerce`.`sales`.`shipments`(
    `tenantId`, `orderNumber`
);
```

Chờ index sẵn sàng, kiểm tra:

```sql
SELECT name, state, index_key, condition,
       bucket_id, scope_id, keyspace_id
FROM system:indexes
WHERE bucket_id = "commerce"
  AND (
      (scope_id = "crm" AND keyspace_id = "customers")
      OR
      (scope_id = "sales" AND keyspace_id = "shipments")
  );
```

Lấy SQL++ thực khi tải relation, chạy `EXPLAIN`. Ghi index của mỗi phía, `spans`, `Fetch`, toán tử join, thời gian thực và số hàng. Không tự khẳng định optimizer dùng index mới chỉ vì nó `online`.

### Bài E — So sánh ba chiến lược tải

Triển khai ba phương án cho cùng màn hình Order:

- **Phương án 1:** `@N1qlJoin` với `IMMEDIATE`.
- **Phương án 2:** `@N1qlJoin` với `LAZY`, chỉ tải khi người dùng mở chi tiết.
- **Phương án 3:** DTO Order nhẹ, dùng truy vấn/lookup tường minh khi cần Customer hoặc Shipment.

Giữ cùng dataset, concurrency và tập field trả về, đo:

| Phương án | Query/round trip mỗi request | p95 latency | Documents fetched | Response bytes | Ghi chú |
| --- | --- | --- | --- | --- | --- |
| IMMEDIATE | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Association có luôn cần? |
| LAZY, không truy cập getter | Chưa đo | Chưa đo | Chưa đo | Chưa đo | List nhẹ |
| LAZY, truy cập trên N Order | Chưa đo | Chưa đo | Chưa đo | Chưa đo | N+1? |
| DTO + truy vấn chủ động | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Projection/limit rõ |

“Chưa đo” là các ô người học phải điền sau thực nghiệm, **không phải số liệu một cluster đã chạy**.

### Câu hỏi tự kiểm tra

1. `@N1qlJoin` thuộc package nào và đặt trên thành phần Java nào?
2. Vì sao `lks` và `rks` không được thay tùy tiện bằng alias từ một câu SQL++ viết tay?
3. Vì sao điều kiện `lks.customerCode = rks.customerCode` có thể sai trong hệ thống multi-tenant?
4. Field `Customer customer` và `List<Shipment> shipments` thể hiện hai loại cardinality khác nhau thế nào?
5. `@N1qlJoin` có tạo foreign key, unique constraint hoặc cascade delete không?
6. `fetchType = IMMEDIATE` khác `LAZY` thế nào? Vì sao LAZY vẫn có thể phát sinh N+1?
7. Tại sao việc serialize nguyên entity có thể làm endpoint chậm dù repository query gốc nhanh?
8. `on` và `where` có thể khác nhau thế nào trong trường hợp cần giữ parent khi không có match?
9. Vì sao một index trên Customer theo `(tenantId,customerCode)` không tự bảo đảm uniqueness?
10. `index` và `rightIndex` dùng cho phía nào? Khi nào không nên ép hint?
11. `hashside` cần lưu ý gì về edition và chi phí?
12. Vì sao một Order có 50.000 Shipment không nên tải mặc định toàn bộ `List<Shipment>`?
13. Khi Customer đổi mã nghiệp vụ, quan hệ dùng `on` theo mã có thể xảy ra chuyện gì?
14. `@Version`/CAS, transaction và scan consistency giải quyết những vấn đề gì khác nhau?
15. Với đường reactive, vì sao không nên coi getter LAZY là một `Flux` non-blocking?
16. Nêu ba điều phải kiểm chứng bằng SQL++ runtime và `EXPLAIN` trước khi đưa annotation join vào production.

## 20. Tài liệu tham khảo và cách xác minh phiên bản

Các API chính được mô tả trong tài liệu của dự án Spring:

- [Spring Data Couchbase — ANSI Joins](https://docs.spring.io/spring-data/couchbase/reference/couchbase/ansijoins.html): cấu hình `@N1qlJoin`, alias `lks`/`rks`, eager/lazy fetching và index/hash/key hints.
- [Javadoc `N1qlJoin`](https://docs.spring.io/spring-data/couchbase/reference/api/java/org/springframework/data/couchbase/core/query/N1qlJoin.html): các phần tử `on`, `where`, `fetchType`, `index`, `rightIndex`, `hashside`, `keys` và mặc định.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): phân biệt thao tác KV theo ID và truy vấn SQL++ theo thuộc tính, cùng yêu cầu về chỉ mục.

Khi làm dự án thật, hãy mở đúng phiên bản tài liệu với version Spring Data Couchbase được dependency management khai báo. Không tự sao chép ví dụ của một phiên bản mới sang bản cũ mà chưa xác minh package, annotation elements, scope/collection mapping và kiểu truy vấn phát sinh.

## 21. Kết luận

`@N1qlJoin` giúp diễn đạt **điều kiện liên kết entity qua ANSI JOIN** ngay trên field trong Spring Data Couchbase. `on` với `lks`/`rks` chỉ ra những document nào tương ứng; `where` thêm điều kiện lọc; `fetchType` quyết định khi nào association được tải; các hint chỉ mục/hash/key phục vụ chẩn đoán và tối ưu trong cấu hình được hỗ trợ.

Để áp dụng an toàn, cần bảo đảm **business key đúng và đủ điều kiện tenant**, xác định cardinality 1:1 hay 1:N, xử lý document thiếu/trùng, không kỳ vọng cascade/transaction tự động, và đo chi phí thực khi load nhiều entity. Với tập liên quan lớn, DTO hoặc SQL++ tường minh có phân trang thường dễ kiểm soát hơn tải nguyên object graph. Kết hợp `EXPLAIN`, Query Profile, index trên đúng collection, CAS, TTL và scan consistency sẽ giúp việc khai báo quan hệ **đúng ngữ nghĩa, đủ hiệu năng và có thể vận hành lâu dài**.
