# Tính nguyên tử của một document và giới hạn của nhiều lệnh liên tiếp

## 1. Nguyên tử ở cấp document không có nghĩa cả nghiệp vụ nguyên tử

Trong chương **Kiểm soát đồng thời** của **Spring Data MongoDB**, nhiều hệ thống phải xử lý cùng lúc các yêu cầu đặt hàng, trừ tồn kho, chuyển trạng thái hoặc chuyển tiền. MongoDB có một bảo đảm nền tảng: **một thao tác ghi trên một document có tính nguyên tử ở cấp document đó**. Nhưng một chuỗi `find → check → save`, hai lần `updateOne` hay các thao tác trên hai collection **không tự động** thuộc cùng một giao dịch.

Ví dụ sản phẩm có `stock_qty = 5`, hai khách hàng cùng muốn giữ chỗ 3 đơn vị:

~~~text
Request A                         Request B
---------                         ---------
read(stock = 5)
                                  read(stock = 5)
5 >= 3 => hợp lệ                   5 >= 3 => hợp lệ
save(stock = 2)
                                  save(stock = 2)
thông báo thành công               thông báo thành công
~~~

Hai request cùng nhận mua tổng cộng **6** sản phẩm, nhưng tồn kho chỉ ghi nhận giảm **3**. Mỗi lần `save` có thể đã nguyên tử, song quá trình **đọc → kiểm tra → ghi** vẫn bị *lost update*.

Để giữ invariant “stock không âm” trong **một document**, chuyển thành một câu lệnh có điều kiện:

~~~javascript
db.inventory_products.updateOne(
  {
    _id: "p-101",
    tenantId: "tenant-a",
    status: "ACTIVE",
    stock_qty: { $gte: 3 }
  },
  { $inc: { stock_qty: -3 } }
);
~~~

MongoDB kiểm tra điều kiện khi áp dụng write. Một request trừ 3 thành công từ 5 xuống 2, request thứ hai sẽ **không khớp** `stock_qty >= 3`; không xảy ra oversell nếu các đường ghi khác cũng tuân thủ invariant này.

Mục tiêu của bài:

- Phân biệt **nguyên tử một document** với **nguyên tử nhiều lệnh/nhiều document**.
- Nhận diện lost update, stale read, time-of-check/time-of-use và retry nguy hiểm.
- Sử dụng `MongoTemplate.updateFirst`, `$inc`, `findAndModify` và điều kiện compare-and-set.
- Biết khi nào `@Version` hoặc MongoDB transaction là cần thiết.
- Xử lý đúng `matchedCount`, idempotency, lỗi mạng, write concern và kiểm thử cạnh tranh.

> Ví dụ dùng Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x và MongoDB tương thích. Những chỗ phụ thuộc framework/driver/topology phải được xác minh trên phiên bản đang triển khai. Bài hướng dẫn mô hình đúng về concurrency, không thay thế quy trình kiểm thử và kiểm toán cho hệ thống tài chính thật.

## 2. Ma trận các loại bảo đảm

| Khái niệm | Bảo đảm hoặc mục đích | Không tự bảo đảm |
|---|---|---|
| Single-document atomic write | Một lệnh sửa một document không để lộ trạng thái ghi dở của chính lệnh ấy | Các lệnh tiếp theo cũng commit |
| `$inc`, `$set`, `$addToSet` | Thao tác field trong một update server-side | Một request phát lại không tác động hai lần |
| Conditional update | Chỉ ghi khi filter vẫn khớp | Tự giải thích vì sao filter không khớp |
| `findAndModify` | Tìm/sửa một document nguyên tử và lấy pre/post-image | Sửa các document khác cùng giao dịch |
| `@Version` | Phát hiện stale save trên đường ghi hỗ trợ optimistic locking | Tự bảo vệ mọi raw/bulk update |
| Unique index | Chặn duplicate business key theo index | Các thao tác xuyên collection nguyên tử |
| Write concern | Mức xác nhận/durability của ghi | Đúng invariant nghiệp vụ |
| Retryable writes | Driver có thể retry một số lệnh hỗ trợ theo cơ chế riêng | Exactly-once cho toàn bộ workflow |
| Transaction | Tính commit/rollback cho các thao tác được enlist trong transaction | Rollback email/API bên ngoài MongoDB |
| Idempotency key | Chống áp dụng lại một ý định nghiệp vụ | Tự thay transaction khi nhiều document cần all-or-nothing |

~~~mermaid
flowchart TD
    A["Nghiệp vụ cần ghi"] --> B{"Invariant nằm trong một document?"}
    B -->|"Có"| C["Conditional update / findAndModify"]
    B -->|"Không"| D{"Nhiều document phải cùng commit?"}
    D -->|"Có"| E["Transaction + MongoTransactionManager"]
    D -->|"Không"| F["State machine + compensation/reconciliation"]
    C --> G["Check matched/result"]
    E --> H["Handle commit/retry errors"]
    F --> H
    G --> I["Idempotency và observability"]
    H --> I
~~~

Một HTTP request, một method Java hay một `BulkOperations.execute()` không tự tạo transaction. Phạm vi bảo đảm phải được xác định **theo thao tác thực tế trên MongoDB**.

## 3. Một thao tác có thể cập nhật nhiều field của một document

Document:

~~~json
{
  "_id": "p-101",
  "tenantId": "tenant-a",
  "status": "ACTIVE",
  "stock_qty": 5,
  "reserved_qty": 0
}
~~~

Một lệnh thay đổi đồng thời:

~~~javascript
db.inventory_products.updateOne(
  {
    _id: "p-101",
    tenantId: "tenant-a",
    stock_qty: { $gte: 3 }
  },
  {
    $inc: {
      stock_qty: -3,
      reserved_qty: 3
    },
    $set: { status: "RESERVING" }
  }
);
~~~

Trong phạm vi document đích, các field này được cập nhật trong **một** thao tác nguyên tử. Một reader không nhận trạng thái cập nhật nửa chừng do chính lệnh này chỉ mới ghi `stock_qty` mà chưa ghi `reserved_qty`.

So sánh với **hai lệnh**:

~~~javascript
db.inventory_products.updateOne(
  { _id: "p-101" },
  { $inc: { stock_qty: -3 } }
);

db.inventory_products.updateOne(
  { _id: "p-101" },
  { $inc: { reserved_qty: 3 } }
);
~~~

Nếu process crash giữa hai lệnh, document sẽ có stock giảm nhưng số reserved không tăng. Một request khác cũng có thể chen vào giữa hai lời gọi. **Hai thao tác nguyên tử riêng không tạo thành một thao tác nguyên tử chung**.

### 3.1. Điều kiện trên filter là một phần của tính đúng đắn

Nếu filter chỉ có `{ _id: "p-101" }`, hai lệnh `$inc: { stock_qty: -3 }` có thể đều khớp: stock 5 → 2 → −1. MongoDB không tự suy ra invariant “stock không âm”.

Điều kiện `stock_qty >= 3` phải nằm **trong lệnh ghi** để request thứ hai được từ chối khi request thứ nhất đã giảm tồn kho. Một lần đọc trước đó không bảo vệ được invariant này.

### 3.2. Array và document lồng cũng nằm trong một document

~~~javascript
db.carts.updateOne(
  { _id: "cart-101", tenantId: "tenant-a" },
  {
    $addToSet: { reservedSkus: "BOTTLE-500" },
    $set: { updatedBy: "checkout-service" }
  }
);
~~~

