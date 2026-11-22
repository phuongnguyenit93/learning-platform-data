# Giảm tồn kho bằng điều kiện số lượng và inc nguyên tử

## 1. Tình huống: hai khách cùng mua sản phẩm còn một món

Một ứng dụng bán hàng lưu tồn kho cho từng SKU trong MongoDB. Sản phẩm **BOOK-101** chỉ còn **1** món. Gần như cùng lúc, hai khách gửi yêu cầu mua mỗi người một món.

Nếu code xử lý bằng cách đọc trước rồi ghi sau:

~~~text
Tồn kho ban đầu: stock = 1

Request A: đọc stock = 1
Request B: đọc stock = 1
Request A: kiểm tra 1 >= 1, ghi stock = 0, trả thành công
Request B: kiểm tra 1 >= 1, ghi stock = 0, trả thành công

Kết quả database: stock = 0
Kết quả nghiệp vụ: đã xác nhận bán 2 món dù chỉ có 1
~~~

Lỗi này là một biến thể của **race condition / lost update**: việc đọc, kiểm tra và ghi diễn ra ở các thời điểm khác nhau, nên cả hai request có thể cùng dựa vào trạng thái cũ.

Một cách sửa đúng ở cấp **một document MongoDB** là ghép **điều kiện tồn kho** và **phép giảm số lượng** vào **cùng một thao tác cập nhật nguyên tử**:

~~~javascript
db.inventories.updateOne(
  {
    _id: ObjectId("507f1f77bcf86cd799439011"),
    tenantId: "shop-a",
    active: true,
    stock: { $gte: NumberLong("1") }
  },
  {
    $inc: { stock: NumberLong("-1") }
  }
);
~~~

Mỗi lần cập nhật, MongoDB chỉ chọn document còn thỏa **stock >= quantity** tại thời điểm thao tác ghi. Với stock ban đầu = 1, chỉ một yêu cầu có thể trừ thành 0; yêu cầu còn lại không còn khớp điều kiện và sẽ không được trừ tiếp.

Bài **Giảm tồn kho bằng điều kiện số lượng và inc nguyên tử** thuộc chương **Kiểm soát đồng thời** trong module **SPRING_DATA_MONGODB**. Module sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác qua MongoTemplate hoặc repository; kỹ thuật này liên hệ trực tiếp tới thiết kế truy vấn, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.

Sau bài, bạn có thể:

1. Giải thích vì sao **read → check → save** không an toàn dưới tải đồng thời.
2. Viết filter **stock >= qty** và phép **Update.inc("stock", -qty)** trong một lệnh.
3. Dùng **MongoTemplate.updateFirst** và đọc **UpdateResult** để xác nhận thành công.
4. Dùng **findAndModify** nếu cần nhận số dư tồn kho sau cập nhật.
5. Phân biệt nguyên tử trong một document với transaction cho nhiều document.
6. Xử lý đúng validate quantity, multi-tenant, unavailable stock, retry và idempotency.
7. Mở rộng sang **giữ hàng (reservation)**, ReactiveMongoTemplate và kiểm thử cạnh tranh thật.

## 2. Dữ liệu mẫu và ranh giới bất biến

Collection **inventories**:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "shop-a",
  sku: "BOOK-101",
  stock: NumberLong("8"),
  reserved: NumberLong("0"),
  active: true,
  updatedAt: ISODate("2025-06-01T08:00:00Z")
}
~~~

Trong bài:

- **stock** là số đơn vị **còn sẵn để phân phối/bán**.
- **reserved** là số đơn vị đang giữ cho các đơn chưa hoàn tất.
- **active** quyết định sản phẩm có cho phép phân phối hay không.
- **tenantId** giới hạn phạm vi sở hữu dữ liệu.

Một bất biến cơ bản là:

\[
\text{stock}\ge0,\qquad \text{reserved}\ge0.
\]

Khi mô hình có thể giữ hàng, số lượng vật lý có thể được xác định từ **stock + reserved** nếu hai trường chỉ biểu diễn hai trạng thái đó. Trong thực tế, còn có hàng hỏng, đang vận chuyển, bị khóa, số đếm kế toán hoặc nhiều kho; hãy định nghĩa rõ **available stock** trước khi viết phép cập nhật.

### 2.1. Entity Java

~~~java
package com.example.inventory;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "inventories")
public record InventoryDocument(
    @Id ObjectId id,
    String tenantId,
    String sku,
    long stock,
    long reserved,
    boolean active,
    Instant updatedAt
) {}
~~~

**@Document** xác định collection, **@Id** ánh xạ id sang BSON _id. Giá trị quantity/stock dùng **long** để biểu diễn số nguyên; nếu tồn kho có đơn vị đo lẻ, phải chọn đơn vị nhỏ nhất hoặc mô hình số chính xác được kiểm soát, không dùng số thực binary một cách tùy tiện.

### 2.2. Chọn khóa định danh

Trong ví dụ, request cập nhật theo **_id** và **tenantId**. Nếu API dùng SKU thay ID, cần đảm bảo duy nhất trong mỗi tenant bằng một compound unique index:

~~~javascript
db.inventories.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true, name: "uk_inventory_tenant_sku" }
);
~~~

Không được suy rằng **sku** luôn unique toàn hệ thống nhiều tenant. Nếu có nhiều kho, khóa kinh doanh thường phải thêm **warehouseId** hoặc một định danh phân vùng thích hợp.

## 3. Vì sao đọc rồi save có thể bán vượt tồn?

Đây là ví dụ **không nên dùng** khi nhiều request cập nhật cùng sản phẩm:

~~~java
public void unsafeDecrease(ObjectId id, long quantity) {
    InventoryDocument inventory = repository.findById(id)
        .orElseThrow();

    if (inventory.stock() < quantity) {
        throw new IllegalStateException("Out of stock");
    }

    InventoryDocument changed = new InventoryDocument(
        inventory.id(),
        inventory.tenantId(),
        inventory.sku(),
        inventory.stock() - quantity,
        inventory.reserved(),
        inventory.active(),
        inventory.updatedAt()
    );

    repository.save(changed);
}
~~~

Vấn đề không nằm ở cú pháp Java mà ở **khoảng hở giữa lần đọc và lần ghi**:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant M as MongoDB
    A->>M: findById -> stock=1
    B->>M: findById -> stock=1
    A->>A: 1 >= 1
    B->>B: 1 >= 1
    A->>M: save stock=0
    B->>M: save stock=0
    Note over A,B: Cả hai có thể xác nhận bán thành công
~~~

**save() không tự biến hai thao tác find và save thành một giao dịch kiểm tra-ghi.** Nếu entity sử dụng @Version, Spring Data có thể phát hiện stale save theo cơ chế optimistic locking; nhưng phải xử lý conflict/retry một cách chính xác. Nếu không có version, việc save từ snapshot cũ có thể ghi đè thay đổi khác.

Thay vì cần đọc trước, MongoDB cho phép đưa **precondition vào filter của lệnh update**. Đây là kỹ thuật trọng tâm của bài.

## 4. Công thức nguyên tử: stock >= qty + $inc âm

Với số lượng cần mua **q > 0**:

\[
\text{Nếu } stock\ge q \quad\Rightarrow\quad stock'=stock-q.
\]

Nếu điều kiện không đúng, document không được cập nhật:

\[
\text{Nếu } stock<q \quad\Rightarrow\quad \text{không match, không giảm}.
\]

MongoDB:

~~~javascript
const productId = ObjectId("507f1f77bcf86cd799439011");
const requested = NumberLong("3");

const result = db.inventories.updateOne(
  {
    _id: productId,
    tenantId: "shop-a",
    active: true,
    stock: { $gte: requested }
  },
  {
    $inc: { stock: NumberLong("-3") },
    $currentDate: { updatedAt: true }
  }
);

printjson(result);
~~~

Nếu stock ban đầu = 8 và không có writer khác, kết quả là stock=5. Nếu stock chỉ còn 2, query không khớp; MongoDB không trừ thành số âm chỉ vì request đã được gửi.

### 4.1. Điều kiện và cập nhật phải nằm trong cùng lệnh

~~~javascript
// KHÔNG an toàn khi nhiều writer chạy đồng thời:
const item = db.inventories.findOne({ _id: productId });
if (item.stock >= 3) {
  db.inventories.updateOne(
    { _id: productId },
    { $inc: { stock: -3 } }
  );
}
~~~

Điều kiện trong Java/JavaScript chỉ được kiểm tra trên dữ liệu đã đọc, có thể không còn hiện hành. Lệnh update cuối cùng **không mang điều kiện stock >= 3**, nên hai yêu cầu vẫn có thể cùng giảm.

### 4.2. Vì sao $inc tốt hơn $set cho counter?

~~~javascript
// Có thể ghi đè giá trị của writer khác nếu computedStock là dữ liệu cũ.
{ $set: { stock: computedStock } }
~~~

~~~javascript
// Thao tác tăng/giảm tương đối trên giá trị tại server.
{ $inc: { stock: -3 } }
~~~

**$inc** cập nhật một giá trị số dựa trên trạng thái document được thao tác; không yêu cầu caller tính stock mới từ snapshot cũ. **Nhưng $inc âm một mình chưa đủ:** nó vẫn có thể làm stock âm nếu không kèm điều kiện **stock >= quantity** trong filter.

### 4.3. Nguyên tử ở cấp document

MongoDB bảo đảm tính nguyên tử cho một thao tác ghi lên **một document**, kể cả thao tác sửa nhiều field của document đó. Khi các writer tranh chấp cùng document, điều kiện lọc gắn với update được đánh giá với trạng thái phù hợp lúc ghi, nên mô hình **conditional decrement** ngăn hai thao tác cùng rút quá số lượng.

