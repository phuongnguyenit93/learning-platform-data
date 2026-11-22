# Phân biệt insert nhiều document, saveAll và bulk operations

## 1. Bài toán: ghi hàng nghìn document không chỉ là một vòng lặp

Trong chương **Ghi hàng loạt** của **Spring Data MongoDB**, yêu cầu phổ biến là đồng bộ danh mục từ ERP, nhập nhiều dòng dữ liệu từ CSV hoặc thay đổi tồn kho của hàng nghìn sản phẩm. Người phát triển có thể thấy một số API có vẻ cùng làm nhiệm vụ này:

- `MongoTemplate.insert(Collection, Entity.class)` hoặc `insertAll(...)` để thêm nhiều document.
- `MongoRepository.saveAll(Iterable)` để lưu một tập entity mới hoặc đã tồn tại.
- `MongoTemplate.bulkOps(...)` để đưa nhiều thao tác `insert`, `updateOne`, `updateMulti`, `remove`, `upsert` vào một kế hoạch bulk write.
- MongoDB Java Driver `MongoCollection.insertMany(...)` và `bulkWrite(...)` khi cần làm việc trực tiếp với BSON/driver.

Các API này **không tương đương** về ngữ nghĩa. Nếu dùng `saveAll` cho dữ liệu được yêu cầu *chỉ tạo mới*, một bản ghi đã tồn tại có thể bị ghi đè tùy cách Spring Data nhận diện entity và đường ghi. Ngược lại, dùng `insert` cho dữ liệu cần cập nhật sẽ gặp duplicate key. Với bulk operations, kết quả có thể **thành công một phần** và callback/optimistic locking không thể được mặc định giống như `save` từng entity.

Mục tiêu là biết lựa chọn đúng API dựa trên **loại thao tác, tính bất biến của khóa, hành vi khi lỗi, thứ tự thực thi, hiệu năng, version và khả năng retry**.

Ví dụ xuyên suốt: hệ thống nhập sản phẩm vào collection `catalog_products`, có khóa nội bộ `_id`, business key (`tenantId`, `sku`), tên sản phẩm, trạng thái và số lượng tồn kho. Sau khi nhập lần đầu, một luồng khác có thể gửi cập nhật tồn kho cho các sản phẩm đã có.

> Bài sử dụng Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x và MongoDB tương thích. Hành vi triển khai `saveAll`, phiên dịch exception, lifecycle callbacks và API bulk có thể thay đổi theo phiên bản. Những chỗ phụ thuộc implementation được giải thích riêng; kiểm thử integration trên phiên bản triển khai là bước cần thiết trước production.

## 2. Bảng so sánh nhanh