Hai thay đổi xảy ra nguyên tử trên cùng document cart. Nhưng nếu service tiếp tục trừ tồn kho trên **document sản phẩm khác**, sự bảo đảm chỉ ở cart **không tự mở rộng** sang product.

Đừng nhúng toàn bộ dữ liệu không giới hạn vào một document chỉ để tận dụng atomicity: MongoDB có giới hạn BSON document **16 MiB**, và một document quá lớn/nóng có thể tạo contention.

## 4. Lost update và time-of-check/time-of-use

Mẫu thường gặp:

~~~java
InventoryProduct current = repository.findById("p-101")
        .orElseThrow();

if (current.getStock() >= 3) {
    current.setStock(current.getStock() - 3);
    repository.save(current);
}
~~~

Giả sử entity không dùng `@Version`. Hai request đọc cùng giá trị cũ rồi lưu nguyên trạng entity có thể ghi đè kết quả của nhau. Kể cả khi một request đọc từ primary, dữ liệu vẫn có thể bị request khác sửa **sau khi đọc, trước khi ghi**.

Một chuỗi dễ sai khác:

~~~java
if (!repository.existsById("external-101")) {
    repository.save(newEntity);
}
~~~

Hai request có thể cùng thấy `existsById == false`. Nếu cần uniqueness, phải dùng **unique index** theo business key, không trông chờ read-before-insert.

### 4.1. synchronized không phải distributed lock

~~~java
public synchronized void reserve(...) {
    // find, check, save
}
~~~

`synchronized` chỉ khóa các thread đi qua **cùng instance trong một JVM**. Nhiều pod, job, worker và kết nối MongoDB khác vẫn có thể ghi đồng thời. Đây không phải giải pháp tổng quát cho concurrency nhiều instance.

### 4.2. Atomicity và CAS khác nhau

Lệnh cập nhật chỉ theo `_id` vẫn nguyên tử, nhưng không ngăn stale update ghi đè state mới. **Compare-and-set (CAS)** có nghĩa “chỉ thay đổi nếu trạng thái còn phù hợp với kỳ vọng”:

~~~javascript
db.orders.updateOne(
  { _id: "ord-101", tenantId: "tenant-a", status: "PENDING" },
  { $set: { status: "PAID" } }
);
~~~

Nếu một request khác đã chuyển trạng thái sang `CANCELLED`, filter không còn khớp. Khi đó việc không sửa document là **kết quả hợp lệ của CAS**, không nhất thiết là lỗi database.

## 5. Entity và repository mẫu

Các ví dụ dùng collection `inventory_products`. Property Java `stock` được ánh xạ vào BSON `stock_qty`.

**InventoryProduct.java**

~~~java
package com.example.inventory;

import java.util.ArrayList;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "inventory_products")
public class InventoryProduct {
    @MongoId(FieldType.STRING)
    private String id;
    private String tenantId;
    private String status;

    @Field("stock_qty")
    private long stock;

    private List<String> appliedCommandIds;

    protected InventoryProduct() {}

    public InventoryProduct(
            String id, String tenantId, String status, long stock) {
        this.id = id;
        this.tenantId = tenantId;
        this.status = status;
        this.stock = stock;
        this.appliedCommandIds = new ArrayList<>();
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getStatus() { return status; }
    public long getStock() { return stock; }
    public List<String> getAppliedCommandIds() {
        return appliedCommandIds;
    }

    public void setStock(long stock) { this.stock = stock; }
    public void setStatus(String status) { this.status = status; }
}
~~~

**InventoryProductRepository.java**

~~~java
package com.example.inventory;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface InventoryProductRepository
        extends MongoRepository<InventoryProduct, String> {
}
~~~

`@MongoId(FieldType.STRING)` khiến `id` được lưu ở `_id` kiểu String. `@Field("stock_qty")` định nghĩa tên BSON vật lý. `tenantId` có vai trò phạm vi quyền nghiệp vụ nhưng **không tự lọc** truy vấn; service phải đưa tenant đáng tin cậy vào filter.

Field `appliedCommandIds` được dùng ở ví dụ idempotency trong một document. Nó **không** phải cơ chế lưu request ID vô hạn cho production.

## 6. Conditional update bằng MongoTemplate.updateFirst

**StockReservationService.java**

~~~java
package com.example.inventory;

import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class StockReservationService {
    private final MongoTemplate mongo;

    public StockReservationService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public boolean reserve(
            String authenticatedTenantId,
            String productId,
            long quantity) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || productId == null || productId.isBlank()
                || quantity <= 0) {
            throw new IllegalArgumentException("Request không hợp lệ");
        }

        Query query = Query.query(
                Criteria.where("id").is(productId)
                        .and("tenantId").is(authenticatedTenantId)
                        .and("status").is("ACTIVE")
                        .and("stock").gte(quantity));

        Update update = new Update()
                .inc("stock", -quantity);

        UpdateResult result = mongo.updateFirst(
                query, update, InventoryProduct.class);

        return result.getMatchedCount() == 1;
    }
}
~~~

Một lệnh thực tế tương đương:

~~~javascript
db.inventory_products.updateOne(
  {
    _id: "p-101",
    tenantId: "tenant-a",
    status: "ACTIVE",
    stock_qty: { $gte: 3 }
  },
  { $inc: { stock_qty: -3 } }
);
~~~

Vì phương thức dùng `InventoryProduct.class`, Spring Data có metadata để chuyển property Java `stock` sang `stock_qty`. Dùng lệnh raw shell/driver thì phải viết tên BSON thật.

### 6.1. Diễn giải kết quả

`getMatchedCount() == 1` nghĩa là một document thỏa **toàn bộ** filter và lệnh ghi nhận kết quả theo write concern. Khi `matchedCount = 0`, có thể do:

- ID không tồn tại;
- Tenant khác, không có quyền;
- Sản phẩm không ACTIVE;
- Tồn kho không đủ.

Một kết quả 0 **không đủ phân biệt nguyên nhân**. Nếu cần phân loại thành 404/409 hoặc idempotent replay, phải có contract và bước đọc/đối soát an toàn sau lệnh; đừng dùng read-before-update để thay thế bảo vệ CAS.

### 6.2. Matched khác modified

~~~java
long matched = result.getMatchedCount();
long modified = result.getModifiedCount();
~~~

Với `$inc` một lượng khác 0, một document match thường thực sự thay đổi. Nhưng một `$set` gán đúng giá trị đã có vẫn có thể cho `matched=1, modified=0`. Nếu nghiệp vụ hỏi “điều kiện được chấp nhận?” hãy xét **matched**; nếu hỏi “BSON đã đổi?” hãy xét **modified**.

Khi write concern không acknowledged hoặc lỗi mạng làm kết quả chưa rõ, không hứa counts luôn sẵn có và phản ánh chắc chắn trạng thái cuối.

### 6.3. updateMulti không tương đương một document CAS

`updateMulti` có thể tác động nhiều document. Mỗi document được ghi nguyên tử, nhưng **không có atomic all-or-nothing trên toàn bộ tập** ngoài transaction. Với reservation theo một ID, dùng `updateFirst`/update theo khóa duy nhất để không vô tình thay đổi nhiều sản phẩm.

