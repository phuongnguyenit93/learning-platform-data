# insert, save, findById, findOne và find

## 1. Mục tiêu: chọn đúng thao tác của MongoTemplate

Trong chương **MongoTemplate** thuộc module **Spring Data MongoDB**, năm phương thức `insert`, `save`, `findById`, `findOne` và `find` tạo thành nhóm thao tác cơ bản để ghi và đọc document. Chúng thường được dùng khi yêu cầu truy vấn hoặc kiểm soát hành vi ghi vượt ra ngoài các phương thức suy diễn của `MongoRepository`.

Giả sử một ứng dụng bán hàng quản lý collection `catalog_products`. Chúng ta cần tạo sản phẩm mới, sửa tên sản phẩm đã tồn tại, tìm chính xác một sản phẩm theo ID, tìm sản phẩm mới nhất đang bán và lấy danh sách sản phẩm còn hàng. Nếu dùng nhầm API, một thao tác “chỉ tạo mới” có thể trở thành cập nhật ghi đè, hoặc một truy vấn “lấy sản phẩm đầu tiên” có thể trả kết quả không ổn định.

| API | Câu hỏi giải quyết | Kết quả điển hình | Điều cần chú ý |
|---|---|---|---|
| `insert(entity)` | Tạo **document mới** | Entity sau thao tác ghi | Trùng `_id` hoặc unique key sẽ bị từ chối |
| `save(entity)` | Lưu entity mới hoặc trạng thái mới của entity đã có | Entity sau thao tác ghi | Có thể insert/update hoặc replace; không phải create-only |
| `findById(id, Type.class)` | Tìm một document theo `_id` | Entity hoặc `null` | Chỉ chọn theo ID, không tự thêm điều kiện tenant/quyền |
| `findOne(query, Type.class)` | Tìm tối đa một document thỏa điều kiện | Entity hoặc `null` | Nếu nhiều bản ghi khớp, cần `sort` rõ ràng |
| `find(query, Type.class)` | Tìm nhiều document thỏa điều kiện | `List<Entity>`, có thể rỗng | Cần kiểm soát filter, sort, limit và kích thước |

**Một nguyên tắc xuyên suốt:** `MongoTemplate` ánh xạ giữa **property Java** và **field BSON** khi có entity type. Điều đó khác với làm việc trực tiếp trên `MongoCollection<org.bson.Document>` của driver, nơi phải dùng đúng tên field BSON.

> Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x và driver đồng bộ. Với các phiên bản major khác, hãy kiểm tra API và cấu hình dự án. Các ví dụ code minh họa cách dùng; chưa chạy kiểm thử thực thi trong bước biên soạn bài này.

## 2. Chuẩn bị entity và dữ liệu mẫu

Khi dự án đã có dependency `spring-boot-starter-data-mongodb` và URI MongoDB được cấu hình đúng, Spring Boot thường cung cấp bean `MongoTemplate`. Ứng dụng có thể inject bean này vào service thay vì tự tạo `MongoClient` và converter ở từng nơi.

Các ví dụ trong bài đặt trong package `com.example.catalog`. Ta chọn entity mutable để minh họa cách đọc, sửa thuộc tính rồi lưu lại; phần optimistic locking sẽ có một model riêng.

**CatalogProduct.java**

~~~java
package com.example.catalog;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_products")
public class CatalogProduct {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("display_name")
    private String name;

    @Field("stock_qty")
    private int stock;

    private String status;
    private String tenantId;
    private Instant createdAt;

    protected CatalogProduct() {
        // Spring Data có thể materialize entity từ document.
    }