Điều đó **không tự đảm bảo atomicity cho nhiều document** như vừa trừ inventory vừa tạo order trong collection khác.

## 5. MongoTemplate.updateFirst: ví dụ Java tối thiểu đúng

~~~java
package com.example.inventory;

import com.mongodb.client.result.UpdateResult;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public class InventoryService {

    private final MongoTemplate mongoTemplate;

    public InventoryService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public boolean tryDecreaseStock(
            ObjectId productId,
            String authenticatedTenantId,
            long quantity) {

        if (productId == null) {
            throw new IllegalArgumentException("Product ID is required");
        }
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()) {
            throw new IllegalArgumentException("Tenant is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive");
        }

        Query query = Query.query(
            Criteria.where("_id").is(productId)
                .and("tenantId").is(authenticatedTenantId)
                .and("active").is(true)
                .and("stock").gte(quantity)
        );

        Update update = new Update()
            .inc("stock", -quantity)
            .currentDate("updatedAt");

        UpdateResult result = mongoTemplate.updateFirst(
            query,
            update,
            InventoryDocument.class
        );

        if (!result.wasAcknowledged()) {
            throw new IllegalStateException(
                "Inventory update was not acknowledged");
        }

        return result.getModifiedCount() == 1;
    }
}
~~~

Phần quan trọng nhất:

~~~java
Criteria.where("_id").is(productId)
    .and("tenantId").is(authenticatedTenantId)
    .and("active").is(true)
    .and("stock").gte(quantity);

new Update().inc("stock", -quantity);
~~~

**Cùng một request MongoDB chứa cả điều kiện và phép giảm**. Không có một lần findById trước đó để quyết định số lượng có đủ.

### 5.1. Tại sao dùng updateFirst?

Đã có filter theo **_id**, nên tối đa một document khớp do _id là duy nhất trong collection bình thường. **updateFirst** diễn đạt rõ ý định thay đổi một inventory document.

Với filter chỉ theo status/tenant, updateFirst có thể cập nhật một document nào đó trong nhóm khớp, không phù hợp nếu caller muốn trừ đúng một SKU. Khi đó cần đưa ID hoặc khóa kinh doanh đã được bảo đảm unique vào filter.

### 5.2. Không bật upsert

**updateFirst** trong ví dụ là cập nhật document đang tồn tại; **không tự upsert** một inventory mới khi không tìm được.

Nếu chuyển sang một API có **upsert=true**, trường hợp out-of-stock/không tìm thấy có thể dẫn tới chèn document ngoài ý muốn. Một yêu cầu trừ tồn không được tự tạo inventory với stock âm hoặc thông tin thiếu.

### 5.3. Nên dùng đối tượng ID hay SKU?

ID ổn định phù hợp khi caller đã có mã inventory nội bộ. SKU có thể hợp lý nếu repository bảo đảm compound unique theo tenant/warehouse. Dù dùng cách nào, **quyền tenant phải được áp đặt bởi server** và **điều kiện stock >= quantity phải ở cùng update**.

### 5.4. updatedAt

**currentDate("updatedAt")** dùng thời gian MongoDB Server để đánh dấu thay đổi. Nếu app có auditing callback, đừng tự giả định mọi đường update bằng MongoTemplate gọi giống repository.save. Quyết định rõ field nào được cập nhật tại server, field nào thuộc audit pipeline riêng.

## 6. Đọc UpdateResult: 0 không nhất thiết là lỗi database

MongoDB trả kết quả cập nhật với các thông tin như:

- **matchedCount**: số document khớp filter.
- **modifiedCount**: số document được sửa đổi theo hợp đồng lệnh.
- **upsertedId**: có giá trị nếu dùng upsert và đã tạo document mới.
- **wasAcknowledged**: thao tác ghi có được xác nhận hay không.

Ví dụ:

| Tình huống | matchedCount | modifiedCount | Ý nghĩa |
| --- | ---: | ---: | --- |
| stock=8, q=3, update thành công | 1 | 1 | Trừ đúng 3 |
| stock=2, q=3 | 0 | 0 | Không đủ hàng |
| ID không tồn tại | 0 | 0 | Không tìm thấy |
| tenant sai | 0 | 0 | Không có quyền hoặc không thấy document trong phạm vi |
| active=false | 0 | 0 | Không cho phép xuất hàng |

Vì quantity luôn dương và update có phép trừ stock, nếu lệnh được xác nhận và match thành công thì trong mô hình này giá trị stock phải thay đổi. **modifiedCount=1** là tín hiệu thành công đơn giản.

### 6.1. Khi modifiedCount=0 phải làm gì?

Không nên lập tức trả thông tin nhạy cảm kiểu:

~~~text
"Bạn có quyền với SKU này nhưng cửa hàng khác đang có stock=2"
~~~

Một update=0 có thể do nhiều nguyên nhân: không tồn tại, tenant không khớp, inactive, stock không đủ hoặc dữ liệu vừa thay đổi. Với public API, có thể trả một kết quả chung như **409 Conflict / unavailable** hoặc **business error không thể giữ hàng** theo hợp đồng.

Nếu cần chẩn đoán nội bộ, có thể đọc lại document **sau khi xác thực quyền**. Nhưng lần đọc đó là trạng thái quan sát sau update, không phải bằng chứng tuyệt đối về nguyên nhân tại thời điểm cập nhật.

### 6.2. Sự khác nhau giữa “0” và exception

- **0 modified** trong một lệnh acknowledged: không có document đáp ứng điều kiện cập nhật.
- **Exception/time-out/network error**: caller có thể không biết chắc server đã áp dụng cập nhật hay chưa.

**Không xử lý timeout bằng cách coi như out-of-stock**, vì phép giảm có thể đã thành công trước khi response bị mất. Trường hợp kết quả không chắc chắn cần được giải quyết qua operation ID/idempotency và cơ chế đối soát, không retry mù.

### 6.3. Những kết quả không nên suy từ một con số

modifiedCount=1 **không chứng minh** order đã được tạo, thanh toán thành công, event đã gửi hoặc warehouse ngoài hệ thống đã xác nhận. Nó chỉ xác nhận một thao tác cập nhật inventory trên MongoDB.

## 7. findAndModify: lấy số dư sau khi trừ

Nhiều API muốn trả **stock còn lại** ngay sau thao tác. Nếu làm updateFirst rồi findById, một request khác có thể tiếp tục trừ trước khi đọc, khiến số dư đọc được **không phải giá trị ngay sau phép trừ của mình**.

Spring Data MongoDB có **findAndModify** để thực hiện điều kiện + update và trả document trước hoặc sau cập nhật theo option.

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public InventoryDocument decreaseAndReturnNewStock(
        MongoTemplate template,
        ObjectId productId,
        String tenantId,
        long quantity) {

    if (productId == null || tenantId == null
            || tenantId.isBlank() || quantity <= 0) {
        throw new IllegalArgumentException("Invalid request");
    }

    Query query = Query.query(
        Criteria.where("_id").is(productId)
            .and("tenantId").is(tenantId)
            .and("active").is(true)
            .and("stock").gte(quantity)
    );

    Update update = new Update()
        .inc("stock", -quantity)
        .currentDate("updatedAt");

    return template.findAndModify(
        query,
        update,
        FindAndModifyOptions.options()
            .returnNew(true)
            .upsert(false),
        InventoryDocument.class
    );
}
~~~

- Khi match và update thành công: trả **InventoryDocument mới sau cập nhật**.
- Khi không match: trả **null** (với API overload này).
- Khi operation lỗi: ném exception, không dùng null để che lỗi.

### 7.1. Không lấy số dư sau cập nhật bằng phép trừ từ số cũ

Không tính stockAfter = preRead.stock - quantity rồi gửi lại như kết quả đã commit. Nếu đã có concurrency, số cũ có thể không còn phù hợp.

**findAndModify(returnNew=true)** trả document của chính thao tác đã được thực hiện, phù hợp khi response cần số dư sau decrement. Một thao tác ghi khác vẫn có thể xảy ra ngay sau đó; response không phải khóa độc quyền dài hạn trên tồn kho.

### 7.2. Projection giảm payload

Khi inventory chứa nhiều field lớn, cân nhắc chỉ trả các field cần thiết bằng projection trong Query/options tương ứng và một DTO. Không lưu lại partial InventoryDocument bằng repository.save, vì có thể ghi đè các field không được đọc.

### 7.3. updateFirst hay findAndModify?

| Nhu cầu | API thường phù hợp |
| --- | --- |
| Chỉ cần biết trừ thành công hay không | updateFirst + UpdateResult |
| Cần số dư stock ngay sau cập nhật | findAndModify returnNew=true |
| Cần sửa nhiều inventory document trong một giao dịch | MongoDB transaction / quy trình reserve phù hợp |
| Chỉ cần đọc số dư không đổi dữ liệu | find/query thông thường |

**findAndModify không làm thao tác nhiều document trở nên atomic**; sức mạnh của nó ở đây là filter, update và việc trả trạng thái gắn với **một document**.

## 8. Vì sao conditional update ngăn bán vượt tồn?

Với stock=1 và hai request cùng quantity=1:

~~~mermaid
sequenceDiagram
    participant A as Checkout A
    participant B as Checkout B
    participant M as MongoDB
    A->>M: updateOne(_id=X, stock >= 1; $inc stock:-1)
    B->>M: updateOne(_id=X, stock >= 1; $inc stock:-1)
    M-->>A: modifiedCount=1
    Note over M: stock trở thành 0
    M-->>B: modifiedCount=0
    Note over A,B: Chỉ một checkout được trừ hàng
~~~