| Tiêu chí | Insert nhiều document | Repository `saveAll` | `BulkOperations` |
|---|---|---|---|
| Ý nghĩa chính | **Chỉ tạo mới** | Lưu các entity mới/**đã có** | Kết hợp nhiều lệnh ghi được chỉ rõ |
| Thao tác có thể thực hiện | Insert | Insert hoặc save theo nhận diện entity | Insert, update, upsert, replace, delete theo API |
| Khi trùng `_id` | Lỗi duplicate key | Có thể lưu/update entity hiện hữu hoặc lỗi tùy version/trạng thái entity | Phụ thuộc từng lệnh insert/upsert/update và unique index |
| Có tự động là **một** MongoDB command? | Không được bảo đảm cho mọi batch/kích thước | **Không** | Driver có thể chia thành nhiều batch/command |
| Có tự động là một transaction? | Không | Không | Không |
| Có thể ordered/unordered? | Driver insertMany có lựa chọn; Spring Data insert thông thường không cung cấp cùng bulk plan | Không phải API đặt `BulkMode` | Có `BulkMode.ORDERED` hoặc `UNORDERED` |
| `@Version`/entity lifecycle | Cần kiểm tra đường insert và callback tương ứng | Có cơ chế entity save và optimistic locking phù hợp | **Không giả định** bulk xử lý version/callback như save từng entity |
| Kết quả trả về | Collection các entity hoặc kết quả insert tùy API | Iterable/List entity đã lưu tùy phiên bản | `BulkWriteResult` tổng hợp số thao tác |
| Trường hợp nên dùng | Seed/import tạo mới | Lưu tập entity trong workflow ứng dụng | Nhập hỗn hợp insert/update/upsert/delete, cập nhật hàng loạt hiệu quả |

Điểm cốt lõi: **“gửi nhiều dữ liệu” không tự đồng nghĩa “ghi nguyên tử toàn bộ dữ liệu”**. MongoDB bảo đảm mỗi thao tác ghi trên **một document** có tính nguyên tử ở cấp document, nhưng các document khác nhau trong cùng batch có thể có kết quả khác nhau khi xảy ra lỗi.

### Sơ đồ chọn cách ghi

~~~mermaid
flowchart TD
    A["Cần ghi nhiều document"] --> B{"Chỉ tạo mới, không được ghi đè?"}
    B -->|"Có"| C["MongoTemplate.insert / insertAll"]
    B -->|"Không"| D{"Mỗi entity đã có trạng thái đầy đủ, cần lưu theo entity?"}
    D -->|"Có"| E["Repository.saveAll + kiểm soát @Version"]
    D -->|"Không"| F{"Cần cập nhật/upsert/xóa theo query riêng?"}
    F -->|"Có"| G["MongoTemplate.bulkOps"]
    F -->|"Không"| H["Xem lại hợp đồng nghiệp vụ và kiểu dữ liệu"]
    C --> I["Unique index + batch + retry policy"]
    E --> I
    G --> J["ORDERED/UNORDERED + result + partial failure"]
    J --> I
~~~

## 3. Entity mẫu, định danh và unique business key

Để các ví dụ rõ ràng, dùng Java class mutable, vì `saveAll` với entity đã tồn tại cần thể hiện quá trình đổi trạng thái rồi lưu. Các class trong package `com.example.catalog`; Spring Boot phải quét package này và có kết nối MongoDB hợp lệ.

**CatalogProduct.java**

~~~java
package com.example.catalog;

import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_products")
public class CatalogProduct {
    @MongoId(FieldType.STRING)
    private String id;

    private String tenantId;
    private String sku;

    @Field("display_name")
    private String name;

    @Field("stock_qty")
    private long stock;

    private String status;

    @Version
    private Long version;

    protected CatalogProduct() {}

    public CatalogProduct(
            String id, String tenantId, String sku,
            String name, long stock, String status) {
        this.id = id;
        this.tenantId = tenantId;
        this.sku = sku;
        this.name = name;
        this.stock = stock;
        this.status = status;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public long getStock() { return stock; }
    public String getStatus() { return status; }
    public Long getVersion() { return version; }

    public void setName(String name) { this.name = name; }
    public void setStock(long stock) { this.stock = stock; }
    public void setStatus(String status) { this.status = status; }
}
~~~

Trong MongoDB, document có hình dạng như sau (lược bỏ `_class` nếu có):

~~~json
{
  "_id": "prd-101",
  "tenantId": "tenant-a",
  "sku": "BOTTLE-500",
  "display_name": "Bình nước 500 ml",
  "stock_qty": 20,
  "status": "ACTIVE",
  "version": 0
}
~~~

`@MongoId(FieldType.STRING)` yêu cầu ID dạng BSON String; `id` trong Java được ánh xạ tới `_id`. `@Field("display_name")` và `@Field("stock_qty")` cho thấy các query/update typed phải ánh xạ property sang tên BSON.

**Khóa `_id`** được MongoDB bảo vệ bởi unique index mặc định trong collection. Nhưng nếu cùng tenant không được có hai sản phẩm cùng SKU, cần unique index **ghép**:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true, name: "uq_product_tenant_sku" }
);
~~~

Trước khi áp dụng index trong production, phải kiểm tra duplicate có sẵn, quy tắc chuẩn hóa SKU, cách xử lý null/thiếu field và chính sách tenant. Không coi `existsByTenantIdAndSku` là ràng buộc uniqueness: hai request có thể cùng thấy chưa có rồi cùng ghi.

**Repository tương ứng:**

~~~java
package com.example.catalog;

import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogProductRepository
        extends MongoRepository<CatalogProduct, String> {

    Optional<CatalogProduct> findByTenantIdAndSku(
            String tenantId, String sku);
}
~~~

Vì entity có `@Version Long`, bản ghi đã lưu có version dùng cho optimistic locking trên các đường ghi phù hợp. Sự tồn tại của annotation này là một **ràng buộc thiết kế khi so sánh các API ghi**, không có nghĩa mọi bulk operation sẽ áp dụng kiểm tra version tự động.

## 4. Insert nhiều document bằng MongoTemplate

### 4.1. Một collection, một tập object mới

Khi nghiệp vụ yêu cầu **tạo mới tất cả**, có thể dùng `MongoTemplate.insert(Collection, Entity.class)`:

~~~java
package com.example.catalog;

import java.util.Collection;
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductInsertService {
    private final MongoTemplate mongo;

    public ProductInsertService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public Collection<CatalogProduct> seedProducts() {
        List<CatalogProduct> products = List.of(
                new CatalogProduct(
                        "prd-101", "tenant-a", "BOTTLE-500",
                        "Bình nước 500 ml", 20, "ACTIVE"),
                new CatalogProduct(
                        "prd-102", "tenant-a", "MUG-250",
                        "Cốc sứ 250 ml", 35, "ACTIVE"));

        return mongo.insert(products, CatalogProduct.class);
    }
}
~~~

`mongo.insert(products, CatalogProduct.class)` sử dụng metadata của `CatalogProduct` để xác định collection và mapping. Các document mới được tạo; ID trùng unique index sẽ bị MongoDB từ chối. Với version field, hãy kiểm tra phiên bản/framework khởi tạo version phù hợp trong đường insert.

Điểm cần nhớ:

- Insert **không phải** cách cập nhật giá/tồn kho của sản phẩm đã có.
- Một batch có thể bị driver tách thành nhiều nhóm ghi khi vượt giới hạn server/driver.
- Một batch có nhiều lệnh không đồng nghĩa với việc rollback tất cả nếu một document lỗi.
- Kết quả method là collection các object đã được xử lý, **không phải** báo cáo chi tiết per-document kiểu `BulkWriteResult`.

### 4.2. insertAll: collection do từng entity quyết định

`MongoTemplate.insertAll(Collection<? extends T>)` hữu ích khi cần đưa nhiều object Spring Data vào thao tác insert; đường ghi có thể **nhóm theo collection** được suy ra từ entity mapping.

~~~java
List<CatalogProduct> input = List.of(
        new CatalogProduct(
                "prd-201", "tenant-a", "NOTE-01",
                "Sổ tay", 14, "ACTIVE"),
        new CatalogProduct(
                "prd-202", "tenant-a", "PEN-01",
                "Bút mực", 60, "ACTIVE"));

Collection<CatalogProduct> inserted = mongo.insertAll(input);
~~~

Khi mọi item đều là `CatalogProduct`, kết quả là các document trong `catalog_products`. Nếu tập chứa nhiều loại entity với collection khác nhau, việc nhóm và thứ tự lệnh có thể khác; **không sử dụng `insertAll` như transaction xuyên collection**.

`insertAll` và `insert(collection, Entity.class)` có contract khác nhau về cách chỉ định entity/collection. Khi muốn rõ collection mục tiêu và kiểu của toàn bộ batch, overload `insert(..., CatalogProduct.class)` thường dễ kiểm soát hơn.

### 4.3. MongoDB Driver insertMany

Ở tầng driver, tương đương về ý tưởng là:

~~~javascript
db.catalog_products.insertMany(
  [
    {
      _id: "prd-101",
      tenantId: "tenant-a",
      sku: "BOTTLE-500",
      display_name: "Bình nước 500 ml",
      stock_qty: 20,
      status: "ACTIVE"
    },
    {
      _id: "prd-102",
      tenantId: "tenant-a",
      sku: "MUG-250",
      display_name: "Cốc sứ 250 ml",
      stock_qty: 35,
      status: "ACTIVE"
    }
  ],
  { ordered: true }
);
~~~

Với `MongoCollection<Document>.insertMany(...)` trong Java Driver, có thể cấu hình `InsertManyOptions.ordered(boolean)`. Đó là **API của driver**, không phải tham số `BulkMode` của `MongoTemplate.insert(...)`. Khi làm việc trực tiếp với raw `Document`, phải dùng tên BSON `display_name`, `stock_qty`; không có mapping từ property Java của entity nếu không đi qua converter tương ứng.

## 5. saveAll: lưu entity mới hoặc hiện hữu

`MongoRepository.saveAll(Iterable)` thuộc mô hình repository, và **không có nghĩa “insertMany với tên khác”**. Một entity có thể được nhận diện là mới hoặc đã có tùy metadata như ID, `@Version` và chiến lược `isNew`.

### 5.1. Lưu các entity mới

~~~java
List<CatalogProduct> drafts = List.of(
        new CatalogProduct(
                "prd-301", "tenant-a", "BAG-01",
                "Túi vải", 10, "DRAFT"),
        new CatalogProduct(
                "prd-302", "tenant-a", "BAG-02",
                "Túi du lịch", 5, "DRAFT"));

Iterable<CatalogProduct> saved = repository.saveAll(drafts);
~~~

`repository` là bean kiểu `CatalogProductRepository`. Khi mọi entity được nhận diện là **new**, implementation của Spring Data MongoDB trong các phiên bản thông dụng có thể tối ưu đường ghi bằng cách gom insert thay vì gọi save riêng từng item. **Không được viết test/thiết kế nghiệp vụ dựa vào cam kết rằng `saveAll` luôn phát đúng một lệnh `insertMany`.**

Vì `@Version` được khai báo với kiểu nullable `Long`, một entity có version `null` thường được Spring Data nhận diện là **mới**. Đây là điểm rất quan trọng: việc object có ID được cấp sẵn **không đủ** để suy ra Spring Data sẽ cập nhật document đã tồn tại.

### 5.2. Lưu các entity đã tồn tại

~~~java
CatalogProduct existing = repository.findById("prd-101")
        .orElseThrow();

existing.setName("Bình giữ nhiệt 500 ml");
existing.setStock(18);

repository.saveAll(List.of(existing));
~~~

Trong một đường ghi `save` entity hiện hữu, Spring Data có thể kiểm tra version và từ chối bản ghi stale bằng optimistic locking. Nếu một request khác đã cập nhật `prd-101` sau khi chúng ta đọc, cần xử lý `OptimisticLockingFailureException` theo chính sách nghiệp vụ.

**Không dùng `saveAll` để cập nhật một tập entity không đầy đủ** chỉ có ID và tên. Khi framework thực hiện save trạng thái entity, các field không được tải hoặc đang mang giá trị mặc định có thể bị ghi đè. Nếu mục tiêu là thay đổi một field, dùng `Update.set` và điều kiện bảo vệ thích hợp.

### 5.3. Vì sao saveAll có thể không “batch” như bạn nghĩ?

Trong nhiều phiên bản Spring Data MongoDB, implementation có tối ưu cho trường hợp **tất cả entity đều mới**; khi có entity đã tồn tại hoặc tập hỗn hợp, việc lưu có thể trở thành **nhiều lần save riêng** thay vì một bulk write duy nhất.

Điều đó có thể kéo theo:

- Số round trip phụ thuộc số lượng entity và phiên bản framework.
- `@Version`, callback/auditing và phân loại new/existing ảnh hưởng đường ghi.
- Thời gian xử lý hỗn hợp 1.000 entity có thể khác đáng kể với 1.000 document mới.
- Nếu một item gặp lỗi, những item đã lưu trước đó **không tự được rollback**.

Vì vậy, `saveAll` ưu tiên **semantics lưu entity**, không phải một cam kết tối ưu hiệu năng bulk cho mọi workload.

### 5.4. Không thay thế create-only bằng exists + saveAll

Mẫu sau không bảo đảm uniqueness:

~~~java
if (repository.findById("prd-301").isEmpty()) {
    repository.saveAll(List.of(
            new CatalogProduct(
                    "prd-301", "tenant-a", "BAG-01",
                    "Túi vải", 10, "ACTIVE")));
}
~~~

Hai request có thể cùng nhìn thấy ID chưa tồn tại. Hơn nữa `isNew` của entity và `@Version` còn ảnh hưởng hành vi save. Dùng **insert + unique index** khi nghiệp vụ yêu cầu chỉ tạo mới; dùng idempotency key hoặc phép upsert có điều kiện khi muốn xử lý phát lại một request.

## 6. BulkOperations: lập kế hoạch nhiều thao tác ghi

`MongoTemplate.bulkOps(BulkMode, Entity.class)` trả về một builder `BulkOperations`. Ta thêm từng thao tác vào kế hoạch, rồi gọi `execute()` để gửi tới MongoDB:

~~~java
BulkOperations bulk = mongo.bulkOps(
        BulkOperations.BulkMode.ORDERED,
        CatalogProduct.class);

bulk.insert(new CatalogProduct(
        "prd-401", "tenant-a", "PENCIL-01",
        "Bút chì", 100, "ACTIVE"));

bulk.updateOne(
        Query.query(Criteria.where("id").is("prd-101")
                .and("tenantId").is("tenant-a")),
        new Update().set("name", "Bình giữ nhiệt bản mới"));

BulkWriteResult result = bulk.execute();
~~~

Cần import:

~~~java
import com.mongodb.bulk.BulkWriteResult;
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
~~~

Đây là ví dụ ghép **insert và updateOne** vào cùng một kế hoạch. Khi `execute()` được gọi, Spring Data chuyển các yêu cầu thành write models/driver calls; driver/server có thể chia nhỏ batch tùy giới hạn và điều kiện runtime.

Các thao tác thường có:

| Phương thức BulkOperations | Mục đích |
|---|---|
| `insert(entity)` hoặc `insert(List<?>)` | Thêm document |
| `updateOne(query, update)` | Cập nhật một document khớp filter |
| `updateMulti(query, update)` | Cập nhật nhiều document khớp filter |
| `upsert(query, update)` | Cập nhật khi có, tạo khi không khớp |
| `replaceOne(query, replacement)` | Thay document bằng một object mới theo điều kiện, với lưu ý về ID và schema |
| `remove(query)` | Xóa document khớp filter |
| `execute()` | Thực thi các thao tác đã tích lũy và trả kết quả tổng hợp |

Chọn API theo nhu cầu: bulk có thể xử lý **một danh sách thao tác khác nhau**, không nhất thiết mọi item đều là insert hoặc save cùng một entity.

### 6.1. Một ví dụ bulk update tồn kho có điều kiện

Trong nghiệp vụ bán hàng, muốn trừ tồn kho khi **đủ số lượng**, không được làm `stock` âm. Với mỗi command, đặt điều kiện tồn kho trong query rồi giảm bằng `$inc` ngay trên server:

**StockDeduction.java**

~~~java
package com.example.catalog;

public record StockDeduction(
        String id, String tenantId, long amount,
        long expectedVersion) {
}
~~~

**StockBulkService.java**

~~~java
package com.example.catalog;

import com.mongodb.bulk.BulkWriteResult;
import java.util.List;
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class StockBulkService {
    private final MongoTemplate mongo;

    public StockBulkService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public BulkWriteResult deduct(List<StockDeduction> commands) {
        if (commands == null || commands.isEmpty()) {
            throw new IllegalArgumentException("Batch không được rỗng");
        }

        BulkOperations bulk = mongo.bulkOps(
                BulkOperations.BulkMode.UNORDERED,
                CatalogProduct.class);

        for (StockDeduction command : commands) {
            if (command.id() == null || command.tenantId() == null
                    || command.amount() <= 0
                    || command.expectedVersion() < 0) {
                throw new IllegalArgumentException(
                        "StockDeduction không hợp lệ");
            }

            Query query = Query.query(
                    Criteria.where("id").is(command.id())
                            .and("tenantId").is(command.tenantId())
                            .and("version").is(command.expectedVersion())
                            .and("stock").gte(command.amount()));

            Update update = new Update()
                    .inc("stock", -command.amount())
                    .inc("version", 1);

            bulk.updateOne(query, update);
        }

        return bulk.execute();
    }
}
~~~

Trong code, `Criteria` và `Update` sử dụng property Java `stock`, còn MongoDB lưu thực tế là `stock_qty`. Vì bulk được khai báo cho `CatalogProduct.class`, mapping của Spring Data có thể ánh xạ điều kiện và update tới tên BSON phù hợp.

Điều kiện trên **cùng document** được đánh giá khi ghi:

- `id` và `tenantId` xác định đúng tài nguyên của tenant.
- `version = expectedVersion` làm **compare-and-set** theo revision đã đọc.
- `stock >= amount` ngăn giảm từ một lượng không đủ.
- `Update.inc("stock", -amount)` và `inc("version", 1)` thay đổi tồn kho và version trong cùng thao tác.

**Không để framework tự suy ra optimistic locking trong bulk.** Đoạn này cố ý đặt điều kiện và tăng `version` một cách tường minh; phải kiểm thử trên phiên bản Spring Data đang triển khai, nhất là khi các đường ghi khác cũng dùng `save`. Giữ tất cả đường ghi thống nhất cách dùng version.

`BulkWriteResult.getMatchedCount()` và `getModifiedCount()` là **số lượng cộng dồn**; nếu 10 command chỉ khớp 8, kết quả không chỉ ra ngay **hai command nào** không khớp. Với API cần phản hồi từng item, phải có ID command, đối soát hoặc cơ chế ghi nhận riêng thay vì giả định có per-item result.

### 6.2. Vì sao code ví dụ dùng UNORDERED?

Ở ví dụ này, mỗi command được giả định độc lập trên một sản phẩm. `UNORDERED` cho phép driver/server linh hoạt thứ tự, có thể đem lại hiệu năng tốt hơn và tiếp tục xử lý các thao tác độc lập dù một số lệnh gặp lỗi.

**Ràng buộc nghiệp vụ bổ sung:** danh sách `commands` phải không chứa hai thao tác xung đột trên cùng sản phẩm/version hoặc có phụ thuộc thứ tự. Không được dùng `UNORDERED` để mô tả chuỗi “tạo xong mới cập nhật”, “trừ kho rồi mới xóa” khi thứ tự là bắt buộc.

Nếu hai command cùng mục tiêu nhưng khác trạng thái kỳ vọng, `UNORDERED` có thể thực hiện chúng theo thứ tự khó dự đoán. Ngay cả `ORDERED` cũng không tạo transaction; nó chỉ quy định cách xử lý thứ tự/lỗi của **một bulk plan**.

## 7. ORDERED và UNORDERED: hành vi khi gặp lỗi

### 7.1. Ordered

Với `BulkMode.ORDERED`, các write được yêu cầu xử lý theo thứ tự được khai báo; khi gặp lỗi write, bulk thông thường dừng xử lý các thao tác phía sau theo semantics ordered.

~~~text
Input:  [insert A] [insert B] [insert C] [insert D]
                  ^
               B trùng _id

Ordered:
  A có thể đã được insert;
  B bị từ chối;
  C và D chưa được xử lý theo luồng ordered.
~~~

Điều quan trọng: **A không tự rollback**. Ordered không biến toàn bộ chuỗi thao tác thành “all-or-nothing”.

### 7.2. Unordered

Với `BulkMode.UNORDERED`, các thao tác độc lập có thể được thực thi mà không bảo đảm thứ tự khai báo; nếu một thao tác lỗi, các thao tác khác vẫn có thể được thử thực thi.

~~~text
Input:  [insert A] [insert B] [insert C] [insert D]
                  ^
               B trùng _id

Unordered:
  B có thể thất bại;
  A, C, D có thể thành công;
  Không dựa vào thứ tự hoàn thành.
~~~

Kết quả phụ thuộc server, topology, các lỗi khác và cách batch được chia. Không mặc định rằng mọi thao tác khác *chắc chắn* đã thành công; phải kiểm tra trạng thái thực tế và exception/result.

### 7.3. Bảng tình huống

| Tình huống | ORDERED | UNORDERED |
|---|---|---|
Các bước **phụ thuộc thứ tự** | Phù hợp hơn, vẫn không transaction | Không phù hợp nếu thứ tự ảnh hưởng logic |
Hàng nghìn upsert độc lập | Có thể chậm hơn vì ràng buộc thứ tự | Thường là ứng viên hiệu năng |
Duplicate key ở giữa batch | Thường dừng phần sau lỗi | Thường tiếp tục thử các lệnh khác |
Rollback các write đã hoàn tất | Không có | Không có |
Kết quả chi tiết từng command | Không được bảo đảm từ `BulkWriteResult` tổng hợp | Cũng không |
Đảm bảo đúng với cạnh tranh ghi | Cần filter/index/version thích hợp | Vẫn cần cùng các cơ chế đó |

Trong hệ thống có nhiều consumer, chọn bulk mode chỉ là **một phần** của thiết kế cạnh tranh. Một batch ORDERED vẫn có thể tranh chấp với request của process khác.

## 8. Kết quả BulkWriteResult và lỗi ghi hàng loạt

`BulkOperations.execute()` trả `BulkWriteResult` khi thực thi thành công. Các giá trị cần quan sát:

~~~java
BulkWriteResult result = bulk.execute();

int inserted = result.getInsertedCount();
int matched = result.getMatchedCount();
int modified = result.getModifiedCount();
int deleted = result.getDeletedCount();
int upserts = result.getUpserts().size();
~~~

Ví dụ một batch có 2 insert, 3 updateOne (chỉ 2 document khớp) và 1 delete (không có document khớp) có thể có các con số:

~~~text
insertedCount = 2
matchedCount  = 2
modifiedCount = 2 (nếu cả hai update thực sự đổi dữ liệu)
deletedCount  = 0
upserts       = 0
~~~

Đây là **ví dụ giả định**, không phải kết quả cố định của mọi batch.

Giải thích quan trọng:

- `matchedCount` đếm thao tác cập nhật khớp document, **không** nhất thiết bằng số command được thêm.
- `modifiedCount` có thể nhỏ hơn `matchedCount` nếu giá trị mới giống giá trị cũ.
- `getUpserts()` chứa metadata cho các upsert đã tạo mới, nhưng không phải business acknowledgement cho từng command.
- Khi bulk gặp lỗi, `execute()` có thể **ném exception** thay vì trả bình thường; không thể luôn đợi một `BulkWriteResult` đầy đủ từ đường success.

Trong Spring Data, lớp exception cụ thể và thông tin lỗi phụ thuộc vào translation/version; có thể thấy các lỗi liên quan `BulkOperationException`, `BulkWriteException` hoặc data access exception được chuyển đổi. Đừng viết `catch(Exception e) { retryAll(); }` rồi coi mọi lệnh chưa thực hiện.

### Kịch bản thành công một phần

~~~mermaid
flowchart TD
    A["Bulk request có 4 thao tác"] --> B["Một thao tác insert thành công"]
    B --> C["Một thao tác lỗi unique index"]
    C --> D{"Bulk mode?"}
    D -->|"ORDERED"| E["Phần sau có thể dừng"]
    D -->|"UNORDERED"| F["Các thao tác khác vẫn có thể được thử"]
    E --> G["Cần đối soát trạng thái thực tế"]
    F --> G
    G --> H["Retry an toàn theo ID/event/version"]
~~~

Nếu một batch gồm các thao tác **tăng số lượng**, việc retry toàn bộ batch sau lỗi có thể tăng **hai lần** cho các item đã thành công. Với thao tác **gán giá trị cố định**, retry có thể an toàn hơn về trạng thái cuối nhưng vẫn phải xét audit, timestamp và side effects. Mọi chiến lược retry phải dựa trên idempotency nghiệp vụ chứ không chỉ thuộc tính bulk ordered/unordered.

## 9. Bulk upsert: đồng bộ bản ghi theo khóa nghiệp vụ

Nếu dữ liệu nhập từ nguồn ngoài có khóa tự nhiên `(tenantId, sku)`, nhiều hệ thống muốn “có thì cập nhật, chưa có thì thêm”. `BulkOperations.upsert(...)` là một ứng viên:

~~~java
BulkOperations bulk = mongo.bulkOps(
        BulkOperations.BulkMode.UNORDERED, CatalogProduct.class);

for (IncomingProduct incoming : sourceProducts) {
    Query query = Query.query(
            Criteria.where("tenantId").is(incoming.tenantId())
                    .and("sku").is(incoming.sku()));

    Update update = new Update()
            .set("name", incoming.name())
            .set("status", "ACTIVE")
            .setOnInsert("createdAt", importStartedAt);

    bulk.upsert(query, update);
}

BulkWriteResult result = bulk.execute();
~~~

Trong đó `IncomingProduct` là DTO đầu vào đã được validate, `sourceProducts` là collection DTO và `importStartedAt` là timestamp chung của đợt nhập. **Đây là đoạn minh họa đặt trong service**, không phải class hoàn chỉnh. Nếu entity `CatalogProduct` không có property `createdAt` như model mục 3, cần mở rộng model hoặc bỏ `setOnInsert("createdAt", ...)` trước khi sử dụng; không nên thêm field ngoài schema một cách vô thức.

### 9.1. Các lưu ý khi thiết kế upsert

1. Có unique index `{ tenantId: 1, sku: 1 }` để ngăn hai import đồng thời tạo duplicate business key.
2. Quyết định ID: model mục 3 dùng `@MongoId(FieldType.STRING)`, nhưng một upsert chỉ lọc business key nếu không chỉ rõ `_id` có thể khiến MongoDB tự sinh ObjectId. Cần thiết kế nhất quán schema ID và query/filter/upsert hoặc dùng khóa `_id` ổn định do ứng dụng cấp.
3. Không để dữ liệu đầu vào tự ý sửa những field **không được nguồn ngoài sở hữu** (ví dụ stock nội bộ, quyền người dùng).
4. Chọn rõ chính sách `null`: `set("name", null)` có thể ghi null, không nhất thiết nghĩa là “giữ nguyên”.
5. Các sự kiện nhập không theo thứ tự cần revision/timestamp đáng tin, điều kiện cập nhật hoặc chiến lược đối soát; upsert đơn giản có thể để sự kiện cũ ghi đè mới.
6. `upsert` không có nghĩa tự động có optimistic locking theo entity `@Version` hoặc cascade-save liên quan.

Trong bài lab, có thể đơn giản hóa bằng cách lưu ID dựa trên namespace của nguồn và kiểm tra raw BSON. Với hệ thống thực, ID nên ổn định qua nhiều lần nhập và không được phụ thuộc vào tên/thuộc tính có thể đổi.

### 9.2. Khác biệt upsert và saveAll

`saveAll` xử lý **entity** và cơ chế nhận biết new/existing; `BulkOperations.upsert` dùng một **query chỉ rõ document đích** và `Update` chỉ định những trường cần sửa khi khớp, cộng với những trường chỉ set khi tạo mới. Upsert là công cụ mạnh khi import một phần field, nhưng cần quản lý index và cạnh tranh chặt chẽ.

## 10. @Version, auditing, callback và các đường ghi đặc biệt

Một hiểu nhầm phổ biến: “Đã annotate `@Version`/`@LastModifiedDate` trên entity thì bulk operations tự có mọi hành vi giống repository save.”

**Không nên giả định như vậy.** Spring Data MongoDB mô tả bulk operations là nhóm API tập trung vào write models; chúng **không cung cấp đầy đủ lifecycle events/callbacks và optimistic locking semantics giống lưu từng entity**. Với batch có thao tác update, version cần được thiết kế tường minh và kiểm thử:

- Dùng điều kiện `version = expectedVersion` khi nghiệp vụ cần compare-and-set.
- Tăng version theo một quy tắc duy nhất; tránh vừa tự `inc("version", 1)` vừa để một cơ chế khác vô tình tăng lần nữa.
- Kiểm tra `matchedCount`, vì một lệnh không khớp version có thể không ném `OptimisticLockingFailureException` mà chỉ không update.
- Nếu cần audit timestamp, cân nhắc đưa nó vào `Update.set("updatedAt", now)` có kiểm soát; đừng dựa vào callback tự chạy khi dùng bulk.
- Nếu nghiệp vụ cần entity callbacks, validation phức tạp hoặc sự kiện domain theo từng entity, có thể cần `saveAll`/`save` hoặc một pipeline riêng.

**Cẩn trọng cả chiều ngược lại:** có thể có callback liên quan một số đường insert trong framework, nhưng không nên suy luận mọi API batch kích hoạt cùng chuỗi callback như `save`. Hãy viết test cho auditing, version khởi tạo và event theo đúng đường ghi được sử dụng.

### Tránh cập nhật từ entity được tải thiếu field

Nếu muốn cập nhật 100.000 giá sản phẩm, không nhất thiết tải 100.000 entity đầy đủ rồi `saveAll`. Dùng `bulkOps.updateOne` với `Update.set("price", ...)` và filter phù hợp thường giảm lượng dữ liệu được truyền và hạn chế mất field khác. Ngược lại, nếu cần thực thi invariant của aggregate qua domain model và optimistic locking theo từng entity, lợi ích đó có thể đáng giá hơn việc tối đa hóa throughput.

## 11. Transaction, atomicity và write concern

### 11.1. Bulk không tự tạo transaction

Một lệnh bulk có nhiều write model **không tự được wrap trong transaction**. Ngay cả `BulkMode.ORDERED`, nếu thao tác thứ ba thất bại thì hai thao tác đầu có thể vẫn nằm trong database.

Nếu nghiệp vụ yêu cầu nhiều document cùng thành công hoặc cùng rollback, cần MongoDB transaction được cấu hình đúng (session, `MongoTransactionManager` hoặc API driver/session tương ứng, topology hỗ trợ). Transaction làm tăng chi phí và không loại bỏ nhu cầu phân loại lỗi/retry; chỉ dùng khi bất biến xuyên document thực sự đòi hỏi.

Một transaction nhiều document **có thể chứa** các thao tác bulk trên cùng session khi được framework hỗ trợ và cấu hình đúng; không coi chỉ cần viết `@Transactional` là đủ nếu hệ thống chưa có transaction manager hoặc topology tương thích.

### 11.2. Write concern và retryable writes

Các thao tác được MongoDB acknowledgement có thể bị timeout ở phía client sau khi server đã ghi. Khi đó ứng dụng có thể **không biết chắc** write đã thành công hay chưa.

- Write concern quyết định mức xác nhận và ảnh hưởng đến durability/latency.
- Retryable writes của driver có phạm vi và điều kiện hỗ trợ riêng; không thay thế **idempotency nghiệp vụ**.
- Khi bulk chứa `$inc`, `$push` hoặc side effect phụ thuộc trạng thái, tự retry cả batch có thể áp dụng hai lần.
- Dùng request/event ID duy nhất, khóa business ổn định, version/compare-and-set, checkpoint hoặc reconcile để quyết định thao tác nào có thể chạy lại.

### 11.3. Thứ tự và transaction là hai khái niệm khác nhau

| Khái niệm | Câu hỏi nó giải quyết | Không đảm bảo |
|---|---|---|
`ORDERED` | Thứ tự xử lý thao tác trong bulk plan | Rollback các thao tác trước |
`UNORDERED` | Cho phép lệnh độc lập được xử lý linh hoạt | Đúng thứ tự hoặc mọi lệnh đều thành công |
Unique index | Không tạo hai document có cùng khóa unique | Toàn bộ batch nguyên tử |
Optimistic locking | Không ghi dựa trên version cũ khi đường ghi tuân thủ | Tự động trên mọi bulk update |
Transaction | Phạm vi commit/rollback của một giao dịch phù hợp | Tự động có chỉ vì dùng bulk |
Idempotency key | Một ý định nghiệp vụ có thể được xử lý lại an toàn | Tự động có chỉ vì driver hỗ trợ retry |

## 12. Chia batch: giới hạn, bộ nhớ và khả năng phục hồi

Một import có thể chứa hàng triệu dòng. Đừng tạo `List` gồm hàng triệu entity rồi gọi `saveAll` hoặc build một `BulkOperations` khổng lồ mà không có giới hạn bộ nhớ.

### 12.1. Chia thành từng phần nhỏ

Ví dụ một phương thức xử lý input đã có sẵn theo từng batch:

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;

public final class ProductBatchWriter {
    private final MongoTemplate mongo;

    public ProductBatchWriter(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public void insertChunk(List<CatalogProduct> chunk) {
        if (chunk == null || chunk.isEmpty()) {
            return;
        }
        if (chunk.size() > 500) {
            throw new IllegalArgumentException(
                    "Quy ước batch tối đa 500 phần tử");
        }

        mongo.insert(chunk, CatalogProduct.class);
    }
}
~~~

Con số **500 là ví dụ về giới hạn của ứng dụng**, không phải con số tối đa MongoDB bắt buộc cho mọi batch. Driver/server có giới hạn về số thao tác và kích thước message, và một BSON document không thể vượt **16 MiB**. Ngay cả khi vượt một giới hạn gửi lệnh, driver có thể chia requests; kết quả không biến thành một transaction.

Ở hệ thống import thực, reader nên stream/chia dữ liệu từ nguồn thành từng chunk, không tải toàn bộ tệp vào RAM. Kích thước chunk nên được đo theo kích thước document, độ trễ mạng, quota database và chi phí xử lý lỗi.

### 12.2. Checkpoint và đối soát

Một pipeline import có thể gồm:

~~~mermaid
flowchart LR
    R["Đọc nguồn"] --> V["Validate & normalize"]
    V --> P["Chia batch có giới hạn"]
    P --> W["Insert / SaveAll / BulkOps"]
    W --> C{"Kết quả"}
    C -->|"PASS"| K["Ghi checkpoint"]
    C -->|"Partial/unknown"| E["Đối soát theo ID/revision"]
    E --> T["Retry các item an toàn"]
    T --> K
~~~

Checkpoint chỉ nên được đánh dấu khi có đủ thông tin khẳng định kết quả của tập tương ứng, hoặc khi có khả năng kiểm chứng lại các mục chưa rõ. Không chỉ ghi offset nguồn rồi giả định mọi item trong batch đã thành công; khi server trả lỗi hoặc timeout, có thể cần query lại theo ID/event.

Đối với import từ hệ thống ngoài:

1. Dùng `sourceSystem` và `externalId` ổn định, có thể thêm tenant namespace.
2. Chuẩn hóa/validate ID và business key trước khi ghi.
3. Phân biệt sự kiện **tạo mới** với sự kiện **cập nhật**.
4. Nếu có revision nguồn, kiểm tra out-of-order và chỉ áp dụng sự kiện mới hơn.
5. Với dữ liệu nhạy cảm, lọc log và bảo vệ trace chứa nội dung import.
6. Đo tỷ lệ duplicate, lỗi transient, lỗi validation và tốc độ xử lý thực tế.

## 13. Hiệu năng: không chỉ đếm số lần gọi API

Muốn biết API nào phù hợp nhất, cần đo **đường ghi thực tế**:

| Thành phần | Điều nên quan sát |
|---|---|
Số round trip | Repository có gọi save từng entity hay dùng insert theo lô? |
Kích thước payload | Dùng full document hay partial update? |
Index | Mỗi insert/update phải duy trì bao nhiêu index? Có unique index nào tạo hotspot? |
Tài nguyên server | CPU, I/O, lock contention, cache và write amplification |
Độ trễ | p50/p95/p99 theo kích thước batch |
Hậu quả khi lỗi | Số document thành công một phần; chi phí retry/reconcile |
Version/callback | Có callback hoặc kiểm tra stale write theo từng entity không? |
Thứ tự | Có phụ thuộc giữa các thao tác hoặc có xung đột cùng ID trong một batch không? |

Với dữ liệu mới hoàn toàn, `MongoTemplate.insert` hoặc đường insert tối ưu của `saveAll` có thể nhanh hơn gọi `save` riêng từng item. Với cập nhật một vài field của document đã có, `BulkOperations.updateOne` có thể tiết kiệm đáng kể payload và round trip. Nhưng điều này **không phải định luật**: với document nhỏ, số ít item hoặc logic cần callback/optimistic locking, hiệu năng tổng thể có thể khác.

### Index cũng tác động hiệu năng ghi

Index unique trên (`tenantId`, `sku`) bảo vệ bất biến nhưng làm tăng chi phí mỗi lần insert. Các index phụ như `status`, `stock_qty` cũng cần được cập nhật khi field tương ứng thay đổi. Đừng tạo index chỉ để tăng tốc đọc mà không đo tác động lên pipeline bulk write.

Nếu batch làm nhiều update lên **một document nóng**, hiệu năng có thể bị giới hạn bởi cạnh tranh trên document đó. Chia batch không tự giải quyết contention; cần phân vùng dữ liệu hoặc thiết kế lại hướng ghi phù hợp.

## 14. Kiểm thử với MongoDB thật

Mock repository/MongoTemplate chỉ chứng minh ứng dụng gọi API, **không** xác minh duplicate key, kiểu BSON, partial success hoặc event/version behavior. Nên viết integration test trên MongoDB dành riêng cho test, ví dụ Testcontainers. Trong Spring Boot 3.x, `@DataMongoTest` tạo ngữ cảnh test MongoDB nhưng **không tự khởi động MongoDB server**.

### 14.1. Test insert nhiều document và saveAll

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.dao.DataAccessException;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;

@DataMongoTest
class ProductBatchWriteTest {
    @Autowired MongoTemplate mongo;
    @Autowired CatalogProductRepository repository;

    private CatalogProduct product(
            String id, String sku, long stock) {
        return new CatalogProduct(
                id, "tenant-a", sku, sku, stock, "ACTIVE");
    }

    @BeforeEach
    void prepare() {
        // Chỉ chạy trên database test cô lập.
        mongo.dropCollection(CatalogProduct.class);
        mongo.indexOps(CatalogProduct.class).ensureIndex(
                new Index()
                        .on("tenantId", Sort.Direction.ASC)
                        .on("sku", Sort.Direction.ASC)
                        .unique());
    }

    @Test
    void batchInsertIsCreateOnly() {
        mongo.insert(List.of(
                product("p-1", "SKU-1", 5),
                product("p-2", "SKU-2", 7)), CatalogProduct.class);

        assertThat(repository.count()).isEqualTo(2);

        // Trùng ID; insert không được thay thế tài liệu đã có.
        assertThatThrownBy(() -> mongo.insert(
                List.of(product("p-1", "SKU-3", 99)),
                CatalogProduct.class))
                .isInstanceOf(DataAccessException.class);

        assertThat(repository.findById("p-1").orElseThrow().getStock())
                .isEqualTo(5);
    }

    @Test
    void saveAllUpdatesAnExistingVersionedEntity() {
        mongo.insert(product("p-1", "SKU-1", 5));

        CatalogProduct current =
                repository.findById("p-1").orElseThrow();
        current.setStock(9);
        repository.saveAll(List.of(current));

        CatalogProduct after =
                repository.findById("p-1").orElseThrow();
        assertThat(after.getStock()).isEqualTo(9);
        assertThat(after.getVersion()).isNotNull();
    }
}
~~~

Test sử dụng `@Version` và entity đã được đọc từ database để `saveAll` lưu **bản ghi hiện hữu**, tránh dựng một object có ID đã tồn tại nhưng version null rồi nhầm rằng framework sẽ tự coi là update.

**Không dùng `dropCollection` hoặc `deleteAll` trên database chia sẻ**. Với test chạy đồng thời, dùng database hoặc collection riêng cho từng nhóm test; các đoạn chuẩn bị này chỉ an toàn khi đã cô lập môi trường.

### 14.2. Test bulk update với điều kiện version/tồn kho

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.bulk.BulkWriteResult;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
@Import(StockBulkService.class)
class StockBulkServiceTest {
    @Autowired MongoTemplate mongo;
    @Autowired StockBulkService stockBulk;

    @Test
    void deductsOnlyWhenVersionAndStockMatch() {
        mongo.insert(new CatalogProduct(
                "stock-1", "tenant-a", "STOCK-1",
                "Bình nước", 5, "ACTIVE"));

        CatalogProduct before =
                mongo.findById("stock-1", CatalogProduct.class);
        assertThat(before).isNotNull();
        assertThat(before.getVersion()).isNotNull();

        BulkWriteResult result = stockBulk.deduct(List.of(
                new StockDeduction(
                        "stock-1", "tenant-a", 3, before.getVersion()),
                new StockDeduction(
                        "stock-1", "tenant-a", 4, before.getVersion())));

        // Hai command có cùng version kỳ vọng; chỉ một command khớp.
        assertThat(result.getMatchedCount()).isEqualTo(1);

        CatalogProduct after =
                mongo.findById("stock-1", CatalogProduct.class);
        assertThat(after).isNotNull();
        assertThat(after.getStock()).isBetween(1L, 2L);
        assertThat(after.getVersion())
                .isEqualTo(before.getVersion() + 1);
    }
}
~~~

**Giải thích test:** Vì bulk là `UNORDERED`, một trong hai command có thể thắng, do đó tồn kho cuối có thể là **2** nếu trừ 3 hoặc **1** nếu trừ 4. Bản ghi không thể bị trừ cả hai lần dựa trên cùng một version, nếu bộ lọc và cập nhật version được áp dụng đúng. Test cố ý kiểm tra **tính bất biến**, không áp đặt thứ tự thực thi.

Trong dự án thật, cần kết hợp test này với test hai request chạy đồng thời từ nhiều process, vì một bulk UNORDERED trong một thread chỉ là một phần của bài toán cạnh tranh.

### 14.3. Các ca lỗi cần bổ sung

| Kịch bản | Kiểm tra |
|---|---|
Insert 3 document, phần tử thứ 2 trùng ID | Phần nào đã ghi, phần nào không, theo ordered/unordered |
Insert trùng business key nhưng ID khác | Unique compound index bảo vệ chính xác |
saveAll gồm entity mới và entity cũ | Đếm command, kiểm tra version và hiệu năng |
Bulk update với version kỳ vọng sai | `matchedCount` không tăng, dữ liệu không đổi |
Bulk update với tồn kho không đủ | Không làm stock âm |
Bulk upsert cùng business key từ hai worker | Không duplicate; lỗi race được xử lý |
Bulk lỗi/timeout sau ghi một phần | Có cơ chế đối soát, retry theo item an toàn |
Custom callback hoặc auditing | Xác minh API nào thật sự gọi callback |
Nhiều document trên nhiều collection | Không nhầm group insert với transaction |
Document lớn và batch lớn | Chia chunk, kiểm tra bộ nhớ và độ trễ |

### 14.4. Quan sát command thực tế

MongoDB Java Driver có `CommandListener` để ghi nhận `CommandStartedEvent` trong môi trường test. Đối chiếu lệnh:

- `insert` cho danh sách document mới;
- `update` với các update models, `multi`, `upsert`;
- `delete` với điều kiện tương ứng.

Không suy số round trip chỉ từ việc code Java gọi một method: driver có thể chia batch và framework có thể thực hiện các lời gọi khác nhau theo `isNew`. Khi bật command capture, lọc theo collection và che thông tin nhạy cảm; không log raw business payload trong production thiếu kiểm soát.

## 15. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
Cho rằng `saveAll` luôn bằng insertMany | Có thể update hoặc save từng entity | Kiểm tra `isNew`, version và command thực tế |
Cho rằng `saveAll` luôn chỉ một round trip | Tải lớn có thể chậm ngoài dự kiến | Đo driver commands, chia batch, chọn bulk nếu phù hợp |
Gọi `insert` cho bản ghi cần cập nhật | Duplicate key khi import lặp | Phân biệt create-only và update/upsert |
Dùng `saveAll` với entity chỉ có ID + một field | Có thể mất dữ liệu chưa được tải | Update từng field, không save partial entity |
Tin `ORDERED` nghĩa là transaction | Dữ liệu đã ghi trước lỗi không rollback | Thiết kế transaction nếu cần all-or-nothing |
Tin `UNORDERED` luôn chạy đúng thứ tự source | Cập nhật phụ thuộc nhau có kết quả sai | Chỉ dùng cho thao tác độc lập |
Giả định bulk tự xử lý optimistic locking theo `@Version` | Stale updates có thể không bị chặn | Đưa version vào filter và increment rõ ràng |
Đọc `BulkWriteResult` như kết quả chi tiết từng dòng | Không biết command nào không match | Gắn ID, đối soát và trả kết quả theo item |
Retry toàn bộ `$inc` batch sau timeout | Có thể cộng/trừ hai lần | Idempotency key, event revision, reconcile |
Không có unique business key | Hai upsert đồng thời có thể tạo duplicate | Tạo unique index đúng namespace |
Upsert không chỉ định kiểu `_id` nhất quán | BSON ObjectId/String khác nhau, mapping lỗi | Thiết kế ID/Query/`setOnInsert` phù hợp |
Không giới hạn batch và RAM | OOM, payload lớn, khó retry | Chia chunk và checkpoint |
Không phân biệt zero matched với lỗi write | Thông báo thành công sai nghiệp vụ | Đọc matched/modified counts và đối soát |
Quên callback/auditing khi chuyển sang bulk | Thiếu metadata và side effect | Test hoặc quản lý tường minh |
Kiểm thử chỉ bằng mock | Không thấy unique index/partial success | Integration test MongoDB thật |

## 16. Bài tập vận dụng

**Bài 1 — Chọn API đúng.** Có ba quy trình: seed 500 sản phẩm mới, lưu 20 entity hiện hữu đã chỉnh trong domain model, nhập 2.000 bản cập nhật giá theo SKU. Chọn `insert`, `saveAll` hay `BulkOperations` cho từng quy trình và giải thích trade-off.

**Bài 2 — Insert nhiều document.** Insert ba entity có ID khác nhau. Lặp lại một ID và ghi nhận lỗi. Kiểm tra xem document cũ có bị ghi đè không. Thử cả `insertAll` và `insert(collection, class)` trên database test.

**Bài 3 — saveAll và isNew.** Tạo entity có ID được ứng dụng cấp và `@Version Long`. Gọi `saveAll` khi version null, sau đó đọc lại entity, đổi tên rồi `saveAll` lần nữa. Quan sát BSON/command và giải thích vì sao “có ID” không luôn đồng nghĩa “entity đã tồn tại”.

**Bài 4 — ORDERED/UNORDERED.** Tạo bulk gồm bốn insert, bản thứ hai trùng unique key. Chạy riêng trên hai database test và đối chiếu document nào thành công. Không giả định rollback cho các write đã hoàn tất.

**Bài 5 — Stock CAS.** Dùng `StockBulkService` với hai command có cùng version và lượng tồn kho khởi tạo 5. Kiểm tra chỉ tối đa một thao tác khớp; thử thiếu hàng và sai tenant.

**Bài 6 — Upsert từ ERP.** Dùng `tenantId + sku` làm business key. Thiết kế update chỉ các field thuộc ERP, có `setOnInsert` cho dữ liệu tạo mới, unique index chống duplicate và chiến lược xử lý event revision cũ.

**Bài 7 — Partial success và retry.** Mô phỏng batch có ba thao tác: một đã ghi, một gặp duplicate, một chưa rõ trạng thái do timeout. Thiết kế bảng theo dõi item ID, checkpoint, đối soát và cách retry mà không tăng tồn kho hai lần.

**Bài 8 — Callback và version.** Tạo entity có `@Version` và auditing timestamp. So sánh insert, repository saveAll và bulk update; viết integration test để kiểm tra version/timestamp thực sự thay đổi ở từng đường.

**Bài 9 — Benchmark.** Sinh 50.000 sản phẩm test (dữ liệu riêng) và so sánh gọi `save` từng cái, `saveAll`, `mongo.insert` theo chunk 500, và `bulkOps` updateOne theo chunk. Đo round trip, p95, throughput, memory và số exception; kết luận theo workload thay vì chỉ theo tên API.

## 17. Ghi nhớ

Trong **Spring Data MongoDB**, **insert nhiều document** biểu đạt **chỉ tạo mới** và dựa vào unique index để từ chối bản ghi trùng. **`MongoRepository.saveAll`** biểu đạt **lưu tập entity**, trong đó cơ chế nhận biết new/existing, `@Version` và cách implementation thực thi quyết định có insert theo lô hay nhiều save riêng. **`MongoTemplate.bulkOps`** biểu đạt **một kế hoạch gồm nhiều thao tác ghi rõ ràng** như insert/update/upsert/delete, cùng lựa chọn `ORDERED` hoặc `UNORDERED`.

Không phương án nào tự biến hàng nghìn ghi thành **một transaction nguyên tử**. Với bulk, cần quan sát `BulkWriteResult` và exception, thừa nhận **thành công một phần**, xác định chính sách retry/idempotency, và kiểm tra version/callback thay vì suy luận theo entity annotation. Đối với import khối lượng lớn, hãy **chia chunk, dùng unique key ổn định, validate input, ghi checkpoint và đối soát item chưa rõ trạng thái**.

Cuối cùng, chọn API theo **ngữ nghĩa nghiệp vụ trước, hiệu năng sau**: tạo mới dùng insert, lưu entity dùng saveAll khi phù hợp, cập nhật/upsert có điều kiện ở quy mô lớn cân nhắc bulk operations. Chỉ integration test trên MongoDB thật và đo lường workload mới xác minh được hành vi thực tế của đường ghi.
