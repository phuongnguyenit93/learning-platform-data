# Xây BulkOperations với insert, update, upsert, replace và remove

> **Chương:** Ghi hàng loạt  
> **Module:** `SPRING_DATA_MONGODB`

Khi một dịch vụ cần nhập vài nghìn đơn hàng, đồng bộ trạng thái từ hệ thống đối tác hoặc dọn những bản ghi quá hạn, việc lặp `repository.save(...)` hoặc `MongoTemplate.updateFirst(...)` trong một vòng `for` có thể tạo nhiều lệnh ghi riêng lẻ và tăng chi phí đi lại giữa ứng dụng với MongoDB. Spring Data MongoDB cung cấp **`BulkOperations`** để gom một chuỗi thao tác **insert, update, upsert, replace và remove** rồi thực thi thông qua `MongoTemplate`.

Bulk write giúp giảm overhead gửi lệnh và tổ chức một đợt ghi rõ ràng. Tuy vậy, **bulk không đồng nghĩa “tất cả thành công hoặc không có gì thay đổi”**. Hành vi lỗi phụ thuộc vào chế độ `ORDERED`/`UNORDERED`, kết quả thao tác, ràng buộc unique index và việc có sử dụng transaction hay không. Đặc biệt, `BulkOperations` không cung cấp cùng cách xử lý từng entity như một vòng `save`: không nên giả định auditing callbacks hoặc optimistic locking với `@Version` được tự động áp dụng.

Bài nằm trong module `SPRING_DATA_MONGODB`: kết nối và ánh xạ document, truy vấn và ghi dữ liệu qua repository hoặc `MongoTemplate`, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng. Trọng tâm ở đây là **xây và vận hành một bulk write đúng ngữ nghĩa**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Tạo `BulkOperations` bằng `MongoTemplate.bulkOps(...)`, chọn `BulkMode.ORDERED` hoặc `UNORDERED`.
2. Dùng đúng các thao tác `insert`, `updateOne`, `updateMulti`, `upsert`, `replaceOne` và `remove`.
3. Phân biệt **cập nhật một phần** bằng `$set` với **thay thế document** bằng replacement.
4. Đọc `BulkWriteResult`, hiểu matched/modified/upserted/inserted/deleted và xử lý **thành công một phần**.
5. Thiết kế bulk có giới hạn tenant, unique index, idempotency, kiểm soát phiên bản và batch size phù hợp.
6. Viết kiểm thử tích hợp xác nhận BSON sau ghi, kết quả thống kê, lỗi duplicate key và tính bảo toàn dữ liệu.

## 2. BulkOperations nằm ở đâu trong Spring Data MongoDB?

Sơ đồ luồng xử lý:

```text
Application Service
       |
       |  xây các thao tác:
       |  insert / updateOne / updateMulti / upsert
       |  replaceOne / remove
       v
MongoTemplate.bulkOps(BulkMode, Entity.class)
       |
       |  BulkOperations (tích lũy thao tác, chưa ghi)
       |
       +-- .insert(...)
       +-- .updateOne(...)
       +-- .updateMulti(...)
       +-- .upsert(...)
       +-- .replaceOne(...)
       +-- .remove(...)
       |
       v
    .execute()
       |
       v
MongoDB Java Driver -> MongoDB Server
       |
       +-- Thành công: BulkWriteResult
       |
       +-- Thất bại: exception; có thể đã ghi được
           một phần trước hoặc song song với lỗi
```

**`insert/updateOne/upsert/...` khi gọi trên `BulkOperations` là bước đăng ký operation**, không phải thao tác ghi tức thời. Các lệnh được gửi khi gọi **`execute()`**. Điều này khác với `MongoTemplate.insert(...)` hay `repository.save(...)`, vốn là lời gọi thực thi ngay.

### 2.1. Những thao tác chính

| BulkOperations API | Tương ứng ý tưởng MongoDB | Ảnh hưởng |
| --- | --- | --- |
| `insert(entity)` | Insert document | Thêm document mới, lỗi nếu trùng khóa unique |
| `insert(list)` | Nhiều insert | Thêm nhiều document |
| `updateOne(query, update)` | Update một document khớp | Chỉ sửa field do update operator chỉ định |
| `updateMulti(query, update)` | Update mọi document khớp | Cập nhật hàng loạt trong phạm vi query |
| `upsert(query, update)` | Update hoặc insert khi không khớp | Có thể tạo document mới |
| `replaceOne(query, replacement)` | Replace một document | Ghi representation mới, có thể làm mất field cũ không được đưa vào |
| `remove(query)` | Xóa document khớp query theo bulk remove | Xóa dữ liệu, cần filter chặt và xác minh ý nghĩa overload |
| `execute()` | Gửi các bulk write models | Trả tổng kết kết quả hoặc ném exception |