Thứ tự request nào thắng không được bảo đảm bởi ví dụ. Nhưng mỗi thao tác chỉ được ghi khi điều kiện của nó thỏa, nên hai request **không thể cùng trừ thành công nếu chỉ có một đơn vị còn lại**, với giả định không có writer khác cộng hàng vào giữa.

### 8.1. Quy tắc có hiệu lực khi mọi đường giảm cùng tuân thủ

Nếu một service khác vẫn chạy:

~~~javascript
db.inventories.updateOne(
  { _id: productId },
  { $inc: { stock: -100 } }
);
~~~

thì bất biến stock >= 0 có thể bị vi phạm. Cần bảo đảm **mọi đường xuất kho** dùng điều kiện phù hợp hoặc có policy quản trị được kiểm soát. Không thể chứng minh dữ liệu an toàn chỉ từ một method trong khi các writer khác không tuân thủ.

### 8.2. $inc không thay schema validation

MongoDB cho phép các phép cập nhật số và xử lý những kiểu BSON khác nhau theo quy tắc của server. Đừng mặc định mọi document đều lưu stock dạng long không âm chỉ vì Java entity khai báo long.

Migration hoặc thao tác trực tiếp có thể tạo dữ liệu null, missing, String, double hoặc giá trị âm. Cần:

- Validation khi tạo inventory.
- Schema validation ở database nếu cần bất biến mạnh.
- Kiểm tra/migration dữ liệu legacy.
- Quyền ghi hạn chế cho các dịch vụ và job được phép điều chỉnh stock.

## 9. Điều kiện quantity: bảo vệ phép trừ ngay từ input

**Không được cho quantity = 0 hoặc quantity âm** đi vào nhánh giảm tồn.

~~~java
if (quantity <= 0) {
    throw new IllegalArgumentException(
        "Quantity must be positive");
}
~~~

Vì sao?

~~~text
quantity = 0  -> $inc: {stock: 0}; không giảm nhưng có thể gây side effect khác
quantity = -3 -> $inc: {stock: +3}; biến request mua hàng thành cộng tồn
~~~

Ngoài điều kiện dương, cần một **giới hạn nghiệp vụ hợp lý** cho số lượng tối đa trên mỗi request:

~~~java
if (quantity > 1000) {
    throw new IllegalArgumentException(
        "Quantity exceeds policy limit");
}
~~~

Con số 1000 chỉ là ví dụ, không phải giới hạn MongoDB. Chính sách thực phụ thuộc SKU/kho/khách hàng.

### 9.1. Overflow và Long.MIN_VALUE

Nếu đã kiểm tra **quantity > 0**, phép **-quantity** không thể gặp trường hợp Long.MIN_VALUE (giá trị âm), và không tràn theo hướng negation của long. Tuy nhiên, các phép **cộng stock** hoặc **tăng reserved** vẫn có nguy cơ overflow nếu dữ liệu vượt ngưỡng long.

Chọn kiểu số, giới hạn maximum và schema validation phù hợp. Không dùng int nếu inventory có thể vượt Integer.MAX_VALUE, cũng không dùng double để lưu số lượng nguyên cần tính chính xác.

### 9.2. Không để client quyết định tenant

Tham số authenticatedTenantId trong code phải được lấy từ **principal/session/token đã xác thực**, hoặc được policy server kiểm tra trước khi gọi cập nhật.

Filter tenant là lớp hạn chế ở database; nó không thay thế **authorization**. Nếu client tùy ý truyền tenantId của người khác, việc thêm tenantId vào query chưa đủ để chống xóa/trừ hàng xuyên tenant.

## 10. SKU, nhiều kho và unique index

Nếu mỗi SKU có nhiều kho:

~~~javascript
{
  tenantId: "shop-a",
  warehouseId: "HCM-01",
  sku: "BOOK-101",
  stock: NumberLong("8")
}
~~~

thì khóa nghiệp vụ có thể là **tenantId + warehouseId + sku**.

~~~javascript
db.inventories.createIndex(
  { tenantId: 1, warehouseId: 1, sku: 1 },
  { unique: true }
);
~~~

Nếu gọi updateFirst chỉ theo tenantId+sku khi có nhiều kho, MongoDB có thể cập nhật một inventory document không đúng kho. **Atomicity chỉ bảo vệ document được chọn, không tự quyết định kho nào đúng về nghiệp vụ.**

### 10.1. Filter theo _id và tenant thường đủ định danh

Trong hệ thống dùng ObjectId, **_id đã có unique index**, nên query theo _id xác định tối đa một document. Filter tenant và active/stock bổ sung ràng buộc bảo mật/điều kiện nghiệp vụ.

Không tạo hàng loạt index chỉ vì thấy filter có thêm tenant/active/stock. Hãy dùng **explain, cardinality và workload** để quyết định index bổ sung, đặc biệt nếu truy vấn cập nhật theo _id đã rất chọn lọc.

### 10.2. Cập nhật theo SKU có thể cần compound index

Nếu use case chủ yếu tìm theo **tenantId + sku + stock >= q**, index bắt đầu bằng tenantId và sku có thể hữu ích để tìm document. Vì SKU unique trong tenant, việc thêm stock vào index có thể không đáng chi phí; cần đo.

## 11. Giữ hàng: giảm available và tăng reserved cùng document

Trong quy trình checkout thật, có thể chưa thu tiền ngay. Thay vì trừ hàng vĩnh viễn khi bấm thanh toán, ứng dụng **reserve** một số lượng cho order đang xử lý.

Với cấu trúc stock = available và reserved = số đang giữ:

\[
\text{stock}'=\text{stock}-q,\qquad
\text{reserved}'=\text{reserved}+q.
\]

Vì hai field nằm **trong cùng document**, MongoDB có thể cập nhật cả hai nguyên tử:

~~~javascript
db.inventories.updateOne(
  {
    _id: productId,
    tenantId: "shop-a",
    active: true,
    stock: { $gte: 2 }
  },
  {
    $inc: {
      stock: -2,
      reserved: 2
    },
    $currentDate: { updatedAt: true }
  }
);
~~~

Java:

~~~java
Query query = Query.query(
    Criteria.where("_id").is(productId)
        .and("tenantId").is(tenantId)
        .and("active").is(true)
        .and("stock").gte(quantity)
);

Update update = new Update()
    .inc("stock", -quantity)
    .inc("reserved", quantity)
    .currentDate("updatedAt");

UpdateResult result = mongoTemplate.updateFirst(
    query, update, InventoryDocument.class
);
~~~

Trong cập nhật thành công, **stock+reserved** không đổi, miễn là hai field bắt đầu có giá trị hợp lệ và không có writer trái quy tắc. Đây là **reservation counter**, chưa phải bằng chứng đã có bản ghi reservation duy nhất cho từng order.

### 11.1. Khi thanh toán thành công

Nếu hàng đã được reserve, có thể chuyển trạng thái reservation thành **consumed** và giảm reserved tương ứng, tùy mô hình số lượng vật lý:

~~~text
Trước reserve: stock=8, reserved=0
Sau reserve 2: stock=6, reserved=2
Sau consume:   stock=6, reserved=0
~~~

Như vậy, hai món đã ra khỏi tổng stock+reserved sau consume. **Không trừ stock thêm lần nữa ở bước thanh toán**, nếu stock đã được giảm khi reserve.

### 11.2. Khi hủy reservation

Hoàn lại hàng:

\[
stock'=stock+q,\qquad reserved'=reserved-q.
\]

Không được viết một update cộng stock vô điều kiện chỉ vì nhận message “cancel”. Cần bảo đảm reservation thực sự đang ở trạng thái **RESERVED**, không bị cancel hai lần; giảm reserved phải có điều kiện **reserved >= q**, nhưng điều kiện số lượng này **không đủ chống refund hai lần cho cùng order**.

### 11.3. TTL không tự hoàn hàng

Nếu reservation có expiresAt và TTL tự xóa document reservation, **MongoDB TTL không tự cộng lại stock hoặc giảm reserved**. Phải có workflow hết hạn được thiết kế: chuyển trạng thái reservation có điều kiện, thực hiện hoàn counter và xử lý retry/idempotency.

## 12. Kiểm soát nhất quán khi có nhiều document

Conditional decrement cập nhật **một inventory document** an toàn. Nhưng checkout thường gồm:

1. Giảm stock sản phẩm A.
2. Giảm stock sản phẩm B.
3. Tạo order và order items.
4. Ghi reservation hoặc payment intent.
5. Gửi sự kiện cho hệ thống ngoài.

Không có nghĩa tất cả các bước trên sẽ thành một thao tác atomic chỉ vì mỗi inventory update dùng $inc.

### 12.1. Transaction nhiều document

Khi deployment MongoDB hỗ trợ transaction và Spring Data cấu hình **MongoTransactionManager**, có thể dùng transaction để gộp các ghi MongoDB liên quan.

~~~java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void reserveOrder(
        String tenantId,
        OrderRequest request) {

    for (OrderLine line : request.lines()) {
        boolean ok = inventoryService.tryDecreaseStock(
            line.inventoryId(),
            tenantId,
            line.quantity()
        );

        if (!ok) {
            throw new OutOfStockException(line.inventoryId());
        }
    }

    orderRepository.insert(
        createReservedOrder(tenantId, request)
    );
}
~~~

Ví dụ minh họa cấu trúc: **OrderRequest, OrderLine, OutOfStockException, orderRepository và createReservedOrder** là thành phần nghiệp vụ cần định nghĩa riêng. Khi áp dụng thực tế:

- Lời gọi phải đi qua Spring transactional proxy.
- Các thao tác MongoDB phải tham gia cùng transaction/session.
- Deployment phải hỗ trợ transaction.
- Nếu một thao tác hết hàng, phải ném exception phù hợp để rollback.
- Transaction có thể gặp write conflict và cần chiến lược retry được kiểm soát.