## 7. findAndModify: trả post-image của đúng thao tác

Khi API cần biết tồn kho sau khi giữ chỗ:

~~~java
import org.springframework.data.mongodb.core.FindAndModifyOptions;

Query query = Query.query(
        Criteria.where("id").is(productId)
                .and("tenantId").is(authenticatedTenantId)
                .and("stock").gte(quantity));

InventoryProduct after = mongo.findAndModify(
        query,
        new Update().inc("stock", -quantity),
        FindAndModifyOptions.options().returnNew(true),
        InventoryProduct.class);
~~~

Với các biến `productId`, `authenticatedTenantId`, `quantity` hợp lệ, `after != null` là **post-image** của document được tìm và sửa trong cùng thao tác. Nếu không khớp, `after` là `null` theo trường hợp không upsert.

So sánh với:

~~~java
mongo.updateFirst(query, update, InventoryProduct.class);
InventoryProduct after = mongo.findById(
        productId, InventoryProduct.class);
~~~

Đây là **hai lệnh**; một writer khác có thể cập nhật document sau `updateFirst` và trước `findById`. Object đọc sau đó không nhất thiết là post-image của lần update ban đầu.

### 7.1. Before-image và after-image

`FindAndModifyOptions.options().returnNew(true)` yêu cầu object sau cập nhật; mặc định đường find-and-modify có thể trả object trước cập nhật. Hãy đặt tùy chọn rõ trong code và kiểm thử. Kết quả ở đây là entity hoặc null, **không phải `UpdateResult` với các count**.

### 7.2. findAndModify không bao phủ document khác

Sau lệnh find-and-modify, nếu service cập nhật thêm `orders` hoặc `shipments`, những thay đổi đó nằm ngoài thao tác nguyên tử vừa rồi. Nếu cả hai phải cùng commit hoặc rollback, phải đánh giá transaction hoặc thiết kế workflow nhất quán khác.

## 8. CAS theo status, phiên bản và những invariant khác

Không đủ khi filter chỉ có ID. Một trạng thái nghiệp vụ thường cần kiểm tra:

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-101",
    tenantId: "tenant-a",
    status: "PENDING",
    expectedPaymentAmount: 150000
  },
  {
    $set: { status: "PAID" }
  }
);
~~~

Đây là ví dụ có field `expectedPaymentAmount` trong document nguồn; schema order thực tế phải khai báo và validate trường này trước khi dùng. Điều kiện giữ nguyên vẹn thông tin kỳ vọng **tại thời điểm ghi**, không chỉ tại thời điểm app đọc trước đó.

Một điều kiện CAS có thể là:

| Điều kiện | Bảo vệ |
|---|---|
`status = PENDING` | Không chuyển lại state đã xử lý/hủy |
`version = expectedVersion` | Không ghi đè revision mới |
`stock >= requested` | Không để tồn kho âm |
`tenantId = authenticatedTenantId` | Không ghi vào tài nguyên tenant khác |
`requestId chưa xử lý` | Giới hạn áp dụng lại cùng command |

Không phải mọi điều kiện đều phù hợp để đưa vào một filter; một invariant liên quan nhiều document hoặc API ngoài cần thiết kế thêm. Nhưng điều kiện **có thể kiểm tra nguyên tử trên document đích** thì không nên tách thành một lần đọc Java riêng rồi mới update.

## 9. Optimistic locking với @Version

Spring Data MongoDB hỗ trợ `@Version`. Khi framework xử lý `save` entity đã đọc theo đường ghi có optimistic locking, phiên bản cũ có thể bị từ chối thay vì ghi đè state mới.

**VersionedInventory.java**

~~~java
package com.example.inventory;

import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "versioned_inventory")
public class VersionedInventory {
    @MongoId(FieldType.STRING)
    private String id;

    private String tenantId;
    private long stock;

    @Version
    private Long version;

    protected VersionedInventory() {}