    public CatalogProduct(
            String id, String name, int stock, String status,
            String tenantId, Instant createdAt) {
        this.id = id;
        this.name = name;
        this.stock = stock;
        this.status = status;
        this.tenantId = tenantId;
        this.createdAt = createdAt;
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public int getStock() { return stock; }
    public String getStatus() { return status; }
    public String getTenantId() { return tenantId; }
    public Instant getCreatedAt() { return createdAt; }

    public void setName(String name) { this.name = name; }
    public void setStock(int stock) { this.stock = stock; }
    public void setStatus(String status) { this.status = status; }
}
~~~

Điểm quan trọng:

- `@Document(collection = "catalog_products")` chỉ định collection cho entity.
- `@MongoId(FieldType.STRING)` ánh xạ `id` sang BSON `_id` kiểu String. Nếu dùng `@Id String`, Spring Data có thể chuyển chuỗi trông như ObjectId hợp lệ thành BSON ObjectId; phải thiết kế kiểu khóa nhất quán.
- `@Field("display_name")` đổi tên property `name` trong BSON; `@Field("stock_qty")` đổi tên `stock`.
- `createdAt` được Spring Data chuyển đổi sang BSON Date theo bộ converter được cấu hình. BSON Date có độ chính xác mili giây.
- Model **chưa có `@Version`**, vì thế một lần `save` đối với bản đọc cũ có thể ghi đè trạng thái vừa được worker khác cập nhật.

Một document sau khi lưu có hình dạng gần như sau (lược bỏ metadata `_class` nếu framework lưu):

~~~json
{
  "_id": "p-101",
  "display_name": "Bình nước giữ nhiệt",
  "stock_qty": 12,
  "status": "ACTIVE",
  "tenantId": "tenant-a",
  "createdAt": { "$date": "2026-11-20T08:00:00Z" }
}
~~~

Hãy phân biệt **tên Java** (`name`, `stock`, `id`) với **tên lưu trữ** (`display_name`, `stock_qty`, `_id`). Phần sau sẽ dùng chính sự khác nhau này để kiểm tra truy vấn.

## 3. insert: tạo document mới, không ghi đè document cũ

`MongoTemplate.insert(entity)` diễn đạt ý định *tạo mới*. Với entity có ID do ứng dụng cung cấp:

~~~java
import java.time.Instant;
import org.springframework.data.mongodb.core.MongoTemplate;

public CatalogProduct createProduct(MongoTemplate mongo) {
    CatalogProduct product = new CatalogProduct(
            "p-101", "Bình nước giữ nhiệt", 12, "ACTIVE",
            "tenant-a", Instant.parse("2026-11-20T08:00:00Z"));

    return mongo.insert(product);
}
~~~

Đoạn trên là một method minh họa được đặt trong class service có tham số `MongoTemplate`; import `CatalogProduct` tương ứng nếu class ở package khác.

### 3.1. Điều gì xảy ra nếu đã có _id?

MongoDB tạo unique index trên `_id` cho mỗi collection. Nếu gọi lại:

~~~java
mongo.insert(new CatalogProduct(
        "p-101", "Tên khác", 3, "ACTIVE",
        "tenant-a", Instant.parse("2026-11-20T09:00:00Z")));
~~~

trong khi `p-101` đã tồn tại, lệnh insert bị từ chối do khóa trùng. Khi sử dụng Spring Data với cơ chế dịch exception thông thường, ứng dụng có thể nhận `DuplicateKeyException`. **Nó không tự sửa tên hoặc tồn kho của document đã có.**

Không nên gọi `existsById` hoặc `findById` trước `insert` rồi coi đó là biện pháp bảo đảm duy nhất. Hai request có thể cùng thấy “chưa tồn tại”, sau đó cùng cố insert. Chính **unique index tại thời điểm ghi** mới ngăn hai document cùng ID.

Nếu có business key như `sku` hoặc email phải duy nhất, cần thêm unique index tương ứng, không chỉ dựa vào `_id`. Việc tạo unique index trên collection có sẵn duplicate phải đi kèm kiểm tra và xử lý dữ liệu trước đó.

### 3.2. ID sinh tự động và kiểu ID

Spring Data/driver có thể hỗ trợ cấp ID tự động khi entity không cung cấp khóa phù hợp, đặc biệt với `ObjectId` hoặc `String` theo mapping được hỗ trợ. Nhưng hành vi gán ID cho class mutable, record bất biến hoặc custom type có thể khác nhau; cần kiểm tra trên phiên bản và kiểu entity cụ thể.

Trong toàn bộ bài này, **ID được cấp tường minh** (`p-101`, `p-102`, ...), để không phụ thuộc vào cơ chế sinh khóa. Nếu ứng dụng chọn UUID/String riêng, hãy bảo đảm quy trình cấp khóa không tái sử dụng ID do lỗi logic.

### 3.3. Lưu một tập đối tượng

`MongoTemplate` cũng có các overload để insert nhiều entity. Thao tác này phù hợp import theo lô, nhưng đừng nhầm một lệnh bulk với **transaction nguyên tử cho toàn bộ lô**. Khi có document trùng khóa, kết quả một số thao tác trước đó có thể đã được ghi; cần hiểu cách API và driver xử lý batch, lỗi và retry.

Với luồng nhập cần có tính idempotent, nên thiết kế khóa ổn định, unique index, chính sách retry và checkpoint, không chỉ gọi insertAll rồi giả định “hoặc tất cả thành công hoặc tất cả bị hủy”.

## 4. save: lưu trạng thái hiện tại, có thể cập nhật hoặc tạo mới

`MongoTemplate.save(entity)` phù hợp khi ứng dụng cần **lưu trạng thái của entity**. Với model không có `@Version` ở trên, save thông thường xử lý trường hợp document chưa có và trường hợp document đã tồn tại theo ID; khi đã tồn tại, nó có thể **thay thế nội dung document dựa trên object đang lưu**.

Ví dụ:

~~~java
CatalogProduct product = mongo.findById(
        "p-101", CatalogProduct.class);

if (product == null) {
    throw new IllegalArgumentException("Không có sản phẩm p-101");
}

product.setName("Bình giữ nhiệt inox");
CatalogProduct saved = mongo.save(product);
~~~

Kết quả mong đợi: MongoDB lưu tên mới tại trường `display_name`. Không cần tự xây dựng raw BSON vì Spring Data biết metadata entity.

### 4.1. Vì sao save không phải lệnh “update một field”?

Khi gọi `save`, ứng dụng đưa **trạng thái entity** cho converter để ghi. Đối với entity không có `@Version`, nó có thể thực hiện lưu theo semantics thay thế/upsert document theo ID, thay vì một phép `$set` đơn lẻ cho trường vừa sửa.

Hệ quả:

- Nếu entity được đọc từ lâu, trạng thái cũ trong object có thể **ghi đè** thay đổi mới hơn trên MongoDB.
- Một entity được dựng mới nhưng chỉ gán `id` và `name` không phải cách cập nhật từng phần an toàn: những property còn lại có thể bị ghi bằng giá trị mặc định/null hoặc không còn trong document.
- Trường không được mapping trong object Java có thể bị mất khi document bị thay thế, tùy đường ghi và converter.
- Callback/auditing/custom converter được Spring Data áp dụng theo API và cấu hình; đừng xem save chỉ là một lệnh BSON raw.

Nếu ý định là **chỉ giảm tồn kho** hoặc **chỉ sửa tên mà giữ nguyên các field khác**, hãy cân nhắc `updateFirst`/`findAndModify` với `Update.set`/`inc` và điều kiện bảo vệ phù hợp.

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

Query byId = Query.query(Criteria.where("id").is("p-101"));
Update rename = new Update().set("name", "Bình giữ nhiệt inox");

mongo.updateFirst(byId, rename, CatalogProduct.class);
~~~

Với `CatalogProduct.class`, Spring Data ánh xạ `id` thành `_id` và `name` thành `display_name`. Lệnh cập nhật chỉ target field đã nêu. Tuy nhiên cập nhật này **không tự bảo đảm** không có request cạnh tranh; nếu nghiệp vụ cần version hoặc trạng thái kỳ vọng, thêm điều kiện vào `Query`.

### 4.2. upsert không phải quyền tự động tạo mới

Với entity không có version và ID do ứng dụng cung cấp, `save` có thể tạo document khi chưa có và lưu thay thế khi đã có. Vì vậy:

- Muốn **create-only**: ưu tiên `insert`.
- Muốn **ghi trạng thái đầy đủ** đã được kiểm tra: `save` có thể phù hợp.
- Muốn **update-only nếu tồn tại và thỏa điều kiện**: dùng `updateFirst` hoặc `findAndModify` với query rõ ràng.
- Muốn **upsert có điều kiện và thay đổi từng field**: xem xét `upsert` cùng `Update`, `setOnInsert` và unique index đúng nghiệp vụ; kiểm thử race condition.

Không suy đoán rằng `save` tự biết một entity “mới về nghiệp vụ” hay “đã tồn tại” chỉ dựa trên việc ta vừa tạo object bằng `new`. ID, version và chiến lược nhận biết entity mới có thể ảnh hưởng đường ghi của Spring Data.

## 5. findById: tìm chính xác bằng khóa _id

`findById` là lựa chọn rõ ràng khi bạn đã có ID:

~~~java
CatalogProduct found = mongo.findById(
        "p-101", CatalogProduct.class);

if (found == null) {
    // Không tìm thấy document với ID đó tại thời điểm đọc.
}
~~~

Chữ ký thường dùng:

~~~java
<T> T findById(Object id, Class<T> entityClass);
<T> T findById(Object id, Class<T> entityClass, String collectionName);
~~~

Đây là **minh họa chữ ký** trong tài liệu, không phải định nghĩa hàm Java nằm độc lập ngoài interface.

`findById` tìm bằng `_id`, chuyển ID Java theo mapping của entity, materialize kết quả và trả entity hoặc `null` nếu không có document. Nó **không trả `Optional<T>` như `MongoRepository.findById`**. Có thể bọc kết quả vào `Optional.ofNullable(...)` ở ranh giới service nếu muốn.

Với entity gắn `@Document(collection = "catalog_products")`, `findById(id, CatalogProduct.class)` biết collection cần đọc. Overload thứ ba cho phép dùng tên collection khác khi thực sự cần; khi đó phải bảo đảm collection được truyền chứa đúng schema entity.

### 5.1. ID không tự bảo vệ phân quyền tenant

Giả sử `p-101` thuộc `tenant-a`. Câu lệnh:

~~~java
mongo.findById("p-101", CatalogProduct.class);
~~~

chỉ lọc theo ID. Nó **không tự thêm điều kiện `tenantId`**. Với dữ liệu đa tenant trong cùng collection, cần áp dụng kiểm soát quyền, ví dụ dùng `findOne` với cả ID và tenant:

~~~java
Query withinTenant = Query.query(
        Criteria.where("id").is("p-101")
                .and("tenantId").is("tenant-a"));

CatalogProduct ownProduct =
        mongo.findOne(withinTenant, CatalogProduct.class);
~~~

Trong code thực, tenant phải lấy từ **ngữ cảnh xác thực đã được tin cậy**, không phải tin nguyên một chuỗi tenant do client bất kỳ gửi lên. Nếu tất cả document của cùng entity có tenant, cần nhất quán điều kiện này trong find, update, delete và aggregation.

### 5.2. Đọc được không có nghĩa có thể ghi sau đó

Hai bước `findById → sửa Java object → save` không tạo transaction tự động và không ngăn một request khác cập nhật document giữa hai bước. Để bảo vệ lost update, cân nhắc `@Version` hoặc một câu lệnh cập nhật điều kiện. Việc đọc từ secondary còn có thể quan sát dữ liệu trễ nếu cấu hình read preference cho phép.

## 6. findOne: tìm một kết quả từ Query linh hoạt

`findOne(Query, Class<T>)` sử dụng **Query** được xây dựng từ `Criteria`, thay vì giới hạn ở `_id`:

~~~java
Query available = Query.query(
        Criteria.where("status").is("ACTIVE")
                .and("stock").gt(0));

CatalogProduct one =
        mongo.findOne(available, CatalogProduct.class);
~~~

Filter BSON tương đương:

~~~json
{
  "status": "ACTIVE",
  "stock_qty": { "$gt": 0 }
}
~~~

Nếu nhiều document thỏa filter, `findOne` chỉ trả **một** document hoặc `null` khi không khớp. **Không có sort thì không có bảo đảm rằng đó là sản phẩm mới nhất, rẻ nhất hay có ID nhỏ nhất.**

### 6.1. Dùng sort để xác định “một bản ghi đầu tiên”

Giả sử cần sản phẩm mới nhất:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query newestActive = Query.query(Criteria.where("status").is("ACTIVE"));
newestActive.with(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")));

CatalogProduct newest =
        mongo.findOne(newestActive, CatalogProduct.class);
~~~

Ý nghĩa MongoDB shell:

~~~javascript
db.catalog_products.find({ status: "ACTIVE" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(1);
~~~

`createdAt DESC` đưa sản phẩm mới lên trước; `id DESC` là khóa phụ duy nhất trong trường hợp timestamp bằng nhau. Tên `id` được Spring Data đổi thành `_id` khi thực hiện Query typed.

### 6.2. findOne khác gì findById?

| Tình huống | Chọn API |
|---|---|
Đã biết ID và không có điều kiện bổ sung | `findById` |
Tìm một bản ghi đang ACTIVE, còn hàng | `findOne` với `Query` |
Tìm một ID **thuộc tenant hiện tại** | `findOne` kết hợp `id` và `tenantId` |
Tìm bản ghi gần nhất hoặc giá thấp nhất | `findOne` với `Sort` |
Muốn nhiều bản ghi hoặc trang kết quả | `find` với filter/sort/limit |

Thao tác `findOne` không tự chứng minh điều kiện là unique. Nếu nghiệp vụ yêu cầu mỗi email/SKU chỉ có tối đa một document, cần unique index đúng scope. **Truy vấn chỉ trả một kết quả không phải ràng buộc duy nhất của dữ liệu.**

## 7. find: tìm nhiều kết quả và kiểm soát kích thước

`find(query, Type.class)` nhận cùng kiểu `Query` như `findOne` nhưng trả danh sách:

~~~java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
                .and("stock").gte(5));
query.with(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")));
query.limit(20);

List<CatalogProduct> products =
        mongo.find(query, CatalogProduct.class);
~~~

Nếu không có document phù hợp, `find` thông thường trả **danh sách rỗng**, không phải `null` như trường hợp không tìm thấy của `findOne`/`findById`. Luôn phân biệt:

- `findById`/`findOne`: kết quả đơn và có thể `null`.
- `find`: danh sách; dùng `isEmpty()` hoặc `size()`.
- `count` và `exists` là API khác: không nên tải cả danh sách để chỉ đếm hoặc kiểm tra tồn tại.

### 7.1. Phân trang offset bằng Query

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

Pageable page = PageRequest.of(
        1, 10,
        Sort.by(Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")));

Query paged = Query.query(Criteria.where("status").is("ACTIVE"));
paged.with(page);

List<CatalogProduct> secondPage =
        mongo.find(paged, CatalogProduct.class);
~~~

`PageRequest` dùng số trang bắt đầu từ **0**; ví dụ lấy trang thứ hai với kích thước 10. `query.with(page)` đặt skip/limit/sort, nhưng vì kiểu trả về là `List` nên không tự tạo metadata total count hay `hasNext()`.

Muốn trả `Slice` không đếm tổng, có thể lấy `size + 1` phần tử rồi cắt một phần tử dư; với `Page` cần tổng số theo semantics tương ứng. Ở trang sâu, `skip` vẫn có thể rất tốn chi phí ngay cả khi đã có index.

### 7.2. Không sử dụng find không giới hạn cho dữ liệu lớn

~~~java
// Không nên dùng cho API có collection lớn nếu thiếu giới hạn:
List<CatalogProduct> everything =
        mongo.find(new Query(), CatalogProduct.class);
~~~

`find(new Query(), ...)` không có filter, có thể đưa một lượng lớn document vào bộ nhớ cùng lúc. Với export hoặc batch processing, cân nhắc streaming/cursor có đóng tài nguyên, trang có giới hạn hoặc reactive access theo nhu cầu. Một pipeline reactive cũng cần filter, limit và backpressure phù hợp; chỉ đổi kiểu API không tự làm truy vấn vô hạn trở nên an toàn.

### 7.3. Lọc trên field lồng nhau

Nếu mô hình có property `supplier.countryCode` và `@Field("country_code")` trên nested value object, có thể viết:

~~~java
Query byCountry = Query.query(
        Criteria.where("supplier.countryCode").is("VN"));
List<SomeProductWithSupplier> items =
        mongo.find(byCountry, SomeProductWithSupplier.class);
~~~

Đây là **minh họa**: `SomeProductWithSupplier` phải là một entity được khai báo riêng với property `supplier`. Không copy đoạn này vào ví dụ `CatalogProduct` nếu chưa thêm mô hình supplier. Với entity type phù hợp, Spring Data có thể ánh xạ đường dẫn property sang `supplier.country_code`. Với raw BSON, phải viết tên vật lý trực tiếp.

## 8. Kiểm tra Query mapping: property Java khác tên BSON

Cùng một điều kiện được diễn tả theo hai cách:

**Qua MongoTemplate với entity type:**

~~~java
Query query = Query.query(
        Criteria.where("name").is("Bình nước giữ nhiệt")
                .and("stock").gt(0));

List<CatalogProduct> result =
        mongo.find(query, CatalogProduct.class);
~~~

**Qua MongoDB shell với field BSON:**

~~~javascript
db.catalog_products.find({
  display_name: "Bình nước giữ nhiệt",
  stock_qty: { $gt: 0 }
});
~~~

Mapping áp dụng dựa trên entity type `CatalogProduct.class`. Khi sử dụng `mongo.getCollection("catalog_products")` để truy cập driver, hoặc khi đưa raw `Document` không qua Spring Data query mapping, phải viết đúng field BSON.

### 8.1. Field projection và hậu quả của entity thiếu dữ liệu

Nếu chỉ cần tên và trạng thái để hiển thị:

~~~java
Query lightweight = Query.query(
        Criteria.where("status").is("ACTIVE"));
lightweight.fields()
        .include("id")
        .include("name")
        .include("status");
lightweight.limit(20);

List<CatalogProduct> partial =
        mongo.find(lightweight, CatalogProduct.class);
~~~

Lệnh MongoDB có thể chỉ trả các field được chọn, với `id` được map sang `_id` và `name` sang `display_name`. Nhưng vì vẫn materialize `CatalogProduct`, những field không được tải như `stock` (kiểu `int`) có thể mang giá trị mặc định Java (0) trong object trả về.

**Không gọi `save` trên một entity được tải thiếu field như thể đó là trạng thái đầy đủ.** Điều này có thể ghi mất dữ liệu chưa được tải. Với API chỉ đọc, hãy ưu tiên DTO/record projection thích hợp hoặc mapping sang DTO và xác minh field BSON đã được chọn đúng.

### 8.2. Query immutable hay mutable?

`Query` là object dùng để tích lũy `Criteria`, sort, skip, limit và field projection. Code ví dụ thường chỉnh trên chính instance đó:

~~~java
Query search = Query.query(Criteria.where("status").is("ACTIVE"));
search.with(Sort.by(Sort.Order.asc("name")));
search.limit(10);
~~~

Tránh tái sử dụng một `Query` có thể thay đổi giữa các request hoặc thread; tạo Query mới theo mỗi nhu cầu hoặc xây builder riêng. Nếu dùng filter động, không ghép raw JSON từ input người dùng; dùng `Criteria` và validation giúp kiểm soát loại toán tử và tên field.

## 9. Service mẫu dùng đúng năm thao tác

Ví dụ sau đặt cả năm phương thức vào một service đơn giản. API public tạo ID đầu vào chỉ là ví dụ; trong ứng dụng thật, cần kiểm tra tenant, quyền truy cập, dữ liệu đầu vào và cơ chế cấp ID.

**CatalogService.java**

~~~java
package com.example.catalog;

import java.time.Instant;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final MongoTemplate mongo;

    public CatalogService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public CatalogProduct create(
            String id, String name, int stock, String tenantId) {
        if (id == null || id.isBlank()
                || name == null || name.isBlank() || stock < 0
                || tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Dữ liệu tạo sản phẩm không hợp lệ");
        }
        return mongo.insert(new CatalogProduct(
                id, name, stock, "ACTIVE", tenantId, Instant.now()));
    }

    public CatalogProduct saveFullState(CatalogProduct product) {
        // Chỉ gọi với aggregate hợp lệ và đã kiểm soát tranh chấp ghi.
        return mongo.save(product);
    }

    public CatalogProduct getById(String id) {
        return mongo.findById(id, CatalogProduct.class);
    }

    public CatalogProduct newestActive(String tenantId) {
        Query query = Query.query(
                Criteria.where("tenantId").is(tenantId)
                        .and("status").is("ACTIVE"));
        query.with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")));
        return mongo.findOne(query, CatalogProduct.class);
    }

    public List<CatalogProduct> availableProducts(
            String tenantId, int minimumStock, int limit) {
        if (minimumStock < 0 || limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Điều kiện tìm kiếm không hợp lệ");
        }

        Query query = Query.query(
                Criteria.where("tenantId").is(tenantId)
                        .and("status").is("ACTIVE")
                        .and("stock").gte(minimumStock));
        query.with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")));
        query.limit(limit);
        return mongo.find(query, CatalogProduct.class);
    }
}
~~~

Trong service:

1. `create` dùng **`insert`** để từ chối tạo trùng khóa.
2. `saveFullState` minh họa **`save`**, nhưng chưa phải API cập nhật đủ an toàn cho môi trường multi-tenant/concurrency nếu nhận nguyên entity từ client.
3. `getById` dùng **`findById`**, tiện cho logic nội bộ đã kiểm soát quyền. Không đưa nó làm API đọc đa tenant trực tiếp khi chưa thêm chính sách truy cập.
4. `newestActive` dùng **`findOne`** có filter tenant và sort xác định.
5. `availableProducts` dùng **`find`** để trả danh sách có filter, sort và limit.

Ví dụ này cố ý phân biệt phương thức CRUD khỏi nghiệp vụ hoàn chỉnh. Với endpoint production, nên tách DTO request/response, kiểm tra quyền và tránh phương thức `saveFullState` cho phép client ghi đè trường nội bộ.

## 10. Ghi đồng thời: @Version, duplicate key và cập nhật điều kiện

Một vấn đề thường bị bỏ qua khi học `save` là **lost update**:

~~~text
Ban đầu: p-101 có stock = 12.
Request A đọc stock = 12.
Request B đọc stock = 12.
B sửa stock = 11 và save.
A sửa name trên entity cũ rồi save.
Kết quả có thể quay stock về 12 do A lưu toàn bộ trạng thái cũ.
~~~

Spring Data MongoDB có cơ chế optimistic locking bằng `@Version` cho entity được mapping qua các đường ghi phù hợp. Dùng model riêng để tránh làm phức tạp ví dụ `CatalogProduct` ban đầu:

**VersionedProduct.java**

~~~java
package com.example.catalog;

import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "versioned_products")
public class VersionedProduct {
    @MongoId(FieldType.STRING)
    private String id;

    private String name;

    @Version
    private Long version;

    protected VersionedProduct() {}

    public VersionedProduct(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public Long getVersion() { return version; }
    public void setName(String name) { this.name = name; }
}
~~~

Kịch bản:

~~~java
mongo.insert(new VersionedProduct("v-101", "Tên ban đầu"));

VersionedProduct a = mongo.findById("v-101", VersionedProduct.class);
VersionedProduct b = mongo.findById("v-101", VersionedProduct.class);

a.setName("Tên do A đặt");
mongo.save(a);

b.setName("Tên do B đặt");
// Trên đường ghi có optimistic locking, save này sẽ bị từ chối
// vì version của b đã cũ.
mongo.save(b);
~~~

Khi write concern đã được xác nhận và các đường ghi liên quan tôn trọng version, thao tác lưu với version cũ có thể gây `OptimisticLockingFailureException` thay vì âm thầm ghi đè. Ứng dụng cần phân loại xung đột, đọc lại trạng thái, đánh giá lại nghiệp vụ rồi mới retry nếu phù hợp.

**Lưu ý:** Nếu đường ghi khác dùng raw driver hoặc update không có điều kiện version, optimistic locking ở repository/`save` chưa chắc bảo vệ toàn hệ thống. Không giả định một annotation giải quyết mọi dạng tranh chấp. Với một field như tồn kho, `Update.inc` kèm điều kiện đủ hàng có thể phù hợp hơn read-modify-save.

### 10.1. Lỗi không chỉ có duplicate key

| Tình huống | Lỗi/kết quả có thể gặp | Phản ứng phù hợp |
|---|---|---|
`insert` với `_id` đã có | `DuplicateKeyException` | Xử lý như xung đột create, không retry mù |
`save` với version cũ | `OptimisticLockingFailureException` | Đọc lại và xử lý xung đột nghiệp vụ |
`findById` không có bản ghi | `null` | Trả not found theo contract, không dereference |
`findOne` không có bản ghi | `null` | Xử lý như không có kết quả |
`find` không có bản ghi | Danh sách rỗng | Trả danh sách rỗng hoặc phản hồi phù hợp |
Query tên property sai | Có thể lỗi mapping hoặc kết quả rỗng | Kiểm tra entity metadata và BSON |
MongoDB mất kết nối/timeout | Data-access exception tùy nguyên nhân | Phân loại transient, retry có giới hạn và đo độ trễ |

Đừng lấy mọi exception để mặc định gọi lại `insert` hoặc `save`. Với timeout sau write, request cũ có thể đã được MongoDB áp dụng; một retry không có idempotency key hoặc điều kiện bảo vệ có thể tạo hiệu ứng ngoài ý muốn.

## 11. Index, round trip và hiệu năng truy vấn

`findById` có lợi thế là MongoDB có unique index mặc định trên `_id`. Tuy nhiên việc gọi `findById` hàng nghìn lần vẫn có chi phí round trip; nếu cần nhiều ID, nên thiết kế truy vấn theo tập có giới hạn, caching hoặc batch phù hợp.

Với `findOne`/`find` ở ví dụ, index ứng viên để lọc theo tenant, trạng thái và sắp xếp theo thời gian:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "idx_tenant_status_created_id" }
);
~~~

Để tìm theo tồn kho hoặc mức giá, index tối ưu có thể khác. Không tự tạo index cho mọi property; chọn theo các query thực tế, tỷ lệ chọn lọc, thứ tự sort và chi phí cập nhật index.

Ví dụ phân tích một truy vấn:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  status: "ACTIVE",
  stock_qty: { $gte: 5 }
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
~~~

Kiểm tra `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, độ trễ và số document thực sự trả. Một query có filter trên `stock_qty` nhưng index chỉ có `tenantId`/`status`/`createdAt` có thể vẫn phải kiểm tra nhiều document; lựa chọn index dựa vào dữ liệu và tần suất workload.

### 11.1. Đọc ít field bằng projection

Nếu trang danh sách chỉ cần tên và trạng thái:

~~~java
Query query = Query.query(Criteria.where("status").is("ACTIVE"));
query.fields().include("id").include("name").include("status");
query.limit(20);
List<CatalogProduct> cards = mongo.find(query, CatalogProduct.class);
~~~

Tùy mapping, lệnh find có thể mang field projection chỉ định `_id`, `display_name`, `status`. **Tải ít field không đồng nghĩa có một entity đầy đủ để save**. Nên sử dụng DTO projection hoặc phương thức đọc riêng cho API.

### 11.2. MongoTemplate hay MongoRepository?

| Nhu cầu | Lựa chọn thường phù hợp |
|---|---|
CRUD đơn giản theo entity và ID | `MongoRepository` |
Truy vấn động với nhiều điều kiện tùy chọn | `MongoTemplate` + `Criteria` |
Chỉ cần một document theo ID | `findById` ở repository hoặc template |
Chỉ tạo mới, từ chối trùng ID | `MongoTemplate.insert` hoặc API insert phù hợp |
Tìm document mới nhất theo điều kiện | `MongoTemplate.findOne` có sort |
Sửa một field nguyên tử có điều kiện | `MongoTemplate.updateFirst` / `findAndModify` |
Aggregation, nhóm và tính toán | `MongoTemplate.aggregate` |

Không cần chuyển toàn bộ dự án từ repository sang template. Hai abstraction dùng chung hạ tầng mapping Spring Data và có thể kết hợp trong các service khi cần.

## 12. Kiểm thử năm thao tác với MongoDB thật

Một unit test mock `MongoTemplate` chỉ kiểm tra code gọi đúng phương thức, **không chứng minh** Spring Data ghi đúng field BSON, xử lý duplicate key hay áp dụng sort. Để xác minh hành vi tích hợp, dùng MongoDB dành riêng cho test, có thể qua Testcontainers. `@DataMongoTest` trong Spring Boot 3.x chỉ chuẩn bị test slice MongoDB; nó không tự khởi chạy MongoDB server.

**CatalogMongoTemplateTest.java**

~~~java
package com.example.catalog;

import static com.mongodb.client.model.Filters.eq;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Instant;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class CatalogMongoTemplateTest {
    @Autowired
    MongoTemplate mongo;

    private CatalogProduct product(
            String id, String name, int stock, String status, int hour) {
        return new CatalogProduct(
                id, name, stock, status, "tenant-a",
                Instant.parse("2026-11-20T00:00:00Z").plusSeconds(3600L * hour));
    }

    @BeforeEach
    void clear() {
        // Chỉ thực hiện trong database test được cô lập.
        mongo.remove(new Query(), CatalogProduct.class);
    }

    @Test
    void insertCreatesAndDuplicateIdIsRejected() {
        mongo.insert(product("p-101", "Bình nước", 12, "ACTIVE", 8));

        assertThatThrownBy(() ->
                mongo.insert(product("p-101", "Trùng ID", 99, "ACTIVE", 9)))
                .isInstanceOf(DuplicateKeyException.class);
    }

    @Test
    void saveChangesExistingDocument() {
        mongo.insert(product("p-101", "Bình nước", 12, "ACTIVE", 8));
        CatalogProduct existing =
                mongo.findById("p-101", CatalogProduct.class);
        assertThat(existing).isNotNull();

        existing.setName("Bình giữ nhiệt");
        mongo.save(existing);

        Document raw = mongo.getCollection("catalog_products")
                .find(eq("_id", "p-101")).first();
        assertThat(raw).isNotNull();
        assertThat(raw.getString("display_name"))
                .isEqualTo("Bình giữ nhiệt");
        assertThat(raw.getInteger("stock_qty")).isEqualTo(12);
        assertThat(raw.containsKey("name")).isFalse();
    }

    @Test
    void findByIdAndFindOneReturnNullWhenMissing() {
        assertThat(mongo.findById(
                "missing", CatalogProduct.class)).isNull();

        Query noMatches = Query.query(
                Criteria.where("status").is("MISSING"));
        assertThat(mongo.findOne(
                noMatches, CatalogProduct.class)).isNull();
    }

    @Test
    void findOneUsesSortAndFindReturnsList() {
        mongo.insert(product("p-101", "Cũ", 2, "ACTIVE", 8));
        mongo.insert(product("p-102", "Mới", 7, "ACTIVE", 9));
        mongo.insert(product("p-103", "Ẩn", 5, "INACTIVE", 10));

        Query active = Query.query(
                Criteria.where("status").is("ACTIVE"));
        active.with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")));

        CatalogProduct newest =
                mongo.findOne(active, CatalogProduct.class);
        assertThat(newest).isNotNull();
        assertThat(newest.getId()).isEqualTo("p-102");

        List<CatalogProduct> found =
                mongo.find(active, CatalogProduct.class);
        assertThat(found).extracting(CatalogProduct::getId)
                .containsExactly("p-102", "p-101");
    }
}
~~~

Các test trên minh họa **hành vi mong đợi**. Database test phải sẵn sàng; nếu chạy song song, phải cô lập collection để `remove(new Query(), ...)` không xóa dữ liệu của test khác.

### 12.1. Test lỗi lost update

Với `VersionedProduct`, integration test có thể:

1. Insert một document versioned.
2. Đọc hai đối tượng `a` và `b` trước khi ghi.
3. Sửa `a` và `save(a)` thành công.
4. Sửa `b` rồi `save(b)`; xác minh nhận `OptimisticLockingFailureException` theo cấu hình và đường ghi.
5. Đọc lại document, kiểm tra phiên bản mới và không có ghi đè.

Điều kiện cần: MongoDB write concern được xác nhận và các lần ghi đều đi qua đường mapping có hỗ trợ optimistic locking. Nếu trộn driver raw hoặc update không tôn trọng version, test phải bổ sung những đường ghi đó.

### 12.2. Quan sát BSON command

Khi cần xác minh `Criteria.where("name")` thực sự thành `display_name`, có thể gắn MongoDB Java Driver `CommandListener` qua cấu hình test `MongoClientSettingsBuilderCustomizer` (Spring Boot 3.x) và quan sát `CommandStartedEvent`.

Một lệnh `find` minh họa:

~~~json
{
  "find": "catalog_products",
  "filter": {
    "status": "ACTIVE",
    "stock_qty": { "$gte": 5 }
  },
  "sort": { "createdAt": -1, "_id": -1 },
  "limit": 20
}
~~~

JSON trên **không phải khẳng định byte-for-byte** về command của mọi phiên bản driver; tên field và semantics là điều quan trọng. Khi capture, không log dữ liệu nhạy cảm trong filter/insert/update vào hệ thống quan sát production nếu chưa có chính sách bảo vệ.

## 13. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra và khắc phục |
|---|---|---|
`insert` lần hai bị lỗi | Đã có `_id` hoặc business key duy nhất | Kiểm tra unique index và xử lý `DuplicateKeyException` như xung đột |
`save` làm mất trường dữ liệu cũ | Lưu entity thiếu field hoặc snapshot đã cũ | Dùng update từng field hoặc quản lý `@Version`; tránh save partial entity |
`findById` luôn trả null | Sai ID, sai kiểu BSON `_id` hoặc sai collection | Đọc raw BSON, đối chiếu `@MongoId`/`@Id` và collection |
`findOne` trả sản phẩm không mong muốn | Có nhiều bản ghi khớp mà thiếu sort | Thêm sort xác định và index phù hợp |
`find` trả rất nhiều dữ liệu | Query thiếu filter/limit | Giới hạn kích thước, phân trang hoặc streaming có kiểm soát |
Filter `name` không khớp trong raw driver | Field BSON là `display_name` | Dùng typed Query hoặc tên BSON vật lý đúng |
`Query` không phân biệt tenant | Thiếu điều kiện bảo mật trong query | Gắn tenant từ auth context vào find/update/delete |
Save sau khi tìm document bị lost update | Hai request cùng sửa snapshot cũ | Dùng optimistic locking hoặc compare-and-set |
Kết quả đúng nhưng query chậm | Thiếu index, sort tốn bộ nhớ hoặc skip sâu | Dùng `explain("executionStats")`, đo keys/docs examined |
Test `@DataMongoTest` không kết nối | Chưa có server MongoDB phục vụ test | Cấp database test hoặc Testcontainers phù hợp |

## 14. Bài tập thực hành

**Bài 1 — Insert hay save?** Tạo document `p-101` bằng `insert`. Gọi `insert` lần nữa với cùng ID và ghi lại lỗi. Sau đó đọc entity hiện có, thay tên và dùng `save`; so sánh BSON trước/sau, giải thích vì sao không dùng save làm API create-only.

**Bài 2 — findById và findOne.** Tạo ba sản phẩm với cùng trạng thái ACTIVE. Dùng `findById` lấy đúng một ID, dùng `findOne` tìm sản phẩm mới nhất theo `createdAt DESC, id DESC`. Bỏ sort và quan sát vì sao không được dựa vào “bản ghi đầu” mặc định.

**Bài 3 — find, Criteria và mapping.** Dùng `@Field("stock_qty")` trên property `stock`. Truy vấn `status=ACTIVE` và `stock>=5` bằng `MongoTemplate`; kiểm tra raw BSON/filter để xác nhận dùng tên BSON `stock_qty`.

**Bài 4 — Projection và partial entity.** Chỉ tải `id`, `name` rồi xem giá trị `stock` trong entity Java. Giải thích rủi ro nếu save entity thiếu field, sau đó thiết kế DTO chỉ đọc hoặc `Update.set` để sửa tên.

**Bài 5 — Lost update.** Cho hai request đọc cùng `p-101`, một request giảm stock, một request sửa name. Mô phỏng thao tác save hai snapshot; thêm `@Version` hoặc câu lệnh cập nhật có điều kiện để bảo vệ thay đổi.

**Bài 6 — Multi-tenant.** Thiết kế API đọc và cập nhật sản phẩm chỉ cho tenant hiện tại. So sánh `findById(id)` với `findOne(query với id + tenantId)`; test request của tenant khác không đọc được thông tin.

**Bài 7 — Index và hiệu năng.** Tạo tập dữ liệu đủ lớn và đo filter `tenantId + status`, sort `createdAt DESC, _id DESC`, limit 20. Dùng `explain("executionStats")`, so sánh hiệu năng trước/sau compound index; kiểm tra chi phí `skip` ở các trang sâu.

**Bài 8 — Khả năng phát lại.** Một client gửi lệnh tạo sản phẩm nhưng timeout sau khi MongoDB đã nhận insert. Thiết kế idempotency key hoặc kiểm tra kết quả theo ID để phân biệt “yêu cầu trước đã thành công” với “ID bị request khác sử dụng”. Không retry mọi duplicate như lỗi transient.

## 15. Ghi nhớ

Trong **Spring Data MongoDB**, `MongoTemplate.insert` là lựa chọn cho **tạo document mới và từ chối trùng khóa**; `save` dùng khi cần lưu trạng thái entity và có thể thêm mới hoặc ghi lại document hiện có theo metadata mapping. Không sử dụng `save` trên entity thiếu field hoặc snapshot đã cũ nếu không có chính sách kiểm soát ghi đè.

`findById` tìm một document theo `_id`, `findOne` chọn một document theo `Query` linh hoạt, còn `find` trả danh sách các document thỏa điều kiện. Với `findOne` hoặc `find`, luôn xác định **filter, sort, limit và quyền truy cập**; đặc biệt không phụ thuộc vào “document đầu tiên” nếu thiếu sort.

Hãy kiểm tra **mapping từ property Java sang BSON**, kiểu `_id`, index, số round trip và các tình huống cạnh tranh ghi. `MongoRepository` giúp đơn giản hóa CRUD phổ biến; `MongoTemplate` cho phép xây dựng Query/Update có chủ đích. Kết quả chính xác đến từ **ngữ nghĩa thao tác và kiểm thử trên MongoDB thật**, không chỉ từ tên phương thức.