**Không bật transaction cho mọi phép trừ một document nếu không cần.** Single-document conditional update đã có tính nguyên tử; transaction thêm overhead và có giới hạn runtime.

### 12.2. Thanh toán và HTTP ngoài MongoDB

Một transaction MongoDB **không rollback** được lệnh gọi thành công tới cổng thanh toán hoặc API của một hệ thống bên ngoài. Nếu cần liên kết order/inventory/event, cân nhắc **outbox** hoặc saga/reservation workflow với các trạng thái và bước bù trừ idempotent.

### 12.3. Thứ tự cập nhật nhiều SKU

Với order có nhiều dòng, nên xác định thứ tự khóa để giảm va chạm và tránh những hành vi cạnh tranh không cần thiết. Tuy nhiên, việc sắp xếp SKU không thay thế transaction; nếu bước trừ SKU thứ hai thất bại, cần rollback/bù trừ đúng cách cho SKU thứ nhất.

## 13. MongoDB update nguyên tử và optimistic locking @Version

Spring Data MongoDB hỗ trợ **@Version** cho các entity cập nhật theo optimistic locking:

~~~java
import org.springframework.data.annotation.Version;

@Document(collection = "inventories")
public record VersionedInventory(
    @Id ObjectId id,
    String tenantId,
    long stock,
    @Version Long version
) {}
~~~

Repository **save(entity)** với version phù hợp có thể phát hiện việc entity đã thay đổi bởi writer khác. Khi stale, Spring Data có thể ném **OptimisticLockingFailureException** theo hợp đồng của thao tác và write concern.

**Đây là cơ chế khác với điều kiện stock >= qty + $inc.**

| Mục tiêu | Cơ chế |
| --- | --- |
| Không bao giờ trừ quá stock hiện tại | stock >= qty trong filter và $inc âm |
| Không ghi đè một phiên bản document đã đổi | @Version/expectedVersion |
| Cập nhật có điều kiện status/tenant | Gắn predicate vào cùng update |
| Ghi nhiều document cùng commit/rollback | Transaction |

### 13.1. Có cần @Version cho atomic decrement?

Để bảo vệ bất biến stock >= 0 khi các writer đều dùng conditional update đúng, **không cần đọc version trước**. Kiểm tra version có thể làm tăng tỉ lệ conflict nếu nhiều writer đều muốn trừ hàng nhưng tổng stock vẫn đủ.

Tuy nhiên, nếu còn những thao tác khác sửa nhiều field có liên quan đến inventory, version có thể hữu ích. Khi dùng MongoTemplate update, cần biết Spring Data có thể xử lý tăng version ở các update operation tùy entity/phiên bản. **Không tự cho rằng version tự động được kiểm tra với expected version nếu filter không chứa version**.

### 13.2. Nếu phải kiểm tra expectedVersion

~~~java
Query query = Query.query(
    Criteria.where("_id").is(productId)
        .and("tenantId").is(tenantId)
        .and("stock").gte(quantity)
        .and("version").is(expectedVersion)
);

Update update = new Update()
    .inc("stock", -quantity);
~~~

Đây là conditional update với **cả điều kiện stock và version**. Nếu update=0, nguyên nhân có thể là stock không đủ hoặc version không khớp. Nếu nghiệp vụ cần phân loại, đọc lại có kiểm soát; không được suy duy nhất từ modifiedCount.

## 14. Retry không đúng có thể trừ hàng hai lần

Giả sử kho có stock=10, một request muốn trừ quantity=2:

~~~text
Client gửi request lần 1
MongoDB áp dụng update thành công: stock=8
Mạng đứt trước khi client nhận response
Client retry cùng request lần 2
MongoDB vẫn thấy stock>=2: trừ tiếp thành stock=6
~~~

**Conditional update ngăn stock âm, nhưng không ngăn cùng một yêu cầu bị áp dụng hai lần** nếu mỗi lần đều còn đủ stock. Đây là hai loại tính đúng đắn khác nhau:

| Vấn đề | Giải pháp chính |
| --- | --- |
| Hai request độc lập cùng tranh một đơn vị hàng | stock >= qty + $inc âm nguyên tử |
| Một request bị phát lại sau timeout | **Idempotency key** và ghi nhận kết quả của thao tác |
| Trừ hàng thành công nhưng tạo order thất bại | Transaction hoặc saga/compensation |
| Gửi event thanh toán lặp | Outbox, event ID, consumer idempotent |

### 14.1. Phân biệt driver retryable writes và retry ứng dụng

MongoDB driver và server có cơ chế **retryable writes** cho những thao tác đáp ứng điều kiện tương ứng. Tuy nhiên, **một request HTTP bị gửi lại như một request mới** không mặc nhiên dùng cùng transaction statement identifier của driver.

Vì vậy, không dùng lý do “driver có retryable writes” để bỏ qua idempotency ở tầng API/order. Nếu ứng dụng tự gọi lại service bằng một operation mới, phải có cơ chế tránh xử lý cùng business action hai lần.

### 14.2. Không retry mù khi kết quả chưa chắc chắn

~~~java
// Không nên: timeout có thể xảy ra sau khi server đã trừ hàng.
for (int i = 0; i < 3; i++) {
    try {
        return inventoryService.tryDecreaseStock(id, tenant, qty);
    } catch (RuntimeException error) {
        // Retry không có request ID hoặc kiểm chứng trạng thái.
    }
}
~~~

Đoạn trên nguy hiểm vì lần thứ hai có thể giảm thêm hàng. Ngoài ra, nó bắt mọi RuntimeException mà không phân biệt lỗi input, network hay lỗi dữ liệu.

Nếu driver/server trả một lỗi ghi chắc chắn không thực thi, ứng dụng có thể có đường retry kỹ thuật theo hợp đồng. Nhưng với tình huống **không biết lệnh đã commit hay chưa**, phải dùng định danh yêu cầu và quy trình đối soát.

## 15. Idempotency key: gắn thao tác giảm hàng với một yêu cầu

Một reservation hoặc một checkout attempt nên có **requestId** duy nhất, ví dụ:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439099"),
  tenantId: "shop-a",
  requestId: "checkout-2025-000123",
  inventoryId: ObjectId("507f1f77bcf86cd799439011"),
  quantity: NumberLong("2"),
  status: "RESERVED",
  createdAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

Index duy nhất:

~~~javascript
db.inventory_reservations.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true, name: "uk_reservation_tenant_request" }
);
~~~

### 15.1. Vì sao chỉ kiểm tra exists(requestId) không đủ?

~~~text
Request A: kiểm tra requestId chưa tồn tại
Request B: kiểm tra requestId chưa tồn tại
Request A: trừ stock
Request B: trừ stock
Request A/B: một bên insert reservation trùng thất bại
~~~

Nếu không có transaction/thiết kế phù hợp, **unique index trên reservation chưa đủ để tự đảo ngược phép trừ stock đã xảy ra ở collection khác**.

### 15.2. Mô hình transaction cho reservation

Với transaction MongoDB nhiều document:

1. Nhận **tenantId** đã xác thực, **requestId**, inventoryId, quantity đã validate.
2. Kiểm tra hoặc cố tạo record idempotency/reservation có unique key.
3. Trừ inventory bằng **conditional $inc** trong cùng transaction.
4. Chỉ đánh dấu reservation là RESERVED và commit nếu decrement thành công.
5. Nếu hết hàng, abort transaction và trả kết quả nghiệp vụ.
6. Nếu trùng requestId, đọc record hiện có và **đối chiếu payload** (SKU/quantity) để xác định có phải cùng yêu cầu thật không.
7. Nếu commit outcome chưa rõ, tra cứu theo requestId trước khi thử thực hiện lại.

~~~mermaid
flowchart TD
    A["Nhận tenant + requestId + inventoryId + qty"] --> B["Bắt đầu transaction"]
    B --> C["Đảm bảo idempotency record duy nhất"]
    C -->|Trùng| D["Xác minh kết quả của request đã có"]
    C -->|Mới| E["Conditional $inc: stock >= qty"]
    E -->|Không match| F["Abort, báo không giữ được hàng"]
    E -->|Thành công| G["Lưu reservation/order cùng transaction"]
    G --> H["Commit"]
    H --> I["Trả kết quả theo requestId"]
~~~

**Điểm thiết yếu:** chính sách idempotency phải bao trùm cả **inventory decrement và record ghi nhận nghiệp vụ**. Đừng dùng một thao tác insert unique tách rời mà không xử lý trường hợp decrement đã thành công nhưng record chưa được lưu.

### 15.3. Trùng key không luôn là “thành công”

Nếu một client vô ý tái sử dụng requestId nhưng thay quantity từ 2 thành 10, không được trả kết quả cũ như thể hai yêu cầu giống nhau. Record idempotency cần lưu fingerprint/những trường quan trọng để kiểm tra payload consistency.

### 15.4. Không lưu vô hạn request ID trong một inventory document

Có thể nghĩ tới việc thêm requestId vào một array để kiểm tra trùng ngay trong update. Nhưng array request IDs tăng không giới hạn sẽ làm inventory document phình to, kéo theo giới hạn kích thước BSON và chi phí ghi.

Một collection reservation/idempotency riêng cùng transaction hoặc một mô hình workflow được thiết kế là lựa chọn dễ quản lý hơn cho hệ thống lớn.

## 16. Giải phóng reservation phải idempotent

Một message hủy đặt hàng có thể được gửi lặp. Nếu mỗi lần đều chạy:

~~~javascript
db.inventories.updateOne(
  { _id: productId },
  { $inc: { stock: 2, reserved: -2 } }
);
~~~

thì lần thứ hai có thể làm **stock tăng thừa** và reserved âm, dù lần đầu đã hoàn tất.