    public VersionedInventory(
            String id, String tenantId, long stock) {
        this.id = id;
        this.tenantId = tenantId;
        this.stock = stock;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public long getStock() { return stock; }
    public Long getVersion() { return version; }
    public void setStock(long stock) { this.stock = stock; }
}
~~~

**VersionedInventoryRepository.java**

~~~java
package com.example.inventory;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface VersionedInventoryRepository
        extends MongoRepository<VersionedInventory, String> {
}
~~~

Hai bản sao của entity cùng revision:

~~~java
VersionedInventory first = repository.findById("v-101")
        .orElseThrow();
VersionedInventory second = repository.findById("v-101")
        .orElseThrow();

first.setStock(4);
repository.save(first);

second.setStock(4);
// Bản second đã stale: save có thể bị từ chối.
repository.save(second);
~~~

`repository` là bean `VersionedInventoryRepository`. Khi update đầu tăng version và write concern có xác nhận, save sau dùng version cũ sẽ không khớp và có thể ném `OptimisticLockingFailureException`.

### 9.1. @Version không thay invariant stock

Version giúp phát hiện rằng dữ liệu đã thay đổi **từ lần đọc trước**. Nó không tự biết “stock phải >= 0”, “chỉ trừ khi đơn còn ACTIVE” hoặc “không xử lý payment hai lần”. Cần:

1. Validate invariant trước thao tác.
2. Khi save stale thất bại, không báo thành công.
3. Nếu retry, đọc lại và **tính lại quyết định nghiệp vụ** có giới hạn.
4. Không retry bằng cách ép version hoặc ghi đè bản ghi stale.

### 9.2. Không giả định mọi đường update đều tôn trọng @Version

Custom `MongoTemplate` updates, repository `@Update`, bulk writes hoặc raw Java Driver có thể có semantics khác repository save. Với trường hợp cần CAS version tường minh:

~~~javascript
db.versioned_inventory.updateOne(
  {
    _id: "v-101",
    tenantId: "tenant-a",
    version: 7,
    stock: { $gte: 3 }
  },
  {
    $inc: {
      stock: -3,
      version: 1
    }
  }
);
~~~

Ở đây version trong filter và increment nằm trong **một** document write. Với `MongoTemplate.Update` trên entity `@Version`, Spring Data có thể tự tăng version ở một số đường update nếu version chưa có trong update; phải xác minh phiên bản và **không tăng version hai lần**.

### 9.3. Optimistic locking cần acknowledged write concern

Để nhận biết match count bằng 0 và báo stale object, ứng dụng cần kết quả ghi đã được xác nhận. Write concern không acknowledged có thể làm mất khả năng phát hiện lỗi optimistic locking một cách đáng tin. Đừng tắt acknowledgement chỉ để tăng throughput rồi vẫn cam kết chặn mọi lost update.

## 10. Idempotency: atomic $inc không chống phát lại request

`$inc` trên một document là nguyên tử, nhưng khi client retry một **ý định nghiệp vụ** như “giữ chỗ 3 sản phẩm”, lệnh có thể bị áp dụng lần nữa.

~~~text
Client -> reserve 3
Server ghi stock 10 -> 7
Response mất trên mạng
Client retry như lệnh mới
Server ghi stock 7 -> 4
~~~

Từng lần trừ đều nguyên tử, nhưng một ý định đã làm giảm tồn kho **hai lần**. Vì vậy cần phân biệt:

- **Atomicity:** một lệnh không ghi nửa chừng.
- **Idempotency:** cùng một ý định được phát lại không tạo hiệu ứng nghiệp vụ lặp.
- **Retryable writes:** driver có cơ chế retry một số thao tác theo điều kiện hỗ trợ, không phải lời hứa mọi HTTP retry là cùng một command.

### 10.1. Đặt dấu command trong cùng document

Với volume command **được giới hạn**, một cách minh họa là lưu request ID đã áp dụng vào `appliedCommandIds`:

~~~javascript
db.inventory_products.updateOne(
  {
    _id: "p-101",
    tenantId: "tenant-a",
    status: "ACTIVE",
    stock_qty: { $gte: 3 },
    appliedCommandIds: { $ne: "reserve-101" }
  },
  {
    $inc: { stock_qty: -3 },
    $addToSet: { appliedCommandIds: "reserve-101" }
  }
);
~~~

Điều kiện “chưa dùng command” và hai thay đổi được thực hiện nguyên tử trên **một document**. Nếu command ID được gửi lại đồng thời, sau khi một lệnh thành công, lệnh còn lại không khớp `appliedCommandIds: { $ne: ... }`.

### 10.2. Java method reserveOnce

Phương thức sau được **bổ sung vào `StockReservationService`** ở mục 6, dùng lại field `mongo` và các import:

~~~java
public boolean reserveOnce(
        String authenticatedTenantId,
        String productId,
        long quantity,
        String commandId) {
    if (authenticatedTenantId == null
            || authenticatedTenantId.isBlank()
            || productId == null || productId.isBlank()
            || commandId == null || commandId.isBlank()
            || quantity <= 0) {
        throw new IllegalArgumentException("Request không hợp lệ");
    }

    Query query = Query.query(
            Criteria.where("id").is(productId)
                    .and("tenantId").is(authenticatedTenantId)
                    .and("status").is("ACTIVE")
                    .and("stock").gte(quantity)
                    .and("appliedCommandIds").ne(commandId));

    Update update = new Update()
            .inc("stock", -quantity)
            .addToSet("appliedCommandIds", commandId);

    UpdateResult result = mongo.updateFirst(
            query, update, InventoryProduct.class);
    return result.getMatchedCount() == 1;
}
~~~

Ở đây kết quả `false` có thể do duplicate command, không đủ tồn kho, sai tenant hoặc status. Nếu API phải **trả lại response gốc khi replay**, cần ghi kết quả theo command ID hoặc thiết kế idempotency record phù hợp. Một boolean không diễn đạt hết các trạng thái này.

### 10.3. Không giữ vô hạn mọi command ID trong một document

Mảng `appliedCommandIds` tăng vô hạn khiến document lớn, tăng chi phí ghi và có thể chạm giới hạn BSON **16 MiB**. Với hệ thống có nhiều giao dịch, nên cân nhắc:

- Collection idempotency riêng, unique key và retention rõ;
- Transaction nếu idempotency record và document tài nguyên cần cùng commit;
- Event sequence/revision ổn định và checkpoint đối soát;
- Bounded history có điều kiện xóa phù hợp với hợp đồng retry.

Không xóa dấu command quá sớm khi client vẫn có thể retry. Idempotency là **quyết định nghiệp vụ** về thời gian lưu và phạm vi key.

## 11. Hai lệnh liên tiếp trên cùng document vẫn có trạng thái trung gian

Một ví dụ nguy hiểm:

~~~java
mongo.updateFirst(
        Query.query(Criteria.where("id").is("p-101")),
        new Update().set("status", "RESERVED"),
        InventoryProduct.class);

// Process có thể crash hoặc writer khác chen vào tại đây.

mongo.updateFirst(
        Query.query(Criteria.where("id").is("p-101")),
        new Update().inc("stock", -3),
        InventoryProduct.class);
~~~

Timeline có thể xảy ra:

~~~text
T0: status = ACTIVE,   stock = 5
T1: update #1 chạy -> status = RESERVED, stock = 5
T2: process dừng đột ngột
T3: update #2 chưa chạy
~~~

Hai lệnh cùng sửa ID nhưng **không tự thành một transaction**. Nếu hai field thuộc cùng document, hãy gộp:

~~~javascript
db.inventory_products.updateOne(
  {
    _id: "p-101",
    tenantId: "tenant-a",
    status: "ACTIVE",
    stock_qty: { $gte: 3 }
  },
  {
    $set: { status: "RESERVED" },
    $inc: { stock_qty: -3 }
  }
);
~~~

Lệnh mới giữ invariant trong một thao tác. Tuy nhiên, `status = RESERVED` trên một **sản phẩm dùng chung** không phải lúc nào là model đúng cho nhiều booking; có thể cần entity reservation riêng. Tính nguyên tử không thay thế việc thiết kế aggregate/domain hợp lý.

### 11.1. Cùng Java method hoặc cùng connection không đủ

Hai lời gọi dùng cùng `MongoTemplate`, cùng thread, cùng client session thông thường hoặc cùng HTTP request **không mặc định** có transaction. Một method trong Spring Service chỉ là ranh giới code, không phải ranh giới atomicity MongoDB.

### 11.2. try/catch không rollback lệnh trước

~~~java
try {
    firstMongoWrite();
    secondMongoWrite();
} catch (RuntimeException exception) {
    // Catch không tự rollback firstMongoWrite().
}
~~~

Muốn rollback phải có transaction thực sự, hoặc mô hình trạng thái trung gian/compensating action và cơ chế retry/đối soát. Một thao tác bù cũng có thể thất bại, nên nó không đồng nghĩa transaction ACID.

## 12. updateMany và BulkOperations: không có atomicity toàn tập

Một lệnh:

~~~javascript
db.inventory_products.updateMany(
  { tenantId: "tenant-a", status: "ACTIVE" },
  { $set: { status: "INACTIVE" } }
);
~~~

có thể sửa nhiều document. **Mỗi document được cập nhật nguyên tử**, nhưng không có bảo đảm all-or-nothing cho **toàn bộ tập document** nếu không đặt các lệnh vào transaction. Reader có thể thấy một phần document đã đổi và phần khác chưa đổi.

### 12.1. BulkOperations ORDERED không phải transaction

~~~java
BulkOperations bulk = mongo.bulkOps(
        BulkOperations.BulkMode.ORDERED,
        InventoryProduct.class);

bulk.updateOne(queryA, updateA);
bulk.updateOne(queryB, updateB);
bulk.execute();
~~~

Đây là fragment minh họa trong service, với biến `queryA`/`queryB` và `updateA`/`updateB` đã được tạo, cần import `org.springframework.data.mongodb.core.BulkOperations`.

`BulkMode.ORDERED` liên quan **thứ tự xử lý và dừng khi lỗi**; nó không tự rollback các thao tác thành công trước đó. `BulkMode.UNORDERED` có thể tiếp tục thử các write độc lập dù một write lỗi; nó cũng không tạo transaction.

Ví dụ:

~~~text
Insert A => thành công
Insert B => duplicate key
Update C => tùy ordered/unordered có thể chưa được thử hoặc đã chạy
~~~

Nếu ứng dụng retry toàn bộ batch gồm `$inc`, thao tác A hoặc C đã thành công có thể bị áp dụng hai lần. Cần idempotency từng operation, tracking ID và đối soát.

### 12.2. MatchedCount không bằng số request đầu vào

Một `updateMany` có thể match 100 document và modify 95 document. Một bulk có 10 write models có thể chỉ match 8 document. Các con số này khác **số API calls**, **số lệnh**, **số entity đầu vào** và **số nghiệp vụ hoàn thành**. Đọc `UpdateResult`/`BulkWriteResult` đúng semantics.

### 12.3. Không nhầm bulk với transaction xuyên collection

Ngay cả khi một lệnh bulk được đưa xuống driver thành ít network round trips, **bớt round trip không biến nó thành all-or-nothing**. Chỉ thiết kế transaction thực sự mới cung cấp ranh giới commit/rollback cho những document tham gia.

## 13. Unique index và upsert dưới cạnh tranh

Hai request cùng muốn tạo đơn có khóa nghiệp vụ (`tenantId`, `externalOrderId`):

~~~java
if (repository.findByExternalOrderId(externalId).isEmpty()) {
    repository.save(newOrder);
}
~~~

Đây là kiểm tra trước ghi, không bảo vệ khỏi race. Index trên MongoDB mới là nguồn bảo đảm:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { unique: true, name: "uq_order_tenant_external_id" }
);
~~~