Trong ví dụ, để tránh xóa ngoài ý muốn, thao tác `remove` sẽ luôn có `_id`/**tenantId** cụ thể. Dù một API xóa áp dụng được cho nhiều document, cách đó giữ tối đa một đích ở mức filter nghiệp vụ.

### 2.2. Khi nào dùng BulkOperations?

Bulk phù hợp khi:

- Nhập hoặc đồng bộ nhiều entity vào cùng collection trong một đợt.
- Cập nhật nhiều document theo các điều kiện độc lập và đã được kiểm tra.
- Thực hiện migration/correction có checkpoint và thống kê kết quả.
- Cần xử lý kết hợp insert, update, upsert, replace hoặc remove trong một tác vụ có tổ chức.

Không nhất thiết dùng bulk cho một lệnh update duy nhất hoặc một thao tác nghiệp vụ cần kết quả của từng entity ngay lập tức. Khi cần callbacks, auditing hoặc bảo vệ `@Version` như `repository.save(...)`, phải phân tích lại lựa chọn bulk trước khi triển khai.

## 3. Chọn ORDERED hay UNORDERED

Spring Data dùng `BulkOperations.BulkMode` với hai lựa chọn.

| Đặc điểm | `ORDERED` | `UNORDERED` |
| --- | --- | --- |
| Thứ tự thực thi | Giữ thứ tự logic của danh sách thao tác | Driver/server được phép sắp xếp/tối ưu khác thứ tự |
| Khi một thao tác lỗi | Dừng các thao tác phía sau trong cùng bulk theo quy tắc ordered | Có thể tiếp tục những thao tác khác |
| Phù hợp | Thao tác sau phụ thuộc kết quả thao tác trước | Các thao tác độc lập, ưu tiên throughput |
| Có atomic toàn batch? | **Không**, nếu không có transaction bao ngoài | **Không** |
| Có đảm bảo một document không bị hai thao tác đua nhau? | Có thứ tự trong bulk, nhưng writer bên ngoài vẫn có thể cạnh tranh | Không nên có nhiều operation cùng sửa một document nếu thứ tự quan trọng |

### 3.1. Ví dụ lỗi duplicate key

Một bulk ordered gồm:

```text
1. insert O-200     -> thành công
2. insert O-101     -> lỗi duplicate _id
3. update O-102     -> không được thực hiện sau lỗi ordered
```

Không có transaction, **insert O-200 vẫn có thể đã được commit** khi exception xảy ra. Với unordered, thao tác số 3 có thể vẫn được thực hiện. Đó là lý do không thể kiểm tra kiểu “có exception thì chắc chắn chưa ghi gì”.

### 3.2. Chọn mode cho bài thực hành

Ta chọn **`ORDERED`** cho ví dụ một batch hỗn hợp để dễ theo dõi diễn tiến. Trong hệ thống import độc lập, `UNORDERED` có thể phù hợp, nhưng phải tránh để hai thao tác phụ thuộc thứ tự cập nhật cùng một document hoặc cùng một business key.

```java
import org.springframework.data.mongodb.core.BulkOperations;

BulkOperations bulk = mongoTemplate.bulkOps(
    BulkOperations.BulkMode.ORDERED,
    OrderDocument.class
);
```

`mongoTemplate` là bean `MongoTemplate` đã được inject. Dùng `OrderDocument.class` giúp Spring Data áp metadata mapping cho entity, tên field và các custom conversions phù hợp; không biến bulk thành một vòng `save` đầy đủ.

## 4. Mô hình thực hành

Ta xây một luồng đồng bộ đơn hàng từ đối tác:

- Chèn một đơn mới.
- Đổi trạng thái một đơn.
- Đổi trạng thái nhiều đơn đang chờ xử lý.
- Tạo hoặc cập nhật đơn theo khóa từ hệ thống đối tác.
- Thay toàn bộ dữ liệu của một đơn khi có **replacement snapshot** được phê duyệt.
- Xóa một bản ghi thử nghiệm/đã được xác minh quyền xóa.

File `OrderDocument.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id String id,
    String tenantId,
    String externalRef,
    String status,
    long amountMinor,
    Instant updatedAt
) {}
```

Ở ví dụ này, `_id` là BSON String như `"ORD-101"`, không phải chuỗi ObjectId 24 ký tự hex. Các mã `tenantId` và `externalRef` phải được xác thực theo nghiệp vụ, không coi chuỗi do client gửi là bằng chứng về quyền truy cập.

### 4.1. Dữ liệu ban đầu (chỉ chạy trên database test)

```javascript
use shop

db.orders.insertMany([
  {
    _id: "ORD-101",
    tenantId: "TENANT-A",
    externalRef: "EXT-101",
    status: "NEW",
    amountMinor: NumberLong(200000),
    updatedAt: ISODate("2026-11-19T01:00:00Z")
  },
  {
    _id: "ORD-102",
    tenantId: "TENANT-A",
    externalRef: "EXT-102",
    status: "NEW",
    amountMinor: NumberLong(300000),
    updatedAt: ISODate("2026-11-19T01:30:00Z"),
    legacy_note: "Giữ nếu không thay document"
  },
  {
    _id: "ORD-103",
    tenantId: "TENANT-A",
    externalRef: "EXT-103",
    status: "TEST_ONLY",
    amountMinor: NumberLong(0),
    updatedAt: ISODate("2026-11-19T02:00:00Z")
  },
  {
    _id: "ORD-104",
    tenantId: "TENANT-A",
    externalRef: "EXT-104",
    status: "WAITING_RETRY",
    amountMinor: NumberLong(100000),
    updatedAt: ISODate("2026-11-19T02:30:00Z")
  },
  {
    _id: "ORD-105",
    tenantId: "TENANT-A",
    externalRef: "EXT-105",
    status: "WAITING_RETRY",
    amountMinor: NumberLong(150000),
    updatedAt: ISODate("2026-11-19T03:00:00Z")
  },
  {
    _id: "ORD-B01",
    tenantId: "TENANT-B",
    externalRef: "EXT-101",
    status: "NEW",
    amountMinor: NumberLong(999999),
    updatedAt: ISODate("2026-11-19T04:00:00Z")
  }
])
```

Tenant B cố ý dùng cùng `externalRef = "EXT-101"` với tenant A để kiểm tra rằng filter phải chứa **tenantId**. Bộ dữ liệu không chứa `ORD-200` hay `EXT-201` trước khi thực thi bulk.

### 4.2. Index cần cho upsert theo business key

Trong luồng đối tác, `externalRef` là mã duy nhất **trong phạm vi tenant**, không duy nhất toàn collection:

```javascript
db.orders.createIndex(
  { tenantId: 1, externalRef: 1 },
  { unique: true, name: "uq_tenant_external_ref" }
)
```

Unique index giúp ngăn hai writer tạo hai đơn có cùng cặp `(tenantId, externalRef)`. Phải kiểm tra dữ liệu đang tồn tại trước khi tạo index; nếu có duplicate, MongoDB có thể không tạo được index. Khi field có thể missing/null, cần thiết kế schema/index (ví dụ partial index) theo quy tắc nghiệp vụ, không áp lệnh một cách mù quáng.

## 5. Xây bulk hỗn hợp với đủ năm nhóm thao tác

File `OrderBulkService.java`:

```java
package com.example.shop.orders;

import com.mongodb.bulk.BulkWriteResult;
import java.time.Instant;
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class OrderBulkService {

    private final MongoTemplate template;

    public OrderBulkService(MongoTemplate template) {
        this.template = template;
    }

    public BulkWriteResult executeExample() {
        String tenant = "TENANT-A";
        Instant now = Instant.parse("2026-11-20T02:00:00Z");

        BulkOperations bulk = template.bulkOps(
            BulkOperations.BulkMode.ORDERED,
            OrderDocument.class);

        // (1) INSERT: thêm document có ID mới.
        bulk.insert(new OrderDocument(
            "ORD-200", tenant, "EXT-200",
            "NEW", 250000L, now));

        // (2) UPDATE ONE: chỉ đổi field cần thiết.
        bulk.updateOne(
            Query.query(Criteria.where("id").is("ORD-101")
                .and("tenantId").is(tenant)),
            new Update()
                .set("status", "PAID")
                .set("updatedAt", now));

        // (3) UPDATE MULTI: sửa mọi document còn chờ thử lại.
        bulk.updateMulti(
            Query.query(Criteria.where("tenantId").is(tenant)
                .and("status").is("WAITING_RETRY")),
            new Update()
                .set("status", "QUEUED")
                .set("updatedAt", now));

        // (4) UPSERT: tra cứu theo khóa nghiệp vụ trong tenant.
        bulk.upsert(
            Query.query(Criteria.where("tenantId").is(tenant)
                .and("externalRef").is("EXT-201")),
            new Update()
                .setOnInsert("tenantId", tenant)
                .setOnInsert("externalRef", "EXT-201")
                .set("status", "NEW")
                .set("amountMinor", 450000L)
                .set("updatedAt", now));

        // (5) REPLACE: thay toàn bộ representation của ORD-102.
        bulk.replaceOne(
            Query.query(Criteria.where("id").is("ORD-102")
                .and("tenantId").is(tenant)),
            new OrderDocument(
                "ORD-102", tenant, "EXT-102",
                "PAID", 300000L, now));

        // (6) REMOVE: chỉ xóa đúng bản ghi test đã được chỉ định.
        bulk.remove(
            Query.query(Criteria.where("id").is("ORD-103")
                .and("tenantId").is(tenant)
                .and("status").is("TEST_ONLY")));

        // Chỉ tại đây các thao tác mới được gửi để thực thi.
        return bulk.execute();
    }
}
```

Ở đây có **sáu lời gọi đăng ký**, nhưng năm nhóm chức năng cần học là `insert`, `update` (một/nhiều), `upsert`, `replace` và `remove`. Mã được trình bày dưới dạng ví dụ có dữ liệu và thời gian cố định; production phải nhận thao tác đầu vào đã được xác thực, có batch ID, checkpoint và không dùng `executeExample()` như một endpoint công khai.

Khi `execute()` thành công, nó trả `BulkWriteResult` tổng hợp. Ví dụ này dùng `ORDERED` nên `updateOne` chạy trước `updateMulti`; các filter được chọn không trùng nhau ngoài phạm vi cố ý. Với `UNORDERED`, không nên dùng những thao tác phụ thuộc kết quả ghi trước để dựng logic nghiệp vụ.

## 6. Insert: thêm mới, không tự thay thế bản ghi trùng ID

```java
BulkOperations bulk = template.bulkOps(
    BulkOperations.BulkMode.ORDERED,
    OrderDocument.class);

bulk.insert(new OrderDocument(
    "ORD-300", "TENANT-A", "EXT-300",
    "NEW", 100000L,
    Instant.parse("2026-11-20T03:00:00Z")));

BulkWriteResult result = bulk.execute();
```

`insert` tạo document mới. Nếu `_id` đã tồn tại, unique index `_id` chặn ghi trùng; bulk có thể ném lỗi thay vì “chuyển thành update”. Nếu muốn **khớp thì cập nhật, chưa có thì thêm**, sử dụng `upsert` với điều kiện và unique index phù hợp, không trộn lẫn ngữ nghĩa insert và upsert.

### 6.1. Insert nhiều entity

```java
BulkOperations bulk = template.bulkOps(
    BulkOperations.BulkMode.UNORDERED,
    OrderDocument.class);

bulk.insert(java.util.List.of(
    new OrderDocument(
        "ORD-301", "TENANT-A", "EXT-301",
        "NEW", 130000L, Instant.parse("2026-11-20T03:00:00Z")),
    new OrderDocument(
        "ORD-302", "TENANT-A", "EXT-302",
        "NEW", 180000L, Instant.parse("2026-11-20T03:00:00Z"))
));

BulkWriteResult result = bulk.execute();
```

Với `UNORDERED`, hai insert là độc lập, nên driver/server có quyền tối ưu thứ tự. Nếu một insert lỗi duplicate key, các insert khác vẫn có thể thành công. Không nên dựa vào việc “lỗi thì chưa thêm bản ghi nào”.

### 6.2. Định danh và mapping

Entity dùng `@Id`; Spring Data thực hiện mapping sang BSON `_id`. Nếu ứng dụng dùng ID kiểu String có dạng 24 ký tự hex, hãy kiểm tra khả năng chuyển sang ObjectId theo quy tắc `@Id`. Khi cần ID BSON String một cách bắt buộc, xem xét `@MongoId` với cấu hình kiểu rõ ràng.

Không giả định mọi entity được bulk insert đều đi qua toàn bộ lifecycle callback hoặc auditing của `save`. Nếu dữ liệu cần `createdAt`, `updatedBy` hay version, chuẩn bị các field đó theo hợp đồng ghi bulk của hệ thống.

## 7. UpdateOne và UpdateMulti: ghi theo toán tử

### 7.1. UpdateOne: chỉ document đầu tiên khớp

```java
bulk.updateOne(
    Query.query(Criteria.where("id").is("ORD-101")
        .and("tenantId").is("TENANT-A")),
    new Update().set("status", "PAID"));
```

Vì filter có `_id`, tối đa một document khớp. `$set` thay field `status` nhưng không đụng tới các field khác ngoài đường dẫn đó.

**Đừng dùng `updateOne` với filter quá rộng** rồi hy vọng nó chọn document “đúng nhất” theo sort; nếu có nhiều document khớp mà không có định danh/điều kiện duy nhất, kết quả được chọn có thể không đúng ý định nghiệp vụ.

### 7.2. UpdateMulti: mọi document khớp

```java
bulk.updateMulti(
    Query.query(Criteria.where("tenantId").is("TENANT-A")
        .and("status").is("WAITING_RETRY")),
    new Update().set("status", "QUEUED"));
```

Với dữ liệu ở mục 4, thao tác này sửa **ORD-104 và ORD-105**. Nếu cần chỉ sửa 100 bản ghi đầu tiên, `updateMulti` không có ý nghĩa “update 100 document theo limit” chỉ vì gắn limit vào `Query`; cần thiết kế bước chọn ID theo index, rồi tạo các updateOne cụ thể hoặc một phương án batch tương ứng.

### 7.3. Các update operator thường gặp

```java
Update patch = new Update()
    .set("status", "PAID")
    .inc("retryCount", 1)
    .unset("obsoleteFlag")
    .currentDate("updatedAt");
```

`$set` đổi một giá trị; `$inc` tăng/giảm số; `$unset` xóa field; `$currentDate` đặt timestamp phía MongoDB theo kiểu được cấu hình. Không có operator nào buộc MongoDB phải ghi lại toàn bộ document. Tuy vậy, `set("nested", wholeObject)` có thể **thay toàn bộ object con**, làm mất sibling field; muốn sửa một field con, dùng dotted path như `"nested.trackingCode"`.

### 7.4. Update chưa chắc là thay đổi

Nếu `status` vốn đã là `PAID` và query tiếp tục `$set status=PAID`, document **có thể được match nhưng không modified**. Vì vậy `matchedCount` và `modifiedCount` khác nhau; không xem modifiedCount thấp là lỗi trong mọi trường hợp.

## 8. Upsert: cập nhật nếu khớp, tạo mới nếu không

`upsert(query, update)` diễn đạt hai khả năng:

1. Có document khớp filter: áp dụng các update operator.
2. Không có document khớp: tạo document mới theo quy tắc upsert của MongoDB, bao gồm các giá trị equality trong filter và các operator cập nhật phù hợp.

Với batch đối tác, khóa `(tenantId, externalRef)` phải được đảm bảo duy nhất.

```java
bulk.upsert(
    Query.query(
        Criteria.where("tenantId").is("TENANT-A")
            .and("externalRef").is("EXT-201")),
    new Update()
        .setOnInsert("tenantId", "TENANT-A")
        .setOnInsert("externalRef", "EXT-201")
        .set("status", "NEW")
        .set("amountMinor", 450000L));
```

`setOnInsert` chỉ có tác dụng **khi tạo document mới** do upsert; nếu đã có document, giá trị của những field này không bị thay theo nhánh update thường. `set` áp dụng cho cả trường hợp tạo mới và cập nhật hiện có.

### 8.1. Khi nào dùng setOnInsert?

Ví dụ đồng bộ hóa một khoản mục:

```java
Update update = new Update()
    .setOnInsert("createdAt",
        Instant.parse("2026-11-19T00:00:00Z"))
    .setOnInsert("source", "PARTNER-IMPORT")
    .set("status", "PAID")
    .set("updatedAt",
        Instant.parse("2026-11-20T02:00:00Z"));
```

`createdAt` và `source` chỉ được khởi tạo lúc tạo document; `status` và `updatedAt` được cập nhật mỗi lần xử lý. Đây là một lựa chọn nghiệp vụ: nếu một lần đồng bộ không được sửa `status` khi đã finalized, phải thêm điều kiện/state machine phù hợp thay vì cứ `$set`.

### 8.2. Upsert không đồng nghĩa kiểm soát duy nhất bằng code

Hai instance có thể đồng thời chạy:

```text
Instance A                Instance B
     |                         |
     +-- upsert EXT-201        +-- upsert EXT-201
     |                         |
     +-- chưa thấy document    +-- chưa thấy document
     |                         |
     +-- thử insert            +-- thử insert
                |
                v
        Unique index bảo vệ
        (tenantId, externalRef)
```

Nếu thiếu unique index, có thể tạo **hai bản ghi nghiệp vụ trùng**. Nếu có index phù hợp, MongoDB ngăn hai document trùng; một writer có thể cập nhật lại bản vừa được tạo hoặc gặp lỗi duplicate key tùy query/update/race cụ thể. **Không giả định mọi duplicate-key error đều được driver tự retry thành công**.

Khi upsert gặp duplicate key, service cần đọc lại document theo business key, xác minh tenant và trạng thái, rồi quyết định retry có kiểm soát hoặc báo conflict.

### 8.3. Upsert không có ID cố định

Nếu query không chỉ định `_id`, MongoDB có thể tự cấp `ObjectId` cho document mới. Trong model Java có `@Id String id`, Spring Data có thể chuyển ID BSON thành giá trị Java khi đọc. Tuy nhiên, nếu nghiệp vụ yêu cầu ID cố định hoặc định dạng cụ thể, phải **thiết kế rõ ID tạo mới và kiểm thử BSON**, không dựa vào giả định rằng upsert tự sinh ID giống như một lần `repository.save`.

Ví dụ dùng khóa ngoại bộ `(tenantId, externalRef)` để tìm bản ghi sau upsert; không nên cố đoán ID:

```javascript
db.orders.findOne({
  tenantId: "TENANT-A",
  externalRef: "EXT-201"
})
```

## 9. ReplaceOne: thay document là thao tác có rủi ro mất dữ liệu

`replaceOne(query, replacement)` ghi **representation đầy đủ** của document đích từ object thay thế. Nó khác với `updateOne(query, new Update().set(...))`.

### 9.1. Trước và sau replace

Ban đầu:

```javascript
{
  _id: "ORD-102",
  tenantId: "TENANT-A",
  externalRef: "EXT-102",
  status: "NEW",
  amountMinor: NumberLong(300000),
  legacy_note: "Giữ nếu không thay document"
}
```

Với entity `OrderDocument` **không khai báo `legacy_note`**, lệnh:

```java
bulk.replaceOne(
    Query.query(Criteria.where("id").is("ORD-102")
        .and("tenantId").is("TENANT-A")),
    new OrderDocument(
        "ORD-102",
        "TENANT-A",
        "EXT-102",
        "PAID",
        300000L,
        Instant.parse("2026-11-20T02:00:00Z")));
```

có thể tạo representation mới:

```javascript
{
  _id: "ORD-102",
  tenantId: "TENANT-A",
  externalRef: "EXT-102",
  status: "PAID",
  amountMinor: NumberLong(300000),
  updatedAt: ISODate("2026-11-20T02:00:00Z"),
  _class: "com.example.shop.orders.OrderDocument"
  // Không còn legacy_note.
}
```

Điều này **không phải lỗi MongoDB**: replacement có nhiệm vụ thay document bằng dữ liệu mới. Nếu field legacy phải được giữ, **không dùng replacement từ entity chỉ chứa một phần schema**; thay bằng `$set` các field sở hữu hoặc dùng cơ chế merge/round-trip BSON có kiểm soát.

### 9.2. Giữ _id bất biến

Replacement không được đổi `_id` của document đã khớp. Nếu object thay thế có ID khác, MongoDB có thể từ chối vì `_id` là immutable. Không bao giờ dùng `replaceOne` để “đổi khóa chính” của document.

Đối với upsert-replace, cần thiết kế riêng cách sinh ID và xử lý không khớp. Ví dụ bài này **không** bật upsert cho replacement để không tạo nhầm document.

### 9.3. Khi nào replacement hợp lý?

- Bên ghi **sở hữu toàn bộ schema** của document.
- Nhận được một snapshot mới đã xác minh đầy đủ.
- Muốn xóa có chủ đích những field không còn trong hợp đồng schema.
- Có version/CAS hoặc chiến lược khác để tránh ghi đè snapshot của writer đồng thời.

Không dùng replacement cho việc đơn giản như “đổi status”, “tăng retryCount” hoặc “cập nhật một trường trong object lồng nhau”.

## 10. Remove: xóa có phạm vi, không lạm dụng filter rộng

Để xóa bản ghi thử nghiệm `ORD-103` của tenant A:

```java
bulk.remove(Query.query(
    Criteria.where("id").is("ORD-103")
        .and("tenantId").is("TENANT-A")
        .and("status").is("TEST_ONLY")));
```

Trong ví dụ, `_id` bảo đảm điều kiện nhắm tới tối đa một document. Khi muốn dọn hàng nghìn bản ghi, không nên chỉ dùng `{ status: "EXPIRED" }` rồi xóa trực tiếp nếu hệ thống nhiều tenant hoặc có dữ liệu cần retention.

### 10.1. Kiểm tra trước khi xóa thật

Với các tác vụ cleanup:

1. Dựng filter từ ràng buộc tenant, loại dữ liệu và thời gian giữ lại.
2. Chạy **đếm và xem mẫu** trên dữ liệu thử nghiệm/tập đích đã xác minh.
3. Kiểm tra unique business rules, soft-delete policy, yêu cầu audit và backup/khôi phục.
4. Chia theo lô hoặc chọn ID cụ thể nếu cần giới hạn mỗi lần xóa.
5. Log batch ID, filter đã chuẩn hóa, số lượng xóa và lỗi.

**Không coi ordered bulk là biện pháp hoàn nguyên:** sau khi xóa thành công một phần rồi có lỗi ở operation kế tiếp, document đã xóa không tự quay lại nếu không dùng transaction phù hợp.

### 10.2. Soft delete thay cho remove

Nếu nghiệp vụ cần lưu lịch sử:

```java
bulk.updateOne(
    Query.query(Criteria.where("id").is("ORD-103")
        .and("tenantId").is("TENANT-A")),
    new Update()
        .set("deleted", true)
        .set("deletedAt", Instant.parse(
            "2026-11-20T02:00:00Z")));
```

Việc chọn soft delete hay hard delete phải dựa vào hợp đồng nghiệp vụ, bảo mật, retention và yêu cầu pháp lý. Nếu dùng soft delete, mọi truy vấn nghiệp vụ cần áp dụng điều kiện `deleted != true`/`deleted = false` theo quy ước dữ liệu rõ ràng.

## 11. Đọc BulkWriteResult đúng cách

Khi `execute()` thành công:

```java
import com.mongodb.bulk.BulkWriteResult;

BulkWriteResult result = bulk.execute();

int inserted = result.getInsertedCount();
int matched = result.getMatchedCount();
int modified = result.getModifiedCount();
int deleted = result.getDeletedCount();
int upserted = result.getUpserts().size();
```

| Trường trong kết quả | Diễn giải | Lưu ý |
| --- | --- | --- |
| `insertedCount` | Số document được thêm bởi insert operations | Không nhất thiết bao gồm document được tạo qua upsert |
| `matchedCount` | Tổng số document khớp các update/replace thích hợp | Không đồng nghĩa số operation; `updateMulti` có thể khớp nhiều document |
| `modifiedCount` | Số document thực sự thay đổi theo báo cáo driver | Có thể thấp hơn matchedCount do thao tác no-op |
| `deletedCount` | Tổng số document bị xóa | Một remove với filter rộng có thể ảnh hưởng nhiều document |
| `upserts` | Thông tin các upsert tạo document mới | Có thể dùng danh sách này để lấy index thao tác và ID được tạo |

Với **bộ seed và bulk ordered chính xác ở mục 4–5**, khi không có writer cạnh tranh và các thao tác đều thay đổi dữ liệu:

```text
insertedCount        = 1  (ORD-200)
matchedCount         = 4  (1 updateOne + 2 updateMulti + 1 replaceOne)
modifiedCount        = 4  (các thao tác trên thực sự đổi giá trị)
deletedCount         = 1  (ORD-103)
upserts.size()       = 1  (EXT-201 được tạo mới)
```

Nếu chạy **lại** một đợt bulk giống hệt trên database đã thay đổi, kết quả sẽ khác: insert `ORD-200` có thể lỗi duplicate key, updateMulti không còn match `WAITING_RETRY`, remove không còn đích và upsert có thể đi nhánh update. Vì vậy các con số trên chỉ là **kỳ vọng cho một lần chạy trên fixture đã seed**, không phải số cố định của method.

### 11.1. Trên lỗi, không luôn có BulkWriteResult bình thường

`execute()` có thể ném exception, kể cả khi một phần thao tác đã thành công. Với ordered/unordered, việc dừng/tiếp tục và phần kết quả có thể khác nhau.

Code xử lý cần:

- Phân biệt **lỗi lệnh ghi** (duplicate key, validation, bất biến BSON...) với lỗi kết nối/không xác định kết quả.
- Ghi nhận batch ID, tập operation và thông tin lỗi có thể truy xuất từ exception.
- Không mặc định retry **toàn bộ batch**; trước hết xác định thao tác nào đã áp dụng.
- Kiểm tra trạng thái thực tế của business keys hoặc dùng idempotency keys để đối soát.

Không nên đặt một khối `catch` rồi trả `insertedCount = 0` khi exception xảy ra: đó có thể là báo cáo sai và dẫn tới thao tác lặp gây mất dữ liệu.

### 11.2. Write acknowledgement

Bulk kết quả và kiểm soát lỗi cần write concern có **acknowledgement** phù hợp. `WriteConcern.UNACKNOWLEDGED` làm giảm khả năng xác định lệnh nào được áp dụng và có thể khiến một số phép truy cập kết quả ghi không khả dụng.

Với dữ liệu quan trọng, chọn write concern và read concern theo yêu cầu hệ thống; `acknowledged` có nghĩa server xác nhận theo mức đã cấu hình, **không** có nghĩa một bulk nhiều document trở thành atomic.

## 12. Lỗi một phần, retry và idempotency

Một bulk có nhiều thao tác độc lập nên được thiết kế như một **đợt công việc có thể đối soát**, không đơn giản như một lời gọi “gửi tất cả rồi quên”.

| Thao tác | Khi chạy lại cùng dữ liệu | Điều cần bảo vệ |
| --- | --- | --- |
| `insert` với ID cố định | Có thể lỗi duplicate key | Batch ID, kiểm tra document đã tồn tại, không tự coi mọi duplicate là thành công |
| `$set field=value` | Thường idempotent đối với cùng field/value | Writer đồng thời và cập nhật các field khác |
| `$inc counter=1` | **Không idempotent**, có thể tăng hai lần | CAS/version, operation ID hoặc deduplication |
| `upsert` theo business key | Có thể đi từ insert sang update khi retry | Unique index, filter chính xác, `setOnInsert` |
| `replaceOne` | Có thể ghi cùng snapshot lặp lại | Không ghi đè thay đổi mới của writer khác |
| `remove` theo ID | Lần sau có thể không còn đích | Audit/retention, không xóa nhầm document mới dùng lại business key |

### 12.1. Không retry toàn bộ unordered bulk một cách mù quáng

Giả sử một unordered bulk gồm insert, `$inc` và upsert. Nếu lỗi timeout xảy ra **sau khi server đã thực hiện một số lệnh**, ứng dụng chưa chắc biết chính xác phần đã commit. Retry toàn bộ có thể:

- Chèn trùng ID.
- Tăng counter hai lần.
- Cập nhật trạng thái của bản ghi vừa được user sửa.
- Sinh lỗi unique index khác với lần chạy đầu.

Phương án bền vững:

1. Gán `operationId`/`batchId` có ý nghĩa nghiệp vụ.
2. Chọn operations **có thể chạy lại** khi có thể.
3. Lưu checkpoint hoặc bảng ghi nhận thao tác đã xử lý theo yêu cầu.
4. Đối soát business keys sau lỗi trước khi retry.
5. Giới hạn số lần retry, áp backoff và báo lỗi có khả năng xử lý.

### 12.2. Những thao tác phụ thuộc thứ tự

Nếu cùng một document được thực hiện:

```text
1. updateOne(status = PAID)
2. replaceOne(status = NEW)
```

thứ tự có thể làm thay đổi kết quả. Với `UNORDERED`, không được dựa vào thứ tự này. Cách tốt hơn là **gộp logic thành một operation có điều kiện** hoặc tách thành những giai đoạn độc lập với checkpoint.

`ORDERED` giữ thứ tự của chính batch, nhưng **không ngăn** những writer khác cùng lúc sửa document. Để bảo vệ cạnh tranh, cần expected version/CAS hoặc transaction thích hợp.

## 13. BulkOperations không tự thay thế @Version và entity callbacks

Một điểm rất dễ hiểu nhầm: một entity có annotation `@Version` không khiến **mọi thao tác ghi** tự động có optimistic locking. Theo hợp đồng của `BulkOperations`, các thao tác cần kết quả riêng của từng entity, như **optimistic locking với `@Version`**, không được hỗ trợ giống các thao tác `save` chuẩn. Không nên dựa vào bulk để framework tự gắn version điều kiện và tự cập nhật version cho từng entity.

### 13.1. Mô hình có version

File `VersionedOrder.java`:

```java
package com.example.shop.orders;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record VersionedOrder(
    @Id String id,
    String tenantId,
    String status,
    @Version Long version
) {}
```

Với `repository.save(...)` thông thường, `@Version` giúp phát hiện stale write theo cách Spring Data hỗ trợ. Nhưng trong **bulk**, người viết phải thiết kế cách kiểm tra expected version.

### 13.2. CAS tường minh bên trong bulk

```java
BulkOperations bulk = template.bulkOps(
    BulkOperations.BulkMode.ORDERED,
    VersionedOrder.class);

bulk.updateOne(
    Query.query(Criteria.where("id").is("ORD-101")
        .and("tenantId").is("TENANT-A")
        .and("version").is(3L)),
    new Update()
        .set("status", "PAID")
        .inc("version", 1L));

BulkWriteResult result = bulk.execute();

if (result.getMatchedCount() != 1) {
    throw new IllegalStateException(
        "Không tìm được đơn/version phù hợp");
}
```

Trong đoạn này, việc **so sánh `version=3`** và **tăng version bằng `$inc`** được viết **tường minh**, chứ không do `BulkOperations` tự thực hiện theo `@Version`. Nếu một writer khác đã tăng version trước đó, filter không khớp và `matchedCount` có thể bằng 0.

**Lưu ý:** `BulkWriteResult` chỉ tổng hợp cho cả batch. Nếu chứa 100 updateOne có điều kiện version, `matchedCount = 95` cho thấy có 5 operation không khớp (giả sử mỗi query nhắm một document và không trùng nhau), nhưng **không tự chỉ rõ ID của 5 operation**. Muốn xác định từng bản ghi:

- Lưu mapping `operationId → business key / expectedVersion`.
- Chia batch hợp lý và đối soát các ID không được cập nhật.
- Với nghiệp vụ cần trả kết quả chính xác từng update hoặc quản lý optimistic locking entity, cân nhắc dùng API khác cho những lệnh đó.

### 13.3. Auditing và lifecycle callbacks

Trong các đường save entity thông thường, hệ thống có thể có `@CreatedDate`, `@LastModifiedDate`, `BeforeConvertCallback`, `BeforeSaveCallback` hoặc các event khác. Bulk write **không có hợp đồng “gọi save trên mỗi entity”**, vì vậy không nên trông chờ toàn bộ chu trình callback/auditing xảy ra như khi gọi `repository.save` riêng lẻ.

Nếu bulk cần `createdAt`, `updatedAt`, `updatedBy`, tenant, version hoặc audit metadata, hãy chuẩn bị giá trị một cách tường minh trong DTO/entity/`Update` và kiểm thử BSON cuối cùng. Với upsert, `setOnInsert("createdAt", ...)` thường thích hợp; với update, `set("updatedAt", ...)` thể hiện rõ thay đổi.

## 14. Bulk, transaction và tính nguyên tử

MongoDB bảo đảm **tính nguyên tử của một thao tác ghi trên một document**. Nhưng một bulk có nhiều insert/update/remove không mặc nhiên nguyên tử trên toàn batch.

### 14.1. Không có transaction

Ví dụ:

```text
Bulk ORDERED:
  INSERT A -> thành công
  UPDATE B -> thành công
  INSERT C -> duplicate key
  DELETE D -> chưa thực thi

Kết quả:
  A đã được thêm
  B đã được sửa
  C bị lỗi
  D còn nguyên
```

Ngay cả khi `execute()` ném exception, **A/B không tự rollback**. Với unordered, có thể có kết quả thành công/lỗi đan xen và thứ tự không theo danh sách nhập.

### 14.2. Khi cần tất cả hoặc không có gì

Nếu yêu cầu nghiệp vụ thật sự cần commit đồng thời nhiều document, có thể dùng **MongoDB multi-document transaction** khi deployment hỗ trợ (replica set/sharded cluster phù hợp) và Spring Data đã cấu hình transaction manager/session.

Ví dụ khái niệm trong một service đã có `TransactionTemplate`:

```java
transactionTemplate.executeWithoutResult(status -> {
    BulkOperations bulk = template.bulkOps(
        BulkOperations.BulkMode.ORDERED,
        OrderDocument.class);

    bulk.insert(new OrderDocument(
        "ORD-401", "TENANT-A", "EXT-401",
        "NEW", 100000L, Instant.parse(
            "2026-11-20T02:00:00Z")));

    bulk.updateOne(
        Query.query(Criteria.where("id").is("ORD-101")
            .and("tenantId").is("TENANT-A")),
        new Update().set("status", "PAID"));

    bulk.execute();
});
```

Mẫu này chỉ diễn tả **phạm vi transaction**. Để chạy thật, cần cấu hình `MongoTransactionManager` và transaction management của Spring, MongoDB hỗ trợ transaction, và `TransactionTemplate` trỏ đúng manager. Đừng copy rồi giả định transaction có hiệu lực khi chưa kiểm tra hạ tầng.

Transaction có chi phí; không nên dùng chỉ để “bulk nhanh hơn”. Ngoài ra, transaction không tự giải quyết idempotency của một request bị retry, cũng không bảo đảm mọi field unknown không bị replacement làm mất.

### 14.3. Transaction và bulk quá lớn

Bulk gồm nhiều document lớn trong transaction kéo dài có thể làm tăng tài nguyên, khả năng conflict và thời gian giữ snapshot. Với tác vụ ETL/import có thể đối soát, **chia batch có checkpoint** thường là lựa chọn thực tế hơn; chỉ dùng transaction ở phạm vi thật sự cần bất biến.

## 15. Chia batch, giới hạn tải và tối ưu hiệu năng

Không nên tạo một `BulkOperations` chứa hàng triệu thao tác rồi mới `execute()`. Dù driver/server có thể tự chia lệnh theo các giới hạn giao thức, ứng dụng vẫn tiêu tốn bộ nhớ giữ operation, khó checkpoint và khó xác định lỗi theo nhóm.

### 15.1. Chunking đơn giản

```java
import java.util.List;
import org.springframework.data.mongodb.core.BulkOperations;

public void insertChunks(
        MongoTemplate template,
        List<OrderDocument> orders) {

    int chunkSize = 500; // Ví dụ, cần đo theo kích thước document.

    for (int from = 0; from < orders.size(); from += chunkSize) {
        int to = Math.min(from + chunkSize, orders.size());
        List<OrderDocument> chunk = orders.subList(from, to);

        BulkOperations bulk = template.bulkOps(
            BulkOperations.BulkMode.UNORDERED,
            OrderDocument.class);

        bulk.insert(chunk);
        BulkWriteResult result = bulk.execute();

        // Ghi checkpoint/đối soát sau mỗi chunk thành công.
        System.out.println("Inserted: " + result.getInsertedCount());
    }
}
```

`orders` trong ví dụ là danh sách đã chuẩn hóa và được phép ghi. Đoạn này không bao gồm cơ chế retry và cố tình **không bắt exception rồi bỏ qua**; production phải lưu checkpoint có khả năng đối soát và xử lý lỗi từng chunk.

### 15.2. Vì sao chunk size không có một con số tối ưu?

Chi phí phụ thuộc:

- Kích thước trung bình và lớn nhất của document (MongoDB có giới hạn kích thước BSON mỗi document).
- Số field/index phải cập nhật trên mỗi write.
- Mức tải server, độ trễ mạng, connection pool và write concern.
- Tỷ lệ duplicate key, conflict, upsert và updateMulti nhiều document.
- Bộ nhớ ứng dụng và nhu cầu checkpoint/retry.

Giới hạn batch/message do MongoDB server/driver công bố có thể khiến driver chia tác vụ thành nhiều phần. Không nên đồng nhất **một lời gọi `execute()`** với đúng **một network packet** hoặc một transaction.

### 15.3. Gom nhiều collection?

`MongoTemplate.bulkOps(mode, Entity.class)` gắn bulk với một entity/collection đích. Nếu cần ghi nhiều collection, tạo các bulk tương ứng; không trộn order, customer và inventory vào cùng một builder rồi mong framework tự phân phối.

Nếu nhiều collection cần cập nhật nhất quán, thiết kế session/transaction ở mức service phù hợp hoặc xử lý theo event/saga thay vì gọi đó là “một bulk”. Điều này cũng giúp dễ giám sát lỗi theo collection.

### 15.4. Đo lường đúng

Khi benchmark:

1. So sánh với vòng `save` trên **cùng kích thước dữ liệu**, cùng write concern và cùng index.
2. Ghi thời gian `execute()`, throughput (operations/s), p95/p99 latency, CPU và số document xử lý.
3. Theo dõi duplicate key, write errors, write concern errors, memory, queue và lock contention.
4. Tách chi phí **mapping BSON** khỏi chi phí driver/network/server nếu cần chẩn đoán.
5. Kiểm tra tác động của index: thêm index giúp đọc nhưng có thể tăng chi phí ghi.

`explain("executionStats")` rất hữu ích cho các **query/filter** dùng trong update hoặc bước chọn ID, nhưng không thay thế đo toàn bộ bulk write. Mức hiệu năng còn chịu ảnh hưởng của cách viết/update index và mức cạnh tranh.

## 16. Kế hoạch phục hồi sau lỗi

Một tác vụ bulk production nên có thông tin tối thiểu:

| Dữ liệu vận hành | Tại sao cần |
| --- | --- |
| `batchId` và nguồn dữ liệu | Truy dấu một lần import/sync |
| ID/business key cho từng operation | Biết thao tác nào cần đối soát |
| Loại thao tác và expected version | Phân biệt insert/update/upsert, chống stale write |
| Thời điểm bắt đầu/kết thúc | Đo độ trễ và điều tra lỗi |
| Kết quả thống kê và lỗi driver | Đối chiếu số lượng thực thi |
| Checkpoint cuối đã xác nhận | Tránh xử lý lại toàn bộ khi restart |
| Trạng thái retry/quarantine | Cách xử lý bản ghi lỗi dữ liệu riêng biệt |

**Cẩn trọng thông tin nhạy cảm:** log nên lưu ID hoặc metadata đã lọc, không đưa toàn bộ payload khách hàng, token hoặc dữ liệu bảo mật vào log bulk error.

### 16.1. Khi có lỗi duplicate key

Không tự coi duplicate key là thành công. Phải xác minh:

- Document đang tồn tại có đúng business key và tenant?
- Dữ liệu hiện tại có tương thích với operation không?
- Đó là retry của **cùng một operation** hay xung đột của hai yêu cầu khác nhau?
- Nếu là upsert, unique index đã được tạo đúng chưa?

Sau đó quyết định *skip đã hoàn thành*, *retry có điều kiện*, *merge* hoặc *đưa vào hàng xử lý lỗi*. Với `ORDERED`, đợt ghi phía sau lỗi cần được xem là chưa thực hiện; với `UNORDERED`, phải đối soát từng operation để tránh đoán thứ tự.

## 17. Kiểm thử tích hợp với MongoDB: kết quả và BSON sau ghi

Mock `MongoTemplate` không thể xác nhận server áp dụng đúng `$set`, upsert tạo document, replacement xóa field legacy hay `ORDERED` dừng sau lỗi duplicate key. Cần kiểm thử với MongoDB thật trong **instance/database cô lập**. Có thể sử dụng Testcontainers theo cách dự án Spring Boot cấu hình test connection.

Ví dụ sau dùng JUnit 5, AssertJ và `@DataMongoTest`. Chú ý import `@DataMongoTest` trong ví dụ thuộc dòng Spring Boot dùng package `org.springframework.boot.test.autoconfigure.data.mongo`; kiểm tra package phù hợp nếu dự án nâng major version.

### 17.1. Fixture chứa dữ liệu ngoài Java model

File `OrderBulkOperationsTest.java`:

```java
package com.example.shop.orders;

import com.mongodb.bulk.BulkWriteResult;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DataMongoTest
class OrderBulkOperationsTest {

    @Autowired
    MongoTemplate template;

    private static Document order(
            String id,
            String tenantId,
            String externalRef,
            String status,
            long amountMinor) {

        return new Document("_id", id)
            .append("tenantId", tenantId)
            .append("externalRef", externalRef)
            .append("status", status)
            .append("amountMinor", amountMinor)
            .append(
                "updatedAt",
                Date.from(Instant.parse(
                    "2026-11-19T01:00:00Z")))
            .append("legacy_note", "legacy-owned-data");
    }

    private Document rawById(String id) {
        return template.getCollection("orders")
            .find(new Document("_id", id))
            .first();
    }

    @BeforeEach
    void seed() {
        // Chỉ xóa dữ liệu trong database test CÔ LẬP.
        var collection = template.getCollection("orders");
        collection.deleteMany(new Document());

        collection.insertMany(List.of(
            order("ORD-101", "TENANT-A", "EXT-101",
                  "NEW", 200000L),
            order("ORD-102", "TENANT-A", "EXT-102",
                  "NEW", 300000L),
            order("ORD-103", "TENANT-A", "EXT-103",
                  "TEST_ONLY", 0L),
            order("ORD-104", "TENANT-A", "EXT-104",
                  "WAITING_RETRY", 100000L),
            order("ORD-105", "TENANT-A", "EXT-105",
                  "WAITING_RETRY", 150000L),
            order("ORD-B01", "TENANT-B", "EXT-101",
                  "NEW", 999999L)
        ));
    }

    @Test
    void mixedBulkAppliesSixOperationsInCorrectScope() {
        BulkWriteResult result =
            new OrderBulkService(template).executeExample();

        assertThat(result.wasAcknowledged()).isTrue();
        assertThat(result.getInsertedCount()).isEqualTo(1);
        assertThat(result.getMatchedCount()).isEqualTo(4);
        assertThat(result.getModifiedCount()).isEqualTo(4);
        assertThat(result.getDeletedCount()).isEqualTo(1);
        assertThat(result.getUpserts()).hasSize(1);

        assertThat(rawById("ORD-200")).isNotNull();
        assertThat(rawById("ORD-103")).isNull();

        assertThat(rawById("ORD-101").getString("status"))
            .isEqualTo("PAID");
        assertThat(rawById("ORD-104").getString("status"))
            .isEqualTo("QUEUED");
        assertThat(rawById("ORD-105").getString("status"))
            .isEqualTo("QUEUED");

        Document upserted = template.getCollection("orders")
            .find(new Document("tenantId", "TENANT-A")
                .append("externalRef", "EXT-201"))
            .first();
        assertThat(upserted).isNotNull();
        assertThat(upserted.getString("status"))
            .isEqualTo("NEW");

        // Không rò rỉ sang tenant B dù trùng externalRef.
        assertThat(rawById("ORD-B01").getString("status"))
            .isEqualTo("NEW");
    }

    @Test
    void updatePreservesUnknownFieldsButReplaceRemovesThem() {
        new OrderBulkService(template).executeExample();

        Document updated = rawById("ORD-101");
        assertThat(updated).isNotNull();
        assertThat(updated.getString("legacy_note"))
            .isEqualTo("legacy-owned-data");

        Document replaced = rawById("ORD-102");
        assertThat(replaced).isNotNull();
        assertThat(replaced.getString("_id"))
            .isEqualTo("ORD-102");
        assertThat(replaced.getString("status"))
            .isEqualTo("PAID");

        // Replacement không giữ field không có trong OrderDocument.
        assertThat(replaced.containsKey("legacy_note"))
            .isFalse();
    }

    @Test
    void orderedBulkStopsAfterDuplicateKeyButEarlierInsertPersists() {
        BulkOperations bulk = template.bulkOps(
            BulkOperations.BulkMode.ORDERED,
            OrderDocument.class);

        bulk.insert(new OrderDocument(
            "ORD-300", "TENANT-A", "EXT-300",
            "NEW", 100000L,
            Instant.parse("2026-11-20T02:00:00Z")));

        // ORD-101 đã tồn tại; insert lần hai sẽ lỗi duplicate _id.
        bulk.insert(new OrderDocument(
            "ORD-101", "TENANT-A", "EXT-DUPLICATE",
            "NEW", 100000L,
            Instant.parse("2026-11-20T02:00:00Z")));

        // Không được chạy nếu ordered dừng tại operation thứ hai.
        bulk.updateOne(
            Query.query(Criteria.where("id").is("ORD-104")
                .and("tenantId").is("TENANT-A")),
            new Update().set("status", "PAID"));

        assertThatThrownBy(() -> bulk.execute())
            .isInstanceOf(RuntimeException.class);

        // Bulk không phải transaction: phần trước lỗi vẫn có thể ghi.
        assertThat(rawById("ORD-300")).isNotNull();
        assertThat(rawById("ORD-104").getString("status"))
            .isEqualTo("WAITING_RETRY");
    }
}
```

**Cảnh báo rõ ràng:** `collection.deleteMany(new Document())` xóa toàn bộ `orders` của database test mà nó kết nối. Phải có test profile và database cô lập; **không chạy những test này trên môi trường production**.

Kết quả đếm ở test `mixedBulkAppliesSixOperationsInCorrectScope` chỉ áp dụng đúng fixture trên, không có writer đồng thời và không có thay đổi mapping/version ngoài ví dụ. `modifiedCount` có thể khác `matchedCount` với các update không làm thay đổi giá trị.

### 17.2. Vì sao fixture cần được chèn bằng driver?

`OrderDocument` không khai báo `legacy_note`. Nếu seed bằng `template.insert(new OrderDocument(...))`, document vốn không có field này; sau `replaceOne`, kiểm thử không thể biết dữ liệu ngoài model có bị xóa hay không.

Lệnh `template.getCollection("orders").insertMany(...)` ghi `org.bson.Document` trực tiếp qua driver, tạo **BSON đúng kiểu** gồm String, Int64, Date và field lạ. Đọc lại bằng raw driver sau bulk chứng minh field nào còn/mất.

### 17.3. Một kiểm thử riêng cho CAS thủ công

Giả sử document đã có `version: NumberLong(3)`. Kiểm tra hai update cùng expectedVersion:

```java
BulkOperations bulk = template.bulkOps(
    BulkOperations.BulkMode.ORDERED,
    OrderDocument.class);

Query v3 = Query.query(Criteria.where("id").is("ORD-101")
    .and("tenantId").is("TENANT-A")
    .and("version").is(3L));

bulk.updateOne(v3,
    new Update().set("status", "PAID")
        .inc("version", 1L));

bulk.updateOne(
    Query.query(Criteria.where("id").is("ORD-101")
        .and("tenantId").is("TENANT-A")
        .and("version").is(3L)),
    new Update().set("status", "CANCELLED")
        .inc("version", 1L));

BulkWriteResult result = bulk.execute();
// Kỳ vọng matchedCount = 1, version từ 3 thành 4.
```

Đây là **đoạn minh họa bổ sung**, không chạy trực tiếp trên fixture ở mục 17.1 vì fixture đó chưa có version. Phải seed document có version trước và kiểm tra BSON sau ghi. Đoạn này thể hiện cách tạo CAS **thủ công** trong bulk, không hứa hẹn `@Version` sẽ tự làm hộ.

### 17.4. Ma trận trường hợp nên kiểm thử

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Insert ID mới | `insertedCount` tăng, BSON mapping đúng |
| Insert trùng `_id` | Có lỗi duplicate key; ordered dừng phần sau |
| UpdateOne có đúng ID và tenant | Chỉ đúng document đích bị sửa |
| UpdateMulti cùng trạng thái trong tenant | Mọi document khớp được đổi, tenant khác không đổi |
| Upsert lần đầu | Có `upserted` và document mới đủ field cần thiết |
| Upsert lần hai | Đi nhánh update, không tạo duplicate business key |
| ReplaceOne trên document có field lạ | Phát hiện field bị loại nếu không có trong replacement |
| UpdateOne `$set` trên document có field lạ | Field lạ được giữ |
| Remove filter không khớp | Không xóa gì, `deletedCount` phù hợp |
| Unordered bulk có một duplicate key | Những thao tác độc lập khác có thể đã thực thi |
| Update dùng expected version | Một writer stale không khớp, không tăng version lần hai |
| Lỗi mạng giữa batch | Không tự giả định 0 write đã thành công; có đối soát |
| Batch rỗng | Service không gọi `execute()` với danh sách operation rỗng |
| Batch lớn | Có chia lô, giới hạn bộ nhớ và checkpoint |

## 18. Reactive bulk write: cùng ngữ nghĩa, API bất đồng bộ

Trong Spring Data MongoDB reactive, `ReactiveMongoTemplate.bulkOps(...)` cung cấp hướng tổ chức bulk tương ứng với `ReactiveBulkOperations` và trả publisher cho `execute()`, thường là `Mono<BulkWriteResult>`.

Ví dụ:

```java
import com.mongodb.bulk.BulkWriteResult;
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import reactor.core.publisher.Mono;

public Mono<BulkWriteResult> markQueuedReactive(
        ReactiveMongoTemplate template, String tenantId) {

    return template.bulkOps(
            BulkOperations.BulkMode.UNORDERED,
            OrderDocument.class)
        .updateMulti(
            Query.query(Criteria.where("tenantId").is(tenantId)
                .and("status").is("WAITING_RETRY")),
            new Update().set("status", "QUEUED"))
        .execute();
}
```

Đoạn mã được đặt trong service/class Java, cần xác minh `tenantId` trước khi gọi. Publisher **không thực hiện tác vụ cho đến khi có subscribe** theo hợp đồng Reactor. Kiểm thử reactive có thể sử dụng `StepVerifier`; đừng gọi `block()` trong một luồng non-blocking production chỉ để có kết quả đồng bộ.

Ở reactive hay imperative, **ORDERED/UNORDERED, partial failure, unique index, không tự động optimistic locking và idempotency** vẫn là cùng những vấn đề cần xử lý. Khác biệt chủ yếu là cách điều phối kết quả và tài nguyên không chặn luồng.

## 19. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Gọi nhiều `bulk.insert` nhưng database không đổi | Chưa gọi `execute()` | Thực thi builder và kiểm tra kết quả/lỗi |
| `ORDERED` báo lỗi rồi bản ghi đầu vẫn tồn tại | Bulk không phải transaction | Thiết kế partial failure, checkpoint hoặc transaction phù hợp |
| `UNORDERED` tạo trạng thái cuối khó đoán | Nhiều operation phụ thuộc thứ tự trên cùng document | Gom logic hoặc chia giai đoạn ordered |
| Insert lỗi trùng ID | Có unique `_id`/business key | Xử lý duplicate, cân nhắc upsert đúng ngữ nghĩa |
| Upsert tạo hai bản ghi trùng nghiệp vụ | Thiếu unique index hoặc filter không ổn định | Dùng unique key theo tenant và đối soát concurrent upsert |
| Replace xóa field legacy | Replacement không chứa field ngoài Java model | Dùng `$set` hoặc merge BSON có kiểm soát |
| Bulk không tăng `@Version` như `save` | Không có optimistic locking entity tự động trong bulk | CAS expected version và `$inc` tường minh |
| `matchedCount` lớn hơn `modifiedCount` | Update no-op hoặc giá trị đã đúng | So sánh hai chỉ số theo ý nghĩa riêng |
| Retry khiến counter tăng hai lần | `$inc` không idempotent | Deduplication/operation ID, CAS |
| Đơn tenant B bị sửa khi batch chạy tenant A | Filter thiếu tenantId | Bắt buộc scoping mọi update/remove/upsert |
| Remove xóa quá nhiều | Query quá rộng hoặc logic retention sai | Chọn ID/ràng buộc rõ, xem mẫu và kiểm tra quyền |
| Batch quá lớn gây tiêu tốn tài nguyên | Giữ nhiều operation trong bộ nhớ | Chunking, giới hạn payload, checkpoint |
| Không có auditing timestamp | Bulk không chạy cùng callbacks của entity save | Ghi timestamp/audit field có chủ đích |
| Thấy exception và báo “không có ghi nào thành công” | Không hiểu partial result | Đối soát thực tế và không retry mù quáng |

## 20. Bài tập vận dụng

Một hệ thống vận hành kho nhận tệp đồng bộ gồm 10.000 sản phẩm cho nhiều nhà cung cấp. Mỗi sản phẩm có `tenantId`, `sku`, `priceMinor`, `available`, `updatedAt` và `sourceRevision`. Collection còn có `supplierMetadata` do dịch vụ khác quản lý.

Yêu cầu:

1. Đề xuất unique index phù hợp cho khóa nghiệp vụ `(tenantId, sku)`.
2. Thiết kế **bulk upsert** cập nhật giá và trạng thái hàng, nhưng chỉ đặt `createdAt` khi insert mới.
3. Nếu chỉ cần cập nhật giá, giải thích vì sao không nên `replaceOne` toàn document.
4. Với hai dòng trong cùng file nói về cùng `sku`, nên dùng `ORDERED` hay `UNORDERED`? Đưa ra chính sách deduplicate hoặc từ chối file.
5. Một giá được thay bằng `$inc` theo số tiền điều chỉnh; lần retry sau timeout có thể gây lỗi gì?
6. Thiết kế chunk size, checkpoint và cách xử lý một dòng có schema không hợp lệ.
7. Nếu `sourceRevision` phải chống ghi đè từ một tệp cũ, hãy viết điều kiện CAS/version tường minh trong `Query` và mô tả cách kiểm tra kết quả.
8. Viết integration test seed BSON có `supplierMetadata`, chạy bulk update và xác minh metadata vẫn còn; sau đó chạy replace với entity thiếu field để nhận diện nguy cơ mất dữ liệu.

**Định hướng giải:** dùng `$set`/`setOnInsert` với unique index, giữ mọi update trong phạm vi tenant, loại bỏ duplicate input trước khi dựng bulk và ưu tiên operations idempotent khi có thể. `UNORDERED` chỉ phù hợp khi các operation độc lập; nếu cùng SKU xuất hiện nhiều lần và thứ tự có ý nghĩa, cần chuẩn hóa dữ liệu hoặc xử lý riêng thay vì dựa vào thứ tự bulk. Version/CAS phải được triển khai rõ, vì `BulkOperations` không thay thế optimistic locking của `save`.

## 21. Tài liệu tham khảo

- Spring Data MongoDB — [Bulk Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.bulk-operations): cách sử dụng `BulkOperations` và lưu ý về optimistic locking.
- Spring Data MongoDB — [BulkOperations API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/BulkOperations.html): `BulkMode`, `insert`, `updateOne`, `updateMulti`, `upsert`, `replaceOne`, `remove` và `execute`.
- Spring Data MongoDB — [ReactiveBulkOperations API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveBulkOperations.html): bulk với publisher không chặn luồng.
- MongoDB Manual — [Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/): ordered/unordered, semantics và hành vi lỗi.
- MongoDB Manual — [db.collection.bulkWrite()](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/): kết quả, ordered flag và danh sách operation.
- MongoDB Manual — [Transactions](https://www.mongodb.com/docs/manual/core/transactions/): ranh giới nguyên tử và yêu cầu hạ tầng khi dùng transaction nhiều document.

## Ghi nhớ

**`BulkOperations` là công cụ gom các thao tác ghi**, không phải một cơ chế transaction hay một vòng `save` entity tự động. Dùng `insert` để thêm mới, `updateOne`/`updateMulti` để sửa có chọn lọc, `upsert` khi không có thì tạo mới, `replaceOne` khi thật sự muốn thay toàn bộ document và `remove` khi xóa đã được xác thực. Chọn `ORDERED` nếu cần thứ tự, `UNORDERED` khi các lệnh độc lập; luôn kiểm tra `BulkWriteResult` và khả năng lỗi một phần. Với dữ liệu quan trọng, giữ giới hạn tenant, unique business key, CAS/version, idempotency, kiểm thử BSON thật và checkpoint để thao tác hàng loạt có thể vận hành an toàn.