Thiết kế đúng cần một trạng thái reservation:

~~~text
NEW -> RESERVED -> CONSUMED
                 -> CANCELLED
                 -> EXPIRED
~~~

Chỉ cho phép một transition hợp lệ từ **RESERVED** sang **CANCELLED/EXPIRED**, và chỉ sau transition thành công mới thực hiện tác động hoàn stock đúng một lần, dưới transaction hoặc một cơ chế đảm bảo idempotency/bù trừ tương ứng.

### 16.1. Cách làm trong transaction

- Cập nhật reservation từ RESERVED sang CANCELLED bằng điều kiện status=RESERVED.
- Nếu modifiedCount=1, hoàn counter stock/reserved cho inventory.
- Nếu modifiedCount=0, không hoàn thêm; xác minh reservation đã xử lý hoặc không tồn tại.
- Commit hai thay đổi MongoDB cùng transaction nếu yêu cầu bất biến nhiều document.

### 16.2. Khi không thể dùng transaction

Cần một saga/state machine có **operation IDs**, trạng thái trung gian và khả năng phục hồi nếu process crash giữa các bước. Không chỉ tạo một cron job “thấy expired thì cộng stock” khi không có marker nào chứng minh đã hoàn hay chưa.

## 17. Xử lý lỗi và response HTTP

Một service cấp API cần phân biệt **sai input**, **không giữ được hàng**, **kết quả chưa xác định** và **lỗi hệ thống**.

| Tình huống | Phản ứng gợi ý |
| --- | --- |
| quantity <= 0 | 400 Bad Request |
| productId sai định dạng | 400 Bad Request |
| tenant chưa xác thực | 401 Unauthorized hoặc 403 theo policy |
| product không tồn tại hoặc không thuộc tenant | 404/403 theo chính sách không tiết lộ |
| stock không đủ, sản phẩm inactive | 409 Conflict hoặc 422 theo API contract |
| requestId trùng với cùng payload | Trả kết quả đã ghi nhận, không trừ lại |
| requestId trùng với payload khác | 409 Conflict |
| network timeout sau lệnh ghi | Đánh dấu outcome chưa chắc chắn, tra cứu theo requestId |
| lỗi database không thể phục hồi | 5xx, telemetry, không biến thành out-of-stock |

Đây là các **gợi ý thiết kế API**, không phải mapping HTTP bắt buộc của Spring Data MongoDB. Điều quan trọng là không làm mất thông tin kỹ thuật bằng cách biến mọi exception thành “không đủ hàng”.

### 17.1. Không trả thông tin tồn kho xuyên tenant

Nếu user gửi ID của tenant khác, không nên trả chi tiết “shop-b còn 12 món”. Giới hạn điều kiện tenant trong update, áp authorization trước và chỉ trả response phù hợp để tránh data enumeration.

### 17.2. Metrics không thay business result

Nên đo:

- Số request decrement được chấp nhận.
- Số request không khớp condition.
- Conflict/duplicate idempotency key.
- Timeout/unknown outcome.
- Độ trễ update theo SKU/warehouse ở mức bảo vệ dữ liệu nhạy cảm.

Các metrics giúp theo dõi hotspot và lỗi, nhưng không được dùng thay trạng thái order/reservation có tính bền vững.

## 18. ReactiveMongoTemplate: nguyên tắc giống hệt, API khác

Trong stack WebFlux, dùng **ReactiveMongoTemplate** và để caller subscribe:

~~~java
package com.example.inventory;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import reactor.core.publisher.Mono;

public class ReactiveInventoryService {

    private final ReactiveMongoTemplate template;

    public ReactiveInventoryService(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Mono<Boolean> tryDecreaseStock(
            ObjectId productId,
            String authenticatedTenantId,
            long quantity) {

        if (productId == null || authenticatedTenantId == null
                || authenticatedTenantId.isBlank() || quantity <= 0) {
            return Mono.error(
                new IllegalArgumentException("Invalid request")
            );
        }

        Query query = Query.query(
            Criteria.where("_id").is(productId)
                .and("tenantId").is(authenticatedTenantId)
                .and("active").is(true)
                .and("stock").gte(quantity)
        );

        Update update = new Update()
            .inc("stock", -quantity)
            .currentDate("updatedAt");

        return template.updateFirst(
            query, update, InventoryDocument.class
        ).map(result -> {
            if (!result.wasAcknowledged()) {
                throw new IllegalStateException(
                    "Inventory update was not acknowledged");
            }
            return result.getModifiedCount() == 1;
        });
    }
}
~~~

**Mono<Boolean>** chỉ phát true/false khi thao tác được subscribe và hoàn tất. Cơ chế atomic update là do MongoDB Server bảo đảm, không phụ thuộc vào Java dùng thread blocking hay reactive.

### 18.1. Không block trên WebFlux event loop

~~~java
// Không nên trong reactive request handler:
Boolean ok = reactiveService
    .tryDecreaseStock(id, tenant, quantity)
    .block();
~~~

Hãy compose bằng **flatMap/map** hoặc trả Mono cho controller. Blocking làm giảm khả năng phục vụ request và có thể gây lỗi event loop.

### 18.2. Không subscribe thủ công hai lần

~~~java
// Sai: có thể tạo hai lần cập nhật cho cùng business request.
Mono<Boolean> decrement =
    reactiveService.tryDecreaseStock(id, tenant, quantity);

decrement.subscribe();
return decrement;
~~~

Nếu caller subscribe lần thứ hai, MongoDB có thể nhận hai thao tác decrement. **Mono không tự bảo đảm idempotency**. Dùng một subscription đúng lifecycle, và requestId để xử lý retry khi cần.

### 18.3. Reactive findAndModify

~~~java
Mono<InventoryDocument> updated =
    reactiveTemplate.findAndModify(
        query,
        update,
        FindAndModifyOptions.options()
            .returnNew(true)
            .upsert(false),
        InventoryDocument.class
    );
~~~

Khi filter không khớp, ReactiveMongoTemplate thường phát **Mono.empty()**. Nếu nghiệp vụ cần phân biệt outcome, sử dụng **switchIfEmpty** hoặc một kiểu kết quả rõ thay vì tự biến empty thành thành công.

### 18.4. Reactive transaction

Khi cần cập nhật inventory và reservation trong một MongoDB transaction reactive, phải cấu hình **ReactiveMongoTransactionManager** và dùng ranh giới transaction tương ứng. Không dùng @Transactional kiểu đồng bộ rồi kỳ vọng tự liên kết mọi thao tác reactive khi các session không được thiết lập đúng.

## 19. Index và hiệu năng dưới cạnh tranh đồng thời

Một inventory update theo **_id** có thể dùng index mặc định trên _id để tìm document. Đối với truy vấn:

~~~javascript
db.inventories.updateOne(
  {
    _id: productId,
    tenantId: "shop-a",
    stock: { $gte: 2 }
  },
  { $inc: { stock: -2 } }
);
~~~

MongoDB có thể định vị theo _id rồi kiểm tra thêm tenant/stock trên một document. Không nhất thiết cần index **{_id,tenantId,stock}**; thêm index có thể chỉ tăng write amplification mà không giúp đáng kể.

### 19.1. Cập nhật theo tenant + SKU

Với query dùng **tenantId + sku**, compound unique index:

~~~javascript
db.inventories.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true }
);
~~~

vừa bảo vệ khóa nghiệp vụ vừa có thể hỗ trợ tìm một inventory document. Nếu tồn kho phân theo warehouse, thêm warehouseId đúng với unique key.

### 19.2. Không index stock theo thói quen

Stock thay đổi trên gần như mọi checkout. Index riêng trên stock làm tăng chi phí mỗi lần giảm. Chỉ tạo index trên stock nếu có **một workload truy vấn thực** được chứng minh cần nó, ví dụ tìm nhiều SKU còn hàng theo filter và sort cụ thể.

### 19.3. Hot document

Một SKU bán cực chạy có thể bị hàng nghìn writer cập nhật cùng document. Dù nguyên tử, mọi lần ghi vào cùng document vẫn cạnh tranh về tài nguyên.

Nếu p95/p99 latency tăng, cần:

- Đo số update/s, matched/modified count, write conflicts và độ trễ.
- Kiểm tra hệ thống queue/reservation để điều tiết tải.
- Giảm số writer thừa và số lần retry ứng dụng.
- Đánh giá partition theo warehouse/lot nếu **bài toán nghiệp vụ thật** cho phép.

**Sharding không tự loại bỏ contention nếu toàn bộ request vẫn ghi một document của cùng SKU.** Partitioning phải đi kèm quy tắc cấp phát hàng để không gây oversell khi nhìn tổng across partitions.

## 20. Write concern, failover và giới hạn của acknowledged result

Một thao tác **modifiedCount=1** là kết quả của một ghi được xác nhận theo write concern đang áp dụng. Nó không đồng nghĩa mọi replica đã có dữ liệu vĩnh viễn trong mọi tình huống failover.

Khi nghiệp vụ yêu cầu độ bền cao:

- Chọn **write concern** phù hợp (ví dụ majority) theo chính sách deployment.
- Hiểu khả năng rollback của những ghi chưa được majority commit khi primary thay đổi.
- Không tự xem một HTTP response thành công là bằng chứng mọi hệ thống ngoài đã nhận trạng thái tồn kho.
- Dùng idempotency/operation log và đối soát để phục hồi khi commit outcome chưa rõ.

**Write concern không làm các update nhiều document trở thành một transaction** và không thay yêu cầu stock >= qty.

### 20.1. Đọc sau ghi từ replica khác