### 13.1. Upsert không tự thay unique index

~~~javascript
db.orders.updateOne(
  { tenantId: "tenant-a", externalOrderId: "ERP-101" },
  {
    $setOnInsert: {
      status: "PENDING",
      createdBy: "erp-sync"
    }
  },
  { upsert: true }
);
~~~

Nếu thiếu unique index đúng business key, các upsert đồng thời có thể tạo document trùng nhau. Unique index sẽ ngăn duplicate key ở server, nhưng code phải xử lý duplicate-key exception và đối soát trạng thái sau lỗi, không chỉ dựa vào pre-check.

### 13.2. Idempotent upsert cần xác định ownership của field

Nếu một sự kiện nguồn cũ đến sau sự kiện mới, upsert với `$set` không có revision guard có thể ghi đè dữ liệu mới. Tính nguyên tử của một upsert không tự đảm bảo **thứ tự sự kiện**, **đúng version** hay **không lặp side effect**.

Khi import từ hệ thống ngoài, nên có:

1. Khóa nghiệp vụ ổn định và unique index.
2. Revision/timestamp nguồn đáng tin nếu event có thể out-of-order.
3. Quy tắc field ownership (nguồn ngoài được sửa field nào?).
4. ID của event/command để xử lý replay.
5. Cách phân loại duplicate key và kết quả chưa rõ sau timeout.

## 14. Ví dụ chuyển tiền: hai document cần invariant xuyên document

Giả sử:

~~~text
Account A = 100.000 VND
Account B = 20.000 VND
Chuyển 30.000 VND từ A sang B

Kết quả mong muốn:
  A = 70.000
  B = 50.000
  Tổng = 120.000
~~~

Nếu dùng hai update riêng:

~~~javascript
db.money_accounts.updateOne(
  { _id: "A", balance_vnd: { $gte: 30000 } },
  { $inc: { balance_vnd: -30000 } }
);

db.money_accounts.updateOne(
  { _id: "B" },
  { $inc: { balance_vnd: 30000 } }
);
~~~

Một lỗi sau debit A nhưng trước credit B khiến **mất cân bằng**. Mỗi document update đã nguyên tử nhưng invariant “tổng số dư không đổi” trải qua **hai document**.

### 14.1. Entity account

**MoneyAccount.java**

~~~java
package com.example.finance;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "money_accounts")
public class MoneyAccount {
    @MongoId(FieldType.STRING)
    private String id;
    private String tenantId;

    @Field("balance_vnd")
    private long balanceVnd;

    protected MoneyAccount() {}

    public MoneyAccount(
            String id, String tenantId, long balanceVnd) {
        this.id = id;
        this.tenantId = tenantId;
        this.balanceVnd = balanceVnd;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public long getBalanceVnd() { return balanceVnd; }
}
~~~

### 14.2. Transaction manager

Trong Spring Data MongoDB, có thể cấu hình `MongoTransactionManager`:

**MongoTransactionConfig.java**

~~~java
package com.example.finance;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfig {
    @Bean
    public MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory databaseFactory) {
        return new MongoTransactionManager(databaseFactory);
    }
}
~~~

MongoDB transaction cần **replica set hoặc sharded cluster có hỗ trợ**, session và transaction manager được cấu hình đúng. MongoDB standalone không phải môi trường thử multi-document transaction phù hợp. Phải đảm bảo những thao tác liên quan đều tham gia cùng transaction.

### 14.3. Service chuyển tiền có transaction

**MoneyTransferService.java**

~~~java
package com.example.finance;

import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MoneyTransferService {
    private final MongoTemplate mongo;

    public MoneyTransferService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    @Transactional
    public void transfer(
            String authenticatedTenantId,
            String fromId,
            String toId,
            long amountVnd) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || fromId == null || fromId.isBlank()
                || toId == null || toId.isBlank()
                || fromId.equals(toId)
                || amountVnd <= 0) {
            throw new IllegalArgumentException("Chuyển tiền không hợp lệ");
        }

        Query debitQuery = Query.query(
                Criteria.where("id").is(fromId)
                        .and("tenantId").is(authenticatedTenantId)
                        .and("balanceVnd").gte(amountVnd));
        UpdateResult debit = mongo.updateFirst(
                debitQuery,
                new Update().inc("balanceVnd", -amountVnd),
                MoneyAccount.class);

        if (debit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                    "Tài khoản nguồn không hợp lệ hoặc thiếu số dư");
        }

        Query creditQuery = Query.query(
                Criteria.where("id").is(toId)
                        .and("tenantId").is(authenticatedTenantId));
        UpdateResult credit = mongo.updateFirst(
                creditQuery,
                new Update().inc("balanceVnd", amountVnd),
                MoneyAccount.class);

        if (credit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                    "Không có tài khoản nhận tiền");
        }
        // Spring commit transaction khi method kết thúc bình thường.
    }
}
~~~

Trong một **transaction MongoDB thực sự hoạt động**, nếu credit không match và phương thức ném unchecked exception, transaction có thể được abort và debit rollback. Khi commit thành công, cả hai thay đổi cùng thuộc một ranh giới giao dịch.

**Ví dụ này phục vụ học atomicity/transaction, không đủ làm hệ thống chuyển tiền production.** Còn cần transfer ID/idempotency, ledger bất biến, xác thực quyền, chống overflow, currency, audit, chống fraud và chính sách xử lý transaction retry/unknown commit outcome.

## 15. Điều kiện để @Transactional thực sự bảo vệ dữ liệu

`@Transactional` là annotation Spring, không phải phép màu ở database.

Các điều kiện cần kiểm tra:

1. Có `MongoTransactionManager` phù hợp, không bị một transaction manager khác vô tình được chọn.
2. MongoDB topology hỗ trợ transaction (replica set/sharded cluster tương thích).
3. Các thao tác `MongoTemplate`/repository tham gia cùng session/transaction.
4. Transaction được kích hoạt qua Spring proxy/interceptor; **self-invocation** thường không áp dụng proxy transaction mặc định.
5. Lỗi phải dẫn đến rollback theo rule cấu hình. Với unchecked exception trong ví dụ, rollback là hành vi mặc định thường gặp.
6. Transaction không được kéo quá lâu và cần xử lý write conflicts, transient errors, unknown commit results.