Nếu giảm hàng trên primary rồi ngay lập tức đọc từ một secondary có độ trễ, kết quả đọc có thể chưa phản ánh cập nhật mới nhất tùy read preference/read concern. Khi API cần số dư **ngay sau lần decrement**, **findAndModify returnNew(true)** thuận tiện hơn một thao tác cập nhật rồi đọc độc lập ở nơi khác.

### 20.2. Telemetry và business state

Khi xảy ra rollback/failover, metrics có thể đã ghi nhận một request thành công trước đó. Quy trình nghiệp vụ quan trọng cần bản ghi reservation/order và cơ chế đối soát thay vì chỉ dựa vào counter ở monitoring.

## 21. Atomicity không có nghĩa hàng được giữ mãi

Conditional decrement giải quyết vấn đề **không trừ quá số lượng tại thời điểm ghi**. Nó không giải quyết mọi tình huống:

- Hàng vật lý vừa bị hỏng nhưng chưa được cập nhật.
- Hai hệ thống kho khác nhau không đồng bộ.
- Reservation bị quá hạn nhưng chưa được giải phóng.
- Admin chỉnh sửa stock từ dữ liệu cũ.
- Đơn hàng bị hủy sau khi đã trừ.
- Hệ thống nhận lại một webhook thanh toán trùng.

Vì vậy, inventory model cần kết hợp trạng thái theo order/reservation, auditing, điều chỉnh kho và công cụ reconciliation.

### 21.1. Không dùng $set từ màn hình admin mà không có điều kiện

Màn hình quản trị đọc stock=10; sau đó có checkout trừ thành 9. Nếu admin lưu một form cũ bằng:

~~~javascript
{ $set: { stock: 10 } }
~~~

thì đã ghi đè thay đổi hợp lệ. Với thao tác điều chỉnh, có thể dùng **$inc theo delta**, hoặc **compare-and-set** với expected version/current value, kèm audit trail, phân quyền và xác nhận người thực hiện.

### 21.2. Hàng nhập cũng cần idempotency

Nếu cùng một phiếu nhập kho bị xử lý hai lần và cả hai đều chạy **$inc stock:+100**, tồn kho tăng sai. **$inc là nguyên tử nhưng không tự chống phát lại sự kiện nhập hàng**. Nguyên tắc requestId/unique operation áp dụng cho cả nhập và xuất.

## 22. Bulk updates không thay transaction nhiều document

Spring Data MongoDB hỗ trợ **BulkOperations** khi cần xử lý nhiều lệnh update hiệu quả:

~~~java
mongoTemplate.bulkOps(
    BulkOperations.BulkMode.ORDERED,
    InventoryDocument.class
);
~~~

Mỗi **updateOne** trong bulk có thể chứa điều kiện stock >= qty và $inc âm để bảo vệ **từng inventory document**. Nhưng cả batch không tự có atomicity nhiều document; nếu một item thất bại hoặc không match, các item trước đó có thể đã được cập nhật.

| Cách làm | Bảo đảm chính |
| --- | --- |
| updateFirst với _id + stock>=q | Nguyên tử một document |
| findAndModify với điều kiện | Nguyên tử một document và trả trạng thái |
| bulkOps nhiều updateOne | Giảm overhead nhiều lệnh, **không tự all-or-nothing** |
| MongoDB transaction | Nhóm các thao tác MongoDB hỗ trợ commit/rollback cùng transaction |
| Saga / compensation | Điều phối nhiều hệ thống, phục hồi/bù trừ theo workflow |

Không dùng **BulkMode.ORDERED** để suy rằng một item bị lỗi sẽ tự rollback các item đã ghi trước.

## 23. Kiểm soát dữ liệu thiếu, sai kiểu và schema

Một số document legacy có thể không có field stock, hoặc stock = null:

~~~javascript
{ _id: productId, tenantId: "shop-a", stock: null }
~~~

MongoDB **$inc** yêu cầu giá trị hiện tại thuộc kiểu số phù hợp; trên field null có thể gây lỗi, còn trên field thiếu có thể tạo field với giá trị delta khi update vô điều kiện.

Trong bài, điều kiện **stock: {$gte: quantity dương}** giúp không match document thiếu/null thông thường, thay vì phát sinh tồn kho âm. Nhưng đừng coi đây là biện pháp thay thế:

- Schema validation.
- Migration các document cũ.
- Giới hạn kiểu BSON và biên số.
- Kiểm thử dữ liệu sai kiểu.

### 23.1. Validation ở database

Nếu cần bảo vệ ngay cả khi có writer ngoài Spring Data, có thể xây **MongoDB collection validator** yêu cầu stock là số nguyên không âm, reserved không âm và các field bắt buộc đúng kiểu. Cần thiết kế ràng buộc BSON hợp lệ với dữ liệu hiện có và rollout qua migration có kiểm soát.

Validator không tự đảm bảo request idempotency hay trạng thái order; đó là những bất biến liên quan đến nhiều document/workflow.

### 23.2. Tránh đối chiếu sai đơn vị

Nếu stock tính theo **sản phẩm nguyên chiếc**, quantity cũng phải cùng đơn vị. Không trộn stock=100 gram với quantity=2 gói mà so sánh trực tiếp rồi $inc. Quy định đơn vị đo/pack size và chuyển đổi trước khi tạo filter/update.

## 24. Kiểm thử tích hợp: 20 yêu cầu tranh nhau 5 sản phẩm

Unit test mock MongoTemplate chỉ có thể xác nhận service đã tạo Query/Update như mong muốn; nó **không chứng minh** MongoDB thực thi điều kiện stock>=q đúng khi nhiều writer đồng thời.

Một integration test tốt cần:

1. Chèn inventory có stock=5.
2. Chuẩn bị **20 tác vụ** cùng muốn trừ quantity=1.
3. Dùng CountDownLatch cho chúng bắt đầu gần nhau.
4. Gọi **cùng service** sử dụng MongoTemplate.updateFirst.
5. Đếm số kết quả true.
6. Đọc stock thực sau khi tất cả tác vụ kết thúc.
7. Kiểm tra chỉ **5** request thành công và stock cuối **0**.
8. Xóa fixture chỉ trong MongoDB dành cho test.

### 24.1. Mẫu JUnit 5 với @DataMongoTest

~~~java
package com.example.inventory;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class ConcurrentStockDecrementTest {

    @Autowired
    MongoTemplate template;

    @Test
    void neverSellsMoreThanStockUnderConcurrentRequests()
            throws Exception {

        ObjectId id = new ObjectId();
        String tenant = "TEST-" + UUID.randomUUID();
        InventoryService service = new InventoryService(template);

        template.insert(new InventoryDocument(
            id,
            tenant,
            "CONCURRENT-BOOK",
            5L,
            0L,
            true,
            Instant.parse("2025-06-01T09:00:00Z")
        ));

        int requests = 20;
        ExecutorService workers =
            Executors.newFixedThreadPool(requests);
        CountDownLatch ready = new CountDownLatch(requests);
        CountDownLatch go = new CountDownLatch(1);

        try {
            List<Future<Boolean>> results = new ArrayList<>();

            for (int i = 0; i < requests; i++) {
                results.add(workers.submit(() -> {
                    ready.countDown();
                    go.await();
                    return service.tryDecreaseStock(
                        id, tenant, 1L
                    );
                }));
            }

            assertThat(ready.await(15, TimeUnit.SECONDS))
                .isTrue();
            go.countDown();

            int accepted = 0;
            for (Future<Boolean> future : results) {
                if (future.get(30, TimeUnit.SECONDS)) {
                    accepted++;
                }
            }

            assertThat(accepted).isEqualTo(5);

            InventoryDocument after = template.findById(
                id, InventoryDocument.class
            );

            assertThat(after).isNotNull();
            assertThat(after.stock()).isEqualTo(0L);
            assertThat(after.reserved()).isEqualTo(0L);
        } finally {
            go.countDown();
            workers.shutdownNow();
            template.remove(
                Query.query(Criteria.where("_id").is(id)),
                InventoryDocument.class
            );
        }
    }
}
~~~

**Chỉ chạy trên MongoDB test instance**, ví dụ một môi trường Testcontainers có phiên bản MongoDB phù hợp. Test trên không tạo MongoDB container giúp giữ ví dụ tập trung vào logic; cấu hình kết nối test phải do dự án cung cấp.

### 24.2. Vì sao dùng latch?

Nếu chạy lần lượt 20 request, số lần thành công cũng có thể là 5, nhưng test không tạo áp lực cạnh tranh thực. **CountDownLatch** giúp các tác vụ đợi cùng một tín hiệu bắt đầu.

Test vẫn không bảo đảm mọi thread thực sự chạy cùng một chu kỳ CPU, nhưng tạo điều kiện kiểm thử contention tốt hơn một vòng lặp tuần tự.

### 24.3. Tiêu chí đúng của concurrency test

Nếu stock ban đầu là **N**, mọi request có quantity=1 và không có phép nhập hàng đồng thời, thì:

\[
\text{successCount}\le N,\quad stock_{\mathrm{final}}=N-\text{successCount}.
\]

Trong ví dụ có đủ 20 request và không có lỗi hạ tầng, mong đợi chính xác **successCount=5**, stock cuối=0. Nếu test gặp timeout/exception, phải phân loại lỗi đó chứ không âm thầm xem như update trả false.

### 24.4. Giới hạn của test này

Test chứng minh cạnh tranh giữa nhiều phép **conditional decrement cùng document** trên MongoDB test. Nó **chưa chứng minh**:

- Không có double decrement khi một HTTP request bị retry.
- Transaction inventory + order commit cùng nhau.
- Reservation cancel idempotent.
- Mức chịu tải thực tế ở p99 dưới hàng nghìn request/s.
- Các hệ thống kho bên ngoài cùng nhất quán.