### 15.1. Transaction không rollback hệ thống ngoài

Nếu service gửi email hoặc gọi API thanh toán ở giữa transaction, MongoDB rollback không thể thu hồi email hay request HTTP đã gửi. Cách phổ biến là **transactional outbox**:

~~~mermaid
flowchart LR
    A["Business transaction"] --> B["Ghi Order"]
    A --> C["Ghi Outbox event"]
    B --> D["Commit MongoDB transaction"]
    C --> D
    D --> E["Worker đọc outbox"]
    E --> F["Publish với retry và dedup"]
    F --> G["Consumer idempotent"]
~~~

Ngay cả outbox không có nghĩa message được gửi đúng một lần ở mọi hệ thống. Worker có thể publish rồi chết trước khi mark delivered; consumer cần idempotency/deduplication.

### 15.2. Transaction không tự idempotent

Một transfer request có thể **commit thành công** nhưng response HTTP bị mất. Client retry tạo một transaction mới và chuyển tiền **lần nữa** nếu không có transfer ID bảo vệ.

~~~text
transaction = all-or-nothing cho những MongoDB operations tham gia
idempotency = một ý định nghiệp vụ không bị áp dụng hai lần
~~~

Cần phân biệt cả hai và thường kết hợp chúng.

### 15.3. Transaction có chi phí

Transaction nhiều document có thể tăng latency, contention, memory và khả năng gặp write conflict. Một số thao tác quản trị, tạo collection/index hoặc aggregation stage có hạn chế trong transaction. Không đưa mọi thao tác MongoDB vào transaction vô điều kiện chỉ để cảm thấy an toàn.

Nếu invariant nằm hoàn toàn trên một document, **một conditional update** thường đơn giản và có ranh giới lỗi dễ kiểm soát hơn.

## 16. Write concern, read concern và unknown outcome

Phân biệt:

- **Atomicity:** một document không bị ghi nửa chừng.
- **Write concern:** mức độ xác nhận/durability mà client yêu cầu.
- **Read concern:** mức dữ liệu mà một lần đọc được phép quan sát.
- **Read preference:** nguồn đọc (primary/secondary...) và khả năng gặp replication lag.

Một lệnh update có điều kiện có thể hoàn tất ở server nhưng client không nhận được response:

~~~text
Client gửi updateOne($inc)
MongoDB thực hiện update
Kết nối mạng mất trước acknowledgement
Client nhìn thấy timeout
Server có thể đã đổi dữ liệu
~~~

**Timeout không chứng minh “lệnh chưa chạy”.** Retry toàn bộ nghiệp vụ ngay sau timeout, đặc biệt với `$inc`, có thể áp dụng hiệu ứng hai lần.

### 16.1. Retryable writes và application-level retry

MongoDB Driver hỗ trợ retryable writes cho **một số loại lệnh** trên topology/phiên bản phù hợp. Nhưng:

- HTTP handler gọi lại `updateFirst` như **một thao tác mới** không mặc định được coi là retry của driver cho thao tác cũ.
- Một chuỗi debit → credit không trở thành một retryable write duy nhất.
- Một batch nhiều document hoặc transaction có quy tắc lỗi/retry riêng.
- Nếu kết quả commit transaction không rõ, việc retry cần tuân theo quy trình transaction và idempotency, không phát lại blind toàn bộ transfer.

Với nghiệp vụ tài chính hoặc reservation, hãy dùng **command ID và trạng thái bền vững** để phân biệt đã xử lý, chưa xử lý hoặc cần đối soát.

### 16.2. Read-after-write và secondary lag

Ngay cả sau một update thành công, một reader sử dụng secondary có thể thấy dữ liệu cũ khi replication chưa theo kịp. Atomicity không có nghĩa mọi replica cập nhật cùng một thời điểm. Cần định nghĩa consistency contract cho API và cấu hình read/write concern/session/read preference phù hợp.

### 16.3. Hai lần đọc không chứng minh kết quả của một write

~~~java
long before = repository.count();
performUpdate();
long after = repository.count();
~~~

Hiệu số `after - before` không phải modifiedCount; update trạng thái không đổi tổng số document, và tác vụ đồng thời có thể chen vào giữa các lần đọc. Dùng `UpdateResult` hoặc `DeleteResult` để đo tác động của chính lệnh ghi và dùng readback/đối soát cho những trường hợp outcome chưa rõ.

## 17. Kiểm thử tích hợp conditional update trên MongoDB thật

Mock repository hoặc `MongoTemplate` có thể chứng minh service gọi `updateFirst`, nhưng không chứng minh hai writers cạnh tranh và MongoDB **kiểm tra lại filter khi ghi**. Cần integration test có MongoDB thực, ví dụ Testcontainers. Trong Spring Boot 3.x, `@DataMongoTest` cấu hình test slice nhưng **không tự chạy MongoDB server**.

### 17.1. Hai request cùng giữ 3 từ stock=5

**StockReservationIntegrationTest.java**

~~~java
package com.example.inventory;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

@DataMongoTest
@Import(StockReservationService.class)
class StockReservationIntegrationTest {
    @Autowired MongoTemplate mongo;
    @Autowired StockReservationService stock;

    private InventoryProduct saved() {
        return mongo.findById("p-101", InventoryProduct.class);
    }

    @BeforeEach
    void prepare() {
        // Chỉ thực hiện trên database test cô lập.
        mongo.remove(new Query(), InventoryProduct.class);
        mongo.insert(new InventoryProduct(
                "p-101", "tenant-a", "ACTIVE", 5));
    }

    @Test
    void secondRequestFailsWhenStockIsInsufficient() {
        assertThat(stock.reserve("tenant-a", "p-101", 3)).isTrue();
        assertThat(stock.reserve("tenant-a", "p-101", 3)).isFalse();
        assertThat(saved().getStock()).isEqualTo(2L);
    }

    @Test
    void concurrentRequestsCannotBothReserveThree() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        try {
            Future<Boolean> a = pool.submit(() -> {
                ready.countDown();
                start.await();
                return stock.reserve("tenant-a", "p-101", 3);
            });
            Future<Boolean> b = pool.submit(() -> {
                ready.countDown();
                start.await();
                return stock.reserve("tenant-a", "p-101", 3);
            });

            assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue();
            start.countDown();

            boolean aSucceeded = a.get(10, TimeUnit.SECONDS);
            boolean bSucceeded = b.get(10, TimeUnit.SECONDS);

            assertThat(aSucceeded ^ bSucceeded).isTrue();
            assertThat(saved().getStock()).isEqualTo(2L);
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }

    @Test
    void wrongTenantOrInactiveStatusCannotChangeStock() {
        assertThat(stock.reserve("tenant-b", "p-101", 1)).isFalse();
        assertThat(saved().getStock()).isEqualTo(5L);

        mongo.updateFirst(
                Query.query(Criteria.where("id").is("p-101")),
                new Update().set("status", "INACTIVE"),
                InventoryProduct.class);

        assertThat(stock.reserve("tenant-a", "p-101", 1)).isFalse();
        assertThat(saved().getStock()).isEqualTo(5L);
    }