Các yêu cầu đó cần thêm test riêng.

## 25. Kiểm thử biên: thiếu hàng, tenant và quantity

Với cùng InventoryService, nên có các test:

| Trường hợp | Kỳ vọng |
| --- | --- |
| stock=3, quantity=3 | modifiedCount=1, stock=0 |
| stock=3, quantity=4 | Không update, stock vẫn 3 |
| stock=0, quantity=1 | Không update, stock vẫn 0 |
| active=false, stock=10 | Không update |
| tenantId không khớp | Không update, không lộ tồn kho |
| ID không tồn tại | Không update |
| quantity=0 | IllegalArgumentException, không gửi update |
| quantity=-1 | IllegalArgumentException, không tăng stock |
| quantity lớn hơn policy | Request bị từ chối trước update |
| stock thiếu/null/sai kiểu | Không coi là tồn dương hợp lệ; cần migration/validation |
| update lỗi mạng | Không tự biến thành false hoặc retry mù |
| requestId được gửi lại | Không giảm lần nữa nếu đã xử lý thành công |

### 25.1. Ví dụ test không đủ hàng

~~~java
@Test
void doesNotDecrementWhenQuantityExceedsStock() {
    ObjectId id = new ObjectId();
    String tenant = "TEST-" + UUID.randomUUID();

    template.insert(new InventoryDocument(
        id, tenant, "BOOK-LOW", 2L, 0L, true, Instant.now()
    ));

    try {
        InventoryService service = new InventoryService(template);

        boolean accepted =
            service.tryDecreaseStock(id, tenant, 3L);

        assertThat(accepted).isFalse();

        InventoryDocument after = template.findById(
            id, InventoryDocument.class
        );
        assertThat(after).isNotNull();
        assertThat(after.stock()).isEqualTo(2L);
    } finally {
        template.remove(
            Query.query(Criteria.where("_id").is(id)),
            InventoryDocument.class
        );
    }
}
~~~

Phương thức trên được đặt **trong cùng lớp ConcurrentStockDecrementTest** ở phần trước, nơi đã có template và các import dùng chung.

### 25.2. Thử nghiệm đúng tenant

Chèn một InventoryDocument thuộc tenant A, sau đó gọi service với tenant B nhưng cùng ObjectId. Kết quả mong đợi là false và stock không đổi. Sau đó gọi với tenant A để xác nhận chỉ tenant đúng mới được giảm theo quyền đã xác thực.

### 25.3. Thử nghiệm idempotency khác với concurrency

Gửi **cùng requestId** hai lần không phải hai lần mua hàng độc lập. Test cần:

1. Trừ hàng và ghi reservation lần đầu.
2. Gửi lại cùng requestId/payload.
3. Xác nhận cùng một reservation/result được trả.
4. Stock chỉ giảm một lần.
5. Gửi requestId giống nhưng payload khác, phải phát hiện conflict.

Test này yêu cầu tầng reservation/transaction hoặc workflow idempotency hoàn chỉnh; không thể chỉ gọi tryDecreaseStock hai lần rồi mong nó biết cùng request.

## 26. Chẩn đoán vấn đề dưới tải đồng thời

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Stock âm | Có writer trừ bằng $inc mà thiếu stock>=q | Rà soát mọi đường ghi, validation và migration |
| Hai checkout cùng báo thành công khi còn một món | read-check-save hoặc điều kiện không nằm trong update | Dùng conditional atomic decrement |
| modifiedCount=0 dù UI thấy còn hàng | Concurrent writer vừa trừ, tenant/status sai hoặc UI cache cũ | Kiểm tra filter và trạng thái sau ghi |
| modifiedCount=1 nhưng order không có | Hai thao tác thuộc collection khác, không transaction/workflow | Transaction, outbox hoặc saga |
| Cùng order trừ hai lần | HTTP retry, duplicate webhook, không có idempotency | RequestId/unique reservation và workflow |
| Timeout sau update rồi retry làm mất thêm hàng | Unknown outcome bị hiểu là thất bại | Tra cứu operation log trước retry |
| Cancel một order cộng stock hai lần | Release không kiểm tra reservation state | State transition idempotent |
| reserved âm | Nhiều release hoặc thiếu guard reserved>=q | Conditional state, validation, transaction |
| Ghi hàng thất bại do write conflict | Transaction nhiều writer tranh document | Retry có backoff và idempotency |
| p99 tăng mạnh trên SKU hot | Contention trên cùng inventory document | Điều tiết tải, queue, mô hình partition hợp lý |
| Query update chậm | Không có index hợp lý cho khóa lookup | Xem query plan, key lookup, index |
| admin sửa tồn làm mất checkout mới | Dùng $set từ snapshot cũ | Update delta hoặc CAS/version |
| Reactive giảm hai lần | Hai subscription vào publisher write | Trả Mono đúng lifecycle, idempotency |
| Session hết hạn không hoàn hàng | TTL chỉ xóa reservation record | Workflow expire + compensation |
| Đọc sau ghi thấy stock cũ | Replica lag/read preference | findAndModify returnNew hoặc read policy phù hợp |
| Không đồng nhất giữa các kho | Mỗi kho nằm document khác, chưa có allocation policy | Thiết kế multi-warehouse và transaction/saga |

### 26.1. Quy trình điều tra thực tế

1. Xác nhận **bất biến nghiệp vụ**: stock biểu diễn available hay physical?
2. Liệt kê tất cả nguồn ghi inventory (checkout, import, cancel, admin, migration).
3. Xem update thực tế có **stock >= qty và $inc âm trong cùng một lệnh** không.
4. Kiểm tra query gồm đúng tenant, ID/SKU/warehouse và trạng thái.
5. Đọc UpdateResult và phân biệt **0** với exception/timeout.
6. Xác định có requestId/idempotency ledger không.
7. Nếu nhiều document, xác nhận transaction/session hoặc compensation workflow.
8. Kiểm tra index, hotspot SKU và thời gian giữ transaction.
9. Tái hiện bằng test concurrent, duplicate request và lỗi mạng/commit chưa rõ.
10. Chỉ sau đó tối ưu hiệu năng; không bỏ precondition để tăng throughput.

## 27. Những câu hỏi thiết kế quan trọng

### 27.1. Nếu số lượng nhập và xuất đồng thời thì sao?

Nhập kho bằng $inc stock:+q và xuất kho bằng conditional $inc stock:-q đều là thao tác trên cùng document, nên được sắp xếp theo thứ tự nguyên tử tại server. Một request xuất có thể thành công hoặc không, tùy thứ tự cập nhật với đợt nhập. Đây là hành vi hợp lý nếu nghiệp vụ chấp nhận phân phối ngay khi hàng nhập được ghi nhận.

Nếu hàng nhập phải qua kiểm định mới được bán, không cộng thẳng vào stock available; cần model trạng thái kho riêng.

### 27.2. Có nên luôn dùng findAndModify để trả stock?

Không. Nếu caller chỉ cần biết thành công hay không, updateFirst + UpdateResult là đủ và có thể giảm chi phí trả entity. Dùng findAndModify nếu số dư sau cập nhật là một phần hợp đồng API.

### 27.3. Có nên đợi đến khi thanh toán xong mới trừ?

Tùy yêu cầu. Nếu thanh toán kéo dài, không giữ hàng có thể khiến stock bị bán hết giữa lúc khách thanh toán. Mô hình **reserve → consume/cancel/expire** thường rõ ràng hơn, nhưng yêu cầu thêm transaction/idempotency/cleanup.

### 27.4. Có thể dùng @Version thay điều kiện stock>=q không?

@Version cho phép phát hiện thay đổi giữa đọc và ghi ở các thao tác được hỗ trợ, nhưng nếu không có logic kiểm tra stock tại bản ghi mới và retry phù hợp, **không tự bảo đảm business invariant**. Conditional decrement là biểu thức trực tiếp của invariant và thường gọn hơn khi chỉ cần thay đổi counter.

### 27.5. Có cần transaction cho một decrement không?

Không, nếu mục tiêu chỉ là cập nhật một inventory document có điều kiện. MongoDB đã cung cấp atomicity cho một thao tác trên một document. Transaction cần khi phải điều phối nhiều document/collection cùng commit hoặc rollback.

### 27.6. Có thể dùng upsert để giảm hàng cho SKU mới không?

Không phù hợp với mô hình này. Nếu inventory không tồn tại, việc trừ hàng không nên tự tạo document có giá trị âm. Hãy tạo inventory qua một workflow nhập hàng riêng với validation và unique key.

## 28. Bài tập thực hành

### Bài tập 1: tìm race condition

Service đọc stock=2 rồi nếu đủ thì save(stock-1). Hai request đồng thời đều mua 2 món, lỗi có thể là gì?

**Đáp án:** Cả hai đều kiểm tra từ stock=2 và báo thành công; save từ dữ liệu cũ có thể ghi một giá trị không phản ánh tổng số đã bán. Cần đưa điều kiện stock>=quantity vào chính lệnh cập nhật nguyên tử.

### Bài tập 2: viết MongoDB updateOne

Trừ 3 món cho productId, chỉ khi còn đủ và active=true:

~~~javascript
db.inventories.updateOne(
  {
    _id: productId,
    tenantId: "shop-a",
    active: true,
    stock: { $gte: 3 }
  },
  { $inc: { stock: -3 } }
);
~~~

**Giải thích:** filter và cập nhật được thực hiện trong một thao tác ghi.

### Bài tập 3: Java MongoTemplate

Điền hai biểu thức quan trọng:

~~~java
Query query = Query.query(
    Criteria.where("_id").is(id)
        .and("tenantId").is(tenant)
        .and("stock").gte(quantity)
);

Update update = new Update()
    .inc("stock", -quantity);