    @Test
    void repeatedCommandDoesNotDeductTwiceEvenWithEnoughStock() {
        assertThat(stock.reserveOnce(
                "tenant-a", "p-101", 1, "cmd-101")).isTrue();

        // Còn 4 đơn vị, đủ để trừ thêm 1, nhưng command đã được lưu.
        assertThat(stock.reserveOnce(
                "tenant-a", "p-101", 1, "cmd-101")).isFalse();

        assertThat(saved().getStock()).isEqualTo(4L);
        assertThat(saved().getAppliedCommandIds())
                .containsExactly("cmd-101");
    }
}
~~~

**Vì sao kiểm tra bằng XOR?** Test không kiểm soát request A hay B chạy trước; nó chỉ đòi hỏi **đúng một request** có `matchedCount = 1`, tồn kho cuối là 2 và không âm. Assert một thread cụ thể phải thắng sẽ làm test phụ thuộc scheduler và dễ flaky.

**Vì sao test replay dùng quantity=1?** Nếu vẫn dùng quantity=3 sau khi stock còn 2, request thứ hai cũng không khớp do **không đủ tồn**; như vậy chưa chứng minh điều kiện command ID hoạt động. Dùng quantity=1 để lần gọi thứ hai **vẫn đủ hàng**, chỉ bị loại bởi ID đã áp dụng.

### 17.2. Verify mapping Java → BSON

Sau khi insert `InventoryProduct`, có thể đọc raw document:

~~~java
org.bson.Document raw = mongo.getCollection("inventory_products")
        .find(new org.bson.Document("_id", "p-101"))
        .first();

assertThat(raw).isNotNull();
assertThat(raw.containsKey("stock_qty")).isTrue();
assertThat(raw.containsKey("stock")).isFalse();
~~~

`Query`/`Update` typed của Spring Data phải tham chiếu property Java và được map đúng thành `stock_qty` ở server. Khi cần xác minh chính xác filter, dùng `CommandListener` của MongoDB Java Driver trong test và kiểm tra BSON command `update`.

### 17.3. Không dùng database test chung với production

`mongo.remove(new Query(), InventoryProduct.class)` xóa **toàn bộ document** thuộc collection. Chỉ làm vậy trong database/collection test được cô lập; với parallel test cần isolation rõ. **Không copy @BeforeEach này vào một environment dùng dữ liệu thật.**

## 18. Kiểm thử @Version và phân biệt update không thay đổi

### 18.1. Test optimistic locking

Một class integration test có thể dùng repository `VersionedInventoryRepository` trên MongoDB test:

~~~java
package com.example.inventory;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.dao.OptimisticLockingFailureException;

@DataMongoTest
class VersionedInventoryTest {
    @Autowired VersionedInventoryRepository repository;

    @BeforeEach
    void prepare() {
        // Database test được cô lập.
        repository.deleteAll();
        repository.save(new VersionedInventory(
                "v-101", "tenant-a", 5));
    }

    @Test
    void staleSaveIsRejected() {
        VersionedInventory a =
                repository.findById("v-101").orElseThrow();
        VersionedInventory b =
                repository.findById("v-101").orElseThrow();

        assertThat(a.getVersion()).isNotNull();
        assertThat(b.getVersion()).isEqualTo(a.getVersion());

        a.setStock(4);
        repository.save(a);
        b.setStock(4);

        assertThatThrownBy(() -> repository.save(b))
                .isInstanceOf(OptimisticLockingFailureException.class);
        assertThat(repository.findById("v-101")
                .orElseThrow().getStock()).isEqualTo(4L);
    }
}
~~~

Test cần **acknowledged write concern**. Không suy rộng từ test này rằng mọi phép update viết bằng raw driver hoặc `BulkOperations` đều tự động kiểm tra `@Version`.

### 18.2. Test matchedCount và modifiedCount khi $set không đổi

~~~java
UpdateResult noOp = mongo.updateFirst(
        Query.query(Criteria.where("id").is("p-101")
                .and("tenantId").is("tenant-a")),
        new Update().set("status", "ACTIVE"),
        InventoryProduct.class);

assertThat(noOp.getMatchedCount()).isEqualTo(1L);
assertThat(noOp.getModifiedCount()).isEqualTo(0L);
~~~

Đoạn này dùng môi trường test đã seed product trạng thái ACTIVE, trong scope có `mongo` và import `UpdateResult`/`Query`/`Criteria`/`Update`. Vì không có auditing/version field bổ sung trên entity `InventoryProduct`, đặt lại cùng status có thể là no-op. Nếu đường ghi/version framework tự sửa field metadata khác, cần điều chỉnh test theo dữ liệu/semantics thực tế.

### 18.3. Một phép đọc sau update chỉ để giải thích lỗi

Khi `reserve` trả false, tầng API có thể đọc lại trạng thái để phân biệt hết hàng/INACTIVE/không tồn tại. Nhưng kết quả đọc đó có thể bị thay đổi bởi writer khác sau update; nó là thông tin **chẩn đoán tại một thời điểm khác**, không phải bằng chứng nguyên tử về lý do lệnh update ban đầu không match.

Nếu cần xác định trạng thái thất bại chính xác theo hợp đồng chặt chẽ, hãy thiết kế protocol/state machine/transaction phù hợp, không chỉ gắn một câu lệnh `findById` vào sau.

## 19. Kiểm thử transaction và lỗi giữa chừng

### 19.1. Không test transaction trên standalone rồi giả định thành công

Một bài test rollback transaction cần MongoDB **replica set** hoặc topology tương thích với multi-document transaction, cấu hình `MongoTransactionManager`, cùng `MongoTemplate`/repository tham gia session:

~~~text
Given:
  A.balanceVnd = 100000
  B.balanceVnd = 20000

When:
  MoneyTransferService.transfer(tenant-a, A, B, 30000)

Then:
  A.balanceVnd = 70000
  B.balanceVnd = 50000
~~~

Kịch bản lỗi:

~~~text
Given:
  A.balanceVnd = 100000
  Tài khoản B không tồn tại

When:
  transfer(A -> B, 30000) ném unchecked exception

Then:
  A.balanceVnd vẫn = 100000
  không có debit chưa rollback
~~~

Nếu chạy trên standalone và transaction không được hỗ trợ, đó là **lỗi môi trường**; không bỏ `@Transactional` rồi tuyên bố test chứng minh atomicity đa document.

### 19.2. Kiểm thử tính đúng đắn trước khi kiểm thử throughput

Một chuyển tiền có thể nhanh và đồng thời vẫn sai nếu chỉ debit mà không credit sau lỗi. Hãy kiểm thử:

1. Commit thành công làm thay đổi đủ hai tài khoản.
2. Mất tài khoản đích làm transaction rollback debit.
3. Chuyển cùng một tài khoản hoặc amount không hợp lệ bị từ chối.
4. Thiếu số dư không được làm số dư âm.
5. Hai transfer cạnh tranh cùng nguồn có chính sách write conflict/retry.
6. Transfer ID trùng không tạo transfer thứ hai khi retry.
7. Unknown commit result được đối soát trước khi phát lại.

Đối với mục 6–7, ví dụ `MoneyTransferService` ở trên **chưa triển khai idempotency/ledger**, nên phải bổ sung kiến trúc/test trước khi dùng cho giao dịch thật.

### 19.3. Hai request hay hai server?

Test sử dụng hai threads trong một JVM là điểm bắt đầu, nhưng chưa đủ cho:

- Nhiều application replicas/pods;
- Failover/replication lag;
- Timeout sau ghi nhưng trước acknowledgement;
- Transaction commit không rõ;
- Application crash giữa các thao tác;
- Event replay sau nhiều ngày;
- Thay đổi dữ liệu bởi service khác không dùng chung convention.

Mỗi loại lỗi cần một chiến lược kiểm chứng riêng thay vì quy mọi tình huống thành “đã test concurrent”.

## 20. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Hướng sửa |
|---|---|---|
Cho rằng MongoDB atomic nên read → save an toàn | Lost update | CAS hoặc `@Version` |
Đọc stock trước rồi `$inc` không filter đủ hàng | Oversell/stock âm | `stock >= quantity` trong filter |
`synchronized` trong một pod được coi là distributed lock | Race qua nhiều JVM | Đặt điều kiện tại MongoDB |
Chỉ filter theo ID, bỏ tenant | Sửa dữ liệu tenant khác | Tenant từ auth context trong query ghi |
Hai update trên cùng document được hiểu như một transaction | Trạng thái trung gian | Gộp thay đổi vào một update |
Cho rằng `updateMany` nguyên tử toàn bộ collection | Thấy partial state | Transaction nếu cần all-or-nothing |
Cho rằng `BulkMode.ORDERED` rollback các write trước lỗi | Partial success | Transaction/idempotency/reconcile |
`matched=0` luôn bị coi là not found | Báo 404 sai khi thiếu stock/status đổi | Phân loại theo contract |
`matched=1` nghĩa là toàn bộ workflow thành công | Email/order/shipment có thể chưa xong | Tách technical và business result |
`save` nguyên entity chưa có version, dựa trên state cũ | Ghi đè dữ liệu mới | Optimistic locking/partial update |
Giả định mọi custom update tự kiểm tra `@Version` | Stale write lọt qua | Version CAS rõ ràng |
Retry lệnh `$inc` như một request mới sau timeout | Trừ/cộng hai lần | Idempotency key và đối soát |
Mảng command ID tăng vô hạn | Tốn tài nguyên, đạt 16 MiB | Idempotency collection/retention |
`existsBy...` được coi là uniqueness | Race insert duplicate | Unique index |
Upsert được coi là chống duplicate dù thiếu unique | Có thể tạo hai document | Unique index theo business key |
Chỉ thêm `@Transactional` không có manager/topology | Rollback không hoạt động | Cấu hình session/manager và test replica set |
Gửi email trong transaction rồi kỳ vọng rollback email | External side effect vẫn tồn tại | Outbox/consumer idempotent |
Gặp timeout rồi chắc chắn server chưa ghi | Retry gây duplicate | Phân biệt unknown outcome |
Đọc secondary và thấy state cũ thì nghĩ write thất bại | Kết luận sai | Cấu hình read/write concerns |
Chỉ test Mockito mock | Không chứng minh CAS/concurrency MongoDB | Integration test thực |

## 21. Bài tập vận dụng

**Bài 1 — Ba phạm vi atomicity.** So sánh một `updateOne` thay 3 field trên một document, hai lần `updateOne` trên cùng document, và một `updateMany` trên 100 document. Chỉ ra trạng thái trung gian có thể quan sát ở đâu.

**Bài 2 — Lost update.** Seed stock=5, tạo hai snapshots cùng stock=5 và dùng read-modify-save không version. Viết timeline cho kết quả cả hai request báo thành công nhưng stock chỉ còn 2.

**Bài 3 — Atomic stock reservation.** Dùng `MongoTemplate.updateFirst` với filter tenant, status, stock. Hai request cùng trừ 3 từ 5 phải có đúng một lần `matched=1`, stock cuối không âm.

**Bài 4 — findAndModify.** Trả post-image sau khi cập nhật. So sánh với update rồi find và nêu interleaving làm object đọc sau không còn là post-image chính xác của lệnh đầu.

**Bài 5 — Status CAS.** Chỉ cho order chuyển `PENDING → PAID` một lần. Cho request hủy cạnh tranh; phân tích matched=0 và cách trả 409/404/idempotent replay theo contract.

**Bài 6 — Optimistic locking.** Tạo entity `@Version Long`, đọc hai bản sao, save lần lượt và xác minh stale save thất bại; đề xuất retry có giới hạn.

**Bài 7 — Idempotent command.** Dùng `$addToSet` + `$inc` trong cùng một update và điều kiện `appliedCommandIds` chưa chứa command ID. Chứng minh retry khi stock vẫn đủ không trừ lần hai.

**Bài 8 — Kích thước idempotency history.** Phân tích số command ID có thể tích lũy trong một document. Thiết kế chuyển sang collection riêng với unique key, retention và transaction khi cần.

**Bài 9 — Multiple updates.** Tạo method gọi set status rồi inc stock; chèn exception có chủ đích giữa hai lệnh. Đo trạng thái còn lại; sau đó gộp hai field vào một update.

**Bài 10 — Bulk partial success.** Tạo bulk gồm insert A, insert B trùng unique key, update C. So sánh ORDERED và UNORDERED rồi thiết kế retry theo operation ID.

**Bài 11 — Transaction chuyển tiền.** Cấu hình replica set, `MongoTransactionManager` và `@Transactional`. Test successful transfer, insufficient funds và missing destination rollback.

**Bài 12 — Unknown commit result.** Mô tả response mất sau khi server ghi. Thiết kế transfer ID/idempotency record để request retry không chuyển tiền lần hai.

**Bài 13 — Outbox.** Viết sơ đồ cập nhật Order và Outbox trong một transaction; worker gửi event có retry. Nêu lý do consumer vẫn cần dedup.

**Bài 14 — Read consistency.** Trên replica set test, so sánh đọc sau ghi từ primary/secondary theo read preference. Giải thích atomicity khác replication freshness.

**Bài 15 — Load test.** Seed stock=50; gửi 100 request đồng thời, mỗi request trừ 1. Assert đúng 50 request thành công, stock cuối 0. Đo contention/latency và kiểm tra mọi đường ghi khác cũng giữ invariant.

## 22. Ghi nhớ

**Một lệnh ghi trên một document của MongoDB có tính nguyên tử ở cấp document.** Nếu invariant nằm trong một document, hãy gộp **điều kiện trong filter** và **thay đổi trong cùng update**: `stock >= quantity` cùng `$inc` là ví dụ điển hình. `findAndModify` giúp nhận pre/post-image của cùng thao tác; `@Version` giúp phát hiện entity stale trên các đường ghi có optimistic locking.

**Hai hoặc nhiều lệnh liên tiếp — kể cả cùng document, cùng method Java, cùng thread hoặc cùng HTTP request — không tự tạo transaction.** `updateMany` và bulk writes vẫn có thể cho kết quả thành công một phần vì mỗi document được cập nhật nguyên tử riêng. Nếu invariant phải bảo vệ **nhiều document**, dùng MongoDB transaction được cấu hình đúng hoặc một quy trình eventual consistency có state machine/compensation/outbox/đối soát rõ ràng.

Cuối cùng, **atomicity không thay idempotency, uniqueness, authorization, acknowledgement hay retry policy**. Một update thành công không chứng minh toàn bộ nghiệp vụ đã hoàn tất; timeout không chứng minh server chưa ghi. Hãy đọc `matchedCount`/exception theo đúng semantics, tránh retry `$inc` mù quáng và xác minh bằng integration test trên MongoDB thực trước khi triển khai production.