~~~

**Đáp án:** gte(quantity) trong Query và inc âm trong Update.

### Bài tập 4: stock không đủ

Stock hiện tại=2, quantity=3. Một updateFirst có điều kiện stock>=quantity và $inc âm trả modifiedCount bao nhiêu?

**Đáp án:** 0 khi lệnh acknowledged, không có writer khác; stock không đổi. Không tự gọi đây là lỗi driver.

### Bài tập 5: đọc số dư sau ghi

API phải trả chính xác giá trị stock do phép trừ này tạo ra. Có nên updateFirst rồi findById?

**Đáp án:** Ưu tiên **findAndModify(returnNew=true)** để nhận trạng thái sau chính thao tác đó. Read độc lập có thể quan sát một cập nhật sau nữa.

### Bài tập 6: quantity âm

Nếu quantity=-5 rồi code dùng inc("stock", -quantity), chuyện gì xảy ra?

**Đáp án:** $inc sẽ cộng 5 vào stock. Phải validate quantity>0 trước khi tạo query/update.

### Bài tập 7: tenant

Người dùng shop-a gửi inventoryId của shop-b. Chỉ filter theo _id đã an toàn chưa?

**Đáp án:** Không. Cần authorization và ràng buộc tenant server-side trong update; không tin tenantId do client tự khai.

### Bài tập 8: reserved stock

Stock=10, reserved=0; reserve 4 sản phẩm. Sau update nguyên tử, hai field phải là bao nhiêu?

**Đáp án:** stock=6, reserved=4, thông qua cùng update **$inc stock:-4, reserved:+4**.

### Bài tập 9: cancel hai lần

Nếu reservation đã cancel, callback cancel lần hai có được cộng stock nữa không?

**Đáp án:** Không. Chỉ hoàn khi transition RESERVED→CANCELLED thành công; cần transaction/workflow có idempotency.

### Bài tập 10: retry timeout

Client không nhận response dù server có thể đã trừ stock. Có nên gọi lại update không có requestId?

**Đáp án:** Không retry mù. Phải có idempotency key và đối soát trạng thái operation; việc gửi lại có thể làm trừ thêm.

### Bài tập 11: @Version

Entity có @Version nhưng method MongoTemplate.updateFirst chỉ lọc theo ID, tenant và stock. Có chắc update tự từ chối mọi expectedVersion stale không?

**Đáp án:** Không. Nếu yêu cầu compare-and-set theo version, đưa expectedVersion vào filter hoặc dùng API có hợp đồng version phù hợp; không nhầm tự tăng version với kiểm tra expectedVersion.

### Bài tập 12: nhiều SKU

Checkout trừ thành công SKU A nhưng SKU B hết. Một updateOne trên A có tự rollback không?

**Đáp án:** Không. Cần transaction nhiều document hoặc saga có bù trừ và idempotency.

### Bài tập 13: reactive

ReactiveMongoTemplate.updateFirst trả kiểu kết quả nào trong ví dụ, và service có thể map ra gì?

**Đáp án:** Mono<UpdateResult>, có thể **map** modifiedCount thành Mono<Boolean>. Không gọi block() trong WebFlux.

### Bài tập 14: reactive double subscribe

Tạo một Mono chứa lệnh giảm hàng rồi subscribe hai lần, có thể gây vấn đề gì?

**Đáp án:** Hai lần subscribe có thể kích hoạt hai cập nhật. Reactive không tự chống áp dụng trùng một business request.

### Bài tập 15: concurrency test

Stock=3; có 10 request độc lập đồng thời, mỗi request giảm 1. Không có nhập hàng hoặc lỗi hạ tầng. Sau các request, số thành công và stock cuối?

**Đáp án:** 3 request thành công, 7 request không khớp filter, stock cuối=0.

### Bài tập 16: admin adjustment

Admin đọc stock=12 rồi checkout giảm thành 11. Admin save(stock=12) từ form cũ. Hãy đề xuất cách an toàn hơn.

**Đáp án:** Dùng update delta với $inc hoặc conditional compare-and-set/@Version, phân quyền và audit. Không ghi $set từ snapshot cũ mà không kiểm tra cạnh tranh.

### Bài tập 17: TTL reservation

Một reservation hết hạn được MongoDB TTL tự xóa. Tồn kho có tự được hoàn không?

**Đáp án:** Không. TTL không tự gọi $inc lên inventory; cần quy trình expire/release có trạng thái và idempotency.

### Bài tập 18: dữ liệu legacy

Document có stock=null. Một câu lệnh $inc âm vô điều kiện có an toàn không?

**Đáp án:** Không. $inc trên null có thể lỗi; phải validate/migrate dữ liệu và luôn bảo vệ query bằng điều kiện stock phù hợp.

## 29. Checklist trước khi áp dụng vào production

- **Bất biến:** stock là available, physical hay tổng bao gồm reserved?
- **Input:** quantity là số nguyên dương, trong giới hạn và cùng đơn vị chưa?
- **Phân quyền:** tenant/warehouse lấy từ context đáng tin cậy chưa?
- **Định danh:** query chọn tối đa một inventory document đúng chưa?
- **Atomicity:** stock>=quantity và $inc âm có nằm trong **cùng lệnh** không?
- **Upsert:** đã đảm bảo không tự tạo inventory âm khi không match chưa?
- **Kết quả:** phân biệt modifiedCount=0, acknowledged và exception chưa?
- **Response:** có tránh lộ tồn kho của tenant khác không?
- **Idempotency:** có requestId/reservationId để tránh xử lý cùng checkout hai lần không?
- **Timeout:** có chiến lược unknown outcome, không retry mù không?
- **Reservation:** reserve/consume/cancel/expire có state transition rõ chưa?
- **Transaction:** những ghi nhiều document có cùng commit/rollback hoặc compensation chưa?
- **Outbox:** event/payment bên ngoài có được xử lý nhất quán không?
- **Admin:** không ghi $set từ snapshot cũ mà thiếu CAS/version chưa?
- **Schema:** stock/reserved lưu numeric BSON hợp lệ, không âm chưa?
- **Index:** query lookup dùng _id hoặc compound key phù hợp chưa?
- **Hot SKU:** có đo write contention, p95/p99 và số conflict không?
- **Reactive:** không block hoặc subscribe cập nhật hai lần chưa?
- **Durability:** write concern/read concern phù hợp nhu cầu chưa?
- **Testing:** đã kiểm thử concurrency, thiếu hàng, tenant, retry và cancel trùng chưa?
- **Monitoring:** có đối soát tồn kho với order/reservation và hệ thống kho thực chưa?

## 30. Tổng kết

1. **Đọc rồi kiểm tra rồi save** không an toàn cho tồn kho khi nhiều writer cập nhật cùng document.
2. **Giảm hàng nguyên tử** là một thao tác MongoDB gồm **stock >= quantity** trong filter và **$inc stock:-quantity** trong update.
3. Với cùng một inventory document, điều kiện và cập nhật được thực thi nguyên tử, giúp ngăn bán vượt tồn khi mọi writer tuân thủ quy tắc.
4. **MongoTemplate.updateFirst** trả UpdateResult; **modifiedCount=1** trong mô hình này biểu diễn một decrement thành công.
5. **modifiedCount=0 không tự là lỗi hệ thống**, còn timeout có thể để lại kết quả ghi chưa chắc chắn.
6. **findAndModify(returnNew=true)** phù hợp khi cần nhận stock ngay sau lần cập nhật.
7. **Validate quantity>0**, giới hạn tenant, chọn đúng ID/SKU/warehouse và không upsert là những điều kiện an toàn tối thiểu.
8. **stock và reserved có thể cập nhật cùng document nguyên tử** qua hai phép $inc, nhưng reservation workflow nhiều document vẫn cần thiết kế nhất quán.
9. **Atomic không đồng nghĩa idempotent**: request HTTP gửi lại có thể tiếp tục trừ nếu còn hàng.
10. **Unique requestId + transaction hoặc workflow có kiểm soát** cần thiết để tránh xử lý lại reservation/order.
11. **@Version** giúp optimistic locking trong những trường hợp được hỗ trợ; không thay thế trực tiếp điều kiện số lượng.
12. **ReactiveMongoTemplate** giữ cùng semantics MongoDB nhưng dùng Mono và subscription; không block hoặc subscribe lặp.
13. **Một update không làm các collection/order/payment cùng atomic**; dùng transaction, outbox hay saga khi cần.
14. **Index, schema validation và observability** giúp vận hành ổn định nhưng không thay business invariant.
15. **Concurrency integration test** trên MongoDB thật phải chứng minh số request thành công không vượt tồn và stock cuối đúng.

Nắm vững **giảm tồn kho bằng điều kiện số lượng và inc nguyên tử** giúp dịch vụ **SPRING_DATA_MONGODB** tránh bán vượt hàng tại điểm cập nhật, có tín hiệu rõ cho tình huống không đủ hàng và tạo nền tảng vững chắc cho reservation, thanh toán, transaction, reactive access và kiểm thử cạnh tranh.

### Tài liệu tham khảo

- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/) — atomicity trên một document và việc đặt expected value vào filter.
- [MongoDB Manual — $inc Update Operator](https://www.mongodb.com/docs/manual/reference/operator/update/inc/) — tăng/giảm giá trị số và hành vi với null/missing.
- [MongoDB Manual — findAndModify](https://www.mongodb.com/docs/manual/reference/method/db.collection.findAndModify/) — tìm và cập nhật một document, return new.
- [Spring Data MongoDB — Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html) — MongoTemplate.updateFirst, findAndModify, Update.inc.
- [Spring Data MongoDB — Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.optimistic-locking) — @Version và xung đột cập nhật.
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — phạm vi retryable writes của driver và server.
